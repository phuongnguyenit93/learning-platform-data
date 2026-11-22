# Tự quản lý tài khoản hay tích hợp nhà cung cấp danh tính

## 1. Quyết định về nơi quản lý danh tính

Khi xây một ứng dụng với Spring Security, đội phát triển phải quyết định: **tự quản lý tài khoản và mật khẩu** hay **đăng nhập qua nhà cung cấp danh tính (Identity Provider, IdP)**? Đây không chỉ là lựa chọn giao diện đăng nhập. Quyết định này ảnh hưởng đến bảo mật, dữ liệu, hỗ trợ người dùng, MFA, vòng đời nhân sự, tính sẵn sàng và khả năng tích hợp những hệ thống khác.

Ba kiến trúc hay gặp:

- **Local identity:** ứng dụng sở hữu user store, lưu hash mật khẩu, xác thực đăng nhập và quản lý reset, thay đổi credential, khóa tài khoản, phiên làm việc.
- **Federated identity/SSO:** IdP bên ngoài xác thực người dùng; ứng dụng nhận thông tin đã được xác minh qua giao thức như **OpenID Connect (OIDC)** hoặc **SAML 2.0**, sau đó xử lý quyền nghiệp vụ của chính mình.
- **Hybrid:** IdP phụ trách xác thực nhưng ứng dụng vẫn có ID người dùng nội bộ, quyền theo tenant và hồ sơ; có thể tồn tại một luồng local riêng cho nhóm được cho phép theo chính sách.

**Không có phương án an toàn tuyệt đối trong mọi trường hợp.** Một hệ thống local được thiết kế tốt có thể phù hợp với một sản phẩm độc lập; một IdP được cấu hình đúng có thể giảm đáng kể gánh nặng quản lý credential, đặc biệt với SSO và MFA. Nhưng một IdP cấu hình sai hoặc tự động cấp quyền admin dựa vào email cũng có thể tạo lỗ hổng nghiêm trọng.

Nguyên tắc xuyên suốt: **IdP hoặc local login chỉ chứng minh danh tính; chính ứng dụng vẫn phải kiểm tra người đó có quyền làm gì trên tài nguyên nào.**

## 2. Phân biệt authentication, identity, authorization và token

| Thuật ngữ | Ý nghĩa | Ví dụ trong Spring Security |
| --- | --- | --- |
| **Identity** | Bản ghi định danh một người hoặc service | User ID nội bộ, subject do IdP phát hành |
| **Credential** | Yếu tố dùng để chứng minh danh tính | Password, passkey, MFA factor, session credential |
| **Authentication** | Kiểm chứng credential rồi tạo danh tính cho request | `AuthenticationManager`, `UserDetailsService`, OIDC login |
| **Authorization** | Quyết định action được phép trên resource | `hasRole`, `AuthorizationManager`, kiểm tra owner/tenant |
| **Identity Provider (IdP)** | Hệ thống xác thực user và phát thông tin danh tính | OIDC Provider, SAML IdP |
| **OIDC client/relying party** | Ứng dụng nhờ IdP đăng nhập | Spring `oauth2Login()` trên web app |
| **Authorization server** | Hệ thống phát token cho OAuth2 | Token endpoint của nền tảng identity |
| **Resource server** | API xác minh access token trước khi cho request qua | Spring `oauth2ResourceServer().jwt()` |
| **Provisioning** | Tạo, cập nhật, khóa hoặc xóa tài khoản được sử dụng ở app | JIT provisioning, SCIM, invitation |
| **SSO** | Dùng một danh tính để truy cập nhiều ứng dụng | Nhiều app đăng nhập qua cùng IdP |

**OAuth2 không tự đồng nghĩa với đăng nhập.** OAuth2 tập trung vào **ủy quyền truy cập** và cấp access token; **OIDC** xây thêm lớp xác thực trên OAuth2, trong đó có ID token và những quy tắc xác minh danh tính. Một API có thể dùng OAuth2 Resource Server để nhận access token mà không hề có trang đăng nhập OIDC.

