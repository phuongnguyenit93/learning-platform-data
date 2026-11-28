# Bản đồ khái niệm: tổng kết xác thực HTTP request bằng HMAC

## 1. Cách đọc bản đồ khái niệm

Module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` hướng tới việc thiết kế xác thực HTTP request bằng **HMAC với shared secret**, dựng **canonical request** từ method, URI, signed headers và/hoặc body theo hợp đồng ký; xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt authentication với authorization.

Bài **Bản đồ khái niệm** thuộc chương **Tổng kết HMAC authentication** là bản tổng hợp các khái niệm và **quan hệ nhân–quả** của toàn hệ thống, không chỉ là danh sách thuật ngữ. Mỗi nhánh trả lời ba câu hỏi: *thành phần đó bảo vệ điều gì, nó phụ thuộc vào gì, và lỗi nào xuất hiện khi mối liên kết bị đứt?*

**Một mô hình tư duy ngắn gọn:**

> Authentication thành công khi server biết **ai đang dùng key hợp lệ**, chứng minh **chữ ký trên đúng bytes**, chứng minh **bằng chứng còn mới và chưa được sử dụng**, rồi gắn danh tính từ registry đáng tin vào request. Authorization là phép quyết định **danh tính đó được phép làm gì**.

Tuy nhiên, HMAC không mã hóa nội dung; TLS bảo vệ kênh truyền. HMAC với secret chung cũng không tự mang tính **non-repudiation** như chữ ký số khóa bất đối xứng: cả client lẫn server có secret đều có khả năng tạo MAC.

### Quy ước trên bản đồ

| Ký hiệu / mối liên kết | Cách hiểu |
| --- | --- |
| **A → B** | B phụ thuộc vào kết quả hoặc thông tin tin cậy từ A |
| **A ≠ B** | Hai khái niệm thường bị nhầm nhưng giải quyết vấn đề khác nhau |
| **A + B** | Cần kết hợp để đạt thuộc tính bảo mật |
| **Candidate → Verified** | Dữ liệu client khai được kiểm chứng và gắn với principal |
| **First-use** | Nonce được claim nguyên tử thành công |
| **Fail closed** | Khi không xác minh đủ điều kiện thì không cấp authenticated principal |
| **Trust boundary** | Nơi dữ liệu từ nguồn không đáng tin phải được kiểm soát, xác minh lại |

Ví dụ ngắn: `keyId` từ HTTP request chỉ là **candidate selector**; client không được tin cậy chỉ vì khai một key ID có tồn tại. Chỉ khi server tra đúng credential, kiểm tra status/owner/suite và HMAC đúng dưới secret đó mới có bằng chứng xác thực. Sau đó còn timestamp, nonce và authorization.

## 2. Bản đồ tổng thể: từ bytes HTTP tới quyết định nghiệp vụ

~~~mermaid
flowchart TD
    C["Client / workload tin cậy"] --> K["Credential và shared secret"]
    C --> R["HTTP request gốc"]
    R --> CAN["Canonical request bytes theo version"]
    K --> MAC["HMAC(secret, canonical bytes)"]
    CAN --> MAC
    MAC --> SIG["Chữ ký HMAC / signature encoding"]
    SIG --> WIRE["Signed HTTP request qua HTTPS"]
    R --> WIRE

    WIRE --> GW["Gateway / reverse proxy"]
    GW --> PARSE["Bounded HTTP parser + trust boundary"]
    PARSE --> SELECT["Exact key ID + signing suite + policy"]
    SELECT --> VERIFY["Dựng canonical bytes và verify MAC"]
    VERIFY --> FRESH["Kiểm tra timestamp/freshness"]
    FRESH --> REPLAY["Atomic nonce claim / shared replay state"]
    REPLAY --> PRINCIPAL["Authenticated principal từ registry"]
    PRINCIPAL --> AUTHZ["Authorization tenant/action/resource"]
    AUTHZ --> BIZ["Business execution + idempotency"]
    BIZ --> RESP["HTTP response"]

    REG["Credential lifecycle / vault / revocation"] --> SELECT
    CLOCK["Clock & window policy"] --> FRESH
    STORE["Replay store nhất quán + TTL"] --> REPLAY
    POLICY["Permission / delegation / resource ownership"] --> AUTHZ
    OBS["Audit / metrics / tests / incident runbooks"] -.-> VERIFY
    OBS -.-> REPLAY
    OBS -.-> AUTHZ
    OBS -.-> RESP
~~~

Đây là **đường đi khái niệm**, không ép tất cả deployment phải đặt HMAC verifier ở backend: gateway có thể verify và gửi trusted assertion xuống backend. Điều bắt buộc là phải xác định **ai sở hữu quyết định authentication**, ai claim nonce, ai xác thực forwarded identity, và các thành phần ký/verify có cùng hiểu canonical bytes hay không.

### Một tập điều kiện logic

Có thể hình dung một lần authentication được chấp nhận khi:

\[
A =
C_{\mathrm{active}}
\land S_{\mathrm{allowed}}
\land M_{\mathrm{valid}}
\land T_{\mathrm{valid}}
\land N_{\mathrm{firstUse}}
\]

Trong đó:

- `C_active`: credential hợp lệ, đúng client/owner/key version, chưa bị revoke.
- `S_allowed`: signing suite/version được policy cho phép ở server/route/credential.
- `M_valid`: MAC khớp trên canonical bytes do server dựng lại.
- `T_valid`: signed timestamp nằm trong freshness window.
- `N_firstUse`: atomic nonce claim trả FIRST_USE trong replay scope đã định nghĩa.

Nếu thiếu khả năng xác định một thành phần do dependency outage (ví dụ Redis timeout), server **không được tự gán TRUE**; phải fail closed. Ngay cả khi `A=true`, business vẫn cần:

\[
Execute = A \land Authorization(principal, action, resource)
\]

Business idempotency là một kiểm soát **bổ sung**, không nằm trong định nghĩa MAC validity hay nonce first-use.

## 3. Ba câu hỏi không được gộp: bí mật, bằng chứng, quyền

Một trong những mối quan hệ quan trọng nhất của bản đồ:

~~~mermaid
flowchart LR
    S["Secret K ở client/server"] --> P["Proof: HMAC trên request"]
    P --> I["Authentication: principal đã kiểm chứng"]
    I --> Z["Authorization: có grant không?"]
    Z --> E["Business intent & side effects"]

    T["Timestamp + nonce state"] --> I
    R["Credential registry ACTIVE/REVOKED"] --> I
    A["Tenant/resource policy"] --> Z
    D["Idempotency key + transaction"] --> E
~~~

| Câu hỏi | Tầng quyết định | Phần dữ liệu quan trọng | Điều không được suy ra |
| --- | --- | --- | --- |
| Ai có key này? | Credential provisioning/registry | Key ID, secret, client owner, trạng thái | Secret tồn tại ≠ request hợp lệ |
| Request có thực sự được ký và chưa phát lại? | Authentication | Canonical bytes, MAC, signed timestamp, nonce claim | MAC đúng ≠ có quyền resource |
| Chủ thể có quyền gọi API với dữ liệu này không? | Authorization | Principal, tenant grant, action, resource owner | Tenant header được ký ≠ tenant được grant |
| Ý định nghiệp vụ đã được xử lý chưa? | Business idempotency | Idempotency key, payload binding, transaction state | Nonce mới ≠ ý định mới |

**Ví dụ:** `partner-a` có secret K4 của tenant-a. Client có thể tạo MAC hợp lệ cho request ghi `X-Tenant-Id: tenant-b`. Nếu tenant ID là signed field, HMAC chứng minh request **không bị sửa sau khi ký**, chứ không chứng minh `partner-a` được thao tác với tenant-b. Authorization phải kiểm tra grant trước khi xử lý.

Tương tự, một payment request có MAC đúng và nonce mới vẫn có thể mang cùng business idempotency key với một attempt đã thành công trước đó: authentication cho attempt mới pass, còn business layer quyết định trả cached result, conflict hoặc xử lý theo contract.

## 4. Nhánh mật mã: HMAC, hash, encoding và TLS liên quan thế nào?

### Khái niệm lõi

HMAC là **message authentication code** dùng secret key `K`:

\[
tag = \operatorname{HMAC}_{K}(\operatorname{canonicalize}(request))
\]

Một hệ thống thường dùng `HmacSHA256` với secret ngẫu nhiên mạnh. Nếu hợp đồng yêu cầu body hash, có thể tính:

\[
bodyDigest=\operatorname{SHA256}(rawBodyBytes)
\]

rồi đưa digest vào canonical request. Đây là **hai phép toán có mục đích khác nhau**:

- **SHA-256 body digest**: biểu diễn nội dung body trong chuỗi được ký; bản thân digest **không có secret**.
- **HMAC-SHA256**: gắn secret vào MAC trên canonical request; chứng minh tính toàn vẹn và bằng chứng biết secret.
- **Base64/hex**: chỉ là wire encoding của bytes, **không mã hóa bảo mật**.
- **TLS/HTTPS**: bảo vệ kênh truyền, peer identity và dữ liệu trên đường đi; HMAC bảo vệ các **trường được ký** ở mức ứng dụng, nhưng không thay thế TLS.

### Bản đồ phân biệt

| Thành phần | Bảo vệ | Không giải quyết |
| --- | --- | --- |
| SHA-256(body) | Tính toàn vẹn body khi **được HMAC ràng buộc** | Ai là client, secret, replay |
| HMAC-SHA256 | Integrity/authenticity cho canonical bytes | Confidentiality, replay, tenant grant |
| Base64(signature) | Truyền MAC bytes qua header | Encryption |
| HTTPS/TLS | Confidentiality/integrity kênh truyền và xác thực server/peer tùy mode | Tự động kiểm tra nonce hoặc business idempotency |
| CSPRNG | Sinh key và nonce có entropy cao | Atomic used-once state phía server |
| Constant-time compare | Giảm timing leakage khi so MAC | Toàn HTTP stack constant-time |
| KMS/HSM/secret manager | Quản lý/giới hạn truy cập key material | Canonicalization và authorization logic |

Một request có HMAC đúng vẫn có thể bị copy sau TLS termination trong gateway/log. Vì vậy **TLS + HMAC + timestamp/nonce** là các lớp bổ trợ, không thay thế nhau.

### Những hiểu nhầm cần gạch bỏ

- “Dùng SHA-512 thì khỏi cần nonce”: sai; thuật toán MAC mạnh không chống phát lại.
- “Digest body đã có, không cần ký digest”: sai; digest không có secret, attacker có thể thay body và tính digest mới.
- “Base64 là mã hóa bí mật”: sai; decode được trực tiếp.
- “Có HMAC nên có bằng chứng không thể chối bỏ”: sai với **shared secret**; cả hai phía đều biết secret.
- “Secret phải là một chuỗi 64 ký tự”: sai; key là bytes, entropy và generation policy mới quan trọng.

## 5. Nhánh canonicalization: ký cái gì và theo quy tắc nào?

Hai hệ thống có cùng secret và cùng thuật toán HMAC nhưng **canonicalize khác nhau** sẽ tính tag khác nhau. Đây là một nguyên nhân phổ biến của 401 khi đi qua SDK, gateway hoặc framework.

~~~mermaid
flowchart TD
    R["Raw HTTP request tại trust boundary"] --> M["Method"]
    R --> U["Request-target URI + query"]
    R --> H["Signed header names/values"]
    R --> B["Raw body bytes"]
    R --> F["Timestamp, nonce, key ID, suite ID"]
    M --> C["Versioned canonical encoder"]
    U --> C
    H --> C
    B --> HASH["Body digest theo contract"]
    HASH --> C
    F --> C
    C --> BYTES["Exact UTF-8 bytes / LF / escaping"]
    BYTES --> MAC["HMAC(secret, canonicalBytes)"]
~~~

### Contract ví dụ

Một profile tự thiết kế có thể quy định canonical text:

~~~text
HMAC-REQUEST-V1
hmac-v1-sha256
POST
/api/hmac/orders?currency=VND
application/json
partner-a
partner-a-prod-k004
2026-11-28T04:00:00Z
84a9b6c3-764e-40e3-a9b2-154fdb154f79
<lowercase-sha256-hex-of-raw-body>
~~~

Các dòng dùng **UTF-8, LF (0x0A), không có LF cuối** và giá trị body digest là **placeholder**, không phải vector đã tính MAC. Hợp đồng cụ thể của dự án có thể khác: không có một định dạng canonical HMAC duy nhất áp dụng cho mọi HTTP API.

**Những thuộc tính phải chốt chính xác:**

| Thành phần | Câu hỏi bắt buộc |
| --- | --- |
| Method | Uppercase? Lấy raw method ở điểm nào? |
| Path | Ký external hay internal path sau proxy rewrite? |
| Query | Giữ raw thứ tự hay sort? Duplicate params xử lý thế nào? |
| Percent encoding | `%2F` và `%2f` có tương đương không theo contract? |
| Header names | Lowercase trước ký? Chọn header nào? |
| Header values | Trim OWS? Gộp duplicate? Từ chối ambiguous? |
| Body | Ký compressed, decompressed hay raw bytes sau transfer decoding? |
| Content-Type | Có ký media type và charset không? |
| Timestamp | UTC format, precision, timezone, signed field? |
| Nonce | Encoding, length, syntax, signed? |
| Key ID/suite | Có đưa vào canonical bytes để chống confusion/downgrade không? |
| Signature | Base64 padded, Base64url hay hex? Exact length? |
| Version | Canonical contract nào của signing suite? |

### Ranh giới JSON

Hai JSON biểu diễn cùng object nhưng khác whitespace/property order có thể có **raw bytes khác nhau**:

~~~json
{"id":1,"amount":250000}
~~~

~~~json
{
  "amount": 250000,
  "id": 1
}
~~~

Nếu hợp đồng ký **raw body bytes**, hai payload này không có cùng digest. Đừng parse rồi serialize lại JSON để “sửa” signature mismatch, trừ khi protocol được **thiết kế và version hóa** để ký một JSON canonicalization chuẩn cụ thể.

### Header ambiguity

Nếu client gửi hai `X-Key-Id` hoặc `X-Timestamp`, proxy và app có thể chọn first/last khác nhau. Với security-critical signed headers, mặc định nên **reject duplicate/ambiguous input**, không thử nhiều cách diễn giải cho đến khi MAC pass.

## 6. Nhánh credential: key ID, secret, principal và lifecycle

~~~mermaid
flowchart LR
    ON["Onboarding được phê duyệt"] --> GEN["CSPRNG sinh secret K"]
    GEN --> VAULT["Vault/KMS/HSM"]
    GEN --> META["Credential registry"]
    META --> ID["keyId + credentialId + owner client/tenant"]
    META --> STATE["PENDING / ACTIVE / GRACE / REVOKED"]
    META --> SUITE["Signing suite grants"]
    VAULT --> VERIFY["Exact secret lookup"]
    ID --> VERIFY
    STATE --> VERIFY
    SUITE --> VERIFY
    VERIFY --> PR["Trusted principal sau MAC + replay"]
~~~

### Các thực thể khác nhau

| Thuật ngữ | Vai trò | Phân biệt quan trọng |
| --- | --- | --- |
| `clientId` | ID application/đối tác | Chỉ là claim tới khi registry+MAC verify |
| `keyId` | Chọn key/version | Thường không phải secret; không tự chứng minh identity |
| `credentialId` | Record nội bộ | Namespace audit/replay từ server |
| `secret` | Vật liệu HMAC | Bí mật ở cả client và server; không log |
| `ownerTenant` | Chủ sở hữu key từ registry | Không lấy từ tenant header chưa được auth |
| `signingSuite` | MAC+canonical version được phép | Runtime hỗ trợ ≠ credential được phép |
| `principal` | Identity đã authenticated | Chỉ tạo sau MAC và anti-replay đạt |
| `grants` | Quyền truy cập | Authorization quyết định riêng |

### Lifecycle có trạng thái

~~~text
REQUESTED -> APPROVED -> GENERATED -> PENDING_DELIVERY
    -> PENDING_ACTIVATION -> ACTIVE -> GRACE -> REVOKED
                               |                 ^
                               +-> EXPIRED ------+
~~~

State machine chỉ là mô hình tham khảo; tên và transitions do sản phẩm định nghĩa. Một key `REVOKED` hoặc `EXPIRED` phải bị reject **dù MAC toán học đúng**. Rotation nên cấp **key ID/version mới**, có overlap được quản lý; không “ghi đè” secret K4 tại chỗ hoặc thử secret K3 fallback khi request khai K4.

### Cách cấp secret an toàn

- Secret được sinh bằng **CSPRNG**, ví dụ 32 byte ngẫu nhiên cho HMAC-SHA256 theo policy.
- Mỗi credential/client/environment/suite có key material độc lập khi thích hợp.
- Secret nằm trong vault/KMS/HSM, IAM least privilege, TLS in transit, audit truy cập.
- Phân phối qua **one-time authenticated retrieval** hoặc secure provisioning, không gửi trong email/ticket/query URL.
- Client chứng minh sở hữu key (PoP challenge) nếu quy trình yêu cầu; activation theo approval và policy.
- Không đưa shared secret vào JavaScript public/browser/mobile bundle vì không bảo mật được bí mật chung trên public client.
- Key leak → revoke/rotate; chỉ xóa khỏi Git/log không đủ.

## 7. Nhánh signing suite: algorithm agility là thay đổi có kiểm soát

Một `signing suite` nên bundle **primitive MAC, canonicalization, body digest, encoding và replay policy** thành một version đã kiểm thử. Ví dụ:

| Suite | MAC | Canonical contract | Key policy |
| --- | --- | --- | --- |
| `hmac-v1-sha256` | `HmacSHA256` | `HMAC-REQUEST-V1` | K3/V1 enabled trong overlap |
| `hmac-v2-sha512` | `HmacSHA512` | `HMAC-REQUEST-V2` | K4/V2 provisioned, route cho phép |

Server có thể có provider `HmacSHA512` nhưng credential K3 chưa provision key V2; vậy không được nhận V2 chỉ vì client khai V2.

~~~text
effectiveAllowedSuites
  = runtimeCapabilities
  ∩ deployedImplementations
  ∩ globalSecurityPolicy
  ∩ routePolicy
  ∩ credentialGrant
~~~

**Không tự fallback** từ V2 sang V1 khi MAC mismatch hoặc Redis lỗi. Nếu migration có giai đoạn dual acceptance, server chọn **một suite được ký, được policy cho phép cho credential**, không thử `old.verify || new.verify`.

### Lỗi downgrade trên bản đồ

~~~mermaid
flowchart TD
    A["Client ký suite V2 / key K4"] --> B["Server chọn V2 theo allowlist"]
    B --> C{"V2 MAC/credential valid?"}
    C -->|Có| D["Đi tới timestamp + nonce"]
    C -->|Không| X["Reject, không fallback"]
    C -. "SAI: thử V1/K3" .-> V["Downgrade / algorithm confusion"]
~~~

Khi chuyển phiên bản canonicalization hoặc MAC, cần **golden vectors độc lập** và có thể cần **dual signatures** nếu muốn chạy shadow V2. Chữ ký V1 không tự chứng minh V2 valid khi bytes/key/algorithm khác nhau.

## 8. Nhánh freshness: timestamp không thay nonce

Một request có HMAC đúng nhưng được gửi lại vẫn có **cùng MAC đúng**. Muốn giới hạn replay, thường cần:

\[
Freshness = TimestampWithinWindow \land NonceFirstUse
\]

| Khái niệm | Trả lời | Thiếu gì nếu chỉ có một mình? |
| --- | --- | --- |
| Timestamp được ký | Request còn trong khoảng thời gian chấp nhận không? | Không chứng minh chưa sử dụng trong window |
| Nonce được ký | Bằng chứng mang định danh attempt nào? | Phải có store used-once |
| Atomic nonce claim | Nonce còn mới trong scope đã định nghĩa không? | Phải có signed binding, expiry và consistency |
| Replay TTL | Duy trì state đến khi signature hết hiệu lực? | Không chữa lỗi cross-node/failover |
| Client retry | Một business intent có attempt mới không? | Cần nonce mới và idempotency key riêng |

Một nonce random 128-bit khó bị **trùng do ngẫu nhiên**, nhưng exact replay tái dùng chính nonce N đã quan sát. Độ ngẫu nhiên của nonce **không làm server tự nhớ** đã thấy N.

### Timestamp-only là anti-pattern

Ví dụ window `±5 phút`: R1 ký tại 04:00 được chấp nhận, R2 copy y nguyên tại 04:01 vẫn trong cửa sổ. Nếu server chỉ check timestamp+HMAC, cả hai được authenticated.

Nếu nonce không nằm trong canonical bytes, attacker có thể đổi `X-Nonce: N1` thành `N2` và giữ MAC cũ. Do đó **timestamp và nonce đều phải được ràng buộc vào chữ ký**.

### Thứ tự chặn nonce poisoning

~~~mermaid
flowchart TD
    R["Request"] --> P["Parse/limit"]
    P --> T["Validate timestamp format/window"]
    T --> C["Resolve exact credential + canonical bytes"]
    C --> M{"MAC đúng?"}
    M -->|Không| X["Reject; KHÔNG ghi nonce"]
    M -->|Có| N["Atomic claim nonce"]
    N -->|FIRST_USE| A["Authentication pass"]
    N -->|ALREADY_USED| B["Replay rejected"]
    N -->|UNKNOWN| U["Fail closed"]
~~~

Nếu ghi nonce trước MAC, attacker không biết secret vẫn có thể chiếm nonce N của người hợp lệ (khi đoán/quan sát được), khiến request thật bị từ chối: **nonce poisoning**.

## 9. Nhánh replay store: atomicity, scope, TTL và consistency

**Replay store** là nguồn quyết định một nonce đã được dùng chưa. Một primitive thường thấy với Redis:

~~~redis
SET hmac:nonce:<opaque-digest-of-scope-and-nonce> 1 NX PX 660000
~~~

`SET NX PX` dùng một thao tác conditional insert với TTL, thay vì `GET` rồi `SET` tạo race condition. `660000` ms = 11 phút là **minh họa**, chỉ đúng nếu phù hợp acceptance window và margin của profile triển khai.

### Key scope

Một replay key nên được ràng buộc vào **trusted identity** do registry cung cấp:

~~~text
replayScope = credentialIdFromTrustedRegistry
replayKey   = digest(encodeLengthPrefixed(scope, signedNonce))
~~~

`digest` chỉ là cách encode opaque key, không phải thay cho MAC security. Dùng length-prefixed encoding để tránh tuple ambiguity. Các lựa chọn scope có trade-off:

| Scope | Điều gì được chặn? | Cần đánh giá |
| --- | --- | --- |
| `credentialId + nonce` | Một nonce không dùng lại trên credential đó | Key rotation có namespace riêng |
| `trustedClientId + nonce` | Có thể chặn xuyên key versions cùng client | Granularity, traffic, availability |
| `credentialId + suiteId + nonce` | Chỉ trong cùng suite | Có thể mở replay xuyên suite |
| `clientProvidedTenant + nonce` | Phụ thuộc claim chưa tin | Nguy cơ bypass nếu tenant đổi |
| `IP + nonce` | Phụ thuộc IP/proxy | Không đại diện identity thật |

### TTL phải bao phủ cửa sổ còn hợp lệ

Với timestamp window đối xứng `±W`, một request ký ở mép tương lai có thể còn hợp lệ gần **2W** sau lần claim đầu. Vì vậy, nếu TTL tính từ lúc claim, một cấu hình bảo thủ:

\[
TTL_{\mathrm{nonce}} \ge 2W+\epsilon
\]

với margin `ε` cho clock precision/skew và chính sách thực tế. Với `W=5 phút`, **11 phút** có thể là ví dụ. Nếu policy chỉ nhận timestamp quá khứ hoặc expiry gắn với signed time, cách tính khác; phải **chứng minh retention**, không sao chép 11 phút cho mọi sản phẩm.

### Trạng thái claim và hệ quả

| Outcome | Có chắc first-use? | Hành động |
| --- | --- | --- |
| `FIRST_USE` | Có trong consistency model đã cam kết | Có thể tiếp tục principal/authz |
| `ALREADY_USED` | Nonce đã được lưu | Reject authentication/replay |
| `UNKNOWN` / timeout / lost ACK | **Không** | Fail closed, thường 503 |
| Store down | Không thể xác minh | Fail closed; không local fallback |
| Key evicted sớm | Replay state bị mất | Security incident/retention violation |

**Redis replication/failover và đa vùng** không tự bảo đảm global at-most-one claim chỉ vì có `SET NX` trên một primary. Cần thiết kế/kiểm thử consistency, loss-of-ACK, eviction, failover và region partitions theo security guarantee đã công bố.

## 10. Nhánh Spring Security: Authentication trước, Authorization sau

Spring Security cung cấp **authentication/authorization pipeline**, nhưng **không tự định nghĩa một giao thức HMAC request signing chung**. Ứng dụng phải xây filter/provider cho suite HMAC cụ thể, request canonicalizer, key registry và replay guard rồi tích hợp vào security chain.

~~~mermaid
flowchart LR
    A["HTTP security filter / WebFilter"] --> P["AuthenticationManager / ReactiveAuthenticationManager"]
    P --> C["Credential + MAC + freshness"]
    C --> N["Atomic nonce claim"]
    N --> I["Authentication principal"]
    I --> S["SecurityContext / Reactor Context"]
    S --> Z["AuthorizationManager / policy"]
    Z --> H["Controller / handler"]
~~~

### Spring MVC/Servlet

| Lớp | Chức năng | Điều cần chú ý |
| --- | --- | --- |
| `OncePerRequestFilter` | Đọc envelope/HMAC headers/body theo route | Không đăng ký trùng, kiểm soát dispatch |
| Bounded request wrapper | Giữ raw body bytes để verify và đọc tiếp | Không buffer vô hạn; downstream đọc đúng bytes |
| `AuthenticationManager` | Điều phối AuthenticationProvider | Từ chối ngay khi proof không hợp lệ |
| `AuthenticationProvider` | Lookup key, policy, MAC, timestamp, nonce | Không tự thử nhiều keys/algorithms |
| `AuthenticationEntryPoint` | Trả lỗi authentication | 401 an toàn, HMAC challenge nếu API có định nghĩa |
| `AccessDeniedHandler` | Trả lỗi authorization | 403/404 theo policy |
| `SecurityContextHolder` | Lưu authenticated principal cho request | Không tin header client khai |

Nếu filter nằm **trước** `DispatcherServlet`, `@RestControllerAdvice` không mặc định bắt exception từ mọi filter. HMAC filter cần được đặt và kết nối với Spring Security failure handling đúng vị trí, hoặc tự chuyển exception tới entry point theo cấu hình.

### Spring WebFlux

| Lớp | Chức năng | Chú ý |
| --- | --- | --- |
| `SecurityWebFilterChain` | Định tuyến reactive security | Match chính xác protected routes |
| `ReactiveAuthenticationManager` | Verify HMAC bất đồng bộ | Không `block()` trên event loop |
| `Flux<DataBuffer>` | Raw request body | Bounded capture, release/cancel, replay downstream |
| Reactive Redis client | Atomic nonce claim | Compose vào chain, không `subscribe()` fire-and-forget |
| `ServerAuthenticationEntryPoint` | Map authentication failure | Không biến Redis outage thành bad MAC |
| `ReactiveSecurityContextHolder` | Request-scoped identity | Không rò context qua requests |

Không có lý do gì để authentication đã pass trước khi nonce store xác nhận `FIRST_USE`. Một `Mono<Authentication>` không được emit principal khi claim trả `UNKNOWN`.

### Kiến trúc tích hợp khuyến nghị

Nên tách **HTTP adapter**, **pure MAC verifier**, **credential policy**, **freshness validator**, **replay store** và **Spring Security adapter**. Cách này giúp kiểm thử từng nhánh bản đồ, giữ business controller không biết chi tiết MAC/HMAC.

## 11. Nhánh gateway/proxy: ai xác thực, ai chịu trách nhiệm nonce?

Trong hệ thống thực, request hiếm khi đi thẳng từ client đến controller. Có thể có CDN, WAF, API gateway, ingress, reverse proxy và backend. Mỗi tầng có thể chuẩn hóa URI, signed headers, content encoding và trust context.

~~~mermaid
flowchart LR
    C["Client ký external request"] --> G["Gateway / TLS termination"]
    G --> H["HMAC verification tại gateway hoặc backend"]
    H --> R[("Authoritative replay store")]
    H --> P["Trusted identity"]
    P --> B["Backend authorization"]
    B --> A["Application"]
~~~

### Mô hình A: gateway verify HMAC

Gateway kiểm tra MAC, key state, timestamp và **claim nonce**. Backend không bắt buộc giữ raw client secret; nó nhận **trusted identity assertion** đã được bảo vệ bằng mTLS/workload identity hoặc chữ ký nội bộ có issuer, audience, expiration và request binding.

Bản đồ quan hệ:

~~~text
Client HMAC proof
    -> Gateway verify + claim nonce
    -> Trusted internal identity assertion
    -> Backend verify assertion + authorization
    -> Business
~~~

**Điều kiện:** client không thể tự gửi `X-Authenticated-Client` rồi backend tin. Gateway cần strip/reject forwarded identity headers từ Internet; backend chỉ chấp nhận assertion của trusted gateway. Nếu gateway đã claim client nonce, backend **không claim lại chính nonce** trên cùng replay key. Internal assertion có thể cần `jti`/anti-replay riêng.

### Mô hình B: backend verify HMAC

Gateway chỉ forward signed request đến backend; backend dùng secret từ vault/registry để verify. Khi đó:

- Canonical method/URI phải xác định từ **external** hay **internal** target.
- Header normalization và duplicate signed headers phải thống nhất.
- Body transformations (JSON rewrite, gzip decompress, transfer decoding) phải tuân đúng contract.
- Direct backend bypass gateway không được làm mất security filter hoặc trust controls.
- Multi-gateway traffic phải dùng replay authority nhất quán.

### Tình huống giải thích lỗi

~~~text
Client ký:  POST /public/orders?currency=VND
Gateway chuyển: POST /internal/orders?currency=VND
Backend verify: /internal/orders?currency=VND
~~~

Nếu hợp đồng yêu cầu ký **external target**, MAC mismatch là hợp lý: server đang dựng khác bytes. Cách sửa là định nghĩa/verifier tin external target qua một **trusted ingress mechanism**, không chọn bất kỳ `X-Original-URI` do Internet client khai hoặc “thử thêm path khác cho tới khi pass”.

## 12. Nhánh tenant: request được ký khác với request được cấp quyền

**Authentication** trả lời “ai sở hữu credential đã ký request?”. **Authorization** trả lời “principal đó có được thao tác action/resource/tenant này không?”.

~~~mermaid
flowchart TD
    H["Signed request: clientId=partner-a, tenant=b"] --> V["HMAC + timestamp + nonce"]
    V --> I["Principal từ registry: partner-a, ownerTenant=a"]
    I --> A{"Có grant tenant-b + action + resource?"}
    A -->|Không| X["403/404 theo policy"]
    A -->|Có| B["Business handler"]
~~~

Ngay cả khi `tenant=b` được HMAC ký, nó vẫn chỉ là **claim không bị sửa**. Server phải so claim với policy được cấp từ hệ thống đáng tin: scope, role, delegation và resource ownership. Không set `SecurityContext` tenant từ header trước khi authn và không suy quyền từ key ID string pattern.

### Những cặp cần phân biệt

| Cặp khái niệm | Không đồng nghĩa vì |
| --- | --- |
| `keyId` ≠ `principal` | Key ID là lookup selector, principal chỉ tồn tại sau verify |
| `clientId` ≠ `tenantGrant` | Một client có thể phục vụ nhiều tenant theo policy |
| `signedTenant` ≠ `authorizedTenant` | Integrity của claim không cấp permission |
| `role/authority` ≠ HMAC signature | Role xuất phát từ policy, không từ MAC bytes |
| `403` ≠ `401` | 403 thường khi đã authenticated nhưng thiếu quyền |
| `404` ≠ “không có quyền” trong mọi API | Có thể che resource existence theo policy |

### Một kịch bản 4 request

1. **R1:** K4 ACTIVE, MAC đúng, N1 mới, tenant-a có grant → authentication và authorization pass.
2. **R2:** R1 exact replay → authentication reject, dù tenant-a có grant.
3. **R3:** K4 đúng, N3 mới, tenant-b không có grant → authentication pass, authorization deny 403/404.
4. **R4:** Client đổi tenant-a→tenant-b giữ MAC cũ → MAC mismatch nếu tenant là signed field.

Bốn kết quả khác nhau không thể được giải thích chỉ bằng việc “HMAC đã đúng hay chưa”.

## 13. Nhánh HTTP error semantics: lỗi thuộc tầng nào?

Chọn error semantics là một phần kiến trúc, không chỉ là làm đẹp JSON response.

| Tình huống | Tầng quyết định | Public HTTP gợi ý | Internal reason |
| --- | --- | --- | --- |
| HTTP framing sai, signed header duplicate | Parsing/protocol | 400 | `MALFORMED_HMAC_ENVELOPE` |
| Body quá giới hạn | Resource limit | 413 | `BODY_TOO_LARGE` |
| Media type không hỗ trợ | API contract | 415 | `UNSUPPORTED_MEDIA_TYPE` |
| Key không tồn tại hoặc revoked | Authentication | 401 chung | `KEY_NOT_FOUND` / `CREDENTIAL_REVOKED` |
| Signature sai | Authentication | 401 chung | `SIGNATURE_MISMATCH` |
| Timestamp ngoài window | Authentication/freshness | 401 chung | `TIMESTAMP_OUT_OF_WINDOW` |
| Nonce đã dùng | Authentication/replay | 401 chung | `REPLAY_DETECTED` |
| Redis/secret manager unknown/unavailable | Auth dependency | 503, fail closed | `AUTH_DEPENDENCY_UNAVAILABLE` |
| Principal thiếu quyền tenant/action | Authorization | 403/404 theo policy | `ACCESS_DENIED` |
| Cùng idempotency key, payload khác | Domain/business | 409 | `IDEMPOTENCY_CONFLICT` |
| Quá rate/quota | Admission | 429 | `RATE_LIMIT_EXCEEDED` |
| Unexpected application bug | Runtime | 500 | `INTERNAL_ERROR` |

Đây là **profile tham khảo**; 400/401 cho invalid envelope, 403/404 resource hiding, hoặc 5xx gateway có thể khác theo contract nhưng phải **nhất quán và bảo mật**.

### Public vs internal reasons

Một public response 401 nên tránh xác nhận key ID tồn tại, secret đã revoke hoặc nonce đã dùng. Có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
WWW-Authenticate: HMAC realm="api"

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "code": "AUTHENTICATION_FAILED",
  "detail": "Authentication is required or invalid."
}
~~~

Đây là **custom challenge profile minh họa**: chỉ dùng `WWW-Authenticate: HMAC realm="api"` khi ứng dụng **đã định nghĩa scheme này**. Spring Security không có một challenge HMAC chuẩn áp dụng cho mọi ứng dụng. `code` là field extension nếu dùng Problem Details (RFC 9457).

### Ba lý do trông giống nhau, ba cách xử lý

~~~text
R1: signature mismatch       -> 401, client sửa signer/key.
R2: nonce already used       -> 401, không replay; retry cần nonce mới.
R3: Redis timeout / UNKNOWN  -> 503, fail closed, xử lý availability.
~~~

Không trả `409` cho authentication nonce replay; `409` thích hợp cho conflict ở **business idempotency** sau khi authentication đã pass. Không trả 401 cho Redis timeout rồi khiến client tự rotate key vô ích. Không biến 503 thành “accept anyway”.

### Oracle và timing

Response khác biệt giữa `unknown key` và `known key bad MAC` có thể tạo **credential enumeration oracle**. Public status/body/headers nên tối giản; internal logs lưu reason enum, không log raw key material, expected MAC, full signature hoặc canonical bytes. `MessageDigest.isEqual` hỗ trợ so MAC phù hợp, nhưng không bảo đảm **toàn HTTP pipeline** có thời gian xử lý constant-time.

## 14. Nhánh retry: nonce chống replay khác idempotency nghiệp vụ

Một client có thể không nhận được response vì timeout dù server đã thực thi POST. Nếu client retry **nguyên chữ ký/nonce**, replay guard sẽ từ chối và đó là hành vi đúng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as HMAC Server
    participant N as Nonce Store
    participant B as Business / Idempotency
    C->>S: POST intent I, timestamp T1, nonce N1, MAC1
    S->>N: Claim N1
    N-->>S: FIRST_USE
    S->>B: Execute I / save idempotency result
    S--xC: Response lost
    C->>S: Retry intent I, timestamp T2, nonce N2, MAC2
    S->>N: Claim N2
    N-->>S: FIRST_USE
    S->>B: Same idempotency key & payload binding
    B-->>C: Stored result, no duplicated intent
~~~

### Khái niệm cần đặt cạnh nhau

| Khái niệm | Key được dùng | Mục đích |
| --- | --- | --- |
| HTTP request nonce | Signed nonce + trusted credential/client scope | Chặn *same authentication evidence* dùng hai lần |
| Business idempotency key | Principal/tenant/action/intent + request binding | Chặn *cùng business intent* tạo hai side effects |
| Transaction ID | DB/outbox/payment transaction | Ghi nhận business state/atomicity |
| Correlation ID | Tracing | Tìm log, không chặn replay |
| Timestamp | Freshness | Giới hạn tuổi signature, không used-once |

**Không dùng requestId/correlationId làm nonce mặc định** nếu không bảo đảm uniqueness/signed binding/lifecycle. Không dùng nonce HMAC làm idempotency key: mỗi retry bảo mật đúng **cần nonce mới**, trong khi business intent **cần idempotency key cũ**.

### Hậu quả khi claim nonce rồi lỗi 500

Khi nonce đã claim thành công nhưng controller/DB trả 500, server không nên xóa nonce để client có thể gửi lại cùng signed request. Side effect có thể đã xảy ra trước lỗi. Client ký attempt mới, giữ idempotency key nếu intent không đổi và sử dụng status lookup/reconciliation nếu cần.

## 15. Nhánh vận hành: cấp, rotate, revoke và quan sát credential

Một hệ thống HMAC không chỉ có code verifier. Nó còn có **provisioning workflow** và trách nhiệm bảo mật vận hành.

~~~mermaid
flowchart TD
    R["Request credential"] --> A["Verify identity + approve scope"]
    A --> G["Generate independent high-entropy secret"]
    G --> V["Store in Vault / KMS / HSM"]
    V --> D["Secure one-time retrieval"]
    D --> P["Proof of possession / activation"]
    P --> O["ACTIVE credential + exact key ID"]
    O --> S["Signed requests + audit"]
    S --> N["Rotation: new key ID & secret"]
    N --> G2["Provision / canary / overlap"]
    G2 --> X["Revoke old key"]
    O --> I["Incident: credential compromise"]
    I --> X
~~~

### Một runbook tối thiểu

1. Xác minh danh tính đối tác/workload và quyền yêu cầu cấp key.
2. Chốt environment, signing suite, allowed routes/audience và tenant grants.
3. Sinh secret bằng CSPRNG/KMS, không dựa `UUID` hoặc timestamp như key material.
4. Lưu secret tại secret manager có IAM/audit, metadata registry giữ key ID/reference và status.
5. Phân phối qua kênh được xác thực, one-time retrieval hoặc phương án approved; không đưa secret vào ticket/chat/URL.
6. Kích hoạt theo approval/PoP và `notBefore`/`notAfter` policy.
7. Kiểm tra signed request **positive** và wrong-MAC/replay/tenant negative.
8. Rotate bằng **key ID mới**, overlap có hạn rồi revoke key cũ.
9. Khi leak secret: revoke ngay theo incident policy, invalidate caches, điều tra blast radius và provision khóa mới.
10. Monitor credential/key state convergence qua gateway/region.

### Lỗi vận hành nguy hiểm

- “Secret K3 bị lộ nhưng chỉ xóa commit”: chưa revoke key.
- “K4 có MAC đúng nên K3 cũng nên được thử”: tạo key fallback/downgrade.
- “K3 revoked nhưng một pod còn cache ACTIVE”: security incident cần kiểm tra freshness.
- “Gateway A có V2, B chưa có nhưng quảng bá V2 toàn cục”: capability mismatch.
- “Có Redis outage thì dùng local nonce HashSet”: fail-open so với global replay guarantee.

## 16. Nhánh monitoring: những tín hiệu nào chứng minh hệ thống hoạt động?

Quan sát chỉ hữu ích khi gắn với **stage và mục tiêu** của bản đồ khái niệm.

| Câu hỏi vận hành | Tín hiệu / metric logic | Điều cần tránh |
| --- | --- | --- |
| Client sai signature tăng? | `hmac_auth_attempts_total{reason="signature_mismatch"}` | Đoán nguyên nhân canonical cụ thể mà không có evidence |
| Nonce được claim đúng? | `hmac_nonce_claims_total{outcome=...}` | Đếm 401 làm bằng chứng replay |
| Redis/vault lỗi? | `hmac_auth_dependency_errors_total` | Map thành client invalid 401 |
| Key revoked còn pass? | Revoked-key synthetic probes và audit decision | Chỉ tin rằng event revoke đã được gửi |
| Gateway/region cùng policy? | Capability/policy revision theo region | Quảng bá suite chưa deploy đủ |
| Có cross-tenant deny? | `hmac_authz_denied_total{reason=...}` | Log nguyên tenant ID vào Prometheus labels |
| Body/HMAC tốn CPU? | Stage latency p95/p99, body-size distribution | Hash vô hạn trước size limit |
| Có retry duplicate business? | Idempotency conflict + DB/outbox consistency | Dùng nonce metric thay business metric |
| Error contract có lệch? | Public status/code by route/gateway | Dựa vào HTML upstream error khó parse |

Metric labels nên giới hạn ở `route template`, `suite enum`, `result`, `reason enum` và region nhóm hữu hạn. **Không dùng** raw secret, key ID, client ID, tenant ID, nonce, full signature, raw URI/body hoặc request ID làm labels.

### Ba cảnh báo nhất thiết có runbook

- **Nonce UNKNOWN nhưng HTTP 2xx:** có thể fail-open, ưu tiên điều tra security boundary.
- **Revoked credential vẫn authenticated:** cache/state propagation violation.
- **Exact replay synthetic probe được accept hai lần:** broken replay guarantee; không chờ business double-charge mới xử lý.

### Logging và privacy

Để debug canonical mismatch, ghi stage, signing suite version, size/route template, correlation ID được kiểm soát và reason enum. Không in toàn bộ signed request/expected MAC/secret vào production logs: một bộ request headers+body+signature còn hạn có thể được sử dụng để replay.

## 17. Bản đồ kiểm thử: chứng minh từng liên kết thay vì chỉ HTTP 2xx

Một test **R1 hợp lệ** chứng minh rất ít nếu thiếu test phủ định. Bộ kiểm thử cần chứng minh các **đường liên kết**:

~~~mermaid
flowchart TD
    A["Raw request fixture"] --> B["Golden canonical bytes"]
    B --> C["Independent HMAC test vector"]
    C --> D["HTTP filter/provider integration"]
    D --> E["Atomic nonce + concurrency tests"]
    E --> F["Gateway/region E2E"]
    F --> G["Fault injection / incident rehearsal"]
    D --> H["Tenant/resource authorization"]
    H --> I["No unauthorized business side effect"]
~~~

### Test pyramid

| Tầng | Cần chứng minh | Ví dụ |
| --- | --- | --- |
| Unit cryptographic | MAC bytes đúng, encoding, fixed key | HMAC-SHA256 known-answer vector |
| Canonical contract | Client/server cùng exact bytes | URI/query/header/body golden fixtures |
| Policy unit | Key/suite/tenant được phép đúng | K4 active, K3 revoked, V2 not provisioned |
| Replay unit | Wrong MAC không claim; R2 rejected | Fake atomic store + fixed Clock |
| Redis integration | SET NX TTL + UNKNOWN fail closed | Real Redis test environment |
| Spring MVC/WebFlux | Filter chain/context/body đúng | MockMvc, WebTestClient |
| Gateway E2E | Raw target/trusted headers/proxy parity | External path, gzip, HTTP/2 |
| Distributed | Single first-use trong phạm vi bảo vệ | Concurrent requests across pods/regions |
| Failure injection | Vault/Redis timeout, lost ACK, failover | Không principal/business trên UNKNOWN |
| Security regression | Key revoke, downgrade, authz, privacy | Revoke propagation/cross-tenant tests |

### Positive control trước negative assertions

Nếu bạn chỉ gửi một request với signature sai và nhận 401, test đó vẫn pass khi filter **luôn trả 401**, hoặc khi key chưa được provision. Với replay:

~~~text
1. Provision test K4 ACTIVE, fixed Clock và golden signer độc lập.
2. R1: signed request có nonce N1 mới, MAC đúng -> pass.
3. R2: exact copy R1 trong window -> authentication reject.
4. Assert R2 internal REPLAY_DETECTED, không business side effect thứ hai.
5. R3: MAC sai, nonce N3 mới -> reject, store không claim N3.
6. R4: MAC đúng, giữ N3 -> FIRST_USE; phát hiện nonce poisoning.
~~~

Sau đó mới mở rộng sang multi-instance, cross-region, TTL boundary, gateway rewrite, Redis timeout và credential revocation. Trong test đa tenant, HMAC valid+nonce fresh nhưng tenant grant deny phải trả **authorization failure**, không phải authn failure.

## 18. Nhánh chọn kiến trúc: quyết định nào tác động nhiều nhánh nhất?

Một architecture review nên đặt các lựa chọn thành **decision records**:

| Quyết định | Option A | Option B | Điểm phải đánh giá |
| --- | --- | --- | --- |
| Verify HMAC tại đâu? | Gateway | Backend | Trust boundary, secrets, internal assertion |
| Replay scope là gì? | Credential | Client principal | Key rotation/cross-key replay |
| Nonce store nào? | Shared Redis | Strongly consistent service/DB | Atomicity, TTL, failover, p99 |
| Canonical target ở đâu? | External path | Internal path | Proxy rewrite, signed metadata trust |
| Body signing thế nào? | Raw-body digest | Versioned canonical structured body | Interoperability, streaming, security |
| Suite migration thế nào? | Server-chosen allowlist | Dual-protocol phase | No downgrade, key grants, test vectors |
| Secret storage thế nào? | Vault/KMS | HSM key handle | IAM, performance, operational burden |
| Auth error public chi tiết mức nào? | Generic 401 | Detailed errors via authenticated management | Credential/nonce oracle, SDK support |
| Retry side effect thế nào? | Idempotency key | Status lookup/reconciliation | Unknown outcome sau timeout |
| Region replay guarantee? | Region-bound | Global | Routing, partition, consistency, availability |

Không có một đáp án tối ưu cho mọi hệ thống. Nhưng các **thuộc tính bắt buộc** không nên thay đổi theo lựa chọn: no secret leak, exact key lookup, signed canonical fields, no nonce poisoning, fail closed, authorization độc lập và không thực thi business trước authentication.

### Một ADR dạng rút gọn

~~~text
Decision: HMAC verification at API Gateway
Scope: partner server-to-server payment API
Signing contract: HMAC-REQUEST-V2, versioned canonical raw target
Key lookup: exact key ID from trusted credential registry
Replay: atomic shared store, scope=(credentialId, signedNonce)
Nonce claim: gateway after MAC verified
Internal identity: mTLS + signed assertion with request binding
Authorization: backend principal/tenant/resource policy
Failure policy: generic 401 authn; 503 replay unknown; 403/404 authz
Rollback: cannot restore revoked keys or fail-open nonce behavior
Evidence: conformance vectors, concurrency and failover E2E
~~~

Đây là **ví dụ ADR**, chưa đại diện deployment cụ thể. Nếu backend được phép nhận traffic trực tiếp ngoài gateway, cần bảo vệ bypass route hoặc chuyển HMAC verification về backend.

## 19. Mô hình mã: phần nào nên tách thành interface?

Để biến bản đồ thành code Java 17/Spring Security, tránh một `GodFilter` làm tất cả từ parse HTTP đến Redis, authority và business:

~~~java
import java.time.Instant;
import java.util.Set;

record HmacEnvelope(
    String keyId,
    String suiteId,
    String timestamp,
    String nonce,
    byte[] receivedSignature
) {}

record TrustedCredential(
    String credentialId,
    String clientId,
    String ownerTenant,
    String signingSuite,
    boolean active,
    Set<String> grants
) {}

enum ReplayOutcome {
    FIRST_USE, ALREADY_USED, UNKNOWN
}

interface CredentialResolver {
    TrustedCredential findExactKeyId(String keyId);
}

interface CanonicalRequestBuilder {
    byte[] build(HttpRequestEvidence request,
                 HmacEnvelope envelope,
                 String signingSuite);
}

interface MacVerifier {
    boolean matches(TrustedCredential credential,
                    byte[] canonicalBytes,
                    byte[] receivedSignature);
}

interface FreshnessValidator {
    boolean withinWindow(String signedTimestamp,
                         Instant observedAt);
}

interface ReplayClaimStore {
    ReplayOutcome claim(String trustedCredentialId,
                        String validatedNonce);
}

interface AuthorizationPolicy {
    boolean permits(TrustedCredential principal,
                    String requestedTenant,
                    String action,
                    String resourceId);
}
~~~

`HttpRequestEvidence` là **abstraction dự án** đại diện method, raw target, bounded signed headers và raw body/digest đã lấy từ HTTP thật; không phải class chuẩn Java. `TrustedCredential.grants` chỉ là ví dụ data model. Không bao giờ cho client truyền thẳng `TrustedCredential` như nguồn tin cậy.

### Luồng điều phối khái niệm

~~~text
parseBoundedHttpRequest(request)
  -> parseStrictHmacEnvelope(request)
  -> resolveExactCredential(keyId)
  -> check ACTIVE + allowed suite + audience
  -> serverBuildCanonicalBytes(...)
  -> verify MAC using exact secret
  -> validate timestamp, signed nonce grammar
  -> atomic claim trusted scope + nonce
     FIRST_USE -> create authenticated principal
     ALREADY_USED -> authentication reject
     UNKNOWN -> fail closed / dependency unavailable
  -> authorize principal + tenant + action + resource
  -> execute business with idempotency
~~~

### Những ràng buộc không thể bỏ

- MAC verifier chỉ dùng **một key được chọn bởi exact key ID** và một suite được policy cho phép.
- Replay store chỉ được gọi **sau** MAC đúng.
- Không dùng `boolean firstUse` nếu cần phân biệt timeout/UNKNOWN.
- Bất kỳ store/dependency error nào phải được map có type, không nuốt thành success.
- **Authentication result khác Authorization decision**.
- Không dùng `HmacEnvelope` từ request để cấp principal khi không xác minh.
- Key material qua vault/HSM abstraction; không log hoặc expose `secretBytes`.

## 20. Đi theo một request thật: từ HTTP đến quyết định cuối

Giả sử đối tác `partner-a` đã được cấp key `K4`, signing suite `HMAC-REQUEST-V1` và quyền tạo đơn hàng tenant-a.

~~~http
POST /api/hmac/orders?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-prod-k004
X-Signing-Suite: hmac-v1-sha256
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 84a9b6c3-764e-40e3-a9b2-154fdb154f79
X-Tenant-Id: tenant-a
X-Signature: <base64-signature>
Idempotency-Key: order-intent-401

{"orderId":"o-401","amount":250000}
~~~

Request trên là **minh họa**, không có MAC thực. Một signer/verifier đúng hợp đồng phải xác định `Idempotency-Key` và `X-Tenant-Id` có thuộc signed scope không; với API nghiệp vụ nhạy cảm, nên ràng buộc cả **business intent và tenant claim** vào chữ ký hoặc cơ chế bảo vệ tương đương đã được review.

### Trace qua 12 checkpoint

| # | Checkpoint | Quyết định | Nếu sai |
| --- | --- | --- | --- |
| 1 | HTTPS ingress | Peer, route, framing hợp lệ | Chặn trước business |
| 2 | Body/header limits | Không vượt kích thước/số lượng | 400/413 theo contract |
| 3 | Strict HMAC envelope | Một key ID, suite, timestamp, nonce, signature | Từ chối ambiguous input |
| 4 | Exact credential lookup | K4 ACTIVE, đúng owner/environment | Authentication failure chung |
| 5 | Suite policy | Suite được server/route/K4 cho phép | Reject; không fallback |
| 6 | Canonical request | Method, raw target, signed fields, body digest đúng | MAC mismatch |
| 7 | HMAC verification | MAC khớp secret đúng key version | 401 chung |
| 8 | Freshness | Signed timestamp còn trong window | 401 chung |
| 9 | Replay authority | Atomic claim (trusted scope, N) FIRST_USE | 401 replay hoặc 503 UNKNOWN |
| 10 | Principal | Lấy identity từ registry đáng tin | Không tạo nếu authn fail |
| 11 | Authorization | Tenant-a + CREATE_ORDER được phép | 403/404 nếu deny |
| 12 | Business | Intent từng xử lý chưa? | Result/idempotency conflict |

R1 đi qua bước 9 bằng FIRST_USE; R2 copy nguyên method, target, signed headers, body, timestamp, nonce và signature **vẫn có MAC hợp lệ** nhưng bước 9 phải trả `ALREADY_USED`. R2 không được đi đến business. Nếu store trả `UNKNOWN`, server không biết nonce đã dùng hay chưa: **fail closed** thay vì gán FALSE/TRUE tùy ý.

### Bản đồ một request sai nhiều điều kiện

Nếu body quá lớn, timestamp expired, MAC sai và requested tenant không được grant cùng lúc, server **không cần kiểm tra mọi lỗi rồi trả chi tiết đầu tiên**. Chặn theo ingress limits, grammar, credential/MAC, freshness/replay rồi authorization. Authn fail phải dừng, không được tới tenant/resource lookup hay nghiệp vụ.

## 21. Bản đồ anti-pattern: liên kết nào bị đứt?

| Anti-pattern | Quan hệ bị thiếu/sai | Hậu quả |
| --- | --- | --- |
| Chỉ ký body | Method/URI không ràng buộc trong HMAC | Thay endpoint/operation |
| Tin canonical bytes client gửi | Server không tự dựng từ raw request | Chữ ký không ràng buộc HTTP thực |
| Parse rồi serialize JSON khi ký raw bytes | Body digest drift | False 401 hoặc parser confusion |
| `Mac.getInstance(userHeader)` | Suite thiếu allowlist | Algorithm confusion |
| Thử tất cả secret tới khi khớp | Key ID không exact | Revoked/old key vẫn pass |
| Key REVOKED nhưng MAC pass | State không được kiểm tra | Leaked key còn hiệu lực |
| Timestamp-only | Thiếu used-once | Replay trong window |
| Nonce không ký | Nonce không nằm trong MAC | Thay nonce để qua replay store |
| Claim nonce trước MAC | Dữ liệu chưa xác thực được ghi | Nonce poisoning |
| `GET nonce` rồi `SET nonce` | Thiếu atomic claim | Double-accept khi concurrency |
| Local cache per pod | Replay authority không chia sẻ | Cross-node replay |
| TTL ngắn hơn signature validity | Nonce state hết quá sớm | Replay trước khi signature hết hạn |
| Redis timeout → success | Không chứng minh first-use | Fail-open |
| Tin `X-Tenant-Id` là grant | Integrity bị nhầm với authorization | Cross-tenant exposure |
| Gateway+backend claim client nonce | Hai chủ sở hữu state | False replay ngay trên R1 |
| Client retry nguyên signature | Attempt dùng lại nonce | 401 liên tục hoặc bypass nếu không guard |
| Shadow verifier cấp principal | Thêm acceptance path | Downgrade |
| Log secret/full signed request | Bằng chứng có thể bị lộ | Compromise/replay |
| Mọi exception → 401 | Outage bị coi bad credential | Che incident |
| Business duplicate ignored vì idempotency | Nhầm intent với auth evidence | Replay vẫn tới controller |

**Cách dùng:** khi phát hiện lỗi, tìm **liên kết đã đứt** thay vì vá triệu chứng bằng cách bỏ ký một header, bật fallback key hay xóa nonce store.

## 22. Bản đồ chẩn đoán theo status và tín hiệu nội bộ

~~~mermaid
flowchart TD
    A["HTTP request failed"] --> B{"Public status?"}
    B -->|400/413/415| P["HTTP envelope, signed-header duplication, media/size"]
    B -->|401| C{"Positive golden request cùng route có pass?"}
    C -->|Không| D["Key ACTIVE? Signing suite? Canonical bytes? Clock?"]
    C -->|Có| E["MAC mismatch / freshness / nonce state"]
    B -->|403/404| F["Principal, tenant grants, resource authorization"]
    B -->|409| G["Business idempotency and payload binding"]
    B -->|429| H["Rate limiter + retry placement"]
    B -->|5xx| I["Redis/vault/HSM, proxy status translation"]
    E --> J{"Internal reason?"}
    J -->|REPLAY_DETECTED| K["Retry reuse, double filter, cross-node replay"]
    J -->|SIGNATURE_MISMATCH| L["SDK/gateway canonical URI/header/body/key"]
~~~

| Triệu chứng | Kiểm tra | Không nên làm |
| --- | --- | --- |
| Luôn 401 ngay sau cấp key | K4 ACTIVE, suite/route, signer golden vector | In secret ra logs |
| 401 chỉ sau proxy rollout | External/internal target, query/body transform | Thử ngẫu nhiên nhiều canonical versions |
| R1 pass, R2 401 | Replay claim ALREADY_USED | Xóa nonce cho “retry dễ” |
| R1 và R2 cùng 401 | Positive control có pass không? | Coi đã chứng minh replay |
| Redis timeout mà HTTP 2xx | Fail-open branch | Bỏ qua vì SLO |
| Key revoked vẫn accepted | Policy/cache revision mọi region | Bật lại key |
| HMAC valid, tenant-b data bị trả | Authorization và resource scoping | Đổi hash algorithm |
| Nhiều payment rows | Idempotency/outbox và anti-replay | Chỉ dùng rate limiter |
| WebFlux heap/direct memory tăng | Bounded DataBuffer capture/release | Buffer vô hạn để debug |
| Lỗi chỉ với HTTP/2/gzip | Raw target/header/body bytes | Bỏ body khỏi MAC |

Audit có thể ghi **route template**, stage, signing suite enum, trusted request correlation ID, credential policy revision với ACL và internal reason. Không đưa raw secret, MAC, signature, body, nonce, query chứa token hoặc key/tenant/client ID vào high-cardinality metric labels.

## 23. Java 17: gắn công thức HMAC với một primitive helper

Đoạn code sau **chỉ** minh họa tính MAC, kiểm tra wire encoding và so MAC bytes; nó **không phải một bộ xác thực HTTP hoàn chỉnh**.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class HmacSha256Primitive {
    private HmacSha256Primitive() {}

    static byte[] sign(byte[] secret, byte[] bytes) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                secret, "HmacSHA256"));
            return mac.doFinal(bytes);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "hmac_runtime_unavailable", ex);
        }
    }

    static boolean matches(
            byte[] secret,
            byte[] serverCanonicalBytes,
            String receivedBase64) {
        byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(receivedBase64);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (supplied.length != 32) return false;

        // Trong profile này: Base64 RFC4648 padded, canonical.
        if (!Base64.getEncoder().encodeToString(supplied)
                .equals(receivedBase64)) {
            return false;
        }

        byte[] expected = sign(secret, serverCanonicalBytes);
        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

Điều kiện dùng helper đúng:

- `serverCanonicalBytes` phải do server dựng từ HTTP request thật theo versioned contract, không tin một chuỗi canonical do client tự gửi.
- `secret` lấy sau exact key ID lookup/credential state/suite policy, không log.
- `Mac` mutable, không chia sẻ bừa instance qua threads.
- Runtime/provider failure phải fail closed, không fallback weak algorithm.
- Helper chưa làm timestamp, nonce, authorization, principal hay body size checks.
- Với HSM non-exportable key, cần provider/key handle API thay vì ép xuất raw `byte[]`.

### Known-answer vector công khai

Với `key=20 bytes 0x0b` và message ASCII `Hi There`, expected HMAC-SHA256 hex:

~~~text
b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
~~~

Đây là test **primitive**, không phải HTTP signed request vector. Contract HTTP phải có expected canonical UTF-8 bytes và MAC tính độc lập từ signer implementation khác.

## 24. JUnit 5: kiểm tra từng mối liên kết một cách có chứng cứ

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;

class HmacConceptMapTest {
    @Test
    void knownAnswerMatchesHmacSha256() {
        byte[] key = new byte[20];
        java.util.Arrays.fill(key, (byte) 0x0b);
        byte[] data = "Hi There"
            .getBytes(StandardCharsets.US_ASCII);

        byte[] mac = HmacSha256Primitive.sign(key, data);
        assertEquals(
            "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7",
            HexFormat.of().formatHex(mac));
    }

    @Test
    void tamperCanonicalBytesBreaksSignature() {
        byte[] key = "test-key-only"
            .getBytes(StandardCharsets.UTF_8);
        byte[] source = "POST\n/api/orders\n{}"
            .getBytes(StandardCharsets.UTF_8);
        byte[] tampered = "POST\n/api/payments\n{}"
            .getBytes(StandardCharsets.UTF_8);
        String signature =
            java.util.Base64.getEncoder().encodeToString(
                HmacSha256Primitive.sign(key, source));

        assertTrue(HmacSha256Primitive.matches(
            key, source, signature));
        assertFalse(HmacSha256Primitive.matches(
            key, tampered, signature));
    }

    @Test
    void malformedSignatureEncodingIsRejected() {
        byte[] key = "test-key-only".getBytes(
            StandardCharsets.UTF_8);
        assertFalse(HmacSha256Primitive.matches(
            key, new byte[0], "!not-base64!"));
    }
}
~~~

Các tests trên chứng minh **primitive và bytes integrity**, chưa chứng minh replay hoặc quyền tenant. Để kiểm tra hai mối liên kết đó, dùng fake Clock + nonce store trong unit test, Redis thật trong integration test và Spring Security filter chain trong end-to-end test.

### Bộ 3 kiểm thử không thể thiếu

~~~text
POS-1:
  K4 ACTIVE, MAC đúng, timestamp hợp lệ, nonce N1 mới.
  -> FIRST_USE, authenticated principal từ registry.

REPLAY-2:
  Gửi lại nguyên POS-1 trong timestamp window.
  -> ALREADY_USED, không business side effect lần hai.

POISON-3:
  Gửi MAC sai với nonce N3 mới.
  -> Authentication reject, nonce claim count = 0.
  Sau đó gửi MAC đúng với N3.
  -> FIRST_USE, không bị nonce poisoning.
~~~

Muốn chứng minh distributed protection, phải chạy 100 concurrent copies trên nhiều pods/gateways và fault injection Redis timeout/lost ACK/failover. Một fake `ConcurrentHashMap` trong cùng JVM không chứng minh multi-region consistency.

## 25. Ma trận 50 liên kết để ôn tập và kiểm thử

| ID | Liên kết | Assertion |
| --- | --- | --- |
| MAP-01 | CSPRNG → secret | Key entropy/length policy đạt |
| MAP-02 | Key ID → registry | Lookup exact credential |
| MAP-03 | Registry → principal | Identity không từ header tự khai |
| MAP-04 | Key state → authentication | REVOKED không pass dù MAC đúng |
| MAP-05 | Credential → signing suite | Suite chưa grant bị reject |
| MAP-06 | Runtime → capability | Provider có ≠ được policy allow |
| MAP-07 | Method → MAC | Sửa method làm mismatch |
| MAP-08 | URI/query → MAC | Sửa raw target làm mismatch |
| MAP-09 | Signed headers → MAC | Tampering bị phát hiện |
| MAP-10 | Raw body → digest | Byte change làm digest đổi |
| MAP-11 | Digest → canonical | Body hash thực nằm trong signed bytes |
| MAP-12 | Suite selector → MAC | Header tamper không downgrade |
| MAP-13 | Key ID → MAC | Sửa K4→K3 không fallback |
| MAP-14 | Timestamp → MAC | Sửa timestamp giữ MAC reject |
| MAP-15 | Nonce → MAC | Sửa nonce giữ MAC reject |
| MAP-16 | UTF-8/LF → canonical | Client/server golden bytes parity |
| MAP-17 | JSON bytes → body digest | Whitespace đổi digest theo contract |
| MAP-18 | Header duplicates → parser | Reject ambiguity |
| MAP-19 | Body limit → parser | 413; không hash truncated |
| MAP-20 | Signature Base64 → MAC bytes | Reject malformed/wrong length |
| MAP-21 | MAC compare → authn | Signature mismatch không principal |
| MAP-22 | Clock → freshness | ±window boundaries đúng contract |
| MAP-23 | Client nonce → attempt | Fresh nonce mỗi attempt |
| MAP-24 | Bad MAC → nonce store | Claim calls = 0 |
| MAP-25 | First-use → authn | R1 claim đúng một lần |
| MAP-26 | Same proof → replay | R2 reject trong window |
| MAP-27 | Concurrent claims → atomicity | 100 copies chỉ 1 FIRST_USE |
| MAP-28 | TTL → signature lifetime | Nonce record không expire sớm |
| MAP-29 | Store outage → fail closed | UNKNOWN không thành success |
| MAP-30 | Multiple pods → nonce authority | R2 qua node B vẫn reject |
| MAP-31 | Regions → consistency | Đúng security guarantee đã công bố |
| MAP-32 | Gateway → canonical target | External/internal contract đúng |
| MAP-33 | Gateway → internal identity | Spoofed forwarded header không được tin |
| MAP-34 | Backend ingress → trust | Không bypass gateway HMAC |
| MAP-35 | WebFlux chunks → digest | Chunk segmentation không đổi hash |
| MAP-36 | WebFlux cancel → resource | DataBuffer release, no early claim |
| MAP-37 | Servlet filter → controller | Raw body được replay đúng |
| MAP-38 | Filter dispatch → nonce | Không double-claim request |
| MAP-39 | Principal → tenant grant | Cross-tenant deny 403/404 |
| MAP-40 | Signed tenant → integrity | Tampered tenant fails MAC |
| MAP-41 | New nonce → same intent | Idempotency ngăn double business |
| MAP-42 | Old nonce → replay | Không tới domain handler |
| MAP-43 | Key rotation → exact version | K4 không thử K3 |
| MAP-44 | Revoke → propagation | Mọi node reject revoked key |
| MAP-45 | Suite migration → policy | Không OR verifiers hoặc downgrade |
| MAP-46 | Public error → privacy | Không expected MAC/key existence |
| MAP-47 | Redis UNKNOWN → response | 503, không che thành 401/2xx |
| MAP-48 | Authorization deny → response | 403/404, không authn 401 |
| MAP-49 | Monitoring → safe metadata | Không secret/high-cardinality labels |
| MAP-50 | Incident → recovery | Revoke/rotate, probes, no stale accept |

**Positive control quan trọng hơn số lượng test:** trước khi gửi negative request, cùng một key/route/clock phải có R1 thật sự pass. Nếu cả R1 và R2 đều 401 vì gateway rewrite path, không thể kết luận replay guard đúng.

## 26. Bài tập tình huống: tìm nút hỏng trên bản đồ

Một hệ thống Spring Boot 3 có các đặc điểm:

~~~text
Key K4 ACTIVE cho partner-a, tenant-a
Gateway: /public/payments -> /internal/payments
Gateway tin X-Authenticated-Client từ client request
Backend verifier ký internal path thay vì external
Verifier có timestamp ±5 phút, nhưng chỉ check nonce format
Business tin X-Tenant-Id là effective tenant
Retry SDK gửi lại nguyên nonce/signature
Redis outage -> local in-memory fallback
Rotation ghi secret mới đè lên cùng key ID K4
~~~

Hãy đánh dấu nút bị sai và giải thích:

1. Vì sao external/internal target phải được chốt trong canonical contract?
2. Gateway header identity cần trusted assertion/mTLS thế nào?
3. HMAC valid có chứng minh request chưa được dùng không?
4. Nonce format valid khác atomic first-use ở đâu?
5. Vì sao signed tenant header không tự cấp grant tenant?
6. Client retry cùng nonce có nguy cơ gì?
7. Local fallback có giữ global replay guarantee không?
8. Rotation cùng key ID làm verifier/key lifecycle mập mờ ra sao?
9. Nếu Redis UNKNOWN, nên fail closed và phân loại response thế nào?
10. Bộ test nào chứng minh request replay không gây business side effect thứ hai?
11. Nếu secret bị lộ, anti-replay có đủ thay revocation không?
12. Vì sao MAC helper unit test không chứng minh end-to-end Spring Security an toàn?

**Hướng giải:** version canonical raw-target contract, exact key lookup, shared atomic replay authority, MAC-first claim, tenant authorization độc lập, nonce mới + same idempotency key khi retry, revoke/rotate với key ID mới, fail closed, golden vectors và E2E tests qua gateway. Đừng sửa bằng cách “thử nhiều paths/secret cho tới khi signature khớp”.

## 27. Câu hỏi tự kiểm tra theo mối quan hệ

### Nhóm nền tảng

1. HMAC khác SHA-256 digest và TLS ở bảo đảm nào?
2. Vì sao HMAC shared secret không cho non-repudiation?
3. Base64 signature khác raw secret ra sao?
4. Tại sao cùng K/HmacSHA256 mà client và server vẫn tính tag khác?
5. Key ID do client gửi khác authenticated principal ở điểm nào?
6. Runtime hỗ trợ suite V2 có đồng nghĩa mọi credential được dùng V2 không?

### Nhóm hệ thống

7. Canonical request cho API payment nên ký các trường nào và vì sao?
8. Timestamp, nonce, TTL, atomic claim bổ sung cho nhau ra sao?
9. Claim nonce trước MAC gây kiểu tấn công gì?
10. Khi Gateway A verify HMAC, backend tin identity qua cơ chế nào?
11. Khi V1 và V2 cùng tồn tại, vì sao không thử `v1.verify || v2.verify`?
12. Khi Redis failover mất write, `SET NX` có tự bảo đảm global at-most-once không?

### Nhóm vận hành

13. R1 và R2 cùng 401 có chứng minh replay protection không?
14. Redis UNKNOWN khác nonce ALREADY_USED về semantics?
15. HMAC pass mà tenant deny thì tầng nào chịu trách nhiệm?
16. Retry business intent cần giữ gì và thay gì?
17. Key revoked vẫn được accept ở một node phải xử lý thế nào?
18. Khi 401 chỉ trên gateway mới, thu thập dữ liệu nào?
19. 503 auth dependency có được trả giả 401 để “bảo mật hơn” không?
20. Log cần đủ gì để debug mà không thành nguồn replay?

**Cách tự chấm:** câu trả lời tốt phải chỉ được **decision owner**, **trust boundary**, **failure mode** và **test kiểm chứng**, không chỉ nói “bật Redis” hay “thêm Spring Security”.

## 28. Checklist tổng kết và bản đồ mang theo

### Giao thức và mật mã

- [ ] Suite/version cố định, có canonical contract rõ; không chọn algorithm tùy ý từ HTTP.
- [ ] Method, raw URI/query, signed headers/body digest và metadata quan trọng được HMAC ràng buộc.
- [ ] Client/server có golden canonical bytes, encoding, MAC vectors.
- [ ] Proxy rewrite/content encoding không làm verifier dùng sai signed bytes.
- [ ] HMAC không bị nhầm với encryption, anti-replay hoặc authorization.
- [ ] Key ID gắn một exact credential/version; không fallback keys/suites.

### Key và chống replay

- [ ] Secret được sinh bằng CSPRNG và giữ ở vault/KMS/HSM với quyền tối thiểu.
- [ ] Credential ACTIVE/REVOKED/expired/owner/tenant/suite policy được kiểm tra.
- [ ] Timestamp/nonce **được ký** và dùng đúng window/grammar.
- [ ] Claim nonce atomic sau MAC đúng, tránh nonce poisoning.
- [ ] Scope replay đến từ identity đáng tin; TTL đủ bao phủ signature lifetime.
- [ ] Store outage/UNKNOWN → fail closed; multi-node/region/failover được test.
- [ ] Principal chỉ tạo sau authenticated first-use; authorization tenant/action/resource độc lập.

### Spring, gateway, vận hành

- [ ] MVC/WebFlux filter chain đúng route, không double filter hoặc unprotected fallback.
- [ ] Body capture bounded; Servlet body replay và WebFlux DataBuffer lifecycle đúng.
- [ ] Gateway/backend có trust boundary và internal identity assertion rõ.
- [ ] Chỉ một nơi authoritative claim client nonce.
- [ ] HTTP errors phân biệt authn 401, authz 403/404, business 409 và dependency 503.
- [ ] SDK retry dùng nonce/signature mới, business idempotency key cũ cho same intent.
- [ ] Key rotation/revoke, suite migration và policy cache không mở downgrade.
- [ ] Audit/metrics không lộ secret, raw signature, nonce/body hay nhãn động.
- [ ] Có on-call/runbook cho replay breach, revoked-key acceptance và dependency failures.

### Bằng chứng kiểm thử

- [ ] Known-answer HMAC test và golden canonical vectors PASS.
- [ ] R1 hợp lệ pass qua đường production-like; R2 exact replay bị reject trong window.
- [ ] Wrong MAC không claim nonce; right MAC cùng nonce vẫn first-use.
- [ ] Multi-node concurrency chỉ một FIRST_USE trong phạm vi bảo vệ.
- [ ] Auth dependency UNKNOWN không tạo principal/business side effect.
- [ ] HMAC valid nhưng unauthorized tenant bị deny theo policy.
- [ ] Key revoked, suite disallowed, identity-header spoofing bị chặn.
- [ ] Test xác minh stage/internal reason/nonce state/context/side effects, không chỉ HTTP status.

### Bản đồ 10 nút cốt lõi

~~~mermaid
flowchart TD
    A["1. Workload + shared secret"]
    B["2. Canonical HTTP request contract"]
    C["3. HMAC on exact bytes"]
    D["4. Credential state + suite policy"]
    E["5. Signed timestamp freshness"]
    F["6. Signed nonce + atomic replay claim"]
    G["7. Authenticated principal"]
    H["8. Tenant/action/resource authorization"]
    I["9. Business idempotency"]
    J["10. Gateway, tests, monitoring, rotation"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
    J -. "Vận hành và bảo vệ" .-> D
    J -. "Kiểm thử" .-> F
    J -. "Quan sát" .-> H
~~~

**Kết luận:** HMAC bảo vệ **những bytes được ký**; credential registry quyết định **key thuộc về ai và còn được phép không**; timestamp + nonce trả lời **request còn mới và chưa dùng chưa**; Spring Security thiết lập **principal đã xác thực**; authorization trả lời **principal được làm gì**; idempotency trả lời **business intent đã hoàn thành chưa**. Gateway, kiểm thử và vận hành phải duy trì từng liên kết qua nhiều instance, region và phiên bản.

Khi gặp một lỗi thực tế, hãy xác định nút tương ứng, tìm đầu vào nào đã được tin trước khi xác minh, quyết định nào fail-open và test nào chứng minh được trạng thái. Đó là cách sử dụng **bản đồ khái niệm HMAC authentication** như một công cụ review kiến trúc, không chỉ như một tờ ghi nhớ thuật ngữ.
