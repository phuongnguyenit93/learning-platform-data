# Active và retired key

Khi Authorization Server (AS) ký access token JWT, không có nghĩa khóa ký đó phải tồn tại mãi mãi. Khóa có thể được thay định kỳ, bị thu hồi khẩn cấp khi lộ, hoặc hết thời gian được phép tạo chữ ký mới. Tuy nhiên, **dừng dùng một khóa để ký token mới không đồng nghĩa lập tức ngừng xác minh những token hợp lệ đã được ký bằng khóa ấy**.

Ví dụ, AS đang dùng khóa **K1** để ký JWT có thời hạn 15 phút. Lúc 10:00, AS chuyển sang **K2** để phát hành token mới. Một JWT được ký bằng **K1 lúc 09:59** vẫn có thể hợp lệ đến 10:14 (cộng leeway nếu chính sách cho phép). Nếu Resource Server (RS) xóa public key K1 khỏi kho tin cậy đúng 10:00, request hợp lệ sẽ bị từ chối. Ngược lại, nếu K1 đã **bị lộ private key**, tiếp tục tin mọi JWT ký bằng K1 chỉ vì “chưa hết thời gian overlap” lại có thể tạo rủi ro nghiêm trọng.

Vì thế, cần phân biệt:

- **Active key:** khóa được hệ thống chỉ định **sử dụng cho thao tác mới** theo vai trò, ví dụ AS được ký JWT mới bằng private signing key này.
- **Retired key:** khóa **không còn được dùng cho thao tác tạo mới** nhưng có thể được giữ để **xác minh hoặc giải mã dữ liệu cũ** trong một thời gian giới hạn và theo chính sách.
- **Revoked/disabled/compromised key:** khóa không còn được tin hoặc bị cấm sử dụng do rủi ro/chính sách; có thể cần ngừng cả việc xác minh, bất kể token còn hạn.
- **Destroyed key:** key material đã bị tiêu hủy theo quy trình, không thể dùng tiếp; phải tính đến backup, replicas, HSM và quy định retention.

Bài **“Active và retired key”** thuộc chương **Key management** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Bài kết nối quản lý khóa với vòng đời JWT/opaque access token, refresh token, OAuth 2.0/OIDC, kiểm `iss`/`aud`/`exp`/`scope`, phát hành, xác minh, thu hồi và phòng chống token theft/replay.

> **Nguyên tắc:** **Retire một signing key thường nghĩa là “ngừng ký mới, tiếp tục verify có điều kiện trong cửa sổ cần thiết”.** Nó **không** có nghĩa khóa đã bị compromise, và cũng **không** tự làm các JWT cũ bị revoke. Khi khóa lộ hoặc không còn đáng tin, phải dùng **emergency distrust/revocation** riêng, không áp máy móc lịch rotation thông thường.

## 1. Cần phân biệt hai chiều sử dụng khóa

Với **JWS JWT access token** dùng chữ ký bất đối xứng:

~~~text
Authorization Server (issuer)
  private signing key K1
         |
         | Sign(header.payload)
         v
  JWT có kid=K1
         |
         | Bearer token qua client
         v
Resource Server
  public verification key K1
         |
         | Verify signature
         v
  Kiểm iss, aud, exp, nbf, token type, scope,
  tenant, quyền trên tài nguyên và revocation
~~~

Khi AS ngừng **ký mới** bằng K1, RS vẫn có thể phải giữ **public verification key K1** để kiểm những JWT hợp lệ chưa hết hạn. Hai vai trò được tách bằng quyền sử dụng khóa:

| Hoạt động | Ai thực hiện? | Khóa cần dùng | Khi K1 vừa retired |
| --- | --- | --- | --- |
| **Ký JWT mới** | AS/issuer signing service | Private key K1 | **Không được tiếp tục** |
| **Xác minh JWT cũ** | RS/gateway | Public key K1 | **Có thể được phép** đến khi hết trust window |
| **Phát JWT mới bằng K2** | AS | Private key K2 | **Có**, khi K2 active và đã được chuẩn bị |
| **Xác minh JWT mới bằng K2** | RS | Public key K2 | **Có**, nếu RS đã lấy/trust K2 |
| **Kiểm tra quyền API** | RS | Claims + policy/state | **Luôn cần**, không phụ thuộc key active/retired |

**Không phải mọi phương thức dùng khóa đều có cách phân tách này.** Với HMAC/HS256, issuer và verifier dùng **chung secret**. Một verifier biết secret vẫn có khả năng tạo MAC hợp lệ. Với JWE, quy tắc có thể là **ngừng mã hóa mới bằng key cũ nhưng vẫn giữ quyền giải mã ciphertext cũ**. Cần xác định *key purpose* trước khi đặt trạng thái.

### 1.1. “Active” và “retired” là thuật ngữ lifecycle nội bộ

JOSE/JWK định nghĩa các trường như `kid`, `kty`, `alg`, `use` và `key_ops`, nhưng **không có một cờ chuẩn JOSE bắt buộc tên `status: retired`** áp dụng phổ quát cho mọi issuer. Trạng thái active/retired thường nằm trong **key registry, KMS/HSM metadata và deployment policy** của tổ chức.

Một key record nội bộ có thể chứa:

~~~yaml
kid: issuer-sign-2026-11
purpose: JWS_SIGNING
algorithm: RS256
issuer: https://auth.example.com
status: RETIRED
signing_stopped_at: "2026-11-23T03:00:00Z"
verify_until: "2026-11-23T03:20:00Z"
compromised: false
~~~

**Đây là schema minh họa, không phải một JWK public chuẩn.** Không công khai private key, thông tin KMS nhạy cảm hoặc internal lifecycle policy qua JWKS chỉ vì đối tượng quản trị có thể lưu YAML tương tự.

### 1.2. Trạng thái của key không phải trạng thái của token

Khóa K1 retired nhưng **một JWT được ký bằng K1** vẫn có thể:

- Hợp lệ: chữ ký đúng, còn hạn, đúng audience và policy cho phép key này verify.
- Không hợp lệ: hết hạn `exp`, sai issuer/audience, thiếu scope, token đã bị revoke.
- Phải bị chặn ngay: nếu K1 compromised và RS đã distrust K1.

**“JWT được ký bằng retired key” không tự đồng nghĩa “JWT invalid”.** Phải xem định nghĩa retirement và thời điểm hiệu lực của **verification trust**.

## 2. Vòng đời khóa đầy đủ

Một thiết kế vận hành rõ ràng thường tách các trạng thái sau:

| Trạng thái | Được ký/mã hóa dữ liệu **mới**? | Được verify/decrypt dữ liệu **cũ**? | Ý nghĩa |
| --- | --- | --- | --- |
| **CREATED / STAGED** | Chưa | Chưa hoặc chỉ trong test | Khóa đã sinh, được gắn identity/permissions |
| **PREPUBLISHED / PENDING** | Chưa | Có thể xuất public key cho RS nhận trước | Chuẩn bị phân phối trước cutover |
| **ACTIVE** | **Có**, theo policy | **Có** | Khóa hiện hành cho mục đích được cấp |
| **RETIRED / VERIFY_ONLY** | **Không ký mới** | **Có điều kiện**, đến trust deadline | Hỗ trợ token/ciphertext cũ |
| **DISABLED / REVOKED** | **Không** | **Không**, khi policy distrust | Dừng chấp nhận khóa |
| **DESTROYED** | Không | Không thể dùng key material | Kết thúc vòng đời theo quy trình |

**Một số hệ thống dùng tên khác:** `DEACTIVATED`, `ARCHIVED`, `SUSPENDED`, `COMPROMISED`, `DELETED`. Không ánh xạ trạng thái KMS thành “JWT còn hợp lệ” chỉ theo tên; cần biết chính xác **những crypto operations được cho phép**.

~~~mermaid
flowchart LR
    A["CREATED / STAGED"] --> B["PREPUBLISHED"]
    B --> C["ACTIVE<br/>sign new tokens"]
    C --> D["RETIRED<br/>verify old tokens"]
    D --> E["DISABLED / DISTRUSTED"]
    E --> F["DESTROYED"]
    C -. "Compromise / emergency" .-> E
    D -. "Compromise / emergency" .-> E
~~~

Trong sơ đồ, `br` trong nhãn chỉ trình bày; các **trạng thái là ví dụ thiết kế**, không phải các trạng thái được bắt buộc bởi RFC 7517.

### 2.1. Tại sao cần PREPUBLISHED?

RS có thể cache JWKS nhiều phút. Nếu AS ký token bằng K2 **trước khi RS tải public key K2**, RS sẽ thấy `kid=K2` chưa biết và có thể từ chối request hợp lệ. Do đó, **xuất bản public key K2 trước**, đợi thời gian phân phối/caching phù hợp, rồi mới chuyển signing key sang K2.

### 2.2. Tại sao cần RETIRED?

Token đã phát bằng K1 có thể còn hạn sau cutover. Retired K1 cho phép RS verify những JWT cũ **đến khi không còn token hợp lệ nào cần public key đó**, cộng margin theo time-skew/distribution policy.

### 2.3. Tại sao DISABLED khác RETIRED?

Khi private signing key K1 bị lộ, attacker có thể tạo chữ ký hợp lệ cho JWT giả. Giữ K1 trong tập trusted verification keys có thể tiếp tục chấp nhận token do attacker tạo. **Phải đánh giá emergency distrust**, kể cả gây invalidation rộng, thay vì coi compromised key chỉ là một retired key bình thường.

### 2.4. Có cần lưu private key của retired signing key?

Để **Resource Server verify JWS bất đối xứng**, chỉ cần **public key** K1. Về nguyên tắc AS có thể ngừng/khóa quyền **sign** của private key K1 sau cutover; không cần phân phối private key K1 cho verifiers. Việc archive/destroy private key phải tuân quy trình KMS/HSM, backup/forensics và an toàn, nhưng **không phải điều kiện để giữ public verification capability**.

## 3. Ví dụ thời gian: chuyển active K1 sang K2

Giả sử:

~~~text
Issuer: https://auth.example.com
Audience: https://api.example.com/orders
JWT access-token lifetime tối đa: 15 phút
Clock leeway tối đa tại RS: 60 giây
Signing key K1: RS256, kid=issuer-sign-1
Signing key K2: RS256, kid=issuer-sign-2
~~~

Một lịch chuyển khóa minh họa:

| Thời điểm | AS làm gì? | RS cần làm gì? |
| --- | --- | --- |
| **09:40** | Sinh K2; đưa public K2 vào trusted JWKS | Bắt đầu có thể discover/refresh K2 |
| **09:50** | K1 vẫn ACTIVE; K2 PREPUBLISHED | Có thể verify tokens ký K1, đã biết K2 |
| **10:00** | Dừng ký K1, bắt đầu ký K2 | Chấp nhận JWT hợp lệ ký **cả K1 và K2** |
| **10:14** | K1 không ký mới | JWT K1 phát 09:59 còn có thể hợp lệ |
| **10:16** | K1 đã hết cửa sổ token/clock policy trong ví dụ | Có thể ngừng tin K1 theo runbook và phân phối |
| **Sau cutover** | K2 ACTIVE, K1 retired/disabled theo policy | Chỉ tiếp tục nhận keys có trust state phù hợp |

