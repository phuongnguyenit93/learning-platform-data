# Xây authorization server phát hành access token

> **Chương:** Dự án thực hành  
> **Phạm vi:** Xây một Authorization Server OAuth 2.0/OIDC để xác thực người dùng/client, cấp access token có audience và scope giới hạn, quản lý refresh token, công bố khóa xác minh và tích hợp với Resource Server.

## Mục tiêu dự án

Trong dự án này, bạn sẽ xây dựng một Authorization Server phục vụ Orders API. Sau khi hoàn thành, hệ thống có thể:

1. Đăng ký và quản lý OAuth client với redirect URI, grant type, scope và phương thức xác thực rõ ràng.
2. Cấp access token qua Authorization Code Flow với PKCE cho public client.
3. Cấp access token qua Client Credentials Flow cho service-to-service.
4. Ký JWT access token bằng khóa riêng, công bố public key qua JWKS và để Resource Server xác minh token.
5. Giới hạn token theo issuer, audience, thời hạn và scope; không đưa password hoặc secret vào payload.
6. Quản lý authorization, consent và refresh token bằng persistence phù hợp; cấu hình rotation/reuse detection.
7. Kiểm thử các trường hợp hợp lệ, sai issuer/audience, thiếu scope, token hết hạn, refresh token reuse và client không được phép.

Dự án dùng Java, Spring Boot và Spring Authorization Server làm ví dụ. Các đoạn code thể hiện cấu trúc cốt lõi; hãy chọn phiên bản Spring Boot/Spring Authorization Server tương thích theo dependency management của dự án. Tên API cấu hình có thể thay đổi giữa các phiên bản, vì vậy đối chiếu tài liệu đúng phiên bản trước khi ghép vào ứng dụng.

## 1. Kiến trúc và ranh giới trách nhiệm

Authorization Server (AS) chịu trách nhiệm xác thực chủ thể/client, áp dụng chính sách cấp quyền và phát hành token. Resource Server (RS) nhận access token, xác minh token và quyết định có cho phép request truy cập tài nguyên hay không.

~~~mermaid
flowchart LR
    U["User / Browser"] --> C["Orders Web Client"]
    C -->|"Authorization Code + PKCE"| AS["Authorization Server"]
    AS --> ID["User Authentication"]
    AS --> RC["Registered Clients / Consent"]
    AS --> K["Signing Key / JWKS"]
    AS -->|"Access token"| C
    C -->|"Bearer access token"| API["Orders Resource Server"]
    API -->|"issuer, signature, aud, exp, scope"| V["Token validation"]
    V -->|Valid| P["Authorization policy"]
    P --> DB[("Orders database")]
    V -->|Invalid| X["401 Unauthorized"]
    P -->|Forbidden| F["403 Forbidden"]
    S["Worker service"] -->|"Client Credentials"| AS
    AS -->|"Service access token"| S
    S -->|"aud=orders-api / allowed scope"| API
~~~

| Thành phần | Trách nhiệm |
| --- | --- |
| Authorization Server | Xác thực người dùng/client, cấp authorization code/token, kiểm tra refresh, consent và policy |
| Registered Client | Khai báo client ID, grant type, redirect URI, authentication method và scope được phép |
| Signing key/JWKS | Ký token và cung cấp public key để Resource Server xác minh |
| Resource Server | Kiểm tra chữ ký, issuer, audience, thời hạn và scope; bảo vệ API |
| User store | Lưu password verifier và trạng thái tài khoản; không lưu password dạng plaintext |
| Authorization store | Lưu authorization, token state, consent và dữ liệu phục vụ revoke/refresh |
| Secret Manager/KMS | Bảo vệ client secret, private signing key hoặc tham chiếu tới key được quản lý |
| Audit/observability | Ghi sự kiện bảo mật đã lọc, không ghi bearer token hoặc secret |

**Không nhầm vai trò:** Authorization Server phát hành token; Resource Server xác minh và thực thi quyền. Client không tự ký token cho mình. API không cần biết password người dùng hoặc client secret để xác minh access token.

### Các flow trong phạm vi dự án

| Flow | Đối tượng | Mục đích |
| --- | --- | --- |
| Authorization Code + PKCE | SPA/mobile/native app hoặc public client | Người dùng đăng nhập, client đổi code lấy token |
| Authorization Code (confidential client) | Web backend có khả năng giữ credential | Người dùng đăng nhập qua backend client đã xác thực |
| Client Credentials | Service/workload | Service lấy token theo quyền của chính service |
| Refresh Token | Client đã được cấp refresh token | Xin access token mới theo session/policy |

