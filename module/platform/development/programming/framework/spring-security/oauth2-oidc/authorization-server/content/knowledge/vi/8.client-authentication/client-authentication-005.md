# private_key_jwt và phân phối khóa công khai của client

> **Chương: Xác thực client.** Bài học thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, tập trung vào thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server với Spring Security và Spring Authorization Server trong Spring Boot. Nội dung này giải thích cách một **confidential client** chứng minh danh tính bằng JWT ký bằng **private key** của chính client, cách Authorization Server tra cứu **public key** đã đăng ký để kiểm chứng, và cách quản lý khóa qua các môi trường.

## 1. Bài toán: không dùng một shared client secret khi xác thực client

Trong `client_secret_basic`, confidential client chứng minh danh tính bằng `client_id` và một **bí mật chia sẻ** với Authorization Server. Với **`private_key_jwt`**, client tự ký một **client assertion JWT** có thời hạn ngắn bằng private key của nó, rồi gửi JWT tới token endpoint. Authorization Server lấy **public key đáng tin cậy của đúng client** để kiểm tra chữ ký và các claim; server **không cần giữ private key** và không cần biết một shared client secret để xác thực client này.

Ví dụ xuyên suốt:

- **Authorization Server (AS):** `https://login.example.vn`, issuer cố định `https://login.example.vn`, token endpoint `https://login.example.vn/oauth2/token`.
- **Confidential client:** dịch vụ `reporting-service`, dùng `grant_type=client_credentials` để xin scope `reports.read`.
- **Public JWKS của client:** `https://keys.example.vn/clients/reporting-service/jwks.json`.
- **Client private key:** nằm ở secret store/keystore/HSM/KMS mà chỉ workload `reporting-service` được phép ký.
- **Resource Server:** `https://reports-api.example.vn`, nhận **access token do AS cấp**, xác minh quyền truy cập API.

| Phương thức xác thực client | Client giữ | Authorization Server sử dụng | Khi nào đáng cân nhắc |
|---|---|---|---|
| `client_secret_basic` | Shared secret | Hash secret trong `RegisteredClient` | Confidential client đơn giản, có kênh phân phối và rotation secret |
| `client_secret_jwt` | Shared secret dùng làm khóa MAC | Secret tương ứng để kiểm tra HMAC | Hệ thống đã hỗ trợ JWT client assertion nhưng vẫn dùng shared secret |
| **`private_key_jwt`** | **Private key** để ký JWT assertion | **Public key** được đăng ký qua JWKS/nguồn đáng tin | Confidential service muốn tách quyền ký và quyền xác minh, dùng hạ tầng quản lý khóa |
| `tls_client_auth` / `self_signed_tls_client_auth` | Private key của client certificate | Chứng chỉ/chuỗi tin cậy hoặc public certificate đăng ký | Hạ tầng TLS/mTLS và policy chứng chỉ phù hợp |
| `none` | Không có credential bí mật bảo vệ được | Không coi client là confidential | Public client (SPA/native) với Authorization Code + PKCE |

**Hai ý cần tách biệt:** `private_key_jwt` là **cơ chế xác thực client**, không phải OAuth grant type. Client vẫn phải gửi `grant_type=client_credentials` hoặc `authorization_code` phù hợp `RegisteredClient`. JWT client assertion cũng **không phải access token** để gọi API, và không phải ID Token của OIDC.

## 2. Đường đi của khóa và thông điệp xác thực

~~~mermaid
sequenceDiagram
    autonumber
    participant KeyMgr as Secret store / HSM
    participant Client as reporting-service (OAuth Client)
    participant JWKS as HTTPS Client JWKS Endpoint
    participant AS as Spring Authorization Server
    participant API as Resource Server

    KeyMgr->>Client: Cấp quyền ký bằng private key của client
    Client->>Client: Tạo JWT: iss=sub=client_id, aud=AS issuer,<br/>exp, iat, jti, header kid và typ
    Client->>KeyMgr: Ký JWS (nếu khóa trong KMS/HSM)
    KeyMgr-->>Client: Chữ ký JWS
    Client->>AS: POST /oauth2/token<br/>grant_type=client_credentials + client_assertion
    AS->>AS: Tìm RegisteredClient bằng client_id
    AS->>AS: Kiểm tra phương thức private_key_jwt đã đăng ký
    AS->>JWKS: GET jwkSetUrl khi cần tải/cập nhật key
    JWKS-->>AS: Public JWK Set theo policy đã đăng ký
    AS->>AS: Kiểm tra JWS, kid, alg, iss, sub,<br/>aud, exp/nbf và policy bổ sung
    AS-->>Client: Access token nếu client và grant/scope hợp lệ
    Client->>API: Authorization: Bearer ACCESS_TOKEN
    API->>API: Xác minh access token do AS phát hành
    API-->>Client: Trả tài nguyên theo scope/quyền
~~~

Thông thường thao tác ký có thể thực hiện tại tiến trình client với private key được nạp từ keystore; nếu dùng HSM/KMS thì private key **không rời khỏi** thiết bị/dịch vụ ký, client chỉ nhận chữ ký. Việc tải JWKS của client phụ thuộc cơ chế cache của Authorization Server, không nhất thiết xảy ra trong **mọi** lần đổi token.

### 2.1. Ai sở hữu khóa nào?

