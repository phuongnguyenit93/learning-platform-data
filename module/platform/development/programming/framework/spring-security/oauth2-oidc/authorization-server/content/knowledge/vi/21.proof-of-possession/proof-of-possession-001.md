# Bearer token và DPoP-bound access token

> **Chương: DPoP.** Bài học thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server. Bài tập trung vào sự khác nhau giữa **Bearer access token** và **DPoP-bound access token**, cơ chế ràng buộc token với khóa công khai, cách client chứng minh đang giữ khóa riêng và trách nhiệm xác minh của Authorization Server/Resource Server.

## 1. Vì sao Bearer token có rủi ro khi bị đánh cắp?

Trong OAuth 2.0, access token thường được gửi tới Resource Server qua HTTP header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.vn
Authorization: Bearer ACCESS_TOKEN_REDACTED
~~~

Bearer token có nghĩa là **bên nào sở hữu token đều có thể trình token để sử dụng**, miễn token còn hiệu lực và đáp ứng các chính sách khác. Resource Server không yêu cầu bên gửi request chứng minh token được cấp cho chính thiết bị hoặc ứng dụng đang gửi request.

Điều này rất thuận tiện cho tích hợp API, nhưng nếu token bị lộ qua log, browser storage, crash dump, proxy, telemetry hoặc máy trạm bị xâm nhập, attacker có thể dùng token từ một thiết bị khác. Chữ ký JWT hợp lệ chỉ chứng minh token được phát hành bởi issuer tin cậy và chưa bị sửa; nó **không chứng minh người gửi request đang giữ một bí mật riêng gắn với token**.

Ví dụ trong module:

- **Authorization Server:** `https://login.example.vn`.
- **Client:** `portal-web`, ứng dụng web hoặc BFF.
- **Resource Server:** `https://api.example.vn`.
- **Access token:** được cấp cho `portal-web` để gọi API với scope `orders.read`.
- **Tình huống:** token `A0` bị sao chép khỏi một log lỗi. Attacker gửi `A0` từ máy của họ trước khi token hết hạn.

Với Bearer token, Resource Server có thể chấp nhận request trên nếu chữ ký, issuer, audience, expiry và quyền đều hợp lệ. Resource Server không có bằng chứng rằng attacker đang dùng thiết bị/client ban đầu.

**DPoP (Demonstrating Proof of Possession, RFC 9449)** bổ sung một bằng chứng mật mã ở tầng ứng dụng: token được ràng buộc với một public key, còn client phải ký một DPoP Proof mới cho từng HTTP request bằng private key tương ứng. Token bị đánh cắp một mình vì thế không đủ để gọi API.

## 2. Bearer token và DPoP-bound access token khác nhau thế nào?

| Tiêu chí | Bearer access token | DPoP-bound access token |
|---|---|---|
| Điều kiện trình token | Sở hữu token là đủ ở tầng cơ chế Bearer | Phải có token và DPoP Proof hợp lệ chứng minh giữ private key đã ràng buộc |
| Authorization header | `Authorization: Bearer <token>` | `Authorization: DPoP <token>` |
| Proof riêng cho request | Không có | Có JWT trong header `DPoP` |
| Ràng buộc với khóa | Không có sender-binding trong cơ chế Bearer | `cnf.jkt` hoặc metadata introspection xác định thumbprint của public key |
| Chống sử dụng token bị đánh cắp riêng lẻ | Hạn chế bằng TTL, revocation và bảo vệ lưu trữ | Mạnh hơn: attacker còn cần private key tương ứng hoặc khả năng tạo proof |
| Chống replay proof | Không áp dụng vì không có proof | Dùng thời gian `iat`, `jti`, kiểm tra request và có thể dùng nonce/replay cache |
| Yêu cầu ở client | Quản lý token | Quản lý token, key pair và tạo proof mới cho mỗi request |
| Yêu cầu ở Resource Server | Xác minh token và authorization | Xác minh token, proof, key binding và authorization |
| Khả năng tương thích | Rộng, nhiều thư viện hỗ trợ mặc định | Client, Authorization Server và Resource Server đều phải hỗ trợ DPoP |
| Chi phí | Ít xử lý mật mã ở mỗi request | Thêm ký/xác minh proof và quản lý trạng thái chống replay |

Mô hình Bearer truyền thống:

~~~text
Client có ACCESS_TOKEN
        |
        v
Authorization: Bearer ACCESS_TOKEN
        |
        v
Resource Server xác minh token
        |
        v
Cho phép nếu token/quyền hợp lệ
~~~

Mô hình DPoP:

~~~text
Client có ACCESS_TOKEN + private key
        |
        +--> Tạo DPoP Proof cho HTTP request hiện tại
        |
        v
Authorization: DPoP ACCESS_TOKEN
DPoP: SIGNED_PROOF
        |
        v
Resource Server xác minh token + proof
        |
        +--> cnf.jkt khớp public key trong proof?
        +--> ath khớp access token?
        +--> htm/htu/iat/jti/nonce hợp lệ?
        |
        v
