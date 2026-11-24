# Algorithm agility

## Mục tiêu học tập

Trong chương **Cryptography** của học phần **Token Security Fundamentals**, **algorithm agility** (*khả năng chuyển đổi thuật toán mật mã an toàn*) là năng lực **thay đổi có kiểm soát** thuật toán, tham số, khóa, thư viện và giao thức khi có rủi ro mới, yêu cầu tuân thủ mới hoặc nhu cầu vận hành mới — **mà không để đầu vào không tin cậy tự hạ cấp cơ chế bảo vệ**.

Trong OAuth 2.0 và OpenID Connect (OIDC), vấn đề này đặc biệt rõ ở JWT/JWS/JWE: một access token hoặc ID token có thể tự khai `alg` trong phần header, nhưng **header chưa được xác minh không được quyền quyết định thuật toán mà ứng dụng sẽ tin**. Việc “hỗ trợ mọi thuật toán để dễ tương thích” có thể mở lại thuật toán yếu, tạo nhầm lẫn giữa khóa đối xứng và bất đối xứng hoặc cho token của issuer khác vượt qua ranh giới xác thực.

Sau bài này, bạn có thể:

1. Giải thích **algorithm agility khác algorithm negotiation tùy ý** và khác với việc chỉ đổi `kid`/khóa ký.
2. Phân biệt hash, MAC, digital signature, authenticated encryption, key agreement và TLS trong hệ thống token.
3. Thiết kế **allowlist thuật toán theo issuer, token purpose, Client/Resource Server và trust domain**, không dựa vào header chưa verify.
4. So sánh `HS256`, `RS256`, `PS256`, `ES256` và `EdDSA` cùng các ràng buộc key type, key size, thư viện, profile.
5. Phân tích `alg=none`, **RS256↔HS256 confusion**, downgrade, key confusion, `kid` injection, `jku`/`x5u` và cross-JWT confusion.
6. Hiểu sự khác nhau giữa **JWS `alg`**, **JWE `alg`/`enc`**, JOSE `kid`/JWK/JWKS và cipher suite TLS.
7. Lập kế hoạch migration theo giai đoạn: inventory, chuẩn bị verifier, publish key, đổi issuer signing, theo dõi, vô hiệu thuật toán cũ, rollback có hạn.
8. Áp dụng trong Java/Spring Security, phân biệt signed ID token, JWT/opaque access token, Client assertion, DPoP proof và mTLS.
9. Kiểm thử cả **happy path, downgrade, lỗi vận hành, rotation, incident và quyền trên từng object/tenant**.

## 1. Thuật toán mật mã không được bất biến mãi mãi

Một dịch vụ phát access token năm nay có thể dùng khóa RSA và `RS256`; trong tương lai muốn chuyển sang `PS256` hoặc `ES256` để đáp ứng policy/khả năng vận hành. Nếu mã nguồn hardcode một thuật toán mà không có kế hoạch cập nhật, hệ thống có thể gặp downtime khi issuer đổi cách ký. Ngược lại, nếu verifier chấp nhận **bất kỳ `alg` nào JWT tự khai**, hệ thống có nguy cơ bị mạo danh.

**Algorithm agility** là khả năng **chuyển đổi qua cơ chế an toàn được quản trị và kiểm thử**, không phải khả năng **tự động tin cơ chế yếu hơn**.

~~~text
Trước migration:
  AS ký JWT bằng RS256 + private key A.
  RS chỉ chấp nhận RS256 và public key A thuộc issuer tin cậy.

Giai đoạn chuyển tiếp có kiểm soát:
  AS công bố public key B phù hợp PS256.
  RS tạm chấp nhận {RS256, PS256} từ issuer đã tin
    với key type, key ID, token profile và deadline cụ thể.
  AS bắt đầu phát JWT PS256 bằng private key B.

Sau migration:
  RS chỉ chấp nhận PS256 theo policy.
  RS256 bị gỡ khỏi allowlist; khóa A không còn được dùng.
~~~

**Ví dụ là một kịch bản lựa chọn**, không khẳng định PS256 luôn là thuật toán tốt nhất cho mọi hệ thống hoặc mọi OP. Nếu thư viện, tiêu chuẩn ngành hay AS không hỗ trợ, cần chọn đường di chuyển phù hợp thay vì tự tạo thuật toán.

### Ba chữ “đổi” không giống nhau

| Hoạt động | Thay đổi chính | Có phải đổi thuật toán? | Ví dụ |
|---|---|---|---|
| **Key rotation** | Thay **key pair/secret** nhưng giữ thuật toán. | Không nhất thiết. | `RS256/key-A` → `RS256/key-B`. |
| **Algorithm migration** | Đổi thuật toán hoặc tham số mật mã được phép. | Có. | `RS256` → `PS256`. |
| **Protocol/format migration** | Đổi profile hoặc biểu diễn credential. | Có thể liên quan nhưng rộng hơn. | JWT access token → opaque token với introspection. |
| **Crypto provider migration** | Đổi thư viện/JCA provider, KMS/HSM, phần cứng. | Có thể vẫn dùng cùng alg. | Đổi signing service nhưng giữ `PS256`. |

Mỗi hoạt động cần kiểm thử khác nhau. **Chỉ thay `kid` trong JWT không chứng minh thuật toán hay khóa đã thay**, và **chỉ thêm thuật toán mới vào allowlist không bảo đảm issuer đã phát token bằng thuật toán mới**.

## 2. Lập bản đồ mật mã trước khi thiết kế agility

Trong một nền tảng token, các primitive thường có mục đích riêng:

| Cơ chế | Ví dụ | Chứng minh/bảo vệ điều gì? | Không tự bảo đảm |
|---|---|---|---|
| **Hash** | SHA-256 | Tạo digest có tính chất chống va chạm/tiền ảnh theo giả định an toàn. | Không chứng minh người phát thông điệp. |
| **HMAC/MAC** | HMAC-SHA-256 (`HS256` trong JOSE). | Toàn vẹn/xác thực giữa các bên cùng giữ secret. | Không phân biệt được bên nào nắm shared secret đã tạo MAC. |
| **Chữ ký bất đối xứng** | RSA-PSS, ECDSA, EdDSA. | Private key ký; public key tương ứng xác minh. | JWT payload được giữ bí mật; issuer/audience/scope đã hợp lệ. |
| **Mã hóa có xác thực (AEAD)** | AES-GCM. | Bí mật nội dung và phát hiện sửa ciphertext/tag khi dùng đúng. | Chủ thể của JWT có quyền gọi API nào. |
| **Key agreement/encapsulation** | ECDH-ES trong JOSE profile thích hợp. | Thiết lập/bao bọc khóa phục vụ mã hóa. | Chính sách phân quyền của Client/RS. |
| **CSPRNG** | `SecureRandom`/KMS RNG. | Sinh nonce, token, secret hoặc key material khó đoán. | Secret sẽ được lưu trữ an toàn sau khi tạo. |
| **TLS** | TLS 1.2/1.3 với cipher suites phù hợp. | Bảo vệ kênh truyền và xác thực endpoint theo trust store. | Nội dung JWT tự động hợp lệ hoặc Client được cấp scope. |

### Những lớp thường xuất hiện trong Authorization Code + PKCE

~~~mermaid
flowchart TD
    C["OAuth Client"] -->|"Authorization Code + PKCE S256"| AS["Authorization Server"]
    AS -->|"JWS: private signing key"| AT["JWT access token"]
    AS -->|"Opaque access token tùy profile"| OP["Opaque token"]
    AT --> RS["Resource Server"]
    OP --> IN["Trusted introspection"]
    IN --> RS
    RS -->|"JWK public key + JOSE policy"| V["Verify issuer/signature hoặc trạng thái"]
    V --> A["Validate aud, type, exp, scope, tenant/object"]
    A --> R["Permit hoặc deny"]
~~~

**PKCE `S256` không có nghĩa Access Token phải dùng `HS256` hoặc `RS256`.** PKCE dùng SHA-256 tạo **code challenge** từ code verifier; đây không phải thuật toán ký JWT. Thuật toán trong `JWS alg` là lựa chọn khác với thuật toán TLS, thuật toán mã hóa storage hoặc hàm hash của PKCE.

## 3. Ranh giới tin cậy: ai được chọn thuật toán?

Một JWT có protected header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-01",
  "typ": "at+jwt"
}
~~~

Các trường header được bảo vệ **bởi chữ ký**, nhưng **trước khi xác minh chữ ký**, chúng vẫn chỉ là dữ liệu do bên gửi token cung cấp. Verifier có thể đọc `alg` và `kid` để **định tuyến tới thuật toán/khóa đã được chính sách cho phép**, chứ không được coi chúng là **mệnh lệnh mở quyền**.

### Phân quyền quyết định

| Thuộc tính | Ai có thẩm quyền quyết định? |
|---|---|
| Issuer nào được tin | Cấu hình/tín nhiệm quản trị của RP hoặc RS. |
| Token profile nào được nhận | RP/RS theo OIDC/OAuth và hợp đồng nghiệp vụ. |
| Allowed signing algorithms | Chính sách của verifier theo issuer/profile, phù hợp đăng ký/metadata đã kiểm tra. |
| Dùng key set nào | Trusted issuer → trusted metadata/`jwks_uri` hoặc key registration đáng tin. |
| `kid` chọn khóa nào | Verifier tìm **trong đúng key set đã tin**, kiểm tra tính duy nhất/compatibility. |
| Token `aud`, `scope`, `exp` có hợp lệ | Verifier theo resource/client policy sau khi verify chữ ký. |
| User có quyền đối với order cụ thể | Resource Server và dữ liệu/quy tắc nghiệp vụ đáng tin. |

### Quy tắc một chiều

~~~text
Policy đáng tin -> quyết định thuật toán/khóa/token type được chấp nhận
JWT header chưa verify -> chỉ được cung cấp gợi ý chọn trong chính sách
JWS signature hợp lệ -> mới cho phép tin claims dưới policy
Validated claims -> tiếp tục authorization, không tự phát quyền rộng hơn
~~~

Không dùng:

~~~text
JWT header alg -> tự bật thuật toán đó
JWT header jku -> tải public key tùy ý rồi tin
JWT payload iss -> tự tin issuer chưa được đăng ký
JWT payload scope -> bỏ qua Resource Server policy
~~~

## 4. `alg=none`: khả năng thuật toán không có chữ ký không phải “tính linh hoạt”

JOSE có định nghĩa `alg="none"` cho một số ngữ cảnh **unsecured JWS**, nhưng **OAuth/OIDC token yêu cầu xác thực nguồn ký** không được chấp nhận nội dung unsigned chỉ vì JWT khai `alg=none`.

### Token do attacker tự tạo

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "admin",
  "aud": "orders-api",
  "scope": "orders:delete",
  "exp": 1893456600
}
~~~

Nếu verifier chỉ decode payload và bỏ qua signature do header khai `none`, attacker có thể **tự viết claims**. Đường phòng thủ là:

1. **Token profile phải yêu cầu chữ ký** nếu đó là hợp đồng AS/RP/RS.
2. Chỉ allowlist signing alg đã duyệt.
3. Không để JWT header chuyển sang mode “không verify”.
4. Sau verify, tiếp tục kiểm tra issuer, audience, loại token và thời hạn.
5. Test token unsigned, missing signature và malformed compact serialization.

