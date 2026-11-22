# Đối chiếu phiên bản Spring Boot, Spring Security và tính năng phân quyền

## Mục tiêu học tập

Khi nâng cấp Spring Boot, tên phiên bản trong `build.gradle` hay `pom.xml` chưa đủ để kết luận chương trình đang chạy tính năng phân quyền nào. **Spring Boot quản lý dependency**, còn **Spring Security cung cấp và thực thi các API xác thực/phân quyền**; ứng dụng tiếp tục chịu trách nhiệm cấu hình đúng request, method, resource và dữ liệu. Bản nâng cấp có thể biên dịch thành công nhưng thay đổi đường khớp URL, kiểu dispatch, method security, custom `AuthorizationManager` hoặc ánh xạ role/authority. Một kết quả “endpoint trả 200” không chứng minh rằng quyền vẫn được giữ đúng.

Bài này giúp bạn:

1. Đối chiếu dòng Spring Boot ↔ Spring Security và phiên bản artifact **thực sự được resolve** trong một bản build.
2. Phân loại chức năng phân quyền theo **request-level, method-level, object/data-level** và kiểm tra sự hiện diện/điều kiện kích hoạt của từng tính năng.
3. Nhận ra thay đổi đáng chú ý khi đi từ Security 5.x sang 6.x và 6.x sang 7.x; phân biệt API bị deprecated, bị loại bỏ và thay đổi hành vi mặc định.
4. Dùng các lệnh Gradle/Maven, mẫu cấu hình, test theo ma trận danh tính và đường dẫn để kiểm chứng chuyển đổi mà không vô tình mở quyền.
5. Viết bảng đối chiếu riêng cho dự án theo phiên bản cố định, evidence và quyết định PASS/FAIL, thay vì suy luận dựa trên tên release.

**Quy ước:** ví dụ dùng Java 17+ và Spring Boot/Spring Security ở các nhánh được nêu rõ. Những số `x` trong bảng chỉ **dòng phiên bản**, không cố định bản vá; bản vá và dependency quản lý phải đọc từ BOM/metadata chính xác của project. Thư viện bên thứ ba, Spring Cloud, Servlet/Reactive và cách cung cấp principal cũng phải được kiểm tra riêng.

## 1. Phân biệt trách nhiệm của Boot và Security

**Spring Boot** giúp dựng ứng dụng, khởi động, auto-configuration, cung cấp starter và dependency management (thường là BOM `spring-boot-dependencies`). Khi dùng dependency management của Boot đúng cách, phần lớn `org.springframework.security:*` lấy version tương thích do BOM chọn, trừ khi dự án hoặc plugin khác override.

**Spring Security** cung cấp `SecurityFilterChain`/`SecurityWebFilterChain`, xác thực, `GrantedAuthority`, `AuthorizationManager`, request matcher, method security, OAuth 2.0 resource server/client, CSRF và nhiều cấu phần khác. Có dependency Security **không có nghĩa** mọi cơ chế phân quyền đều đã bật:

- Khai báo starter không tự tạo quy tắc row-level/tenant-level cho repository.
- Method authorization bằng `@PreAuthorize` cần kích hoạt `@EnableMethodSecurity` (hoặc cấu hình tương đương); starter Security **không tự bật** method security.
- Một request-level rule `authenticated()` chỉ chứng minh caller đã đăng nhập; nó không tự xác nhận caller được phép xem hóa đơn/document theo ID.
- Một tên role trong token chưa tự trở thành `GrantedAuthority` đúng giá trị; JWT converter và prefix là các phần của hợp đồng.

Để biết “phiên bản hỗ trợ gì”, hỏi tuần tự: **artifact nào đã resolve? API đó có trong version không? cấu hình có kích hoạt không? bean/filter nào đang thực thi? các test quyền chứng minh hành vi nào?**

## 2. Ma trận đường phiên bản cần đối chiếu

Bảng sau là bản đồ **dòng release tiêu biểu**, không phải tất cả tổ hợp tương thích hoặc bản vá hiện hành:

| Dòng Spring Boot | Dòng Spring Security đi kèm/đích chính | Mốc liên quan đến phân quyền | Lưu ý đối chiếu |
| --- | --- | --- | --- |
| Boot **2.7.x** | Security **5.7.x** theo BOM thông thường | `WebSecurityConfigurerAdapter` và `authorizeRequests` là đường cấu hình legacy; hướng mới `SecurityFilterChain` đang được khuyến nghị | Có thể **chủ động** nâng riêng Security lên **5.8.x** để chuẩn bị cho 6.0; đó là bước migration có kiểm soát, không phải mặc định 2.7 |
| Boot **3.0.x** | Security **6.0.x** | Java 17+, Spring Framework 6, namespace Jakarta; hướng `SecurityFilterChain`/`authorizeHttpRequests` và `AuthorizationManager` | Kiểm tra quy tắc dispatch của filter, method security và import `javax.*` → `jakarta.*` |
| Boot **3.3.x** | Security **6.3.x** | Dòng 6.x triển khai request/method authorization hiện đại | Dùng tài liệu theo bản Security 6.3/6.x, kiểm tra BOM patch chính xác |
| Boot **3.5.x** | Security **6.5.x** | Dòng cuối 6.x, giai đoạn chuẩn bị nâng Security 7 | Hoàn tất bước “Preparing for 7” trước khi đổi major |
| Boot **4.0.x** | Security **7.0.x** | Một số API deprecated bị loại bỏ; `AuthorizationManager#check` bị thay bằng `authorize`; đổi một số matcher | Cần rà custom `AuthorizationManager`, `HttpSecurity` DSL, các matcher và legacy access API |
| Boot **4.1.x** | Security **7.1.x** | Cùng thế hệ Security 7 với các thay đổi/tính năng bổ sung | Không suy từ 4.0 ra từng method của 4.1; đối chiếu dependency versions và reference theo 7.1 |

**Cách dùng đúng:** đặt BOM đang chạy vào cột đầu, mở bảng “Managed Dependency Coordinates” của **chính bản Boot đó** để lấy `spring-security-config`, `spring-security-web`, `spring-security-core` và `spring-security-test`; kế tiếp đối chiếu với graph Gradle/Maven. Ví dụ các số `3.3.x → 6.3.x` và `4.0.x → 7.0.x` mô tả release line, không bảo đảm dự án có override hoặc dùng Spring Cloud sẽ resolve đúng các bản đó.

Những cặp Boot/Security mang tính khuyến nghị, không phải phép ghép tùy ý: nâng duy nhất `spring-security-web` sang major mới còn `spring-security-config` ở major cũ có thể gây `NoSuchMethodError`, `ClassNotFoundException` hoặc semantics chưa kiểm thử. Cần đối chiếu **tất cả artifact Security có mặt** và những thư viện tích hợp, thay vì chỉ so version starter.

### Tại sao không dùng danh sách “bản mới nhất” làm nguồn quyết định?

“Latest” thay đổi theo ngày và có thể là patch mới, preview hoặc snapshot. Dự án còn có baseline Java, Spring Framework, container Servlet, Spring Cloud và thư viện nền. Bản nâng cấp phù hợp là **release ổn định được hỗ trợ cho chính dự án**, với dependency tree, release notes, migration guide và test. Không tự thay dependency production bằng bản mới nhất qua tìm kiếm trang chủ rồi kết luận tương thích.

## 3. Kiểm tra version thực tế ở Gradle và Maven

### 3.1. Gradle: phân biệt version khai báo với version resolve

Ví dụ cho một ứng dụng **Spring Boot 3.3.x**; các plugin/repository khác của dự án có thể bổ sung theo nhu cầu, đây là **đoạn build cấu hình minh họa**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`3.3.0` ở đây chỉ để minh họa bản build tái lập, **không phải bản mới nhất hoặc khuyến nghị production**. Starter Security và `spring-security-test` không gắn version riêng vì muốn dùng dependency management của Boot. Nếu dự án dùng Gradle native platform/BOM thay plugin quản lý dependency, hãy kiểm tra chỗ nào import `spring-boot-dependencies` và các constraints khác; không khẳng định BOM đang có hiệu lực chỉ vì thấy plugin Spring Boot.