Cho phép nếu toàn bộ kiểm tra và authorization đều đạt
~~~

DPoP là cơ chế **sender-constraining** ở tầng ứng dụng. Nó không thay thế xác thực client, xác thực người dùng, scope, audience, authorization nghiệp vụ hoặc TLS. Một DPoP Proof hợp lệ chỉ chứng minh khả năng giữ khóa; bản thân proof không cấp quyền truy cập.

## 3. Các thành phần của DPoP

### 3.1. Cặp khóa của client

Client tạo một cặp khóa bất đối xứng:

- **Private key:** giữ trong môi trường client, dùng để ký DPoP Proof. Không gửi khóa riêng tới Authorization Server hoặc Resource Server.
- **Public key:** được đưa vào JOSE header của DPoP Proof dưới dạng JWK. Server dùng khóa này để xác minh chữ ký.
- **JWK Thumbprint:** giá trị SHA-256 được tính từ public JWK theo RFC 7638. Authorization Server dùng thumbprint này để ràng buộc access token với khóa.

Khóa DPoP là khóa của **client**, không phải khóa ký JWT access token của Authorization Server. Hai cặp khóa có mục đích khác nhau:

| Khóa | Chủ sở hữu | Dùng để |
|---|---|---|
| DPoP private key | OAuth client/thiết bị | Ký proof chứng minh possession |
| DPoP public key | Công khai trong proof | Xác minh proof và tính thumbprint |
| Authorization Server signing key | Authorization Server | Ký JWT access token/ID Token |
| Resource Server key (nếu có) | Resource Server | Không thay thế DPoP client key |

Không tái sử dụng private key ký access token của Authorization Server cho DPoP. Client nên tạo và bảo vệ khóa riêng theo vòng đời thiết bị/ứng dụng; với thiết bị hỗ trợ, ưu tiên keystore hoặc phần cứng bảo vệ khóa.

### 3.2. DPoP Proof là một JWT riêng cho HTTP request

Một DPoP Proof là JWT được ký bằng private key của client và gửi trong HTTP header `DPoP`. JOSE header phải có các trường cơ bản:

| Trường | Ý nghĩa |
|---|---|
| `typ` | Bắt buộc có giá trị `dpop+jwt` để xác định rõ loại proof |
| `alg` | Thuật toán chữ ký bất đối xứng được phép, ví dụ `ES256` hoặc `RS256`; không được dùng `none` hoặc thuật toán MAC đối xứng |
| `jwk` | Public JWK tương ứng với private key ký proof; không được chứa private key |

Payload proof phải có các claim:

| Claim | Ý nghĩa |
|---|---|
| `jti` | Định danh duy nhất của proof; hỗ trợ phát hiện replay |
| `htm` | HTTP method của request, ví dụ `GET` hoặc `POST` |
| `htu` | Target URI của request, không gồm query string và fragment |
| `iat` | Thời điểm proof được tạo (NumericDate) |
| `ath` | Hash của access token; bắt buộc khi proof được gửi cùng access token tới protected resource |
| `nonce` | Nonce do server cung cấp nếu server yêu cầu |

Ví dụ payload proof dùng tại token endpoint:

~~~json
{
  "jti": "dpop-proof-id-unique",
  "htm": "POST",
  "htu": "https://login.example.vn/oauth2/token",
  "iat": 1794825600
}
~~~

Ví dụ payload proof dùng khi gọi Resource Server:

~~~json
{
  "jti": "another-unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.vn/api/orders",
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN",
  "iat": 1794825610
}
~~~

Đây là payload minh họa, không phải JWT đã ký. Mỗi HTTP request cần một proof riêng; không cache và gửi lại cùng proof cho nhiều request. `ath` ràng buộc proof với đúng giá trị access token đang trình. `htm` và `htu` ràng buộc proof với method và target URI, giúp proof không thể được chuyển tùy tiện sang endpoint khác.

### 3.3. Vì sao `htu` bỏ query và fragment?

Theo RFC 9449, `htu` chứa HTTP target URI **không có query và fragment**. Ví dụ:

~~~text
Request URL:
https://api.example.vn/api/orders?status=open&page=2#result

htu trong DPoP Proof:
https://api.example.vn/api/orders
~~~

Method và target URI phải được chuẩn hóa/đối chiếu theo quy tắc RFC. Với hệ thống sau reverse proxy, Resource Server cần biết URL public thực sự mà client gọi. Không tin tùy tiện `X-Forwarded-Host` hoặc `X-Forwarded-Proto` từ nguồn không đáng tin; cấu hình trusted proxy để server tính `htu` đúng.

## 4. Luồng cấp DPoP-bound access token

