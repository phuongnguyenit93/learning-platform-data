# Algorithm confusion

Trong một hệ thống dùng JWT để xác thực và phân quyền, thông điệp **“signature valid”** chỉ có ý nghĩa khi Resource Server (RS) đã chọn **đúng thuật toán, đúng loại khóa và đúng nguồn khóa được tin cậy**. Một lỗi đặc biệt nguy hiểm là **algorithm confusion**: chương trình để thông tin do token chưa xác minh cung cấp điều khiển cách xác minh chữ ký, rồi vô tình áp dụng một thuật toán hoặc một loại khóa **khác với chính sách bảo mật dự kiến**.

Ví dụ nổi tiếng là dịch chuyển từ **RSA signature** (`RS256`, dùng private key để ký và public key để kiểm) sang **HMAC** (`HS256`, dùng cùng shared secret để tạo và kiểm MAC). Nếu một verifier dự kiến kiểm RS256 bằng **public RSA key**, nhưng lại cho phép dùng chính public-key bytes ấy làm **HMAC secret** khi header JWT yêu cầu HS256, một attacker biết public key có thể tạo MAC hợp lệ theo cách diễn giải sai ấy. Kết quả: chương trình báo “hợp lệ” mặc dù **Authorization Server (AS) không ký token**.

Đây không phải lỗi của RSA hay HMAC khi dùng đúng quy tắc, mà là lỗi **ghép thuật toán–khóa–trust policy**. Các thư viện hiện đại có cơ chế kiểm kiểu khóa và thuật toán, nhưng tích hợp sai, thư viện cũ, custom decoder hoặc cấu hình “chấp nhận mọi algorithm” vẫn có thể tạo rủi ro.

Bài **“Algorithm confusion”** nằm trong chương **Threats**, thuộc module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**: nắm mô hình tin cậy và vòng đời token bảo mật, JWT so với opaque token, access token so với refresh token, OAuth 2.0/OIDC, các bước phát hành/kiểm claims, scope, audience, storage, revocation và phòng chống token bị đánh cắp/phát lại. Bài tập trung vào **cơ chế hiểu sai thuật toán và trust boundary**, cách phòng thủ, kiểm thử và vận hành, không chỉ học thuộc tên một kiểu tấn công.

> **Nguyên tắc nền tảng:** **JWT header `alg` là dữ liệu đầu vào chưa đáng tin, không phải lệnh cấp quyền đổi chính sách xác minh.** Thuật toán được phép, loại khóa và issuer/key registry phải được xác định bởi **cấu hình tin cậy của verifier và token profile**; token chỉ có thể đề nghị chọn một phương án nằm **trong chính sách đã được phép**.

## 1. Nhắc lại mô hình tin cậy của JWT access token

Một luồng thường gặp:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant JWKS as Trusted issuer JWKS
    participant RS as Orders Resource Server
    C->>AS: Xin access token với grant hợp lệ
    AS->>AS: Đánh giá client, grant, scopes, audience
    AS-->>C: JWT ký bằng private signing key
    C->>RS: Authorization: Bearer JWT
    RS->>JWKS: Lấy public verification keys từ issuer đã tin
    JWKS-->>RS: Allowed issuer public keys
    RS->>RS: Check alg + key type + signature
    RS->>RS: Check iss, aud, exp, token type, scope, revoke
    RS->>RS: Check tenant + object authorization
    RS-->>C: 200 hoặc 401/403 tùy kết quả
~~~

Một JWT access token ví dụ được chia thành ba phần **JWS Compact**:

~~~text
BASE64URL(UTF8(protected_header))
.
BASE64URL(payload)
.
BASE64URL(signature_or_MAC)
~~~

Protected header có thể chứa:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "issuer-signing-2026-11"
}
~~~

Payload minh họa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "scope": "orders.read",
  "iat": 1800000000,
  "exp": 1800000900,
  "jti": "access-token-42"
}
~~~

**Các JSON trên chỉ minh họa**, chưa được ký thành JWT. Người nhận **có thể decode** Base64url để xem `alg`, `kid`, claims trước khi xác minh, nhưng **không được tin các giá trị đó** cho mục đích phân quyền hoặc mở rộng trust.

### 1.1. “Valid JWT” là nhiều phép kiểm

Đối với một JWT access token, cần tối thiểu:

1. **Format/profile:** nhận đúng JWS/JWT type, kích thước và nesting hợp lệ.
2. **Allowed algorithm:** `alg` nằm trong danh sách được cấu hình cho issuer/token type.
3. **Trusted key:** `kid` chọn key **đúng issuer**, đúng `kty`, `use`/`key_ops` và algorithm compatibility.
4. **Cryptographic verification:** JWS signing input và chữ ký/MAC đúng thuật toán với key đã tin.
5. **Token claims:** `iss`, `aud`, `exp`, `nbf`, `iat`, `scope`, `client_id`, token type và profile theo chính sách.
6. **State:** revoke/grant/session version, sender constraint nếu được yêu cầu.
7. **Authorization:** quyền thực sự với operation, tenant và đối tượng tài nguyên.

**Algorithm confusion** phá ở bước 2–4. Sau khi sửa lỗi đó, **không được bỏ các bước còn lại**.

### 1.2. Ai quyết định thuật toán?

**Authorization Server** quyết định thuật toán khi tạo token theo issuer policy. **Resource Server** phải xác định **những thuật toán mà nó đồng ý tin** theo cấu hình kiểm chứng của mình. Hai phía phải có **contract được quản trị độc lập với nội dung token**.

Một JWT ghi `alg=HS256` không thể buộc Orders API sử dụng HS256 nếu contract của AS/Orders API chỉ chấp nhận **RS256**. Tương tự, một JWT ghi `alg=none` không thể yêu cầu RS bỏ kiểm chữ ký.

## 2. Thuật ngữ: algorithm confusion, key confusion và token confusion

| Thuật ngữ | Sai lệch trọng tâm | Ví dụ |
| --- | --- | --- |
| **Algorithm confusion** | Verifier thực hiện thuật toán ngoài policy dự kiến hoặc dùng sai loại key cho thuật toán | Dự kiến RS256 nhưng xử lý HS256 với public RSA key bytes |
| **Key confusion / key substitution** | Chọn khóa không thuộc nguồn tin cậy hoặc sai purpose | Lấy public key từ `jku` của attacker |
| **Issuer confusion** | Dùng key/claims của issuer khác để cấp quyền | JWT issuer B được RS của issuer A chấp nhận |
| **Cross-JWT / token-type confusion** | Dùng một JWT hợp lệ ở sai vai trò | ID token OIDC thay access token OAuth |
| **Format confusion** | Parser tráo JWS/JWE, detached/unencoded payload, nested layers | JWE decrypt được rồi bỏ inner JWS verify |
| **Authorization confusion** | Xem chữ ký hợp lệ là quyền trên mọi tài nguyên | `scope=orders.read` được xem order tenant khác |

Các lỗi có thể **kết hợp**, nhưng không đồng nghĩa. Ví dụ một JWT do issuer B ký bằng thuật toán hợp lệ mà RS A nhận sai là **issuer/key trust confusion**, ngay cả khi không có chuyển từ RSA sang HMAC.

### 2.1. Tên gọi không quyết định cơ chế

Thỉnh thoảng bài viết bảo mật dùng “JWT algorithm confusion” để chỉ riêng **HS256/RS256**. Trong thực tế cần kiểm rộng hơn: thuật toán bị hạ cấp, parser dựa vào header chưa tin, key set quá rộng, JWS vs JWE, multi-issuer và token purpose.

### 2.2. Thuật toán mạnh không cứu trust policy sai

RSA 3072-bit, Ed25519 hoặc AES-GCM vẫn không giúp nếu ứng dụng:

- Xác minh bằng **public key attacker tự đưa**;
- Bỏ signature verification khi `kid` không thấy;
- Dùng một access token dành cho Payments để gọi Orders;
- Nhận một **ID token** như access token;
- Cho phép `alg` bất kỳ trong token điều khiển code path.

Thuộc tính mật mã chỉ hữu ích sau khi **đúng khóa và đúng mục đích** được thiết lập.

## 3. HS256 và RS256 khác nhau về quyền giữ khóa

Hai thuật toán đều có thể bảo mật khi dùng đúng, nhưng trust model rất khác:

| Tiêu chí | **HS256** | **RS256** |
| --- | --- | --- |
| Primitive | HMAC với SHA-256 | RSASSA-PKCS1-v1_5 signature với SHA-256 |
| Loại khóa | Shared symmetric secret | Private signing key + public verification key |
| Ai tạo MAC/signature? | **Bất kỳ ai biết secret** | Bên giữ **private signing key** |
| Ai xác minh? | Bên có **cùng shared secret** | Bên có **public verification key** |
| Có thể công bố verification key không? | **Không**: secret là bí mật | **Có**: public key được thiết kế để công bố |
| Rủi ro khi RS bị compromise | Shared secret có thể cho phép forged MAC | Public verification key tự nó không cho phép giả chữ ký |
| Phù hợp nhiều RS/trust domains? | Cần quản lý secret sharing rất chặt | Thường dễ tách quyền sign/verify hơn |

### 3.1. Cách ký đúng với RS256

~~~text
AS:
  JWS alg=RS256
  private_RSA_key_AS -> Sign(JWS signing input)

RS:
  trusted_public_RSA_key_AS -> Verify(signature)

Kẻ biết public RSA key:
  -> có thể verify
  -> không được cấp khả năng tạo issuer RSA signature
~~~

### 3.2. Cách dùng đúng với HS256

~~~text
AS:
  JWS alg=HS256
  shared_HMAC_secret -> MAC(JWS signing input)

RS:
  cùng shared_HMAC_secret -> Verify MAC

Kẻ biết HMAC secret:
  -> có khả năng tạo MAC mới
~~~

**Không có khái niệm “HS256 public verification key”** tương đương RSA. Nếu một RS chỉ cần đọc và kiểm access token, việc chia private/shared signing capability cho nó là quyết định trust architecture, không phải lựa chọn tốc độ vô hại.

### 3.3. Vì sao public key không phải secret?

Trong OAuth JWT access token dùng RS256, **JWKS của AS thường công khai** để RS lấy public verification key. Một implementation dùng bytes của public RSA key làm **HMAC secret** đã biến thứ công khai thành “secret”, làm hỏng giả định bảo mật của MAC.

## 4. Kịch bản kinh điển: nhầm RS256 thành HS256

Giả sử Orders API được thiết kế chỉ chấp nhận JWT **RS256** của `https://auth.example.com`. RS có sẵn trusted public key của issuer để verify.

Một anti-pattern (pseudocode **không được dùng**) có dạng:

~~~text
function verifyJwt_WRONG(rawJwt, issuerPublicKeyBytes):
    header = decodeBase64url(rawJwt.header)
    algorithm = header.alg  // attacker-controlled trước verify
    return GenericVerify(
        jwt = rawJwt,
        algorithm = algorithm,
        keyBytes = issuerPublicKeyBytes
    )
~~~

Nếu `GenericVerify` cho phép cả RSA lẫn HMAC và **không kiểm key type**, thì khi token chọn `HS256`, thuật toán có thể diễn giải **public RSA bytes làm HMAC shared secret**. Lỗ hổng không đòi attacker phá SHA-256 hoặc factoring RSA; verifier đã chọn **sai công cụ**.

~~~mermaid
flowchart TD
    A["RS dự kiến RS256 từ issuer AS"] --> B["Public RSA verification key từ trusted JWKS"]
    C["JWT header chưa tin alg=HS256"] --> D["Verifier tự tin header để chọn thuật toán"]
    B --> D
    D --> E["Lỗi: diễn giải public RSA key bytes\nnhư HMAC shared secret"]
    E --> F["Có thể nhận MAC không thuộc AS\nnếu implementation dễ bị nhầm"]
    F --> G["Nguy cơ forged JWT / privilege escalation"]
~~~

### 4.1. Những điều kiện cần để lỗi xảy ra

**Không phải thư viện nào cũng mắc lỗi**. Rủi ro điển hình cần một hoặc nhiều điều kiện:

1. Verifier **cho phép cả HS256 lẫn RS256** dù issuer contract chỉ cho RS256.
2. Có một API xác minh **dùng chung key parameter** mà không cưỡng chế `RSA public key` phải đi với `RS256`.
3. Chương trình truyền **public key bytes** vào vị trí HMAC secret.
4. Verifier dựa vào **`alg` do JWT header cung cấp** để chọn branch xử lý thay vì allowlist độc lập.
5. Kết quả “cryptographically valid” được chuyển thành authenticated principal/authority mà không có trust/claims controls đủ mạnh.

Thư viện JOSE hiện đại thường phân loại keys như `RSAKey`, `OctetSequenceKey`, `ECKey` và từ chối mismatch; tuy nhiên **đoạn integration tự viết** vẫn có thể bỏ qua kiểm đó. Không được chỉ dựa vào niềm tin “thư viện mới chắc chắn an toàn” thay kiểm thử thực tế.

### 4.2. Đây không phải “HS256 yếu hơn RS256” theo kiểu đơn giản

