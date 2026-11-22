# 34.10. Tích hợp provider tự triển khai trong môi trường local

## 1. Tình huống thực hành

Trong các ví dụ OAuth 2.0/OIDC Client, ứng dụng thường đăng nhập qua một Identity Provider sẵn có. Ở bài thực hành này, chúng ta **tự triển khai và vận hành OpenID Provider (OP) local** rồi cấu hình một ứng dụng **Spring Security OAuth2/OIDC Client** thực hiện Authorization Code Flow với provider ấy.

Hai ứng dụng Spring Boot riêng biệt:

~~~text
Browser
  |
  | GET http://127.0.0.1:8080
  v
Portal / Relying Party (:8080)
  |  Spring Security oauth2Login()
  |  ClientRegistration(local-idp)
  |
  | 302 /oauth2/authorize?...state...nonce...PKCE...
  v
Local OpenID Provider (:9000)
  |  Spring Authorization Server
  |  Login form + consent
  |  Authorization Code, Token, ID Token, JWK Set
  |
  | 302 callback with code and state
  v
Portal /login/oauth2/code/local-idp
  |  POST /oauth2/token từ backend
  |  Xác minh ID Token iss/aud/exp/signature/nonce
  v
Portal /me -> authenticated OidcUser
~~~

**Provider tự triển khai** ở đây là một ứng dụng do chúng ta kiểm soát, cấu hình bằng **Spring Authorization Server**, chứ không phải tự viết toàn bộ OAuth 2.0/OIDC protocol bằng vài REST controllers. Framework cung cấp các bộ lọc, grant handlers và token services có thể tùy biến, giảm nguy cơ bỏ sót client authentication, redirect URI, PKCE, state, token signature và consent.

> Công nghệ: Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring Authorization Server thuộc dòng tương thích, Spring MVC/Servlet. Các snippets dựa trên APIs Spring Authorization Server 1.x phù hợp Spring Security 6; kiểm tra đúng BOM/phiên bản dự án nếu sử dụng Spring Security 7 hoặc dòng Authorization Server mới hơn. Tất cả credentials, keys, hosts và URLs trong lab chỉ dành cho môi trường local.

## 2. Mục tiêu học tập

Hoàn thành bài, người học có thể:

1. Phân biệt OpenID Provider, Authorization Server, OAuth2 Client và Resource Server.
2. Chạy OP local tại `http://127.0.0.1:9000`.
3. Công bố OIDC discovery document và public JWKS.
4. Đăng ký một confidential client có `authorization_code`, `refresh_token`, scopes và PKCE policy.
5. Tạo demo user và authorization consent.
6. Ký ID Token JWT bằng RSA test key và hiểu issuer/audience.
7. Kết nối Portal MVC tại `http://127.0.0.1:8080` bằng `issuer-uri`.
8. Dùng `oauth2Login()`, `OAuth2AuthorizationRequestCustomizers.withPkce()` và OidcUser.
9. Quan sát state, nonce, callback, session cookie, code exchange và ID Token validation.
10. Thử các ca sai issuer/client ID/secret, redirect URI, PKCE, state và signature.
11. Phân biệt ID Token, access token, UserInfo, authorized-client storage và logout.
12. Nắm được giới hạn của demo in-memory và yêu cầu thay đổi trước production.

## 3. Roles trong giao thức

| Vai trò | Trong lab | Trách nhiệm |
|---|---|---|
| Resource Owner | Người dùng `alice` | Xác thực và chấp thuận cấp quyền |
| Authorization Server | `local-provider` | Cấp authorization code, access token |
| OpenID Provider | Cũng là `local-provider` | Cấp ID Token, UserInfo, OIDC metadata |
| OAuth2 Client / Relying Party | `portal-client` | Bắt đầu login và xác minh ID Token |
| Resource Server | `orders-api` tùy chọn | Chấp nhận Bearer access token, bảo vệ API |
| RegisteredClient | Bản ghi ở OP với `clientId=portal-client` | Client authentication, scopes, redirects |
| ClientRegistration | Bản ghi ở Portal với `registrationId=local-idp` | Metadata local của OAuth2 Client |
| OAuth2AuthorizedClient | Authorization/token dành cho registration + principal | Token lifecycle |

Không được nhầm:

~~~text
Provider RegisteredClient.clientId       = portal-client
Portal ClientRegistration.registrationId = local-idp
~~~

`client_id` xuất hiện trong OAuth protocol, còn `registrationId` là khóa nội bộ của Spring Security để chọn client configuration.

## 4. Bức tranh Authorization Code Flow với OIDC và PKCE

~~~mermaid
sequenceDiagram
    actor B as Browser
    participant RP as Portal :8080
    participant OP as Local Provider :9000

    B->>RP: GET /oauth2/authorization/local-idp
    RP-->>B: 302 /oauth2/authorize (client_id, state, nonce, PKCE challenge)
    B->>OP: GET /oauth2/authorize
    OP-->>B: Login page
    B->>OP: Credentials / consent
    OP-->>B: 302 /login/oauth2/code/local-idp?code=...&state=...
    B->>RP: Callback with code/state + Portal session cookie
    RP->>OP: POST /oauth2/token (code, secret, PKCE verifier)
    OP-->>RP: access_token, id_token, optional refresh_token
    RP->>OP: GET /oauth2/jwks as needed
    OP-->>RP: Public RSA JWK
    RP->>RP: Validate ID Token issuer, audience, expiry, signature, nonce
    RP-->>B: Portal authenticated session, redirect /me
    B->>RP: GET /me
    RP-->>B: User summary
~~~

Browser không nhận client secret; nó chỉ đi qua top-level redirects. Portal backend gọi token endpoint và giải mã/kiểm tra ID Token.

## 5. Project structure và địa chỉ sử dụng

~~~text
oidc-local-lab/
├── local-provider/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/com/example/provider/
│       │   ├── LocalProviderApplication.java
│       │   └── ProviderSecurityConfig.java
│       └── resources/application.yml
└── portal-client/
    ├── build.gradle.kts
    └── src/main/
        ├── java/com/example/portal/
        │   ├── PortalClientApplication.java
        │   ├── PortalSecurityConfig.java
        │   └── HomeController.java
        └── resources/application.yml
~~~

Sử dụng thống nhất các địa chỉ:

~~~text
Provider issuer : http://127.0.0.1:9000
Portal URL      : http://127.0.0.1:8080
Portal callback : http://127.0.0.1:8080/login/oauth2/code/local-idp
~~~

**Không trộn `localhost` và `127.0.0.1`** trong provider issuer, browser URL và ClientRegistration: hai hostnames có thể cùng trỏ loopback nhưng **không phải cùng URI/cookie host/trust identity**.

### 5.1. Lưu ý cực kỳ quan trọng: cookie không tách theo port

