# Key ID trong audit của hệ thống xác thực HTTP request bằng HMAC

> **Chương:** Key identifier  
> **Đề bài:** Key ID trong audit  
> **Module:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request bảo vệ phương thức, URI, headers hoặc body theo hợp đồng ký. Module còn yêu cầu xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt authentication với authorization.

## 1. Vì sao Key ID phải xuất hiện trong audit?

**Key ID** (`keyId`) là **mã định danh một credential/key record**. Khi một client có nhiều shared secrets trong quá trình rotation, key ID giúp receiver chọn đúng secret để kiểm HMAC mà **không phải thử tất cả secret**.

Trong **security audit**, key ID giúp trả lời:

- Request đã được xác minh bằng **credential nào** của client?
- Client đã chuyển sang key `ACTIVE` mới hay vẫn dùng key `VERIFY_ONLY` cũ?
- Có nỗ lực gọi API bằng key bị `REVOKED` hoặc quá hạn không?
- Sau một đợt rotation, key ID nào còn có authenticated traffic?
- Có lỗi 401 do key lookup, MAC mismatch, proxy rewrite, timestamp hoặc nonce replay không?
- Audit request nối được với lịch sử **key created → activated → verify-only → revoked** nào?

Ví dụ:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Request-Id: dRGla0slwS-KGNO1VKGbyw
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k-2026-11", signature="<base64url-tag>"

{"orderId":"o-123","amount":150000}
~~~

`merchant-17` là client ID **được khai báo**, `k-2026-11` là key ID **được khai báo**. Chúng chỉ trở thành metadata được xác minh khi server tra đúng record, kiểm ownership/audience/key state, tính lại HMAC và so được full tag.

**Quy tắc quan trọng nhất:** phân biệt **`claimedKeyId`** (giá trị do người gọi cung cấp, ban đầu untrusted) và **`verifiedKeyId`** (định danh trusted key record mà MAC đã khớp). Nếu log gọi mọi giá trị từ header là “verified key”, attacker chỉ việc gửi `key_id="key-cua-nan-nhan"` với chữ ký giả để tạo bằng chứng giả rằng nạn nhân đã sử dụng key đó.

### 1.1. Key ID không phải shared secret

| Khái niệm | Vai trò | Có nên ghi audit? |
|---|---|---|
| **Claimed client ID** | Client tự khai trước xác thực | Chỉ trong vùng audit phù hợp, đánh dấu **UNVERIFIED** |
| **Claimed key ID** | Selector do client tự khai | Có thể ghi có kiểm soát, **không** đồng nghĩa key thực đã được sử dụng |
| **Verified client ID** | Principal từ key record sau MAC đúng | Có, với outcome/stage rõ |
| **Verified key ID** | Record key đã làm MAC khớp | Có, hỗ trợ điều tra/rotation |
| **Key state/version** | State từ trusted key store | Có, lưu trạng thái tại thời điểm quyết định |
| **Shared secret** | Vật liệu khóa HMAC | **Tuyệt đối không log** |
| **HMAC tag nhận/tính lại** | Chữ ký raw/encoded | Tránh lưu toàn bộ |
| **Nonce raw** | Dùng một lần; có thể hữu ích cho replay nếu lộ kèm message | Không ghi raw mặc định |
| **Authorization raw** | Chứa credentials, đôi khi cả Bearer/Basic | Không ghi nguyên field |
| **Request body** | Có thể chứa thông tin cá nhân/tài chính | Không log vào security audit mặc định |

Key ID có thể **không phải secret mật mã** nhưng vẫn là metadata nhạy cảm, vì tiết lộ inventory, tên tenant, timeline rotation hoặc cấu trúc hệ thống. Không để key ID thô trong public response hay làm metric label không giới hạn cardinality.

### 1.2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả Key ID trong audit, khác với client ID, shared secret, nonce, request/trace ID.
2. Thiết kế schema phân biệt **claimedKeyId** với **verifiedKeyId**, xác định trust boundary.
3. Theo dõi key `ACTIVE`, `VERIFY_ONLY`, `REVOKED` và rotation deadlines.
4. Ghi chính xác kết quả malformed header, lookup fail, MAC mismatch, stale timestamp, replay, authenticated, forbidden.
5. Đưa Key ID vào canonical request để ràng buộc key selector bằng chữ ký.
6. Gắn authentication event với key lifecycle/management event theo audience/client/key record.
7. Chống log injection, key enumeration, leak credentials, tampering hoặc mất audit events.
8. Triển khai demo Java 17 với HMAC, event schema, key lookup, nonce, key rotation và unit tests.
9. Hiểu audit của HMAC shared-secret **không tự bảo đảm non-repudiation**.
10. Kiểm thử gateway/proxy và phân tách audit authentication, authorization, business commit.

## 2. Threat model: ai có thể đưa Key ID vào log?

### 2.1. Claim chưa phải bằng chứng

Attacker không biết secret nhưng có thể gửi:

~~~http
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k-2026-11", signature="<tag-gia>"
~~~

Log không đúng:

~~~text
[SECURITY] verifiedKeyId=k-2026-11 principal=merchant-17 success=false
~~~

Thông tin thực sự xác nhận chỉ là **ai đó khai báo** selector đó; chưa có bằng chứng merchant 17 thực hiện request.

Audit chính xác hơn:

~~~json
{
  "eventType": "HMAC_AUTHENTICATION",
  "outcome": "MAC_MISMATCH",
  "credentialTrust": "UNVERIFIED",
  "claimedClientId": "merchant-17",
  "claimedKeyId": "k-2026-11",
  "verifiedClientId": null,
  "verifiedKeyId": null,
  "authenticated": false
}
~~~

Ví dụ có raw claims để minh họa **mức độ tin cậy**; production có thể giữ chúng trong vùng audit hạn chế, pseudonymize hoặc chỉ aggregate theo policy.

### 2.2. Các mức trust của Key ID

| Bước xử lý | Điều có thể biết | Điều không được khẳng định |
|---|---|---|
| Chưa parse Authorization | Có HTTP attempt | Chưa có selector an toàn |
| Parse thành công | Có claimed client/key IDs đúng grammar | Chưa có authenticated principal |
| Key lookup hit | Candidate key record và state từ trusted store | Chưa biết sender sở hữu secret |
| MAC khớp | Tag khớp secret của record cho message đã ký | Chưa chắc timestamp/nonce hợp lệ |
| Timestamp và nonce pass | Authentication hoàn tất, principal/key đã verify | Chưa có quyền trên resource |
| Authorization pass | Actor được phép action/resource | Chưa chứng minh business commit |
| Business commit | Có transaction/operation thực | Không có non-repudiation mặc định |

Sau **MAC đúng nhưng nonce đã dùng**, security audit có thể ghi `verifiedKeyId` với `outcome=REPLAY_REJECTED` trong vùng hạn chế, nhưng không đếm sự kiện này là **authentication success** của attempt mới. Một report chỉ có key ID và không có stage/outcome rất dễ diễn giải sai.

### 2.3. Nguy cơ log forging/injection

Nếu nhận Key ID từ request rồi nối thẳng vào log:

~~~text
X-Key-Id: key42
[AUDIT] authenticated client=admin
~~~

Attacker có thể chèn newline/quotes/control characters hoặc chuỗi rất dài để làm giả sự kiện, phá parser log hoặc tiêu tốn storage. Phải:

1. Reject CR/LF/NUL và HTTP framing không hợp lệ ở HTTP stack.
2. Validate Key ID, ví dụ `[A-Za-z0-9_-]{1,64}`.
3. Dùng structured logger/serializer có escaping, không nối raw header vào format string.
4. Đặt size/rate/cardinality limits.
5. Đánh nhãn **UNVERIFIED** cho claim, kể cả khi đúng grammar.

### 2.4. Không suy identity từ thông tin mạng

`remoteAddress` có thể là NAT/proxy; `X-Forwarded-For` có thể bị giả nếu không có trusted proxy chain; `X-Verified-Client` do client gửi phải bị strip; `X-Request-Id` do client tự chọn có thể trùng. `key_id` là **selector**, không phải proof of possession.

Trong audit nên phân biệt `edgeRequestId` (server-generated), `signedClientRequestId` (chỉ tin sau MAC), `auditEventId` (server-generated, unique per event) và `traceId` (được truyền theo trust boundary). Không ép tất cả thành một `requestId`.

## 3. Thiết kế structured audit event cho HMAC

### 3.1. Một event thành công có đủ ngữ cảnh

~~~json
{
  "schemaVersion": "hmac-auth-audit-v1",
  "eventId": "srv-example-0001",
  "occurredAt": "2026-11-28T00:00:00Z",
  "serviceAudience": "orders-api-production",
  "edgeRequestId": "edge-example-0001",
  "eventType": "HMAC_AUTHENTICATION",
  "stage": "ANTI_REPLAY_COMPLETED",
  "outcome": "AUTHENTICATED",
  "claimedClientId": "merchant-17",
  "claimedKeyId": "k-2026-11",
  "verifiedClientId": "merchant-17",
  "verifiedKeyId": "k-2026-11",
  "verifiedKeyState": "ACTIVE",
  "canonicalVersion": "hmac-key-audit-v1",
  "macAlgorithm": "HmacSHA256",
  "timestampSkewSeconds": 0,
  "nonceOutcome": "RESERVED",
  "authorization": "NOT_EVALUATED"
}
~~~

Đối với key lookup miss:

~~~json
{
  "schemaVersion": "hmac-auth-audit-v1",
  "eventType": "HMAC_AUTHENTICATION",
  "stage": "KEY_LOOKUP",
  "outcome": "KEY_NOT_FOUND",
  "claimedClientId": "merchant-17",
  "claimedKeyId": "unknown-key",
  "verifiedClientId": null,
  "verifiedKeyId": null
}
~~~

Giữ `verifiedKeyId=null` cho lookup fail, key state fail hoặc MAC mismatch. Nếu vẫn muốn ghi một candidate key record đã tìm thấy, dùng field riêng `lookupCandidateKeyId` với **trust semantics khác**; không đánh đồng nó với sender đã được verify.

### 3.2. Schema fields và độ tin cậy

