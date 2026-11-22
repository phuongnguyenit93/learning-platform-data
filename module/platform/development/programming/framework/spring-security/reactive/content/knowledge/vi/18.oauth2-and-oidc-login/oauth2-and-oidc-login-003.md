# ClientRegistration, provider và ReactiveClientRegistrationRepository trong Spring Security WebFlux

> **Phạm vi:** Spring Security 6.x, Spring WebFlux, Spring Boot 3.3.x, Java 17+, đăng nhập OAuth 2.0 / OpenID Connect (OIDC) bằng Authorization Code. Bài giải thích ba thành phần thường bị nhầm lẫn: `ClientRegistration` mô tả cấu hình client, `provider` mô tả Authorization Server/Identity Provider, và `ReactiveClientRegistrationRepository` giúp WebFlux tra cứu cấu hình đó. Mã dùng Spring Boot 3.3.13 để minh họa API; dự án production nên chọn bản được duy trì và vá lỗi bảo mật.

## 1. Vấn đề thực tế

Một portal nội bộ muốn cho nhân viên đăng nhập bằng Identity Provider (IdP) của doanh nghiệp. Trước khi cho phép một browser được chuyển sang IdP, ứng dụng phải biết:

1. **Ứng dụng là client nào tại IdP?** Client ID, cách xác thực client, redirect URI, scopes.
2. **IdP nào đang phục vụ client?** Authorization endpoint, token endpoint, issuer, JWKS, UserInfo endpoint.
3. **Spring Security tìm cấu hình đó ở đâu?** Repository lookup theo `registrationId`.

```text
Browser                  Spring WebFlux                         OIDC IdP
   |                           |                                  |
   | GET /private/me           |                                  |
   |-------------------------->| chưa có Authentication            |
   |<--------------------------| redirect vào login flow         |
   |                           |                                  |
   | GET /oauth2/authorization/corporate                          |
   |-------------------------->|                                  |
   |                ReactiveClientRegistrationRepository         |
   |                      findByRegistrationId("corporate")      |
   |                           |                                  |
   |<--------------------------| 302 Location: IdP /authorize    |
   |---------------------------- GET /authorize?client_id=... -->|
   |                           |                          đăng nhập
   |<--------------------------- redirect ?code=...&state=... ---|
   | GET /login/oauth2/code/corporate                             |
   |-------------------------->| đối chiếu state, đổi code/token |
   |                           |------------------------------->  |
   |                           |<-------------------------------  |
   |                           | xác minh ID token / principal   |
   |<--------------------------| lưu SecurityContext/session     |
```

**Một `ClientRegistration` được tạo thành công không có nghĩa người dùng đã đăng nhập.** Nó chỉ là cấu hình để khởi tạo một giao thức xác thực. IdP phải tồn tại, callback đúng, tokens hợp lệ và Spring Security phải tạo Authentication.

## 2. Các khái niệm nền tảng

| Thuật ngữ | Ý nghĩa | Không đồng nghĩa với |
|---|---|---|
| **OAuth2 Client** | Ứng dụng của bạn cần login hoặc gọi API bên ngoài | Resource Server nhận bearer token |
| **Authorization Server** | Hệ thống cấp authorization code và token | ClientRegistrationRepository |
| **Identity Provider / OIDC Provider** | Dịch vụ xác thực end-user theo OpenID Connect | User trong database ứng dụng |
| **Resource Owner / End-user** | Người dùng thực hiện login/consent | Client ứng dụng |
| **ClientRegistration** | Một client cấu hình ở ứng dụng: ID, secret, grant, scopes, redirect, endpoints | Phiên đăng nhập hoặc access token đã cấp |
| **registrationId** | Khóa nội bộ do ứng dụng đặt để tìm registration | client_id do IdP cấp |
| **providerId** | Khóa nhóm endpoint/issuer trong `spring.security.oauth2.client.provider` | registrationId bắt buộc phải giống |
| **clientId** | Mã định danh ứng dụng được IdP cấp | clientSecret |
| **OAuth2AuthorizedClient** | Thông tin client đã được ủy quyền cho một principal, bao gồm token | Chỉ là ClientRegistration |
| **OIDC ID Token** | JWT khẳng định thông tin đăng nhập của end-user đối với client | OAuth2 access token cấp quyền cho API |

OAuth2 cung cấp cơ chế **ủy quyền**. OIDC thêm một lớp **xác thực end-user** dựa trên ID Token, issuer, subject và các kiểm tra protocol. Trong Spring Security, `scope` chứa `openid` là tín hiệu quan trọng để kích hoạt xử lý OIDC thay vì OAuth2 Login chỉ dùng OAuth2 UserInfo.

Không tự đọc `id_token` bằng Base64 rồi dùng `sub` làm bằng chứng login: token cần được kiểm chữ ký, issuer, audience, hạn dùng, nonce và các điều kiện khác theo OIDC.

### Ba định danh minh họa

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:                       # registrationId
            provider: enterprise-idp       # providerId
            client-id: portal-web-client   # clientId
        provider:
          enterprise-idp:
            issuer-uri: https://login.example.com/realms/enterprise
