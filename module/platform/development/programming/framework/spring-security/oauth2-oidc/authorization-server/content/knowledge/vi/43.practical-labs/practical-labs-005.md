# Hoàn thiện OIDC SSO, ID Token, UserInfo và Logout

> **Chương: Thực hành tổng hợp.** Bài lab thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn hoàn thiện một luồng OpenID Connect có thể dùng cho nhiều ứng dụng web. Bạn sẽ cấu hình Spring Authorization Server làm OpenID Provider, đăng nhập từ hai relying party, kiểm tra ID Token, lấy thông tin người dùng qua UserInfo endpoint và thực hiện RP-Initiated Logout. Bài tập kết nối quản lý client, authorization code, PKCE, ký token, session và endpoint OIDC thành một luồng có thể chạy và kiểm thử.

Kết quả mong đợi là người dùng đăng nhập một lần tại Authorization Server, sau đó có thể mở ứng dụng web thứ hai trong cùng trình duyệt mà không phải nhập lại mật khẩu. Mỗi ứng dụng vẫn có session riêng; SSO xảy ra vì cả hai cùng tin cậy một OpenID Provider và trình duyệt còn session đăng nhập tại provider.

## 1. Mục tiêu và kiến trúc lab

Sau khi hoàn thành, bạn có thể:

1. Bật OpenID Connect trên Spring Authorization Server.
2. Đăng ký hai confidential web client dùng authorization code và PKCE.
3. Phát hành ID Token với subject ổn định và claim phù hợp với scope.
4. Cung cấp UserInfo endpoint có kiểm soát quyền truy cập claim.
5. Cấu hình Spring Security OAuth2 Login ở hai relying party.
6. Phân biệt local logout với RP-Initiated Logout.
7. Kiểm tra discovery metadata, chữ ký ID Token, nonce, UserInfo và logout redirect.

Kiến trúc sử dụng ba ứng dụng chạy local:

| Thành phần | Địa chỉ | Vai trò |
|---|---|---|
| Spring Authorization Server | `http://localhost:9000` | OpenID Provider, login session, authorization, token, UserInfo và end-session endpoint |
| Portal A | `http://localhost:8081` | Relying party thứ nhất |
| Portal B | `http://localhost:8082` | Relying party thứ hai |

~~~mermaid
flowchart TD
    U[Browser] --> A[Portal A :8081]
    U --> B[Portal B :8082]
    A -->|Authorization Code + PKCE| AS[Authorization Server :9000]
    B -->|Authorization Code + PKCE| AS
    AS --> LOGIN[Spring Security login session]
    AS --> TOK[ID Token + Access Token]
    AS --> UI[UserInfo endpoint]
    A -->|Bearer Access Token| UI
    B -->|Bearer Access Token| UI
    A -->|RP-Initiated Logout| AS
    B -->|RP-Initiated Logout| AS
~~~

Hai portal có client ID, secret và redirect URI riêng. Chúng cùng dùng một issuer. Trình duyệt giữ cookie session của Authorization Server trên host localhost; vì vậy khi Portal B chuyển hướng trình duyệt tới issuer, Authorization Server có thể nhận ra người dùng đã đăng nhập.

Trong lab, repository và signing key có thể chạy trong memory để giảm bước cài đặt. Khi triển khai thật, phải dùng persistence bền vững, khóa ký được quản lý an toàn và session store phù hợp. Không dùng cấu hình khóa tạm của lab cho production.

## 2. Chuẩn bị project

Tạo ba Spring Boot application riêng hoặc ba module trong cùng workspace:

- `authorization-server`
- `portal-a`
- `portal-b`

Dùng cùng một dòng Spring Boot/Spring Security tương thích với phiên bản Spring Authorization Server đã chọn. Ở Authorization Server, thêm dependency Spring Authorization Server và Spring Security. Ở mỗi portal, thêm Spring Web, Spring Security và OAuth2 Client.

Các dependency chính:

~~~xml
<!-- Authorization Server -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-oauth2-authorization-server</artifactId>
</dependency>

<!-- Mỗi relying party -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Dependency management phải lấy version từ Spring Boot BOM hoặc ma trận tương thích chính thức. Không trộn tùy ý Spring Security và Spring Authorization Server khác dòng version.

## 3. Cấu hình OpenID Provider

### 3.1. Bật OIDC endpoints

Authorization Server hỗ trợ OAuth 2.0 và OpenID Connect. Việc phát hành ID Token, discovery metadata, UserInfo và logout endpoint cần OIDC được bật rõ ràng trong configurer.

