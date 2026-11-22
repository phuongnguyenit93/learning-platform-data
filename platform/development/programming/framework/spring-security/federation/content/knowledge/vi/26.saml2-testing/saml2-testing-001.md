# Thiết lập MockMvc với Spring Security cho ứng dụng Service Provider

> **Module:** Spring Security – federation · **Chủ đề cha:** Kiểm thử SAML2. Bài Knowledge hướng dẫn thiết lập và sử dụng **MockMvc cùng Spring Security** để kiểm thử một ứng dụng Java Servlet đóng vai **SAML 2.0 Service Provider (SP) / Relying Party (RP)**. Bài phân biệt rõ hai việc rất khác nhau: **giả lập một principal đã xác thực** để kiểm tra controller, filter chain và phân quyền; và **kiểm chứng thực sự SAML Response** từ Identity Provider (IdP) tại Assertion Consumer Service (ACS). Không được suy từ một test `MockMvc.with(authentication(...))` thành kết luận chữ ký SAML, audience, recipient, expiration hay replay protection đã an toàn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích SP/RP, IdP/Asserting Party, `RelyingPartyRegistration`, `RelyingPartyRegistrationRepository`, AuthnRequest, SAMLResponse và ACS.
2. Xác định endpoint mặc định `/saml2/authenticate/{registrationId}` và `/login/saml2/sso/{registrationId}` trong Spring Security 6.x; hiểu rằng cấu hình tùy biến có thể đổi đường dẫn.
3. Thiết lập `spring-boot-starter-test`, `spring-security-test`, `spring-security-saml2-service-provider` và `MockMvc` trên Spring Boot 3.3.x với Java 17.
4. Dùng `@WebMvcTest` hoặc `@SpringBootTest @AutoConfigureMockMvc` đúng mức, giữ Spring `FilterChainProxy` khi test phân quyền.
5. Dùng `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity())` khi tạo MockMvc thủ công; không nhầm với `standaloneSetup` thiếu Spring Security.
6. Tạo `Saml2Authentication` giả trong test qua `DefaultSaml2AuthenticatedPrincipal` và `SecurityMockMvcRequestPostProcessors.authentication(...)`; phân biệt với các processor `user()` và `@WithMockUser`.
7. Viết test cho anonymous redirect, principal, RP registration ID, role/authority, 403, CSRF, POST hành động nhạy cảm và không lộ dữ liệu tenant.
8. Biết cách kiểm tra source IdP và đăng ký RP trong logic ứng dụng, đồng thời không coi field trong mock principal là chữ ký đã được kiểm chứng.
9. Dùng test slice với `@MockBean RelyingPartyRegistrationRepository` khi chỉ kiểm tra controller/security, không gọi IdP thật; hiểu giới hạn của repository mock.
10. Tách unit/slice tests, MockMvc filter-chain tests, ACS validation tests với SAMLResponse **được ký hợp lệ bằng khóa test**, và end-to-end với IdP thật.
11. Nhận diện các lỗi thường gặp: FilterChainProxy không được gắn, @WithMockUser khác SAML principal, 302 thay 401, 403 do CSRF, ACS route sai, chứng thư test hết hạn, key rotation, ký sai, sai audience/destination, Response replay.
12. Thiết kế fixture SAML phù hợp, chạy test bằng Gradle, lập ma trận kiểm thử và ngưỡng QA trước khi đưa SP lên production.

**Nền tảng ví dụ:** Java 17, Spring Boot 3.3.x, Spring Security 6.3.x/6.x, JUnit Jupiter, Mockito và Spring MVC Test. Tên API có thể thay theo Spring Security 7.x; khi nâng version cần kiểm tra lại Javadoc và regression suite. Những URL `.example`/`.test` trong bài là địa chỉ minh họa, không phải IdP hoạt động.

## 2. Bài toán: ứng dụng SP đã login qua SAML2, làm sao test mà không bật IdP?

Một ứng dụng Orders Portal có:
- `GET /health` công khai, dùng health check.
- `GET /api/me` chỉ cho người dùng được SAML2 xác thực từ IdP `corp`.
- `GET /api/admin/report` chỉ cho principal SAML của RP `corp` có local authority `APP_ADMIN`.
- `POST /api/admin/approve` là hành động nhạy cảm, cần same-origin CSRF protection và authority `APP_ADMIN`.
- Dự án production nhận SAML Response từ IdP, link danh tính tới local user và kiểm tra tenant/quyền.

Trong test MVC, ta không muốn mỗi lần chạy JUnit đều cần mở trình duyệt, kết nối IdP, tạo ticket và click login. Ta có thể **dựng trực tiếp một `Saml2Authentication` chỉ trong test** để gọi controller dưới cùng Spring Security filter chain.

Tuy nhiên, test ấy chỉ chứng minh những gì **sau khi authentication đã thành công**:

~~~text
MockMvc request
    |
    +-- with(authentication(fixtureSaml2Auth))
    |          |
    |          +-- SecurityContext cho request test
    |
    +-- Spring Security FilterChainProxy
    |          |
    |          +-- CSRF / authorization / exception translation
    |
    +-- MVC controller
               |
               +-- response/status/body
~~~

Nó **không** tạo `SAMLResponse` ký số hay gọi `OpenSaml4AuthenticationProvider` / parser/validator tại ACS. Vì thế cần các **tầng kiểm thử bổ sung** ở mục 12–14.

## 3. Các thành phần SAML2 nên thấy trong test

| Thành phần | Vai trò thực | Kiểm thử MockMvc nào? |
| --- | --- | --- |
| `RelyingPartyRegistration` | Mô tả SP entity ID, ACS location, IdP entity ID, SSO URL, certificate, signing/decryption policies. | Test cấu hình/metadata/request generation với registration thật. |
| `RelyingPartyRegistrationRepository` | Lưu nhiều registrations, tra theo `registrationId`. | Có thể mock trong test controller; test khác phải có registration thật. |
| `Saml2WebSsoAuthenticationRequestFilter` | Tạo AuthnRequest từ endpoint `/saml2/authenticate/{registrationId}`. | Kiểm tra redirect/Form POST và request params khi dùng fixture RP thật. |
| `Saml2WebSsoAuthenticationFilter` | Nhận `SAMLResponse` tại ACS `/login/saml2/sso/{registrationId}`. | Kiểm thử signed Response fixtures qua `post(...)`, **không bypass** filter. |
| `Saml2AuthenticationToken` | Bọc nội dung Response và registration trước khi xác minh. | Chỉ dùng ở ACS integration test với provider thật. |
| OpenSAML authentication provider | Xác minh signatures, issuer, audience, timing, subject confirmation, decrypt khi cần. | Phải dùng trusted test key, signed assertions/responses, negative fixtures. |
| `Saml2Authentication` | Spring Security `Authentication` **sau** khi SAML2 đã xác thực thành công. | Có thể dựng trực tiếp cho test controller/authorization. |
| `Saml2AuthenticatedPrincipal` | Principal chứa NameID, attributes và `relyingPartyRegistrationId`. | Test principal mapping và quyền, không coi attributes là trusted khi tự dựng. |
| `SecurityFilterChain`/`FilterChainProxy` | CSRF, authorization, sessions, exception handling. | Phải được gắn vào MockMvc thì mới kiểm tra an toàn đường HTTP. |

**Lưu ý phiên bản:** Spring Security 6.3 dùng OpenSAML 4 trong nhiều cấu hình mặc định; các tài liệu của phiên bản mới có thể mô tả OpenSAML 5. Tên class provider chính xác cần đối chiếu dependency tree thay vì hard-code một phiên bản xuyên mọi release.

### 3.1. Một SAML flow đầy đủ

~~~text
Browser -> SP /api/me (chưa có session)
   SP -> /saml2/authenticate/corp
   SP -> IdP SSO endpoint (SAMLRequest/AuthnRequest)
   IdP xác thực user và ký SAML assertion/response
   Browser POST SAMLResponse -> SP /login/saml2/sso/corp
   SP/Spring validate:
     issuer, signature, trust key, InResponseTo, Destination,
     Recipient, Audience, Conditions, SubjectConfirmation, expiry
   SP tạo Saml2Authentication, local identity/role mapping
   Browser có local session -> /api/me