```

Đoạn trên **chỉ minh họa quan hệ ID**, chưa đủ credentials cho triển khai. Trong ví dụ này:

- `corporate` tạo đường dẫn bắt đầu `/oauth2/authorization/corporate`.
- `enterprise-idp` chọn khối provider.
- `portal-web-client` được gửi dưới tên tham số OAuth2 `client_id` đến IdP.

Không thay đổi `registrationId` rồi quên đường dẫn callback; cũng không giả định một tên trong ba tên trên phải bằng hai tên còn lại.

## 3. ClientRegistration giữ những thông tin nào?

`org.springframework.security.oauth2.client.registration.ClientRegistration` là một Java object bất biến ở cấp cấu hình, đại diện cho **một client đã đăng ký với provider**.

| Trường | Vai trò | Ví dụ |
|---|---|---|
| `getRegistrationId()` | Tên local registration | `corporate` |
| `getClientId()` | Client ID được cấp | `portal-client` |
| `getClientSecret()` | Bí mật client confidential | Secret manager/environment |
| `getClientAuthenticationMethod()` | Cách client xác thực ở token endpoint | `client_secret_basic` |
| `getAuthorizationGrantType()` | OAuth2 grant | `authorization_code` |
| `getRedirectUri()` | Callback URI/template | `{baseUrl}/login/oauth2/code/{registrationId}` |
| `getScopes()` | Những scope yêu cầu | `openid`, `profile`, `email` |
| `getClientName()` | Tên hiển thị trên login chooser | `Corporate SSO` |
| `getProviderDetails().getAuthorizationUri()` | Browser được điều hướng tới đây để login | `https://idp.example/authorize` |
| `getProviderDetails().getTokenUri()` | Backend trao đổi code lấy token tại đây | `https://idp.example/token` |
| `getProviderDetails().getJwkSetUri()` | Public keys để verify JWT | `https://idp.example/jwks` |
| `getProviderDetails().getUserInfoEndpoint()` | Metadata về UserInfo endpoint | `https://idp.example/userinfo` |
| `getProviderDetails().getIssuerUri()` | OIDC/OAuth issuer identifier | `https://idp.example/realms/corp` |

**Đừng serialize trực tiếp `ClientRegistration` thành JSON** từ một debug endpoint: object có thể chứa `clientSecret` và cấu hình nhạy cảm. Nếu cần UI cho danh sách nhà cung cấp login, chỉ đưa ra một allowlist gồm `registrationId` và tên hiển thị an toàn.

### Registration cho login và registration cho outbound API

Một `ClientRegistration` có thể dùng cho OAuth2 Login hoặc OAuth2 Client gọi protected API. Nhưng:

- **`oauth2Login()`**: đăng nhập end-user qua Authorization Code, tạo authenticated principal/session.
- **`oauth2Client()`**: quản lý authorized client và truy cập outbound protected API bằng access token.
- **`oauth2ResourceServer()`**: bảo vệ inbound API của bạn bằng Bearer JWT/opaque token, không cần client registration để xác minh JWT trong cấu hình đơn giản.

Không nghĩ thêm `spring-boot-starter-oauth2-client` tự biến API thành resource server, hay thêm `oauth2ResourceServer` sẽ tạo OIDC browser login page.

## 4. Provider: issuer, authorization URI, token URI và JWKS

Một provider mô tả **phía nhà cung cấp** mà registration sẽ gọi.

```text
provider "enterprise-idp"
  |
  +-- issuer-uri         -> định danh IdP/issuer dùng để xác minh token
  +-- authorization-uri  -> đích browser 302 khi login
  +-- token-uri          -> backend POST authorization code để lấy tokens
  +-- jwk-set-uri        -> bộ public keys verify ID Token/JWT
  +-- user-info-uri      -> endpoint lấy thông tin user khi phù hợp
  +-- user-name-attribute -> claim định danh từ UserInfo, thường "sub"
```

**Issuer không nhất thiết trùng authorization URI.** Ví dụ issuer là `https://login.example.com/realms/acme` nhưng authorization URI có thể là `https://login.example.com/realms/acme/protocol/openid-connect/auth`.

Một provider có thể phục vụ **nhiều** registrations: ứng dụng quản trị, ứng dụng customer portal, hoặc các client có redirect/scopes khác nhau. Khi viết `registration.portal.provider: enterprise-idp`, Spring Boot trỏ registration đó đến endpoint của provider `enterprise-idp`.

### 4.1 Spring Boot ánh xạ YAML thành ClientRegistration

Tiền tố properties:

```text
spring.security.oauth2.client
  registration
    <registrationId>
      provider
      client-id
      client-secret
      client-name
      client-authentication-method
      authorization-grant-type
      redirect-uri
      scope
  provider
    <providerId>
      issuer-uri
      authorization-uri
      token-uri
      jwk-set-uri
      user-info-uri
      user-info-authentication-method
      user-name-attribute
```

Nếu `provider` không được chỉ định và registration ID trùng khóa provider hoặc tên provider mặc định của Spring Boot, Boot có thể suy ra một số cấu hình. Với provider custom, nên khai báo `provider: some-id` tường minh.

### 4.2 Cấu hình IdP hỗ trợ discovery

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: enterprise-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-name: Corporate SSO
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          enterprise-idp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Đây là mẫu cho **IdP thật**: phải cung cấp ba environment variables và đăng ký callback đúng phía IdP. Với `issuer-uri`, Spring Security/Spring Boot có thể thực hiện OIDC Provider Metadata/Authorization Server Metadata discovery và lấy authorization/token/JWKS/UserInfo endpoints.

**Điểm vận hành:** discovery có thể gọi HTTP tới IdP khi tạo bean/configuration. Nếu IdP không có DNS/TLS đúng hoặc bị outage, ứng dụng có thể không khởi động được tùy version và cách cấu hình. Đừng trộn issuer `.invalid` vào cấu hình thật rồi mặc định network sẽ không bị gọi.

### 4.3 Cấu hình endpoint tường minh

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: enterprise-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          enterprise-idp:
            authorization-uri: https://idp.example.com/oauth2/authorize
            token-uri: https://idp.example.com/oauth2/token
            jwk-set-uri: https://idp.example.com/oauth2/jwks
            user-info-uri: https://idp.example.com/userinfo
            user-name-attribute: sub
```

Các endpoint ở trên là **địa chỉ ví dụ**, phải thay theo tài liệu IdP. Cách này không cần discovery để dựng registration, nhưng bạn chịu trách nhiệm cập nhật endpoint và kiểm đúng issuer/trust metadata. Trong production OIDC, cần chắc chắn ID Token được validate theo chuẩn; cung cấp vài URL không phải lý do bỏ `iss`, `aud`, signature/nonce.

**Không cấu hình metadata/endpoint mâu thuẫn nhau.** Nếu dùng issuer discovery, ưu tiên nguồn metadata IdP đáng tin; nếu override một endpoint, phải kiểm thử token exchange, key rotation và issuer validation.

### 4.4 ClientRegistrations helper

`org.springframework.security.oauth2.client.registration.ClientRegistrations` có các helper:

```java
ClientRegistration registration = ClientRegistrations
    .fromIssuerLocation("https://idp.example.com/realms/acme")
    .registrationId("corporate")
    .clientId(System.getenv("OIDC_CLIENT_ID"))
    .clientSecret(System.getenv("OIDC_CLIENT_SECRET"))
    .build();
