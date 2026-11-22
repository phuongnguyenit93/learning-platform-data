# Loại bỏ API lỗi thời sau khi bộ kiểm thử hồi quy xác nhận hành vi

> **Bối cảnh:** nâng cấp ứng dụng **Spring Security Servlet** trên Java 17+, Spring Boot 3.x / Spring Security 6.x. Mục đích không đơn thuần là làm hết cảnh báo `deprecated`: phải **giữ nguyên hành vi bảo mật đã được chấp thuận** khi thay API cấu hình, method security, request matcher hoặc quản lý SecurityContext. Thứ tự bắt buộc là **đặc tả hành vi → kiểm thử hồi quy xanh trên bản cũ → thay API theo từng bước nhỏ → chạy lại và phân tích chênh lệch → chỉ lúc đó mới xóa đường cũ**. Các ví dụ phiên bản trong bài minh họa một nhánh framework cụ thể, không khẳng định đó là bản mới nhất tại thời điểm đọc.

## 1. Tại sao “hết deprecated” vẫn có thể làm ứng dụng kém an toàn?

Một thay đổi tưởng như chỉ là cú pháp:

```java
// Cú pháp cũ, minh họa lịch sử của Spring Security
http.authorizeRequests()
    .antMatchers("/admin/**").hasRole("ADMIN");
```

chuyển sang:

```java
// Cú pháp lambda trong Spring Security 6.x
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
```

có thể kéo theo thay đổi **semantics** hoặc làm lộ cấu hình sai đã tồn tại:

- Quy tắc matcher đầu tiên áp dụng cho URL nào, với servlet path/context path hay HTTP method nào?
- Các request khác `/admin/**` có còn `authenticated()`, hay vô tình được phép khi không có rule cuối?
- Dữ liệu authority có đúng `ROLE_ADMIN` hay bị map sai sau nâng cấp?
- Trang login/logout/error có được truy cập ở trạng thái anonymous?
- CSRF vẫn bảo vệ POST/PUT/PATCH/DELETE không?
- Phiên sau form login có tiếp tục hoạt động, cookie session còn nguyên flags, redirect còn đúng?
- Endpoint JSON/API trả 401, 403 hay 302 như hợp đồng cũ?
- Method-security annotations vẫn được chặn qua proxy, kể cả khi gọi service từ luồng khác?
- Filter ordering, exception translation và SecurityContext persistence có thay đổi không?

**Một build biên dịch thành công không chứng minh chính sách xác thực/phân quyền không bị thay đổi.** Cần bộ test đo đúng hành vi bên ngoài và các side effects, không chỉ test class/config có khai báo những method tên mới.

## 2. Bốn loại thay đổi phải phân biệt

| Loại | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| **Deprecated API** | Vẫn còn nhưng tác giả framework khuyến nghị thay thế | Đọc hướng dẫn migration đúng phiên bản; thiết lập regression baseline trước |
| **Removed API** | Đã không còn ở dependency target, mã cũ không compile | Nâng cấp theo chặng tương thích hoặc chuyển API có kiểm soát, không tắt test |
| **Behavioral change** | API mới compile nhưng matcher/filter/session/exception có semantics khác | Viết characterization tests và so sánh hành vi thực |
| **Security policy change có chủ đích** | Muốn siết chặt rule, CSRF, session hay role | Tách thành thay đổi riêng, cập nhật yêu cầu/acceptance test và được phê duyệt |

**Không trộn lẫn** “refactor để hết deprecated” với “đổi chính sách bảo mật”. Ví dụ chuyển từ `permitAll("/health")` sang yêu cầu xác thực cho `/health` là thay đổi behavior; có thể là đúng theo yêu cầu mới, nhưng không được lén đi cùng commit xóa API cũ rồi gọi đó là migration tương đương.

## 3. Nguyên tắc vàng: test trước khi thay API

Với mỗi API cũ, lập **hợp đồng hành vi** gồm:

1. **Input:** HTTP method/path/host, principal, authorities, cookie, CSRF, origin, session, dispatch type.
2. **Output:** status 200/302/401/403, body error, `Location`, `Set-Cookie`, security headers.
3. **Side effects:** session rotation, invalidation, repository call, audit event, ghi dữ liệu, request cache.
4. **Boundary:** anonymous, user sai role, user đúng role, token hết hạn, cùng/khác tenant, account disabled.
5. **Môi trường:** test Servlet filter chain thật, path context, proxy HTTPS, browser nếu cookie/SameSite quan trọng.
6. **Quyết định:** giữ behavior hay thay đổi có chủ đích? Ai là owner phê duyệt thay đổi?

Chạy test trên **phiên bản đang hoạt động** để thu baseline đã được review. Tới lúc thay API, cùng bộ tests phải pass mà không làm yếu assertion. Nếu test cũ đang fail, ghi nhận chính xác nguyên nhân trước khi sửa; không gọi build đang đỏ là regression baseline đáng tin.

### 3.1. Test xấu và test tốt

Test yếu:

```java
// Test này chỉ đọc một bean, không chứng minh quyền truy cập:
assertThat(securityFilterChain).isNotNull();
```

Test có giá trị:

```java
mvc.perform(get("/admin/report")
        .with(httpBasic("alice", "alice-pass")))
    .andExpect(status().isForbidden());
```

Test thứ hai chứng minh user thiếu `ROLE_ADMIN` thật sự bị từ chối qua Spring Security HTTP filter chain. Test còn cần ca **được phép** với admin và ca **anonymous**; chỉ test âm tính hoặc chỉ test thành công đều không đủ.

**Không “làm xanh test” bằng cách xóa negative cases, thay `403` thành `anyStatus`, mock bỏ qua SecurityFilterChain hoặc tắt CSRF.** Nếu cần thay expected result do policy mới, phải có quyết định được ghi nhận riêng.

## 4. Kiểm kê API cũ trước khi viết migration

### 4.1. Xác định phiên bản framework thực tế