| Field | Nguồn | Quy tắc |
|---|---|---|
| `schemaVersion` / `canonicalVersion` | Server config | Version ổn định |
| `eventId` | Server CSPRNG/UUID | Dedup audit ingestion |
| `occurredAt` | UTC `Clock` của server | Không lấy client timestamp làm audit time |
| `edgeRequestId` | Trusted ingress/gateway | Correlation per HTTP attempt |
| `claimedClientId` / `claimedKeyId` | Parsed request | **UNVERIFIED**, validate/limit |
| `verifiedClientId` / `verifiedKeyId` | Key record sau MAC đúng | Không set khi MAC sai |
| `keyState` | Key store server-side | Snapshot tại thời điểm quyết định |
| `serviceAudience` | Server config/key policy | Không tự tin giá trị `Host`/`X-Audience` |
| `timestampSkewSeconds` | Signed timestamp vs server wall clock | Đúng đơn vị **seconds**, tránh overflow |
| `nonceOutcome` | Atomic nonce store | `RESERVED/ALREADY_USED/UNAVAILABLE` |
| `authnOutcome` | Verifier | Theo **terminal outcome**, không suy từ HTTP status riêng |
| `authzOutcome` | Authorization engine | Event riêng với principal đáng tin |
| `durationNanos` | Monotonic elapsed measurement | Không dùng `nanoTime` làm Unix epoch |
| `clientIp` / `userAgent` | Network metadata | Có thể là untrusted/PII; thường nên hạn chế |
| `rawBodyHash` | SHA-256 raw body | Chỉ log khi có policy; hash không mặc nhiên ẩn danh |

Nên giữ **ít trường nhất đủ mục tiêu điều tra**, không dump mọi header. Body digest có thể bị đoán offline với messages thuộc domain nhỏ, nên không log hash vì tưởng rằng đó là che dữ liệu tuyệt đối.

### 3.3. Một terminal authentication event cho mỗi attempt

Bài chọn:

- Mỗi HTTP attempt tạo **một terminal authentication event** với kết quả cuối của các bước authn/anti-replay.
- Sau khi đã xác thực, bước authorization phát **một event riêng** ghi permission decision.
- Management plane phát **key lifecycle events riêng**.
- Mỗi event có `eventId` riêng; các events thuộc một attempt chia sẻ `edgeRequestId`.

Bảng diễn giải:

| Outcome | Claimed key | Verified key | Đếm authentication success? |
|---|---|---|---|
| `MALFORMED_AUTHORIZATION` | Không parse an toàn | `null` | Không |
| `KEY_NOT_FOUND` | Có, unverified | `null` | Không |
| `KEY_REVOKED` | Có, unverified | `null` | Không |
| `MAC_MISMATCH` | Có, unverified | `null` | Không |
| `TIMESTAMP_OUT_OF_WINDOW` sau MAC đúng | Có | Có thể ghi trusted key | Không |
| `REPLAY_NONCE` sau MAC đúng | Có | Có thể ghi trusted key | Không |
| `NONCE_STORE_UNAVAILABLE` sau MAC đúng | Có | Có thể ghi trusted key | Không |
| `AUTHENTICATED` | Có | **Có** | **Có** |
| `AUTHORIZATION_DENIED` | Authentication đã pass | **Có** | Authn pass; authz deny |
| `AUTHORIZED` | Authentication đã pass | **Có** | Authn và authz pass |

Nếu một dashboard đếm `MAC_VERIFIED` là authn success mà quên rằng nonce có thể replay, nó sẽ **phóng đại** số lượt xác thực thành công và có thể che giấu tấn công phát lại.

## 4. Ràng buộc Key ID vào HMAC canonical request

### 4.1. Hợp đồng ký minh họa `hmac-key-audit-v1`

Canonical request có 11 dòng:

| Dòng | Trường | Quy tắc |
|---|---|---|
| 1 | Version | Literal `hmac-key-audit-v1` |
| 2 | Audience | Literal `orders-api-production` |
| 3 | Method | `POST` |
| 4 | Raw target | `/v1/orders?mode=commit` |
| 5 | Content-Type | `application/json` canonical |
| 6 | Client ID | Giá trị `client_id` đã parse |
| 7 | **Key ID** | Giá trị `key_id` đã parse |
| 8 | Timestamp | Unix epoch **seconds** ASCII canonical |
| 9 | Nonce | 16-byte CSPRNG/Base64URL no-padding |
| 10 | Client request ID | Attempt ID đã ký |
| 11 | Body digest | SHA-256 **raw body bytes**, lowercase hex |

Nối các dòng bằng LF (`\n`), **không thêm LF cuối**, mã hóa UTF-8. Thuật toán HMAC-SHA-256 được cố định, tag đủ 32 byte và encode Base64URL without padding (43 ký tự). Không đưa raw `Authorization` chứa signature vào canonical bytes để tránh tự tham chiếu.

~~~text
hmac-key-audit-v1
orders-api-production
POST
/v1/orders?mode=commit
application/json
merchant-17
k-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
dRGla0slwS-KGNO1VKGbyw
<sha256-hex-of-exact-raw-body>
~~~

Digest và signature ở ví dụ là placeholders; khi thực tế phải tính chính xác trên bytes, và timestamp ví dụ chỉ minh họa format. Hợp đồng này **không tự nhận tương thích RFC 9421**, vốn có syntax và signature base riêng.

### 4.2. Nếu attacker đổi Key ID?

Client ký `key_id=kA`, attacker đổi thành `kB`:

- Lookup/ownership có thể fail.
- Nếu kB tồn tại nhưng secret khác, MAC không khớp.
- Vì key ID là một dòng canonical, thay key ID **làm thay message được ký**.
- Audit chỉ ghi `claimedKeyId=kB` trong attempt fail, **không** xác nhận sender đã dùng kB.
- Nếu client biết secret kB và ký request mới, đó là **một credential và một request khác**.

Đưa Key ID vào canonical bytes giúp ràng buộc selected credential và giải thích audit. Nhưng receiver vẫn phải kiểm `(audience,clientId,keyId)` ở trusted store — không chỉ tin field vì nó nằm trong message text.

### 4.3. Lookup đúng tuple, không scan mọi secret

~~~text
lookup = (
    serviceAudience,
    claimedClientId,
    claimedKeyId
)
record = trustedKeyStore.lookup(lookup)
~~~

Key ID **không mặc định global unique**. Hai tenant có thể cùng text `key-1`; audit phải gắn key ID với audience, owner và nếu cần **immutable record ID/version**. Tránh thử mọi secrets để tìm một tag khớp: việc đó gây rủi ro cross-tenant confusion, bỏ qua revoke và mở timing/key enumeration oracle.

### 4.4. Key ID không phải bằng chứng non-repudiation

Khi HMAC khớp, audit có thể xác nhận verifier đã chấp nhận MAC theo shared secret. Nhưng **shared secret có mặt ở cả sender và verifier/key custodian**, nên một HMAC tag **không chứng minh với bên thứ ba rằng chỉ riêng sender tạo message**. Nó không cung cấp non-repudiation kiểu chữ ký số bất đối xứng.

Nếu forensic đòi bằng chứng mạnh, cần kết hợp audit provenance, quản trị khóa, trusted timestamping, append-only storage và có thể chữ ký số/HSM riêng. Không dump HMAC tag hoặc secret vào log để “làm bằng chứng”.

## 5. Key rotation, revocation và timeline audit

### 5.1. Key state và usage

| Key state | Verifier | Điều audit cần phản ánh |
|---|---|---|
| `ACTIVE` | Verify bình thường | Verified usage theo key |
| `VERIFY_ONLY` | Verify đến deadline server-managed | Mức độ client còn dùng key cũ |
| `REVOKED` | Reject dù MAC có thể tính đúng | Attempts tự khai key đã revoke, **không đếm verified usage** |
| `EXPIRED` | Reject khi key quá hạn | Deadline và effective state |
| `NOT_FOUND` | Reject | Claims unverified; key ID scan/config errors |

`EXPIRED` có thể là state lưu riêng hoặc được suy ra từ `VERIFY_ONLY` cộng deadline; schema cần ghi rõ **effective state** và thời gian quyết định.

### 5.2. Management-plane lifecycle audit

Sự kiện thường gặp:

~~~text
KEY_CREATED
KEY_ACTIVATED
KEY_SET_VERIFY_ONLY
KEY_ROTATION_SCHEDULED
KEY_ROTATION_COMPLETED
KEY_REVOKED
KEY_DELETED_OR_DESTROYED
KEY_POLICY_UPDATED
KEY_ACCESS_GRANTED_OR_REMOVED
~~~

Management-plane event nên có:

| Field | Ý nghĩa |
|---|---|
| `actorType`, `actorId` | Operator/service đã được xác thực tạo thay đổi |
| `targetAudience`, `targetClientId`, `targetKeyId` | **Key bị thay đổi**, không nhất thiết key của actor |
| `operation` | Loại thay đổi |
| `previousState`, `newState` | State transition |
| `effectiveAt`, `verifyUntil` | Deadline dạng UTC instant rõ ràng |
| `changeRequestId` / `approvalId` | Liên kết ticket/phê duyệt |
| `reasonCode` | Rotate, compromised, expired, policy |
| `occurredAt`, `eventId` | Audit time/unique ID từ server |
| `outcome`, `keyStoreVersion` | Commit thực hay failed; version immutable |
| `sharedSecret` | **Không bao giờ** được ghi |

Ví dụ:

~~~json
{
  "eventType": "KEY_LIFECYCLE",
  "operation": "KEY_SET_VERIFY_ONLY",
  "targetAudience": "orders-api-production",
  "targetClientId": "merchant-17",
  "targetKeyId": "k-2026-10",
  "previousState": "ACTIVE",
  "newState": "VERIFY_ONLY",
  "verifyUntil": "2026-12-01T00:00:00Z",
  "actorType": "SERVICE_ACCOUNT",
  "actorId": "key-rotation-controller",
  "changeRequestId": "rotation-plan-42",
  "outcome": "COMMITTED"
}
~~~

Không nhập chung **actor credential** với **target key**: người vận hành thu hồi key A không có nghĩa key A tự thu hồi nó. Management audit nên liên kết IAM approvals và key-store transaction chứ không dựa vào raw HTTP claims.