Không xây mới Resource Owner Password Credentials grant cho ứng dụng hiện đại. Client không thu thập password rồi gửi password qua các service để đổi token. Password được xử lý ở bước xác thực người dùng tại Authorization Server/IdP.

## 2. Xác định yêu cầu và hợp đồng token

Trước khi viết code, chốt hợp đồng token giữa Authorization Server và Orders API.

### Issuer, audience và scope

| Thuộc tính | Giá trị ví dụ | Quy tắc |
| --- | --- | --- |
| Issuer (`iss`) | `https://id.example.test` | Resource Server cấu hình chính xác issuer tin cậy |
| Audience (`aud`) | `orders-api` | Token chỉ dành cho API được chỉ định |
| Scope đọc | `orders.read` | Chỉ đọc đơn hàng |
| Scope ghi | `orders.write` | Tạo/cập nhật đơn theo policy |
| Subject (`sub`) | Pairwise/user identifier | Chỉ phát hành khi API cần nhận diện chủ thể |
| Expiry (`exp`) | 10 phút | Ví dụ ban đầu; hiệu chỉnh theo threat model |
| Tenant claim | `tenant_id` nếu cần | Chỉ cấp từ membership đã xác minh |
| Algorithm | RS256 trong lab | Cấu hình allow-list; không tin thuật toán do token tự chọn |

Ví dụ payload access token tối thiểu:

~~~json
{
  "iss": "https://id.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "iat": 1900000000,
  "exp": 1900000600,
  "scope": "orders.read"
}
~~~

Payload minh họa không chứa password, client secret, API key, private key, refresh token hay database credential. JWT JWS được ký nhưng payload không được mã hóa; không đặt dữ liệu bí mật vào custom claim.

### Phân biệt user token và service token

User token đại diện cho người dùng đã xác thực; service token đại diện cho client/workload theo Client Credentials. Không tự gán user `sub` vào service token hoặc giả lập một người dùng khi không có user context.

Với Client Credentials, scope phải gắn với client/service đã đăng ký và được cấp quyền. Nếu API cần biết tenant, service token chỉ được nhận tenant context khi có policy rõ ràng và nguồn xác thực đáng tin; không lấy tenant ID tùy ý từ request của client rồi chép vào token.

## 3. Khởi tạo project và dependency

Tạo ứng dụng Spring Boot với các dependency cần thiết:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-authorization-server")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    runtimeOnly("com.h2database:h2")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Dependency starter cho Authorization Server tùy phiên bản Spring Boot. Nếu phiên bản đang dùng không cung cấp starter này, thêm dependency Spring Authorization Server tương thích do BOM của dự án quản lý.

Cấu hình local tối thiểu:

~~~yaml
server:
  port: 9000

app:
  security:
    issuer: https://id.example.test

spring:
  datasource:
    url: jdbc:h2:mem:authorization;DB_CLOSE_DELAY=-1
    username: sa
    password:
  h2:
    console:
      enabled: false
~~~

Issuer ở local có thể dùng host test riêng. Trong production, issuer phải là URL HTTPS ổn định, được công bố trong metadata và khớp chính xác với cấu hình Resource Server. Không dùng issuer localhost trong token production.

H2 in-memory chỉ phù hợp cho lab ngắn hạn. Dữ liệu client, authorization, consent và refresh token sẽ mất khi process dừng; production cần database bền vững, migration/schema được quản lý và backup phù hợp.

## 4. Cấu hình Authorization Server

Spring Authorization Server cung cấp các protocol endpoint, filter và service nền. Trong lab, cấu hình một filter chain riêng cho authorization endpoint và một filter chain cho màn hình đăng nhập.

