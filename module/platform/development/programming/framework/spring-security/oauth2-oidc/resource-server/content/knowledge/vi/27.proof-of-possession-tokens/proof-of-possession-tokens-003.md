# Authorization scheme DPoP và header chứa DPoP proof

**Demonstrating Proof of Possession (DPoP)** là cơ chế ở tầng ứng dụng của OAuth 2.0 giúp ràng buộc access token với một cặp khóa do client sở hữu. Khi gọi API, client không chỉ gửi access token; nó còn ký một **DPoP proof** mới cho request bằng private key tương ứng. Resource Server kiểm tra proof, xác nhận proof được ký bằng đúng khóa đã ràng buộc với token, rồi mới xử lý quyền truy cập.

Điểm dễ nhầm nhất là DPoP sử dụng **hai thành phần HTTP riêng**:

- Header `Authorization` mang scheme **`DPoP`** và access token đã được ràng buộc khóa.
- Header **`DPoP`** mang một JWT proof được ký cho chính HTTP request hiện tại.

Ví dụ request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <DPoP_BOUND_ACCESS_TOKEN>
DPoP: <SIGNED_DPOP_PROOF_JWT>
~~~

Access token và proof JWT không phải cùng một token. Access token chứa quyền được cấp; proof là bằng chứng ngắn hạn cho thấy client đang sở hữu private key được gắn với access token và đang tạo proof cho method/URI này.

Bài học thuộc chương **Token ràng buộc khóa** của module **Spring Security OAuth 2.0 OIDC Resource Server**. Nội dung đi từ RFC 9449, cấu trúc DPoP proof, cách Authorization Server phát hành token ràng buộc khóa, cách client tạo request, đến cách Resource Server xác minh proof, ngăn replay và tích hợp/kiểm thử trong hệ sinh thái Spring.

> DPoP không thay TLS, không mã hóa access token và không tự giải quyết XSS hoặc việc private key bị đánh cắp. Nó làm giảm khả năng dùng lại một access token bị lấy cắp **mà không có private key tương ứng**. Ví dụ URL, token, khóa và client IDs bên dưới đều là dữ liệu giả lập.

## 1. Vì sao Bearer token cần cơ chế proof of possession?

Với access token Bearer truyền thống, bên nào có token thường có thể trình nó để truy cập API:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

Resource Server kiểm tra token hợp lệ và quyền. Nhưng nếu token bị lộ trong log, browser storage, crash dump, proxy hoặc do malware lấy cắp, attacker có thể replay token từ một máy khác trong thời gian token còn hiệu lực. Với Bearer, possession của chuỗi token là điều kiện chính để sử dụng nó.

DPoP bổ sung **bằng chứng sở hữu private key**:

~~~text
Client tạo key pair:
    public key  (có thể công bố)
    private key (phải giữ bí mật)

Authorization Server:
    bind access token với public key thumbprint

Client gọi Resource Server:
    gửi access token + proof JWT ký bằng private key

Resource Server:
    xác minh access token
    xác minh proof signature và claims
    so thumbprint proof key với token binding
    kiểm tra replay
~~~

Nếu attacker chỉ lấy được access token mà không lấy được private key, họ không thể tự tạo một proof mới hợp lệ cho request của mình. Đây là lợi ích cốt lõi của **sender-constrained access token**.

### 1.1. Bearer và DPoP khác nhau ở request

| Thuộc tính | Bearer token | DPoP-bound access token |
|---|---|---|
| Authorization scheme | `Bearer` | `DPoP` |
| Credential trong `Authorization` | Access token | Access token đã bind với key |
| Header proof riêng | Không yêu cầu | `DPoP: <proof JWT>` |
| Bằng chứng sở hữu key cho từng request | Không | Có |
| Khả năng replay chỉ bằng token bị lộ | Cao hơn | Bị hạn chế nếu private key an toàn |
| TLS/HTTPS | Bắt buộc trong thực tế bảo mật | Vẫn cần |

Không được gửi DPoP-bound access token bằng `Authorization: Bearer` nếu server đã phát hành/định nghĩa nó là token type DPoP. Scheme là một phần của cách client trình bày credential và Resource Server xử lý token.

### 1.2. DPoP là sender constraint ở tầng ứng dụng

DPoP được thiết kế để hoạt động trên HTTP ở tầng ứng dụng, không cần ràng buộc TLS certificate như mutual TLS. Mỗi proof ký một số thuộc tính của request và có thể ràng buộc với access token qua `ath`. Resource Server xác minh rằng proof được ký bằng public key đã được liên kết với token.

DPoP không có nghĩa là:

- Access token được mã hóa bằng public key của client.
- Mọi request có thể dùng lại cùng một proof JWT.
- Client gửi private key trong header.
- Resource Server chỉ cần kiểm tra `DPoP` header mà không kiểm tra access token.
- HTTPS có thể bị bỏ vì request đã được ký.

### 1.3. Hai mục tiêu cần phân biệt

**Token binding** trả lời: “Access token này được ràng buộc với public key nào?”

**Proof validation** trả lời: “Request hiện tại có được ký bằng private key tương ứng, cho đúng method/URI/token, trong thời gian chấp nhận và chưa bị replay không?”

Chỉ đạt cả hai mới tạo được bằng chứng possession phù hợp.

## 2. Các thành phần và thuật ngữ của DPoP

| Thuật ngữ | Ý nghĩa |
|---|---|
| DPoP key pair | Cặp public/private key do OAuth client tạo và quản lý |
| DPoP proof | JWT ngắn hạn được ký bằng private key để chứng minh possession |
| DPoP HTTP header | Header mang compact serialized DPoP proof JWT |
| DPoP authorization scheme | Scheme `DPoP` trong `Authorization` header |
| DPoP-bound access token | Access token có binding tới public key thumbprint |
| `jkt` | JWK thumbprint của public key được bind với token |
| `cnf` | Claim confirmation trong token, có thể chứa `jkt` |
| `ath` | Hash của access token được proof ràng buộc |
| `jti` | Identifier duy nhất của proof JWT |
| `nonce` | Giá trị server đưa ra để proof tiếp theo chứng minh client đã nhận challenge gần đây |

### 2.1. Ai tạo proof và ai xác minh?

~~~text
OAuth Client
  ├─ tạo private/public key
  ├─ ký DPoP proof bằng private key
  └─ gửi public JWK trong proof header

Authorization Server
  ├─ xác minh proof ở token endpoint
  ├─ tính public key thumbprint (jkt)
  └─ phát hành token có confirmation binding

Resource Server
  ├─ xác minh access token
  ├─ đọc token confirmation (cnf.jkt)
  ├─ xác minh proof JWT
  ├─ so proof public key thumbprint với cnf.jkt
  └─ kiểm tra method/URI/ath/iat/jti/nonce
~~~

Tùy token format và kiến trúc, Resource Server có thể đọc `cnf.jkt` từ JWT access token hoặc nhận metadata binding từ một introspection response đáng tin. **Không được lấy binding từ dữ liệu client tự gửi rồi tin nó**.

### 2.2. Một key pair có thể được giữ ở đâu?

Client phải bảo vệ private key:

- SPA có thể dùng Web Crypto API và lưu key trong phạm vi browser phù hợp; mức bảo vệ phụ thuộc browser, origin và khả năng XSS.
- Native/mobile client có thể dùng OS keystore hoặc secure enclave khi khả dụng.
- BFF/confidential client có thể quản lý key phía server trong keystore/HSM hoặc secret/key service.
- Key rotation cần phối hợp với việc cấp token mới, vì access token cũ đang bind với thumbprint cũ.

Không đưa private key vào `DPoP` header, JSON payload, source control hoặc log. Public JWK được gửi trong proof header; **private parameters phải vắng mặt**.

## 3. Hai header HTTP không được nhầm lẫn

DPoP dùng header `Authorization` và header `DPoP` cùng lúc ở request tới Resource Server.

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP eyJhbGciOiJFUzI1NiIs...
DPoP: eyJ0eXAiOiJkcG9wK2p3dCIs...
Accept: application/json
~~~

| Header | Giá trị | Vai trò |
|---|---|---|
| `Authorization` | `DPoP <access-token>` | Trình access token DPoP-bound |
| `DPoP` | `<compact-proof-jwt>` | Chứng minh possession cho HTTP request |

### 3.1. `Authorization: DPoP` không chứa proof

Phần sau là **scheme + access token**:

~~~http
Authorization: DPoP <ACCESS_TOKEN>
~~~

Phần sau là **proof JWT**:

~~~http
DPoP: <SIGNED_DPOP_PROOF_JWT>
~~~

Nếu đặt proof JWT vào `Authorization` thay cho access token, Resource Server không có credential token để kiểm tra scopes/audience. Nếu đặt access token vào `DPoP` header, server không nhận được proof hợp lệ.

### 3.2. Request Bearer và DPoP không hoán đổi tùy ý

~~~http
# Bearer access token
Authorization: Bearer <ACCESS_TOKEN>

# DPoP-bound access token
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <PROOF_JWT>
~~~

Một API có thể hỗ trợ cả Bearer và DPoP trong giai đoạn migration, nhưng cần policy rõ ràng về token type và cách xác thực từng scheme. Không nên âm thầm coi DPoP-bound token là Bearer token nếu mục tiêu là duy trì sender constraint.

### 3.3. DPoP proof là JWT, nhưng không phải access token

DPoP proof là một **JWT có chữ ký bất đối xứng**, thường có JOSE header và claims được quy định bởi RFC 9449. Proof có thời hạn ngắn, gắn với một request, có thể gắn với access token qua `ath` và được kiểm tra chống replay.

Proof không đại diện cho user permission. Nó không mang scope để cấp quyền. Sau khi xác minh proof, Resource Server vẫn phải xác minh access token, audience, issuer, thời hạn và authorization như bình thường.

## 4. Cấu trúc DPoP proof JWT

DPoP proof là compact JWT gồm ba phần:

~~~text
BASE64URL(protected header)
.
BASE64URL(payload claims)
.
BASE64URL(signature)
~~~

Ví dụ JOSE header:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<PUBLIC_X>",
    "y": "<PUBLIC_Y>"
  }
}
~~~

Ví dụ payload cho request API:

~~~json
{
  "jti": "b7d9f2a8-unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1924989000,
  "ath": "<BASE64URL_SHA256_OF_ACCESS_TOKEN>",
  "nonce": "<SERVER_NONCE_IF_REQUIRED>"
}
~~~

Đây là payload minh họa. `nonce` có thể không xuất hiện nếu server chưa yêu cầu nonce; `ath` được yêu cầu cho proof dùng kèm access token ở Resource Server. Token timestamp phải được tạo tại thời điểm request thực, không dùng con số cố định này.

### 4.1. JOSE header

| Trường | Yêu cầu/ý nghĩa |
|---|---|
| `typ` | Phải nhận diện proof type `dpop+jwt` |
| `alg` | Thuật toán chữ ký bất đối xứng được chấp nhận; không dùng `none` |
| `jwk` | Public JSON Web Key dùng để xác minh proof |

Header `jwk` chứa **public key**, không chứa private key. Resource Server phải kiểm tra cấu trúc/thuật toán/key type và policy cho phép. Không dùng thuật toán bất kỳ mà proof tự khai báo nếu server chưa allowlist.

### 4.2. Claim `htm` — HTTP method

`htm` ghi HTTP method của request mà proof đang đại diện:

~~~json
{
  "htm": "GET"
}
~~~

Nếu client ký proof cho `GET` nhưng request thật là `POST`, Resource Server phải từ chối. So sánh cần theo quy tắc method của HTTP/DPoP và không chuẩn hóa tùy tiện làm hai method khác nhau thành một.

