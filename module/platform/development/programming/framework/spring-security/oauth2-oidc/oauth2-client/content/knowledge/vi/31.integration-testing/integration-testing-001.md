# 31.1. Dựng provider thử nghiệm và tài khoản dành riêng cho test

## 1. Vì sao cần một OpenID Provider thử nghiệm thực sự?

Ở những bài kiểm thử đơn vị, Spring Security Test cho phép giả lập người dùng bằng <code>oidcLogin()</code> hoặc <code>oauth2Login()</code>. Điều đó rất hữu ích khi muốn kiểm tra controller, method security hoặc cách ánh xạ quyền của một principal.

Tuy nhiên, một OIDC Client thực sự phải đi qua nhiều thành phần khác:

1. Lấy OpenID Provider metadata từ Discovery Endpoint.
2. Chọn <code>ClientRegistration</code> đúng provider, Client ID, scopes và callback URI.
3. Tạo authorization request với <code>state</code>, <code>nonce</code> và PKCE khi được cấu hình.
4. Điều hướng browser đến Authorization Endpoint.
5. Xác thực test user tại OP và hoàn tất consent/chính sách của provider.
6. Nhận authorization code qua callback.
7. Gửi code đến Token Endpoint bằng client authentication và <code>code_verifier</code> nếu dùng PKCE.
8. Xác minh ID Token, chữ ký/JWK, <code>iss</code>, <code>aud</code>, <code>exp</code>, <code>nonce</code> khi áp dụng.
9. Tạo <code>OidcUser</code>, <code>OAuth2AuthenticationToken</code>, HTTP session và <code>OAuth2AuthorizedClient</code>.
10. Sau đó mới kiểm tra redirect, UserInfo, refresh, logout hoặc API calls.

Một test chỉ đặt <code>OidcUser</code> vào <code>SecurityContext</code> **không xác minh được** toàn bộ chuỗi trên. Đó là lý do chương **31. Kiểm thử tích hợp** cần một **OpenID Provider thử nghiệm có cấu hình tái lập được** và các **tài khoản không dùng trong production**.

> **Mục tiêu:** Dựng một OP test cô lập, khai báo chính xác OIDC ClientRegistration, tạo test users ổn định và chạy được những tình huống đăng nhập thành công/thất bại mà không chạm tài khoản, secrets hoặc dữ liệu production.

Trong bài, ta dùng **Keycloak làm provider thử nghiệm**. Đây là một lựa chọn thực tế, không phải yêu cầu bắt buộc: các nguyên tắc vẫn áp dụng với Dex, một OP sandbox do tổ chức quản lý hoặc một fake OP triển khai đủ giao thức. Ví dụ tập trung vào **Spring Boot 3.x, Spring Security 6.x, Java 17 và Servlet stack**; khi áp dụng với Spring Security 7.x hoặc một Keycloak version khác, cần đối chiếu API và cấu hình của đúng phiên bản đang sử dụng.

## 2. Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt unit test dùng mock principal, protocol test với stub và end-to-end test với OP thật.
- Thiết kế môi trường test cô lập theo **realm/tenant, ClientRegistration, users, scopes và redirect URIs**.
- Khởi chạy một Keycloak test realm bằng Docker Compose hoặc Testcontainers.
- Import realm và tạo test users/client test **theo fixture xác định**, không cần nhập thủ công trong Admin Console mỗi lần.
- Cấu hình Spring Security OAuth2 Client trỏ tới **issuer** của provider test.
- Xác minh Discovery document, JWKS, ID Token issuer/audience và callback URI tương ứng.
- Đăng nhập bằng Authorization Code Flow qua browser, không sử dụng Resource Owner Password Credentials (ROPC) để “giả lập” OIDC browser login.
- Tổ chức test accounts có quyền khác nhau, account bị vô hiệu hóa và các negative scenarios.
- Quản lý vòng đời secrets, dữ liệu cá nhân giả, ports, containers, parallel tests và CI isolation.
- Nhận diện các lỗi thường gặp như issuer mismatch, redirect URI mismatch, missing state, cookie/SameSite và JWKS lookup failure.

## 3. Lựa chọn loại provider theo mức kiểm thử

| Lựa chọn | Sức mạnh | Hạn chế | Khi nên dùng |
|---|---|---|---|
| <code>SecurityMockMvcRequestPostProcessors.oidcLogin()</code> | Rất nhanh; kiểm thử controller/authorization | Không có code exchange, Discovery, signature, OP UI | Unit/MVC security tests |
| Mock <code>OidcUserService</code> hoặc token response client | Cô lập một integration boundary | Không chứng minh OP metadata, JWT issuance hay redirect | Focused component tests |
| HTTP stub như WireMock/MockWebServer | Điều khiển 400/401/503, invalid_grant, malformed response | Muốn giả OP đầy đủ phải tự xây metadata/JWKS/JWT/authorization flow đúng chuẩn | Negative protocol tests, fault injection |
| Keycloak hoặc OP thật trong container | Kiểm tra Discovery, authorization code, login UI, consent, token/JWKS | Chậm hơn, cần Docker/browser và quản lý phiên bản | Integration/E2E OIDC Login |
| Sandbox của provider bên ngoài | Gần behavior provider mà production dùng | Hạn chế tài khoản, mạng, throttling, tính xác định | Compatibility/contract tests |

**Không nhất thiết chọn một trong các lựa chọn trên.** Một test suite tốt có các tầng:

~~~mermaid
flowchart TD
    U["Unit/MVC tests: mock OidcUser"] --> C["Component tests: stubs/token HTTP"]
    C --> I["Integration tests: local OP container"]
    I --> E["Browser E2E: OP + Portal + browser"]
    E --> S["Sandbox compatibility: provider production-like"]
~~~

Test provider trong container xác minh hành vi giao thức của một OP cụ thể. Nó **không chứng minh** production OP hỗ trợ mọi tính năng y hệt, nhất là logout, <code>prompt</code>, tenant routing, MFA hoặc refresh-token rotation.

## 4. Kiến trúc môi trường kiểm thử

Ví dụ:

~~~text
Developer / CI
    |
    +--- Browser/Playwright
    |        |
    |        v
    |    http://localhost:18080
    |        |
    |        v
    |    Spring Boot Portal (OIDC Client)
    |        |
    |        +---- OIDC Discovery/JWKS/Token Endpoint
    |        |             |
    |        |             v
    |        |    http://localhost:18081/realms/it-realm
    |        |             |
    |        |             v
    |        |    Keycloak test container
    |        |
    |        +---- Fake Reports API / test database
    |
    +--- JUnit + Testcontainers
             |
             +---- Ephemeral Keycloak on random host port
             +---- Test clients/users/realm fixture
~~~

Hai cách chạy trong bài:

**A. Local browser flow:** Portal dùng cổng <code>18080</code>, Keycloak dùng <code>18081</code>. Callback được đăng ký chính xác:

~~~text
http://localhost:18080/login/oauth2/code/it-op
~~~

**B. Testcontainers trong JUnit:** Keycloak dùng **random mapped host port** để các test processes không xung đột. Ta inject <code>issuer-uri</code> động qua <code>@DynamicPropertySource</code>; cần bảo đảm Discovery issuer thật trùng external URL của container. Bản demo Testcontainers đầu tiên là **smoke test provider**, không tự chạy browser login.

**Không trộn tùy tiện hai mô hình ports.** Authorization code luôn bị ràng buộc với redirect URI đã đăng ký tại OP; HTTP callback từ browser phải tới đúng địa chỉ mà Portal phục vụ.

## 5. Nguyên tắc cô lập môi trường test

Một OP test đáng tin cậy cần:

1. **Issuer/realm riêng:** không dùng production issuer hoặc production realm.
2. **Client ID riêng:** ví dụ <code>portal-it</code>, không dùng production Client ID.
3. **Test accounts riêng:** user giả không trùng người dùng thật.
4. **Secrets riêng:** client secret và mật khẩu test không được tái sử dụng ở production.
5. **Redirect URI riêng:** chỉ callback local/CI đã kiểm soát.
6. **Scopes/quyền tối thiểu:** bắt đầu với <code>openid</code>, <code>profile</code>, <code>email</code> khi thật sự cần.
7. **Không chạm production API/database:** downstream integrations trỏ tới fake API/test DB.
8. **Dữ liệu xác định:** fixture có thể import lại giống nhau để test không phụ thuộc trạng thái cũ.
9. **Cổng/mạng giới hạn:** container local không được quảng bá public Internet.
10. **Lifecycle rõ ràng:** mỗi test run có cleanup; parallel tests không cùng sửa user/session state tùy tiện.

Ví dụ test data:

~~~text
realm           = it-realm
issuer          = http://localhost:18081/realms/it-realm
client_id       = portal-it
registrationId  = it-op
redirect_uri    = http://localhost:18080/login/oauth2/code/it-op
username        = alice.test
email           = alice@example.test
~~~

Domain <code>example.test</code> là placeholder/dữ liệu test. Không gửi mail thật, không dùng email của nhân viên hoặc khách hàng, không tạo account test bằng dữ liệu production.

## 6. Kế hoạch test accounts trước khi dựng provider

Không nên chỉ có một account <code>admin/admin</code> rồi dùng cho mọi scenario. Hãy lập ma trận:

