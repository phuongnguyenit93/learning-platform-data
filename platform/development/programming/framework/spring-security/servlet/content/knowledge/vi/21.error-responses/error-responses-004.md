# AuthenticationTrustResolver và cách xử lý người dùng anonymous hoặc remember-me

## Mục tiêu

Trong Spring Security Servlet, **bị từ chối truy cập** không luôn đồng nghĩa với **403 Forbidden**. Có ba tình huống đặc biệt: khách chưa đăng nhập (anonymous) cần xác thực; người đang dùng remember-me có thể cần đăng nhập đầy đủ trước thao tác nhạy cảm; và người đã đăng nhập đầy đủ nhưng thiếu quyền phải bị từ chối theo chính sách. AuthenticationTrustResolver và ExceptionTranslationFilter phối hợp để đưa mỗi tình huống tới AuthenticationEntryPoint hoặc AccessDeniedHandler thích hợp.

Học xong bài này, bạn có thể:

1. Phân biệt Authentication, AnonymousAuthenticationToken, RememberMeAuthenticationToken và full authentication.
2. Giải thích vì sao cờ Authentication.isAuthenticated() một mình không đủ để coi caller là user thực.
3. Sử dụng AuthenticationTrustResolver.isAnonymous() và isRememberMe() để phân loại token.
4. Nắm khác biệt giữa permitAll(), anonymous(), authenticated(), fullyAuthenticated() và hasRole().
5. Mô tả cách ExceptionTranslationFilter xử lý AuthenticationException, AccessDeniedException và chọn response.
6. Phân biệt redirect 302, challenge 401, từ chối 403 và các trường hợp CSRF bị từ chối.
7. Xây demo Spring Boot 3.x, Security 6.x, Java 17+ có formLogin và rememberMe.
8. Kiểm thử anonymous, remember-me, fully authenticated và thiếu role bằng MockMvc.
9. Biết hạn chế của remember-me token, cookie, logout, persistent token storage và key rotation.
10. Phân biệt full authentication với xác thực gần đây (fresh authentication) hoặc MFA.

Phạm vi: Spring Security **Servlet/MVC**. Bài dùng browser form login và HttpSession, không phải WebFlux. Cấu hình key/password cố định dành riêng cho localhost, không đưa ra production.

## 1. Có Authentication không nhất thiết đã login

Spring Security dùng SecurityContext chứa Authentication để biểu diễn thông tin về caller. Trong một request chưa login, AnonymousAuthenticationFilter có thể tạo AnonymousAuthenticationToken với principal như anonymousUser và ROLE_ANONYMOUS. Đây là mô hình đại diện khách **chưa xác minh danh tính**, không phải người dùng được xác thực hợp lệ.

Ví dụ đọc context:

~~~java
Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

boolean flag = current != null && current.isAuthenticated();
~~~

Đoạn trên **không phải** một kiểm tra an toàn cho việc “user thật đã login”. AnonymousAuthenticationToken có thể báo isAuthenticated() là true theo implementation của token. Spring Security phân biệt trạng thái anonymous dựa trên trust semantics, chứ không chỉ cờ đó.

| Loại request | Authentication thường gặp | Ý nghĩa |
| --- | --- | --- |
| Chưa có context | null | Chưa biết danh tính |
| Chưa đăng nhập, đã qua anonymous filter | AnonymousAuthenticationToken | Caller anonymous, có thể có ROLE_ANONYMOUS |
| Được nhận diện bằng remember-me cookie hợp lệ | RememberMeAuthenticationToken | Được khôi phục identity, nhưng không phải login tương tác đầy đủ |
| Đã form login thành công | UsernamePasswordAuthenticationToken hoặc token do provider chọn | Đã xác thực theo flow đầy đủ đang dùng |
| API JWT/OIDC hoặc custom | Authentication phụ thuộc cơ chế | Phải xem provider và level-of-assurance cụ thể |

**Tên token không phải bằng chứng về MFA.** Nếu API dùng JWT, resolver mặc định không tự hiểu ACR/AMR, xác thực gần đây hay số yếu tố đã hoàn tất. Muốn step-up phải có chính sách riêng.

### Chuỗi xử lý anonymous

~~~text
HTTP GET /account/profile
   |
SecurityContext chưa có user thật
   |
AnonymousAuthenticationFilter
   | -> có thể đặt AnonymousAuthenticationToken
   |
AuthorizationFilter: route yêu cầu authenticated()
   | -> anonymous không đạt
   |
