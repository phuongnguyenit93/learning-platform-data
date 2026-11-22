# Không tương thích phiên bản Spring Framework hoặc REST Assured

Spring REST Docs hoạt động cùng test framework và thư viện HTTP client để ghi nhận request/response. Khi nâng cấp Spring Boot, Spring Framework, Spring REST Docs hoặc REST Assured, các dependency có thể không còn tương thích. Biểu hiện thường gặp là lỗi resolve dependency, lỗi biên dịch do API thay đổi, lỗi NoSuchMethodError/NoClassDefFoundError lúc chạy test, recorder không khởi tạo hoặc snippet không được tạo.

Cách xử lý đúng là xác định phiên bản thực tế của toàn bộ dependency trong runtime test classpath, kiểm tra compatibility và chọn một bộ version nhất quán. Không sửa lỗi bằng cách thêm ngẫu nhiên một version khác vào dependencies; điều đó có thể tạo nhiều phiên bản Spring cùng tồn tại và khiến lỗi khó chẩn đoán hơn.

Bài học thuộc chương **Chẩn đoán lỗi** của module `SPRING_REST_DOCS`. Module tạo tài liệu REST API có thể kiểm chứng từ test HTTP bằng MockMvc, WebTestClient hoặc REST Assured, sinh snippet cho request, response, payload, tham số và header, rồi biên soạn Asciidoctor/Markdown và tích hợp build, CI.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện lỗi tương thích giữa Spring Boot, Spring Framework và Spring REST Docs.
2. Kiểm tra phiên bản thực tế thay vì chỉ nhìn version khai báo trực tiếp.
3. Phân biệt lỗi compile-time, dependency resolution và runtime linkage.
4. Chọn đúng REST Assured artifact và phiên bản tương thích với JDK/Spring stack.
5. Phát hiện xung đột javax/jakarta và dependency bị override.
6. Dùng dependency tree để truy nguyên thư viện kéo version không mong muốn.
7. Khôi phục bộ dependency nhất quán và xác minh documentation tests.

## 2. Nhận diện triệu chứng

| Triệu chứng | Nhóm nguyên nhân có thể |
| --- | --- |
| Could not resolve artifact/version | Repository, tọa độ artifact hoặc version không tồn tại/không tương thích |
| Compilation error: cannot find symbol | API thay đổi, package/import sai hoặc dependency compile thiếu |
| NoSuchMethodError | Runtime nạp version class khác với version lúc compile |
| NoClassDefFoundError / ClassNotFoundException | Thiếu artifact, sai module hoặc dependency bị loại |
| NoSuchFieldError / AbstractMethodError | Các module binary không cùng dòng version |
| ClassCastException giữa các kiểu Spring | Nhiều version cùng package/class hoặc classloader khác nhau |
| Test context không khởi động | Spring Boot/Framework/test dependency không đồng bộ |
| MockMvc/WebTestClient setup lỗi | Sai module Spring REST Docs integration hoặc API thay đổi |
| REST Assured filter không được gọi | Sai artifact, API filter hoặc dependency version |
| Test chạy nhưng không sinh snippet | Recorder không được gắn đúng, test bị skip hoặc lỗi cấu hình độc lập |

Thông báo lỗi là manh mối, chưa phải kết luận. Cần xem stack trace đầu tiên có ý nghĩa, class được nạp từ JAR nào và dependency graph của test runtime.

## 3. Các lớp phiên bản cần phối hợp

| Thành phần | Vai trò |
| --- | --- |
| JDK | Quyết định bytecode/API Java mà build và runtime hỗ trợ |
| Spring Boot | Quản lý dependency versions qua dependency management/BOM |
| Spring Framework | Cung cấp Spring MVC, WebFlux, TestContext và MockMvc |
| Spring REST Docs | Cung cấp core API và integration modules |
| REST Assured | Cung cấp DSL HTTP, request specification và filter |
| JUnit / TestNG | Test engine và API lifecycle |
| Gradle / Maven | Resolve dependency, compile và chạy test |
| Asciidoctor plugin | Render tài liệu từ snippet và source |