Không thể sửa lỗi bằng cách “ẩn `alg` khỏi JSON”. JWT/JWS processor phải chủ động **reject** trường hợp ngoài profile, dù token đã được cấu trúc để trông giống token thật.

## 5. Algorithm confusion: RSA public key bị dùng nhầm làm HMAC secret

Một lỗ hổng kinh điển xuất hiện khi thư viện hoặc code custom nhận **`HS256` và `RS256`** mà không ràng buộc đúng key type.

### Mô hình lỗi

~~~text
Hệ thống hợp lệ:
  AS ký RS256 bằng RSA private key.
  RS verify bằng RSA public key công khai từ JWKS.

Attacker:
  Lấy RSA public key (vốn công khai).
  Tạo JWT với alg=HS256.
  Dùng bytes của RSA public key làm HMAC "secret".

Verifier lỗi:
  Thấy header alg=HS256 nên gọi HMAC verify
  với cùng biến key vốn chứa RSA public key.
  Nếu code sai, nó có thể chấp nhận MAC do attacker tạo.
~~~

**Đây không phải yếu điểm của RSA hay HMAC khi dùng đúng.** Đây là lỗi **trộn lẫn hai lớp thuật toán và kiểu khóa** ở verifier.

### Biện pháp

| Quy tắc | Lý do |
|---|---|
| Nếu issuer ký bằng `RS256`, verifier **chỉ cho phép `RS256`** trong giai đoạn policy đó. | Header attacker không thể chọn HS256. |
| Public RSA/EC key chỉ dùng làm **verification key bất đối xứng** phù hợp. | Không thể vô tình dùng làm HMAC secret. |
| JWK `kty`/`use`/`key_ops`/`alg` phải khớp profile. | Chặn key type/usage confusion. |
| Thư viện JOSE được bảo trì, cấu hình algorithm allowlist rõ. | Tránh nhánh xử lý crypto tự viết. |
| Test token HS256 giả ký bằng bytes public key. | Phát hiện regression. |

**Không viết `verifySignature(jwt, key)` rồi để hàm tự đoán mọi thuật toán từ header**. Kiểu key, mục đích và thuật toán phải được quyết định bởi một **trusted verification policy**.

## 6. Downgrade attack trong quá trình migration

Algorithm agility có thể vô tình tạo downgrade:

~~~text
Tháng 1:
  Verifier chấp nhận RS256.

Tháng 2:
  Verifier chấp nhận RS256 + PS256 để chuyển tiếp.
  Issuer bắt đầu ký PS256.

Tháng 6:
  Verifier vẫn cho RS256 vì "để đề phòng".
  Một Client cũ còn được phép phát/hợp thức token RS256
  hoặc khóa yếu/cũ bị lộ.

=> Chính sách chuyển tiếp không bao giờ kết thúc.
~~~

### Những dạng downgrade

- **Algorithm fallback không có deadline**: một thuật toán cũ tiếp tục được chấp nhận vô hạn.
- **“Try all algorithms”**: nếu alg mới lỗi, verifier thử alg khác để nhận bằng được token.
- **Key fallback cross-issuer**: không có `kid` phù hợp thì dùng khóa từ một issuer khác.
- **HMAC fallback**: từ bất đối xứng chuyển sang shared secret vì thuận tiện.
- **Unsigned fallback**: khi verify thất bại thì decode claims và tiếp tục xử lý.
- **TLS fallback**: bỏ certificate validation hoặc dùng HTTP khi endpoint JWKS/token gặp lỗi.
- **Tenant-specific bypass**: thêm ngoại lệ cho “tenant legacy” mà không kiểm soát scope/token type/thời hạn.

### Đề phòng

Giai đoạn chuyển tiếp phải có **owner, allowlist, danh sách signer được phép, deadline và chỉ số sử dụng**. Khi signer cuối cùng chuyển xong và token cũ hết hạn/hết được tin theo policy, **loại thuật toán cũ khỏi verifier**. Nếu cần tương thích lâu dài với bên phát token legacy, cô lập trong trust domain/adapter riêng với rủi ro được chấp thuận, không biến exception thành mặc định toàn hệ thống.

## 7. So sánh thuật toán chữ ký JOSE thường gặp

| `alg` JOSE | Primitive | Key type | Điểm mạnh | Điều kiện/cẩn trọng |
|---|---|---|---|---|
| **`HS256`** | HMAC-SHA-256. | Shared symmetric secret, `kty=oct`. | Hiệu quả, đơn giản giữa các bên cùng tin và bảo vệ secret. | Mọi verifier nắm secret **cũng có thể tạo token**; không phù hợp mô hình RS công khai chỉ cần verify. |
| **`RS256`** | RSASSA-PKCS1-v1_5 + SHA-256. | RSA private/public. | Tương thích phổ biến; verifier chỉ cần public key. | Quản lý RSA key size, padding đúng profile, library support; không nhầm sang HMAC. |
| **`PS256`** | RSASSA-PSS + SHA-256. | RSA private/public. | Chữ ký PSS với security properties phù hợp khi triển khai đúng. | Cần kiểm tra PSS parameters/JWA, thư viện, HSM, issuer/RS support. |
| **`ES256`** | ECDSA P-256 + SHA-256. | EC key trên P-256. | Public key/chữ ký thường gọn, phổ biến trong JOSE. | Curve validation, ECDSA nonce bảo mật, JOSE signature format khác DER; dùng thư viện đúng. |
| **`EdDSA`** | Edwards-curve signature theo JOSE profile. | OKP (ví dụ Ed25519). | Thuận lợi trong một số hệ thống/phần cứng, không cần signer tự quản ECDSA nonce. | Chỉ dùng khi AS/RP/RS, crypto provider, profile và chuẩn nội bộ thực sự hỗ trợ. |

### Đừng chọn thuật toán chỉ theo độ dài chữ ký

Quyết định còn phụ thuộc:

1. **Threat model**: ai phát token, ai chỉ verify, số lượng RS và ranh giới tin cậy.
2. **Profile**: OIDC ID token, RFC 9068 access token, Client assertion, DPoP.
3. **KMS/HSM/JCA provider** và availability của thuật toán trong hạ tầng hiện tại.
4. **Thuật toán và tham số được cơ quan/tổ chức phê duyệt**, đặc biệt các môi trường kiểm soát tuân thủ.
5. **Tốc độ signing/verification, kích thước JWT, network/CDN cache và năng lực thiết bị**.
6. **Lộ trình migration và rollback**: cách phát và kiểm tra token cũ trong cửa sổ TTL.
7. **Khả năng cập nhật Client và Resource Server**, nhất là bên ngoài tổ chức.

RSA tối thiểu thường cần kích thước khóa đáp ứng mức an ninh được chính sách chấp nhận (chẳng hạn RSA 2048-bit trở lên trong nhiều triển khai), nhưng yêu cầu cụ thể tùy profile, thời hạn sử dụng khóa và policy. **Không sinh RSA 1024-bit mới** chỉ để “token nhỏ và ký nhanh”. Không tự suy rằng EdDSA/ES256 được tất cả thư viện hoặc bên nhận hỗ trợ.

### Shared-secret JWT không mặc định là lựa chọn tốt cho nhiều RS

Nếu AS ký JWT bằng `HS256` và đưa **cùng HMAC key** cho 10 Resource Server để verify, bất kỳ RS nào lộ key có thể **tạo JWT mới trông như do AS ký**. Với hệ thống tách AS/RS, **bất đối xứng** thường thuận lợi hơn: RS chỉ có public key. Nếu dùng HS*, phải có **trusted secret distribution**, ranh giới giữa signer/verifier và khả năng rotate an toàn.

## 8. JWK/JWKS: thuật toán phải phù hợp khóa

Một JWK trong JWKS có thể như:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-legacy-a",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_RSA_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "rsa-pss-b",
      "use": "sig",
      "alg": "PS256",
      "n": "<BASE64URL_RSA_MODULUS_NEW>",
      "e": "AQAB"
    },
    {
      "kty": "EC",
      "kid": "ec-p256-c",
      "use": "sig",
      "alg": "ES256",
      "crv": "P-256",
      "x": "<BASE64URL_X>",
      "y": "<BASE64URL_Y>"
    }
  ]
}
~~~

**Các giá trị khóa trong ngoặc nhọn là placeholder**, không thể verify token thật. JWKS public chỉ nên chứa **public key parameters** phục vụ verification, không có RSA `d/p/q`, EC private `d` hay symmetric HMAC secret.

### Thông tin cần khớp

| Thuộc tính | Cách sử dụng đúng |
|---|---|
| **`kid`** | Gợi ý chọn **đúng key trong key set của issuer**. Không phải bí mật, không phải identity toàn cầu. |
| **`kty`** | `RSA` cho RS*/PS*, `EC` với curve phù hợp cho ES*, `OKP` cho EdDSA tùy profile, `oct` cho symmetric key. |
| **`use`** | `sig` cho signature, `enc` cho encryption khi có. Không dùng khóa encryption để verify chữ ký sai policy. |
| **`key_ops`** | Hoạt động được mô tả như `sign`, `verify`, `encrypt`, `decrypt`; phải nhất quán `use` nếu cả hai có mặt. |
| **`alg`** | Thuật toán dự kiến cho key nếu được công bố; **không tự mở allowlist của verifier**. |
| **`crv`** | Kiểm tra curve tương thích, ví dụ `ES256` với `P-256`. |
| **`x5c`/`x5t#S256`** | Metadata chứng chỉ/thumbprint, không thay trusted issuer/key-source policy. |
| **Private parameters** | Chỉ ở nơi giữ khóa ký/giải mã; **không công bố JWKS public**. |

### Không mặc định `kid` toàn cục

~~~text
Issuer A:
  kid=signing-v2, key=A2

Issuer B:
  kid=signing-v2, key=B2

Sai:
  globalKeys["signing-v2"] = bất kỳ key nào đến trước.

Đúng:
  verifier giữ key set tách theo issuer/trust domain,
  chỉ so kid trong bộ khóa của issuer tương ứng.
~~~

Nếu không có `kid` hoặc có hai khóa `kid` trùng gây mơ hồ, xử lý theo profile đã đăng ký, **không chọn tùy ý phần tử đầu tiên**. Một số profile/issuer có thể cho phép chọn một khóa duy nhất phù hợp khi `kid` vắng mặt; quyết định này cần được cấu hình rõ ràng.

## 9. Discovery metadata và nguồn khóa đáng tin

Một OIDC Client/RP có thể khám phá cấu hình OP:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.test
Accept: application/json
~~~

~~~json
{
  "issuer": "https://auth.example.test",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "id_token_signing_alg_values_supported": ["RS256", "PS256"],
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token"
}
~~~

Đây là **metadata minh họa**. `id_token_signing_alg_values_supported` cho biết khả năng ký **ID token** mà OP công bố; không tự bảo đảm một Resource Server được phép nhận mọi thuật toán đó cho **access token**. Thuật toán được Client đăng ký/đàm phán, key policy và token profile cần được đối chiếu riêng.

### Tin theo chuỗi

