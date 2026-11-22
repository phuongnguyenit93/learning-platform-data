# 25.2. Nhiều registration dùng chung một provider

## 1. Bài toán: một OpenID Provider phục vụ nhiều OAuth2 clients

Giả sử công ty vận hành một **Employee Portal** để đọc đơn hàng và một **Admin Console** cho bộ phận quản trị. Hai ứng dụng hoặc hai chức năng của cùng ứng dụng đều đăng nhập thông qua một OpenID Provider (OP):

~~~text
Issuer: https://login.company.example
~~~

Nhưng tại OP có **hai bản ghi OAuth2 client** khác nhau:

~~~text
Client A:
  client_id = employee-portal-web
  redirect_uri = https://portal.example.com/login/oauth2/code/portal-web
  scopes = openid profile orders.read

Client B:
  client_id = employee-portal-admin
  redirect_uri = https://portal.example.com/login/oauth2/code/portal-admin
  scopes = openid profile admin.read
~~~

Hai clients có chung issuer, authorization endpoint, token endpoint, JWK Set endpoint và có thể chung UserInfo endpoint. Tuy nhiên, **client ID, client secret, redirect URI, scopes, consent, token và quyền sử dụng API không tự động chia sẻ**.

Trong **Spring Security OAuth 2.0/OIDC Client**, cách biểu diễn đúng là:

~~~text
registrationId = portal-web
         |
         +---- provider key = company-oidc
         |
registrationId = portal-admin
         |
         +---- provider key = company-oidc
                          |
                          v
              issuer = https://login.company.example
~~~

**Một provider configuration được nhiều registrations tham chiếu không đồng nghĩa Spring Security chỉ có một OAuth2 client.** Đây là trọng tâm bài học.

> Bối cảnh: Java 17+, Spring Boot 3, Spring Security 6, Spring MVC/Servlet và OIDC Authorization Code Flow. Phần Reactive được nhắc riêng. Các hostname/client IDs/scopes là giả định giáo dục; IAM/Authorization Server và Resource Server phải thực sự cấu hình, cấp và xác minh các quyền đó.

## 2. Phân biệt ba khái niệm thường bị gọi chung là provider

| Khái niệm | Ví dụ | Trách nhiệm |
|---|---|---|
| **ClientRegistration** | `portal-web`, `portal-admin` | Định nghĩa một OAuth client với ID, secret, grant, redirect, scopes |
| **Provider configuration** trong Spring Boot | `company-oidc` | Thông tin chung về Authorization Server/OpenID Provider |
| **OpenID Provider thật** | `https://login.company.example` | Thực hiện login, authorization và phát tokens |

`spring.security.oauth2.client.provider` cũng **không phải** class `AuthenticationProvider` trong Spring Security authentication pipeline. Chữ “provider” xuất hiện ở nhiều tầng nhưng mỗi tầng có chức năng khác nhau.

### 2.1. Bên trong ClientRegistration

Spring Security sử dụng:

~~~java
org.springframework.security.oauth2.client.registration.ClientRegistration
~~~

Thông tin mang tính **client-specific**:

~~~text
registrationId
clientId
clientSecret
clientAuthenticationMethod
authorizationGrantType
redirectUri
scopes
clientName
~~~

Thông tin **provider metadata**:

~~~text
providerDetails.authorizationUri
providerDetails.tokenUri
providerDetails.jwkSetUri
providerDetails.issuerUri
providerDetails.userInfoEndpoint
providerDetails.configurationMetadata
~~~

Hai ClientRegistration có thể cùng metadata endpoints nhưng có các trường client-specific khác nhau.

### 2.2. Ma trận ví dụ

| Thuộc tính | portal-web | portal-admin | Kết luận |
|---|---|---|---|
| registration ID | `portal-web` | `portal-admin` | **Riêng** |
| client ID | `employee-portal-web` | `employee-portal-admin` | **Riêng** |
| client secret | WEB secret | ADMIN secret | **Riêng** |
| grant | authorization_code | authorization_code | Có thể giống |
| scopes | openid, profile, orders.read | openid, profile, admin.read | Khác |
| redirect URI template | `{baseUrl}/login/oauth2/code/{registrationId}` | Cùng template | URI sau expansion khác |
| provider key | `company-oidc` | `company-oidc` | **Chung** |
| issuer | `https://login.company.example` | Cùng issuer | **Chung** |
| token endpoint | OP token endpoint | Cùng endpoint | **Chung** |
| JWKS | OP JWK Set endpoint | Cùng endpoint | **Chung** |

**Cùng template redirect URI không có nghĩa cùng redirect URI thật.** `{registrationId}` được thay bằng ID riêng.

## 3. Sơ đồ kiến trúc

~~~mermaid
flowchart TD
    Browser["Browser của nhân viên"] --> Portal["Employee Portal / Spring Security"]
    Portal --> Repo["ClientRegistrationRepository"]
    Repo --> Web["portal-web registration"]
    Repo --> Admin["portal-admin registration"]
    Web --> Provider["provider: company-oidc"]
    Admin --> Provider
    Provider --> OP["OpenID Provider / issuer chung"]
    Portal --> Tokens["OAuth2AuthorizedClientRepository / Service"]
    Tokens --> WToken["portal-web + principal -> token W"]
    Tokens --> AToken["portal-admin + principal -> token A"]
    Portal --> Orders["Orders API"]
    Portal --> AdminAPI["Admin API"]
~~~

Một số ranh giới cần giữ:

1. **OP** cung cấp metadata và token endpoints cho các clients đã đăng ký.
2. **ClientRegistrationRepository** lưu những registration IDs riêng.
3. **Authorization Code Flow** được khởi tạo theo registration ID.
4. **OAuth2AuthorizedClient** được lưu theo registration/principal.
5. **Resource Server** kiểm tra token, audience, scopes và quyền dữ liệu.
6. **Browser session** không tự hợp nhất hai authorization grants.

## 4. Cấu hình Spring Boot: nhiều registrations, một provider

