# Bearer token và token ràng buộc bên gửi có mô hình bảo vệ khác nhau

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một access token có thể được bảo vệ theo hai mô hình khác nhau:

- **Bearer token**: bất kỳ bên nào đang sở hữu token đều có thể trình token để sử dụng, miễn token còn hợp lệ và API chấp nhận.
- **Sender-constrained token (token ràng buộc bên gửi)**: token được liên kết với một khóa hoặc chứng thư của client. Khi gọi API, client phải chứng minh đang nắm giữ khóa riêng tương ứng hoặc chứng thư TLS đã được ràng buộc với token.

Sự khác biệt này ảnh hưởng trực tiếp tới nguy cơ **token bị đánh cắp rồi phát lại**. Nếu kẻ tấn công lấy được bearer token, họ có thể dùng token từ một thiết bị khác trong thời gian token còn hiệu lực. Nếu token được ràng buộc với khóa và Resource Server xác minh proof đúng cách, chỉ có access token thường chưa đủ để sử dụng token.

Hai cơ chế sender-constrained phổ biến trong OAuth 2.0 là:

1. **DPoP — Demonstrating Proof of Possession**, chuẩn hóa tại RFC 9449. Client ký một proof JWT cho từng HTTP request bằng khóa riêng; access token được ràng buộc với public key tương ứng.
2. **Mutual TLS certificate-bound access token**, chuẩn hóa tại RFC 8705. Access token được ràng buộc với chứng thư X.509 của client; khi gọi API, client phải thiết lập kết nối TLS có client certificate tương ứng.

> **Nguyên tắc quan trọng:** JWT hay opaque mô tả cách biểu diễn/xác minh token; bearer hay sender-constrained mô tả cách token được phép sử dụng. Một access token có thể là JWT hoặc opaque, đồng thời có thể là bearer hoặc được ràng buộc với một khóa/chứng thư. Đừng nhầm định dạng token với cơ chế chứng minh người gửi.

Bài này giải thích luồng phát hành và sử dụng token, claim `cnf`, DPoP proof, mTLS certificate binding, cách cấu hình Spring Security, những điểm cần kiểm tra tại reverse proxy, cách kiểm thử replay và lựa chọn mô hình phù hợp. Các ví dụ Java chính sử dụng **Spring Security Servlet Resource Server**. WebFlux có API và filter model riêng; không sao chép nguyên các lớp Servlet vào reactive stack.

## 1. Bearer token hoạt động như thế nào?

Một client gửi access token trong HTTP `Authorization` header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

Resource Server xác minh token theo loại token:

- JWT: xác minh chữ ký bằng khóa tin cậy, kiểm tra issuer, audience, thời hạn và các điều kiện khác.
- Opaque token: gọi introspection endpoint tin cậy để kiểm tra trạng thái token và lấy thông tin cần thiết.

Nếu token hợp lệ và có scope phù hợp, API cho phép request tiếp tục.

### 1.1. Bearer nghĩa là “ai có token thì có thể trình token”

Ví dụ:

~~~text
Client A nhận access token T
        |
        v
T bị ghi vào log hoặc bị lấy từ bộ nhớ
        |
        v
Attacker lấy được T
        |
        v
Attacker gửi Authorization: Bearer T
        |
        v
Resource Server thấy token hợp lệ
        |
        v
Request có thể được chấp nhận
~~~

Resource Server không có bằng chứng rằng request đến từ chính client đã nhận token ban đầu. Token hoạt động như một **credential dạng possession**: người nắm giữ nó có thể sử dụng.

TLS bảo vệ token trên đường truyền giữa hai đầu TLS, nhưng không tự bảo vệ token sau khi token bị lộ từ:

- Log ứng dụng, proxy hoặc tracing.
- Browser storage, mobile storage hoặc file cấu hình.
- Memory dump, crash dump hoặc telemetry.
- Clipboard, shell history hoặc ticket hỗ trợ.
- Một service trung gian có quyền đọc request headers.

### 1.2. Bearer token không đồng nghĩa JWT

Bearer token có thể là JWT:

~~~http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

hoặc opaque reference:

~~~http
Authorization: Bearer 4Y7dR2kq9v...
~~~

Trong cả hai trường hợp, nếu token là bearer, bên giữ token có thể trình nó. Việc JWT có chữ ký không chứng minh request được gửi bởi đúng client đã nhận token.

**Chữ ký JWT chứng minh token được phát hành bởi nguồn có khóa ký tương ứng**, không chứng minh người gửi request hiện tại đang giữ một khóa riêng của client.

## 2. Sender-constrained token là gì?

Sender-constrained token gắn access token với một **proof-of-possession credential**:

~~~text
Authorization Server
        |
        | Phát access token T
        | Ràng buộc T với public key K
        v
Client giữ private key K_private
        |
        | Gửi T + proof chứng minh đang giữ K_private
        v
Resource Server
        |
        | Xác minh T
        | Xác minh proof
        | So sánh proof key với key binding trong T
        v
Chỉ chấp nhận khi cả hai bước hợp lệ
~~~

Kẻ tấn công chỉ lấy được access token sẽ không có đủ thông tin để tạo proof hợp lệ, nếu private key được bảo vệ và Resource Server thực sự kiểm tra binding.

### 2.1. Claim `cnf` mô tả khóa/chứng thư được ràng buộc

Trong JWT access token, RFC 7800 định nghĩa claim **`cnf` (confirmation)** để biểu diễn thông tin xác nhận credential của client. Các chuẩn cụ thể sử dụng thành viên bên trong `cnf` khác nhau:

**DPoP:**

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  },
  "exp": 2000000300
}
~~~

`cnf.jkt` là JWK SHA-256 thumbprint của public key dùng để ký DPoP proof.

**mTLS certificate-bound access token:**

~~~json
{
  "iss": "https://login.example.com",
  "sub": "svc:inventory-sync",
  "aud": ["orders-api"],
  "scope": "orders.import",
  "cnf": {
    "x5t#S256": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
  },
  "exp": 2000000300
}
~~~

`cnf.x5t#S256` là SHA-256 thumbprint của chứng thư X.509 client được dùng để ràng buộc token.

Các giá trị thumbprint ở đây chỉ minh họa định dạng; không phải credential thực.

### 2.2. Không được tự tạo `cnf` ở Resource Server

`cnf` phải được gắn bởi Authorization Server theo quy trình phát hành token. Resource Server đọc claim này **sau khi token đã được xác minh** và so sánh với proof/certificate của request.

Không làm:

~~~java
// SAI: tự thêm cnf vào token chỉ để vượt qua kiểm tra.
claims.put("cnf", Map.of("jkt", request.getHeader("X-Client-Key")));
~~~

Header do client gửi không chứng minh khóa hoặc chứng thư đã được AS ràng buộc với token.

## 3. So sánh ba mô hình bảo vệ

| Tiêu chí | Bearer | DPoP | mTLS-bound token |
|---|---|---|---|
| Credential bổ sung khi gọi API | Không | DPoP proof JWT | Client certificate trong TLS |
| Access token header | `Authorization: Bearer` | `Authorization: DPoP` | `Authorization: Bearer` |
| Header bổ sung | Không | `DPoP: <proof>` | Không bắt buộc có HTTP proof header |
| Binding trong access token | Không cần `cnf` | `cnf.jkt` | `cnf.x5t#S256` |
| Proof được kiểm tra ở đâu | Token validation | Application layer | TLS handshake + token/certificate binding |
| Ràng buộc HTTP method/URI | Không | Có qua `htm` và `htu` | Không theo cách DPoP làm |
| Ràng buộc hash access token | Không | Có qua `ath` | Không qua DPoP `ath` |
| Hạ tầng cần có | TLS | TLS + client key management | TLS mutual authentication + PKI |
| Phù hợp thường gặp | API phổ thông | Mobile/native/public client, client khó dùng mTLS | Service-to-service, môi trường PKI |
| Rủi ro còn lại | Token bị đánh cắp có thể bị replay | Private key bị chiếm hoặc proof bị replay nếu thiếu kiểm soát | Client certificate/private key bị chiếm hoặc proxy xử lý sai |

