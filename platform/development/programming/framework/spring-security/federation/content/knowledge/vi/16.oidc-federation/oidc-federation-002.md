# Cấu hình oauth2Login và ClientRegistration cho nhà cung cấp OIDC

**OpenID Connect (OIDC)** là lớp định danh xây trên OAuth 2.0. Với ứng dụng Spring Security Servlet, `oauth2Login(...)` xử lý đăng nhập qua trình duyệt bằng **Authorization Code**, còn `ClientRegistration` xác định **OpenID Provider (OP)**, client ID, client authentication, các endpoint giao thức, scopes, redirect URI và thông tin issuer/JWKS. Một ứng dụng còn có thể dùng **identity broker** làm OP trực tiếp, trong khi broker liên kết nhiều upstream IdP thuộc những tổ chức khác nhau.

Điểm thiết kế cần nhớ: **OAuth2 Login** không tự là OIDC nếu thiếu scope `openid`; **ID Token** có mục đích xác thực user khác **Access Token** dùng gọi API; **registrationId** là khóa cấu hình của Spring, khác **client_id**, **provider ID**, **issuer** và **subject** của người dùng.

Bài thuộc nhóm **OIDC và môi giới**, giải thích cách cấu hình Spring Boot 3.x/4.x và Spring Security 6.x/7.x, nguyên lý Discovery, luồng state/PKCE/nonce, multi-provider, broker identity boundaries, cấu hình Java, bài tập Java 17 độc lập và các test tích hợp. Mọi miền `.example` chỉ minh họa và không tồn tại trong production.

## 1. Các vai trò và thuật ngữ cần phân biệt

| Thành phần | Vai trò | Thành phần/giá trị Spring |
| --- | --- | --- |
| **Relying Party (RP)** | Ứng dụng Spring cần nhận diện end-user | `oauth2Login()` |
| **OpenID Provider (OP)** | Xác thực end-user và cấp ID Token | `ClientRegistration.providerDetails` |
| **Authorization Server** | Nhận authorization request, cấp code và tokens | `authorizationUri`, `tokenUri` |
| **Resource Server** | API kiểm Access Token | `oauth2ResourceServer()` (nếu cần) |
| **Client ID** | ID của app tại OP | `clientId` |
| **Client Secret** | Credential của confidential client | `clientSecret`, giữ bí mật |
| **Issuer** | Định danh OP phát token | `issuerUri`, claim `iss` |
| **User Subject** | ID ổn định trong namespace của issuer | claim `sub` |
| **Client registration key** | Chọn cấu hình client trong Spring | `registrationId` |
| **Provider configuration key** | Nhóm thông số OP trong Spring Boot | `providerId` |
| **Redirect URI** | RP callback nhận `code`/`state` | `redirectUri` |
| **JWKS URI** | Public keys của OP để verify ID Token | `jwkSetUri` |
| **UserInfo Endpoint** | Bổ sung claims qua access token | `userInfoUri` |

Ví dụ doanh nghiệp có:

~~~text
Spring RP: https://portal.example.com
OpenID Provider: https://login.corp.example/realms/workforce

registrationId: corp-oidc
providerId: workforce-op
clientId: portal-production
issuerUri: https://login.corp.example/realms/workforce
~~~

`registrationId=corp-oidc` không phải issuer, và `providerId=workforce-op` cũng không phải issuer. Khi xác minh ID Token, `iss` phải khớp URI của OP **đã tin cậy**, không phải nhãn cấu hình ngẫu nhiên.

**OIDC không phải SAML2.** Với OIDC, callback thường nhận `code` và `state` rồi backend đổi code lấy tokens. Với SAML, ACS thường nhận `SAMLResponse` chứa Assertion. Dùng `oauth2Login` cho OIDC; không sao chép SAML filters/config vào cùng endpoint.

## 2. Luồng Authorization Code với oauth2Login

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant RP as Spring Security RP
    participant OP as OIDC Provider
    U->>RP: GET /private
    RP-->>U: Chuyển hướng tới login / chọn provider
    U->>RP: GET /oauth2/authorization/corp-oidc
    RP->>RP: Tạo state, nonce và PKCE khi áp dụng
    RP->>RP: Lưu OAuth2AuthorizationRequest theo phiên
    RP-->>U: 302 tới OP authorization endpoint
    U->>OP: GET /authorize?client_id&redirect_uri&scope&state
    OP->>OP: Xác thực / MFA / consent
    OP-->>U: 302 tới redirect_uri kèm code, state
    U->>RP: GET /login/oauth2/code/corp-oidc?code=...&state=...
    RP->>RP: Kiểm state và authorization request đã lưu
    RP->>OP: POST /token: code + client authentication / PKCE verifier
    OP-->>RP: ID Token + Access Token (và Refresh Token nếu cấp)
    RP->>RP: Kiểm ID Token, dựng OidcUser/Authentication
    RP-->>U: Session của RP và chuyển trang
~~~

Spring có **hai route khác nhau**:

| Route ở RP | Tác dụng |
| --- | --- |
| `GET /oauth2/authorization/{registrationId}` | **Bắt đầu** Authorization Code; `OAuth2AuthorizationRequestRedirectFilter` xử lý |
| `GET /login/oauth2/code/{registrationId}` | **Callback mặc định** nhận code/state; `OAuth2LoginAuthenticationFilter` xử lý |

Authorization Endpoint và Token Endpoint thuộc **OP**, không thuộc RP. `/oauth2/authorization/corp-oidc` trả redirect tới OP; không tự sinh ID Token. `/login/oauth2/code/corp-oidc` không phải URL nhập mật khẩu.

**`Authorization Code` không phải access token hay ID Token**. Nó là credential ngắn hạn dùng đổi tokens tại Token Endpoint; backend phải ràng buộc bằng redirect URI, client authentication và PKCE khi áp dụng. Không đưa client secret vào URL browser.

