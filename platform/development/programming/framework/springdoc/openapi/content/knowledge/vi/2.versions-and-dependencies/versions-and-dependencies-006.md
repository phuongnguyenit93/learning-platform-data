# Khai báo phụ thuộc bằng Maven hoặc Gradle

## 1. Vì sao phải khai báo đúng phụ thuộc Springdoc?

Springdoc OpenAPI đọc metadata từ ứng dụng Spring Boot để tạo OpenAPI document và, nếu dùng module giao diện, cung cấp Swagger UI. Để quá trình này hoạt động, ứng dụng cần khai báo đúng thư viện theo loại web stack, phiên bản Spring Boot và nhu cầu triển khai.

Khai báo sai artifact hoặc sai major version có thể khiến ứng dụng không khởi động, không đăng ký endpoint /v3/api-docs, thiếu Swagger UI, lỗi class khi chạy hoặc kéo vào hai bộ thư viện không tương thích.

Module SPRINGDOC_OPENAPI tập trung dùng springdoc-openapi để tạo và tùy biến đặc tả OpenAPI cùng Swagger UI từ controller Spring Boot. Vì vậy, lựa chọn dependency cần phục vụ đúng các nhu cầu: mô tả request/response, schema, security, document groups, xuất JSON/YAML, kiểm thử contract và phân phối tài liệu API.

Maven và Gradle đều quản lý dependency graph, nhưng cú pháp và cách tập trung version khác nhau. Cần hiểu artifact nào được chọn trước khi thêm nó vào build file.

## 2. Chọn starter theo web stack

Springdoc cung cấp artifact khác nhau cho Spring MVC và Spring WebFlux. Chọn theo stack thực tế của ứng dụng:

| Web stack | Starter có Swagger UI | Starter chỉ cung cấp API docs |
|---|---|---|
| Spring MVC | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webmvc-api |
| Spring WebFlux | springdoc-openapi-starter-webflux-ui | springdoc-openapi-starter-webflux-api |

Starter có hậu tố ui thường tích hợp OpenAPI endpoint và Swagger UI. Starter có hậu tố api cung cấp phần sinh OpenAPI document mà không cần đóng gói giao diện Swagger UI.

Một ứng dụng Spring MVC dùng spring-boot-starter-web thường chọn webmvc starter. Ứng dụng reactive dùng spring-boot-starter-webflux thường chọn webflux starter.

Không thêm cả webmvc-ui và webflux-ui vào cùng ứng dụng chỉ để thử. Hai web stack có cách xử lý request khác nhau và có thể kéo theo cấu hình auto-configuration không mong muốn.

Nếu ứng dụng có kiến trúc đặc biệt hoặc dùng cả hai stack, hãy xác minh rõ runtime thực tế và hướng dẫn Springdoc của phiên bản tương ứng trước khi chọn dependency.

## 3. Phân biệt starter UI và starter API

Chọn starter theo nơi tài liệu sẽ được sử dụng:

**Dùng starter UI khi:**

- Developer cần mở Swagger UI trong trình duyệt.
- Nhóm cần thử request trực tiếp bằng Try it out.
- Ứng dụng phục vụ tài liệu cho người tích hợp.
- Muốn có sẵn giao diện mà không tự xây trang tài liệu.

**Dùng starter API khi:**

- Chỉ cần endpoint OpenAPI JSON/YAML.
- CI tải document để validate, lint hoặc so sánh contract.
- Một developer portal khác render OpenAPI document.
- Muốn giảm tài nguyên UI trong runtime production.

Tắt Swagger UI bằng property không giống với việc không đưa dependency UI vào artifact. Nếu dự án không cần giao diện ở bất kỳ môi trường nào, starter API thường diễn đạt mục đích rõ hơn.

Dù dùng starter nào, OpenAPI document vẫn có thể được cung cấp qua endpoint Springdoc nếu api-docs được bật.

## 4. Kiểm tra tương thích giữa Spring Boot và Springdoc

Springdoc có các dòng artifact khác nhau theo major version của Spring Boot. Không chọn dependency chỉ dựa vào việc tên artifact trông gần giống nhau.

Quy tắc tổng quát:

| Nền tảng | Dòng Springdoc thường tương ứng | Lưu ý |
|---|---|---|
| Spring Boot 2.x | Springdoc 1.x, artifact legacy | Dùng artifact như springdoc-openapi-ui hoặc springdoc-openapi-webflux-ui theo stack |
| Spring Boot 3.x | Springdoc 2.x, starter mới | Dùng starter có hậu tố webmvc hoặc webflux |
| Spring Boot major mới hơn | Kiểm tra compatibility matrix của Springdoc | Không suy ra major Springdoc chỉ từ số major Spring Boot |

Spring Boot 3 chuyển sang Jakarta EE APIs, vì vậy dependency cần tương thích với namespace jakarta. Dòng Springdoc 2.x starter được thiết kế cho nền tảng Spring Boot 3. Không ghép tùy tiện thư viện cũ dùng javax với ứng dụng Jakarta.

Bảng trên là định hướng lựa chọn, không thay thế compatibility matrix chính thức. Trước khi pin version, kiểm tra chính xác Spring Boot patch line, Java version, Spring Framework và Springdoc release được hỗ trợ.

Không dùng version động như latest.release trong release build. Pin một version cụ thể để local, CI và production giải quyết cùng dependency graph.

## 5. Khai báo dependency bằng Maven

Trong dự án Maven có Spring Boot parent hoặc dependency management phù hợp, thêm starter vào phần dependencies.

Ví dụ Spring MVC với Swagger UI:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>2.x.y</version>
    </dependency>
</dependencies>
~~~

Thay 2.x.y bằng version Springdoc đã xác minh tương thích với Spring Boot của dự án. Không giữ nguyên placeholder trong pom.xml.

Với ứng dụng WebFlux, thay artifact bằng:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Nếu chỉ cần OpenAPI endpoint mà không cần Swagger UI, dùng artifact API tương ứng:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Không thêm cả UI và API starter cùng web stack nếu UI starter đã cung cấp chức năng API cần thiết. Chọn một artifact phù hợp với nhu cầu.

## 6. Quản lý version Springdoc trong Maven

Với dự án có nhiều module, không nên lặp một version literal ở nhiều pom.xml. Có thể khai báo property trong parent POM:

~~~xml
<properties>
    <springdoc.version>2.x.y</springdoc.version>
</properties>
~~~

Sau đó dùng property đó làm version cho dependency Springdoc ở module cần thiết. Trong ví dụ minh họa, version literal 2.x.y phải được thay bằng property reference Maven tương ứng khi đưa vào POM thật.

Nếu nhiều module cùng dùng Springdoc, có thể đặt dependency trong dependencyManagement của parent để quản lý version tập trung, còn từng module khai báo artifact mình thực sự cần.

Ví dụ dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>2.x.y</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Module con có thể khai báo dependency mà không cần lặp version nếu dependencyManagement đã quản lý đúng tọa độ artifact.

Không đặt mọi dependency Springdoc vào parent dependencies nếu một số module không phải web application. Parent nên quản lý version; module con quyết định có cần thư viện hay không.

## 7. Khai báo dependency bằng Gradle Groovy DSL

Với build.gradle dùng Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui:2.x.y'
}
~~~

Với WebFlux:

~~~groovy
dependencies {
    implementation 'org.springdoc:springdoc-openapi-starter-webflux-ui:2.x.y'
}
~~~

Chỉ cần OpenAPI API:

~~~groovy
dependencies {
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-api:2.x.y'
}
~~~

Thay version placeholder bằng release tương thích đã pin. Gradle dùng implementation để dependency có mặt trên compile classpath của module và runtime classpath của ứng dụng.

Không dùng testImplementation cho dependency mà ứng dụng cần khi chạy thật. Nếu chỉ đặt Springdoc ở test scope, test có thể thấy class nhưng executable application không có endpoint docs.

## 8. Khai báo dependency bằng Gradle Kotlin DSL

Với build.gradle.kts:

~~~kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.x.y")
}
~~~

WebFlux:

~~~kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webflux-ui:2.x.y")
}
~~~

API-only:

~~~kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-api:2.x.y")
}
~~~

Kotlin DSL dùng lời gọi function và dấu ngoặc. Coordinates vẫn có dạng group:artifact:version như Groovy DSL.

Nếu dùng convention plugin hoặc shared build logic, có thể đặt dependency declaration trong một nơi dùng chung. Tuy nhiên, module chỉ nên nhận starter tương ứng với web stack của chính nó.