Ví dụ cấu hình filter chain theo API cấu hình phổ biến của Spring Authorization Server:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper)
            throws Exception {

        OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http);

        http.getConfigurer(OAuth2AuthorizationServerConfigurer.class)
                .oidc(oidc -> oidc
                        .userInfoEndpoint(userInfo ->
                                userInfo.userInfoMapper(userInfoMapper))
                        .logoutEndpoint(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated())
                .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Filter chain đầu tiên bảo vệ protocol endpoint của Authorization Server và bật OIDC UserInfo/logout. Filter chain thứ hai cung cấp login form cho người dùng. Nếu phiên bản Spring Authorization Server đang dùng có DSL mới hoặc đã thay đổi API cấu hình, điều chỉnh phần khởi tạo configurer theo tài liệu đúng phiên bản; các endpoint và nguyên tắc bảo mật của lab vẫn giữ nguyên.

OIDC logout của Authorization Server dùng `SessionRegistry` để tìm session đã xác thực cần kết thúc. Khai báo registry và publisher để registry nhận sự kiện khi HTTP session bị hủy:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class OidcSessionRegistryConfiguration {

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }
}
~~~

Với hệ thống nhiều instance, `SessionRegistryImpl` trong memory chỉ theo dõi session của một instance. Cần dùng session registry/store phân tán tương thích nếu browser có thể đăng nhập ở node khác hoặc logout phải tìm session trên toàn cụm.

OIDC cần scope `openid`. Nếu client chỉ yêu cầu OAuth scope như `orders.read` mà không yêu cầu `openid`, request đó không phải OIDC authentication request và không được kỳ vọng có ID Token.

### 3.2. Khai báo issuer

Issuer phải là URL công khai ổn định mà relying party dùng để khám phá metadata và xác minh token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Configuration
public class AuthorizationServerSettingsConfiguration {

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("http://localhost:9000")
                .build();
    }
}
~~~

Tất cả node của cùng một Authorization Server phải dùng cùng issuer. Khi chạy sau reverse proxy, cấu hình issuer theo URL bên ngoài và chỉ tin forwarded header từ proxy đáng tin cậy. Không để mỗi node tự tạo issuer từ hostname nội bộ.

### 3.3. Signing key và JWK Set

ID Token là JWT được ký. Relying party dùng public key được công bố qua JWKS để xác minh chữ ký. Ví dụ lab tạo RSA key khi khởi động:

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
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Configuration
public class SigningKeyConfiguration {

    @Bean
    JWKSource<SecurityContext> jwkSource() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair keyPair = generator.generateKeyPair();

        RSAKey rsaKey = new RSAKey.Builder(
                (RSAPublicKey) keyPair.getPublic())
                .privateKey((RSAPrivateKey) keyPair.getPrivate())
                .keyID(UUID.randomUUID().toString())
                .build();

        JWKSet jwkSet = new JWKSet(rsaKey);
        return (selector, context) -> selector.select(jwkSet);
    }

    @Bean
    JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
        return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
    }
}
~~~

Key được tạo mới sau mỗi lần restart chỉ phù hợp cho lab. Khi đó token cũ có thể không còn xác minh được bằng public key mới. Production cần lưu private key trong KMS/HSM hoặc secret store được bảo vệ, giữ `kid` ổn định, công bố public JWK đúng thời điểm và có quy trình rotation. Không commit private key vào source control hoặc đóng gói trong image container.

### 3.4. Tạo user đăng nhập lab

Để tập trung vào OIDC, lab dùng một user in-memory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class LabUserConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(passwordEncoder.encode("ChangeMe-OnlyForLab"))
                        .roles("USER")
                        .build());
    }
}
~~~

Đăng nhập bằng `alice` và mật khẩu lab ở trên. Không dùng tài khoản/mật khẩu này ở môi trường thật. Principal name trong ví dụ là `alice`; trong hệ thống thực, `Authentication.getName()` nên trả về một subject ID bất biến, duy nhất trong phạm vi issuer, thay vì email hoặc tên hiển thị có thể thay đổi.

## 4. Đăng ký hai relying party

Hai portal là confidential web client chạy ở server. Mỗi client có secret riêng, redirect URI riêng và post-logout redirect URI riêng.

~~~java
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration
public class RegisteredClientConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder passwordEncoder) {

        RegisteredClient portalA = createClient(
                "portal-a",
                "http://localhost:8081/login/oauth2/code/auth-server",
                "http://localhost:8081/",
                passwordEncoder);

        RegisteredClient portalB = createClient(
                "portal-b",
                "http://localhost:8082/login/oauth2/code/auth-server",
                "http://localhost:8082/",
                passwordEncoder);

        return new InMemoryRegisteredClientRepository(portalA, portalB);
    }

    private RegisteredClient createClient(
            String clientId,
            String redirectUri,
            String postLogoutRedirectUri,
            PasswordEncoder passwordEncoder) {

        return RegisteredClient.withId(UUID.randomUUID().toString())
                .clientId(clientId)
                .clientSecret(passwordEncoder.encode("LabSecret-" + clientId))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri(redirectUri)
                .postLogoutRedirectUri(postLogoutRedirectUri)
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .scope(OidcScopes.EMAIL)
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(false)
                        .build())
                .build();
    }
}
~~~

