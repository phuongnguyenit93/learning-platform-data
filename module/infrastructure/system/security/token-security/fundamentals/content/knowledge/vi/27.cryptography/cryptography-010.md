# Key compromise

## 1. Một khóa bị lộ có thể phá vỡ mô hình tin cậy token như thế nào?

Trong chương **Cryptography** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, **key compromise** là tình huống bí mật mật mã hoặc khả năng sử dụng khóa bị một chủ thể không có thẩm quyền chiếm được. Với token security, sự cố này không chỉ là “mất một chuỗi bí mật”: nó có thể khiến một **Authorization Server (AS)/OpenID Provider (OP)** bị giả mạo, một **client** không hợp lệ được chấp nhận, hoặc một **Resource Server (RS)** tiếp tục tin những token do kẻ tấn công tạo ra.

Hãy xét hệ thống Shop:

~~~text
                          Ký JWT bằng private key K1
Authorization Server  -----------------------------------+
                                                        |
                                                        v
                                             JWT Access Token T1
                                                        |
                                                        v
Orders API / Billing API  <-- JWKS chứa public key K1 để kiểm chữ ký
~~~

Khi khóa **private K1** bị đánh cắp, attacker có thể tạo JWT mới có chữ ký hợp lệ tương ứng với public key K1. Nếu API chỉ kiểm chữ ký, issuer, audience, `exp` và scope mà chưa nhận thông báo ngừng tin K1, nó có thể chấp nhận token giả.

Ví dụ payload JWT do attacker **có khả năng tự chọn** sau khi chiếm khóa ký:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "victim-user-42",
  "aud": ["https://orders.example.com"],
  "scope": "orders:read orders:write",
  "iat": 1893492000,
  "exp": 1893495600,
  "jti": "attacker-minted-001"
}
~~~

Đây chỉ là payload minh họa, **không phải một JWT hoàn chỉnh**. Điểm nguy hiểm là với signing key thực bị compromise, attacker có thể tạo chữ ký mà RS thông thường xem là hợp lệ, kể cả khi AS **chưa từng phát hành** token với các claims trên.

**Một chữ ký mật mã hợp lệ chứng minh token được ký bằng khóa tương ứng, không chứng minh khóa đó vẫn do đúng issuer kiểm soát.** Khi signing key đã bị compromise, **trust anchor** đã mất, nên chỉ kiểm chữ ký không còn đủ.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **khóa ký (signing)**, **khóa xác minh (verification)**, **khóa mã hóa (encryption)**, **HMAC shared secret**, khóa **client authentication**, **DPoP**, **mTLS** và các loại secrets khác.
2. Giải thích vì sao lộ **public verification key** bình thường không giống lộ **private signing key**.
3. Xác định blast radius của khóa JWT/ID token, opaque token, refresh token, client assertion và sender-constrained token theo từng kiến trúc.
4. Phân biệt **planned key rotation** với **emergency compromise response**.
5. Xử lý JWKS, `kid`, algorithm allowlist, RS cache và revocation propagation an toàn.
6. Thiết kế key lifecycle với KMS/HSM, least privilege, audit, backup, rotation, separation of duties và khôi phục sau sự cố.
7. Hiểu vì sao token vẫn có thể được API chấp nhận **sau khi AS xóa khóa khỏi JWKS**.
8. Đề xuất ví dụ Java/Spring Security và kiểm thử incident nhiều node/region.

## 2. Mô hình khóa và ba ranh giới tin cậy

### 2.1. Authentication, authorization và cryptography là ba lớp khác nhau

Đối với một JWT access token, RS thường cần:

~~~text
Cryptographic verification:
    Chữ ký/thuật toán/khóa có hợp lệ?

Token validation:
    iss, aud, exp, nbf, token type, scope và profile đúng?

Business authorization:
    Principal có thể làm action này trên resource/tenant này không?
~~~

Lộ signing key làm hỏng **cryptographic verification trust**. Các lớp issuer/audience/role nằm **bên trong JWT mà attacker có thể ký giả** có thể không cứu được hệ thống nếu chúng chỉ dựa trên chính token giả.

Tuy nhiên business policy **dựa trên nguồn độc lập đáng tin**—ví dụ owner/tenant được kiểm tại database—vẫn có thể giới hạn một số hành vi. Đây là defense in depth, **không phải** lý do giữ tin khóa đã lộ.

### 2.2. JWS, JWE, JWT và opaque token

| Khái niệm | Vai trò | Rủi ro key compromise điển hình |
|---|---|---|
| **JWS** | Chữ ký/MAC bảo vệ tính toàn vẹn và nguồn của claims | Lộ khóa ký/MAC có thể cho phép tạo chữ ký/token giả |
| **JWT** | Định dạng claims; thường được bảo vệ bằng JWS, có thể là JWE | Phụ thuộc khóa/thuật toán/profile được sử dụng |
| **JWE** | Mã hóa nội dung token | Lộ khóa giải mã có thể khiến claims bí mật bị lộ; không tự suy ra khả năng ký giả |
| **Opaque access token** | Chuỗi không tự mô tả đối với RS | Rủi ro tùy token store, token generator, introspection và secrets |
| **Refresh token** | Credential xin token mới tại AS | Rủi ro khi token bị đánh cắp hoặc secret dùng kiểm/chấp nhận bị lộ |
| **ID token OIDC** | Khẳng định xác thực dành cho Relying Party | Lộ khóa ký OP có thể cho phép giả ID token nếu RP còn tin khóa |

**JWT không tự đồng nghĩa với mã hóa.** Payload của một JWS compact JWT thường có thể đọc được qua Base64url; việc chữ ký hợp lệ không bảo đảm tính bí mật.

### 2.3. Signing key và verification key

Với thuật toán bất đối xứng:

~~~text
AS / OP:
    private signing key K1_private    => phải giữ bí mật.

RS / RP:
    public verification key K1_public => được phân phối qua JWKS.
~~~

Một public key được công bố trong JWKS là **chủ đích thiết kế**, không phải sự cố “lộ khóa” chỉ vì ai cũng tải được. Attacker có public key **không vì thế tạo được chữ ký RS256/ES256/EdDSA hợp lệ**.

Ngược lại, khi **private signing key** bị lộ, mọi verifier đang tin public key tương ứng có thể bị tấn công bằng token giả.

### 2.4. HMAC khác bất đối xứng

Với `HS256`, cùng một bí mật HMAC được dùng để **ký và xác minh**. Nếu RS nào cũng giữ secret này để validate, việc một RS bị xâm nhập có thể khiến attacker có năng lực **tạo token mới**.

~~~text
Asymmetric signing (RS256 / ES256 / EdDSA):
    AS giữ private key.
    RS giữ public key.

Symmetric MAC (HS256):
    AS và RS cùng biết secret.
    Bất kỳ bên giữ secret bị compromise đều có thể tạo MAC.
~~~

Trong kiến trúc nhiều Resource Servers thuộc các trust domains khác nhau, dùng asymmetric signing thường giúp **giảm phạm vi bí mật cần chia sẻ**. Đừng dùng secret HS256 yếu, hardcode trong source, hoặc gửi cho các đối tác chỉ để họ tự verify access token.

## 3. Những loại khóa có thể bị compromise trong OAuth 2.0/OIDC

Không phải mọi “key compromise” đều có cùng tác động; trước khi ứng cứu phải xác định **khóa nào, mục đích gì, nằm ở đâu và được tin bởi ai**.

| Loại khóa/bí mật | Ai thường giữ | Nếu bị lộ/chiếm quyền sử dụng |
|---|---|---|
| **AS JWT signing private key** | AS/KMS/HSM | Có thể ký JWT/ID token giả cho những verifiers tin khóa |
| **HS256 shared secret** | AS và các verifiers được cấp secret | Bất kỳ bên giữ secret có thể tạo MAC hợp lệ |
| **JWE encryption/decryption key** | Bên mã hóa/giải mã theo profile | Có thể giải mã claims hoặc giả token mã hóa tùy cấu trúc khóa/chế độ |
| **OAuth client secret** | Confidential client/AS | Có thể giả mạo client ở những endpoints dùng secret; không phải AS signing key |
| **`private_key_jwt` client private key** | Confidential client | Có thể tạo client assertions giả cho client đó |
| **DPoP holder private key** | Client/thiết bị | Có thể tạo DPoP proofs; tăng rủi ro dùng token ràng buộc với khóa |
| **mTLS client private key** | Client/thiết bị hoặc HSM | Có thể giả mạo client nếu cert còn được chấp nhận và có khả năng sử dụng khóa |
| **TLS server private key** | Reverse proxy/service endpoint | Có thể cho phép giả server trong điều kiện thích hợp; không mặc định giải mã mọi traffic TLS lịch sử |
| **Session signing/encryption secret** | RP/BFF | Có thể giả/đọc cookie hoặc state theo cách framework dùng secret |
| **Opaque token MAC/derivation secret** | AS/issuer | Tác động tùy opaque token format; có thể cho phép tạo/kiểm token giả nếu token tự xác thực bằng MAC |
| **Refresh token storage/verifier secret** | AS/token store | Có thể gây rủi ro xác minh hoặc liên kết token; không tự suy mọi random token đều bị khôi phục |
| **KMS credential/IAM role** | Service principal | Có thể có quyền ký/giải mã qua KMS dù private key không export được |

### 3.1. Compromise về *khả năng ký* không nhất thiết là lấy được private key

Attacker có thể chiếm:

- Một bản sao **private key** trên đĩa/backup hoặc secret store.
- Credential/IAM cho phép gọi **KMS Sign** bằng khóa không export được.
- Pipeline deploy để thay **JWKS public key** hoặc trust configuration.
- Máy chủ AS để ký token qua API nội bộ.
- Admin console cho phép phát hành grant/claim bất hợp lệ mà không cần truy cập trực tiếp key bytes.

Các trường hợp có tác động gần nhau ở RS nhưng **đường khắc phục khác nhau**. Chỉ rotate file private key sẽ không đủ nếu attacker vẫn có IAM permission ký hoặc quyền chỉnh trust metadata.

### 3.2. Tác động phụ thuộc *khóa dùng ở đâu*, không chỉ nhãn `kid`

Một signing key có thể đã bị tái sử dụng cho:

~~~text
Key K1:
    issuer A access tokens
    issuer A ID tokens
    issuer B tokens (sai isolation)
    client assertions (sai key separation)
~~~

Blast radius có thể lớn hơn những gì JWKS hiện tại hiển thị. Cần điều tra **key fingerprint/material**, issuers, audiences, environments, services và lịch sử version; không chỉ tìm token có `kid="K1"`.

### 3.3. `kid` là tham chiếu, không phải bằng chứng đáng tin

Trong JWS header:

~~~json
{
  "alg": "RS256",
  "kid": "issuer-2026-11",
  "typ": "at+jwt"
}
~~~

`kid` giúp verifier chọn khóa trong **trusted key set**. Attacker có thể tự đặt `kid` trong header JWT giả; vì vậy:

- Không tự động fetch bất kỳ URL `jku`, `x5u` do JWT chưa xác minh khai báo.
- Không chọn issuer/trust root dựa trên `kid` của token không tin cậy.
- Không coi `kid` duy nhất toàn internet; namespace theo issuer/key set.
- Không cho `alg` của token tùy ý chuyển từ RS256 sang HS256/`none`.
- Không sử dụng `kid` làm cách duy nhất xác định khóa bị lộ nếu cùng key material tồn tại dưới nhiều ID.

**Thu hồi trust phải nhắm tới đúng key material/issuer/key versions**, kết hợp `kid` khi thích hợp, không chỉ blacklist một chuỗi header có thể bị đặt lại.

## 4. Khả năng tấn công khi signing key của issuer bị lộ

### 4.1. Token forgery khác token theft

**Token theft**: attacker lấy một access token T1 đã phát hành rồi sử dụng lại trong thời hạn/phạm vi của T1. **Key compromise**: attacker có thể **tạo nhiều token mới**, tự chọn `sub`, `scope`, `aud`, `iat`, `exp`, `jti`, nếu các điều kiện cryptographic và claims verification của RS không có bảo vệ độc lập.

~~~text
Theft:
    Attacker giữ bản sao T1.
    Hành vi thường bị giới hạn bởi claims/TTL của T1.

Signing key compromise:
    Attacker có năng lực ký token T2, T3, T4...
    Có thể giả claims trong trust domain của key K1.
~~~

Với signing key đã bị compromise, **không thể phân biệt chắc token do AS ký hay attacker ký chỉ bằng cách kiểm chữ ký K1**. Những log phát hành của AS có thể giúp đối chiếu, nhưng chỉ nên được dùng như **nguồn chứng cứ độc lập** khi chúng đáng tin cậy và đầy đủ.

### 4.2. Vì sao kiểm `iss`, `aud`, `exp` vẫn chưa đủ?

Khi RS chỉ kiểm các claims được ký bằng K1, attacker có thể điền các giá trị hợp lệ:

~~~text
iss = issuer mà RS tin.
aud = Orders API.
scope = orders:write.
exp = thời điểm còn hạn.
sub = nạn nhân hoặc service principal bị giả.
~~~

RS thấy claims “đúng dạng” và chữ ký K1 “đúng”, nhưng **nguồn ký K1 không còn độc quyền của AS**.

Một kiểm soát **độc lập** như đối chiếu grant/token ID với state issuer được bảo vệ có thể giúp phát hiện token chưa từng phát hành; tuy nhiên nó cần được thiết kế để chống giả ID, stale cache và mất tính toàn vẹn của state store.

### 4.3. `iat` không chứng minh token có trước thời điểm compromise

Giả sử phát hiện K1 bị lộ lúc 10:00 và RS định chặn JWT với:

~~~text
iat >= 10:00 => DENY.
iat <  10:00 => ALLOW.
~~~

**Sai** nếu `iat` chỉ là claim do K1 ký: attacker có private K1 có thể **ký token mới với `iat=09:00`**. Tương tự, `jti` tự khai không chứng minh token đã được AS phát hành.

Chỉ có thể dùng ranh giới thời điểm khi kết hợp **issuance provenance độc lập/authoritative allowlist** hoặc một cơ chế xác minh state không thể bị attacker tự tạo claims vượt qua.

### 4.4. Giới hạn token lifetime và current policy vẫn có ích