### 4.1. Security filter chains

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http);

        http.getConfigurer(OAuth2AuthorizationServerConfigurer.class)
                .oidc(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

Đây là cấu hình khởi đầu cho lab. OIDC được bật để hỗ trợ discovery/UserInfo theo cấu hình provider; chỉ bật endpoint và claim thực sự cần. Với production, cần cấu hình login/MFA, session/cookie, CSRF, CORS, rate limit, account lockout và quy trình recovery phù hợp. Không mở authorization endpoint hoặc trang quản trị cho truy cập ẩn danh ngoài phần protocol yêu cầu.

### 4.2. Issuer và signing key

Authorization Server ký JWT bằng private key. Resource Server lấy public key qua JWKS endpoint và xác minh chữ ký. Ví dụ tạo RSA key trong bộ nhớ:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() throws JOSEException {
    RSAKey rsaKey = new RSAKeyGenerator(2048)
            .keyID(UUID.randomUUID().toString())
            .generate();

    JWKSet jwkSet = new JWKSet(rsaKey);
    return new ImmutableJWKSet<>(jwkSet);
}

@Bean
AuthorizationServerSettings authorizationServerSettings(
        @Value("${app.security.issuer}") String issuer) {
    return AuthorizationServerSettings.builder()
            .issuer(issuer)
            .build();
}

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Key tạo ngẫu nhiên trong bộ nhớ chỉ dành cho lab. Restart sẽ tạo key mới, làm token đã phát hành trước đó không còn xác minh được. Production phải lấy private key từ KMS/HSM hoặc keystore được bảo vệ, có quy trình backup/rotation, kiểm soát quyền ký và công bố public key đúng thời điểm. Không commit private key vào repository, image hoặc cấu hình plaintext.

Khi xoay vòng khóa, công bố public key mới trước khi bắt đầu ký bằng key mới; giữ public key cũ trong JWKS đủ lâu để xác minh token còn hiệu lực và cache của Resource Server có thời gian cập nhật. Dùng `kid` duy nhất, theo dõi cache/JWKS refresh và có kế hoạch xử lý key compromise.

### 4.3. Đăng ký OAuth clients

Mỗi client cần khai báo rõ client authentication method, grant type, redirect URI, scope và token settings. Ví dụ dùng repository in-memory cho lab:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder,
        SecretProvider secretProvider) {

    RegisteredClient ordersWeb = RegisteredClient
            .withId(UUID.randomUUID().toString())
            .clientId("orders-web")
            .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri("http://127.0.0.1:8080/login/oauth2/code/orders-web")
            .scope("orders.read")
            .scope("orders.write")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(10))
                    .refreshTokenTimeToLive(Duration.ofDays(7))
                    .reuseRefreshTokens(false)
                    .build())
            .build();

    RegisteredClient workerService = RegisteredClient
            .withId(UUID.randomUUID().toString())
            .clientId("orders-worker")
            .clientSecret(passwordEncoder.encode(
                    secretProvider.require("orders-worker-client-secret")))
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
            .scope("orders.read")
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(5))
                    .build())
            .build();

    return new InMemoryRegisteredClientRepository(
            ordersWeb, workerService);
}
~~~

`secretProvider` trong ví dụ là abstraction đọc secret từ secret store; không tạo client secret bằng literal rồi commit. Public client dùng `ClientAuthenticationMethod.NONE` và bắt buộc PKCE; nó không có khả năng giữ client secret an toàn. Redirect URI phải được đăng ký chính xác, không dùng wildcard hoặc kiểm tra tiền tố lỏng lẻo.

`SecretProvider` là interface do ứng dụng định nghĩa và triển khai bằng adapter tới Secret Manager/KMS; đây không phải class có sẵn của Spring Authorization Server.

Confidential client có thể dùng `client_secret_basic` trong ví dụ. Với production, cân nhắc phương thức mạnh hơn như `private_key_jwt` hoặc mTLS khi hệ sinh thái hỗ trợ; lưu secret/private key trong Secret Manager/KMS và rotate theo chính sách. Chỉ cấp grant type và scope mà client thực sự cần.

Repository in-memory không phù hợp production: client đăng ký sẽ mất khi restart và khó kiểm soát thay đổi. Dùng `JdbcRegisteredClientRepository` hoặc implementation bền vững có quy trình provisioning, review, audit và thu hồi client.

### 4.4. Giới hạn audience và custom claims

Resource Server phải biết token được phát hành cho API nào. Có thể dùng token customizer để đặt audience cho access token:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer() {
    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            context.getClaims().audience(List.of("orders-api"));
        }
    };
}
~~~

Đảm bảo customizer này áp dụng đúng cho token profile của Orders API. Nếu Authorization Server phục vụ nhiều resource server, audience phải được xác định từ resource indicator/ủy quyền đã kiểm tra và allow-list; không gán một audience chung cho mọi token.

Chỉ thêm tenant claim hoặc role nếu API cần và nguồn dữ liệu đã được xác minh. Ví dụ tenant context phải lấy từ membership/policy service sau khi người dùng chọn tenant và server kiểm tra quyền. Không copy `tenant_id`, `role` hoặc scope từ query/header/body của client vào JWT.

Đối với token của Client Credentials, principal là client/service. Không tạo claim giả rằng có người dùng tương tác. Resource Server cần phân biệt token đại diện user với token đại diện workload nếu policy của API khác nhau.

## 5. User authentication và consent