```

Đây là **đoạn code minh họa cần imports và IdP thật**, không phải nội dung của project chạy offline ở mục 9. `fromIssuerLocation` dùng network metadata discovery và không phải API nên gọi mỗi HTTP request trên Netty event loop. `fromOidcIssuerLocation` là biến thể ưu tiên OIDC Provider Configuration.

**Cảnh báo SSRF:** issuer URI phải lấy từ cấu hình/allowlist đáng tin; không bao giờ ghép URI dựa trên query/header do Internet client tự gửi rồi gọi `fromIssuerLocation`. Nếu hệ thống nhiều tenant, ánh xạ tenant sang issuer từ database đáng tin, có validation và quyền cấu hình rõ.

## 5. ReactiveClientRegistrationRepository

Trong Spring Security WebFlux:

```java
package org.springframework.security.oauth2.client.registration;

public interface ReactiveClientRegistrationRepository {
    Mono<ClientRegistration> findByRegistrationId(String registrationId);
}
```

Đây là **signature rút gọn để giải thích**, interface đã tồn tại trong Spring Security, không tạo file mới trùng tên.

- `findByRegistrationId("corporate")` phát cấu hình OAuth2/OIDC client.
- Kiểu trả về là `Mono<ClientRegistration>`, phù hợp WebFlux.
- Với `InMemoryReactiveClientRegistrationRepository`, một ID không có cấu hình thường cho publisher **hoàn thành rỗng**, không tự chọn client khác.
- Repository giữ *cấu hình* client, không giữ user session, OAuth2 Authorization Code, access token hay refresh token đã cấp.

### 5.1 WebFlux khác Servlet

| Chủ đề | Reactive/WebFlux | Servlet/MVC |
|---|---|---|
| Client registrations | `ReactiveClientRegistrationRepository` | `ClientRegistrationRepository` |
| Lookup | `Mono<ClientRegistration>` | `ClientRegistration` trả trực tiếp |
| In-memory repository | `InMemoryReactiveClientRegistrationRepository` | `InMemoryClientRegistrationRepository` |
| Security DSL | `ServerHttpSecurity` | `HttpSecurity` |
| Security chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Authentication context | Reactor Context và reactive persistence | Servlet SecurityContextHolder/filter |
| Request/response | `ServerWebExchange`/WebFilter | Servlet API |

**Không** import `InMemoryClientRegistrationRepository` vào reactive security config rồi hy vọng `oauth2Login` tự chuyển thành reactive. Tên gần giống nhưng đây là hai API khác nhau.

### 5.2 Spring Boot tự tạo bean

Với dependency `spring-boot-starter-oauth2-client` và cấu hình `spring.security.oauth2.client.registration.*` hợp lệ, auto-configuration của Boot trong ứng dụng reactive tạo một `ReactiveClientRegistrationRepository` (thường là `InMemoryReactiveClientRegistrationRepository`) từ các `ClientRegistration` được bind từ properties.

Nếu bạn khai báo chính bean repository thủ công, auto-configuration có thể back off; **đừng kỳ vọng hai danh sách client được tự gộp**. Chọn một cơ chế tạo nguồn client rồi test chính bean thực tế.

### 5.3 InMemoryReactiveClientRegistrationRepository và Iterable

`InMemoryReactiveClientRegistrationRepository` còn triển khai `Iterable<ClientRegistration>`. Điều này hữu ích vì trang `/login` mặc định do `LoginPageGeneratingWebFilter` tạo có thể liệt kê provider links, chẳng hạn:

```html
<a href="/oauth2/authorization/corporate">Corporate SSO</a>
```

Một custom `ReactiveClientRegistrationRepository` **chỉ** implement method `findByRegistrationId` không mặc nhiên triển khai `Iterable`; nếu cần trang login tự sinh liệt kê client, hãy đáp ứng yêu cầu Iterable hoặc tự tạo một login page hợp đồng an toàn.

### 5.4 Đọc repository trong code

```java
public Mono<String> displayName(String id) {
    return registrations.findByRegistrationId(id)
        .map(ClientRegistration::getClientName)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Unknown registration")));
}
```

Đây là method minh họa thiếu class/import/field. Trong WebFlux, không gọi `block()` từ request handler để lấy cấu hình. Nếu repository custom gọi JDBC/JPA đồng bộ, cần boundary `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` có giới hạn và timeout hoặc dùng backend reactive.

## 6. Những repository “na ná” nhưng khác trách nhiệm

| Thành phần | Lưu/truy xuất điều gì? | Có phải ClientRegistration không? |
|---|---|---|
| `ReactiveClientRegistrationRepository` | Danh sách cấu hình client và provider | **Đúng** |
| `ReactiveOAuth2AuthorizedClientService` | `OAuth2AuthorizedClient` với principal và token đã được cấp | Không |
| `ServerOAuth2AuthorizedClientRepository` | Authorized client trong ngữ cảnh `ServerWebExchange`/principal | Không |
| `ServerSecurityContextRepository` | SecurityContext/Authentication có thể qua WebSession | Không |
| `ServerAuthorizationRequestRepository` | OAuth2 authorization request/state cho callback, theo cơ chế flow | Không |
| `ReactiveJwtDecoder` | Kiểm JWT khi protocol cần | Không |

**`ClientRegistration` không có nghĩa đã nhận được access token.** `OAuth2AuthorizedClient` chỉ xuất hiện sau flow phù hợp; nó gắn với registration và principal, có token nhạy cảm và cơ chế lưu/thu hồi riêng.

Không hiển thị `ReactiveOAuth2AuthorizedClientService` hoặc nội dung token vào debug JSON. Những object này có thể chứa access/refresh tokens hoặc thông tin có giá trị truy cập tài nguyên.

## 7. Các endpoint mặc định của OAuth2/OIDC login

| URL | Vai trò |
|---|---|
| `GET /login` | Trang login được Spring Security sinh khi được cấu hình phù hợp |
| `GET /oauth2/authorization/{registrationId}` | Khởi tạo authorization request sang IdP |
| `GET /login/oauth2/code/{registrationId}` | Callback nhận `code`, `state` từ IdP |
| `provider.authorization-uri` | Endpoint IdP cho browser login/consent |
| `provider.token-uri` | Backend trao đổi code để nhận tokens |
| `provider.jwk-set-uri` | JWKS phục vụ kiểm chữ ký token |
| `provider.user-info-uri` | UserInfo claims khi được sử dụng |

### 7.1 Luồng bắt đầu login

1. User vào route được bảo vệ hoặc nhấp `/oauth2/authorization/corporate`.
2. Spring lấy `ClientRegistration` theo `registrationId` từ repository reactive.
3. Tạo authorization request với `client_id`, `response_type=code`, `redirect_uri`, `scope` và một giá trị `state` khó đoán.
4. Với OIDC có `nonce`; với PKCE có `code_challenge` theo client settings/flow.
5. Correlation data (state, metadata cần đối chiếu) được lưu bằng cơ chế repository, thường cần WebSession.
6. Browser nhận HTTP 302 tới authorization endpoint của IdP.

**Không gửi `client_secret` trong authorization URL**. Secret confidential client được dùng ở token endpoint, không phải input gắn URL có thể bị log qua browser.

### 7.2 Callback và token exchange

1. IdP redirect browser về `/login/oauth2/code/corporate?code=...&state=...`.
2. Spring Security so `state` với authorization request đã lưu; state không khớp phải bị từ chối.
3. Spring gửi code/token request tới token endpoint với client authentication phù hợp, kèm PKCE verifier nếu flow sử dụng.
4. Với OIDC: validate ID Token signature/JWKS, `iss`, `aud`, thời hạn, nonce và điều kiện protocol; có thể đọc UserInfo tùy provider/scopes.
5. Tạo Authentication từ principal đã xác minh, lưu SecurityContext/session theo cấu hình, rồi điều hướng người dùng về ứng dụng.

**Không viết controller callback thủ công chỉ kiểm có `code` là cho login.** Phải xác thực state và token theo giao thức; Spring Security cung cấp phần flow này.

### 7.3 state, nonce và PKCE khác nhau

- **state**: gắn authorization response với request đã bắt đầu, giúp ngăn callback/login CSRF.
- **nonce**: đặc biệt quan trọng ở OIDC để liên kết ID Token với authentication request/chống replay.
- **PKCE**: có `code_challenge` trên authorization request và `code_verifier` khi trao đổi code, ngăn một số kiểu code interception. Public client đặc biệt cần PKCE; confidential client cũng có thể dùng theo hỗ trợ của provider.
- **CSRF token HTTP**: dùng với form/cookie để bảo vệ các unsafe methods của ứng dụng. `state` không thay thế mọi CSRF token trong ứng dụng.

Trong cấu hình OAuth2 Login, `client_authentication_method=client_secret_basic` nói **cách ứng dụng xác thực với IdP**, không phải HTTP Basic login của end-user vào portal.

## 8. Vai trò `openid` và OIDC claims

`scope: [openid, profile, email]` biểu thị mong muốn đăng nhập bằng OIDC và xin thêm scope profile/email. Nhà cung cấp có thể trả các claims tùy theo consent và policy.

- `openid`: phân biệt OIDC Login với OAuth2 Login thuần trong Spring Security.
- `sub` (subject): một định danh của end-user tại issuer; thường nên kết hợp **issuer + subject** để ánh xạ sang internal account.
- `email` và `email_verified`: không nên suy từ email thô rằng người dùng đã thuộc đúng tenant.
- `groups` hoặc role claims: chỉ đáng tin sau khi xác minh token/issuer và được map qua policy rõ.
- `id_token`: dành cho client xác thực end-user; **không tự đồng nghĩa access token được chấp nhận ở API khác**.

Trong WebFlux, có thể lấy `Principal` hoặc `OidcUser` sau login. Ví dụ mảnh method OIDC:

```java
@GetMapping("/me/claims")
public Mono<String> claims(
        @AuthenticationPrincipal OidcUser user) {
    if (user == null) {
        return Mono.error(new ResponseStatusException(
            HttpStatus.UNAUTHORIZED));
    }
    return Mono.just(user.getSubject());
}
```

Đây là **mảnh code** cần imports/route security, không phải component đầy đủ. Đừng trả toàn bộ claims/ID token để debug trên một public endpoint; chỉ trả trường cần thiết, có quyền truy cập hợp lệ.

## 9. Demo Spring Boot 3.3/Java 17+: repository tự tạo từ YAML

Bài dùng một provider **giả định** có host `idp.example.invalid`, không có IdP live. Điều này giúp project có thể **khởi động, render login page và tạo authorization redirect** mà không cần discovery network khi startup. **Login hoàn chỉnh qua callback không thể thành công** cho đến khi thay bằng một IdP thực đã đăng ký client.

### 9.1 Cấu trúc

```text
reactive-oidc-registration/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/oidc/OidcApplication.java
  src/main/java/example/oidc/SecurityConfiguration.java
  src/main/java/example/oidc/ProfileController.java
  src/test/java/example/oidc/OidcRegistrationTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'reactive-oidc-registration'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.oidc'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web` của Servlet. Boot starter OAuth2 client là thành phần cần thiết để có bean `ReactiveClientRegistrationRepository` khi dùng WebFlux. `reactor-test` cung cấp `StepVerifier`, các test còn lại dùng `WebTestClient`.

