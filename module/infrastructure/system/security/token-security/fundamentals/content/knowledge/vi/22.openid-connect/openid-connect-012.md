# JWKS metadata

## Mục tiêu học tập

Trong chương **OpenID Connect** của học phần **Token Security Fundamentals**, **JWKS metadata** là điểm nối giữa việc **Authorization Server/OpenID Provider (OP) công bố khóa công khai** và việc **Client/Relying Party (RP), Resource Server xác minh token đã ký**. JWKS giúp bên nhận chọn đúng khóa khi issuer có nhiều khóa hoặc đang xoay vòng khóa, nhưng việc tải được một tài liệu JSON mang tên `jwks` **không tự chứng minh bất kỳ token nào đáng tin**.

Bài này đặt JWKS vào toàn bộ mô hình bảo mật token: JWT/opaque token, ID token và access token, issuer, audience, scope, xác minh chữ ký, lưu trữ khóa, rotation và ứng phó khi khóa bị lộ. Trọng tâm là **cách tìm đúng JWKS thông qua metadata đáng tin, sử dụng khóa đúng mục đích và không để JWT header điều khiển ranh giới tin cậy**.

Sau bài học, bạn có thể:

1. Phân biệt **OIDC Discovery metadata**, trường **`jwks_uri`**, tài liệu **JSON Web Key Set (JWKS)** và từng **JSON Web Key (JWK)**.
2. Đọc các trường `kty`, `kid`, `use`, `key_ops`, `alg`, `n`/`e`, `crv`/`x`/`y`, `x5c` và biết trường nào chỉ là gợi ý metadata.
3. Theo dõi trình tự xác minh **OIDC ID token** qua `iss`, `kid`, thuật toán, khóa công khai, chữ ký, `aud`, `exp` và `nonce` khi áp dụng.
4. Hiểu khác biệt giữa **ID token**, **JWT access token**, **opaque access token**, **refresh token** và khóa riêng dùng ký hoặc giải mã.
5. Thiết kế **JWKS cache, key rollover/rotation, xử lý unknown `kid`**, outage và sự cố lộ khóa mà không bỏ qua xác minh token.
6. Nhận diện **algorithm confusion**, `alg=none`, `jku`/`x5u` dẫn tới SSRF, issuer mix-up, dùng khóa sai tenant và chấp nhận sai audience.
7. Cấu hình ví dụ Java/Spring Security, kiểm tra âm tính và xác định ranh giới giữa xác thực chữ ký và phân quyền dữ liệu.

## 1. JWKS metadata là gì?

Ba lớp thông tin liên quan nhưng **không đồng nghĩa**:

| Lớp | Ví dụ | Chức năng |
|---|---|---|
| **OIDC Provider Configuration / Discovery metadata** | `https://auth.example.test/.well-known/openid-configuration` | Cho Client biết `issuer`, các endpoint, khả năng hỗ trợ và **`jwks_uri`** của OP. |
| **`jwks_uri`** | `https://auth.example.test/oauth2/jwks` | Địa chỉ do OP công bố để tải **JWK Set** của nó. |
| **JWKS / JSON Web Key Set** | JSON có thuộc tính `"keys": [...]` | Danh sách các **khóa JWK**, thường bao gồm public keys được OP công bố để các bên kiểm tra chữ ký JWT. |
| **JWK / JSON Web Key** | Một object có `kty`, `kid`, dữ liệu public key | Biểu diễn **một khóa mật mã** kèm metadata chọn khóa. |

Khi OP dùng thuật toán chữ ký bất đối xứng như **RS256** hoặc **ES256**, nó ký ID token bằng **private key**; RP dùng **public key** tương ứng từ JWKS đáng tin để xác minh chữ ký. Trong một hệ thống phát hành **JWT access token**, Resource Server có thể dùng chính hoặc một bộ khóa công khai được AS công bố theo hợp đồng để xác minh JWT của AS.

~~~text
Authorization Server / OpenID Provider:
  private signing key      -> ký JWT, KHÔNG công bố
  corresponding public key -> công bố qua JWKS

Client / Resource Server:
  configured trusted issuer
  verified provider metadata
  trusted jwks_uri + public key set
  signature verification + token-specific claim validation
~~~

**JWKS thường được tải công khai**, vì public key không phải bí mật. Điều này **không** làm private key có thể công bố; private key phải nằm trong hệ thống ký, KMS/HSM hoặc keystore được bảo vệ.

### JWKS giải quyết bài toán nào?

Nếu OP dùng duy nhất một khóa tĩnh được cấu hình thủ công, mọi lần đổi khóa đều đòi các Client cập nhật. Với JWKS:

- Một OP có thể công bố **nhiều khóa công khai** trong giai đoạn chuyển tiếp.
- JWT header có thể dùng `kid` giúp verifier chọn khóa tương ứng.
- Client có thể **cache** bộ khóa và cập nhật có kiểm soát khi issuer rotate.
- Bên xác minh có thể lấy public key từ nguồn chuẩn **gắn với issuer**, không phải hỏi Client gửi khóa tùy ý.

**Không nên hiểu rằng JWKS là một “dịch vụ cho phép API”.** Nó cung cấp khóa; quyết định token hợp lệ còn phụ thuộc **issuer, thuật toán, chữ ký, token type, audience, thời hạn, nonce, scope và quyền trên tài nguyên**.

## 2. Mối quan hệ giữa OIDC Discovery và `jwks_uri`

OIDC Discovery cho phép Client biết thông tin cấu hình OpenID Provider. Một tài liệu metadata minh họa:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.test
Accept: application/json
~~~

~~~json
{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "userinfo_endpoint": "https://auth.example.test/oidc/userinfo",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256", "ES256"],
  "scopes_supported": ["openid", "profile", "orders:read"],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ]
}
~~~

**Đây là metadata minh họa**, không phải một server thật. Trong OIDC Discovery, `jwks_uri` mô tả bộ khóa của OP. Các trường ví dụ khác giúp Client lựa chọn luồng, endpoint và thuật toán phù hợp; **chúng không tự đăng ký Client hay cấp quyền**.

### Chuỗi tin cậy cần đúng thứ tự

1. Ứng dụng biết **trusted issuer** qua cấu hình hoặc quy trình onboarding tin cậy.
2. Ứng dụng truy vấn metadata **của issuer đó** qua HTTPS; không lấy `issuer` bất kỳ từ JWT rồi tin ngay.
3. Kiểm tra `issuer` trong metadata **khớp chính xác issuer mong đợi** theo quy tắc giao thức.
4. Lấy `jwks_uri` từ **metadata đã được chấp nhận**, sau đó tải JWKS qua kết nối an toàn.
5. Xác minh JWT từ issuer đó với **key set gắn với issuer** và thuật toán đã được cho phép.
6. Kiểm tra **claims và mục đích của token** (ID token cho RP, access token cho RS).

~~~mermaid
flowchart TD
    A["Trusted issuer cấu hình trước"] --> B["Lấy OIDC Discovery qua HTTPS"]
    B --> C{"Metadata issuer khớp expected issuer?"}
    C -- Không --> X["Từ chối provider/token"]
    C -- Có --> D["Lấy jwks_uri từ metadata đáng tin"]
    D --> E["Tải/cache JWKS có giới hạn"]
    E --> F["Chọn public key hợp lệ cho issuer/alg/kid"]
    F --> G{"Signature hợp lệ?"}
    G -- Không --> X
    G -- Có --> H["Validate iss/aud/exp/nonce/type và policy"]
    H --> I{"Các điều kiện đều đúng?"}
    I -- Không --> X
    I -- Có --> J["Chấp nhận kết quả theo mục đích token"]
~~~

**Sai lầm nghiêm trọng:** thấy `iss=https://attacker.example` trong token chưa xác minh rồi tự động tải JWKS của host đó và chấp nhận token của attacker như token đăng nhập cho hệ thống. Giá trị `iss` chỉ là một **claim chưa được tin cậy** trước khi được kiểm tra với issuer đã cấu hình.

