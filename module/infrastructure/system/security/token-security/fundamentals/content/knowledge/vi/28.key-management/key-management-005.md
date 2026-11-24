# JWKS và public key distribution

Một **Resource Server** nhận JWT access token do Authorization Server phát hành. JWT có chữ ký `RS256`, nhưng Resource Server không giữ private key của Authorization Server. Vậy làm thế nào API có thể kiểm chữ ký mà **không phải chia sẻ khóa ký bí mật** cho hàng chục dịch vụ?

Câu trả lời là **public key distribution**: Authorization Server giữ **private signing key** trong ranh giới bảo mật của mình, còn công bố các **public verification keys** qua một nguồn đáng tin, thường là **JSON Web Key Set (JWKS)**. Resource Server lấy public key, xác định đúng khóa được phép dùng để kiểm chữ ký, rồi kiểm tiếp **issuer, audience, thời hạn, token type, scope và quyền trên tài nguyên**.

Nhưng “có JWKS” không đồng nghĩa “JWT nào có chữ ký khớp một khóa công khai cũng được chấp nhận”. Nếu Resource Server tải khóa từ URL do token tự khai, dùng nhầm khóa của issuer khác hoặc tin mọi `kid`/thuật toán do attacker chọn, việc phân phối public key có thể biến thành **đường bỏ qua ranh giới tin cậy**.

**Nguyên tắc cốt lõi:** **public key có thể được phân phối rộng rãi; quyền được tin public key phải đến từ cấu hình issuer/Authorization Server đáng tin, thuật toán được phép và chính sách key lifecycle.** JWKS là **cơ chế biểu diễn và phân phối khóa**, không phải bằng chứng độc lập rằng một khóa thuộc về issuer nào hoặc rằng token có đủ quyền.

Bài thuộc chương **Key management** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết nối key management với mô hình tin cậy và vòng đời JWT, opaque token, access token, refresh token, OAuth 2.0/OIDC, phát hành và kiểm claims, scope/audience, lưu trữ, thu hồi và ngăn token bị đánh cắp/phát lại.

Sau bài học, bạn có thể đọc JWKS, cấu hình trust chain từ issuer đến public key, triển khai xác minh JWT đúng cách, thiết kế caching và key rotation, phân biệt thu hồi token với thu hồi niềm tin vào khóa, và kiểm thử nhiều issuer, `kid` lạ, sự cố mạng, sai thuật toán và lộ khóa ký.

## 1. Bài toán phân phối khóa công khai

Với chữ ký số bất đối xứng, Authorization Server có một **cặp khóa**:

- **Private signing key:** chỉ bên có quyền ký được sử dụng; phải bảo vệ trong KMS/HSM/secret management phù hợp.
- **Public verification key:** Resource Server và các verifier được phép nhận để kiểm chữ ký; không cho phép tạo chữ ký mới thay mặt issuer.

~~~mermaid
flowchart LR
    AS["Authorization Server\nprivate signing key"] -->|Ký JWS| JWT["JWT access token"]
    AS -->|Công bố public keys| JWKS["Trusted JWKS endpoint"]
    JWT -->|Bearer token| RS["Resource Server"]
    JWKS -->|HTTPS + cache, đúng issuer| RS
    RS --> V{"Verify signature + claims"}
    V -->|Đạt| A["Policy/scope/resource checks"]
    V -->|Không đạt| D["Reject"]
~~~

| Thành phần | Có được phân phối cho Resource Server? | Lý do |
|---|---|---|
| **RSA/EC/OKP public key** dùng để verify JWS | **Có**, qua JWKS/config đáng tin | Dùng kiểm chữ ký, không ký token |
| **Private signing key** | **Không** | Lộ khóa đồng nghĩa bên khác có thể ký token giả |
| **Symmetric HMAC secret** cho HS256 | **Không được công bố** qua public JWKS | Bên biết secret có thể tạo MAC hợp lệ |
| **JWT đã ký** | Có thể gửi cho client/RS theo flow | Là credential, không phải public key |
| **Opaque access token** | Không phân phối như public key | RS thường cần introspection/nguồn trạng thái |
| **Refresh token** | **Không** | Credential nhạy cảm dùng tại token endpoint |

Public key có thể xuất hiện trong certificate hoặc JWKS mà không phải secret. Nhưng **chính việc chọn đúng public key để tin** mới là bước quan trọng. Một kẻ tấn công cũng có thể tự tạo cặp khóa và đăng public key của họ: Resource Server **không được tin khóa đó** chỉ vì tải qua HTTPS.

## 2. JWK, JWKS, JWS và JWT khác nhau thế nào?

| Khái niệm | Vai trò | Chuẩn liên quan |
|---|---|---|
| **JWK — JSON Web Key** | Định dạng JSON biểu diễn một khóa và metadata | RFC 7517 |
| **JWKS — JSON Web Key Set** | Đối tượng JSON chứa mảng `keys` các JWK | RFC 7517 |
| **JWS — JSON Web Signature** | Cơ chế ký/MAC và kiểm tính toàn vẹn nội dung | RFC 7515 |
| **JWA — JSON Web Algorithms** | Định danh thuật toán và biểu diễn khóa | RFC 7518 |
| **JWT — JSON Web Token** | Cấu trúc claims có thể được bảo vệ bằng JWS/JWE theo profile | RFC 7519 |
| **JWE — JSON Web Encryption** | Cơ chế mã hóa nội dung | RFC 7516 |
| **OIDC Discovery/AS metadata** | Cách xác định issuer, endpoint và `jwks_uri` theo cấu hình được tin | OIDC Discovery / RFC 8414 |

**JWKS không phải danh sách JWT**, cũng không phải token introspection endpoint. Đó là **tập khóa**. Một JWT có thể chứa JOSE header với `kid` để gợi ý chọn khóa từ tập này.

### Ví dụ JWKS mang hai public keys

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "sig-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-rsa-modulus>",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "kid": "sig-ec-02",
      "use": "sig",
      "alg": "ES256",
      "crv": "P-256",
      "x": "<base64url-x-coordinate>",
      "y": "<base64url-y-coordinate>"
    }
  ]
}
~~~

Các giá trị trong dấu ngoặc nhọn là **placeholder minh họa**, không tạo ra JWK hợp lệ để xác minh thật. Một JWKS thực tế chỉ chứa giá trị key material được mã hóa đúng định dạng, đúng chiều dài/tham số thuật toán.

### Vì sao có nhiều khóa?

AS có thể công bố **khóa cũ và khóa mới** trong giai đoạn rotation, hoặc hỗ trợ **nhiều thuật toán/loại khóa** cho những nhóm token khác nhau. Điều đó **không có nghĩa mọi public key trong JWKS được phép xác minh mọi JWT**. RS phải lọc theo **issuer, thuật toán/key type, mục đích, token profile và `kid`** trước khi chọn khóa.

## 3. Cấu trúc một JWK: từng trường có nghĩa gì?

| Field | Ý nghĩa | Lưu ý |
|---|---|---|
| `kty` | Loại khóa: `RSA`, `EC`, `OKP`, `oct` | Public JWKS không được tiết lộ khóa đối xứng `oct` |
| `kid` | Key ID để hỗ trợ chọn khóa | Identifier, **không phải chứng cứ khóa đáng tin** |
| `use` | Mục đích: thường `sig` (ký) hoặc `enc` (mã hóa) | Không dùng khóa mã hóa để xác minh chữ ký ngoài contract |
| `key_ops` | Các thao tác khóa được công bố, ví dụ `verify` | Nếu có, phải nhất quán với mục đích và policy |
| `alg` | Thuật toán dự kiến dùng với khóa, ví dụ `RS256` | **Không được để field này tự thay policy alg allowlist** |
| `n`, `e` | RSA modulus/exponent | Giá trị public, Base64URL theo JWK |
| `crv`, `x`, `y` | Elliptic curve và tọa độ public key | Phải kiểm curve và key validity |
| `x` với `kty=OKP` | Public key cho một số OKP curves | Chỉ dùng với thuật toán/provider hỗ trợ rõ |
| `x5c` | Chuỗi certificate X.509 được biểu diễn trong JWK | **Không tự tạo trust** nếu chưa kiểm certificate/profile phù hợp |
| `x5t`, `x5t#S256` | Thumbprint của certificate | Không thay kiểm định danh issuer/trust policy |
| `d`, `p`, `q` ... | Tham số private key ở những loại JWK | **Tuyệt đối không công bố** trong public signing JWKS |
| `k` với `kty=oct` | Secret đối xứng | **Tuyệt đối không công bố** tại public `jwks_uri` |

**Không nên coi mọi field JWK là bắt buộc.** Một số field là metadata tùy chọn và có thể bị lược bỏ; verifier cần dựa vào contract, chuẩn khóa, thuật toán và issuer policy.

### Ví dụ khóa RSA dùng công khai

~~~json
{
  "kty": "RSA",
  "kid": "issuer-main-key-03",
  "use": "sig",
  "alg": "RS256",
  "n": "<public-modulus-base64url>",
  "e": "AQAB"
}
~~~

**Không được thêm `d`** (RSA private exponent) hoặc các private factors vào response này. Nếu serializer xuất `RSAKey` chứa private fields vì dùng sai loại object/method, endpoint JWKS có thể làm lộ private signing key ngay lập tức.

## 4. Phân phối public key không phải phân phối private key

Lý tưởng, khóa ký do **KMS/HSM** quản lý và chỉ cho thành phần phát hành token quyền **sign**. Thành phần publish JWKS chỉ xuất **public components** hoặc certificate public. Resource Server nhận quyền **verify**, không nhận quyền ký.

~~~text
Key generation / custody:
    Trusted KMS / HSM hoặc key manager có kiểm soát
        |
        +-- Private key: sign operation (AS only)
        |
        +-- Public key: export/distribute as JWK
                    |
                    +-- JWKS endpoint HTTPS
                    +-- Resource Server key cache
                    +-- Trusted verifier