HMAC-SHA256 với secret entropy cao và xử lý đúng **không tự yếu**. Vấn đề là RS **không có shared secret bí mật thật**; nó đang dùng **public RSA key** làm bí mật cho một thuật toán khác. Nếu hệ thống thật sự có issuer HS256, phải có **secret manager, namespace và key policy cho HS256** độc lập.

### 4.3. Việc từ chối HS256 phải diễn ra trước khi cấp principal

Đối với Orders API có policy `RS256-only`:

~~~text
JWS header alg=RS256 + trusted RSA key + valid signature
  -> tiếp tục kiểm claims/authorization

JWS header alg=HS256
  -> reject: algorithm not allowed

JWS header alg=none
  -> reject: required signature absent

JWS header alg=PS256 (chưa được đăng ký)
  -> reject: not in this issuer/token profile allowlist
~~~

**PS256 cũng là một thuật toán chữ ký được chuẩn hóa**, không phải thuật toán “xấu”; chỉ là token policy hiện tại chưa cho phép nó. Nếu AS muốn migrate từ RS256 sang PS256, phải **cập nhật contract và key registry có kiểm soát**.

## 5. `alg=none`: lỗi chấp nhận JWT không có chữ ký

JOSE có khái niệm **Unsecured JWS** với `alg=none` trong những ngữ cảnh đặc biệt. Nhưng một **Resource Server yêu cầu JWT access token được AS ký** phải **từ chối** kiểu token không có authentication cryptographic phù hợp.

Header minh họa:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

Nếu parser decode claims rồi tự cho phép `alg=none` hoặc bypass verification khi chữ ký vắng mặt, attacker có thể tự đưa `sub`, `scope` hoặc `role` bất kỳ. Đây thường được xếp vào **signature bypass/downgrade**, không phải RS/HS key confusion, nhưng cùng nguyên nhân gốc: **phó mặc mức bảo vệ cho header chưa tin**.

### 5.1. Không hiểu nhầm phát biểu “none luôn bị cấm ở mọi nơi”

Một số chuẩn/ứng dụng có quy tắc riêng cho unsecured objects dưới **điều kiện bảo vệ khác**. Không nên nói `none` là byte sequence luôn bất hợp pháp trong toàn JOSE. Điều quan trọng ở đây: **OAuth signed JWT access-token profile và chính sách của RS yêu cầu authenticated issuer signature**, do đó `none` bị cấm ở trust boundary đó.

### 5.2. Không có fallback “JWKS lỗi thì decode không kiểm”

~~~text
try:
    claims = verifySignedJwt(rawToken)
catch jwksUnavailable:
    claims = base64urlDecode(rawToken.payload)
    return authenticated(claims)    // SAI, KHÔNG BAO GIỜ LÀM
~~~

Availability problem không trao quyền bỏ authentication. Nếu không thể xác minh theo policy/cached key còn hiệu lực, phải **fail closed**.

## 6. `alg` khác `kid`, `kty`, `use`, `key_ops`

| Field | Nằm ở đâu? | Ý nghĩa | Rủi ro nếu dùng sai |
| --- | --- | --- | --- |
| `alg` | JWS/JWE header, đôi khi JWK metadata | Thuật toán sử dụng/khai báo | Cho token chọn algorithm ngoài allowlist |
| `kid` | JOSE header/JWK | Identifier gợi ý chọn key | Lấy key sai issuer, trùng IDs, key injection |
| `kty` | JWK | Loại key: RSA, EC, OKP, oct… | Dùng RSA public bytes như HMAC secret |
| `use` | JWK (tùy chọn) | Mục đích `sig` hoặc `enc` | Dùng encryption key cho signature |
| `key_ops` | JWK (tùy chọn) | Operations `sign`, `verify`, `encrypt`… | Cho operation sai purpose |
| `typ` | JOSE header | Type của object/token profile | Dùng ID token/proof làm access token |
| `cty` | JOSE header | Type payload bên trong, quan trọng cho nested JWT | Bỏ qua inner signature sau decrypt |

**JWK metadata là dữ liệu chỉ đáng tin sau khi đến từ trusted key registry**; một JWK do chính token attacker nhúng vào header không tự biến thành key được tin.

### 6.1. Một `kid` không xác thực nguồn khóa

Một protected header:

~~~json
{
  "alg": "RS256",
  "kid": "issuer-sign-2026-11"
}
~~~

không chứng minh key thực sự thuộc AS. `kid` được dùng để **lọc key trong tập keys RS đã quyết định tin**. Chữ ký với public key được chọn và issuer claims sau đó mới được xác minh.

### 6.2. `kid` có thể trùng giữa hai issuers

~~~text
Trusted issuer A: kid=signing-1 -> publicKey A
Trusted issuer B: kid=signing-1 -> publicKey B
~~~

Nếu RS có map toàn cục `kid -> publicKey`, token có thể bị verify bằng **khóa của issuer khác**. Registry cần namespace `(issuer, token purpose, kid, key fingerprint)` và **claim `iss` phải khớp issuer đã dùng chọn trusted keys** sau khi verify.

### 6.3. Khi JWK không có `alg`

JWK `alg` là metadata tùy chọn trong nhiều profiles. **Thiếu trường JWK `alg` không đồng nghĩa chấp nhận mọi thuật toán**. RS vẫn phải giới hạn `alg` bằng **issuer-specific allowlist** và kiểm key material compatibility (`kty`, curves, key size, use/key_ops).

### 6.4. Khi key bị rotate

AS có thể prepublish K2, dùng K1 ACTIVE để ký, rồi ngừng ký K1 và chuyển K2 ACTIVE. RS có thể giữ public K1 trong **retired verify-only window**. Đây là **key lifecycle**, không phải lý do nới `alg` sang mọi thuật toán:

~~~text
Allowed: issuer=AS, alg=RS256, kid in {K1, K2}
Not allowed: any issuer, any alg, any kid
~~~

Nếu key compromise, RS phải có đường **emergency distrust** thay vì chờ token cũ tự hết hạn.

## 7. Chuỗi tin cậy tối thiểu: từ issuer đến public verification key

Một verifier nên tách hai khái niệm:

**Trust configuration** — từ ngoài token:

~~~yaml
trusted_issuer: https://auth.example.com
jwks_uri: https://auth.example.com/oauth2/jwks
token_profile: oauth2-access-token
expected_audience: https://api.example.com/orders
accepted_jws_algorithms:
  - RS256
accepted_key_types:
  - RSA
require_signature: true
~~~

**Untrusted token input** — do caller gửi:

~~~text
JWT.header.alg
JWT.header.kid
JWT.header.typ
JWT.payload.iss
JWT.payload.aud
JWT.payload.scope
~~~

Token có thể cung cấp **hints** để chọn một policy đã đăng ký, nhưng **không được thêm issuer/JWKS URL/algorithm vào trust registry**. Cuối cùng, RS verify chữ ký dưới policy đó rồi kiểm claims.

### 7.1. Không dùng `iss` chưa verify để mở trust vô hạn

Đối với multi-issuer RS, có thể **parse `iss` chưa verify làm routing hint** để tra **allowlist issuer đã cấu hình trước**, rồi verify bằng đúng key set issuer ấy và đối chiếu lại `iss` sau. Không được lấy `iss=https://attacker.example` rồi gọi issuer metadata URL tùy ý để tự thêm một identity provider mới.

### 7.2. JWKS URI là cấu hình trust, không phải lời hứa từ JWT

Public JWKS thường tải qua HTTPS và metadata issuer đã biết (RFC 8414/OIDC discovery). Cần kiểm certificate/hostname, đúng domain/issuer, cache/rotation policy. Một response JWKS có public RSA key **không** đồng nghĩa RSA key được dùng làm HMAC secret.

### 7.3. Token validity và key validity là hai tầng

Public K1 còn được tin trong overlap không làm JWT có `exp` đã qua trở lại hợp lệ. Ngược lại, token còn `exp` nhưng K1 đã bị compromised/distrust phải từ chối. **Key trust, token claims và revocation state** đều là các điều kiện độc lập.

## 8. Key-source confusion: `jku`, `x5u` và `jwk` trong JOSE header

Một lớp lỗi có liên quan mật thiết là **key-source confusion**. Token có thể mang các header parameters liên quan tới khóa hoặc certificate; nếu verifier tin những chỉ dẫn ấy vô điều kiện, attacker có thể kiểm soát **nguồn public key**, khiến signature do attacker tạo cũng được chấp nhận.

Ví dụ header do caller có thể tự tạo:

~~~json
{
  "alg": "RS256",
  "kid": "some-key",
  "jku": "https://attacker.example/keys.json"
}
~~~

**Nếu** RS tự lấy `jku` làm URL JWKS tin cậy, nó đã đưa quyết định trust cho token chưa verify. Chữ ký có thể đúng với **key do attacker sở hữu**, nhưng không phải chữ ký của AS được tin.

### 8.1. `jku` không thể tùy ý mở rộng key trust

`jku` theo JOSE là URL trỏ tới một JWK Set. Nó **không tạo quyền** cho ứng dụng đi tải bất kỳ URL nào từ untrusted token. Cách xử lý:

1. Chỉ dùng **issuer-specific, allowlisted JWKS sources** do administrator/metadata đã tin đăng ký.
2. Nếu profile có sử dụng `jku`, phải có cơ chế so khớp URL với registry/trust policy và kiểm TLS, không theo redirect đến host không được phép.
3. Không dùng token để tự thêm key nguồn mới.
4. Giới hạn refresh frequency/rate và network behavior.

### 8.2. `x5u` và certificate chain

`x5u` trỏ tới nguồn certificate. Việc tải certificate ở URL do attacker đưa ra hoặc xem **certificate bất kỳ** là issuer signing authority đều sai. Nếu ứng dụng sử dụng chứng chỉ để verify:

- Chứng chỉ/key phải thuộc issuer registry hoặc chuỗi trust được định nghĩa rõ.
- Phải kiểm đúng key usage, certificate path/hostname hay pinning theo profile.
- Không nhầm “certificate có chữ ký CA hợp lệ” với “key này được AS ủy quyền ký OAuth access token”.

TLS certificate của website nào đó **không tự trở thành signing key của Authorization Server**.

### 8.3. `jwk` nhúng trong header

Một số JOSE contexts có thể chứa public JWK ngay trong header. Đó vẫn là **dữ liệu do bên gửi cung cấp**. Với AS-signed access token, không được verify bằng public key từ token rồi coi đó là AS issuer key, trừ khi có **trust-binding profile độc lập** cho phép và đã kiểm.

**Đối chiếu quan trọng:** DPoP proof JWT theo RFC 9449 cố ý mang public JWK trong header vì proof cần chứng minh sở hữu private DPoP key; **nhưng proof JWK không phải issuer signing key của access token**. Dùng “DPoP cho phép embedded JWK” để tin embedded JWK trong mọi JWT access token là một lỗi phân biệt profile.

### 8.4. SSRF và đổi khóa qua DNS/redirect

Nếu verifier tự tải URL do header cung cấp, attacker có thể lợi dụng tính năng đó như một **SSRF entry point**. Phòng thủ không chỉ là kiểm chuỗi URL bắt đầu bằng `https://`; cần allowlist nguồn, chặn URL nội bộ/redirect không hợp lệ, xác thực host đích và hạn chế kết nối mạng của token-validation service.

### 8.5. `kid` có thể được dùng sai làm đường dẫn hoặc câu truy vấn

Một anti-pattern:

~~~text
keyFile = "/keys/" + token.header.kid + ".pem"
loadFile(keyFile)
~~~

Khi `kid` chưa được kiểm và được nối thành filesystem path, SQL query hoặc HTTP URL, có thể sinh **path traversal, injection, SSRF hoặc key substitution**. Không dùng `kid` làm command/path tùy ý; tra trong **key registry có các identifiers đã biết**, với giới hạn chiều dài và định dạng.

### 8.6. Bảng phân biệt ba nguồn key

| Nguồn | Có tự được tin để verify AS access token? | Cách xử lý |
| --- | --- | --- |
| Trusted AS JWKS đã cấu hình | **Có điều kiện** | TLS/issuer/purpose/alg/key checks |
| Public JWK nhúng trong arbitrary JWT header | **Không** | Chỉ được sử dụng trong profile khác đã được thiết kế, ví dụ DPoP proof |
| `jku` URL tự khai trong JWT | **Không** | Không tải tùy ý; chỉ chấp nhận nếu ràng buộc registry tin cậy |
| Public key từ issuer khác | **Không** cho issuer hiện tại | Namespace issuer/key và kiểm `iss` |
| RS private decryption key | **Không** phải AS signing key | Dùng đúng JWE purpose, không trộn với JWS verify |

## 9. JWS và JWE: chữ `alg` không cùng một nghĩa

JOSE dùng **`alg`** cả trong JWS lẫn JWE, nhưng:

- Với **JWS**, `alg` chọn thuật toán **signature/MAC**.
- Với **JWE**, `alg` chọn **key management/agreement/wrapping** cho content-encryption key (CEK).
- Với **JWE**, `enc` chọn **content encryption** như AES-GCM.

Ví dụ **JWS protected header**:

~~~json
{
  "alg": "PS256",
  "typ": "at+jwt",
  "kid": "as-sign-2026-11"
}
~~~

