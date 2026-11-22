# OAuth2TokenGenerator và DelegatingOAuth2TokenGenerator

> **Chương:** Token và claims  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Phạm vi:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phiên bản minh họa:** Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.x (Servlet stack). Với Spring Security 7.x tích hợp Authorization Server, cần đối chiếu lại tên package và DSL theo phiên bản thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích hợp đồng `OAuth2TokenGenerator<T extends OAuth2Token>`, đầu vào `OAuth2TokenContext` và kết quả trả về của `generate(...)`.
2. Mô tả cách `DelegatingOAuth2TokenGenerator` thử các generator theo thứ tự và **chọn token khác null đầu tiên**.
3. Phân biệt `JwtGenerator`, `OAuth2AccessTokenGenerator` và `OAuth2RefreshTokenGenerator`.
4. Hiểu `RegisteredClient` và `TokenSettings` quyết định JWT self-contained hay reference/opaque access token ra sao.
5. Cấu hình `JwtEncoder`, `DelegatingOAuth2TokenGenerator` và hai kiểu `OAuth2TokenCustomizer` cho JWT và opaque token.
6. Phân biệt OAuth2 access token, OIDC ID token và refresh token để không làm lẫn claims, audience và principal.
7. Kiểm thử token generator từ unit test đến end-to-end, gồm chữ ký, issuer, audience, TTL, scope, introspection và refresh.
8. Nhận diện lỗi phổ biến khi thay thế generator mặc định, đặc biệt thiếu JWT, refresh generator hoặc cấu hình customizer sai.

**Điểm cốt lõi:** Token generator là **bước tạo hiện vật token từ ngữ cảnh đã được xử lý**. Nó không tự thay nhiệm vụ xác thực OAuth2 Client, phê duyệt grant, kiểm tra consent hoặc xác minh quyền truy cập dữ liệu của Resource Server.

## 2. Token generation nằm ở chỗ nào trong Authorization Server?

Ví dụ Client Credentials Grant:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=booking.read
~~~

Để phản hồi một access token, Spring Authorization Server cần:

1. Xác thực/nhận diện Client theo `RegisteredClientRepository` và phương thức được đăng ký.
2. Xác minh Client được phép dùng `client_credentials`, scope yêu cầu phù hợp và grant đáp ứng chính sách.
3. Grant `AuthenticationProvider` dựng `OAuth2TokenContext` chứa RegisteredClient, principal, token type, authorized scopes và dữ liệu liên quan.
4. `OAuth2TokenGenerator` tạo access token theo policy.
5. `OAuth2AuthorizationService` lưu trạng thái authorization/token và metadata phù hợp.
6. Token endpoint trả response OAuth2 với `access_token`, `token_type`, `expires_in`, v.v.

~~~mermaid
flowchart TD
    REQ["POST /oauth2/token"]
    CLIENT["Client authentication<br/>RegisteredClient"]
    GRANT["Grant AuthenticationProvider<br/>grant type + scope + policy"]
    CONTEXT["OAuth2TokenContext<br/>tokenType, client, principal, scopes"]
    DELEGATE["DelegatingOAuth2TokenGenerator"]
    JWT["JwtGenerator"]
    OPAQUE["OAuth2AccessTokenGenerator"]
    REFRESH["OAuth2RefreshTokenGenerator"]
    STORE[("OAuth2AuthorizationService")]
    RESP["OAuth2 token response"]
    ERROR["OAuth2 error<br/>không phát token"]

    REQ --> CLIENT --> GRANT
    GRANT -->|"Không hợp lệ"| ERROR
    GRANT -->|"Hợp lệ"| CONTEXT --> DELEGATE
    DELEGATE --> JWT
    JWT -->|"Không phù hợp: null"| OPAQUE
    OPAQUE -->|"Không phù hợp: null"| REFRESH
    JWT -->|"JWT / ID token"| STORE
    OPAQUE -->|"Reference access token"| STORE
    REFRESH -->|"Refresh token"| STORE
    STORE --> RESP
~~~

Sơ đồ tóm lược logic **một lần gọi `generate(context)`**. Provider có thể cần gọi generator nhiều lần với các token type khác nhau trong cùng grant; thực tế thời điểm lưu token/authorization phụ thuộc provider. **Delegating generator không trực tiếp ghi vào database.**

### 2.1. Phân chia trách nhiệm

| Thành phần | Làm gì? | Không làm gì? |
| --- | --- | --- |
| `OAuth2ClientAuthenticationFilter` | Xác thực OAuth2 Client | Không ký access token |
| Grant `AuthenticationProvider` | Kiểm tra grant, scopes, code, PKCE, refresh binding | Không phải JWK key store |
| `OAuth2TokenContext` | Mang ngữ cảnh phát token đã được chuẩn hóa | Không thay authorization DB |
| `OAuth2TokenGenerator` | Tạo `OAuth2Token` | Không tự quyết định client được dùng grant |
| `DelegatingOAuth2TokenGenerator` | Chọn generator phù hợp | Không tự fallback sau lỗi ký để nới chính sách |
| `JwtEncoder` và `JWKSource` | Tạo chữ ký JWT | Không kiểm tra object-level authorization |
| `OAuth2AuthorizationService` | Lưu trạng thái authorization/token | Không xác minh JWT tại Resource Server |
| Resource Server | Xác minh access token và quyền truy cập API | Không phải thành phần tạo token ở AS |

Không đưa logic “quyền đọc mọi booking” vào generator chỉ vì nó có thể thêm claim. Client/user có scope vẫn phải chịu kiểm tra ownership/tenant ở Resource Server.

## 3. Hợp đồng `OAuth2TokenGenerator`

API quan trọng về mặt ý tưởng:

~~~java
public interface OAuth2TokenGenerator<T extends OAuth2Token> {

    @Nullable
    T generate(OAuth2TokenContext context);
}
~~~

Đây là chữ ký rút gọn phục vụ diễn giải; package và annotation hãy lấy từ Javadoc của đúng phiên bản Spring Authorization Server.