Ở Linux/macOS:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
```

Ở Windows PowerShell/CMD, đổi `./gradlew` thành `.\gradlew.bat`. Lệnh `dependencyInsight` cho thấy version cuối cùng đã resolve, các đường dependency và lý do chọn như constraint/force/conflict (phần hiển thị phụ thuộc Gradle). Lặp cho `spring-security-oauth2-resource-server`, `spring-security-oauth2-jose`, `spring-security-messaging` nếu dự án dùng các module đó.

**Đọc kết quả đúng cách:** nếu build có `requested: 6.2.x` nhưng `selected: 6.3.y`, cần tìm nguồn quản lý thực tế và xác nhận đó là tình trạng dự kiến. Nếu `spring-security-web` = 6.x mà `spring-security-config` = 7.x, coi đây là **rủi ro lệch major**, không lấy build xanh làm bằng chứng an toàn. Khi có multi-module Gradle, chạy ở **đúng module executable/classpath**; graph project root hoặc module library có thể không giống runtime.

### 3.2. Maven: parent/BOM và effective model

Ví dụ phụ thuộc không khai version:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Lệnh đối chiếu:

```bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.security
```

Kiểm tra parent/BOM, `dependencyManagement`, properties như `spring-security.version` (nếu được dùng/override), profile và các dependency khai phiên bản tường minh. Không nhầm version `spring-boot-maven-plugin` với toàn bộ dependency graph; chúng có thể được cấu hình độc lập.

### 3.3. Ghi lại một “version manifest” có chứng cứ

Ví dụ bảng kiểm kê (giá trị `...` là **khung điền**, không phải output của lệnh):

| Thông tin | Nguồn xác minh |
| --- | --- |
| Spring Boot plugin/parent và BOM | Build script, effective POM, dependency constraints |
| Security core/config/web/test từng version | `dependencyInsight` hoặc `dependency:tree` |
| Spring Framework và Java runtime/toolchain | Dependency graph, `java -version`, build image |
| Servlet hay WebFlux | Starters và loại security filter chain |
| Có custom `AuthorizationManager` hay legacy access API | Search project source cho type/import/method |
| Có annotation method security nào đang dùng | Search `@EnableMethodSecurity`, `@PreAuthorize`, `@Secured`, `@RolesAllowed` |
| Kết quả integration test matrix | CI run và tình trạng PASS/FAIL theo endpoint/role |

Lưu manifest với kết quả CI cho **trước và sau upgrade** để phân biệt lỗi compatibility với thay đổi policy dự kiến.

## 4. Tính năng phân quyền cần đối chiếu theo từng tầng

Không hỏi chung “Security 6 có phân quyền không?”, mà cần chia theo tầng:

| Tầng | API/config tiêu biểu | Quyết định gì? | Những điều cần kiểm sau upgrade |
| --- | --- | --- | --- |
| Request Servlet | `HttpSecurity`, `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers` | URL/method/dispatcher hiện tại được qua filter hay không | Thứ tự matcher, đường public, 401/403, ERROR/FORWARD, nhiều chain |
| Request Reactive | `ServerHttpSecurity`, `SecurityWebFilterChain`, `authorizeExchange` | Exchange trên WebFlux được tiếp tục hay không | `pathMatchers`, web filter order, `WebTestClient`, reactive context |
| Method | `@EnableMethodSecurity`, `@PreAuthorize`/`@PostAuthorize`, `@Secured`/`@RolesAllowed` (nếu bật) | Ai được gọi phương thức hoặc nhận giá trị trả về | Annotation có hiệu lực, biểu thức tham số, proxy/self-invocation |
| Programmatic | `AuthorizationManager`, custom authorization bean | Quyết định từ code/nguồn policy | Chữ ký API, fail-closed, trạng thái abstain/deny, exception |
| Object/data | `hasPermission`, service policy, repository predicate/ACL | Có quyền đối với bản ghi cụ thể không | IDOR, tenant isolation, COUNT, search/page, redaction |
| JWT/OAuth2 | Resource server, JWT converter, authorities mapping | Claim/scope nào trở thành `GrantedAuthority` | `SCOPE_*`, `ROLE_*`, issuer/audience validation, claim mapping |
| Test | `spring-security-test`, `MockMvc`/`WebTestClient` | Test đang chạy với security thật hay mock/bypass | Có filter chain, method interceptor, principal/claims đúng |

**Tính năng có mặt trong thư viện ≠ được kích hoạt ≠ xử lý đúng dữ liệu nghiệp vụ.** Ví dụ `hasRole("ADMIN")` kiểm tra authority với tiền tố `ROLE_` theo mặc định; `hasAuthority("ADMIN")` so chính xác tên `ADMIN`. Hai biểu thức không tương đương, đặc biệt sau khi chuyển đổi converter JWT hoặc role hierarchy. Phải kiểm tra `Authentication.getAuthorities()` tại runtime/test với dữ liệu an toàn.

## 5. Chuyển từ Spring Security 5.x sang 6.x

### 5.1. Đường di chuyển ít bất ngờ

1. Với Boot 2.7, dùng Security 5.7 theo BOM; cân nhắc nâng riêng lên **5.8.x** theo hướng dẫn migration chính thức để thay API deprecated, rồi mới nâng Boot 3.0/Security 6.0.
2. Dọn `WebSecurityConfigurerAdapter`, `authorizeRequests`/`antMatchers` legacy, cấu hình method security cũ, các import/namespace và thư viện phụ thuộc.
3. Nâng Java lên **17+**, Spring Framework 6, chuẩn `jakarta.*`, Boot 3/Security 6 theo BOM tương ứng.
4. Chạy test request/method/object permissions, chú ý servlet dispatcher types và thành phần filter/custom security.
5. Sau khi hành vi tương đương mới nâng lần lượt dòng Boot 3.x được dự án hỗ trợ và kiểm tra điểm mới theo từng release.

**Thay đổi thiết kế cấu hình:** Security 5.x thường có code kế thừa `WebSecurityConfigurerAdapter`; Security 6.x sử dụng bean `SecurityFilterChain`. Không thể đổi tên class/DSL cơ học mà bỏ qua độ ưu tiên của các rule.

Mẫu lịch sử **chỉ có ý nghĩa với nhánh legacy**, **không dùng làm mã nguồn cho Security 6/7**:

```java
// Phác họa cấu hình legacy của Spring Security 5.x.
@EnableGlobalMethodSecurity(prePostEnabled = true)
class LegacySecurity extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers("/public/**").permitAll()
            .antMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated();
    }
}
```

Mẫu tương ứng sử dụng bean Security 6.x (giả định Servlet MVC, Java 17+, cần import tương ứng):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Ở mẫu mới, `anyRequest().denyAll()` là chủ đích **mặc định từ chối**; mẫu legacy dùng `anyRequest().authenticated()`. **Hai cấu hình không tương đương đối với tất cả URL** — khi migration sản phẩm thật, phải ghi rõ route nào được tiếp tục bảo vệ bằng authenticated, route nào phải đóng; không âm thầm thay logic theo ví dụ. Đổi từ `hasRole` sang `hasAuthority` phải đi kèm kiểm tra giá trị authority thực tế, không đoán.

`httpBasic` ở đây chỉ là cơ chế authentication để ví dụ tập trung vào authorization. Nếu production dùng JWT/OAuth2, cần cấu hình resource server tương ứng và test converter; không suy luận có Basic Auth từ ví dụ.

### 5.2. Chuyển method security

Trước đây có `@EnableGlobalMethodSecurity(prePostEnabled = true)`; hệ mới dùng `@EnableMethodSecurity` và mặc định bật nhóm pre/post annotations. Nếu trước đây chỉ bật `securedEnabled = true` mà **không bật pre/post**, khi chuyển có thể cần:

```java
// Ví dụ khi muốn giữ đúng lựa chọn chỉ dùng @Secured:
@EnableMethodSecurity(
        securedEnabled = true,
        prePostEnabled = false)
