# Key confusion

## 1. Key confusion là gì và vì sao nguy hiểm trong bảo mật token?

Trong chương **Threats** thuộc module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài này nghiên cứu **key confusion**: lỗi xảy ra khi bên xác minh token nhầm **khóa, thuật toán, nguồn khóa, mục đích khóa hoặc miền tin cậy**. Hệ quả là một token không được ký bởi chủ thể có thẩm quyền vẫn có thể được xem là đáng tin, hoặc token dành cho một giao thức/đối tượng khác bị chấp nhận sai.

Trong OAuth 2.0/OpenID Connect (OIDC), Authorization Server (AS)/OpenID Provider (OP) có thể ký JWT access token hoặc ID token. Resource Server (RS) và Relying Party (RP) phải xác minh bằng **đúng khóa đáng tin trong đúng ngữ cảnh**. Nếu verifier để JWT tự quyết định dùng khóa gì, trust boundary bị đảo ngược.

Ví dụ hệ thống:

~~~text
Authorization Server (AS)
    Private signing key K_AS
        |
        +--> ký JWT access token
                     |
                     v
                 Orders API
        trusted issuer + trusted public JWKS
                     |
                     v
           signature + claims + action/resource policy
~~~

Một thiết kế sai có thể làm:

~~~text
JWT attacker gửi
    |
    +--> header alg tự chọn thuật toán
    +--> header kid tự chọn khóa
    +--> header jku tự chọn nơi tải khóa
    |
    v
Verifier tin các thông tin này như chính sách
    |
    v
Token giả được ALLOW
~~~

**Nguyên tắc quan trọng:** *JWT header là dữ liệu chưa đáng tin cho đến khi toàn bộ JWT được xác minh. Nó có thể hỗ trợ tìm khóa **trong tập khóa đã được ứng dụng tin trước**, nhưng không được tự tạo nguồn tin cậy, thuật toán chấp nhận hay quyền truy cập.*

### 1.1. Hậu quả điển hình

- **Giả mạo token:** attacker tạo chữ ký/MAC được verifier chấp nhận nhờ nhầm loại khóa hoặc thuật toán.
- **Nhầm issuer/tenant:** key của issuer A được sử dụng để chấp nhận JWT tự khai từ issuer B.
- **Nhầm token type:** ID token, DPoP proof hoặc client assertion được chấp nhận như OAuth access token.
- **Nhầm key purpose:** public key của một client dùng xác minh client assertion lại trở thành key tin cậy cho AS access tokens.
- **Lấy khóa từ nguồn không tin cậy:** `jku`, `x5u` hay `jwk` trong header khiến verifier tin key của attacker.
- **SSRF/điều hướng tùy ý:** verifier tự tải key từ URI do token chưa được xác minh khai báo.
- **Fail-open khi không tìm được khóa:** hệ thống bỏ qua bước xác minh hoặc thử một khóa mặc định không đúng trust policy.

Không phải mọi trường hợp đều cho phép attacker vượt qua hệ thống đã cấu hình tốt. **Khả năng khai thác phụ thuộc verifier và các kiểm soát độc lập.**

### 1.2. Bạn sẽ học được gì?

Sau bài này, bạn có thể:

1. Phân biệt **key confusion**, **algorithm confusion**, **key substitution**, **key compromise** và **cross-JWT confusion**.
2. Giải thích cách `alg`, `kid`, `jwk`, `jku`, `x5u`, `x5c`, `crit`, `typ` và `cty` tác động đến xác minh JOSE.
3. Hiểu rủi ro nhầm giữa RSA/EC/OKP public keys và HMAC secret; đặc biệt trường hợp `RS256` bị xử lý thành `HS256`.
4. Thiết kế **trusted issuer → trusted key set → allowed algorithm → expected token type/audience**.
5. Cách ly key set giữa issuers, tenants, OAuth clients, DPoP holders, AS/RP/RS và các môi trường.
6. Áp dụng Spring Security/Nimbus JWT decoder theo hướng **chốt chính sách ở server**, không theo header do caller chọn.
7. Xây dựng test matrix cho key confusion, key rotation, JWKS cache và các đường fallback.
8. Ứng cứu khi phát hiện hệ thống từng chấp nhận JWT bằng khóa sai.

## 2. Phân biệt các khái niệm dễ bị trộn lẫn

| Khái niệm | Sai lệch chính | Ví dụ |
|---|---|---|
| **Key confusion** | Verifier chọn hoặc sử dụng **nhầm khóa** | Key OAuth client được dùng để verify issuer access token |
| **Algorithm confusion** | Verifier cho token tự đổi thuật toán/cách dùng key | Chuyển từ asymmetric signature sang symmetric MAC trái policy |
| **Key substitution** | Nguồn khóa tin cậy bị thay bằng khóa khác | `jku` trỏ JWKS của attacker, verifier tin key ở đó |
| **Key compromise** | Attacker có private key, HMAC secret hoặc khả năng dùng signer | Private AS signing key bị copy từ backup |
| **Cross-issuer confusion** | Key/token của issuer khác được chấp nhận | Cùng `kid` giữa hai issuer dẫn tới lookup sai |
| **Cross-JWT confusion** | Token dành cho **một mục đích** được dùng ở mục đích khác | ID token bị API chấp nhận như access token |
| **Audience confusion** | Token dành cho resource/client khác được nhận | `aud=payments` nhưng Orders API vẫn ALLOW |
| **Key rotation error** | Key cũ/mới/cache bị quản lý sai | Verifier tiếp tục tin key bị emergency-block |

Những lỗi này **có thể liên kết** nhưng không đồng nghĩa.

Ví dụ: nếu attacker thật sự đánh cắp **AS private signing key**, dù verifier chọn đúng khóa vẫn có thể bị token giả. Đó là **key compromise**. Còn nếu attacker chỉ giữ **private key của chính họ**, nhưng verifier cho phép token khai báo dùng public key của attacker làm trust anchor, đó là **key substitution/key confusion**.

### 2.1. Các vai trò trong OAuth 2.0/OIDC

~~~text
AS / OP:
    Phát và có thể ký access token, ID token.
    Giữ private signing key an toàn.

RS:
    Nhận access token để bảo vệ API.
    Tin đúng public verification key hoặc introspection service.

OAuth Client / RP:
    Khởi tạo flow; có thể giữ client authentication key.
    RP xác minh ID token theo OP và client registration.

DPoP holder:
    Giữ private key để chứng minh sender.
    Đây KHÔNG phải OP signing key.
~~~

Một cặp khóa có chữ “RSA” ở cả hai phía **không có nghĩa có thể thay thế nhau**. Vai trò, issuer, audience, algorithm, key purpose và registration phải khớp.

### 2.2. JWS, JWE, JWT không phải một thuật toán

- **JWT** là định dạng tập claims; có thể được bảo vệ bằng JWS/JWE hoặc theo profile cụ thể.
- **JWS** dùng chữ ký số hoặc MAC để bảo vệ tính toàn vẹn/nguồn gốc của dữ liệu.
- **JWE** dùng mã hóa và xác thực thông điệp theo cơ chế JOSE.
- **JWKS** là tập JSON Web Keys, thường gồm **public verification keys** cho AS/OP.

**Ký không đồng nghĩa mã hóa.** Một JWS JWT thường có payload đọc được sau Base64url decode; `alg` của JWS và `alg`/`enc` của JWE có ngữ nghĩa khác nhau. Không tự dùng JWE decryption key làm JWS verification secret.

## 3. Trust chain đúng: không để JWT tự chọn người xác minh

Một Resource Server an toàn nên bắt đầu từ **cấu hình đã được tin trước**:

~~~mermaid
flowchart TD
    A[Incoming OAuth access token] --> B[Trusted API resource configuration]
    B --> C[Expected issuer and trusted metadata/JWKS]
    C --> D[Allowed algorithms and appropriate key types]
    D --> E[Select matching key from this trusted set]
    E --> F{Signature or MAC valid?}
    F -- No --> X[Reject]
    F -- Yes --> G[Validate iss, aud, typ/profile, exp/nbf, scope]
    G --> H{Token is suitable for this API?}
    H -- No --> X
    H -- Yes --> I[Authorization: subject/action/resource/tenant]
    I --> J{Permission granted?}
    J -- No --> X
    J -- Yes --> K[Allow]
~~~

Sơ đồ là **mô hình quyết định**. Một thư viện có thể parse header để lựa key trước khi kiểm chữ ký; đó là việc cần thiết về mặt kỹ thuật, nhưng **không có nghĩa header được quyền thay đổi issuer/JWKS URL/algorithm policy**.

### 3.1. Đầu vào đáng tin và chưa đáng tin

| Dữ liệu | Trạng thái trước verify | Cách dùng đúng |
|---|---|---|
| Route/resource server config | Đáng tin nếu được quản lý đúng | Xác định issuer, expected audience, allowed alg |
| OAuth/OIDC issuer metadata | Tin sau discovery/issuer/TLS/source validation đúng | Lấy `jwks_uri` được phép |
| Client registration | Đáng tin nếu được cập nhật theo quy trình đã xác thực | Xác định client JWKS/auth method |
| JWT protected header `kid`, `alg` | **Chưa tin** | Chỉ lựa key/alg trong chính sách đã chốt |
| JWT header `jku`, `x5u`, `jwk` | **Chưa tin** | Không tự cấp authority cho nguồn/key này |
| JWT claims `iss`, `aud`, `sub`, `scope` | **Chưa tin** | Sau crypto verification mới dùng cho quyết định |
| Public JWKS từ attacker URL | Không đáng tin | Không thêm vào key set chỉ vì JWT yêu cầu |
| Security key blocklist/epoch | Đáng tin khi có nguồn, phiên bản và freshness phù hợp | Loại bỏ key đã bị revoke/compromise |

### 3.2. Quy tắc quan trọng cho nhiều issuer

Một API có thể chấp nhận **nhiều issuer**, nhưng phải có **allowlist** và binding:

~~~text
Issuer A:
    iss = https://idp-a.example.com
    trust set = JWKS_A
    allowed alg = RS256
    audiences = orders-api

Issuer B:
    iss = https://idp-b.example.com
    trust set = JWKS_B
    allowed alg = ES256
    audiences = orders-api
~~~

Không gộp `JWKS_A + JWKS_B` thành một tập khóa không namespace rồi tin claim `iss` bất kỳ. Một chữ ký hợp lệ bằng key A **không chứng minh** token thuộc issuer B. Khi hỗ trợ multi-issuer, phải liên kết khóa đã dùng với **issuer đúng** và cấu hình issuer được phép.

### 3.3. Trust boundary và thứ tự quyết định

Một thiết kế phòng thủ ở mức logic:

~~~text
1. API xác định accepted token profile, audience, issuer allowlist.
2. Lấy trusted issuer/key config từ nguồn server-side.
3. Parse JOSE header trong phạm vi giới hạn (size, depth, alg, kid).
4. Chọn ứng viên từ trusted key set và loại key đã block.
5. Cryptographically verify bằng algorithm/key type được phép.
6. Kiểm claims và token purpose/profile.
7. Kiểm authorization trên action/resource/tenant.
8. ALLOW chỉ nếu mọi cổng đều PASS.
~~~

Nếu không thể có trusted key phù hợp, **REJECT**. Không fallback sang “JWT decode được, tạm tin claims” hay “thử HMAC cho tiện”.

## 4. `alg` confusion: nhầm chữ ký bất đối xứng với HMAC

### 4.1. RSA signing và HMAC khác nhau về quyền giữ khóa

**RS256** dùng chữ ký RSA với SHA-256:

~~~text
AS:
    RS256 signing private key K1_private

RS:
    RS256 verification public key K1_public
~~~

**HS256** dùng HMAC-SHA-256:

~~~text
Issuer / Verifier:
    cùng biết một secret K_HS

Bất kỳ bên giữ K_HS đều có thể tạo MAC hợp lệ.
~~~

Nếu RS được cấp public key của AS để verify RS256, **nó không có quyền tạo chữ ký RS256**. Đây là lợi ích tách quyền ký và xác minh của crypto bất đối xứng.

### 4.2. Trường hợp nhầm RS256 với HS256

Lớp lỗi từng xuất hiện trong các JWT verifier cũ/tự viết:

~~~text
Server policy thực:
    JWT phải ký RS256 với AS private key.
    RS chỉ có public key PEM.

Verifier sai:
    Tin alg do JWT header yêu cầu.
    Khi header nêu HS256, dùng public PEM bytes như HMAC secret.
    Coi MAC hợp lệ là issuer signature.
~~~

Vì public key vốn được công bố, nếu verifier nhầm nó thành HMAC secret, attacker có thể tính cùng MAC cho payload tùy chọn. Đây là **algorithm/key-type confusion**; không cần đánh cắp private RSA key.

**Điều kiện khai thác là verifier có lỗi thật.** Thư viện JOSE hiện đại thường yêu cầu key type tương thích và có cơ chế chốt thuật toán. Không nên suy mọi server chấp nhận RS256 đều mắc lỗi này.

### 4.3. Phòng thủ chính xác