- **Đầu vào:** `OAuth2TokenContext` mô tả token cần sinh và dữ liệu authorization.
- **Đầu ra:** một `OAuth2Token` hoặc subtype như `Jwt`, `OAuth2AccessToken`, `OAuth2RefreshToken`.
- **`null`:** generator không tạo token cho context hiện tại; `DelegatingOAuth2TokenGenerator` được phép thử generator tiếp theo.
- **Exception:** tạo token thất bại thật sự, ví dụ signer lỗi. Không đồng nhất exception với `null`; không bỏ qua lỗi bảo mật để phát loại token khác.

### 3.1. Token type và Java object không hoàn toàn trùng nhau

| Token type hoặc nhu cầu | Object có thể được tạo | Ghi chú |
| --- | --- | --- |
| `OAuth2TokenType.ACCESS_TOKEN`, self-contained | `Jwt` | JWT có chữ ký, thường được provider chuyển thành OAuth2 access token response |
| `OAuth2TokenType.ACCESS_TOKEN`, reference | `OAuth2AccessToken` | Chuỗi opaque, metadata lưu phía AS |
| `OAuth2TokenType.REFRESH_TOKEN` | `OAuth2RefreshToken` | Credential để xin access token mới |
| OIDC `id_token` | `Jwt` | OIDC ID token khác JWT access token về mục đích và audience |
| `code` | Authorization code do luồng authorization quản lý | Không coi authorization code là JWT access token |

Một `Jwt` implements `OAuth2Token` nhưng có claims khác với cách lưu `OAuth2AccessToken`. Provider và authorization storage giữ vai trò kết nối token được tạo với giao thức.

## 4. `OAuth2TokenContext` cung cấp thông tin gì?

Theo core model của Spring Authorization Server:

| Accessor | Ý nghĩa | Chú ý |
| --- | --- | --- |
| `getRegisteredClient()` | Đăng ký Client được AS nhận diện | Không phải `client_id` thô chưa được kiểm tra |
| `getPrincipal()` | `Authentication` của Resource Owner hoặc Client | Client Credentials không có người dùng login |
| `getAuthorizationServerContext()` | Thông tin runtime AS, gồm issuer | Issuer phải đúng HTTPS/public URL |
| `getAuthorization()` | Authorization hiện hữu, **có thể null** | Grant mới không nhất thiết có record trước |
| `getAuthorizedScopes()` | Những scope thực sự được cấp | Không tự nâng thành toàn bộ registered scopes |
| `getTokenType()` | Loại token đang được yêu cầu | Dùng để chọn và tùy biến claim |
| `getAuthorizationGrantType()` | Grant đang xử lý | Phân biệt user grant/client grant |
| `getAuthorizationGrant()` | `Authentication` của grant đã được xử lý | Không ghi credential ra log |

### 4.1. Registered scopes không phải authorized scopes

Giả sử Client đăng ký `openid`, `booking.read`, `booking.write` và `profile`, nhưng Resource Owner chỉ chấp thuận `openid` và `booking.read`.

`RegisteredClient.getScopes()` có thể chứa **bốn** scope; `context.getAuthorizedScopes()` trong grant tương ứng chỉ được phản ánh phạm vi **đã cấp**. Một customizer dùng mọi registered scope để tạo claim sẽ có nguy cơ vượt consent.

Không lấy tham số `scope` tùy ý từ HTTP token request rồi gắn nguyên văn vào JWT. Grant provider phải kiểm tra yêu cầu với client registration và authorization thực tế.

### 4.2. Principal có thể là user hoặc client

Ở Authorization Code, principal thường là Resource Owner đã xác thực. Ở Client Credentials, principal thường là OAuth2 Client. Vì vậy ví dụ dưới có thể lỗi:

~~~java
// Không đúng cho mọi grant:
UserDetails user =
    (UserDetails) context.getPrincipal().getPrincipal();
~~~

Nếu cần claim dành riêng user, hãy giới hạn theo grant type và xác thực principal type, hoặc dùng service đọc dữ liệu người dùng từ nguồn tin cậy. Đừng mặc định rằng `sub` của mọi access token đều là user ID.

### 4.3. Context có thể xuất hiện nhiều lần trong một grant

Ở Authorization Code + OIDC, provider có thể cần access token, refresh token (nếu grant/client được phép) và ID token. Mỗi lần sinh có một `getTokenType()` cụ thể. Customizer phải biết nó đang bổ sung claim cho **loại token nào**, không áp dữ liệu API indiscriminately vào ID token.

## 5. `DelegatingOAuth2TokenGenerator` chọn kết quả như thế nào?

`DelegatingOAuth2TokenGenerator` được khởi tạo bằng danh sách generators. Mỗi generator lần lượt nhận context; **token khác null đầu tiên được trả về**.

Pseudocode:

~~~java
// Mã giả để giải thích contract, không phải mã nguồn framework.
OAuth2Token generate(OAuth2TokenContext context) {
    for (OAuth2TokenGenerator<? extends OAuth2Token> generator
            : generators) {
        OAuth2Token token = generator.generate(context);
        if (token != null) {
            return token;
        }
    }
    return null;
}
~~~

Hệ quả:

1. **Thứ tự quan trọng**: generator phía trước có cơ hội quyết định kết quả trước.
2. **`null` là bình thường** khi generator không hỗ trợ token type/format hiện tại.
3. **Kết quả không null kết thúc vòng lặp**; generator sau không được gọi.
4. **Exception không phải tín hiệu thử tiếp**; lỗi ký JWT không nên bị nuốt và biến thành fallback opaque token trái chính sách.
5. Một provider cần nhiều token có thể gọi `generate(...)` nhiều lần với các token types khác nhau.

### 5.1. Ba generator thông dụng

| Generator | Vai trò chính | Trường hợp trả null |
| --- | --- | --- |
| `JwtGenerator` | Tạo JWT self-contained access token và JWT phục vụ OIDC ID token | Yêu cầu `REFERENCE` access token hoặc refresh token |
| `OAuth2AccessTokenGenerator` | Tạo reference/opaque access token | Token type khác access token, hoặc format không phải reference |
| `OAuth2RefreshTokenGenerator` | Tạo refresh token theo policy | Không phải refresh token, hoặc grant/client không được cấp RT |