## 3. Spring Security yêu cầu những thành phần nào?

Với Servlet stack:

- `HttpSecurity.oauth2Login(...)` cấu hình filter và login flow.
- `ClientRegistration` mô tả một client tại OP.
- `ClientRegistrationRepository` tra ClientRegistration bằng registrationId.
- `InMemoryClientRegistrationRepository` phù hợp cho tập registration tĩnh, nhỏ.
- `OAuth2AuthorizationRequestRedirectFilter` khởi tạo authorization request.
- `HttpSessionOAuth2AuthorizationRequestRepository` mặc định giữ authorization request và `state` trước callback.
- `OAuth2LoginAuthenticationFilter` xử lý callback và Authentication.
- `OidcIdTokenDecoderFactory` hỗ trợ kiểm ID Token cho OIDC login.
- `OidcUserService` trích identity/claims từ ID Token/UserInfo.
- `OAuth2AuthenticationToken` giữ kết quả Authentication.
- `OidcUser` là principal OIDC đã xác thực, chứa `sub`/claims.
- `OAuth2AuthorizedClientService` hoặc `OAuth2AuthorizedClientRepository` quản lý client đã được cấp tokens khi RP gọi API.

Một ứng dụng có thể chỉ dùng OAuth2 Login để đăng nhập user và không gọi API ngoài; không nhất thiết phải triển khai `oauth2ResourceServer`. Ngược lại, API nhận bearer access token dùng `oauth2ResourceServer` không tự có browser login redirect.

**Servlet vs WebFlux:** bài này dùng `SecurityFilterChain` và `HttpSecurity`. Trong reactive stack phải dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và `ReactiveClientRegistrationRepository`; không copy API Servlet vào reactive project.

## 4. Đăng ký OIDC client tại OP trước khi viết Java

Một client registration phải được tạo tại quản trị OP/broker:

1. Tạo application/client riêng cho staging và production.
2. Chọn confidential web client nếu backend bảo vệ được secret; public client khi không có chỗ giữ secret.
3. Bật **Authorization Code Flow**; tránh Implicit Flow cho ứng dụng mới.
4. Đăng ký **redirect URI chính xác**, ví dụ `https://portal.example.com/login/oauth2/code/corp-oidc`.
5. Lưu client ID và secret (nếu được cấp) trong vault hoặc secret manager.
6. Xác nhận issuer identifier, metadata/JWKS, authorization/token/userinfo URLs.
7. Xin scope tối thiểu `openid`, thêm `profile`/`email` nếu dùng.
8. Xác định chính sách MFA, `acr`, `amr`, conditional access và user eligibility.
9. Ghi nhận những claims/group OP thực sự phát, ai chịu trách nhiệm role mapping.
10. Có owner và quy trình rotate client secret, OP keys, disabled clients.

**Callback phải khớp exact URI**, bao gồm HTTPS, domain, port, context path và trailing slash theo quy tắc OP. Một URI kiểu wildcard rộng hoặc callback do user điều khiển dễ mở lỗ hổng rò code/open redirect.

## 5. Cấu hình Spring Boot bằng issuer-uri và Discovery