Authorization Server cần một cơ chế xác thực người dùng trước khi cấp authorization code. Lab có thể tích hợp UserDetailsService hoặc một identity provider hiện có. Dữ liệu password phải được lưu dưới dạng password verifier với thuật toán chuyên dụng, salt và tham số phù hợp; không lưu plaintext, không log password và không đưa password vào token.

Nếu dùng user store trong cùng ứng dụng, cần tối thiểu:

- Trạng thái tài khoản active/locked và quy trình đổi/reset password.
- MFA hoặc step-up authentication cho thao tác nhạy cảm theo threat model.
- Rate limiting và phát hiện brute force/credential stuffing.
- Session management, cookie Secure/HttpOnly/SameSite phù hợp.
- Audit đăng nhập, thất bại, consent và thay đổi bảo mật.
- Quy trình thu hồi session và refresh token khi tài khoản bị khóa hoặc quyền bị thu hồi.

Consent cho phép người dùng xem client xin những scope nào và quyết định chấp thuận theo policy. Không hiển thị hoặc xin scope rộng hơn nhu cầu. Consent record phải được lưu theo client/user và có khả năng thu hồi.

Đối với hệ thống đã có IdP, thường nên để IdP xử lý mật khẩu/MFA và dùng Authorization Server theo mô hình federation hoặc tích hợp phù hợp, thay vì tạo thêm một kho password không cần thiết.

## 6. Protocol endpoints và các flow cấp token

Authorization Server cung cấp endpoint theo cấu hình. Các đường dẫn mặc định phổ biến của Spring Authorization Server gồm:

| Endpoint | Mục đích |
| --- | --- |
| `/oauth2/authorize` | Bắt đầu authorization request |
| `/oauth2/token` | Đổi authorization code hoặc grant hợp lệ lấy token |
| `/.well-known/openid-configuration` | OIDC discovery metadata |
| `/oauth2/jwks` | Công bố public keys |
| `/userinfo` | Trả claims user được phép qua OIDC UserInfo |
| `/oauth2/introspect` | Kiểm tra trạng thái opaque/reference token khi được cấu hình |
| `/oauth2/revoke` | Thu hồi token theo hỗ trợ của server |

Endpoint thực tế có thể được thay đổi qua `AuthorizationServerSettings` và cấu hình OIDC. Chỉ công bố endpoint cần thiết; bảo vệ endpoint quản trị và database khỏi truy cập công khai.

### 6.1. Authorization Code + PKCE

Đây là flow chính cho public client như SPA/mobile/native app:

1. Client tạo `code_verifier` ngẫu nhiên, khó đoán, giữ trong phiên giao dịch và tính `code_challenge = BASE64URL(SHA256(code_verifier))`.
2. Client chuyển trình duyệt tới authorization endpoint với `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state`, `code_challenge` và `code_challenge_method=S256`.
3. Authorization Server xác thực người dùng, yêu cầu consent nếu policy cần và trả authorization code qua redirect URI đã đăng ký.
4. Client gửi code, redirect URI và `code_verifier` tới token endpoint.
5. Authorization Server kiểm tra code, client, redirect URI, thời hạn, trạng thái dùng một lần và PKCE verifier.
6. Nếu hợp lệ, server phát access token và refresh token nếu client/policy được phép.

Ví dụ authorization request (giá trị chỉ minh họa):

~~~text
GET /oauth2/authorize?
  response_type=code
  &client_id=orders-web
  &redirect_uri=http%3A%2F%2F127.0.0.1%3A8080%2Flogin%2Foauth2%2Fcode%2Forders-web
  &scope=orders.read
  &state=<random-state>
  &nonce=<random-nonce>
  &code_challenge=<BASE64URL-SHA256-CHALLENGE>
  &code_challenge_method=S256
~~~

`state` chống CSRF/correlation attack trong authorization response và phải được client kiểm tra. Với OIDC, dùng `nonce` để liên kết ID token với authentication request và kiểm tra nonce khi nhận ID token. PKCE bảo vệ authorization code khỏi bị đổi bởi bên không có verifier.

Không dùng `plain` nếu `S256` được hỗ trợ. Redirect URI phải so khớp chính xác với URI đã đăng ký; không cho phép redirect tới domain do người dùng tùy ý cung cấp.

Token request sau khi client nhận code:

~~~http
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
client_id=orders-web&
code=<authorization-code>&
redirect_uri=http%3A%2F%2F127.0.0.1%3A8080%2Flogin%2Foauth2%2Fcode%2Forders-web&
code_verifier=<original-code-verifier>
~~~

Public client không gửi client secret vì nó không thể giữ secret an toàn. Authorization Server phải kiểm tra PKCE và mọi ràng buộc client/redirect URI trước khi cấp token.