- Pin **allowed signing algorithms** trong server config theo issuer/token profile.
- Không chọn verifier algorithm chỉ theo `alg` trong JWT header.
- Không cho public RSA/EC/OKP material được sử dụng như HMAC secret.
- Kiểm JWK `kty`, key material, `use`, `key_ops`, `alg` theo chính sách, không xem trường nào trong JWT là nguồn authority.
- Nếu profile dùng HS256, secret phải là **secret chuyên dụng đủ entropy**, không phải public key PEM.
- Không cho `alg=none` đối với OAuth access token/ID token cần chữ ký, trừ một **profile được thiết kế rõ cho unsecured token** ngoài ngữ cảnh này.
- Test negative với algorithm mismatch và key-type mismatch.

### 4.4. Vì sao “chữ ký hợp lệ” vẫn có thể là kết luận sai?

Chữ ký/MAC chỉ có ý nghĩa khi **đúng thuật toán, đúng key purpose và đúng nguồn tin cậy**. Nếu server xác minh HMAC bằng key public không bí mật, kết quả “MAC valid” không chứng minh token do AS phát hành.

Không tự viết thư viện xác minh JWS bằng việc base64-decode rồi so chuỗi hoặc tự chọn crypto provider. Dùng thư viện đã được kiểm thử, cấu hình algorithm constraints rõ ràng và kiểm token profile đầy đủ.

## 5. `kid` confusion: tên khóa không phải bằng chứng nguồn gốc

`kid` (Key ID) là một trường JOSE header thường dùng để **tìm một khóa ứng viên** trong tập khóa. Nó không phải chữ ký, không phải certificate và không phải định danh có tính toàn cục.

Ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "2026-prod-01",
  "typ": "at+jwt"
}
~~~

Với JWT này, verifier có thể tìm `kid=2026-prod-01` trong **JWKS đã được tin của issuer được phép**. Nhưng attacker có thể tự viết bất kỳ `kid` nào vào một JWT chưa xác minh; key lookup phải giới hạn bởi server configuration.

### 5.1. Hai issuer có thể cùng dùng `kid`

~~~text
Issuer A / JWKS_A:
    kid = current
    public key = KA

Issuer B / JWKS_B:
    kid = current
    public key = KB
~~~

Nếu API cache JWKS theo `kid` đơn thuần:

~~~text
publicKeyCache["current"] = KA
~~~

thì request của issuer B có thể bị xác minh nhầm bằng KA, hoặc attacker lợi dụng logic fallback để vượt ranh giới issuer. Cách đúng là **issuer-scoped key registry**, thường cần key-set identity và key fingerprint, không dùng một `kid` toàn cục.

### 5.2. Cùng `kid` nhưng khác key material

Key rotation không được chỉ thay public key gắn với `kid=current` mà không có quy tắc cache/version hợp lệ. Một RS có thể:

- Còn giữ `kid=current → K_old` trong cache.
- Một node khác đã nhận `kid=current → K_new`.
- Hai region xác minh cùng JWT ra kết quả khác nhau.

Trong planned rotation, nên dùng `kid` phân biệt key versions theo profile và giữ overlap cần thiết. Trong emergency, cần quản lý trust/key fingerprint để chặn compromised material, không chỉ xóa một entry theo chuỗi.

### 5.3. `kid` injection vào filesystem hoặc database

Một lỗi khác xảy ra khi custom verifier sử dụng `kid` trực tiếp:

~~~text
Untrusted JWT header kid
    -> dựng tên đường dẫn trong key directory
    -> đọc file theo path từ input

hoặc

Untrusted JWT header kid
    -> nối chuỗi SQL query
    -> chọn khóa ngoài phạm vi được phép
~~~

Đây là **input-validation/injection risk** trên đường key resolution. Một `kid` được phép tìm key theo **map đã đăng ký** hoặc query được parameterize, không phải raw filename/SQL fragment/command.

Ví dụ cách tiếp cận tốt:

~~~java
// Pseudocode: registry chỉ chứa các keys đã được phê duyệt cho issuer.
TrustedKeyRef key = registry.findByIssuerAndKid(
    expectedIssuer,
    parsedKid);

if (key == null || key.isBlocked()) {
    throw new InvalidTokenException("Unknown or blocked signing key");
}
~~~

**Không được** để `expectedIssuer` lấy từ query user tự chọn rồi coi nó là issuer tin cậy; nó phải nằm trong allowlist/route-specific trust policy.

### 5.4. Không fallback “thử mọi khóa” vô kiểm soát

Một số JWT libraries có thể thử một tập khóa phù hợp khi JWT không có `kid` hoặc khi `kid` không match. Việc này chỉ chấp nhận được nếu **tập khóa đã được giới hạn đúng issuer, algorithm, key use và profile**. Không thử mọi khóa của mọi issuer, mọi tenant và cả client registrations.

Nếu một token không cung cấp được bằng chứng cryptographic hợp lệ với key thuộc trust set yêu cầu, phải từ chối. Không lấy lý do “đang rotate key” để chấp nhận bất kỳ chữ ký nào.

### 5.5. `kid` và key compromise

Khi private K1 bị lộ, việc khóa chỉ `kid=old-1` có thể không đủ nếu **cùng K1 public** được công bố với `kid=legacy`, hoặc verifier bỏ qua `kid`. Emergency response nên chặn theo **trusted key material/fingerprint** và policy version, đồng thời purge JWKS caches.

## 6. `jku`, `x5u` và `jwk`: header không được chọn trust root

JOSE hỗ trợ nhiều trường liên quan đến tìm khóa hoặc certificate. Các trường này hữu ích trong những profile nhất định, nhưng **không phải chỉ dẫn được tin một cách mặc định** từ bất kỳ JWT caller gửi.

### 6.1. `jku`: URL dẫn tới JWK Set

Ví dụ header:

~~~json
{
  "alg": "RS256",
  "kid": "attacker-controlled-1",
  "jku": "https://keys.attacker.example/jwks.json"
}
~~~

Nếu verifier tải JWKS từ `jku` trên token và dùng ngay để verify **mà không có trust binding từ trước**, attacker có thể công bố public key của chính họ rồi ký JWT bằng private key tương ứng. Chữ ký khớp public key attacker **không chứng minh token do issuer được yêu cầu phát hành**.

Đây là ví dụ **key substitution**. Không có nghĩa mọi JWT mang `jku` đều độc hại; vấn đề là **ai quyết định URL đó có đáng tin hay không**.

### 6.2. SSRF từ dynamic key fetching

Nếu `jku`/`x5u` được dùng làm HTTP URL tùy ý:

~~~text
Untrusted JWT header
    -> HTTP client chạy trong backend
    -> gửi request tới địa chỉ do attacker chỉ định
~~~

Ngoài key substitution, verifier có thể trở thành **SSRF primitive** để truy cập dịch vụ nội bộ, metadata endpoints hoặc hosts không được phép.

Biện pháp:

- Dùng `jwks_uri` từ **trusted issuer metadata/configuration**, không theo URL trong token.
- Nếu profile đặc biệt đòi remote key reference, dùng **exact allowlist**, TLS, redirects/host validation, DNS/IP/network controls, content type và size/time limits.
- Chặn chuyển hướng sang host/IP/port ngoài policy; cân nhắc DNS rebinding và proxy behavior.
- Không trả key-fetch error/body nhạy cảm cho caller.
- Không cho token từ tenant A tự buộc backend tải JWKS của tenant B.

### 6.3. `x5u`: URL dẫn tới certificate hoặc chuỗi certificate

`x5u` có thể tham chiếu certificate chain; certificate xuất hiện ở URL do caller tự khai **không làm nó thành chứng chỉ được issuer tin cậy**. Nếu ứng dụng hỗ trợ, cần profile PKI, chain validation, key usage, hostname/trust policy khi áp dụng và **issuer-to-key binding**.

Không trộn logic “certificate hợp lệ theo một CA công cộng” với “certificate đó được phép ký access token của AS này”. PKI chain alone không chứng minh quyền đóng vai issuer OAuth.

### 6.4. `jwk`: JWK nhúng ngay trong header

Header có thể mang public JWK nhúng. Trong một số protocol như **DPoP**, public JWK trong proof **được kỳ vọng**. Nhưng:

~~~json
{
  "alg": "RS256",
  "jwk": {
    "kty": "RSA",
    "kid": "self-chosen-public-key",
    "n": "<ATTACKER_PUBLIC_MODULUS>",
    "e": "AQAB"
  }
}
~~~

Nếu API lấy key nhúng này để xác minh JWT access token như bằng chứng issuer signing, attacker tự quyết định khóa mà server sẽ tin. **Đây là key confusion.**

Trong DPoP, nhúng public JWK giúp kiểm **proof of possession của client**, nhưng proof còn phải được ràng buộc với token/HTTP request (`cnf.jkt`, `htm`, `htu`, `ath`, `iat`, `jti`, nonce khi dùng). **Không được nâng public DPoP JWK thành AS issuer signing key.**

### 6.5. `x5c`: certificate chain nhúng

`x5c` có thể chứa certificate chain trong header. Trường này tự thân không chứng minh certificate chain được phép ký JWT của AS. Nếu hỗ trợ:

1. Validate chain/path đúng trusted anchors theo profile.
2. Check key usage/purpose, thời gian/certificate policy khi áp dụng.
3. Liên kết leaf public key với **registered issuer/client key identity**.
4. Không coi một chain tự khai là trust anchor.
5. Kiểm JWT algorithm và claims như bình thường.

### 6.6. Header nào được phép?

Một API chỉ nhận JWT access token do AS ký bằng JWKS đã đăng ký **thường không cần** cho token chỉ định `jku`, `x5u` hoặc key `jwk` tự chọn. Có thể từ chối hoặc bỏ qua các trường ngoài profile theo library/policy, nhưng tuyệt đối **không dùng chúng để mở rộng trust set**.

## 7. `alg=none`, `crit`, `typ` và `cty`: nhầm profile cũng là rủi ro

### 7.1. `alg=none` không phù hợp JWT access token cần xác minh chữ ký

`none` là một JOSE algorithm identifier cho unsecured JWS trong các profile có cho phép. Một RS OAuth yêu cầu JWT access token ký bởi issuer **không được chấp nhận token trống chữ ký chỉ vì header nói `none`**.

Một số use case khác có thể sử dụng unsecured JWT theo hợp đồng riêng, nhưng điều đó không cho phép dùng unsecured token qua đường Bearer API yêu cầu signature.

### 7.2. `crit` và các header extension không được hiểu

JWS `crit` chỉ ra những header parameters mà verifier **phải hiểu và xử lý đúng** để xác minh. Nếu JWT yêu cầu một critical extension mà verifier không hỗ trợ, phải từ chối theo JOSE profile. Không bỏ qua extension ảnh hưởng tới signing input/canonicalization hoặc semantics.

Ví dụ khái niệm:

~~~json
{
  "alg": "RS256",
  "kid": "k1",
  "crit": ["custom-verified-header"]
}
~~~

Nếu implementation không biết `custom-verified-header` có nghĩa gì, không được âm thầm coi nó như metadata trang trí.

### 7.3. `typ` giúp chống cross-JWT confusion

`typ` mô tả loại đối tượng JOSE; các token profiles có thể yêu cầu các giá trị cụ thể.

Ví dụ profile JWT access token theo **RFC 9068** sử dụng `typ=at+jwt` (hoặc dạng tương đương theo quy định của profile). Một OIDC ID token có **mục đích và audience khác**.

Không phải mọi JWT trên đời đều bắt buộc có cùng `typ`, và không thể chỉ kiểm `typ` để bảo mật. Nhưng **type/profile binding** giúp ngăn token trong hệ thống này bị nhận bởi ngữ cảnh khác.

### 7.4. `cty` trong nested JWT/JWE

`cty` (content type) có thể giúp thể hiện payload là JWT lồng nhau theo profile. Ví dụ JWE bọc một JWS:

~~~text
Outer JWE:
    decrypt bằng decryption key đúng recipient.
        |
        v
Inner JWS:
    verify signing key đúng issuer.
        |
        v
Validate claims + audience + token type + scope.
~~~

**Giải mã thành công không có nghĩa inner JWT được ký đúng issuer.** Một sai lầm là server decrypt outer JWE rồi tin claims trong plaintext mà bỏ qua inner signature trong profile yêu cầu nested signed JWT.

Ngược lại, không dùng JWS verification key để giải mã JWE hoặc chấp nhận thuật toán `enc` như `alg` của JWS. Key purpose (`sig`/`enc`) phải được thực thi.

### 7.5. Header validity và payload validity là hai cổng khác nhau

Ngay cả khi:

~~~text
alg = RS256 thuộc allowlist
kid = key của issuer
signature = valid
~~~

token vẫn phải bị từ chối khi `iss`, `aud`, `exp`, `nbf`, `typ` hoặc scope/policy không phù hợp. **Key confusion fixes không thay token validation và business authorization.**

## 8. `use`, `key_ops`, `kty`, `alg` trong JWK: vai trò nào thuộc key?

Một JSON Web Key có thể nêu:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "key_ops": ["verify"],
  "alg": "RS256",
  "kid": "issuer-signing-01",
  "n": "<PUBLIC_MODULUS>",
  "e": "AQAB"
}
~~~

Các trường này hỗ trợ xác định mục đích và tương thích thuật toán, **nhưng phải nằm trong key set đã được tin**. Một attacker có thể công bố JWK của mình với `use=sig`, `alg=RS256`, `kid=issuer-signing-01`; điều đó không tạo quyền ký access token của AS.