Ví dụ `application.yml` cho một OIDC client được OP phê duyệt:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-oidc:
            provider: workforce-op
            client-id: ${OIDC_CORP_CLIENT_ID}
            client-secret: ${OIDC_CORP_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: "Đăng nhập công ty"
        provider:
          workforce-op:
            issuer-uri: "https://login.corp.example/realms/workforce"
~~~

`registration.corp-oidc` xác định **registrationId=corp-oidc**. `provider: workforce-op` trỏ tới `provider.workforce-op`, nơi có `issuer-uri`. Hai key có thể khác nhau. `client-id` và `client-secret` lấy từ biến môi trường, không nên hardcode hoặc commit giá trị thật. `client-authentication-method: client_secret_basic` là một phương thức phổ biến nhưng phải khớp yêu cầu OP (một số OP hỗ trợ phương thức khác).

Khi app chạy và base URL public là `https://portal.example.com`, URI callback được mở rộng:

~~~text
https://portal.example.com/login/oauth2/code/corp-oidc
~~~

**Issuer URI không phải OP Authorization Endpoint.** Nó là định danh chính thức do OP công bố; Spring có thể dùng để khám phá các endpoint cần thiết. Trong nhiều hệ thống multi-tenant/realms, phần path của issuer rất quan trọng: `/realms/workforce` khác root issuer.

### Discovery trả về những gì?

Một tài liệu `.well-known/openid-configuration` có thể có:

~~~json
{
  "issuer": "https://login.corp.example/realms/workforce",
  "authorization_endpoint": "https://login.corp.example/realms/workforce/protocol/openid-connect/auth",
  "token_endpoint": "https://login.corp.example/realms/workforce/protocol/openid-connect/token",
  "jwks_uri": "https://login.corp.example/realms/workforce/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://login.corp.example/realms/workforce/protocol/openid-connect/userinfo"
}
~~~

**Đây là metadata JSON rút gọn minh họa**, không phải OP thật. URI Discovery chính xác phải tuân theo OIDC Discovery/RFC 8414 và cách issuer có path. `ClientRegistrations.fromIssuerLocation(...)` trong các bản Spring Security hiện đại có thể dò những well-known locations theo quy tắc framework; `fromOidcIssuerLocation(...)` tập trung endpoint OIDC. Không tự ghép URL tuỳ ý rồi tin rằng nó đúng.

Nếu OP metadata service/DNS/TLS không hoạt động, discovery khi tạo registration có thể khiến startup thất bại. Điều đó khác lỗi trong khi user đã đi qua callback. Với hệ thống HA, cần quy trình cache/pinned metadata hoặc khởi tạo an toàn được quản trị; **không nhận issuer URL từ query param của browser** để thực hiện discovery vì rủi ro SSRF/issuer mix-up.

## 6. Bật oauth2Login bằng SecurityFilterChain

Trong project Spring Boot có `spring-boot-starter-oauth2-client` và YAML phía trên:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Mã là **Spring JavaConfig** phải nằm trong ứng dụng và có bean registration hợp lệ; không chạy độc lập bằng `javac`. Spring sẽ cấu hình filters OAuth2 Login cho authorization request/callback. Nếu chỉ chạy project mà không có `ClientRegistrationRepository` hoặc YAML hợp lệ, Spring không thể tự biết OP nào.

Trong dự án có nhiều `SecurityFilterChain`, phải bảo đảm cả `/oauth2/authorization/**` và `/login/oauth2/code/**` đi vào chain bật `oauth2Login`. Không mở `anyRequest().permitAll()` cho production.

**Kiểm nhanh:** mở trang `https://portal.example.com/oauth2/authorization/corp-oidc` trên browser. Khi cấu hình hợp lệ, response thường redirect 302 tới OP authorization endpoint; cần kiểm tiếp callback, code exchange, ID Token validation và quyền người dùng. **HTTP 302 không tự chứng minh login đã thành công.**

## 7. Các dependencies Maven và Gradle

Trong dự án dùng Spring Boot parent/BOM quản lý versions, dependencies thường là:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
  </dependency>
</dependencies>
~~~

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Đây là **fragments của build** chứ không phải pom/Gradle project hoàn chỉnh. Đối với dự án không dùng starter, cần các module Spring Security OAuth2 Client, OAuth2 JOSE và Web/Security tương thích. Không ép version `spring-security-oauth2-client` riêng khỏi BOM để lấy API mới.

Kiểm artifacts resolve:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-oauth2-client
~~~

Lệnh không có stdout cố định; mục tiêu là xác định version thật của `spring-security-config`, `oauth2-client`, `oauth2-jose`, Spring Framework/Boot và JDK.

## 8. Spring Boot auto-configuration so với Java ClientRegistrationRepository

`ClientRegistrationRepository` là nguồn cấu hình clients. Nếu Spring Boot thấy `spring.security.oauth2.client.registration.<id>.*` và dependency cần thiết, nó có thể tạo repository phù hợp.

Nếu muốn tự quản lý bằng Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;

@Configuration
public class CorporateOidcRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration corporate = ClientRegistrations
                .fromIssuerLocation(
                    "https://login.corp.example/realms/workforce")
                .registrationId("corp-oidc")
                .clientId(System.getenv("OIDC_CORP_CLIENT_ID"))
                .clientSecret(System.getenv("OIDC_CORP_CLIENT_SECRET"))
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .build();

        return new InMemoryClientRegistrationRepository(corporate);
    }
}
~~~

Mã chạy **trong Spring project** có OP Discovery thật và biến môi trường đã cấp; hostname .example chưa thể sử dụng. `fromIssuerLocation` thực hiện truy cập metadata khi tạo registration. Với production, cần fail-fast có kiểm soát khi biến secret rỗng/missing, quản lý TLS trust và không log credentials.

**Đừng vừa tạo repository bean tự quản vừa kỳ vọng Boot tự trộn mọi registration từ YAML**. Tùy điều kiện auto-configuration, một bean tự định nghĩa có thể khiến Boot không tạo repository từ properties. Chọn một nguồn cấu hình có chủ đích.

### Dựng ClientRegistration thủ công

Nếu OP không hỗ trợ discovery hoặc doanh nghiệp muốn pin endpoints, Spring có `ClientRegistration.withRegistrationId(...)`:

~~~java
ClientRegistration registration = ClientRegistration
        .withRegistrationId("corp-oidc")
        .clientId("client-id-from-secure-config")
        .clientSecret("client-secret-from-secure-config")
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile", "email")
        .authorizationUri("https://login.corp.example/authorize")
        .tokenUri("https://login.corp.example/token")
        .jwkSetUri("https://login.corp.example/jwks")
        .issuerUri("https://login.corp.example")
        .userInfoUri("https://login.corp.example/userinfo")
        .userNameAttributeName("sub")
        .clientName("Đăng nhập công ty")
        .build();
~~~

Đây là **API fragment**, chưa có imports/secret management/repository, không phải Java standalone. Literal clientId/secret ở đây **biểu thị giá trị phải lấy từ cấu hình bảo mật**, không phải credential dùng được. Với OP dùng issuer chứa realm path, `issuerUri` phải khớp chính xác `iss`, không được đoán từ endpoint URL. Kiểm builder API theo Spring Security version đã resolve.

Manual config tăng trách nhiệm bảo trì khi OP thay endpoint/JWKS/algorithm. Nếu có thể dùng verified discovery, giảm nguy cơ gõ sai token/userinfo URI.

## 9. Scope openid là điều kiện nhận dạng OIDC

Với Spring Security OIDC Login, **scope `openid`** cho biết request dùng OIDC Authentication. Ví dụ:

~~~yaml
scope:
  - openid
  - profile
  - email
~~~

- `openid`: yêu cầu ID Token/luồng OIDC.
- `profile`: xin các profile claims theo chính sách OP.
- `email`: xin email-related claims; không đảm bảo mọi trường có giá trị.
- `offline_access`: nếu OP hỗ trợ và app thực sự cần refresh token/offline access, phải có policy rõ.

**Scope khác role.** Một scope `email` không cấp quyền `ROLE_ADMIN`. `profile` cũng không bảo đảm user được phép quản trị tenant. Authority mapping là trách nhiệm của ứng dụng và phải dựa trên issuer/subject/contract, không đọc chuỗi scopes rồi tự cấp quyền nghiệp vụ.

