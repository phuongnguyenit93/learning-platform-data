# Key identifier

## Mục tiêu học tập

Trong chương **Key management** của học phần **Token Security Fundamentals**, **key identifier** là định danh giúp bên phát hành và bên xác minh tìm đúng khóa mật mã giữa nhiều phiên bản, mục đích sử dụng và miền tin cậy. Trong JSON Object Signing and Encryption (JOSE), trường thường gặp nhất là **`kid` — Key ID**. Nó có thể nằm trong **JWS/JWE header** và trong từng **JSON Web Key (JWK)** thuộc một **JSON Web Key Set (JWKS)**.

Điểm cốt lõi: **`kid` chỉ là gợi ý để chọn khóa, không phải chữ ký, mật khẩu, bằng chứng khóa hợp lệ hay quyền truy cập tài nguyên**. Một token mang `kid=production-signing-key` không trở thành token tin cậy chỉ nhờ tên đó. Bên nhận vẫn phải chọn khóa từ **nguồn đã được tin cậy**, kiểm tra đúng thuật toán và loại khóa, xác minh chữ ký/chứng thực mật mã rồi kiểm tra claims và chính sách của token.

Bài học liên hệ trực tiếp đến **JWT, opaque token, access token, refresh token, OAuth 2.0/OIDC**, quy trình phát hành, xác minh issuer/audience/scope, vòng đời khóa, lưu trữ, thu hồi và phòng chống token bị đánh cắp/phát lại. Trọng tâm được đặt vào cách quản lý **định danh khóa** an toàn, thay vì mô tả mọi thuật toán mã hóa nói chung.

Sau bài học, bạn có thể:

1. Đọc `kid` trong JWS/JWE protected header và JWK; mô tả cách verifier tra cứu khóa từ **trusted JWKS**.
2. Phân biệt `kid` với **`jti`, `sub`, `client_id`, `iss`, `aud`, JWK thumbprint (RFC 7638), `x5t#S256`** và phiên bản khóa của KMS/HSM.
3. Thiết kế phạm vi duy nhất của định danh theo **issuer, key set, tenant, key purpose và policy**, không dùng `kid` như ID toàn cầu.
4. Chọn khóa đúng khi thiếu/trùng/không tìm thấy `kid`, hoặc khi issuer đang rotate khóa ký.
5. Ngăn **key confusion, algorithm confusion, `kid` injection, `jku`/`x5u` SSRF và unknown-`kid` cache-refresh DoS**.
6. Phân biệt key ID phục vụ **JWS signature**, **JWE encryption**, **Client authentication** và **DPoP/mTLS sender binding**.
7. Thiết kế **khâu phát hành, public JWKS, cache, overlap, key compromise, auditing và disaster recovery**.
8. Áp dụng Java/Spring Security và triển khai ma trận kiểm thử có cả trường hợp lỗi.

## 1. Vì sao một khóa cần có định danh?

Authorization Server (AS) có thể ký token bằng nhiều khóa:

~~~text
Issuer: https://auth.example.test

Khóa A:
  kid = orders-signing-2026-09
  thuật toán = RS256
  trạng thái = verify-only (ngừng ký token mới)

Khóa B:
  kid = orders-signing-2026-11
  thuật toán = PS256
  trạng thái = active-signing

Client/Resource Server:
  nhận JWT header kid=orders-signing-2026-11
  chọn public key B từ JWKS thuộc issuer đã tin
  xác minh chữ ký và claims
~~~

Không có định danh khóa, verifier phải xác định khóa bằng cách khác trong một tập khóa. Khi tập khóa lớn hoặc đang xoay vòng, điều này làm tăng độ phức tạp và có thể dẫn tới chọn sai. **`kid`** giúp **phân loại ứng viên**, giảm thử sai và hỗ trợ quan sát vòng đời khóa.

Tuy nhiên, có hai điều cần phân biệt:

- **Định danh khóa:** câu trả lời cho “đang nói đến khóa nào?”.
- **Tin cậy khóa:** câu trả lời cho “khóa đó có thuộc issuer/Client đáng tin và được phép dùng cho thao tác này không?”.

Không được suy từ câu trả lời thứ nhất ra câu trả lời thứ hai.

### Trong JOSE, `kid` có bắt buộc không?

Theo JOSE, `kid` là tham số **tùy chọn**. Một triển khai có thể chỉ có một khóa hợp lệ nên không cần `kid`; một profile hoặc quy ước tổ chức lại có thể **yêu cầu** `kid` để hỗ trợ nhiều khóa và rotation. Vì vậy:

- Không tuyên bố tất cả JWT hợp lệ **bắt buộc** có `kid`.
- Không suy rằng thiếu `kid` cho phép tự động chọn **bất kỳ** khóa nào.
- Thống nhất quy tắc chọn khóa trong **issuer/client registration và verifier policy**.

## 2. `kid` xuất hiện ở đâu?

### JWS — JWT được ký

Một JWS Compact Serialization có ba phần:

~~~text
BASE64URL(protected_header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Protected header đã giải mã có thể là:

~~~json
{
  "typ": "at+jwt",
  "alg": "PS256",
  "kid": "orders-signing-2026-11"
}
~~~

Đây là ví dụ header của **JWT access token** theo một profile có yêu cầu nhận diện token type. `alg` mô tả thuật toán ký, `kid` gợi ý khóa, `typ` giúp phân biệt loại JWT theo hợp đồng; **cả ba chưa được tin trước khi verify**.

### JWK — từng khóa công bố trong JWKS

~~~json
{
  "kty": "RSA",
  "kid": "orders-signing-2026-11",
  "use": "sig",
  "alg": "PS256",
  "n": "<BASE64URL_RSA_PUBLIC_MODULUS>",
  "e": "AQAB"
}
~~~

Chuỗi `n` ở trên là **placeholder**, không phải modulus hợp lệ để sử dụng trong hệ thống thật. Public JWK chỉ cần thông số **public key** cho việc verify; không được công bố RSA private `d`/`p`/`q`/`dp`/`dq`/`qi` hoặc những secret khác.

### JWKS — tập khóa của một nguồn tin cậy

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "orders-signing-2026-09",
      "use": "sig",
      "alg": "RS256",
      "n": "<OLD_PUBLIC_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "orders-signing-2026-11",
      "use": "sig",
      "alg": "PS256",
      "n": "<NEW_PUBLIC_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

Thuộc tính `keys` chứa nhiều JWK. Hai `kid` ở ví dụ minh họa hai **phiên bản khóa khác nhau**; không có yêu cầu `kid` phải chứa ngày tháng hoặc tên dịch vụ. Dữ liệu private key không thuộc public JWKS.

### JWE — token được mã hóa

`kid` còn có thể giúp chọn khóa **mã hóa/giải mã** trong JWE:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "shop-recipient-enc-2026-11",
  "cty": "JWT"
}
~~~

Trong ví dụ JWE này, `alg` là thuật toán quản lý/bao bọc khóa, `enc` là thuật toán mã hóa nội dung. **`kid` có thể chỉ khóa recipient**, không phải signing key của AS. Không trộn khóa `use=enc` với `use=sig` nếu profile/policy không cho phép.

## 3. `kid` không chứng minh chữ ký hoặc danh tính

Giả sử attacker tự tạo JWT header:

~~~json
{
  "alg": "PS256",
  "kid": "orders-signing-2026-11"
}
~~~

và payload:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "admin",
  "aud": "orders-api",
  "scope": "orders:delete",
  "exp": 1893456600
}
~~~

Nếu attacker **không có private signing key** của issuer, việc đoán được `kid` và viết đúng claims vẫn **không tạo ra chữ ký hợp lệ**. Public JWKS và tên `kid` vốn có thể được tải công khai; bảo mật phụ thuộc vào **private key** và quy tắc xác minh chứ không dựa vào `kid` bí mật.

~~~text
Sai:
  if header.kid == "orders-signing-2026-11":
      trust(header.payload)

Đúng (khái niệm):
  select expected issuer and token profile from trusted context
  check header alg against configured allowlist
  locate matching key within trusted issuer key set
  verify cryptographic signature
  validate claims, revocation state if required, authorization
~~~

**`kid` là dữ liệu do token cung cấp** khi nằm trong header JWS/JWE của request. Mặc dù protected header sẽ được signature/MAC bảo vệ khi được xác minh thành công, verifier phải **đọc nó trước khi hoàn tất verify**; lúc đó mọi giá trị header vẫn là input chưa đáng tin.

### Rủi ro khi coi `kid` là bí mật

- Che tên `kid` không ngăn attacker tạo JWT giả nếu verifier bỏ kiểm tra chữ ký.
- Đổi `kid` nhưng **giữ nguyên compromised private key** không xử lý sự cố lộ khóa.
- Dựa vào `kid` để thay `iss`, `aud` hoặc `sub` làm sai ranh giới tin cậy.
- Log giá trị `kid` từ token chưa verify vào metric không giới hạn có thể gây **high-cardinality DoS**.

## 4. Phân biệt `kid` với những identifier khác

| Trường/khái niệm | Định danh cái gì? | Ai đặt/kiểm tra? | Có thay `kid` không? |
|---|---|---|---|
| **`kid`** | Một **khóa mật mã**, thường trong key set cụ thể. | Issuer/Key manager tạo, verifier dùng làm hint. | Đây là trường đang xét. |
| **`jti`** | **Một JWT cụ thể** (JWT ID). | Issuer đặt nếu profile dùng; RS/AS có thể dùng trong replay/denylist. | **Không.** Một khóa có thể ký hàng triệu JWT với `jti` khác nhau. |
| **`iss`** | **Issuer** đã phát token. | AS/OP cung cấp; RP/RS đối chiếu exact trusted issuer. | Không. `kid` có thể trùng giữa hai issuer. |
| **`sub`** | Subject/principal của token trong ngữ cảnh issuer. | AS/OP cung cấp, verifier kiểm tra theo profile. | Không. User có thể đổi token/key mà vẫn cùng `sub`. |
| **`aud`** | Audience/người nhận của JWT. | AS/OP cấp, verifier kiểm tra token dành cho mình. | Không. Khóa có thể ký token cho nhiều audiences. |
| **`client_id`** | OAuth Client đã đăng ký. | AS cấp/đăng ký; kiểm tra theo OAuth flow. | Không. Một Client có thể rotate nhiều khóa riêng. |
| **`scope`** | Phạm vi quyền được cấp. | AS cấp theo Client/user/resource policy; RS enforce. | Không. `kid` không là permission. |
| **`nonce`** | Liên kết giao dịch OIDC hoặc proof tùy profile. | Client/AS/RS dùng theo từng giao dịch. | Không. Nó không nhận diện signing key. |
| **`cnf.jkt`** | Thumbprint của public JWK ràng buộc một token DPoP. | AS phát binding, RS kiểm tra proof và token. | Không. Là fingerprint key theo RFC 7638, không phải nhãn `kid`. |
| **`x5t#S256`** | Thumbprint SHA-256 của chứng chỉ X.509. | JWK/JWS/mTLS profile dùng theo ngữ cảnh. | Không. Hash chứng chỉ khác `kid`. |
| **KMS key version ID** | Phiên bản đối tượng khóa trong hạ tầng KMS/HSM. | Key management service. | Không mặc định; có thể được ánh xạ tới `kid`. |
| **JWK thumbprint** | Fingerprint tính từ các thành phần JWK công khai được quy định. | Thư viện JOSE hoặc key manager tính theo RFC 7638. | Có thể dùng làm `kid` nếu thiết kế chọn, nhưng không bắt buộc. |