Đây là cấu hình trọng tâm:

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-web:
            provider: company-oidc
            client-id: ${PORTAL_WEB_CLIENT_ID}
            client-secret: ${PORTAL_WEB_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read

          portal-admin:
            provider: company-oidc
            client-id: ${PORTAL_ADMIN_CLIENT_ID}
            client-secret: ${PORTAL_ADMIN_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - admin.read

        provider:
          company-oidc:
            issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
~~~

Mọi client secret ở đây là **placeholder**, phải được inject từ secret manager/runtime. Không đặt secret thật trong Git, README hay browser JavaScript.

### 4.1. Đọc cấu trúc YAML

~~~text
spring.security.oauth2.client.registration.<registrationId>
spring.security.oauth2.client.provider.<providerId>
~~~

Cấu hình:

~~~yaml
portal-web:
  provider: company-oidc
~~~

nghĩa là registration `portal-web` tham chiếu provider alias `company-oidc`.

Tương tự:

~~~yaml
portal-admin:
  provider: company-oidc
~~~

Provider alias được định nghĩa **một lần**:

~~~yaml
provider:
  company-oidc:
    issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
~~~

Chỉ có **một provider configuration**, nhưng vẫn có **hai ClientRegistration objects**.

### 4.2. Không cần nhân bản provider metadata

Một cấu hình trùng lặp như:

~~~yaml
provider:
  web-idp:
    issuer-uri: https://login.company.example
  admin-idp:
    issuer-uri: https://login.company.example
~~~

không tự sai về mặt cú pháp, nhưng khi thực sự cùng issuer/endpoints sẽ làm tăng khả năng drift, cấu hình lệch và bảo trì không cần thiết. Dùng chung provider key giúp biểu thị rõ **trust boundary chung**.

### 4.3. Provider alias không phải ClientRegistration ID

Đừng nhầm:

~~~text
provider alias: company-oidc
registration ID: portal-web
client ID: employee-portal-web
issuer URI: https://login.company.example
~~~

Các giá trị này có ngữ nghĩa khác nhau. Khi Spring Security yêu cầu `clientRegistrationId`, sử dụng `portal-web` hoặc `portal-admin`, không dùng provider alias.

## 5. OpenID discovery và issuer-uri

OpenID Providers thường công bố discovery metadata liên quan:

~~~text
/.well-known/openid-configuration
~~~

Một response minh họa:

~~~json
{
  "issuer": "https://login.company.example",
  "authorization_endpoint": "https://login.company.example/oauth2/authorize",
  "token_endpoint": "https://login.company.example/oauth2/token",
  "jwks_uri": "https://login.company.example/oauth2/jwks",
  "userinfo_endpoint": "https://login.company.example/oidc/userinfo"
}
~~~

Nếu đặt `issuer-uri` trong provider configuration, Spring Security có thể dùng OIDC discovery để dựng provider details và phục vụ validation theo thư viện.

**Chia sẻ provider config là chia sẻ giá trị metadata và nguồn trust**, không phải bảo đảm framework chỉ tạo một Java object hoặc chỉ thực hiện một lần HTTP discovery. Điều đó phụ thuộc implementation/caching.

### 5.1. Issuer là danh tính bảo mật

Hai URLs:

~~~text
https://login.company.example/realms/employees
https://login.company.example/realms/partners
~~~

có thể là **hai issuers khác nhau** dù chung host và vendor. Không gộp hai realm thành cùng provider chỉ vì tên công ty giống nhau.

### 5.2. Cùng JWKS không đồng nghĩa cùng issuer

Trong OIDC, việc xác minh ID Token cần kiểm tra issuer, audience, signature, expiration, nonce và các điều kiện khác. Hai issuers có thể dùng các keys tương tự, nhưng không được bỏ issuer validation chỉ vì JWK Set URI giống nhau.

### 5.3. Provider không hỗ trợ discovery

Với OAuth2 provider tùy biến, có thể cấu hình endpoints thủ công:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          legacy-oauth:
            authorization-uri: https://auth.example.test/oauth2/authorize
            token-uri: https://auth.example.test/oauth2/token
            user-info-uri: https://auth.example.test/api/userinfo
            user-name-attribute: sub
~~~

Nếu client thực sự yêu cầu OIDC (scope `openid` và ID Token), cần thiết lập đầy đủ issuer/JWK/metadata và validation phù hợp, không chỉ copy token URI bất kỳ rồi giả định đó là OP chuẩn.

## 6. Tại Authorization Server phải có hai OAuth client records

YAML ở Portal **không tạo client trong IdP**. Quản trị viên IAM cần đăng ký tương ứng:

| Client tại IdP | Client ID | Redirect URI được đăng ký |
|---|---|---|
| Employee Portal | employee-portal-web | `https://portal.example.com/login/oauth2/code/portal-web` |
| Admin Console | employee-portal-admin | `https://portal.example.com/login/oauth2/code/portal-admin` |

Client scopes, secret/client auth method, consent, PKCE và token policies cũng cần được phép đúng từng record.

### 6.1. Vì sao redirect URI template giống mà callback khác?

YAML:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

Với baseUrl là `https://portal.example.com`:

~~~text
portal-web   -> /login/oauth2/code/portal-web
portal-admin -> /login/oauth2/code/portal-admin
~~~

OP cần cho phép URI thực **theo từng client**. Không dùng client ID của web với redirect URI admin rồi mong OP tự sửa.

### 6.2. Một redirect URI chung có được không?

Một callback URI chung có thể khả thi khi ứng dụng tùy biến resolver/filter/correlation đúng cách, nhưng mặc định dùng `{registrationId}` rõ ràng hơn.

Nếu tùy biến callback URL, phải bảo đảm Authorization Code response được ghép đúng **registration, original state, redirect URI và client credentials**. Không bỏ correlation chỉ để dùng một path duy nhất.

### 6.3. Client secrets là độc lập

Hai records có client IDs khác nhau thường có credential riêng. Không copy `PORTAL_WEB_CLIENT_SECRET` vào admin registration trừ khi đó thật sự là credential đã đăng ký và được IdP chấp nhận.

Lỗi thường gặp:

~~~text
invalid_client
unauthorized_client
invalid_scope
redirect_uri_mismatch
~~~

Tên lỗi cụ thể tùy provider, nhưng cần điều tra **registration-specific settings** trước khi sửa issuer chung.

## 7. URL bắt đầu login phụ thuộc registration ID

Mặc định trên Servlet Spring Security:

~~~text
/oauth2/authorization/portal-web
/oauth2/authorization/portal-admin
~~~

Khi browser tới:

~~~http
GET /oauth2/authorization/portal-web HTTP/1.1
Host: portal.example.com
~~~

Spring Security tạo authorization request với:

~~~text
client_id=employee-portal-web
redirect_uri=https://portal.example.com/login/oauth2/code/portal-web
scope=openid profile orders.read
state=<random-web-state>
response_type=code
~~~

Với URL:

~~~http
GET /oauth2/authorization/portal-admin HTTP/1.1
Host: portal.example.com
~~~

các tham số thay đổi:

~~~text
client_id=employee-portal-admin
redirect_uri=https://portal.example.com/login/oauth2/code/portal-admin
scope=openid profile admin.read
state=<random-admin-state>
response_type=code
~~~

**Cả hai cùng chuyển tới một authorization endpoint** nhưng Authorization Server quyết định theo client ID, redirect URI, requested scopes và per-client policies.

## 8. SecurityFilterChain không cần nhân đôi chỉ vì nhiều registrations

Một cấu hình cơ bản:

~~~java
package com.example.portal.config;

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
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Một chain với `oauth2Login()` có thể hỗ trợ nhiều `authorization_code` registrations qua cùng `ClientRegistrationRepository`.

### 8.1. Khi nào cần tách SecurityFilterChain?

Nếu Admin Console cần security rules/entry points khác, hoặc app có API stateless và browser login stateful, có thể tách chains theo request matchers. Nhưng **hai registrations tự chúng không bắt buộc có hai chains**.

Đặc biệt, nếu tạo nhiều chains, kiểm tra `@Order`, `securityMatcher` và bảo đảm login start/callback được xử lý bởi chain có OAuth2 login filters tương ứng.

## 9. Trang chọn phương thức đăng nhập

Khi cung cấp hai lựa chọn:

~~~html
<main>
  <h1>Đăng nhập</h1>
  <a href="/oauth2/authorization/portal-web">
    Employee Portal
  </a>
  <a href="/oauth2/authorization/portal-admin">
    Admin Console
  </a>
</main>
~~~

Nếu dùng login page tùy chỉnh:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .loginPage("/login")
);
~~~

thì phải tự cung cấp GET `/login` và cho phép truy cập URL đó.

### 9.1. Chọn Admin Console không tạo ROLE_ADMIN

Một người click:

~~~text
/oauth2/authorization/portal-admin
~~~

chỉ yêu cầu Authorization Server xử lý **admin OAuth client**. Điều đó **không tự cấp quyền admin** cho người dùng.

Application/Resource Server vẫn phải xác minh RBAC, permissions, organization/tenant, scope và resource ownership.

### 9.2. Allowlist đăng nhập công khai

Nếu có thêm machine registration như `reports-service`, đừng tự liệt kê nó thành browser login choice hoặc cho browser lựa chọn mọi registration ID qua query parameter không kiểm soát. Registration được cấu hình **không đồng nghĩa** phù hợp cho user login.

## 10. State, nonce và PKCE thuộc mỗi authorization request

Cùng OP không có nghĩa các correlation values được chia sẻ:

~~~text
portal-web:
  state = W1
  nonce = NW1
  PKCE code_verifier = VW1 (nếu áp dụng)

portal-admin:
  state = A1
  nonce = NA1
  PKCE code_verifier = VA1 (nếu áp dụng)
~~~

Mỗi callback cần được ghép với đúng authorization request:

~~~mermaid
sequenceDiagram
    actor Browser as Browser
    participant Portal as Spring Security Portal
    participant OP as Shared OpenID Provider

    Browser->>Portal: GET /oauth2/authorization/portal-web
    Portal-->>Browser: Redirect: client_id=WEB, state=W1
    Browser->>OP: Authenticate/authorize WEB
    OP-->>Browser: Redirect: code=C1, state=W1
    Browser->>Portal: GET /login/oauth2/code/portal-web?code=C1&state=W1
    Portal->>Portal: Find original WEB request / validate state
    Browser->>Portal: GET /oauth2/authorization/portal-admin
    Portal-->>Browser: Redirect: client_id=ADMIN, state=A1
    Browser->>OP: Authenticate/authorize ADMIN
    OP-->>Browser: Redirect: code=C2, state=A1
    Browser->>Portal: GET /login/oauth2/code/portal-admin?code=C2&state=A1
    Portal->>Portal: Find original ADMIN request / validate state
~~~

`state` chống login CSRF và gắn response với request; OIDC `nonce` gắn ID Token với authentication request; PKCE `code_verifier` ràng buộc việc đổi code.

**Không dùng state/nonce/code_verifier chung** chỉ vì issuer trùng.

### 10.1. Không hoán đổi authorization code giữa clients

Authorization code được phát cho một client ID và redirect URI cụ thể. Không dùng code của WEB để đổi tại token endpoint bằng admin client credentials. Authorization Server phải kiểm tra binding, và có thể trả `invalid_grant` nếu sai.

## 11. Session browser, session OP và authorized clients: ba thứ khác nhau

~~~text
Browser:
  JSESSIONID của Portal
  Cookie SSO riêng của OpenID Provider

Portal:
  HttpSession / SecurityContext
  OAuth2AuthorizationRequest trong login flow
  OAuth2AuthorizedClient store

OP:
  SSO session
  client registrations, authorization/consent policy
~~~

Nếu user đã login `portal-web`, khi họ bắt đầu login `portal-admin`, OP có thể tái dùng SSO session mà không yêu cầu nhập mật khẩu lại.

**Không nhập mật khẩu lại không có nghĩa web/admin cùng token hoặc user đã được cấp quyền quản trị.** OP vẫn đang xử lý một authorization request mới của client admin và có thể yêu cầu consent hoặc step-up MFA.

### 11.1. Authentication hiện hành trong SecurityContext

Trong một browser session Servlet, Spring Security thường lưu **một Authentication hiện hành**. Đăng nhập lại qua registration khác có thể thay thế Authentication đó.

~~~text
T0: Browser đang authenticated qua portal-web.
T1: Browser khởi động portal-admin authorization.
T2: Sau callback, Authentication hiện hành có thể là portal-admin.
~~~

Điều này khác với **authorized-client store** có thể còn cả WEB và ADMIN entries.

### 11.2. Nhiều tabs và session correlation

Nếu tab A bắt đầu web login, tab B bắt đầu admin login rồi tab A callback, tùy authorization request repository/session implementation có thể có xung đột state.

Không quy mọi `authorization_request_not_found` thành lỗi provider config. Kiểm tra cookies, HttpSession persistence, multiple tabs, authorization request repository và callback correlation.

## 12. Cookie SameSite và reverse proxy áp dụng cho cả hai login flows

Với top-level GET callback thông thường:

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

thường phù hợp khi IdP cross-site. Với OIDC `response_mode=form_post` tạo cross-site POST callback, cookie Lax thường không được gửi; có thể cần `SameSite=None; Secure` và CSRF callback POST handling được thiết kế hẹp.

**Cùng provider không bảo đảm mọi registration dùng cùng response mode hoặc step-up policy.**

### 12.1. Reverse proxy cần hiểu public base URL

Nếu browser truy cập:

~~~text
https://portal.example.com
~~~

nhưng app nhìn thấy:

~~~text
http://portal-service:8080
~~~

thì `{baseUrl}` có thể bị dựng sai, khiến cả hai registrations gặp redirect URI mismatch hoặc cookie không gửi do scheme/host sai.

Một cấu hình minh họa:

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Chỉ tin forwarded headers từ proxy đáng tin; ingress phải strip/overwrite client-supplied values để tránh host/header spoofing.

## 13. OAuth2AuthorizedClient thuộc registration, không thuộc provider alias

Spring Security biểu diễn kết quả authorization:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
~~~

Một authorized client gắn với:

~~~text
ClientRegistration + principalName + accessToken [+ refreshToken]
~~~

Ví dụ:

~~~text
Authorized Client W:
  registrationId = portal-web
  principalName = employee-0042
  accessToken = AT-W
  refreshToken = RT-W (nếu được cấp)

Authorized Client A:
  registrationId = portal-admin
  principalName = employee-0042
  accessToken = AT-A
  refreshToken = RT-A (nếu được cấp)
~~~

Authorized-client store thường phân biệt theo **(clientRegistrationId, principalName)**. Không cache bằng:

~~~text
key = providerId + ":" + username
~~~

vì hai clients cùng `company-oidc` sẽ đè token của nhau.

### 13.1. Token không hoán đổi qua registrations

AT-W có thể có scope `orders.read` và audience cho Orders API. AT-A có thể có scope `admin.read` và audience khác.

**Cùng issuer/JWK không làm token WEB hợp lệ cho ADMIN API.** Resource Server kiểm tra issuer, signature/introspection, audience, scopes, expiry và resource authorization.

### 13.2. ID Token không phải access token

OIDC ID Token phục vụ xác thực tại client. Nếu:

~~~text
ID Token W:
  iss = https://login.company.example
  aud = employee-portal-web

ID Token A:
  iss = https://login.company.example
  aud = employee-portal-admin
~~~

thì dù cùng issuer/signature key, **audience vẫn theo client ID**. Không dùng ID Token W cho Admin client, không dùng ID Token để gọi Orders API thay access token.

## 14. Refresh tokens cũng không được chia sẻ

Một OP có thể cấp refresh token cho một, cả hai hoặc không registration nào, tùy client policy, scopes và consent.

~~~text
portal-web:
  RT-W issued to WEB client

portal-admin:
  RT-A issued to ADMIN client
~~~

Không dùng RT-W cùng admin client credentials tại token endpoint. RT-W có thể bị ràng buộc với WEB client ID/authorization grant.

### 14.1. Refresh token rotation

~~~text
WEB: RT-W1 -> AT-W2 + RT-W2
ADMIN: RT-A1 tồn tại độc lập
~~~

Nếu `invalid_grant` xảy ra với RT-W1, không được tự xóa/admin-revoke RT-A1 chỉ vì provider key giống nhau.

### 14.2. Token TTL khác nhau

OP có thể áp dụng:

~~~text
WEB access token TTL   = 5 phút
ADMIN access token TTL = 2 phút
~~~

Provider URI chung **không có nghĩa client policies giống nhau**. Authorized-client manager phải dựa vào expiry/token response của từng client.

## 15. Đọc registration hiện hành sau login

Trong Servlet, Authentication của OAuth2 login thường là:

~~~java
org.springframework.security.oauth2.client.authentication
    .OAuth2AuthenticationToken
~~~

Ví dụ controller:

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentLoginController {

    @GetMapping("/api/login-context")
    public Map<String, String> current(Authentication authentication) {
        if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
            throw new IllegalStateException(
                "Current authentication is not OAuth2 Login"
            );
        }
        return Map.of(
            "registrationId",
            oauth.getAuthorizedClientRegistrationId(),
            "principalName",
            oauth.getName()
        );
    }
}
~~~

