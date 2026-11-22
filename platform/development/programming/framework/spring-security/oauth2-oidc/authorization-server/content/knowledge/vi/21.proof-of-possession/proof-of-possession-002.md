# Cấu trúc DPoP proof, khóa của client và public JWK

## 1. DPoP ràng buộc access token với khóa của client như thế nào?

Trong OAuth 2.0 Bearer Token, bất kỳ bên nào sở hữu access token đều có thể thử dùng token đó trong thời hạn hiệu lực. Nếu token bị lộ qua log, bộ nhớ, trình duyệt hoặc một dịch vụ trung gian, kẻ lấy được token có thể sử dụng nó từ một môi trường khác.

**Demonstrating Proof of Possession (DPoP)** theo RFC 9449 bổ sung một bằng chứng mật mã ở cấp HTTP. Client sở hữu một cặp khóa bất đối xứng, giữ private key và gửi một **DPoP proof** được ký cho từng HTTP request. Authorization Server hoặc Resource Server xác minh chữ ký bằng public JWK nằm trong JOSE header của proof. Access token được ràng buộc với thumbprint của public key đó.

Vì vậy, người chỉ lấy được access token nhưng không có private key tương ứng không thể tạo proof hợp lệ cho request mới.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Tạo key pair (private/public)
    C->>AS: Token request + DPoP proof ký bằng private key
    AS->>AS: Xác minh proof, tính JWK thumbprint
    AS->>AS: Phát hành access token có cnf.jkt
    AS-->>C: DPoP-bound access token
    C->>RS: Authorization: DPoP + token, DPoP proof mới
    RS->>RS: Kiểm tra proof, ath, htm, htu, iat, jti
    RS->>RS: So sánh JWK thumbprint với cnf.jkt
    RS-->>C: Chấp nhận hoặc từ chối request
~~~

Bài thuộc chương **Proof of Possession** của module học thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server. Trọng tâm là **cấu trúc DPoP proof, cặp khóa client và public JWK**; từ đó người học hiểu vì sao proof gắn với đúng HTTP request và vì sao token đầu ra cần claim `cnf.jkt`.

DPoP không thay thế TLS, xác thực người dùng, scope, audience hay authorization nghiệp vụ. Nó bổ sung bằng chứng client đang nắm private key tương ứng với public key mà access token đã ràng buộc.

## 2. Ba thành phần phải phân biệt

| Thành phần | Nội dung | Bí mật? | Vai trò |
| --- | --- | --- | --- |
| **Private key của client** | Khóa ký proof | **Có** | Tạo chữ ký cho DPoP proof |
| **Public JWK** | Biểu diễn public key theo JSON Web Key | Không | Được đưa vào proof để server xác minh chữ ký |
| **JWK thumbprint** | Giá trị băm chuẩn hóa từ các thành phần bắt buộc của JWK | Không | Ràng buộc access token với public key qua `cnf.jkt` |
| **DPoP proof JWT** | JWT ký số cho một HTTP request cụ thể | Chữ ký và payload có thể quan sát; không chứa private key | Chứng minh possession và ràng buộc method/URI/thời gian |
| **Access token** | Credential được AS phát hành | Nhạy cảm | Mang quyền truy cập và thông tin key confirmation |

**Không nhầm public JWK với proof JWT.** JWK chỉ mô tả public key. Proof JWT là thông điệp đã ký chứa các claim về request. Server cần cả hai: JWK để xác minh chữ ký, claims để xác định proof áp dụng cho request nào và có còn hợp lệ hay không.

Cũng không nhầm `cnf.jkt` với `kid`:
- `kid` là một key identifier tùy chọn trong JOSE/JWK, thường giúp lựa chọn khóa.
- `jkt` là JWK thumbprint, có semantics mật mã xác định theo RFC 7638.
- DPoP binding của access token dùng `cnf.jkt` để biểu diễn public key đã được AS gắn với token.

## 3. Cấu trúc một DPoP proof JWT

DPoP proof là một **signed JWT (JWS Compact Serialization)**. Header thường có ba thành phần quan trọng:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "BASE64URL_PUBLIC_X",
    "y": "BASE64URL_PUBLIC_Y"
  }
}
~~~

Payload ở Resource Server có thể có dạng:

~~~json
{
  "jti": "unique-proof-id-7e91",
  "htm": "GET",
  "htu": "https://api.example.com/orders/42",
  "iat": 1794823200,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

Đây là payload minh họa. Giá trị thời gian, key coordinates và token hash phải được tạo thực tế; không sử dụng literal minh họa trong production.

### 3.1. JOSE header

| Header parameter | Yêu cầu / ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| `typ` | Giá trị DPoP proof là `dpop+jwt` | Phải đúng loại proof; không nhầm với JWT access token |
| `alg` | Thuật toán chữ ký bất đối xứng | Không chấp nhận `none` hoặc thuật toán MAC đối xứng như HS256 |
| `jwk` | Public JWK tương ứng private key ký proof | Phải chỉ chứa public key material; không được có private parameters |
| `kid` | Có thể dùng làm key identifier theo profile | Không thay thế xác minh chữ ký hay thumbprint |

DPoP proof không dùng một shared secret mà cả client và server cùng biết để tạo MAC. Mục tiêu là chứng minh client đang nắm **private key**, do đó server chỉ nhận các thuật toán chữ ký bất đối xứng nằm trong allowlist của mình.

Public JWK trong proof phải được kiểm tra đúng loại và cấu trúc. Không được nhận private parameters như `d` của EC/OKP/RSA, hoặc `p`, `q`, `dp`, `dq`, `qi`, `oth` của RSA. Private key tuyệt đối không được gửi tới Authorization Server hoặc Resource Server.

### 3.2. Các claim bắt buộc trong proof

| Claim | Ý nghĩa | Quy tắc xác minh |
| --- | --- | --- |
| `jti` | Định danh duy nhất của proof JWT | Dùng phát hiện proof replay; mỗi request tạo proof mới |
| `htm` | HTTP method của request | Phải khớp method thực tế, ví dụ `GET`, `POST` |
| `htu` | HTTP target URI | Phải khớp URI request theo quy tắc chuẩn hóa; không chứa query hoặc fragment |
| `iat` | Thời điểm proof được tạo (NumericDate) | Phải nằm trong cửa sổ thời gian được chấp nhận |
| `ath` | Hash của access token | Bắt buộc khi proof được gửi cùng access token tới Resource Server |

Một proof dùng ở token endpoint thường **không có `ath`** vì request đang xin token, chưa trình access token để gọi API. Khi client trình access token ở Resource Server, proof phải chứa `ath` tính từ đúng access token được gửi cùng request.

### 3.3. Claim nonce

`nonce` là claim tùy chọn do server cấp để ràng buộc proof với một challenge gần thời điểm request. Authorization Server hoặc Resource Server có thể trả header `DPoP-Nonce`; client phải đưa nonce đó vào proof tiếp theo khi server yêu cầu.

Nonce giúp giảm khả năng attacker chuẩn bị proof trước rồi sử dụng sau. Nó không thay thế `jti`, `iat` hoặc kiểm tra chữ ký. Server phải có policy về nonce theo từng issuer/resource, thời hạn và cách xử lý nonce sai/hết hạn.

## 4. Ý nghĩa chính xác của htm, htu, iat, jti và ath

### 4.1. htm — HTTP method

`htm` là method của HTTP request mà proof bảo vệ. Ví dụ:
- Request đọc tài nguyên: `GET`.
- Request tạo đơn: `POST`.
- Request cập nhật: `PUT` hoặc `PATCH`.

Giá trị phải phản ánh method thực tế. Nếu proof được tạo cho `GET` nhưng client gửi request `POST`, server phải từ chối. Không dùng một proof chung cho mọi method.

### 4.2. htu — HTTP target URI

`htu` là URI đích của HTTP request, **không bao gồm query string và fragment**. Ví dụ:

~~~text
Actual request:
https://api.example.com/orders/42?expand=items#details

DPoP htu:
https://api.example.com/orders/42
~~~

Server cần so sánh theo quy tắc URI normalization của RFC 9449/RFC 3986 và cấu hình deployment. Phải tính đến scheme, host, port và path thực tế. Không lấy URI từ header `Host` hoặc `Forwarded` chưa được proxy tin cậy kiểm soát.

Trong môi trường reverse proxy/load balancer, ứng dụng có thể nhìn thấy URI nội bộ như `http://service:8080` trong khi client gọi `https://api.example.com`. Cần cấu hình trusted proxy và external base URL chính xác. Nếu không, proof hợp lệ có thể bị từ chối hoặc attacker có thể khai thác việc server tin header proxy giả mạo.

### 4.3. iat — thời điểm tạo proof

`iat` là NumericDate. Server thường chấp nhận proof trong một cửa sổ thời gian ngắn để hạn chế việc lưu lại và phát lại proof. Cần xác định:
- Clock skew cho client/server.
- Maximum proof age.
- Mức cho phép timestamp ở tương lai.
- Cách đồng bộ NTP trên các node.

Cửa sổ quá rộng làm proof bị đánh cắp có thêm thời gian để replay; quá hẹp khiến request lỗi khi đồng hồ client lệch hoặc mạng chậm.

### 4.4. jti — định danh duy nhất và chống replay

Mỗi proof phải có `jti` riêng, không tái sử dụng cùng một proof JWT cho request khác. Server có thể lưu replay marker theo tổ hợp key thumbprint và `jti` trong khoảng thời gian proof còn được chấp nhận.

Ví dụ logic:

~~~text
replay_key = (jkt, jti)
if replay_cache.contains(replay_key):
    reject proof
else:
    replay_cache.put(replay_key, expiry = proof_acceptance_window)
~~~

Đây là pseudocode. Cache phải dùng chung hoặc có semantics nhất quán khi Resource Server chạy nhiều instance. Nếu mỗi node có replay cache riêng, attacker có thể gửi cùng proof đến node khác và vượt kiểm tra replay.

### 4.5. ath — hash của access token

Khi DPoP proof được gửi kèm access token tới Resource Server, claim `ath` ràng buộc proof với đúng token đó:

~~~text
ath = BASE64URL-ENCODE(
        SHA-256(ASCII(access_token))
      )
~~~

Base64URL ở đây bỏ padding (`=`). Hash tính trên **chuỗi access token thực tế** trong header Authorization, không phải decoded JWT payload, token ID hoặc refresh token.

Nếu attacker thay access token trong header nhưng giữ nguyên proof, `ath` sẽ không khớp. Nếu client tạo proof cho token A nhưng gửi token B, Resource Server phải từ chối.

## 5. Public JWK và cách tính thumbprint

### 5.1. JWK là gì?

JSON Web Key (RFC 7517) biểu diễn một khóa mật mã bằng JSON. Với DPoP, public key được đưa trong JOSE header `jwk` để server xác minh chữ ký proof.

Ví dụ EC P-256:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "PUBLIC_X_COORDINATE",
  "y": "PUBLIC_Y_COORDINATE"
}
~~~