### Ví dụ phân biệt

~~~text
Một user (sub=user-123)
  đăng nhập qua Client (client_id=shop-web)
  nhận 2 access tokens (jti=token-A, jti=token-B)
  đều có audience orders-api
  cùng được AS ký bằng private key K
  => header của cả 2 token có thể cùng kid=signing-v4
~~~

Trong **logout/revocation**, `jti` hoặc grant/token-family state có thể dùng nhận diện token cần chặn. **`kid` không phù hợp để “logout user-123”**: gỡ signing key sẽ ảnh hưởng tất cả JWT dựa vào nó, không riêng người dùng này.

## 5. Chuỗi tin cậy: issuer → metadata → JWKS → `kid` → key

Đối với OpenID Connect, RP thường biết **trusted issuer** và có thể lấy Provider Configuration từ endpoint OIDC Discovery phù hợp. Metadata công bố `jwks_uri` của OP:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: auth.example.test
Accept: application/json
~~~

~~~json
{
  "issuer": "https://auth.example.test",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "id_token_signing_alg_values_supported": ["RS256", "PS256"]
}
~~~

**Metadata trên là ví dụ**, không phải server có thật. Theo OIDC Discovery, RP kiểm tra issuer trong metadata **khớp issuer đã mong đợi**. Với OAuth JWT access tokens, RS có thể dùng metadata/`jwks_uri` theo hợp đồng AS/RS; không mặc định các thuật toán ID token được công bố cũng là chính sách của mọi API.

~~~mermaid
flowchart TD
    A["Issuer tin cậy đã cấu hình"] --> B["Tải/kiểm tra metadata AS/OP qua HTTPS"]
    B --> C{"metadata.issuer khớp expected issuer?"}
    C -- Không --> X["Reject provider/token"]
    C -- Có --> D["Chọn trusted jwks_uri"]
    D --> E["Tải/cache JWK Set cho issuer đó"]
    E --> F["Đọc JWT alg/kid như input chưa tin"]
    F --> G{"Alg đúng allowlist; key đúng kid/kty/use?"}
    G -- Không --> X
    G -- Có --> H["Verify signature bằng public key đã tin"]
    H --> I{"Signature hợp lệ?"}
    I -- Không --> X
    I -- Có --> J["Kiểm tra iss, aud, typ, exp, scope, nonce khi áp dụng"]
    J --> K{"Policy cho phép?"}
    K -- Không --> X
    K -- Có --> L["Accept token cho mục đích cụ thể"]
~~~

### Ranh giới quan trọng

**Không** thực hiện:

~~~text
unverified JWT -> read iss -> tự tin issuer đó
unverified JWT -> read jku -> tải JWKS của URL đó
unverified JWT -> read kid -> tìm toàn Internet hoặc mọi KMS
matching kid    -> bỏ verify signature
~~~

**Có thể** đọc một số header/claim chưa tin để **tra cứu ứng viên theo policy**, nhưng không được sử dụng chúng để **mở rộng tập issuer/khóa đáng tin**. Với nhiều issuer, nguồn tin cậy phải được lựa chọn từ cấu hình/transaction/resource context đã được phê duyệt, không từ chuỗi bất kỳ do caller gửi.

## 6. Bộ lọc chọn khóa: `kid` chỉ là một điều kiện

Một JWS verifier an toàn thường cần kiểm tra:

1. **Trusted issuer**: token được phép đến từ ai, theo endpoint/Client registration.
2. **Token purpose**: ID token, JWT access token hay Client assertion.
3. **Accepted algorithm**: ví dụ chỉ `RS256` hoặc `PS256` trong migration được quản trị.
4. **Matching `kid`**: khóa trong tập tin cậy tương ứng có ID nào.
5. **Key type**: `kty=RSA` cho RS*/PS*, `kty=EC` và đúng `crv` cho ES*, v.v.
6. **Key usage**: `use=sig`, `key_ops=verify` nếu được công bố và đúng profile.
7. **Key status**: key có còn được phép verify hay đã bị thu hồi/compromise.
8. **Cryptographic verification**: signature/MAC phải hợp lệ.
9. **Claims/profile validation**: `iss`, `aud`, `exp`, `nbf`, `typ`/`nonce`, scope và quyền nghiệp vụ.

### Pseudocode thuật toán chọn khóa

~~~text
verifyIncomingJwt(token, endpointPolicy):
    expectedIssuers = endpointPolicy.trustedIssuers
    requiredPurpose = endpointPolicy.requiredTokenPurpose

    header = parseBoundedJwsProtectedHeader(token)
    if header.alg not in endpointPolicy.allowedSigningAlgs:
        reject

    issuer = resolveAllowedIssuerFromTrustedContext(
        endpointPolicy, untrustedCandidateClaimsIfNecessary
    )
    if issuer not in expectedIssuers:
        reject

    keySet = trustedKeyCache.forIssuerAndPurpose(issuer, requiredPurpose)
    candidates = keySet.filter(
        kid=header.kid,
        alg=header.alg,
        compatibleKeyType=true,
        keyUse="sig",
        notRevoked=true
    )
    if not uniqueAndAllowedSelection(candidates):
        rejectOrBoundedTrustedJwksRefreshThenReject

    verified = cryptoLibrary.verifyJws(token, candidates.selectedKey)
    if not verified:
        reject

    claims = verified.payload
    require claims.iss exactlyMatches issuer
    require claims.aud contains endpointPolicy.requiredAudience
    validateTokenTypeLifetimeScopeAndContext(claims, requiredPurpose)
    authorizeUserOrClientOnRequestedObject()
~~~

Mã trên là **pseudocode**, không phải thư viện verify JOSE. Việc phân giải nhiều issuer dựa trên claim chưa tin phải được **giới hạn trong tập issuer đã tin**, sau đó kiểm tra exact issuer **sau signature**. Một số profile cho phép kiểm tra nhiều khóa phù hợp khi thiếu `kid`; nếu làm vậy phải dùng thư viện/thuật toán đã pin và một chính sách không mơ hồ. **Không coi `kid` chọn được ứng viên là đã xác minh token**.

## 7. `kid` có thể trùng nhau không?

`kid` là một chuỗi dùng để phân biệt khóa trong một tập; JOSE không định nghĩa nó là **ID duy nhất toàn cầu**. Trong thực hành:

~~~text
Issuer A:
  JWKS A: {kid="key-1", publicKey=A1}

Issuer B:
  JWKS B: {kid="key-1", publicKey=B1}

Không có mâu thuẫn toàn cục nếu verifier luôn
gắn khóa với issuer đúng và không trộn hai sets.
~~~

Ngược lại, một JWKS của **cùng issuer** có hai khóa ký khác nhau nhưng cùng `kid` có thể khiến selection mơ hồ:

~~~json
{
  "keys": [
    {"kty":"RSA","kid":"signing-1","alg":"RS256","n":"<MODULUS_A>","e":"AQAB"},
    {"kty":"RSA","kid":"signing-1","alg":"RS256","n":"<MODULUS_B>","e":"AQAB"}
  ]
}
~~~

Trong ví dụ này, `kid=signing-1` và `alg=RS256` **không phân biệt được khóa A và B**. Đây là một cấu hình lỗi cần sửa từ issuer/key management. Không chọn “JWK đầu tiên” theo thứ tự JSON hoặc thứ tự cache vốn có thể thay đổi.

### Khuyến nghị thiết kế uniqueness

- Giữ `kid` **duy nhất cho các active/verify-eligible keys trong cùng key set** theo chính sách đơn giản, dù JOSE cho phép hệ thống phức tạp hơn.
- Nếu tách nhiều purpose, phải quản lý rõ `(issuer, purpose, kid)`; tránh fallback purpose.
- Không tái sử dụng `kid` cũ cho **key material mới** trong khi các verifier còn cache key cũ.
- Không dùng `kid` đơn lẻ làm key của cache toàn hệ thống multi-issuer.
- Phát hiện duplicate/ambiguous key IDs khi xuất bản JWKS và trong CI/monitoring.

## 8. Thiếu `kid` và unknown `kid`: xử lý khác nhau

### Khi token không có `kid`

JWS header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT"
}
~~~

`kid` vắng mặt **không đồng nghĩa token giả** theo đặc tả chung. Verifier có thể:

1. **Từ chối**, nếu issuer/profile của ứng dụng yêu cầu `kid`.
2. **Chọn một khóa phù hợp duy nhất** từ trusted key set khi profile cho phép và không mơ hồ.
3. Thực hiện lựa chọn khác **chỉ khi** được profile/JOSE library hỗ trợ và bảo đảm không có key confusion.

Không dùng hành vi “thử mọi khóa từ mọi nguồn đến khi có một chữ ký khớp”.

### Khi token có `kid` nhưng không có khóa tương ứng

~~~text
JWT header:
  alg = PS256
  kid = signing-NEW

Verifier cache:
  kid = signing-OLD

Có thể là:
  - AS vừa rotate khóa;
  - cache đã hết hạn/chưa đồng bộ;
  - token đến từ issuer sai;
  - attacker đang gửi unknown kid để gây DoS.
~~~

Xử lý an toàn:

- Nếu cache policy cho phép, **refresh trusted JWKS có giới hạn**.
- Lọc theo issuer/alg/key purpose và thử verify lại **theo policy**.
- Nếu vẫn không thấy key hợp lệ, **từ chối**.
- Không tải `jku`/`x5u` lạ do header chỉ định.
- Không chuyển sang alg yếu hoặc bỏ kiểm tra signature để giảm tỷ lệ 401.

### Khi có duplicate `kid`

Nếu hai khóa **cùng phù hợp** tạo selection mơ hồ, nên **báo lỗi issuer/JWKS** và từ chối theo policy. Một verifier không được tự coi duplicate ID là cơ hội thử từng khóa tuỳ tiện cho tới khi có kết quả; cách vận hành tốt hơn là **sửa uniqueness ở key registry**.

## 9. Đặt `kid`: tên phiên bản, random ID hay fingerprint?

JOSE không bắt buộc một phương thức sinh `kid` duy nhất. Có ba nhóm phổ biến:

| Cách | Ví dụ | Ưu điểm | Rủi ro / lưu ý |
|---|---|---|---|
| **Version/label do issuer quản lý** | `signing-2026-11-v2` | Dễ audit và vận hành. | Tên có thể bị tái sử dụng/đánh sai; không được coi là secret. |
| **Random opaque ID** | `k_q7m9...` | Giảm khả năng trùng nếu CSPRNG/độ dài đủ. | Cần registry để map tới key material và lifecycle. |
| **Public JWK thumbprint** | Base64URL của digest theo RFC 7638. | Gắn định danh với public-key parameters cụ thể. | Thuật toán canonicalization/hash phải đúng; không tự là chứng nhận issuer hoặc key usage. |