Một custom generator có thể được thêm, nhưng phải hỗ trợ chính xác token type và format. Một generator luôn trả token dù context yêu cầu gì có thể chặn hoàn toàn những generator còn lại.

### 5.2. Bảng lựa chọn thường gặp

| `getTokenType()` | `TokenSettings.accessTokenFormat` | Generator được chọn | Kết quả |
| --- | --- | --- | --- |
| `ACCESS_TOKEN` | `SELF_CONTAINED` | `JwtGenerator` | JWT được ký |
| `ACCESS_TOKEN` | `REFERENCE` | `OAuth2AccessTokenGenerator` | Opaque/reference access token |
| `REFRESH_TOKEN` | Không phụ thuộc trực tiếp access format | `OAuth2RefreshTokenGenerator` | Refresh token, nếu được phép |
| OIDC `ID_TOKEN` | Không phụ thuộc access format | `JwtGenerator` | JWT ID token khi OIDC flow hợp lệ |
| Token type mở rộng | Theo policy và extension | Custom generator | Token riêng, cần contract đầy đủ |

**Access token JWT không có nghĩa refresh token cũng JWT.** OIDC ID token là JWT theo giao thức, không bị chuyển sang opaque khi access token chọn `REFERENCE`.

### 5.3. Luồng nhiều generator

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Grant Provider
    participant D as DelegatingOAuth2TokenGenerator
    participant J as JwtGenerator
    participant A as OAuth2AccessTokenGenerator
    participant R as OAuth2RefreshTokenGenerator

    P->>D: generate(context tokenType=ACCESS_TOKEN)
    D->>J: generate(context)
    alt SELF_CONTAINED
        J-->>D: JWT access token
    else REFERENCE
        J-->>D: null
        D->>A: generate(context)
        A-->>D: Opaque access token
    end
    D-->>P: Access token
    opt Grant/client cho phép refresh
        P->>D: generate(context tokenType=REFRESH_TOKEN)
        D->>J: generate(context)
        J-->>D: null
        D->>A: generate(context)
        A-->>D: null
        D->>R: generate(context)
        R-->>D: Refresh token
        D-->>P: Refresh token
    end
~~~

Với OIDC, provider có thể tiếp tục gọi `generate(context tokenType=ID_TOKEN)` để `JwtGenerator` tạo ID token. Delegating chỉ chọn generator, **không lưu token hoặc trả HTTP response trực tiếp**.

## 6. Generator mặc định được Spring Authorization Server cấu hình thế nào?

Theo tài liệu Spring Authorization Server 1.x:

- Nếu ứng dụng không khai báo `OAuth2TokenGenerator`, cấu hình mặc định có thể tạo `DelegatingOAuth2TokenGenerator` với `OAuth2AccessTokenGenerator` và `OAuth2RefreshTokenGenerator`.
- Nếu có `JwtEncoder` bean hoặc `JWKSource<SecurityContext>` bean phù hợp, `JwtGenerator` được bổ sung trong bộ delegating generator.
- `TokenSettings.accessTokenFormat` mặc định thường là `SELF_CONTAINED`.
- Khi client cần JWT nhưng không có signing infrastructure, không nên kỳ vọng AS tự động đổi sang opaque để thành công. Hãy cấu hình JWK/JwtEncoder đúng.

### 6.1. Vì sao cần `JwtEncoder`?

`JwtGenerator` dùng `JwtEncoder` để ký JWT. Một cấu hình phổ biến sử dụng `NimbusJwtEncoder` với `JWKSource<SecurityContext>`.

JWT thông thường **được ký chứ không được mã hóa**. Payload có thể bị người giữ token đọc; phải giữ claim tối thiểu và tránh mật khẩu, client secret, session cookie, refresh token và PII không cần thiết.

Production cần key lifecycle rõ: khóa được bảo vệ, JWKS công khai chính xác, `kid` và rotation hợp lệ, issuer ổn định, backup/failover có kiểm soát. Không tạo private signing key mới ở mọi lần restart nếu Resource Server cần tiếp tục xác minh token đã cấp.

### 6.2. JWT signing và Resource Server validation là hai phía

AS dùng khóa riêng ký token; RS dùng khóa công khai xác minh JWT, cộng các validator về `iss`, `aud`, `exp`, `nbf` nếu có, scope và policy nghiệp vụ.

Nếu RS chấp nhận JWT chỉ vì chữ ký được ký bởi cùng AS nhưng không kiểm tra audience, token cấp cho API A có thể bị dùng tại API B. Vì vậy `aud` là một ràng buộc cần thiết trong thiết kế.

## 7. `TokenSettings` quyết định access token format

Ví dụ hai client có nhu cầu khác nhau:

- `booking-bff`: access token JWT ngắn hạn để RS xác minh cục bộ.
- `admin-integration`: reference token và introspection vì cần kiểm tra trạng thái tập trung.

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat;

TokenSettings jwtSettings = TokenSettings.builder()
    .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
    .accessTokenTimeToLive(Duration.ofMinutes(5))
    .refreshTokenTimeToLive(Duration.ofDays(7))
    .reuseRefreshTokens(false)
    .build();

TokenSettings opaqueSettings = TokenSettings.builder()
    .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
    .accessTokenTimeToLive(Duration.ofMinutes(3))
    .build();
~~~

Khi tạo client:

~~~java
RegisteredClient bookingBff = RegisteredClient.withId("booking-bff-id")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecureConfig))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://app.example.test/login/oauth2/code/booking-bff")
    .scope("booking.read")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .build())
    .tokenSettings(jwtSettings)
    .build();
~~~

Đây là **mảnh cấu hình `RegisteredClient`**, chưa phải ứng dụng AS có thể chạy độc lập. `passwordEncoder` và `secretFromSecureConfig` cần được cung cấp bởi bean/secret manager; client phải được lưu bởi `RegisteredClientRepository`. Production cần khóa ký, authorization/consent store, issuer, token endpoint và user login.