RS vẫn cần kiểm:

- `exp`, `nbf`, `iat` hợp lệ theo profile/clock skew.
- Maximum acceptable token lifetime nếu security policy có quy định.
- `iss`, expected `aud`, `typ`, `alg` và scope grammar.
- Business authorization trên từng resource/tenant/action.
- Revocation/key trust state hiện tại.

Các điều kiện này giảm blast radius của nhiều lỗ hổng, **nhưng không thay việc loại bỏ khóa K1 bị compromise khỏi tập khóa đáng tin**.

## 5. Phân biệt lộ public key, lộ private key và key substitution

### 5.1. Public key xuất hiện trên JWKS là bình thường

Ví dụ rút gọn một JSON Web Key Set:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "issuer-k1",
      "alg": "RS256",
      "n": "<PUBLIC_MODULUS_BASE64URL>",
      "e": "AQAB"
    }
  ]
}
~~~

`n` và `e` là thành phần **public**. Không có `d`, `p`, `q` hay private key bytes. Việc một API tải tài liệu JWKS này **không phải sự cố an ninh**.

Ngược lại, tài liệu như sau **không được phân phối** cho các Resource Servers như key set xác minh công khai:

~~~json
{
  "kty": "RSA",
  "kid": "issuer-k1",
  "n": "<PUBLIC_MODULUS>",
  "e": "AQAB",
  "d": "<PRIVATE_EXPONENT>",
  "p": "<PRIVATE_PRIME>",
  "q": "<PRIVATE_PRIME>"
}
~~~

Đây là ví dụ nhấn mạnh secret fields, không chứa khóa thực. Nếu một JWK private key bị đăng nhầm lên public JWKS, cần coi là compromise, dừng tin vật liệu khóa và điều tra phạm vi phân phối.

### 5.2. Public JWKS bị sửa trái phép cũng nguy hiểm

Giả sử attacker **không có K1_private** nhưng chiếm được nơi phục vụ JWKS hoặc pipeline cập nhật metadata, thay public K1 bằng **public key của attacker KX**. Nếu RS tải và tin key set giả đó, attacker có thể ký token bằng KX_private rồi được RS chấp nhận.

Đây là **trust-source/key substitution compromise**, khác **private key disclosure**, nhưng có thể có kết quả giống nhau ở verifier.

Vì vậy cần bảo vệ:

- OIDC/OAuth issuer discovery và `jwks_uri` qua TLS và nguồn cấu hình đáng tin.
- Quyền publish JWKS/metadata, CI/CD, DNS và reverse proxies.
- Algorithm allowlist và issuer binding tại RS.
- Quy tắc thay đổi key set, log audit và giám sát bất thường.
- Key trust distribution/cache; nếu cần trust pinning theo chính sách phải có quy trình rotation an toàn.

### 5.3. Không fetch khóa từ JWT header chưa xác minh

Anti-pattern:

~~~java
// SAI: pseudocode, tuyệt đối không làm trong JWT verifier.
String arbitraryJwksUrl = untrustedJwtHeader.get("jku");
PublicKey key = httpGet(arbitraryJwksUrl);
return verifyWith(key, token);
~~~

Attacker có thể trỏ `jku` tới server của họ hoặc địa chỉ nội bộ để gây SSRF. Verifier phải chọn **trusted issuer/configured JWKS** độc lập với URL do token tự khai, rồi giới hạn `kid`/`alg` trong trust set đó.

### 5.4. Algorithm confusion và key-type confusion

Đừng để JWT tự nói:

~~~json
{
  "alg": "none",
  "kid": "issuer-k1"
}
~~~

rồi verifier bỏ chữ ký vì thấy `"none"`; cũng đừng tự đổi từ `RS256` sang `HS256` và dùng **public RSA key** như HMAC secret. Security libraries hiện đại thường ngăn các trường hợp này khi cấu hình đúng, nhưng custom parser/compatibility code vẫn có thể sai.

An toàn hơn là:

~~~text
Trusted issuer:
    allowed algorithms = RS256 (hoặc tập được phê duyệt).
    key set = JWKS HTTPS trusted của issuer đó.
    expected token type = at+jwt khi dùng RFC 9068.
    expected audience = https://orders.example.com.

JWT header:
    chỉ gợi ý chọn một key phù hợp từ trust set,
    KHÔNG quyết định trust policy.
~~~

## 6. Phát hiện key compromise: bằng chứng, dấu hiệu và giới hạn

Không phải sự cố nào cũng bắt đầu từ “private key xuất hiện trên GitHub”. Có thể nhận tín hiệu từ hạ tầng, logs, token verification hoặc hành vi API.

### 6.1. Một số dấu hiệu cần điều tra

| Tín hiệu | Điều cần kiểm tra |
|---|---|
| Private key/secret có trong repo, build artifact, ticket, chat hoặc log | Đường phân phối, lịch sử commit/artifact, quyền đọc, thời gian phơi lộ |
| KMS Sign calls từ IAM role hoặc region bất thường | Principal, key version, thời gian, target/thuật toán và audit completeness |
| Signed JWT không có record issuance tương ứng | Issuance logs/store có đầy đủ và đáng tin không; có AS nodes khác không |
| Token có `aud`, `sub`, `scope`, `exp` bất thường | AS policy, token profile, key identifier và quyền đã dùng |
| JWKS/key metadata đổi ngoài change request | Publisher/deployment/DNS/trust-store compromise |
| Một client có private_key_jwt assertion phát từ IP/service khác | Client key/credential access và certificate/registered key |
| DPoP proofs từ thiết bị/đường mạng bất thường | Holder key theft, attacker control, replay detection |
| Certificates/private key bị export trái policy | HSM/KMS/PKI audit, device compromise |
| Algorithm/key-type fallback bất ngờ | JWT verifier config regression hoặc malicious token |

Một token được ký hợp lệ nhưng không có issuance log có thể là **dấu hiệu mạnh cần điều tra**, nhưng log có thể thiếu do sampling, outage, batch issuance hoặc retention. Không dùng “không thấy log” làm cơ sở kết luận duy nhất.

### 6.2. Cần xác định thời điểm sớm nhất có thể bị chiếm

Sự kiện được phát hiện ở `T_detect` **không phải** thời điểm attacker bắt đầu có khóa. Ví dụ:

~~~text
T_exposure_start?   Private key nằm trong backup có quyền quá rộng.
T_compromise?       Attacker có thể đã truy cập từ tuần trước.
T_detect            Security nhận cảnh báo hôm nay.
T_contain           Khóa K1 bị ngừng tin ở AS/RS.
T_recover           Hệ thống chỉ dùng key K2 đã được kiểm soát.
~~~

Trong incident, nên ghi **khoảng bất định** cho thời điểm exposure/compromise; không tự coi `T_detect` là ranh giới an toàn của các token đã ký.

### 6.3. Inventory key là điều kiện của phạm vi ứng cứu

Một **key registry** tối thiểu có thể lưu:

~~~text
keyReference / KMS key ARN
publicKeyFingerprint (ví dụ JWK thumbprint phù hợp)
issuerId
purpose = SIGN_JWT_AT / SIGN_OIDC_ID / CLIENT_AUTH / ENCRYPT_JWE ...
algorithmAllowlist
environments / regions
owningService / owningTeam
allowedSigners (IAM principals)
verifiers / JWKS distribution paths
createdAt / activatedAt / retiredAt
lastKnownUsage
revocationOrDisableStatus
~~~

Không lưu private key trong inventory. Fingerprint giúp tìm cùng key material được dùng với nhiều `kid`, nhưng phải phân biệt thumbprint public key và secret fingerprint. Một inventory thiếu sẽ khiến scope incident bị đánh giá thấp.

### 6.4. Phân biệt key compromise thật và tín hiệu giả

Nếu team thấy **public JWK** trong logs, thường chưa đủ để coi signing key bị lộ. Nếu leak là **private key/JWK `d`**, KMS Signing IAM privilege, HMAC secret hoặc khả năng publish JWKS đáng tin, đó là rủi ro nghiêm trọng.

Đừng chia sẻ raw key thêm với đội điều tra qua chat/email để “xác nhận”. Dùng cơ chế kiểm tra fingerprint/metadata phù hợp và bảo vệ chain of custody; giảm tối đa số người và hệ thống tiếp xúc secret.

## 7. Đánh giá blast radius theo issuer, audience và key reuse

Một private signing key bị lộ có thể ảnh hưởng **nhiều hơn một JWT** vì attacker có thể ký các claims phù hợp với bất kỳ token mà verifier tin key đó theo trust policy.

### 7.1. Mô hình xác định blast radius

~~~text
Compromised capability:
    key material / KMS Sign authority / JWKS publisher control

Affected trust domains:
    issuers và key sets đã dùng capability đó

Potentially forgeable token types:
    access token, ID token, client assertion ... tùy key reuse

Affected verifiers:
    Resource Servers, Relying Parties, token endpoint,
    introspection/custom services ...

Affected operations:
    login, API access, client auth, account linking, token exchange...
~~~

Không thể suy “chỉ `orders:read` bị ảnh hưởng” chỉ vì token hợp lệ gần nhất mang scope đó. Attacker có thể tạo claims **rộng hơn** nếu RS không có kiểm soát độc lập.

### 7.2. Signing key dùng cho ID token

Nếu OP ID token signing key bị lộ, một RP tiếp tục tin key có thể chấp nhận **ID token giả** với `sub` của user khác, nếu các kiểm tra OIDC khác cũng bị attacker vượt qua trong flow/implementation cụ thể.

Tuy nhiên **không đồng nhất** “có private key ký ID token” với “tự đăng nhập qua mọi OAuth login callback”: RP vẫn cần kiểm issuer, audience, nonce/state, Authorization Code + PKCE và response binding. Key compromise là nghiêm trọng, nhưng thành công tấn công phụ thuộc đường token được sử dụng.

### 7.3. Signing key dùng cho JWT access token

Nếu Orders API xác minh offline bằng public K1 và tin các claims trong JWT:

~~~text
Potentially forgeable:
    sub / client_id / scope / aud / exp / role custom claims.

Potential independent controls:
    current account active state
    resource ownership/tenant membership
    token issuance allowlist / grant state
    server-side transaction and approval policy
~~~

Đừng coi independent controls là đủ nếu token vẫn được RS chấp nhận từ khóa đã bị compromise; đó chỉ là các lớp hạn chế tác động.

### 7.4. Client auth key khác issuer signing key

Nếu client `expense-sync` dùng `private_key_jwt` để xác thực tại AS:

~~~text
Client holds C1_private.
AS trusts C1_public for client_id=expense-sync.
~~~

Lộ C1_private có thể khiến attacker tạo **client assertion** để giả client này theo constraints của token endpoint, nhưng **không tự** có quyền ký access token như OP key K1. Cần thu hồi client key C1, client registration/JWKS binding, đánh giá grants/tokens được cấp qua client giả mạo.

### 7.5. TLS server key không mặc nhiên giải mã traffic TLS lịch sử

Với TLS hiện đại có **forward secrecy** (ví dụ TLS 1.3), lộ lâu dài server private key **không tự** giải mã toàn bộ các phiên đã ghi lại từ trước. Nhưng nó vẫn có thể hỗ trợ impersonation hoặc các tình huống khác tùy certificate, key exchange, private key usage và trạng thái chứng chỉ.

Không đưa ra kết luận “lộ TLS key = đọc được tất cả lịch sử HTTPS” hoặc “TLS 1.3 nên không có vấn đề”. Cần điều tra cấu hình thực tế, certificate revocation, key replacement và các phiên/endpoint có thể bị ảnh hưởng.

## 8. Chiến lược ứng cứu: kiểm soát khả năng ký trước, rồi thay trust

Khi **tin rằng signing private key đã bị compromise**, việc ưu tiên là **ngừng cho attacker tiếp tục sử dụng capability** và **ngăn verifiers tin chữ ký từ capability đó**.

### 8.1. Một playbook ở mức cao

1. **Tuyên bố incident và khoanh vùng:** loại key, fingerprints, issuers, verifiers, owners, thời điểm và mức độ chắc chắn.
2. **Bảo vệ chứng cứ:** audit KMS/IAM, deploys, key registry, sự kiện đăng nhập/API; không nhân bản secret qua kênh không an toàn.
3. **Chặn khả năng ký bị chiếm:** vô hiệu/giới hạn KMS key hoặc IAM signer, thu hồi credential, cô lập host/pipeline bị xâm nhập.
4. **Tạo key K2 mới** bằng CSPRNG/KMS/HSM đáng tin, với quyền truy cập mới và môi trường đã được kiểm soát.
5. **Chuyển signing sang K2** sau khi các thành phần cần thiết có đường xác minh khóa mới; kiểm soát rủi ro gián đoạn.
6. **Ngừng trust K1 tại toàn bộ verifiers** đúng trust domain, kể cả RS JWKS caches, pinned key sets và regions.
7. **Kiểm tra mọi token/grant/session bị ảnh hưởng**, revoke/force reauthentication khi policy yêu cầu; không hứa giữ an toàn các token K1 chỉ nhờ `exp`.
8. **Giám sát convergence và abuse**, xác nhận mọi API cần thiết từ chối token ký K1.
9. **Phục hồi và hardening:** sửa nguồn lộ, IAM, secret distribution, key separation, retention và CI checks.
10. **Rà soát tác động:** audit dữ liệu đã truy cập/hành động API, người dùng/tenant/partners và nghĩa vụ thông báo khi phù hợp.

### 8.2. Vì sao chỉ rotate secret trong AS là chưa đủ?

~~~text
AS đã bắt đầu ký token mới bằng K2.
JWKS ở AS không còn K1.
Orders API vẫn cache K1 public trong 30 phút.
Attacker vẫn có K1 private.

=> Orders API có thể tiếp tục chấp nhận JWT giả ký K1.
~~~

**Đổi khóa phát hành** và **loại bỏ khóa xác minh khỏi tập tin cậy của RS** là **hai hành động riêng**. Trong emergency, phải xử lý cả hai và đo thời gian hội tụ ở từng RS.

### 8.3. Không giữ K1 để “tránh logout người dùng” khi đã compromise