~~~mermaid
flowchart TD
    I["Trusted issuer đã đăng ký"] --> M["Fetch discovery/AS metadata qua HTTPS"]
    M --> Q{"Metadata issuer đúng expected issuer?"}
    Q -- Không --> D["Reject"]
    Q -- Có --> J["jwks_uri từ metadata tin cậy"]
    J --> K["Fetch/cache JWKS với TLS và giới hạn"]
    K --> P["Lọc key type/use/kid/alg theo verifier policy"]
    P --> V{"Verify JWS signature?"}
    V -- Không --> D
    V -- Có --> C["Validate claims + token purpose + audience/scope"]
    C --> A["Authorization tại API/RP"]
~~~

**Không lấy URL JWKS từ claim `iss` của token chưa verify rồi tự tin issuer mới.** Trust anchor bắt đầu từ **issuer đã cấu hình**, không bắt đầu từ chuỗi do attacker đưa vào payload.

### `jku`/`x5u` injection và SSRF

~~~json
{
  "alg": "RS256",
  "kid": "attacker-key",
  "jku": "https://attacker.invalid/keys.json",
  "x5u": "http://169.254.169.254/metadata"
}
~~~

Nếu verifier tự tải `jku`/`x5u` do JWS header cung cấp, attacker có thể tạo khóa của mình rồi yêu cầu verifier tin khóa đó, hoặc gây **server-side request forgery (SSRF)**. Mặc định **không follow** các URL này ngoài một profile có allowlist/trust validation chặt chẽ. Cần giới hạn URL, DNS/IP/redirect, response size/time và source trust nếu profile buộc fetch.

## 10. Ràng buộc thuật toán với đúng token purpose

Chấp nhận cùng một thuật toán chữ ký từ một issuer **không đồng nghĩa chấp nhận mọi JWT do issuer ký**. JWT là một container; **ID token, access token, Client assertion, DPoP proof và logout token** có mục đích khác nhau.

| Token/JWS | Người nhận | Header/profile đáng chú ý | Các điều kiện ngoài chữ ký |
|---|---|---|---|
| **OIDC ID token** | Relying Party/Client. | Signing alg được OP/RP chấp nhận; profile OIDC. | `iss`, `aud` chứa `client_id`, `exp`/`iat`, `azp`/`nonce`/hash khi áp dụng. |
| **JWT access token** | Resource Server được nêu trong `aud`. | RFC 9068 yêu cầu xử lý token type, thường `typ=at+jwt`. | `iss`, `aud`, thời gian, scope và object/tenant authorization. |
| **JWT Client assertion** | AS token endpoint. | RFC 7523 và client auth profile. | `iss`/`sub`, `aud` của AS, exp/iat/jti khi policy yêu cầu, client-key registration. |
| **DPoP proof JWT** | AS/RS cần proof theo RFC 9449. | `typ=dpop+jwt`, thuật toán bất đối xứng cho phép, JWK public trong header. | `htm`, `htu`, `iat`, `jti`, `ath`/nonce khi áp dụng, key-token binding. |
| **OIDC Logout Token** | RP back-channel logout consumer. | Logout Token profile, key trust của OP. | Issuer/audience, events claim, thời gian/ID, không nhầm với ID/access token. |
| **Refresh token** | AS token endpoint. | Thường opaque; nếu có JWT format thì profile riêng. | Grant/family/client binding, expiry, rotation/revocation; không gọi RS. |

### Cross-JWT confusion

~~~text
ID token:
  iss = https://auth.example.test
  aud = shop-web
  sub = user-123
  chữ ký RS256 hợp lệ

Resource Server Orders:
  Expected audience = orders-api
  Expected token type = access token

=> REJECT. Không dùng ID token để gọi Orders API.
~~~

**Algorithm agility không được phá vỡ type separation**: dù issuer chuyển từ RS256 sang PS256, verifier vẫn phải phân biệt **đúng loại token và đối tượng nhận**. Token có signature valid và `sub` hợp lệ nhưng thiếu `aud` phù hợp vẫn phải bị từ chối.

## 11. ID token và OIDC algorithm policy

### Các yếu tố cần kiểm tra

Khi RP nhận ID token ký bất đối xứng:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "shop-web",
  "exp": 1893456600,
  "iat": 1893456000,
  "nonce": "<NONCE_FROM_ORIGINAL_REQUEST>"
}
~~~

1. RP xác định **trusted OP/issuer gắn với authorization transaction**, không tin issuer tùy ý từ token.
2. Lấy **signing key đáng tin** theo `jwks_uri` từ OIDC metadata đã xác minh.
3. Chỉ cho phép **OIDC ID token signing alg** theo registration/policy và key type tương ứng.
4. Xác minh JWS signature trước khi tin claims.
5. Kiểm tra `iss` khớp, `aud` chứa **Client ID**, và `azp` khi quy tắc OIDC yêu cầu.
6. Kiểm tra `exp`/`iat`, `nonce` nếu request/profile cần, `auth_time` khi `max_age` hoặc policy cần.
7. Kiểm tra `at_hash`/`c_hash` khi flow/profile yêu cầu; không bắt vô điều kiện đối với mọi Code flow.
8. Không dùng ID token làm authorization credential của Orders API.

### Migration ID token có yếu tố Client

Một OP có thể công bố nhiều thuật toán, nhưng **Client cụ thể** có thể đăng ký dùng một ID token signing algorithm. Khi đổi thuật toán, phải bảo đảm:

- Client library/JWK processor hỗ trợ.
- Client registration/metadata không mâu thuẫn.
- HSM/issuer thực sự phát token mới với alg dự kiến.
- RP kiểm tra phiên bản key cache mới trước khi tắt alg cũ.
- Các quy tắc OIDC như `nonce`, `aud`, `azp` không thay đổi vì đã đổi alg.

## 12. JWT access token và chính sách ở Resource Server

Ví dụ Orders API chỉ nhận JWT access token từ `https://auth.example.test`:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456600
}
~~~

**Payload chỉ minh họa**, không phải token có chữ ký. Nếu issuer đổi `alg`, RS cần:

1. Chỉ nhận issuer đã cấu hình; key/JWKS của issuer đó.
2. Chỉ nhận thuật toán chữ ký **allowlisted cho JWT access token của Orders**.
3. Nếu theo **RFC 9068**, kiểm tra token type `at+jwt`/tương đương profile và các claims bắt buộc tương ứng.
4. Verify signature và khóa/`kid`/key use phù hợp.
5. Kiểm tra `aud=orders-api`, `exp`, `nbf`, `iss`, các điều kiện thời gian.
6. Kiểm tra `scope=orders:read` cho thao tác đọc; quyền tenant, owner, object-level còn do Orders quyết định.
7. Nếu RS yêu cầu revocation state, thêm introspection/denylist/grant version; chữ ký đúng không chứng minh token chưa bị thu hồi.
8. Nếu token là DPoP/mTLS-bound, enforce sender proof/certificate khi tương ứng.

### Một thông điệp dành cho người kiểm thử

**Chữ ký JWT hợp lệ không đồng nghĩa authorization hợp lệ**. Bất kỳ thay đổi nào trong thuật toán/khóa cũng phải **giữ nguyên chính sách audience, token type và phân quyền** — không được chuyển từ validator cũ sang “decode claims only” để tiện tương thích.

## 13. Opaque token và khả năng thay đổi thuật toán phía AS

OAuth 2.0 **không bắt buộc** access token là JWT. Một hệ thống dùng **opaque access token** có thể hỏi trạng thái qua **RFC 7662 introspection**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Authorization: Basic <RESOURCE_SERVER_AUTH>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
~~~

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "orders-api",
  "scope": "orders:read",
  "sub": "user-123",
  "exp": 1893456600
}
~~~

Với opaque token, **RS không thể tự đọc JWS alg/kid để xác minh token**, vì không có JWS để decode. Algorithm agility của AS có thể diễn ra ở storage/token generator, kết nối RS→AS, token verifier hoặc cơ chế ký token nội bộ, nhưng **không biến chuỗi opaque thành một JWT**.

### Những sai lầm khi chuyển token format

- **JWT → opaque:** nếu RS còn cố decode JWT, hệ thống thất bại; cần introspection/state contract và quyền của RS.
- **Opaque → JWT:** nếu RS chỉ kiểm tra `exp` mà bỏ signature/issuer/audience, migration mở lỗ hổng nghiêm trọng.
- **Cùng RS chấp nhận cả hai dạng**: cần policy rõ, lựa chọn parser không được làm giảm xác thực hoặc tạo fallback “unknown token = trusted”.
- Introspection response có thể bị cache; revocation/TTL và audience vẫn phải được RS kiểm tra.

## 14. JWE: có hai loại thuật toán cần quản trị

**JWS** bảo vệ tính toàn vẹn và xác thực nguồn ký; **JWE** bảo vệ tính bí mật của nội dung bằng mã hóa có xác thực. Trong JWE, header thường có **hai** tham số quan trọng:

- **`alg`**: thuật toán **quản lý/thỏa thuận khóa** (ví dụ `RSA-OAEP-256` hoặc một profile `ECDH-ES`).
- **`enc`**: thuật toán **mã hóa nội dung có xác thực** (ví dụ `A256GCM`).

### Header minh họa

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "recipient-encryption-key-2026",
  "cty": "JWT"
}
~~~

JWE Compact Serialization thường có **năm thành phần**:

~~~text
BASE64URL(protected_header)
.
BASE64URL(encrypted_key)
.
BASE64URL(initialization_vector)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication_tag)
~~~

**Không nhầm `alg=RSA-OAEP-256` trong JWE với `alg=RS256` trong JWS**. Một thuật toán dùng public key để mã hóa/bao bọc khóa, thuật toán kia dùng private key để ký dữ liệu.

### Nguyên tắc cho JWE agility

1. Chỉ chấp nhận **cặp `alg`/`enc` đã được profile/policy cho phép**, không tin header bất kỳ.
2. Dùng **authenticated encryption** và kiểm tra tag đầy đủ; tránh triển khai unauthenticated CBC không có MAC tương ứng.
3. Với AES-GCM, đảm bảo **không reuse nonce/IV với cùng key** theo yêu cầu của cơ chế; lựa chọn thư viện có quản lý đúng.
4. Tách **signing keys** và **recipient decryption keys** theo mục đích, không công bố private decryption key trong public JWKS.
5. Đánh giá kỹ các thuật toán key management cũ, ví dụ `RSA1_5`, theo khuyến nghị bảo mật/profile; không giữ thuật toán yếu chỉ vì có trong JWA registry.
6. Khi đổi `enc`/`alg`, kiểm thử interoperability, key IDs, KMS/HSM support, kích thước token, canonicalization và thông báo lỗi không lộ dữ liệu nhạy cảm.
7. Nếu JWT được **ký rồi mã hóa** hoặc **mã hóa rồi ký** theo profile, cần kiểm tra **đúng tất cả các lớp bắt buộc**; decrypt thành công không tự chứng minh claims/issuer đáng tin.
8. Cẩn trọng với **compression + secret + attacker-controlled plaintext** vì có thể tạo side-channel; không tự bật `zip` để giảm kích thước token nếu threat model chưa đánh giá.

### Ví dụ phân tách policy

~~~yaml
# Policy minh họa; KHÔNG phải cấu hình mặc định của Spring/Jose.
trusted_issuer: https://auth.example.test
token_type: id_token_encrypted
allowed_key_management_algorithms: [RSA-OAEP-256]
allowed_content_encryption_algorithms: [A256GCM]
require_inner_signed_jwt: true
inner_signed_jwt_algorithms: [PS256]
recipient_private_key_source: protected-keystore
~~~