## 3. Cấu trúc tài liệu JWKS

Một phản hồi JWKS thường có dạng:

~~~http
GET /oauth2/jwks HTTP/1.1
Host: auth.example.test
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300
ETag: "jwks-version-42"

{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_RSA_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "kid": "signing-ec-next",
      "use": "sig",
      "alg": "ES256",
      "crv": "P-256",
      "x": "<BASE64URL_EC_X_COORDINATE>",
      "y": "<BASE64URL_EC_Y_COORDINATE>"
    }
  ]
}
~~~

Các chuỗi trong ngoặc nhọn là **placeholder**, không phải khóa thực; JSON này dùng để giải thích cấu trúc, **không thể dùng nguyên văn để verify JWT**. Việc xuất hiện cả RS256 và ES256 không có nghĩa Client/RS phải chấp nhận cả hai: thuật toán được phép phải được cấu hình và đối chiếu chính sách của issuer/profile.

### Những điểm cần nhớ

- Thuộc tính **`keys`** là một mảng JWK; có thể chứa nhiều khóa trong thời gian rotation.
- Một JWK có thể mô tả khóa **RSA**, **EC**, **OKP** hoặc loại khác tùy thuật toán/hỗ trợ.
- JWKS dùng cho xác minh chữ ký **thường chỉ cần public parameters**.
- Metadata như `kid`, `alg`, `use` có thể **vắng mặt theo đặc tả JWK**; chương trình phải xử lý theo profile và chính sách, không giả định chúng luôn tồn tại.
- **JWK Set không phải một JWT đã ký**: nó là tài liệu JSON được bên xác minh lấy từ một kênh/issuer đáng tin. HTTP TLS, cấu hình issuer và quản lý cache là một phần của chuỗi tin cậy.

### Public key là dữ liệu công khai; private key thì không

JWK biểu diễn khóa RSA private có thể có các trường **`d`, `p`, `q`, `dp`, `dq`, `qi`**; với EC private key có thể có **`d`**. **Không công bố các trường private key đó trong JWKS public endpoint**.

Một endpoint JWKS chứa private key là sự cố nghiêm trọng: attacker có thể ký JWT giả theo thuật toán/issuer liên quan. Phải thu hồi/rotate khóa ký và điều tra token, chứ không chỉ gỡ URL.

## 4. Đọc từng trường của JWK

| Trường | Ý nghĩa | Lưu ý an toàn |
|---|---|---|
| **`kty`** | **Key type**: RSA, EC, OKP, oct... | Thuật toán và loại khóa phải tương thích; không dùng RSA public key như HMAC secret. |
| **`kid`** | **Key ID**, giúp chọn khóa trong một set. | Chỉ là **gợi ý chọn**, không phải chữ ký, quyền hạn hay bí mật. |
| **`use`** | Intended public key use, thường `sig` hoặc `enc`. | Không dùng khóa `enc` để verify `sig` nếu policy không cho phép. |
| **`key_ops`** | Các hoạt động dự kiến như `verify`, `encrypt`. | Nếu có phải phù hợp thao tác; tránh dùng key trái policy. |
| **`alg`** | Thuật toán dự kiến cho key, ví dụ `RS256`. | Metadata không được tự mở allowlist thuật toán của verifier. |
| **`n`, `e`** | RSA modulus và public exponent (Base64URLUInt). | Đây là public parameters của RSA key. |
| **`crv`, `x`, `y`** | Đường cong và public point của EC key. | Kiểm tra loại/đường cong khớp thuật toán, ví dụ ES256 với P-256. |
| **`x`** của OKP | Public key trên đường cong được khai. | Chỉ hỗ trợ khi thuật toán, thư viện và profile cho phép. |
| **`x5c`** | Chuỗi chứng chỉ X.509 đính kèm key. | Không tự bỏ kiểm tra issuer/đích tin cậy vì thấy certificate. |
| **`x5t`, `x5t#S256`** | Thumbprint chứng chỉ X.509. | Không thay thế xác minh key, issuer và chính sách. |
| **`x5u`** | URL chứng chỉ X.509 liên quan. | Không tự fetch URL tùy ý từ token/JWK không tin cậy. |
| **`d`, `p`, `q`...** | Dữ liệu private key. | Không được có trong JWKS public dùng phân phối verification keys. |

### `kid` có quan trọng không?

Có. Khi OP xoay vòng khóa và JWKS chứa cả **khóa cũ** và **khóa mới**, `kid` trong JWT header giúp trình xác minh chọn khóa. Tuy nhiên:

1. `kid` là **chuỗi do header token khai**, chưa đáng tin trước khi verify.
2. Nó chỉ được dùng làm **bộ lọc trong bộ khóa của issuer đã được tin cậy**.
3. `kid` **không có phạm vi toàn cầu**; hai issuer có thể dùng cùng tên `kid`.
4. Một issuer không nên công bố hai khóa signing có cùng `kid` gây mơ hồ; hệ thống có thể phải từ chối khi lựa chọn không xác định duy nhất.
5. Thiếu hoặc không tìm thấy `kid` phải được xử lý bằng **quy tắc lựa chọn an toàn**, không thử tìm khóa qua URL do attacker gửi.

### `use` và `key_ops`

Ví dụ:

~~~json
{
  "kty": "RSA",
  "kid": "encryption-2026",
  "use": "enc",
  "key_ops": ["encrypt"],
  "n": "<BASE64URL_MODULUS>",
  "e": "AQAB"
}
~~~

JWK trên chỉ mô tả một **khóa encryption** ở dạng minh họa. Không tự chọn nó để xác minh chữ ký của ID token `RS256` chỉ vì `kty=RSA`. Nếu cả `use` lẫn `key_ops` được công bố, chúng phải nhất quán với mục đích và profile.

## 5. Một ID token được xác minh qua JWKS như thế nào?

Trong **OpenID Connect**, Client/Relying Party thường nhận **ID token** sau khi hoàn thành một luồng OIDC hợp lệ. Với ID token JWS ký bằng RS256:

~~~text
BASE64URL(JWS protected header)
.
BASE64URL(ID token payload)
.
BASE64URL(signature)
~~~

Đây là dạng **JWS Compact Serialization** cho một JWT được ký. **Chia chuỗi theo dấu chấm rồi decode payload không phải xác minh chữ ký**.

### Protected header minh họa

~~~json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "signing-2026-11"
}
~~~

### ID token payload minh họa

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "shop-web",
  "exp": 1893456600,
  "iat": 1893456000,
  "nonce": "<NONCE_FROM_ORIGINAL_OIDC_REQUEST>"
}
~~~

Payload chỉ minh họa, không phải ID token thật. NumericDate dùng giây Unix. Với OIDC, ID token phải được Client kiểm tra theo đúng luồng và profile, không chỉ signature.

### Trình tự kiểm tra

~~~mermaid
sequenceDiagram
    participant Browser
    participant RP as OIDC Relying Party
    participant OP as OpenID Provider
    participant JWKS as Trusted JWKS endpoint
    Browser->>RP: Callback authorization code + state
    RP->>RP: Verify state, issuer/context, PKCE transaction
    RP->>OP: Đổi code tại token endpoint với PKCE và client auth nếu cần
    OP-->>RP: ID token (và access token theo grant)
    RP->>RP: Đọc header alg/kid như input chưa đáng tin
    RP->>JWKS: Lấy/cache public keys từ jwks_uri đã xác minh
    JWKS-->>RP: JWK Set thuộc issuer đáng tin
    RP->>RP: Chọn key phù hợp, verify JWS signature
    RP->>RP: Validate iss, aud, azp/nonce nếu áp dụng, exp/iat, chính sách OIDC
    RP-->>Browser: Tạo session cho user đã được xác minh
~~~

Các bước rút gọn, không mô tả tất cả token endpoint/consent. **RP không được tạo session từ các claims chưa verify**.

### Những điều Client/RP cần làm ngoài việc tìm khóa

