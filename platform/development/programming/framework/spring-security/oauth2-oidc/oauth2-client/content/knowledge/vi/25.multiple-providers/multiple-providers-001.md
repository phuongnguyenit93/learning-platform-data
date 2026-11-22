# 25.1. Cấu hình nhiều registration cho OAuth 2.0 và OIDC

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, một ứng dụng có thể cần hỗ trợ nhiều nhà cung cấp danh tính, nhiều OAuth clients hoặc những grant khác nhau cùng lúc. Ví dụ **Partner Portal** cần đăng nhập nhân viên qua Corporate OP, đăng nhập đối tác qua Partner OP, hỗ trợ một nhà cung cấp OAuth2 cũ chỉ có UserInfo API, đồng thời lấy service token để gọi Reporting API.

Spring Security biểu diễn mỗi cấu hình client bằng **`ClientRegistration`**. Registration gắn với một `registrationId`, có thể trỏ tới một provider và chứa client ID/secret, grant type, redirect URI, scope cùng các thông tin cần thiết khác.

Điều cốt lõi là: **nhiều registrations không có nghĩa user được tự động liên kết giữa các OP, cũng không có nghĩa access token của registration này được phép gọi API của registration kia**.

Sau bài học, bạn có thể:

1. Phân biệt `registrationId`, provider ID, issuer URI, Authorization Server và Resource Server.
2. Cấu hình nhiều OIDC registrations trong `application.yml` bằng `provider` và `issuer-uri`.
3. Kết hợp OIDC Login, OAuth2-only Login và `client_credentials` trong một ứng dụng Spring Boot.
4. Hiểu URL mặc định bắt đầu login và callback theo registration ID.
5. Tra cứu `ClientRegistrationRepository` và nhận diện provider của `OAuth2AuthenticationToken`.
6. Tạo trang chọn nhà cung cấp đăng nhập mà không mở URL/issuer tùy ý cho người dùng.
7. Phân biệt `OidcUser` và `OAuth2User` theo cách đăng nhập.
8. Thiết kế account linking dựa trên cặp `iss` + `sub`, không tự gộp user vì trùng email.
9. Quản lý các `OAuth2AuthorizedClient` riêng cho từng registration/principal.
10. Dùng token đúng audience/scope, không gửi token của nhà cung cấp này cho API khác.
11. Bảo vệ state, PKCE, nonce, issuer validation và callback khỏi provider mix-up.
12. Xử lý logout, account switching, reverse proxy, multi-environment và kiểm thử riêng từng provider.

## 1. Bài toán: một Portal, nhiều provider

Một công ty xây **Partner Portal** với bốn tích hợp:

- **Corporate OP:** nhân viên đăng nhập qua OIDC.
- **Partner OP:** đối tác đăng nhập qua một OIDC issuer khác.
- **Legacy OAuth2 Provider:** dùng Authorization Code + UserInfo để nhận biết user; chưa hỗ trợ OIDC.
- **Reporting Authorization Server:** cấp access token theo `client_credentials` cho scheduled job.

Sơ đồ:

~~~mermaid
flowchart LR
    U["Browser user"] --> P["Partner Portal / Spring Security"]
    P --> C["Corporate OIDC OP"]
    P --> R["Partner OIDC OP"]
    P --> L["Legacy OAuth2 AS"]
    P --> S["Reporting AS"]
    P --> API1["Orders API"]
    P --> API2["Reporting API"]
~~~

Portal có các registration ID:

~~~text
corporate-login
partner-login
legacy-oauth-login
reporting-service
~~~

Ba registration đầu phục vụ **interactive login**. `reporting-service` phục vụ **service identity**, không có browser login.

Một ứng dụng có thể cấu hình tất cả các registration trong cùng một cây `spring.security.oauth2.client`.

## 2. Registration, provider và issuer khác nhau

### 2.1. `ClientRegistration`

Một `ClientRegistration` mô tả **một OAuth client đã đăng ký với AS**. Nó có thể chứa:

~~~text
registrationId
clientId
clientSecret
clientAuthenticationMethod
authorizationGrantType
redirectUri
scopes
providerDetails
clientName
~~~

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
~~~

`corporate-login` là **khóa do ứng dụng đặt**, không phải issuer của ID token.

### 2.2. Provider configuration

`provider` mô tả endpoint và metadata của Authorization Server/OpenID Provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees
~~~

`corporate-op` là khóa local của provider config. `issuer-uri` là issuer thực sự mà OP/AS công bố và là một phần của trust boundary.

### 2.3. Ghép registration với provider

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-op
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees
~~~

Trường `provider: corporate-op` nối registration với provider đã cấu hình.

### 2.4. Bảng phân biệt

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Registration ID | `corporate-login` | Khóa tra cứu OAuth client trong Spring |
| Provider ID | `corporate-op` | Khóa cấu hình provider trong Spring Boot |
| Client ID | `partner-portal-web` | Danh tính OAuth client tại AS |
| Issuer URI | `https://login.company.example/realms/employees` | Danh tính AS/OP dùng khi xác minh token |
| Authorization endpoint | `.../authorize` | Bắt đầu Authorization Code flow |
| Token endpoint | `.../token` | Đổi code, refresh hoặc client credentials lấy token |
| UserInfo endpoint | `.../userinfo` | Nhận thông tin user theo contract |
| JWKS URI | `.../certs` | Lấy public keys phục vụ JWT validation |
| Resource Server | `Orders API` | API nhận access token |

Không dùng registration ID, provider ID và issuer như ba tên thay thế nhau.

## 3. Ví dụ đầy đủ: hai OIDC registrations