### 4.3. Claim `htu` — HTTP target URI

`htu` ghi URI đích của request. Theo DPoP, query và fragment components không tham gia giá trị `htu`. Ví dụ request:

~~~http
GET https://api.example.test/api/orders/42?expand=items HTTP/1.1
~~~

Proof có thể mang:

~~~json
{
  "htu": "https://api.example.test/api/orders/42"
}
~~~

Không đưa `?expand=items` hoặc fragment vào `htu`. Cách so khớp URI cần tuân thủ quy tắc chuẩn hóa của RFC 9449, đặc biệt khi có reverse proxy, scheme/host rewrite hoặc port mapping. Client và Resource Server phải tính cùng target URI theo hợp đồng, không tự dùng một chuỗi URL do header không tin cậy chỉ định.

### 4.4. Claim `iat` — thời điểm tạo proof

`iat` là thời điểm proof được tạo, biểu diễn Unix NumericDate. Resource Server kiểm tra proof đủ mới theo cửa sổ thời gian cho phép.

~~~json
{
  "iat": 1924989000
}
~~~

Proof cũ hoặc timestamp nằm quá xa tương lai/quá khứ cần bị từ chối theo policy. Clock skew phải được cấu hình có giới hạn; cửa sổ quá rộng làm tăng thời gian replay có thể xảy ra.

### 4.5. Claim `jti` — proof identifier

`jti` là identifier duy nhất của proof. Client nên tạo giá trị khó đoán/không trùng cho từng proof, chẳng hạn UUID ngẫu nhiên đủ chất lượng hoặc random identifier thích hợp.

Resource Server có thể lưu (thumbprint key, `jti`) trong replay cache trong cửa sổ chấp nhận. Nếu cùng proof được gửi lần nữa, server phát hiện replay và từ chối. `jti` không thay chữ ký và không thay kiểm tra `iat`.

### 4.6. Claim `ath` — access token hash

Khi proof được dùng cùng access token ở Resource Server, `ath` ràng buộc proof với chính token đang trình. Giá trị được tính từ access token:

~~~text
ath = BASE64URL-ENCODE(SHA-256(ASCII(access_token)))
~~~

Không thêm padding vào Base64URL output. Phải hash **đúng chuỗi access token được gửi trong `Authorization`**, không hash proof JWT, decoded payload, token prefix hoặc một representation đã sửa.

Nếu attacker thay access token trong Authorization header nhưng giữ nguyên proof, `ath` không khớp và request bị từ chối.

### 4.7. Claim `nonce` — server challenge

Resource Server hoặc Authorization Server có thể yêu cầu client dùng nonce gần đây. Server gửi nonce trong response header `DPoP-Nonce`; client đặt giá trị đó trong claim `nonce` của proof kế tiếp.

Nonce giúp server chứng minh proof được tạo sau khi client nhận challenge, giảm khả năng dùng proof được chuẩn bị trước. Nonce không thay `jti`/replay cache và không phải access token.

## 5. Luồng DPoP tại Authorization Server và Resource Server

DPoP có hai thời điểm quan trọng: **lấy access token** và **dùng access token gọi API**. Cả hai có thể dùng DPoP proof, nhưng proof được tạo cho endpoint/method tương ứng.

### 5.1. Bước đầu: client tạo key pair

Client tạo cặp khóa bất đối xứng:

~~~text
Private key: dùng ký proof, giữ trong client
Public key:  được biểu diễn thành public JWK, đưa vào proof header
~~~

Client phải giữ key pair nhất quán trong thời gian token bị ràng buộc với key đó. Nếu client mất private key hoặc đổi key, token đã bind với key cũ không tự động trở thành token dùng được với key mới.

### 5.2. Client gửi token request có DPoP proof

Ví dụ Authorization Code grant:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <TOKEN_ENDPOINT_DPOP_PROOF>

grant_type=authorization_code&
code=<AUTHORIZATION_CODE>&
redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback&
client_id=shop-spa-client&
code_verifier=<PKCE_CODE_VERIFIER>
~~~

Proof ở token endpoint phải ràng buộc với:

~~~json
{
  "htm": "POST",
  "htu": "https://login.example.test/oauth2/token",
  "iat": 1924989000,
  "jti": "<UNIQUE_PROOF_ID>"
}
~~~

**Không có `ath` ở proof token request thông thường** vì request đang yêu cầu access token, chưa trình access token đó tới Resource Server. Nếu AS yêu cầu nonce, proof còn có claim `nonce`.

Với confidential client, cơ chế xác thực client (ví dụ client secret/private_key_jwt/mTLS theo đăng ký) vẫn có thể được yêu cầu song song. DPoP proof không tự thay thế mọi phương thức client authentication; nó cung cấp **proof of possession key** cho token binding.

### 5.3. Authorization Server xác minh proof và bind token

Authorization Server cần:

1. Parse DPoP compact JWT và yêu cầu `typ=dpop+jwt`.
2. Chỉ chấp nhận thuật toán chữ ký bất đối xứng theo policy.
3. Lấy public JWK trong proof header, xác minh chữ ký.
4. Kiểm tra `htm`, `htu`, `iat`, `jti` và nonce nếu yêu cầu.
5. Tính JWK thumbprint theo RFC 7638.
6. Gắn thumbprint vào access token dưới confirmation claim `cnf.jkt`.
7. Trả token với `token_type=DPoP` khi cấp DPoP-bound access token.

Access token JWT minh họa:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read",
  "cnf": {
    "jkt": "<THUMBPRINT_OF_CLIENT_PUBLIC_JWK>"
  },
  "exp": 1924992000
}
~~~

Với opaque token, binding có thể được Resource Server lấy qua introspection response hoặc cơ chế tin cậy tương đương. Dù token là JWT hay opaque, điều quan trọng là **server phải có confirmation binding được issuer bảo đảm**.

Response token endpoint minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<DPoP_BOUND_ACCESS_TOKEN>",
  "token_type": "DPoP",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

### 5.4. Client gọi Resource Server với hai header

Client ký proof mới cho từng request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <DPoP_BOUND_ACCESS_TOKEN>
DPoP: <NEW_PROOF_FOR_THIS_REQUEST>
~~~

Payload proof cho request API có:

~~~json
{
  "jti": "<FRESH_UNIQUE_PROOF_ID>",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1924989050,
  "ath": "<HASH_OF_THE_ACCESS_TOKEN>"
}
~~~

Client **không tái sử dụng proof của token endpoint** cho API call; endpoint, method và token hash khác. Client cũng không nên cache một proof rồi gắn nó vào nhiều request, kể cả khi request cùng method/URL.

### 5.5. Resource Server kiểm tra token và proof

Resource Server kiểm tra:

- Access token hợp lệ: issuer, signature/introspection, audience, expiry, scopes và confirmation binding.
- Proof JWT hợp lệ: typ, alg, public JWK, signature.
- `htm` và `htu` khớp request đang xử lý.
- `iat` nằm trong freshness window.
- `jti` chưa được dùng trong replay window.
- `ath` đúng access token trong Authorization header.
- `nonce` phù hợp nếu server đã yêu cầu nonce.
- Thumbprint public key trong proof khớp `cnf.jkt` trong access token.

Chỉ sau khi hoàn tất những kiểm tra bắt buộc, server mới tạo authentication context và áp authorization cho endpoint.

### 5.6. Sequence diagram tổng thể

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Generate/hold DPoP key pair
    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof and calculate JWK thumbprint
    AS-->>C: Access token (token_type=DPoP, cnf.jkt)
    C->>C: Sign new proof (htm, htu, iat, jti, ath)
    C->>RS: Authorization: DPoP token + DPoP proof
    RS->>RS: Validate access token and cnf.jkt
    RS->>RS: Validate proof signature/claims/replay/nonce
    alt Token and proof valid
        RS-->>C: API response
    else Invalid token/proof
        RS-->>C: Authentication error / DPoP nonce challenge
    end
~~~

## 6. Cách tạo proof cho từng loại request

### 6.1. Proof ở token endpoint

Token endpoint nhận `DPoP` header, proof có `htm=POST` và `htu` là URI token endpoint. Access token chưa được phát hành nên không có `ath` ràng buộc với token mới. Proof vẫn cần `jti` và `iat`; server có thể yêu cầu `nonce`.

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
DPoP: <PROOF_SIGNED_BY_CLIENT_PRIVATE_KEY>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read
~~~

Với Client Credentials grant, AS vẫn phải kiểm tra client được phép yêu cầu scopes/resource và gắn access token với DPoP key của request nếu cấp DPoP-bound token. DPoP không tự biến một client thành principal có quyền user.

### 6.2. Proof ở Resource Server

Request API đã có access token, vì vậy proof phải chứa `ath`:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <PROOF_WITH_ATH>
~~~

Nếu thiếu `ath`, hash không khớp hoặc proof ràng buộc với một token khác, Resource Server từ chối.

### 6.3. Mỗi request mới cần proof mới

Ví dụ hai request:

~~~text
Request A:
    GET /api/orders/42
    jti = proof-001
    ath = hash(access-token-A)

Request B:
    GET /api/orders/43
    jti = proof-002
    ath = hash(access-token-A)
~~~

Hai request có thể cùng access token/key, nhưng `jti` phải khác và proof được ký riêng cho method/URI tương ứng. Nếu request retry ở HTTP client hoặc gateway, cần tạo proof mới cho lần gửi lại; gửi lại nguyên proof có thể bị replay detection từ chối.

### 6.4. Redirects và proxy rewriting

DPoP proof gắn với `htu`. Nếu client ký cho URL A nhưng HTTP client tự redirect sang URL B, proof cũ không còn đại diện đúng URI đích. Không tự động forward access token/proof qua redirect sang host khác. Client phải áp chính sách redirect an toàn, xác minh origin và tạo proof mới nếu redirect được phép.

Reverse proxy có thể nhận HTTPS ở edge rồi forward HTTP tới ứng dụng. Nếu Resource Server tự nhìn thấy URI nội bộ, nó có thể so `htu` sai với URL công khai client ký. Cần một cấu hình trusted proxy rõ ràng để dựng external URI đúng; **không tin tùy tiện `Forwarded`/`X-Forwarded-*` từ bất kỳ client nào**.

## 7. JWK thumbprint và claim confirmation `cnf.jkt`

DPoP proof header chứa public JWK. Resource Server không thể chỉ thấy “proof có chữ ký hợp lệ” rồi chấp nhận; attacker có thể tự tạo key pair của mình và ký proof bằng key đó. Server cần chứng minh public key trong proof chính là key mà Authorization Server đã bind với access token.

### 7.1. JWK thumbprint là gì?

**JWK thumbprint** là fingerprint tính từ các thành viên public-key cần thiết của JWK theo RFC 7638, được serialize theo quy tắc canonical rồi hash. DPoP sử dụng SHA-256 để tạo key thumbprint `jkt`.

Với EC P-256, các thành viên dùng để tính thumbprint gồm:

~~~json
{
  "crv": "P-256",
  "kty": "EC",
  "x": "<PUBLIC_X>",
  "y": "<PUBLIC_Y>"
}
~~~

Với RSA, các thành viên public tương ứng là `e`, `kty` và `n`. Các field phụ như `kid`, `alg` hoặc private parameters không được coi là phần tùy ý để tự thay đổi cách tính thumbprint; hãy dùng implementation JWK thumbprint tuân thủ RFC 7638.

### 7.2. Token binding trong claim `cnf`

JWT access token DPoP-bound có thể chứa:

~~~json
{
  "cnf": {
    "jkt": "BASE64URL_SHA256_JWK_THUMBPRINT"
  }
}
~~~

`cnf` là **confirmation claim**. `jkt` xác định public key thumbprint mà token bị ràng buộc. Khi Resource Server đọc token đã được xác minh:

~~~text
accessToken.cnf.jkt
        ==
thumbprint(proof.header.jwk)
~~~

Nếu không bằng nhau, proof được ký bằng một key khác với key token yêu cầu; server từ chối, dù proof signature của key đó tự nó hợp lệ.

### 7.3. Ví dụ hai client key khác nhau

~~~text
Client key A:
    public JWK = JWK-A
    thumbprint = JKT-A
    access token cnf.jkt = JKT-A

Request proof ký bởi private key A:
    header.jwk = JWK-A
    signature valid
    thumbprint = JKT-A
    → binding matches

Request proof ký bởi private key B:
    header.jwk = JWK-B
    signature valid under B
    thumbprint = JKT-B
    → binding mismatch, reject
~~~

### 7.4. Không tin `cnf` do client tự khai

Client không được tự thêm `cnf.jkt` vào access token và mong Resource Server tin. Với JWT access token, `cnf` phải nằm trong token có chữ ký issuer tin cậy. Với opaque token, Resource Server phải lấy binding từ introspection/metadata được Authorization Server xác thực.

Proof header `jwk` là do client gửi, nên nó chỉ trở thành bằng chứng khi:

1. Proof signature được xác minh bằng chính public JWK đó.
2. Public JWK thumbprint khớp `cnf.jkt` đã xác minh từ access token.
3. Các claims proof và replay checks hợp lệ.

### 7.5. Token không có confirmation binding

Nếu Resource Server đang xử lý một token được cho là DPoP-bound nhưng không có `cnf.jkt` hoặc binding tương đương, không tự lấy JWK từ proof rồi coi đó là binding. Khi server không có bằng chứng token gắn với key nào, **proof possession không được ràng buộc với access token**.

Nếu API hỗ trợ cả Bearer và DPoP token, phải xác định scheme/policy riêng cho từng loại. Một access token Bearer bình thường không thể trở thành DPoP-bound chỉ bằng cách client thêm header `DPoP`.

## 8. Tạo DPoP proof JWT bằng Java và Nimbus JOSE/JWT

Để hiểu client tạo hai header thế nào, có thể dùng Nimbus JOSE/JWT. Ví dụ dưới đây tạo EC P-256 key pair, public JWK, `ath` và proof cho một HTTP request. Nó minh họa **phần ký proof**, không phải toàn bộ OAuth client hay một thư viện DPoP production hoàn chỉnh.

### 8.1. Tạo key pair EC

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.spec.ECGenParameterSpec;

KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
generator.initialize(new ECGenParameterSpec("secp256r1"));
KeyPair dpopKeyPair = generator.generateKeyPair();
~~~

`secp256r1` tương ứng với đường cong P-256 dùng cho ES256. Cần giữ `dpopKeyPair.getPrivate()` trong key storage phù hợp. Không serialize private key vào request.

### 8.2. Tạo `ath` từ access token

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

Đây là cách tính `ath` theo DPoP: SHA-256 trên ASCII bytes của access token rồi Base64URL không padding. Không hash chuỗi `"Bearer "`/`"DPoP "` đi kèm trong HTTP header; chỉ hash **giá trị access token**.

### 8.3. Tạo public JWK và ký proof

~~~java
import java.security.interfaces.ECPrivateKey;
import java.security.interfaces.ECPublicKey;
import java.security.KeyPair;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.ECDSASigner;
import com.nimbusds.jose.jwk.Curve;
import com.nimbusds.jose.jwk.ECKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

static String createDpopProof(
        KeyPair keyPair,
        String httpMethod,
        String htu,
        String accessToken,
        String nonce) throws Exception {

    ECKey publicJwk = new ECKey.Builder(
            Curve.P_256,
            (ECPublicKey) keyPair.getPublic())
        .build();

    Instant now = Instant.now();
    JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
        .jwtID(UUID.randomUUID().toString())
        .claim("htm", httpMethod)
        .claim("htu", htu)
        .issueTime(Date.from(now));

    if (accessToken != null) {
        claims.claim("ath", accessTokenHash(accessToken));
    }

    if (nonce != null && !nonce.isBlank()) {
        claims.claim("nonce", nonce);
    }

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.ES256)
        .type(new JOSEObjectType("dpop+jwt"))
        .jwk(publicJwk)
        .build();

    SignedJWT proof = new SignedJWT(header, claims.build());
    proof.sign(new ECDSASigner((ECPrivateKey) keyPair.getPrivate()));
    return proof.serialize();
}
~~~

`accessToken` có thể là `null` khi tạo proof cho token endpoint (chưa có access token để hash). Với Resource Server request, truyền access token để tạo `ath`. `htu` phải là target URI theo quy tắc DPoP, loại query/fragment; `httpMethod` phải là method thực.

Đoạn code trên dùng `UUID` làm `jti` minh họa. Production cần nguồn random đủ mạnh, tránh collision và quản lý key lifecycle. Thư viện/phiên bản Nimbus có thể khác overload; khi áp dụng phải dùng API phù hợp với dependency đang khóa trong dự án.

### 8.4. Gửi request với hai header

Sau khi có `accessToken` và `proof`:

~~~java
String proof = createDpopProof(
    dpopKeyPair,
    "GET",
    "https://api.example.test/api/orders/42",
    accessToken,
    serverNonce
);

// Pseudocode: dùng HTTP client của ứng dụng.
request.header("Authorization", "DPoP " + accessToken);
request.header("DPoP", proof);
~~~

Hai dòng `request.header(...)` là **pseudocode**, không phải một API HTTP client cụ thể. Với Spring `WebClient`, Java `HttpClient` hoặc SDK OAuth client, phải dùng API request builder tương ứng. Đừng log hai giá trị header khi debug.

### 8.5. Tạo proof cho token endpoint

~~~java
String tokenEndpointProof = createDpopProof(
    dpopKeyPair,
    "POST",
    "https://login.example.test/oauth2/token",
    null,            // Chưa có access token, nên không có ath
    serverNonce      // null nếu AS chưa yêu cầu nonce
);
~~~

Token endpoint request vẫn đặt proof vào **header `DPoP`**:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <TOKEN_ENDPOINT_PROOF>

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&...
~~~

## 9. Resource Server xác minh DPoP proof như thế nào?

Không nên triển khai logic chỉ dựa trên một phép verify chữ ký. Một proof có signature đúng vẫn có thể:

- Dùng sai HTTP method hoặc URI.
- Gắn với access token khác.
- Được tạo quá lâu hoặc nằm trong tương lai.
- Đã bị sử dụng trước đó.
- Được ký bằng key không khớp token binding.
- Thiếu nonce mà server yêu cầu.

### 9.1. Trình tự validation ở mức khái niệm

~~~text
1. Parse Authorization: DPoP <access-token>
2. Lấy DPoP proof JWT từ header DPoP
3. Validate access token:
     signature/introspection
     issuer, audience, expiry, scope
     confirmation binding cnf.jkt
4. Validate proof JOSE header:
     typ=dpop+jwt
     allowed asymmetric alg
     public jwk only
     verify signature
5. Validate proof claims:
     htm == current HTTP method
     htu == current target URI (without query/fragment)
     iat within accepted time window
     ath == hash(presented access token)
     nonce valid when required
6. Check jti has not been used (replay detection)
7. Compare thumbprint(proof jwk) == access token cnf.jkt
8. Only then establish authenticated principal
9. Apply scope/role and domain authorization
~~~

Thứ tự thực tế có thể tối ưu để giảm DoS/cost, nhưng **không được bỏ điều kiện bắt buộc**. Ví dụ server có thể parse token header/claims sau khi kiểm tra chữ ký; không được tin `cnf.jkt` trước khi xác minh token.

### 9.2. Validate `typ` và `alg`

Server phải yêu cầu proof JWT type đúng `dpop+jwt` và thuật toán bất đối xứng được hỗ trợ. Các thuật toán đối xứng như HS256 không phù hợp vì server sẽ cần một shared secret, làm mất mô hình public-key proof. `alg=none` tuyệt đối không được chấp nhận.

Public JWK phải có key type/curve/parameters hợp lệ cho thuật toán đã chọn. Không chấp nhận private parameters trong `jwk` proof header; proof chỉ cần public key để verifier kiểm tra chữ ký.

### 9.3. Verify chữ ký bằng public JWK trong proof

Khác với JWT access token, proof key được client gửi trong header `jwk`. Server parse public JWK, xác minh chữ ký của chính proof rồi mới dùng thumbprint để so với binding trong access token.

Việc proof tự mang public JWK không tạo ra trust một cách độc lập. **Trust đến từ việc key thumbprint khớp confirmation binding do issuer phát hành trong access token đã xác minh**.

### 9.4. Kiểm tra `htm`

So `htm` với method HTTP thật. Proof `GET` không hợp lệ cho request `POST`; không coi `GET` và `get` là cùng một proof claim nếu contract/implementation không chuẩn hóa đúng theo RFC.

### 9.5. Kiểm tra `htu`

Tính target URI từ request theo quy tắc DPoP:

- Scheme và authority/host phải phản ánh đúng URI đích.
- Query và fragment bị loại khỏi `htu`.
- Cách chuẩn hóa/so sánh phải theo RFC 9449, không dùng phép so chuỗi tùy tiện.
- Nếu có reverse proxy, chỉ dùng forwarded metadata từ proxy được tin cậy.
- Không dùng host do request tùy ý gửi để chọn một audience/issuer khác.

### 9.6. Kiểm tra `iat` và thời gian

Server cần đặt một freshness window đủ hẹp nhưng cho phép sai lệch đồng hồ hợp lý. Ví dụ policy minh họa có thể chấp nhận proof được tạo trong 60 giây gần đây, nhưng con số thật phải dựa vào clock synchronization, latency và threat model.

Không dùng cửa sổ quá dài; nó kéo dài thời gian proof bị đánh cắp có thể được replay. Đồng thời, đồng hồ client/server lệch lớn có thể khiến request hợp lệ bị từ chối. Đồng bộ thời gian hệ thống là một phần của vận hành DPoP.

### 9.7. Kiểm tra `ath`

Resource Server lấy access token từ Authorization header, tự tính `BASE64URL(SHA-256(token))` rồi so sánh chính xác với claim `ath` của proof. Nếu khác hoặc thiếu, từ chối.

Điều này ngăn attacker ghép proof hợp lệ của token A với access token B. Server không lấy `ath` từ header khác hoặc từ dữ liệu client tự khai ngoài proof đã ký.

### 9.8. So khớp `cnf.jkt`

Sau khi xác minh access token và proof:

~~~text
token.cnf.jkt
    ==
RFC7638_SHA256_JWK_THUMBPRINT(proof.header.jwk)
~~~

Nếu mismatch, proof key không phải key đã bind với token. **Không fallback sang Bearer authentication** chỉ vì DPoP binding sai.

### 9.9. Kiểm tra replay bằng `jti`

Server lưu proof identifier đã chấp nhận trong một replay cache có TTL phù hợp với freshness window. Key cache thường cần gắn với thumbprint (hoặc namespace tin cậy) và `jti` để tránh collision giữa clients:

~~~text
replay-cache-key = thumbprint + ":" + jti
ttl              = proof acceptance window
~~~