Hai ứng dụng Servlet dùng chung hostname nhưng khác cổng có thể **ghi đè `JSESSIONID` của nhau**, vì browser cookies được phân chia theo host/domain và path, **không theo port**. Do đó:

~~~text
Provider cookie name: IDPSESSION
Portal cookie name:   PORTALSESSION
~~~

Giải pháp này giúp browser giữ **hai sessions độc lập** khi cả hai app dùng `127.0.0.1` và cookie Path `/`.

## 6. Công cụ cần có

- JDK 17 hoặc mới hơn.
- Gradle/Maven và Spring Boot 3.x tương thích Spring Authorization Server.
- Hai terminal, một browser và `curl` hoặc HTTP client.
- Cổng 9000 và 8080 còn trống.
- Không cần Docker, database hay IdP public cho lab tối thiểu.

Trong snippets chỉ đưa dependencies và code cần thiết; khi tạo `build.gradle.kts`, dùng plugin versions/BOM của một Spring Boot 3.x release phù hợp thay vì chép version placeholder vào build đang chạy.

## 7. local-provider: dependencies

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation(
        "org.springframework.boot:spring-boot-starter-oauth2-authorization-server"
    )
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Spring Authorization Server giúp tự triển khai OP một cách có cấu trúc. Dòng starters/artifacts và namespace có thể thay đổi khi nâng major version; dùng tài liệu theo BOM dự án.

## 8. local-provider: application.yml

~~~yaml
server:
  port: 9000
  servlet:
    session:
      cookie:
        name: IDPSESSION
        http-only: true

logging:
  level:
    org.springframework.security: INFO
~~~

Đây là HTTP **loopback lab**, không phải cấu hình production. Trong production dùng HTTPS, Secure cookies, proper signing-key management và không log raw credentials/tokens.

## 9. local-provider: Spring Boot application

~~~java
package com.example.provider;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LocalProviderApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            LocalProviderApplication.class, args);
    }
}
~~~

## 10. local-provider: hai SecurityFilterChain

File `ProviderSecurityConfig.java`:

~~~java
package com.example.provider;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation
    .web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication
    .LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration
public class ProviderSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer configurer =
            OAuth2AuthorizationServerConfigurer
                .authorizationServer();

        http
            .securityMatcher(configurer.getEndpointsMatcher())
            .with(configurer, server -> server
                .oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(errors -> errors
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(resource -> resource
                .jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain formLoginChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Các bean còn lại ở các mục sau được **bổ sung vào cùng cấu hình ProviderSecurityConfig** hoặc đặt trong `@Configuration` riêng có component scanning phù hợp; không tạo các duplicate beans với cùng type/name.

### 10.1. OAuth2 chain đứng trước

`@Order(1)` xử lý protocol endpoints do configurer sở hữu. `@Order(2)` làm fallback, phục vụ form login `/login` để xác thực resource owner.

### 10.2. OIDC cần được bật riêng

`.oidc(Customizer.withDefaults())` bật OIDC provider features như discovery/UserInfo/logout theo config/version. Một OAuth Authorization Server chưa bật OIDC không tự phát ID Token chỉ vì có JWT signing key.

### 10.3. Resource Server JWT trong chính OP

OIDC UserInfo là Bearer-protected endpoint. `.oauth2ResourceServer(...jwt())` trên provider chain hỗ trợ xác thực access token khi OP xử lý những yêu cầu như UserInfo.

### 10.4. Matcher của OP

`configurer.getEndpointsMatcher()` là tập endpoints do Authorization Server nắm giữ. Không thay bằng `securityMatcher("/api/**")` khiến `/oauth2/token`, discovery hay `/userinfo` nằm ngoài chain.

## 11. Đăng ký confidential client tại Provider

Provider cần biết Portal được phép dùng OAuth2/OIDC:

~~~java
import java.time.Duration;
import java.util.UUID;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client
    .InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client
    .RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client
    .RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings
    .ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings
    .TokenSettings;

@Bean
RegisteredClientRepository registeredClients(PasswordEncoder encoder) {
    RegisteredClient portal = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("portal-client")
        .clientSecret(encoder.encode("portal-secret"))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
            AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
            AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri(
            "http://127.0.0.1:8080/login/oauth2/code/local-idp")
        .postLogoutRedirectUri("http://127.0.0.1:8080/")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope(OidcScopes.EMAIL)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
            .requireAuthorizationConsent(true)
            .requireProofKey(true)
            .build())
        .tokenSettings(TokenSettings.builder()
            .accessTokenTimeToLive(Duration.ofMinutes(5))
            .refreshTokenTimeToLive(Duration.ofMinutes(30))
            .reuseRefreshTokens(false)
            .build())
        .build();

    return new InMemoryRegisteredClientRepository(portal);
}
~~~

| Property | Mục đích |
|---|---|
| `clientId=portal-client` | Định danh client gửi trong authorization request |
| `clientSecret` | Xác thực Portal tại token endpoint |
| `client_secret_basic` | HTTP Basic ở token exchange |
| `authorization_code` | Server-side browser login |
| `refresh_token` | Cho phép refresh nếu OP thực sự cấp |
| `redirectUri` | Callback allowlist |
| `openid` | Kích hoạt OIDC/ID Token |
| `orders.read` | Scope demo cho API tùy chọn |
| `requireAuthorizationConsent` | Cơ chế user consent |
| `requireProofKey` | Bắt buộc PKCE |

### 11.1. PKCE trên confidential client

Provider yêu cầu PKCE, nên **Portal phải tự gửi `code_challenge` và `code_verifier`**. Với confidential clients, không giả định phiên bản Spring Security tự bật PKCE. Sẽ cấu hình explicit `withPkce()` ở phía Portal.

### 11.2. Refresh token không phải lúc nào cũng có

RegisteredClient có `refresh_token` grant chưa chứng minh token endpoint luôn phát refresh token; tùy policy, grant và consent mà response có thể khác.

### 11.3. In-memory repository là giới hạn của lab

Sau restart, client record/consent/authorization/token store có thể thay đổi hoặc mất. Production cần persistent repositories và lifecycle quản trị.

## 12. Người dùng test và PasswordEncoder

Thêm vào ProviderSecurityConfig:

~~~java
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.factory
    .PasswordEncoderFactories;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
UserDetailsService users(PasswordEncoder encoder) {
    UserDetails alice = User.withUsername("alice")
        .password(encoder.encode("alice-pass"))
        .roles("USER")
        .build();
    UserDetails admin = User.withUsername("admin")
        .password(encoder.encode("admin-pass"))
        .roles("USER", "ADMIN")
        .build();
    return new InMemoryUserDetailsManager(alice, admin);
}
~~~

Demo credentials:

~~~text
alice / alice-pass
admin / admin-pass
~~~

**Không đưa những credentials này lên production, không mở cổng provider ra mạng public.**

### 12.1. Password thuộc Provider, không phải Portal

Browser nhập user/password ở OP trên cổng 9000. Portal không bao giờ cần biết password của Alice; chỉ dùng authorization code và OIDC ID Token response.

### 12.2. Role ở Provider không tự thành ROLE_ADMIN ở Portal

`UserDetailsService` phục vụ form authentication tại OP. Role mapping tại Portal phụ thuộc các claims mà OP thực sự phát và cơ chế mapping đã xác minh; không suy từ username `admin`.

## 13. Issuer cố định

~~~java
import org.springframework.security.oauth2.server.authorization.settings
    .AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("http://127.0.0.1:9000")
        .build();
}
~~~

Issuer là trust identifier, cần khớp chính xác giữa discovery metadata, ID Token `iss` và ClientRegistration của Portal. Không tự chuyển giữa `http://localhost:9000` và `http://127.0.0.1:9000`.

**Production issuer phải là HTTPS URL cố định/trusted**, không quyết định tùy tiện từ Host/X-Forwarded-Host của browser.

## 14. Ký ID Token bằng RSA và công bố JWK Set

Provider cần một RSA keypair dùng để ký JWT. Đăng ký:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.util.UUID;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

@Bean
JWKSource<SecurityContext> jwkSource() throws Exception {
    KeyPairGenerator generator =
        KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    KeyPair pair = generator.generateKeyPair();

    RSAKey rsa = new RSAKey.Builder(
        (RSAPublicKey) pair.getPublic())
        .privateKey((RSAPrivateKey) pair.getPrivate())
        .keyID(UUID.randomUUID().toString())
        .build();

    JWKSet keys = new JWKSet(rsa);
    return (selector, context) -> selector.select(keys);
}
~~~

OIDC features của Spring Authorization Server thường cần `JwtDecoder`:

~~~java
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation
    .web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration
        .jwtDecoder(jwkSource);
}
~~~