### Quy tắc lựa chọn thực tế

1. **`kid` không phải mật khẩu**: không cần giấu, không nên mang bí mật nội bộ.
2. Không chứa dữ liệu cá nhân (`email`, `sub`), private key hoặc token trong tên.
3. Không mặc định prefix `prod-` hoặc số version chứng minh key đang active.
4. Quản lý **mapping từ `kid` tới immutable key version**, không trỏ động tới alias bị đổi ngầm.
5. Nếu key material thay đổi, cấp **`kid` mới** để tránh cache giữ giá trị cũ.
6. Đảm bảo định danh hợp lệ với thư viện JSON/HTTP/log và không tạo đường đi đến filesystem, KMS hay database từ input chưa xác minh.
7. Thời gian sống của `kid` nên phản ánh **identity của key material**, không phản ánh tuổi của một JWT hoặc session.

### Ví dụ một bảng registry nội bộ

~~~yaml
# Pseudodata: registry nội bộ, không phải chuẩn OAuth/JOSE.
issuer: https://auth.example.test
key_records:
  - kid: signing-2026-09
    kms_key_version: kms-key-a-version-1
    use: sig
    algorithm: RS256
    status: verify_only
  - kid: signing-2026-11
    kms_key_version: kms-key-b-version-1
    use: sig
    algorithm: PS256
    status: active_signing
~~~

**Không công bố `kms_key_version`/quyền truy cập KMS trong JWT hoặc public JWKS chỉ vì registry nội bộ có trường đó**. Public `kid` có thể được trình bày theo tên opaque; map từ `kid` tới key material nằm ở issuer/key manager và được kiểm soát.

## 10. JWK thumbprint không phải tự động là `kid`

**RFC 7638** định nghĩa cách tính **JWK Thumbprint** từ một tập các thành phần công khai **bắt buộc** của JWK, sau khi canonical hóa đối tượng JSON theo trình tự và quy tắc được đặc tả, rồi hash (thường SHA-256) và mã hóa thích hợp khi cần.

Ví dụ khái niệm cho RSA public JWK:

~~~json
{
  "e": "AQAB",
  "kty": "RSA",
  "n": "<PUBLIC_MODULUS>"
}
~~~

Để tạo thumbprint, **không đơn giản hash toàn bộ chuỗi JSON JWKS**. RFC 7638 yêu cầu chọn **các trường public bắt buộc**, sắp xếp/tạo biểu diễn đúng chuẩn và hash bytes chính xác. Những metadata như `kid`, `use`, `alg`, `x5c` **không phải thành phần dùng để tính thumbprint RSA theo RFC 7638**.

### Phân biệt ba giá trị

| Giá trị | Dựa trên dữ liệu nào? | Khi nào dùng? |
|---|---|---|
| **`kid`** | Chuỗi ID do bên quản lý khóa chọn. | Key lookup trong đúng trust domain. |
| **JWK thumbprint (RFC 7638)** | Các thành phần JWK public bắt buộc theo canonicalization. | Fingerprint public key; có thể được chọn làm `kid`, hoặc dùng trong DPoP `cnf.jkt`. |
| **`x5t#S256`** | SHA-256 thumbprint của **chứng chỉ X.509 dạng DER**. | Liên kết với chứng chỉ trong JOSE/mTLS profile, không cùng nghĩa với JWK thumbprint. |

**Cùng một public key** có thể được bọc trong nhiều certificate X.509 khác nhau nên certificate thumbprints có thể khác, trong khi JWK thumbprint của cùng public-key parameters vẫn như nhau. Ngược lại, **hai khóa khác nhau không được cố tình gán cùng `kid`** chỉ vì cùng vai trò “signing”.

### Có nên dùng thumbprint làm `kid`?

Có thể nếu key manager/verifier thống nhất: nó giúp tránh vô tình giữ cùng ID cho **public key material khác**. Nhưng nó **không chứng minh khóa thuộc issuer tin cậy**, vì attacker cũng tính thumbprint cho khóa của chính mình. Vẫn phải lấy khóa từ **trusted registry/JWKS** và kiểm tra issuer/algorithm/key usage.

## 11. Sinh `kid` mới bằng Java

Với một registry do tổ chức quản lý, có thể tạo **opaque `kid` ngẫu nhiên** rồi ghi kèm metadata/phiên bản khóa. Ví dụ Java dùng `SecureRandom` tạo 16 byte (128 bit) và mã hóa Base64URL không padding:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class KeyIdentifierGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    private KeyIdentifierGenerator() {}

    public static String newKid() {
        byte[] idBytes = new byte[16];
        RANDOM.nextBytes(idBytes);
        return "k_" + Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(idBytes);
    }
}
~~~

### Giới hạn của ví dụ

- **Randomness nhằm giảm xác suất trùng**, không nhằm tạo một secret. `kid` được dùng công khai.
- 16 byte là **quyết định minh họa** cho không gian ID lớn; tổ chức có thể chọn format/length khác sau khi phân tích nhu cầu.
- Phải có **unique constraint/check** tại trusted key registry cho đúng namespace; nếu gặp collision thì tạo lại, không ghi đè khóa hiện hữu.
- **Sinh `kid` không sinh key pair**. Key material phải được sinh riêng trong KMS/HSM/keystore bằng CSPRNG và thuật toán/chính sách đã được duyệt.
- Một `kid` chỉ nên được **gán một lần cho một phiên bản khóa bất biến**, không thay vì rotation thì sửa lại public key dưới cùng ID.
- Đừng dùng `java.util.Random`, timestamp một mình, PID hoặc tên user làm security-sensitive identity; dù `kid` không bí mật, dễ trùng sẽ phá vận hành và key selection.

### Không cần hash private key

Không tạo `kid` bằng `SHA256(privateKeyBytes)` để rồi phải **xuất private key khỏi HSM**. Nếu muốn ID gắn với key material, dùng **public JWK thumbprint chuẩn RFC 7638**, hoặc gán opaque ID trong registry. Private key không cần ra khỏi nơi lưu chỉ để tạo tên khóa.

## 12. Phân biệt `kid` với KMS/HSM key ID, key version và alias

Một dịch vụ có thể giữ khóa trong **KMS/HSM** thay vì file private key. KMS có thể cung cấp:

~~~text
KMS key name/ARN:
  resource định danh một key object

KMS key version:
  phiên bản vật liệu khóa cụ thể

KMS alias:
  tên thân thiện có thể được remap sang key/version khác

JOSE kid:
  identifier công bố cùng JWT/JWK để chọn key phù hợp
~~~

Các khái niệm phụ thuộc nhà cung cấp; **không giả định chúng là một**. Một KMS có thể dùng nội bộ ID/version dài, còn JOSE `kid` ngắn cho public verifier.

### Bảng ánh xạ có chủ sở hữu

~~~text
AS Signing Registry
  issuer: https://auth.example.test
  jose_kid: signing-2026-11
  expected_alg: PS256
  expected_use: sig
  kms_key_ref: protected:kms/signing/key-B/version-3
  public_jwk_fingerprint: <APPROVED_PUBLIC_KEY_FINGERPRINT>
  status: active-signing
~~~

**Ánh xạ là dữ liệu vận hành nội bộ**, phải được phê duyệt, audit và không cho Client thay đổi. KMS key ARN/version có thể được giữ kín khỏi external JWKS dù không phải private key, để giảm phụ thuộc nội bộ và tránh lộ topology.

### Lỗi alias trôi

~~~text
Ngày 1:
  JOSE kid=signing-live
  KMS alias=current -> key-A

Ngày 30:
  KMS alias=current -> key-B
  JOSE kid vẫn signing-live

Verifier đã cache:
  kid=signing-live -> public key A

AS bắt đầu ký bằng key-B dưới cùng kid.
=> Verification failures hoặc selection mơ hồ.
~~~

**Không gắn `kid` với một alias mutable mà bỏ qua phiên bản vật liệu khóa**. Sau key rotation, dùng `kid` mới và công bố public JWK tương ứng; giữ key cũ trong JWKS theo cửa sổ overlap nếu vẫn có token hợp lệ.

### Tại sao không để verifier tự gọi KMS bằng `kid` từ token?

Một `kid` chưa tin có thể mang giá trị kiểu:

~~~text
../../prod/admin-key
arn:provider:kms:region:tenant:key/foreign
https://attacker.invalid/public-key
some-key?version=latest
~~~

Verifier không được dùng trực tiếp chuỗi này để **truy cập filesystem, KMS, database table, URL hoặc CLI** mà thiếu mapping/allowlist. Nếu cần tra registry, key lookup phải **theo issuer/purpose đã tin**, parameterized và giới hạn cardinality.

## 13. Khóa bất đối xứng và khóa đối xứng có cách nhận diện khác nhau

### JWS bất đối xứng

Với `RS256`, `PS256` hoặc `ES256`:

~~~text
AS:
  giữ PRIVATE signing key
  tạo JWS signature
  đặt kid của key pair đang dùng trong protected header

RP/RS:
  tải trusted PUBLIC JWKS
  chọn public key theo issuer + alg + kid + use
  verify signature
~~~

Public JWKS có thể được mọi người tải về; **private signing key không bao giờ nằm ở đó**.

### JWS đối xứng (HMAC)

Với `HS256`, các bên dùng cùng một shared secret để tạo và xác minh MAC. Điều này có hệ quả:

- Bên giữ HMAC secret để verify **cũng có khả năng ký token mới**.
- Một endpoint public JWKS **không được công bố secret `kty=oct`** để Client bên ngoài verify.
- `kid` của HMAC key vẫn có thể dùng trong **registry nội bộ** để chọn secret phù hợp.
- Key rotation và phân phối secret phải có kiểm soát, tránh dùng cùng secret giữa các issuer/Client hoặc môi trường thiếu lý do.
- Không dùng RSA public key dưới dạng HMAC secret chỉ vì JWT header khai `alg=HS256`.

### So sánh

| Câu hỏi | Asymmetric signature | HMAC signature |
|---|---|---|
| Bên xác minh cần gì? | Public key. | Shared secret. |
| Có thể công bố verification material? | Thường có với public key. | **Không**, vì secret cũng dùng để ký. |
| `kid` có phải secret? | Không. | Không. |
| Có thể dùng JWKS public? | Có, công bố public JWK phù hợp. | Không công bố `oct` secret trên public endpoint. |
| Key bị lộ nguy hiểm ra sao? | Lộ private key cho phép ký giả; lộ public key là bình thường. | Lộ shared secret cho phép ký giả. |

Khi hệ thống có nhiều Resource Server độc lập, mô hình AS ký bất đối xứng và RS chỉ giữ public key thường dễ quản lý **ranh giới quyền ký** hơn việc chia HMAC secret cho mọi RS.

## 14. `kid` ở OIDC ID token và JWT access token

Một Authorization Server/OpenID Provider có thể dùng **cùng key pair** ký nhiều loại JWT, nhưng việc nhìn thấy cùng `kid` **không cho phép đổi mục đích token**.