**Mốc 09:40 và 10:16 chỉ là ví dụ**, không phải số phút chuẩn cho mọi AS. Nếu access-token max lifetime là một giờ, có refresh JWT profile riêng, hoặc có consumer offline, cửa sổ phải tính lại.

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS/CDN
    participant RS as Orders Resource Server
    AS->>JWKS: Publish public K1 + K2 (K2 chưa sign)
    RS->>JWKS: Refresh keys, có K1 + K2
    Note over AS: Cutover: K2 ACTIVE, K1 RETIRED
    AS-->>RS: JWT mới: kid=K2
    RS->>RS: Verify bằng public K2
    Note over RS: Token cũ kid=K1 vẫn có thể chưa hết exp
    RS->>RS: Verify K1 + kiểm exp/aud/scope
    Note over AS,RS: Sau max old-token validity + margin
    AS->>JWKS: Stop publishing K1 theo policy
    RS->>RS: Distrust K1 theo lịch/refresh
~~~

### 3.1. Cách tính cửa sổ verify tối thiểu

Ký hiệu:

- \(T_{\text{stop}}\): thời điểm **cuối cùng** AS còn được ký bằng K1.
- \(L_{\max}\): lifetime lớn nhất của **tất cả token classes** có thể được verify bằng K1.
- \(\Delta_{\text{clock}}\): khoảng leeway/clock drift tối đa mà verifiers cho phép.
- \(\Delta_{\text{operations}}\): biên độ vận hành/phân phối được xác định theo SLA, nếu cần.

Một cách tính conservative:

\[
T_{\text{verify-until}} \ge T_{\text{stop}}
 + L_{\max} + \Delta_{\text{clock}}
 + \Delta_{\text{operations}}
\]

**Điều kiện:** AS không tiếp tục phát token bằng K1 sau `T_stop`; lifetime có upper bound được enforce; verifiers không cho phép tokens vượt `exp`; các consumers được liệt kê đầy đủ. Nếu điều kiện sai, công thức **không còn là bảo đảm**.

### 3.2. Phải dùng lifetime tối đa của token sử dụng khóa đó

Nếu K1 ký:

~~~text
Access token A: exp = issued + 15 phút
ID token I:     exp = issued + 60 phút
Client assertion C: exp = issued + 2 phút
~~~

thì không thể giữ K1 chỉ 16 phút nếu còn OIDC clients có thể verify ID token **trong 60 phút** và dùng **cùng signing key** cho các token classes. Tốt hơn là **phân tách keys theo purpose/token profile**; nếu không, phải tính validity horizon của **mọi loại thông điệp** còn cần verify.

**Refresh token** có thể là opaque hoặc JWT theo AS, và có lifecycle khác. Không tự suy rằng mọi refresh tokens đều dùng cùng JWS signing key hoặc đều có TTL 15 phút.

### 3.3. JWKS cache duration không phải token lifetime

`Cache-Control: max-age=300` nghĩa là client/cache có thể giữ JWKS khoảng 5 phút theo HTTP policy; nó **không** khiến access token có `exp` 15 phút kéo dài thành 20 phút. Tuy nhiên, caching tác động đến **khi nào RS biết K2 mới và khi nào RS ngừng tin K1 cũ**.

Hai thời gian cần quản lý **độc lập**:

1. Token validity horizon: `iat/nbf/exp`, token purpose và revocation.
2. Key distribution/trust horizon: prepublication, JWKS cache/refresh, emergency invalidation.

### 3.4. Đừng ký tiếp bằng K1 do một node cập nhật chậm

Trong AS nhiều instances, cutover phải bảo đảm **mọi signing nodes** đã chuyển K2 hoặc không còn cấp token bằng K1:

~~~text
AS node A: activeSigningKey=K2
AS node B: activeSigningKey=K2
AS node C: activeSigningKey=K1  <-- lỗi cấu hình / stale state
~~~

Node C có thể phát token K1 **sau** lúc operator tin rằng K1 retired, khiến JWT hợp lệ xuất hiện ngoài cửa sổ tính trước. Cần deployment coordination, signer-side policy, metrics `tokens_signed_by_kid` và kiểm chứng actual last issuance time.

## 4. `kid` và trust của public signing key

Trong **JWS protected header**, `kid` (*key ID*) thường giúp RS chọn public key thuộc issuer đã tin:

~~~json
{
  "alg": "RS256",
  "kid": "issuer-sign-2",
  "typ": "at+jwt"
}
~~~

RS có thể tải trusted JWKS:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "issuer-sign-1",
      "use": "sig",
      "alg": "RS256",
      "n": "<public-modulus-K1>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "issuer-sign-2",
      "use": "sig",
      "alg": "RS256",
      "n": "<public-modulus-K2>",
      "e": "AQAB"
    }
  ]
}
~~~

**Dữ liệu trên chỉ minh họa public JWKS.** Hai `n` là placeholders; signing private key không bao giờ được đưa vào JWKS public.

### 4.1. `kid` không xác thực issuer

`kid=issuer-sign-2` do JWT header cung cấp là **dữ liệu chưa tin cậy cho đến khi verify**. RS phải chọn khóa trong **registry/JWKS gắn issuer đã được cho phép** và theo algorithm/token profile. Attacker có thể tự tạo token mang cùng `kid`; chỉ verify bằng đúng key tin cậy mới có ý nghĩa.

### 4.2. `kid` không nên được tái sử dụng cho key material khác

Nếu K1 bị retired và K2 mới thay thế, dùng **kid mới** là cách vận hành đơn giản:

~~~text
K1 public key bytes => kid=issuer-sign-1
K2 public key bytes => kid=issuer-sign-2
~~~

Thay nội dung public key nhưng **giữ nguyên `kid`** có thể gây confusion giữa các JWKS caches, rollback và đồng bộ nhiều nodes. Đừng dựa vào key ID có thể bị tái sử dụng để xác định key version.

### 4.3. `kid` không nhất thiết duy nhất toàn cầu

Hai issuers khác nhau có thể có cùng `kid`. Namespace trust phải gồm **issuer + token purpose/profile + key ID** theo policy, không dùng một map `kid -> publicKey` chung cho mọi tenants/issuers mà không kiểm context.

### 4.4. Không tải `jku`/`x5u` tùy ý từ JWT header

Một token attacker tự ký có thể đặt:

~~~json
{
  "alg": "RS256",
  "kid": "my-own-key",
  "jku": "https://attacker.example/jwks.json"
}
~~~

Nếu RS tải JWKS theo `jku` **không nằm trong trust registry**, attacker có thể thay thế nguồn public key hoặc gây SSRF. Địa chỉ JWKS phải được **cấu hình/tìm từ metadata issuer đã tin**, không lấy từ unverified header như một chỉ thị cấp quyền.

### 4.5. `use` và `key_ops` không phải active/retired status

`use=sig` hoặc `key_ops=["verify"]` mô tả **mục đích/operation**, không phải thông báo “đây là key mới nhất”. Một retired key có thể tiếp tục xuất hiện với public `use=sig` để RS xác minh token cũ. Trạng thái signing-active nằm trong **AS key registry**; public JWKS một mình có thể không nói key nào **đang được AS dùng ký token mới**.

## 5. Signing-key lifecycle khác encryption-key lifecycle

Chủ đề active/retired không chỉ áp cho JWT signing:

| Khóa | ACTIVE thường làm gì? | RETIRED có thể làm gì? | Hạn lưu |
| --- | --- | --- | --- |
| **JWS issuer private key** | Ký JWT mới | Không ký mới; private key có thể bị vô hiệu/archived | Đến thời điểm destroy theo policy |
| **JWS issuer public key** | Xác minh JWS đang phát | Xác minh JWS cũ cho đến verify deadline | Đến khi không còn signed tokens hợp lệ cần key |
| **JWE recipient public encryption key** | Mã hóa content/CEK mới cho RS | Không tạo ciphertext mới bằng key cũ | Theo cutover contract |
| **JWE recipient private decryption key** | Giải mã JWE hiện hành | Giải mã ciphertext cũ còn hợp lệ | Theo ciphertext/token validity |
| **HMAC secret (HS256)** | Tạo và verify MAC | Có thể verify cũ, nhưng bên có secret vẫn tạo MAC | Cần kiểm soát đặc biệt về secret exposure |
| **At-rest KEK trong KMS** | Wrap DEKs/CEKs mới | Unwrap keys cũ để đọc backups/data | Có thể dài theo data retention, cần rewrap |
| **mTLS client key** | Chứng minh caller identity tại handshake | Certificate cũ có thể bị ngừng tin theo rollout | Theo certificate/registration policy |

### 5.1. JWE: retired nghĩa là decrypt-only

Giả sử AS mã hóa JWT cho Orders RS bằng public key `E1`. Khi RS chuyển sang key pair `E2`:

1. Đăng ký **public encryption key E2** với bên phát token.
2. Bên phát mã hóa **token mới** bằng E2 sau khi Orders RS sẵn sàng giải mã E2.
3. Giữ **private decryption key E1** đủ lâu để giải mã **JWE cũ còn hợp lệ**.
4. Sau khi token/ciphertext E1 hết vòng đời và chính sách cho phép, ngừng giải mã và hủy/archive E1 theo quy trình.

**Không mang nhầm signing-key rule:** public signing key retired có thể giữ công khai để verify. Với JWE, private decryption key E1 là **bí mật cực kỳ nhạy cảm**, giữ lại là giữ tiếp khả năng giải mã dữ liệu cũ; cần access control, KMS/HSM và delete policy nghiêm ngặt.

### 5.2. Dữ liệu at rest có retention lâu hơn JWT

Một KEK mã hóa dữ liệu backup có thể cần decrypt ciphertext nhiều năm sau, trong khi access token JWT hết hạn sau vài phút. Không dùng **JWT TTL** để suy deadline xóa encryption key dùng cho database/backups. Thay vào đó cần **rewrap/re-encrypt** dữ liệu dưới key mới trước khi destroy key cũ, hoặc chấp nhận dữ liệu cũ không thể giải mã theo retention policy.

### 5.3. HMAC/HS256 có rủi ro khác asymmetric signatures

Với HS256, issuer và mọi verifier có **cùng shared secret**. Khi key “retired cho ký mới nhưng còn verify”, việc chia shared secret cho verifier vẫn tạo **khả năng giả mạo MAC** nếu một verifier bị compromise. Không có cơ chế public-key-only verification thật sự. Trong hệ thống nhiều RS/trust domains, nên cân nhắc **asymmetric JWS signatures** để RS chỉ giữ public key và giảm blast radius.

## 6. Rotation bình thường: một giao thức chuyển trạng thái có thứ tự

Không nên triển khai key rotation như hai lệnh độc lập “tạo key mới” và “xóa key cũ”. Trong hệ thống phát hành/xác minh JWT phân tán, rotation là **quy trình phối hợp**:

~~~mermaid
flowchart TD
    A["Tạo K2, đăng ký issuer/alg/purpose"] --> B["PREPUBLISH public K2 tới trusted JWKS"]
    B --> C["RS refresh/prefetch K2; kiểm khả dụng"]
    C --> D["AS chuyển K2 thành ACTIVE signing key"]
    D --> E["K1 thành RETIRED / no-new-sign"]
    E --> F["Giữ public K1 cho tokens cũ còn hợp lệ"]
    F --> G{"Hết validity horizon và đạt checks?"}
    G -->|Chưa| F
    G -->|Có| H["Loại K1 khỏi trust set theo runbook"]
    H --> I["Archive/destroy key material theo policy"]
~~~

### 6.1. Bước 1 — Tạo key và xác định danh tính

AS tạo key pair hoặc yêu cầu KMS/HSM sinh key với:

- **Issuer/trust domain** rõ ràng.
- **Key purpose** riêng: JWS signing, JWE encryption/decryption, HMAC, mTLS…
- **Algorithm policy** đúng (ví dụ RSA-PSS/RS256/ES256), kích thước key phù hợp và crypto provider đã được duyệt.
- **Unique `kid`** trong key namespace, không dùng lại khi rotate.
- **Key custody:** ai có quyền sign, verify, rotate, disable, destroy và audit?

**Không tự tạo key bằng seed/timestamp** hoặc commit PEM private key vào Git/container image. Nếu cần HSM hoặc cloud KMS, quyền **sign** nên ở issuer service; Resource Server chỉ cần public verification keys.

### 6.2. Bước 2 — Prepublish public key K2

Đưa **public JWK K2** vào JWKS của **trusted issuer** khi K1 vẫn là active signing key. Nếu có CDN, proxy, RS caches, multi-region, cần đủ thời gian để K2 được tải về. Có thể dùng:

- `Cache-Control` và `ETag` phù hợp cho JWKS;
- Scheduled refresh/prefetch ở RS;
- Canary verification với test token được ký K2 trong môi trường phù hợp;
- Theo dõi tỷ lệ `unknown_kid` và `signature_invalid`.

**Không dựa vào “AS đã publish K2, RS chắc chắn đã biết”**: RS có thể đang dùng JWKS cache, offline, hoặc cấu hình sai issuer/JWKS URL.

### 6.3. Bước 3 — Chuyển signing key trên tất cả issuer nodes

Tại thời điểm cutover:

~~~text
Before cutover:
  ACTIVE_SIGNING_KID=K1
  published_verification_keys={K1, K2}

After cutover:
  ACTIVE_SIGNING_KID=K2
  published_verification_keys={K1, K2}
  K1.private.sign_permission=DISABLED
~~~

Đảm bảo:

1. Chỉ có một policy active signing key cho **đúng issuer/purpose** tại mỗi issuance transaction.
2. Issuer nodes không lấy signing key từ cache stale không bị giới hạn.
3. New tokens có `kid=K2`, signature thuộc private K2 và claims đúng.
4. Không có fallback âm thầm sang K1 nếu K2/KMS tạm lỗi.
5. Token issuance/audit có thể ghi **kid, issuer alias, token type và thời điểm** mà không log raw JWT.

**K1 retired phải được enforce tại signer**, không chỉ là nhãn trên dashboard.

### 6.4. Bước 4 — Retain public K1 trong overlap

Sau cutover, K1 bị cấm ký mới nhưng RS vẫn verify **JWT cũ, chưa hết hạn**. Lưu public key K1 trong JWKS/trust registry đến thời điểm đủ an toàn, với các giới hạn:

- Chỉ những token types/profiles sử dụng K1 theo issuer policy.
- Claims phải đúng `iss`, `aud`, `exp`, `nbf`, scope và resource authorization.
- Chỉ chấp nhận thuật toán nằm trong allowlist.
- Không có incident key compromise buộc distrust sớm.
- Không chấp nhận `exp` xa bất thường hoặc `iat` sau stop-signing theo policy nếu hệ thống có đủ thông tin để kiểm.

**Không cần và không nên tiếp tục dùng private K1 để phát JWT cho tới lúc hết overlap.**

### 6.5. Bước 5 — Loại K1 khỏi trusted verification

Chỉ sau khi xác định **không còn token hợp lệ được phép verify bằng K1**, operator mới lên lịch:

1. Ngừng publish public K1 trong JWKS theo policy.
2. Đẩy/cưỡng chế trust update khi yêu cầu.
3. Theo dõi RS đã cập nhật trust state; không suy tất cả node đã biết ngay.
4. Kiểm tra không có dịch vụ dựa vào K1 cho token khác (ID token, assertions, legacy clients).
5. Hủy/archive private key material khi retention/forensics cho phép.

**Không đồng nhất loại public key khỏi JWKS với hủy private key**. Hai đối tượng có thể có lifecycle và trách nhiệm vận hành khác nhau.

## 7. JWKS caching làm rotation thành bài toán phân tán

Public JWK thường được phân phối theo **JWKS URI** trong issuer metadata đáng tin. RS có thể tải key set qua HTTPS và cache:

~~~http
GET /.well-known/jwks.json HTTP/1.1
Host: auth.example.com
Accept: application/json
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300
ETag: "jwks-version-42"

{"keys":[{"kty":"RSA","kid":"K1","use":"sig","n":"...","e":"AQAB"},
         {"kty":"RSA","kid":"K2","use":"sig","n":"...","e":"AQAB"}]}
~~~

Các keys/values trong response trên chỉ mang tính mô phỏng, **không phải JWKS RSA có thể verify token thực**. Issuer thực tế có thể dùng URI khác và cache directives khác.

### 7.1. Publish mới quá muộn

~~~text
10:00:00 AS đưa K2 vào JWKS và bắt đầu sign K2
10:00:01 RS vẫn giữ JWKS cache trước 10:00:00, chỉ có K1
10:00:02 RS nhận JWT kid=K2 -> unknown kid
10:03:00 RS refresh cache, mới biết K2
~~~

Đây là **outage xác thực do key distribution**, không phải các JWT K2 “sai chữ ký”. Cách phòng: **prepublish K2 và kiểm nhận diện K2 trước cutover**.

### 7.2. Retire key quá sớm

~~~text
10:00:00 AS stop sign K1, start sign K2
10:00:01 AS xóa public K1 khỏi JWKS
10:01:00 RS refresh JWKS chỉ còn K2
10:01:01 Client gửi JWT K1 còn exp=10:15
10:01:01 RS không verify được K1 -> user bị 401
~~~

Đây là lỗi **retirement window**, trừ khi policy cố ý invalid tất cả tokens K1 vì incident. Rotation thường phải để K1 public verification key tồn tại đến khi old-token validity hết.

### 7.3. Unknown `kid` không được là lý do tắt verify

Khi RS nhận JWT với `kid` chưa thấy:

1. Kiểm format/size/header theo policy; không xử lý các URL tùy ý.
2. Nếu hợp lý, refresh **trusted JWKS URI** theo cơ chế bounded, rate-limited.
3. Tìm đúng issuer/key/algorithm sau refresh.
4. Nếu vẫn không có key hợp lệ, **từ chối token**.

Không:

~~~text
if unknown_kid:
    accept_unverified_jwt()   // NGUY HIỂM
~~~

Không tải `jku` từ unverified token, không thử mọi public key của mọi issuer. Đặc biệt phải giới hạn refresh khi attacker flood nhiều `kid` ngẫu nhiên để tránh **JWKS refresh DoS**.

### 7.4. Khi JWKS unavailable

Nếu public key **đã được RS tải và còn hiệu lực trong trust cache theo policy**, RS có thể tiếp tục verify offline theo cấu hình đã duyệt. Nếu RS không có key phù hợp, hoặc policy yêu cầu key revocation state mới nhất nhưng không lấy được, cần **fail closed** cho request tương ứng.

**Không gia hạn cache/trust vô hạn trong sự cố** khi có yêu cầu emergency distrust hoặc giới hạn key freshness. Phải phân biệt graceful outage của JWKS với trạng thái kompromat của key.

### 7.5. CDN, cache và đồng hồ

Cần theo dõi:

- `Cache-Control`, proxy behavior và stale cache semantics;
- Conditional GET/ETag khi hỗ trợ;
- `Last-Modified` nếu dùng, nhưng không coi timestamp là cryptographic proof;
- Timeouts/retries/backoff có giới hạn;
- Cache refresh jitter giữa nhiều RS instances;
- NTP và clock skew khi kiểm JWT `exp`/`nbf`.

JWKS dùng HTTPS với certificate validation, hostname đúng và issuer trust. **Public key có thể công khai nhưng nguồn public key phải đáng tin**.

## 8. Retired key có làm token hợp lệ đến vô hạn không?

**Không**, nếu RS luôn kiểm đúng token validity. Một public key có thể ở JWKS trong nhiều ngày nhưng JWT được ký bằng key đó vẫn phải bị từ chối khi `exp` đã qua, `aud` sai hoặc token bị revoke.

### 8.1. Bắt buộc kiểm `exp` và `nbf`

Với JWT:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": "orders-api",
  "scope": "orders.read",
  "iat": 1800000000,
  "nbf": 1800000000,
  "exp": 1800000900
}
~~~

RS phải từ chối sau `exp` theo clock skew policy, dù `kid` vẫn xuất hiện trong trusted JWKS. **Signature có thể hợp lệ mật mã mãi mãi; OAuth token không vì thế tồn tại mãi**.

### 8.2. Kiểm `iat` theo key activation window có ích nhưng không hoàn hảo

Hệ thống có thể đặt policy:

~~~text
Token signed with K1:
  iat must be within allowed K1 issuance window
  exp must be <= iat + maxTokenTTL
  token's aud/iss/type must be correct
~~~

Nếu issuer vô tình ký K1 sau cutover, checks này có thể phát hiện. Nhưng **đừng coi `iat` là bằng chứng không thể giả mạo thời điểm ký** khi attacker đã đánh cắp private K1: họ có thể ký JWT mới với `iat` **nằm trong quá khứ** và `exp` vẫn còn trong horizon. Cần xử lý key compromise bằng distrust/revocation, không chỉ dùng `iat` cutoff.

### 8.3. `exp` kéo quá xa phải bị từ chối

Nếu AS policy cho access token tối đa 15 phút, RS có thể enforce `exp - iat <= 15 phút` khi contract cho phép. Nếu chỉ kiểm token chưa hết hạn mà không giới hạn lifetime, attacker có compromised key có thể tạo JWT `exp` xa tùy ý. **Max-lifetime check giúp hardening nhưng không thay key compromise response**.

### 8.4. Retired verify key có thể vẫn tạo rủi ro tấn công

Một retired public key vẫn thuộc **trusted verification set** trong overlap. Nếu private K1 rơi vào tay attacker, họ có thể lợi dụng cửa sổ đó. Vì thế:

- Giữ overlap **đủ dùng nhưng không vô hạn**.
- Không làm các JWT cũ sống lâu hơn `exp` nhờ cache.
- Monitor tokens có `kid=K1` được xuất hiện **sau khi K1 retired**.
- Khi nghi ngờ compromise, chuyển sang incident response.

### 8.5. JWT key lifetime và revocation lifetime là hai chiều

Một JWT K2 active có thể bị revoke **ngay sau khi phát**. Một JWT K1 retired có thể vẫn được chấp nhận vì chưa hết hạn và chưa revoked. **Key rotation không thay access-token revocation**; RS phải kiểm denylist, introspection hoặc state theo security SLA nếu yêu cầu thu hồi sớm.