class MethodSecurityConfiguration {}
```

Nếu dự án dùng `@RolesAllowed` hoặc `@PermitAll` qua JSR-250, cần bật cấu hình thích hợp, ví dụ `@EnableMethodSecurity(jsr250Enabled = true)`. **Đừng cho rằng `@EnableMethodSecurity` tự bật mọi loại annotation legacy.** Nhìn lại những annotation đang có và kiểm tra chúng thực sự chặn lời gọi.

Khi biểu thức `@PreAuthorize("hasAuthority('report:read') and #id > 0")` phụ thuộc tên tham số, cần bảo đảm Spring nhận được tên trong bytecode (thường bằng `-parameters`), hoặc chú giải tham số bằng `@P` phù hợp. Đổi compiler flags có thể làm biểu thức không nhận tham số dù mã vẫn biên dịch. Ngoài ra method security qua proxy có thể bị bỏ qua bởi lời gọi nội bộ `this.method()`; phải test đường đi thực tế.

### 5.3. Phân quyền theo dispatcher

Theo hướng dẫn chuyển Boot 3.0/Security 6.0, authorization của Servlet có thay đổi liên quan **các dispatcher type**. Các dispatch `REQUEST`, `ERROR`, `FORWARD` không nên được giả định giống nhau trước/sau migration; ví dụ rendering error page có thể thành 403 nếu cấu hình không cho `ERROR` đi qua. Khi xử lý, dùng đúng rule cho dispatcher cần thiết và **không vô tình mở các request dữ liệu bình thường**. Hãy test cả request gốc lẫn đường error/forward, dùng contract an toàn của ứng dụng làm nguồn chân lý.

## 6. Chuyển từ Spring Security 6.x sang 7.x

Lộ trình được Spring khuyến nghị: cập nhật tới nhánh Boot **3.5.x**/Security **6.5.x**, xử lý bước chuẩn bị cho 7 theo migration guide, sau đó mới nâng Boot **4.x**/Security **7.x**. Nâng major có thể thay cả Spring Framework và hệ sinh thái Jackson, module, matcher, build infrastructure; cần một nhánh upgrade có build/test đầy đủ.

Những điểm **được ghi trong tài liệu Spring Security 7.0** và đặc biệt liên quan đến code phân quyền:

| Điểm chuyển đổi | Dòng Security 6.x | Dòng Security 7.x | Hành động |
| --- | --- | --- | --- |
| AuthorizationManager custom | API `check(...)` đã tồn tại trong 6.x, đồng thời có hướng mới `authorize(...)` | `AuthorizationManager#check` **đã bị loại bỏ**, dùng `authorize(...)` | Search `.check(` trong custom auth/policy integration, sửa theo API mới và test đủ PERMIT/DENY/null |
| Request DSL legacy | `authorizeRequests` còn ở một số nhánh cũ dưới trạng thái deprecated | `authorizeRequests` **đã bị loại bỏ** | Dùng `authorizeHttpRequests` và xác minh matcher/rule priority |
| HttpSecurity chaining | Một số dạng `.and()` legacy còn được hỗ trợ/deprecated ở 6.x | `HttpSecurity` DSL `and()` legacy **đã bị loại bỏ** | Chuyển sang lambda DSL đúng overload |
| Servlet request matcher | Code cũ có thể dùng `AntPathRequestMatcher`/`MvcRequestMatcher` | Các matcher cũ **đã bị loại bỏ**, hướng tới `PathPatternRequestMatcher` | Kiểm tra imports/custom matchers, test path variable/trailing slash/encoding |
| Access decision legacy | `AccessDecisionManager`, voters và config legacy có thể còn hiện diện | API legacy di chuyển sang module `spring-security-access` | Ưu tiên chuyển sang `AuthorizationManager`; nếu giữ legacy, hiểu module hỗ trợ và kế hoạch chuyển |
| Method security | `@EnableMethodSecurity`, `@PreAuthorize` có sẵn | Cơ chế hiện đại tiếp tục được hỗ trợ | Kiểm tra default bật annotation, tham số, proxy, exceptions |
| Phân quyền theo scope/role | `hasAuthority`/`hasRole` | Vẫn phải ánh xạ authorities đúng | Không suy đoán bảo toàn mapping khi chuyển converter/dependency |