### 9.2 application.yml

**src/main/resources/application.yml**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training-idp
            client-id: training-web-demo
            client-secret: training-placeholder-not-a-secret
            client-name: Training Identity Provider
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          training-idp:
            authorization-uri: https://idp.example.invalid/oauth2/authorize
            token-uri: https://idp.example.invalid/oauth2/token
            jwk-set-uri: https://idp.example.invalid/oauth2/jwks
            user-info-uri: https://idp.example.invalid/userinfo
            user-name-attribute: sub
```

- `training` là registrationId dùng trong URL `/oauth2/authorization/training`.
- `training-idp` là providerId.
- `training-web-demo` là client ID giả định.
- `training-placeholder-not-a-secret` chỉ là **placeholder không phải credential**; chỉ dùng trong demo local.
- Explicit endpoints cho phép tránh discovery khi startup. Không có IdP thật tại `.invalid`, nên callback/token exchange **không thể** hoàn tất.
- Khi chuyển sang IdP thật, thay bằng issuer/endpoint thật, client ID/secret được quản lý bằng secret manager, redirect URI đã đăng ký và HTTPS.

### 9.3 Application

**src/main/java/example/oidc/OidcApplication.java**

```java
package example.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcApplication.class, args);
    }
}
```

### 9.4 SecurityConfiguration

**src/main/java/example/oidc/SecurityConfiguration.java**

```java
package example.oidc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Trong demo **không tự khai báo bean `ReactiveClientRegistrationRepository`**: Spring Boot tạo nó từ `application.yml`. Việc thêm bean cùng loại chỉ để “đảm bảo có repository” có thể làm auto-configuration back off, khiến registration `training` không còn được tải theo cách bạn nghĩ.