### 14.1. Public JWKS không chứa private key

`/oauth2/jwks` công bố public key, dùng xác minh chữ ký. Private RSA key chỉ tồn tại phía provider. Nếu tự ghi public response, dùng `rsa.toPublicJWK()` chứ không serialize cả private key.

### 14.2. Vì sao dùng RSA 2048 trong lab?

Đủ để quan sát ký/xác minh JWT ở test. Production cần key management, KMS/HSM nếu thích hợp, key ID, rotation, certificate/JWKS caching và khả năng phục hồi.

### 14.3. Key bị đổi sau restart

Lab tạo key mới mỗi lần khởi động, do đó JWT cũ có thể không xác minh được sau restart. Đây là behavior **không phù hợp production**, nơi signing keys phải được quản lý ổn định và rotate có overlap window.

## 15. Thêm claims vào ID Token (tùy chọn)

Ví dụ customizer trong ProviderSecurityConfig:

~~~java
import org.springframework.security.oauth2.core.oidc.endpoint
    .OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.token
    .JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token
    .OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> tokenCustomizer() {
    return context -> {
        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            String username =
                context.getPrincipal().getName();
            context.getClaims()
                .claim("preferred_username", username)
                .claim("name", username)
                .claim("email", username + "@example.test");
        }
    };
}
~~~

Đây là mapper **chỉ dùng trong lab**. Không tự suy email đã được xác minh, không phát `email_verified=true` nếu chưa có quy trình verification; không tự biến bất kỳ claim nào thành quyền admin.

### 15.1. ID Token và access token có claims khác mục đích

ID Token dành cho client xác thực user. Access token dành cho Resource Server. Nếu cần audience/resource claims ở access token, tạo policy/customizer riêng cho token type ấy; không sao chép tất cả ID Token claims sang access token.

### 15.2. UserInfo

OIDC UserInfo có thể trả user claims theo scopes/consent/configuration. Nếu cần custom UserInfo mapping ngoài defaults, dùng extension points của Spring Authorization Server thay vì bypass access-token authentication.

## 16. Danh sách beans ở Provider

Sau khi ghép các snippets, ProviderSecurityConfig hoặc các @Configuration classes tương đương có:

~~~text
@Bean SecurityFilterChain authorizationServerChain(...)
@Bean SecurityFilterChain formLoginChain(...)
@Bean RegisteredClientRepository registeredClients(...)
@Bean PasswordEncoder passwordEncoder()
@Bean UserDetailsService users(...)
@Bean AuthorizationServerSettings authorizationServerSettings()
@Bean JWKSource<SecurityContext> jwkSource()
@Bean JwtDecoder jwtDecoder(...)
@Bean OAuth2TokenCustomizer<JwtEncodingContext> tokenCustomizer()
~~~

Các đoạn method trong tài liệu **không phải từng class độc lập có thể copy trùng**, mà là những thành phần để ghép vào cấu hình.

## 17. Khởi động local-provider và kiểm tra metadata

Linux/macOS terminal:

~~~bash
cd oidc-local-lab/local-provider
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
cd oidc-local-lab\local-provider
.\gradlew.bat bootRun
~~~

Khi ứng dụng đã nghe trên cổng 9000, kiểm tra discovery:

~~~bash
curl -i http://127.0.0.1:9000/.well-known/openid-configuration
~~~

Một phần response kỳ vọng:

~~~json
{
  "issuer": "http://127.0.0.1:9000",
  "authorization_endpoint": "http://127.0.0.1:9000/oauth2/authorize",
  "token_endpoint": "http://127.0.0.1:9000/oauth2/token",
  "jwks_uri": "http://127.0.0.1:9000/oauth2/jwks"
}
~~~

Đây là **trích yếu**; discovery document thật có nhiều metadata khác như grant types, algorithms, scopes và UserInfo endpoints.

JWK Set:

~~~bash
curl -i http://127.0.0.1:9000/oauth2/jwks
~~~

Một phần response:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "<generated-key-id>",
      "n": "<public-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Public JWKS không được lộ RSA private params như `d`, `p`, `q`.

### 17.1. Nếu discovery 404

Kiểm tra OIDC configurer `oidc()`, Authorization Server chain/order và compatibility. Đừng khởi động Portal trước khi Provider discovery trả đúng issuer, vì Portal sẽ dùng `issuer-uri` để tìm metadata khi xây ClientRegistration.

## 18. portal-client: dependencies

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Portal **không cần** Authorization Server starter; nó chỉ đóng vai Relying Party/OAuth2 Client.

## 19. portal-client: application.yml

~~~yaml
server:
  port: 8080
  servlet:
    session:
      cookie:
        name: PORTALSESSION
        http-only: true

spring:
  security:
    oauth2:
      client:
        registration:
          local-idp:
            provider: local-idp
            client-id: portal-client
            client-secret: portal-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          local-idp:
            issuer-uri: http://127.0.0.1:9000
~~~

