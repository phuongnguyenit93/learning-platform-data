# Dual verification: xác minh đồng thời khóa cũ và khóa mới khi xoay vòng HMAC

**Dual verification** trong **key rotation** là giai đoạn dịch vụ **cho phép xác minh request bằng hai phiên bản credential hợp lệ**, thường là **old key** và **new key**, trong một khoảng chuyển tiếp có kiểm soát. Mục tiêu là để client chuyển dần sang secret mới mà các request hợp lệ vẫn được nhận, không gián đoạn dịch vụ và không phải tắt xác thực HMAC.

Đây là bài thuộc chương **Key rotation** của module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Phạm vi module là thiết kế xác thực HTTP request bằng **HMAC và shared secret**, ký **canonical request** chứa method, URI, signed headers/body; xác minh signature, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**. Chủ đề trực tiếp của bài là **dual verification ở verifier**: cho phép **hai key ID đang có hiệu lực**, nhưng với **mỗi request chỉ chọn đúng key mà nó khai báo và đã ký**.

> **Bất biến quan trọng:** “Nhận được request ký bằng old key **hoặc** new key” **không** có nghĩa “thử tất cả secret cho đến khi một secret khớp”. Trong hợp đồng có `keyId`, verifier chỉ tra cứu **một bản ghi chính xác** theo `(audience, authenticated-scope-client, keyId)`, áp dụng trạng thái/thời gian/scope của bản ghi đó rồi tính HMAC. Unknown, revoked, expired hoặc bad signature **không được fallback sang key khác**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích dual verification, **overlap window** và sự khác biệt giữa **dual-key acceptance** với “verify cả hai key cho một request”.
2. Thiết kế **old/new credential records** có `keyId`, secret riêng, `ACTIVE/RETIRING/REVOKED`, thời gian hiệu lực và scope theo audience/client/route.
3. Chọn secret bằng **signed key ID** thay vì brute-force qua mọi secret hoặc dùng default secret.
4. Lập kế hoạch rollout **provision → activate new key → dual verification → client cutover → retire/revoke old key**, có readiness và rollback an toàn.
5. Duy trì **một nonce replay namespace cho cùng client/audience** trong khi key ID thay đổi; kiểm tra TTL theo signed timestamp.
6. Phân tích request đang bay trên mạng, lệch đồng hồ, stale key cache, revoke propagation, multi-region và lỗi KMS.
7. Viết ví dụ Java 17 dùng `Mac`/`MessageDigest.isEqual`, keyring có hai phiên bản, timestamp/nonce và kiểm thử replay qua rotation.
8. Phân biệt xác thực khóa đúng với **business authorization** và **idempotency** khi client retry bằng secret mới.

## 2. Dual verification thực sự xác minh điều gì?

Giả sử `partner-42` có hai credential:

| Thuộc tính | Old credential | New credential |
| --- | --- | --- |
| Client ID | `partner-42` | `partner-42` |
| Key ID | `key-2026-11` | `key-2026-12` |
| Secret | Secret A, giữ bí mật | Secret B **khác** A, giữ bí mật |
| Audience | `payments-api` | `payments-api` |
| Algorithm | `HmacSHA256` | `HmacSHA256` |
| State trong overlap | `RETIRING` hoặc `ACTIVE` | `ACTIVE` |
| Verify | Được phép trong grace period | Được phép |
| Ký request mới ở client | Nên dừng sau cutover | Được ưu tiên |

Client A chưa cập nhật có thể gửi:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: 1795831200
X-Nonce: 00112233445566778899aabbccddeeff
X-Content-SHA256: <lowercase-hex-sha256-body>
X-Signature: <base64-hmac-sha256-tag-using-secret-A>

{"orderId":"ord-123","amount":50000}
~~~

Client B đã cập nhật gửi:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-12
X-Timestamp: 1795831201
X-Nonce: ffeeddccbbaa99887766554433221100
X-Content-SHA256: <lowercase-hex-sha256-body>
X-Signature: <base64-hmac-sha256-tag-using-secret-B>

{"orderId":"ord-123","amount":50000}
~~~

Các phần `<...>` chỉ là placeholder, không phải giá trị gửi thật. Mỗi request dùng **key ID/secret đồng nhất** và có timestamp/nonce khác. Verifier có thể xác nhận cả hai request **nếu cùng thỏa mọi policy**, nhưng hai request cùng nghiệp vụ chưa chắc được phép tạo **hai thanh toán**: authorization và idempotency phải xử lý riêng.

### 2.1. “Dual verification” có ba nghĩa dễ nhầm

| Cách hiểu | Đúng với bài này? | Giải thích |
| --- | --- | --- |
| **Cùng một API chấp nhận chữ ký từ hai key version đang active.** | **Đúng** | Hai key ID nằm trong tập được phép của client/audience trong overlap. |
| **Mỗi request phải có hai chữ ký và cả hai đều hợp lệ.** | Không | Đó là **dual-signature / multi-signature protocol** khác, không phải mục đích chuyển khóa thông thường. |
| **Một request khai key A nhưng server thử A, B, C cho đến khi có tag khớp.** | **Không** | Không tuân thủ signed key ID, tạo đường fallback/downgrade và tăng blast radius. |

Ở một số giao thức **legacy không có key ID**, hệ thống có thể dùng **tối đa hai key ứng viên đã cố định trong migration** để kiểm tra, với policy nghiêm ngặt và cùng client/scope. Đây là **ngoại lệ tương thích** cần phiên bản giao thức riêng, giới hạn cửa sổ, kiểm thử timing/CPU và loại bỏ sớm; không được âm thầm bật `try-all-secrets` trên hợp đồng đã có `X-Key-Id`.

### 2.2. Tại sao cần hai secret độc lập?

Rotation có ý nghĩa khi **new key material thực sự khác old key material**. Nếu hai key ID khác nhau cùng trỏ một secret, đổi `keyId` không giảm rủi ro lộ key cũ. Trong migration có alias tạm thời dùng cùng secret, vẫn phải hiểu đó **chưa phải rotation mật mã hoàn chỉnh** và key ID phải nằm trong canonical để tránh thay alias sang policy khác.

## 3. Threat model trong thời gian overlap

Trong dual verification, hệ thống **tạm chấp nhận hai credential**, vì vậy surface có thể lớn hơn:

~~~mermaid
flowchart TD
    A["Client đã được cấp secret A hoặc B"] --> R["HTTP signed canonical request"]
    R --> V["Verifier chọn exact (clientId, keyId)"]
    V --> O["Old ACTIVE / RETIRING"]
    V --> N["New ACTIVE"]
    O --> M["HMAC của old secret + key policy"]
    N --> P["HMAC của new secret + key policy"]
    M --> T["Timestamp + atomic nonce + authz"]
    P --> T
    X["Attacker chiếm old secret"] --> Y["Ký request mới bằng old key khi overlap"]
    Y --> O
~~~

Nếu attacker đã có **old secret**, nó có thể tạo request mới có timestamp/nonce hợp lệ **chừng nào old key còn được chấp nhận**. Vì vậy dual verification là biện pháp **availability trong planned rotation**, **không** phải phương án xử lý an toàn để kéo dài quyền của một key **đã bị compromise**.

| Tình huống | Rủi ro | Biện pháp |
| --- | --- | --- |
| Planned rotation, old secret chưa lộ | Request cũ vẫn tới trong quá trình client cập nhật. | Overlap ngắn, kiểm soát trạng thái và deadline. |
| Old secret đã lộ | Attacker vẫn ký HMAC mới bằng old secret. | **Revoke ngay**, không tiếp tục overlap như planned rotation. |
| Old key đã revoke nhưng cache stale | Một verifier vẫn coi key ACTIVE. | Invalidation/revoke barrier, monitoring SLA, fail closed khi không chắc policy. |
| Signed key ID có thể bị sửa | Chuyển sang key với policy khác. | Ký client ID/key ID/audience vào canonical và verify đúng key. |
| Gateway/region chưa có new key | Request new key bị 401 không đồng đều. | Provision-before-use; readiness/version barrier, traffic gating. |
| Nonce cache tách theo key ID | Cùng nonce có thể được chấp nhận lại dưới key mới. | Namespace nonce theo **(audience, authenticated client ID, nonce)**. |
| Rotation lặp nhưng key IDs tái sử dụng | Mơ hồ policy, cache, audit; nguy cơ dùng nhầm secret. | ID/version bất biến, không tái sử dụng ID của key bị revoke. |