Trong đó:
- `kty`: loại khóa, ở đây là Elliptic Curve.
- `crv`: đường cong, ví dụ `P-256`.
- `x` và `y`: tọa độ public key được mã hóa Base64URL.
- Không có `d`: `d` là private scalar của EC key và không được đưa vào public JWK.

Một RSA public JWK có `kty=RSA`, `n` (modulus) và `e` (public exponent). JWK thumbprint sẽ được tính từ tập thuộc tính bắt buộc tương ứng với loại khóa.

### 5.2. JWK thumbprint theo RFC 7638

Server cần xác định public key trong DPoP proof có đúng là key đã ràng buộc với access token hay không. RFC 7638 định nghĩa **JWK Thumbprint** bằng cách:
1. Chọn chính xác các thành phần bắt buộc theo `kty`.
2. Tạo JSON object chỉ chứa những thành phần đó.
3. Sắp xếp tên thuộc tính theo thứ tự từ điển và serialize theo quy tắc canonicalization của RFC 7638.
4. Hash UTF-8 bytes của JSON bằng SHA-256.
5. Encode kết quả Base64URL, không padding.

Ví dụ EC P-256 chỉ dùng `crv`, `kty`, `x` và `y` theo canonical JSON:

~~~json
{"crv":"P-256","kty":"EC","x":"PUBLIC_X_COORDINATE","y":"PUBLIC_Y_COORDINATE"}
~~~

Thumbprint không được tính bằng cách hash tùy ý toàn bộ JSON JWK ban đầu, vì JWK có thể chứa thêm các metadata như `use`, `kid`, `alg`. Phải dùng đúng thành phần bắt buộc được RFC 7638 quy định.

### 5.3. cnf.jkt trong access token

Sau khi xác minh proof ở token endpoint, AS tính thumbprint của public JWK và gắn vào access token:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794826800,
  "cnf": {
    "jkt": "BASE64URL_JWK_THUMBPRINT"
  }
}
~~~

`cnf` là confirmation claim. `jkt` chứa JWK thumbprint, cho biết token bị ràng buộc với public key nào. Resource Server khi nhận proof mới sẽ:
1. Xác minh chữ ký proof bằng public JWK trong header.
2. Tính thumbprint từ JWK đó.
3. Đọc `cnf.jkt` của access token đã được xác minh.
4. So sánh hai giá trị constant-time hoặc bằng phép so sánh an toàn phù hợp.
5. Chỉ chấp nhận khi thumbprint khớp và các claim proof khác đều hợp lệ.

**Không tin `cnf.jkt` từ một JWT chưa xác minh chữ ký.** Trước hết phải xác minh access token theo issuer, key, signature, expiry và audience policy.

## 6. Tạo và sử dụng cặp khóa client

### 6.1. Client tạo khóa bất đối xứng