Không nên hiểu “Security 7 thêm tính năng mới” thành “mọi dự án phải dùng ngay tính năng đó”. Ví dụ Security 7 bổ sung `AllAuthoritiesAuthorizationManager` và tiện ích kiểm tra “cần tất cả authority”; nó **khác** với `hasAnyAuthority`. Nếu viết điều kiện yêu cầu tất cả scope, phải kiểm tra đúng semantic AND thay vì OR ở mọi version.

**Tìm API bị loại bỏ trước khi nâng:** search toàn bộ code ứng dụng và integration packages cho `WebSecurityConfigurerAdapter`, `authorizeRequests`, `antMatchers`, `AntPathRequestMatcher`, `MvcRequestMatcher`, `AccessDecisionManager`, `AccessDecisionVoter`, `AuthorizationManager#check`/`.check(`, `.and()`. Không phải mọi kết quả tìm thấy đều là security call; cần kiểm tra type/import trước khi sửa. Nếu thư viện thứ ba dùng API bị loại bỏ, nâng thư viện tương thích hoặc cô lập/migrate phù hợp — đừng chỉ thêm một dependency với hy vọng lỗi tự hết.

## 7. Hiểu đúng quyền `hasRole`, `hasAuthority` và JWT scope

Đây là nguồn lỗi “nâng cấp xong đột nhiên 403” hoặc “vô tình cho phép nhiều hơn” rất thường gặp.

- `hasAuthority("report:read")`: so với chuỗi authority **chính xác** được gắn trên Authentication.
- `hasRole("EDITOR")`: trong cấu hình thông thường, đối chiếu với authority `ROLE_EDITOR` (có thể custom default role prefix).
- Scope OAuth2 resource server thường được converter mặc định ánh xạ thành authority dạng `SCOPE_reports.read`; tuy nhiên converter tùy chỉnh có thể khác. Không lấy dữ liệu `scope` trong token rồi tự thêm `ROLE_` nếu chính sách không định nghĩa.
- `hasAnyRole` và `hasAnyAuthority` kiểm tra **một trong nhiều**; không thay nó cho một điều kiện cần **đồng thời** nhiều quyền.

Một chương trình **Java 17+ chạy độc lập** mô phỏng cách phân biệt tiền tố role và authority string. Nó không thay thế evaluator của Spring; mục đích là ghi nhớ sự khác nhau về dữ liệu.

Tạo `AuthorizationNamesDemo.java`:

```java
import java.util.Set;

public class AuthorizationNamesDemo {
    static boolean hasRole(Set<String> granted, String role) {
        return granted.contains("ROLE_" + role);
    }

    static boolean hasAuthority(Set<String> granted, String name) {
        return granted.contains(name);
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
                "ROLE_EDITOR", "SCOPE_reports.read");

        System.out.println("hasRole(EDITOR): "
                + hasRole(granted, "EDITOR"));
        System.out.println("hasAuthority(EDITOR): "
                + hasAuthority(granted, "EDITOR"));
        System.out.println("hasAuthority(SCOPE_reports.read): "
                + hasAuthority(granted, "SCOPE_reports.read"));
        System.out.println("hasRole(REPORTS): "
                + hasRole(granted, "REPORTS"));
    }
}
```