## 4. Hợp đồng ký: key ID phải ở trong canonical request

Để học và kiểm thử, bài định nghĩa **HMAC-DUAL-VERIFY-V1**. Đây là **profile minh họa** cho một API, không phải một RFC HTTP HMAC dùng chung.

| Thành phần | Quy định |
| --- | --- |
| Method | `POST`, có phân biệt chữ hoa/thường trong canonical. |
| Raw target | `/v1/payments?currency=VND`; giữ đúng path/query mà backend thực thi. |
| Audience | `payments-api`, chọn từ server policy, không tin `X-Audience` client tự khai. |
| Client ID | `partner-42`, header `X-Client-Id` chính xác một lần. |
| Key ID | `key-2026-11` hoặc `key-2026-12`, header `X-Key-Id` chính xác một lần. |
| Signing algorithm | `HmacSHA256` theo server policy; không nhận algorithm header tùy ý. |
| Timestamp | Unix epoch seconds ASCII chính tắc, `[1-9][0-9]{0,18}`. |
| Freshness | `now-300 <= ts <= now+60`, tính bằng **server clock**, inclusive. |
| Nonce | 16 byte ngẫu nhiên từ CSPRNG, lowercase hex 32 ký tự. |
| Body digest | SHA-256 trên body bytes thực nhận, 64 lowercase hex. |
| Signature | HMAC-SHA256 **32-byte full tag**, Base64 basic padded, **44 ASCII ký tự**, một `=` ở cuối. |
| Key lookup | Exact `(environment, audience, claimedClientId, signedKeyId)`. |
| Nonce claim | Sau HMAC hợp lệ, atomically theo `(audience, authenticatedClientId, nonce)`, **không theo key ID**. |

Canonical request khi ký bằng old key:

~~~text
HMAC-DUAL-VERIFY-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:1795831200
x-nonce:00112233445566778899aabbccddeeff
content-type:application/json
x-content-sha256:<sha256-of-original-body-bytes>
~~~

Khi ký bằng new key, đổi **dòng `x-key-id` thành key ID mới**, dùng **secret mới**, timestamp/nonce mới và tính lại HMAC. Chuỗi canonical nối các dòng bằng **LF (0x0A)**, mã hóa **UTF-8**, **không có LF cuối**.

### 4.1. Vì sao không ký raw chữ ký?

`X-Signature` chứa kết quả HMAC nên **không** đặt signature vào chính canonical: nó sẽ tạo vòng tự tham chiếu. Client ký các **trường metadata bảo mật** (đặc biệt client ID, key ID, timestamp và nonce) cùng request method/URI/body, rồi chuyển tag đã encode qua header.

### 4.2. Key ID không phải identity đã xác thực

Trước HMAC, `X-Client-Id` và `X-Key-Id` chỉ là **lookup hints**. Verifier lấy secret bằng đúng locator sau khi validate format nhưng **chưa khẳng định** ai gửi request. Chỉ khi active key policy và HMAC tag đúng, client ID mới được tin để claim nonce, gọi authorization và quản lý idempotency.

### 4.3. Vì sao không thử old key khi new-key tag sai?

Giả sử request khai `key-2026-12` nhưng tag được tạo bằng secret A của `key-2026-11`. Nếu verifier cố “cứu” request bằng cách thử secret A thì:

- Không còn thực thi được policy “key ID mới bắt buộc dùng secret mới”.
- Có thể tiếp tục nhận old secret sau deadline hoặc revoke do code fallback.
- Mất khả năng thống kê chính xác client đã cutover hay chưa.
- Có thể dùng một secret sai audience/client nếu vòng lặp lấy toàn registry.
- Tăng CPU theo số key, tạo tín hiệu timing/enumeration và rủi ro DoS.

**Cách đúng:** tra đúng `key-2026-12`; nếu tag không khớp, **reject**. Không thử A.

## 5. Lập kế hoạch overlap giữa key cũ và key mới

Một planned rotation an toàn thường gồm các mốc:

~~~mermaid
sequenceDiagram
    participant O as Rotation controller
    participant K as Key registry/KMS
    participant V as Verifier fleet
    participant C as Client signer
    O->>K: Provision B, keyId=key-2026-12, STAGED
    K-->>V: Phân phối B + policy, vẫn STAGED
    V-->>O: Readiness attest theo config/version
    O->>K: Activate B với conditional state transition
    O-->>C: Cho phép ký mới bằng B (cutover)
    par Overlap
        C->>V: Request key-2026-11 (old, còn hạn)
        C->>V: Request key-2026-12 (new, còn hạn)
    end
    O->>C: Dừng ký mới bằng A; chờ in-flight/grace
    O->>K: Retire/revoke A sau deadline
    V-->>O: Monitor zero/low old-key usage, revoke propagation
~~~

### 5.1. Các pha và trạng thái đề xuất

| Pha | Old key | New key | Client signer | Verifier |
| --- | --- | --- | --- | --- |
| 0. Trước rotation | `ACTIVE` | Chưa có | Ký A | Verify A |
| 1. Provision/stage | `ACTIVE` | `STAGED` | Ký A | Verify A; **không nhận B** |
| 2. Activate new | `ACTIVE` | `ACTIVE` | Bắt đầu có thể ký B | Nhận A hoặc B theo **signed key ID** |
| 3. Client cutover | `RETIRING` | `ACTIVE` | Ký request **mới** bằng B; hạn chế A | Nhận A cho in-flight, nhận B |
| 4. Old verify cutoff | `REVOKED` hoặc expired | `ACTIVE` | Chỉ ký B | **Reject A**, verify B |
| 5. Sau rotation | Không còn hiệu lực | `ACTIVE` | Chỉ dùng B | Không fallback về A |

Tên trạng thái `RETIRING` là lựa chọn của bài; một số hệ thống chỉ có `ACTIVE`/`REVOKED` và deadline. Dù chọn model nào, cần tách **quyền client ký mới** với **quyền server tiếp tục verify old key cho request đang bay**.

### 5.2. Timeline ví dụ và grace period

Giả sử:

~~~text
P (pastWindow)          = 300 seconds
F (futureTolerance)     = 60 seconds
M (safety margin)       = 10 seconds
Client final old signing = 2026-11-28 03:00:00 UTC
Old verification cutoff  = 2026-11-28 03:07:00 UTC  (ví dụ)
~~~

Grace **7 phút** ở đây là ví dụ dành cho một hệ thống có SLA đã xác nhận; **không** tự suy rằng mọi hệ thống chỉ cần 7 phút. Phải cân nhắc client clock skew, queue/network delay, gateway retries, tải hệ thống, batch workers, max age request, rate limit, customer communication và khả năng retry thành công.

Khi client ký `ts=03:00:00`, theo freshness contract nó chỉ có thể được nhận đến `03:05:00` (chưa kể chính sách verifier). Tuy nhiên client có thể có clock lệch một chút hoặc last-send khác thời điểm last-sign, nên **verify cutoff** cần dựa trên contract vận hành thực, không chỉ một công thức tùy tiện.

**Không** kéo dài overlap nếu nghi ngờ old key bị lộ: trong incident, revoke nhanh và yêu cầu ký bằng key an toàn sau khi đã phân phối, chấp nhận có thể phải retry/thỏa thuận xử lý nghiệp vụ.

### 5.3. Không đổi HMAC algorithm cùng lúc nếu không cần

Đổi secret/key ID là rotation. Đổi đồng thời `HmacSHA256`, URI normalization, Base64 encoding hay signed-header set là **protocol migration** khác, khó debug. Nên giữ canonical version/algorithm ổn định trong dual verification, có test vector chung cho A/B và chỉ thay key ID/secret; nếu bắt buộc đổi protocol, dùng **versioned contract** và rollout độc lập, không “thử mọi algorithm cho tới khi khớp”.

## 6. Verifier keyring: hai phiên bản hợp lệ, một key cho mỗi request

Hình dung key registry:

~~~text
KeyLocator = (prod, payments-api, partner-42, key-2026-11)
    state = RETIRING
    verifyAllowedUntil = cutoff
    secretRef = internal-key-A

KeyLocator = (prod, payments-api, partner-42, key-2026-12)
    state = ACTIVE
    activeFrom = activated-at
    secretRef = internal-key-B
~~~

**Không** nhận secretRef từ HTTP client như file path/KMS ARN tự khai. `kid` chỉ được validate và map qua registry do server kiểm soát.

