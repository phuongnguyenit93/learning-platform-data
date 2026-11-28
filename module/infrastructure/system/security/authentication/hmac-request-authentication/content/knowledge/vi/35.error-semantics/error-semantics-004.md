# Sai key ID

Trong xác thực HTTP request bằng **HMAC**, **key ID** (key identifier, thường gọi `kid` hay `keyId`) là giá trị client gửi để server tìm **đúng bản ghi credential và shared secret** dùng xác minh chữ ký. Key ID thiếu, sai định dạng, không tồn tại, bị tráo hoặc đã bị thu hồi đều có thể làm request không được xác thực dù có trường `X-Signature`.

Bài **“Sai key ID”** thuộc chương **Error semantics** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun hướng dẫn xác thực HTTP request bằng HMAC với shared secret và canonical request gồm method, URI, header hoặc body theo hợp đồng ký; xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**.

> **Nguyên tắc:** Key ID là **selector do client khai**, không phải bằng chứng danh tính và thường không phải bí mật. Server chỉ tra **một** credential record bằng exact ID, kiểm lifecycle/audience, tính expected HMAC bằng secret của record đó và so **toàn bộ tag**. Nếu ID sai hoặc không có bản ghi đáng tin thì **reject**; không thử secret mặc định, không quét mọi secrets, không tạo principal từ prefix của key ID. Lỗi nội bộ đủ chi tiết để vận hành, nhưng phản hồi HTTP phải hạn chế lộ key nào tồn tại/đang hoạt động.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **key ID**, client ID, principal ID, shared secret, audience và tenant ID.
2. Giải thích key ID là **untrusted selector**, không phải credential đủ để đăng nhập.
3. Phân loại missing/malformed/duplicate/unknown/wrong-key/revoked/expired/wrong-audience và lookup-unavailable.
4. Thiết kế grammar, encoding, case sensitivity và exact-match lookup ổn định.
5. Ràng buộc key ID vào **canonical request được ký bằng HMAC**.
6. Thiết kế public HTTP semantics `400`/`401`/`403`/`503` và `WWW-Authenticate` theo hợp đồng.
7. Chống key-existence enumeration qua response status/body/timing và high-cardinality requests.
8. Phân biệt key ID mismatch với signature mismatch, nonce replay và tenant authorization deny.
9. Xử lý key rotation, key compromise, revoked credential và cache consistency.
10. Cài đặt Java 17 parser, registry, verifier, typed outcomes và JUnit 5 negative tests.
11. Kết nối các outcomes với Spring Security MVC/WebFlux mà không fail open.
12. Thiết kế test matrix, observability và runbook sự cố.

## 2. Key ID là gì và không phải gì?

Một credential record minh họa:

~~~text
clientId:      partner-A
principalId:   partner-a-service
keyId:         partner-a-k3
sharedSecret:  <32 bytes bí mật, cấp riêng cho k3>
algorithm:     HmacSHA256
audience:      orders-api
status:        ACTIVE
~~~

Client gửi `keyId=partner-a-k3`. Server tra `partner-a-k3` từ **trusted registry** và tính:

\[
T_{\mathrm{expected}} =
\operatorname{HMAC}_{K_{\mathrm{partner-a-k3}}}
  (\operatorname{CanonicalRequest}(R)).
\]

Chỉ nếu credential policy đạt và full tag client gửi bằng expected tag mới xác nhận năng lực sử dụng secret. Timestamp/nonce còn phải đạt điều kiện chống replay. Sau thành công, **principal được lấy từ trusted registry**, không được suy từ text key ID.

| Đối tượng | Ví dụ | Tin được trước khi kiểm HMAC? |
| --- | --- | --- |
| Key ID HTTP field | `X-Key-Id: partner-a-k3` | Không; selector do caller khai |
| Shared secret | Bytes trong KMS/secret store | Có nếu trusted provenance |
| Credential record | Key ID → principal/secret/policy | Có nếu trusted registry |
| Presented signature | Base64URL HMAC | Không, phải tính lại |
| Timestamp/nonce | `X-Timestamp`/`X-Nonce` | Chỉ được ràng buộc integrity sau full HMAC |
| Trusted principal | `partner-a-service` | Chỉ tạo sau verification thành công |
| Tenant/role claim | `X-Tenant-Id`, `X-Role` | Không tự cấp quyền |
| Authorization grants | Trusted server policy | Bước khác sau authentication |

### 2.1. Key ID không phải shared secret

Biết key ID chỉ cho attacker biết **nhãn cần lookup**. Nó không giúp tạo HMAC hợp lệ nếu không biết secret của record đó. Không dùng `registry.exists(keyId)` làm điều kiện cấp `SecurityContext`.

~~~java
// SAI: một key ID tồn tại không chứng minh caller biết secret.
String id = request.getHeader("X-Key-Id");
if (registry.exists(id)) {
    setAuthenticatedPrincipal(id);
}
~~~

Một key ID có thể tiết lộ tên đối tác, môi trường hoặc tenant nếu được đặt dễ đoán; vì vậy cần policy logs/privacy. Nhưng **security không được dựa vào việc giữ bí mật ID**.

### 2.2. Key ID, client ID và tenant ID không đồng nhất

Một client có thể giữ nhiều keys trong rotation. Một principal có thể được delegated grant vào nhiều tenants. Prefix `tenant-a` trong key ID không phải server authorization. Tenant/resource access phải dựa trên **trusted grants, ownership, action policy** sau authentication.

## 3. Tình huống thực tế

Registry ví dụ:

~~~text
Client A:
  partner-a-k2  RETIRING đến T, secret KA2
  partner-a-k3  ACTIVE, secret KA3

Client B:
  partner-b-k1  ACTIVE, secret KB1

Không có record:
  partner-a-k99
~~~

HTTP request:

~~~http
POST /v1/orders?dryRun=false HTTP/1.1
Host: orders.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1800000030
X-Nonce: 0123456789abcdef0123456789abcdef
X-Signature: <43-char-Base64URL-HMAC-SHA256-tag>

{"orderId":"O42"}
~~~

Các sự cố có bề ngoài tương tự nhưng ý nghĩa khác nhau:

- Không có `X-Key-Id` → `KEY_ID_MISSING`.
- Key ID chứa whitespace, newline, ký tự không hợp lệ → `KEY_ID_MALFORMED`.
- Hai occurrences `X-Key-Id` → `KEY_ID_AMBIGUOUS`.
- `partner-a-k99` đúng grammar nhưng registry xác nhận không tồn tại → `KEY_ID_UNKNOWN`.
- Khai k3 nhưng HMAC bằng secret k2 hoặc B1 → `HMAC_TAG_MISMATCH`; **không được dò lại key**.
- k2 hết cửa sổ verify hoặc k3 REVOKED → `KEY_NOT_ALLOWED` dù tag có thể đúng.
- Registry timeout → `KEY_LOOKUP_UNAVAILABLE`; không coi là unknown hoặc success.
- k3 đúng nhưng key chỉ cho audience khác → `KEY_WRONG_AUDIENCE`.
- k3/MAC đúng nhưng tenant không được cấp quyền → `AUTHZ_TENANT_DENIED`, **không phải lỗi key ID**.

### 3.1. Sơ đồ xử lý

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Strict parse key ID and signature fields]
    B --> C{One valid key ID?}
    C -- No --> X[Reject]
    C -- Yes --> D[Registry exact lookup]
    D --> E{Found and allowed?}
    E -- No or unavailable --> X
    E -- Yes --> F[Canonicalize signed request]
    F --> G[Compute expected HMAC using selected secret]
    G --> H{Full tag match?}
    H -- No --> X
    H -- Yes --> I[Validate signed timestamp]
    I --> J[Atomic claim signed nonce]
    J --> K{NEW and reliable?}
    K -- No --> X
    K -- Yes --> L[Create trusted principal]
    L --> M[Authorize action, tenant, resource]
    M --> N[Business handler only if allowed]
~~~

Thứ tự chi tiết có thể thay đổi để giảm chi phí, nhưng **không** được tạo authenticated principal hoặc claim nonce từ request có MAC sai.

## 4. Taxonomy sai key ID

| Internal outcome | Điều kiện | Phân lớp | Tạo authenticated principal? |
| --- | --- | --- | --- |
| `KEY_ID_MISSING` | Thiếu field bắt buộc | Parsing | Không |
| `KEY_ID_MALFORMED` | Grammar, encoding, length sai | Parsing | Không |
| `KEY_ID_AMBIGUOUS` | Duplicates/combined fields | HTTP/gateway | Không |
| `KEY_ID_UNKNOWN` | Exact lookup xác nhận missing | Identification | Không |
| `KEY_ID_LOOKUP_UNAVAILABLE` | Timeout/partition/KMS unavailable | Infrastructure | Không |
| `KEY_ID_RECORD_INCONSISTENT` | Record trả ID khác requested | Integrity/infrastructure | Không |
| `KEY_NOT_ALLOWED` | Disabled, revoked, expired | Credential policy | Không |
| `KEY_WRONG_AUDIENCE` | API khác intended use | Credential policy | Không |
| `HMAC_TAG_MALFORMED` | Encoding/full length không hợp lệ | Authentication | Không |
| `HMAC_TAG_MISMATCH` | Tag sai dưới exact secret | Authentication | Không |
| `HMAC_TIMESTAMP_STALE` | Signed timestamp ngoài window | Freshness | Không |
| `HMAC_NONCE_REPLAY` | Nonce đã claim | Replay | Không |
| `HMAC_NONCE_UNAVAILABLE` | Store không quyết định được | Infrastructure | Không |
| `AUTHZ_TENANT_DENIED` | Principal đúng nhưng không có grant | Authorization | Có thể authenticated, nhưng deny action |

### 4.1. Missing, malformed, unknown và unavailable

**Missing** = không có selector. **Malformed** = có selector nhưng cú pháp ngoài protocol. **Unknown** = selector đúng grammar, trusted lookup xác nhận không có record. **Unavailable** = không thể kết luận vì dependency lỗi; không được đổi outage thành “không tồn tại” hoặc fallback success.

### 4.2. Sai key ID có thể là correct ID nhưng policy không cho dùng

Một ID có record vẫn có thể REVOKED, NOT_YET_VALID, expired, wrong audience hoặc không được phục vụ route này. Public error thường cần **gộp với unknown/bad signature** để giảm khả năng dò tồn tại và key lifecycle.

### 4.3. HMAC mismatch không có nghĩa server phải tìm key khác

Khi client khai `partner-a-k3`, verifier **chỉ dùng KA3**. Tag được ký bằng KA2/KB1 làm MAC mismatch. “Try all secrets until one matches” có thể cho B giả danh A, phá rotation/revocation và tạo key-enumeration timing oracles.

## 5. Grammar key ID: một hợp đồng cố định

Ví dụ HMAC-HTTP-V1:

~~~text
keyId grammar  = [A-Za-z0-9][A-Za-z0-9._-]{0,63}
encoding       = US-ASCII
length         = 1..64 characters
case           = case-sensitive
whitespace     = forbidden
aliases        = forbidden
normalization  = none
~~~

| Input | Parser V1 | Ý nghĩa |
| --- | --- | --- |
| `partner-a-k3` | Hợp lệ | Tra exact ID |
| `Partner-A-K3` | Hợp lệ | **Là ID khác** vì case-sensitive |
| `a` | Hợp lệ | Một ký tự |
| `.partner-k3` | Reject | Ký tự đầu không phù hợp |
| ` partner-a-k3` | Reject | Leading whitespace |
| `partner-a-k3 ` | Reject | Trailing whitespace |
| `partner a k3` | Reject | Embedded whitespace |
| `partner/a-k3` | Reject | Slash ngoài grammar |
| `partner%2Da-k3` | Reject | Không hỗ trợ percent-encoded ID |
| `partnér-k3` | Reject | Non-ASCII |
| Rỗng | Reject | Thiếu value |
| 65 ký tự ASCII | Reject | Quá dài |
| Một value có CRLF/control bytes | Reject | HTTP injection/malformed |
| `partner-a-k3,partner-b-k1` | Reject | Combined field ngoài V1 |
| Hai `X-Key-Id` fields | Reject | Ambiguous input |

### 5.1. Không tự trim/lowercase/URL-decode

~~~java
// SAI nếu protocol V1 không quy định normalization.
String id = rawId.trim().toLowerCase();
return registry.find(id);
~~~

Việc sửa input thành một ID khác có thể tạo alias không rõ ràng, gây lệch signer/verifier hoặc khác biệt DB collation. Nên reject rồi yêu cầu caller sửa theo contract.

### 5.2. HTTP field names khác key ID values

`X-Key-Id` và `x-key-id` là **cùng HTTP field name** vì names case-insensitive. Nhưng `partner-a-k3` và `Partner-A-K3` là **hai key IDs khác nhau** theo V1. Nếu caller gửi cả hai occurrences, không được “chọn cái đầu” hoặc “ưu tiên cái có chữ ký đúng”.

### 5.3. Unicode, collations và opaque IDs