## 9. Emergency key compromise: không áp overlap thông thường

**K1 retired do lịch rotation** khác hoàn toàn với **K1 bị lộ private signing key**.

### 9.1. Kịch bản nguy hiểm

Attacker lấy private K1 từ một backup, có thể:

1. Ký JWT mới với `kid=K1`.
2. Tự đặt `sub`, `scope`, `aud`, `iat`, `exp` trong phạm vi validator cho phép.
3. Gửi JWT giả tới RS vẫn tin public K1 trong overlap.

Do signature hợp lệ với K1, RS không thể nhận biết JWT này **không do AS thật phát** chỉ từ chữ ký. Nó cần nguồn trạng thái cấp phát có quyền kiểm chứng, allowlist issued-token IDs, introspection hoặc **ngừng tin K1**.

### 9.2. Phản ứng khác rotation bình thường

~~~mermaid
flowchart TD
    D["Phát hiện private signing key K1 compromised"] --> A["Dừng sign bằng K1 tại tất cả issuer nodes"]
    A --> B["Chuyển sang key sạch K2/K3"]
    B --> C["Emergency distrust K1 ở mọi RS"]
    C --> E["Invalidate tokens ký K1 theo policy"]
    E --> F["Kiểm consistency/cache, ngăn bypass/partition"]
    F --> G["Audit, forensic, revoke grants khi cần"]
    G --> H["Rotate secrets/keys liên quan và cải thiện custody"]
~~~

**Không đợi đến cuối overlap K1** khi đã biết key bị compromise. Có thể cần dừng một số API để tránh chấp nhận token giả trên RS chưa nhận trạng thái distrust.

### 9.3. Không chỉ xóa K1 khỏi JWKS rồi tuyên bố an toàn

RS có thể đang cache K1. Ngay cả khi AS loại key khỏi JWKS, các nodes/regions chưa refresh vẫn có thể verify JWT giả. Cần:

- Control plane thông báo **force-distrust** hoặc phiên bản trust bundle mới;
- Xác minh per-RS/per-region acknowledgment;
- Cho nodes stale **fail closed** với đường API yêu cầu guarantee;
- Khi cần, network isolation/gateway blocking cho đến khi trust state mới được áp;
- Đo thời gian từ incident/commit đến request signed K1 thực sự bị chặn.

### 9.4. “Revoke all tokens signed by K1” có phạm vi lớn

Khác denylist một `jti`, distrust signing key K1 có thể vô hiệu **hàng triệu JWT hợp lệ** đã phát bằng K1. Cần kế hoạch **forced reauthentication/token refresh** cho legitimate clients, nếu có đường an toàn, và thông báo incident minh bạch. Nhưng **không được duy trì trust K1 nguy hiểm chỉ để tránh lỗi 401**.

### 9.5. Nếu chỉ lộ public key?

Với chữ ký bất đối xứng, **public verification key được thiết kế để công khai**. Việc biết public key không tạo khả năng ký JWT mới theo thuật toán an toàn. Sự cố là **private signing key lộ, trust registry bị thay thế hoặc algorithm/key confusion**, không phải đơn thuần client tải JWKS.

### 9.6. Nếu compromised là HMAC secret?

Với HS256/HS512, secret của issuer và verifier là **cùng một bí mật**. Lộ secret ở bất kỳ RS nào có thể cho attacker tạo MAC hợp lệ. Cần rotate secret, update tất cả verifiers và vô hiệu old-secret tokens theo incident policy; không thể “giữ old public verification key” vì **không có public-only verifier**.

## 10. Key retirement trong môi trường nhiều issuers và tenants

Một Resource Server có thể tin:

~~~text
Issuer A: https://auth-a.example.com
  kid=a-2026-10 (retired)
  kid=a-2026-11 (active)

Issuer B: https://auth-b.example.com
  kid=b-2026-10 (retired)
  kid=b-2026-11 (active)
~~~

Một tenant hoặc API có thể chỉ chấp nhận tokens của issuer A. Dù JWT của issuer B ký đúng, vẫn **không hợp lệ cho trust domain A**.

### 10.1. Định danh key cần đủ namespace

Một key registry an toàn tối thiểu ràng buộc:

~~~text
(trusted_issuer, token_purpose, kid, key_material_fingerprint)
~~~

Nên tách **JWS signing verification** khỏi **JWE decryption**, **client assertion**, **DPoP public key** và các token classes khác. `kid` có thể trùng giữa issuers, giữa phiên bản hoặc giữa loại key; không phải toàn cầu duy nhất.

### 10.2. Multi-tenant issuer và scope

Một JWT có `tenant_id=acme` từ issuer A không tự được phép xem orders của tenant Globex. Sau khi verify token bằng active/retired key, RS vẫn phải ràng buộc **user membership, scope và object ownership** với dữ liệu đáng tin.

### 10.3. Issuer discovery cũng có lifecycle

RS phải chọn **đúng trusted issuer/JWKS URI**, không dựa vào `iss` chưa verify như một lệnh tải URL tùy ý. Trong môi trường multi-issuer, có thể dùng allowlisted issuer registry rồi validate chính xác token against selected issuer. Không fan-out bearer JWT/opaque token tới nhiều endpoints ngoài trust policy.

## 11. Key status có cần xuất hiện trong JWT hay JWKS không?

Thông thường **không cần** nhúng `key_status=ACTIVE` vào JWT để kiểm key lifecycle. Vì JWT mang claims tại thời điểm phát hành, trường ấy sẽ **cũ đi** khi K1 retired. RS phải dựa vào trust set và policy hiện hành, không tin status tĩnh trong token.

### 11.1. Không dùng JWT claim để tự cho phép verify key

Sai:

~~~json
{
  "kid": "K1",
  "key_status": "ACTIVE",
  "sub": "user-42"
}
~~~

K1 có thể đã bị distrust ở RS, nhưng token cũ vẫn ghi `key_status=ACTIVE`. **Chữ ký hoặc claim của token không điều khiển được việc key đang có được tin hay không**.

### 11.2. Khi nào cần metadata status mở rộng?

Hệ thống có thể có **trusted control-plane API** phân phối danh sách key versions, effective windows, emergency distrust flags. Nếu làm vậy, phải xác minh **nguồn gốc, integrity, freshness, replay/rollback resistance** của chính control-plane data.

Không tự coi một property `retired=true` trong JWKS lấy từ URL attacker là authority. JWKS chuẩn chủ yếu phân phối **JWK key material/metadata**, không bảo đảm hỗ trợ internal status semantics.

### 11.3. Có phải JWT với `kid` không tồn tại là revoked?

**Không thể kết luận nguồn cơn chỉ từ một lỗi verify.** `unknown_kid` có thể do AS rotate quá sớm, RS cache stale, cấu hình issuer sai, hoặc token giả. Resource Server **phải từ chối request**, nhưng giám sát vận hành cần phân loại nguyên nhân thay vì tự gắn mọi lỗi là “user token bị revoke”.

## 12. Java 17: diễn giải active/retired bằng key-policy metadata

Ví dụ dưới đây không tự triển khai JWS. Nó thể hiện **quy tắc nội bộ** mà một issuer có thể dùng trước khi yêu cầu KMS/HSM ký:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public final class SigningKeyLifecyclePolicy {
    public enum State {
        STAGED, PREPUBLISHED, ACTIVE,
        RETIRED, DISABLED, DESTROYED
    }

    // Lưu metadata; KHÔNG chứa private key bytes.
    public record KeyVersion(
        String issuer,
        String kid,
        String algorithm,
        State state,
        Instant signFrom,
        Instant stopSigningAt,
        Instant verifyUntil,
        boolean compromised
    ) {
        public KeyVersion {
            Objects.requireNonNull(issuer);
            Objects.requireNonNull(kid);
            Objects.requireNonNull(algorithm);
            Objects.requireNonNull(state);
            Objects.requireNonNull(signFrom);
            Objects.requireNonNull(stopSigningAt);
            Objects.requireNonNull(verifyUntil);
            if (!signFrom.isBefore(stopSigningAt)
                    || verifyUntil.isBefore(stopSigningAt)) {
                throw new IllegalArgumentException(
                    "Inconsistent key lifecycle window");
            }
        }
    }

    /** Chỉ ACTIVE key trong issuance window mới được ký mới. */
    public static boolean maySign(KeyVersion key, Instant now) {
        return key.state() == State.ACTIVE
            && !key.compromised()
            && !now.isBefore(key.signFrom())
            && now.isBefore(key.stopSigningAt());
    }

    /**
     * Metadata gate minh họa cho verify; chưa xác minh chữ ký,
     * issuer, audience, exp hoặc JWT token type.
     */
    public static boolean mayVerify(KeyVersion key, Instant now) {
        boolean statusAllows =
            key.state() == State.ACTIVE
            || key.state() == State.RETIRED;

        return statusAllows
            && !key.compromised()
            && !now.isAfter(key.verifyUntil());
    }

    /** Không fallback sang RETIRED nếu không có đúng 1 active key. */
    public static KeyVersion selectForSigning(
            String trustedIssuer,
            Instant now,
            List<KeyVersion> keys) {
        List<KeyVersion> allowed = keys.stream()
            .filter(k -> k.issuer().equals(trustedIssuer))
            .filter(k -> maySign(k, now))
            .toList();

        if (allowed.size() != 1) {
            throw new IllegalStateException(
                "Expected exactly one active signing key");
        }
        return allowed.get(0);
    }
}
~~~

### 12.1. Minh họa K1 retired, K2 active

~~~java
import java.time.Instant;
import java.util.List;

var stop = Instant.parse("2026-11-23T10:00:00Z");
var now = Instant.parse("2026-11-23T10:05:00Z");

var k1 = new SigningKeyLifecyclePolicy.KeyVersion(
    "https://auth.example.com",
    "issuer-sign-1", "RS256",
    SigningKeyLifecyclePolicy.State.RETIRED,
    Instant.parse("2026-10-01T00:00:00Z"),
    stop,
    Instant.parse("2026-11-23T10:20:00Z"),
    false
);

var k2 = new SigningKeyLifecyclePolicy.KeyVersion(
    "https://auth.example.com",
    "issuer-sign-2", "RS256",
    SigningKeyLifecyclePolicy.State.ACTIVE,
    stop,
    Instant.parse("2027-01-01T00:00:00Z"),
    Instant.parse("2027-01-01T00:20:00Z"),
    false
);

assert !SigningKeyLifecyclePolicy.maySign(k1, now);
assert SigningKeyLifecyclePolicy.mayVerify(k1, now);
assert SigningKeyLifecyclePolicy.maySign(k2, now);

var active = SigningKeyLifecyclePolicy.selectForSigning(
    "https://auth.example.com", now, List.of(k1, k2));
assert active.kid().equals("issuer-sign-2");
~~~

Đây là **snippet minh họa sử dụng lớp trước đó**, không phải file Java độc lập có các biến ngoài ngữ cảnh. Nó kiểm chính sách **chọn khóa**, không phát JWT thực và không xác minh signature.

### 12.2. Các giới hạn của mẫu Java