Một version riêng lẻ có thể hợp lệ nhưng cả tổ hợp không hợp lệ. Spring REST Docs integration cần đúng API Spring Test; REST Assured cần artifact phù hợp test stack; JDK phải đáp ứng yêu cầu của thư viện và plugin.

## 4. Kiểm tra version Spring đang thực sự được sử dụng

### 4.1. Spring Boot quản lý dependency

Nếu dự án dùng Spring Boot, ưu tiên dependency management/BOM do phiên bản Boot cung cấp. Tránh tự khai báo version cho từng module Spring Framework nếu không có lý do đã được kiểm chứng.

Ví dụ Gradle:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.restdocs:spring-restdocs-mockmvc")
}
```

Ví dụ Maven khi dùng Spring Boot parent hoặc BOM:

```xml
<dependency>
  <groupId>org.springframework.restdocs</groupId>
  <artifactId>spring-restdocs-mockmvc</artifactId>
  <scope>test</scope>
</dependency>
```

Không ghi version cho Spring REST Docs chỉ khi dependency management phù hợp đã quản lý version đó. Nếu không có BOM/parent quản lý, khai báo version rõ ràng theo tài liệu phát hành tương ứng.

### 4.2. Không trộn version Spring Framework tùy tiện

Các module Spring Framework như spring-core, spring-context, spring-test, spring-webmvc và spring-webflux thường cần cùng release train. Nếu một dependency kéo spring-test khác version với spring-webmvc, test có thể compile nhưng thất bại runtime.

Không sửa bằng cách thêm spring-test version mới nhất vào cuối file. Hãy xác định BOM/parent quản lý version nào và dependency nào override nó.

## 5. Chọn Spring REST Docs integration module đúng

| Test client | Integration module thường dùng |
| --- | --- |
| MockMvc | spring-restdocs-mockmvc |
| WebTestClient | spring-restdocs-webtestclient |
| REST Assured | spring-restdocs-restassured |

Chọn module khớp test client đang dùng. Không thêm cả ba module chỉ để thử chữa lỗi nếu dự án chỉ dùng một loại client.

Ví dụ Maven cho MockMvc:

```xml
<dependency>
  <groupId>org.springframework.restdocs</groupId>
  <artifactId>spring-restdocs-mockmvc</artifactId>
  <scope>test</scope>