Client tạo key pair bằng CSPRNG và chọn thuật toán nằm trong allowlist của AS/RS. Ví dụ EC P-256 với ES256 là lựa chọn phổ biến. Khóa cần:
- Được sinh bằng thư viện mật mã đáng tin cậy.
- Có độ mạnh phù hợp policy.
- Có private key giữ kín.
- Có public key có thể xuất ra JWK.
- Có định danh/key lifecycle rõ ràng.

Không dùng HS256 hoặc một shared secret thay cho DPoP asymmetric proof. Không tự tạo key từ password, timestamp, device ID hoặc một chuỗi có thể đoán.

### 6.2. Lưu private key ở đâu?

| Loại client | Vị trí khuyến nghị | Lưu ý |
| --- | --- | --- |
| Native mobile | iOS Keychain/Secure Enclave hoặc Android Keystore khi phù hợp | Ưu tiên non-exportable key và kiểm soát backup/restore |
| Desktop | OS credential store, TPM hoặc hardware-backed keystore nếu có | Hạn chế export và quyền đọc process |
| Web SPA | Web Crypto API với key không extractable khi khả thi | XSS vẫn có thể gọi thao tác ký; DPoP không tự chặn XSS |
| Backend confidential client | KMS/HSM hoặc secret/key store được kiểm soát | Phân quyền service account, audit và rotation |
| Test automation | Key riêng cho test fixture | Không dùng khóa test trong môi trường production |

DPoP chứng minh possession của private key tại thời điểm ký, không bảo đảm thiết bị/client không bị compromise. Nếu attacker có quyền gọi private key hoặc điều khiển runtime, họ có thể tạo proof hợp lệ.

### 6.3. Một key cho mỗi client hay mỗi cài đặt?

DPoP binding gắn token với key, vì vậy cần xác định phạm vi key:
- Một key cho một installation/device giúp cô lập token giữa các thiết bị.
- Một key cho một backend client có thể phù hợp khi service vận hành tập trung.
- Dùng một key chung cho toàn bộ người dùng làm tăng phạm vi ảnh hưởng khi key bị lộ.

Khi key thay đổi, access token cũ vẫn bị ràng buộc với thumbprint cũ. Client không thể tự đổi key mà vẫn dùng token đó. Cần xin token mới theo luồng authorization/exchange thích hợp hoặc thực hiện quy trình key rollover mà AS hỗ trợ.

## 7. Sinh DPoP proof bằng Java

Ví dụ sau minh họa cách dùng Nimbus JOSE + JWT để tạo EC key và ký proof. API chi tiết có thể khác theo version Nimbus; đây là ví dụ tập trung vào cấu trúc RFC 9449, cần đối chiếu dependency của dự án trước khi đưa vào production.

### 7.1. Sinh key pair và public JWK

~~~java
import com.nimbusds.jose.jwk.Curve;
import com.nimbusds.jose.jwk.ECKey;
import com.nimbusds.jose.jwk.gen.ECKeyGenerator;

ECKey clientKey = new ECKeyGenerator(Curve.P_256)
        .keyID("client-dpop-key-01")
        .generate();

ECKey publicJwk = clientKey.toPublicJWK();

// clientKey giữ private material; publicJwk chỉ chứa public material.
~~~

Không gửi `clientKey` lên server. Chỉ phần `publicJwk` được nhúng trong proof. Trong ứng dụng thật, key nên được lưu vào secure keystore thay vì tạo lại mỗi lần chạy.

### 7.2. Tạo proof cho token endpoint

~~~java
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.ECDSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.time.Instant;
import java.util.Date;
import java.util.UUID;

String method = "POST";
String targetUri = "https://auth.example.com/oauth2/token";

JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.ES256)
        .type(new JOSEObjectType("dpop+jwt"))
        .jwk(clientKey.toPublicJWK())
        .build();

JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .jwtID(UUID.randomUUID().toString())
        .issueTime(Date.from(Instant.now()))
        .claim("htm", method)
        .claim("htu", targetUri)
        // Thêm nonce khi Authorization Server yêu cầu.
        .build();

SignedJWT proof = new SignedJWT(header, claims);
proof.sign(new ECDSASigner(clientKey));
String dpopProofJwt = proof.serialize();
~~~

Ở token endpoint, ví dụ không có `ath` vì chưa trình access token. Khi refresh token request, client tiếp tục dùng private key đã ràng buộc với refresh token nếu server áp dụng DPoP binding cho refresh token.

### 7.3. Tính ath khi gọi Resource Server

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

static String accessTokenHash(String accessToken) throws Exception {
    byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(accessToken.getBytes(StandardCharsets.US_ASCII));

    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
}
~~~

Sau đó thêm claim `ath` vào proof trước khi ký. Proof phải có `htm`, `htu` tương ứng với request API và `jti` mới.