### ID token

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "shop-web",
  "iat": 1893456000,
  "exp": 1893456600,
  "nonce": "<NONCE_OF_ORIGINAL_OIDC_REQUEST>"
}
~~~

ID token dành cho **Relying Party có `client_id=shop-web`**. RP phải xác minh signature/key cùng `iss`, `aud`, `exp`, `iat`, `azp` và `nonce` nếu áp dụng theo OIDC profile, không tạo session chỉ vì `kid` hợp lệ.

### JWT access token

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "client_id": "shop-web",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893456600,
  "jti": "access-token-xyz"
}
~~~

Access token ở ví dụ dành cho **Orders API**, không phải cho RP tạo session. Nếu sử dụng **RFC 9068 JWT Profile for OAuth 2.0 Access Tokens**, verifier phải xử lý token type (`typ=at+jwt` hoặc dạng tương đương theo profile) và claims bắt buộc. RS cũng kiểm tra audience, scope và quyền owner/tenant.

### Cả hai có `kid=signing-2026-11` thì sao?

~~~text
ID token:
  header: alg=PS256, kid=signing-2026-11
  audience: shop-web

Access token:
  header: alg=PS256, kid=signing-2026-11, typ=at+jwt
  audience: orders-api

Orders API:
  chỉ nhận đúng access-token profile + aud=orders-api
  REJECT ID token dù alg/kid/signature đều đúng.
~~~

**Key reuse không đồng nghĩa token interchangeability**. Nếu có thể, thiết kế key/typ/issuer/audience riêng theo token profile giúp giảm cross-JWT confusion, nhưng **chính sách xác minh token type vẫn bắt buộc**.

### Opaque token và refresh token

- **Opaque access token:** không có JWS header để RS đọc `kid`. RS kiểm tra qua introspection/trạng thái tin cậy theo hợp đồng.
- **Refresh token:** thông thường là chuỗi AS quản lý; nếu được biểu diễn dạng JWT nội bộ thì key ID có thể phục vụ AS, **không phải quyền gọi API**.
- **Authorization code:** không phải access token và không cần mang JOSE `kid` trong giao diện browser.
- **PKCE `code_verifier`:** không phải signing key và không được dùng làm `kid`.

## 15. Client authentication bằng `private_key_jwt`

Một OAuth confidential Client có thể xác thực với AS tại token endpoint bằng **Client assertion JWT** thay vì gửi client secret.

~~~text
Client billing-worker:
  private key K-client
  kid=client-billing-key-3
  ký JWT assertion.

AS:
  biết client_id=billing-worker
  có public keys đã đăng ký cho billing-worker
  chọn đúng key theo issuer(Client)/registration + kid
  verify assertion, aud/iss/sub/exp/jti theo profile.
~~~

### Header và payload minh họa

~~~json
{
  "alg": "PS256",
  "kid": "client-billing-key-3",
  "typ": "JWT"
}
~~~

~~~json
{
  "iss": "billing-worker",
  "sub": "billing-worker",
  "aud": "https://auth.example.test/oauth2/token",
  "iat": 1893456000,
  "exp": 1893456060,
  "jti": "assertion-unique-abc"
}
~~~

**Không dùng OP JWKS thay cho Client key registration**. Đây là hai quan hệ khác nhau:

| Việc xác minh | Bên ký | Nguồn key mà verifier được tin |
|---|---|---|
| RP xác minh ID token | OP private signing key. | **OP JWKS** và OIDC trust. |
| RS xác minh JWT access token | AS private signing key. | **AS JWKS**/trusted key set của issuer. |
| AS xác minh `private_key_jwt` | Client private key. | **Public key/JWKS đã đăng ký cho đúng Client**. |

Nếu Client A và Client B cùng dùng `kid=key1` nhưng khóa khác nhau, AS phải namespace theo **registered client ID** và key store tương ứng. Đừng tạo một global `kid` map khiến Client A được xác thực bằng public key của Client B.

### Rotation Client assertion key

Client có thể đăng ký công khai key mới `client-billing-key-4` trước khi bắt đầu ký assertions bằng private key tương ứng. AS chấp nhận hai khóa trong cửa sổ overlap có hạn, sau đó ngừng tin key cũ. Client registration, exact audience và replay protection **không biến mất** chỉ vì `kid` được thay.

## 16. DPoP: `kid`, JWK thumbprint và `cnf.jkt`

**DPoP (RFC 9449)** sử dụng một JWS proof do Client ký để chứng minh khả năng sử dụng private key gắn với request. Proof header có thể chứa **public JWK**; key ID (nếu xuất hiện) không thay thế xác minh key binding.

### DPoP proof minh họa

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

Payload proof có thể chứa:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.test/orders",
  "iat": 1893456000,
  "jti": "dpop-proof-one-time-id",
  "ath": "<ACCESS_TOKEN_HASH>"
}
~~~

**Khác biệt quan trọng:**

1. **`kid` trong JWS header** (khi được profile cho phép) chỉ gợi ý khóa; **không phải giá trị key binding** của DPoP access token.
2. **`cnf.jkt`** trong access token DPoP-bound chứa **JWK thumbprint** theo RFC 7638 của public key được ràng buộc.
3. RS xác minh chữ ký proof, đúng `htm`/`htu`/`iat`/`jti`/`ath` và nonce khi yêu cầu.
4. RS phải **so khớp thumbprint của public JWK proof với `cnf.jkt`** của access token đã được xác minh.
5. Một proof có chữ ký hợp lệ do **key bất kỳ của attacker** tạo **không chứng minh** attacker được phép dùng token DPoP-bound của người khác.

### Vì sao dùng thumbprint chứ không chỉ `kid`?

Hai Client có thể tự chọn cùng `kid=key1`. Key ID dễ trùng và không nhất thiết gắn với key material. **JWK thumbprint phản ánh những tham số public key cụ thể**, phù hợp với mục tiêu xác định key sở hữu proof theo DPoP. Tuy nhiên, thumbprint không tự chứng minh người cầm key đã được cấp đúng audience/scope; vẫn cần AS binding và RS authorization.

### Key rotation DPoP

Nếu Client tạo DPoP key pair mới, thumbprint thay đổi. Token đã được ràng buộc với key cũ **không mặc nhiên** có thể sử dụng bằng proof của key mới. Thường cần lấy token mới ràng buộc key mới, quản lý refresh-token binding theo profile và revoke/session cleanup khi cần.

## 17. mTLS certificate thumbprint khác `kid`

Với **certificate-bound access token (RFC 8705)**, AS có thể ghi thông tin binding vào claim `cnf`:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": "orders-api",
  "cnf": {
    "x5t#S256": "<BASE64URL_SHA256_CERT_THUMBPRINT>"
  }
}
~~~

Ở đây `x5t#S256` nhận diện **chứng chỉ Client được ràng buộc**, không phải tên signing key của AS. Một JWT vẫn có thể có:

~~~text
JWT header kid = as-signing-key-B
JWT payload cnf.x5t#S256 = hash certificate Client C
~~~

RS phải xác minh **chữ ký access token bằng public key AS** và **certificate presenter binding** theo mTLS profile. **`kid` của AS không chứng minh Client đang giữ private key của chứng chỉ C**.

### Ba vòng đời khác nhau

- **AS signing key**: phục vụ phát hành/verify JWT, `kid` thường ở header.
- **Client mTLS certificate/key**: phục vụ TLS client authentication và sender binding.
- **Access token**: credential được phát cho Client/resource/scope, có `exp` và có thể `cnf`.

Đổi một thành phần không tự cập nhật hai thành phần còn lại. Khi Client thay certificate, token bound với certificate cũ có thể cần được cấp lại; khi AS đổi signing key, Client certificate có thể không đổi.

## 18. JWE key identifier: người nhận và khóa giải mã

Trong JWE, `kid` có thể nhận diện **recipient encryption key** để decrypt:

~~~text
Issuer gửi encrypted ID token tới Client shop-web:
  JWE header:
    alg=RSA-OAEP-256
    enc=A256GCM
    kid=shop-web-enc-key-v2

Client shop-web:
  chọn PRIVATE decryption key v2 từ local protected keystore
  thực hiện JWE decrypt + authentication tag verification
  nếu nested signed JWT -> verify lớp JWS bên trong theo profile
  validate iss/aud/exp/nonce và OIDC claims
~~~

**Không dùng `kid` của JWE recipient key để chọn AS signing key**. Nếu có nested JWT, lớp ngoài và lớp trong có thể có **hai protected headers và hai `kid` khác nhau**:

~~~text
Outer JWE kid = client-encryption-v2
Inner JWS kid = op-signing-v5
~~~

| Thành phần | Mục đích | Ai giữ private key? |
|---|---|---|
| **Outer JWE recipient key** | Mã hóa/giải mã cho người nhận. | Recipient/Client. |
| **Inner JWS signing key** | Bảo vệ tính toàn vẹn và xác thực issuer. | OP/AS. |

Với multi-recipient JWE JSON Serialization, các recipient có thể có metadata khóa riêng theo cấu trúc JOSE. Không suy rằng mọi `kid` trong một message đều trỏ về một key store. Thư viện JWE/JWS phải xử lý đúng protected header, critical parameters và chính sách lớp mã hóa/ký.

### Không nhầm encryption với signature

Giải mã JWE thành công **không tự chứng minh nội dung đến từ AS đáng tin**, trừ khi profile/cơ chế bảo vệ thực sự cung cấp xác thực nguồn cần thiết. Với encrypted ID token theo profile yêu cầu JWS bên trong, phải verify chữ ký bên trong rồi kiểm tra claims. **`kid` không thay phần xác thực nào**.

## 19. Planned key rotation: định danh phải thay cùng key material

Vòng đời quay khóa có kế hoạch thường gồm:

~~~mermaid
flowchart LR
    A["Sinh key pair B với kid B"] --> B["Công bố public JWK B bên cạnh A"]
    B --> C["Chờ JWKS cache/verifier biết B"]
    C --> D["AS bắt đầu ký JWT mới bằng private B, header kid B"]
    D --> E["Giữ public A khi JWT cũ ký bằng A còn hiệu lực"]
    E --> F["Ngừng ký A, chờ TTL + propagation phù hợp"]
    F --> G["Gỡ public A và retire private A"]
~~~

### Timeline minh họa

| Mốc | JWKS công bố | AS ký mới | Verifier chấp nhận | Lý do |
|---|---|---|---|---|
| **T0** | A. | A. | A. | Trạng thái ban đầu. |
| **T1** | A, B. | A. | A, B theo policy. | Verifier preload B. |
| **T2** | A, B. | B. | A, B. | Token mới dùng B; token cũ dùng A. |
| **T3** | A, B. | B. | A, B. | Chờ JWT A hết hạn và caches cập nhật. |
| **T4** | B. | B. | B. | Hoàn tất planned retirement A. |

**T4 không có thời gian cố định cho mọi hệ thống.** Cần xét access/ID token TTL, clock skew, cache directives, propagation, external RPs/RSs và token signing profiles. Đừng dùng “giữ A 24 giờ” như quy luật không có chứng cứ.