Hai client đều yêu cầu authorization code và PKCE. `requireProofKey(true)` buộc authorization request có PKCE challenge. Secret được mã hóa bằng cùng PasswordEncoder mà client authentication sử dụng. `requireAuthorizationConsent(false)` giúp lab tập trung vào SSO; nếu bật consent, Authorization Server cần có consent page và quy trình lưu quyết định của người dùng.

Ở relying party, `OAuth2AuthorizationRequestCustomizers.withPkce()` được gắn vào resolver để gửi code_challenge và code_verifier ngay cả khi client là confidential. Server yêu cầu PKCE nên hai phía phải cùng thực hiện bước này.

Redirect URI phải khớp chính xác với callback mà portal đăng ký. `postLogoutRedirectUri` cũng phải khớp giá trị được đăng ký cho client. Trong lab, dùng thống nhất `localhost`; không trộn `localhost` với `127.0.0.1` vì chúng là host khác nhau đối với redirect URI và cookie.

## 5. Phát hành claim trong ID Token

### 5.1. ID Token mang thông tin gì?

ID Token là chứng thực về kết quả xác thực người dùng dành cho client OIDC. Các claim chuẩn thường gồm:

| Claim | Ý nghĩa |
|---|---|
| `iss` | Issuer phát hành token |
| `sub` | Subject ổn định đại diện người dùng trong issuer |
| `aud` | Client hoặc audience được token dành cho |
| `exp` | Thời điểm hết hạn |
| `iat` | Thời điểm phát hành |
| `auth_time` | Thời điểm người dùng được xác thực nếu flow/policy cung cấp |
| `nonce` | Giá trị ràng buộc request và ID Token nếu client gửi nonce |
| `at_hash` / `c_hash` | Hash liên kết access token hoặc authorization code trong các trường hợp áp dụng |

Spring Authorization Server tạo các claim protocol như issuer, subject, audience, thời hạn và nonce theo flow. Không tự ghi đè `iss`, `aud`, `exp`, `iat`, `nonce`, `at_hash` hoặc `c_hash` trong customizer nếu không có yêu cầu protocol cụ thể.

### 5.2. Tạo nguồn profile

Tách profile người dùng khỏi token customizer để có thể thay nguồn in-memory bằng database hoặc identity service:

~~~java
public record UserProfile(
        String subject,
        String name,
        String preferredUsername,
        String email,
        boolean emailVerified) {
}

public interface UserProfileService {
    UserProfile findBySubject(String subject);
}
~~~

Trong lab, tạo implementation đơn giản trả profile cho subject `alice`:

~~~java
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class DemoUserProfileService implements UserProfileService {

    private final Map<String, UserProfile> profiles = Map.of(
            "alice",
            new UserProfile(
                    "alice",
                    "Alice Nguyen",
                    "alice",
                    "alice@example.test",
                    true));

    @Override
    public UserProfile findBySubject(String subject) {
        UserProfile profile = profiles.get(subject);
        if (profile == null) {
            throw new IllegalArgumentException("Unknown subject");
        }
        return profile;
    }
}
~~~

Giá trị `subject` phải trùng với `Authentication.getName()` trong lab. Trong production, ánh xạ principal sang một ID nội bộ ổn định; không dùng email làm `sub` nếu email có thể đổi hoặc được tái sử dụng.

### 5.3. Thêm claim theo scope

Dùng `OAuth2TokenCustomizer<JwtEncodingContext>` để bổ sung claim cho ID Token. Chỉ thêm claim khi client đã được cấp scope tương ứng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.oidc.OidcParameterNames;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration
public class IdTokenClaimsConfiguration {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> idTokenCustomizer(
            UserProfileService profiles) {

        return context -> {
            if (!OidcParameterNames.ID_TOKEN.equals(
                    context.getTokenType().getValue())) {
                return;
            }

            UserProfile profile = profiles.findBySubject(
                    context.getPrincipal().getName());

            if (context.getAuthorizedScopes().contains(OidcScopes.PROFILE)) {
                context.getClaims()
                        .claim("name", profile.name())
                        .claim("preferred_username", profile.preferredUsername());
            }

            if (context.getAuthorizedScopes().contains(OidcScopes.EMAIL)) {
                context.getClaims()
                        .claim("email", profile.email())
                        .claim("email_verified", profile.emailVerified());
            }
        };
    }
}
~~~

Customizer được gọi cho JWT token generation; điều kiện `ID_TOKEN` ngăn profile claim của ID Token bị thêm nhầm vào mọi access token. Ví dụ chỉ phát hành `name` và `preferred_username` khi có scope `profile`, và `email`/`email_verified` khi có scope `email`.