### 8.1. `kty`: không ép sai key material

Các loại cơ bản:

| `kty` | Thuật toán điển hình | Điều cần chú ý |
|---|---|---|
| `RSA` | RS256, PS256 theo policy | Public RSA dùng verify; private RSA dùng sign |
| `EC` | ES256/ES384 theo curve/profile | Curve phải phù hợp algorithm và validation |
| `OKP` | EdDSA với Ed25519/Ed448 theo profile | Không dùng như RSA/HMAC secret |
| `oct` | HS256 và các secret-based algorithms | Đây là symmetric secret, không đưa lên public JWKS |

RSA/EC/OKP public keys **không thể biến thành HMAC secret hợp lệ theo security policy** chỉ vì thuật toán trong JWT header thay đổi.

### 8.2. `use` và `key_ops` không phải yếu tố xác thực một mình

Một JWK với `use=enc` không nên được dùng để verify chữ ký khi profile chỉ cho `sig`. Một JWK với `key_ops=["encrypt"]` không phù hợp thao tác `verify`. Nếu JWK metadata mâu thuẫn, key resolver nên từ chối theo policy/profile.

Tuy nhiên **không chỉ tin `use`/`key_ops` của một JWK bên ngoài** rồi cho nó thành trusted signer. Nguồn khóa, issuer binding và registration vẫn quyết định thẩm quyền.

### 8.3. Không chia sẻ HMAC secret trên public JWKS

Một symmetric JWK loại `oct` có thể mang secret key material. Đưa nó vào public `jwks_uri` sẽ tiết lộ khả năng tạo MAC, không phải chỉ công bố khóa xác minh.

**Public JWKS dùng cho RS256/ES256/EdDSA thường nên chứa public verification material**, không có private RSA fields như `d`, `p`, `q` và không có `oct` secret. Nếu phát hiện secret bị publish, đây là **key compromise** cần ứng cứu, không chỉ một lỗi naming.

### 8.4. Curve và key type đúng chưa đủ

ES256 không được dùng với bất kỳ EC public key tùy ý: phải ràng buộc curve/key/profile được phép. Signature decoding/JOSE format do thư viện chuẩn chịu trách nhiệm; đừng tự convert ECDSA signature hoặc chọn key bằng substring của `crv`.

### 8.5. Thư viện phải xác định thuật toán cùng key

Theo JWT Best Current Practices, verification logic nên bảo đảm **cùng một key được dùng với thuật toán thích hợp đã chỉ định** và kiểm key/algorithm consistency. Không nên để một key tùy chọn nhiều thuật toán trái profile hoặc chuyển đổi symmetric/asymmetric theo token.

## 9. Cross-issuer và multi-tenant key confusion

Với hệ thống SaaS nhiều tenant, API có thể tin nhiều OP hoặc nhiều OAuth issuers. Đây là nơi dễ mắc lỗi **một key hợp lệ nhưng dành sai issuer**.

### 9.1. Ví dụ nhầm trust domain

~~~text
Tenant A login:
    issuer = https://idp-a.example
    kid = key-1
    public key = KA

Tenant B login:
    issuer = https://idp-b.example
    kid = key-1
    public key = KB

Orders API sai:
    gộp KA, KB thành global key map
    xác minh chữ ký bằng key bất kỳ
    rồi tin claim tenant/issuer trong JWT
~~~

Nếu một tenant có khả năng cấu hình issuer riêng, **tenant A không được làm mình thành tenant B** chỉ nhờ dùng một key thuộc tenant A và claim `tenant=B` trong JWT.

### 9.2. Nguồn xác định issuer đáng tin

Có thể dùng:

- Một allowlist cố định của các issuers theo deployment/API.
- Trusted tenant configuration gắn với route, hostname đã xác thực hoặc tenant context đã có.
- Một authentication manager resolver có cấu hình trusted issuer mapping.
- Issuer metadata/discovery được validate theo URI kỳ vọng và TLS/profile.

Một số framework đọc `iss` chưa xác minh để **chọn ứng viên decoder** từ allowlist. Đây chỉ là **routing hint**, không phải quyết định cuối; sau verify phải đảm bảo issuer trong token khớp decoder đã dùng và issuer được phép cho ngữ cảnh.

### 9.3. `iss` trong JWT không đủ để cấp quyền tenant

Ngay cả khi issuer A ký JWT hợp lệ và API chấp nhận issuer A, một claim `tenant_id=T-B` cũng không tự có quyền đọc dữ liệu T-B. Phải có mapping đáng tin **issuer + subject/client → tenant membership** và authorization trên object/action.

### 9.4. Môi trường dev/staging/prod

Một lỗi cấu hình:

~~~text
Production RS trusted issuer:
    https://login.prod.example

But key resolver imports both:
    prod JWKS
    staging JWKS
~~~

Nếu staging signing key bị lộ hoặc staging issuer cho phép tạo tài khoản tùy ý, việc RS production tin keys đó có thể mở đường token giả. Key sets nên **tách môi trường và issuer**; đừng reuse HMAC signing secret cho dev/prod.

### 9.5. Issuer alias và federation

Một tổ chức có thể có URL aliases, custom domains và federation. Mỗi alias phải nằm trong **trust policy minh bạch**. Không tự coi hai issuer tương đương chỉ vì chúng chung DNS parent domain hoặc cùng dùng `kid`.

Nếu federation đòi tin key của đối tác, phải phân biệt **issuer trust for that token type** với **quyền được truy cập resource/tenant**. External valid signature không tự cấp internal admin authority.

## 10. Cross-JWT confusion: ID token, access token và client assertion dùng khóa nào?

Một hệ thống có nhiều loại JWT với claims nhìn rất giống nhau:

~~~text
ID token
    -> RP/OIDC client xác minh người dùng đã authentication tại OP.

OAuth access token (JWT profile)
    -> Resource Server chấp nhận để bảo vệ API theo audience/scope.

Client assertion (private_key_jwt)
    -> Authorization Server xác thực OAuth client.

DPoP proof JWT
    -> AS/RS xác minh client đang sở hữu một private key.

Logout token JWT
    -> RP nhận OIDC Back-Channel Logout từ OP.
~~~

**Chúng không thay thế được nhau**, dù đều có `iss`, `sub`, `aud`, `iat`, `exp`, `jti`, chữ ký và JWT format.

### 10.1. ID token bị API chấp nhận như access token

Ví dụ Alice đăng nhập Shop Web qua OIDC:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": "shop-web",
  "iat": 1893492000,
  "exp": 1893495600
}
~~~

ID token này nhằm cho **client `shop-web`**. Nếu Orders API chỉ kiểm chữ ký OP rồi lấy `sub=alice-123` để nhận request, nó đã bỏ qua **token purpose và audience**.

Orders API phải yêu cầu **access token** dành cho Orders API:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": "https://orders.example.com",
  "scope": "orders:read",
  "iat": 1893492000,
  "exp": 1893495600
}
~~~

Ngay cả khi cả hai token ký bằng cùng OP key, chúng có **đối tượng nhận và ngữ nghĩa khác**. Resource Server nên dùng JWT access token profile/`typ`, audience, scopes, client context và token-specific validation theo hợp đồng.

### 10.2. `private_key_jwt` client assertion bị coi là access token

Trong OAuth client authentication, một confidential client có thể ký JWT assertion bằng **private key của client**:

~~~text
Client expense-sync:
    own private key C1_private

AS token endpoint:
    trusts registered public C1 to verify client assertion
~~~

Đây là **client authentication key**, không phải AS signing key. Nếu Orders API lỡ đưa toàn bộ registered client JWKS vào issuer JWT verification set, một client có thể dùng key riêng để ký dữ liệu có hình dạng access token. Thiết kế đúng phải giữ:

~~~text
AS signing key K_AS:
    verify access tokens / ID tokens theo issuer và profile.

Client key C1:
    verify client assertions của client C1 tại AS token endpoint.
~~~

**Không gộp hai trust stores** chỉ vì chúng cùng có kiểu JWK RSA hoặc `kid`.

### 10.3. `iss` và `sub` trong client assertion

Đối với JWT client assertion, `iss`/`sub` thường liên kết với **client identifier**, và `aud` dành cho **authorization server/token endpoint** theo profile. Trong access token, các claims mang vai trò khác. Không chỉ kiểm chữ ký mà cần kiểm assertion type, audience, expiry, `jti` replay và client registration.

### 10.4. Logout token không phải access token

OIDC Back-Channel Logout token có `events` dành cho logout, được RP nhận theo protocol và kiểm các claims riêng. Nếu API chấp nhận logout JWT như bearer access token chỉ vì OP signature hợp lệ, đó là cross-JWT confusion.

### 10.5. JWT access token không phải refresh token

Refresh token được client trình tới AS token endpoint, thường có lifecycle/rotation riêng. Không dùng JWT access token có chữ ký hợp lệ như refresh token chỉ vì nó có `sub` và `exp`. Tương tự, RS không chấp nhận refresh token làm Bearer credential cho tài nguyên nghiệp vụ.

## 11. DPoP proof: `jwk` nhúng đúng giao thức nhưng không phải issuer trust

DPoP là một ví dụ rất rõ về **cùng một header `jwk` nhưng trust semantics khác**.

### 11.1. Cấu trúc DPoP proof

DPoP proof JWT minh họa:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<CLIENT_PUBLIC_X>",
    "y": "<CLIENT_PUBLIC_Y>"
  }
}
~~~

Proof JWT được client ký bằng **holder private key** tương ứng. Public JWK trong proof giúp verifier kiểm rằng client tạo proof bằng khóa đó.

Nhưng proof chỉ có ý nghĩa bảo vệ access token nếu AS/RS còn kiểm:

~~~text
DPoP proof signature and public key
    +
HTTP method htm
    +
HTTP target htu
    +
iat freshness
    +
jti replay protection
    +
ath binding to access token at RS
    +
cnf.jkt on token matches proof public key thumbprint
    +
nonce when required
~~~

### 11.2. Key confusion giữa DPoP và issuer JWT

Sai:

~~~text
Orders API nhận access token T1 và DPoP proof P1.
API dùng public JWK trong P1 để "verify" T1.
~~~

Đúng:

~~~text
T1:
    verify bằng trusted AS issuer signing key.
    validate iss/aud/exp/scope/cnf.

P1:
    verify bằng public DPoP holder key trong proof.
    validate htm/htu/iat/jti/ath/nonce.

Binding:
    public key thumbprint của P1 == cnf.jkt của T1.
~~~

**DPoP proof xác nhận holder key, không xác nhận issuer được phép phát hành access token.** Đổi chéo hai nguồn khóa là một dạng key confusion, kể cả khi cả hai dùng ES256.

### 11.3. Không dùng `kid` của proof để chọn AS key

Một proof có thể không dùng `kid` hoặc có key hint theo profile. RS không nên đưa hint đó vào JWKS lookup của OP. AS public keys và DPoP public key là **hai không gian tin cậy**.

### 11.4. DPoP key bị đánh cắp khác AS signing key bị lộ

Nếu attacker có DPoP holder private key và token tương ứng, họ có thể tạo proof mới nếu các điều kiện khác phù hợp. Nhưng điều này **không tự cấp** khả năng ký arbitrary AS access tokens. Incident response cần revoke/rebind tokens holder và xử lý device compromise; nếu AS signing key bị lộ, phải emergency-distrust tại RS/RP.

### 11.5. Sender-constrained token không thay authorization

Kể cả token và proof đều hợp lệ, Orders API vẫn phải kiểm Alice có thể xem **order cụ thể** không. `scope=orders:read` không tự biến Alice thành owner của mọi đơn.

## 12. mTLS-bound tokens và certificate key confusion

OAuth mTLS có thể dùng certificate/private key của client cho authentication và sender-constrained access token.

### 12.1. Key binding theo certificate fingerprint

Một access token có thể chứa thông tin `cnf` ràng buộc certificate thumbprint, ví dụ key confirmation claim theo profile:

~~~json
{
  "iss": "https://login.example.com",
  "aud": "https://orders.example.com",
  "cnf": {
    "x5t#S256": "<CLIENT_CERT_SHA256_THUMBPRINT>"
  },
  "exp": 1893495600
}
~~~

RS kiểm access token bằng **AS signing key** rồi so certificate của mTLS connection với thumbprint ràng buộc. Certificate client **không phải AS signing key**, cũng không được tự cấp quyền qua claims của token.

### 12.2. Ba nhầm lẫn cần tránh

1. **Nhầm certificate public key của client với issuer JWT signing key**: client cert có chữ ký CA nhưng không có quyền mint access token.
2. **Nhầm TLS server certificate với mTLS client certificate**: đúng transport endpoint không có nghĩa request holder của access token được xác thực.
3. **Chỉ kiểm cert chain mà bỏ `cnf` binding**: không chứng minh sender đang dùng đúng certificate đã ràng buộc với token.

### 12.3. Proxy và trust boundary

Nếu TLS chấm dứt tại reverse proxy, downstream RS có thể nhận thông tin client certificate qua một kênh nội bộ đã được bảo vệ. Không tin header `X-Client-Cert` tùy ý từ internet. Proxy phải:

- Xác thực client certificate thật.
- Xóa/ghi đè client-supplied identity headers.
- Truyền identity tới RS trên kênh nội bộ được xác thực và ủy quyền.
- Đảm bảo RS bind đúng certificate thumbprint với token.

Không chỉ dựa vào một string `subject=trusted` do request tự khai.

### 12.4. Client certificate bị compromise

Nếu private key của client certificate bị đánh cắp, thay cert và revoke/rotate token binding theo policy. Đừng giải quyết bằng cách rotate AS JWT signing key khi sự cố chỉ nằm ở **client mTLS key**. Ngược lại, nếu AS key bị compromise, chỉ revoke client cert không chặn access token forgery.

## 13. JWE và nested JWT: nhầm key mã hóa thành key ký

Một encrypted JWT có thể dùng hai hoặc nhiều lớp khóa:

~~~mermaid
flowchart TD
    A[Incoming compact JWE] --> B[Identify trusted recipient decryption profile]
    B --> C[Decrypt with authorized JWE key]
    C --> D[Inner JWS JWT if required by profile]
    D --> E[Verify AS signature with trusted signing key]
    E --> F[Validate token type, iss, aud, exp, scope]
    F --> G[Business authorization]
~~~

### 13.1. Ciphertext authenticity không thay issuer signature

Một JWE dùng authenticated encryption bảo vệ integrity trong ngữ cảnh các bên có key, nhưng **quyền tạo ciphertext** phụ thuộc key management profile. Nếu cả attacker và service khác có thể encrypt bằng một public encryption key của RS, việc decrypt thành công **không chứng minh chỉ AS đã tạo nội dung đó**.

Khi profile yêu cầu **sign-then-encrypt**, RS phải xác minh inner JWS signature của AS sau decrypt; không tin claims chỉ vì JWE decrypt và tag hợp lệ.

### 13.2. Tách purpose `sig` và `enc`

~~~text
K_SIGN_PRIVATE:
    AS ký inner JWS.

K_SIGN_PUBLIC:
    RS xác minh inner JWS.

K_ENC_PUBLIC:
    AS hoặc sender mã hóa JWE gửi RS.

K_DEC_PRIVATE:
    RS giải mã JWE.
~~~

Một ứng dụng dùng `K_DEC_PRIVATE` để xác minh issuer signature hoặc `K_SIGN_PUBLIC` để giải mã token là nhầm key use. Library JOSE phải phân biệt JWS algorithms, JWE key management algorithms và content encryption `enc`.

### 13.3. Không để `alg` hoặc `enc` tùy ý đổi chính sách

Với JWE, `alg` có ý nghĩa **key management**, còn `enc` là **content encryption**. Các trường này phải nằm trong allowlist đã được xác định theo recipient/profile; không được cho JWT tự chọn một thuật toán yếu/không mong muốn hoặc key khác trust domain để decrypt.

### 13.4. Tách outer vs inner claims

Nếu nested JWT có cả metadata ngoài/claims trong, cần biết **claim nào được chứng thực bởi lớp nào**. Không dùng outer unverified hint làm `sub`, `aud`, `scope` đáng tin thay inner signed token. Đồng thời không bỏ `typ`/`cty`/profile checks phù hợp.

### 13.5. Khi JWE key bị lộ

Lộ private decryption key có thể làm claims bí mật bị đọc và đòi hỏi re-encryption/data impact review, nhưng **không tự** cho attacker quyền ký inner JWS nếu issuer signing key tách riêng. Đây là **key compromise có mục đích khác**, không tự suy thành JWT signer compromise.

## 14. Authorization Server và client keys: cách ly key registry theo nghiệp vụ

Một Authorization Server có thể giữ nhiều tập khóa:

~~~text
AS token signing keys:
    K_AS1_public/priv, K_AS2_public/priv

Registered client credentials:
    Client C1: client secret hoặc C1_public for private_key_jwt
    Client C2: C2_public for private_key_jwt

OIDC RP public keys:
    Có thể dùng cho mã hóa ID token/JAR hoặc client authentication
    theo đăng ký và profile.

DPoP holder keys:
    D1_public riêng cho mỗi holder/token binding.

TLS/mTLS trust:
    Certificate verification và transport identity.
~~~

### 14.1. Mỗi key có một namespace và mục đích

Thay vì:

~~~text
allTrustedKeysByKid["shared"] = <SOME_PUBLIC_KEY>
~~~

nên biểu diễn:

~~~text
KeyTrustContext:
    issuer
    keyOwner / clientRegistration
    tokenPurpose
    acceptedAlgorithms
    keyId and/or keyFingerprint
    lifecycleState
    validity/rotationPolicy
    tenant/environment boundary
~~~

Một key hợp lệ cho **client authentication** không tự chuyển thành key hợp lệ cho **access token issuance**.

### 14.2. Một client không được sửa signing key của AS

Ví dụ client đăng ký public JWK để dùng `private_key_jwt`. Nếu API cho nó tự sửa `jwks_uri` của **issuer metadata** hoặc đưa JWK vào AS signing key registry, attacker có thể đưa chính khóa của họ thành trusted AS signer.

Phải tách quyền **client registration administration** khỏi quyền **issuer signing key publication**; cả hai đều cần validation và audit.

### 14.3. Dynamic client registration

Dynamic client registration là một workflow có chính sách riêng; một client có thể đăng ký public key phục vụ **client-specific features**. Nhưng việc một client đăng ký JWK thành công **không cấp phép token do client đó ký được nhận là access token của AS**.

### 14.4. Token exchange, delegation và actor claims

Trong hệ thống dùng token exchange (RFC 8693), token từ issuer/token type này có thể được chuyển đổi thành token khác qua **AS được tin**. RS không nên tự coi token đầu vào như token đầu ra chỉ vì cùng subject hoặc key algorithm. Token exchange là một **ủy quyền/phát hành** có ranh giới, không phải “cho phép mọi token có chữ ký hợp lệ qua mọi API”.

### 14.5. Key reuse làm tăng blast radius

Khi dùng cùng private signing key cho nhiều issuers, token types hoặc environments, compromise một nơi có thể ảnh hưởng rộng. Ngay cả khi reuse hợp lệ theo profile, cần explicit token type/issuer/audience controls; với đa tenant hay nhiều trust domains, ưu tiên key separation phù hợp threat model.

## 15. Java/Spring Security: khóa được chọn từ issuer tin cậy

Spring Security Resource Server có khả năng xác minh OAuth JWT access token dựa trên issuer hoặc JWKS cấu hình. Với hệ thống Java, điều quan trọng không phải viết bộ parser tự tạo mà là **cấu hình trust policy đúng và kiểm các custom claims cần thiết**.

### 15.1. Cấu hình ban đầu cho một issuer

~~~yaml
# application.yml — ví dụ Resource Server cho Orders API
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
~~~

Khi dùng issuer location phù hợp, framework có thể lấy metadata/JWKS từ **issuer đã được cấu hình**. Nhưng cấu hình này **không tự** chứng minh:

- JWT có audience dành Orders API.
- JWT đúng access-token profile/`typ`.
- Scope đủ cho action cụ thể.
- Principal được truy cập order/tenant đang yêu cầu.
- Key đã compromised không còn trong caches/trust set.
- Multi-issuer configuration đã tách keys giữa issuers.

### 15.2. Decoder với JWKS URI tin cậy và pin thuật toán

Ví dụ Spring Security servlet, tùy phiên bản và bộ phụ thuộc:

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
public class OrdersResourceServerJwtConfig {
    private static final String ISSUER =
        "https://login.example.com";

    private static final String JWKS =
        "https://login.example.com/.well-known/jwks.json";

    private static final String AUD =
        "https://orders.example.com";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audValidator = jwt -> {
            if (jwt.getAudience().contains(AUD)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Wrong audience",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audValidator));

        return decoder;
    }
}
~~~

Ý nghĩa:

1. `JWKS` được lấy từ **server configuration**, không từ `jku` caller đưa.
2. `RS256` là thuật toán được cho phép theo hợp đồng với issuer.
3. Validator kiểm `iss` và thời gian theo khả năng framework/defaults.
4. API tự thêm kiểm **audience**.
5. JWT được xác minh qua trust set mà decoder quản lý; **không đưa client public JWK vào đó**.

Đây là ví dụ để hiểu cách chốt trust, **không phải toàn bộ Spring Security setup production**. Phải thêm `SecurityFilterChain`, token profile/type checks (nếu profile đòi), scopes, exception handling, TLS/HTTP hardening, key cache emergency policy và business authorization. Xác minh API từng phiên bản Spring/Nimbus trước khi đưa vào dự án.

### 15.3. Kiểm token type với profile đã thỏa thuận

Một Resource Server dùng RFC 9068 JWT access token có thể đòi `typ=at+jwt` (hoặc dạng JOSE theo spec/profile) và các claims bắt buộc. Ví dụ một **additional check**:

~~~java
// Minh họa thêm validator trong chuỗi validators sau khi decoder
// đã xác minh cryptographic signature bằng trusted key set.
OAuth2TokenValidator<Jwt> accessTokenTypeValidator = jwt -> {
    Object typ = jwt.getHeaders().get("typ");
    if ("at+jwt".equals(typ) || "application/at+jwt".equals(typ)) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Unexpected JWT type",
            null));
};
~~~

**Lưu ý:** `typ` có thể được library chuẩn hóa, và các profiles khác có hợp đồng riêng. Không ép mọi ID token/JWT phải có `at+jwt`; ví dụ này là kiểm thêm cho **access tokens theo RFC 9068**. Chốt expected token type bằng **resource server policy**; không để caller gửi một custom header rồi quyết định endpoint xử lý “ID token mode”. Một số phiên bản Nimbus/Spring Security thực hiện kiểm `typ` **ngay tại JWT processor, trước custom validators**; nếu triển khai profile `at+jwt`, phải cấu hình JOSE type verification phù hợp và kiểm thử decoder thực tế, không giả định chỉ thêm hậu-validator là đủ.

### 15.4. Không sửa lỗi key confusion bằng cách parse JWT trước rồi tự tìm key

Anti-pattern:

~~~java
// SAI — pseudocode minh họa mẫu cần tránh.
UnverifiedJwt claims = decodeWithoutVerification(rawBearerToken);
String issuer = claims.getIssuer();
String jwksUrl = claims.getHeader("jku");

TrustedKeys keys = download(jwksUrl); // Caller có thể chọn URL.
verifyWithAnyKey(rawBearerToken, keys);
~~~

Đúng hướng:

~~~java
// Pseudocode kiến trúc; không phải Spring API có sẵn.
TrustedApiPolicy policy = policyStore.forResource("orders-api");
JwtDecoder decoder = decoderRegistry.forAllowedIssuer(
    policy,
    issuerRoutingHintFromJwt);

VerifiedJwt verified = decoder.verify(rawBearerToken);

policy.requireIssuer(verified.issuer());
policy.requireAudience(verified.audience());
policy.requireAccessTokenType(verified.headerType());
policy.requireAllowedScopes(verified.scopes());
policy.requireCurrentKeyTrust(verified.keyIdentity());

ordersAuthorization.requireActionOnResource(
    verified.principal(), "orders:read", requestedOrder);
~~~

`issuerRoutingHintFromJwt` nếu có chỉ là **hint để chọn decoder trong allowlist**. Kết quả `decoder.verify` và các checks phải liên kết issuer được khai với **issuer của decoder** và key set thật đã dùng. Không tự gọi `decode` như bằng chứng authentication.

### 15.5. Một decoder cho mỗi trust domain khi có nhiều issuer

Ví dụ cấu trúc tốt:

~~~text
TrustedDecoderRegistry:
    idp-A:
        issuer = https://idp-a.example
        jwks = trusted Jwks A
        algorithms = RS256
        audience policy = orders-api

    idp-B:
        issuer = https://idp-b.example
        jwks = trusted Jwks B
        algorithms = ES256
        audience policy = orders-api
~~~

Một `AuthenticationManagerResolver` có thể định tuyến theo issuer được khai, nhưng **phải kiểm allowlist** trước khi dựng decoder để tránh việc gọi arbitrary issuer discovery/JWKS endpoints từ token do attacker gửi. Sau xác minh phải enforce issuer/audience/profile.

### 15.6. Không dùng validators để thay key resolver hoàn toàn

Một validator hậu xác minh có thể xem `kid`/claims, nhưng có thể chưa đủ để chặn **same key material dưới alias khác**, hoặc một lỗi key type/algorithm trong decoder. Các ràng buộc key source, accepted algorithm và trust-root binding phải nằm **tại chính bước cryptographic verification/key resolution**.

## 16. Java/Nimbus JOSE: cấu trúc key selection đúng

Khi cần tùy chỉnh sâu, hãy giữ nguyên tắc:

~~~text
Trusted profile:
    expectedIssuer
    trustedJwksUri
    approvedAlgorithms
    permittedKeyTypes
    keyPurpose
    expectedAudience
    expectedTokenType
    keyTrustPolicyVersion

Candidate key selection:
    Parse untrusted protected header.
    Filter ONLY keys from profile trustedJwksUri.
    Check key type, use/key_ops and algorithm compatibility.
    Reject blocked or stale keys.
    Cryptographically verify signature.