| Portal field | Provider must match |
|---|---|
| `client-id: portal-client` | RegisteredClient.clientId |
| `client-secret: portal-secret` | Credential hash at OP |
| `client_secret_basic` | Allowed client authentication method |
| `authorization_code` | Allowed grant type |
| `redirect-uri` | Exact registered redirect URI |
| `scope: openid/...` | Registered scopes |
| `issuer-uri` | AuthorizationServerSettings.issuer |

### 19.1. Registration ID không phải client ID

`local-idp` được Spring Client dùng làm khóa để khởi tạo login:

~~~text
/oauth2/authorization/local-idp
/login/oauth2/code/local-idp
~~~

Còn `portal-client` được gửi tới OP qua `client_id`.

### 19.2. Client secret này chỉ dùng local

Production nên dùng `client-secret: ${PORTAL_OIDC_CLIENT_SECRET}` và secret manager. Không copy chuỗi `portal-secret` sang public deployment.

## 20. portal-client: Spring Boot entry point

~~~java
package com.example.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortalClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortalClientApplication.class, args);
    }
}
~~~

## 21. portal-client: SecurityFilterChain và PKCE

Vì Provider yêu cầu PKCE, Portal cần thêm `code_challenge` trong authorization request ngay cả khi là confidential client.

~~~java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web
    .DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web
    .OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
        HttpSecurity http,
        ClientRegistrationRepository registrations
    ) throws Exception {
        var requestResolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations,
                "/oauth2/authorization"
            );
        requestResolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce()
        );

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().authenticated())
            .oauth2Login(oauth -> oauth
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(requestResolver))
                .defaultSuccessUrl("/me", false))
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

### 21.1. withPkce()

`OAuth2AuthorizationRequestCustomizers.withPkce()` thêm PKCE challenge và giữ verifier để trao đổi code tại token endpoint. Nếu thiếu, Provider với `requireProofKey(true)` sẽ từ chối flow theo chính sách.

### 21.2. PKCE không thay state hoặc nonce

PKCE gắn authorization code với client initiating request; `state` giúp chống login CSRF/correlation, còn `nonce` gắn ID Token với OIDC request. Ba yếu tố bổ sung cho nhau.

### 21.3. Không bật STATELESS cho browser OIDC login

Default AuthorizationRequestRepository dùng session để giữ state/nonce/verifier; Browser login còn cần authenticated session sau callback. Đừng dùng `SessionCreationPolicy.STATELESS` máy móc ở Portal.

### 21.4. CSRF

POST endpoints dùng session cookie nên cần chính sách CSRF riêng. Ví dụ không tắt CSRF trên Portal.

## 22. portal-client: HomeController

~~~java
package com.example.portal;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HomeController {

    @GetMapping("/")
    public String home() {
        return """
            Local OIDC Portal
            Start login: /oauth2/authorization/local-idp
            After login: /me
            """;
    }

    @GetMapping("/me")
    public Map<String, Object> me(
        @AuthenticationPrincipal OidcUser user
    ) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("subject", user.getSubject());
        result.put("issuer", user.getIssuer().toString());
        String display = user.getFullName();
        if (display == null) {
            display = user.getPreferredUsername();
        }
        result.put("displayName", display);
        result.put("authorities", user.getAuthorities()
            .stream()
            .map(a -> a.getAuthority())
            .toList());
        return result;
    }
}
~~~

Không trả ID Token, access token hoặc refresh token ra HTTP response. Để test login, chỉ cần subject, issuer, displayName và một số authorities.

### 22.1. Subject chỉ có nghĩa trong issuer namespace

`sub` có thể trùng giữa hai issuers; user identity mapping nên dùng `(iss, sub)` hoặc internal mapping đã xác minh, không mặc định email là khóa bất biến.

### 22.2. ROLE_ADMIN không tự xuất hiện

Provider có user `admin` không đồng nghĩa Portal có `ROLE_ADMIN`. Portal phải map verified claims/tenant membership đúng policy nếu cần RBAC.

### 22.3. UserInfo claims có thể thiếu

`name`, `email` tùy provider/scope/consent. Controller nên có fallback khi optional claim null.

## 23. Khởi động Portal

Khi Provider đã chạy:

~~~bash
cd oidc-local-lab/portal-client
./gradlew bootRun
~~~

Windows:

~~~powershell
cd oidc-local-lab\portal-client
.\gradlew.bat bootRun
~~~

Portal lắng nghe cổng 8080 và đọc OIDC discovery từ Provider.

### 23.1. Nếu Portal không boot

Kiểm tra:

~~~text
GET http://127.0.0.1:9000/.well-known/openid-configuration
~~~

Nếu provider chưa chạy hoặc issuer metadata khác cấu hình, Spring Boot có thể không tạo được ClientRegistrationRepository.

## 24. Đăng nhập end-to-end bằng browser

Thực hiện:

1. Mở `http://127.0.0.1:8080/`.
2. Đi tới `http://127.0.0.1:8080/oauth2/authorization/local-idp`.
3. Browser redirect sang Provider `http://127.0.0.1:9000/oauth2/authorize`.
4. Đăng nhập `alice / alice-pass`.
5. Chấp thuận scopes khi OP hỏi consent.
6. Browser chuyển về callback `/login/oauth2/code/local-idp?code=...&state=...` trên Portal.
7. Portal backend đổi code lấy token và xác minh ID Token.
8. Portal lưu authenticated session, đưa browser tới `/me`.

JSON response minh họa:

~~~json
{
  "subject": "alice",
  "issuer": "http://127.0.0.1:9000",
  "displayName": "alice",
  "authorities": [
    "OIDC_USER",
    "SCOPE_openid"
  ]
}
~~~

Đây là **minh họa**, không phải tập authorities cố định: các scopes/authority mapping khác nhau theo configuration/version.

### 24.1. Network Developer Tools

Quan sát các request/redirect:

~~~text
GET :8080/oauth2/authorization/local-idp  -> 302
GET :9000/oauth2/authorize?...            -> login/consent
GET :8080/login/oauth2/code/local-idp?... -> 302 /me
GET :8080/me                              -> 200
~~~

Không chia sẻ HAR dump chưa redact: URLs có authorization codes và requests có session cookies.

## 25. Nhìn kỹ Authorization Request

Redirect sang OP thường chứa:

~~~text
response_type=code
client_id=portal-client
redirect_uri=http://127.0.0.1:8080/login/oauth2/code/local-idp
scope=openid profile email orders.read
state=<random-value>
nonce=<random-oidc-nonce>
code_challenge=<S256-derived-value>
code_challenge_method=S256
~~~

### 25.1. response_type=code

Chúng ta đang dùng Authorization Code Flow. Token endpoint được gọi từ backend; không gửi client secret xuống browser JavaScript.

### 25.2. state

Ràng buộc callback với authorization request trước đó, giúp ngăn login CSRF/mix-up. Nếu state bị thay, callback phải bị từ chối.

### 25.3. nonce