| User test | Trạng thái | Vai trò/policy | Kịch bản kiểm thử |
|---|---|---|---|
| <code>alice.test</code> | enabled, email verified | Quyền reader | Đăng nhập OIDC thông thường |
| <code>bob.test</code> | enabled, email verified | Quyền khác Alice | Switch account, session isolation |
| <code>admin.test</code> | enabled | Quyền quản trị test app | Kiểm tra role mapping |
| <code>disabled.test</code> | disabled | Không cấp quyền | OP từ chối đăng nhập |
| <code>unverified.test</code> | enabled, email chưa verify | Chính sách tùy OP | Claims/verified email policy |
| <code>consent.test</code> | enabled | Consent bắt buộc | Đồng ý/từ chối consent |
| <code>mfa.test</code> | enabled | MFA/step-up theo flow test | <code>acr</code>/<code>amr</code> và policy |
| <code>partner.test</code> | realm/issuer khác | Partner | Multi-provider/mix-up |

**Không nhất thiết import tất cả accounts ngay.** Fixture cơ sở có thể tạo Alice/Bob/disabled; các scenarios cần consent/MFA/partner có fixture hoặc realm riêng để test độc lập.

### 6.1. Danh tính OIDC phải dựa trên issuer và subject

Trong OIDC, identity nên được phân biệt bằng:

~~~text
(iss, sub)
~~~

Không dùng email làm khóa toàn cục. Hai realms có thể phát ID Token cho:

~~~text
alice@example.test
~~~

nhưng đây vẫn là hai identities nếu <code>iss</code>/<code>sub</code> khác nhau.

### 6.2. Stable test subject

Nếu cần assert <code>sub</code> ổn định, có thể nhập realm user với ID cố định trong fixture. Nhưng test production logic không nên phụ thuộc Keycloak-specific username format hoặc UUID layout.

Đối với use case “user đã đổi account”, kiểm tra:

- ID Token <code>iss/sub</code> đã được xác minh.
- <code>OidcUser.getSubject()</code> đúng test identity.
- Authorized-client token thuộc registration/principal phù hợp.
- Session/caches/tenant không mang dữ liệu account cũ.

### 6.3. Không chia sẻ account có trạng thái mutable giữa tests

Nếu test A disable user Alice và test B đồng thời login Alice, test B có thể thất bại ngẫu nhiên.

Giải pháp:

- Mỗi test suite dùng realm hoặc container riêng.
- Mỗi test có users riêng khi cần mutate account.
- Reset account/consent/revocation state sau test.
- Chạy tuần tự những cases thay đổi cùng user nếu không thể cô lập.

## 7. Docker Compose: Keycloak dành cho local integration test

Một ví dụ compose khởi chạy Keycloak test qua HTTP local:

~~~yaml
services:
  keycloak-it:
    image: quay.io/keycloak/keycloak:26.0.0
    command: ["start-dev", "--import-realm"]
    environment:
      KC_HTTP_ENABLED: "true"
      KC_HOSTNAME_STRICT: "false"
      KC_BOOTSTRAP_ADMIN_USERNAME: "test-admin"
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${TEST_KEYCLOAK_ADMIN_PASSWORD:-local-only-test-password}
    ports:
      - "127.0.0.1:18081:8080"
    volumes:
      - ./src/test/resources/oidc/realm-integration.json:/opt/keycloak/data/import/realm-integration.json:ro
~~~

Lưu ý:

- Tag <code>26.0.0</code> chỉ là **một version minh họa có pin**, không phải tuyên bố đây là bản mới nhất. Dự án cần chọn và cố định version đã kiểm thử, lý tưởng là image digest.
- <code>start-dev</code> và HTTP chỉ dành cho **test local hoặc CI cô lập**; không phải cấu hình production.
- <code>127.0.0.1:18081:8080</code> giảm nguy cơ expose container ngoài máy local.
- <code>KC_HOSTNAME_STRICT=false</code> trong dev mode cho phép suy ra URL từ request theo cấu hình hostname của Keycloak; phải kiểm tra Discovery <code>issuer</code> sau khi chạy. Với proxy/CI public URL, có thể cần hostname settings rõ hơn.
- Admin password ở đây **chỉ dành cho fixture local**; không tái sử dụng, không public cổng admin.
- Chỉ mount realm JSON test, không mount production configuration hoặc database.

Lệnh ví dụ tại root dự án khi đã có compose file tương ứng:

~~~powershell
docker compose -f compose.oidc-it.yml up -d
docker compose -f compose.oidc-it.yml logs -f keycloak-it
~~~

Khi dừng:

~~~powershell
docker compose -f compose.oidc-it.yml down --volumes
~~~

<code>--volumes</code> chỉ dùng với compose stack test đã xác định. Không chạy lệnh phá dữ liệu production hoặc nhầm compose project.

### 7.1. Vì sao import realm thay vì click Admin Console?

Một hướng dẫn click tay:

~~~text
Open Admin Console
Create realm
Create client
Create users
Set roles
Set password
...
~~~

khó tái lập khi CI chạy headless, đổi môi trường hoặc reviewer kiểm chứng lỗi.

Realm fixture cho phép:

- Review cấu hình như code.
- Chạy lại cùng trạng thái test.
- Kiểm tra khác biệt qua version control.
- Không phụ thuộc thứ tự thao tác thủ công.
- Tái tạo test users/clients trong vài bước xác định.

Tuy nhiên, import một realm **đã tồn tại** có behavior khác nhau theo startup mode/provider. Để reset trạng thái hoàn toàn, dùng container/database test mới hoặc cơ chế import/reset được kiểm soát, không giả định <code>--import-realm</code> luôn ghi đè mọi chỉnh sửa cũ.

## 8. Realm fixture: test OIDC client và users

Ví dụ một file:

~~~text
src/test/resources/oidc/realm-integration.json
~~~

Nội dung mẫu:

~~~json
{
  "realm": "it-realm",
  "enabled": true,
  "sslRequired": "external",
  "clients": [
    {
      "clientId": "portal-it",
      "name": "Portal Integration Test Client",
      "enabled": true,
      "protocol": "openid-connect",
      "publicClient": false,
      "clientAuthenticatorType": "client-secret",
      "secret": "local-it-client-secret-not-for-production",
      "standardFlowEnabled": true,
      "implicitFlowEnabled": false,
      "directAccessGrantsEnabled": false,
      "serviceAccountsEnabled": false,
      "redirectUris": [
        "http://localhost:18080/login/oauth2/code/it-op"
      ],
      "webOrigins": [
        "http://localhost:18080"
      ]
    }
  ],
  "users": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "username": "alice.test",
      "enabled": true,
      "emailVerified": true,
      "email": "alice@example.test",
      "firstName": "Alice",
      "lastName": "Test",
      "credentials": [
        {
          "type": "password",
          "value": "local-only-alice-password",
          "temporary": false
        }
      ]
    },
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "username": "bob.test",
      "enabled": true,
      "emailVerified": true,
      "email": "bob@example.test",
      "firstName": "Bob",
      "lastName": "Test",
      "credentials": [
        {
          "type": "password",
          "value": "local-only-bob-password",
          "temporary": false
        }
      ]
    },
    {
      "username": "disabled.test",
      "enabled": false,
      "emailVerified": false,
      "email": "disabled@example.test"
    }
  ]
}
~~~

### 8.1. Giải thích ClientRegistration phía OP

- <code>clientId=portal-it</code>: Client ID test mà Portal sử dụng.
- <code>publicClient=false</code>: ví dụ confidential Client có secret.
- <code>standardFlowEnabled=true</code>: cho phép Authorization Code Flow.
- <code>implicitFlowEnabled=false</code>: không dùng implicit flow cho bài test này.
- <code>directAccessGrantsEnabled=false</code>: không dùng ROPC/password grant để giả lập browser login.
- <code>redirectUris</code>: exact callback URL mà OP chấp nhận.
- <code>webOrigins</code>: origin test nếu các browser features cần; không phải danh sách redirect URI.

**Một client secret nằm trong fixture test vẫn phải được coi là test-only.** Vì nó xuất hiện trong source code, không được mang client này vào public/staging/production deployment có dữ liệu thật. Với test environment có truy cập mạng chung, generate secrets động hoặc lấy từ CI secret store thay vì dùng placeholder được commit.

### 8.2. Giải thích users

- Alice và Bob là **hai OIDC subjects khác nhau**.
- Email thuộc domain <code>.test</code>, không gửi mail thật.
- Password test ở đây là dữ liệu giả chỉ dành cho isolated container.
- <code>enabled=false</code> giúp tạo negative login scenario.

Nếu cần test MFA, account lockout, consent hoặc role mappers, nên bổ sung fixture chuyên biệt. Không mặc định coi Keycloak realm import JSON trên là đầy đủ mọi mapper/role policy sản phẩm.

### 8.3. Kiểm tra import

Sau khi chạy Keycloak, thử mở:

~~~text
http://localhost:18081/realms/it-realm/.well-known/openid-configuration
~~~

Một Discovery document hợp lệ có những field như:

~~~json
{
  "issuer": "http://localhost:18081/realms/it-realm",
  "authorization_endpoint": "http://localhost:18081/realms/it-realm/protocol/openid-connect/auth",
  "token_endpoint": "http://localhost:18081/realms/it-realm/protocol/openid-connect/token",
  "jwks_uri": "http://localhost:18081/realms/it-realm/protocol/openid-connect/certs"
}
~~~

Đây là **minh họa một phần** của JSON trả về, không phải toàn bộ metadata thật. Không hardcode token/JWKS endpoint bằng string suy đoán khi OP hỗ trợ discovery; dùng <code>issuer-uri</code> để framework nạp metadata và kiểm tra values.

## 9. Issuer, Discovery và JWKS: ba điểm phải chính xác

### 9.1. Issuer

Với OIDC, issuer là định danh có tính security. Ví dụ:

~~~text
http://localhost:18081/realms/it-realm
~~~

Spring Security OIDC Client phải xác minh <code>iss</code> trong ID Token khớp issuer đã cấu hình.

Không coi những chuỗi sau là tương đương:

~~~text
http://localhost:18081/realms/it-realm
http://127.0.0.1:18081/realms/it-realm
http://keycloak-it:8080/realms/it-realm
~~~

Dù chúng có thể dẫn đến cùng container trong một vài mạng, chúng là **những issuer URLs khác nhau** theo string comparison.

### 9.2. Discovery

OIDC Discovery thông qua:

~~~text
{issuer}/.well-known/openid-configuration
~~~

Client có thể lấy:

- <code>issuer</code>.
- <code>authorization_endpoint</code>.
- <code>token_endpoint</code>.
- <code>jwks_uri</code>.
- <code>userinfo_endpoint</code>, nếu có.
- Supported response types, grant types, signing algorithms và scopes.

**Không làm tests chỉ assert HTTP 200.** Nếu Discovery <code>issuer</code> không khớp <code>issuer-uri</code>, đó là một lỗi cấu hình cần phát hiện.

### 9.3. JWKS

JWKS chứa **public keys** để Client verify chữ ký JWT do OP phát hành. Không copy private signing key của OP vào Portal.

Trong integration test:

1. OP ký ID Token bằng private key thuộc test realm.
2. Spring Security lấy public key từ JWKS URI đáng tin.
3. Client kiểm tra JWT signature và claims.

Nếu JWKS không truy cập được, không khắc phục bằng cách tắt JWT signature validation. Kiểm tra hostname, DNS, network routing, TLS/truststore, key rotation và cache behavior.

### 9.4. Key rotation

Một kịch bản nâng cao:

~~~text
T0: OP ký bằng kid=K1
T1: OP rotate sang kid=K2
T2: Client gặp ID Token kid=K2
T3: Client refresh/reload JWK Set theo chính sách
T4: Validation vẫn thành công nếu key trust phù hợp
~~~

Test key rotation cần provider hỗ trợ và kiểm soát được key lifecycle. Không biến key rotation test thành “chấp nhận mọi chữ ký” hoặc hardcode một PEM public key vĩnh viễn.

## 10. Spring Boot Client trỏ tới provider test

Trong ứng dụng Portal:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          it-op:
            provider: it-op
            client-id: portal-it
            client-secret: ${TEST_OIDC_CLIENT_SECRET:local-it-client-secret-not-for-production}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          it-op:
            issuer-uri: ${TEST_OIDC_ISSUER_URI:http://localhost:18081/realms/it-realm}
server:
  port: 18080
~~~

Với local browser test:

~~~text
Portal baseUrl:
    http://localhost:18080

OAuth2 initiation:
    http://localhost:18080/oauth2/authorization/it-op

Callback:
    http://localhost:18080/login/oauth2/code/it-op

OIDC issuer:
    http://localhost:18081/realms/it-realm
~~~

**Lưu ý port:** <code>server.port=18080</code> phù hợp cho một local browser test. Khi dùng <code>@SpringBootTest(webEnvironment = RANDOM_PORT)</code> hoặc chạy nhiều CI jobs, callback port sẽ khác; cần cấp redirect URIs phù hợp hoặc dùng test ingress/hostname riêng. Không thay callback thành wildcard rộng trong production để tránh vấn đề này.

### 10.1. Dùng test profile

Nên đặt cấu hình này ở:

~~~text
src/test/resources/application-oidc-it.yml
~~~

và chỉ bật trong integration test hoặc local profile test:

~~~java
@ActiveProfiles("oidc-it")
~~~

Không đưa <code>TEST_OIDC_CLIENT_SECRET</code> hoặc test issuer lên production configuration path. Cần kiểm tra CI/CD không tự import test profile vào production.

### 10.2. Phân biệt provider ID và registration ID

Trong Spring Boot:

~~~yaml
registration:
  it-op:
    provider: it-op
~~~

<code>it-op</code> dưới <code>registration</code> quyết định URL:

~~~text
/oauth2/authorization/it-op
~~~

<code>it-op</code> dưới <code>provider</code> nhóm metadata/issuer configuration. Hai tên có thể khác nếu khai báo đúng mapping, nhưng trong ví dụ dùng giống nhau để dễ theo dõi.

## 11. Cấu hình Servlet SecurityFilterChain tối thiểu

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class TestPortalSecurityConfig {

    @Bean
    SecurityFilterChain portalChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Ví dụ trên dùng mặc định OAuth2 Login flow. Nếu tạo custom login page ở <code>/login</code>, cấu hình lại <code>oauth2Login().loginPage("/login")</code> và cung cấp trang đó. Một GET trực tiếp:

~~~text
http://localhost:18080/oauth2/authorization/it-op
~~~

không nhất thiết cần custom login page.

**Không tắt CSRF cho toàn ứng dụng** để login chạy. Authorization Code callback GET thông thường dùng OAuth2 <code>state</code> correlation; các POST nghiệp vụ dựa trên browser session vẫn cần CSRF protection.

### 11.1. Một test-only principal endpoint

Để quan sát user sau login mà không trả tokens:

~~~java
package example.web;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TestIdentityController {

    @GetMapping("/test/whoami")
    Map<String, String> whoami(
            @AuthenticationPrincipal OidcUser user) {

        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject());
    }
}
~~~

Chỉ bật endpoint này trong **test environment đã cô lập**. Không đưa toàn bộ claims, ID Token, access token hoặc refresh token ra browser. Trong production, dùng authorization/privacy policy phù hợp nếu cần endpoint profile.

### 11.2. Đọc issuer và subject

Sau login Alice, phản hồi khái niệm:

~~~json
{
  "issuer": "http://localhost:18081/realms/it-realm",
  "subject": "11111111-1111-4111-8111-111111111111"
}
~~~

Nếu <code>sub</code> đã được nhập cố định từ realm fixture và Keycloak version tôn trọng ID này, test có thể assert chính xác; tốt hơn vẫn xác minh claims theo OP test state thực tế. Không lấy email làm identity primary key.

## 12. Authorization Code Flow: test với browser, không phải password grant

Đối với OIDC browser login, user agent thực hiện:

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant Portal as Spring Security Portal
    participant OP as Keycloak Test OP
    User->>Browser: GET /test/whoami
    Browser->>Portal: Unauthenticated request
    Portal-->>Browser: Redirect OIDC initiation
    Browser->>Portal: GET /oauth2/authorization/it-op
    Portal->>Portal: Generate state, nonce, PKCE when configured
    Portal-->>Browser: 302 Authorization Endpoint
    Browser->>OP: Authorization request
    User->>OP: Login alice.test
    OP-->>Browser: Redirect code + state
    Browser->>Portal: GET /login/oauth2/code/it-op
    Portal->>OP: POST token request with authorization code
    OP-->>Portal: Access Token + ID Token
    Portal->>Portal: Validate ID Token, create OidcUser/session
    Portal-->>Browser: Redirect to protected URL or target
    Browser->>Portal: GET /test/whoami
    Portal-->>Browser: issuer + subject
~~~

### 12.1. Vì sao không dùng ROPC để “test login”?

Request:

~~~http
POST /token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=password&username=alice.test&password=...
~~~

là **Resource Owner Password Credentials** (password grant), không phải Authorization Code + OIDC browser authentication. Nó bỏ qua redirect, state, nonce, consent UI, browser session và nhiều cơ chế MFA. Bài này cố ý **tắt direct access grants** trong realm fixture.

Nếu chỉ cần test token handling từ một issuer, dùng token fixtures/stub phù hợp và ghi rõ phạm vi. Đừng coi ROPC thành bằng chứng OIDC Client login flow đúng.

### 12.2. PKCE trong integration test

PKCE có:

~~~text
code_verifier
code_challenge = BASE64URL(SHA256(code_verifier))
code_challenge_method = S256
~~~

Nếu ứng dụng sử dụng PKCE, test phải giữ <code>code_verifier</code> của authorization request gốc để token exchange. Không copy authorization code từ browser rồi gửi một verifier khác; OP phải từ chối.

Với confidential Client, cách framework tạo PKCE phụ thuộc cấu hình và Spring Security version; cần kiểm tra authorization request thực tế thay vì mặc định cho rằng mọi registration đều tự bật PKCE như nhau.

### 12.3. Nonce và ID Token

OIDC Client thường đưa <code>nonce</code> vào request theo flow/configuration, rồi xác minh claim <code>nonce</code> trong ID Token nếu dùng. Trong test E2E, không thay ID Token bằng JWT tự tạo thiếu nonce chỉ để login thành công.

## 13. Tài khoản test và dữ liệu fixture nên được quản lý như code

Một cấu trúc ví dụ:

~~~text
src/
  main/
    java/example/...
  test/
    java/example/oidc/
      ProviderSmokeIT.java
      OidcLoginBrowserIT.java
      OidcFailureIT.java
    resources/
      application-oidc-it.yml
      oidc/
        realm-integration.json
compose.oidc-it.yml
~~~

Đây là layout minh họa, không phải yêu cầu phải tạo đúng các file trên trong task hiện tại.

### 13.1. Fixture cần có version

Mỗi thay đổi về:

- Realm name.
- Client ID/secret test.
- Redirect URIs.
- User roles/credentials.
- Protocol mappers.
- Token/session expiration.
- Signing algorithms/key settings.

có thể làm test đổi behavior. Cần review fixture trong cùng pull request thay vì chỉnh manual trên một Keycloak đang chạy rồi quên cập nhật source.

### 13.2. Tạo data độc lập theo scenario

Ví dụ:

~~~text
Test login success          → alice.test
Test switch account         → alice.test, bob.test
Test disabled account       → disabled.test
Test role mapping           → reader.test, admin.test
Test consent denied         → consent.test + explicit consent
Test refresh revoked        → a dedicated account/grant
Test MFA                    → mfa.test + configured authenticator
~~~

Không chia sẻ một user mutable giữa hàng chục parallel tests nếu chúng revoke session, reset password hoặc thay đổi consent của nhau.

### 13.3. Cleanup an toàn

Mỗi test run nên:

1. Start container/realm mới hoặc reset database test.
2. Import fixture.
3. Run tests.
4. Thu logs đã lọc cần thiết khi lỗi.
5. Stop container và xóa dữ liệu test theo CI retention.

Tránh cleanup dựa trên pattern rộng như “delete all realms starting with prod” ở provider dùng chung. Dành endpoint hoặc namespace riêng cho test automation.

## 14. Testcontainers: dựng OP ephemeral trong JUnit

Docker Compose tiện cho developer chạy browser. **Testcontainers** phù hợp JUnit/CI vì mỗi test run có container riêng, port mapping ngẫu nhiên và lifecycle được test framework quản lý.

### 14.1. Gradle dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers'
}
~~~

