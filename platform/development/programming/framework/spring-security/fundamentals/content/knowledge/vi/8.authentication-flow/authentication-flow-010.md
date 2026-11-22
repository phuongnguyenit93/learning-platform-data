# Phân biệt xác thực người dùng, xác thực dịch vụ và xác thực nhiều yếu tố

> **Phạm vi:** Spring Security Servlet/Spring MVC; Java 17+, Spring Boot 3.x và Spring Security 6.x cho ví dụ chạy. Bài này so sánh ba khái niệm **user authentication**, **service/machine-to-machine authentication (M2M)** và **multi-factor authentication (MFA)**; giải thích credential, principal, token, các yếu tố độc lập, step-up authentication và các cách tích hợp trong Spring Security. Phần về MFA API mới của **Spring Security 7** được ghi riêng để tránh dùng sai phiên bản.

## 1. Ba khái niệm, hai loại chủ thể và một mức độ bảo đảm

Giả sử ứng dụng có ba tình huống:

- Alice mở trang hồ sơ và đăng nhập bằng mật khẩu, passkey hoặc hệ thống đăng nhập doanh nghiệp.
- Một batch worker không có người dùng trực tiếp gọi API `/service/jobs` theo lịch.
- Alice muốn thay phương thức khôi phục tài khoản, hệ thống yêu cầu xác minh thêm bằng authenticator trước khi cho phép.

Trường hợp đầu là **xác thực người dùng**; thứ hai là **xác thực dịch vụ**; thứ ba là **xác thực nhiều yếu tố (MFA)**. MFA **không phải loại tài khoản thứ ba**. Nó là chiến lược xác minh danh tính bằng nhiều bằng chứng độc lập, thường được áp dụng cho **chính người dùng đang đăng nhập**.

| Tiêu chí | Xác thực người dùng | Xác thực dịch vụ | MFA/step-up |
| --- | --- | --- | --- |
| Chủ thể | Người dùng/human account | Application, worker, backend, workload | Thường là user hiện tại |
| Câu hỏi | “Ai đang đăng nhập?” | “Workload nào đang gọi?” | “Danh tính này đã được chứng minh đủ mạnh và gần đây chưa?” |
| Credential | Password, passkey, OIDC login | Client secret, private key, certificate, workload credential | Yếu tố bổ sung như TOTP, WebAuthn, hardware key |
| Luồng thường gặp | Form login, OIDC Authorization Code + PKCE | OAuth2 `client_credentials`, mTLS, workload identity | MFA lúc login hoặc challenge khi thao tác nhạy cảm |
| Quyền sau xác thực | ROLE_USER, ROLE_ADMIN, user permissions | Service scopes, workload roles | Thêm thông tin **mức bảo đảm/factor**, không thay quyền nghiệp vụ |
| Có người tương tác? | Thường có ở thời điểm login | Thường không | Thường có với challenge xác minh |
| Rủi ro đặc trưng | Password reuse, session theft, account takeover | Lộ secret, token replay, quyền service quá rộng | OTP phishing, factor bypass, recovery yếu, replay |

**Authentication** xác minh chủ thể. **Authorization** quyết định chủ thể có quyền với action và resource hay không. **MFA** nâng độ tin cậy của cách xác minh chủ thể. Một người đã đăng nhập, kể cả đã dùng MFA, vẫn phải được kiểm tra role, owner, tenant và các điều kiện domain.

## 2. Ba luồng ở mức kiến trúc

### 2.1. Người dùng đăng nhập

~~~text
Alice -> Browser/App
   |
   | Password, passkey, OIDC...
   v
Spring Security authentication filter hoặc Identity Provider
   |
   +--> Kiểm tra credential và account status
   |
   v
User Authentication / user session / user access token
   |
   +--> userId, roles, tenant, permission claims
   |
   v
AuthorizationFilter / method security
   |
   +--> GET /user/profile: cần authenticated
   +--> GET /user/admin: cần ROLE_ADMIN
   +--> thao tác nhạy cảm: có thể cần recent MFA
~~~

Nếu ứng dụng dùng form login, sau thành công Authentication có thể được lưu trong session. Nếu dùng OIDC, Identity Provider xác thực người dùng và ứng dụng nhận thông tin danh tính qua giao thức; đối với API, access token cần được Resource Server xác minh.

### 2.2. Service gọi Service

~~~text
Report Worker
   |
   | client credentials (client secret/private_key_jwt/mTLS)
   v
Authorization Server
   |
   +--> Xác minh client/workload
   +--> Cấp access_token với scope được phép
   |
   v
Report Worker -> Authorization: Bearer <access_token>
   |
   v
Resource Server (Spring Security)
   |
   +--> Validate JWT hoặc introspect opaque token
   +--> Kiểm tra issuer, audience, thời hạn, scopes
   |
   v
Authentication của SERVICE, ví dụ service:report-worker
   |
   +--> SCOPE_jobs.read
   |
   v
Authorization -> ALLOW / DENY
~~~

**Client credentials token đại diện client/workload, không mặc định đại diện người dùng cuối.** Nếu worker thực hiện tác vụ thay mặt Alice, đó là một bài toán ủy quyền/delegation khác, có thể cần on-behalf-of hoặc token exchange do Authorization Server hỗ trợ.