Lệnh:

```bash
javac AuthorizationNamesDemo.java
java AuthorizationNamesDemo
```

Stdout chính xác:

```text
hasRole(EDITOR): true
hasAuthority(EDITOR): false
hasAuthority(SCOPE_reports.read): true
hasRole(REPORTS): false
```

Trong ứng dụng Spring thật, phải quan sát bộ `GrantedAuthority` của principal đã xác thực trên **môi trường test**, và test cả `ROLE_EDITOR`/`SCOPE_reports.read` khi custom JWT converter thay đổi. Chỉ vì biến `roles` trong token chứa `EDITOR` không có nghĩa `hasRole("EDITOR")` chắc chắn hoạt động: cần kiểm tra converter và convention của hệ thống.

## 8. Servlet, WebFlux và request matcher không thể đánh đồng

Hai stack có API và test khác nhau:

| Thành phần | Spring MVC/Servlet | Spring WebFlux/Reactive |
| --- | --- | --- |
| HTTP security | `HttpSecurity`, `SecurityFilterChain` | `ServerHttpSecurity`, `SecurityWebFilterChain` |
| Rule theo request | `authorizeHttpRequests(...)` | `authorizeExchange(...)` |
| URL matching | `requestMatchers(...)` hoặc matcher hiện hành của version | `pathMatchers(...)`/`ServerWebExchangeMatcher` phù hợp |
| Bản chất request | `HttpServletRequest` và dispatcher/filter chain | `ServerWebExchange` và Reactor context/web filters |
| Test HTTP authorization | `MockMvc` + `spring-security-test` | `WebTestClient` + reactive security test support |
| Context | Servlet/thread/request context liên quan | Reactive `Context`, propagation theo pipeline |

Không copy `SecurityFilterChain` sang WebFlux với kỳ vọng hoạt động; cũng không dùng `@WebMvcTest` để chứng minh reactive security. Khi dependencies có cả web starter và webflux starter, cần xác định **application type thực tế** đang chạy.

Đối chiếu matcher khi nâng major:

1. Có nhiều `SecurityFilterChain` với `@Order` hay `securityMatcher`? Rule và chain được chọn phải đúng.
2. Đường dẫn `/admin`, `/admin/`, `/admin/42`, encoding/URL normalization, đường chứa dấu phân tách đặc biệt có match như trước không?
3. `requestMatchers(HttpMethod.GET, ...)` khác với matcher mọi method; một route đọc public không tự cho phép POST ghi.
4. Nếu có reverse proxy, context-path, servlet-path, forwarded headers, cần test đường mà ứng dụng thực sự nhận được.
5. Sau chuyển sang `PathPatternRequestMatcher` theo Spring Security 7, không giả định cú pháp và đặc tính mọi Ant/MVC matcher giữ nguyên; viết test phủ positive + negative boundary.

Bất kỳ cấu hình `permitAll()` mới nào cũng phải được review vì có thể làm lộ endpoint nhạy cảm; tránh “sửa cho test xanh” bằng `anyRequest().permitAll()` hay tắt security filters.

## 9. Quy trình migration có kiểm soát

### Bước 1 — Chốt baseline và phạm vi

Ghi Boot/Security **đang chạy thật** và Java/Spring Framework; xác định ứng dụng Servlet/Reactive, authentication mechanism (session, Basic, JWT, opaque token, mTLS), method security và các policy theo dữ liệu. Tạo bảng endpoint → HTTP method → loại principal → authority/tenant/owner → expected status và side effect. Lấy cả endpoint public lẫn endpoint nhạy cảm làm đối chứng.

### Bước 2 — Lập diff phiên bản

So bảng BOM trước/sau; ghi artifact nào đổi major/minor. Đọc release notes **đúng các dòng đi qua**, không chỉ đọc trang bản đích. Dùng migration guide theo chặng: 2.7→3.0/5.8→6.0 và 3.5→4.0/6.5→7.0 khi có liên quan. Kiểm tra các thư viện hỗ trợ OAuth, JWT, SAML, OpenAPI, Spring Cloud, session, actuator có tương thích hay không.

### Bước 3 — Chuyển API và giữ semantic quyền

Sửa code deprecated/removed, nhưng **giữ hợp đồng phân quyền trước đó** trừ khi nghiệp vụ cho thay. Mỗi rule phải được đánh dấu tương đương hoặc thay đổi có phê duyệt: `authenticated` khác `permitAll`, `hasRole` khác `hasAuthority`, `hasAny...` khác `hasAll...`, chỉ kiểm tra request khác với kiểm tra object.