## 9. Quản lý version bằng Gradle Version Catalog

Trong dự án Gradle nhiều module, Version Catalog giúp quản lý version và alias tập trung.

Ví dụ gradle/libs.versions.toml:

~~~toml
[versions]
springdoc = "2.x.y"

[libraries]
springdoc-webmvc-ui = { module = "org.springdoc:springdoc-openapi-starter-webmvc-ui", version.ref = "springdoc" }
springdoc-webflux-ui = { module = "org.springdoc:springdoc-openapi-starter-webflux-ui", version.ref = "springdoc" }
springdoc-webmvc-api = { module = "org.springdoc:springdoc-openapi-starter-webmvc-api", version.ref = "springdoc" }
~~~

Sau đó trong build.gradle.kts:

~~~kotlin
dependencies {
    implementation(libs.springdoc.webmvc.ui)
}
~~~

Hoặc module WebFlux:

~~~kotlin
dependencies {
    implementation(libs.springdoc.webflux.ui)
}
~~~

Gradle tạo accessor từ alias trong catalog. Alias springdoc-webmvc-ui thường được truy cập bằng libs.springdoc.webmvc.ui trong Kotlin DSL.

Version Catalog tập trung version và tên dependency; nó không tự bảo đảm version đã tương thích. Nhóm vẫn cần kiểm tra compatibility matrix trước khi nâng.

## 10. Dùng property hoặc convention plugin trong Gradle

Nếu chưa dùng Version Catalog, có thể quản lý version bằng Gradle property hoặc extra property trong build logic chung.

Ví dụ khai báo trực tiếp trong một build script:

~~~kotlin
val springdocVersion = "2.x.y"

dependencies {
    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion"
    )
}
~~~

Trong dự án lớn, nên tránh khai báo cùng một version riêng ở nhiều subproject. Dùng Version Catalog hoặc convention plugin để mọi module được kiểm soát theo một chính sách.

Không tạo biến version mới ở từng module nếu chúng phải luôn đồng bộ. Một nơi quản lý version giúp review nâng cấp dễ hơn và giảm nguy cơ một service chạy Springdoc khác major với các service còn lại.

## 11. Maven và Gradle: chọn cách quản lý nào?

| Tiêu chí | Maven | Gradle |
|---|---|---|
| Khai báo dependency | dependencies/dependency trong pom.xml | implementation trong build.gradle hoặc build.gradle.kts |
| Version tập trung | Parent properties và dependencyManagement | Version Catalog, convention plugin hoặc shared property |
| Kiểm tra dependency | dependency:tree | dependencies, dependencyInsight |
| Scope runtime/compile | Maven scope | Gradle configuration |
| Multi-module | Parent POM và module | Root build, subprojects và convention plugins |
| Locking | Dependency management và plugin hỗ trợ | Dependency locking tích hợp |

Không có lựa chọn nào tự động làm Springdoc tương thích hơn. Điều quan trọng là version được pin, artifact đúng web stack và dependency graph không chứa các phiên bản xung đột.

Dùng build tool mà dự án đã chọn. Không thêm Gradle chỉ để khai báo một dependency cho ứng dụng Maven hoặc ngược lại.

## 12. Hiểu scope và configuration của dependency

Với Maven, dependency không khai báo scope thường dùng compile scope. Starter Springdoc cần có mặt khi ứng dụng chạy, nên không đặt nó ở test scope.

Các scope thường gặp:

- compile: có trong compile và runtime classpath.
- runtime: không cần cho compile nhưng có trong runtime.
- provided: kỳ vọng môi trường triển khai cung cấp.
- test: chỉ có trong test classpath.

Với Gradle, implementation thường là lựa chọn phù hợp cho starter mà ứng dụng cần cả khi compile và runtime. testImplementation chỉ dành cho thư viện chỉ phục vụ test.

Không dùng compileOnly cho starter Springdoc nếu runtime cần auto-configuration và endpoint. Ứng dụng có thể compile nhưng khi chạy thiếu class hoặc không đăng ký bean.

Nếu dự án có packaging đặc biệt, kiểm tra nội dung executable JAR/container image để bảo đảm dependency thực sự được đóng gói.

## 13. Không khai báo đồng thời nhiều starter không cần thiết

