# Unknown key ID: xử lý định danh khóa không tồn tại khi xác thực HMAC request

**Unknown key ID** là tình huống verifier nhận được một **key identifier** (thường là `X-Key-Id`, `kid` hoặc một tham số của `Authorization`) nhưng **không tìm thấy một khóa được phép sử dụng** cho đúng client, audience và signing contract. Đây là trường hợp **không thể xác minh HMAC bằng khóa mà request chỉ định**. Hành vi an toàn là **từ chối xác thực (fail closed)**, không tự động thử tất cả secret khác, không bỏ qua signature và không suy diễn identity từ key ID tự khai.

Bài thuộc chương **Key identifier**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request gồm method, URI, header/body theo hợp đồng; kiểm tra timestamp/nonce chống replay, key rotation, proxy/gateway và phân biệt **authentication** với **authorization**. Trọng tâm bài là **key lookup khi key ID không được nhận diện**, ranh giới tin cậy và cách xử lý lỗi an toàn, có thể vận hành.

> **Quy tắc:** `keyId` là **gợi ý tra cứu khóa do client cung cấp**, không phải bằng chứng xác thực. Chỉ sau khi server tìm đúng key record, kiểm tra policy và tính lại full HMAC tag thành công, client ID mới được coi là danh tính đã xác thực.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **missing key ID**, **malformed key ID**, **unknown key ID**, **key tồn tại nhưng chưa hiệu lực/đã hết hạn/đã thu hồi**, **sai audience/client scope**, **sai signature** và **key store unavailable**.
2. Thiết kế key lookup có namespace theo **audience + claimed client ID + key ID**, không tìm khóa bằng một chuỗi `kid` toàn cục không có ràng buộc.
3. Quyết định xử lý **unknown key ID = reject**, không fallback sang key mặc định, không brute-force thử mọi key, không cho request tự chọn algorithm hoặc secret.
4. Ràng buộc `clientId` và `keyId` trong canonical request để ngăn metadata bị thay đổi sau khi ký.
5. Thiết kế phản hồi HTTP 401 không tạo **key enumeration oracle** qua mã lỗi, thời gian, response body và log.
6. Thực hành Java 17 với `Mac`, `MessageDigest.isEqual`, strict Base64, key registry, timestamp/nonce và các test unknown/malformed/revoked/expired/rotation.
7. Đánh giá rủi ro cache, KMS/Vault outage, negative caching, multi-replica key propagation, proxy header ambiguity và phân quyền.

## 2. Key ID là gì và tại sao verifier cần nó?

Một client có thể được cấp nhiều secret theo từng giai đoạn, chẳng hạn để xoay vòng khóa mà không dừng dịch vụ:

| Client | Key ID | Secret ở phía server | Trạng thái ví dụ |
| --- | --- | --- | --- |
| `partner-42` | `key-2026-11` | Secret A (không truyền lên HTTP) | Active trong giai đoạn overlap. |
| `partner-42` | `key-2026-12` | Secret B | Active, key mới. |
| `partner-42` | `key-2026-10` | Secret C | Revoked hoặc đã hết hạn. |
| `partner-77` | `key-2026-11` | Secret D khác | Có thể hợp lệ **cho client khác**. |

Một request ví dụ:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
X-Timestamp: 1795831200
X-Nonce: 00112233445566778899aabbccddeeff
X-Content-SHA256: <64-lowercase-hex-body-digest>
X-Signature: <base64-standard-padded-hmac-sha256>

{"orderId":"ord-123","amount":50000}
~~~

`<...>` ở đây là placeholder. Nếu `X-Key-Id` đổi thành `key-2026-99` nhưng registry không có key tương ứng trong đúng scope, verifier **không biết secret nào hợp lệ** để kiểm tra chữ ký. Dù `X-Signature` có đúng 44 ký tự Base64, nó vẫn **chưa được xác thực**.

### 2.1. Key ID không phải secret

- **Key ID:** identifier dùng để chọn key record. Nó có thể xuất hiện trên wire, trong log đã được giảm thiểu và metadata vận hành theo chính sách; nó **không** đóng vai trò secret.
- **Shared secret:** vật liệu mật mã nằm ở client được cấp quyền và key manager của server. Nó **không** được gửi trong request.
- **HMAC tag:** giá trị tính từ secret + canonical request bytes. Nó có thể được gửi như signature nhưng **không chứng minh điều gì** trước khi verifier so khớp.
- **Client ID:** định danh người gửi do request khai báo, chỉ đáng tin **sau khi HMAC đúng và key được gắn với client ấy**.

Một `kid` trông “đúng định dạng” không chứng minh người gửi biết secret. Một `kid` được tìm thấy trong registry cũng **chưa** chứng minh người gửi có quyền dùng nó.

### 2.2. Key ID không nhất thiết duy nhất toàn công ty

Nhiều hệ thống cấp tên key như `v1`, `primary` hoặc `key-2026-11` cho **nhiều client**. Vì thế registry nên dùng một **locator có namespace**:

~~~text
KeyLocator = (audience, claimedClientId, keyId)

ví dụ:
  audience        = payments-api
  claimedClientId = partner-42
  keyId           = key-2026-11
~~~

Tìm thấy `key-2026-11` cho `partner-77` **không** cho phép dùng secret đó để xác minh request của `partner-42`. Tương tự, một key dành cho `payments-api` không mặc nhiên hợp lệ trên `admin-api`.

## 3. Phân loại chính xác các tình huống lỗi

Đừng gộp mọi lỗi nội bộ thành “unknown” dù phản hồi public có thể được thống nhất.

| Trường hợp | Ví dụ | Xử lý an toàn của verifier |
| --- | --- | --- |
| **Missing key ID** | Không có `X-Key-Id` | Reject: thiếu trường bắt buộc. |
| **Malformed key ID** | `../secrets/root`, chứa CR/LF, khoảng trắng, quá dài | Reject ở parser/validation, **không** tra key manager bằng input ấy. |
| **Unknown key ID** | `key-2026-99` đúng format nhưng registry không có | Reject authentication; không fallback. |
| **Known ID, wrong client** | Có `key-2026-11` cho `partner-77` nhưng request khai `partner-42` | Không có bản ghi ở **đúng locator**; reject. |
| **Known ID, wrong audience** | Key của `payments-api` đưa vào `admin-api` | Reject theo scope/audience policy. |
| **Not yet active** | Key mới chưa tới `activeFrom` | Reject theo server verify time. |
| **Expired** | `expiresAt <= now` | Reject, kể cả tag tính đúng. |
| **Revoked** | Key bị thu hồi khẩn cấp | Reject ngay khi policy có hiệu lực. |
| **Unsupported algorithm/version** | Request yêu cầu HMAC-MD5 trong contract HMAC-SHA256 | Reject; không downgrade. |
| **Bad signature** | Key tìm thấy nhưng tag không khớp | Reject; không thử key khác. |
| **Key store unavailable** | KMS/Vault/DB timeout, replica chưa đồng bộ | **Không** đánh đồng với NOT_FOUND; fail closed và xử lý lỗi hạ tầng. |

**Key record không tồn tại** và **key manager không truy cập được** là hai trạng thái khác nhau. Với outage, nếu verifier coi lỗi hạ tầng như cache miss rồi chuyển sang một secret mặc định, đó là một bypass nghiêm trọng. Không dùng `try/catch { return true; }` hoặc tự tắt authentication để duy trì availability.