1. **`iss`:** token phải được phát bởi OP **đúng issuer đã được chọn cho giao dịch**.
2. **`aud`:** ID token phải có audience chứa **`client_id` của RP**; nếu có nhiều audience, cần xử lý **`azp`** theo quy tắc OIDC.
3. **`exp`, `iat`:** phải phù hợp thời gian và profile; cân nhắc clock skew nhỏ theo chính sách.
4. **`nonce`:** nếu Client đã gửi nonce hoặc profile yêu cầu, phải so khớp nonce của giao dịch.
5. **`auth_time`:** kiểm tra nếu request/profile (ví dụ `max_age`) cần thời điểm xác thực.
6. **`at_hash`/`c_hash`:** kiểm tra khi thuộc flow/profile yêu cầu (ví dụ trường hợp có token/code cùng authorization response); đừng đòi chúng vô điều kiện ở mọi Code flow.
7. **Thuật toán/loại token:** áp dụng chính sách signing algorithm và token semantics, không chấp nhận mọi JWT ký được bằng cùng khóa.

**Không dùng ID token để gọi Orders API** chỉ vì OP ký bằng một public key có trong JWKS. ID token có audience là **RP/Client**, không phải Resource Server của đơn hàng.

## 6. JWKS giúp xác minh JWT access token nhưng không thay quyền API

OAuth 2.0 **không bắt buộc** access token là JWT; nhiều AS phát **opaque token**. Nếu AS phát **JWT access token** mà Resource Server có hợp đồng nhận, RS có thể xác minh chữ ký bằng JWKS của issuer.

### Ví dụ JWT access token cho Orders

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "client_id": "shop-web",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456600
}
~~~

Trong **RFC 9068 (JWT Profile for OAuth 2.0 Access Tokens)**, Resource Server cần kiểm tra token type trong JWS header theo profile (ví dụ `typ=at+jwt` hoặc media type tương đương), **issuer, audience, thời gian, chữ ký** và những yêu cầu của profile.

| Token | Người nhận hợp lệ | JWKS có vai trò gì? | Không được nhầm |
|---|---|---|---|
| **OIDC ID token** | Relying Party/Client, `aud` thường chứa `client_id`. | Xác minh chữ ký ID token do OP ký. | Không là quyền gọi RS. |
| **JWT access token** | Resource Server nằm trong `aud`. | Xác minh chữ ký nếu token dạng JWS theo hợp đồng AS/RS. | Signature đúng không đủ; phải kiểm tra type, scope/permission/object. |
| **Opaque access token** | Resource Server theo hợp đồng. | **Không decode JWT/JWKS để xác minh token opaque**. | Dùng introspection/tra cứu token tin cậy theo cấu hình. |
| **Refresh token** | Token endpoint của Authorization Server. | Không mặc nhiên là JWT public-verifiable dành cho API. | Không trình refresh token cho RS. |
| **Client assertion JWT** | AS token endpoint để xác thực Client khi dùng `private_key_jwt`. | AS dùng **client keys đăng ký** để verify assertion. | Không mặc nhiên dùng JWKS của OP để xác thực khóa Client. |

### Một chữ ký hợp lệ chưa phải đủ điều kiện đọc dữ liệu

~~~text
JWT signature đúng
issuer = https://auth.example.test
audience = orders-api
scope = orders:read

Nhưng:
  Token sub = user-123 thuộc tenant-a
  Order #999 thuộc user-999 và tenant-b

=> Orders API phải từ chối nếu không có quyền override rõ ràng.
~~~

JWKS chỉ hỗ trợ **mật mã và key lifecycle**. Nó không biết owner của đơn hàng, chính sách tenant, scope mà endpoint cần hoặc người giữ bearer token hiện tại có phải Client ban đầu hay không.

## 7. Bootstrap trust: đừng để JWT header quyết định nơi tải khóa

JWS protected header có thể chứa một số tham số như:

~~~json
{
  "alg": "RS256",
  "kid": "signing-2026-11",
  "jku": "https://untrusted.example.org/attacker-jwks"
}
~~~

**Header nằm trong token do caller gửi**, vì vậy **chưa đáng tin trước khi verify**. Nếu verifier làm theo `jku` để tải bất kỳ JWKS nào, attacker có thể tự tạo key pair, ký JWT rồi trỏ tới public key của mình, hoặc hướng hệ thống thực hiện HTTP request ngoài ý muốn.

### Quy tắc chống `jku`/`x5u` injection và SSRF

- **Tin JWKS endpoint từ cấu hình issuer/metadata đã được kiểm tra**, không từ URL tùy ý trong JWT.
- Mặc định **bỏ qua hoặc từ chối `jku`/`x5u` không nằm trong profile/allowlist tin cậy**.
- Nếu môi trường bắt buộc cho phép URL key/certificate, dùng allowlist host/scheme/path, DNS/IP restrictions, TLS, giới hạn redirect/response size/time; tránh SSRF đến metadata service/private network.
- Không cho `kid` điều khiển filesystem path, SQL fragment hay URL thông qua nối chuỗi không kiểm soát.
- Không cho token tự thay đổi **trusted issuer** chỉ bằng claim `iss`.

### Nguồn tin cậy phải được ràng buộc với issuer

~~~text
Trusted issuer A -> Discovery A -> JWKS A -> token A
Trusted issuer B -> Discovery B -> JWKS B -> token B

SAI:
  token có iss=B nhưng dùng khóa của A để chấp nhận;
  token không xác minh nhưng tự chỉ JWKS của B bất kỳ.
~~~

Hai issuer dùng cùng `kid=key1` không biến chúng thành một tổ chức tin cậy. **Cache và key selection phải có namespace theo issuer/trust domain**.

## 8. Thuật toán chữ ký phải được pin theo policy

JWT header thường chứa `alg`. Verifier **cần đọc `alg` để chọn quy trình xác minh phù hợp**, nhưng **không được cho attacker quyết định thuật toán mà hệ thống sẵn lòng tin**.

### Những lỗi nguy hiểm

| Lỗi | Điều có thể xảy ra | Phòng ngừa |
|---|---|---|
| Chấp nhận `alg=none` với token vốn phải ký | Token tự tạo không có chữ ký được chấp nhận. | Chỉ cho các thuật toán được AS/profile cho phép, không chấp nhận unsigned token trong ngữ cảnh yêu cầu ký. |
| **RS256 ↔ HS256 confusion** | Public RSA key bị dùng nhầm như HMAC secret. | Ràng buộc alg, key type, key usage; không coi RSA public key là symmetric key. |
| Tin `alg` trong JWK để mở allowlist | Endpoint/key metadata có thể khiến verifier nới thuật toán. | Allowlist thuật toán từ cấu hình tin cậy và hợp đồng profile. |
| Tin `kid` rồi chọn bất kỳ key | Token bị verify bằng key sai nguồn hoặc sai mục đích. | Chỉ key từ JWKS của issuer, lọc `use`/`key_ops`/`kty`. |
| Chấp nhận `crit` chưa hiểu | Bỏ qua yêu cầu bảo vệ mở rộng. | JWS processor phải hiểu/xử lý đúng critical header; nếu không, từ chối. |
| Bỏ qua `typ` khi ID/AT dùng chung khóa | **Cross-JWT confusion**, ID token bị nhận là access token. | Áp dụng token type/profile và claims cho từng nơi nhận. |

### Ma trận tương thích minh họa

| JWT `alg` | Public key type thường dùng | Ví dụ JWK | Điều kiện |
|---|---|---|---|
| **RS256** | RSA | `kty=RSA`, `n`, `e`. | RS256 nằm trong allowlist của issuer/profile. |
| **PS256** | RSA | RSA public key. | RSASSA-PSS được hệ thống cho phép và implement đúng. |
| **ES256** | EC P-256 | `kty=EC`, `crv=P-256`, `x`, `y`. | Chấp nhận ES256 và xác minh ECDSA đúng chuẩn JOSE. |
| **EdDSA** | OKP, đường cong phù hợp | `kty=OKP`, `crv=Ed25519`, `x`. | Thư viện và profile hỗ trợ, không chấp nhận vì thấy tên alg lạ. |
| **HS256** | Symmetric secret | `kty=oct`. | **Không dùng public RSA key** làm HMAC secret; OIDC ID token HS* có quy tắc dùng secret khác, không phải endpoint JWKS public. |