### Invariant quan trọng

~~~text
Signer active key material = private B
Signer JWS header kid      = kid B
Published JWKS key B       = public part của đúng private B
Verifier key selection     = issuer + kid B + allowed alg/key use
~~~

Nếu signer thực sự ký bằng B nhưng header vẫn mang `kid=A`, các verifier có thể báo invalid signature. Nếu public JWK B được xuất từ **sai key pair**, mọi token mới sẽ thất bại dù `kid`/algorithm trông chính xác.

### Khóa cũ còn nằm trong JWKS không có nghĩa được quyền ký token mới

Trong trạng thái **verify-only**, public key A còn được công bố để xác minh JWT đã phát. Chính sách signing service **không** được tiếp tục ký JWT mới bằng A. Cần phân biệt trạng thái:

~~~text
prepublished -> active_signing -> verify_only -> retired
                         \
                          -> compromised/revoked (không dùng overlap thường)
~~~

Nếu key A bị lộ, chuyển sang quy trình **emergency revocation**, không chờ T4 theo kế hoạch.

## 20. JWKS caching và unknown-`kid` refresh storm

RS/RP không nên gọi JWKS endpoint **mỗi khi nhận JWT**: độ trễ, phụ thuộc mạng và nguy cơ DoS đều tăng. Nhưng nếu cache bất biến, verifier có thể không nhận biết key mới khi AS rotate.

### Cơ chế cache hợp lý

~~~http
GET /oauth2/jwks HTTP/1.1
Host: auth.example.test
If-None-Match: "keys-v42"
Accept: application/json
~~~

~~~http
HTTP/1.1 304 Not Modified
ETag: "keys-v42"
Cache-Control: public, max-age=300
~~~

AS **có thể** hỗ trợ `ETag`/`Cache-Control` và các cơ chế HTTP cache, nhưng không bắt buộc mọi nhà cung cấp có cùng TTL. Verifier/library cần hiểu cache policy thực tế.

### Unknown `kid` không được gây mạng vô hạn

Attacker có thể gửi hàng nghìn token:

~~~text
kid=random-000001
kid=random-000002
kid=random-000003
...
~~~

Nếu mỗi token gọi một lần JWKS fetch, attacker gián tiếp gây quá tải AS/CDN và RP/RS.

| Biện pháp | Ý nghĩa |
|---|---|
| **Bounded refresh** | Chỉ refresh trusted JWKS theo thời gian/quota đã cấu hình. |
| **Single-flight** | Nhiều request cùng issuer/refresh window chia sẻ một công việc fetch. |
| **Negative cache ngắn** | `kid` không tồn tại tạm được nhớ để tránh fetch lặp ngay. |
| **Length/format limits** | `kid` quá dài/bất thường bị từ chối sớm và tránh log cardinality lớn. |
| **Key-set size limits** | Tránh JWKS khổng lồ hoặc parser/CPU memory exhaustion. |
| **Verified cache namespace** | Cache theo trusted issuer/key purpose, không global theo `kid`. |
| **Purge khi compromise** | Kênh khẩn cấp invalidate key cũ ngoài TTL thông thường. |

### Tình huống endpoint lỗi

~~~text
JWKS 503 + key đã cache và còn được policy tin:
  Có thể verify bằng cached key theo chính sách availability.

JWKS 503 + kid mới hoàn toàn:
  Không có public key tin cậy -> REJECT token.

JWT signature invalid:
  Không được chuyển sang decode-only/alg=none.
~~~

Với rủi ro cao, cần xác định **max cache staleness** và sự kiện **key compromise** có ưu tiên cao hơn availability. Chỉ xóa key khỏi JWKS trên server **không bảo đảm** các verifier đã dừng tin key nằm trong cache của họ.

## 21. `kid` injection, key substitution và các tấn công liên quan

Không có lý do hợp lệ nào để biến một `kid` chưa được xác minh thành **đường dẫn filesystem, tên collection SQL, URL tùy ý hoặc lệnh gọi KMS với quyền của server**.

### Các mô hình lỗi

| Lỗi | Cách attacker lợi dụng | Cách chống |
|---|---|---|
| **Filesystem path injection** | `kid=../../secrets/key.pem` được nối vào đường dẫn đọc public key. | Chỉ lookup qua registry đã chuẩn hóa và allowlist; không tạo path từ header. |
| **SQL injection** | Ghép `kid` thẳng vào câu truy vấn. | Parameterized query/ORM, giới hạn độ dài và namespace theo issuer. |
| **KMS key selector injection** | Dùng `kid` làm ARN/alias của khóa bất kỳ. | Mapping immutable `trusted kid → allowed key ref` với quyền tối thiểu. |
| **`jku` / `x5u` SSRF** | JWT yêu cầu tải key/cert từ URL attacker hoặc IP nội bộ. | Không follow URL ngoài trust policy; nếu profile cần, allowlist + TLS + SSRF defense. |
| **`jwk` header key substitution** | Token tự nhúng public JWK của attacker và được tin thay OP JWKS. | Không dùng attacker-provided key làm AS signing key; trừ profile cụ thể có proof/registration riêng. |
| **Duplicate `kid`** | Verifier chọn khóa mơ hồ theo thứ tự JSON. | Xử lý ambiguous selection như lỗi cấu hình, không chọn ngẫu nhiên. |
| **Unknown-`kid` flood** | Mỗi giá trị lạ kích hoạt fetch JWKS/KMS. | Bounded refresh, rate limit, single-flight, negative cache. |
| **`alg=none` downgrade** | Verifier bỏ chữ ký vì header tự khai không dùng alg. | Pin thuật toán ký theo token profile. |
| **RSA↔HMAC confusion** | Dùng RSA public key như HMAC secret với `HS256`. | Ràng buộc `alg`, `kty`, `use` và key material theo policy. |
| **Cross-issuer mix-up** | Token issuer B dùng key ID trùng issuer A. | Cache namespace theo trusted issuer và exact `iss` validation. |

### Ví dụ anti-pattern nguy hiểm

~~~text
function verify(jwt):
    kid = jwt.header.kid
    publicKey = readFile("/keys/" + kid + ".pem")
    return verifySignature(jwt, publicKey)
~~~

Đoạn trên sai vì `kid` do caller khai, không có issuer namespace, không kiểm tra algorithm/key purpose và đưa chuỗi chưa tin vào filesystem path.

### Cách tiếp cận an toàn

~~~text
function verify(jwt, trustedEndpointPolicy):
    issuer = trustedEndpointPolicy.expectedIssuer
    allowedAlgorithms = trustedEndpointPolicy.allowedAlgorithms
    allowedKeySet = verifiedKeyRegistry.getKeySet(issuer)

    header = parseLimitedJwsHeader(jwt)
    if header.alg not in allowedAlgorithms:
        reject
    key = allowedKeySet.findEligibleKey(
        header.kid, header.alg, requiredKeyUse="sig"
    )
    if key is missing or ambiguous:
        rejectOrBoundedRefreshFromTrustedSource
    require cryptoVerify(jwt, key)
    validateIssuerAudienceTypeLifetimeAndPermissions()
~~~

**Không thay anti-pattern bằng một đoạn regex đơn giản** rồi tin tất cả. Regex/length limits giúp giảm injection/DoS, nhưng **nguồn key, crypto verification và token-specific policy** mới là điều kiện quyết định.

### Header có `jku`/`x5u` là phải fail ngay?

Hành vi tùy profile. Với đa số OAuth/OIDC token validation phổ biến, verifier **không cần** fetch external `jku`/`x5u` từ token do Client gửi; có thể bỏ qua khi không liên quan hoặc từ chối theo chính sách strict. Nếu profile yêu cầu hỗ trợ, phải ràng buộc **đích URL, nguồn issuer, TLS, redirect, DNS/IP resolution và certificate/key association**. Dù chọn xử lý nào, header **không được tự mở rộng trust store**.

## 22. Khi private key lộ: thay `kid` không đủ

Giả sử private signing key A của AS bị xuất trái phép. Attacker có thể ký token mới bằng A và tự khai:

~~~json
{
  "alg": "RS256",
  "kid": "signing-A"
}
~~~

Nếu public key A vẫn được RP/RS tin, token giả **có thể có chữ ký toán học hợp lệ**. Xóa token local, thay `kid` trên signing service hoặc đổi tên `signing-A` thành `signing-B` mà không thay private key **không xử lý được lỗ hổng**.

### Quy trình sự cố

~~~mermaid
flowchart TD
    A["Phát hiện/nghi private signing key bị lộ"] --> B["Xác định issuer, key material, kid, token types bị ảnh hưởng"]
    B --> C["Khóa quyền ký/không xuất thêm token bằng key bị lộ"]
    C --> D["Tạo và kích hoạt key material mới an toàn + kid mới"]
    D --> E["Cập nhật JWKS và trust policy, thông báo verifier"]
    E --> F["Purge/invalidate cached compromised key"]
    F --> G["Đánh giá thu hồi/cấp lại token và grant liên quan"]
    G --> H["Test mọi RS/RP không còn nhận key cũ"]
    H --> I["Forensic/audit và sửa nguyên nhân gốc"]
~~~

### Hai sự kiện khác nhau

| Sự kiện | Điều cần làm | Điều không cần tự suy |
|---|---|---|
| **Lộ public JWK hoặc `kid`** | Thường không phải sự cố private key; public key vốn được công bố. Kiểm tra có vi phạm policy dữ liệu không. | Không cần revoke mọi token chỉ vì ai đó biết `kid`. |
| **Lộ private signing key hoặc HMAC secret** | Kích hoạt incident; stop signing, rotate/revoke key, invalidate caches/trust, rà soát token. | Không đủ nếu chỉ đổi tên `kid`. |

### Độ khó của revocation JWT

Nếu RS verify JWT offline, nó có thể tiếp tục dùng **public key A được cache** dù AS đã gỡ A khỏi JWKS. Cần có cơ chế **invalidate key cache/trust state khẩn cấp**, denylist, token state hoặc cắt TTL theo policy. **Không giữ A trong JWKS chờ token cũ hết hạn** trong kịch bản đã xác nhận private key bị lộ như thể đây là planned rotation.

### `kid` riêng cho signing key không tự thu hồi refresh token

Refresh token có thể là opaque credential được quản lý qua authorization grant và token family. Một sự cố lộ signing private key không đồng nghĩa mọi refresh token đã bị lộ, nhưng tổ chức phải đánh giá **issuer trust compromise** và có thể cần revoke sessions/grants theo mức độ. Ngược lại, **refresh token bị sao chép** không phải lý do mặc định rotate toàn bộ signing key của AS.

## 23. Multi-issuer, multi-tenant và nhiều miền khóa

Một hệ thống đa tổ chức có thể tin nhiều issuer:

~~~text
Orders tenant A:
  trusted issuer = https://auth.example.test/tenant-a
  JWKS A:
    kid=key-v2 -> publicKey A2

Orders tenant B:
  trusted issuer = https://auth.example.test/tenant-b
  JWKS B:
    kid=key-v2 -> publicKey B2
~~~