Giới hạn ASCII tránh Unicode normalization/confusable issues. Nếu muốn Unicode key IDs, phải định nghĩa byte encoding, normalization, length/collation và cách canonical signing. Nếu ID mang marker như `client-a-k3`, prefix chỉ có ích vận hành; trusted registry vẫn phải trả principal/tenant/audience/secret/status, không suy permission từ chuỗi ID.

## 6. Key ID phải được ràng buộc trong canonical request

Một sai lầm cơ bản là ký method/path/body nhưng **không ký key ID**. Khi đó attacker có thể thay selector mà không trực tiếp thay các bytes HMAC input. Nếu nhiều records lỡ chia sẻ secret hoặc có một fallback key, điều này tăng nguy cơ **key substitution/identity confusion**.

Hợp đồng minh họa **HMAC-HTTP-V1** (protocol nội bộ của bài, **không phải một chuẩn RFC phổ quát**) dùng:

~~~text
HMAC-HTTP-V1
POST
/v1/orders
dryRun=false
audience:orders-api
host:orders.example.test
content-type:application/json
key-id:partner-a-k3
timestamp:1800000030
nonce:0123456789abcdef0123456789abcdef
body-sha256:<lowercase-hex-of-SHA256-raw-body>
~~~

Quy tắc:

- Ghép các dòng bằng **LF**, encode UTF-8, **không** thêm LF cuối.
- Method, raw/canonical path, canonical query và signed headers dùng chính **một contract versioned**.
- `key-id`, `timestamp`, `nonce` và audience đều nằm trong signed bytes.
- Server tự tính body digest từ **raw bytes thực nhận**, không tin `X-Body-Sha256` do caller khai.
- Key ID trong input ký bằng **chính giá trị đã parse hợp lệ**; không trim hoặc lowercase.
- Tag đầu ra là full 32-byte HMAC-SHA256 encode Base64URL **không padding**, dài 43 ký tự.
- Header `X-Signature` là tag đầu ra, **không nằm trong chính HMAC input**.
- Secret được chọn **theo exact key ID từ trusted registry**; algorithm và audience phải khớp policy server, không do client hạ cấp.
- Nếu gateway rewrite signed URI/headers, signing boundary phải cố định và được kiểm bằng fixtures; không “thử các variants” để ép HMAC match.

### 6.1. Đổi key ID gây hậu quả gì?

Giả sử client ký bằng KA3:

~~~text
key-id:partner-a-k3
HMAC(KA3, canonical-with-A3) -> tag-A3
~~~

Attacker sửa header:

~~~text
key-id:partner-b-k1
presented signature: tag-A3 (unchanged)
~~~

Server lookup B1, lấy KB1, dựng canonical **chứa B1**, tính expected tag-B1. Tag không khớp; **reject**. Nếu hai clients bị cấu hình chung secret ngoài ý muốn, việc ký key ID vẫn giúp bảo vệ selector integrity, nhưng **không làm chung secret trở thành thực hành tốt**: phải phân phối secret material độc lập.

### 6.2. Không lấy key ID từ hai nơi rồi chọn theo ý thích

Một thiết kế có thể đặt key ID trong `Authorization: HMAC ...` hoặc `X-Key-Id`. Nếu contract chỉ cho **một nguồn**, tuyệt đối không nhận hai nguồn rồi ưu tiên tùy parser.

Ví dụ:

~~~http
Authorization: HMAC keyId="partner-a-k3",signature="..."
X-Key-Id: partner-b-k1
~~~

Nếu protocol V1 chỉ dùng `X-Key-Id` thì có thể reject `Authorization` authentication scheme không mong đợi trên cùng HMAC-required endpoint. Nếu protocol dùng `Authorization` thì định nghĩa grammar/key-id binding và reject conflict/duplicates ở mọi tầng. **Không** thử scheme/key nào verify được trước.

### 6.3. Signed key ID không phải quyền

HMAC đúng trên `key-id:partner-a-k3` chỉ khẳng định request do bên biết secret A3 tạo; grant đến `tenant-B` hoặc `orders:delete` vẫn phải lấy từ trusted policy. Các field `X-Role` hoặc `X-Tenant-Id` dù được ký vẫn là **claim do caller tạo**, không tự trở thành role/tenant entitlement.

## 7. HTTP error semantics: public contract và internal reason

Phản hồi cho sai key ID phải cân bằng: client nhận được lỗi đủ để sửa tích hợp, nhưng attacker không thể dùng response để **dò credential registry**.

### 7.1. Những status thường gặp

| HTTP status | Ý nghĩa điển hình | Gợi ý với HMAC |
| --- | --- | --- |
| `400 Bad Request` | Syntax/framing/parameter invalid | Header malformed, duplicate/ambiguous request theo public contract |
| `401 Unauthorized` | Chưa có authentication credentials hợp lệ cho resource | Missing/unknown/key revoked/MAC mismatch trên HMAC-protected API |
| `403 Forbidden` | Server hiểu request nhưng **không cho phép** hành động | Authenticated principal thiếu scope, tenant grant hoặc object authorization |
| `404 Not Found` | Resource không có hoặc chủ đích không tiết lộ | Có thể dùng sau authorization theo policy, không dùng để tiết lộ registry |
| `413 Content Too Large` | Payload vượt giới hạn | Signed body vượt bound, reject trước expensive HMAC |
| `429 Too Many Requests` | Rate limiting | Flood malformed/unknown key IDs hoặc abuse theo trusted quotas |
| `503 Service Unavailable` | Dependency/security authority outage | Registry/KMS/replay authority unavailable, fail closed theo contract |
| `500 Internal Server Error` | Lỗi hệ thống không dự kiến | Crypto provider/config/invariant failure; không silently accept |

Không có một ánh xạ bắt buộc duy nhất cho mọi custom HMAC protocol. Ví dụ, malformed authentication metadata có thể được phân loại `400` hoặc gộp `401` để giảm oracle; hãy **chọn và tài liệu hóa một contract**. Quan trọng hơn status chính xác là không xử lý business khi key ID không đáng tin.

### 7.2. Lưu ý `401` và `WWW-Authenticate`

Theo HTTP authentication semantics, response **401** phải chứa ít nhất một **`WWW-Authenticate` challenge áp dụng cho resource**. Nếu xây một HTTP authentication scheme `HMAC` riêng, cần định nghĩa challenge grammar và behavior; đây **không** tự động là scheme tiêu chuẩn chung.

Ví dụ minh họa cho **một custom HMAC scheme đã được ứng dụng định nghĩa**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: HMAC realm="orders-api"
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Authentication failed","status":401,
 "code":"AUTHENTICATION_FAILED","traceId":"srv-7f22"}
~~~

Challenge không gửi secret, expected signature, key state hay danh sách key IDs hợp lệ. Nếu API dùng custom `X-Key-Id/X-Signature` chứ không hỗ trợ một HTTP auth-scheme hoàn chỉnh, đội ngũ cần quyết định và tài liệu hóa cách áp dụng `401`/challenge cho contract, không tự suy rằng thêm `HMAC` vào header đã tạo một standard.

### 7.3. Một public response chung cho credential failures

Một public contract hữu ích:

~~~json
{
  "type": "about:blank",
  "title": "Authentication failed",
  "status": 401,
  "code": "AUTHENTICATION_FAILED",
  "traceId": "srv-7f22"
}
~~~

Với **unknown key ID**, **key revoked**, **wrong secret**, **bad signature**, có thể dùng cùng public shape để tránh key-existence oracle. Internal metrics vẫn ghi reason codes chính xác từ server-side verifier.

### 7.4. Đừng tiết lộ registry state

**Sai:**

~~~json
{
  "error": "KEY_EXISTS_BUT_REVOKED",
  "clientId": "partner-A",
  "keyId": "partner-a-k3",
  "expectedSignature": "abc...",
  "secretRef": "kms/production/partnerA"
}
~~~

Nó tiết lộ partner/key existence, lifecycle, secret storage topology và expected MAC. Đúng hơn là dùng một **server-generated trace ID**, cung cấp hướng debug qua kênh đã xác thực (developer console/support portal) khi đối tác chứng minh quyền quản lý credential đó.

### 7.5. `403` không thay `401` khi chưa authenticated

Nếu caller gửi unknown key ID và wrong MAC, chưa có trusted principal. Không trả `403 Missing scope orders:write` dựa vào `X-Role` hoặc key-ID prefix, vì điều đó ngầm coi caller đã authenticated.

Ngược lại, key ID đúng + HMAC/freshness/replay pass nhưng principal không có quyền `tenant-B` là **authorization**, có thể trả `403`. Tuy nhiên, resource non-disclosure policy có thể dùng `404` để ẩn resource existence.

### 7.6. `503` không phải `401` giả khi registry outage

Một timeout không chứng minh key ID không tồn tại. Hệ thống phải **fail closed**, nhưng observability và retry semantics cần phân biệt dependency failure với bad credentials. Có thể trả `503`/`Retry-After` với generic body, rate limits và idempotent retry contract; không retry vô hạn một signed request với nonce cũ mà kỳ vọng chắc chắn thành công.

## 8. Key-existence oracle và timing side-channel

Một attacker có thể thử hàng nghìn IDs:

~~~text
partner-a-k1 -> response A
partner-a-k2 -> response B
partner-a-k3 -> response C
~~~

Nếu server trả `KEY_NOT_FOUND` cho unknown, `BAD_SIGNATURE` cho known, `REVOKED` cho disabled, attacker có thể vẽ inventory key IDs và lifecycle dù không biết secret.

### 8.1. Oracle qua status/message/header

Dấu hiệu:

- Unknown ID → 404; known ID/wrong tag → 401.
- Known ID → public error chứa principal/client.
- Revoked ID → thêm `X-Key-Revoked-At` hay `reason: key-expired`.
- Known ID → cookie/header khác unknown ID.
- Registry miss → error body ngắn hơn và redirect khác.

**Giảm rủi ro:** dùng public status/body/challenge tương tự với các trường hợp credential không hợp lệ, redacted internal logging và secured troubleshooting channels.

### 8.2. Oracle qua thời gian

Unknown key có thể reject ngay sau cache miss; known key phải load secret và tính HMAC, khiến latency khác nhau. `MessageDigest.isEqual` là primitive so tag tốt hơn early-exit loop, nhưng **không làm toàn HTTP verifier constant-time** vì parsing, lookup, network, JIT/GC, key cache và replay store.

Một số hệ thống thực hiện **dummy HMAC work với một secret không dùng để cấp quyền** trên unknown IDs nhằm làm bớt chênh lệch timing. Nếu áp dụng, phải bảo đảm **không bao giờ accept unknown key dù dummy tag trùng**, không dùng dummy secret như fallback, và không khẳng định một phép đo đơn giản đã loại bỏ timing oracle. Cần threat modeling, statistical testing và rate limiting.

### 8.3. Không tạo unbounded cache/metrics state theo raw key ID

Attacker có thể tạo hàng triệu key IDs ngẫu nhiên đúng grammar gây registry cache misses, negative-cache growth hoặc Prometheus label explosion.

Giảm rủi ro:
- Giới hạn header length và total request header bytes tại ingress.
- Pre-auth coarse rate limiting dựa trên trusted network/connection/edge identity.
- Bounded negative caching với TTL ngắn và eviction policies; không tạo entry vô hạn theo attacker input.
- Cẩn thận với negative cache khi **onboarding key mới**; cần invalidation/TTL contract rõ.
- Không dùng unknown key ID raw làm một metrics label riêng cho mỗi giá trị.
- Authenticated per-client quotas chỉ dùng **trusted principal** sau MAC, không dựa vào key ID do caller khai.
- Giới hạn concurrent registry/KMS lookups, timeouts và backpressure.

### 8.4. Key ID entropy không thay HMAC

Opaque/random key IDs có thể làm enumeration khó hơn so với `partner-a-k3`, nhưng nếu attacker có ID hợp lệ mà không có secret, HMAC vẫn phải bảo vệ. Nếu secret đã lộ, key ID có khó đoán cũng không phải biện pháp revoke; cần chấm dứt credential và rotate.

## 9. Proxy/gateway: lỗi key ID có thể xuất phát từ HTTP ambiguity

Một gateway có thể nhận:

~~~http
X-Key-Id: partner-a-k3
x-key-id: partner-b-k1
~~~

Một downstream proxy/parser có thể giữ cả hai values, merge thành một value hoặc lấy đầu/cuối. Nếu gateway chọn A3 còn application chọn B1, error sẽ có vẻ là “client ký sai key” trong khi lỗi thực là **request interpretation mismatch**. Đây là security boundary nghiêm trọng, không nên “sửa” bằng cách thử cả A3/B1.

### 9.1. Đúng một field occurrence

Contract V1 cần reject:
- Hai `X-Key-Id` fields dù khác case hay cùng value.
- Duplicate `Authorization` nếu dùng HMAC auth scheme.
- Conflict giữa `X-Key-Id` và selector trong Authorization nếu có cả hai.
- Comma-joined value nếu field không hỗ trợ combined-value grammar.
- CRLF/control bytes, vượt limits, malformed framing.
- Request-target/Host/auth fields có ambiguity qua HTTP/1.1–HTTP/2 conversion.

