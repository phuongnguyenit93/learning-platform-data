# Tra cứu reference, API Javadoc và ví dụ đúng phiên bản đang sử dụng

> **Chủ đề:** Spring Security fundamentals · **Phiên bản và học tiếp**. Bài học xây dựng một quy trình có thể lặp lại để tìm **tài liệu Reference**, **API Javadoc**, **mã mẫu và bài kiểm thử** tương thích với phiên bản Spring Security **thực sự được resolve/chạy trong dự án**. Ví dụ thực hành dùng **Java 17, Maven, Spring Boot 3.3.5, Spring Security 6.3.4 mặc định qua BOM, Servlet/Spring MVC, JUnit 5 và MockMvc**. Không áp nguyên chữ ký API của Spring Security 7 lên một dự án đang chạy 6.x hoặc ngược lại.

## 1. “Phiên bản đang sử dụng” là phiên bản nào?

Khi thấy lỗi biên dịch một API Spring Security, người học thường tìm tên class trên công cụ tìm kiếm rồi lấy snippet đầu tiên. Cách đó nguy hiểm vì có nhiều thứ có thể khác nhau:

- **Spring Boot version:** ví dụ §3.3.5§, §3.5.x§ hoặc §4.x§.
- **Spring Security version:** ví dụ §6.3.4§, §6.5.x§ hoặc §7.x§, được quản lý bởi BOM nhưng có thể bị override.
- **Spring Framework version** và **Java version**, có ràng buộc tương thích riêng.
- **Runtime Servlet hay reactive:** §HttpSecurity§/§SecurityFilterChain§ khác §ServerHttpSecurity§/§SecurityWebFilterChain§.
- **Module có trên classpath:** §spring-security-web§, §spring-security-config§, §spring-security-test§, §spring-security-oauth2-resource-server§, §spring-security-oauth2-jose§...
- **Mã tài liệu thuộc release nào:** trang §/spring-security/reference/§ thường hiển thị tài liệu hiện hành, không mặc định là release mà ứng dụng của bạn đang dùng.
- **Mã ví dụ thuộc tag/commit nào:** README của nhánh §main§ hoặc code trên blog cũ không tự bảo đảm biên dịch với project hiện tại.

**Thứ tự ưu tiên:** xác định dependency *resolved* và runtime artifact → chọn đúng major/minor/patch và stack → đọc Reference giải thích hành vi → kiểm tra Javadoc chính xác của class/method → kiểm tra sample đúng tag và dependencies → compile/test trong project thực.

### 1.1 Vì sao chỉ đọc pom.xml chưa đủ?

Ví dụ file Maven chứa:

§§§xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
§§§

Đoạn này **không có version Spring Security** vì Spring Boot parent/BOM quản lý dependency. Người đọc không nên đoán “Boot 3 nghĩa là Security 6 mới nhất”. Ngay trong Spring Boot 3, từng minor/patch có thể quản lý phiên bản khác nhau. Maven dependency management, §<spring-security.version>§, BOM import hoặc dependency khai báo trực tiếp có thể thay kết quả.

Ví dụ được kiểm tra theo BOM: **Spring Boot 3.3.5 quản lý Spring Security 6.3.4** trong bộ mặc định, nếu dự án không override. Nhưng phải xác minh cây dependency: không khẳng định mọi ứng dụng Boot 3.3.5 ngoài thực tế vẫn dùng đúng 6.3.4.

### 1.2 Không coi “mới nhất” là “đúng nhất”

Một trang chính thức được cập nhật năm 2026 có thể sử dụng Spring Security 7.x. Trang đó đúng **cho release của nó**, nhưng mẫu trong đó có thể sử dụng API mới, khác signature, namespace hoặc hành vi mặc định của 6.3.x.

| Nhánh ứng dụng minh họa | Spring Security thường được quản lý | Cách dùng tài liệu |
| --- | --- | --- |
| Spring Boot 3.3.5 | Spring Security 6.3.4 mặc định nếu không override | Xem Javadoc 6.3.4; đối chiếu Reference 6.x và change log |
| Spring Boot 3.5.x | Spring Security 6.5.x theo BOM của bản Boot cụ thể | Dùng Reference 6.5 và Javadoc patch thực tế |
| Spring Boot 4.x | Spring Security 7.x theo BOM tương ứng | Dùng Reference 7.x, Javadoc 7.x và migration guide |
| Không dùng Boot BOM | Do project chọn | Kiểm tra §dependency:tree§/§dependencyInsight§ rồi mới chọn docs |

Bảng chỉ là **cách xác định thế hệ**, không phải bảng tương thích đầy đủ cho mọi patch. Khi upgrade framework, luôn kiểm tra compatibility matrix và quản lý dependency của release được chọn.

## 2. Bản đồ ba loại tài liệu chính thức