| Khóa/endpoint | Chủ sở hữu | Ai được đọc? | Dùng vào việc gì? |
|---|---|---|---|
| **Private key của `reporting-service`** | Client | Chỉ workload/thiết bị ký được cấp quyền | Ký `client_assertion` cho `private_key_jwt` |
| **Public JWK của `reporting-service`** | Client | AS và các bên được phép lấy public JWKS | Xác minh rằng assertion do client tương ứng ký |
| **Private signing key của Authorization Server** | AS | Chỉ dịch vụ cấp token/thiết bị ký được phép | Ký access token JWT hoặc ID Token |
| **Public JWKS của Authorization Server** (`/oauth2/jwks`) | AS | Client/Resource Server cần kiểm tra token | Xác minh chữ ký JWT **do AS phát hành** |

Hai bộ khóa có thể cùng dùng RSA/EC nhưng **không được nhầm lẫn**. `ClientSettings.jwkSetUrl` trỏ đến **public JWKS của client**. `AuthorizationServerSettings.jwkSetEndpoint` hoặc metadata `jwks_uri` của AS nói tới **public JWKS của Authorization Server**. Chúng phục vụ hai chiều kiểm chứng khác nhau.

## 3. JWT client assertion có những trường gì?

Client assertion là một **signed JWT (JWS compact serialization)** được gửi trong form body của token request. Ví dụ header:

~~~json
{
  "alg": "RS256",
  "kid": "reporting-2026-11",
  "typ": "client-authentication+jwt"
}
~~~

Payload minh họa (**không phải JWT đã ký**, các timestamp chỉ là ví dụ cấu trúc):

~~~json
{
  "iss": "reporting-service",
  "sub": "reporting-service",
  "aud": "https://login.example.vn",
  "iat": 1794790000,
  "exp": 1794790060,
  "jti": "d1a3c403-188a-4833-98a8-989598fbb204"
}
~~~

| Trường | Quy tắc cần hiểu |
|---|---|
| `iss` (JWT issuer) | Trong profile xác thực client, **client tự khai danh tính**, thường bằng chính `client_id`; **không** phải issuer của AS |
| `sub` | Phải là `client_id` của client đang xác thực; ví dụ `reporting-service` |
| `aud` | **Issuer identifier của Authorization Server**, đúng một giá trị `https://login.example.vn`, theo **RFC 10070** cập nhật RFC 7523 |
| `exp` | Thời điểm JWT hết hiệu lực; nên đặt vòng đời rất ngắn, ví dụ 60 giây theo policy nội bộ |
| `iat` | Thời điểm phát hành; có thể hỗ trợ kiểm tra độ mới và sai lệch đồng hồ |
| `nbf` | Nếu có, không chấp nhận assertion trước thời điểm này |
| `jti` | Định danh duy nhất cho assertion, hữu ích để chống phát lại (replay) khi AS lưu lịch sử đã sử dụng |
| `alg` | Thuật toán ký JWS đã được policy/registration cho phép; ví dụ `RS256`, **không** cho `none` hoặc thuật toán bị ép từ input không tin cậy |
| `kid` | Chỉ ra **khóa public** cần chọn trong JWKS của chính client; key ID phải nhất quán khi rotation |
| `typ` | RFC 10070 **khuyến nghị** `client-authentication+jwt` để phân biệt kiểu JWT; kiểm tra tương thích với thư viện triển khai |

### 3.1. Thay đổi quan trọng của RFC 10070 (tháng 11/2026)

**RFC 7523 bản đầu** cho phép dùng URL token endpoint làm một giá trị audience của JWT assertion. Tuy nhiên, **RFC 10070 (11/2026)** đã cập nhật quy tắc này để ngăn dạng tấn công lợi dụng nhầm lẫn audience:

- Đối với JWT dùng **xác thực client**, `aud` **MUST chỉ chứa issuer identifier của AS** theo RFC 8414; **không** được dùng URL token endpoint làm audience, kể cả token request đang gửi tới endpoint đó.
- AS phải từ chối JWT assertion mà audience không khớp **chính xác một issuer** của mình. Không chấp nhận một mảng audience chứa cả issuer và URL khác.
- RFC khuyến nghị `typ: client-authentication+jwt`, nhưng **không khuyến nghị từ chối chỉ vì thiếu `typ`** để giữ tương thích với client cũ vốn đã dùng audience an toàn.
- **`iss` của assertion vẫn là client ID**; **`aud` mới là issuer của AS**. Đừng nhầm hai chữ `issuer` vì chúng nói tới hai chủ thể khác nhau.

**Ví dụ đúng:**

~~~text
AS issuer:      https://login.example.vn
AS token URL:   https://login.example.vn/oauth2/token
assertion iss:  reporting-service
assertion sub:  reporting-service
assertion aud:  https://login.example.vn
~~~

Ví dụ sai theo quy tắc cập nhật: `"aud": "https://login.example.vn/oauth2/token"` hoặc `"aud": ["https://login.example.vn", "https://other.example.vn"]`.

**Lưu ý tương thích:** Một số phiên bản thư viện/cấu hình AS cũ có thể còn xác thực audience theo hành vi trước RFC 10070. Việc upgrade hoặc tùy biến validator để buộc audience **đúng một issuer** cần được kiểm thử với phiên bản Spring Security/Spring Authorization Server thực tế. Không tự kết luận framework đã áp dụng quy tắc mới chỉ vì request có JWT hợp lệ.