~~~

### Lỗi nghiêm trọng

~~~json
{
  "keys": [
    {
      "kty": "oct",
      "kid": "hs256-production",
      "alg": "HS256",
      "k": "<symmetric-secret-base64url>"
    }
  ]
}
~~~

Đây là **ví dụ điều cấm** với một **JWKS công khai**. JWK có thể biểu diễn khóa đối xứng trong môi trường bảo mật thích hợp, nhưng **không được xuất bí mật `k` lên endpoint công khai**. Ai biết khóa HMAC có thể tự tạo chữ ký MAC hợp lệ.

Với RSA/EC/OKP cũng cần kiểm **private fields** không bị serialize, không xuất private key thành PEM, không nhúng secret trong `x5c` hay JSON metadata khác. **Public JWKS phải là cấu trúc được whitelist cụ thể**, không đơn giản serialize toàn bộ object khóa trong memory.

## 5. Chuỗi tin cậy: issuer → metadata → jwks_uri → key

Khi Resource Server nhận JWT, nguồn xác thực **JWKS URL** không được đến từ tham số do client hoặc JWT chưa xác minh tự khai. Một mô hình tin cậy đúng:

~~~mermaid
flowchart TD
    C["RS config: trusted issuer\nhttps://auth.example.org"] --> M["Trusted metadata / discovery"]
    M --> U["jwks_uri\nhttps://auth.example.org/.well-known/jwks.json"]
    U --> T["HTTPS/TLS + host/redirect policy"]
    T --> J["Parse JWKS, validate key structure"]
    J --> K["Select permitted kid/kty/alg/use"]
    K --> S["Verify JWS signature"]
    S --> P["Validate iss, aud, exp, nbf, token type, scope"]
    P --> A["Resource Server authorization"]
~~~

**Trust anchor** là cấu hình issuer/AS đã được triển khai, không phải bất kỳ `iss` mà attacker viết vào payload JWT.

Ví dụ metadata minh họa:

~~~json
{
  "issuer": "https://auth.example.org",
  "authorization_endpoint": "https://auth.example.org/oauth2/authorize",
  "token_endpoint": "https://auth.example.org/oauth2/token",
  "jwks_uri": "https://auth.example.org/.well-known/jwks.json",
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

**Lưu ý:** `id_token_signing_alg_values_supported` thuộc bối cảnh OIDC provider metadata; không được tự suy mọi access token cũng dùng đúng thuật toán ấy. Với API, thuật toán/profile access token phải được cấu hình theo **hợp đồng AS–RS**, ví dụ RFC 9068 khi áp dụng.

Resource Server:

1. Chỉ chấp nhận **issuer đã được đăng ký**.
2. Dùng đúng discovery/metadata profile và xác minh `issuer` trả về đúng expected issuer.
3. Đọc `jwks_uri` đã được cho phép theo policy; TLS server authentication phải thành công.
4. Không cho URL JWKS tự ý chuyển sang host/IP/port nhạy cảm qua redirect không được phê duyệt.
5. Lấy và parse tập khóa có giới hạn kích thước, số lượng keys, loại key và cấu trúc.
6. Chọn khóa được tin theo issuer và thuật toán.
7. **Chỉ sau khi verify signature**, mới dựa trên claims của token để quyết định quyền.

**Một JWT có `iss` đúng trong payload chưa xác minh không chứng minh nguồn phát hành.** Nó chỉ trở thành claim đáng tin sau signature verification với key đã gắn đúng issuer, rồi kiểm issuer theo policy.

## 6. Hai loại cấu hình: discovery và JWKS URL cố định

**Phương án A — issuer discovery có kiểm soát:** RS được cấu hình một issuer cố định; client thư viện truy metadata, xác minh issuer và lấy `jwks_uri`. Phù hợp khi AS cung cấp OIDC/OAuth metadata đúng chuẩn và môi trường cho phép HTTPS discovery.

**Phương án B — JWKS URL pinned trong config:** RS có issuer và `jwks_uri` được cấu hình theo deployment; không cần discovery runtime nếu hợp đồng đã xác định. Điều này có thể giảm phụ thuộc metadata discovery nhưng cần quy trình cập nhật endpoint và giám sát.

| Tiêu chí | Issuer discovery | Pinned JWKS URL |
|---|---|---|
| Nguồn trust | Issuer cố định + metadata được xác minh | Issuer và URL do deployment kiểm soát |
| Thay đổi URL JWKS | Có thể cập nhật qua metadata đáng tin theo policy | Cần cập nhật config/rollout |
| Nguy cơ nổi bật | Không verify metadata issuer, follow arbitrary redirect | Pin sai môi trường/issuer hoặc URL stale |
| Caching | Metadata và JWKS đều cần cache hợp lý | JWKS vẫn cần cache hợp lý |
| Khi phù hợp | OP/AS chuẩn, discovery vận hành ổn | Hệ thống nội bộ cần quy tắc egress chặt |

**Không có phương án nào cho phép tin URL từ `jku`, `x5u`, request header hoặc domain do client tự gửi.** Hai phương án khác nhau ở cách phân phối **cấu hình đã được phê duyệt**, không khác bản chất xác minh chữ ký.

## 7. `kid`: key identifier, không phải authority

JOSE header của một JWS có thể có:

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "sig-2026-11"
}
~~~

`kid` giúp verifier tìm **khóa ứng viên** trong JWKS đã được tin; nó **không nói ai sở hữu khóa** và không mang quyền “hãy lấy key bất kỳ”.

Các yêu cầu:

- Dùng `kid` để lookup trong **key set thuộc issuer đã trusted**.
- `kid` cần được quản lý tránh trùng/nhầm trong cùng tập và thời điểm có hiệu lực.
- Nếu nhiều khóa có cùng `kid`, không tùy tiện chọn một key ngẫu nhiên; xử lý theo policy an toàn hoặc từ chối do ambiguous key.
- Chỉ kiểm một khóa có `kty`, thuật toán, `use`/`key_ops` và trạng thái được phép.
- `kid` thiếu hoặc lạ không phải lý do để tải một URL bất kỳ từ token header.
- `kid` là dữ liệu đầu vào chưa xác minh: cần giới hạn độ dài, charset/path handling, logging và tránh injection.

**Không dùng `kid` làm tên file rồi nối thẳng vào path** hay dùng làm SQL string:

~~~text
Sai:
  readFile("/keys/" + jwt.header.kid + ".pem")
  query("SELECT key FROM jwks WHERE kid='" + jwt.header.kid + "'")

Đúng về nguyên tắc:
  lookup một key ID đã giới hạn định dạng trong
  in-memory trusted key registry hoặc parameterized query.
~~~

Nếu attacker gửi `kid=../../secrets/private.pem` hoặc `kid` dài hàng megabyte, parser phải chặn ở boundary; **JWKS không được biến thành path traversal, injection hoặc memory amplification primitive**.

## 8. `alg`, `kty` và key purpose: chống algorithm confusion

Một JWT header có thể viết `alg=HS256`, `RS256`, `ES256`, `PS256` hoặc các giá trị khác. **Attacker kiểm header trước khi verify chữ ký**, nên verifier phải có **allowlist thuật toán và binding tới key/issuer/token profile**.

~~~text
Trusted RS policy:
  issuer = https://auth.example.org
  access_token_algorithms = [RS256]
  expected_token_type = at+jwt
  accepted_key_type = RSA

Untrusted header:
  alg = HS256
  kid = sig-2026-11

Decision:
  Reject before allowing an attacker-selected HMAC verification path.
~~~

### Thuật toán `none`

Một token `alg=none` có thể là cấu trúc JOSE không được ký theo một số profile, nhưng **Resource Server yêu cầu signed access token không được chấp nhận nó**. Không bật `none` chỉ để “tương thích” với một JWT có payload hợp lệ.

### Không dùng public RSA key làm HMAC secret

Lỗi lịch sử **RS256/HS256 confusion** xảy ra khi verifier tin `alg` từ token để chuyển sang HMAC và dùng RSA public key (vốn công khai) làm shared secret. Attacker có thể biết public key và tạo MAC nếu hệ thống mắc lỗi nghiêm trọng này.

**Biện pháp:** thư viện JOSE đáng tin, allowlist `alg` theo issuer/client/token purpose, kiểm `kty` và key usage, không fallback qua thuật toán khác khi verify thất bại.

### `use` và `key_ops`

JWK cho signing thường có `use=sig`; nếu `key_ops` hiện diện có thể chỉ rõ `verify`. Không đưa encryption key vào signature verification chỉ vì `kid` khớp. Các field này **giúp diễn đạt mục đích nhưng không thay thế policy local**; thiếu `use` có thể được xử lý tùy contract, còn giá trị xung đột nên bị từ chối.

## 9. JWT access token: verify chữ ký chỉ là bước đầu

Khi nhận một JWT access token qua `Authorization: Bearer`, RS thường cần:

~~~mermaid
flowchart TD
    A["Bearer JWT"] --> B["Kiểm cấu trúc/kích thước/token profile"]
    B --> C["Trusted issuer config + JWKS cache"]
    C --> D["Select key và algorithm được phép"]
    D --> E{"JWS signature valid?"}
    E -->|Không| X["Reject"]
    E -->|Có| F{"iss/aud/exp/nbf/type hợp lệ?"}
    F -->|Không| X
    F -->|Có| G{"Scope và client/grant policy hợp lệ?"}
    G -->|Không| X
    G -->|Có| H{"Tenant/object-level access hợp lệ?"}
    H -->|Không| X
    H -->|Có| I["Allow request"]
~~~

Ví dụ payload **minh họa, chưa có chữ ký**:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1795400000,
  "exp": 1795400900,
  "jti": "at-example-003"
}
~~~