Với Gradle Wrapper:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration compileClasspath
```

Dùng `./gradlew.bat` tương ứng trên Windows PowerShell. Đọc phiên bản từ **dependency resolution**, không suy đoán chỉ từ `build.gradle` nếu project có BOM/plugin khác.

Ghi:

- Java version, Spring Boot version, Spring Security artifacts và version resolution.
- Servlet stack (`jakarta.servlet` ở Boot 3) hay reactive WebFlux. Bài này **chỉ xử lý Servlet**.
- Có bao nhiêu `SecurityFilterChain`, `@Order` và `securityMatcher`?
- Những authentication mechanisms: form, HTTP Basic, OAuth2 login, OIDC, resource server, LDAP, remember-me, custom provider?
- Custom `Filter`/`AuthenticationProvider`/`AuthenticationSuccessHandler`/`SecurityContextRepository` nào phụ thuộc API cũ?
- Method security đang bật qua annotation/config nào?
- Có reverse proxy/Ingress, session store đa node, Redis/JDBC, CORS, SameSite và CSRF đặc thù không?

### 4.2. Tìm các dấu hiệu legacy một cách có giới hạn

Ví dụ tìm trong mã nguồn **của dự án bạn**, không phải chạy trong thư mục dependency/vendor:

```bash
rg -n 'WebSecurityConfigurerAdapter|authorizeRequests|antMatchers|mvcMatchers|regexMatchers' src
rg -n 'EnableGlobalMethodSecurity|GlobalMethodSecurityConfiguration|access\\(' src
rg -n 'SecurityContextPersistenceFilter|SecurityContextHolderFilter|SessionCreationPolicy' src
rg -n 'csrf\\(\\)|headers\\(\\)|httpBasic\\(\\)|formLogin\\(\\)|logout\\(\\)' src
```

Lệnh `rg` cần ripgrep được cài; một số mẫu có ký tự escape tùy shell. **Kết quả chỉ là ứng viên**, không phải tất cả deprecated symbols: có thể là comment, string, code test hoặc API của một thư viện khác. Với dự án lớn, cần tìm cả module con và generated/config files có chủ đích.

Bật cảnh báo compiler trên Java:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-Xlint:deprecation')
}
```

Với Gradle, xem cảnh báo compilation và plugin deprecation riêng; warning từ Gradle DSL **không đồng nghĩa** deprecated Spring Security Java API. Nếu muốn biến warnings thành build failure về sau, tách thành một gate riêng **sau** khi baseline đã được chấp thuận, không bật `-Werror` quá sớm khiến không thể đối chiếu.

### 4.3. Lập bảng migration inventory