</dependency>
```

Ví dụ Gradle:

```groovy
testImplementation(
    "org.springframework.restdocs:spring-restdocs-mockmvc:<version-managed-by-project>"
)
```

Placeholder version phải được thay bằng version dự án quản lý. Chọn version phù hợp Spring stack và JDK; không copy version từ hướng dẫn dành cho release train khác.

### 5.1. Core và integration module

Integration module phụ thuộc core API của Spring REST Docs. Tránh khai báo hai version khác nhau cho core và integration module. Nếu dependency management không quản lý chúng, đặt cùng release version theo hướng dẫn phát hành của Spring REST Docs.

NoSuchMethodError trong package org.springframework.restdocs có thể cho thấy runtime đang dùng các module REST Docs không đồng bộ hoặc test compile/runtime classpath khác nhau.

## 6. Tương thích REST Assured

REST Assured có các module/artifact riêng cho core DSL, Spring MockMvc và WebTestClient trong những cấu hình tương ứng. Tọa độ artifact và API có thể thay đổi theo dòng phiên bản.

Khi dùng REST Assured với Spring REST Docs:

1. Xác định test gửi request bằng REST Assured standalone hay tích hợp MockMvc/WebTestClient.
2. Chọn đúng REST Assured module cho integration đó.
3. Chọn Spring REST Docs REST Assured integration module.
4. Kiểm tra REST Assured version và Spring REST Docs version tương thích với JDK và test API.
5. Kiểm tra không có REST Assured core/module bị kéo hai version khác nhau.

Ví dụ dependency declaration minh họa:

```groovy
dependencies {
    testImplementation("io.rest-assured:rest-assured:<ra-version>")
    testImplementation(
        "org.springframework.restdocs:spring-restdocs-restassured:<restdocs-version>"
    )
}
```

Placeholder cần thay bằng version đã chọn từ compatibility/release documentation của đúng dòng thư viện. Sau đó xác minh dependency graph.

### 6.1. Lỗi API filter sau nâng cấp

Nếu code không còn compile ở lời gọi filter, request specification hoặc cấu hình MockMvc/WebTestClient:

- Đọc compile error đầu tiên và xác định class/method bị đổi.
- Kiểm tra import trỏ tới đúng package/artifact.
- Đối chiếu API docs/changelog của version đang dùng.
- Kiểm tra ví dụ trong dự án có dùng API deprecated đã bị loại bỏ không.
- Nâng cấp code test theo API mới thay vì thêm JAR cũ để giữ API cũ.

## 7. JDK và build tool cũng nằm trong compatibility matrix

Một thư viện có thể tương thích Spring nhưng yêu cầu JDK mới hơn. Build tool/plugin cũng có yêu cầu runtime riêng.

Kiểm tra JDK dùng chạy Gradle/Maven, Java toolchain dùng compile, Gradle/Maven wrapper, Asciidoctor plugin, bytecode target/source compatibility và JDK trên CI runner.

Lệnh kiểm tra cơ bản:

```bash
java -version
./gradlew --version
./mvnw -version
```

Chỉ chạy lệnh tương ứng build tool của dự án. Với Gradle, wrapper version và JVM chạy Gradle có thể khác toolchain dùng compile project.

## 8. Xung đột javax và jakarta

Một thay đổi lớn trong hệ sinh thái Java là chuyển từ namespace javax sang jakarta ở nhiều API enterprise. Spring Framework 6 và Spring Boot 3 trở lên dựa trên Jakarta EE namespace cho các integration liên quan.

Triệu chứng thường gặp:

- ClassNotFoundException với package javax.* hoặc jakarta.*.
- Method signature không khớp do module dùng namespace cũ.
- Servlet API hoặc validation API bị kéo version không tương thích.
- Test runtime có cả API cũ và mới.

Không thay hàng loạt import chỉ để hết lỗi. Xác định Spring Boot/Framework major version, servlet container/API và thư viện tích hợp. Với stack Spring Boot 3/Spring Framework 6, kiểm tra dependency liên quan đã chuyển sang Jakarta tương thích. Nếu dự án dùng stack Spring cũ, chọn namespace và integration tương ứng.

Spring REST Docs không tự chuyển ứng dụng từ javax sang jakarta; đây là việc nâng cấp toàn bộ dependency/application stack.

## 9. Dùng dependency tree tìm version bị kéo vào

### 9.1. Gradle

Liệt kê dependency test runtime:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Tìm nguyên nhân chọn version cho một module:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
```

Kiểm tra thêm spring-core, spring-webmvc, spring-restdocs, rest-assured và servlet API. dependencyInsight giúp biết dependency nào yêu cầu version, version nào được chọn và có rule nào thay thế.

### 9.2. Maven

Xem dependency tree:

```bash
./mvnw dependency:tree -Dscope=test
```

Lọc theo nhóm thư viện nếu output dài:

```bash
./mvnw dependency:tree -Dscope=test -Dincludes=org.springframework
./mvnw dependency:tree -Dscope=test -Dincludes=org.springframework.restdocs
./mvnw dependency:tree -Dscope=test -Dincludes=io.rest-assured
```

Kiểm tra dependency management và effective POM khi version đến từ parent/BOM hoặc profile.

## 10. Cách đọc lỗi linkage

| Exception | Ý nghĩa thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| NoSuchMethodError | Class runtime không có method mà code đã compile cần | JAR thực tế, duplicate versions, dependency mediation |
| NoClassDefFoundError | Class cần thiết không có ở runtime hoặc khởi tạo class thất bại | Missing artifact, scope, static initialization cause |
| ClassNotFoundException | Code/classloader yêu cầu class không tìm thấy | Artifact, package namespace, classpath |
| NoSuchFieldError | Field không có trong version class runtime | Module version mismatch |
| AbstractMethodError | Implementation không đáp ứng interface runtime | Version API và implementation |
| IncompatibleClassChangeError | Cấu trúc class/interface không tương thích | Binary compatibility giữa dependency |

