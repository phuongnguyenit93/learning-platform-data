# DPoP proof khác access token và được ký bằng khóa của client

Trong **Spring Security OAuth 2.0 / OIDC Resource Server**, một Bearer Access Token có thể được bất kỳ ai đang nắm giữ sử dụng: người gửi chỉ cần đưa token vào request. Điều đó thuận tiện, nhưng nếu token bị sao chép từ log, browser storage, thiết bị hoặc một kết nối bị xâm phạm, kẻ lấy được token có thể thử dùng nó như chính client hợp lệ cho đến khi token hết hạn hoặc bị thu hồi.

**DPoP (Demonstrating Proof of Possession)** theo **RFC 9449** bổ sung một bằng chứng rằng bên gửi request đang sở hữu private key đã được ràng buộc với Access Token. Client tạo một cặp khóa, giữ private key và ký một **DPoP proof JWT riêng cho từng HTTP request**. Resource Server xác minh chữ ký proof, kiểm tra proof gắn với đúng request và đúng Access Token, rồi đối chiếu public-key thumbprint trong proof với thông tin ràng buộc của token.

DPoP proof và Access Token có vai trò khác nhau:

- **Access Token** là credential mang quyền truy cập: subject/client, audience, scopes/authorities và thời hạn theo token contract.
- **DPoP proof** là một JWT ngắn hạn được client ký bằng private key, chứng minh quyền sở hữu khóa cho một request cụ thể.
- **Public JWK** nằm trong header proof để bên nhận xác minh chữ ký; private key không được gửi lên server.
- **Ràng buộc khóa** được biểu diễn trong Access Token bằng claim `cnf.jkt` (confirmation key thumbprint). Proof chỉ hợp lệ cho token nếu thumbprint khớp.

Vì vậy, **DPoP proof không thay thế Access Token và cũng không tự cấp scope/role**. Proof hợp lệ chỉ chứng minh request được ký bằng khóa tương ứng; Resource Server vẫn phải xác thực Access Token, audience, issuer, expiration, quyền endpoint và quyền trên dữ liệu.

Bài học thuộc chương **Token ràng buộc khóa**, sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x** làm bối cảnh. Nội dung đi từ cấu trúc DPoP proof, quy trình phát hành token, request tới Resource Server, `ath`/`cnf.jkt`, nonce, chống replay, vòng đời khóa, tích hợp Spring Security và kiểm thử. API hỗ trợ DPoP phụ thuộc phiên bản/thành phần cụ thể; không nên giả định một cấu hình JWT Resource Server thông thường tự động thực thi toàn bộ RFC 9449.

## 1. Vấn đề của Bearer Access Token

Với cơ chế Bearer thông thường:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Resource Server xác thực token. Bên nào có token cũng có thể gửi request; server không có bằng chứng mật mã rằng người gửi là client ban đầu đã nhận token.

~~~text
Client hợp lệ ---- Access Token T ----> Resource Server
       |
       +---- Token T bị sao chép ----> Attacker
                                        |
                                        +---- Bearer T ----> Resource Server
~~~

Nếu T chưa hết hạn, chưa bị revoke và có scope phù hợp, một Bearer API có thể chấp nhận cả hai request. TLS bảo vệ token khi truyền trên kết nối, nhưng **không ngăn token bị lấy từ nơi lưu trữ hoặc hệ thống đầu cuối**.

DPoP thay đổi điều kiện chấp nhận:

~~~text
Access Token T được ràng buộc với public key K

Client giữ private key k
       |
       +-- tạo proof P và ký bằng k
       |
       v
Request: DPoP token T + proof P
       |
       v
Resource Server kiểm tra:
  - Access Token hợp lệ?
  - Proof signature đúng với public key K?
  - Thumbprint(K) == token.cnf.jkt?
  - Proof dành cho đúng HTTP method/URI?
  - Proof còn mới và chưa replay?
       |
       v
Chỉ sau đó mới xét scope và quyền tài nguyên
~~~

Attacker chỉ sao chép được Access Token T nhưng **không có private key** sẽ không thể tạo proof mới hợp lệ. Đây là cơ chế **sender-constrained token** (token ràng buộc người gửi).

## 2. Ba đối tượng không được nhầm lẫn

| Đối tượng | Là gì? | Ai tạo/ký? | Vai trò |
| --- | --- | --- | --- |
| **Access Token** | OAuth credential, có thể opaque hoặc JWT. | Authorization Server phát hành; nếu JWT thì AS ký. | Mang quyền truy cập resource. |
| **DPoP proof JWT** | JWT ngắn hạn, thường tạo riêng cho mỗi request. | Client ký bằng private key DPoP. | Chứng minh possession và ràng buộc proof với request/token. |
| **DPoP key pair** | Public key + private key của client. | Client tạo/quản lý. | Private key ký proof; public key được gắn với token qua thumbprint. |

Một cách ghi nhớ:

- **Token trả lời:** “Bạn được phép truy cập tài nguyên nào?”
- **Proof trả lời:** “Request này được ký bởi bên đang sở hữu khóa đã gắn với token không?”
- **Resource Server trả lời:** “Token và proof có hợp lệ không, và principal có quyền thực hiện thao tác này không?”

DPoP key **không phải** signing key của Authorization Server. Private key DPoP thuộc client; public key DPoP được gửi trong proof. Signing key của AS vẫn dùng để ký JWT Access Token nếu hệ thống phát hành token dạng JWT.

## 3. Cặp khóa của client và JWK

Client tạo một cặp khóa bất đối xứng:

~~~text
Private key k
  - chỉ client giữ
  - dùng để ký DPoP proof
  - không gửi qua HTTP

Public key K
  - có thể công khai
  - được đưa vào header DPoP proof dưới dạng JWK
  - Resource Server dùng để xác minh chữ ký proof
~~~

Ví dụ public JWK EC P-256:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "f83OJ3D2xF4...",
  "y": "x_FEzRu9v..."
}
~~~

Đây chỉ là hình dạng minh họa; tọa độ đã rút gọn nên không phải key có thể sử dụng. **Private member** như `d` của EC JWK hoặc `d` của RSA JWK không được gửi trong DPoP proof. Client cần bảo vệ private key trong keystore, secure enclave, TPM, OS credential store hoặc cơ chế phù hợp với môi trường.

### 3.1. Thumbprint của public key

DPoP dùng **JWK Thumbprint** theo RFC 7638 để nhận diện public key một cách ổn định. Với một EC P-256 key, thumbprint được tính từ các thành phần JWK chuẩn hóa:

~~~text
{"crv":"P-256","kty":"EC","x":"...","y":"..."}
~~~

Sau đó:

~~~text
jkt = BASE64URL-ENCODE(
        SHA-256(canonical-JWK-thumbprint-input)
      )
~~~

Không tự hash toàn bộ JSON JWK tùy thứ tự field hoặc whitespace. Phải dùng thuật toán canonicalization/serialization đúng RFC 7638.

### 3.2. Vì sao dùng thumbprint thay public key đầy đủ trong Access Token?

Access Token chỉ cần mang một giá trị ràng buộc ngắn:

~~~json
{
  "cnf": {
    "jkt": "BASE64URL_JWK_THUMBPRINT"
  }
}
~~~

Khi client gửi proof chứa public JWK, Resource Server tự tính thumbprint và so sánh với `cnf.jkt` trong token đã xác thực. Nếu khác nhau, proof không được dùng với token đó.

**Không được lấy `cnf.jkt` từ một token chưa xác minh rồi cấp quyền.** Phải xác thực Access Token trước, hoặc dùng một quy trình xác minh opaque token/introspection tin cậy trả metadata `cnf`.

## 4. Cấu trúc DPoP proof JWT

DPoP proof là một JWT có header và payload riêng. Header thường gồm:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "PUBLIC_KEY_X",
    "y": "PUBLIC_KEY_Y"
  }
}
~~~

Ý nghĩa:

- `typ` phải là `dpop+jwt` theo profile DPoP.
- `alg` là thuật toán chữ ký bất đối xứng được chấp nhận; ví dụ `ES256` với EC P-256.
- `jwk` chứa public key tương ứng private key dùng ký proof.
- Không đưa private key vào JWK.
- Không chấp nhận thuật toán không an toàn, `none` hoặc cấu hình downgrade ngoài allowlist.

Payload proof thường chứa:

~~~json
{
  "jti": "unique-proof-id-7b2...",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1893452400,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

Các claim quan trọng:

| Claim | Ý nghĩa | Resource Server kiểm tra |
| --- | --- | --- |
| `jti` | ID duy nhất của proof. | Chống replay; cùng proof không được chấp nhận lại trong cửa sổ hiệu lực. |
| `htm` | HTTP method mà proof dành cho, ví dụ GET/POST. | Khớp method của request hiện tại. |
| `htu` | HTTP target URI mà proof dành cho, bỏ query và fragment theo RFC. | Khớp URI request sau chuẩn hóa đúng quy tắc. |
| `iat` | Thời điểm tạo proof. | Nằm trong cửa sổ thời gian được chấp nhận. |
| `ath` | Hash của Access Token. | Gắn proof với chính token gửi trong request resource. |
| `nonce` | Server-provided nonce khi được yêu cầu. | Proof phải dùng nonce hợp lệ/chưa hết hạn theo chính sách server. |

Không phải mọi proof đều có đủ tất cả claim trong mọi ngữ cảnh. Đặc biệt, `ath` được dùng để ràng buộc proof với Access Token trong **resource request**; ở token endpoint lúc xin token chưa có Access Token mới để hash nên không gửi `ath` cho token request đó.

## 5. Các claim của proof ràng buộc điều gì?

### 5.1. htm: HTTP method

Nếu proof được tạo cho:

~~~http
GET /api/orders/42
~~~

thì `htm` là:

~~~json
{"htm":"GET"}
~~~

Attacker không thể lấy nguyên proof đó đổi request thành `DELETE` mà vẫn vượt method binding, vì Resource Server phải so khớp method. Method phải theo giá trị HTTP method thực tế và quy tắc RFC; không tự lowercase hoặc biến đổi khác nhau giữa proxy và ứng dụng.

### 5.2. htu: HTTP target URI

Proof ràng buộc URI đích, ví dụ:

~~~json
{
  "htu": "https://api.example.test/api/orders/42"
}
~~~

Theo RFC 9449, `htu` biểu diễn target URI với **query và fragment bị loại bỏ**. Vì vậy không được hiểu DPoP là chữ ký toàn bộ HTTP message:

- DPoP proof không ký request body.
- DPoP proof không ràng buộc query string theo cách chữ ký request toàn phần.
- TLS vẫn cần bảo vệ nội dung request và response.
- API vẫn phải validate query/body và authorization theo nghiệp vụ.

Khi chạy sau reverse proxy, việc dựng URI công khai phải dựa trên proxy/gateway **được tin cậy**. Không lấy tùy tiện `Host`, `X-Forwarded-Host` hoặc `Forwarded` từ client chưa xác thực để tính `htu`, nếu không attacker có thể thao túng cách server so khớp URI.

### 5.3. iat: thời điểm tạo

`iat` thường là NumericDate (giây Unix epoch). Resource Server áp dụng một cửa sổ thời gian ngắn, ví dụ proof không được cũ quá một khoảng được cấu hình:

~~~text
now - allowedAge <= iat <= now + allowedClockSkew
~~~

Các con số phải phù hợp clock synchronization và policy. Proof quá cũ hoặc thời gian tương lai vượt clock skew phải bị từ chối.

### 5.4. jti: định danh duy nhất và chống replay

Mỗi proof cần một `jti` duy nhất, thường là giá trị ngẫu nhiên có entropy cao. Server có thể lưu cặp:

~~~text
(JWK thumbprint, jti)
~~~

trong replay cache với TTL tương ứng cửa sổ proof hợp lệ. Nếu cùng proof được gửi lại, server phát hiện `jti` đã dùng và từ chối.

Chỉ kiểm tra `iat` là chưa đủ: attacker có thể replay một proof trong chính cửa sổ thời gian còn mới. **Freshness và replay detection là hai kiểm tra khác nhau.**

### 5.5. ath: gắn proof với Access Token

Với request tới Resource Server, `ath` là:

~~~text
ath = BASE64URL-ENCODE(
        SHA-256(ASCII(access_token))
      )
~~~

Base64url encoding dùng dạng không padding theo quy tắc JOSE. Resource Server tự tính từ **Access Token nhận trong Authorization header** rồi so với `ath` trong proof.

Tác dụng: proof được ký cho token T1 không thể bị ghép với token T2 khác. Nếu không có `ath` hoặc hash không khớp, proof không hợp lệ cho resource request.

## 6. Proof JWT khác Access Token JWT như thế nào?

Cả hai có thể được biểu diễn dưới dạng compact JWT:

~~~text
header.payload.signature
~~~

Nhưng định dạng chung không làm chúng cùng một loại credential.

| Tiêu chí | Access Token JWT | DPoP proof JWT |
| --- | --- | --- |
| Mục đích | Cấp quyền truy cập API. | Chứng minh possession cho một request. |
| Bên ký | Authorization Server. | Client giữ private DPoP key. |
| Header type | Theo Access Token profile, ví dụ `at+jwt` khi áp dụng RFC 9068. | `dpop+jwt`. |
| Khóa xác minh | Public signing key của AS. | Public JWK do client đưa trong proof, sau đó đối chiếu thumbprint. |
| Nội dung | Issuer, subject, audience, scopes, expiration, confirmation binding. | `htm`, `htu`, `iat`, `jti`, `ath` và có thể `nonce`. |
| Thời hạn | Thường dùng qua nhiều requests đến khi hết hạn/revoke. | Ngắn, riêng cho từng request. |
| Có tự cấp scope? | Có thể mang scopes/authorities theo token contract. | **Không.** |
| Có thể dùng làm Bearer token? | Chỉ khi token được cấp cho kiểu sử dụng đó. | **Không.** |

Một Access Token có thể là **opaque** thay vì JWT. Trong trường hợp đó RS introspect token để lấy metadata, bao gồm confirmation claim `cnf` nếu AS trả theo contract; DPoP proof vẫn là JWT được client ký.

## 7. Quy trình phát hành DPoP-bound Access Token

DPoP bắt đầu trước khi client gọi Resource Server: client phải đưa public-key proof vào **token request** để Authorization Server có thể gắn token mới với khóa.

~~~text
Client                           Authorization Server
  |                                       |
  | Tạo cặp khóa DPoP (k, K)              |
  | Giữ private key k                     |
  |                                       |
  | POST /oauth2/token                    |
  | DPoP: proof-signed-by-k                |
  | grant_type=authorization_code ...     |
  |-------------------------------------->|
  |                                       |
  | AS xác minh DPoP proof                 |
  | - typ/alg/signature                    |
  | - htm/htu/iat/jti/nonce                |
  | - public JWK và thumbprint             |
  |                                       |
  | AS phát hành Access Token T            |
  | gắn cnf.jkt = thumbprint(K)            |
  |                                       |
  | access_token=T, token_type=DPoP        |
  |<--------------------------------------|
  |                                       |
~~~

### 7.1. Token endpoint request

Ví dụ minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: DPOP_PROOF_JWT_SIGNED_BY_CLIENT_KEY

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&
code_verifier=PKCE_CODE_VERIFIER&
client_id=orders-web
~~~

DPoP proof trong header `DPoP` được ký bằng private key của client. Nó gắn với token endpoint request qua `htm` và `htu`, có `iat`/`jti` và có thể phải chứa server nonce.

Ở request này **không có `ath` cho Access Token mới**, vì token chưa được phát hành. Các grant/PKCE/client authentication vẫn phải được kiểm tra theo OAuth flow; DPoP không thay thế chúng.

### 7.2. Token response

Một response có thể có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "DPoP",
  "expires_in": 600,
  "scope": "orders.read"
}
~~~