| Cấu phần | API/hành vi hiện tại | API đích | Nguy cơ | Test bảo vệ |
| --- | --- | --- | --- | --- |
| HTTP configuration | `WebSecurityConfigurerAdapter` | Bean `SecurityFilterChain` | Mất authentication manager/filter chain | Basic/form login + negative auth |
| Authorization DSL | `authorizeRequests` | `authorizeHttpRequests` | Thứ tự rule, semantics và exception mapping | Matrix 200/302/401/403 |
| URL matcher | `antMatchers`/`mvcMatchers` | `requestMatchers` hoặc explicit `RequestMatcher` | Path/context/servlet method khác | Wildcards, URL encoding, methods |
| Method security | `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Annotation không chạy hoặc policy khác | Proxy-backed service tests |
| SecurityContext handling | Tự đặt authentication | Context repository / flow phù hợp | Mất phiên sau redirect | Login + request kế tiếp |
| HTTP DSL config | Tham sốless chain methods cũ | Lambda DSL phù hợp version | Defaults/setting bị bỏ | CSRF, headers, logout |
| Error dispatch | Custom filtering | Dispatcher/error policy hiện hành | Lỗi thành redirect loop | Test 500/ERROR dispatch |

Đọc Javadoc và migration guide tương ứng **source version → target version**; không ghép lời khuyên của nhiều major versions thành một cú pháp giả định.

## 5. Những thay thế phổ biến trong Spring Security Servlet

### 5.1. WebSecurityConfigurerAdapter → các bean cấu hình rõ ràng

Trong các project Spring Security cũ, người ta subclass `WebSecurityConfigurerAdapter`. API này không phải đường cấu hình thông thường trong Spring Security 6; thay bằng bean `SecurityFilterChain`, cộng những bean authentication/user/password cần thiết.

Ví dụ kiểu legacy, **không biên dịch trong Boot 3 / Security 6**:

```java
// Ví dụ lịch sử từ đời framework cũ; KHÔNG chạy với Spring Security 6.
public class LegacySecurity extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers("/public").permitAll()
            .anyRequest().authenticated()
            .and().httpBasic();
    }
}
```

Cấu hình hiện đại theo bean:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

**Không coi hai đoạn tương đương chỉ vì giống tên URL.** Phải kiểm tra thứ tự matcher, ứng dụng nhiều chains, exception response, CSRF và authentication provider, đặc biệt nếu bản cũ có override `configure(AuthenticationManagerBuilder)`/`configure(WebSecurity)`. Khi chuyển sang bean composition, dependency injection và config precedence có thể khác.

### 5.2. authorizeRequests/antMatchers → authorizeHttpRequests/requestMatchers

Ví dụ trước (historical):

```java
// Mẫu API cũ để đối chiếu, không dùng làm ví dụ compile mới:
http.authorizeRequests()
    .antMatchers("/public/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

Ví dụ sau:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

**Kiểm tra behavior thay vì chỉ đổi tên:**

- Một matcher có bắt `/admin`, `/admin/`, `/admin/report` giống dự kiến không?
- Context path và servlet path có ảnh hưởng không?
- HTTP method có được giới hạn đúng nếu từng dùng matcher theo method?
- Encoded slash, percent encoding, semicolon, path traversal được `HttpFirewall` xử lý ra sao?
- Thứ tự rule **từ cụ thể đến tổng quát** có giữ nguyên không?
- Rule cuối `anyRequest().authenticated()` có bị bỏ mất?
- Dùng MVC trên Servlet và chọn cơ chế matcher tương ứng: `requestMatchers(String...)` là API tiện dụng, nhưng hành vi thực phụ thuộc request matcher/config/version. Nếu phải giữ semantics đặc thù, dùng `RequestMatcher` tường minh và test ở môi trường Servlet thực.

Không khuyên sao chép chuỗi Ant patterns cũ nguyên xi rồi tin rằng mọi edge case đều giống. Nếu path matching là một phần quan trọng của business access control, viết **bảng test path/method** trước khi đổi.

### 5.3. Lambda DSL cho csrf, httpBasic, formLogin, logout

Các dạng chain-style tham sốless cũ dễ gặp trong code đã nâng cấp qua nhiều đời:

```java
// Mẫu style cũ; một số method/no-arg entry points đã bị deprecate:
http.csrf().disable();
http.httpBasic();
http.formLogin();
```

Khi thay bằng lambda DSL, ý định phải rõ:

```java
http.httpBasic(Customizer.withDefaults());
http.formLogin(Customizer.withDefaults());

// Chỉ khi có chính sách CSRF cụ thể:
http.csrf(csrf -> csrf
        .ignoringRequestMatchers("/webhook/verified"));
```

**Không đưa `csrf(csrf -> csrf.disable())` vào cấu hình chỉ để bắt chước legacy mà không kiểm toán security model.** Cả code cũ và code mới có thể cho kết quả biên dịch nhưng khác kỳ vọng bảo mật. Với session/cookie authentication, CSRF thường cần được giữ; trường hợp webhook/bearer-token riêng cần đánh giá theo trust model và endpoint.

Ví dụ logout rõ ràng:

```java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/login?logout")
        .permitAll());
```

Nếu dùng CSRF mặc định, logout thường cần **POST** và CSRF token; không đổi thành GET logout để tránh test 403. Test logout phải xác minh session không còn quyền, cookies/remember-me được xử lý đúng, chứ không chỉ redirect thành công.

### 5.4. @EnableGlobalMethodSecurity → @EnableMethodSecurity

Ở các phiên bản cũ:

```java
// Cấu hình lịch sử, không phải cách mới:
@EnableGlobalMethodSecurity(prePostEnabled = true)
```

Trong Spring Security 6:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Tuy nhiên, **không chỉ xem annotation đã đổi**. Cần test:

- `@PreAuthorize` chặn trước method body chạy khi thiếu quyền.
- `@PostAuthorize` từ chối kết quả sau method nhưng method body có thể đã thực thi; không dùng post authorize để bảo vệ thao tác có side effects.
- Rule dùng `#parameter` có còn parameter name discovery đúng? Có cần `@P` hoặc compiler flag `-parameters` không?
- Bean service có được gọi **qua Spring proxy** hay là `new Service()`/self-invocation `this.securedMethod()` làm bỏ interceptor?
- `@Secured`, JSR-250 annotations hoặc permission evaluator có được bật theo nhu cầu không? Không suy ra mọi loại annotation được enable chỉ bởi một flag bất kỳ.
- Role mapping `ROLE_` và OAuth/JWT authorities có giữ semantics cũ?

Ví dụ biểu thức:

```java
@PreAuthorize("hasRole('ADMIN') or (isAuthenticated() and #owner == authentication.name)")
public String readOwner(@P("owner") String owner) {
    return "profile:" + owner;
}
```

Ở đây `@P` thuộc `org.springframework.security.core.parameters.P`. Test user `alice` đọc owner `bob` phải bị từ chối; đừng chỉ test admin luôn pass.

### 5.5. SecurityContextHolderFilter và explicit context save

Một custom filter cũ có thể thiết lập:

```java
SecurityContextHolder.getContext()
        .setAuthentication(authentication);
```

Trong cơ chế Spring Security 6 sử dụng `SecurityContextHolderFilter` và yêu cầu explicit save theo cấu hình, **chỉ set ThreadLocal không chứng minh request kế tiếp có authentication**. Nếu flow custom cần session persistence, hãy tạo context và lưu theo hợp đồng `SecurityContextRepository` phù hợp sau khi đã xác thực credential thật:

```java
// Snippet kiến trúc: chỉ dùng sau khi authentication provider tin cậy xác thực.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

Đoạn trên cần các biến và imports của một custom authentication flow, **không phải chương trình độc lập**. Không dùng nó để tự cấp quyền cho username từ request. Nếu đang dùng `formLogin()`, HTTP Basic, OAuth2/OIDC login chuẩn, ưu tiên để framework quản lý context theo flow chính thống.

**Regression test quyết định:** login qua socket HTTP + cookie jar, rồi gửi request thứ hai: `GET /me` phải còn xác thực nếu hợp đồng là session-based. Unit test chỉ kiểm `SecurityContextHolder.getContext()` trong cùng thread không đủ.

### 5.6. Đừng đánh đồng “mới” với “an toàn hơn” nếu cấu hình bị nới

Một số thay đổi có thể làm test pass bằng cách bỏ lớp bảo vệ:

```java
// Không dùng làm mẹo migration:
http.csrf(csrf -> csrf.disable());
http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
```

Các cấu hình này cần justification security rất mạnh theo thiết kế, không thể là cách mặc định thay API cũ. Migration hợp lệ phải giữ nguyên hoặc **siết chặt có chủ đích** security policy được chấp thuận, không xóa negative tests để tránh lỗi.

## 6. Xây dựng bộ regression test theo hợp đồng bảo mật

### 6.1. Các lớp test cần có

| Lớp kiểm thử | Công cụ | Mục đích |
| --- | --- | --- |
| Unit policy | JUnit + Mockito | Test logic nghiệp vụ và permission calculator; không tự xác minh security proxy/filter |
| Method security | `@SpringBootTest`, `@WithMockUser` | Test `@PreAuthorize`/`@PostAuthorize` qua Spring-managed proxy |
| Web MVC security | `MockMvc` + `spring-security-test` | Test request matcher, authentication entry point, CSRF, authorization, error mapping |
| Real Servlet HTTP | `@SpringBootTest(RANDOM_PORT)` + Java `HttpClient` | Test cookie, redirect, session persistence, form login qua socket |
| Reverse proxy/TLS | Nginx/Ingress staging, HTTP client | Test external host/scheme/prefix, forwarded headers, Secure cookie |
| Browser E2E | Playwright/Selenium | Test SameSite/cookie acceptance, cross-origin, navigation và IdP callback |

Không nhất thiết mọi pull request chạy toàn bộ cross-browser suite, nhưng với thay đổi liên quan session/cookie/proxy thì **MockMvc đơn lẻ không đủ**. Nếu legacy behavior phụ thuộc servlet path, cần real Servlet requests có path/dispatcher types tương ứng.

### 6.2. Ma trận hành vi HTTP tối thiểu

| Actor và request | Hành vi mong muốn | Điểm migration phải giữ |
| --- | --- | --- |
| Anonymous `GET /public` | 200 | Đường public vẫn public |
| Anonymous `GET /private` với Basic | 401 + Basic challenge | Entry point/API contract |
| Basic user thường `GET /private` | 200 | Authentication provider được nối đúng |
| User thường `GET /admin/report` | 403 | Không bypass role check |
| Admin `GET /admin/report` | 200 | Role mapping đúng |
| Sai password `GET /private` | 401 | Không tự xem credential sai là anonymous được permit |
| User thường `POST /settings` thiếu CSRF | 403 trong session-based web config | CSRF không bị tắt |
| User thường `POST /settings` với CSRF | 200/redirect theo API contract | Form/CSRF repository đúng |
| Anonymous `POST /settings` | 401/302 theo entry point và policy | Không được thao tác chỉ vì có CSRF |
| `GET /error` hoặc ERROR dispatch | Error policy phù hợp | Không tạo login redirect loop |
| Login form/session: POST rồi GET | User vẫn authenticated | SecurityContext/cookie persistence |
| Logout rồi GET private | Bị yêu cầu login | Session invalidate/cleanup |
| Same user gọi resource tenant khác | 403 hoặc 404 theo security policy | Object-level authorization |
| OAuth2 login callback fail/state mismatch | Login thất bại an toàn | Không bỏ state/code validation |
| CORS preflight hợp lệ | Response theo allowlist | Không mở `*` tùy tiện với credentials |

Các status ví dụ trên có thể thay đổi theo `AuthenticationEntryPoint`: **form login thường redirect 302** cho anonymous, trong khi HTTP Basic thường 401. Trước khi đổi expected status phải xác định cơ chế hiện có và contract thật; không “chuẩn hóa” tất cả thành 403.

### 6.3. Test cả kết quả được phép và bị từ chối

Một yêu cầu tốt gồm ít nhất:

- **Positive test**: user có role/authority phù hợp truy cập thành công.
- **Negative test**: user cùng trạng thái authenticated nhưng thiếu quyền bị từ chối.
- **Anonymous test**: chưa login không đọc được dữ liệu cần xác thực.
- **Cross-user/object test**: user A không thể truy cập object của B dù URL/ID đoán được.
- **CSRF test**: unsafe method thiếu token không được đi qua.
- **Session test**: sau login có session đúng, sau logout/session expiry không còn quyền.
- **Error/redirect test**: trang lỗi không gây loop, entry point đúng theo browser/API.
- **Path boundary test**: trailing slash, servlet context, prefix, HTTP method và URL encoding không làm đổi rule ngoài ý muốn.

Test chính xác **lý do** denied khi cần, không chỉ status: 403 có thể do CSRF, method security, URL authorization hoặc business validation. Có thể có hai positive/negative tests ở tầng khác nhau để cô lập nguồn lỗi.

## 7. Demo chạy được: cấu hình hiện đại và kiểm thử hồi quy với Spring Boot 3.4

Phần này tạo project Servlet nhỏ với **Spring Boot 3.4.2 + Java 17** để kiểm tra behavior trước/sau khi thay một cấu hình legacy tương ứng. Dùng Gradle Wrapper nếu dự án đã tạo bằng Spring Initializr. Không chạy các đoạn API historical trên version mới; chúng chỉ dùng để so sánh.

### 7.1. Cấu trúc project

```text
security-upgrade-regression/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/upgrade/
    │   ├── UpgradeApplication.java
    │   ├── SecurityConfig.java
    │   ├── AdminTaskService.java
    │   └── DemoController.java
    └── test/java/com/example/upgrade/
        ├── SecurityHttpRegressionTest.java
        └── MethodSecurityRegressionTest.java
```

### 7.2. Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'security-upgrade-regression'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
    options.compilerArgs.add('-Xlint:deprecation')
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Phần `-parameters` hỗ trợ parameter-name discovery khi có biểu thức SpEL theo tham số. `-Xlint:deprecation` chỉ tạo cảnh báo compiler; nó không tự khẳng định behavior đã đúng. Dự án demo dùng syntax Spring Security 6.x, không import lớp bị loại bỏ.

### 7.3. Application

Tệp `src/main/java/com/example/upgrade/UpgradeApplication.java`:

```java
package com.example.upgrade;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UpgradeApplication {
    public static void main(String[] args) {
        SpringApplication.run(UpgradeApplication.class, args);
    }
}
```

### 7.4. SecurityConfig

Tệp `src/main/java/com/example/upgrade/SecurityConfig.java`:

```java
package com.example.upgrade;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.PasswordEncoder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error")
                            .permitAll()
                        .requestMatchers("/admin/**")
                            .hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Chính sách demo:**

- `/public` có thể gọi anonymous.
- `/admin/**` chỉ cho `ROLE_ADMIN`.
- Các URL còn lại cần authentication.
- HTTP Basic là entry point của ví dụ; unauthorized thường trả 401 thay vì form login 302.
- CSRF vẫn bật mặc định: POST thiếu CSRF token bị chặn. Với API stateless bearer token, CSRF policy cần thiết kế riêng; **không áp nguyên mẫu Basic này lên mọi kiến trúc**.
- `@EnableMethodSecurity` bật interceptor `@PreAuthorize`.
- User/password mẫu chỉ dùng local test, không đưa credential này vào môi trường production.

### 7.5. Service method security và side effect có thể đếm

Tệp `src/main/java/com/example/upgrade/AdminTaskService.java`:

```java
package com.example.upgrade;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class AdminTaskService {

    private final AtomicInteger invoked = new AtomicInteger();

    @PreAuthorize("hasRole('ADMIN')")
    public String performAdminTask() {
        invoked.incrementAndGet();
        return "admin-ok";
    }

    @PreAuthorize("""
            hasRole('ADMIN') or
            (isAuthenticated() and #owner == authentication.name)
            """)
    public String readOwnerPage(@P("owner") String owner) {
        return "owner:" + owner;
    }

    public int invocationCount() {
        return invoked.get();
    }
}
```

`invocationCount()` ở đây chỉ là counter test, không phải production metric. `@PreAuthorize` phải chặn method body trước khi counter tăng nếu user thiếu role. Test direct method qua Spring proxy sẽ chứng minh thứ tự bảo vệ, thay vì chỉ đo HTTP 403 có thể đến từ filter khác.

### 7.6. Controller

Tệp `src/main/java/com/example/upgrade/DemoController.java`:

```java
package com.example.upgrade;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final AdminTaskService adminTaskService;

    public DemoController(AdminTaskService adminTaskService) {
        this.adminTaskService = adminTaskService;
    }

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/admin/task")
    public Map<String, String> adminTask() {
        return Map.of("result",
                adminTaskService.performAdminTask());
    }

    @GetMapping("/owners/{owner}")
    public Map<String, String> ownerPage(@PathVariable String owner) {
        return Map.of("result",
                adminTaskService.readOwnerPage(owner));
    }

    @PostMapping("/settings")
    public Map<String, Boolean> updateSettings() {
        return Map.of("accepted", true);
    }
}
```

`/settings` cố tình không ghi DB; mục tiêu của test là xác nhận CSRF chặn POST thiếu token. Rule `anyRequest().authenticated()` cho phép authenticated users đến controller, còn `AdminTaskService` bảo vệ owner theo parameter. Khi nâng cấp framework, cả tầng URL và method phải giữ behavior.

## 8. HTTP regression test bằng MockMvc

Tệp `src/test/java/com/example/upgrade/SecurityHttpRegressionTest.java`:

```java
package com.example.upgrade;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHttpRegressionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicUrlRemainsPublic() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateUrlRejectsAnonymous() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void privateUrlRejectsBadPassword() throws Exception {
        mvc.perform(get("/me")
                        .with(httpBasic("alice", "wrong-pass")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedUserReadsOwnIdentity() throws Exception {
        mvc.perform(get("/me")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void userCannotCallAdminUrl() throws Exception {
        mvc.perform(get("/admin/task")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanCallAdminUrl() throws Exception {
        mvc.perform(get("/admin/task")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("admin-ok"));
    }

    @Test
    void ownerParameterCannotBeForged() throws Exception {
        mvc.perform(get("/owners/admin")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void ownerCanReadOwnPage() throws Exception {
        mvc.perform(get("/owners/alice")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("owner:alice"));
    }

    @Test
    void unsafeRequestWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/settings")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unsafeRequestWithCsrfCanPass() throws Exception {
        mvc.perform(post("/settings")
                        .with(httpBasic("alice", "alice-pass"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted").value(true));
    }
}
```

**Điểm học tập:** `MockMvc` đi qua filter chain nếu Spring Security được tích hợp vào test context như cấu hình này. `httpBasic(...)` cung cấp Basic credentials, nên test không giả định session login. `csrf()` của `spring-security-test` cung cấp CSRF token phù hợp cho kiểm thử filter; nó **không chứng minh browser token transport** đã đúng ở môi trường thật.

Kết quả kỳ vọng: **10 tests pass** với mã/config demo. Các status 401/403 được chọn theo **HTTP Basic**; với `formLogin()`, anonymous có thể nhận 302 tới login thay vì 401.

## 9. Method security regression test: kiểm tra proxy và tác dụng phụ

Tệp `src/test/java/com/example/upgrade/MethodSecurityRegressionTest.java`:

```java
package com.example.upgrade;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class MethodSecurityRegressionTest {

    @Autowired
    AdminTaskService adminTaskService;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void nonAdminMethodCallIsDeniedBeforeBody() {
        int before = adminTaskService.invocationCount();

        assertThatThrownBy(adminTaskService::performAdminTask)
                .isInstanceOf(AccessDeniedException.class);

        assertThat(adminTaskService.invocationCount())
                .isEqualTo(before);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminMethodCallWorks() {
        assertThat(adminTaskService.performAdminTask())
                .isEqualTo("admin-ok");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userCanReadOwnOwnerParameter() {
        assertThat(adminTaskService.readOwnerPage("alice"))
                .isEqualTo("owner:alice");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userCannotReadOtherOwnerParameter() {
        assertThatThrownBy(
                () -> adminTaskService.readOwnerPage("admin"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

**Vì sao test này quan trọng:** `@WithMockUser` đặt một authentication giả trong Spring test context nhưng service được lấy **qua Spring-managed proxy**; annotation method security thực sự được kiểm chứng. `new AdminTaskService()` hoặc Mockito `@InjectMocks` **không tự có security interceptor**, có thể tạo false-positive khi bảo vệ đã bị bỏ qua.

Khi chuyển từ `@EnableGlobalMethodSecurity` sang `@EnableMethodSecurity`, hãy chạy các test này cả trên bản đang có và bản mới (điều chỉnh source test theo dependency test tương thích). Nhóm HTTP test ở trên có thể phát hiện lỗi URL, còn direct service test cô lập lỗi interceptor/proxy.

## 10. Chạy và tạo baseline đáng tin

Trong repository demo có Gradle Wrapper:

```bash
# Linux/macOS
./gradlew clean test
./gradlew compileJava

# Windows PowerShell
.\gradlew.bat clean test
.\gradlew.bat compileJava
```

Kỳ vọng **14 test** trong hai class trên chạy thành công khi config, Java và dependencies đúng. Đây là **kết quả kỳ vọng của ví dụ**, không phải khẳng định bài học đã chạy được trên môi trường của người học. Nếu framework version/dependency local khác, phải thực thi lệnh để xác minh biên dịch và điều chỉnh API tương ứng.

Lưu bằng chứng:

- Commit SHA nguồn trước thay đổi, Java/Gradle/Boot/Security dependency versions.
- Test report `build/test-results/test`, số ca pass/fail, môi trường (OS, JDK, DB, session store).
- Những HTTP contracts cụ thể đã kiểm: 200, 401, 403, CSRF, principal, method.
- Danh sách deprecated symbols từ `-Xlint:deprecation` và đường dẫn mã nguồn.
- Những hành vi chưa test (SSO/proxy/TLS/cookie browser), gán owner để bổ sung.

**Không coi test chạy không ổn định do môi trường là bằng chứng migration pass.** Flaky test cần được phân loại và sửa hoặc cách ly có quyết định, tránh “thỉnh thoảng xanh” thành gate release.

## 11. Các kiểm thử bổ sung khi ứng dụng dùng form login/session

Ví dụ HTTP Basic giúp test authorization rõ nhưng **không bao trùm** form login. Một dự án đang nâng cấp form-login thực cần regression tests theo session:

1. Anonymous `GET /account` nhận `302 Location: /login`.
2. `GET /login` trả HTML login hợp lệ, không redirect về chính nó.
3. `GET /login` tạo hoặc dùng session, form chứa CSRF token đúng flow.
4. `POST /login` đúng username/password và CSRF với **cùng cookie jar** tạo login thành công.
5. Client chấp nhận `Set-Cookie` mới sau login (có thể rotate session ID).
6. `GET /account` với cookie jar đó trả 200, principal đúng.
7. `GET /account` với client mới/không cookie vẫn yêu cầu login.
8. `POST /logout` với CSRF token phù hợp invalidates local session theo policy, request kế tiếp bị yêu cầu login.
9. Login failure không tạo authenticated session; error message không tiết lộ chi tiết nhạy cảm.
10. URL error/login/static assets không tạo redirect loops khi anonymous.

Đây là nơi dễ phát hiện regression sau thay SecurityContext persistence, session configuration, filter chain hoặc success handler mà MockMvc với `with(user("alice"))` không thấy.

Nếu sử dụng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và Java `HttpClient` có `CookieManager`, nhớ đặt redirect policy phù hợp khi chẩn đoán `302`. Nếu dùng OAuth2/OIDC, kiểm tra thêm `state`, redirect URI, cookie SameSite trong browser và id token validation theo trust boundary. Không giả lập một identity provider bằng cách bỏ qua token signature/issuer check rồi coi kết quả là đủ.

## 12. Những điểm dễ thay đổi ngầm khi di chuyển API

### 12.1. RequestMatcher ordering

Trong `authorizeHttpRequests`, thứ tự thường quyết định rule đầu tiên áp dụng. Ví dụ sai:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN"));
```

Rule public tổng quát có thể phủ lên rule admin. Test `GET /admin/report` với user thường phải fail, giúp phát hiện một refactor đặt rule sai thứ tự. Phải đặt rule cụ thể trước và rule cuối có ý nghĩa:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated());
```

### 12.2. Anonymous authentication và hasRole

`AnonymousAuthenticationToken` có thể có `isAuthenticated()==true` ở cấp token, nhưng Spring Security expression `isAuthenticated()` có semantics dựa trên trust resolver. Đừng viết custom guard `authentication != null && authentication.isAuthenticated()` rồi coi anonymous là login. Sau migration, test anonymous **và** authenticated-without-role.

`hasRole("ADMIN")` dùng convention authority `ROLE_ADMIN` trong cấu hình thông thường, còn `hasAuthority("ADMIN")` so khớp exact authority `ADMIN`. Nếu đổi authority mapping khi nâng cấp, test bằng role thật từ authentication provider, không chỉ mock admin.

### 12.3. CORS và preflight

Một `OPTIONS` preflight có thể bị từ chối nếu CORS filter/rule không được áp dụng đúng thứ tự hoặc chain. Chỉ khi ứng dụng thực sự phục vụ browser cross-origin mới cần policy CORS tương ứng; không bật `allowedOrigins("*")` kết hợp credentials như một workaround.

Regression test cần kiểm:

- Origin thuộc allowlist → preflight phản hồi đúng allowed methods/headers/credentials.
- Origin ngoài allowlist → không được mở.
- Cross-origin request có cookie hay bearer credential đúng theo scheme thiết kế.
- CSRF vẫn áp dụng cho unsafe requests khi dựa vào cookie/session.

### 12.4. Error pages và authentication entry point

Khi exception controller dẫn tới `/error`/ERROR dispatch, rule có thể khác trước migration. Nếu bị chặn, client có thể nhận redirect login thay vì 500 hoặc gặp vòng lặp. Test thực tế lỗi ứng dụng, error handling và `AuthenticationEntryPoint`. Có thể cần permit `DispatcherType.ERROR` hoặc custom error path, nhưng không mở rộng mọi dispatcher types bừa bãi.

### 12.5. RequestCache, saved request và redirects

Form login có thể giữ URL user yêu cầu trước login rồi redirect về đó. Khi đổi chain/matcher, `RequestCache`, success URL hoặc custom success handler có thể trả host/path sai. Regression test cần kiểm `Location` chính xác theo hợp đồng, không chỉ status `302`; với TLS termination cần test qua proxy và external host/scheme.

### 12.6. CSRF không đồng nghĩa authorization

HTTP `403` có thể do CSRF thiếu, thiếu authority hoặc business policy. Để tránh test mơ hồ:

- Positive POST kèm CSRF + user có quyền.
- Negative POST thiếu CSRF + user có quyền.
- Negative POST có CSRF + user thiếu quyền.
- Anonymous POST có/không CSRF tùy entry point.

Chỉ khi đủ tổ hợp mới tách được nguyên nhân. Nếu migration đổi CSRF repository, token request handler hoặc cookie strategy, phải test tương thích browser hoặc SPA thật.

### 12.7. @PostAuthorize và side effects

Đổi method-security infrastructure không nên thay đổi thời điểm check mà không test. `@PreAuthorize` kiểm trước body; `@PostAuthorize` kiểm sau khi method đã trả result. Đừng dựa `@PostAuthorize` duy nhất để chặn transfer/payment/delete/email send; side effects có thể đã xảy ra. Test denial phải xác nhận side effect **không xảy ra** nếu policy yêu cầu chặn trước.

## 13. Một quy trình migration theo các cổng kiểm định

### Gate A — Chuẩn hóa yêu cầu và baseline

1. Chốt target framework/dependency versions đã được hỗ trợ trong tổ chức.
2. Tài liệu hóa behavior hiện hành và security invariants.
3. Kiểm kê deprecated APIs, legacy classes, filters, providers, matchers, custom auth flows.
4. Viết/ổn định regression tests cho allow, deny, anonymous, CSRF, session và method security.
5. Chạy test trên code cũ, lưu báo cáo, xác nhận những kết quả expected.
6. Nếu test đang đỏ, xử lý trước migration hoặc ghi ngoại lệ rõ; không đi tiếp với “baseline mù”.

**Tiêu chí qua Gate A:** bộ test xác nhận được một contract đang được phê duyệt, có owner và reproducible test run.

### Gate B — Thay thế hẹp theo nhóm API

1. Đổi **một nhóm nhỏ**: ví dụ `WebSecurityConfigurerAdapter` → `SecurityFilterChain`, chưa đổi method security và session cùng lúc.
2. Biên dịch, chạy unit + web + method tests; so sánh status, authorities, Location, session behavior.
3. Nếu regression khác baseline, xác định **đó là bug hay intentional change**, không tự sửa assertions cho xanh.
4. Chỉ commit khi một nhóm thay API có tests pass và review được diff nhỏ.
5. Tiếp tục nhóm tiếp theo: URL matcher, method security, DSL, context persistence, logout.
6. Giữ commit/tag có thể quay lại ở từng chặng.

**Tiêu chí qua Gate B:** code đích không còn cần legacy API trong phạm vi đã chọn, runtime behavior pass cùng bộ kiểm thử, không bỏ một đường bảo vệ cũ.

### Gate C — Dọn API cũ và xác minh cuối

1. Tìm lại deprecated symbols trong source và test code; xác nhận không còn duplicate security filter chain hoặc config bean cũ.
2. Không xóa ngay custom filter/adapter nếu có tests chưa bao phủ đường dùng hoặc integration chưa được chạy.
3. Chạy toàn suite với dependency target cố định: unit, integration, method, HTTP, session.
4. Dùng staging/proxy/browser khi các thay đổi liên quan cookie, HTTPS, redirect hoặc IdP.
5. Review security invariants và code diff: deny paths vẫn deny, CSRF vẫn có, cookie policy không bị hạ.
6. Chỉ sau cùng mới xóa dead code, lớp bridge tạm, import cũ, comment migration tạm không còn hữu ích.
7. Thực hiện reviewer sign-off và ghi record thay đổi nếu policy yêu cầu.

**Tiêu chí qua Gate C:** source sạch API lỗi thời trong phạm vi nâng cấp, tests xanh đáng tin, không có bảo vệ bị mở ngoài ý định.

### Gate D — Release canary và rollback

1. Deploy canary/staging gần production (proxy HTTPS, cookie flags, session store, IdP).
2. Kiểm tra login success/failure, 401/403, CSRF, logout, error route và quyền method thật.
3. Theo dõi rate 401/403, login failures, redirect loops, session churn, unauthorized attempts, nhưng tránh log secrets.
4. Nếu phát hiện behavior regression: **rollback có kiểm soát** về artifact trước đó, không vội tắt security rule trong production.
5. Ghi root cause, bổ sung test tương ứng để lỗi không quay lại.
6. Release rộng hơn chỉ khi canary và smoke tests đáp ứng ngưỡng đã định.

**Không chỉ** lấy `gradle test` xanh làm tiêu chí release nếu việc đổi API còn ảnh hưởng proxy/session/SSO mà test suite chưa mô phỏng.

## 14. Review checklist dành cho pull request loại bỏ deprecated API

### 14.1. Kiểm tra mã

- [ ] Tất cả API cũ được liệt kê với replacement có nguồn/version rõ.
- [ ] Không còn `WebSecurityConfigurerAdapter` hay legacy override không cần thiết trên branch target.
- [ ] `SecurityFilterChain` và `@Order`/`securityMatcher` phù hợp URL thực.
- [ ] `authorizeHttpRequests` giữ thứ tự rule đúng; rule cuối không nới quyền.
- [ ] `requestMatchers` được test với servlet/context path, HTTP method, special paths.
- [ ] `@EnableMethodSecurity` và security proxy bảo vệ service được gọi.
- [ ] Không tự tạo authenticated token cho username request hoặc bỏ provider validation.
- [ ] SecurityContext được lưu đúng policy nếu có custom authentication.
- [ ] CSRF và logout behavior không bị thay đổi vô ý.
- [ ] CORS, security headers, session cookie, reverse proxy và error dispatch không bị bỏ cấu hình.
- [ ] Không giữ hai cấu hình authentication chồng nhau gây conflict.
- [ ] Không copy legacy config mang `csrf.disable()`/`permitAll()` vào API mới chỉ để build xanh.

### 14.2. Kiểm tra test

- [ ] Baseline test xanh trên phiên bản trước khi thay API.
- [ ] Unit tests, method-security tests, MockMvc và HTTP integration chạy đúng suite.
- [ ] HTTP 200/302/401/403 có positive/negative/anonymous assertions.
- [ ] CSRF thiếu bị từ chối; CSRF hợp lệ + quyền đúng được phép.
- [ ] Owner/tenant/resource authorization từ dữ liệu server-side được giữ.
- [ ] Session sau login và logout hoạt động nếu ứng dụng stateful.
- [ ] Tests verify side effects không xảy ra khi `@PreAuthorize` từ chối.
- [ ] Tests không gọi service bằng `new` thay vì proxy khi test annotation.
- [ ] Khi có thay đổi theo proxy/HTTPS, đã có test ở đúng lớp proxy/browser.
- [ ] Không có test bị xóa, ignore, đổi expected để “che” regression không có phê duyệt.

### 14.3. Kiểm tra vận hành

- [ ] Dependency lock/BOM/Java version được ghi nhận.
- [ ] Không còn compile warnings cũ trong phạm vi nâng cấp; các warnings ngoài phạm vi có owner.
- [ ] Audit log không ghi password, `Authorization` header, session cookie, access/refresh token.
- [ ] Có đường rollback artifact và compatibility plan cho session/token giữa release.
- [ ] Canary/smoke tests trên cấu hình sát production pass.
- [ ] Security reviewer và người sở hữu hệ thống đã xác nhận không mất permission boundary.

## 15. Những lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Khắc phục đúng |
| --- | --- | --- |
| Compile fail do `WebSecurityConfigurerAdapter` | API cũ đã removed ở Security 6 | Chuyển sang beans, di chuyển auth wiring, chạy regression |
| `antMatchers` không có trên API mới | DSL/matcher method cũ đã thay | Dùng `requestMatchers`/explicit RequestMatcher, test path semantics |
| Anonymous truy cập được `/admin` | Matcher bị thay hoặc rule tổng quát `permitAll` đứng trước | So sánh rule order; negative test admin |
| Test controller xanh nhưng service chưa bảo vệ | `@EnableMethodSecurity` thiếu hoặc self-invocation bypass proxy | Test direct Spring-managed service |
| `@PreAuthorize` không đọc được `#owner` | Parameter metadata thiếu, SpEL mapping khác | Dùng `@P`/`-parameters` và test owner mismatch |
| `POST /settings` trả 403 sau migration | CSRF token thiếu/sai, role thiếu hoặc chain khác | Tách CSRF test và authorization test |
| GET API trả 302 thay 401 | Entry point đổi từ Basic/API sang form | Khôi phục entry point theo API contract |
| Form login success nhưng request sau anonymous | Session stateless, cookie không gửi, context chưa save | Test real HTTP + CookieManager, context repository |
| `JSESSIONID` mất qua HTTPS proxy | Secure/SameSite/Domain/Path hoặc forwarded scheme sai | Kiểm tra browser Network/Storage và proxy |
| Redirect sang `http://app:8080` | App không hiểu external scheme/host | Trusted forwarded headers + proxy integration test |
| Error page lặp redirect login | `/error`/ERROR dispatch bị bảo vệ | Error policy phù hợp và xem exception gốc |
| Hai filters chạy lặp | Bean auto-register và addFilter vào Security chain | Quản lý đăng ký filter có chủ đích |
| `hasRole("ADMIN")` fail dù user có authority `ADMIN` | Không khớp prefix `ROLE_` | Đối chiếu authority mapping thực và policy |
| Unit test pass nhưng production IDOR | Không test object owner/tenant với ID do client kiểm soát | Negative tests theo object/tenant |
| OAuth2 callback fail sau upgrade | Cookies/state/redirect URI/scheme/host mismatch | IdP/proxy/browser test, không bỏ state validation |
| Bỏ code cũ rồi không thể rollback | Không có compatibility/test sign-off | Small commits, artifact version và canary gate |