DPoP không tạo grant type OAuth2 mới. Client vẫn dùng Authorization Code, Refresh Token, Client Credentials hoặc grant được hỗ trợ; điểm khác là client đính kèm DPoP Proof tại token endpoint để Authorization Server ràng buộc token được phát với public key.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server

    C->>C: Tạo key pair Kpriv/Kpub
    C->>AS: Token request + DPoP Proof(Kpriv, Kpub)
    AS->>AS: Xác minh proof, htm, htu, iat, jti, nonce
    AS->>AS: Tính JWK Thumbprint của Kpub
    AS->>AS: Phát access token gắn cnf.jkt
    AS-->>C: access_token + token_type=DPoP
    C->>C: Giữ access token và Kpriv
    C->>RS: Authorization: DPoP token + DPoP Proof mới
    RS->>RS: Xác minh access token và proof
    RS->>RS: So khớp cnf.jkt, ath, htm, htu, iat, jti
    RS-->>C: Trả tài nguyên nếu token và authorization hợp lệ
~~~

### 4.1. Request tại token endpoint

Ví dụ client đổi authorization code và dùng DPoP:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_CREDENTIALS_REDACTED
DPoP: SIGNED_DPOP_PROOF_REDACTED

grant_type=authorization_code&code=AUTHORIZATION_CODE_REDACTED&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&code_verifier=PKCE_VERIFIER_REDACTED
~~~

- Header `DPoP` chứa proof được ký bằng private key của client.
- `htm` phải là `POST` và `htu` phải khớp token endpoint public mà client đang gọi.
- Proof có `jti` mới, `iat` phù hợp và `nonce` nếu Authorization Server yêu cầu.
- `ath` được dùng khi proof gắn với access token đang trình tại protected resource; không phải claim cần để chứng minh request đổi code ở token endpoint.
- `Authorization: Basic` chỉ là ví dụ confidential client dùng `client_secret_basic`. DPoP không thay thế client authentication; public client có thể không có client secret.

Sau khi xác minh proof, Authorization Server tính thumbprint của public key và ràng buộc token với thumbprint đó. Response thành công báo loại token:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "DPOP_ACCESS_TOKEN_REDACTED",
  "token_type": "DPoP",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

Client phải đọc `token_type=DPoP` để sử dụng đúng authentication scheme khi gọi API. Không đổi scheme thành `Bearer` chỉ để tương thích một HTTP client cũ.

### 4.2. Thông tin ràng buộc trong access token

Với JWT access token, public key thumbprint được thể hiện qua claim `cnf.jkt`:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794825900,
  "cnf": {
    "jkt": "JWK_SHA256_THUMBPRINT"
  }
}
~~~

`cnf.jkt` không chứa private key hoặc toàn bộ public JWK; nó là thumbprint để Resource Server so sánh với public key trong DPoP Proof. Nếu access token là opaque/reference token, Resource Server có thể lấy thông tin binding qua token introspection. Theo RFC 9449, introspection response có thể trả `cnf.jkt`; Resource Server tự xác minh proof và binding, không gửi DPoP Proof trong request introspection.

## 5. Gọi Resource Server bằng DPoP-bound access token

Khi gọi API, client gửi **cả access token và proof mới**:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.vn
Authorization: DPoP DPOP_ACCESS_TOKEN_REDACTED
DPoP: SIGNED_DPOP_PROOF_WITH_ATH_REDACTED
~~~

Proof phải được tạo cho request này, có:

- `htm=GET`.
- `htu=https://api.example.vn/api/orders` (không có query/fragment).
- `iat` gần thời điểm gửi request.
- `jti` duy nhất.
- `ath` là Base64URL không padding của SHA-256 trên ASCII bytes của giá trị access token đang gửi.
- `nonce` nếu Resource Server yêu cầu.

### 5.1. Tính `ath` bằng Java

Ví dụ helper tính hash theo RFC 9449:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

final class DPoPProofSupport {

    private DPoPProofSupport() {
    }

    static String accessTokenHash(String accessToken)
            throws NoSuchAlgorithmException {

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(accessToken.getBytes(StandardCharsets.US_ASCII));

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
    }
}
~~~

Không hash chuỗi đã URL-encode, không dùng UTF-8 thay ASCII cho giá trị token và không đưa access token nguyên văn vào claim proof. `ath` được ký cùng proof nên Resource Server có thể xác nhận proof gắn với đúng token.

### 5.2. Các kiểm tra tại Resource Server

Resource Server phải kiểm tra cả access token và DPoP Proof:

1. **Access token:** chữ ký hoặc introspection, issuer, audience, expiry, scope, trạng thái active và authorization nghiệp vụ.
2. **Proof JWT:** chữ ký bằng public JWK, `typ=dpop+jwt`, thuật toán bất đối xứng nằm trong allowlist.
3. **Request binding:** `htm` và `htu` khớp request thực tế.
4. **Token binding:** JWK thumbprint của proof public key khớp `cnf.jkt` của access token.
5. **Token hash:** `ath` khớp SHA-256 của access token được gửi.
6. **Freshness/replay:** `iat` nằm trong cửa sổ thời gian chấp nhận; `jti` chưa bị dùng lại trong phạm vi replay detection.
7. **Nonce:** nếu Resource Server yêu cầu nonce, proof phải chứa nonce mới/đúng do chính Resource Server cấp.