| Kiểm tra | Nếu bỏ qua có thể xảy ra |
|---|---|
| **Signature** | Chấp nhận token giả không do AS ký |
| **Issuer (`iss`)** | Chấp nhận token ký bởi AS khác |
| **Audience (`aud`)** | Dùng token của Payments API tại Orders API |
| **Expiration (`exp`) / `nbf`** | Dùng token hết hạn hoặc chưa đến thời điểm hiệu lực |
| **Token type/purpose** | Chấp nhận ID token/refresh token thay access token |
| **Scope** | Cho phép chức năng ngoài quyền đã cấp |
| **Tenant/object authorization** | Đọc/sửa đối tượng thuộc user/tenant khác |
| **Revocation/current policy** | Tiếp tục chấp nhận token sau khi grant hoặc user bị vô hiệu hóa nếu cần revoke sớm |

**Public key trong JWKS chỉ giải quyết bước signature verification.** JWKS không phải database quyền, không chứa thông tin token đã bị thu hồi và không thay bộ lọc authorization của Resource Server.

## 10. Quy trình phát hành JWT và lấy JWKS lần đầu

Giả sử:

~~~text
Authorization Server issuer:
  https://auth.example.org

JWKS:
  https://auth.example.org/.well-known/jwks.json

Resource Server:
  orders-api

AS signing key:
  kid=sig-a, algorithm=RS256
~~~

Luồng thông thường:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Orders API
    participant J as AS JWKS Endpoint
    C->>AS: OAuth authorization/token request hợp lệ
    AS->>AS: Ký JWT bằng private key sig-a
    AS-->>C: Access token có header kid=sig-a
    C->>RS: Authorization: Bearer JWT
    RS->>RS: Xác định issuer từ trusted configuration
    RS->>J: GET JWKS qua HTTPS khi cache miss
    J-->>RS: Public JWK sig-a
    RS->>RS: Kiểm kid/kty/alg/use + verify JWS
    RS->>RS: Kiểm iss/aud/exp/type/scope/policy
    RS-->>C: API response nếu được phép
~~~

**Không cần gọi JWKS endpoint mỗi request.** Public keys thường được cache vì xác minh JWT không phụ thuộc một network call ở từng request. Cũng không nên **tải public key từ mỗi JWT**: verifier sử dụng **tập khóa đã được tin và cache có kiểm soát**.

### HTTP JWKS response minh họa

~~~http
GET /.well-known/jwks.json HTTP/1.1
Host: auth.example.org
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300
ETag: "jwks-revision-17"