1. `mayVerify` là **metadata gate**, không thay JOSE verifier của RS.
2. Public trust registry ở RS có thể **không đồng bộ cùng trạng thái** với AS key registry; phải thiết kế phân phối cập nhật.
3. Không cho `status=RETIRED` làm quyền ký thông qua logic phụ. Cần áp **KMS/HSM sign permission** độc lập.
4. `stopSigningAt` phải phản ánh actual last issuance khi tính verify deadline; deployment skew làm assumptions sai.
5. `mayVerify` không kiểm `exp`, `aud`, `iss`, `scope`, revocation. Chữ ký phải được kiểm **trước khi tin claims**.
6. Mẫu code dùng `Instant` UTC, nhưng không thể tự chứng minh clock không bị lệch hoặc rollback.
7. Nếu `compromised=true` hoặc state DISABLED, cả sign lẫn verify bị từ chối; production cần cơ chế **immediate propagation**.
8. Code không mô hình hóa JWE encryption/decryption hay symmetric HMAC secret; áp status theo đúng key purpose.

### 12.3. Chọn khóa phải fail closed

Nếu có **hai active signing keys cho cùng issuer/purpose**, đó có thể là lỗi control-plane. Không được “chọn phần tử đầu tiên từ database” một cách ngẫu nhiên. Nếu không có active key do KMS outage/rotation sai, **ngừng phát token mới** và báo lỗi, không fallback sang K1 retired để giữ uptime.

### 12.4. Kiểm token vừa ký trước khi trả client

Issuer có thể xác minh/kiểm soát output của signing service: `kid` đúng version, `alg` allowlist, `iss/aud/scope/exp` hợp lệ và JWS được tạo bằng private key đã cho phép. Không log full token chỉ để xác minh metrics.

## 13. Spring Security: public JWKS verification qua nhiều key versions

Với **Spring Boot 3 / Spring Security 6**, Resource Server có thể lấy public keys từ issuer JWKS để xác minh signed JWT. Một cấu hình cơ bản:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
~~~

Thư viện sẽ dùng issuer metadata/JWKs theo cách mà version của Spring hỗ trợ. Khi JWKS cùng lúc công bố K1 và K2, verifier thường có thể chọn key theo `kid` và policy, nhưng **không tự hiểu các trạng thái ACTIVE/RETIRED nội bộ của AS**.

### 13.1. Ràng buộc algorithm, issuer, audience

Ví dụ Java:

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
    private static final String EXPECTED =
        "https://api.example.com/orders";

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        List<String> audience = jwt.getAudience();
        if (audience != null && audience.contains(EXPECTED)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token",
                "Wrong access-token audience", null));
    }
}

@Configuration
public class OrdersJwtDecoderConfiguration {
    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://auth.example.com/oauth2/jwks")
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(
                    "https://auth.example.com"),
                new OrdersAudienceValidator()
            )
        );
        return decoder;
    }
}
~~~

**Điểm quan trọng:** Trong cấu hình này, **K1/K2 có thể cùng tồn tại trong trusted JWKS** và decoder verify signature theo key matching/policy. Nhưng Spring Security **không tự biết** K1 mới retired do AS UI đổi status nếu public JWKS/trust config chưa được cập nhật.

**Khi cấu hình custom decoder**, cần tiếp tục kiểm token type/profile `at+jwt` (khi dùng RFC 9068), scope, principal, tenant, ownership, max token lifetime và revocation theo contract. Không nghĩ signature thành công là đã hoàn tất authorization.