Nếu thiếu `openid`, Spring Security có thể dùng OAuth2-user processing thay OIDC-specific `OidcUserService`; đừng gọi đó là “OIDC login thành công” chỉ vì user nhận được access token.

## 10. ID Token khác Access Token và UserInfo

| Thành phần | Dùng bởi ai | Điểm cần kiểm |
| --- | --- | --- |
| **Authorization Code** | RP backend đổi lấy tokens | Không phải identity, ngắn hạn và dùng một lần |
| **ID Token** | **OIDC RP** | JWT phát cho client, chứa `iss`, `sub`, `aud`, `exp`, `iat`, `nonce` khi áp dụng |
| **Access Token** | API/Resource Server | Audience/scope riêng; không thay ID Token |
| **Refresh Token** | RP hoặc authorized client service | Credential nhạy cảm, phải lưu và rotate/thu hồi |
| **UserInfo** | RP gọi qua access token | Claims bổ sung và `sub` phải phù hợp ID Token |
| **RP Session Cookie** | Browser sau login | Giữ SecurityContext; khác mọi tokens trên |

**Không dùng một JWT access token được ký hợp lệ để lập user session theo OIDC chỉ vì có claim `sub`.** JWT có thể được phát cho API khác. Phải kiểm token purpose, issuer, audience và validation đúng flow.

### ID Token validation

Theo OIDC Core, `OidcIdTokenDecoderFactory` và validators của Spring Security phải duy trì:

1. **Signature/JWS:** khóa từ JWKS OP tin cậy; không tin `alg=none` hay tùy ý algorithm theo token.
2. **Issuer (`iss`):** phải bằng issuer URI đã cấu hình.
3. **Audience (`aud`):** phải có `client_id` của registration đang dùng.
4. **Authorized party (`azp`):** kiểm theo các quy tắc OIDC trong trường hợp có nhiều audiences.
5. **Expiry và timestamps:** `exp`, `iat`, sai số đồng hồ theo chính sách.
6. **Nonce:** nếu request gửi `nonce`, phải kiểm claim nonce đã được ràng buộc.
7. **Subject (`sub`):** giá trị cần thiết và scoped theo issuer.
8. **UserInfo `sub`:** không được mâu thuẫn với ID Token `sub`.
9. **`auth_time`, `acr`, `amr`:** áp policy khi doanh nghiệp yêu cầu MFA/freshness.
10. **Token audience/purpose:** không chấp nhận JWT phát cho một client/API khác.

Trong Spring Security, một `JwtDecoder` bean cho `oauth2ResourceServer().jwt()` **không mặc định là decoder được dùng để xác minh ID Token của `oauth2Login`**. Nếu cần tùy chỉnh OIDC Login decoder, xem `JwtDecoderFactory<ClientRegistration>`, `OidcIdTokenDecoderFactory` và `OidcIdTokenValidator` theo version. Đừng thay validator chuẩn bằng kiểm chữ ký duy nhất.

## 11. state, nonce và PKCE: ba lớp bảo vệ riêng

| Cơ chế | Nơi xuất hiện | Chống lại |
| --- | --- | --- |
| **`state`** | Authorization request/callback query | Authorization response CSRF/mix-up và sai flow |
| **`nonce`** | Authorization request và ID Token | Token replay/substitution, ràng buộc ID Token với flow |
| **PKCE** | `code_challenge` lúc authorize, `code_verifier` lúc token exchange | Code interception/injection, ràng buộc authorization code |
| **Client authentication** | Token endpoint | Xác thực client bằng secret/private key tùy mode |
| **Redirect URI validation** | OP và Spring RP | Code chuyển sang địa chỉ không được phép |

**PKCE không thay `state`**; `state` không thay nonce. Confidential client có secret không nên bỏ PKCE nếu OP/policy yêu cầu. Một ID Token có chữ ký hợp lệ nhưng nonce hoặc audience sai vẫn phải bị từ chối.

### Public clients

Với client không thể giữ secret, Spring Security hỗ trợ PKCE khi `client-authentication-method=none` và secret bỏ trống:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          public-oidc:
            provider: workforce-op
            client-id: ${OIDC_PUBLIC_CLIENT_ID}
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          workforce-op:
            issuer-uri: "https://login.corp.example/realms/workforce"
~~~

**Đây là ví dụ về public client**, không phải lý do để đổi mọi web server thành public client. Backend bảo vệ được secret thường nên dùng confidential client theo quy định OP/security team. Nếu cấu hình `ClientRegistration.clientSettings.requireProofKey=true` với Authorization Code, Spring Security có thể bật PKCE theo docs; phải kiểm `code_challenge` trên authorization request và `code_verifier` ở token exchange thật.

**Không đưa `code_verifier` vào browser URL hoặc logs.** Sử dụng S256 theo hỗ trợ OP. Nếu OP không hỗ trợ PKCE với confidential client, phối hợp cấu hình thay vì tắt các kiểm tra khác.

## 12. AuthorizationRequestRepository và HttpSession

Spring Security mặc định dùng `HttpSessionOAuth2AuthorizationRequestRepository` để lưu `OAuth2AuthorizationRequest` từ lúc user bắt đầu SSO đến callback. Dữ liệu này chứa state và các context cần thiết để chống ghép nhầm giao dịch.

Nếu browser nhận 302 từ OP với `code`/`state` nhưng callback không mang session cookie của SP, repository có thể không lấy được request. Những nguyên nhân:

- Cookie `SameSite`/`Secure`/`Domain`/`Path` sai hoặc browser chặn third-party context.
- Session hết TTL hoặc bị rotate/xóa.
- Nhiều nodes không chia sẻ session store.
- User mở nhiều login tabs khiến flow state bị ghi đè theo cách repo/app đang dùng.
- Proxy đổi hostname hoặc callback path.
- Authorization request đã bị consume và callback bị replay.