### 3.2. `jti` và replay protection có tự hoạt động không?

RFC 7523 xem việc kiểm tra `jti` đã dùng là một biện pháp **có thể áp dụng**, nhưng không bảo đảm thư viện mặc định đang lưu mọi `jti` để chống replay. Nếu yêu cầu chống replay, AS nên lưu khóa như `(client_id, jti)` với TTL đến ít nhất hết `exp` cộng mức skew theo policy, sử dụng thao tác ghi nguyên tử ở storage chia sẻ giữa các pod. Assertion đã sử dụng lại phải bị từ chối.

Không đánh đồng `jti` duy nhất với cơ chế chống replay: nếu server **không kiểm tra lịch sử dùng**, attacker có assertion bị đánh cắp trong thời gian sống có thể phát lại. Dùng HTTPS, TTL ngắn và kiểm soát log vẫn cần thiết.

## 4. Cấu hình `RegisteredClient` với `PRIVATE_KEY_JWT`

Spring Authorization Server hỗ trợ `private_key_jwt` thông qua cơ chế client authentication mặc định. Với Spring Authorization Server 1.5.x, đăng ký client bằng builder như sau:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

@Configuration(proxyBeanMethods = false)
class ClientRegistrationConfig {

    @Bean
    RegisteredClientRepository registeredClientRepository() {
        RegisteredClient reporting = RegisteredClient
                .withId("registration-reporting-service")
                .clientId("reporting-service")
                .clientName("Reporting service")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.PRIVATE_KEY_JWT)
                .authorizationGrantType(
                        AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("reports.read")
                .clientSettings(ClientSettings.builder()
                        .jwkSetUrl(
                          "https://keys.example.vn/clients/reporting-service/jwks.json")
                        .tokenEndpointAuthenticationSigningAlgorithm(
                                SignatureAlgorithm.RS256)
                        .build())
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .build())
                .build();

        return new InMemoryRegisteredClientRepository(reporting);
    }
}
~~~

**Diễn giải:**

1. `clientAuthenticationMethod(PRIVATE_KEY_JWT)` cho phép xác thực client bằng một JWT assertion **ký bất đối xứng**, không phải HTTP Basic.
2. Không thiết lập `clientSecret(...)`: server chỉ cần public key đáng tin và client chứng minh mình giữ private key. Không thêm một secret giả để làm vừa lòng builder.
3. `ClientSettings.jwkSetUrl(...)` trỏ đến **HTTPS JWKS của client**; server dùng nguồn khóa theo registration để xác minh chữ ký.
4. `tokenEndpointAuthenticationSigningAlgorithm(SignatureAlgorithm.RS256)` giới hạn thuật toán chấp nhận phù hợp với private/public key. Không chấp nhận thuật toán do assertion tự chọn ngoài policy.
5. `authorizationGrantType(CLIENT_CREDENTIALS)` độc lập với phương thức xác thực. Client đăng ký `AUTHORIZATION_CODE` cũng có thể dùng `private_key_jwt` tại token endpoint khi đổi authorization code.
6. `InMemoryRegisteredClientRepository` chỉ để minh họa/local test. Production nên dùng repository bền vững, policy provisioning và validation URL/key; đồng thời đảm bảo các instance AS đọc cùng bản đăng ký.

**Điều kiện chạy đầy đủ:** Ứng dụng Spring Boot vẫn cần bean/filter chain cấu hình Authorization Server, `AuthorizationServerSettings` có issuer public ổn định, cách tạo access token, các service lưu authorization/consent phù hợp và private signing key **của AS** (nếu phát JWT). Đoạn mã này chỉ đăng ký một client.

### 4.1. Bật client authentication trong SecurityFilterChain

Ở cấu hình Spring Authorization Server chuẩn, `OAuth2ClientAuthenticationFilter` hỗ trợ `private_key_jwt` theo mặc định thông qua `JwtClientAssertionAuthenticationConverter` và `JwtClientAssertionAuthenticationProvider`. Thường **không cần tự viết một filter xác minh JWT client assertion**.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
        .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                        new LoginUrlAuthenticationEntryPoint("/login"),
                        new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://login.example.vn")
            .build();
}
~~~

Đây là khung cấu hình **phía Authorization Server** (các imports lấy từ Spring Security/Spring Authorization Server tương ứng). `/oauth2/token` yêu cầu client authentication theo grant/policy; khi nhận assertion, provider lấy `RegisteredClient` và cấu hình key để kiểm chứng. Nếu hệ thống bật OIDC, bổ sung OIDC configurer phù hợp; **`private_key_jwt` không đòi hỏi phải bật OIDC** vì đây là cách client xác thực ở token endpoint OAuth 2.0.

Để siết các claim theo RFC 10070 hoặc chính sách `jti`, có thể tùy biến `JwtClientAssertionDecoderFactory` và cung cấp validator cho `JwtClientAssertionAuthenticationProvider` qua `OAuth2ClientAuthenticationConfigurer.authenticationProviders(...)`. Khi làm vậy, phải **kết hợp** validator mới với `DEFAULT_JWT_VALIDATOR_FACTORY` để giữ các kiểm tra mặc định (`iss`, `sub`, `aud`, `exp`, `nbf`), đồng thời thêm rule audience chính xác và replay protection nếu cần. Việc thay hẳn default validator dễ vô tình bỏ sót xác thực quan trọng.