Chỉ khi toàn bộ kiểm tra đạt, Resource Server mới tiếp tục authorization theo scope và quyền trên tài nguyên. DPoP không thay kiểm tra quyền API.

## 6. Tạo DPoP Proof bằng Nimbus và Spring Security

Ví dụ sau minh họa cấu trúc dùng `NimbusJwtEncoder` để ký proof. Khóa trong ví dụ là khóa của **OAuth Client**; production phải lấy khóa riêng từ keystore/hardware-backed storage hoặc cơ chế bảo vệ phù hợp, không tạo một khóa dùng chung trong source code.

### 6.1. Tạo proof cho token endpoint

~~~java
import java.time.Instant;
import java.util.UUID;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;

import org.springframework.security.oauth2.jose.jws.JwsHeader;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

final class DPoPProofFactory {

    private final JwtEncoder encoder;
    private final RSAKey dpopKey;

    DPoPProofFactory(RSAKey dpopKey) {
        this.dpopKey = dpopKey;

        JWKSource<SecurityContext> jwkSource =
                (selector, context) -> selector.select(new JWKSet(dpopKey));

        this.encoder = new NimbusJwtEncoder(jwkSource);
    }

    Jwt createTokenEndpointProof(String method, String tokenEndpoint) {
        JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
                .type("dpop+jwt")
                .jwk(dpopKey.toPublicJWK().toJSONObject())
                .build();

        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuedAt(Instant.now())
                .claim("htm", method.toUpperCase())
                .claim("htu", tokenEndpoint)
                .id(UUID.randomUUID().toString())
                .build();

        return this.encoder.encode(
                JwtEncoderParameters.from(header, claims));
    }
}
~~~

Đây là ví dụ cho proof tại token endpoint, chưa bao gồm nonce challenge, replay store phía server hoặc quản lý vòng đời key. `tokenEndpoint` phải là URL public mà client gọi, ví dụ `https://login.example.vn/oauth2/token`. Không tự suy URL từ header proxy không đáng tin.

### 6.2. Tạo proof cho protected resource

Với resource request, tạo proof mới và thêm `ath`:

~~~java
JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuedAt(Instant.now())
        .claim("htm", "GET")
        .claim("htu", "https://api.example.vn/api/orders")
        .claim("ath", DPoPProofSupport.accessTokenHash(accessToken))
        .id(UUID.randomUUID().toString())
        .build();

JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
        .type("dpop+jwt")
        .jwk(dpopKey.toPublicJWK().toJSONObject())
        .build();

Jwt proof = jwtEncoder.encode(JwtEncoderParameters.from(header, claims));
~~~

Đoạn code chỉ minh họa claims và header; helper ký token cần được xây dựng với cùng private key client như ví dụ trước. Mỗi request cần `jti` khác nhau. Không tái sử dụng proof từ request trước, kể cả request trước trả lỗi mạng.

## 7. Nonce và chống replay

DPoP Proof có `jti` duy nhất và `iat` để giới hạn khả năng sử dụng lại. Server phải giới hạn thời gian chấp nhận proof (thường chỉ trong khoảng giây hoặc phút). Server có thể lưu `jti` đã thấy trong cửa sổ đó để từ chối proof replay.

### 7.1. Replay cache

Một Resource Server nhiều instance cần suy nghĩ về chia sẻ trạng thái replay:

- Lưu hash của `jti` cùng issuer/resource context trong TTL ngắn.
- Khi nhận proof, kiểm tra `jti` chưa tồn tại và ghi nhận theo thao tác atomic.
- Nếu đã có, từ chối request.
- TTL của replay record không vượt quá cửa sổ mà proof còn được chấp nhận.
- Giới hạn kích thước `jti` và số record để tránh memory exhaustion.
- Nếu các node không chia sẻ replay state, một proof có thể được gửi tới node khác; cần đánh giá nguy cơ và thiết kế storage phù hợp.

DPoP ràng buộc proof với method và URI, nhưng một proof bị đánh cắp vẫn có thể bị phát lại tại **cùng endpoint, cùng method** trong thời gian nó còn được chấp nhận nếu server không phát hiện replay.

### 7.2. Server-provided nonce

Authorization Server hoặc Resource Server có thể yêu cầu nonce. Server gửi header `DPoP-Nonce`; client thêm giá trị này vào claim `nonce` của proof tiếp theo.

Ví dụ khi Authorization Server yêu cầu nonce:

~~~http
HTTP/1.1 400 Bad Request
DPoP-Nonce: SERVER_NONCE_VALUE

{
  "error": "use_dpop_nonce",
  "error_description": "Authorization Server requires a nonce"
}
~~~

Client phải tạo **proof mới** có nonce mới và gửi lại request theo đúng hướng dẫn. Không sửa payload của proof đã ký hoặc dùng lại cùng proof với nonce mới.