### 2.3. User cần MFA

~~~text
Alice đăng nhập bằng password
   |
   v
User Authentication ở mức ban đầu
   |
   +--> GET /user/profile: có thể ALLOW
   |
   +--> POST /user/change-recovery
             |
             v
         Policy yêu cầu step-up
             |
             +--> Challenge factor độc lập (TOTP/WebAuthn)
             +--> Verifier kiểm tra factor, nonce, replay, binding
             +--> Ghi nhận factor/assurance vừa được xác minh
             |
             v
         Kiểm tra role + resource + freshness
             |
             v
          ALLOW / DENY
~~~

**MFA không phải một boolean client tự đặt.** Header `X-MFA-Verified: true`, JSON `{"mfa":true}` hay role do client gửi không chứng minh yếu tố thứ hai. Chỉ một verifier đáng tin cậy sau khi hoàn tất challenge mới có quyền tạo bằng chứng factor hợp lệ.

## 3. Xác thực người dùng: những cơ chế thường gặp

### 3.1. Form login và HTTP Basic

Với username/password, Spring Security Servlet thường phối hợp:

~~~text
Form/Basic Authentication Filter
   |
   +--> UsernamePasswordAuthenticationToken (chưa xác thực)
   |
   v
AuthenticationManager / ProviderManager
   |
   v
DaoAuthenticationProvider
   |
   +--> UserDetailsService.loadUserByUsername(username)
   +--> PasswordEncoder.matches(rawPassword, storedHash)
   +--> Kiểm tra locked/disabled/expired
   |
   v
Authentication đã xác thực
   |
   v
SecurityContextHolder
   |
   v
AuthorizationFilter / @PreAuthorize
~~~

`UserDetailsService` **tìm account**, không nhận raw password để so khớp. `PasswordEncoder` đối chiếu credential với hash; provider kiểm tra trạng thái và tạo Authentication tin cậy. Phân quyền của ứng dụng tiếp tục diễn ra sau authentication.

**Form login** thích hợp ứng dụng web/session có browser, nhưng cần quản lý CSRF, cookie, session fixation, logout và timeout. **HTTP Basic** phù hợp để học hoặc một số API được kiểm soát, nhưng mỗi request có thể mang username/password dạng Base64. **Base64 không mã hóa bí mật**; dùng TLS và không đưa credential production vào source/log.

### 3.2. OIDC và đăng nhập doanh nghiệp

Trong OpenID Connect, ứng dụng thường là OIDC client và Identity Provider xác thực user. Authorization Code + PKCE là một luồng phổ biến, với redirect, state, nonce và token validation theo protocol.

**Phân biệt ID token và access token:**

| Token | Mục đích |
| --- | --- |
| **ID token** | Cho OIDC client biết thông tin xác thực của user tại IdP; kiểm tra issuer, audience, nonce và claims theo flow |
| **Access token** | Cấp quyền truy cập API/Resource Server, phải có audience/scope và kiểm tra hợp lệ theo API |
| **Session cookie** | Tham chiếu session của browser/app, không đồng nghĩa JWT |

**Không gửi ID token tới mọi API thay access token.** Khi dùng Resource Server, principal có thể là `Jwt`; với form login/DaoAuthenticationProvider, principal thường là `UserDetails`. Không cast mọi Authentication principal thành cùng một Java class.

### 3.3. Đăng nhập được chưa đủ quyền với dữ liệu

Alice có `ROLE_USER`, nhưng `/orders/42` có thể thuộc người khác. `authenticated()` chỉ kiểm tra tình trạng xác thực theo policy framework, không kiểm tra record ownership. Cần authorization theo accountId, tenantId, action và resource. Username/email có thể thay đổi, nên ứng dụng thường cần ID ổn định.

### 3.4. Vòng đời user session

- Session đã cấp có thể chứa Authentication/authorities cũ khi role vừa bị thu hồi.
- JWT access token đã phát có thể giữ claims trước khi role đổi cho đến hết hạn/thu hồi hoặc bước revalidation.
- Đổi password hoặc khóa account trong database không mặc định hủy mọi session/token cũ.
- Các chức năng nhạy cảm cần xác thực lại hoặc step-up có giới hạn về thời gian, không chỉ dựa vào session tồn tại.

## 4. Xác thực dịch vụ: không có người dùng cuối đang đăng nhập

### 4.1. Service principal và phạm vi quyền

Một worker nên có **service identity** riêng, chẳng hạn `service:report-worker`, kèm scope `jobs.read`. Trách nhiệm của server là xác minh danh tính service từ credential/token tin cậy rồi quyết định quyền.

| Thông tin | User principal | Service principal |
| --- | --- | --- |
| Định danh | userId, user subject, tenant | client_id, service account, workload ID |
| Quyền | Roles, permissions, ownership | Scopes, service roles, resource permissions |
| Audit | User nào làm action? | Workload nào gọi, môi trường nào, trên danh nghĩa ai nếu có delegation? |
| Credential | Password/passkey/OIDC | Client secret/private key/certificate/workload assertion |
| Thu hồi | Session/logout/password reset | Rotate credential, revoke client/tokens, workload policy |