**Không bỏ kiểm state** để chữa lỗi. Nếu triển khai repository thay `HttpSessionOAuth2AuthorizationRequestRepository`, phải giữ binding với browser, random state, TTL, replay protection và fail closed. Chỉ dùng Redis/cache theo `state` mà không ràng buộc browser có thể tạo lỗ hổng login CSRF/login fixation.

Với callback OIDC mặc định top-level GET, cookie `SameSite=Lax` thường được gửi. Khi OP dùng `response_mode=form_post` hoặc khi RP nằm trong iframe, kiểm chính sách SameSite/third-party cookie riêng; không giả định mọi flow giống nhau.

## 13. Nhiều registrations và môi giới danh tính

Một portal có thể hỗ trợ OP nội bộ và OP của đối tác B:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-op
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            scope: [openid, profile, email]
          partner-b:
            provider: partner-op
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            scope: [openid, profile]
        provider:
          corp-op:
            issuer-uri: "https://login.corp.example/realms/employees"
          partner-op:
            issuer-uri: "https://login.partner-b.example/oidc"
~~~

Hai start URLs:

~~~text
GET /oauth2/authorization/corp
GET /oauth2/authorization/partner-b
~~~

Hai callbacks:

~~~text
GET /login/oauth2/code/corp
GET /login/oauth2/code/partner-b
~~~

OP phải đăng ký callback chính xác theo từng client. Khi application tự dựng login picker, nên chỉ hiển thị registration từ allowlist được server phê duyệt; không lấy issuer/discovery URL từ query parameter chưa kiểm rồi mở outbound request.

### Identity broker với upstream Entra ID/SAML/OIDC

~~~mermaid
flowchart LR
    USER[Người dùng] --> RP[Spring Relying Party]
    RP --> BROKER[OIDC Identity Broker]
    BROKER --> CORP[Upstream Entra ID]
    BROKER --> PARTNER[Upstream SAML IdP]
    BROKER --> EXTERNAL[Upstream OIDC IdP]
    BROKER --> RP
~~~

Spring RP có thể **chỉ có một ClientRegistration** tới broker:

~~~text
registrationId = broker
clientId       = portal-rp
issuerUri      = https://broker.example.com/realms/external
~~~

Broker giao tiếp các upstream IdPs nhưng phát ID Token cho RP với issuer của **broker**:

~~~json
{
  "iss": "https://broker.example.com/realms/external",
  "aud": "portal-rp",
  "sub": "broker-stable-subject"
}
~~~

**Không thay `iss` trong RP thành issuer upstream** chỉ vì user nhập mật khẩu ở Entra ID trước đó. `iss` phải khớp OP trực tiếp mà RP đăng ký và tin. Claims mô tả upstream source/subject chỉ dùng theo **hợp đồng broker** về tính xác thực, bền vững và namespaces.

Một broker có thể cho phép account linking hoặc JIT provisioning. Nếu `sub` broker thay đổi khi đổi upstream, local identity mapping có thể bị ảnh hưởng. Đừng tự gộp tài khoản theo email, kể cả email được đánh dấu verified; áp dụng identity-link key `(trustedIssuer, subject)` và chính sách mapping rõ.

**Home realm discovery / IdP hints:** broker có thể hỗ trợ các tham số riêng như `idp_hint` hoặc `domain_hint`. Chúng **không phải tham số OIDC tiêu chuẩn dùng chung mọi OP**. Nếu cần, dùng `OAuth2AuthorizationRequestResolver` thêm tham số trong allowlist theo server-side policy; không chấp nhận issuer URL tùy ý từ browser.

## 14. Tùy chỉnh authorization URL và callback

Mặc định Spring Security sử dụng:

~~~text
Start:    /oauth2/authorization/{registrationId}
Callback: /login/oauth2/code/{registrationId}
~~~

Muốn thay base URI khởi động:

~~~java
.oauth2Login(oauth2 -> oauth2
    .authorizationEndpoint(authorization ->
        authorization.baseUri("/federation/oidc/start")))
~~~

Với default resolver, URL sẽ theo mẫu `/federation/oidc/start/{registrationId}`.

Muốn callback `/federation/oidc/callback/{registrationId}`:

~~~java
.oauth2Login(oauth2 -> oauth2
    .redirectionEndpoint(redirection ->
        redirection.baseUri("/federation/oidc/callback/*")))
~~~

Cùng lúc đổi `ClientRegistration.redirectUri`:

~~~yaml
redirect-uri: "{baseUrl}/federation/oidc/callback/{registrationId}"
~~~

Và đăng ký URI public tại OP:

~~~text
https://portal.example.com/federation/oidc/callback/corp-oidc
~~~

**Ba nơi phải đồng bộ**: filter callback matcher, ClientRegistration redirectUri và OP allowlist. Nếu chỉ đổi một phía, có thể nhận `redirect_uri_mismatch`, 404 hoặc callback bị filter khác xử lý.

### Proxy public URL

Khi app chạy nội bộ `http://app:8080` nhưng public tại `https://portal.example.com/app`, `{baseUrl}` phải mở rộng ra public scheme/host/port/path đúng thực tế. Chỉ tin `Forwarded`/`X-Forwarded-*` từ reverse proxy đã được quản trị và loại bỏ headers do client internet tự đặt. Không giải quyết redirect mismatch bằng cách cho wildcard redirect hoặc tin mọi `Host` header: sẽ làm tăng nguy cơ open redirect/code leakage.

## 15. OidcUserService và quyền của user