### 7.4. Request tới Resource Server

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Authorization: DPoP ACCESS_TOKEN_VALUE
DPoP: SIGNED_DPOP_PROOF_JWT
~~~

Scheme trong Authorization header là **`DPoP`**, không phải `Bearer`, khi trình bày DPoP-bound access token theo RFC 9449. Header `DPoP` chứa proof JWT riêng cho request. Không đặt access token trong payload proof thay cho Authorization header.

## 8. Server xác minh proof như thế nào?

Resource Server cần thực hiện một chuỗi kiểm tra có thứ tự. Có thể tổ chức thành một verifier service và một filter tích hợp với authentication flow.

~~~mermaid
flowchart TD
    A[Nhận access token + DPoP proof] --> B[Xác minh access token]
    B --> C{Token hợp lệ và có cnf.jkt?}
    C -->|Không| X[Từ chối]
    C -->|Có| D[Parse DPoP JWS]
    D --> E[Kiểm tra typ, alg, public jwk]
    E --> F[Xác minh chữ ký bằng JWK]
    F --> G[Kiểm tra htm, htu, iat, jti, nonce]
    G --> H[Tính ath từ access token]
    H --> I[So sánh JWK thumbprint với cnf.jkt]
    I --> J{Tất cả đều hợp lệ?}
    J -->|Không| X
    J -->|Có| K[Đánh dấu jti đã dùng]
    K --> L[Tiếp tục authorization]
~~~

### 8.1. Các bước validation

1. Xác minh access token: issuer, chữ ký hoặc introspection, expiry, audience và trạng thái.
2. Xác định token có DPoP confirmation binding (`cnf.jkt`). Token DPoP-bound không được hạ cấp thành Bearer chỉ vì thiếu proof.
3. Parse proof theo JWS compact; kiểm tra `typ=dpop+jwt`.
4. Chỉ chấp nhận thuật toán asymmetric nằm trong allowlist; từ chối `none` và MAC symmetric.
5. Kiểm tra JWK public-only, đúng key type/curve/strength theo policy.
6. Xác minh chữ ký bằng public JWK.
7. Kiểm tra `htm` bằng HTTP method thực tế.
8. Kiểm tra `htu` bằng target URI thực tế sau normalization, không gồm query/fragment.
9. Kiểm tra `iat` trong cửa sổ thời gian và `nonce` nếu server yêu cầu.
10. Tính `ath` từ đúng access token và so sánh với claim trong proof.
11. Tính JWK thumbprint và so sánh với `cnf.jkt` trong token.
12. Kiểm tra `jti` chưa xuất hiện trong replay cache; ghi nhận nó một cách nguyên tử trước khi chấp nhận request.
13. Tiếp tục scope/role/business authorization như bình thường.

Các bước có thể được tối ưu hoặc sắp xếp lại trong implementation, nhưng không được bỏ các ràng buộc tương ứng. Không đánh dấu `jti` đã dùng trước khi có đủ dữ liệu xác minh cơ bản; đồng thời phải tránh hai request đồng thời cùng chấp nhận một proof.

### 8.2. DPoP-Nonce challenge

Server có thể yêu cầu nonce. Ví dụ response:

~~~http
HTTP/1.1 401 Unauthorized
DPoP-Nonce: SERVER_NONCE_VALUE
WWW-Authenticate: DPoP error="use_dpop_nonce"
~~~

Client tạo proof mới với claim `nonce` mang giá trị server cấp, `jti` mới và `iat` mới. Không gửi lại nguyên proof cũ chỉ thêm nonce ở HTTP header; nonce phải nằm trong payload JWT và proof phải được ký lại.

### 8.3. Proxy và URI reconstruction

Resource Server cần xác định URI client thực sự gọi. Nếu reverse proxy terminate TLS, app phải tin các forwarded headers chỉ từ proxy đã cấu hình. Không tin `X-Forwarded-Host` do bất kỳ client nào gửi trực tiếp. Sai cấu hình URI có thể làm htu validation từ chối request hợp lệ hoặc tạo bypass nếu validator so sánh một URI do attacker điều khiển.

## 9. Token endpoint và Resource Server có khác biệt gì?

| Kiểm tra | Token Endpoint | Resource Server |
| --- | --- | --- |
| DPoP proof | Có, khi client dùng DPoP theo flow | Có, khi trình DPoP-bound access token |
| `htm` / `htu` | Khớp POST và token endpoint URI | Khớp method và URI của API request |
| `ath` | Không gửi trong proof cho token request | Bắt buộc khi proof gắn access token |
| `cnf.jkt` | AS tính và gắn thumbprint vào token đầu ra | RS so thumbprint proof với token confirmation |
| Client authentication | Vẫn áp dụng theo RegisteredClient/method | Thường dùng access token; không thay bằng client auth |
| Nonce | AS có thể yêu cầu nonce riêng | RS có thể yêu cầu nonce riêng |
| Replay cache | Chống proof replay tại AS | Chống proof replay tại RS |