Đây là **pseudoconfig** cho tư duy policy; các profile có thể yêu cầu trật tự ký/mã hóa và claims khác nhau. Không dùng trực tiếp một file YAML tự đặt field để giả định framework sẽ tự enforce.

## 15. Client authentication bằng JWT assertion có policy thuật toán riêng

OAuth Client có thể xác thực với AS tại token endpoint bằng các phương thức được đăng ký, ví dụ:

| Phương thức | Credential chính | Chính sách thuật toán |
|---|---|---|
| **`client_secret_basic`** | Client ID và shared secret qua HTTPS Basic. | Không phải JWT signing alg; phải bảo vệ secret/TLS. |
| **`client_secret_post`** | Shared secret trong POST body qua HTTPS. | Không phải JOSE alg; hạn chế log body. |
| **`client_secret_jwt`** | JWT client assertion ký HMAC bằng shared secret. | Chỉ HMAC algorithms/profile được Client/AS hỗ trợ; secret đủ entropy và không lộ. |
| **`private_key_jwt`** | JWT client assertion ký bằng private key của Client. | AS allowlist bất đối xứng alg và xác minh bằng **public key đăng ký cho đúng Client**. |
| **mTLS client authentication** | TLS client certificate và private key của Client. | TLS/X.509 policy, khác với `alg` của JWT access token. |

### Ví dụ `private_key_jwt` assertion

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=billing-worker&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=<URL_FORM_ENCODED_SIGNED_CLIENT_ASSERTION>
~~~

Client assertion có thể có protected header:

~~~json
{
  "alg": "PS256",
  "kid": "billing-client-key-v3",
  "typ": "JWT"
}
~~~

Và payload minh họa:

~~~json
{
  "iss": "billing-worker",
  "sub": "billing-worker",
  "aud": "https://auth.example.test/oauth2/token",
  "iat": 1893456000,
  "exp": 1893456060,
  "jti": "unique-assertion-id"
}
~~~

**Các giá trị và thời gian đều là ví dụ**, không phải JWT đã ký. Theo profile được dùng, AS cần kiểm tra issuer/subject đại diện cho Client, audience phù hợp AS, hạn dùng, thuật toán/key đăng ký, và chống replay `jti`/assertion theo policy. Không chấp nhận JWT assertion của Client A chỉ vì signature đúng bằng một khóa từ **OP JWKS**.

### Ranh giới khóa của Client và AS

~~~text
AS ký access token:
  AS private signing key
  -> Resource Server verify bằng trusted AS public JWKS.

Client xác thực bằng private_key_jwt:
  Client private signing key
  -> AS verify bằng public key đã đăng ký cho đúng client_id.
~~~

Hai nguồn khóa **không được trộn**. Khi chuyển signing algorithm của **access token**, không nhất thiết phải đổi thuật toán của **Client assertion**. Ngược lại, đổi `private_key_jwt` algorithm ở Client cần AS hỗ trợ và cập nhật registration/key policy, không mặc định tác động RS.

## 16. DPoP proof: một JWT nữa với ranh giới tin cậy khác

**Demonstrating Proof of Possession (DPoP, RFC 9449)** sử dụng JWT proof để chứng minh Client có khả năng sử dụng private key liên quan và ràng buộc request. DPoP proof không phải access token và không phải OIDC ID token.

### Protected header DPoP minh họa

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

### DPoP proof payload minh họa

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.test/orders",
  "iat": 1893456000,
  "jti": "proof-unique-id",
  "ath": "<HASH_OF_ACCESS_TOKEN>"
}
~~~

Ở DPoP, public JWK có thể được cung cấp ngay trong proof header theo RFC 9449. Điều này **khác** cơ chế lấy AS signing keys từ trusted OP JWKS:

1. RS/AS chỉ chấp nhận **DPoP signing alg bất đối xứng phù hợp profile**, không chấp nhận `none` hoặc HMAC cho proof.
2. Verifier kiểm tra proof signature bằng **public key trong proof** theo cơ chế DPoP.
3. Quan trọng nhất: với **DPoP-bound access token**, khóa trong proof phải **khớp key binding** của token (thường `cnf.jkt` theo JWK thumbprint), và token phải đúng issuer/audience/scope.
4. Xác minh `htm`, `htu`, `iat`, `jti`, `ath` và `nonce` khi được yêu cầu, cùng replay cache/độ lệch thời gian.
5. **Đúng chữ ký DPoP bằng một khóa bất kỳ chưa đủ**. Nếu không kiểm tra binding, attacker có thể tự tạo proof với khóa của họ cho token không thuộc khóa đó.

### Migration DPoP

Chuyển từ `ES256` sang một thuật toán DPoP khác (khi profile và thư viện hỗ trợ) có thể cần **thay key pair, JWK thumbprint và token binding**. Không giả định DPoP proof mới dùng khóa khác vẫn chứng minh quyền dùng access token cũ ràng buộc `cnf.jkt` của khóa trước. Có thể cần xin access token mới và lập kế hoạch tồn tại song song của các phiên đã được ràng buộc.

### DPoP cũng không thay revocation

Nếu attacker điều khiển thiết bị/khóa có khả năng ký proof, sender constraint không tự ngăn lạm dụng. Cần quản lý key storage, logout, grant revocation, TTL, replay cache và authorization tại RS.

## 17. TLS/mTLS cũng cần agility nhưng độc lập với JOSE `alg`

JWKS được tải qua HTTPS và token gửi qua TLS; mTLS có thể xác thực Client và ràng buộc access token với chứng chỉ. Các thuật toán trong:

- TLS key exchange/cipher suite.
- Chữ ký chứng chỉ và X.509 chain.
- Client authentication bằng mTLS.
- JWT/JWS `alg`.
- JWE `alg`/`enc`.

**không phải cùng một trường điều khiển**.

### Ví dụ

~~~text
AS phát JWT access token:
  JWS alg = PS256

Client kết nối RS:
  TLS 1.3 được thương lượng theo policy
  mTLS certificate dùng khóa/alg phù hợp PKI

RS xác minh:
  JWT signature PS256, issuer, aud, exp, scope
  certificate thumbprint khớp cnf["x5t#S256"] khi token mTLS-bound
  quyền trên object/tenant
~~~

Thuật toán chữ ký JWT có thể chuyển từ `RS256` sang `PS256` mà **không** cần thay cipher suite TLS; nhưng nếu certificate-bound access token chuyển sang chứng chỉ Client mới, cần kiểm tra token binding, session/cert rollover riêng.

### Những nguyên tắc bất biến

1. Không tắt TLS hostname/certificate verification khi JWKS endpoint mới lỗi.
2. Không fallback sang HTTP plaintext vì thuật toán signing/token endpoint chưa tương thích.
3. Không coi **mTLS client auth ở AS** tự động làm access token **certificate-bound tại RS**; AS phải phát binding và RS enforce.
4. Không cho reverse proxy/TLS terminator làm mất hoặc giả **verified client certificate identity**; chỉ tin metadata cert từ proxy đáng tin.
5. Quản lý CA chain, expiration, renewal, trust store, cipher suites và protocol versions theo policy TLS riêng.
6. Chỉ cho phép thuật toán X.509/TLS mà thư viện/PKI được phê duyệt; không tự bật mọi legacy cipher.

## 18. Crypto inventory: biết mình đang dùng thuật toán ở đâu

Trước migration, lập inventory không chỉ ở AS:

| Thành phần | Cần thu thập | Ví dụ |
|---|---|---|
| **AS/OP token issuer** | JWT types, signing alg, `kid`, key size, KMS/HSM, TTL, JWKS rotation. | ID token RS256; access token RS256. |
| **OIDC Relying Parties** | Client đăng ký, thư viện, accepted ID token alg, cache/JWKS source. | `shop-web` chỉ nhận RS256. |
| **Resource Servers** | JWT/opaque, issuer/audience/type allowlist, signature provider. | Orders RS hỗ trợ RS256 và PS256 sau nâng cấp. |
| **Service Clients** | `private_key_jwt`/`client_secret_jwt`/mTLS, key registry, rotation. | Billing Worker dùng PS256 assertion. |
| **DPoP Clients/RS** | Accepted proof alg, key binding, thumbprint, replay cache. | DPoP ES256, `cnf.jkt`. |
| **Encryption recipients** | JWE `alg`/`enc`, private decryption key, profile interoperability. | RSA-OAEP-256 / A256GCM. |
| **TLS/PKI** | TLS versions, cert algorithms, trust store, terminators. | mTLS ở API gateway. |
| **Build/runtime** | JDK/JCA provider, crypto library version, FIPS policy, HSM support. | Java 17+ và Nimbus/Jose. |
| **Key stores** | Owner, usage, creation, activation, expiry, revocation và backup. | signing-key A/B trong KMS. |
| **Client/RS không cập nhật được ngay** | Đối tác, mobile, IoT, external API consumers. | Mobile app cũ không hỗ trợ PS256. |

### Phân loại theo trust domain

Đừng viết inventory kiểu:

~~~text
all-services: allowedAlgorithms = [HS256, RS256, PS256, ES256, EdDSA]
~~~

Nên cụ thể hóa:

~~~yaml
# Ví dụ POLICY MODEL, không phải config Spring có hiệu lực.
trusted_issuer: https://auth.example.test
token_profiles:
  oidc_id_token_for_shop:
    expected_audience: shop-web
    allowed_signing_algorithms: [PS256]
  oauth_jwt_access_token_for_orders:
    expected_audience: orders-api
    expected_typ: at+jwt
    allowed_signing_algorithms: [PS256]
  oauth_client_assertion_billing:
    registered_client: billing-worker
    allowed_signing_algorithms: [PS256]
  dpop_proof:
    allowed_asymmetric_algorithms: [ES256]
~~~

**Mỗi entry phải gắn với thành phần kiểm tra thực tế**. Một allowlist đẹp trong tài liệu không có giá trị nếu mã production vẫn xử lý `alg` từ token bằng thuật toán bất kỳ.

## 19. Quy trình migration thuật toán an toàn theo giai đoạn

Không bật một thuật toán mới và tắt thuật toán cũ trên toàn hệ thống trong cùng thời điểm nếu còn token/các bên nhận chưa tương thích. Một lộ trình có kiểm soát:

### Giai đoạn 0 — Xác định mục tiêu và đường lùi

- Ghi lý do thay thuật toán: security review, compliance, thư viện/HSM mới hoặc chính sách tương thích.
- Xác định **token types**, issuer, RS/RP, Client, key IDs, TTL và đặc tả profile.
- Định nghĩa **thuật toán đích**, điều kiện chấp nhận, risk owner và deadline tắt thuật toán cũ.
- Chốt **rollback plan**: trong hoàn cảnh nào có thể quay về signer cũ; trường hợp khóa đã bị compromise thì **không được rollback sang khóa bị lộ**.
- Thiết kế observability không lộ token/private key.

### Giai đoạn 1 — Chuẩn bị bên xác minh