**Service không trở thành admin chỉ vì nó chạy ở backend.** Scope `SCOPE_jobs.read` không bằng `ROLE_ADMIN`, và permission của một service không tự cấp phép truy cập dữ liệu cá nhân của mọi user.

### 4.2. OAuth2 client_credentials

Các bước chuẩn:

1. Service được đăng ký như OAuth2 client tại Authorization Server.
2. Service xác thực ở token endpoint bằng method được cho phép, ví dụ `client_secret_basic`, `private_key_jwt` hoặc mTLS.
3. Authorization Server cấp access token **cho chính client**, với scope được chấp thuận.
4. Service gửi Bearer token tới API.
5. Resource Server kiểm tra token; authorization đánh giá scope và resource.

**Đừng nhầm client authentication ở token endpoint với Resource Server authentication khi token được dùng.** Chúng là hai lần kiểm tra ở hai ranh giới. Dữ liệu `client_id` và token `sub` phải được hiểu theo hợp đồng với issuer; tên claim không tự biến nó thành human account.

### 4.3. Chọn credential cho workload

- **Client secret:** dễ triển khai nhưng cần secret manager, rotation và hạn chế phân phối. Không đặt trong frontend/mobile app.
- **private_key_jwt:** dùng khóa riêng để tạo assertion, cần key rotation, ràng buộc audience/issuer/time và chống replay theo protocol.
- **mTLS:** client chứng minh sở hữu khóa chứng chỉ ở tầng TLS; cần quản lý CA, trust store, expiry, revocation/binding.
- **Cloud workload identity/federation:** có thể cấp credential thời hạn ngắn dựa trên danh tính workload, giảm việc phân phát secret dài hạn.
- **API key:** là secret thường có đặc tính bearer, không tự là OAuth2 access token và không mặc định có scopes/expiry/issuer validation.

Thực tế có thể dùng mTLS/private_key_jwt để lấy OAuth2 access token, rồi dùng token gọi API. Một workload identity không tự bỏ qua authorization ở API đích.

### 4.4. JWT và opaque token

Spring Security OAuth2 Resource Server có hai hướng phổ biến:

- **JWT:** `JwtDecoder` kiểm tra chữ ký và claims; cần cấu hình issuer, audience, expiry, algorithm/kid/key rotation theo hệ thống. Không tin payload chỉ vì Base64URL đọc được.
- **Opaque token:** `OpaqueTokenIntrospector` xác minh token qua introspection hoặc cơ chế được cung cấp; thường nhận attributes/scopes từ Authorization Server.

Scope `jobs.read` thường được ánh xạ thành `SCOPE_jobs.read` trong GrantedAuthorities của Resource Server. Khi token hợp lệ nhưng thiếu scope, request có thể nhận **403**, khác với token không hợp lệ thường nhận **401**.

### 4.5. Service hành động thay mặt user là trường hợp riêng

Nếu Alice bấm nút tạo báo cáo và backend gọi service khác, dùng một client_credentials token chung có thể làm mất context **user nào yêu cầu**, consent và phạm vi dữ liệu. Cần policy delegation/on-behalf-of/token exchange hoặc thiết kế truyền và xác minh user context qua cơ chế tin cậy.

**Không tự thay claim `sub` trong JWT, không lấy userId request body làm một user authentication mới.** Hãy audit cả actor (service) và subject (user) khi hệ thống cho phép delegation.

## 5. MFA: nhiều yếu tố độc lập

MFA yêu cầu bằng chứng từ **ít nhất hai nhóm yếu tố khác nhau**. Số lượng prompt/field không phải tiêu chí đủ.

| Nhóm | Ví dụ | Điều cần hiểu |
| --- | --- | --- |
| **Something you know** | Password, PIN | Password + PIN vẫn thuộc nhóm knowledge |
| **Something you have** | Authenticator TOTP, security key, chứng chỉ/thiết bị sở hữu | OTP thủ công có thể bị phishing/relay |
| **Something you are** | Biometrics được dùng trong xác thực đáng tin cậy | File ảnh khuôn mặt do client upload không tự là factor |

Location/IP, thiết bị lạ hoặc risk score có thể ảnh hưởng quyết định xác thực, nhưng **không tự thay cho yếu tố độc lập**. Một phương thức cryptographic có thể có tính chất multi-factor khi dùng ràng buộc thiết bị và user verification phù hợp; hệ thống phải kiểm tra assurance thực tế.

### 5.1. Password + TOTP

Một luồng cơ bản:

1. User đăng nhập bằng password.
2. User đã đăng ký TOTP authenticator bằng cách an toàn, seed được bảo vệ.
3. Server yêu cầu mã TOTP tại login hoặc khi thực hiện action nhạy cảm.
4. Verifier kiểm tra thời gian, replay, rate limits, user/session binding và trạng thái enrollment.
5. Nếu hợp lệ, một thành phần đáng tin cậy mới ghi nhận MFA assurance cho session/token theo lifetime đã định.

**TOTP không phishing-resistant.** Attacker có thể lừa user nhập mã và chuyển tiếp trong thời gian mã còn hiệu lực. Không log TOTP/seed và không chấp nhận lại mã đã dùng khi chính sách yêu cầu chống replay.

### 5.2. Passkeys và WebAuthn