~~~mermaid
flowchart TD
    R["HTTP request + signed clientId, kid, ts, nonce"] --> P["Strict parse, reject duplicate security headers"]
    P --> I["Chọn audience/route từ server policy"]
    I --> L["Exact lookup (env,audience,clientId,kid)"]
    L --> K{"Key record?"}
    K -->|Unknown / registry unavailable| X["Reject / fail closed"]
    K -->|Found| S{"ACTIVE/RETIRING + time + scope?"}
    S -->|Không| X
    S -->|Có| C["Canonical request gồm chính signed kid"]
    C --> M["HMAC bằng secret của đúng key record"]
    M --> V{"Full tag khớp?"}
    V -->|Không| X
    V -->|Có| T{"Signed ts fresh + nonce atomic claim?"}
    T -->|Không| X
    T -->|Có| A["Authenticated identity -> authorization + idempotency"]
~~~

### 6.1. Chọn key đúng ngay từ đầu

Trong code:

~~~java
KeyLocator locator = new KeyLocator(
    serverEnvironment,
    serverAudience,
    requestClaimedClientId,
    requestSignedKeyId
);
KeyRecord selected = trustedRegistry.lookup(locator);

if (selected == null || !selected.canVerifyAt(serverNow)) {
    return REJECT;
}

byte[] expected = hmacSha256(
    selected.secret(), canonicalRequestBytes
);
return fullTagMatches(expected, suppliedTag) ? NEXT_CHECK : REJECT;
~~~

**Không** thay `selected` bằng secret A sau khi HMAC với B sai. Cũng không để cùng `kid` mapping sang hai secret khác nhau trên các replica mà không có versioning.

### 6.2. Khi có legacy request không có key ID

Nếu bắt buộc phục vụ giao thức cũ:

1. Đặt **scheme/version riêng** cho legacy, không trộn với V1 có `kid`.
2. Chỉ cho phép **tối đa tập khóa nhỏ, cố định của cùng một client/audience** trong grace.
3. Cân nhắc tính tất cả MAC ứng viên trước khi quyết định, không dừng khi match đầu, để giảm rò rỉ do vị trí match — nhưng vẫn phải đánh giá I/O, message length và toàn pipeline; không hứa constant-time tuyệt đối.
4. Giới hạn CPU, rate limiting và thời gian chấp nhận legacy; có deadline loại bỏ.
5. Không mở rộng thử đến secret của mọi client, không fallback sang unscoped/default key.

Khi đã triển khai signed `X-Key-Id` đầy đủ, **không** cho phép legacy branch tự hoạt động khi client bỏ `X-Key-Id` để downgrade.

## 7. Nonce replay guard phải dùng chung qua hai key ID

Một lỗi dễ mắc trong dual verification là tạo nonce key như sau:

~~~text
WRONG:
    nonceKey = audience + clientId + keyId + nonce

CORRECT for this contract:
    nonceKey = encodeTuple(audience, authenticatedClientId, nonce)
~~~

Giả sử một request dùng old key với nonce `N` đã được chấp nhận. Sau đó người gửi (có khả năng ký bằng new key) tạo **một HMAC tag khác** nhưng **tái sử dụng `N`**. Nếu nonce store thêm `keyId` vào namespace, key mới tạo một ô trống và có thể được claim lại. Với scope `(audience,clientId,nonce)`, lần thứ hai **phải bị từ chối** trong retention window.

**Lưu ý:** một attacker không biết new secret **không thể tự ký lại** request để đổi kid; nhưng client bị lỗi, client multi-instance hoặc attacker có quyền ký cả hai key có thể tạo request mới với same nonce. Thiết kế nonce không nên dựa vào giả định ai sẽ có secret nào.

### 7.1. Timestamp, nonce và signed freshness

Contract ví dụ dùng:

~~~text
P = pastWindowSeconds    = 300
F = futureTolerance      = 60
M = safetyMargin         = 10

fresh(ts, now) := now - P <= ts <= now + F
~~~

Timestamp `ts` là **signed epoch seconds**, `now` đến từ **verifier server clock**. Một request có `ts` có thể fresh từ `now=ts-F` tới `now=ts+P`, tổng **P+F=360 giây**.

Nonce record cần giữ ít nhất đến sau:

~~~text
expiresAt >= signedTimestamp + P + M
~~~

hoặc dùng **relative TTL** bảo thủ khi claim:

~~~text
TTL = P + F + M = 370 seconds
~~~

Không dùng TTL `P=300` tính từ claim sớm nhất: nonce có thể biến mất khi request vẫn fresh. Nonce store có **conditional atomic insert** (ví dụ Redis `SET key 1 NX PX 370000` hoặc SQL unique insert) và phải không evict/delete sớm, không mất record sau failover vượt durability SLA.

### 7.2. Chọn namespace khi service có nhiều tenant

Với credential scope theo client và audience, nonce key của bài là `(audience, authenticatedClientId, nonce)`. Nếu hệ thống có identity tenant-specific hoặc nhiều trust domain, xác định thêm partition **dựa trên identity đã xác thực**, không thêm `kid` tùy tiện để reset lịch sử replay khi rotation.

### 7.3. Authentication khác business idempotency

Client retry một ý định thanh toán sau timeout nên:

~~~text
Same Idempotency-Key: giữ nguyên (và được ký trong canonical).
New timestamp: tạo mới đúng server time window.
New nonce: tạo bằng CSPRNG cho request retry.
New HMAC: ký lại bằng credential đang active.
~~~

Replay guard chỉ chống dùng lại **nonce**, còn **idempotency** mới bảo vệ chống **hai side effect** khi client đổi nonce/key ID trong retry. Một dual-verification implementation không tự cung cấp exactly-once payment.

## 8. Key state, validity và revocation trong overlap

Một policy tại verifier:

~~~text
acceptCredential(key, serverVerificationInstant) =
    state IN {ACTIVE, RETIRING}
    AND environment/audience/clientId/kid match selected locator
    AND allowedAlgorithm == HmacSHA256
    AND allowedMethod/route match this request
    AND activeFrom <= serverVerificationInstant
    AND serverVerificationInstant < expiresAt
    AND NOT revoked
~~~

**Thời gian hiệu lực key dựa trên server verify time**, không dựa vào signed timestamp của client để tránh hồi sinh key đã revoke/expired bằng request backdated.

### 8.1. Tại sao RETIRING vẫn có thể verify?

Trong overlap, client đã được chỉ đạo **ngừng ký request mới** bằng A, nhưng request A ký trước cutover có thể đang nằm trong queue, bị network delay hoặc retry ở proxy. Cho phép `RETIRING` tiếp tục verify một khoảng **bounded** giúp chuyển đổi ít lỗi. Đây là chính sách có điều kiện, không phải đặc tính bắt buộc của mọi hệ thống.

### 8.2. Khi nào phải REVOKE ngay?

Nếu old key có dấu hiệu **compromised**, continued verification bằng old key làm attacker có thể ký request mới. Do đó planned grace nên được **cắt ngắn hoặc chấm dứt** theo incident policy. Không dùng trạng thái `RETIRING` để trì hoãn revoke chỉ vì muốn tránh 401.

### 8.3. Không tái sử dụng key ID sau revoke

Key ID đã revoke cần giữ **tombstone/audit** theo retention; không cấp ID cũ cho secret khác hoặc rollback registry snapshot khiến `REVOKED → ACTIVE`. Sự không nhất quán này gây key-confusion, cache staleness và khó truy cứu.

### 8.4. Không đặt hạn ACTIVE bằng signed timestamp

Ví dụ old key hết hạn tại `2026-11-28T03:07:00Z`. Nếu request có signed timestamp `03:06:59` nhưng server nhận lúc `03:07:01`, verifier **reject** theo key validity dù timestamp vẫn fresh. Nếu thay bằng `signedTs < expiresAt`, kẻ có old secret có thể tiếp tục gửi request với timestamp cũ trong freshness window sau khi key đã bị vô hiệu hóa.

## 9. Java 17: dual-key verifier với exact key ID, HMAC và replay

Ví dụ dưới đây là một file **`DualVerificationExample.java`**, sử dụng Java 17 standard library. Nó gồm:

- Hai secret ngẫu nhiên **khác nhau**, key ID `key-2026-11` và `key-2026-12`.
- Registry có state `STAGED → ACTIVE → RETIRING → REVOKED`; snapshot record chỉ đọc, update state bằng conditional map operation trong demo.
- Signer ký method, raw target, audience, client/key ID, timestamp, nonce, content type và SHA-256 body.
- Verifier **tra chính xác signed kid**, kiểm tra state/time, HMAC full 32-byte tag và freshness, rồi claim nonce atomically theo **audience/client/nonce**.
- Test song song old/new cùng active, old ID mà tag dùng secret mới, unknown/revoked key, body tamper, cross-client, nonce replay qua rotation, clock boundaries, registry/nonce outage và **8 request đồng thời** cùng nonce dưới hai key ID.

**Đây là ví dụ sư phạm trong một JVM.** `KeyRegistry` và `NonceStore` không có persistent storage/distributed consensus. Trong production, cần trusted ingress, secret manager/KMS/HSM, atomic nonce store chung, TTL, audit, authorization, idempotency và replication/failover policy.

### 9.1. Chương trình hoàn chỉnh

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class DualVerificationExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String ENV = "prod";
    private static final String AUD = "payments-api";
    private static final String CLIENT = "partner-42";
    private static final String METHOD = "POST";
    private static final String TARGET = "/v1/payments?currency=VND";
    private static final String TYPE = "application/json";
    private static final String OLD = "key-2026-11";
    private static final String NEW = "key-2026-12";
    private static final long PAST = 300L;
    private static final long FUTURE = 60L;
    private static final long MARGIN = 10L;

    enum State { STAGED, ACTIVE, RETIRING, REVOKED }

    enum Result {
        VERIFIED, MALFORMED, STALE_TIMESTAMP, UNKNOWN_KEY,
        KEY_NOT_ACTIVE, BAD_SIGNATURE, REPLAY, STORE_UNAVAILABLE
    }

    record Locator(
        String environment, String audience, String clientId, String keyId
    ) {}

    record KeyRecord(
        Locator locator, byte[] secret, State state,
        Instant activeFrom, Instant expiresAt
    ) {}

    record Request(
        String method, String target, String clientId, String keyId,
        String timestamp, String nonce, String contentType,
        String bodySha256, String signature, byte[] body
    ) {}

    static final class KeyRegistry {
        private final ConcurrentHashMap<Locator, KeyRecord> keys =
            new ConcurrentHashMap<>();
        private volatile boolean available = true;

        void register(KeyRecord record) {
            if (keys.putIfAbsent(record.locator(), record) != null) {
                throw new IllegalStateException(
                    "Never overwrite a registered key ID");
            }
        }

        // Demo local atomic state transition; not distributed CAS.
        // A revoked key ID may never be revived by an old snapshot.
        boolean transition(Locator loc, State expected, State target) {
            AtomicBoolean updated = new AtomicBoolean(false);
            keys.computeIfPresent(loc, (k, old) -> {
                if (old.state() != expected) {
                    return old;
                }
                boolean allowed = switch (expected) {
                    case STAGED -> target == State.ACTIVE
                        || target == State.REVOKED;
                    case ACTIVE -> target == State.RETIRING
                        || target == State.REVOKED;
                    case RETIRING -> target == State.REVOKED;
                    case REVOKED -> false;
                };
                if (!allowed) {
                    return old;
                }
                updated.set(true);
                return new KeyRecord(old.locator(), old.secret(),
                    target, old.activeFrom(), old.expiresAt());
            });
            return updated.get();
        }

        KeyRecord lookup(Locator loc) {
            if (!available) {
                throw new IllegalStateException("Key store unavailable");
            }
            return keys.get(loc);
        }

        void setAvailable(boolean value) {
            available = value;
        }
    }

    // ONLY within one JVM; no replication, TTL cleanup, or durability.
    static final class NonceStore {
        private final ConcurrentHashMap<String, Long> expiryByKey =
            new ConcurrentHashMap<>();
        private volatile boolean available = true;

        void setAvailable(boolean value) {
            available = value;
        }

        boolean claim(String audience, String client, String nonce,
                long now, long expiry) {
            if (!available) {
                throw new IllegalStateException("Nonce store unavailable");
            }
            if (expiry <= now) {
                return false;
            }
            // Length-prefixed tuple: no ambiguous delimiters and NO kid.
            String scope =
                audience.length() + ":" + audience +
                client.length() + ":" + client +
                nonce.length() + ":" + nonce;
            AtomicBoolean created = new AtomicBoolean(false);
            expiryByKey.compute(scope, (key, previous) -> {
                if (previous != null && previous > now) {
                    return previous;
                }
                created.set(true);
                return expiry;
            });
            return created.get();
        }
    }

    static byte[] secret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return bytes;
    }

    static String nonce() {
        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    static boolean validId(String value) {
        return value != null &&
            value.matches("[a-z0-9][a-z0-9-]{0,39}");
    }

    static Long timestamp(String text) {
        if (text == null ||
            !text.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException overflow) {
            return null;
        }
    }

    static boolean fresh(long signedTs, long serverNow) {
        try {
            return signedTs >= Math.subtractExact(serverNow, PAST)
                && signedTs <= Math.addExact(serverNow, FUTURE);
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static String sha256Hex(byte[] data)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(data));
    }

    static byte[] hmacSha256(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8));
    }

    static String canonical(Request r, String actualBodyHash) {
        if (r == null || !METHOD.equals(r.method())
            || !TARGET.equals(r.target())
            || !TYPE.equals(r.contentType())
            || !validId(r.clientId())
            || !validId(r.keyId())
            || timestamp(r.timestamp()) == null
            || r.nonce() == null
            || !r.nonce().matches("[0-9a-f]{32}")
            || actualBodyHash == null
            || !actualBodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException(
                "Invalid HMAC-DUAL-VERIFY-V1 fields");
        }
        return String.join("\n",
            "HMAC-DUAL-VERIFY-V1",
            r.method(), r.target(),
            "audience:" + AUD,
            "x-client-id:" + r.clientId(),
            "x-key-id:" + r.keyId(),
            "x-timestamp:" + r.timestamp(),
            "x-nonce:" + r.nonce(),
            "content-type:" + r.contentType(),
            "x-content-sha256:" + actualBodyHash);
    }

    static byte[] strictSignature(String encoded) {
        // HMAC-SHA256 full 32B -> padded Basic Base64 44 characters.
        if (encoded == null ||
            !encoded.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] bytes = Base64.getDecoder().decode(encoded);
            if (bytes.length != 32 ||
                !Base64.getEncoder().encodeToString(bytes)
                    .equals(encoded)) {
                return null;
            }
            return bytes;
        } catch (IllegalArgumentException bad) {
            return null;
        }
    }

    static Request sign(
            byte[] secret, String kid, Clock signingClock,
            String nonce, byte[] body) throws GeneralSecurityException {
        String ts =
            Long.toString(signingClock.instant().getEpochSecond());
        String digest = sha256Hex(body);
        Request unsigned = new Request(
            METHOD, TARGET, CLIENT, kid, ts, nonce,
            TYPE, digest, "", body.clone());
        String signature = Base64.getEncoder().encodeToString(
            hmacSha256(secret, canonical(unsigned, digest)));
        return new Request(
            METHOD, TARGET, CLIENT, kid, ts, nonce,
            TYPE, digest, signature, body.clone());
    }

    static Result verify(
            Request r, KeyRegistry registry,
            NonceStore nonces, Clock clock)
            throws GeneralSecurityException {
        if (r == null || r.body() == null
            || r.body().length > 65536
            || !validId(r.clientId())
            || !validId(r.keyId())) {
            return Result.MALFORMED;
        }
        Long ts = timestamp(r.timestamp());
        byte[] supplied = strictSignature(r.signature());
        if (ts == null || supplied == null) {
            return Result.MALFORMED;
        }
        Instant verifiedAt = clock.instant();
        long now = verifiedAt.getEpochSecond();
        if (!fresh(ts, now)) {
            return Result.STALE_TIMESTAMP;
        }

        final String message;
        try {
            String computedDigest = sha256Hex(r.body());
            if (!computedDigest.equals(r.bodySha256())) {
                return Result.BAD_SIGNATURE;
            }
            message = canonical(r, computedDigest);
        } catch (IllegalArgumentException invalid) {
            return Result.MALFORMED;
        }

        // Claimed client ID + signed kid are only lookup hints until
        // the MAC validates. No attempt to try other keys on mismatch.
        Locator locator =
            new Locator(ENV, AUD, r.clientId(), r.keyId());
        final KeyRecord key;
        try {
            key = registry.lookup(locator);
        } catch (IllegalStateException outage) {
            return Result.STORE_UNAVAILABLE;
        }
        if (key == null) {
            return Result.UNKNOWN_KEY;
        }
        if (!locator.equals(key.locator())
            || !(key.state() == State.ACTIVE
                 || key.state() == State.RETIRING)
            || key.secret() == null
            || key.secret().length < 32
            || key.activeFrom() == null
            || key.expiresAt() == null
            || verifiedAt.isBefore(key.activeFrom())
            || !verifiedAt.isBefore(key.expiresAt())) {
            return Result.KEY_NOT_ACTIVE;
        }

        byte[] expected = hmacSha256(key.secret(), message);
        if (expected.length != 32 ||
            !MessageDigest.isEqual(expected, supplied)) {
            return Result.BAD_SIGNATURE;
        }

        final long expiresAt;
        try {
            expiresAt = Math.addExact(ts,
                Math.addExact(PAST, MARGIN));
        } catch (ArithmeticException overflow) {
            return Result.STALE_TIMESTAMP;
        }
        // Replay namespace deliberately omits kid across rotation.
        try {
            return nonces.claim(AUD, r.clientId(), r.nonce(),
                    now, expiresAt)
                ? Result.VERIFIED : Result.REPLAY;
        } catch (IllegalStateException outage) {
            return Result.STORE_UNAVAILABLE; // fail closed.
        }
    }

    static Request changeKeyIdWithoutResigning(
            Request r, String changedKid) {
        return new Request(
            r.method(), r.target(), r.clientId(), changedKid,
            r.timestamp(), r.nonce(), r.contentType(),
            r.bodySha256(), r.signature(), r.body());
    }

    static Request changeClientWithoutResigning(
            Request r, String changedClient) {
        return new Request(
            r.method(), r.target(), changedClient, r.keyId(),
            r.timestamp(), r.nonce(), r.contentType(),
            r.bodySha256(), r.signature(), r.body());
    }

    static Request changeBodyWithoutResigning(
            Request r, byte[] body) {
        return new Request(
            r.method(), r.target(), r.clientId(), r.keyId(),
            r.timestamp(), r.nonce(), r.contentType(),
            r.bodySha256(), r.signature(), body);
    }

    static void require(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    static void rfc4231TestVector() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        require(expected.equals(
            HexFormat.of().formatHex(hmacSha256(key, "Hi There"))),
            "HMAC-SHA256 RFC 4231 vector");
    }

    public static void main(String[] args) throws Exception {
        rfc4231TestVector();
        Instant t0 = Instant.parse("2026-11-28T02:00:00Z");
        Clock beforeOverlap = Clock.fixed(t0, ZoneOffset.UTC);
        Clock overlap = Clock.fixed(
            t0.plusSeconds(300), ZoneOffset.UTC);
        byte[] oldSecret = secret();
        byte[] newSecret = secret();
        byte[] body =
            "{\"orderId\":\"ord-123\",\"amount\":50000}"
                .getBytes(StandardCharsets.UTF_8);
        Locator oldLoc = new Locator(ENV, AUD, CLIENT, OLD);
        Locator newLoc = new Locator(ENV, AUD, CLIENT, NEW);
        KeyRegistry registry = new KeyRegistry();
        registry.register(new KeyRecord(
            oldLoc, oldSecret, State.ACTIVE,
            t0.minusSeconds(3600), t0.plusSeconds(7200)));
        registry.register(new KeyRecord(
            newLoc, newSecret, State.STAGED,
            t0.plusSeconds(300), t0.plusSeconds(14400)));

        // Valid MAC under STAGED key must NOT pass verification.
        Request staged = sign(
            newSecret, NEW, beforeOverlap, nonce(), body);
        require(verify(staged, registry, new NonceStore(),
                beforeOverlap) == Result.KEY_NOT_ACTIVE,
            "STAGED must not be accepted");

        // Old key works before and during overlap.
        Request oldBefore = sign(
            oldSecret, OLD, beforeOverlap, nonce(), body);
        require(verify(oldBefore, registry,
                new NonceStore(), beforeOverlap) == Result.VERIFIED,
            "Old key before cutover must verify");

        // Simulated control plane: new key provisioned/readiness complete.
        require(registry.transition(
                newLoc, State.STAGED, State.ACTIVE),
            "New key must activate exactly once");
        require(!registry.transition(
                newLoc, State.STAGED, State.ACTIVE),
            "Second state transition must not overwrite");
        require(registry.transition(
                oldLoc, State.ACTIVE, State.RETIRING),
            "Old key enters verification grace period");

        Request oldDuring = sign(
            oldSecret, OLD, overlap, nonce(), body);
        Request newDuring = sign(
            newSecret, NEW, overlap, nonce(), body);
        NonceStore shared = new NonceStore();
        require(verify(oldDuring, registry,
                shared, overlap) == Result.VERIFIED,
            "Dual acceptance: old key in RETIRING");
        require(verify(newDuring, registry,
                shared, overlap) == Result.VERIFIED,
            "Dual acceptance: new key in ACTIVE");

        // Show wire contract but DO NOT send HTTP.
        HttpRequest sample = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + TARGET))
            .header("Content-Type", newDuring.contentType())
            .header("X-Client-Id", newDuring.clientId())
            .header("X-Key-Id", newDuring.keyId())
            .header("X-Timestamp", newDuring.timestamp())
            .header("X-Nonce", newDuring.nonce())
            .header("X-Content-SHA256", newDuring.bodySha256())
            .header("X-Signature", newDuring.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(
                newDuring.body()))
            .build();
        require(METHOD.equals(sample.method()),
            "HTTP sample method");

        // Exact nonce replay under same key.
        require(verify(oldDuring, registry,
                shared, overlap) == Result.REPLAY,
            "Old key exact replay must fail");

        // Critical: same client/audience/nonce under a DIFFERENT key
        // remains a replay even when tag and signed kid are both new.
        Request sameNonceNewKey = sign(
            newSecret, NEW, overlap, oldDuring.nonce(), body);
        require(verify(sameNonceNewKey, registry,
                shared, overlap) == Result.REPLAY,
            "Rotation must not reset claimed nonce history");

        // Claim old kid, sign tag with new secret: must NOT try all keys.
        Request wrongSecretForOldId = sign(
            newSecret, OLD, overlap, nonce(), body);
        require(verify(wrongSecretForOldId, registry,
                new NonceStore(), overlap) == Result.BAD_SIGNATURE,
            "Old kid + new secret is NOT a valid fallback");

        // Tamper signed kid while keeping old signature: no fallback.
        Request alteredKid =
            changeKeyIdWithoutResigning(oldDuring, NEW);
        require(verify(alteredKid, registry,
                new NonceStore(), overlap) == Result.BAD_SIGNATURE,
            "Unsigned change of kid must fail HMAC");

        // Unknown kid must fail even when signed with a known secret.
        Request unknownKid = sign(
            oldSecret, "key-2026-99", overlap, nonce(), body);
        require(verify(unknownKid, registry,
                new NonceStore(), overlap) == Result.UNKNOWN_KEY,
            "Unknown kid must never try old/new by trial");

        // Caller cannot impersonate another client by rewriting ID.
        Request changedClient =
            changeClientWithoutResigning(newDuring, "partner-77");
        require(verify(changedClient, registry,
                new NonceStore(), overlap) == Result.UNKNOWN_KEY,
            "Cross-client key lookup must not borrow partner-42 key");

        // Tampered body must be rejected without consuming nonce.
        Request untaken = sign(
            newSecret, NEW, overlap, nonce(), body);
        byte[] corrupt = untaken.body().clone();
        corrupt[0] ^= 1;
        NonceStore bodyGuard = new NonceStore();
        require(verify(changeBodyWithoutResigning(untaken, corrupt),
                registry, bodyGuard, overlap)
                == Result.BAD_SIGNATURE,
            "Body tampering must fail");
        require(verify(untaken, registry,
                bodyGuard, overlap) == Result.VERIFIED,
            "Bad MAC must not burn nonce");

        // Test timestamp freshness boundaries using the new active key.
        for (long offset : new long[] {-300L, +60L}) {
            Clock signedClock = Clock.offset(
                overlap, Duration.ofSeconds(offset));
            Request boundary = sign(
                newSecret, NEW, signedClock, nonce(), body);
            require(verify(boundary, registry, new NonceStore(),
                    overlap) == Result.VERIFIED,
                "Inclusive timestamp boundary " + offset);
        }
        for (long offset : new long[] {-301L, +61L}) {
            Clock signedClock = Clock.offset(
                overlap, Duration.ofSeconds(offset));
            Request outside = sign(
                newSecret, NEW, signedClock, nonce(), body);
            require(verify(outside, registry, new NonceStore(),
                    overlap) == Result.STALE_TIMESTAMP,
                "Reject timestamp boundary " + offset);
        }

        // Concurrent claims across BOTH key versions, same nonce:
        // one passes even though valid signatures use different keys.
        NonceStore contested = new NonceStore();
        String contestedNonce = nonce();
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch ready = new CountDownLatch(8);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<Result>> results = new ArrayList<>();
        try {
            for (int i = 0; i < 8; i++) {
                Request signed = (i % 2 == 0)
                    ? sign(oldSecret, OLD, overlap,
                        contestedNonce, body)
                    : sign(newSecret, NEW, overlap,
                        contestedNonce, body);
                results.add(pool.submit((Callable<Result>) () -> {
                    ready.countDown();
                    release.await();
                    return verify(signed, registry, contested, overlap);
                }));
            }
            ready.await();
            release.countDown();
            int verified = 0;
            int replays = 0;
            for (Future<Result> f : results) {
                Result result = f.get();
                if (result == Result.VERIFIED) {
                    verified++;
                } else if (result == Result.REPLAY) {
                    replays++;
                } else {
                    throw new AssertionError(
                        "Unexpected concurrent result: " + result);
                }
            }
            require(verified == 1 && replays == 7,
                "Exactly one of 8 same-nonce requests may pass");
        } finally {
            release.countDown();
            pool.shutdownNow();
        }

        // Old key's verification time window is independent of ts.
        Clock atOldExpiry = Clock.fixed(
            t0.plusSeconds(7200), ZoneOffset.UTC);
        Request lateOld = sign(
            oldSecret, OLD, atOldExpiry, nonce(), body);
        require(verify(lateOld, registry,
                new NonceStore(), atOldExpiry)
                == Result.KEY_NOT_ACTIVE,
            "Old key expires at exclusive expiresAt");

        // Revoke old; all old-key requests fail even when HMAC is valid.
        require(registry.transition(
                oldLoc, State.RETIRING, State.REVOKED),
            "Old key must be revocable");
        require(!registry.transition(
                oldLoc, State.REVOKED, State.ACTIVE),
            "Revoked key must never be reactivated");
        require(verify(oldDuring, registry,
                new NonceStore(), overlap)
                == Result.KEY_NOT_ACTIVE,
            "Revoked old key must not be accepted");
        Request newAfterRevoke = sign(
            newSecret, NEW, overlap, nonce(), body);
        require(verify(newAfterRevoke, registry,
                new NonceStore(), overlap) == Result.VERIFIED,
            "New key remains valid after old key revoked");

        // Outage must not be treated as unknown/default-key success.
        registry.setAvailable(false);
        require(verify(newAfterRevoke, registry,
                new NonceStore(), overlap)
                == Result.STORE_UNAVAILABLE,
            "Key registry outage must fail closed");
        registry.setAvailable(true);
        NonceStore down = new NonceStore();
        down.setAvailable(false);
        require(verify(newAfterRevoke, registry,
                down, overlap) == Result.STORE_UNAVAILABLE,
            "Nonce store outage must fail closed");

        System.out.println(
            "PASS: dual verification, rotation, exact key ID, replay");
    }
}
~~~

