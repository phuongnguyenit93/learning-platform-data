# Audit secret access trong hệ thống xác thực HTTP request bằng HMAC

> **Chương:** Secret management  
> **Đề bài:** Audit secret access  
> **Phạm vi module:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request bảo vệ phương thức, URI, header hoặc body; xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền.

## 1. Audit secret access là gì và vì sao cần thiết?

Trong HMAC request authentication, **shared secret** là giá trị bí mật mà client gửi request và server xác minh đều có thể sử dụng để tạo tag HMAC. Nếu một kẻ tấn công lấy được secret, họ có thể **tạo request mới** với timestamp và nonce mới, tính HMAC đúng rồi gửi như một client có credential hợp lệ. Vì thế hệ thống cần biết **ai có thể lấy secret, ai đã lấy, từ phiên bản nào, qua đường nào, vào lúc nào và kết quả ra sao**.

**Audit secret access** là việc ghi dấu vết bảo mật về những hành động truy cập, quản lý hoặc sử dụng secret, chẳng hạn:

- Workload gọi Secret Manager để lấy **plaintext shared secret**.
- Workload gọi KMS `Decrypt`/`Unwrap` để lấy bí mật từ encrypted blob.
- Ứng dụng đọc **key metadata** (owner/state/secret version) nhưng chưa đọc plaintext.
- Verifier dùng secret **đã cache** trong RAM để tính HMAC.
- IAM/KMS từ chối một lệnh đọc secret do thiếu quyền.
- Operator chạy break-glass, automation rotate hoặc revoke key.
- Credential material bị export/backup/restore hoặc secret version bị destroy.
- Audit sink gặp lỗi, queue bị chậm hoặc log được chuyển tới kho forensic lâu dài.

Audit cần trả lời: **ai là actor**, **target/version nào**, **operation và purpose gì**, **decision/outcome**, **server time và correlation**, **sự kiện xuất phát từ platform hay application** và **dữ liệu có được lưu bền vững/tamper-evident không**.

**Audit không thay thế IAM hoặc kiểm tra HMAC.** Một log `SECRET_READ_ALLOWED` chỉ mô tả một thao tác đã được cho phép; nó không chứng minh request HTTP cụ thể đã MAC match. Một request HMAC đúng không chứng minh ai là người trực tiếp gọi Secret Manager.

### 1.1. Ví dụ hai identity rất khác nhau

~~~text
Client merchant-17
  -> gửi signed POST /v1/orders?mode=commit
     Authorization: HMAC-SHA256 client_id="merchant-17",
                    key_id="k-2026-11", signature="..."
     X-Timestamp: 1795824000
     X-Nonce: b75sZVQmhTBcfnX-bNbGqw
  -> API Gateway
  -> HMAC Verifier chạy với identity svc-hmac-verifier-prod
        |
        +-- Lookup key record theo audience/client/key ID
        +-- Secret Manager GetSecretValue (cache miss)
        |     actorPrincipal=svc-hmac-verifier-prod
        |     targetSecretVersion=secret-record-17/v7
        +-- Compute HMAC-SHA256
        +-- Check signed timestamp, atomic nonce reserve
        +-- Authenticated principal=merchant-17
  -> Authorization: merchant-17 được phép action/resource?
~~~

Sự kiện **Secret Manager access** có actor là **workload `svc-hmac-verifier-prod`**, không phải tự động là `merchant-17`. Merchant chỉ là **HMAC client** được khai báo trong request trước khi MAC khớp, còn `verifiedClientId=merchant-17` chỉ được thiết lập sau xác thực. Một request sai MAC vẫn có thể khiến verifier **đọc candidate secret để thử MAC**; Secret Manager access event lúc đó vẫn là sự kiện thật của workload.

Ngược lại, nhiều request HMAC có thể sử dụng cùng secret **đã cache** mà không có API call Secret Manager mới; log platform không đếm mọi lần secret được dùng trong process.

### 1.2. Các lớp dấu vết khác nhau

| Lớp | Câu hỏi | Điều không thể kết luận chỉ từ lớp đó |
|---|---|---|
| **Secret access audit** | Workload/human nào đọc, unwrap, quản lý secret? | Bao nhiêu signed HTTP requests hợp lệ |
| **HMAC authentication audit** | Message nào có MAC/freshness/nonce pass? | Ai đã gọi Secret Manager hay được quyền business |
| **Authorization audit** | Principal nào được phép action/resource/tenant nào? | Giao dịch thực sự commit chưa |
| **Business ledger** | Side effect nào được ghi bền vững? | Có ai đọc secret ở background hay không |
| **Metrics/telemetry** | Latency, cache hit, lỗi/rate của Secret Manager? | Toàn bộ chứng cứ audit chống chỉnh sửa |
| **Key lifecycle audit** | Ai rotate/revoke/grant secret access? | Mọi bản secret trong RAM đã bị xóa chưa |

HMAC là cơ chế MAC dùng **shared secret**: cả sender và verifier/key custodian đều có khả năng tính tag. **Không gọi audit HMAC là non-repudiation tuyệt đối** như chữ ký số bất đối xứng.

### 1.3. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân loại **plaintext read**, metadata lookup, KMS decrypt, cache hit và key management.
2. Phân biệt **secret-access actor** (workload/human) với **HMAC client principal**.
3. Thiết kế schema audit có provenance, actor, secret record/version, purpose, stage, outcome và trusted correlation.
4. Áp IAM least privilege, audience/tenant isolation, separation of duties và break-glass controls.
5. Ghi nhận cache use/secret lease mà không nhầm với Secret Manager API calls.
6. Theo dõi rotation/revocation và xử lý stale cache, policy version, KMS failures.
7. Tránh log plaintext, raw Authorization, full HMAC tags, secret-derived material và PII.
8. Triển khai Java 17 HMAC demo với secret access audit, cache, key policy, timestamp/nonce và tests.
9. Test audit sink outage, multi-node, gateway rewrite, key compromise, revoked-key traffic.
10. Nêu được giới hạn của log integrity, attribution và các trường hợp cần reconciliation.

## 2. Secret inventory: phân biệt metadata, material và phiên bản

### 2.1. Key record minh họa

~~~text
Trusted HMAC key metadata:
  audience             = orders-api-production
  clientId             = merchant-17
  publicKeyId           = k-2026-11
  immutableRecordId    = key-record-017
  secretVersionId      = v7
  keyState             = ACTIVE
  verifyUntilEpochSec  = server-managed deadline (nếu cần)
  allowedPurpose       = HMAC_VERIFY
  secretLocator        = opaque provider reference

Sensitive material:
  hmacSharedSecret     = 32 random bytes (KHÔNG ghi audit)
~~~

`publicKeyId` ở đây chỉ là **key identifier trong giao thức HMAC**, không phải khóa công khai theo mật mã bất đối xứng. Secret material là bytes làm key cho `javax.crypto.Mac`.

**KMS wrapping key** có thể là key dùng encrypt/decrypt một encrypted HMAC-secret blob; nó **khác với HMAC shared secret**. Audit phải tách `kmsWrappingKeyId`, `hmacCredentialKeyId` và `secretVersionId`. Dồn cả ba vào một field `keyId` sẽ làm sai điều tra khi các loại khóa được rotate độc lập.

### 2.2. Từng loại access có nghĩa khác nhau

| Operation | Có plaintext trả về không? | Dấu vết nên có |
|---|---|---|
| Lookup key metadata | Không nhất thiết | Lookup outcome, audience, key state |
| Read key version/state | Không | Metadata-access event nếu cần |
| `GetSecretValue` | **Có** | Material read + actor, resource version, outcome |
| KMS `Decrypt` / `Unwrap` | **Có thể** | KMS operation, wrapping key, context, actor |
| Cache hit trong process | Trả secret đã giữ trong RAM | **Application CACHE_USE**; không giả đó là platform read |
| HMAC `Mac.init`/`doFinal` | Sử dụng key trong process | Request authentication outcome; không log key |
| Rotate/revoke/version change | Thay chính sách hoặc material | Management actor, target, prior/new state |
| Secret access denied | Không | Actor, target, policy decision, reason category |
| Break-glass access | Có thể | MFA/approval/ticket, alert, emergency scope |
| Export/backup/restore | Có thể | High-risk operation, protected backup, actor |
| Delete/destroy version | Không trả plaintext nhưng có hậu quả lớn | Destructive control-plane event |

**Không dùng số lượng Secret Manager reads như số request xác thực.** Một process có thể dùng cache cho hàng nghìn MAC computations; một warm-up fetch có thể diễn ra khi chưa có request nào.

### 2.3. Các đường có thể chạm plaintext

~~~text
Production verifier -> Secret Manager / KMS
Production verifier -> protected in-memory cache
Provisioning service -> secret creation / one-time client delivery
Rotation controller -> new version creation + cutover
Operations -> break-glass guarded read
Backup/restore -> encrypted secret snapshot or sensitive restore path
Debug tooling -> SHOULD NOT dump bytes
Logs and crash dumps -> SHOULD NOT expose process memory secrets
~~~

Phải inventory cả **đường trực tiếp** và **đường phụ**: environment variables, mounted files, container secrets, JVM heap dumps, debugging, APM/exception capture, build/CI logs và backups. Bật provider audit không ngăn plaintext đã bị sao chép ra khỏi provider.

### 2.4. Namespace và ownership

| Metadata | Quy tắc |
|---|---|
| `audience` | Giá trị service-controlled, không lấy từ HTTP `Host` tự khai |
| `clientId` | Key owner trong trusted store |
| `keyId` | Selector từ signed request; lookup phải xác nhận owner |
| `immutableRecordId` | Opaque ID, không reuse khi đổi secret |
| `versionId` | Bắt buộc nhận biết key material version trong audit |
| `environment` / `region` | Prod/staging không cùng quyền đọc |
| `accessPolicyVersion` | Có thể giải thích vì sao access allowed/denied |
| `allowedPurpose` | `HMAC_VERIFY`/`ROTATE`/`PROVISION` có quyền riêng |
| `verifyUntil` / `revokedAt` | Server-owned time, không lấy từ timestamp client |
| `retentionPolicyId` | Phục vụ forensic/tuân thủ, độc lập với nonce TTL |

## 3. Ai có quyền đọc secret?

### 3.1. Workload IAM principal khác HTTP client ID

Request bên ngoài có thể khai:

~~~http
Authorization: HMAC-SHA256 client_id="merchant-17", key_id="k-2026-11", signature="..."
~~~

Secret Manager API call lại có:

~~~text
actorId=svc-hmac-verifier-prod
operation=GetSecretValue
target=secret-record-017/v7
iamDecision=ALLOW
~~~

Nếu audit ghi `merchant-17 accessed secret-record-017` từ event provider thì có thể **sai actor**. Merchant thường không có quyền gọi Secret Manager của server. Có thể ghi `associatedRequestClientClaim=merchant-17` nếu cần điều tra nhưng đánh dấu **UNVERIFIED** trước MAC và tuyệt đối không đổi actor ở provider event.

Các actor thường gặp:

- `WORKLOAD`: verifier đang chạy với workload identity cụ thể.
- `AUTOMATION`: rotation controller, provisioning service.
- `HUMAN`: operator có SSO/MFA, truy cập qua path đã phê duyệt.
- `BREAK_GLASS`: human/service dùng quyền khẩn cấp trong thời hạn giới hạn.
- `DELEGATED`: actor on-behalf-of chỉ khi delegation/trust chain được chứng minh.

Không tin `X-Forwarded-For`, `User-Agent` hoặc `X-Verified-Client` do Internet client gửi để xác định người gọi Secret Manager.

### 3.2. Least privilege và separation of duties

Một chính sách hợp lý cho verifier production:

~~~text
Actor: svc-hmac-verifier-prod
Allow:
  read HMAC_VERIFY secret versions
  only environment=production
  only audience=orders-api-production
  only approved resource paths/roles

Deny:
  read unrelated tenants/audiences without explicit scope
  list/export all organizational secrets
  create/delete/rotate secret versions
  edit IAM policy
  disable/alter audit retention
  read staging secrets without authorized role
~~~

Chính sách thật có thể dùng IAM resource conditions, workload identity, KMS encryption context, mTLS/service identity và policy engine. **Không chỉ tin một header `purpose=HMAC_VERIFY` do client gửi**: purpose phải đến từ server-controlled code path và quyền của workload.

Tách trách nhiệm: verifier được fetch secret để verify, rotation service quản lý version, audit viewer chỉ đọc event, audit writer không tự sửa lịch sử, người phê duyệt break-glass có thể khác người thực hiện.