### 6.2. Client Credentials cho worker service

Service-to-service flow không có người dùng tương tác. Client xác thực với Authorization Server và xin scope đã được cấp:

~~~bash
curl --user "$ORDERS_WORKER_CLIENT_ID" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=orders.read" \
  https://id.example.test/oauth2/token
~~~

Lệnh curl trên yêu cầu nhập password tương tác sau khi gửi username. Với CI hoặc môi trường tự động, dùng HTTP client đọc credential từ secret store/credential injection an toàn; tránh đặt secret trực tiếp trong command line, shell history hoặc log CI. Trong production, ưu tiên workload identity, private_key_jwt hoặc mTLS khi phù hợp với provider. Service chỉ nhận scope tối thiểu, audience chính xác và TTL ngắn.

Token Client Credentials đại diện cho client/workload. Không dùng token này để giả lập hành động của một user. Nếu cần on-behalf-of, dùng flow/token exchange phù hợp và giữ rõ actor/subject semantics.

### 6.3. Refresh token

Refresh token được dùng tại token endpoint để xin access token mới. Chỉ cấp khi client, grant và policy cho phép; không phải client nào cũng cần refresh token. Với public client, bảo vệ refresh token ở client storage và cân nhắc sender constraint/rotation theo khả năng hỗ trợ.

Cấu hình `reuseRefreshTokens(false)` trong ví dụ yêu cầu phát refresh token mới khi refresh thành công. Khi token cũ bị dùng lại, server phải từ chối token đã hết hiệu lực. Nếu cần thu hồi cả token family/session khi phát hiện reuse, cần cơ chế theo dõi family và policy xử lý tương ứng; không giả định chỉ bật rotation đã tự động giải quyết mọi trường hợp reuse.

## 7. Lưu trữ authorization, client và consent

Authorization Server cần giữ trạng thái đủ để kiểm tra authorization code, refresh token, consent, revoke và audit. Dữ liệu lưu trữ có thể bao gồm:

- Registered client: client ID, client authentication method, grant type, redirect URI, scope và token settings.
- Authorization: principal/client, grant, authorized scopes, access/refresh token metadata và trạng thái.
- Consent: user, client và scope đã được chấp thuận.
- Signing key metadata: key ID, thuật toán, trạng thái active/retiring và public key đã công bố.
- Session/account state: trạng thái xác thực và policy cần thiết, theo mô hình lưu trữ của ứng dụng.

Với Spring Authorization Server, có thể dùng `JdbcRegisteredClientRepository`, `JdbcOAuth2AuthorizationService` và `JdbcOAuth2AuthorizationConsentService`. Sử dụng schema/migration tương ứng đúng phiên bản thư viện; kiểm soát quyền đọc database, mã hóa backup và không expose bảng authorization qua API nghiệp vụ.

### Quy tắc lưu trữ

1. Không lưu password dạng plaintext. Dùng password hashing chuyên dụng hoặc external IdP.
2. Không log access token, refresh token, authorization code, client secret hoặc private key.
3. Giới hạn quyền đọc bảng authorization/consent; dữ liệu này có thể chứa token hoặc metadata nhạy cảm.
4. Đặt retention và cleanup cho authorization code/token state đã hết hạn theo policy.
5. Audit thao tác đăng ký/sửa client, đổi redirect URI, cấp quyền, consent và revoke.
6. Dùng database bền vững, backup mã hóa, kiểm tra restore và migration có review.
7. Tách dữ liệu dev/test khỏi production; không copy token/credential thật sang môi trường lab.

### Revocation và JWT access token

JWT self-contained có thể được xác minh offline bởi Resource Server. Việc xóa authorization record tại Authorization Server không tự động làm mọi Resource Server ngừng chấp nhận JWT đã phát hành. Để rút ngắn thời gian hiệu lực sau revoke, kết hợp TTL access token ngắn với introspection/reference token, denylist, session/policy version hoặc cơ chế kiểm tra trạng thái phù hợp mức rủi ro.

Không nhầm endpoint revoke với bảo đảm mọi JWT đã bị vô hiệu ngay lập tức. Phải định nghĩa rõ thời gian tối đa một token bị thu hồi còn được chấp nhận và cách từng Resource Server nhận trạng thái revoke.

## 8. Tích hợp Orders Resource Server

Orders API phải xác minh access token độc lập. Nó không tin token chỉ vì request đi qua API Gateway hoặc vì client đã đăng nhập thành công.

### 8.1. Cấu hình Resource Server