Nonce do Authorization Server cấp chỉ dùng với Authorization Server đó; nonce của Resource Server chỉ dùng với Resource Server đã cấp. Không nhầm DPoP nonce với OIDC `nonce` trong ID Token. Với browser client dùng CORS, nếu JavaScript cần đọc header `DPoP-Nonce` thì server phải expose header đó trong CORS response.

## 8. DPoP kết hợp Authorization Code, PKCE và PAR

DPoP và PKCE bảo vệ các giai đoạn khác nhau:

| Cơ chế | Bảo vệ |
|---|---|
| PKCE | Ràng buộc authorization code với `code_verifier` để giảm code interception/injection |
| DPoP | Ràng buộc access token (và có thể refresh token) với khóa của client |
| `state` | Liên kết authorization response với giao dịch client đã khởi tạo, chống CSRF/nhầm giao dịch |
| OIDC `nonce` | Liên kết ID Token với giao dịch đăng nhập OIDC |
| `dpop_jkt` | Tùy chọn ràng buộc authorization code với thumbprint của DPoP public key |

### 8.1. Authorization code binding với `dpop_jkt`

Client có thể gửi tham số `dpop_jkt` trong authorization request. Giá trị là JWK SHA-256 Thumbprint của public key DPoP mà client dự định sử dụng. Khi token request tới, Authorization Server tính thumbprint từ public key trong DPoP Proof và so sánh với `dpop_jkt` đã lưu. Nếu không khớp, server phải từ chối token request.

Ví dụ:

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=orders.read&state=STATE_VALUE&code_challenge=PKCE_CHALLENGE&code_challenge_method=S256&dpop_jkt=PUBLIC_KEY_THUMBPRINT
Host: login.example.vn
~~~

`dpop_jkt` là tùy chọn theo RFC 9449. Có thể kết hợp với PKCE; khi dùng, nên tạo khóa DPoP riêng cho từng authorization request nếu muốn có ràng buộc tương tự PKCE đối với key. DPoP không thay PKCE.

### 8.2. Kết hợp PAR

Nếu dùng Pushed Authorization Requests (PAR), client có thể đưa `dpop_jkt` trong POST body của PAR request. Một cách khác là gửi header `DPoP` trên PAR request; Authorization Server xác minh proof và coi thumbprint trong proof như `dpop_jkt` đã được cung cấp. Nếu dùng cả hai, hai thumbprint phải khớp.

Điều này giúp ràng buộc cả authorization code với khóa DPoP ngay từ bước khởi tạo authorization, sau đó token endpoint phải nhận proof từ đúng khóa đó.

## 9. DPoP với refresh token

DPoP có thể ràng buộc refresh token, đặc biệt hữu ích cho public client không có client secret. Theo RFC 9449, nếu Authorization Server phát refresh token cho public client, refresh token cũng được ràng buộc với public key DPoP.

Khi refresh:

1. Client gửi `grant_type=refresh_token` và refresh token qua HTTPS.
2. Client tạo proof mới cho token endpoint, với `htm=POST`, `htu` đúng endpoint, `iat`, `jti` và nonce nếu yêu cầu.
3. Authorization Server kiểm tra proof và xác minh khóa khớp binding của refresh token.
4. Nếu hợp lệ, server phát access token mới được ràng buộc theo DPoP; chính sách refresh token rotation vẫn được áp dụng độc lập.
5. Client tiếp tục tạo proof mới cho mỗi lần gọi Resource Server.

DPoP không loại bỏ nhu cầu rotation, replay detection, TTL và revocation cho refresh token. Nếu private key bị lộ, attacker có thể tạo proof; cần quy trình thu hồi token/key binding và cấp authorization mới.

## 10. DPoP và các cơ chế bảo vệ khác

| Cơ chế | Binding ở đâu? | Điểm mạnh | Khác biệt với DPoP |
|---|---|---|---|
| Bearer token | Không sender-binding | Đơn giản, tương thích rộng | Ai có token đều có thể trình token |
| DPoP | Tầng HTTP/application, gắn với public key | Phù hợp SPA/native client; không cần client certificate | Cần proof JWT cho từng request; không ký toàn bộ request body/header |
| mTLS-bound token | Tầng TLS/certificate | Ràng buộc token với client certificate ở kết nối TLS | Yêu cầu hạ tầng mutual TLS và quản lý certificate |
| PKCE | Authorization code exchange | Chống code interception/injection | Không ràng buộc access token sau khi phát hành |
| Client authentication | Danh tính OAuth client tại AS | Xác minh client theo secret/private key/certificate | DPoP không phải client authentication |
| TLS | Kênh truyền | Bảo mật dữ liệu trên đường truyền | DPoP không thay thế TLS; vẫn cần HTTPS |

DPoP thường phù hợp khi client chạy trong browser/native app và khó triển khai mTLS. mTLS có thể phù hợp với service-to-service trong hạ tầng kiểm soát certificate tốt. Hai cơ chế có thể cùng xuất hiện theo policy, nhưng cần hiểu rõ binding nào đang được Resource Server xác minh.