Version/BOM quản lý dependencies phải phù hợp Spring Boot và Testcontainers được dự án pin. Nếu không dùng BOM, khai báo version theo dependency management của build; không thả dependency floating trên CI.

### 14.2. Ví dụ provider smoke test

~~~java
package example.oidc;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class ProviderSmokeIT {

    @Container
    static final GenericContainer<?> keycloak =
        new GenericContainer<>(
            DockerImageName.parse(
                "quay.io/keycloak/keycloak:26.0.0"))
            .withExposedPorts(8080)
            .withEnv("KC_HTTP_ENABLED", "true")
            .withEnv("KC_HOSTNAME_STRICT", "false")
            .withCopyFileToContainer(
                MountableFile.forClasspathResource(
                    "oidc/realm-integration.json"),
                "/opt/keycloak/data/import/realm-integration.json")
            .withCommand("start-dev", "--import-realm")
            .waitingFor(
                Wait.forHttp(
                    "/realms/it-realm/.well-known/openid-configuration")
                    .forPort(8080)
                    .forStatusCode(200)
                    .withStartupTimeout(Duration.ofMinutes(3)));

    @Test
    void oidcDiscoveryIsReachable() throws Exception {
        String base = "http://" + keycloak.getHost() + ":"
            + keycloak.getMappedPort(8080);

        String url = base
            + "/realms/it-realm/.well-known/openid-configuration";

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(url))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains(
            "\"authorization_endpoint\""));
        assertTrue(response.body().contains(
            "\"token_endpoint\""));
        assertTrue(response.body().contains("\"jwks_uri\""));
    }
}
~~~

**Phạm vi test này chỉ là smoke test Discovery.** Không có browser login, authorization code, token exchange hoặc ID Token validation. Đoạn sample sử dụng Java 17 <code>HttpClient</code> thông thường; khi dùng Java version mới hơn, vòng đời HTTP client có thể có API quản lý tài nguyên khác. Đối với smoke test thực tế, nên kiểm tra JSON metadata bằng parser và assert **giá trị <code>issuer</code> chính xác**, thay vì dùng <code>String.contains</code> như ví dụ rút gọn. Code trình bày hai phần quan trọng: container lifecycle và discovery verification.

### 14.3. Rủi ro issuer khi container chạy random mapped port

Keycloak bên trong nghe tại:

~~~text
http://container:8080
~~~

nhưng JVM truy cập qua:

~~~text
http://localhost:49152
~~~

Nếu Discovery trả:

~~~text
issuer=http://container:8080/realms/it-realm
~~~

trong khi Portal cấu hình:

~~~text
issuer-uri=http://localhost:49152/realms/it-realm
~~~

thì strict issuer validation có thể thất bại. **Không tắt issuer check để test chạy.**

Giải pháp:

1. Cấu hình Keycloak hostname/public URL để Discovery và token <code>iss</code> trùng URL mà JVM/Portal dùng.
2. Dùng test proxy/hostname nhất quán nếu Client chạy trong Docker network.
3. Đọc Discovery <code>issuer</code> thực tế và assert bằng exact expected issuer.
4. Giữ redirect URI browser tách biệt với issuer của provider.

Các biến hostname/proxy của Keycloak có thể thay đổi theo version. Đừng copy hướng dẫn cũ cho một Keycloak mới rồi tự tin rằng metadata luôn đúng.

### 14.4. Tách smoke test và full login

Trong CI, có thể chạy:

~~~text
ProviderSmokeIT
    → container starts
    → realm exists
    → Discovery metadata valid
    → JWKS accessible
    → issuer matches expected
~~~

và riêng:

~~~text
OidcBrowserLoginIT
    → Portal + OP started
    → redirect URI registered
    → browser logs in test user
    → callback verified
    → authenticated session
~~~

Tránh đặt tên một smoke test là <code>OidcFullLoginIT</code> khi nó chưa đi qua authorization code callback.

## 15. @DynamicPropertySource để cung cấp issuer-uri

Khi container dùng random host port, <code>@DynamicPropertySource</code> cho phép Spring test context lấy issuer động.

~~~java
package example.oidc;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("oidc-it")
@Testcontainers
class OidcSpringContextIT {

    // Container declaration tương tự ProviderSmokeIT,
    // hoặc dùng base fixture được tổ chức hợp lý cho suite.
    static GenericContainer<?> keycloak = createTestKeycloak();

    static {
        keycloak.start();
    }

    @DynamicPropertySource
    static void registerProvider(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.security.oauth2.client.provider.it-op.issuer-uri",
            () -> "http://" + keycloak.getHost() + ":"
                + keycloak.getMappedPort(8080)
                + "/realms/it-realm");
    }

    @Test
    void springContextLoadsWithTestProvider() {
        // Chỉ kiểm tra wiring + metadata được resolve.
    }
}
~~~

Đây là **pseudocode lớp test minh họa**, không phải class copy-paste hoàn chỉnh: method <code>createTestKeycloak()</code> cần được định nghĩa bằng container config ở mục trước; cần import <code>GenericContainer</code>. Có thể chọn một trong hai lifecycle styles:

- <code>@Testcontainers</code> + <code>@Container</code> do JUnit extension quản lý.
- Start static container trong shared fixture, rồi dừng/cleanup bằng lifecycle được kiểm soát.

Không vừa start static thủ công vừa để JUnit extension start/stop cùng container không theo chủ đích. <code>@DynamicPropertySource</code> phải trả issuer của **container đã start**, và Spring test context cần dùng đúng test profile.

### 15.1. Cảnh báo test context cache

Spring TestContext có thể cache ApplicationContext giữa nhiều test classes. Nếu một context cache trỏ tới issuer random-port của container đã stop, những test chạy sau có thể lỗi khó hiểu.

Các lựa chọn:

- Dùng container dùng chung có lifecycle bao trùm những contexts tái sử dụng.
- Phân vùng context theo dynamic properties/test class phù hợp.
- Dùng <code>@DirtiesContext</code> khi cần tránh cache sai, cân nhắc hiệu năng.
- Không dùng static mutable issuer variable để các suites song song ghi đè.

### 15.2. Dynamic issuer khác dynamic redirect URI

<code>issuer-uri</code> là URL của OP. <code>redirect-uri</code> là callback URL của Portal. Dù cả hai có thể dùng random ports, cách cung cấp chúng khác nhau.

Nếu Portal chạy <code>@SpringBootTest(RANDOM_PORT)</code>, cần đăng ký callback với OP cho **port thực**. Không chọn wildcard redirect URI rộng để tránh việc provision client đúng trong test.

## 16. Browser E2E: thiết lập callback URI đúng

Với local flow ở các mục trước:

~~~text
Portal: http://localhost:18080
OP:     http://localhost:18081
~~~

Client redirect URI tại OP:

~~~text
http://localhost:18080/login/oauth2/code/it-op
~~~

Ứng dụng phải dùng registration với:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

và thực sự được browser truy cập qua <code>http://localhost:18080</code>, không phải <code>http://127.0.0.1:18080</code> nếu OP chỉ đăng ký localhost. Với OIDC, các URLs cần khớp chính xác theo registration/OP validation.

### 16.1. Vì sao không dùng localhost ở một phía và tên Docker service ở phía kia?

Nếu Portal ở host JVM:

~~~text
http://localhost:18081
~~~

có thể là Keycloak qua published port.

Nếu Portal cũng nằm trong Docker network:

~~~text
http://keycloak-it:8080
~~~

có thể trỏ tới cùng container, nhưng browser ngoài Docker **không nhất thiết resolve** được <code>keycloak-it</code>. OP redirects/JWT <code>iss</code> cũng phải dùng URL nhất quán.

Do đó, full browser test cần thiết kế một hostname/public URL **được cả browser và Client backend truy cập đúng**, đồng thời OP công bố issuer tương ứng.

### 16.2. Hostnames và TLS

HTTP local là một ngoại lệ test trong môi trường cô lập. Với HTTPS integration test:

- Tạo CA/certificate test và cấu hình truststore cho JVM/browser.
- Đảm bảo issuer, discovery endpoints và callback đúng <code>https</code>.
- Không tắt certificate verification toàn JVM để test chạy.
- Không bật trust-all client TLS trong code có thể lọt production.

## 17. Browser automation đăng nhập tài khoản test

Playwright hoặc Selenium có thể điều khiển browser thật:

~~~text
1. Mở http://localhost:18080/test/whoami.
2. Portal đưa tới OIDC initiation/provider login.
3. Điền alice.test và password test tại OP.
4. Submit login.
5. Browser nhận callback code + state.
6. Portal tạo session.
7. Browser tới /test/whoami.
8. Kiểm tra issuer/sub của Alice.
~~~

### 17.1. Ví dụ Playwright Java dạng skeleton

~~~java
import com.microsoft.playwright.*;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class OidcBrowserLoginIT {

    @Test
    void aliceCanLogInThroughTestProvider() {
        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch(
                new BrowserType.LaunchOptions().setHeadless(true));

            BrowserContext context = browser.newContext();
            Page page = context.newPage();

            page.navigate(
                "http://localhost:18080/oauth2/authorization/it-op");

            // Thực tế dùng Page Object/locators theo DOM của
            // Keycloak version đã pin hoặc test-id do test theme cung cấp.
            page.locator("#username").fill("alice.test");
            page.locator("#password").fill(
                "local-only-alice-password");
            page.locator("#kc-login").click();

            page.waitForURL(url ->
                url.contains("localhost:18080"));

            page.navigate("http://localhost:18080/test/whoami");

            String body = page.locator("body").innerText();
            assertTrue(body.contains(
                "11111111-1111-4111-8111-111111111111"));

            context.close();
            browser.close();
        }
    }
}
~~~

Đây là **skeleton test flow**, không phải bộ E2E chạy độc lập: phải có Portal + Keycloak được start, Playwright test dependency và browser binary, test fixtures, callback URI đúng, cũng như locators khớp trang login của OP version đã chọn.

Playwright Java là dependency lựa chọn thêm cho E2E tests; không dùng cho MockMvc-only tests nếu không cần browser. UI của Keycloak có thể đổi giữa versions, vì vậy nên gom locators vào Page Object hoặc dùng theme/test IDs ổn định.

### 17.2. Browser context isolation

Mỗi test nên có <code>BrowserContext</code> mới:

~~~text
Test Alice → context A → SSO/session cookies A
Test Bob   → context B → SSO/session cookies B
~~~

Không dùng chung browser profile có OP SSO cookie từ test trước. Nếu muốn kiểm thử switch-account/SSO reuse, đó phải là **một scenario có chủ đích** và dùng cùng context trong scenario đó.

### 17.3. Không log password hoặc full callback URL

Browser automation có thể ghi screenshots, HAR và traces. Callback URLs có <code>code</code>/<code>state</code> là dữ liệu nhạy cảm. Cần lọc artifact, giới hạn retention/access và không đẩy credentials vào CI logs.

## 18. Test accounts: các positive scenarios cơ bản

### 18.1. Alice đăng nhập thành công

Given:

~~~text
alice.test: enabled, emailVerified=true
client: portal-it
scope: openid profile email
~~~

When:

~~~text
Browser starts /oauth2/authorization/it-op
User authenticates Alice at OP
Callback completes
~~~

Then:

~~~text
Authentication is OAuth2AuthenticationToken
Principal is OidcUser
getSubject() matches Alice test subject
issuer matches registered OP issuer
Authorized Client registrationId = it-op
Portal session authenticated
~~~

Không assert access token bằng toàn bộ JWT string hoặc lưu nó trong test reports. Token có <code>iat</code>/<code>exp</code> và chữ ký động; test semantic claims và intended audience/scope.

### 18.2. Bob đăng nhập trong context khác

Given:

~~~text
Bob: different subject
New isolated browser context
~~~

Then:

~~~text
Bob session != Alice session
Bob subject != Alice subject
No cross-user authorized client
No cached profile from Alice
~~~

### 18.3. Kiểm tra redirect sau login

User chưa đăng nhập mở:

~~~text
/reports/quarterly?year=2026
~~~

Sau login thành công, <code>SavedRequestAwareAuthenticationSuccessHandler</code> có thể đưa user về original URL. Cần xác minh URL/query và authorization của principal mới.

Không chỉ assert <code>302</code> rồi coi redirect policy đã đúng; phải kiểm tra <code>Location</code> hoặc browser URL thực.

## 19. Negative scenarios dành cho provider test

| Scenario | Cách dựng | Kỳ vọng |
|---|---|---|
| Sai mật khẩu | User nhập password không đúng | OP từ chối; Portal không có authenticated session |
| User disabled | Dùng <code>disabled.test</code> | OP không cấp login thành công |
| User deny consent | Realm/client yêu cầu consent; user từ chối | Callback chứa OAuth2 error khi profile hỗ trợ; failure handler |
| Sai redirect_uri | Registration client không chứa callback URI | OP từ chối authorization request |
| Sai client secret | Portal gửi secret không khớp test client | Token Endpoint <code>invalid_client</code> |
| Code reused | Gửi authorization code đã tiêu thụ | Token Endpoint từ chối, thường <code>invalid_grant</code> |
| Callback state mismatch | Đổi state callback hoặc mất repository | Spring Security từ chối login |
| ID Token issuer sai | Token fixture/JWKS trust setup không phù hợp | OIDC validation fail |
| ID Token audience sai | Token phát cho Client ID khác | OIDC validation fail |
| ID Token expired | Fault injection bằng token fixture có <code>exp</code> cũ | OIDC validation fail |
| JWK key unavailable | Tắt JWKS endpoint hoặc đổi key cache | Test phản ứng failure, không disable verification |
| OP unavailable | Stop container/network fault | Portal phản hồi an toàn, không login loop |
| UserInfo lỗi | Stub/UserInfo policy từ chối | OIDC integration error handling |

**Không nên dùng một OP thật duy nhất để cố tạo mọi malformed JWT bằng cách chỉnh sửa database sống.** Một số negative cases như signature sai, nonce mismatch hay token body malformed thường dễ kiểm soát bằng **HTTP token-response stub + test signing keys**; dùng Keycloak cho các luồng behavior bình thường và những lỗi OP có thể cấu hình đáng tin cậy.

### 19.1. Client secret mismatch

Nếu Portal dùng:

~~~text
client-secret=WRONG-TEST-SECRET
~~~

còn Keycloak client có:

~~~text
secret=local-it-client-secret-not-for-production
~~~

Token request bằng <code>client_secret_basic</code> phải bị từ chối theo client authentication policy.

Trong browser, user có thể login thành công ở OP nhưng Portal thất bại khi đổi code. Đây **không phải** lỗi “user nhập sai password”.

### 19.2. State mismatch

Một callback code hợp lệ nhưng <code>state</code> sai phải bị từ chối. Không khắc phục bằng cách:

~~~java
// KHÔNG làm điều này:
skipStateValidation = true;
~~~

Test cần giữ phân biệt:

- Authorization request đã tạo nhưng state sai.
- Authorization request không tồn tại do khác session hoặc hết hạn.

Hai trường hợp đều không được cấp authenticated session, nhưng root cause khác.

### 19.3. Consent denied

Realm fixture cơ sở chưa bật consent-required flow. Muốn test user deny consent, cần **cấu hình consent tại test client/OP phù hợp** và xác minh OP thật hiển thị màn hình consent. Không mặc định “mọi login có OIDC scope đều hiện consent”.

## 20. UserInfo, roles và claims

Một OIDC Client có thể dùng ID Token và gọi UserInfo Endpoint tùy scopes/provider configuration.

### 20.1. Email claim

Kỳ vọng:

~~~text
email = alice@example.test
email_verified = true
~~~

chỉ khi provider thực sự phát các claims đó trong token/UserInfo theo scopes và protocol mappers.