DPoP proof ở token endpoint có thể được dùng để xác định key sẽ ràng buộc với access token mới. Khi client dùng refresh token đã DPoP-bound, AS phải kiểm tra proof được tạo bằng đúng key đã ràng buộc theo quy tắc RFC. Không được cho phép client thay public key bằng một proof mới mà không có quy trình chuyển binding được xác thực.

## 10. Khóa, rotation và vòng đời token

### 10.1. Key rotation

Khi private key có nguy cơ bị lộ hoặc cần đổi theo chu kỳ:
- Tạo key pair mới bằng quy trình an toàn.
- Bắt đầu một authorization/token issuance flow có thể ràng buộc access token mới với key mới.
- Giữ key cũ chỉ trong khoảng cần thiết để xử lý token cũ, nếu policy cho phép.
- Thu hồi token gắn với key cũ khi có compromise.
- Xóa key cũ khỏi keystore khi không còn token hợp lệ cần nó.

Không thể đổi `cnf.jkt` của access token đã phát hành chỉ bằng cách gửi public JWK mới. Token cũ vẫn gắn với thumbprint ban đầu.

### 10.2. Backup và restore

Nếu key mất sau khi app reinstall hoặc restore backup, client có thể không tạo được proof cho token đã ràng buộc. Cần yêu cầu reauthorization hoặc cơ chế recovery an toàn. Không export private key vào cloud backup không kiểm soát chỉ để giữ session tiện lợi.

### 10.3. Khi key bị compromise

Kẻ tấn công có private key và access token có thể tạo proof hợp lệ. DPoP không thể phân biệt client hợp lệ với attacker đang kiểm soát cùng key. Cần thu hồi token, rotation/re-registration key, điều tra thiết bị và kiểm soát refresh token/authorization theo policy.

## 11. DPoP trong ứng dụng Spring Security và Spring Authorization Server

DPoP là một protocol ở tầng HTTP/JWT. Khi tích hợp Spring, cần tách trách nhiệm:
- **Client:** tạo proof JWT cho mỗi request bằng private key.
- **Authorization Server:** xác minh proof ở token endpoint, chọn public key đã chứng minh possession và ràng buộc token đầu ra với thumbprint.
- **Resource Server:** xác minh DPoP proof trên mỗi request bảo vệ và so sánh thumbprint với access token.
- **Persistence/operations:** lưu/revoke trạng thái token, quản lý nonce và replay cache khi cần.

### 11.1. Phần cần kiểm tra theo phiên bản

Spring Security và Spring Authorization Server thay đổi API theo release. Không suy ra hỗ trợ đầy đủ DPoP chỉ từ việc ứng dụng có OAuth2 Resource Server, JWT decoder hoặc token customizer.

Trên dependency tree thực tế, kiểm tra:
1. Resource Server có built-in DPoP authentication/proof validation hay cần custom filter/provider.
2. Authorization Server có hỗ trợ DPoP proof tại token endpoint và tạo `cnf.jkt` hay cần custom converter/provider/token customizer.
3. Refresh token có được sender-constrain với cùng key không.
4. DPoP nonce và replay detection được lưu/truyền thế nào.
5. JWT access token và opaque token có cùng semantics confirmation không.
6. Error response, WWW-Authenticate và DPoP-Nonce tuân thủ RFC 9449 ra sao.

**JwtDecoder chỉ xác minh access token JWT.** Nó không tự xác minh proof JWT trong header `DPoP`, không so `htm`/`htu`/`ath` và không tự ngăn proof replay nếu không có cơ chế DPoP riêng.

### 11.2. Kiến trúc mở rộng tại Authorization Server

Nếu phiên bản SAS không cung cấp đầy đủ DPoP issuance, một thiết kế mở rộng có thể gồm:
- Converter/endpoint integration đọc header `DPoP` trong token request.
- Proof verifier kiểm tra typ, alg, public JWK, signature, htm, htu, iat, nonce và jti.
- Kết quả xác minh trả public JWK thumbprint.
- Token generator/customizer gắn `cnf.jkt` vào access token.
- Với refresh token, persistence ghi binding và provider kiểm tra proof cùng key trước khi cấp token tiếp theo.

Đây là **kiến trúc tích hợp**, không phải đoạn cấu hình copy-paste bảo đảm chạy với mọi phiên bản. Phải giữ toàn bộ kiểm tra grant, client authentication, scope, authorization và token lifecycle mặc định của SAS.

### 11.3. Kiến trúc mở rộng tại Resource Server