WebAuthn/FIDO2 dựa trên public-key cryptography, credential được ràng buộc với relying-party/domain và challenge, có thể chống phishing tốt hơn OTP nhập tay. Passkey có thể kết hợp possession với **user verification (UV)** qua PIN/biometric cục bộ.

**Không được coi mọi WebAuthn assertion tự động là MFA**. Assurance phụ thuộc loại authenticator, UV flag và policy. Khi endpoint đòi user verification, verifier phải kiểm tra UV thực sự đã được thực hiện theo giao thức và mức tin cậy phù hợp.

### 5.3. SMS/email code, push và recovery

SMS có rủi ro SIM swap, email account có thể bị chiếm, push có thể bị fatigue attacks. Trong những môi trường nhất định chúng vẫn được sử dụng, nhưng không nên đánh đồng với xác thực chống phishing.

**Recovery là một đường đi xác thực nhạy cảm.** Đổi authenticator, thêm thiết bị, lấy recovery code hay reset factor cần reauthentication, rate limits, audit, thông báo và quy trình giảm nguy cơ account takeover. Nếu recovery quá dễ, attacker chỉ cần đi đường recovery để vượt MFA.

### 5.4. MFA tại login và step-up authentication

- **MFA tại login:** user hoàn tất nhiều factor trước khi được cấp session/token đủ assurance.
- **Step-up theo hành động:** user đã đăng nhập cơ bản nhưng một action như đổi password, chuyển tiền, thêm admin hoặc đổi recovery cần factor bổ sung *gần thời điểm thao tác*.

Đừng coi một claim “đã từng MFA” là vĩnh viễn. Cần thiết kế **authentication time/freshness**, challenge binding và expiry; một phiên quá lâu có thể cần xác thực lại.

### 5.5. OIDC amr/acr

Identity Provider có thể cho biết authentication method/reference qua `amr` hoặc authentication context qua `acr`. **Giá trị cụ thể không phải mặc định phổ quát**; ví dụ `pwd`, `otp`, `mfa` phụ thuộc IdP và contract.

Chỉ tin factor/assurance claim **sau khi token hoặc session được xác minh từ nguồn tin cậy**, đúng issuer/audience/time và có policy freshness. Với Resource Server, thông tin assurance cần có ở **access token/introspection** hoặc được tra cứu qua kênh tin cậy; không tin một ID token do client tự đưa sai mục đích.

## 6. Spring Security tích hợp các luồng khác nhau thế nào?

| Feature/API | Vai trò |
| --- | --- |
| `formLogin`, `httpBasic` | Xác thực username/password với user store/provider phù hợp |
| `UserDetailsService` | Tìm account, password hash, authorities và trạng thái |
| `DaoAuthenticationProvider` | Phối hợp lookup và `PasswordEncoder` |
| `oauth2Login` | Ứng dụng làm OAuth2/OIDC client cho human login |
| `oauth2Client` | Ứng dụng chủ động lấy access token để gọi API, bao gồm client credentials |
| `oauth2ResourceServer` | API nhận Bearer token và xác minh JWT/opaque token |
| `SecurityFilterChain` | Chọn filter và rule phân quyền cho mỗi nhóm request |
| `@EnableMethodSecurity` | Bật kiểm tra quyền qua annotation trên service/method |
| MFA mechanism/IdP step-up | Xác minh yếu tố độc lập và cập nhật mức bảo đảm cho user |

Một ứng dụng có thể đồng thời là OAuth2 Client và Resource Server, nhưng **đừng trộn nhiệm vụ phát token, dùng token và xác minh token**. `oauth2ResourceServer` không tự cấp access token; Resource Server không tự gọi UserDetailsService để xác minh JWT.

### 6.1. MFA trong Spring Security 6

Với Boot 3/Security 6, hệ thống thường dùng một IdP có MFA và kiểm tra assurance đã được xác minh hoặc một flow riêng có challenge/verifier và security context được bảo vệ. Ví dụ snippet chỉ để diễn giải policy khi **Jwt đã được xác minh**:

~~~java
// Snippet — không phải ứng dụng hoàn chỉnh; phụ thuộc hợp đồng IdP.
boolean hasPasswordAndOtp(Jwt verifiedJwt) {
    List<String> methods = verifiedJwt.getClaimAsStringList("amr");
    return methods != null
        && methods.contains("pwd")
        && methods.contains("otp");
}
~~~

Đây là một cách đọc claim của **IdP cụ thể**, không phải phép xác thực TOTP. Phải kiểm tra signed token, issuer, audience, `auth_time`, thời hạn, resource context và chính sách thực tế. Không lấy claim `amr` từ JSON request chưa xác minh.

### 6.2. MFA built-in trong Spring Security 7

Spring Security 7 hỗ trợ `FactorGrantedAuthority` và các rule yêu cầu nhiều yếu tố, cùng một số cơ chế one-time-token/step-up. **Snippet sau chỉ dành cho Spring Security 7**; không trộn vào project Boot 3/Security 6 phía dưới:

~~~java
// Spring Security 7 only — snippet, cần imports/bean hỗ trợ.
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
@Configuration
class WebMfaConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Tư tưởng là **mỗi factor chỉ được ghi nhận sau khi cơ chế thực hiện xác minh đúng**, và authorization có thể đòi cả password factor lẫn one-time-token factor. Việc cấu hình delivery, enrollment, session và policy vẫn cần được hoàn thiện; không coi thêm một annotation là hệ thống MFA production hoàn chỉnh.