### 5.3. Giám sát migration và lỗi Key ID reuse

Giả sử merchant 17 có `old=k-2026-10` (`VERIFY_ONLY`) và `new=k-2026-11` (`ACTIVE`). Chỉ **authenticated events** được dùng để tính “traffic đang sử dụng key cũ”; requests với `claimedKeyId=old` và MAC sai có thể do attacker, không phải SDK thật.

Nếu sau deadline vẫn thấy attempts `claimedKeyId=old`, đó là **dấu hiệu cần điều tra**, không phải bằng chứng xác định client chưa migrate. Kết hợp authenticated usage trước deadline, client feedback và network metadata đáng tin.

**Không tái sử dụng cùng key ID cho secret khác** trong cùng namespace nếu không có immutable version. Nếu `k-2026-11` đã chỉ secret A, rồi sau đó bị gán lại cho secret B, một log từ năm trước sẽ mơ hồ. Khi bắt buộc hỗ trợ alias, audit lưu alias **và key record/version ID immutable**. Cần giữ metadata/tombstones tương ứng audit retention, dù secret bytes đã bị destroy.

## 6. Bảo vệ audit log khỏi rò rỉ và chỉnh sửa

### 6.1. Các kênh log khác nhau

| Kênh | Mục đích | Ví dụ fields |
|---|---|---|
| Access log | Latency, route, HTTP status | Server request ID, status, route template |
| Authentication security audit | Credential misuse, replay, MAC failures | Outcome, stage, verifiedKeyId/trusted state |
| Key lifecycle audit | Ai đổi key, khi nào và vì sao | Actor, targetKeyId, prior/new state |
| Authorization audit | Ai được/không được action nào | Trusted principal, action, policy decision |
| Business ledger | Giao dịch đã commit chưa | Operation/payment ID, transaction metadata |
| Metrics | Alert xu hướng | Outcome counts, service, region; hạn chế raw key ID label |

Authentication success **không chứng minh business commit**. Điều tra tiền/đơn hàng phải ghép security audit với ledger/outbox/transaction records.

### 6.2. Dữ liệu không ghi

~~~text
NEVER LOG:
  sharedSecret
  KMS plaintext key
  raw Authorization header
  received full signature
  expected HMAC tag
  raw request body/PII
  raw nonce by default
  access token/session cookie
~~~

Nếu cần tương quan replay, có thể ghi `nonceOutcome=ALREADY_USED` và một reference được tạo bằng **keyed digest phục vụ logging riêng**, theo privacy policy; không tự coi public hash của nonce/body là ẩn danh tuyệt đối. Đừng ghi hash của secret rồi cho rằng “đã an toàn”; nguyên tắc tối thiểu hóa là ghi stable key record ID/version thay vì derived secret fingerprint.

### 6.3. Giữ integrity, availability và privacy

Một security audit có giá trị phải đảm bảo:

- **Append-only/WORM** hoặc immutability khi yêu cầu kiểm chứng lịch sử.
- Quyền ghi tách khỏi quyền xóa/sửa; audit sink/transport được xác thực và mã hóa.
- Unique `eventId`; dedup khi exporter retry, không đếm duplicate hai lần.
- Quan sát queue lag, delivery errors, backlog, dead-letter; tránh silent event loss.
- UTC wall-clock đồng bộ, có thể có sequence/monotonic offset để điều tra thứ tự.
- Retention, access controls, encryption at rest và chính sách legal hold rõ.
- Hash-chain/batch signatures **nếu** cần integrity proof cao và quản trị signing key độc lập.
- Hạn chế raw claimedKeyId trong metrics/SIEM shared để tránh key enumeration và cardinality explosion.

**Chính sách sink failure phải do hệ thống quyết định:** nếu bắt buộc audit durable trước giao dịch thì sink down phải dừng xử lý an toàn; nếu async, cần durable queue/outbox/alert và xử lý gap. Không coi `System.out.println` là security audit production.

### 6.4. Timestamp trong audit khác timestamp được ký

- `occurredAt`: server UTC wall clock (e.g. `Clock.systemUTC().instant()`).
- `signedTimestamp`: claim client, Unix epoch seconds, nằm trong HMAC canonical bytes.
- `durationNanos`: dùng `System.nanoTime()` đo thời lượng; origin không phải epoch.
- `keyEffectiveAt`: deadline từ key store server-managed, **không lấy time của client làm nguồn**.

Có thể tính skew theo seconds sau khi parse timestamp, nhưng phải tránh overflow (`Math.subtractExact` hoặc kiểm phạm vi phù hợp). Clock các verifier nodes nên đồng bộ và event-time/ingestion-time nên được phân biệt trong hệ thống phân tán.

## 7. Gateway, proxy và nối Key ID vào audit end-to-end

~~~mermaid
sequenceDiagram
    participant C as Client SDK
    participant G as Gateway / WAF
    participant V as HMAC Verifier
    participant K as Key Store
    participant N as Shared Nonce Store
    participant L as Audit Sink
    participant A as Authorization
    C->>C: keyId, canonical request, HMAC
    C->>G: Authorization + timestamp + nonce + signed request
    G->>G: Sinh edgeRequestId, reject duplicate fields
    G->>V: Preserved signed content + trusted edgeRequestId
    V->>K: Lookup audience/client/keyId
    K-->>V: Key record, state, secret
    V->>V: Verify MAC; trustedKeyId chỉ sau MAC match
    V->>V: Verify timestamp seconds
    V->>N: Atomic reserve nonce per client
    N-->>V: Reserved hoặc replay
    V->>L: Terminal authentication event
    V->>A: Principal nếu anti-replay pass
    A->>L: Authorization event riêng
~~~

### 7.1. Những biến đổi gateway cần test

| Thay đổi | Rủi ro | Biện pháp |
|---|---|---|
| Gateway sửa `key_id` hoặc `X-Key-Id` | Lookup sai, MAC fail | Không rewrite signed selector |
| Proxy chuyển giá trị key ID sang lowercase | Case-sensitive key bị đổi | Chỉ field names case-insensitive, values theo contract |
| Gateway nhận `X-Verified-Key-Id` từ client | Attacker tạo “verified” metadata giả | Strip untrusted headers, kênh nội bộ đáng tin |
| Gộp duplicate Authorization/Key-ID fields | Backend/WAF chọn khác nhau | Reject duplicate tại ingress |
| Rewrite raw URI/query/body | HMAC mismatch, forensic khó so | Chốt canonicalization và verify boundary |
| CDN cache trước verifier | Bỏ qua authn/authz | Cache policy đúng, không bypass |
| Gateway clock sai | Timeline audit sai, freshness false reject | UTC/NTP và monitoring clock skew |
| Verifier A/B có key caches khác nhau | Một node đã revoke, node kia còn verify | Key-store consistency/version/cutover |
| Nonce stores local hoặc eventual-only | Replay được accept tại nhiều nodes | Shared atomic store/fail closed |
| Debug middleware log raw Authorization | Lộ tag/metadata | Redaction từ framework/edge |
| Proxy thay signed request ID để trace | MAC fail và correlation mismatch | Tạo **edgeRequestId riêng** không rewrite signed ID |

### 7.2. Dùng nhiều loại request ID đúng mục đích

Một request đi từ client qua CDN, WAF, API gateway đến verifier và business handler. Nên tách:

- `edgeRequestId`: gateway **đáng tin tự sinh**, duy nhất per HTTP attempt.
- `signedClientRequestId`: do client gửi và được ký; chỉ trusted sau HMAC.
- `auditEventId`: riêng cho từng event, giúp dedup audit pipeline.
- `traceId`: trace context theo trust rules; có thể nhận từ client nhưng phải validate.
- `idempotencyKey`: nếu có, ổn định qua retry một logical operation, không thay nonce.

Ví dụ retry qua key rotation:

~~~text
Attempt 1: keyId=old, nonce=N1, timestamp=T1, requestId=R1, MAC=S1
Attempt 2: keyId=new, nonce=N2, timestamp=T2, requestId=R2, MAC=S2
           idempotencyKey=I giữ nguyên (nếu cùng operation)
~~~

Đây có thể là **hai lượt authentication thành công nhưng chỉ một giao dịch**. Không kết luận “duplicate payment” chỉ từ hai `verifiedKeyId` khác nhau. Nonce scope minh họa là `(audience, authenticatedClientId, nonce)`, **không chứa key ID**, để tránh reset replay protection trong rotation.


## 8. Java 17: kiểm HMAC và xuất audit có mức trust đúng

Ví dụ Java 17 sau dùng **JCA chuẩn** và bộ nhớ trong một JVM, không cần Spring/Gradle hoặc thư viện bên ngoài. Trọng tâm không phải làm HTTP middleware production mà là minh họa **quyết định khi nào một key ID có thể được gọi là verified**.

Ví dụ gồm:

- Custom `Authorization`: `HMAC-SHA256 client_id="...", key_id="...", signature="..."`, parse đúng **một** header.
- Request có method, raw target, Content-Type, timestamp **epoch seconds**, nonce 16-byte Base64URL, signed client request ID và raw body.
- Canonical HMAC `hmac-key-audit-v1` gồm 11 dòng, body SHA-256, secret 32 byte và tag 32 byte.
- `MessageDigest.isEqual` sau strict Base64URL no-padding decode (43 ký tự).
- Key lookup `(audience, claimedClientId, claimedKeyId)`, xử lý `ACTIVE`, `VERIFY_ONLY` và `REVOKED`.
- Audit sink lưu **một terminal authentication event/attempt**, claim và verified ID là fields **khác nhau**.
- Timestamp ±300 giây, nonce scope per **authenticated client**, atomic reservation bằng `ConcurrentHashMap.compute`.
- Authorization event độc lập, chỉ sử dụng authenticated principal.
- Tests MAC giả, key không tồn tại, key bị revoke, request quá cũ, nonce replay, rotate key, hai clients cùng nonce và concurrent requests.

**Lưu ý:** `InMemoryAuditSink` là demo không durable; `LocalNonceStore` chỉ atomic trong một JVM và không có cleanup nền. Production cần persistent audit sink có controls và shared atomic nonce store.