**ID token khác access token.** ID token chứng minh thông tin xác thực cho OIDC client; access token được thiết kế cho resource server/API. Không gửi ID token của một client sang API khác rồi dùng như Bearer token nếu API không được thiết kế và xác minh đúng token đó.

## 3. Bảng so sánh trách nhiệm của hai mô hình

| Câu hỏi | Tự quản lý tài khoản | Tích hợp IdP |
| --- | --- | --- |
| Ai lưu password? | App lưu **password hash** và quản lý thay đổi | IdP quản lý credential; app không cần nhận password IdP |
| Ai cung cấp MFA/passkey? | App phải tự triển khai/tích hợp | Thường IdP hỗ trợ chính sách tập trung |
| Ai xử lý quên password? | App thiết kế reset token, email và quy trình xác minh | IdP thường cung cấp recovery |
| Nhiều ứng dụng dùng chung đăng nhập? | Phải xây SSO hoặc lặp tài khoản | Dùng federation/SSO qua cùng IdP |
| Khóa nhân viên nghỉ việc? | App cần cơ chế khóa và thu hồi quyền | IdP giúp quản trị tập trung, app vẫn xử lý session/token |
| Ai kiểm soát quyền xem dữ liệu? | App | **App vẫn phải kiểm soát** |
| Dễ tùy biến giao diện login? | Cao hơn, đồng nghĩa tự chịu rủi ro | Phụ thuộc khả năng tùy biến của IdP |
| IdP/network gặp sự cố? | Không phụ thuộc IdP bên ngoài | Login mới có thể bị ảnh hưởng |
| Chi phí? | Xây dựng, vận hành, support và bảo mật | Phí dịch vụ, tích hợp, quản trị, migration |
| Dữ liệu nghiệp vụ? | App quản lý | App vẫn thường quản lý |
| Di chuyển hệ thống? | Cần migration user/password hash | Cần migration issuer, subject, account linking, role mapping |

Một đội ngũ thường đánh giá sai chi phí local identity nếu chỉ tính vài ngày làm form login. Chi phí thực tế bao gồm bảo vệ credential store, chống credential stuffing, MFA, khôi phục tài khoản, thông báo sự cố, thay đổi password, phiên đăng nhập, khóa và hỗ trợ người dùng.

Mặt khác, dùng IdP không loại bỏ các chi phí trong ứng dụng: quản lý quyền theo bản ghi, ánh xạ tenant, cấp quyền admin, onboarding, xử lý tài khoản trùng, logout, audit và hỗ trợ trường hợp IdP không khả dụng.

## 4. Kiến trúc local account: những gì phải tự chịu trách nhiệm

Một ứng dụng local account phải thiết kế đầy đủ vòng đời:

1. **Đăng ký:** xác minh thuộc tính cần thiết (ví dụ email) và chống đăng ký tự động hoặc chiếm tên.
2. **Lưu credential:** dùng hash thích ứng như bcrypt, scrypt, PBKDF2 hoặc Argon2 theo chính sách phù hợp, salt và work factor; không lưu plaintext hoặc hash nhanh SHA-256 đơn thuần.
3. **Đăng nhập:** HTTPS, xử lý password sai không làm lộ danh sách tài khoản, rate limiting và bảo vệ khỏi credential stuffing.
4. **MFA/passkey:** lựa chọn phương án xác thực nhiều yếu tố với luồng thiết lập và khôi phục an toàn.
5. **Quên/đổi mật khẩu:** token ngẫu nhiên, thời hạn ngắn, giới hạn một lần, thu hồi/re-auth khi cần.
6. **Session:** chống session fixation, cookie `Secure`/`HttpOnly`/`SameSite` thích hợp, idle/absolute timeout, logout, CSRF cho form và yêu cầu thay đổi trạng thái.
7. **Vòng đời tài khoản:** khóa hoặc xóa theo chính sách, xác minh email mới, đổi role, audit và thông báo liên quan.
8. **Giám sát:** đăng nhập bất thường, tấn công theo credential, sự kiện khóa/mở, rò rỉ dữ liệu, reset hàng loạt.
9. **Phân quyền:** không tin role/owner/tenant do browser gửi; kiểm tra trong service theo user đã xác thực.

