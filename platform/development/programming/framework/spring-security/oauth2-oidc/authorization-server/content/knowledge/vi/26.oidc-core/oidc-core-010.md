# Chính sách thuật toán ký ID Token theo cấu hình client

## 1. Bối cảnh và mục tiêu

Trong **OAuth 2.0/OpenID Connect Authorization Server** xây dựng bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, ID Token là JWT mang thông tin xác thực người dùng mà OpenID Provider (OP) phát hành cho một OIDC client. ID Token phải được ký bằng JSON Web Signature (JWS) để client kiểm tra tính toàn vẹn và nguồn phát hành.

Một OP có thể phục vụ nhiều client với yêu cầu tương thích khác nhau. Client cũ có thể chỉ hỗ trợ RSA RS256; một client mới có thể hỗ trợ ECDSA ES256. Chính sách ký cần xác định thuật toán nào được phép cho từng client, bảo đảm thuật toán đó nằm trong danh sách OP công bố và có private key phù hợp để ký.

Ví dụ xuyên suốt: `customer-portal` được đăng ký dùng RS256; `mobile-app` được đăng ký dùng ES256. Cả hai cùng dùng Authorization Code Flow và nhận ID Token từ một Authorization Server. Khi cấp token, server đọc cấu hình của RegisteredClient, chọn thuật toán đã được phê duyệt cho client đó và dùng khóa tương ứng. Client kiểm tra chữ ký theo `alg` trong protected header và public key lấy từ JWKS.

Sau bài học, bạn có thể:

1. Phân biệt thuật toán ký ID Token, thuật toán ký client assertion và thuật toán OP quảng bá trong discovery metadata.
2. Hiểu trường OIDC Dynamic Client Registration `id_token_signed_response_alg`.
3. Cấu hình thuật toán theo từng `RegisteredClient` bằng `TokenSettings.idTokenSignatureAlgorithm(...)`.
4. Giải thích cách `JwtGenerator`, `JwtEncoder` và `JWKSource` phối hợp để tạo ID Token.
5. Bảo đảm JWK có key type, curve, `alg`, `use` và `kid` phù hợp thuật toán.
6. Áp dụng allow-list khi đăng ký client động và giữ cấu hình thuật toán trong kho RegisteredClient.
7. Kiểm thử thuật toán trong JWT header, chữ ký, discovery metadata và khả năng xác minh của OIDC client.
8. Quản lý thay đổi thuật toán, key rotation và sự cố khi không còn khóa tương thích.

**Phạm vi phiên bản:** Ví dụ Java dùng Spring Authorization Server 1.5.x, Spring Security 6.x và Servlet stack. API chính là `TokenSettings.Builder.idTokenSignatureAlgorithm(SignatureAlgorithm)`. Các bản Spring Security mới tích hợp Authorization Server có thể thay package hoặc cách cấu hình; hãy kiểm tra Javadoc của đúng version ứng dụng.

## 2. Thuật toán ký ID Token trong OIDC

### 2.1. ID Token là JWT được ký

OIDC ID Token là một security token chứa claims về lần xác thực End-User. Ở dạng JWS compact, token có ba phần:

~~~text
BASE64URL(protected-header).
BASE64URL(payload).
BASE64URL(signature)
~~~

Protected header chứa thuật toán ký, ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "op-rsa-2026-01",
  "typ": "JWT"
}
~~~

Payload chứa claims như `iss`, `sub`, `aud`, `exp`, `iat`, `auth_time`, `nonce` và các claim khác tùy flow. Chữ ký JWS cho phép client xác minh token không bị sửa đổi và được ký bởi private key tương ứng với public key tin cậy của OP.

**Ký không phải mã hóa.** Với JWS thông thường, header và payload có thể đọc được sau Base64URL decoding. Nếu cần bảo mật nội dung bằng JWE, đó là chính sách mã hóa riêng, với các tham số như `id_token_encrypted_response_alg` và `id_token_encrypted_response_enc`; không đồng nhất chúng với thuật toán ký JWS.

### 2.2. `id_token_signed_response_alg`

OIDC Dynamic Client Registration định nghĩa metadata client:

~~~json
{
  "client_name": "customer-portal",
  "redirect_uris": [
    "https://portal.example.com/login/oauth2/code/oidc"
  ],
  "response_types": ["code"],
  "grant_types": ["authorization_code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "id_token_signed_response_alg": "RS256"
}
~~~

`id_token_signed_response_alg` mô tả JWS algorithm mà client yêu cầu OP dùng để ký ID Token phát hành cho client đó. Đây là **cấu hình theo client**, không phải thuật toán client dùng để ký JWT xác thực chính nó.

Theo OIDC Dynamic Client Registration, nếu client không khai báo trường này, mặc định là `RS256`. OP vẫn phải kiểm tra thuật toán yêu cầu có nằm trong tập được OP hỗ trợ và có cấu hình khóa tương thích hay không.

### 2.3. Ba trường thuật toán thường bị nhầm

| Trường/API | Ai ký? | JWT nào? | Phạm vi |
| --- | --- | --- | --- |
| `id_token_signed_response_alg` | Authorization Server / OP | ID Token gửi cho client | Yêu cầu theo từng client trong OIDC registration. |
| `token_endpoint_auth_signing_alg` | OAuth client | `client_assertion` gửi tới Token Endpoint khi dùng `private_key_jwt` hoặc `client_secret_jwt` | Thuật toán xác thực client, không điều khiển ID Token. |
| `id_token_signing_alg_values_supported` | Authorization Server / OP công bố | Các ID Token mà OP có thể ký | Danh sách toàn cục trong OpenID Provider Configuration. |

Ví dụ `customer-portal` có thể yêu cầu ID Token RS256 nhưng dùng `client_secret_basic` tại Token Endpoint; khi đó không có client assertion JWT. Một client khác có thể yêu cầu ID Token ES256 nhưng dùng `private_key_jwt` với client assertion PS256. Hai quyết định này độc lập.

## 3. Chính sách thuật toán theo từng RegisteredClient

### 3.1. TokenSettings là nơi cấu hình trong Spring Authorization Server

Spring Authorization Server biểu diễn chính sách ID Token trong `TokenSettings`. API:

~~~java
TokenSettings.builder()
    .idTokenSignatureAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

`TokenSettings` thuộc về `RegisteredClient`, do đó mỗi client có thể lưu một thuật toán riêng. Giá trị mặc định của `TokenSettings` trong Spring Authorization Server 1.5.8 là `RS256`.

Ví dụ cấu hình client RS256:

~~~java
RegisteredClient customerPortal = RegisteredClient
    .withId("customer-portal-record-001")
    .clientId("customer-portal")
    .clientName("Customer Portal")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri(
        "https://portal.example.com/login/oauth2/code/oidc")
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .idTokenSignatureAlgorithm(SignatureAlgorithm.RS256)
        .build())
    .build();
~~~

Ví dụ client ES256:

~~~java
RegisteredClient mobileApp = RegisteredClient
    .withId("mobile-app-record-001")
    .clientId("mobile-app")
    .clientName("Mobile App")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.NONE)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("com.example.mobile:/oauth2redirect")
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .idTokenSignatureAlgorithm(SignatureAlgorithm.ES256)
        .build())
    .build();
~~~

Hai cấu hình trên minh họa hai client khác nhau; redirect URI, client authentication method và các policy khác phải được thiết kế theo loại ứng dụng thực tế. Public client như ứng dụng mobile phải dùng PKCE và không được dựa vào một client secret nhúng trong ứng dụng.

### 3.2. Đọc chính sách từ RegisteredClient

Khi xử lý một authorization request, token generation context chứa `RegisteredClient` tương ứng. Thuật toán của ID Token có thể được đọc từ:

~~~java
SignatureAlgorithm algorithm = context
    .getRegisteredClient()
    .getTokenSettings()
    .getIdTokenSignatureAlgorithm();
~~~

Đây là một cấu hình thuộc bản ghi client, không nên suy ra từ query parameter do browser gửi tại thời điểm authorization. Nếu client thay đổi thuật toán, thay đổi đó phải đi qua quy trình cập nhật registration có kiểm soát và được lưu vào RegisteredClientRepository.

### 3.3. Không nhầm TokenSettings với ClientSettings

`ClientSettings` chứa các chính sách như yêu cầu PKCE, consent, JWK Set URL hoặc thuật toán ký JWT dùng để xác thực client tại Token Endpoint. `TokenSettings` chứa chính sách token, trong đó có thuật toán ký ID Token.

~~~java
ClientSettings clientSettings = ClientSettings.builder()
    .tokenEndpointAuthenticationSigningAlgorithm(
        SignatureAlgorithm.RS256)
    .build();

TokenSettings tokenSettings = TokenSettings.builder()
    .idTokenSignatureAlgorithm(SignatureAlgorithm.ES256)
    .build();
~~~

Đoạn minh họa trên thể hiện hai nhóm cấu hình độc lập. `tokenEndpointAuthenticationSigningAlgorithm(...)` dùng kiểu `JwsAlgorithm` và chỉ áp dụng cho client assertion; `idTokenSignatureAlgorithm(...)` dùng `SignatureAlgorithm` cho ID Token. Không lấy giá trị ở một nhóm để thay cho nhóm kia.

## 4. JwtGenerator áp dụng thuật toán ra sao?

### 4.1. Chuỗi tạo ID Token

Trong cấu hình mặc định, `JwtGenerator` có thể tạo JWT dùng làm OAuth access token hoặc OIDC ID Token. Khi Authorization Code Flow hoàn tất và cần ID Token:

1. Authorization Server tìm `RegisteredClient` tương ứng với authorization.
2. Token generation context xác định token type là ID Token.
3. `JwtGenerator` đọc `TokenSettings` của client.
4. Header được tạo với JWS algorithm phù hợp chính sách.
5. `JwtEncoder` chọn khóa tương thích từ `JWKSource` và ký JWT.
6. Authorization Server lưu ID Token vào authorization và trả token response theo OIDC flow.