### 9.2. Những nguyên tắc quan trọng trong ví dụ

**Thứ nhất — dual acceptance tại registry, không thử-all-key:**

~~~java
Locator locator = new Locator(
    ENV, AUD, r.clientId(), r.keyId()
);
KeyRecord key = registry.lookup(locator);
if (key == null) {
    return Result.UNKNOWN_KEY;
}
byte[] expected = hmacSha256(key.secret(), message);
if (!MessageDigest.isEqual(expected, supplied)) {
    return Result.BAD_SIGNATURE;
}
~~~

Ở production, còn phải kiểm tra `state/time/algorithm/scope` và full tag length như chương trình hoàn chỉnh ở trên. Không chọn key bằng cách “thử MAC tất cả key rồi trả key đầu tiên khớp”.

**Thứ hai — nonce namespace không có key ID:**

~~~java
String scope =
    audience.length() + ":" + audience +
    client.length() + ":" + client +
    nonce.length() + ":" + nonce;
~~~

`ConcurrentHashMap.compute` trong demo cho atomic update **trên một process**, không thay Redis `SET NX PX`, SQL unique insert hoặc store có tính nhất quán chung khi nhiều gateway/region tranh chấp.

**Thứ ba — hết hạn dựa trên server verify time:** `verifiedAt` được dùng để kiểm tra `activeFrom/expiresAt` và key state. Signed timestamp chỉ dùng cho **freshness**; một attacker có old secret không được “lùi thời gian” để làm key đã revoke hoạt động trở lại.