### 3.3. Ba threat scenarios

**Attacker khai key ID của victim.** Kẻ tấn công gửi `client_id=victim` và MAC giả. Verifier có thể thật sự gọi Secret Manager lấy candidate secret để tính MAC; event **material read actor=verifier workload** là đúng, còn `claimedClientId=victim` ở request audit vẫn unverified. Không gán read cho victim.

**Compromised workload identity.** Một token service bị lộ được dùng để đọc secret từ pod/host/region bất thường. Platform audit cần actor, source, operation, version, status, policy; kết hợp workload attestation, rate limiting và alert. Không có request correlation không tự chứng minh bị tấn công: background warm-up, key rotation hoặc maintenance có thể hợp lệ.

**Debug hoặc log leak.** App serialize `byte[]`/`SecretKeySpec` hoặc header `Authorization` vào traces/logs. Access ban đầu có thể hợp IAM nhưng secret vẫn rò rỉ. Cần redaction, lint/review, secrets scanner và phản ứng sự cố; không chỉ dựa vào audit của Secret Manager.

## 4. Event taxonomy và thiết kế schema audit

### 4.1. Phân biệt events theo operation và provenance

| Event type | Nguồn phát | Ý nghĩa |
|---|---|---|
| `SECRET_MATERIAL_READ_ALLOWED` | Provider/adapter | Plaintext được trả theo policy |
| `SECRET_MATERIAL_READ_DENIED` | Provider/adapter | Request đọc bị từ chối |
| `SECRET_MATERIAL_READ_ERROR` | Provider/adapter | Provider lỗi/timeout |
| `SECRET_UNWRAP_ALLOWED` | KMS/adapter | Key unwrap/decrypt thành công |
| `SECRET_CACHE_HIT` | Ứng dụng | Material dùng từ cache, **không phải provider read mới** |
| `SECRET_CACHE_MISS` | Ứng dụng | Cache chưa có; chưa chắc fetch success |
| `SECRET_CACHE_EVICTED` | Ứng dụng | Entry bị loại do TTL/rotation |
| `SECRET_VERSION_REFRESHED` | Ứng dụng | Cache nạp đúng version mới |
| `SECRET_ACCESS_POLICY_DENIED` | IAM/policy | Actor/resource/action không được phép |
| `SECRET_ACCESS_GRANT_CHANGED` | Management | Quyền đọc bị cấp/thu hồi |
| `KEY_ROTATION_STARTED/COMPLETED` | Management | Thay material/version và rollout |
| `KEY_REVOKED` | Management | Không còn cho verify credential |
| `BREAK_GLASS_SECRET_ACCESS` | Guarded control plane | Truy cập khẩn cấp với ticket/MFA |
| `HMAC_MAC_VERIFIED` | Verifier | MAC đúng, chưa chắc freshness/nonce |
| `HMAC_AUTHENTICATED` | Verifier | MAC, timestamp và nonce đều pass |
| `HMAC_AUTHZ_DENIED` | Authorization | Authenticated nhưng không có quyền resource |

**Không sử dụng chung một nhãn `SECRET_ACCESSED`** cho read, cache hit, metadata lookup và HMAC verification: những thứ đó phục vụ điều tra khác nhau.

### 4.2. Hai ví dụ JSON với provenance khác nhau

Platform-origin secret read:

~~~json
{
  "schemaVersion": "hmac-secret-audit-v1",
  "eventId": "platform-0001",
  "occurredAt": "2026-11-28T03:00:00Z",
  "eventType": "SECRET_MATERIAL_READ_ALLOWED",
  "provenance": "SECRET_MANAGER_PLATFORM",
  "actorType": "WORKLOAD",
  "actorId": "svc-hmac-verifier-prod",
  "operation": "GetSecretValue",
  "outcome": "ALLOWED",
  "targetSecretRecordId": "secret-record-017",
  "targetVersionId": "v7",
  "targetAudience": "orders-api-production",
  "purpose": "HMAC_VERIFY",
  "environment": "production",
  "requestCorrelationId": "edge-req-123",
  "policyDecisionId": "access-policy-v5"
}
~~~

Application-origin cache event:

~~~json
{
  "schemaVersion": "hmac-secret-audit-v1",
  "eventId": "app-0002",
  "occurredAt": "2026-11-28T03:00:01Z",
  "eventType": "SECRET_CACHE_HIT",
  "provenance": "APPLICATION",
  "actorType": "WORKLOAD",
  "actorId": "svc-hmac-verifier-prod",
  "operation": "HMAC_VERIFY",
  "outcome": "USED_CACHED_MATERIAL",
  "targetSecretRecordId": "secret-record-017",
  "targetVersionId": "v7",
  "requestCorrelationId": "edge-req-124"
}
~~~

Các giá trị này là **minh họa**, không tự nhận tương thích một API provider nào. `provenance=APPLICATION` không được đặt thành `SECRET_MANAGER_PLATFORM` chỉ để làm event “đáng tin hơn”. Event phải có nguồn xuất xứ chính xác và chính sách integrity tương ứng.

### 4.3. Từng field lấy từ nguồn nào?

| Field | Nguồn | Giới hạn tin cậy |
|---|---|---|
| `eventId` | Provider hoặc server sinh | Dedup exporter retries |
| `occurredAt` | UTC wall-clock tại emitter | Không dùng client signed timestamp làm event time |
| `ingestedAt` | Audit sink | Đo lag, không thay occurredAt |
| `provenance` | Source connector/config đáng tin | `PLATFORM` khác `APPLICATION` |
| `actorId` / `actorType` | IAM identity của caller | Không lấy HMAC client ID làm Secret Manager actor |
| `operation` / `outcome` | Provider response hoặc code path | Phân biệt read/cache/verify/denied/error |
| `targetSecretRecordId` / `versionId` | Trusted secret inventory | Không chứa plaintext secret |
| `targetAudience` | Server config/key metadata | Không tin raw `Host`/`X-Audience` |
| `claimedClientId` / `claimedKeyId` | HTTP request, nếu cần | **UNVERIFIED** trước HMAC |
| `verifiedClientId` | Verifier sau full authn | Không thay actor của provider read |
| `requestCorrelationId` | Trusted gateway/edge | Có thể null khi background read |
| `policyDecisionId` | IAM/access policy | Cho biết rule/version |
| `cacheOutcome` | Application cache | Không mặc định provider có event |
| `errorCategory` | Sanitized code | Không serialize exception chứa secret |
| `durationNanos` | Monotonic timer | Không phải epoch timestamp |

Giới hạn event fields theo **mục tiêu điều tra**, không dump toàn bộ request. Raw body hash có thể tiết lộ thông tin từ domain nhỏ dù không chứa plaintext; không tự coi SHA-256 của PII là ẩn danh.

### 4.4. Một request có thể có ba actor/outcomes

~~~text
Event 1: SECRET_MATERIAL_READ_ALLOWED
  actor            = svc-hmac-verifier-prod
  provenance       = SECRET_MANAGER_PLATFORM
  target           = secret-record-017/v7
  requestCorrelation=edge-req-123

Event 2: HMAC_AUTHENTICATED
  claimedClientId  = merchant-17
  verifiedClientId = merchant-17
  verifiedKeyId    = k-2026-11
  requestCorrelation=edge-req-123

Event 3: AUTHORIZATION_DENIED
  principal        = merchant-17 (đã xác thực)
  resourceOwner    = merchant-42 (đọc từ trusted DB)
  requestCorrelation=edge-req-123
~~~

`SECRET_MATERIAL_READ_ALLOWED` không chứng minh event 2 sẽ pass; `HMAC_AUTHENTICATED` không tự cấp quyền ở event 3.

## 5. Pipeline truy cập secret, HMAC và nonce

~~~mermaid
sequenceDiagram
    participant C as HMAC Client
    participant G as Gateway
    participant V as HMAC Verifier
    participant M as Key Metadata Store
    participant S as Secret Manager / KMS
    participant N as Shared Nonce Store
    participant L as Audit Sink
    participant B as Authorization
    C->>G: Method/target/headers/body + HMAC
    G->>G: Reject malformed/duplicate fields, edgeRequestId
    G->>V: Signed fields và trusted correlation
    V->>M: Lookup audience/client/keyId
    M-->>V: Key record/state/version
    V->>S: Authorized material read or cache lookup
    S-->>V: Secret material when allowed
    S->>L: Platform material-read event (nếu fetch)
    V->>L: App secret-use/cache event
    V->>V: Compute HMAC-SHA256, verify tag
    V->>V: Timestamp freshness
    V->>N: Atomic reserve nonce per authenticated client
    N-->>V: Reserved or replay
    V->>L: Terminal request-authentication event
    V->>B: Verified principal only if authn passed
    B->>L: Resource authorization event
~~~

### 5.1. Canonical signing contract tham khảo

Trong bài, một hợp đồng minh họa `hmac-secret-audit-v1` có **10 dòng**:

| Dòng | Thành phần ký | Quy tắc |
|---|---|---|
| 1 | Version | `hmac-secret-audit-v1` |
| 2 | Audience | `orders-api-production` |
| 3 | Method | `POST` |
| 4 | Raw target | `/v1/orders?mode=commit` |
| 5 | Content-Type | `application/json` canonical |
| 6 | Client ID | Claimed selector, được bind với key record |
| 7 | Key ID | Chọn trusted secret record |
| 8 | Timestamp | Unix epoch **seconds** ASCII canonical |
| 9 | Nonce | 16-byte CSPRNG/Base64URL no-pad |
| 10 | Body digest | SHA-256 raw body bytes, lowercase hex |

Nối bằng **LF (`\n`)**, không thêm LF cuối, mã hóa UTF-8. HMAC-SHA-256 có tag **32 byte**; encode Base64URL không padding dài 43 ký tự. Không ký nguyên raw `Authorization` chứa chính signature vì gây tự tham chiếu. Không dùng `Host` hoặc raw client-provided `X-Audience` để lựa chọn secret trái policy.

~~~text
hmac-secret-audit-v1
orders-api-production
POST
/v1/orders?mode=commit
application/json
merchant-17
k-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
<sha256-hex-of-raw-request-body>
~~~

Dòng cuối là placeholder. Timestamp mẫu minh họa cú pháp, không mặc nhiên còn mới tại thời điểm chạy. Hợp đồng này **khác** RFC 9421 HTTP Message Signatures.

### 5.2. Policy key và thứ tự an toàn

Một pipeline an toàn:

1. HTTP adapter reject duplicate signed headers, giới hạn size và giữ raw target/body theo contract.
2. Lookup candidate record `(audience, claimedClientId, claimedKeyId)` trong trusted key store.
3. Kiểm key state theo server clock: `ACTIVE`/`VERIFY_ONLY` còn hạn, `REVOKED` reject.
4. Nếu cần secret, kiểm IAM workload và lấy **đúng version** từ Secret Manager/KMS hoặc cache còn hợp lệ.
5. Phát/sở hữu audit về **material read/use** với actor workload và đúng provenance.
6. Dựng canonical bytes, tính HMAC và so full tag bằng `MessageDigest.isEqual`.
7. Kiểm timestamp trong cửa sổ và reserve nonce **nguyên tử sau MAC đúng**, phạm vi `(audience, authenticatedClientId, nonce)`.
8. Chỉ sau khi authn pass mới tạo principal rồi thực hiện **authorization theo action/resource/tenant**.
9. Ghi terminal authentication outcome và authorization event; không trộn secret access với business commit.

Một hệ thống có thể kiểm timestamp format/freshness sớm để giảm chi phí truy cập secret, nhưng phải giữ semantics: **đọc secret không phải MAC đúng**, **lookup hit không phải material read**, và **MAC đúng không phải authorization**.

### 5.3. Nonce TTL và secret cache TTL là hai thứ khác nhau

Giả sử timestamp được accept khi `now - 300 <= t <= now + 300`. Với cùng signed timestamp `t`, tổng acceptance interval từ `t - 300` đến `t + 300` là **600 giây**. Nonce TTL phải bao phủ toàn interval cùng margin nếu store giữ nonce tính từ lần reserve đầu tiên; ví dụ `660 seconds`. Redis `SET key 1 NX EX 660` là **atomic insert + expiry**, không tương đương `PX 660` (660 milliseconds); `PX 660000` mới tương đương 660 giây.

**Cache TTL secret** phục vụ performance/rotation: nó không thể lấy trực tiếp từ nonce TTL. Secret `REVOKED` phải bị từ chối theo key-status policy dù còn cached plaintext; cần invalidation/revalidation, version pinning và eventual consistency được đánh giá.

### 5.4. Failure policies