Thao tác kiểm tra-và-ghi phải **atomic** trong hệ thống nhiều node. Nếu mỗi instance giữ cache riêng, attacker có thể gửi cùng proof tới node A rồi node B và cả hai cùng chấp nhận. Dùng shared/distributed cache hoặc cơ chế đồng bộ đủ mạnh; nếu replay store unavailable, policy phải xác định rõ và không âm thầm bỏ replay detection.

### 9.10. Kiểm tra nonce

Nếu server yêu cầu nonce, proof tiếp theo phải có claim `nonce` phù hợp với nonce server phát. Nonce cần có entropy và thời hạn/validation policy phù hợp. Server có thể phát nonce mới trong response header để client dùng ở request tiếp theo.

Nonce và `jti` phục vụ hai mục đích khác nhau:

| Cơ chế | Chống/đáp ứng |
|---|---|
| `jti` + replay cache | Phát hiện proof đã được sử dụng lại |
| `iat` freshness | Giới hạn tuổi của proof |
| `nonce` | Ràng buộc proof với challenge gần đây do server tạo |

Không coi nonce là lý do để bỏ kiểm tra `jti` hoặc `iat`.

## 10. Nonce challenge và cách client xử lý

Nonce là một phần của giao thức request/response giữa client và server. Client không tự nghĩ ra nonce thay server; server phát nonce và client đưa nó vào **proof mới**.

### 10.1. Resource Server yêu cầu nonce

Ví dụ client gửi request nhưng chưa có nonce được server chấp nhận:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <PROOF_WITHOUT_REQUIRED_NONCE>
~~~

Resource Server có thể trả challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DPoP error="use_dpop_nonce"
DPoP-Nonce: <SERVER_GENERATED_NONCE>
Cache-Control: no-store
~~~

Client nhận `DPoP-Nonce` và tạo proof mới:

~~~json
{
  "jti": "<NEW_UNIQUE_PROOF_ID>",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders",
  "iat": 1924989100,
  "ath": "<HASH_OF_ACCESS_TOKEN>",
  "nonce": "<SERVER_GENERATED_NONCE>"
}
~~~

Sau đó client gửi lại request với cùng access token nếu token vẫn hợp lệ, nhưng **DPoP proof mới**:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <NEW_PROOF_WITH_NONCE>
~~~

### 10.2. Nonce ở token endpoint

Authorization Server cũng có thể yêu cầu nonce trong quá trình lấy/refresh token. Token endpoint thường trả lỗi OAuth `use_dpop_nonce` cùng header `DPoP-Nonce`; client cần tạo proof mới có claim `nonce` rồi gửi lại token request.

Ví dụ response minh họa:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
DPoP-Nonce: <AS_NONCE>
Cache-Control: no-store

{
  "error": "use_dpop_nonce",
  "error_description": "A fresh DPoP proof with the supplied nonce is required."
}
~~~

Mã HTTP và chi tiết response phải theo contract/RFC và implementation của endpoint; client nên phân biệt token endpoint với Resource Server challenge.

### 10.3. Client không gửi lại proof cũ

Sau challenge, tạo một proof JWT mới:

- `jti` mới.
- `iat` mới.
- Claim `nonce` mới nhất do đúng server cung cấp.
- `htm`/`htu` vẫn khớp request được gửi lại.
- `ath` vẫn hash đúng access token được trình.
- Ký bằng private key đã bind với access token.

Không chỉ nối thêm `nonce` vào payload của JWT cũ rồi giữ signature cũ. Mọi thay đổi payload đều cần ký lại. Không dùng nonce của Authorization Server cho Resource Server khác, trừ khi contract định nghĩa rõ phạm vi chia sẻ.

### 10.4. Nonce có thể thay đổi qua nhiều response

Server có thể phát nonce mới trong response; client nên quản lý nonce theo đúng **server/authority và context** thay vì một biến toàn cục dùng cho mọi issuer/resource. Một nonce cũ có thể hết hạn hoặc bị server thay thế. Client phải sẵn sàng xử lý challenge và không tạo vòng lặp vô hạn khi server liên tục trả `use_dpop_nonce`.

### 10.5. Retry sau nonce challenge cần được giới hạn

Một lần retry sau `use_dpop_nonce` là bước protocol bình thường, nhưng cần:

- Giới hạn số lần challenge liên tiếp để tránh loop.
- Mỗi lần retry tạo proof mới.
- Giữ nguyên resource/issuer trust policy.
- Không retry vô hạn khi nonce sai, proof invalid hoặc token hết hạn.
- Không log nonce cùng raw token trong HTTP wire logs nếu dữ liệu được coi là nhạy cảm.

## 11. Error handling và HTTP response

DPoP phân biệt lỗi access token, lỗi proof và lỗi nonce. Resource Server nên ánh xạ lỗi theo nguyên nhân, nhưng không tiết lộ chi tiết nội bộ không cần thiết.

| Lỗi | Ý nghĩa | Cách xử lý thường gặp |
|---|---|---|
| `invalid_token` | Access token không hợp lệ/hết hạn/không đúng binding | Authentication thất bại |
| `invalid_dpop_proof` | Proof không hợp lệ: chữ ký, claim, method, URI, `ath`, replay... | Từ chối request |
| `use_dpop_nonce` | Server yêu cầu nonce mới trong proof | Trả nonce challenge |
| Thiếu DPoP header | Request dùng DPoP scheme nhưng không có proof | Từ chối |
| Scheme Bearer với DPoP-bound token | Client dùng sai authorization scheme hoặc policy | Từ chối theo token binding/scheme policy |
| Replay detected | `jti` đã được chấp nhận trước đó | Từ chối proof |

### 11.1. Ví dụ proof không hợp lệ

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DPoP error="invalid_dpop_proof"
Cache-Control: no-store
~~~

Đây là response minh họa; API có thể dùng body lỗi theo format riêng. Không đưa public JWK đầy đủ, access token, signature bytes, private-key data hoặc internal stack trace vào response công khai.

### 11.2. Token invalid và proof invalid không giống nhau

Ví dụ:

~~~text
Access token expired:
    → invalid_token

Access token valid, but proof htm=POST while request is GET:
    → invalid_dpop_proof

Access token valid, proof signed by another key:
    → binding mismatch / invalid_dpop_proof

Access token valid, nonce required but absent:
    → use_dpop_nonce challenge (nếu đây là chính sách nonce)
~~~

Việc phân loại hữu ích cho client và metrics. Nhưng dù lỗi nào, request không được tiếp tục vào controller/service với principal đã xác thực.

### 11.3. `WWW-Authenticate` scheme phải phản ánh DPoP

Khi Resource Server phát challenge cho DPoP authentication, challenge scheme cần phù hợp với DPoP, ví dụ:

~~~http
WWW-Authenticate: DPoP error="invalid_token"
~~~

Đừng mặc định mọi lỗi DPoP đều phát `Bearer error=...`. Client cần nhận diện đúng scheme để thực hiện nonce flow hoặc xử lý token/proof.

## 12. Tích hợp DPoP với Spring Security

Spring Security cung cấp các building blocks cho OAuth 2.0 Resource Server: authentication filters, token converters, `JwtDecoder`/`ReactiveJwtDecoder`, authentication providers/managers và authorization rules. Tuy nhiên, **cấu hình JWT thông thường không tự động chứng minh DPoP đã được triển khai đầy đủ**.

### 12.1. JWT Resource Server thông thường chưa đủ

Ví dụ cấu hình JWT chuẩn:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
~~~

hoặc WebFlux:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
~~~

Những cấu hình này thể hiện JWT resource server authentication. Chúng **không nên được mặc định hiểu là**:

- Chấp nhận scheme `Authorization: DPoP`.
- Đọc và xác minh header `DPoP`.
- Kiểm tra `htm`/`htu`/`ath`/`jti`/nonce.
- Kiểm tra `cnf.jkt` với proof key.
- Duy trì replay cache phân tán.

Khả năng DPoP native, API và DSL phụ thuộc **phiên bản Spring Security/Spring Boot** và implementation đang dùng. Hãy xác nhận tài liệu chính thức đúng version trước khi chọn cấu hình. Nếu version có hỗ trợ DPoP đầy đủ, dùng API được tài liệu mô tả và vẫn kiểm thử các ranh giới bên dưới. Nếu không, cần một integration layer DPoP rõ ràng.

### 12.2. Các trách nhiệm cần có trong integration layer

Một kiến trúc tùy chỉnh cần ít nhất:

| Thành phần | Trách nhiệm |
|---|---|
| Authorization header converter | Phân tích scheme `DPoP` và lấy access token |
| Proof header resolver | Lấy đúng một DPoP proof JWT từ header `DPoP` |
| Access token verifier | Xác minh JWT hoặc introspection: issuer, audience, expiry, scopes |
| DPoP proof verifier | Xác minh JOSE, signature, `htm`, `htu`, `iat`, `ath`, `nonce` |
| JWK thumbprint verifier | So proof key thumbprint với `cnf.jkt` |
| Replay store | Kiểm tra/ghi `jti` một cách atomic |
| Nonce service | Phát, lưu hoặc xác minh nonce theo policy |
| Authentication provider/manager | Chỉ tạo principal khi token và proof đều hợp lệ |
| Authorization layer | Kiểm tra scope/role và quyền nghiệp vụ |

### 12.3. Flow Servlet ở mức khái niệm

~~~text
HTTP request
    |
    v
DPoP Authentication Converter
    |-- Authorization: DPoP <access-token>
    |-- DPoP: <proof>
    v
DPoP Authentication Token (chưa authenticated)
    |
    v
AuthenticationManager / Provider
    |-- verify access token
    |-- verify proof signature + claims
    |-- compare cnf.jkt
    |-- check replay / nonce
    v
Authenticated principal
    |
    v
HTTP / method / domain authorization
~~~

Ở Servlet, một custom `AuthenticationConverter` cùng `AuthenticationManager`/provider có thể là các điểm tích hợp tùy kiến trúc. Có thể dùng filter phù hợp trong security chain, nhưng phải bảo đảm filter chạy **trước authorization** và chỉ set SecurityContext sau khi toàn bộ DPoP validation thành công.

### 12.4. Flow WebFlux ở mức khái niệm

~~~text
ServerWebExchange
    |
    v
ServerAuthenticationConverter
    |-- parse Authorization: DPoP
    |-- parse DPoP proof header
    v
Unauthenticated DPoP Authentication
    |
    v
ReactiveAuthenticationManager
    |-- ReactiveJwtDecoder / introspector
    |-- DPoP proof validation (Mono)
    |-- reactive replay/nonce store
    v
Authenticated Authentication
    |
    v
Reactive authorization rules
~~~

Trong WebFlux, các thao tác replay/nonce store, remote introspection và JWKS retrieval nên giữ reactive/non-blocking behavior phù hợp. Không chặn event loop bằng `Thread.sleep` hoặc synchronous remote cache/database calls.

### 12.5. Không chuyển scheme DPoP thành Bearer rồi bỏ proof

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: scheme DPoP bị hạ thành Bearer.
String token = authorizationHeader.substring("DPoP ".length());
return bearerAuthenticationManager.authenticate(
    new BearerTokenAuthenticationToken(token)
);
~~~

Đoạn trên chỉ lấy access token và gọi Bearer authentication; nó **bỏ hoàn toàn proof header và sender constraint**. Token có thể vẫn được xác thực như Bearer nếu decoder không bắt buộc `cnf`/DPoP, làm mất mục tiêu bảo vệ.

Nếu cần hỗ trợ cả Bearer và DPoP:

- Xử lý scheme Bearer theo chính sách Bearer riêng.
- Xử lý scheme DPoP bằng full proof/binding validation.
- Không tự fallback từ DPoP invalid sang Bearer.
- Không chấp nhận DPoP-bound token qua Bearer nếu policy issuer/server yêu cầu DPoP.