Spring Security có `PasswordEncoder`, `AuthenticationProvider`, `UserDetailsService`, form login, CSRF và các thành phần bảo mật nền tảng. **Spring Security không tự cung cấp một sản phẩm quản trị danh tính hoàn chỉnh** với toàn bộ đăng ký, recovery, MFA, support và quy trình tuân thủ cho ứng dụng của bạn.

### Luồng login local điển hình

```text
Browser -> GET /me
    -> Spring Security thấy chưa xác thực
    -> redirect tới /login
Browser -> POST /login (username, password, CSRF)
    -> authentication filter / authentication manager
    -> UserDetailsService tải account
    -> PasswordEncoder so khớp password với hash
    -> Authentication thành công
    -> SecurityContext và session web phù hợp
    -> authorizeHttpRequests / method security / service policy
    -> endpoint được phép hoặc bị từ chối
```

Ở bước so khớp, server có thể tạm nhận password trong request, nên **không log password**. Password hash trong database là dữ liệu cần bảo vệ, không được xem là vô hại. Sau login, browser dùng session cookie thay vì gửi lại password với từng request trong mô hình form session.

## 5. Ví dụ runnable trong dự án: tự quản lý login bằng Spring Security

Dựng một dự án Spring Boot **3.x**, Spring Security **6.x**, Java **17+**, Servlet/MVC, gồm dependencies **Spring Web** và **Spring Security** (chọn Gradle khi tạo qua Spring Initializr). Tạo tệp:

```text
src/main/java/demo/localidentity/LocalIdentityApplication.java
```

Toàn bộ mã:

```java
package demo.localidentity;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LocalIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(LocalIdentityApplication.class, args);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @RestController
    public static class Endpoints {
        @GetMapping("/public")
        public Map<String, String> publicEndpoint() {
            return Map.of("message", "open");
        }

        @GetMapping("/me")
        public Map<String, String> me(Authentication authentication) {
            return Map.of(
                "user", authentication.getName(),
                "message", "authenticated"
            );
        }

        @GetMapping("/admin")
        public Map<String, String> admin() {
            return Map.of("message", "admin-only");
        }
    }
}
```

**Đây là chương trình chạy được trong dự án có Spring Boot/Security**; `javac` độc lập sẽ không có classpath phù hợp. Tài khoản in-memory chỉ dành cho localhost và học tập; không thể coi là giải pháp user store production.

- `InMemoryUserDetailsManager` cung cấp user cho hệ thống xác thực. Khi lưu user thật, có thể thay bằng repository/JDBC/LDAP hoặc `UserDetailsService` tùy chỉnh và vẫn dùng `PasswordEncoder` đúng chuẩn.
- `DelegatingPasswordEncoder` giúp dùng định dạng hash có tiền tố thuật toán, hỗ trợ chiến lược nâng cấp. Khi lưu user thật, **hash khi tạo hoặc đổi password**, không hash lại mỗi lần tải user từ DB.
- `formLogin()` tạo luồng login dựa trên session, trang login mặc định và điểm xử lý gửi credential. Demo không tự viết controller POST password.
- `hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN`. Đã đăng nhập là `reader` chưa đủ để mở `/admin`.
- **Không vô hiệu hóa CSRF** trong demo. Form login có cơ chế kiểm tra CSRF; sản phẩm phải thiết kế CSRF phù hợp cách dùng cookie/session.

Chạy:

```bash
./gradlew bootRun
# Windows PowerShell:
# .\gradlew.bat bootRun
```

Kiểm tra trình duyệt (nên mở phiên riêng tư mới khi đổi tài khoản):

| Thao tác | Kết quả dự kiến |
| --- | --- |
| GET `/public` không login | HTTP 200, JSON `{"message":"open"}` |
| GET `/me` không login | HTTP 302 tới `/login`, rồi trang login hiển thị |
| Login `reader / reader123`, mở `/me` | 200, user `reader` |
| `reader` mở `/admin` | 403 |
| Login `admin / admin123`, mở `/admin` | 200, JSON `{"message":"admin-only"}` |