| Failure | Điều không được làm | Hướng xử lý |
|---|---|---|
| Secret Manager IAM DENIED | Dùng default/fallback secret | Fail closed, ghi denied event |
| KMS decrypt ERROR | Thử bất kỳ secret nào khác | Fail closed, sanitized error |
| Secret cache stale sau revoke | Chấp nhận key cũ vì bytes còn | Kiểm trusted state/invalidate cache |
| Nonce store unavailable | Bỏ kiểm replay | Fail closed nếu nonce bắt buộc |
| Mandatory audit sink down | Báo “đã audit” dù log chỉ ở RAM | Fail closed hoặc durable outbox theo policy |
| Audit queue lag | Im lặng drop events | Alert/backpressure/retry/dedup |
| Key metadata lookup miss | Thử mọi secrets | Reject, không cross-tenant scan |
| Client sends key ID giả | Gán read event cho client giả | Giữ claimed vs verified và actor workload |


## 6. Cache, leases và ý nghĩa của secret access audit

### 6.1. Một material read có thể phục vụ hàng nghìn HMAC requests

Giả sử verifier xử lý 1.000 HTTP attempts trong một phút, nạp secret version một lần rồi cache trong process:

~~~text
Secret Manager platform:
  SECRET_MATERIAL_READ_ALLOWED = 1

Verifier application:
  SECRET_CACHE_MISS = 1
  SECRET_CACHE_HIT = 999
  MAC verification attempts = 1000
  HMAC_AUTHENTICATED = 990
  MAC_MISMATCH / STALE / REPLAY = 10
~~~

Không kết luận chỉ một HTTP request được ký vì chỉ thấy **một** `GetSecretValue`. Ngược lại, cache warm-up có thể đọc secret mà **chưa có request nào**. Cần đối chiếu các counters với loại event/nguồn tương ứng.

### 6.2. Cache key phải chứa immutable secret version

Một cache key hợp lý:

~~~text
CacheKey(
    audience="orders-api-production",
    ownerClientId="merchant-17",
    hmacKeyId="k-2026-11",
    immutableSecretVersionId="v7"
)
~~~

Nếu chỉ cache theo `keyId`, hai tenants có thể dùng cùng text `key-1` và vô tình truy cập sai secret. Nếu cache theo mutable alias “latest” mà không pin immutable version, quá trình rotation có thể khiến verifier A và B ký/verify các bytes khác nhau dưới cùng key ID.

**Hợp đồng của bài:** HMAC selector gắn với **trusted key metadata**, metadata chọn **secret version chính xác**, và cache không được cho `REVOKED` key verify chỉ vì material còn trong RAM.

### 6.3. Memory handling không phải magic erase

Trong Java, có thể sử dụng `byte[]` cho secret và thử xóa bản copy do ứng dụng trực tiếp sở hữu sau dùng:

~~~java
byte[] secretCopy = acquireSecretForOneVerification();
try {
    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(secretCopy, "HmacSHA256"));
    byte[] tag = mac.doFinal(canonicalBytes);
} finally {
    Arrays.fill(secretCopy, (byte) 0);
}
~~~

Nhưng `SecretKeySpec` và crypto provider có thể tạo internal copies; Java GC, JIT, heap/core dump có thể giữ bản sao. **Không tuyên bố `Arrays.fill` bảo đảm xóa sạch mọi bit secret khỏi RAM**. Hạn chế thời gian giữ material, tránh `String` immutable, bảo vệ process memory/heap dump, thu hẹp quyền attach debugger và dùng HSM/KMS MAC operations trực tiếp nếu kiến trúc và key policy cho phép.

Nếu HMAC secret chỉ tồn tại trong HSM và provider thực hiện MAC operation từ một opaque key handle, phía ứng dụng có thể không bao giờ nhận plaintext; audit lúc đó nên ghi **`MAC/Verify operation by key handle`** thay vì `SECRET_MATERIAL_READ_ALLOWED`. Đây là kiến trúc khác và phải xác minh provider hỗ trợ primitive, performance, quota và usage policy.

### 6.4. Cache invalidation trong key rotation

Giai đoạn rotation có thể có:

~~~text
k-old / secret-version=v6 / VERIFY_ONLY until D
k-new / secret-version=v7 / ACTIVE

At D:
  k-old -> REVOKED hoặc VERIFY_ONLY hết hạn
  invalidate cached v6
  all verifiers must enforce new policy
~~~

Vì `X-Timestamp` do client ký, request có timestamp “trước D” **không thể** vượt qua revocation hiện tại. Server dùng trusted clock và key state. Một version vẫn còn material trong cache **không có nghĩa** có quyền sử dụng nó để xác thực.

Cách giảm rủi ro stale key:
- Key state revalidation hoặc versioned policy snapshots với TTL hữu hạn và emergency invalidation.
- Push invalidate/revoke tới workers nếu hạ tầng hỗ trợ, cùng bounded propagation SLA.
- Không fallback secret-version v6 khi v7 fetch timeout.
- Audit cache refresh/invalidation với actor/version/outcome riêng.
- Test multi-AZ/region trong cutover và failover.

### 6.5. Kích thước log và quyền xem cache events

Ghi `SECRET_CACHE_HIT` cho **mọi HMAC attempt** có thể tạo số lượng log rất lớn. Nếu yêu cầu kiểm chứng mọi lần sử dụng secret, cần pipeline audit chịu tải và semantics rõ. Nếu chính sách chỉ yêu cầu audit **material retrieval và admin actions** còn cache-use được thể hiện bằng metrics/aggregates, phải nói thẳng rằng dữ liệu đó **không phải forensic per-use trail đầy đủ**.

**Sampling metrics không tương đương sampling mandatory audit.** Quyết định số lượng và mức chi tiết events dựa trên threat model, regulatory policy, chi phí và khả năng truy vết, không tùy tiện bỏ event khi load cao.

## 7. Audit sink, tamper resistance và privacy

### 7.1. Những dữ liệu tuyệt đối tránh ghi

~~~text
DO NOT LOG:
  plaintext hmac shared secret
  encrypted secret blob with accessible decrypt context (unless approved)
  KMS decrypted plaintext bytes
  raw Authorization value / bearer tokens
  expected or received full HMAC tag
  body carrying personal or payment data
  secret environment-variable value
  raw nonce by default
  session cookies and service account credentials
  stack trace carrying sensitive request material
~~~

Ngay cả một `sha256(secret)` được đưa vào log có thể trở thành fingerprint bí mật lâu dài và tạo correlation không mong muốn. Dùng **opaque immutable record/version ID**. Nếu cần liên kết nhiều events mà không để lộ tenant/key ID trong SIEM, dùng pseudonym/keyed digest với secret logging key **riêng**, theo chính sách truy cập và retention.

### 7.2. Ngăn log injection

Key ID, client ID, `X-Request-Id`, User-Agent và `traceparent` đến từ HTTP có thể được client điều khiển trước khi verify. Không bao giờ ghép raw inputs thành dòng log như:

~~~text
logger.info("keyId=" + rawHeader + " result=" + result)
~~~

Phòng vệ:
1. HTTP parser reject CR/LF/NUL/obs-fold sai và duplicate signed headers.
2. Validate selector grammar, ví dụ `[A-Za-z0-9_-]{1,64}`, giới hạn size trước key lookup.
3. Dùng structured serializer có escaping, không tự nối values vào JSON.
4. Đánh dấu `claimedKeyId` là **UNVERIFIED**; chỉ dùng key record trusted để gán verified identity sau MAC đúng.
5. Rate limit malformed requests, không tạo metric labels từ raw attacker-chosen values.
6. Trong dashboards, phân biệt `claims seen` với `verified key usage`.

### 7.3. Platform-origin và application-origin không thể đánh đồng

**Platform audit event** có thể xác nhận một IAM identity gọi API `GetSecretValue`/`Decrypt` và provider trả outcome gì. Nó mạnh ở provenance của **API boundary**, nhưng không quan sát mọi access từ application cache.

**Application audit event** có thể biết request correlation, cache hit, HMAC verify và principal sau authn. Nó bổ sung business context, nhưng nếu process bị xâm nhập thì logs do process phát có thể bị giả/xóa trước khi tới sink.

Khi forensic, nên correlate:
- Provider Secret Manager/KMS API call events và IAM grant changes.
- Cache refresh/use events từ app.
- HMAC authentication/anti-replay terminal events.
- Key lifecycle/revocation management events.
- Authorization actions trên resource và business ledger.

Không suy rằng **không có lộ secret** chỉ vì provider không ghi read mới: một bản copy đã lộ hoặc material cached vẫn có thể bị sử dụng.

### 7.4. Integrity, availability và retention

Một pipeline audit đáng tin cần:
- Append-only/immutable storage hoặc WORM khi required.
- Tách quyền write, view, delete và policy change; operator không tự xóa dấu vết truy cập mình.
- TLS/mTLS/identity của emitter và authenticated ingestion.
- Unique `eventId`/ingestion dedup, event timestamp và ingestion timestamp.
- Durable queue/outbox/retry/backoff/dead-letter và alert khi audit sink lag/down.
- Encryption at rest, access review, retention và legal hold.
- Có thể hash-chain hoặc ký audit batches bằng signing key quản lý độc lập khi cần tamper evidence.
- Dashboard so expected access count vs observed provider/app events trong khả năng observability.
- Kiểm thử mất log trong failover, backpressure, restart và multi-region.

**Chính sách fail closed phụ thuộc yêu cầu an toàn:** Nếu luật/policy yêu cầu audit durable **trước khi tiết lộ plaintext**, không trả secret khi sink unavailable. Nếu tổ chức phê duyệt queue bất đồng bộ, phải dùng **durable queue/outbox** và minh chứng event sẽ được giao lại; không gọi `System.out.println` là durable security audit.

### 7.5. Audit key rotation khác audit request authentication

Một management-plane event có actor khác target:

~~~json
{
  "eventType": "KEY_REVOKED",
  "actorType": "AUTOMATION",
  "actorId": "rotation-controller",
  "targetClientId": "merchant-17",
  "targetKeyId": "k-old",
  "targetSecretVersion": "v6",
  "previousState": "VERIFY_ONLY",
  "newState": "REVOKED",
  "reasonCode": "ROTATION_COMPLETE",
  "approvalId": "change-2026-042",
  "outcome": "COMMITTED"
}
~~~

`actorId=rotation-controller` mới là người thực hiện management action; `targetKeyId=k-old` là object bị thay đổi. Không ghi như “key tự revoke”. Giữ immutable version metadata/tombstones cho forensic dù plaintext đã bị destroy theo policy.

## 8. Đưa Secret Manager/KMS audit vào luồng điều tra

### 8.1. Chuỗi sự kiện điển hình

~~~mermaid
flowchart TD
    A["Ingress có signed HMAC request"] --> B["Đọc metadata key state"]
    B --> C{"Secret cache hit?"}
    C -->|No| D["Secret Manager material fetch"]
    C -->|Yes| E["Application CACHE_HIT audit/telemetry"]
    D --> F["Provider-origin access audit"]
    F --> G["Application verifier"]
    E --> G
    G --> H{"MAC matches?"}
    H -->|No| I["Authentication MAC_MISMATCH"]
    H -->|Yes| J{"Timestamp + nonce valid?"}
    J -->|No| K["STALE / REPLAY rejected"]
    J -->|Yes| L["AUTHENTICATED principal"]
    L --> M{"Authorized resource?"}
    M -->|No| N["AUTHORIZATION_DENIED"]
    M -->|Yes| O["Business operation / idempotency"]
~~~

### 8.2. Correlation IDs đúng vai trò

| Identifier | Nguồn | Mục đích |
|---|---|---|
| `edgeRequestId` | Trusted ingress | Correlate HTTP attempt qua gateway/verifier |
| `providerRequestId` | KMS/Secret Manager | Correlate provider API operation |
| `auditEventId` | Emitter/sink | Idempotent ingestion |
| `actorWorkloadId` | IAM identity | Ai gọi provider |
| `claimedClientId` | HTTP sender | Chỉ unverified đến khi MAC đúng |
| `verifiedClientId` | HMAC verifier | Principal của signed request |
| `secretRecordId/versionId` | Secret inventory | Đúng material/version |
| `hmacKeyId` | Credential selector | Không là secret material |
| `kmsWrappingKeyId` | Provider crypto key | Không nhầm HMAC selector |
| `traceId` | Tracing subsystem | Có trust context, có thể đến từ client |
| `idempotencyKey` | Client logical operation | Không thay nonce; tránh ghi raw nếu nhạy cảm |

