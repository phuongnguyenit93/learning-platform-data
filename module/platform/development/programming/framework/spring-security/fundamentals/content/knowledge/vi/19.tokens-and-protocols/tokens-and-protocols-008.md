# OpenID Connect bổ sung danh tính và ID token trên nền OAuth2

> **Module:** Spring Security - fundamentals  
> **Nhóm:** Token và giao thức  
> **Trọng tâm:** OAuth 2.0 cung cấp cơ chế ủy quyền truy cập tài nguyên; OpenID Connect (OIDC) bổ sung một **lớp xác thực danh tính người dùng** trên OAuth 2.0 bằng `openid` scope, ID token và các quy tắc xác minh bắt buộc.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

- Giải thích tại sao **access token của OAuth 2.0 không đồng nghĩa với ID token** và không đủ để chuẩn hóa việc đăng nhập.
- Nhận diện End-User, Relying Party (RP), OpenID Provider (OP), Authorization Server và Resource Server.
- Đọc và hiểu `iss`, `sub`, `aud`, `exp`, `iat`, `nonce`, `auth_time`, `azp` và các claims tùy chọn trong ID token.
- Mô tả OIDC Authorization Code Flow với `state`, `nonce` và PKCE, biết nơi xác minh ID token.
- Phân biệt ID token, access token, refresh token, UserInfo và local Spring SecurityContext.
- Cấu hình Spring Boot OAuth2/OIDC client với `oauth2Login()` và lấy `OidcUser` trong controller.
- Test OIDC principal bằng MockMvc `oidcLogin()` mà **không nhầm** mock test với kiểm tra chữ ký/issuer/audience của ID token thật.
- Áp dụng nhận diện tài khoản dựa trên cặp `issuer + subject` và tách biệt identity với role/authority.

## 2. OAuth 2.0 làm gì và thiếu gì cho mục tiêu đăng nhập?

**OAuth 2.0** thiết kế luồng ủy quyền cho phép một client gọi API được bảo vệ với access token. Ví dụ một ứng dụng muốn đọc ảnh từ dịch vụ ảnh:

~~~text
User đồng ý cấp quyền đọc ảnh
       |
       v
Authorization Server cấp access token cho Client
       |
       v
Client gọi Resource Server với access token
       |
       v
Resource Server kiểm tra quyền/scope và xử lý request
~~~

Quy trình đó nói về **quyền sử dụng tài nguyên**. OAuth 2.0 thuần không định nghĩa một ID token chuẩn để client biết chắc “End-User nào đã được một nhà cung cấp danh tính xác thực cho chính client này”.

Nhiều hệ thống từng dùng OAuth2 access token và một API profile tự đặt để mô phỏng đăng nhập. Cách này có thể thành công trong một hệ thống riêng nhưng thiếu quy tắc chung để liên thông: access token có thể là opaque string, JWT với audience dành cho API hoặc có định dạng mà client không được phép dựa vào.

**OpenID Connect 1.0** giải quyết khoảng trống này bằng một **identity layer trên OAuth 2.0**: RP gửi authentication request có `openid`, OP xác thực End-User và cung cấp **ID token** theo quy tắc chuẩn.

| Khía cạnh | OAuth 2.0 | OpenID Connect |
| --- | --- | --- |
| Câu hỏi chính | Client được truy cập API nào và với quyền gì? | OP đã xác thực End-User nào cho RP? |
| Thành phần | Client, Resource Owner, Authorization Server, Resource Server | Bổ sung RP, OP, End-User và ID token |
| Scope bắt buộc để nhận diện flow | Không có scope chung “đăng nhập” | `openid` đánh dấu OIDC authentication request |
| Token phục vụ mục tiêu chính | **Access token** | **ID token** dành cho RP; vẫn dùng access token trong OAuth2 |
| User identity theo chuẩn | Không được bảo đảm từ access token | `iss` và `sub` trong ID token đã xác minh |
| Thông tin profile | Tùy API/provider | Standard Claims và UserInfo endpoint khi hỗ trợ |
| Cơ chế tài nguyên | Resource Server xác minh access token | OIDC không thay thế resource server authorization |

**Không nói “OIDC thay thế OAuth2”.** OIDC tái sử dụng authorization endpoint, token endpoint, redirect URI, authorization code và cơ chế bảo mật OAuth2 để bổ sung thông điệp xác thực người dùng.