~~~

Chỉ phần **sau khi SP tạo `Saml2Authentication`** được mô phỏng bởi processor `authentication(...)`. Để test các bước trước đó, phải gửi SAML data thực và để filter/provider xử lý.

## 4. Chọn đúng phạm vi kiểm thử

| Tầng | Công cụ | Bằng chứng đạt được | Không đạt được |
| --- | --- | --- | --- |
| Java unit | JUnit, pure Java, Mockito. | Mapping role/tenant và policy thuần. | Không có Servlet filters, HTTP, SAML validation. |
| MVC slice | `@WebMvcTest` + `@Import(SecurityConfig)` + MockMvc. | Controller JSON/status, CSRF và security filter chain được import, principal injection. | Không tự chứng minh signed SAML Response hợp lệ. |
| Full app MockMvc | `@SpringBootTest @AutoConfigureMockMvc`. | ApplicationContext, controllers, filters, persistence test wiring theo cấu hình. | Không tự có IdP/browser/HTTPS thực. |
| ACS protocol integration | MockMvc với RP registration + signed SAML fixtures. | Parser, signatures, issuer, audience, recipient, status/failure handler, session creation. | Không test thật KDC/IdP/browser/proxy ngoài app. |
| Federated end-to-end | Test IdP, browser, SP, TLS, proxy, session store. | Login/logout/metadata/clock/cert rotation qua hệ thống. | Chậm, phụ thuộc môi trường, không thay negative unit tests. |

**Quy tắc:** MockMvc là giao diện HTTP test của Spring MVC. Nó không tự đảm bảo một test đã đi qua đúng SAML filter; chính cách dựng request và SecurityContext quyết định validation path.

## 5. Dependency tối thiểu cho Spring Boot + Spring Security test

### 5.1. Cấu trúc project giáo trình

~~~text
saml-sp-mockmvc/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/spmock/
    │   ├── SpApplication.java
    │   ├── SpSecurityConfig.java
    │   └── SpController.java
    └── test/java/com/example/spmock/
        └── SpMockMvcTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-sp-mockmvc'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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
    // Một số OpenSAML/Shibboleth artifacts cần repository này
    // theo hướng dẫn Spring Security về SAML2 dependencies.
    maven { url 'https://build.shibboleth.net/maven/releases/' }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ở phần `implementation`, **`spring-security-saml2-service-provider`** mang API `Saml2Authentication` và các SAML filters, còn `spring-security-test` mang `SecurityMockMvcRequestPostProcessors.authentication(...)` và `SecurityMockMvcConfigurers.springSecurity()`.

Không import `spring-security-saml2-service-provider` vào một module test không có dependency chính xác rồi cố tạo class thủ công bằng cùng tên. Không dùng package `javax.servlet` khi chạy Spring Boot 3 / Jakarta Servlet.

**Giới hạn của project:** `@WebMvcTest` bên dưới mock `RelyingPartyRegistrationRepository` để tập trung vào các HTTP route sau xác thực. Đó không phải cấu hình SP chạy với IdP thật. Nếu muốn chạy `bootRun`, bổ sung một registration thật và certificate/metadata như mục 11.

## 6. Cấu hình SecurityFilterChain của SP

`src/main/java/com/example/spmock/SpApplication.java`:

~~~java
package com.example.spmock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpApplication {
    public static void main(String[] args) {
        SpringApplication.run(SpApplication.class, args);
    }
}
~~~

`src/main/java/com/example/spmock/SpSecurityConfig.java`:

~~~java
package com.example.spmock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication
        .LoginUrlAuthenticationEntryPoint;

@Configuration(proxyBeanMethods = false)
public class SpSecurityConfig {

    private static boolean approvedSaml(Authentication a) {
        if (!(a instanceof Saml2Authentication saml)
                || !saml.isAuthenticated()) {
            return false;
        }
        if (!(saml.getPrincipal()
                instanceof Saml2AuthenticatedPrincipal principal)) {
            return false;
        }
        return "corp".equals(
            principal.getRelyingPartyRegistrationId()
        );
    }

    private static boolean hasAuthority(
            Authentication a, String permission) {
        return a != null && a.getAuthorities().stream()
            .anyMatch(g -> permission.equals(g.getAuthority()));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error").permitAll()
                .requestMatchers("/saml2/**", "/login/**").permitAll()
                .requestMatchers("/api/admin/**").access(
                    (authSupplier, context) -> {
                        Authentication user = authSupplier.get();
                        return new AuthorizationDecision(
                            approvedSaml(user)
                                && hasAuthority(user, "APP_ADMIN")
                        );
                    }
                )
                .requestMatchers("/api/**").access(
                    (authSupplier, context) ->
                        new AuthorizationDecision(
                            approvedSaml(authSupplier.get())
                        )
                )
                .anyRequest().denyAll()
            )
            .saml2Login(Customizer.withDefaults())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new LoginUrlAuthenticationEntryPoint(
                        "/saml2/authenticate/corp"
                    )
                )
            )
            .build();
    }
}
~~~

**Vì sao kiểm tra `Saml2Authentication` và `registrationId`?**

- `hasAuthority("APP_ADMIN")` một mình chứng minh quyền của một `Authentication` bất kỳ; đôi khi app cần ràng buộc access theo RP/IdP đã duyệt.
- `approvedSaml` kiểm tra authentication đã được đánh dấu authenticated, kiểu principal SAML và registration ID `corp`.
- Đây là **guard thuộc lớp authorization**, không thay thế việc `Saml2WebSsoAuthenticationFilter` xác minh chữ ký SAML trước khi tạo `Saml2Authentication` thật.
- Trong **test**, chúng ta chủ động tạo fixture có registration ID `corp`; đó là dữ liệu giả. Trong **production**, phải giữ SAML protocol validation, trust config, account linking và local authority mapper.
- Controller không nhận quyền admin chỉ dựa NameID/email. `APP_ADMIN` là **local authority mẫu**, cần được cấp từ authorization store được quản trị sau khi xác định đúng local user.
- `/saml2/**` và `/login/**` là routes của SAML security flow; việc permitAll ở tầng URL **không** làm bypass validation của SAML filters. Đừng tự đặt controller nhận `SAMLResponse` rồi trả 200.
- `LoginUrlAuthenticationEntryPoint` cho phép test chính xác redirect của anonymous user tới path phát AuthnRequest. Một SP nhiều IdP thường cần trang lựa chọn hoặc custom entry point.
- `@Configuration` import qua test slice sẽ làm `SecurityFilterChain` thật có hiệu lực. Đừng tắt security filters trong @AutoConfigureMockMvc chỉ vì một test khó chạy.

### 6.1. Điều chỉnh import Java cho dễ sao chép

Java cho phép xuống dòng ở nhiều điểm giữa tokens; nhưng để tránh nhầm và dễ copy, hai `import` nên được viết trên một dòng trong source:

~~~java
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
~~~

Nếu bạn sử dụng nguyên cấu trúc source ở mục 6, hãy thay các `import` được xuống dòng bằng ba dòng trên. Việc định dạng không phải một API khác.

## 7. Controller dùng SAML principal và local permission

`src/main/java/com/example/spmock/SpController.java`:

~~~java
package com.example.spmock;

import java.util.Map;
import org.springframework.security.core.annotation
    .AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication
    .Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SpController {

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(
            @AuthenticationPrincipal
            Saml2AuthenticatedPrincipal principal) {
        return Map.of(
            "subject", principal.getName(),
            "registrationId",
            principal.getRelyingPartyRegistrationId()
        );
    }

    @GetMapping("/api/admin/report")
    public String report() {
        return "report";
    }

    @PostMapping("/api/admin/approve")
    public String approve() {
        return "approved";
    }
}
~~~

Với tệp nguồn thật, dùng các import một dòng:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
~~~