Trong planned rotation, giữ public K1 trên JWKS cho tới khi các token hợp lệ cũ hết hạn thường hữu ích để tránh outage. Nhưng trong **known/suspected signing key compromise**, giữ K1 được tin đồng nghĩa vẫn cho attacker sử dụng quyền ký.

Tổ chức phải đánh giá mức độ chắc chắn, blast radius và business continuity, nhưng không nên gắn nhãn **“emergency rotation hoàn tất”** khi các RS còn chấp nhận K1 trong cửa sổ không được chấp thuận.

### 8.4. Không cần công bố private key để chứng minh đã thu hồi

Các verifiers chỉ cần key ID/fingerprint/public key trust state đã xác thực, cùng metadata issuer/algorithm. Không đưa private key hay HMAC secret vào security event, ticket, monitoring hoặc notification gửi downstream.

## 9. Planned rotation và emergency compromise rotation là hai quy trình khác nhau

Một hệ thống token thường có chính sách **key rotation** định kỳ. Khi không có dấu hiệu compromise, rotation được thực hiện theo giai đoạn để tránh từ chối token còn hạn. Khi signing key đã lộ, mục tiêu chuyển từ **tương thích** sang **loại bỏ niềm tin đối với khóa bị chiếm**.

### 9.1. Planned rotation: chồng lấn key để không gián đoạn

~~~text
Thời gian  ----------------------------------------------->

Giai đoạn A:    K1 ký, K1 public có trong JWKS.
Giai đoạn B:    K1 ký, K1 + K2 public có trong JWKS.
Giai đoạn C:    K2 ký, K1 + K2 public có trong JWKS.
Giai đoạn D:    K2 ký, chỉ K2 public còn được tin
               sau khi token K1 hợp lệ đã hết hạn,
               tính cả cache, clock skew và policy.
~~~

Quy tắc chung:

- Publish K2 public tới JWKS và để verifiers cập nhật trước khi AS bắt đầu ký K2.
- Dùng `kid` ổn định, key material/algorithm phù hợp và metadata trusted.
- Chuyển issuance sang K2 theo rollout có giám sát.
- Giữ K1 public trong khoảng các token K1 hợp lệ có thể còn được chấp nhận.
- Sau đó retire K1 theo retention/audit/backup policy.

### 9.2. Emergency compromise: chặn trust ngay theo risk policy

~~~text
K1 private bị lộ!
    |
    +--> Disable/contain K1 Sign capability.
    +--> Tạo, kiểm soát và activate K2.
    +--> Emergency distrust K1 tại RS/RP.
    +--> Purge/override JWKS caches và pinned key sets.
    +--> Xác nhận tokens K1 bị từ chối trong tất cả vùng.
    +--> Revoke grants/sessions theo mức độ rủi ro.
~~~

Không chờ token K1 “tự hết hạn” nếu điều đó vượt security incident objective. Attacker có khóa K1 có thể tự chọn `exp` giả; chỉ TTL policy độc lập của RS và current key trust controls mới giới hạn điều đó.

### 9.3. Nếu K2 chưa được phân phối, phải xử lý availability ra sao?

Trong sự cố thật, có thể xảy ra:

~~~text
AS đã vô hiệu K1.
Một số RS chưa biết K2.
~~~

Nếu phải ưu tiên **ngăn token giả**, các RS đó có thể phải **fail closed** tạm thời thay vì quay về chấp nhận K1. Phương án có thể là:

1. Phân phối K2 và trust policy qua kênh cấu hình khẩn cấp được xác thực.
2. Sử dụng introspection/authoritative token state cho các endpoints hỗ trợ.
3. Giới hạn/đóng tạm những đường nhạy cảm nếu chưa xác minh key trust mới.
4. Khôi phục traffic khi validators đã nhận đúng K2 và reject K1.

Đây là quyết định tradeoff security/availability; cần playbook và authority xác định trước. Không dùng một public key tải từ URL tự khai của caller làm “giải pháp cứu hỏa”.

### 9.4. Không tái sử dụng key material trong K2

“Đổi `kid` từ `K1` sang `K2`” mà vẫn dùng cùng private key bytes **không phải rotation**. Tương tự, cùng key material xuất hiện trong một KMS alias khác vẫn là compromised capability.

~~~text
K1 (kid=old)  -> modulus/fingerprint F1
K2 (kid=new)  -> modulus/fingerprint F1

=> Cùng key material; attacker giữ K1_private vẫn ký được.
~~~

K2 phải là khóa **mới được sinh an toàn**, không có quan hệ tái sử dụng key material, và phải kiểm chứng không rò qua cùng nguồn build/secret pipeline bị xâm nhập.

## 10. JWKS propagation: xóa một khóa khỏi endpoint chưa đủ

Trong OIDC/OAuth JWT, RS/RP thường lấy public keys từ `jwks_uri` đáng tin. Để bảo đảm emergency distrust, phải hiểu **các lớp cache và trust stores**.

### 10.1. Các nơi có thể lưu K1 public

~~~text
Authorization Server
   |
   +--> HTTPS JWKS endpoint
   |       |
   |       +--> CDN / reverse proxy cache
   |       +--> Service mesh / gateway cache
   |
   +--> Resource Server A local JWKS cache
   +--> Resource Server B local JWKS cache
   +--> Mobile/partner app embedded public key
   +--> API Gateway verifier key store
   +--> Cloud function / batch worker JWT verifier
   +--> Multi-region edge authorizer
~~~

Một JWKS response mới không **tự xóa** bản copy K1 ở mọi nơi. Ngay cả khi AS ngừng phát K1, một RS vẫn có K1 public trong memory và tiếp tục xác minh chữ ký do attacker tạo bằng K1 private.

### 10.2. Cache-Control và key refresh

JWKS endpoint thường có cache headers/ETag; các JWT libraries cũng có **cache nội bộ**. Trong planned rotation, cache giúp giảm request. Trong emergency:

- Invalidate CDN/proxy cache nếu được.
- Có cơ chế **push security trust state** hoặc emergency config refresh tới RS.
- Xác định và kiểm soát **maximum stale duration** của từng verifier.
- Phân biệt local JWKS cache với token/introspection cache.
- Không phụ thuộc hoàn toàn việc JWT có `kid` mới để kích hoạt refresh; token giả ký K1 vẫn yêu cầu loại K1 cũ.
- Kiểm tra sau restart/rolling deploy: một node mới có thể đọc trust store cũ từ image/sidecar/config.

**Cache refresh khi gặp `kid` lạ** không giải quyết trường hợp attacker tiếp tục ký bằng `kid` cũ mà cache đã biết.

### 10.3. Key trust policy phải ràng buộc issuer + algorithm

Một RS bảo vệ Orders API nên có trust config kiểu:

~~~yaml
# Schema ứng dụng minh họa, không phải cấu hình Spring mặc định.
trusted_issuers:
  - issuer: https://login.example.com
    jwks_uri: https://login.example.com/.well-known/jwks.json
    allowed_signing_algorithms: [RS256]
    expected_audiences:
      - https://orders.example.com
    emergency_blocked_key_fingerprints:
      - "<THUMBPRINT_OF_COMPROMISED_K1>"
    policy_version: 18
~~~

`emergency_blocked_key_fingerprints` phải là policy **đến từ nguồn tin cậy**, không lấy từ JWT header. `policy_version` giúp ngăn một cấu hình cũ ghi đè phiên bản mới; production có thể dùng cơ chế khác nhưng vẫn cần monotonic trust decisions.

### 10.4. Chặn `kid` đơn lẻ có thể không đủ

Attacker có K1_private có thể:

- Tiếp tục dùng `kid=K1` nếu RS còn tin key.
- Phát token tự đặt `kid=K2` nhưng chữ ký vẫn K1; verifier đúng sẽ từ chối nếu K2 là key material khác.
- Lợi dụng verifier cấu hình sai dùng một khóa mặc định bất kể `kid`.
- Lợi dụng cùng K1 public được đăng dưới **một `kid` khác**.

Vì vậy emergency response nên xác định **public-key thumbprint/key material** và nơi khóa đó được trusted, kết hợp block `kid` nếu hữu ích. Không tin claim/header chưa xác minh như nguồn duy nhất cho status.

### 10.5. `jti` denylist không tự đủ khi khóa ký đã bị chiếm

Thông thường, thu hồi một access token bằng cách lưu `iss+jti` vào denylist có ích. Nhưng sau khi attacker có signing key:

~~~text
Attacker tạo T_fake_1, jti=randomA.
RS denylist không có randomA.
Attacker tạo T_fake_2, jti=randomB.
RS denylist không có randomB.
~~~

**Không thể denylist từng `jti` chưa biết như cách bảo vệ duy nhất.** Cần distrust signing key hoặc một **issuance allowlist / token authorization state độc lập** mà attacker không thể giả mạo bằng claims của chính JWT.

### 10.6. Issuance allowlist là một hướng phòng vệ bổ sung

Một thiết kế có thể gắn token với **server-side issuance record** đáng tin (hoặc opaque reference), rồi RS kiểm token đó tồn tại, có issuer/client/scope/audience đúng và chưa revoke.

Tuy nhiên cần xác định:

- Issuance store được bảo vệ khỏi cùng kẻ tấn công không?
- RS lookup online/cache với freshness budget nào?
- Token giả với `jti` trùng token thật có thể vượt không? Phải ràng buộc đầy đủ token identity/claims hoặc token digest theo policy.
- Quyền ghi store có độc lập với signing capability bị lộ không?

Một allowlist thiết kế sai chỉ kiểm `jti` mà attacker có thể đoán hoặc sao chép vẫn có thể bị bypass. **Trust removal** thường là biện pháp căn bản với signing key đã compromise.

## 11. Key compromise và revocation propagation

Thu hồi một access token, refresh token hoặc grant đã khó trong hệ thống phân tán; thu hồi **trust với signing key** còn có blast radius rộng hơn.

### 11.1. Phân biệt các bước và bằng chứng hoàn tất

| Mốc | Hành động | Chưa chứng minh điều gì |
|---|---|---|
| `T_detect` | Security phát hiện dấu hiệu lộ K1 | Chưa biết thời điểm compromise thật |
| `T_kms_disable` | Vô hiệu KMS Sign/IAM với K1 | Bản private key đã export không còn tồn tại |
| `T_as_switch` | AS phát token bằng K2 | RS đã ngừng tin K1 |
| `T_jwks_publish` | Public JWKS không còn K1 | CDN/RS caches đã hết K1 |
| `T_rs_apply` | Một RS áp trust policy chặn K1 | Mọi regions/instances đã áp |
| `T_all_verifiers_reject` | Tất cả verifier thuộc phạm vi từ chối K1 | Dữ liệu đã bị đọc trước đó được hoàn tác |

### 11.2. Kiến trúc phát sự kiện key distrust

~~~mermaid
sequenceDiagram
    participant I as Incident Controller
    participant K as KMS/Key Registry
    participant AS as Authorization Server
    participant B as Trusted Security Event Bus
    participant R1 as Orders API
    participant R2 as Billing API
    I->>K: Disable K1 signing / mark compromised
    K-->>I: New security policy version 18
    I->>AS: Activate trusted K2, distrust K1
    AS->>B: KeyDistrust(issuer, fingerprint K1, version=18)
    B-->>R1: Security event
    B-->>R2: Security event
    R1->>R1: Persist block, evict key cache, verify readiness
    R2->>R2: Persist block, evict key cache, verify readiness
    R1-->>I: Enforcement applied
    R2-->>I: Enforcement applied
    Note over I,R2: Phải kiểm thực tế các token ký K1 bị từ chối
~~~

Sơ đồ mô tả một **security control plane nội bộ** có thể xây dựng, không phải một cơ chế chuẩn tự động của JWKS hay OIDC. Không giả định broker ack nghĩa là RS đã áp trust policy.

### 11.3. Outbox, idempotency, version và snapshot

Nếu dùng event-driven invalidation:

- Ghi quyết định K1 `COMPROMISED`/`BLOCKED` và outbox event trong transaction thích hợp.
- Phân phối bền vững (retry, consumer checkpoint, replay).
- **Idempotent**: nhận event nhiều lần không làm đổi trạng thái sai.
- **Monotonic**: policy v17 `K1 trusted` đến sau v18 `K1 blocked` không được hồi sinh K1.
- **Bootstrap**: RS mới phải tải trust snapshot hiện tại trước khi nhận traffic nhạy cảm.
- **Reconciliation**: định kỳ đối chiếu local security policy với authoritative registry.
- **Fail mode**: khi trust state quá cũ, RS không âm thầm tiếp tục tin K1.

Không đưa private key vào event. Chỉ gửi issuer/key fingerprint, policy version, reason code và metadata cần thiết với producer được xác thực.

### 11.4. Cửa sổ rủi ro cần đo ở RS

~~~text
Key compromise known at T_detect.
K1 blocked at AS at T_as_switch.
Orders API rejects K1 at T_orders.
Billing API rejects K1 at T_billing.

Enforcement lag for Billing = T_billing - T_as_switch.
~~~

Hệ thống có thể đặt emergency SLO—ví dụ ngừng tin key bị compromise trong một số giây/phút theo risk policy. Đây là **mục tiêu nội bộ**, không phải guarantee của RFC. Cần đo P99 và node/region chậm nhất; một dịch vụ có traffic thấp có thể cần synthetic probe để kiểm enforcement.

### 11.5. Network partition và fail-closed

~~~text
Region A:
    Security policy v18: K1 BLOCKED.

Region B mất kết nối:
    Security policy v17: K1 TRUSTED.
    JWT ký K1 vẫn có chữ ký hợp lệ.
~~~

Nếu policy chặn key khẩn cấp yêu cầu hiệu lực gần thời gian thực, region B phải có **freshness deadline**. Khi quá hạn mà không fetch được policy mới, có thể cần **fail closed** cho endpoints cần JWT trust. Việc “serve last known key forever” có thể phá cam kết emergency revocation.

Hành vi cụ thể cần được phê duyệt trước vì fail closed ảnh hưởng availability. Nhưng **không tuyên bố ứng cứu đã hoàn tất** khi còn một region ALLOW token ký K1.

## 12. KMS/HSM và thiết kế key lifecycle giảm thiểu compromise

Mục tiêu của key management là **hạn chế người có thể nhìn thấy key material, giới hạn nơi có thể sử dụng khóa và phát hiện hành vi sai**, chứ không phải chỉ đổi mật khẩu mỗi tháng.