Nếu gateway tự thay `X-Request-Id` đã nằm trong canonical HMAC, MAC sẽ fail. Dùng **server edgeRequestId riêng**, giữ nguyên signed client request ID và chuyển correlation nội bộ qua kênh tin cậy. `X-Verified-Client` do client Internet gửi phải bị strip.

### 8.3. Một số nhận định sai từ số liệu

| Quan sát | Suy luận sai | Suy luận đúng hơn |
|---|---|---|
| 1 platform read, 5.000 HMAC successes | Log thiếu 4.999 lần read | Có thể 4.999 cache uses; phải kiểm app policy |
| 50 platform reads, 0 HMAC successes | 50 requests đã authenticated | Có thể warm-up, failed MAC, rotation hoặc abuse |
| Secret read bởi `svc-verifier`, claimed client merchant A | Merchant A tự gọi Secret Manager | Actor là verifier; claim A chưa được verify |
| Không có provider read sau revoke | Không còn ai biết secret cũ | RAM caches/copies có thể còn |
| App ghi `SECRET_CACHE_HIT` | Provider đã trả plaintext ở attempt này | Cache use khác platform material read |
| Key state REVOKED nhưng MAC tag đúng | Nên accept vì secret chính xác | Key policy **deny** |
| Một HTTP request được authenticated | Business được commit | Cần authorization/ledger/idempotency |
| KMS logs có `Decrypt` success | Shared secret không thể bị lộ | Plaintext có thể đã đến workload; cần least privilege và memory controls |


## 9. Java 17: demo secret access audit, cache và HMAC verifier

Ví dụ dưới đây minh họa **một luồng end-to-end trong một JVM**. Nó dùng Java 17/JCA, `SecureRandom`, `Clock.fixed`, `ConcurrentHashMap`, `Mac` và `MessageDigest.isEqual`; **không cần Spring hoặc thư viện ngoài JDK**.

Cấu trúc:

- `MockSecretProvider` giả lập Secret Manager. Nó kiểm **workload actor**, phát `MOCK_PROVIDER/SECRET_MATERIAL_READ_ALLOWED` hoặc `READ_DENIED` **trước khi trả plaintext** theo chính sách audit bắt buộc.
- `SecretCache` lưu secret theo immutable `SecretRef(recordId,versionId)` và phát **application-origin CACHE_MISS/CACHE_HIT**; không giả cache hit là provider read.
- `SecretLease` giữ một bản copy ngắn hạn, đóng bằng `try-with-resources` và **best-effort zeroization**.
- Key metadata tách khỏi material, lookup `(audience,clientId,keyId)`, kiểm `ACTIVE/VERIFY_ONLY/REVOKED`.
- Parser custom `Authorization: HMAC-SHA256 client_id="...", key_id="...", signature="..."`, strict tag Base64URL no-pad **43 chars/32 bytes**.
- Canonical request 10 dòng, full HMAC-SHA256, timestamp ±300 giây, nonce scope theo **authenticated client** và atomic nonce store.
- Audit terminal authentication event có **claimedKeyId** và **verifiedKeyId** riêng; verified ID chỉ xuất hiện sau MAC đúng, kể cả trường hợp nonce replay bị từ chối.
- `AuditSink` có trạng thái unavailable để mô phỏng **fail closed** khi audit bắt buộc không khả dụng.
- Tests cho provider read vs cache hit, forged MAC, revoked key, stale timestamp, replay, cross-client nonce, 8 requests đồng thời và authorization riêng.

**Phạm vi chính xác:** `MOCK_PROVIDER` là **provider giả trong Java demo**, không phải nhật ký thực do AWS/GCP/Azure phát. Application audit và mock provider audit đều nằm trong một `InMemoryAuditSink` cho mục đích quan sát. Production phải tích hợp identity, provider audit logs và durable sink thực sự.

### 9.1. Mã Java hoàn chỉnh: `SecretAccessAuditDemo.java`

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
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
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

public final class SecretAccessAuditDemo {
    private static final String VERSION = "hmac-secret-audit-v1";
    private static final String AUDIENCE = "orders-api-production";
    private static final String WORKLOAD = "svc-hmac-verifier-prod";
    private static final String ALGORITHM = "HmacSHA256";
    private static final long WINDOW_SECONDS = 300L;
    private static final long NONCE_TTL_SECONDS = 660L;
    private static final long SECRET_CACHE_TTL_SECONDS = 120L;

    private static final Pattern AUTH = Pattern.compile(
            "(?i:HMAC-SHA256) "
          + "(?i:client_id)=\"([A-Za-z0-9_-]{1,64})\", "
          + "(?i:key_id)=\"([A-Za-z0-9_-]{1,64})\", "
          + "(?i:signature)=\"([A-Za-z0-9_-]{43})\"");

    private SecretAccessAuditDemo() {}

    public record KeyRef(String audience, String clientId, String keyId) {}
    public record SecretRef(String recordId, String versionId) {}
    public enum KeyState { ACTIVE, VERIFY_ONLY, REVOKED }

    public record KeyMetadata(
            KeyRef ref, SecretRef secretRef, KeyState state,
            long verifyUntilEpochSeconds) {}

