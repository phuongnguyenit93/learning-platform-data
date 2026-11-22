# Phân biệt người dùng tương tác với tài khoản dịch vụ

## 1. Tại sao thiết kế bảo mật cần phân biệt hai loại danh tính?

Một ứng dụng Spring Security thường phục vụ đồng thời hai nhóm tác nhân:

- **Người dùng tương tác (interactive user):** một người thật đăng nhập, thao tác trên trình duyệt hoặc ứng dụng di động, có thể cần MFA, thông báo xác nhận, phiên, chuyển hướng, đăng xuất và quản lý quyền theo người dùng.
- **Tài khoản dịch vụ (service account / workload identity):** danh tính được cấp cho tiến trình, job, container, microservice hoặc hệ thống tích hợp để gọi API tự động; nó không có người ngồi trước màn hình để nhập mật khẩu, giải CAPTCHA, xác nhận MFA hoặc mở trang đăng nhập.

Ví dụ trong một hệ thống quản lý đơn hàng:

```text
Nhân viên vận hành
   -> Trình duyệt -> /ui/orders
   -> Đăng nhập tương tác; cookie/session; quyền theo nhân viên

Worker đồng bộ tồn kho
   -> API HTTP -> /api/m2m/inventory-sync
   -> Danh tính workload; access token ngắn hạn; quyền theo dịch vụ

Dịch vụ thanh toán
   -> API HTTP -> /api/m2m/payment-events
   -> Danh tính dịch vụ khác; scope và audience riêng
```

Nếu tất cả tiến trình đều sử dụng tài khoản người dùng như `admin@example.com` hoặc một username/password dùng chung, hệ thống gặp nhiều vấn đề: khó truy vết ai thực hiện, khó thu hồi riêng một tích hợp, MFA dễ bị bỏ qua, mật khẩu phải lưu trong cấu hình hoặc pipeline và dịch vụ có thể được cấp quyền con người rộng hơn mức cần thiết.

**Nguyên tắc:** *Danh tính phản ánh chủ thể thực hiện hành động.* Người dùng tương tác là một người; service account là một workload. Quyền được cấp theo công việc thực tế và **không tự động chuyển từ loại danh tính này sang loại kia**.

Bài học thuộc **Spring Security – fundamentals / Thiết kế ứng dụng**, trình bày cách phân biệt mô hình, cơ chế xác thực/phân quyền, thiết kế endpoint, quản lý vòng đời credential và kiểm thử. Ví dụ dựa trên **Java 17+, Spring Boot 3.x, Spring Security 6.x Servlet**. Với WebFlux, cần dùng `SecurityWebFilterChain` và các API reactive tương ứng.

## 2. So sánh người dùng tương tác và tài khoản dịch vụ

| Tiêu chí | Người dùng tương tác | Tài khoản dịch vụ |
| --- | --- | --- |
| Chủ thể | Một người, có quy trình onboarding/offboarding và có thể được xác minh danh tính. | Một ứng dụng, worker, deployment, job hoặc tích hợp có chủ sở hữu vận hành. |
| Thời điểm hoạt động | Khi người dùng mở trang, đăng nhập, bấm nút. | Theo lịch, hàng đợi, sự kiện hoặc lời gọi tự động 24/7. |
| Hình thức xác thực thường gặp | Form login + session, passkey, federated OIDC Authorization Code + PKCE. | OAuth 2.0 Client Credentials, mTLS/workload identity, token do nền tảng cấp. |
| Thành phần cung cấp credential | Người dùng và thiết bị/trình duyệt tin cậy theo mô hình. | Runtime/secret manager/identity provider của workload. |
| MFA | Có thể bắt buộc theo rủi ro và chính sách con người. | Không yêu cầu một người nhập OTP mỗi lần job chạy; dùng bảo mật danh tính workload. |
| Phiên | Thường có cookie phiên, CSRF, logout, timeout. | Thường gọi API bằng bearer token ngắn hạn trong header, không cần phiên browser. |
| Quyền | Role/permission theo người và ngữ cảnh nghiệp vụ. | Scope/permission theo dịch vụ, API, môi trường và tác vụ. |
| Khả năng thu hồi | Khóa tài khoản, đổi mật khẩu, revoke session/token người dùng. | Vô hiệu client/workload, xoay secret/chứng chỉ, revoke token và thay deployment. |
| Truy vết | Ai đã thao tác, trên đối tượng gì, với ngữ cảnh phiên nào. | Workload/client nào đã gọi, thuộc deployment nào, tác vụ gì. |
| Trình duyệt | Có thể render UI, redirect, CORS, cookie, SameSite, CSRF. | Không cần trang login, cookie trình duyệt hoặc redirect tới IdP để lấy token. |
| Kiểm thử | Login, MFA/session, CSRF, quyền người dùng, logout. | Token issuance, issuer/audience/scope/client identity, rotation, access denied. |

Không phải mọi hệ thống đều dùng chính xác hai dạng trên: ứng dụng di động có người dùng tương tác nhưng API vẫn có thể được gọi qua bearer access token; service account có thể dùng certificate thay vì JWT; một người có thể khởi chạy một job mang quyền ủy quyền. Vì vậy, **loại chủ thể và cách vận chuyển token là hai khía cạnh khác nhau**. Không kết luận “JWT luôn là service” hoặc “cookie luôn là người dùng” chỉ từ kỹ thuật truyền credential.

## 3. Phân biệt authentication, principal, authorities và authorization

Spring Security xây dựng ngữ cảnh bảo mật trên đối tượng `Authentication`:

- `principal` biểu diễn danh tính đã xác thực. Với form login có thể là `UserDetails`; với JWT Resource Server thường là `Jwt` thông qua `JwtAuthenticationToken`.
- `credentials` biểu diễn vật liệu xác thực đầu vào. Ứng dụng không nên log hoặc hiển thị giá trị này.
- `authorities` là tập quyền đã chuyển đổi, ví dụ `ROLE_USER` hoặc `SCOPE_jobs.write`.
- `Authentication.isAuthenticated()` biểu diễn trạng thái xác thực của token tương ứng; **không tự đủ** để quyết định quyền. Anonymous authentication có những đặc điểm riêng và không được xem là người dùng đã đăng nhập chỉ vì một flag.
- `AuthorizationManager` hoặc biểu thức phân quyền xét **principal, authorities, request và chính sách** để cho phép/từ chối thao tác.

Ví dụ người dùng và dịch vụ có thể cùng mang quyền chung `read`, nhưng điều đó không có nghĩa cả hai được phép thao tác trên cùng endpoint. Nhiều ứng dụng cần **hai điều kiện đồng thời**:

1. **Đúng loại danh tính** (human hoặc service) được nhà phát hành đáng tin cậy chứng nhận.
2. **Đúng quyền và phạm vi tài nguyên** (scope, role, audience, tenant, đối tượng) được phép.

Một service token có `SCOPE_jobs.write` không được phép thay thế session người dùng để truy cập trang quản trị; một người dùng có `ROLE_USER` cũng không mặc nhiên được phép gửi job tự động đến endpoint M2M.

### 3.1. Tên claim không phải tiêu chuẩn chung

Trong token JWT, `sub` (subject) là claim chuẩn nhưng **không đủ để suy luận chủ thể là người hay máy**. Một nhà cung cấp có thể đặt `sub` bằng user ID, một nhà cung cấp khác bằng client ID hoặc service principal ID. Các claim `client_id`, `azp`, `scp`, `scope` và `grant_type` có quy ước phụ thuộc nhà phát hành và giao thức; **không được mặc định rằng mọi access token đều có đủ các trường đó**.

Nếu hệ thống cần kiểm tra loại chủ thể trực tiếp, hãy thống nhất với Identity Provider/Authorization Server một claim đáng tin cậy, ví dụ **`principal_kind: "service"` hoặc `"human"`**, và bảo đảm issuer **chỉ cấp giá trị tương ứng cho đúng loại principal**. Đây là claim **tùy biến của ví dụ**, không phải claim bắt buộc của OAuth2/OIDC.

**Không tin header hoặc body do client tùy ý gửi** như `X-Principal-Type: service` hay `{"isService": true}` để cấp quyền. Loại chủ thể phải đến từ xác thực đã được kiểm tra chữ ký, issuer, audience và chính sách cấp quyền.

## 4. Hai luồng xác thực phù hợp với hai loại tác nhân

### 4.1. Người dùng tương tác: trình duyệt và phiên

```text
Browser -> GET /login
Browser -> điền form hoặc chuyển tới IdP/OIDC
Server/IdP -> xác thực người dùng, có thể MFA
Browser -> nhận session cookie có thuộc tính bảo vệ
Browser -> GET /ui/home
Spring Security -> đọc session, kiểm tra ROLE_USER và quyền chi tiết
```

Nếu dùng form login/`HttpSession`, ứng dụng thường cần:

- Cookie phiên `Secure`, `HttpOnly`, `SameSite` hợp lý và HTTPS.
- CSRF protection cho các thao tác thay đổi trạng thái dùng credential trình duyệt tự gửi.
- Session fixation protection, timeout, logout, quản lý nhiều phiên khi cần.
- Login throttling, MFA hoặc step-up authentication cho thao tác rủi ro.
- Kiểm soát quyền theo người dùng và đối tượng nghiệp vụ, không chỉ “đã đăng nhập”.
- Không đặt username/password, session ID hay token vào URL hoặc log.

Nếu ứng dụng tích hợp OIDC, **Authorization Code + PKCE** là luồng phù hợp cho các loại client được hỗ trợ; IdP có thể xác thực con người rồi ứng dụng tạo local session hoặc dùng token theo kiến trúc. Trong một SPA hiện đại, token có thể tồn tại ở lớp frontend hoặc kiến trúc Backend-for-Frontend (BFF); phải đánh giá XSS, CSRF, cookie, CORS và nơi lưu token theo thiết kế.

### 4.2. Workload: OAuth 2.0 Client Credentials

```text
Worker (client_id + secret/certificate/workload identity)
      |
      | POST /oauth2/token, grant_type=client_credentials
      v
Authorization Server
      | Xác thực client, cấp access token với audience/scope/TTL
      v
Worker
      |
      | POST /api/m2m/jobs
      | Authorization: Bearer <access_token>
      v
Spring Security Resource Server
      | Kiểm tra chữ ký, thời gian, issuer, audience
      | Chuyển scope thành authority, kiểm tra loại principal/client
      v
API cho phép hoặc từ chối
```

Trong grant `client_credentials`, **client hoạt động vì chính nó**, không đại diện cho một người dùng vừa login. Không có thao tác nhập password con người hoặc browser redirect bắt buộc trong mỗi lần chạy. Token M2M phải có **scope và audience tối thiểu**, thời gian sống ngắn và được cấp từ một issuer đáng tin cậy.

Ví dụ HTTP minh họa (giá trị đều giả):

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_FAKE_CLIENT_AUTH