### 9.3. Những hạn chế chủ động của mã

- `Request` là mô hình các field đã được parse; **không** thể phát hiện hai `X-Key-Id`, `X-Nonce` hay `X-Signature` do proxy gộp. Trusted ingress phải reject ambiguity và oversized/CRLF trước khi tạo record.
- `KeyRegistry` là `ConcurrentHashMap` trong một JVM, **không** có KMS/IAM, replication, distributed CAS hoặc durable audit.
- `NonceStore` không có background cleanup/persistence và chưa có multi-region consistency; chỉ minh họa atomic update cục bộ. Production phải đặt TTL theo timestamp policy và xử lý failover/eviction.
- Hàm `sign` nhận raw secret; production signer phải dùng secret manager/keystore, tránh debug/log/heap dump lộ bytes. `Mac` instance mới cho mỗi operation; không chia sẻ state sai giữa thread.
- Ví dụ minh họa planned rotation; nếu old key bị compromise, **revoke ngay**, không tiếp tục overlap cho “êm”.
- Không có business payment thực: **authorization** và **idempotency** phải được thêm trước khi thực hiện side effect.
- `String.matches`, `Base64` và `MessageDigest.isEqual` là các thành phần minh họa strict parser/comparison; toàn bộ HTTP pipeline **không được đảm bảo constant-time** chỉ vì dùng một phép so sánh byte an toàn.

## 10. Deployment readiness, cache và multi-region

### 10.1. Provision-before-use

Một quy trình tương đối tin cậy:

1. Provision key mới trong key manager/KMS; gắn đúng client ID, audience, environment và allowed routes.
2. Stage key với state **không cho verify**, đồng thời phân phối record/key reference tới verifier fleet và signer qua kênh an toàn.
3. Chạy health checks **theo config version**, test vectors MAC và quyền key access cho mọi gateway sẽ nhận traffic.
4. Sau readiness, **activate new key** tại authoritative control plane, có compare-and-set/version.
5. Quan sát canary request mới và tỷ lệ `kid` mới; hướng dẫn client cutover.
6. Giữ old key `ACTIVE/RETIRING` chỉ tới **deadline** đã công bố; monitor remaining old-key usage.
7. Revoke/expire old, invalidation các verifier cache; xác nhận new key vẫn xử lý bình thường.

**Readiness ACK không chứng minh data-plane consistency toàn cục** khi thêm pod mới, failover hay network partition. Nếu yêu cầu không reject hợp lệ khi active cả hai, cần routing/version barrier hoặc strong consistency phù hợp. Nếu hệ thống không bảo đảm, phải ghi rõ availability SLA và fail-closed khi không thấy đúng state.

### 10.2. Positive và negative cache

| Loại cache | Rủi ro trong dual verification | Thiết kế |
| --- | --- | --- |
| Key record cache ACTIVE | Old key bị revoke nhưng cache còn nhận request. | TTL/invalidation đáp ứng revoke SLA, version/epoch check. |
| Key record cache STAGED | New key đã activate nhưng một verifier vẫn reject. | Propagation + readiness + canary/monitoring. |
| NOT_FOUND negative cache | New ID vừa provision nhưng replica giữ NOT_FOUND cũ. | TTL ngắn, invalidation theo version, bounds. |
| Full `kid`-only cache | Same ID của client khác bị dùng nhầm. | Cache theo exact locator `(env,audience,clientId,kid)`. |
| Secret material quá rộng | Compromise gateway làm lộ key của nhiều khách hàng. | Workload identity, least privilege, partition, KMS VerifyMac nếu khả thi. |
| Key manager outage → default key | Bypass security ở thời điểm outage. | Fail closed; phân biệt NOT_FOUND và UNAVAILABLE. |