Claims:
    Check iss/aud/time/type/scope/authorization.
~~~

### 16.1. Không dùng chung `JWKSource` cho issuer và client

Một **JWKSource** cho AS signing public keys có vai trò khác **JWKSource** cho từng OAuth client. Nếu viết lớp `AllKeys` chứa cả hai tập rồi chuyển hết vào một JWT processor không có key context, sẽ dễ dẫn đến client-key-as-issuer-key confusion.

Thiết kế nên có:

~~~text
IssuerJwtVerifier:
    expected AS/OP issuer.
    issuer JWKS only.

ClientAssertionVerifier:
    expected client_id.
    registered client JWKS only.
    token endpoint aud and assertion rules.

DPoPProofVerifier:
    proof embedded public JWK.
    sender binding + method/URI/ath/jti/iat.

JweRecipient:
    expected recipient decryption keys.
    content encryption and inner JWT profile.
~~~

Các lớp này **không nên** dùng chung một key map truy cập bằng `kid` thuần.

### 16.2. JWK thumbprint và lifecycle state

`kid` là label; **JWK thumbprint** theo RFC 7638 có thể giúp nhận diện public key material theo profile. Khi khóa bị lộ hoặc bị thu hồi, security policy nên liên kết key fingerprint/issuer hơn là chỉ một chuỗi `kid`.

Nhưng fingerprint cũng **không tự chứng minh authority**: attacker có thể tính thumbprint cho public key của họ. Fingerprint chỉ có ý nghĩa khi được lưu trong **trusted key registry** cùng issuer, purpose và policy status.

### 16.3. Thuật toán ký ECDSA/EdDSA

Nếu AS dùng ES256/EdDSA, áp dụng nguyên tắc tương tự:

- Chỉ nhận algorithms đã phê duyệt.
- Kiểm `kty`/curve/key strength theo JOSE profile.
- Không tự chuyển EC/OKP public key thành HMAC secret.
- Không cho caller chọn curve hoặc key material ngoài trust set.
- Dùng thư viện JOSE xử lý signature encoding/verification đúng.

Không tạo “universal verifier” thử RSA, EC, EdDSA và HMAC với mọi key cho đến khi một cách xác minh PASS. Mỗi token type/issuer có một **algorithm/key type policy cụ thể**.

### 16.4. Cần giới hạn tài nguyên xử lý parser

Attacker có thể gửi JWT có:

- Header rất lớn.
- `kid` chuỗi bất thường.
- `x5c` chain quá dài.
- Nested JWT sâu.
- Nhiều JWKS URLs/redirects.

Đặt size, timeout, depth, key-count và cache-refresh rate limits theo thư viện/framework để tránh DoS. Parser thất bại phải **fail closed**; không dùng lỗi parse làm lý do bỏ verification.

### 16.5. Kiểm đối chiếu chính sách độc lập

Một cách kiểm cấu hình:

~~~text
For each Resource Server:
    Enumerate configured trusted issuers.
    Enumerate allowed JWS algorithms per issuer.
    Enumerate trusted JWK sources.
    Enumerate accepted token types/audiences.
    Ensure no client-owned/DPoP/other issuer keys enter AS trust.
    Ensure all keys have lifecycle state/rotation story.
    Ensure unknown kid/alg/jku cannot trigger fail-open.
~~~

## 17. JWKS rotation, caches và key confusion khi vận hành

### 17.1. Planned rotation

Một planned rotation có thể:

~~~text
T0: K1 public có trong JWKS; AS ký K1.
T1: Publish K2 public trước.
T2: RS/RP đã có đường lấy K2.
T3: AS chuyển ký K2.
T4: Giữ public K1 đến khi token K1 hợp lệ hết hạn.
T5: Retire K1 khỏi trusted JWKS theo policy.
~~~

**Chuyển khóa phát hành** và **cập nhật verifier** là hai hành động khác nhau. Nếu K2 chưa được RS biết, token hợp lệ mới có thể bị 401; không xử lý bằng cách chấp nhận chữ ký từ key bất kỳ.

### 17.2. Emergency key compromise

Khi private K1 bị lộ hoặc khả năng KMS Sign bị chiếm:

- Chặn signing capability bị chiếm.
- Sinh K2 thật sự mới và bảo vệ K2.
- **Ngừng tin K1** tại mọi RS/RP, kể cả JWKS caches/local config.
- Đo propagation và xử lý region offline theo fail policy.
- Không chỉ blacklist một `kid` nếu cùng key có aliases khác.
- Không đợi token K1 tự hết hạn nếu security objective cần chặn sớm.

### 17.3. Key confusion do stale cache và `kid` reuse

~~~text
Node A:
    kid=current -> K1 public.

Node B:
    kid=current -> K2 public.

K1 compromised:
    security policy = BLOCKED K1.
~~~

Nếu application không có key identity/version/fingerprint binding, một số nodes vẫn có thể dùng K1 dưới label `current`. Tránh tái sử dụng `kid` cho key material mới khi không có lý do/semantics rõ, và có monotonic key-trust policy trong emergency.

### 17.4. Cache refresh khi không thấy `kid` lạ

Một số verifier refresh JWKS khi JWT có `kid` không tìm thấy. Nhưng attacker với K1 private có thể tiếp tục dùng `kid` cũ **đã nằm trong cache**, nên không có refresh. Bởi vậy emergency distrust phải có đường **push/invalidation/freshness policy** độc lập với unknown-`kid` fallback.

### 17.5. Key cache fill race

~~~text
T0: RS fetch JWKS cũ từ CDN, request chưa trả.
T1: Security event BLOCKED K1, cache bị xóa.
T2: Fetch T0 hoàn thành, ghi lại K1 public vào cache.
T3: RS tiếp tục chấp nhận K1.
~~~

Chỉ `cache.evict()` chưa đủ. Cần **version-aware cache write**, blocked-fingerprint list riêng, authoritative trust state và ready/fail-closed policy.

### 17.6. Cross-region restore không được hồi sinh key bị block

Một backup key registry từ hôm qua chứa `K1=ACTIVE`. Hôm nay K1 bị compromised và chuyển `BLOCKED`. DR restore backup hôm qua không được làm K1 active trở lại. Security tombstone/version phải được replay từ authoritative journal trước khi RS phục vụ traffic nhạy cảm.

### 17.7. Không dùng arbitrary key lookup làm availability fallback

Sai:

~~~text
Trusted JWKS unavailable.
    -> Try "jku" URL from JWT.
    -> Or trust locally cached client JWKS.
    -> Or skip verification until issuer recovers.
~~~

Đúng hướng là fail closed hoặc dùng trusted, fresh-enough snapshot/cơ chế introspection theo risk policy. **Availability tradeoff phải được thẩm định**, không biến outage thành lỗ hổng key confusion.

## 18. Log, audit và phát hiện dấu hiệu key confusion

### 18.1. Tín hiệu cần quan sát

| Tín hiệu | Điều cần điều tra |
|---|---|
| Đột ngột nhiều JWT có `alg` ngoài allowlist | Misconfiguration, scanning hoặc attacker input |
| `kid` lạ/không match trong issuer JWKS | Rotation lag, token giả, issuer mismatch |
| Requests có `jku`/`x5u` ngoài profile | Có dynamic fetch nguy hiểm không? |
| JWT chứa `jwk` nhúng gửi vào Bearer API | Có nhầm DPoP/client public key thành issuer signer không? |
| Key issuer A được dùng cho token tự khai issuer B | Cross-issuer key lookup |
| Có cả HMAC secret và public RSA trong cùng key resolver | Potential HS/RS confusion |
| OIDC ID token xuất hiện ở RS Authorization header | Cross-JWT confusion hoặc client integration bug |
| `typ=dpop+jwt` được API ghi nhận như access token | Token purpose validation sai |
| JWKS source mới được thêm không qua approval | Key substitution/metadata compromise |
| Một RS cập nhật key trust chậm nhiều giờ | Stale cache/partition/DR bootstrap |
| Client registration key trùng issuer public key material | Key reuse / suspicious configuration |
| Các failed JWT checks bị tự động retry với verifier khác | Potential fail-open/fallback path |

### 18.2. Log metadata nhưng không lưu bearer token

Có thể ghi audit theo chính sách:

~~~text
requestCorrelationId
resourceServerId / region
expectedIssuer
claimedIssuer (chưa tin, phải gắn nhãn unverified)
tokenTypeHint / headerAlg / kid as untrusted metadata
keySelectionContext
trustedKeyFingerprint used
trustPolicyVersion
validationOutcome
failureCategory = WRONG_ALG | UNKNOWN_KID | WRONG_ISSUER | WRONG_AUD
~~~

Không ghi:

~~~text
Authorization: Bearer <RAW_ACCESS_TOKEN>
refresh_token=<SECRET>
id_token=<JWT_WITH_USER_CLAIMS>
privateSigningKey=<SECRET>
HMACSecret=<SECRET>
DPoPPrivateKey=<SECRET>
client_secret=<SECRET>
~~~

`kid`, claimed issuer, client ID và key fingerprint cũng có thể là metadata nhạy cảm, cần retention/access control. Một `kid` do attacker nhập có thể chứa control characters; **escape/normalize trước khi log** để tránh log injection.

### 18.3. Việc JWT signature PASS có thể là tín hiệu giả

Nếu verifier dùng **khóa sai nguồn**, metric `signature_valid=true` không chứng minh token hợp lệ. Cần khả năng audit:

~~~text
signedWithKey = trusted issuer key?
selectedBy = configured issuer JWKS, not arbitrary header URL?
algorithm = approved for this issuer/token type?
claims = valid for resource?
principal = allowed for object/action?
~~~

### 18.4. Cảnh báo bảo mật khi key trust thay đổi

Security logs nên ghi các thay đổi:

- Issuer registration/trusted JWKS URI.
- Key set additions/removals và public key fingerprints.
- Allowed JWS algorithm list.
- Client JWT authentication JWKS.
- DPoP proof key binding policy.
- Emergency blocked keys và cache invalidation lag.

Một attacker không cần đánh cắp AS private key nếu họ có thể tự thay trusted JWKS của RS. Vì thế **quyền thay trust configuration** nhạy cảm tương đương năng lực nhận dạng issuer trong hệ thống.

## 19. Threat model: key confusion ở từng điểm trong đường token

| Điểm vào/ranh giới | Lỗi key confusion | Hậu quả có thể có | Kiểm soát phòng thủ |
|---|---|---|---|
| **Bearer token parser** | Header `alg` trực tiếp quyết định verifier algorithm | HS/RS confusion hoặc unsecured JWT được nhận | Server-side algorithm allowlist |
| **JWKS selector** | Key lookup chỉ theo `kid` toàn cục | Issuer/tenant khác bị trộn khóa | Issuer-scoped registry + key identity |
| **JWK source** | Token tự cung cấp `jku` làm trusted source | Key substitution, SSRF | Configured trusted JWKS URI |
| **Certificate loader** | Token `x5u`/`x5c` tự làm trust anchor | Cert khác được dùng làm issuer signer | PKI policy + issuer/key binding |
| **Embedded JWK** | Dùng `jwk` của token để verify access token | Attacker tự cấp key trust | Chỉ issuer public key set được tin |
| **JWK metadata** | Tin `use=sig` của JWK bất kỳ | Key sai mục đích được nhận | Nguồn trusted + policy `use/key_ops` |
| **`alg=none` path** | Cho phép bỏ chữ ký ở Bearer API | Nhận JWT tự khai | Reject unsecured JWT trong profile |
| **Critical extensions** | Bỏ qua `crit` không hỗ trợ | Semantics signing bị hiểu sai | Reject unknown critical headers |
| **Issuer resolver** | Fetch JWKS từ `iss` tự khai tùy ý | Trust arbitrary issuer hoặc SSRF | Trusted allowlist + issuer recheck |
| **Token type** | API tin ID token như access token | Login artifact bị dùng để gọi API | Explicit access-token profile + aud |
| **Client assertion** | Client public key được dùng như AS signer | Client tự ký token cho API | Separate issuer/client key stores |
| **DPoP proof** | DPoP embedded JWK trở thành AS key | Holder proof bị nhầm token issuer | Separate proof verification + `cnf` |
| **mTLS client** | Certificate client được dùng ký issuer JWT | Client identity thành token issuer | Key purpose & certificate binding |
| **JWE recipient** | Decryption key được dùng như signing trust | Decrypt được bị coi là issuer-authentic | Inner JWS verification khi profile yêu cầu |
| **Tenant routing** | Tenant claim chưa verify chọn trust/policy tùy ý | Cross-tenant impersonation | Tenant/issuer authorization binding |
| **Environment** | Prod tin staging key | Leak staging ảnh hưởng prod | Separation dev/stage/prod |
| **Key rotation** | Tái sử dụng `kid` và cache stale | Các node chọn key khác nhau | Key version/fingerprint-aware rotation |
| **Emergency revoke** | Block một `kid`, không block same key alias | K1 compromise vẫn được dùng | Distrust actual key material |
| **Network failure** | Unknown key => accept unsigned token | Outage dẫn đến authentication bypass | Fail closed |
| **Audit/logging** | Log raw JWT và dynamic key source | Credential leakage/SSRF khó điều tra | Redaction + key trust telemetry |
| **Authorization** | JWT đã verify => cho mọi scope/resource | BOLA/IDOR và role abuse | Resource/action/tenant checks |