Kết quả registration ID có thể là `portal-web` hoặc `portal-admin`. **Không nên phơi bày token, client secret hay claims nhạy cảm** ra browser; endpoint minh họa cần authorization và tối thiểu dữ liệu.

### 15.1. Current Authentication khác authorized-client store

`getAuthorizedClientRegistrationId()` phản ánh login Authentication hiện tại. Authorized-client repository/service có thể vẫn lưu authorized clients khác cho principal trước đó hoặc cùng principal.

Không suy từ “đang login portal-admin” rằng token portal-web đã bị xóa, hoặc ngược lại.

## 16. @RegisteredOAuth2AuthorizedClient có cần chỉ định registration ID?

Servlet Spring Security có annotation:

~~~java
org.springframework.security.oauth2.client.annotation
    .RegisteredOAuth2AuthorizedClient
~~~

Ví dụ:

~~~java
@GetMapping("/api/orders/registration")
public String currentOrdersRegistration(
    @RegisteredOAuth2AuthorizedClient("portal-web")
    OAuth2AuthorizedClient authorizedClient
) {
    if (authorizedClient == null) {
        return "portal-web authorized client not available";
    }
    return authorizedClient.getClientRegistration().getRegistrationId();
}
~~~

Không trả `authorizedClient.getAccessToken().getTokenValue()` cho frontend. Nếu chưa có authorized client của registration được chỉ định, annotation/resolver không tự bảo đảm browser đã được cấp quyền của client đó; Authorization Code Flow tương tác có thể cần chạy riêng.