### 10.3. Multi-region active-active

Nếu traffic được phân phối A/B region:

~~~text
Region A: old=RETIRING, new=ACTIVE
Region B: old=ACTIVE, new=STAGED
~~~

Đây không chỉ gây lỗi new-key request; nó còn có thể khiến revocation **không đồng nhất**. Cần control-plane consistency hoặc route traffic qua các verifier có version đủ mới. Nonce replay protection **cũng cần thẩm quyền chung/nhất quán**: hai nonce store độc lập có thể cho cùng nonce claim một lần ở A và một lần ở B.

### 10.4. Operation timeout không phải authentication success

Nếu KMS `VerifyMac`, registry lookup hoặc nonce store timeout, verifier **không** có bằng chứng request hợp lệ. Trạng thái đó không được coi là “key còn active” hoặc “nonce mới”. Tùy API, có thể trả lỗi dịch vụ chung (ví dụ 503), nhưng **không thực hiện side effect**.

## 11. Proxy/gateway và parser differential trong dual verification

~~~mermaid
sequenceDiagram
    participant C as Client signer
    participant P as Untrusted proxy
    participant G as Trusted gateway
    participant K as Scoped key registry
    participant N as Shared nonce store
    participant B as Backend
    C->>P: Signed method, raw path, headers/body + kid A hoặc B
    P->>G: Forward / retry / possible rewrite
    G->>G: Reject duplicate key ID, nonce, timestamp, sig
    G->>K: Lookup exact scoped kid and state
    alt Old ACTIVE/RETIRING
        K-->>G: Old key (scope + validity)
    else New ACTIVE
        K-->>G: New key (scope + validity)
    else Unknown/expired/revoked
        K-->>G: Deny / not found
        G-->>C: Authn failure
    end
    G->>G: Recompute HMAC over same canonical request
    G->>N: Signed ts freshness + atomic nonce claim
    N-->>G: CREATED / REPLAY
    G->>B: Verified identity + original signed semantics
    B->>B: Authorization + idempotency
~~~

| Vấn đề | Nguy cơ | Biện pháp |
| --- | --- | --- |
| Hai `X-Key-Id` khác chữ hoa/thường | Gateway lấy A, backend lấy B. | Reject duplicate security field lines tại trusted ingress. |
| `Authorization` HMAC và `X-Key-Id` cạnh tranh | Một tầng chọn kid từ auth-param, tầng khác từ header. | Chọn một nguồn theo scheme; reject ambiguity, không fallback. |
| Proxy đổi raw path/query order | HMAC ký một action, backend thực thi action khác. | Ký/verify raw method+target đúng ngữ nghĩa; thống nhất trust boundary. |
| Proxy nén/giải nén body | Body bytes hoặc Content-Encoding khác khi verify. | Contract representation rõ; verify bytes thực được xử lý. |
| Proxy retry nguyên request | Cùng tag/ts/nonce có thể bị gửi lần nữa. | Atomic nonce claim; không cho qua vì dual-key state. |
| Gateway verify nhưng backend public bypass | Bỏ qua HMAC. | Chặn direct backend, mTLS/internal auth và strip spoofed headers. |
| Gateway lỡ dùng old secret khi unknown kid | Downgrade ngoài overlap. | Exact lookup và fail closed. |
| Key rotation dùng keyring ở gateway, backend dùng keyring khác | Hai nơi diễn giải policy trái nhau. | Một authoritative verification boundary và config version. |

### 11.1. Một điểm xác thực có thẩm quyền

Nếu gateway đã verify HMAC và claim nonce, backend không nên tự ý **claim lần hai** cùng nonce rồi coi đó là replay nếu không có giao thức phối hợp. Xác định một **verification boundary** duy nhất hoặc thiết kế **signed internal assertion**/mTLS với semantics rõ; backend tuyệt đối không tin `X-Verified: true` từ Internet.

### 11.2. Authentication không thay authorization

Một request `partner-42` ký hợp lệ với old/new key chỉ chứng minh credential hợp lệ và message integrity theo HMAC contract. Nó **không** cho phép chuyển tiền tenant khác hoặc vượt hạn mức. Backend phải kiểm tra tenant, resource, action, scope, risk policy và idempotency riêng.

## 12. Phản hồi lỗi, telemetry và audit khi có hai key

Các lỗi nội bộ nên phân biệt rõ:

~~~text
UNKNOWN_KEY_ID       -> exact locator không có bản ghi
KEY_NOT_ACTIVE       -> staged / expired / revoked / wrong scope
BAD_SIGNATURE        -> đúng key record nhưng HMAC không khớp
STALE_TIMESTAMP      -> signed ts ngoài freshness policy
REPLAY               -> nonce đã claim trong cùng client/audience
KEY_STORE_UNAVAILABLE -> lỗi registry/KMS
NONCE_STORE_UNAVAILABLE -> lỗi replay store
~~~

Tuy nhiên **public API** có thể trả một lỗi authentication generic (ví dụ 401 với `WWW-Authenticate: HMAC-V1 realm="payments-api"` cho scheme minh họa) để tránh cung cấp **key enumeration oracle**. Với outage hạ tầng, có thể dùng response 503 theo contract; vẫn **fail closed**.

### 12.1. Không tạo timing oracle bằng fallback

Nếu unknown kid khiến verifier thử nhiều key hoặc lỗi bad HMAC mất thời gian khác xa unknown, attacker có thể học được thông tin registry. Các biện pháp:

- Giới hạn alphabet/length của key ID và tốc độ lookup.
- Không trả danh sách key ID hợp lệ, secret metadata hay policy chi tiết ra Internet.
- So sánh **full tag bytes** bằng `MessageDigest.isEqual` sau strict Base64 decode.
- Không hứa **constant-time end-to-end**: key lookup, policy, HTTP parse, nonce store và network vẫn có timing khác biệt.
- Đánh giá dummy HMAC cho unknown kid **chỉ nếu threat model cần**, giới hạn CPU/DoS và luôn reject; không biến dummy key thành default key hợp lệ.

### 12.2. Audit cần ghi những gì?

Một record rotation/verification tối thiểu:

~~~json
{
  "event": "hmac_verification",
  "environment": "prod",
  "audience": "payments-api",
  "clientScope": "partner-42",
  "keyVersionClass": "new",
  "decision": "VERIFIED",
  "registryVersion": "v42",
  "requestId": "req-opaque-123"
}
~~~

Log/metrics nên dùng **classes hoặc scoped IDs đã kiểm soát cardinality**, không tạo labels từ raw `kid` do attacker gửi. Không ghi shared secret, full signature, raw Authorization, canonical chứa PII hoặc body nhạy cảm. Audit lifecycle cần actor được xác thực, thời điểm, old/new state và approval; lưu theo retention/immutability policy.

### 12.3. Dấu hiệu cần cảnh báo

| Metric | Vì sao đáng chú ý |
| --- | --- |
| Old-key traffic % theo client | Kiểm tra client cutover và deadline. |
| New-key unknown/staged errors theo gateway | Lệch propagation, cache invalidation hoặc rollout sớm. |
| Bad HMAC tăng ngay sau activation | Sai secret/encoding/canonical, proxy rewrite hoặc key ID mismatch. |
| Replay tăng khi đổi key | Nonce reuse giữa client instances hoặc attack. |
| Revoked key verification attempts | Client chưa cập nhật hoặc key bị lạm dụng. |
| Registry/KMS unavailable/timeouts | Không thể verify, phải fail closed và xử lý availability. |
| Nonce store duplicates/evictions | Nguy cơ replay khi TTL/consistency sai. |
| Clock skew/outside window | Key activeFrom và signed freshness bị đánh giá không đồng đều. |
| Gateway registry version drift | Key state có thể khác nhau giữa replicas. |

## 13. Ma trận kiểm thử Dual verification

Các test dưới đây mô tả kỳ vọng của **signed `kid` contract**. Java example xác minh logic cục bộ; multi-region/Redis/KMS/HTTP parsing phải được test tích hợp trên hệ thống thật.