Client khác có thể gọi `.tokenSettings(opaqueSettings)` để chọn `REFERENCE`. **Không cho HTTP client tùy tiện gửi một tham số “token_format=JWT” để override chính sách đăng ký**.

### 7.1. Hệ quả với Resource Server

| Access token | Cách RS xử lý | Lưu ý |
| --- | --- | --- |
| JWT self-contained | `oauth2ResourceServer().jwt()` | Verify signature, issuer, audience, expiry, scope |
| Opaque/reference | `oauth2ResourceServer().opaqueToken()` | Gọi introspection đáng tin, kiểm tra active/metadata/scope |

JWT thường ít phụ thuộc AS ở từng API request sau khi RS đã có khóa, nhưng việc AS revoke không được RS biết tức thì nếu RS chỉ verify local. Reference cho phép AS trả trạng thái token lúc introspection, đổi lại chi phí mạng, availability và cache policy.

## 8. Định nghĩa `DelegatingOAuth2TokenGenerator` thủ công

Nếu cần toàn quyền điều phối, có thể khai báo bean generator. Ví dụ sau **giữ đủ ba generator mặc định** và gắn customizer cho JWT và reference access token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.server.authorization.token.DelegatingOAuth2TokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.JwtGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2AccessTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2RefreshTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenClaimsContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenGenerator;

@Configuration
public class TokenGenerationConfig {

    @Bean
    OAuth2TokenGenerator<?> tokenGenerator(
            JwtEncoder jwtEncoder,
            OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer,
            OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueCustomizer) {

        JwtGenerator jwtGenerator = new JwtGenerator(jwtEncoder);
        jwtGenerator.setJwtCustomizer(jwtCustomizer);

        OAuth2AccessTokenGenerator accessTokenGenerator =
            new OAuth2AccessTokenGenerator();
        accessTokenGenerator.setAccessTokenCustomizer(opaqueCustomizer);

        OAuth2RefreshTokenGenerator refreshTokenGenerator =
            new OAuth2RefreshTokenGenerator();

        return new DelegatingOAuth2TokenGenerator(
            jwtGenerator, accessTokenGenerator, refreshTokenGenerator);
    }
}
~~~

**Giả định:** Có một `JwtEncoder` bean, một `JwtEncodingContext` customizer bean và một `OAuth2TokenClaimsContext` customizer bean theo mục 9/10. Việc dùng generic types rõ ràng giúp Spring chọn đúng bean. Ví dụ sẽ fail injection nếu những bean này chưa được khai báo, điều này là bình thường đối với fragment dùng để học.

### 8.1. Đăng ký generator qua configurer

Có thể cấu hình tường minh:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurity(
        HttpSecurity http,
        OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, as -> as.tokenGenerator(tokenGenerator))
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated());

    return http.build();
}
~~~

Với nhánh Spring Authorization Server 1.x, framework cũng có thể lấy `OAuth2TokenGenerator` bean từ application context. Nếu bạn **tự khai báo bean generator**, nên gắn customizer **tường minh** như mục 8 để không dựa vào đường tự động khởi tạo mặc định.

Filter chain ví dụ chưa bao gồm toàn bộ form login, login entry point, JWK/issuer/metadata và OIDC endpoint; phải bổ sung các bean/chính sách phù hợp khi triển khai AS hoàn chỉnh.

### 8.2. JwtEncoder dựa trên JWKSource

Nếu dự án có JWKSource đáng tin:

~~~java
@Bean
JwtEncoder jwtEncoder(JWKSource<SecurityContext> jwkSource) {
    return new NimbusJwtEncoder(jwkSource);
}
~~~

Imports:

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
~~~

Không hardcode private key production vào source và không tạo khóa tạm mỗi lần boot. Có thể dùng secure key store/KMS/HSM theo hạ tầng.

## 9. `JwtEncodingContext`: tùy biến JWT access token

`JwtGenerator.setJwtCustomizer(...)` nhận `OAuth2TokenCustomizer<JwtEncodingContext>`. Context cung cấp builder cho `JwsHeader` và `JwtClaimsSet`.

### 9.1. Ví dụ gắn audience cho client được biết trước

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        String clientId = context.getRegisteredClient().getClientId();

        // Mapping được AS kiểm soát, không lấy audience tùy ý từ HTTP.
        if ("booking-bff".equals(clientId)) {
            context.getClaims()
                .audience(List.of("booking-api"))
                .claim("api_tier", "standard");
        }
    };
}
~~~

Đoạn này **chỉ minh họa một client đã được biết trước**. Production cần mapping client/grant/resource → audience đầy đủ và được quản trị; những client khác cũng phải được xác định audience đúng để RS kiểm tra.

### 9.2. Không gắn scope hoặc quyền vượt authorization

Giả sử client được đăng ký `booking.read` và `booking.write` nhưng user chỉ chấp thuận `booking.read`. Không gắn `permissions=["booking.write"]` vào JWT chỉ vì scope đó nằm trong registration.

Dùng `context.getAuthorizedScopes()` và dịch vụ quyền đáng tin cậy để chọn claim. Với claim `tenant_id`, cần kiểm tra user/client thực sự thuộc tenant đó. Không tin giá trị `tenant_id` gửi trực tiếp trong query token endpoint.

### 9.3. Không áp claim dành cho user vào Client Credentials

~~~text
Client Credentials:
  principal = OAuth2 Client
  không có Resource Owner tương tác trong request

Authorization Code:
  principal = Resource Owner theo flow
  có login/consent và authorization state
~~~

Không viết customizer luôn ép `context.getPrincipal().getPrincipal()` thành `UserDetails`. Khi token đại diện dịch vụ, `sub` có thể đại diện client; authorization policy ở RS phải biết điều đó.

### 9.4. Không tùy tiện sửa JWS header

Mặc dù `context.getJwsHeader()` cho phép sửa header, cần tránh:

- Chuyển `alg` sang `none` hoặc thuật toán yếu.
- Chèn `jku`/`x5u` từ URL do client gửi chưa được xác minh.
- Gắn `kid` không tương ứng khóa ký thực.
- Làm nhầm `typ` của access token và ID token.

Các quyết định key/algorithm phải theo chính sách AS, `JwtEncoder` và cơ chế key rotation, không phải phụ thuộc vào request không tin cậy.

## 10. `OAuth2TokenClaimsContext`: tùy biến opaque access token

`OAuth2AccessTokenGenerator` tạo opaque/reference access token khi `TokenSettings.accessTokenFormat` là `REFERENCE`. Metadata/claims có thể được tùy biến bằng `OAuth2TokenCustomizer<OAuth2TokenClaimsContext>`:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenClaimsContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<OAuth2TokenClaimsContext> opaqueCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }
        if ("admin-integration".equals(
                context.getRegisteredClient().getClientId())) {
            context.getClaims()
                .claim("aud", List.of("admin-api"))
                .claim("token_class", "internal");
        }
    };
}
~~~

**Điểm khác so với JWT:**

- Chuỗi opaque không mang payload mà Client có thể tự giải mã để suy ra claims.
- AS lưu token/metadata và quyết định trạng thái qua `OAuth2AuthorizationService`.
- Resource Server thường gọi Token Introspection (RFC 7662) để nhận `active` và metadata cho phép.
- Không giả định mọi custom claim tự xuất hiện ở introspection response của mọi phiên bản/triển khai; cần test API thực.
- Không vì token opaque mà lưu thông tin mật khẩu, private key hoặc dữ liệu riêng tư không cần thiết vào metadata.

### 10.1. Hai customizer bean không thay thế nhau

| Token muốn tùy biến | Context | Nơi gắn |
| --- | --- | --- |
| JWT access token | `JwtEncodingContext` | `JwtGenerator.setJwtCustomizer(...)` |
| OIDC ID token (JWT) | `JwtEncodingContext` nhưng token type `id_token` | `JwtGenerator.setJwtCustomizer(...)` |
| Reference access token | `OAuth2TokenClaimsContext` | `OAuth2AccessTokenGenerator.setAccessTokenCustomizer(...)` |

Nếu chỉ có `JwtEncodingContext` customizer, client dùng `REFERENCE` sẽ **không** nhận claims từ customizer đó.

Theo tài liệu SAS 1.x, nếu ứng dụng **không** tự cấu hình token generator, framework có thể tự nhận một customizer bean đúng kiểu và gắn vào generator mặc định. Khi tự tạo delegating bean, nên wire tường minh. Không tạo nhiều bean cùng generic customizer type nếu chưa chủ động cấu hình composite/qualifier.

## 11. OIDC ID token và JWT access token khác nhau

JWT access token dành cho Resource Server. ID token dành cho OpenID Connect Client/Relying Party để xác minh kết quả đăng nhập. Cả hai có thể được `JwtGenerator` hỗ trợ nhưng **không cùng audience hoặc semantics**.

### 11.1. Phân nhánh trong JWT customizer

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            customizeAccessToken(context);
        } else if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            customizeIdToken(context);
        }
    };
}
~~~

`customizeAccessToken(...)` và `customizeIdToken(...)` là hàm policy do ứng dụng tự định nghĩa, chưa được cung cấp trong fragment trên. Import `OidcParameterNames` từ `org.springframework.security.oauth2.core.oidc.OidcParameterNames`.

### 11.2. Những claim cần cẩn trọng

| Claim | Vì sao nhạy cảm? |
| --- | --- |
| `iss` | RS/Client phải xác minh issuer |
| `sub` | Định danh chủ thể theo protocol |
| `aud` | Access token dành cho API, ID token dành cho OIDC Client |
| `iat`, `exp`, `nbf` | Thời hạn và tính hợp lệ |
| `nonce` | Ràng buộc OIDC request/ID token khi áp dụng |
| `auth_time` | Thời điểm xác thực, có ý nghĩa với chính sách OIDC |
| `scope` | Quyền access token, không phải mọi user role |

Không tự xóa/ghi đè claim chuẩn chỉ để đáp ứng UI/API tạm thời. ID token có chữ ký đúng vẫn có thể sai giao thức nếu audience/nonce bị sửa. Resource Server không được chấp nhận ID token thay access token.

## 12. Refresh token và giới hạn của generator

`OAuth2RefreshTokenGenerator` tạo refresh token khi grant/provider/chính sách cho phép. Nó không tự quyết định:

- Có cấp refresh token cho Client Credentials hay không (RFC 6749 khuyến nghị không).
- Client đang gọi có được dùng `REFRESH_TOKEN` grant hay không.
- Refresh token cũ có active, thuộc đúng client, còn hạn hay không.
- Khi rotation, cần revoke/family detection hoặc xử lý concurrent request thế nào.

Các điều kiện đó thuộc grant provider và authorization/token lifecycle. `TokenSettings.refreshTokenTimeToLive(...)` và `reuseRefreshTokens(...)` mô tả chính sách token, nhưng **rotation không tự động là đầy đủ cơ chế replay detection/family revocation**.

### 12.1. Tại sao không bỏ `OAuth2RefreshTokenGenerator` khi chỉ muốn JWT?

Giả sử AS phát JWT access token cho BFF dùng Authorization Code + PKCE và cho phép Refresh Token Grant. Nếu bean tự tạo chỉ có `JwtGenerator`, có thể không sinh được refresh token như flow yêu cầu.

Giải pháp là giữ `DelegatingOAuth2TokenGenerator(jwtGenerator, accessTokenGenerator, refreshTokenGenerator)` và test Authorization Code, refresh grant, token expiration/rotation.

## 13. Claims và `OAuth2AuthorizationService`

Một `OAuth2Authorization` có thể lưu code, access token, refresh token, ID token và các metadata tùy flow. Nếu token được tạo có claims và hỗ trợ `ClaimAccessor`, claims có thể được đọc thông qua `OAuth2Authorization.Token.getClaims()` theo core model.