Nếu Access Token là JWT, phần claims đã được AS ký có thể bao gồm:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "person-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000,
  "cnf": {
    "jkt": "BASE64URL_JWK_THUMBPRINT"
  }
}
~~~

Với opaque token, thông tin binding có thể được RS lấy qua introspection. Điều quan trọng là **AS phát hành token gắn với public key mà proof đã chứng minh possession**, và RS có cách đáng tin cậy để đọc confirmation binding.

### 7.3. Vì sao token_type là DPoP?

Token response báo `token_type` là `DPoP`. Khi gọi Resource Server, client sử dụng authorization scheme `DPoP` thay cho `Bearer`:

~~~http
Authorization: DPoP ACCESS_TOKEN_VALUE
~~~

Nếu token được cấp theo DPoP-bound profile, client không nên tùy tiện đổi sang `Bearer` và kỳ vọng API vẫn áp dụng đúng sender constraint. Resource Server phải phân biệt đúng token usage và policy; không âm thầm hạ cấp DPoP-bound token thành Bearer.

## 8. Gọi Resource Server: Access Token và proof đi cùng nhau

Mỗi protected-resource request gửi hai thành phần:

1. **Access Token** trong Authorization header với scheme `DPoP`.
2. **DPoP proof JWT** trong header `DPoP`.

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP ACCESS_TOKEN_VALUE
DPoP: DPOP_PROOF_JWT_FOR_THIS_REQUEST
Accept: application/json
~~~

Proof có payload minh họa:

~~~json
{
  "jti": "request-proof-42-unique",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1893452400,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

Header proof có public JWK và chữ ký bằng private key:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "PUBLIC_KEY_X",
    "y": "PUBLIC_KEY_Y"
  }
}
~~~

### 8.1. Các bước Resource Server phải kiểm tra

~~~text
1. Nhận Authorization: DPoP <access-token>
2. Nhận DPoP: <proof-jwt>
3. Xác thực Access Token theo JWT decoder hoặc introspection
4. Xác nhận token được cấp cho DPoP use và có cnf.jkt
5. Parse proof header:
     typ = dpop+jwt
     alg thuộc asymmetric allowlist
     jwk là public key hợp lệ
6. Xác minh proof signature bằng public JWK
7. Tính JWK thumbprint và so với token.cnf.jkt
8. Kiểm tra htm và htu với HTTP request hiện tại
9. Kiểm tra iat trong freshness window
10. Kiểm tra jti chưa từng được sử dụng (replay cache)
11. Kiểm tra ath khớp Access Token
12. Kiểm tra nonce nếu server yêu cầu
13. Sau khi authentication hoàn tất, kiểm tra scope/role/domain
~~~

Thứ tự triển khai chi tiết có thể khác theo framework, nhưng **không được bỏ một điều kiện bảo mật**. Đặc biệt, không tạo Authentication thành công chỉ vì Access Token hợp lệ nếu token yêu cầu DPoP proof mà proof bị thiếu/sai.

### 8.2. Vì sao proof phải mới cho mỗi request?

Một proof có `htm`/`htu` gắn với một method/URI và `jti` duy nhất. Client tạo proof mới cho từng request, kể cả hai request GET tới cùng endpoint:

~~~text
Request A: jti=proof-A, iat=t1, htm=GET, htu=/orders/42
Request B: jti=proof-B, iat=t2, htm=GET, htu=/orders/42
~~~

Không cache một proof JWT để tái sử dụng qua nhiều HTTP requests. Việc tái dùng có thể bị replay detection từ chối và không phản ánh đúng request mới.