## 5. Phân phối public key của client qua JWKS

### 5.1. Một JWKS công khai đúng hình thức

**JSON Web Key Set (JWKS)** là một JSON object chứa mảng `keys`. Với RSA key dùng `RS256`, public JWK thường có:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "reporting-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_PUBLIC_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

Giá trị `n` phía trên là **placeholder**, không phải modulus hợp lệ và không thể sử dụng để xác minh token thực tế. Public JWKS phải được sinh từ **public key thật** tương ứng private key đang ký. Một JWKS cho nhiều client có thể làm khó phân quyền và rotation; ví dụ này đặt đường riêng cho `reporting-service`.

| Field | Ý nghĩa |
|---|---|
| `kty` | Loại khóa, ví dụ `RSA` hoặc `EC` |
| `kid` | Định danh giúp server chọn đúng public key theo JWT header |
| `use` | Mục đích `sig` (ký/xác minh) |
| `alg` | Thuật toán tương ứng, ví dụ `RS256`; server vẫn cần kiểm tra policy registration |
| `n`, `e` | RSA public modulus và public exponent mã hóa base64url |

**Không công bố thông số khóa riêng** như RSA `d`, `p`, `q`, `dp`, `dq`, `qi` hoặc khóa symmetric `k`. Public JWKS không cần bảo mật nội dung như private key, nhưng phải có **tính toàn vẹn và nguồn gốc đáng tin**: phục vụ qua HTTPS, hostname đăng ký được kiểm soát, policy xuất bản/rotation và giám sát certificate.

### 5.2. Sinh JSON public JWKS từ public key bằng Nimbus

Ví dụ phía **dịch vụ client hoặc bộ phận provisioning**, nơi đã có `RSAPublicKey` được đọc từ keystore/secret manager:

~~~java
import java.security.interfaces.RSAPublicKey;
import java.util.Map;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;

static Map<String, Object> publicJwks(RSAPublicKey publicKey) {
    RSAKey jwk = new RSAKey.Builder(publicKey)
            .keyID("reporting-2026-11")
            .keyUse(KeyUse.SIGNATURE)
            .algorithm(JWSAlgorithm.RS256)
            .build();

    // true: chỉ serialize các phần công khai của JWK
    return new JWKSet(jwk).toJSONObject(true);
}
~~~

Kết quả có thể được đưa lên một endpoint/static JSON được quản trị, ví dụ `https://keys.example.vn/clients/reporting-service/jwks.json`. Ví dụ này không tự tạo HTTP server và không đọc private key. Cần thiết lập TLS, response content type `application/json`, cache HTTP có thời gian phù hợp và quy trình cập nhật khi rotate khóa.

**Phân phối qua URL hay nhúng sẵn key?** Spring Authorization Server có cấu hình chuẩn `jwkSetUrl` để tải public JWKS; trong môi trường không thể cho server fetch URL, có thể cần một custom decoder/key resolver hoặc cơ chế đăng ký khác được thiết kế cẩn thận. Không gán một URL có thể chỉnh tùy ý trực tiếp từ HTTP request cho decoder.

### 5.3. Phòng tránh SSRF và key-substitution

Public JWKS là dữ liệu **được tải qua mạng**, nên URL lấy key là một phần của trust boundary:

- Chỉ cho admin/provisioning có thẩm quyền đăng ký hoặc thay `jwkSetUrl`. Kiểm tra HTTPS, hostname/dải domain cho phép, IP private/loopback/link-local, redirects, DNS và egress policy.
- Không tin header `jku`, `x5u` hoặc JWK tự nhúng trong **JWT chưa xác minh** để tự lấy một public key mới. Chọn key từ **nguồn đã đăng ký cho client**, kết hợp `kid` và thuật toán được cho phép.
- Không coi một key chỉ vì có cùng `kid` là đáng tin: `kid` chỉ là chỉ báo chọn trong tập key tin cậy; chữ ký phải được kiểm tra thật.
- Xử lý key không tìm thấy, JWKS không hợp lệ, timeout hay TLS fail theo nguyên tắc **không xác thực được thì từ chối**; không fallback sang xác thực không secret hoặc cho qua chữ ký.
- Theo dõi public JWKS cache để cập nhật khóa mới khi rotation; chi tiết refresh/cache phụ thuộc phiên bản thư viện và cấu hình HTTP client.

Nếu nhiều tenant dùng chung dịch vụ Authorization Server, tập key của một tenant/client **không được** dùng để xác minh assertion từ client khác. Trust phải bắt đầu từ bản đăng ký client có quyền truy cập.

## 6. Tạo client assertion bằng Java/Nimbus JOSE + JWT

Ở **phía client** `reporting-service`, công việc gồm: có một private key được bảo vệ, tạo claims, ký JWS bằng thuật toán được đăng ký và gửi JWT vào token endpoint qua HTTPS.

Phương thức Java minh họa tạo JWT assertion bằng RSA private key **được truyền từ lớp quản lý khóa**:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