Ràng buộc ID Token với authentication request trong OIDC. Spring Security kiểm tra nonce sau token exchange.

### 25.4. PKCE

`code_challenge` là giá trị derive từ `code_verifier`; verifier được gửi khi Portal đổi code lấy token. Không gửi raw verifier trên browser redirect.

### 25.5. redirect_uri

OP phải đối chiếu URI với RegisteredClient allowlist. Không dùng `redirect_uri` tùy ý do browser supply để chuyển code sang external URL.

## 26. Backend token request

Portal backend sẽ POST:

~~~http
POST /oauth2/token HTTP/1.1
Host: 127.0.0.1:9000
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <redacted-client-credentials>

grant_type=authorization_code&
code=<one-time-code>&
redirect_uri=http%3A%2F%2F127.0.0.1%3A8080%2Flogin%2Foauth2%2Fcode%2Flocal-idp&
code_verifier=<original-verifier>
~~~

Response:

~~~json
{
  "access_token": "<redacted>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email orders.read",
  "id_token": "<signed-jwt>",
  "refresh_token": "<optional>"
}
~~~

OP xác minh client auth, code, redirect URI và PKCE. `refresh_token` có thể không hiện diện tùy grant/OP policy. Không dùng raw token response trong logs hay JSON endpoint công khai.

## 27. ID Token khác Access Token

| Token | Đối tượng sử dụng | Cần kiểm tra |
|---|---|---|
| ID Token | Relying Party/Portal | `iss`, `aud=portal-client`, expiry, signature, nonce |
| Access Token | Resource Server, UserInfo | Issuer/signature/expiry, scopes, audience/resource policy |
| Refresh Token | OAuth Client và token endpoint | Storage, rotation, revocation, refresh grant |

### 27.1. Không coi decode JSON là verification

Base64url decode JWT payload không xác minh chữ ký. Portal phải dùng Spring Security OIDC decoder/trusted JWKS, kiểm tra issuer, audience, expiration, nonce.

### 27.2. OIDC ID Token audience là OAuth client ID

ID Token có `aud=portal-client`, không phải mặc định `orders-api`. Access token cho Orders API có resource audience policy riêng.

### 27.3. ID Token sai phải từ chối

Token hết hạn, issuer sai, audience không chứa Portal client ID hoặc signature sai phải bị từ chối. Không “cho qua” nếu email/sub trông đúng.

## 28. UserInfo endpoint

Tìm trong discovery:

~~~bash
curl -s http://127.0.0.1:9000/.well-known/openid-configuration
~~~

UserInfo thường công bố URL như:

~~~text
http://127.0.0.1:9000/userinfo
~~~

Gọi UserInfo bằng access token:

~~~http
GET /userinfo HTTP/1.1
Host: 127.0.0.1:9000
Authorization: Bearer <redacted-access-token>
~~~

### 28.1. Không dùng ID Token làm Bearer token

UserInfo dùng access token, không phải ID Token. Resource Server/API cũng dùng access token theo policy, không chấp nhận ID Token chỉ vì token có `sub`.

### 28.2. Claims phụ thuộc scopes/consent

Không tự tin `email` hiện diện hoặc verified. Provider phải tuân thủ privacy/consent; Portal cần xử lý optional claims.

### 28.3. Subject phải nhất quán

OIDC UserInfo `sub` phải trùng subject của ID Token cho login đang xét. Không ghép attributes của user khác vào session.

## 29. OAuth2AuthorizedClient của Portal

Sau login, Portal có thể giữ:

~~~text
OAuth2AuthenticationToken:
  principal = Alice
  registrationId = local-idp

OAuth2AuthorizedClient:
  registrationId = local-idp
  principalName = Alice's stable name
  accessToken = value + scopes + expiration
  refreshToken = optional
~~~

Controller để quan sát metadata (không tiết lộ token):

~~~java
@GetMapping("/token-info")
public Map<String, Object> tokenInfo(
    @RegisteredOAuth2AuthorizedClient("local-idp")
    OAuth2AuthorizedClient client
) {
    return Map.of(
        "registrationId",
        client.getClientRegistration().getRegistrationId(),
        "expiresAt",
        client.getAccessToken().getExpiresAt().toString(),
        "scopes",
        client.getAccessToken().getScopes()
    );
}
~~~

Cần imports `OAuth2AuthorizedClient` và `@RegisteredOAuth2AuthorizedClient` từ Spring Security Client. Đây là **lab-only endpoint**; production không cần expose token metadata nếu không có use case.

### 29.1. AuthorizedClient không phải Browser session

SecurityContext giữ authenticated browser principal; OAuth2AuthorizedClientRepository/Service giữ token grant theo registration/principal. Chúng liên quan nhưng không phải một object duy nhất.

### 29.2. Khi nhiều registrations

Không dùng token của registration A để gọi API dành cho B. Test `registrationId`, principal, scopes và outbound Authorization header.

## 30. Optional: thêm Orders Resource Server cổng 8081

Để thấy access token hoạt động, thêm ứng dụng:

~~~text
Portal :8080
  -> Authorization: Bearer access_token
Orders API :8081
  -> Validate issuer/JWKS/exp/scope/audience
  -> GET /orders
~~~

Dependencies Orders API:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation(
        "org.springframework.boot:spring-boot-starter-oauth2-resource-server"
    )
}
~~~

application.yml:

~~~yaml
server:
  port: 8081

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: http://127.0.0.1:9000
~~~