## 3. Vai trò trong một luồng OIDC

~~~text
               Browser / End-User
                       |
                       v
             Spring Boot App / RP
              (OIDC OAuth2 Client)
                       |
          authorization code request
                       |
                       v
            OpenID Provider (OP)
       Identity Provider / Authorization Server
                 |             |
               ID token     Access token
                 |             |
                 v             v
                RP        Resource Server
                 |        API được bảo vệ
                 v
           Local SecurityContext
           / HttpSession khi dùng
~~~

- **End-User:** người dùng cuối được xác thực.
- **Relying Party (RP):** ứng dụng tin vào kết quả OIDC; ở đây là Spring Boot OAuth2 Client.
- **OpenID Provider (OP):** máy chủ xác thực End-User và phát ID token. Trong thực tế thường gọi Identity Provider (IdP).
- **Authorization Server:** cấp access token và những token liên quan theo OAuth2; trong OIDC OP đóng vai trò này.
- **Resource Server:** API sử dụng **access token** để quyết định truy cập tài nguyên.
- **Client Registration:** metadata của client tại OP: client ID, redirect URI, phương thức xác thực client, scopes, và các endpoint liên quan.

Đừng nhầm **ai nhận token**: ID token dành cho RP, access token dành cho Resource Server phù hợp. Cùng một chuỗi JWT có chữ ký đúng vẫn có thể **sai audience** và không thể dùng thay vai trò token khác.

## 4. ID token là gì?

ID token là thông điệp OIDC thể hiện kết quả xác thực End-User dành cho RP cụ thể. ID token thường là **JWT được ký theo JWS**; trong cấu hình đặc biệt có thể là JWT mã hóa (JWE) theo chuẩn.

Một JWS JWT thường có cấu trúc:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Payload của JWT được ký **không được mã hóa**. Ai có chuỗi token có thể giải mã Base64url để đọc claims, dù chưa có key kiểm tra chữ ký. Vì vậy không chứa bí mật/PII không cần thiết và không ghi ID token thô vào log.

Ví dụ **payload minh họa**, không phải JWT có chữ ký hợp lệ:

~~~json
{
  "iss": "https://idp.example.invalid/tenant-a",
  "sub": "user-3812",
  "aud": "demo-web-client",
  "exp": 1900003600,
  "iat": 1900000000,
  "nonce": "random-nonce-correlating-a-request",
  "auth_time": 1899999970,
  "name": "Example User",
  "email": "user@example.invalid",
  "email_verified": true
}
~~~

Địa chỉ `.invalid` và timestamps chỉ dành cho ví dụ; không mang ý nghĩa token hiện tại dùng được.

### Claims cốt lõi

| Claim | Bắt buộc trong ID token? | Ý nghĩa |
| --- | --- | --- |
| `iss` | Có | Issuer identifier; RP phải so khớp chính xác issuer đã tin cậy |
| `sub` | Có | Subject identifier của End-User trong phạm vi issuer |
| `aud` | Có | Audience(s); phải chứa `client_id` của RP nhận ID token |
| `exp` | Có | Expiration time; token hết hạn phải bị từ chối |
| `iat` | Có | Issued-at time; có thể kiểm tra tuổi token theo policy |
| `nonce` | Có điều kiện theo flow/request | Ràng buộc ID token với authentication request; trong code flow phải kiểm tra nếu đã gửi |
| `auth_time` | Có điều kiện, ví dụ request dùng `max_age` | Thời điểm OP đã xác thực End-User |
| `azp` | Theo điều kiện multiple audiences | Authorized party; dùng theo quy tắc OIDC Core |
| `at_hash` | Tùy flow; optional với code flow | Có thể ràng buộc access token với ID token |
| `acr`, `amr` | Tùy chọn | Authentication context / methods nếu OP cung cấp |
| `email`, `name`, `picture`, `email_verified` | Tùy chọn | Standard Claims về hồ sơ, không phải quyền quản trị |

OIDC không bảo đảm mọi OP trả `email` hoặc `name` trong tất cả trường hợp. Scope `profile`/`email`, consent và provider policy ảnh hưởng các claims mà RP nhận.