`oauth2Login(Customizer.withDefaults())` bật xử lý login reactive. `anyExchange().authenticated()` bảo vệ mọi URL trừ `/public`. Các WebFilter do Spring Security quản lý được phép xử lý `/login`, khởi tạo authorization request và callback; bạn **không cần tự viết controller callback**.

CSRF mặc định vẫn bật; demo chỉ expose GET. Khi thêm POST/PUT/PATCH/DELETE trong ứng dụng session-cookie, áp dụng chính sách CSRF phù hợp, không tắt để sửa lỗi 403.

### 9.5 ProfileController

**src/main/java/example/oidc/ProfileController.java**

```java
package example.oidc;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ProfileController {

    @GetMapping(value = "/public",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping(value = "/private/me",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> currentUser(Principal principal) {
        return Mono.just("signed in: " + principal.getName());
    }
}
```

Route `/private/me` chỉ gọi được sau authentication hợp lệ. Trong OIDC login, `Principal.getName()` có thể là subject hoặc một tên do mapping cấu hình; **không mặc định là email/username nội bộ**. Không dùng chuỗi này trực tiếp để quyết định quyền sở hữu một bản ghi mà chưa có identity mapping chính thức.

### 9.6 Chạy bằng Gradle và curl

```bash
gradle bootRun

# Không cần IdP:
curl -i http://localhost:8080/public

# Chưa login: xem redirect
curl -i -H "Accept: text/html" http://localhost:8080/private/me

# Login page mặc định
curl -i -H "Accept: text/html" http://localhost:8080/login

# Bắt đầu authorization flow, chỉ xem Location, không follow
curl -i http://localhost:8080/oauth2/authorization/training
```

Nếu đã có Gradle Wrapper phù hợp: `./gradlew bootRun`, Windows `gradlew.bat bootRun`. Trong PowerShell, `curl` có thể là alias; dùng `curl.exe` khi cần. Không dùng `curl -L` lúc kiểm 302 vì tự follow sẽ che status redirect ban đầu.

Kết quả dự kiến:

| Request | Kết quả chính |
|---|---|
| `GET /public` | 200, body `public` |
| `GET /private/me` chưa login | 3xx redirect bắt đầu login |
| `GET /login` | 200, trang HTML với link tới `/oauth2/authorization/training` |
| `GET /oauth2/authorization/training` | 302; `Location` bắt đầu bằng `https://idp.example.invalid/oauth2/authorize?...` |
| Browser theo redirect tới IdP giả | Không thể login hoàn chỉnh vì provider không tồn tại |
| Sau khi thay IdP thật và login thành công | Có thể gọi `GET /private/me` và nhận principal name |

Cookie session/state dùng để liên hệ authorization request với callback. **Không đăng state, authorization code, access token, session cookie hay client secret lên logs** để kiểm chứng luồng.

## 10. Kiểm thử WebTestClient và StepVerifier không cần IdP thật

**src/test/java/example/oidc/OidcRegistrationTest.java**

```java
package example.oidc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class OidcRegistrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ReactiveClientRegistrationRepository registrations;

    @Test
    void bootCreatesReactiveRegistration() {
        StepVerifier.create(registrations.findByRegistrationId("training"))
            .assertNext(reg -> {
                assertEquals("training", reg.getRegistrationId());
                assertEquals("training-web-demo", reg.getClientId());
                assertEquals("Training Identity Provider",
                    reg.getClientName());
                assertEquals(
                    "https://idp.example.invalid/oauth2/authorize",
                    reg.getProviderDetails().getAuthorizationUri());
                assertTrue(reg.getScopes().contains("openid"));
            })
            .verifyComplete();
    }

    @Test
    void unknownRegistrationIsEmpty() {
        StepVerifier.create(
            registrations.findByRegistrationId("unknown"))
            .verifyComplete();
    }

    @Test
    void publicRouteIsAvailable() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedRouteBeginsLogin() {
        client.get().uri("/private/me")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void generatedLoginPageOffersRegistrationLink() {
        client.get().uri("/login")
            .accept(MediaType.TEXT_HTML)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .consumeWith(result -> {
                assertNotNull(result.getResponseBody());
                assertTrue(result.getResponseBody()
                    .contains("/oauth2/authorization/training"));
            });
    }

    @Test
    void authorizationRequestRedirectsToConfiguredIdp() {
        var result = client.get()
            .uri("/oauth2/authorization/training")
            .exchange()
            .expectStatus().isFound()
            .returnResult(Void.class);

        String location = result.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);

        URI target = URI.create(location);
        assertEquals("https", target.getScheme());
        assertEquals("idp.example.invalid", target.getHost());
        assertEquals("/oauth2/authorize", target.getPath());
        assertTrue(location.contains("client_id=training-web-demo"));
        assertTrue(location.contains("response_type=code"));
        assertTrue(location.contains("state="));
        assertTrue(location.contains("redirect_uri="));
    }
}
```