Trong OIDC, thuật toán HMAC có thể xuất hiện trong một số cấu hình Client/ID token theo đặc tả; **đừng suy rằng JWKS public cung cấp secret để verify HS256**. Phải tuân thủ đúng profile và key source được thiết lập qua quan hệ Client–OP.

**Sử dụng thư viện JOSE/JWT được kiểm chứng**. Không tự viết hàm verify RSA/ECDSA/HMAC, không chỉ base64-decode rồi tin `sub`/`scope`.

## 9. Chọn khóa an toàn khi nhiều `kid` hoặc khóa trùng

Giả sử JWKS hiện có:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "old-signing-key",
      "use": "sig",
      "alg": "RS256",
      "n": "<OLD_PUBLIC_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "new-signing-key",
      "use": "sig",
      "alg": "RS256",
      "n": "<NEW_PUBLIC_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

Một token được ký bằng private key mới có header:

~~~json
{
  "alg": "RS256",
  "kid": "new-signing-key",
  "typ": "JWT"
}
~~~

Verifier thực hiện:

1. Xác định **trusted issuer** từ ngữ cảnh ứng dụng và kiểm tra claim `iss` sau verify.
2. Lấy bộ khóa của **issuer đó**.
3. Dùng `kid` làm gợi ý chọn JWK **trong bộ khóa ấy**.
4. Lọc theo `alg` được phép, `kty`, `use`/`key_ops` phù hợp và profile.
5. Nếu chọn được khóa hợp lệ, **xác minh chữ ký**.
6. **Không thử key của issuer khác** nếu verify thất bại.
7. Sau chữ ký, xác minh **audience, token type, exp/nbf/nonce/scope** theo nơi nhận.

### Nếu token không có `kid`?

JWS/JWK không bắt mọi token luôn có `kid`, nhưng nhiều triển khai production yêu cầu nó để vận hành nhiều khóa. Nếu thiếu `kid`:

- Dựa vào **profile và policy** của issuer/verifier; có thể từ chối.
- Nếu profile cho phép lựa chọn khi chỉ có một khóa phù hợp, phải bảo đảm **duy nhất và rõ ràng**, không chọn ngẫu nhiên.
- Không dùng chiến thuật “thử mọi khóa trên Internet đến khi có chữ ký đúng”.

### Nếu có hai JWK cùng `kid`?

Một JWKS chứa `kid` trùng cho các khóa ký khác nhau gây mơ hồ. Hệ thống nên coi đây là **bất thường cấu hình** và không nhận key selection mơ hồ, đặc biệt khi `kty`/`alg` cùng phù hợp. Đừng chọn “phần tử đầu tiên” theo thứ tự JSON rồi hy vọng an toàn.

### Nếu token có `kid` lạ?

Điều này thường gặp khi AS **mới xoay khóa nhưng Client vẫn cache JWKS cũ**. Có thể thử **refresh JWKS có kiểm soát một lần** theo policy; nếu vẫn không tìm thấy khóa hợp lệ thì **từ chối token**. Không fallback sang verify không chữ ký hoặc tải URL do header token chỉ định.

## 10. Key rotation / rollover: vòng đời của JWKS

Mỗi khóa ký cần có một vòng đời rõ ràng:

~~~mermaid
flowchart LR
    A["Tạo key pair mới trong KMS/HSM/keystore"] --> B["Công bố public key mới trong JWKS"]
    B --> C["Chờ cache/verifier nhận key mới"]
    C --> D["OP bắt đầu ký JWT bằng private key mới và kid mới"]
    D --> E["Giữ public key cũ trong thời gian token cũ còn hợp lệ"]
    E --> F["Ngừng phát token bằng khóa cũ; hết TTL/grace phù hợp"]
    F --> G["Gỡ public key cũ khỏi JWKS và thu hồi private key cũ"]
~~~

### Cửa sổ chồng lấp khóa

Ví dụ timeline:

| Mốc | JWKS công bố | Khóa OP dùng ký | Tác động |
|---|---|---|---|
| **T0** | `key-A`. | `key-A`. | Trạng thái ban đầu. |
| **T1** | `key-A` và `key-B`. | Vẫn `key-A`. | Verifier có cơ hội cache B trước khi token B xuất hiện. |
| **T2** | `key-A` và `key-B`. | Bắt đầu `key-B`. | Token mới có `kid=B`; token cũ dùng A vẫn xác minh được. |
| **T3** | `key-A` và `key-B`. | `key-B`. | Chờ các token ký bằng A hết hạn hoặc được thu hồi theo policy. |
| **T4** | Chỉ `key-B`. | `key-B`. | Gỡ A sau khi đủ điều kiện kết thúc chuyển tiếp. |

**Đừng gỡ A ngay khi vừa bắt đầu ký bằng B**, nếu vẫn còn ID/access token ký bằng A được kỳ vọng sử dụng và chưa hết hạn. Ngược lại, **không giữ private key cũ vô hạn** chỉ vì ngại cập nhật cache.

### Nguyên tắc triển khai

1. Tạo private key mới trong nơi lưu an toàn; không xuất private material lên JWKS.
2. Cấp **`kid` duy nhất trong phạm vi issuer** cho khóa mới, tránh gán lại ID cũ cho key mới.
3. Công bố public key mới **trước** khi dùng nó ký, khi có thể.
4. Tính **JWKS cache TTL, token TTL, clock skew, propagation delay, số lượng verifier** để lên lịch.
5. Sau cutover, tiếp tục công bố khóa cũ đủ lâu cho token cũ còn giá trị **nếu không phải sự cố an ninh**.
6. Khi kết thúc, gỡ khóa cũ, xóa/thu hồi private key theo policy và kiểm tra không còn issuer signing service dùng nó.
7. Audit bằng **key ID/version và issuer**, không log private key.

### Khi cùng một issuer phục vụ nhiều loại token

ID token và JWT access token có thể được ký bằng **cùng key pair** hoặc **khóa riêng** tùy AS. Dù dùng chung key, RP và RS **không được dùng chung token validation policy**: ID token cần audience của Client và OIDC checks, access token cần audience/resource, type, scope và quyền dữ liệu.

## 11. JWKS caching: vừa hiệu năng vừa an toàn

Không nên fetch JWKS **cho từng request API**. Điều này tạo phụ thuộc mạng, tăng tải OP và làm hệ thống dễ bị DoS. Nhưng cache vô hạn cũng rủi ro khi **khóa đã bị thu hồi**.

### Các yếu tố HTTP có thể dùng

~~~http
GET /oauth2/jwks HTTP/1.1
Host: auth.example.test
If-None-Match: "jwks-version-42"
Accept: application/json
~~~

~~~http
HTTP/1.1 304 Not Modified
ETag: "jwks-version-42"
Cache-Control: public, max-age=300
~~~

`Cache-Control`, `ETag` và `304 Not Modified` có thể hỗ trợ cache/revalidation **nếu OP triển khai**. Không phụ thuộc giả định rằng mọi OP đều dùng cùng `max-age` hoặc `ETag`. Thư viện JWKS có thể có chính sách cache riêng, cần hiểu cách nó thực hiện.

### Các trường hợp vận hành

| Trường hợp | Xử lý an toàn |
|---|---|
| `kid` đã có trong cache, chữ ký và các điều kiện đúng | Dùng key cached theo TTL/policy, không gọi OP liên tục. |
| Gặp `kid` mới chưa có trong cache | Có thể refresh JWKS **có giới hạn** rồi thử chọn key lại một lần. |
| Token sai chữ ký nhưng `kid` quen thuộc | **Từ chối**; đừng tự xem signature failure là tín hiệu phải tin endpoint khác. |
| JWKS endpoint trả 404, 5xx hoặc JSON không hợp lệ | **Không fail-open**; xử lý availability riêng và chỉ dùng cache còn được policy cho phép. |
| Cache hết hạn, không thể liên hệ OP | Từ chối token khi không còn cơ sở tin cậy hợp lệ; có thể áp dụng grace policy được phân tích rủi ro cho key đã tin, không tự động vô hạn. |
| JWKS bị thay đổi bất thường, rất nhiều key | Giới hạn response size/key count, validate cấu trúc và phát cảnh báo. |
| Nhiều request cùng `kid` lạ | Rate-limit refresh, **single-flight** hoặc negative cache để chặn request storm. |
| Có thông báo key compromise | Purge/invalidate cache theo quy trình khẩn cấp, đẩy key policy mới tới verifier. |