## 9. DPoP proof có ký bằng private key của client

Client thực hiện các bước khái quát:

1. Tạo DPoP key pair theo thuật toán được hỗ trợ.
2. Tạo header chứa `typ=dpop+jwt`, `alg` và public `jwk`.
3. Tạo payload với `jti` ngẫu nhiên, `htm`, `htu`, `iat`, `ath` khi gọi resource và `nonce` nếu có.
4. Ký header.payload bằng **private key**.
5. Gửi compact JWT trong header `DPoP`.

~~~text
proof = BASE64URL(header)
      + "."
      + BASE64URL(payload)
      + "."
      + SIGN(privateKey, signingInput)
~~~

Đây là mô tả JOSE ở mức khái niệm. Khi triển khai, sử dụng thư viện JOSE được duy trì, cấu hình thuật toán rõ ràng và không tự viết cryptography.

### 9.1. Public JWK không phải private credential

Server cần public key để verify signature. Nếu client vô tình gửi private JWK member `d`, đó là lỗi nghiêm trọng: private key đã bị tiết lộ. Resource Server phải từ chối public JWK chứa private material theo profile/algorithm phù hợp; client phải giữ private key trong nơi lưu trữ an toàn.

### 9.2. Key có thể là software hoặc hardware-backed

Tùy client:

- Native mobile có thể dùng OS keystore hoặc hardware-backed key.
- Desktop app có thể dùng platform credential store.
- Server-side confidential client có thể dùng HSM/keystore.
- Browser client có thể dùng Web Crypto non-extractable key, nhưng XSS vẫn có thể gọi API ký nếu chạy được trong origin.

**Non-extractable không đồng nghĩa không thể bị lạm dụng**: mã JavaScript độc hại không lấy được bytes private key vẫn có thể gọi signing operation nếu chiếm quyền chạy trong context ứng dụng.

## 10. ath: ràng buộc proof với đúng Access Token

Nếu client gửi:

~~~http
Authorization: DPoP TOKEN_A
DPoP: PROOF_FOR_TOKEN_A
~~~

proof cần `ath` là hash của chính TOKEN_A:

~~~text
ath = BASE64URL_NO_PADDING(
        SHA-256(ASCII(TOKEN_A))
      )
~~~

Nếu attacker thay Authorization header:

~~~http
Authorization: DPoP TOKEN_B
DPoP: PROOF_FOR_TOKEN_A
~~~

Resource Server tính lại hash TOKEN_B. Nó khác `ath` trong proof nên request bị từ chối.

### 10.1. Hash Access Token không phải ký lại token

`ath` không biến proof thành Access Token và không mang scopes. Nó chỉ bind proof với token cụ thể. Token vẫn phải được xác minh:

- JWT: signature, issuer, audience, thời hạn, token profile và các validators.
- Opaque: introspection thành công, `active` true và metadata phù hợp.

Sau đó mới kiểm tra `cnf.jkt` và DPoP proof.

### 10.2. Không bỏ ath trong resource request

Nếu proof có chữ ký hợp lệ nhưng không ràng buộc token, có nguy cơ một proof hợp lệ bị ghép với một credential khác trong một số tình huống. Theo DPoP profile, Resource Server cần kiểm tra `ath` với Access Token của protected-resource request. **Không nhầm quy tắc này với token endpoint request**, nơi chưa có Access Token được cấp.

## 11. cnf.jkt: Access Token được ràng buộc với khóa nào?

Trong Access Token đã xác minh:

~~~json
{
  "sub": "person-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "THUMBPRINT_OF_CLIENT_PUBLIC_JWK"
  }
}
~~~

DPoP proof có public JWK. Resource Server:

1. Xác minh Access Token hoặc lấy metadata introspection tin cậy.
2. Đọc `cnf.jkt`.
3. Đọc public JWK trong proof header.
4. Tính JWK thumbprint theo RFC 7638.
5. So sánh giá trị.

~~~text
Access Token:
  cnf.jkt = thumbprint(K1)

DPoP proof:
  header.jwk = K1
  computed thumbprint = thumbprint(K1)

So sánh: MATCH -> tiếp tục các kiểm tra proof khác
~~~

Nếu proof được ký bằng key K2:

~~~text
Access Token cnf.jkt = thumbprint(K1)
Proof JWK thumbprint  = thumbprint(K2)

K1 != K2 -> REJECT
~~~

### 11.1. Với opaque Access Token

Nếu Access Token opaque, RS không tự decode claims. Nó cần introspection response hoặc một trusted adapter cung cấp thông tin confirmation binding theo contract:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "person-42",
  "aud": ["orders-api"],
  "cnf": {
    "jkt": "THUMBPRINT_OF_CLIENT_PUBLIC_JWK"
  }
}
~~~

Nếu token là DPoP-bound nhưng introspection adapter không trả `cnf` hoặc không phân biệt token type, RS **không có đủ thông tin để xác minh sender constraint**. Không được fallback thành Bearer acceptance chỉ vì token active.

### 11.2. cnf là confirmation, không phải quyền

`cnf.jkt` chỉ nói token được gắn với public key nào. Nó không cho biết:

- Client được phép đọc mọi tenant.
- Người dùng có quyền admin.
- Request body là hợp lệ.
- Scope của token có quyền ghi.

Đó là các quyết định authorization khác.

## 12. Nonce: server có thể yêu cầu proof dùng challenge mới

DPoP có thể dùng **server-provided nonce** để tăng khả năng chống replay và hạn chế việc client chuẩn bị proof từ trước.

Luồng:

~~~text
Client -> Resource Server
  Request với DPoP proof không có nonce

Resource Server -> Client
  DPoP-Nonce: SERVER_NONCE_VALUE
  response yêu cầu proof mới

Client tạo proof mới:
  jti = giá trị mới
  iat = hiện tại
  nonce = SERVER_NONCE_VALUE
  htm/htu/ath = request hiện tại

Client -> Resource Server
  Request + proof mới
~~~

Resource Server có thể gửi response header `DPoP-Nonce` để client sử dụng cho lần thử tiếp theo. Client phải tạo **proof mới**, không chỉ copy nguyên proof cũ rồi sửa payload (sửa payload làm chữ ký cũ không còn hợp lệ).

### 12.1. Nonce không thay jti

Nonce và `jti` phục vụ các mục đích liên quan nhưng khác nhau:

- **Nonce** chứng minh proof có sử dụng challenge gần đây do server cấp.
- **jti** nhận diện một proof cụ thể để server phát hiện việc dùng lại.
- **iat** kiểm soát độ mới theo đồng hồ.