ExceptionTranslationFilter:
   | -> anonymous -> AuthenticationEntryPoint
   |
Browser form login: thường 302 đến /login
HTTP Basic API: thường 401 + WWW-Authenticate
~~~

Không tự so tên anonymousUser với một path variable để cấp quyền dữ liệu người dùng, cũng không tin X-User header do client gửi.

## 2. Remember-me không giống đăng nhập đầy đủ

Remember-me cho phép browser duy trì khả năng được nhận diện trong thời gian dài hơn một phiên HTTP thông thường. Nếu user đã chọn remember-me khi login, một RememberMeServices phù hợp có thể phát cookie/token. Khi HttpSession hết hạn nhưng cookie remember-me hợp lệ vẫn được gửi, RememberMeAuthenticationFilter có thể sử dụng RememberMeServices để tạo RememberMeAuthenticationToken.

~~~text
POST /login + password đúng + remember-me
        |
Full Authentication
        | -> HttpSession/SecurityContext
        | -> Remember-me cookie/token (theo config)
        v
Browser sử dụng website bình thường

Sau khi session cookie mất nhưng remember-me cookie còn:
        |
RememberMeServices kiểm tra cookie/token
        |
RememberMeAuthenticationToken
        |
GET /account/profile: authenticated() -> thường được phép
GET /account/payment: fullyAuthenticated() -> không đủ
        |
ExceptionTranslationFilter có thể yêu cầu login đầy đủ
~~~

Remember-me giúp UX, nhưng cookie dài hạn có nguy cơ bị sao chép, đánh cắp hoặc tồn tại trên thiết bị không còn đáng tin. Với chức năng thanh toán, đổi mật khẩu, thay địa chỉ email, phát hành API key, xóa dữ liệu quan trọng, cân nhắc **full login và bước xác thực mới** theo threat model.

AuthenticationTrustResolver **không xác thực chữ ký cookie**, không đọc persistent token repository, không quyết định token hết hạn và không thay RememberMeServices. Nó chỉ phân loại Authentication đã có.

## 3. API AuthenticationTrustResolver

Interface và implementation phổ biến:

~~~java
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

AuthenticationTrustResolver resolver =
        new AuthenticationTrustResolverImpl();

Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

boolean anonymous = resolver.isAnonymous(current);
boolean rememberMe = resolver.isRememberMe(current);
~~~

Đây là snippet cần nằm trong một method/class Java phù hợp; không phải file độc lập. Hai phương thức cốt lõi là isAnonymous(Authentication) và isRememberMe(Authentication). Với những token chuẩn, AuthenticationTrustResolverImpl thường dựa trên loại token để phân loại.

Có thể mô tả full authentication cho mục đích học tập:

~~~java
boolean hasRealUser =
        current != null
        && current.isAuthenticated()
        && !resolver.isAnonymous(current);

boolean full =
        hasRealUser && !resolver.isRememberMe(current);
~~~

Trong chính sách HTTP nên ưu tiên các AuthorizationManager hoặc DSL dựng sẵn, không sao chép logic phân loại vào mọi controller. Những method tiện ích như isAuthenticated/isFullyAuthenticated có thể có trong phiên bản interface đang dùng; hãy bám đúng phiên bản Spring Security thực tế khi viết custom code.

### Tự tạo token trong test không phải xác thực thực

~~~java
var anon = new AnonymousAuthenticationToken(
        "test-key", "anonymousUser",
        List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

var remembered = new RememberMeAuthenticationToken(
        "test-key", "alice",
        List.of(new SimpleGrantedAuthority("ROLE_USER")));

var full = UsernamePasswordAuthenticationToken.authenticated(
        "alice", null,
        List.of(new SimpleGrantedAuthority("ROLE_USER")));

var resolver = new AuthenticationTrustResolverImpl();

System.out.println(resolver.isAnonymous(anon));        // true
System.out.println(resolver.isRememberMe(remembered)); // true
System.out.println(resolver.isAnonymous(full));        // false
~~~

Snippet này cần imports và classpath của Spring Security. Output ở các comment là kỳ vọng với resolver mặc định. Các constructor này **không** xác minh user/password hoặc cookie: chỉ dùng để unit test phân loại trạng thái, không nhận dữ liệu client chưa tin cậy rồi dựng token production.

## 4. Các điều kiện authorization thường gặp

Ví dụ cấu hình:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/status").permitAll()
        .requestMatchers("/account/profile").authenticated()
        .requestMatchers("/account/payment").fullyAuthenticated()
        .requestMatchers("/admin/report").hasRole("ADMIN")
        .anyRequest().denyAll());