Ví dụ **JWE protected header**:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT",
  "kid": "orders-decrypt-2026-11"
}
~~~

**`RSA-OAEP-256` là key-management/encryption algorithm, không phải RSA signature algorithm.** `A256GCM` không thể thay `PS256` để verify issuer signature.

### 9.1. Một access token được mã hóa không tự chứng minh issuer

Nếu token là **JWE dùng public encryption key của RS**, người bất kỳ biết public key có thể tạo ciphertext hợp lệ gửi RS. RS giải mã được **không đồng nghĩa** AS đã phát token. Cần **issuer-authenticated layer**:

~~~text
Thông thường:
    outer JWE( inner JWS( claims ) )

RS:
    decrypt outer JWE + verify AEAD tag
    verify inner JWS bằng AS trusted signing key
    validate token claims & authorization
~~~

Nếu chỉ decrypt rồi đọc `role=admin`, đó là **issuer-authentication bypass**. Algorithm confusion có thể xảy ra khi parser nhìn `alg=RSA-OAEP-256` và nhầm là đủ xác nhận nguồn.

### 9.2. Nested JWT: `typ` và `cty`

Một nested JWT có thể có:

- **Outer JWE:** `alg`/ `enc` và `cty=JWT`.
- **Inner JWS:** `alg` chữ ký, `typ=at+jwt` nếu là JWT access token theo RFC 9068.

Không được coi header `cty=JWT` là bằng chứng rằng inner object thật sự hợp lệ. Sau decrypt phải parse đúng **inner JWS**, kiểm signature và token profile.

### 9.3. Nguy cơ multi-layer fallback

Một code path nguy hiểm:

~~~text
try verify JWS
else try decrypt JWE
else decode base64url payload
else accept JSON claims
~~~

Không thử nhiều interpretation cho tới khi một cách “có dữ liệu” rồi cho vào security principal. Mỗi API cần một **allowed token format/nesting profile**: signed JWS, nested JWE(JWS), opaque reference token, hoặc một application-specific profile đã phê duyệt.

### 9.4. JWE `alg=dir` không phải `alg=none`

Trong JWE, `dir` nghĩa là dùng **shared content-encryption key trực tiếp**; encrypted-key segment có thể rỗng trong Compact Serialization, nhưng payload **vẫn được mã hóa và xác thực** theo `enc`. Không lấy quy tắc JWS `alg=none` để suy mọi trường hợp “đoạn rỗng” đều là unsecured JWT.

### 9.5. Encryption/decryption key phải khác issuer signature key theo purpose

AS private signing key chỉ nên dùng **sign**. RS private decryption key dùng **decrypt/unwrap**. Public key dành cho JWE recipient encryption **không tự là public issuer verification key**, ngay cả khi đều có `kty=RSA`.

## 10. Cross-JWT confusion: thuật toán đúng nhưng dùng sai loại token

Một số token đều có thể là JWS/JWT:

| Object | Ai ký? | Đối tượng dùng đúng | Kiểm tra riêng |
| --- | --- | --- | --- |
| **OAuth JWT access token** | AS | Resource Server/API | `typ=at+jwt` theo RFC 9068, `iss`, `aud`, `scope`, `exp` |
| **OIDC ID token** | OpenID Provider | **OIDC client** | `iss`, client `aud`, `nonce` theo flow, `exp`, OIDC rules |
| **JWT client assertion** | OAuth client | AS token endpoint | client identity, `aud` token endpoint, `exp`, replay controls |
| **DPoP proof JWT** | Client holding DPoP key | AS/RS verifying sender proof | `typ=dpop+jwt`, `jwk`, `htm`, `htu`, `iat`, `jti`, `ath` |
| **JWT request object/JAR** | Client theo profile | AS authorization endpoint | request-object issuer/aud/alg/policy |
| **Refresh token** | AS (opaque/JWT tùy AS) | AS token endpoint | rotation/reuse detection/client/grant binding |

Một RS chỉ kiểm “chữ ký đúng với một key đã biết” nhưng không kiểm **token type và audience** có thể nhận nhầm:

~~~text
ID token có aud=reports-web
    --Gửi làm Authorization: Bearer-->
Orders API kỳ vọng aud=orders-api

Nếu Orders chỉ verify signature rồi accept:
    -> token substitution / authorization bug
~~~

Đây có thể được gọi là **cross-JWT confusion**, có liên hệ với algorithm/key trust nhưng **không nhất thiết có chuyển thuật toán**. Cần **explicit typing** và **mutually exclusive validation rules** theo RFC 8725.

### 10.1. ID token không có nhiệm vụ thay access token

ID token OIDC chứng minh kết quả authentication cho **client**. Access token có quyền truy cập **resource server** trong giới hạn audience/scope. Dù cả hai được ký bằng cùng issuer key, **Orders API không thể lấy ID token làm access token**.

### 10.2. DPoP embedded JWK không mở quyền cho issuer verification

DPoP proof được ký bởi **client key** hiển thị public JWK trong header, còn DPoP-bound access token được **AS cấp và xác minh độc lập**. RS phải:

1. Verify access token theo trusted AS keys (hoặc introspection).
2. Verify DPoP proof bằng public JWK trong proof theo RFC 9449.
3. Đối chiếu proof key thumbprint với access-token `cnf.jkt`.
4. Kiểm `htm`, `htu`, `iat`, `jti`, `ath`, server nonce nếu yêu cầu.
5. Kiểm scope/audience/ownership.

Một client có thể tự tạo DPoP proof ký hợp lệ, nhưng **không được quyền tự phát JWT access token** bằng public JWK ấy.

### 10.3. JWT client assertion sử dụng key của OAuth client

Trong `private_key_jwt` (OAuth client authentication), AS verify JWT assertion bằng **public key đã đăng ký của client**, không bằng issuer signing key cấp access token. Nếu hệ thống gộp hai key domains, attacker có thể lợi dụng sai trust boundary.

### 10.4. Refresh token có trạng thái sử dụng khác access token

Một rotated refresh token cũ bị dùng lại cần AS phát hiện qua **rotation family/state**, bất kể token được ký bằng HS256, RS256 hay là opaque reference. Algorithm verification đúng **không tạo ra** single-use semantics. Không cho RS nhận refresh token như Bearer access token.

## 11. Multi-issuer và multi-tenant: trust confusion ngoài `alg`

Một RS có thể hỗ trợ hai issuers:

~~~text
Issuer A:
  iss=https://auth-a.example.com
  accepted_alg=RS256
  jwks_uri=https://auth-a.example.com/jwks

Issuer B:
  iss=https://auth-b.example.com
  accepted_alg=ES256
  jwks_uri=https://auth-b.example.com/jwks
~~~

Lỗi:

~~~text
GLOBAL_ACCEPTED_ALGS = {RS256, ES256, HS256}
GLOBAL_JWKS = keysA + keysB
lookupKeyByKidWithoutIssuer()
~~~

Không phải việc hỗ trợ RS256 và ES256 đồng thời luôn sai, mà **mỗi token phải bị ràng buộc vào đúng một issuer/profile trước khi tin key, và thuật toán phải nằm trong policy của issuer ấy**.

### 11.1. Multi-issuer routing bằng untrusted claim

Ứng dụng có thể parse unverified `iss` để **gợi ý chọn allowlisted authentication manager**. Nhưng nếu `iss` không thuộc allowlist, phải **từ chối**, không phát sinh network discovery tới host bất kỳ. Sau signature verification, đối chiếu `iss` với issuer đã dùng chọn key.

### 11.2. Không tin tenant claim thay dữ liệu phân quyền

Ngay cả token ký đúng issuer B, `tenant_id=blue` không cho phép xem bản ghi của tenant red. RS phải kiểm **membership/entitlement và object-level ownership** từ nguồn đáng tin. Algorithm confusion và broken object authorization có thể độc lập hoặc kết hợp.

### 11.3. Một `kid` nằm trong nhiều JWKS không đồng nghĩa key giống nhau

`kid` có phạm vi do nhà phát hành quyết định, không là định danh toàn cầu. Key lookup nên gắn issuer + purpose + key fingerprint và kiểm `kty/alg` phù hợp; tránh mutable global registry bị token header điều khiển.

### 11.4. Token exchange và downstream services

Khi gateway/BFF đổi access token dành cho resource A thành token dành cho resource B, phải dùng **token exchange/ủy quyền có kiểm soát** theo profile và bảo vệ delegation chain. Không sửa `aud` hoặc ký lại với key không thuộc AS để “tái sử dụng” token; thay `aud` trong JWS làm signature hỏng, còn key confusion có thể khiến một verifier sai chấp nhận bản sửa ấy.

## 12. Kiểm `alg` đúng nghĩa là kiểm *policy*, không chỉ string

Một policy khỏe phải trả lời:

1. **Token này là loại nào?** JWS access token, JWE nested, DPoP proof, ID token, assertion hay opaque?
2. **Issuer/signer thuộc trust domain nào?** Ai có quyền phát hành object đó?
3. **Algorithms nào được phép trong domain?** `RS256`, `PS256`, `ES256`, `EdDSA` hoặc HMAC theo thỏa thuận đã phê duyệt.
4. **Key nào được phép với alg đó?** RSA vs EC vs octet symmetric, key strength, `use` và `key_ops` phù hợp.
5. **Nơi chọn key?** Trusted issuer JWKS, client registration, DPoP proof key theo RFC, recipient encryption registry…
6. **Làm gì nếu mismatch?** **Reject**, không fallback sang một algorithm/key khác.

### 12.1. Đừng mặc định “chỉ RS256” là luật của toàn bộ JWT

RS256 không phải lựa chọn duy nhất an toàn. `PS256`, `ES256` hoặc `EdDSA` có thể được cho phép trong profile phù hợp và được thư viện hỗ trợ. Vấn đề là **có hợp đồng và kiểm đúng key/algorithm**, không phải một danh sách thuật toán “tốt” dùng đại trà.

### 12.2. Chuẩn hóa tên thuật toán

JOSE dùng identifiers chuẩn, case-sensitive như `RS256`, `PS256`, `ES256`, `HS256`. Không tự map các tên không rõ như `rsa`, `sha256`, `RSA-OAEP` để chọn signature mode. `SHA-256` là hash function; **chỉ biết hash name không nói được là HMAC, RSA-PSS hay RSASSA-PKCS1-v1_5**.

### 12.3. Kiểm key type và purpose

Ví dụ policy:

| `alg` JWS | Key phù hợp | Bị từ chối nếu… |
| --- | --- | --- |
| `HS256` | Shared symmetric key với entropy/custody đúng | RSA public key bytes hoặc secret không đăng ký cho issuer |
| `RS256` | RSA public verification key của issuer | Octet symmetric key, wrong issuer, key size không đạt |
| `PS256` | RSA public verification key với PSS policy | Chỉ cho RS256 nhưng token yêu cầu PS256 |
| `ES256` | EC public key trên curve phù hợp | RSA/OKP key hoặc curve sai |
| `EdDSA` | Key type/curve phù hợp JOSE profile được hỗ trợ | EC P-256/RSA key hoặc library không hỗ trợ |
| `none` | Không có cryptographic signature | Signed access-token profile yêu cầu issuer signature |

Một RSA key có thể toán học hỗ trợ nhiều signature schemes, nhưng **policy** vẫn cần chỉ rõ những `alg` đã được phép cho key/issuer/token type; không suy “RSA key nên nhận RS256 lẫn PS256 tự động”.

### 12.4. Kiểm `crit` và các profile có payload khác thường

JOSE hỗ trợ critical headers; nếu `crit` chứa extension mà verifier không hiểu và được yêu cầu xử lý, **phải từ chối** theo RFC. Một số JWS profiles dùng unencoded payload (`b64=false` theo RFC 7797) hoặc detached payload; parser thông thường không được tự chấp nhận trong OAuth JWT access-token profile nếu không có contract. Sai cách hiểu signing input có thể gây **verification confusion**.

### 12.5. Không “thử cho đến khi có key đúng”

~~~text
for every key in all issuers:
    for every algorithm supported by crypto library:
        if verify(token, key, algorithm):
            accept()
~~~

Đây là anti-pattern. Verifier phải chọn **issuer/profile/algorithm policy trước**, chỉ kiểm các khóa được phép theo policy đó; không biến crypto provider capability thành trust policy.

## 13. Threat modeling: điều kiện tấn công, hậu quả và lớp phòng thủ