Nếu chỉ dùng nonce mà chấp nhận cùng `jti` nhiều lần, có thể còn lỗ hổng replay tùy cách quản lý nonce. Nếu chỉ dùng `iat`, proof vẫn có thể replay trong cửa sổ tuổi cho phép.

### 12.2. Nonce phải gắn đúng server/resource context

Client không nên dùng một nonce từ server A cho server B. Server cần tạo, lưu hoặc xác minh nonce theo policy của mình, có TTL và cách chống giả mạo thích hợp. Nếu có nhiều replicas, nonce validation phải nhất quán giữa những nodes có thể nhận request kế tiếp, hoặc dùng cơ chế cho phép xác minh phân tán.

## 13. Replay protection và jti cache

Proof là một message đã ký. Nếu attacker đánh cắp **cả Access Token và một DPoP proof chưa sử dụng**, attacker có thể thử phát lại nguyên request trong cửa sổ thời gian proof hợp lệ. DPoP cần cơ chế replay detection.

Một mô hình replay cache:

~~~text
key = (JWK thumbprint, jti)
value = firstSeenAt
TTL = proof acceptance window + clock margin
~~~

Khi request đến:

1. Xác minh chữ ký proof.
2. Kiểm tra `iat` và nonce theo policy.
3. Tính thumbprint public JWK.
4. Thực hiện **atomic insert-if-absent** cho `(jkt,jti)`.
5. Nếu key đã tồn tại, từ chối proof replay.
6. Nếu insert thành công, tiếp tục xác minh `htm`, `htu`, `ath` và token binding theo pipeline được thiết kế.

**Atomicity quan trọng:** hai requests đồng thời đến hai replicas với cùng proof phải không thể cùng vượt qua chỉ vì mỗi node dùng một local map độc lập. Nếu cần replay protection toàn cụm, cần shared store hoặc chiến lược routing/consistency được thiết kế.

### 13.1. Vì sao chỉ dùng local in-memory cache có giới hạn?

~~~text
Request proof P -> Node A: jti chưa thấy -> accept
Replay proof P  -> Node B: jti chưa thấy ở B -> có thể accept
~~~

Nếu load balancer có thể gửi cùng proof đến nhiều nodes, local cache không đủ để bảo đảm toàn cluster. Có thể:

- Dùng distributed replay store với atomic insert.
- Dùng nonce/validation strategy có khả năng kiểm tra giữa nodes.
- Đảm bảo routing affinity trong phạm vi cần thiết, nếu threat model và hạ tầng cho phép.

Không tuyên bố “DPoP chống replay toàn cụm” chỉ vì mỗi node có một Caffeine cache.

### 13.2. Cache TTL phải khớp proof freshness

Replay record phải được giữ đủ lâu để bao phủ **toàn bộ cửa sổ mà proof có thể được chấp nhận**. Nếu proof chỉ được chấp nhận trong 60 giây nhưng replay cache hết sau 10 giây, attacker có thể phát lại proof trong 50 giây còn lại.

Ngược lại, TTL quá dài làm tăng memory usage và có thể tạo DoS bằng lượng proof IDs lớn. Cần:

- Giới hạn tuổi proof.
- Giới hạn kích thước/rate của replay cache.
- Dùng key có namespace/partition phù hợp.
- Đồng bộ thời gian và giám sát cache availability.
- Fail closed khi không thể đảm bảo replay check theo policy.

## 14. DPoP không thay thế TLS hoặc ký toàn bộ HTTP request

DPoP ràng buộc một số thuộc tính:

- HTTP method (`htm`).
- Target URI (`htu`) theo quy tắc RFC.
- Thời điểm tạo (`iat`).
- Định danh proof (`jti`).
- Access Token hash (`ath`) cho resource request.
- Public key của client (JWK/`cnf.jkt`).

DPoP **không ký request body** và không cung cấp mã hóa dữ liệu. TLS vẫn cần thiết để bảo vệ:

- Authorization header và DPoP header khỏi nghe lén.
- Request body, query parameters và response.
- Confidentiality/integrity của dữ liệu ứng dụng.
- Client/server transport authentication theo kiến trúc.

Nếu API cần bảo vệ tính toàn vẹn body hoặc payload ở tầng ứng dụng, cần một cơ chế message signing phù hợp riêng; không diễn giải DPoP thành chữ ký mọi byte của HTTP message.

### 14.1. DPoP không ngăn mọi kiểu compromise

DPoP giúp giảm rủi ro **Access Token bị đánh cắp đơn lẻ**. Nó không tự bảo vệ khi:

- Attacker lấy được cả private key.
- Attacker điều khiển ứng dụng client và có thể gọi key signing API.
- Malware/extension có quyền thao tác trong browser profile.
- Request/proof hợp lệ bị relay trong cửa sổ cho phép trước khi replay cache ghi nhận.
- Resource Server bỏ kiểm tra `ath`, `htu`, `htm` hoặc replay.
- Private key được dùng chung không kiểm soát giữa nhiều người dùng/thiết bị.

Vì vậy DPoP là một lớp sender constraint, không phải thay thế secure storage, TLS, XSS prevention, endpoint security hoặc authorization.

## 15. DPoP so với Bearer và mTLS-bound tokens

| Tiêu chí | Bearer Token | DPoP-bound Token | mTLS-bound Token |
| --- | --- | --- | --- |
| Chứng minh possession | Có token là đủ. | Client ký proof bằng private key cho request. | Client chứng minh possession private key qua TLS handshake/certificate. |
| Key binding | Không bắt buộc. | Public-key thumbprint trong token (`cnf.jkt`). | Certificate binding, thường qua confirmation claim tương ứng. |
| Per-request data | Không có DPoP proof. | `htm`, `htu`, `iat`, `jti`, `ath`, nonce khi cần. | TLS connection/client certificate cung cấp binding. |
| Tính phù hợp | Phổ biến, dễ tích hợp. | Native apps, browser/public clients và môi trường khó triển khai client cert. | Service-to-service hoặc môi trường quản lý certificate tốt. |
| Replay defense | Chủ yếu dựa vào bảo vệ token/TLS. | Proof freshness, `jti`, nonce và token binding. | TLS handshake/connection binding; vẫn cần bảo vệ token và session. |
| Độ phức tạp | Thấp hơn. | Client và RS cần tạo/verify proof và replay policy. | PKI, certificate lifecycle và TLS termination phức tạp. |