## 7. Demo có thể chạy: user Basic, service Bearer, MFA fail closed

Demo dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+**. Thực hành ba điểm:

1. User gọi `/user/profile` và `/user/admin` qua HTTP Basic với user store/BCrypt.
2. Service gọi `/service/jobs` qua Bearer opaque token; token được xác minh bởi **introspector in-memory chỉ cho localhost** để không phải dựng Authorization Server khi học.
3. `/user/high-risk` yêu cầu authority `MFA_VERIFIED`, **nhưng demo không cấp authority này**, vì chưa triển khai factor verifier. Endpoint luôn bị chặn khi user chỉ có password.

**Introspector in-memory chỉ mô phỏng bước xác nhận token trong bài học**, không phát token theo OAuth2 client_credentials, không xác minh issuer, expiry, revocation hay external IdP. Nó tuyệt đối **không phải cấu hình nên dùng trong production**. Production phải thay bằng JWT validation/introspection thực và policy xác minh tokens. Phần test ở dưới không chứng minh một hệ thống MFA thật đã được triển khai.

### 7.1. Dependencies và files

Tạo một dự án Spring Boot 3.x có Gradle Wrapper/plugin, Java 17+ và dependency management. Trong `build.gradle` hiện hữu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Block trên **không phải build.gradle độc lập**. Cấu trúc file:

~~~text
src/main/java/com/example/identitymodes/
  IdentityModesApplication.java
  SecurityConfig.java
  IdentityController.java

src/test/java/com/example/identitymodes/
  IdentityModesTest.java
~~~

### 7.2. IdentityModesApplication.java