Không đưa mọi thuộc tính của user database vào ID Token. Chỉ phát hành claim cần thiết cho client, đúng scope và đúng consent. ID Token được gửi tới client; thông tin nhạy cảm không cần thiết nên được giữ ở UserInfo hoặc API riêng có authorization phù hợp.

## 6. Cấu hình UserInfo endpoint

UserInfo endpoint trả các claim về người dùng khi relying party gọi bằng access token hợp lệ. Đây là resource endpoint của OpenID Connect:

- Request dùng `Authorization: Bearer <access_token>`.
- Access token phải được cấp cho flow/client và còn hiệu lực.
- Server chỉ trả claim mà scope/authorization cho phép.
- Claim `sub` trong UserInfo phải khớp `sub` trong ID Token.
- Không dùng ID Token làm bearer token để gọi UserInfo.

Tạo mapper dựa trên authorization đã lưu:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.oidc.IdTokenClaimNames;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;

@Configuration
public class UserInfoConfiguration {

    @Bean
    Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
            UserProfileService profiles) {

        return context -> {
            OAuth2Authorization authorization = context.getAuthorization();
            UserProfile profile = profiles.findBySubject(
                    authorization.getPrincipalName());
            Set<String> scopes = authorization.getAuthorizedScopes();

            Map<String, Object> claims = new HashMap<>();
            claims.put(IdTokenClaimNames.SUB, profile.subject());

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.put("name", profile.name());
                claims.put("preferred_username", profile.preferredUsername());
            }

            if (scopes.contains(OidcScopes.EMAIL)) {
                claims.put("email", profile.email());
                claims.put("email_verified", profile.emailVerified());
            }

            return new OidcUserInfo(claims);
        };
    }
}
~~~

Mapper dùng `OAuth2Authorization` để lấy principal và authorized scopes. UserInfo luôn trả `sub`; các claim khác được giới hạn theo scope. Khi profile thay đổi, UserInfo có thể phản ánh dữ liệu mới từ profile service, trong khi ID Token cũ vẫn giữ claim tại thời điểm phát hành. Đây là một lý do để không coi ID Token như API profile có dữ liệu luôn mới nhất.

Nếu dùng custom mapper, hãy kiểm tra `sub` khớp chính xác với subject trong ID Token. Không trả claim cho scope mà client chưa được cấp. Kiểm tra access token thuộc đúng authorization/client và không chỉ dựa vào query parameter do client gửi.

## 7. Cấu hình Portal A và Portal B

### 7.1. application.yml

Portal A chạy ở port 8081 và dùng client `portal-a`:

~~~yaml
server:
  port: 8081

spring:
  application:
    name: portal-a
  security:
    oauth2:
      client:
        registration:
          auth-server:
            provider: auth-server
            client-id: portal-a
            client-secret: LabSecret-portal-a
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          auth-server:
            issuer-uri: http://localhost:9000
~~~

Portal B dùng cấu hình tương tự, nhưng đổi:

~~~yaml
server:
  port: 8082

spring:
  application:
    name: portal-b
  security:
    oauth2:
      client:
        registration:
          auth-server:
            provider: auth-server
            client-id: portal-b
            client-secret: LabSecret-portal-b
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          auth-server:
            issuer-uri: http://localhost:9000
~~~

Spring Security OAuth2 Client dùng `issuer-uri` để khám phá metadata OpenID Provider. Từ metadata, client tìm authorization endpoint, token endpoint, JWKS URI, UserInfo endpoint và end-session endpoint nếu provider công bố. Redirect URI do Spring tạo phải khớp URI đã đăng ký ở Authorization Server.

Trong production, client secret phải được cấp qua secret manager hoặc môi trường triển khai an toàn. Không commit secret lab vào repository công khai.

### 7.2. SecurityFilterChain cho relying party

Mỗi portal bật OAuth2 Login và cấu hình logout thành OIDC RP-Initiated Logout:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
public class PortalSecurityConfiguration {

    @Bean
    OAuth2AuthorizationRequestResolver pkceAuthorizationRequestResolver(
            ClientRegistrationRepository clientRegistrationRepository) {

        DefaultOAuth2AuthorizationRequestResolver resolver =
                new DefaultOAuth2AuthorizationRequestResolver(
                        clientRegistrationRepository, "/oauth2/authorization");
        resolver.setAuthorizationRequestCustomizer(
                OAuth2AuthorizationRequestCustomizers.withPkce());
        return resolver;
    }