Hai issuer có thể dùng cùng `kid=key-v2`; điều này **không biến hai khóa thành một**.

### Cache key sai

~~~text
globalKeyCache[kid] = publicKey
~~~

Nếu key cache không namespace theo issuer, một token của tenant B có thể bị kiểm tra nhầm bằng khóa A, gây lỗi xác minh hoặc mở đường cho **key/issuer confusion** trong code lỗi.

### Cache/trust đúng hướng

~~~text
trustedKeySets[issuer][keyPurpose] = JWKS verified for issuer

trong từng key set:
  select by kid + alg + key type + use
~~~

### Một cấu hình nhiều issuer cần làm rõ

1. **Danh sách issuer** được phép đến từ policy/onboarding, không từ `iss` bất kỳ.
2. Token issuer phải khớp **chính xác** giá trị issuer được tin sau verify.
3. Token type, signing algorithms, audience và key sources có thể **khác nhau theo issuer**.
4. `kid` không thay **`tenant_id`** hoặc quyền data ownership.
5. Khi cùng một issuer có nhiều tenant dựa trên claims, cần thêm kiểm tra **tenant/resource/client context** sau signature.
6. Nếu server xác minh OIDC response từ nhiều AS, cần bảo vệ **authorization server mix-up** bằng state/issuer binding theo profile, chẳng hạn các biện pháp RFC 9207 khi phù hợp.
7. Không dùng `startsWith("https://auth.example.test")` thay exact issuer comparison.

### Ví dụ token có signature đúng nhưng sai tenant

~~~text
JWT (valid signature using kid=key-v2):
  iss = https://auth.example.test/tenant-a
  sub = user-123
  aud = orders-api
  scope = orders:read

Requested order:
  owner = user-999
  tenant = tenant-b

=> DENY nếu không có explicit cross-tenant authorization.
~~~

**`kid` là vấn đề tìm khóa; không phải vấn đề phân quyền object.** Cả khi issuer/key selection đúng, Resource Server vẫn phải kiểm tra quyền trên bản ghi và ngữ cảnh tài khoản.

## 24. Spring Security: JwtDecoder dùng trusted JWKS và kiểm tra audience

Trong Spring Security Resource Server, có thể cấu hình **issuer-based discovery** hoặc **trusted JWK Set URI**. Đoạn dưới minh họa một Orders API chỉ nhận JWT `RS256` từ issuer tin cậy với `aud=orders-api`.

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
class OrdersJwtKeySelectionConfig {
    private static final String TRUSTED_ISSUER =
            "https://auth.example.test";
    private static final String TRUSTED_JWKS =
            "https://auth.example.test/oauth2/jwks";
    private static final String ORDERS_AUDIENCE = "orders-api";

    @Bean
    JwtDecoder ordersJwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(TRUSTED_JWKS)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> expectedAudience = jwt -> {
            if (jwt.getAudience().contains(ORDERS_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                            "Unexpected access-token audience", null));
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER),
                expectedAudience));
        return decoder;
    }
}
~~~

### Tại sao không viết code `kid` lookup bằng tay?

Trong một JOSE library đáng tin, JWK selection dựa trên header, JWKS và compatible algorithm/key type được thực hiện theo các quy tắc được hỗ trợ. Ứng dụng có thể kiểm soát:

- **Nguồn JWKS**: URL được lấy từ trusted issuer/metadata hoặc cấu hình vận hành.
- **Allowed signing algorithms**: ví dụ chỉ `RS256` ở đây; không tự bật `HS256` hoặc `none`.
- **Issuer/audience validators**: phải đúng hợp đồng API.
- **Token profile checks**: nếu dùng RFC 9068 thì cần validator token type (`typ=at+jwt`), claims và policy tương ứng.
- **Scope/authority**: Spring có thể ánh xạ `scope` thành `SCOPE_...`, nhưng mapping phụ thuộc cấu hình.
- **Authorization nghiệp vụ**: controller/service vẫn phải kiểm tra quyền theo owner/tenant/object.

Đoạn trên **không minh họa trực tiếp API lựa chọn `kid`**, mà ủy quyền phần JOSE selection/crypto cho thư viện. Để kiểm thử `kid`, tạo token bằng các cặp khóa hợp lệ/không hợp lệ, thay key ID và kiểm tra kết quả request.

### Giới hạn ví dụ

1. Đây là mã minh họa phong cách **Spring Security 6**, cần dependency/version phù hợp.
2. `TRUSTED_JWKS` phải liên hệ đúng issuer đã được cấu hình; **không lấy từ `jku` hoặc `iss` chưa xác minh**.
3. `RS256` chỉ là algorithm được chọn trong ví dụ; nếu AS dùng PS256/ES256 cần change control và cấu hình tương ứng.
4. `JwtValidators.createDefaultWithIssuer` cung cấp một số validation mặc định; phần **audience** được thêm tường minh.
5. Cần **token type RFC 9068, scope/permissions, sender constraint, revocation state và object-level policy** tùy kiến trúc. Chữ ký hợp lệ không đủ.
6. Với **opaque access token**, dùng Resource Server opaque introspection, không dùng `NimbusJwtDecoder`.

### Khi issuer-based configuration phù hợp hơn

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Issuer-based configuration giúp framework tìm key source qua metadata được hỗ trợ, nhưng **không mặc định giải quyết mọi audience/token-type authorization**. Khi lựa chọn giữa issuer-based discovery và trusted hardcoded JWKS, cần kiểm tra hành vi startup/cache/version/rotation của framework thật.

## 25. Java: mô hình registry chống lựa chọn khóa mơ hồ

Một key registry nội bộ có thể quản lý **immutable key descriptors** để bảo đảm khi AS phát token, signing private key và `kid` thuộc đúng issuer/algorithm/purpose. Đây là **mô hình điều khiển policy**, không thay JOSE verifier hoặc KMS:

~~~java
import java.util.Map;
import java.util.Objects;

enum KeyLifecycleState {
    PREPUBLISHED,
    ACTIVE_SIGNING,
    VERIFY_ONLY,
    REVOKED,
    RETIRED
}

record SigningKeyDescriptor(
        String trustedIssuer,
        String kid,
        String algorithm,
        String keyUsage,
        String immutableKmsVersionRef,
        KeyLifecycleState state) {
    SigningKeyDescriptor {
        Objects.requireNonNull(trustedIssuer);
        Objects.requireNonNull(kid);
        Objects.requireNonNull(algorithm);
        Objects.requireNonNull(keyUsage);
        Objects.requireNonNull(immutableKmsVersionRef);
        Objects.requireNonNull(state);
        if (kid.isBlank() || kid.length() > 128) {
            throw new IllegalArgumentException("Invalid key identifier");
        }
    }
}

record SigningKeyLookup(String trustedIssuer, String kid) {}

final class SigningKeyRegistry {
    private final Map<SigningKeyLookup, SigningKeyDescriptor> keys;

    SigningKeyRegistry(
            Map<SigningKeyLookup, SigningKeyDescriptor> source) {
        this.keys = Map.copyOf(source);
        // Database/registry phải enforce uniqueness trước khi dựng map:
        // Map.copyOf không tự phát hiện entry trùng bị overwrite trước đó.
    }

    SigningKeyDescriptor requireActiveSigner(
            String configuredIssuer, String configuredKid,
            String expectedAlgorithm) {

        SigningKeyDescriptor key = keys.get(
                new SigningKeyLookup(configuredIssuer, configuredKid));

        if (key == null
                || key.state() != KeyLifecycleState.ACTIVE_SIGNING
                || !"sig".equals(key.keyUsage())
                || !Objects.equals(expectedAlgorithm, key.algorithm())
                || !Objects.equals(configuredIssuer, key.trustedIssuer())
                || !Objects.equals(configuredKid, key.kid())) {
            throw new IllegalStateException(
                    "No eligible configured signing key");
        }
        return key;
    }
}
~~~

### Những gì registry chưa làm

- Không sinh private key/không gọi KMS để ký; `immutableKmsVersionRef` phải được dùng trong một signing service đã kiểm soát.
- Không verify JWT signature; đó là trách nhiệm thư viện JOSE và trusted public-key store.
- Không đủ để enforce JSON Web Key `use`/`key_ops`, curve, key size, public-key fingerprint hoặc token claims.
- Không chứng minh một response từ KMS đã thực sự ký bằng **key version có public JWK khớp**; cần integration tests.
- Không xử lý trạng thái cập nhật đồng thời/DB transaction; production phải có uniqueness constraints, optimistic locking, change approval và audit.

### Một invariant cho issuer signing service

~~~text
activeSigningDescriptor.kid
    == JWS protected header kid

publicKey(activeSigningDescriptor.immutableKmsVersionRef)
    == public JWK in published trusted JWKS

signatureVerify(JWS, selected JWK from JWKS)
    == true
~~~

Đây là **điều kiện cần về mật mã/vận hành**. Access token vẫn phải được AS phát với `iss`/`aud`/`scope`/TTL đúng policy, và RS còn phải kiểm tra quyền trên dữ liệu.

## 26. Vận hành, audit và khôi phục sau sự cố

### Dashboard hữu ích cho key management

| Chỉ số/sự kiện | Giúp trả lời câu hỏi | Điều cần tránh |
|---|---|---|
| **JWT issued by issuer/profile/`kid`** | Signing service còn phát token bằng khóa cũ không? | Log raw JWT hoặc private key. |
| **JWT verification success by trusted key version** | RP/RS có nhận đúng public key mới? | Dùng `kid` của token chưa verify làm nhãn không giới hạn. |
| **Unknown `kid` rate** | Có rotation chậm cache hay attacker flood? | Refresh JWKS cho từng request. |
| **Invalid signature by issuer/profile** | Public key và private signing key có khớp? | Bỏ verify khi lỗi tăng. |
| **JWKS cache age / refresh errors** | Verifier có khả năng nhận khóa mới? | Coi stale key được tin vĩnh viễn. |
| **Duplicate `kid` alert** | Key registry/AS có xuất bản ID mơ hồ? | Chọn key đầu tiên trong array. |
| **Active key past retirement deadline** | Khóa/thuật toán cũ đã được loại? | Gia hạn vô hạn chỉ vì tương thích. |
| **Compromised `kid` still accepted** | Có verifier chưa purge key bị lộ? | Chỉ xem JWKS hiện tại mà bỏ cache ở RS. |
| **Signing KMS key version and public fingerprint** | Token được ký bằng key pair đúng như JWKS? | Xuất private material để so sánh. |
| **Unexpected issuer/key association** | Có cross-tenant key confusion? | Cache key global dựa trên `kid`. |

### Phân biệt log đã verify và log chưa verify

~~~json
{
  "event": "jwt.verification.failure",
  "trusted_issuer": "https://auth.example.test",
  "token_profile": "orders-api-access-token",
  "claimed_kid": "signing-2026-11",
  "claimed_alg": "PS256",
  "result": "rejected",
  "reason": "invalid_signature",
  "correlation_id": "jwt-check-20261123-42"
}
~~~