{
  "keys": [
    {
      "kty": "RSA",
      "kid": "sig-a",
      "use": "sig",
      "alg": "RS256",
      "n": "<rsa-public-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Các header cache và URI trong ví dụ **chỉ là minh họa policy**. `max-age=300` nghĩa là HTTP representation có thể được cache **5 phút** theo chỉ thị; nó **không phải bảo đảm tối đa độ trễ xử lý khi private key bị compromise**. Hệ thống phải cân bằng hiệu năng, rotation, emergency invalidation và độ mới của trust state.

## 11. Caching JWKS khác caching trạng thái active của token

**JWKS cache** giữ **public verification keys**. **Introspection cache** có thể giữ kết quả **active=true** của một token cụ thể. Hai cache có ý nghĩa và rủi ro rất khác nhau.

| Thuộc tính | JWKS cache | Introspection cache |
|---|---|---|
| Dữ liệu | Public keys và metadata | Trạng thái/claims của token |
| Đơn vị thường cache | Issuer/JWKS URL + key set revision | Token fingerprint + issuer/RS/caller context |
| Khi token bị revoke | Khóa có thể vẫn hợp lệ | `active` có thể đổi thành false |
| Khi key rotate bình thường | Có thể cần fetch key mới theo `kid` | Không tự cần fetch JWKS |
| Khi signing key bị compromise | Phải xử lý **trust vào key** | Có thể phải chặn tokens dựa vào key/issuer theo policy |
| TTL | Theo HTTP headers và key-lifecycle policy | Theo revocation freshness policy, không vượt token `exp` |
| Có thể cache lâu? | Có thể, nếu đã xét rotation và emergency behavior | `active=true` cache quá lâu làm revoke chậm |

**Không dùng token `exp` làm TTL của JWKS.** Public key có thể phải phục vụ xác minh nhiều token có thời hạn khác nhau. Ngược lại, **không lấy max-age của JWKS làm TTL của một access token**.

### Cache key JWKS

Thường là **trusted issuer identity và JWKS endpoint/config revision**. Không dùng `kid` duy nhất trên toàn hệ thống vì **hai issuer có thể chọn cùng `kid`** nhưng khóa khác. Nếu thư viện cache từng JWK theo `kid`, phải bảo đảm **namespace issuer** và chính sách loại token/thuật toán.

### HTTP conditional fetch

Nếu JWKS endpoint hỗ trợ **ETag**:

~~~http
GET /.well-known/jwks.json HTTP/1.1
Host: auth.example.org
If-None-Match: "jwks-revision-17"
~~~

~~~http
HTTP/1.1 304 Not Modified
ETag: "jwks-revision-17"
Cache-Control: public, max-age=300
~~~

Verifier có thể giữ representation đã xác minh/cached theo HTTP policy. **HTTP 304 không có nghĩa “key bị thu hồi rồi trở lại hợp lệ”**; nó chỉ báo representation chưa đổi theo cache validator. Hệ thống phải có cơ chế **explicit distrust** khi key compromise hoặc issuer policy yêu cầu ngừng sử dụng key.

## 12. Key rotation bình thường: publish trước, ký sau

Một rotation chuẩn phải tránh tình huống **AS bắt đầu ký bằng key B trước khi Resource Servers biết public key B**.

~~~text
Phase 0:
  JWKS = [A]
  Signing = A

Phase 1 — Prepublish:
  JWKS = [A, B]
  Signing = A
  Đợi tối đa thời gian cache/distribution cần thiết.

Phase 2 — Switch signing:
  JWKS = [A, B]
  Signing = B
  A vẫn dùng để verify JWT cũ.

Phase 3 — Retire A:
  Đợi token do A ký hết hạn + clock leeway + propagation.
  JWKS = [B]
  Signing = B
~~~

~~~mermaid
gantt
    title Rotation ký JWT từ key A sang key B (minh họa)
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    Key A ký token         :a1, 2026-11-01, 15d
    Key A còn công bố để verify :a2, 2026-11-01, 25d
    Publish public key B   :b1, 2026-11-12, 14d
    Key B bắt đầu ký       :b2, 2026-11-16, 10d
~~~

Sơ đồ chỉ thể hiện một **timeline minh họa**, không có ý nghĩa đặt ngày/TTL tiêu chuẩn cho mọi hệ thống.

### Các mốc cần tính

1. **Generate B:** tạo key bằng CSPRNG/KMS/HSM, gắn mục đích và thuật toán.
2. **Publish B:** công bố **public JWK** với `kid` mới, giữ A.
3. **Propagation:** đợi ít nhất theo **thực tế cache TTL/refresh lag/cold start** và rollout RS; kiểm các RS thật có thể lấy B.
4. **Switch signer:** AS ký token mới bằng B. Tránh một cụm AS có nodes phát token bằng A/B ngoài chính sách mà JWKS không phản ánh.
5. **Overlap verification:** giữ A trong JWKS đủ lâu để các token **được ký hợp lệ bằng A** còn trong thời gian cho phép có thể được kiểm.
6. **Retire A:** khi các token cần thiết đã hết `exp` và không còn leeway/cached validators cần A, bỏ A theo policy; vô hiệu quyền ký A.
7. **Observe:** theo dõi token failures do unknown `kid`, số JWT ký bằng A/B, lỗi fetch và độ trễ cache.

### Khoảng overlap cần bao lâu?

Một phương pháp là dùng **max lifetime của mọi token có thể được ký bằng A**, cộng **clock skew allowance** và **distribution/cache delays** có liên quan. Không chỉ xét access token nếu cùng key ký **ID tokens, logout tokens hoặc JWT assertions** với vòng đời khác.

**Không bắt buộc dùng một signing key cho mọi loại token.** Key separation theo token purpose/issuer/risk có thể làm rotation và ứng cứu dễ kiểm soát hơn.

## 13. Khóa bị xâm phạm: emergency rotation khác planned rotation

Khi **private signing key A bị lộ**, attacker có thể tạo JWT có chữ ký hợp lệ của A. Khi đó nguyên tắc planned rotation **“giữ A đủ lâu để token cũ hết hạn”** có thể nguy hiểm.

~~~text
Planned rotation:
  ưu tiên tương thích với token đã phát hợp lệ
  giữ A để verify trong overlap đã kiểm soát.

Compromise response:
  ưu tiên khôi phục tính tin cậy
  dừng ký A, loại A khỏi trusted verifier set
  hoặc áp emergency deny policy ngay khi có thể.
~~~

Các bước phản ứng theo mức độ sự cố:

1. **Xác minh và khoanh vùng:** key nào/issuer nào/token types nào bị ảnh hưởng, thời điểm nghi lộ, dấu hiệu giả mạo.
2. **Ngừng sử dụng private key bị xâm phạm:** vô hiệu key signing ở KMS/HSM/AS; khóa quyền truy cập và audit.
3. **Tạo và công bố public key thay thế** qua trusted JWKS/metadata.
4. **Phân phối thông tin distrust** tới Resource Servers: cache purge, key denylist, config update hoặc phương án cô lập.
5. **Đánh giá JWT đã phát:** chấp nhận việc các token cũ do A ký **có thể phải bị từ chối** và người dùng/client phải xác thực lại.
6. **Thu hồi hoặc vô hiệu grant/refresh tokens liên quan** nếu threat model yêu cầu, nhưng tránh giả định revoke RT chữa được việc kẻ tấn công có private signing key.
7. **Kiểm chứng end-to-end:** cả node có cache cũ, gateway, third-party RS và môi trường DR đều không còn tin A theo yêu cầu.
8. **Giám sát và truyền thông:** reason codes, time-to-distrust, replay và incident handling, không đăng raw key/token.

**Chỉ bỏ A khỏi JWKS endpoint không chắc đủ.** Resource Server có thể **cache JWKS cũ**, giữ public key A và tiếp tục verify token giả. Emergency response phải có **cơ chế đẩy distrust hoặc giới hạn tuổi cache**, cùng khả năng xử lý outage mà không fail open.

### Thu hồi một token và thu hồi một signing key khác nhau

| Hành động | Tác động | Giới hạn |
|---|---|---|
| Revoke một refresh token (RFC 7009) | Chặn dùng RT đó theo AS policy | Không tự khiến JWT giả ký bằng key đã lộ bị chặn |
| Revoke access token theo `jti`/denylist | Chặn token cụ thể | Attacker có key có thể tạo `jti` mới |
| Retire key A | Chấm dứt phát token mới bằng A | RS cache cũ có thể vẫn tin A |
| Distrust public key A tại mọi verifier | Chặn các JWT mang chữ ký A | Có thể làm token hợp lệ cũ mất hiệu lực, cần xử lý availability |
| Thay issuer trust/metadata toàn bộ | Đáp ứng compromise phạm vi rộng | Ảnh hưởng lớn tới mọi client/RS |

**Không tuyên bố “đã thay private key trên AS” là xử lý xong compromise** trước khi xác minh các verifier đã loại bỏ key cũ khỏi trust set.

## 14. Unknown `kid`: refetch có kiểm soát, không tạo DoS

Khi RS nhận JWT mang `kid=sig-new` mà cache chỉ có `sig-old`, có thể do AS vừa rotate. Một hành vi hợp lý là **refresh JWKS đã được tin một cách có kiểm soát** rồi thử lại một lần. Nhưng attacker có thể gửi vô hạn `kid` ngẫu nhiên:

~~~text
kid=attacker-000001
kid=attacker-000002
kid=attacker-000003
...
~~~

Nếu RS gọi JWKS endpoint **mỗi lần gặp unknown `kid`**, attacker có thể làm bùng phát HTTP requests, cạn connection pool và khiến AS metadata service quá tải.

### Phòng vệ

- Giới hạn độ dài, định dạng và cấu trúc JOSE header.
- Chỉ refresh từ **pinned trusted JWKS endpoint**, không đổi URL theo `kid`.
- **Rate limit** JWKS refresh cho mỗi issuer (minimum interval/backoff).
- **Single-flight**: gộp nhiều request refresh đồng thời, không gửi hàng trăm GET cùng lúc.
- Có thể **negative-cache unknown key IDs** trong thời gian ngắn, nhưng phải xét planned rotation để tránh chặn key mới quá lâu.
- Không coi unknown `kid` là tín hiệu cho phép fallback sang **một public key bất kỳ**.
- Nếu đã refresh hợp lệ mà vẫn không tìm được key, **từ chối JWT**.

~~~mermaid
flowchart TD
    A["JWT header kid không có trong cached JWKS"] --> B{"Trusted JWKS refresh được phép theo rate limit?"}
    B -->|Không| X["Reject / bounded retry policy"]
    B -->|Có| C["Single-flight fetch JWKS từ URL đã pin"]
    C --> D{"HTTPS / schema / key set hợp lệ?"}
    D -->|Không| X
    D -->|Có| E{"Key mới có kid/alg/kty hợp lệ?"}
    E -->|Không| X
    E -->|Có| F["Verify JWS signature + validate claims"]
    F --> G{"Full token validation đạt?"}
    G -->|Không| X
    G -->|Có| H["Allow theo resource policy"]
~~~

**Unknown `kid` không chứng minh token giả**; nó có thể phản ánh rotation mới. Nhưng **không kiểm chứng được key thì phải từ chối**, thay vì vô hiệu hóa signature verification.

## 15. JWKS endpoint unavailable: bảo đảm availability mà không fail open

Khi JWKS service lỗi, hai tình huống khác nhau:

| Trạng thái RS | Tùy chọn có thể chấp nhận theo policy | Điều tuyệt đối tránh |
|---|---|---|
| Có cached trusted key chưa vượt hard trust TTL, không bị distrust | Có thể tiếp tục verify JWT với khóa này trong phạm vi policy | Không kéo dài vô hạn sau compromise |
| JWT cần key mới chưa có, JWKS fetch fail | Từ chối hoặc báo dependency failure phù hợp | Không skip chữ ký |
| Cache key đã bị emergency distrust | Phải từ chối JWT dựa vào key đó | Không dùng stale key vì AS down |
| JWKS response malformed/HTTP 5xx | Giữ last-known-good **trong giới hạn được duyệt**, ghi lỗi | Không thay bằng key từ token header |
| Không có trusted key nào | Không thể verify signed token | Không cho qua theo payload decode |

**Last-known-good JWKS cache** có thể cải thiện availability, nhưng phải có **hard upper bound, emergency invalidation và trust policy**. Không nhầm HTTP cache freshness với khả năng thu hồi niềm tin khi key bị lộ.

### Phân loại response API

Một token có chữ ký sai nên bị **từ chối vì credential không hợp lệ**. Khi JWKS dependency chưa khả dụng để kiểm key mới, RS có thể báo **503** thay vì 401 tùy hợp đồng để mô tả sự cố hạ tầng; cả hai trường hợp đều **không thực hiện yêu cầu được bảo vệ**.

**Không trả “success” chỉ vì thư viện đã decode JWT payload**. Decode Base64URL không phải signature verification.

## 16. Bảo vệ HTTP JWKS endpoint và cache

Public JWKS endpoint thường không đòi người đọc xác thực, bởi dữ liệu **public key** được thiết kế để phân phối. Tuy nhiên, độ tin cậy và tính khả dụng của endpoint vẫn là tài sản an ninh.

### Yêu cầu vận hành

1. **HTTPS/TLS** và danh tính server đúng, certificate chain hợp lệ.
2. **Public-only serialization**: kiểm không chứa `d`, `k` hay private factors.
3. **Key set có giới hạn**: kích thước response, số lượng keys, key strength, formats.
4. **Caching phù hợp**: `Cache-Control`, `ETag`/revalidation và hard TTL theo rotation policy.
5. **Availability**: phục vụ nhiều RS, cache/CDN nếu tương thích trust policy và khả năng purge khi khẩn cấp.
6. **Integrity of publication**: pipeline publish keys có quyền hạn/audit, không để một CI job tùy ý đẩy khóa attacker vào JWKS.
7. **Monitoring**: JWKS fetch error rate, ETag/cache hit, unknown `kid`, mismatch issuer, key count, key-age.
8. **Response consistency**: các AS nodes/CDN PoPs phải xuất đủ keys cần thiết trong giai đoạn overlap.
9. **Egress control** ở RS: chỉ được gọi host/port đã phê duyệt.
10. **No silent fallback** sang HTTP, self-signed TLS không tin hoặc metadata endpoint của attacker.

### HTTP headers không phải authorization policy

JWKS có thể dùng `Cache-Control: public` vì chứa public keys. Điều này **không có nghĩa bất kỳ khóa nào trong response cũng được phép ký token**: verifier vẫn cần issuer, key purpose, thuật toán và trạng thái trust.

### Một failure mode với CDN

AS công bố B rồi chuyển signer sang B, nhưng một edge CDN vẫn phục vụ JWKS `[A]` vì cấu hình TTL sai. RS nhận JWT `kid=B` và từ chối, gây outage. Giải pháp: **prepublish, kiểm edge propagation, cache TTL hợp lý, ETag/purge**, cùng metric `unknown_kid`; không “fix” bằng cách tắt kiểm chữ ký.

## 17. Header `jku`, `jwk`, `x5u` và `x5c`: không tự tạo nguồn tin cậy

JOSE header có thể chứa các tham số gợi ý về key:

- **`jku`**: URL tới JWK Set.
- **`jwk`**: JWK được đặt ngay trong JOSE header.
- **`x5u`**: URL tới certificate chain.
- **`x5c`**: Certificate chain đính kèm.
- **`kid`**: ID hỗ trợ chọn khóa.

Một JWT chưa verify là dữ liệu **do caller có thể tự tạo**. Nếu RS làm:

~~~text
if (jwt.header.jku != null):
    keySet = http.get(jwt.header.jku)
else:
    keySet = trustedJwks

verifyWith(keySet)
~~~

thì attacker có thể đưa **public key của chính họ** vào một endpoint HTTPS do họ kiểm soát rồi ký JWT giả bằng private key tương ứng. Phép xác minh chữ ký có thể cho kết quả **đúng về mặt mật mã**, nhưng **sai nguồn tin cậy**.

### Những nguy cơ cụ thể

| Input chưa tin | Nếu sử dụng mù quáng | Cách đúng |
|---|---|---|
| `jku=https://attacker.example/jwks` | Chấp nhận key của attacker | Bỏ qua nếu profile không cho; nếu profile cho thì **ràng buộc URL với trusted issuer/registration** |
| `jku=http://169.254.169.254/...` | SSRF tới metadata service | Egress allowlist, chặn private/link-local, không fetch arbitrary URL |
| `jwk={...attacker-public-key...}` | Tự xác thực token bằng key do chính token mang | Không dùng embedded JWK làm trust anchor |
| `x5u` tùy ý | Tải certificate từ host attacker/SSRF | Trusted URL + certificate/path/purpose validation theo profile |
| `x5c` tự đính kèm | Nhầm certificate có chữ ký là thuộc issuer | Kiểm trust anchors và binding đúng issuer/client |
| `kid` giống một file path | Path traversal/local file inclusion | Lookup ID trong trusted registry, không nối filesystem path |

**HTTPS của `jku` không làm khóa đó đáng tin.** HTTPS chỉ giúp xác thực server của domain được truy cập; nếu domain do attacker sở hữu, attacker hoàn toàn có thể có certificate TLS hợp lệ.

### Khi nào có thể dùng header chứa key?

Một số protocol thực sự dùng `jwk` hoặc certificate trong header cho **proof-of-possession** hoặc client assertion. Khi ấy **trust model của protocol** phải xác định **key được ràng buộc với ai** (chẳng hạn JWK thumbprint hoặc đăng ký client), không thể bê quy tắc “mọi header JWK đều là signing key của issuer” sang JWT access token.

**Không cấm mọi `jwk` trong mọi chuẩn**, nhưng **không lấy nó làm public key của Authorization Server** trừ khi profile và trust binding cho phép rõ ràng.

## 18. `x5c`, certificate chain và JWK thumbprint

Một public key có thể được biểu diễn trực tiếp qua `n/e`, `x/y` hoặc được liên hệ với chứng thư X.509 qua `x5c`. Chứng thư có thể mang thông tin thời hạn, chủ thể và chain, nhưng **không tự chứng minh issuer OAuth đã đăng ký sử dụng nó**.

Ví dụ:

~~~json
{
  "kty": "RSA",
  "kid": "sig-with-cert-01",
  "use": "sig",
  "alg": "RS256",
  "x5c": ["<base64-der-certificate>"],
  "n": "<base64url-rsa-modulus>",
  "e": "AQAB"
}
~~~

**Các giá trị chứng thư/modulus là placeholders.** Nếu có cả JWK public parameters và certificate, implementer cần kiểm **chúng thực sự đại diện cùng public key** theo profile thư viện. Nếu chain validation được yêu cầu, phải kiểm chain và mục đích theo chính sách phù hợp; không chỉ kiểm certificate có parse được.

### JWK thumbprint (RFC 7638) khác `kid`

**JWK thumbprint** tính một digest trên tập field public được chuẩn hóa theo quy tắc chuẩn, ví dụ public RSA `kty`, `n`, `e`; không đơn giản hash JSON nguyên dạng tùy thứ tự field. Một key có thể có:

~~~text
kid = sig-2026-11 (issuer đặt, có thể đổi)
JWK thumbprint = SHA-256 trên canonical required public JWK members
~~~

Thumbprint giúp xác định **đúng key material** trong một số cơ chế, chẳng hạn binding proof-of-possession, nhưng **không chứng minh issuer đã cho phép key này dùng để ký access token**.

**DPoP** có thể dùng JWK trong proof header và liên hệ access token với JWK thumbprint; đó là **key của client/sender**, không phải key của Authorization Server dùng để ký JWT access token. Nhầm hai key sets này có thể tạo lỗi bảo mật nghiêm trọng.

## 19. Nhiều issuer, nhiều tenant: cô lập trust store

Giả sử Orders API chấp nhận token từ hai AS đã được đăng ký:

~~~text
Issuer A:
  https://auth-a.example.org
  jwks_uri=https://auth-a.example.org/keys
  kid=key-1, public key A

Issuer B:
  https://auth-b.example.org
  jwks_uri=https://auth-b.example.org/jwks
  kid=key-1, public key B
~~~

Hai issuer có cùng `kid=key-1` là điều có thể xảy ra. **Không được cache global theo `kid` rồi dùng public key của issuer A để verify token được claim là issuer B.**

### Trust policy đúng theo issuer

~~~text
TrustedIssuerConfig:
  issuerId
  exactExpectedIssuer
  trustedJwksUri
  allowedSigningAlgorithms
  acceptedTokenTypes
  expectedAudiences
  keyCacheNamespace
  securityIncidentControls
~~~

Trong hệ thống multi-tenant, **tenant context** không đồng nghĩa issuer: một AS có thể phục vụ nhiều tenants, hoặc mỗi tenant có AS riêng. Cần cấu hình mapping tenant/issuer được phê duyệt, kiểm claims sau chữ ký và **object-level authorization**; không lấy tenant chưa verify để tự mở URL JWKS bất kỳ.

### Cẩn thận khi chọn issuer từ token chưa verify

Một số thư viện có thể đọc `iss` chưa xác minh để **chọn ứng viên issuer**. Điều này chỉ an toàn khi RS tra trong **allowlist issuer cố định** và sau đó xác minh chữ ký/iss; không tạo client/config mới hoặc fetch metadata từ `iss` tùy ý.

~~~text
Untrusted iss claim:
  "https://attacker.example"

Unsafe:
  discover("https://attacker.example")
  -> trust its keys

Safe:
  if iss not in approvedIssuers: reject
  else select that issuer's trusted decoder
  -> verify signature
  -> validate exact issuer and audience
~~~

Nếu cùng API route cho phép nhiều issuers, **audience và resource policy** vẫn phải đúng. JWT ký hợp lệ bởi AS-B không mặc nhiên được dùng ở resource chỉ chấp nhận AS-A.

## 20. JWKS của OpenID Provider và access token tại Resource Server

OIDC RP dùng public keys của OP để xác minh **ID token** theo OIDC validation rules. Một Resource Server dùng public keys của AS để xác minh **JWT access token** theo access-token profile/hợp đồng.

| Token | Ai thường verify? | Kiểm quan trọng |
|---|---|---|
| **OIDC ID token** | Relying Party/client | `iss`, `aud` = client ID, signature, exp, nonce/azp khi áp dụng, OIDC profile |
| **JWT access token** | Resource Server | `iss`, `aud` = API/resource, exp/nbf, scope, token type, RS policy |
| **Opaque access token** | Resource Server qua AS/introspection hoặc trusted state service | `active`, issuer/audience/scope/type và token policy |
| **Refresh token** | Authorization Server tại token endpoint | Client/grant binding, rotation/reuse/revocation, thời hạn |
| **Back-Channel Logout Token** | OIDC Relying Party | Chữ ký từ OP, type/events, `jti` anti-replay, sid/sub và profile |

**Cùng public key có thể ký nhiều token types**, nhưng verifier vẫn phải thực hiện **token type confusion defense**: chẳng hạn API không được nhận **ID token** như một access token chỉ vì ID token có chữ ký từ đúng issuer.

### RFC 9068: JWT access token profile

Nếu AS/RS sử dụng **RFC 9068**, JWT access token có những quy tắc về JOSE header `typ`, claims và validation. Resource Server phải triển khai **đúng profile** và kiểm **audience/resource**. Đừng chỉ thấy JWKS `RS256` rồi coi tất cả JWT do OP ký đều là access tokens.

### Sender-constrained tokens

**mTLS-bound access token** hoặc **DPoP-bound access token** còn đòi chứng minh client/sender nắm khóa tương ứng. Việc RS xác minh **AS signature bằng JWKS** chỉ xác minh **issuer**; nó **không** thay chứng minh **holder-of-key**. Hệ thống phải kiểm `cnf` và proof/mTLS binding theo profile.

## 21. Java/Spring Security: cấu hình JWKS URI và issuer tin cậy

Trong ứng dụng Spring Security, Resource Server JWT nên dùng **library và framework được duy trì**, không tự parse JWT rồi dùng `Signature.verify` trên một public key lấy từ header.

Một ví dụ cấu hình **Java/Spring Security 6-style**, áp dụng khi AS phát **RS256 JWT access tokens** theo profile đã thống nhất:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;

@Configuration
public class ResourceServerJwtConfig {
    private static final String ISSUER = "https://auth.example.org";
    private static final String JWKS_URI =
            "https://auth.example.org/.well-known/jwks.json";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(JWKS_URI)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Unexpected audience",
                                    null));

        // Ví dụ khi AS phát access token tuân thủ RFC 9068.
        OAuth2TokenValidator<Jwt> accessTokenType = jwt -> {
            Object typ = jwt.getHeaders().get("typ");
            boolean accepted = "at+jwt".equals(typ)
                    || "application/at+jwt".equals(typ);
            return accepted
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Unexpected token type",
                                null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience, accessTokenType));
        return decoder;
    }
}
~~~