~~~mermaid
flowchart TD
    A["Authorization Code Flow hoàn tất"] --> B["RegisteredClient"]
    B --> C["TokenSettings.idTokenSignatureAlgorithm"]
    C --> D["JwtGenerator"]
    D --> E["JwsHeader: alg + kid"]
    E --> F["JwtEncoder"]
    F --> G["JWKSource chọn private key tương thích"]
    G --> H["Ký ID Token"]
    H --> I["ID Token trả cho OIDC Client"]
~~~

### 4.2. Không cần customizer chỉ để chọn thuật toán

Với `JwtGenerator` mặc định, hãy cấu hình `TokenSettings` cho client. Không cần tự sửa `alg` trong `OAuth2TokenCustomizer<JwtEncodingContext>` chỉ để đạt lựa chọn per-client.

`JwtGenerator.setJwtCustomizer(...)` là điểm mở rộng để tùy chỉnh JWS headers và claims. Nếu một customizer tự ghi đè header `alg`, nó có thể phá vỡ chính sách trong `TokenSettings`, khiến header không còn tương ứng với key selection hoặc thuật toán đã phê duyệt.

Chỉ customizer header khi có một yêu cầu JOSE cụ thể, có kiểm tra token type và có test chứng minh `alg`, `kid`, JWK và chữ ký vẫn tương thích.

### 4.3. Thuật toán ID Token không tự đổi thuật toán access token

`TokenSettings.idTokenSignatureAlgorithm` là cấu hình cho ID Token. Không dùng nó như một thiết lập chung cho mọi JWT. Access token JWT có chính sách ký và key selection riêng thông qua token generator, encoder và JWKSource.

Khi thay đổi ID Token từ RS256 sang ES256, hãy kiểm tra ID Token header. Không giả định access token JWT cũng phải đổi sang ES256 hoặc opaque access token bị ảnh hưởng.

## 5. JWK và key selection phải khớp thuật toán

### 5.1. Thuật toán quyết định loại khóa

| JWS algorithm | Loại khóa thường dùng | Điều kiện key |
| --- | --- | --- |
| `RS256`, `RS384`, `RS512` | RSA | RSA public/private key phù hợp, modulus đủ mạnh. |
| `PS256`, `PS384`, `PS512` | RSA | RSA key và hỗ trợ RSA-PSS trong crypto provider/encoder. |
| `ES256` | EC P-256 | Curve P-256 và cặp khóa EC tương ứng. |
| `ES384` | EC P-384 | Curve P-384. |
| `ES512` | EC P-521 | Curve P-521. |

Không thể ký ES256 bằng RSA private key hoặc ký RS256 bằng EC private key. Nếu client yêu cầu thuật toán mà JWKSource không có private key tương thích, token generation phải thất bại an toàn.

### 5.2. JWK metadata cần nhất quán

Một JWK dùng để ký thường có:

- `kty`: key type, ví dụ `RSA` hoặc `EC`.
- `use`: `sig` cho chữ ký.
- `alg`: thuật toán dự kiến, nếu metadata được gắn.
- `kid`: ID ổn định để client chọn public key tương ứng.
- Public parameters: ví dụ RSA `n`/`e`, EC `crv`/`x`/`y`.
- Private parameters: chỉ ở kho nội bộ dùng ký, tuyệt đối không xuất ra JWKS công khai.

Ví dụ JWK RSA public:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "alg": "RS256",
  "kid": "op-rsa-2026-01",
  "n": "base64url-modulus",
  "e": "AQAB"
}
~~~

Ví dụ JWK EC public:

~~~json
{
  "kty": "EC",
  "use": "sig",
  "alg": "ES256",
  "kid": "op-ec-2026-01",
  "crv": "P-256",
  "x": "base64url-x-coordinate",
  "y": "base64url-y-coordinate"
}
~~~

Các giá trị tham số trong ví dụ là placeholder, không phải khóa thật.

### 5.3. JWKSource có thể chứa nhiều loại key

Khi OP phục vụ client RS256 và ES256, JWKSource có thể quản lý nhiều JWK:

~~~java
JWKSet jwkSet = new JWKSet(List.of(
    rsaSigningJwk,
    ecSigningJwk
));

JWKSource<SecurityContext> jwkSource =
    new ImmutableJWKSet<>(jwkSet);
~~~

`rsaSigningJwk` và `ecSigningJwk` là các Nimbus JWK đã được tạo từ key pair tương ứng. Với production, key material nên được lưu trong keystore/KMS/HSM và được nạp qua key manager phù hợp; không tạo lại khóa ngẫu nhiên mỗi lần ứng dụng khởi động.

`NimbusJwtEncoder` dùng selector dựa trên JWS header để tìm key phù hợp. Đảm bảo:

1. Có private key phù hợp thuật toán đang active.
2. Không có nhiều private keys cùng khớp selector khiến encoder không chọn được một key duy nhất.
3. `kid` trong header xác định đúng public JWK trong JWKS.
4. Public JWK và private key ký token là cùng một cặp.
5. JWKS công khai không chứa private key parameters.

### 5.4. Không chỉ dựa vào kid

`kid` giúp định vị key trong JWK Set, nhưng bản thân `kid` không chứng minh thuật toán hoặc key là an toàn. Resource Server/OIDC client phải xác minh chữ ký theo thuật toán allow-list và key phù hợp; không tin thuật toán tùy ý do JWT header yêu cầu.