DPoP và mTLS đều tăng khả năng chống sử dụng access token bị đánh cắp. Chúng không loại bỏ các rủi ro như client endpoint bị chiếm quyền, malware có thể gọi private-key signer, quyền API cấp quá rộng hoặc lỗi authorization ở tầng nghiệp vụ.

## 4. DPoP: chứng minh sở hữu khóa theo từng HTTP request

DPoP được định nghĩa trong **RFC 9449**. Client tạo một cặp khóa:

~~~text
K_private: private key, chỉ client giữ
K_public:  public key, được công bố trong DPoP proof
~~~

Client gửi proof JWT ký bằng `K_private`. Authorization Server liên kết access token với thumbprint của `K_public`. Khi gọi Resource Server, client tiếp tục gửi proof mới để chứng minh đang sở hữu private key.

### 4.1. Luồng cấp token

~~~text
1. Client tạo hoặc chọn DPoP key pair
             |
             v
2. Client gửi token request tới Authorization Server
   kèm DPoP proof trong header DPoP
             |
             v
3. Authorization Server xác minh proof JWT
             |
             v
4. Authorization Server lấy public JWK
   và tính JWK thumbprint
             |
             v
5. AS phát access token có cnf.jkt
             |
             v
6. Token response báo token_type = DPoP
~~~

Ví dụ token request:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: eyJraWQiOiJjbGllbnQta2V5IiwidHlwIjoiZHBvcCtqd3QifQ...

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
client_id=storefront-web&
code_verifier=PKCE_VERIFIER
~~~

Proof tại token endpoint thường có các claim `htm`, `htu`, `iat`, `jti` và có thể có `nonce` nếu AS yêu cầu. Nó chưa cần `ath` vì client chưa trình access token trong request này.

Token response có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "DPoP",
  "expires_in": 600
}
~~~

`token_type=DPoP` báo client rằng access token được ràng buộc với public key của DPoP proof.

### 4.2. DPoP proof có những thành phần nào?

DPoP proof là một JWT có header dạng:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<public-key-x>",
    "y": "<public-key-y>"
  }
}
~~~

Header `jwk` chứa public key; không được đưa private key parameters vào proof.

Với protected resource request, payload thường có:

~~~json
{
  "jti": "unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.com/api/orders",
  "iat": 2000000000,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

| Claim | Ý nghĩa |
|---|---|
| `jti` | ID duy nhất của proof, dùng để phát hiện proof bị phát lại |
| `htm` | HTTP method của request |
| `htu` | HTTP target URI theo quy tắc canonicalization của RFC 9449 |
| `iat` | Thời điểm proof được tạo |
| `ath` | Hash của access token đang được gửi |
| `nonce` | Nonce do server yêu cầu, khi áp dụng |

`htu` được tính theo quy tắc của RFC 9449; query string và fragment không được đưa vào giá trị URI target này. Khi có reverse proxy, Resource Server phải xác định đúng public URI mà client đã dùng.

### 4.3. Protected resource request

Khác với bearer token, DPoP access token dùng scheme `DPoP`:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: DPoP ACCESS_TOKEN_VALUE
DPoP: SIGNED_DPOP_PROOF_JWT
~~~

Resource Server cần kiểm tra ít nhất:

1. Access token hợp lệ theo issuer, audience, thời hạn, chữ ký hoặc introspection.
2. Access token có binding `cnf.jkt`.
3. DPoP proof JWT có `typ=dpop+jwt` và thuật toán chữ ký được phép.
4. Chữ ký proof hợp lệ theo public JWK trong proof.
5. Thumbprint của public JWK khớp `cnf.jkt` trong access token.
6. `htm` khớp HTTP method thực tế.
7. `htu` khớp URI request theo quy tắc chuẩn.
8. `ath` khớp hash của access token được gửi.
9. `iat` nằm trong cửa sổ thời gian chấp nhận.
10. `jti` chưa được sử dụng trước đó.
11. `nonce` khớp nếu Resource Server yêu cầu nonce.

**Không bỏ qua một bước nào chỉ vì chữ ký DPoP proof hợp lệ.** Một proof được ký bằng khóa bất kỳ vẫn không được chấp nhận nếu public key không khớp `cnf.jkt` của access token.

### 4.4. `ath` ngăn proof bị ghép với token khác

Giả sử client sở hữu:

~~~text
Access token A
Access token B
```

Nếu proof được ký chỉ theo method/URI mà không ràng buộc token, attacker có thể tìm cách ghép proof với một access token khác.

`ath` ràng buộc proof với đúng access token đang gửi. Về ý tưởng:

~~~text
ath = BASE64URL-ENCODE(SHA-256(access_token))
```

Resource Server tự tính hash từ token nhận được rồi so sánh với claim `ath`. Không lấy `ath` từ request header khác hoặc tin kết quả do client tự gửi mà không tính lại.

### 4.5. Nonce và challenge

Resource Server có thể yêu cầu client sử dụng nonce. Server trả một header như:

~~~http
HTTP/1.1 401 Unauthorized
DPoP-Nonce: SERVER_NONCE
WWW-Authenticate: DPoP error="use_dpop_nonce"
~~~

Client tạo proof mới có claim `nonce` tương ứng và gửi lại. Nonce giúp giảm nguy cơ attacker chuẩn bị proof từ trước rồi phát lại sau.

Nonce không thay thế `jti` replay detection. Hai cơ chế bổ sung cho nhau và cần được triển khai theo RFC 9449 cùng contract của server.

## 5. Replay attack với DPoP và cách ngăn chặn

DPoP proof có thời hạn ngắn, nhưng một proof bị chặn bắt vẫn có thể bị phát lại trong cửa sổ chấp nhận nếu server không kiểm soát việc sử dụng lại.

Ví dụ:

~~~text
Client gửi proof có jti=proof-123
        |
        v
Attacker chặn request
        |
        v
Attacker gửi lại đúng proof-123
        |
        v
Nếu server không lưu jti đã dùng,
proof có thể được xử lý lần nữa
~~~

Resource Server cần:

- Bắt buộc `jti` tồn tại và có giá trị duy nhất theo proof.
- Giới hạn tuổi proof qua `iat` và clock skew.
- Lưu dấu vết `jti` đã dùng trong một khoảng thời gian phù hợp.
- Dùng thao tác insert-if-absent hoặc cơ chế atomic tương đương để hai node không cùng chấp nhận một proof.
- Giữ cache đủ lâu để bao phủ toàn bộ cửa sổ proof có thể hợp lệ.
- Đồng bộ clock giữa các nodes.

### 5.1. Replay cache trong Spring Security

Spring Security có `DPoPProofReplayValidator` từ **6.5.12**. Validator này kiểm tra `iat` nằm trong cửa sổ chấp nhận và `jti` chưa được sử dụng; `jti` được lưu trong Spring Cache để đảm bảo proof chỉ dùng một lần.

API có các thành phần:

- `DPoPProofReplayValidator`
- `DPoPProofReplayValidator.InMemoryCache`
- `DPoPProofJwtDecoderFactory`

`InMemoryCache` sử dụng `ConcurrentHashMap`, phù hợp cho một node hoặc môi trường thử nghiệm. Tài liệu cảnh báo implementation này chỉ phù hợp single-node; hệ thống nhiều replicas cần cache phân tán như Redis hoặc Hazelcast để tất cả instances cùng nhìn thấy replay state.

Ví dụ tạo validator:

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.jwt.DPoPProofReplayValidator;
import org.springframework.security.oauth2.jwt.DPoPProofReplayValidator.InMemoryCache;

DPoPProofReplayValidator replayValidator =
    new DPoPProofReplayValidator(new InMemoryCache());

replayValidator.setClockSkew(Duration.ofSeconds(30));
~~~

Đây là ví dụ tạo validator. Để áp dụng custom validator vào proof decoder, dùng extension point `DPoPProofJwtDecoderFactory.setJwtValidatorFactory(...)` và giữ các default validators của framework. Không thay chúng bằng một validator chỉ kiểm tra `jti`, vì như vậy có thể làm mất các ràng buộc `htm`, `htu`, `jkt`, `ath` và `iat`.

### 5.2. Tùy chỉnh proof validator factory

Trong Spring Security từ 6.5.12, factory cung cấp hàm `createDefaultJwtValidatorFactory(...)` để kết hợp các kiểm tra mặc định với validators bổ sung:

~~~java
DPoPProofJwtDecoderFactory proofDecoderFactory =
    new DPoPProofJwtDecoderFactory();

proofDecoderFactory.setJwtValidatorFactory(
    DPoPProofJwtDecoderFactory.createDefaultJwtValidatorFactory(
        List.of(replayValidator)
    )
);
~~~

Khi tự wiring `DPoPAuthenticationProvider`, có thể truyền factory bằng `setDPoPProofVerifierFactory(...)`. Nếu dùng DSL DPoP cấp cao của Spring Security 7.1, hãy xem API extension tương ứng của đúng phiên bản; không giả định mọi custom provider có thể được thay thế trực tiếp từ mọi configurer.

### 5.3. Cache replay trong môi trường nhiều node

~~~text
API instance A ----+
                   |
API instance B ----+---- Shared replay cache
                   |
API instance C ----+
~~~

Nếu mỗi node dùng cache in-memory riêng:

- Request đầu tiên tới node A lưu `jti`.
- Attacker phát lại proof tới node B.
- Node B chưa thấy `jti`, có thể chấp nhận lần nữa.

Replay cache phải có semantics atomic trên toàn cụm. Cũng cần TTL tự xóa entry sau khi proof hết thời hạn để giới hạn dung lượng.

## 6. mTLS-bound access token: ràng buộc với chứng thư X.509

DPoP dùng proof JWT ở tầng HTTP application. **mTLS-bound access token** dùng chứng thư client trong quá trình TLS handshake.

Client có:

~~~text
Client certificate
Client private key
```

Khi kết nối tới API, client và server thực hiện mutual TLS:

~~~text
Client                               Resource Server
  |                                        |
  | ClientHello                            |
  |--------------------------------------->|
  |                                        |
  | Server certificate                    |
  |<---------------------------------------|
  |                                        |
  | Client certificate                     |
  |--------------------------------------->|
  |                                        |
  | Client proves private-key possession  |
  |<-------------------------------------->|
  |                                        |
  | TLS channel established               |
~~~

TLS stack xác minh certificate chain theo trust store và policy của server. Sau đó Resource Server cần **so sánh chứng thư client của kết nối với binding trong access token**.

### 6.1. Claim `cnf.x5t#S256`

Access token được ràng buộc với certificate có thể chứa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "svc:inventory-sync",
  "aud": ["orders-api"],
  "scope": "orders.import",
  "cnf": {
    "x5t#S256": "BASE64URL_SHA256_CERT_THUMBPRINT"
  },
  "exp": 2000000300
}
~~~