Nếu phiên bản Spring Security chưa cung cấp validator DPoP tích hợp theo nhu cầu, cần một lớp xác thực kết hợp:
1. Đọc access token theo scheme `DPoP`.
2. Xác minh access token.
3. Parse/verify DPoP proof.
4. Xác minh claim và replay.
5. So `cnf.jkt`.
6. Tạo Authentication đã xác minh để phần authorization Spring tiếp tục kiểm tra scope/authority.

Không thêm một filter chỉ kiểm tra header `DPoP` có tồn tại. Một chuỗi ngẫu nhiên ở header không chứng minh possession.

## 12. Những lỗi thiết kế thường gặp

**Lỗi 1 — gửi private key trong JWK.** Public JWK phải loại bỏ private parameters. Không serialize private JWK vào proof header.

**Lỗi 2 — dùng proof nhiều lần.** Mỗi HTTP request cần proof riêng với `jti` mới, method và URI đúng. Retry phải tạo proof mới.

**Lỗi 3 — dùng `htu` có query hoặc fragment.** Claim htu không chứa query/fragment; server phải so sánh theo URI normalization.

**Lỗi 4 — bỏ `ath` tại Resource Server.** Nếu không ràng buộc proof với access token cụ thể, attacker có thể ghép proof với token khác cùng key.

**Lỗi 5 — chỉ xác minh signature.** Signature hợp lệ chưa đủ: còn phải kiểm tra htm, htu, iat, jti, ath, nonce và cnf.jkt.

**Lỗi 6 — dùng Bearer scheme cho DPoP-bound token.** Client phải trình token theo scheme DPoP và kèm proof; server không được fallback sang Bearer.

**Lỗi 7 — dùng symmetric algorithm.** DPoP cần proof bằng private key bất đối xứng; từ chối HS* và none.

**Lỗi 8 — replay cache chỉ nằm trong memory từng node.** Có thể replay cùng proof qua node khác. Dùng store dùng chung hoặc cơ chế có consistency phù hợp.

**Lỗi 9 — tin forwarded headers từ mọi nguồn.** Kẻ tấn công có thể tác động URI reconstruction và làm sai htu validation. Chỉ tin proxy đã cấu hình.

**Lỗi 10 — nghĩ DPoP chặn XSS hoặc malware.** Nếu attacker điều khiển runtime hoặc gọi được key signing operation, họ vẫn có thể tạo proof hợp lệ.

## 13. Ma trận kiểm thử

| Nhóm | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Header | Thiếu typ hoặc typ khác `dpop+jwt` | Từ chối |
| Header | alg=`none` hoặc symmetric MAC | Từ chối |
| Header | JWK có private parameter | Từ chối |
| Signature | Chữ ký sai hoặc key không khớp | Từ chối |
| Key binding | JWK thumbprint khác `cnf.jkt` | Từ chối |
| Method | htm khác HTTP method thật | Từ chối |
| URI | htu sai scheme/host/port/path | Từ chối |
| URI | htu có query/fragment | Proof không hợp lệ |
| Time | iat quá cũ hoặc ở tương lai ngoài skew | Từ chối |
| Replay | Cùng jti/proof gửi lần hai | Từ chối |
| Token hash | ath tính từ token khác | Từ chối |
| Token hash | Thiếu ath khi gọi Resource Server với DPoP token | Từ chối |
| Nonce | Server yêu cầu nonce nhưng proof thiếu/sai | Trả challenge hoặc từ chối theo RFC |
| Token type | DPoP-bound token gửi bằng Bearer | Từ chối |
| Token endpoint | Proof hợp lệ cho POST token endpoint | Có thể phát hành token bound với jkt |
| Refresh | Refresh token bound được dùng với key khác | Từ chối |
| Concurrency | Cùng proof gửi đồng thời tới hai node | Tối đa một request được chấp nhận |
| Proxy | Forwarded header giả mạo từ client | Không thay đổi URI tin cậy |
| Rotation | Key mới dùng với access token cũ | Từ chối |
| Revocation | Token bị revoke nhưng proof đúng | Từ chối token |
| Logging | Kiểm tra log sau test | Không lộ private key/access token/proof nhạy cảm |

### 13.1. Test ath độc lập

Tạo token A và token B. Sinh proof với `ath` của A rồi gửi:
- Authorization header chứa token A → có thể qua kiểm tra ath.
- Authorization header chứa token B → phải bị từ chối.
- Thay một ký tự trong token A → ath không khớp.
- Gửi proof tới URI khác hoặc method khác → htu/htm không khớp.

### 13.2. Test replay cache phân tán