Một `application.yml` cơ bản:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-op
            client-id: ${CORPORATE_OIDC_CLIENT_ID}
            client-secret: ${CORPORATE_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

          partner-login:
            provider: partner-op
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees

          partner-op:
            issuer-uri: https://identity.partner.example/realms/partners
~~~

Tên miền và tên client trong ví dụ đều giả định. Triển khai thực tế phải dùng issuer, client ID, secret và redirect URI đã được đăng ký, kiểm chứng tại từng OP.

### 3.1. Registration ID phải duy nhất

Hai registration có khóa riêng:

~~~text
corporate-login
partner-login
~~~

Nếu dùng trùng khóa YAML hoặc ghi đè property, một trong hai registration có thể bị mất hoặc mang cấu hình sai.

### 3.2. Cùng URI template, khác callback thật

Cả hai dùng:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

nhưng URL thực tế là:

~~~text
https://portal.example.com/login/oauth2/code/corporate-login
https://portal.example.com/login/oauth2/code/partner-login
~~~

Corporate OP chỉ nên được cấu hình callback thuộc `corporate-login`; Partner OP tương tự với `partner-login`. Mỗi OP phải chấp nhận chính xác URI mà application gửi.

### 3.3. Scope `openid`

OIDC Login cần yêu cầu `openid` và provider thực sự hỗ trợ OIDC. Scope `profile` và `email` có thể yêu cầu thêm claims, nhưng OP quyết định dữ liệu được cấp.

Nếu provider không hỗ trợ OIDC, thêm `openid` vào danh sách scope không tự tạo ra một ID token hợp lệ.

### 3.4. Secret và client authentication

Trong ví dụ, hai registrations là confidential clients dùng `client_secret_basic`. Mỗi OP có thể phát client secret riêng.

Nếu dùng public client hoặc client authentication method khác như `private_key_jwt`, phải cấu hình theo chính sách provider. Không cố dùng secret hoặc client ID của Corporate OP tại Partner OP.

## 4. OIDC discovery với `issuer-uri`

Khi cấu hình issuer URI hợp lệ, Spring Security có thể lấy metadata của OP/AS để xác định:

- `authorization_endpoint`.
- `token_endpoint`.
- `jwks_uri`.
- `userinfo_endpoint` nếu công bố.
- Issuer và thông tin hỗ trợ khác.

Ví dụ:

~~~text
Corporate issuer:
  https://login.company.example/realms/employees

Partner issuer:
  https://identity.partner.example/realms/partners
~~~

Mỗi provider có issuer riêng và metadata riêng.

### 4.1. Discovery không thay đăng ký OAuth client

Metadata giúp tìm endpoints và capabilities. Nó **không tự tạo client ID/secret hoặc đăng ký callback** ở OP.

Portal vẫn cần được cấu hình là OAuth client ở Corporate OP và Partner OP.

### 4.2. ID token phải có issuer đúng

OIDC ID token chứa claim `iss`. Token nhận từ Corporate OP phải được xác minh theo issuer của Corporate registration. Không chấp nhận ID token của Partner OP như Corporate identity vì chữ ký JWT thuộc một key hợp lệ nào đó.

### 4.3. Không discovery URL do người dùng gửi

Một endpoint như:

~~~text
/login?issuer=https://arbitrary.example.net
~~~

không nên khiến backend tạo registration, gọi metadata endpoint và tin issuer tùy ý. Điều đó có thể dẫn tới SSRF hoặc đăng nhập qua một AS không được hệ thống phê duyệt.

Chỉ nhận registration ID nằm trong danh sách đã được server quản lý.

### 4.4. Khi provider không hỗ trợ discovery

Có thể cấu hình endpoints thủ công:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          manual-provider:
            authorization-uri: https://auth.example.net/oauth2/authorize
            token-uri: https://auth.example.net/oauth2/token
            user-info-uri: https://api.example.net/me
            user-name-attribute: id
~~~

Các URL phải theo tài liệu của provider thực, không tự suy ra endpoint bằng cách nối chuỗi vào issuer khi provider không công bố metadata.

## 5. OAuth2-only Login: không có `OidcUser`

Một provider cũ chỉ hỗ trợ OAuth2 Authorization Code, có UserInfo API nhưng không phát ID token.

Cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-oauth-login:
            provider: legacy-oauth
            client-id: ${LEGACY_OAUTH_CLIENT_ID}
            client-secret: ${LEGACY_OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read

        provider:
          legacy-oauth:
            authorization-uri: https://auth.legacy.example/oauth/authorize
            token-uri: https://auth.legacy.example/oauth/token
            user-info-uri: https://api.legacy.example/me
            user-name-attribute: id
~~~

Ở đây:

- Không dùng `openid`.
- Không có OIDC ID token.
- OAuth2 Login có thể dùng UserInfo API để lấy attributes.
- Principal thường là `OAuth2User`, không phải `OidcUser`.
- `user-name-attribute: id` phải khớp field thật mà API trả.
- Tin cậy của dữ liệu profile phải dựa trên contract và authentication policy của provider.

### 5.1. OAuth2 không đồng nghĩa OIDC

OAuth 2.0 là framework ủy quyền. OIDC bổ sung lớp xác thực End-User, ID token và các quy tắc issuer/nonce/subject.

Nếu cần nhận diện user với bảo đảm OIDC, hãy ưu tiên OP thực sự hỗ trợ OIDC thay vì tự ghép một cơ chế UserInfo không chuẩn hóa.

### 5.2. Không mặc định email là ID bất biến

Legacy API có thể trả:

~~~json
{
  "id": "legacy-123",
  "email": "alice@example.com",
  "name": "Alice"
}
~~~

`id` có thể là stable provider user ID nếu contract xác nhận; email có thể thay đổi hoặc chưa được xác minh.

Không tự động liên kết local account chỉ từ email của provider OAuth2-only.

## 6. `client_credentials` là một registration khác mục đích

Một backend job có thể cần access token để gọi Reporting API mà không có người dùng tương tác.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: reporting-as
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read

        provider:
          reporting-as:
            token-uri: https://auth.reporting.example/oauth2/token
~~~

Với `client_credentials`:

- Token đại diện cho client/service, không phải End-User.
- Không có browser login.
- Thường không cần redirect URI, nonce, ID token hoặc scope `openid`.
- AS phải cho phép client dùng grant.
- Token cần audience/scope phù hợp Reporting API.

**Không hiển thị `reporting-service` thành nút login.**

### 6.1. Dùng đúng manager cho background service

Trong Servlet ứng dụng, `AuthorizedClientServiceOAuth2AuthorizedClientManager` phù hợp với tác vụ không có `HttpServletRequest`/`HttpServletResponse`.

Đừng phụ thuộc vào web authorization manager cần request context khi scheduled job đang chạy ngoài HTTP request.

## 7. File YAML tổng hợp bốn registrations

Tất cả có thể nằm trong cùng một cây cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-op
            client-id: ${CORPORATE_OIDC_CLIENT_ID}
            client-secret: ${CORPORATE_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

          partner-login:
            provider: partner-op
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

          legacy-oauth-login:
            provider: legacy-oauth
            client-id: ${LEGACY_OAUTH_CLIENT_ID}
            client-secret: ${LEGACY_OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read

          reporting-service:
            provider: reporting-as
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read

        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees

          partner-op:
            issuer-uri: https://identity.partner.example/realms/partners

          legacy-oauth:
            authorization-uri: https://auth.legacy.example/oauth/authorize
            token-uri: https://auth.legacy.example/oauth/token
            user-info-uri: https://api.legacy.example/me
            user-name-attribute: id

          reporting-as:
            token-uri: https://auth.reporting.example/oauth2/token
~~~

Đây là ví dụ minh họa, không phải cấu hình có thể sử dụng trực tiếp với một provider công khai. Giá trị thật phải do AS và môi trường deployment cung cấp.

### 7.1. Có thể nhiều registration cùng provider

Ví dụ một Corporate OP có hai clients:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-op
            client-id: ${CORPORATE_LOGIN_CLIENT_ID}
            client-secret: ${CORPORATE_LOGIN_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile

          corporate-orders:
            provider: corporate-op
            client-id: ${CORPORATE_ORDERS_CLIENT_ID}
            client-secret: ${CORPORATE_ORDERS_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - orders.read

        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees
~~~

Hai registrations này:

- Cùng issuer.
- Khác registration ID.
- Có thể có client ID/secret riêng.
- Có scope và authorized client records riêng.
- Cần callback URI riêng nếu cùng dùng Authorization Code.
- Không tự chia sẻ token chỉ vì issuer giống nhau.

Nếu không có nhu cầu thực sự, không nên tạo nhiều registration chỉ để đổi scope mà không đánh giá consent và incremental authorization policy.

## 8. URL bắt đầu login theo `registrationId`

Với cấu hình mặc định của Spring Security Servlet:

~~~text
/oauth2/authorization/{registrationId}
~~~

Ví dụ:

~~~text
/oauth2/authorization/corporate-login
/oauth2/authorization/partner-login
/oauth2/authorization/legacy-oauth-login
~~~

Spring Security chọn `ClientRegistration` rồi dựng Authorization Request với đúng client ID, authorization endpoint, scope, redirect URI, state và các tham số bảo vệ tương ứng.

### 8.1. Sơ đồ flow Partner Login

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant P as Portal Spring Security
    participant R as ClientRegistrationRepository
    participant OP as Partner OP
    U->>B: Chọn Partner Login
    B->>P: GET /oauth2/authorization/partner-login
    P->>R: findByRegistrationId(partner-login)
    R-->>P: Partner ClientRegistration
    P-->>B: 302 đến authorization endpoint Partner OP
    B->>OP: Authorization Request
    OP-->>B: 302 callback với code + state
    B->>P: /login/oauth2/code/partner-login
    P->>OP: Token request với authorization code
    OP-->>P: Token response
    Note over P: Verify OIDC ID token và tạo Authentication
    P-->>B: Authenticated session
~~~

### 8.2. Bắt đầu login khác callback

~~~text
/oauth2/authorization/partner-login
/login/oauth2/code/partner-login
~~~

- URL đầu khởi tạo request và lưu correlation.
- URL sau nhận Authorization Response, đổi code lấy token và hoàn thành login.

Không gọi trực tiếp callback với code tùy ý để bỏ qua state verification.

### 8.3. Callback của từng OP phải được đăng ký

Corporate OP:

~~~text
https://portal.example.com/login/oauth2/code/corporate-login
~~~

Partner OP:

~~~text
https://portal.example.com/login/oauth2/code/partner-login
~~~

Nếu OP chưa đăng ký callback hoặc URI không khớp, Authorization Server có thể từ chối trước token exchange.

## 9. Cấu hình Spring Security Servlet

Một `SecurityFilterChain` có thể phục vụ nhiều login registrations:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/css/**", "/error")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

`oauth2Login()` xử lý browser Authorization Code/OIDC Login, còn `oauth2Client()` hỗ trợ dùng authorized clients cho outbound API calls.

### 9.1. Không cần một chain cho mỗi provider

Không cần tạo ba SecurityFilterChain chỉ vì có Corporate, Partner và Legacy providers. Spring Security tra cứu registration theo ID.

Các chain riêng chỉ cần khi ứng dụng có các security boundaries khác nhau, chẳng hạn web session login và API Resource Server bearer token ở các nhóm endpoint khác nhau.

### 9.2. Default login page

Trong những điều kiện cấu hình phù hợp, Spring Security có thể tạo default login page với links cho OAuth2 client registrations.

Nhưng không nên mặc định mọi repository động hoặc mọi grant type sẽ được hiển thị đúng như ý định nghiệp vụ. Với nhiều providers, trang chọn provider tự quản lý thường rõ ràng hơn.

## 10. Trang chọn provider tùy biến

Một trang login có thể hiển thị:

~~~text
Đăng nhập vào Partner Portal

[Corporate Account]
[Partner Account]
[Legacy Account]
~~~

Các links:

~~~html
<a href="/oauth2/authorization/corporate-login">
  Corporate Account
</a>
<a href="/oauth2/authorization/partner-login">
  Partner Account
</a>
<a href="/oauth2/authorization/legacy-oauth-login">
  Legacy Account
</a>
~~~

Không hiển thị `reporting-service` vì không phải browser login.

### 10.1. Cấu hình custom login page

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/login", "/css/**", "/error")
                    .permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2.loginPage("/login"))
            .oauth2Client(Customizer.withDefaults())
            .build();
}
~~~

Khi đặt `loginPage("/login")`, ứng dụng cần tự triển khai view/endpoint GET /login.

### 10.2. Controller hiển thị trang login

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginPageController {

    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

Giả định ứng dụng có view template tên `login`. Trong bài này chỉ minh họa logic, không tạo template file.

### 10.3. Chỉ hiển thị những registration được phép login

Không hiển thị mọi key trong `ClientRegistrationRepository` mà không lọc mục đích. Một registration dùng `client_credentials` hoặc grant mở rộng chỉ dành cho backend sẽ không có browser flow.

Có thể dùng một allowlist cố định:

~~~java
private static final Set<String> LOGIN_REGISTRATIONS =
        Set.of("corporate-login", "partner-login",
               "legacy-oauth-login");
~~~

Đây chỉ là danh sách minh họa; ứng dụng còn phải kiểm tra quyền/cấu hình hợp lệ.

### 10.4. Không nhận issuer URL do browser chọn

Một giao diện như:

~~~text
/login?providerUrl=https://random.example.net
~~~

rồi backend gọi discovery theo URL tùy ý có nguy cơ SSRF và issuer injection. Chỉ cho browser lựa chọn registration ID đã được định nghĩa từ cấu hình tin cậy.

## 11. `ClientRegistrationRepository`

Spring Security sử dụng:

~~~java
org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository
~~~

Phương thức cốt lõi:

~~~java
ClientRegistration findByRegistrationId(String registrationId);
~~~

Spring Boot có thể tạo `InMemoryClientRegistrationRepository` từ properties nếu ứng dụng không định nghĩa repository bean khác.

### 11.1. Tra cứu registration

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.stereotype.Service;

@Service
public class RegistrationLookupService {

    private final ClientRegistrationRepository repository;

    public RegistrationLookupService(
            ClientRegistrationRepository repository) {
        this.repository = repository;
    }

    public ClientRegistration required(String registrationId) {
        ClientRegistration registration =
                repository.findByRegistrationId(registrationId);

        if (registration == null) {
            throw new IllegalArgumentException(
                    "Unknown OAuth2 registration");
        }

        return registration;
    }
}
~~~

Tra được registration **không có nghĩa caller được phép dùng registration ấy**. Với API động, cần kiểm tra use case được phép và principal tương ứng.

### 11.2. Phân biệt repositories

| Repository/service | Dữ liệu |
|---|---|
| `ClientRegistrationRepository` | Client ID, secret, grant, provider metadata |
| `OAuth2AuthorizedClientRepository` | Access/refresh token của registration/principal trong web context |
| `OAuth2AuthorizedClientService` | Authorized clients theo registration/principal ngoài request |
| `OAuth2AuthorizationRequestRepository` | Authorization Request/correlation đang đợi callback |

Đừng lấy `ClientRegistration` rồi xem như nó đã chứa token của Alice. Nó là cấu hình client, không phải authorized client.

## 12. Xác định registration đã dùng để đăng nhập

Trong Servlet app, `OAuth2AuthenticationToken` có:

~~~java
authentication.getAuthorizedClientRegistrationId();
~~~

Ví dụ:

~~~java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LoginProviderController {

    @GetMapping("/me/provider")
    ProviderInfo provider(
            OAuth2AuthenticationToken authentication) {

        return new ProviderInfo(
                authentication.getAuthorizedClientRegistrationId(),
                authentication.getName());
    }

    record ProviderInfo(
            String registrationId,
            String principalName) {}
}
~~~

Nếu user login bằng Partner OP, response có thể là:

~~~json
{
  "registrationId": "partner-login",
  "principalName": "partner-user-123"
}
~~~

Giá trị principal name thực tế phụ thuộc OIDC subject hoặc provider-specific user-name attribute.

### 12.1. Không dùng registration ID làm role

`registrationId=corporate-login` không tự có nghĩa `ROLE_ADMIN`. Provider xác thực user; ứng dụng phải có policy mapping authorities và kiểm tra quyền nghiệp vụ.

### 12.2. URL login ban đầu không chứng minh user đã xác thực

Một user có thể mở `/oauth2/authorization/partner-login` nhưng chưa hoàn thành flow. Chỉ tin Authentication được Spring Security xây sau callback/token validation thành công.

## 13. Phân biệt `OidcUser` và `OAuth2User`

Với OIDC Login, principal thường là `OidcUser`. Với OAuth2-only Login, principal thường là `OAuth2User`.

### 13.1. Xử lý chung hai loại principal

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityTypeController {

    @GetMapping("/me/identity-type")
    String identityType(
            @AuthenticationPrincipal OAuth2User principal) {

        if (principal instanceof OidcUser) {
            return "OIDC";
        }

        return "OAUTH2";
    }
}
~~~

Đoạn code chỉ minh họa loại principal; endpoint thật cần xác thực và xử lý principal hợp lệ.

### 13.2. Không cast mọi principal thành OIDC

Mẫu:

~~~java
OidcUser user = (OidcUser) authentication.getPrincipal();
~~~

có thể thất bại khi login bằng legacy OAuth2 provider không có ID token.

Cần phân nhánh theo loại principal hoặc mapping vào một internal identity model.

## 14. Multi-provider account linking

Cấu hình nhiều OIDC OP là một chuyện. **Liên kết các danh tính của cùng một người** là chuyện khác.

Giả sử:

~~~text
Corporate OP:
  iss = https://login.company.example/realms/employees
  sub = 12345
  email = alex@example.com

Partner OP:
  iss = https://identity.partner.example/realms/partners
  sub = 12345
  email = alex@example.com
~~~

Hai cặp `iss`/`sub` khác nhau có thể đại diện cho **hai người khác nhau**.

### 14.1. `sub` chỉ duy nhất trong phạm vi issuer

Không dùng một mình `sub=12345` làm khóa định danh toàn cầu. Nên xem cặp:

~~~text
(issuer, subject)
~~~

### 14.2. Lấy issuer và subject từ OIDC ID token

~~~java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record ExternalIdentityKey(
        String issuer,
        String subject) {

    public static ExternalIdentityKey from(OidcUser user) {
        return new ExternalIdentityKey(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject());
    }
}
~~~

Dữ liệu trong ID token phải được Spring Security xác minh trước khi dùng làm identity.

### 14.3. Email không phải khóa account linking mặc định

Email có thể thay đổi, chưa verified hoặc được cấp lại cho người khác. Không gộp hai external identities tự động chỉ vì email giống nhau.

Nếu cần account linking, phải có flow xác minh user kiểm soát cả hai identities, với consent/audit theo policy.

### 14.4. Schema ánh xạ custom

~~~sql
CREATE TABLE external_identity (
    id              BIGSERIAL PRIMARY KEY,
    local_user_id   BIGINT NOT NULL,
    issuer          VARCHAR(500) NOT NULL,
    subject         VARCHAR(500) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    linked_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (issuer, subject)
);
~~~

Đây là schema minh họa của application, không phải schema Spring Security tạo sẵn.

### 14.5. Pairwise subject identifiers

Một số OP dùng pairwise `sub` để hạn chế correlation giữa clients/sectors. Không giả định hai registrations cùng OP luôn nhìn thấy cùng subject nếu chính sách pairwise khác nhau.

## 15. Quản lý authorized clients theo registration

Một principal có thể có các authorized clients:

~~~text
alice
  corporate-login  -> A1/R1
  corporate-orders -> A2/R2
  partner-api      -> B1/S1
~~~

Access token của `corporate-login` không tự thay cho `corporate-orders` hoặc `partner-api`.

### 15.1. Tra authorized client theo registration

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

public class AuthorizedClientLookup {

    private final OAuth2AuthorizedClientRepository repository;

    public AuthorizedClientLookup(
            OAuth2AuthorizedClientRepository repository) {
        this.repository = repository;
    }

    public OAuth2AuthorizedClient lookup(
            String registrationId,
            Authentication authentication,
            HttpServletRequest request) {

        return repository.loadAuthorizedClient(
                registrationId,
                authentication,
                request);
    }
}
~~~

`registrationId` phải gắn với use case được server cho phép; không cho caller chọn tùy ý để đọc token của một integration khác.

### 15.2. `@RegisteredOAuth2AuthorizedClient`

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersClientStatusController {

    @GetMapping("/orders/token-status")
    TokenStatus status(
            @RegisteredOAuth2AuthorizedClient("corporate-orders")
            OAuth2AuthorizedClient client) {

        if (client == null) {
            return new TokenStatus(false, null);
        }

        return new TokenStatus(
                client.getAccessToken() != null,
                client.getClientRegistration().getRegistrationId());
    }

    record TokenStatus(boolean hasAccessToken, String registrationId) {}
}
~~~

Không trả access token raw trong response.

### 15.3. Login Partner không tự cấp token Corporate

~~~text
User login qua partner-login
  -> Portal có Partner Authentication
  -> không tự tạo corporate-orders authorized client
~~~

Nếu Orders API cần token của Corporate AS, phải có flow token issuance/authorization phù hợp. Không dùng Partner ID token để gọi Corporate API.

## 16. `OAuth2AuthorizedClientManager` trong môi trường nhiều registrations

Manager dùng registration ID và principal để load/save authorized client; các providers trong chain xử lý grant tương ứng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class MultiClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Đây là ví dụ cấu hình manager trong Servlet HTTP request; tùy dự án Spring Boot có thể đã cung cấp manager mặc định phù hợp, không nhất thiết cần tạo bean mới.

### 16.1. Refresh token riêng từng provider

Nếu Corporate authorized client có A1/R1 và Partner authorized client có B1/S1, việc refresh Corporate phải dùng R1 tại Corporate token endpoint, không dùng S1 của Partner.

Không lưu “refresh token hiện tại” vào một biến global chung.

### 16.2. Background manager riêng

Một job dùng `reporting-service` với `client_credentials` nên dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` và service store phù hợp, không phụ thuộc request/session browser.

### 16.3. Registration selection có thể ảnh hưởng bảo mật

Một endpoint nhận cả `registrationId` và URL đích từ user rồi lấy token tương ứng có nguy cơ thành proxy mang credential. Cần whitelist registration theo chức năng và giới hạn host/audience của HTTP client.

## 17. Access token đúng Resource Server

Nhiều providers không đồng nghĩa mọi access token dùng chung.

| Resource Server | Nguồn token hợp lệ | Lưu ý |
|---|---|---|
| Corporate Profile API | Token do Corporate AS cấp theo audience/scope | Không dùng Partner token |
| Partner Orders API | Token do Partner AS cấp theo contract | Không dùng ID token |
| Reporting API | `reporting-service` client credentials token | Service identity |
| Payments API | Token dành cho Payments audience | Có thể cần grant/client khác |

Resource Server phải kiểm tra issuer, audience, expiry, scope/authority và quyền nghiệp vụ.

### 17.1. Đăng nhập thành công không tự cấp quyền API khác

Corporate OIDC Login chứng minh một user được OP xác thực. Nó không chứng minh user có `orders.approve` hoặc được xem mọi đơn hàng.

### 17.2. Token Exchange phải được AS cho phép

Nếu nghiệp vụ cần đổi token cho downstream API, có thể xem Token Exchange khi AS hỗ trợ. Không gửi token của Partner AS sang Corporate AS chỉ vì cả hai dùng OAuth 2.0.

### 17.3. Giới hạn host khi đính kèm Bearer token

Nếu RestClient/WebClient gắn access token tự động, nên tách dedicated client theo API. Không truyền URL do browser cung cấp vào client mang bearer token hoặc tự follow redirect cross-host không có policy.

## 18. State, PKCE, nonce và kiểm soát mix-up

Mỗi Authorization Code/OIDC transaction cần correlation riêng:

~~~text
Corporate flow:
  registrationId = corporate-login
  state = state-C
  nonce = nonce-C
  PKCE verifier = verifier-C (nếu dùng)

Partner flow:
  registrationId = partner-login
  state = state-P
  nonce = nonce-P
  PKCE verifier = verifier-P (nếu dùng)
~~~

Không chia sẻ một biến static `state`/nonce/code_verifier giữa các browser sessions hoặc registration flows.

### 18.1. State correlation

`state` bảo vệ correlation giữa authorization request và response. Không bỏ qua state validation khi viết custom callback handler.

### 18.2. PKCE

PKCE bảo vệ authorization code bằng code challenge/verifier. Cách áp dụng phụ thuộc loại client, Spring Security version và OP policy. Không dùng chung code verifier giữa các requests.

### 18.3. OIDC nonce

OIDC nonce (khi áp dụng) ràng buộc authentication transaction với ID token. ID token phải còn được xác minh issuer, audience, signature, time và các claims khác theo profile.

### 18.4. Provider mix-up

Một tình huống nguy hiểm:

~~~text
Portal khởi tạo flow Corporate
  -> Browser nhận authorization response từ Partner
  -> Custom callback xử lý nhầm như Corporate
~~~

Có thể gây gửi code tới sai token endpoint hoặc chấp nhận kết quả danh tính không đúng issuer.

Bảo vệ bằng:

- Ràng buộc `registrationId` với authorization request đã lưu.
- State correlation.
- Callback URI riêng theo registration.
- Issuer validation.
- Không lấy token endpoint/issuer từ callback request không tin cậy.
- Ưu tiên filter flow chuẩn thay vì callback handler tự viết thiếu kiểm tra.
- Dùng issuer identification trong authorization response nếu protocol/profile hỗ trợ và cấu hình phù hợp.

**Đường dẫn callback riêng không thay thế cryptographic validation.**

## 19. Chuyển provider trong cùng browser

Alice login Corporate, sau đó chọn Partner Login trong cùng browser. Ứng dụng có thể thay Authentication hiện tại nhưng authorized clients cũ chưa chắc đã được xóa khỏi mọi storage.

### 19.1. Cần quy tắc account switching

- Xác định user đã logout hay đang chủ động liên kết accounts.
- Kiểm tra issuer/subject từ login mới.
- Không tự gộp local accounts nếu chưa xác minh.
- Dọn authorized clients không còn phù hợp.
- Đảm bảo token của principal A không được dùng trong request principal B.
- Audit sự kiện chuyển provider nếu cần.

### 19.2. Session của OP khác session Portal

Portal logout không tự kết thúc Corporate OP SSO session hoặc Partner OP SSO session. Hai OP có cookie, policy và logout endpoints riêng.

### 19.3. Tránh token của user cũ

Nếu Bob login vào session đã từng thuộc Alice, custom store không được trả token Alice chỉ vì registration ID giống. Khóa storage phải xét principal, issuer/tenant và policy.

## 20. Reverse proxy và redirect URI

Portal có thể chạy sau load balancer:

~~~text
External URL:
  https://portal.example.com

Internal URL:
  http://portal-service:8080
~~~

Nếu application tính `{baseUrl}` từ host nội bộ, redirect URI gửi tới OP có thể bị sai:

~~~text
http://portal-service:8080/login/oauth2/code/partner-login
~~~

thay vì:

~~~text
https://portal.example.com/login/oauth2/code/partner-login
~~~

### 20.1. Dấu hiệu

- OP báo redirect URI mismatch.
- Callback quay về HTTP hoặc hostname nội bộ.
- Một provider thành công, provider khác thất bại vì mỗi OP đăng ký URI khác nhau.
- Session/cookie không được browser gửi như kỳ vọng.

### 20.2. Hướng xử lý

- Đăng ký đúng external HTTPS redirect URI tại từng OP.
- Cấu hình forwarded headers và reverse proxy tin cậy.
- Không tin `X-Forwarded-Host` do client ngoài tự kiểm soát.
- Kiểm tra allowed host/TLS.
- Có thể dùng redirect URI cố định qua cấu hình deployment an toàn khi cần.
- Không mở wildcard redirect URI rộng tại AS để “sửa nhanh”.

## 21. Nhiều môi trường dev/staging/prod

Một dự án có:

~~~text
application.yml
application-dev.yml
application-staging.yml
application-prod.yml
~~~

Client ID/secret, issuer hoặc callback domain có thể khác ở từng môi trường.

### 21.1. Không dùng secret production trong dev

Đăng ký client riêng cho môi trường phát triển. Không commit secret vào source.

### 21.2. Cấu hình issuer theo deployment tin cậy

Có thể dùng environment variables do hệ thống deployment quản lý, nhưng không cho user tự thay issuer.

### 21.3. Mỗi OP cần callback đúng môi trường

Corporate/Partner OP phải được đăng ký callbacks cho dev, staging và production nếu các môi trường đều hoạt động. Không tự suy luận callback giữa các môi trường là tương đương.

## 22. Custom claim mapping và roles

Corporate OP có thể trả `groups`, Partner OP trả `roles`, Legacy OAuth2 trả một JSON profile khác.

Ví dụ:

~~~json
{
  "sub": "corporate-123",
  "groups": ["staff", "finance"]
}
~~~

Và:

~~~json
{
  "sub": "partner-456",
  "roles": ["viewer"]
}
~~~

Không tự map mọi claim `admin` từ mọi issuer thành `ROLE_ADMIN`. Cần quy tắc trust và authority mapping rõ ràng cho từng issuer.

### 22.1. User identity khác quyền nghiệp vụ

Authentication đã hợp lệ không có nghĩa user được truy cập mọi API resource. Backend/Resource Server còn phải kiểm tra owner, tenant, scope và internal roles.

### 22.2. Không log toàn bộ claims

ID token/UserInfo có thể chứa dữ liệu cá nhân. Log metadata như registration ID, issuer reference và correlation ID khi cần, không dump token raw hoặc toàn bộ claims.

## 23. Logout với nhiều OP

Local logout trong Portal và RP-Initiated Logout tại từng OP là các flow khác nhau.

### 23.1. Local session logout

Application có thể clear SecurityContext/invalidate session. Điều này không tự revoke refresh token ở Authorization Server.

### 23.2. OP End Session

Nếu Corporate OP và Partner OP hỗ trợ OIDC logout, mỗi nơi có end-session endpoint riêng. Không dùng endpoint Partner để logout identity Corporate.

### 23.3. `id_token_hint`

Nếu provider yêu cầu/cho phép `id_token_hint`, dùng đúng ID token của issuer/client/session tương ứng, không gửi ID token của provider A cho provider B.

### 23.4. Authorized client storage ngoài session

Một `OAuth2AuthorizedClientService` ở database có thể còn record token sau browser logout. Cần quy tắc cleanup riêng nếu nghiệp vụ yêu cầu disconnect provider hoặc chấm dứt quyền API.

## 24. Reactive/WebFlux

Ý tưởng multi-registration không đổi trong WebFlux, nhưng lớp bảo mật/repository là reactive.

### 24.1. SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactivePortalSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/", "/login", "/error").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

### 24.2. API reactive tương ứng

~~~text
ReactiveClientRegistrationRepository
ServerOAuth2AuthorizedClientRepository
ReactiveOAuth2AuthorizedClientService
ReactiveOAuth2AuthorizedClientManager
WebClient
~~~

Không dùng `HttpSessionOAuth2AuthorizedClientRepository` của Servlet khi đang xử lý `ServerWebExchange`.

### 24.3. Cùng quy tắc isolation

WebFlux không tự giải quyết việc issuer A bị nhầm với issuer B, email collision hoặc token sai audience. Vẫn cần registration selection, ID token validation, account linking và storage isolation.

## 25. Kiểm thử nhiều registrations

Một file YAML không báo lỗi chưa chứng minh hai OIDC OP và OAuth2-only provider đều hoạt động. Cần kiểm thử theo từng registration.

### 25.1. Ma trận cấu hình

| Test | Kỳ vọng |
|---|---|
| Lookup `corporate-login` | Trả đúng Corporate ClientRegistration |
| Lookup `partner-login` | Trả đúng Partner ClientRegistration |
| Lookup `legacy-oauth-login` | Có UserInfo mapping đúng |
| Lookup `reporting-service` | Grant type là client_credentials |
| Registration lạ | Không tìm thấy |
| Corporate issuer | Khớp metadata của Corporate OP |
| Partner issuer | Khớp metadata của Partner OP |
| Hai registrations cùng provider | Không trộn client ID/redirect/scope |
| Callback mỗi provider | Trỏ đến external HTTPS URL đã đăng ký |

### 25.2. Unit test repository

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@SpringBootTest
class ClientRegistrationsTest {

    @Autowired
    ClientRegistrationRepository repository;

    @Test
    void registersTwoIndependentOidcProviders() {
        var corporate =
                repository.findByRegistrationId("corporate-login");

        var partner =
                repository.findByRegistrationId("partner-login");

        assertThat(corporate).isNotNull();
        assertThat(partner).isNotNull();

        assertThat(corporate.getRegistrationId())
                .isNotEqualTo(partner.getRegistrationId());

        assertThat(corporate.getProviderDetails().getIssuerUri())
                .isNotEqualTo(
                        partner.getProviderDetails().getIssuerUri());
    }
}
~~~

**Lưu ý:** `issuer-uri` có thể kích hoạt discovery trong quá trình cấu hình. Dùng mock metadata/test issuer, tránh để một unit/integration test không kiểm soát gọi OP production.

### 25.3. Authorization Request tests

Với từng registration:

1. Truy cập `/oauth2/authorization/{registrationId}`.
2. Kiểm tra redirect đến đúng authorization endpoint.
3. Xác nhận client ID.
4. Xác nhận redirect URI.
5. Xác nhận scope.
6. Xác nhận state correlation.
7. Xác nhận PKCE/nonce theo flow và provider policy.

### 25.4. Negative tests

- Callback có state không khớp.
- Callback path thuộc provider khác.
- ID token issuer không đúng.
- ID token audience không đúng.
- UserInfo thiếu `user-name-attribute`.
- Client secret không khớp.
- Redirect URI không được OP đăng ký.
- Resource Server từ chối token sai audience.

Không dùng token thật production để thử các trường hợp lỗi.

### 25.5. Authorized client isolation tests

- Alice đăng nhập Corporate.
- Bob đăng nhập Partner.
- Bob không đọc được token Alice.
- Đổi provider trong cùng browser không dùng stale token.
- Hai OP có cùng email hoặc `sub` không tự merge.
- `reporting-service` không xuất hiện như interactive login.
- Service manager nhận token đúng Reporting AS.

## 26. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| `ClientRegistration` không tìm thấy | Sai registration ID, profile hoặc YAML | Properties/repository |
| Nút Corporate mở Partner OP | Link đăng nhập dùng sai registration | `/oauth2/authorization/{id}` |
| OP báo redirect mismatch | URI chưa đăng ký hoặc proxy baseUrl sai | External redirect/callback |
| Token endpoint `invalid_client` | Sai client ID/secret/auth method | Registration/AS settings |
| ID token issuer mismatch | Provider/issuer sai | Discovery và `iss` validation |
| Cast `OidcUser` bị lỗi | Login đến từ OAuth2-only provider | Phân biệt OidcUser/OAuth2User |
| UserInfo không tạo principal | user-name-attribute sai | API response contract |
| Hai accounts bị nhập nhằng | Chỉ dùng email hoặc sub đơn lẻ | Issuer+subject/linking |
| Partner token gọi Corporate API trả 401 | Sai audience/issuer | Resource Server contract |
| API trả 403 | Thiếu scope/ownership | API authorization |
| Token của user A lẫn user B | Custom repository key không đủ | Principal/session isolation |
| Job dùng client credentials bị redirect login | Dùng web registration/manager sai | Service manager |
| Custom login page không hiển thị | Chưa implement GET /login/view | Login page config |
| Logout Portal nhưng OP vẫn SSO | Local logout khác OP logout | End-session policy |
| Chỉ production lỗi callback | Reverse proxy/forwarded header | External URI và trusted headers |
| Gửi token cho host bất kỳ | HTTP client không có allowlist | Dedicated RestClient/WebClient |

## 27. Những hiểu nhầm cần tránh

**“Mỗi provider phải có một SecurityFilterChain.”**

Không. Một `oauth2Login()` có thể dùng nhiều registrations.

**“Registration ID phải bằng issuer.”**

Không. Registration ID là khóa nội bộ; issuer là danh tính AS/OP được xác minh.

**“Một provider chỉ có một registration.”**

Không. Nhiều registrations có thể dùng cùng provider.

**“Có `openid` là provider chắc chắn trả ID token.”**

Không. Provider phải thực sự hỗ trợ OIDC.

**“OAuth2 UserInfo giống OIDC ID token.”**

Không. OIDC định nghĩa authentication semantics và ID token validation riêng.

**“Đăng nhập Corporate thì tự có Partner token.”**

Không. Authorized clients thuộc registrations và principal riêng.

**“Cùng email hay cùng subject là một user.”**

Không. `sub` chỉ duy nhất trong issuer; linking cần được xác minh.

**“Client credentials là một nút login.”**

Không. Nó là grant cho service identity.

**“Logout Portal là logout mọi OP và revoke mọi token.”**

Không. Các vòng đời riêng.

**“Discovery tự đăng ký OAuth client tại OP.”**

Không. Client registration và redirect allowlist phải có tại AS.

## 28. Tình huống thực hành

### A. Hai OIDC issuers

Portal cho Corporate và Partner đăng nhập.

**Xử lý:** hai registrations trỏ hai providers/issuers; links và callbacks theo registration ID, token issuer validation độc lập.

### B. Cùng issuer, nhiều client IDs

Corporate OP cấp một client cho login và một client khác cho Orders API.

**Xử lý:** nhiều registrations dùng chung provider, authorized client và callback/scope vẫn riêng.

### C. Legacy OAuth2 UserInfo

Provider không hỗ trợ OIDC.

**Xử lý:** cấu hình authorization/token/user-info endpoints và user-name-attribute. Xử lý principal `OAuth2User`; không ép OIDC.

### D. Scheduled reporting job

Job cần token `client_credentials`.

**Xử lý:** dùng `reporting-service` với service authorized client manager, không có browser login.

### E. Email collision

Hai OP phát email giống nhau.

**Xử lý:** không auto-link; dùng issuer+subject và quy trình xác minh account linking.

### F. Reverse proxy làm redirect sai

Portal gửi callback URL từ internal hostname.

**Xử lý:** trusted forwarded headers/external baseUrl, đăng ký callback đúng mỗi OP, tránh wildcard.

### G. API khác issuer

Partner login thành công nhưng Orders API chỉ tin Corporate AS.

**Xử lý:** không dùng Partner token như Corporate token; thiết kế authorization/token issuance đúng Resource Server.

### H. Chuyển Alice sang Bob

Cùng browser, registration/token cũ còn ở storage.

**Xử lý:** kiểm soát session/principal isolation và cleanup, không dùng token của Alice trong request Bob.

## 29. Câu hỏi tự kiểm tra

**Câu 1.** Registration ID khác provider ID như thế nào?

**Trả lời:** Registration ID định danh OAuth client trong ứng dụng; provider ID tham chiếu cấu hình AS/OP.

**Câu 2.** Có thể nhiều registrations trỏ cùng một provider không?

**Trả lời:** Có. Chúng có thể có client ID, scope hoặc grant khác nhau.

**Câu 3.** Scope nào thường xác định yêu cầu OIDC?

**Trả lời:** `openid`, kết hợp với provider thực sự hỗ trợ OIDC.

**Câu 4.** URL bắt đầu login mặc định của `partner-login`?

**Trả lời:** `/oauth2/authorization/partner-login`.

**Câu 5.** Callback mặc định thường có dạng?

**Trả lời:** `/login/oauth2/code/{registrationId}`, khớp redirect URI tại OP.

**Câu 6.** Có cần SecurityFilterChain riêng cho từng OP?

**Trả lời:** Thường không.

**Câu 7.** Registration nào không nên hiển thị làm nút login?

**Trả lời:** `client_credentials` hoặc registration không dành cho browser interaction.

**Câu 8.** User đăng nhập Partner có tự có Corporate access token không?

**Trả lời:** Không.

**Câu 9.** API nào giúp biết registration đã dùng login trong Servlet?

**Trả lời:** `OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()`.

**Câu 10.** Có thể cast mọi principal thành `OidcUser`?

**Trả lời:** Không. OAuth2-only login có thể cho `OAuth2User`.

**Câu 11.** Vì sao cần `iss` + `sub`?

**Trả lời:** Subject chỉ duy nhất trong phạm vi issuer.

**Câu 12.** Email trùng có chứng minh cùng user?

**Trả lời:** Không. Linking phải được xác minh.

**Câu 13.** Discovery có cấp client secret cho Portal?

**Trả lời:** Không. AS cần đăng ký client và cấu hình credential/callback.

**Câu 14.** ID token issuer mismatch nên xử lý bằng cách nào?

**Trả lời:** Kiểm tra provider/registration/metadata; không tắt issuer validation.

**Câu 15.** Logout local có tự revoke mọi token và kết thúc SSO ở cả hai OP?

**Trả lời:** Không.

**Câu 16.** Token của Corporate OP có dùng gọi mọi Resource Server không?

**Trả lời:** Không. Phải đúng audience/scope và contract API.

**Câu 17.** Với WebFlux dùng repository registration nào?

**Trả lời:** `ReactiveClientRegistrationRepository`.

**Câu 18.** Cách xác minh multi-provider thực sự hoạt động?

**Trả lời:** Kiểm thử lookup, redirects, state/issuer validation, token exchange và account/token isolation riêng từng registration.

## Ghi nhớ

- **Một ứng dụng Spring Security có thể cấu hình nhiều ClientRegistration** với provider/issuer riêng hoặc dùng chung provider khi có lý do chính đáng.
- **`registrationId` không phải issuer hay provider ID**. Dùng chúng đúng vị trí để tránh chọn sai endpoint.
- **OIDC Login cần `openid` và issuer/ID token validation**; OAuth2-only Login cần UserInfo/identity mapping riêng.
- **`/oauth2/authorization/{registrationId}` bắt đầu login**, còn `/login/oauth2/code/{registrationId}` thường nhận callback. Đăng ký callback chính xác ở từng OP.
- **Một SecurityFilterChain thường đủ cho nhiều login providers**; trang login chỉ nên hiển thị những registration dành cho interactive flow.
- **`client_credentials` dùng cho service identity**, không phải nút đăng nhập End-User.
- **Token của các registrations không được tự dùng chung**. Access token phải đúng Resource Server audience, scope và quyền nghiệp vụ.
- **Không tự gộp identities qua email hoặc `sub` đơn lẻ**. Dùng issuer + subject và một quy trình account linking an toàn.
- **Giữ state, PKCE, nonce, issuer validation và correlation riêng cho từng authorization transaction**, tránh provider mix-up.
- **Logout, session và token revocation là những vòng đời riêng**. Phải kiểm thử account switching, token isolation và callback reverse proxy theo từng provider.