`curl -i http://localhost:8080/me` cho phép xem 302 đầu tiên. Đừng dùng mật khẩu mẫu trên mạng thật; HTTP Basic hay form login đều cần HTTPS trong production.

### Test phân quyền local bằng MockMvc

Thêm `spring-boot-starter-test` và `spring-security-test` trong `build.gradle` của dự án đã tạo:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo `src/test/java/demo/localidentity/LocalIdentityApplicationTests.java`:

```java
package demo.localidentity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LocalIdentityApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk());
    }

    @Test
    void privateEndpointRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void readerCannotOpenAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin-only"));
    }
}
```

Chạy `./gradlew test`, kỳ vọng bốn test pass nếu cấu hình đúng. Đây **không phải stdout đã đo** trong bài học. `user(...)` tạo danh tính test để thử phân quyền, **không tự chứng minh password thật đã được xác minh**. Muốn kiểm tra credential flow, bổ sung integration tests cho form login đúng/sai, CSRF, session lifecycle và account khóa.

## 6. IdP: giao xác thực cho một hệ thống chuyên dụng

Tích hợp IdP thường được ưu tiên khi có SSO doanh nghiệp, MFA/passkey tập trung, nhiều ứng dụng chia sẻ danh tính, khách hàng B2B muốn dùng tài khoản của họ hoặc khi đội ứng dụng không muốn vận hành password store.

Với OIDC trên ứng dụng server-side, luồng ý tưởng là:

```text
Browser -> /me (chưa có session app)
Spring Security -> redirect tới /oauth2/authorization/corp
Browser -> IdP authorization endpoint
IdP -> kiểm tra user, MFA và chính sách
IdP -> redirect về /login/oauth2/code/corp với code + state
Spring Security OAuth2 Client:
    kiểm tra state, đổi code, xử lý và xác minh ID token
    tạo Authentication cho web app và session phù hợp
Ứng dụng:
    ánh xạ issuer + subject -> user ID nội bộ
    kiểm tra trạng thái, tenant và quyền nghiệp vụ
    trả tài nguyên được phép
```

Authorization Code và PKCE có vai trò bảo vệ luồng phù hợp loại OAuth2 client; `state` và OIDC `nonce` giải quyết những ràng buộc khác nhau. Không bỏ qua các bước kiểm chứng chỉ để chữa redirect/callback lỗi. **Không tự viết endpoint callback rồi tin chuỗi `code` hay nội dung JWT chưa xác minh.**

### 6.1. Ví dụ ứng dụng OIDC Spring Boot

Tạo **một dự án riêng** với Spring Boot 3.x, Java 17+, **Spring Web**, **Spring Security**, **OAuth2 Client**. Đặt file:

```text
src/main/java/demo/oidc/OidcIdentityApplication.java
```

```java
package demo.oidc;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OidcIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcIdentityApplication.class, args);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }

    @RestController
    public static class Endpoints {
        @GetMapping("/")
        public Map<String, String> home() {
            return Map.of("message", "public");
        }

        @GetMapping("/me")
        public Map<String, String> me(
                @AuthenticationPrincipal OidcUser user) {

            String issuer = String.valueOf(
                user.getIdToken().getClaims().get("iss")
            );
            return Map.of(
                "issuer", issuer,
                "subject", user.getSubject()
            );
        }
    }
}
```

Ví dụ này **chạy đăng nhập chỉ khi đã kết nối được IdP OIDC hợp lệ**; nó là chương trình Spring Boot đầy đủ nhưng không thể mô phỏng IdP thật nếu chỉ có mã Java. Trong sản phẩm, hạn chế trả claim/token ra frontend để debug; endpoint `/me` nên trả profile tối thiểu và internal user ID khi đã liên kết danh tính.

Cấu hình `src/main/resources/application.properties`:

```properties
spring.security.oauth2.client.registration.corp.client-id=${OIDC_CLIENT_ID}
spring.security.oauth2.client.registration.corp.client-secret=${OIDC_CLIENT_SECRET}
spring.security.oauth2.client.registration.corp.scope=openid,profile
spring.security.oauth2.client.provider.corp.issuer-uri=${OIDC_ISSUER_URI}
```