Thumbprint được tính trên DER-encoded X.509 certificate:

~~~text
x5t#S256 =
    BASE64URL-ENCODE(
        SHA-256(DER-ENCODED-CERTIFICATE)
    )
~~~

Resource Server lấy certificate đã được TLS layer xác minh, tính lại thumbprint và so sánh với claim `cnf.x5t#S256`.

Nếu attacker chỉ lấy access token mà không có private key của certificate, họ không thể thiết lập TLS connection với đúng client certificate.

### 6.2. Access token vẫn dùng Authorization: Bearer

mTLS-bound access token thường được trình trong header:

~~~http
GET /api/import/jobs HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Điểm khác biệt nằm ở **TLS connection**: client phải gửi certificate tương ứng trong handshake. Không có `DPoP` proof header.

Vì vậy:

- DPoP: scheme `Authorization: DPoP`, thêm header `DPoP`.
- mTLS-bound: scheme `Authorization: Bearer`, client certificate được trình ở TLS layer.

Không cố đọc certificate từ một header tùy ý rồi xem đó là mTLS. Chứng thư phải đến từ TLS connection đã được xác minh hoặc một gateway được tin cậy có cơ chế chuyển tiếp danh tính certificate an toàn.

## 7. Cấu hình phát hành mTLS-bound token tại Authorization Server

Resource Server không thể tự ràng buộc token nếu AS không phát hành token có certificate confirmation.

Với **Spring Authorization Server**, có thể đăng ký client sử dụng TLS client authentication và bật certificate-bound access tokens.

~~~java
RegisteredClient mtlsClient =
    RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("inventory-sync")
        .clientAuthenticationMethod(ClientAuthenticationMethod.TLS_CLIENT_AUTH)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.import")
        .clientSettings(ClientSettings.builder()
            .x509CertificateSubjectDN(
                "CN=inventory-sync,OU=Workloads,O=Example")
            .build())
        .tokenSettings(TokenSettings.builder()
            .x509CertificateBoundAccessTokens(true)
            .build())
        .build();
~~~

Ví dụ cần các imports từ Spring Authorization Server, bao gồm `RegisteredClient`, `ClientAuthenticationMethod`, `AuthorizationGrantType`, `ClientSettings`, `TokenSettings` và `UUID`.

Ý nghĩa:

- `TLS_CLIENT_AUTH`: AS xác thực OAuth client bằng TLS client certificate.
- `x509CertificateSubjectDN(...)`: ràng buộc danh tính certificate theo cấu hình client.
- `x509CertificateBoundAccessTokens(true)`: yêu cầu access token được gắn với certificate thumbprint.

Đây là cấu hình phía **Authorization Server**. Nó không tự cấu hình ingress, TLS connector hoặc việc Resource Server kiểm tra claim binding. Phía API vẫn phải nhận được certificate client đúng và đối chiếu `cnf.x5t#S256`.

## 8. Kiểm tra certificate binding tại Resource Server

Spring Security `oauth2ResourceServer().jwt()` có thể xác minh chữ ký và claims JWT, nhưng việc xác minh `cnf.x5t#S256` còn cần certificate của **request hiện tại**.

`JwtDecoder` chỉ nhận token; nó không tự biết TLS client certificate đang được dùng cho HTTP request. Vì vậy cần một bước request-aware sau khi JWT được xác minh.

### 8.1. Luồng xử lý

~~~text
HTTP request
    |
    +-- TLS layer xác minh client certificate
    |
    +-- BearerTokenAuthenticationFilter lấy access token
    |
    +-- JwtAuthenticationProvider xác minh JWT
    |
    +-- Request-aware verifier lấy certificate từ request
    |
    +-- Tính SHA-256 thumbprint của certificate
    |
    +-- So sánh với JWT cnf.x5t#S256
    |
    +-- Match -> Authentication tiếp tục
    |
    +-- Mismatch/missing -> Authentication thất bại
~~~

### 8.2. Interface kiểm tra binding

~~~java
package com.example.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.oauth2.jwt.Jwt;

public interface CertificateBoundAccessTokenVerifier {

    void verify(HttpServletRequest request, Jwt jwt);
}
~~~

Đây là interface do ứng dụng định nghĩa. Implementation phải lấy certificate từ TLS request attribute hoặc một adapter của gateway được tin cậy.

### 8.3. Ví dụ verifier cho Servlet container kết thúc TLS trực tiếp