grant_type=client_credentials&scope=jobs.write
```

Response thành công thường trả `access_token` và `expires_in` theo giao thức; không được đưa token thật vào log, URL hay tài liệu. Khi dùng client secret, bảo vệ nó bằng secret manager và TLS. Các cơ chế mạnh hơn như `private_key_jwt`, mTLS hoặc workload federation có thể giảm phụ thuộc secret tĩnh.

**Không nên tạo “nhân viên kỹ thuật” trong user table rồi để job dùng mật khẩu đăng nhập form** chỉ để tận dụng cùng một controller. Mật khẩu con người, session browser, MFA và quy trình offboarding khác bản chất với danh tính của workload.

### 4.3. Hai ví dụ không được đánh đồng

- **Microservice A gọi Microservice B để tự đồng bộ dữ liệu:** dùng service principal và quyền của A, không tự gán người dùng cuối.
- **Người dùng Alice bấm “xuất báo cáo”, backend gọi service B:** có thể cần vừa ghi nhận Alice là chủ thể yêu cầu, vừa xác thực backend A là workload. Nếu chính sách B cần biết Alice, dùng mô hình **ủy quyền có kiểm soát** (delegation, on-behalf-of hoặc token exchange theo hỗ trợ của IdP), không giả mạo một `user_id` trong JSON và gọi đó là danh tính đã xác thực.

Một “service account” không tự có quyền hành động **như mọi người dùng**. Delegation phải có giới hạn phạm vi, bằng chứng quyền và audit riêng.

## 5. Thiết kế API rõ ranh giới người và máy

Một cách tổ chức dễ kiểm toán:

| Nhóm URL | Ai được truy cập | Authn/Authz đề xuất |
| --- | --- | --- |
| `/ui/**` | Nhân viên trong trình duyệt | Form/session hoặc OIDC login; role và quyền người dùng. |
| `/api/user/**` | Người dùng qua ứng dụng frontend | Token/session theo kiến trúc, kiểm tra quyền theo subject người dùng. |
| `/api/m2m/**` | Worker, integration, microservice | OAuth2 bearer Resource Server; kiểm tra client/workload identity, audience và scope. |
| `/admin/**` | Người dùng đặc quyền có MFA/step-up | Rule chặt hơn; không coi service credential là admin. |
| `/actuator/**` | Hệ thống vận hành được ủy quyền | Đường truy cập/phương thức xác thực riêng, không công khai tùy tiện. |

Điều quan trọng không phải **tên URL** `/api/m2m` tự làm endpoint an toàn. Cần xác định `SecurityFilterChain`, loại authentication được chấp nhận và policy tại backend. Có thể dùng **một chain** với `AuthorizationManager` riêng theo endpoint, hoặc **nhiều chain** nếu cơ chế browser/session và stateless bearer khác biệt đáng kể.

**Bẫy phổ biến với nhiều chain:** `FilterChainProxy` chọn **SecurityFilterChain đầu tiên** khớp request. Chain cho `/api/m2m/**` cần được ưu tiên trước chain fallback, và chain fallback cần bao phủ những đường dẫn còn lại. Nếu một endpoint không khớp chain nào, nó có thể bị bỏ qua các filter bảo mật.

Đừng chỉ viết `hasAuthority("SCOPE_jobs.write")` ở cả luồng người và service nếu chính sách còn đòi **đúng loại chủ thể**. Kết hợp điều kiện loại principal, client identity và quyền phù hợp để tránh confused deputy.

## 6. Ví dụ Spring Boot 3.x: phân tách browser và service API bằng hai filter chain

Ví dụ này minh họa một ứng dụng vừa có giao diện cho người dùng, vừa nhận lời gọi tự động từ service. Trọng tâm là **ủy quyền đúng loại danh tính**, không xây một Identity Provider mới.

**Quy ước kiểm tra service token của ví dụ:**

- Nhà phát hành token đáng tin cậy cấp JWT có `principal_kind = "service"` cho client credentials, không cấp claim đó cho người dùng.
- Service client được phép trong ví dụ có `client_id = "batch-worker"`.
- Access token dành cho API phải có `aud` chứa `inventory-api`.
- Quyền tối thiểu là `scope = "jobs.write"`, được Spring Security chuyển thành `SCOPE_jobs.write`.
- JWT phải được kiểm tra chữ ký theo JWK của issuer, thời hạn, issuer và audience.
- Các tên claim và giá trị này **là hợp đồng do ứng dụng demo tự quy ước**, không phải lời hứa rằng mọi nhà cung cấp OAuth đều tạo token như thế. Trong production, hãy cấu hình IdP để thực hiện hợp đồng và xác thực metadata của issuer.

Browser UI vẫn dùng form login với `HttpSession`. Machine API không chấp nhận cookie người dùng làm cơ chế đăng nhập, không tạo session và không trả redirect login.

### 6.1. Dependency và thư mục dự án

Dự án Gradle Spring Boot 3.x, Java 17+ cần các starter:

```groovy
// Trích đoạn trong build.gradle (Groovy DSL) của dự án đã có plugin Boot.
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Các file Java cùng package `demo.identityboundary`. Đây là mã có thể biên dịch trong dự án Spring Boot tương thích; **để gọi thật bằng bearer token cần IdP cấp token đã cấu hình issuer/JWK phù hợp**. Bộ test dùng JWT giả lập tại test boundary, không cần gọi IdP ngoài.

### 6.2. Main class

`src/main/java/demo/identityboundary/IdentityBoundaryApplication.java`:

```java
package demo.identityboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityBoundaryApplication.class, args);
    }
}
```

### 6.3. Cấu hình issuer/JWK

`src/main/resources/application.yml`:

```yaml
app:
  security:
    issuer-uri: "${M2M_ISSUER_URI:https://idp.example.invalid/realms/demo}"
    jwk-set-uri: "${M2M_JWK_SET_URI:https://idp.example.invalid/realms/demo/protocol/openid-connect/certs}"
```

**Thay hai URL giả bằng issuer và JWK Set URI chính thức do IdP cung cấp** trước khi chạy thử end-to-end. Domain `.invalid` được dùng làm giá trị minh họa để không vô tình trỏ tới hệ thống thật. Khi chạy Gradle test trong tài liệu, các bài test sử dụng `spring-security-test` và không thực hiện network call tới các URL này.

### 6.4. Cấu hình Spring Security

`src/main/java/demo/identityboundary/SecurityConfig.java`:

```java
package demo.identityboundary;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain machineApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/m2m/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            // Chỉ chain M2M dùng bearer token trong header và không
            // dùng cookie làm phương tiện xác thực tự động.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().access((authentication, request) -> {
                    Authentication current = authentication.get();

                    if (!(current instanceof JwtAuthenticationToken jwtAuth)) {
                        return new AuthorizationDecision(false);
                    }

                    Jwt jwt = jwtAuth.getToken();
                    boolean serviceIdentity =
                        "service".equals(jwt.getClaimAsString("principal_kind"))
                        && "batch-worker".equals(jwt.getClaimAsString("client_id"));

                    boolean correctAudience =
                        jwt.getAudience().contains("inventory-api");

                    boolean correctPermission = jwtAuth.getAuthorities()
                        .stream()
                        .anyMatch(authority ->
                            "SCOPE_jobs.write".equals(authority.getAuthority())
                        );

                    return new AuthorizationDecision(
                        serviceIdentity && correctAudience && correctPermission
                    );
                })
            )
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/logout", "/error").permitAll()
                .requestMatchers("/ui/**").hasRole("USER")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/ui/home", true)
            )
            .logout(Customizer.withDefaults());

        // Không tắt CSRF ở chain browser.
        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer-uri}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri
    ) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("inventory-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token audience is not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audience
            )
        );
        return decoder;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

**Điểm giải thích quan trọng:**

1. `machineApi` có `@Order(1)` và `securityMatcher("/api/m2m/**")`, nên request trong nhánh M2M được chọn vào chain này, không chạy tiếp chain browser. `browser` là fallback để những URL khác vẫn có chính sách bảo vệ.
2. `SessionCreationPolicy.STATELESS` ngăn việc dùng session để duy trì `SecurityContext` cho chain M2M. Không có form login hoặc HTTP Basic trong chain M2M.
3. CSRF được tắt **chỉ trong chain M2M**, vì giả định API ở đây chỉ xác thực bằng bearer token do client chủ động đặt trong `Authorization`, **không** bằng cookie tự gửi. Nếu một endpoint M2M còn chấp nhận cookie browser hoặc cơ chế credential tự động khác, phải đánh giá lại CSRF.
4. Chain browser vẫn có CSRF mặc định, form login và `HttpSession`, phù hợp người dùng tương tác.
5. `JwtDecoder` dùng JWK từ issuer để kiểm tra chữ ký và validator để kiểm tra issuer/thời gian/audience. Chỉ nhận token từ IdP đáng tin cậy; không tự giải mã Base64 JWT rồi coi claim là đã xác thực.
6. `JwtAuthenticationToken` và claims cho service được kiểm tra tại phân quyền. Token người dùng có `SCOPE_jobs.write` nhưng `principal_kind="human"` sẽ bị từ chối.
7. `client_id="batch-worker"` là allowlist minh họa một workload. Ứng dụng thật có thể dùng quy tắc cấu hình theo client, scope, đối tượng, tenant và thao tác; không hardcode mọi client trong một hàm lớn.
8. `SCOPE_jobs.write` xuất hiện khi `JwtGrantedAuthoritiesConverter` mặc định đọc scope/scp phù hợp. Nếu IdP dùng claim khác, cần cấu hình converter có kiểm soát, không tự nâng quyền.
9. Claim `principal_kind` là **custom claim** chỉ đáng tin khi nhà phát hành bảo đảm không cho token người dùng giả lập giá trị service. Nếu IdP không hỗ trợ, chọn cách định danh service khác được issuer chứng thực và kiểm thử ràng buộc.
10. `Logout` của browser chỉ kết thúc session của người dùng theo cấu hình. Nó **không tự revoke access token M2M** đang được một worker khác giữ.

**Cảnh báo quan trọng về phạm vi:** Token bearer thật của production cần còn được kiểm tra chính sách thuật toán ký, khóa, issuer và các thuộc tính khác theo môi trường. Bài này minh họa nguyên tắc kiểm tra ở Resource Server, không xây dựng một Authorization Server hoặc khẳng định các URL JWK giả đã phát hành token có giá trị.

### 6.5. Controller minh họa tách dữ liệu

`src/main/java/demo/identityboundary/DemoController.java`:

```java
package demo.identityboundary;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/ui/home")
    public Map<String, String> home(Authentication authentication) {
        return Map.of("interactiveUser", authentication.getName());
    }

    @PostMapping("/api/m2m/jobs")
    public Map<String, Object> submitJob(Authentication authentication) {
        JwtAuthenticationToken service = (JwtAuthenticationToken) authentication;
        return Map.of(
            "accepted", true,
            "clientId", service.getToken().getClaimAsString("client_id")
        );
    }
}
```

Controller không đọc `client_id` hay `principal_kind` từ body, query string hoặc một header tùy ý do caller tự khai. Danh tính dịch vụ đến từ `Authentication` mà chain bearer đã xác thực, và request đã vượt qua `AuthorizationManager` trước khi đến controller.

Trong hệ thống thật, **không** chỉ dựa vào kiểm tra URL/role mà bỏ kiểm tra quyền trên từng đối tượng; nếu service được phép sửa dữ liệu của một tenant, backend phải ràng buộc chính sách tenant/ownership và phạm vi tài nguyên tại nơi thao tác.

## 7. Kiểm thử MockMvc: có quyền nhưng sai loại danh tính vẫn bị từ chối

Mục tiêu kiểm thử là chứng minh **đường phân cách người–máy**, không chỉ test một service token thành công. `spring-security-test` cung cấp `jwt()` và `user()` để tạo `Authentication` kiểm thử. Những helper này **không kiểm tra chữ ký JWT**; chúng thích hợp kiểm thử phân quyền và filter chain, nhưng cần thêm integration test với token thật để kiểm tra bộ giải mã, issuer, audience và key rotation.

Tệp `src/test/java/demo/identityboundary/IdentityBoundaryTests.java`:

```java
package demo.identityboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

import java.util.List;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityBoundaryTests {

    @Autowired
    MockMvc mvc;

    @Test
    void browserWithoutLoginMustRedirectToLogin() throws Exception {
        mvc.perform(get("/ui/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void browserHumanUserCanAccessUi() throws Exception {
        mvc.perform(get("/ui/home").with(user("reader").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.interactiveUser").value("reader"));
    }

    @Test
    void realFormLoginFlowIsAvailableForHumanUser() throws Exception {
        mvc.perform(formLogin().user("reader").password("demo-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/ui/home"));
    }

    @Test
    void machineEndpointWithoutBearerIs401() throws Exception {
        mvc.perform(post("/api/m2m/jobs"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validServiceIdentityAndScopeCanSubmitJob() throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("service", "batch-worker",
                            "jobs.write", "inventory-api")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.accepted").value(true))
            .andExpect(jsonPath("$.clientId").value("batch-worker"));
    }

    @Test
    void humanJwtIsNotAcceptedAsServiceEvenWithSameScope()
            throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("human", "batch-worker",
                            "jobs.write", "inventory-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void serviceWithoutRequiredScopeIsDenied() throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("service", "batch-worker",
                            "jobs.read", "inventory-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void differentServiceClientIsDenied() throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("service", "unknown-worker",
                            "jobs.write", "inventory-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongAudienceIsDenied() throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(token("service", "batch-worker",
                            "jobs.write", "other-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void BrowserSessionIdentityCannotBecomeServiceIdentity()
            throws Exception {
        mvc.perform(post("/api/m2m/jobs")
                .with(user("reader").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void machineTokenDoesNotGrantHumanUiRole() throws Exception {
        mvc.perform(get("/ui/home")
                .with(token("service", "batch-worker",
                            "jobs.write", "inventory-api")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownUrlIsDeniedByFallbackChain() throws Exception {
        mvc.perform(get("/not-an-api"))
            .andExpect(status().isForbidden());
    }

    private RequestPostProcessor token(
            String kind,
            String clientId,
            String scope,
            String audience
    ) {
        return jwt().jwt(builder -> builder
            .claim("principal_kind", kind)
            .claim("client_id", clientId)
            .claim("scope", scope)
            .claim("aud", List.of(audience))
        );
    }
}
```

Chạy:

```bash
./gradlew test --tests demo.identityboundary.IdentityBoundaryTests
```

**Kết quả mong đợi:** 12 bài test đều PASS trong dự án Spring Boot tương thích, khi các lớp và dependency được tạo đúng. Tài liệu này **không tuyên bố đã thực thi test**. Một số chính sách status/redirect có thể khác nếu tích hợp cấu hình bổ sung; khi đó cần giữ mục tiêu kiểm thử, đồng thời cập nhật assertion theo hợp đồng thực tế.

| Nhóm test | Điều cần chứng minh |
| --- | --- |
| Browser không có login | Luồng người dùng tương tác dẫn tới trang đăng nhập; không âm thầm cấp quyền. |
| Browser có `ROLE_USER` | Người dùng đúng vai trò truy cập UI, không cần bearer machine token. |
| Form login thật | Cơ chế login có CSRF/test helper hoạt động theo chain browser. |
| M2M không bearer | Không dùng session browser để “mượn” quyền service; bị 401. |
| M2M token đúng claim/client/aud/scope | Request được chấp nhận và gắn đúng service client. |
| JWT loại human nhưng có scope service | Bị 403, chứng minh quyền và loại danh tính đều quan trọng. |
| Service thiếu scope | Bị 403, không cấp quyền chỉ vì là service. |
| Service khác client ID | Bị 403, tránh mọi workload cùng scope dùng chung quyền. |
| Service sai audience | Bị 403, token dành cho API khác không được chấp nhận. |
| Mock user session gọi M2M | Bị từ chối vì loại `Authentication` không phải JWT service. |
| Mock service JWT gọi UI | Bị từ chối vì không có role browser. |
| URL không được khai báo | Chain fallback từ chối thay vì vô tình công khai. |

**Giới hạn cốt lõi của `jwt()` trong MockMvc:** helper có thể tạo `Authentication` với bất kỳ claim nào mà test đặt vào. Vì vậy, các ca trên kiểm tra **logic phân quyền và phân tách chain**, không chứng minh kẻ tấn công có thể hoặc không thể giả chữ ký JWT. Trong staging cần thêm test nhận token thật được ký bởi issuer, token sai chữ ký, token hết hạn, sai issuer, sai audience, key rotation và trường hợp IdP phát hành claim sai; token không hợp lệ phải không qua được `JwtDecoder`.

**Cần phân biệt kiểm tra quyền với kiểm tra luồng cấp token.** Resource Server chỉ nhận/kiểm tra token. Việc service có thật sự nhận được token đúng `client_credentials`, với claim `principal_kind` không giả được và scope tối thiểu, phải được kiểm tra ở Authorization Server và test tích hợp IdP.

## 8. Khi một service muốn tự lấy token: outbound OAuth2 client

Ứng dụng ở phần 6 là **Resource Server nhận token**. Một worker gọi API lại đóng vai **OAuth2 Client xin token**, cần cấu hình khác. Không lẫn hai trách nhiệm này:

```text
[Worker: OAuth2 Client]   -- xin token --> [Authorization Server]
[Worker: OAuth2 Client]   -- Bearer ----> [API: Resource Server]
```

Ở ứng dụng worker riêng, dùng dependency `spring-boot-starter-oauth2-client` và cấu hình client registration:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
```

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-worker:
            provider: company-idp
            client-id: "${M2M_CLIENT_ID}"
            client-secret: "${M2M_CLIENT_SECRET}"
            authorization-grant-type: client_credentials
            scope: jobs.write
        provider:
          company-idp:
            token-uri: "${M2M_TOKEN_URI}"
```

Không hardcode `client-secret` thật trong repository. Với worker chạy ngoài HTTP request, có thể dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` thay vì manager phụ thuộc `HttpServletRequest`/`HttpServletResponse`:

```java
// Trích đoạn cấu hình trong ứng dụng worker riêng (không thay SecurityConfig).
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService clients
) {
    AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, clients
        );
    manager.setAuthorizedClientProvider(
        OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build()
    );
    return manager;
}
```

Các import tương ứng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
```

Một worker có thể xin token từ manager:

```java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("inventory-worker")
    .principal("inventory-worker")
    .build();

OAuth2AuthorizedClient authorized = manager.authorize(request);
if (authorized == null) {
    throw new IllegalStateException("Unable to authorize worker client");
}
String token = authorized.getAccessToken().getTokenValue();
// Gửi token vào Authorization: Bearer ... qua HTTPS tới đúng API.
// Không ghi token này vào log/URL.
```

Đây là **trích đoạn sử dụng trong ứng dụng worker có manager và client registration đã cấu hình**, không phải một chương trình `javac` độc lập. Manager quản lý access token và tái cấp theo provider được cấu hình; token lấy được phải gửi qua header của HTTP client, kiểm soát TTL và không lưu vào log.

**Lưu ý thực tế:** `client_credentials` thường không cung cấp refresh token theo cách giống người dùng; worker xin access token mới khi cần. Cơ chế token caching/retry/rate limit cần tương ứng với Authorization Server. Khi dùng workload federation/mTLS thay secret, cấu hình cơ chế xác thực client phải thay đổi phù hợp, nhưng nguyên tắc phân biệt người–máy không đổi.

## 9. Chính sách cấp quyền: loại danh tính, scope và tài nguyên

Một quyết định ủy quyền tốt không chỉ hỏi “token hợp lệ chưa?”. Nó có thể gồm:

1. **Issuer**: token do ai phát hành? Có nằm trong danh sách IdP tin cậy không?
2. **Audience**: token dành cho API nào? Token của API A không mặc định được dùng ở API B.
3. **Loại principal**: con người hay workload, được issuer chứng nhận theo hợp đồng?
4. **Client ID/workload ID**: chính xác service nào? Có được phép gọi chức năng này không?
5. **Authority/scope**: quyền dành cho endpoint, method, hành động cụ thể.
6. **Đối tượng tài nguyên**: service có được thao tác với tenant/dự án/order này không?
7. **Trạng thái**: tài khoản đã khóa, credential đã thu hồi, deployment đã bị hủy, token hết hạn?
8. **Ngữ cảnh rủi ro**: môi trường, kết nối mTLS, IP/network trust trong chính sách, yêu cầu xác thực tăng cường của người dùng.

Ví dụ scope `jobs.write` chỉ nên cấp quyền tạo job trong ranh giới đã định, không có nghĩa worker được đọc mọi hồ sơ người dùng hoặc quản trị tài khoản. Nếu phải chạy thay mặt user Alice, thêm ngữ cảnh ủy quyền một cách có chứng thực thay vì thay `sub` bằng tùy ý trong body.

**Least privilege** áp dụng cả hai loại: nhân viên chỉ có role cần thiết; service chỉ có API/scope cần thiết, TTL ngắn, credential riêng theo ứng dụng/môi trường. Tách danh tính service `inventory-worker-dev` và `inventory-worker-prod`; đừng dùng cùng secret cho mọi môi trường.

## 10. Quản lý vòng đời và bí mật của service account

Tài khoản dịch vụ cũng cần chủ sở hữu, ngày cấp, scope, chính sách thu hồi và kiểm toán. Một bảng kiểm toán mẫu:

| Thuộc tính | Điều cần định nghĩa |
| --- | --- |
| Owner | Đội sở hữu workload và người duyệt quyền. |
| Mục đích | Job/tích hợp nào và endpoint nào thực sự cần. |
| Issuer và audience | Authorization Server nào, token dùng cho API nào. |
| Scopes | Danh sách tối thiểu, không chia sẻ scope admin mặc định. |
| Cách xác thực | Workload identity, mTLS, private_key_jwt, hoặc secret đã được bảo vệ. |
| Kho lưu bí mật | Secret manager, vault hoặc nền tảng identity; không commit vào repo. |
| Vòng đời | Cấp phát, rotate, revoke, huỷ sau khi job không còn dùng. |
| Audit | Client ID, workload/deployment, trace ID, operation, result; không log raw token. |
| Phản ứng sự cố | Khóa client, revoke token nếu hỗ trợ, rotate secret, rà log hoạt động. |

Không dùng `Authorization: Basic` với mật khẩu của một user người thật cho cron job. Nếu tạm thời kế thừa hệ thống cũ không có OAuth2, cần tài khoản hệ thống riêng, quyền giới hạn, lưu bí mật an toàn, transport TLS và lộ trình chuyển sang danh tính workload chuẩn.

Nếu service secret bị lộ, “đăng xuất browser” không giúp thu hồi. Phải khóa hoặc rotate credential tại nhà cấp, xử lý access token còn hiệu lực theo khả năng thu hồi đã cam kết, rồi deploy secret/chứng chỉ mới.

### 10.1. Service account không mặc định “không có người chịu trách nhiệm”

Mỗi service account phải có **owner** và chuỗi trách nhiệm. “Không tương tác” nghĩa là tiến trình tự chạy, **không** có nghĩa không cần approval, audit hay review định kỳ. Khi người sở hữu rời dự án, ownership cần được chuyển giao. Nếu không còn workload dùng credential, phải vô hiệu hóa thay vì để tài khoản tồn tại vĩnh viễn.

### 10.2. Secret của ứng dụng và token người dùng không được dùng lẫn

Không gửi refresh token của người dùng cho job chạy lâu dài nếu thiết kế không có delegation/revocation phù hợp. Không dùng API key của service như session ID của người dùng. Các loại credential khác nhau có thời hạn và khả năng thu hồi khác nhau; một giá trị dùng chung giữa nhiều vai trò làm mở rộng phạm vi khi bị xâm phạm.

## 11. Logging và quan sát: ghi đúng actor, không ghi secret

Một hệ thống có cả user và service cần phân biệt **ai yêu cầu**, **dịch vụ nào xử lý** và **có đại diện người dùng khác hay không**.

Bản ghi audit có thể lưu:

```json
{
  "actorType": "service",
  "clientId": "batch-worker",
  "operation": "jobs.create",
  "resource": "inventory",
  "decision": "ALLOW",
  "correlationId": "sample-correlation-id",
  "environment": "test"
}
```

Đây là dữ liệu minh họa; trong production cần hạn chế PII và thời hạn lưu phù hợp. Với thao tác người dùng, actorType có thể là `human`, kèm định danh người dùng được phép ghi log. Với delegation, có thể cần **cả** user subject và calling service cùng mối quan hệ ủy quyền đã xác minh.

**Không log** `Authorization`, JWT gốc, `Cookie`, `Set-Cookie`, client secret, private key hoặc raw body chứa credential. JWT claim có thể chứa PII; chỉ lấy trường tối thiểu đã được thẩm định. Một mã tương quan dùng để tra log không được mang giá trị token/session ID.

Khi lỗi 401/403, response nên dùng status và mã lỗi công khai, không trả thông tin nội bộ như tên role bí mật, issuer key path hoặc token chưa xác minh. Với Bearer Resource Server, giữ `WWW-Authenticate` đúng giao thức; đừng tự thay một response 401 bằng 200 chỉ để frontend không hiện cảnh báo.

## 12. Những sai lầm phổ biến

1. **Dùng account người thật làm service account.** Cấp password cho cron job hoặc webhook khiến credential tồn tại ngoài quy trình người dùng, khó MFA và audit.
2. **Dùng chung một client ID/secret cho tất cả service.** Khi lộ secret hoặc phải thu hồi, không thể cô lập sự cố và khó biết job nào đã gọi.
3. **Cho service role ADMIN vì “job phải chạy”.** Thay bằng scope/resource permission tối thiểu và tách endpoint đặc quyền.
4. **Nhầm `sub` với loại principal.** Subject của JWT có thể biểu diễn người hoặc client tùy issuer. Cần hợp đồng claim/metadata được xác thực.
5. **Tin `principal_kind` do client tự gửi.** Chỉ tin claim đã được nhà phát hành có thẩm quyền ký và bảo vệ khỏi tự cấp sai.
6. **Chỉ kiểm tra `SCOPE_jobs.write`, bỏ actor/client/audience.** Token dành cho API hoặc chủ thể khác có thể bị dùng sai ngữ cảnh.
7. **Dùng token user cho service mà không có delegation.** Service có thể thừa hưởng quyền không đúng hoặc không có dấu vết nguồn ủy quyền.
8. **Bỏ CSRF trên browser chỉ vì API M2M dùng bearer.** Từng chain có mô hình credentials riêng; không tắt CSRF toàn ứng dụng.
9. **Bật form login trong API M2M rồi trả 302 HTML login.** Worker cần hợp đồng HTTP/token, không phải quy trình tương tác người dùng.
10. **Nhầm Spring OAuth2 Client với Resource Server.** Client xin token và gửi đi; Resource Server nhận và xác minh token.
11. **Cho rằng MockMvc `jwt()` chứng minh chữ ký/token thật hợp lệ.** Helper tạo authentication giả ở biên test; phải test decoder và IdP riêng.
12. **Không có fallback `SecurityFilterChain`.** URL có thể không bị Spring Security bảo vệ khi không khớp chain nào.
13. **Không rotate, không tắt service account cũ.** Credential không còn dùng vẫn có nguy cơ bị khai thác.
14. **Log token để “dễ debug”.** Token và secret phải được che tại nguồn thu thập, không chỉ che trong màn hình dashboard.
15. **Đồng nhất logout và revoke.** Logout `HttpSession` của người không tự vô hiệu hóa client-credentials access token của worker.

## 13. Checklist thiết kế và kiểm thử chấp nhận

| Kiểm tra | Người dùng tương tác | Tài khoản dịch vụ |
| --- | --- | --- |
| Loại danh tính | User identity được xác thực qua login/IdP. | Workload/client identity được issuer chứng nhận. |
| Đúng kênh xác thực | Form/session, OIDC code flow, cookie và CSRF đúng. | Token header hoặc chứng chỉ/workload identity, không dùng form login. |
| Phạm vi endpoint | User không được “mượn” service API chỉ nhờ role chung. | Service không vào UI/admin human vì có token hợp lệ. |
| Quyền tối thiểu | Role/resource ownership, MFA/step-up khi cần. | Scope, client allowlist, audience và tenant theo workload. |
| Vòng đời | Logout, session timeout, lock/reset, offboarding. | Expire/rotate/revoke token/secret, tắt workload không còn dùng. |
| Dữ liệu nhật ký | Actor người dùng, resource, kết quả, không ghi session/cookie. | Client/workload ID, operation, trace, không ghi raw token/secret. |
| Tình huống phủ định | Anonymous, thiếu role, CSRF sai, user bị khóa. | Bearer thiếu/sai, scope thiếu, client khác, audience sai, token hết hạn. |
| Tích hợp thực | Trình duyệt thật, cookie, IdP, OAuth redirect. | Client credentials grant, IdP/JWK, key rotation, mTLS/secret store. |

**Bộ câu hỏi trước khi chấp nhận thiết kế:**

- Nếu nhân viên nghỉ việc, có thể khóa tài khoản họ mà **không** làm dừng các worker hợp lệ không?
- Nếu một worker bị xâm nhập, có thể thu hồi credential của worker đó mà **không** khóa toàn bộ người dùng không?
- Một service token còn hạn có tự động vào được UI quản trị người dùng không? **Câu trả lời kỳ vọng: không.**
- Một human access token có scope tình cờ trùng với service scope có thực hiện được việc của worker không? **Không, nếu chính sách yêu cầu phân tách chủ thể và được triển khai đúng.**
- Nếu thiếu IdP trong test, test MockMvc có đang kiểm tra **authorization rules** hay đang khẳng định nhầm rằng JWT đã được xác minh?
- Các sự kiện audit có ghi được user actor hoặc client actor thực tế, phân biệt với giá trị `userId`/`clientId` do caller tự khai không?

## 14. Bài tập áp dụng

Hệ thống có ba tác vụ:

1. **Alice mở trang thống kê đơn hàng.** Gắn một danh tính user, kiểm tra role và quyền truy cập dữ liệu/tenant của Alice. Có thể yêu cầu MFA cho thống kê nhạy cảm.
2. **Job mỗi 15 phút nhập tồn kho.** Cấp service principal riêng, chỉ scope `inventory.write`, audience `inventory-api` và token ngắn hạn. Không sử dụng tài khoản Alice hay mật khẩu admin.
3. **Alice bấm duyệt một giao dịch, backend đẩy lệnh sang dịch vụ thứ ba.** Backend xác thực như workload khi gọi dịch vụ, nhưng nghiệp vụ phải giữ dấu vết Alice là người quyết định. Nếu service đích cần kiểm tra quyền Alice, dùng một cơ chế delegation/on-behalf-of được issuer hỗ trợ, thay vì đặt `userId=alice` vào body rồi tin ngay.

Viết test tối thiểu cho từng trường hợp: đúng principal và quyền thành công; sai loại principal bị từ chối; thiếu quyền bị từ chối; token sai audience/issuer bị từ chối; dữ liệu audit không ghi secret; khóa một service không ảnh hưởng người dùng và service khác.

**Kết luận:** người dùng tương tác và service account là **hai loại chủ thể khác nhau**, có cách xác thực, thẩm quyền, vòng đời và dấu vết kiểm toán khác nhau. Spring Security cho phép kết hợp form/session và Resource Server trên những `SecurityFilterChain` riêng, nhưng ranh giới chỉ thực sự an toàn khi backend kiểm tra **đúng principal, đúng loại, đúng audience, đúng quyền và đúng tài nguyên**.

## Tài liệu tham khảo

- Spring Security — [Java Configuration và multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).
- Spring Security — [OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- Spring Security — [OAuth 2.0 Client Credentials](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html).
- Spring Security — [Spring Security Test: OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- Spring Security — [Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html).
- OAuth 2.0 — [RFC 6749, Client Credentials Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.4).
- OAuth 2.0 Security Best Current Practice — [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700).
- OAuth 2.0 JWT Access Token Profile — [RFC 9068](https://www.rfc-editor.org/rfc/rfc9068).
- OWASP — [Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).