Các giá trị ở `${...}` trong đoạn trên là **placeholder biến môi trường của Spring Boot**, ví dụ `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` và `OIDC_ISSUER_URI`. Cấp chúng từ secret manager/environment phù hợp, không commit client secret vào Git hoặc log ra console.

Với registration ID `corp`, redirect URI mặc định thường là:

```text
http://localhost:8080/login/oauth2/code/corp
```

Đăng ký URI này chính xác ở IdP cho môi trường local; production cần HTTPS và callback allowlist. Cấu hình wildcard hoặc redirect tùy ý làm tăng nguy cơ lộ authorization code.

Mở `http://localhost:8080/me` khi chưa có session: app đưa người dùng qua IdP. Sau xác thực OIDC thành công, kết quả có `issuer` và `subject` được Spring Security lấy từ ID token đã xử lý. **Phải liên kết hai giá trị với user ID nội bộ trước khi cấp quyền dữ liệu nghiệp vụ.**

### 6.2. Không tự có ROLE_ADMIN sau OIDC login

OIDC login cho biết một user đã được xác thực. Spring Security có thể gắn authority như `OIDC_USER`; điều đó **không phải `ROLE_ADMIN` của ứng dụng**. Nếu chỉ cấu hình `.hasRole("ADMIN")` mà chưa có nguồn role nội bộ hoặc mapping authority được tin cậy, người dùng đăng nhập IdP thành công vẫn có thể nhận 403, và đây là việc bảo vệ đúng.

Nguồn quyền có thể là bảng user–tenant–role trong app, dịch vụ quản trị quyền hoặc claim/group của IdP được **xác minh và map bằng allowlist**. Không tự cấp ADMIN vì email có đuôi thuộc một domain hoặc do frontend gửi query `role=ADMIN`.

### 6.3. OIDC login không phải Resource Server JWT

| Vai trò | Cấu hình Servlet Spring Security | Credential |
| --- | --- | --- |
| OIDC web login | `oauth2Login(Customizer.withDefaults())` | Browser redirect/callback, ID token được OIDC client xử lý |
| REST API nhận JWT | `oauth2ResourceServer(o -> o.jwt(...))` | `Authorization: Bearer ...` với access token |
| API nhận opaque token | `oauth2ResourceServer(o -> o.opaqueToken(...))` | Bearer token cần introspection/validation |
| Web form local | `formLogin(...)` | Form username/password với CSRF và session |

Một đoạn cấu hình minh họa **trong dự án Resource Server khác**:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
```

Với dependency `spring-boot-starter-oauth2-resource-server` và cấu hình:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=${API_ISSUER_URI}
```

Đây là **đoạn cấu hình có điều kiện, không phải file Java độc lập**. Resource Server phải xác minh chữ ký, issuer, thời hạn và **audience/loại token/scopes đúng hợp đồng API**. Cấu hình issuer mặc định không bảo đảm mọi yêu cầu audience của sản phẩm đã tự được thiết lập; bổ sung validator và test. **Không coi ID token dành cho web app là Bearer token dành cho API khác.**

## 7. Hybrid: IdP phụ trách credential, ứng dụng phụ trách hồ sơ và quyền

Một hệ thống thực tế thường có:

- **IdP** xác thực người dùng, quản lý credential và MFA.
- **Ứng dụng** quản lý `app_user_id`, trạng thái user, membership theo tenant, role, chủ sở hữu tài nguyên, hạn chế hoạt động, audit nghiệp vụ.
- **Bảng liên kết** ánh xạ danh tính ngoài vào user nội bộ.

Ví dụ schema khái niệm:

```sql
CREATE TABLE app_users (
    id UUID PRIMARY KEY,
    status VARCHAR(24) NOT NULL
);

CREATE TABLE external_identities (
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    app_user_id UUID NOT NULL REFERENCES app_users(id),
    PRIMARY KEY (issuer, subject)
);

CREATE TABLE tenant_memberships (
    app_user_id UUID NOT NULL REFERENCES app_users(id),
    tenant_id UUID NOT NULL,
    role VARCHAR(64) NOT NULL,
    PRIMARY KEY (app_user_id, tenant_id)
);
```