`claimed_kid` và `claimed_alg` ở đây **chỉ là header value chưa xác minh**; phải được escape, giới hạn độ dài và gộp bucket cho thống kê. Không đưa chuỗi `kid` chưa tin trực tiếp vào Prometheus label có cardinality vô hạn.

Sau khi verify thành công, có thể log **key version/fingerprint chuẩn do registry kiểm soát**, issuer/trust domain và kết quả claim validation theo chính sách quyền riêng tư. Không log toàn bộ JWT, refresh token, Authorization header, ID token, PKCE verifier, session cookie, client secret hoặc private key.

### Runbook khi token mới có unknown `kid`

1. Kiểm tra **issuer đã cấu hình** và khả năng token đến nhầm môi trường/tenant.
2. So sánh `kid` theo **metadata/JWKS trusted source**, không dựa vào URL header.
3. Kiểm tra AS signing key version, JWS `alg` và public JWK tương ứng.
4. Kiểm tra JWKS cache age/ETag, TTL và khả năng mạng; bounded refresh nếu policy cho phép.
5. Kiểm tra nhiều RS/RP có đang nhận key mới nhất quán không.
6. Nếu rollout AS quá sớm, khôi phục bằng **signing key vẫn an toàn và verifier đã sẵn sàng** theo change control; không bypass signature.
7. Nếu có bằng chứng compromise, dùng **runbook khẩn cấp**, không “quay lại khóa cũ” đã lộ.

### Disaster recovery và backup

- Khi restore AS/KMS, cần bảo đảm **`kid` → immutable key version → public JWKS** nhất quán với token đang lưu hành.
- Không phục hồi registry backup khiến **khóa đã bị revoke quay lại `active_signing`**.
- Nếu public JWKS nằm sau CDN, xác nhận cache purge và version consistency giữa regions.
- Thử **failover signing service** khi KMS region mất kết nối mà không ký token với key không có public JWK công bố.
- Cần kiểm soát quyền xuất private key và backup theo phân quyền, audit, HSM policy; không mở secret để xử lý lỗi 401.

## 27. Ma trận kiểm thử Key identifier

Giả sử AS tin cậy là `https://auth.example.test`, đang ký JWT access token cho `orders-api` bằng khóa B, `kid=signing-B`, `alg=PS256`; khóa A cũ chỉ còn verify trong planned overlap. Một ứng dụng OIDC có `client_id=shop-web`, Client assertion `billing-worker` có registry riêng. Các ca bên dưới yêu cầu **thực sự verify chữ ký và claims bằng thư viện**, không chỉ kiểm tra chuỗi header.

| # | Trường hợp | Kỳ vọng | Mục đích |
|---|---|---|---|
| 1 | JWT có `kid=signing-B`, chữ ký B hợp lệ, đúng issuer/audience | Tiếp tục kiểm tra type/scope/expiry và quyền dữ liệu. | Luồng chuẩn. |
| 2 | JWT có `kid=signing-B` nhưng chữ ký do private key A tạo | Từ chối. | `kid` không thay chữ ký. |
| 3 | JWT có `kid=signing-B`, signature giả và `scope=admin` | Từ chối. | Không tin payload tự khai. |
| 4 | JWT có `kid` đúng, `alg=none` | Từ chối nếu profile yêu cầu signed token. | Chống unsigned. |
| 5 | JWT khai `HS256` với public RSA key làm HMAC secret | Từ chối. | Algorithm/key confusion. |
| 6 | JWT khai `ES256` nhưng JWK thuộc `kty=RSA` | Từ chối. | Key type mismatch. |
| 7 | JWK `use=enc` được chọn verify JWS | Từ chối nếu policy không cho phép. | Key purpose separation. |
| 8 | JWK `key_ops` không cho `verify` | Từ chối dùng cho verify theo policy. | Key operation. |
| 9 | JWT header có `kid` không nằm trong JWKS cache | Refresh có giới hạn rồi reject nếu vẫn unknown. | Rotation/unknown key. |
| 10 | `kid` vắng mặt, profile bắt buộc có ID | Từ chối. | Profile enforcement. |
| 11 | `kid` vắng mặt, profile cho phép một key ứng viên duy nhất | Có thể verify theo policy nếu key/alg đúng. | Optional `kid`. |
| 12 | `kid` vắng mặt khi có nhiều key phù hợp gây mơ hồ | Từ chối/áp dụng profile an toàn. | Ambiguous selection. |
| 13 | JWKS chứa hai public signing keys cùng `kid` và `alg` | Không chọn tùy ý; báo cấu hình lỗi. | Duplicate detection. |
| 14 | Issuer A và issuer B cùng `kid=key-1` | Mỗi token chỉ dùng key của đúng issuer. | Cross-issuer isolation. |
| 15 | JWT có `iss` khác trusted issuer nhưng `kid` trùng | Từ chối. | Exact issuer matching. |
| 16 | JWT header `jku` trỏ tới host attacker | Không lấy làm trusted source. | Key substitution defense. |
| 17 | JWT header `x5u` trỏ IP nội bộ/cloud metadata | Không request URL không tin. | SSRF defense. |
| 18 | JWT nhúng public `jwk` của attacker | Không coi đây là AS signing key. | Trust-anchor enforcement. |
| 19 | `kid=../../secret/private.pem` | Không dẫn tới file read hoặc traversal. | Path injection. |
| 20 | `kid` chứa chuỗi SQL metacharacters | Lookup parameterized/giới hạn, không SQL injection. | Query safety. |
| 21 | `kid` chứa một KMS ARN của tenant khác | Không làm server truy xuất key ngoài registry. | KMS confused deputy. |
| 22 | `kid` dài hàng megabyte | Từ chối sớm, bounded parse/memory. | Resource exhaustion. |
| 23 | Attacker gửi hàng nghìn unknown `kid` khác nhau | JWKS refresh bị rate-limit/single-flight. | Cache-refresh DoS. |
| 24 | JWKS trả JSON quá lớn/nhiều keys | Bounded fetch/parse/reject. | JWKS resource limits. |
| 25 | JWKS gặp lỗi 503 khi key B cached còn hợp lệ | Dùng cache theo policy hoặc fail closed; không mở trust. | Availability policy. |
| 26 | JWKS 503 và token cần key C chưa biết | Từ chối. | No key, no verify. |
| 27 | Public key B đã công bố, signer vẫn ký A | JWT A tiếp tục được verify trong overlap. | Prepublication. |
| 28 | Signer bắt đầu ký B trước khi công bố B | Token mới bị từ chối; phát hiện rollout lỗi. | Migration ordering. |
| 29 | Signer dùng private B nhưng header ghi `kid=A` | Verify thất bại. | Signer/header inconsistency. |
| 30 | KMS alias chuyển A→B nhưng `kid` giữ nguyên | Test phát hiện public key mismatch. | Alias drift. |
| 31 | Ngừng ký A nhưng JWKS giữ A tới khi token cũ hết hạn | Token A còn hợp lệ có thể verify trong planned overlap. | Safe retirement. |
| 32 | Gỡ A sớm trước khi JWT A hết `exp` theo kế hoạch | Cảnh báo downtime, không bỏ signature. | TTL overlap. |
| 33 | Private key A bị lộ và vẫn cached ở RS | Purge/deny key theo incident; test RS từ chối. | Emergency revocation. |
| 34 | Kẻ ngoài biết `kid`/public key của AS | Không đủ ký JWT giả. | Public identifier semantics. |
| 35 | JWK thumbprint thay đổi khi public material đổi | Kiểm thử theo RFC 7638 đúng canonicalization. | Fingerprint correctness. |
| 36 | Metadata `alg`/`use` thay nhưng public key không đổi | Thumbprint theo RSA public key vẫn dựa trên mandatory members. | Thumbprint vs metadata. |
| 37 | Hai certificates chứa cùng public key nhưng chứng chỉ khác | Có thể khác `x5t#S256`, không nhầm `kid`/JWK thumbprint. | X.509 distinction. |
| 38 | JWT ID token `aud=shop-web` trình cho Orders API | Từ chối dù `kid`/signature hợp lệ. | Cross-token confusion. |
| 39 | Access token `aud=billing-api` trình Orders | Từ chối. | Audience validation. |
| 40 | Access token đúng `kid` nhưng hết `exp` | Từ chối. | Time validation. |
| 41 | Access token đúng `kid`, thiếu `orders:read` | Từ chối request đọc orders. | Scope enforcement. |
| 42 | Access token đúng mọi claim nhưng order thuộc tenant khác | Từ chối theo owner/tenant. | Object authorization. |
| 43 | Client assertion A và B dùng cùng `kid=key1` | AS dùng Client registration đúng, không dùng khóa Client khác. | Client-key namespace. |
| 44 | Client assertion có key đúng, `aud` token endpoint sai | AS từ chối. | Assertion claims. |
| 45 | DPoP proof có JWK hợp lệ nhưng không khớp `cnf.jkt` | RS từ chối. | Token-key binding. |
| 46 | DPoP proof có `jti` đã dùng lại | Từ chối theo replay policy. | Proof replay. |
| 47 | mTLS-bound access token `cnf.x5t#S256` không khớp chứng chỉ trình | Từ chối. | Certificate binding. |
| 48 | Outer JWE `kid` đúng recipient nhưng inner JWS signature sai | Từ chối nested JWT theo profile. | Encryption/signing separation. |
| 49 | Opaque access token được gửi vào JWT/JWKS verifier | Không decode như JWT; dùng introspection theo profile. | Token format separation. |
| 50 | Một node RS còn tin retired `kid` sau deadline | Phát hiện và sửa policy/cache ở node đó. | Consistent rollout. |
| 51 | Invalid JWT header có `kid` chứa ký tự điều khiển/log newline | Không được tạo log injection; sanitize. | Telemetry safety. |
| 52 | Đổi `kid` trong token mà không ký lại | Từ chối vì protected header/signature không khớp. | Header integrity. |

### Cách tổ chức kiểm thử

1. Chuẩn bị **test keys** riêng, không dùng private keys production trong CI.
2. Tạo token hợp lệ bằng thư viện JOSE uy tín; sửa header/ký sai có chủ đích **chỉ trong môi trường kiểm thử cách ly**.
3. Chạy qua **issuing service, metadata/JWKS endpoint, cache, RP/RS validation và token endpoint Client assertions** theo từng profile.
4. Đo **success/failure theo issuer/key version/alg**; tránh log raw JWT hoặc các giá trị `kid` chưa được chuẩn hóa thành metric label.
5. Mô phỏng **rotation, clock skew, cache expiry, JWKS outage, regional replication và key compromise**.
6. Kiểm tra **negative cases** trước, trong và sau khi planned key overlap kết thúc.
7. Xác minh **RS authorization sau crypto**, nhất là scope, audience, dữ liệu owner/tenant.
8. Nếu production dùng **Spring Security**, xác nhận bằng integration test phần framework thực sự kiểm tra `iss`/`aud`/`typ`/scope theo cấu hình; không coi một unit test decoder là đủ.

## 28. Tình huống tự luyện

**Tình huống A — `kid` hợp lệ, chữ ký giả.** JWT có `kid=signing-B` giống JWKS của AS, payload `sub=admin`, nhưng attacker tự tạo signature. API có nhận không?