~~~

- permitAll(): không đòi xác thực. Người đã đăng nhập cũng truy cập được.
- anonymous(): chỉ cho caller được coi là anonymous. Không nên thay permitAll bằng anonymous() một cách mù quáng cho mọi trang công khai.
- authenticated(): yêu cầu Authentication có tính xác thực theo resolver; remember-me thông thường đáp ứng, anonymous thì không.
- fullyAuthenticated(): loại anonymous và remember-me; buộc phải có authentication đầy đủ theo semantics của framework.
- hasRole("ADMIN"): yêu cầu ROLE_ADMIN; không mặc định bắt full login hay MFA.
- denyAll(): từ chối route chưa khai báo; response thực tế còn phụ thuộc trust state và entrypoint.

| Caller | /public/status | /account/profile | /account/payment | /admin/report |
| --- | --- | --- | --- | --- |
| Anonymous | Cho phép | Cần login | Cần login | Cần login |
| Alice remember-me ROLE_USER | Cho phép | Cho phép | Cần full login | Thiếu role; có thể được mời login lại |
| Alice full login ROLE_USER | Cho phép | Cho phép | Cho phép | Từ chối quyền |
| Root full login ROLE_ADMIN | Cho phép | Cho phép | Cho phép | Cho phép |

Một điều dễ bỏ sót: **remember-me user có ROLE_ADMIN vẫn có thể qua rule hasRole("ADMIN")**, nếu role đủ và rule không đòi full authentication. Nếu admin action cần cả role lẫn full login, phải cấu hình cả hai điều kiện (ví dụ method security expression isFullyAuthenticated() and hasRole('ADMIN')), không trông chờ framework tự cấm mọi remember-me user.

Đừng đánh đồng fullyAuthenticated với fresh login hay MFA: một session đầy đủ có thể đã đăng nhập từ nhiều giờ trước. Dùng auth_time, assurance level, step-up, MFA hoặc password recheck theo policy nếu nghiệp vụ yêu cầu.

## 5. ExceptionTranslationFilter và phản hồi lỗi

ExceptionTranslationFilter là mắt xích chuyển một số security exceptions thành HTTP response. Nó thường đứng để bắt AuthenticationException hoặc AccessDeniedException phát sinh ở filter chain phía sau, rồi sử dụng AuthenticationEntryPoint hoặc AccessDeniedHandler.

~~~text
Request -> authentication/authorization
                |
                +-- OK -> Controller/Service
                |
                +-- AuthenticationException
                |        -> AuthenticationEntryPoint
                |           (login redirect, 401 challenge...)
                |
                +-- AccessDeniedException
                          |
                          +-- anonymous?
                          |       -> AuthenticationEntryPoint
                          |
                          +-- remember-me?
                          |       -> AuthenticationEntryPoint
                          |          (cơ hội đăng nhập đầy đủ)
                          |
                          +-- user đã được xác thực đầy đủ?
                                  -> AccessDeniedHandler
                                     (thường HTTP 403)
~~~

**Phân loại trust quyết định hướng xử lý của AccessDeniedException**. Với remember-me chưa đủ tin cậy, lỗi thiếu quyền có thể được coi là cần thực hiện authentication thêm, không nhất thiết là forbidden cuối cùng.

### Vai trò từng thành phần

- AuthenticationTrustResolver: phân loại anonymous/remember-me.
- AuthenticationEntryPoint: khởi động authentication; formLogin thường redirect, Basic thường challenge, API có thể trả JSON 401.
- AccessDeniedHandler: xử lý denied đối với caller đã xác thực đầy đủ nhưng thiếu quyền, thường 403.
- ExceptionTranslationFilter: phối hợp ba thành phần trên; không tự xác minh password/token.
- RequestCache: có thể giữ saved request để quay lại sau khi login theo cấu hình.

Nếu đã login đầy đủ mà không có ROLE_ADMIN, yêu cầu nhập password lại liên tục **không sửa được thiếu quyền**. Cần trả forbidden theo hợp đồng. Nếu remember-me chưa đáp ứng fullyAuthenticated, điều hướng login để nâng cấp mức xác thực lại phù hợp.

### Không chỉ có 302, 401 và 403