| Điểm yếu | Điều attacker kiểm soát | Điều kiện làm tăng nguy cơ | Hậu quả | Phòng thủ |
| --- | --- | --- | --- | --- |
| RS/HS confusion | JWT `alg` và token bytes | Verifier dùng RSA public bytes làm HMAC key | Có thể forged issuer token | Algorithm allowlist + typed keys |
| `alg=none` bypass | Header/payload | Ứng dụng không yêu cầu signature | Arbitrary claims | Bắt buộc signed profile |
| `jku`/ `x5u` key injection | URL header | Verifier tự tải key không allowlist | Forged trust, SSRF | Trusted key registry/URL policy |
| Embedded `jwk` confusion | JWK header | RS tin key tùy ý của caller | Attacker-signed JWT được chấp nhận | Phân biệt token/profile/key binding |
| `kid` injection | Identifier header | Ghép key ID thành path/query | File access/injection/key substitution | Key registry lookup, validation |
| Multi-issuer mix-up | `iss`, `kid` | Global key pool, thiếu issuer binding | Cross-tenant/issuer access | Per-issuer key/alg validation |
| Nested JWT skip layer | Outer JWE hoặc JWS | Decrypt mà không verify issuer, hoặc ngược lại | Token forgery/bypass | Verify tất cả layers |
| JWT type confusion | Loại object/claims | Chỉ check signature | ID token/DPoP assertion thay AT | `typ`, `aud`, mutually exclusive rules |
| Key rotation stale | Header `kid`, replay | JWKS cache/rollback, improper trust window | JWT giả tiếp tục được chấp nhận sau compromise | Emergency distrust, cache policy |
| Fail-open fallback | Invalid/unknown key | Availability logic bypass crypto | Unverified token accepted | Fail closed, bounded refresh |

### 13.1. Algorithm confusion không nhất thiết dẫn tới exploit

Việc một JWT header dùng `HS256` trong hệ thống chỉ chấp nhận `RS256` là **thử sai thuật toán**. Để thành công, implementation phải mắc lỗi diễn giải secret/key/trust và có đường chuyển thành authentication success. **Một token bị từ chối trước signature verification không phải lỗ hổng**; đó là kết quả phòng thủ mong muốn.

### 13.2. Cần quan sát quyết định bảo mật, không chỉ exception

Một test nên xác minh:

- Không có `Authentication`/principal/authority được tạo sau mismatch.
- Không có truy vấn dữ liệu/side effect.
- Mọi đường fallback đều từ chối.
- Error response không lộ secret, JWKS internals hay raw token.
- Metrics phân loại nhóm lỗi mà không ghi `kid` attacker tự tạo làm label.

### 13.3. Phân biệt có key đúng và có quyền đúng

Ngay cả chữ ký của AS đúng `RS256`, token có thể dành cho resource khác, bị revoke, hết hạn hoặc thiếu scope. **Algorithm hardening là một lớp cần thiết, không phải biện pháp phân quyền cuối cùng**.

## 14. Java 17: policy gate chống chọn thuật toán tùy ý

Một mẫu đơn giản để minh họa **trusted configuration không lấy từ token** là kiểm policy trước khi giao JWS cho một thư viện JOSE. Ví dụ dưới đây là **policy gate**, **không tự là JWT verifier**:

~~~java
import java.util.Map;
import java.util.Objects;

public final class TrustedJwtAlgorithmPolicy {
    // Ví dụ: bản ghi trusted key metadata đến từ issuer registry,
    // KHÔNG lấy key material / issuer trực tiếp từ token.
    public record KeyRecord(
            String trustedIssuer,
            String kid,
            String allowedAlgorithm,
            String keyType,
            boolean allowedForVerification) {}

    private final String issuer;
    private final Map<String, KeyRecord> trustedKeysByKid;

    public TrustedJwtAlgorithmPolicy(
            String issuer,
            Map<String, KeyRecord> trustedKeysByKid) {
        this.issuer = Objects.requireNonNull(issuer);
        this.trustedKeysByKid = Map.copyOf(trustedKeysByKid);
    }

    /**
     * Trả metadata trusted key nếu header match policy.
     * Hàm này KHÔNG parse JWT hoặc xác minh chữ ký.
     */
    public KeyRecord requireAllowedJwsHeader(
            String tokenAlg,
            String tokenKid) {
        if (!"RS256".equals(tokenAlg)) {
            throw new SecurityException("JWS algorithm not allowed");
        }
        if (tokenKid == null || tokenKid.length() > 128
                || tokenKid.isBlank()) {
            throw new SecurityException("Invalid key identifier");
        }

        KeyRecord key = trustedKeysByKid.get(tokenKid);
        if (key == null
                || !issuer.equals(key.trustedIssuer())
                || !tokenKid.equals(key.kid())
                || !tokenAlg.equals(key.allowedAlgorithm())
                || !"RSA".equals(key.keyType())
                || !key.allowedForVerification()) {
            throw new SecurityException("Untrusted key/algorithm");
        }
        return key;
    }
}
~~~

### 14.1. Điều đúng ở ví dụ

- Policy **RS256-only** thuộc trusted issuer configuration, không lấy từ JWT header.
- Key lookup theo **known `kid`** trong registry issuer; `kid` chưa tin chỉ là index/hint.
- Metadata từ trusted key record phải khớp **issuer, alg, key type và verify permission**.
- Không có fallback thành HMAC nếu token ghi `HS256`.
- `Map.copyOf` là một snapshot cấu hình trong process; không phải cơ chế rotation/distributed trust hoàn chỉnh.

### 14.2. Điều ví dụ **chưa làm**

Nó **không kiểm cryptographic JWS signature**, không parse protected header bằng JOSE, không kiểm `crit`, `b64` hay nested structure, không kiểm JWT `iss`, `aud`, `exp`, `scope`. Một hệ thống thật phải dùng **library JOSE/JWT được duy trì** và xây pipeline **policy → signature verification → claims/authorization**.

**Không bao giờ coi một kết quả `KeyRecord` trả về là `Authentication` đã được chứng thực.** Nó chỉ xác nhận metadata có thể dùng cho bước kiểm chữ ký.

### 14.3. Không tự viết JWS signing input

JWS signature được tạo/kiểm trên signing input theo RFC 7515. Nếu ứng dụng tự decode/re-encode JSON header hoặc payload theo cách riêng trước khi verify, có thể làm sai byte sequence và bỏ sót special profiles. Để cryptographic verify đúng, sử dụng thư viện JOSE thay vì tự nối bytes, HMAC hay RSA primitives.

## 15. Spring Boot 3 / Spring Security 6: khóa RS256 và kiểm audience

Một Spring Security **OAuth2 Resource Server** có thể dùng trusted issuer/JWK Set URI và **cấu hình thuật toán xác minh được chấp nhận**. Ví dụ cho Orders API có một issuer, access token ký **RS256**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
~~~

Điểm quan trọng: khai báo issuer giúp verifier biết **trust domain**, nhưng trong triển khai thực tế vẫn cần explicit algorithm/audience/type policy và integration test.

### 15.1. Ví dụ decoder với allowlisted signing algorithm

~~~java
import java.util.List;
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

final class OrdersAudienceValidator
        implements OAuth2TokenValidator<Jwt> {
    private static final String EXPECTED_AUD =
        "https://api.example.com/orders";

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        List<String> audiences = jwt.getAudience();
        if (audiences != null
                && audiences.contains(EXPECTED_AUD)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token", "Wrong audience", null));
    }
}

@Configuration
public class OrdersJwtDecoderConfig {
    private static final String TRUSTED_ISSUER =
        "https://auth.example.com";
    private static final String TRUSTED_JWKS_URI =
        "https://auth.example.com/oauth2/jwks";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(TRUSTED_JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER),
                new OrdersAudienceValidator()
            )
        );
        return decoder;
    }
}
~~~

**Ý nghĩa bảo mật:**

- JWT `alg=HS256` **không được phép** chỉ vì caller đổi header; decoder được xây với trusted RS256 policy.
- Key được lấy từ **JWKS URI do ứng dụng cấu hình**, không phải URL do JWT header tự đưa.
- Issuer và audience được kiểm trong JWT validators.
- Token còn phải đạt **expiry/nbf** qua default validators, cùng scope/type/tenant/authorization theo ứng dụng.

**Lưu ý kỹ thuật:** Đoạn này minh họa một cấu hình, không thay việc **compile/test với phiên bản Spring Security cụ thể**. Các phiên bản framework có cách mặc định xử lý `typ` khác nhau; nếu dùng JWT access token theo RFC 9068 với `typ=at+jwt`, cần thiết lập **type validation phù hợp phiên bản thư viện** (có thể cần cấu hình type verifier/validator riêng) và chạy integration test. Không tự xóa `typ` hoặc bỏ xác minh chỉ để token parse được.