~~~java
package com.example.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.cert.X509Certificate;
import java.util.Base64;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public class ServletCertificateBoundAccessTokenVerifier
        implements CertificateBoundAccessTokenVerifier {

    private static final String CERTIFICATE_ATTRIBUTE =
        "jakarta.servlet.request.X509Certificate";

    @Override
    public void verify(HttpServletRequest request, Jwt jwt) {
        Object rawConfirmation = jwt.getClaims().get("cnf");

        if (!(rawConfirmation instanceof Map<?, ?> confirmation)) {
            throw new BadCredentialsException(
                "Certificate confirmation is missing");
        }

        Object rawThumbprint = confirmation.get("x5t#S256");

        if (!(rawThumbprint instanceof String expected)
                || expected.isBlank()) {
            throw new BadCredentialsException(
                "Certificate thumbprint is missing");
        }

        Object rawCertificates =
            request.getAttribute(CERTIFICATE_ATTRIBUTE);

        if (!(rawCertificates instanceof X509Certificate[] certificates)
                || certificates.length == 0) {
            throw new BadCredentialsException(
                "Client certificate is required");
        }

        String actual = sha256Thumbprint(certificates[0]);

        boolean matches = MessageDigest.isEqual(
            expected.getBytes(StandardCharsets.US_ASCII),
            actual.getBytes(StandardCharsets.US_ASCII)
        );

        if (!matches) {
            throw new BadCredentialsException(
                "Access token is bound to another certificate");
        }
    }

    private static String sha256Thumbprint(X509Certificate certificate) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(certificate.getEncoded());

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (Exception ex) {
            throw new BadCredentialsException(
                "Could not calculate client certificate thumbprint", ex);
        }
    }
}
~~~

Ví dụ giả định:

- Servlet container trực tiếp nhận TLS client certificate.
- Container đã xác minh certificate chain theo trust store.
- Request attribute chứa client certificate chain theo Servlet contract.
- Certificate đầu tiên trong chain là client certificate.

Tên request attribute và cách cung cấp certificate phụ thuộc Servlet container/phiên bản. Nếu TLS kết thúc tại ingress hoặc API gateway, attribute này có thể không tồn tại.

### 8.4. Bọc JWT AuthenticationManager bằng bước kiểm tra request

~~~java
package com.example.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

@Configuration
public class CertificateBoundResourceServerConfig {

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
            certificateBoundAuthenticationManagerResolver(
                JwtDecoder jwtDecoder,
                CertificateBoundAccessTokenVerifier verifier) {

        AuthenticationManager jwtManager =
            new ProviderManager(
                new JwtAuthenticationProvider(jwtDecoder));

        return request -> authentication -> {
            var result = jwtManager.authenticate(authentication);

            if (!(result instanceof JwtAuthenticationToken jwtAuthentication)) {
                throw new BadCredentialsException(
                    "A verified JWT access token is required");
            }

            verifier.verify(request, jwtAuthentication.getToken());

            return result;
        };
    }
}
~~~

Imports bổ sung cho ví dụ gồm `BadCredentialsException`. Resolver trả một manager gắn với request hiện tại; không lưu `HttpServletRequest` vào singleton hoặc biến dùng chung giữa requests.

