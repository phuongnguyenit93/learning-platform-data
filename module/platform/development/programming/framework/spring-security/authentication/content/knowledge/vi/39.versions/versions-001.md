# Tra cứu API và reference theo đúng phiên bản Spring Security

> **Module:** Spring Security – authentication. **Nhóm:** Phiên bản. Bài học dành cho người học Java 17+, Spring Boot và Spring Security trên Servlet stack (các lưu ý WebFlux được phân biệt riêng). Mục tiêu là biết **đang chạy chính xác phiên bản nào, đọc đúng bộ tài liệu Reference/Javadoc, tìm đúng package/module/signature và kiểm chứng code mẫu với dependency đã resolve**, thay vì sao chép ví dụ từ trang “latest” rồi phát hiện project cũ không biên dịch hoặc hành vi xác thực khác. Tài liệu phản ánh trang chính thức được đối chiếu ngày **06/11/2026**; trạng thái “latest” hoặc patch đang phát hành phải luôn kiểm tra lại khi áp dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Spring Security version**, **Spring Boot version**, **Spring Framework version** và những module Security riêng: `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-oauth2-resource-server`, `spring-security-oauth2-jose`, `spring-security-test`.
2. Xác định phiên bản **được resolve lúc build**, **đóng gói trong artifact** và **đang chạy trên môi trường đích**, ngay cả khi `pom.xml`/`build.gradle` không khai số version ở dependency.
3. Hiểu khác nhau giữa **Reference Documentation**, **API/Javadoc**, **Migration Guide**, **Release Notes** và **Security Advisories**, từ đó chọn nguồn phù hợp câu hỏi.
4. Mở tài liệu cố định theo nhánh phiên bản như `/reference/6.5/` hoặc `/reference/7.0/` thay vì mặc định `/reference/`.
5. Tra Javadoc đúng class và package bằng đường `/reference/<major.minor>/api/java/...`; kiểm tra constructors, methods, `@since`, deprecations, signatures và inherited members.
6. Phân biệt code cho **Servlet** (`HttpSecurity`, `SecurityFilterChain`, `HttpServletRequest`) và **Reactive/WebFlux** (`ServerHttpSecurity`, `SecurityWebFilterChain`, `ServerWebExchange`).
7. Nhận diện sự khác biệt khi đọc ví dụ **Spring Security 6.5** so với **7.x**: passkey/WebAuthn dependencies, MFA APIs, migration và Spring Boot release line.
8. Viết một Java 17 utility độc lập để dựng đường dẫn tài liệu đúng nhánh từ version đã xác định, với đầu ra tái lập.
9. Tạo quy trình kiểm thử compile/behavior, lưu bằng chứng URL + version + commit + dependency graph, không tuyên bố một API hỗ trợ chỉ vì tìm được trong Javadoc “latest”.
10. Đọc security advisory cùng ngữ cảnh version; tránh coi câu trả lời trên forum hoặc một GitHub snippet đã cũ là đặc tả của ứng dụng đang chạy.

## 2. “Đúng phiên bản” nghĩa là đúng phiên bản nào?

Một dự án thường có nhiều nguồn khác nhau nói về version:

```text
                 pom.xml / build.gradle(.kts)
                          |
             parent / dependencyManagement
                 Spring Boot BOM / platform
                          |
                  Resolve dependency graph
                 /          |           \
       spring-security  spring-framework  third-party
       -core/-web/...       libraries       modules
                  |
        runtimeClasspath / testRuntimeClasspath
                  |
            app.jar / container image
                  |
       production deployment image digest
                  |
                Đọc Reference + API của
               phiên bản thực đang chạy
```

Ví dụ cấu hình:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Không thấy chuỗi `6.5.x` hay `7.x` **không có nghĩa project không có version**. Spring Boot BOM/platform sẽ chọn cụ thể một bộ dependencies. Nếu người viết bài tra trên docs “latest” mà không kiểm resolved runtime, có thể đọc một API chưa xuất hiện trong project.

Ngược lại, version ghi ở dependency là **ý định**, không nhất thiết là version được chọn sau khi quản lý BOM, constraints, profile, locking, transitive conflicts, hoặc đóng gói lại.

### 2.1. Năm lớp evidence cần đối chiếu

| Nguồn | Câu hỏi | Khi nào đủ? |
|---|---|---|
| `pom.xml`/`build.gradle` | Project khai điều gì? | Chỉ cho biết cấu hình ban đầu |
| BOM / parent / version catalog | Ai quản lý số version của modules? | Giải thích ý định dependency management |
| Maven dependency tree / Gradle runtimeClasspath | **JAR nào được build tool chọn?** | Đủ để tra API phù hợp build local/CI đó |
| `BOOT-INF/lib` / SBOM / image | JAR nào thật sự được đóng gói? | Đủ để đối chiếu artifact sẽ triển khai |
| Deployment inventory/image digest/runtime diagnostics | Pod/server đang chạy artifact nào? | Cần để trả lời câu hỏi sự cố production |

**Quy tắc:** với lỗi biên dịch, ưu tiên **compileClasspath**; với lỗi lúc chạy, ưu tiên **runtimeClasspath + artifact**; với bug production, phải xác minh **deployed image digest/actual JAR**, không dùng phiên bản trên nhánh Git đang mở.

### 2.2. Spring Security có nhiều module, nhưng chia sẻ release train

Trong một ứng dụng bạn có thể gặp:

```text
org.springframework.security:spring-security-core
org.springframework.security:spring-security-config
org.springframework.security:spring-security-web
org.springframework.security:spring-security-crypto
org.springframework.security:spring-security-test
org.springframework.security:spring-security-oauth2-client
org.springframework.security:spring-security-oauth2-resource-server
org.springframework.security:spring-security-oauth2-jose
```

Một class có thể ở module Web nhưng tài liệu ví dụ dùng Config; một class ở OAuth2 JOSE có thể cần thêm starter. Đừng thấy `spring-security-core:6.5.11` rồi mặc định tất cả modules khác cùng patch nếu dự án có overrides; **liệt kê resolved versions**.

Nếu module versions lệch (ví dụ Config 6.5.x còn Web 6.4.x do override), cần coi đó là **dependency drift** và kiểm compatibility, thay vì chọn tài liệu trộn hai bản. Nâng chỉ một JAR để sửa lỗi compiler hoặc cảnh báo CVE có thể tạo `NoSuchMethodError`/`ClassNotFoundException`/thay đổi behavior.

### 2.3. Version của Spring Boot không phải của Spring Security

- Spring Boot là framework/autoconfiguration/BOM cho ứng dụng.
- Spring Framework cung cấp IoC/MVC/WebFlux, `@Configuration`, transactions, HTTP infrastructure.
- Spring Security cung cấp authentication/authorization/filter chains/OAuth2 support.
- Spring Authorization Server, Spring Session và Spring LDAP là các dự án khác, có vòng đời tài liệu riêng.

Một URL `docs.spring.io/spring-boot/...` không thay Javadoc của `AuthenticationManager`; và Javadoc của Spring Security không mặc định mô tả Spring Boot property `spring.security.oauth2.resourceserver.jwt.issuer-uri` đầy đủ. Hãy ghi rõ **tên sản phẩm và phiên bản** trong câu hỏi.

## 3. Bốn nguồn tài liệu chính: chúng trả lời các câu hỏi khác nhau