### 19.1. Attacker control cần được xác định rõ

Một threat model tốt hỏi attacker kiểm soát được gì:

~~~text
Level 1: JWT bytes (headers, payload, signature) gửi đến RS.
Level 2: JWK/JWKS public endpoint của attacker.
Level 3: Public key trong registered OAuth client.
Level 4: Client holder private key (DPoP/private_key_jwt).
Level 5: Quyền thay issuer/key configuration của RS.
Level 6: Private AS signing key hoặc KMS Sign capability.
~~~

Các cấp **không nhất thiết tạo thành quan hệ bao hàm**; ví dụ có client private key không có nghĩa có AS private key. Mỗi cấp có những attack paths và controls khác nhau. Không kết luận key compromise nếu vấn đề chỉ là verifier đã tin sai public key, và không kết luận chỉ là key confusion nếu private key issuer đã thực sự bị đánh cắp.

### 19.2. Phòng thủ theo ba lớp

**Crypto trust:** đúng issuer/JWKS/key/algorithm và key lifecycle.

**Token context:** đúng token type, audience, claims/expiry, scope và OAuth/OIDC profile.

**Business authorization:** đúng subject, client, tenant, resource và action.

Một token phải đi qua **cả ba**. Nếu lớp crypto bị lỗi, lớp business có thể giảm tác động nhưng không thể lấy lại bảo đảm rằng issuer thật đã phát token.

### 19.3. Nhầm thông tin từ headers của reverse proxy

Nếu Resource Server tin `X-Authenticated-Issuer` hoặc `X-Verified-Client-Cert` từ mọi request, attacker có thể bỏ qua key selection/tls-binding logic bằng header tự đặt. Gateway/proxy phải xác thực và **xóa/ghi đè** các headers do caller gửi, sau đó truyền thông tin qua kênh nội bộ được bảo vệ.

Chỉ dùng header identity nếu trust boundary đã được thiết kế rõ, không coi mọi header bắt đầu bằng `X-` là bằng chứng đã verify.

### 19.4. JWKS source compromise khác private key compromise

Nếu attacker sửa được JWKS của issuer để thêm public KX, RS có thể tin token do attacker ký bằng KX dù private key K1 nguyên vẹn. Cần kiểm:

- Ai quản lý/publish metadata/JWKS?
- DNS/TLS/CDN/proxy có bị chiếm?
- RS có pin issuer/key policy phù hợp không?
- Key registry có audit và approval không?
- Khi khắc phục, JWKS caches và token trust đã hội tụ chưa?

**Vì thế key trust source là một tài sản bảo mật quan trọng**, không chỉ private key storage.

## 20. Ma trận kiểm thử key confusion: phải có negative cases

Test “JWT hợp lệ được chấp nhận” không phát hiện đầy đủ key confusion. Cần nhiều token **có cấu trúc hợp lệ nhưng không đúng trust context** và kiểm rằng hệ thống từ chối.

### 20.1. JWS algorithm và key type

| Test | Kết quả mong muốn |
|---|---|
| RS256 JWT do AS ký, đúng issuer/audience | Có thể qua crypto/token checks; tiếp tục business policy |
| `alg=HS256` gửi tới RS256-only API | Từ chối, không dùng RSA public PEM làm HMAC secret |
| `alg=none` với payload có claims hợp lệ | Từ chối |
| `alg=PS256` khi policy chỉ cho RS256 | Từ chối dù cùng RSA key family |
| `alg=ES256` khi issuer chỉ dùng RSA | Từ chối |
| JWK `kty=oct` được đưa vào public JWKS | Fail security review; không công khai secret |
| EC key không đúng curve cho algorithm | Từ chối |
| EdDSA/OKP key bị ép vào HMAC/RSA verifier | Từ chối |
| JWK `use=enc` được đưa làm signing key | Từ chối theo key purpose/profile |
| JWK `key_ops` không phù hợp verification | Từ chối hoặc không chọn key |
| JWT khai báo unknown critical header | Từ chối |
| JWT thiếu protected signature khi profile yêu cầu | Từ chối |
| JWT signed correctly nhưng `exp` đã qua | Từ chối |
| JWT có lifetime quá policy maximum | Từ chối nếu policy áp dụng |

### 20.2. `kid` và JWKS lookup

| Test | Kết quả mong muốn |
|---|---|
| Issuer A/B cùng có `kid=current` | Keys không bị trộn giữa issuers |
| JWT tự khai `kid` của issuer khác | Không dùng key ngoài expected trust set |
| `kid` không tồn tại | Từ chối; refresh chỉ từ trusted JWKS URI nếu policy cho phép |
| `kid` có ký tự path/SQL đặc biệt | Không đọc file tùy ý, không raw SQL injection |
| `kid` quá dài | Bị giới hạn hoặc từ chối an toàn |
| Không có `kid` nhưng issuer JWKS chỉ có một key phù hợp | Behavior theo profile/library policy, không thử key ngoài issuer |
| Không có `kid` và JWKS có nhiều keys | Không chấp nhận bừa; chỉ thử trusted compatible keys nếu policy cho phép |
| Cùng key material xuất hiện với hai `kid` | Security policy vẫn nhận đúng fingerprint |
| Compromised K1 bị block, đổi header `kid` | Không làm K1 trusted trở lại |
| Stale JWKS cache sau K1 revoke | RS chặn K1 theo emergency trust state |
| Key K2 chưa được RS biết khi rotation | Không bypass verification để tăng availability |

### 20.3. `jku`, `x5u`, `jwk`, `x5c`

| Test | Kết quả mong muốn |
|---|---|
| JWT mang `jku` attacker URL | Verifier không fetch/trust nguồn đó |
| JWT mang `jku` trỏ IP/hostname nội bộ | Không xảy ra SSRF qua verifier |
| JWKS URL HTTP 30x trỏ host ngoài allowlist | Không theo redirect vượt trust policy |
| `x5u` trỏ certificate attacker | Không thành AS issuer signer |
| JWT nhúng `jwk` public attacker | RS không dùng key đó để verify access token |
| JWT nhúng `x5c` với chain hợp lệ nhưng issuer binding sai | Từ chối |
| JWT khai `jku` trùng trusted URL nhưng có query bất thường | Không để URL input override trusted source |
| JWT có nhiều headers/extensions lạ | Giới hạn parse/unsupported `crit` |
| Public JWK có private fields ở JWKS | Cảnh báo key leak, incident handling |
| JWKS từ DNS/metadata thay đổi ngoài kế hoạch | Detect publisher trust/source change |

### 20.4. OAuth/OIDC token purpose và key scopes

| Test | Kết quả mong muốn |
|---|---|
| ID token có OP signature gửi tới Orders API | Từ chối: sai audience/type |
| RFC 9068 access token gửi tới OIDC ID-token validator | Từ chối theo token type/nonce/aud profile |
| `private_key_jwt` client assertion gửi làm bearer access token | Từ chối; client key không phải issuer key |
| DPoP proof gửi như access token | Từ chối |
| DPoP proof public JWK được dùng làm AS key | Không xảy ra |
| DPoP proof sai method/URI | Từ chối |
| DPoP `ath` không khớp access token | Từ chối |
| DPoP proof `jti` replay | Từ chối theo replay policy |
| mTLS-bound token dùng certificate khác | Từ chối sender mismatch |
| mTLS certificate của client dùng ký AS token | Không được RS tin |
| JWT có `aud=payments` gửi Orders API | Từ chối |
| JWT ký issuer A nhưng tự khai `iss=issuer B` | Từ chối |
| JWT có scope `orders:read` nhưng resource thuộc Bob | Từ chối theo resource authorization |
| JWT từ staging gửi production API | Từ chối khi issuer/trust isolation đúng |
| OAuth refresh token gửi đến RS | Từ chối sai credential/type |

### 20.5. Cache, multi-region và failure modes

| Test | Kết quả mong muốn |
|---|---|
| Region A có K1 BLOCKED, region B vẫn cache K1 | Region B không ALLOW ngoài freshness budget |
| JWKS cache fill cũ đến sau invalidate mới | K1 không được ghi đè thành trusted |
| Consumer event duplicate | Idempotent, key block không bị xóa |
| Event `K1 trusted v17` đến sau `K1 blocked v18` | Không hồi sinh K1 |
| RS mới scale-out từ image chứa key cũ | Readiness yêu cầu current security state |
| Metadata/issuer endpoint unavailable | Không tin header `jku` làm fallback |
| CDN JWKS trả stale key set | Block policy/freshness xử lý đúng SLO |
| RS restore key registry snapshot cũ | Replay compromised-key tombstones |
| OAuth client vừa rotate public key | AS client assertion verifier cập nhật, RS issuer verifier không bị ảnh hưởng nhầm |
| Key publisher bị compromise | Detection/audit và trust recovery đúng issuer scope |
| Token có claim `iss` chưa verify của host lạ | Không tự kết nối tùy ý đến host đó |

### 20.6. Nguyên tắc thiết kế fixtures

Trong test, có thể tạo **synthetic keys**:

~~~text
K_AS_TEST    = issuer signing fixture key.
K_CLIENT_A   = client assertion fixture key.
K_DPOP_A     = DPoP holder fixture key.
K_TENANT_B   = other issuer fixture key.
~~~

Với từng token, test expected trust source:

~~~text
valid issuer token:
    K_AS_TEST -> ACCEPT if claims/business policy pass.

wrong source:
    K_CLIENT_A -> REJECT even if RSA signature is valid under K_CLIENT_A.

wrong issuer:
    K_TENANT_B -> REJECT under issuer A verifier.

wrong purpose:
    K_DPOP_A -> REJECT as AS access token signer.
~~~

**Không dùng production signing keys để tạo JWT giả rồi replay trên production API** trừ một bài kiểm thử bảo mật được phê duyệt có kiểm soát. Negative tests đủ để xác minh implementation trong môi trường cô lập.

## 21. Thử nghiệm tích hợp: Spring Security verifier nhiều issuer

Một kịch bản có thể chạy trong staging/test:

1. Tạo AS fixture issuer A và issuer B, mỗi issuer có JWKS độc lập.
2. Đặt **cùng `kid`** cho hai public keys khác nhau để kiểm namespace logic.
3. Cấu hình Orders API chỉ tin issuer A cho tenant A và issuer B cho tenant B theo allowlist.
4. Gửi JWT A hợp lệ; xác minh qua crypto/claims rồi kiểm order ownership.
5. Gửi JWT B tới tenant A; bảo đảm bị từ chối dù signature B đúng.
6. Gửi ID token A tới Orders API; bảo đảm `aud=client A` không được chấp nhận.
7. Gửi token với `alg=HS256` nhưng API chỉ cho `RS256`; bảo đảm từ chối.
8. Gửi token có `jku` pointing to test-controlled JWKS; xác minh không có key fetch vượt trusted config.
9. Tạo một OAuth client fixture với key C1; xác minh RS không tin C1 như AS signing key.
10. Mô phỏng K1 rotation→K2, cache cũ, revoke K1, stale restore.
11. Xác minh các region/instances đồng bộ trust policy và không fail-open khi nguồn metadata không có.
12. Bật audit nhưng bảo đảm logs không chứa raw tokens hoặc private keys.

### 21.1. Chứng minh fail closed

Khi không tìm được key:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <TOKEN_WITH_UNTRUSTED_KEY>
~~~

RS phải **không ALLOW**. Thông thường authentication failure tương ứng HTTP 401/Bearer `invalid_token` theo profile/hợp đồng API. Nếu trust service tạm outage, HTTP 503 có thể hợp lý theo kiến trúc; điểm quan trọng là không biến outage thành authentication success.

### 21.2. Chứng minh token profile

Không chỉ kiểm signature:

~~~text
signature valid using trusted issuer key   YES
issuer matches trusted issuer              YES
audience contains Orders API               YES
token type/profile matches access token    YES
expiry/nbf valid                           YES
scope sufficient                            YES
subject has permission on order 123        NO

=> REJECT by authorization policy.
~~~

### 21.3. Không tin callback UI làm test crypto

Một ứng dụng có thể hiển thị “đăng nhập thành công” hoặc chuyển browser đến trang Orders API, nhưng nó không chứng minh RS đã dùng **đúng issuer signing key**. Test phải quan sát **crypto verification path** và request outcome tại RS, không chỉ trang UI.

### 21.4. Kiểm nguyên nhân từ chối

Một JWT bị 401 vì `aud` sai **không chứng minh** verifier từ chối public key attacker. Hãy có fixture với claims đúng nhưng wrong key, sau đó assert đúng failure category trong audit không lộ secret.

## 22. Checklist cho code review và configuration review

### 22.1. Các câu hỏi phải hỏi