Gửi cùng một proof JWT tới hai Resource Server instance trong cùng cửa sổ thời gian. Nếu cả hai đều chấp nhận, replay protection không có tính nhất quán cần thiết. Kiểm tra cả trường hợp hai request đến gần như đồng thời để xác minh thao tác check-and-insert `(jkt, jti)` là nguyên tử.

## 14. Bài tập tình huống

Một SPA gọi `orders-api`. Authorization Server đã cấp access token có claim:

~~~json
{
  "aud": ["orders-api"],
  "cnf": {
    "jkt": "JKT_FOR_CLIENT_KEY_A"
  }
}
~~~

Client tạo DPoP proof bằng key A, `htm=GET`, `htu=https://api.example.com/orders/42` và `ath` tính từ token hiện tại.

Hãy phân tích:

1. Vì sao attacker chỉ lấy được access token nhưng không có key A không thể tạo proof hợp lệ?
2. Vì sao public JWK nằm trong proof không làm lộ private key?
3. Nếu client thay key B nhưng tiếp tục dùng access token trên, server phải phản hồi thế nào?
4. Nếu attacker thay access token B trong Authorization header nhưng giữ proof có ath của token A, kiểm tra nào phát hiện?
5. Nếu cùng proof được gửi lại tới hai node, replay cache cần bảo đảm điều gì?
6. Nếu reverse proxy terminate TLS, làm sao Resource Server xác định htu đáng tin?
7. Khi DPoP-Nonce được yêu cầu, client phải tạo proof mới thế nào?
8. Vì sao DPoP không tự ngăn XSS điều khiển browser gọi private key?

**Gợi ý:** token A gắn với thumbprint key A qua cnf.jkt; proof mới phải được ký bằng private key A. ath ràng buộc proof với access token đang gửi; htm/htu ràng buộc method/URI; jti và iat giúp chống replay theo thời gian. Public JWK chỉ chứa thành phần public. Nếu key đổi, cần token mới hoặc quy trình rollover được AS hỗ trợ.

## 15. Checklist triển khai production

1. **Key generation:** sinh khóa bằng CSPRNG, dùng thuật toán bất đối xứng được cho phép và key strength phù hợp.
2. **Key storage:** giữ private key trong OS keystore/KMS/HSM hoặc WebCrypto non-extractable khi phù hợp; không gửi private material.
3. **Public JWK:** chỉ đưa public parameters vào proof; kiểm tra key type, curve, kích thước và thuật toán.
4. **Proof header:** `typ=dpop+jwt`, `alg` asymmetric allowlist, `jwk` hợp lệ.
5. **Proof claims:** jti duy nhất, htm/htu chính xác, iat mới; ath khi gọi Resource Server; nonce khi được yêu cầu.
6. **Token binding:** phát hành access token có `cnf.jkt` đúng thumbprint từ public JWK đã xác minh.
7. **Resource Server:** xác minh access token, proof, ath, htm, htu, iat, jti, nonce và cnf.jkt.
8. **Replay:** cache dùng chung/atomic theo jkt+jti, TTL phù hợp cửa sổ proof.
9. **Refresh:** nếu refresh token được ràng buộc DPoP, kiểm tra cùng key và không cho đổi binding tùy ý.
10. **Proxy:** cấu hình trusted proxy/external URI để htu không bị spoof.
11. **Lifecycle:** có key rotation, revoke, backup/restore và recovery plan.
12. **Spring integration:** xác minh tính năng theo dependency version; JwtDecoder không thay thế DPoP verifier.
13. **Testing:** kiểm thử âm, replay đồng thời, nhiều node, proxy, nonce, token hash và key rotation.
14. **Operations:** không log private key, access token hoặc raw proof; có metrics lỗi signature, ath, htu, replay và nonce.

## 16. Tài liệu chuẩn để đối chiếu

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): cấu trúc proof, claim, header, token binding, nonce và validation.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): serialization và chữ ký JWT compact.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): cấu trúc public/private JWK.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): thuật toán chữ ký và key representation.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638.html): canonical JSON và cách tính thumbprint.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): profile JWT access token và claims.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT access token; DPoP proof validation là trách nhiệm riêng nếu version không cung cấp tích hợp tương ứng.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): thư viện Java dùng để tạo/xác minh JWS và JWK.

**Ghi nhớ:** DPoP proof là JWT ký bằng **private key của client**, có public JWK trong header và các claim ràng buộc method, URI, thời gian, định danh proof; khi gọi Resource Server còn có `ath` gắn proof với access token. Authorization Server gắn token với JWK thumbprint qua `cnf.jkt`. Resource Server chỉ chấp nhận khi chữ ký, request claims, replay/nonce và thumbprint đều hợp lệ. Public JWK có thể được công khai; private key phải ở lại trong môi trường được client kiểm soát.