Một số cấu hình sai thường gặp:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x.y</version>
</dependency>
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Nếu UI starter đã bao gồm API documentation support, khai báo thêm API starter cùng stack thường không cần thiết. Có thể làm dependency graph khó hiểu và tăng rủi ro version conflict nếu hai dependency bị quản lý khác nhau.

Một lỗi khác là thêm cả starter WebMVC và WebFlux dù ứng dụng chỉ dùng một stack. Chỉ thêm dependency mà ứng dụng thực sự cần.

Nếu cần nhiều chức năng Springdoc chuyên biệt như Data REST, Security hoặc Kotlin support, hãy kiểm tra module tương ứng trong tài liệu đúng version. Không tự thêm các artifact nội bộ chỉ vì thấy tên trong dependency tree.

## 14. Tránh trộn Springdoc 1.x và 2.x

Dòng Springdoc 1.x dùng artifact legacy như:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.8.x</version>
</dependency>
~~~

Dòng Springdoc 2.x dùng starter mới, ví dụ:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Không thêm cả hai dòng vào cùng một ứng dụng. Chúng có cấu trúc module, dependency và nền tảng tương thích khác nhau.

Khi nâng từ 1.x lên 2.x, cần đổi artifact coordinates theo hướng dẫn migration, kiểm tra Jakarta namespace, Swagger Core và Spring Boot compatibility. Không chỉ thay số version ở một dependency cũ rồi kỳ vọng starter mới hoạt động.

## 15. Không override Swagger Core tùy tiện

Springdoc phụ thuộc vào các thư viện Swagger Core để xử lý annotation và OpenAPI model. Starter thường khai báo các dependency tương thích cần thiết.

Nếu dự án tự thêm swagger-core, swagger-models hoặc swagger-annotations với version khác, có thể tạo ra binary incompatibility:

- NoSuchMethodError khi runtime gọi method không có trong version đang nạp.
- NoClassDefFoundError khi thiếu class.
- Annotation không được đọc như dự kiến.
- Schema hoặc document được serialize sai.
- Classpath chứa nhiều version cùng thư viện.

Không thêm Swagger Core chỉ vì muốn dùng @Schema hoặc @Operation; starter Springdoc thường đã cung cấp dependency annotation cần thiết qua transitive dependencies.

Chỉ override version khi có lý do kỹ thuật, đã kiểm tra compatibility và có test xác nhận. Ghi rõ lý do trong dependency management để người nâng cấp sau hiểu được ràng buộc.

## 16. Kiểm tra dependency tree với Maven

Dùng dependency:tree để xem Springdoc và Swagger Core thực sự được giải quyết:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

Có thể kiểm tra toàn bộ dependency tree khi cần:

~~~bash
./mvnw dependency:tree
~~~

Tập trung kiểm tra:

- Có đúng một dòng Springdoc major được dùng.
- Artifact webmvc hoặc webflux khớp ứng dụng.
- Không có version Swagger Core bị override ngoài dự kiến.
- Không có dependency cũ được kéo từ module khác.
- Scope runtime có chứa starter cần thiết.

Nếu Maven chọn version khác với version khai báo trực tiếp, kiểm tra dependencyManagement, parent POM và mediation rule. Maven có thể chọn dependency gần nhất trong graph khi không có quản lý version rõ ràng.

Không xóa dependency transitive một cách máy móc. Trước khi exclude, xác định dependency nào kéo thư viện đó vào và starter có thật sự cần nó không.

## 17. Kiểm tra dependency graph với Gradle

Gradle có thể hiển thị dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để tìm nguồn của một dependency:

~~~bash
./gradlew dependencyInsight \
  --dependency springdoc-openapi \
  --configuration runtimeClasspath
~~~

Có thể chạy dependencyInsight cho Swagger Core khi nghi ngờ version conflict:

~~~bash
./gradlew dependencyInsight \
  --dependency swagger-core \
  --configuration runtimeClasspath
~~~

Kiểm tra configuration runtimeClasspath vì đây là nơi dependency cần có khi ứng dụng chạy. CompileClasspath có thể đúng trong khi runtimeClasspath thiếu hoặc resolve version khác.

Nếu dùng dependency locking, cập nhật lockfile theo quy trình dự án sau khi xác minh version. Không xóa lockfile chỉ để Gradle tự chọn một dependency graph mới.