1. **Issuer có từ đâu?** Từ server allowlist hay lấy tùy ý từ claim chưa xác minh?
2. **JWKS URI có từ đâu?** Trusted issuer metadata hay token `jku`/`x5u`?
3. **Allowed `alg`** có được pin theo issuer/type không?
4. **Key type** được kiểm đúng HMAC vs RSA/EC/OKP không?
5. **Public vs private material** có bị đưa nhầm vào secret/key store không?
6. **Key use** `sig`/`enc`/`verify`/`decrypt` có được thực thi?
7. **`kid` cache namespace** có gắn issuer/key-set identity không?
8. **Same key multiple aliases** có được xử lý theo fingerprint khi revoke không?
9. **Untrusted `jwk`** có bị dùng làm AS signing trust không?
10. **`crit`** có được xử lý/reject khi unknown không?
11. **Token type** có phân biệt access, ID, DPoP, client assertion và logout JWT không?
12. **Audience** có khớp resource/client/token endpoint đúng không?
13. **Scope và authorization** được kiểm trên action/resource/tenant không?
14. **Multi-issuer** có allowlist/binding không; có trộn staging/prod không?
15. **Rotation** có khả năng chấp nhận K2 trước khi AS dùng không?
16. **Compromised key** có bị block ở mọi verifier và cache không?
17. **Fail mode** khi unknown key/JWKS timeout có fail closed không?
18. **Audit** có biết trusted key fingerprint/issuer/algorithm được dùng không?
19. **Test** có negative cases HS/RS, `alg=none`, wrong issuer, wrong key, `jku`, DPoP không?
20. **Incident response** có thể khôi phục issuer trust mà không phụ thuộc token claims của attacker không?

### 22.2. Dấu hiệu code cần review ngay

~~~text
readJwtHeader(rawToken).get("jku") -> httpGet(...)
readJwtClaims(rawToken).get("iss") -> fetchAnyDiscovery(...)
keyCache.get(kid)                 -> without issuer boundary
if signatureFails then allow
if jwksTimeout then skipVerification
if unknownKid then trust embedded jwk
if alg == HS256 then use publicPemAsHmacSecret
allIssuerKeys.addAll(clientRegisteredKeys)
if jwtDecodes then authenticated = true
if tokenHasScope then skipObjectOwnershipCheck
~~~

Những mẫu này cần điều tra sâu theo execution path, không nhất thiết từng chuỗi là một bug trong mọi codebase. Điểm chung: **dữ liệu chưa được xác minh bị nâng thành authority**.

## 23. Tình huống thực tế: kiểm tra suy luận và thiết kế phòng thủ

### Tình huống A — Public key bị dùng như HMAC secret

Orders API chỉ phải tin JWT ký RS256, nhưng một custom verifier cho phép header `alg=HS256` và lấy public RSA PEM làm HMAC secret.

**Câu hỏi:** Attacker có cần đánh cắp RSA private key không?

**Trả lời:** Trong verifier sai kiểu này, không nhất thiết. Public RSA PEM vốn có thể được tải từ JWKS. Cần chốt `RS256`, ràng buộc key type và không chuyển asymmetric public key thành symmetric secret.

### Tình huống B — JWT yêu cầu `alg=none`

Một JWT có claims hợp lệ và header `alg=none`, không có chữ ký được gửi tới Bearer-protected API.

**Câu hỏi:** Có thể tin vì `iss` và `aud` đúng không?

**Trả lời:** Không. Claims chưa được chứng thực; API yêu cầu signed access token phải từ chối unsecured JWT.

### Tình huống C — Hai issuer cùng `kid`

Issuer A và B đều dùng `kid=current` nhưng với public keys khác nhau. Một RS lưu cache theo key `"current"` thuần.

**Câu hỏi:** Vấn đề gì?

**Trả lời:** Key cache không namespace theo issuer; có thể xác minh nhầm hoặc gây inconsistency. Key lookup phải giới hạn theo issuer, key set, algorithm và purpose.

### Tình huống D — JWKS URL nằm trong token

JWT header có `jku=https://attacker.example/jwks`. RS tải JWK này rồi verify chữ ký token.

**Câu hỏi:** Chữ ký PASS có chứng minh AS đã ký không?

**Trả lời:** Không. Attacker có thể công bố public key của họ và ký bằng private key riêng. RS phải chỉ tin JWKS từ cấu hình/discovery issuer được xác minh.

### Tình huống E — Remote key lookup trở thành SSRF

Verifier tải `x5u` từ một URL bất kỳ do JWT cung cấp. Một request khiến backend truy cập mạng nội bộ trái policy.

**Câu hỏi:** Đây là lỗi khóa hay lỗi mạng?

**Trả lời:** Cả hai khía cạnh có thể liên quan: **key-source trust confusion** và **SSRF**. Không fetch arbitrary URLs từ unverified headers, kiểm redirects/host/network nếu remote reference thật sự cần.

### Tình huống F — Embedded JWK trong access token

Attacker gửi Bearer JWT có `jwk` chứa public key của attacker. Custom RS dùng key đó để verify JWT.

**Câu hỏi:** Vì sao không an toàn?

**Trả lời:** Attacker tự cấp khóa mà verifier sẽ tin. Access-token signature phải được xác minh bằng issuer signing keys từ trusted registry, không dùng self-declared JWK.

### Tình huống G — Embedded JWK trong DPoP

Một DPoP proof hợp lệ cũng chứa public JWK do client giữ.

**Câu hỏi:** Có phải mọi token chứa `jwk` đều sai?

**Trả lời:** Không. DPoP cần public JWK để verify holder proof; RS vẫn phải xác minh **access token riêng bằng AS signing key**, rồi bind proof thumbprint với `cnf.jkt` và request.

### Tình huống H — DPoP proof bị gửi như access token

Một client gửi JWT có `typ=dpop+jwt` trong header `Authorization: Bearer`.

**Câu hỏi:** Resource Server nên làm gì?

**Trả lời:** Từ chối sai token type/profile. DPoP proof là bằng chứng holder key cho một HTTP request, không phải access token cấp quyền gọi API.

### Tình huống I — ID token bị API chấp nhận

ID token của Shop Web được ký bằng OP key có `aud=shop-web`; Orders API dùng cùng OP JWKS và chỉ kiểm signature.

**Câu hỏi:** Token hợp lệ về chữ ký có đủ không?

**Trả lời:** Không. ID token dành cho RP, không phải OAuth access token dành cho Orders API. Kiểm expected audience, token type/profile và authorization.

### Tình huống J — Client assertion có chữ ký hợp lệ

Client `expense-sync` dùng private C1 ký một JWT assertion. Orders API thử verify assertion bằng public C1 được đăng ký tại AS.

**Câu hỏi:** Có thể cấp quyền API không?

**Trả lời:** Không. C1 được đăng ký cho **client authentication**, không phải issuer access-token signing. Tách trust stores.

### Tình huống K — Issuer B giả claim A

JWT được ký bằng issuer B key, nhưng payload có `iss=https://issuer-a.example`.

**Câu hỏi:** Nếu RS tin cả hai issuers thì có nên ALLOW?

**Trả lời:** Không. Chữ ký phải liên kết **đúng issuer đã khai và được phép**. Không chấp nhận token ký B như token của A.

### Tình huống L — Staging key trong production

Một RS production vô tình nhập JWKS staging vào cùng verifier với production. Staging client có khả năng mint tokens trong môi trường test.

**Câu hỏi:** Rủi ro?

**Trả lời:** Trust boundary giữa môi trường bị trộn. Kể cả staging key chưa lộ, production không nên tin tokens staging trái policy.

### Tình huống M — `kid` giống SQL fragment

Custom key lookup nối raw `kid` của JWT vào SQL query để tìm khóa.

**Câu hỏi:** Có nên “lọc dấu nháy” là đủ?

**Trả lời:** Không. Dùng parameterized queries và issuer-scoped key registry; kiểm length/format và không dùng raw unverified values làm SQL/filename/command.

### Tình huống N — JWKS có key `use=enc`

Verifier dùng một JWK từ trust registry nhưng key được đăng cho encryption, không phải signing.

**Câu hỏi:** Có thể verify JWT JWS bằng key này không?

**Trả lời:** Không nếu không đáp ứng purpose/policy; phải kiểm `use`, `key_ops`, algorithm/key type và trusted registration. Một JWK không được dùng sai mục đích chỉ vì key material parse được.

### Tình huống O — Certificate chain hợp lệ nhưng không phải issuer

JWT có `x5c` với cert được ký bởi CA công cộng, nhưng key không được OP đăng ký là signing key.

**Câu hỏi:** Cert chain valid có đủ?

**Trả lời:** Không. PKI validity không tự cấp quyền ký access token cho issuer cụ thể. Cần trusted issuer/key binding.

### Tình huống P — `crit` unknown

Một JWS header có critical parameter tùy chỉnh mà thư viện không hiểu.

**Câu hỏi:** Có nên bỏ qua rồi verify chữ ký?

**Trả lời:** Không. JOSE critical extensions cần được hiểu và xử lý đúng; unknown critical parameter phải bị từ chối theo spec/profile.

### Tình huống Q — Nested JWE decrypt thành công

Resource Server decrypt outer JWE bằng private key của mình, rồi tin `sub`/`scope` trong plaintext mà không verify inner JWS theo profile yêu cầu.

**Câu hỏi:** Điều gì sai?

**Trả lời:** Decryption/authenticated ciphertext không tự chứng minh **issuer đã ký nội dung**. Trong signed-then-encrypted profile, phải verify inner JWS rồi kiểm claims.

### Tình huống R — K1 signing key bị lộ

AS K1_private bị compromise; RS vẫn dùng đúng trusted K1_public.

**Câu hỏi:** Đây có phải key confusion không?

**Trả lời:** Trọng tâm là **key compromise**. Key lookup có thể đúng nhưng signer đã mất độc quyền. Cần emergency distrust K1 và đổi khóa, không chỉ sửa algorithm parser.

### Tình huống S — `kid` bị chặn nhưng same key alias khác

Security block `kid=old`, còn cùng public key K1 xuất hiện với `kid=legacy`.

**Câu hỏi:** Key K1 đã được chặn hoàn toàn chưa?

**Trả lời:** Chưa chắc. Cần block **key material/fingerprint** trên issuer trust set và kiểm mọi aliases/caches.

### Tình huống T — KMS key chưa lộ, JWKS publisher bị chiếm

Private K1 vẫn an toàn trong HSM, nhưng attacker thêm public KX của họ vào JWKS.

**Câu hỏi:** Có thể chấp nhận JWT giả KX không?

**Trả lời:** Nếu RS tin JWKS đã bị chiếm mà không có controls phù hợp, có thể. Đây là key substitution/trust-source compromise, không cần đánh cắp K1_private.

### Tình huống U — OAuth client đăng ký public key thành công

Client C1 được phép tự cập nhật `private_key_jwt` public key trong client registration.

**Câu hỏi:** C1 có quyền thêm khóa đó vào AS JWT signing JWKS không?

**Trả lời:** Không. Client authentication trust và issuer signing trust là hai authority domains. Chỉ issuer/key management workflow được phê duyệt mới có quyền thay JWKS của AS.

### Tình huống V — JWKS timeout, verifier thử `jku`

Trusted AS JWKS endpoint tạm không phản hồi. RS fallback sang `jku` trong token để giảm lỗi 401.

**Câu hỏi:** Có an toàn không?

**Trả lời:** Không. Đây là fail-open/key-source substitution. Có thể dùng trusted cache còn đủ freshness hoặc trả lỗi/fail closed theo policy, không tin nguồn do token chọn.

### Tình huống W — JWT đúng issuer nhưng sai tenant

Một access token đúng issuer, đúng audience, đúng signature, `scope=orders:read`, nhưng user yêu cầu order ở tenant khác.

**Câu hỏi:** Key confusion fixes có chặn hết không?

**Trả lời:** Không. Cần business authorization theo principal, tenant và resource ownership. Authentication đúng không tự cấp mọi quyền.

### Tình huống X — Client cert bị lộ

Client mTLS private key bị copy; AS JWT signing key vẫn an toàn.

**Câu hỏi:** Phải rotate AS signing key không?

**Trả lời:** Không mặc nhiên. Cần xử lý client certificate/private key và những tokens ràng buộc cert, đánh giá client impersonation. Chỉ rotate AS key nếu có bằng chứng hoặc risk assessment cho thấy nó cũng bị ảnh hưởng.

### Tình huống Y — JWT có `alg` đúng nhưng key thuộc issuer khác

API pin RS256 và tìm được public key đúng RSA, nhưng key lấy từ JWKS của issuer B trong khi JWT tự khai issuer A.

**Câu hỏi:** Có phải algorithm pinning đã giải quyết key confusion?

**Trả lời:** Chưa. Thuật toán đúng **không thay issuer-to-key binding**. Phải xác minh bằng issuer A trusted key set, sau đó kiểm expected issuer và audience.

### Tình huống Z — `kid` thiếu ở JWT hợp lệ

Một issuer profile không đặt `kid` khi chỉ có đúng một signing key và verifier có trust set duy nhất.

**Câu hỏi:** Thiếu `kid` luôn là lỗ hổng?

**Trả lời:** Không tự động. JWS không biến `kid` thành bằng chứng bảo mật bắt buộc toàn cục; việc chọn khóa có thể an toàn nếu **nguồn, issuer, algorithm, purpose** bị giới hạn và signature verify đúng. Hệ thống multi-key/rotation nên có policy rõ ràng.

## 24. Playbook ứng cứu khi phát hiện key confusion