| Nguồn | Trả lời câu hỏi nào? | Khi nào dùng? | Điều cần đề phòng |
| --- | --- | --- | --- |
| **Spring Security Reference** | “Cơ chế này vận hành ra sao, cấu hình đúng cách nào, ví dụ use case?” | Học authentication, authorization, CSRF, OAuth2, filter chain, testing | Trang version mới có thể mô tả behavior/API khác |
| **API Javadoc** | “Class, interface, package, constructor, overload, return type, deprecation, since là gì?” | Khi code không compile, cần implement custom interface hoặc chọn overload | Javadoc code fragment có thể dùng API cũ; đọc cả §@Deprecated§ và §forRemoval§ |
| **Official samples/tests** | “Làm sao nối các bean, cấu hình và test đầy đủ trong một project?” | Khi cần áp dụng từ POM đến MockMvc/WebTestClient | Nhánh §main§ thay đổi liên tục; phải xem tag/commit và build files |
| **Spring Boot documentation** | “Starter, auto-configuration, BOM, property và dependency versions nào?” | Khi dùng §spring-boot-starter-security§ hoặc test/Actuator | Version của Boot không đồng nghĩa Security |
| **Release notes + migration guide** | “Điều gì thêm, bị deprecated, thay đổi mặc định hoặc bị bỏ?” | Trước khi nâng minor/major và khi snippet cũ báo deprecation | Đọc hướng dẫn của cả nguồn và đích; không chỉ changelog |
| **Issue/Stack Overflow/blog** | “Có ai gặp vấn đề tương tự?” | Tạo giả thuyết hoặc xem giải pháp thay thế | Không phải chuẩn API; ngày đăng, version và môi trường có thể khác |

**Cách sử dụng hiệu quả:** Reference cho **ý nghĩa**, Javadoc cho **hợp đồng Java chính xác**, sample cho **cách ghép các bộ phận**, còn test/CI cho **bằng chứng chạy với dependency của dự án**. Không một nguồn riêng lẻ thay thế toàn bộ quy trình.

### 2.1 Các trang khởi đầu có tính định hướng

- Landing page hiện hành: https://docs.spring.io/spring-security/reference/
- Reference **Spring Security 6.5**: https://docs.spring.io/spring-security/reference/6.5/
- Reference **Spring Security 7.0**: https://docs.spring.io/spring-security/reference/7.0/
- Boot 3.3 — Spring Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Getting Spring Security (Boot/starter/BOM): https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html
- Migration 6.5 → 7: https://docs.spring.io/spring-security/reference/migration/
- Spring Security Javadoc **6.3.4**, class §HttpSecurity§: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
- Spring Security Javadoc **6.3.4**, interface §SecurityFilterChain§: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/SecurityFilterChain.html

**Đừng tự tạo link phiên bản bằng suy đoán.** Không phải mọi đường dẫn Reference cũ đều còn có cấu trúc versioned giống trang mới. Nếu link §/reference/6.3/...§ không tồn tại, sử dụng Javadoc đúng 6.3.4, release notes và bản reference/zip được nhà phát hành lưu trữ; đối chiếu với nguồn 6.x hiện có, đồng thời **ghi rõ khi một snippet cần kiểm tra lại**.

## 3. Xác định phiên bản thực tế bằng Maven

### 3.1 Từ parent/BOM đến resolved artifacts

Trong dự án Maven, đầu tiên đọc cấu hình dependency của project:

§§§bash
mvn -version
mvn help:effective-pom
§§§

§mvn -version§ cho thấy Maven và JDK đang dùng, **không** cho biết Spring Security dependency. §help:effective-pom§ cho thấy kết quả gộp parent, profile và management; file có thể rất dài, không cần gửi toàn bộ cho người ngoài.

Để liệt kê các module Spring Security đã thực sự được chọn:

§§§bash
mvn dependency:tree -Dincludes=org.springframework.security
§§§

Trong một dự án thực, bạn có thể thấy những artifact như:

§§§text
org.springframework.security:spring-security-config:jar:6.3.4:compile
org.springframework.security:spring-security-web:jar:6.3.4:compile
org.springframework.security:spring-security-core:jar:6.3.4:compile
org.springframework.security:spring-security-test:jar:6.3.4:test
§§§

Đây là **ví dụ rút gọn về dạng dòng kết quả**, không phải cây dependency nguyên văn của một lệnh chạy trên dự án thật. Dependency tree thực có ký hiệu phân cấp, số module khác và artifact không thuộc Security.

**Đọc kết quả theo từng module:** §spring-security-web§, §spring-security-config§, §spring-security-core§ và §spring-security-test§ nên cùng bộ phiên bản được quản lý tương thích. Nếu một module ở 6.3.x và module khác ở 6.5.x do override/transitive dependency, cần tìm nguyên nhân trước khi tra Javadoc. Đừng chỉ nhìn §spring-boot-starter-security§: version của starter là version Boot, không phải version các module Security.

Một lệnh lọc riêng khi cần:

§§§bash
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-web
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-test
§§§

Các tham số §-Dincludes§ lọc artifact được hiển thị; plugin và shell có thể cần cách quote riêng trong một số trường hợp. Nếu dùng multi-module reactor, chạy đúng module ứng dụng hoặc chỉ rõ module bằng §-pl§ và phần phụ thuộc cần thiết; đừng chỉ nhìn parent POM không đóng gói app.

### 3.2 Tìm override có chủ đích hoặc vô tình

Kiểm tra §pom.xml§ và effective POM xem có:

§§§xml
<properties>
    <spring-security.version>6.3.4</spring-security.version>
</properties>
§§§

Hoặc version được pin thẳng:

§§§xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-core</artifactId>
    <version>6.3.4</version>
</dependency>
§§§

Hai đoạn là **minh họa cấu hình**, không có nghĩa bạn phải chép cả hai. Với Spring Boot, ưu tiên để BOM quản lý Security trừ khi có lý do kỹ thuật bảo mật/tương thích được kiểm chứng. Ghi chú lý do override; đừng chỉ nâng riêng một artifact mà để các module khác ở version cũ.

Khi phát hiện xung đột, ghi lại: module nào yêu cầu version nào, version nào được chọn, BOM/profile nào quyết định, và test nào xác nhận trạng thái sau sửa. Maven §dependency:tree§ phản ánh resolution của project, là cơ sở tốt hơn dữ liệu từ blog.