DPoP và mTLS đều là sender-constrained approaches nhưng ràng buộc ở các tầng khác nhau. Không chuyển từ DPoP sang Bearer fallback khi proof lỗi chỉ để tăng compatibility nếu token đã được phát hành với yêu cầu DPoP.

## 16. Key lifecycle của client

### 16.1. Tạo và lưu khóa

Client nên:

1. Tạo key pair từ CSPRNG và thuật toán được hỗ trợ.
2. Không xuất private key ra logs, analytics hoặc network.
3. Bảo vệ key bằng OS keystore/HSM/secure enclave hoặc Web Crypto theo môi trường.
4. Tách key theo application installation/device/user context phù hợp.
5. Có cơ chế backup/recovery/re-enrollment theo threat model; không đồng bộ private key tùy tiện qua cloud.

### 16.2. Khi key bị mất

Nếu private key bị mất, client không thể tạo proof hợp lệ cho token đã bind với thumbprint cũ. Cần:

- Bắt đầu authorization/token issuance flow để bind token mới với key mới.
- Revoke token cũ nếu còn sử dụng được và policy yêu cầu.
- Không sửa `cnf.jkt` trong token cũ; đó là claim do AS phát hành/ký.
- Xử lý refresh token theo chính sách sender constraint của AS.

### 16.3. Khi key bị compromise

Nếu attacker có private key:

- DPoP không còn ngăn attacker sử dụng token bound với key đó.
- Thu hồi token/grant và yêu cầu token mới gắn với key mới.
- Vô hiệu hóa thiết bị/session liên quan theo policy.
- Kiểm tra logs/audit về request proof và resource access.
- Không chỉ xóa public JWK khỏi client; AS/RS cần cập nhật token state và key binding lifecycle.

### 16.4. Key rotation

Token cũ gắn với thumbprint K1. Token mới gắn với K2:

~~~text
Token T1: cnf.jkt = thumbprint(K1)
Token T2: cnf.jkt = thumbprint(K2)
~~~

Proof ký bằng K2 không thể dùng với T1. Trong giai đoạn chuyển đổi, client có thể cần giữ K1 để dùng token cũ cho đến khi token hết hạn/revoke, trong khi xin token mới gắn K2. Cách xử lý refresh token và re-binding phải theo AS implementation và OAuth flow; không tự thay key rồi kỳ vọng token cũ tự cập nhật.

## 17. DPoP với Spring Security Resource Server

Spring Security có các thành phần OAuth 2.0 Resource Server cho Bearer JWT và opaque token. Tuy nhiên, **chỉ cấu hình JWT decoder hoặc opaque introspector không tự chứng minh toàn bộ RFC 9449 đã được thực thi**. Một triển khai DPoP đầy đủ phải xử lý:

1. Phân biệt scheme `DPoP` với `Bearer`.
2. Xác thực Access Token theo đúng token format.
3. Xác minh DPoP proof JWT, public JWK và asymmetric algorithm.
4. Đối chiếu `cnf.jkt`.
5. Kiểm tra `htm`, `htu`, `iat`, `jti`, `ath` và nonce.
6. Replay detection với concurrency/cluster semantics.
7. Trả DPoP nonce challenge/response header nếu áp dụng.
8. Chỉ sau đó mới tạo Authentication cho authorization layer.

**Khả năng hỗ trợ tích hợp sẵn phụ thuộc phiên bản Spring Security và Authorization Server.** Trước khi chọn API, kiểm tra tài liệu đúng version đang dùng. Nếu version không có hỗ trợ đầy đủ, cần một integration chuyên biệt đã được review hoặc gateway/authorization component có hỗ trợ DPoP. Không tự kết luận cấu hình `oauth2ResourceServer().jwt()` đã xử lý proof.

### 17.1. Phần JWT Access Token vẫn cần cấu hình bình thường

Ví dụ Spring Security Servlet cho JWT Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là **cấu hình JWT Resource Server thông thường**, minh họa phần xác thực Access Token và authorization. Nó **chưa tự thực hiện DPoP proof verification**. Không dùng nguyên cấu hình này làm bằng chứng DPoP đã bật; cần integration DPoP đứng đúng vị trí trong authentication pipeline và chặn Bearer fallback cho DPoP-bound tokens.

Với opaque token, phần token validation có thể dùng `OpaqueTokenIntrospector`; DPoP integration vẫn phải kiểm tra `cnf` trong metadata introspection và proof độc lập.

### 17.2. Pipeline tích hợp khái niệm

~~~text
HTTP request
  |
  v
Extract DPoP authorization scheme + DPoP header
  |
  v
Access Token authentication
  |   JWT decoder / opaque introspection
  |   issuer, audience, exp, active
  v
Get verified cnf.jkt
  |
  v
DPoP proof verifier
  |   typ / alg / public jwk / signature
  |   htm / htu / iat / jti / ath / nonce
  |   replay cache
  v
Create authenticated principal
  |
  v
Spring Security authorization
  |   scopes / roles / method security
  v
Domain tenant / owner / object checks
  |
  v
Controller
~~~

Đây là **sơ đồ trách nhiệm**, không phải một class/filter có sẵn. Cần bảo đảm lỗi DPoP không bị chuyển thành anonymous request rồi đi qua một rule `permitAll` sai phạm vi, và không có endpoint protected nào vô tình chấp nhận DPoP-bound token bằng Bearer scheme.

### 17.3. Filter order và error handling

Một integration cần phân biệt:

- **Invalid Access Token:** authentication thất bại.
- **Valid token nhưng thiếu proof:** sender constraint không được thỏa mãn, request bị từ chối theo DPoP protocol.
- **Proof signature sai, method/URI/ath sai:** proof invalid.
- **Replay `jti`:** từ chối proof đã sử dụng.
- **Nonce required/missing:** có thể trả challenge kèm `DPoP-Nonce` theo RFC.
- **Token hợp lệ, proof hợp lệ nhưng thiếu scope:** authorization 403.

Không bắt mọi exception rồi trả 401 generic nếu điều đó làm mất challenge/nonce semantics cần thiết. Đồng thời không tiết lộ chi tiết private key, token hoặc nội dung proof trong response/log.

## 18. DPoP và reverse proxy

`htu` phải được so với URI request thực tế theo quy tắc RFC. Khi API ở sau proxy:

~~~text
Client -- HTTPS --> API Gateway -- HTTP/internal TLS --> Spring App
~~~

Spring có thể chỉ nhìn thấy:

~~~text
http://orders-service:8080/api/orders/42
~~~

trong khi client đã ký:

~~~text
https://api.example.test/api/orders/42
~~~

Nếu so sánh hai chuỗi sai cách, request hợp lệ bị từ chối; nếu lấy forwarded headers không đáng tin, attacker có thể thao túng URI mà verifier dùng.

Thiết kế đúng:

- Xác định canonical external URI theo trusted proxy configuration.
- Chỉ tin forwarded headers từ proxy đã được xác thực/cấu hình.
- Chuẩn hóa scheme/host/port/path đúng profile DPoP.
- Kiểm tra các biến thể URL encoding, default ports, path normalization và redirect.
- Không tự bỏ path hoặc thêm query/fragment để “làm cho proof pass”.
- Test qua đúng topology gateway/ingress của production.

## 19. DPoP và các HTTP redirects

Một proof được tạo cho URI A không thể tùy tiện dùng cho URI B:

~~~text
Client -> https://api.example.test/orders/42
  302 Location: https://other.example.test/orders/42
~~~

Khi theo redirect, client phải cân nhắc **tạo proof mới** cho request đích, với đúng `htu`/`htm` và token phù hợp. Không gửi Access Token/DPoP proof sang host khác chỉ vì redirect. Client libraries cần policy rõ cho redirects và Authorization headers, đặc biệt cross-origin.

Nếu resource server redirect giữa host/scheme, cần test DPoP behavior; tránh thiết kế khiến client phải tiết lộ token tới một origin không được phép.

## 20. DPoP với OIDC và PKCE

DPoP, OIDC và PKCE giải quyết các khía cạnh khác nhau:

| Cơ chế | Bảo vệ điều gì? |
| --- | --- |
| **OIDC** | Authentication/identity layer và ID Token theo OpenID Connect. |
| **OAuth Access Token** | Quyền truy cập resource. |
| **PKCE** | Ràng buộc authorization code với client đã khởi tạo flow, giảm nguy cơ code interception. |
| **DPoP** | Ràng buộc Access Token với public key client và chứng minh possession theo từng request. |
| **TLS** | Bảo vệ kênh truyền và xác thực server; có thể xác thực client khi dùng mTLS. |

Các cơ chế có thể **cùng tồn tại**. PKCE không thay DPoP; DPoP không thay PKCE; DPoP proof không phải ID Token và không chứng minh người dùng đã đăng nhập.

## 21. Các tình huống tấn công và kết quả mong đợi

| Tình huống | Vì sao phải từ chối? |
| --- | --- |
| Token DPoP-bound nhưng request dùng `Authorization: Bearer` | Sai token usage/scheme; không được hạ cấp sender constraint. |
| Thiếu DPoP header | Không có proof-of-possession. |
| Proof ký bằng key khác `cnf.jkt` | Không sở hữu key gắn với token. |
| Proof không có `ath` cho resource request | Không ràng buộc proof với Access Token gửi kèm. |
| `ath` hash token khác | Proof được tạo cho credential khác. |
| `htm` khác HTTP method | Proof không dành cho request hiện tại. |
| `htu` khác URI đích | Proof không dành cho resource URI hiện tại. |
| Proof đã quá cũ/tương lai quá xa | Không đạt freshness policy. |
| `jti` đã được dùng | Replay. |
| `nonce` bắt buộc nhưng thiếu/sai | Không đáp ứng challenge của server. |
| Header `typ` không phải `dpop+jwt` | Không đúng DPoP proof profile. |
| `alg=none` hoặc thuật toán không allowlist | Chữ ký không được xác minh an toàn. |
| JWK chứa private key material | Public proof không được làm lộ private credential. |
| Access Token sai issuer/audience/exp hoặc inactive | Credential không hợp lệ, dù proof có chữ ký đúng. |
| Token/proof hợp lệ nhưng thiếu scope | Authentication có thể thành công, authorization trả 403. |

## 22. Kiểm thử DPoP theo lớp

Không nên chỉ test một JWT proof chữ ký đúng. Cần test toàn bộ liên kết giữa **token, key, request, thời gian và replay state**.

### 22.1. Unit tests cho proof verifier

| Test | Kỳ vọng |
| --- | --- |
| Proof ES256 đúng key | Chữ ký pass. |
| Thay một byte payload sau khi ký | Chữ ký fail. |
| `typ` sai | Từ chối. |
| `alg` không được phép hoặc none | Từ chối. |
| JWK không hợp lệ/không phải public key phù hợp | Từ chối. |
| JWK thumbprint khác token `cnf.jkt` | Từ chối. |
| `htm` khác method thực | Từ chối. |
| `htu` khác canonical URI | Từ chối. |
| `iat` quá cũ/quá tương lai | Từ chối. |
| `jti` đã được ghi nhận | Từ chối replay. |
| `ath` không khớp token | Từ chối. |
| Nonce bắt buộc nhưng thiếu/sai | Challenge hoặc từ chối theo RFC/policy. |
| `ath` không có ở token endpoint proof | Không áp quy tắc resource-request một cách máy móc. |

### 22.2. Integration tests với Spring Security

Thiết lập test:

1. Tạo test DPoP key pair.
2. Phát hành hoặc dựng Access Token có `cnf.jkt` khớp public key test.
3. Gửi request có `Authorization: DPoP ...` và proof được ký bằng private key test.
4. Xác minh token JWT/introspection theo đường thực tế.
5. Gửi proof hợp lệ đến endpoint có scope phù hợp.
6. Gửi lại **cùng proof** lần hai để xác nhận replay detection.
7. Đổi key/token/method/URI/ath/nonce để xác nhận từng điều kiện bị từ chối.
8. Xác minh không có đường Bearer fallback cho DPoP-bound token.

### 22.3. Kiểm thử nhiều replicas

Nếu replay cache dùng distributed store:

~~~text
Request P -> Node A -> jti insert success -> accept
Replay P  -> Node B -> jti already exists -> reject
~~~

Nếu Node B vẫn chấp nhận P, replay defense chỉ có hiệu lực local và chưa đạt yêu cầu toàn cluster. Kiểm tra atomic insert, TTL, store outage và cách fail-closed khi replay state không truy cập được.

### 22.4. Kiểm thử qua proxy thật

Gửi request qua gateway/ingress, không chỉ gọi trực tiếp localhost:

- External scheme/host/port đúng.
- Forwarded headers bị giả mạo từ client không được tin.
- Path normalization/URL encoding không làm sai `htu`.
- Redirect không làm proof/token bị gửi sang origin ngoài policy.
- Nonce response và lần thử lại giữ đúng request binding.