### 3.1. Các lỗi nên được phân biệt nội bộ nhưng không phơi bày hết ra ngoài

Ứng dụng cần biết phân loại để **audit, alert, điều tra sự cố và hỗ trợ key rotation**. Tuy vậy, gửi ra ngoài:

~~~json
{"error":"unknown key id: key-2026-99; valid ids: key-2026-11,key-2026-12"}
~~~

là không phù hợp: response đã lộ registry và cung cấp một công cụ **enumeration**. Một phản hồi public chung, ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: HMAC-V1 realm="payments-api"
Content-Type: application/json
Cache-Control: no-store

{"error":"INVALID_AUTHENTICATION"}
~~~

có thể dùng cho unknown, revoked, expired và wrong tag trong contract này. `HMAC-V1` là **scheme ví dụ**, không phải một chuẩn phổ quát. Với lỗi key store không sẵn sàng, có thể chọn phản hồi **503 Service Unavailable** chung theo chính sách vận hành, **nhưng tuyệt đối không nhận request**. Không cần làm hỏng trải nghiệm khách hàng bằng cách giả mọi outage thành một key ID không tồn tại trong audit.

## 4. Quy trình lookup đúng: parse → scope → lookup → verify → chống replay

~~~mermaid
flowchart TD
    A["Nhận request tại trusted ingress"] --> B["Strict parse: một client ID, một key ID, một signature"]
    B --> C{"Format/size/algorithm/version đúng?"}
    C -->|Không| X["Reject authentication"]
    C -->|Có| D["Lấy audience/route từ server policy"]
    D --> E["Lookup (audience, claimed client, key ID)"]
    E --> F{"Kết quả key registry?"}
    F -->|NOT_FOUND| X
    F -->|UNAVAILABLE| O["Fail closed; lỗi hạ tầng"]
    F -->|FOUND| G{"Key active, đúng scope, không revoked?"}
    G -->|Không| X
    G -->|Có| H["Dựng canonical request từ bytes thực nhận"]
    H --> I["Tính HMAC bằng secret của CHÍNH key record"]
    I --> J{"Full HMAC tag khớp?"}
    J -->|Không| X
    J -->|Có| K["Kiểm tra timestamp + atomic nonce claim"]
    K -->|Fail| X
    K -->|Pass| L["Định danh đã xác thực, kiểm tra authorization + idempotency"]
~~~

Một số kiểm tra format/freshness không có side effect có thể diễn ra trước lookup để tiết kiệm tài nguyên. **Bất biến không thay đổi:** khi key không được nhận diện, verifier **không thể công nhận request**, không claim nonce từ một request giả và không tạo side effect nghiệp vụ.

### 4.1. Nguyên tắc lookup theo đúng locator

~~~text
locator = KeyLocator(
    serverConfiguredAudience,
    requestClaimedClientId,
    requestClaimedKeyId
)

switch keyStore.lookup(locator):
    case FOUND(keyRecord): validate key policy -> HMAC verify
    case NOT_FOUND:        reject authentication
    case UNAVAILABLE:      fail closed / service error
~~~

Lookup là thao tác **chọn ứng viên secret**. Danh tính chỉ được khẳng định khi:

1. Key record thuộc **đúng client ID/audience**.
2. Key record được phép dùng cho signing contract, algorithm, route/method và thời gian hiện tại.
3. HMAC trên **canonical method/URI/headers/body** đúng với full tag.
4. Replay guard và các điều kiện authentication khác đã được đáp ứng.

**Không** đổi `claimedClientId` thành `keyRecord.clientId` một cách vô hình nếu chúng không khớp. Không cho caller gửi cả `kid` và một secret/key material rồi tự chọn.

### 4.2. Không tìm file/KMS path bằng input thô của client

Thiết kế dễ lỗi:

~~~java
// SAI: nối key ID chưa validate trực tiếp vào path hoặc tên key trong Vault.
// String secret = readFile("/keys/" + httpHeader("X-Key-Id"));
~~~

Kẻ tấn công có thể gửi giá trị chứa `../`, Unicode lạ, dấu phân cách hoặc chuỗi cực dài. Thay vào đó:

- Validate **ID alphabet/length** trước lookup (ví dụ `[a-z0-9][a-z0-9-]{0,39}`).
- Lookup bằng **prepared query / exact map key / internal opaque record ID**, không chắp nối path, SQL hay command từ header.
- Khi dùng KMS/Vault, ánh xạ public key ID sang **trusted internal secret reference**; không cho header quyết định trực tiếp một đường dẫn KMS bất kỳ.
- Dùng rate limiting, budget cho key lookup và timeout để tránh tấn công DoS bằng nhiều key ID lạ.

## 5. Key ID và client ID phải nằm trong canonical request

Hợp đồng ví dụ **HMAC-KEY-ID-V1** ký request:

~~~text
HMAC-KEY-ID-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:1795831200
x-nonce:00112233445566778899aabbccddeeff
content-type:application/json
x-content-sha256:<64-hex-lowercase>
~~~

Đây là **contract của bài học**, không phải format HMAC chung của HTTP. Các dòng được nối bằng **LF (0x0A)**, mã hóa **UTF-8**, **không có LF cuối**.

| Thành phần | Vì sao cần ràng buộc? |
| --- | --- |
| Method `POST` | Không để chữ ký cho GET/POST bị dùng làm chữ ký cho DELETE. |
| Raw path/query | Không dùng chữ ký của tài nguyên hoặc số tiền khác. |
| Audience server-controlled | Ngăn cross-service/cross-purpose reuse khi có key chung hoặc alias. |
| **Client ID** | Không mạo danh client khác bằng metadata chưa ký. |
| **Key ID** | Ràng buộc secret/policy được chọn với đúng request. |
| Timestamp + nonce | Giới hạn replay time và phân biệt từng request. |
| Content-Type và body digest | Bảo vệ representation mà backend thực thi. |

**Chữ ký không nằm trong canonical**, vì HMAC được tạo từ canonical. `X-Signature` chỉ chứa **encoded HMAC tag**; `X-Key-Id` là metadata ký.

### 5.1. Kịch bản thay `X-Key-Id`

Client ký với key A:

~~~text
x-key-id:key-2026-11
sig = HMAC(secretA, canonical chứa key-2026-11)
~~~

Attacker sửa header thành:

~~~text
x-key-id:key-2026-12
sig giữ nguyên
~~~

Nếu server tra key B, HMAC tính lại từ canonical mới không khớp tag A. **Nếu `key-2026-12` không tồn tại, verifier phải reject ngay ở lookup.** Không nên fallback về A khi B không có: fallback xóa ý nghĩa của việc client đã chọn key ID và làm khó kiểm soát rotation.

### 5.2. Key alias và key tái sử dụng

Ngay cả khi hai key ID tạm trỏ cùng secret bytes trong một giai đoạn migration, **key ID vẫn cần ký**. Nếu không, có thể đổi ID để trượt sang policy khác mà HMAC tag không đổi. Hệ thống nên cấp key IDs ổn định, không tái sử dụng ID đã thu hồi cho **secret khác** trong cùng scope, và đặt chính sách alias rõ ràng.

## 6. Unknown key ID, key enumeration và timing side channels

Một client ngoài không nên học được danh sách key đang active bằng cách thử:

~~~text
key-2026-10 -> 401 "expired"
key-2026-11 -> 401 "bad signature"
key-2026-12 -> 401 "bad signature"
key-2026-99 -> 401 "unknown"
~~~

Nếu responses phân biệt theo key state, attacker có thể xác định key tồn tại hoặc trạng thái rotation. Dù `keyId` không phải secret, thông tin registry có thể phục vụ mục tiêu dò tìm và DoS.

### 6.1. Phản hồi public thống nhất

- Với **missing/malformed/unknown/revoked/expired/bad signature**, cân nhắc một public authentication failure chung theo contract, ví dụ `401 + WWW-Authenticate` mà **không nêu valid IDs**.
- Log nội bộ có thể phân biệt `invalid-key-id-format`, `unknown-key-id`, `key-revoked`, `key-not-active` và `signature-mismatch`, nhưng phải giảm thiểu dữ liệu có thể tái sử dụng hoặc thông tin định danh nhạy cảm.
- Rate limit theo IP/trust boundary trước authn và theo authenticated client sau authn; có thể dùng phát hiện bất thường như spike unknown IDs.
- Không đưa **raw key ID chưa kiểm soát số lượng** thành metrics label; điều đó tạo bùng nổ cardinality khi attacker gửi vô hạn giá trị khác nhau.

### 6.2. Có cần so sánh HMAC giả khi key ID lạ?

Một số thiết kế thực hiện **dummy HMAC** bằng secret cố định, **không dùng để chấp nhận request**, nhằm làm đường xử lý unknown key trông gần hơn đường bad signature:

~~~text
Nếu NOT_FOUND:
    dùng một dummy secret server-side cho thao tác tính HMAC giả
    luôn REJECT

Nếu FOUND:
    dùng secret thật, HMAC so sánh
    chỉ ACCEPT khi mọi policy đạt
~~~

Đây **không phải yêu cầu mặc định**, cũng **không** biến toàn bộ pipeline thành constant-time: key store I/O, cache hit/miss, parsing, timestamp, nonce DB và scheduler tạo khác biệt. Dummy computation còn tiêu CPU, có thể bị DoS khi attacker gửi nhiều ID lạ. Cần threat model và đo đạc thực tế trước khi áp dụng; ưu tiên **generic errors, rate limiting, giới hạn lookup và full-tag constant-time comparison**.

**Tuyệt đối không** dùng dummy secret làm key mặc định mà request không biết ID lại có thể tạo HMAC đúng và được chấp nhận.

### 6.3. `MessageDigest.isEqual` dùng ở đâu?

Khi **đã tìm đúng active key**, verifier:

~~~java
byte[] expectedTag = hmacSha256(key.secret(), canonicalBytes);
byte[] suppliedTag = strictDecodeSignature(signatureHeader);

if (expectedTag.length != 32 || suppliedTag == null ||
    suppliedTag.length != 32 ||
    !java.security.MessageDigest.isEqual(expectedTag, suppliedTag)) {
    // authentication failed
}
~~~

`MessageDigest.isEqual` giúp tránh kiểu so sánh byte kết thúc sớm theo vị trí khác nhau trong tag. Nhưng **không có phép so sánh full tag bằng secret thật khi key ID unknown**, bởi không có active secret thích hợp. Không được “thử lần lượt key A, B, C đến khi khớp” chỉ để có một tag hợp lệ.

## 7. Key rotation: unknown không phải lý do tự fallback

Key ID thường xuất hiện nhiều nhất khi **rotate shared secret**:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant V as HMAC verifier
    participant R as Key registry
    C->>V: key-2026-11 + HMAC bằng key A
    V->>R: Lookup client,key-2026-11
    R-->>V: ACTIVE A
    V-->>C: Verify theo A
    Note over C,R: Giai đoạn overlap, key B được provision
    C->>V: key-2026-12 + HMAC bằng key B
    V->>R: Lookup client,key-2026-12
    R-->>V: ACTIVE B
    V-->>C: Verify theo B
    C->>V: key-2026-99 (chưa provision)
    V->>R: Lookup client,key-2026-99
    R-->>V: NOT_FOUND
    V-->>C: Reject; không thử A/B
~~~

Một quy trình an toàn:

1. **Provision** key mới vào trusted registry (và các vùng/replica liên quan) trước khi client sử dụng.
2. Định nghĩa `activeFrom`/`expiresAt` và overlap period rõ ràng. Client chỉ sử dụng key ID mới sau khi registry sẵn sàng.
3. Verifier chọn **chính key ID được ký**, kiểm tra client/audience/route và thời gian hiệu lực dựa trên **server verify time**.
4. Monitor unknown ID spike trong migration để phát hiện deploy lệch hoặc typo; không tự fallback và che lỗi.
5. **Revoke** key cũ sau thời hạn chuyển đổi; mọi request dùng key cũ không còn hợp lệ dù HMAC tag đúng.
6. Nonce store scope theo **audience + authenticated client + nonce**, không tự reset replay history khi thay key ID.

### 7.1. Một replica có key mới, replica khác chưa có

Nếu key registry được cache cục bộ và triển khai không đồng bộ, cùng request có thể:

~~~text
Replica A: key-2026-12 FOUND -> HMAC PASS
Replica B: key-2026-12 NOT_FOUND -> authentication REJECT
~~~

Đây là lỗi **propagation/configuration**, không phải lý do để verifier B thử key A. Cần rollout có kiểm soát, version/snapshot của key registry, TTL cache phù hợp, health checks, telemetry và thông báo readiness của key mới trước khi client chuyển đổi.

### 7.2. Negative cache của unknown key ID

Key lookup có thể đắt, nên một số hệ thống cache kết quả NOT_FOUND. Nhưng cache lâu có thể khiến key **vừa provision** vẫn bị xem unknown trên một replica.

| Chiến lược | Lợi ích | Rủi ro/cách xử lý |
| --- | --- | --- |
| Không negative cache | Key mới thấy ngay khi registry cập nhật | Lookup nhiều hơn nếu bị tấn công bằng key ID lạ. |
| Negative cache TTL ngắn | Giảm tải khi một unknown ID bị lặp | Có thể reject tạm key mới; cần TTL ngắn/version invalidation. |
| Cache theo key ID **không scope** | Đơn giản | **Sai:** cùng ID có thể tồn tại cho client khác; tạo false miss. |
| Cache theo full locator | Phân tách client/audience chính xác | Vẫn cần kiểm soát stale data và cardinality. |
| Cache lỗi KMS timeout thành NOT_FOUND | Có vẻ tăng availability | **Sai:** che outage; làm state không nhất quán và delay recovery. |

**Không lưu vô hạn các unknown IDs do attacker tạo** vì negative cache bản thân có thể bị lấp đầy. Dùng bounded cache, rate limit và observability không tạo cardinality vô hạn.

## 8. Hợp đồng thực hành HMAC-KEY-ID-V1

Để có các test độc lập, ví dụ quy định:

| Yếu tố | Hợp đồng của bài |
| --- | --- |
| Service audience | `payments-api` do server chọn |
| Request method | `POST`, đúng chữ hoa, case-sensitive |
| Raw target | `/v1/payments?currency=VND`, không tự normalize query |
| Identity header | Chính xác một `X-Client-Id` |
| Key ID header | Chính xác một `X-Key-Id`, alphabet `[a-z0-9][a-z0-9-]{0,39}` |
| Signing algorithm | `HmacSHA256` do server policy quy định |
| Shared secret | Key bytes cấp từ trusted key registry; demo yêu cầu ít nhất 32 byte |
| Timestamp | Unix epoch seconds dạng ASCII chính tắc, không leading zero |
| Freshness | `now-300 <= ts <= now+60`, inclusive |
| Nonce | 16 byte CSPRNG, 32 ký tự hex lowercase, được ký |
| Body digest | `SHA256(bodyBytes)`, 64 hex lowercase |
| Signature | Base64 chuẩn padded, 44 ASCII chars = full HMAC-SHA256 32 byte |
| Key lookup | Exact `(audience, clientId, keyId)` |
| Key rotation | Chọn đúng ID đã ký, không default/fallback; key active và chưa revoked |
| Nonce guard | Atomic claim sau HMAC, chung giữa các replica; retention đủ dài |

Canonical của ví dụ là:

~~~text
HMAC-KEY-ID-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:1795831200
x-nonce:00112233445566778899aabbccddeeff
content-type:application/json
x-content-sha256:<sha256-body-hex>
~~~

`<sha256-body-hex>` là placeholder. Tên header được canonical hóa theo contract; giá trị client/key ID chỉ được phép có alphabet hợp lệ. Không đưa `X-Signature` vào canonical, và không cho proxy chỉnh path/query/body sau khi verify mà backend lại dùng representation khác.

## 9. Java 17: xử lý unknown key ID mà không fallback secret

Mã sau là một ví dụ **tự chứa** `UnknownKeyIdExample.java`, không cần framework bên ngoài:

- Client ký request với `Mac.getInstance("HmacSHA256")`, nonce từ `SecureRandom`, timestamp từ `Clock` và canonical byte UTF-8.
- Verifier kiểm tra input/signature format và timestamp, lookup **đúng key locator** trong registry giả lập; unknown ID được từ chối **trước khi claim nonce**.
- Nếu tìm thấy active key, verifier tính HMAC lại và so sánh **full 32-byte tag** với `MessageDigest.isEqual`.
- Unit tests kiểm tra unknown/malformed ID, wrong client/audience, revoked/expired/not-yet-active, bad signature, replay và rotation.

**Giới hạn demo:** `SignedRequest` chỉ là model đã parse; không phải HTTP parser có thể phát hiện duplicate field line. `Map` key registry và `ConcurrentHashMap.newKeySet()` nonce chỉ chạy trong một JVM, không có TTL/durability/distributed consistency. Production phải dùng trusted ingress, key manager, shared atomic nonce store và authorization thực.