~~~java
package com.example.identitymodes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityModesApplication {
    public static void main(String[] args) {
        SpringApplication.run(IdentityModesApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig.java

~~~java
package com.example.identitymodes;

import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    OpaqueTokenIntrospector demoIntrospector() {
        return token -> {
            if (!"demo-service-token".equals(token)) {
                throw new BadOpaqueTokenException("invalid_token");
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                "service:report-worker",
                Map.of(
                    "sub", "service:report-worker",
                    "client_id", "report-worker",
                    "scope", "jobs.read"
                ),
                List.of(new SimpleGrantedAuthority("SCOPE_jobs.read"))
            );
        };
    }

    @Bean
    @Order(1)
    SecurityFilterChain serviceChain(
            HttpSecurity http,
            OpaqueTokenIntrospector introspector) throws Exception {

        http
            .securityMatcher("/service/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/service/jobs")
                    .hasAuthority("SCOPE_jobs.read")
                .requestMatchers(HttpMethod.GET, "/service/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth
                .opaqueToken(opaque -> opaque.introspector(introspector))
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain userChain(HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/user/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/user/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/user/high-risk")
                    .hasAuthority("MFA_VERIFIED")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }
}
~~~

**Giải thích chính:**

- `UserDetailsService` và `PasswordEncoder` xác thực human accounts bằng hash BCrypt.
- `demoIntrospector` chấp nhận một token giả trên localhost và trả principal **service**, không phải Alice.
- `serviceChain` có `securityMatcher("/service/**")` và `@Order(1)`; nó chỉ bật Bearer token Resource Server authentication.
- `/service/jobs` cần `SCOPE_jobs.read`, còn `/service/admin` yêu cầu `ROLE_ADMIN` mà token demo không có.
- `userChain` là fallback chain `@Order(2)`; `/public` cho anonymous, `/user/profile` cần đăng nhập, `/user/admin` cần ROLE_ADMIN.
- `/user/high-risk` cần `MFA_VERIFIED`; **không có user nào được cấp marker này**, vì không có factor verifier. Đây là policy khóa an toàn để minh họa chỗ cần step-up thực tế.
- `anyRequest().denyAll()` chặn URL chưa khai báo. Không dùng `permitAll` rộng hoặc `web.ignoring` để chữa lỗi quyền.
- `STATELESS` trong demo không dùng HttpSession để đọc SecurityContext của request sau. Nó **không tự bật JWT/MFA**.
- Demo chỉ dùng GET; không tắt CSRF. Khi bổ sung POST/PUT/DELETE cần đánh giá CSRF theo client/credential transport.

### 7.4. IdentityController.java

~~~java
package com.example.identitymodes;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/user/profile")
    public String userProfile(Authentication authentication) {
        return "user:" + authentication.getName();
    }

    @GetMapping("/user/admin")
    public String userAdmin() {
        return "human-admin";
    }

    @GetMapping("/user/high-risk")
    public String highRisk() {
        return "high-risk";
    }

    @GetMapping("/service/jobs")
    public String serviceJobs(Authentication authentication) {
        return "jobs:" + authentication.getName();
    }

    @GetMapping("/service/admin")
    public String serviceAdmin() {
        return "service-admin";
    }

    @GetMapping("/unknown")
    public String unknown() {
        return "should-not-be-exposed";
    }
}
~~~

Controller chỉ đọc tên principal để minh họa. Không cast mọi principal thành UserDetails, không trả credentials/secret/token ra HTTP response.

### 7.5. Chạy và so sánh kết quả

Từ thư mục có Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Từ terminal khác trên localhost:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/user/profile
curl -i -u alice:alice123 http://localhost:8080/user/profile
curl -i -u alice:alice123 http://localhost:8080/user/admin
curl -i -u admin:admin123 http://localhost:8080/user/admin
curl -i -u alice:alice123 http://localhost:8080/user/high-risk
curl -i http://localhost:8080/service/jobs
curl -i -H "Authorization: Bearer demo-service-token" http://localhost:8080/service/jobs
curl -i -H "Authorization: Bearer wrong-token" http://localhost:8080/service/jobs
curl -i -H "Authorization: Bearer demo-service-token" http://localhost:8080/service/admin
curl -i -u alice:alice123 http://localhost:8080/service/jobs
curl -i -u alice:alice123 http://localhost:8080/unknown
~~~

Với đúng ứng dụng demo và không có proxy/custom handler:

| Request | Status kỳ vọng | Vì sao? |
| --- | --- | --- |
| Anonymous GET `/public` | **200** | permitAll |
| Anonymous GET `/user/profile` | **401** | User chain đòi Basic credentials |
| Alice Basic đúng `/user/profile` | **200** | Body `user:alice` |
| Alice Basic đúng `/user/admin` | **403** | ROLE_USER không đủ ROLE_ADMIN |
| Admin Basic đúng `/user/admin` | **200** | Body `human-admin` |
| Alice Basic đúng `/user/high-risk` | **403** | Chưa có bằng chứng MFA đã xác minh |
| Anonymous GET `/service/jobs` | **401** | Bearer authentication chưa có |
| Bearer demo đúng `/service/jobs` | **200** | Body `jobs:service:report-worker` |
| Bearer sai `/service/jobs` | **401** | Introspector từ chối |
| Bearer demo `/service/admin` | **403** | Scope jobs.read không bằng ROLE_ADMIN |
| Alice Basic `/service/jobs` | **401** | Chain service không xác thực bằng Basic |
| Alice Basic `/unknown` | **403** | Fallback denyAll |

401/403 và body lỗi tùy AuthenticationEntryPoint/AccessDeniedHandler nếu ứng dụng có custom handler. Các giá trị này là **kết quả HTTP dự kiến**, không phải stdout Java đã đo được.

**Không dùng password hoặc bearer token demo trên mạng thật.** Cả HTTP Basic và bearer token đều cần bảo vệ bởi TLS; tránh đưa secrets vào source code, log, shell history và trace. Literal token của demo không có cryptographic validation, expiry hoặc revocation.

## 8. MockMvc test: phân biệt Principal và policy MFA

Tạo file `src/test/java/com/example/identitymodes/IdentityModesTest.java`:

~~~java
package com.example.identitymodes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityModesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicIsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void userBasicChecksPassword() throws Exception {
        mvc.perform(get("/user/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/user/profile")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"));

        mvc.perform(get("/user/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void humanAccountNeedsAdminRoleForAdminEndpoint()
            throws Exception {
        mvc.perform(get("/user/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/user/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("human-admin"));
    }

    @Test
    void serviceBearerCreatesDifferentPrincipal() throws Exception {
        mvc.perform(get("/service/jobs"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/service/jobs")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-service-token"))
            .andExpect(status().isOk())
            .andExpect(content().string("jobs:service:report-worker"));

        mvc.perform(get("/service/jobs")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userBasicCannotBecomeService() throws Exception {
        mvc.perform(get("/service/jobs")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void serviceScopeDoesNotGrantAdminRole() throws Exception {
        mvc.perform(get("/service/admin")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo-service-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void passwordOnlyDoesNotSatisfyMfa() throws Exception {
        mvc.perform(get("/user/high-risk")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authorizationRuleCanRecognizeTrustedFactor()
            throws Exception {
        mvc.perform(get("/user/high-risk")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("ROLE_USER"),
                    new SimpleGrantedAuthority("MFA_VERIFIED")
                )))
            .andExpect(status().isOk())
            .andExpect(content().string("high-risk"));
    }

    @Test
    void unknownRouteIsDenied() throws Exception {
        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy test:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

**Đừng hiểu nhầm test MFA:** `SecurityMockMvcRequestPostProcessors.user(...)` **giả lập một Authentication** để kiểm tra authorization. Nó không thực hiện password login, không kiểm tra TOTP/WebAuthn và không xác nhận hệ thống có MFA thật. Test chỉ chứng minh rằng khi một thành phần đáng tin cậy đã cấp authority `MFA_VERIFIED`, rule sẽ cho phép. Production phải có verifier và test riêng cho enrollment, challenge binding, factor freshness, replay và recovery.

Test Basic và Bearer kiểm tra đường đi qua filter của demo. Những status là **kỳ vọng theo code**, cần chạy Gradle trên project thật để xác minh build.

## 9. Ví dụ production: OAuth2 Client và Resource Server

### 9.1. Service chủ động lấy token bằng client_credentials

Cấu hình cho **ứng dụng gọi API khác** với `spring-boot-starter-oauth2-client`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          report-worker:
            provider: company-idp
            client-id: ${WORKER_CLIENT_ID}
            client-secret: ${WORKER_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: jobs.read
        provider:
          company-idp:
            token-uri: https://idp.example.test/oauth2/token
~~~

YAML trên là **ví dụ cấu hình**, không tự gửi request và cần IdP thật. Ứng dụng còn phải sử dụng OAuth2 Client support/`OAuth2AuthorizedClientManager` hoặc tích hợp tương đương để lấy và gắn access token vào outgoing requests. Bảo vệ client secret bằng secret manager và rotate; service principal dùng cho token lifecycle phải được chọn đúng thay vì tái sử dụng ngẫu nhiên danh tính user trong browser.

### 9.2. Resource Server xác minh JWT từ issuer

API **nhận** token có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/company
~~~

Với `spring-boot-starter-oauth2-resource-server` và SecurityFilterChain:

~~~java
// Snippet trong cấu hình HttpSecurity:
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()));
~~~

Trong production cần **issuer thật** và audience validator/rule scope phù hợp. Không chỉ khai báo `issuer-uri` rồi giả định API đã kiểm tra mọi claim nghiệp vụ; phải test đúng audience, expiry, scopes, key rotation và các access token không thuộc API.

### 9.3. Resource Server xác minh opaque token bằng introspection

Tùy IdP, thay introspector demo bằng `SpringOpaqueTokenIntrospector` hoặc cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Resource Server dùng credential của **chính nó** để gọi introspection endpoint; đó là một ranh giới khác với credential của worker dùng ở token endpoint. Khi introspection fail hoặc token inactive, phải từ chối theo policy, không chuyển sang permitAll.

## 10. Phân biệt 401, 403 và mức assurance

| Tình huống | Diễn giải thường gặp |
| --- | --- |
| Không gửi user credential vào protected endpoint Basic | **401** (cần authentication) |
| User gửi password sai | **401** |
| Service gửi token sai/expired | **401** từ Bearer mechanism |
| Service token hợp lệ nhưng thiếu scope | **403** (authorization denied) |
| Alice đã đăng nhập, thiếu ROLE_ADMIN | **403** |
| Alice đăng nhập bằng password, chưa hoàn tất policy MFA | Có thể **403** hoặc **redirect/challenge** tùy cơ chế MFA/entry point |
| POST không có CSRF token khi bật CSRF | Có thể **403**, độc lập với MFA |
| User hoàn tất MFA nhưng không có quyền resource | Vẫn **403** hoặc quyết định từ chối tương ứng |
| Request không khớp SecurityFilterChain | Có thể **không được bảo vệ** nếu thiếu fallback chain |

**Không suy diễn chỉ từ status.** Trong demo, user và service dùng hai chain với entry point khác nhau. Trong web app có form login, thiếu authentication có thể trả 302 redirect tới login thay vì 401. Với MFA framework tự quản lý, thiếu factor có thể dẫn tới một luồng challenge thay vì JSON 403.

## 11. Bảo mật theo vòng đời identity

### 11.1. User lifecycle

Đăng ký, xác minh email, đặt password hash, khóa/disable, MFA enrollment, recovery, đổi password, session revocation và audit đều có ảnh hưởng đến xác thực. `UserDetailsService` không tự triển khai toàn bộ các tác vụ này.

### 11.2. Workload lifecycle

Provision client ID/workload identity, scopes tối thiểu, secret/certificate rotation, token expiry, revoked clients, environment isolation, audit và least privilege. Token ngắn hạn giảm tác động khi bị đánh cắp; có thể cần sender-constrained token theo threat model.

### 11.3. MFA lifecycle

Enrollment phải có user binding; verifier phải kiểm tra nonce/challenge, thời hạn và replay; session/token assurance phải expire; thêm/đổi factor và recovery là high-risk actions. Không dùng mã OTP/seed trong log, metrics hoặc URL.

### 11.4. Token và authorities có thể cũ

Đổi role trong DB không tự thay role trong JWT đã phát; khóa service client không tự vô hiệu hóa mọi token nếu cơ chế revoke không được triển khai; MFA thành công một lần không đồng nghĩa mãi mãi phù hợp cho step-up. Cần cơ chế **revalidation và thu hồi** theo độ nhạy nghiệp vụ.

## 12. Các lỗi phổ biến

### 12.1. Cho rằng MFA là một service account

MFA là quá trình tăng assurance của chủ thể. Service identity vẫn là service identity; user identity vẫn là user identity.

### 12.2. Coi client_credentials là user delegation

Access token kiểu client credentials đại diện client, không mặc định có user subject. Nếu service thay mặt user, cần ủy quyền và audit rõ.

### 12.3. Dùng một secret chung cho mọi worker

Lộ một secret có thể mở quá nhiều quyền. Tách service identities, scope, environment và rotation.

### 12.4. Tin JWT chỉ vì đọc được payload

Cần signature, issuer, audience, time và policy validation, không chỉ Base64 decode.

### 12.5. Dùng `.authenticated()` rộng mà không phân biệt subject

Một service đã xác thực có thể đáp ứng `authenticated()` nhưng không có quyền user. Phải kiểm tra scope/role/principal type/issuer, resource và delegation.

### 12.6. Hai password/PIN được gọi là MFA

Cùng knowledge factor nên không chứng minh hai nhóm yếu tố độc lập.

### 12.7. Chấp nhận MFA marker do client gửi

`X-MFA-Verified` hoặc role `MFA_VERIFIED` từ request không thể thay factor verification.

### 12.8. Cấp MFA_VERIFIED ngay trong UserDetailsService

Nếu UserDetails luôn có marker này, user chỉ cần password là thỏa rule, làm mất ý nghĩa step-up. Marker phải được cấp bởi cơ chế verifier đáng tin và có freshness.

### 12.9. Coi TOTP là phishing-resistant

Mã nhập tay có thể bị relay. WebAuthn có bảo vệ domain tốt hơn khi triển khai đúng.

### 12.10. Dùng ID token như access token

ID token phục vụ OIDC client; API phải nhận access token đúng audience/scope.

### 12.11. Bỏ qua CSRF vì login đã MFA

MFA và CSRF bảo vệ những mối đe dọa khác nhau; session/browser vẫn phải có CSRF policy phù hợp.

### 12.12. Quên fallback chain

`securityMatcher("/service/**")` chỉ chọn service paths. Nếu không có chain bảo vệ phần còn lại, các URL khác có thể nằm ngoài Spring Security.

### 12.13. Chỉ test happy path

Cần test anonymous, sai password, token sai, thiếu scope, thiếu role, thiếu factor, invalid issuer/audience, stale assurance và ownership; không coi 200 đủ để kết luận an toàn.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Một cron job dùng OAuth2 client_credentials. Nó là user hay service?

**Đáp án:** Service/client identity, không mặc định đại diện user cuối.

**Câu 2.** Password + PIN có chắc là MFA?

**Đáp án:** Không. Chúng đều là knowledge factor.

**Câu 3.** `SCOPE_jobs.read` có đồng nghĩa `ROLE_ADMIN`?

**Đáp án:** Không. Rule yêu cầu đúng authority theo scope/role mapping.

**Câu 4.** User ROLE_USER đã hoàn thành MFA có được đọc order của tenant khác?

**Đáp án:** Không nếu ownership/tenant policy từ chối. MFA không thay authorization.

**Câu 5.** Worker có thể gửi `X-Service: admin` để được xem là admin?

**Đáp án:** Không. Identity và authorities phải đến từ credential/token được xác minh.

**Câu 6.** JWT có payload đúng nhưng chữ ký sai thì API nên làm gì?

**Đáp án:** Từ chối token; không coi claims là trusted.

**Câu 7.** Resource Server tự phát access token khi bật `.oauth2ResourceServer(...)`?

**Đáp án:** Không. Nó xác minh token; Authorization Server phát, OAuth2 Client dùng token.

**Câu 8.** Một token có claim `amr=["pwd","otp"]` do client tự gửi đã đủ chứng minh MFA?

**Đáp án:** Không. Phải xác minh nguồn/token và hợp đồng IdP, user binding, freshness.

**Câu 9.** Vì sao không nên trả nguyên Authentication làm JSON?

**Đáp án:** Nó có thể chứa credentials/token, principal nội bộ và metadata không dành cho client.

**Câu 10.** Tại sao test MockMvc gắn user với marker MFA không chứng minh OTP đã được kiểm tra?

**Đáp án:** Đó là mock authorization; còn thiếu factor verifier và test end-to-end.

**Câu 11.** MFA tại login khác step-up?

**Đáp án:** Login yêu cầu factor ngay trước khi cấp phiên; step-up yêu cầu factor bổ sung ở thời điểm action nhạy cảm, có thể cần recent authentication.

**Câu 12.** Tại sao client secret rotation quan trọng với service?

**Đáp án:** Giảm cửa sổ lộ credential và cho phép thu hồi workload bị compromise.

**Câu 13.** Passkey nào cũng tự chứng minh MFA?

**Đáp án:** Không. Phụ thuộc authenticator và trạng thái user verification/policy.

**Câu 14.** Khi service cần thao tác trên tài nguyên của Alice, dùng client_credentials đủ chưa?

**Đáp án:** Chưa chắc. Có thể cần user delegation/on-behalf-of cùng quyền owner/tenant và audit.

**Câu 15.** Spring Security 7 factor authority có thể copy vào Boot3/Security6 không?

**Đáp án:** Không nguyên xi. Kiểm tra phiên bản; ví dụ trên chỉ là snippet của Spring Security 7.

## 14. Tài liệu tham khảo chính thức

- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **Username/Password Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security 6.5 — **OAuth2 Resource Server**: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/
- Spring Security 6.5 — **Opaque Token**: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security — **OAuth2 Client/client_credentials**: https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html
- Spring Security — **OAuth2 Login**: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security 7 — **MFA (FactorGrantedAuthority)**: https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html
- Spring Security — **Authorization / Request Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- OWASP — **Multi-Factor Authentication Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- NIST SP 800-63B — **Authenticator Management**: https://pages.nist.gov/800-63-4/sp800-63b.html

**Ghi nhớ:** **User authentication** xác minh user; **service authentication** xác minh workload, thường không có end-user; **MFA** dùng các yếu tố độc lập để tăng độ tin cậy của một danh tính. Dù xác thực theo cách nào, Spring Security vẫn cần authorization đúng **principal, role/scope, resource, tenant và assurance**. Không lấy token service làm user token, cũng không coi MFA là quyền quản trị.