static String newClientAssertion(
        RSAPrivateKey privateKey,
        String kid,
        String clientId,
        String authorizationServerIssuer) throws JOSEException {

    Instant now = Instant.now();

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(clientId)
            .subject(clientId)
            // RFC 10070: audience là một issuer identifier duy nhất.
            .audience(authorizationServerIssuer)
            .issueTime(Date.from(now))
            .expirationTime(Date.from(now.plus(Duration.ofSeconds(60))))
            .jwtID(UUID.randomUUID().toString())
            .build();

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
            .type(new JOSEObjectType("client-authentication+jwt"))
            .keyID(kid)
            .build();

    SignedJWT assertion = new SignedJWT(header, claims);
    assertion.sign(new RSASSASigner(privateKey));
    return assertion.serialize();
}
~~~

**Điểm giới hạn:** đoạn code chỉ tạo JWT, chưa thực hiện một HTTP token request và chưa mô tả cách nạp private key. Trong production, tải khóa theo quy trình quản lý secret, hạn chế quyền file/keystore, hoặc dùng KMS/HSM với signer phù hợp thay `RSASSASigner(privateKey)` để private key không bị xuất ra tiến trình. Với RSA, chọn kích thước key/thuật toán đáp ứng chính sách (ví dụ RSA tối thiểu 2048-bit khi dùng RS256 theo yêu cầu an toàn thực tế).

**Không tạo key pair mới trên mỗi token request.** Chữ ký phải dùng private key đã được đăng ký public key tương ứng, `kid` chính xác trong JWKS. Mỗi request nên tạo `iat`, `exp`, `jti` mới; không tái dùng một assertion đã hết hạn hoặc lộ trong log.

### 6.1. Gửi JWT tới token endpoint

Ví dụ HTTP sau dùng `grant_type=client_credentials`. `client_assertion` trong thực tế là chuỗi ba đoạn `base64url(header).base64url(payload).base64url(signature)`, toàn bộ trường form phải được **URL-encode**:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&scope=reports.read
&client_id=reporting-service
&client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer
&client_assertion=SIGNED_JWT_ASSERTION_URL_ENCODED
~~~

Các dòng body được xuống dòng để đọc, **không phải raw body đúng cú pháp**: khi gửi thật phải nối và form encode các cặp tham số. Không gửi `Authorization: Basic ...` chứa shared client secret cho đăng ký chỉ dùng `PRIVATE_KEY_JWT`. Một số thư viện OAuth2 Client không tự tạo `private_key_jwt` chỉ từ cấu hình `client-authentication-method`; cần xác nhận hoặc tự cấu hình cách tạo/ký assertion trong token client của phiên bản sử dụng.

AS thực hiện hai kiểm tra độc lập:

1. **Client authentication:** assertion có chữ ký/key/claims hợp lệ và phương thức này được phép cho `reporting-service`.
2. **Grant authorization:** client được dùng `client_credentials` và được phép xin `reports.read`; còn quyết định cấp token phụ thuộc policy của Authorization Server.

Nếu muốn dùng Authorization Code + PKCE, sau redirect hợp lệ client đổi `code` bằng token request có `grant_type=authorization_code`, `code`, `redirect_uri`, `code_verifier` và **cặp `client_assertion_type`/`client_assertion`**, vẫn xác thực theo private_key_jwt. PKCE, `state` và kiểm tra redirect URI vẫn bắt buộc theo thiết kế; private_key_jwt không thay thế chúng.

### 6.2. Phân biệt client assertion và JWT bearer authorization grant

| Thành phần request | **private_key_jwt client authentication** | **JWT bearer authorization grant** |
|---|---|---|
| Mục tiêu | Chứng minh danh tính client trước AS | Dùng JWT assertion làm **authorization grant** |
| Tham số JWT | `client_assertion` | `assertion` |
| Tham số loại | `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer` | `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer` |
| Grant type đi kèm | Ví dụ `client_credentials`, `authorization_code` | Chính JWT bearer grant |
| Cấu hình tiêu biểu trong Spring | `ClientAuthenticationMethod.PRIVATE_KEY_JWT` | Cần xác nhận hỗ trợ grant extension riêng; không tự suy ra từ PRIVATE_KEY_JWT |

Hai tính năng được bàn trong RFC 7523, nhưng cách sử dụng và chính sách **khác nhau**. Không gửi JWT client assertion vào tham số `assertion` rồi kỳ vọng server nhận là xác thực client.

## 7. AS kiểm tra assertion theo thứ tự nào?

Việc triển khai thư viện có thể tổ chức các bước nội bộ khác, nhưng kết quả phải đạt các điều kiện sau:

1. Xác định `client_id` được trình bày và **tra cứu `RegisteredClient`** trong repository đã tin cậy. Từ chối client không tồn tại hoặc không cho phép `PRIVATE_KEY_JWT`.
2. Lấy JWKS từ `ClientSettings.jwkSetUrl` của **chính client đó**, không từ một header/URL tùy ý do assertion yêu cầu.
3. Xác định thuật toán được chấp nhận từ registration và policy; kiểm tra `alg`, `kid`, kiểu key, chữ ký JWS bằng public key phù hợp.
4. Kiểm tra `iss` và `sub` đúng `client_id` theo profile xác thực client.
5. Kiểm tra `aud` **chỉ bằng** issuer của AS theo RFC 10070, so khớp chuỗi chính xác (bao gồm scheme/host/path/dấu slash).
6. Kiểm tra `exp`, `nbf`, có thể cả `iat`, mức clock skew phù hợp; từ chối assertion quá hạn hoặc có thời điểm bất thường.
7. Áp dụng chính sách replay `jti` nếu hệ thống yêu cầu; chỉ coi `jti` là chống replay khi server có xử lý lưu và đối chiếu thật.
8. Cuối cùng mới kiểm tra grant type, scope, authorization code/PKCE hoặc policy cấp token.