Spring có `OidcUserService` để tạo `OidcUser` từ ID Token và UserInfo (nếu được gọi). Một controller trong Spring project:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentUserController {
    @GetMapping("/me")
    String me(@AuthenticationPrincipal OidcUser user) {
        return user.getSubject();
    }
}
~~~

Ví dụ này chỉ phù hợp khi endpoint yêu cầu OIDC-authenticated principal. Nếu ứng dụng đồng thời hỗ trợ form/SAML/OAuth2 thuần, principal có thể không là `OidcUser`; code cần xử lý phù hợp. Việc hiển thị `sub` thô cho browser cũng cần cân nhắc privacy/audit; trong hệ thống thật, trả local user ID hoặc view model theo chính sách.

### Custom OidcUserService

Nếu cần tra local user và authority mapping, dùng `oauth2Login(...).userInfoEndpoint(...).oidcUserService(...)` theo API:

~~~java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

OidcUserService defaultService = new OidcUserService();
OAuth2UserService<OidcUserRequest, OidcUser> service = userRequest -> {
    OidcUser verified = defaultService.loadUser(userRequest);
    // Sử dụng issuer + subject để tra local user và authorities.
    // Nếu account inactive hoặc tenant không hợp lệ, từ chối login.
    return verified;
};
~~~

**Đây là fragment hướng dẫn điểm mở rộng**, cần được gắn vào `userInfoEndpoint.oidcUserService(service)` trong security config và bổ sung local mapping thật; phần comment không tự ánh xạ role. Khi map authorities, có thể dùng `GrantedAuthoritiesMapper`. Nếu cần biến dữ liệu user, phải bảo vệ claim types, multi-valued attributes và kiểm `sub` của UserInfo.

**Quy tắc an toàn:** `ROLE_ADMIN`, tenant membership, account enabled/disabled phải đến từ policy nội bộ hoặc mapping IdP đã phê duyệt. `groups=admin` từ một OP bên ngoài không tự đồng nghĩa được cấp admin. Định danh user thường nên dùng `(iss, sub)`, không dùng email làm global key.

## 16. OAuth2AuthorizedClient khác ClientRegistration

Một client có thể nhận access token rồi gọi API downstream. Khi đó:

| Loại object | Chứa gì | Mục đích |
| --- | --- | --- |
| `ClientRegistration` | clientId, issuer/endpoints, scopes, redirect URI | Cấu hình một RP client |
| `OAuth2AuthenticationToken` | principal và authorities đã xác thực | SecurityContext của session |
| `OidcUser` | ID Token, UserInfo/claims | Danh tính end-user theo OIDC |
| `OAuth2AuthorizedClient` | registration, principalName, access/refresh tokens | Gọi API bằng token đã cấp |
| `OAuth2AuthorizedClientService` | Kho authorized clients | Lưu trữ/đọc tokens trong client context |
| `OAuth2AuthorizedClientManager` | Điều phối authorized client | Xin/refresh tokens khi phù hợp |

Access/refresh token là bí mật cần bảo vệ, không cho vào URL query/log. Nếu app chỉ xác thực user mà không gọi API ngoài, có thể không cần các API scopes rộng hay flow refresh.

**Không dùng ID Token để gọi resource server** nếu API mong access token. Không tự coi access token cho API là ID Token để xác thực browser session.

## 17. OIDC logout không phải SAML2 SLO

`oauth2Login()` hỗ trợ login, không tự làm SAML2 SLO. Local logout ở Spring có thể xóa session RP, nhưng OP/broker session vẫn còn; lần đăng nhập sau có thể tự SSO trở lại.

Nếu OP công bố `end_session_endpoint` qua Discovery và hỗ trợ OIDC RP-Initiated Logout, Spring Security Servlet có `OidcClientInitiatedLogoutSuccessHandler`:

~~~java
OidcClientInitiatedLogoutSuccessHandler handler =
    new OidcClientInitiatedLogoutSuccessHandler(clientRegistrationRepository);
handler.setPostLogoutRedirectUri("{baseUrl}");
~~~

Đây là fragment cần bean `ClientRegistrationRepository` và gắn vào `http.logout(logout -> logout.logoutSuccessHandler(handler))`. OP phải cho phép post-logout redirect URI theo policy. Không tự lấy issuer string và nối URL logout ngẫu nhiên.

Khi broker có upstream IdPs, logout broker không tự chứng minh tất cả upstream sessions đều được thu hồi. Đừng thông báo “đăng xuất khỏi mọi hệ thống” nếu chưa có xác nhận và chính sách rõ.

## 18. Java 17 độc lập: kiểm hợp đồng registration và callback

Để phân biệt sai config với lỗi giao thức thật, chương trình sau mô phỏng kiểm **issuer HTTPS**, **scope openid**, **grant authorization_code** và **redirectUri**. Nó không gọi mạng, không verify ID Token, không dùng Spring. Chỉ dùng để học cách tránh nhầm URL.

Tạo file `OidcRegistrationContractDemo.java`:

~~~java
import java.net.URI;
import java.util.Set;

public class OidcRegistrationContractDemo {
    record Registration(
            String id,
            String issuer,
            String redirectUri,
            String grant,
            Set<String> scopes) {}

    static String start(Registration r) {
        return "/oauth2/authorization/" + r.id();
    }

    static String callback(Registration r) {
        return "/login/oauth2/code/" + r.id();
    }

    static String check(Registration r, String registeredRedirect) {
        URI issuer = URI.create(r.issuer());
        if (!"https".equalsIgnoreCase(issuer.getScheme())
                || issuer.getHost() == null) {
            return "REJECT: issuer must use HTTPS";
        }
        if (!r.scopes().contains("openid")) {
            return "REJECT: openid scope missing";
        }
        if (!"authorization_code".equals(r.grant())) {
            return "REJECT: incorrect grant";
        }
        if (!r.redirectUri().equals(registeredRedirect)) {
            return "REJECT: redirect URI mismatch";
        }
        return "ACCEPT: registration contract consistent";
    }