- Nâng cấp thư viện JOSE/JWT, crypto providers, trust store, KMS/HSM tương thích.
- Cấu hình allowlist **cũ + mới** chỉ ở **issuer/profile cụ thể**, trong thời gian chuyển tiếp.
- Kiểm tra chữ ký, key type, `kid`, issuer/audience/typ/expiration/scope.
- Test malformed, none/HS confusion, unknown kid và dependency failure.
- Triển khai canary/rolling update với monitoring rõ ràng.

### Giai đoạn 2 — Chuẩn bị signing key mới

- Sinh key pair mới trong **KMS/HSM/keystore** được bảo vệ.
- Gán `kid` mới, không tái sử dụng `kid` cũ cho material khác.
- Công bố **public key mới** trong trusted JWKS trước khi AS bắt đầu ký, nếu có thể.
- Để verifier có thời gian refresh cache; giới hạn số key và cache TTL.
- Không đưa private key, `d` hoặc symmetric secret ra JWKS public.

### Giai đoạn 3 — Bắt đầu phát token bằng thuật toán mới

- Cho **canary issuers/clients/regions** nhận token ký bằng alg đích.
- Quan sát tỷ lệ verify success theo thuật toán đã được verify, `kid` và từng RS/RP.
- Tăng dần tỉ lệ traffic, kiểm tra mobile/offline Client và external partners.
- Không dùng "nếu signature PS256 fail thì thử HS256/none" làm fallback.
- Token đã cấp bằng alg cũ còn có thể được verify trong **overlap đã định**, nếu không có compromise.

### Giai đoạn 4 — Ngừng ký cũ, kết thúc overlap

- Ngừng **tạo token mới** bằng algorithm/key cũ.
- Chờ đủ token TTL, skew, cache propagation và consumer lag theo profile; cân nhắc token có thời hạn dài.
- Tắt thuật toán cũ ở **verifier allowlist** khi đã chứng minh không còn token hợp lệ cần nó.
- Gỡ public key cũ khỏi JWKS và xóa/retire private key theo key policy.
- Chặn cấu hình/Client tự bật lại thuật toán cũ mà không có change control.

### Giai đoạn 5 — Hậu kiểm

- Kiểm tra RS chỉ nhận thuật toán đích cho từng issuer/token type.
- Kiểm tra không còn **legacy issuers, signing key, test-only bypass, debug flag** hoặc môi trường staging nhầm production.
- Tổng hợp evidence triển khai, test results, key usage metrics và policy approval.
- Đặt lịch kiểm tra crypto dependencies/key lifecycle trong các phiên bảo trì sau.

## 20. Sơ đồ migration: không đổi signer trước khi verifier sẵn sàng

~~~mermaid
sequenceDiagram
    participant Ops as Security / Platform
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS endpoint
    participant R1 as Orders Resource Server
    participant RP as Shop OIDC Relying Party
    Ops->>R1: Cập nhật allowlist RS256+PS256, issuer/aud/type giữ nguyên
    Ops->>RP: Cập nhật ID-token policy RS256+PS256 nếu profile cần
    Ops->>AS: Sinh signing key B, kid B (PS256)
    AS->>JWKS: Công bố public key A và B
    R1->>JWKS: Refresh key set có giới hạn
    RP->>JWKS: Refresh key set có giới hạn
    Ops->>AS: Bắt đầu ký PS256 bằng B cho profile đã sẵn sàng
    AS-->>R1: JWT access token PS256, kid B
    R1->>R1: Verify PS256 + iss/aud/typ/scope/tenant
    AS-->>RP: ID token PS256 nếu Client registration đã chấp thuận
    RP->>RP: Verify PS256 + OIDC claims/nonce/audience
    Ops->>Ops: Đo token cũ, TTL/cache và consumer compatibility
    Ops->>AS: Ngừng ký RS256/key A
    Ops->>R1: Sau deadline: chỉ cho PS256
    Ops->>RP: Sau deadline: chỉ cho PS256
    AS->>JWKS: Gỡ public key A sau khi hết overlap hợp lệ
~~~

**Không có một thứ tự “tất cả Client trước” áp dụng mọi deployment.** Nếu Client registration chỉ cho một signing alg, cần **điều phối thay registration** trước khi OP thay token algorithm. Khi có nhiều issuer/tenants, chỉ migrate phần nào verifier đã sẵn sàng; đảm bảo token không bị nhận chéo trust domain.

### Tại sao phải tính TTL?

~~~text
T1: AS phát access JWT A bằng RS256, exp=T1+10m.
T2: AS chuyển sang ký PS256, T2=T1+2m.
T3: RS loại RS256 ngay ở T2.

=> JWT A có thể bị từ chối trước hạn dù hợp lệ theo thiết kế cũ.

Trong planned migration (không compromise):
  Giữ RS256 verifier trong cửa sổ kết thúc tính theo
  token TTL + clock skew + propagation/cache lag + safety margin.
~~~

**Không có con số overlap cố định cho mọi hệ thống.** Refresh token có thể tồn tại lâu dài nhưng **không nhất thiết** được ký cùng thuật toán JWT; phải inventory đúng profile và thời gian sống thực tế trước khi chọn mốc loại bỏ.

## 21. Overlap không có nghĩa verifier được “thử mọi khóa”

Một verifier hỗ trợ hai thuật toán trong giai đoạn migration nên có **policy hai nhánh rõ ràng**, không tự tìm mọi đường để cho token qua.

~~~text
Input JWT (chưa tin): protected header alg, kid

Trusted policy cho Orders:
  issuer = https://auth.example.test
  type = at+jwt
  algorithms = {RS256 until retirement, PS256}
  key source = trusted AS JWKS
  required aud = orders-api

Selection:
  1. Header alg có trong allowlist? Không -> reject.
  2. kid trỏ key phù hợp trong JWKS issuer? Không -> bounded refresh/reject.
  3. kty/use/curve/alg khớp? Không -> reject.
  4. Signature verify? Không -> reject.
  5. iss/aud/type/exp/scope/tenant/object? Không -> reject.
~~~

### Những “fallback” cần từ chối

| Khi lỗi | Fallback nguy hiểm | Thay bằng |
|---|---|---|
| PS256 signature fail | Tự thử HS256 với RSA public key. | Từ chối và log mã lỗi an toàn. |
| Unknown `kid` | Tải `jku` bất kỳ từ JWT. | Refresh trusted JWKS có giới hạn rồi reject nếu vẫn unknown. |
| `iss` không khớp | Chỉ so hostname bằng `startsWith`. | Exact issuer trust check theo profile. |
| Thuật toán không được hỗ trợ | Bỏ signature, chỉ decode claims. | Nâng thư viện/hoàn tất migration hoặc fail closed. |
| JWKS endpoint 503 | Tin key từ cache không còn hợp lệ vô hạn. | Dùng cache hợp lệ theo policy; fail closed nếu thiếu key tin cậy. |
| API audience sai | Bỏ audience check để “tương thích”. | Phát token đúng resource/audience. |
| ID token được gửi thay access token | Nhận vì dùng cùng key/alg. | Kiểm tra token purpose, `typ`/claims và audience. |
| Token không có scope | Cho quyền mặc định khi signature đúng. | Áp dụng explicit authorization, mặc định deny. |

### Các ngoại lệ legacy

Nếu một thiết bị IoT cũ không nâng cấp được và vẫn cần RS256, **không mở RS256 cho tất cả issuers/tokens**. Có thể cân nhắc cô lập Client/issuer/RS endpoint, scope và TTL, hạn chế exposure, có owner và ngày khai tử. Nếu rủi ro không thể chấp nhận, giải pháp đúng là **ngừng hỗ trợ** thay vì mở downgrade.

## 22. Emergency key compromise khác planned algorithm migration

Khi **private signing key bị lộ**, attacker có thể ký JWT giả bằng khóa đó. Không thể áp dụng cửa sổ overlap dài như kế hoạch đổi thuật toán thông thường.

### Quy trình ứng phó

1. **Dừng signing bằng key bị lộ**, khóa quyền dùng trong KMS/HSM, bảo vệ bằng chứng.
2. Tạo/activate key mới; nếu thuật toán cũ cũng bị đánh giá yếu, chọn algorithm mới **theo policy**.
3. Cập nhật JWKS/trust policy; **invalidate cache** tại RP/RS càng nhanh càng phù hợp mức rủi ro.
4. Gỡ/deny key bị lộ, không chỉ đổi `kid` nhưng giữ private material cũ.
5. Đánh giá **JWT còn hạn ký bằng key bị lộ**; có thể phải từ chối/cấp lại theo chính sách, ngay cả nếu user gặp gián đoạn.
6. Kiểm tra issuance/audit/RS access logs để xác định token giả/hoạt động trái phép.
7. Xử lý các credentials khác bị ảnh hưởng: refresh token, Client assertion keys, mTLS keys, DPoP keys theo đúng chủ sở hữu.
8. Công bố trạng thái sự cố và xác minh không còn verifier nào nhận compromised key.

~~~mermaid
flowchart TD
    A["Nghi private signing key bị lộ"] --> B["Khoanh vùng issuer, key ID, token types"]
    B --> C["Stop use/key; tạo key mới an toàn"]
    C --> D["Thay trusted JWKS/key policy và purge caches"]
    D --> E["Đánh giá revoke/reissue tokens ký bằng key cũ"]
    E --> F["Theo dõi mọi RS/RP xác minh key mới"]
    F --> G["Điều tra nguồn lộ và audit quyền truy cập key"]
    G --> H["Đóng sự cố sau khi test compromised key bị từ chối"]
~~~

**Một JWT ký bằng compromised key có thể có chữ ký toán học hợp lệ**, nên chỉ kiểm tra signature không phát hiện token giả trong trường hợp này. Cần cập nhật **trust state, key revocation, grant/token policy và điều tra**.

## 23. Multi-issuer, multi-tenant và cross-algorithm confusion

Nền tảng multi-tenant có thể dùng nhiều AS/OP hoặc cùng OP với nhiều issuer path:

~~~text
Tenant A:
  issuer = https://auth.example.test/tenant-a
  signing algorithm = PS256
  key IDs = a-2026-1, a-2026-2

Tenant B:
  issuer = https://auth.example.test/tenant-b
  signing algorithm = ES256
  key IDs = b-2026-1, b-2026-2
~~~

### Không dùng một allowlist quá rộng toàn tổ chức

~~~yaml
# Anti-pattern: policy global không phân token/issuer.
all_jwt_accepted_algorithms: [HS256, RS256, PS256, ES256, EdDSA]
accept_key_from_any_jwks: true
~~~

Thay vào đó:

1. **Trusted issuer registration** được quản trị, không tự trust issuer từ token.
2. Mỗi issuer có key source/JWKS cache **riêng**, allowlist thuật toán, token profiles và thời hạn migration riêng.
3. Kiểm tra `kid` trong **key set của issuer đó**, không chia sẻ global map dựa trên `kid`.
4. Token `iss=A` và `aud=orders-api-B` không tự hợp lệ dù ký bằng thuật toán được hỗ trợ.
5. Không dùng `HS256` với cùng secret cho nhiều tenants/clients trừ khi trust boundaries được đánh giá và chấp thuận.
6. Dữ liệu owner/tenant phải được RS xác minh, không tin header `X-Tenant-Id` caller tự cung cấp.
7. Với OIDC callback nhiều OP, triển khai issuer/authorization-response binding chống AS mix-up.