### 3.3 Kiểm tra artifact triển khai, không chỉ project nguồn

Nếu đã có JAR Spring Boot đóng gói, có thể kiểm tra tên các thư viện nằm trong JAR:

§§§bash
jar tf target/my-app.jar | grep 'BOOT-INF/lib/spring-security'
§§§

Lệnh mang tính minh họa cho **Spring Boot executable JAR**, shell Unix/Git Bash và đúng tên file build. Trong một fat JAR kiểu này, bạn có thể thấy §BOOT-INF/lib/spring-security-web-6.3.4.jar§. Nếu đóng gói bằng WAR, native image, custom classloader hoặc container image, đường dẫn và cách kiểm tra khác. Runtime còn có thể bị ảnh hưởng bởi external classpath và môi trường container; cần xác minh **chính artifact đã deploy** khi điều tra production.

Với Windows PowerShell:

§§§powershell
jar tf target\my-app.jar | Select-String "BOOT-INF/lib/spring-security"
§§§

Nếu chưa có file JAR, chạy build trước; không suy ra phiên bản runtime từ mỗi tên artifact dự kiến.

## 4. Xác định phiên bản bằng Gradle

Gradle thường dùng plugin Spring Boot và dependency-management plugin hoặc native Gradle platform/BOM. Cấu hình có thể trông như:

§§§groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
§§§

Đây là **fragment §build.gradle§ Groovy**, không phải project Gradle hoàn chỉnh. Trong môi trường thật, plugin versions có thể được cung cấp bởi version catalog hoặc §settings.gradle§. Đừng đoán version Spring Security từ việc Gradle không hiện số version trong dependency declaration.

Lệnh nên dùng:

§§§bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
§§§

Trên Windows có thể dùng §gradlew.bat§ thay cho §./gradlew§. §dependencyInsight§ cho biết đường chọn version, lý do resolution/constraint hoặc conflict. Chạy trong **module thực sự tạo application**, không chỉ root project trong multi-project build.

Để tra doc đúng bản, lấy version **resolved** từ §runtimeClasspath§/§testRuntimeClasspath§; version hiển thị trong version catalog mà chưa được chọn chưa phải bằng chứng. Test module nên nhất quán với version security runtime.

## 5. Đọc Reference cho đúng stack và use case

Spring Security có hai mô hình web lớn:

| Servlet / MVC | Reactive / WebFlux | Không nên trộn |
| --- | --- | --- |
| §HttpSecurity§ | §ServerHttpSecurity§ | Builder cấu hình security khác |
| §SecurityFilterChain§ | §SecurityWebFilterChain§ | Kiểu bean khác |
| §Filter§/§OncePerRequestFilter§ | §WebFilter§ | Servlet filter vs Reactor pipeline |
| §AuthenticationManager§ | §ReactiveAuthenticationManager§ | Phương thức đồng bộ vs §Mono<Authentication>§ |
| §UserDetailsService§ | §ReactiveUserDetailsService§ | Tải user sync vs reactive |
| §SecurityContextHolder§ | §ReactiveSecurityContextHolder§ | ThreadLocal vs Reactor Context |
| §MockMvc§ + §spring-security-test§ | §WebTestClient§ + reactive test tools | Môi trường HTTP test khác |
| §AccessDeniedHandler§ | §ServerAccessDeniedHandler§ | Handler và return type khác |

**Cách chọn:** nếu project dùng §spring-boot-starter-web§ và servlet web app, tìm Reference → Servlet. Nếu chỉ dùng §spring-boot-starter-webflux§ để phục vụ reactive endpoints, tìm Reference → Reactive. Một project có WebClient **không tự biến server MVC thành WebFlux**; WebClient cũng dùng được trong Servlet apps.

Đừng copy một đoạn §ServerHttpSecurity§ từ reactive reference vào method nhận §HttpSecurity§, rồi sửa kiểu trả về để ép biên dịch. Đó là hai contract khác nhau.

### 5.1 Đọc đúng vấn đề thay vì tìm mỗi từ “security”

Ví dụ lỗi “authenticated user bị 403 trên §/admin§”:

1. Reference **Servlet → Authorization → Authorize HTTP Requests** để hiểu matcher và authority.
2. Javadoc §HttpSecurity#authorizeHttpRequests(Customizer)§ và §SecurityFilterChain§ của version resolved.
3. Xác định §hasRole("ADMIN")§ và §hasAuthority("ROLE_ADMIN")§ theo role prefix mặc định.
4. Tham khảo official test examples của **cùng generation**.
5. Chạy negative tests: anonymous, user không đủ quyền, user có role.
6. Nếu chỉ POST bị 403, xem thêm **CSRF Reference** chứ không kết luận role sai.

Ví dụ lỗi “callback OAuth2 khác tài liệu” thì phải mở phần OAuth2 Client, kiểm tra module §spring-security-oauth2-client§ trên dependency tree và Javadoc lớp converter/handler đang override. Không thay một class bằng class cùng tên ở package khác khi chưa biết interface đã đổi.

## 6. Javadoc: xác minh một API tới mức phương thức

Reference nói **nên làm gì**; Javadoc giúp trả lời **có thể gọi chính xác hàm nào**.

Giả sử cần cấu hình rule cho servlet app sử dụng 6.3.4. Mở Javadoc tương ứng:

https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html

Trong class §HttpSecurity§, tìm §authorizeHttpRequests§. Javadoc 6.3.4 liệt kê overload nhận §Customizer<...>§ và overload **không tham số** bị đánh dấu deprecated/for removal ở thế hệ tương lai.