Không kết luận một client cấu hình <code>scope=email</code> thì ID Token luôn có email claim; provider có thể để email ở UserInfo hoặc áp dụng policy khác.

### 20.2. Role mapping

Keycloak có thể dùng realm/client roles; nhưng Spring Security OAuth2/OIDC Client không tự chuyển mọi role JSON thành <code>ROLE_ADMIN</code> theo mọi cấu hình.

Nếu cần test:

~~~text
admin.test → ROLE_ADMIN
alice.test → ROLE_READER
~~~

hãy cấu hình:

1. Role assignments trong realm fixture.
2. Protocol mapper đưa roles tới đúng token/UserInfo nếu policy muốn.
3. <code>OidcUserService</code> / granted-authorities mapper của ứng dụng.
4. Assertions trên <code>Authentication.getAuthorities()</code>.

**Không tự cho quyền dựa trên email kết thúc bằng <code>@example.test</code>**; đó không phải OIDC authorization proof.

### 20.3. Multi-provider

Nếu test cả Company và Partner:

~~~text
issuer A: /realms/it-company
issuer B: /realms/it-partner
~~~

Tạo **hai ClientRegistrations**, mỗi registration có issuer/client ID/secret/redirect URI tương ứng. Không dùng một issuer cho cả hai chỉ vì user email trùng.

## 21. Refresh token và rotation tests

Không phải mọi OIDC login đều cấp refresh token theo cùng một policy; cần hiểu provider config/scopes, offline access và session policy.

### 21.1. Access token expiry

Trong test realm, có thể giảm access-token lifetime để thử:

~~~text
Login Alice
Wait until access token near expiry
AuthorizedClientManager refreshes
Token Endpoint returns new access token
Token stored for Alice/registrationId
~~~

Đừng dùng <code>Thread.sleep(5 minutes)</code> trong mỗi test nếu có cách điều khiển clock hoặc token fixture; test suite sẽ chậm và dễ flaky.

### 21.2. Refresh rotation

Nếu provider test hỗ trợ refresh-token rotation, bật trong một fixture riêng:

~~~text
Initial: access A0, refresh R0
Refresh: access A1, refresh R1
Old R0 reused: rejected according to OP policy
~~~

Trong cluster:

~~~text
Node A and B load R0
Node A refreshes R0 → R1
Node B refreshes R0 → invalid_grant
~~~

**Shared JDBC/Redis token store không tự ngăn race.** Cần test single-flight/locking/versioned conditional delete để Node B không xóa R1 do Node A vừa lưu.

### 21.3. Revoke/grant invalidation

Tạo một dedicated test account/session rồi revoke grant tại OP qua Admin API/test fixture hoặc theo capability provider. Đừng revoke shared test user Alice khi các tests khác đang dùng.

## 22. Logout tests: local, RP-Initiated và back-channel

OIDC có nhiều loại logout, phụ thuộc provider capability.

| Loại | Điểm bắt đầu | Test trọng tâm |
|---|---|---|
| Local logout | Portal session | SecurityContext/session invalidated; POST + CSRF |
| RP-Initiated Logout | Portal → OP <code>end_session_endpoint</code> | Redirect OP, <code>id_token_hint</code>, post-logout URI hợp lệ |
| Front-Channel Logout | OP → browser → RP | Browser cookies, iframe/session mapping theo profile |
| Back-Channel Logout | OP server → RP server | Signed Logout Token, issuer/audience/sid/sub/session registry |

### 22.1. Local logout không xóa OP SSO session

Sau:

~~~text
POST /logout
~~~

Portal session có thể mất nhưng browser còn OP cookie. Khi vào:

~~~text
/oauth2/authorization/it-op
~~~

OP có thể SSO user Alice trở lại ngay. **Đây không nhất thiết là lỗi local logout.**

### 22.2. RP-Initiated Logout

Nếu Keycloak/test OP cung cấp <code>end_session_endpoint</code>, có thể kiểm thử <code>OidcClientInitiatedLogoutSuccessHandler</code> hoặc reactive counterpart theo stack.

Phải đăng ký/allowlist <code>post_logout_redirect_uri</code> đúng policy. Không redirect người dùng đến một URL tùy ý do browser gửi.

### 22.3. Back-Channel Logout

Nếu dùng Spring Security feature hỗ trợ:

~~~java
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
~~~

đây là cấu hình tham khảo cho **phiên bản có DSL Back-Channel Logout**; cần kiểm tra version và SecurityFilterChain integration.

Test phải chứng minh:

- OP gửi **signed Logout Token**.
- Spring Security xác minh <code>iss</code>, <code>aud</code>, <code>events</code>, chữ ký và các claims theo profile.
- <code>sid/sub</code> match session registry.
- Session chính xác bị kết thúc.

Không kiểm thử back-channel bằng cách tự POST <code>sub=alice</code> chưa ký rồi mong Portal logout.

## 23. Môi trường CI và khả năng chạy song song

### 23.1. Docker requirements

Testcontainers thường yêu cầu Docker-compatible runtime. Trên developer/CI:

~~~text
Docker engine reachable
Container image accessible or mirrored
Sufficient RAM/CPU
Network/DNS predictable
Ports available (for local Compose)
Browser runtime installed (for E2E)
~~~

Đừng coi mọi CI runner đều có Docker hoặc được quyền kéo image từ Internet. Nếu tổ chức dùng registry mirror/private artifact repository, pin image digest và cấu hình mirror phù hợp.

### 23.2. Không phụ thuộc shared public sandbox

Một provider sandbox chung có thể gặp:

- Nhiều CI runs dùng cùng test account.
- Password bị đổi bởi test khác.
- Session/consent state còn sót.
- Rate limiting.
- Provider deploy giữa test.
- Mất mạng hoặc không cho callback từ CI runner.

Ưu tiên ephemeral containers cho routine integration tests; chỉ dùng shared provider sandbox cho compatibility tests có isolation và ownership rõ.

### 23.3. Parallel tests

Các chiến lược:

1. Container riêng per test class/suite khi resource cho phép.
2. Realm/client/user namespace riêng per parallel job.
3. Random mapped host port cho Testcontainers; test provider issuer phải phản ánh port đúng.
4. Một browser context riêng per user test.
5. Không mutate shared test account.
6. Cleanup theo run ID/namespace, tránh thao tác phá các runs khác.

### 23.4. Test result không nên phụ thuộc thứ tự

Không thiết kế:

~~~text
test1 creates Alice
test2 logs in Alice
test3 disables Alice
test4 expects Alice still enabled
~~~

Mỗi test cần fixture độc lập hoặc setup/reset rõ ràng.

## 24. Security của test provider

Dù không phải production, OP test vẫn chứa credentials và có thể cấp tokens dùng được cho test APIs.

### 24.1. Không dùng production secrets

Tuyệt đối không import:

~~~text
PRODUCTION_CLIENT_SECRET
PRODUCTION_REFRESH_TOKEN
PRODUCTION_SIGNING_PRIVATE_KEY
CUSTOMER_PASSWORD
~~~

vào test environment hoặc logs.

### 24.2. Không expose OP test rộng

Local Compose bind <code>127.0.0.1</code>. Trong CI, giới hạn container network/ingress và tránh public endpoints nếu không cần.

Nếu phải chạy cloud E2E browser và Portal/OP ở hosts khác, yêu cầu:

- TLS đúng.
- Firewall/access control.
- Test-only issuer/client/users.
- Secret store.
- Logging/redaction.
- Lifecycle cleanup.

### 24.3. Không gửi email/SMS thật

User <code>alice@example.test</code> chỉ dùng cho claims test. Tắt SMTP hoặc dùng mail sink giả như MailHog/Mailpit trong môi trường cô lập nếu test email verification/password reset.

### 24.4. Test admin accounts

Admin API user có quyền cấu hình realm. Không dùng admin credentials trong browser login tests thông thường, không in vào CI output, không tái sử dụng cho production.

### 24.5. Test artifacts và GDPR/privacy

Browser screenshots/HAR có thể chứa email claims, session IDs, authorization codes hoặc cookies. Với account giả, rủi ro nhỏ hơn nhưng không phải bằng không.

Chỉ lưu artifacts cần thiết, redact headers/URL parameters nhạy cảm và giới hạn retention.

## 25. Kiểm thử lỗi có kiểm soát: OP thật và stub bổ sung

Một OP thật như Keycloak rất phù hợp positive flows, nhưng không phải mọi lỗi đều dễ tạo bằng UI.

### 25.1. Dùng HTTP stub cho malformed response

Khi cần test:

- Token Endpoint trả JSON thiếu <code>access_token</code>.
- ID Token có chữ ký sai.
- JWKS có key ID không khớp.
- HTTP 429/503.
- UserInfo trả unexpected content type.
- Token response chứa unknown provider error code.

có thể dựng một **test OP stub** với Discovery/JWKS/Token Endpoints nhất quán, hoặc fault injection proxy chuyên biệt. Không nhất thiết thay đổi Keycloak global config để tạo từng lỗi.

### 25.2. Không trả JWT bất kỳ rồi tin Spring Security chấp nhận

Một ID Token hợp lệ cần:

~~~text
Signature verifiable with trusted JWKS
iss = configured issuer
aud contains expected client_id
exp > now within configured clock policy
iat appropriate
sub present and valid
nonce matches authorization request, when required
~~~