### 9.2. Ứng dụng không phục hồi raw wire evidence đã bị gateway mất

`HttpServletRequest.getHeaders("X-Key-Id")` và WebFlux `getHeaders().get("X-Key-Id")` chỉ thấy HTTP representation **sau** các middleware/transport adapters. Nếu gateway đã drop second field, backend không còn đủ dữ liệu để nhận ra duplicate. Test cần gồm **raw HTTP ingress tests**, không chỉ MockMvc/WebTestClient in-process.

### 9.3. Không tin `X-Original-*` hoặc `X-Authenticated-*` từ Internet

Gateway phải strip/overwrite headers nhạy cảm như `X-Authenticated-Client`, `X-Original-URI` hoặc `X-Forwarded-Host` và bảo vệ backend channel. Nếu gateway tự verify HMAC rồi truyền trusted principal, phải dùng mTLS/integrity-protected context, không cho direct backend access bypass.

### 9.4. URI rewrite có thể biến key ID đúng thành “bad signature”

Client ký public `/public/v1/orders`, backend verifier nhận `/v1/orders` sau prefix rewrite. Registry lookup A3 có thể đúng nhưng canonical mismatch gây `HMAC_TAG_MISMATCH`. Đừng đổi key ID hoặc thử secrets khác để giải quyết; sửa **signing boundary/versioned URI contract** và test gateway e2e.

## 10. Key rotation, revocation và sai key ID

Một credential lifecycle minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONED
    PROVISIONED --> ACTIVE: activate
    ACTIVE --> RETIRING: planned rotation
    RETIRING --> REVOKED: revoke/expire verify window
    ACTIVE --> REVOKED: emergency compromise
    ACTIVE --> DISABLED: administrative hold
    DISABLED --> REVOKED: final revoke
~~~

### 10.1. Planned rotation

~~~text
partner-a-k2 = RETIRING, secret KA2, verifyUntil T
partner-a-k3 = ACTIVE, secret KA3
~~~

Client dùng k2 + KA2 trước T có thể verify nếu policy overlap cho phép. Client dùng k3 + KA3 verify theo status ACTIVE. Nhưng:

- Khai k3 + ký KA2 → **BAD SIGNATURE**, không fallback k2.
- Khai k2 sau T → **KEY NOT ALLOWED**, không thử KA3.
- Khai unknown k4 + ký KA3 → **UNKNOWN KEY**, không đoán newest.
- Thay key ID trong request sau khi tính MAC → signed bytes thay đổi, phải ký lại từ đầu.

### 10.2. Emergency revocation

Khi key k3 bị compromise, attacker có thể tạo timestamp/nonce **mới** và HMAC tag hợp lệ. Replay protection không chặn được việc attacker có secret ký fresh request. Revoke k3 tại trusted authority, propagate tới mọi verifier và cấp k4 với **secret material mới độc lập**.

Không accept k3 chỉ vì `X-Timestamp` khai thời điểm trước `revokedAt`: caller có secret có thể ký lùi thời gian trong freshness window. Key status quyết định theo trusted server policy.

### 10.3. Tránh tái sử dụng key ID

Đổi secret bytes nhưng giữ nguyên k3 có thể làm cache verifiers không đồng bộ và khó audit. Ưu tiên phiên bản key ID mới `k4`, phân phối secret an toàn và có rollback/overlap policy rõ. Khi k3 bị revoke, không “tạm gán k3 trỏ sang secret k4” để giúp client cũ.

### 10.4. Multi-client / multi-tenant isolation

Một principal P có thể phục vụ tenants A/B. Revoke grant P→A là authorization change, **không nhất thiết** revoke key P7 hoặc quyền P→B. Revoke toàn tenant A khiến request HMAC hợp lệ của P trên A vẫn phải deny. Key ID selector không cấp quyền tenant hoặc action.

## 11. Thiết kế Java 17: internal outcome và HTTP adapter

Để minh họa, ta chia thành các lớp **Java 17** độc lập với web framework:

- `KeyIdInputV1`: đọc một field occurrence và áp strict grammar.
- `HmacCanonicalV1`: dựng canonical bytes từ parsed request theo V1.
- `CredentialRegistryV1`: exact key lookup có typed absence/outage.
- `HmacVerifierV1`: key policy, full MAC, timestamp, nonce và authenticated principal.
- `PublicErrorMapperV1`: map **internal failure** sang public response chung.
- `Spring Security adapter`: đặt Authentication chỉ sau verifier success, không tự dùng header làm principal.

Mỗi public class/record/enum/interface nên nằm trong source file tương ứng. Ví dụ có tính **educational**, dùng source bytes test-only; khi dùng production phải có secret manager, logging policy, size limits, HTTP ingress, dynamic key rotation và shared replay authority phù hợp.

### 11.1. Typed failure codes

~~~java
public enum AuthFailureV1 {
    KEY_ID_MISSING,
    KEY_ID_MALFORMED,
    KEY_ID_AMBIGUOUS,
    KEY_ID_UNKNOWN,
    KEY_ID_NOT_ALLOWED,
    KEY_ID_WRONG_AUDIENCE,
    KEY_ID_RECORD_INCONSISTENT,
    TAG_MALFORMED,
    TAG_MISMATCH,
    TIMESTAMP_INVALID,
    NONCE_REPLAY,
    DEPENDENCY_UNAVAILABLE,
    CONTRACT_VIOLATION
}
~~~

~~~java
public final class AuthRejectedV1 extends RuntimeException {
    private final AuthFailureV1 code;

    public AuthRejectedV1(AuthFailureV1 code) {
        super("HMAC authentication failed");
        this.code = code;
    }

    public AuthFailureV1 code() {
        return code;
    }
}
~~~

**Không** tự động serialize `code` cho unauthenticated public callers. Internal reason code giúp test, alert và incident triage; public body thường chuẩn hóa chung. Exceptions ở đây dùng cho minh họa một đơn vị xử lý đồng bộ; trong WebFlux có thể map sang `Mono.error` với cùng semantics.

### 11.2. Parse header có đúng một occurrence

Ví dụ một adapter **đã nhận được danh sách header fields mà HTTP stack còn giữ**:

~~~java
public record HttpFieldV1(String name, String value) {}
~~~

~~~java
import java.util.List;
import java.util.regex.Pattern;

public final class KeyIdInputV1 {
    private static final Pattern KEY_ID = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    private KeyIdInputV1() {}

    public static String requireExact(List<HttpFieldV1> fields) {
        if (fields == null) {
            throw new AuthRejectedV1(
                    AuthFailureV1.KEY_ID_MISSING);
        }

        String seen = null;
        int occurrences = 0;

        for (HttpFieldV1 field : fields) {
            if (field == null || field.name() == null) {
                throw new AuthRejectedV1(
                        AuthFailureV1.KEY_ID_MALFORMED);
            }

            // HTTP field name case-insensitive.
            if ("X-Key-Id".equalsIgnoreCase(field.name())) {
                occurrences++;
                if (occurrences > 1) {
                    throw new AuthRejectedV1(
                            AuthFailureV1.KEY_ID_AMBIGUOUS);
                }
                seen = field.value();
            }
        }

        if (occurrences == 0) {
            throw new AuthRejectedV1(
                    AuthFailureV1.KEY_ID_MISSING);
        }

        if (seen == null || !KEY_ID.matcher(seen).matches()) {
            // No trim, lower-case, URL decode or alias resolution.
            throw new AuthRejectedV1(
                    AuthFailureV1.KEY_ID_MALFORMED);
        }

        return seen;
    }
}
~~~

Nếu proxy đã merge hai headers thành một value, adapter Java **không thể khôi phục số occurrences trên wire**. `KeyIdInputV1` không thay ingress strict duplicate validation, header-size limits hoặc request-smuggling protections. Giá trị như `partner-a-k3,partner-b-k1` bị regex reject theo contract.

### 11.3. Case sensitivity là yêu cầu của registry, không chỉ parser

DB có thể dùng collation không phân biệt hoa/thường; lookup `Partner-A-K3` vô tình trả record `partner-a-k3`. Sau khi registry trả record, verifier vẫn phải **so exact Java string**:

~~~java
if (!record.keyId().equals(presentedKeyId)) {
    throw new AuthRejectedV1(
            AuthFailureV1.KEY_ID_RECORD_INCONSISTENT);
}
~~~

Trong production, đặt unique key/collation phù hợp (binary/case-sensitive khi cần), chống alias và theo dõi duplicate records. Đừng sửa bằng cách `equalsIgnoreCase` vì như vậy thay đổi protocol.

## 12. Java 17: credential record và exact lookup

Một trusted credential record:

~~~java
public enum KeyStatusV1 {
    PROVISIONED, ACTIVE, RETIRING, DISABLED, REVOKED
}
~~~

~~~java
import java.time.Instant;
import java.util.Objects;