Mẫu khuyến nghị phù hợp với 6.3.4:

§§§java
@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
§§§

Đây là **fragment**: muốn compile cần import §@Bean§, §SecurityFilterChain§, §HttpSecurity§ và §Customizer§ trong một class Spring configuration; ví dụ dự án hoàn chỉnh ở phần 8.

Mẫu cũ có thể được tìm thấy trong Javadoc/một blog:

§§§java
// Phản ví dụ về kiểu DSL cũ: có thể deprecated hoặc bị loại ở release mới.
http.authorizeHttpRequests()
    .requestMatchers("/admin").hasRole("ADMIN")
    .and()
    .httpBasic();
§§§

Không nên copy snippet cũ chỉ vì nó vẫn xuất hiện trong trang Javadoc. **Chữ ký overload**, tag §Deprecated§, mục §Since§, §See Also§ và cảnh báo §forRemoval§ quan trọng hơn việc snippet trông quen thuộc.

### 6.1 Các mục phải đọc trong Javadoc

1. **Package và import chính xác:** §org.springframework.security.config.annotation.web.builders.HttpSecurity§, không phải package reactive.
2. **Class hay interface:** có thể khởi tạo trực tiếp hay do Spring tạo bean?
3. **Kiểu tham số:** §Customizer<T>§, §Supplier<Authentication>§, §ServerWebExchange§, §HttpServletRequest§...
4. **Kiểu trả về:** §SecurityFilterChain§, §AuthorizationDecision§, §Mono<Void>§...
5. **Checked exceptions:** ví dụ method xây chain có thể khai báo §throws Exception§.
6. **Overloads:** overload cũ có thể deprecated, overload mới cần lambda.
7. **Since/Deprecated/forRemoval:** đánh giá support cho version nguồn và đích.
8. **Semantics:** Javadoc nói §null§, §empty§, exception hoặc default có ý nghĩa gì?
9. **Kế thừa/interface:** đôi khi method được khai báo ở superinterface chứ không ở class đang xem.
10. **API artifact:** symbol thuộc §spring-security-web§, §-config§, §-core§ hay module OAuth2 bổ sung?

**Đừng nhìn chữ “Since: 6.4” rồi sử dụng trên 6.3.4.** API thêm ở minor mới không tự xuất hiện ở patch cũ. Ngược lại, một API có mặt ở 6.3.4 có thể bị deprecate/loại ở 7.x.

### 6.2 Đọc source khi Javadoc chưa đủ

Nếu contract chưa rõ, tiếp tục đến source đúng **tag release**, test của module và migration notes. Đối với API nội bộ hoặc phụ thuộc vào builder behavior, đọc source phiên bản chính xác có thể giải thích default hoặc order. Nhưng phân biệt:

- **Public API Javadoc**: nền tảng của code tích hợp.
- **Reference**: cách dùng được khuyến nghị.
- **Implementation/test nội bộ**: giúp hiểu, nhưng có thể đổi mà không bảo đảm backward compatibility.

Không gọi một implementation internal là public extension point chỉ vì nó là §public class§; kiểm tra Javadoc, đường đi cấu hình và support policy.

## 7. Tìm và đánh giá code mẫu đúng phiên bản

Một đường thường dùng là từ **Reference** đến code sample chính thức hoặc dự án §spring-security-samples§. Nếu dùng GitHub, không chỉ mở branch §main§ rồi dán code:

1. Xác định repo **chính thức** và đường dẫn sample từ trang reference của bản tương ứng.
2. Kiểm tra tag/commit cụ thể; repository sample có thể phát triển song song với Spring Security mới nhất.
3. Đọc §settings.gradle§, §build.gradle§, §pom.xml§ hoặc version catalog của **sample**, xác định dependency thực tế.
4. Xác định sample thuộc **Servlet hay reactive**, **HTTP Basic, form login, OAuth2 client hay resource server**.
5. Xác định Java/Jakarta version; Spring Security 6 dùng §jakarta.servlet§, không dùng các snippet §javax.servlet§ cũ của Servlet 5.x trở về trước.
6. Kiểm tra sample có config giá trị demo như §{noop}§, user/password hardcode, CSRF disabled hoặc TLS giả định hay không.
7. Xem test kèm theo, nhất là negative path; đừng học theo chỉ một controller thành công.
8. Nếu sample khác version, coi nó là **ý tưởng**, đối chiếu lại Javadoc và compile với project của bạn trước khi sử dụng.

Ví dụ format ghi chú nguồn bên cạnh đoạn code học được:

§§§text
Source type: Official Spring Security sample / Reference
Source version: checked release/tag/commit (record concrete ID)
Project: Spring Boot 3.3.5; Spring Security resolved 6.3.4
Web stack: Servlet / Spring MVC
Feature: authorizeHttpRequests + HTTP Basic + CSRF defaults
API checked: HttpSecurity#authorizeHttpRequests(Customizer)
Verification: mvn test + HTTP 200/401/403 assertions
Known limitations: demo-only in-memory user, local password
§§§

Mục tiêu là **truy xuất nguồn gốc kỹ thuật**, không phải điền thông tin cho có. Nếu repo hoặc tag không xác nhận được, ghi “chưa xác minh”, đừng tự điền commit ID.

### 7.1 Quy tắc lựa chọn ví dụ

Ưu tiên theo thứ tự:

- Sample/Test chính thức cùng major/minor và stack.
- Sample chính thức khác patch nhưng Javadoc và behavior đã được xác minh.
- Reference khác minor trong cùng major, sau khi kiểm tra method có tồn tại và behavior tương thích.
- Sample cộng đồng đã kiểm tra dependency và negative tests.
- Blog/snippet không ghi version: **chỉ tham khảo khái niệm**, không dùng làm code production khi chưa kiểm chứng.

Một snippet từ blog “Spring Security 5 + WebSecurityConfigurerAdapter” rất dễ khác cấu hình Spring Security 6. Không dùng bản sao nào chỉ vì IDE auto-import được.

## 8. Dự án Spring Boot 3.3.5: code và test với API đã tra Javadoc

Ví dụ dưới đây sử dụng một baseline **có version cố định** để người học tự chạy: Boot §3.3.5§ quản lý Spring Security §6.3.4§ theo BOM mặc định, nếu không có override. Code dùng §SecurityFilterChain§, §HttpSecurity#authorizeHttpRequests(Customizer)§, §Customizer.withDefaults()§ và test MockMvc. **Không pin thủ công §spring-security-web§/§-config§/§-test§**, giúp các module do BOM quản lý đồng nhất.

### 8.1 Cấu trúc

§§§text
version-aware-security/
├── pom.xml
└── src/
    ├── main/java/com/example/versiondocs/
    │   └── VersionAwareSecurityApplication.java
    └── test/java/com/example/versiondocs/
        └── VersionAwareSecurityApplicationTest.java
§§§

### 8.2 pom.xml

§§§xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>version-aware-security</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
§§§

### 8.3 Application Java đầy đủ

Tạo §src/main/java/com/example/versiondocs/VersionAwareSecurityApplication.java§:

§§§java
package com.example.versiondocs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class VersionAwareSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(VersionAwareSecurityApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-123"))
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-456"))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        String publicPage() {
            return "public ok";
        }

        @GetMapping("/me")
        String currentUser(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin ok";
        }

        @PostMapping("/notes")
        String postNote() {
            return "note saved";
        }
    }
}
§§§

**Giải thích theo API đã tra:**

- §@Bean SecurityFilterChain§ thay cho cách kế thừa §WebSecurityConfigurerAdapter§ của các ví dụ cũ; §http.build()§ kết thúc cấu hình.
- §authorizeHttpRequests(auth -> ...)§ là overload nhận §Customizer§, có trong Javadoc 6.3.4; không dùng biến thể không tham số đã được đánh dấu deprecated.
- §requestMatchers§ đặt theo thứ tự: §/public§ công khai, §/admin§ yêu cầu role và mọi request khác phải authenticated.
- §hasRole("ADMIN")§ theo role prefix mặc định kiểm §ROLE_ADMIN§; khi dùng §hasAuthority§ phải truyền authority string chính xác.
- §httpBasic(Customizer.withDefaults())§ cung cấp cơ chế xác thực thật cho demo; §formLogin(...disable)§ làm 401 thay vì redirect trang login trong các case này.
- CSRF vẫn **bật** theo mặc định. §POST /notes§ thiếu token thường 403 dù password đúng; test cần §csrf()§.
- §UserDetailsService§ và BCrypt dùng hai user demo, không phải production account store. Không ghi password thật hoặc token vào log.

### 8.4 Test JUnit 5/MockMvc để xác thực hành vi đúng thế hệ API

Tạo §src/test/java/com/example/versiondocs/VersionAwareSecurityApplicationTest.java§:

§§§java
package com.example.versiondocs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class VersionAwareSecurityApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    void anonymousUserCannotReadMe() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongCredentialIsRejected() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void realBasicAuthenticationReturnsPrincipalName() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "reader-demo-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello reader"));
    }

    @Test
    void readerCannotEnterAdminPage() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("reader", "reader-demo-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdminPage() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-demo-456")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin ok"));
    }

    @Test
    void missingCsrfStillBlocksPost() throws Exception {
        mvc.perform(post("/notes")
                .with(httpBasic("reader", "reader-demo-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndCredentialAllowPost() throws Exception {
        mvc.perform(post("/notes")
                .with(httpBasic("reader", "reader-demo-123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("note saved"));
    }
}
§§§

**Tám test** đảm bảo 200/401/403, credential đúng/sai và CSRF hợp lệ/thiếu. Các test xác thực Basic thông qua filter/provider thật của demo, không dùng §@WithMockUser§ để thay thế kiểm tra password.

### 8.5 Các bước chạy và xác minh version trước khi chạy test

Yêu cầu Java 17+ và Maven. Từ thư mục có §pom.xml§:

§§§bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework.security
mvn test
mvn spring-boot:run
§§§

Mở terminal khác:

§§§bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u reader:reader-demo-123 http://localhost:8080/me
curl -i -u reader:reader-demo-123 http://localhost:8080/admin
curl -i -u admin:admin-demo-456 http://localhost:8080/admin
§§§

| Request | Status dự kiến | Body ổn định |
| --- | --- | --- |
| GET §/public§ anonymous | 200 | §public ok§ |
| GET §/me§ anonymous | 401 | Basic challenge |
| GET §/me§ với reader và password đúng | 200 | §hello reader§ |
| GET §/admin§ với reader | 403 | Không gọi controller |
| GET §/admin§ với admin | 200 | §admin ok§ |

Đây là **kết quả kỳ vọng theo mã ví dụ**, không phải tuyên bố đã chạy Maven trên máy người học. Khi test không compile, quay lại §dependency:tree§ và Javadoc phiên bản đó, không “fix” bằng cách chép code 7.x vào pom 3.3.x.

## 9. Phân biệt lỗi từ tài liệu sai phiên bản với lỗi logic thật

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách tra cứu |
| --- | --- | --- |
| §Cannot resolve symbol SecurityFilterChain§ | Module/config/dependency chưa có hoặc sai import | Tree có §spring-security-web§? Javadoc package đúng? |
| §Cannot resolve method ...§ | API mới hơn version resolved; overload khác | Javadoc đúng patch → Method Summary → Since |
| Một method deprecated | Code cũ còn tồn tại nhưng sẽ bị loại | Javadoc §Deprecated§, migration guide, overload thay thế |
| §javax.servlet§ không tìm thấy | Snippet của Spring Security 5/Java EE cũ | Spring Security 6 dựa trên §jakarta.servlet§ |
| Class §HttpSecurity§ không dùng được trong WebFlux | Trộn Servlet và reactive | Reference Reactive và §ServerHttpSecurity§ |
| §NoClassDefFoundError§ khi chạy | Trộn module Security/framework version | Dependency tree runtime và packaged JAR |
| Test compile nhưng auth không chạy | Test thiếu Spring Security integration/filter | §@AutoConfigureMockMvc§ / §springSecurity()§ |
| CSRF 403 với POST dù user đúng | CSRF vẫn bật theo mặc định | Reference CSRF và test §with(csrf())§ |
| §@WithMockUser§ trả 200 nhưng password sai ngoài đời | Mock bypass authentication provider | Test §httpBasic§/JWT thật |
| §hasRole("ADMIN")§ trả 403 dù có §ADMIN§ | Authority cần §ROLE_ADMIN§ theo prefix | Reference + Javadoc role/authority |
| Code 6.3 compile nhưng không compile trên 7.x | API deprecated đã bị remove hoặc type thay đổi | Migration 6.5 → 7, Javadoc 7.x |
| Code 7.x compile mà behavior khác | Defaults/contract/schema/stack thay đổi | Release notes + regression tests |

**Không kết luận lỗi do version khi chưa kiểm tra:** 401/403 cũng có thể do password, session, wrong role, CSRF, CORS, tenant, token issuer hoặc filter order. Version docs giúp xác định *contract có thể dùng*, còn test giúp xác định *cấu hình thực chạy ra sao*.

### 9.1 Cách kiểm tra API “Since” thực tế

Giả sử một bài trên mạng sử dụng method §foo(Bar)§ mà compiler báo không tồn tại. Quy trình:

1. Xác định **fully qualified class** chứa method; không tìm theo tên §foo§ chung chung.
2. Lấy resolved version của **artifact chứa class**, ví dụ §spring-security-config:6.3.4§.
3. Mở Javadoc 6.3.4 của class đó và tìm overload §foo(Bar)§.
4. Nếu **không có**, so Javadoc release có method và thông tin “Since” để biết khi nào xuất hiện.
5. Nếu method tồn tại nhưng type của tham số khác, đọc generic types/import/dependencies; IDE auto-import có thể chọn sai §Authentication§/§RequestMatcher§.
6. Nếu method deprecated hoặc for removal, đọc phần hướng dẫn thay thế **đúng major**.
7. Chọn giải pháp có thể compile với baseline thực; viết test sau mỗi bước, không thay ồ ạt dependency để làm một snippet hoạt động.

### 9.2 Điểm dễ nhầm trong Spring Security 6.3 và 7.x

Ở Javadoc §HttpSecurity§ 6.3.4, overload kiểu lambda như §authorizeHttpRequests(Customizer)§ là lựa chọn phù hợp; overload gọi không tham số đã được đánh dấu for removal 7.0. Vì vậy đoạn blog cũ dùng §.authorizeHttpRequests().and()§ có thể compile với warning ở 6.3, nhưng không nên là điểm khởi đầu khi muốn nâng lên 7.

Mặt khác, tài liệu 7.x có thể sử dụng API hoặc module không có trong 6.3. Đừng áp cấu trúc bean, package và Gradle dependencies của Boot 4 lên Boot 3.3 chỉ vì cùng tên feature. Đối với nâng major, dùng 6.5 như bước chuẩn bị theo migration guide của Spring Security, sau đó nâng Boot/framework/security như **một tổ hợp tương thích**.

## 10. Phân biệt dependency version, Javadoc version và runtime version

Trong một ticket “code theo docs không chạy”, nên ghi rõ ba sự kiện:

1. **Build resolution:** §mvn dependency:tree§/Gradle §dependencyInsight§ chọn những module Spring Security nào, version nào.
2. **Runtime artifact:** JAR/WAR/container image đang chạy chứa những library nào (nếu không dùng native image), có khác source/CI build không.
3. **Docs consulted:** URL Reference, URL Javadoc exact patch, sample tag/commit và ngày truy cập.

Ví dụ một phiếu điều tra tốt:

§§§text
Project: api-service
Build: Maven, Java 17, Spring Boot 3.3.5 parent
Resolved: spring-security-core/config/web/test 6.3.4
Runtime: executable JAR verified containing spring-security-web-6.3.4.jar
Stack: Servlet / Spring MVC
Symptom: authorization DSL found in online sample does not compile
Reference: Spring Security 6.x Servlet authorization
Javadoc: HttpSecurity 6.3.4, overload authorizeHttpRequests(Customizer)
Change: replace no-arg deprecated DSL with lambda overload
Evidence: mvn test, anonymous 401 / reader 403 / admin 200
§§§

Đó là **bản ghi giả lập minh họa quy trình**, không phải trạng thái build thật của người dùng. Đối với production, nguồn chuẩn là artifact thực được deploy; một POM trên main branch có thể không giống image đang chạy.

### 10.1 Version drift giữa dev, CI và production

Nguyên nhân thường gặp:

- CI dùng JDK khác local, hoặc build với một Maven profile khác.
- Dependency conflict từ thư viện bổ sung khiến classpath khác.
- Image production chưa được deploy sau khi merge.
- Cache artifact hoặc container registry trỏ tới image tag không bất biến.
- Spring Boot BOM bị override bởi dependency management khác.
- Test có §spring-security-test§ version khác runtime Security; lỗi chỉ lộ khi test chạy.
- Multi-module app sử dụng common security config nhưng module web không cùng dependency management.

**Biện pháp:** lock/test version theo quy trình quản lý dependency, dùng immutable image digest, tạo SBOM khi phù hợp, lưu §dependency:tree§/§dependencyInsight§ trong CI artifact khi điều tra. Không hardcode version khác nhau cho §security-core§/§-web§/§-config§ để chữa lỗi ngắn hạn.

## 11. Đọc migration guide trước khi nâng phiên bản

### 11.1 Patch, minor và major khác nhau

Spring Security sử dụng MAJOR.MINOR.PATCH. Một patch thường sửa bug/security; một minor có thể thêm API; major có thể thay đổi hoặc loại bỏ API. Nguyên tắc an toàn là **đọc changelog và chạy regression tests cho mọi nâng cấp**, nhất là security-sensitive behavior.

Với dự án Boot 3.3.5 + Security 6.3.4, nâng trực tiếp lên Boot 4/Security 7 không chỉ là sửa version string. Phải xem:

- Java baseline, Spring Framework và Jakarta Servlet API.
- API bị remove, DSL thay đổi, deprecated annotations, config classes.
- Security filter order, request matcher và authorization behavior.
- OAuth2/OIDC/JWT decoder, session, CSRF, CORS, headers và method security.
- Test framework và Boot auto-configuration (đặc biệt với test slices).
- Schema JSON/Jackson khi dùng OAuth/serialization và các converter.
- Rollback/rollout với các client/session đang tồn tại.

Tài liệu migration chính thức khuyến nghị dùng **Spring Security 6.5 để chuẩn bị cho 7.0**, sau đó nâng Boot/Security theo release tương thích. Điều này không có nghĩa **tự ý nâng riêng Spring Security 6.5 trên bất kỳ Boot 3.3 dự án nào**: vẫn cần BOM/framework compatibility và test.

### 11.2 Ma trận kiểm thử khi nâng version

| Nhóm | Case tối thiểu |
| --- | --- |
| Authentication | Credential đúng/sai, disabled/locked, MFA/OIDC nếu có |
| Authorization | Anonymous, thiếu quyền, đủ quyền, method security, tenant |
| CSRF | POST thiếu/sai/đúng token; cookie/session |
| CORS | Preflight hợp lệ, sai origin/method/header, credentialed response |
| Headers | HSTS HTTPS, CSP/frame policy, cache-control, nosniff |
| OAuth2/JWT | Invalid signature/issuer/audience/expiry, revoked/rotated key |
| Error handling | 401, 403, 5xx dependency outage; không leak secrets |
| Servlet/Reactive | Đúng filter/web chain, context propagation |
| Testing APIs | §spring-security-test§ version đồng bộ, MockMvc/WebTestClient |
| Observability | Log/audit/metrics và privacy sau upgrade |
| Runtime | Java, servlet container, Actuator exposure, proxy/gateway |

**Mục tiêu:** bảo đảm “cùng hành vi mong muốn” khi lên bản mới, không nhất thiết bảo đảm mọi error body/header nội bộ giống hệt từng byte nếu framework thay đổi. Tập trung kiểm tra contract bảo mật được định nghĩa trong app.

## 12. Cách học tiếp một API mới mà không bị quá tải

Khi gặp tên mới như §AuthorizationManager§, hãy dùng trình tự sáu bước:

1. **Mô tả nhu cầu bằng một câu:** “Tôi muốn chặn mọi tài khoản không có role ADMIN tại §GET /admin§”.
2. **Xác định stack/module/version:** Servlet/Security §6.3.4§/§spring-security-config§ + §spring-security-web§.
3. **Mở Reference đúng mục:** Servlet → Authorization → Authorize HTTP Requests.
4. **Tra Javadoc:** §HttpSecurity#authorizeHttpRequests(Customizer)§, §AuthorizationManager§ và các kiểu liên quan của version resolved.
5. **Xem sample + chạy tối thiểu:** một bean §SecurityFilterChain§, một controller, test 401/403/200.
6. **Viết lại bằng lời:** explain matcher precedence, role prefix, CSRF và những gì code chưa chứng minh; lưu URL docs/version trong ghi chú học.

Khi đã hiểu một use case, mới mở rộng sang method security, OAuth2 resource server, multi-chain hoặc WebFlux. Không học đồng thời 6.3 Servlet + 7.x reactive + 5.8 §WebSecurityConfigurerAdapter§ nếu đang giải một lỗi hiện tại.

## 13. Checklist kiểm tra snippet trước khi đưa vào ứng dụng

| Câu hỏi | Cần có bằng chứng |
| --- | --- |
| Đã biết version resolved chưa? | Maven dependency tree hoặc Gradle dependencyInsight |
| Đã xác minh artifact runtime chưa? | Packaged JAR/WAR/image hoặc classpath hiện chạy |
| Có cùng web stack không? | Servlet vs WebFlux từ starter và application type |
| Có đúng module không? | §spring-security-config/web/core/test/oauth2-*§ trên classpath |
| Reference đúng release chưa? | URL/version hoặc lưu ý khi dùng 6.5 để đối chiếu 6.3 |
| Javadoc đúng patch chưa? | Method Summary, overload, return type, Since/Deprecated |
| Sample có tag/commit không? | Build file và branch/tag rõ ràng |
| Có mã demo nguy hiểm không? | §{noop}§, hardcoded password, CSRF/headers disable, wildcard CORS |
| Đã compile chưa? | §mvn test§ hoặc Gradle §test§ chạy thành công |
| Đã test deny chưa? | Anonymous và thiếu role/invalid credential bị chặn |
| Behavior runtime khớp chưa? | 200/401/403, CSRF, headers đúng config |
| Có xem migration notes không? | Đặc biệt khi đổi major/minor |
| Có ghi lại nguồn gốc không? | Doc URL, module, version, commit/test evidence |

Một snippet **có API hợp lệ** chưa chắc có **chính sách bảo mật đúng**. Ví dụ §permitAll()§ compile ở nhiều release nhưng nếu đặt lên §/admin/**§ sẽ mở tài nguyên. Cần xem cả contract Java, use case và kết quả security test.

## 14. Những lỗi nghiên cứu tài liệu phổ biến

1. **Google cho trang mới nhất, ứng dụng chạy bản cũ.** Xác minh version và ghim Javadoc/reference ngay từ đầu.
2. **Nhìn version Spring Boot như version Spring Security.** Boot §3.3.5§ không có Security §3.3.5§; BOM mặc định quản lý §6.3.4§.
3. **Đọc Javadoc snippet mà không xem deprecation.** Ưu tiên overload mới được khuyến nghị cho release đang dùng.
4. **Copy mã từ §main§ không xem build file.** Sample có thể chuyển lên Boot4/Security7.
5. **Trộn §HttpSecurity§ với §ServerHttpSecurity§.** Servlet và reactive là hai contract khác nhau.
6. **Trộn §javax.servlet§ với §jakarta.servlet§.** Vấn đề thường xuất hiện khi dùng snippet trước Spring Security 6.
7. **Chỉ thêm starter-security nhưng quên module test/OAuth2.** Khi cần §spring-security-test§ hoặc jose/resource-server, kiểm tra dependency phù hợp.
8. **Nâng riêng §security-web§ để có API mới.** Các module không tương thích có thể gây runtime error.
9. **Tin IDE tự import là chính xác.** Kiểm tra fully qualified class và Javadoc exact version.
10. **Chỉ test 200, không test 401/403.** Code có thể biên dịch nhưng mở quyền.
11. **Không kiểm tra CSRF.** POST dùng đúng user nhưng thiếu token thường nhận 403 vì bảo vệ mặc định.
12. **Cho rằng §@WithMockUser§ test password.** Nó tạo mock SecurityContext, không xác minh HTTP Basic/JWT thực.
13. **Không đọc migration guide.** API deprecation và defaults có thể khác khi lên major.
14. **Chỉ dựa vào source trên nhánh chính.** Runtime có thể đang dùng artifact khác.
15. **Ghi link docs mà không ghi version.** Sau vài tháng người khác có thể mở ra nội dung khác.
16. **Bỏ qua security advisories.** Khi chọn patch hoặc nền tảng cũ, cần đánh giá trạng thái hỗ trợ và cập nhật bảo mật theo hướng dẫn vendor, không dùng ví dụ lịch sử làm cấu hình triển khai mới.

## 15. Kết luận

- **Bản “đúng” là bản dependency resolved và artifact đang chạy**, không phải số version đoán từ một starter hoặc tên bài blog.
- **Reference giải thích cơ chế; Javadoc kiểm tra hợp đồng API; sample/test chứng minh cách áp dụng.** Mỗi nguồn có vai trò khác nhau.
- Với ví dụ Boot §3.3.5§, bộ mặc định quản lý Security §6.3.4§; ghim Javadoc §6.3.4§ và đối chiếu Reference thuộc 6.x. Với Boot 4/Security 7, phải chọn docs mới và migration.
- **Kiểm tra overload, package, return type, deprecation và Since** trước khi copy đoạn code.
- **Bộ test positive/negative** là điều kiện cuối: compiler chấp nhận API chưa có nghĩa authorization/CSRF/authentication an toàn.
- Lưu **URL tài liệu, phiên bản, sample tag/commit và kết quả test** trong ghi chú hoặc PR để người sau tái lập việc nghiên cứu.

## Tài liệu chính thức và nguồn kiểm chứng

1. Spring Security Reference hiện hành: https://docs.spring.io/spring-security/reference/
2. Spring Security Reference 6.5: https://docs.spring.io/spring-security/reference/6.5/
3. Spring Security Reference 7.0: https://docs.spring.io/spring-security/reference/7.0/
4. Spring Security Reference — Getting Spring Security, BOM: https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html
5. Javadoc Spring Security 6.3.4 — HttpSecurity: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
6. Javadoc Spring Security 6.3.4 — SecurityFilterChain: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/SecurityFilterChain.html
7. Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
8. Spring Security — Migration to 7: https://docs.spring.io/spring-security/reference/migration/
9. Spring Boot 3.3 — Security Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
10. Maven Central — Spring Boot Starter OAuth2 Client 3.3.5, resolved Security 6.3.4: https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-oauth2-client/3.3.5
11. Maven Repository — Spring Boot 3.3.5 managed dependencies (Security BOM 6.3.4): https://mvnrepository.com/artifact/org.springframework.boot/spring-boot-parent/3.3.5/dependencies
12. Spring Security Test Reference: https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html