Đây là schema minh họa, không phải migration production đầy đủ: cần thêm chính sách uniqueness, index, lifecycle, soft delete, history và quyền quản trị phù hợp.

**Tại sao dùng (issuer, subject)?** Trong OIDC, `sub` định danh subject ở phạm vi issuer. Hai IdP khác nhau có thể phát hành cùng chuỗi `sub` cho hai người khác nhau. Email/tên đăng nhập lại có thể đổi, được tái sử dụng hoặc có trạng thái chưa được xác minh.

```text
(issuer-A, subject-123) -> app-user-10
(issuer-B, subject-123) -> app-user-27

app-user-10 và app-user-27 không mặc nhiên là một người.
```

Không tự động merge hai account chỉ vì **email trùng nhau**. Một IdP được cấu hình yếu hoặc tài khoản email thay đổi có thể khiến người khác chiếm quyền account nội bộ. Account linking phải có quy trình **xác minh quyền kiểm soát danh tính cũ và mới**, đồng ý của user khi thích hợp, audit và khả năng khôi phục.

### Luồng JIT provisioning có kiểm soát

1. Spring Security xác minh OIDC login thành công.
2. Lấy cặp `issuer + subject` từ danh tính đã xác minh, không lấy từ query client.
3. Tìm liên kết trong `external_identities` và lấy internal ID nếu đã có.
4. Nếu chưa có, áp dụng **quy tắc onboarding**: invitation, tenant đã xác minh, email verification hoặc chính sách tổ chức phù hợp; không phải provider nào cũng được tự tạo account.
5. User mới nên có quyền tối thiểu hoặc trạng thái chờ phê duyệt, không tự cấp ADMIN.
6. Kiểm tra trạng thái user và membership khi truy cập tài nguyên; role từ IdP không tự thay thế owner/tenant policy.
7. Khi xóa/khóa user ở IdP, đồng bộ hoặc kiểm tra lại quyền app theo SLA/nhu cầu revoke đã thiết kế.

Nếu thay đổi IdP (ví dụ sáp nhập doanh nghiệp), đừng cập nhật account cũ bằng cách nối email theo heuristic. Cần migration có proof, cutover và audit; dữ liệu nghiệp vụ nên giữ `app_user_id` ổn định.

## 8. SSO, phiên đăng nhập, logout và thu hồi quyền

**SSO không có nghĩa mọi ứng dụng dùng chung một session.** Browser có thể có phiên IdP và từng app có session riêng. Logout trong một ứng dụng thường kết thúc phiên ứng dụng đó; nó không nhất thiết xóa phiên IdP hoặc mọi phiên của ứng dụng khác. Tương tự, một người bị khóa ở IdP chưa chắc lập tức mất mọi session/token đã phát hành trước đó.

Thiết kế rõ:

- Thời hạn session, idle timeout, re-authentication cho tác vụ nhạy cảm.
- Cookie attributes, session fixation protection, CSRF với browser session.
- Revocation khi người dùng nghỉ việc, quyền admin bị thu hồi hoặc có sự cố.
- Single logout/front-channel/back-channel logout chỉ khi IdP và app thực sự hỗ trợ, kiểm thử đúng luồng.
- Khi token có thời gian sống dài, chính sách giảm quyền có thể cần kết nối trạng thái account/membership hiện tại thay vì chỉ tin role cũ nằm trong token.
- Với API resource server, token hết hạn/sai audience/issuer phải bị từ chối, bất kể người dùng có session website khác hay không.

**IdP outage:** phân biệt việc **đăng nhập mới** bị chặn với **phiên đã tồn tại** có thể tiếp tục đến khi hết hạn. JWT có thể được kiểm tra với khóa công khai đã cache theo cấu hình hợp lệ; opaque token có thể phụ thuộc introspection. Không tự động mở "bypass login" nếu IdP không truy cập được. Nếu cần tài khoản break-glass vận hành, phải có scope, MFA, audit và quy trình khẩn cấp riêng, không dùng một admin/password mặc định chia sẻ.

## 9. Các lỗi bảo mật cần kiểm tra khi chọn mô hình