Khi một key được sử dụng cho nhiều thuật toán, phải bảo đảm key policy cho phép chính xác các thuật toán đó. Tốt hơn là phân chia key theo thuật toán/role nếu yêu cầu bảo mật hoặc audit cần ranh giới rõ.

## 6. OIDC Dynamic Client Registration

### 6.1. Client gửi thuật toán trong registration request

Một registration request có thể khai báo:

~~~http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer <initial-access-token>
Content-Type: application/json

{
  "redirect_uris": [
    "https://partner.example.com/oidc/callback"
  ],
  "response_types": ["code"],
  "grant_types": ["authorization_code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "id_token_signed_response_alg": "ES256"
}
~~~

Endpoint Dynamic Client Registration trong Spring Authorization Server **bị tắt mặc định**. Chỉ bật khi tổ chức cần chức năng này và đã có chính sách bảo vệ initial access token, client registration, redirect URI và client metadata.

### 6.2. Validate algorithm trước khi lưu

Không chấp nhận bất kỳ chuỗi thuật toán nào client gửi. Xây allow-list theo năng lực thật của OP:

~~~java
private static final Map<String, SignatureAlgorithm>
        ALLOWED_ID_TOKEN_ALGORITHMS = Map.of(
            "RS256", SignatureAlgorithm.RS256,
            "ES256", SignatureAlgorithm.ES256
        );
~~~

Khi nhận `id_token_signed_response_alg`:

1. Nếu không có giá trị, áp dụng default đã công bố (thường RS256 trong OIDC registration).
2. Nếu có giá trị, kiểm tra nó thuộc allow-list.
3. Kiểm tra OP có private key/JWK tương thích.
4. Kiểm tra thuật toán được công bố trong `id_token_signing_alg_values_supported`.
5. Lưu thuật toán vào `RegisteredClient.tokenSettings`.
6. Trả metadata registration nhất quán với giá trị đã lưu.

Nếu không hỗ trợ thuật toán, từ chối registration bằng lỗi `invalid_client_metadata` theo OIDC Dynamic Client Registration; không âm thầm thay thuật toán client yêu cầu bằng thuật toán khác.

### 6.3. Map registration metadata sang TokenSettings

`OidcClientRegistration` cung cấp `getIdTokenSignedResponseAlgorithm()`. `OidcClientRegistrationAuthenticationProvider` cho phép thay `RegisteredClient` converter bằng `setRegisteredClientConverter(...)`. Nếu ứng dụng tùy chỉnh converter hoặc cần thực thi allow-list riêng, có thể ánh xạ metadata rõ ràng:

~~~java
private static final Converter<OidcClientRegistration, RegisteredClient>
        DEFAULT_CONVERTER =
            new OidcClientRegistrationRegisteredClientConverter();

private static Converter<OidcClientRegistration, RegisteredClient>
        idTokenAlgorithmConverter() {

    return registration -> {
        RegisteredClient registeredClient =
            DEFAULT_CONVERTER.convert(registration);

        String requestedAlgorithm =
            registration.getIdTokenSignedResponseAlgorithm();

        SignatureAlgorithm algorithm =
            requestedAlgorithm == null
                ? SignatureAlgorithm.RS256
                : ALLOWED_ID_TOKEN_ALGORITHMS.get(requestedAlgorithm);

        if (algorithm == null) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    "invalid_client_metadata",
                    "Unsupported id_token_signed_response_alg",
                    null));
        }

        TokenSettings tokenSettings = TokenSettings.withSettings(
            registeredClient.getTokenSettings().getSettings())
            .idTokenSignatureAlgorithm(algorithm)
            .build();

        return RegisteredClient.from(registeredClient)
            .tokenSettings(tokenSettings)
            .build();
    };
}
~~~

Đây là ví dụ cho converter tùy chỉnh. Trong ứng dụng thực, hãy xác nhận converter mặc định của version đang dùng đã ánh xạ metadata đúng theo yêu cầu; nếu đã có mapping, không thêm một lớp chuyển đổi trùng lặp. Nếu thay converter, phải giữ nguyên các trường registration khác như redirect URI, grant type, authentication method, scope và client secret.

### 6.4. Gắn converter vào OIDC registration provider