## 16. Câu hỏi tự kiểm tra

**1.** Vì sao không thể vừa thấy `deprecated` là xóa API và sửa test theo response mới?  
**Trả lời:** vì cần chứng minh behavior/security policy có được giữ nguyên hay thay đổi có chủ đích. Sửa expected response để test xanh có thể che một regression phân quyền.

**2.** Tại sao `@SpringBootTest` với service bean hữu ích hơn `new Service()` khi test `@PreAuthorize`?  
**Trả lời:** annotation thường được thực thi bởi Spring method-security proxy/interceptor. Gọi đối tượng tự tạo không đi qua proxy nên có thể bỏ qua protection.

**3.** Thay `antMatchers("/admin/**")` bằng `requestMatchers("/admin/**")` đã đủ chưa?  
**Trả lời:** chưa. Cần kiểm wildcard path, servlet/context path, rule order, HTTP method, encoding và status của user có/không có role.

**4.** `POST /login` thành công nhưng `GET /me` kế tiếp lại anonymous — test unit có phát hiện hết không?  
**Trả lời:** chưa chắc. Cần real HTTP session/cookie test, SecurityContextRepository/explicit save, proxy và multi-node nếu có.

**5.** Vì sao bật `-Xlint:deprecation` không thay thế regression suite?  
**Trả lời:** warning chỉ chỉ ra API không còn được khuyến nghị; không đo HTTP status, authorization, CSRF hay session behavior.