### Nhận diện tài khoản đúng: cặp `(iss, sub)`

`sub` là định danh subject trong phạm vi issuer; không suy ra từ trùng `sub` của hai OP rằng đó là cùng user.

~~~text
Issuer A: https://idp-a.example.invalid | sub=42
Issuer B: https://idp-b.example.invalid | sub=42

Đây KHÔNG được tự động coi là cùng một identity.
~~~

`email` có thể thay đổi hoặc tái sử dụng và không phải khóa ổn định tuyệt đối. Khi liên kết account, lựa chọn thường phù hợp là cặp `issuer + subject`, với chính sách liên kết nhiều issuer/tenants rõ ràng. OP cũng có thể cấp **pairwise subject** khác nhau cho những clients khác nhau để giảm correlation giữa RP.

## 5. OIDC Authorization Code Flow

Với web app server-side, mô hình phổ biến là OIDC **Authorization Code Flow**, nên kết hợp PKCE phù hợp chính sách client.

~~~text
Browser             Spring Boot RP               OpenID Provider
   |                       |                             |
   | GET /me               |                             |
   |---------------------->|                             |
   |                       | redirect tới authorization   |
   |<----------------------|                             |
   | GET /authorize?scope=openid&response_type=code...    |
   |----------------------------------------------------->|
   |                       |       Login / consent       |
   |                       |                             |
   | 302 /login/oauth2/code/demo?code=...&state=...       |
   |<-----------------------------------------------------|
   |---------------------->|                             |
   |                       | check state, exchange code   |
   |                       | POST /token: code + verifier |
   |                       |----------------------------->|
   |                       | access_token + id_token      |
   |                       |<-----------------------------|
   |                       | XÁC MINH ID TOKEN            |
   |                       | Tạo OidcUser, Authentication |
   |                       | SecurityContext/session      |
   |<----------------------|                             |
   | request authenticated |                             |
~~~

### Authorization request

Một request có các tham số sau:

~~~text
GET https://idp.example.invalid/authorize
  response_type=code
  client_id=demo-web-client
  redirect_uri=https://app.example.invalid/login/oauth2/code/demo
  scope=openid profile email
  state=opaque-random-state
  nonce=opaque-random-nonce
  code_challenge=base64url(SHA256(code_verifier))
  code_challenge_method=S256
~~~

Đây là mô tả ý nghĩa, **không phải một URL đã percent-encode và không chứa giá trị mật mã thật**. Framework/library sẽ tạo URL hợp lệ và các random values an toàn.

- `openid`: bắt buộc để OP hiểu đây là OIDC authentication request.
- `response_type=code`: OP trả authorization code ở redirect; RP đổi code ở token endpoint.
- `state`: liên kết callback với request khởi tạo, chống login CSRF/authorization response injection.
- `nonce`: liên kết ID token với request xác thực; phải kiểm tra theo quy tắc flow.
- **PKCE:** client giữ `code_verifier`, gửi `code_challenge` trước, chứng minh sở hữu verifier khi đổi code. Thường dùng phương thức `S256`.
- `redirect_uri`: phải được OP xác nhận theo client registration; không lấy URL redirect tùy ý của attacker.

Không dùng implicit flow cho thiết kế mới chỉ vì muốn “nhận ID token trực tiếp từ browser”. Authorization Code + PKCE giúp hạn chế việc phát token vào front-channel và tăng bảo vệ trước code interception.

### Token response

OP có thể trả:

~~~json
{
  "access_token": "opaque-or-jwt-access-token",
  "token_type": "Bearer",
  "expires_in": 600,
  "id_token": "signed-oidc-id-token",
  "refresh_token": "optional-refresh-token"
}
~~~

Các giá trị là **placeholder mô tả**. Refresh token có được cấp hay không phụ thuộc grant, scope, consent và provider policy.

| Token | Nơi chủ yếu tiêu thụ | Cách dùng |
| --- | --- | --- |
| **ID token** | RP/OIDC client | Xác minh OP đã xác thực ai; audience là RP |
| **Access token** | API/Resource Server | Cho phép API đánh giá quyền/scopes theo token |
| **Refresh token** | Token endpoint/Authorization Server | Xin access token mới theo chính sách sống/rotation/revocation |