public record HmacCredentialV1(
        String keyId,
        String clientId,
        String principalId,
        String tenantId,
        String audience,
        String algorithm,
        KeyStatusV1 status,
        Instant notBefore,
        Instant notAfter,
        byte[] secret) {

    public HmacCredentialV1 {
        Objects.requireNonNull(keyId);
        Objects.requireNonNull(clientId);
        Objects.requireNonNull(principalId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(audience);
        Objects.requireNonNull(algorithm);
        Objects.requireNonNull(status);
        Objects.requireNonNull(notBefore);
        Objects.requireNonNull(notAfter);
        Objects.requireNonNull(secret);
        secret = secret.clone();
    }

    @Override
    public byte[] secret() {
        return secret.clone();
    }
}
~~~

**Cảnh báo:** Java record auto-generated `toString()` cho `byte[]` thường không in raw secret bytes nhưng có thể để lộ metadata; không dựa vào điều đó làm log hygiene. Production credential/secret model nên tránh in/serialize secrets, có ACL/KMS/ref lifecycle và có thể dùng secret handle thay raw byte[].

### 12.1. Exact lookup và unavailable

~~~java
import java.util.Optional;

public interface CredentialRegistryV1 {
    /**
     * Empty = authoritative "no such exact ID".
     * Dependency outage must THROW, not return empty.
     */
    Optional<HmacCredentialV1> findExact(String keyId);
}
~~~

~~~java
public final class RegistryUnavailableV1
        extends RuntimeException {

    public RegistryUnavailableV1(String message) {
        super(message);
    }
}
~~~

**Registry lookup timeout không phải unknown key.** Một API ổn định cần phân loại missing/outage cho alerting, retry handling và cache policy; cả hai đều không tạo authenticated principal.

### 12.2. Positive/negative caches và revoke

- Positive cache giúp giảm registry latency nhưng có thể chấp nhận key REVOKED từ stale ACTIVE snapshot.
- Negative cache giúp giảm unknown-key flood nhưng có thể trì hoãn onboarding key mới.
- Cache cần bounded memory, TTL/lease, version/revision, invalidation và **revocation effectiveness guarantee**.
- Một loader trả ACTIVE version cũ không được ghi đè REVOKED version mới trong cache.
- Với emergency revoke mạnh, không accept vô hạn dựa trên stale cache khi authoritative registry unreachable.

### 12.3. Một record phải có đúng algorithm và audience

Không tin `X-Algorithm: none` hoặc `X-Audience: admin-api` để chọn verifier policy. Record server-side quyết định `HmacSHA256` và `orders-api`. Key ID đúng nhưng audience không phù hợp vẫn là **credential policy failure**, không phải request đã authenticated.

## 13. Java 17: canonical request và signature codec

Để giảm số biến khi học “sai key ID”, contract V1 chỉ minh họa:

~~~text
method       = POST
rawPath      = /v1/orders
rawQuery     = dryRun=false
host         = orders.example.test
contentType  = application/json
body         = <= 64 KiB raw bytes
algorithm    = HmacSHA256 fixed by server
keyId        = exact V1 grammar
nonce        = 32 lowercase hexadecimal characters
timestamp    = non-negative epoch seconds
~~~

Trong production, method/URI/query có thể phong phú hơn nhưng **phải có một canonicalization spec nhất quán** giữa signer/verifier/gateway.

### 13.1. Parsed request value object

~~~java
import java.util.Objects;

public record SignedRequestV1(
        String method,
        String rawPath,
        String rawQuery,
        String host,
        String contentType,
        String keyId,
        long timestampSeconds,
        String nonceHex,
        String presentedTagB64Url,
        byte[] rawBody) {

    public SignedRequestV1 {
        Objects.requireNonNull(method);
        Objects.requireNonNull(rawPath);
        Objects.requireNonNull(rawQuery);
        Objects.requireNonNull(host);
        Objects.requireNonNull(contentType);
        Objects.requireNonNull(keyId);
        Objects.requireNonNull(nonceHex);
        Objects.requireNonNull(presentedTagB64Url);
        Objects.requireNonNull(rawBody);
        rawBody = rawBody.clone();
    }

    @Override
    public byte[] rawBody() {
        return rawBody.clone();
    }
}
~~~

`SignedRequestV1` là **input data**, chưa phải principal đã authenticated. Trong real HTTP adapter, đừng cho client tự cấp canonical bytes thay vì các components server thực thấy.

### 13.2. Canonicalizer đúng contract V1

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Pattern;

public final class CanonicalHmacV1 {
    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");

    private CanonicalHmacV1() {}

    public static byte[] bytes(SignedRequestV1 request)
            throws NoSuchAlgorithmException {

        if (!"POST".equals(request.method())
                || !"/v1/orders".equals(request.rawPath())
                || !"dryRun=false".equals(request.rawQuery())
                || !"orders.example.test".equals(request.host())
                || !"application/json".equals(
                        request.contentType())
                || request.timestampSeconds() < 0
                || !NONCE.matcher(request.nonceHex()).matches()
                || request.rawBody().length > 65_536) {

            throw new AuthRejectedV1(
                    AuthFailureV1.CONTRACT_VIOLATION);
        }

        byte[] bodyHash = MessageDigest
                .getInstance("SHA-256")
                .digest(request.rawBody());

        String canonical = String.join("\n",
                "HMAC-HTTP-V1",
                "POST",
                "/v1/orders",
                "dryRun=false",
                "audience:orders-api",
                "host:orders.example.test",
                "content-type:application/json",
                "key-id:" + request.keyId(),
                "timestamp:" + request.timestampSeconds(),
                "nonce:" + request.nonceHex(),
                "body-sha256:" + HexFormat.of()
                        .formatHex(bodyHash));

        return canonical.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Để tránh parser/verifier nhận key ID sai grammar khi gọi trực tiếp service (không qua HTTP adapter), verifier ở mục kế tiếp sẽ gọi **validator của chính key ID** trước khi lookup. Trong production nên có type đại diện `ValidatedKeyId` được tạo duy nhất qua strict parser.

### 13.3. Signature strict Base64URL 43 ký tự

~~~java
import java.util.Base64;
import java.util.regex.Pattern;

public final class SignatureCodecV1 {
    private static final Pattern TAG =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private SignatureCodecV1() {}

    public static byte[] decode(String encoded) {
        if (encoded == null || !TAG.matcher(encoded).matches()) {
            throw new AuthRejectedV1(
                    AuthFailureV1.TAG_MALFORMED);
        }

        final byte[] result;
        try {
            result = Base64.getUrlDecoder().decode(encoded);
        } catch (IllegalArgumentException invalid) {
            throw new AuthRejectedV1(
                    AuthFailureV1.TAG_MALFORMED);
        }

        if (result.length != 32
                || !Base64.getUrlEncoder()
                        .withoutPadding()
                        .encodeToString(result)
                        .equals(encoded)) {
            throw new AuthRejectedV1(
                    AuthFailureV1.TAG_MALFORMED);
        }

        return result;
    }
}
~~~

Strict encoding chống các representation khác nhau của cùng tag, rejects padding/invalid characters/truncation. Với `HmacSHA256`, expected output luôn **32 bytes**; so prefix hoặc accept 8/16-byte tags không được phép trong contract này.

## 14. Java 17: full HMAC và replay authority

### 14.1. MAC primitive

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSha256V1 {
    private HmacSha256V1() {}

    public static byte[] expected(
            byte[] trustedSecret, byte[] canonical)
            throws GeneralSecurityException {

        if (trustedSecret == null || trustedSecret.length == 0
                || canonical == null) {
            throw new IllegalArgumentException("Invalid HMAC input");
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(trustedSecret, "HmacSHA256"));
        return mac.doFinal(canonical);
    }

    public static boolean sameFullTag(
            byte[] expected32, byte[] presented32) {

        return expected32 != null && expected32.length == 32
                && presented32 != null && presented32.length == 32
                && MessageDigest.isEqual(expected32, presented32);
    }
}
~~~

`MessageDigest.isEqual` là lựa chọn thích hợp để so MAC bytes trong Java, thay vì early-exit loop tự viết. Nó **không chứng minh mọi hoạt động lookup/key policy/HTTP pipeline là constant-time**.

### 14.2. Nonce store contract

~~~java
import java.time.Duration;

public interface ReplayStoreV1 {
    enum Claim {
        NEW,
        REPLAY,
        UNKNOWN
    }

    Claim claimOnce(String key, Duration ttl);
}
~~~

`claimOnce` phải là **atomic insert-if-absent** trong shared authority. Redis có thể dùng `SET key value NX EX ttl`, nhưng phải đánh giá primary failover/replication/durability theo security guarantee. Một local `ConcurrentHashMap` chỉ thích hợp unit tests trong một JVM, không bảo vệ replay giữa pods.

### 14.3. Namespace nonce không lấy từ raw caller tenant header

~~~text
hmac-replay:v1:orders-api:partner-a-k3:<signed-nonce>
~~~

Scope theo protocol version, audience, **exact selected credential ID** và nonce đã ký. Không dùng `X-Tenant-Id` caller chưa authenticated làm namespace, vì có thể thay tenant để tạo key khác. Nếu nhiều principals cùng dùng shared secret, đó là thiết kế isolation cần xem lại, không phải lý do bỏ nonce.

### 14.4. TTL bao phủ freshness window

Nếu max past age `A=300s`, future skew `F=30s` và margin `M=30s`, TTL replay store tính từ claim cần bound bảo thủ:

\[
TTL_{\text{nonce}} \ge A+F+M = 360\text{ s}.
\]

Không giảm TTL vì bộ nhớ thiếu rồi vô tình cho request cùng nonce được accept lại trước khi signed timestamp hết hiệu lực.

## 15. Java 17: verifier không fallback khi key ID sai

Đây là service minh họa theo contract ở mục 13–14. Nó **không** làm thay HTTP parser/gateway, nhưng có một lớp kiểm tra defensively cho key ID ngay cả khi caller gọi service trực tiếp.

### 15.1. Trusted result chỉ tồn tại khi thành công

~~~java
public record VerifiedPrincipalV1(
        String principalId,
        String clientId,
        String tenantId,
        String credentialKeyId,
        String audience) {}
~~~

Đừng nhận một `VerifiedPrincipalV1` được deserialized từ HTTP request làm Authentication. Chỉ trusted verifier được tạo result sau full HMAC, freshness và nonce.

### 15.2. HmacRequestVerifierV1

~~~java
import java.security.GeneralSecurityException;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

public final class HmacRequestVerifierV1 {
    private static final long MAX_PAST_SECONDS = 300;
    private static final long FUTURE_SKEW_SECONDS = 30;
    private static final Duration NONCE_TTL =
            Duration.ofSeconds(360);

    private final CredentialRegistryV1 registry;
    private final ReplayStoreV1 replayStore;
    private final Clock clock;

    public HmacRequestVerifierV1(
            CredentialRegistryV1 registry,
            ReplayStoreV1 replayStore,
            Clock clock) {

        this.registry = registry;
        this.replayStore = replayStore;
        this.clock = clock;
    }

    public VerifiedPrincipalV1 verify(SignedRequestV1 request) {
        // Defensive key-ID grammar check at the service boundary.
        String keyId = KeyIdInputV1.requireExact(List.of(
                new HttpFieldV1("X-Key-Id", request.keyId())));

        // Reject malformed tag before cryptographic work.
        byte[] presented = SignatureCodecV1.decode(
                request.presentedTagB64Url());

        final HmacCredentialV1 key;
        try {
            Optional<HmacCredentialV1> found =
                    registry.findExact(keyId);

            if (found.isEmpty()) {
                throw new AuthRejectedV1(
                        AuthFailureV1.KEY_ID_UNKNOWN);
            }
            key = found.get();
        } catch (RegistryUnavailableV1 unavailable) {
            throw new AuthRejectedV1(
                    AuthFailureV1.DEPENDENCY_UNAVAILABLE);
        }

        // Never accept a case-insensitive/alias lookup result.
        if (!keyId.equals(key.keyId())) {
            throw new AuthRejectedV1(
                    AuthFailureV1.KEY_ID_RECORD_INCONSISTENT);
        }

        Instant now = clock.instant();

        // V1 demo allows only ACTIVE; a production rotation policy
        // can explicitly allow RETIRING until verifyUntil.
        if (key.status() != KeyStatusV1.ACTIVE
                || now.isBefore(key.notBefore())
                || !now.isBefore(key.notAfter())) {

            throw new AuthRejectedV1(
                    AuthFailureV1.KEY_NOT_ALLOWED);
        }

        if (!"orders-api".equals(key.audience())
                || !"HmacSHA256".equals(key.algorithm())) {
            throw new AuthRejectedV1(
                    AuthFailureV1.KEY_WRONG_AUDIENCE);
        }

        final byte[] canonical;
        final byte[] expected;
        try {
            canonical = CanonicalHmacV1.bytes(request);
            expected = HmacSha256V1.expected(
                    key.secret(), canonical);
        } catch (NoSuchAlgorithmException unavailable) {
            throw new AuthRejectedV1(
                    AuthFailureV1.DEPENDENCY_UNAVAILABLE);
        } catch (GeneralSecurityException unavailable) {
            throw new AuthRejectedV1(
                    AuthFailureV1.DEPENDENCY_UNAVAILABLE);
        }

        if (!HmacSha256V1.sameFullTag(expected, presented)) {
            throw new AuthRejectedV1(
                    AuthFailureV1.TAG_MISMATCH);
        }

        // Client signed timestamp is integrity-protected, but
        // freshness is still determined by trusted server clock.
        long nowSeconds = now.getEpochSecond();
        final long oldest, newest;
        try {
            oldest = Math.subtractExact(
                    nowSeconds, MAX_PAST_SECONDS);
            newest = Math.addExact(
                    nowSeconds, FUTURE_SKEW_SECONDS);
        } catch (ArithmeticException overflow) {
            throw new AuthRejectedV1(
                    AuthFailureV1.TIMESTAMP_INVALID);
        }

        if (request.timestampSeconds() < oldest
                || request.timestampSeconds() > newest) {
            throw new AuthRejectedV1(
                    AuthFailureV1.TIMESTAMP_INVALID);
        }

        // Claim only AFTER exact-key, full-MAC and freshness pass.
        String nonceKey = "hmac-replay:v1:orders-api:"
                + keyId + ":" + request.nonceHex();

        final ReplayStoreV1.Claim claim;
        try {
            claim = replayStore.claimOnce(nonceKey, NONCE_TTL);
        } catch (RuntimeException unavailable) {
            throw new AuthRejectedV1(
                    AuthFailureV1.DEPENDENCY_UNAVAILABLE);
        }

        if (claim == ReplayStoreV1.Claim.REPLAY) {
            throw new AuthRejectedV1(
                    AuthFailureV1.NONCE_REPLAY);
        }
        if (claim != ReplayStoreV1.Claim.NEW) {
            // UNKNOWN or null is not "NEW".
            throw new AuthRejectedV1(
                    AuthFailureV1.DEPENDENCY_UNAVAILABLE);
        }

        return new VerifiedPrincipalV1(
                key.principalId(),
                key.clientId(),
                key.tenantId(),
                key.keyId(),
                key.audience());
    }
}
~~~

### 15.3. Điều gì quan trọng nhất?

- Parser không tự sửa key ID. `KeyIdInputV1` đưa ra một string exact.
- Chỉ một `registry.findExact(keyId)`; không có vòng lặp secrets.
- `Optional.empty()` có nghĩa authoritative missing; `RegistryUnavailableV1` không được nuốt.
- Record returned phải có exact `record.keyId().equals(requested)`.
- Status/audience/algorithm phải đến từ server credential policy.
- Canonical bytes bao gồm exact signed key ID.
- HMAC mismatch **không** làm verifier đổi sang key k2/B1.
- Nonce chỉ claim sau full HMAC và timestamp đúng.
- `REPLAY`/`UNKNOWN`/dependency errors đều không tạo principal.
- Trusted principal do record quyết định, không do header tenant/role quyết định.

### 15.4. Một hạn chế về thứ tự

Trong ví dụ, key policy được kiểm trước MAC, nên known-but-revoked key có thể trả nhanh hơn known-active-wrong-MAC. Public body/status nên được chuẩn hóa; timing vẫn cần đánh giá riêng theo threat model. Có thể áp dụng dummy work hoặc tổ chức lookup khác, nhưng không được biến unknown/revoked thành accept.

### 15.5. Lỗi nghiệp vụ không phải lỗi key ID

`verify()` không tự kiểm customer ownership hay scope `orders:delete`. Business layer phải kiểm authenticated principal/tenant/resource. Kể cả khi một principal có key ID/secret hợp lệ, việc truy cập tenant khác không tự được cho phép.

## 16. Public response mapper: một lớp, nhiều internal reasons

Một service không nên để mọi `AuthRejectedV1.code()` rò thẳng ra HTTP. Thay vào đó, dùng một lớp ánh xạ theo API contract.

### 16.1. PublicErrorV1

~~~java
import java.util.Map;

public record PublicErrorV1(
        int httpStatus,
        Map<String, String> headers,
        String body) {}
~~~

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public final class PublicErrorMapperV1 {
    private PublicErrorMapperV1() {}

    /**
     * traceId phải do server tạo, đã validate/redact;
     * tuyệt đối không dùng raw keyId làm traceId.
     */
    public static PublicErrorV1 forAuthFailure(
            AuthRejectedV1 error, String traceId) {

        boolean dependency = error.code()
                == AuthFailureV1.DEPENDENCY_UNAVAILABLE
                || error.code()
                == AuthFailureV1.KEY_ID_RECORD_INCONSISTENT;

        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("Content-Type", "application/problem+json");
        headers.put("Cache-Control", "no-store");

        if (dependency) {
            // Optional. Retry policy must address nonce and
            // idempotency; Retry-After alone is not sufficient.
            headers.put("Retry-After", "5");
            return new PublicErrorV1(
                    503, Map.copyOf(headers),
                    """
                    {"type":"about:blank",
                     "title":"Authentication service unavailable",
                     "status":503,
                     "code":"AUTH_SERVICE_UNAVAILABLE"}
                    """);
        }

        // A demo custom auth scheme: challenge grammar must be
        // documented by the API. Not a universal HMAC standard.
        headers.put("WWW-Authenticate",
                "HMAC realm=\"orders-api\"");

        return new PublicErrorV1(
                401, Map.copyOf(headers),
                """
                {"type":"about:blank",
                 "title":"Authentication failed",
                 "status":401,
                 "code":"AUTHENTICATION_FAILED"}
                """);
    }
}
~~~

Java text block có LF/whitespace format; đó là response body minh họa. `traceId` trong signature chưa được đưa vào JSON ở ví dụ để tránh cần JSON escaping tự viết; production nên dùng JSON serializer và server-generated request correlation ID.

### 16.2. Lỗi nào được gộp?

Theo public mapping minh họa, `KEY_ID_MISSING`, `KEY_ID_MALFORMED`, `KEY_ID_UNKNOWN`, `KEY_NOT_ALLOWED`, `TAG_MALFORMED`, `TAG_MISMATCH` và `NONCE_REPLAY` đều có public authentication-failed response tương đương. Nếu API muốn trả `400` cho syntax violations, phải tài liệu hóa và đánh giá enumeration surface. **Không** để một public branch lộ key ID tồn tại riêng.

### 16.3. Lỗi dependency không giả thành credential invalid

Registry outage được thể hiện thành `503` để client có thể xử lý service availability theo contract; phía server vẫn **không gọi business**. Nếu partial nonce claim đã thành công nhưng response bị mất, client retry cùng nonce có thể gặp `REPLAY`: cần operation-status hoặc signed retry nonce mới với cùng idempotency key, không tắt replay protection.

### 16.4. 401 challenge không nên chứa user/key existence

Đừng trả một challenge khác cho `unknown key`, `key revoked` và `bad tag`. Một simple `WWW-Authenticate: HMAC realm="orders-api"` đủ cho custom scheme nếu hợp đồng định nghĩa nó. Không đưa `keyId`/status, accepted key list, expected signature vào challenge.

## 17. Tích hợp Spring Security MVC và WebFlux

### 17.1. Spring MVC/Servlet filter

Một custom `OncePerRequestFilter` hoặc `AuthenticationFilter` có thể lấy header fields từ `HttpServletRequest`, gọi parser/verifier, và chỉ đặt trusted Authentication sau khi service trả `VerifiedPrincipalV1`.

Các cảnh báo:

- Servlet `getHeader("X-Key-Id")` thường trả first value; cần `getHeaders` và ingress duplicate validation.
- Raw body ký HMAC phải được buffer với limit và **request wrapper replay bytes** cho controller.
- Nếu filter ở trước `ExceptionTranslationFilter`, không giả định exception từ verifier được filter ở sau bắt; dùng failure handler/entry point đúng vị trí.
- Không register filter hai lần ở Servlet container và Spring Security chain.
- Authenticated principal phải có trusted authorities; authorization tenant/object vẫn xử lý riêng.

Một đoạn tích hợp **chỉ sau verify thành công**:

~~~java
// trustedResult được tạo từ verifier.verify(parsedRequest) đã PASS.
var authentication =
        org.springframework.security.authentication
            .UsernamePasswordAuthenticationToken.authenticated(
                trustedResult,
                null,
                grantedAuthoritiesFromTrustedPolicy);

var context =
        org.springframework.security.core.context
            .SecurityContextHolder.createEmptyContext();

context.setAuthentication(authentication);
org.springframework.security.core.context
        .SecurityContextHolder.setContext(context);

// Trong custom filter, cần chain + context cleanup đúng lifecycle.
~~~

Không đặt authenticated context ngay khi registry.findExact tìm thấy record.

### 17.2. Spring WebFlux reactive stack

Trong WebFlux, dùng `AuthenticationWebFilter` + `ServerAuthenticationConverter` + `ReactiveAuthenticationManager` khi phù hợp, hoặc specialized `WebFilter` cho body capture. `ServerWebExchange` cung cấp URI/headers và `Flux<DataBuffer>`; body phải được giữ nguyên/replay nếu converter đã đọc.

- Missing/unknown key trên required HMAC route không được biến thành `Mono.empty()` khiến endpoint anonymous vẫn được accept.
- Registry unavailable và nonce store UNKNOWN phải emit authentication failure/service error, không `onErrorResume(... -> chain.filter(exchange))`.
- Dùng `ReactiveSecurityContextHolder`/framework security integration, không thread-local mutable static principal.
- Blocking registry/KMS/Redis APIs không được chạy trên Netty event loop; dùng reactive clients hoặc bounded offload có giám sát.

### 17.3. Authorization không bị chuyển thành 401 mọi lúc

Nếu HMAC đã xác thực principal nhưng `AuthorizationManager` từ chối tenant/action, response có thể `403` (hoặc policy-specific non-disclosure status). Không bắt tất cả exceptions trong web filter rồi báo “invalid key ID”; như vậy vừa sai semantics vừa khó điều tra.

### 17.4. Khi nào có `WWW-Authenticate`?

Với HTTP `401`, challenge là bắt buộc theo HTTP semantics. Nếu API chỉ truyền HMAC qua custom headers, hãy xác định đầy đủ authentication scheme/challenge contract hoặc response strategy phù hợp. Đừng gửi Bearer challenge trên HMAC-only endpoint rồi khiến client nghĩ có thể thay HMAC bằng JWT để vượt request-signature requirement.

## 18. JUnit 5: fake registry và nonce store

Các ví dụ này dùng **Java 17 + JUnit Jupiter** và các lớp ở mục 11–15. Mỗi public type nên đặt trong source file riêng khi tích hợp thật. Fake stores chỉ test logic **trong một JVM**, không chứng minh TTL, Redis failover hay KMS ACL.

### 18.1. FakeCredentialRegistryV1

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class FakeCredentialRegistryV1
        implements CredentialRegistryV1 {

    private final Map<String, HmacCredentialV1> keys =
            new ConcurrentHashMap<>();
    private volatile boolean unavailable;

    public void put(HmacCredentialV1 key) {
        keys.put(key.keyId(), key);
    }

    public void putUnderWrongAlias(
            String requested, HmacCredentialV1 actual) {
        keys.put(requested, actual);
    }

    public void setUnavailable(boolean value) {
        unavailable = value;
    }

    @Override
    public Optional<HmacCredentialV1> findExact(String id) {
        if (unavailable) {
            throw new RegistryUnavailableV1("Test lookup outage");
        }
        return Optional.ofNullable(keys.get(id));
    }
}
~~~

### 18.2. FakeReplayStoreV1

~~~java
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public final class FakeReplayStoreV1 implements ReplayStoreV1 {
    private final Set<String> claimed =
            ConcurrentHashMap.newKeySet();
    private volatile boolean unavailable;

    public int size() { return claimed.size(); }

    public void setUnavailable(boolean value) {
        unavailable = value;
    }

    @Override
    public Claim claimOnce(String key, Duration ttl) {
        if (unavailable) return Claim.UNKNOWN;
        return claimed.add(key) ? Claim.NEW : Claim.REPLAY;
    }
}
~~~

**Giới hạn:** `ConcurrentHashMap.newKeySet()` atomic trong process, nhưng không có retention/expiry, durability hoặc shared authority giữa pods. Không dùng fake này làm production anti-replay.

## 19. JUnit 5: test sai key ID và cross-client impersonation

### 19.1. Fixture hai clients độc lập

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public final class WrongKeyIdVerifierV1Test {
    private static final long EPOCH = 1_800_000_030L;
    private static final Instant NOW =
            Instant.ofEpochSecond(EPOCH);
    private static final Clock CLOCK =
            Clock.fixed(NOW, ZoneOffset.UTC);

    private static final byte[] KA =
            "test-only-secret-independent-for-A"
                .getBytes(StandardCharsets.US_ASCII);
    private static final byte[] KB =
            "test-only-secret-independent-for-B"
                .getBytes(StandardCharsets.US_ASCII);
    private static final String N =
            "0123456789abcdef0123456789abcdef";

    private FakeCredentialRegistryV1 registry;
    private FakeReplayStoreV1 replay;
    private HmacRequestVerifierV1 verifier;

    private static HmacCredentialV1 key(
            String id, String client, String tenant,
            byte[] secret, KeyStatusV1 status) {
        return new HmacCredentialV1(
                id, client, client + "-principal", tenant,
                "orders-api", "HmacSHA256", status,
                NOW.minusSeconds(600),
                NOW.plusSeconds(600),
                secret);
    }

    private static SignedRequestV1 draft(
            String id, String nonce) {
        String tagPlaceholder =
                Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(new byte[32]);
        return new SignedRequestV1(
                "POST", "/v1/orders", "dryRun=false",
                "orders.example.test", "application/json",
                id, EPOCH, nonce, tagPlaceholder,
                "{\"orderId\":\"O42\"}"
                    .getBytes(StandardCharsets.UTF_8));
    }

    private static SignedRequestV1 sign(
            String id, byte[] secret, String nonce)
            throws Exception {

        var original = draft(id, nonce);
        byte[] tag = HmacSha256V1.expected(
                secret, CanonicalHmacV1.bytes(original));

        return new SignedRequestV1(
                original.method(),
                original.rawPath(),
                original.rawQuery(),
                original.host(),
                original.contentType(),
                id,
                EPOCH,
                nonce,
                Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(tag),
                original.rawBody());
    }

    private static AuthFailureV1 fails(Runnable attempt) {
        return assertThrows(
                AuthRejectedV1.class, attempt::run).code();
    }

    @BeforeEach
    void before() {
        registry = new FakeCredentialRegistryV1();
        registry.put(key(
                "partner-a-k3", "partner-A", "tenant-A",
                KA, KeyStatusV1.ACTIVE));
        registry.put(key(
                "partner-b-k1", "partner-B", "tenant-B",
                KB, KeyStatusV1.ACTIVE));

        replay = new FakeReplayStoreV1();
        verifier = new HmacRequestVerifierV1(
                registry, replay, CLOCK);
    }

    @Test
    void exactAAndBAreAuthenticatedSeparately()
            throws Exception {
        var a = verifier.verify(sign("partner-a-k3", KA, N));
        var b = verifier.verify(sign("partner-b-k1", KB, N));

        assertEquals("partner-A", a.clientId());
        assertEquals("partner-B", b.clientId());
        // Cùng text N nhưng namespace theo key ID.
        assertEquals(2, replay.size());
    }

    @Test
    void unknownIdNeverFallsBackToASecret()
            throws Exception {
        var input = sign("partner-a-k99", KA, N);

        assertEquals(AuthFailureV1.KEY_ID_UNKNOWN,
                fails(() -> verifier.verify(input)));
        assertEquals(0, replay.size());
    }

    @Test
    void clientBSecretCannotImpersonateA()
            throws Exception {
        var input = sign("partner-a-k3", KB, N);

        assertEquals(AuthFailureV1.TAG_MISMATCH,
                fails(() -> verifier.verify(input)));
        assertEquals(0, replay.size());
    }

    @Test
    void changingSignedKeyIdAfterSigningFails()
            throws Exception {
        var signedA = sign("partner-a-k3", KA, N);
        var tampered = new SignedRequestV1(
                signedA.method(), signedA.rawPath(),
                signedA.rawQuery(), signedA.host(),
                signedA.contentType(), "partner-b-k1",
                signedA.timestampSeconds(), signedA.nonceHex(),
                signedA.presentedTagB64Url(), signedA.rawBody());

        assertEquals(AuthFailureV1.TAG_MISMATCH,
                fails(() -> verifier.verify(tampered)));
    }

    @Test
    void revokedAStillAllowsB() throws Exception {
        registry.put(key(
                "partner-a-k3", "partner-A", "tenant-A",
                KA, KeyStatusV1.REVOKED));

        var a = sign("partner-a-k3", KA, N);
        assertEquals(AuthFailureV1.KEY_NOT_ALLOWED,
                fails(() -> verifier.verify(a)));

        var b = sign("partner-b-k1", KB, N);
        assertEquals("partner-B",
                verifier.verify(b).clientId());
        assertEquals(1, replay.size());
    }

    @Test
    void wrongTagDoesNotPoisonNonce()
            throws Exception {
        var bad = sign("partner-a-k3", KB, N);
        assertEquals(AuthFailureV1.TAG_MISMATCH,
                fails(() -> verifier.verify(bad)));
        assertEquals(0, replay.size());

        var good = sign("partner-a-k3", KA, N);
        assertEquals("partner-A",
                verifier.verify(good).clientId());
    }

    @Test
    void sameRequestCannotBeAdmittedTwice()
            throws Exception {
        var good = sign("partner-a-k3", KA, N);
        verifier.verify(good);

        assertEquals(AuthFailureV1.NONCE_REPLAY,
                fails(() -> verifier.verify(good)));
        assertEquals(1, replay.size());
    }

    @Test
    void lookupOutageFailsClosed() throws Exception {
        registry.setUnavailable(true);
        var good = sign("partner-a-k3", KA, N);

        assertEquals(AuthFailureV1.DEPENDENCY_UNAVAILABLE,
                fails(() -> verifier.verify(good)));
        assertEquals(0, replay.size());
    }

    @Test
    void registryAliasRecordMustNotAuthenticate()
            throws Exception {
        registry.putUnderWrongAlias(
                "Partner-A-K3",
                key("partner-a-k3", "partner-A",
                    "tenant-A", KA, KeyStatusV1.ACTIVE));

        var aliasInput = sign("Partner-A-K3", KA, N);
        assertEquals(
                AuthFailureV1.KEY_ID_RECORD_INCONSISTENT,
                fails(() -> verifier.verify(aliasInput)));
    }

    @Test
    void unknownCaseVariantIsNotAutoLowercased()
            throws Exception {
        var input = sign("PARTNER-A-K3", KA, N);

        assertEquals(AuthFailureV1.KEY_ID_UNKNOWN,
                fails(() -> verifier.verify(input)));
    }

    @Test
    void replayStoreUnknownIsNotNew() throws Exception {
        replay.setUnavailable(true);
        var good = sign("partner-a-k3", KA, N);

        assertEquals(AuthFailureV1.DEPENDENCY_UNAVAILABLE,
                fails(() -> verifier.verify(good)));
    }

    @Test
    void malformedAndDuplicateHeadersAreRejected() {
        assertEquals(AuthFailureV1.KEY_ID_MALFORMED,
                fails(() -> KeyIdInputV1.requireExact(
                        List.of(new HttpFieldV1(
                                "X-Key-Id", " partner-a-k3")))));

        assertEquals(AuthFailureV1.KEY_ID_AMBIGUOUS,
                fails(() -> KeyIdInputV1.requireExact(
                        List.of(
                            new HttpFieldV1(
                                    "X-Key-Id", "partner-a-k3"),
                            new HttpFieldV1(
                                    "x-key-id", "partner-b-k1")))));

        assertEquals(AuthFailureV1.KEY_ID_MISSING,
                fails(() -> KeyIdInputV1.requireExact(
                        List.of())));
    }
}
~~~

### 19.2. Các bất biến được kiểm

- A/B có secrets độc lập; cùng nonce text có thể hợp lệ nếu key-scoped namespace khác nhau.
- Unknown ID không fallback sang key khác, không claim nonce.
- Secret B không thể ký request khai key ID A.
- Thay key ID sau khi ký phải làm tag mismatch.
- Key REVOKED có MAC đúng vẫn bị từ chối; client B không liên quan vẫn hoạt động.
- MAC sai không chiếm nonce của request hợp lệ.
- Replay cùng signed request bị chặn.
- Registry/nonce store unavailable không cấp principal.
- Case-sensitive exact lookup và record alias mismatch đều được kiểm.

### 19.3. Những điều chưa được chứng minh

Bộ tests chỉ kiểm verifier trong một JVM. Nó **không** chứng minh body đã được canonicalize giống gateway, Spring Security chain đã match đúng, Redis cluster atomic/durability, anti-enumeration timing, tenant authorization hoặc đúng client error contract. Vì fixture signer/verifier dùng cùng `CanonicalHmacV1`, hãy bổ sung **golden byte fixtures độc lập** và RFC 4231 known-answer vectors.

**STEP 4 chỉ soạn nội dung**, không khẳng định Java tests đã được chạy hoặc STEP 6 Content QA đã hoàn thành.

## 20. Test HTTP public response và Spring Security integration

Unit tests trong mục 19 kiểm tính chất của verifier, không tự chứng minh public API trả đúng `401`/`WWW-Authenticate`. Phải có integration tests chạy qua **security filter chain** và handler thật.

### 20.1. Ma trận public HTTP outcomes

| Tình huống | Internal reason | Public response minh họa | Business side effect |
| --- | --- | --- | --- |
| Không có `X-Key-Id` | KEY_ID_MISSING | Generic 401 + challenge | Không |
| ID sai grammar | KEY_ID_MALFORMED | Generic 401 hoặc policy 400 | Không |
| Duplicate Key-ID header | KEY_ID_AMBIGUOUS | Reject tại ingress (ví dụ 400) | Không |
| Unknown key ID | KEY_ID_UNKNOWN | Generic 401 | Không |
| ID known nhưng dùng secret khác | TAG_MISMATCH | **Cùng public 401 như unknown** | Không |
| ID REVOKED/EXPIRED | KEY_NOT_ALLOWED | **Cùng public 401 như unknown** | Không |
| ID wrong audience | KEY_WRONG_AUDIENCE | Generic 401 | Không |
| Registry timeout | DEPENDENCY_UNAVAILABLE | Generic 503 + retry policy | Không |
| Secret manager outage | DEPENDENCY_UNAVAILABLE | Generic 503 | Không |
| HMAC tag không canonical encoding | TAG_MALFORMED | Generic 401 hoặc contract 400 | Không |
| Timestamp stale | TIMESTAMP_INVALID | Generic 401 | Không |
| Nonce replay | NONCE_REPLAY | Generic 401 | Không |
| Nonce store UNKNOWN | DEPENDENCY_UNAVAILABLE | Generic 503 | Không |
| Key/MAC đúng, scope thiếu | AUTHZ_DENIED | 403 hoặc domain non-disclosure policy | Không |
| Key/MAC đúng, resource không tồn tại | RESOURCE_NOT_FOUND | 404 | Không |
| Valid/authorized request | ACCEPTED | Business response | Theo operation |

Mọi con số là **gợi ý cho một API contract minh họa**, không phải mapping tiêu chuẩn duy nhất của các HMAC APIs. HTTP 401 phải có `WWW-Authenticate` challenge thích hợp; nếu chọn 400 cho malformed input thì phải xem xét risk enumeration và consistency.

### 20.2. Integration assertions quan trọng

~~~text
POST /v1/orders?dryRun=false
X-Key-Id: partner-a-k99
X-Signature: ...
  -> 401 generic
  -> no principal
  -> no order created

POST /v1/orders?dryRun=false
X-Key-Id: partner-a-k3
X-Signature: tag computed with KB1
  -> same public status/challenge/body shape
  -> no order created

POST /v1/orders?dryRun=false
X-Key-Id: partner-a-k3
X-Signature: correct tag, key REVOKED
  -> same public authentication failure
  -> no order created

POST /v1/orders?dryRun=false
X-Key-Id: partner-a-k3
X-Signature: correct tag, key ACTIVE
  -> HMAC authentication succeeds
  -> resource authorization still enforced
~~~

Ngoài status, assert:
- Không có trusted principal hoặc authorities trong failure flows.
- Handler/database không bị gọi.
- Không ghi nonce khi malformed/unknown/bad MAC.
- Không có expected MAC/secretRef/key-state details trong body/headers/logs.
- Internal metrics phân biệt unknown/mismatch/revoked/outage.
- Không có khác biệt public response shape đáng kể do credential tồn tại.
- Client được chỉ dẫn theo **một troubleshooting contract an toàn**.

### 20.3. MockMvc có thể bỏ qua HMAC nếu chỉ dùng @WithMockUser

Trong Spring Security Servlet, một integration test chỉ gắn `@WithMockUser` có thể tạo security principal mà **không đi qua HMAC filter**. Cần gửi signed request headers thật và xác minh verifier invocation count.

Với WebFlux, `WebTestClient` integration phải dùng `AuthenticationWebFilter`/`ReactiveAuthenticationManager` thật theo test configuration, không chỉ chèn authentication bằng test security context. Body stream cần đúng bytes và signing boundary.

### 20.4. Raw HTTP tests qua gateway

`MockMvc` và `WebTestClient.bindToApplicationContext` không mô phỏng hoàn toàn:
- Multiple raw `X-Key-Id` fields qua HTTP/1.1–HTTP/2 conversion.
- Request smuggling/framing ambiguities.
- HTTP/2 pseudo-headers `:path` và `:authority`.
- Proxy path prefix rewrites.
- Header field merging/normalization.
- Body decompression/re-serialization.
- Alternate ingress hoặc backend direct access.

Vì vậy cần tests qua **proxy/gateway thật**, không chỉ Java parser.

### 20.5. Same HTTP response không đủ chống timing oracle

Dù status/body giống nhau, known key có thể cần KMS lookup+HMAC còn unknown key reject sớm. Đừng tuyên bố không có enumeration chỉ vì MockMvc assert public JSON bằng nhau. Kết hợp threat model, controlled timing experiments, rate limits và monitoring.

## 21. Chẩn đoán client-side: sửa sai key ID mà không tiết lộ secret

Đối tác thường báo “signature invalid” và nghĩ thuật toán HMAC sai. Một quy trình tự kiểm tra an toàn:

1. Xác nhận client chọn đúng **environment/audience** (production vs sandbox, orders vs payments).
2. Đối chiếu key ID đang cấu hình với portal/credential metadata qua **kênh đã xác thực**, không gửi secret vào support ticket.
3. Bảo đảm key ID string là exact, đúng chữ hoa/thường và không có leading/trailing whitespace.
4. Kiểm **key ID đi với đúng secret version**; rotation k2→k3 đòi đổi cả ID và secret.
5. Xác minh signed header `X-Key-Id` thực sự được gửi **một lần** trên HTTP wire.
6. Đảm bảo key ID được ràng buộc trong canonical request; signer/verifier dùng cùng canonical version.
7. Kiểm method, public URI/path, query, signed headers và raw body digest trước/sau proxy.
8. Kiểm timestamp là **epoch seconds**, không milliseconds; nonce có format/uniqueness policy rõ.
9. Xác nhận signature là full HMAC-SHA256 tag, encode Base64URL unpadded.
10. Không “fix” bằng cách thử mọi secrets hoặc bỏ header khỏi HMAC input.
11. Nếu nghi key revoked/compromised, dùng secure credential rotation workflow thay vì cố reuse old secret.
12. Dùng **server-generated trace ID** để support tra internal reason; không yêu cầu gửi raw secret, full Authorization hoặc raw sensitive payload vào ticket.

### 21.1. Troubleshooting matrix cho client

| Client thấy | Có thể kiểm an toàn ở client | Không nên làm |
| --- | --- | --- |
| Generic 401 ngay sau rotation | Key ID/secret version pair | Thử dùng secret cũ dưới ID mới |
| 401 chỉ trong production | Audience/environment/host/path | Tắt signature verification ở production |
| 401 khi qua gateway | Public URI, query, signed headers/body bytes | Fallback qua nhiều canonical paths |
| 401 với uppercase ID | Case-sensitive exact ID | Lowercase mọi key ID bên server |
| 401 ngắt quãng | Clock skew, nonce reuse, replica consistency | Nới freshness vô hạn hoặc tắt replay |
| 503 từ registry | Retry/backoff/idempotency/status lookup | Vòng lặp requests vô hạn cùng nonce |
| 403 sau HMAC pass | Trusted scopes, grants, target tenant | Thay `X-Role: admin` để tự cấp quyền |
| 413 với signed body | Payload limit, streaming contract | Buffer file cực lớn trong filter |

### 21.2. Debug canonical bytes bằng fixtures không bí mật

Tạo một **test-only** canonical request fixture có payload không nhạy cảm, known test secret và expected HMAC vector. Có thể so byte-for-byte tại signer/verifier trong test environment. Không log canonical request production nếu nó chứa sensitive header/body hash/tenant identifiers vi phạm policy.

### 21.3. Không dùng public key-discovery endpoint cho unknown IDs

Một endpoint `GET /keys/{keyId}/exists` cho Internet sẽ biến key registry thành enumeration oracle. Nếu cần dashboard quản lý credentials, bảo vệ bằng **authenticated owner/admin authorization**, hạn chế tenant scope, rate limit và audit đầy đủ.

## 22. Vận hành và phản ứng sự cố

### 22.1. Khi tăng mạnh KEY_ID_UNKNOWN

Dấu hiệu:

~~~text
KEY_ID_UNKNOWN rate increased
many distinct key IDs
same source / ASN / bot-like burst
registry lookup and negative-cache pressure rising
~~~

Hành động:
- Kiểm pre-auth rate limits, request body/header limits và identity-independent resource budgets.
- Xem mẫu IDs **dưới quyền truy cập audit** để phân biệt partner misconfiguration với enumeration.
- Xác định có key mới onboard nhưng negative cache chưa invalidate không.
- Kiểm URL/env/audience routing và API version migration.
- Không phát raw unknown ID labels vô hạn vào metrics.
- Không trả danh sách key IDs hợp lệ cho callers.

### 22.2. Khi tăng KEY_ID_NOT_ALLOWED

Dấu hiệu có thể do:
- Một partner chưa hoàn tất rotation overlap.
- Emergency revocation đã có hiệu lực.
- Stale cache không đồng bộ key status.
- Key bị disabled/expired, client vẫn gửi request.
- Clock/status policy mismatch giữa verifier nodes.

Hành động phải khác unknown-ID flood: xem trusted registry change events, rotation timeline và revocation propagation. Không tự re-enable compromised key chỉ để giảm 401 rate.

### 22.3. Khi tăng TAG_MISMATCH cho một known key

Khả năng:
- Client dùng secret version không thuộc key ID.
- Canonical path/query/body khác sau gateway rewrite.
- Signed header thiếu hoặc khác encoding/whitespace.
- Base64URL vs hex/standard Base64 confusion.
- Body JSON bị serialize lại.
- Client thay key ID sau khi ký.
- Secret store có wrong version/corruption.
- Algorithm/audience policy không nhất quán.

Điều tra bằng test fixtures/canonical byte hashes đã kiểm soát, không yêu cầu đối tác chia sẻ production secret. Nếu nghi material lộ, theo incident runbook và revoke/rotate.

### 22.4. Khi registry/KMS outage

Một dependency outage **không chứng minh key không tồn tại**. Fail closed, áp timeout/backpressure, công bố retry semantics, kiểm khả năng impact trên các tenants/regions, và tránh để cache stale ACTIVE kéo dài ngoài policy.

Nếu request đã claim nonce nhưng response bị mất, client không thể chắc business có chạy chưa. Dùng durable operation ID/idempotency and status lookup, không suy từ `503` rằng request chắc chắn chưa được xử lý.

### 22.5. Khi key bị compromise

1. Xác định chính xác key IDs/secrets/clients/tenants bị ảnh hưởng.
2. Revoke exact key IDs tại trusted authority và đo effective deny ở mọi gateways/verifiers.
3. Cấp secret mới **độc lập** cùng key ID mới.
4. Đánh giá source of leak (CI, logs, config, partner device, KMS permissions).
5. Đối chiếu accepted requests và business side effects trong exposure window.
6. Kiểm key B không liên quan vẫn hợp lệ nếu credential isolation đúng.
7. Test requests ký bằng revoked key bị deny dù HMAC cryptographically correct.
8. Không sửa sự cố bằng default/fallback secret hoặc bypass replay store.

### 22.6. Audit dữ liệu gì?

Ghi vào trusted logs/metrics:
- Server-generated trace/correlation ID.
- Matched route/audience và gateway/node.
- Outcome code nội bộ, elapsed time theo bucket.
- Trusted client/principal/key version **chỉ khi đã được xác minh hoặc theo privileged audit policy**.
- Registry/policy revision khi có ích.
- Incident/change ID khi key status thay đổi.

Không log raw shared secret, expected HMAC, raw authorization/sensitive body hoặc full replayable signed request. Unknown key ID là untrusted high-cardinality input, không nên đưa nguyên văn vào metrics labels.

## 23. Ma trận kiểm thử Sai key ID

| Nhóm | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Parsing | Không có `X-Key-Id` | Reject, no principal |
| Parsing | Empty key ID | Reject |
| Parsing | Leading/trailing spaces | Reject, no trim |
| Parsing | Unicode/confusable characters | Reject theo ASCII V1 |
| Parsing | 65+ characters | Reject sớm |
| Parsing | Comma-joined IDs | Reject |
| Parsing | Duplicate key header khác case | Reject ở ingress |
| Parsing | CRLF/control bytes | Reject |
| Parsing | Malformed Authorization HMAC scheme | Reject |
| Lookup | Unknown k99 | Reject, không fallback |
| Lookup | Uppercase variant của valid ID | Exact different ID/unknown |
| Lookup | DB alias returns wrong record ID | Reject, alert integrity |
| Lookup | Registry timeout | Fail closed, internal unavailable |
| Lookup | KMS/secret manager outage | Fail closed |
| Credential | Key disabled/revoked | Reject even with correct MAC |
| Credential | Key not yet valid/expired | Reject |
| Credential | Wrong audience/algorithm | Reject |
| Credential | Key rotation A2→A3 | Mỗi ID dùng đúng secret |
| Credential | A3 tag từ secret A2 | MAC mismatch, no fallback |
| Credential | Key A3 revoked, B1 active | B1 unaffected |
| Canonical | Key ID changed after signing | MAC mismatch |
| Canonical | Method/path/query changed | MAC mismatch |
| Canonical | Gateway rewrites signed public URI | Contract mismatch identified |
| Canonical | Body bytes altered after signing | MAC mismatch |
| Canonical | Missing mandatory signed key ID | Reject |
| HMAC | Full valid 32-byte tag | May pass authentication |
| HMAC | Truncated/prefix tag | Reject |
| HMAC | Invalid Base64URL/padding | Reject |
| HMAC | Secret B signing under ID A | Reject |
| Replay | Bad MAC with fresh nonce | Do not claim nonce |
| Replay | Same signed request twice | Second replay reject |
| Replay | A and B same nonce text | Independent key-scoped NEW |
| Replay | Replay store UNKNOWN | Fail closed |
| HTTP | Unknown ID vs known bad MAC | Same public auth failure shape |
| HTTP | Revoked ID vs unknown ID | No public key-state oracle |
| HTTP | 401 challenge | Appropriate `WWW-Authenticate` |
| HTTP | Registry outage | Unavailable semantics, never auth success |
| HTTP | Authenticated but unauthorized tenant | 403 / non-disclosure policy |
| Gateway | Two Key-ID headers HTTP/1.1 | Reject |
| Gateway | HTTP/2 host/path conversion | Same signed semantics |
| Gateway | Direct backend access | Cannot bypass trusted auth |
| Concurrency | Random key-ID flood | Bounded registry/cache/metrics |
| Concurrency | 100 same nonce via two nodes | At most one admission under declared guarantee |
| Incident | Revocation cache stale ACTIVE | No accept beyond policy guarantee |
| Incident | Response lost after nonce claim | Retry/idempotency policy preserves business correctness |

## 24. Sai lầm triển khai thường gặp

### 24.1. “Key ID là API secret”

Không. Key ID chọn credential; HMAC secret mới là vật liệu mật mã. Nếu chỉ cần biết key ID là được truy cập, hệ thống chưa xác thực bằng HMAC.

### 24.2. “Không tìm thấy key thì thử key mặc định”

Một default secret là **fail-open/identity confusion risk**. Unknown ID phải reject; không đưa request đến một “global” principal.

### 24.3. “Signature không khớp thì quét toàn bộ secrets”

Sai cả hiệu năng, bảo mật và audit. Nó có thể chấp nhận tag của client B trên request khai A, gây lộ cross-client identity và làm revocation khó quản lý. Exact key ID → một secret → compare → reject.

### 24.4. “Cứ lowercase/trim key ID cho tiện”

Nếu contract case-sensitive, normalization biến các key IDs khác nhau thành một, mở alias và signer/verifier mismatch. Yêu cầu client gửi đúng bytes/grammar.

### 24.5. “Có hai X-Key-Id thì lấy getFirst”

HTTP field names case-insensitive. Gateway và backend có thể first-wins/last-wins khác nhau. Reject ambiguity tại trusted ingress, không tự chọn.

### 24.6. “Unknown key ID phải trả 404, revoked key phải trả 403”

Khác biệt status có thể tiết lộ key nào tồn tại. Thường nên có generic public authentication failure cho các credential failures. `403` dành cho trường hợp **đã authenticated nhưng thiếu permission** theo contract.

### 24.7. “401 không cần WWW-Authenticate vì dùng X-Signature”

Theo HTTP authentication semantics, `401` phải có challenge. Với custom HMAC API, phải thiết kế scheme/challenge đúng hoặc chọn response contract phù hợp. Không tự giả định HMAC là universal standard HTTP scheme.

### 24.8. “Registry timeout là unknown key ID”

Timeout không xác nhận missing. Không convert outage thành `Optional.empty()` rồi làm mất monitoring hoặc dựa vào stale key để accept; phải fail closed và báo dependency error nội bộ.

### 24.9. “Một key ID mới có thể dùng lại secret cũ”

Key rotation an toàn nên có key ID/secret material mới độc lập. Reuse secret làm giảm isolation, gây khó emergency revoke và cache consistency.

### 24.10. “Chỉ cần ký body; key ID không cần ký”

Nếu ID không được bind, attacker có thể thay selector mà không đổi signed bytes. Contract nên ký key ID và những metadata liên quan (timestamp, nonce, audience, method, URI, body hash) như đã định nghĩa.

### 24.11. “Ký JSON logic là đủ giống raw bytes”

Không khi contract ký raw body bytes. Gateway/client JSON serialization/whitespace thay đổi sẽ làm digest mismatch; không sửa bằng cách thử nhiều canonical variants.

### 24.12. “Key A bị revoke thì tắt luôn tenant B”

Thu hồi phải đúng phạm vi credential/client/tenant/grant. Nếu A3 bị compromise mà B1 độc lập, B phải có thể tiếp tục hoạt động nếu policy không có lý do chặn rộng.

### 24.13. “Nonce mới nghĩa là key hợp lệ”

Nonce NEW chỉ là replay state; key có thể unknown/revoked hoặc MAC sai. Không claim nonce trước khi MAC được verify; không dùng nonce store để suy credential existence.

### 24.14. “Dùng raw key ID làm Prometheus label để debug”

Attacker tạo hàng triệu labels; có thể gây cardinality/memory overload. Aggregate theo reason; trusted principal labels chỉ dùng khi phù hợp và giới hạn.

### 24.15. “Key ID đúng mà HMAC sai là do client chắc chắn sai”

Không luôn đúng. Gateway có thể rewrite signed URI, secret manager có wrong version, server canonicalization khác client; cần independent golden fixtures và audit. Nhưng **không** tắt HMAC/fallback để che lỗi.

### 24.16. “Public response phải trả chính xác key nào bị revoke”

Support troubleshooting nên đi qua authenticated developer portal/ticket trace ID. Public unauthenticated API không cần tiết lộ key existence/lifecycle.

### 24.17. “MessageDigest.isEqual khiến cả verifier constant-time”

Không. Lookup latency, JIT/GC, failure branching, network cache và status policy còn tạo differences. Không xem một benchmark ít mẫu là chứng minh không tồn tại timing oracle.

### 24.18. “Bắt mọi exception rồi chain.doFilter để giữ availability”

Đây là fail-open. Credential lookup/crypto/replay errors không được tạo principal hoặc side effect; availability được giải quyết bằng capacity, retry policy và incident response.

## 25. Bài tập thực hành

### Bài tập 1 — Phân loại nội bộ

Cho 12 requests có missing key ID, Unicode, leading space, duplicate fields, unknown key, wrong secret, revoked key, expired key, wrong audience, registry timeout, nonce replay và wrong tenant grant. Gán mỗi request một internal reason và xác định request nào **đã authenticated** nhưng bị authorization deny.

### Bài tập 2 — Public error contract

Thiết kế `401` response cho custom HMAC scheme của một Orders API với `WWW-Authenticate` challenge, Problem Details hoặc JSON error body. Yêu cầu response của unknown key/bad MAC/revoked key không tiết lộ key existence; internal logs vẫn phân loại.

### Bài tập 3 — Case-sensitive exact match

Tạo key `partner-a-k3` rồi gửi `Partner-A-K3`. Test phải trả unknown nếu record uppercase không có. Dùng fake registry cố tình trả record lowercase cho uppercase requested ID; assert `KEY_ID_RECORD_INCONSISTENT`.

### Bài tập 4 — Cross-client mismatch

Hai clients A/B dùng KA/KB khác nhau. Request khai key ID A nhưng HMAC tính với KB; assert reject, không tìm key khác, không tạo principal và không ghi nonce.

### Bài tập 5 — Ký key ID

Tạo canonical request với `key-id:partner-a-k3` và tag hợp lệ. Giữ nguyên tag nhưng đổi header/key-id canonical field sang B1. Tính lại expected và chứng minh mismatch. Giải thích tại sao test với shared secret material là một case cần đánh giá thêm.

### Bài tập 6 — Header parser ambiguity

Gửi hai `X-Key-Id` khác case qua raw HTTP gateway. Kiểm backend không vô tình chọn first/last; xác minh ingress reject. Lặp với combined comma value và CRLF injection.

### Bài tập 7 — Planned key rotation

A2 RETIRING tới T, A3 ACTIVE. Test A2/KA2 pass chỉ trong overlap, A3/KA3 pass; A3 + KA2 reject; A2 hết verifyUntil reject. Lưu ý demo verifier mục 15 chỉ accept ACTIVE; hãy mở rộng policy versioned cho RETIRING **không fallback secrets**.

### Bài tập 8 — Emergency revoke

Đánh dấu A3 REVOKED, ký request mới bằng KA3 với timestamp fresh/nonce mới. Dù HMAC đúng, request phải deny. Cấp A4 secret mới độc lập và kiểm B1 không bị ảnh hưởng.

### Bài tập 9 — Outage không là unknown

Cho registry trả timeout và `Optional.empty()` ở hai tests riêng. Kiểm internal reasons lần lượt là DEPENDENCY_UNAVAILABLE và KEY_ID_UNKNOWN, public behavior theo contract, không business. Kiểm retry/backoff và idempotency.

### Bài tập 10 — Fake replay store poisoning

Gửi một request khai A3 với MAC từ KB và nonce N, rồi gửi request A3 hợp lệ cùng nonce N. Request thứ hai phải được admit lần đầu; invalid MAC không claim N.

### Bài tập 11 — Unknown-key flood

Sinh 100.000 random key IDs đúng grammar và đánh giá memory/CPU của registry miss, cache và metrics. Thiết kế bounded negative cache, coarse pre-auth rate limiting và cardinality-safe labels. Không dựa vào raw IDs để tạo authenticated quotas.

### Bài tập 12 — Timestamp/nonce boundaries

Dùng `Clock.fixed`. Kiểm signed timestamp tại `now-300s`, `now+30s` và vượt giới hạn 1 giây. Đánh giá nonce TTL ≥360 giây theo contract và kiểm replay sau gateway retry.

### Bài tập 13 — Gateway rewrite

Client ký public path `/public/v1/orders` nhưng backend nhìn `/v1/orders`. Tạo independent canonical byte vectors, chọn signing boundary rõ và test e2e. Không sửa bằng cách thử canonical path khác nếu signature mismatched.

### Bài tập 14 — Security filter mapping

Trong Spring MVC hoặc WebFlux, khi verifier trả KEY_ID_UNKNOWN, filter phải ngừng request và trả generic auth error. Với registry outage, dùng fail-closed infrastructure mapping. Với tenant denial sau valid HMAC, phản hồi theo authorization policy.

### Bài tập 15 — Incident tabletop

Mô phỏng một partner cấu hình nhầm key ID k2 với secret k3, cùng lúc registry ở một region có stale status ACTIVE và ở region khác REVOKED. Xây runbook tách misconfiguration khỏi compromise, test propagation và cách xử lý signed retries.

### Bài tập 16 — Independent test vectors

Đừng dùng cùng canonicalizer để vừa tạo expected vừa verify mà cho rằng đủ. Tạo một golden canonical string/byte fixture độc lập và HMAC known-answer tests theo RFC 4231; đối chiếu byte-for-byte method/path/query/headers/body digest.

## 26. Checklist triển khai Sai key ID

### 26.1. Protocol và key selection

- [ ] Key ID có grammar, maximum length, ASCII/case-sensitive policy được công bố.
- [ ] Không tự trim, lowercase, URL-decode hoặc resolve aliases ngoài contract.
- [ ] Key ID là untrusted selector, không phải authenticated principal.
- [ ] Duplicate/multi-value Key-ID/Authorization headers bị reject ở trusted ingress.
- [ ] Không trust raw `X-Forwarded-*`/original URI do client tự gửi.
- [ ] Credential lookup là **exact-match**, với unique/case-sensitive storage semantics.
- [ ] Record returned được đối chiếu exact requested ID.
- [ ] Không fallback default/old key/other-client secret khi unknown/mismatch.
- [ ] Mỗi client/trust boundary có independent secret material và key version.
- [ ] Key ID, timestamp, nonce, audience và relevant request fields được HMAC ràng buộc.
- [ ] Algorithm/audience/status/validity lấy từ trusted key policy, không từ caller.
- [ ] Rotation overlap có cutoff rõ, emergency revoke không giữ compromised secret hoạt động.
- [ ] Body canonicalization dùng exact signed representation, có golden fixtures.
- [ ] Full HMAC tag strict encoding/length và so bằng primitive thích hợp.

### 26.2. Authentication, replay và authorization

- [ ] Missing/malformed/unknown/revoked/expired/wrong audience đều **không tạo principal**.
- [ ] Registry/KMS timeout không bị đổi thành “không có key” hoặc success.
- [ ] MAC sai không claim nonce và không chạy business handler.
- [ ] Nonce claim atomic trên shared authority, đúng namespace/TTL và fail closed khi unknown.
- [ ] Timestamp dùng server clock, past age/future skew được định nghĩa.
- [ ] Key REVOKED deny dù HMAC cryptographically correct và nonce fresh.
- [ ] Key A revoke không tự động phá client B nếu credentials độc lập.
- [ ] Authenticated principal/authorities đến từ trusted record/policy, không từ key ID prefix.
- [ ] Tenant/action/resource authorization được thực hiện **sau** authentication.
- [ ] Business idempotency không bị thay bằng nonce replay key.

### 26.3. HTTP error và observability

- [ ] Public errors tránh leak key existence, principal, revoke status hoặc secret references.
- [ ] `401` có `WWW-Authenticate` challenge thích hợp với custom scheme contract.
- [ ] `400`/`401`/`403`/`503`/`429` được tài liệu hóa đúng semantics.
- [ ] Infrastructure unavailable fail closed; retry handling rõ.
- [ ] Public response unknown/known-bad/revoked không tạo key-existence oracle rõ ràng.
- [ ] Lỗi nội bộ có codes phân biệt để cảnh báo nhưng không được serialize cho caller lạ.
- [ ] Không log shared secret, expected HMAC hoặc full replayable signed request.
- [ ] Unknown key ID raw không làm unbounded metrics labels/cache state.
- [ ] Rate limiting, bounded header/body length, cache TTL và backpressure được kiểm.
- [ ] Có incident runbook revoke, rotate, verify propagation qua nodes/regions.

### 26.4. Kiểm thử nhiều tầng

- [ ] Unit tests key ID grammar, duplicates, case variants, record mismatch.
- [ ] HMAC vectors độc lập theo RFC 4231 và golden canonical fixtures.
- [ ] Negative tests unknown ID, wrong secret, changed key ID, revoked key, wrong audience.
- [ ] Tests nonce không bị poison khi MAC sai và replay trên nhiều nodes.
- [ ] Test registry outage/negative cache/activation race/stale revoke state.
- [ ] Spring security integration test actual filter chain, không chỉ mocked principal.
- [ ] Gateway raw HTTP tests (HTTP/1.1, HTTP/2, URI/header rewrites).
- [ ] Test same public error shape và internal reason metrics.
- [ ] Test tenant denial sau successful HMAC khác credential failure.
- [ ] Test retry/idempotency khi response bị mất sau nonce claim.

## 27. Câu hỏi tự kiểm tra

1. **Key ID là gì?** Nhãn selector để tìm đúng credential/secret trong trusted registry.
2. **Key ID có phải secret không?** Thường không; shared secret mới là vật liệu HMAC cần giữ kín.
3. **Biết key ID có nghĩa đã authenticated không?** Không, phải verify full HMAC và policy.
4. **Missing khác unknown thế nào?** Missing thiếu selector; unknown đúng grammar nhưng không có record.
5. **Malformed khác unknown thế nào?** Malformed không thuộc grammar; unknown thuộc grammar nhưng lookup không tìm thấy.
6. **Registry timeout có phải unknown không?** Không; đó là unavailable và phải fail closed.
7. **Có thể trim/lowercase key ID không?** Chỉ nếu protocol quy định; V1 của bài không cho.
8. **Tên header HTTP có case-sensitive không?** Không; `X-Key-Id` và `x-key-id` là cùng field name.
9. **Giá trị key ID có case-sensitive không?** Có theo contract V1.
10. **Duplicate key ID headers xử lý thế nào?** Reject ambiguity tại ingress; không chọn first/last.
11. **Unknown ID có nên thử default secret không?** Không, đó là fallback identity risk.
12. **Tag ký bằng secret B nhưng khai ID A thì sao?** Reject MAC mismatch, không thử B.
13. **Vì sao cần ký key ID trong canonical request?** Để ràng buộc selector vào integrity của request.
14. **Key ID có thể suy tenant/role từ prefix không?** Không; principal/grant từ trusted registry/policy.
15. **Key revoked có thể tạo MAC đúng không?** Có nếu secret còn được biết, nhưng policy vẫn phải deny.
16. **Timestamp trước revokedAt có giúp key revoked được accept không?** Không, caller có thể ký lùi timestamp.
17. **401 cần header nào?** `WWW-Authenticate` challenge thích hợp.
18. **Unknown key nên có public response khác known bad MAC không?** Thường nên tránh để giảm enumeration.
19. **Có nên trả expected HMAC trong response không?** Không.
20. **403 thường dành cho trường hợp nào?** Principal đã authenticated nhưng thiếu quyền.
21. **503 do registry outage có cho request đi tiếp không?** Không; vẫn fail closed.
22. **Nonce NEW có chứng minh key hợp lệ không?** Không, chỉ chứng minh chưa claim trong replay namespace.
23. **Nên claim nonce trước MAC không?** Không, dễ bị unauthenticated replay-state poisoning.
24. **Local nonce map per pod có đủ không?** Không nếu API có nhiều verifier nodes.
25. **Request đã claim nonce rồi mất response thì retry thế nào?** Dùng operation status hoặc signed retry nonce mới với business idempotency.
26. **Negative cache unknown key có rủi ro gì?** Làm chậm activation key mới và bị flood/unbounded state.
27. **MessageDigest.isEqual bảo đảm toàn verifier constant-time không?** Không, lookup/network/status vẫn có thể lộ timing.
28. **Key A revoked có đồng nghĩa key B bị revoked không?** Không nếu không cùng compromise scope và credentials độc lập.
29. **HMAC đúng có cho phép cross-tenant access không?** Không; authorization tách biệt.
30. **Mục tiêu error semantics là gì?** Từ chối an toàn, public response ổn định, internal diagnostics chính xác và không leak key existence.

## 28. Tài liệu tham khảo

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Khái niệm shared-secret MAC và toàn vẹn thông điệp.
- **RFC 4231 — HMAC-SHA-224/256/384/512 Test Vectors.** Known-answer tests để kiểm primitive độc lập.
- **RFC 9110 — HTTP Semantics, Authentication và 401/403/WWW-Authenticate.** Public HTTP error contract.
- **RFC 9457 — Problem Details for HTTP APIs.** Một định dạng body lỗi có thể sử dụng cho public responses.
- **RFC 9112 / RFC 9113 — HTTP/1.1 và HTTP/2.** HTTP fields, framing, proxies và duplicate/normalization boundaries.
- **RFC 3986 — URI Generic Syntax.** Percent encoding, raw/canonical path/query signing contract.
- **NIST SP 800-57 Part 1 — Recommendation for Key Management.** Key IDs, rotation, lifecycle và revoke policy.
- **OWASP Authentication Cheat Sheet.** Authentication failures và user/key enumeration risks.
- **OWASP API Security guidance.** Resource-level authorization và HTTP API security boundaries.
- **OWASP Secrets Management Cheat Sheet.** Secret isolation, rotation, provenance và log hygiene.
- **Java SE 17 API — javax.crypto.Mac, SecretKeySpec, MessageDigest.isEqual, Base64, Clock.** Java examples trong bài.
- **Spring Security Reference — AuthenticationEntryPoint, AuthenticationFilter, AuthenticationProvider, AuthenticationWebFilter.** Tích hợp authentication errors trong Servlet/WebFlux.
- **Spring Security Test / JUnit Jupiter.** Test đúng chuỗi xác thực, failure/negative cases và principal isolation.

## 29. Kết luận

**Sai key ID không phải một lỗi duy nhất.** Một header thiếu, một ID sai grammar, ID unknown, một key đã revoked, việc ký bằng secret của key khác và một registry timeout cần được **phân biệt chính xác trong nội bộ**. Tuy nhiên, đối với caller chưa authenticated, phản hồi HTTP thường phải giữ một **hình thức authentication failure nhất quán**, tránh tiết lộ key tồn tại hoặc trạng thái lifecycle; với `401` cần challenge thích hợp.

Trong HMAC request authentication, **key ID chỉ chọn đúng một credential**, còn danh tính được xác lập khi server kiểm full HMAC theo canonical method/URI/headers/raw body đã ràng buộc key ID, timestamp và nonce, sau đó bảo đảm freshness, atomic replay và trusted principal construction. Không trim/alias key ID, không quét secrets khác, không fallback khi registry unavailable và không dùng key ID prefix cấp quyền tenant. Cùng với test matrix đa tầng, monitoring đúng privacy, key rotation và gateway consistency, những quy tắc này giúp lỗi “sai key ID” được xử lý **vừa chính xác vừa không mở thêm lỗ hổng xác thực**.