Stack trace có thể bọc exception gốc. Đọc cause đầu tiên có thông tin class/method và xem class đó đến từ JAR nào. Với Gradle, dependencyInsight và runtime classpath là điểm bắt đầu; với Maven, dùng dependency:tree và kiểm tra resolved artifacts.

## 11. Quy trình xử lý có hệ thống

1. **Ghi nhận lỗi:** lấy compile error hoặc stack trace đầy đủ, không chỉ dòng cuối.
2. **Xác định phase:** dependency resolution, compile, test context startup, test execution hay render.
3. **Ghi version môi trường:** JDK, Gradle/Maven, Spring Boot, Spring Framework, Spring REST Docs và REST Assured.
4. **Xem dependency graph:** tìm module bị kéo nhiều version hoặc version override.
5. **Kiểm tra compatibility:** đối chiếu release notes và reference của đúng version.
6. **Chọn một bộ version:** dùng Boot BOM/parent nếu phù hợp; tránh override rời rạc.
7. **Resolve lại sạch:** refresh dependencies khi cần và clean output.
8. **Chạy test nhỏ nhất:** bắt đầu với một documentation test dùng integration module liên quan.
9. **Chạy toàn bộ docs tests:** xác minh snippet được tạo đúng.
10. **Render tài liệu:** chỉ thực hiện sau khi test pass.

Không nâng đồng thời mọi dependency lên latest để thử. Thay đổi nhiều biến cùng lúc khiến khó xác định dependency nào gây lỗi.

## 12. Ví dụ xử lý tình huống

### Tình huống A: NoSuchMethodError trong Spring Test

Ứng dụng compile thành công nhưng chạy MockMvc documentation test lại lỗi NoSuchMethodError trong class thuộc Spring Test.

Cách xử lý:

- Chạy dependencyInsight cho spring-test và spring-webmvc.
- Kiểm tra chúng có cùng release train không.
- Xem Spring Boot BOM có bị override bởi dependency version khai báo trực tiếp không.
- Gỡ override không cần thiết và để BOM quản lý đồng bộ.
- Chạy lại một MockMvc test rồi toàn bộ documentation tests.

### Tình huống B: REST Assured filter không compile sau nâng version

Lời gọi filter hoặc request specification không còn khớp method signature.

Cách xử lý:

- Xác nhận artifact REST Assured đang dùng và version thực tế.
- Kiểm tra import có trỏ tới API của module đúng không.
- Đọc migration/release notes của REST Assured version mới.
- Sửa test code theo API mới.
- Kiểm tra Spring REST Docs REST Assured integration có cùng dòng tương thích.

### Tình huống C: ClassNotFoundException sau chuyển Spring Boot major

Test báo thiếu class thuộc javax hoặc jakarta.

Cách xử lý:

- Xác định Spring Boot/Framework major version.
- Xác định servlet container và API namespace của ứng dụng.
- Tìm dependency cũ kéo javax hoặc dependency mới kéo jakarta không đồng bộ.
- Nâng/cấu hình integration library tương thích với stack đã chọn.
- Chạy test context và documentation test để xác nhận.

## 13. Ma trận kiểm tra trước khi nâng cấp

Duy trì bảng version đã được dự án xác nhận:

| Thành phần | Version đang dùng | Kiểm tra |
| --- | --- | --- |
| JDK | Theo toolchain/CI | Thư viện và plugin hỗ trợ |
| Spring Boot | Theo parent/BOM | Quản lý version Spring |
| Spring Framework | Do BOM quản lý | Các module đồng bộ |
| Spring REST Docs | Version thống nhất | Core và integration module đồng bộ |
| REST Assured | Theo compatibility docs | Artifact/API phù hợp |
| JUnit | Theo test stack | Test engine tương thích |
| Gradle/Maven | Wrapper đã pin | Plugin và JDK tương thích |
| Asciidoctor plugin | Version đã pin | Chạy được trên build runtime |

Cập nhật bảng khi nâng cấp framework hoặc test client. Ghi rõ version được kiểm tra trong CI để người khác không phải suy đoán từ build file.