Một sự cố key confusion có thể âm thầm tồn tại rất lâu nếu ứng dụng chỉ ghi “signature valid”. Khi phát hiện, cần ưu tiên **ngăn chấp nhận token từ trust source sai** và xác định đã có những API actions nào được cấp phép ngoài dự kiến.

### 24.1. Bước 1 — Xác định trust boundary bị phá

Phân loại:

~~~text
Algorithm/key-type confusion:
    HS256/RS256, none, EC/RSA/OKP mismatch.

Key-source substitution:
    jku, x5u, jwk, x5c, JWKS/metadata publisher.

Issuer/client/tenant confusion:
    key của issuer hoặc client khác được dùng làm token signer.

Token-purpose confusion:
    ID token, DPoP proof, client assertion trở thành access token.

Key compromise:
    actual private/HMAC/Sign capability bị chiếm, cần playbook riêng.
~~~

Một sự cố có thể có **nhiều nhánh cùng lúc**; xác định rõ key material đã lộ hay chỉ verifier tin key sai là bước quan trọng để chọn biện pháp.

### 24.2. Bước 2 — Containment

Biện pháp tùy sự cố:

- Chốt lại allowed JWT signing algorithms per issuer/profile; tắt fallback vô kiểm soát.
- Loại arbitrary `jku`/`x5u` dynamic key fetching khỏi verifier, hoặc giới hạn theo trusted allowlist nếu profile bắt buộc.
- Tách issuer JWKS khỏi client/DPoP key store.
- Chặn mọi token type không dành cho API bằng `typ`/audience/profile checks.
- Kiểm issuer/JWKS metadata và rollback **chỉ** tới nguồn cấu hình đáng tin, không rollback một security deny/tombstone quan trọng.
- Dọn stale JWKS cache/RS trust state, bắt readiness check ở các nodes mới.
- Nếu không đủ tin cậy, fail closed các endpoint nhạy cảm thay vì tiếp tục nhận token có signature source không rõ.

Nếu public JWKS bị thay bởi attacker, phải bảo vệ publisher/CI/CD/DNS/IAM trước khi phân phối trust set mới; nếu attacker vẫn sở hữu control plane, sửa một file JWKS sẽ không bền.

### 24.3. Bước 3 — Xác định phạm vi đã bị ảnh hưởng

Một bảng truy vết nội bộ:

| Nhóm | Cần thu thập |
|---|---|
| **Accepted JWTs** | Issuer claimed/expected, key identity, algorithm, token type, audience, decision |
| **Affected verifiers** | API gateways, RS/RP, batch workers, regions, versions |
| **Trust configuration** | JWKS URI, issuer allowlist, client registration, deployment history |
| **Time window** | Khi bug xuất hiện, thay đổi key/trust gần nhất, khi được phát hiện |
| **Sensitive actions** | Giao dịch, data export, role changes, tenant access, token exchange |
| **Key material exposure** | HMAC/private key đã thực sự lộ hay chỉ public key bị trusted sai |
| **Propagated credentials** | Access/refresh tokens, sessions/grants đã cấp qua đường sai |
| **Containment evidence** | Synthetic negative probes và policy version tại từng RS |

**Không thể tái tạo chắc toàn bộ quá khứ chỉ từ JWT có chữ ký PASS**, vì signature-validity có thể dựa trên một public key sai. Cần đối chiếu issuance logs, security events, resource access logs và business transaction state từ những nguồn độc lập có độ tin cậy phù hợp.

### 24.4. Bước 4 — Đánh giá token/grant đã phát và session còn hoạt động

Nếu attacker đã dùng key confusion để truy cập API, token đó có thể:

- Được dùng để thay đổi account settings hoặc grants.
- Kích hoạt token exchange để lấy downstream tokens.
- Tạo session BFF/RP từ một ID token sai.
- Thực hiện giao dịch/đọc dữ liệu trước khi lỗi được sửa.
- Được cache bởi gateway/introspection/custom service khác.

Do đó cần đánh giá **revoke sessions/grants/tokens** trong phạm vi và các **server-side state changes** có phải rollback/điều tra thêm không. Việc sửa verifier không hoàn tác dữ liệu đã bị đọc hay giao dịch đã thực hiện.

### 24.5. Bước 5 — Phát hành cấu hình bảo mật mới

~~~text
Security policy version v21:
    trustedIssuer = https://login.example.com
    allowedAlg = RS256
    trustedJwksUri = https://login.example.com/.well-known/jwks.json
    expectedAud = https://orders.example.com
    acceptedTokenType = OAuth access token
    clientKeysInIssuerTrust = forbidden
    arbitraryHeaderKeySource = forbidden
    blockedKeyFingerprints = [if applicable]
~~~

Phân phối qua trusted configuration/event control plane, kiểm version monotonic và catch-up. Không để snapshot cũ `v20` từ region khác ghi đè security policy `v21`.

### 24.6. Bước 6 — Xác minh tại từng enforcement point

Một test riêng cho key confusion:

~~~text
Expected issuer key, proper claims:
    ALLOW only if business permission passes.

Client-owned key, same valid-looking claims:
    REJECT.

Other issuer key, same kid:
    REJECT.

JWT header jku with attacker JWKS:
    REJECT without arbitrary fetch.

HS256 with RSA public PEM as alleged secret:
    REJECT.

ID token or DPoP proof in access-token slot:
    REJECT.
~~~

Kiểm ở gateway, mỗi RS instance, multi-region và những paths gọi trực tiếp bypass gateway. Chỉ một 401 do sai audience chưa chứng minh trusted key selection đúng; cần các fixtures phân biệt nguyên nhân.

### 24.7. Bước 7 — Theo dõi và hậu kiểm

- Metric `wrong_alg`, `untrusted_key_source`, `issuer_mismatch`, `wrong_token_type`, `blocked_key`.
- Thời gian mọi RS áp trust policy mới.
- Các token/grants/sessions đã bị revoke sau incident.
- Các resource actions bất thường trong incident window.
- Code review các crypto libraries, custom verifiers và dynamic tenant onboarding.
- Kiểm secrets không bị log, client JWKS không bị trộn vào issuer JWKS.
- Bổ sung regression/chaos tests.

Một cuộc điều tra có thể kết luận **chưa thấy bằng chứng khai thác**, nhưng điều đó không chứng minh không hề có khai thác nếu logs thiếu. Ghi rõ phạm vi quan sát và uncertainty.

## 25. Thiết kế tham chiếu và checklist tổng kết

### 25.1. Mẫu kiến trúc kiểm JWT access token

~~~mermaid
flowchart TD
    A[Bearer access token] --> B[Resource Server policy]
    B --> C[Trusted issuer allowlist]
    C --> D[Trusted issuer JWKS / key registry]
    D --> E[Algorithm and key type constraints]
    E --> F{Signature verified under trusted issuer key?}
    F -- No --> X[Reject]
    F -- Yes --> G[Token type and claims validation]
    G --> H{iss/aud/time/scope correct?}
    H -- No --> X
    H -- Yes --> I[Revocation / session / key trust state if required]
    I --> J{Still valid under security policy?}
    J -- No --> X
    J -- Yes --> K[Resource + action + tenant authorization]
    K --> L{Allowed?}
    L -- No --> X
    L -- Yes --> M[Allow]
~~~

Trong sơ đồ, các bước validation thực tế có thể được thư viện tích hợp khác thứ tự. Điều quan trọng là **không tin claims/headers như authority khi chưa verify** và không cho request tự thay trusted issuer/key source.

### 25.2. Bảng so sánh đúng/sai

| Quyết định | Sai | Đúng |
|---|---|---|
| Chọn thuật toán | Theo `alg` token bất kỳ | Theo allowlist issuer/profile |
| Chọn JWKS | Theo `jku` untrusted | Trusted issuer metadata/config |
| Chọn issuer | Theo claim `iss` tự do | Allowlist/routing hint rồi verify binding |
| Chọn key | Global cache theo `kid` | Scoped issuer/key-set/algorithm/purpose |
| Dùng `jwk` | Tin key tự nhúng là issuer key | DPoP holder key chỉ cho DPoP proof, bind `cnf` |
| Dùng HMAC | Public RSA PEM làm secret | Secret riêng đủ entropy nếu profile dùng HS256 |
| JWE | Decrypt xong tin claims | Validate inner signature/profile khi yêu cầu |
| Multi-tenant | Tenant claim tự cấp quyền | Trusted identity→tenant authorization |
| Key rotation | Tái dùng `kid`, bỏ versioning | Public key rollout + fingerprint/trust state |
| Key compromise | Xóa một `kid` | Distrust actual key material tại mọi verifier |
| Unknown key | Bỏ signature hoặc arbitrary fetch | Reject/fail closed, trusted refresh only |
| Token type | Mọi JWT đều là access token | ID/access/client/DPoP/logout phân biệt |
| API access | Chữ ký đúng là ALLOW | Crypto + claims + current permissions |

### 25.3. Checklist ngắn cho production

1. Pin issuer/JWKS URL và algorithm/key type phù hợp.
2. Không dùng token header/claims chưa verify làm nguồn authority.
3. Không dùng `kid` toàn cục; tách issuer, client, tenant và environment.
4. Không tin `jku`, `x5u`, `jwk`, `x5c` tự khai nếu profile không có trust binding tương ứng.
5. Không dùng public asymmetric key làm HMAC secret.
6. Từ chối unsigned JWT/unknown `crit` trong profile yêu cầu.
7. Tách ID token, access token, client assertion, DPoP proof, logout token.
8. Kiểm expected `aud`, `iss`, `exp`, `nbf`, `typ`/profile, scope.
9. Với DPoP/mTLS, kiểm sender proof/binding **riêng** với AS signature.
10. Với nested JWE, không bỏ inner JWS verification nếu profile yêu cầu.
11. Tách khóa ký/mã hóa/client/public JWKS và quản lý purpose.
12. Có key rotation và emergency distrust bao phủ JWKS caches/regions.
13. Khi unknown key hoặc metadata outage, fail closed theo risk policy.
14. Tiến hành negative tests cho HS/RS, `none`, cross issuer, cross JWT, `jku`, key alias.
15. Vẫn kiểm business authorization trên resource/action/tenant.

### 25.4. Ghi nhớ trong một phút

~~~text
JWT header alg:
    Phải được ràng buộc với server allowlist.

JWT header kid:
    Chỉ là hint chọn key trong trusted issuer key set.

JWT header jku/x5u/jwk:
    Không tự trở thành trust source của AS.

RSA/EC/OKP public key:
    Không phải HMAC secret.

OAuth client private key:
    Không phải issuer signing key.

DPoP holder public key:
    Dùng verify proof, không verify AS access token.

ID token:
    Không thay access token.

Signature valid:
    Có ý nghĩa chỉ khi dùng đúng issuer/key/algorithm/profile.

Authentication valid:
    Chưa thay authorization trên resource/action/tenant.
~~~

**Kết luận:** **Key confusion là lỗi ở ranh giới tin cậy**: verifier để dữ liệu chưa được xác minh quyết định **khóa nào, thuật toán nào hoặc bên nào** có thẩm quyền cấp token. Giải pháp không phải chỉ “kiểm chữ ký”, mà là **chốt trusted issuer, JWKS/key purpose, allowed algorithms, token profile và audience từ server-side policy**; phân tách AS, client, DPoP/mTLS, JWE và môi trường; đồng thời bảo vệ key rotation, cache và failure modes. Với OAuth 2.0/OIDC, sau khi chứng minh chữ ký đúng nguồn, RS vẫn cần kiểm expiry, scope, revocation khi yêu cầu và quyền theo resource/action.

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JOSE protected header, `alg`, `kid`, `jku`, `x5u`, `x5c`, `jwk`, `crit` và signature verification.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK Set, `kty`, `kid`, `use`, `key_ops` và public/private key material.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): `HS256`, `RS256`, `PS256`, `ES256` và thuật toán JOSE.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims, `iss`, `aud`, `exp`, `nbf`, `jti`, token validation.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): content encryption, JWE `alg`/`enc`, nested JWT và key management.
- [RFC 7638 — JSON Web Key Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): public JWK thumbprint giúp nhận diện key material.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, cross-JWT confusion, issuer/audience/key binding, mutually exclusive validation rules.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token type, issuer, audience và resource server profile.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): AS, RS, clients, access/refresh token, grant.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): OAuth security boundaries, token protection, client/AS threats.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): `private_key_jwt`-style JWT client assertions, client key/issuer/audience binding.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): trusted AS metadata và `jwks_uri`.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer identification và mix-up defenses trong authorization response.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): DPoP holder JWK/proof, `cnf.jkt`, replay và token binding.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): client certificate authentication, `cnf` certificate thumbprint và sender-constrained tokens.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange, subject/actor và authorization grant boundaries.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, OP/RP claims và token validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata và JWKS source của OP.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): logout token JWT purpose, `events`, `sid`/`sub`.
- [Spring Security Reference — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `NimbusJwtDecoder`, issuer/JWKS và custom validators.
- [Spring Security Reference — Resource Server Multitenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): multiple issuers và authentication manager resolution.
- [OWASP JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT verification, cryptographic keys, token handling và common pitfalls.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth clients, authorization code, token trust và security.
- [OWASP Server-Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): URL/host controls khi thành phần backend tải tài nguyên từ mạng.