Tình huống trước/sau dễ nhầm:

```text
Trước:  GET /api/reports/42
        USER alice, authority report:read, owner=bob  -> 403

Sau:    requestMatchers("/api/reports/**").hasAuthority("report:read")
        -> cho qua request-level, nhưng nếu bỏ luôn object check
           ở service thì alice có thể đọc báo cáo của bob.

Yêu cầu tương đương:
        request-level có authority + service/repository kiểm tra owner/tenant,
        hoặc AuthorizationManager/policy tương đương chạy trước khi trả dữ liệu.
```

**Biên giới dữ liệu** không tự phục hồi sau khi đổi API filter. Nếu repo có chính sách multi-tenant hoặc row-level ACL, cần test truy vấn dữ liệu, `totalElements` phân trang, field redaction và side effects theo principal.

### Bước 4 — Cấu hình test đúng phiên bản

Chọn `spring-security-test` cùng dòng được BOM quản lý; bảo đảm `MockMvc`/`WebTestClient` bật security chain. Một unit test tự tạo service với mock principal không phát hiện matcher đổi; ngược lại, một test chỉ request không xác nhận `@PreAuthorize` bảo vệ service khi gọi qua đường khác.

Ví dụ **phác thảo test tích hợp Spring Boot 3.x + Security 6.x** (cần application context, controller `/api/reports/**`, security config, dependencies JUnit/Spring Test và import tương ứng):

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationIT {
    @Autowired MockMvc mvc;

    @Test
    void anonymousCannotReadReport() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanReachPermittedEndpoint() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void missingAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void unknownRouteIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/not-configured"))
                .andExpect(status().isForbidden());
    }
}
```

Kỳ vọng 401 cho anonymous phụ thuộc authentication entry point (trong ví dụ là Basic), cũng như endpoint thực tế phải trả 200 khi `report:read` **và** resource policy cho phép. Nếu ứng dụng có kiểm tra owner/tenant, fixture phải cho người đọc sở hữu 42 hoặc đổi kỳ vọng phù hợp; không mock bỏ policy chỉ để ép 200. Với JSON error handler riêng, response body có thể khác. Đoạn trên là **minh họa trong ứng dụng có đủ bean/config**, không phải chương trình Java độc lập. Không có body/DB fixture nên cần bổ sung integration test data-level riêng cho hệ thống thật.

### Bước 5 — Test ma trận trước/sau

| Principal/tình huống | Request | Kỳ vọng minh họa | Điều cần chứng minh |
| --- | --- | --- | --- |
| Anonymous | GET public | 200 | Chỉ route public được cấp quyền |
| Anonymous | GET protected | 401 hoặc entry point theo cấu hình | Không có dữ liệu/side effect |
| Authenticated không đủ authority | GET protected | 403 | Không nhầm `authenticated` thành đủ quyền |
| Có authority nhưng sai owner | GET /documents/{id} | 403/404 theo policy | Object-level policy không bị bỏ qua |
| Có authority và đúng owner | GET /documents/{id} | 200 | Quyền hợp lệ được phục vụ |
| ADMIN tenant A | GET tài liệu tenant B | 403/404 | Không mở quyền cross-tenant |
| Authenticated thiếu CSRF token ở trình duyệt sử dụng session | POST/DELETE cần CSRF | 403 (nếu CSRF được áp dụng) | Không xóa CSRF vô tình trong migration |
| FORWARD/ERROR path | Đường điều phối nội bộ | Theo chính sách đã đặc tả | Không lộ dữ liệu hay gây vòng lỗi |
| JWT đúng signature nhưng scope thiếu | GET scope-protected | 403 | Converter authorities + scope đúng |
| PDP/custom auth lỗi | GET protected | Chặn an toàn, 403/503 theo policy | Không fallback sang PERMIT |

Kết quả cần so sánh **cả trước và sau** nâng cấp. Nếu trạng thái thay đổi, phân loại rõ là sửa lỗi, intentional policy change hay regression. Không dùng thông điệp HTTP 403 làm bằng chứng toàn bộ method security hoạt động; các test nên có ít nhất một đường chạm trực tiếp service qua Spring bean và kiểm tra dữ liệu/side effects.

### Bước 6 — Xác nhận chạy thật và ghi lại baseline mới

Ở CI, chạy test kiểm tra request/method/object quyền trong cấu hình tương ứng production, dependencyInsight/dependency:tree, compile + package, test deploy environment; xác nhận response headers, trạng thái 401/403, audit decision và độ bao phủ đường đi. Nếu đổi Servlet container, Jakarta, JWT decoder, path matcher hoặc filter order, phải chạy test trên HTTP layer thật trước khi kết luận hoàn tất. Lưu kết quả kèm version manifest để lần nâng tiếp theo có thể so sánh.

## 10. Các lỗi thường gặp khi đối chiếu phiên bản

| Sai lầm | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Nhìn version plugin Boot để đoán mọi bản Security | Dependency có thể bị override/transitive/constraint | Đọc dependency graph **từng artifact** của module chạy |
| Gắn `spring-security-web` 7.x vào Boot 3.x nhưng giữ config 6.x | Có thể lệch API, Framework, module | Dùng đường phiên bản được hỗ trợ; test stack trọn vẹn |
| Sao chép `WebSecurityConfigurerAdapter`/`antMatchers` lên Boot 3/4 | API bị thay thế/loại bỏ | Chuyển `SecurityFilterChain`/matcher hiện hành |
| Chuyển `authorizeRequests` sang `authorizeHttpRequests` mà đổi semantic | Endpoint public/private thay đổi | So từng matcher, method và fallback |
| Không bật `@EnableMethodSecurity` | `@PreAuthorize` không được thực thi | Bật đúng annotation + test qua Spring bean/proxy |
| Nhầm `hasRole("ADMIN")` với `hasAuthority("ADMIN")` | Prefix `ROLE_` khác nhau | Đối chiếu `GrantedAuthority` thực |
| Chỉ kiểm tra biên dịch, không kiểm 401/403 | API compile nhưng matcher/dispatch khác | HTTP integration tests theo ma trận |
| Chỉ bảo vệ URL, bỏ kiểm owner/tenant | IDOR, xuyên tenant dù endpoint có role | Test object/data-level query và service |
| Giữ `AuthorizationManager#check` sau nâng 7.x | API bị loại bỏ | Chuyển `authorize`, test custom manager |
| Copy Servlet DSL sang WebFlux | Sai kiểu filter/matcher/context | Dùng `SecurityWebFilterChain`/`authorizeExchange` và test reactive |
| Dùng mock bỏ qua security filters | Test xanh giả | Chạy security filter chain, test method proxy và policy thật |
| Tắt CSRF/permitAll khi bị test 403 | Mở quyền ngoài chủ đích | Điều tra khác biệt theo request/token/policy |