| Mã | Một tình huống điển hình | Không nên kết luận |
| --- | --- | --- |
| 302 | Form-login entrypoint chuyển hướng /login | Không chắc user nhập sai mật khẩu |
| 401 | HTTP Basic/bearer challenge hoặc entrypoint API | Không phải mọi app đều dùng status này cho anonymous |
| 403 | User đủ xác thực thiếu role hoặc CSRF check từ chối | Không thể suy nguyên nhân chỉ từ status |
| 400 | Container/firewall từ chối URL không hợp lệ | Không phải vai trò đã bị từ chối |
| 404 | MVC không tìm thấy route hoặc API ẩn tài nguyên | Không xác minh trust state chỉ bằng status |

Khi CsrfFilter từ chối POST thiếu CSRF token, response có thể là 403 **trước** khi authorization rule được thực hiện; test với CSRF hợp lệ nếu muốn chứng minh role/trust check.

Một @PreAuthorize ở service cũng có thể ném AccessDeniedException. Nếu exception phát sinh trong web request và truyền ngược qua filter chain, ExceptionTranslationFilter có thể xử lý. Nhưng nếu @ControllerAdvice bắt và nuốt exception, hoặc job/message listener gọi service không qua HTTP, response/handling sẽ khác.

## 6. Project Spring Boot 3.x: Form Login + Remember Me

### 6.1. Cấu trúc và Gradle

~~~text
trust-resolver-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (cần tạo wrapper nếu chưa có)
  src/main/java/dev/example/trust/
    TrustDemoApplication.java
    SecurityConfig.java
    TrustController.java
  src/test/java/dev/example/trust/
    TrustDemoIntegrationTest.java
~~~

settings.gradle:

~~~groovy
rootProject.name = 'trust-resolver-demo'
~~~

build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các dependency Spring Security được quản lý theo phiên bản Boot, không tự ép artifact khác major. Dùng JDK 17+, Gradle Wrapper, Internet để tải Maven dependencies ban đầu hoặc cache đã chuẩn bị.

### 6.2. Java main

Tệp src/main/java/dev/example/trust/TrustDemoApplication.java:

~~~java
package dev.example.trust;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TrustDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TrustDemoApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig

Tệp src/main/java/dev/example/trust/SecurityConfig.java:

~~~java
package dev.example.trust;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-only"))
                        .roles("USER")
                        .build(),
                User.withUsername("root")
                        .password(encoder.encode("root-demo-only"))
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/status").permitAll()
                        .requestMatchers("/account/profile").authenticated()
                        .requestMatchers("/account/payment").fullyAuthenticated()
                        .requestMatchers("/admin/report").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .formLogin(form -> form.permitAll())
                .rememberMe(remember -> remember
                        .userDetailsService(users)
                        .key("local-demo-key-not-for-production")
                        .tokenValiditySeconds(3600))
                .logout(Customizer.withDefaults())
                .build();
    }
}
~~~

Các điểm cần nhớ:

1. formLogin(form -> form.permitAll()) mở login page/form do Spring Security cung cấp cho anonymous.
2. rememberMe bật remember-me services, dùng user store và key demo; tokenValiditySeconds=3600 chỉ là thông số lab.
3. authenticated() trên profile chấp nhận remember-me theo policy; fullyAuthenticated() trên payment không.
4. hasRole ADMIN kiểm tra role; không tự yêu cầu full login cho admin remember-me.
5. anyRequest().denyAll() bảo vệ route không có policy rõ.
6. LogoutFilter chuẩn được giữ. Các bước cleanup nhớ đăng nhập cần test theo remember-me configuration.
7. CSRF mặc định không bị tắt; login/logout POST cần token CSRF thích hợp.

Không hardcode password và signing key trong source production; cần secret management, HTTPS, cookie flags an toàn, key rotation và user/token repository phù hợp. Hệ thống nhiều node phải dùng cùng key hoặc thiết kế tương thích khi verify token.

### 6.4. TrustController: quan sát trạng thái ở local

Tệp src/main/java/dev/example/trust/TrustController.java:

~~~java
package dev.example.trust;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TrustController {

    private final AuthenticationTrustResolver resolver =
            new AuthenticationTrustResolverImpl();

    @GetMapping("/public/status")
    public TrustState status() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        boolean anonymous = authentication == null
                || resolver.isAnonymous(authentication);
        boolean remembered = authentication != null
                && resolver.isRememberMe(authentication);
        boolean full = authentication != null
                && authentication.isAuthenticated()
                && !anonymous
                && !remembered;
        String name = anonymous ? "guest" : authentication.getName();

        return new TrustState(anonymous, remembered, full, name);
    }

    @GetMapping("/account/profile")
    public String profile() {
        return "PROFILE_OK";
    }

    @GetMapping("/account/payment")
    public String payment() {
        return "PAYMENT_READY";
    }

    @GetMapping("/admin/report")
    public String report() {
        return "ADMIN_REPORT";
    }

    public record TrustState(
            boolean anonymous,
            boolean rememberMe,
            boolean fullyAuthenticated,
            String name) {
    }
}
~~~

Đối tượng resolver trong controller chỉ để **hiển thị trạng thái demo**; nó không phải cấu hình lại resolver đang dùng bên trong ExceptionTranslationFilter. Spring Security nội bộ có các thành phần riêng của chain. Trong production không nên công khai raw Authentication, principal attributes, session cookie hoặc token để debug.

### 6.5. Chạy và quan sát

~~~bash
./gradlew bootRun
~~~

Với Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Mở http://localhost:8080/public/status trong browser chưa login, body dự kiến:

~~~json
{
  "anonymous": true,
  "rememberMe": false,
  "fullyAuthenticated": false,
  "name": "guest"
}
~~~

Vào http://localhost:8080/account/profile: browser formLogin thường chuyển tới /login. Đăng nhập alice bằng mật khẩu alice-demo-only, chọn Remember me, rồi vào /account/profile và /account/payment. Trong phiên full login cả hai được phép.

Để thấy remember-me thực sự: ở môi trường local, xóa riêng **session cookie** (ví dụ JSESSIONID) nhưng giữ remember-me cookie; sau đó dùng đúng browser profile truy cập /account/profile. Nếu remember-me token vẫn hợp lệ và được services xác minh, tài khoản có thể được nhận diện bằng RememberMeAuthenticationToken. /public/status khi ấy dự kiến rememberMe=true, fullyAuthenticated=false. Vào /account/payment sẽ được yêu cầu full login.

Nếu status vẫn full, session cookie có thể chưa thực sự mất. Nếu status anonymous, cookie remember-me có thể thiếu/hết hạn/bị từ chối hoặc cấu hình cookie không khớp. Không xóa tất cả cookies hoặc thực hiện logout chuẩn khi mục tiêu là kiểm thử tình huống **session hết hạn nhưng remember-me còn**.

## 7. Kiểm thử MockMvc và token classification

Tệp src/test/java/dev/example/trust/TrustDemoIntegrationTest.java:

~~~java
package dev.example.trust;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TrustDemoIntegrationTest {

    @Autowired
    MockMvc mvc;

    private static Authentication rememberAlice() {
        return new RememberMeAuthenticationToken(
                "test-key", "alice",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void trustResolverRecognizesTokenKinds() {
        var resolver = new AuthenticationTrustResolverImpl();
        Authentication anonymous = new AnonymousAuthenticationToken(
                "test-key", "anonymousUser",
                List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));
        Authentication remembered = rememberAlice();
        Authentication full =
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice", null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));

        assertThat(resolver.isAnonymous(anonymous)).isTrue();
        assertThat(resolver.isRememberMe(anonymous)).isFalse();
        assertThat(resolver.isAnonymous(remembered)).isFalse();
        assertThat(resolver.isRememberMe(remembered)).isTrue();
        assertThat(resolver.isAnonymous(full)).isFalse();
        assertThat(resolver.isRememberMe(full)).isFalse();
    }

    @Test
    void anonymousStatusDoesNotClaimFullLogin() throws Exception {
        mvc.perform(get("/public/status").with(anonymous()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.anonymous").value(true))
                .andExpect(jsonPath("$.rememberMe").value(false))
                .andExpect(jsonPath("$.fullyAuthenticated").value(false))
                .andExpect(jsonPath("$.name").value("guest"));
    }

    @Test
    void anonymousIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/account/profile").with(anonymous()))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void rememberMeCanUseAuthenticatedRule() throws Exception {
        mvc.perform(get("/account/profile")
                        .with(authentication(rememberAlice())))
                .andExpect(status().isOk())
                .andExpect(content().string("PROFILE_OK"));
    }

    @Test
    void rememberMeMustReauthenticateForFullRule()
            throws Exception {
        mvc.perform(get("/public/status")
                        .with(authentication(rememberAlice())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.rememberMe").value(true))
                .andExpect(jsonPath("$.fullyAuthenticated").value(false));

        mvc.perform(get("/account/payment")
                        .with(authentication(rememberAlice())))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void fullUserCanUsePayment() throws Exception {
        mvc.perform(get("/account/payment")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("PAYMENT_READY"));
    }

    @Test
    void fullUserWithoutAdminGets403() throws Exception {
        mvc.perform(get("/admin/report")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void fullAdminCanViewReport() throws Exception {
        mvc.perform(get("/admin/report")
                        .with(user("root").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(content().string("ADMIN_REPORT"));
    }

    @Test
    void formLoginSupportsRememberMeParameter()
            throws Exception {
        mvc.perform(post("/login").with(csrf())
                        .param("username", "alice")
                        .param("password", "alice-demo-only")
                        .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Các test đo ba điều quan trọng: anonymous cần login; remember-me được xem route authenticated nhưng không đủ fullyAuthenticated; full login thiếu role nhận forbidden còn full ADMIN được cho phép.

**Giới hạn kiểm thử:** cách with(authentication(rememberAlice())) cung cấp một Authentication giả lập trong MockMvc. Nó không tự xác minh remember-me cookie thật, chữ ký/token expiry, persistent token store hoặc logout cleanup. Cần một thử nghiệm browser/end-to-end HTTP với cookie thật để chứng minh RememberMeServices hoạt động. Cách with(user("alice")) cũng là authentication test data, không phải password verification; bài test POST /login tách riêng flow xác thực form.

## 8. Nếu muốn trả JSON 401/403 thay redirect

Browser formLogin thường dùng redirect 302 đến /login. Với REST API/mobile client, redirect HTML có thể không phù hợp; nên chọn AuthenticationEntryPoint và AccessDeniedHandler theo API security chain.

Snippet **thay thế** cho một security chain API:

~~~java
http.exceptionHandling(ex -> ex
        .authenticationEntryPoint(
                (request, response, error) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED))
        .accessDeniedHandler(
                (request, response, error) ->
                    response.sendError(
                        HttpServletResponse.SC_FORBIDDEN)));
~~~

Trong file Java sử dụng snippet cần import jakarta.servlet.http.HttpServletResponse. Nếu dùng HTTP Basic, hãy giữ cơ chế challenge WWW-Authenticate theo contract, không đổi thành 401 trống header mà client không biết cách xác thực. Với Bearer, Spring Security resource-server entrypoint/denied handler có contract và header riêng.

Không ghép đoạn thay thế này trực tiếp vào demo formLogin rồi vẫn kỳ vọng 302 trong các MockMvc tests. Có thể tạo nhiều SecurityFilterChain: một cho /api/** với Basic/Bearer và entry point API; một cho web MVC với formLogin và remember-me. Hãy kiểm tra securityMatcher/order và URL được chain nào xử lý. Không để endpoint nhạy cảm rơi ngoài mọi chain.

Một custom error handler không tự quyết định quyền. Quyền vẫn do Authentication và AuthorizationManager/service policy quyết định; handler chỉ chọn response khi bị từ chối.

## 9. Những vấn đề vận hành quan trọng

### Cookie và logout

Remember-me cookie có thể còn sau khi HttpSession bị invalidated. Nếu logout tùy biến chỉ clear SecurityContextHolder hoặc gọi HttpSession.invalidate() mà **không** dọn remember-me token, request sau có thể tự đăng nhập lại. Ưu tiên LogoutFilter/LogoutConfigurer và các logout handlers chuẩn; nếu tự viết logout MVC, phải bổ sung remember-me cleanup theo RememberMeServices và policy token store của ứng dụng.

Test logout: sau POST /logout hợp lệ có CSRF token, dùng lại browser/cookies và xác nhận request mới không tự trở thành authenticated ngoài chủ đích. Cookie còn tồn tại trong browser không nhất thiết nghĩa session server còn hợp lệ, nhưng remember-me token có thể thật sự tạo Authentication mới.

### Persistent tokens và thu hồi

Token-based remember-me khác persistent-token-based remember-me. Persistent token repository có thể hỗ trợ quản lý theo thiết bị và thu hồi theo thiết kế; không tự mặc định rằng gọi rememberMe() làm mọi token được lưu và thu hồi tập trung. Muốn logout mọi thiết bị, khóa account, reset password hay phát hiện replay cần thêm policy và token lifecycle rõ ràng.

### Multi-node

Trong cluster, key/token repository/UserDetailsService và cookie scope cần tương thích giữa các node. Spring Session chia sẻ HttpSession không tự giải quyết mọi cấu hình remember-me. Nếu A tạo token mà B dùng key khác, browser có thể bị yêu cầu login lại khi LB chuyển node.

### Request không qua HTTP

Một method @PreAuthorize có thể ném AccessDeniedException khi job hoặc message listener gọi trực tiếp. Lúc đó ExceptionTranslationFilter không tồn tại vì không có Servlet response. Job phải có service identity/delegation với quyền tối thiểu và xử lý exception theo retry/alert/fail closed, không gán ROLE_ADMIN tổng quát để tránh lỗi.

### Authentication không đồng nghĩa permission trên object

Ngay cả fullyAuthenticated và ROLE_ADMIN cũng không mặc định có quyền trên mọi tài liệu hoặc tenant. Cần service/resource authorization, owner/tenant isolation và audit theo nghiệp vụ. Với API đa tenant, nhớ rằng remember-me token giữ identity, không thay thế kiểm tra quyền hiện tại trong database.

## 10. Lỗi thường gặp

**Lỗi A: AnonymousAuthenticationToken.isAuthenticated() là true, rồi hệ thống trả dữ liệu riêng tư.** Không dùng boolean cờ token như proof; dùng resolver/authorization DSL và kiểm tra quyền trên object.

**Lỗi B: Remember-me user bị chuyển về login khi mở payment.** Đây là hành vi đúng nếu payment yêu cầu fullyAuthenticated; kiểm tra policy và entry point trước khi coi là bug.

**Lỗi C: Full user thiếu role ADMIN nhưng cứ bị đưa về login.** Có thể error handler nhầm thiếu quyền với thiếu login. Với user full login, thông thường trả 403 qua AccessDeniedHandler.

**Lỗi D: Remember-me admin vượt qua trang nhạy cảm.** Nếu rule chỉ hasRole ADMIN, remember-me có đủ role vẫn có thể được phép. Phải yêu cầu full auth hoặc step-up nếu chính sách cần.

**Lỗi E: Sau logout user tự login lại.** Remember-me cookie/token chưa được dọn; dùng pipeline logout đúng và test lại với cùng cookie.

**Lỗi F: API gửi 302 trang login thay vì JSON 401.** Request vào formLogin chain. Chọn API chain/entry point đúng client contract.

**Lỗi G: REST API 403 nhưng dev tưởng do role.** CsrfFilter cũng có thể trả 403 với POST/PUT thiếu token. Kiểm tra log/test có CSRF hợp lệ.

**Lỗi H: Custom Authentication không được resolver nhận diện.** AuthenticationTrustResolverImpl nhận biết token kiểu chuẩn, không tự hiểu mức đảm bảo của mọi custom provider. Thiết kế kiểm tra riêng khi cần.

**Lỗi I: Mất key remember-me khi rolling deploy.** Token cũ có thể vô hiệu, user phải login lại. Quản lý key bằng secret store và có rollout plan.

**Lỗi J: Node A nhớ user còn B thì không.** Kiểm tra key, token repo, UserDetailsService, cookie domain/path và load balancer; không đồng nhất vấn đề với Redis HttpSession.

**Lỗi K: User bị khóa vẫn có phiên/remember-me.** Thiết kế revalidation, token revocation và account lifecycle, không suy token cũ tự thu hồi.

**Lỗi L: ControllerAdvice trả 200 cho AccessDeniedException.** Không nuốt security exception hoặc cấp quyền fallback. Nếu xử lý riêng phải giữ semantics từ chối đúng.

**Lỗi M: isFullyAuthenticated được hiểu là MFA gần đây.** Đây là nhầm lẫn. Yêu cầu thời gian xác thực/MFA phải đọc các claim/attributes tin cậy và dùng step-up riêng.

**Lỗi N: Test giả lập token mà tưởng đã test cryptography.** MockMvc authentication postprocessor không xác minh cookie; thêm E2E test RememberMeServices thật.

## 11. Checklist trước production

1. Xác định yêu cầu của từng URL: permitAll, authenticated, fullyAuthenticated, role, owner, tenant.
2. Giữ khác biệt giữa anonymous, remember-me và full authentication rõ ràng.
3. Dùng AuthenticationTrustResolver để phân loại, không tự đặt tên anonymousUser làm bằng chứng danh tính.
4. Cấu hình AuthenticationEntryPoint/AccessDeniedHandler theo browser hay API.
5. Test 302/401/403 theo đúng security chain, không suy chỉ từ status.
6. Giữ CSRF protection cho form login và cookie authentication, test request unsafe với token hợp lệ.
7. Chỉ cấp remember-me cookie sau authentication thực sự, không tự tạo token từ header client.
8. Giới hạn remember-me lifetime và bảo vệ cookie Secure/HttpOnly/SameSite với HTTPS.
9. Dọn remember-me token khi logout, reset password, khóa account theo policy.
10. Đồng bộ key và persistent token store khi chạy nhiều node.
11. Không log cookie, password, Authentication credentials, raw Authorization header.
12. Yêu cầu full/step-up login cho hành động rủi ro cao khi threat model chỉ định.
13. Kết hợp role/trust với object authorization và tenant isolation.
14. Kiểm thử positive và negative: anonymous, remembered, full USER, full ADMIN, token hết hạn.
15. Nếu có nhiều SecurityFilterChain, test chain selection và fallback.
16. Không catch AccessDeniedException để trả success hoặc dữ liệu nhạy cảm.
17. Với job/async, xác định service identity và SecurityContext propagation an toàn.
18. Review remember-me cookie/token policies sau nâng Spring Boot/Security.

## 12. Tự luyện

**Câu 1.** Vì sao anonymous token có thể isAuthenticated=true nhưng Spring Security vẫn chặn ở authenticated()?

**Đáp án:** đó là cờ implementation, còn rule dùng semantics của AuthenticationTrustResolver để xác định caller anonymous, không phải user login.

**Câu 2.** AuthenticationTrustResolver có đọc và xác minh chữ ký cookie remember-me không?

**Đáp án:** không. RememberMeServices thực hiện xác minh; resolver phân loại Authentication đã được tạo.

**Câu 3.** Remember-me user được profile cho phép nhưng payment redirect login. Vì sao?

**Đáp án:** profile dùng authenticated; payment dùng fullyAuthenticated, không chấp nhận remember-me; ExceptionTranslationFilter có thể gọi AuthenticationEntryPoint.

**Câu 4.** Full login user thiếu ROLE_ADMIN thường nhận gì?

**Đáp án:** 403 qua AccessDeniedHandler, không phải bắt đăng nhập lại.

**Câu 5.** Web form login và Basic API có cùng phản hồi khi anonymous không?

**Đáp án:** không nhất thiết. Form login thường 302 tới /login, Basic thường 401 challenge; entry point quyết định.

**Câu 6.** Remember-me admin có ROLE_ADMIN, rule hasRole ADMIN đã buộc re-authentication chưa?

**Đáp án:** chưa; cần chính sách kết hợp full auth hoặc step-up khi nhạy cảm.

**Câu 7.** fullyAuthenticated xác nhận đã hoàn tất MFA không?

**Đáp án:** không. Nó chủ yếu phân biệt anonymous/remember-me; MFA/fresh auth cần cơ chế khác.

**Câu 8.** Logout invalidate session nhưng remember-me vẫn còn, điều gì có thể xảy ra?

**Đáp án:** browser có thể tự nhận diện lại request sau nhờ remember-me token; cần cleanup cookie/token.

**Câu 9.** Test tiêm RememberMeAuthenticationToken có chứng minh cookie thật chưa?

**Đáp án:** chưa. Nó chỉ test phân loại/authorization, phải có E2E cookie/token validation.

**Câu 10.** POST trả 403 thì có chắc là do role?

**Đáp án:** không; có thể do CSRF và filter khác. Phải kiểm tra đường xử lý.

## Kết luận

**AuthenticationTrustResolver phân loại trạng thái anonymous và remember-me; ExceptionTranslationFilter dựa vào trạng thái đó để chọn khởi động authentication hay trả forbidden.** Anonymous và remember-me cần nâng mức xác thực thường được hướng tới AuthenticationEntryPoint, còn user đã full login nhưng thiếu quyền thường nhận 403 qua AccessDeniedHandler. Mã HTTP cụ thể phụ thuộc entry point và SecurityFilterChain.

Cấu hình đúng authenticated() và fullyAuthenticated(), bảo vệ remember-me cookie/token, giữ CSRF, và kiểm thử cả MockMvc lẫn request trình duyệt thực. Với hành động nhạy cảm cần thêm **fresh authentication/MFA và kiểm tra quyền trên tài nguyên**, không chỉ phân loại một token.