    public static void main(String[] args) {
        String allowed =
                "https://portal.example.com/login/oauth2/code/corp";

        Registration correct = new Registration(
                "corp",
                "https://login.corp.example/realms/workforce",
                allowed,
                "authorization_code",
                Set.of("openid", "profile", "email"));

        Registration noOidc = new Registration(
                "corp", correct.issuer(), correct.redirectUri(),
                correct.grant(), Set.of("profile", "email"));

        Registration wrongCallback = new Registration(
                "corp", correct.issuer(),
                "https://portal.example.com/wrong/callback",
                correct.grant(), correct.scopes());

        Registration insecure = new Registration(
                "corp", "http://login.corp.example",
                correct.redirectUri(), correct.grant(), correct.scopes());

        System.out.println("Start: " + start(correct));
        System.out.println("Callback: " + callback(correct));
        System.out.println("Valid: " + check(correct, allowed));
        System.out.println("No OIDC: " + check(noOidc, allowed));
        System.out.println("Wrong callback: "
                + check(wrongCallback, allowed));
        System.out.println("Unsafe issuer: " + check(insecure, allowed));
    }
}
~~~

Chạy JDK 17+:

~~~bash
javac OidcRegistrationContractDemo.java
java OidcRegistrationContractDemo
~~~

**Stdout chính xác:**

~~~text
Start: /oauth2/authorization/corp
Callback: /login/oauth2/code/corp
Valid: ACCEPT: registration contract consistent
No OIDC: REJECT: openid scope missing
Wrong callback: REJECT: redirect URI mismatch
Unsafe issuer: REJECT: issuer must use HTTPS
~~~

**Giới hạn cần nhớ:** `Valid: ACCEPT` chỉ nói chuỗi cấu hình trong demo nhất quán. Nó **không** chứng minh có OP tại URL, clientId/secret đúng, Discovery thành công, `state`/PKCE hoạt động, ID Token đã verify signature/issuer/audience, hay tenant authorization đúng. Không đưa hàm `check` này vào pipeline xác thực production.

## 19. Ma trận integration test với OP thật

| Kịch bản | Cách thử | Kỳ vọng |
| --- | --- | --- |
| Discovery | App khởi động với issuer thật | OP metadata/JWKS resolve hoặc báo lỗi cấu hình rõ |
| Start | GET `/oauth2/authorization/corp` | Redirect đúng allowlisted OP |
| Request parameters | Browser test/proxy lab | `client_id`, `response_type=code`, redirect_uri, state, openid |
| PKCE public client | `none`, secret rỗng | `code_challenge` và `code_verifier` đúng |
| Callback | OP trả code/state về RP | `OAuth2LoginAuthenticationFilter` xử lý |
| State | Callback state của request gốc | Được chấp nhận; state lạ bị từ chối |
| Token exchange | Backend gửi đúng code/client auth | Tokens đúng theo OP contract |
| ID Token signature | OP ký đúng và sai key | Chỉ key tin cậy được chấp nhận |
| ID Token issuer | `iss` từ OP khác | Từ chối |
| ID Token audience | `aud` không chứa client ID | Từ chối |
| Token expired | `exp` đã qua | Từ chối |
| Nonce | ID Token nonce sai | Từ chối |
| UserInfo | `sub` khác ID Token | Từ chối |
| Local link | `(iss,sub)` đã đăng ký | Đúng local user và tenant |
| Unlinked user | Subject mới chưa phê duyệt | Fail closed hoặc JIT policy rõ |
| Role spoof | OP group=ADMIN chưa allowlist | Không có `ROLE_ADMIN` |
| Callback mismatch | OP URI khác Spring callback | OP từ chối, app không nhận code |
| Cookie missing | Callback thiếu RP session | Từ chối an toàn, phân loại state/repository |
| Multi-OP mix-up | Code/token của partner B trên corp registration | Không tạo user session |
| Reverse proxy | Internal HTTP nhưng public HTTPS | redirect_uri và issuer đúng |
| Session logout | Logout local/OP theo config | Báo rõ mức logout thực |
| Tenant boundary | User B gọi API C | HTTP 403 |

`SecurityMockMvcRequestPostProcessors.oidcLogin()` từ `spring-security-test` hữu ích để unit test một controller đã có `OidcUser`/authority, nhưng **không test thật** Discovery, redirect, code exchange, ID Token signature hoặc PKCE. Cần test E2E với OP lab hoặc signed fixtures để kết luận tích hợp OIDC chính xác.

## 20. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Không có `ClientRegistrationRepository` | Thiếu dependency/cấu hình | Kiểm starter và registration properties |
| Startup fail với issuer-uri | DNS/TLS/well-known lỗi, issuer path sai | Kiểm issuer và metadata từ nguồn tin cậy |
| Start URL 404 | registrationId không tồn tại, matcher chain sai | Kiểm repo, `authorizationEndpoint.baseUri` |
| OP trả `redirect_uri_mismatch` | OP không đăng ký đúng public callback | Đồng bộ OP, redirectUri và proxy |
| Callback 404 | `redirectionEndpoint.baseUri` khác redirectUri | Sửa callback matcher |
| `authorization_request_not_found` | Mất session/authorization request | Kiểm cookie `JSESSIONID`/`SESSION`, TTL và repo |
| `invalid_state` | State không khớp hoặc replay | Từ chối, không disable state check |
| `invalid_client` | Client secret/auth method sai | Kiểm secret manager, OP app settings |
| `invalid_grant` | Code expired/used, verifier/redirect sai | Kiểm token exchange, PKCE, callback |
| ID Token signature failed | JWKS/key/alg sai, issuer bị thay | Cập nhật trust, không bỏ verify |
| Wrong issuer/audience | Registration cấu hình nhầm OP/client | So `iss`/`aud` với issuer/clientId |
| Email claim thiếu | OP không phát theo scope/consent | Không tự đoán hoặc dùng email làm khóa duy nhất |
| Login nhưng role sai | Chưa map local authorities | Dùng `OidcUserService`/mapper có policy |
| 403 sau login | User thiếu quyền tài nguyên/tenant | Kiểm authorization riêng, không lỗi OIDC |
| Logout xong lại login thầm | OP/broker session vẫn còn | Xem OIDC RP-initiated logout |
| Có session nhưng đổi node lỗi | Session repository/load balancer không đồng bộ | Test multi-node và cookie |
| Class/method mismatch | Spring modules bị override version | Dùng BOM, resolved dependency graph |