    @Bean
    LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository clientRegistrationRepository) {

        OidcClientInitiatedLogoutSuccessHandler handler =
                new OidcClientInitiatedLogoutSuccessHandler(
                        clientRegistrationRepository);
        handler.setPostLogoutRedirectUri("{baseUrl}/");
        return handler;
    }

    @Bean
    SecurityFilterChain portalSecurityFilterChain(
            HttpSecurity http,
            LogoutSuccessHandler oidcLogoutSuccessHandler,
            OAuth2AuthorizationRequestResolver pkceAuthorizationRequestResolver)
            throws Exception {

        http.authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated())
                .oauth2Login(oauth2 -> oauth2
                        .authorizationEndpoint(endpoint ->
                                endpoint.authorizationRequestResolver(
                                        pkceAuthorizationRequestResolver)))
                .logout(logout ->
                        logout.logoutSuccessHandler(oidcLogoutSuccessHandler));

        return http.build();
    }
}
~~~

`OidcClientInitiatedLogoutSuccessHandler` tạo logout request tới end-session endpoint được khám phá từ metadata của provider. Handler dùng ID Token của phiên đăng nhập để gửi `id_token_hint`, cùng `post_logout_redirect_uri`. URI sau logout phải được đăng ký trên client ở Authorization Server.

Nếu provider không công bố `end_session_endpoint` hoặc không hỗ trợ RP-Initiated Logout, handler không thể hoàn tất luồng logout tại provider. Hãy kiểm tra discovery metadata và phiên bản Spring Authorization Server. Local logout mặc định chỉ xóa session tại portal.

### 7.3. Hiển thị thông tin đăng nhập

Controller nhận `OidcUser` do Spring Security tạo sau khi xác minh OIDC response. Để giữ ví dụ gọn, endpoint trả JSON các claim đã được xác minh:

~~~java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PortalController {

    @GetMapping("/")
    Map<String, Object> home(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "subject", user.getSubject(),
                "issuer", user.getIssuer().toString(),
                "name", user.getFullName() == null ? "" : user.getFullName(),
                "email", user.getEmail() == null ? "" : user.getEmail(),
                "idTokenClaims", user.getIdToken().getClaims(),
                "userInfoClaims", user.getUserInfo() == null
                        ? Map.of()
                        : user.getUserInfo().getClaims());
    }
}
~~~

Không hiển thị raw ID Token hoặc access token trên trang. Lab chỉ trả claim đã được Spring Security xác minh và UserInfo đã nhận. Ứng dụng thật cần kiểm soát claim nào được hiển thị, tránh lộ PII trong browser, log hoặc analytics.

## 8. Chạy lab theo thứ tự

### Bước 1: Khởi động Authorization Server

Chạy ứng dụng ở port 9000. Mở discovery document:

`http://localhost:9000/.well-known/openid-configuration`

Kiểm tra metadata có:

- `issuer` là `http://localhost:9000`.
- `authorization_endpoint` và `token_endpoint`.
- `jwks_uri`.
- `userinfo_endpoint`.
- `end_session_endpoint` khi OIDC logout được bật ở phiên bản đang dùng.

Mở `jwks_uri` lấy từ metadata và xác nhận có public key với `kid`. Không dựa vào việc đoán đường dẫn JWKS; dùng URI provider công bố.

### Bước 2: Khởi động Portal A

Chạy Portal A ở port 8081 và truy cập `http://localhost:8081/`.

1. Portal chuyển trình duyệt tới Authorization Server.
2. Authorization Server hiển thị login form.
3. Đăng nhập bằng user lab `alice`.
4. Browser quay lại callback của Portal A cùng authorization code.
5. Portal A đổi code lấy token bằng back-channel token request.
6. Spring Security xác minh ID Token và tạo local session.
7. Trang chủ hiển thị subject, issuer, name, email và UserInfo claims.

Lần đầu, người dùng có thể thấy màn hình consent nếu cấu hình client yêu cầu consent. Trong cấu hình lab đang dùng `requireAuthorizationConsent(false)` để bỏ qua bước đó.

### Bước 3: Khởi động Portal B và kiểm tra SSO

Chạy Portal B ở port 8082 và truy cập `http://localhost:8082/` trong cùng trình duyệt:

1. Portal B chuyển browser tới cùng issuer.
2. Authorization Server nhận cookie login session đã tạo khi dùng Portal A.
3. Nếu session còn hợp lệ và không có policy bắt buộc xác thực lại, Authorization Server không cần hỏi lại mật khẩu.
4. Authorization Server tạo authorization code cho client `portal-b`.
5. Portal B đổi code, xác minh ID Token và tạo local session riêng.

Portal B vẫn có authorization transaction và client ID riêng. SSO không có nghĩa Portal A chia sẻ session nội bộ hoặc access token cho Portal B. Mỗi relying party thực hiện authorization flow riêng với cùng OpenID Provider.

### Bước 4: Kiểm tra ID Token