### Một token có thể hợp lệ về crypto nhưng sai quyền

~~~text
JWT:
  iss = tenant-a OP
  alg = PS256 (được phép)
  signature = valid
  aud = orders-api
  scope = orders:read
  sub = user-123

Order đang yêu cầu:
  owner = user-999
  tenant = tenant-b

=> DENY nếu không có quyền cross-tenant/owner override rõ.
~~~

**Algorithm agility không được làm nới lỏng quyền nghiệp vụ**. Việc thay key signer và thuật toán chỉ giúp token được xác minh mật mã theo cách mới.

## 24. Spring Security: chỉ chấp nhận thuật toán ký JWT đã đăng ký

Ví dụ một **Spring Security Resource Server** nhận JWT access token cho Orders API. Trong cửa sổ migration từ `RS256` sang `PS256`, cấu hình cho phép **đúng hai thuật toán** cho **issuer đã tin**, không thêm `HS256` hoặc `none`.

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
class OrdersAlgorithmMigrationConfig {
    private static final String ISSUER =
            "https://auth.example.test";
    private static final String TRUSTED_JWKS =
            "https://auth.example.test/oauth2/jwks";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder ordersJwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(TRUSTED_JWKS)
                .jwsAlgorithm(SignatureAlgorithm.RS256) // Legacy, temporary
                .jwsAlgorithm(SignatureAlgorithm.PS256) // Target
                .build();

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                            "Incorrect access-token audience", null));
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));
        return decoder;
    }
}
~~~

### Giới hạn và điều kiện sử dụng

- Đây là ví dụ **Spring Security 6-style** khi API `NimbusJwtDecoder.withJwkSetUri` và `jwsAlgorithm` tương ứng được hỗ trợ; dùng phiên bản và dependency thực tế của dự án.
- **`TRUSTED_JWKS` không được lấy từ JWT header hoặc request user**; phải được xác minh khớp trusted issuer/metadata. Ví dụ cấu hình trực tiếp để tránh nhầm source.
- Khi migration xong, **xóa dòng cho phép RS256**, redeploy, kiểm thử và loại key cũ khi đủ điều kiện.
- **Issuer và audience** được kiểm tra tường minh. **Ví dụ chưa triển khai đầy đủ `typ=at+jwt` validation theo RFC 9068, DPoP/mTLS sender proof, scope, tenant và object authorization.** Cần thêm các validator/authorization layer tương ứng.
- Nếu thư viện xử lý `typ` mặc định khác profile access-token, phải thiết lập và kiểm thử type validation đúng theo phiên bản framework, **không tắt luôn token-type checking**.
- Nếu token là **opaque**, không sử dụng `NimbusJwtDecoder` để phân tích một chuỗi opaque.
- Nếu AS bắt đầu phát `ES256` thay vì `PS256`, **không tự thêm ES256 chỉ vì thấy lỗi signature**. Cần change control: policy, key type, curve và khả năng thư viện.

### Sau khi kết thúc migration

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(TRUSTED_JWKS)
        .jwsAlgorithm(SignatureAlgorithm.PS256)
        .build();

// Giữ nguyên validators issuer, audience, type/profile,
// scope và authorization policy đã được kiểm thử.
~~~

**Quan trọng:** Phương thức `jwsAlgorithm` quyết định thuật toán verifier chấp nhận; nó **không** làm AS tự phát token bằng PS256. AS signing configuration phải được triển khai và kiểm chứng riêng.

## 25. Java: policy thuật toán phải được gắn với token profile

Khi cần thêm kiểm soát ở tầng ứng dụng, nên biểu diễn algorithm policy **bằng cấu hình kiểu rõ ràng** thay vì lắp chuỗi khi xử lý request.

~~~java
import java.util.Map;
import java.util.Set;

enum TokenPurpose {
    OIDC_ID_TOKEN,
    OAUTH_ACCESS_TOKEN,
    CLIENT_ASSERTION,
    DPOP_PROOF
}

record TrustedAlgorithmPolicy(
    String issuerOrClientRegistration,
    TokenPurpose purpose,
    Set<String> allowedAlgs
) {
    TrustedAlgorithmPolicy {
        allowedAlgs = Set.copyOf(allowedAlgs);
        if (allowedAlgs.isEmpty()) {
            throw new IllegalArgumentException("No allowed algorithms");
        }
    }

    boolean canAttemptVerification(String untrustedHeaderAlg) {
        // Đây CHỈ là bước loại trước, không phải signature verification.
        return allowedAlgs.contains(untrustedHeaderAlg);
    }
}

final class TokenAlgorithmPolicies {
    static final TrustedAlgorithmPolicy ORDERS_ACCESS =
            new TrustedAlgorithmPolicy(
                "https://auth.example.test",
                TokenPurpose.OAUTH_ACCESS_TOKEN,
                Set.of("PS256")); // Trạng thái SAU migration.

    static final TrustedAlgorithmPolicy SHOP_ID =
            new TrustedAlgorithmPolicy(
                "https://auth.example.test",
                TokenPurpose.OIDC_ID_TOKEN,
                Set.of("PS256"));
}
~~~

### Cách dùng đúng

~~~text
trustedPolicy = resolveTrustedPolicyFromConfiguredEndpointAndTokenPurpose()
untrustedHeader = parseBoundedProtectedHeaderWithoutTrustingClaims()

if not trustedPolicy.canAttemptVerification(untrustedHeader.alg):
    reject

trustedKeys = resolveTrustedKeysForPolicy(trustedPolicy)
verifySignatureWithAllowedAlgorithmAndMatchingKey(trustedKeys, jwt)
validateClaimsAfterSignature(iss, aud, typ, exp, nonce, ...)
authorizeActionOnObjectAndTenant()
~~~

**Đoạn trên là pseudocode sau Java policy class**, không phải code gọi thư viện JOSE. Không lấy `TokenPurpose` từ một `purpose` claim chưa verify rồi coi nó là chính sách tin cậy; resource endpoint và giao dịch OIDC quyết định token purpose trước. Header có thể bị parse để phân luồng sơ bộ nhưng **chưa tạo quyền** cho tới khi signature và claims được validate.

### Tách signing policy và verification policy

~~~yaml
# Policy mô hình, không phải schema framework có sẵn.
issuer:
  name: https://auth.example.test
  signing:
    active_algorithm: PS256
    active_kid: signing-b
  verification:
    allowed_algorithms: [PS256]
  migration:
    legacy_algorithm: RS256
    legacy_acceptance_deadline: disabled
~~~

**Signer** nên có **một thuật toán hiện hành chính xác theo token profile**, còn **verifier** có thể tạm nhận nhiều thuật toán trong cửa sổ migration. Không để signer tự phát token cũ mới tùy header do Client gửi, trừ khi profile registration/migration policy được thiết kế rõ và kiểm thử.

## 26. Quản lý khóa, secret và thư viện theo vòng đời

**Algorithm agility không tách rời key management**. Có thể chọn thuật toán tốt nhưng thất bại nếu private signing key bị commit vào Git, được chia sẻ cho mọi service hoặc tồn tại trong image registry.

### Vòng đời khóa

~~~mermaid
flowchart TD
    A["Chọn algorithm/profile + security level"] --> B["Generate key trong KMS/HSM/keystore"]
    B --> C["Register key ID, usage, owner, activation time"]
    C --> D["Publish đúng public material/trust metadata"]
    D --> E["Activate signer / verifier policy"]
    E --> F["Audit usage, expiration và dependencies"]
    F --> G["Rotate / migrate với overlap có hạn"]
    G --> H["Revoke, retire, destroy private material theo policy"]
~~~

### Quy tắc quản lý

| Loại khóa/secret | Ai nắm material nhạy cảm? | Phải tránh |
|---|---|---|
| **AS JWT signing private key** | KMS/HSM/signing service đáng tin. | Đưa `d`/private key vào public JWKS; cho RS giữ private signing key. |
| **AS JWT public key** | Có thể công bố trong trusted JWKS. | Coi public key là secret HMAC hoặc tải từ header `jku` tùy ý. |
| **Client `private_key_jwt` key** | Confidential Client và keystore của nó. | AS dùng OP JWKS thay Client registration để verify. |
| **Client `client_secret_jwt` HMAC secret** | Client/AS theo mô hình shared secret. | Phân phối cho public SPA, ghi vào log, dùng chung tất cả Clients. |
| **JWE recipient private key** | Recipient giữ để giải mã. | Công bố trong JWK Set public; dùng lại làm signing key bất chấp policy. |
| **DPoP private key** | Client giữ; AS/RS kiểm tra proof/binding. | Đổi key mà không đổi token ràng buộc, log/xuất private material. |
| **TLS/mTLS private key** | Endpoint/load balancer/workload được tin. | Để mọi container dùng một khóa chung không kiểm soát, bỏ hostname validation. |

### Vì sao `kid` và thuật toán không thể thay việc quản lý secret?

`kid` là **identifier do issuer đặt cho khóa**, không có tính chất bảo mật độc lập. Thay `kid=A` thành `kid=B` nhưng **vẫn dùng cùng private key** không loại bỏ tác hại nếu key đó đã lộ. Tương tự, đổi cấu hình `alg` trên giấy mà không bảo đảm HSM đang ký theo thuật toán mới và verifier enforce đúng thì không có migration thực sự.

### Mức độ an ninh và crypto provider

Khi chọn phương án mới, cần xem:

- **Key generation:** CSPRNG/hardware key generation, chính sách kích thước khóa, định dạng/curve được duyệt.
- **Key protection:** quyền ký, rate limits, audit, dual control, non-exportable key nếu khả thi.
- **Algorithm parameterization:** không tự thêm salt/IV/nonce không chuẩn vào JWS; để thư viện JOSE được kiểm chứng quản lý định dạng và tham số.
- **JCA/JCE provider:** thuật toán thật sự hoạt động trên JDK/HSM đã triển khai, không chỉ compile trong IDE.
- **FIPS/compliance requirements:** chỉ dùng thuật toán/provider được policy cụ thể phê duyệt; **không gắn nhãn FIPS cho cả hệ thống chỉ vì alg có tên AES/RSA**.
- **Crypto library maintenance:** version an toàn, test vectors, xử lý `crit` và algorithm/key constraints đúng, có SBOM/vulnerability response.
- **Backup/restore:** khóa khôi phục phải có quyền/retention riêng; restore không được vô tình bật lại khóa đã revoke.

### Tính sẵn sàng trước những đợt thay đổi xa hơn

Cryptographic agility còn hữu ích khi cần thay primitive do tiến bộ mật mã, bao gồm các lộ trình **post-quantum cryptography** trong tương lai. Không tự gắn một tên thuật toán hậu lượng tử chưa được JOSE/OIDC profile và các bên triển khai hỗ trợ vào allowlist production. Đầu tiên cần inventory, threat model, approved profile, interoperability và kế hoạch kiểm thử như mọi đợt migration khác.

## 27. Quan sát vận hành và lỗi triển khai thuật toán

Một migration chỉ hoàn thành khi có thể chứng minh **token mới được phát đúng, các bên nhận xác minh đúng và thuật toán cũ đã hết hiệu lực**.

### Metric nên theo dõi