SecurityFilterChain:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/orders")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .csrf(csrf -> csrf.disable())
        .oauth2ResourceServer(server -> server
            .jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

**Lưu ý:** tắt CSRF ở đây chỉ minh họa Bearer-only stateless API, không phải Portal browser session. Production Resource Server cần thêm **audience/resource validation**; issuer + scopes không luôn đủ.

### 30.1. Access-token audience

Spring Authorization Server token customization có thể bổ sung audience theo Resource Server. Orders API phải dùng validator phù hợp, không chỉ tin mọi JWT do OP ký cho bất kỳ Resource Server nào.

## 31. Portal gọi API bằng RestClient

Với Spring Security 6.4+ có `OAuth2ClientHttpRequestInterceptor`:

~~~java
@Bean
RestClient ordersClient(
    RestClient.Builder builder,
    OAuth2AuthorizedClientManager manager
) {
    OAuth2ClientHttpRequestInterceptor oauth =
        new OAuth2ClientHttpRequestInterceptor(manager);

    return builder
        .baseUrl("http://127.0.0.1:8081")
        .requestInterceptor(oauth)
        .build();
}
~~~

Chọn registration:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver
    .clientRegistrationId;

String orders = restClient.get()
    .uri("/orders")
    .attributes(clientRegistrationId("local-idp"))
    .retrieve()
    .body(String.class);
~~~

Đây là fragment tích hợp: cần manager/repository đúng Servlet request principal. Nếu dùng WebClient, có `ServletOAuth2AuthorizedClientExchangeFilterFunction`.

### 31.1. Không forward token sang host tùy ý

Không lấy untrusted request parameter như `?target=https://attacker.example` rồi đính Bearer token. Resource destination và registration phải được ràng buộc bởi trusted allowlist.

### 31.2. Phân biệt 401/403/429/5xx từ downstream

`401 invalid_token` có thể là token issue; `403 insufficient_scope` là permission; `429` và `5xx` là rate limiting/availability. Không refresh token vô hạn hay logout browser trên mọi lỗi.

## 32. Logout: hai sessions khác nhau

Sau login browser có:

~~~text
PORTALSESSION = session ở Portal :8080
IDPSESSION    = session ở Provider :9000
~~~

Nếu logout **chỉ tại Portal**, IDPSESSION có thể còn hiệu lực. Lần login sau Browser được redirect tới Provider và có thể không cần nhập password.

### 32.1. Local logout

Spring Security bảo vệ logout POST theo CSRF policy. Không tự biến `/logout` thành GET vô điều kiện trong production.

### 32.2. OIDC RP-initiated logout

Nếu OP công bố end-session endpoint phù hợp, Portal có thể dùng `OidcClientInitiatedLogoutSuccessHandler` để redirect browser sang OP logout flow.

### 32.3. Token revocation

Local session logout, authorized-client token removal/revocation và OP SSO session termination là **ba lifecycle khác nhau**. Không mặc định một hành động sẽ kết thúc cả ba.

## 33. Tại sao cookie names riêng là bắt buộc trong lab?

Nếu cả Portal và Provider cùng set:

~~~http
Set-Cookie: JSESSIONID=...; Path=/
~~~

trên host `127.0.0.1`, browser không dựa vào port để tách cookies. Một response của Provider có thể thay JSESSIONID của Portal, khiến original OAuth2AuthorizationRequest bị mất:

~~~text
GET /oauth2/authorization/local-idp
  -> Portal stores state/nonce in session

Provider login sets same cookie name JSESSIONID
  -> Browser overwrites Portal session cookie

Callback to Portal
  -> Portal cannot find original request
  -> authorization_request_not_found / invalid_state
~~~

Sử dụng:

~~~yaml
# Provider
server.servlet.session.cookie.name: IDPSESSION

# Portal
server.servlet.session.cookie.name: PORTALSESSION
~~~

Nếu browser đã lưu cookies từ lần thử trước, xóa riêng cookies cho local lab origins hoặc dùng private browsing profile sạch.

### 33.1. Không tắt state validation để sửa lỗi cookie

Lỗi state/cookie phải giải quyết ở session isolation, hostname, cookie Path/SameSite/Secure hoặc load-balancing; không bỏ state/nonce để callback đi tiếp.

## 34. Redirect URI, PKCE và session correlation

Provider cho phép:

~~~text
http://127.0.0.1:8080/login/oauth2/code/local-idp
~~~

Portal tạo URI này từ:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

### 34.1. Thay port 8080 bằng 8082

Nếu chỉ đổi port Portal, OP phải từ chối redirect URI chưa đăng ký. Sửa cả hai phía một cách có chủ đích, không dùng wildcard redirects.

### 34.2. Bỏ PKCE customizer

Với Provider `requireProofKey(true)`, Authorization Code request thiếu challenge hoặc token request thiếu verifier phải bị từ chối. Khôi phục `withPkce()`, không tắt validation để che lỗi.

### 34.3. Double submit hoặc nhiều tabs

Authorization codes dùng một lần. Multiple browser tabs có thể chứa các state/nonce riêng; repository/session phải giữ đúng correlation. Không hard-code một state/nonce toàn cục.

## 35. Mô hình test tự động

Đừng đánh đồng các cấp độ test:

| Test type | Mục đích |
|---|---|
| Unit test Provider components | Token customizer, authority mapping, RegisteredClient policy |
| Discovery/JWKS smoke | OP public metadata và public keys |
| MockMvc `oidcLogin()` | Portal controller nhận OidcUser giả |
| Fake OP + MockMvc integration | Spring Security code exchange, state/nonce/JWT validation |
| Two real local apps | Browser redirect, cookies, consent, login |
| Resource Server integration | Access token issuer/signature/audience/scope |
| Browser E2E | SameSite, redirect chain, actual cookie behavior |

### 35.1. Discovery smoke test

~~~java
@Test
void discoveryHasExpectedIssuer() {
    RestClient rest = RestClient.create();
    Map<?, ?> metadata = rest.get()
        .uri("http://127.0.0.1:9000/.well-known/openid-configuration")
        .retrieve()
        .body(Map.class);

    assertThat(metadata.get("issuer"))
        .isEqualTo("http://127.0.0.1:9000");
    assertThat(metadata).containsKey("jwks_uri");
}
~~~

Đây là smoke test phụ thuộc Provider đang chạy. Trong CI, hãy dùng ephemeral port và injected URL/fixture lifecycle.

### 35.2. MockMvc controller test không thực sự login

~~~java
@WebMvcTest(HomeController.class)
class HomeControllerTest {
    @Autowired MockMvc mvc;

    @Test
    void displaysSubject() throws Exception {
        mvc.perform(get("/me")
                .with(oidcLogin().idToken(token ->
                    token.claim("sub", "employee-42"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject")
                .value("employee-42"));
    }
}
~~~

`oidcLogin()` tạo mock Authentication, không chạy OP/token endpoint/signature check. Để test ID Token validation, phát JWT được ký thật từ fake OP và đi qua callback.

## 36. Ma trận negative tests

| Thao tác | Expected behavior |
|---|---|
| Provider chưa chạy | Discovery/connect error |
| Portal issuer URI khác OP issuer | Discovery/ID Token validation failure |
| Portal client ID sai | Invalid client |
| Portal client secret sai | Invalid client tại token endpoint |
| Registered redirect URI thiếu | Authorization request rejected |
| Scope openid bị bỏ | Không còn OIDC login/ID Token như kỳ vọng |
| PKCE code_challenge thiếu | OP từ chối khi requireProofKey |
| PKCE verifier không khớp | Token exchange rejected |
| Callback state bị đổi | Login rejected; không authenticated |
| Callback không có PORTALSESSION | Original authorization request missing |
| Fake OP phát ID Token wrong nonce | Login rejected |
| Fake OP phát expired ID Token | Login rejected |
| Fake OP phát wrong iss/aud | Login rejected |
| Fake OP ký bằng untrusted key | Login rejected |
| Consent bị từ chối | Controlled OAuth error; không login |
| Access token thiếu orders.read | Orders API 403 |
| Token hết hạn/sai chữ ký tới API | Orders API 401 |

**Nguyên tắc test:** valid control phải thành công. Mỗi negative case chỉ thay một yếu tố, để biết chính xác lỗi đến từ issuer, client authentication, PKCE, state hay signature.

## 37. Troubleshooting theo từng lớp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Cổng 9000 bận | Process khác chiếm cổng | Đổi port đồng bộ issuer/config |
| Portal boot fail | Discovery không truy cập được | Start Provider trước |
| Discovery 404 | OIDC chưa bật | Kiểm tra `.oidc(...)` |
| JWK Set 404 | JWKSource/chain sai | Đăng ký key và matcher |
| Login form Provider không hiện | Form login chain thiếu | @Order(2) + formLogin |
| Authorization 400 | clientId/scope/redirect | RegisteredClient settings |
| invalid_client | Secret hoặc auth method sai | Đồng bộ client-secret-basic |
| invalid_request PKCE | Challenge/verifier thiếu | withPkce ở Portal |
| Consent lặp | In-memory consent mất khi restart | Lab limitation/persistence |
| authorization_request_not_found | Cookie session mất | PORTALSESSION và host/path |
| invalid_state | State không khớp original request | Giữ callback/session |
| invalid_redirect_uri | Port/host/path khác | Exact RegisteredClient redirect |
| ID Token invalid issuer | URI khác giữa OP/RP | Exact issuer |
| ID Token invalid audience | client ID khác | Correct audience/clientId |
| ID Token bad signature | Signing key/JWKS mismatch | Trusted public key/current kid |
| ID Token nonce fail | Correlation sai | Không bỏ nonce validation |
| UserInfo 401 | Access token sai/hết hạn | Bearer auth/OP endpoint |
| Portal logout nhưng OP vẫn login | IDPSESSION còn | RP-initiated OP logout |
| API trả 401 | JWT iss/exp/signature/audience sai | Resource Server decoder |
| API trả 403 | Thiếu scope/permission | Consent/policy |
| Provider restart làm token fail | Ephemeral signing key/store | Test reset; prod persistent key |

## 38. Cây quyết định debug

~~~text
Cannot complete local OIDC login
  |
  v
Provider discovery http://127.0.0.1:9000/.well-known/openid-configuration?
  |-- No -> fix OP .oidc(), chain and server startup.
  |
  v
Provider public /oauth2/jwks?
  |-- No -> fix JWKSource / JwtDecoder / OP config.
  |
  v
Portal /oauth2/authorization/local-idp redirects?
  |-- No -> ClientRegistration / oauth2Login / filter chain.
  |
  v
Redirect client_id, redirect_uri, scope, state, nonce, PKCE valid?
  |-- No -> fix registration and request resolver.
  |
  v
Provider user login and consent succeed?
  |-- No -> formLogin / user store / scope policy.
  |
  v
Callback same PORTALSESSION and original state?
  |-- No -> browser cookies / host mismatch.
  |
  v
Backend POST /oauth2/token succeeds?
  |-- No -> client secret, code, redirect, PKCE verifier.
  |
  v
ID Token iss/aud/exp/signature/nonce verified?
  |-- No -> issuer/JWKS/token validator.
  |
  v
Portal /me shows principal?
  |-- No -> authenticated session / controller mapping.
~~~

## 39. Giới hạn của môi trường in-memory

Provider mẫu dùng:

~~~text
InMemoryRegisteredClientRepository
InMemoryUserDetailsManager
In-memory authorization/consent support
RSA signing key sinh ở startup
HTTP loopback
Demo credentials và client secret
~~~

### 39.1. Restart làm thay đổi state

Signing key, authorizations, consents và sessions có thể mất hoặc thay. Token được phát trước restart có thể không xác minh được bằng key mới. Đây là giới hạn demo, không phải pattern production.

### 39.2. Không scale provider replicas bằng memory store độc lập

Nếu hai instances giữ keys/authorizations khác nhau, callback/token validation có thể không nhất quán. Production cần shared/persistent stores, stable issuer và signing key management.

## 40. Từ lab đến môi trường thật

| Hạng mục | Local | Production |
|---|---|---|
| Issuer | HTTP 127.0.0.1 | HTTPS public fixed URI |
| Client secret | Demo plaintext | Managed secret, rotation |
| Client repository | In-memory | Persistent JDBC/custom |
| Consent/authorization store | In-memory demo | Persistent/shared |
| Users | Demo passwords | Real directory/MFA/password policy |
| Signing key | New RSA key each restart | Managed keys + rotation/JWKS |
| Sessions | Two local cookies | Secure/HttpOnly/SameSite and shared store as needed |
| Scopes | Demo values | Least privilege/consent |
| Audience | Simplified | Explicit resource audience validation |
| Logout | Local only or optional OP flow | Tested OIDC SSO logout lifecycle |
| Audit | Console | Redacted structured logs/metrics |
| Ingress | Direct loopback | Trusted forwarded headers and proxy |
| Testing | Browser manual smoke | CI protocol/security negative tests |

**Không triển khai những demo user/passwords, HTTP issuer và ephemeral signing keys ra Internet.** Với provider thực, cần threat modeling, secure key storage, account/MFA policy, user lifecycle, DPoP/mTLS nếu contract yêu cầu, rate limits, monitoring, recovery và security review.

## 41. Bài tập 1 — login thành công

Khởi động hai apps, truy cập `/oauth2/authorization/local-idp`, đăng nhập Alice và tới `/me`.

**Câu hỏi:** Vì sao Portal không biết password của Alice?

**Đáp án:** Password đi đến Provider; Portal nhận code, trao đổi backend với OP và xác minh ID Token.

## 42. Bài tập 2 — redirect URI mismatch

Đổi Portal cổng 8080 thành 8082 nhưng giữ Provider RegisteredClient redirect ở 8080.

**Expected:** OP từ chối redirect URI chưa đăng ký. Không dùng wildcard redirect để “chữa”.

## 43. Bài tập 3 — thiếu PKCE

Giữ Provider `requireProofKey(true)`, bỏ `withPkce()` khỏi Portal.

**Expected:** authorization/token request bị từ chối nếu challenge/verifier thiếu. Khôi phục PKCE customizer thay vì tắt policy.

## 44. Bài tập 4 — hai JSESSIONID trùng tên

Thử dùng cookie `JSESSIONID` ở cả Provider/Portal trên `127.0.0.1`.

**Expected:** Cookie collision có thể khiến state/session bị mất. Khôi phục `IDPSESSION` và `PORTALSESSION`.

## 45. Bài tập 5 — thêm claim vào ID Token

Trong `OAuth2TokenCustomizer`, thêm:

~~~java
context.getClaims().claim("department", "engineering");
~~~

**Câu hỏi:** Claim này có tự cấp quyền xem engineering reports không?

**Đáp án:** Không. Business authorization vẫn cần trusted membership/authority mapping.

## 46. Bài tập 6 — kiểm tra consent và UserInfo

Đăng nhập với scopes khác nhau; quan sát consent và claims UserInfo/ID Token.

**Câu hỏi:** Có được tự phát `email_verified=true` từ demo username không?

**Đáp án:** Không. Chỉ phát claim verified khi có nguồn xác minh thật.

## 47. Bài tập 7 — refresh token

Giảm access-token TTL và quan sát authorized-client manager khi token hết hạn hoặc gần hết hạn.

**Câu hỏi:** Vì sao có thể không có refresh token?

**Đáp án:** Registered grant type chưa đảm bảo cấp refresh; còn phụ thuộc OP policy, consent và token lifecycle. App cũng cần đúng manager/provider/persistence.

## 48. Bài tập 8 — Orders API

Tạo Resource Server :8081 yêu cầu `SCOPE_orders.read`.

**Expected:**

- Không Bearer token: 401.
- Token hết hạn/sai chữ ký/issuer: 401.
- Token hợp lệ nhưng thiếu scope: 403.
- Token được cấp đúng quyền, issuer/audience: 200.

**Nhắc lại:** API phải kiểm tra resource audience phù hợp, không chỉ issuer và scope.

## 49. Bài tập 9 — thêm registration thứ hai

Tạo RegisteredClient `portal-admin-client`, ClientRegistration `local-admin-idp` và callback:

~~~text
http://127.0.0.1:8080/login/oauth2/code/local-admin-idp
~~~

**Câu hỏi:** Có dùng ID Token audience `portal-client` để đăng nhập client mới không?

**Đáp án:** Không. Audience phải chứa đúng client ID của registration đích.

## 50. Bài tập 10 — logout và restart

Logout chỉ tại Portal, đăng nhập lại, sau đó restart Provider.

**Quan sát:** IDPSESSION có thể giúp re-login mà không hỏi password; restart có thể làm mất OP session/consent và đổi RSA signing key.

**Câu hỏi:** Tại sao production cần persistent keys/authorization store và OIDC logout policy?

**Đáp án:** Để bảo đảm token verification, session continuity, key rotation và SSO termination đúng contract.

## 51. Checklist hoàn thành

| Hạng mục | Yêu cầu |
|---|---|
| Provider chạy :9000 | Có |
| Portal chạy :8080 | Có |
| Issuer exact `127.0.0.1:9000` | Có |
| Session cookies riêng | IDPSESSION, PORTALSESSION |
| Authorization Server OIDC enabled | Có |
| Discovery trả issuer/JWKS URI đúng | Có |
| Public JWKS không lộ private key | Có |
| RegisteredClient.clientId | portal-client |
| Client secret và method khớp Portal | Có |
| Authorization Code grant | Có |
| Redirect URI chính xác | Có |
| OIDC openid scope | Có |
| Consent được xử lý | Có |
| Provider yêu cầu PKCE | Có |
| Portal gửi PKCE challenge/verifier | Có |
| Demo users có thể login | Có |
| state/nonce được giữ qua callback | Có |
| ID Token được validate đầy đủ | Có |
| Portal /me hiển thị safe OIDC principal | Có |
| Không expose raw tokens/secrets | Có |
| AuthorizedClient chọn đúng registration | Có |
| Resource Server audience/scopes (nếu thêm) | Có |
| Local/OP logout được phân biệt | Có |
| Restart làm đổi ephemeral signing keys được hiểu | Có |
| Negative tests được thử | Có |
| Không dùng HTTP/credentials demo trong production | Có |

## 52. Anti-pattern cần tránh

**1.** Tự làm OAuth2/OIDC Provider bằng một endpoint trả JWT tùy tiện, bỏ qua grant/protocol checks.

**2.** Dùng cùng JSESSIONID cho hai Servlet apps trên một hostname nhưng khác port.

**3.** Trộn localhost và 127.0.0.1 khi issuer/callback cần exact match.

**4.** Copy HTTP loopback issuer/secrets demo vào production.

**5.** Sinh signing key mới khi mọi production instance restart mà không có key rotation/persistence.

**6.** Tắt PKCE/state/nonce vì callback gặp lỗi.

**7.** Trả raw ID Token/access token trong `/me`.

**8.** Coi access token và ID Token có cùng audience và mục đích.

**9.** Coi OP role ADMIN tự chuyển thành Portal ROLE_ADMIN.

**10.** Bỏ CSRF cho browser session Portal.

**11.** Forward Bearer token đến bất kỳ URL do browser yêu cầu.

**12.** Chỉ test `oidcLogin()` rồi tuyên bố real OIDC callback/JWT signature đã đúng.

**13.** Bỏ resource audience validation vì JWT signature/issuer đã đúng.

**14.** Cho rằng local logout đồng nghĩa OP SSO logout và token revocation.

**15.** Đưa keys/authorization codes/cookies vào CI logs không redact.

## 53. Tài liệu tham khảo

- Spring Authorization Server Reference: https://docs.spring.io/spring-authorization-server/reference/
- Spring Authorization Server Getting Started: https://docs.spring.io/spring-authorization-server/reference/getting-started.html
- Spring Security OAuth2 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/
- Spring Security OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Code Grant: https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 PKCE: https://www.rfc-editor.org/rfc/rfc7636

Khi áp dụng các snippets cho dòng Spring Security hoặc Authorization Server mới, đối chiếu dependency starter, configuration classes và phương thức DSL với tài liệu của đúng major/minor version.

## 54. Tổng kết

Chúng ta vừa tự triển khai một OpenID Provider local bằng **Spring Authorization Server** và tích hợp một **Spring Security OAuth2/OIDC Client**:

~~~text
local-provider :9000
  RegisteredClient, demo user, consent
  Authorization Code + PKCE
  OIDC issuer/discovery/ID Token
  RSA signing key + public JWKS

portal-client :8080
  ClientRegistration issuer-uri
  oauth2Login + PKCE request resolver
  OIDC callback + ID Token validation
  authenticated browser session + OidcUser
~~~

Điểm mấu chốt không chỉ là trang `/me` trả 200. Người học cần hiểu **redirect, registered client và redirect URI, state, nonce, PKCE challenge/verifier, token endpoint, public JWKS, issuer/audience/signature validation, hai cookie sessions riêng và authorized-client lifecycle**.

Spring Authorization Server giúp ta tự quản lý OP mà không phải tự viết lại giao thức. Nhưng demo dùng HTTP loopback, demo passwords/secrets, stores in-memory và ephemeral RSA signing keys **không phải một thiết kế production**. Trước khi triển khai thật cần HTTPS, persistent stores, keys/secret management, identity/MFA policy, resource audience validation, rate limits, logout design, monitoring và kiểm thử bảo mật.

**Kết quả đạt yêu cầu:** Portal đăng nhập qua provider local với Authorization Code + PKCE, xác minh ID Token đúng chuẩn, nhận OIDC principal và lưu session; các tình huống sai issuer/client/redirect/state/PKCE/signature phải **bị từ chối**, không được “sửa” bằng cách bỏ validation.