Cần đặc biệt thận trọng với **algorithm confusion**: không cho phép JWT tự thay `RS256` thành `HS256` rồi dùng public key bytes như shared secret; không cho `alg=none`. Nếu cấu hình mỗi client cho nhiều thuật toán, chỉ chấp nhận tập được quản trị và kiểm thử riêng.

**Có giới hạn ở JWT type header:** `typ: client-authentication+jwt` là tín hiệu có ích cho phân loại token. Quy tắc thực tế cần tương thích với version decoder; không được dựa riêng vào `typ` để tin một JWT không đúng audience/chữ ký.

## 8. Rotation khóa: đổi private key mà không ngắt cấp token

Sử dụng `kid` để lựa chọn khóa trong JWKS giúp client chuyển từ key cũ sang key mới theo kế hoạch.

~~~mermaid
sequenceDiagram
    autonumber
    participant Ops as Key operator
    participant JWKS as Client JWKS endpoint
    participant Client as reporting-service
    participant AS as Authorization Server

    Ops->>JWKS: Công bố public key cũ kid=v1 và mới kid=v2
    AS->>JWKS: Cập nhật/tải lại JWKS
    JWKS-->>AS: v1 + v2
    Ops->>Client: Cấp quyền ký bằng private key mới
    Client->>AS: Assertion ký key v2, header kid=v2
    AS->>AS: Xác minh bằng public v2; cấp token
    Note over Client,AS: Đảm bảo các instance client cũ đã chuyển đổi,<br/>assertion v1 hết hạn và cache phù hợp
    Ops->>JWKS: Gỡ public v1 sau khi có xác nhận an toàn
    Ops->>Client: Thu hồi/xóa private key v1
~~~

Trình tự vận hành:

1. Tạo key pair mới trong KMS/HSM hoặc keystore theo chuẩn, xác lập `kid` mới duy nhất.
2. **Công bố public JWK mới cùng public JWK cũ** trong client JWKS để AS có thể xác minh cả hai trong giai đoạn chuyển đổi.
3. Kiểm tra JWKS được fetch thành công từ mọi instance AS hoặc có cơ chế refresh cache khi cần.
4. Rollout client để ký assertion mới bằng `kid` mới; quan sát tỷ lệ xác thực thành công.
5. Chờ các assertion cũ hết hạn và kiểm tra mọi instance client đã ngừng dùng key cũ, cộng thời gian cache/clock skew liên quan.
6. Gỡ public key cũ khỏi JWKS và vô hiệu private key cũ theo runbook; ghi audit về phiên bản/owner/thời điểm.

**Nếu private key bị lộ:** ưu tiên thu hồi key khỏi nguồn tin cậy và thay thế khẩn cấp; đánh giá các access token đã cấp cho client bị ảnh hưởng (có thể cần cơ chế thu hồi riêng). Không chỉ chờ assertion ngắn hạn tự hết hiệu lực, vì kẻ tấn công giữ private key còn có thể tạo assertion **mới** liên tục trước khi key bị thu hồi.

### 8.1. Các tình huống dễ gây lỗi rotation

- Client đổi `kid=v2` nhưng JWKS vẫn chỉ có `v1` ⇒ AS không tìm được khóa xác minh.
- AS cache JWKS cũ chưa refresh ⇒ rollout mới có thể lỗi dù endpoint đã công bố key mới.
- Public JWK `v2` được xuất từ **nhầm key pair** ⇒ `kid` trùng nhưng chữ ký không hợp lệ.
- Key v1 bị gỡ trong khi còn instance client ký v1 ⇒ lỗi token endpoint ngắt quãng.
- Thay `jwkSetUrl` sang domain mới mà không kiểm tra TLS/egress/allowlist ⇒ AS không tải được JWKS hoặc tạo lỗ hổng SSRF.
- Hai client dùng chung private key ⇒ mất khả năng thu hồi/điều tra độc lập; mỗi client nên có cặp khóa và policy riêng.

## 9. Bảo mật private key và hệ thống phân phối public key

### 9.1. Khóa riêng phải được bảo vệ suốt vòng đời

- Sinh khóa bằng nguồn ngẫu nhiên mật mã đủ mạnh, kiểm tra kích thước/thuật toán theo chính sách và dùng khóa riêng cho từng client, từng môi trường.
- Cất private key trong secret store được kiểm soát, HSM/KMS hoặc keystore mã hóa; ưu tiên workload identity và quyền **chỉ ký** nếu nền tảng hỗ trợ.
- Không đưa private key, PEM, PKCS#12 password hoặc JWT assertion nguyên văn vào Git, Docker image, container args, `application.yml`, CI log, heap dump hoặc bug report.
- Khi bị lỗi ký, log chỉ nên chứa `client_id`, `kid`, loại lỗi, correlation ID và thời điểm; **không** log chữ ký, assertion đầy đủ hay key.
- Gắn giới hạn quyền đọc và thời hạn truy cập theo môi trường. Khi service được scale, đảm bảo các instance cùng client dùng các key được phép và JWKS công bố đủ.
- Audit hoạt động tạo key, cấp quyền ký, công bố public JWKS, thay URL đăng ký và thu hồi key.