### 12.6. DPoP proof phải được kiểm tra trước khi tạo principal

Không tạo `Authentication` rồi chỉ kiểm tra proof ở controller. Nếu controller/filter sau đó quên kiểm tra hoặc endpoint public bypass, token đã được coi là authenticated dù proof chưa hợp lệ. **DPoP là một phần của authentication**, không phải một optional controller argument.

### 12.7. Authorization Server và OAuth client cũng phải hỗ trợ

Resource Server support không đủ nếu Authorization Server không phát hành DPoP-bound tokens hoặc client không thể tạo proof. Toàn bộ chuỗi cần:

~~~text
OAuth client:
    key management + proof generation + token request

Authorization Server:
    proof validation + token binding + DPoP token_type

Resource Server:
    access token validation + proof validation + replay defense
~~~

Nếu bất kỳ mắt xích nào chỉ xử lý Bearer, DPoP sender constraint có thể không được duy trì.

## 13. DPoP ở phía OAuth client: vòng đời key và proof

Client là nơi tạo proof, vì vậy cần một thành phần chuyên trách thay vì rải logic ký JWT trong từng controller.

### 13.1. Quản lý key theo client instance

Một client instance nên quản lý:

~~~text
DpopKeyManager
  ├─ generate or load key pair
  ├─ expose public JWK
  ├─ sign DPoP proof
  ├─ calculate JWK thumbprint
  ├─ track token -> bound key
  └─ rotate/retire keys
~~~

Nếu ứng dụng có nhiều user/session hoặc nhiều thiết bị, cần quyết định key thuộc phạm vi **browser profile, app installation, client instance, service identity hay session**. Không chia sẻ private key rộng hơn mức cần thiết; nếu một key dùng chung cho nhiều users/instances, sự cố lộ key có phạm vi ảnh hưởng lớn hơn.

### 13.2. Lưu liên hệ giữa access token và key

Client cần biết access token nào được cấp với key nào để tạo proof đúng:

~~~text
Token record:
    access_token = ...
    token_type   = DPoP
    expires_at   = ...
    dpop_key_id  = key-alias-17
~~~

Không cần lưu private key trong token record; chỉ tham chiếu key alias/handle trong secure key store. Access token và refresh token vẫn là credential nhạy cảm, cần mã hóa/bảo vệ theo mô hình client.

### 13.3. Proof được tạo sau khi request đã hoàn tất URL và method

HTTP client interceptor cần biết:

- Method cuối cùng (GET/POST/PUT/PATCH/DELETE...).
- URI đích cuối cùng sau khi base URL và path được ghép.
- Access token thực sự sẽ đặt vào Authorization header.
- Nonce mới nhất của đúng server nếu có.

Sau đó mới ký proof và gắn hai header. Nếu interceptor ký proof trước khi client hoàn tất URL, `htu` có thể không khớp request cuối cùng.

### 13.4. Mỗi retry/redirect tạo proof mới

Khi HTTP client tự retry do network error hoặc 503, proof trước đó đã được gửi hoặc có thể đã được server nhận. Retry phải:

1. Tính lại method/URI thực tế.
2. Tạo `jti` mới.
3. Cập nhật `iat`.
4. Tính lại `ath` nếu access token thay đổi.
5. Thêm nonce hiện tại nếu cần.
6. Ký proof mới bằng private key được bind với token.

Không cache proof như một header tĩnh trong default request builder. Nếu token refresh hoặc key rotation xảy ra, phải đảm bảo proof được tạo bằng đúng key của token đang gửi.

### 13.5. DPoP cho refresh token

Khi Authorization Server phát hành refresh token gắn với DPoP key, client phải tiếp tục dùng key tương ứng khi gửi refresh request theo contract. Việc refresh có thể trả access token mới với cùng hoặc binding được cập nhật theo cơ chế của AS; client không tự suy luận token mới được bind với key khác nếu response/protocol không nói vậy.

Nếu private key bị mất:

- Client có thể không còn khả năng sử dụng access/refresh token đang bind với key đó.
- Thường cần một luồng cấp token mới với key mới theo policy Authorization Server.
- Không thay public JWK trong proof nhưng giữ access token cũ rồi mong token binding tự cập nhật.
- Cần xử lý thu hồi/đăng nhập lại theo vòng đời token và chính sách issuer.

### 13.6. Key rotation

Một access token đã bind với thumbprint `JKT-A` sẽ tiếp tục yêu cầu proof từ key A. Khi client chuyển sang key B:

~~~text
Old token:
    cnf.jkt = JKT-A
    proof must be signed by private key A

New token:
    cnf.jkt = JKT-B
    proof must be signed by private key B
~~~

Không xoay key ngay trong khi vẫn dùng token cũ nếu không có quy trình chuyển tiếp phù hợp. Có thể giữ hai key trong thời gian token cũ còn hiệu lực, nhưng token nào phải dùng key nào cần được lưu/tra cứu chính xác.

## 14. DPoP và reverse proxy, gateway, CORS

DPoP ràng buộc proof với URI và method. Điều này khiến các tầng trung gian cần được cấu hình cẩn thận.

### 14.1. HTTPS termination

Ví dụ:

~~~text
Client
  → https://api.example.test/orders/42
  → Gateway terminates TLS
  → http://orders-service:8080/orders/42
~~~

Client ký `htu` dựa trên URL công khai HTTPS. Backend chỉ thấy HTTP và host nội bộ. Nếu backend so trực tiếp URL nội bộ, proof hợp lệ sẽ thất bại.

Giải pháp kiến trúc:

- Gateway là trusted proxy duy nhất hoặc có danh sách proxy tin cậy.
- Gateway truyền external scheme/host/path theo một hợp đồng rõ ràng.
- Backend chỉ tin forwarded headers từ các proxy đã xác thực/giới hạn network.
- Cấu hình framework để lấy external request URI an toàn, tránh dùng header client tự giả mạo.
- Test cả request trực tiếp và qua gateway theo kiến trúc triển khai.

### 14.2. Path rewriting

Nếu gateway đổi:

~~~text
Public:  /api/orders/42
Internal: /orders/42
~~~

thì cần xác định `htu` mà Resource Server phải so khớp theo URI đích được client sử dụng và cách proxy truyền thông tin gốc. Không tự thêm/bỏ prefix theo một rule tùy tiện; phải thống nhất URI canonicalization ở client, gateway và verifier.

### 14.3. Không tin forwarded headers từ internet

Nếu attacker có thể tự gửi:

~~~http
Forwarded: proto=https;host=api.example.test
X-Forwarded-Host: api.example.test
X-Forwarded-Proto: https
~~~

và ứng dụng lấy trực tiếp chúng làm `htu`, attacker có thể tác động cách server so proof URI. Chỉ chấp nhận forwarded metadata từ trusted proxy; gateway cần loại bỏ header do client gửi trước khi thêm giá trị của nó.

### 14.4. CORS cho header `DPoP`

Browser client cần được phép gửi các header custom trong CORS preflight. Ví dụ policy minh họa:

~~~http
Access-Control-Allow-Headers: Authorization, DPoP, Content-Type
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
~~~

Đây không phải cấu hình CORS đầy đủ; cần khai báo origin cụ thể, credentials policy, allowed methods và response headers phù hợp. Nếu client phải đọc nonce do server trả:

~~~http
Access-Control-Expose-Headers: DPoP-Nonce, WWW-Authenticate
~~~

Browser cần được phép nhìn thấy `DPoP-Nonce` để xây proof tiếp theo. Không dùng `Access-Control-Allow-Origin: *` một cách vô điều kiện cùng credentials. CORS chỉ là chính sách browser; **không thay authentication hoặc DPoP proof validation**.

### 14.5. Gateway không được bỏ một trong hai header

Kiểm tra proxy/gateway có:

- Forward đúng `Authorization: DPoP`.
- Forward đúng `DPoP` header.
- Không ghi raw token/proof vào access logs.
- Không tự đổi Authorization scheme thành Bearer.
- Không gộp hoặc loại bỏ header duplicate ngoài policy.
- Giữ đúng request method và URI mapping.

Nếu gateway xác thực DPoP rồi downstream vẫn yêu cầu DPoP, gateway phải giữ hoặc tạo cơ chế delegation/token phù hợp. Không chuyển một access token DPoP-bound sang downstream mà không duy trì binding.

## 15. Những gì DPoP không bảo vệ

DPoP tăng khả năng chống replay token bị đánh cắp, nhưng không phải giải pháp toàn diện cho mọi rủi ro client/API.

### 15.1. Không chống được private key bị đánh cắp

Nếu attacker lấy được cả access token và private key, họ có thể tạo proof hợp lệ. Bảo vệ key trong secure storage, giảm quyền đọc key, hạn chế export, monitor bất thường và có quy trình rotate/revoke vẫn cần thiết.

### 15.2. Không tự bảo vệ trước XSS điều khiển client

Trong SPA, XSS có thể chạy trong cùng origin và gọi chức năng ký proof bằng key mà ứng dụng đang sử dụng, kể cả khi key không exportable. DPoP làm khó việc mang token sang máy khác nhưng không đảm bảo một browser đang bị chiếm quyền không thể thực hiện request thay user.

Vẫn cần CSP, output encoding, dependency hygiene, tránh lưu token không cần thiết, kiểm soát script và quy trình xử lý session.

### 15.3. Không mã hóa access token hoặc proof

JWT proof và access token có thể được đọc bởi các tầng quan sát request nếu chúng được ghi log. DPoP không phải encryption. Dùng TLS và redaction trong logging/tracing/proxy.

### 15.4. Không ký toàn bộ request body

DPoP proof ràng buộc method, URI và access token hash cùng những claims quy định; nó **không mặc định ký body JSON hoặc mọi header tùy chỉnh**. TLS vẫn cần bảo vệ confidentiality/integrity trên đường truyền. Nếu ứng dụng cần integrity của nội dung nghiệp vụ ở mức application, phải dùng một cơ chế request signing/message integrity riêng theo threat model.

### 15.5. Không thay authorization

Một proof hợp lệ chỉ chứng minh client có private key bind với token. Nó không cho phép user đọc mọi đơn hàng, không thay scope/role/tenant/owner checks và không biến token hết hạn thành token hợp lệ.

### 15.6. Không thay mutual TLS trong mọi kiến trúc

DPoP và mTLS có mô hình triển khai khác nhau:

| DPoP | mTLS certificate-bound token |
|---|---|
| Proof JWT ở tầng ứng dụng | TLS client certificate ở tầng transport |
| Khóa ký proof thuộc OAuth client | Client certificate/private key dùng trong TLS handshake |
| Proof có `htm`/`htu`/`ath`/`jti` | Binding token với certificate thumbprint |
| Có thể hoạt động qua một số proxy nếu truyền proof/URI đúng | TLS termination/proxy ảnh hưởng trực tiếp client certificate |

Lựa chọn phụ thuộc client platform, proxy/network architecture, yêu cầu vận hành và support của AS/RS. Không xem hai cơ chế có thể thay thế nhau mà không thay đổi trust model.

## 16. Kiểm thử DPoP: cần kiểm tra cả token binding và proof

Một bộ test DPoP không thể chỉ tạo access token JWT hợp lệ rồi gọi API. Cần có **positive control** với access token có `cnf.jkt` và proof được ký bằng key đúng, sau đó thay đổi từng thuộc tính để chứng minh server từ chối.

### 16.1. Bộ fixture test

Một test fixture nên tạo:

~~~text
Trusted issuer signing key:
    dùng ký access token JWT (nếu test JWT)

Client DPoP key pair A:
    public JWK A
    private key A
    thumbprint JKT-A

Client DPoP key pair B:
    public JWK B
    private key B
    thumbprint JKT-B

Access token A:
    iss = trusted issuer
    aud = orders-api
    exp = future
    scope = orders.read
    cnf.jkt = JKT-A

Valid proof A:
    signed by private key A
    header.jwk = public JWK A
    htm/htu match request
    ath = hash(access token A)
    fresh iat, unused jti
~~~

Key pair B cho phép kiểm tra một proof có chữ ký hợp lệ nhưng **không phải key đã bind với token**. Cần giữ riêng key ký access token và key DPoP của client: chúng phục vụ hai vai trò khác nhau.

### 16.2. Ma trận Resource Server

| Case | Thay đổi so với positive control | Kết quả |
|---|---|---|
| P-01 | Access token đúng, proof đúng key/claims | Cho qua authentication; scope đủ thì endpoint thành công |
| P-02 | Không có `DPoP` header | Từ chối |
| P-03 | `Authorization` thiếu scheme/token | Từ chối |
| P-04 | Dùng `Bearer` với token policy yêu cầu DPoP | Từ chối theo policy |
| P-05 | Proof malformed/không phải compact JWT | Từ chối |
| P-06 | `typ` khác `dpop+jwt` | Từ chối |
| P-07 | `alg=none` hoặc thuật toán đối xứng | Từ chối |
| P-08 | Proof signature sai | Từ chối |
| P-09 | Proof ký bằng key B nhưng token `cnf.jkt=JKT-A` | Từ chối binding mismatch |
| P-10 | `htm` khác HTTP method | Từ chối |
| P-11 | `htu` khác URI đích | Từ chối |
| P-12 | `htu` chứa query/fragment sai quy tắc | Từ chối theo RFC validation |
| P-13 | `iat` quá cũ hoặc tương lai quá xa | Từ chối |
| P-14 | `jti` đã được sử dụng | Từ chối replay |
| P-15 | Thiếu `ath` ở resource request | Từ chối |
| P-16 | `ath` hash token khác | Từ chối |
| P-17 | Nonce bắt buộc nhưng proof thiếu/sai nonce | Challenge `use_dpop_nonce` hoặc từ chối theo policy |
| P-18 | Access token hết hạn | Từ chối token |
| P-19 | Access token sai audience/issuer | Từ chối token |
| P-20 | Token scope thiếu | Authentication có thể thành công, authorization từ chối |
| P-21 | Replay cùng proof gửi đến hai node | Chỉ request đầu được chấp nhận |
| P-22 | Token không có `cnf.jkt` nhưng client gửi proof | Không tự tạo binding; từ chối DPoP authentication |

### 16.3. Ma trận Authorization Server

| Case | Token endpoint request | Kết quả cần kiểm tra |
|---|---|---|
| AS-01 | DPoP proof hợp lệ, token grant hợp lệ | Token type DPoP, binding `cnf.jkt` đúng key |
| AS-02 | Proof signature sai | Không cấp DPoP-bound token |
| AS-03 | `htm`/`htu` sai | Từ chối proof |
| AS-04 | `iat` cũ/tương lai | Từ chối proof |
| AS-05 | `jti` bị replay | Từ chối theo replay policy |
| AS-06 | Nonce yêu cầu nhưng không gửi | Trả challenge/nonce |
| AS-07 | Proof mới có nonce đúng | Token request có thể tiếp tục nếu grant/client hợp lệ |
| AS-08 | Token refresh dùng sai key | Không cho refresh token đã bind với key khác |
| AS-09 | Client không được phép resource/scope | Không cấp token dù proof hợp lệ |

Proof hợp lệ **không thay authorization grant**. AS vẫn phải kiểm tra code/PKCE/client authentication, consent, scopes, resource và grant policy trước khi cấp token.

### 16.4. Test đúng key và sai key

Một test logic:

~~~text
token.cnf.jkt = JKT-A

proof A:
    signature verifies with JWK-A
    thumbprint(JWK-A) = JKT-A
    → accept (nếu claims/replay/token đều hợp lệ)

proof B:
    signature verifies with JWK-B
    thumbprint(JWK-B) = JKT-B
    → reject (binding mismatch)
~~~

Điểm cần chứng minh là proof B **có chữ ký hợp lệ của chính nó** nhưng vẫn bị từ chối vì không khớp token binding. Nếu tạo proof B với signature hỏng, test chỉ chứng minh signature validation, không chứng minh `cnf.jkt` comparison.

### 16.5. Test `ath`

Tạo proof với access token A rồi gửi kèm access token B:

~~~text
proof.ath = BASE64URL(SHA-256(token A))
Authorization: DPoP token B
~~~

Resource Server phải tính lại `ath` từ token B và từ chối mismatch. Test thêm trường hợp thiếu `ath` và hash bị thay một ký tự. Không chỉ assert decoder token B hợp lệ; cần assert **proof/token association** thất bại.

### 16.6. Test replay

Gửi chính xác cùng một request proof hai lần:

~~~text
First request:
    jti = proof-123
    → accepted (nếu các điều kiện khác hợp lệ)

Second request:
    jti = proof-123
    → replay rejected
~~~

Nếu API idempotent và client cần retry request nghiệp vụ, retry vẫn phải tạo **proof mới** với `jti` mới. Test replay phải chạy trên replay store có semantics giống môi trường triển khai, đặc biệt khi có nhiều instances.

## 17. Kiểm thử DPoP qua Spring WebFlux/Servlet

Khi Spring integration layer đã hỗ trợ DPoP, nên dùng HTTP test thật qua filter chain. Không chỉ gọi proof validator trực tiếp.

### 17.1. Một test HTTP WebFlux ở mức ý tưởng

~~~java
// Pseudocode: helper/API cụ thể phụ thuộc DPoP support của ứng dụng.
String accessToken = issueDpopBoundToken(
    clientKeyPairA,
    "https://api.example.test/orders",
    "orders.read"
);

String proof = createDpopProof(
    clientKeyPairA,
    "GET",
    "https://api.example.test/api/orders",
    accessToken,
    null
);

webTestClient.get()
    .uri("/api/orders")
    .headers(headers -> {
        headers.set("Authorization", "DPoP " + accessToken);
        headers.set("DPoP", proof);
    })
    .exchange()
    .expectStatus().isOk();
~~~

`issueDpopBoundToken(...)` và `createDpopProof(...)` là helper của test/issuer fixture, không phải method Spring Security built-in. Test app cần cấu hình DPoP authentication layer thực và controller route có tồn tại.

### 17.2. Test proof sai method

Giữ token, key, `htu`, `ath` và mọi claims đúng; chỉ tạo proof `htm=POST` trong khi gửi GET:

~~~java
String wrongMethodProof = createDpopProof(
    clientKeyPairA,
    "POST",
    "https://api.example.test/api/orders",
    accessToken,
    null
);
~~~

Gửi proof đó với request GET và mong đợi authentication thất bại. Không đổi thêm key/token/nonce trong cùng test vì khó xác định nguyên nhân.

### 17.3. Test nonce challenge

Kịch bản:

1. Gửi request proof hợp lệ nhưng không có nonce tới Resource Server đang yêu cầu nonce.
2. Kiểm tra response có `DPoP-Nonce` và challenge `use_dpop_nonce` theo contract.
3. Tạo proof mới, `jti` mới và `nonce` lấy từ response.
4. Gửi lại request với proof mới.
5. Xác nhận request đi qua nếu token/proof còn hợp lệ.

Không replay cùng proof sau challenge. Nonce test cần kiểm tra client xử lý response, không chỉ kiểm tra server trả một header.

### 17.4. Test hai node dùng replay store chung

~~~text
Request 1 → Resource Server node A → replay store → accept
Same proof → Resource Server node B → same replay store → reject
~~~

Nếu node B chấp nhận cùng proof, replay detection chỉ local hoặc thao tác check/insert không atomic. Đây là test quan trọng cho triển khai clustered.

### 17.5. Test authorization sau DPoP authentication

Một DPoP proof hợp lệ chỉ giúp xác thực token. Dùng token có:

~~~text
aud = orders-api
cnf.jkt = JKT-A
scope = orders.create
~~~

với request GET yêu cầu `orders.read`. Kỳ vọng authentication thành công nhưng HTTP authorization từ chối (thường 403). Như vậy test phân biệt **proof/token invalid** với **token valid nhưng thiếu quyền**.

### 17.6. Test scheme Bearer không được fallback

Nếu token đã bind DPoP và endpoint yêu cầu DPoP:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <DPoP_BOUND_ACCESS_TOKEN>
~~~

Không có proof header. Resource Server phải từ chối theo policy; không được chấp nhận chỉ vì JWT signature/claims hợp lệ. Đây là test bảo đảm sender constraint không bị vô hiệu hóa bởi một đường Bearer fallback.

## 18. Replay cache, nonce store và triển khai nhiều node

DPoP proof thường có thời gian sống ngắn. Để chống việc một proof hợp lệ bị gửi lại, Resource Server cần ghi nhận `jti` đã sử dụng trong cửa sổ chấp nhận.

### 18.1. Replay key

Một replay record có thể dùng:

~~~text
replayKey = "dpop:" + jkt + ":" + jti
expiresAt = now + proofAcceptanceWindow
~~~

`jkt` giúp namespace theo key; `jti` phân biệt từng proof. Không cần lưu toàn bộ JWT proof hoặc access token trong cache. Chỉ lưu fingerprint/identifier tối thiểu đủ cho việc phát hiện replay và điều tra.

### 18.2. Check-and-set phải atomic

Logic sai:

~~~text
if cache does not contain replayKey:
    cache.put(replayKey)
    accept
~~~

Hai node có thể cùng kiểm tra “chưa tồn tại” trước khi node nào ghi, rồi cùng chấp nhận. Cần primitive atomic kiểu `SET key value NX EX ttl` hoặc thao tác compare-and-insert tương đương trong datastore phù hợp:

~~~text
insert replayKey if absent with TTL

insert succeeded → proof chưa bị dùng, tiếp tục
insert failed    → proof replay, từ chối
~~~

Tên lệnh chỉ minh họa semantics; lựa chọn Redis, database, cache cluster hay store khác phụ thuộc hệ thống. Điều quan trọng là atomicity và TTL.

### 18.3. Replay store unavailable

Nếu policy dựa vào replay cache để đảm bảo DPoP, việc cache không khả dụng làm server không thể chứng minh `jti` chưa được sử dụng. Không nên tự động bỏ replay check rồi chấp nhận mọi proof.

Các lựa chọn cần thiết kế trước:

- Fail closed cho DPoP request trong thời gian store lỗi.
- Dùng một store HA có consistency/atomic operation phù hợp.
- Chấp nhận risk window có kiểm soát chỉ khi threat model và security owner phê duyệt.

Không biến lỗi hạ tầng thành một đường bypass im lặng.

### 18.4. TTL của replay entry

TTL cần bao phủ khoảng thời gian server có thể chấp nhận proof dựa trên `iat` và clock skew. Nếu proof được chấp nhận trong cửa sổ 60 giây, entry phải còn tồn tại ít nhất đủ lâu để proof cũ không thể được gửi lại và lọt qua sau khi record đã hết TTL.

Ví dụ:

~~~text
accepted proof iat = 12:00:00
server accepts until = 12:01:00
replay record expiry must not precede acceptance end
~~~

Không đặt TTL 5 giây chỉ vì “DPoP proof ngắn hạn” nếu server vẫn chấp nhận proof có tuổi 60 giây. TTL và freshness policy phải được thiết kế đồng bộ.