### 16.1. Không chọn client khác chỉ vì scope thiếu

Nếu user có WEB token mà Orders API đòi ADMIN scope, không lén chuyển sang `portal-admin` hoặc `reports-service` để “vượt quyền”. Business policy và consent quyết định cách xin scope mới.

## 17. OAuth2AuthorizedClientManager chọn registration theo request

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("portal-web")
        .principal(authentication)
        .build();

OAuth2AuthorizedClient client = manager.authorize(request);
~~~

`manager` là `OAuth2AuthorizedClientManager`. `authentication` phải được lấy từ security context đã xác minh; không dùng username do browser tự nhập.

### 17.1. Manager Servlet cho HTTP request

~~~java
DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientRepository
    );

manager.setAuthorizedClientProvider(
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build()
);
~~~

Đây là code minh họa wiring; variables cần được inject từ Spring. Manager dùng Servlet request context/repository, nên khi tự gọi ngoài integration có thể cần HttpServletRequest/Response được ánh xạ vào authorization context.

### 17.2. Không tự hoàn tất authorization-code flow trong cron

Nếu ứng dụng có thêm `reports-service` registration dùng `client_credentials`, scheduled job nên sử dụng `AuthorizedClientServiceOAuth2AuthorizedClientManager` với service principal và authorized-client service phù hợp.

**Shared provider không tạo HttpSession cho background job.**

## 18. WebClient trên Servlet với registration ID rõ ràng

WebClient có thể tích hợp OAuth2 Servlet:

~~~java
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction;
~~~

Bean minh họa:

~~~java
@Bean("ordersWebClient")
WebClient ordersWebClient(OAuth2AuthorizedClientManager manager) {
    ServletOAuth2AuthorizedClientExchangeFilterFunction oauth =
        new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .baseUrl("https://orders.example.test")
        .apply(oauth.oauth2Configuration())
        .build();
}
~~~

Khi gọi:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> orders = ordersWebClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("portal-web"))
    .retrieve()
    .bodyToMono(String.class);
~~~

**Không đặt `clientRegistrationId("company-oidc")`**; đó là provider alias, không phải registration.

### 18.1. WebClient theo Resource Server

Một cấu hình an toàn hơn khi có nhiều downstream:

~~~text
ordersWebClient -> https://orders.example.test + portal-web
adminWebClient  -> https://admin-api.example.test + portal-admin
~~~

Không tự động gửi Bearer token tới mọi host/URL do user nhập. Kiểm soát destinations, redirects và registration selection theo backend trust boundary.

### 18.2. Servlet async và SecurityContext

WebClient trả Mono nhưng ứng dụng Servlet dùng SecurityContext/HttpServletRequest theo ngữ cảnh request. Khi subscribe trên thread khác, cần đảm bảo OAuth2 filter có đủ context theo integration API. Không tự gắn principalName bất kỳ để tìm token khác.

## 19. RestClient trên Servlet (Spring Security 6.4+)

Từ Spring Security 6.4+, có:

~~~java
org.springframework.security.oauth2.client.web.client
    .OAuth2ClientHttpRequestInterceptor
~~~

Ví dụ:

~~~java
OAuth2ClientHttpRequestInterceptor oauth =
    new OAuth2ClientHttpRequestInterceptor(authorizedClientManager);

RestClient ordersClient = RestClient.builder()
    .baseUrl("https://orders.example.test")
    .requestInterceptor(oauth)
    .build();
~~~

Chọn registration:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;

String orders = ordersClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("portal-web"))
    .retrieve()
    .body(String.class);
~~~

`authorizedClientManager` là manager cấu hình phù hợp request context/store. Nếu app có nhiều managers thì dùng qualifier để consumer nhận đúng instance.

### 19.1. Failure handler xóa theo registration/principal

Nếu Admin API trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

thì cleanup authorized client phải nhắm đúng **portal-admin + trusted principal**, không xóa mọi token do `company-oidc` phát.

Nếu API trả `403 insufficient_scope`, token có thể vẫn hợp lệ cho API khác. Không coi mọi 403 là token revoked và không retry vô hạn.

## 20. Cùng provider nhưng client authentication method có thể khác

OP có thể có clients:

~~~text
portal-web:
  confidential client, client_secret_basic

public-frontend:
  public client, no client secret, Authorization Code + PKCE

reports-service:
  confidential service client, client_credentials
~~~

**ClientAuthenticationMethod thuộc từng ClientRegistration**. Dùng chung provider endpoints không bắt buộc mọi client dùng cùng client secret, mTLS certificate hoặc private_key_jwt policy.

### 20.1. Không đưa confidential client secret vào browser

Nếu một registration là SPA/public client, không copy server-side secret sang JavaScript. PKCE hỗ trợ Authorization Code Flow cho public clients nhưng không biến browser thành nơi giữ bí mật client.

### 20.2. Audience và token type

Access token có thể là opaque hoặc JWT tùy provider. Resource Server kiểm tra token theo contract; issuer giống nhau không bảo đảm token có audience/claims giống nhau.

## 21. Thêm registration client_credentials cùng provider