**6 test methods** kiểm tra: bean từ YAML, unknown ID, route công khai, redirect khi chưa login, link trang login và URL authorization request. `StepVerifier` xác nhận `Mono<ClientRegistration>` được phát/hoàn thành đúng.

Chạy:

```bash
gradle test
```

**Giới hạn kiểm thử:** các test này **không xác nhận** token exchange, JWKS, ID Token validation, UserInfo hay callback đầy đủ. Để kiểm those bước, cần IdP thật hoặc mock IdP tuân thủ OIDC với authorization endpoint/token endpoint/JWKS và ID Token ký hợp lệ. Test chỉ ở giai đoạn redirect không chứng minh user đã xác thực.

**Chưa chạy build thực tế** trong bài Knowledge này; status/test là kỳ vọng sau khi mã và API được rà soát. Khi chạy trên dependency khác, hãy xem stack trace, security chain và HTTP behavior thực thay vì giả định 302/200 luôn giống mọi cấu hình.

## 11. Tạo repository bean thủ công bằng Java

Thay vì Boot property binding, có thể khai báo một bean:

```java
package example.manual;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.IdTokenClaimNames;

@Configuration(proxyBeanMethods = false)
public class ManualRegistrationConfiguration {

    @Bean
    ReactiveClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration client =
            ClientRegistration.withRegistrationId("corporate")
                .clientId(requiredEnv("OIDC_CLIENT_ID"))
                .clientSecret(requiredEnv("OIDC_CLIENT_SECRET"))
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                    "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .authorizationUri(
                    "https://login.example.com/oauth2/authorize")
                .tokenUri("https://login.example.com/oauth2/token")
                .jwkSetUri("https://login.example.com/oauth2/jwks")
                .userInfoUri("https://login.example.com/userinfo")
                .userNameAttributeName(IdTokenClaimNames.SUB)
                .clientName("Corporate SSO")
                .build();

        return new InMemoryReactiveClientRegistrationRepository(client);
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Missing environment variable: " + key);
        }
        return value;
    }
}
```

**Đây là phương án thay thế**, không dán lớp này vào project mục 9 cùng với YAML registration. Nếu chọn bean manual:

- Dùng các endpoint thực được IdP cung cấp; đừng sử dụng URL giả.
- Cấu hình secrets bằng environment/secret manager.
- Kiểm issuer/JWK/ID Token validation theo protocol khi cấu hình endpoint thủ công.
- Truyền nhiều `ClientRegistration` vào constructor in-memory repository nếu có nhiều client.
- Đảm bảo class được component scanned và `SecurityWebFilterChain` có `oauth2Login`.

Ví dụ phía trên dùng Java 17+ nhưng vẫn cần IdP thực cho login cuối cùng. Đối với môi trường chỉ dùng static repo, đây là cách rõ để xem Builder API. `ClientRegistrations.fromIssuerLocation(...)` là lựa chọn khác khi muốn lấy thông tin provider bằng metadata discovery.

## 12. Nhiều registrations, một provider hoặc nhiều IdP

Ví dụ hai client dùng chung issuer và hai client ID khác nhau:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: corporate
            client-id: ${PORTAL_CLIENT_ID}
            client-secret: ${PORTAL_CLIENT_SECRET}
            scope: [openid, profile, email]
          reporting:
            provider: corporate
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            scope: [openid, profile]
        provider:
          corporate:
            issuer-uri: ${CORPORATE_ISSUER_URI}
```

Các login links tương ứng:

```text
/oauth2/authorization/portal
/oauth2/authorization/reporting
```

Cùng provider có thể cấp scopes khác nhau tùy client; mỗi callback cần đăng ký tại IdP. Nếu hai IdP khác nhau, dùng hai provider blocks khác nhau. Không tạo registration từ URL issuer do người dùng tự nhập khi xử lý login.

### Provider defaults

Spring Boot hỗ trợ defaults của một số provider phổ biến, chẳng hạn Google, GitHub, Facebook, Okta. Ví dụ:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope: [openid, profile, email]
```

Provider defaults chỉ giúp cấu hình endpoint; bạn vẫn phải đăng ký client và redirect URI tại provider. Không giả định mọi IdP custom đều có sẵn defaults.

## 13. Redirect URI, callback và reverse proxy

Một `redirect-uri` thường dùng:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

Ở local, khi người dùng gọi `http://localhost:8080`, callback trở thành:

```text
http://localhost:8080/login/oauth2/code/training
```

Ở production, sau TLS termination:

```text
https://portal.example.com/login/oauth2/code/corporate
```

URI này phải **khớp allowlist phía IdP**, bao gồm scheme/host/path/port theo chính sách IdP. Không cho client tự cung cấp redirect URI từ query param chưa xác minh và không dùng wildcard không kiểm soát.

### Reverse proxy

```text
Browser --HTTPS--> Ingress/Load Balancer --HTTP--> WebFlux Pod
                       |
                Forwarded / X-Forwarded-Proto
```

Nếu WebFlux chỉ thấy HTTP nội bộ, template `{baseUrl}` có thể dựng sai scheme/host, gây `redirect_uri_mismatch`. Khi có proxy đáng tin, Spring Boot hỗ trợ:

```yaml
server:
  forward-headers-strategy: framework
```

**Đây là cấu hình production có điều kiện**, không dùng để “tin” arbitrary `X-Forwarded-Host` từ Internet. Reverse proxy phải loại bỏ/ghi đè forwarded headers do người dùng gửi và giới hạn trusted hops; nếu không attacker có thể ảnh hưởng URL redirect.

Khi tùy chỉnh callback path, phải đồng bộ **registration.redirect-uri**, matcher của OAuth2 Login redirection endpoint WebFlux và URI được IdP allowlist. Không dùng cấu hình `HttpSecurity`/Servlet để sửa callback trong `ServerHttpSecurity`.

## 14. Trạng thái bảo mật và session

Authorization Code login thường cần lưu `state`/authorization request đến lúc callback; trong WebFlux, WebSession và repository liên quan thường được dùng. Những lưu ý:

- Cookie `SESSION` là mã tham chiếu phiên, không chứa client secret.
- Nếu nhiều pod dùng session store in-memory riêng, callback có thể đến pod khác rồi mất `state`; cần shared WebSession store hoặc kiến trúc phù hợp.
- `state`/`nonce`/PKCE không thay thế CSRF protection của POST trong ứng dụng cookie-session.
- Login thành công không tự xác định người dùng là ADMIN; cần map issuer+subject với account/tenant.
- Logout cục bộ có thể không logout khỏi IdP; phải xét OIDC logout nếu product yêu cầu.
- Không đưa access/refresh token vào URL, browser localStorage hay logs.
- Bảo vệ cookie bằng HTTPS/Secure/HttpOnly/SameSite theo threat model, và đổi session ID khi nâng quyền theo policy/framework.

## 15. Vấn đề bảo mật khi dùng custom repository

Một custom `ReactiveClientRegistrationRepository` có thể tải metadata từ database hoặc config service:

```java
public Mono<ClientRegistration> findByRegistrationId(String id) {
    return configurationService.findTrustedRegistration(id)
        .map(this::mapToClientRegistration);
}
```

Đây là pseudocode: `configurationService` phải là trusted backend và `mapToClientRegistration` phải validate trường dữ liệu. **Không lấy `issuer-uri` từ request không tin cậy** và chạy discovery ngay, vì có thể bị SSRF/credential leakage.

Cần giới hạn:

1. Ai được tạo/sửa registration? Chỉ admin được ủy quyền; audit changes.
2. Provider URI thuộc allowlist và dùng TLS hợp lệ?
3. Secret lấy bằng KMS/vault, không lưu plaintext trong logs/cache công khai?
4. Có cache/timeout/TTL phù hợp với token/key rotations?
5. Configuration có consistency giữa authorization request và callback?
6. ID không tồn tại hay backend lỗi phải fail closed, không fallback sang provider ngẫu nhiên.
7. Nếu lookup dùng JDBC/JPA đồng bộ, đặt blocking boundary với scheduler/concurrency; không block event loop.
8. Nếu cần default login page tự liệt kê providers, repository có Iterable hoặc UI login custom đã kiểm quyền.

`InMemoryReactiveClientRegistrationRepository` quản lý static registration tốt nhưng không phải hệ thống phân quyền đa tenant, credential vault hay authorized-client token store.

## 16. Phân biệt lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Kiểm tra/khắc phục |
|---|---|---|
| Thiếu bean `ReactiveClientRegistrationRepository` | Không có OAuth2 client starter hoặc YAML sai | Xem classpath, Boot binder, type reactive |
| Bean kiểu Servlet `ClientRegistrationRepository` | Nhầm MVC với WebFlux | Dùng repository và Security chain reactive |
| Trang `/login` không có link IdP | Custom repo thiếu `Iterable`, login page bị custom, OAuth2 Login chưa bật | Kiểm bean/chain |
| `/oauth2/authorization/corporate` không redirect | Sai registrationId hoặc chain/matcher | Kiểm repository.findByRegistrationId |
| Đến sai authorization URL | Sai `provider` ID hoặc provider endpoints | Test `getProviderDetails().getAuthorizationUri()` |
| App không start khi có `issuer-uri` | Discovery network/TLS/DNS không thành công | Kiểm issuer metadata và trust |
| IdP báo `invalid_client` | Client ID/secret/method không khớp | Xác minh với IdP, không log secret |
| IdP báo `redirect_uri_mismatch` | Sai callback, scheme hoặc proxy headers | So URL IdP allowlist và actual Location |
| Callback báo `invalid_state` | Session/cookie/state mất hoặc bị sửa | Kiểm WebSession/IdP return/correlation |
| ID Token không được chấp nhận | JWKS/iss/aud/nonce/clock sai | Verify protocol, không bỏ signature |
| Login xong vẫn 403 | Thiếu role/tenant permission | Map issuer+sub, kiểm quyền |
| Không có OIDC principal | Thiếu `openid` scope hoặc IdP không đáp ứng OIDC | Kiểm registration scopes và response |
| Muốn gọi API ngoài mà không có access token | Nhầm registration metadata với authorized client | Dùng OAuth2AuthorizedClient và oauth2Client |
| App stateless chỉ bật Resource Server | Không cấu hình OAuth2 Login | Dùng đúng client registration và oauth2Login |
| Secret bị lộ khi debug | Log hoặc JSON serialize registration/token | Redact, rotate secret, hạn chế logs |

Một số lỗi chỉ xuất hiện **sau** redirect thành công; đừng kết luận “Spring Security OAuth2 hoạt động đầy đủ” chỉ vì browser được 302 tới IdP.

## 17. Ma trận integration test với IdP thật hoặc mock

Các test ở mục 10 kiểm **configuration và bắt đầu login**. Với security-critical login, bổ sung:

1. Authorization redirect có `response_type=code`, `client_id`, scopes, `state` và callback đúng.
2. Callback trả code hợp lệ được đổi ở token endpoint và có response theo protocol.
3. ID Token ký bằng JWKS của issuer đáng tin, có `iss`/`aud`/nonce hợp lệ, được chấp nhận.
4. Token sai signature, issuer, audience, nonce, lifetime đều bị từ chối.
5. Callback thiếu/sai `state`, code hết hạn/đã dùng hoặc session cookie mất phải fail closed.
6. Multiple registrations dùng đúng provider/clientID, không thể mix-up issuer/client.
7. External HTTPS/proxy callback có scheme, hostname và port đúng.
8. Key rotation ở JWKS không làm accept mọi key/algorithm; cache refresh có giới hạn.
9. Login thành công chưa có role vẫn bị từ chối route admin/record ngoại tenant.
10. Logout, session expiry, multiple tabs/pods và IdP outage không làm rò token hoặc bypass login.
11. Secret rotation làm fail/khôi phục đúng mà không phát tán secret trong HTTP/log.
12. Kiểm PKCE flow nếu policy yêu cầu; code verifier không lộ browser response.
13. Scope `openid`/`profile`/`email` thực tế được IdP đáp ứng hay có thể thiếu.
14. UserInfo data được lấy bằng access token an toàn khi cần, không trust email/role chưa xác minh.
15. Security upgrades không làm đổi endpoint matcher, bean, session persistence một cách âm thầm.