**Đây là minh họa cấu hình**, không khẳng định ứng dụng hoàn chỉnh: phiên bản Spring Security/Nimbus có thể khác về API, defaults và xử lý `typ`. Cần compile/test trong project thật, cài đặt `SecurityFilterChain`/resource-server bearer processing và authorization rules theo môi trường.

### Những gì đoạn code thể hiện

- **Pinned JWKS URI**: URL do deployment tin và cấu hình; không lấy từ token.
- **Allowed algorithm RS256**: không để client chọn HS256/`none`.
- **Issuer validation**: expected `iss` được kiểm, không chỉ verify với một key bất kỳ.
- **Audience validation**: token phải dành cho `orders-api`.
- **Access-token type**: ví dụ yêu cầu `at+jwt`/profile phù hợp, giúp tránh ID-token confusion.

### Những gì còn phải triển khai

- `scope`/authorities mapping và **object-level authorization**.
- Token revocation/current user/tenant policy nếu yêu cầu thu hồi sớm.
- Cache TTL, trust refresh, `kid` unknown throttling, emergency distrust theo library/config.
- Server-side HTTP TLS/egress policy và metadata/JWKS endpoint observability.
- JWT profile khác nếu issuer không dùng RFC 9068; không ép `at+jwt` lên một hợp đồng không sử dụng profile ấy mà không xem xét.
- Kiểm `cnf`/DPoP/mTLS sender proof nếu access token là sender-constrained.

**Đừng xây decoder bằng URL trực tiếp từ claim `iss` hoặc `jku` mà không có allowlist.** Trường `jwksUri` phải đến từ trusted deployment context.

## 22. Khi cần xác minh JWT mà không dùng Spring

Với JCA/JCE thuần, một verifier chữ ký số cần hiểu **JOSE signing input và signature encoding**:

~~~text
JWS Compact Serialization:
  BASE64URL(protectedHeader) .
  BASE64URL(payload) .
  BASE64URL(signature)

JWS signing input:
  ASCII(BASE64URL(protectedHeader) + "." + BASE64URL(payload))
~~~