| Sai lầm | Hậu quả |
| --- | --- |
| Lưu password plaintext hoặc hash nhanh SHA-256 | Rủi ro khi rò credential store |
| Không bảo vệ reset password | Chiếm tài khoản mà không biết password cũ |
| Bật login nhưng bỏ kiểm tra owner/tenant | Broken Object Level Authorization |
| Tin email trùng nhau để tự link account | Account takeover |
| Tin claim role chưa được xác minh | Leo thang quyền |
| Chỉ decode JWT, không verify chữ ký/issuer/expiry | Token giả hoặc token từ hệ khác được chấp nhận |
| Bỏ qua audience của access token | API chấp nhận token dành cho resource khác |
| Mở redirect URI wildcard | Rò authorization code, chuyển hướng sai đích |
| Để client secret trong Git/log | Credential leak |
| Dùng ID token như access token của API | Sai đối tượng nhận và ràng buộc token |
| Tắt CSRF mọi endpoint browser vì đang dùng IdP | Nguy cơ request giả mạo qua session/cookie |
| Xóa session app rồi coi IdP đã logout mọi nơi | Sai kỳ vọng Single Logout |
| Dùng cùng client registration/secret mọi môi trường | Tăng ảnh hưởng khi secret lộ |
| IdP outage thì tự cấp bypass admin | Bỏ qua authentication |
| Không cập nhật trạng thái user khi rời tổ chức | Phiên/role app còn hiệu lực ngoài ý muốn |

**Luôn phân quyền theo dữ liệu nghiệp vụ.** `ROLE_USER` hay việc login thành công không chứng minh quyền đọc từng hóa đơn, hồ sơ, tài liệu. Quy tắc owner, tenant và action phải được kiểm tra ở backend.

## 10. Ma trận kiểm thử hệ thống danh tính

Đừng chỉ thử "đăng nhập thành công thì trang chủ trả 200". Cần chứng minh các lớp riêng:

| Tầng | Khi tự quản lý | Khi dùng IdP |
| --- | --- | --- |
| Xác thực | Password đúng/sai, account disable, reset, lockout | OIDC redirect, callback, state/nonce, ID token validation |
| Phân quyền | USER không truy cập ADMIN/owner khác | OIDC user hợp lệ nhưng không có role vẫn 403 |
| Phiên | Cookie, CSRF, session expiry, logout | App session, IdP session, logout phạm vi được hứa |
| Danh tính | User ID nội bộ đúng với credentials | Issuer + subject đúng, không ghép bằng email |
| Provisioning | Đăng ký và khóa user | JIT invitation, SCIM/lifecycle, membership |
| API | Access token nếu có được xác minh đúng | JWT/opaque token đúng issuer/audience/expiry/scope |
| Vận hành | Password recovery, credential stuffing | IdP outage, key rotation, migration, revocation |

Những test âm tính quan trọng:

1. Anonymous gọi tài nguyên riêng tư → 401 hoặc 302 tới login, tùy giao diện.
2. User đã xác thực thiếu quyền admin → 403.
3. Người dùng tenant A yêu cầu tài nguyên tenant B → bị từ chối.
4. Hai IdP phát cùng `sub` → không nhập thành một account.
5. Email OIDC trùng account local → không tự liên kết.
6. Token sai issuer/audience hoặc hết hạn → API từ chối.
7. OIDC callback state sai hoặc authorization code không hợp lệ → không cấp phiên.
8. Tài khoản IdP bị khóa, app session còn tồn tại → hành vi phản ánh chính sách thu hồi đã được thiết kế.
9. IdP không khả dụng → không mở đường bypass login.
10. POST trong ứng dụng dùng cookie không có CSRF token → từ chối đúng chính sách.

**Mock login khác kiểm chứng nhà cung cấp thật.** `@WithMockUser`, `user()`, `oidcLogin()`, `mockJwt()` trong `spring-security-test` phù hợp để kiểm thử authentication context/authorization trong app, nhưng không tự chứng minh password thật, ký token, OIDC discovery hay token endpoint đã hoạt động. Thêm integration/e2e tests với môi trường test IdP có cấu hình tin cậy khi cần.