## 11. Giới hạn bảo mật và threat model

DPoP giảm rủi ro **đánh cắp access token đơn lẻ**, nhưng không giải quyết mọi kiểu tấn công:

- **XSS hoặc mã độc trong client context:** attacker có thể gọi API ký bằng key trong khi ứng dụng còn chạy, kể cả key không exportable. Cần CSP, chống XSS, dependency review và bảo vệ runtime.
- **Private key bị đánh cắp:** attacker có token và private key có thể tạo proof hợp lệ. Cần keystore/HSM, hạn chế export, rotate/revoke khi compromise.
- **Proof bị replay:** proof bị đánh cắp có thể phát lại trong thời gian ngắn ở cùng endpoint/method nếu server không phát hiện `jti` đã dùng. Cần freshness, replay cache và nonce theo threat model.
- **Request body/header bị sửa:** DPoP ràng buộc method và URI, không ký toàn bộ body hoặc tất cả HTTP headers. TLS vẫn cần để bảo vệ tính toàn vẹn và bí mật của request.
- **Sai URL sau reverse proxy:** nếu client ký public URI nhưng server so với internal URI hoặc ngược lại, request hợp lệ có thể bị từ chối; nếu tin forwarded header sai, attacker có thể gây bypass hoặc DoS.
- **Key sharing quá rộng:** nhiều thiết bị cùng dùng một private key làm tăng blast radius khi một thiết bị bị compromise và làm khó thu hồi riêng.
- **Downgrade sang Bearer:** Resource Server không được chấp nhận token DPoP-bound như Bearer chỉ để “tương thích”. Cần tôn trọng token type và confirmation binding.
- **Authorization sai:** proof hợp lệ không có nghĩa user có quyền đọc/sửa dữ liệu. Resource Server vẫn phải kiểm tra scope, role, tenant, audience và quyền trên đối tượng.
- **Mất private key:** client không thể tiếp tục dùng token đã ràng buộc với khóa cũ; cần cấp authorization/token mới theo quy trình.

DPoP là một lớp bảo vệ bổ sung cho bearer credential, không phải lý do để lưu token lâu hơn, bỏ TLS hoặc bỏ kiểm soát quyền.

## 12. Tích hợp với Spring Authorization Server và Spring Security

### 12.1. Spring Authorization Server

Spring Authorization Server **1.5.x** bổ sung hỗ trợ DPoP theo RFC 9449. Token endpoint nhận DPoP Proof trong header `DPoP`; khi proof hợp lệ, server ràng buộc public key với access token và trả `token_type=DPoP`. Với JWT access token, binding được biểu diễn trong `cnf.jkt`; với opaque token, Resource Server có thể lấy thông tin qua introspection.

Khung filter chain cho Authorization Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
                .with(authorizationServer, Customizer.withDefaults())
                .authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

Đây là khung cấu hình filter chain. DPoP được xử lý trong token endpoint của phiên bản hỗ trợ; ứng dụng vẫn cần RegisteredClient, AuthorizationServerSettings, authorization/token services, JWK signing cho JWT, client authentication và user authentication. Không tự tạo controller token endpoint thay thế filter/provider chuẩn.

Kiểm tra metadata Authorization Server theo RFC 9449. Trường `dpop_signing_alg_values_supported` công bố các thuật toán JWS được hỗ trợ để ký DPoP Proof. Đừng tự thêm metadata quảng cáo một thuật toán mà token endpoint thực tế không chấp nhận.

### 12.2. Spring Security Resource Server