Nếu muốn test chữ ký sai, bắt đầu từ một flow có token hợp lệ rồi cố ý tạo sai signature trong fixture. Assertion mong đợi là **login bị từ chối**, không phải framework chấp nhận.

### 25.3. Error simulation theo tầng

| Tầng | Tool/fixture | Điều nên assert |
|---|---|---|
| Authorization Endpoint | Keycloak UI/policy | User login/consent, redirect + state |
| Token Endpoint | Keycloak hoặc stub | Code exchange/invalid_client/invalid_grant |
| JWKS/ID Token | Test keys, controlled issuer | Signature/issuer/audience/nonce validation |
| UserInfo | Provider/stub | Claims đúng/sai và mapping |
| Resource Server | Fake API | Bearer audience/scope, HTTP 401/403 |
| Local session | MockMvc/browser | SecurityContext/session/cookie |
| Logout | OP feature/fault injection | Correct session termination |

## 26. Troubleshooting: lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng chẩn đoán |
|---|---|---|
| OP trả 404 tại Discovery | Realm chưa import, path sai | Kiểm tra realm name và logs import |
| Discovery trả 200 nhưng issuer sai | Keycloak hostname/proxy config | So sánh <code>issuer</code> chính xác |
| Redirect browser tới <code>keycloak-it:8080</code> nhưng không truy cập được | Docker service hostname chỉ có trong network | Thiết kế public browser-reachable hostname |
| <code>redirect_uri_mismatch</code> | Portal port/host/path không trùng registration | So sánh exact callback |
| <code>invalid_client</code> | Client secret/auth method sai | Kiểm tra test client và registration |
| <code>unauthorized_client</code> | Standard Flow tắt hoặc policy không cho phép | Kiểm tra OP client settings |
| <code>invalid_scope</code> | Scope client chưa được phép | Kiểm tra scopes, client scopes/mappers |
| User login xong quay về login ngay | SecurityContext/session cookie không được giữ | Kiểm tra cookie, session, filter chain |
| Callback <code>authorization_request_not_found</code> | State repo/session/cookie thất lạc | Kiểm tra HTTP session/SameSite/proxy |
| Callback state mismatch | Sai session, concurrent flow hoặc state bị thay | Không bỏ state validation |
| <code>invalid_grant</code> tại Token Endpoint | Code expired/reused, redirect URI/PKCE mismatch | Kiểm tra correlation, token request |
| ID Token issuer mismatch | Hostname, realm, issuer-uri khác nhau | Exact issuer, discovery, token claims |
| ID Token signature invalid | JWKS/key/cache sai | Kiểm tra public key và <code>kid</code> |
| Browser báo insecure cookie | HTTP/HTTPS/SameSite/Secure config sai | Điều chỉnh test origin/HTTPS |
| Browser test tự động vào Alice thay vì Bob | OP SSO cookie còn | New browser context hoặc account chooser |
| <code>oidcLogin()</code> test xanh nhưng E2E fail | Mock không chạy protocol | Thêm OP + browser integration |
| Test fails only in CI | Docker/network/port/clock/resources | Check runtime constraints & retries |
| Parallel tests flaky | Shared mutable realm/users/session | Isolate realm/container/user |
| Token refresh tests flaky | TTL/sleep/rotation race | Clock/test token lifetime/coordination |
| Login OP được nhưng API 403 | Scope/audience/role mapping | Kiểm tra access token và Resource Server |

### 26.1. Các bước điều tra cụ thể

~~~text
Test failure
   |
   +-- Provider container đã ready?
   |       |
   |       +-- Không → image, startup logs, realm import, healthcheck
   |       |
   |       +-- Có → Discovery issuer đúng?
   |                    |
   |                    +-- Không → hostname, proxy, mapped port
   |                    |
   |                    +-- Có → ClientRegistration/callback đúng?
   |                                 |
   |                                 +-- Không → client ID, secret, URI
   |                                 |
   |                                 +-- Có → Authorization request state?
   |                                              |
   |                                              +-- Mất → session/cookie
   |                                              |
   |                                              +-- Có → code/token exchange?
   |                                                           |
   |                                                           +-- Lỗi → PKCE/client credentials
   |                                                           |
   |                                                           +-- OK → ID Token validation,
   |                                                                      SecurityContext/redirect
~~~

### 26.2. Log gì để debug an toàn?

Ví dụ:

~~~text
testRunId=it-2026-11-run42
providerAlias=it-op
realm=it-realm
discoveryStatus=200
issuerMatch=true
loginStage=token_exchange
oauth2ErrorCategory=invalid_grant
correlationId=sample
~~~

Không log:

~~~text
client_secret
admin_password
user_password
authorization_code
code_verifier
state / nonce thật
id_token / access_token / refresh_token
session cookie
~~~

Không dùng raw authorization callback URL làm log label hoặc CI artifact công khai.

## 27. Danh sách integration scenarios cần có

| ID | Scenario | Loại kiểm thử | Đầu ra quan trọng |
|---|---|---|---|
| IT-01 | Realm/Discovery sẵn sàng | Testcontainers smoke | Metadata, exact issuer |
| IT-02 | JWKS endpoint reachable | Testcontainers smoke | JWK set phù hợp |
| IT-03 | Alice authorization-code login | Browser E2E | OIDC principal đúng iss/sub |
| IT-04 | Bob login isolated context | Browser E2E | Subject/session khác Alice |
| IT-05 | Protected URL saved request | Browser/MockMvc | Redirect an toàn sau login |
| IT-06 | Invalid password | Browser E2E | Không tạo session |
| IT-07 | Disabled user | Browser E2E | OP từ chối |
| IT-08 | Deny consent | Provider-specific E2E | Failure handler |
| IT-09 | Wrong client secret | Token integration | invalid_client |
| IT-10 | Wrong redirect URI | Provider integration | OP từ chối |
| IT-11 | Callback state mismatch | OIDC callback integration | Fail closed |
| IT-12 | Wrong ID Token issuer/audience | JWT fixture | Fail closed |
| IT-13 | Bad JWT signature/key | JWT fixture | Fail closed |
| IT-14 | UserInfo unavailable | Stub/provider | Error handling |
| IT-15 | Refresh success | Token integration | Token state updated đúng principal |
| IT-16 | Refresh invalid_grant | OP/stub | Cleanup/reauthorize theo policy |
| IT-17 | Refresh rotation race | Multi-node fixture | Không xóa token mới |
| IT-18 | Local POST logout | Browser/MockMvc | Session invalidated + CSRF |
| IT-19 | RP-Initiated Logout | Provider-specific E2E | OP SSO behavior |
| IT-20 | Back-Channel Logout | OIDC feature integration | Logout Token verified, session mapped |
| IT-21 | Two providers, same email | Multi-realm E2E | Không link nhầm identity |
| IT-22 | Cluster callback across nodes | Multi-instance integration | Shared session/state |
| IT-23 | Token audience/scope mismatch | Resource Server integration | 401/403 đúng |
| IT-24 | OP temporarily unavailable | Fault injection | Safe failure/retry bounded |

Không cần chạy tất cả scenarios mỗi pull request nếu chi phí cao: có thể chia fast integration suite và nightly compatibility suite. Nhưng **không loại bỏ các security-critical assertions** khỏi những test được chọn.

## 28. Những sai lầm thường gặp khi dựng OP test

### 28.1. Dùng tài khoản production để “giống thật”

Sai vì rò rỉ credentials, dữ liệu cá nhân và có thể gây side effect. Dùng accounts giả và sandbox tách biệt.

### 28.2. Hardcode secrets trong application production profile

Một secret fixture chỉ có thể tồn tại trong test config bị giới hạn. Không dùng cùng secret trong sản phẩm thật.

### 28.3. Chỉ mock OidcUser rồi gọi đó là integration test OIDC

Mock principal không chạy Discovery, Token Endpoint hay ID Token signature verification. Dùng đúng nhãn test.

### 28.4. Bỏ issuer validation để tránh lỗi Docker hostname

Không chấp nhận. Phải sửa public hostname/issuer của provider test.

### 28.5. Wildcard redirect URI quá rộng

Một callback wildcard rộng khiến code có nguy cơ đi tới host/path không mong muốn. Dùng exact URI và cơ chế provision client động nếu test port động.

### 28.6. Dùng password grant để test browser login

ROPC không phản ánh Authorization Code/OIDC flow, không test state, consent, SSO cookie, callback hoặc PKCE đúng cách.

### 28.7. Reuse browser context giữa accounts

OP SSO cookie có thể tự đăng nhập lại Alice khiến test Bob fail hoặc pass sai. Isolate context; chỉ reuse trong scenario SSO/switch cụ thể.

### 28.8. Dùng shared user mutable trong parallel tests

Test revoke/disable/update consent có thể ảnh hưởng test khác. Cô lập account hoặc realm.

### 28.9. In token vào log để debug

Không in JWT/authorization code/refresh token vào CI logs. Chỉ log metadata đã lọc và correlation IDs.

### 28.10. Test một OP rồi khẳng định tương thích mọi providers