### 8.1. Mã nguồn `KeyIdAuditHmacDemo.java`

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class KeyIdAuditHmacDemo {
    private static final String AUDIENCE = "orders-api-production";
    private static final String VERSION = "hmac-key-audit-v1";
    private static final String HMAC_ALGORITHM = "HmacSHA256";
    private static final long WINDOW_SECONDS = 300L;
    private static final long NONCE_TTL_SECONDS = 660L;

    private static final Pattern AUTH_PATTERN = Pattern.compile(
            "(?i:HMAC-SHA256) "
            + "(?i:client_id)=\"([A-Za-z0-9_-]{1,64})\", "
            + "(?i:key_id)=\"([A-Za-z0-9_-]{1,64})\", "
            + "(?i:signature)=\"([A-Za-z0-9_-]{43})\"");

    private KeyIdAuditHmacDemo() {}

    // HTTP adapter phải kiểm duplicate headers và raw bytes trước đây.
    public record Request(
            String method, String rawTarget, String contentType,
            String timestamp, String nonce, String clientRequestId,
            byte[] rawBody) {
        public Request {
            if (rawBody == null) {
                throw new IllegalArgumentException("Missing body");
            }
            rawBody = rawBody.clone();
        }

        @Override
        public byte[] rawBody() {
            return rawBody.clone();
        }
    }

    public record Credential(
            String clientId, String keyId, String signature) {}

    public record KeyRef(
            String audience, String clientId, String keyId) {}

    public enum KeyState {
        ACTIVE, VERIFY_ONLY, REVOKED
    }

    // Trusted key record. Secret không nằm trong audit event.
    public record KeyRecord(
            KeyRef ref, KeyState state,
            long verifyUntilEpochSeconds, byte[] secret) {
        public KeyRecord {
            if (ref == null || state == null || secret == null
                    || secret.length != 32) {
                throw new IllegalArgumentException(
                        "Invalid demo key record");
            }
            secret = secret.clone();
        }

        @Override
        public byte[] secret() {
            return secret.clone();
        }
    }

    public record Principal(
            String clientId, String audience, String verifiedKeyId) {}

    public record NonceScope(
            String audience, String authenticatedClientId,
            String nonce) {}

    public enum Outcome {
        MALFORMED_AUTHORIZATION,
        KEY_NOT_FOUND,
        KEY_REVOKED,
        KEY_EXPIRED,
        MALFORMED_SIGNED_INPUT,
        MAC_MISMATCH,
        TIMESTAMP_OUT_OF_WINDOW,
        REPLAY_NONCE,
        NONCE_STORE_UNAVAILABLE,
        INTERNAL_VERIFICATION_ERROR,
        AUTHENTICATED
    }

    // Không có secret, signature, Authorization raw hay body.
    // Nếu used in production, sink phải áp privacy/retention policy.
    public record AuditEvent(
            String eventId, Instant occurredAt,
            String edgeRequestId, String eventType,
            String serviceAudience, String outcome,
            String claimedClientId, String claimedKeyId,
            String verifiedClientId, String verifiedKeyId,
            String lookedUpKeyState, Long timestampSkewSeconds,
            boolean macVerified) {}

    public interface AuditSink {
        void append(AuditEvent event);
    }

    // DEMO: thread-safe nhưng KHÔNG durable, KHÔNG WORM.
    public static final class InMemoryAuditSink
            implements AuditSink {
        private final ConcurrentLinkedQueue<AuditEvent> entries =
                new ConcurrentLinkedQueue<>();

        @Override
        public void append(AuditEvent event) {
            entries.add(event);
        }

        public List<AuditEvent> snapshot() {
            return List.copyOf(entries);
        }
    }

    public static final class LocalNonceStore {
        private final ConcurrentHashMap<NonceScope, Long> expiries =
                new ConcurrentHashMap<>();

        public boolean reserve(
                NonceScope scope, long nowSeconds, long ttlSeconds) {
            AtomicBoolean inserted = new AtomicBoolean(false);
            expiries.compute(scope, (key, expiry) -> {
                if (expiry != null && expiry > nowSeconds) {
                    return expiry;
                }
                inserted.set(true);
                return Math.addExact(nowSeconds, ttlSeconds);
            });
            return inserted.get();
        }
    }

    public record AuthResult(
            Outcome outcome, Principal principal,
            String edgeRequestId) {}

    // Mutable context cục bộ MỘT attempt, không chia sẻ threads.
    private static final class AuditContext {
        final String edgeRequestId;
        final Instant occurredAt;
        Credential claim;          // UNVERIFIED
        KeyRecord lookedUpRecord;  // Record tồn tại, MAC CHƯA chứng minh.
        KeyRecord macVerifiedKey;  // Chỉ set sau MAC đúng.
        Long timestampSkewSeconds;

        AuditContext(String edgeRequestId, Instant occurredAt) {
            this.edgeRequestId = edgeRequestId;
            this.occurredAt = occurredAt;
        }
    }

    public static String newId(SecureRandom rng) {
        byte[] bytes = new byte[16];
        rng.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    public static Credential parseAuthorization(List<String> values) {
        if (values == null || values.size() != 1) {
            throw new IllegalArgumentException(
                    "One Authorization field required");
        }
        String value = values.get(0);
        if (value == null || value.length() > 300) {
            throw new IllegalArgumentException("Bad Authorization length");
        }
        Matcher match = AUTH_PATTERN.matcher(value);
        if (!match.matches()) {
            throw new IllegalArgumentException(
                    "Authorization HMAC grammar mismatch");
        }
        return new Credential(
                match.group(1), match.group(2), match.group(3));
    }

    private static String identifier(String value) {
        if (value == null
                || !value.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid client/key ID");
        }
        return value;
    }

    private static String randomField(String value) {
        if (value == null
                || !value.matches("[A-Za-z0-9_-]{22}")) {
            throw new IllegalArgumentException(
                    "Expected 16-byte Base64URL identifier");
        }
        final byte[] raw;
        try {
            raw = Base64.getUrlDecoder().decode(value);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Bad random ID", ex);
        }
        if (raw.length != 16
                || !Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(raw).equals(value)) {
            throw new IllegalArgumentException("Non-canonical ID");
        }
        return value;
    }

    private static long parseEpochSeconds(String value) {
        if (value == null
                || !value.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException(
                    "Expected canonical Unix epoch seconds");
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Time overflow", ex);
        }
    }

    private static byte[] decodeTagStrict(String signature) {
        if (signature == null
                || !signature.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException("Bad signature encoding");
        }
        final byte[] tag;
        try {
            tag = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Bad Base64URL", ex);
        }
        if (tag.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(tag).equals(signature)) {
            throw new IllegalArgumentException("Non-canonical MAC tag");
        }
        return tag;
    }

    private static String canonicalContentType(String input) {
        if (input == null || input.length() > 128
                || input.chars().anyMatch(
                        c -> (c < 0x20 && c != '\t') || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        String canonical = input.trim()
                .toLowerCase(java.util.Locale.ROOT);
        if (!"application/json".equals(canonical)) {
            throw new IllegalArgumentException(
                    "Only application/json supported");
        }
        return canonical;
    }

    public static byte[] canonicalBytes(
            Request request, String clientId, String keyId)
            throws GeneralSecurityException {
        if (request == null
                || !"POST".equals(request.method())) {
            throw new IllegalArgumentException("Expected POST");
        }
        if (request.rawTarget() == null
                || !request.rawTarget().matches(
                    "/v1/orders\\?mode=(?:commit|preview)")) {
            throw new IllegalArgumentException("Bad raw target");
        }
        String client = identifier(clientId);
        String key = identifier(keyId);
        String timestamp = request.timestamp();
        parseEpochSeconds(timestamp); // Không tự đổi đơn vị.
        String nonce = randomField(request.nonce());
        String requestId = randomField(request.clientRequestId());

        byte[] body = request.rawBody();
        if (body.length > 64 * 1024) {
            throw new IllegalArgumentException("Body too large");
        }
        String bodyHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        String canonical = String.join("\n",
                VERSION,
                AUDIENCE,
                request.method(),
                request.rawTarget(),
                canonicalContentType(request.contentType()),
                client,
                key,
                timestamp,
                nonce,
                requestId,
                bodyHex);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] mac(byte[] secret, byte[] data)
            throws GeneralSecurityException {
        if (secret == null || secret.length == 0 || data == null) {
            throw new IllegalArgumentException("Bad HMAC input");
        }
        Mac engine = Mac.getInstance(HMAC_ALGORITHM);
        engine.init(new SecretKeySpec(secret, HMAC_ALGORITHM));
        return engine.doFinal(data);
    }

    public static String sign(Request r, KeyRecord key)
            throws GeneralSecurityException {
        String tag = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac(
                        key.secret(),
                        canonicalBytes(
                                r, key.ref().clientId(),
                                key.ref().keyId())));
        return "HMAC-SHA256 client_id=\""
                + key.ref().clientId()
                + "\", key_id=\""
                + key.ref().keyId()
                + "\", signature=\"" + tag + "\"";
    }

    private static boolean keyMayVerify(KeyRecord record, long now) {
        if (record == null
                || !AUDIENCE.equals(record.ref().audience())) {
            return false;
        }
        return record.state() == KeyState.ACTIVE
                || (record.state() == KeyState.VERIFY_ONLY
                    && now <= record.verifyUntilEpochSeconds());
    }

    // Chỉ một terminal authentication event cho một attempt.
    private static AuthResult finish(
            AuditContext ctx, Outcome outcome,
            AuditSink sink, SecureRandom rng) {
        Credential c = ctx.claim;
        KeyRecord found = ctx.lookedUpRecord;
        KeyRecord verified = ctx.macVerifiedKey;

        AuditEvent entry = new AuditEvent(
                newId(rng),
                ctx.occurredAt,
                ctx.edgeRequestId,
                "HMAC_AUTHENTICATION",
                AUDIENCE,
                outcome.name(),
                c == null ? null : c.clientId(),
                c == null ? null : c.keyId(),
                verified == null ? null : verified.ref().clientId(),
                verified == null ? null : verified.ref().keyId(),
                found == null ? null : found.state().name(),
                ctx.timestampSkewSeconds,
                verified != null);
        sink.append(entry);

        Principal principal = outcome == Outcome.AUTHENTICATED
                ? new Principal(
                        verified.ref().clientId(),
                        verified.ref().audience(),
                        verified.ref().keyId())
                : null;
        return new AuthResult(
                outcome, principal, ctx.edgeRequestId);
    }

    // Audit sink của demo không fail. Production phải quyết định rõ
    // fail-closed hoặc durable outbox khi audit bắt buộc.
    public static AuthResult authenticate(
            Request request, List<String> authorizationValues,
            Map<KeyRef, KeyRecord> keyStore,
            Clock clock, LocalNonceStore nonceStore,
            AuditSink auditSink, SecureRandom rng) {
        if (clock == null || auditSink == null || rng == null) {
            throw new IllegalArgumentException(
                    "Missing server-controlled dependencies");
        }
        AuditContext ctx =
                new AuditContext(newId(rng), clock.instant());

        if (request == null || keyStore == null
                || nonceStore == null) {
            return finish(
                    ctx, Outcome.MALFORMED_SIGNED_INPUT,
                    auditSink, rng);
        }

        try {
            ctx.claim = parseAuthorization(authorizationValues);
        } catch (IllegalArgumentException badHeader) {
            return finish(
                    ctx, Outcome.MALFORMED_AUTHORIZATION,
                    auditSink, rng);
        }

        KeyRef lookup = new KeyRef(
                AUDIENCE, ctx.claim.clientId(), ctx.claim.keyId());
        KeyRecord record = keyStore.get(lookup);
        ctx.lookedUpRecord = record;
        if (record == null) {
            return finish(
                    ctx, Outcome.KEY_NOT_FOUND, auditSink, rng);
        }
        if (record.state() == KeyState.REVOKED) {
            return finish(
                    ctx, Outcome.KEY_REVOKED, auditSink, rng);
        }
        long now = ctx.occurredAt.getEpochSecond();
        if (!keyMayVerify(record, now)) {
            return finish(
                    ctx, Outcome.KEY_EXPIRED, auditSink, rng);
        }

        try {
            byte[] supplied = decodeTagStrict(
                    ctx.claim.signature());
            byte[] expected = mac(
                    record.secret(),
                    canonicalBytes(request,
                            ctx.claim.clientId(),
                            ctx.claim.keyId()));
            if (!MessageDigest.isEqual(expected, supplied)) {
                return finish(
                        ctx, Outcome.MAC_MISMATCH, auditSink, rng);
            }
        } catch (IllegalArgumentException malformed) {
            return finish(
                    ctx, Outcome.MALFORMED_SIGNED_INPUT,
                    auditSink, rng);
        } catch (GeneralSecurityException failure) {
            return finish(
                    ctx, Outcome.INTERNAL_VERIFICATION_ERROR,
                    auditSink, rng);
        }

        // CHỈ từ dòng này mới được ghi verifiedKeyId!
        ctx.macVerifiedKey = record;
        try {
            long signed = parseEpochSeconds(request.timestamp());
            ctx.timestampSkewSeconds =
                    Math.subtractExact(signed, now);
            long delta = ctx.timestampSkewSeconds;
            if (delta < -WINDOW_SECONDS || delta > WINDOW_SECONDS) {
                return finish(
                        ctx, Outcome.TIMESTAMP_OUT_OF_WINDOW,
                        auditSink, rng);
            }
        } catch (IllegalArgumentException | ArithmeticException ex) {
            return finish(
                    ctx, Outcome.TIMESTAMP_OUT_OF_WINDOW,
                    auditSink, rng);
        }

        // Nonce scope không chứa keyId: replay policy xuyên rotation.
        NonceScope nonceKey = new NonceScope(
                record.ref().audience(),
                record.ref().clientId(),
                request.nonce());
        try {
            if (!nonceStore.reserve(
                    nonceKey, now, NONCE_TTL_SECONDS)) {
                return finish(
                        ctx, Outcome.REPLAY_NONCE, auditSink, rng);
            }
        } catch (RuntimeException storeUnavailable) {
            return finish(
                    ctx, Outcome.NONCE_STORE_UNAVAILABLE,
                    auditSink, rng);
        }
        return finish(ctx, Outcome.AUTHENTICATED, auditSink, rng);
    }

    // Authorization là event riêng, KHÔNG dùng claimed key ID.
    public static boolean authorizeOrder(
            AuthResult authn, String ownerFromTrustedDatabase,
            Clock clock, AuditSink sink, SecureRandom rng) {
        if (authn == null || authn.principal() == null) {
            return false;
        }
        Principal principal = authn.principal();
        boolean allowed = principal.clientId()
                .equals(ownerFromTrustedDatabase);
        sink.append(new AuditEvent(
                newId(rng),
                clock.instant(),
                authn.edgeRequestId(),
                "AUTHORIZATION",
                principal.audience(),
                allowed ? "AUTHORIZED" : "AUTHORIZATION_DENIED",
                null,
                null,
                principal.clientId(),
                principal.verifiedKeyId(),
                null,
                null,
                true));
        return allowed;
    }

    private static Request request(
            long now, String nonce, String requestId,
            String target, byte[] body) {
        return new Request(
                "POST", target, "application/json",
                Long.toString(now), nonce, requestId, body);
    }

    private static void require(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    private static void testHmacRfc4231()
            throws GeneralSecurityException {
        // RFC 4231 Test Case 1:
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0B);
        byte[] data = "Hi There".getBytes(
                StandardCharsets.US_ASCII);
        String expected =
                "b0344c61d8db38535ca8afceaf0bf12b"
              + "881dc200c9833da726e9376c2e32cff7";
        require(HexFormat.of().formatHex(mac(key, data))
                .equals(expected), "HMAC known-answer vector");
    }

    private static void testConcurrentReplay(
            Request r, String header, Map<KeyRef, KeyRecord> keys,
            Clock clock, AuditSink sink, SecureRandom rng)
            throws Exception {
        int threads = 8;
        LocalNonceStore shared = new LocalNonceStore();
        ExecutorService pool =
                Executors.newFixedThreadPool(threads);
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch begin = new CountDownLatch(1);
        List<Future<AuthResult>> answers = new ArrayList<>();
        try {
            for (int i = 0; i < threads; i++) {
                answers.add(pool.submit(() -> {
                    ready.countDown();
                    begin.await();
                    return authenticate(r, List.of(header),
                            keys, clock, shared, sink, rng);
                }));
            }
            require(ready.await(10, TimeUnit.SECONDS),
                    "Threads must be ready");
            begin.countDown();
            int accepted = 0;
            int replayed = 0;
            for (Future<AuthResult> f : answers) {
                Outcome outcome = f.get().outcome();
                if (outcome == Outcome.AUTHENTICATED) accepted++;
                if (outcome == Outcome.REPLAY_NONCE) replayed++;
            }
            require(accepted == 1, "One nonce reservation");
            require(replayed == threads - 1,
                    "All remaining attempts rejected as replay");
        } finally {
            begin.countDown();
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        testHmacRfc4231();

        SecureRandom rng = new SecureRandom();
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"),
                ZoneOffset.UTC);
        long now = clock.instant().getEpochSecond();
        InMemoryAuditSink audit = new InMemoryAuditSink();
        LocalNonceStore nonces = new LocalNonceStore();

        byte[] oldSecret = new byte[32];
        byte[] newSecret = new byte[32];
        byte[] otherSecret = new byte[32];
        rng.nextBytes(oldSecret);
        rng.nextBytes(newSecret);
        rng.nextBytes(otherSecret);

        KeyRecord oldKey = new KeyRecord(
                new KeyRef(AUDIENCE, "merchant-17", "k-old"),
                KeyState.VERIFY_ONLY, now + 120, oldSecret);
        KeyRecord newKey = new KeyRecord(
                new KeyRef(AUDIENCE, "merchant-17", "k-new"),
                KeyState.ACTIVE, 0L, newSecret);
        KeyRecord otherKey = new KeyRecord(
                new KeyRef(AUDIENCE, "merchant-42", "k-42"),
                KeyState.ACTIVE, 0L, otherSecret);
        Map<KeyRef, KeyRecord> keys = new HashMap<>();
        for (KeyRecord k : List.of(oldKey, newKey, otherKey)) {
            keys.put(k.ref(), k);
        }

        byte[] body = "{\"orderId\":\"o-123\",\"amount\":150000}"
                .getBytes(StandardCharsets.UTF_8);
        Request initial = request(
                now, newId(rng), newId(rng),
                "/v1/orders?mode=commit", body);
        String oldHeader = sign(initial, oldKey);

        // Success: verified key chỉ được log sau MAC + nonce pass.
        AuthResult first = authenticate(initial,
                List.of(oldHeader), keys, clock, nonces, audit, rng);
        require(first.outcome() == Outcome.AUTHENTICATED,
                "Key old VERIFY_ONLY may authenticate");
        require(first.principal() != null
                && "k-old".equals(first.principal().verifiedKeyId()),
                "Authenticated identity includes trusted key ID");

        // HMAC đúng nhưng nonce reused: không có auth success mới.
        AuthResult replay = authenticate(initial,
                List.of(oldHeader), keys, clock, nonces, audit, rng);
        require(replay.outcome() == Outcome.REPLAY_NONCE,
                "Exact replay rejected");
        require(replay.principal() == null,
                "Replay must not create a principal");

        // Key mới của cùng client không reset nonce namespace.
        AuthResult rotatedReplay = authenticate(initial,
                List.of(sign(initial, newKey)), keys, clock,
                nonces, audit, rng);
        require(rotatedReplay.outcome() == Outcome.REPLAY_NONCE,
                "Cross-key replay rejected");

        // Khác authenticated client: cùng nonce vẫn là namespace khác.
        AuthResult other = authenticate(initial,
                List.of(sign(initial, otherKey)), keys, clock,
                nonces, audit, rng);
        require(other.outcome() == Outcome.AUTHENTICATED,
                "Other client has separate nonce namespace");

        // Candidate key tồn tại, MAC sai -> verifiedKeyId = null.
        Request wrongMacRequest = request(
                now, newId(rng), newId(rng),
                "/v1/orders?mode=commit", body);
        String good = sign(wrongMacRequest, newKey);
        Credential goodCredential =
                parseAuthorization(List.of(good));
        byte[] wrongTag =
                decodeTagStrict(goodCredential.signature());
        wrongTag[0] ^= 1;
        String forged = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(wrongTag);
        String badHeader = "HMAC-SHA256 client_id=\"merchant-17\""
                + ", key_id=\"k-new\", signature=\"" + forged + "\"";
        AuthResult badMac = authenticate(wrongMacRequest,
                List.of(badHeader), keys, clock, nonces, audit, rng);
        require(badMac.outcome() == Outcome.MAC_MISMATCH,
                "Forged HMAC rejected");
        require(authenticate(wrongMacRequest,
                List.of(good), keys, clock, nonces, audit, rng)
                .outcome() == Outcome.AUTHENTICATED,
                "Bad MAC must not poison nonce");

        // Unknown key ID: chỉ là claim, không có verified key.
        String unknownHeader = good.replace(
                "key_id=\"k-new\"", "key_id=\"k-missing\"");
        AuthResult missingKey = authenticate(wrongMacRequest,
                List.of(unknownHeader), keys, clock, nonces, audit, rng);
        require(missingKey.outcome() == Outcome.KEY_NOT_FOUND,
                "Unknown key rejected");

        // Key đã revoked: dù biết secret để tính đúng MAC cũng fail.
        KeyRecord revoked = new KeyRecord(
                new KeyRef(AUDIENCE, "merchant-17", "k-revoked"),
                KeyState.REVOKED, 0L, newSecret);
        keys.put(revoked.ref(), revoked);
        Request revokedRequest = request(
                now, newId(rng), newId(rng),
                "/v1/orders?mode=commit", body);
        AuthResult revokedResult = authenticate(revokedRequest,
                List.of(sign(revokedRequest, revoked)),
                keys, clock, nonces, audit, rng);
        require(revokedResult.outcome() == Outcome.KEY_REVOKED,
                "Revoked key cannot authenticate");

        // MAC đúng, timestamp cũ: có MAC-verified key nhưng
        // không có authenticated principal.
        Request stale = request(
                now - 301L, newId(rng), newId(rng),
                "/v1/orders?mode=commit", body);
        AuthResult staleResult = authenticate(stale,
                List.of(sign(stale, newKey)), keys, clock,
                nonces, audit, rng);
        require(staleResult.outcome() == Outcome.TIMESTAMP_OUT_OF_WINDOW,
                "Timestamp too old must fail");
        require(staleResult.principal() == null,
                "Stale request must not create principal");

        // Malformed Authorization: không gắn trusted key ID.
        AuthResult malformed = authenticate(initial,
                List.of(oldHeader, oldHeader), keys, clock,
                nonces, audit, rng);
        require(malformed.outcome() == Outcome.MALFORMED_AUTHORIZATION,
                "Duplicate Authorization rejected");

        // MAC đúng không tự cấp quyền trên resource tenant khác.
        require(!authorizeOrder(
                first, "merchant-42", clock, audit, rng),
                "Authorization denied for another tenant");
        require(authorizeOrder(
                first, "merchant-17", clock, audit, rng),
                "Authorization allowed for owned resource");

        // Concurrent request cùng key/nonce: một AUTHENTICATED,
        // các attempt còn lại log REPLAY_NONCE riêng.
        Request racing = request(
                now, newId(rng), newId(rng),
                "/v1/orders?mode=commit", body);
        testConcurrentReplay(
                racing, sign(racing, newKey),
                keys, clock, audit, rng);

        // Assert audit semantics: invalid MAC/unknown/revoked
        // KHÔNG được gắn verifiedKeyId.
        List<AuditEvent> events = audit.snapshot();
        boolean seenBadMac = false;
        boolean seenReplayWithVerifiedKey = false;
        boolean seenAuthnSuccess = false;
        boolean seenAuthzDenied = false;
        for (AuditEvent event : events) {
            if (event.outcome().equals("MAC_MISMATCH")
                    || event.outcome().equals("KEY_NOT_FOUND")
                    || event.outcome().equals("KEY_REVOKED")
                    || event.outcome().equals(
                            "MALFORMED_AUTHORIZATION")) {
                require(event.verifiedKeyId() == null,
                        "Unverified claims must not appear verified");
            }
            if (event.outcome().equals("MAC_MISMATCH")) {
                seenBadMac = true;
            }
            if (event.outcome().equals("REPLAY_NONCE")) {
                require(event.macVerified()
                        && event.verifiedKeyId() != null,
                        "MAC verified but attempt rejected as replay");
                seenReplayWithVerifiedKey = true;
            }
            if (event.outcome().equals("AUTHENTICATED")) {
                require(event.macVerified()
                        && event.verifiedClientId() != null
                        && event.verifiedKeyId() != null,
                        "Successful event must have verified identity");
                seenAuthnSuccess = true;
            }
            if (event.outcome().equals("AUTHORIZATION_DENIED")) {
                seenAuthzDenied = true;
            }
        }
        require(seenBadMac && seenReplayWithVerifiedKey
                && seenAuthnSuccess && seenAuthzDenied,
                "Audit must contain representative outcomes");

        // Demo audit records KHÔNG có secret/HMAC/body.
        String auditText = events.toString();
        require(!auditText.contains(
                HexFormat.of().formatHex(newSecret)),
                "Audit must not contain shared secret");
        require(!auditText.contains(
                goodCredential.signature()),
                "Audit must not contain raw HMAC signature");
        require(!auditText.contains("\"orderId\""),
                "Audit must not contain raw body");

        System.out.println("PASS HMAC Key ID audit/rotation/replay tests");
    }
}
~~~

### 8.2. Cách chạy

Lưu đoạn mã vào `KeyIdAuditHmacDemo.java` rồi dùng JDK 17+:

~~~bash
javac KeyIdAuditHmacDemo.java
java KeyIdAuditHmacDemo
~~~

Kết quả kỳ vọng:

~~~text
PASS HMAC Key ID audit/rotation/replay tests
~~~

### 8.3. Test nào trực tiếp chứng minh audit trust boundary?

| Test | Hành vi | Audit kỳ vọng |
|---|---|---|
| Key cũ `VERIFY_ONLY` còn hạn, MAC đúng | Authenticated | `verifiedKeyId=k-old`, `outcome=AUTHENTICATED` |
| Exact request replay | MAC vẫn đúng, nonce đã dùng | `verifiedKeyId=k-old`, `outcome=REPLAY_NONCE`, **không có principal mới** |
| Key mới cùng client tái sử dụng nonce | MAC mới đúng nhưng replay | `verifiedKeyId=k-new` + replay outcome |
| Client khác có cùng nonce | Scope khác | `verifiedClientId=merchant-42`, authenticated riêng |
| Key có thật nhưng tag sai | MAC mismatch | `claimedKeyId=k-new`, **`verifiedKeyId=null`** |
| Key không tồn tại | Lookup fail | `claimedKeyId=k-missing`, **`verifiedKeyId=null`** |
| Key bị revoke | Key state fail | `outcome=KEY_REVOKED`, **`verifiedKeyId=null`** |
| Timestamp cũ, MAC đúng | Freshness fail | MAC-verified key có thể lưu, **nhưng không authentication success** |
| Duplicate Authorization | Parse fail | Không gắn trusted key |
| Authenticated nhưng resource khác tenant | Authorization deny | Event `AUTHORIZATION_DENIED` riêng, không đổi authn outcome |
| Tám request đồng thời cùng nonce | Atomic reserve một lần | **Một** `AUTHENTICATED`, các attempt còn lại `REPLAY_NONCE` |

### 8.4. Điều ví dụ không triển khai

- `InMemoryAuditSink` **không durable**, không mã hóa, không WORM, không hỗ trợ recovery khi process crash hoặc exporter mất kết nối. Trong thực tế phải chọn rõ **fail-closed hay durable outbox**.
- `LocalNonceStore` chỉ atomic trong **một JVM**, không có eviction nền, không kháng failover/multi-region; phải dùng shared atomic store có TTL thật.
- Demo key records ở RAM, chưa dùng KMS, key version/tombstones, audit management-plane chính thức.
- `parseAuthorization` chỉ nhận subset cú pháp custom HMAC v1; không thay HTTP parser và checks duplicate headers, request smuggling, framing, content coding ở gateway.
- `AuditEvent` là record có vài fields cho mục đích học tập; production cần schema governance, access control, retention, redaction, alerting và provenance.
- `authenticate` đo thời gian theo injected `Clock` cố định; không chứng minh production clocks đồng bộ hoặc không có timing oracle toàn pipeline.
- `authorizeOrder` chỉ kiểm resource owner string từ phía trusted database; authorization thật cần action/resource/tenant roles và policy engine.
- Test ký và verify bằng cùng canonical helper có thể cùng sai; cần **golden fixtures cross-language** và STEP 6 QA chuyên môn.
- Việc assert “không thấy secret trong string events” là **sanity check**, không chứng minh toàn bộ hệ thống log production không bao giờ leak credentials.
- Giới hạn route/body của demo để tập trung Key ID trong audit; API thật cần full canonicalization contract và kiểm thử qua HTTP/1.1, HTTP/2, gateway.


## 9. Ma trận kiểm thử audit theo Key ID

Một hệ thống có thể kiểm HMAC đúng nhưng **vẫn viết audit sai**. Do đó bộ test cần đối chiếu **kết quả xác thực** và **nội dung audit event** bằng expected độc lập.

### 9.1. Key lookup, MAC và độ tin cậy của identity

| Case | Mô tả | Auth outcome | `claimedKeyId` | `verifiedKeyId` |
|---|---|---|---|---|
| A1 | Key ACTIVE, MAC đúng, nonce mới | `AUTHENTICATED` | `k-new` | **`k-new`** |
| A2 | Key VERIFY_ONLY chưa deadline, MAC đúng | `AUTHENTICATED` | `k-old` | **`k-old`** |
| A3 | Key VERIFY_ONLY đã quá deadline | `KEY_EXPIRED` | `k-old` | **null** |
| A4 | Key REVOKED, attacker/sender biết secret cũ | `KEY_REVOKED` | `k-revoked` | **null** |
| A5 | Key ID không tồn tại | `KEY_NOT_FOUND` | `unknown` | **null** |
| A6 | Key ID thuộc client B, claim client A | Lookup reject | `key-of-b` | **null** |
| A7 | Candidate key tồn tại, tag sai byte đầu | `MAC_MISMATCH` | `k-new` | **null** |
| A8 | Candidate key tồn tại, tag sai byte cuối | `MAC_MISMATCH` | `k-new` | **null** |
| A9 | MAC đúng nhưng timestamp `now-301` | `TIMESTAMP_OUT_OF_WINDOW` | `k-new` | **Có thể là k-new**, nhưng authenticated=false |
| A10 | MAC đúng nhưng nonce đã dùng | `REPLAY_NONCE` | `k-new` | **Có thể là k-new**, nhưng authenticated=false |
| A11 | MAC đúng nhưng nonce store down | `NONCE_STORE_UNAVAILABLE` | `k-new` | **Có thể là k-new**, nhưng authenticated=false |
| A12 | Authn thành công, resource tenant khác | `AUTHENTICATED` rồi `AUTHORIZATION_DENIED` | `k-new` | **k-new** trên authn/authz, không cấp quyền |

Tại A9–A11, event có thể ghi **MAC-verified key record** nhưng **không có authenticated principal cho request được xử lý tiếp**. Nếu schema dùng `verifiedKeyId` cho cả MAC-verified failures, field `outcome` và `macVerified` là bắt buộc để tránh hiểu nhầm. Một thiết kế khác có thể dùng tên `macVerifiedKeyId` rõ hơn và chỉ dùng `authenticatedKeyId` khi toàn bộ authn/anti-replay pass.

### 9.2. Parser/header negative tests

| Request input | Kết quả | Audit |
|---|---|---|
| Không có `Authorization` | Reject | `MALFORMED_AUTHORIZATION`, không có verified ID |
| Hai Authorization fields | Reject | Không tự chọn first/last |
| Duplicate `key_id` trong auth-params | Reject | Không log một value như đã verify |
| Scheme `Bearer` hoặc `HMAC-SHA1` | Reject theo custom v1 | Không fallback secret/algorithm |
| Client/key ID chứa newline, NUL hoặc whitespace | Reject | Không đưa raw malformed text vào log |
| Key ID dài hàng nghìn ký tự | Reject trước lookup | Không tạo high-cardinality key labels |
| Key ID viết khác chữ hoa/thường | Lookup theo **đúng case-sensitive value** | Không tự lower-case ID |
| Hai `X-Timestamp` hoặc `X-Nonce` headers | Reject ở HTTP adapter | Không log MAC verified nếu chưa xác minh |
| `X-Request-Id` do client tự gắn “admin” | Reject format hoặc giữ untrusted claim | `edgeRequestId` phải do server tạo |
| Signature sai Base64URL hoặc cắt ngắn | Reject | Không log raw tag |
| Signed URI/body bị đổi qua gateway | MAC fail | Ghi canonical version và stage, không log body |

### 9.3. Integrity/retention tests dành riêng cho audit sink

1. Gửi cùng event tới audit pipeline hai lần vì exporter retry: `eventId` giúp **không double count**.
2. Cho audit queue đầy: xác nhận policy **fail closed** hoặc durable buffering đúng thiết kế, không im lặng bỏ record.
3. Ngắt mạng tới SIEM: local service không được báo đã **durably audited** nếu dữ liệu chỉ nằm trong RAM.
4. Thay đổi log file cũ: cơ chế append-only/WORM hoặc integrity verification phải phát hiện.
5. Thử truy cập audit bằng service account không có quyền: phải bị từ chối và chính hành vi này có thể được audit.
6. Gửi key ID chứa ký tự log control: không tạo được event giả hoặc phá cấu trúc JSON.
7. Thử search một claimed key ID chưa được verify: dashboard không nhầm nó với legitimate key usage.
8. Retention hết hạn: secret material có thể đã destroy, nhưng audit/metadata key record vẫn có giải nghĩa hợp lệ.
9. Key alias trỏ version khác theo thời gian: audit phải xác định được immutable record version.
10. Chuyển từ key cũ sang key mới trong multi-region: security events không được khẳng định “verified” nếu node đã nhận credential bằng state hết hiệu lực.
11. Log injection qua `X-Request-Id`, User-Agent, traceparent: field được validate/escaped và mức tin cậy được giữ.
12. Kiểm tra quyền xem `verifiedKeyId`: không để nhân viên chỉ được xem access log đồng thời xem key inventory toàn tenant.

## 10. Phân tích audit theo Key ID: phát hiện rotation và sự cố

### 10.1. Chỉ đếm authenticated usage, không đếm claimed attempts

Để biết một key cũ đang được sử dụng thật, logic truy vấn phải gần với:

~~~sql
-- Pseudocode: tên bảng/fields chỉ minh họa, không gắn DB cụ thể.
SELECT
    service_audience,
    verified_client_id,
    verified_key_id,
    COUNT(*) AS successful_authentications
FROM security_audit
WHERE event_type = 'HMAC_AUTHENTICATION'
  AND outcome = 'AUTHENTICATED'
  AND verified_key_id IS NOT NULL
  AND occurred_at >= :window_start
  AND occurred_at < :window_end
GROUP BY service_audience, verified_client_id, verified_key_id;
~~~

**Không dùng:**

~~~sql
-- Sai nghĩa: attacker tự đặt claimed_key_id của key bất kỳ.
SELECT claimed_key_id, COUNT(*)
FROM security_audit
GROUP BY claimed_key_id;
~~~

Truy vấn sai có thể vẫn hữu ích để **đếm attempts khai Key ID**, nhưng không được gắn nhãn “verified key usage”.

### 10.2. Các tín hiệu cảnh báo có ý nghĩa

| Tín hiệu | Cần điều tra | Cẩn trọng với kết luận |
|---|---|---|
| Verified usage key cũ tăng sát verify-only deadline | Client chưa migrate? SDK bị rollback? | Cần xác nhận theo client và deployment |
| Claimed attempts với key đã REVOKED tăng | Attacker có thể đang thử selector, hoặc SDK còn cũ | Chưa chứng minh attacker sở hữu secret |
| MAC mismatches tăng với claimed key hợp lệ | Sai secret, canonicalization/gateway, attack traffic | Không log expected HMAC để debug |
| KEY_NOT_FOUND bursts | Scan key ID, client dùng sai environment, đồng bộ KMS | Không tiết lộ key existence qua public 401 |
| REPLAY_NONCE tăng ngay sau SDK retry | SDK gửi lại same nonce/signature | Phân biệt retries thật và attack |
| Timestamp skew tăng ở một region | Clock drift, NTP issue, long queue delay | Không tự mở rộng replay window bừa bãi |
| Verified ID khác audience trong cùng trace | Misrouting, tenant confusion | Kiểm trusted audience key binding |
| Authenticated → AUTHORIZATION_DENIED tăng | Client bị thiếu quyền hoặc đang enumerate resources | Authn không đồng nghĩa authz |
| Audit queue lag/dropped events | Hệ thống mất khả năng điều tra | Ưu tiên kiểm integrity/availability pipeline |
| Management KEY_REVOKED không khớp data-plane policy | Cache stale, thiếu invalidate, race cutover | Cần liên kết key store version/time |

### 10.3. Hướng điều tra một request lỗi

Ví dụ support nói “merchant-17 vừa rotate từ k-old sang k-new, request 401”. Trình tự:

1. Lấy **server-generated edgeRequestId** và khoảng thời gian UTC; không dựa hoàn toàn client request ID.
2. Kiểm `eventType`, `outcome`, `stage`: malformed, lookup, MAC, freshness, replay hay authorization.
3. Nếu `KEY_NOT_FOUND`, xem **claimed key selector đã validate** trong vùng log được phép, audience/tenant mapping và environment; không thử toàn bộ secrets.
4. Nếu `MAC_MISMATCH`, kiểm canonical request contract, algorithm version, method/raw target/body digest trong **test fixture không nhạy cảm** và config gateway; không log expected HMAC.
5. Nếu `KEY_REVOKED/KEY_EXPIRED`, đối chiếu management-plane events, effective deadline và cached key-store version tại node.
6. Nếu `TIMESTAMP_OUT_OF_WINDOW`, so signed timestamp seconds với **server UTC clock**, kiểm SDK milliseconds/seconds và NTP.
7. Nếu `REPLAY_NONCE`, kiểm SDK retry, gateway auto-retry và atomic store; không bảo client gửi lại same signature.
8. Nếu `AUTHENTICATED` nhưng response là 403, đọc **authorization event** theo principal/action/resource, không đi sửa shared secret.
9. Nếu request có side effect, kiểm business ledger và idempotency operation ID trước khi cho retry.
10. Ghi incident/ticket ID và quyết định điều tra ở management audit, không thay đổi log cũ.

### 10.4. Không tạo key/secret enumeration oracle trong quá trình debug

Một API không nên trả:

~~~text
401: key merchant-17/k-2026-11 exists but signature wrong
401: key merchant-17/k-2026-12 does not exist
~~~

Những thông báo này làm lộ key inventory. External response có thể dùng mã lỗi authentication chung phù hợp policy; detailed reason ở **restricted audit**. Cùng với đó, latency path key lookup miss vs hit có thể tạo **timing oracle**; cân nhắc threat model, response uniformity và rate limits, nhưng không nhầm “cố làm mọi branch cùng thời gian” với khả năng triển khai constant-time end-to-end.

## 11. Các lỗi thiết kế audit Key ID thường gặp

1. **Ghi `keyId` raw từ request thành `verifiedKeyId` trước MAC:** cho phép attacker giả danh usage trong audit.
2. **Không phân biệt lookup candidate và MAC-verified key:** lookup hit không chứng minh sender có secret.
3. **Đếm MAC-verified replay như authentication success:** sai số liệu, che giấu replay.
4. **Đếm `claimedKeyId` là traffic của một key:** request giả làm sai rotation dashboard.
5. **Không ghi audience/client owner:** cùng text key ID của các tenant bị gộp.
6. **Tái sử dụng Key ID cho secret mới không có record version:** audit quá khứ không giải thích được.
7. **Dùng key ID làm secret hoặc log secret để đối chiếu:** lộ credential material.
8. **Log cả Authorization/HMAC tag:** tăng nguy cơ lộ dữ liệu và replay.
9. **Chỉ dùng HTTP status 401/403 mà không có stage/outcome:** khó điều tra và phân biệt authn/authz.
10. **Không ký key ID trong canonical request:** selector có thể bị thay độc lập với message.
11. **Duyệt mọi secret khi key lookup fail:** cross-tenant confusion, timing oracle, DoS.
12. **Bỏ key state/revocation:** MAC đúng toán học nhưng credential không còn được phép verify.
13. **Dùng client-provided `X-Verified-Key-Id` làm principal:** bypass trust boundary.
14. **Giữ secret fingerprint trong analytics không cần thiết:** tạo rủi ro metadata/sensitive hashes.
15. **Nối raw Key ID vào log text:** log forging, injection và parser ambiguity.
16. **Ghi client IP/traceparent như trusted identity:** proxy/NAT/spoofing làm sai bức tranh.
17. **Không bảo vệ log khỏi sửa/xóa:** kẻ tấn công có thể xóa dấu vết key abuse.
18. **Không kiểm audit sink failure:** trả thành công khi mandatory audit bị mất.
19. **Không có event ID/dedup:** exporter retry làm double count.
20. **Không đồng bộ UTC clock giữa nodes:** rotation timeline và timestamp skew sai.
21. **Metric label theo mọi claimed Key ID:** cardinality explosion do attacker.
22. **Không tách management actor khỏi target key:** sự kiện revoke diễn giải sai.
23. **Tin rằng HMAC có non-repudiation tuyệt đối:** shared secret có nhiều bên biết.
24. **Tin rằng authenticated nghĩa là authorized:** Key ID đúng không cấp quyền trên resource tenant khác.

## 12. Bài tập thực hành

**Bài 1 — Trust boundary.** Một request có `key_id=kA`, key store tìm được kA nhưng HMAC sai. Trong audit có được ghi `verifiedKeyId=kA` không? Hãy thiết kế `claimedKeyId` và `verifiedKeyId` phù hợp.

**Bài 2 — Replay.** Request đầu MAC đúng, nonce N được reserve. Attacker phát lại y nguyên. `verifiedKeyId` có thể ghi không? `AUTHENTICATED` có được ghi cho lần phát lại không? Vì sao phải có `stage` và `outcome`?

**Bài 3 — Rotation dashboard.** Trong một giờ, có 3.000 `claimedKeyId=old` attempts nhưng chỉ 20 `AUTHENTICATED` events với `verifiedKeyId=old`. Báo cáo nào phản ánh legitimate usage của key cũ?

**Bài 4 — Revocation.** Key k-old bị revoke lúc 10:00 UTC. Một client ký request `X-Timestamp`=09:59 nhưng server nhận lúc 10:01. Có được accept vì client ký thời điểm trước revoke không? Vì sao server time/key state quyết định?

**Bài 5 — Log injection.** Một key ID chứa newline và text `AUTHENTICATED admin`. Hãy chỉ ra các lớp phòng vệ: HTTP parsing, grammar, structured logging và output escaping.

**Bài 6 — Alias reuse.** Key ID `key-1` từng trỏ secret A, sau đó trỏ secret B. Đề xuất immutable key record/version ID và retention metadata để forensic hiểu các events từ hai thời điểm khác nhau.

**Bài 7 — Authn vs authz.** Client merchant A có MAC đúng, nonce mới, Key ID được verify nhưng yêu cầu sửa order của merchant B. Hãy viết hai audit events với kết quả khác nhau.

**Bài 8 — False key attribution.** Attacker gửi 1 triệu requests khai `key_id=k-victim` và MAC giả. Dashboard đếm `claimedKeyId` rồi nhắc victim rằng key bị sử dụng 1 triệu lần. Sai ở đâu? Làm thế nào báo sự kiện đúng nghĩa?

**Bài 9 — Gateway.** Một proxy rewrite `X-Key-Id`/Authorization `key_id` nhưng không ký lại. MAC sẽ ra sao? Cần ghi gì trong security audit và không được ghi gì?

**Bài 10 — Shared secret và non-repudiation.** Vì sao audit event chứa Key ID và HMAC match chưa đủ để chứng minh trước bên thứ ba rằng chỉ một tổ chức đã tạo message?

**Bài 11 — Failover.** Hai backend nodes có key state snapshots khác nhau: A đã `REVOKED`, B còn `VERIFY_ONLY`. Những sai lệch audit nào có thể xuất hiện? Đề xuất key-store consistency/TTL/cutover policy.

**Bài 12 — Audit loss.** Audit pipeline mất kết nối tới SIEM. Khi nào cần fail closed, khi nào có thể queued durable event? Chứng minh rằng event thật sự được persist hoặc đã có cơ chế retry/alert.

**Bài 13 — Java 17.** Mở rộng `AuditEvent` để có `trustedKeyRecordId` immutable và `keyPolicyVersion`. Bảo đảm trường này không được tin trước MAC success và không chứa secret.

**Bài 14 — Property test.** Sinh các candidate client/key IDs có ký tự ASCII bất thường; assert không có event `AUTHENTICATED` nếu header sai hoặc MAC không khớp. Dùng test fixtures không chứa secret production.

**Bài 15 — HMAC vs business ledger.** Hai requests retry đều authenticated bằng hai keys khác nhau nhưng cùng idempotency key và chỉ có một payment commit. Security audit nên có mấy sự kiện authn? Business ledger có mấy giao dịch?

## 13. Checklist triển khai

| Nhóm | Kiểm tra |
|---|---|
| **Key ID semantics** | Key ID là selector, không phải secret hay proof of possession |
| **Claim vs verified** | `claimedKeyId` và `verifiedKeyId` là hai fields có trust semantics rõ |
| **Client/audience** | Key lookup và audit gắn `(audience, clientId, keyId)`, không chỉ key ID text |
| **Immutable identity** | Có key record ID/version hoặc chính sách không reuse Key ID |
| **Signed binding** | Key ID, client ID, method, raw URI/query, headers, timestamp, nonce, body hash nằm trong canonical bytes |
| **Signature** | HMAC-SHA-256 full 32 byte, strict Base64URL no-pad, `MessageDigest.isEqual` |
| **Key state** | `ACTIVE`/`VERIFY_ONLY` deadline/`REVOKED` được quyết định theo trusted store/server clock |
| **Timestamp** | Unix epoch seconds canonical, skew window và overflow handling |
| **Replay** | Nonce CSPRNG, atomic per-authenticated-client namespace, TTL phủ full time window |
| **Event schema** | Version, server time, event ID, service audience, trusted correlation IDs, outcome, stage |
| **Audit accuracy** | Không coi MAC mismatch/lookup hit/replay là authenticated success |
| **Authz separation** | Event khác cho action/resource policy, không cấp quyền bằng Key ID alone |
| **Lifecycle audit** | Actor/target tách biệt, previous/new states, approval/reason, immutable key version |
| **Sensitive data** | Không log shared secret, raw Authorization, raw full signature, raw body/nonce mặc định |
| **Structured logging** | Escaping đúng, reject log injection và duplicate/malformed signed headers |
| **Audit durability** | Append-only/integrity, access control, encryption, event delivery/retry/dedup/alerts |
| **Retention/privacy** | Metadata mức tối thiểu, key ID sensitive theo policy, hạn chế cardinality |
| **Gateway** | Không rewrite signed selectors, không tin `X-Verified-Key-Id` từ Internet |
| **Operations** | Theo dõi legitimate key usage, revoked attempts, old-key migration, SIEM lag |
| **Testing** | HMAC known-answer, invalid claims, tampering, replay, concurrency, rotation, proxy, log sink failure |

## 14. Kết luận

**Key ID trong audit** không đơn giản là “ghi lại giá trị `key_id` của HTTP request”. Trong HMAC authentication, cần nhận diện **hai nguồn dữ liệu khác nhau**: `claimedKeyId` do client khai trước khi xác thực và `verifiedKeyId` lấy từ trusted key record **chỉ sau khi MAC đã khớp**. Ngay cả với MAC đúng, audit vẫn phải phân biệt **request được xác thực hoàn tất** với **request bị từ chối vì timestamp, nonce replay hoặc authorization**.

Một thiết kế có trách nhiệm sẽ ràng buộc Key ID trong canonical request, lookup secret theo đúng audience/client/key, kiểm key rotation/revocation bằng server time, reserve nonce atomically, và ghi events có **stage, outcome, trusted correlation ID, key state/version**. Log cần được bảo vệ khỏi injection, tiết lộ secret/tag, thay đổi/xóa, event loss và truy cập trái quyền. Bảng kê Key ID hỗ trợ điều tra và migration, nhưng **không biến HMAC shared-secret thành chữ ký non-repudiation** hay cấp quyền truy cập tài nguyên cho principal.

**Tài liệu tham khảo:**

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): cơ sở thuật toán HMAC và shared secret.
- [RFC 4231 — HMAC-SHA-256 Test Vectors](https://www.rfc-editor.org/rfc/rfc4231): known-answer tests, bao gồm Test Case 1.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): Authorization, methods, HTTP fields, authentication semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): framing, request parsing, duplicate fields và intermediaries.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-headers và HTTP/2-to-HTTP/1.1 mapping.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): một chuẩn ký HTTP riêng; `hmac-key-audit-v1` chỉ là hợp đồng minh họa.
- [RFC 4648 — Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL, padding và canonical encoding.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): quản lý log bảo mật, phân tích/retention/audit controls.
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): nguyên tắc quản lý vòng đời khóa.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log injection, sự kiện cần ghi và bảo vệ dữ liệu.
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): JCA HMAC-SHA-256.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256, `isEqual`.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): sinh IDs/nonce.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): UTC/fixed clocks cho audit tests.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `compute` atomic trong một JVM, không thay distributed nonce store.
- [Redis — SET](https://redis.io/docs/latest/commands/set/): tham khảo `NX`/`EX`/`PX` cho atomic nonce reservation theo datastore contract.