Ví dụ cấu hình issuer và audience:

~~~java
@Bean
JwtDecoder ordersJwtDecoder(
        @Value("${app.security.issuer}") String issuer) {

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null
        );
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(issuer),
                    audienceValidator
            )
    );

    return decoder;
}
~~~

Cấu hình filter chain cho API:

~~~java
@Configuration
@EnableMethodSecurity
@EnableWebSecurity
class OrdersResourceServerSecurity {

    @Bean
    SecurityFilterChain ordersApiChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Nếu ứng dụng dùng cấu hình property tự động của Spring Boot, có thể đặt `issuer-uri` và bổ sung audience validator trong decoder bean. Tránh khai báo hai decoder cạnh tranh trong cùng application context. Production cần HTTPS, timeout/retry/cache hợp lý cho discovery/JWKS, kiểm soát outbound network và giám sát trạng thái key provider.

### 8.2. Kiểm tra scope tại endpoint

~~~java
@RestController
@RequestMapping("/api/orders")
class OrdersController {

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    List<OrderDto> listOrders() {
        return orderService.listForCurrentTenant();
    }

    @PostMapping
    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    OrderDto createOrder(@RequestBody CreateOrderRequest request) {
        return orderService.createForCurrentTenant(request);
    }
}
~~~

Ví dụ rút gọn này giả định service đã xác định tenant context từ authentication đã xác thực và áp dụng tenant filter ở repository. Scope chỉ xác định loại hành động; nó không thay thế kiểm tra quyền trên từng resource hoặc tenant boundary.

Kết quả HTTP thường mong đợi:

- `401 Unauthorized` khi thiếu token, chữ ký sai, issuer/audience sai hoặc token hết hạn.
- `403 Forbidden` khi token hợp lệ nhưng thiếu scope/permission hoặc không có quyền trên tài nguyên.
- Có thể dùng `404 Not Found` nhất quán cho tài nguyên thuộc tenant khác để hạn chế lộ sự tồn tại của dữ liệu.

## 9. Kiểm thử Authorization Server và Resource Server

Kiểm thử cả flow cấp token và hành vi API. Không chỉ test một hàm tạo JWT; cần chứng minh filter chain, decoder, client policy và persistence hoạt động cùng nhau.

### 9.1. Kiểm thử Client Credentials

Ví dụ test tích hợp dùng MockMvc; cấu hình test phải có client đã đăng ký và secret fixture được quản lý trong môi trường test:

~~~java
@Test
void clientCredentialsIssuesOrdersReadToken() throws Exception {
    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("orders-worker", testClientSecret))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("scope", "orders.read"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").isNotEmpty())
        .andExpect(jsonPath("$.token_type").value("Bearer"))
        .andExpect(jsonPath("$.expires_in").isNumber())
        .andExpect(jsonPath("$.scope").value("orders.read"));
}
~~~

Test này xác nhận token endpoint chấp nhận client đã xác thực và cấp đúng scope. Sau khi nhận access token, giải mã bằng decoder kiểm thử để kiểm tra issuer, audience, thời gian và không có claim secret.

### 9.2. Kiểm thử token validation

| Ca | Token/request | Kết quả mong đợi |
| --- | --- | --- |
| AS-01 | Client hợp lệ xin scope được cấp | Token được phát hành |
| AS-02 | Client secret sai | Token endpoint trả lỗi OAuth phù hợp |
| AS-03 | Client xin scope chưa được cấp | Token endpoint trả lỗi `invalid_scope` theo OAuth policy |
| AS-04 | Authorization Code thiếu PKCE verifier hoặc verifier sai | Không cấp token |
| AS-05 | Redirect URI không khớp URI đã đăng ký | Authorization request bị từ chối |
| AS-06 | Authorization code đã dùng hoặc hết hạn | Không đổi được token |
| RS-01 | JWT chữ ký hợp lệ, issuer/audience đúng | API chấp nhận nếu scope/quyền đủ |
| RS-02 | JWT ký bằng key không tin cậy | 401 |
| RS-03 | Issuer mismatch | 401 |
| RS-04 | Audience không có `orders-api` | 401 |
| RS-05 | Token hết hạn hoặc chưa đến `nbf` | 401 |
| RS-06 | Token hợp lệ nhưng thiếu `orders.read` | 403 |
| RS-07 | Scope đọc có nhưng gọi endpoint ghi | 403 |
| RT-01 | Refresh token hợp lệ, client đúng | Cấp access token mới theo policy |
| RT-02 | Refresh token cũ bị dùng lại sau rotation | Từ chối; xử lý token family/session theo policy |
| RT-03 | Refresh token đã revoke hoặc session bị khóa | Không cấp token mới |

### 9.3. Kiểm thử Authorization Code + PKCE

Kiểm thử flow này qua browser/MockMvc hoặc test harness có thể:

1. Tạo verifier/challenge ngẫu nhiên theo chuẩn PKCE S256.
2. Gửi authorization request với client ID, redirect URI, scope, state và challenge.
3. Xác thực user bằng test user store và chấp thuận consent nếu yêu cầu.
4. Lấy authorization code từ redirect response trong môi trường test.
5. Gửi token request với code và verifier gốc.
6. Xác minh token có issuer/audience/scope đúng.
7. Lặp lại với verifier sai, redirect URI sai và code đã dùng; tất cả phải bị từ chối.

Không dùng Spring Security test helper tạo sẵn Authentication để tuyên bố đã kiểm thử token decoding. Khi kiểm tra Resource Server, gửi compact JWT ký thật qua Bearer header để decoder và filter chain thực sự chạy.

### 9.4. Kiểm tra không phát hành secret

~~~java
@Test
void accessTokenContainsNoCredentialClaims() {
    Jwt jwt = testJwtDecoder.decode(issueTestAccessToken());

    assertThat(jwt.getClaims()).doesNotContainKeys(
            "password",
            "client_secret",
            "api_key",
            "private_key",
            "database_password",
            "refresh_token"
    );
}
~~~

Danh sách trên là ví dụ. Thêm các alias/claim nội bộ có khả năng chứa credential vào policy test. Cũng rà soát log/trace/APM để xác nhận Authorization header và token không bị ghi lại.

## 10. Quy trình thực hành theo từng milestone

Chia dự án thành các milestone để có thể kiểm tra đầu ra sau mỗi bước:

| Milestone | Công việc | Đầu ra cần chứng minh |
| --- | --- | --- |
| M1 — Contract | Chốt issuer, audience, scopes, client types, TTL và flow | Token contract được ghi thành tài liệu |
| M2 — Bootstrap | Tạo Spring Boot app, security chains, issuer settings, JWK source | Discovery và JWKS endpoint hoạt động |
| M3 — Clients | Đăng ký public client PKCE và confidential worker client | Client policy/redirect URI/scope đúng |
| M4 — User auth | Tích hợp user store/IdP, login và consent | User chỉ nhận code sau khi xác thực/consent |
| M5 — Token issuance | Cấu hình JWT claims, audience, TTL, signing key | Access token đúng profile, không có secret |
| M6 — Resource Server | Cấu hình decoder, issuer/audience validator và scope | Orders API chỉ chấp nhận token hợp lệ |
| M7 — Persistence | Lưu registered client, authorization, consent | Restart không làm mất trạng thái cần thiết |
| M8 — Lifecycle | Refresh rotation, revoke, key rotation và session handling | Token cũ/reuse/revoke được xử lý theo policy |
| M9 — Security tests | Chạy positive/negative/integration tests | Ma trận kiểm thử đạt |
| M10 — Operations | TLS, KMS/HSM, rate limit, audit, alert và backup | Checklist vận hành được review |

Không đánh dấu milestone hoàn thành chỉ vì endpoint trả HTTP 200. Cần kiểm tra claims, scope, audience, trạng thái token và quyền truy cập thật của Resource Server.

## 11. Checklist bảo mật trước khi đưa vào môi trường thật

- [ ] Chỉ dùng HTTPS; issuer public khớp metadata và cấu hình Resource Server.
- [ ] Authorization Code + PKCE S256 cho public client; không dùng password grant.
- [ ] Redirect URI chính xác, không wildcard; xác thực state và OIDC nonce.
- [ ] Client authentication method phù hợp loại client; không nhúng secret vào SPA/mobile.
- [ ] Scope tối thiểu, audience cụ thể; kiểm tra resource/tenant authorization ở API.
- [ ] Private signing key được bảo vệ bởi KMS/HSM/keystore; có rotation và compromise plan.
- [ ] JWKS publish/refresh và overlap khóa được kiểm thử.
- [ ] Access token TTL phù hợp; refresh token rotation/reuse detection/revocation có policy.
- [ ] Client, authorization và consent persistence bền vững; database/backup được bảo vệ.
- [ ] Login có MFA/abuse protection theo rủi ro; session/cookie/CSRF/CORS được cấu hình.
- [ ] Rate limit token endpoint và endpoint đăng nhập; giám sát brute force và lỗi xác minh.
- [ ] Không log access token, refresh token, authorization code, password, client secret hoặc private key.
- [ ] Có audit cho đăng ký client, thay redirect URI, consent, cấp/revoke token và key rotation.
- [ ] Có quy trình incident response, backup/restore, patching và review cấu hình định kỳ.

## 12. Lỗi thường gặp trong dự án

**Dùng một signing key ngẫu nhiên mỗi lần restart:** token đang còn hiệu lực lập tức không xác minh được. Dùng key bền vững và quy trình rotation có overlap.

**Không đặt audience:** token được phát hành cho API này có thể bị gửi sang API khác nếu các API chỉ kiểm tra chữ ký/issuer. Đặt audience và kiểm tra tại từng Resource Server.

**Cấp scope rộng cho mọi client:** một client bị compromise có quyền vượt nhu cầu. Đăng ký scope theo client, grant và use case.

**Cho public client giữ client secret:** secret trong JavaScript/mobile package có thể bị trích xuất. Dùng PKCE và public-client registration phù hợp.

**Dùng refresh token không rotation:** token bị đánh cắp có thể được dùng kéo dài. Cấu hình rotation, reuse detection và thu hồi token family/session.

**Tin claim do client gửi:** client tự đặt tenant/role/scope trong request. Authorization Server chỉ phát hành claim từ dữ liệu và policy đã xác minh.

**Chỉ test controller bằng mock JWT:** bỏ qua decoder, chữ ký, issuer và audience. Dùng token ký thật qua filter chain trong test tích hợp.

**Nghĩ revoke JWT có hiệu lực tức thì ở mọi nơi:** Resource Server có thể xác minh JWT offline đến khi hết hạn. Xác định rõ cơ chế và thời gian thu hồi tối đa.

## 13. Bài tập tổng kết

**Tình huống:** Bạn cần xây Authorization Server cho Orders API với hai client: Orders Web (SPA) và Orders Worker (backend). Orders Web cần đọc đơn hàng của người dùng đã đăng nhập; Orders Worker chạy lịch đồng bộ và chỉ cần đọc dữ liệu theo quyền service.

1. Chọn grant type và client authentication method cho từng client.
2. Nêu cách PKCE bảo vệ authorization code và vì sao SPA không được giữ client secret.
3. Đề xuất audience, scope và TTL khác nhau cho hai loại token.
4. Giải thích vì sao Worker token không nên giả lập user `sub`.
5. Mô tả cách bảo vệ signing key, công bố JWKS và xoay vòng khóa.
6. Thiết kế refresh token rotation/reuse handling cho Orders Web.
7. Nêu cách Orders API kiểm tra issuer, audience, scope và tenant/resource boundary.
8. Liệt kê ít nhất năm negative test trước khi phát hành.

**Gợi ý đáp án:**

- Orders Web: Authorization Code + PKCE S256, public client, redirect URI cố định, scope user-facing tối thiểu.
- Orders Worker: Client Credentials, confidential client authentication bằng secret store hoặc workload identity/private_key_jwt/mTLS khi hỗ trợ.
- Cả hai token phải có audience dành cho Orders API; scope và TTL được giới hạn theo client/use case. Worker token đại diện service principal.
- Signing key nằm trong KMS/HSM/keystore, JWKS công bố public key, key rotation có overlap và theo dõi cache.
- Refresh token của Web được bảo vệ, rotate khi dùng, phát hiện reuse và revoke session/token family theo policy.
- Orders API xác minh chữ ký, issuer, audience, thời hạn, scope và quyền trên tài nguyên/tenant; không tin tenant do client tự gửi.
- Negative test gồm sai client secret, redirect URI sai, PKCE sai, code reuse, sai issuer/audience, chữ ký sai, token hết hạn, thiếu scope, refresh token reuse và token đã revoke.

## Ghi nhớ

- Authorization Server xác thực và phát hành token; Resource Server xác minh token và thực thi quyền.
- Dùng Authorization Code + PKCE cho public client và Client Credentials cho service principal.
- Token phải có issuer, audience, expiry và scope đúng; không chứa password hoặc secret.
- Signing key cần được bảo vệ, JWKS công bố public key và rotation phải có overlap.
- Lưu registered client, authorization, consent và refresh state bền vững; quy định rõ revoke và reuse detection.
- Kiểm thử cả protocol flow, decoder, HTTP filter chain, audience/scope và tenant/resource authorization.
- Hoàn thành lab chưa đồng nghĩa Authorization Server sẵn sàng production; cần security review, vận hành và kiểm soát thay đổi.

### Tài liệu tham khảo

- [Spring Authorization Server — Reference](https://docs.spring.io/spring-authorization-server/reference/)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