Spring Security **7.1 trở lên** cung cấp DSL cấu hình DPoP cho Resource Server. Ví dụ khi dùng JWT access token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/health").permitAll()
                    .anyRequest().authenticated())
                .oauth2ResourceServer(resourceServer -> resourceServer
                    .jwt(Customizer.withDefaults())
                    .dPoP(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ví dụ giả định JWT decoder đã được cấu hình (ví dụ qua issuer URI hoặc bean tương ứng) và dependency version có DSL DPoP. Với opaque token, cấu hình introspection và DPoP theo đúng API phiên bản đang dùng; introspection response cần cung cấp confirmation claim `cnf.jkt`.

**Lưu ý tương thích:** Spring Authorization Server 1.5.x có hỗ trợ phát DPoP-bound access token; DSL Resource Server DPoP được Spring Security bổ sung từ **7.1**. Nếu dự án đang dùng Spring Security 6.x, không copy nguyên ví dụ DSL trên rồi giả định API tồn tại. Hãy kiểm tra BOM/dependency alignment và API của phiên bản Spring Boot/Security/SAS thực tế; có thể cần nâng cấp stack đồng bộ hoặc cấu hình extension point phù hợp.

### 12.3. Phía OAuth2 Client

Client phải tạo proof cho cả token request và protected resource request. Không mặc định rằng chỉ bật `oauth2Login()` hoặc `oauth2Client()` là thư viện tự tạo DPoP Proof, quản lý private key, xử lý nonce và gắn `ath`.

Khi tích hợp:

- Dùng thư viện client có hỗ trợ DPoP rõ ràng, hoặc xây lớp HTTP client/interceptor có quản lý key và proof đúng RFC.
- Đảm bảo proof ở token endpoint và Resource Server dùng cùng public key đã ràng buộc token.
- Tạo proof mới cho từng request; không retry request bằng proof cũ.
- Xử lý `DPoP-Nonce` và lỗi `use_dpop_nonce`.
- Không đưa private key vào cấu hình plaintext, browser local storage hoặc log.
- Với SPA, bảo vệ execution context và dùng Web Crypto/keystore theo khả năng nền tảng; key không exportable không ngăn XSS gọi API ký.

## 13. Kiểm thử Bearer và DPoP-bound token

Một bộ test tốt cần chứng minh **token bị đánh cắp riêng lẻ không đủ** và Resource Server thực thi đúng binding. Dùng key/token giả ở staging, không ghi raw credential vào log.

| Ca | Thao tác | Kết quả mong đợi |
|---|---|---|
| 1 | Gọi API bằng Bearer token hợp lệ với Resource Server Bearer | Được chấp nhận theo scope/policy |
| 2 | Gọi API bằng DPoP token và proof hợp lệ | Được chấp nhận |
| 3 | Gửi DPoP token nhưng thiếu header `DPoP` | Từ chối |
| 4 | Gửi DPoP token với scheme `Bearer` | Không được chấp nhận như Bearer |
| 5 | Proof ký bằng key khác | Từ chối do thumbprint không khớp `cnf.jkt` |
| 6 | Sửa payload proof nhưng giữ chữ ký cũ | Từ chối chữ ký |
| 7 | `typ` khác `dpop+jwt` | Từ chối |
| 8 | Gửi `alg=none` hoặc MAC đối xứng | Từ chối |
| 9 | `htm` không khớp HTTP method | Từ chối |
| 10 | `htu` không khớp target URI | Từ chối |
| 11 | Thiếu `ath` tại protected resource | Từ chối |
| 12 | `ath` được tính từ token khác | Từ chối |
| 13 | `iat` quá cũ hoặc ngoài cửa sổ | Từ chối |
| 14 | Gửi lại cùng `jti`/proof | Từ chối theo replay policy |
| 15 | Server yêu cầu nonce nhưng proof không có nonce | Trả challenge `use_dpop_nonce`/nonce theo policy |
| 16 | Gửi nonce cũ hoặc nonce từ server khác | Từ chối |
| 17 | Access token hết hạn hoặc sai audience | Từ chối dù proof đúng |
| 18 | Proof đúng nhưng scope không đủ | Từ chối authorization |
| 19 | Public client refresh token bằng key sai | Từ chối |
| 20 | Authorization Code có `dpop_jkt` nhưng token proof key khác | Từ chối |
| 21 | DPoP qua reverse proxy | `htu` được so khớp với public URI chính xác |
| 22 | Nhiều Resource Server instance | Replay detection hoạt động theo thiết kế cluster |
| 23 | XSS mô phỏng gọi WebCrypto sign | Đánh giá được giới hạn bảo vệ; không giả định DPoP chặn được mã chạy trong origin |
| 24 | Mất private key | Client không thể dùng token binding cũ; cần authorization mới |

### 13.1. Kiểm tra token response và JWT claim

Sau khi đổi token thành công, xác minh:

- Response có `token_type=DPoP`.
- JWT access token có `cnf.jkt` và thumbprint khớp public key client.
- Opaque token introspection trả `cnf.jkt` theo contract.
- `iss`, `aud`, `exp`, scope và subject vẫn đúng.
- Không có private key hoặc secret trong access token.

Không chỉ decode JWT để đọc claims; trong test phải xác minh chữ ký và issuer trước khi tin payload.

### 13.2. Kiểm thử replay và nonce

Dùng một proof có `jti` cố định gửi hai lần trong cửa sổ thời gian chấp nhận. Request đầu có thể thành công; request thứ hai phải bị phát hiện replay nếu server triển khai replay cache. Kiểm tra cả trường hợp hai request tới hai node khác nhau.

Với nonce, test luồng: server trả `DPoP-Nonce` → client tạo proof mới với claim `nonce` → gửi lại → server chấp nhận nếu nonce còn hợp lệ. Không tái sử dụng proof cũ khi nhận nonce mới.

## 14. Troubleshooting và checklist vận hành

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Token endpoint trả `invalid_dpop_proof` | Sai chữ ký, typ/alg/JWK, `htm`/`htu` hoặc `iat` | Decode proof trong môi trường test, kiểm tra key và public URL |
| Token response vẫn là `Bearer` | Client không gửi proof, proof không được xử lý hoặc server/version không hỗ trợ | Kiểm tra header DPoP, token endpoint và version |
| Resource Server trả 401 | Thiếu proof, sai authentication scheme hoặc token invalid | Dùng `Authorization: DPoP` và proof mới |
| `cnf.jkt` không khớp | Client đổi key sau khi token được phát hoặc gửi nhầm key | Dùng đúng private key đã binding; cấp token mới nếu key thay |
| `ath` mismatch | Hash token sai encoding hoặc proof tạo cho token khác | Hash ASCII access token, Base64URL không padding |
| `htu` mismatch sau proxy | App nhìn thấy internal URI thay vì external URI | Cấu hình trusted forwarded headers và canonical public URL |
| `use_dpop_nonce` lặp lại | Client không cập nhật nonce hoặc dùng nonce sai server | Lưu nonce theo issuer/resource server và tạo proof mới |
| Một proof dùng được nhiều lần ở các pod | Replay cache không chia sẻ hoặc chưa bật | Thiết kế shared replay store/nonce và TTL |
| Spring Resource Server không nhận DSL DPoP | Spring Security version trước 7.1 hoặc dependency lệch | Kiểm tra BOM và API version |
| XSS vẫn gọi API thành công | Mã độc chạy trong client context có thể yêu cầu key ký proof | Chống XSS, CSP, giảm third-party code, bảo vệ key |

### 14.1. Checklist production

- [ ] Chọn DPoP cho client/API có rủi ro token theft phù hợp; đánh giá tương thích của client, AS và RS.
- [ ] Private key được tạo và bảo vệ ở client; public JWK trong proof không chứa private parameters.
- [ ] Proof JWT có `typ=dpop+jwt`, asymmetric `alg` được allowlist, `jwk` public, `jti`, `htm`, `htu` và `iat`.
- [ ] Mỗi HTTP request có proof mới, `jti` không lặp và thời gian proof nằm trong cửa sổ ngắn.
- [ ] Proof tại protected resource có `ath` hash chính xác của access token.
- [ ] Access token có binding `cnf.jkt` hoặc thông tin introspection tương đương; Resource Server so khớp thumbprint.
- [ ] DPoP token chỉ được gửi bằng authentication scheme `DPoP`; không downgrade sang Bearer.
- [ ] Nonce challenge được xử lý đúng và tách riêng theo từng AS/RS.
- [ ] Replay cache/nonce state hoạt động khi chạy nhiều instance.
- [ ] TLS vẫn được bật; DPoP không được xem là cơ chế bảo vệ body/header hoặc thay TLS.
- [ ] PKCE, state, client authentication, audience, scope và authorization nghiệp vụ vẫn được kiểm tra.
- [ ] Có quy trình key rotation, key compromise, token revocation và cấp authorization mới.
- [ ] Kiểm thử XSS và lưu trữ key, đặc biệt với SPA/browser client.
- [ ] Phiên bản Spring Authorization Server và Spring Security được căn chỉnh; xác minh behavior thực tế thay vì chỉ dựa vào code mẫu.
- [ ] Không ghi access token, refresh token, DPoP proof, private key hoặc Authorization header vào log.

**Câu hỏi tự kiểm tra**

1. Vì sao Bearer token có thể bị sử dụng bởi bất kỳ ai có được chuỗi token?
2. DPoP-bound access token được ràng buộc với public key bằng claim nào?
3. Vì sao DPoP Proof phải có `typ=dpop+jwt` và thuật toán chữ ký bất đối xứng?
4. Khác nhau giữa `jti`, `ath`, `htm` và `htu` là gì?
5. Vì sao `ath` chỉ bắt buộc khi proof được gửi cùng access token tới protected resource?
6. Vì sao DPoP Proof không phải client authentication?
7. DPoP nonce khác OIDC ID Token nonce như thế nào?
8. DPoP có ngăn XSS trong origin của SPA gọi API thay người dùng không?
9. Vì sao DPoP không thay thế TLS và PKCE?
10. Nếu Resource Server dùng nhiều pod, cần làm gì để phát hiện cùng proof bị replay?
11. `dpop_jkt` ràng buộc authorization code với khóa DPoP ra sao?
12. Vì sao không được gửi DPoP-bound access token bằng scheme `Bearer`?

## Tài liệu tham khảo

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): proof JWT, public key confirmation, access token binding, nonce, replay, `dpop_jkt` và bảo mật.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): cách sử dụng Bearer access token và rủi ro bearer credential.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638.html): cách tính thumbprint của public JWK.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): so sánh cơ chế certificate-bound token.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html): PKCE và authorization code binding.
- [Spring Authorization Server — Protocol Endpoints: DPoP-bound Access Tokens](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): phát DPoP-bound access token và claim `cnf.jkt`.
- [Spring Authorization Server 1.5 GA](https://spring.io/blog/2025/05/20/spring-authorization-server-1-5-goes-ga/): hỗ trợ DPoP được bổ sung trong dòng 1.5.
- [Spring Security — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): xác minh DPoP proof và DPoP Resource Server.
- [Spring Security — OAuth2 Resource Server API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html): DSL cấu hình DPoP và phiên bản hỗ trợ.