### Chống `kid`-spam và JWKS refresh storm

Attacker có thể gửi hàng nghìn JWT với header `kid=random-1`, `kid=random-2`... Nếu mỗi unknown `kid` khiến RS tải JWKS từ OP ngay, attacker tạo **DoS gián tiếp**.

Giải pháp:

- Chỉ refresh khi **cache policy cho phép**, giới hạn tốc độ và đồng bộ các request.
- Chặn/giới hạn kích thước header, độ dài `kid` và số lượng key.
- Dùng negative cache ngắn cho `kid` đã biết không tồn tại, kết hợp rate limit.
- Không sử dụng JWKS fetch thất bại làm lý do chấp nhận token không verify.
- Phát hiện sự tăng bất thường của `unknown_kid`, signature failures và cache misses.

### Cache key không chỉ là `kid`

~~~text
SAFE conceptual cache key:
  (trusted_issuer, jwks_uri_or_source_version, key_id, permitted_key_use)

UNSAFE:
  globalMap[kid] -> key, bất kể issuer/tenant
~~~

Đây là cấu trúc **khái niệm**; thực tế dùng cache theo provider/trust domain do thư viện quản lý. Mục đích là tránh **cross-issuer key confusion** và rò rỉ ranh giới multi-tenant.

## 12. Khi signing key bị lộ: không thể chỉ rotate chậm

**Planned rotation** và **emergency key revocation** là hai quy trình khác nhau.

### Planned rotation

Khi không có bằng chứng private key bị lộ, OP có thể công bố khóa mới trước, ký bằng khóa mới và giữ public key cũ trong JWKS cho đến khi token cũ hết hạn theo chính sách.

### Emergency compromise

Nếu private key ký token bị lộ, attacker **có thể tạo token với chữ ký hợp lệ bằng chính khóa đó**. Trong tình huống này:

1. **Ngừng dùng private key cũ ngay** và khóa quyền ký trái phép.
2. Chuyển sang key pair an toàn, thu hồi/quản lý trạng thái khóa cũ.
3. **Gỡ khóa bị lộ khỏi JWKS/trust policy** và chủ động **invalidate JWKS cache** tại verifier; đừng đợi mọi cache tự hết TTL nếu cần xử lý khẩn cấp.
4. Đánh giá **token đã phát bằng khóa cũ**: có thể phải vô hiệu hoặc yêu cầu cấp lại, kể cả token hợp lệ chưa hết `exp`.
5. Kiểm tra hệ thống có **nhiều RS/RP/cache node** hay không; một node còn giữ khóa cũ có thể vẫn chấp nhận token giả.
6. Điều tra log key access/KMS signing operation, token issuance, client/tenant impact và phạm vi dữ liệu.
7. Khôi phục khả năng phát hành/kiểm tra token hợp lệ bằng khóa mới, theo dõi retry/failure và audit.

~~~mermaid
flowchart TD
    A["Phát hiện signing private key bị lộ"] --> B["Khóa key cũ; tạo và kích hoạt key mới"]
    B --> C["Cập nhật JWKS/trust policy"]
    C --> D["Purge cache ở RP/RS/verifier"]
    D --> E["Đánh giá revoke/reissue token ký bằng key cũ"]
    E --> F["Kiểm tra issuer/aud/tenant/incident scope"]
    F --> G["Chứng minh không còn verifier nhận khóa đã bị thu hồi"]
~~~

**Gỡ key khỏi JWKS không tự làm cache của mọi verifier biến mất ngay.** Nếu Token vẫn được verify offline bằng public key cũ nằm trong cache, cần cơ chế cấp bách hơn như cache invalidation, denylist hoặc yêu cầu thay đổi key policy.

## 13. `x5c`, `x5u`, JWS và JWE: các lớp không được nhầm

### `x5c` là chuỗi chứng chỉ, không phải một authorization grant

JWK có thể đính kèm **X.509 certificate chain** trong `x5c`. Nó có thể giúp gắn public key với chứng chỉ, nhưng **cần xác minh đúng nguồn và chain/policy nếu thiết kế yêu cầu**. Không suy rằng “có certificate hợp lệ” nghĩa là token có issuer/audience/subject được phép.

### `x5u` và `jku` là URL — rủi ro khi tải tự động

- `x5u` có thể trỏ tới tài nguyên chứng chỉ.
- `jku` trong JWS header có thể chỉ JWKS URI.
- **Cả hai không được quyền tự động thay trusted `jwks_uri` từ OIDC Discovery**, nếu không có một profile/allowlist bảo mật rõ.
- Truy cập URL do attacker kiểm soát có thể gây **SSRF** và **key substitution**.

### Ký và mã hóa là hai mục tiêu khác nhau

| Dạng | Thành phần mật mã | JWKS liên quan như thế nào? |
|---|---|---|
| **JWS (Signed JWT)** | Signature/MAC bảo vệ toàn vẹn và nguồn khóa ký. | Verifier dùng public signing key của OP/AS khi alg bất đối xứng. |
| **JWE (Encrypted JWT)** | Mã hóa bảo mật nội dung cho recipient. | Recipient dùng **private decryption key**; public encryption key có thể được công bố ở JWKS thích hợp. |
| **Nested JWT** | Có thể kết hợp JWE và JWS. | Cần kiểm tra **từng lớp** theo profile, không chỉ giải mã xong rồi tin claims. |
| **Opaque token** | Chuỗi tham chiếu/trạng thái do AS quản lý. | Không xác minh bằng cách tìm `kid` trong JWKS. |

Nếu token được **mã hóa**, việc decrypt thành công **không mặc nhiên** đồng nghĩa đã xác minh được chữ ký/issuer và audience. Nếu token được **ký**, signature bảo vệ toàn vẹn nhưng **không mã hóa payload**: JWT payload có thể được đọc bởi bên có token nếu không mã hóa.

### Không công bố private decryption key

Tương tự private signing key, **private decryption key của recipient** không được xuất ra JWKS công khai. Khi OP cần **public encryption key của Client** để gửi ID token/JWT response mã hóa, cấu hình và nguồn JWKS của Client là một quan hệ riêng, không thể đồng nhất với JWKS chứa signing keys của OP.

## 14. Multi-issuer, multi-tenant và federation

Một ứng dụng enterprise có thể tin nhiều OP hoặc nhiều tenant:

~~~text
Tenant A:
  expected issuer = https://login-a.example.test
  trusted jwks_uri = https://login-a.example.test/keys

Tenant B:
  expected issuer = https://login-b.example.test
  trusted jwks_uri = https://login-b.example.test/keys
~~~

### Nguyên tắc thiết kế

1. **Trusted issuer registration phải được quản trị**: chỉ cho những OP/tenant được phép. Không biến mọi URL user nhập thành issuer đáng tin.
2. Mỗi issuer có metadata, JWKS cache, signing algorithm policy và issuer validation **riêng**.
3. **`kid` không phải global identifier**; cùng `kid=key-1` ở hai tenant không cho phép dùng chéo key.
4. JWT có `iss=A` nhưng chứa `aud` của Client B không tự hợp lệ; audience phải khớp RP/RS nhận token.
5. Khi nhiều OP trả callback OAuth/OIDC, Client cần **authorization server mix-up defense**, ràng buộc issuer với authorization request/response (có thể dùng **RFC 9207** khi profile hỗ trợ).
6. Khi OP tự động phát metadata thay đổi `jwks_uri` sang host mới, nên áp dụng **source validation/monitoring** và chính sách thay đổi tin cậy; không cho redirect tự do sang domain bất kỳ.
7. Sau xác thực, quyền app vẫn cần **tenant mapping** và object authorization; một chữ ký đúng của tenant A không cho user quyền trên dữ liệu tenant B.