Nếu dùng RSA `RS256`, thư viện phải ánh xạ đúng chữ ký **RSASSA-PKCS1-v1_5 với SHA-256** theo JWS. Với ECDSA, JWS signature encoding **khác encoding DER mà một số JCA APIs mong đợi**; không tự truyền bytes vào `Signature.verify` rồi bỏ qua conversion/profile.

**Không khuyến nghị tự viết JOSE parser/verifier.** Dùng Nimbus JOSE + JWT hoặc thư viện được kiểm tra; JCA `Signature.verify` chỉ là primitive bên trong quy trình còn phải parse, bound header, select trusted key, check alg, validate claims và authorization.

### Chống `kid` collision khi chọn khóa

Trong một JWKS có nhiều key candidates:

~~~text
Candidates = trustedKeys[expectedIssuer]
    .filter(kid == jwtHeader.kid)
    .filter(kty/alg/use phù hợp với RS policy)

if candidates not unambiguous:
    reject

verify signature using selected trusted key
~~~

Đây là **pseudocode**. Một thư viện có thể thử nhiều keys hợp lệ trong cùng trust set, nhưng ứng dụng không được biến key ambiguity thành cơ chế **“thử key của mọi issuer cho đến khi thành công”**.

### Không dựa vào thứ tự JWK trong `keys`

Mảng `keys` của JWKS không phải danh sách “khóa đầu tiên là key đang ký”. Trong giai đoạn rotation có nhiều khóa cùng được công bố và chỉ AS biết key nào đang dùng để ký token mới. Verifier phải chọn key theo các thuộc tính/metadata phù hợp và chữ ký; **không chọn `keys[0]` như một quy tắc bảo mật**.

Nếu `kid` trống, hãy theo chính sách của thư viện/profile và bảo đảm không tạo đường thử mọi issuer/alg tùy ý. Với môi trường có nhiều key đang hoạt động, **phát token có `kid` rõ ràng và không trùng** là thực hành tốt để giảm ambiguity.

## 23. Key management không kết thúc ở JWKS

Public key distribution chỉ là một phần của **signing key lifecycle**:

~~~text
Generate -> Store -> Authorize sign -> Publish public part
    -> Monitor -> Rotate -> Retire -> Destroy/Archive per policy
                       |
                       +--> Emergency compromise response
~~~

| Giai đoạn | Kiểm soát cần thiết |
|---|---|
| **Key generation** | CSPRNG, thuật toán/key size phù hợp chuẩn và security requirements |
| **Private key custody** | KMS/HSM, least privilege, non-exportable nếu khả thi |
| **Signing authorization** | Chỉ AS/workload được duyệt có quyền sign, audit usage |
| **Public JWKS publication** | Chỉ public members, ký duyệt/pipeline có kiểm soát |
| **Distribution** | HTTPS, metadata/issuer pinning, cache/availability |
| **Verification** | `kid`/alg/kty/use, signature, token profile, issuer/audience |
| **Rotation** | Prepublish, switch signer, overlap, retire đúng thời điểm |
| **Emergency distrust** | Revoke signing ability, purge key caches, deny forged tokens |
| **Retirement/destruction** | Bỏ trusted key khi không cần, quản lý bản sao/backups theo policy |

### Cẩn thận khi một khóa phục vụ nhiều mục đích

Nếu cùng signing key được dùng cho access tokens, ID tokens và hệ thống webhook riêng, sự cố khóa có thể ảnh hưởng **nhiều trust domains**. **Purpose/key separation** (ít nhất ở policy và khi phù hợp bằng các key riêng) giúp giới hạn phạm vi sự cố và giảm khả năng chấp nhận token sai mục đích.

Mỗi key nên có **owner, issuer, algorithm, purpose, creation/activation/retirement dates, next rotation plan, emergency contact và audit trail**. JWKS thường không công bố toàn bộ thông tin quản trị này; nó là dữ liệu vận hành nội bộ.

### Signing service authorization

Không chỉ “không export private key”; nếu bất kỳ workload nào có thể gọi API `Sign` của KMS/HSM với payload tùy ý, attacker có thể **nhờ KMS ký JWT giả dù không lấy được key bytes**. Vì vậy cần:

- Least privilege và workload identity rõ ràng cho ký token.
- Audit mỗi hoạt động ký theo issuer/key/purpose và điều tra bất thường.
- Kiểm policy issuance **trước** khi gọi sign: subject, client, grant, scope, audience, TTL.
- Quota/rate limit và giám sát bất thường, nhất là khi key là shared signing infrastructure.

**KMS/HSM bảo vệ key material nhưng không tự bảo vệ logic phát hành token sai quyền.**

## 24. Quan sát, cảnh báo và SLO cho JWKS distribution

Các metrics hữu ích:

| Metric | Mục đích | Cảnh báo khi nào? |
|---|---|---|
| **jwks_fetch_success_rate** | Tỷ lệ tải JWKS từ AS/CDN | Giảm mạnh hoặc lỗi TLS/5xx |
| **jwks_fetch_latency** | Độ trễ phân phối khóa | p95/p99 tăng ảnh hưởng cold start |
| **unknown_kid_rate** | Mức JWT mang `kid` chưa biết | Tăng sau rotation hoặc bị abuse |
| **signature_validation_failure_rate** | Thất bại verify JWS | Sau deploy/rotation, cảnh báo khi có spike |
| **active_signer_kid** | AS đang ký bằng key nào | Ký bằng B trước khi publish B |
| **published_key_set_revision** | Phiên bản representation JWKS | Các nodes/CDN phục vụ khác revision |
| **last_successful_jwks_refresh_age** | Tuổi lần đồng bộ tin cậy gần nhất | Vượt hard cache policy |
| **key_distrust_propagation_latency** | Thời gian RS ngừng tin key compromised | Vượt incident response SLO |
| **alg_rejection_count** | Token yêu cầu alg bị cấm | Misconfiguration hoặc tấn công |
| **unexpected_key_count/type** | Public JWKS thay đổi ngoài kế hoạch | Lộ khóa/quy trình publish sai |

### Audit an toàn

~~~json
{
  "event": "jwt_verification_rejected",
  "issuer_ref": "auth-main",
  "resource_server": "orders-api",
  "reason_code": "UNKNOWN_KID",
  "jwk_set_revision": "17",
  "request_id": "req-example-004"
}
~~~

Không log **full JWT, access token, refresh token, Authorization header, secret key hoặc JWK private members**. `kid` là untrusted input, nên cần limit/sanitize khi log hoặc dùng metric labels để tránh log injection và cardinality explosion. Với phân tích sự cố, dùng **issuer reference**, **reason code**, **token fingerprint HMAC** khi thật sự cần và có chính sách truy cập riêng.

### SLO nào đáng theo dõi?

- Sau **planned rotation**, mọi RS phải biết key mới **trước khi AS ký bằng key ấy**.
- Sau **emergency distrust**, thời gian để mọi RS ngừng tin key compromised phải có **mục tiêu/giới hạn được đo**, không chỉ thông báo “đã cập nhật JWKS”.
- Với **JWKS outage**, RS duy trì availability chỉ khi có cached trusted key hợp lệ theo policy; tuyệt đối không **bypass signature**.

## 25. Sự cố thực tế: planned rotation khiến API trả 401

Giả sử:

~~~text
AS:
  09:00 JWKS = [A]
  09:05 ký JWT bằng B (kid=B)
  09:10 JWKS mới chuyển thành [A, B]

RS:
  cache JWKS [A] đến 09:08
  nhận JWT kid=B tại 09:06
~~~

### Tại sao lỗi?

RS có đúng **issuer**, đúng thuật toán và đúng access token `aud`, nhưng thiếu **public key B** để kiểm chữ ký. Từ chối tại 09:06 là **hành vi bảo mật đúng**; sai ở trình tự rotation của AS.

### Không nên chữa lỗi bằng cách nào?

- Không tắt signature validation.
- Không tin payload JWT chỉ vì `iss` trông giống issuer thật.
- Không lấy `jku` trong header làm thay trusted JWKS.
- Không dùng public key A để “thử ký” JWT có `kid=B` nếu key selection không cho phép.
- Không tự tăng clock leeway để bỏ qua lỗi key không tồn tại.

### Phương án khắc phục

Quay về signer A nếu A vẫn tin cậy và policy cho phép, **publish B trước**; đảm bảo mọi RS/caches đã nhận B qua kiểm thử distribution, rồi mới switch signer. Có thể dùng rollout theo stage, canary verifier và metric `unknown_kid`.

**Rotation availability failure khác compromise.** Nếu A chưa bị lộ, overlap thường là mục tiêu đúng. Nếu A bị lộ, phải ưu tiên distrust A ngay cả khi làm một số token cũ bị từ chối.

## 26. Sự cố thực tế: khóa RSA ký JWT bị lộ

Một AS sử dụng private key A ký access tokens. Sau một sự cố quản lý secret, private key A bị lộ. Kẻ tấn công có thể tự tạo một JWT với:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "admin-example",
  "aud": "orders-api",
  "scope": "orders:write",
  "exp": 1795400900
}
~~~

Nếu kẻ tấn công thật sự có private key A, JWT giả có thể **vượt qua chữ ký bằng key A**. Kiểm `iss`, `aud`, `exp` và scope theo token **không đủ** để phân biệt token giả với token issuer thật đã ký, vì attacker kiểm payload trước khi ký.

**Hướng ứng cứu:** vô hiệu ký A, cấp key B, phát lệnh **distrust A** cho mọi RS, xóa cache JWKS/deny key A theo chính sách, buộc phát lại token hợp lệ khi cần, điều tra token giả và đánh giá độ trễ phân phối. Resource Server vẫn phải áp dụng object-level policy, nhưng không được xem đó là lý do để trì hoãn khôi phục trust key.

### Thứ tự ưu tiên

1. Không cấp thêm token bằng A.
2. Ngăn mọi verifier tiếp tục tin A theo incident policy.
3. Bảo đảm B đủ tin cậy để khôi phục dịch vụ.
4. Đánh giá phạm vi token/issuer và cấp phát lại theo quy trình.
5. Chứng minh mọi node, cache/CDN, DR region và khách hàng tích hợp đã cập nhật trust state.