## 11. Gợi ý lựa chọn theo bối cảnh

| Hệ thống | Điểm xuất phát thường đáng đánh giá | Phần vẫn tự xây |
| --- | --- | --- |
| Một app nhỏ độc lập | Local account hoặc managed consumer identity tùy năng lực đội | Phân quyền và bảo vệ dữ liệu |
| Bộ ứng dụng nội bộ doanh nghiệp | OIDC/SAML qua IdP của doanh nghiệp | Role/membership, session và access policy |
| B2B SaaS nhiều công ty | Federated IdP theo tenant + app user nội bộ | Tenant isolation, invitation, mapping quyền |
| Consumer app cần social login | OIDC với provider phù hợp; có thể thêm local | Linking, privacy, support, recover |
| API cho mobile/SPA và service khác | OAuth2 resource server/authorization server phù hợp | Token audience/scope validation, owner/tenant |
| Môi trường yêu cầu hoạt động offline | Đánh giá local hoặc cơ chế identity offline được quản trị | Credential/revoke/sync, rủi ro stale quyền |

Đặt thêm các câu hỏi:

- Ai là chủ của user: tổ chức nhân sự, khách hàng B2B hay nền tảng của chúng ta?
- Có bắt buộc SSO, MFA, passkey, device policy hay đồng bộ offboarding?
- Dữ liệu nào ứng dụng thực sự cần giữ để phục vụ nghiệp vụ?
- Ai có quyền cấp/revoke ADMIN hoặc quyền theo tenant?
- Có yêu cầu lưu trữ dữ liệu theo khu vực, thời gian giữ và khả năng export không?
- Khi IdP lỗi, ứng dụng nên hành xử ra sao với login mới và session hiện tại?
- Khi thay IdP, dữ liệu và quan hệ liên kết account sẽ được chuyển thế nào?
- Đội ứng dụng có đủ năng lực vận hành password store, MFA, reset và ứng phó sự cố nếu chọn local?

Đừng so sánh chỉ mức giá subscription IdP với chi phí viết vài form đăng nhập. Hãy so sánh **tổng chi phí sở hữu, rủi ro, vòng đời người dùng và năng lực vận hành**.

## 12. Checklist triển khai sản phẩm

- [ ] Ghi rõ hệ thống nào xác thực user: local, OIDC/SAML hoặc hybrid.
- [ ] Định nghĩa user ID nội bộ và mapping external identity bằng `issuer + subject`.
- [ ] Chỉ tin thông tin ID/role/tenant sau khi được xác minh và ánh xạ qua nguồn đáng tin.
- [ ] Với local account, dùng password hashing phù hợp, MFA/rate limit/reset/session protection.
- [ ] Với IdP, khóa redirect URI, client registration và secret; kiểm tra state/nonce/issuer/token đúng mô hình.
- [ ] Phân biệt OIDC web login với OAuth2 Resource Server của API.
- [ ] Quy định cách cấp quyền, giới hạn tenant, owner và quyền admin độc lập với việc đăng nhập.
- [ ] Thiết kế provisioning, account linking, account disabled, migration và offboarding.
- [ ] Thiết kế CSRF/CORS/session/cookie và logout đúng đặc tính client.
- [ ] Có kế hoạch xử lý IdP outage, rotate key/secret và thu hồi quyền.
- [ ] Kiểm thử cả luồng hợp lệ lẫn account takeover, user trùng email, token sai audience và cross-tenant.
- [ ] Chỉ log dữ liệu audit cần thiết, không log password, ID/access/refresh token, cookie hoặc client secret.

**Kết luận:** lựa chọn tự quản lý tài khoản nghĩa là nhận toàn bộ trách nhiệm bảo vệ credential và vòng đời đăng nhập. Tích hợp IdP chuyển đáng kể phần xác thực sang nền tảng chuyên dụng nhưng **không chuyển quyền quyết định nghiệp vụ**. Thiết kế thường bền vững khi ứng dụng có **user ID nội bộ**, IdP cung cấp danh tính đã xác minh, và mọi quyền trên dữ liệu được kiểm tra bởi backend.

### Tài liệu tham khảo

- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — OAuth2 Client and Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