### Issuer exact matching

~~~text
Expected issuer:
  https://auth.example.test/tenant-a

Token issuer:
  https://auth.example.test/tenant-b

=> REJECT nếu tenant-a và tenant-b là trust domains riêng.
~~~

Không so `iss` bằng `startsWith("https://auth.example.test")` hoặc dựa vào hostname gần giống. **Issuer phải khớp chính xác** theo quy tắc provider/profile và cấu hình đã chấp nhận.

## 15. Spring Security: Resource Server dùng JWKS và kiểm tra audience

Với Spring Security, **JWT Resource Server** có thể cấu hình issuer để framework khám phá metadata và JWK Set URI, hoặc dùng trusted JWKS URI do quản trị cấu hình. Quan trọng là **mở đúng trust anchor** và **kiểm tra audience**.

### Spring Boot issuer-based configuration

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Khi dùng issuer-based configuration và phiên bản Spring Security phù hợp, framework có thể lấy JWKS URI qua metadata endpoint được hỗ trợ. Từng phiên bản có thể khác ở thời điểm fetch (startup hay request đầu tiên) và cache policy; **không được mặc định rằng cấu hình issuer chỉ một mình đã kiểm tra audience của Orders API**.

### Java minh họa đặt trusted JWKS URI và audience validator

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtValidationConfig {
    private static final String TRUSTED_ISSUER =
            "https://auth.example.test";
    private static final String TRUSTED_JWKS =
            "https://auth.example.test/oauth2/jwks";
    private static final String EXPECTED_AUDIENCE = "orders-api";

    @Bean
    JwtDecoder ordersJwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(TRUSTED_JWKS)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(EXPECTED_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                            "JWT audience is not orders-api", null));
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER),
                audienceValidator));
        return decoder;
    }
}
~~~

**Giới hạn quan trọng của ví dụ:**

- `TRUSTED_JWKS` phải lấy từ **cấu hình/metadata đáng tin** và được gắn với `TRUSTED_ISSUER`; không lấy từ header token hay request user.
- Ví dụ chỉ chấp nhận **RS256**; nếu OP thực sự dùng ES256 hoặc profile khác, cấu hình phải được quản trị phù hợp, **không tự chấp nhận mọi thuật toán**.
- `JwtValidators.createDefaultWithIssuer` kiểm tra issuer và những điều kiện mặc định như thời hạn theo cấu hình framework; audience được kiểm tra **tường minh**.
- Ví dụ chưa thể hiện đầy đủ kiểm tra **JWT access token type (RFC 9068 `typ`)**, scope, tenant, sender proof và object authorization. Hãy bổ sung các validator/policy đó khi dùng JWT profile tương ứng.
- Nếu bạn chọn **opaque token**, cần cấu hình resource server opaque introspection, không dùng decoder JWT.
- Mã là **minh họa Spring Security 6-style**, cần dependencies/cấu hình dự án phù hợp; không giả định một đoạn bean đủ tạo API hoàn chỉnh.

### Scope và quyền trên từng đơn

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderReadService {

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public OrderDto readAuthorizedOrder(String orderId) {
        // Tra token principal đã verify và kiểm tra owner/tenant
        // từ DB/policy đáng tin, trước khi trả dữ liệu.
        return loadOrderAfterOwnerAndTenantChecks(orderId);
    }
}
~~~

Nếu dùng `@PreAuthorize`, ứng dụng phải bật **method security** tương ứng (`@EnableMethodSecurity`) và dùng JWT-to-authority mapping đúng hợp đồng. `SCOPE_` là convention phổ biến của Spring Security, **không phải claim do JWKS cấp**. **Object authorization không thể thay bằng việc signature JWT hợp lệ**.

## 16. Spring Security: OIDC Client/Relying Party dùng issuer metadata

Đối với ứng dụng web đăng nhập qua OIDC, Spring Security OAuth2 Login có thể cấu hình issuer:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          shop:
            provider: company-op
            client-id: shop-web
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company-op:
            issuer-uri: https://auth.example.test
~~~

**`${OIDC_CLIENT_SECRET}` là placeholder biến cấu hình**, không phải secret để commit vào Git. Với môi trường đã cấu hình đúng, Spring có thể dùng discovery metadata để xác định endpoints/JWKS và xác minh ID token theo OIDC.

### Không trộn ID-token validation với API access-token validation

| Ứng dụng | Token cần verify | Audience phù hợp | Quyết định kế tiếp |
|---|---|---|---|
| **Shop RP** | OIDC ID token do OP ký. | `shop-web`, xử lý `azp` khi cần. | Tạo/duy trì session user theo OIDC. |
| **Orders Resource Server** | Access token dành cho Orders. | `orders-api`. | Scope `orders:read` và owner/tenant authorization. |
| **Billing Resource Server** | Access token dành cho Billing. | `billing-api`. | Scope/payment permission tương ứng. |

Một ID token có `sub=user-123`, `aud=shop-web` và chữ ký hợp lệ **không được Orders chấp nhận**, kể cả khi OP dùng **cùng `kid`/JWKS** để ký cả ID token và access token.

### PKCE, client authentication, nonce và JWKS ở các bước khác nhau

- **PKCE** ràng buộc authorization code với verifier của transaction khi đổi code.
- **Client authentication** chứng minh confidential Client tại token endpoint.
- **`state` / issuer binding** liên kết callback với giao dịch khởi tạo.
- **OIDC nonce** ràng buộc ID token với request khi cần.
- **JWKS** giúp xác minh signature của ID token/JWT access token.
- **Scope/audience/RS policy** quyết định token được dùng ở đâu và quyền nào thực sự có hiệu lực.

Không bỏ một lớp chỉ vì lớp khác đã thành công.

## 17. Thiết kế JWKS endpoint ở phía Authorization Server

Không chỉ bên nhận token cần làm đúng. OP/AS cũng phải công bố JWKS với vòng đời khóa có kiểm soát.

### Yêu cầu công bố

1. **Chỉ công bố public key material** phục vụ các profile đã được phép; không đưa private key/JWK `d`, RSA primes hoặc secret HMAC ra endpoint công khai.
2. Cung cấp **`kid` rõ ràng và nhất quán** cho key version đang sử dụng, tránh trùng `kid` trong các signing keys gây mơ hồ.
3. Nếu khai `use`, `key_ops`, `alg`, phải phù hợp key type và thực tế sử dụng.
4. Duy trì **HTTPS**, server certificate, kiểm soát đường truyền/cache/CDN, rate limiting và giới hạn kích thước dữ liệu.
5. Áp dụng **Cache-Control/ETag** phù hợp lịch key rotation để verifier cập nhật kịp.
6. Đăng metadata **`jwks_uri` đúng URL** và bảo đảm issuer/discovery không tạo các đích redirect bất ngờ.
7. Xem xét khả năng **JWK Set phân tán qua nhiều AS node**: các node phải công bố/nhận key set nhất quán trước khi ký bằng khóa mới.
8. Thiết kế **emergency key revocation** gồm thông báo/invalidate verifier cache, không chỉ đổi JSON trên một instance.

### Kiểm tra endpoint trước khi phát hành

~~~text
CHECK:
  GET discovery -> issuer đúng, jwks_uri đúng và HTTPS
  GET JWKS -> valid JSON object có keys array
  signing keys -> public-only; không có private parameters
  each kid -> đúng phạm vi issuer, không mơ hồ
  advertised algorithms -> phù hợp AS policy
  old/new keys -> overlap đủ cho planned rotation
  Cache-Control/ETag -> hoạt động như thiết kế
  key compromise -> có thủ tục thu hồi và cache purge
~~~

### Tránh lộ khóa qua hệ thống phụ trợ