| Metric/điểm quan sát | Cần trả lời |
|---|---|
| **Signing operation by issuer/profile/algorithm/key version** | AS đang ký bằng thuật toán nào và có còn ký cũ không? |
| **Verified JWT by issuer/profile/alg/`kid`** | RS/RP thực sự chấp nhận alg mới tới đâu? |
| **Rejected JWT: unsupported_algorithm** | Đối tác nào còn dùng thuật toán cũ hoặc attacker đang thử downgrade? |
| **Rejected JWT: signature_invalid** | Có key mismatch, lỗi signing hoặc token bị sửa không? |
| **Rejected JWT: unknown_kid** | JWKS cache/chuyển khóa/DoS có vấn đề không? |
| **Rejected JWT: issuer/audience/type_invalid** | Migration có vô tình làm hỏng chính sách authn/authz không? |
| **JWKS fetch/cache age/error** | Verifier có key mới và trusted source ổn định không? |
| **Token age/time-to-expiry per legacy algorithm** | Còn bao nhiêu token cũ hợp lệ cần overlap? |
| **KMS/HSM signing failure/latency** | Thuật toán mới gây lỗi vận hành hoặc tăng tải không? |
| **Legacy algorithm accepted after deadline** | Có node/tenant chưa xóa allowlist cũ không? |

### Log đúng cách

~~~json
{
  "event": "jwt.verification",
  "trusted_issuer": "https://auth.example.test",
  "token_profile": "orders-access-token",
  "claimed_alg": "PS256",
  "matched_key_version": "signing-b",
  "verification_result": "rejected",
  "reason": "invalid_audience",
  "deployment": "orders-rs-v42",
  "correlation_id": "verify-event-314"
}
~~~

**`claimed_alg` là thông tin từ header chưa tin** nếu token verify thất bại. Khi dùng nó để thống kê, phải **giới hạn chiều dài/nhóm giá trị**, không để attacker tạo hàng triệu label Prometheus bằng chuỗi `kid`/`alg` tùy ý. Tránh log raw JWT, ID/access/refresh token, Client secret, DPoP private key, authorization code hoặc session cookie.

### Những điều số liệu không tự chứng minh

- **`JWKS fetch 200`** không có nghĩa JWKS thuộc trusted issuer hoặc có đúng private-key pair đang ký.
- **`signature_success`** không có nghĩa audience, token type, scope, owner/tenant đúng.
- **`0 RS256 tokens today`** không chứng minh hết token cũ ở thiết bị offline nếu token TTL dài hoặc log thiếu vùng.
- **`AS already signs PS256`** không chứng minh toàn bộ RP/RS đã đủ thuật toán mới.
- **`key removed from JWKS`** không chứng minh mọi verifier đã purge cache hoặc không còn pin key cũ.

### Khi JWKS không truy cập được

Verifier có thể sử dụng **cached public keys còn hợp lệ theo policy**, nhưng không được:

~~~text
JWKS timeout -> skip signature check
unknown kid -> accept payload if exp looks fresh
invalid signature -> retry against unrelated key URLs
~~~

Nếu không còn cơ sở xác minh an toàn, cần **fail closed** với thông báo lỗi phù hợp và bảo đảm hệ thống có cơ chế recovery/availability rõ ràng. Đừng tự giữ cached key bị thu hồi vô hạn.

## 28. Ma trận kiểm thử Algorithm agility

Giả sử AS `https://auth.example.test` chuyển JWT access token cho `orders-api` từ `RS256/key-A` sang `PS256/key-B`; dự kiến kết thúc overlap tại T4. OIDC Client `shop-web` được cập nhật signing-alg policy tương ứng. Mỗi test dưới đây cần sử dụng **JWT test data có chữ ký thật hoặc bị sửa có chủ đích**, không chỉ decode payload.

| # | Kịch bản | Kết quả mong đợi | Mục tiêu |
|---|---|---|---|
| 1 | JWT `RS256`, đúng A, trước migration | Verify nếu issuer/aud/type/claims hợp lệ. | Baseline. |
| 2 | JWT `PS256`, đúng B, trước khi verifier sẵn sàng | Từ chối; không bỏ verify. | Migration ordering. |
| 3 | Public key B được công bố trước khi AS ký | Verifier có thể preload/cache B. | JWKS staging. |
| 4 | Trong overlap, JWT hợp lệ RS256/A | Chỉ chấp nhận trong phạm vi/deadline policy. | Controlled compatibility. |
| 5 | Trong overlap, JWT hợp lệ PS256/B | Chấp nhận nếu claims và profile đúng. | New algorithm. |
| 6 | Sau T4, JWT RS256/A chưa hết `exp` nhưng policy đã tắt | Từ chối theo chính sách mới, kiểm tra kế hoạch TTL. | Retirement enforcement. |
| 7 | Sau T4, JWT PS256/B hợp lệ | Chấp nhận theo policy. | Post-migration baseline. |
| 8 | JWT header `alg=none` | Từ chối trong profile yêu cầu signed token. | Unsigned JWT attack. |
| 9 | JWT header `alg=HS256` với RSA public key làm HMAC secret | Từ chối. | RSA/HMAC confusion. |
| 10 | JWT header `alg=rs256` viết sai case | Từ chối nếu không đúng registry/allowlist. | Strict alg matching. |
| 11 | JWT alg không nằm trong allowlist, dù signature được tạo đúng với alg đó | Từ chối. | Policy precedence. |
| 12 | JWT đổi header `alg=PS256` nhưng vẫn ký RS256 | Từ chối. | Header tamper/mismatched signature. |
| 13 | `kid` không tồn tại | Bounded trusted JWKS refresh/reject, không fail-open. | Unknown key handling. |
| 14 | Hàng nghìn `kid` ngẫu nhiên | Rate-limit/collapse refresh, không DoS. | Unknown-kid flood. |
| 15 | JWT trỏ `jku` đến attacker host | Không tin/fetch URL ngoài policy; từ chối token giả. | Key substitution. |
| 16 | JWT `x5u` trỏ metadata IP nội bộ | Không SSRF/tự tải. | Network trust boundary. |
| 17 | JWKS chứa JWK `use=enc` nhưng JWT ký `PS256` | Từ chối dùng khóa sai mục đích. | Key usage separation. |
| 18 | JWK `kty=EC` nhưng JWT `alg=PS256` | Từ chối. | Key type/algorithm binding. |
| 19 | JWK `crv=P-384` nhưng JWT `alg=ES256` | Từ chối theo mapping profile. | Curve constraint. |
| 20 | JWKS có hai signing keys trùng `kid` gây mơ hồ | Không chọn phần tử tùy ý. | Deterministic selection. |
| 21 | Issuer A/B có cùng `kid` | Mỗi token chỉ được verify bằng keys issuer của chính nó. | Multi-issuer isolation. |
| 22 | `iss` của JWT khác exact trusted issuer | Từ chối. | Issuer validation. |
| 23 | JWT access token có `aud=billing-api` gửi Orders | Từ chối. | Audience check. |
| 24 | OIDC ID token `aud=shop-web` gửi Orders | Từ chối dù signature đúng. | Cross-JWT confusion. |
| 25 | JWT access token có `typ` sai profile RFC 9068 | Từ chối theo profile RS. | Token type enforcement. |
| 26 | JWT đúng issuer/aud/alg nhưng `exp` đã hết | Từ chối. | Expiration validation. |
| 27 | JWT đúng issuer/aud/alg nhưng thiếu `orders:read` | Từ chối thao tác đọc. | Scope policy. |
| 28 | JWT đúng scope nhưng order khác tenant | Từ chối. | Object/tenant authorization. |
| 29 | JWT có `crit` extension mà thư viện không hiểu | Từ chối. | JOSE critical headers. |
| 30 | JWT JWS `b64=false` mà profile không hỗ trợ | Từ chối thay vì parse mơ hồ. | Unencoded payload profile. |
| 31 | JWKS endpoint trả JSON sai cấu trúc hoặc rất lớn | Bounded parse/reject, không crash/DoS. | Robustness. |
| 32 | JWKS endpoint TLS certificate sai | Không bỏ certificate validation. | Transport trust. |
| 33 | JWKS 503 với key còn trong cache hợp lệ | Chỉ dùng cache theo policy, không tin khóa mới. | Resilience. |
| 34 | JWKS 503 với unknown key | Từ chối token. | Fail closed. |
| 35 | AS phát PS256 nhưng một RS chỉ biết RS256 | RS từ chối; phát hiện canary trước rollout rộng. | Compatibility. |
| 36 | AS đã ngừng ký RS256 nhưng RP vẫn cho phép mãi | Cảnh báo vi phạm deadline, sửa policy. | Eliminate legacy acceptance. |
| 37 | Private signing key A bị lộ khi overlap | Emergency revoke/purge cache, không giữ A vì TTL planned. | Compromise response. |
| 38 | KMS PS256 key lỗi signing nhưng hệ thống tự đổi `alg=none` | Không được phép; fail closed/failover an toàn. | Unsafe fallback. |
| 39 | `private_key_jwt` Client A có key đúng nhưng assertion `aud` sai | AS từ chối. | Client authentication policy. |
| 40 | Client A assertion được verify bằng key Client B | AS từ chối. | Client key isolation. |
| 41 | DPoP proof dùng `HS256` | Từ chối theo proof profile. | Asymmetric alg requirement. |
| 42 | DPoP proof valid nhưng JWK không khớp `cnf.jkt` | Từ chối. | Token-key binding. |
| 43 | DPoP proof valid nhưng `htu`/`htm`/`ath` sai | Từ chối. | Request binding. |
| 44 | JWE `alg`/`enc` ngoài allowlist | Từ chối giải mã theo profile. | Encryption agility. |
| 45 | JWE tag sai hoặc nonce policy vi phạm | Từ chối/đánh dấu lỗi; không xuất plaintext. | Authenticated encryption. |
| 46 | JWE recipient decryption key bị công bố public | Incident + key revoke/rotation. | Private key secrecy. |
| 47 | mTLS-bound access token có cert thumbprint không khớp | RS từ chối dù JWT signature hợp lệ. | Sender binding. |
| 48 | Client Credentials token ký hợp lệ nhưng Client đã bị disable | Kiểm tra policy/trạng thái theo yêu cầu, không tự tái cấp grant. | Token lifecycle. |
| 49 | Opaque access token gửi tới JWS decoder | Không decode giả; dùng introspection nếu token profile đó được phép. | Token format distinction. |
| 50 | Hai phiên deployment có alg policy khác sau migration | Test phát hiện và sửa cấu hình không đồng nhất. | Rollout consistency. |

### Cách làm test chất lượng

1. **Tách positive/negative test fixtures** theo issuer, profile, alg, key ID và expiration.
2. Tạo JWT test token bằng thư viện JOSE được tin cậy; khi kiểm tra invalid signature/alg tampering, **chỉ dùng trong môi trường kiểm thử cách ly**.
3. Chạy qua **AS signing pipeline, RP/RS verifier, JWKS cache, KMS/HSM integration**; không chỉ unit test một method Java.
4. Đo **signing/verification success, rejected reasons, latency, cache refresh, TTL** trước, trong và sau migration.
5. Kiểm tra policy của **mỗi region/tenant/deployment**, kể cả mobile/offline/partner Client.
6. Test rollback **chỉ** với keys/algorithms vẫn được đánh giá an toàn; không thiết kế rollback khôi phục compromised keys.
7. Ghi kết quả kiểm thử mà **không lưu raw tokens, secrets, private keys hoặc Authorization headers** vào CI/artifact.