Keycloak chỉ đại diện cho behavior của Keycloak version/fixture đã chọn. Production OP khác có thể có khác biệt ở consent, account chooser, UserInfo, logout, refresh rotation và token claims.

## 29. Bài tập thực hành

### Bài 1 — Unit test hay integration test?

Một test gọi:

~~~java
mockMvc.perform(get("/private").with(oidcLogin()));
~~~

**Câu hỏi:** Có kiểm tra issuer discovery và ID Token signature không?

**Đáp án:** Không. Đây là test với mock principal, thích hợp cho controller/security authorization, không chạy authorization-code flow.

### Bài 2 — Realm fixture

**Yêu cầu:** Tạo realm <code>it-realm</code>, Client ID <code>portal-it</code>, test user Alice/Bob và exact callback URI.

**Đáp án gợi ý:** Viết JSON realm import tại <code>src/test/resources/oidc/realm-integration.json</code>; tránh click tay mỗi lần CI chạy.

### Bài 3 — Issuer mismatch

Discovery trả:

~~~text
http://localhost:49152/realms/it-realm
~~~

App cấu hình:

~~~text
http://keycloak-it:8080/realms/it-realm
~~~

**Đáp án:** Hai issuer strings khác nhau. Sửa hostname/public URL để Client config, Discovery và ID Token <code>iss</code> nhất quán. Không disable validation.

### Bài 4 — Redirect URI

OP chỉ cho:

~~~text
http://localhost:18080/login/oauth2/code/it-op
~~~

Browser chạy Portal bằng:

~~~text
http://127.0.0.1:18080
~~~

**Đáp án:** Redirect URI có thể không khớp vì hostname khác. Dùng exact registered URI hoặc provision client test theo origin thực.

### Bài 5 — Wrong client secret

OP trả <code>invalid_client</code> khi đổi code.

**Đáp án:** Kiểm tra Client ID, secret và client authentication method. Không coi đó là lỗi user password.

### Bài 6 — Disabled user

**Yêu cầu:** Login bằng <code>disabled.test</code>.

**Đáp án:** OP phải không cấp authenticated login bình thường; Portal không được tạo <code>OidcUser</code> từ claims chưa xác minh.

### Bài 7 — Test switch account

Alice đã login, sau đó muốn chọn Bob trong cùng browser.

**Đáp án:** Local logout không tự xóa OP SSO cookie; dùng account-selection/reauth profile provider hỗ trợ hoặc browser context mới tùy mục tiêu test.

### Bài 8 — Password grant

**Câu hỏi:** Tại sao <code>grant_type=password</code> không phải test đầy đủ Spring Security OIDC Login?

**Đáp án:** Nó bỏ qua browser authorization redirect, state, nonce, PKCE, consent UI và SSO flow.

### Bài 9 — Callback state mismatch

**Đáp án:** Login phải thất bại, không tạo authenticated session; không tắt state validation để test pass.

### Bài 10 — JWKS bị unavailable

**Đáp án:** Kiểm tra network/cert/key URI/JWK cache; không cho qua ID Token signature validation khi JWKS lỗi.

### Bài 11 — Refresh rotation

Node A dùng R0 thành công rồi lưu R1, Node B dùng R0 nhận invalid_grant.

**Đáp án:** Cần concurrency handling/versioned cleanup để B không xóa R1.

### Bài 12 — Shared CI account

Hai test suites cùng disable Alice.

**Đáp án:** Tests không độc lập. Cần realm/account riêng hoặc reset tuần tự theo ownership.

### Bài 13 — Local logout vs OP logout

**Câu hỏi:** Sau POST /logout, OP vẫn SSO vào Alice, có chắc bug không?

**Đáp án:** Không. Local session logout khác RP-Initiated Logout/OP SSO logout.

### Bài 14 — Role mapping

OP trả Keycloak realm role nhưng Portal không có <code>ROLE_ADMIN</code>.

**Đáp án:** Phải cấu hình protocol mapper/claims và authorities mapping phía Spring Security. Không tự coi mọi realm role là Spring GrantedAuthority.

### Bài 15 — E2E artifacts

Browser traces chứa callback URLs và cookies.

**Đáp án:** Redact secrets, giới hạn access/retention; không upload raw artifacts lên public CI report.

### Bài 16 — Full integration workflow

Thực hiện theo thứ tự:

1. Tạo realm fixture test-only với Client ID, exact callback và users Alice/Bob.
2. Khởi chạy Keycloak local qua Docker Compose.
3. Kiểm tra Discovery <code>issuer</code> và JWKS.
4. Cấu hình Spring Boot <code>issuer-uri</code>, Client ID, secret, scopes.
5. Chạy Portal local cổng 18080.
6. Login qua browser với Alice, kiểm tra <code>OidcUser.iss/sub</code>.
7. Dùng browser context mới login Bob, xác minh session isolation.
8. Test disabled user và wrong password.
9. Test wrong redirect URI/client secret trong fixture riêng.
10. Test state mismatch và ID Token validation bằng integration/fault fixture.
11. Kiểm thử saved request redirect sau login.
12. Kiểm thử local logout và RP-Initiated Logout nếu OP hỗ trợ.
13. Chạy smoke tests bằng Testcontainers với random port.
14. Chạy tests song song với realms/accounts độc lập.
15. Thu logs/metrics không có token, passwords, state hoặc session cookie.
16. Dọn containers và dữ liệu test sau khi hoàn thành.

**Câu hỏi tổng hợp:** Vì sao phải phân biệt một test **provider discovery thành công**, một test **<code>oidcLogin()</code> với mock principal**, và một test **authorization-code login qua browser thành công**?

**Đáp án:** Chúng kiểm tra các lớp khác nhau: metadata/network, Spring Security authorization/controller và toàn bộ OIDC protocol/session flow. Không lớp nào tự thay thế hoàn toàn hai lớp còn lại.

## 30. Tổng kết

- **Integration test OIDC Client cần một provider test đáng tin cậy**, không chỉ mock <code>OidcUser</code>.
- Có thể dùng Keycloak container, một OP sandbox hoặc HTTP stub; mỗi công cụ có phạm vi kiểm thử khác nhau.
- **Realm, client, test users, scopes và redirect URIs** nên được khai báo bằng fixtures có version, không phụ thuộc Admin Console thủ công.
- Test provider phải có issuer riêng, Client ID riêng, secrets riêng, users giả và không chạm production APIs/databases.
- Dùng Authorization Code Flow qua browser để kiểm tra login thật; **không dùng password grant/ROPC** làm thay thế.
- OIDC Discovery, exact issuer, Token Endpoint, JWKS, ID Token signature/issuer/audience và state/nonce/PKCE phải được xác minh đúng.
- Với Testcontainers random host ports, **public issuer URL, Discovery issuer và token <code>iss</code> phải khớp**; đừng disable issuer validation để sửa lỗi hostname.
- Callback redirect URI phải được đăng ký chính xác tại OP, nhất là khi Portal chạy random port hoặc chạy trong Docker network khác browser.
- Test accounts nên bao gồm nhiều subjects/quyền/trạng thái; test nào mutate user/session phải có isolation/cleanup rõ.
- Browser E2E cần browser context sạch để tránh SSO cookie của test trước, trừ khi đang cố ý kiểm tra switch-account/SSO reuse.
- Keycloak thật phù hợp flow chuẩn; stub/fault injection hữu ích cho malformed JWT, HTTP 503, JWKS outages và các lỗi khó tạo trong OP UI.
- Testcontainers smoke test Discovery **không tự động là một OIDC login integration test**.
- Session, SavedRequest, AuthorizedClient và OP SSO session là những trạng thái khác nhau; cần test vòng đời của từng loại.
- Local logout không tự đồng nghĩa OP logout; back-channel logout cần signed Logout Token và session mapping khi áp dụng.
- CI cần pin image/dependencies, kiểm soát Docker/runtime, test isolation, secrets, logging và artifacts để có kết quả tái lập được.

### Tài liệu tham khảo

- **Spring Security Reference — OAuth2 Login (Servlet):** ClientRegistration, authorization request, callback, OIDC Login.
- **Spring Security Reference — OAuth2 Client:** authorized clients, token management và refresh token flow.
- **Spring Security Reference — Spring Security Test:** <code>oauth2Login()</code>, <code>oidcLogin()</code>, MockMvc integration.
- **Spring Boot Reference — Testcontainers and DynamicPropertySource:** lifecycle containers và injected configuration.
- **Keycloak Server Guide — Importing and Exporting Realms:** realm import JSON, client/user fixture và server startup.
- **Keycloak Server Guide — Hostname Configuration:** public issuer URL, reverse proxy và hostname behavior.
- **Testcontainers for Java Documentation — GenericContainer, Wait Strategies, JUnit Jupiter:** ephemeral containers và mapped ports.
- **OpenID Connect Core 1.0:** Authorization Code Flow, ID Token, nonce, issuer, audience và UserInfo.
- **OpenID Connect Discovery 1.0:** <code>.well-known/openid-configuration</code> và issuer metadata.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, redirect URI, state và Token Endpoint.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** code_verifier/code_challenge.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** OAuth flow hardening, mix-up và refresh-token security.
- **OWASP Authentication Testing Guide / Session Management Cheat Sheet:** test account isolation, session/cookie security và login/logout testing.