| Loại tài liệu | Phạm vi | Dùng khi nào | Không dùng để kết luận |
|---|---|---|---|
| **Spring Security Reference** | Cơ chế, use case, cấu hình Java/Kotlin, flow và kiến trúc | “Cấu hình `SecurityFilterChain` thế nào?”, “JWT/OTT hoạt động ra sao?” | Không hứa mọi snippet tự biên dịch nếu bạn chưa kiểm phiên bản/dependencies |
| **Javadoc/API** | Package, class, interface, constructor/method signature, `@since`, `@deprecated`, Java generics | “Method này tồn tại trong 6.5 không?”, “Return type là gì?” | Không thay business threat model, hướng dẫn deploy hay migration |
| **Migration Guide/Release Notes** | Những thay đổi giữa versions, APIs bị bỏ/deprecate, cấu hình cần chuyển | “Từ 6.x lên 7.x phải đổi gì?” | Không thay dependency graph thực của project |
| **Security Advisories** | Vulnerabilities, affected/fixed versions, prereqs, mitigation, support channels | “Phiên bản này bị CVE nào?” | Không thay test reachability hoặc xác minh image production |

Nguồn thứ năm hữu ích là **source code/tag tương ứng version** để xác minh behavior chi tiết. Nhưng đọc `main` hoặc `master` của repository cho một ứng dụng đang chạy 6.5.x có thể sai vì source đã lên nhánh 7.x. Luôn chọn **release tag/commit đã phát hành** và đối chiếu artifact metadata.

### 3.1. “Reference” khác “API/Javadoc” thế nào?

Reference nói **cách dùng**:

```java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults());
```

Đoạn trên là **snippet** bên trong một bean `SecurityFilterChain`; nó dựa vào `HttpSecurity`, `Customizer`, security configuration và một user store/provider phù hợp.

Javadoc nói **chữ ký**: `HttpSecurity.formLogin(Customizer<FormLoginConfigurer<HttpSecurity>>)` hay những overloads cụ thể theo phiên bản, cấu trúc `AuthenticationEntryPoint.commence(...)` và exceptions. Khi Reference có ví dụ khó hiểu, **Javadoc đúng phiên bản** giúp kiểm tên method/constructor và điều kiện khả dụng.

**Đừng dùng riêng Javadoc để suy ra default behavior của cả Spring Boot app**: bean autoconfiguration, order các filter chains và classpath dependencies cũng quyết định kết quả. Ngược lại, đừng dựa vào ví dụ Reference trang “latest” để phát biểu method có trong patch cũ.

### 3.2. Kết hợp theo thứ tự

1. Đọc đúng **phần Reference** của feature để hiểu flow.
2. Mở Javadoc của các class xuất hiện trong code mẫu.
3. Kiểm `Since`, deprecated, constructor signature, method overload, required modules.
4. Đọc migration guide nếu feature khác phiên bản hoặc compiler cảnh báo deprecated.
5. Đối chiếu dependency graph để xác nhận class nằm trong classpath.
6. Viết unit/integration test cho hành vi thực, đặc biệt authentication/authorization/CSRF/session/token.

## 4. Điều hướng URL tài liệu Spring Security cố định theo nhánh

Trang index chính thức:

- [Spring Security Reference](https://docs.spring.io/spring-security/reference/) – thông thường trỏ tới **bản tài liệu hiện hành**, có thể đổi theo các lần release.
- [Spring Security Reference 6.5](https://docs.spring.io/spring-security/reference/6.5/) – tài liệu nhánh 6.5.
- [Spring Security Reference 7.0](https://docs.spring.io/spring-security/reference/7.0/) – tài liệu nhánh 7.0.
- [Spring Security Reference 7.1](https://docs.spring.io/spring-security/reference/7.1/) – tài liệu nhánh 7.1.

**Snapshot tra cứu 06/11/2026:** trang index liệt kê stable `7.1.2`, `7.0.8` và `6.5.11`, cùng preview/snapshot của các nhánh khác. Đây chỉ là số phát hành quan sát tại thời điểm đọc; **không mặc định là “latest” vào ngày mai** và không tự áp dụng Security 7.1 cho một dự án đang dùng Boot 3.x.

Các URL `/reference/6.5/` và `/reference/7.0/` thường là **theo minor release line**, có thể được cập nhật sang patch cuối của nhánh. Chúng **không tự động ghim xuống từng patch** (ví dụ 6.5.3); do đó khi phân tích một bug rất cụ thể của patch cũ, phải xem release tag/Javadoc artifact đúng patch và release notes/advisory lịch sử.

### 4.1. Các ví dụ URL cố định đã xác minh

| Mục đích | Spring Security 6.5 | Spring Security 7.0 |
|---|---|---|
| Trang nhánh | `https://docs.spring.io/spring-security/reference/6.5/` | `https://docs.spring.io/spring-security/reference/7.0/` |
| Servlet architecture | `https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html` | `https://docs.spring.io/spring-security/reference/7.0/servlet/architecture.html` |
| Servlet authentication architecture | `https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html` | `https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/architecture.html` |
| API `AuthenticationEntryPoint` | `https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html` | `https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/AuthenticationEntryPoint.html` |

Đường API/Javadoc dùng path theo **package** `org.springframework.security.web` chuyển dấu chấm thành dấu `/`, sau cùng là `AuthenticationEntryPoint.html`. Cần biết **fully qualified class name (FQCN)** và artifact chứa class đó để tìm đúng tài liệu.

Một số URL cũ dạng `/spring-security/site/docs/6.5.x/api/...` vẫn tồn tại nhưng có thể hiển thị bản patch không mới nhất của nhánh. Với Java API của 6.5/7.0 nên ưu tiên **versioned Reference API** ở bảng trên, rồi kiểm patch chính xác khi câu hỏi đòi hỏi.

### 4.2. Không đoán URL trang chưa kiểm chứng

Không phải mỗi mục đều có cùng slug/path trong mọi version. Ví dụ tên mục “Password Storage”, “Getting Spring Security”, “Passkeys” hay “Migration” có thể nằm ở các vị trí khác nhau theo nhánh. Cách tìm đúng:

1. Mở `/reference/6.5/` hoặc `/reference/7.0/` theo đúng project.
2. Chọn **Servlet** hay **Reactive**.
3. Dùng sidebar/Search của **bản đã chọn** để mở chủ đề.
4. Kiểm breadcrumb/đường dẫn vẫn chứa `/6.5/` hoặc `/7.0/`.
5. Nếu link trả 404, quay về sidebar bản đó, **không** lặng lẽ chuyển sang `/reference/` latest.
6. Ghi canonical URL thật vừa mở vào ticket/PR/README, tránh trích một route đoán ra.

### 4.3. Trang “latest” và kênh preview/snapshot

Hệ thống tài liệu có thể cung cấp **Stable**, **Preview/RC** và **Snapshot**. Một API nằm trong SNAPSHOT/RC **không chắc đã được đưa vào bản stable** tương ứng hoặc có cùng signature. Nếu đang học feature vừa thông báo trên blog, cần đọc tag/điểm phát hành:

```text
Blog/issue nói feature X
        |
        +-- có trong 7.2.0-SNAPSHOT?
        +-- đã phát hành ở 7.1.x stable chưa?
        +-- module nào cung cấp?
        +-- có cần Java/Boot/Framework baseline mới?
        +-- test trên binary nào?
```

**Quy tắc:** giữ cùng một **release channel** giữa docs, artifact và tests. Không lấy code SNAPSHOT chạy trên JAR stable rồi tự kết luận Spring Security thiếu API.

## 5. Javadoc đúng package, module, class và patch

Giả sử muốn kiểm `AuthenticationEntryPoint.commence`. Trong Spring Security 6.5, class:

```text
FQCN    : org.springframework.security.web.AuthenticationEntryPoint
Artifact: org.springframework.security:spring-security-web
API URL : https://docs.spring.io/spring-security/reference/6.5/api/java/
          org/springframework/security/web/AuthenticationEntryPoint.html
```

Javadoc cho biết method:

```java
void commence(
    HttpServletRequest request,
    HttpServletResponse response,
    AuthenticationException authException
) throws IOException, ServletException;
```

Ở đây `HttpServletRequest` và `ServletException` thuộc **jakarta.servlet** trong Spring Security 6.x/7.x (khác imports `javax.servlet` của nhiều dự án Spring Security 5.x). Chỉ nhìn class name `AuthenticationEntryPoint` chưa đủ nếu package/import hoặc API baseline sai.

### 5.1. Trình tự tìm một class chính xác

1. Xác định **FQCN**: nhờ IDE Navigate Class, import trong Java hoặc source/reference.
2. Xác định **module**: ví dụ `AuthenticationEntryPoint` ở `spring-security-web`; `AuthenticationManager` ở `spring-security-core`; `HttpSecurity` ở `spring-security-config`.
3. Xác định **resolved version** của module đó.
4. Mở API nhánh đúng version; tìm package/class.
5. Kiểm **Method Summary**, **Method Details**, **Constructor Summary**, generic types, visibility, exceptions và `@since`.
6. Kiểm method có **inherited** từ parent/interface hay chỉ xuất hiện ở bản mới.
7. Kiểm **Deprecated** và Javadoc đề xuất thay thế; không xóa warnings bằng cách hạ dependency.
8. Nếu API nằm trong artifact khác, thêm dependency hợp lệ và **đồng bộ release train**; không lấy package từ blog rồi thêm JAR ngẫu nhiên.

### 5.2. Phân biệt class trùng ý nghĩa nhưng khác stack

| Servlet | Reactive/WebFlux | Điều cần đối chiếu |
|---|---|---|
| `HttpSecurity` | `ServerHttpSecurity` | DSL và security filters khác nhau |
| `SecurityFilterChain` | `SecurityWebFilterChain` | Servlet Filter vs WebFilter |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` | Servlet response vs `ServerWebExchange` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` | Đồng bộ vs reactive |
| `SecurityContextHolder` | `ReactiveSecurityContextHolder` | ThreadLocal vs Reactor Context |
| `JwtDecoder` | `ReactiveJwtDecoder` | Cách decode có signature/call contract khác |
| `@EnableWebSecurity` | `@EnableWebFluxSecurity` | Cấu hình hoàn toàn khác |

**Không copy Java DSL WebFlux vào ứng dụng Servlet**, dù cả hai dùng tên `authorizeExchange`/`authorizeHttpRequests` nghe giống nhau. Với project dùng Spring MVC, ưu tiên `/servlet/...`; với ứng dụng WebFlux chọn `/reactive/...`. Khi hệ thống có cả hai starters, cần xác định stack thực đã được Spring Boot chọn và filter chains hoạt động.

### 5.3. Tìm method mới hoặc removed

Khi IDE báo `Cannot resolve method`, hãy hỏi:

- Method có nằm ở bản **latest** nhưng không có trong nhánh project?
- Method là **Kotlin extension** chứ không phải Java API?
- Method thuộc **Spring Boot DSL**/project khác?
- Method nằm trong artifact chưa có trên compile classpath?
- Import/overload/generics khác do Java baseline?
- API bị deprecated rồi removed ở major mới?
- Ví dụ viết cho WebFlux, test classpath hoặc XML config chứ không phải Servlet Java DSL?

Chọn **Javadoc đúng version** và xem type parameters trước khi ép compiler bằng casting không an toàn.

### 5.4. Javadoc patch-level khi cần độ chính xác tuyệt đối

Trang Reference `/6.5/api/java` phản ánh nhánh và có thể được cập nhật tới patch hiện hành. Nếu đang điều tra `6.5.3` trên máy sản xuất, còn docs nhánh hiện hiển thị `6.5.11`, một method sửa từ 6.5.4 sẽ khiến bạn hiểu sai.

Cách xử lý:

- Đọc resolved artifact POM/manifest `Implementation-Version` hoặc build info để biết patch thật.
- Tìm **javadoc JAR** đúng `group:artifact:version` trên artifact repository/Maven Central hoặc phiên bản tại `javadoc.io` **nếu artifact có xuất bản Javadoc**.
- Nếu không có Javadoc của patch đó, xem source JAR và release tag tương ứng; kiểm signature bytecode bằng `javap`.
- Ghi trong tài liệu nội bộ: “Test trên Spring Security 6.5.3; API online /6.5 hiện có thể là patch mới hơn”.
- Không dùng `-SNAPSHOT` làm chuẩn cho việc kết luận API xuất hiện ở bản đã release.

**Không giả định Javadoc.io có mọi bản patch:** một số phiên bản có thể chưa tải được Javadoc lên dịch vụ đó. Khi không có, dùng source JAR/release artifact làm bằng chứng.

## 6. Lấy version đúng trong Gradle

Sử dụng Gradle Wrapper của repository để tránh máy phát triển chạy một bản build tool khác CI.

### 6.1. Đọc dependency graphs

```bash
./gradlew --version
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
```

`:app` chỉ là module minh họa. Nếu dự án single-module, bỏ `:app:`; nếu module tên `:api` thì dùng `:api:`. Các lệnh chỉ đọc graph/resolution; không tự sửa dependency.

- `compileClasspath`: có class/method/annotation nào khả dụng khi biên dịch?
- `runtimeClasspath`: JAR nào ứng dụng sẽ tải khi chạy?
- `testRuntimeClasspath`: có thêm `spring-security-test`, Mockito, Testcontainers và phiên bản riêng cho tests?
- `dependencies` hiển thị chọn phiên bản do conflict/constraint với dấu `->` và các ghi chú resolution.

### 6.2. Tìm module bằng dependencyInsight

```bash
./gradlew :app:dependencyInsight \
    --dependency spring-security-web \
    --configuration runtimeClasspath

./gradlew :app:dependencyInsight \
    --dependency spring-security-config \
    --configuration compileClasspath

./gradlew :app:dependencyInsight \
    --dependency spring-security-oauth2-jose \
    --configuration runtimeClasspath

./gradlew :app:dependencyInsight \
    --dependency spring-security-test \
    --configuration testRuntimeClasspath
```

Lệnh giúp trả lời **vì sao version này được chọn**: Spring Boot BOM, direct dependency, transitive graph, constraints, forced version, resolution strategy hoặc lockfile. Nếu một dependency không xuất hiện, kiểm module/project path và configuration trước khi tự thêm bản mới.

### 6.3. Lý do có BOM nhưng vẫn sai version

Một số cấu hình có thể override BOM:

```groovy
// Minh họa cơ chế, KHÔNG khuyến nghị tự override release train.
configurations.all {
    resolutionStrategy.force(
        'org.springframework.security:spring-security-web:6.5.3'
    )
}
```

Trên CI, `dependencyInsight` sẽ giúp phát hiện `force` và bạn biết không nên đọc Javadoc 6.5.11 như thể runtime đang là 6.5.11. Đừng copy đoạn `force` trên vào production; lựa chọn version cần tương thích tất cả Spring Security modules, Boot và Framework.

Ngoài `force`, kiểm:

- `gradle/libs.versions.toml` version catalogs;
- `platform("org.springframework.boot:spring-boot-dependencies:...")`;
- Gradle dependency locking và lockfiles;
- `resolutionStrategy.eachDependency`/`strictly`;
- plugin `io.spring.dependency-management` nếu được dùng;
- multi-project build và composite build;
- dynamic versions `6.+`, `latest.release` hoặc snapshot repositories.

Sau thay BOM, **đọc lại graph**. Đừng tin chỉ vì dòng `plugins { id 'org.springframework.boot' version '...' }` đã thay.

### 6.4. Lấy JAR đã đóng gói

Executable Spring Boot JAR thường chứa dependencies trong `BOOT-INF/lib`. Với artifact đã build thực:

```bash
jar tf path/to/actual-app.jar
```

Tìm các entry `BOOT-INF/lib/spring-security-*.jar`. `path/to/actual-app.jar` là đường minh họa, phải thay bằng artifact thực đã tạo. Đối với container/Kubernetes, liên kết artifact đó tới image digest triển khai; `jar tf` trên laptop không bảo đảm production chạy đúng binary này.

## 7. Lấy version đúng trong Maven

Một project dùng `spring-boot-starter-parent` hoặc `spring-boot-dependencies` trong `dependencyManagement` có thể bỏ phiên bản ở từng dependency:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
</dependencies>
```

Đây là XML snippet, không phải `pom.xml` độc lập; parent/BOM của project phải cung cấp các versions.

### 7.1. Commands

```bash
./mvnw -version
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework.security:spring-security-web
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

Windows dùng `mvnw.cmd`. Nếu Maven không hỗ trợ filtering như mong đợi, dùng `dependency:tree` không includes rồi kiểm chính xác artifact/version. Với multi-module, giới hạn `-pl` và `-am` đúng service và profiles.

Đọc `effective-pom.xml` để biết parent/BOM properties/overrides; đọc dependency tree để thấy **resolved dependencies** chứ không chỉ version được quản lý nhưng thực ra không xuất hiện trên classpath.

### 7.2. Khi nào đọc runtimeScope và testScope?

Maven có scopes như `compile`, `provided`, `runtime`, `test`. Một class trong `spring-security-test` chỉ có ở test classpath không thể được dùng ở production main source nếu dependency chỉ là test scope. Ngược lại một lỗi trong Boot app chạy trên container có thể liên quan provided servlet API hoặc transitives mà test đã khác.

Dùng cùng Maven profiles/properties như CI và production. Với projects dùng Java toolchains, xác minh `maven-compiler-plugin`/`maven-toolchains-plugin` để không nhầm compile errors do JDK.

### 7.3. Maven property override không phải cách đầu tiên

Spring Security documentation có mô tả cách override version qua property như `spring-security.version` trong Spring Boot-managed project. Nhưng không nên **override chỉ để biên dịch một ví dụ trên web**; trước hết xác minh release line tương thích và các modules. Các bản security fixes có thể đòi cập nhật Spring Framework hoặc Boot.

## 8. Ví dụ so sánh API theo phiên bản: 6.5 và 7.x

### 8.1. WebAuthn/passkey: khác nhau cả dependency

**Spring Security 6.5** Reference ở `/reference/6.5/servlet/authentication/passkeys.html` hướng dẫn dùng `spring-security-web` cùng `com.webauthn4j:webauthn4j-core`.

```groovy
// Trích đoạn Gradle cho nhánh 6.5, versions phải theo BOM/policy.
dependencies {
    implementation 'org.springframework.security:spring-security-web'
    implementation 'com.webauthn4j:webauthn4j-core'
}
```

**Lưu ý:** nếu WebAuthn4J không được BOM quản lý trong build của bạn, phải chỉ định **phiên bản được tài liệu 6.5 hướng dẫn/tương thích** (trang 6.5 đã minh họa `0.29.7.RELEASE`), không để dependency thiếu version rồi chờ build tự đoán. Tránh hardcode vào production mà chưa kiểm release notes của nhánh thực tế.

**Spring Security 7.x** Reference mới ở `/reference/servlet/authentication/passkeys.html` minh họa artifact `org.springframework.security:spring-security-webauthn` riêng.

```groovy
// Trích đoạn Gradle của nhánh 7.x, không copy vào ứng dụng 6.5.
dependencies {
    implementation 'org.springframework.security:spring-security-webauthn'
}
```

Vì thế khi gặp câu “`spring-security-webauthn` không tìm thấy trong 6.5”, đừng chỉ thêm repository rồi thử lại; **đọc đúng docs phiên bản** và module artifacts đã được phát hành. Các class/interface hỗ trợ passkey có thể đổi packaging/sự tích hợp giữa hai nhánh.

**Điểm phương pháp:** phiên bản Reference xác định danh sách dependencies tối thiểu để **bật một feature**; Javadoc cho bạn API class; Gradle/Maven graph xác nhận binary thực.

### 8.2. MFA: tính năng có thể thuộc nhánh mới

Trang MFA Reference của Spring Security hiện hành mô tả khái niệm `FactorGrantedAuthority` và các authorization managers cho nhiều yếu tố. Đừng nhìn code này rồi mặc định nó chạy với **Spring Security 6.5**.

Nếu một snippet như:

```java
@EnableMultiFactorAuthentication
class SecurityConfiguration {
    // ... security configuration ...
}
```

được lấy từ tài liệu 7.x, trước khi dùng phải:

- Mở **docs nhánh 7.x** cho đầy đủ import, annotations/options.
- Kiểm Javadoc đúng version của `EnableMultiFactorAuthentication` và `FactorGrantedAuthority`.
- Đối chiếu Boot/Framework/Java baseline và artifact dependencies.
- Xác minh use case cần yếu tố gì, không chỉ “bật” annotation rồi nghĩ MFA luôn đã đủ.
- Với dự án 6.x, thiết kế policy phù hợp phiên bản hoặc plan migration, không ép một class 7.x vào classpath 6.x.

Một **authentication mechanism** và **một MFA policy** không phải thứ giống nhau: cùng project bật `formLogin` và `oneTimeTokenLogin` có thể cung cấp **hai cách login thay thế**, không tự tạo yêu cầu cả hai.

### 8.3. JWT Resource Server: giữ đúng package và Boot properties

Reference cho 6.5 có `/reference/6.5/servlet/oauth2/resource-server/jwt.html`. Một đoạn Spring Security Java DSL:

```java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()));
```

Đây là **snippet trong `SecurityFilterChain`**, không tự chạy bằng `javac`. Các class liên quan thuộc:

- `org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider` – resource-server authentication.
- `org.springframework.security.oauth2.jwt.JwtDecoder` – JWT decode/verify thuộc OAuth2 JOSE.
- `org.springframework.security.config.annotation.web.builders.HttpSecurity` – Servlet configuration.
- `org.springframework.security.web.SecurityFilterChain` – HTTP filter chain.

Spring Boot property:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
          audiences: https://api.example.org
```

Kiểm **Spring Boot Reference** cùng nhánh để biết property đã hỗ trợ tại bản Boot của bạn; kiểm Spring Security Reference/Javadoc để biết decoder/validator tương ứng. `issuer-uri` nhằm xác minh issuer, `audiences` xác minh audience; không chỉ nhìn thấy `JwtDecoder` trong Javadoc rồi kết luận app đã kiểm tra audience. Cần test token sai `iss`/`aud`/`exp`.

### 8.4. Method Security và DSL

Đối với Servlet:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

API annotation có mặt không có nghĩa mọi method `@PreAuthorize` đã được áp dụng: class phải là Spring bean/proxy phù hợp, annotation được bật và invocation không vượt qua AOP interceptor. Trang Reference phần Method Security giải thích semantics; Javadoc chỉ mô tả annotation/properties.

Không trộn `authorizeRequests`/`antMatchers` từ những bài Spring Security 5.x cũ với `authorizeHttpRequests`/`requestMatchers` của phiên bản 6/7. API bị deprecated/removed cần được kiểm bằng Javadoc và Migration Guide của **đúng nhánh** trước khi thay tương đương một cách cơ học.

## 9. Java 17 độc lập: dựng đường tài liệu đúng release line

Mã dưới đây **biên dịch/chạy với Java 17+**, không cần Spring, Gradle hay Maven. Nó minh họa cách **chọn tài liệu 6.5 hoặc 7.0** sau khi đã biết exact version. Chương trình không tự truy cập Internet/đọc project dependencies, không xác minh URL còn tồn tại và không quyết định “bản mới nhất”.

**Vì sao có ích?** Khi viết tài liệu nội bộ hoặc kiểm tra PR, bạn có thể nhận raw version như `6.5.11` từ dependency graph, phân tích thành `major.minor`, và dựng link Reference/API **cùng nhánh** thay vì chèn `/reference/` mặc định.

Lưu file `SpringSecurityDocsLocatorDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SpringSecurityDocsLocatorDemo {

    record Version(int major, int minor, int patch) {

        private static final Pattern NUMERIC =
            Pattern.compile("^(\\d+)\\.(\\d+)\\.(\\d+)$");

        static Version parse(String value) {
            Matcher m = NUMERIC.matcher(value);
            if (!m.matches()) {
                throw new IllegalArgumentException(
                    "Expected numeric major.minor.patch");
            }
            return new Version(
                Integer.parseInt(m.group(1)),
                Integer.parseInt(m.group(2)),
                Integer.parseInt(m.group(3))
            );
        }

        String line() {
            return major + "." + minor;
        }

        String root() {
            return "https://docs.spring.io/spring-security/"
                + "reference/" + line() + "/";
        }

        String servletArchitecture() {
            return root() + "servlet/authentication/architecture.html";
        }

        String api(String fullyQualifiedName) {
            if (!fullyQualifiedName.matches(
                    "[A-Za-z_$][\\w$]*(\\.[A-Za-z_$][\\w$]*)+")) {
                throw new IllegalArgumentException("Invalid Java class name");
            }
            return root() + "api/java/"
                + fullyQualifiedName.replace('.', '/') + ".html";
        }
    }

    public static void main(String[] args) {
        Version six = Version.parse("6.5.11");
        Version seven = Version.parse("7.0.8");

        System.out.println("6.5 docs: " + six.root());
        System.out.println("6.5 architecture: "
            + six.servletArchitecture());
        System.out.println("6.5 API: " + six.api(
            "org.springframework.security.web.AuthenticationEntryPoint"));

        System.out.println("7.0 docs: " + seven.root());
        System.out.println("7.0 API: " + seven.api(
            "org.springframework.security.web.AuthenticationEntryPoint"));

        System.out.println("Same line? "
            + six.line().equals(seven.line()));
    }
}
```

Chạy:

```bash
javac SpringSecurityDocsLocatorDemo.java
java SpringSecurityDocsLocatorDemo
```

Stdout **chính xác**:

```text
6.5 docs: https://docs.spring.io/spring-security/reference/6.5/
6.5 architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
6.5 API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html
7.0 docs: https://docs.spring.io/spring-security/reference/7.0/
7.0 API: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/AuthenticationEntryPoint.html
Same line? false
```

### 9.1. Giới hạn có chủ ý

- Utility chỉ hỗ trợ **3 thành phần số** `major.minor.patch`, không hiểu `7.2.0-RC1`, `6.5.12-SNAPSHOT` hoặc phiên bản Enterprise có qualifier/bốn thành phần.
- `root()` trỏ tới trang **release line**, không bảo đảm nội dung đúng **patch historical**; muốn chính xác đến patch phải xem artifact/source tag/Javadoc version.
- Một class có thể bị removed, renamed hoặc chuyển module: URL được dựng không có nghĩa trang thực tồn tại. Phải mở link và kiểm.
- Các link docs chỉ là **tài liệu**, không nói gì về dependencies thực đang chạy. Đọc `dependencyInsight`/`dependency:tree` trước.
- Không sử dụng link builder làm security scanner hoặc để suy affected CVE; một vulnerability cần full advisory và bối cảnh configuration/runtime.
- Đối với reactive stack, path chủ đề sẽ nằm dưới `reactive/...`; không hardcode Servlet architecture vào ứng dụng WebFlux.

## 10. Mã Spring có nằm đúng bản nhưng vẫn không biên dịch: cần kiểm gì?

Một ví dụ Reference có thể chỉ là **trích đoạn** thiếu imports, bean, dependency hoặc cấu hình. Đây là điều bình thường với docs hướng dẫn khái niệm. Phải phân biệt:

**A. Không tìm thấy symbol ở compile time**

```text
cannot find symbol
  symbol: method webAuthn(...)
```

Kiểm method đã có trong version chưa, module `spring-security-config`, dependency WebAuthn, DSL Java vs Kotlin, overload/import và yêu cầu Spring Framework/Java.

**B. Có symbol nhưng runtime ClassNotFoundException**

```text
java.lang.NoClassDefFoundError:
  org/springframework/security/.../SomeClass
```

Kiểm `runtimeClasspath`, packaging, containers, test vs production scopes, transitive dependencies/exclusions và module version drift.

**C. Có class nhưng runtime NoSuchMethodError**

```text
java.lang.NoSuchMethodError:
  ...someMethod(...)...
```

Thường liên quan **binary version mismatch**: code biên dịch với API mới nhưng runtime tải JAR cũ. Đọc `compileClasspath` vs `runtimeClasspath`, `BOOT-INF/lib` và classloader resolution. Không sửa bằng cách thêm random version override.

**D. Code chạy nhưng behavior không giống docs**

Ví dụ `formLogin` redirect 302 khác REST bearer 401, `SecurityContext` không persist qua request hoặc `@PreAuthorize` không chặn. Cần xem cấu hình filters, Spring Security 6 explicit context save, `@EnableMethodSecurity`, CSRF và chain matching. Javadoc đúng version giúp biết API nhưng **integration tests** mới chứng minh behavior.

### 10.1. “Cannot resolve symbol” không phải lúc nào do version

- Gõ sai package hoặc chọn class Servlet thay vì Reactive.
- IDE indexing/cache stale hoặc chưa refresh Gradle/Maven.
- Thiếu module `spring-security-oauth2-jose` khi gọi `JwtDecoder`.
- Test code bị đặt trong `src/main/java` trong khi `spring-security-test` chỉ thuộc test scope.
- Dùng Java 8 để biên dịch code Java 17 hoặc Jakarta API trên project Spring 5.
- Copy từ XML/Kotlin DSL sang Java nhưng chưa đổi syntax.
- Method có generic type yêu cầu import khác hoặc `Customizer.withDefaults()` sai context.
- Boot autoconfiguration khác vì đã khai custom `SecurityFilterChain`.
- API mới bị document ở `7.1-SNAPSHOT` nhưng project là `7.0` stable.

Trước khi thêm dependency, **xác định FQCN + artifact + version + stack + sample language**.

## 11. Đối chiếu source tag và code history khi docs chưa đủ

Khi cần xác minh behavior của một phiên bản **cụ thể**, có thể làm theo trình tự:

1. Từ `dependencyInsight`/`dependency:tree`, lấy exact `org.springframework.security:artifact:version`.
2. Mở release/tag tương ứng ở repository nguồn hoặc tải `-sources.jar` cùng version từ artifact repository.
3. Xem implementation của class cần tra (ví dụ `ExceptionTranslationFilter`, `JwtAuthenticationProvider`, `DaoAuthenticationProvider`).
4. Xem test đi kèm **cùng tag** để hiểu behavior/hợp đồng nội bộ; không lấy test ở `main`.
5. So Javadoc đúng patch và migration notes; kiểm những thay đổi từ patch A sang patch B.
6. Nếu có CVE, đọc security advisory của nhà phát hành để tránh phân tích dựa vào riêng một commit.
7. Dùng unit/integration test của chính ứng dụng để tái hiện, không chỉ kể lại logic đọc từ source.

**Cảnh giác:** `main` có thể đã chứa fix chưa phát hành; branch maintenance có thể chứa backport khác. Kiểm commit/tag từ release artifact, không suy từ số dòng source.

### 11.1. Dùng javap khi cần signature thực

Nếu đã có JAR đúng version, công cụ JDK `javap` có thể xem public members:

```bash
javap -classpath path/to/spring-security-web-6.5.11.jar \
    org.springframework.security.web.AuthenticationEntryPoint
```

Lệnh là ví dụ, phải dùng đường dẫn JAR thực. Với Java 17 toolchain, `javap` cho biết signature trong **binary cụ thể**. Đây là bằng chứng mạnh khi docs website đang hiển thị patch mới hơn hoặc class bị thiếu. Dù vậy javap không mô tả đầy đủ semantics/điều kiện security; kết hợp Reference/tests/advisory.

## 12. Migration: từ nhánh 6.x sang 7.x

Đường tham khảo chính thức:

- [Preparing for 7.0 (Spring Security 6.5)](https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html)
- [Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/)

Tài liệu migration nói **6.5 là nhánh cuối của 6.x** và khuyên chuẩn bị thay đổi ngay trong ứng dụng 6.5 trước khi chuyển 7.0. Tài liệu cũng hướng dẫn cập nhật Spring Boot 4.0 phù hợp trước khi hoàn tất chuyển Spring Security 7.

Không tự quyết định chỉ bằng cách sửa:

```groovy
// Ví dụ sai nếu hệ thống vẫn dùng Spring Boot 3/Security 6 train:
implementation 'org.springframework.security:spring-security-config:7.0.8'
```

Đoạn sai trên được đưa để cảnh báo. **Một module 7.0.x riêng** không chứng minh tương thích với các module 6.x/Framework/Boot cũ, đặc biệt ở API, filters, JSON serialization và WebAuthn.

### 12.1. Quy trình migration theo tài liệu, không theo phỏng đoán

```text
1. Inventory Spring Boot, Security, Framework và JDK versions.
2. Đọc 6.5 preparation guide + versioned Javadoc của code đang dùng.
3. Thực hiện deprecation cleanup và migration flags theo guidance.
4. Chọn Spring Boot 4.x + Security 7.x supported release train.
5. Đọc 7.x Reference/Javadoc và migration guide của target.
6. Update dependency management/BOM và tất cả related modules.
7. Build, compile, run unit/integration/security tests.
8. Test authentication, authorization, CSRF, session,
   JWT, OAuth2/OIDC, passkeys/WebAuthn/MFA, logout/revocation.
9. Inspect resolved versions, image digest và canary behavior.
10. Ghi decisions, links, versions và rollback plan.
```

Không xem release major là chỉ có syntax: có thể có changes về Servlet/Jakarta, Json/Jackson versions, WebAuthn architecture và method security defaults. Mọi thay đổi cần đối chiếu docs target và production integration tests.

### 12.2. Đừng nhầm docs migration với security fix

Một security advisory có thể yêu cầu **một patch cụ thể** trong 6.5/7.0 và có điều kiện hỗ trợ OSS/Enterprise. Đừng dùng migration guide 7.0 làm nguồn duy nhất cho câu hỏi CVE: đọc [Spring Security Advisories](https://spring.io/security/) để lấy affected/fixed ranges và kênh phát hành; sau đó chọn đường nâng cấp tương thích.

Bản 7.x mới hơn **không có nghĩa tự động đã vá mọi CVE** nếu chưa kiểm ngày/điều kiện; patch mới phát hành có thể có security note bổ sung. “Not affected” cũng phải dựa trên exact runtime and configuration.

## 13. Thực hành tra cứu: bốn tình huống điển hình

### Tình huống A – Hỏi AuthenticationEntryPoint thuộc module nào

**Bối cảnh:** project Spring Security 6.5; cần tùy biến 401/redirect.

Thực hiện:

1. Gradle/Maven: xác nhận `spring-security-web` đã resolve đúng 6.5 patch.
2. Mở [Javadoc 6.5 AuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html).
3. Đọc `commence(HttpServletRequest,HttpServletResponse,AuthenticationException)`, exceptions và implementations.
4. Mở [Servlet Authentication Architecture 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html) để hiểu vị trí EntryPoint trong flow.
5. Test anonymous tới endpoint: browser form trả redirect theo policy; Basic/Bearer có `WWW-Authenticate` đúng scheme.
6. Phân biệt `AccessDeniedHandler` 403 cho user đã xác thực thiếu quyền; EntryPoint không phải authorization engine.

### Tình huống B – Muốn dùng passkeys trên project 6.5

1. Xác nhận Spring Security 6.5 patch/build JDK/Boot.
2. Mở [Spring Security 6.5 Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html).
3. Đọc dependencies WebAuthn4J, repositories và `HttpSecurity.webAuthn`.
4. Mở Javadoc của classes/DSL sử dụng để xác nhận methods.
5. Test registration/authentication với signed assertions, expected origin/RP ID, UP/UV/challenge/session binding.
6. Nếu thấy `spring-security-webauthn` trong trang latest, kiểm đó là nhánh 7.x, không thêm vào 6.5 mà thiếu xác minh.

### Tình huống C – Kiểm thử JWT resource server

1. Kiểm `spring-security-oauth2-resource-server` và `spring-security-oauth2-jose` ở runtime.
2. Mở [JWT Resource Server 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html).
3. Kiểm `JwtDecoder` và `JwtAuthenticationProvider` bằng Javadoc đúng branch.
4. Kiểm Boot properties `issuer-uri`, `jwk-set-uri`, `audiences` trong Boot Reference.
5. Với unit authorization test, `spring-security-test` `jwt()` có thể inject principal giả; **không chứng minh chữ ký JWT đã verify**.
6. Với integration, gửi JWT có chữ ký thật vào `Authorization: Bearer ...` để kiểm invalid signature, issuer, audience, expiry, scope và HTTP 401/403.

### Tình huống D – Gặp code MFA mới trong bài blog

1. Xác định ngày/blog nói về Security version nào.
2. Mở docs mục MFA **trong nhánh** của feature, kiểm `FactorGrantedAuthority` có trong API cụ thể của project không.
3. Kiểm annotations/authorization managers/imports ở Javadoc target và module dependencies.
4. Nếu code dành cho 7.x nhưng app ở 6.5, đọc migration để quyết định nâng cấp hoặc giữ policy custom tương thích.
5. Không tự gán factor authorities từ user request/session flag, vì security model phải kiểm chứng những yếu tố thật.
6. Test thiếu factor/step-up/recovery, không chỉ happy path sau `@WithMockUser`.

## 14. Đọc đúng tài liệu để đánh giá hành vi bảo mật

Trong Spring Security, **chữ ký API đúng** chưa đủ để chứng minh bảo mật. Một cấu hình `authorizeHttpRequests` có thể compile nhưng route private vẫn bị lộ do matcher order. Một `JwtDecoder` có thể tồn tại trong Javadoc nhưng bean production không kiểm `aud`. Một `@PreAuthorize` có thể compile nhưng method security chưa được bật.

Luôn kiểm cả ba lớp:

| Lớp | Câu hỏi | Bằng chứng |
|---|---|---|
| **API/binary** | Class/method thực có trong phiên bản này không? | Javadoc đúng version, `javap`, compiled tests |
| **Cấu hình/flow** | Spring Security có thật sự kích hoạt cơ chế đúng route không? | Reference đúng version, filter chain, integration tests |
| **Chính sách bảo mật** | Bằng chứng và quyền được kiểm soát đúng không? | Negative tests, threat model, account/tenant policy, advisories |

### 14.1. Test phân biệt mock và credential thật

`@WithMockUser`, `user()` hoặc `jwt()` của Spring Security Test có thể tạo sẵn Authentication giả để kiểm **authorization**, không cần password/JWT signature đã được chứng minh. Test dùng những fixtures đó rất hữu ích, nhưng **không phải** bằng chứng credential verifier an toàn.

Muốn xác minh authentication thực:

- `httpBasic()`/`formLogin()` gửi credential qua real `SecurityFilterChain`, `AuthenticationManager`, `UserDetailsService` và `PasswordEncoder` (không bị mock luôn success).
- Với JWT, gửi signed token thực và dùng real decoder/validators, không chỉ `jwt()` fixture.
- Với WebAuthn, dùng virtual/hardware authenticator hoặc test signed assertions chạy real verifier, không chỉ principal giả.
- Với OTT, kiểm token TTL, consume một lần, session lifecycle, CSRF và concurrency ở real token store.

Nội dung Reference/Javadoc là **hướng dẫn kỹ thuật**; tests trên version đã resolve là bằng chứng behavior của ứng dụng.

### 14.2. Tránh lẫn HTTP semantics giữa versions và stacks

Với Servlet browser form login, client chưa xác thực có thể nhận `302 /login`; với Bearer Resource Server nhận `401 WWW-Authenticate: Bearer`; người đã xác thực nhưng thiếu role thường nhận `403`. Đọc mục authentication, authorization, exception handling của **đúng stack/version**, không suy từ một response của app sang mọi giao thức.

## 15. Lưu trữ dẫn chứng trong ticket, PR và nội bộ

Một ghi chú kỹ thuật tốt cho câu hỏi “Method này có chạy ở project không?” nên bao gồm:

```text
Project/service  : account-api
Git commit       : <commit SHA from repository>
Spring Boot      : <resolved version>
Spring Security  : <resolved group:artifact:version per module>
Spring Framework : <resolved version>
JDK              : Java 17 / 21 (actual toolchain)
Source           : src/main/java/.../SecurityConfig.java
Docs reference   : https://docs.spring.io/spring-security/reference/6.5/...
Docs API         : https://docs.spring.io/spring-security/reference/6.5/api/java/...
Docs release line: 6.5 (may move to latest patch of branch)
Actual artifact  : build ID / SHA / container digest
Behavior check   : test name + result + timestamp
Caveat           : Javadoc branch vs runtime exact patch
```

Đây là **mẫu dữ liệu** để người học điền, không phải bằng chứng của một service thật. Ghi URL, version, ngày kiểm, test outcomes; không ghi production passwords, OAuth tokens, private keys hoặc cookie trong ticket.

### 15.1. Version pinning khi chia sẻ link trong team

Không gửi trơ:

```text
https://docs.spring.io/spring-security/reference/
```

khi review PR cho một dự án Spring Security 6.5. Hãy gửi:

```text
https://docs.spring.io/spring-security/reference/6.5/
https://docs.spring.io/spring-security/reference/6.5/api/java/
    org/springframework/security/web/AuthenticationEntryPoint.html
```

Đường API ở trên bị ngắt dòng **chỉ để trình bày trong tài liệu**; khi mở phải ghép liền URL thành một dòng. Như vậy người review biết lời giải thích đang dựa trên nhánh 6.5 thay vì docs hiện hành 7.1.

### 15.2. Khi không có trang versioned cho mục cần tìm

- Dùng index của nhánh đó và sidebar/search.
- Xem source tag/release notes.
- Dùng Javadoc của binary đó từ artifact repository; `javap` khi cần.
- Không “thay bằng latest” mà không đánh dấu sự khác biệt.
- Nếu library ngoài Spring (Nimbus JOSE, WebAuthn4J, Spring Authorization Server), tìm **tài liệu riêng** của thư viện đó ở version thật.
- Trong trường hợp docs nội dung đã đổi sau patch, ghi snapshot/ngày và dùng tests để tái hiện.

## 16. Ma trận kiểm tra tài liệu và version drift

| Ca kiểm thử tra cứu | Bằng chứng cần thu | Kỳ vọng |
|---|---|---|
| Project Boot 3 chưa rõ Security patch | `dependencyInsight`/`dependency:tree` | Xác định `group:artifact:version` chính xác |
| Đọc trang `/reference/` latest khi project 6.5 | URL hiển thị latest và 6.5 | Không copy API 7.x vào 6.5 |
| Method có trong 7.1 nhưng không thấy ở 6.5 | Javadoc hai nhánh | Báo đúng introduced/removed, tìm migration |
| URL Javadoc 6.5 class không tồn tại | FQCN và module | Kiểm package/artifact, không đoán version |
| Java compiler báo method missing | compileClasspath + Javadoc API | Phân biệt code sai vs version cũ |
| Runtime `NoSuchMethodError` | Compile/runtime JAR và artifact | Phát hiện version drift/classloader |
| Snippet dùng `javax.servlet` trong app Boot 3 | Imports/Jakarta API | Phân biệt Spring Security 5.x vs 6.x |
| Đọc WebFlux DSL cho app MVC | Application type + Reference path | Chọn Servlet API đúng |
| Copy WebAuthn dependency `spring-security-webauthn` vào 6.5 | Versioned Passkeys Reference | Đọc đúng WebAuthn4J dependency của 6.5 |
| Dùng MFA 7.x annotation ở 6.x | API/Reference + migration | Không hứa compile trên 6.x |
| JWT tests chỉ dùng `jwt()` | Test setup + real decoder test | Không tuyên bố signature đã verify |
| Cảnh báo CVE trong scanner | Exact runtime + Spring advisory | Ghi affected version/config/mitigation |
| BOM nâng nhưng lockfile còn cũ | dependency graph + lockfile | Cập nhật graph trước kết luận đã vá |
| API docs nhánh hiển thị patch mới hơn runtime | Javadoc release tag/source JAR | Không gán behavior patch mới cho patch cũ |
| Production image khác CI build | digest/SBOM/manifest | Chỉ kết luận theo JAR thật đang deploy |
| Tìm “migration” ở latest 7.x cho dự án 6.5 | Preparation guide 6.5 | Theo đúng lộ trình và compatibility |

## 17. Những lỗi thường gặp và cách sửa

### Lỗi 1 – Tìm Google rồi lấy snippet đầu tiên

Snippet có thể dùng `WebSecurityConfigurerAdapter` hoặc `antMatchers` từ Spring Security 5.x, trong khi project đang dùng 6/7. Cách sửa: mở docs có `/6.5/` hay `/7.0/`, đọc Java DSL và xác nhận Javadoc/migration.

### Lỗi 2 – Mặc định Javadoc latest là API của mọi patch

Ngay cả cùng release line, patch có thể bổ sung/sửa behavior. Cách sửa: ghim exact runtime patch, tìm Javadoc/source tag/`javap` phù hợp khi cần.

### Lỗi 3 – Chỉ biết version Spring Boot

Boot BOM chọn Spring Security nhưng có thể bị override/lock hoặc khác runtime. Cách sửa: resolved graph `spring-security-core/web/config/...` và artifact production.

### Lỗi 4 – Bị ClassNotFoundException thì thêm random JAR

Có thể làm các modules lệch train, gây lỗi mới. Cách sửa: tìm đúng artifact/module, BOM/constraints và test toàn bộ graph.

### Lỗi 5 – Đọc reactive cho Servlet

`SecurityWebFilterChain` không phải `SecurityFilterChain`, `ServerHttpSecurity` không phải `HttpSecurity`. Cách sửa: xác định stack trước khi mở sidebar.

### Lỗi 6 – Nhầm sample code với standalone app

Một snippet có `http` nhưng thiếu imports/bean/context có thể chỉ minh họa DSL. Cách sửa: ghi rõ “snippet”, tạo `@Bean SecurityFilterChain` và user store/decoder cần thiết; compile/test.

### Lỗi 7 – Nâng một module của nhánh mới vào project cũ

Spring Security 7 WebAuthn/MFA components không tự tương thích với Spring Security 6 và Boot 3. Cách sửa: đọc migration, cập nhật coordinated release train.

### Lỗi 8 – Đọc “MFA” và nghĩ bật login thứ hai là đủ

Nhiều login mechanisms có thể là lựa chọn **OR**, không phải policy **AND**. Cách sửa: đọc Reference MFA đúng version, xác định factor assurance và test thiếu yếu tố.

### Lỗi 9 – Kiểm token/JWT qua principal giả rồi nói đã kiểm chữ ký

`@WithMockUser`/`jwt()` bỏ qua verifier. Cách sửa: thêm integration test với password/real signed JWT và negative tests.

### Lỗi 10 – Coi security advisory như release note chung

CVE có affected range/feature prereqs/fix/support channel riêng. Cách sửa: nguồn [spring.io/security](https://spring.io/security/), resolved deployed version và configuration evidence.

## 18. Checklist thao tác khi cần tra cứu API lần sau

1. **Xác định ứng dụng:** Spring Boot version, Security version, Framework version, Java/JDK toolchain, Servlet hay WebFlux.
2. **Lấy dependency graph thật:** Gradle/Maven compile/runtime/test và module coordinates.
3. **Chọn release line:** ví dụ 6.5 hoặc 7.0, không mặc định latest.
4. **Mở Reference cùng line:** tìm feature theo sidebar, kiểm URL và channel stable/preview.
5. **Tìm FQCN:** import/type/class, xác định module artifact.
6. **Mở Javadoc cùng line:** method/constructor/`@since`/deprecated/generics.
7. **Nếu cần patch exact:** Javadoc artifact/source JAR/tag/`javap`; ghi nếu online branch docs là patch mới hơn.
8. **Nếu đang upgrade:** mở preparation/migration guide source→target, Boot BOM compatibility và required JDK.
9. **Kiểm configuration:** filters, matchers, CSRF, session, auth providers, JWT validators, passkey/MFA dependencies.
10. **Compile một test/feature slice:** không copy snippet sang production trực tiếp.
11. **Kiểm negative security cases:** unauthenticated, wrong password, invalid token, insufficient scope, wrong tenant, replay/expired credential.
12. **Đối chiếu runtime artifact:** bootJar/SBOM/image digest nếu lỗi ở staging/production.
13. **Khi có CVE:** tra advisory và release fix đúng source/version/configuration.
14. **Ghi evidence:** URL bản tài liệu, exact version, commit, test name, thời điểm kiểm và giới hạn áp dụng.

## 19. Câu hỏi tự đánh giá

**Câu 1.** Project khai `spring-boot-starter-security` không version. Làm thế nào biết chính xác `AuthenticationEntryPoint` bạn có?  
**Trả lời:** Lấy resolved `spring-security-web` version bằng Gradle `dependencyInsight` hoặc Maven `dependency:tree`, mở Javadoc API của đúng nhánh và khi cần kiểm exact patch bằng JAR/source tag.

**Câu 2.** Đọc `/reference/` rồi thấy một API MFA mới; tại sao không được nói nó dùng được trên Spring Security 6.5?  
**Trả lời:** Trang không versioned thường theo bản hiện hành. Cần mở Reference/Javadoc `/6.5/` và đối chiếu availability; MFA API mới có thể thuộc 7.x.

**Câu 3.** “Javadoc của class có method” đã chứng minh application chạy method đó chưa?  
**Trả lời:** Chưa. Cần compiler/runtime dependency đúng, bean wiring, filters và integration tests.

**Câu 4.** Tại sao không chỉ tìm import `AuthenticationEntryPoint` trên IDE?  
**Trả lời:** Import xác định FQCN, nhưng chưa xác định API version/method signature, module dependency hay HTTP behavior. Cần Javadoc/Reference cùng bản.

**Câu 5.** Spring Security 6.5 và 7.x hướng dẫn thêm cùng WebAuthn dependency không?  
**Trả lời:** Không. 6.5 Reference minh họa `spring-security-web` + `webauthn4j-core`, còn trang mới 7.x dùng `spring-security-webauthn`.

**Câu 6.** Code `ServerHttpSecurity` có dùng nguyên trong Spring MVC/Servlet app không?  
**Trả lời:** Không. Servlet dùng `HttpSecurity` và `SecurityFilterChain`; Reactive dùng `ServerHttpSecurity` và `SecurityWebFilterChain`.

**Câu 7.** Gặp `NoSuchMethodError` sau deployment, nên làm gì trước khi sửa code?  
**Trả lời:** Kiểm compile/runtime dependency graphs, JAR thực trong artifact/image và classloader; có thể runtime đã dùng phiên bản khác compile.

**Câu 8.** Một Javadoc link `/6.5/` hiển thị `6.5.11`, nhưng production chạy `6.5.3`. Có thể xem toàn bộ docs đó là API đúng patch 6.5.3 không?  
**Trả lời:** Không. Nhánh docs thường theo patch hiện hành; muốn exact patch cần Javadoc/source/binary tương ứng.

**Câu 9.** Nếu test dùng `jwt()` của `spring-security-test` thành công, có kết luận app xác minh chữ ký JWT không?  
**Trả lời:** Không. Nó có thể inject `JwtAuthenticationToken` giả; phải test real decoder và token ký bởi test key.

**Câu 10.** Khi bị CVE, nên tin phần “latest” của Reference hay Advisory?  
**Trả lời:** Tra Spring security advisory đúng CVE để lấy affected/fixed ranges, điều kiện và support channel; kiểm exact runtime/deploy/config, rồi dùng versioned docs và migration guide để chọn bản vá tương thích.

## Tài liệu tham khảo chính thức

- [Spring Security Reference – index/chọn version](https://docs.spring.io/spring-security/reference/) – quan sát các nhánh Stable/Preview/Snapshot; không dùng làm link cố định cho project cũ.
- [Spring Security Reference 6.5](https://docs.spring.io/spring-security/reference/6.5/) – tài liệu theo nhánh 6.5.
- [Spring Security Reference 7.0](https://docs.spring.io/spring-security/reference/7.0/) – tài liệu theo nhánh 7.0.
- [Spring Security Reference 7.1](https://docs.spring.io/spring-security/reference/7.1/) – tài liệu theo nhánh 7.1.
- [Getting Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html) – release numbering, BOM và dependency management.
- [Servlet Authentication Architecture 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html) – `SecurityContext`, providers, filters, entry point.
- [Javadoc 6.5 AuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html) – class/method signature đúng nhánh.
- [Javadoc 7.0 AuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/AuthenticationEntryPoint.html) – so sánh API nhánh 7.0.
- [Spring Security 6.5 Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html) – WebAuthn dependencies & config của 6.5.
- [Spring Security Passkeys 7.x](https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html) – WebAuthn module của dòng hiện hành.
- [Spring Security 6.5 JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html) – `JwtDecoder`, validators và OAuth2 bearer.
- [Spring Security 6.5 Preparing for 7.0](https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html) – chuẩn bị trước migration.
- [Spring Security Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/) – những thay đổi sau khi chuyển.
- [Spring Boot Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html) – BOM, version management.
- [Gradle Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) – `dependencies`/`dependencyInsight`.
- [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) – `dependency:tree`.
- [Spring Security Advisories](https://spring.io/security/) – affected/fixed versions và điều kiện lỗ hổng.