Trong Portal A hoặc Portal B, kiểm tra các claim đã hiển thị:

| Claim | Kết quả mong đợi |
|---|---|
| `iss` | `http://localhost:9000` |
| `sub` | Subject ổn định của user lab (`alice`) |
| `aud` | Client ID của portal tương ứng |
| `exp` | Thời điểm trong tương lai khi vừa đăng nhập |
| `iat` | Thời điểm phát hành |
| `name` | `Alice Nguyen` khi scope `profile` được cấp |
| `email` | `alice@example.test` khi scope `email` được cấp |
| `email_verified` | `true` trong dữ liệu profile lab |

Hai portal có `aud` khác nhau vì mỗi ID Token dành cho một client. Không dùng ID Token của Portal A làm token đăng nhập cho Portal B. Portal B phải nhận ID Token của chính authorization flow mà nó khởi tạo.

Spring Security OIDC Login xác minh issuer, chữ ký, audience, thời hạn và các kiểm tra OIDC cần thiết, bao gồm nonce khi request sử dụng nonce. Không tự giải mã JWT rồi tin các claim mà bỏ qua xác minh chữ ký và validation.

### Bước 5: Kiểm tra UserInfo

Sau khi đăng nhập, Spring Security OIDC client có thể gọi UserInfo endpoint bằng access token nếu provider công bố endpoint và client có scope thích hợp. Trong JSON trang home, so sánh `userInfoClaims` với `idTokenClaims`.

Có thể kiểm tra thủ công bằng HTTP client/Postman:

~~~http
GET /userinfo HTTP/1.1
Host: localhost:9000
Authorization: Bearer ACCESS_TOKEN_CUA_PORTAL
Accept: application/json
~~~

Kết quả mong đợi có `sub` bằng subject trong ID Token. Các claim `name`, `preferred_username`, `email` và `email_verified` chỉ xuất hiện khi scope tương ứng được cấp và profile service có dữ liệu.

Không gửi ID Token vào header Bearer của UserInfo. UserInfo được bảo vệ bằng access token. Không chia sẻ token thật trong ảnh chụp, log hoặc tài liệu thực hành.

### Bước 6: Kiểm tra local logout

Để kiểm tra local logout riêng biệt, tạm thời cấu hình logout mặc định của Spring Security trong portal:

~~~java
http.logout(Customizer.withDefaults());
~~~

Local logout chỉ hủy session của Portal A. Mở Portal B nếu nó đã có local session, Portal B vẫn có thể đang đăng nhập. Nếu Portal B cần login lại sau local logout của A, đó không phải hành vi bắt buộc vì hai portal có session riêng.

### Bước 7: Kiểm tra RP-Initiated Logout

Sau khi hoàn tất phép thử local logout, khôi phục `OidcClientInitiatedLogoutSuccessHandler` trong cấu hình portal và kiểm tra:

1. Portal gửi logout request qua browser tới end-session endpoint trong metadata.
2. Request chứa `id_token_hint` và `post_logout_redirect_uri` đã đăng ký.
3. Authorization Server xác minh thông tin logout và kết thúc SSO session theo cấu hình.
4. Browser được chuyển về URI sau logout hợp lệ.
5. Khi truy cập một portal chưa có local session, portal chuyển tới Authorization Server; người dùng phải đăng nhập lại vì SSO session đã kết thúc.

Để kiểm thử sạch, hãy logout local ở cả hai portal trước khi thử lại. Nếu Portal B vẫn còn local session, nó có thể hiển thị trang đã đăng nhập mà chưa cần redirect tới Authorization Server. RP-Initiated Logout tại provider không tự động xóa mọi local session ở mọi relying party; muốn logout đồng bộ nhiều ứng dụng cần triển khai thêm cơ chế front-channel hoặc back-channel logout tương ứng.

## 9. Phân biệt ID Token, Access Token và UserInfo

| Thành phần | Mục đích | Nơi sử dụng | Cách xác minh/kiểm tra |
|---|---|---|---|
| ID Token | Chứng thực kết quả đăng nhập và danh tính cho OIDC client | Relying party | Xác minh chữ ký, issuer, audience, exp, nonce và các kiểm tra OIDC |
| Access Token | Cấp quyền truy cập resource/API | UserInfo endpoint hoặc resource server | Resource server kiểm tra token theo format và policy |
| UserInfo | Cung cấp claim về người dùng theo scope đã cấp | Relying party gọi bằng access token | Endpoint xác thực bearer token và trả `sub` khớp ID Token |

Không dùng ID Token để gọi API nghiệp vụ. Không coi access token là chứng cứ đăng nhập cho client. Không lấy claim từ UserInfo nếu chưa kiểm tra access token và subject binding.

## 10. Những điểm bảo mật cần kiểm tra