### 9.1. Mã nguồn minh họa

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
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class UnknownKeyIdExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String AUDIENCE = "payments-api";
    private static final String METHOD = "POST";
    private static final String TARGET = "/v1/payments?currency=VND";
    private static final String CONTENT_TYPE = "application/json";
    private static final String CLIENT = "partner-42";
    private static final String OLD_ID = "key-2026-11";
    private static final String NEW_ID = "key-2026-12";
    private static final String UNKNOWN_ID = "key-2026-99";
    private static final long PAST = 300L;
    private static final long FUTURE = 60L;

    record KeyLocator(String audience, String clientId, String keyId) {}

    record KeyRecord(
        KeyLocator locator, byte[] secret,
        Instant activeFrom, Instant expiresAt, boolean revoked
    ) {}

    record SignedRequest(
        String method, String rawTarget, String clientId,
        String keyId, String timestamp, String nonce,
        String contentType, String bodyHash,
        String signature, byte[] body
    ) {}

    // Đây là lý do nội bộ phục vụ test/telemetry, KHÔNG phản hồi
    // chi tiết như vậy ra Internet.
    enum Reason {
        ACCEPTED,
        MALFORMED,
        STALE_TIMESTAMP,
        UNKNOWN_KEY_ID,
        KEY_POLICY_REJECTED,
        INVALID_SIGNATURE,
        REPLAYED,
        STORE_UNAVAILABLE
    }

    interface NonceClaims {
        boolean claim(String audience, String client, String nonce);
    }

    // DEMO: atomic chỉ trong một JVM, không có TTL hoặc durability.
    static final class LocalNonces implements NonceClaims {
        private final Set<String> used =
            ConcurrentHashMap.newKeySet();

        @Override
        public boolean claim(
                String audience, String client, String nonce) {
            // Mỗi thành phần có alphabet giới hạn ở signing contract;
            // length-prefix vẫn làm tuple rõ ràng, không bị collision.
            String k = audience.length() + ":" + audience +
                client.length() + ":" + client +
                nonce.length() + ":" + nonce;
            return used.add(k);
        }
    }

    static byte[] randomSecret() {
        byte[] secret = new byte[32];
        RNG.nextBytes(secret);
        return secret;
    }

    static String newNonce() {
        byte[] nonceBytes = new byte[16];
        RNG.nextBytes(nonceBytes);
        return HexFormat.of().formatHex(nonceBytes);
    }

    static String sha256Hex(byte[] body)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(body));
    }

    static byte[] hmacSha256(byte[] secret, String canonical)
            throws GeneralSecurityException {
        // javax.crypto.Mac có trạng thái: không chia sẻ một instance
        // giữa các request/threads không đồng bộ.
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8));
    }

    static boolean validId(String value) {
        return value != null &&
            value.matches("[a-z0-9][a-z0-9-]{0,39}");
    }

    static Long parseTimestamp(String value) {
        if (value == null ||
            !value.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException overflow) {
            return null;
        }
    }

    static boolean isFresh(long ts, long now) {
        try {
            return ts >= Math.subtractExact(now, PAST) &&
                ts <= Math.addExact(now, FUTURE);
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static String canonical(String serverAudience,
            SignedRequest req, String computedBodyHash) {
        if (!METHOD.equals(req.method()) ||
            !TARGET.equals(req.rawTarget()) ||
            !CONTENT_TYPE.equals(req.contentType()) ||
            !validId(req.clientId()) ||
            !validId(req.keyId()) ||
            parseTimestamp(req.timestamp()) == null ||
            req.nonce() == null ||
            !req.nonce().matches("[0-9a-f]{32}") ||
            computedBodyHash == null ||
            !computedBodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException(
                "Invalid signing contract"
            );
        }
        return String.join("\n",
            "HMAC-KEY-ID-V1",
            req.method(),
            req.rawTarget(),
            "audience:" + serverAudience,
            "x-client-id:" + req.clientId(),
            "x-key-id:" + req.keyId(),
            "x-timestamp:" + req.timestamp(),
            "x-nonce:" + req.nonce(),
            "content-type:" + req.contentType(),
            "x-content-sha256:" + computedBodyHash
        ); // LF UTF-8, không newline cuối.
    }

    static byte[] strictDecodeSignature(String value) {
        if (value == null ||
            !value.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] tag = Base64.getDecoder().decode(value);
            if (tag.length != 32 ||
                !Base64.getEncoder().encodeToString(tag)
                    .equals(value)) {
                return null;
            }
            return tag;
        } catch (IllegalArgumentException invalid) {
            return null;
        }
    }

    static SignedRequest sign(String audience, String client,
            String keyId, byte[] secret, Clock clientClock,
            String nonce, byte[] body)
            throws GeneralSecurityException {
        String timestamp =
            Long.toString(clientClock.instant().getEpochSecond());
        String bodyHash = sha256Hex(body);
        SignedRequest unsigned = new SignedRequest(
            METHOD, TARGET, client, keyId, timestamp, nonce,
            CONTENT_TYPE, bodyHash, "", body.clone());
        String message = canonical(audience, unsigned, bodyHash);
        String tag = Base64.getEncoder().encodeToString(
            hmacSha256(secret, message));
        return new SignedRequest(
            METHOD, TARGET, client, keyId, timestamp, nonce,
            CONTENT_TYPE, bodyHash, tag, body.clone());
    }

    static Reason verify(String serverAudience, SignedRequest request,
            Map<KeyLocator, KeyRecord> registry,
            Clock serverClock, NonceClaims nonceStore)
            throws GeneralSecurityException {
        if (request == null || request.body() == null ||
            request.body().length > 65536) {
            return Reason.MALFORMED;
        }

        byte[] suppliedTag =
            strictDecodeSignature(request.signature());
        Long signedTime = parseTimestamp(request.timestamp());
        if (suppliedTag == null || signedTime == null ||
            !validId(request.clientId()) ||
            !validId(request.keyId())) {
            return Reason.MALFORMED;
        }

        // Timestamp do client cung cấp là unsigned input đến khi
        // HMAC đúng, nhưng reject freshness sớm không có side effect.
        Instant serverNow = serverClock.instant();
        if (!isFresh(signedTime, serverNow.getEpochSecond())) {
            return Reason.STALE_TIMESTAMP;
        }

        final String message;
        try {
            String actualBodyHash = sha256Hex(request.body());
            if (!actualBodyHash.equals(request.bodyHash())) {
                return Reason.INVALID_SIGNATURE;
            }
            message = canonical(
                serverAudience, request, actualBodyHash);
        } catch (IllegalArgumentException malformed) {
            return Reason.MALFORMED;
        }

        // Không tra key bằng kid riêng lẻ; bắt buộc audience/client.
        KeyLocator locator = new KeyLocator(
            serverAudience, request.clientId(), request.keyId());
        KeyRecord key = registry.get(locator);
        if (key == null) {
            // Không thử secret/key ID khác. KHÔNG claim nonce.
            return Reason.UNKNOWN_KEY_ID;
        }

        if (!locator.equals(key.locator()) || key.revoked() ||
            key.secret() == null || key.secret().length < 32 ||
            key.activeFrom() == null || key.expiresAt() == null ||
            serverNow.isBefore(key.activeFrom()) ||
            !serverNow.isBefore(key.expiresAt())) {
            return Reason.KEY_POLICY_REJECTED;
        }

        byte[] expectedTag = hmacSha256(key.secret(), message);
        if (expectedTag.length != 32 ||
            !MessageDigest.isEqual(expectedTag, suppliedTag)) {
            return Reason.INVALID_SIGNATURE;
        }

        // Chỉ claim khi lookup đúng key + full HMAC + freshness PASS.
        try {
            return nonceStore.claim(serverAudience,
                request.clientId(), request.nonce())
                ? Reason.ACCEPTED : Reason.REPLAYED;
        } catch (RuntimeException storeFailure) {
            // Production: fail closed + hệ thống xử lý lỗi hạ tầng.
            return Reason.STORE_UNAVAILABLE;
        }
    }

    static SignedRequest withSignature(
            SignedRequest r, String changedSignature) {
        return new SignedRequest(
            r.method(), r.rawTarget(), r.clientId(), r.keyId(),
            r.timestamp(), r.nonce(), r.contentType(),
            r.bodyHash(), changedSignature, r.body());
    }

    static void check(boolean test, String explanation) {
        if (!test) {
            throw new AssertionError(explanation);
        }
    }

    static void rfc4231Vector() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        String actual = HexFormat.of().formatHex(
            hmacSha256(key, "Hi There"));
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        check(actual.equals(expected), "RFC 4231 HMAC vector");
    }

    public static void main(String[] args) throws Exception {
        rfc4231Vector();
        byte[] secretA = randomSecret();
        byte[] secretB = randomSecret();
        byte[] body =
            "{\"orderId\":\"ord-123\",\"amount\":50000}"
                .getBytes(StandardCharsets.UTF_8);

        Clock now = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"),
            ZoneOffset.UTC);
        Instant activeFrom =
            Instant.parse("2026-01-01T00:00:00Z");
        Instant activeUntil =
            Instant.parse("2027-01-01T00:00:00Z");

        KeyLocator oldRef =
            new KeyLocator(AUDIENCE, CLIENT, OLD_ID);
        KeyLocator newRef =
            new KeyLocator(AUDIENCE, CLIENT, NEW_ID);
        KeyRecord oldRecord = new KeyRecord(
            oldRef, secretA, activeFrom, activeUntil, false);
        KeyRecord newRecord = new KeyRecord(
            newRef, secretB, activeFrom, activeUntil, false);
        Map<KeyLocator, KeyRecord> registry =
            Map.of(oldRef, oldRecord, newRef, newRecord);

        String nonce = newNonce();
        SignedRequest known = sign(
            AUDIENCE, CLIENT, OLD_ID, secretA,
            now, nonce, body);

        // Client HTTP object minh họa; không gửi request ra mạng.
        HttpRequest http = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + TARGET))
            .header("Content-Type", known.contentType())
            .header("X-Client-Id", known.clientId())
            .header("X-Key-Id", known.keyId())
            .header("X-Timestamp", known.timestamp())
            .header("X-Nonce", known.nonce())
            .header("X-Content-SHA256", known.bodyHash())
            .header("X-Signature", known.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(known.body()))
            .build();
        check(METHOD.equals(http.method()), "HTTP method wrong");

        // Một key ID không tồn tại phải fail dù signer biết secret A.
        LocalNonces nonces = new LocalNonces();
        SignedRequest unknown = sign(
            AUDIENCE, CLIENT, UNKNOWN_ID, secretA,
            now, nonce, body);
        check(verify(AUDIENCE, unknown, registry, now, nonces)
                == Reason.UNKNOWN_KEY_ID,
            "Unknown key ID must not fall back to key A or B");

        // Unknown key request KHÔNG được đốt nonce của request thật.
        check(verify(AUDIENCE, known, registry, now, nonces)
                == Reason.ACCEPTED,
            "Unknown kid must not claim the nonce");
        check(verify(AUDIENCE, known, registry, now, nonces)
                == Reason.REPLAYED,
            "Known key request replay must fail");

        // Malformed ID bị reject trước lookup: không nối vào KMS path.
        SignedRequest malformed = new SignedRequest(
            METHOD, TARGET, CLIENT, "../secret", known.timestamp(),
            newNonce(), CONTENT_TYPE, known.bodyHash(),
            known.signature(), known.body());
        check(verify(AUDIENCE, malformed, registry, now,
                new LocalNonces()) == Reason.MALFORMED,
            "Unsafe key ID format must be rejected");

        // Unknown client trong cùng key ID không được dùng secret A.
        SignedRequest otherClient = sign(
            AUDIENCE, "partner-77", OLD_ID,
            secretA, now, newNonce(), body);
        check(verify(AUDIENCE, otherClient, registry, now,
                new LocalNonces()) == Reason.UNKNOWN_KEY_ID,
            "Key must be looked up in client scope");

        // Cross-audience lookup không được mượn khóa payments-api.
        check(verify("admin-api", known, registry, now,
                new LocalNonces()) == Reason.UNKNOWN_KEY_ID,
            "Cross-audience key reuse must be denied");

        // Same key ID with wrong HMAC must reject, not try new key.
        byte[] tag = strictDecodeSignature(known.signature());
        check(tag != null && tag.length == 32, "Full tag");
        tag[0] ^= 1;
        SignedRequest badHmac = withSignature(
            known, Base64.getEncoder().encodeToString(tag));
        check(verify(AUDIENCE, badHmac, registry, now,
                new LocalNonces()) == Reason.INVALID_SIGNATURE,
            "Bad signature must be rejected");

        // Key rotation: correct new ID + new secret + fresh nonce passes.
        SignedRequest rotated = sign(
            AUDIENCE, CLIENT, NEW_ID, secretB,
            now, newNonce(), body);
        check(verify(AUDIENCE, rotated, registry, now,
                new LocalNonces()) == Reason.ACCEPTED,
            "Active new key must verify");

        // Nonce namespace không phụ thuộc key ID khi rotation.
        SignedRequest reusedNonceAcrossKeys = sign(
            AUDIENCE, CLIENT, NEW_ID, secretB,
            now, nonce, body);
        check(verify(AUDIENCE, reusedNonceAcrossKeys,
                registry, now, nonces) == Reason.REPLAYED,
            "Rotation cannot reset replay history");

        // ID được tìm thấy nhưng key revoked vẫn phải reject.
        Map<KeyLocator, KeyRecord> revokedRegistry = Map.of(
            oldRef, new KeyRecord(
                oldRef, secretA, activeFrom, activeUntil, true));
        check(verify(AUDIENCE, known, revokedRegistry,
                now, new LocalNonces()) == Reason.KEY_POLICY_REJECTED,
            "Revoked key must fail");

        // Key hết hạn hoặc chưa active đều không phải unknown.
        Map<KeyLocator, KeyRecord> expired = Map.of(
            oldRef, new KeyRecord(
                oldRef, secretA, activeFrom,
                Instant.parse("2026-11-01T00:00:00Z"), false));
        check(verify(AUDIENCE, known, expired, now,
                new LocalNonces()) == Reason.KEY_POLICY_REJECTED,
            "Expired key must fail");
        Map<KeyLocator, KeyRecord> future = Map.of(
            oldRef, new KeyRecord(
                oldRef, secretA,
                Instant.parse("2026-12-01T00:00:00Z"),
                activeUntil, false));
        check(verify(AUDIENCE, known, future, now,
                new LocalNonces()) == Reason.KEY_POLICY_REJECTED,
            "Not-yet-active key must fail");

        // HMAC hợp lệ nhưng timestamp không còn fresh.
        SignedRequest stale = sign(
            AUDIENCE, CLIENT, OLD_ID, secretA,
            Clock.offset(now, Duration.ofSeconds(-301)),
            newNonce(), body);
        check(verify(AUDIENCE, stale, registry, now,
                new LocalNonces()) == Reason.STALE_TIMESTAMP,
            "Stale timestamp must fail even with known key");

        // Nonce store unavailable: fail closed, không accept.
        NonceClaims outage = (aud, client, n) -> {
            throw new IllegalStateException("Store unavailable");
        };
        SignedRequest fresh = sign(
            AUDIENCE, CLIENT, OLD_ID, secretA,
            now, newNonce(), body);
        check(verify(AUDIENCE, fresh, registry, now, outage)
                == Reason.STORE_UNAVAILABLE,
            "Nonce store outage must fail closed");
        System.out.println(
            "PASS: known/unknown/malformed key IDs, rotation and replay");
    }
}
~~~