Private key phải được giữ trong **KMS/HSM/keystore được kiểm soát** khi phù hợp. Không log private material, không đưa vào container image, không xuất secret sang CDN để tạo JWKS. **JWKS generator chỉ cần public parameters**, hoặc public-key export theo cơ chế của KMS, không cần lấy private key vào process web chỉ để tạo JSON.

## 18. Lỗi vận hành thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra không làm giảm bảo mật |
|---|---|---|
| Token mới bị 401 ngay sau rotation | Token có `kid` mới nhưng RS đang cache JWKS cũ. | So metadata issuer/JWKS, kiểm tra TTL và planned overlap. |
| Một vài node chấp nhận, node khác từ chối | Cache/key set hoặc thời gian hệ thống không đồng nhất. | So key IDs, cache age, issuer config, clock skew. |
| Mọi token đều báo invalid signature | Sai JWKS URI, thuật toán, key type hoặc ký bằng private key khác. | Kiểm tra issuer và public fingerprint/`kid` từ nguồn đáng tin, không log full token. |
| Token ID hợp lệ nhưng API trả 401 | API yêu cầu access token với audience/typ khác. | Xem **token type và audience**, không tắt kiểm tra signature. |
| Token JWT có `aud` khác cấu hình RS | Token được cấp cho Resource Server khác. | Sửa AS resource indicator/client registration, không nới audience bừa bãi. |
| `kid` lạ lặp lại hàng nghìn lần | Attacker hoặc client lỗi tạo unknown-kid storm. | Rate-limit JWKS refresh và phân loại request. |
| OIDC login hoạt động nhưng token API sai | RP và RS dùng policy khác nhau. | Kiểm tra ID vs access token, issuer, audience, scope. |
| JWKS endpoint timeout | AS/CDN/network lỗi, cache policy không phù hợp. | Xác minh reachability/TLS, dùng cached key theo policy hoặc fail closed. |
| Metadata `issuer` khác expected | Sai tenant/path/issuer hoặc cấu hình/redirect nhầm. | Từ chối provider, sửa registration/metadata. |
| AS đã gỡ khóa bị lộ mà RS vẫn nhận token | Cache còn key cũ hoặc thiếu revocation. | Purge cache, cập nhật trust policy, kiểm tra token state. |
| Token có `jku` lạ và request đi tới host nội bộ | Verifier fetch URL từ header chưa tin. | Chặn external key URL, xử lý SSRF và rà soát log. |
| JWK chứa `d` trên public endpoint | Lộ private key. | Kích hoạt incident, revoke/rotate signing key và token liên quan. |

### Logging không làm lộ token

Có thể ghi **issuer tin cậy, key ID, thuật toán được kiểm tra, lỗi kiểm tra, cache version, HTTP status của JWKS fetch**. Không ghi **full ID/access/refresh token**, private key, client secret hoặc Authorization header vào log/tracing. Claim `sub`/tenant nếu cần audit cũng phải theo chính sách quyền riêng tư.

## 19. Ma trận kiểm thử bảo mật JWKS metadata

Giả sử OP đáng tin là `https://auth.example.test`, discovery công bố `jwks_uri=https://auth.example.test/oauth2/jwks`, Client OIDC có `client_id=shop-web`, Orders API có audience `orders-api`.

| Kịch bản | Kỳ vọng | Cần chứng minh |
|---|---|---|
| Discovery trả đúng `issuer` và JWKS URI cấu hình | Có thể tải key set theo policy. | Trust bootstrap đúng. |
| Discovery `issuer` khác issuer mong đợi | **Từ chối**. | Chống issuer mix-up. |
| Token có `iss` của attacker và header `jku` đến domain attacker | **Từ chối**, không tin key tự khai. | Chống key substitution. |
| JWT `alg=none` trong hệ thống yêu cầu RS256 | **Từ chối**. | Algorithm allowlist. |
| JWT `alg=HS256` với public RSA key làm HMAC secret | **Từ chối**. | Chống RSA/HMAC confusion. |
| JWT `alg=RS256`, đúng issuer/`kid`, chữ ký thật | Tiếp tục kiểm tra claims/profile. | Signature chỉ là một lớp. |
| JWT đúng `kid` nhưng signature sai | **Từ chối**. | Không tin `kid` thay chữ ký. |
| JWT có `kid` không tồn tại, cache cũ | Refresh có giới hạn; từ chối nếu vẫn không có key. | Rotation và fail closed. |
| Attacker gửi hàng nghìn `kid` khác nhau | Refresh được rate-limit/đồng bộ, không DDoS AS. | Chống JWKS request storm. |
| JWK `use=enc` được dùng làm signing verification key | **Không chấp nhận** nếu profile/policy không cho. | Key usage separation. |
| JWKS chứa private RSA `d`, `p`, `q` công khai | **Báo sự cố và rotate**. | Không tiết lộ private key. |
| JWKS có hai signing keys cùng `kid` gây mơ hồ | Không chọn ngẫu nhiên. | Deterministic safe key selection. |
| JWKS mới công bố public key B trước khi OP ký B | Verifier có thể chuẩn bị/cập nhật key. | Planned rotation đúng. |
| OP bắt đầu ký B nhưng JWKS chỉ có A | Token B bị từ chối; cảnh báo rollout lỗi. | Không bỏ verify để tránh downtime. |
| OP gỡ A khi token ký A còn hạn theo kế hoạch | Token A có thể bị từ chối; cảnh báo rotation overlap sai. | Token TTL và key lifecycle. |
| OP gỡ khóa bị lộ nhưng RS vẫn cache key | Purge/invalidate cache khẩn cấp. | Key compromise response. |
| JWKS endpoint 503 nhưng cache còn key hợp lệ theo policy | Có thể xác minh theo chính sách cache; không tin key khác. | Availability vs trust. |
| JWKS endpoint 503, key unknown và không có nguồn tin | **Từ chối token**. | Fail closed. |
| ID token `aud=shop-web` và chữ ký đúng | RP tiếp tục validate OIDC claims. | Đúng nơi nhận. |
| ID token `aud=shop-web` trình cho Orders API | **Orders từ chối**. | Cross-token confusion prevention. |
| JWT access token `aud=billing-api` trình cho Orders | **Orders từ chối**. | Audience validation. |
| Access token đúng issuer/audience nhưng scope thiếu `orders:read` | **Orders từ chối**, thường 403 nếu token hợp lệ. | Scope authorization. |
| Token đúng issuer/audience/scope nhưng order khác tenant | **Orders từ chối**. | Object/tenant authorization. |
| Multi-issuer cùng `kid=key-1` | Mỗi token chỉ dùng key của issuer đã tin tương ứng. | Namespace cache. |
| Token header chứa `x5u` trỏ metadata IP nội bộ | Không fetch URL tùy ý; không SSRF. | Key source restrictions. |
| JWS header có `crit` không được hiểu | **Từ chối**. | JOSE critical header handling. |
| Opaque token được gửi vào JWT decoder | Không decode/verify như JWS, dùng introspection đúng. | Token format separation. |
| RP nhận ID token `nonce` sai transaction | **Từ chối** dù signature đúng. | OIDC transaction binding. |
| Token ký hợp lệ nhưng `exp` đã qua | **Từ chối**. | Time validation. |
| JWKS trả JSON quá lớn hoặc rất nhiều keys | Giới hạn tải/parse, kiểm tra policy. | DoS resistance. |
| JWK có `alg` khác algorithm allowlist của hệ thống | **Từ chối dùng key/thuật toán không phù hợp**. | Metadata không override policy. |

Ma trận phải được kiểm thử **ở cả OP/AS, OIDC Client và Resource Server**. Unit test chỉ xác nhận “đã decode JWT payload” hoặc “đã tải được JWKS” **chưa chứng minh chữ ký, issuer, audience và object authorization đúng**.

## 20. Tình huống tự luyện

**Tình huống A — Client lấy khóa từ header.** JWT có `jku=https://attacker.example/jwks`. Developer thấy URL hợp lệ HTTPS nên tải key từ đó để verify. Có an toàn không?