Không gửi ID token vào `Authorization: Bearer` để truy cập API chỉ vì đó là JWT có chữ ký. Nếu Resource Server cần login identity của caller, nó vẫn phải xác minh **access token dành cho chính API** và sử dụng claims/authority mapping phù hợp.

## 6. ID token validation: “decode” khác hoàn toàn “verify”

Giải mã Base64url không kiểm tra được chữ ký, người phát hành, audience hay khả năng token đã bị sửa. Một RP không được coi dữ liệu unverified trong JWT như authentication đáng tin.

Checklist xác minh ID token theo OIDC Core và cấu hình ứng dụng:

1. **Signature + algorithm:** tin key/JWKS của issuer đã cấu hình; kiểm tra chữ ký và thuật toán theo trust policy. Không chấp nhận `alg=none` một cách tùy tiện.
2. **Issuer `iss`:** phải khớp **chính xác** với issuer đã biết, không dùng substring/hostname heuristic.
3. **Audience `aud`:** phải chứa `client_id` của RP. Token ký hợp lệ nhưng cấp cho client khác phải bị từ chối. Xử lý `azp` nếu có multiple audiences theo OIDC Core.
4. **Thời hạn:** kiểm tra `exp`, `iat`, chính sách clock skew và `auth_time`/`max_age` khi yêu cầu.
5. **Request binding:** so sánh `state` của callback, `nonce` đã gửi và giá trị trong ID token; sử dụng PKCE đúng để đổi code.
6. **Token response/flow:** xác minh kết quả đến từ grant/token endpoint và client registration mong đợi; áp dụng `at_hash` khi flow/claim yêu cầu.
7. **UserInfo:** nếu gọi endpoint này, `sub` của UserInfo response phải bằng `sub` trong ID token; không kết hợp profile của một user khác.

**Đừng tự triển khai JOSE/JWT validator chỉ bằng split dấu chấm và Base64 decode** trong code production. Spring Security có các thư viện OAuth2/OIDC client hỗ trợ. Kế hoạch kiểm thử vẫn phải bao gồm token có `iss` sai, `aud` sai, `exp` quá hạn, chữ ký giả và nonce không khớp theo OIDC test fixture đáng tin.

### JWKS, `kid` và key rotation

OP thường công bố public keys qua `jwks_uri` trong discovery metadata. RP dùng keys phù hợp và thuật toán ký được hỗ trợ để kiểm tra JWS. Header `kid` thường giúp chọn key. Khi OP thay khóa, client cần chính sách cập nhật/cache JWKS phù hợp.

Không tự tin một URL JWK được attacker gắn vào JWT header; trust root đến từ cấu hình issuer/provider đáng tin, không đến từ token tự trình bày.

### Email và `email_verified` không cấp quyền

`email_verified=true` có thể cho biết OP đã xác minh email theo chính sách của nó, **không có nghĩa người này được cấp `ROLE_ADMIN`**. Identity và authorization là hai lớp khác nhau. Business authority phải lấy từ một chính sách cấp quyền đáng tin.

## 7. UserInfo là gì và khác ID token thế nào?

OIDC UserInfo endpoint có thể trả các Standard Claims về End-User khi RP gọi bằng access token phù hợp:

~~~text
RP -> UserInfo endpoint
       Authorization: Bearer <access-token>
    <- JSON: sub, name, email, picture...
~~~

Các điểm phân biệt:

- **ID token**: thông điệp authentication dành cho RP, có các claims bắt buộc như `iss`, `sub`, `aud`.
- **UserInfo**: nguồn claims hồ sơ bổ sung, tùy OP, scopes và consent; không thay việc xác minh ID token.
- **Subject consistency**: `sub` ở UserInfo **phải trùng** với `sub` ID token; nếu khác phải từ chối dữ liệu UserInfo.
- **Không bắt buộc tất cả claims**: scope `email` không bảo đảm một trường email luôn xuất hiện trong mọi môi trường.

Không dùng thông tin profile làm cơ chế xác định authority chỉ vì được trả từ UserInfo.

## 8. Spring Security và các vai trò OAuth2/OIDC

Trong Spring MVC/Servlet:

| Cấu hình Spring Security | Trách nhiệm |
| --- | --- |
| `oauth2Login()` | App làm RP/client: redirect qua OP, nhận code callback, đổi token, xác thực OIDC user |
| `oauth2Client()` | Client lấy và sử dụng access token để gọi API khác |
| `oauth2ResourceServer().jwt()` | App làm Resource Server: xác minh **bearer access token** dạng JWT dành cho API |
| `oauth2ResourceServer().opaqueToken()` | App làm Resource Server: token introspection |
| `formLogin()` | App tự xử lý username/password và local authentication flow |

Những thành phần dễ gặp:

- `ClientRegistrationRepository` chứa client ID, provider metadata, scope, redirect URI.
- `OAuth2AuthorizationRequestRedirectFilter` tạo authorization redirect.
- `OAuth2LoginAuthenticationFilter` xử lý callback `/login/oauth2/code/{registrationId}` và thiết lập authenticated principal.
- `OidcIdTokenDecoderFactory` và các thành phần liên quan tạo decoder cho ID token theo cấu hình.
- `OidcUser`/`OidcIdToken` biểu diễn principal và ID token đã được xử lý bởi OIDC login.
- `OAuth2AuthorizedClient` mô hình access/refresh token gắn với client registration.
- `SecurityContext` (có thể persisted trong `HttpSession`) chứa trạng thái đã xác thực ở local app.

Spring Security không tự coi scope `openid` là role `ROLE_USER` hoặc authority admin. Nếu cần role business, phải ánh xạ từ nguồn tin cậy và kiểm thử.

## 9. Ví dụ Spring Boot/Java 17 với OIDC client và MockMvc test

Chúng ta tạo một Spring MVC app có `oauth2Login()` và endpoint `GET /me` đọc `OidcUser`. Ví dụ dùng endpoint giả `.invalid` để chạy **MockMvc tests mà không cần IdP bên ngoài**.

**Giới hạn rõ ràng:** Bài test mô phỏng OIDC principal, không thực hiện code exchange hay xác minh JWS thật. Để login tương tác qua browser, cần thay các URL/provider/client secrets bằng IdP hợp lệ.

### 9.1. Cấu trúc file

~~~text
oidc-login-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/oidc/
    │   ├── OidcLoginApplication.java
    │   ├── SecurityConfig.java
    │   └── ProfileController.java
    ├── main/resources/
    │   └── application.yml
    └── test/java/demo/oidc/
        └── OidcLoginTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'oidc-login-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.2. Main application

File `src/main/java/demo/oidc/OidcLoginApplication.java`:

~~~java
package demo.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcLoginApplication.class, args);
    }
}
~~~

### 9.3. Spring Security filter chain

File `src/main/java/demo/oidc/SecurityConfig.java`:

~~~java
package demo.oidc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

`/health` công khai; `/me` yêu cầu authenticated. `oauth2Login()` dùng client registration để thực hiện OIDC login. Không cần bật `oauth2ResourceServer()` khi mục tiêu chỉ là browser login qua OP.

### 9.4. Controller đọc subject

File `src/main/java/demo/oidc/ProfileController.java`:

~~~java
package demo.oidc;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser principal) {
        String sub = principal.getIdToken().getSubject();
        String email = principal.getIdToken()
            .getClaimAsString("email");

        return Map.of(
            "subject", sub,
            "email", email == null ? "" : email
        );
    }
}
~~~

Controller không trả raw ID token. `subject` là ID của principal theo OP, không phải email. Nếu có nhu cầu account-linking với nhiều issuers, ứng dụng cần lưu thêm issuer đã xác minh.

### 9.5. Client registration giả cho tests