## 14. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Nhiều version spring-test | Dependency override hoặc transitive conflict | Dùng BOM và kiểm tra dependency tree |
| REST Docs core/integration lệch version | Khai báo version riêng | Quản lý cùng release version |
| Không tìm thấy REST Docs class | Thiếu integration module hoặc sai scope | Thêm module đúng test client ở test scope |
| REST Assured filter API không khớp | Sai artifact/version hoặc API thay đổi | Kiểm tra release notes và imports |
| javax/jakarta ClassNotFound | Stack namespace không đồng bộ | Chọn dependency theo Spring major |
| Test compile nhưng runtime lỗi | Compile/runtime classpath khác nhau | Kiểm tra testRuntimeClasspath/dependency tree |
| CI lỗi nhưng local pass | JDK hoặc dependency resolution khác | Pin wrapper/JDK và kiểm tra CI graph |
| Plugin Asciidoctor không chạy | Plugin yêu cầu JDK/build tool khác | Kiểm tra plugin compatibility |
| Refresh dependencies vẫn lỗi | Version constraints/BOM vẫn chọn bản xung đột | Xem dependencyInsight/effective POM |
| Nâng nhiều thư viện cùng lúc | Không xác định được nguồn lỗi | Thay đổi từng nhóm và chạy test |

## 15. Best practices

1. Dùng Spring Boot BOM/parent để quản lý Spring dependencies khi dự án dùng Boot.
2. Giữ các module Spring Framework trong cùng release train.
3. Đồng bộ Spring REST Docs core và integration module.
4. Chọn đúng integration module theo MockMvc, WebTestClient hoặc REST Assured.
5. Kiểm tra REST Assured artifact/API theo version thực tế, không copy dependency từ ví dụ khác dòng.
6. Pin JDK, Gradle/Maven wrapper và plugin versions.
7. Dùng dependency tree/insight trước khi thêm exclusion hoặc override.
8. Xử lý chuyển javax/jakarta ở cấp toàn bộ stack.
9. Nâng cấp từng nhóm dependency, chạy test nhỏ rồi toàn bộ documentation tests.
10. Ghi lại version matrix đã được CI xác minh.

## 16. Bài thực hành

Một dự án Spring Boot dùng MockMvc và Spring REST Docs. Sau khi nâng cấp dependency, documentation test lỗi NoSuchMethodError trong Spring Test. Một module khác khai báo REST Assured với version trực tiếp.

**Nhiệm vụ:**

1. Ghi nhận JDK, Gradle/Maven wrapper, Spring Boot và Spring REST Docs versions.
2. Chạy dependencyInsight hoặc dependency:tree cho spring-test, spring-webmvc và spring-restdocs.
3. Xác định dependency nào override version do BOM quản lý.
4. Kiểm tra core và integration module của REST Docs có cùng version không.
5. Kiểm tra REST Assured artifact/version và lý do module đó cần thiết.
6. Gỡ override không cần thiết hoặc điều chỉnh version theo compatibility documentation.
7. Chạy một MockMvc documentation test.
8. Chạy toàn bộ documentation tests và xác minh snippets được tạo.
9. Render Asciidoctor.
10. Ghi version matrix đã xác minh vào tài liệu dự án.

**Tiêu chí hoàn thành:** dependency graph nhất quán; không còn linkage/classpath error; integration module đúng test client; documentation tests pass; snippets và tài liệu render thành công.

## 17. Ghi nhớ

- Lỗi tương thích có thể đến từ Spring Boot, Spring Framework, Spring REST Docs, REST Assured, JDK hoặc build plugin.
- Kiểm tra version thực tế trong runtime classpath, không chỉ version khai báo trực tiếp.
- Dùng BOM/parent phù hợp để giữ các module Spring đồng bộ.
- Chọn đúng Spring REST Docs integration module cho MockMvc, WebTestClient hoặc REST Assured.
- Dùng dependencyInsight hoặc dependency:tree để tìm dependency kéo version không mong muốn.
- NoSuchMethodError thường gợi ý compile/runtime binary mismatch; ClassNotFoundException thường gợi ý thiếu artifact hoặc namespace sai.
- Kiểm tra javax/jakarta theo Spring major version và toàn bộ stack.
- Sau khi sửa dependency, chạy documentation tests rồi render lại tài liệu.