### 12.1. Sinh khóa an toàn và tách mục đích

Một khóa dùng để ký JWT access tokens không nên tự động được tái sử dụng cho:

- JWT ID tokens của nhiều issuer không có cùng trust policy.
- Client assertion `private_key_jwt` của một OAuth client.
- Mã hóa JWE hoặc database encryption.
- Cookie signing, CSRF secret hoặc password-reset token.
- Dev/test/staging và production.

Tách khóa giảm **blast radius** và tránh confusion giữa các mục đích. Tùy profile, một issuer có thể dùng cùng signing key cho các loại token đã phân biệt chặt bằng `typ`, audience và validators; nhưng cần lựa chọn có ý thức, không tái sử dụng vì tiện triển khai.

### 12.2. Non-exportable KMS/HSM không đồng nghĩa không thể bị lạm dụng

~~~text
KMS key K1 = non-exportable.
AS role có quyền kms:Sign.

Attacker chiếm AS role/credential.
    -> Có thể yêu cầu KMS ký payload mà họ kiểm soát.
~~~

Private key bytes không lộ, nhưng **signing capability đã bị chiếm**. Cần IAM least privilege, các điều kiện key usage, service identity, network/region restrictions, key policy, anomaly detection và audit trên operation `Sign`.

Điều tra phải phân biệt:

- **Key material disclosure**: có bản copy private bytes bên ngoài trust boundary.
- **Sign oracle abuse**: kẻ xấu được gọi API ký.
- **Policy/publisher control**: kẻ xấu thay public trust state hoặc key alias.
- **Root/host compromise**: attacker điều khiển ứng dụng phát hành token và claims.

Các trường hợp đều đáng nghiêm trọng nhưng biện pháp containment khác nhau.

### 12.3. Những thực hành phòng ngừa

| Kiểm soát | Tác dụng |
|---|---|
| CSPRNG/KMS/HSM khi sinh key | Tránh private key yếu/dự đoán được |
| Không export key material khi không cần | Giảm bản sao bí mật có thể bị lộ |
| IAM least privilege và separation of duties | Giới hạn ai ký/đổi key policy |
| Tách key theo issuer, môi trường, mục đích | Giảm blast radius và cross-environment trust |
| Không hardcode secret trong source/artifact | Giảm lộ qua repo, build logs, binary |
| Secret scanning + prevention hook | Phát hiện leakage trong commit/CI và artifacts |
| Key usage audit và alert | Phát hiện ký bất thường hoặc thay JWKS |
| Key version + rotation playbook | Hỗ trợ planned/emergency migration |
| Trusted JWKS publisher change control | Chống key substitution |
| Encrypted backup + access/retention control | Giảm lộ từ bản sao dự phòng |
| Incident exercises/chaos probes | Đo khả năng loại bỏ trust K1 ở toàn hệ thống |

### 12.4. Vì sao không đưa HMAC secret vào mọi Resource Server?

Với HS256, mỗi RS được cấp secret để xác minh cũng có khả năng **ký**. Trong hệ thống có nhiều đội, vendor hoặc multi-tenant runtime, đây là trust expansion đáng kể.

Khi vẫn cần HMAC theo profile:

- Sinh secret ngẫu nhiên có entropy phù hợp.
- Giữ trong secret manager/KMS, không log, không commit.
- Không dùng cùng secret cho môi trường khác hoặc purpose khác.
- Có cơ chế rotate và chặn secret cũ trên mọi verifiers.
- Giới hạn bên nào thực sự phải giữ secret.

Đừng tự chuyển JWT verifier từ RS256 sang HS256 chỉ để dễ cấu hình; cần threat model cho việc trao khả năng ký cho các thành phần giữ secret.

### 12.5. Backup/restore có thể hồi sinh khóa đã ngừng tin

Sau emergency distrust, một restore từ snapshot cũ có thể:

~~~text
Trạng thái hiện tại:
    K1 = COMPROMISED, BLOCKED.

Restore snapshot hôm qua:
    K1 = ACTIVE.
~~~

Nếu khôi phục state mà không replay **security revocation events/policy versions**, AS hoặc RS có thể lại chấp nhận K1. Cần **monotonic security tombstone**, authoritative high-watermark và kiểm trust status khi restore.

## 13. DPoP holder key và mTLS certificate-bound tokens

**Sender-constrained tokens** ràng buộc việc sử dụng token với một private key/certificate, giảm nguy cơ attacker **chỉ đánh cắp bearer token string** rồi dùng lại.

Nhưng **khi holder key cũng bị compromise**, token có thể bị sử dụng trái phép nếu attacker nắm token và có khả năng tạo proof phù hợp.

### 13.1. DPoP ràng buộc token với khóa của client

Trong OAuth DPoP (RFC 9449):

~~~text
Client:
    giữ DPoP private key D1.
    chứng minh sở hữu D1 bằng JWT DPoP proof.

AS:
    có thể phát access token ràng buộc thumbprint của D1 public.

RS:
    kiểm DPoP proof, key binding, method, URI, freshness, replay.
~~~

Khi attacker chỉ có token T1 nhưng không có D1_private, việc replay bị hạn chế nếu AS/RS kiểm đúng. Khi **D1_private bị lộ**, yếu tố ràng buộc giảm hiệu lực. Nếu attacker cũng có token, attacker có thể tạo các proof trông hợp lệ, trừ các kiểm soát bổ sung.

### 13.2. DPoP proof checks không được bỏ

Một DPoP-aware RS cần kiểm profile như:

- HTTP method `htm` và URI `htu` đúng request/normalization.
- `iat` trong cửa sổ được phép; `jti` chống replay.
- `ath` ràng buộc proof với access token theo quy tắc tương ứng.
- JWK public trong proof đúng thumbprint token binding (`cnf.jkt`) khi áp dụng.
- Nonce nếu server yêu cầu theo DPoP nonce policy.
- Thuật toán ký proof được hỗ trợ và an toàn; không chấp nhận `alg=none`.

**DPoP key compromise không giống issuer signing key compromise.** Lộ D1 cho phép giả proof của client D1, **không tự** cho phép phát hành arbitrary issuer-signed access tokens. Cần revoke access/refresh tokens ràng buộc D1 theo chính sách và cấp binding mới bằng key D2.

### 13.3. mTLS client authentication và certificate-bound access token

Với mTLS-bound access token, certificate/private key giúp chứng minh sender tại endpoint hỗ trợ. Nếu private key bị lộ:

- Khả năng giả client phụ thuộc cert validity, PKI/trust, handshake và endpoint verification.
- Cần rotate cert/key, vô hiệu client key trust theo policy và đánh giá active tokens bị ràng buộc.
- Certificate revocation qua CRL/OCSP có hiệu lực thực tế phụ thuộc verifier/cache và hành vi fail mode.
- Có thể cần revoke/bind lại token `cnf` gắn certificate fingerprint.

Không nói “đã revoke certificate” đồng nghĩa mọi microservice lập tức từ chối mọi token; **certificate trust propagation** cũng là hệ thống phân tán.

### 13.4. Một key bị lộ ở đâu cần rotate ở đó

| Sự cố | Nơi sửa trước | Đừng nhầm là |
|---|---|---|
| AS signing private key K1 lộ | AS/KMS + mọi RS/RP tin K1 | Chỉ một refresh token bị lộ |
| DPoP private key D1 lộ | Client/device key + AS token binding + RS policy | AS signing key K1 lộ |
| mTLS client key C1 lộ | Client certificate/private key, PKI, AS/mTLS trust | Chỉ cần xóa browser cookie |
| `private_key_jwt` client key lộ | Client registration public key + AS client auth | OP ID token verification key lộ |
| Browser session cookie lộ | RP session store, cookie controls, session revocation | Signing key JWT của AS lộ |

### 13.5. Không dùng sender constraint thay token revocation

Khi user bị khóa, client đã rời tổ chức hoặc thiết bị có private key bị mất, vẫn cần **revoke grant/tokens**. Sender constraint là một lớp bảo vệ chống replay khi chỉ token string bị lộ, không phải “khóa không thể bị chiếm” hay bằng chứng user còn quyền.

## 14. JWE encryption key compromise khác signing key compromise

JWT có thể được **ký bằng JWS**, **mã hóa bằng JWE**, hoặc kết hợp (nested JWT). Cần phân biệt **confidentiality** với **authenticity/integrity**.

### 14.1. Chữ ký không che claims

Một JWS access token chứa:

~~~json
{
  "sub": "alice-123",
  "email": "alice@example.com",
  "scope": "orders:read"
}
~~~

thường có payload có thể đọc sau Base64url decode. JWS không bảo mật email khỏi người cầm token. Nếu dữ liệu nhạy cảm không cần đưa cho RS, **không đưa vào token**, thay vì nghĩ “JWT đã ký nên được mã hóa”.

### 14.2. JWE bảo vệ bí mật nội dung

Nếu JWE encryption/decryption key bị lộ, attacker có thể:

- Giải mã những JWE ciphertext họ có và key đủ để giải mã, tùy thuật toán và key management.
- Giả mạo một số dạng ciphertext/được chấp nhận như token mã hóa nếu hệ thống chỉ dùng symmetric authenticated encryption mà không có xác thực issuer/binding độc lập.
- Khai thác thiếu kiểm token type, issuer, audience hoặc key usage.

Nhưng **không tự kết luận** lộ một decryption key cho phép ký JWS bằng AS signing private key **khác**. Nếu nested JWT được cấu hình **sign-then-encrypt** với kiểm inner signature đúng, việc có thể giải mã JWE không tự tạo inner JWS signature hợp lệ.

### 14.3. Encryption-key rotation ảnh hưởng ciphertext cũ

Khi rotate JWE key cần xác định:

1. Nội dung còn được lưu/tra cứu dưới key cũ không?
2. Có cần re-encrypt dữ liệu tại rest hoặc loại bỏ ciphertext cũ không?
3. Recipient nào giữ decryption key và có bao nhiêu bản sao?
4. Ciphertext từ thời điểm trước khi key bị lộ có thể bị giải mã không?
5. Có authenticated encryption, integrity checks và algorithm allowlist không?
6. Khi loại key cũ, dữ liệu/những thông điệp hợp lệ cũ có trở nên không thể đọc không?

Emergency key compromise của **confidentiality** có thể đòi hỏi xử lý **dữ liệu đã lộ**, không chỉ hủy sessions.

### 14.4. Đừng tái sử dụng một khóa cho ký và mã hóa

Tách key purpose (`sig` vs `enc`), key use và allowed algorithms theo profile. Tùy key material, các chuẩn/hệ thống có yêu cầu riêng; không “dùng chung cho gọn” hay tin field `use` do nguồn không xác minh gửi.

## 15. Opaque token và refresh token: không phải mọi compromise đều mint JWT

Một opaque access token thường là **chuỗi ngẫu nhiên tham chiếu tới server-side state** hoặc có cấu trúc mà chỉ AS hiểu. Nếu AS sinh opaque token bằng CSPRNG và kiểm lookup server-side, **lộ JWT signing key K1 không tự tạo opaque token hợp lệ**.

### 15.1. Rủi ro phụ thuộc cách opaque token được tạo/kiểm

| Thiết kế | Nếu một key/secret bị lộ |
|---|---|
| Opaque random reference + authoritative DB lookup | Lộ JWT signing key không tự làm giả random reference; nhưng DB/token store compromise nghiêm trọng |
| Self-contained opaque token dùng MAC | Lộ MAC key có thể cho phép tạo token giả nếu format/state checks cho phép |
| Opaque token được AS lưu hash/fingerprint | Lộ hash key không nhất thiết khôi phục random token; đánh giá entropy và cách xác minh |
| Introspection endpoint bị chiếm | RS có thể bị đánh lừa `active=true`/claims tùy trust channel |
| Refresh token random bị lộ trực tiếp | Attacker có credential để thử refresh, chịu client binding/rotation/sender constraint |

Không nói “opaque token luôn revoke ngay” nếu RS cache introspection `active=true`; phải đo cache TTL và state propagation.

### 15.2. Thu hồi key khác thu hồi grant/refresh family

Một JWT signing key bị lộ cần distrust key ở RS/RP. Một refresh token bị lộ cần:

- Revoke token/family/grant tại AS.
- Phát hiện reuse trong rotation nếu có.
- Chặn cấp access token mới.
- Đánh giá access tokens còn hạn và propagation.
- Phòng bearer token theft bằng storage/sender constraint và TTL.

Nếu cả signing key và refresh token đều bị compromise, phải ứng cứu **hai ranh giới**. Không dùng rotation K1 để hy vọng refresh token R1 tự mất hiệu lực, trừ khi có cơ chế state thực sự làm điều đó.

### 15.3. Key compromise có thể kéo theo subject/client impersonation

Nếu AS dùng cùng signing key cho access token và ID token, attacker có thể nhắm tới cả:

- API authorization (forged JWT access tokens), và
- RP login/account linking (forged ID tokens nếu đường xác thực/profile bị vượt qua).

Phải đánh giá từng **token type và audience** cụ thể, không chỉ một Endpoint `/userinfo` hay Orders API.

## 16. Java/Spring Security: khóa JWT phải được tin theo cấu hình, không theo token

Ứng dụng Spring Security OAuth2 Resource Server có thể dùng JWT decoder xác minh JWT từ **một issuer đáng tin**. Để ứng cứu key compromise, cần phối hợp **JWKS trust state, algorithm allowlist và security policy freshness**, ngoài các validators `iss`, `aud`, `exp`.

### 16.1. Cấu hình issuer và audience

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

**Không coi `issuer-uri` đơn lẻ là chứng minh audience, business authorization hoặc early key distrust đã được hoàn tất.** Framework có thể tự discover JWKS/issuer metadata và cache public keys theo cấu hình; hãy biết cache policy thật.

Một API Orders cần kiểm:

~~~text
Allowed issuer:
    https://login.example.com

Expected audience:
    https://orders.example.com

Allowed signing algorithms:
    RS256 theo hợp đồng issuer

Key trust:
    chỉ các public keys issuer còn được tin
    và không nằm trong emergency blocked state

Business policy:
    subject/action/order/tenant được phép
~~~

### 16.2. Custom validator chỉ là **một lớp**