**Lưu ý:** Controller `/api/me` giả định SecurityConfig chỉ cho SAML principal đã approved vào. Nếu ứng dụng có nhiều authentication mechanisms, phải xử lý principal types có chủ đích thay vì casting mù quáng. `principal.getName()` có thể là NameID; trong sản phẩm thật, nên map sang local ID tin cậy, không dùng NameID/email mặc nhiên làm ID phân quyền.

## 8. Test slice: @WebMvcTest + MockMvc + Spring Security

`src/test/java/com/example/spmock/SpMockMvcTests.java`:

~~~java
package com.example.spmock;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet
    .WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority
    .SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication
    .DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication
    .Saml2Authentication;
import org.springframework.security.saml2.provider.service.registration
    .RelyingPartyRegistrationRepository;
import org.springframework.test.web.servlet.MockMvc;

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
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;

@WebMvcTest(controllers = SpController.class)
@Import(SpSecurityConfig.class)
@AutoConfigureMockMvc(addFilters = true)
class SpMockMvcTests {

    @Autowired
    MockMvc mvc;

    // Chỉ mock metadata repository trong tầng controller test.
    // Không gọi IdP thật, không xác minh SAMLResponse thật.
    @MockBean
    RelyingPartyRegistrationRepository registrations;

    static Saml2Authentication saml(
            String registrationId,
            String subject,
            String... permissions) {

        Map<String, List<Object>> attributes =
            Map.of("department", List.of((Object) "orders"));

        DefaultSaml2AuthenticatedPrincipal principal =
            new DefaultSaml2AuthenticatedPrincipal(
                subject, attributes
            );
        principal.setRelyingPartyRegistrationId(registrationId);

        List<GrantedAuthority> authorities = new ArrayList<>();
        for (String permission : permissions) {
            authorities.add(
                new SimpleGrantedAuthority(permission)
            );
        }

        // String này CHỈ lưu trong mock Authentication.
        // Không gửi qua ACS và không phải SAML XML đã ký.
        return new Saml2Authentication(
            principal,
            "<test-only-not-a-real-saml-response/>",
            authorities
        );
    }

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void anonymousIsRedirectedToSamlInitiation() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(
                redirectedUrl("/saml2/authenticate/corp")
            );
    }

    @Test
    void approvedSamlPrincipalCanViewProfile() throws Exception {
        mvc.perform(get("/api/me").with(
                authentication(saml(
                    "corp", "subject-17", "APP_ORDER_READ"
                ))
            ))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("subject-17"))
            .andExpect(jsonPath("$.registrationId").value("corp"));
    }

    @Test
    void samlUserWithoutAdminPermissionGets403() throws Exception {
        mvc.perform(get("/api/admin/report").with(
                authentication(saml(
                    "corp", "subject-17", "APP_ORDER_READ"
                ))
            ))
            .andExpect(status().isForbidden());
    }

    @Test
    void samlAdminFromApprovedRpCanViewReport() throws Exception {
        mvc.perform(get("/api/admin/report").with(
                authentication(saml(
                    "corp", "subject-18", "APP_ADMIN"
                ))
            ))
            .andExpect(status().isOk())
            .andExpect(content().string("report"));
    }

    @Test
    void adminPermissionFromWrongRpGets403() throws Exception {
        mvc.perform(get("/api/admin/report").with(
                authentication(saml(
                    "unapproved", "subject-19", "APP_ADMIN"
                ))
            ))
            .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryMockUserIsNotSamlPrincipal() throws Exception {
        mvc.perform(get("/api/admin/report").with(
                user("fake").roles("ADMIN")
            ))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminPostWithoutCsrfGets403() throws Exception {
        mvc.perform(post("/api/admin/approve").with(
                authentication(saml(
                    "corp", "subject-18", "APP_ADMIN"
                ))
            ))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminPostWithCsrfCanProceed() throws Exception {
        mvc.perform(post("/api/admin/approve")
                .with(csrf())
                .with(authentication(saml(
                    "corp", "subject-18", "APP_ADMIN"
                )))
            )
            .andExpect(status().isOk())
            .andExpect(content().string("approved"));
    }

    @Test
    void csrfDoesNotGrantPermission() throws Exception {
        mvc.perform(post("/api/admin/approve")
                .with(csrf())
                .with(authentication(saml(
                    "corp", "subject-17", "APP_ORDER_READ"
                )))
            )
            .andExpect(status().isForbidden());
    }
}
~~~

Trong tệp Java thực, các `import` bị tách dòng để hiển thị trên Google Sheets có thể được **viết lại trên một dòng**, ví dụ:

~~~java
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.saml2.provider.service.authentication.DefaultSaml2AuthenticatedPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2Authentication;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
~~~

**Quan trọng về cú pháp:** `import` theo Java cho phép whitespace giữa identifier và dấu chấm ở một số vị trí, nhưng **không** cho một dấu chấm bị chèn giữa tên package/class tùy tiện. Để chắc chắn, dùng danh sách import chuẩn một dòng ở trên khi sao chép. Phần thân test sử dụng Java 17, JUnit 5 và MockMvc API của Spring Security 6.x.

### 8.1. Ý nghĩa từng ca kiểm thử

| Test | Điều khẳng định | Không khẳng định |
| --- | --- | --- |
| `healthIsPublic` | Public matcher và controller hoạt động. | Chưa liên quan SAML. |
| `anonymousIsRedirectedToSamlInitiation` | Unauthenticated request được đẩy đến route SAML bắt đầu login. | Không chứng minh AuthnRequest được ký hoặc IdP chấp nhận. |
| `approvedSamlPrincipalCanViewProfile` | Mock Saml2Authentication gắn vào request, controller thấy subject/RP. | Không validate XML/chữ ký. |
| `samlUserWithoutAdminPermissionGets403` | Local authorization chặn principal thiếu quyền. | Không chứng minh quyền từ IdP đã được map đúng. |
| `samlAdminFromApprovedRpCanViewReport` | Policy cho phép principal test có RP+permission. | Không chứng minh attacker không thể giả assertion. |
| `adminPermissionFromWrongRpGets403` | Guard RP registration ID chặn principal test nguồn khác. | Registration ID là test fixture; provider trust phải test riêng. |
| `ordinaryMockUserIsNotSamlPrincipal` | UsernamePasswordAuthenticationToken không thay Saml2Authentication. | Không chứng minh gì về LDAP/password production. |
| `adminPostWithoutCsrfGets403` | CSRF filter chạy ở endpoint nghiệp vụ POST. | Không kiểm chứng ACS CSRF exception hoặc SAML assertion. |
| `adminPostWithCsrfCanProceed` | CSRF + đúng authentication và authority cho phép POST. | Không chứng minh transaction service implementation. |
| `csrfDoesNotGrantPermission` | Có token CSRF không tự cấp `APP_ADMIN`. | Không thay object-level permissions. |

### 8.2. Lệnh chạy

Nếu có Gradle wrapper:

~~~bash
./gradlew test --tests com.example.spmock.SpMockMvcTests
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.spmock.SpMockMvcTests
~~~

**Kỳ vọng:** JUnit chạy 10 test methods, thông thường tất cả xanh nếu dependency, slice configuration và version đúng. Đây là kỳ vọng từ mã mẫu, **không phải khẳng định đã thực thi test trên một repository hoặc IdP thật**. Nếu compilation thất bại sau đổi version, kiểm tra các imports/classes trong `spring-security-saml2-service-provider`, `spring-security-test` và compatibility của Boot/BOM.

## 9. Các kiểu MockMvc setup: không để filter chain biến mất

### 9.1. `@WebMvcTest` và `@AutoConfigureMockMvc`

Trong test slice ở mục 8:

~~~java
@WebMvcTest(controllers = SpController.class)
@Import(SpSecurityConfig.class)
@AutoConfigureMockMvc(addFilters = true)
class SpMockMvcTests {
    @Autowired MockMvc mvc;
}
~~~

- `@WebMvcTest` khởi tạo MVC slice chứ không phải tất cả repositories/services.
- `@Import(SpSecurityConfig.class)` đưa rules và `SecurityFilterChain` của SP vào slice.
- `@AutoConfigureMockMvc(addFilters = true)` chỉ rõ test request phải đi qua Servlet filters.
- `@MockBean RelyingPartyRegistrationRepository` cung cấp collaborator để tạo SAML login filters mà **không cần metadata IdP thật** trong controller tests. Nó không có dữ liệu registration thật và không dùng để test `/saml2/authenticate/corp`.
- Khi cần service/domain logic, dùng `@MockBean` thích hợp và assert interactions/side effects; đừng giả mọi authorization service nếu test định kiểm tra authorization thật.

**Chú ý về phiên bản:** Spring Boot 3.3 có `@MockBean`; ở Boot đời mới có cơ chế mock bean thay thế và deprecation. Khi nâng dependency, áp cách tương đương của phiên bản đã dùng.

### 9.2. `@SpringBootTest @AutoConfigureMockMvc`

Khi test wiring toàn ứng dụng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class FullSpMockMvcIntegrationTests {
    @Autowired MockMvc mvc;
}
~~~

Không cần tạo thêm một `MockMvcBuilders.standaloneSetup(...)` riêng; autoconfigured MockMvc đã tích hợp filters của application context. Phù hợp khi muốn test repository, tenant mapping, real session policy hoặc transaction services.

Nhưng **context đầy đủ có thể cần IdP metadata/certificate**. Dùng test-profile RP registrations/fixtures tin cậy, không gọi IdP production để khởi chạy JUnit. Nếu `@SpringBootTest` đang cố tải metadata từ URL public, tách test configuration ra khỏi production registration.

### 9.3. Tạo MockMvc thủ công đúng cách

Khi tự tạo từ `WebApplicationContext`:

~~~java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;

// Trong @BeforeEach, sau khi @Autowired WebApplicationContext context:
this.mvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Hãy dùng static import một dòng ở file Java thật:

~~~java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
~~~

`springSecurity()` tích hợp bean `springSecurityFilterChain` và Spring Security TestSecurityContext holder vào MockMvc. Khi test dùng `authentication(...)`/`user(...)`, SecurityContext chỉ được truyền vào filter chain đúng khi cấu hình này hoặc sự tích hợp tương đương hoạt động.

**Không thêm `springSecurity()` lặp hai lần** nếu Boot đã tự đăng ký filters; tránh duplicate filtering/CSRF test khó chẩn đoán.

### 9.4. Sai lầm: `standaloneSetup(controller)` rồi tưởng đang test Security

~~~java
// SAI nếu mục tiêu là kiểm thử SecurityFilterChain thật:
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new SpController())
    .build();
~~~

Thiếu `FilterChainProxy`, request có thể vào controller trực tiếp, bỏ qua CSRF/authorization; test `200 OK` khi chưa đăng nhập sẽ tạo **false confidence**.

`standaloneSetup` có thể hữu ích cho unit test MVC thuần, **nhưng phải ghi rõ scope**, không dùng làm bằng chứng phân quyền. Nếu cần filters, ưu tiên `webAppContextSetup(...).apply(springSecurity())` hoặc Boot MockMvc auto-configured.

## 10. Tạo fixture Saml2Authentication đúng loại

### 10.1. Vì sao không chỉ dùng `@WithMockUser`?

`@WithMockUser` tạo một Spring Security `Authentication` cho tên/roles giả (thường kiểu user/password). Nó không mang:
- `Saml2AuthenticatedPrincipal` với attributes SAML;
- `getRelyingPartyRegistrationId()`;
- NameID, SessionIndex trong dữ liệu principal;
- kiểu `Saml2Authentication` của SP.

Nó có thể đủ cho controller chỉ dùng `@PreAuthorize("hasRole(...)")` độc lập protocol, **nhưng không đủ** nếu code thực sự đọc SAML attributes hoặc cần đảm bảo authentication tới từ approved RP.

### 10.2. Dùng `authentication(...)`

~~~java
DefaultSaml2AuthenticatedPrincipal p =
    new DefaultSaml2AuthenticatedPrincipal(
        "subject-17",
        Map.of("department", List.of((Object) "orders"))
    );
p.setRelyingPartyRegistrationId("corp");

Saml2Authentication a = new Saml2Authentication(
    p,
    "<test-only-not-a-real-saml-response/>",
    List.of(new SimpleGrantedAuthority("APP_ORDER_READ"))
);

mvc.perform(get("/api/me").with(authentication(a)))
    .andExpect(status().isOk());
~~~

Phần `saml2Response` string của `Saml2Authentication` là trường dữ liệu bên trong fixture; **constructor không parse/xác minh XML**. Đặt một chuỗi không phải XML SAML thật càng giúp học viên nhớ đây là **test authentication fixture**, không phải một ACS authentication success.

### 10.3. Đặt factories để tránh lặp và giảm false positive

Có thể đưa helper vào `src/test/java/.../SamlFixtures.java`:

~~~java
// MẢNH factory dùng trong test source:
static Saml2Authentication samlReader(
        String relyingParty, String immutableSubject) {
    DefaultSaml2AuthenticatedPrincipal principal =
        new DefaultSaml2AuthenticatedPrincipal(
            immutableSubject,
            Map.of("department", List.of((Object) "orders"))
        );
    principal.setRelyingPartyRegistrationId(relyingParty);
    return new Saml2Authentication(
        principal, "<test-only/>",
        List.of(new SimpleGrantedAuthority("APP_ORDER_READ"))
    );
}
~~~

- Dùng subject/NameID giả nhưng ổn định theo test.
- Quyền `APP_*` trong fixture phải là **local authorities** theo policy app; không copy tin cậy các group strings tùy tiện.
- Test nhiều RP/tenant để thấy các negative cases.
- Không dùng fixture quá mạnh (mặc định admin) cho mọi test vì sẽ che lỗi authorization.
- Không lưu raw SAML Assertion, private key hoặc session token vào test logs ngoài môi trường cô lập.

## 11. AuthnRequest endpoint và RelyingPartyRegistration: test riêng

### 11.1. Endpoint phát AuthnRequest

Đường đi mặc định thường là:

~~~text
GET /saml2/authenticate/corp
     |
     v
Saml2WebSsoAuthenticationRequestFilter
     |
     v
RelyingPartyRegistrationRepository.findByRegistrationId("corp")
     |
     v
Generate SAML2 AuthnRequest
     |
     v
HTTP Redirect to IdP SSO URL
with SAMLRequest + optional RelayState + optional Signature
~~~

Với một registration có request binding HTTP-POST, server có thể trả HTML form auto-submit thay vì Redirect. Đừng viết một test **luôn** mong 302 nếu dự án chọn binding POST.

### 11.2. Test registration thật thay vì Mockito repository trống

Để kiểm tra AuthnRequest, cần registration test cấu hình ít nhất:
- `registrationId=corp`;
- SP `entityId` và ACS URL;
- IdP `entityId`/SingleSignOnServiceLocation`;
- binding yêu cầu;
- ký AuthnRequest nếu IdP bắt buộc, dùng **test signing credential**;
- IdP verification certificate nếu cần dùng cùng registration ở ACS tests.

Spring Security Boot configuration ví dụ:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://idp.example.test/entity"
              singlesignon:
                url: "https://idp.example.test/sso"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:test-idp.crt"
~~~

**`test-idp.crt` phải là certificate fixture thực tế** và signer key tương ứng phải thuộc **test IdP**. Cấu hình này không đầy đủ nếu file chưa được tạo; không copy một certificate không có nguồn hay disable signature checks. Trong production, lấy certificate/metadata chính thức, trust anchor từ IdP được phê duyệt và quản lý rotation.

### 11.3. Mảnh test Redirect binding

Sau khi cung cấp registration thực, có thể test đại ý:

~~~java
// MẢNH integration test; không chạy với @MockBean repo trống.
mvc.perform(get("/saml2/authenticate/corp"))
    .andExpect(status().is3xxRedirection())
    .andExpect(header().string(
        "Location",
        org.hamcrest.Matchers.startsWith(
            "https://idp.example.test/sso?"
        )
    ));
~~~

Cần decode SAMLRequest an toàn (URL-decode, Base64, DEFLATE theo HTTP-Redirect binding) để xác nhận:
- `Issuer` là entity ID của SP theo registration;
- `Destination` là SSO endpoint của IdP được duyệt;
- ACS URL, binding và request ID có format/tính ngẫu nhiên phù hợp;
- Nếu yêu cầu signed requests: kiểm tra signature theo binding profile;
- `RelayState` không dẫn đến open redirect hay session mix-up;
- Nếu có nhiều RP: mọi request dùng đúng issuer/ACS/trust bundle.

**Đừng chỉ assert response 302 rồi kết luận AuthnRequest đã ký và đúng.**

## 12. ACS test: một SAMLResponse giả Base64 không phải authentication success

### 12.1. Endpoint nhận SAMLResponse

Thông thường SP nhận:

~~~http
POST /login/saml2/sso/corp HTTP/1.1
Content-Type: application/x-www-form-urlencoded

SAMLResponse=<Base64-encoded-SAML-Response>
~~~

`Saml2WebSsoAuthenticationFilter` đọc tham số, resolve `RelyingPartyRegistration`, tạo token rồi chuyển cho provider xác minh. Các chi tiết phiên bản/thứ tự có thể thay, nhưng các điều kiện xác minh bảo mật không được bỏ:
- trusted issuer/entity ID và verifying certificate;
- XML signature trên Response/Assertion theo profile;
- audience restriction khớp SP entity ID;
- Destination/Recipient khớp ACS URL;
- InResponseTo/ràng buộc AuthnRequest nếu IdP-initiated/SP-initiated policy;
- Conditions: NotBefore/NotOnOrAfter, SubjectConfirmationData;
- replay/reuse Assertion ID/Response ID theo chính sách và cache;
- subject mapping, tenant isolation, local account status, authority mapping;
- parser chống XXE/oversized XML và giới hạn clock skew được phê duyệt.

### 12.2. Điều không được làm trong test

~~~java
// SAI: gửi Base64 từ XML tự chế rồi mock AuthenticationManager
// trả principal admin và kết luận "đã kiểm chứng chữ ký".
mvc.perform(post("/login/saml2/sso/corp")
    .param("SAMLResponse", base64OfUnsignedXml));
~~~

Một test như vậy có thể hữu ích để đo luồng failure, **nhưng không chứng minh valid assertion**. Nếu thay `AuthenticationManager` bằng Mockito luôn trả success, bạn đang bypass provider — tương tự `with(authentication(...))`.

### 12.3. Tạo signed fixtures đúng chuẩn

Một suite thực sự về SAML validation nên có:
1. Key pair và certificate **dùng trong test**, không phải private key production.
2. RP registration trỏ tới public cert của test IdP.
3. Generator/OpenSAML test utility tạo Assertion với ID unique, Issuer, Subject, SubjectConfirmation, AudienceRestriction, timestamps và signature theo binding/profile.
4. Một fixture valid được **ký bởi test private key** và phù hợp chính xác issuer/ACS.
5. Negative cases bằng cách đổi **một thuộc tính sau khi ký** hoặc ký lại bằng untrusted key, bảo đảm mỗi lỗi thực sự được provider phát hiện.
6. Tránh tái sử dụng cùng Response ID trong các test mà replay cache giữ state, trừ test replay cố ý.
7. Dùng test-only clock/cert lifecycle để tránh fixture tự hết hạn và tạo flaky tests.
8. Assertions về **không có authenticated session/security context** khi validate thất bại, không chỉ check 302/400/401 mặc định.

### 12.4. Mẫu request test với valid fixture được tạo trước

~~~java
// MẢNH, yêu cầu fixture signedSamlResponseBase64()
// thật từ test IdP/OpenSAML generator.
MvcResult result = mvc.perform(
    post("/login/saml2/sso/corp")
        .param("SAMLResponse", signedSamlResponseBase64())
).andReturn();

// Kiểm tra authentication success handler/session semantics
// theo config thực tế của dự án.
// Không hard-code status 200/302 khi success handler tùy biến.
~~~

Đối với SP-initiated SSO, trước POST cần có AuthnRequest và **session state/request repository** tương ứng để InResponseTo hợp lệ. Nếu test chỉ POST một assertion do IdP tạo mà chưa có request, kết quả phụ thuộc deployment có hỗ trợ unsolicited/IdP-initiated SSO hay không. Đừng “sửa” test bằng cách tắt InResponseTo validation bừa bãi.

### 12.5. Phân biệt CSRF tại ACS và tại business API

SAML POST từ browser do IdP điều hướng thường **không mang CSRF token của ứng dụng**. Spring SAML2 login config thiết lập cách xử lý ACS phù hợp protocol; nó dựa trên kiểm chứng SAML Response/relay state chứ không dựa vào form CSRF token thông thường.

Ngược lại, `POST /api/admin/approve` là hành động nghiệp vụ dùng local session cookie, **phải** giữ CSRF protection. Test `.with(csrf())` cho business POST không chứng minh ACS có CSRF token, và việc miễn CSRF đúng SAML endpoint không cho phép tắt CSRF toàn app.

## 13. Principal attributes, quyền và tenant trong tests

### 13.1. SAML attributes có thể đa giá trị

`Saml2AuthenticatedPrincipal#getAttributes()` trả về map attribute → list các giá trị. Ví dụ một IdP có thể phát:

~~~text
NameID: opaque-subject-17
registrationId: corp
attributes:
  department: ["orders"]
  groups: ["employee", "approver"]
  tenant: ["company-A"]
~~~

Đừng tự ép mọi attribute thành String đơn nhất. `getFirstAttribute(...)` tiện khi profile bảo đảm một giá trị, còn group membership có thể đa giá trị.

### 13.2. Authentication ≠ authorization

Một mock principal có `groups=["admin"]` do test tự đặt **không** chứng minh IdP thật có quyền cấp `APP_ADMIN`. Production nên:
1. Xác minh issuer/SAML Assertion.
2. Map external stable ID tới local user bằng khóa đã duyệt, không chỉ email.
3. Kiểm tra local account enabled, tenant membership, lifecycle.
4. Nạp local permissions/roles từ authorization store.
5. Áp resource-specific `AuthorizationManager` và method security.
6. Kiểm tra object-level tenant ownership (ví dụ order phải thuộc tenant của người dùng).

Trong test slice, `APP_ADMIN` là local fixture mô phỏng kết quả mapper. Cần test mapper bằng Mockito/database/fixtures riêng, không trộn vào `Saml2Authentication` từ nguồn không tin.

### 13.3. Cross-tenant negative test

Nếu có hai registrations `corp-A` và `corp-B`, cần đảm bảo:
- callback của IdP A không được đọc local users của B chỉ vì NameID/email giống;
- test principal có RP B không được vào endpoint RP A;
- authority của một tenant không tự cấp quyền ở tenant khác;
- `registrationId` chỉ là internal lookup ID, không phải chứng cứ criptographic nếu tự dựng từ HTTP query chưa verify.

### 13.4. Gắn session khi test nhiều requests

`authentication(...)` thông thường đưa Authentication vào **một request test**. Nó không tự giả lập end-to-end session từ SAML ACS. Nếu muốn test session persistence thật, hãy:
- dùng full MockMvc + authenticated ACS flow và giữ `MockHttpSession` từ response;
- kiểm tra tiếp request với `.session(session)`;
- xác minh logout invalidates session/CSRF, session fixation rotation;
- không tạo session mới cho mỗi request rồi tuyên bố session persistence đã pass.

Cùng một `SecurityContext` trong test JVM không chứng minh session cookie qua browser hay reverse proxy sẽ được bảo vệ đúng; phải có integration/e2e tests.

## 14. Test status, redirect, security matchers và success handlers

### 14.1. Test 302 đúng kỳ vọng, không gắn “302 = lỗi”

Một unauthenticated request tới resource được bảo vệ bằng SAML2 thường nhận redirect sang `/saml2/authenticate/{registrationId}` hoặc trang chọn IdP; một test kỳ vọng `401` vì quen API Basic/Bearer có thể sai.

- Browser HTML: 302/303 dẫn sang login có thể đúng.
- Machine API: thường nên trả 401/403 JSON hoặc Bearer challenge nếu contract quy định, không đưa client vào IdP HTML redirect.
- Sau login thành công: custom success handler, saved request hoặc landing page quyết định Location.
- Sau login thất bại: failure handler có thể redirect `/login?error`; status 302 không chứng minh validation success.

### 14.2. Filter ordering khi có nhiều chains

Với `@Order` và `securityMatcher`, **chain đầu tiên match** quyết định filters. Một SAML ACS callback có thể vô tình rơi vào API stateless chain, bị 401/403, hoặc không thấy SAML2 filter.

Kiểm thử:
- `GET /api/me` match đúng browser SP chain;
- `POST /login/saml2/sso/corp` được SAML filter nhận;
- `GET /saml2/authenticate/corp` được AuthnRequest filter xử lý;
- `POST /api/admin/approve` vẫn có CSRF và authorization;
- `GET /actuator/health` không bị SAML redirect khi policy công khai cho health.

### 14.3. SecurityContext và tests dễ tạo false pass

Một test đặt SecurityContext tĩnh toàn JVM rồi quên clear có thể làm request sau nhận Authentication từ test trước. Dùng `spring-security-test` processors/@WithMockUser với teardown mặc định, tránh tự dùng `SecurityContextHolder.setContext` toàn cục mà không cleanup.

Không dùng `MockMvcResultMatchers.status().isOk()` làm assertion duy nhất cho endpoint nhạy cảm: assert cả principal, tenant, local permission và response không chứa dữ liệu của người khác.

## 15. Java 17 độc lập: minh họa ma trận quyết định sau SAML validation

Ví dụ dưới chạy **JDK 17 độc lập**, giúp thấy policy SP hoạt động sau khi IdP đã xác minh principal. Nó không giả lập MockMvc hoặc xác minh XML; phần MockMvc thật nằm ở mục 8. Dùng nó để dạy rằng RP, authority và tenant cần được kiểm tra đồng thời.

### 15.1. `SamlSpAuthorizationDemo.java`

~~~java
public final class SamlSpAuthorizationDemo {

    record SamlEvidence(
        boolean samlValidated,
        String relyingPartyRegistrationId,
        String userTenant,
        boolean localAccountActive,
        boolean hasAdminPermission) {
    }

    enum Decision {
        ALLOW, DENY_UNVERIFIED, DENY_WRONG_RP,
        DENY_DISABLED, DENY_TENANT, DENY_PERMISSION
    }

    static Decision decide(
            SamlEvidence e, String requiredTenant) {
        if (!e.samlValidated()) {
            return Decision.DENY_UNVERIFIED;
        }
        if (!"corp".equals(e.relyingPartyRegistrationId())) {
            return Decision.DENY_WRONG_RP;
        }
        if (!e.localAccountActive()) {
            return Decision.DENY_DISABLED;
        }
        if (!requiredTenant.equals(e.userTenant())) {
            return Decision.DENY_TENANT;
        }
        if (!e.hasAdminPermission()) {
            return Decision.DENY_PERMISSION;
        }
        return Decision.ALLOW;
    }

    static void show(String scenario, SamlEvidence e) {
        System.out.println(scenario + "=" +
            decide(e, "tenant-A"));
    }

    public static void main(String[] args) {
        show("happyPath", new SamlEvidence(
            true, "corp", "tenant-A", true, true));
        show("invalidResponse", new SamlEvidence(
            false, "corp", "tenant-A", true, true));
        show("wrongRp", new SamlEvidence(
            true, "external", "tenant-A", true, true));
        show("disabledAccount", new SamlEvidence(
            true, "corp", "tenant-A", false, true));
        show("crossTenant", new SamlEvidence(
            true, "corp", "tenant-B", true, true));
        show("missingRole", new SamlEvidence(
            true, "corp", "tenant-A", true, false));
    }
}
~~~

### 15.2. Biên dịch, chạy, stdout

~~~bash
javac --release 17 SamlSpAuthorizationDemo.java
java SamlSpAuthorizationDemo
~~~

**Stdout xác định:**

~~~text
happyPath=ALLOW
invalidResponse=DENY_UNVERIFIED
wrongRp=DENY_WRONG_RP
disabledAccount=DENY_DISABLED
crossTenant=DENY_TENANT
missingRole=DENY_PERMISSION
~~~

Giới hạn: `samlValidated` là fixture test của bài Java, không phải request parameter được user cung cấp; RP/tenant/permissions đều phải lấy từ server-side trusted validation và repository. Mã này **không chứng minh chữ ký SAML an toàn**, chỉ chứng minh thứ tự các authorization decisions được mong muốn.

## 16. Test fixtures chuẩn và an toàn

### 16.1. Cần các fixtures nào?

| Fixture | Dùng trong test | Tránh lỗi |
| --- | --- | --- |
| SAML principal đã xác thực giả | Controller/authorization MockMvc slice. | Không suy nó đi qua signature validation. |
| RelyingPartyRegistration `corp` | AuthnRequest/ACS tests. | Endpoint, Issuer/ACS trust và cert phải khớp. |
| Test IdP RSA/EC key + X.509 cert | Ký signed Response/Assertion. | Không dùng production keys/private metadata. |
| Valid SP-initiated Response | ACS happy path có AuthnRequest correlation. | InResponseTo và Session state phải hợp lệ. |
| Unsigned Response/Assertion | Negative signature test. | Phải bị reject; không mock validator luôn success. |
| Wrong Audience | AudienceRestriction test. | Chỉ thay giá trị có chủ đích trong fixture. |
| Wrong Recipient/Destination | ACS routing validation. | Không “fix” bằng tắt destination checks. |
| Expired/NotYetValid | Time validation. | Dùng controlled clock hoặc tạo fixture theo thời gian. |
| Unknown issuer/untrusted signer | Trust boundary. | Không lấy trust cert từ Response tùy ý. |
| Replay Response/Assertion | Replay protection. | Cache state phải tồn tại giữa hai lần gửi. |
| Cross-RP/tenant subject | Identity mapping/authorization. | Không gộp NameID/email giữa IdPs. |

### 16.2. Không chép SAMLResponse thật vào source

SAML Assertion có thể chứa NameID, email, group, session details và sensitive attributes. Tránh lưu full production SAMLResponse trong test resources/Git. Tạo fixture với test subjects và test certificates. Không log toàn bộ XML, decrypted assertions hoặc raw SessionIndex ở CI artifacts công khai.

### 16.3. Cert rollover

Nếu IdP thay signing certificate, cần tests cho:
- cert cũ/trust overlap trong giai đoạn chuyển tiếp;
- cert mới được cấu hình hợp lệ;
- cert chưa được tin bị reject;
- certificate hết hạn hoặc thỏa thuận trust không đúng;
- signing credential cho AuthnRequest khác verification credential cho Response;
- encrypted assertions chỉ mở được bằng private key SP tương ứng, không dùng signing cert của IdP để decrypt.

MockMvc slice với `authentication(...)` sẽ **không** phát hiện rollover failure. Đây là lý do cần tầng ACS signed fixture riêng.

## 17. Ma trận kiểm thử QA cho SP

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| M01 | `@WebMvcTest` có import SecurityConfig và addFilters=true. | Filter chain thực chạy trong MVC slice. |
| M02 | MockMvc tạo thủ công nhưng thiếu `springSecurity()`. | Test phải phát hiện thiếu filter/false pass, không dùng để chứng minh security. |
| M03 | `GET /health` anonymous. | 200 theo public policy. |
| M04 | `GET /api/me` anonymous. | Redirect/challenge đúng entry point; không trả 200. |
| M05 | `Saml2Authentication` fixture RP=corp hợp lệ. | Principal injection đúng NameID/RP. |
| M06 | `@WithMockUser` dùng thay SAML principal. | Test phải thể hiện khác kiểu; không vượt SAML-only guard. |
| M07 | Saml2Authentication có RP khác corp. | 403 ở route hạn chế RP. |
| M08 | SAML principal corp thiếu `APP_ADMIN`. | 403 admin route. |
| M09 | SAML principal corp có local `APP_ADMIN`. | 200 admin route nếu policy khác đạt. |
| M10 | `POST /api/admin/approve` không CSRF. | 403. |
| M11 | POST có `with(csrf())` nhưng thiếu permission. | 403. |
| M12 | POST có CSRF + đúng permission. | 200/action authorized trong fixture. |
| M13 | SAML principal cùng NameID nhưng tenant khác. | Deny cross-tenant theo domain policy. |
| M14 | RP registration repository không có `corp` cho AuthnRequest. | Initiation fail; không giả 302 success. |
| M15 | GET SAML auth initiation với RP thật, Redirect binding. | IdP URL + SAMLRequest đúng config. |
| M16 | SAML AuthnRequest có wrong Issuer/ACS. | QA fail khi decode request. |
| M17 | Invalid/unknown registrationId. | Không chọn arbitrary IdP/registration. |
| M18 | ACS nhận signed Response hợp lệ từ test IdP. | Xác thực và session theo success handler. |
| M19 | ACS nhận unsigned Response/Assertion. | Reject, không tạo authenticated session. |
| M20 | ACS ký bằng untrusted key. | Reject. |
| M21 | ACS có sai issuer. | Reject. |
| M22 | ACS sai Destination/Recipient. | Reject. |
| M23 | ACS wrong AudienceRestriction. | Reject. |
| M24 | ACS expired NotOnOrAfter. | Reject. |
| M25 | ACS NotBefore trong tương lai ngoài clock skew. | Reject. |
| M26 | ACS InResponseTo không khớp outstanding request. | Reject theo SP-initiated policy. |
| M27 | ACS unsolicited IdP-initiated khi policy không cho. | Reject. |
| M28 | ACS gửi lại Response/Assertion ID cũ. | Replay bị chặn theo anti-replay policy. |
| M29 | ACS có XML Entity/oversized payload. | Parser từ chối; không làm sập service. |
| M30 | Signed response chứa multi-valued attributes. | Mapper phân tích đúng profile, không cấp role sai. |
| M31 | IdP group “admin” nhưng local account không có admin. | Không tự cấp `APP_ADMIN`. |
| M32 | Local account disabled sau SAML login. | Reauthorization/session revocation theo policy. |
| M33 | Same NameID từ hai IdPs. | Không tự link cùng local user. |
| M34 | Response có email trùng local account nhưng stable ID khác. | Không auto-link. |
| M35 | Multi-chain: ACS callback bị API chain chiếm. | Test phát hiện 401/403 và sửa matcher. |
| M36 | Multi-chain: business POST vô tình exempt CSRF. | QA fail. |
| M37 | SAML login success handler redirect arbitrary external URL. | Không open redirect; allowlist/saved request. |
| M38 | Local session sau ACS được dùng lại trên request khác. | Session persistence đúng, không chạy lại IdP khi session hợp lệ. |
| M39 | Logout local invalidate session; request cũ không còn quyền. | Deny/redirect theo policy. |
| M40 | Session ID rotation sau SAML login. | Có chống session fixation theo cấu hình. |
| M41 | Certificate rollover với new signer trusted. | Signed fixture mới pass, old/untrusted theo overlap policy. |
| M42 | Invalid/assertion decryption failed. | Reject, không cấp Authentication. |
| M43 | Response valid nhưng local account/tenant sai. | Authentication IdP không vượt local authorization. |
| M44 | MockMvc test dùng `authentication(...)` rồi đánh dấu signature QA pass. | **QA FAIL về phạm vi test**; phải có signed fixture. |
| M45 | SP metadata phát sai ACS/public host sau proxy. | Detect metadata mismatch/trust configuration. |
| M46 | Missing spring-security-test dependency. | Compiler không có `authentication(...)`/`csrf()` processor. |
| M47 | Spring Security version đổi OpenSAML provider API. | Build/test/upgrade review, không bỏ validator. |
| M48 | CI chạy tests mà cần IdP production đang online. | QA fail về tính độc lập, dùng test IdP/fixtures. |

### 17.1. Kiểm tra bắt buộc trước khi merge PR

1. **Controller slice:** các test M01–M13, assertions về body/status/authorities.
2. **AuthnRequest integration:** endpoint, destination, issuer, ACS, binding, RelayState, signature nếu cần.
3. **ACS provider integration:** valid signed fixture, signature fail, trust, audience, destination, time, replay, subject confirmation.
4. **Identity mapping:** issuer/SP-scoped stable ID → local user ID; không auto-link email; local enabled + role + tenant.
5. **Sessions:** CSRF ở business API, fixation, saved request, logout, persistence.
6. **Infrastructure:** reverse proxy Host/X-Forwarded trust, public metadata, TLS certificate, cert rotation.
7. **CI artifacts:** không log raw SAMLResponse/token/private key; test fixture là dữ liệu giả và không cần production IdP.

## 18. Troubleshooting MockMvc và SAML2

### 18.1. Test anonymous trả 200 thay vì redirect

**Nguyên nhân thường thấy:** tạo `MockMvcBuilders.standaloneSetup(controller)` nên SecurityFilterChain không chạy; hoặc `@AutoConfigureMockMvc(addFilters=false)`; hoặc route được permitAll do matcher sai.

**Cách sửa:** dùng `@WebMvcTest + @Import(SecurityConfig)`, `@AutoConfigureMockMvc(addFilters=true)` hoặc `webAppContextSetup(...).apply(springSecurity())`. Kiểm tra endpoint đúng matcher và test không có authentication được leak từ test khác.

### 18.2. `@WithMockUser` dẫn tới ClassCastException/null principal

**Nguyên nhân:** Controller yêu cầu `Saml2AuthenticatedPrincipal`, nhưng @WithMockUser cung cấp principal dạng khác.

**Cách sửa:** dùng `authentication(new Saml2Authentication(...))` cho test SAML-specific. Nếu controller hỗ trợ nhiều loại login, viết mapper chung theo trusted local user ID và test các paths rõ ràng.

### 18.3. POST business API luôn 403 dù có APP_ADMIN

**Nguyên nhân:** CSRF filter đang chặn; 403 có thể xảy ra **trước** authorization business.

**Cách sửa:** thêm `.with(csrf())` cho request nghiệp vụ được phép, sau đó vẫn test case thiếu permission. **Không** tắt CSRF toàn ứng dụng để test xanh.

### 18.4. POST ACS trả 403 khi không có CSRF

**Nguyên nhân:** SAML2 filter không được cấu hình/không match path, hoặc SAML config CSRF exemption đã bị override, callback rơi vào chain sai.

**Cách sửa:** xác định ACS URL có đúng `loginProcessingUrl`, `Saml2WebSsoAuthenticationFilter` có trong chain, Spring `saml2Login` được cấu hình và profile SAML POST thực hiện protocol validation. Không permit arbitrary unvalidated POST chỉ để hết 403.

### 18.5. Test mock principal 200 nhưng IdP thật login không được

**Nguyên nhân:** mock bypass chữ ký/timestamps/issuer/audience, còn production SAML provider reject sai certificate, ACS, clock, InResponseTo hoặc key rotation.

**Cách sửa:** thêm signed fixture ACS tests, metadata agreement và e2e test với test IdP. Không đổi verify certificate thành cert attacker hoặc disable signature validation.

### 18.6. `No qualifying bean of type RelyingPartyRegistrationRepository`

**Nguyên nhân:** Spring Context có `saml2Login()` nhưng thiếu registration config/bean, hoặc slice test đã import security config mà không cung cấp collaborator.

**Cách sửa:** test slice dùng `@MockBean RelyingPartyRegistrationRepository` khi chỉ kiểm tra controller; ACS/AuthnRequest test dùng registration thật/certificate test. Đừng dùng Mockito repo trống cho test muốn generate AuthnRequest.

### 18.7. 302 nhưng Location không như dự đoán

**Nguyên nhân:** có nhiều IdPs, redirect tới login picker, custom entrypoint, saved request hoặc forwarded base URL khác.

**Cách sửa:** xác định entrypoint thật; chỉ assert URL đúng contract của app. Test `Location` sau SAML2 initiation có thể chứa SAMLRequest/RelayState/Signature; không so sánh full URL string có random ID/time.

### 18.8. Tests đôi lúc pass, đôi lúc fail

**Nguyên nhân:** stale SecurityContext/session, time-sensitive SAML fixtures, shared replay cache, random request IDs, expired cert, global test state hoặc chạy đồng thời dùng một principal ID.

**Cách sửa:** mỗi test có fresh fixture/nonce/clock, isolated session/replay store, teardown context đúng, không phụ thuộc production IdP hoặc dữ liệu môi trường.

## 19. Câu hỏi tự đánh giá

**1. `MockMvc.with(authentication(saml2Auth))` có kiểm chứng chữ ký XML không?**  
Không. Nó gắn Authentication do test tự dựng vào SecurityContext và bỏ qua SAML ACS validation.

**2. Vì sao cần `spring-security-test`?**  
Để dùng MockMvc Spring Security configurers và request processors như `authentication()`, `user()`, `csrf()`.

**3. Khi nào dùng `springSecurity()`?**  
Khi tự dựng MockMvc từ WebApplicationContext; nó gắn Spring Security filter chain/test holder. Với MockMvc đã được Boot auto-configure có filters, không gắn lặp.

**4. Vì sao `@WithMockUser` không đủ cho controller đọc SAML attributes?**  
Principal và Authentication type thường không phải Saml2AuthenticatedPrincipal/Saml2Authentication.

**5. Test nhận 302 ở protected page có đồng nghĩa login SAML2 thành công?**  
Không. Có thể chỉ là redirect bắt đầu SSO hoặc redirect do login thất bại.

**6. Test `with(csrf())` có kiểm chứng SAML Response hay không?**  
Không. CSRF bảo vệ thao tác browser app; SAML Response cần signature/recipient/audience/subject confirmation validation.

**7. Dùng `@WebMvcTest` có test toàn IdP flow không?**  
Không. Nó là MVC slice; ACS signed fixtures và e2e test phải nằm ở lớp riêng.

**8. Một unsigned SAMLResponse Base64 chứa NameID có được app nhận không?**  
Phải bị từ chối bởi validation thật; không được mock provider always-success khi test bảo mật.

**9. Một principal test có `registrationId=corp` chứng minh issuer đáng tin?**  
Không. Đó chỉ là field test tự gán. Provider phải xác minh issuer/trust thực tế.

**10. Có thể dùng `standaloneSetup` để test logic controller thuần không?**  
Có, nhưng không coi là test Spring Security authorization/filters nếu không gắn FilterChainProxy đúng cách.

**11. Khi đổi certificate IdP, test nào phát hiện lỗi?**  
ACS integration với signed fixtures/credential rotation; test fixture Saml2Authentication trực tiếp sẽ không phát hiện.

**12. Một response SAML valid có tự cấp APP_ADMIN?**  
Không. Cần local account linking và quyền ứng dụng được cấp theo chính sách.

## 20. Checklist hoàn tất

- [ ] Project dùng JDK 17+, Spring Boot/Spring Security tương thích, dependencies test đúng BOM.
- [ ] Có `spring-boot-starter-test` và `spring-security-test` cho JUnit/MockMvc.
- [ ] SAML SP support dùng `spring-security-saml2-service-provider`, cấu hình OpenSAML/Shibboleth artifact repository khi dependency cần.
- [ ] Test slice có `@Import(SecurityConfig)` và `@AutoConfigureMockMvc(addFilters=true)` hoặc cấu hình tương đương.
- [ ] Manual MockMvc dùng `webAppContextSetup(context).apply(springSecurity())`; không bỏ FilterChainProxy.
- [ ] Test security không dùng `standaloneSetup` không filters như bằng chứng an toàn.
- [ ] Dùng `authentication(Saml2Authentication)` khi cần SAML-specific principal/registration ID/attributes.
- [ ] Phân biệt fixture đã authenticate giả với signed SAMLResponse thật.
- [ ] `@WithMockUser` chỉ dùng khi authentication type không phải mục đích kiểm thử.
- [ ] Có tests anonymous, SAML principal, wrong RP, no permission, admin permission, CSRF POST và 403.
- [ ] Test controller không cần IdP thật; `@MockBean` RP repository chỉ dùng trong lớp phù hợp.
- [ ] Test AuthnRequest dùng registration thực và kiểm tra issuer/ACS/destination/signature theo binding.
- [ ] Test ACS dùng signed fixture với trust cert test, không mock provider always-success.
- [ ] Negative ACS tests gồm unsigned, wrong issuer/audience/destination, expiry, InResponseTo, replay và untrusted cert.
- [ ] Một RP registration không được chọn từ untrusted browser input; tenant isolation được kiểm thử.
- [ ] Stable external ID được map tới local account; email/NameID không tự thành role admin.
- [ ] Business POST có CSRF; SAML ACS xử lý theo protocol và filter chain đúng path.
- [ ] Các tests không phụ thuộc production IdP, private keys hay SAMLResponse có PII.
- [ ] Session fixation, logout, session persistence và account revocation có integration tests riêng.
- [ ] Có CI cho M01–M48 hoặc test coverage tương đương, báo cáo đúng phạm vi test.
- [ ] Khi nâng Spring Boot/Security/OpenSAML, kiểm tra imports, API và rerun SAML regression.
- [ ] Không bao giờ tuyên bố “SAML signature QA PASS” chỉ vì MockMvc request được gắn `Saml2Authentication`.

## Ghi nhớ

> **MockMvc + Spring Security** là công cụ mạnh để kiểm tra **controller, SecurityFilterChain, phân quyền, CSRF và phản hồi HTTP của ứng dụng SAML2 Service Provider**. Dùng `@WebMvcTest`/`@SpringBootTest` với filter chain thật và `authentication(new Saml2Authentication(...))` cho các bài test đã-authenticated. Nhưng **mock principal không xác minh SAML Response**: chữ ký, issuer, audience, recipient, expiry, InResponseTo và replay phải được test riêng bằng **ACS protocol tests với signed fixtures** và test IdP thật khi phù hợp.

### Tài liệu tham khảo chính thức

- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html): tích hợp `MockMvcBuilders.webAppContextSetup(...).apply(springSecurity())`.
- [Spring Security — Running as a User in MockMvc Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `authentication(...)`, `user(...)`, `@WithMockUser` và SecurityContext.
- [Spring Security — CSRF MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())`.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/RP, registration, AuthnRequest, ACS và SAML authentication.
- [Spring Security — SAML2 AuthnRequest](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): request generation and destination/binding.
- [Spring Security — SAML2 Response Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): default ACS, signature/condition checks, principal/authorities.
- [Spring Security 6.3 — Saml2Authentication Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/saml2/provider/service/authentication/Saml2Authentication.html): constructor `(principal, response, authorities)`.
- [Spring Security 6.x — DefaultSaml2AuthenticatedPrincipal Javadoc](https://docs.spring.io/spring-security/site/docs/6.4.10/api/org/springframework/security/saml2/provider/service/authentication/DefaultSaml2AuthenticatedPrincipal.html): NameID, attributes và registrationId.
- [Spring Security — Servlet Architecture / Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter ordering, SecurityFilterChain matching.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@WebMvcTest`/`@SpringBootTest`/`@AutoConfigureMockMvc`.
- [OASIS SAML V2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): assertions, audience, issuer, conditions và subject confirmation.
- [OASIS SAML V2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO, InResponseTo, bindings và SP/IdP flow.