    public record Request(
            String method, String rawTarget, String contentType,
            String timestamp, String nonce, byte[] rawBody) {
        public Request {
            if (rawBody == null) {
                throw new IllegalArgumentException("Missing raw body");
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

    // Audit chỉ chứa metadata, tuyệt đối KHÔNG chứa secret/tag/body.
    public record AuditEvent(
            String eventId, Instant at, String eventType,
            String provenance, String actorId,
            String targetRecordId, String targetVersionId,
            String edgeRequestId, String claimedClientId,
            String claimedKeyId, String verifiedClientId,
            String verifiedKeyId, String outcome) {}

    public static final class AuditUnavailable
            extends RuntimeException {
        AuditUnavailable() {
            super("Mandatory audit sink unavailable");
        }
    }

    public interface AuditSink {
        void append(AuditEvent event);
    }

    // DEMO, không durable/immutable; kiểm fail-closed bằng toggle.
    public static final class InMemoryAuditSink
            implements AuditSink {
        private final ConcurrentLinkedQueue<AuditEvent> events =
                new ConcurrentLinkedQueue<>();
        private final AtomicBoolean available =
                new AtomicBoolean(true);

        public void setAvailable(boolean up) {
            available.set(up);
        }

        @Override
        public void append(AuditEvent event) {
            if (!available.get()) throw new AuditUnavailable();
            events.add(event);
        }

        public List<AuditEvent> snapshot() {
            return List.copyOf(events);
        }
    }

    private static String id(SecureRandom rng) {
        byte[] raw = new byte[16];
        rng.nextBytes(raw);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(raw);
    }

    private static AuditEvent event(
            String type, String provenance, String actor,
            SecretRef secret, String edge, Credential claim,
            KeyMetadata verified, String outcome,
            Clock clock, SecureRandom rng) {
        return new AuditEvent(
                id(rng), clock.instant(), type, provenance, actor,
                secret == null ? null : secret.recordId(),
                secret == null ? null : secret.versionId(),
                edge,
                claim == null ? null : claim.clientId(),
                claim == null ? null : claim.keyId(),
                verified == null ? null : verified.ref().clientId(),
                verified == null ? null : verified.ref().keyId(),
                outcome);
    }

    public static final class MockSecretProvider {
        private final ConcurrentHashMap<SecretRef, byte[]> values =
                new ConcurrentHashMap<>();

        public void register(SecretRef ref, byte[] secret) {
            if (ref == null || secret == null || secret.length != 32) {
                throw new IllegalArgumentException("Demo needs 32 bytes");
            }
            values.put(ref, secret.clone());
        }

        // App-side simulation of platform-origin audit, NOT real cloud log.
        // Audited before returning material; fail closed on sink failure.
        public byte[] read(
                SecretRef ref, String actor, String edge,
                AuditSink sink, Clock clock, SecureRandom rng) {
            if (!WORKLOAD.equals(actor)) {
                sink.append(event(
                        "SECRET_MATERIAL_READ_DENIED",
                        "MOCK_PROVIDER", actor, ref, edge,
                        null, null, "DENIED",
                        clock, rng));
                throw new SecurityException("Secret access denied");
            }
            byte[] secret = values.get(ref);
            if (secret == null) {
                sink.append(event(
                        "SECRET_MATERIAL_READ_ERROR",
                        "MOCK_PROVIDER", actor, ref, edge,
                        null, null, "NOT_FOUND",
                        clock, rng));
                throw new IllegalStateException(
                        "Secret version unavailable");
            }
            sink.append(event(
                    "SECRET_MATERIAL_READ_ALLOWED",
                    "MOCK_PROVIDER", actor, ref, edge,
                    null, null, "ALLOWED",
                    clock, rng));
            return secret.clone();  // Material only after audit success.
        }
    }

    // Chỉ bản copy sử dụng cho một phép HMAC; zeroize best-effort.
    public static final class SecretLease implements AutoCloseable {
        private final byte[] material;
        private boolean closed;

        SecretLease(byte[] ownedMaterial) {
            material = ownedMaterial;
        }

        public byte[] calculateMac(byte[] canonical)
                throws GeneralSecurityException {
            if (closed || canonical == null) {
                throw new IllegalStateException("Closed secret lease");
            }
            Mac engine = Mac.getInstance(ALGORITHM);
            engine.init(new SecretKeySpec(material, ALGORITHM));
            return engine.doFinal(canonical);
        }

        @Override
        public void close() {
            Arrays.fill(material, (byte) 0);
            closed = true;
        }
    }

    private static final class CachedValue {
        final byte[] material;
        final long expiresAt;
        CachedValue(byte[] material, long expiresAt) {
            this.material = material;
            this.expiresAt = expiresAt;
        }
    }

    public static final class SecretCache implements AutoCloseable {
        private final Map<SecretRef, CachedValue> entries =
                new HashMap<>();
        private boolean closed;

        // Synchronized để demo nhất quán trong MỘT JVM.
        // Không có distributed cache, KMS IAM hay global invalidation.
        public synchronized SecretLease acquire(
                SecretRef ref, long nowSeconds,
                String actor, String edge,
                MockSecretProvider provider, AuditSink sink,
                Clock clock, SecureRandom rng) {
            if (closed) throw new IllegalStateException("Cache closed");
            CachedValue cached = entries.get(ref);
            if (cached != null && cached.expiresAt > nowSeconds) {
                sink.append(event(
                        "SECRET_CACHE_HIT", "APPLICATION", actor,
                        ref, edge, null, null, "USED_CACHED_MATERIAL",
                        clock, rng));
                return new SecretLease(cached.material.clone());
            }

            // Không để expired bytes trong cache. Audit eviction
            // phải được thiết kế độc lập trong production.
            if (cached != null) {
                entries.remove(ref);
                Arrays.fill(cached.material, (byte) 0);
            }
            sink.append(event(
                    "SECRET_CACHE_MISS", "APPLICATION", actor,
                    ref, edge, null, null, "NEEDS_FETCH",
                    clock, rng));
            byte[] fetched = provider.read(
                    ref, actor, edge, sink, clock, rng);
            entries.put(ref, new CachedValue(
                    fetched.clone(),
                    Math.addExact(nowSeconds, SECRET_CACHE_TTL_SECONDS)));
            return new SecretLease(fetched);
        }

        public synchronized void invalidate(SecretRef ref) {
            CachedValue prior = entries.remove(ref);
            if (prior != null) {
                Arrays.fill(prior.material, (byte) 0);
            }
        }

        @Override
        public synchronized void close() {
            for (CachedValue value : entries.values()) {
                Arrays.fill(value.material, (byte) 0);
            }
            entries.clear();
            closed = true;
        }
    }

    public record NonceScope(
            String audience, String verifiedClientId, String nonce) {}

    public static final class NonceStore {
        private final ConcurrentHashMap<NonceScope, Long> expiries =
                new ConcurrentHashMap<>();

        public boolean reserve(
                NonceScope key, long nowSeconds, long ttlSeconds) {
            AtomicBoolean inserted = new AtomicBoolean(false);
            expiries.compute(key, (scope, expiry) -> {
                if (expiry != null && expiry > nowSeconds) {
                    return expiry;
                }
                inserted.set(true);
                return Math.addExact(nowSeconds, ttlSeconds);
            });
            return inserted.get();
        }
    }

    public enum Outcome {
        AUTHENTICATED, BAD_AUTHORIZATION, KEY_NOT_FOUND,
        KEY_REVOKED, KEY_EXPIRED, BAD_REQUEST,
        TIMESTAMP_OUT_OF_WINDOW, MAC_MISMATCH,
        REPLAY_NONCE, SECRET_ACCESS_ERROR,
        AUDIT_UNAVAILABLE, INTERNAL_ERROR
    }

    public record AuthResult(
            Outcome outcome, String verifiedClientId,
            String verifiedKeyId, String edgeRequestId) {}

    public static Credential parseAuthorization(List<String> values) {
        if (values == null || values.size() != 1) {
            throw new IllegalArgumentException(
                    "Exactly one Authorization field required");
        }
        String raw = values.get(0);
        if (raw == null || raw.length() > 300) {
            throw new IllegalArgumentException("Bad Authorization size");
        }
        Matcher m = AUTH.matcher(raw);
        if (!m.matches()) {
            throw new IllegalArgumentException(
                    "Unsupported/ambiguous HMAC credential");
        }
        return new Credential(m.group(1), m.group(2), m.group(3));
    }

    private static String nonce(String text) {
        if (text == null || !text.matches("[A-Za-z0-9_-]{22}")) {
            throw new IllegalArgumentException("Bad nonce");
        }
        final byte[] raw;
        try {
            raw = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException invalid) {
            throw new IllegalArgumentException("Malformed nonce", invalid);
        }
        if (raw.length != 16
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(raw).equals(text)) {
            throw new IllegalArgumentException("Non-canonical nonce");
        }
        return text;
    }

    private static byte[] decodeTag(String text) {
        if (text == null || !text.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException("Bad signature format");
        }
        final byte[] raw;
        try {
            raw = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException invalid) {
            throw new IllegalArgumentException("Malformed tag", invalid);
        }
        if (raw.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(raw).equals(text)) {
            throw new IllegalArgumentException("Non-canonical tag");
        }
        return raw;
    }

    private static long parseTimestamp(String text) {
        if (text == null || !text.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException(
                    "Timestamp must be Unix epoch seconds");
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException overflow) {
            throw new IllegalArgumentException("Timestamp overflow");
        }
    }

    private static boolean fresh(String text, long now) {
        try {
            long delta = Math.subtractExact(
                    parseTimestamp(text), now);
            return delta >= -WINDOW_SECONDS
                    && delta <= WINDOW_SECONDS;
        } catch (IllegalArgumentException | ArithmeticException error) {
            return false;
        }
    }

    public static byte[] canonicalBytes(
            Request r, String clientId, String keyId)
            throws GeneralSecurityException {
        if (r == null || !"POST".equals(r.method())
                || r.rawTarget() == null
                || !r.rawTarget().matches(
                        "/v1/orders\\?mode=(?:commit|preview)")) {
            throw new IllegalArgumentException("Unsupported method/URI");
        }
        if (r.contentType() == null
                || !"application/json".equals(
                        r.contentType().trim().toLowerCase(
                                java.util.Locale.ROOT))) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        if (clientId == null
                || !clientId.matches("[A-Za-z0-9_-]{1,64}")
                || keyId == null
                || !keyId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Bad identity");
        }
        parseTimestamp(r.timestamp());
        String signedNonce = nonce(r.nonce());
        byte[] body = r.rawBody();
        if (body.length > 65536) {
            throw new IllegalArgumentException("Body too large");
        }
        String bodyHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        String canonical = String.join("\n",
                VERSION, AUDIENCE, r.method(), r.rawTarget(),
                "application/json", clientId, keyId,
                r.timestamp(), signedNonce, bodyHex);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(byte[] secret, byte[] bytes)
            throws GeneralSecurityException {
        Mac engine = Mac.getInstance(ALGORITHM);
        engine.init(new SecretKeySpec(secret, ALGORITHM));
        return engine.doFinal(bytes);
    }

    // Test-only signing: sender cũng biết secret, không đưa vào audit.
    public static String sign(
            Request r, KeyRef key, byte[] senderSecret)
            throws GeneralSecurityException {
        byte[] tag = hmac(senderSecret,
                canonicalBytes(r, key.clientId(), key.keyId()));
        String encoded = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(tag);
        return "HMAC-SHA256 client_id=\""
                + key.clientId()
                + "\", key_id=\""
                + key.keyId()
                + "\", signature=\"" + encoded + "\"";
    }

    private static boolean keyCanVerify(
            KeyMetadata meta, long nowSeconds) {
        return meta != null
                && meta.ref() != null
                && AUDIENCE.equals(meta.ref().audience())
                && (meta.state() == KeyState.ACTIVE
                    || (meta.state() == KeyState.VERIFY_ONLY
                        && nowSeconds <=
                                meta.verifyUntilEpochSeconds()));
    }

    private static AuthResult finish(
            Outcome outcome, Credential claimed,
            KeyMetadata macVerified,
            String edge, AuditSink sink, Clock clock,
            SecureRandom rng) {
        try {
            sink.append(event(
                    "HMAC_AUTHENTICATION", "APPLICATION",
                    WORKLOAD,
                    macVerified == null ? null :
                            macVerified.secretRef(),
                    edge, claimed, macVerified,
                    outcome.name(), clock, rng));
        } catch (AuditUnavailable auditError) {
            // Không khẳng định đã ghi audit hoặc authenticated.
            return new AuthResult(
                    Outcome.AUDIT_UNAVAILABLE, null, null, edge);
        }
        if (outcome != Outcome.AUTHENTICATED) {
            return new AuthResult(outcome, null, null, edge);
        }
        return new AuthResult(
                outcome, macVerified.ref().clientId(),
                macVerified.ref().keyId(), edge);
    }

    public static AuthResult authenticate(
            Request r, List<String> authValues,
            Map<KeyRef, KeyMetadata> metadata,
            MockSecretProvider provider, SecretCache cache,
            NonceStore nonces, AuditSink sink,
            Clock clock, SecureRandom rng) {
        String edge = id(rng); // Server-generated attempt correlation.
        Credential claim;
        try {
            claim = parseAuthorization(authValues);
        } catch (IllegalArgumentException invalid) {
            return finish(Outcome.BAD_AUTHORIZATION, null, null,
                    edge, sink, clock, rng);
        }

        KeyRef lookup = new KeyRef(
                AUDIENCE, claim.clientId(), claim.keyId());
        KeyMetadata key = metadata.get(lookup);
        if (key == null) {
            return finish(Outcome.KEY_NOT_FOUND, claim, null,
                    edge, sink, clock, rng);
        }
        long now = clock.instant().getEpochSecond();
        if (!keyCanVerify(key, now)) {
            Outcome cause = key.state() == KeyState.REVOKED
                    ? Outcome.KEY_REVOKED : Outcome.KEY_EXPIRED;
            return finish(cause, claim, null,
                    edge, sink, clock, rng);
        }
        if (r == null) {
            return finish(Outcome.BAD_REQUEST, claim, null,
                    edge, sink, clock, rng);
        }
        if (!fresh(r.timestamp(), now)) {
            return finish(Outcome.TIMESTAMP_OUT_OF_WINDOW,
                    claim, null, edge, sink, clock, rng);
        }

        final byte[] received;
        final byte[] canonical;
        try {
            received = decodeTag(claim.signature());
            canonical = canonicalBytes(
                    r, claim.clientId(), claim.keyId());
        } catch (IllegalArgumentException invalid) {
            return finish(Outcome.BAD_REQUEST, claim, null,
                    edge, sink, clock, rng);
        } catch (GeneralSecurityException failure) {
            return finish(Outcome.INTERNAL_ERROR, claim, null,
                    edge, sink, clock, rng);
        }

        final byte[] expected;
        try (SecretLease lease = cache.acquire(
                key.secretRef(), now, WORKLOAD, edge,
                provider, sink, clock, rng)) {
            expected = lease.calculateMac(canonical);
        } catch (AuditUnavailable noAudit) {
            return new AuthResult(
                    Outcome.AUDIT_UNAVAILABLE, null, null, edge);
        } catch (GeneralSecurityException cryptoError) {
            return finish(Outcome.INTERNAL_ERROR, claim, null,
                    edge, sink, clock, rng);
        } catch (RuntimeException accessError) {
            return finish(Outcome.SECRET_ACCESS_ERROR, claim, null,
                    edge, sink, clock, rng);
        }

        if (!MessageDigest.isEqual(expected, received)) {
            return finish(Outcome.MAC_MISMATCH, claim, null,
                    edge, sink, clock, rng);
        }

        // Chỉ từ đây metadata có thể được gọi MAC-verified.
        NonceScope scope = new NonceScope(
                key.ref().audience(), key.ref().clientId(),
                r.nonce());
        final boolean reserved;
        try {
            reserved = nonces.reserve(
                    scope, now, NONCE_TTL_SECONDS);
        } catch (RuntimeException storeError) {
            return finish(Outcome.INTERNAL_ERROR, claim, key,
                    edge, sink, clock, rng);
        }
        return finish(
                reserved ? Outcome.AUTHENTICATED :
                        Outcome.REPLAY_NONCE,
                claim, key, edge, sink, clock, rng);
    }

    // Business authorization độc lập, owner lấy từ trusted database.
    public static boolean authorize(
            AuthResult authn, String ownerFromDb,
            AuditSink sink, Clock clock, SecureRandom rng) {
        if (authn == null
                || authn.outcome() != Outcome.AUTHENTICATED) {
            return false;
        }
        boolean allowed =
                authn.verifiedClientId().equals(ownerFromDb);
        sink.append(new AuditEvent(
                id(rng), clock.instant(), "AUTHORIZATION",
                "APPLICATION", authn.verifiedClientId(),
                null, null, authn.edgeRequestId(),
                null, null, authn.verifiedClientId(),
                authn.verifiedKeyId(),
                allowed ? "ALLOWED" : "DENIED"));
        return allowed;
    }

    private static void require(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    private static void knownAnswer()
            throws GeneralSecurityException {
        // RFC 4231 Test Case 1 (HMAC-SHA-256).
        byte[] secret = new byte[20];
        Arrays.fill(secret, (byte) 0x0B);
        String actual = HexFormat.of().formatHex(
                hmac(secret, "Hi There".getBytes(
                        StandardCharsets.US_ASCII)));
        require(actual.equals(
                "b0344c61d8db38535ca8afceaf0bf12b"
              + "881dc200c9833da726e9376c2e32cff7"),
                "HMAC RFC4231 known-answer");
    }

    private static Request request(
            long timestamp, String nonce, byte[] body) {
        return new Request(
                "POST", "/v1/orders?mode=commit",
                "application/json", Long.toString(timestamp),
                nonce, body);
    }

    private static void race(
            Request request, String header,
            Map<KeyRef, KeyMetadata> metadata,
            MockSecretProvider provider,
            SecretCache cache, AuditSink sink,
            Clock clock, SecureRandom rng) throws Exception {
        int workers = 8;
        NonceStore shared = new NonceStore();
        ExecutorService pool =
                Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<AuthResult>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < workers; i++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    start.await();
                    return authenticate(
                            request, List.of(header), metadata,
                            provider, cache, shared, sink, clock, rng);
                }));
            }
            require(ready.await(10, TimeUnit.SECONDS),
                    "Workers ready");
            start.countDown();
            int accepted = 0, replayed = 0;
            for (Future<AuthResult> f : futures) {
                Outcome kind = f.get().outcome();
                if (kind == Outcome.AUTHENTICATED) accepted++;
                if (kind == Outcome.REPLAY_NONCE) replayed++;
            }
            require(accepted == 1, "Exactly one nonce winner");
            require(replayed == workers - 1,
                    "Every duplicate rejected");
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        knownAnswer();
        SecureRandom rng = new SecureRandom();
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"),
                ZoneOffset.UTC);
        long now = clock.instant().getEpochSecond();
        InMemoryAuditSink sink = new InMemoryAuditSink();
        MockSecretProvider provider = new MockSecretProvider();
        Map<KeyRef, KeyMetadata> keys = new HashMap<>();
        NonceStore nonces = new NonceStore();

        KeyRef old = new KeyRef(
                AUDIENCE, "merchant-17", "k-old");
        KeyRef current = new KeyRef(
                AUDIENCE, "merchant-17", "k-new");
        KeyRef other = new KeyRef(
                AUDIENCE, "merchant-42", "k-42");
        SecretRef oldVersion =
                new SecretRef("secret-017", "v6");
        SecretRef newVersion =
                new SecretRef("secret-017", "v7");
        SecretRef otherVersion =
                new SecretRef("secret-042", "v1");

        byte[] oldSecret = new byte[32];
        byte[] newSecret = new byte[32];
        byte[] otherSecret = new byte[32];
        rng.nextBytes(oldSecret);
        rng.nextBytes(newSecret);
        rng.nextBytes(otherSecret);
        provider.register(oldVersion, oldSecret);
        provider.register(newVersion, newSecret);
        provider.register(otherVersion, otherSecret);

        keys.put(old, new KeyMetadata(
                old, oldVersion, KeyState.VERIFY_ONLY, now + 120));
        keys.put(current, new KeyMetadata(
                current, newVersion, KeyState.ACTIVE, 0));
        keys.put(other, new KeyMetadata(
                other, otherVersion, KeyState.ACTIVE, 0));

        byte[] body = "{\"orderId\":\"o-123\",\"amount\":150000}"
                .getBytes(StandardCharsets.UTF_8);
        try (SecretCache cache = new SecretCache()) {
            Request first = request(now, id(rng), body);
            String oldHeader = sign(first, old, oldSecret);
            AuthResult r1 = authenticate(first, List.of(oldHeader),
                    keys, provider, cache, nonces, sink, clock, rng);
            require(r1.outcome() == Outcome.AUTHENTICATED,
                    "Old key VERIFY_ONLY accepted");
            require("k-old".equals(r1.verifiedKeyId()),
                    "Verified key ID is trusted metadata");

            // MAC replay đúng toán học, nonce đã dùng.
            AuthResult replay = authenticate(first,
                    List.of(oldHeader), keys, provider, cache,
                    nonces, sink, clock, rng);
            require(replay.outcome() == Outcome.REPLAY_NONCE,
                    "Same nonce rejected");
            require(replay.verifiedClientId() == null,
                    "Replay does not create authenticated principal");

            // Key mới cùng client không reset nonce scope.
            require(authenticate(first,
                    List.of(sign(first, current, newSecret)),
                    keys, provider, cache, nonces, sink, clock, rng)
                    .outcome() == Outcome.REPLAY_NONCE,
                    "Cross-key same-client replay rejected");

            // Client khác với own secret được dùng cùng nonce.
            require(authenticate(first,
                    List.of(sign(first, other, otherSecret)),
                    keys, provider, cache, nonces, sink, clock, rng)
                    .outcome() == Outcome.AUTHENTICATED,
                    "Per-client nonce isolation");

            // Sai MAC không reserve nonce.
            Request protectedRequest = request(now, id(rng), body);
            String good = sign(
                    protectedRequest, current, newSecret);
            Credential credential =
                    parseAuthorization(List.of(good));
            byte[] tamperedTag = decodeTag(
                    credential.signature());
            tamperedTag[0] ^= 1;
            String badSignature = Base64.getUrlEncoder()
                    .withoutPadding()
                    .encodeToString(tamperedTag);
            String bad = good.replace(
                    credential.signature(), badSignature);
            AuthResult wrong = authenticate(
                    protectedRequest, List.of(bad), keys,
                    provider, cache, nonces, sink, clock, rng);
            require(wrong.outcome() == Outcome.MAC_MISMATCH,
                    "Wrong MAC rejected");
            require(authenticate(protectedRequest,
                    List.of(good), keys, provider, cache, nonces,
                    sink, clock, rng).outcome()
                    == Outcome.AUTHENTICATED,
                    "Forged request did not poison nonce");

            // Key REVOKED phải fail dù plaintext vẫn cached.
            keys.put(old, new KeyMetadata(
                    old, oldVersion, KeyState.REVOKED, 0));
            Request staleKey = request(now, id(rng), body);
            require(authenticate(staleKey,
                    List.of(sign(staleKey, old, oldSecret)),
                    keys, provider, cache, nonces, sink,
                    clock, rng).outcome() == Outcome.KEY_REVOKED,
                    "Revoked key fails with cached bytes");

            Request tooOld = request(now - 301, id(rng), body);
            require(authenticate(tooOld,
                    List.of(sign(tooOld, current, newSecret)),
                    keys, provider, cache, nonces, sink,
                    clock, rng).outcome()
                    == Outcome.TIMESTAMP_OUT_OF_WINDOW,
                    "Stale timestamp rejected");

            // Truy cập provider bởi actor không được phép.
            boolean denied = false;
            try {
                byte[] unused = provider.read(
                        oldVersion, "unauthorized-workload",
                        id(rng), sink, clock, rng);
                Arrays.fill(unused, (byte) 0);
            } catch (SecurityException expected) {
                denied = true;
            }
            require(denied, "Unauthorized workload cannot read");

            // Sink unavailable phải ngăn material use/authentication.
            Request noAudit = request(now, id(rng), body);
            String noAuditHeader = sign(
                    noAudit, current, newSecret);
            sink.setAvailable(false);
            AuthResult blocked = authenticate(
                    noAudit, List.of(noAuditHeader), keys,
                    provider, cache, nonces, sink, clock, rng);
            require(blocked.outcome() == Outcome.AUDIT_UNAVAILABLE,
                    "Mandatory audit failure must fail closed");
            sink.setAvailable(true);
            require(authenticate(noAudit,
                    List.of(noAuditHeader), keys,
                    provider, cache, nonces, sink, clock, rng)
                    .outcome() == Outcome.AUTHENTICATED,
                    "No nonce reserved when access audit failed");

            // Business authorization riêng với authentication.
            require(!authorize(r1, "merchant-42",
                    sink, clock, rng), "Other tenant denied");
            require(authorize(r1, "merchant-17",
                    sink, clock, rng), "Owner authorized");

            Request racing = request(now, id(rng), body);
            race(racing, sign(racing, current, newSecret),
                    keys, provider, cache, sink, clock, rng);

            List<AuditEvent> events = sink.snapshot();
            long reads = events.stream()
                    .filter(e -> e.eventType().equals(
                            "SECRET_MATERIAL_READ_ALLOWED"))
                    .count();
            long hits = events.stream()
                    .filter(e -> e.eventType().equals(
                            "SECRET_CACHE_HIT")).count();
            require(reads >= 3 && hits >= 1,
                    "Distinct provider read and application cache hit");
            require(events.stream().anyMatch(
                    e -> e.eventType().equals(
                            "SECRET_MATERIAL_READ_DENIED")),
                    "Denied provider access audited");

            for (AuditEvent e : events) {
                if ("MAC_MISMATCH".equals(e.outcome())
                        || "KEY_REVOKED".equals(e.outcome())
                        || "KEY_NOT_FOUND".equals(e.outcome())) {
                    require(e.verifiedKeyId() == null,
                            "Failed MAC/key never becomes verified ID");
                }
                if ("REPLAY_NONCE".equals(e.outcome())) {
                    require(e.verifiedKeyId() != null,
                            "MAC matched but replay rejected");
                }
            }
            String auditText = events.toString();
            require(!auditText.contains(
                    HexFormat.of().formatHex(newSecret)),
                    "No plaintext secret in audit");
            require(!auditText.contains(
                    credential.signature()),
                    "No full HMAC tag in audit");
            require(!auditText.contains("\"orderId\""),
                    "No raw body in audit");
        }
        Arrays.fill(oldSecret, (byte) 0);
        Arrays.fill(newSecret, (byte) 0);
        Arrays.fill(otherSecret, (byte) 0);
        System.out.println("PASS HMAC secret access audit tests");
    }
}
~~~