Một public JWKS không chứa private key vẫn **không tự chống được private key bị lộ ở nơi khác**. Chính sách thu hồi tin cậy ở RS mới quyết định giảm hậu quả nhanh đến đâu.

## 27. Ma trận kiểm thử JWKS và public key distribution

Kiểm thử nên bao phủ **AS publish**, **RS fetch/cache**, **JWS verify**, **claims validation**, **rotation**, **emergency distrust** và API authorization. Chỉ kiểm “JWT giải mã được payload” không có giá trị xác minh chữ ký.

| ID | Loại | Tình huống | Kết quả mong đợi |
|---|---|---|---|
| **S01** | JWKS | Endpoint HTTPS trả public RSA JWK đúng `n/e/kid` | RS parse và dùng key để verify đúng profile |
| **S02** | JWKS | `keys` chứa A và B trong planned rotation | RS verify token hợp lệ ký bằng A hoặc B theo policy |
| **S03** | HTTP cache | JWKS có `ETag`, conditional GET trả 304 | RS giữ last-known-good representation đúng contract |
| **S04** | JWT | Token RS256 ký bởi private key được tin | Signature verification thành công |
| **S05** | JWT | Token có `iss`, `aud`, `exp`, type, scope hợp lệ | Có thể tiếp tục policy evaluation |
| **S06** | Rotation | Public key B publish trước khi AS ký bằng B | RS nhận biết B trước switch signer |
| **S07** | Multi issuer | A và B có cùng `kid` nhưng key khác | RS dùng key đúng issuer/trust namespace |
| **S08** | Availability | JWKS tạm lỗi, cache trusted key vẫn trong hard TTL | RS có thể verify token cũ nếu policy cho phép |
| **F01** | Disclosure | Public JWKS chứa `d` của RSA/EC/OKP | Kiểm publish thất bại; báo sự cố lộ private key |
| **F02** | Disclosure | Public JWKS chứa `kty=oct` kèm `k` | Từ chối publish/khẩn cấp xử lý lộ HMAC secret |
| **F03** | Trust | JWT có `iss` của attacker và tự quảng bá JWKS | RS từ chối issuer không nằm allowlist |
| **F04** | Trust | JWT header `jku` trỏ tới attacker.example | Không fetch/chấp nhận key attacker |
| **F05** | SSRF | `jku` trỏ link-local/loopback/private IP | Không truy cập địa chỉ attacker chỉ định |
| **F06** | Trust | Header có embedded `jwk` do attacker tạo | Không coi embedded key là AS signing key |
| **F07** | Certificate | `x5c` certificate không khớp JWK public key | Từ chối theo profile/key validation |
| **F08** | Certificate | `x5u` dẫn đến redirect chain ngoài allowlist | Không tải certificate từ URL không tin |
| **F09** | Algorithm | JWT `alg=none` | Từ chối signed access-token requirement |
| **F10** | Algorithm | JWT `alg=HS256` nhưng RS chỉ cho RS256 | Từ chối; không dùng RSA public key làm HMAC secret |
| **F11** | Algorithm | Header `alg=RS256` nhưng key `kty=EC` | Từ chối key-type mismatch |
| **F12** | Usage | JWT định verify bằng JWK `use=enc` | Từ chối key dùng sai purpose |
| **F13** | Usage | `key_ops` xung đột `use` hoặc profile | Từ chối ambiguous/invalid key metadata |
| **F14** | Key ID | `kid` không tồn tại trong trusted JWKS | Bounded refresh rồi từ chối nếu vẫn unknown |
| **F15** | DoS | 10.000 JWT có `kid` ngẫu nhiên | RS rate limit/single-flight JWKS fetch, không quá tải AS |
| **F16** | Injection | `kid=../../secrets/private.pem` | Không được truy file local |
| **F17** | Injection | `kid` quá dài hoặc chứa ký tự điều khiển | Parser giới hạn, log sanitized |
| **F18** | Ambiguity | Một trusted JWKS có hai key trùng `kid`, metadata xung đột | Không chọn key tùy tiện; xử lý an toàn |
| **F19** | Ordering | RS chọn `keys[0]` thay vì chọn đúng key | Test phát hiện key-selection bug |
| **F20** | Signature | Payload JWT bị sửa sau khi ký | Signature validation thất bại |
| **F21** | Signature | Token ký bằng private key không thuộc trusted issuer | RS từ chối |
| **F22** | Issuer | Token có chữ ký hợp lệ ở AS-B nhưng `iss` yêu cầu AS-A | Từ chối issuer/key binding sai |
| **F23** | Audience | JWT ký hợp lệ nhưng `aud=payments-api` gửi Orders API | Từ chối |
| **F24** | Expiration | Token ký hợp lệ nhưng hết `exp` hoặc chưa tới `nbf` | Từ chối |
| **F25** | Token type | ID token dùng làm access token ở RS | Từ chối theo type/profile/audience |
| **F26** | Scope | Token hợp lệ nhưng thiếu `orders:write` | Từ chối API ghi |
| **F27** | Tenant | Token đúng audience/scope, truy order của tenant khác | Từ chối theo object-level authorization |
| **F28** | Revocation | JWT bị AS revoke nhưng RS chỉ verify offline | Test chỉ rõ giới hạn; không khẳng định revoke tức thì |
| **F29** | Rotation | AS ký bằng B trước khi publish B | Canary/RS từ chối token, phát hiện availability regression |
| **F30** | Rotation | AS xóa A quá sớm khi còn JWT A hợp lệ | Test phát hiện khách hàng bị 401 trái rollout plan |
| **F31** | Rotation | `kid=A` bị tái sử dụng cho public key B trong overlap | Test phát hiện key ID reuse/ambiguity |
| **F32** | Rotation | CDN phục vụ JWKS thiếu B sau khi signer chuyển sang B | Test phát hiện stale publication ở edge |
| **F33** | Compromise | Private key A lộ, RS vẫn giữ cache A qua incident SLO | Test thất bại, yêu cầu emergency distrust/purge |
| **F34** | Compromise | AS chỉ revoke RT nhưng JWT giả bằng key A còn được nhận | Phát hiện key-trust incident chưa xử lý |
| **F35** | Cache | Token issuer A được xác minh bằng cache key B do `kid` giống | Từ chối cross-issuer key confusion |
| **F36** | Cache | JWKS fetch TLS certificate invalid | Fail closed, không bỏ TLS verification |
| **F37** | Availability | Không có trusted public key và JWKS timeout | Không bypass signature, trả lỗi phù hợp |
| **F38** | Availability | Last-known-good cache đã vượt hard trust TTL | Không tiếp tục tin vô hạn |
| **F39** | Metadata | Discovery trả issuer khác expected issuer | Từ chối metadata/key endpoint |
| **F40** | Privacy | API log full bearer JWT khi verify lỗi | Test phát hiện token leakage |
| **F41** | Multi-tenant | Tenant chưa đăng ký gửi `iss` tùy ý | Không tự tạo trusted decoder qua unverified issuer |
| **F42** | Sender constraint | DPoP-bound access token ký bởi AS nhưng thiếu DPoP proof | Từ chối theo sender-constrained profile |
| **F43** | Token purpose | JWT logout token dùng làm API access token | Từ chối token confusion |
| **F44** | Access | JWT hợp lệ nhưng current resource policy đã cấm quyền | Từ chối theo policy, độc lập chữ ký |

**Đánh giá phải quan sát cả hành vi thực**: key nào đã được publish, key nào AS đang ký, cache tại từng RS/CDN, JWT verification result và quyết định API. Chỉ assert HTTP 200 của JWKS endpoint không đủ; endpoint có thể trả **sai public key** hoặc **private material** dù vẫn có status 200.

## 28. Integration tests: ba ranh giới bắt buộc

### Test A — Planned rotation với cache thật

~~~text
Given:
  AS dùng private key A để ký JWT.
  RS có cached trusted JWKS [A] và TTL policy cố định.
  Token A còn thời hạn và đúng issuer/audience.
When:
  AS publish JWKS [A,B] nhưng vẫn ký A.
  RS refresh JWKS theo TTL hoặc controlled refresh.
  AS chuyển signer sang B sau khi RS có B.
Then:
  JWT A vẫn được verify trong overlap.
  JWT B được verify ngay khi AS bắt đầu ký B.
  RS không hạ cấp signature verification.
  Sau khi mọi JWT A cần hỗ trợ đã hết hạn, AS bỏ A
  và RS bỏ A theo retirement policy.
~~~

**Test biến thể:** để một CDN/RS node vẫn chỉ có JWKS `[A]`, rồi signer chuyển B. Hệ thống phải báo động/nhìn thấy `unknown_kid`, không âm thầm cho qua token B.

### Test B — Unknown `kid` và JWKS fetch storm

~~~text
Given:
  Trusted issuer và trusted JWKS URI đã pin.
  RS cache bộ key hợp lệ [A].
When:
  Attacker gửi hàng nghìn JWT với kid=random-X.
Then:
  RS giới hạn tổng lần refetch JWKS trên mỗi issuer.
  Không fetch URL trong header jku/x5u.
  Không dùng candidate key từ token để tự xác minh.
  Mọi JWT không verify được đều bị từ chối.
  AS/JWKS không bị tạo hàng nghìn HTTP GET đồng thời.
~~~

**Test biến thể:** AS thật sự publish B giữa lúc có unknown-key traffic. Negative caching/rate limit phải tránh **chặn B quá lâu**; kỹ thuật backoff cần đáp ứng rotation availability SLO.

### Test C — Emergency signing-key compromise

~~~text
Given:
  RS đã cache public key A.
  AS đã phát JWT hợp lệ bằng A.
  Incident xác nhận private key A bị compromise.
When:
  AS ngừng ký A và xuất bản B.
  Vận hành gửi lệnh distrust A theo incident policy.