**Giải thích:** Không. Tên khóa chỉ chọn public key B. Chữ ký phải được tạo bằng private key tương ứng và verify thành công; sau đó claims/audience/scope/quyền vẫn phải được kiểm tra.

**Tình huống B — Mọi issuer dùng `kid=key1`.** Hai OP công bố khóa khác nhau cùng tên `key1`. Một RS dùng global cache `cache[kid]`. Có vấn đề gì?

**Giải thích:** Có. `kid` chỉ có ý nghĩa trong trust domain/key set cụ thể. Cache phải gắn trusted issuer và purpose; không lấy khóa của issuer khác để xác minh.

**Tình huống C — Không có `kid`.** Một ID token ký đúng RS256 nhưng header không có `kid`. Có phải mặc nhiên không hợp lệ?

**Giải thích:** Không theo đặc tả JOSE chung vì `kid` tùy chọn. Nhưng **profile cụ thể có thể bắt buộc**; nếu không có ID, verifier phải có quy tắc an toàn lựa chọn khóa, thường chỉ chấp nhận khi không mơ hồ.

**Tình huống D — Trùng `kid` khi rotation.** AS công bố hai JWK có `kid=signing-live`, public keys khác nhau nhưng cùng `alg`. Verifier chọn bản ghi đầu tiên. Cần sửa gì?

**Giải thích:** Key management cần cấp ID mới cho key material mới, đồng thời verifier không được chọn key mơ hồ theo thứ tự. Có thể cần invalidate cache/điều phối chuyển tiếp nếu đã phát token sai.

**Tình huống E — KMS alias đổi mà JOSE ID không đổi.** Alias `current` chuyển key-A sang key-B, nhưng JWT header tiếp tục `kid=A`. Vì sao API trả 401?

**Giải thích:** Key B ký token nhưng verifier dùng public key A theo `kid=A`, signature không khớp. Signing registry phải dùng immutable KMS version → đúng `kid` → đúng published public JWK.

**Tình huống F — Dùng thumbprint làm `kid`.** Team tính SHA-256 trên chuỗi JSON JWK có cả `alg`/`use`/`kid`, rồi gọi đó là RFC 7638 thumbprint. Đúng không?

**Giải thích:** Không. RFC 7638 yêu cầu chọn đúng các mandatory public JWK members và canonicalization/serialization chuẩn. Dùng thư viện chuẩn, không hash JSON tùy ý.

**Tình huống G — Lộ `kid`.** Developer thấy log chứa `kid=signing-B` và đề nghị rotate signing private key vì “ID khóa đã lộ”. Có cần không?

**Giải thích:** Thông thường không; `kid` vốn là public identifier. Chỉ cần xử lý key compromise nếu có bằng chứng **private material** bị lộ hoặc policy khác bị vi phạm.

**Tình huống H — Private key bị lộ.** Team đổi `kid=A` thành `kid=B` nhưng giữ nguyên private key. Đã khắc phục chưa?

**Giải thích:** Chưa. Attacker vẫn ký được bằng private key cũ nếu verifier tin public key tương ứng. Cần key pair mới, trust/cache invalidation và xử lý tokens đã phát.

**Tình huống I — Unknown ID gây DoS.** Attacker gửi một triệu JWT với `kid=random-...`; RS fetch JWKS mỗi lần. Làm gì?

**Giải thích:** Rate-limit/negative cache/single-flight JWKS refresh theo trusted issuer, giới hạn header/key IDs, và từ chối khi không có key hợp lệ. Không bỏ signature để giữ availability.

**Tình huống J — Token ID gọi Orders API.** ID token và access token dùng cùng `kid` và key pair. ID token có `aud=shop-web`. Orders có thể nhận không?

**Giải thích:** Không. Orders yêu cầu access token đúng token profile và audience của API. `kid`/signature hợp lệ chỉ chứng minh lớp mật mã, không thay token purpose.

**Tình huống K — Client assertion sai registry.** Client A gửi `private_key_jwt` mang `kid=client-1`, AS dùng key của Client B vì cùng `kid`. Vì sao sai?

**Giải thích:** AS phải tìm keys trong **registration của Client A** và kiểm tra claims của assertion. `kid` không xác định Client toàn cục.

**Tình huống L — DPoP proof ký đúng bằng khóa của attacker.** Attacker có access token DPoP-bound của nạn nhân nhưng không có private key tương ứng, tự tạo proof key khác và `kid` giống tên của nạn nhân. Token có dùng được không?

**Giải thích:** Không nếu RS enforce DPoP đúng: so thumbprint của public JWK proof với `cnf.jkt` từ token và xác minh request proof. Đặt tên `kid` giống không làm thumbprint khớp.

**Tình huống M — JWE đã decrypt.** Client chọn đúng decryption key nhờ outer `kid`, giải mã thành JWT nhưng bỏ verify inner signature. An toàn không?

**Giải thích:** Không khi profile yêu cầu JWT được ký bên trong. JWE key selection/decryption và JWS signature verification là hai lớp riêng, cần validate các claims OIDC/OAuth sau đó.

**Tình huống N — Tái sử dụng `kid` đã retired.** Hai năm sau, AS đặt lại `kid=key-2024` cho một key khác vì “không còn token cũ”. Có nên?

**Giải thích:** Không khuyến khích. Caches/offline components/backups có thể còn mapping cũ; quản trị nhất quán hơn là cấp `kid` mới cho mỗi key material version.

**Tình huống O — Đã revoke grant nhưng key còn trong JWKS.** Một user disconnect app, JWT access token của user còn hạn. Có cần gỡ `kid` signing key khỏi JWKS?

**Giải thích:** Không. Gỡ signing key tác động mọi token ký bằng key đó. User-level revocation cần grant/token state, denylist/introspection/TTL theo kiến trúc.

**Tình huống P — Sai audience nhưng key đúng.** Một access token có `kid=B`, chữ ký đúng, `aud=billing-api`. Orders API có cho phép đọc đơn không?

**Giải thích:** Không. Orders phải kiểm tra `aud=orders-api` cùng scope, thời hạn, issuer, token type và quyền object/tenant.

## Checklist triển khai Key identifier

1. **Nhớ ý nghĩa:** `kid` là key-selection hint, không phải chữ ký, bí mật, định danh user hay quyền truy cập.
2. **Xác định trust anchor:** trusted issuer, Client registration và key source đã phê duyệt; không mở rộng từ URL/claim chưa verify.
3. **Chọn key đúng namespace:** issuer, token purpose, alg/key type/use, rồi `kid`; không global map theo `kid`.
4. **Quản lý uniqueness:** một `kid` đại diện một key material version; không trùng mơ hồ trong cùng key set, không reuse key ID khi rotate.
5. **Lựa chọn cách sinh ID:** nhãn quản trị, random opaque ID hoặc JWK thumbprint chuẩn RFC 7638; không tạo ID bằng private key.
6. **Phân biệt identifier:** `kid`, `jti`, `client_id`, `sub`, `iss`, `aud`, `cnf.jkt`, `x5t#S256` và KMS version có vai trò khác nhau.
7. **Giữ private key bí mật:** public JWK được công bố phù hợp, không có RSA/EC private parameters hoặc HMAC secret trong public JWKS.
8. **Pin thuật toán:** `alg` trong header chỉ được dùng khi nằm trong verifier allowlist của issuer/profile; không `none`/RS↔HS confusion.
9. **Kiểm tra key usage:** `kty`, `crv`, `use`, `key_ops` và `alg`/key size phù hợp.
10. **Chống injection/SSRF:** không dùng `kid` trực tiếp làm path/SQL/ARN; không fetch `jku`/`x5u` tùy ý, giới hạn độ dài/input.
11. **Làm rõ missing/duplicate/unknown `kid`:** chính sách không mơ hồ, refresh có giới hạn, reject khi thiếu key tin cậy.
12. **Thiết kế rotation:** publish new public JWK trước, ký bằng new key+new `kid`, giữ old key verify-only trong planned overlap phù hợp TTL.
13. **Thiết kế key compromise:** stop compromised signer, replace material, purge verifier caches/trust, revoke/reissue tokens khi cần.
14. **Cô lập client assertion keys:** `private_key_jwt` tìm khóa trong Client registration, không trong OP signing JWKS.
15. **Phân biệt DPoP/mTLS:** `cnf.jkt` và `cnf.x5t#S256` là sender bindings, không là AS `kid`.
16. **Phân biệt JWE/JWS:** outer `kid` có thể chọn recipient decryption key, inner `kid` chọn signing key; verify đúng các lớp.
17. **Quản lý KMS/HSM version:** mapping bất biến và audit được, không để alias trôi làm signing header/JWKS lệch.
18. **Cấu hình RP/RS đúng:** dùng JOSE library/Spring decoder, enforce trusted issuer, audience, type/profile, exp/nbf và scope.
19. **RS vẫn phân quyền:** object owner/tenant, business rules, sender proof và revocation state khi thiết kế yêu cầu.
20. **Vận hành không lộ credential:** log `kid`/alg được chuẩn hóa ở mức cần thiết, tránh high-cardinality và raw token/secret logs.
21. **Kiểm thử end-to-end:** rotate, duplicate/missing ID, unknown ID flood, invalid signature, key injection, multi-issuer, JWE/DPoP/mTLS, JWT/opaque distinction.
22. **Phân biệt hoàn thành kỹ thuật và kiểm định:** một JWKS trả 200 hoặc một `kid` có mặt không thay việc verify chữ ký và claims thật.

## Ghi nhớ

**Key identifier (`kid`) trả lời “dùng khóa nào?”, không trả lời “token có hợp lệ, đáng tin hoặc được quyền truy cập không?”.** Trong OAuth 2.0/OIDC, verifier phải bắt đầu từ **trusted issuer/Client registration**, lấy **key set đáng tin**, sử dụng `kid` như gợi ý chọn đúng JWK với thuật toán/loại khóa/mục đích tương thích, rồi **xác minh chữ ký hoặc cơ chế mật mã** trước khi tin claims. `kid` có thể trùng giữa các issuer, có thể vắng mặt theo JOSE profile và không là bí mật. Không nhầm nó với **`jti`, `client_id`, JWK thumbprint, certificate thumbprint, KMS key version hoặc sender binding**. Mỗi key material version mới nên có `kid` mới; rotation cần public-key prepublication và overlap có hạn, còn compromise cần cập nhật trust/cache khẩn cấp. Chống **unknown-`kid` DoS, path/SQL/KMS injection, `jku`/`x5u` SSRF, algorithm confusion và cross-issuer key mixing**. Dù `kid`/signature đúng, Resource Server vẫn phải kiểm tra **issuer, audience, token type, thời hạn, scope, revocation khi áp dụng và quyền trên từng dữ liệu/tenant**.

### Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS), Key ID header](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 — JSON Web Key (JWK), kid và key set](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication](https://www.rfc-editor.org/rfc/rfc7523)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [RFC 9207 — Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207)
- [OpenID Connect Discovery 1.0 — Provider metadata và jwks_uri](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0 — ID token validation](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP — JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [OWASP — OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