### 9.2. Ba điểm cần chú ý trong code

**Thứ nhất**, key lookup luôn dùng:

~~~java
KeyLocator locator = new KeyLocator(
    serverAudience, request.clientId(), request.keyId());
KeyRecord key = registry.get(locator);
if (key == null) {
    return Reason.UNKNOWN_KEY_ID; // Không thử key khác.
}
~~~

**Thứ hai**, `UNKNOWN_KEY_ID` chỉ là **mã nội bộ**. HTTP boundary có thể map các lỗi authentication sang **một response 401 generic**; `STORE_UNAVAILABLE` thể hiện lỗi cơ sở hạ tầng, phải fail closed và theo dõi riêng. Không xuất enum nội bộ ra API public kèm danh sách key.

**Thứ ba**, khi unknown key ID, verifier **không gọi nonceStore.claim**. Unit test dùng cùng nonce: request giả unknown ID bị reject trước, request thật ký với known key vẫn được chấp nhận một lần. Điều này tránh dạng DoS **nonce burning** do attacker biết nonce nhưng không biết secret.

### 9.3. Những giới hạn cần bổ sung ngoài demo

- `SignedRequest` không phản ánh đầy đủ cách HTTP parser xử lý duplicate headers, obs-fold hoặc HTTP/2; production phải reject input mơ hồ **trước** tạo record.
- `Map<KeyLocator, KeyRecord>` giả lập key registry. Key manager thật có thể trả NOT_FOUND/UNAVAILABLE, có TTL cache và eventual propagation; **không** biến outage thành unknown.
- `LocalNonces` chỉ atomic trong một JVM, **không TTL**. Production cần shared atomic store giữ nonce đến hết freshness window, giới hạn retention và có durability phù hợp.
- Audience được verifier đưa vào canonical, không lấy từ một header `X-Audience` do client tự khai. Một key có thể có method/route/tenant scope bổ sung mà demo chưa thể hiện.
- Ví dụ cố định `POST /v1/payments?currency=VND`; production phải ký method/raw URI/query thực nhận và body representation backend sử dụng.
- Key material được giả lập bằng `byte[]` để giảng giải; trong thực tế sử dụng key manager/secret protection phù hợp, hạn chế lưu secret thô trong log/exception/heap dump.
- Chương trình mới kiểm tra authentication và replay. **Authorization theo tenant, resource, amount, scope** và **idempotency nghiệp vụ** phải được thêm vào endpoint thật.
- Không chạy network integration test trong bài demo; phải kiểm thử từ client tới proxy, gateway, verifier, downstream với các header thực tế.

## 10. Key store outage, cache và triển khai nhiều replica

Một production verifier thường không chỉ có một `Map` nội bộ. Nó có thể dùng database, secret manager, KMS/Vault hoặc sidecar giữ cache.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API gateway
    participant V as HMAC verifier
    participant K as Key registry
    participant N as Shared nonce store
    C->>G: Request with client ID, key ID, HMAC
    G->>V: Strict parsed request, actual body
    V->>K: Exact lookup(audience, client, key ID)
    alt NOT_FOUND
        K-->>V: No record
        V-->>C: Generic authn reject
    else UNAVAILABLE
        K-->>V: Timeout/outage
        V-->>C: Fail closed, service error
    else FOUND and active
        K-->>V: Key record + policy
        V->>V: Recompute HMAC; full tag compare
        alt Full tag valid
            V->>N: Atomic claim nonce
            N-->>V: Created or replayed
        else Invalid
            V-->>C: Generic authn reject
        end
    end
~~~

### 10.1. Key record có thể cached, nhưng policy cần nhất quán