## 18. Phân biệt lỗi compile-time và runtime

Một dependency có thể khiến build compile thành công nhưng ứng dụng chạy sai.

| Hiện tượng | Nơi kiểm tra |
|---|---|
| Không tìm thấy package annotation khi compile | Compile classpath và artifact annotation |
| Ứng dụng khởi động nhưng /v3/api-docs trả 404 | Starter, auto-configuration và profile |
| Swagger UI không có static resources | Có dùng UI starter hay API-only starter |
| NoClassDefFoundError | Runtime dependency graph |
| NoSuchMethodError | Version conflict giữa Springdoc và Swagger Core |
| Bean creation exception | Compatibility, auto-configuration và classpath |
| MVC handler không được phát hiện | Chọn sai web stack hoặc cấu hình MVC |
| WebFlux endpoint không xuất hiện | Chọn nhầm starter MVC hoặc mapping reactive |
| Annotation bị bỏ qua | Swagger annotations version/namespace và scan configuration |

Khi lỗi xảy ra, ghi lại stack trace đầu tiên và dependency tree. Không thêm ngẫu nhiên một artifact khác để chữa lỗi trước khi biết class nào bị thiếu hoặc version nào bị lệch.

## 19. Kiểm tra endpoint sau khi thêm dependency

Sau khi build và chạy ứng dụng, kiểm tra endpoint tài liệu:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs
~~~

Nếu dùng Swagger UI starter, mở:

~~~text
http://localhost:8080/swagger-ui/index.html
~~~

Nếu dùng API-only starter, không mong đợi Swagger UI được đóng gói. OpenAPI JSON/YAML vẫn có thể hoạt động.

Kiểm tra document có:

- Trường openapi.
- info.title và info.version.
- Operation dự kiến trong paths.
- Schema cần thiết trong components.
- Response và security metadata.
- Server URL đúng môi trường.

HTTP 200 chưa đủ để xác minh tài liệu. Response có thể là HTML login page hoặc document rỗng. Trong CI, parse và validate document bằng OpenAPI-aware tool.

## 20. Kiểm tra dependency trong test

Có thể dùng Spring Boot test với MockMvc để xác minh endpoint docs:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldExposeOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.info.title").exists());
    }
}
~~~

Test cần có import và static imports tương ứng trong dự án. Nếu API docs được bảo vệ, test phải xác thực bằng user/role phù hợp hoặc cấu hình test security có chủ đích.

Với WebFlux, dùng WebTestClient thay vì MockMvc cho endpoint reactive.

Một test đơn giản giúp phát hiện starter không được load, api-docs bị tắt hoặc path bị đổi. Nó không thay thế contract validation và kiểm tra đầy đủ schema.

## 21. Multi-module và shared dependency management

Trong Maven multi-module, parent POM có thể quản lý Springdoc version tập trung qua properties hoặc dependencyManagement. Module web cụ thể khai báo starter theo stack của nó.

Trong Gradle multi-project, Version Catalog hoặc convention plugin có thể quản lý alias/version. Module API chọn đúng alias, ví dụ webmvc-ui hoặc webflux-api.

Không ép mọi module dùng Springdoc nếu module đó không expose HTTP API. Một module domain hoặc persistence library thường không cần starter web documentation.

Nếu nhiều service cần Springdoc, hãy đồng bộ version theo policy chung nhưng vẫn cho phép nâng cấp có kiểm soát khi một service cần tương thích khác. Không dùng một dependency block toàn cục áp vào mọi subproject.

## 22. Quy trình nâng version Springdoc

Khi nâng Springdoc:

1. Xác định Spring Boot và Java version hiện tại.
2. Kiểm tra compatibility matrix của Springdoc.
3. Chọn artifact đúng web stack.
4. Đổi version tại nơi quản lý tập trung.
5. Xem release notes và migration notes.
6. Kiểm tra transitive Swagger Core dependencies.
7. Build sạch và chạy test.
8. Khởi động ứng dụng, tải JSON/YAML.
9. Kiểm tra Swagger UI nếu dùng UI starter.
10. Validate document và so sánh contract diff.
11. Kiểm tra behavior của annotation, customizer và document groups.
12. Commit lockfile hoặc dependency changes theo quy trình dự án.