**Điều tra theo từng bước:** nếu lỗi xảy ra trước redirect tới OP, xem registration/start; nếu OP báo lỗi, xem client/redirect/scopes; nếu callback fail, xem state/cookie/token; nếu login xong bị 403, xem role/tenant policy. Không log code, state, client secret, tokens hoặc raw UserInfo PII.

## 21. Bảo mật môi giới và production

- **Pin issuer:** `issuer-uri` chỉ từ cấu hình đã được quản trị, không từ query/email domain chưa xác minh.
- **Client secret:** lưu vault/secret manager; rotate, phân tách staging/prod.
- **Discovery metadata:** lấy HTTPS, kiểm issuer và JWKS theo trust policy; tránh SSRF và thay endpoints ngoài ý muốn.
- **Redirect URI:** khớp exact URI được OP cho phép; không dùng wildcard rộng.
- **state/nonce:** random, tương quan browser session, ngăn replay và mix-up.
- **PKCE:** xác minh code challenge/verifier đúng client type/policy, ưu tiên S256.
- **ID Token:** kiểm signature, issuer, audience, timestamps, nonce và purpose.
- **UserInfo:** `sub` phải nhất quán với ID Token.
- **Danh tính:** key `(iss,sub)`; nếu broker có upstream subject, phải có contract riêng.
- **Phân quyền:** dùng local role/tenant policies và authorization tại service; không suy quyền admin từ OP groups.
- **Session:** cookie `Secure`, `HttpOnly`, SameSite phù hợp redirect mode; không bỏ CSRF toàn ứng dụng.
- **Reverse proxy:** tin forwarded headers từ proxy tin cậy để phát đúng public callback.
- **Audit:** ghi registrationId, localUserId, thời điểm login, rule; không ghi tokens/PII nguyên văn.
- **Logout:** phân biệt local RP session và OP/broker session.
- **Offboarding:** account disabled và role revoked cần policy session recheck/revocation.
- **Version:** Spring Boot/Security/JDK/OpenID libraries phải đồng bộ và regression test.

## 22. Bài tập tự kiểm tra

**A.** `registrationId=corp-oidc` và `providerId=workforce-op`, issuer là `https://login.corp.example/realms/workforce`. URL bắt đầu phải là `/oauth2/authorization/corp-oidc`, còn token `iss` phải bằng URI issuer, **không** là `workforce-op`.

**B.** Scope chỉ có `profile,email`. Không được khẳng định đây là OIDC Login: thiếu `openid`, ID Token không được bảo đảm.

**C.** IdP B và IdP C cùng phát `sub=1234`. Hai định danh không tự là cùng người vì namespace issuer khác nhau; dùng `(iss,sub)` và linking policy.

**D.** Filter callback nhận `/login/oauth2/code/*` nhưng OP chuyển tới `/federation/callback/corp`. Cần sửa đồng bộ callback filter, ClientRegistration redirectUri và OP allowlist.

**E.** Broker phát ID Token `iss=https://broker.example.com/realms/external`, upstream là Entra ID. Spring RP đang tin broker thì phải verify issuer broker, không biến upstream hint thành issuer thay thế.

**F.** ID Token hợp lệ nhưng user không có `ROLE_ADMIN`. HTTP 403 tại `/admin` có thể là kết quả authorization đúng, không phải OAuth2/OIDC login lỗi.

## 23. Tài liệu chính thức

1. [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistrationRepository, redirect URI và Spring Boot mappings.
2. [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): DSL, redirectionEndpoint, OidcUserService và ID Token decoder factory.
3. [Spring Security — Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): Authorization Code, PKCE, state repository và request resolver.
4. [Spring Security — Servlet OAuth2 Overview](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): OAuth2 Client, OIDC login và khác biệt Resource Server.
5. [Spring Boot — OAuth2 Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html): registration/provider settings, issuer-uri Discovery.
6. [Javadoc — ClientRegistrations](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/registration/ClientRegistrations.html): fromIssuerLocation/fromOidcIssuerLocation.
7. [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): OidcClientInitiatedLogoutSuccessHandler.
8. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, OIDC Authorization Code, validation/UserInfo.
9. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): well-known metadata và issuer.
10. [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636): code_verifier/code_challenge.
11. [RFC 9700 — OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700.html): redirect URI, PKCE và mix-up defenses.
12. [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): rủi ro triển khai OAuth2/OIDC.

**Ghi nhớ:** `oauth2Login` bật browser login flow của Spring; `ClientRegistration` xác định **OP/client/trust contract** cụ thể. `openid` xác lập mục tiêu OIDC, `state`/nonce/PKCE bảo vệ authorization request, còn ID Token phải qua issuer/audience/signature/time validation. Với broker, RP trực tiếp tin **issuer của broker**, không tự tin mọi upstream IdP. Khi nhiều tổ chức cùng dùng portal, chỉ danh tính scoped theo `(issuer,sub)` và mapping quyền đã duyệt mới giữ ranh giới federation an toàn.