## 11. Checklist hoàn thành bài

Một kết luận “Spring Boot X sử dụng được tính năng phân quyền Y với Spring Security Z” chỉ đủ căn cứ khi trả lời được:

- **Version:** biết bản Boot/BOM và version resolve của `spring-security-core`, `config`, `web`, `test` cùng các module liên quan; không lệch major ngoài thiết kế.
- **Capability:** API có mặt ở dòng Security đó và không nằm trong danh sách removed; nếu là deprecated, có lộ trình thay thế.
- **Activation:** bean `SecurityFilterChain`/`SecurityWebFilterChain`, method security, JWT converter và policy services được bật tại đúng lớp ứng dụng.
- **Semantic:** matcher, dispatch, role/authority prefix, URL/method, object/tenant policy và hành vi fail-closed đúng với hợp đồng.
- **Evidence:** có test phân biệt public/anonymous/no-role/valid-role/cross-tenant, có data-level checks và bản ghi dependencyInsight/dependency:tree.
- **Migration:** đối chiếu migration guide của từng major, Java/Jakarta, custom managers/matchers, thư viện tích hợp và hành vi endpoint sau thay đổi.

**Điểm cốt lõi:** bảng tương thích chỉ cho biết điểm xuất phát. Kết quả phân quyền thực tế phụ thuộc vào **dependency được resolve + cấu hình đã kích hoạt + ngữ nghĩa policy + test hành vi của ứng dụng**.

## Tài liệu chính thức để tra cứu theo phiên bản

1. [Spring Boot — Managed Dependency Coordinates (bản đang được xuất bản)](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html). Đổi URL tài liệu sang **dòng Boot cụ thể** để đọc đúng phiên bản, ví dụ [3.5](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html) và [4.0](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html).
2. [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17, Jakarta, Spring Security 6, authorization dispatcher.
3. [Spring Security 6.0 Migration Guide](https://github.com/spring-projects/spring-security/wiki/Spring-Security-6.0-Migration-Guide): chuẩn bị qua Security 5.8.
4. [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): chuẩn bị từ 3.5 và các thay đổi hệ sinh thái.
5. [Spring Security — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/index.html) và [Spring Security 7.0 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html): thay đổi authorization APIs/matchers và loại bỏ API cũ.
6. [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) và [Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): luật request, `AuthorizationManager`, `@EnableMethodSecurity`, biểu thức role/authority.