### 9.2. Public không đồng nghĩa vô hại

Public key **được phép công khai**, nhưng khả năng **thay nội dung JWKS** phải được bảo vệ như thao tác thay cấu hình xác thực. Nếu một kẻ xấu sửa JWKS bằng public key của họ, họ có thể ký assertion giả và chứng minh danh tính client với AS đang tin vào JWKS đó.

Cần kiểm soát write access, deploy approvals, HTTPS/TLS, DNS, CDN/CDN cache, giới hạn HTTP redirects, ký/kiểm tra artifact khi phù hợp và giám sát thay đổi ngoài kế hoạch. Không cho người dùng tự đăng ký URL JWKS trỏ tới máy nội bộ hoặc dịch vụ metadata cloud.

## 10. Kiểm thử `private_key_jwt` và JWKS

### 10.1. Kiểm tra public JWKS mà không làm lộ private key

~~~bash
curl -fsS https://keys.example.vn/clients/reporting-service/jwks.json \
  | jq '{kids: [.keys[].kid], key_types: [.keys[].kty], public_only: (all(.keys[]; has("d") | not))}'
~~~

**Lưu ý về cú pháp kiểm tra:** câu `public_only` phía trên chỉ dò trường `d` của RSA; với kiểm tra an toàn thực tế, còn phải kiểm tra các thành phần private như `p`, `q`, `dp`, `dq`, `qi`, hoặc symmetric `k` theo `kty`. Trường `kid` được ghi nhận, nhưng phải kiểm tra cặp public/private tương ứng bằng một assertion thật để khẳng định key đúng.

Đảm bảo `curl` đang gọi **JWKS của client**, khác với:

~~~bash
curl -fsS https://login.example.vn/oauth2/jwks \
  | jq '{as_key_count: (.keys | length)}'
~~~

Đường thứ hai là **public JWKS của AS** dùng xác minh access token/ID Token do AS ký; nó không thay JWKS được cấu hình trong `RegisteredClient`.

### 10.2. Test matrix quan trọng

| Ca kiểm thử | Thay đổi đầu vào | Kết quả mong đợi |
|---|---|---|
| Thành công chuẩn | Assertion RS256 hợp lệ, `iss=sub=client_id`, `aud` đúng một issuer, thời hạn hợp lệ | Token endpoint chấp nhận client và tiếp tục kiểm tra grant/scope |
| Thiếu đăng ký | `client_id` không tồn tại | Từ chối, không cấp token |
| Sai authentication method | Client chỉ đăng ký `CLIENT_SECRET_BASIC` nhưng gửi assertion | Từ chối `invalid_client` hoặc lỗi thích hợp |
| Sai chữ ký | JWT bị sửa payload/chữ ký | Từ chối, không fallback sang key khác ngoài registry |
| Sai `kid` | Header `kid` chưa xuất bản trong JWKS client | Từ chối hoặc cơ chế refresh JWKS được kiểm soát, không chấp nhận token sai |
| Sai `alg` | Assertion dùng `HS256` hoặc `none` thay `RS256` đã đăng ký | Từ chối |
| Sai `iss` hoặc `sub` | Không bằng `client_id` được đăng ký | Từ chối |
| Sai `aud` | Chỉ dùng token endpoint URL thay issuer | Từ chối theo RFC 10070 |
| Sai `aud` nhiều giá trị | `aud` chứa issuer và một URL khác | Từ chối theo RFC 10070 |
| Hết hạn | `exp` trong quá khứ | Từ chối |
| Chưa đến hạn | `nbf` ở tương lai vượt clock skew | Từ chối |
| Replay assertion | Gửi lại cùng `jti`/assertion | Từ chối **nếu hệ thống đã bật replay protection**; phải test policy, không giả định mặc định |
| Không lấy được JWKS | TLS fail, timeout, key endpoint 404 | Không xác thực client; log/alert không tiết lộ credential |
| Key rotation | Công bố v1+v2, client chuyển sang v2 | AS xác minh v2; v1 còn được phép trong thời gian chuyển tiếp |
| Sai grant/scope | Client auth đúng nhưng xin grant hoặc scope ngoài đăng ký | Không cấp token ngoài quyền |
| Chuyển issuer | AS issuer public khác `aud` mà client dùng | Từ chối; cần cập nhật client và policy sau migration |

**Kiểm thử tương thích phiên bản Spring:** đối với RFC 10070 vừa cập nhật năm 2026, cần đặc biệt xác nhận bộ validator của phiên bản Spring Authorization Server đang triển khai **thực sự từ chối** audience là URL token endpoint hoặc mảng audience nhiều giá trị. Nếu chưa, thiết kế custom validator phù hợp thay vì ghi nhận PASS chỉ vì một assertion đúng được chấp nhận.