Một worker cần lấy báo cáo bằng machine identity:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: company-oidc
            client-id: ${REPORTS_SERVICE_CLIENT_ID}
            client-secret: ${REPORTS_SERVICE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
~~~

Nó dùng cùng provider alias nhưng grant và identity khác:

| Registration | Grant | Token đại diện |
|---|---|---|
| portal-web | authorization_code | Authorization của người dùng cho WEB client |
| portal-admin | authorization_code | Authorization của người dùng cho ADMIN client |
| reports-service | client_credentials | OAuth client/service |

Không dùng `reports-service` token để tự động “đăng nhập nhân viên”. Machine identity không thay user identity/consent.

### 21.1. Refresh token không bắt buộc trong client_credentials

Client Credentials Grant thường không phát refresh token; khi access token hết hạn, manager có thể xin access token mới bằng client_credentials. Không dùng refresh token của một browser registration để cấp token service.

## 22. Một issuer nhưng OIDC sub có thể khác giữa registrations

Trong OIDC, identity thường được đánh giá theo:

~~~text
(iss, sub)
~~~

Nếu OP sử dụng **public subject identifier**, hai clients cùng issuer có thể thấy cùng `sub` cho cùng người.

Nếu OP sử dụng **pairwise subject identifiers**, `sub` có thể khác nhau giữa các clients hoặc sector identifiers:

~~~text
WEB:
  iss = https://login.company.example
  sub = pairwise-web-7e8

ADMIN:
  iss = https://login.company.example
  sub = pairwise-admin-2ac
~~~

**Hai subjects khác nhau không đủ chứng minh hai người khác nhau**, nhưng cũng không được tự hợp nhất họ chỉ vì email giống nhau.

### 22.1. Pairwise sector policy

OIDC pairwise identifiers có thể phụ thuộc sector identifier; trong một số mô hình, redirect host hoặc `sector_identifier_uri` tác động sector. Vì vậy việc thay đổi client registration/redirect hosts có thể ảnh hưởng `sub`.

### 22.2. Email không phải khóa định danh bất biến

Email có thể thay đổi, chưa verified, bị tái cấp hoặc trùng trong một số hệ thống. Không mặc định:

~~~text
email_web == email_admin => same internal account
~~~

Nếu cần account linking, thực hiện một quy trình có kiểm chứng ở backend, dựa trên evidence/identity mapping đáng tin cậy.

## 23. Account linking không phải token linking

Giả sử internal user ID:

~~~text
app_user.id = u-0042
~~~

đã liên kết an toàn với hai external identities:

~~~text
WEB identity:
  issuer = https://login.company.example
  subject = pairwise-web-7e8

ADMIN identity:
  issuer = https://login.company.example
  subject = pairwise-admin-2ac
~~~

Hai identities có thể cùng map tới `u-0042` theo chính sách. Nhưng:

~~~text
WEB authorized client != ADMIN authorized client
~~~

Account linking không làm token, refresh token, scopes hoặc consent của hai OAuth clients trở thành tương đương.

### 23.1. Không coi registration admin là bằng chứng role

Một user đăng nhập qua `portal-admin` phải vẫn được ứng dụng kiểm tra RBAC/roles/membership. Client ID xác định **ứng dụng OAuth client**, không chứng minh user có quyền admin.

### 23.2. Step-up MFA có thể khác từng registration

Admin client có thể yêu cầu `max_age`, `acr_values`, `prompt` hoặc chính sách OP khác. Dù cùng issuer, không mặc định SSO session thỏa mức xác thực cần cho thao tác nhạy cảm.

Ứng dụng phải kiểm tra authentication assurance/auth_time và authorization theo contract với OP, không suy từ tên registration.

## 24. Multi-tenant: khi nào phải dùng nhiều provider configurations?

So sánh hai mô hình.

**Mô hình A — Một issuer với nhiều OAuth clients:**

~~~text
issuer = https://id.example.com/realms/corporate
client_id = web
client_id = admin
client_id = reports
~~~

=> Có thể chia sẻ provider configuration.

**Mô hình B — Nhiều issuers/realms:**

~~~text
issuer A = https://id.example.com/realms/tenant-a
issuer B = https://id.example.com/realms/tenant-b
~~~

=> Thường phải có provider configurations tách theo issuer/trust boundary.

### 24.1. Không tự tin issuer do browser nhập

Một request như:

~~~http
GET /login?issuer=https://attacker.example HTTP/1.1
~~~

không được phép khiến backend tạo ClientRegistration rồi tin issuer bất kỳ. Dynamic issuer onboarding cần allowlist, SSRF prevention, metadata validation và cơ chế quản trị tin cậy.

### 24.2. Tenant quyền không phụ thuộc provider alias

`company-oidc` chỉ cho biết cấu hình provider. Tenant/resource authorization vẫn phải được kiểm tra ở backend/Resource Server. Không lấy `tenantId` không tin cậy rồi coi đó là bằng chứng user thuộc tenant.

## 25. Dev, staging và production

Ví dụ mỗi môi trường có issuer riêng:

~~~text
DEV:
  https://login-dev.company.example

STAGING:
  https://login-staging.company.example

PROD:
  https://login.company.example
~~~

Mỗi environment có thể giữ cấu trúc:

~~~yaml
registration:
  portal-web:
    provider: company-oidc
  portal-admin:
    provider: company-oidc
provider:
  company-oidc:
    issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
~~~

nhưng `issuer-uri`, client IDs, secrets và registered redirect URIs phải thuộc **cùng environment**.

### 25.1. Không dùng chung prod secrets trong dev

Tách secrets/clients theo môi trường giúp giảm ảnh hưởng khi credentials của dev/staging bị lộ. Không thêm wildcard redirect URI quá rộng chỉ để dễ chuyển môi trường.

### 25.2. Xác minh actual redirect URI sau reverse proxy

Ngay cả khi YAML đúng, forwarded host/proto sai có thể làm `{baseUrl}` thành host nội bộ và gây lỗi cả hai registrations. Kiểm tra URL thực được gửi đến OP và issuer registration.

## 26. Đọc ClientRegistrationRepository trong Java

Trong Servlet:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

ClientRegistration web =
    registrations.findByRegistrationId("portal-web");

ClientRegistration admin =
    registrations.findByRegistrationId("portal-admin");
~~~

`registrations` là bean `ClientRegistrationRepository` do Spring cung cấp/ứng dụng cấu hình.

Các giá trị có thể được so sánh:

~~~java
String issuerWeb = web.getProviderDetails().getIssuerUri();
String issuerAdmin = admin.getProviderDetails().getIssuerUri();

String clientIdWeb = web.getClientId();
String clientIdAdmin = admin.getClientId();
~~~

Kỳ vọng:

~~~text
issuerWeb.equals(issuerAdmin) == true
clientIdWeb.equals(clientIdAdmin) == false
web.getRegistrationId() != admin.getRegistrationId()
~~~

**Không log `getClientSecret()` hoặc raw tokens.**

### 26.1. Shared configuration không đồng nghĩa cùng Java reference

Test:

~~~java
assertSame(web.getProviderDetails(), admin.getProviderDetails());
~~~

không phải điều kiện đúng về mặt chức năng. Spring có thể dựng ProviderDetails objects khác nhau từ cùng metadata. Hãy kiểm tra issuer/endpoints và client-specific fields, không kiểm tra object identity.

## 27. Test cấu hình Spring Boot bằng JUnit 5

~~~java
package com.example.portal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class SharedProviderRegistrationTest {

    @Autowired
    ClientRegistrationRepository registrations;

    @Test
    void twoRegistrationsHaveSharedIssuerButDistinctClients() {
        ClientRegistration web =
            registrations.findByRegistrationId("portal-web");

        ClientRegistration admin =
            registrations.findByRegistrationId("portal-admin");

        assertNotNull(web);
        assertNotNull(admin);
        assertNotEquals(
            web.getRegistrationId(), admin.getRegistrationId());
        assertEquals(
            web.getProviderDetails().getIssuerUri(),
            admin.getProviderDetails().getIssuerUri());
        assertNotEquals(web.getClientId(), admin.getClientId());

        assertTrue(web.getScopes().contains("openid"));
        assertTrue(admin.getScopes().contains("openid"));
        assertTrue(web.getScopes().contains("orders.read"));
        assertTrue(admin.getScopes().contains("admin.read"));

        assertEquals(
            "{baseUrl}/login/oauth2/code/{registrationId}",
            web.getRedirectUri());
        assertEquals(
            "{baseUrl}/login/oauth2/code/{registrationId}",
            admin.getRedirectUri());
    }
}
~~~

Đây là một integration test **configuration**. Nếu dùng `issuer-uri`, Spring Boot có thể thực hiện discovery qua network khi tạo registrations. Cần cấu hình mock/fake IdP metadata trong test profile; **không buộc unit/integration test phải gọi production IdP**.

### 27.1. Test login entrypoints

Với MockMvc đã bật Spring Security:

~~~java
@Test
void webEntryPointRedirectsForWebClient() throws Exception {
    mvc.perform(get("/oauth2/authorization/portal-web"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            "Location",
            org.hamcrest.Matchers.containsString(
                "client_id=employee-portal-web")));
}
~~~

Đây là **test fragment**, giả sử `mvc`, registrations và test IdP đã thiết lập. Test thêm admin entrypoint, actual redirect URI, requested scopes và state; không dừng ở một substring.

### 27.2. Test callback correlation

~~~text
Given:
  Bắt đầu portal-web authorization.
  State W1 và clientId WEB đã được lưu.

When:
  Callback dùng code/state WEB nhưng vào admin callback path.

Then:
  Không chấp nhận như authorization của ADMIN.
~~~

Sử dụng fake OP/test tokens, không bỏ state/nonce/PKCE validation để làm happy-path test.

## 28. Test tokens không bị dùng chéo

Fake manager trả:

~~~text
portal-web -> TEST_WEB_TOKEN
portal-admin -> TEST_ADMIN_TOKEN
~~~

Với mock HTTP server hoặc fake WebClient ExchangeFunction, xác minh:

1. Orders API nhận `Bearer TEST_WEB_TOKEN`.
2. Admin API nhận `Bearer TEST_ADMIN_TOKEN`.
3. Không gửi TEST_ADMIN_TOKEN cho Orders API.
4. Không gửi TEST_WEB_TOKEN cho Admin API.
5. Không gửi bất kỳ token nào tới host ngoài allowlist.
6. Không log token values, refresh tokens hoặc client secrets.

### 28.1. Test lỗi 401/403

~~~text
Admin API -> 401 Bearer invalid_token
  => cleanup portal-admin authorized client theo policy.

Orders API -> 200 OK
  => portal-web client không bị xóa.
~~~

Không xóa mọi authorized clients có provider `company-oidc` khi chỉ một token bị từ chối.

### 28.2. Test quyền admin server-side

Một test bảo mật cần chứng minh:

- User không có quyền ADMIN vẫn không vào admin endpoint dù login qua portal-admin.
- User có quyền nhưng chưa authorize admin client phải đi đúng consent/authorization flow.
- API kiểm tra audience/scope/resource permission thực tế.
- User thuộc tenant khác không đọc được admin data chỉ bằng cách đổi registration ID.

**Authentication và authorization là hai tầng khác nhau.**

## 29. Observability và vận hành

Khi nhiều registrations dùng cùng OP, metrics nên phân biệt:

~~~text
oauth.client.authorization.failure{registration=portal-web}
oauth.client.authorization.failure{registration=portal-admin}
oauth.client.refresh.attempt{registration=portal-web}
oauth.client.refresh.attempt{registration=portal-admin}
oauth.provider.discovery.failure{provider=company-oidc}
oauth.resource.invalid_token{registration=portal-admin}
~~~

Tên metric ở đây **chỉ là ví dụ**, không phải Spring Boot tự phát tất cả.

### 29.1. Phân biệt lỗi chung với lỗi riêng

| Lỗi | Thường xem tầng nào trước? |
|---|---|
| Cả web/admin timeout issuer discovery | OP/network/proxy/TLS chung |
| Chỉ admin `invalid_client` | Client ID/secret/method admin |
| Chỉ web `redirect_uri_mismatch` | Web redirect URI / IdP record |
| Cả hai callback không thấy state | Cookie, HttpSession, shared session store |
| Chỉ Admin API trả 403 | Scope/role/resource authorization |
| Web token gửi sang Admin API | Registration selection/HTTP client wiring |
| Hai registrations có sub khác nhau | Pairwise subject policy |
| Chỉ admin refresh thất bại | RT/admin client-specific policy |

Nếu một registration gặp lỗi, **không sửa issuer chung hoặc xóa mọi tokens** khi chưa tìm nguyên nhân.

### 29.2. Logging an toàn

Có thể log registration ID, provider alias, error code, status code, correlation ID và latency. Không log:

~~~text
access_token=<actual-token>
refresh_token=<actual-token>
client_secret=<actual-secret>
authorization_code=<actual-code>
Cookie: JSESSIONID=<actual-session>
Authorization: Bearer <actual-token>
~~~

Không lưu raw token/JWT trong metric labels hoặc distributed tracing attributes.

## 30. Troubleshooting

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| Spring Boot không khởi động | Provider key thiếu hoặc discovery lỗi | Kiểm tra `registration.*.provider` và `provider.company-oidc` |
| Chỉ portal-admin invalid_client | Admin ID/secret sai | Đối chiếu admin client record với secret manager |
| Chỉ web redirect_uri_mismatch | Redirect URI sai ở WEB client | Kiểm tra expansion, public URL và IdP |
| Start login web nhưng vào admin callback | Tùy biến redirect matcher sai | Kiểm tra state, registrationId và callback path |
| Cả hai login fail sau proxy deployment | Forwarded scheme/host/cookie sai | Kiểm tra ingress trusted headers, HTTPS |
| User click Admin Console nhưng bị 403 | Chưa có quyền admin | Kiểm tra RBAC, scopes, tenant và Resource Server |
| Cùng user có hai sub khác nhau | OP pairwise subjects | Kiểm tra sector policy, không auto-link email |
| WebClient gửi token của client khác | Default client/registration attribute sai | Chỉ định clientRegistrationId và tách HTTP clients |
| Token được cấp nhưng API 401 | Sai audience/issuer, token expired/revoked | Kiểm tra Bearer error và token lifecycle |
| OAuth2AuthorizedClient không tìm thấy sau login | Storage key/principal khác hoặc session mất | Kiểm tra repo/service, registration/principal |
| Lỗi chỉ khi chạy nhiều replicas | Local session/token storage | Shared store/routing strategy phù hợp |
| Logout nhưng OP vẫn SSO | Local logout không phải OP logout | Thiết kế RP-initiated logout/revocation |
| Reports job yêu cầu HttpServletRequest | Dùng Servlet request manager ngoài web context | Chuyển sang service-based manager |
| Refresh admin fail nhưng web OK | RT-A/client-specific policy | Không dùng RT-W thay thế |
| Discovery có issuer khác config | Sai trust issuer | Sửa provider config, không bỏ validation |

### 30.1. Cây quyết định

~~~text
Login/API lỗi với nhiều registrations
    |
    v
Registration ID được chọn đúng?
    |-- Không -> Sửa login link/HTTP request attribute.
    |
    v
ClientRegistration tồn tại trong repository?
    |-- Không -> Sửa YAML/binding.
    |
    v
Provider key/issuer metadata đúng?
    |-- Không -> Sửa shared provider/trust settings.
    |
    v
Client ID/secret/redirect/scopes khớp IdP?
    |-- Không -> Sửa riêng client registration tương ứng.
    |
    v
Callback state/session/nonce/PKCE hợp lệ?
    |-- Không -> Kiểm tra cookies/session/concurrency.
    |
    v
Authorized client của registration + principal có đúng?
    |-- Không -> Sửa storage/manager selection.
    |
    v
Token audience/scope và Resource Server permission đúng?
    |-- Không -> Sửa token/client policy hoặc RBAC.
    |
    v
Kiểm tra refresh, expiry, failure handlers và logs.
~~~

## 31. Các anti-pattern cần tránh

**1. Nhân bản provider config cho từng registration dù issuer giống nhau.** Dễ drift metadata và khó bảo trì.

**2. Coi cùng provider là cùng client ID/secret.** Mỗi client record có credentials riêng.

**3. Dùng provider alias trong login URL.** Login endpoint mặc định chọn `registrationId`.

**4. Tưởng redirect URI template giống là URI thực giống.** `{registrationId}` tạo callback khác nhau.

**5. Cho WEB token gọi Admin API.** Resource Server kiểm tra đúng audience/scope/role.

**6. Cache token theo issuer thay vì registration + principal.** Có nguy cơ dùng chéo hoặc ghi đè.

**7. Dùng client_credentials như user token.** Machine identity không có user consent/authentication.

**8. Bấm nút Admin Console là có ROLE_ADMIN.** OAuth client selection không thay RBAC.

**9. Auto-link user accounts chỉ bằng email.** Pairwise sub có thể khác; email không bất biến.

**10. Bỏ state/nonce/PKCE do login chung OP.** Mỗi authorization request cần correlation.

**11. Xóa tất cả tokens của issuer vì một invalid_grant.** Cleanup đúng registration/principal.

**12. Tự đính access token vào mọi outgoing HTTP host.** Bearer token có thể bị exfiltrate.

**13. Gộp nhiều realms cùng vendor vào một issuer.** Issuer URI là trust boundary.

**14. Hard-code secret/refresh token.** Cần secret manager, rotation và logging an toàn.

**15. Coi OP SSO session là bằng chứng user có quyền mọi ứng dụng.** SSO khác authorization.

## 32. Bài tập thực hành

### Bài 1 — Bao nhiêu registrations?

~~~yaml
registration:
  web:
    provider: corp
  admin:
    provider: corp
  reports:
    provider: corp
provider:
  corp:
    issuer-uri: https://idp.example.test
~~~

**Hỏi:** Có mấy registrations và provider configurations?

**Đáp án:** Ba ClientRegistration IDs (`web`, `admin`, `reports`) và một provider alias `corp`. Mỗi registration còn cần thông tin client/grant hợp lệ.

### Bài 2 — Login URL nào?

~~~text
registrationId = portal-web
provider = company-oidc
~~~

**Hỏi:** URL khởi tạo login mặc định?

**Đáp án:** `/oauth2/authorization/portal-web`, không phải `/oauth2/authorization/company-oidc`.

### Bài 3 — Callback URLs

Hai registrations dùng template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

**Hỏi:** Callback URI có giống nhau?

**Đáp án:** Không; với baseUrl `https://portal.example.com`, suffix là `/portal-web` và `/portal-admin`. Mỗi URI thực phải được đăng ký đúng tại IdP.

### Bài 4 — Token dùng chéo?

WEB token có scope `orders.read`, ADMIN token có `admin.read`. Cùng issuer.

**Hỏi:** Gửi WEB token cho Admin API có hợp lệ không?

**Đáp án:** Không mặc định. Resource Server còn kiểm tra audience, scopes và permissions.

### Bài 5 — OP không hỏi mật khẩu lần hai

User login web, sau đó admin login được OP SSO tự động.

**Hỏi:** Có nghĩa đã có quyền admin?

**Đáp án:** Không. OP tái sử dụng SSO session, nhưng ứng dụng vẫn phải kiểm tra RBAC/MFA/authentication assurance theo policy.

### Bài 6 — Pairwise sub khác nhau

~~~text
WEB: iss=X, sub=W1, email=a@example.com
ADMIN: iss=X, sub=A9, email=a@example.com
~~~

**Hỏi:** Có tự nối thành một user không?

**Đáp án:** Không. Có thể là pairwise identifiers; cần cơ chế account linking đáng tin, không nối bằng email đơn thuần.

### Bài 7 — Hai issuer realms

~~~text
https://id.example.test/realms/a
https://id.example.test/realms/b
~~~

**Hỏi:** Có dùng một provider config không?

**Đáp án:** Không nếu metadata xác nhận đây là hai issuers khác nhau. Phải tách trust/config.

### Bài 8 — Refresh admin invalid_grant

RT-A bị từ chối; RT-W vẫn hợp lệ.

**Hỏi:** Có xóa cả WEB và ADMIN authorized clients không?

**Đáp án:** Không. Xử lý đúng client registration và principal có token bị lỗi.

### Bài 9 — Job và cùng provider

Thêm `reports-service` với `client_credentials` cùng provider.

**Hỏi:** Job có cần login của browser không?

**Đáp án:** Không. Dùng service-based manager và machine credential đúng policy; token không đại diện user.

### Bài 10 — assertSame ProviderDetails?

~~~java
assertSame(
    web.getProviderDetails(),
    admin.getProviderDetails()
);
~~~

**Hỏi:** Có phải test đúng “provider chung”?

**Đáp án:** Không. Nên so sánh issuer/endpoints theo security contract; không đòi Java object references giống hệt nhau.

## 33. Checklist triển khai

| Kiểm tra | Yêu cầu |
|---|---|
| Mỗi registration có ID riêng? | WEB và ADMIN riêng |
| Cả hai tham chiếu đúng provider alias? | `company-oidc` |
| Issuer thực sự là một? | Kiểm tra OIDC metadata |
| Client IDs/secrets độc lập? | Theo IdP records |
| Client authentication methods hợp lệ? | Theo từng client |
| Scopes/grants được phép? | Theo consent/IAM policy |
| Redirect URI template có expansion đúng? | Exact registered URIs |
| Login URLs dùng registration ID? | `/oauth2/authorization/{registrationId}` |
| Callback correlation đúng? | State/nonce/PKCE |
| Cookie/session/proxy đúng? | HTTPS/Secure/HttpOnly/SameSite |
| ID Token audience/issuer được xác minh? | Theo client ID/issuer |
| Tokens lưu theo key đúng? | Registration + trusted principal |
| Refresh tokens không dùng chéo? | Không |
| Resource Server xác minh token? | Audience, scopes, permissions |
| Admin RBAC thực hiện server-side? | Có |
| Pairwise sub có được xử lý? | Không nối email mù |
| SSO/Portal session/token tách biệt? | Có |
| Multi-tenant issuers tách đúng? | Có |
| Logout/revoke cleanup có phạm vi? | Có |
| Multi-node session/token store phù hợp? | Có |
| WebClient/RestClient giới hạn token destinations? | Có |
| Test login entrypoints và client IDs? | Có |
| Test token isolation và 401/403? | Có |
| Log có che credentials? | Có |

## 34. Tổng kết

Trong **Spring Security OAuth 2.0/OIDC Client**, **nhiều registrations dùng chung một provider** là mô hình hợp lý khi một Authorization Server/OpenID Provider cấp dịch vụ cho nhiều OAuth clients của tổ chức. Ta chỉ cần một:

~~~yaml
provider:
  company-oidc:
    issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
~~~

và các registration độc lập:

~~~yaml
registration:
  portal-web:
    provider: company-oidc
    client-id: ${PORTAL_WEB_CLIENT_ID}
  portal-admin:
    provider: company-oidc
    client-id: ${PORTAL_ADMIN_CLIENT_ID}
~~~

Khi đó issuer/authorization/token/JWK metadata có thể dùng chung, nhưng **client ID, secret, grant, scopes, redirect URI, authorization requests, access/refresh tokens và policies vẫn là của từng registration**. Login dùng **registration ID**; callback phải khớp đúng request/state; HTTP clients phải chọn đúng authorized client; Resource Server kiểm tra audience/scope/resource permissions.

**Cùng provider không tự có nghĩa cùng token, quyền, browser Authentication hay subject identifier trong mọi trường hợp.** OP SSO có thể giúp đăng nhập thuận tiện hơn, nhưng không thay RBAC/MFA; pairwise OIDC `sub` có thể khác nhau giữa clients; token cleanup phải gắn đúng registration/principal. Thiết kế đúng là **chia sẻ metadata theo issuer đáng tin cậy**, đồng thời **giữ độc lập OAuth client identity, token lifecycle và business authorization**.