### 13.2. Phân quyền API là lớp riêng

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {
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

Code trên là **mẫu bảo mật routes**. Nó chưa kiểm tenant, row-level ownership, object permissions hoặc session revocation. K1 retired nhưng JWT vẫn đúng audience/scope và chưa hết hạn **có thể được nhận** theo overlap policy.

### 13.3. Không chọn `jwk-set-uri` theo token header

Sai:

~~~java
// Sai ý tưởng: chọn JWKS URL do attacker đưa trong JWT.
String jwksUri = untrustedJwtHeader.get("jku");
createDecoder(jwksUri).decode(rawToken);
~~~

Đúng: RS dùng **trusted issuer/JWKS configuration**. `kid` chỉ tìm trong key set tin cậy; không có quyền “mở rộng” key sources hoặc phá algorithm allowlist.

### 13.4. Retired key và library caches

Một số JWT verifiers refresh JWKS khi gặp `kid` chưa biết, một số chỉ refresh theo TTL, một số cache dữ liệu lâu hơn. **Không giả định cùng một cache behavior ở mọi phiên bản thư viện**. Phải test:

- Token mới `kid=K2` ngay sau cutover;
- Token cũ `kid=K1` trước `exp`;
- Token `kid=K1` sau trust withdrawal;
- JWKS unavailable;
- K1/K2 có cùng `kid` do cấu hình sai;
- Hàng nghìn token `kid` ngẫu nhiên gây refresh storm.

### 13.5. Emergency revoke key cần thay đổi trust state

Nếu K1 bị compromise, không thể chỉ đổi `signingActiveKid=K2` ở AS mà mong Spring RS lập tức từ chối K1. Cần force-refresh/clear trust cache, custom key-distrust gate, phiên bản security config mới hoặc cơ chế central validation đáp ứng SLA; **một số routes có thể phải fail closed** cho tới khi chứng minh keys đã được cập nhật.

## 14. Key registry và dữ liệu vận hành

Một schema registry nội bộ có thể lưu status, key purpose và thời gian. Ví dụ **PostgreSQL**:

~~~sql
CREATE TABLE signing_key_versions (
    issuer_id          TEXT NOT NULL,
    purpose            TEXT NOT NULL,
    kid                TEXT NOT NULL,
    algorithm          TEXT NOT NULL,
    kms_key_reference  TEXT NOT NULL,
    state              TEXT NOT NULL CHECK (
        state IN (
            'STAGED', 'PREPUBLISHED',
            'ACTIVE', 'RETIRED',
            'DISABLED', 'DESTROYED'
        )
    ),
    sign_from          TIMESTAMPTZ NOT NULL,
    stop_signing_at    TIMESTAMPTZ NOT NULL,
    verify_until       TIMESTAMPTZ NOT NULL,
    compromised        BOOLEAN NOT NULL DEFAULT FALSE,
    state_version      BIGINT NOT NULL DEFAULT 0,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (issuer_id, purpose, kid),
    CHECK (stop_signing_at > sign_from),
    CHECK (verify_until >= stop_signing_at)
);

-- Chỉ một key ACTIVE cho một issuer/purpose
-- trong mẫu policy "single active signing key".
CREATE UNIQUE INDEX uniq_active_key_per_issuer_purpose
ON signing_key_versions (issuer_id, purpose)
WHERE state = 'ACTIVE';
~~~

**Đây là schema minh họa, không phải một tiêu chuẩn RFC.** Nó không lưu private key bytes trong database, chỉ giữ **KMS key reference**. Tổ chức có thể cần thiết kế khác nếu chủ động hỗ trợ nhiều active signing keys theo partition/tenant; khi đó unique index và selection policy phải thay tương ứng.

### 14.1. Không lưu private key trong registry chung

Registry nên nắm metadata, không chứa PEM private key như một trường `private_key`. Secret material phải được bảo vệ bởi HSM/KMS hoặc secret manager đủ mạnh, với audit và quyền tách biệt:

~~~text
Token issuer workload:
  permission: SIGN using active key reference
  no permission: EXPORT private key, DESTROY key

Resource server workload:
  permission: READ trusted public JWKS, VERIFY
  no permission: SIGN using issuer private key

Security operations:
  permission: APPROVE rotation/distrust, audit changes
  no permission: directly read private key plaintext
~~~

### 14.2. State transition cần transaction và revision

Cutover K1→K2 không nên là:

~~~text
Update K2 ACTIVE on node A;
wait;
Update K1 RETIRED on node B;
~~~

Điều này có thể tạo cửa sổ **hai active keys** hoặc không key active. Dùng authoritative transaction/config revision có tính nhất quán phù hợp, signer-side validation và atomic deployment semantics; với KMS policy thay đổi riêng, cần phối hợp để **không phát token K1 ngoài cửa sổ**.

### 14.3. Audit đủ để trả lời “last token signed by K1 khi nào?”

Một audit record không chứa token raw:

~~~text
event=token_issued
issuer_alias=internal-auth
token_type=access_token
signing_kid=issuer-sign-1
issued_at=<secure-server-clock>
expiration_at=<token-exp>
signer_instance=as-node-a
correlation_id=<non-secret-id>
~~~

Khi K1 được retired, dựa trên dữ liệu actual issuance để xác minh `T_stop` và `L_max`. **Không chỉ tin thời điểm operator bấm nút “Retire” nếu các signing workers chưa đồng bộ**.

### 14.4. Quản lý state change bằng least privilege

Không nên để một developer bất kỳ tự chuyển `DISABLED` → `ACTIVE` cho compromised key. Cần phân quyền, change approval/dual control khi phù hợp, immutable audit, incident tracking và quy trình rollback **không hồi sinh khóa bị distrust**.

## 15. Race conditions trong key rotation

Mỗi giai đoạn của rotation có thể gặp race:

| Race | Ví dụ | Hệ quả | Cách phòng |
| --- | --- | --- | --- |
| **Key published chậm** | K2 ACTIVE trước RS thấy public K2 | JWT K2 bị 401 | Prepublish/prefetch |
| **Signing stale** | AS node C vẫn sign K1 sau cutover | Old-token horizon kéo dài | Signer-side revision/metrics |
| **Key removed sớm** | JWKS không còn K1 khi tokens K1 chưa hết hạn | JWT K1 hợp lệ bị 401 | Overlap đủ dài |
| **JWKS cache stale** | RS cache K1 sau khi key compromised | Token giả có thể verify | Emergency distrust/forced update |
| **Reused `kid`** | K1 và K2 cùng ID | Chọn sai public key | Versioned unique `kid` |
| **Issuer mismatch** | RS chọn K2 của issuer B | Cross-issuer trust bug | Namespace issuer/kid |
| **Clock skew** | RS có leeway quá lớn | Token còn hiệu lực ngoài SLA | Đồng bộ đồng hồ/giới hạn skew |
| **Restore backup** | AS quay về cấu hình K1 active | Ký lại bằng retired/compromised key | Monotonic revision, KMS gate |
| **Blue-green deploy** | Cluster cũ và mới giữ active key khác | Khó audit và mismatch | Deployment choreography |
| **Event đến sai thứ tự** | RETIRED event trước ACTIVE event cũ | Key bị re-activate ngoài ý muốn | Versioned transitions/rollback defense |

### 15.1. Version monotonic cho key policy

Một control-plane event:

~~~json
{
  "issuer": "https://auth.example.com",
  "purpose": "JWS_SIGNING",
  "kid": "issuer-sign-1",
  "state": "RETIRED",
  "version": 42,
  "effective_at": "2026-11-23T10:00:00Z"
}
~~~

Các nodes chỉ áp policy version **mới hơn** và từ nguồn authenticated. Nếu event `version=41, state=ACTIVE` đến sau version 42, không được **hồi sinh K1**. Với compromise, có thể cần một **irreversible emergency distrust flag** cho tới khi security authority phê duyệt xử lý riêng.

### 15.2. Transactional outbox cho trust updates

Nếu authoritative DB ghi K1 disabled nhưng message broker không phát event do process crash, các RS khác có thể giữ trust state cũ. **Transactional outbox** và idempotent consumers giúp giảm lost update. Nhưng với emergency distrust, vẫn cần policy **fail closed khi consumer không chứng minh đã cập nhật tới version yêu cầu**.

### 15.3. Không rollback vô điều kiện

Giả sử K2 vừa phát JWT mới, operator rollback app sang bản K1. Nếu K1 bị retired đúng quy trình, rollback **không được tự khôi phục quyền ký K1**. Rollback code và rollback **security state** là hai việc khác nhau; security authority giữ policy monotonic và signer phải fail nếu current key không được phép.

## 16. Khóa active/retired trong OIDC, OAuth và các token classes

Không chỉ **JWT access token** cần phân biệt key lifecycle:

| Đối tượng | Khóa/vai trò | Điều cần cân nhắc khi retired |
| --- | --- | --- |
| **JWT access token** | AS signing key, RS verify | Max AT TTL, audience/scope, key trust overlap |
| **OIDC ID token** | OP signing key, OIDC client verify | ID token profile/lifetime, `aud` client, `nonce` |
| **JWT client assertion** | Client signing key, AS verify | Key registration client và assertion expiry/replay |
| **DPoP proof JWT** | Client DPoP private key, AS/RS verify | Sender key binding, proof replay window, token confirmation |
| **JWE token** | Recipient encryption/decryption key | Còn encrypted tokens cần decrypt, recipient key rotation |
| **Refresh token** | Có thể opaque/JWT theo AS | Family/rotation/revocation và token storage, không suy kiểu key |
| **mTLS-bound access token** | Client cert/key + AS signing key | Certificate binding/rotation độc lập JWT signing key |
| **Opaque AT + introspection** | Có thể không có public JWS verification key ở RS | AS introspection state và caller auth, key lifecycle nội bộ khác |

### 16.1. OIDC client phải xử lý key rollover của OP

Client có thể verify ID token từ OP qua public JWKS. Khi OP đổi signing key, client cần nhận key mới trước khi OP dùng, đồng thời vẫn verify ID token cũ trong window được profile cho phép. **OIDC nonce vẫn phải được kiểm** ở đúng transaction; biết key mới không thay issuer/client audience/nonce verification.

### 16.2. JWT client assertion key là một trust domain khác

Trong `private_key_jwt`, OAuth client ký assertion bằng **private key của client**, AS xác minh bằng **public key đã đăng ký của client**. Khi client key Kc1 retired:

- Client ngừng ký assertions mới bằng Kc1.
- AS có thể giữ khả năng verify assertions còn hạn bằng Kc1 theo contract.
- `iss`, `sub`, `aud`, `exp`, algorithm và replay checks vẫn bắt buộc.

**Không trộn Kc1 với AS signing key phát access token**, dù cả hai đều tạo JWS.

### 16.3. DPoP key rotation còn ràng buộc với access token

DPoP-bound access token có `cnf.jkt` trỏ tới thumbprint của DPoP key. Nếu client tự đổi sang key mới mà access token cũ vẫn bound với key cũ, proof ký bằng key mới **không tự hợp lệ** cho token cũ. Cần token issuance/rotation policy phù hợp. Không lấy quy tắc “retired issuer signing public key” để suy DPoP client key có thể dùng tùy ý.

### 16.4. Key retirement không thay revoke token/grant

Một JWT ký bằng K2 active có thể bị revoke khi user logout hoặc bị rút quyền. Một JWT K1 retired vẫn có thể chưa revoked. **Token validity = signature/key trust + claims/time/audience + revocation/business policy**, không chỉ key state.

## 17. Hợp đồng vận hành về thời điểm retirement

Một yêu cầu mơ hồ:

> “Đổi key ngày 1, xóa key cũ ngay.”

Không đủ để thực hiện an toàn. Hãy ghi rõ:

~~~text
Issuer: https://auth.example.com
Token profiles: access_token(at+jwt), id_token
Key purpose: JWS_SIGNING
Algorithm: RS256
New key K2 public prepublish at: <UTC time>
Earliest K2 signing activation: <UTC time>
Last K1 signing permitted at: <UTC time>
Max lifetime of all K1-signed profiles: <duration>
RS clock skew maximum: <duration>
JWKS max-age and refresh strategy: <policy>
Normal K1 trust removal no earlier than: <UTC time>
Emergency K1 distrust path: <runbook>
Actual per-node uptake proof: <metrics/check>
~~~

### 17.1. Tối thiểu cần cam kết điều gì?

- **Không phát token mới bằng retired K1** sau cutover.
- **Không từ chối token K1 hợp lệ quá sớm** trong normal rotation.
- **Không chấp nhận token K1 sau trust removal** nếu policy yêu cầu, kể cả RS cache cũ.
- **Không chấp nhận key compromised** chỉ vì token `exp` còn hạn.
- **Không bypass issuer/audience/scope** khi key rotate hoặc JWKS unavailable.

### 17.2. Điều cần đo để chứng minh

Chỉ báo có thể dùng:

~~~text
issuer_signing_kid_active{issuer_alias="auth-A"} = K2
tokens_issued_by_kid_total{kid_alias="K1"}
tokens_issued_by_kid_total{kid_alias="K2"}
rs_unknown_kid_errors_total
rs_invalid_signature_errors_total
jwks_cache_age_seconds
jwks_refresh_failures_total
key_trust_policy_version
rs_key_distrust_ack_count
retired_key_verify_success_count
requests_with_unexpected_retired_kid_total
~~~

**Không đưa raw JWT, secret, private JWK, user PII hoặc `kid` nhạy cảm do attacker tự đặt vào metric labels**. `kid` là string attacker có thể kiểm soát ở JWT header; metrics phải chuẩn hóa vào **known key alias** hoặc nhóm `unknown`, tránh cardinality attack.

## 18. Các tình huống thực tế

**Tình huống A — AS đổi sang K2 nhưng chưa public K2.**

10:00 AS phát JWT có `kid=K2`; Orders RS cache JWKS chỉ chứa K1.

**Phân tích:** JWT K2 có thể hợp lệ nhưng RS không có trusted key để verify. Đó là lỗi **prepublication/key distribution**. Không tắt verify; cần prepublish K2, refresh trusted JWKS và đồng bộ cutover.

**Tình huống B — Operator xóa K1 khỏi JWKS ngay khi retire.**

JWT ký K1 từ 09:59 có `exp=10:14`; RS refresh JWKS lúc 10:02 chỉ còn K2.

**Phân tích:** Normal rotation làm token hợp lệ thất bại. Giữ retired verification key đến deadline tính từ **last K1 issuance + max lifetime + clock policy**.

**Tình huống C — Không thể refresh K2 do JWKS outage.**

RS nhận JWT K2 mới nhưng không có public key K2.

**Phân tích:** Fail closed với token chưa verify; phân biệt availability incident với `invalid_token` thật, không cho phép signed token chưa có trusted public key. Dùng prefetch, retry/backoff và monitoring thay vì fallback bypass.

**Tình huống D — Một AS node vẫn ký bằng K1.**

AS A/B chuyển K2, AS C từ bản deploy cũ vẫn sign K1 10 phút sau.

**Phân tích:** `T_stop` thực tế muộn hơn kế hoạch; old-token horizon bị kéo dài. Enforce signer-side active policy, kiểm all nodes và audit issuance by `kid`. Không sửa `exp` của token để che vấn đề.

**Tình huống E — K1 retired nhưng token K1 còn `exp`.**

Orders RS verify chữ ký K1 đúng, `aud=orders-api`, scope hợp lệ.

**Phân tích:** Theo normal overlap policy, token **có thể** tiếp tục được chấp nhận tới `exp`, trừ khi grant/token bị revoke hoặc key K1 compromised. Retired không tự là invalid.

**Tình huống F — K1 bị lộ sau khi retired.**

Attacker lấy private K1 từ backup và ký JWT mới với `iat` lùi về trước thời điểm retire.

**Phân tích:** Kiểm `iat` nằm trong signing window không chứng minh JWT do AS thật phát. Phải **emergency distrust K1**, cập nhật RS caches/trust policy, xử lý tokens đã cấp.

**Tình huống G — Public K1 xuất hiện trên Internet.**

Một auditor báo “public RSA key trong JWKS bị lộ”.

**Phân tích:** Public key được thiết kế để phân phối. Cần xác định có **private key leak**, JWKS integrity compromise hay thuật toán/key confusion không, thay vì coi riêng việc tải public JWK là sự cố.

**Tình huống H — Shared HS256 secret được copy tới 20 microservices.**

AS không còn sign bằng secret K1 nhưng các RS vẫn giữ K1 để verify tokens cũ.

**Phân tích:** Mỗi RS có K1 đều có khả năng tạo MAC hợp lệ. Retired verify-only chỉ là **policy tổ chức**, không phải giới hạn cryptographic của shared secret. Xem xét chuyển sang asymmetric JWS hoặc phạm vi shared secret rất hẹp.

**Tình huống I — Encrypted JWT cũ không decrypt sau rotation.**

RS xóa private JWE decryption key E1 ngay khi issuer bắt đầu encrypt bằng E2.

**Phân tích:** JWT/JWE cũ còn hạn vẫn dùng E1; private E1 phải được giữ cho **decrypt-only window** hoặc tokens phải được reissued theo thiết kế. Khác với public verification key của JWS.

**Tình huống J — KEK cũ bị destroy, backup cũ không mở được.**

KMS xóa K1 dùng wrap encryption keys của database backup, chưa rewrap backup DEKs.

**Phân tích:** Key retirement at rest phải xét **data retention/rewrap/re-encryption**, không dùng access token lifetime để quyết định xóa key.

**Tình huống K — JWT ký đúng K2 nhưng `aud=payments-api`.**

Orders RS tin K2 và signature đúng.

**Phân tích:** Vẫn từ chối; **key trust không cấp quyền trên resource**. Cần kiểm `aud`, `scope`, token purpose, tenant và business permissions.

**Tình huống L — ID token ký bởi K2 được dùng làm API bearer.**

ID token có `iss` và signature hợp lệ nhưng `aud=oidc-client`.

**Phân tích:** Orders RS phải từ chối sai **token type/audience**, dù OP mới rotate key thành công. Không chỉ xem `kid` và chữ ký.

**Tình huống M — JWT K1 bị revoke trước expiry.**

User logout hoặc admin disable account; K1 retired vẫn có public key trong JWKS.

**Phân tích:** RS phải áp **token/grant revocation policy** nếu muốn chặn trước `exp`. Retired-key overlap không phủ nhận revocation.

**Tình huống N — `kid` bị dùng lại giữa hai khóa RSA.**

K1/K2 cùng `kid=2026`, RS caches có public key khác nhau.

**Phân tích:** Key mismatch và key-trust confusion. Dùng **key IDs riêng**, không sửa vật liệu của một key ID đang được cache, lập kế hoạch rollover.

**Tình huống O — Attacker thêm `jku` vào JWT mới.**

JWT `kid=K3` và `jku=https://attacker.example/jwks`.

**Phân tích:** RS không được tải URL tùy ý; chỉ chọn key từ **trusted issuer JWKS** đã được allowlist. Đừng để việc đang rotate thành cơ hội key injection/SSRF.

**Tình huống P — RS cache public K1 sau emergency revoke.**

AS đã loại K1 khỏi JWKS nhưng một RS ở region xa còn tin K1.

**Phân tích:** Phải đo/truyền emergency distrust state, buộc refresh, fail closed hoặc cô lập RS stale. JWKS publication **không đồng nghĩa tất cả consumers đã nhận**.

**Tình huống Q — Client assertion key Kc1 retired.**

OAuth client vừa chuyển sang Kc2, AS còn nhận assertion Kc1 chưa quá `exp`.

**Phân tích:** Có thể cần verification overlap ngắn theo contract, nhưng không cho client **ký assertion mới** bằng Kc1. Vẫn kiểm audience, expiry, signature, `jti` replay.

**Tình huống R — DPoP key của client thay đổi.**

Access token bound với DPoP key D1, client tạo proof mới bằng D2.

**Phân tích:** Proof D2 không tự khớp `cnf.jkt` của token D1. Cần token issuance/refresh theo key mới; đây không phải issuer K1/K2 rollover.

**Tình huống S — Key status trong JWT ghi `ACTIVE`.**

Attacker gửi JWT cũ chứa `key_status=ACTIVE` dù RS đã distrust key.

**Phân tích:** Nội dung token là snapshot tại issuance, không thay live trust registry. Không dùng claim làm authority để re-enable key.

**Tình huống T — Deploy rollback sau signing-key compromise.**

Build cũ có config `activeKid=K1` được redeploy.

**Phân tích:** KMS/signing service phải từ chối K1 vì security state đã distrust, bất kể app config rollback. Không đồng nhất rollback code với rollback key policy.

## 19. Những sai lầm thường gặp

### 19.1. “Retired nghĩa là revoked”

**Sai** trong rotation bình thường. Retired signing key có thể tiếp tục được dùng để verify tokens cũ, còn compromised/revoked key cần distrust ngay.

### 19.2. “Đổi active signing key khiến JWT cũ hết hạn”

**Sai.** Token lifetime được quyết định bởi claims/profile và RS validation, không phải active key hiện tại.

### 19.3. “Nếu key còn trong JWKS, AS chắc chắn đang ký bằng key ấy”

**Sai.** JWKS có thể chứa **active và retired public verification keys** để hỗ trợ overlap.

### 19.4. “Ngừng sign bằng K1 thì có thể xóa K1 ngay”

**Sai** nếu còn JWT hợp lệ cần verify hoặc JWE cần decrypt bằng old key. Phải tính validity/retention horizon theo purpose.

### 19.5. “JWS public key của retired key phải giữ bí mật”

**Sai.** Public verification key vốn có thể công khai. **Private signing key** mới phải được bảo vệ và giới hạn quyền.

### 19.6. “HS256 retired secret an toàn như RSA public verification key”

**Sai.** HMAC secret cho phép cả tạo và kiểm MAC. Chia secret làm tăng nguy cơ giả mạo token.

### 19.7. “JWT tự có `key_status` nên không cần trust registry”

**Sai.** Key trust là quyết định **hiện hành**, không được token chưa verify hay claim cũ quyết định.

### 19.8. “JWKS refresh là đủ cho key compromise”

**Không luôn đúng.** Consumers có thể cache lâu, offline hoặc mất kết nối; yêu cầu emergency revoke cần trust propagation/fail-closed assurance.

### 19.9. “Token `iat` trước retire chứng minh không bị attacker ký sau retire”

**Sai khi private K1 compromised.** Kẻ có key có thể ký token mới chứa `iat` giả quá khứ.

### 19.10. “Một `kid` có thể dùng mãi, chỉ cần thay modulus”

**Rủi ro.** JWKS caches và verifiers có thể giữ mapping cũ, gây mismatch/confusion. Nên version key IDs duy nhất.

### 19.11. “Có `kid` lạ thì tắt verify và chấp nhận”

**Nguy hiểm.** Unknown key phải dẫn tới bounded trusted refresh hoặc từ chối, tuyệt đối không fail open.

### 19.12. “Signing key của issuer có thể dùng giải mã JWE”

**Sai về purpose/trust model.** Tách signing và recipient encryption keys; không tùy tiện tái dùng một RSA key pair.

### 19.13. “K1 retired nên token K1 được miễn kiểm `exp` để tránh gián đoạn”

**Sai.** Signature vẫn cần đúng, và `exp`, `nbf`, audience/scope/revocation không bị miễn.

### 19.14. “Xóa public key khỏi JWKS là xóa private key khỏi mọi backup”

**Sai.** JWKS, KMS/HSM, backup, restore image, operator snapshots là các nơi khác nhau, cần inventory và destruction policy.

### 19.15. “Một key policy áp cho mọi tenant/issuer”

**Rủi ro.** Key/trust domain và token types có thể khác nhau; không gộp mọi `kid` vào một danh sách chung bỏ qua issuer.

## 20. Bộ kiểm thử rotation và retired key

| Test case | Kỳ vọng |
| --- | --- |
| K2 PREPUBLISHED trong trusted JWKS, chưa active | RS đã load K2; AS vẫn ký mới K1 |
| AS active K2 sau prepublish | JWT mới có `kid=K2` và signature đúng |
| K1 chuyển RETIRED | AS không tiếp tục ký JWT mới bằng K1 |
| K1 retired, JWT K1 chưa hết `exp` | RS vẫn verify được theo normal overlap |
| K1 retired, JWT K1 đã hết `exp` | RS từ chối |
| K1 retired, JWT K1 sai `aud` | RS từ chối |
| K1 retired, JWT K1 bị revoke | RS từ chối theo revocation policy |
| K1 retired nhưng AS node stale vẫn sign K1 | Signer-side policy/test phát hiện |
| K1 retired và K2 active, thiếu active signing key khi KMS lỗi | Issuer ngừng phát, không fallback K1 |
| Hai keys cùng ACTIVE trong policy single-active | Registry/issuer từ chối trạng thái |
| JWKS chưa có K2 lúc AS cutover | Predeployment test fail, không thực hiện rollout |
| RS chỉ có K1 cached, nhận token K2 | Bounded trusted JWKS refresh; không bypass |
| RS nhận JWT `kid` ngẫu nhiên | Không gọi untrusted URL, rate limit refresh |
| JWT chứa `jku` attacker | Không tải arbitrary JWKS |
| JWT `alg=none` | Từ chối |
| JWT header đổi RS256 sang HS256 | Từ chối alg/key confusion |
| JWT `kid` trùng giữa issuers | Không chọn key sai trust domain |
| K2 dùng lại `kid` của K1 với key bytes khác | Rotation validation fail |
| Một JWT `iat` sau stop-signing bằng K1 | Từ chối theo issuer/key-window policy nếu contract áp |
| K1 private compromised, JWT attacker `iat` giả quá khứ | Emergency distrust ngăn key acceptance |
| K1 compromised nhưng RS cache public K1 | RS stale bị cập nhật/cô lập hoặc fail closed |
| K1 chỉ retired bình thường, không compromise | Không làm mất JWT cũ hợp lệ trước hạn |
| Client assertion Kc1 còn hạn và chưa bị reuse | Verify theo allowed client-key window |
| Client assertion Kc1 sau retirement phát mới | Issuer/client policy từ chối |
| ID token OP ký K1 cũ còn trong validity window | OIDC client verify issuer/audience/nonce đầy đủ |
| JWE mã hóa bằng public E1 trước cutover | RS giữ private E1 để decrypt đúng hạn |
| New JWE encrypt bằng retired public E1 | Bên phát từ chối theo policy |
| Decryption key E1 xóa khi old ciphertext còn cần | Lifecycle test fail |
| KEK cũ bị destroy trước rewrap backups | Retention/recovery test fail |
| HMAC secret retired còn ở nhiều RS | Security review nhận diện khả năng MAC forgery |
| Issuer K1/K2 signer clock lệch | Không phát ngoài allowed window |
| JWT expiry leeway bị tăng quá mức | Policy/test phát hiện kéo dài token acceptance |
| JWKS outage lúc RS đã có trusted K1/K2 | Chỉ xử lý theo bounded cache policy |
| JWKS outage khi RS chưa biết K2 | Fail closed, không skip signature |
| Cutover có network partition | Node stale không vi phạm required trust policy |
| Rollback app config cố bật lại compromised K1 | KMS/signer-side gate từ chối |
| Disable key event đến trước active event cũ | Version monotonic, không re-enable |
| Signing key K1 public được truy cập từ JWKS | Bình thường, không đánh dấu leak private key |
| Public JWKS chứa private RSA parameters | Security test thất bại |
| API nhận ID token làm access token | Từ chối purpose/audience |
| Scope đúng nhưng order thuộc tenant khác | Từ chối object authorization |
| User disable nhưng JWT K2 còn hạn | Áp revocation/account-state policy theo SLA |
| Logs chứa raw access token/private key/secret | Security test thất bại |

### 20.1. Tầng unit tests

Kiểm key state transitions, `signFrom`, `stopSigningAt`, `verifyUntil`, `compromised`, duplicate active keys, issuer/algorithm namespace và key-selection fail-closed.

### 20.2. Tầng AS integration tests

Ký token trước/sau cutover, kiểm actual `kid`, KMS/HSM permission, old signer nodes, issuance concurrency, max token lifetime, replay/rollback policy và audit.

### 20.3. Tầng RS integration tests

Load public K1/K2 qua trusted JWKS, kiểm validity of old/new JWT, issuer/audience/type/time/scope, unknown `kid`, invalid signature, refresh/caching/outages.

### 20.4. Multi-region/chaos tests

Mô phỏng CDN JWKS stale, network partition, failover KMS, partial rollout, deleted key in cache, active-key rollback, event backlog, emergency distrust và RS stale. Đo thời điểm **API thực sự từ chối key compromised**, không chỉ thời điểm publisher thay JSON.

### 20.5. Security incident drill

Dùng **test key/issuer trong môi trường cô lập**, không dùng production private key. Giả lập compromised K1 và kiểm K1 bị chặn trên tất cả RS, K2 tiếp tục hoạt động, metrics/alerts báo đúng, không có fallback bỏ signature.

## 21. Runbook: normal key rotation và emergency distrust

### 21.1. Runbook A — Rotation có kế hoạch

~~~text
PREPARE
  [ ] Inventory token types/issuers/consumers dùng K1
  [ ] Đo max token TTL, exp, skew, cache TTL và retention
  [ ] Sinh K2 trong KMS/HSM; gán kid mới và policy đúng
  [ ] Đăng ký K2 với issuer signing service

PREPUBLISH
  [ ] Publish public K2 vào trusted JWKS
  [ ] Kiểm CDN/RS caches/tenants/regions đã thấy K2
  [ ] Canary thử verify K2, không log raw JWT

CUTOVER
  [ ] Atomic/control-plane chuyển active signing K1 -> K2
  [ ] Cấm K1 sign ở signer/KMS policy
  [ ] Audit tất cả issuer nodes chỉ sign K2
  [ ] Giữ public K1 + K2 trong verify window

OVERLAP
  [ ] JWT K1 cũ vẫn verify nếu đúng exp/aud/scope
  [ ] JWT K2 mới verify bình thường
  [ ] Theo dõi unknown kid, signature errors, expired tokens
  [ ] Kiểm không có K1 signing sau cutover

SUNSET
  [ ] Xác nhận old-token validity horizon đã kết thúc
  [ ] Remove K1 khỏi JWKS/trust bundles theo policy
  [ ] Xác nhận các consumers đã nhận trust update
  [ ] Archive/destroy private material theo policy
  [ ] Lưu audit rotation và kiểm recovery
~~~

### 21.2. Runbook B — Private signing key bị lộ

~~~text
DETECT
  [ ] Phân loại incident: private signing key hay public JWK?
  [ ] Xác định issuers, kids, token classes, affected RS
  [ ] Ngăn tiếp tục sử dụng compromised signing key

CONTAIN
  [ ] Kích hoạt K2/K3 sạch và signing service policy mới
  [ ] Force-distrust K1 tại RS; không chờ normal expiry
  [ ] Bắt buộc chứng minh trust-policy version trên mọi node
  [ ] Stale/offline RS fail closed hoặc bị cô lập khi cần

RECOVER
  [ ] Revoke/invalidate tokens K1 theo khả năng kiến trúc
  [ ] Reissue legitimate tokens qua trust chain an toàn
  [ ] Đánh giá forged JWT / privileges abused / data accessed
  [ ] Rotate các credentials/keys liên đới khi cần

VERIFY
  [ ] Token thử ký K1 không được RS chấp nhận
  [ ] Token mới ký K2 vẫn được kiểm đúng policy
  [ ] Không fallback unverified JWT/old HMAC secret
  [ ] Rà soát logs, backups, KMS policies và access history
~~~

**Tuyên bố đúng mức:** hoàn thành lệnh **disable K1 trong KMS** không chứng minh mọi RS đã distrust public K1. Mỗi RS có trust cache riêng; cần **end-to-end test**.

### 21.3. Ai phê duyệt và chịu trách nhiệm?

Một ma trận tối thiểu:

| Vai trò | Trách nhiệm |
| --- | --- |
| **Security / Key custodians** | Threat model, key protection, approval/distrust, audit |
| **AS owner** | Signer policy, issuance, JWKS publication, token lifetime |
| **RS/API owners** | Verification/trust refresh, audience/scope authorization |
| **SRE/Operations** | Multi-region rollout, outage, alarms, cache/secret rotation |
| **Product/Support** | Hành vi logout/relogin và thông báo tác động client |

Tùy tổ chức, người vận hành có thể kiêm nhiều vai trò, nhưng **quyền thay đổi key state** không nên không được kiểm soát.

## 22. Checklist production

1. **Định nghĩa đúng purpose:** signing vs verify, encrypt vs decrypt, HMAC vs asymmetric, JWKS key vs KMS key.
2. **Lifecycle rõ:** staged/prepublished/active/retired/disabled/destroyed với transitions được kiểm soát.
3. **Không công khai private keys:** public JWKS chỉ chứa public verification material; KMS/HSM quản lý private key.
4. **`kid` có version và namespace:** không tái dùng cho key bytes khác; ràng issuer/token purpose.
5. **Algorithm allowlist:** RS chặn `alg=none`, HS/RS confusion và key type sai.
6. **Prepublish key mới:** K2 phải được trusted consumers nhận trước khi AS bắt đầu ký.
7. **Switch ký có kiểm soát:** issuer nodes dùng đúng active key; signer/KMS không fallback retired K1.
8. **Retired = verify-only trong normal rotation:** không xóa old public key quá sớm khi JWT còn hạn.
9. **Max token horizon:** tính theo last issuance, mọi token profiles, `exp`, skew và margins đã duyệt.
10. **Không mở rộng JWT lifetime vì JWKS cache:** verification luôn kiểm token expiry và policy.
11. **Key status không đến từ JWT claim:** dùng authoritative key registry/trust policy, không tin status self-declared.
12. **JWKS trust source:** HTTPS issuer metadata allowlisted, chống SSRF/unverified `jku`, cache/ETag phù hợp.
13. **Unknown `kid` xử lý an toàn:** bounded refresh rồi từ chối, không fail open hoặc brute force all keys.
14. **Emergency distrust độc lập:** khi private key compromised, force-remove trust, không chờ normal overlap.
15. **Trust update có consistency:** revision monotonic, ACK/health của RS và stale-node fail-closed policy.
16. **HMAC shared secret đúng risk:** verifier có signing capability; giới hạn trust domain hoặc chuyển asymmetric keys.
17. **JWE lifecycle riêng:** encrypt new bằng E2, decrypt old bằng E1; private keys giữ an toàn đến khi hết nhu cầu.
18. **At-rest KEK retention đúng dữ liệu:** rewrap/re-encrypt trước destroy, test backup restores.
19. **OIDC ID token client verify đúng:** issuer/audience/expiry/nonce và key rollover.
20. **JWT client assertions riêng:** client key lifecycle và replay `jti` không nhầm issuer signing keys.
21. **DPoP/mTLS sender binding:** client key/certificate rotation không tự rebind access token cũ.
22. **RS luôn làm authorization:** issuer, audience, token type, expiry, scope, tenant, ownership và revocation.
23. **Không dùng key rotation thay logout:** refresh token family/grant revocation có lifecycle khác.
24. **Observability an toàn:** known-kid aliases, rotation events, trust versions, no raw tokens/secret/private JWK.
25. **Kiểm concurrency/rollback:** multi-issuer nodes, JWKS cache, key reactivation, KMS availability.
26. **Có runbook incident:** compromised signing key, decryption key, HMAC secret và JWKS endpoint takeover.
27. **Kiểm thử end-to-end:** token K1 cũ đúng hạn, token K2 mới, K1 compromised và RS stale đều có expected outcomes.
28. **Không tuyên bố quá mức:** “K1 retired” không tự nghĩa toàn bộ JWT ký K1 đã revoke hoặc không còn được RS chấp nhận.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Khi K1 đã RETIRED và K2 ACTIVE, một JWT K1 chưa hết hạn có nên được RS chấp nhận?

**Trả lời:** Trong rotation **bình thường**, có thể **có**, nếu K1 còn trong trusted verification window và token đáp ứng tất cả kiểm tra JWT/authorization/revocation. Nếu K1 bị compromise hoặc đã distrust, phải từ chối.

**Câu 2.** Vì sao phải publish K2 trước khi AS bắt đầu ký?

**Trả lời:** RS có thể cache JWKS. Nếu chưa biết K2, RS không có key tin cậy để verify JWT mới. Prepublish giảm `unknown_kid` và outage khi cutover.

**Câu 3.** AS dừng ký K1 lúc 10:00, access token max TTL 15 phút và leeway 60 giây. Có thể xóa K1 khỏi JWKS ngay 10:00 không?

**Trả lời:** Thường **không** trong normal rotation; các JWT K1 vừa phát trước 10:00 có thể còn hợp lệ tới khoảng 10:16 theo giả định. Cần tính cả token profiles khác, actual last issuance, distribution/operational margins.

**Câu 4.** K1 đã bị lộ private key nhưng JWT có `iat` trước thời điểm retire. Có thể tin token đó không?

**Trả lời:** Không chỉ dựa vào `iat`. Attacker có private key có thể ký JWT mới với `iat` giả quá khứ. Cần emergency distrust/issued-token evidence hoặc authoritative state phù hợp.

**Câu 5.** `use=sig` trong public JWK chứng minh key đang ACTIVE không?

**Trả lời:** Không. Nó mô tả mục đích **signature**, không phải lifecycle status. Retired public key vẫn có thể được publish để verify JWS cũ.

**Câu 6.** Nếu dùng HS256, Resource Server có một “public verification key” tương tự RS256 không?

**Trả lời:** Không. HS256 dựa trên **shared secret**, nên bên verify có secret cũng có khả năng tạo MAC. Khi secret bị lộ ở RS, không thể chỉ giữ “public part” an toàn.

**Câu 7.** Tại sao đổi JWE recipient encryption key lại phải giữ private decryption key cũ?

**Trả lời:** JWE cũ đã được mã hóa cho key E1; nếu không có private E1 và chưa reissue/re-encrypt, recipient không giải mã được ciphertext cũ dù token vẫn còn hạn.

**Câu 8.** JWKS đã loại K1 khỏi response nhưng RS đang cache K1. Key K1 có bị vô hiệu ngay ở RS không?

**Trả lời:** Chưa chắc. RS có thể chưa refresh và tiếp tục verify token K1. Emergency distrust phải có cache invalidation, trust-update propagation và xử lý stale nodes theo SLA.

**Câu 9.** Token ký K2 đúng chữ ký, nhưng `aud=payments-api` được gửi đến Orders API?

**Trả lời:** Orders phải từ chối. Signing key đúng không thay **audience/scope/tenant và object-level authorization**.

**Câu 10.** Quản trị viên revoke refresh token nhưng RS còn nhận JWT K2 đã phát. Rotation có sửa vấn đề không?

**Trả lời:** Không tự động. Cần access-token revocation/denylist/introspection hoặc chờ `exp`; refresh-token revoke cắt khả năng phát mới theo AS policy.

## 24. Tài liệu tham khảo

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS, `kid`, `use`, `key_ops` và key representation.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): ký, protected header, thuật toán và xác minh signature.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): recipient decryption key, encrypted content và key management.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): JWS/JWE algorithm identifiers, key types và crypto parameters.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `iat`, `nbf`, `exp`, `jti`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/key trust, cross-JWT confusion và issuer validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): token type, issuer/audience, algorithm và claims validation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer metadata và discovery of endpoints/JWKS.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth roles, access/refresh-token lifecycle.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token/grant revocation khác signing-key retirement.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): online token-state checks và caller authentication.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth threat model, token theft/replay, key/token best practices.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT client assertions và public-key client authentication.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained tokens và DPoP key binding.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): certificate-bound access tokens và mTLS client identity.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token signing/verification, issuer/audience/nonce và OIDC clients.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): cryptographic key lifecycle, cryptoperiods, key protection và compromise.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWKS-backed JWT validation/decoding.
- [OWASP JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): token signing, validation, storage và operational security.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): key storage, rotation, algorithms và protection.

**Ghi nhớ:** **Active key** là khóa được phép thực hiện thao tác **mới** theo purpose, ví dụ AS ký JWT access token mới. **Retired signing key** thường **ngừng ký mới nhưng tiếp tục cho RS verify JWT cũ** trong cửa sổ xác định bởi *last issuance + max token lifetime + clock/operational margins*. Muốn chuyển khóa an toàn, cần **prepublish public key mới, phối hợp tất cả signer/RS nodes, giữ public key cũ đủ lâu rồi ngừng tin theo policy**. Nếu **private key bị compromise**, không được đợi hết overlap: phải kích hoạt **emergency distrust và xác minh mọi RS đã cập nhật trust state**. Dù token ký bằng active hay retired key, Resource Server vẫn phải kiểm **signature/issuer/audience/token type/expiry/scope, revocation, tenant và quyền trên tài nguyên**.