Gắn resolver vào Resource Server:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        AuthenticationManagerResolver<HttpServletRequest> certificateBoundResolver)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/import/**")
                .hasAuthority("SCOPE_orders.import")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(certificateBoundResolver))
        .build();
}
~~~

Cấu hình này dùng resolver để thay authentication manager mặc định; không đồng thời thêm `.jwt()` vào cùng configurer. `JwtDecoder` bên trong manager vẫn phải xác minh issuer, audience, signature, expiry và token profile theo contract.

**Giới hạn:** đây là skeleton tích hợp cho JWT access token. Opaque token cần một manager dùng introspector, lấy `cnf` từ introspection principal đã xác minh rồi thực hiện cùng certificate comparison. Không chấp nhận token chỉ vì TLS certificate hợp lệ; binding giữa certificate và token vẫn là bước bắt buộc.

### 8.5. `http.x509()` có đủ để xác minh mTLS-bound token không?

Không.

~~~java
http.x509(Customizer.withDefaults());
~~~

Spring Security X.509 support có thể xác thực danh tính dựa trên client certificate. Nhưng certificate authentication và OAuth access-token certificate binding là hai kiểm tra khác nhau:

- X.509 authentication: certificate đại diện cho principal nào?
- Certificate-bound token: certificate của request có đúng thumbprint được ràng buộc trong access token hay không?

Chỉ bật `http.x509()` không tự kiểm tra `cnf.x5t#S256` trong bearer JWT.

## 9. mTLS qua reverse proxy và API gateway

Trong nhiều hệ thống production, TLS kết thúc ở load balancer hoặc gateway:

~~~text
Client -- mTLS --> API Gateway -- HTTPS/mTLS --> Spring Resource Server
~~~

Khi đó Spring application có thể chỉ thấy kết nối TLS của gateway, không phải certificate gốc của client. Nếu gateway chuyển certificate identity qua header, cần một trust contract rõ:

1. Gateway phải xác minh client certificate ở TLS handshake.
2. Gateway phải xóa mọi header cùng tên do client tự gửi.
3. Gateway chỉ được ghi header certificate sau khi xác minh.
4. Kênh gateway → application phải được bảo vệ, tốt nhất bằng mTLS hoặc một cơ chế workload identity tương đương.
5. Application chỉ tin header từ gateway đã được xác thực, không nhận request trực tiếp bypass gateway.
6. Certificate forwarding phải giữ đúng DER/fingerprint hoặc một định dạng được chuẩn hóa không nhập nhằng.
7. Không dùng DN text thay cho thumbprint nếu token được bind theo `x5t#S256`.

**Không được tin `X-Client-Cert` từ Internet.** Nếu attacker tự gửi header chứa certificate thumbprint phù hợp, Resource Server có thể bị lừa nếu gateway không xóa/ghi đè header hoặc app vẫn cho truy cập trực tiếp.

### 9.1. Vì sao không chỉ tin `X-Forwarded-Client-Cert`?

Tên header không chứng minh nguồn gốc. Chỉ trust proxy metadata khi:

- Network policy bảo đảm request chỉ đến từ proxy.
- Proxy đã xác thực certificate thực tế.
- Header client gửi trước đó bị xóa.
- Có integrity/authentication trên proxy-to-app hop.
- Có kiểm soát đường truy cập trực tiếp tới app.

Nếu không đáp ứng được các điều kiện này, nên triển khai TLS pass-through hoặc một gateway security integration có khả năng chuyển certificate identity đáng tin.

## 10. So sánh DPoP và mTLS chi tiết

### 10.1. DPoP

**Ưu điểm:**

- Không cần client certificate ở TLS layer.
- Có thể phù hợp với mobile/native/public clients.
- Mỗi request có proof gắn với HTTP method và URI.
- Có thể dùng với JWT hoặc opaque access token nếu AS/Resource Server hỗ trợ binding qua token/introspection.
- Có thể dùng key lưu trong secure hardware/keystore nếu client platform hỗ trợ.

**Chi phí và giới hạn:**

- Client phải tạo proof cho mỗi request.
- Cần quản lý private key và vòng đời key.
- Resource Server phải xác minh proof, `ath`, `jkt`, `htm`, `htu`, `iat`, `jti` và nonce nếu áp dụng.
- Replay cache cần chia sẻ giữa các instances.
- Reverse proxy có thể làm thay đổi URI mà Resource Server quan sát; cần canonical public URI đúng.
- DPoP không ký request body; nó không phải cơ chế transaction signing.
- Nếu malware điều khiển ứng dụng hoặc gọi được key signer, DPoP không tự ngăn malware dùng token.

### 10.2. mTLS-bound token

**Ưu điểm:**

- Tận dụng cơ chế TLS mutual authentication.
- Phù hợp service-to-service trong môi trường PKI.
- Không cần thêm DPoP proof JWT cho từng request.
- Có thể dùng certificate/private key trong HSM, keystore hoặc workload identity infrastructure.
- TLS client certificate đã được kiểm tra ở transport layer; Resource Server chỉ cần đảm bảo token binding cũng được xác minh.

**Chi phí và giới hạn:**

- Cần cấp phát, gia hạn, thu hồi và xoay vòng certificate.
- Cần cấu hình trust store và mutual TLS ở ingress/server.
- Reverse proxy/TLS termination phải chuyển identity client an toàn.
- Certificate renewal có thể làm thumbprint thay đổi; token cũ bị ràng buộc certificate cũ.
- Nếu private key certificate bị đánh cắp, attacker có thể chứng minh possession.
- Việc vận hành PKI phức tạp hơn bearer token thông thường.

### 10.3. Chọn theo môi trường

| Bối cảnh | Điểm bắt đầu nên cân nhắc |
|---|---|
| API công khai cho browser/native/mobile | Bearer nếu threat model chấp nhận; DPoP khi cần giảm rủi ro token replay |
| Mobile app có hardware-backed key | DPoP |
| Service-to-service trong Kubernetes/service mesh | mTLS-bound token nếu PKI và gateway hỗ trợ |
| Backend có HSM/client certificate quản lý tập trung | mTLS-bound token |
| Nhiều client cũ chỉ hỗ trợ Bearer | Bearer trong giai đoạn migration, thêm sender-constrained cho client mới |
| Hệ thống cần chống replay mạnh giữa nhiều API nodes | DPoP với shared replay cache hoặc mTLS theo kiến trúc |
| API sau gateway đã có mTLS identity | Có thể dùng mTLS-bound token, nhưng phải kiểm tra binding end-to-end |

Không có một mô hình phù hợp mọi hệ thống. Hãy đánh giá khả năng bảo vệ private key/certificate, nơi token được lưu, kiến trúc proxy, số lượng replicas và yêu cầu thu hồi.

## 11. Token format và sender constraint là hai trục độc lập

| Token representation | Bearer | Sender-constrained |
|---|---|---|
| JWT | JWT có chữ ký, không có confirmation binding | JWT có `cnf.jkt` hoặc `cnf.x5t#S256` |
| Opaque | Introspection trả token active và authorities | Introspection trả thêm `cnf` để Resource Server xác minh proof/certificate |

Ví dụ:

**JWT bearer:**

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

**JWT DPoP-bound:**

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "PUBLIC_JWK_THUMBPRINT"
  },
  "exp": 2000000300
}
~~~

**JWT mTLS-bound:**

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "x5t#S256": "CLIENT_CERT_THUMBPRINT"
  },
  "exp": 2000000300
}
~~~

Một opaque token có thể introspect ra:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "aud": ["orders-api"],
  "cnf": {
    "jkt": "PUBLIC_JWK_THUMBPRINT"
  }
}
~~~

hoặc:

~~~json
{
  "active": true,
  "scope": "orders.import",
  "aud": ["orders-api"],
  "cnf": {
    "x5t#S256": "CLIENT_CERT_THUMBPRINT"
  }
}
~~~

Với opaque token, Resource Server phải lấy confirmation data từ introspection endpoint đáng tin. Không tự suy ra binding từ request headers.

## 12. Cấu hình Bearer Resource Server cơ bản bằng Spring Security

Nếu API chỉ chấp nhận bearer JWT, cấu hình Servlet phổ biến:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BearerResourceServerConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Với opaque token, dùng:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
~~~

Trong bearer-only API, token được xác minh theo request; không có bước chứng minh request được gửi từ đúng private key/certificate đã nhận token. Đây là điểm mà DPoP hoặc mTLS-bound token bổ sung.

## 13. DPoP tích hợp trong Spring Security

Spring Security có API DPoP ở nhiều mức theo phiên bản:

| API | Mốc phiên bản | Vai trò |
|---|---|---|
| `DPoPAuthenticationProvider` | 6.5 | Provider xác thực DPoP-bound access token |
| `DPoPProofJwtDecoderFactory` | 6.5 | Tạo decoder xác minh DPoP proof JWT |
| `DPoPProofReplayValidator` | 6.5.12 | Kiểm tra `iat` và `jti` chưa bị dùng lại |
| `DPoPProofReplayValidator.InMemoryCache` | 6.5.12 | Replay cache in-memory cho single-node |
| `OAuth2ResourceServerConfigurer.dPoP(...)` | 7.1 | DSL bật DPoP-bound access token support |

**Đừng giả định Spring Security 6.4 hoặc 6.5 có cùng DSL như 7.1.** Với dự án 6.5, các provider/factory mức thấp đã có nhưng cần wiring tương ứng. DSL `dPoP(...)` cấp cao được đánh dấu từ 7.1.

### 13.1. JWT Resource Server với DPoP trên Spring Security 7.1+

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DPoPResourceServerConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
                .dPoP(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ở đây:

- `.jwt(...)` cấu hình xác minh access token JWT.
- `.dPoP(...)` bật DPoP-bound access token support.
- DPoP proof được gửi qua `DPoP` header.
- Access token dùng scheme `DPoP` trong `Authorization` header.
- Scope authorization vẫn thực hiện sau authentication.

Cấu hình này cần Authorization Server phát access token có DPoP binding đúng. Chỉ bật DPoP tại Resource Server không tự biến bearer token cũ thành sender-constrained token.

### 13.2. Opaque Resource Server với DPoP

Nếu AS introspection hỗ trợ DPoP-bound opaque token và trả confirmation data đúng contract, có thể cấu hình opaque token manager cùng DPoP support theo API phiên bản:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
    .dPoP(Customizer.withDefaults()))
~~~

Resource Server phải lấy `cnf.jkt` từ introspection result và xác minh nó với public key trong proof. Nếu AS không trả binding data, Resource Server không thể chứng minh opaque token được ràng buộc với khóa DPoP.

### 13.3. Các điểm có thể tùy chỉnh trong DPoP configurer

`DPoPConfigurer` của Spring Security 7.1 có các extension points:

- `requestMatcher(...)`: chọn những request thuộc DPoP flow.
- `authenticationConverter(...)`: chuyển HTTP request thành `DPoPAuthenticationToken`.
- `authenticationSuccessHandler(...)`: xử lý sau authentication thành công.
- `authenticationFailureHandler(...)`: xử lý lỗi proof/token.

Mặc định có `DPoPAuthenticationConverter` và `DPoPAuthenticationEntryPoint`. Chỉ tùy chỉnh khi có yêu cầu rõ về request matching, response hoặc integration; không viết lại proof validation chỉ để thay đổi format JSON lỗi.

### 13.4. Spring Security DPoP xác minh những gì?

DPoP provider và proof decoder làm việc với:

- Access token và token authentication manager.
- DPoP proof JWT.
- Public JWK và binding `jkt`.
- HTTP method và resource URI.
- Access token hash `ath`.
- `iat`, `jti` và các điều kiện proof khác.

Với custom decoder/factory, phải giữ các default validators của framework. Nếu tự thay validator, có thể vô tình bỏ kiểm tra method, URI, key binding hoặc token hash.

### 13.5. Replay cache và triển khai nhiều replicas

Spring Security có `DPoPProofReplayValidator`, nhưng `InMemoryCache` chỉ phù hợp một node. Nếu API chạy nhiều instances sau load balancer, cần cache phân tán để mọi node cùng nhận ra `jti` đã được sử dụng.

Không coi `jti` chỉ cần có mặt là đủ. Chống replay đòi hỏi **lưu và kiểm tra trạng thái sử dụng trước đó**.

## 14. mTLS-bound token trong Spring Security

Spring Security có hỗ trợ X.509 client certificate authentication qua:

~~~java
http.x509(Customizer.withDefaults());
~~~

Nhưng như đã giải thích, X.509 authentication độc lập với việc kiểm tra token `cnf.x5t#S256`. Với OAuth Resource Server, cần một integration layer request-aware:

1. Xác minh JWT/opaque access token theo cơ chế Resource Server.
2. Lấy client certificate đã được TLS stack/gateway xác minh.
3. Tính thumbprint SHA-256 trên DER certificate.
4. Đọc `cnf.x5t#S256` từ token/introspection principal đã xác thực.
5. So sánh an toàn.
6. Từ chối nếu certificate thiếu, token thiếu binding hoặc thumbprint khác.

Không chỉ bật `http.x509()` rồi kết luận bearer token đã được certificate-bound.

## 15. Không nhầm mTLS client authentication với certificate-bound access token

Hai tính năng này liên quan nhưng không hoàn toàn giống nhau.

| Tính năng | Xác minh điều gì? |
|---|---|
| TLS client authentication tại token endpoint | Client đang xin token có certificate được AS chấp nhận |
| Certificate-bound access token | Token đã phát được ràng buộc với thumbprint certificate |
| mTLS tại Resource Server | Request API được thiết lập bằng client certificate hợp lệ |
| `cnf.x5t#S256` verification | Certificate của request đúng là certificate được gắn vào token |

Một client có thể xác thực với AS bằng mTLS nhưng nếu access token không được bind với certificate, token đó vẫn có thể là bearer token thông thường.

Ngược lại, nếu AS phát certificate-bound access token mà API không yêu cầu client certificate và không kiểm tra thumbprint, Resource Server chưa thực hiện đầy đủ sender constraint.

## 16. DPoP và mTLS có thay thế TLS không?

Không.

DPoP là proof ở application layer; mTLS dùng TLS client certificate. Cả hai vẫn cần HTTPS/TLS để bảo vệ confidentiality và integrity của request/response.

DPoP không thay thế:

- TLS server authentication.
- Mã hóa dữ liệu trong transit.
- CORS policy.
- CSRF policy khi credential được browser tự động gửi.
- Authorization theo scope/role/tenant.
- Bảo vệ request body khỏi các lỗi nghiệp vụ.

mTLS không thay thế:

- Issuer/audience validation của access token.
- Scope authorization.
- Kiểm tra certificate binding trong `cnf`.
- Object-level authorization.
- Quản lý token expiry và revocation.

## 17. DPoP không ký toàn bộ HTTP request

Một hiểu nhầm thường gặp là DPoP proof bảo vệ mọi byte của request. DPoP ràng buộc một số thành phần như:

- HTTP method (`htm`).
- Target URI (`htu`).
- Access token (`ath`).
- Proof key (`jkt`).
- Thời điểm và proof ID (`iat`, `jti`).

DPoP không mặc định ký request body hoặc mọi HTTP header. Vì vậy, nó không phải cơ chế transaction signing hoặc message-level signature.

Nếu nghiệp vụ cần xác nhận nội dung chuyển tiền, payload giao dịch hoặc idempotency semantics, cần cơ chế bổ sung phù hợp. Không suy luận rằng DPoP đã ký body JSON chỉ vì proof JWT được ký.

## 18. Bảo vệ private key và certificate

Sender constraint chỉ hữu ích nếu private key được bảo vệ.

### 18.1. Với DPoP

- Lưu private key trong OS keystore, secure enclave hoặc hardware-backed keystore nếu nền tảng hỗ trợ.
- Không đưa private key vào JavaScript bundle, log hoặc analytics.
- Ưu tiên key không exportable khi client platform cho phép.
- Có quy trình xoay vòng và đăng ký key mới với AS.
- Khi key bị mất/compromise, cần revoke/đổi token và liên kết key mới.
- Không dùng cùng một private key cho quá nhiều client/tenant nếu không có lý do và policy rõ.

### 18.2. Với mTLS

- Lưu private key trong HSM, keystore hoặc secret manager có kiểm soát.
- Quản lý certificate issuance, renewal, revocation và trust anchors.
- Theo dõi expiry và thời điểm rotate.
- Giới hạn quyền sử dụng private key cho workload tương ứng.
- Khi certificate đổi, phải xử lý access token đang bound với thumbprint cũ.
- Kiểm tra certificate revocation policy theo PKI, không mặc định TLS stack luôn kiểm tra CRL/OCSP theo cách hệ thống mong muốn.

## 19. Token theft: sender constraint giảm rủi ro nhưng không xóa mọi rủi ro

| Tình huống | Bearer | DPoP/mTLS |
|---|---|---|
| Chỉ lấy được access token từ log | Có thể sử dụng lại | Thiếu private key/certificate nên không đủ |
| Lấy được token và private key DPoP | Có thể sử dụng | Có thể tạo proof hợp lệ |
| Lấy được token và private key mTLS | Có thể sử dụng | Có thể thiết lập TLS với certificate |
| Chiếm quyền tiến trình client | Có thể dùng token | Có thể gọi key signer hoặc dùng certificate |
| Replay cùng DPoP proof | Không có proof | Bị chặn nếu `jti` replay protection hoạt động |
| Dùng proof cho HTTP method khác | Không có ràng buộc method | DPoP `htm` mismatch |
| Dùng proof cho URI khác | Không có ràng buộc URI | DPoP `htu` mismatch |
| Dùng certificate khác với token binding | Không có binding | mTLS thumbprint mismatch |

Nếu attacker chiếm quyền chính client hoặc có khả năng gọi thiết bị ký private key, sender constraint không tự giải quyết được. Cần endpoint hardening, secure storage, anti-malware, token lifetime ngắn, least privilege và monitoring.

## 20. DPoP, nonce và reverse proxy

DPoP xác minh URI mà client đã gọi. Nhưng khi API nằm sau proxy:

~~~text
Client gọi:
https://api.example.com/api/orders

Proxy chuyển tới:
http://orders-service:8080/api/orders
~~~

Resource Server nhìn thấy internal URI `http://orders-service:8080/api/orders`, trong khi DPoP proof có `htu=https://api.example.com/api/orders`.

Nếu so sánh sai URI, request hợp lệ bị từ chối. Nếu tin mọi `X-Forwarded-Host` hoặc `X-Forwarded-Proto` do client gửi, attacker có thể ảnh hưởng giá trị URI được kiểm tra.

Cần:

- Cấu hình trusted proxy addresses.
- Để proxy loại bỏ forwarded headers do client tự gửi.
- Chỉ dùng forwarded metadata từ proxy được xác thực.
- Cấu hình ứng dụng dựng external URI nhất quán.
- Kiểm thử host, port, path, reverse-proxy prefix và scheme HTTPS.
- Không tắt `htu` validation chỉ để request qua được.

## 21. 401, 403 và lỗi sender proof

| Trường hợp | Kết quả thường gặp | Giải thích |
|---|---|---|
| Không có token vào API private | 401 | Chưa authentication |
| Bearer token sai chữ ký/expired | 401 | Token invalid |
| DPoP-bound token gửi bằng scheme `Bearer` | Từ chối authentication | Thiếu DPoP proof theo contract |
| DPoP proof thiếu | Từ chối authentication | Không chứng minh possession |
| DPoP proof signature sai | Từ chối authentication | Proof không hợp lệ |
| `cnf.jkt` khác proof key | Từ chối authentication | Token bị dùng với key khác |
| `ath` không khớp token | Từ chối authentication | Proof gắn với access token khác |
| `htm` hoặc `htu` sai | Từ chối authentication | Proof không dành cho request hiện tại |
| DPoP proof đã replay | Từ chối authentication | `jti` đã được sử dụng |
| mTLS client certificate thiếu | TLS handshake hoặc authentication failure | Không có certificate |
| `cnf.x5t#S256` khác certificate | Từ chối authentication | Token bound với certificate khác |
| Token hợp lệ và proof đúng nhưng thiếu scope | 403 | Authorization failure |
| Token/proof hợp lệ nhưng sai tenant ownership | 403/404 theo policy | Business authorization |

Status thực tế phụ thuộc entry point, TLS terminator, exception handler và phiên bản Spring Security. Một lỗi TLS handshake có thể xảy ra trước khi HTTP request tới application, vì vậy không nhất thiết có JSON 401/403 từ controller.

### 21.1. DPoP nonce challenge

Khi server yêu cầu nonce, client có thể phải nhận challenge rồi gửi request mới với proof mới. Client không nên gửi lại nguyên proof cũ; mỗi request cần proof có `jti` mới và `iat` phù hợp.

### 21.2. Không nhầm authentication và authorization

DPoP/mTLS chứng minh sender possession. Chúng không cấp scope.

~~~text
Valid token + valid sender proof
            |
            v
Authentication successful
            |
            v
Check SCOPE_orders.read
            |
            v
Check tenant/order ownership
            |
            v
Allow or deny
~~~

Token bound đúng certificate nhưng thiếu `orders.write` vẫn phải bị 403 khi gọi endpoint ghi.

## 22. Kiểm thử Bearer và sender-constrained token

Một bộ test cần kiểm tra cả token validation lẫn proof binding.

### 22.1. Ma trận DPoP

| Test case | Kỳ vọng |
|---|---|
| Access token DPoP-bound + proof đúng key | Authentication thành công |
| Token đúng nhưng thiếu DPoP proof | Từ chối |
| Proof ký bằng key khác | Từ chối |
| `cnf.jkt` sai | Từ chối |
| `ath` hash không khớp | Từ chối |
| `htm` sai method | Từ chối |
| `htu` sai URI | Từ chối |
| `iat` quá cũ/quá tương lai | Từ chối |
| `jti` lặp lại | Từ chối |
| Nonce bị yêu cầu nhưng thiếu/sai | Từ chối hoặc challenge lại |
| JWT signature sai | Từ chối dù DPoP proof đúng |
| Issuer/audience sai | Từ chối dù DPoP proof đúng |
| Scope thiếu | Authentication pass, authorization 403 |
| User thuộc tenant khác | Business authorization từ chối |

### 22.2. Ma trận mTLS

| Test case | Kỳ vọng |
|---|---|
| Client certificate tin cậy, thumbprint khớp token | Authentication thành công |
| Không có client certificate | TLS/authentication failure |
| Certificate không được trust store chấp nhận | TLS handshake failure |
| Certificate hợp lệ nhưng thumbprint khác token | Authentication từ chối |
| JWT signature sai nhưng certificate đúng | Authentication từ chối |
| Audience sai nhưng certificate đúng | Authentication từ chối |
| Token thiếu `cnf.x5t#S256` trong endpoint yêu cầu mTLS binding | Từ chối |
| Opaque introspection trả `active=false` | Từ chối |
| Token đúng nhưng scope thiếu | 403 |
| Certificate được rotate nhưng client dùng token cũ | Từ chối nếu thumbprint không còn khớp |

### 22.3. Test replay trên nhiều node

Một test quan trọng:

~~~text
1. Gửi proof P tới instance A -> thành công.
2. Gửi lại đúng proof P tới instance B.
3. Instance B phải thấy jti đã được sử dụng.
4. Request thứ hai bị từ chối.
~~~

Nếu test chỉ chạy trên một instance với `InMemoryCache`, nó không chứng minh replay protection hoạt động trong cluster.

### 22.4. Test DPoP bằng mock authentication là chưa đủ

Một test `MockMvc.with(jwt())` có thể gắn JWT authentication trực tiếp và bỏ qua DPoP proof validation. Nó hữu ích để kiểm tra scope/HTTP authorization, nhưng không chứng minh:

- `Authorization: DPoP` được parse đúng.
- Proof JWT được verify.
- `cnf.jkt` khớp.
- `ath`, `htm`, `htu` được so sánh.
- `jti` replay cache hoạt động.

Muốn kiểm tra đầy đủ, cần gửi request HTTP thật qua filter chain với access token và proof JWT được ký bằng test key pair. Test mTLS cần test server/client thực hiện TLS handshake với certificate test.

### 22.5. Test không được dùng private key production

Sinh key/certificate riêng cho test:

~~~text
Test DPoP:
  private key -> ký proof
  public JWK -> proof header
  access token -> cnf.jkt tương ứng

Test mTLS:
  test CA -> ký client certificate
  test private key -> TLS handshake
  access token -> cnf.x5t#S256 tương ứng
~~~

Không dùng private signing keys hoặc client certificates thật của production trong fixture.

## 23. Quan sát và vận hành

Nên theo dõi các nhóm chỉ số riêng:

| Metric/sự kiện | Ý nghĩa |
|---|---|
| `dpop_proof_invalid_signature` | Chữ ký proof sai |
| `dpop_jkt_mismatch` | Public key proof không khớp token |
| `dpop_ath_mismatch` | Proof gắn với token khác |
| `dpop_htm_mismatch` | HTTP method không khớp |
| `dpop_htu_mismatch` | URI không khớp |
| `dpop_nonce_required` | Server cần nonce |
| `dpop_replay_detected` | `jti` đã được sử dụng |
| `mtls_certificate_missing` | Request thiếu client certificate |
| `mtls_certificate_untrusted` | TLS trust validation thất bại |
| `mtls_thumbprint_mismatch` | Certificate không khớp token |
| `token_signature_invalid` | JWT access token không hợp lệ |
| `token_expired` | Token hết hạn |
| `authorization_denied` | Thiếu scope/role hoặc business permission |

Tên metric trên là gợi ý cho instrumentation; không khẳng định mọi tên đều được Spring Security tự phát ra.

Không log:

- Raw bearer/DPoP access token.
- Toàn bộ DPoP proof JWT.
- Private key hoặc client certificate private material.
- Client secrets.
- Full certificate chain nếu policy yêu cầu hạn chế.
- Nội dung claim PII không cần thiết.

Có thể log `kid`/thumbprint đã được hash hoặc reference nội bộ, loại lỗi, request ID và issuer reference theo policy.

## 24. Quy trình triển khai từ Bearer sang sender-constrained

Một lộ trình thực tế:

**Bước 1 — Kiểm kê clients.** Xác định client nào có khả năng giữ private key, client nào hỗ trợ client certificates và client nào chỉ hỗ trợ bearer.

**Bước 2 — Chọn cơ chế.** DPoP cho client cần proof ở application layer; mTLS cho workload có PKI; giữ bearer cho client cũ trong giai đoạn chuyển đổi nếu threat model cho phép.

**Bước 3 — Cập nhật Authorization Server.** Phát `token_type=DPoP` và `cnf.jkt`, hoặc phát certificate-bound access token với `cnf.x5t#S256`.

**Bước 4 — Cấu hình Resource Server.** Bật DPoP support hoặc triển khai certificate binding verifier theo đúng phiên bản/framework.

**Bước 5 — Bảo vệ key/certificate.** Thiết lập secure storage, rotation, revocation và quy trình cấp phát.

**Bước 6 — Bảo vệ replay.** Cấu hình nonce nếu cần, replay cache và shared state cho nhiều nodes.

**Bước 7 — Kiểm tra reverse proxy.** Đảm bảo `htu` và client certificate identity được truyền theo trust boundary rõ ràng.

**Bước 8 — Test âm tính.** Token bị đánh cắp, proof sai, certificate sai, replay, audience sai, scope thiếu.

**Bước 9 — Rollout có quan sát.** Bắt đầu với nhóm client có khả năng hỗ trợ, đo lỗi và latency.

**Bước 10 — Thu hẹp bearer.** Khi telemetry cho thấy client đã chuyển đổi, áp policy bắt buộc sender constraint cho những route/clients cần bảo vệ cao.

Không nên bật chế độ bắt buộc DPoP hoặc mTLS trước khi AS và client cùng hỗ trợ; nếu chỉ Resource Server thay đổi, token bearer cũ không tự có binding.

## 25. Những hiểu nhầm cần tránh

**“JWT có chữ ký thì không thể bị replay.”** Sai. JWT bearer bị đánh cắp vẫn có thể được sử dụng lại cho tới khi hết hạn hoặc bị từ chối bởi cơ chế khác.

**“Bearer token và JWT là hai loại đối lập.”** Sai. Bearer là cách sử dụng token; JWT là định dạng biểu diễn.

**“Sender-constrained token luôn là JWT.”** Sai. Opaque token có thể được ràng buộc với khóa/chứng thư nếu introspection trả confirmation data.

**“DPoP chỉ cần chữ ký proof hợp lệ.”** Sai. Còn phải kiểm tra binding `jkt`, `ath`, `htm`, `htu`, thời gian, `jti` và nonce khi yêu cầu.

**“DPoP proof có thể dùng lại cho nhiều requests.”** Không. Mỗi request cần proof phù hợp; replay protection cần ngăn `jti` đã sử dụng.

**“DPoP ký request body.”** Không. DPoP ràng buộc method, URI và access token nhưng không mặc định ký toàn bộ body.

**“mTLS client authentication ở token endpoint tự động làm mọi access token certificate-bound.”** Không. AS cần cấu hình phát hành token có certificate binding, và Resource Server phải kiểm tra claim confirmation.

**“Bật `http.x509()` là đã kiểm tra `cnf.x5t#S256`.”** Sai. X.509 authentication không tự so sánh certificate với token binding.

**“Chỉ cần trust `X-Client-Cert` từ gateway.”** Sai nếu gateway chưa xóa header client gửi, kênh proxy-to-app không được bảo vệ hoặc app còn đường truy cập bypass proxy.

**“DPoP thay thế HTTPS.”** Sai. DPoP là proof ở application layer; TLS vẫn cần thiết.

**“mTLS thay thế issuer/audience validation.”** Sai. Certificate binding không chứng minh token được AS đáng tin phát cho đúng API.

**“Nếu token có `cnf`, API tự biết cách kiểm tra.”** Sai. Resource Server phải có integration phù hợp để xác minh proof/certificate của request.

**“DPoP replay cache in-memory dùng được cho mọi cluster.”** Sai. In-memory cache chỉ chia sẻ trong một process/node.

**“Private key DPoP không exportable nghĩa malware không thể dùng nó.”** Không chắc. Malware có thể điều khiển ứng dụng gọi key signer dù không đọc được key bytes.

**“Sender constraint thay thế scope và object authorization.”** Sai. Nó chứng minh possession, không cấp quyền truy cập tài nguyên.

**“Có thể chuyển bearer token cũ thành DPoP bằng cách thêm header DPoP.”** Sai. AS phải phát hành token có binding `cnf.jkt`; proof header không tự gắn khóa vào token cũ.

## 26. Câu hỏi tự kiểm tra

**1.** Bearer token có nghĩa gì?

> Bất kỳ bên nào sở hữu token đều có thể trình token để sử dụng; Resource Server không yêu cầu proof riêng về client key.

**2.** Sender-constrained token bổ sung điều gì?

> Token được ràng buộc với public key hoặc client certificate; request cần chứng minh possession của credential tương ứng.

**3.** `cnf.jkt` dùng cho cơ chế nào?

> DPoP; nó chứa JWK SHA-256 thumbprint của public key ký proof.

**4.** `cnf.x5t#S256` dùng cho cơ chế nào?

> mTLS certificate-bound access token; nó chứa SHA-256 thumbprint của client X.509 certificate.

**5.** DPoP access token được gửi bằng scheme nào?

> `Authorization: DPoP <access-token>`, kèm header `DPoP` chứa proof JWT.

**6.** mTLS-bound access token thường được gửi bằng scheme nào?

> `Authorization: Bearer <access-token>`, đồng thời client phải dùng certificate phù hợp trong TLS handshake.

**7.** `ath` trong DPoP proof có tác dụng gì?

> Ràng buộc proof với đúng access token được gửi trong request bằng hash SHA-256.

**8.** `htm` và `htu` dùng để làm gì?

> Ràng buộc proof với HTTP method và URI của request.

**9.** Vì sao cần kiểm tra `jti`?

> Để phát hiện proof đã được sử dụng và ngăn replay.

**10.** Spring Security có DPoP DSL từ phiên bản nào?

> `OAuth2ResourceServerConfigurer.dPoP(...)` có từ Spring Security 7.1; các API provider/factory thấp hơn có từ 6.5.

**11.** `DPoPProofReplayValidator` có từ phiên bản nào?

> Spring Security 6.5.12.

**12.** `DPoPProofReplayValidator.InMemoryCache` có phù hợp cluster nhiều nodes không?

> Không. Cần cache phân tán để mọi node cùng thấy `jti` đã dùng.

**13.** `http.x509()` có tự xác minh token `cnf.x5t#S256` không?

> Không. Cần so sánh thumbprint của certificate request với confirmation claim trong access token.

**14.** Vì sao phải cẩn thận khi TLS kết thúc ở reverse proxy?

> Resource Server có thể chỉ thấy certificate của proxy; forwarded client certificate chỉ được tin nếu proxy được xác thực và header không thể bị client giả mạo.

**15.** DPoP có ký request body không?

> Không mặc định. Nó ràng buộc method, URI và access token; transaction/body integrity cần cơ chế khác nếu nghiệp vụ yêu cầu.

**16.** Sender-constrained token có thay thế scope authorization không?

> Không. Sau authentication và proof verification, API vẫn phải kiểm tra scope, role, tenant và quyền trên tài nguyên.

## 27. Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token và cách gửi trong HTTP Authorization header.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof, key binding, `jkt`, `ath`, `htm`, `htu`, nonce và replay.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): TLS client authentication và certificate-bound access token.
- [RFC 7800 — Proof-of-Possession Key Semantics for JWTs](https://www.rfc-editor.org/rfc/rfc7800): claim `cnf` và confirmation methods.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK, public key và JWK thumbprint context.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims và token time.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): lấy trạng thái và claims của opaque token.
- [Spring Security — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): DPoP flow, `cnf.jkt`, request headers và proof.
- [Spring Security — OAuth2ResourceServerConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html): `dPoP(...)` và các cấu hình Resource Server; DPoP DSL từ 7.1.
- [Spring Security — DPoPConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.DPoPConfigurer.html): request matcher, converter và success/failure handlers.
- [Spring Security — DPoPAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html): provider xác thực DPoP-bound token.
- [Spring Security — DPoPProofJwtDecoderFactory API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofJwtDecoderFactory.html): decoder factory và default proof validators.
- [Spring Security — DPoPProofReplayValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofReplayValidator.html): replay validation, `iat`, `jti`, cache và clock skew.
- [Spring Security — DPoPProofReplayValidator.InMemoryCache API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofReplayValidator.InMemoryCache.html): giới hạn single-node và lựa chọn cache phân tán.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cấu hình client và certificate-bound access tokens.
- [Spring Security — X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): xác thực client certificate ở Servlet security.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT access token, issuer, audience và JWK Set.

**Kết luận:** Bearer token cho phép bên đang nắm giữ token trình token để sử dụng; sender-constrained token còn yêu cầu proof gắn với khóa hoặc chứng thư của client. DPoP thực hiện điều này bằng proof JWT theo từng request và binding `cnf.jkt`; mTLS thực hiện bằng TLS client certificate và binding `cnf.x5t#S256`. Spring Security có DPoP DSL tích hợp từ 7.1, còn mTLS certificate-bound token cần bảo đảm Resource Server so sánh certificate thực của request với token confirmation claim. Dù dùng cơ chế nào, vẫn phải xác minh issuer/audience/thời hạn, scope và quyền trên tài nguyên; sender constraint giảm nguy cơ token bị đánh cắp và phát lại nhưng không thay thế TLS, key protection hay authorization.