Ví dụ cấu hình endpoint:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .oidc(oidc -> oidc
                .clientRegistrationEndpoint(registration ->
                    registration.authenticationProviders(providers ->
                        providers.forEach(provider -> {
                            if (provider instanceof
                                    OidcClientRegistrationAuthenticationProvider
                                        registrationProvider) {
                                registrationProvider
                                    .setRegisteredClientConverter(
                                        idTokenAlgorithmConverter());
                            }
                        })))))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Đoạn cấu hình minh họa cách gắn converter vào provider mặc định. Ứng dụng còn cần `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, `JWKSource`, `JwtDecoder` và các cấu hình OIDC khác. Bảo vệ endpoint registration bằng access token có quyền phù hợp; không mở endpoint cho bất kỳ caller ẩn danh nào.

### 6.5. Trả thuật toán đã lưu trong client registration response

Client configuration/read response nên thể hiện lại `id_token_signed_response_alg` đang áp dụng. Spring Authorization Server cung cấp `setClientRegistrationConverter(...)` để tùy chỉnh chuyển đổi từ `RegisteredClient` sang `OidcClientRegistration`.

Nếu dùng custom converter cho cả request và response:

- Đọc thuật toán từ `registeredClient.getTokenSettings().getIdTokenSignatureAlgorithm()`.
- Trả nó qua `OidcClientRegistration.Builder.idTokenSignedResponseAlgorithm(...)`.
- Không trả thuật toán client yêu cầu ban đầu nếu server đã từ chối hoặc áp dụng chính sách khác.
- Kiểm thử round-trip: đăng ký → lưu → đọc lại → thuật toán không đổi.

## 7. Discovery metadata và tập thuật toán OP hỗ trợ

### 7.1. `id_token_signing_alg_values_supported`

OpenID Provider Configuration có trường:

~~~json
{
  "issuer": "https://auth.example.com",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": [
    "RS256",
    "ES256"
  ]
}
~~~

Đây là danh sách **toàn cục** các JWS algorithms OP hỗ trợ cho ID Token, không phải thuật toán riêng của một client. Mọi thuật toán được cấu hình cho RegisteredClient phải thuộc danh sách OP công bố và có key/encoder thực sự hỗ trợ.

### 7.2. Cấu hình provider metadata

Spring Authorization Server cung cấp `OidcProviderConfiguration.Builder.idTokenSigningAlgorithms(...)`:

~~~java
private Consumer<OidcProviderConfiguration.Builder>
        oidcProviderMetadataCustomizer() {

    return builder -> builder.idTokenSigningAlgorithms(algorithms -> {
        algorithms.clear();
        algorithms.add("RS256");
        algorithms.add("ES256");
    });
}
~~~

Customizer này chỉ nên quảng bá những thuật toán mà server có thể ký ở thời điểm hiện tại. Nếu khóa ES256 đang bị disable hoặc encoder không còn key tương thích, hãy gỡ ES256 khỏi danh sách và xử lý các client đang cấu hình ES256 theo kế hoạch tương thích.

### 7.3. Quan hệ giữa ba lớp chính sách

~~~mermaid
flowchart TD
    A["OIDC Discovery: tập alg OP hỗ trợ"] --> B["Allow-list registration"]
    B --> C["id_token_signed_response_alg của client"]
    C --> D["RegisteredClient TokenSettings"]
    D --> E["JwtGenerator"]
    E --> F["JWKSource / JwtEncoder"]
    F --> G["ID Token có alg và kid tương ứng"]
~~~

Discovery nói OP hỗ trợ những gì; registration chọn một thuật toán trong tập đó cho client; TokenSettings lưu quyết định; JwtGenerator và JWKSource thực thi việc ký. Nếu một lớp không nhất quán, lỗi có thể chỉ xuất hiện khi client thực hiện Authorization Code Flow.

## 8. Chọn thuật toán và xây allow-list

### 8.1. RSA RS256

RS256 sử dụng RSA với SHA-256. Đây là lựa chọn tương thích rộng trong hệ sinh thái OIDC. Với RSA key, nên dùng kích thước tối thiểu 2048 bit theo baseline hiện hành và quản lý private key an toàn.

Ưu điểm:

- Tương thích tốt với nhiều OIDC client và thư viện JWT.
- Public key dễ phân phối qua JWKS.
- Phù hợp khi hạ tầng đã có RSA signing key và HSM/KMS hỗ trợ.

Nhược điểm:

- Signature và public key thường lớn hơn EC.
- Cần quản lý key size và hiệu năng phù hợp tải.

### 8.2. ECDSA ES256

ES256 dùng ECDSA với curve P-256 và SHA-256. Signature ngắn hơn RSA tương đương, nhưng cần client và crypto provider hỗ trợ đúng curve.

Ưu điểm:

- Signature nhỏ, tiết kiệm băng thông.
- Phù hợp môi trường có hỗ trợ EC tốt.

Nhược điểm:

- Cần bảo đảm tương thích P-256 ở toàn bộ client, HSM và encoder.
- Không được nhầm curve P-256 với P-384 hoặc P-521.

### 8.3. RSA-PSS

PS256, PS384 và PS512 dùng RSA-PSS. Chúng có thể là lựa chọn tốt khi toàn bộ hệ sinh thái hỗ trợ. Kiểm thử cả JWS provider, Nimbus encoder, JWK metadata và OIDC client trước khi bật.

### 8.4. Thuật toán không nên bật tùy tiện

- Không quảng bá thuật toán chỉ vì enum/thư viện có tên đó.
- Không dùng `none` cho ID Token production.
- Không hạ cấp thuật toán khi encoder không tìm được key.
- Không cho client chọn thuật toán ngoài allow-list.
- Không dùng một thuật toán đối xứng/shared secret nếu mô hình phân phối key khiến nhiều bên có thể giả mạo ID Token.
- Không nhầm thuật toán mã hóa JWE với thuật toán ký JWS.

Trong Spring Authorization Server 1.5.x, API `TokenSettings.idTokenSignatureAlgorithm(...)` nhận `SignatureAlgorithm`. Nếu cần thuật toán ngoài tập API hoặc cần JWE, phải thiết kế encoder/generator riêng và kiểm thử toàn bộ OIDC interoperability; không ép kiểu chuỗi để vượt qua giới hạn của API.

## 9. Kiểm soát an toàn trong JwtEncoder và JWKSource

### 9.1. Không để header do request điều khiển

Client có thể gửi `id_token_signed_response_alg` khi đăng ký hoặc cập nhật registration. Sau khi được xác thực và phê duyệt, giá trị đó được lưu trong RegisteredClient. Không lấy `alg` từ query parameter của authorization request hoặc header do client tự gửi ở mỗi lần cấp token.

### 9.2. Không tự động fallback khi key không tương thích

Giả sử client yêu cầu ES256 nhưng JWKSource chỉ có RSA private key. Server phải báo lỗi cấu hình/issuance và tạo alert; không tự ký RS256 rồi trả token như thể đã đáp ứng registration. Fallback âm thầm phá hợp đồng client và có thể tạo lỗ hổng downgrade.

### 9.3. Quản lý private key

- Private key nằm trong keystore bảo vệ, KMS hoặc HSM.
- Runtime chỉ có quyền ký cần thiết.
- Public JWKS chỉ chứa public key.
- Không log JWK private, PEM, raw ID Token hoặc client secret.
- Mỗi key có `kid` duy nhất và được quản lý vòng đời.
- Có quy trình rotation, pre-publish và retirement.

### 9.4. Không nhầm chữ ký của ID Token với chữ ký client assertion

Client dùng `private_key_jwt` ký assertion bằng private key của **client**. OP dùng private key của **server** để ký ID Token. Hai key có thể thuộc hai trust domain hoàn toàn khác nhau. Không dùng client JWKS URI làm nguồn private key của OP hoặc ngược lại.

## 10. Thay đổi thuật toán và vòng đời key

### 10.1. Thay đổi thuật toán cho một client

Ví dụ chuyển `customer-portal` từ RS256 sang ES256:

1. Xác nhận client hỗ trợ ES256.
2. Kiểm tra OP discovery metadata công bố ES256.
3. Tạo/đưa EC P-256 signing key vào key manager và JWKS.
4. Cập nhật `RegisteredClient.tokenSettings` theo quy trình quản trị.
5. Cấp một ID Token mới và kiểm tra `alg=ES256`, `kid` đúng.
6. Kiểm tra client xác minh ID Token thành công.
7. Theo dõi lỗi xác minh và có rollback plan.

ID Token đã phát hành bằng RS256 vẫn cần public RSA key cũ để xác minh đến khi hết thời hạn hoặc theo policy thu hồi. Không xóa public key cũ chỉ vì client đã đổi thuật toán.

### 10.2. Rotation key cùng thuật toán

Không nhất thiết đổi thuật toán khi chỉ cần rotation. Ví dụ thay RSA key K1 bằng RSA key K2:

- Công bố public K2 trước khi bắt đầu ký bằng K2.
- Chuyển signer sang private K2.
- JWT mới có `kid=K2`, `alg=RS256`.
- Giữ public K1 trong JWKS đến khi ID Token ký bằng K1 không còn cần xác minh.
- Sau đó mới gỡ K1 theo chính sách.

### 10.3. Thu hồi khẩn cấp

Nếu private key bị compromise, cần ngừng ký bằng key đó, thay key, gỡ public key khỏi trust source và đánh giá token bị ảnh hưởng. Với OIDC client cache JWKS, xóa public key khỏi endpoint không bảo đảm mọi client ngừng tin key ngay lập tức. Cần phối hợp cache refresh, client policy và incident response.

### 10.4. Thuật toán ngừng hỗ trợ

Khi OP bỏ một thuật toán khỏi discovery:

- Ngừng nhận registration mới yêu cầu thuật toán đó.
- Xác định client hiện tại đang dùng thuật toán cũ.
- Thông báo và di chuyển client theo thời gian biểu.
- Không bỏ key khỏi JWKS trước khi token cũ hết hạn, trừ sự cố compromise.
- Giữ test tương thích cho client chưa chuyển đổi.

## 11. Kiểm thử chính sách thuật toán

### 11.1. Unit test RegisteredClient settings

~~~java
@Test
void customerPortalUsesRs256ForIdToken() {
    assertThat(customerPortal.getTokenSettings()
        .getIdTokenSignatureAlgorithm())
        .isEqualTo(SignatureAlgorithm.RS256);
}

@Test
void mobileAppUsesEs256ForIdToken() {
    assertThat(mobileApp.getTokenSettings()
        .getIdTokenSignatureAlgorithm())
        .isEqualTo(SignatureAlgorithm.ES256);
}
~~~

Các biến `customerPortal` và `mobileApp` là RegisteredClient được tạo trong fixture test. Test này chỉ xác minh cấu hình đã lưu; vẫn cần test ID Token thực tế.

### 11.2. Integration test ID Token header

Sau khi thực hiện Authorization Code Flow trong test, decode protected header của ID Token để xác nhận:

~~~json
{
  "alg": "ES256",
  "kid": "op-ec-2026-01",
  "typ": "JWT"
}
~~~

Không chỉ Base64URL decode rồi kết luận token hợp lệ. Dùng public JWK tương ứng để xác minh chữ ký, sau đó kiểm tra issuer, audience, expiry, nonce và các OIDC claims bắt buộc.

### 11.3. Ma trận kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| RegisteredClient cấu hình RS256 | ID Token header có `alg=RS256`. |
| RegisteredClient cấu hình ES256 | ID Token header có `alg=ES256`. |
| TokenSettings không cấu hình thuật toán | Dùng default RS256 theo TokenSettings. |
| Client yêu cầu thuật toán không trong allow-list | Registration bị từ chối bằng `invalid_client_metadata`. |
| Client yêu cầu ES256 nhưng không có EC key phù hợp | Không fallback; issuance thất bại an toàn và có log/alert. |
| JWK có `kid` trùng key khác | Deployment/configuration validation thất bại. |
| JWKS không có public key tương ứng `kid` | Client verification thất bại; test phát hiện mismatch. |
| ID Token có chữ ký bị sửa | Client verification thất bại. |
| Client A RS256, client B ES256 | Hai client nhận đúng thuật toán riêng. |
| Access token JWT cùng authorization | Thuật toán access token vẫn theo policy riêng, không bị ID Token setting ghi đè. |
| `token_endpoint_auth_signing_alg` khác ID Token alg | Client assertion và ID Token dùng đúng thuật toán độc lập. |
| Discovery thiếu thuật toán đang dùng | Contract test thất bại. |
| Discovery quảng bá thuật toán không có key/encoder | Contract test thất bại. |
| Dynamic registration yêu cầu `none` | Bị từ chối theo allow-list. |
| Client registration response đọc lại | `id_token_signed_response_alg` khớp TokenSettings đã lưu. |
| Key rotation cùng thuật toán | Header `kid` chuyển sang key mới; public key cũ còn trong JWKS theo thời hạn. |
| Token cũ sau rotation | Vẫn xác minh được trong thời gian key cũ còn được tin cậy. |

### 11.4. Test bằng OIDC client thật

Chọn một OIDC client library đang dùng trong production:

1. Đăng ký client với RS256.
2. Hoàn tất Authorization Code + PKCE.
3. Xác minh ID Token qua discovery/JWKS.
4. Đăng ký client khác với ES256 và lặp lại.
5. Thử gửi thuật toán không được OP hỗ trợ.
6. Kiểm tra client từ chối ID Token ký bằng key không tin cậy hoặc thuật toán ngoài allow-list.

Interoperability test bắt được lỗi mà unit test builder không thể phát hiện, như curve mismatch, JWK `kid`, key cache và thuật toán client library không hỗ trợ.

## 12. Lỗi thường gặp và cách xử lý

### Lỗi 1: Đặt thuật toán ID Token trong ClientSettings

**Triệu chứng:** Cấu hình `tokenEndpointAuthenticationSigningAlgorithm` thay đổi nhưng ID Token vẫn ký RS256.

**Nguyên nhân:** Nhầm thuật toán client assertion với thuật toán OP ký ID Token.

**Cách xử lý:** Dùng `TokenSettings.idTokenSignatureAlgorithm(...)`.

### Lỗi 2: Chỉ sửa discovery metadata

**Triệu chứng:** OP quảng bá ES256 nhưng ID Token vẫn ký RS256 hoặc không ký được.

**Nguyên nhân:** Chỉ sửa `id_token_signing_alg_values_supported`, chưa cấu hình RegisteredClient, encoder hoặc key.

**Cách xử lý:** Đồng bộ metadata, TokenSettings, JWKSource và integration test.

### Lỗi 3: Có EC key nhưng JWK metadata sai

**Triệu chứng:** JwtEncoder không tìm thấy key cho ES256.

**Nguyên nhân:** Curve không đúng, `kty`/`alg`/`use` sai hoặc key không có private material để ký.

**Cách xử lý:** Kiểm tra EC P-256, public/private pair, JWK selector và `kid`.

### Lỗi 4: Client yêu cầu thuật toán không hỗ trợ

**Triệu chứng:** Token issuance lỗi sau khi registration thành công.

**Nguyên nhân:** Không validate `id_token_signed_response_alg` tại thời điểm đăng ký.

**Cách xử lý:** Validate allow-list và key support trước khi lưu RegisteredClient.

### Lỗi 5: Thay header alg bằng customizer

**Triệu chứng:** Header báo ES256 nhưng signature được tạo bằng RSA key hoặc encoder báo lỗi.

**Nguyên nhân:** Customizer ghi đè `alg` ngoài TokenSettings/key selection.

**Cách xử lý:** Dùng chính sách per-client mặc định của JwtGenerator; nếu custom encoder thì kiểm thử selector/header/key đồng nhất.

### Lỗi 6: Dùng chung một thuật toán cho mọi client vì tiện

**Triệu chứng:** Client có khả năng khác nhau không thể đăng ký hoặc bị cấp token không tương thích.

**Nguyên nhân:** Cấu hình algorithm ở mức global thay vì RegisteredClient.

**Cách xử lý:** Lưu `idTokenSignatureAlgorithm` trong TokenSettings của từng client và giữ allow-list toàn cục.

### Lỗi 7: Bỏ public key cũ ngay sau rotation

**Triệu chứng:** OIDC client từ chối ID Token còn hạn ký bằng key trước.

**Nguyên nhân:** Xóa key khỏi JWKS quá sớm.

**Cách xử lý:** Giữ public key cũ trong thời gian tương thích; xử lý riêng trường hợp key compromise.

### Lỗi 8: Đổi thuật toán nhưng không kiểm tra client thật

**Triệu chứng:** Unit test pass nhưng mobile/web client không xác minh được ID Token.

**Nguyên nhân:** Client library hoặc platform không hỗ trợ thuật toán/curve đã chọn.

**Cách xử lý:** Kiểm thử interoperability trên các client thực tế trước khi rollout.

## 13. Checklist production

| Hạng mục | Điều kiện cần xác nhận |
| --- | --- |
| Client policy | Mỗi RegisteredClient có thuật toán ID Token được phê duyệt? |
| Default | Client không khai báo thuật toán có default rõ ràng (RS256)? |
| Allow-list | Registration chỉ chấp nhận thuật toán OP thực sự hỗ trợ? |
| Discovery | `id_token_signing_alg_values_supported` khớp encoder và key inventory? |
| Key type | RSA/EC curve khớp thuật toán? |
| JWK metadata | `alg`, `use`, `kid` và public parameters chính xác? |
| Private key | Được bảo vệ trong keystore/KMS/HSM và không bị xuất ra JWKS? |
| JwtGenerator | Không có customizer ghi đè `alg` ngoài chính sách? |
| Dynamic registration | `id_token_signed_response_alg` được validate, lưu và trả lại đúng? |
| Client assertion | `token_endpoint_auth_signing_alg` được quản lý độc lập? |
| Key rotation | Có pre-publish, overlap, retire và emergency revocation? |
| Client compatibility | Các OIDC client thật đã xác minh token theo thuật toán? |
| Observability | Có metric/log cho alg, kid, signing failure và client ID mà không log raw token? |
| Persistence | TokenSettings được lưu bền vững và đồng bộ trên mọi Authorization Server node? |
| Testing | Có unit, integration, DCR, JWKS, rotation và interoperability tests? |

## 14. Bài tập thực hành

Một OP phục vụ ba client:

- `web-portal`: chỉ hỗ trợ RS256.
- `mobile-app`: hỗ trợ ES256.
- `partner-rp`: yêu cầu PS256 và đăng ký qua OIDC Dynamic Client Registration.

OP có RSA key K1 và EC P-256 key K2 trong JWKSource; chưa có RSA-PSS key policy được kiểm chứng.

1. Cấu hình `TokenSettings` cho web-portal dùng RS256 và mobile-app dùng ES256.
2. Quyết định có chấp nhận PS256 cho partner-rp hay không; giải thích dựa trên key, encoder và client compatibility.
3. Viết allow-list thuật toán và từ chối registration ngoài allow-list.
4. Ánh xạ `id_token_signed_response_alg` vào RegisteredClient TokenSettings.
5. Xác nhận registration response trả lại đúng thuật toán đã lưu.
6. Cấu hình discovery metadata chỉ quảng bá thuật toán OP thực sự hỗ trợ.
7. Cấp ID Token cho hai client và kiểm tra header `alg`, `kid`, chữ ký bằng public JWK.
8. Chứng minh `token_endpoint_auth_signing_alg` không ảnh hưởng ID Token.
9. Thực hiện rotation RSA K1 → K3 cùng thuật toán RS256 và kiểm tra token cũ.
10. Viết test để chứng minh OP không tự fallback từ ES256 sang RS256 khi thiếu EC key.

**Tiêu chí đạt:** Mỗi OIDC client nhận ID Token được ký bằng thuật toán đã đăng ký, thuật toán đó nằm trong allow-list của OP, public JWK tương ứng có thể xác minh chữ ký và server không âm thầm downgrade khi thiếu khóa.

## 15. Tài liệu đối chiếu

- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, JWS signing và xác minh token.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): client metadata `id_token_signed_response_alg` và registration semantics.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): `id_token_signing_alg_values_supported`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header, thuật toán và chữ ký JWS.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWK Set và key metadata.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): RSA, ECDSA, RSA-PSS và thuật toán JOSE.
- [Spring Authorization Server — TokenSettings.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html): `idTokenSignatureAlgorithm(SignatureAlgorithm)`.
- [Spring Authorization Server — TokenSettings Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): thuật toán mặc định và getter.
- [Spring Authorization Server — JwtGenerator Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/JwtGenerator.html): sinh JWT cho OAuth access token và OIDC ID Token.
- [Spring Authorization Server — OidcClientRegistration.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcClientRegistration.Builder.html): `idTokenSignedResponseAlgorithm(...)`.
- [Spring Authorization Server — OidcClientRegistrationAuthenticationProvider Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationProvider.html): converter cho dynamic registration.
- [Spring Authorization Server — OidcProviderConfiguration.Builder Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/OidcProviderConfiguration.Builder.html): danh sách thuật toán OP công bố.
- [Spring Authorization Server — Dynamic Client Registration Guide](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): bật endpoint và tùy chỉnh converter/provider.