### 18.5. Nonce store và phạm vi nonce

Nonce cần gắn với đúng server/authority hoặc context theo thiết kế. Không dùng một nonce global cho:

- Authorization Server token endpoint.
- Orders API.
- Payments API.
- Các issuer/tenant khác nhau.

Nonce phải được tạo đủ ngẫu nhiên, không đoán được và có vòng đời. Nếu dùng nonce one-time, server phải ghi nhận/tiêu thụ nó atomic; nếu dùng nonce theo thời hạn/session, phải định nghĩa cách kiểm tra và refresh. Client phải giữ nonce theo origin/authority tương ứng.

### 18.6. Độ trễ và dung lượng

Với số lượng request lớn, mỗi DPoP request có thể cần một lần atomic write cho replay detection. Cần tính:

~~~text
replay write rate ≈ accepted DPoP request rate
retained entries ≈ accepted proof rate × replay TTL
~~~

Ví dụ 5.000 DPoP requests/s và TTL 90 giây có thể cần giữ khoảng 450.000 replay records tại một thời điểm, chưa tính overhead của datastore. Đây là phép tính minh họa; số thực phụ thuộc throughput và policy.

Đừng tối ưu bằng cách tắt replay detection khi tải tăng. Hãy chọn store/partitioning/TTL phù hợp, theo dõi latency và capacity, hoặc giảm tải request theo policy.

## 19. Vận hành DPoP: metrics, logging và sự cố

DPoP bổ sung một số loại lỗi mới. Metrics phải phân biệt token validation với proof validation và replay.

### 19.1. Metrics nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| `dpop_proof_validation_total` | Số proof accepted/rejected theo reason |
| `dpop_proof_validation_duration_seconds` | Thời gian verify proof |
| `dpop_replay_detected_total` | Số proof bị phát hiện replay |
| `dpop_nonce_challenge_total` | Số lần server yêu cầu nonce |
| `dpop_nonce_validation_failed_total` | Nonce missing/invalid/expired |
| `dpop_jkt_mismatch_total` | Proof key không khớp token binding |
| `dpop_ath_mismatch_total` | Proof không ràng buộc với token đang trình |
| `dpop_replay_store_errors_total` | Lỗi datastore replay |
| `dpop_missing_header_total` | Thiếu DPoP proof header |
| `dpop_scheme_mismatch_total` | Dùng Bearer/DPoP scheme sai policy |

Dùng labels bounded như API alias, issuer alias, outcome reason và environment. Không dùng raw `jti`, raw JWK, token, subject hoặc nonce làm metric label.

### 19.2. Structured logs

Ví dụ có thể log:

~~~text
event=dpop_validation result=accepted api=orders issuer=shop
event=dpop_validation result=rejected reason=htm_mismatch api=orders
event=dpop_validation result=rejected reason=jkt_mismatch api=orders
event=dpop_replay result=detected api=orders
event=dpop_nonce result=challenge api=orders
event=dpop_replay_store result=unavailable api=orders
~~~

Không log:

~~~text
Authorization: DPoP <full-access-token>
DPoP: <full-proof-jwt>
privateKey=...
nonce=<full-secret-nonce>
~~~

Proof JWT có public JWK, nhưng vẫn là dữ liệu bảo mật cần kiểm soát; access token và nonce cũng có thể bị lạm dụng nếu lộ. Không bật HTTP wire logging toàn bộ trong production chỉ để debug DPoP.

### 19.3. Phân loại sự cố

| Tín hiệu | Nguyên nhân cần xem xét |
|---|---|
| `invalid_dpop_proof` tăng | Client ký sai method/URI, key issue, clock drift, proof parser |
| `jkt mismatch` tăng | Token và key bị ghép sai, key rotation/lưu token mapping lỗi |
| `ath mismatch` tăng | Token/proof bị ghép sai, token header bị rewrite, client bug |
| `htm/htu mismatch` tăng | Proxy path rewrite, redirect, canonicalization |
| `use_dpop_nonce` tăng | Nonce rotation/challenge policy hoặc client chưa cập nhật nonce |
| Replay detected tăng | Client reuse proof, retry logic không tạo proof mới, hoặc replay attack |
| Replay store errors | Datastore/cluster/network/capacity |
| DPoP token bị gửi bằng Bearer | OAuth client chưa hỗ trợ DPoP hoặc cache token type sai |

Replay detection tăng không tự động chứng minh có attacker; HTTP client có thể vô tình gửi lại proof khi retry. Cần đối chiếu request IDs, client version và retry behavior mà không log token.

### 19.4. Clock synchronization

`iat` và nonce freshness phụ thuộc thời gian. Các node Resource Server lệch clock có thể cho kết quả khác nhau cho cùng một proof. Cần đồng bộ thời gian hệ thống, theo dõi clock offset và dùng một policy skew thống nhất giữa các nodes.

Không tăng freshness window thật lớn để che một vấn đề NTP; điều đó kéo dài replay window.

## 20. Những lỗi triển khai phổ biến

### 20.1. Chỉ xác minh chữ ký proof

Proof signature đúng chưa đủ. Nếu bỏ `htm`, `htu`, `ath`, `jti` hoặc `cnf.jkt`, proof có thể được dùng sai request hoặc ghép với token khác.

### 20.2. Dùng chung proof cho nhiều request

Một proof gắn method/URI/iat/jti và token. Gửi lại proof có thể bị replay detection từ chối; gửi sang URL/method khác phải bị claim validation từ chối. Tạo proof mới cho từng lần gửi.

### 20.3. Thiếu `ath` ở Resource Server

Không có `ath`, proof không được ràng buộc trực tiếp với access token đang trình. Client có thể vô tình/độc ý ghép proof của token A với token B. Resource Server phải kiểm tra hash theo RFC.

### 20.4. Bỏ so sánh `cnf.jkt`

Nếu server chỉ verify signature theo JWK do proof gửi, bất kỳ ai cũng có thể tạo key pair riêng và ký proof riêng. Phải so public JWK thumbprint với binding được issuer xác minh trong token.

### 20.5. Chấp nhận `alg=none` hoặc HMAC

DPoP dựa trên public/private key. Không dùng thuật toán không ký hoặc symmetric algorithm cho proof. Allowlist thuật toán và key type phù hợp.

### 20.6. Không kiểm tra replay vì `jti` đã unique

Client tạo `jti` unique không có nghĩa server tự biết nó đã xuất hiện. Server cần replay store và atomic check-and-set. Nếu không lưu trạng thái hoặc có cluster nodes độc lập, proof replay có thể được chấp nhận nhiều lần.

### 20.7. So `htu` với URI nội bộ

Gateway TLS termination/path rewrite có thể khiến backend thấy URL khác client ký. Cần external URI trust configuration, không tự tin forwarded headers.

### 20.8. Dùng nonce cũ hoặc nonce sai server

Nonce của AS không tự dùng được cho RS khác. Client phải lưu theo authority/context, cập nhật nonce mới nhất và tạo proof mới sau challenge.

### 20.9. Fallback DPoP sang Bearer

Nếu proof invalid, không thử lại cùng access token bằng Bearer scheme để “cứu request”. Điều đó bỏ qua sender constraint.

### 20.10. Bỏ TLS

DPoP không mã hóa token/proof, không ngăn mọi kiểu traffic interception và không thay TLS. Dùng HTTPS và certificate validation đúng.

### 20.11. Nghĩ DPoP ký cả request body

Proof chuẩn ràng buộc các claims quy định như method, URI, access-token hash; nó không mặc định bảo vệ body JSON. Không tuyên bố DPoP thay thế application payload signing.

### 20.12. Cho phép proof key chứa private parameters

Header `jwk` chỉ nên chứa public JWK. Nếu có `d` hoặc private RSA parameters, từ chối và điều tra client implementation; không ghi private material vào logs.

### 20.13. Replay cache chỉ local trong hệ thống nhiều node

Attacker có thể gửi cùng proof đến node khác nếu cache không được chia sẻ. Cần store cluster/shared atomic hoặc kiến trúc sticky routing kèm bảo đảm phù hợp; sticky routing đơn thuần không thay replay defense khi failover.

### 20.14. DPoP middleware chạy sau authorization

Nếu access token được coi là authenticated trước khi proof được xác minh, endpoint có thể vô tình cấp quyền. DPoP proof validation thuộc authentication boundary, trước khi principal được tin.

## 21. Chuyển đổi từ Bearer sang DPoP

Một hệ thống đang chạy Bearer token không nên bật DPoP bằng cách chỉ đổi chuỗi header ở frontend. Cần phối hợp client, Authorization Server và Resource Server.

### 21.1. Xác định giai đoạn rollout

~~~text
Phase 0 — Baseline:
    Bearer access tokens
    existing JWT/introspection validation

Phase 1 — Capability:
    AS can issue DPoP-bound tokens
    clients can generate proofs
    RS can validate DPoP

Phase 2 — Controlled adoption:
    selected clients request DPoP tokens
    APIs accept DPoP scheme for bound tokens
    observe proof/replay/nonce metrics

Phase 3 — Policy enforcement:
    require DPoP for chosen clients/resources
    reject Bearer presentation of DPoP-bound tokens
    maintain explicit policy for legacy Bearer clients if needed
~~~

Đây là mô hình rollout tham khảo. Việc hỗ trợ song song Bearer và DPoP cần phân biệt token type và client policy, không được để một DPoP-bound token bị hạ cấp sang Bearer.

### 21.2. Không thể đổi token cũ thành DPoP-bound chỉ bằng client code

Bearer token đã được phát hành mà không có `cnf.jkt` không tự trở thành DPoP-bound khi client bắt đầu thêm proof header. Client cần lấy **token mới** qua AS hỗ trợ DPoP binding. Resource Server phải đọc binding từ token/metadata issuer đã xác minh.

### 21.3. Migration client theo capability

Một client có thể cần:

- Khởi tạo key pair và lưu key an toàn.
- Gửi DPoP proof tại token endpoint.
- Xử lý `token_type=DPoP` và lưu key binding với token.
- Gửi scheme `Authorization: DPoP` cùng proof header.
- Xử lý nonce challenge.
- Tạo proof mới cho retries.
- Refresh token bằng đúng key binding.

Không chỉ thêm một interceptor tạo header `DPoP` mà không kiểm tra response token type/confirmation binding.

### 21.4. Migration Resource Server

API cần:

- Xác định DPoP-bound tokens bằng token type/binding theo contract.
- Parse đúng authorization scheme.
- Xác minh token, proof và thumbprint.
- Bật replay cache và nonce policy nếu dùng.
- Kiểm tra reverse proxy/canonical URI.
- Xác nhận observability không log credentials.
- Có tests cho Bearer legacy và DPoP-bound paths riêng biệt.

### 21.5. Chuyển đổi từng API

Không nhất thiết bật DPoP đồng thời cho toàn bộ microservices. Có thể bắt đầu với API nhạy cảm, client được kiểm soát và issuer có support đầy đủ. Nhưng token relay/downstream calls phải được thiết kế để không làm mất binding khi request đi qua các service khác.

### 21.6. Rollback

Rollback cần tính đến token đã phát hành:

- Token DPoP-bound còn hiệu lực vẫn yêu cầu key/proof.
- Không cho token đó qua Bearer chỉ để rollback client code.
- Có thể cấp token mới theo cơ chế legacy nếu policy cho phép và revoke/expire token cũ theo kế hoạch.
- Giữ metrics để biết client nào chưa chuyển đổi.