| Vấn đề | Nguy cơ | Biện pháp |
| --- | --- | --- |
| Cache positive key quá lâu | Key revoked vẫn được chấp nhận | TTL/invalidation, revoke propagation, kill switch theo threat model. |
| Negative cache unknown quá lâu | Key mới provision bị reject | TTL ngắn/versioned invalidation, rollout readiness. |
| Cache key thiếu audience/client | Sai scope, dùng khóa nhầm | Cache theo full `KeyLocator`. |
| KMS timeout được chuyển thành null | Không phân biệt outage với NOT_FOUND | Typed lookup result, fail closed. |
| Khi lookup lỗi thử default key | Bypass/downgrade policy | Không fallback; log an toàn và cảnh báo. |
| Registry data thay giữa lookup và use | TOCTOU policy/rotation race | Dùng key record snapshot có version, định nghĩa thời điểm revoke có hiệu lực. |
| Hai region chưa đồng bộ revoke | Key đã bị thu hồi vẫn được chấp nhận ở region chậm | Stronger consistency/propagation SLA, health checks, security override. |

Key quản lý ở HSM/KMS có thể **không cho xuất raw secret**; trường hợp đó verifier dùng **API HMAC/MAC verification được cấp quyền** thay vì copy secret vào RAM, nhưng vẫn phải giữ đúng lookup/policy/canonical của bài. Không tự giả định mọi KMS đều hỗ trợ HMAC ở cùng interface.

### 10.2. Lỗi key manager không được làm giảm mức xác thực

~~~text
NOT_FOUND     -> Authentication failed
UNAVAILABLE   -> Authentication not proven; fail closed
FOUND_REVOKED -> Authentication failed
FOUND_ACTIVE  -> Compute HMAC -> compare -> nonce -> authorization
~~~

Client có thể được hướng dẫn đồng bộ lại key ID hoặc liên hệ vận hành qua **kênh hỗ trợ đã xác thực**, không đưa danh sách key hợp lệ vào response của API.

## 11. Proxy/gateway, Authorization header và parser differential

Mặc dù bài dùng `X-Key-Id` làm ví dụ, một số giao thức truyền ID trong `Authorization`:

~~~http
Authorization: HMAC-V1 client="partner-42", keyid="key-2026-11", ts="1795831200", nonce="00112233445566778899aabbccddeeff", sig="<base64-tag>"
~~~

Cách đặt **không tự làm thay đổi nguyên tắc**: verifier phải chọn **đúng một** key ID từ đúng credential đã parse và ký **chính giá trị đó** vào canonical request theo contract. Không đồng thời đọc `keyid` từ `Authorization` và `X-Key-Id` để fallback khi một cái không tồn tại.

| Tình huống | Sai lầm có thể xảy ra | Yêu cầu |
| --- | --- | --- |
| Hai `X-Key-Id` khác case | Gateway lấy field đầu, backend lấy field cuối | Reject duplicate security header tại ingress. |
| Hai auth-param `keyid` | Parser chọn tham số khác nhau | Reject duplicate sau case normalization theo grammar. |
| Proxy rewrite header/value | Canonical và key lookup không còn cùng dữ liệu | Verify tại trust boundary, chuyển dữ liệu đã xác minh an toàn. |
| HTTP/2 lowercase header names | App so sánh tên header case-sensitive | Header names case-insensitive, values theo contract. |
| Client gửi `X-Verified: true` | Backend tin header để bỏ HMAC | Strip inbound identity headers, xác thực gateway→backend. |
| Gateway có default secret nếu không tìm kid | Request unknown ID có thể được chấp nhận | **Cấm** default/fallback signing key. |
| Gateway verify, backend route khác | Chữ ký khớp trên URI khác action thật | Gắn signed method/raw URI/body với request thực thi. |
| Client ký bằng key cho audience khác | Secret có thể tồn tại ở registry khác | Không mượn key sai audience; key scope server-controlled. |

**Authorization (phân quyền)** khác với header `Authorization` và khác với **authentication**. Key ID/HMAC đúng không tự cho phép client truy cập bất kỳ tenant hoặc resource nào. Chỉ sau khi xác minh thành công, hệ thống mới áp dụng scope, ACL/ABAC/RBAC, hạn mức và policy nghiệp vụ.

## 12. Replay, timestamp và unknown key ID

Một request mang unknown key ID **không cần** tạo bản ghi nonce: nó chưa chứng minh khả năng sở hữu secret. Với request dùng known active key:

1. Parse timestamp theo contract (ví dụ Unix epoch seconds ASCII thập phân).
2. Dùng server clock kiểm tra `now-300 <= ts <= now+60`; hai biên inclusive.
3. Tính lại canonical bytes gồm method, raw URI/query, signed headers, **client ID + key ID**, timestamp, nonce và body digest.
4. Dùng đúng shared secret của key record để tính HMAC-SHA256, strict decode 32-byte tag, so sánh bằng `MessageDigest.isEqual`.
5. **Sau HMAC hợp lệ**, claim nonce trong shared atomic store; namespace nên theo **audience + authenticated client + nonce**, không key ID.
6. Tiếp tục **authorization** và **idempotency** cho request có side effect.

**TTL nonce:** nếu past window `P=300` giây, future tolerance `F=60` giây, một timestamp có thể fresh trong khoảng `[ts-F, ts+P]` — kéo dài **360 giây**. Nonce phải được giữ ít nhất tới **`ts+P+margin`**, hoặc relative TTL bảo thủ **`P+F+margin`** kể từ claim, chẳng hạn 370 giây với margin 10 giây theo giả định clock. Không xóa nonce sớm hoặc cho phép hai replica claim cùng nonce.

### 12.1. Retry trong key rotation

Một client có thể retry **cùng ý định nghiệp vụ** bằng key ID mới, timestamp mới, nonce mới và signature mới. HMAC/nonce có thể hợp lệ, nhưng cần **Idempotency-Key đã ký** để tránh side effect lặp. Nếu client chỉ đổi key ID mà tái sử dụng nonce đã claim, nonce guard nên reject trong cùng client/audience retention window.

### 12.2. Key bị thu hồi rồi request cũ được phát lại

Nếu key bị revoke sau khi request được ký, verifier phải áp dụng **key policy tại server verification time** theo contract. Request cũ dù HMAC từng đúng không được “hồi sinh” chỉ bằng timestamp trước khi revoke. Timestamp của client là dữ liệu đã ký nhưng không phải nguồn quyết định key hiện còn cấp quyền.

## 13. Ma trận kiểm thử Unknown key ID

Tách **internal diagnostic** và **HTTP public response**. Trong ví dụ Java, `Reason` có nhiều mã; production có thể trả cùng generic 401 cho lỗi authentication để tránh lộ key registry.