## 29. Tình huống tự luyện

**Tình huống A — “Đọc `alg` rồi tự xác minh.”** API nhận JWT chứa `alg=HS256`, trong khi AS được đăng ký ký `RS256`. Developer muốn thay thuật toán verifier theo header để linh hoạt. Sai ở đâu?

**Giải thích:** Header token là input chưa đáng tin. Verifier phải có allowlist/đúng key type theo trusted issuer/profile. Chấp nhận HS256 tùy header có thể tạo RSA/HMAC confusion.

**Tình huống B — `alg=none`.** Một JWT không có signature nhưng chứa `sub=admin` và `scope=orders:write`. Parser decode được. Có nên tin?

**Giải thích:** Không. Nếu profile yêu cầu chữ ký, token unsigned phải bị reject; decode payload không tạo bằng chứng issuer hay quyền.

**Tình huống C — Migration RS256 → PS256.** OP đã bắt đầu ký PS256, nhưng một Resource Server chưa nâng cấp nên trả 401. Có nên tắt kiểm tra chữ ký vài ngày?

**Giải thích:** Không. Cần điều phối verifier readiness trước signer cutover, hoặc quay lại cách ký an toàn theo rollback có kiểm soát khi key chưa bị compromise. Không cho token không verify.

**Tình huống D — Public JWKS đã chứa key mới.** Token có `kid=B` nhưng chữ ký được tạo bằng private key A. JWK B có trong JSON nên có được nhận?

**Giải thích:** Không. `kid` chỉ giúp chọn khóa; chữ ký phải verify bằng key tương ứng thực sự. Key metadata không thay signature validation.

**Tình huống E — Hai issuer chung `kid`.** Tenant A và B cùng dùng `kid=key1`, nhưng khác key. API cache khóa theo `kid` toàn cục. Nguy cơ?

**Giải thích:** Cross-issuer key confusion, nhận nhầm hoặc từ chối token không ổn định. Cache/key selection phải tách theo trusted issuer/trust domain.

**Tình huống F — Alg cũ được giữ vô hạn.** Sau sáu tháng, mọi token mới đã ký PS256 nhưng verifier vẫn chấp nhận RS256 trên toàn hệ thống. Đã xong agility chưa?

**Giải thích:** Chưa. Migration phải có deadline, bằng chứng token cũ hết thời hạn và loại algorithm/key cũ khỏi allowlist. Hỗ trợ alg cũ vô hạn tăng attack surface.

**Tình huống G — Key bị lộ.** Private key A dùng RS256 bị đánh cắp, nhưng team muốn giữ public key A trong JWKS đến khi JWT cũ hết hạn. Có phù hợp?

**Giải thích:** Không nên áp dụng planned overlap như bình thường. Phải kích hoạt incident response, thu hồi key/trust, purge cache, đánh giá revoke/reissue JWT và điều tra.

**Tình huống H — ID token gọi API.** Token có issuer/signature PS256 hợp lệ nhưng `aud=shop-web`, Client dùng để gọi Orders API `aud=orders-api`. Kết quả?

**Giải thích:** Orders phải từ chối. Dùng cùng issuer/JWKS/alg không đổi ID token thành access token.

**Tình huống I — DPoP proof có khóa riêng.** Attacker tự tạo DPoP key, ký proof hoàn hảo rồi trình kèm access token DPoP-bound của người khác. Có hợp lệ?

**Giải thích:** Không, vì public key/thumbprint của proof phải khớp binding `cnf.jkt` của access token và các claims request/nonce/replay checks phải đúng.

**Tình huống J — Client assertion sai nguồn key.** AS verify `private_key_jwt` bằng OP JWKS thay vì public key của Client đã đăng ký. Có đúng?

**Giải thích:** Không. JWT client assertion được ký bởi Client; AS phải xác minh bằng Client keys/registration và các claims audience/issuer/subject phù hợp.

**Tình huống K — Chuyển JWE `enc`.** Một team đổi từ cơ chế content encryption cũ sang `A256GCM`, nhưng chỉ thay chuỗi header `enc` và giữ ciphertext/tag cũ. Có đúng?

**Giải thích:** Không. JWE encryption algorithm phải được **thực thi thực tế** với key/nonce/tag format tương ứng; thay header không biến ciphertext sang thuật toán khác.

**Tình huống L — JWT signature đúng, tenant sai.** JWT `PS256` hợp lệ, `scope=orders:read` nhưng user xin order thuộc tenant khác. Có trả dữ liệu không?

**Giải thích:** Không nếu thiếu cross-tenant authorization. Algorithm agility không miễn kiểm tra owner/tenant/object.

**Tình huống M — JWKS 503.** Token có `kid` lạ, AS JWKS endpoint không truy cập được. Kỹ sư đề xuất nhận token rồi kiểm tra sau. Có nên?

**Giải thích:** Không. Không có trusted key để verify thì phải từ chối hoặc xử lý availability theo policy; không cho phép request đi qua với claims chưa xác minh.

**Tình huống N — FIPS.** Một tổ chức bật alg `EdDSA` vì hiệu năng, nhưng môi trường HSM/JCA/compliance chưa có profile được chấp thuận. Có đưa thẳng production không?

**Giải thích:** Không. Cần xác minh requirements, provider hỗ trợ, interoperability, test vectors, audit và phê duyệt trước migration.

**Tình huống O — Rollback gặp compromised key.** Thuật toán mới gây tăng lỗi 401. Key cũ đã bị lộ trong incident tuần trước. Có thể quay lại key cũ không?

**Giải thích:** Không. Rollback phải chỉ dùng **khóa/thuật toán còn an toàn**. Nếu không có phương án an toàn, chọn fail-closed/khôi phục bằng key mới khác và xử lý availability.

**Tình huống P — Public RSA key bị dùng làm HMAC secret.** Một developer nói “public key vốn công khai nên có thể dùng làm HMAC secret”. Sai ở đâu?

**Giải thích:** HMAC yêu cầu **secret chỉ bên được phép nắm giữ**; RSA public key công khai, nên nếu verifier dùng nó làm HMAC key, attacker có thể tạo MAC tương ứng. Phải ràng buộc `HS*` với secret mạnh và `RS*/PS*` với RSA key đúng kiểu.

## Checklist triển khai Algorithm agility

1. **Inventory đầy đủ:** AS/OP, RP, RS, Client assertions, DPoP, JWE, TLS/mTLS, HSM/KMS, key sizes, thư viện và đối tác.
2. **Xác định token profiles:** ID token, JWT access token, opaque access token, Client assertion, DPoP proof và logout token; không dùng một verifier cho mọi JWT.
3. **Chốt trust anchor:** trusted issuer, Client registration và key source đáng tin, exact issuer matching.
4. **Pin allowlist theo issuer/profile:** `alg` của JWT chỉ được chọn trong allowlist, không bật theo header chưa verify.
5. **Chống `alg=none`/RS↔HS confusion:** chữ ký bắt buộc, kiểm tra key type/algorithm, không coi public key là symmetric secret.
6. **Chống key injection:** `kid` chỉ chọn trong đúng key set, không theo `jku`/`x5u` tùy ý; giới hạn JWKS refresh và SSRF.
7. **Kiểm tra JWK constraints:** `kty`, `use`, `key_ops`, `alg`, curve, key size, `kid` uniqueness, private-material protection.
8. **Tách signing, encryption và transport:** JWS `alg` khác JWE `alg`/`enc` và TLS algorithms; kiểm thử từng lớp.
9. **Tách khóa theo vai trò:** AS signing key, Client assertion key, JWE decryption key, DPoP key và mTLS private key.
10. **Bảo toàn validation:** verify signature, issuer, audience, token type, thời gian, nonce/claims theo profile, scope và object/tenant authorization.
11. **Lập migration plan có deadline:** verifier readiness trước signer cutover, canary, publish-new-key-before-sign, planned overlap hữu hạn.
12. **Không downgrade để khắc phục sự cố:** token sai alg/kid/signature/JWKS thì reject theo policy; không fallback unsigned/HS/public-key confusion.
13. **Quản lý key lifecycle:** CSPRNG/KMS/HSM, non-exportability khi phù hợp, activation, key ID, audit, rotation, revocation và destruction.
14. **Quản lý cached JWKS:** TTL/ETag, unknown-kid refresh rate limit, fail closed khi thiếu key, purge khẩn cấp khi key compromise.
15. **Theo dõi từng consumer:** verified alg/`kid` theo issuer/token type/region, legacy usage, cache failure, authorization regression.
16. **Không bật alg cũ vô hạn:** tắt signer cũ, chờ token TTL/clock skew hợp lệ, loại khỏi allowlist, gỡ public key cũ.
17. **Incident khác planned migration:** private key lộ cần revoke/purge/trust update sớm, không chờ overlap theo lịch.
18. **Cô lập multi-tenant:** key cache và policy theo trusted issuer, grant/client/tenant, không dùng `kid` hoặc `alg` làm định danh toàn cục.
19. **Kiểm tra Client/RS compatibility:** library/JDK/HSM, mobile/IoT, external consumers, compliance, TLS và encrypted-token recipients.
20. **Kiểm thử đường âm tính:** none/HS confusion, bad iss/aud/typ, duplicate kid, jku SSRF, invalid signature, JWE tag, DPoP binding, key compromise.
21. **Vận hành không lộ credential:** log metadata đã giới hạn, không lưu raw JWT, refresh token, Client secret hoặc private key vào tracing/CI.
22. **Chỉ tuyên bố hoàn tất sau kiểm chứng:** mọi RS/RP đúng policy, không còn ký/nhận alg cũ ngoài exception có kiểm soát, quyền nghiệp vụ không bị nới.

## Ghi nhớ

**Algorithm agility là khả năng chuyển thuật toán mật mã có kiểm soát, không phải chấp nhận mọi giá trị `alg` do JWT tự khai.** Đối với OAuth 2.0/OIDC, chính sách phải gắn với **trusted issuer, token purpose, Client/Resource Server, thuật toán và loại khóa**, rồi mới dùng `kid`/JWK/JWKS để xác minh chữ ký. Phải chặn **`alg=none` ngoài profile, RS256↔HS256 confusion, `jku`/`x5u` key substitution, SSRF, cross-issuer/cross-JWT confusion và downgrade kéo dài**. Key rotation, algorithm migration, JWE encryption agility, DPoP Client proof và mTLS có vòng đời **khác nhau**. Một đợt chuyển đổi tốt có **inventory, allowlist, triển khai verifier trước signer, công bố public key, overlap hữu hạn, telemetry, test âm tính, deadline loại thuật toán cũ và phương án xử lý compromised key**. Sau cùng, **chữ ký/thuật toán hợp lệ chưa chứng minh token đúng audience, scope, còn hiệu lực hay người dùng được phép truy cập object/tenant đó**.

### Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7638 — JSON Web Key Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797)
- [RFC 8037 — CFRG Elliptic Curve Algorithms for JOSE](https://www.rfc-editor.org/rfc/rfc8037)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [OpenID Connect Core 1.0 — ID Token, client auth và thuật toán](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0 — Provider metadata và JWKS URI](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OWASP — JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [OWASP — OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