### 9.2. Biên dịch và chạy

Lưu mã vào `SecretAccessAuditDemo.java`, sử dụng JDK 17 hoặc mới hơn:

~~~bash
javac SecretAccessAuditDemo.java
java SecretAccessAuditDemo
~~~

Kết quả **kỳ vọng** của demo:

~~~text
PASS HMAC secret access audit tests
~~~

Mã chưa được chạy trong bước soạn Markdown này. Biên dịch/kiểm thử thực tế và vòng QA chuyên môn thuộc bước kiểm tra tiếp theo của pipeline.

### 9.3. Ý nghĩa security của chương trình

| Test | Kỳ vọng |
|---|---|
| Known-answer HMAC-SHA-256 RFC 4231 | JCA tính đúng tag thuật toán cơ sở |
| Key `VERIFY_ONLY` chưa hết deadline | Secret được fetch đúng version và MAC có thể pass |
| Request phát lại nguyên văn | MAC đúng, nonce store reject |
| Key ID mới của cùng client dùng lại nonce | Replay reject vì scope không chứa keyId |
| Client khác dùng nonce giống nhau | Hợp lệ theo per-client namespace khi MAC riêng đúng |
| MAC sai với nonce mới | Reject, không chiếm nonce |
| Request thật sau MAC giả | Có thể pass, không bị poisoning |
| Key `REVOKED` nhưng secret còn cached | Reject từ metadata/policy trước khi dùng plaintext |
| Timestamp cũ 301 giây | Reject dù client biết shared secret |
| Actor không được phép gọi provider mock | Denied event, không trả bytes |
| Mandatory audit sink down | Request không được authenticated |
| Audit sink restored, cùng nonce chưa reserve | Request có thể được xử lý nếu còn freshness |
| Provider read và cache hit | **Hai event types có provenance khác** |
| Authorization resource khác tenant | Authn có thể pass, authz deny |
| Tám attempts cùng nonce đồng thời | **Một** authn success trong một JVM |
| Audit data model | Không chứa raw secret, raw tag, raw body theo schema demo |

### 9.4. Điều code không tự chứng minh

- **Provider giả**, không phải AWS Secrets Manager, GCP Secret Manager, Azure Key Vault hoặc KMS audit thật. Production phải xem docs/permissions/provider log delivery thực tế.
- `InMemoryAuditSink` **không durable**, không WORM, không có integrity proofs; boolean `available` chỉ mô phỏng fail closed.
- `SecretCache` chỉ được synchronized trong **một JVM**, không có background eviction hoặc cross-process invalidation. Provider mock cũng giữ secret bytes trong RAM.
- `SecretLease.close` best-effort wipe bản copy; JCA, GC và process memory có thể có copies không thể bảo đảm xóa sạch.
- `NonceStore` trong JVM không bảo đảm atomicity giữa nhiều verifier nodes/regions; cần shared consistent store với TTL thật.
- Key metadata tạo sẵn trong RAM, chưa có IAM permission evaluation, key-store consistency/versioning, mTLS hoặc real key rotation cutover.
- Hợp đồng canonical request demo hạn chế method/raw target/content-type/body; HTTP adapter thật phải reject duplicate signed fields và bảo toàn raw bytes qua proxy.
- Code dùng `Clock.fixed` phục vụ deterministic tests; production cần clock đồng bộ và server-side timestamps đáng tin.
- Audit model không phải business ledger; transaction durability/idempotency phải được thiết kế riêng.
- Test so sign/verify cùng helper có thể cùng lỗi canonicalization. Cần golden fixtures cross-language và end-to-end test với gateway thực.
- Việc kiểm `events.toString()` không chứa chuỗi secret chỉ là **sanity check**, không chứng minh hệ thống logging production không rò rỉ.


## 10. Ma trận kiểm thử secret access audit

### 10.1. Tách material read, cache access và HMAC outcomes

| Case | Nguồn material | Authentication result | Audit bắt buộc phân biệt |
|---|---|---|---|
| A1 — Cold cache, key ACTIVE, MAC đúng | Secret Manager read | `AUTHENTICATED` nếu nonce mới | `SECRET_MATERIAL_READ_ALLOWED` (provider) + `CACHE_MISS` (app) + `HMAC_AUTHENTICATED` (app) |
| A2 — Warm cache, key ACTIVE, MAC đúng | Cache hit | `AUTHENTICATED` nếu nonce mới | **Không bịa provider read mới**; `CACHE_HIT` và authn event |
| A3 — Cold cache, MAC sai | Provider read candidate secret có thể xảy ra | `MAC_MISMATCH` | Actor của read là verifier workload; client claim vẫn unverified |
| A4 — Warm cache, MAC sai | Cache hit | `MAC_MISMATCH` | App cache-use khác HMAC authenticated |
| A5 — Key không tồn tại | Không có valid version | `KEY_NOT_FOUND` | Không log material read thành công |
| A6 — Key REVOKED còn trong cache | Không nên dùng cached bytes để verify | `KEY_REVOKED` | Key state terminal event, không nhận MAC chỉ vì có material |
| A7 — Key VERIFY_ONLY còn hạn | Provider/cache theo version cũ | Có thể authenticated | Log đúng version/role, giúp migration |
| A8 — Key VERIFY_ONLY quá deadline | Không fetch chỉ để thử | `KEY_EXPIRED` | Version/state từ trusted metadata |
| A9 — Timestamp quá cũ | Có thể reject trước fetch | `TIMESTAMP_OUT_OF_WINDOW` | Không đếm authenticated |
| A10 — Nonce đã dùng, MAC đúng | Provider read hoặc cache hit | `REPLAY_NONCE` | Có thể đã dùng secret, **không phải authn success** |
| A11 — Store nonce unavailable | Có thể MAC đúng | Reject/fail closed | `NONCE_STORE_UNAVAILABLE`, không làm business |
| A12 — Secret Manager access denied | Không nhận plaintext | Reject | Provider `READ_DENIED` với workload actor, không chứa secret |
| A13 — Secret Manager timeout | Không nhận plaintext | Reject | Provider/app `READ_ERROR` sanitized |
| A14 — Mandatory audit sink down | Không được trả result thành công | Fail closed | Có trạng thái không thể audit; không nói event đã persist |
| A15 — Cache expired, version vẫn active | Provider fetch lại | Theo kết quả MAC/nonce | `CACHE_MISS` + provider read mới |
| A16 — Key rotation sang v8 | Provider fetch v8 nếu cold | Theo key state/secret mới | `targetVersionId=v8`, không đồng nhất alias |
| A17 — Key bị revoke sau khi cached | Material còn ở RAM một thời gian | Reject | Revocation policy thắng cache hit |
| A18 — Client B dùng cùng nonce như A | Secret B/version B | Có thể authenticated theo scope riêng | Phân biệt authenticated client/audience |
| A19 — Authenticated A gọi resource B | Không đổi secret access decision | `AUTHORIZATION_DENIED` | Authn success nhưng authz deny |
| A20 — Side effect chưa rõ do timeout | Không thể suy chỉ từ HMAC | Cần reconciliation | Audit authentication khác ledger/idempotency |