### 15.2. Phân quyền route sau authentication

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurityConfig {
    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Spring Security thường map `scope`/`scp` sang authorities `SCOPE_...` theo conventions, nhưng cần kiểm AS token format và configuration thực tế. Một principal có `SCOPE_orders.read` **vẫn không tự được xem mọi orders**, vì resource owner/tenant authorization phải được kiểm ở service/data layer.

### 15.3. Giới hạn của ví dụ

Ví dụ chưa xây dựng:

- RFC 9068 `typ=at+jwt` validation cụ thể cho phiên bản Spring.
- `client_id`, `azp`, tenant, role/policy mapping và per-object ownership.
- Max JWT lifetime (`exp - iat`) và custom clock skew policy.
- Revocation, denylist, introspection hoặc sender binding DPoP/mTLS.
- Nhiều issuers/regions, JWKS refresh/rotation và trust-policy propagation.
- Custom JWE decryption; một signed-JWT decoder thông thường **không tự là nested JWE/JWS processor**.

Những điểm này là **phần phải bổ sung theo profile**, không phải lý do nới algorithm allowlist.

## 16. Java 17: validation pipeline với bước tin cậy rõ ràng

Một cách tổ chức dễ kiểm toán là tách **trusted issuer policy** khỏi **JWT caller data**:

~~~text
REQUEST /api/orders
  |
  v
MAX_SIZE / FORMAT / EXPECTED TOKEN PROFILE
  |
  v
LOAD trusted issuer policy from application config
  |  - allowed JWS algorithms
  |  - issuer JWKS
  |  - expected audience
  |  - token type
  v
PARSE UNTRUSTED JOSE HEADER (hints only)
  |
  v
REJECT alg outside policy, key type mismatch, unknown issuer/kid
  |
  v
CRYPTOGRAPHIC JWS SIGNATURE VERIFICATION
  |
  v
VALIDATE TRUSTED CLAIMS: iss, aud, exp, nbf, iat, scope
  |
  v
CHECK REVOKE / DPoP / mTLS / CLIENT BINDING IF REQUIRED
  |
  v
BUSINESS AUTHORIZATION: tenant, order ownership, action
  |
  v
ALLOW / DENY
~~~

### 16.1. Điều không nên làm

~~~java
// Anti-pattern minh họa; không có trong API cụ thể:
String algorithm = untrustedHeader.get("alg");
Object key = algorithm.startsWith("HS")
    ? issuerPublicKeyBytes
    : issuerPublicKey;

boolean authenticated = genericVerify(rawJwt, key, algorithm);
~~~

Sai ở cả hai chỗ: algorithm theo header **không được giới hạn bởi trust policy** và **public RSA key bytes bị chuyển thành HMAC secret**.

### 16.2. Dùng key objects có kiểu và giới hạn purpose

Trong thư viện JOSE, dùng `RSAKey`/public RSA verification key cho RSA-signature validators, `OctetSequenceKey`/secret manager key cho HMAC validators, EC/OKP keys theo profile. Không chuyển một key object sang byte array rồi thử mọi thuật toán chỉ vì compiler cho phép.

### 16.3. Security principal chỉ được tạo sau toàn bộ authentication checks

Đừng gắn `Authentication` hoặc ghi session từ **claims chưa verify** để sau đó “nâng cấp” khi signature đúng. Trước bước verify, `scope`, `sub`, `role`, `tenant_id` là input không đáng tin và có thể điều khiển nhầm caching/routing/audit.

### 16.4. Chặn cross-algorithm fallback trong code review

Những tên method hoặc pattern đáng kiểm tra:

~~~text
decodeJwtWithoutVerify
parseClaimsFirst
allowUnsignedJwt
verifyWithAnyKey
tryAllAlgorithms
onJwtExceptionReturnAnonymousWithRoles
loadJwksFromTokenUrl
trustEmbeddedJwk
~~~

Các tên trên là **dấu hiệu review**, không phải danh sách API chuẩn hoặc bằng chứng chắc chắn có bug. Phải xem hành vi và trust model cụ thể.

## 17. Migration thuật toán: RS256 sang PS256 hoặc ES256

Một migration có kế hoạch có thể tạm thời hỗ trợ **nhiều thuật toán**, nhưng không nên chuyển thành “accept all”:

~~~text
Trước migration:
  issuer AS, key K1, allowed alg RS256

Prepublish:
  issuer AS, key K2, allowed alg PS256
  K1 vẫn phát token RS256

Cutover:
  AS bắt đầu ký token mới bằng K2/PS256
  K1 retired: chỉ verify JWT RS256 cũ trong window

Sau old-token horizon:
  RS ngừng tin K1/RS256 theo policy
  K2/PS256 là profile signing mới
~~~

### 17.1. Không dùng cùng một key với mọi alg chỉ vì crypto provider hỗ trợ

Ngay cả khi RSA public key có thể dùng verify cả RS256 và PS256 về mặt primitive, **RFC 8725 khuyến nghị mỗi key được sử dụng với đúng một algorithm** theo token-verification contract. Khi migrate, nên dùng **key version riêng** và policy `(issuer, kid, alg)` rõ, không cho JWT tự chọn.

### 17.2. Algorithm allowlist tạm thời phải có deadline

Một policy migration minh họa:

| Giai đoạn | `kid` được nhận | `alg` tương ứng | Hành vi |
| --- | --- | --- | --- |
| Trước cutover | K1 | RS256 | Chỉ token RS256 hợp lệ |
| Overlap | K1, K2 | K1→RS256; K2→PS256 | Verify cả token cũ và mới |
| Sau sunset | K2 | PS256 | Từ chối K1 và RS256 nếu không còn thuộc profile |

**Không có mapping** `K1 → any RSA alg`, `K2 → all JOSE algs`. `kid` chỉ là hint trong trusted issuer registry, không tạo trust từ token header.

### 17.3. Token phát sau ngày cutover nhưng khai K1

Một AS node còn dùng cấu hình cũ có thể phát RS256 token sau cutover. Phải theo dõi actual last signing time và signer-side key policy. **Đừng cho phép mọi algorithm để “tránh lỗi tạm thời”**; sửa rollout/AS nodes, duy trì overlap có kiểm soát và xác minh key trust.

### 17.4. Compromise khác retirement

K1 retired bình thường có thể verify old tokens đến khi hết hạn. Nếu private K1 bị lộ, attacker có thể ký JWT mới với `iat` giả quá khứ; phải **emergency distrust** K1, không chỉ kiểm `iat <= stopSigningAt` rồi nhận.

## 18. JWKS caching, unknown `kid` và lỗi vận hành dễ biến thành bypass

Resource Servers thường cache JWKS:

~~~http
GET /oauth2/jwks HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

Trusted response có thể chứa public signing keys K1 và K2 trong overlap. Khi nhận `kid` chưa thấy:

1. Kiểm token size/format/header và rate limit.
2. **Chỉ** refresh **trusted issuer JWKS URI**, không lấy bất kỳ URL nào từ JWT header.
3. Kiểm key/alg compatibility và trust state.
4. Nếu vẫn không tìm được key đáng tin, **từ chối token**.

### 18.1. Unknown `kid` không đồng nghĩa yêu cầu phát sinh trust mới

Attacker có thể tạo hàng nghìn JWT với `kid` khác nhau, làm RS liên tục refresh JWKS nếu code không giới hạn. Cần cooldown/negative caching theo policy, bounded retries, rate limits và kiểm JWKS payload size. Không ghi raw unknown `kid` vào Prometheus label gây **cardinality DoS**.

### 18.2. Cache stale sau key compromise

Nếu K1 bị lộ và AS xóa public K1 khỏi JWKS, RS có thể vẫn cache K1. Emergency response cần **trust revocation propagation**, cache invalidation/force update, trust-policy version, ACK hoặc fail closed ở nodes stale. **Xóa key khỏi JWKS response không đồng nghĩa mọi RS ngừng tin key ngay lập tức.**

### 18.3. Fail-closed khi JWKS unavailable

Nếu RS có cached trusted public key còn hợp lệ theo key-freshness policy, có thể tiếp tục verify offline. Nếu không có key/trust state cần thiết, không được **chuyển sang parse-only** hoặc accept JWT chưa verify vì JWKS timeout. Tùy API contract có thể trả `401` hoặc dependency failure `503`, nhưng request **không được cấp quyền**.

### 18.4. Key source và token profile phải ổn định qua retry

Không cho retry lần hai dùng **algorithm rộng hơn** hoặc đổi sang key set issuer khác để vượt qua lỗi lần đầu. Một request chỉ có **một trust policy được chọn** cho mục đích authentication, không thực hiện “verify với mọi key đến khi thành công”.

## 19. Không trộn algorithm validation với revocation và replay

Algorithm confusion thường nhắm tới **tạo token giả hoặc bypass verification**. Nhưng một token hoàn toàn hợp lệ cũng có thể bị **đánh cắp và phát lại**:

~~~text
Case A: forged JWT do key/algorithm confusion
  -> vấn đề: token không thực sự do AS đáng tin phát

Case B: valid JWT access token bị sao chép
  -> vấn đề: caller sở hữu Bearer credential của người khác

Case C: revoked JWT access token còn exp
  -> vấn đề: RS offline không có state update
~~~

Các biện pháp phải giải quyết **đúng nguyên nhân**:

| Nguy cơ | Cách phòng |
| --- | --- |
| Algorithm/key confusion | Algorithm allowlist, trusted keys, key type & purpose checks |
| Token theft qua logs/XSS | HTTPS, storage hygiene, redaction, browser hardening |
| Bearer replay | Short TTL, sender binding DPoP/mTLS theo threat model |
| Refresh-token reuse | AS rotation/family reuse detection |
| Token revoked nhưng RS offline | Denylist/introspection/session version/event theo SLA |
| Cross-resource access | `aud`, `scope`, tenant/object authorization |

### 19.1. DPoP proof không sửa lỗi issuer verification

Nếu RS nhận access token forged do algorithm confusion, việc attacker gửi một DPoP proof mới **không biến access token thành hợp lệ**. RS phải verify access token theo đúng issuer policy **và** DPoP proof/key binding theo RFC 9449.

### 19.2. JWT `jti` không mặc định one-time

`jti` trong access token có thể dùng cho denylist/audit, nhưng access token Bearer thường có thể dùng nhiều API calls trước expiry. `jti` trong DPoP proof mang semantics chống replay proof. **Không áp một replay store dùng một lần cho mọi JWT chỉ để “an toàn hơn”.**

### 19.3. Opaque token không có JWS `alg` để nhầm ở RS

Với opaque token, RS thường gọi AS **introspection endpoint** (RFC 7662) và tin response qua **authenticated AS-RS channel**, sau đó kiểm active/audience/scope. Nó không tự xử lý JWT signing algorithm; tuy nhiên hệ thống vẫn có threat model: token endpoint/introspection caller auth, TLS, replay, caching, revoke, issuer trust và API authorization. Opaque token **không xóa mọi kiểu key/algorithm confusion trong hệ thống**, nhưng thay trust verification model tại RS.

## 20. Những sai lầm phổ biến trong triển khai

### 20.1. “Token ghi `alg=RS256` thì chắc chắn được AS ký”

**Sai.** Header có thể do bất cứ ai tạo. Chỉ **cryptographic verification với đúng AS public key được tin** mới chứng minh signature thuộc key tương ứng; còn cần `iss`, `aud`, type/claims validation.

### 20.2. “`alg` là protected header nên có thể tin nó ngay”

**Sai.** JWS protected header chỉ được integrity-protected **sau khi signature verification thành công**. Trước thời điểm ấy, nó vẫn là **untrusted input**. Có thể đọc `alg` để áp **reject/check allowed policy**, không cho nó mở policy mới.

### 20.3. “HS256 yếu hơn RS256, nên dùng RS256 sẽ hết lỗi”

**Không đủ.** Cả hai là thuật toán được chuẩn hóa. Lỗi xảy ra khi **dùng sai key type, secret bị công khai hoặc algorithm policy không được khóa**, không phải do HS256 luôn yếu về primitive.

### 20.4. “Public RSA key có thể là HMAC secret để tiện dùng chung”

**Sai nghiêm trọng.** Public key vốn không bí mật. Khi dùng nó làm HMAC secret, attacker biết key có thể tạo MAC. Cần typed key objects và không dùng chung key material giữa symmetric/asymmetric modes.

### 20.5. “Thư viện hỗ trợ HS256 và RS256 nghĩa là ứng dụng nên nhận cả hai”

**Sai.** Library capability không phải issuer trust policy. Chỉ nhận algorithms **được thỏa thuận và cấu hình** theo issuer/token profile.

### 20.6. “`kid` trong JWT là đường dẫn tới file key”

**Không nên.** `kid` là string do token chưa verify cung cấp, không phải filesystem path/SQL fragment/remote URL đáng tin. Lookup bằng registry các IDs được phê duyệt.

### 20.7. “`jku` và `x5u` cho phép JWT tự chỉ ra key thật”

**Sai.** URL do token tự khai không chứng minh key thuộc AS. Nếu được dùng phải ràng buộc vào trusted source/policy; tránh SSRF.

### 20.8. “Embedded `jwk` đúng định dạng thì đó là issuer public key”

**Sai.** Một attacker có thể tự tạo key pair. DPoP proof có cơ chế dùng embedded JWK theo profile riêng; access token vẫn phải verify bằng trusted **AS keys**.

### 20.9. “Một key `kid=1` dùng được cho mọi issuers”

**Sai.** `kid` không duy nhất toàn cầu. Phải namespace theo issuer/purpose, tránh cross-issuer trust confusion.

### 20.10. “`iss` đã ở payload thì RS có thể tin ngay và tải JWKS tương ứng”

**Sai nếu bỏ allowlist.** `iss` chưa được verify chỉ có thể làm routing hint tới issuer **đã cấu hình tin cậy**; không được dynamic trust mọi URL.

### 20.11. “Không tìm được key thì cứ decode claims”

**Rất nguy hiểm.** Decode Base64url không phải signature verification. Lỗi JWKS/KMS chỉ cho phép fail closed, không cho bypass authentication.

### 20.12. “Algorithm không khớp thì thử algorithm khác”

**Sai.** Nếu token không đúng issuer policy, phải từ chối. Không thử HS256/RS256/PS256/ES256 với các keys tùy tiện cho tới khi một nhánh thành công.

### 20.13. “Đang rotate từ RS256 sang PS256 thì cho phép mọi RSA alg”

**Sai.** Dùng **key versions riêng, mapping `kid→alg` đúng** và sunset deadline; không tạm nới sang all algorithms.

### 20.14. “`alg=none` có thể được dùng để chạy API khi AS down”

**Sai.** Hệ thống yêu cầu signed access tokens không được nới chính sách chỉ vì dependency lỗi. Từ chối token chưa xác minh.

### 20.15. “JWE decrypt được là giống JWS verify được”

**Sai.** Recipient public-key encryption có thể do bất kỳ bên nào tạo; decrypt và AEAD tag không tự chứng minh AS phát claims. Nested token phải verify inner issuer-authenticated layer.

### 20.16. “ID token có chữ ký đúng thì là access token”

**Sai.** ID token OIDC có audience/purpose dành cho **client**. RS cần access token đúng token type và resource audience.

### 20.17. “DPoP proof `jwk` có thể dùng kiểm access token”

**Sai.** Proof key thuộc client để xác minh sender proof, còn access token thuộc AS issuer trust. Hai chữ ký có ý nghĩa khác nhau.

### 20.18. “Signature hợp lệ thì `scope=orders.delete` chắc chắn được phép”

**Sai.** Scope có thể không thuộc route, token sai `aud`, tenant sai, user bị revoke hoặc order thuộc người khác. Authentication và authorization khác nhau.

### 20.19. “JWT ký an toàn thì không cần TLS”

**Sai.** Bearer token có thể bị đánh cắp và replay nguyên chuỗi; chữ ký không giấu payload. Dùng HTTPS, bảo vệ client storage và logs.

### 20.20. “JWKS không có private key nghĩa là không thể bị tấn công”

**Sai.** Public JWKS đúng là cần thiết để verify; vấn đề là **verifier trust source bị thay**, stale caches, issuer mix-up hoặc public-key-as-HMAC-secret bug.

### 20.21. “Sau update thư viện JWT thì không cần test thuật toán nữa”

**Sai.** Cập nhật thư viện giúp giảm lỗi đã biết, nhưng ứng dụng vẫn có custom adapters, dynamic issuer resolution và cấu hình sai. Bảo đảm bằng **negative tests**.

### 20.22. “Chỉ chặn `HS256` là đã hết mọi confusion”

**Sai.** Còn `none`, wrong key sets, `jku`/embedded `jwk`, key use, nested format, issuer/type confusion và algorithm migration bypass. Cần threat model nhiều lớp.

### 20.23. “RSA-OAEP-256 là RSA signature mode”

**Sai.** `RSA-OAEP-256` dùng trong JWE key management. RS256/PS256 là JWS signature algorithms. Không đánh đồng vì cùng tên bắt đầu bằng RSA.

### 20.24. “Không có `alg` trong public JWK nghĩa là chấp nhận mọi thuật toán”

**Sai.** JWK field có thể tùy chọn; issuer/resource server phải có allowlist **độc lập**.

### 20.25. “Token không có claim `exp` vẫn dùng được nếu signature đúng”

**Không đúng với access-token profile yêu cầu `exp`**. Cần validate thời hạn, issuer, audience và các claims bắt buộc; signature không làm token sống vô hạn.

## 21. Tình huống thực tế: từ bug nhỏ đến sự cố xác thực

**Tình huống A — RS256 issuer, HS256 token trong request.**

Orders API được cấu hình RSA public key. Một token đến với `alg=HS256`.

**Đánh giá:** Nếu policy chỉ cho RS256, phải từ chối **trước khi tạo principal**. Nếu ứng dụng có custom generic verifier dùng public RSA bytes làm HMAC secret, cần coi đó là lỗ hổng algorithm confusion nghiêm trọng và thay verifier.

**Tình huống B — JWKS URI được lấy từ `jku`.**

Ứng dụng thấy `jku=https://unknown.example/keys` và tải keys mà không kiểm trust.

**Đánh giá:** Key source injection/SSRF. Khóa phải thuộc trusted AS JWKS registry; URL trong header không được tự mở rộng trust.

**Tình huống C — OIDC ID token được gửi làm API Bearer.**

Một ID token của browser client có `iss` đúng OP, chữ ký RS256 hợp lệ nhưng `aud=web-client`.

**Đánh giá:** Orders RS phải từ chối vì **sai token type/audience**, không suy “same issuer signature = any role”. Cần type/profile validation tách biệt.

**Tình huống D — Multi-issuer collision.**

Issuer A và B cùng có `kid=main`; Orders RS dùng một global key map không kèm issuer.

**Đánh giá:** Có nguy cơ chọn public key sai trust domain. Tách issuer-specific authentication managers, alg/key sets, issuer claim validation và audience.

**Tình huống E — K1 RS256 retired, K2 PS256 active.**

Token cũ K1 còn `exp`, token mới K2 được phát.

**Đánh giá:** Có thể tạm verify cả **K1→RS256** và **K2→PS256** theo overlap; không nhận `K1→HS256`, `K2→HS256` hoặc thuật toán khác do token tự khai.

**Tình huống F — Private signing K1 bị lộ.**

Attacker có thể tạo JWT đúng RSA signature của key cũ dù K1 đã retired verify-only.

**Đánh giá:** Đây là signing-key compromise, không chỉ algorithm confusion. Cần emergency distrust K1 trên RS, invalidate tokens theo policy và xử lý JWKS cache.

**Tình huống G — RS chỉ decode JWT để lấy user ID.**

API Gateway chuyển `sub` đã decode qua `X-User-Id` đến backend và backend tin header.

**Đánh giá:** Chưa xác minh issuer signature và không có authenticated delegation. Gateway phải verify đầy đủ, backend phải tin kênh/gateway theo contract chống header spoofing hoặc tự verify token.

**Tình huống H — JWE có `alg=RSA-OAEP-256`, RS cho truy cập sau decrypt.**

Attacker có thể mã hóa claims tự tạo bằng public encryption key của Orders RS.

**Đánh giá:** JWE decrypt/tag không tự chứng minh issuer. Cần signed inner JWT/issuer authentication theo profile; kiểm claims và quyền.

**Tình huống I — Access token gắn DPoP key.**

Client có một DPoP proof với embedded `jwk` và access token JWT của AS.

**Đánh giá:** Verify hai nguồn khóa khác nhau: access-token signature bằng trusted AS key, proof signature bằng client DPoP JWK; đối chiếu `cnf.jkt` và request binding. Không tráo proof key thành issuer key.

**Tình huống J — Developer bật “accept any JWT alg” trong môi trường test rồi deploy.**

Hệ thống chạy được với mọi IdP/token mẫu.

**Đánh giá:** Test convenience đã phá production trust policy. Tách test-only fixture và production configuration, kiểm cấu hình fail nếu allowed algorithms không được khai báo cụ thể.

**Tình huống K — Unknown `kid` khi key mới chưa prepublish.**

AS ký token K2, RS chỉ cache K1.

**Đánh giá:** Lỗi key distribution, không nên khắc phục bằng cách bỏ signature. Prepublish key mới, bounded trusted JWKS refresh và sync rollout.

**Tình huống L — Thư viện legacy chấp nhận `alg=none`.**

Một đường error handling bỏ qua signature khi token không có signature segment.

**Đánh giá:** Signature bypass. Phải từ chối theo signed-access-token policy, nâng thư viện và loại custom fallback.

**Tình huống M — Attacker-controlled `kid` được nối vào file path.**

Verifier tải key dựa vào string từ JWT header mà không lookup registry.

**Đánh giá:** Có rủi ro key-file path injection; dùng `kid` như opaque identifier đã được allowlist, không như filesystem path.

**Tình huống N — RS hỗ trợ JWT access token từ hai khách hàng doanh nghiệp.**

App tự parse `iss`, gọi discovery/JWKS URL với bất kỳ hostname rồi chấp nhận issuer trả lời.

**Đánh giá:** Dynamic trust vulnerability. Issuer phải có trong **admin-approved allowlist**, discovery chỉ trên trusted endpoints và token `iss` phải khớp sau verify.

**Tình huống O — JWT ký đúng AS, sai resource audience.**

Token `aud=payments-api` được gửi đến Orders, scope tên cũng trùng `read`.

**Đánh giá:** Từ chối `aud` mismatch. Chính sách audience là một ranh giới bảo mật **độc lập** với algorithm correctness.

**Tình huống P — JWT access token bị sao chép từ logs.**

Token RS256 đúng issuer được attacker gửi lại trước `exp`.

**Đánh giá:** Không phải algorithm confusion; đó là **Bearer replay**. Cần redact logs, TTL, revoke và DPoP/mTLS sender binding khi phù hợp.

**Tình huống Q — Opaque token bị xem nhầm thành JWT vì chứa dấu chấm.**

Application cố Base64url-decode thay vì gửi introspection theo hợp đồng.

**Đánh giá:** Format confusion. Token format được quyết định theo **client/issuer/resource contract**, không chỉ dựa số ký tự `.`; dùng đúng opaque introspection path.

**Tình huống R — Proxy gắn `X-Verified-JWT: true` do client tự tạo.**

Backend tin header và bỏ verification.

**Đánh giá:** Không phải lỗi thuật toán thuần túy nhưng gây cùng kết quả authentication bypass. Hủy/ghi đè headers từ client ở trusted gateway, bảo vệ mTLS/internal assertion và verify provenance.

**Tình huống S — RS nhận JWS(JWE) nhưng chỉ verify lớp ngoài.**

Signature của AS trên ciphertext hợp lệ, nhưng claims bên trong sai `exp` hoặc `aud`.

**Đánh giá:** Chưa hoàn tất nested token validation. Phải decrypt inner JWE, kiểm tag, claims và resource authorization.

**Tình huống T — Issuer ký JWT bằng PS256 nhưng RS contract RS256-only.**

Chữ ký PS256 có thể đúng, thư viện hỗ trợ PS256.

**Đánh giá:** RS từ chối nếu **chưa có migration policy**. Lỗi là contract mismatch cần phối hợp phát hành/kiểm, không phải nguyên nhân để tự mở toàn bộ thuật toán.

**Tình huống U — JWT client assertion được verify bằng AS public key.**

OAuth client gửi assertion tại token endpoint; AS lại dùng key của chính AS thay vì registered client key.

**Đánh giá:** Sai key domain. Với client assertion, key cần thuộc **client registration**, kiểm `iss/sub/aud/exp/jti` theo assertion profile. Không dùng issuer access-token signing key ở mọi chỗ.

**Tình huống V — Logout nhưng RS vẫn chấp nhận JWT đã verify.**

Algorithm RS256 đúng, token chưa hết `exp`, nhưng user đã logout.

**Đánh giá:** Authentication crypto pass không phản ánh revoke state. Cần state/revocation SLA hoặc short-lived AT, không đổi thuật toán để giải quyết logout.

## 22. Kỹ thuật phát hiện và quan sát mà không lộ token

Nên đo các sự kiện ở **đúng ranh giới kiểm**:

~~~text
jwt_algorithm_not_allowed_total
jwt_key_type_mismatch_total
jwt_untrusted_issuer_total
jwt_unknown_kid_total
jwt_jwks_refresh_failures_total
jwt_issuer_mismatch_total
jwt_audience_mismatch_total
jwt_signature_invalid_total
jwt_token_type_invalid_total
jwt_nested_format_invalid_total
jwt_token_rejected_expired_total
jwt_bearer_replay_suspected_total
jwt_revoke_state_unavailable_total
~~~

### 22.1. Không ghi raw `alg`/`kid` làm metric labels tùy ý

Attacker có thể tự tạo header chứa nhiều `kid` giá trị dài/độc nhất. Nếu metric dùng label từ untrusted `kid`, hệ thống giám sát có thể bị **cardinality exhaustion**. Chuẩn hóa thành `known_key_alias`, `unknown`, `not_allowed`; `alg` cũng nên được phân nhóm cố định.

### 22.2. Không log raw JWT hoặc HMAC secret

JWT access token, refresh token, client assertion, ID token và DPoP proof có thể chứa **credentials hoặc PII**. Logs nên chỉ có correlation ID không bí mật, route category, known issuer alias, failure category, time, rate-limit signal và trusted key-version alias khi được phép.

### 22.3. Tín hiệu cảnh báo đáng ưu tiên

- Tăng đột biến số request JWT `alg` ngoài allowlist;
- `kid` lạ tăng đồng thời với JWKS refresh storms;
- Tăng JWT signature failures sau rotation/migration;
- Token thành công với thuật toán **không đúng issuer policy** (nếu xuất hiện, coi là incident);
- Một service nhận ID token hoặc DPoP proof trong Bearer access-token path;
- JWKS/config được thay đổi trái quy trình;
- Cấu hình verifier mất `allowedAlgorithms` hoặc bật unsupported algorithms.

**Không coi tất cả invalid JWT là bằng chứng tấn công thành công.** Cần đối chiếu quyết định allow/deny, deployment và nguồn request để phân biệt probing, bug clients và compromised credentials.

### 22.4. Error contract cho caller

Caller không nên nhận chi tiết như “public key K1 được dùng sai làm HMAC secret”. Với token không hợp lệ, thường trả **`401` và thông điệp `invalid_token` phù hợp RFC 6750**, không lộ key, secret, claims hay stack trace. Khi principal xác thực đúng nhưng **thiếu scope**, thường xử lý **`403`/`insufficient_scope`** theo API contract. Hạ tầng JWKS/KMS outage có thể dẫn tới dependency error nhưng **không biến thành allow**.

## 23. Incident response nếu nghi ngờ algorithm confusion đã bị khai thác

Đây có thể là sự cố **issuer impersonation**, nên ưu tiên ngăn API nhận token không thuộc AS:

~~~mermaid
flowchart TD
    A["Phát hiện token được accept\nvới alg/key không đúng policy"] --> B["Dừng đường verify sai\nvà chuyển fail closed"]
    B --> C["Xác định issuers, RS nodes,\nkey types, token profiles ảnh hưởng"]
    C --> D["Triển khai verifier với allowlist\nvà typed trusted keys"]
    D --> E["Kiểm deploy/caches/trust versions\ntrên mọi instance"]
    E --> F["Audit access, privileges,\nrequests và dữ liệu đã bị ảnh hưởng"]
    F --> G["Revoke/suspend grants hoặc keys\nnếu bị lộ/compromised theo kết quả"]
    G --> H["Negative tests, monitoring,\npost-incident hardening"]
~~~

### 23.1. Phân loại sự cố trước khi rotate mọi key

| Kịch bản | Khắc phục trọng tâm |
| --- | --- |
| Public RSA key bị dùng như HMAC secret | Sửa verifier/key type/algorithm allowlist; đánh giá tokens forged; public key vốn công khai |
| Private AS signing key bị lộ | **Emergency distrust signing key**, rotate, xử lý JWT thật/giả |
| HMAC shared secret bị lộ | Rotate/disable shared secret ở AS và mọi verifiers, chặn old-secret tokens |
| Trusted JWKS bị thay bằng attacker keys | Khôi phục nguồn tin cậy, cache invalidation, integrity/transport controls |
| `jku` khiến RS tải attacker JWKS | Chặn dynamic trust/SSRF, patch code và audit affected traffic |
| OIDC ID token bị dùng nhầm ở API | Sửa type/audience validation, điều tra cross-token usage |

**Không tuyên bố “rotate RSA key sẽ tự sửa HS/RS confusion”** nếu code vẫn cho phép public key mới làm HMAC secret. **Root cause là verifier policy**, phải được sửa và kiểm thử.

### 23.2. Điều tra tác động nhưng không tạo thêm rủi ro

- Xác định những JWT requests đã được **accepted** với alg không hợp lệ, nếu audit có phân loại.
- Đối chiếu quyền `sub`, `scope`, API methods, tenant IDs và dữ liệu truy cập từ nguồn kiểm chứng đáng tin.
- Không in lại raw tokens ở incident tickets, dashboards hay chat; lưu evidence theo hệ thống bí mật/retention policy.
- Khi nghi ngờ attacker có forged JWT, rà soát các side effects đã thực hiện, không chỉ 401/403 metrics.
- Phối hợp AS owner, RS/API owners và security/SRE để xác minh **mọi instances** đã áp verifier policy mới.

### 23.3. Tại sao có thể cần revoke token/grant dù đã sửa verifier?

Algorithm confusion có thể cho attacker gọi API trái phép, sửa quyền hoặc tạo dữ liệu persisted. Sau khi chặn forgery path, phải đánh giá **compromised sessions, grants, stored secrets, data integrity** và quyền còn tồn tại; chỉ vá JWT library không tự đảo ngược side effects đã xảy ra.

### 23.4. Kiểm tra sau khắc phục

1. Token ký đúng issuer/allowed alg vẫn hoạt động.
2. Token `HS256` khi policy RS256-only bị từ chối.
3. `alg=none`, wrong issuer, wrong key type, `jku` không tin và bad signature bị từ chối.
4. Không có fallback parse-only trong error paths.
5. Token ID/DPoP/assertion bị từ chối ở API access-token endpoint.
6. JWKS outage và key rotation không mở thêm algorithm/key sources.
7. Các RS instances/regions báo đúng trust-policy version.

## 24. Ma trận kiểm thử âm và kiểm thử hồi quy

Với bảo mật JWT, một **positive test** “token hợp lệ trả 200” là chưa đủ. Algorithm confusion thường chỉ xuất hiện ở **negative paths**: token format sai, algorithm ngoài policy, key không khớp issuer, JWKS stale hoặc decoder fallback. Bộ test cần chứng minh **không có authenticated principal hay side effect** sau bất kỳ thất bại nào.

### 24.1. Signature và algorithm policy

| Test case | Kỳ vọng |
| --- | --- |
| Token của trusted AS, `alg=RS256`, valid signature, đúng profile | Qua cryptographic verification; tiếp tục claims/authorization |
| JWT `alg=HS256` gửi tới RS256-only resource server | Từ chối algorithm trước khi cấp principal |
| JWT `alg=none` với empty/missing signature | Từ chối vì signed-AT profile yêu cầu signature |
| JWT `alg=PS256` khi issuer policy chỉ RS256 | Từ chối ngoài allowed alg, không tự chấp nhận |
| JWT `alg=ES256` nhưng trusted RSA key | Từ chối key-type/algorithm mismatch |
| JWT `alg=RS256` nhưng verifier chỉ có HMAC secret | Từ chối mismatch, không thử HS256 |
| JWT `alg=RS256` với signature sai | Từ chối |
| JWT `alg=RS256` có header/payload bị sửa | Từ chối chữ ký |
| JWT header thay `alg` nhưng giữ signature cũ | Từ chối |
| JWT bị cắt/malformed sections | Từ chối parse/format |
| `alg` null/không có trong JWS signed profile | Từ chối |
| `alg` string lạ/không hỗ trợ | Từ chối, không fallback |
| `alg` sai chữ hoa/thường khác registry identifier | Từ chối theo exact matching |
| HMAC secret có entropy yếu/được hard-code | Security config review fail, không deploy |
| Public RSA key bytes được đưa vào API HMAC | Security regression test fail |
| Một RSA verification key được phép dùng với bất kỳ alg nào | Policy test fail nếu profile ràng 1 key→1 alg |
| JWT có `crit` chứa extension chưa được hỗ trợ | Từ chối theo JOSE rules |
| JWT có `b64=false` ngoài allowed profile | Từ chối |
| JWT có detached payload khi API chỉ cho Compact JWT thông thường | Từ chối |

### 24.2. Key selection, issuer và JWKS trust

| Test case | Kỳ vọng |
| --- | --- |
| JWT `kid` hợp lệ, key thuộc AS đúng | Có thể verify sau đủ các checks |
| JWT `kid` không tồn tại trong trusted issuer key set | Từ chối sau bounded trusted refresh |
| JWT có cùng `kid` với key của issuer khác | Không chọn sai issuer |
| JWT `kid` trùng nhưng key bytes khác | Không chấp nhận ambiguous mapping |
| JWT public `jwk` do attacker cung cấp | Không tự tin làm AS verification key |
| JWT `jku` tới attacker host | Không tải arbitrary URL/không thêm trust |
| JWT `x5u` tới endpoint không allowlist | Không tải/tin certificate tùy ý |
| JWT `kid` chứa path traversal-like string | Không dùng làm filesystem path |
| JWT `kid` chứa chuỗi dài bất thường | Reject hoặc bounded parsing, không OOM |
| JWT `iss` trỏ URL lạ ngoài allowlist | Reject, không dynamic discovery |
| JWT `iss` của issuer B, signature verify bằng key B, API chỉ tin A | Từ chối issuer mismatch |
| JWT key `use=enc` bị dùng để verify JWS | Từ chối purpose mismatch |
| JWK `kty=oct` xuất hiện trong registry chỉ RSA signer | Từ chối key-type mismatch |
| Trusted JWK không có optional `alg`, token alg khác policy | Từ chối bằng explicit allowlist |
| JWT header `kid` giả làm key đang retired/compromised | Không cho re-enable trust state |
| JWKS TLS certificate không hợp lệ | Không tin nguồn public key |
| JWKS trả private key parameters | Security validation fail/incident, không publish |
| JWKS refresh từ token-supplied URL | Integration test phải bảo đảm **không có request outbound** |
| JWKS unknown-kid flood | Rate-limit/bounded retries; không refresh storm hoặc label explosion |

### 24.3. Token type, claims và authorization

| Test case | Kỳ vọng |
| --- | --- |
| JWT RS256 đúng chữ ký, `iss` sai | Từ chối |
| JWT RS256 đúng chữ ký, `aud` thiếu/sai | Từ chối |
| JWT RS256 đúng chữ ký, `exp` đã qua | Từ chối |
| JWT RS256 đúng chữ ký, `nbf` trong tương lai | Từ chối theo clock policy |
| JWT RS256 đúng chữ ký, `iat` quá xa tương lai | Từ chối theo policy |
| JWT `exp-iat` vượt max access-token TTL | Từ chối nếu profile yêu cầu |
| JWT không có `typ=at+jwt` khi RFC 9068 profile bắt buộc | Từ chối token type |
| OIDC ID token với client `aud` gửi tới Orders RS | Từ chối token type/audience |
| JWT client assertion dùng tại Orders API | Từ chối assertion-as-AT |
| DPoP proof JWT gửi như OAuth access token | Từ chối proof-as-AT |
| AT JWT đúng chữ ký nhưng thiếu `scope=orders.read` | Từ chối resource action |
| AT JWT đúng scope nhưng order thuộc tenant khác | Từ chối object authorization |
| AT đúng algorithm/claims nhưng grant bị revoke | Từ chối theo revocation SLA |
| Rotated refresh token cũ gửi lại token endpoint | AS xử lý reuse/family state |
| JWT chưa verify đưa `sub=admin` vào principal trước crypto check | Test phát hiện, phải không tạo principal |
| JWT access token Bearer được gửi nhiều lần hợp lệ | Không false positive one-time theo `jti` |
| DPoP proof `jti` bị replay trong window | Từ chối proof replay |
| DPoP proof key không khớp AT `cnf.jkt` | Từ chối sender binding |

### 24.4. Nested JWS/JWE và thuật toán mã hóa

| Test case | Kỳ vọng |
| --- | --- |
| StE outer JWE decrypt thành công, inner JWS signature hợp lệ | Tiếp tục token validation |
| StE outer JWE decrypt thành công, inner JWS tự ký attacker | Từ chối issuer signature |
| StE outer JWE decrypt đúng, inner `alg=none` | Từ chối |
| StE outer `alg=RSA-OAEP-256`, `enc=A256GCM` theo policy | Chấp nhận crypto layer nếu recipient key đúng |
| Outer JWE có `enc` ngoài allowlist | Từ chối, không decrypt tùy ý |
| JWE dùng wrong recipient private key | Từ chối |
| JWE GCM tag/ciphertext/AAD bị sửa | Từ chối |
| JWE `alg=dir` hợp lệ nhưng encrypted-key segment rỗng | Xử lý theo profile, không nhầm thành `none` |
| Inner JWS bị tách khỏi JWE và gửi vào endpoint chỉ nhận nested token | Từ chối sai token profile |
| EtS outer JWS verify đúng nhưng inner JWE decrypt sai | Từ chối |
| EtS chỉ verify outer JWS rồi tự cho phép API | Integration security test fail |
| Nested object khai `cty=JWT` nhưng không có inner JWT đúng | Từ chối |
| Nested object có nhiều lớp hơn allowed depth | Từ chối |
| JWE `zip` nở thành payload quá lớn | Từ chối theo resource limits |

### 24.5. Vòng đời khóa, availability và incident

| Test case | Kỳ vọng |
| --- | --- |
| K1→K2 RS256 normal rotation | JWT cũ K1 còn hạn và JWT mới K2 đều verify theo window |
| RS256 K1→PS256 K2 controlled migration | K1 chỉ RS256, K2 chỉ PS256 |
| Migration token dùng HS256 với K1/K2 | Từ chối |
| Key K1 bị emergency distrust | JWT signed K1 bị từ chối dù chưa hết `exp` |
| RS cache public K1 sau emergency distrust | Node stale không được silently allow |
| JWKS outage, RS có trusted cached key còn hiệu lực | Chỉ xử lý theo cache policy |
| JWKS outage, RS chưa có key hợp lệ | Fail closed |
| Unknown `kid` gây refresh failure | Không bypass signature |
| Parser exception hoặc unsupported alg | Không chuyển sang base64 decode-only |
| Backwards compatibility branch “try all algs” | Regression test fail |
| Config thiếu required allowedAlgorithms | Fail startup/config validation theo design |
| Đổi Spring/Nimbus library version | Security regression test phải chạy và pass |
| Khóa sign/verify có key_ops sai | Từ chối operation |
| DPoP/ID token key nhầm issuer AS key | Từ chối cross-purpose key |
| Token hợp lệ nhưng RS không kiểm audience sau upgrade | Integration test fail |

### 24.6. JUnit 5 minh họa cho policy gate

Đây là **unit test lớp policy** ở mục 14, không phải bằng chứng thư viện JWT đã verify signature:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;

public final class TrustedJwtAlgorithmPolicyTest {
    private final TrustedJwtAlgorithmPolicy policy =
        new TrustedJwtAlgorithmPolicy(
            "https://auth.example.com",
            Map.of(
                "as-rsa-k1",
                new TrustedJwtAlgorithmPolicy.KeyRecord(
                    "https://auth.example.com",
                    "as-rsa-k1",
                    "RS256",
                    "RSA",
                    true
                )
            )
        );

    @Test
    void onlyRegisteredRsaAlgorithmCanPassMetadataGate() {
        assertNotNull(policy.requireAllowedJwsHeader(
            "RS256", "as-rsa-k1"));

        assertThrows(SecurityException.class,
            () -> policy.requireAllowedJwsHeader(
                "HS256", "as-rsa-k1"));
        assertThrows(SecurityException.class,
            () -> policy.requireAllowedJwsHeader(
                "none", "as-rsa-k1"));
        assertThrows(SecurityException.class,
            () -> policy.requireAllowedJwsHeader(
                "PS256", "as-rsa-k1"));
        assertThrows(SecurityException.class,
            () -> policy.requireAllowedJwsHeader(
                "RS256", "untrusted-key"));
    }

    @Test
    void unknownKeyAndInvalidHeaderCannotBecomeAuthentication() {
        assertThrows(SecurityException.class,
            () -> policy.requireAllowedJwsHeader(
                "RS256", null));
        assertThrows(SecurityException.class,
            () -> policy.requireAllowedJwsHeader(
                "RS256", ""));
    }
}
~~~

**Cần bổ sung integration tests** với signed JWT thật từ test AS, trusted JWKs, `NimbusJwtDecoder`, invalid JWT có header thay alg, misconfigured key sets và Spring Security request pipeline. Unit test policy không đủ để phát hiện library-level verification bug hoặc JWKS caching sai.

## 25. Security code review checklist

Những câu hỏi quan trọng khi review một **Resource Server JWT verifier**:

1. **Trusted issuers** được allowlist ở đâu? Có bị token `iss` tự thêm issuer không?
2. **Allowed algorithms** được cấu hình theo issuer/token profile hay lấy từ untrusted header?
3. Có **typed key objects** và kiểm `kty`, `use`, `key_ops`, curve/size đúng?
4. Một signing key có bị dùng cho **nhiều thuật toán** mà không có mapping chính sách không?
5. Có chỗ nào dùng **RSA public key bytes làm HMAC secret** hoặc trộn symmetric/asymmetric verification không?
6. JWT `alg=none` có bị từ chối ở signed-access-token path không?
7. Unknown `alg`/`kid` có **fail closed** hay chuyển sang parse-only?
8. `kid` có bị nối thẳng vào file path, SQL statement hoặc URL không?
9. Có chỗ nào tự tải `jku`, `x5u`, embedded `jwk` như một nguồn trust không?
10. JWKS URI có đến từ **trusted issuer metadata/config**, với TLS validation và bounded refresh không?
11. Key lookup có namespace theo **issuer, purpose, algorithm, kid** không?
12. Multi-issuer `iss` có được đối chiếu **sau signature verification** với issuer đã chọn không?
13. Key rotation có prepublish/retired verification overlap và emergency distrust riêng không?
14. `typ`/token profile có chặn ID token, client assertion, DPoP proof làm access token không?
15. Nếu dùng nested JWT, có **decrypt/verify cả hai lớp** đúng profile không?
16. JWS `alg` và JWE `alg`/`enc` có được kiểm riêng không?
17. Có giới hạn **token length, nested depth, decompressed size và critical headers** không?
18. Claims `iss`, `aud`, `exp`, `nbf`, `iat` và max lifetime có validator không?
19. Authority mapping từ `scope`/`scp` có kiểm profile đúng và không áp claims chưa verify không?
20. Có business authorization cho **tenant, order owner, operation** sau authentication không?
21. Token revocation/sender constraint (DPoP/mTLS) có được thực thi nếu risk yêu cầu không?
22. JWT signature verification có bị bypass khi KMS/JWKS unavailable hoặc timeout không?
23. Test có **negative cases** HS/RS confusion, `none`, wrong issuer, key injection và stale caches không?
24. Logs/metrics có tránh raw JWT, shared secret, private key và unbounded `kid` labels không?
25. Dependency/security advisories của JWT/JOSE library có được theo dõi và test khi nâng version không?
26. Nếu hỗ trợ nhiều token formats, có **một policy rõ cho từng endpoint** thay vì fallback try-everything không?
27. Có runbook **incident, compromise và forced trust withdrawal** trên toàn RS cluster không?
28. Team có hiểu **signed ≠ encrypted ≠ authorized ≠ not revoked** không?

### 25.1. Quy tắc ra quyết định trước khi deploy

Nếu bất kỳ câu trả lời nào là “không biết” với **trusted issuer key source**, **algorithm allowlist** hoặc **crypto verification có fail-closed không**, chưa nên coi hệ thống đã đủ điều kiện production. Những bất định đó tác động trực tiếp vào việc API có thể nhận **forged access token**.

### 25.2. Những điều có thể chấp nhận có điều kiện

Hỗ trợ nhiều algorithms, keys hoặc issuers **không tự sai** nếu đó là yêu cầu có kiểm soát và được partition theo trust policy. Dùng HS256 cũng **không tự sai** nếu secret custody và trust domain phù hợp. Điều không thể chấp nhận là **để token tự mở trust** vượt policy đã định.

## 26. Quy trình quyết định khi nhận JWT chưa tin

Sơ đồ sau tổng hợp các lớp kiểm soát từ **định dạng token** đến **quyền sử dụng API**. Nó không thay code/JWT library, mà nhấn mạnh điểm nào được phép sử dụng **thông tin chưa verify** và điểm nào phải dùng **trusted configuration**.

~~~mermaid
flowchart TD
    A["Nhận credential từ HTTP request"] --> B{"Đúng credential/profile\nđược endpoint cho phép?"}
    B -->|Không| X["Reject / fail closed"]
    B -->|Có| C["Chọn issuer policy từ\ntrusted allowlist/config"]
    C --> D["Parse JOSE header có giới hạn\n(chưa tin claims/header)"]
    D --> E{"alg, kid, kty, use,\nkey source khớp policy?"}
    E -->|Không| X
    E -->|Có| F["Verify JWS signature\nbằng key issuer đã tin"]
    F --> G{"Signature hợp lệ?"}
    G -->|Không| X
    G -->|Có| H["Kiểm typ, iss, aud,\nexp, nbf, iat, scope"]
    H --> I{"Claims đúng contract?"}
    I -->|Không| X
    I -->|Có| J["Kiểm revocation / DPoP / mTLS\nnếu profile yêu cầu"]
    J --> K{"Đúng state và sender?"}
    K -->|Không| X
    K -->|Có| L["Business authorization:\ntenant / owner / action"]
    L --> M{"Đủ quyền?"}
    M -->|Không| X
    M -->|Có| N["Allow API request"]
~~~

**Với nested JWE(JWS),** phải thêm **recipient decryption/AEAD verification** trước khi xử lý inner JWS. **Với opaque token**, thay bước JWS verification bằng **authenticated introspection response** đúng contract. **Không được áp sơ đồ JWS một cách máy móc** cho tất cả token formats.

### 26.1. Quyết định chỉ dùng hints chưa verify ở đâu?

Có thể đọc `alg`, `kid` và `iss` chưa verify **chỉ để chọn một nhánh kiểm có sẵn trong allowlist**, và nhánh đó phải reject nếu không match. Không được:

- Dùng `scope` chưa verify để gọi service nội bộ với quyền admin;
- Dùng `iss` làm dynamic URL không allowlist;
- Dùng `kid` làm file path;
- Dùng `alg` để cấp quyền chọn HMAC/RSA ngoài issuer policy;
- Dùng `jwk` tự khai làm trusted issuer key;
- Dùng thành công decryption của JWE thay issuer authentication.

### 26.2. Positive verification không kết thúc authorization

Chỉ sau khi signature được kiểm đúng key/alg, RS mới có cơ sở xét claims. Nhưng JWT `scope=orders.read` chỉ là một **permission boundary thô**; quyền với **order cụ thể** và **tenant cụ thể** vẫn phải được kiểm. Khi user bị revoke/grant thay đổi, cần state/TTL policy cập nhật, không dựa vào việc JWT trước đây từng có chữ ký hợp lệ.

### 26.3. Nếu không chắc token format, đừng tự đoán theo số dấu chấm

Một token opaque có thể có ký tự `.`, một nested JWE có năm segment và một JWS có ba segment. **Format là contract** giữa issuer/client/resource, không phải quyền cho parser thử mọi decoder. Một endpoint phải biết mình nhận Bearer signed JWT, opaque introspection token, DPoP-bound JWT hay một nested format được cho phép.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Algorithm confusion là gì?

**Trả lời:** Một dạng lỗi khi verifier **chọn hoặc diễn giải thuật toán/khóa không theo chính sách tin cậy** mà theo dữ liệu do token chưa verify cung cấp. Ví dụ verifier chỉ dự kiến RS256 nhưng cho token đổi sang HS256 và dùng RSA public key bytes làm HMAC secret.

**Câu 2.** Vì sao HS256 không tự yếu hơn RS256?

**Trả lời:** HS256 dùng HMAC-SHA256 với **shared secret** đủ mạnh; RS256 dùng RSA signature với public/private keys. Cả hai có thể an toàn theo đúng profile. Lỗi điển hình là **secret không thực sự bí mật** khi public RSA key bị dùng làm HMAC secret, hoặc shared secret bị phân phối sai trust boundary.

**Câu 3.** Nếu JWT `alg=RS256`, có thể tin ngay token do AS phát không?

**Trả lời:** Không. Header do bên gửi kiểm soát; phải verify signature bằng **trusted AS public key** theo issuer-specific algorithm/key policy, sau đó kiểm claims.

**Câu 4.** Vì sao `kid` không tự là bằng chứng khóa đáng tin?

**Trả lời:** `kid` chỉ là identifier/hint do token đưa vào. Public key phải thuộc **trusted issuer JWKS/registry**, đúng purpose/alg/key type; `kid` có thể trùng giữa các issuers.

**Câu 5.** Nếu JWT có `jku=https://attacker.example/jwks`, RS có nên tải rồi verify không?

**Trả lời:** Không được dùng `jku` tùy ý làm trust source. Nếu profile cho phép trường này, cần **allowlist và trust binding** độc lập; nếu không, bỏ qua/từ chối theo profile. Đồng thời phải phòng SSRF.

**Câu 6.** `alg=none` có nghĩa gì và khi nào phải từ chối?

**Trả lời:** Nó mô tả unsecured JWS theo JOSE trong những ngữ cảnh đặc biệt. **Signed OAuth JWT access token** đòi xác thực issuer signature nên phải **từ chối `none`**.

**Câu 7.** Trong JWE, `alg=RSA-OAEP-256` và `enc=A256GCM` có phải thuật toán ký không?

**Trả lời:** Không. `alg` của JWE chỉ key management, `enc` chỉ content encryption. JWS signature dùng `RS256`, `PS256`, `ES256`, HMAC hoặc thuật toán được profile cho phép.

**Câu 8.** Decrypt được JWE chứa `scope=admin` có đủ cho phép API không?

**Trả lời:** Không. Public-key recipient encryption không chứng minh issuer; phải có **trusted issuer signature hoặc profile xác thực nguồn khác** và kiểm audience, scope, expiry, tenant, revoke.

**Câu 9.** Tại sao DPoP proof có embedded JWK mà access token không được tin arbitrary embedded JWK?

**Trả lời:** DPoP proof JWK chứng minh **client sở hữu key của proof** theo RFC 9449, và được ràng buộc với access token qua `cnf.jkt`. Access token **phải được AS phát** và verify theo AS keys/introspection độc lập.

**Câu 10.** Nếu chuyển từ RS256 sang PS256, có nên cho `allowedAlgorithms = all`?

**Trả lời:** Không. Cần key versions/trust policy rõ, ví dụ **K1→RS256** trong overlap và **K2→PS256** cho token mới; có deadline sunset, không mở HS256/ES256/`none` theo ý header.

**Câu 11.** Token có signature hợp lệ với issuer A nhưng khai `iss=B` thì sao?

**Trả lời:** Từ chối issuer mismatch. Public key chọn theo trusted issuer A không chứng minh B đã phát token. Không cho claims `iss` tự tạo trust cho B.

**Câu 12.** ID token của OIDC provider được ký bằng cùng key với access token. Orders API có nhận được không?

**Trả lời:** Không được nhận chỉ vì chữ ký đúng. ID token dành cho **OIDC client**, thường có `aud=client_id`, không phải OAuth access token dành cho Orders RS. Kiểm token type, audience và OAuth scopes.

**Câu 13.** JWT signature hợp lệ nhưng `aud=payments-api`, `scope=orders.read` có được vào Orders API không?

**Trả lời:** Không. Audience ràng buộc **resource intended**, là điều kiện riêng ngoài scope; `aud` sai phải từ chối.

**Câu 14.** JWKS outage có cho phép decode claims để phục vụ request không?

**Trả lời:** Không. Có thể dùng trusted public key cache còn hợp lệ theo policy hoặc trả lỗi; không cấp quyền khi không thể xác minh token.

**Câu 15.** Một token RS256 còn `exp` nhưng signing key K1 bị compromise, có nên chấp nhận đến hết hạn?

**Trả lời:** Không tự động. Phải có emergency distrust/incident response; K1 bị lộ cho phép attacker tạo tokens giả có chữ ký đúng, kể cả tự đặt `iat`.

**Câu 16.** Sửa algorithm confusion có làm access token bị lấy cắp không thể replay không?

**Trả lời:** Không. Sửa algorithm confusion ngăn forged token theo đường đó. Bearer token thật vẫn có thể bị sao chép; cần TLS, storage hygiene, TTL, revoke và sender binding theo threat model.

**Câu 17.** Vì sao chỉ nhìn code `jwt.getClaims()` không biết đã an toàn?

**Trả lời:** Phải xác minh claims được trả về **sau cryptographic verification theo trusted issuer policy**. Một số API chỉ parse/decode JSON, không verify; việc dùng chúng làm authenticated principal có thể là bypass.

**Câu 18.** Kiểm `kty=RSA` có đủ an toàn chưa?

**Trả lời:** Chưa. Vẫn cần trusted issuer, allowed `alg`, key size/purpose, đúng public key, signature verification và token claims/authorization. Một RSA key từ attacker cũng có `kty=RSA`.

## 28. Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS signature, protected headers, signing input và key identification.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS, `kty`, `kid`, `use`, `key_ops` và key management metadata.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): HMAC, RSA, RSA-PSS, ECDSA, JWE encryption/key-management algorithm identifiers.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Claims `iss`, `aud`, `exp`, `nbf`, `iat`, `jti` và signed/encrypted/nested JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): **Algorithm verification**, one algorithm per key, key/issuer validation, explicit typing, cross-JWT confusion và attacks liên quan.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `at+jwt`, expected claims, issuer/audience validation và RS behavior.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): AS/RS/client roles, access/refresh token semantics và scopes.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): Issuer metadata/JWKS URI discovery trong trusted configurations.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Token security, theft, client authentication và sender constraints.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credential transport, TLS và `invalid_token`/`insufficient_scope` semantics.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Revocation endpoint và token lifecycle.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Opaque token introspection, caller authentication và token state validation.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT client assertions và sự khác biệt issuer/client key trust.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): Proof JWK, `dpop+jwt`, `cnf.jkt`, HTTP request binding và replay checks.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): Certificate-bound access tokens và mTLS client authentication.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE `alg` vs `enc`, encryption recipient và nested content.
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797): `b64=false`, critical headers và signing input semantics.
- [RFC 8037 — CFRG Elliptic Curve Algorithms for JOSE](https://www.rfc-editor.org/rfc/rfc8037): OKP/EdDSA key types trong JOSE.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token validation, signing algorithms, client audience và `nonce`.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signature validation, JWK Set URI, issuer/time/audience validators và authorities.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): Authenticated introspection model thay cho JWT local verification.
- [OWASP JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT security pitfalls, algorithm/key validation, storage và revocation.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): Token validity không thay quyền trên đối tượng dữ liệu.

**Ghi nhớ:** **Algorithm confusion** phát sinh khi JWT chưa xác minh được quyền điều khiển **thuật toán, loại khóa hoặc nguồn khóa** mà verifier sử dụng. Trường hợp kinh điển là **RS256→HS256** trong một verifier sai, khiến public RSA key bị diễn giải như HMAC secret; các biến thể liên quan gồm `alg=none`, `kid`/`jku`/embedded `jwk` injection, issuer/key mix-up và JWS/JWE/token-type confusion. Phòng thủ dựa trên **issuer-specific algorithm allowlist, typed trusted keys, key purpose/rotation policy, signature verification đầy đủ, explicit token type, issuer/audience/time/scope checks và fail-closed behavior**. Một chữ ký hợp lệ vẫn **không tự bảo đảm** token chưa bị revoke, không bị đánh cắp hay người dùng có quyền trên tài nguyên; Resource Server còn phải thực hiện **sender binding/revocation khi cần và business authorization**.