Rollback không được biến thành một đường tắt bỏ sender constraint mà tổ chức đã yêu cầu.

## 22. Hướng dẫn chẩn đoán theo triệu chứng

### 22.1. AS từ chối token request dù grant hợp lệ

Kiểm tra:

1. Token request có header `DPoP` không?
2. Proof `typ` đúng `dpop+jwt` và `alg` được hỗ trợ không?
3. `htm` có đúng POST không?
4. `htu` có đúng token endpoint URI, bỏ query/fragment không?
5. `iat` có trong freshness window không?
6. `jti` có bị dùng trước đó không?
7. Nonce có được yêu cầu và client đã dùng nonce mới nhất chưa?
8. Public JWK có khớp private key đã ký proof không?

Proof đúng không đảm bảo grant/client/resource được phép; sau proof validation, AS vẫn áp authorization policy.

### 22.2. Token endpoint trả `use_dpop_nonce` liên tục

Nguyên nhân có thể:

- Client không lưu `DPoP-Nonce` từ response.
- Client gửi lại proof cũ thay vì ký proof mới.
- Nonce được lưu nhầm theo host hoặc dùng nonce của issuer khác.
- Reverse proxy làm client gọi một endpoint khác với `htu` đã ký.
- Server phát nonce mới nhưng client tiếp tục dùng nonce cũ.

Giới hạn số lần retry và log reason/request ID; không tạo vòng lặp vô hạn.

### 22.3. Resource Server báo `invalid_dpop_proof`

Kiểm tra theo từng claim:

| Claim/header | Câu hỏi |
|---|---|
| `typ` | Có đúng `dpop+jwt` không? |
| `alg` | Có thuộc allowlist bất đối xứng không? |
| `jwk` | Có public key hợp lệ, không có private parameters không? |
| Signature | Có verify bằng public JWK không? |
| `htm` | Có khớp method thật không? |
| `htu` | Có khớp URI chuẩn hóa không? |
| `iat` | Có trong freshness window không? |
| `jti` | Có trùng replay cache không? |
| `ath` | Có hash đúng access token không? |
| `nonce` | Có được yêu cầu và khớp server nonce không? |
| `cnf.jkt` | Có khớp thumbprint proof JWK không? |

Không bật log toàn bộ token/proof trong production để tìm lỗi.

### 22.4. Proof signature đúng nhưng `jkt` mismatch

Thường là:

- Client dùng private key B nhưng access token bind với key A.
- Token cache không lưu đúng key alias.
- Key rotation diễn ra nhưng client vẫn dùng token cũ.
- AS đã bind token với thumbprint khác với public JWK client gửi.
- Server tính thumbprint không theo RFC 7638 hoặc dùng sai JWK members.

Đối chiếu key alias và thumbprint dạng fingerprint đã được phép quan sát, không in private key.

### 22.5. `ath` mismatch

Kiểm tra client có hash:

- Đúng access token không?
- Đúng ASCII bytes và SHA-256 không?
- Base64URL không padding không?
- Có vô tình hash prefix `DPoP `/`Bearer ` không?
- Có dùng token cũ trong proof nhưng header chứa token mới sau refresh không?

Nếu proxy thay Authorization header hoặc client retry sau token refresh, proof phải được tạo lại theo token thực gửi.

### 22.6. `htu` mismatch sau khi triển khai gateway

Đối chiếu:

~~~text
Client target URI
Public gateway URI
Forwarded scheme/host
Rewritten path
Backend request URI
DPoP verifier canonical URI
~~~

Chỉ tin forwarded metadata từ proxy được xác thực. Đặt test integration đi qua cùng gateway/path rewrite như production.

### 22.7. Replay detected tăng đột biến

Có thể do:

- HTTP client retry cùng request object/header.
- Gateway retry và forward nguyên proof.
- Một middleware cache proof theo URL.
- Client tạo `jti` từ timestamp cố định.
- Replay attack thực sự.

Sửa client/gateway để mỗi lần gửi tạo proof mới, sau đó vẫn giữ replay detection. Không tắt replay store để làm giảm metric.

### 22.8. Một node chấp nhận, node khác từ chối

Kiểm tra:

- Đồng hồ node.
- Replay store shared/atomic.
- Nonce state được chia sẻ đúng phạm vi.
- Trusted proxy/URI canonicalization đồng nhất.
- Key/algorithm allowlist và token validation config đồng nhất.
- Cache/issuer metadata.

DPoP trong cluster cần **cùng một trust policy**, không chỉ cùng code.

## 23. Bài tập thực hành

### Bài tập 1 — Nhìn đúng hai header

Cho request:

~~~http
GET /api/orders HTTP/1.1
Authorization: DPoP eyJ...
DPoP: eyJ...
~~~

Giá trị trong `Authorization` là **access token DPoP-bound**; giá trị trong `DPoP` là **DPoP proof JWT**. Không hoán đổi hai giá trị.

### Bài tập 2 — Token request hay API request?

Proof có `htm=POST` và `htu=https://login.example.test/oauth2/token`, không có `ath`. Đây là proof phù hợp cho **token endpoint request**. Khi gọi Resource Server với access token, proof phải có `ath` hash access token.

### Bài tập 3 — Proof key đúng hay sai?

~~~text
Access token cnf.jkt = JKT-A
Proof signature valid with JWK-B
thumbprint(JWK-B) = JKT-B
~~~

Resource Server phải từ chối vì **binding mismatch**, dù chữ ký proof hợp lệ.

### Bài tập 4 — Chỉnh method

Client tạo proof với `htm=GET` nhưng gửi POST. Server cần từ chối proof. Không được coi signature đúng là đủ.

### Bài tập 5 — Query parameter

Request `GET https://api.example.test/orders?status=open`: claim `htu` không chứa query string. Client và server phải áp quy tắc URI DPoP nhất quán.

### Bài tập 6 — Replay

Gửi cùng một proof hai lần. Request đầu có thể được chấp nhận; lần thứ hai phải bị phát hiện replay nếu proof đã được dùng và còn trong cửa sổ replay. Retry hợp lệ cần tạo proof mới.

### Bài tập 7 — Nonce challenge

Server trả `DPoP-Nonce` và `use_dpop_nonce`. Client tạo proof mới có `nonce` đó, `jti` mới và chữ ký mới; không sửa payload của proof cũ.

### Bài tập 8 — API scope

DPoP token/proof hợp lệ nhưng chỉ có `orders.create` gọi GET yêu cầu `orders.read`. Authentication thành công, authorization từ chối (thường 403).

### Bài tập 9 — Bearer fallback

Token có `cnf.jkt` nhưng client gửi `Authorization: Bearer`, không có proof. Nếu policy yêu cầu DPoP, server từ chối; không bỏ qua binding.

### Bài tập 10 — Proxy

Client ký public URI HTTPS, backend thấy internal HTTP URI. Hãy mô tả cách trusted gateway chuyển external URI an toàn và viết test qua proxy để chứng minh `htu` khớp.

## 24. Checklist trước production

### 24.1. Authorization Server

- [ ] Có hỗ trợ DPoP theo RFC 9449.
- [ ] Xác minh proof tại token endpoint.
- [ ] Yêu cầu `typ=dpop+jwt` và asymmetric algorithm allowlist.
- [ ] Xác minh `htm`, `htu`, `iat`, `jti` và nonce khi áp dụng.
- [ ] Tính thumbprint từ public JWK theo RFC 7638.
- [ ] Bind access token với `cnf.jkt` hoặc metadata tương đương.
- [ ] Trả `token_type=DPoP` cho DPoP-bound token.
- [ ] Có policy rõ cho refresh token/key binding.
- [ ] Không phát token nếu grant/client/resource/scope không được phép.

### 24.2. OAuth client

- [ ] Tạo và bảo vệ private key.
- [ ] Chỉ đưa public JWK vào proof header.
- [ ] Tạo proof mới cho mỗi request/token request.
- [ ] Dùng đúng `htm`/`htu`.
- [ ] Có `ath` cho Resource Server proof.
- [ ] Dùng `Authorization: DPoP` và `DPoP` header đúng vị trí.
- [ ] Xử lý `DPoP-Nonce` và `use_dpop_nonce`.
- [ ] Retry/redirect tạo proof mới.
- [ ] Lưu quan hệ token ↔ key alias.
- [ ] Xử lý key rotation/mất key/refresh token.
- [ ] Không log access token/proof/private key.

### 24.3. Resource Server

- [ ] Xác minh access token issuer/signature/audience/time/scope.
- [ ] Đọc confirmation binding từ token/introspection đáng tin.
- [ ] Parse scheme `DPoP` và header `DPoP`.
- [ ] Xác minh proof type/algorithm/public JWK/signature.
- [ ] Kiểm tra `htm`, `htu`, `iat`, `ath`, nonce.
- [ ] So thumbprint proof key với `cnf.jkt`.
- [ ] Chống replay bằng `jti` + atomic store.
- [ ] Có policy khi replay/nonce store unavailable.
- [ ] Không fallback DPoP invalid sang Bearer.
- [ ] Chỉ tạo Authentication sau toàn bộ validation.
- [ ] Sau đó vẫn kiểm tra scopes/roles/tenant/owner.

### 24.4. Hạ tầng và kiểm thử

- [ ] TLS được bật và kiểm tra certificate đúng.
- [ ] Trusted proxy/URI reconstruction được cấu hình.
- [ ] CORS cho phép `DPoP` header và expose `DPoP-Nonce` khi cần.
- [ ] Gateway forward đúng cả hai header và không log credentials.
- [ ] Replay cache hoạt động atomic trên nhiều node.
- [ ] Đồng bộ clock giữa client/AS/RS ở mức phù hợp.
- [ ] Có test positive/negative cho token binding, method, URI, `ath`, nonce, replay.
- [ ] Có test cross-node replay và gateway rewriting.
- [ ] Metrics tách token errors/proof errors/replay/nonce.
- [ ] Key rotation và incident response đã được diễn tập.

## 25. Kết luận

DPoP thêm một bằng chứng sở hữu khóa vào cách OAuth client trình access token. Hai header phải được hiểu đúng:

~~~http
Authorization: DPoP <DPoP_BOUND_ACCESS_TOKEN>
DPoP: <SIGNED_PROOF_JWT>
~~~

`Authorization` mang token được issuer ràng buộc với public key; `DPoP` mang proof mới được ký bằng private key tương ứng cho request hiện tại.

Một Resource Server chỉ nên tạo Authentication khi:

~~~text
Access token valid:
    issuer + signature/introspection + audience + time
    + scope/profile + cnf.jkt

DPoP proof valid:
    typ + asymmetric alg + public jwk + signature
    + htm + htu + iat + ath + jti/replay
    + nonce when required

Binding:
    thumbprint(proof.jwk) == access-token.cnf.jkt
~~~

Sau đó API vẫn áp dụng authorization theo scope, role, tenant và quyền trên từng tài nguyên. DPoP không thay thế TLS, không tự bảo vệ private key trước XSS/malware và không ký toàn bộ HTTP body. Nó cung cấp **sender constraint** cho access token, giảm khả năng một token bị đánh cắp có thể được dùng độc lập mà không có private key đã bind.

Khi tích hợp với Spring Security, cần xác nhận phiên bản và support DPoP thực tế. Cấu hình JWT thông thường không nên được coi là đã xác minh proof. Nếu cần custom integration, việc parse scheme, verify proof, so thumbprint, kiểm tra replay/nonce phải diễn ra trong authentication pipeline trước khi tạo principal.

## Tài liệu tham khảo

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Nimbus JOSE + JWT — Documentation](https://connect2id.com/products/nimbus-jose-jwt)