Mỗi case cần **expected events độc lập**, không chỉ kiểm “log không null”. Đặc biệt, A3 không nên bị diễn giải thành “client có MAC sai đã **đọc secret**”: actor provider read vẫn là **server workload**, không phải principal tự khai.

### 10.2. Key ID và version isolation

Một số property tests:

- Với cùng text `keyId=k1` nhưng hai tenants A và B, metadata lookup phải trả **đúng audience/client/version**, không lấy nhầm secret.
- Với cùng client và hai keys trong rotation, MAC tính bằng secret v6 không tự khớp v7.
- Audit material read `secretRecordId/v6` khác `secretRecordId/v7`; không chỉ ghi mutable alias `latest`.
- Nếu revoked version v6 còn trong cache, không dùng nó để accept request mới.
- Nếu request tự đổi `key_id` sau khi ký, expected MAC phải fail hoặc lookup reject.
- Nếu một workload không có IAM permission tới production version v7, read denied **không trả secret bytes**.
- Key selection không được thử lần lượt toàn bộ secret store, tránh cross-tenant confusion, timing oracle và amplification DoS.
- Đăng ký key mới phải có **lifecycle event và immutable version metadata**, không reuse record ID để xóa dấu vết.

### 10.3. Negative tests cho HTTP/gateway

| Input/thay đổi | Rủi ro | Expected |
|---|---|---|
| Hai `Authorization` fields | Gateway/backend chọn first/last | Reject multiplicity trước secret lookup |
| Duplicate `X-Nonce` / `X-Timestamp` | Hai tầng parse khác nhau | Reject |
| Client header `X-Verified-Client: merchant-admin` | Giả principal | Strip ở ingress, không tin để lấy secret |
| `X-Key-Id` chứa CR/LF | Log injection/request smuggling | Reject HTTP parsing |
| Gateway decode/reorder query trước verify | Canonical bytes đổi | MAC fail hoặc verify tại boundary đúng |
| Proxy reserialize JSON body | SHA-256 raw bytes đổi | MAC fail theo contract |
| CDN cache response trước authn | Bypass verified principal | Không dùng public cache sai chính sách |
| Gateway auto-retry POST với cùng nonce | Replay bị phát hiện | Retry phải ký timestamp/nonce mới, giữ idempotency key cho same intent |
| Gateway rewrite signed request ID | HMAC fail | Dùng server edgeRequestId riêng |
| HTTP/1.1↔HTTP/2 mapping | `:method`/`:path` khác origin-form | Cross-protocol golden fixtures |
| Proxy log raw Authorization | Lộ credential/tag | Redact trước logging |
| Gateway và backend key-state cache khác nhau | Revoked vẫn được verify ở node cũ | Policy/version consistency, invalidation/fail-safe |

**Integration tests** nên đi qua chính tuyến gần production: SDK → TLS/WAF → gateway → verifier → metadata/secret stores → nonce store → authorization. So sánh **raw method/target/headers/body** và các event IDs giữa từng tầng bằng **test data không nhạy cảm**.

### 10.4. Load, concurrency, multi-AZ và failover

1. Gửi 100 HTTP attempts với cùng key vào cache trống. Trong một JVM synchronized demo, chỉ một fetch cần thiết; trong production nhiều nodes có thể có **một fetch trên mỗi node**, tùy chính sách. Audit phải phản ánh **sự kiện thật**, không hứa count cố định toàn cluster nếu chưa có single-flight phân tán.
2. Gửi 100 attempts với các nonce mới: số `HMAC_AUTHENTICATED` có thể cao hơn số provider reads; metric phải ghi đúng nguồn.
3. Gửi 100 attempts **cùng nonce** qua nhiều verifiers, yêu cầu **tối đa một** vượt qua atomic nonce reservation trên toàn cluster.
4. Revoke key trong khi nhiều nodes có cache. Theo propagation SLA, mọi node phải áp key-state policy an toàn; test stale caches và race.
5. Chặn network tới Secret Manager: cache hit có thể tiếp tục **chỉ nếu key policy và cache lease vẫn hợp lệ**; cache miss phải fail closed, không dùng fallback secret.
6. Chặn audit sink: nếu audit mandatory thì không release material mới và không trả authenticated success; nếu durable queue được cho phép phải có bằng chứng event đã persist trong queue.
7. Chặn KMS decrypt: ứng dụng không log ciphertext/plaintext/error chứa material, không chọn secret khác “cho chạy được”.
8. Cho audit exporter retry cùng `eventId`: sink không double-count.
9. Cho clock drift: `occurredAt` vẫn là server time được ghi theo source, `X-Timestamp` chỉ là signed claim.
10. Test key alias trỏ sang immutable version mới, không mix material version của old/new trong cache key.
11. Test provider/access log không còn được truyền tới SIEM vì regional outage: alert, queue lag, replay/dedup khi phục hồi.
12. Test concurrent key rotation và request verification: việc đổi metadata state phải có ranh giới áp dụng nhất quán.

### 10.5. Audit sink failure: không đánh tráo nghĩa

Một lỗi dễ mắc:

~~~text
service:
  result = secretManager.getSecretValue()
  log("READ_ALLOWED")  // logging fails, nhưng service vẫn trả bytes
  return result
~~~

Nếu policy bắt buộc audit durable trước khi release plaintext, kiểu trên **vi phạm policy**. Có thể sử dụng provider audit origin đã được quản lý và/hoặc một service có transactional/durable intent logging. Ví dụ Java trong bài chỉ minh họa audit callback **trước khi return copy**; nó **không bảo đảm atomic transaction giữa external Secret Manager và audit sink thực tế**. Một success event được ghi trước return chỉ chứng minh provider/adapter đã quyết định trả material, không tự bảo đảm consumer đã sử dụng nó.

Khi cần chứng minh, định nghĩa rõ:
- `ACCESS_REQUESTED`: một attempt đã bắt đầu, có thể chưa có plaintext.
- `ACCESS_ALLOWED`: policy cho phép.
- `MATERIAL_DELIVERED`: material được trả từ provider boundary theo ngữ nghĩa provider hỗ trợ.
- `MATERIAL_USED`: ứng dụng cho phép phép MAC/decrypt bắt đầu; không có nghĩa MAC match.
- `AUTHENTICATED`: request đã qua full verifier/freshness/nonce.
- `BUSINESS_COMMITTED`: phải dựa vào transaction/ledger, không suy từ access event.

Không dùng một `success=true` cho mọi stage.

## 11. Playbook điều tra truy cập secret bất thường

### 11.1. Tín hiệu cần xem xét

| Dấu hiệu | Giả thuyết khả dĩ | Cách xác minh |
|---|---|---|
| Actor mới đọc nhiều production secrets | Compromised IAM / permission quá rộng | IAM identity, source, policy, change approvals |
| `GetSecretValue` tăng đột biến | Cache flush, autoscaling, tấn công lookup hoặc leak | Deployment changes, cache miss rates, request outcomes |
| Material reads ngoài giờ vận hành | Break-glass, scheduled job hoặc abuse | Ticket/approval, SSO, workload identity |
| Reads của secret `REVOKED` | Stale config, unauthorized access, test/rollback | Key lifecycle event, client/cache state |
| App có cache hits nhưng không provider events | Có thể hợp lệ | Kiểm cache load history, lease, version |
| Provider read ALLOWED nhưng HMAC liên tục fail | Candidate key lookup do traffic giả, mismatch SDK | Correlation, signed canonical contract, rate limits |
| Authenticated với key cũ sau deadline | Key-store state stale | Region/node/version, revocation propagation |
| Audit queue lag/dropped events | Mất khả năng forensic | Exporter health, durable buffer, alerts |
| SIEM có raw secret/tag/body | Logging leak | Truy vết sources, hạn chế access, rotate credential |
| Key ID scanning từ Internet | Enumeration/DoS | Claimed vs verified, throttle, uniform external errors |

### 11.2. Quy trình xử lý nghi ngờ lộ shared secret

Một playbook thực tế (tùy chính sách tổ chức):

1. **Phát hiện và phân loại:** xác định event types, provider actor/source, secret record/version, khả năng plaintext đã bị trả, SIEM/audit retention.
2. **Giữ chứng cứ:** bảo toàn platform logs, access-policy changes, key lifecycle metadata, app events và event IDs trong storage có integrity/access controls.
3. **Khoanh vùng:** xác định audience/client/key versions bị tác động và các workloads có quyền đọc; không tự công bố raw secret trong ticket.
4. **Thu hẹp quyền:** thu hồi IAM permissions không cần, vô hiệu hóa compromised workload identity/service tokens, áp quotas nếu phù hợp.
5. **Rotate/revoke:** phát secret mới theo quy trình an toàn, cắt hiệu lực secret cũ và đồng bộ key-store state/cache invalidation.
6. **Kiểm request forgery:** đối chiếu authenticated events, key IDs, timestamp skew, nonce outcomes, authorization/ledger; secret lộ có thể cho attacker tạo request mới với nonce mới.
7. **Khắc phục nguồn lộ:** app logs, environment variables, debug endpoints, heap dumps, CI/CD, backup policy, KMS policy.
8. **Xác thực phục hồi:** negative tests với revoked key, provider DENIED từ actor trái quyền, multi-node cutover, audit sink deliveries.
9. **Hậu kiểm:** cập nhật threat model, IAM least privilege, alert thresholds, incident playbook và client communications theo policy.

**Nonce anti-replay không cứu được compromised secret**: attacker có thể ký HMAC mới với timestamp/nonce mới. Cần revoke key và authorization/rate limits, không chỉ chặn nonce đã thấy.

### 11.3. Break-glass audit phải mạnh hơn read thông thường

Nếu operator cần truy cập khẩn cấp:

~~~text
actorType             = HUMAN
actorId               = authenticated SSO identity
operation             = BREAK_GLASS_SECRET_ACCESS
targetSecretRecordId  = opaque record identifier
targetVersionId       = immutable version
reasonCode            = INCIDENT_RESPONSE
approvalId            = approved ticket / dual approval if required
sessionId             = restricted emergency session
mfaState              = verified
expiresAt             = short-lived elevation deadline
outcome               = ALLOWED / DENIED / ERROR
notified              = security responders
~~~

Phải xác minh permission trước khi trả plaintext; hạn chế scope/time, có alert gần real-time, hậu kiểm và revoke elevation sau sự cố. Không chỉ ghi `actor=admin` — đó có thể là một role dùng chung không đủ trách nhiệm cá nhân.

### 11.4. Bản đồ các loại bằng chứng

| Nguồn | Độ tin cậy/câu hỏi | Giới hạn |
|---|---|---|
| Provider IAM/KMS logs | Authenticated workload nào gọi provider API? | Không thấy mọi cache use |
| Application cache events | Bản version nào được process sử dụng? | App bị compromise có thể giả/xóa |
| HMAC authentication events | Request nào MAC/freshness/nonce pass? | Shared secret không có non-repudiation |
| Key lifecycle events | Key state/policy thay đổi khi nào, ai làm? | Không chứng minh mọi RAM copy bị xóa |
| Authorization events | Ai có quyền action/resource? | Không chứng minh business commit |
| Business ledger/outbox | Transaction nào thật sự commit? | Không thay security provenance |
| Change approvals/CI deploy | Sự kiện có trùng change window? | Cần kiểm approval authenticity |
| Audit integrity proofs | Event histories có bị thay/xóa? | Phụ thuộc cách bảo vệ log signing key |