| Ca thử | Thao tác | Kết quả nội bộ và hành vi bảo mật |
| --- | --- | --- |
| Valid key | ID tồn tại, active, đúng client/audience, HMAC đúng | ACCEPT nếu freshness/nonce và policy đạt. |
| Missing key ID | Bỏ `X-Key-Id` | Reject malformed/missing, không fallback. |
| Malformed path-like ID | `../secret` | Reject trước key lookup. |
| ID quá dài | Chuỗi 10.000 ký tự | Reject/size limit trước key store. |
| ID khác case | `KEY-2026-11` khi policy lowercase | Reject format, không âm thầm sửa. |
| **Unknown ID đúng format** | `key-2026-99` | NOT_FOUND, reject, không thử A/B. |
| Typo tại client | `key-2026-1l` thay `key-2026-11` | NOT_FOUND; log an toàn, hướng dẫn qua kênh hỗ trợ. |
| Same ID, wrong client | Request `partner-77` dùng ID của `partner-42` | Không có đúng locator; reject. |
| Same ID, wrong audience | Key payments dùng trên admin service | Reject theo registry scope. |
| Known ID, wrong secret | Tính HMAC bằng secret B nhưng khai ID A | BAD_HMAC, không thử B. |
| Known ID, signature sai byte cuối | Full 32-byte tag nhưng sai byte 31 | BAD_HMAC, không so prefix. |
| Unknown ID, fake signature | Base64 full-tag hợp format nhưng không có key record | Reject, không claim nonce. |
| Invalid MAC, known nonce | Attacker cố đốt nonce của request thật | Reject và nonce vẫn chưa được claim. |
| Missing/duplicate header | Hai `X-Key-Id` hoặc nhiều auth-param `keyid` | Reject tại trusted ingress. |
| Known key expired | `serverNow >= expiresAt` | Reject key policy dù HMAC đúng. |
| Key not yet active | `serverNow < activeFrom` | Reject theo key policy. |
| Known key revoked | Record revoked | Reject ngay theo policy. |
| New key pre-provisioned | `key-2026-12` có active record | HMAC hợp lệ bằng secret mới được chấp nhận. |
| Client đổi ID trước rollout | Replica chưa có key mới | Reject; sửa rollout/propagation, không fallback. |
| Negative cache stale | Key mới có trong registry nhưng cache vẫn NOT_FOUND | Phát hiện và invalidation/TTL phù hợp. |
| KMS timeout | Registry không trả kết quả xác định | FAIL CLOSED; không coi là known/default. |
| Registry outage với fallback | Code sử dụng test/default key | **Lỗi nghiêm trọng**; không cho accept. |
| Enumeration | Thử hàng nghìn key IDs | Public errors generic; rate limit và metrics bounded. |
| Key ID injection | Đưa ký tự path/SQL/CRLF | Reject format và dùng lookup an toàn. |
| Rotation reuse nonce | Dùng key mới nhưng nonce đã claim qua key cũ | REPLAYED, không mở lại namespace. |
| Timestamp quá hạn | Unknown hoặc known key nhưng timestamp ngoài window | Reject; không claim. |
| Replay nguyên request | Known key, signature vẫn đúng, nonce trùng | Atomic nonce store reject. |
| Proxy đổi raw path/query | Header key đúng nhưng request thực thi khác | HMAC/route policy reject. |
| Missing authorization | HMAC valid của client nhưng client thiếu quyền tenant | Authentication có thể PASS, authorization DENY. |

### Câu hỏi tự kiểm tra

1. Vì sao `key-2026-99` đúng format nhưng unknown không cho phép verifier “thử các key còn lại cho đến khi khớp”?
2. Vì sao `KeyLocator(audience, clientId, keyId)` an toàn hơn tìm secret bằng mỗi `keyId` khi key ID không duy nhất toàn hệ thống?
3. Khi KMS timeout, vì sao không được coi đó là `NOT_FOUND` rồi sử dụng default secret?
4. Khi unknown ID trả 401 giống bad HMAC, việc đó có tự khiến pipeline constant-time không? Vì sao?
5. Một key được tìm thấy nhưng revoked khác gì với unknown ID về audit? Cả hai cần xử lý thế nào ở public API?
6. Nếu một request unknown ID có nonce trùng với request thật, tại sao không được claim nonce ngay khi nhận header?
7. Vì sao key ID phải nằm trong canonical kể cả khi hai key ID đang trỏ tới cùng secret bytes trong giai đoạn migration?
8. Một ID chỉ tồn tại trên replica A nhưng chưa tới replica B nên được xử lý như thế nào mà không làm giảm bảo mật?
9. Vì sao key ID hợp lệ và HMAC đúng vẫn chưa đủ để cấp quyền thanh toán cho tenant khác?

## 14. Checklist triển khai

- [ ] Xác định **format, max length và signed location** của key ID (`X-Key-Id` hoặc auth-param `keyid`) trong API contract; không hỗ trợ fallback header ngầm định.
- [ ] Reject **missing/malformed/duplicate key ID** ở trusted ingress, cả khi header name khác case hoặc auth-param lặp.
- [ ] Validate key ID trước lookup, không nối raw header vào file path, SQL, command hoặc arbitrary Vault/KMS reference.
- [ ] Dùng `KeyLocator(audience, claimedClientId, keyId)`; audience do server policy chọn, client ID vẫn là claim đến khi HMAC đúng.
- [ ] Tách lookup result **FOUND / NOT_FOUND / UNAVAILABLE**, không biến KMS outage thành NOT_FOUND và không nhận request khi store lỗi.
- [ ] **Unknown ID → reject authentication**. Không dùng default key, thử mọi secret, auto-enroll, auto-create key hoặc downgrade algorithm.
- [ ] Ràng buộc client ID, key ID, audience, method, raw URI/query, signed headers và body digest trong canonical request theo hợp đồng.
- [ ] Kiểm tra key record activeFrom/expiresAt/revoked, algorithm, audience, route scope và trạng thái client ở server verification time.
- [ ] Strict decode full HMAC-SHA256 tag 32 byte; dùng `MessageDigest.isEqual`, không so prefix hoặc Base64 text như primitive mật mã.
- [ ] Phản hồi authentication lỗi **tổng quát**, không tiết lộ danh sách key, key state hoặc secret; logging/metrics nội bộ không chứa dữ liệu nhạy cảm/high-cardinality raw IDs.
- [ ] Có rate limiting, bounds cho key lookup và phương án xử lý side-channel theo threat model; không đánh đồng generic status với constant-time.
- [ ] Key rotation có provision-before-use, overlap/revoke, readiness, version/TTL cache và kiểm soát negative cache stale.
- [ ] Kiểm tra signed timestamp freshness và claim nonce **sau HMAC hợp lệ** trong shared atomic store có TTL đủ dài; giữ namespace ổn định qua key rotation.
- [ ] Gateway/backend xác thực kênh nội bộ, chặn direct bypass và forwarded identity headers giả, bảo toàn signed method/path/query/body.
- [ ] Sau khi HMAC và replay guard PASS, **authorization** theo tenant/action/resource và **idempotency** cho side effect vẫn là bắt buộc.
- [ ] Có unit/integration tests cho unknown, malformed, duplicate, wrong client/audience, bad signature, revoked/expired, rotation propagation, key store timeout, replay, proxy và cache invalidation.

**Kết luận:** **Unknown key ID** không phải một ngoại lệ cho phép bỏ qua HMAC hay tự đoán secret thay thế. Nó là bằng chứng rằng verifier **chưa có khóa hợp lệ được phép dùng cho chính request này**, vì vậy phải **từ chối an toàn**, không claim nonce và không thực hiện nghiệp vụ. Một hệ thống tốt còn phải phân biệt lỗi key registry với ID thực sự không tồn tại, ngăn enumeration, vận hành rotation/cache đúng, ký key ID trong canonical và kiểm tra authorization sau khi xác thực thành công.