### 10.3. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `invalid_client` dù JWT đã ký | Sai `client_id`, phương thức đăng ký, `iss/sub/aud`, chữ ký hoặc `alg` | Kiểm tra `RegisteredClient`, metadata issuer và header/claims **đã che dữ liệu nhạy cảm** |
| `kid` not found | Public JWKS không chứa đúng `kid`, cache chưa refresh | Kiểm tra JWKS client, thứ tự công bố trước rollout, cache/TTL |
| JWT claim audience không hợp lệ | Dùng token endpoint URL thay AS issuer; trùng/sai dấu slash | Đặt `aud` đúng một AS issuer theo RFC 10070 |
| Signing algorithm mismatch | `tokenEndpointAuthenticationSigningAlgorithm` không khớp key/JWT header | Thống nhất RS256/EC algorithm đã đăng ký; không dùng `none` |
| JWKS fetch fail | URL sai, TLS/DNS lỗi, proxy chặn hoặc policy egress | Kiểm tra `jwkSetUrl`, HTTPS, allowlist, DNS và network policy |
| JWT assertion expired | Client/server lệch giờ hoặc `exp` đặt quá ngắn so với latency | Đồng bộ NTP và chọn TTL/skew hợp lý; không nới hạn dùng vô tội vạ |
| `typ` mới bị thư viện cũ xử lý không tương thích | Decoder/validation chưa hỗ trợ explicit type | Kiểm thử tương thích thư viện; nâng cấp hoặc cấu hình xác minh type phù hợp |
| `private_key_jwt` đăng ký rồi nhưng client vẫn gửi Basic | OAuth Client library không tự ký assertion hoặc cấu hình phương thức chưa đúng | Thêm cơ chế ký client assertion bên client và kiểm tra request thực tế |
| Client xác thực thành công nhưng API trả 403 | Access token thiếu scope/audience/authorization phù hợp | Kiểm tra Resource Server policy; `private_key_jwt` chỉ là xác thực client tại AS |

## 11. Checklist vận hành và câu hỏi tự kiểm tra

Trước khi đưa client `private_key_jwt` lên production:

- [ ] Mỗi client có `client_id` riêng, `PRIVATE_KEY_JWT` được đăng ký rõ ràng, grant type và scope tối thiểu.
- [ ] `ClientSettings.jwkSetUrl` trỏ đến **HTTPS JWKS của đúng client** và URL được admin/automation tin cậy kiểm soát.
- [ ] JWT assertion ký bằng private key không được xuất ra ngoài miền tin cậy; public JWKS **chỉ** có key công khai, `kid` ổn định.
- [ ] Thuật toán được chốt theo registration; không nhận `alg=none`, header `jku`/JWK tự cung cấp hoặc key ngoài registry.
- [ ] `iss=sub=client_id`, `aud` **chỉ bằng AS issuer**, `exp` ngắn, `iat` hợp lý, `jti` duy nhất; cân nhắc chống replay có state.
- [ ] Kiểm thử RFC 10070 với phiên bản Spring thực tế, đặc biệt ca audience token endpoint, audience nhiều giá trị và JWT `typ`.
- [ ] Có kế hoạch rotation: publish public key mới trước, đổi key ký sau, gỡ key cũ khi toàn bộ client/AS đã cập nhật.
- [ ] Có runbook khi private key bị lộ: chặn key, thay key, đánh giá access token đã cấp, audit và thông báo sự cố.
- [ ] Hệ thống quan sát theo dõi lỗi `invalid_client`, JWKS fetch, `kid`, latency, rotation; **không** log assertion hoặc khóa.
- [ ] Các môi trường local/staging/production dùng khóa, issuer, registration và policy độc lập.

**Câu hỏi tự kiểm tra:**

1. Vì sao Authorization Server chỉ cần public key để xác minh `private_key_jwt`, còn client phải có private key?
2. `iss` và `aud` trong JWT client assertion khác nhau thế nào, đặc biệt khi AS cũng có issuer identifier riêng?
3. Sau RFC 10070, có được dùng `https://login.example.vn/oauth2/token` làm `aud` thay issuer `https://login.example.vn` hay không?
4. `ClientSettings.jwkSetUrl` và `Authorization Server jwks_uri` trỏ đến hai bộ khóa nào?
5. Vì sao `kid` trong JWT chưa đủ để xác minh client, và có rủi ro gì khi tin URL `jku` từ assertion?
6. Nếu đã có `jti` duy nhất nhưng server không lưu/kiểm tra lịch sử `jti`, assertion có được bảo vệ khỏi replay không?
7. Khi xoay vòng private key, tại sao phải công bố public key mới trước khi client bắt đầu ký bằng key đó?
8. `private_key_jwt` thay thế `grant_type=client_credentials` hay hoạt động cùng với một grant type?

## Tài liệu tham khảo

- [RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523).
- [RFC 10070 (11/2026) — Updates to OAuth 2.0 JWT Client Authentication and Assertion-Based Authorization Grants](https://www.rfc-editor.org/rfc/rfc10070.html): cập nhật bắt buộc về `aud` và khuyến nghị `typ`.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): định danh issuer và metadata.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517); [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515); [RFC 7519 — JWT](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): hạn chế thuật toán và nguy cơ thay đổi mục đích sử dụng JWT.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): client authentication filter/provider và cách custom validation JWT assertion.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `ClientSettings` và JWKS.
- [Spring Authorization Server — ClientSettings.Builder API (1.5.8)](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.Builder.html): `jwkSetUrl` và `tokenEndpointAuthenticationSigningAlgorithm`.