~~~mermaid
flowchart LR
    P["Grant Provider"]
    G["OAuth2TokenGenerator"]
    T["OAuth2Token<br/>ClaimAccessor nếu có"]
    B["OAuth2Authorization.Builder"]
    DB[("OAuth2AuthorizationService")]
    RS["Resource Server"]

    P --> G --> T --> B --> DB
    T -.->|"JWT gửi qua Client"| RS
    DB -.->|"Introspection metadata cho opaque"| RS
~~~

Không đồng nhất:

- JWT payload có thể được bên giữ token đọc.
- Opaque token chỉ là chuỗi, muốn biết trạng thái thường phải introspect.
- Authorization store chứa metadata không nhất thiết công bố tất cả cho Resource Server.
- Khả năng phát token không đồng nghĩa user/client có quyền đọc mọi tài nguyên.

### 13.1. Dữ liệu nào nên nằm trong access token?

| Claim | Ví dụ | Kiểm soát cần thiết |
| --- | --- | --- |
| `iss` | `https://auth.example.test` | Issuer hợp lệ |
| `sub` | User ID hoặc Client ID | Phụ thuộc grant, không ép user |
| `aud` | `["booking-api"]` | RS validate audience |
| `client_id` | `booking-bff` | ID công khai, không thay client authentication |
| `scope` | `booking.read` | Không vượt authorized scopes |
| `iat`, `exp`, `nbf` | Mốc thời gian | TTL và clock skew |
| `jti` | Token ID | Có thể dùng audit/revocation nhưng đừng log raw token |
| `tenant_id` | ID tenant | Chỉ gắn khi xác minh membership |
| `permissions` | Danh sách quyền | Có thể stale, không thay object-level authorization |

Không đưa password hash, raw password, client secret, refresh token hoặc dữ liệu cá nhân không cần thiết vào claims.

## 14. Khi nào nên viết custom generator?

Có những nhu cầu cần phát token theo định dạng đặc thù, nhưng đa số trường hợp **chỉ cần token customizer** thay vì viết generator mới.

Chỉ cân nhắc custom generator khi:

- Có định dạng token riêng được các thành phần nhận token và RS thực sự hỗ trợ.
- Cần cơ chế ký hoặc encode đặc thù được chính sách an toàn cho phép.
- Có yêu cầu lifecycle và persistence đã được thiết kế.
- Có test rõ ràng về issuer, audience, TTL, claim, token type, scope, revocation và error response.

Một custom generator mới phải:

1. Kiểm tra `context.getTokenType()` và format phù hợp.
2. Kiểm tra RegisteredClient/token policy từ context đã qua grant validation.
3. **Trả `null`** nếu nó không có trách nhiệm xử lý token hiện tại.
4. Không cấp token khi chưa đủ context hoặc khi không thể ký/mã hóa an toàn.
5. Phối hợp với provider để lưu token/metadata và phản hồi đúng protocol.
6. Không “nuốt lỗi” rồi cấp access token có quyền rộng hơn.
7. Có unit test và integration test chứng minh không phá các grant mặc định.

### 14.1. Ví dụ anti-pattern

~~~java
// KHÔNG NÊN: chỉ tạo JwtGenerator rồi thay cả bean mặc định.
@Bean
OAuth2TokenGenerator<?> tokenGenerator(JwtEncoder encoder) {
    return new JwtGenerator(encoder);
}
~~~

Bean này có thể khiến reference clients và refresh flow không tạo được token cần thiết. Hãy dùng Delegating generator với đủ thành phần.

### 14.2. Anti-pattern: generator luôn trả token

Nếu custom generator luôn trả một chuỗi token bất kể `tokenType`, nó có thể chặn `JwtGenerator`, `OAuth2AccessTokenGenerator` và `OAuth2RefreshTokenGenerator` phía sau. Điều này làm sai định dạng, thời hạn và quyền.

### 14.3. Anti-pattern: fallback sau lỗi ký JWT

Một hệ thống không nên bắt mọi exception của `JwtEncoder` rồi chuyển sang opaque token “cho API đỡ lỗi” nếu client đã được đăng ký nhận JWT. Lỗi ký là lỗi phát hành/token infrastructure, phải báo lỗi phù hợp và sửa nguyên nhân, không ngầm đổi contract bảo mật.

## 15. Ví dụ kiến trúc Booking API

Giả sử `batch-reporter` là confidential client dùng Client Credentials, nhận JWT cho `booking-api`.

### 15.1. Client gửi request

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=booking.read
~~~

RegisteredClient của `batch-reporter` **phải được đăng ký `AuthorizationGrantType.CLIENT_CREDENTIALS`** và `booking.read`. Không dùng nguyên registration `booking-bff` chỉ có Authorization Code/Refresh Token ở mục 7 rồi chờ request máy này thành công.

### 15.2. Response và JWT minh họa

~~~json
{
  "access_token": "eyJ...signed.jwt...placeholder",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "booking.read"
}
~~~

Một JWT payload có thể mang:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": ["booking-api"],
  "sub": "batch-reporter",
  "client_id": "batch-reporter",
  "scope": "booking.read",
  "iat": 1893455700,
  "exp": 1893456000
}
~~~

Đây là **giá trị minh họa**, không phải JWT thật. `sub` thể hiện client/service trong Client Credentials. Scope có thể được biểu diễn theo profile khác nhau; RS phải dùng mapping và validation thống nhất.