**6.** Khi Spring Security chuyển từ DSL cũ sang lambda DSL, có nên tắt CSRF để tránh 403?  
**Trả lời:** không. Kiểm tra token/session và policy; tắt CSRF là thay đổi security boundary cần được xem xét riêng.

**7.** Vì sao phải test cả user thiếu role nhưng đã xác thực?  
**Trả lời:** nếu chỉ test anonymous và admin, có thể bỏ sót authorization bypass cho authenticated user quyền thấp.

**8.** Một POST mutation chỉ có `@PostAuthorize` có đủ bảo vệ không?  
**Trả lời:** không. Method có thể thực thi side effect trước khi post check. Cần pre-check/business policy và test không có side effect khi denied.

**9.** Khi nào được xóa lớp adapter/bridge cũ?  
**Trả lời:** sau khi migration ở nhánh mới đã có test baseline, regression pass, behavior review chấp thuận, không còn consumer phụ thuộc và rollback/compatibility được thiết kế.

**10.** Một suite MockMvc pass có chứng minh cookie SameSite ngoài production hoạt động không?  
**Trả lời:** không. SameSite/Secure/third-party cookie và TLS termination cần browser/proxy tests phù hợp.

## 17. Kết luận

**Loại bỏ API lỗi thời là bước sau cùng của một quá trình chứng minh hành vi, không phải mục tiêu đầu tiên.** Trong Spring Security Servlet, nâng cấp thường liên quan `SecurityFilterChain`, `authorizeHttpRequests`, `requestMatchers`, lambda DSL, `@EnableMethodSecurity` và SecurityContext persistence. Mỗi thay đổi có thể ảnh hưởng **request matching, authentication, authorization, CSRF, session, login/logout, error handling, proxy và browser**.

Quy trình đáng tin là:

1. **Khóa phiên bản và đo behavior cũ bằng regression tests.**
2. **Thay một nhóm API có kiểm soát, không trộn sửa bug/chính sách.**
3. **Chạy lại cả positive/negative tests và phân tích từng khác biệt.**
4. **Kiểm chứng session/HTTPS/proxy/browser ở tầng thực khi có rủi ro.**
5. **Chỉ sau tất cả gates đạt yêu cầu mới xóa mã cũ và release có rollback.**

Đích đến không phải chỉ là mã “không có deprecated warning”, mà là **cấu hình hiện đại với security behavior được test và chứng minh vẫn đúng**.