File `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-idp
            client-id: demo-client
            client-secret: placeholder-not-for-production
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo-idp:
            authorization-uri: https://idp.example.invalid/authorize
            token-uri: https://idp.example.invalid/token
            jwk-set-uri: https://idp.example.invalid/jwks
            user-info-uri: https://idp.example.invalid/userinfo
            user-name-attribute: sub
~~~

Các URL `.invalid` không phục vụ login thật. Chúng được khai báo tường minh để Spring không phải gọi OIDC Discovery tới một fake issuer khi dựng context cho MockMvc. Với môi trường thực, ưu tiên provider `issuer-uri` được OP công bố (và client ID/secret do secret management quản lý) nếu hỗ trợ discovery.

### 9.6. Test sử dụng `oidcLogin()`

File `src/test/java/demo/oidc/OidcLoginTest.java`:

~~~java
package demo.oidc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OidcLoginTest {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void meRequiresLogin() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void oidcPrincipalContainsSubject() throws Exception {
        mvc.perform(get("/me")
                .with(oidcLogin().idToken(token -> token
                    .claim("sub", "user-42")
                    .claim("email", "alice@example.invalid")
                )))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("user-42"))
            .andExpect(jsonPath("$.email")
                .value("alice@example.invalid"));
    }
}
~~~

Các static imports xuống dòng hợp lệ vì Java kết thúc câu lệnh import ở dấu chấm phẩy. `oidcLogin()` tạo OIDC principal giả gắn với request, phù hợp để kiểm tra Spring MVC controller lấy `OidcUser` từ SecurityContext.

Chạy ở project root với JDK 17+ và Gradle 8.x:

~~~bash
gradle test
~~~

Kết quả **kỳ vọng**: ba test thành công. Đây là phân tích từ mã mẫu, **không phải log thực thi**.

| Request | Authentication | Kỳ vọng |
| --- | --- | --- |
| `GET /health` | Anonymous | HTTP 200, body `ok` |
| `GET /me` | Anonymous | Redirect sang login |
| `GET /me` | Mock `oidcLogin()` với `sub=user-42` | HTTP 200, JSON có subject/email mong đợi |

**Hạn chế của MockMvc:** Không có trao đổi code tại token endpoint, không có OP thật cấp ID token, không kiểm tra JWS/JWKS, `iss`, `aud`, `exp` hay nonce của ID token thật. Để kiểm chứng các bước đó, cần integration test với test IdP hoặc setup có JWT decoder/protocol validation được kiểm soát.

### 9.7. Thay bằng OP thật

Nếu OP hỗ trợ Discovery, ví dụ cấu hình production/test dạng:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            client-id: CLIENT_ID_FROM_SECURE_CONFIGURATION
            client-secret: CLIENT_SECRET_FROM_SECURE_CONFIGURATION
            scope:
              - openid
              - profile
              - email
        provider:
          corporate:
            issuer-uri: https://real-issuer.example.org/realm/demo
~~~

**Đây là mẫu cấu hình**, không phải OP công khai đang hoạt động. Phải dùng issuer URI thật và cấu hình client secrets bằng environment/secret manager an toàn; không hardcode password production vào source. Khi dùng `issuer-uri`, framework có thể gọi Discovery khi khởi tạo registration, vì vậy URL phải truy cập được.

Với registration ID `corporate`, luồng mặc định có thể bắt đầu từ `/oauth2/authorization/corporate` và nhận callback ở `/login/oauth2/code/corporate`. OP phải cho phép redirect URI đã đăng ký; proxy/HTTPS/forwarded headers cần cấu hình đúng để sinh public base URL chuẩn.

## 10. Spring Security authority không tự lấy từ mọi claim OIDC

OIDC xác thực **identity**, còn phân quyền business là lớp khác.

- `sub`: ai được OP xác thực (trong issuer này).
- `scope`: điều kiện quyền OAuth2 client/token.
- `GrantedAuthority`: abstraction được Spring Security dùng trong authorization rules.
- `ROLE_ADMIN`, `document:edit`, quyền tenant: chính sách ứng dụng/IdP được tin cậy đã ánh xạ.

Spring Security có `OidcUserAuthority` để đại diện claims của ID token/UserInfo. Khi cần mapping authorities, dùng `GrantedAuthoritiesMapper` hoặc tùy biến OIDC user service, với policy và test độc lập.

~~~java
// ĐOẠN MINH HỌA, không phải class Java độc lập.
// "trustedMapper" là bean được ứng dụng định nghĩa.
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userAuthoritiesMapper(trustedMapper)
    )
);
~~~

Không tự động cho user `ROLE_ADMIN` vì `email_verified=true` hoặc email kết thúc bằng một chuỗi cụ thể. Nếu quyền thực sự do IdP quản lý, cần tin chính xác issuer, client, claim mapping, audience và chính sách thu hồi quyền. Khi business permission nằm trong database nội bộ, nên đọc nó qua lớp policy phù hợp sau khi identity được xác thực.

### Demo Java 17: subject phải đi cùng issuer

File `OidcIdentityKey.java`, chương trình Java 17 độc lập với Spring:

~~~java
import java.util.Objects;

public record OidcIdentityKey(String issuer, String subject) {

    public OidcIdentityKey {
        Objects.requireNonNull(issuer);
        Objects.requireNonNull(subject);
    }

    public static void main(String[] args) {
        OidcIdentityKey a =
            new OidcIdentityKey("https://a.invalid", "42");
        OidcIdentityKey b =
            new OidcIdentityKey("https://b.invalid", "42");
        OidcIdentityKey aAgain =
            new OidcIdentityKey("https://a.invalid", "42");

        System.out.println(a.equals(b));
        System.out.println(a.equals(aAgain));
    }
}
~~~

Chạy:

~~~bash
javac OidcIdentityKey.java
java OidcIdentityKey
~~~

Stdout chính xác:

~~~text
false
true
~~~

Bài demo minh họa khóa identity composite; **không** xác minh ID token. Trong hệ thống thật, `issuer`/`subject` chỉ được lấy từ authentication đã được OIDC client library xác minh.

## 11. Discovery và provider metadata

OP thường công bố OIDC metadata thông qua đường dẫn `.well-known/openid-configuration` theo quy tắc Discovery. Metadata có thể bao gồm:

| Metadata key | Vai trò |
| --- | --- |
| `issuer` | Tên OP dùng so khớp `iss` |
| `authorization_endpoint` | Địa chỉ xử lý authorization request |
| `token_endpoint` | Nơi đổi authorization code lấy tokens |
| `jwks_uri` | Bộ public keys kiểm tra chữ ký ID token |
| `userinfo_endpoint` | Nơi lấy profile claims nếu hỗ trợ |
| `response_types_supported` | Những response types OP hỗ trợ |
| `id_token_signing_alg_values_supported` | Những thuật toán ký ID token OP hỗ trợ |
| `end_session_endpoint` | Logout endpoint nếu OP hỗ trợ/công bố |

Issuer có thể chứa path/realm; không tự ghép URL discovery bằng một phép nối chuỗi tùy tiện không theo chuẩn. Các endpoint tùy chọn có thể thiếu; không mặc định mọi OP cung cấp UserInfo hay logout cùng cách.

Quy tắc an toàn: **trust issuer được cấu hình**, kiểm tra metadata và validation theo issuer đó; không lấy URL provider từ một token chưa được xác minh rồi dùng nó làm nguồn tin cậy.

## 12. State, nonce, PKCE: ba lớp bảo vệ khác nhau

| Thành phần | Gắn với đâu? | Mục tiêu |
| --- | --- | --- |
| `state` | Authorization request và callback | Tương quan request/response, chống login CSRF |
| `nonce` | Authentication request và ID token | Chống replay/substitution ID token |
| PKCE `code_verifier`/`code_challenge` | Authorization request và token request | Bảo vệ việc đổi authorization code khi code bị đánh cắp |

Bật PKCE **không** cho phép bỏ kiểm tra `state` hoặc `nonce`. `nonce` cũng **không** thay việc xác minh chữ ký/issuer/audience. Chọn thư viện OAuth2/OIDC client được duy trì, không tự chế toàn bộ state machine và token validation trong controller.

## 13. Lỗi phổ biến

| Sai lầm | Nguy cơ | Cách đúng |
| --- | --- | --- |
| Dùng access token thay ID token | Nhầm quyền API thành bằng chứng login | Phân biệt token và audience |
| Không có scope `openid` | Request không phải OIDC login | Bật OIDC client đúng chuẩn |
| Base64 decode ID token rồi tin claims | Token giả hoặc bị sửa được tin | Xác minh JWS, issuer, audience, expiry và binding |
| Chỉ xem `sub`, bỏ issuer | Gộp user của các OP khác nhau | Dùng `iss + sub` |
| Dùng email làm khóa identity | Email đổi/tái sử dụng/không có | Dùng subject được xác minh |
| Không check `aud` | Nhận token của client khác | Audience phải chứa client ID của RP |
| Dùng ID token gọi API | API nhận sai loại token | Gửi access token phù hợp |
| Coi `email_verified` là role admin | Cấp quyền quá mức | Authorization policy và trusted mapping |
| Bỏ `state`, `nonce` hoặc PKCE | Tăng rủi ro tấn công flow/replay | Dùng thư viện và cấu hình chuẩn |
| Xem MockMvc `oidcLogin()` như test JWT thật | Bỏ sót lỗi issuer/JWKS/nonce | Kiểm thử OP thật hoặc dedicated security integration |
| Dùng issuer/redirect URI tùy ý từ user input | Token confusion/open redirect | Dùng registered issuer/redirect allowlist |
| Log raw ID/access token | Lộ credential/PII | Redact logs, bảo vệ token storage |

## 14. Tự kiểm tra kiến thức

**Câu 1.** Một client có access token của OAuth2 có thể coi đó là ID token OIDC?

**Đáp án:** Không. Access token dành cho Resource Server/API; ID token là thông điệp authentication dành cho RP với claims/validation riêng.

**Câu 2.** Thiếu `openid` scope thì request có phải OIDC authentication request?

**Đáp án:** Không. Nó có thể là OAuth2 authorization request hợp lệ nhưng không có nghĩa vụ trả OIDC ID token.

**Câu 3.** Hai tokens có `sub=42` nhưng issuer khác nhau có cùng account không?

**Đáp án:** Không thể kết luận như vậy; cần xét cặp `iss + sub` và account-linking policy.

**Câu 4.** Vì sao token có chữ ký hợp lệ vẫn phải kiểm tra `aud`?

**Đáp án:** Vì OP có thể ký token cho client khác; RP chỉ được chấp nhận token dành cho chính client ID của mình.

**Câu 5.** `state`, `nonce` và PKCE có phải ba cách làm cùng một việc?

**Đáp án:** Không. State gắn callback với request; nonce gắn ID token với authentication request; PKCE bảo vệ authorization code exchange.

**Câu 6.** Test `oidcLogin()` pass đã chứng minh ký JWT/issuer/nonce thật hợp lệ?

**Đáp án:** Chưa. Mock principal test không trao đổi code với OP và không xác minh chữ ký token thật.

**Câu 7.** `email_verified=true` có tự cấp quyền quản trị không?

**Đáp án:** Không. Nó chỉ là profile claim theo chính sách OP, business permissions phải được cấp và ánh xạ riêng.

## 15. Checklist khi làm OIDC Login trong Spring Security

- [ ] RP đăng ký với OP đúng `client_id`, redirect URI và client authentication method.
- [ ] Request có `openid`, dùng code flow và PKCE theo client policy.
- [ ] `state`, `nonce`, callback correlation và HTTPS đúng.
- [ ] Xác minh ID token signature/algorithm, `iss`, `aud`, `exp` và conditional claims.
- [ ] Dùng `OAuth2AuthorizedClient`/`OidcUser` đúng vai trò thay vì tự parse JWT.
- [ ] Không gửi ID token làm bearer token cho Resource Server.
- [ ] Nếu dùng UserInfo, kiểm tra `sub` trùng với ID token.
- [ ] Liên kết account dựa trên issuer+subject, không chỉ email.
- [ ] Định nghĩa authority mapping và business policy độc lập.
- [ ] Không log access/refresh/ID token hoặc client secret.
- [ ] Có MockMvc unit/integration tests và OIDC end-to-end tests với OP thật.
- [ ] Thiết kế riêng local session/logout, IdP SSO session và token revocation.

## 16. Tổng kết và tài liệu tham khảo

**OAuth2 là nền tảng ủy quyền; OIDC bổ sung lớp xác thực danh tính và ID token trên nền đó.** ID token đã được xác minh cho RP mô tả ai (`iss + sub`) đã được OP xác thực, token dành cho client nào (`aud`) và trong khoảng thời gian nào (`iat`/`exp`). Access token vẫn dành cho API; refresh token dùng xin token mới. Trong Spring Security, `oauth2Login()` xử lý OIDC client flow, còn `oauth2ResourceServer()` xác minh access token của API.

Tài liệu chính thức:

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OAuth 2.0 Authorization Framework — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749)
- [PKCE — RFC 7636](https://www.rfc-editor.org/rfc/rfc7636)
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — Testing OIDC Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