## 12. Những sai lầm thường gặp

1. **Gán HTTP `client_id` làm actor của Secret Manager read:** actor thật là workload/API caller đã IAM-authenticated.
2. **Dùng provider-read count làm HTTP request count:** cache có thể phục vụ nhiều MAC verifications.
3. **Gắn `provenance=PLATFORM` cho event app tự phát:** tạo cảm giác tin cậy giả.
4. **Không phân biệt material read và metadata lookup:** sai mức nhạy cảm.
5. **Dùng một field `keyId` cho HMAC key, KMS wrapping key và secret version:** forensic nhập nhằng.
6. **Không ghi immutable version:** không xác định được secret nào đã được trả.
7. **Log secret/expected MAC/raw Authorization để debug:** tự tạo đường rò rỉ.
8. **Đưa token IAM/Secret Manager credentials vào application audit:** credential disclosure.
9. **Cho verifier quyền list/export/delete tất cả secrets:** vi phạm least privilege.
10. **Tin header `purpose` từ request là quyền đọc secret:** client có thể tự khai.
11. **Thấy `GetSecretValue ALLOWED` rồi kết luận client đã authenticated:** MAC có thể sai.
12. **Thấy `MAC_VERIFIED` rồi bỏ timestamp/nonce:** replay vẫn có tag đúng.
13. **Chấp nhận `REVOKED` vì cache còn material:** bypass key policy.
14. **Cho cache TTL dài vô hạn không invalidation:** lạm dụng credential bị thu hồi.
15. **Fallback secret cũ khi KMS timeout:** có thể dùng key đã revoke hoặc sai tenant.
16. **Dùng `X-Verified-Client` do client tự đặt:** giả principal và sai audit.
17. **Không ký client/key ID vào canonical bytes:** attacker đổi selector ngoài message.
18. **Chỉ log HTTP 401 mà không có reason/stage:** khó phân biệt IAM denied, wrong MAC và stale timestamp.
19. **Dùng `claimedKeyId` làm metric label không giới hạn:** attacker gây cardinality explosion.
20. **Logger nối raw header không escape:** log injection và parser confusion.
21. **Không kiểm audit sink outage:** giả định một event đã persist dù chỉ ở RAM.
22. **Bỏ audit do log volume cao mà không policy:** tạo blind spot bắt buộc.
23. **Coi `Arrays.fill` là xóa sạch mọi bản copy trong JVM:** không thể bảo đảm.
24. **Tin HMAC mang non-repudiation tuyệt đối:** server/client có cùng secret.
25. **Tin authn pass đồng nghĩa authz pass:** resource ownership/action vẫn phải kiểm.
26. **Nhầm nonce TTL với secret lease TTL:** mục tiêu và threat window khác nhau.
27. **Không audit break-glass và IAM grant changes:** thiếu context cho high-risk material reads.
28. **Không giữ tombstones key version:** forensic không giải thích được log sau rotate/delete.

## 13. Bài tập thực hành

**Bài 1 — Actor vs client.** Request khai `client_id=merchant-a`, verifier `svc-verifier-prod` dùng quyền IAM đọc secret từ provider rồi MAC sai. Ai là actor của `SECRET_MATERIAL_READ_ALLOWED`? Trong request audit, `verifiedClientId` được set hay vẫn null?

**Bài 2 — Cache.** Một verifier xử lý 10.000 requests nhưng chỉ đọc Secret Manager 5 lần. Đây có chắc là thiếu 9.995 audit records không? Phân biệt yêu cầu per-material-read với per-secret-use.

**Bài 3 — KMS.** Secret được mã hóa bằng wrapping key K1; HMAC client có credential key ID C1 và secret version V1. Hãy thiết kế event có các field tách ba ID, tránh nhầm các rotations.

**Bài 4 — Metadata.** Server chỉ lookup key record state và secret locator nhưng chưa decrypt. Có được ghi `SECRET_MATERIAL_READ_ALLOWED` không? Nên ghi gì?

**Bài 5 — IAM.** Thiết kế policy cho `svc-hmac-verifier-prod` chỉ đọc HMAC secrets của audience production; nó có nên được grant quyền `RotateSecret` hoặc `DeleteSecret` không?

**Bài 6 — Denied.** Một workload không có quyền gọi Secret Manager `GetSecretValue`. Event nào xuất hiện? Làm sao chứng minh không có plaintext trả về ở ranh giới được kiểm soát?

**Bài 7 — Audit sink.** Nếu audit bắt buộc durable trước khi release material và sink down, có thể tiếp tục trả secret từ cache không? Policy cần xác định gì cho mỗi use và mỗi read?

**Bài 8 — Rotation.** Client A có key old VERIFY_ONLY và key new ACTIVE. Một request dùng old đến sau deadline, secret vẫn trong cache. Kết quả authn phải thế nào?

**Bài 9 — Replay.** MAC đúng và cache hit, nhưng nonce đã dùng. `SECRET_CACHE_HIT` có thể đúng trong khi `HMAC_AUTHENTICATED` là false không? Vì sao?

**Bài 10 — Canonical request.** Thêm key ID, audience và method/raw URI vào hợp đồng ký. Tại sao không đưa raw `Authorization` chứa signature vào canonical bytes?

**Bài 11 — Gateway.** Proxy rewrite raw query hoặc JSON body. HMAC và cache/provider audit có thể cho những kết quả khác nhau thế nào?

**Bài 12 — Incident.** Một operator break-glass đọc secret trong production. Liệt kê actor, target version, MFA, approval, duration, reason, outcome và alert cần có.

**Bài 13 — Privacy.** Một developer ghi `SHA-256(raw secret)` vào mọi event. Hash đó có thể là metadata nhạy cảm như thế nào? Có thể dùng identifier nào ít rủi ro hơn?

**Bài 14 — Multi-region.** Một region đã revoke key, region khác còn cached metadata ACTIVE. Làm sao bảo đảm các requests không được accept trái policy? Cần audit version nào?

**Bài 15 — HSM.** Nếu HMAC được tính hoàn toàn trong HSM qua opaque handle, ứng dụng không nhìn thấy plaintext. Event taxonomy cần thay `SECRET_MATERIAL_READ_ALLOWED` thành những operation types nào?

**Bài 16 — Audit integrity.** Một exporter retry gửi cùng event hai lần và sink lưu cả hai. Hãy đề xuất eventId/dedup, append-only integrity và alert cho missing event.

**Bài 17 — Java.** Mở rộng demo với `SecretCache.invalidate` ghi một event `SECRET_CACHE_EVICTED` an toàn. Nếu audit sink down khi invalidate, có nên tiếp tục wipe cache? Hãy giải thích fail-safe behavior.

**Bài 18 — Attribution.** Một HMAC tag match với key v7. Có chứng minh merchant là người duy nhất tạo request không, khi server cũng giữ shared secret? Cần bổ sung kiểm soát chứng cứ nào?

**Bài 19 — Idempotency.** Client retry một payment bằng nonce/timestamp/HMAC mới, giữ idempotency key cũ. Authentication audit sẽ có bao nhiêu attempts và business ledger có thể có bao nhiêu commits?

**Bài 20 — Threat model.** Một credential read được phép từ service account nhưng nguồn truy cập là một pod lạ. Hãy mô tả cách dùng provider audit, workload attestation, deployment logs, IAM policy và alerts để điều tra.

## 14. Checklist triển khai production

| Nhóm | Điều phải xác nhận |
|---|---|
| **Inventory** | Mỗi secret có opaque immutable record/version ID, audience/client owner và chính sách purpose |
| **Identity** | Audit actor của provider là workload/human IAM principal, không là raw HMAC client claim |
| **IAM** | Least privilege, tenant/environment isolation, workload identity, tách quyền rotate/delete |
| **Material access** | `GetSecretValue`/`Decrypt` có đúng provenance, outcome, version, actor và policy |
| **Cache** | Cache hit khác platform read, key gồm immutable version, TTL/revoke invalidation rõ |
| **Memory** | Không tạo `String` secret, zeroize best-effort, bảo vệ heap dumps/debug |
| **Secret transport** | Kênh TLS/mTLS, không phơi plaintext trong error/log/metrics |
| **Signing contract** | Method, raw URI/query, content type, client/key ID, timestamp, nonce, raw body hash đã ký |
| **MAC** | HMAC-SHA-256 tag đầy đủ 32 byte, strict Base64URL, `MessageDigest.isEqual` |
| **Key state** | `ACTIVE/VERIFY_ONLY/REVOKED` theo server-managed time và trusted store |
| **Replay** | Timestamp seconds, nonce CSPRNG, atomic per-authenticated-client store, TTL phủ full window |
| **Authn/authz** | Principal chỉ sau MAC/freshness/nonce; quyền resource được kiểm riêng |
| **Event schema** | Version, eventId, occurredAt/ingestedAt, actor, provenance, operation/outcome, target/version |
| **Correlation** | Edge request ID, provider request ID, app trace ID có nguồn/trust rõ |
| **Sensitive fields** | Không log secret, tag, raw Authorization, body hoặc token |
| **Logging security** | Structured serialization, escape, limits, privacy controls và rate limiting |
| **Durability** | Append-only/immutable khi required, durable queue/outbox, retries/dedup, lag alerts |
| **Break-glass** | MFA, approval, time-bound elevation, notification, post-incident review |
| **Key lifecycle** | Created/rotated/revoked/destroyed, actor khác target, immutable version/tombstone |
| **Gateway** | Signed fields bảo toàn, duplicate headers reject, no trusted client-supplied principal headers |
| **Multi-node** | Clock consistency, key-state propagation, shared nonce atomicity, audit events từ mọi region |
| **Testing** | Wrong MAC, stale, replay, denied secret read, sink fail, cache hit/miss, rotation/revoke |
| **Governance** | Audit retention, access reviews, privacy, incident response, controlled export |

## 15. Kết luận

**Audit secret access** không phải việc thêm một dòng `logger.info("key read")`. Nó cần trả lời **actor thực sự nào** truy cập **secret record/version nào**, **thao tác plaintext/metadata/cache hay management nào**, **kết quả gì**, với **nguồn chứng cứ** và **mức bảo vệ log** ra sao.

Trong HMAC request authentication, **workload đọc secret** và **HMAC client gửi request** là hai principal khác nhau. Provider `GetSecretValue` event không chứng minh một client được xác thực; `CACHE_HIT` trong ứng dụng không phải provider read; MAC khớp không tự làm timestamp/nonce hợp lệ; và authentication thành công không cấp quyền trên mọi tài nguyên. Đặc biệt, secret vẫn có thể nằm trong RAM sau revoke hoặc từng bị lộ trước đó, vì vậy audit phải đi cùng IAM, key rotation, cache invalidation, least privilege, incident response và authorization.

Một triển khai có thể điều tra được sẽ có **event taxonomy rõ**, **actor/provenance/immutable secret version**, **no-secret logging**, **durable tamper-resistant audit**, **atomic anti-replay** và các kiểm thử lỗi multi-node/gateway. HMAC dùng shared secret giúp xác thực request, nhưng **không tự mang non-repudiation** và cũng không thay business idempotency hoặc ledger.

**Tài liệu tham khảo:**

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): MAC dựa trên shared secret.
- [RFC 4231 — HMAC-SHA-256 Test Vectors](https://www.rfc-editor.org/rfc/rfc4231): giá trị kiểm chứng HMAC nguyên thủy.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP methods, authorization và semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): message framing và header parsing.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-headers và gateway conversions.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): chuẩn tham khảo, **khác** custom contract `hmac-secret-audit-v1`.
- [RFC 4648 — Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL/padding/canonical encoding.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): xây dựng và vận hành log security.
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): chính sách và vòng đời khóa.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): nội dung cần ghi/tránh ghi, log injection, log protection.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): kiểm soát truy cập, quản lý và bảo vệ secret.
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): `HmacSHA256` của JCA.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 và `isEqual`.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nonce và event identifiers.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): UTC/fixed clock cho tests.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `compute` nguyên tử trong một JVM.
- [Redis — SET command](https://redis.io/docs/latest/commands/set/): `NX`, `EX` và `PX` cho atomic nonce store.