Không nâng Spring Boot, Springdoc, Swagger Core và các plugin build cùng lúc nếu không cần thiết. Thay từng nhóm có kiểm soát giúp xác định nguyên nhân khi có regression.

## 23. Những lỗi thường gặp khi khai báo Maven hoặc Gradle

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Maven không resolve artifact | Sai groupId/artifactId hoặc repository | Kiểm tra tọa độ artifact và repository |
| Gradle không tìm thấy module | Coordinates sai hoặc version không tồn tại | Kiểm tra catalog và dependency declaration |
| /v3/api-docs trả 404 | Starter sai, docs bị disable hoặc profile khác | Kiểm tra web stack và api-docs.enabled |
| Swagger UI không có | Dùng API-only starter | Chuyển sang UI starter nếu cần giao diện |
| NoClassDefFoundError | Runtime classpath thiếu dependency | Xem runtime dependency tree |
| NoSuchMethodError | Swagger Core/Springdoc version conflict | Kiểm tra dependency mediation và override |
| javax/jakarta class mismatch | Trộn dependency theo Spring Boot major khác nhau | Dùng dòng Springdoc tương thích |
| Cả MVC và WebFlux cùng được load | Thêm nhiều starter không cần thiết | Chọn đúng một stack |
| Annotation không có hiệu lực | Thiếu hoặc lệch Swagger annotations | Kiểm tra dependency được resolve |
| CI và local khác kết quả | Version động hoặc lock/config khác nhau | Pin version và tái lập dependency graph |

Không xử lý bằng cách thêm tất cả starter hoặc ép version mọi dependency về cùng một số. Cách đó có thể che lỗi ban đầu và tạo xung đột mới.

## 24. Checklist trước khi commit dependency

Trước khi commit thay đổi Maven hoặc Gradle:

- Đã xác định Spring Boot major/minor và Java version.
- Đã xác định ứng dụng dùng Spring MVC hay WebFlux.
- Đã chọn UI starter hay API-only starter theo nhu cầu.
- Đã chọn Springdoc version theo compatibility matrix.
- Đã pin version cụ thể.
- Không trộn Springdoc legacy 1.x với starter 2.x.
- Không khai báo đồng thời UI và API starter cùng stack nếu không cần.
- Không thêm cả WebMVC và WebFlux starter tùy tiện.
- Không override Swagger Core nếu chưa có lý do.
- Đã kiểm tra dependency tree/runtimeClasspath.
- Đã build và chạy test.
- Đã xác nhận /v3/api-docs trả document hợp lệ.
- Đã xác nhận Swagger UI nếu dự án cần giao diện.
- Đã cập nhật lockfile hoặc parent dependency management theo quy trình.

## 25. Nguyên tắc chọn và quản lý dependency

Khi khai báo Springdoc bằng Maven hoặc Gradle:

1. Chọn artifact dựa trên Spring MVC hoặc Spring WebFlux.
2. Chọn UI starter nếu cần Swagger UI; chọn API starter nếu chỉ cần document endpoint.
3. Đối chiếu Spring Boot major với dòng Springdoc tương thích.
4. Dùng version pin cụ thể và quản lý tập trung.
5. Giữ dependency trong compile/runtime scope phù hợp.
6. Tránh trộn Springdoc 1.x và 2.x hoặc trộn namespace javax/jakarta.
7. Không thêm trùng starter hoặc override Swagger Core tùy tiện.
8. Kiểm tra dependency tree bằng Maven hoặc Gradle.
9. Kiểm tra endpoint JSON/YAML và Swagger UI sau khi khởi động.
10. Chạy contract validation và test trước khi nâng version.

Một dependency declaration đúng phải phản ánh đúng web stack, phiên bản nền tảng và nhu cầu runtime của ứng dụng. Khi version được quản lý tập trung, dependency graph được kiểm tra và endpoint tài liệu được xác minh sau build, Springdoc sẽ trở thành một phần ổn định của quy trình phát triển và phát hành API.

## 26. Tài liệu tham khảo

- Springdoc OpenAPI documentation: https://springdoc.org/
- Springdoc compatibility and migration documentation: https://springdoc.org/#getting-started
- Spring Boot dependency management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Maven dependency mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle dependency management: https://docs.gradle.org/current/userguide/dependency_management.html
- Gradle Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html