- **Subject ổn định:** `sub` phải duy nhất trong phạm vi issuer và không phụ thuộc email/tên hiển thị có thể thay đổi.
- **Issuer nhất quán:** ID Token, discovery metadata và cấu hình relying party phải dùng cùng issuer.
- **Audience đúng client:** Portal A chỉ chấp nhận ID Token dành cho Portal A.
- **Nonce:** khi client gửi nonce, ID Token phải mang nonce tương ứng và client phải xác minh.
- **PKCE:** authorization code flow sử dụng S256 challenge/verifier; không chấp nhận verifier không khớp.
- **Redirect URI:** so khớp chính xác với URI đã đăng ký; không dùng wildcard tùy tiện.
- **Scope và claim:** chỉ trả profile/email claim đã được cấp và được phép tiết lộ.
- **UserInfo subject:** `sub` của UserInfo phải trùng `sub` của ID Token trong cùng phiên.
- **Signing key:** private key được bảo vệ; public JWK được công bố đúng và có kế hoạch rotation.
- **Logout redirect:** chỉ chuyển hướng tới `post_logout_redirect_uri` đã đăng ký.
- **Session cookie:** dùng Secure, HttpOnly và SameSite phù hợp khi chạy HTTPS production.
- **CSRF:** giữ CSRF protection cho form logout và các thao tác web có session.
- **Token handling:** không log hoặc hiển thị raw ID Token/access token; lưu token theo cơ chế an toàn của ứng dụng.

## 11. Ma trận kiểm thử

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Discovery document được truy cập | Metadata trả đúng issuer và các endpoint OIDC |
| 2 | Client không yêu cầu `openid` | Request không được xử lý như OIDC authentication và không kỳ vọng ID Token |
| 3 | Portal A login lần đầu | User được xác thực và có local session |
| 4 | Portal B login trong cùng browser | Không cần nhập lại mật khẩu khi AS session còn hiệu lực |
| 5 | Portal B dùng client ID khác | ID Token có audience của Portal B |
| 6 | ID Token sai chữ ký | Relying party từ chối xác thực |
| 7 | ID Token sai issuer hoặc audience | Relying party từ chối token |
| 8 | ID Token hết hạn | Relying party từ chối token |
| 9 | Nonce không khớp | OIDC login thất bại |
| 10 | Authorization code dùng lại | Token endpoint từ chối code đã tiêu thụ |
| 11 | PKCE verifier sai | Token endpoint từ chối token request |
| 12 | Scope chỉ có `openid` | UserInfo không trả profile/email claim ngoài phạm vi |
| 13 | Scope có `profile` | UserInfo trả claim profile được phép |
| 14 | Scope có `email` | UserInfo trả email và trạng thái verified theo policy |
| 15 | UserInfo dùng ID Token làm bearer | Request bị từ chối |
| 16 | UserInfo access token không hợp lệ | Request bị từ chối |
| 17 | UserInfo `sub` khác ID Token `sub` | Relying party không được ghép hai danh tính |
| 18 | Local logout Portal A | Session A bị xóa; session B và AS session có thể vẫn tồn tại |
| 19 | RP-Initiated Logout với redirect URI không đăng ký | Authorization Server từ chối redirect không hợp lệ |
| 20 | RP-Initiated Logout thành công | AS SSO session kết thúc theo cấu hình |
| 21 | Truy cập portal sau AS logout và đã xóa local session | Browser phải xác thực lại tại AS |
| 22 | Restart Authorization Server dùng key tạm | Token cũ có thể không xác minh được; đây là giới hạn của lab |

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có ID Token | Client không yêu cầu `openid` hoặc OIDC chưa bật | Kiểm tra scope và `.oidc(...)` |
| Discovery không có UserInfo endpoint | OIDC chưa bật hoặc endpoint chưa được cấu hình | Kiểm tra OIDC configurer và metadata |
| Discovery không có end-session endpoint | Logout endpoint chưa bật hoặc phiên bản không hỗ trợ | Kiểm tra `.logoutEndpoint(...)` và phiên bản SAS |
| Portal A login được nhưng Portal B hỏi mật khẩu | Khác issuer/host, cookie AS không được gửi hoặc session hết hạn | Dùng cùng issuer/host, kiểm tra cookie và session |
| Portal B bị lỗi redirect_uri | URI trong RegisteredClient không khớp callback | So sánh chính xác scheme, host, port và path |
| Invalid client tại token endpoint | client_id/secret sai hoặc authentication method không khớp | Kiểm tra cấu hình hai phía và PasswordEncoder |
| ID Token không có name/email | Scope chưa được cấp hoặc customizer không thêm claim | Kiểm tra authorized scopes và profile service |
| UserInfo trả 401 | Thiếu access token, token hết hạn hoặc sai bearer token | Gửi access token đúng bằng Authorization header |
| UserInfo không có claim mong đợi | Mapper lọc scope hoặc profile không có dữ liệu | Kiểm tra authorized scopes và profile mapping |
| UserInfo subject khác ID Token subject | Mapping principal/subject không ổn định | Dùng cùng immutable subject cho hai luồng |
| Logout chỉ thoát khỏi portal | Portal đang dùng local logout mặc định | Cấu hình OIDC logout success handler |
| Logout redirect bị từ chối | post_logout_redirect_uri không được đăng ký chính xác | Khai báo URI tương ứng trong RegisteredClient |
| Logout AS xong nhưng portal kia vẫn hiện đăng nhập | Portal kia còn local session | Logout local portal đó hoặc triển khai front/back-channel logout |
| Token cũ lỗi sau restart | Signing key lab được tạo lại | Dùng key persistence ổn định ngoài môi trường lab |