Có thể dùng mock OIDC IdP đầy đủ với authorization endpoint, token endpoint, JWKS và JWT ký test key; **đừng chỉ fake query `?code=abc` rồi tuyên bố đã test validation**.

## 18. Checklist triển khai

1. Chọn đúng nhiệm vụ: browser login OAuth2/OIDC, outbound OAuth2 client, hay JWT resource server.
2. Đăng ký client ở IdP, nhận clientId/secret/method và callback URI allowlist.
3. Tách ba tên: registrationId, providerId, clientId; ghi rõ mapping trong YAML.
4. Cấu hình `spring.security.oauth2.client.registration.*` và `provider.*`, ưu tiên discovery nếu IdP hỗ trợ.
5. Đặt client secrets trong environment/secret manager, không hardcode production.
6. Dùng `spring-boot-starter-webflux` + `spring-boot-starter-oauth2-client`; kiểm Bean repository reactive.
7. Bật `oauth2Login(Customizer.withDefaults())` hoặc customize qua `ServerHttpSecurity` đúng WebFlux.
8. Kiểm link `/oauth2/authorization/{registrationId}` và callback `/login/oauth2/code/{registrationId}`.
9. Kiểm URI ngoài sau proxy HTTPS, không tin forwarded headers giả mạo.
10. Giữ state, nonce, PKCE và token validation; không tự bỏ bảo vệ callback.
11. Bảo vệ session, CSRF, cookie và OAuth2 authorized-client storage.
12. Map issuer+subject sang account/tenant và kiểm quyền dữ liệu.
13. Viết test repository `Mono`, registration unknown, redirect URL và end-to-end IdP mock/thật.
14. Với multi-tenant, chỉ cho phép provider đã duyệt; tránh SSRF từ dynamic issuer.
15. Kiểm scopes/claims và hoạt động khi provider offline, secret rotation, JWKS rotation.
16. Nâng cấp Spring Security khi security advisories thay đổi; không giữ bản demo cũ cho production.

## 19. Bài tập thực hành

1. Phân biệt registrationId, providerId, clientId trong YAML demo. Nếu đổi một ID, những URL/bean nào bị ảnh hưởng?
2. Dùng `StepVerifier` đọc registration `training`, sau đó đọc ID `unknown`; mô tả Mono có/không có giá trị.
3. Gọi `/oauth2/authorization/training` bằng curl **không -L**, quan sát Location. Vì sao clientSecret không có trong query?
4. Thêm một registration khác trỏ cùng `training-idp`, khác scope và clientId. Viết test bảo đảm không trộn hai cấu hình.
5. Tự tạo `InMemoryReactiveClientRegistrationRepository` bean thay cho Boot properties; kiểm bean auto-configuration back off.
6. Thay endpoints giả bằng `issuer-uri` của IdP staging thật; kiểm metadata discovery và key/JWKS endpoint.
7. Cấu hình một callback URL khác mặc định. Nêu các nơi phải đồng bộ trên Spring Security và IdP.
8. Tạo mock callback sai `state`, sai `iss`, sai `aud`, sai nonce; chứng minh không có authenticated user.
9. Chạy app phía sau HTTPS reverse proxy; so request `redirect_uri` với allowlist của IdP.
10. So `oauth2Login` với `oauth2Client` và `oauth2ResourceServer`. Với ứng dụng chỉ kiểm JWT inbound, có cần ClientRegistration không?
11. Thiết kế một custom repository tenant-aware: tenant mapping đáng tin, issuer allowlist, timeout, cache và secret rotation.
12. Sau OIDC login, map `issuer+sub` sang internal user ID và kiểm một route thuộc tenant khác bị từ chối.
13. Kiểm xem default login page còn liệt kê providers khi repository custom không `Iterable`; sửa bằng custom login chooser an toàn.
14. Diễn giải vì sao gọi metadata discovery với issuer từ user input có thể gây SSRF.
15. Viết runbook khi IdP outage: startup failure, existing sessions, retry/backoff và bảo mật token/secret.

## Tóm tắt

**`ClientRegistration`** đại diện cho một client OAuth2/OIDC đã đăng ký, bao gồm client credentials, Authorization Code grant, scopes, redirect URI và endpoint provider. **`provider`** của Spring Boot định nghĩa issuer/discovery hoặc authorization/token/JWKS/UserInfo endpoints. **`ReactiveClientRegistrationRepository`** là API WebFlux trả `Mono<ClientRegistration>` theo `registrationId`; Spring Boot có thể dựng `InMemoryReactiveClientRegistrationRepository` từ YAML hoặc ứng dụng có thể cung cấp bean thủ công. Cùng `ServerHttpSecurity.oauth2Login(...)`, những thành phần này khởi động Authorization Code flow và xử lý callback **nhưng không tự cấp quyền**: cần IdP thực, state/nonce/token validation, session an toàn và business authorization.

## Tài liệu chính thức

1. Spring Security — Reactive OAuth2 Login Core Configuration: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html
2. Spring Security — Reactive OAuth2 Login Advanced Configuration, login page/callback: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html
3. Spring Security — Reactive OAuth2 Client Core Interfaces: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
4. Spring Security 6.3.8 Javadoc — InMemoryReactiveClientRegistrationRepository: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/oauth2/client/registration/InMemoryReactiveClientRegistrationRepository.html
5. Spring Security — WebFlux OAuth2 Login và OAuth2 Client: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
6. Spring Boot 3.3 — OAuth2 Client properties, WebFlux Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
7. Spring Security 6.3.8 Javadoc — ClientRegistration: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/oauth2/client/registration/ClientRegistration.html
8. RFC 6749 — OAuth2 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
9. RFC 7636 — Proof Key for Code Exchange: https://www.rfc-editor.org/rfc/rfc7636
10. OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