### 15.3. Resource Server xác minh

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Policy API ví dụ:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/bookings/**")
                .hasAuthority("SCOPE_booking.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Cần dependency Resource Server, `JwtDecoder` và kiểm tra audience. **`issuer-uri` không thay thế việc cấu hình audience validator cho API**. Hệ thống vẫn phải kiểm tra object-level authorization và tenant. Nhiều ứng dụng có thể có một issuer nhưng mỗi RS chỉ được nhận token dành cho chính nó.

## 16. Kiểm thử token generator và claims

### 16.1. Ma trận kiểm thử

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| `SELF_CONTAINED` access token | JWT có chữ ký, issuer/audience/TTL/scope đúng |
| `REFERENCE` access token | Opaque token, authorization metadata và introspection hợp lệ |
| Grant cần refresh token | Generator có RT, cấp theo policy |
| Client Credentials | Không tự giả định có refresh token |
| OIDC ID token | Đúng audience OIDC Client, không chứa nhầm API claim |
| JWT customizer | Chạy cho access token type đúng |
| Opaque customizer | Chạy cho reference access token |
| JWT sai signature | RS từ chối |
| JWT sai audience | RS từ chối |
| JWT hết hạn | RS từ chối |
| Opaque `active: false` | RS từ chối |
| Key rotation | Token ký bởi key cũ/mới hợp lệ trong giai đoạn chuyển đổi |
| Signing key outage | AS báo lỗi, không tự fallback trái policy |
| Custom generator trả null | Delegating thử generator kế tiếp |
| Custom generator trả token | Generator phía sau không được gọi |
| Customizer principal sai kiểu | Được xử lý an toàn, không ClassCastException |
| Refresh rotation | Trạng thái RT cũ/mới đúng |
| Multi-instance | Authorization/key store nhất quán |

### 16.2. Unit test cơ chế delegating

Mã lõi sau kiểm tra rằng một generator trả `null` sẽ nhường cơ hội cho generator sau:

~~~java
OAuth2TokenGenerator<OAuth2Token> noMatch = context -> null;

OAuth2AccessToken expected = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "test-token-only",
    Instant.now(),
    Instant.now().plusSeconds(60),
    Set.of("booking.read")
);

OAuth2TokenGenerator<OAuth2Token> match = context -> expected;

DelegatingOAuth2TokenGenerator delegating =
    new DelegatingOAuth2TokenGenerator(noMatch, match);

// Với OAuth2TokenContext fixture hợp lệ:
// assertThat(delegating.generate(context)).isSameAs(expected);
~~~

Đây là unit test **ý tưởng**, chưa có builder/fixture `context`. Nó không kiểm tra JWT signature hay grant authorization. Test thêm trường hợp generator đầu trả token thì generator hai không chạy, và generator đầu ném exception thì không bị xem như `null`.

### 16.3. MockMvc: Client Credentials end-to-end

~~~java
@Test
void clientCredentialsIssuesAccessToken() throws Exception {
    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("batch-reporter", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("scope", "booking.read"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").isNotEmpty())
        .andExpect(jsonPath("$.token_type").value("Bearer"));
}
~~~

Test fixture phải có `RegisteredClient` cho `batch-reporter`, Client Credentials, scope, hashed secret, token generator/keys/issuer và authorization store. Đoạn này **chỉ chứng minh nhận được token response**. Để xác minh JWT thật, phải lấy token, decode/verify với `JwtDecoder` thực, kiểm tra `iss`, `aud`, `exp`, `scope` và chữ ký.

### 16.4. Test metadata và introspection

Với client dùng `REFERENCE`, cần test:

1. Access token có dạng opaque theo contract (không chỉ kiểm tra dấu chấm).
2. `OAuth2AuthorizationService` lưu token và metadata phù hợp.
3. Introspection bằng client credentials hợp lệ trả `active: true` và các metadata được cho phép.
4. Token sai/hết hạn/revoked trả `active: false`.
5. RS từ chối token khi introspection timeout/outage, không tự cho qua.
6. Scope, audience và quyền nghiệp vụ được kiểm tra tại RS.
7. Không dựa vào một customizer JWT để làm thay metadata opaque.

### 16.5. Kiểm thử riêng OIDC

Với OIDC, cần test rằng ID token được ký và có `iss`/`aud`/`sub`/`exp` và các claim khác đúng profile; nonce khi áp dụng được Client kiểm tra. API **không chấp nhận ID token** như access token.

`@WithMockUser` và `jwt()` từ `spring-security-test` có ích cho test authorization rules, nhưng **không chứng minh token generator đã tạo token và ký đúng**.

## 17. Vận hành, bảo mật và quan sát

### 17.1. Quản lý khóa ký

- Khóa riêng phải được bảo vệ theo policy (secret manager/KMS/HSM hoặc kho khóa phù hợp).
- JWKS công khai phải phản ánh khóa đúng, `kid` và thuật toán hợp lệ.
- Khi rotation, giữ khóa công khai cũ đủ thời gian xác minh token đã cấp, trừ khi cần emergency revoke.
- Nhiều AS instances phải dùng key set nhất quán.
- Đừng sinh khóa ký mới mỗi restart nếu token cũ còn cần dùng.
- Xử lý sự cố signer lỗi như sự cố vận hành, không fallback mù quáng sang định dạng khác.

### 17.2. Dữ liệu và privacy

- Giảm tối đa claims chứa PII.
- Không chèn password, session ID, client secret hoặc refresh token vào access token.
- Không đọc user/tenant claim từ tham số chưa được xác minh.
- Role/permission có thể stale trong JWT; áp dụng TTL, revocation hoặc policy RS bổ sung.
- Không log raw access token, ID token, refresh token hoặc private keys.
- Không đưa token vào analytics URL, stack traces hoặc metrics label.

### 17.3. Monitoring hữu ích

| Chỉ số | Ý nghĩa |
| --- | --- |
| Token issuance theo grant/token type | Tải hệ thống và hành vi thay đổi |
| JWT signing failures/latency | Vấn đề signer/keys |
| JWT vs opaque distribution | Migration client/token format |
| Token generator exception count | Lỗi cấu hình hoặc runtime |
| Introspection failures/latency | Khả năng vận hành reference token |
| RS rejects by issuer/audience/expiry | Không đồng bộ AS-RS |
| Key rotation/JWKS cache misses | Cần kiểm tra phân phối khóa |
| Refresh failures/rotation races | Policy/token store concurrency |

Log phải có correlation ID, client ID đã xác thực, token type, error code và thời gian xử lý; **không chứa raw bearer credential**.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| JWT không được phát | Thiếu JwtEncoder/JWKSource, signer lỗi | Key configuration, issuer, bean wiring |
| JWT thiếu custom claim | Customizer không gắn, sai token type | `setJwtCustomizer`, JWT vs opaque |
| Opaque thiếu metadata | Chỉ có JwtEncodingContext customizer | `OAuth2TokenClaimsContext` |
| Client muốn opaque nhưng nhận JWT | TokenSettings sai hoặc custom generator rộng | RegisteredClient format |
| Client muốn JWT nhưng nhận opaque | Custom fallback vi phạm policy | Delegating order và signer |
| Refresh token không được cấp | Thiếu RefreshTokenGenerator hoặc grant/client không cho | Delegating list, grant policy |
| OIDC ID token thiếu | Chưa bật OIDC, thiếu encoder hoặc token provider | OIDC config, JWK, claim policy |
| ClassCastException khi cấp Client Credentials | Ép principal thành UserDetails | Kiểm tra grant/principal type |
| RS trả 401 dù JWT ký đúng | Issuer/audience/TTL/algorithm không khớp | JwtDecoder và validators |
| RS trả 403 | Scope hoặc quyền trên object không đủ | Token claims + API authorization |
| JWT cũ vẫn được dùng sau revoke | RS chỉ verify local | TTL/denylist/check online |
| Claim đổi role chưa cập nhật | JWT đã cấp chứa dữ liệu cũ | TTL/revoke/session policy |
| Token hỏng sau restart AS | Key store khác hoặc authorization store mất | Persistence, multi-instance |
| Introspection không có custom claim | Metadata chưa lưu hoặc response mapping | Authorization store/contract |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** `DelegatingOAuth2TokenGenerator` dừng ở điều kiện nào?

**Đáp án:** Khi generator đầu tiên theo thứ tự trả token không null. Generator sau không được gọi.

**Câu 2.** Vì sao không đồng nhất `null` và exception từ `generate(...)`?

**Đáp án:** `null` nghĩa là generator không đảm nhiệm loại token đó. Exception thể hiện lỗi phát hành thực sự; không nên ngầm thử format khác để bỏ qua lỗi bảo mật.

**Câu 3.** `JwtGenerator` tạo access token cho Client có `REFERENCE` format không?

**Đáp án:** Trong bộ generator mặc định, JWT generator không đảm nhiệm reference access token; `OAuth2AccessTokenGenerator` tạo opaque token.

**Câu 4.** Tại sao một customizer dùng `JwtEncodingContext` không ảnh hưởng reference token?

**Đáp án:** Reference/opaque token được tạo bởi `OAuth2AccessTokenGenerator` và dùng `OAuth2TokenClaimsContext` khi cần claims metadata.

**Câu 5.** `context.getPrincipal()` có luôn là Resource Owner không?

**Đáp án:** Không. Ở Client Credentials, principal thường là OAuth2 Client. Phải tránh ép kiểu user trong mọi grant.

**Câu 6.** Có nên dùng `RegisteredClient.getScopes()` để tạo claim quyền khi user chỉ consent một phần không?

**Đáp án:** Không. Sử dụng authorized scopes và policy đã được xác minh cho authorization tương ứng.

**Câu 7.** Vì sao không nên chỉ đăng ký bean `JwtGenerator` thay cả delegating bean?

**Đáp án:** Vì có thể làm mất khả năng tạo reference access token và refresh token cần cho những client/grant khác.

**Câu 8.** ID token và access token JWT có được dùng thay nhau không?

**Đáp án:** Không. ID token dành cho OIDC Client, access token dành cho Resource Server. Audience và mục đích khác nhau.

**Câu 9.** JWT có chữ ký đúng đã đủ để cho phép đọc mọi booking chưa?

**Đáp án:** Chưa. RS còn phải kiểm tra issuer, audience, expiry, scope và quyền trên từng object/tenant.

## 20. Checklist

- [ ] Client/grant được xác thực trước khi generator tạo token.
- [ ] `OAuth2TokenContext` dùng nguồn dữ liệu đã được server kiểm tra.
- [ ] Delegating generator có Jwt, opaque access token và refresh generator theo nhu cầu.
- [ ] Custom generator trả `null` cho token type ngoài phạm vi.
- [ ] Không swallow signing exception để đổi format trái policy.
- [ ] `TokenSettings.accessTokenFormat` và TTL được khai báo rõ theo RegisteredClient.
- [ ] JwtEncoder/JWKSource/issuer/rotation được quản lý an toàn.
- [ ] JWT có audience đúng và RS validate issuer/audience/signature.
- [ ] Opaque token có introspection và authorization store bền vững.
- [ ] JwtEncodingContext customizer chỉ chèn claim access token vào access token.
- [ ] OAuth2TokenClaimsContext customizer được gắn đúng OAuth2AccessTokenGenerator.
- [ ] Không mở rộng scope hoặc role/tenant từ request chưa xác minh.
- [ ] Refresh token được cấp theo grant/client và policy, không lẫn access token.
- [ ] OIDC ID token đáp ứng đúng audience và claim profile.
- [ ] Có test Jwt, opaque, refresh, ID token, TTL, signature, audience, scope và restart.
- [ ] Không log raw token, khóa ký hoặc client secret.

## 21. Tài liệu chính thức và kết luận

Nên đọc theo **đúng phiên bản** Spring đang triển khai:

- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Customize JWT access token claims](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html)

**Tổng kết:** `OAuth2TokenGenerator` tạo token theo `OAuth2TokenContext`. `DelegatingOAuth2TokenGenerator` điều phối các generator và lấy **kết quả không null đầu tiên**. `JwtGenerator` phục vụ JWT access token và ID token theo context; `OAuth2AccessTokenGenerator` phục vụ opaque/reference access token; `OAuth2RefreshTokenGenerator` phục vụ refresh token khi policy cho phép. Khi cấu hình và tùy biến claims, phải giữ đúng token type, client, scopes, audience, key lifecycle và vai trò Resource Server; kiểm thử end-to-end mới chứng minh hệ thống OAuth 2.0/OIDC phát hành token an toàn.