## 23. Vận hành và quan sát

Các số liệu hữu ích:

- DPoP proof verification success/failure theo nhóm nguyên nhân.
- Token validation failures riêng với proof failures.
- Thumbprint binding mismatch.
- Replay detections và nonce challenge counts.
- Proof age distribution.
- Replay cache size/eviction/store errors.
- Clock skew và sai lệch URI do proxy.
- Tỷ lệ client gửi nhầm Bearer scheme với DPoP-bound token.

Không ghi log:

- Access Token nguyên văn.
- Compact DPoP proof nguyên văn.
- Private JWK/key material.
- Authorization header.
- Full user claims không cần thiết.

Có thể log request correlation ID, error category và metadata không nhạy cảm. Nếu cần điều tra theo key, cân nhắc fingerprint có kiểm soát, giới hạn truy cập và retention.

### 23.1. Replay store outage

Nếu không thể kiểm tra `jti` do replay store unavailable:

- Với endpoint yêu cầu DPoP replay protection, không mặc nhiên bỏ qua replay check để tăng availability.
- Có thể từ chối request theo fail-closed policy hoặc dùng fallback có bảo đảm tương đương đã được phê duyệt.
- Phát cảnh báo vì lỗi replay store có thể ảnh hưởng cả bảo mật lẫn availability.

### 23.2. Clock synchronization

Proof dùng `iat` và nonce lifetime; đồng hồ giữa client, gateway và server có thể lệch. Cần:

- Đồng bộ clock của server nodes.
- Cấu hình allowed clock skew có giới hạn.
- Đo proof age và reject reason.
- Không mở cửa sổ quá rộng chỉ để chữa client clock lỗi.

## 24. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Coi DPoP proof là Access Token. | Dùng JWT proof như credential mang scope. | Token cấp quyền; proof chứng minh possession. |
| Gửi private key trong JWK header. | Lộ private credential. | Chỉ đưa public JWK. |
| Dùng signing key của AS để ký proof. | Nhầm hai trust domains. | Client ký bằng DPoP private key riêng. |
| Dùng một proof cho nhiều requests. | Replay và method/URI binding sai. | Tạo proof mới cho mỗi request. |
| Bỏ `ath` trên resource request. | Proof không gắn với token gửi kèm. | Hash Access Token theo RFC 9449. |
| So `cnf.jkt` với một public key chưa verify đúng profile. | Có thể chấp nhận key không khớp token. | Tính RFC 7638 thumbprint từ proof JWK. |
| Chỉ kiểm tra chữ ký proof. | Bỏ qua htm/htu/iat/jti/ath/nonce. | Thực thi toàn bộ DPoP validation. |
| Chỉ kiểm tra iat, không replay cache. | Proof có thể được dùng lại trong time window. | Atomic `jti` replay detection. |
| Replay cache chỉ local trong cluster. | Cùng proof có thể qua node khác. | Shared/consistent replay defense. |
| Dùng DPoP thay TLS. | Body/response không được mã hóa. | Vẫn bắt buộc HTTPS. |
| Cho rằng DPoP ký body/query. | Hiểu sai phạm vi htu/ath. | Validate payload riêng; DPoP không ký toàn message. |
| Tin X-Forwarded-Host từ client. | Bypass URI binding. | Trusted proxy/canonical URI configuration. |
| Fallback sang Bearer khi proof lỗi. | Vô hiệu sender constraint. | Từ chối DPoP-bound token nếu thiếu proof. |
| Cache proof và reuse. | Replay detection từ chối hoặc proof không đúng request. | Sinh proof theo request. |
| Không xử lý nonce challenge. | Client/server không hoàn thành DPoP flow. | Tạo proof mới có nonce hợp lệ. |
| Nghĩ non-extractable key chống XSS hoàn toàn. | XSS vẫn có thể gọi signing API. | CSP, origin security và secure client design. |
| Nghĩ DPoP tự chứng minh user identity. | Lẫn client key possession với user authentication. | OIDC/OAuth authentication và authorization riêng. |
| Chỉ cấu hình `oauth2ResourceServer().jwt()` rồi cho rằng đã bật DPoP. | Access Token được verify nhưng proof có thể bị bỏ qua. | DPoP-aware integration đúng version và test. |

## 25. Lộ trình triển khai

1. **Xác định client types:** browser, native mobile, desktop hay confidential backend; quyết định nơi tạo/lưu private key.
2. **Xác nhận AS hỗ trợ RFC 9449:** token endpoint nhận DPoP proof, phát token type DPoP và confirmation binding `cnf.jkt`.
3. **Thống nhất thuật toán/key policy:** asymmetric algorithm allowlist, JWK thumbprint và key rotation.
4. **Thiết kế token issuance:** proof cho token endpoint, nonce challenge, Access Token được bind với đúng public key.
5. **Thiết kế Resource Server validation:** token, `cnf.jkt`, proof signature, htm/htu/iat/jti/ath/nonce.
6. **Chọn replay store:** TTL theo proof acceptance window, atomic insert và consistency giữa replicas.
7. **Tích hợp Spring Security theo đúng version:** không giả định JWT/opaque Resource Server mặc định đã kiểm tra DPoP; đặt verifier trước authorization.
8. **Cấu hình proxy URI trust:** canonical external URI, forwarded headers từ proxy đáng tin, redirects.
9. **Kiểm thử negative cases:** thiếu proof, wrong key, wrong ath, replay, nonce, URI/method mismatch, Bearer downgrade.
10. **Bảo vệ key lifecycle:** secure storage, recovery, compromise, re-issuance và token revocation.
11. **Đo vận hành:** proof failures, replay hits, nonce challenges, clock skew, replay store health.
12. **Giữ TLS và domain authorization:** DPoP không thay confidentiality, scope hoặc tenant/owner checks.

**Ghi nhớ:** **Access Token** mang quyền truy cập; **DPoP proof JWT** được client ký bằng private key để chứng minh quyền sở hữu khóa cho một HTTP request. Proof chứa public JWK và các claim ràng buộc method, URI, thời gian, ID duy nhất và hash Access Token. Authorization Server gắn token với khóa qua **`cnf.jkt`**; Resource Server phải xác minh token, proof signature, thumbprint, `htm`/`htu`/`iat`/`jti`/`ath` và nonce/replay policy trước khi xét quyền. DPoP giảm rủi ro token bị đánh cắp đơn lẻ, nhưng **không thay Access Token, TLS, secure key storage hoặc authorization**.

## Tài liệu tham khảo

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449).
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html).
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html).
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html).