Đoạn Java dưới đây minh họa chặn `kid` bị cảnh báo **sau khi JWT decoder xác minh chữ ký**. Nó không tự phát hiện attacker đổi alias `kid`, không tự xóa JWKS cache và **không thay việc loại bỏ key material K1**.

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
public class OrdersJwtSecurityConfig {

    private static final String ISSUER =
        "https://login.example.com";
    private static final String JWKS =
        "https://login.example.com/.well-known/jwks.json";
    private static final String AUDIENCE =
        "https://orders.example.com";

    @Bean
    JwtDecoder jwtDecoder(EmergencyKeyPolicy keyPolicy) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return fail("Wrong audience");
        };

        OAuth2TokenValidator<Jwt> emergencyKidGuard = jwt -> {
            Object kid = jwt.getHeaders().get("kid");

            // Đây chỉ là lớp phụ trợ bằng key ID; production còn phải
            // distrust key material K1 trong trusted JWKS / key resolver.
            if (!(kid instanceof String)
                    || keyPolicy.isBlocked(ISSUER, (String) kid)
                    || !keyPolicy.isFreshEnough()) {
                return fail("Signing key not trusted");
            }
            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator,
                emergencyKidGuard));

        return decoder;
    }

    private static OAuth2TokenValidatorResult fail(String reason) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", reason, null));
    }
}
~~~

`EmergencyKeyPolicy` là **interface ứng dụng tự xây**, không phải Spring Security API. Cần kiểm soát nguồn chính sách, TTL, consistency và fail mode. Ví dụ này minh họa rõ:

1. Decoder chỉ chấp nhận thuật toán **RS256** đã phê duyệt.
2. Expected issuer được kiểm qua default validator.
3. Audience Orders API được kiểm riêng.
4. Emergency key policy được hỏi trước khi chấp nhận JWT.
5. **Điều cốt yếu vẫn là trust set của decoder phải thực sự loại bỏ compromised public key material** và cập nhật mọi cache.

Một blocklist chỉ theo `kid` là **defense in depth**, không phải giải pháp hoàn chỉnh. Nếu K1 được publish lại dưới alias khác hoặc một verifier tự fallback sang khóa mặc định, cần khóa trust ở **public key fingerprint/key resolver layer**.

### 16.3. Không cho token tự chọn nguồn khóa

Sai:

~~~java
// Pseudocode SAI: không dùng trong hệ thống thật.
String url = parseUnverifiedJwtHeader(rawToken).jku();
JWKSet keys = downloadAnyUrl(url);
verify(rawToken, keys);
~~~

Đúng hướng:

~~~java
// Pseudocode kiến trúc:
TrustedIssuer issuer =
    trustedIssuerRegistry.getExpectedIssuerForApi("orders-api");

KeyTrustSnapshot snapshot =
    trustStore.requireFreshSnapshot(issuer.id());

VerifiedJwt jwt = jwtVerifier.verify(
    rawToken,
    issuer.configuredJwksEndpoint(),
    issuer.allowedAlgorithms(),
    snapshot.allowedPublicKeyFingerprints());

authorizationService.requireAudience(jwt, "orders-api");
authorizationService.requireActionOnResource(jwt, action, resource);
~~~

`TrustedIssuer`, `KeyTrustSnapshot`, `VerifiedJwt`, `jwtVerifier` là **pseudocode**, không phải Spring classes. Trong implementation thật, key resolver và signature verification phải liên kết khóa thực tế đã được dùng với fingerprint đáng tin; không lấy trust từ JWT chưa xác minh.

### 16.4. Cấu hình public keys không đồng nghĩa phát hành credential

Resource Server chỉ cần public verification keys; **không cần biết AS private key** để kiểm chữ ký. Nếu ứng dụng yêu cầu đưa KMS signing credential cho Orders API để “verify JWT”, đó là dấu hiệu sai kiến trúc.

### 16.5. `scope` và quyền nghiệp vụ vẫn cần kiểm

~~~java
// Pseudocode Spring MVC + method security, chưa phải full production app.
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
@GetMapping("/api/orders/{orderId}")
public OrderDto read(
        @PathVariable String orderId,
        Authentication authentication) {
    VerifiedActor actor =
        actorMapper.fromValidatedAuthentication(authentication);

    return orderService.readIfAuthorized(actor, orderId);
}
~~~

Kể cả JWT ký K2 và không bị revoke, API vẫn phải kiểm subject/tenant/owner. Key rotation không sửa BOLA/IDOR.

### 16.6. Khi state service lỗi phải có fail mode rõ

Nếu `EmergencyKeyPolicy.isFreshEnough()` không truy cập được key registry:

- Không mặc định `true` vô hạn.
- Có thể dùng local **signed/trusted snapshot** trong hard freshness deadline.
- Với endpoints nhạy cảm, khi quá deadline nên **fail closed** hoặc tạm không phục vụ.
- Phân biệt “JWT có chữ ký sai” với “key trust service outage” trong audit/telemetry, tránh gây hiểu nhầm.

HTTP 401/503 cụ thể cần phù hợp policy/hợp đồng API; điều bắt buộc là **không ALLOW khi không đủ chứng cứ trust theo security requirement**.

## 17. Java pseudocode: phát token bằng KMS mà không đưa private key cho ứng dụng

Một phương án thực tế là AS request KMS ký dữ liệu JWT theo **purpose và issuer được phê duyệt** thay vì tải raw private key vào container.

~~~java
// Pseudocode kiến trúc; KHÔNG phải AWS/GCP/Azure KMS SDK cụ thể.
SignedToken issueAccessToken(
        VerifiedGrant grant,
        TrustedIssuer issuer,
        KeyRegistry registry,
        KmsSigner kms) {

    SigningKeyRef active = registry.requireActiveKey(
        issuer.id(), "JWT_ACCESS_TOKEN");

    issuerPolicy.requireGrantAllowed(grant, issuer);
    issuerPolicy.requireSigningKeyAllowed(active, issuer);

    JwtHeader header = JwtHeader.forApprovedAlgorithm(
        active.keyId(), "RS256", "at+jwt");
    JwtClaims claims = claimIssuer.buildBoundAccessTokenClaims(
        grant, issuer, clock.instant());

    byte[] signingInput = jwtEncoder.encodeSigningInput(
        header, claims);

    // Service chỉ có quyền ký bằng đúng key/purpose,
    // không có quyền export hay thay issuer trust policy.
    byte[] signature = kms.sign(
        active.kmsReference(),
        signingInput,
        "RSASSA_PKCS1_V1_5_SHA_256");

    return jwtEncoder.compose(header, claims, signature);
}
~~~

**Quan trọng:** `JwtHeader`, `JwtClaims`, `KmsSigner` và các helpers là type **minh họa**, không phải implementation hoàn chỉnh. Trong KMS thật, thuật toán ký, hash/prehashed data và JWS encoding phải khớp chính xác contract KMS và JOSE. Với RSA-PSS/EC/EdDSA, không được tự áp encoding của RS256.

### 17.1. Nếu IAM của AS bị compromise?

Kể cả KMS non-exportable, attacker có quyền gọi `Sign` có thể ký payload giả. Vì vậy cần:

- IAM role chỉ được ký key đúng purpose/issuer, giới hạn nơi gọi khi khả thi.
- Phân tách quyền **Sign** và **Disable/Rotate/Publish JWKS**.
- Audit logs được gửi ra hệ thống độc lập, chống xóa/sửa bởi service principal ký.
- Giám sát request rate, principal, region, key version và anomaly.
- Với signing of arbitrary bytes, cân nhắc tầng token issuance policy tin cậy trước KMS, không trao API ký tùy ý cho consumer.

### 17.2. Tái cấp khóa mới sau compromise

Pseudocode workflow:

~~~text
Incident declares K1 compromised.
    |
Security disables K1 Sign privilege.
    |
KMS generates non-exportable K2.
    |
Key Registry marks K2 pending.
    |
JWKS publishes K2 public to trusted endpoint.
    |
AS switches token issuance to K2.
    |
Security policy blocks K1 verification in RS/RP.
    |
Every verifier applies monotonic policy version.
    |
Test tokens signed K1 => REJECT.
Test tokens signed K2 => ACCEPT (with valid claims).
    |
Close incident only after enforcement evidence.
~~~

Không dùng một `kid` mới nhưng key bytes cũ. Không khôi phục K1 từ backup sau khi đã đánh dấu compromised.

### 17.3. Sơ đồ bảo vệ khóa

~~~mermaid
flowchart TD
    A[Verified OAuth Grant] --> B[AS Issuance Policy]
    B --> C[Trusted Key Registry]
    C --> D[KMS Sign by constrained IAM role]
    D --> E[JWT K2]
    E --> F[Resource Server]
    F --> G[Trusted Issuer + JWKS + Key Trust]
    G --> H{K2 still trusted and token valid?}
    H -- No --> X[Reject / fail closed]
    H -- Yes --> I[Business authorization]
    I --> J{Allowed on resource?}
    J -- No --> X
    J -- Yes --> K[Allow]
    L[Security Incident Controller] --> M[Monotonic Emergency Block K1]
    M --> G
~~~

Sơ đồ cho thấy **key trust** và **business authorization** là hai cổng riêng, cả hai phải vượt qua.

## 18. Dữ liệu, audit và event-driven distrust trong hệ thống phân tán

Một incident không kết thúc khi người vận hành đổi cấu hình tại một AS node. Mọi verifier cần nhìn cùng **security policy** và không được bị snapshot/replica cũ ghi đè.

### 18.1. Schema key registry minh họa

~~~sql
-- Khái niệm cho nội bộ; không phải schema chuẩn JOSE/OAuth.
CREATE TABLE signing_keys (
    issuer_id VARCHAR(256) NOT NULL,
    key_fingerprint VARCHAR(256) NOT NULL,
    key_id VARCHAR(128) NOT NULL,
    kms_key_reference VARCHAR(512),
    algorithm VARCHAR(32) NOT NULL,
    purpose VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    activated_at TIMESTAMP,
    blocked_at TIMESTAMP,
    security_version BIGINT NOT NULL,
    PRIMARY KEY (issuer_id, key_fingerprint)
);