**Giải thích:** Không. Header token do caller cung cấp, attacker có thể tự cung cấp khóa và ký token của mình hoặc ép truy cập URL nguy hiểm. Phải dùng JWKS từ metadata/cấu hình **issuer đã tin**.

**Tình huống B — Cùng `kid`, khác tenant.** Issuer A và issuer B đều có key tên `k1`. RS có thể cache `global[k1]` và dùng chung không?

**Giải thích:** Không. `kid` không là định danh toàn cầu. Chọn khóa trong trust domain issuer cụ thể và kiểm tra `iss` chính xác.

**Tình huống C — JWT nhìn hợp lệ.** Một JWT decode được, có `sub=user-123`, `scope=admin`, và `kid` khớp. Có được cấp quyền không?

**Giải thích:** Không. Cần verify chữ ký bằng key đáng tin, kiểm tra issuer, audience, thời hạn, token type và quyền trên object. Header/claim chưa xác minh không tự tạo authority.

**Tình huống D — Rotation làm 401.** OP bắt đầu ký bằng B trước khi công bố B ở JWKS. Client từ chối token mới. Cần sửa gì?

**Giải thích:** Planned rotation nên công bố public key B **trước** khi dùng private key B ký; chờ verifier cache cập nhật, giữ A để token cũ còn xác minh được. Không tắt JWT verification khi gặp 401.

**Tình huống E — Lộ private key.** OP phát hiện khóa ký A bị export trái phép. Có nên giữ A trong JWKS đến hết TTL token?

**Giải thích:** Không theo quy trình planned rotation thông thường. Đây là **compromise**: cần thu hồi A, invalidate cache/verification policy, đánh giá revoke/reissue token và điều tra khẩn cấp.

**Tình huống F — ID token gọi Orders.** Client có ID token `aud=shop-web`, chữ ký đúng từ OP. Orders API tin cùng issuer/JWKS. Có nhận không?

**Giải thích:** Không. ID token dành cho RP. Orders yêu cầu **access token** có audience/orders scope/type và quyền dữ liệu phù hợp.

**Tình huống G — JWKS endpoint tạm 503.** RS đang có cache một khóa còn hợp lệ nhưng gặp unknown `kid` mới. Có thể chọn một key khác để tránh outage?

**Giải thích:** Không. Có thể dùng cache đã tin theo policy cho những token ký bằng key đó, nhưng unknown key không có cơ sở verify nên phải từ chối và retry JWKS một cách có giới hạn.

**Tình huống H — RS256 và HS256.** JWT header đổi thành HS256, code dùng public RSA key làm HMAC secret rồi báo signature hợp lệ. Sai chỗ nào?

**Giải thích:** Lỗi **algorithm confusion**: key type và thuật toán không được ràng buộc. Chỉ chấp nhận thuật toán đã được cấu hình, không dùng RSA public key như symmetric key.

**Tình huống I — Key có `use=enc`.** JWKS chứa RSA public key cho mã hóa và signing key khác. JWT RS256 dùng `kid` của encryption key. Hệ thống nên làm gì?

**Giải thích:** Từ chối nếu key usage không phù hợp, không chọn bất kỳ RSA key nào chỉ vì cùng `kty`.

**Tình huống J — Scope đúng nhưng object sai.** Access token chữ ký đúng, `aud=orders-api`, `scope=orders:read`, nhưng user-123 đọc order của tenant B. Kết quả?

**Giải thích:** Từ chối nếu thiếu quyền liên tenant. JWKS chứng minh token được ký bởi khóa tin cậy, **không** chứng minh người dùng có quyền trên tất cả đơn.

**Tình huống K — Thấy `x5c` là đã tin?** Một JWK từ nguồn không xác minh có `x5c` và certificate chain trông hợp lệ. Có thể dùng để tin issuer không?

**Giải thích:** Không. Phải xác định **source trust** của key, issuer và profile, thêm chain/key binding validation nếu thiết kế yêu cầu. Certificate không cho phép bỏ trust anchor và audience.

**Tình huống L — Access token opaque.** Orders API nhận chuỗi ngẫu nhiên không có dấu chấm, muốn xác minh qua JWKS. Có phù hợp không?

**Giải thích:** Không. Với opaque token, RS sử dụng introspection/tra cứu trạng thái được cấu hình và kiểm tra metadata trả về. JWKS không biến opaque token thành JWT.

## Checklist triển khai JWKS metadata

1. **Chốt trust anchor:** danh sách issuer được phép, exact issuer match; không tự tin `iss`/`jku` từ token chưa xác minh.
2. **Lấy đúng metadata:** OIDC Discovery/provider configuration từ issuer đáng tin, kiểm tra `jwks_uri` và TLS.
3. **Xác định token profile:** OIDC ID token, JWT access token RFC 9068 hoặc opaque token, không dùng chung validation policy.
4. **Chọn key đúng nguồn:** JWKS gắn issuer, `kid` là gợi ý, lọc `kty`/`use`/`key_ops`/`alg` theo chính sách.
5. **Cho phép thuật toán có chủ đích:** RS256/ES256/... theo profile, không chấp nhận `alg=none` hoặc RS/HS confusion.
6. **Bảo vệ key material:** JWKS public-only; private signing/decryption key giữ trong KMS/HSM/keystore; không xuất key bí mật.
7. **Xác minh chữ ký bằng thư viện JOSE/JWT:** không tự triển khai crypto hoặc chỉ decode payload.
8. **Kiểm tra ID token theo OIDC:** issuer, audience là Client, exp/iat, azp, nonce/auth_time/hash khi áp dụng.
9. **Kiểm tra JWT access token theo RS:** issuer, audience API, type, exp/nbf, scope, sender proof nếu cần và object/tenant authorization.
10. **Quản lý key rotation:** publish-new-before-sign, giữ old public key đủ thời gian planned overlap, dừng old signing và gỡ key an toàn.
11. **Xây cache an toàn:** TTL/ETag nếu có, rate-limited unknown `kid` refresh, không tải JWKS mỗi request, fail closed.
12. **Sẵn sàng xử lý compromise:** revoke signing key, purge cache, rà soát/revoke/reissue token, theo dõi verifier vẫn tin key cũ.
13. **Chống URL/key injection:** không follow `jku`/`x5u` ngoài policy, chống SSRF, giới hạn redirect/size/time.
14. **Cô lập multi-issuer/multi-tenant:** cache và policy theo issuer, chống authorization server mix-up và cross-tenant token acceptance.
15. **Kiểm thử trường hợp thất bại:** invalid signature, expired token, bad issuer/audience, none/HS confusion, duplicate/unknown `kid`, rotation, JWKS outage, private key leak, token substitution và BOLA.

## Ghi nhớ

**JWKS metadata không phải một cơ chế cấp quyền: đó là phương tiện công bố và tìm public keys của OpenID Provider/Authorization Server để xác minh chữ ký token.** Ứng dụng bắt đầu từ **trusted issuer**, lấy **OIDC Discovery metadata**, ràng buộc **`jwks_uri`** với issuer, rồi chọn đúng JWK theo `kid`, thuật toán, key type và key usage trước khi kiểm tra JWS signature. **`kid` không phải bí mật hay danh tính toàn cầu, còn `jku`/`x5u` từ token không được tự quyết định nguồn khóa đáng tin.** Key rotation đòi cache/TTL overlap và quy trình khẩn cấp khi lộ private key. Dù signature ID token/JWT access token hợp lệ, bên nhận vẫn phải kiểm tra **issuer, audience, token type, thời hạn, nonce/claims tương ứng và quyền trên từng dữ liệu**. Với **opaque token**, dùng introspection thay vì JWKS. Bảo vệ private key, không fail-open khi JWKS lỗi và tách ranh giới OP/RP/Resource Server là nền tảng của xác minh token an toàn.

### Tài liệu tham khảo

- [OpenID Connect Discovery 1.0 — Provider Configuration và jwks_uri](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0 — ID Token và validation](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OpenID Connect / OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