Then:
  Các RS từ chối token ký A trong thời gian SLO đã cam kết,
    kể cả cache JWKS cũ vẫn chứa A.
  Các token ký B có issuer/audience/type/scope đúng được
    chấp nhận sau khi rollout tin cậy hoàn tất.
  Không dùng AS outage hoặc cache stale để bỏ bước distrust.
  Audit cho thấy thời gian từ incident decision tới
    trạng thái verifier đã ngừng tin A ở mọi node.
~~~

**Đây là kiểm thử khác planned rotation**: việc token A bị từ chối sớm là quyết định an ninh có chủ đích khi key bị xâm phạm, không phải regression cần sửa bằng cách kéo overlap.

## 29. Checklist trước khi đưa JWKS vào production

1. **Issuer trust:** RS có danh sách issuer cố định/được phê duyệt, xác minh `iss` sau chữ ký?
2. **JWKS discovery:** `jwks_uri` đến từ trusted discovery/configuration và metadata issuer exact match?
3. **TLS/egress:** TLS verification bật, hạn chế redirect, SSRF và private IP access?
4. **Public-only:** JWKS không bao giờ xuất `d`, `k` hoặc private key parameters?
5. **Key custody:** Private signing keys nằm trong KMS/HSM/secret store, least-privilege signer identity?
6. **Key purpose:** `use`, `key_ops`, `kty` và `alg` được kiểm phù hợp token profile?
7. **Algorithms:** Có allowlist rõ; không nhận `none`, không RS/HS confusion?
8. **JOSE header:** `kid`, `jku`, `jwk`, `x5u` chỉ được xử lý theo trust contract; không fetch URL tùy ý?
9. **Key IDs:** `kid` unique trong key set được dùng, không reuse trong overlap; xử lý ambiguous IDs?
10. **Cache namespace:** Cách ly key cache theo issuer, environment và trust policy, không cache global chỉ theo `kid`?
11. **Cache TTL:** Có ETag/Cache-Control/hard bounds, last-known-good policy và emergency purge?
12. **Unknown key:** Có bounded refresh, single-flight, backoff, negative cache hợp lý, chống fetch storm?
13. **Rotation:** Key mới được publish và kiểm propagation trước khi signer dùng nó?
14. **Overlap:** Key cũ giữ đủ thời gian cho token còn hiệu lực **khi không có compromise**?
15. **Compromise:** Có lệnh distrust signing key và quy trình đo propagation tới từng RS, kể cả CDN/DR?
16. **Signature:** Dùng JOSE library kiểm chữ ký thật; không chỉ Base64URL decode payload?
17. **Claims:** Kiểm `iss`, `aud`, `exp`, `nbf`, token type/profile và `jti` theo policy?
18. **Authorization:** Scope, tenant, client/grant và object permissions vẫn được kiểm độc lập?
19. **Token types:** API không chấp nhận ID token, refresh token, logout token hoặc DPoP proof như access token?
20. **Sender constraint:** Nếu token có `cnf`/DPoP/mTLS binding, RS kiểm bằng chứng sender đúng?
21. **Revocation:** JWT offline validation có giới hạn thu hồi sớm đã được thỏa thuận; RS không tự tuyên bố revoke tức thì?
22. **Privacy:** Không log bearer JWT, secret, full Authorization header; `kid` và claims được sanitize/limit?
23. **Monitoring:** Có unknown-kid, signature-failure, JWKS cache-age, key-set revision và emergency distrust SLO?
24. **Tests:** Có positive, malformed JWK, alg confusion, issuer swap, audience, rotation overlap, CDN stale, key compromise và SSRF tests?
25. **Governance:** Có key owners, activation/retirement schedule, access reviews, recovery/rollback và incident contacts?

## 30. Câu hỏi tự đánh giá

**1. JWKS dùng để làm gì?** Công bố một tập **JWK** để verifier nhận public keys theo nguồn tin cậy; phổ biến nhất là kiểm chữ ký JWT do AS/OP phát hành.

**2. Tại sao private key không có trong JWKS công khai?** Vì bên có private key có thể ký token giả mạo issuer. Public JWKS chỉ được chứa key material không bí mật phù hợp mục đích phân phối.

**3. `kid` có chứng minh một key thuộc AS không?** Không. Nó chỉ hỗ trợ tìm key **trong trust set đã được cấu hình**.

**4. Một JWT có `jku=https://attacker.example/jwks` và chữ ký khớp key ở đó có được chấp nhận không?** Không nếu URL ấy không được issuer/profile tin cậy. HTTPS không thay thế trust anchor.

**5. Khác nhau giữa JWKS và introspection là gì?** JWKS phân phối **public verification keys**; introspection có thể cung cấp **trạng thái token active/metadata** từ AS cho caller có quyền.

**6. Vì sao cùng `kid` ở hai issuers không đồng nghĩa cùng một key?** `kid` không phải định danh toàn cục; cache và verifier phải cô lập theo issuer.

**7. Public JWK `use=enc` có nên dùng để kiểm JWS signature không?** Không tự động. Phải tuân theo key purpose/algorithm và policy; thường cần key dùng `sig`.

**8. JWT có chữ ký RS256 đúng nhưng `aud` sai thì sao?** Resource Server vẫn phải từ chối vì token không dành cho API đó.

**9. Vì sao không chọn key đầu tiên trong mảng JWKS?** Trong rotation, JWKS có nhiều keys; thứ tự không đại diện khóa cần verify token đang nhận.

**10. Khi có `kid` mới chưa cache, RS nên làm gì?** Refresh **trusted JWKS** có giới hạn và kiểm lại, nhưng không fetch theo URL do token tự chỉ; từ chối nếu không verify được.

**11. Tại sao publish public key B trước rồi mới chuyển sang ký bằng B?** Để các RS đang cache JWKS có thể lấy B trước khi gặp token mới, tránh lỗi xác minh diện rộng.

**12. Khi nào có thể bỏ public key A sau rotation bình thường?** Khi những token hợp lệ A ký không còn cần được chấp nhận, sau khi xét TTL, clock leeway và propagation/consumers theo policy.

**13. Nếu private key A bị lộ có nên giữ A đến hết thời gian token cũ?** Không mặc định. Phải ưu tiên emergency distrust A để chặn JWT giả; có thể cần từ chối token cũ và phát lại.

**14. Chỉ xóa key A khỏi JWKS endpoint có đủ khi key bị lộ không?** Không chắc. RS có thể cache JWKS chứa A; cần revoke trust tại verifier và đo propagation.

**15. Dùng JWKS có khiến refresh token hoặc opaque token được xác minh bằng chữ ký không?** Không mặc định. Các token ấy theo mô hình riêng của AS/introspection/token endpoint, không suy từ việc có JWKS.

**16. DPoP key trong JWT proof có phải khóa issuer JWKS không?** Không. DPoP liên quan sender proof; issuer key ký access token là trust domain khác.

**17. Nếu JWKS endpoint lỗi, có được tắt signature verification để giữ uptime không?** Không. Chỉ có thể dùng cached trusted key còn được phép theo policy hoặc từ chối khi thiếu bằng chứng.

**18. Một JWT verify được chữ ký có chứng minh user được đọc mọi đối tượng không?** Không. RS còn phải kiểm tenant, resource ownership, scope và authorization policy.

## 31. Tài liệu chuẩn và tổng kết

Các tài liệu nền tảng để đối chiếu khi triển khai thực tế:

- **RFC 7517 — JSON Web Key (JWK):** định dạng JWK/JWKS và các trường key.
- **RFC 7518 — JSON Web Algorithms (JWA):** biểu diễn khóa và thuật toán JOSE.
- **RFC 7515 — JSON Web Signature (JWS):** cấu trúc và xác minh chữ ký/MAC.
- **RFC 7516 — JSON Web Encryption (JWE):** mã hóa và ranh giới key purpose.
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc claims của JWT.
- **RFC 7638 — JSON Web Key (JWK) Thumbprint:** cách tính thumbprint từ các public key members được chuẩn hóa.
- **RFC 8725 — JSON Web Token Best Current Practices:** kiểm thuật toán, tránh nhầm token/key/issuer và trust boundary.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata** và **OIDC Discovery 1.0:** nhận diện issuer và `jwks_uri`.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** validation requirements cho JWT access tokens theo profile.
- **RFC 6749 — OAuth 2.0**, **RFC 7009 — Token Revocation**, **RFC 7662 — Token Introspection:** vai trò phát hành, thu hồi và kiểm trạng thái token.
- **Java JCA/JCE, Spring Security Resource Server, Nimbus JOSE + JWT:** tài liệu API và thư viện cần kiểm theo phiên bản triển khai.

Không phải mọi AS/OP sử dụng cùng thuật toán, cung cấp cùng profile JWKS, hỗ trợ JWK fields hoặc có cùng chiến lược cache/rotation. **Chỉ dùng ví dụ minh họa sau khi kiểm hợp đồng cụ thể và kiểm thử với provider thực tế**; đừng tự coi một `jwks_uri` tìm thấy qua mạng là đáng tin.

**Ghi nhớ:** **JWKS phân phối public keys, không phân phối niềm tin một cách tự động.** Resource Server phải bắt đầu từ **issuer và metadata/JWKS URI đã được tin cậy**, chọn **đúng khóa theo `kid`, `kty`, thuật toán và mục đích**, kiểm **chữ ký JWS thực sự**, rồi vẫn kiểm **issuer, audience, thời hạn, token type, scope và quyền tài nguyên**. Khi rotation bình thường, **publish khóa mới trước khi ký bằng nó và giữ overlap có kiểm soát**; khi private signing key bị xâm phạm, **phải ngừng tin key cũ tại mọi verifier**, kể cả cache. Bảo vệ private key, chống URL/key injection, quản lý cache và xử lý thu hồi đúng cách mới giúp vòng đời token bảo mật từ phát hành tới hết hiệu lực.