CREATE TABLE security_events_outbox (
    event_id VARCHAR(128) PRIMARY KEY,
    issuer_id VARCHAR(256) NOT NULL,
    aggregate_fingerprint VARCHAR(256) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    security_version BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Các giá trị status có thể được định nghĩa như:

~~~text
PENDING
ACTIVE
RETIRING
RETIRED
COMPROMISED
BLOCKED
~~~

**Không tự cho phép `BLOCKED -> ACTIVE`** vì một bản backup/management API gửi giá trị `ACTIVE` cũ. Để phục hồi hệ thống, phát **khóa/generation mới**, không hồi sinh key material K1 đã compromise.

### 18.2. Transaction ghi policy và outbox

~~~sql
-- Pseudocode transaction; cần authorization, version locking, kiểm rows.
BEGIN;

UPDATE signing_keys
SET status = 'COMPROMISED',
    blocked_at = CURRENT_TIMESTAMP,
    security_version = :next_version
WHERE issuer_id = :issuer_id
  AND key_fingerprint = :fingerprint
  AND status <> 'COMPROMISED'
  AND security_version < :next_version;

INSERT INTO security_events_outbox (
    event_id,
    issuer_id,
    aggregate_fingerprint,
    event_type,
    security_version,
    created_at
) VALUES (
    :event_id,
    :issuer_id,
    :fingerprint,
    'SIGNING_KEY_DISTRUST',
    :next_version,
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Trong production, **không insert event cho một UPDATE không thực sự đổi state** nếu nghiệp vụ yêu cầu exactly-once logical transition. Dùng transaction, unique event IDs và optimistic locking/row locks hoặc cơ chế kiểm soát đồng thời phù hợp.

### 18.3. Event schema không chứa secret

~~~json
{
  "event_id": "evt-key-2026-001",
  "type": "SIGNING_KEY_DISTRUST",
  "issuer_id": "login-prod",
  "public_key_thumbprint": "thumbprint-of-K1",
  "kid_hints": ["issuer-k1"],
  "policy_version": 18,
  "reason_code": "PRIVATE_KEY_EXPOSURE",
  "occurred_at": "2026-11-23T03:00:00Z"
}
~~~

Đây là event nội bộ minh họa, **không phải RFC standard event**. Event producer cần được xác thực và được ủy quyền thay issuer trust policy. Verifiers cần phân biệt event **ngừng tin** với event **bổ sung khóa public mới**; không cho attacker tự đăng “KX trusted” bằng quyền publish không kiểm soát.

### 18.4. Consumer xử lý version và idempotency

~~~java
// Pseudocode: Store, EventVerifier, BrokerOffset là helpers.
void applyEmergencyKeyEvent(SecurityEvent event) {
    eventVerifier.requireTrustedPublisher(event);
    eventVerifier.requireValidSchemaAndIssuer(event);

    trustPolicyStore.transaction(() -> {
        TrustState current = trustPolicyStore.lockIssuer(event.issuerId());

        if (event.policyVersion() <= current.version()) {
            return; // duplicate hoặc stale event
        }

        if (!"SIGNING_KEY_DISTRUST".equals(event.type())) {
            throw new UnsupportedSecurityEventException();
        }

        trustPolicyStore.blockFingerprint(
            event.issuerId(),
            event.publicKeyThumbprint(),
            event.policyVersion());

        // Phải chặn stale trust ngay, không chỉ gửi cache-evict.
        trustedJwksCache.invalidateIssuer(event.issuerId());
    });

    brokerOffset.ackAfterDurableApply(event.eventId());
}
~~~

**Tính nguyên tử** giữa durable state, cache invalidation và broker ack phụ thuộc implementation. Nếu `invalidateIssuer` không thể transaction cùng DB, cần đảm bảo **mọi request tới verifier kiểm policy version/fingerprint** hoặc có replay/reconciliation trước khi allow. Không tuyên bố exactly-once chỉ vì broker có một config tùy chọn.

### 18.5. Chống trust cache fill race

~~~text
t0: RS bắt đầu fetch JWKS cũ chứa K1.
t1: Event v18 BLOCKED K1 đến, RS xóa cache.
t2: Fetch t0 về muộn, ghi JWKS cũ có K1 vào cache.
t3: Attacker gửi token ký K1.
~~~

Nếu trust resolver chỉ dựa vào cache cũ, đây là lỗ hổng **stale cache fill**. Cần:

- Trust snapshot mang version/checkpoint.
- Tách **deny/block state monotonic** khỏi cache JWKS có thể stale.
- Không cho cache với version cũ ghi đè security policy v18.
- Kiểm policy ngay tại verifier hoặc đã kết hợp vào trusted key resolver.
- Fail closed nếu không thể chứng minh trust state đủ mới theo action.

### 18.6. Bootstrap một RS mới

Node mới scale-out từ image cũ có thể chứa public K1 trong local trust cache. Trước khi đưa node vào load balancer:

1. Tải **trusted security policy snapshot** với high-watermark hiện tại.
2. Đồng bộ JWKS từ issuer tin cậy.
3. Chứng minh fingerprint K1 bị chặn dù key còn có ở local artifact.
4. Chỉ đặt readiness `true` nếu policy freshness đạt.
5. Theo dõi consumer events/replay sau snapshot, không subscribe `latest` rồi bỏ qua history.

Một node “cache rỗng nên mọi key đều hợp lệ” là cấu hình fail-open nguy hiểm.

## 19. Observability, chỉ số và dữ liệu cần bảo vệ

### 19.1. Chỉ số quan trọng

| Chỉ số | Câu hỏi trả lời |
|---|---|
| `kms_sign_calls_by_key_principal` | Ai đang gọi sign, từ đâu, nhiều bao nhiêu? |
| `jwt_signer_key_version` | AS đang ký bằng key/version nào? |
| `jwks_publication_version` | Key set công khai thuộc phiên bản nào? |
| `rs_key_trust_policy_version` | RS đã áp emergency policy mới nhất chưa? |
| `compromised_key_rejections` | Các verifiers có từ chối token khóa K1 không? |
| `last_trust_sync_age` | State của node hiện đã stale bao lâu? |
| `key_event_consumer_lag` | Event bus/consumer có bị chậm? |
| `jwt_signature_or_alg_errors` | Có surge token giả hoặc config mismatch? |
| `access_token_minted_without_issuance_record` | Có dấu hiệu issuer signing abuse không, khi issuance record đáng tin? |
| `sensitive_actions_by_claimed_subject` | Có hành động API bất thường theo actor/tenant không? |

Không dùng **average propagation 100 ms** để tuyên bố đã an toàn nếu một RS ở region xa vẫn ALLOW K1 trong nhiều phút. Theo dõi **P95/P99/outliers và max stale age**.

### 19.2. Log những gì và tránh những gì?

Có thể ghi theo policy:

~~~text
traceId
trustedIssuerId
keyReference hoặc publicKeyFingerprint
clientRegistrationId
tokenType
resourceServerId / region
policyVersion
validationDecision=ALLOW|REJECT
rejectionCategory=KEY_BLOCKED|UNKNOWN_KID|ALGORITHM_REJECTED
securityEventId
issuedAt/expiry category khi được phép
~~~

Không ghi:

~~~text
privateSigningKey
HMACSecret
DPoPPrivateKey
mTLSPrivateKey
Authorization: Bearer <ACCESS_TOKEN>
refresh_token=<REFRESH_TOKEN>
client_secret=<SECRET>
IDToken=<SIGNED_JWT_WITH_PII>
KMS credential
~~~

Public key fingerprint, `kid`, issuer, subject, IP và clientId cũng có thể là metadata nhạy cảm. Dùng retention, access controls và data minimization; không gửi raw JWT vào crash traces.

### 19.3. Tránh ghi raw JWT làm chứng cứ

Raw JWT có thể chứa thông tin cá nhân và là bearer credential nếu là access token. Khi điều tra:

- Dùng token ID đáng tin hoặc **HMAC token fingerprint** với khóa quản lý riêng.
- Có thể lưu metadata của signature verification result, public key fingerprint và claims categories.
- Nếu bắt buộc lưu mẫu độc hại để phân tích, đặt trong evidence vault hạn chế, retention ngắn và kiểm soát truy cập nghiêm ngặt.
- Không paste token hoặc private key vào issue tracker để mọi người xem.

Không xem **SHA-256 không khóa của token** là ẩn danh hoàn toàn; tùy loại token và khả năng đoán, có thể liên kết dữ liệu. HMAC với secret riêng thường phù hợp hơn cho correlation logs.

### 19.4. Không thể kết luận “đã an toàn” chỉ từ một dashboard

Một metric:

~~~text
AS signing_key = K2
~~~

chỉ chứng minh AS node báo đang phát hành K2; không cho biết:

- Có AS instance khác vẫn ký K1 hay không.
- KMS Sign của K1 đã bị chặn với attacker chưa.
- RS caches có còn tin K1 không.
- RP đã từ chối ID token K1 không.
- Dữ liệu nào đã bị tấn công trước đó.

Chỉ có **enforcement evidence** và phạm vi inventory đầy đủ mới hỗ trợ kết luận sự cố đã được khống chế.

## 20. Threat model: những lỗi khiến key compromise lan rộng

| Mối đe dọa / sai lầm | Điều có thể xảy ra | Kiểm soát quan trọng |
|---|---|---|
| **Lộ private signing key** | Attacker tạo JWT/ID token có chữ ký hợp lệ | Emergency distrust key ở mọi verifier |
| **HMAC secret dùng chung nhiều RS** | Compromise một RS biến thành khả năng ký token | Asymmetric signatures hoặc giới hạn secret scope |
| **KMS Sign IAM bị chiếm** | Ký giả dù key không export được | Constrained IAM, key policy, KMS usage audit |
| **JWKS publisher bị chiếm** | Attacker thay public key được các RS tin | Protect publication, issuer binding, review/audit |
| **Issuer discovery bị thay** | Verifier nhận JWKS từ issuer lạ | Trusted issuer metadata, TLS, config integrity |
| **JWT `jku`/`x5u` tùy ý** | Fetch khóa attacker hoặc SSRF | Không trust header URL, use configured key set |
| **`alg=none`** | JWT được chấp nhận không chữ ký | Hard algorithm allowlist, proper JWT library |
| **HS/RS algorithm confusion** | Dùng public key như HMAC secret | Enforce key type và approved algorithm |
| **Nhầm `kid` là key trust** | Key giả với `kid` bất kỳ được chấp nhận | Bind to trusted issuer/public key fingerprint |
| **Đổi `kid` nhưng giữ key material** | Attacker vẫn ký được bằng K1 private | Sinh K2 mới, kiểm fingerprint |
| **Sử dụng key chung dev/prod** | Leak staging ảnh hưởng production | Separate environments and purposes |
| **Lộ JWE decryption key** | Lộ claims bí mật trong ciphertext | Data breach response, re-encryption/key renewal |
| **Lộ DPoP holder key** | Attacker có thể tạo proof cho token binding | Revoke bound tokens/key, device response |
| **Lộ mTLS client key** | Giả client/certificate holder | Cert replacement, trust revocation, token rebinding |
| **Lộ `private_key_jwt` client key** | Giả OAuth client tại token endpoint | Rotate client key, block client assertions |
| **Signing key trong Docker image** | Mọi ai có image/registry access có thể lấy khóa | Non-exportable KMS/HSM, image scanning |
| **Secret xuất hiện trong logs** | Thêm nhiều bản sao secret tại SIEM/analytics | Redaction, access control, key rotation |
| **Private key trong backup cũ** | Leak/restore làm key bị giữ quá lâu | Encrypted backups, retention và emergency purge |
| **JWKS cache còn K1** | RS tiếp tục nhận token giả sau AS rotate | Emergency invalidation và trust policy freshness |
| **CDN cache JWKS stale** | Một số verifiers cập nhật muộn | Cache purge và propagation metrics |
| **RS subscribe event từ latest** | Không biết K1 đã bị blocked trước khi khởi động | Snapshot/replay/high-watermark readiness |
| **Out-of-order trust event** | `ACTIVE` v17 ghi đè `BLOCKED` v18 | Monotonic versions/tombstones |
| **Cache fill race** | K1 quay lại cache sau invalidation | Version-aware cache writes và block state riêng |
| **Network partition fail-open** | Một region vẫn tin K1 vô hạn | Freshness deadline/fail closed risk policy |
| **Chỉ denylist một `jti`** | Attacker đổi jti và ký JWT khác | Distrust signer, hoặc authoritative issuance check |
| **Chỉ lọc `iat > T_detect`** | Attacker backdate iat trên JWT giả | Không dùng claims tự khai làm bằng chứng issuance |
| **Chỉ revoke refresh token** | JWT giả vẫn có thể được RS chấp nhận | Xử lý signing key trust độc lập với grant |
| **Business policy chỉ tin role claim** | Token giả có role admin được dùng | Token trust + current role/resource policy |
| **OP và AS dùng chung signing key** | Rủi ro login và API cùng lúc | Key separation hoặc đánh giá cả hai profiles |
| **Emergency đổi khóa gây outage** | RS không biết K2 và từ chối mọi token | Preplanned distribution, rollback an toàn không re-trust K1 |

### 20.1. Đừng dùng một phản hồi “401” làm kết luận tổng thể

Một token giả bị từ chối tại Orders API có thể do **audience sai**, không phải vì Orders API đã ngừng tin K1. Để kiểm emergency distrust, cần test có kiểm soát so sánh:

~~~text
T_K1:
    claims hợp lệ cho Orders API, chữ ký K1 -> REJECT do K1 blocked.

T_K2:
    claims tương ứng, chữ ký K2 -> ACCEPT nếu grant/policy hợp lệ.

T_wrong_aud:
    chữ ký K2, aud sai -> REJECT do audience.
~~~

Chỉ khi biết nguyên nhân và token profile được xây đúng mới có thể kết luận **key trust đã được cập nhật**.

### 20.2. Không để policy `unknown key` mặc định trust

Một custom verifier không được xử lý:

~~~text
if kid not found:
    download arbitrary key URL from JWT
    or skip verification
    or try every HMAC secret
~~~

Đúng là **reject** nếu không có khóa phù hợp trong **trust set được phép**; chỉ refresh JWKS theo một issuer/URL đã cấu hình và algorithm policy, không do JWT chưa tin quyết định.

## 21. Ma trận kiểm thử key compromise, rotation và propagation

Một unit test chỉ xác nhận JWT K2 verify thành công không đủ. Cần kiểm cả **đường ký**, **đường xác minh**, **key distribution** và **security incident lifecycle**.

### 21.1. JWT/JWS verification

| Test | Kết quả mong muốn |
|---|---|
| JWT K2 còn hiệu lực, issuer/audience đúng | Có thể qua token validation, tiếp tục business authorization |
| JWT K1 trước emergency, K1 bị BLOCKED | RS từ chối theo key trust policy |
| JWT K1 attacker ký sau emergency, `exp` tương lai | RS từ chối dù claims/time hợp lệ |
| JWT K1 với `iat` trước thời điểm phát hiện | RS từ chối; không trust backdated iat |
| JWT K1 đổi `kid` nhưng key material vẫn K1 | RS từ chối dựa trust resolver/key fingerprint |
| JWT có `alg=none` | Từ chối |
| JWT `alg=HS256` khi RS chỉ cho RS256 | Từ chối, không HS/RS confusion |
| JWT `jku` trỏ tới attacker URL | Không fetch arbitrary URL hoặc tin key đó |
| JWT `x5u` trỏ internal metadata service | Không SSRF/tin key ngoài configured trust |
| JWT không có key match trong trust set | Từ chối |
| JWT K2 chữ ký đúng nhưng sai `iss` | Từ chối |
| JWT K2 chữ ký đúng nhưng sai `aud` | Từ chối |
| JWT K2 hết `exp` hoặc `nbf` tương lai | Từ chối |
| JWT ID token gửi làm access token | RS từ chối sai token type/audience |
| JWT access token gửi tới OIDC client như ID token | Client từ chối sai token type/profile |
| Token ký từ issuer A dùng `kid` giống issuer B | Không trộn key sets giữa issuers |
| Key K1 xuất hiện dưới hai `kid` trong JWKS | Tất cả references tới K1 đều bị chặn |
| Token có `scope=admin` từ key K2 hợp lệ nhưng principal thiếu quyền resource | Business policy từ chối |

### 21.2. KMS, CI/CD và key lifecycle

| Test | Kết quả mong muốn |
|---|---|
| App AS cần `KMS Sign` cho đúng issuer/purpose | Chỉ được ký bằng key được cấp |
| RS thử gọi KMS Sign | Từ chối; RS chỉ có public verification keys |
| IAM role không thuộc AS thử export/sign K1 | Từ chối và cảnh báo |
| KMS key non-exportable | Không có API export raw private key |
| KMS Sign từ region/role bất thường | Alert và containment process |
| Build artifact chứa private key/secret | Pipeline security check fail |
| Secret scanner tìm private JWK trong repo | Alert; xử lý compromise, không chỉ xóa commit |
| K1 rotate sang K2 với fingerprint giống | Test fail: key material không đổi |
| K1 planned rotation, token còn hạn | Hệ thống chấp nhận K1 theo rollout policy trước retire |
| K1 emergency compromise | Phải ngừng tin K1 trước/đúng emergency SLO |
| Backups chứa K1 private sau incident | Điều tra retention/physical purge/access, không tái dùng |
| Restore snapshot có K1 ACTIVE | Reconciliation không cho hồi sinh |
| KMS alias bị đổi tới K1 sau emergency | Policy/registry chặn sử dụng lại K1 |
| JWKS publisher không thuộc trusted pipeline | Từ chối thay key set |

### 21.3. JWKS/Resource Server phân tán

| Test | Kết quả mong muốn |
|---|---|
| AS ngừng publish K1 | Mỗi RS/RP cập nhật trust trong SLO |
| CDN giữ JWKS có K1 | Purge hoặc local block policy chặn K1 |
| RS cache JWKS K1 quá TTL | Freshness policy phát hiện và xử lý |
| RS nhận distrust event hai lần | Idempotent, không giảm policy version |
| RS nhận ACTIVE v17 sau BLOCKED v18 | Không hồi sinh K1 |
| RS fetch JWKS v17 chậm sau event v18 | Cache fill không làm K1 trusted trở lại |
| RS mới scale-out từ image cũ chứa K1 | Readiness yêu cầu policy snapshot v18 hoặc fail closed |
| RS restart trong khi event bus offline | Fallback/snapshot và fail mode theo policy |
| Region B bị partition 20 phút | Không ALLOW K1 ngoài freshness budget đã phê duyệt |
| Consumer crash sau apply trước ack | Replay an toàn |
| Outbox publish bị lỗi sau DB commit | Retry và reconcile đảm bảo event cuối cùng tới consumer |
| Policy registry replica chậm | Có consistency/freshness guarantee phù hợp |
| Một RS không nằm trong event consumer group | Inventory/test phát hiện missing enforcement point |
| JWKS URI bị redirect tới host lạ | Không trust ngoài configured issuer/TLS policy |
| RP login verifier còn K1 dù APIs đã block | Test fail nếu ID token K1 còn được tin trái incident scope |

### 21.4. Các loại key khác và token security

| Test | Kết quả mong muốn |
|---|---|
| Public JWK được tải từ JWKS | Bình thường, không coi là private-key leak |
| Private JWK chứa `d` bị xuất ra public | Incident nghiêm trọng, emergency distrust |
| Client `private_key_jwt` private key lộ | AS chặn assertion từ key cũ, rekey client |
| DPoP-bound token chỉ bị lộ token string, không có private key | RS kiểm proof/binding để chống replay |
| DPoP holder key bị compromise | Revoke/rebind tokens và điều tra device/client |
| DPoP proof sai `htu`/`htm`/`ath` | Từ chối |
| DPoP proof `jti` replay | Từ chối theo replay/nonce policy |
| mTLS client certificate/private key bị lộ | Cert/key rotate; endpoint cập nhật trust |
| JWE decryption key lộ | Đánh giá confidentiality của ciphertext, re-encrypt khi cần |
| Refresh token opaque random còn sống sau JWT signing key rotation | Chỉ bị revoke nếu AS grant/token state xử lý, không giả định mất hiệu lực |
| Introspection trả `active=true` nhưng audience sai | RS vẫn từ chối |
| Access token K2 có scope phù hợp nhưng resource tenant khác | Từ chối theo business authorization |
| Signing key K1 lộ và refresh family cũng bị lộ | Xử lý cả key trust và grant/token revocation |

### 21.5. Một bài chaos test có ý nghĩa

1. Tạo K1/K2 **fixture keys** trong môi trường test, không dùng private key production.
2. Phát test JWT có `iss`, `aud`, `scope`, `exp` hợp lệ bằng K1, xác minh các RS nhận đúng trước incident.
3. Đánh dấu K1 `COMPROMISED/BLOCKED` trong authoritative key registry, ghi timestamp commit.
4. Đảm bảo AS không còn ký K1, phát test JWT hợp lệ bằng K2.
5. Gửi token K1 đã phát hành và token K1 mới tự ký với `iat` backdated tới **mọi** verifier test.
6. Chặn/pause event broker tại một region, tạo JWKS cache cũ và CDN cache stale có K1.
7. Scale-out một RS mới từ image trước emergency và kiểm readiness/trust snapshot.
8. Inject consumer duplicate/out-of-order events và cache fill race.
9. Xác minh **mọi RS từ chối K1**, token K2 hợp lệ đi qua crypto nhưng business policy vẫn enforce.
10. Đo lag từ security commit tới enforcement ở node/region chậm nhất.
11. Quan sát fail mode khi không đồng bộ key trust và đối chiếu SLO.
12. Kiểm logs, traces và test reports **không chứa private key hoặc raw JWT tokens**.

**Không thử mint token bằng khóa bị nghi lộ trên production và gọi API thật** nếu không có kế hoạch kiểm thử bảo mật được cấp phép. Sử dụng fixture/synthetic environment và quy trình red team/incident được phê duyệt.

## 22. Tình huống suy luận: nhận diện đúng khóa và ranh giới bị ảnh hưởng

### Tình huống A — Public JWKS bị tải công khai

Security thấy người ngoài tải `https://login.example.com/.well-known/jwks.json`, trong đó có RSA `n`, `e`, `kid`.

**Câu hỏi:** Đây có phải lộ signing private key?

**Trả lời:** Không chỉ từ việc đó. JWKS public keys thường được **công bố để các RS/RP xác minh chữ ký**. Cần xác minh không có private fields như `d`, không có key substitution và endpoint metadata được bảo vệ.

### Tình huống B — Private key xuất hiện trong CI artifact

Một build artifact có `private-key.pem` của AS production, được nhiều developer tải về.

**Câu hỏi:** Chỉ xóa artifact có đủ không?

**Trả lời:** Không. Phải coi key material có khả năng bị lộ; xác định người/đường truy cập, chặn signing capability, sinh K2 mới, ngừng trust K1 tại mọi RS/RP và đánh giá token giả/truy cập API. Xóa artifact không xóa mọi bản sao đã tải.

### Tình huống C — KMS không cho export private key

K1 non-exportable nhưng attacker chiếm được IAM role có quyền `Sign`.

**Câu hỏi:** Có thể nói “không có compromise vì private key chưa xuất” không?

**Trả lời:** Không. Attacker có thể **lạm dụng signing capability** để tạo chữ ký hợp lệ. Cần revoke IAM, kiểm KMS audit, sửa token issuance boundary, rotate/distrust K1 theo incident scope.

### Tình huống D — JWT backdated trước khi phát hiện

Security phát hiện K1 bị lộ lúc 10:00. Attacker ký JWT lúc 10:05 nhưng tự đặt `iat=09:00`.

**Câu hỏi:** Có nên chấp nhận tất cả token `iat<10:00` không?

**Trả lời:** Không. `iat` do attacker có K1 ký giả được. Cần ngừng trust K1 hoặc kiểm issuance provenance độc lập; timestamp phát hiện không phải bằng chứng token được AS tạo trước đó.

### Tình huống E — Đổi `kid` nhưng giữ nguyên private key

AS đổi header `kid=issuer-2026-11` thành `kid=issuer-2027-01` nhưng vẫn dùng K1_private.

**Câu hỏi:** Đã khắc phục compromise chưa?

**Trả lời:** Chưa. Material vẫn là K1. Attacker tiếp tục tạo chữ ký tương ứng; K2 cần có key material thật sự mới, fingerprint khác và signing privileges được kiểm soát.

### Tình huống F — AS ngừng ký K1, Orders API vẫn tin K1

AS đã chuyển K2; Orders API cache JWKS có K1 thêm 30 phút.

**Câu hỏi:** Attacker còn có thể dùng JWT K1 giả không?

**Trả lời:** Có thể nếu RS vẫn chấp nhận chữ ký K1 và attacker đặt các claims phù hợp. Cần emergency block/invalidate trust ở RS, không chỉ thay key issuance tại AS.

### Tình huống G — JWT giả không có trong issuance log

Orders API nhận JWT ký K1, `jti=X123`. AS issuance database không có X123.

**Câu hỏi:** Đây chắc chắn là forgery?

**Trả lời:** Là tín hiệu rất đáng nghi nhưng phải kiểm xem logs/store có authoritative và đầy đủ không. Khi signing key đã bị compromise, một issuance allowlist độc lập có thể giúp chặn/điều tra; không chỉ dựa trên log sampling.

### Tình huống H — JWT ký K1 có scope admin

Attacker dùng private K1 tạo token với `scope=admin` và `aud=orders-api`.

**Câu hỏi:** Kiểm chữ ký, audience và scope có đủ không?

**Trả lời:** Không nếu K1 đã mất trust. Claims có thể do attacker tự chọn. RS phải distrust K1 và còn áp business authorization độc lập đối với action/resource/tenant.

### Tình huống I — `jti` denylist hoạt động với T1

Security denylist token `jti=T1`. Attacker có signing key K1 tạo T2 với `jti=T2`.

**Câu hỏi:** Có thể chặn toàn bộ forgery bằng cách chỉ denylist T1 không?

**Trả lời:** Không. Attacker có thể tạo vô hạn token IDs mới. Cần loại K1 khỏi trust set hoặc một cơ chế issuance authorization độc lập đủ mạnh, không chỉ blacklist vài `jti`.

### Tình huống J — Verifier tự tải JWK URL trong token

JWT header có `jku=https://attacker.example/jwks.json`. Verifier lấy key từ đó rồi chấp nhận chữ ký.

**Câu hỏi:** Đây là lỗi gì?

**Trả lời:** Key-source trust confusion. JWT chưa được xác minh không được tự chọn public key trust root; cũng có nguy cơ SSRF. Chỉ tin JWKS từ issuer/configuration đã được kiểm soát.

### Tình huống K — HS256 secret được gửi tới vendor

Orders API dùng HS256, vendor được cấp chung HMAC secret để verify tokens.

**Câu hỏi:** Nếu vendor bị compromise thì sao?

**Trả lời:** Vendor nắm secret có thể tạo MAC như issuer. Nên xem xét asymmetric signing cho RS đối tác và key separation, hoặc ít nhất giới hạn trust/rotate secret và điều tra mọi bên giữ nó.

### Tình huống L — Key để giải mã JWE bị lộ

Recipient private key giải mã JWE bị lộ, nhưng JWT bên trong được ký bằng private signing key khác không bị lộ.

**Câu hỏi:** Attacker tự động ký được ID token hợp lệ không?

**Trả lời:** Không chỉ vì biết decryption key. Có thể ảnh hưởng **confidentiality** của ciphertext; cần đánh giá nested JWT inner signature verification và mức độ lộ dữ liệu. Không đánh đồng decryption với signing.

### Tình huống M — DPoP token string bị lấy, holder key chưa lộ

Attacker có DPoP-bound access token nhưng không có DPoP private key D1.

**Câu hỏi:** Có thể dùng như bearer token thường không?

**Trả lời:** Nếu AS/RS kiểm sender constraint đúng, không. Attacker cần proof hợp lệ ràng buộc token/HTTP request. Điều này không thay chính sách revoke hoặc bảo đảm D1 không bao giờ bị đánh cắp.

### Tình huống N — DPoP holder key cũng bị lộ

Attacker có cả DPoP token và D1_private.

**Câu hỏi:** DPoP còn ngăn toàn bộ replay không?

**Trả lời:** Không. Attacker có thể tạo proof hợp lệ trừ khi có các kiểm soát khác. Cần revoke/rebind tokens và thay D1, đồng thời đánh giá device compromise. Issuer signing key K1 không mặc nhiên bị lộ.

### Tình huống O — `private_key_jwt` client key bị đánh cắp

Client `expense-sync` có C1_private để ký assertions; attacker lấy được C1.

**Câu hỏi:** Có thể mint JWT access token trực tiếp cho mọi API không?

**Trả lời:** Không tự động. C1 dùng **client authentication**, không phải issuer signing key. Nhưng attacker có thể giả client tại AS trong limits của registration/grants và lấy token hợp lệ. Cần rotate client key, chặn assertions cũ và điều tra token issuance.

### Tình huống P — mTLS certificate bị revoke nhưng RS cache trạng thái cũ

Client mTLS private key C1 bị lộ, CA thu hồi certificate. Một verifier không kiểm revocation hoặc cache stale.

**Câu hỏi:** Có thể coi certificate đã hết tin trên mọi endpoint không?

**Trả lời:** Không. Certificate revocation và trust propagation phụ thuộc PKI/verifier implementation. Cần kiểm enforcement trên các AS/RS endpoints liên quan và xử lý token binding.

### Tình huống Q — Một region không nhận emergency event

Region A đã `K1=BLOCKED`, region B còn snapshot `K1=TRUSTED` do mất mạng.

**Câu hỏi:** Có thể báo incident contained không?

**Trả lời:** Không nếu region B vẫn có thể chấp nhận token K1. Cần freshness deadline/fail closed hoặc cô lập traffic và xác minh hội tụ theo SLO.

### Tình huống R — Event cũ hồi sinh K1

Security event v18 chặn K1, nhưng một snapshot v17 `ACTIVE` đến trễ và ghi đè.

**Câu hỏi:** Sửa thế nào?

**Trả lời:** Dùng monotonic security versions, tombstones, idempotent handlers và không cho stale trust state overwrite emergency block. Nếu cần phát hành lại, dùng key mới chứ không tái tin K1.

### Tình huống S — Token có chữ ký hợp lệ, owner sai

Một JWT K2 có `orders:read` và chưa revoke, nhưng user thử xem đơn hàng của tenant khác.

**Câu hỏi:** Key security có tự bảo đảm quyền này không?

**Trả lời:** Không. RS phải kiểm owner/tenant/action/resource state. Signature hợp lệ chỉ là một lớp của quyết định; không có nghĩa được quyền mọi tài nguyên.

### Tình huống T — Signing key lộ ở môi trường staging

Security phát hiện private key staging lộ, và cả staging/production cùng dùng fingerprint F1.

**Câu hỏi:** Có thể chỉ rotate staging?

**Trả lời:** Không nếu production cũng tin cùng key material F1. Phải đánh giá và xử lý production trust domain. Đây là lý do phải tách khóa theo environment ngay từ đầu.

### Tình huống U — OP key compromise và OIDC login

OP signing K1 bị lộ, một RP dùng ID token cùng K1 để nhận diện `sub`.

**Câu hỏi:** Có phải mọi callback đều bị chiếm tài khoản ngay?

**Trả lời:** Không khẳng định như vậy; RP có thêm state/nonce/code/PKCE/issuer binding. Tuy nhiên forged ID token có thể làm authentication nguy hiểm nếu RP vẫn tin K1 ở một đường xử lý. Cần ngừng trust K1 và kiểm flow/issuance/login logs.

### Tình huống V — JWT K1 đã exp nhưng cache vẫn tin K1

Một token cũ đã hết `exp`; RS cache vẫn giữ K1 public.

**Câu hỏi:** Token cũ có thể được dùng lại không?

**Trả lời:** Nếu RS kiểm `exp` đúng thì token cũ bị từ chối. Nhưng attacker có K1_private có thể tạo **token mới** với `exp` tương lai (trong giới hạn validators). Đó là lý do phải distrust K1, không chỉ đợi tokens cũ hết hạn.

### Tình huống W — TLS private key bị lộ

Một TLS 1.3 endpoint lộ server private key, đội vận hành nói “mọi HTTPS traffic đã ghi từ trước đều bị giải mã”.

**Câu hỏi:** Kết luận có chính xác không?

**Trả lời:** Không mặc nhiên. TLS 1.3 dùng forward secrecy cho các phiên được thiết lập đúng, nên lộ long-term cert key không tự giải mã toàn bộ phiên lịch sử. Vẫn cần rotate/revoke certificate và đánh giá khả năng impersonation/cấu hình thực tế.

### Tình huống X — Restore key registry cũ

Sau emergency block K1, đội vận hành restore snapshot trong đó K1 còn ACTIVE.

**Câu hỏi:** Hệ thống nên làm gì?

**Trả lời:** Reconcile với authoritative security high-watermark, replay BLOCKED event, không cho trạng thái cũ hồi sinh key. Verifiers chưa đạt freshness phải fail closed theo policy.

## 23. Playbook ứng cứu một JWT issuer signing key bị compromise

Khi private signing key của AS/OP có khả năng bị lộ, incident cần được xử lý như **mất một trust anchor**, không chỉ như một token bị đánh cắp.

### 23.1. Giai đoạn 1 — Xác minh và giới hạn việc lộ thêm

1. Xác nhận **đúng key material/capability** nào bị ảnh hưởng bằng fingerprint, KMS reference, issuer và key usage registry.
2. Hạn chế người truy cập evidence; không chuyển raw private key qua chat/ticket.
3. Xác định các đường lộ: repo, artifact, host memory, VM snapshot, CI, KMS IAM, JWKS publisher, developer device.
4. Giữ audit/forensics từ KMS, AS, RS, CI/CD, registry và access logs theo quy định.
5. Kiểm tra môi trường đang bị chiếm **đã được cô lập** trước khi tạo/phân phối khóa mới; nếu không, K2 có thể bị lộ ngay.

### 23.2. Giai đoạn 2 — Containment khả năng ký

~~~text
Compromised K1_private exported?
    -> Không thể "lấy lại" mọi bản sao bằng cách xóa máy gốc.
    -> Phải ngừng tin public K1 tại verifiers.

Compromised KMS Sign role?
    -> Disable/revoke IAM capability, kiểm access policies.
    -> Đánh giá rotation và các chữ ký đã được tạo.

Compromised JWKS publisher?
    -> Khôi phục metadata/key trust từ nguồn đã xác minh.
    -> Tìm key substitution, kiểm issuer discovery.
~~~

Nếu key material từng được export, chỉ **disable KMS key** không đủ chặn những bản sao private bytes đã ra ngoài. Phải distrust public key ở RS/RP.

### 23.3. Giai đoạn 3 — Tạo K2, chuyển issuance, chặn K1

- Sinh K2 mới từ KMS/HSM/CSPRNG đã xác minh an toàn, với key purpose/algorithm đúng.
- Tách quyền issuer signing với key publication và resource-server trust.
- Publish K2 public qua trusted JWKS/configuration path.
- Chuyển AS issuance sang K2; ngừng K1 signing.
- **Block fingerprint K1** ở mọi verifiers liên quan. Không đợi K1 tokens hết hạn nếu không phù hợp emergency objective.
- Invalidate JWKS/CDN/local key caches; xử lý rollout/regions chưa cập nhật.
- Áp readiness/fail-closed khi một verifier chưa biết security policy hiện hành.

Nếu phải hy sinh availability để ngăn token giả ở API nhạy cảm, có quy trình phê duyệt và thông báo rõ; không bí mật fail-open.

### 23.4. Giai đoạn 4 — Vòng đời grants, sessions và credentials

Key trust compromise và token revocation là hai công việc **bổ sung**, không thay thế nhau.

1. Đánh giá những access/ID tokens đã phát hành khi K1 có thể bị chiếm; token K1 có thể không đáng tin nữa.
2. Buộc đăng nhập lại ở RPs khi OIDC authentication assurance bị ảnh hưởng.
3. Revoke refresh grants/session security epochs nếu có nguy cơ credential theft hoặc attacker đã dùng token giả để có quyền mới.
4. Kiểm tra `client_id`, `sub`, `aud`, `scope`, token exchange và delegated tokens liên quan.
5. Đánh giá client credentials/DPoP/mTLS keys khác có bị ảnh hưởng bởi cùng host/secret manager không.
6. Theo dõi resource-level authorizations và bảo vệ API trước token replay/forgery.

**Không tự hứa** “rotate signing key = mọi refresh token tự bị revoke” hoặc “revoke refresh token = không ai giả được JWT bằng K1”. Chúng thuộc các trust boundaries khác nhau.

### 23.5. Giai đoạn 5 — Kiểm chứng hội tụ, không chỉ thay metadata

Một bộ tiêu chí incident containment có thể gồm:

~~~text
[ ] K1 Sign/IAM usage đã bị chặn hoặc cô lập.
[ ] Không còn AS node phát K1.
[ ] K2 public được phân phối tới các verifiers liên quan.
[ ] Mọi RS/RP trong inventory từ chối JWT K1 hợp lệ về claims.
[ ] Có test token K1 với iat backdated và exp chưa hết hạn.
[ ] JWKS/CDN/sidecar caches đã phản ánh security policy.
[ ] Region bị partition có fail mode đáp ứng freshness budget.
[ ] Không có replay/event stale nào hồi sinh trust K1.
[ ] K2 tokens hợp lệ đi qua signature/issuer/audience checks.
[ ] Business authorization theo action/resource/tenant vẫn hoạt động.
[ ] Có giám sát API suspicious accesses và incident audit.
~~~

Không có cách kiểm tuyệt đối **mọi** hệ thống nếu inventory thiếu. Cần cập nhật coverage, phát hiện unknown consumers và ghi rõ những vùng chưa kiểm chứng thay vì báo “100% done”.

### 23.6. Giai đoạn 6 — Điều tra dữ liệu và trách nhiệm

Thời điểm khóa lộ có thể trước ngày phát hiện; xem:

- API requests dùng token K1 đáng ngờ, đặc biệt scopes/audiences/sub lạ.
- Các account links, permissions, transfers, approvals đã thực hiện.
- Session/token issuances không có record đáng tin.
- Dữ liệu được export/đọc (không thể “revoke” dữ liệu đã lộ).
- Nguồn key compromise: IAM, repo, build artifacts, backups, host, secret manager.
- Những người/đơn vị có thể cần thông báo theo policy và pháp luật liên quan.

Một token được RS từ chối sau incident không hoàn tác hành động trước đó. Security response phải đánh giá **impact đến dữ liệu và người dùng**, không dừng ở sự kiện JWKS đã cập nhật.

### 23.7. Giai đoạn 7 — Hậu kiểm và phòng ngừa tái diễn

- Tách keys theo purpose/issuer/environment.
- Chuyển signing sang KMS/HSM với least privilege.
- Bảo vệ CI/CD, JWKS publisher và developer access.
- Cải thiện key registry, audit và secret scanning.
- Đặt emergency trust-propagation SLO.
- Tạo test suite cho K1 reject/K2 accept và stale cache.
- Tập diễn tập incident key compromise nhiều region.
- Giảm TTL tokens nơi hợp lý, kết hợp stateful revocation và resource authorization.
- Bổ sung cơ chế phát hiện issuer signing abuse qua issuance record/logs độc lập.

Không coi việc “tăng lịch rotate từ 90 ngày lên 30 ngày” là giải pháp toàn bộ; nếu secret vẫn bị publish trong build artifact, khóa mới cũng có thể lộ.

## 24. Checklist thiết kế chống key compromise

1. **Xác định loại khóa:** JWT signing, JWE encryption, HS256, DPoP, mTLS, `private_key_jwt`, TLS server, cookie/session hay opaque-token secret.
2. **Phạm vi:** key được tin bởi issuer/client/resource servers/regions nào, có reused across env/purpose không?
3. **Trust:** public verification keys được lấy từ trusted metadata/JWKS; không theo `jku`/`x5u` trong JWT tự khai.
4. **Algorithms:** pin allowlist đúng key type, không `alg=none` hoặc HS/RS confusion; kiểm JOSE/JWT profiles.
5. **Key separation:** private signing keys không được cấp cho RS, không dùng HMAC secret chung không có căn cứ.
6. **Generation:** KMS/HSM/CSPRNG, key material K2 hoàn toàn mới, public key fingerprint được kiểm.
7. **Permissions:** IAM least privilege, tách quyền Sign/Decrypt/Rotate/Publish, service principal isolation.
8. **Storage:** không commit key vào repo, image, mobile app, client bundle, log, crash dump hoặc support ticket.
9. **Public JWKS:** không xuất private JWK fields, issuer/JWKS URI qua TLS và pipeline đáng tin.
10. **Inventory:** key ID/fingerprint, issuer/purpose, owner, verifiers, activation/retirement và history.
11. **Planned rotation:** publish K2 trước chuyển issuance, retire K1 sau khoảng hợp lệ, kiểm TTL/cache.
12. **Emergency rotation:** disable K1 signer, distrust K1 tại mọi RS/RP, không chờ tokens tự hết hạn nếu vượt SLO.
13. **JWKS cache:** purge/invalidate CDN, proxies, sidecars, verifiers; tránh cache fill race và stale JWKS.
14. **Policy version:** dùng monotonic trust state/tombstone, event authenticity, outbox, replay và snapshot.
15. **Network partitions:** freshness deadline/fail-closed phù hợp API; không silently accept K1 vô hạn.
16. **JWT validation:** issuer, expected audience, exp/nbf, token type, signature, alg, key trust và scope.
17. **No backdating exception:** không dùng `iat` trong JWT K1 làm bằng chứng AS phát hành trước compromise.
18. **Revocation:** signing-key trust khác refresh-token/grant revocation; cần cả hai khi incident scope đòi hỏi.
19. **Sender constraints:** DPoP/mTLS key compromise cần rotate holder keys, revoke/rebind bound tokens.
20. **Encryption:** JWE decryption key compromise cần đánh giá confidentiality/ciphertext cũ, không chỉ access expiry.
21. **Business checks:** token hợp lệ không thay owner/tenant/action policy.
22. **Evidence:** giữ KMS/JWKS/AS/RS audit bảo vệ, không lưu raw secrets; phân biệt detected và actual compromise time.
23. **Testing:** verifier phải REJECT K1 sau emergency và ACCEPT K2 đúng claims trên mọi node/region.
24. **Recovery:** restore/backup không hồi sinh K1; risk analysis phải bao gồm data access đã xảy ra.

### 24.1. Quyết định nhanh theo loại khóa

~~~mermaid
flowchart TD
    A[Phát hiện nghi lộ khóa] --> B{Khóa thuộc loại nào?}
    B --> C[AS JWT signing / HMAC]
    B --> D[Client DPoP / mTLS / private_key_jwt]
    B --> E[JWE decryption]
    B --> F[TLS / session secret]
    C --> G[Chặn ký + sinh K2 + distrust K1 tại RS/RP]
    D --> H[Chặn client/holder key + rebind và revoke tokens]
    E --> I[Đánh giá dữ liệu ciphertext có thể bị lộ + rotate key]
    F --> J[Rotate key/cert + invalidate affected sessions]
    G --> K[Kiểm hiệu lực ở mọi trust boundary]
    H --> K
    I --> K
    J --> K
    K --> L[Điều tra tác động và hậu kiểm]
~~~

### 24.2. Ghi nhớ trong một phút

~~~text
Public verification key:
    Có thể công khai qua JWKS.

Private signing key / HMAC secret:
    Nếu bị chiếm, có thể tạo chữ ký/MAC hợp lệ.

JWKS rotation:
    Không tự bảo đảm RS đã loại K1 khỏi cache.

kid / alg / iat / jti trong JWT:
    Không tự trở thành bằng chứng issuance khi signer bị chiếm.

Emergency trust removal:
    Chặn K1 theo key material/trust policy tại mọi RS/RP.

DPoP / mTLS client key:
    Chứng minh sender, không phải AS signing key.

JWE decryption key:
    Rủi ro confidentiality; tách khỏi JWS signature trust.

JWT signature valid:
    Chưa đủ nếu signing key đã compromise.

Token trusted + policy:
    Vẫn phải kiểm principal/action/resource/tenant.
~~~

**Kết luận:** **Key compromise là sự cố của mô hình tin cậy**, không chỉ là một lỗi cấu hình hoặc một token cần revoke. Khi **issuer signing private key hoặc khả năng ký** bị chiếm, attacker có thể tạo JWT có chữ ký hợp lệ, kể cả những JWT **chưa từng được AS phát hành**. Vì vậy, sửa ở AS và đổi `kid` chưa đủ: hệ thống phải **ngừng tin key material bị compromise tại mọi verifier**, xử lý JWKS/cache/multi-region propagation, đồng thời đánh giá grants, sessions, dữ liệu đã truy cập và các keys khác trong cùng trust boundary. Với JWE, DPoP, mTLS hay client authentication, cần ứng cứu theo **mục đích khóa cụ thể**. Phòng ngừa bằng KMS/HSM, key separation, least privilege, trusted distribution, audit, kiểm thử phân tán và authorization theo resource.

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS protected header, chữ ký, `alg`, `kid` và cách xác minh.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): encryption, key management và confidentiality của JOSE.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): public/private JWK, JWK Set, `kty`, `use`, `kid`.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán HMAC, RSA, ECDSA và JOSE key management.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims như `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): phương pháp tính thumbprint của JWK public material.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, cross-JWT confusion, key/issuer binding và JWT security.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token JWT, issuer/audience, claim và token type validation.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): AS, RS, grant, refresh/access tokens, client authentication.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ token, refresh rotation và trust boundaries.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint và giới hạn hiệu lực phân tán.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque token `active` và cache/introspection security.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): holder key, DPoP proof, replay và sender-constrained tokens.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS client key và token binding.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token validation, issuer, subject và OIDC client authentication.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): trusted issuer metadata, `jwks_uri` và OP discovery.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): NimbusJwtDecoder, issuer validation và custom token validators.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): bảo vệ API bằng JWT/opaque tokens.
- [OWASP JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): lưu trữ JWT, key management và token revocation.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lưu trữ và quản lý secrets, rotation, audits.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): quản lý khóa, key lifetime, thuật toán và secret storage.
- [NIST SP 800-57 Part 1 Revision 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): key lifecycle, protection, compromise và key management policy.