## 13. Bài tập mở rộng

1. Thay `InMemoryUserDetailsManager` bằng user store trong database và dùng immutable user ID làm `sub`.
2. Thay `DemoUserProfileService` bằng profile service có phân quyền theo tenant.
3. Chỉ cho phép `email` claim khi email đã được xác minh.
4. Bật consent và xây consent page để người dùng chọn scope.
5. Bật refresh token rotation và kiểm thử replay.
6. Chuyển `RegisteredClientRepository` và `OAuth2AuthorizationService` sang JDBC.
7. Lưu signing key trong KMS/HSM và kiểm thử key rotation với nhiều `kid`.
8. Thêm front-channel hoặc back-channel logout cho các relying party cần logout đồng bộ.
9. Yêu cầu re-authentication cho thao tác nhạy cảm bằng `prompt=login` hoặc `max_age` theo policy.
10. Thêm integration test xác minh ID Token, UserInfo subject binding và end-session redirect.

## 14. Checklist hoàn thành lab

- [ ] Authorization Server khởi động tại port 9000.
- [ ] Discovery metadata có issuer đúng.
- [ ] OIDC được bật và UserInfo endpoint được công bố.
- [ ] Logout endpoint được công bố nếu phiên bản hỗ trợ.
- [ ] JWKS có public key tương ứng với key ký ID Token.
- [ ] Hai relying party được đăng ký với redirect URI riêng.
- [ ] Hai client dùng authorization code và PKCE.
- [ ] Portal A đăng nhập thành công và hiển thị ID Token claims.
- [ ] Portal B SSO trong cùng browser mà không hỏi lại mật khẩu.
- [ ] Audience của hai ID Token khớp từng client.
- [ ] UserInfo được gọi bằng access token và `sub` khớp ID Token.
- [ ] Claim profile/email được giới hạn theo scope.
- [ ] Local logout và RP-Initiated Logout được kiểm thử riêng.
- [ ] Post-logout redirect URI được kiểm tra theo danh sách đăng ký.
- [ ] Đã hiểu local session của từng RP không tự biến mất chỉ vì AS logout.
- [ ] Đã ghi nhận giới hạn của in-memory store và ephemeral signing key trong lab.

## 15. Câu hỏi tự đánh giá

1. Vì sao OIDC authorization request cần scope `openid`?
2. ID Token khác access token ở mục đích và audience như thế nào?
3. Vì sao `sub` nên là subject ID ổn định thay vì email?
4. Relying party cần xác minh những claim và thuộc tính nào trong ID Token?
5. Nonce bảo vệ OIDC flow khỏi loại lỗi nào?
6. PKCE bảo vệ authorization code như thế nào?
7. UserInfo endpoint nhận loại token nào?
8. Vì sao `sub` trong UserInfo phải khớp ID Token?
9. Khi nào nên đưa claim vào ID Token và khi nào nên trả qua UserInfo?
10. Vì sao claim cần được lọc theo scope/consent?
11. SSO hoạt động giữa Portal A và Portal B nhờ trạng thái nào ở browser?
12. Vì sao hai portal vẫn có local session riêng?
13. Local logout khác RP-Initiated Logout như thế nào?
14. `id_token_hint` và `post_logout_redirect_uri` có vai trò gì?
15. Vì sao logout tại Authorization Server không tự động xóa mọi local session của các relying party?
16. Vì sao signing key tạo mới ở mỗi lần restart chỉ phù hợp cho lab?

## Tài liệu tham khảo

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): authentication request, ID Token, UserInfo và validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): provider metadata và endpoint discovery.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): logout request, `id_token_hint` và post-logout redirect.
- [Spring Authorization Server — OpenID Connect 1.0](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html#oidc-user-info): cấu hình OIDC và UserInfo endpoint.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, authorization, consent và persistence service.
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): cấu hình relying party và đăng nhập OIDC.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client registration, authorized client và token access.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT và JWK Set.