| Ca thử | Thao tác | Kết quả cần đạt |
| --- | --- | --- |
| Old ACTIVE trước rotation | Sign bằng old secret và old kid | HMAC và nonce hợp lệ → **ACCEPT**. |
| New STAGED | Sign đúng bằng new secret khi new chưa active | **Reject**, dù MAC khớp toán học. |
| Activate new | Registry chuyển `STAGED→ACTIVE` sau readiness | Verifier cho phép new kid đúng thời gian/scope. |
| Dual overlap | Gửi request A và B với nonce khác nhau | **Cả hai ACCEPT** nếu cùng thỏa policy. |
| Old RETIRING | Old request còn trong grace | Verify cho đến cutoff nếu contract cho phép. |
| Old REVOKED | Old tag đúng nhưng key đã revoke | **Reject** trước nonce/business. |
| Old expired | `serverNow == expiresAt` | **Reject**, end exclusive. |
| New key continues | Revoke old, ký đúng bằng new | New request vẫn được nhận. |
| Wrong secret for claimed kid | Khai old kid, ký bằng new secret | **BAD_SIGNATURE**, không fallback. |
| Unknown kid | Khai ID không có, tag vẫn full-length | Reject unknown, không thử A/B. |
| Same ID reused | Đăng ký lại cùng locator với secret khác | Registry **reject**; không overwrite. |
| Client ID giả | Đổi `X-Client-Id` sang khách hàng khác | Scoped lookup fail hoặc MAC fail. |
| Audience khác | Key payments dùng trên admin API | Reject theo audience/server policy. |
| Key ID tampered | Thay old kid thành new kid, giữ tag | MAC FAIL. |
| Body tampered | Sửa bytes JSON, giữ signature | MAC FAIL; không claim nonce. |
| Timestamp -300 | Signed ts đúng biên quá khứ | Freshness PASS, nếu key cũng active. |
| Timestamp -301 | Quá biên một giây | Reject stale. |
| Timestamp +60 | Signed ts đúng biên tương lai | Freshness PASS. |
| Timestamp +61 | Tương lai quá xa | Reject. |
| Replay old key | Gửi lại nguyên old request | Nonce store **REPLAY**. |
| Same nonce, new kid | Dùng new secret ký lại cùng nonce old đã claim | **REPLAY** trong cùng audience/client. |
| 8 concurrent old/new | Tám chữ ký hợp lệ cùng nonce, hai key | **Một** ACCEPT, **bảy** REPLAY tại authoritative nonce store. |
| Nonce TTL quá ngắn | Xóa nonce khi request còn fresh | Test phát hiện double-claim. |
| Redis/SQL atomic nonce | Multi-process claim same tuple | Tối đa một CREATED nếu store đáp ứng consistency contract. |
| Redis failover lost write | Nonce mất sau ACK | Phát hiện durable replay gap. |
| Registry outage | Lookup secret timeout | FAIL CLOSED, không dùng default key. |
| Nonce store outage | Không biết nonce đã claim chưa | FAIL CLOSED, không coi miss. |
| Negative-cache stale | Key mới active nhưng verifier còn NOT_FOUND | Detect; invalidation/readiness/version barrier. |
| Revocation lag | Một region còn ACTIVE old key | Detect; giới hạn propagation theo SLA/threat model. |
| Client retries new nonce | Cùng business intent, new timestamp/key | HMAC có thể pass; **idempotency** chặn side effect lặp. |
| Authentication pass, authz fail | Client đúng secret nhưng không có quyền resource | **403/deny business**, không thực thi. |
| Duplicate `X-Key-Id` | Hai field line khác case | Reject tại ingress. |
| HTTP/1.1 ↔ HTTP/2 proxy | Raw method/path/query/body được chuyển qua gateway | Verifier/backend cùng semantics, không mơ hồ. |

### Câu hỏi tự đánh giá

1. Dual verification nghĩa là API nhận **hai key version**, hay mỗi request phải chứa **hai chữ ký**?
2. Vì sao request khai `key-2026-12` nhưng được ký bằng secret A của `key-2026-11` phải bị từ chối, thay vì thử secret A để “giúp” client?
3. Sự khác nhau giữa **new key STAGED**, **ACTIVE** và **old key RETIRING** trong overlap là gì?
4. Nếu old secret đã bị lộ, dual verification giúp hay kéo dài khả năng attacker tạo request mới?
5. Vì sao `(audience,clientId,keyId,nonce)` không phải nonce namespace phù hợp trong ví dụ?
6. Với `P=300,F=60,M=10`, vì sao TTL 300 giây từ lần claim sớm nhất không đủ?
7. Nếu new key active trên gateway A nhưng còn staged trên B, có nên dùng default secret trên B để tránh 401 không?
8. Tại thời điểm old key đã revoked, request có signed timestamp trước revoke và MAC đúng có còn được nhận không?
9. Vì sao client retry với nonce mới, signature mới trong rotation vẫn cần **Idempotency-Key** cho payment?
10. Authentication thành công với new key có thay thế authorization tenant/resource không?

## 14. Checklist triển khai

- [ ] Định nghĩa planned rotation, active/retiring/revoked policy, overlap window và deadline old verify cutoff **rõ ràng**; compromised key phải revoke theo incident policy.
- [ ] Dùng **secret mới khác secret cũ** và key ID/version bất biến; không tái sử dụng ID đã thu hồi.
- [ ] Provision new key qua secret manager/KMS/HSM, access policy least privilege, client onboarding được xác thực, không ghi key bytes trong source/log.
- [ ] Stage new key, phân phối đúng client/audience/environment/method/route/algorithm cho verifier fleet **trước khi activate**.
- [ ] Kiểm tra readiness/version ở mọi gateway nhận traffic; activation atomic/idempotent, theo dõi eventual propagation và canary.
- [ ] Với một request, chọn đúng **signed key ID** rồi verify bằng **một** secret record được phép. Không thử tất cả keys, không default/fallback key, không downgrade sang legacy.
- [ ] Signed canonical chứa **clientId, keyId, timestamp, nonce**, method, raw URI/query, content type và body digest; HMAC-SHA256 full 32-byte tag.
- [ ] Strict parse, reject malformed/duplicate security headers và ambiguous auth-param, Base64 chuẩn padded full tag; so sánh bằng `MessageDigest.isEqual`.
- [ ] Check `key.state∈{ACTIVE,RETIRING}`, server-verified `activeFrom <= now < expiresAt` và not revoked; không dùng signedTs để kéo dài key validity.
- [ ] Signed timestamp freshness theo `now-P <= ts <= now+F`; nonce atomically claim **sau** HMAC PASS.
- [ ] Nonce namespace theo **(audience, authenticatedClientId, nonce)**, **không có keyId**, bảo toàn replay history xuyên rotation.
- [ ] Nonce TTL giữ tới sau `signedTs+P+margin` hoặc relative TTL `P+F+margin`; không evict sớm, kiểm thử failover/durability.
- [ ] Khi KMS/registry/nonce store lỗi, **fail closed**; không bật xác thực “tạm thời” hoặc bỏ qua replay guard.
- [ ] Key cache, positive/negative cache, active/revoke propagation theo version/TTL và consistency SLA; giám sát multi-region drift.
- [ ] Client chỉ ký new requests bằng new key sau cutover; xác định grace cho in-flight old requests và deadline retire/revoke.
- [ ] Nếu buộc dùng legacy không có key ID, giới hạn trong **versioned compatibility path** ngắn hạn, không fallback trên API V1.
- [ ] Proxy/gateway preserve signed request semantics, strip inbound identity spoof, mTLS hop nội bộ, chặn direct backend bypass.
- [ ] Sau authentication/replay guard, backend thực hiện **authorization** theo client/tenant/action/resource và **idempotency** cho retry cùng business intent.
- [ ] Audit rotation, key state, config revision, signed kid usage và HMAC/replay failures; redact secret, signature, body nhạy cảm và không dùng raw attacker kid làm metrics label.
- [ ] Integration test concurrent old/new traffic, 8-way nonce race, unknown kid/bad tag, old revoke/expire, registry outage, TTL, key rollout nhiều gateway và HTTP proxy.

**Kết luận:** **Dual verification** cho phép verifier **nhận chữ ký từ hai phiên bản khóa đang hợp lệ** trong một giai đoạn rotation được kiểm soát, nhưng vẫn chỉ sử dụng **đúng secret theo signed key ID của từng request**. Thành công của rotation phụ thuộc provision-before-use, key readiness, cutoff/revoke nhất quán, canonical request chính xác và **nonce replay store dùng chung qua hai key ID**. Một request vượt qua HMAC, timestamp và nonce vẫn phải được kiểm tra **authorization**; các retry bằng secret mới phải có **idempotency** để không tạo side effect trùng. Dual verification giúp giảm gián đoạn khi **planned rotation**, không thay thế việc revoke ngay khi old secret bị compromise.
