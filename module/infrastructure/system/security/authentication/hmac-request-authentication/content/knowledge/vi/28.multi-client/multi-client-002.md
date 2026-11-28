# Secret riêng từng client trong xác thực HTTP request bằng HMAC

> **Chương:** Multi-client  
> **Đề bài:** Secret riêng từng client  
> **Module:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request bao gồm phương thức HTTP, URI, header hoặc body theo hợp đồng ký. Người học thực hành xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền.

## 1. Vì sao hệ thống nhiều client cần secret riêng?

Trong mô hình HTTP API dùng HMAC, mỗi client gửi request biết một **shared secret** và server xác minh chữ ký cũng biết đúng secret ấy (hoặc có khả năng thực hiện HMAC bằng key handle). Nếu toàn bộ các client dùng **chung một secret**, chỉ cần một client bị xâm phạm là attacker có thể tính tag HMAC cho request giả mạo client khác, trừ khi có một cơ chế ràng buộc độc lập khác. Đây là lỗi **cross-client impersonation**.

Giải pháp căn bản: cấp **credential material riêng cho từng client**, quản lý danh tính chủ sở hữu của key và không cho verifier tự lựa chọn một secret chung khi lookup gặp lỗi.

~~~text
                              Server / HMAC verifier
                                 (trusted key store)
                                     |
                           +---------+-----------+
                           |                     |
                 Client A  |                     |  Client B
            clientId=A, keyId=A-v1        clientId=B, keyId=B-v1
            secret=KA                     secret=KB
                |                            |
                | sign request with KA       | sign request with KB
                v                            v
              HMAC tag A                   HMAC tag B

Server:
  lookup (audience, client A, key A) -> KA -> verify A
  lookup (audience, client B, key B) -> KB -> verify B

Compromise KA does NOT imply possession of KB.
~~~

Một hệ thống có thể sở hữu **nhiều khóa trong cùng một client**: khóa `ACTIVE` mới và khóa `VERIFY_ONLY` cũ trong giai đoạn rotation. Điều đó không phá quy tắc “secret riêng từng client”: tất cả khóa thuộc client A vẫn phải **tách biệt** với client B.

**Mục tiêu bảo mật quan trọng:** Nếu client A biết `KA`, họ vẫn **không thể** ký một request giả danh client B bằng cách thay `clientId=B` hoặc `keyId=B-v1` trên header. Verifier phải dùng secret của **đúng key record thuộc B**, và canonical request phải ràng buộc client/key ID.

### 1.1. Khác nhau giữa client, principal, key ID và secret

| Thuật ngữ | Vai trò | Điều không được nhầm |
|---|---|---|
| `clientId` | Danh tính ứng dụng/đối tác được cấp credential | Giá trị trong request chỉ là **claim** trước MAC |
| `keyId` | Selector trỏ đến **một phiên bản credential** | Không phải secret; không mặc định unique toàn hệ thống |
| `sharedSecret` | Byte bí mật dùng làm HMAC key | Không được gửi nguyên trong HTTP request hoặc log |
| `audience` | Phạm vi API/environment mà key được phép dùng | Không nên do raw `Host`/untrusted header tùy ý quyết định |
| `keyVersionId` | ID phiên bản bí mật bất biến ở Secret Manager | Có thể khác text `keyId` gửi qua API |
| `authenticatedClientId` | Client đã được server xác minh sau MAC/freshness/nonce | Không nhất thiết có quyền đối với mọi tài nguyên |
| `authorization policy` | Quy tắc client được gọi hành động trên resource nào | Không tự phát sinh từ việc HMAC khớp |

Trong bài dùng chữ **client** cho một machine-to-machine integrator/application được cấp credential. Tùy hệ thống, một khách hàng doanh nghiệp (tenant) có thể có **nhiều client applications**. Vì vậy cần định nghĩa rõ `tenantId` khác `clientId`, tránh mặc định một tenant chỉ có một client.

### 1.2. Mục tiêu học tập

Sau bài, người học có thể:

1. Giải thích tại sao dùng một HMAC shared secret toàn hệ thống nguy hiểm trong multi-client API.
2. Thiết kế record `(audience, clientId, keyId, versionId, state, secretReference)` không trộn tenant.
3. Tra secret bằng tuple đầy đủ và xác thực **key ownership**, không thử mọi secret/fallback default key.
4. Ràng buộc client ID, key ID, method, raw target, timestamp, nonce, body digest vào canonical request.
5. Phân biệt **claim** trước MAC và principal sau khi MAC/freshness/nonce hợp lệ.
6. Chống replay theo phạm vi `(audience, authenticatedClientId, nonce)`, đồng thời cho phép hai client khác nhau dùng trùng nonce tình cờ.
7. Rotate, revoke và audit riêng từng client mà không ngừng mọi client khác.
8. Tổ chức provisioning/KMS/Secret Manager, least privilege và xử lý key leak an toàn.
9. Viết Java 17 signer/verifier minh họa với test cross-client, tampering, revoked key, replay và concurrency.
10. Thiết kế kiểm thử proxy/gateway, idempotency và authorization xuyên tenant.

## 2. Threat model của việc dùng chung secret

### 2.1. Một secret toàn cục làm mất khả năng cách ly

Thiết kế sai:

~~~java
// SAI: Tất cả client dùng chung một HMAC key.
byte[] key = config.get("GLOBAL_HMAC_SECRET");
boolean verified = MessageDigest.isEqual(
        sign(key, canonical(request)), suppliedTag);
String clientId = request.getHeader("X-Client-Id");
// Sai tiếp: coi clientId untrusted thành authenticated principal.
~~~

Nếu client A có key toàn cục, họ có thể tạo canonical request chứa `clientId=B` và tính HMAC hợp lệ. Việc đưa `clientId` vào dữ liệu ký **không thể sửa lỗi** nếu **cùng secret** được phân phát cho mọi client: A có thể ký bất kỳ ID nào.

Thiết kế đúng:

~~~text
request claims:
  audience = orders-api-production
  clientId = client-b
  keyId    = b-2026-11

server trusted lookup:
  keyRef(audience, client-b, b-2026-11) -> secret KB

server verifies:
  HMAC(KB, canonical(... client-b, b-2026-11 ...))
~~~

Request giả danh B được A ký bằng KA sẽ **không khớp**. Verifier **không được** fallback sang KA, một secret chung hoặc duyệt toàn bộ key store để tìm “khóa nào làm MAC khớp”.

### 2.2. Các tình huống cần phân biệt

| Tình huống | Rủi ro | Cơ chế chặn |
|---|---|---|
| A biết secret A, khai `clientId=B` | Giả danh tenant/client B | Lookup chỉ key B + signed client/key IDs |
| A dùng `keyId=A-v1` nhưng khai `clientId=B` | Lấy nhầm key A vì key ID không scoped | Lookup tuple `(audience,client,keyId)` và owner validation |
| Hai client đều có text `keyId=primary` | Key collision ở key store | Namespace per client/audience |
| Attacker đoán key ID B | Key enumeration/DoS | Random high-entropy secret, uniform external errors, throttling |
| Secret A bị lộ | Request giả mạo A | Revoke/rotate A, không ép mọi client rotate nếu độc lập |
| Sender/receiver canonicalization khác nhau | MAC sai, false reject | Versioned canonical contract và golden fixtures |
| Backend chọn key bằng `Host` từ client | Cross-audience secret confusion | Audience từ trusted routing/config |
| Gateway gửi `X-Verified-Client=B` từ Internet | Vượt auth boundary | Strip và chỉ tin principal do verifier tạo |
| Key A vẫn `VERIFY_ONLY` sau deadline | Credential hết hạn được chấp nhận | Key state + server clock |
| Nonce store local ở mỗi replica | Replay cùng client được accept nhiều lần | Shared atomic store và TTL đủ dài |
| Verified client A truy cập order B | Broken object-level authorization | Authorization theo resource owner/action |
| Multi-client cùng one global idempotency key space | Retry A làm kẹt operation B | Scope theo authenticated client/audience |

### 2.3. Secret isolation không đồng nghĩa network isolation

Tách KA và KB ngăn **việc A dùng chính secret của mình để ký B**. Nó không thay thế:

- IAM policy: verifier có quyền đọc **chỉ** secret cần thiết theo audience/environment.
- Transport security: client/server phải sử dụng TLS; HMAC không mã hóa body.
- Key storage: KMS/Secret Manager, giới hạn debug/heap dump/log.
- Rate limiting, abuse detection, credential revocation.
- Authorization trên tài khoản, tổ chức, resource cụ thể.
- Multi-region key-state/nonce consistency.
- Audit, incident response, key rotation automation.

Khi chính **server verifier hoặc secret store** bị xâm nhập, rủi ro có thể lan sang nhiều client nếu workload có quyền đọc hàng loạt secrets. Tách per-client secret **giảm blast radius khi một client bị lộ**, không tự hạn chế mọi rủi ro do compromised server identity.

## 3. Mô hình dữ liệu per-client key store

### 3.1. Record và ràng buộc danh tính

Ví dụ một record **do server quản lý**:

~~~yaml
  # Chỉ minh họa schema; KHÔNG chứa plaintext shared secret.
audience: orders-api-production
clientId: merchant-a
keyId: ma-2026-11
immutableKeyRecordId: credential-001
secretVersionId: v7
state: ACTIVE
verifyOnlyUntilEpochSeconds: null
secretRef: secret-manager-opaque-locator
allowedPurpose: HMAC_VERIFY
ownerTenantId: merchant-a-tenant
~~~

Record cho client B riêng:

~~~yaml
audience: orders-api-production
clientId: merchant-b
keyId: mb-2026-11
immutableKeyRecordId: credential-002
secretVersionId: v2
state: ACTIVE
verifyOnlyUntilEpochSeconds: null
secretRef: another-opaque-locator
allowedPurpose: HMAC_VERIFY
ownerTenantId: merchant-b-tenant
~~~

`secretRef` là handle/locator tin cậy; không bao giờ chứa secret trong bản YAML minh họa. Trong sản phẩm thật, version metadata và key state có thể lưu trong database, KMS hoặc Secret Manager; danh tính client/key phải được kiểm **đồng nhất giữa các nguồn**.

### 3.2. Primary key của credential

Một khóa lookup phù hợp:

~~~text
CredentialRef = (
    serviceAudience,
    clientId,
    keyId
)
~~~

Một client có thể rotate nhiều `keyId`, hai client có thể dùng trùng chuỗi `keyId` nếu namespace tách. Nếu key IDs global unique theo chuẩn nội bộ, vẫn cần owner/audience binding thay vì mặc định chỉ so key ID là đủ.

Không xây lookup theo `keyId` thuần nếu record owner chưa được kiểm:

~~~text
SAI:
  secret = keyStore.get(keyId)
  principal = untrustedHeader("X-Client-Id")

ĐÚNG:
  ref = CredentialRef(trustedAudience, claimedClientId, claimedKeyId)
  record = keyStore.find(ref)
  require record.audience == trustedAudience
  require record.clientId == claimedClientId
  require record.keyId == claimedKeyId
  require state permits verification
  verify MAC with this record's secret
  principal = record.clientId, but only after authn completes
~~~

**Không** duyệt danh sách secrets và nhận first match để đoán client. Ngoài timing/DoS, cách này có thể bỏ qua trạng thái key, cross-tenant scope hoặc làm sai audit attribution.

### 3.3. Mỗi client nhiều keys, không phải mỗi client luôn một key

Trong một thời gian:

| Audience | Client | Key ID | State | Được verify? |
|---|---|---|---|---|
| orders-api-production | A | a-2026-10 | `VERIFY_ONLY` | Có, **chỉ** trước deadline |
| orders-api-production | A | a-2026-11 | `ACTIVE` | Có |
| orders-api-production | B | b-2026-11 | `ACTIVE` | Có |
| orders-api-production | B | b-2026-09 | `REVOKED` | Không |
| orders-api-staging | A | a-staging-01 | `ACTIVE` | Chỉ trong staging audience |

Một client có thể có **nhiều application credentials** nếu mô hình phân vai trò yêu cầu, nhưng phải có owner, scope, audit, rotation policy tường minh. Key ID là selector; **secret bytes của key mới phải độc lập với secret của key cũ**.

### 3.4. Có nên dẫn xuất secret từ client ID?

**Không** dùng `SHA256(clientId)`, `MD5(clientId)`, mã cố định hoặc mật khẩu giống nhau cho mọi khách hàng. Client ID là giá trị công khai/dễ đoán, không đủ entropy.

Cách đơn giản và an toàn: dùng `SecureRandom`/CSPRNG tạo **32 bytes độc lập cho mỗi credential**. Nếu kiến trúc chọn key derivation từ một root secret bằng HKDF, phải có **thiết kế được đánh giá** gồm salt, domain-separated info, context audience/client/version, lifecycle/revoke và bảo vệ root. Không tự đặt `HMAC(master, clientId)` rồi dùng làm mọi credential mà không có cryptographic/key-management review: lộ master sẽ tác động toàn bộ clients, trái với mục tiêu blast-radius isolation.

### 3.5. Isolation theo tenant hay client application?

Ví dụ merchant A sở hữu `checkout-web` và `warehouse-sync`. Nếu hai application cùng dùng một secret, sự cố `warehouse-sync` có thể cho attacker ký request trong scope `checkout-web` khi permissions chung. Nếu nhu cầu phân quyền khác nhau, tạo **client ID/credential riêng cho từng application/workload**, gắn policy theo client. Một tenant có thể chứa nhiều authenticated clients, và authorization dùng mapping tin cậy từ client → tenant/actions/resources.

## 4. Provisioning shared secret riêng cho mỗi client

### 4.1. Tạo secret có đủ entropy

Ví dụ Java 17:

~~~java
SecureRandom rng = new SecureRandom();
byte[] secret = new byte[32]; // 256-bit random key material.
rng.nextBytes(secret);

// Đóng gói secret bằng Secret Manager/KMS workflow.
// KHÔNG print, không serialize vào YAML/git/log.
// KHÔNG coi Base64 là mã hóa bảo vệ secret.
~~~

Cấp đúng **một secret** tới client theo một kênh an toàn, có authentication của người nhận, TLS, thời hạn hiển thị rõ và revocation policy. Thông thường server giữ encrypted/managed copy hoặc key handle. Tránh gửi qua email/chat/ticket không mã hóa, gắn vào URL query string, committed source code hoặc log CI.

### 4.2. Thứ tự provisioning điển hình

~~~mermaid
sequenceDiagram
    participant O as Tenant Admin / Onboarding
    participant P as Credential Provisioning
    participant S as Secret Manager/KMS
    participant M as Key Metadata Store
    participant C as Client Application
    O->>P: Request credential for approved client
    P->>P: Authorize onboarding and audience
    P->>S: Generate/store independent secret version
    S-->>P: Secret record/version + protected delivery
    P->>M: Bind audience/client/keyId/state/owner
    P->>C: Secure one-time delivery of clientId/keyId/secret
    C->>C: Store secret in protected client environment
    C->>P: Acknowledge possession/enable rotation policy
~~~

Control plane nên audit actor, target, secret record/version, issuer, tenant, approval, state transition, thời gian. Audit **không** chứa plaintext key.

### 4.3. Secret retrieval phía verifier

Mô hình material access:

1. Verifier lookup `CredentialRef` trong **trusted metadata store**.
2. Verify key state, audience, owner, immutable version.
3. Dùng workload identity với least privilege lấy đúng secret version (hoặc HSM/MAC handle).
4. Secret Manager/KMS audit material retrieval, version/actor/outcome.
5. HMAC engine dùng secret với canonical bytes; tránh log/heap dumps.
6. TTL cache theo policy, emergency invalidation khi revoke.
7. Không tìm secret tenant khác khi lookup không có kết quả.

**Secret Manager caller là workload verifier**, không phải client tự khai trong HTTP. Một attacker có thể khai client B và khiến verifier cố lookup candidate B; không gán event material read cho B như actor khi MAC chưa được kiểm.

## 5. HMAC canonical request phải ràng buộc đúng client

Một hệ thống per-client secret vẫn có thể lỗi nếu sender và receiver **ký/hiểu các thành phần khác nhau**, hoặc nếu key selectors không được ràng buộc với request.

### 5.1. Hợp đồng giáo dục `hmac-multiclient-v1`

Bài này dùng một hợp đồng **riêng**, không khẳng định tương thích RFC 9421. Canonical request có **11 dòng**:

| Dòng | Giá trị | Quy tắc |
|---|---|---|
| 1 | Contract version | Literal `hmac-multiclient-v1` |
| 2 | Audience | Literal `orders-api-production`, server-controlled |
| 3 | HTTP method | `POST` |
| 4 | Raw request target | `/v1/orders?mode=commit` |
| 5 | Content-Type | `application/json` canonical |
| 6 | Client ID | Claimed ID, được bind với key record |
| 7 | Key ID | Claimed key selector, signed |
| 8 | Timestamp | Unix epoch seconds canonical |
| 9 | Nonce | 16 random bytes/Base64URL no padding |
| 10 | Client request ID | 16 random bytes/Base64URL no padding |
| 11 | Body digest | SHA-256 của **exact raw request body**, lowercase hex |

Nối bằng **LF (`\n`)**, không thêm LF ở cuối, encode UTF-8, rồi:

\[
\text{tag}=\operatorname{HMAC\text{-}SHA256}
  (\text{secret của đúng client/key},\, \text{canonicalBytes}).
\]

Full HMAC-SHA-256 tag dài **32 bytes**, encoded Base64URL không padding dài **43 ký tự**. Signature nằm trong auth-param `signature` của custom `Authorization`; không đưa **nguyên Authorization chứa signature** vào canonical bytes để tránh tự tham chiếu. Timestamp và nonce bắt buộc nằm trong message được ký.

### 5.2. Hai clients gọi cùng endpoint

Client A:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Request-Id: dRGla0slwS-KGNO1VKGbyw
Authorization: HMAC-SHA256 client_id="merchant-a", key_id="a-v1", signature="<tag-A>"

{"orderId":"A-123","amount":150000}
~~~

Client B:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Request-Id: 5nlDi9JUnI0xxnGhWtM0UA
Authorization: HMAC-SHA256 client_id="merchant-b", key_id="b-v1", signature="<tag-B>"

{"orderId":"B-999","amount":150000}
~~~

**Hai clients có thể tình cờ dùng cùng nonce text** và timestamp vì nonce uniqueness **scoped per authenticated client**. Nhưng cần phân biệt HMAC tag vì **secret khác nhau, client/key IDs khác nhau, raw body khác nhau**.

Canonical text cho A:

~~~text
hmac-multiclient-v1
orders-api-production
POST
/v1/orders?mode=commit
application/json
merchant-a
a-v1
1795824000
b75sZVQmhTBcfnX-bNbGqw
dRGla0slwS-KGNO1VKGbyw
<sha256-lowercase-hex-of-A-body>
~~~

`<tag-A>` và digest cuối là **placeholder**; khi chạy phải tạo byte arrays và MAC thực. Timestamp minh họa không mặc nhiên nằm trong cửa sổ tại ngày đang đọc bài.

### 5.3. Custom Authorization grammar (chỉ dành cho bài)

~~~text
Authorization: HMAC-SHA256 client_id="<id>", key_id="<id>", signature="<tag>"
~~~

Quy tắc v1:

- **Đúng một** `Authorization` occurrence; HTTP adapter reject duplicate trước khi lấy một value.
- Đúng ba params theo thứ tự, không có param lặp/`algorithm=none` hoặc param lạ.
- Scheme và param **names** không phân biệt hoa/thường; **values** client/key ID phân biệt chữ hoa/thường.
- Client/key IDs chỉ có `[A-Za-z0-9_-]{1,64}`.
- Signature là **43 Base64URL no-pad characters**, decode **đúng 32 bytes**, round-trip canonical.
- Nonce và request ID gồm **22 Base64URL no-pad characters**, decode **16 bytes**.
- Không tự trim/normalize/percent-decode các giá trị đã ký ngoài contract.
- Không dùng `Proxy-Authorization` thay `Authorization`; đây là hai HTTP fields khác.
- Hợp đồng **không** cho client đàm phán HMAC-SHA1/none/truncated tag.

Trong HTTP authentication nói chung, auth-param grammar linh hoạt hơn subset v1; parser bài này **cố tình strict**. Dùng nó cho API thật phải đối chiếu đúng wire format đã công bố. `Authorization` chỉ là trường mang credentials; nó **không tự cấp business authorization**.

## 6. Chống replay và idempotency theo từng client

### 6.1. Nonce namespace phải theo authenticated client

Một nonce không nên được kiểm theo một global value nếu yêu cầu là mỗi client **có nonce space riêng**. Nếu A dùng `nonce=N`, B vẫn có thể hợp lệ dùng cùng N:

~~~text
NonceScope(
  trustedAudience,
  authenticatedClientId,
  canonicalNonce
)
~~~

**Không** lấy `X-Client-Id` raw từ Internet làm trusted namespace trước MAC. Trình tự đúng:

1. Parse claimed client/key IDs.
2. Key lookup trong trusted store và kiểm key policy.
3. Verify HMAC tag.
4. Đọc authenticated client ID từ **đúng key record**.
5. Reserve `(audience, authenticatedClientId, nonce)` atomically.
6. Nếu nonce đã có thì reject replay; nếu mới thì cho qua anti-replay.

Một attacker không biết secret của A **không được phép chiếm nonce A** bằng request giả vì nonce reservation chỉ xảy ra **sau MAC đúng**.

### 6.2. Key rotation không được reset nonce protection

Trong client A có key cũ `A-old` và key mới `A-new`. Nếu nonce scope chứa key ID, cùng nonce N có thể bị gửi lại dưới key mới mà hệ thống coi như chưa dùng. Hợp đồng bài chọn **không đưa key ID vào nonce scope** để nonce uniqueness theo client **xuyên key rotation**. Key ID vẫn phải nằm trong HMAC canonical bytes và key lookup.

### 6.3. Timestamp window, TTL và atomic store

Policy minh họa:

~~~text
timestamp = Unix epoch seconds canonical
freshness = now - 300 <= timestamp <= now + 300
nonce = 16 bytes CSPRNG; Base64URL no padding, 22 chars
nonce storage scope = (audience, authenticatedClient, nonce)
nonce TTL example = 660 seconds
reservation = atomic insert-if-absent (e.g. Redis SET key 1 NX EX 660)
~~~

Window ±300 s nghĩa là **một signed timestamp có thể hợp lệ trong khoảng 600 giây** từ thời điểm sớm nhất đến muộn nhất. Nếu TTL chỉ 300 giây tính từ lần reserve sớm, record có thể hết hạn trong khi timestamp còn fresh. Có thể dùng 660 giây như ví dụ với operational margin, hoặc thiết kế TTL theo exact remaining validity, phải được phân tích kỹ.

Redis `EX 660` tính **giây**; `PX 660` tính **mili giây** và không tương đương. Nếu nonce store bắt buộc nhưng unavailable, fail closed. `ConcurrentHashMap` chỉ atomic trong một JVM, không giải quyết multi-instance/failover.

### 6.4. Idempotency khác nonce và cũng phải scoped

Với POST tạo payment/order, retry hợp lệ có **timestamp/nonce/request ID/signature mới** nhưng giữ **idempotency key ổn định cho cùng logical operation**. Operation dedup scope thường là:

~~~text
IdempotencyScope(
  serviceAudience,
  authenticatedClientId,
  idempotencyKey
)
~~~

Client A và B được phép trùng text idempotency key mà không chặn nhau. Fingerprint method/raw target/content-type/body giúp từ chối reuse cùng key cho intent khác. **Không đưa nonce/timestamp/attempt request ID/key ID vào idempotency scope** theo hợp đồng này: retry và rotation phải giữ operation identity. Idempotency không thay HMAC, nonce hoặc business authorization.


## 7. Key rotation và thu hồi credential theo từng client

### 7.1. Đổi secret của A mà không buộc B dừng hoạt động

Ví dụ thời gian chuyển tiếp:

~~~mermaid
sequenceDiagram
    participant O as Credential Manager
    participant A as Client A
    participant B as Client B
    participant K as Trusted Key Store
    participant V as Verifier
    O->>K: Create A-new (ACTIVE) with independent secret
    O->>K: A-old -> VERIFY_ONLY until deadline D
    O->>A: Secure delivery of A-new
    A->>V: Request signed by A-old before D
    V->>K: Lookup (audience,A,A-old)
    K-->>V: VERIFY_ONLY; verify permitted
    V-->>A: Authenticated if MAC/freshness/nonce pass
    A->>V: New request with A-new
    V->>K: Lookup (audience,A,A-new)
    K-->>V: ACTIVE
    V-->>A: Authenticated if all checks pass
    B->>V: Request with B-secret (unchanged)
    V-->>B: Independent client B continues
    O->>K: A-old -> REVOKED at/after D
~~~

Khi rotate một client, phải đảm bảo:
- Key mới có **secret material độc lập**, key ID/immutable version khác.
- Chỉ server quản lý thời điểm `ACTIVE`/`VERIFY_ONLY`/`REVOKED`.
- Receiver verify old key trong overlap **có hạn**; client nên ngừng ký bằng old key theo kế hoạch.
- Nonce store không reset chỉ vì đổi key ID.
- Logs ghi verified client/key ID và key state, giúp biết client nào chưa migrate.
- Client B hoặc C không cần thay secret chỉ vì A rotate (nếu không có sự cố hệ thống chung).
- Nếu secret A bị lộ, cần revoke A ngay theo incident policy, **không** giữ overlap dài chỉ để thuận tiện.

### 7.2. Key states và policy

| State | Ý nghĩa | Receiver |
|---|---|---|
| `ACTIVE` | Key hiện được phép dùng | HMAC verify cho request phù hợp |
| `VERIFY_ONLY` | Key cũ dùng trong overlap | Verify **chỉ tới deadline**; không tiếp tục phát mới nếu client tuân policy |
| `REVOKED` | Credential bị hủy quyền | Từ chối dù tag HMAC toán học đúng |
| `EXPIRED` | Deadline đã qua | Từ chối theo effective state |
| `NOT_FOUND` | Không có key theo tuple | Từ chối, không fallback secret |

Request timestamp do client ký **không thể** hồi sinh một key đã revoke: chính sách dùng **server time và trusted key record state**. Nếu một replica dùng metadata cache stale, cần bounded propagation, invalidation và fail-safe policy. Secret cache và key-state cache **không nhất thiết có cùng TTL**.

### 7.3. Secret leak và phạm vi ảnh hưởng

Giả sử chỉ KA bị lộ:

1. Xác định những `keyId`/version của A bị ảnh hưởng.
2. Revoke key lộ; từ chối MAC ký mới bằng key đó.
3. Cấp secret mới cho A qua kênh an toàn.
4. Kiểm tra authenticated events, nonce replay, unusual authorization và business ledger của A.
5. Không kết luận B bị compromise chỉ vì A bị compromise; tiếp tục giám sát ảnh hưởng tới server/KMS.
6. Nếu **root store, verifier IAM hoặc provisioning system** cũng bị lộ, đánh giá lại toàn bộ clients vì phạm vi có thể lớn hơn A.

Audit **material read** bởi verifier workload khác audit **HMAC authentication** của A: attacker có thể gửi MAC giả và khiến verifier đọc candidate secret; điều đó không chứng minh A gửi request hợp lệ.

## 8. Authentication và authorization trong hệ thống nhiều khách hàng

### 8.1. HMAC chứng minh việc sở hữu secret, không chứng minh quyền đọc dữ liệu

Giả sử client A gửi request có MAC đúng:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Authorization: HMAC-SHA256 client_id="merchant-a", key_id="a-v1", signature="<valid-A-tag>"
X-Nonce: <fresh-nonce>
X-Timestamp: <valid-time>
Content-Type: application/json

{"orderId":"belongs-to-merchant-b","amount":150000}
~~~

Một HMAC signature hợp lệ cho A **chỉ chứng minh request tương ứng credential A**, không cho phép A sửa order của B. Business authorization cần lấy **owner của order từ trusted database**, so với principal/tenant mappings, và kiểm action `orders:commit`.

~~~text
HTTP authn:
  request MAC matched for authenticatedClientId = merchant-a
  timestamp fresh, nonce unused
  -> Authentication PASS

Resource authorization:
  order.ownerClient = merchant-b
  actor = merchant-a
  action = orders:commit
  -> Authorization DENY
~~~

Nếu body có `tenantId=merchant-b` do client tự gửi, server không được tin field đó như bằng chứng A thuộc tenant B. Rủi ro này là **BOLA/IDOR** (broken object-level authorization), không được sửa bằng cách “ký body là đủ”. A biết secret A nên có thể ký mọi body mình tự chọn.

### 8.2. Tenant mapping khi một tenant có nhiều applications

Một tenant có thể sở hữu clients `tenant-A-web` và `tenant-A-batch`. Authorization nên dựa trên **trusted mapping** `(authenticatedClientId → tenant/principal permissions)` cùng resource ownership và action policy. Có thể hai clients chung tenant nhưng quyền khác:

| Principal đã xác thực | Tenant | Scope | Hành động |
|---|---|---|---|
| A-web | A | `orders:read` | Chỉ đọc đơn thuộc A |
| A-batch | A | `orders:commit` | Được commit đơn thuộc A |
| B-web | B | `orders:read` | Không đọc đơn của A |

**Per-client HMAC secret** giải quyết việc xác nhận danh tính ứng dụng; **authorization policy** mới giải quyết phân quyền trong tenant.

### 8.3. Mã phản hồi và không làm lộ tồn tại của client

| Trường hợp | Public API response minh họa | Internal audit |
|---|---|---|
| Authorization header thiếu/nhập nhằng | 400 hoặc 401 theo contract | Header format failure |
| Unknown client/key ID | 401 chung | `KEY_NOT_FOUND` / claimed selectors unverified |
| HMAC tag sai | 401 chung | `MAC_MISMATCH` |
| Timestamp ngoài cửa sổ | 401 chung | `TIMESTAMP_OUT_OF_WINDOW` |
| Nonce replay | 401 chung | `REPLAY_NONCE` |
| Key revoked | 401 chung | `KEY_REVOKED` |
| Authenticated A đọc resource B | 403 | `AUTHORIZATION_DENIED` |
| Shared nonce store không khả dụng | 503/fail closed theo API | `NONCE_STORE_UNAVAILABLE` |

Không cần trả thông báo public “client B tồn tại nhưng secret của bạn sai”; khác biệt lỗi như vậy có thể trở thành **key/client enumeration oracle**. Audit nội bộ có thể phân loại chi tiết nhưng phải giới hạn quyền xem và chống log injection.


## 9. Java 17: signer/verifier multi-client với secret tách biệt

Ví dụ `MultiClientHmacDemo.java` dùng Java 17/JCA thuần, mô phỏng ba credentials:

- `merchant-a/shared`: secret A cũ, `VERIFY_ONLY` trong thời gian overlap.
- `merchant-a/a-new`: secret A mới, `ACTIVE`.
- `merchant-b/shared`: secret B riêng, `ACTIVE`.

Hai clients **cố ý có key ID text giống nhau `shared`** để chứng minh không được lookup chỉ bằng key ID. Các secret đều là **32 bytes CSPRNG độc lập**. Demo minh họa:

1. Strict parse custom `Authorization` có client/key selectors và HMAC tag Base64URL.
2. Lookup chính xác `KeyRef(audience, clientId, keyId)`; key record bảo vệ secret bằng defensive copy trong ví dụ.
3. Canonical request **11 dòng** có signed client ID, key ID, nonce, timestamp, request ID và raw-body digest.
4. Tính HMAC-SHA-256 đầy đủ, so raw 32-byte tag bằng `MessageDigest.isEqual`.
5. Kiểm key state và deadline bằng `Clock.fixed`; không bỏ qua `REVOKED`.
6. Nonce scope `(audience, authenticatedClientId, nonce)`, reserve nguyên tử **sau MAC đúng**.
7. Trả `Principal` từ **trusted key record**, không dùng raw claims trực tiếp.
8. Test cross-client impersonation, key selector tampering, same nonce across clients, cross-key replay, stale time, wrong body, revocation, authorization và 12-thread race.

**Giới hạn:** Đây là mô hình học tập trong **một JVM**. `ConcurrentHashMap` không thay Redis/database atomic store giữa nhiều nodes; `Map<KeyRef, KeyRecord>` không thay Secret Manager/KMS, không có durable audit, HTTP adapter thực hay end-to-end gateway tests. Chỉ STEP 6 hoặc test harness ngoài bài mới xác nhận code thực sự compile và hoạt động như mong đợi.

### 9.1. Mã nguồn `MultiClientHmacDemo.java`

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
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
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

public final class MultiClientHmacDemo {
    private static final String VERSION = "hmac-multiclient-v1";
    private static final String AUDIENCE = "orders-api-production";
    private static final String ALGORITHM = "HmacSHA256";
    private static final long WINDOW_SECONDS = 300L;
    private static final long NONCE_TTL_SECONDS = 660L;

    // Hợp đồng custom-v1: đúng một Authorization; ba params,
    // đúng thứ tự và quoted values, tag Base64URL no padding.
    private static final Pattern AUTH_PATTERN = Pattern.compile(
            "(?i:HMAC-SHA256) "
            + "(?i:client_id)=\"([A-Za-z0-9_-]{1,64})\", "
            + "(?i:key_id)=\"([A-Za-z0-9_-]{1,64})\", "
            + "(?i:signature)=\"([A-Za-z0-9_-]{43})\"");

    private MultiClientHmacDemo() {}

    public record KeyRef(
            String audience, String clientId, String keyId) {}

    public enum KeyState {
        ACTIVE, VERIFY_ONLY, REVOKED
    }

    // Một credential phải được bind với owner và audience.
    // Defensive copy chống caller sửa secret sau provisioning.
    public record KeyRecord(
            KeyRef ref,
            KeyState state,
            long verifyOnlyUntilEpochSeconds,
            byte[] secret) {
        public KeyRecord {
            if (ref == null || state == null || secret == null
                    || secret.length != 32) {
                throw new IllegalArgumentException(
                        "Demo needs valid 32-byte independent key");
            }
            secret = secret.clone();
        }

        @Override
        public byte[] secret() {
            return secret.clone();
        }
    }

    public record Request(
            String method,
            String rawTarget,
            String contentType,
            String timestamp,
            String nonce,
            String requestId,
            byte[] rawBody) {
        public Request {
            if (rawBody == null) {
                throw new IllegalArgumentException("Missing body bytes");
            }
            rawBody = rawBody.clone();
        }

        @Override
        public byte[] rawBody() {
            return rawBody.clone();
        }
    }

    public record Credential(
            String claimedClientId,
            String claimedKeyId,
            String signature) {}

    public record Principal(
            String clientId,
            String audience,
            String verifiedKeyId) {}

    public record NonceScope(
            String audience,
            String authenticatedClientId,
            String nonce) {}

    public enum Decision {
        AUTHENTICATED,
        AUTHN_REJECTED,
        KEY_REVOKED,
        KEY_EXPIRED,
        TIMESTAMP_REJECTED,
        REPLAY_REJECTED,
        NONCE_STORE_ERROR
    }

    public record AuthResult(
            Decision decision,
            Principal principal) {}

    // DEMO ONLY: atomic trong cùng JVM, không shared across replicas.
    public static final class NonceStore {
        private final ConcurrentHashMap<NonceScope, Long> used =
                new ConcurrentHashMap<>();

        public boolean reserve(
                NonceScope scope,
                long nowSeconds,
                long ttlSeconds) {
            AtomicBoolean first = new AtomicBoolean(false);
            used.compute(scope, (key, priorExpiry) -> {
                if (priorExpiry != null && priorExpiry > nowSeconds) {
                    return priorExpiry;
                }
                first.set(true);
                return Math.addExact(nowSeconds, ttlSeconds);
            });
            return first.get();
        }
    }

    public static String freshRandomId(SecureRandom random) {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    // Nonce và requestId dùng cùng encoding nhưng KHÁC vai trò.
    private static String strictRandomId(String value) {
        if (value == null
                || !value.matches("[A-Za-z0-9_-]{22}")) {
            throw new IllegalArgumentException(
                    "Expected 16-byte Base64URL no-pad ID");
        }
        final byte[] decoded;
        try {
            decoded = Base64.getUrlDecoder().decode(value);
        } catch (IllegalArgumentException failure) {
            throw new IllegalArgumentException(
                    "Invalid Base64URL", failure);
        }
        if (decoded.length != 16
                || !Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(decoded).equals(value)) {
            throw new IllegalArgumentException(
                    "Non-canonical signed identifier");
        }
        return value;
    }

    private static String strictSelector(String text) {
        if (text == null
                || !text.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                    "Invalid client/key selector");
        }
        return text;
    }

    private static String canonicalContentType(String input) {
        if (input == null || input.length() > 128
                || input.chars().anyMatch(
                    c -> (c < 0x20 && c != '\t') || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        String type = input.trim().toLowerCase(Locale.ROOT);
        if (!"application/json".equals(type)) {
            throw new IllegalArgumentException(
                    "Unsupported Content-Type");
        }
        return type;
    }

    private static long parseTimestamp(String text) {
        if (text == null
                || !text.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException(
                    "Unix timestamp must use seconds");
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException overflow) {
            throw new IllegalArgumentException("Timestamp overflow", overflow);
        }
    }

    private static boolean freshTimestamp(
            String timestamp, long nowSeconds) {
        try {
            long delta = Math.subtractExact(
                    parseTimestamp(timestamp), nowSeconds);
            return delta >= -WINDOW_SECONDS
                    && delta <= WINDOW_SECONDS;
        } catch (IllegalArgumentException | ArithmeticException ex) {
            return false;
        }
    }

    public static Credential parseAuthorization(
            List<String> authorizationValues) {
        if (authorizationValues == null
                || authorizationValues.size() != 1) {
            throw new IllegalArgumentException(
                    "Exactly one Authorization field required");
        }
        String fieldValue = authorizationValues.get(0);
        if (fieldValue == null || fieldValue.length() > 300) {
            throw new IllegalArgumentException(
                    "Authorization header too large");
        }
        Matcher match = AUTH_PATTERN.matcher(fieldValue);
        if (!match.matches()) {
            throw new IllegalArgumentException(
                    "Wrong Authorization HMAC-v1 grammar");
        }
        return new Credential(
                match.group(1), match.group(2), match.group(3));
    }

    private static byte[] decodeTagStrict(String signature) {
        if (signature == null
                || !signature.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException(
                    "Expected full 32-byte HMAC tag encoding");
        }
        final byte[] raw;
        try {
            raw = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException failure) {
            throw new IllegalArgumentException(
                    "Malformed signature Base64URL", failure);
        }
        if (raw.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(raw).equals(signature)) {
            throw new IllegalArgumentException(
                    "Invalid/non-canonical HMAC tag");
        }
        return raw;
    }

    public static byte[] canonicalBytes(
            Request request, String clientId, String keyId)
            throws GeneralSecurityException {
        if (request == null
                || !"POST".equals(request.method())) {
            throw new IllegalArgumentException("Only POST supported");
        }
        if (request.rawTarget() == null
                || !request.rawTarget().matches(
                    "/v1/orders\\?mode=(?:commit|preview)")) {
            throw new IllegalArgumentException("Unsupported raw URI");
        }

        String type = canonicalContentType(request.contentType());
        String client = strictSelector(clientId);
        String key = strictSelector(keyId);
        String timestamp = request.timestamp();
        parseTimestamp(timestamp);
        String nonce = strictRandomId(request.nonce());
        String requestId = strictRandomId(request.requestId());

        byte[] body = request.rawBody();
        if (body.length > 64 * 1024) {
            throw new IllegalArgumentException("Body too large");
        }
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));

        // Exactly 11 lines, UTF-8, LF separators, NO final LF.
        String canonical = String.join("\n",
                VERSION,
                AUDIENCE,
                request.method(),
                request.rawTarget(),
                type,
                client,
                key,
                timestamp,
                nonce,
                requestId,
                bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] computeHmac(
            byte[] secret, byte[] canonical)
            throws GeneralSecurityException {
        if (secret == null || secret.length == 0
                || canonical == null) {
            throw new IllegalArgumentException("Invalid HMAC input");
        }
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(secret, ALGORITHM));
        return mac.doFinal(canonical);
    }

    // Test helper đại diện CLIENT signer, không được dùng để
    // tự fallback hoặc thử mọi secret ở server verifier.
    public static String sign(Request request, KeyRecord clientCredential)
            throws GeneralSecurityException {
        KeyRef ref = clientCredential.ref();
        if (!AUDIENCE.equals(ref.audience())) {
            throw new IllegalArgumentException("Wrong signing audience");
        }
        byte[] tag = computeHmac(
                clientCredential.secret(),
                canonicalBytes(request, ref.clientId(), ref.keyId()));
        String encoded = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(tag);
        return "HMAC-SHA256 client_id=\""
                + ref.clientId() + "\", key_id=\""
                + ref.keyId() + "\", signature=\""
                + encoded + "\"";
    }

    private static boolean keyAllowsVerification(
            KeyRecord record, long nowSeconds) {
        if (record == null || record.ref() == null
                || !AUDIENCE.equals(record.ref().audience())) {
            return false;
        }
        return record.state() == KeyState.ACTIVE
                || (record.state() == KeyState.VERIFY_ONLY
                    && nowSeconds <=
                            record.verifyOnlyUntilEpochSeconds());
    }

    // Return authenticated principal ONLY after MAC + time + nonce.
    // HTTP adapter đã reject duplicate headers, wrong framing/content
    // coding và bảo toàn đúng raw target/body theo hợp đồng ký.
    public static AuthResult authenticate(
            Request request,
            List<String> authorizationValues,
            Map<KeyRef, KeyRecord> trustedKeys,
            NonceStore nonceStore,
            Clock clock) {
        if (trustedKeys == null || nonceStore == null
                || clock == null) {
            throw new IllegalArgumentException(
                    "Missing server security dependencies");
        }
        if (request == null) {
            return new AuthResult(
                    Decision.AUTHN_REJECTED, null);
        }

        final Credential claim;
        try {
            claim = parseAuthorization(authorizationValues);
        } catch (IllegalArgumentException malformed) {
            return new AuthResult(
                    Decision.AUTHN_REJECTED, null);
        }

        // The claim is NOT the authenticated identity yet.
        KeyRef lookup = new KeyRef(
                AUDIENCE, claim.claimedClientId(),
                claim.claimedKeyId());
        KeyRecord record = trustedKeys.get(lookup);
        if (record == null || !lookup.equals(record.ref())) {
            return new AuthResult(
                    Decision.AUTHN_REJECTED, null);
        }

        long now = clock.instant().getEpochSecond();
        if (record.state() == KeyState.REVOKED) {
            return new AuthResult(
                    Decision.KEY_REVOKED, null);
        }
        if (!keyAllowsVerification(record, now)) {
            return new AuthResult(
                    Decision.KEY_EXPIRED, null);
        }

        try {
            byte[] suppliedTag = decodeTagStrict(claim.signature());
            byte[] expectedTag = computeHmac(
                    record.secret(),
                    canonicalBytes(request,
                            claim.claimedClientId(),
                            claim.claimedKeyId()));
            if (!MessageDigest.isEqual(
                    expectedTag, suppliedTag)) {
                return new AuthResult(
                        Decision.AUTHN_REJECTED, null);
            }
        } catch (IllegalArgumentException
                 | GeneralSecurityException invalid) {
            return new AuthResult(
                    Decision.AUTHN_REJECTED, null);
        }

        // Không dùng client claim nếu chưa MAC đúng.
        if (!freshTimestamp(request.timestamp(), now)) {
            return new AuthResult(
                    Decision.TIMESTAMP_REJECTED, null);
        }

        NonceScope scope = new NonceScope(
                record.ref().audience(),
                record.ref().clientId(),
                request.nonce());
        final boolean reserved;
        try {
            reserved = nonceStore.reserve(
                    scope, now, NONCE_TTL_SECONDS);
        } catch (RuntimeException unavailable) {
            return new AuthResult(
                    Decision.NONCE_STORE_ERROR, null);
        }
        if (!reserved) {
            return new AuthResult(
                    Decision.REPLAY_REJECTED, null);
        }

        return new AuthResult(
                Decision.AUTHENTICATED,
                new Principal(
                        record.ref().clientId(),
                        record.ref().audience(),
                        record.ref().keyId()));
    }

    // Demo business authorization. owner đến từ DB/server,
    // không lấy từ untrusted JSON tenant field.
    public static boolean mayCommitOrder(
            Principal principal,
            String orderOwnerFromTrustedDb) {
        return principal != null
                && principal.clientId().equals(
                        orderOwnerFromTrustedDb);
    }

    private static Request request(
            long now, String nonce, String requestId, byte[] body) {
        return new Request(
                "POST", "/v1/orders?mode=commit",
                "application/json", Long.toString(now),
                nonce, requestId, body);
    }

    private static void require(boolean value, String label) {
        if (!value) throw new AssertionError(label);
    }

    private static void testKnownAnswer() throws Exception {
        // RFC 4231 HMAC-SHA-256 Test Case 1.
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0B);
        byte[] msg = "Hi There"
                .getBytes(StandardCharsets.US_ASCII);
        String expected =
                "b0344c61d8db38535ca8afceaf0bf12b"
              + "881dc200c9833da726e9376c2e32cff7";
        require(
                HexFormat.of().formatHex(
                    computeHmac(key, msg)).equals(expected),
                "RFC 4231 known-answer HMAC");
    }

    // Từ cùng secret B, giả một key record A trong TEST,
    // nhưng server sẽ lookup secret A thật => MAC mismatch.
    private static KeyRecord fakeSigner(
            KeyRef claimedA, byte[] secretOfB) {
        return new KeyRecord(
                claimedA, KeyState.ACTIVE, 0L, secretOfB);
    }

    private static void concurrencyTest(
            KeyRecord key, Map<KeyRef, KeyRecord> keys,
            Clock clock, SecureRandom random) throws Exception {
        final int attempts = 12;
        long now = clock.instant().getEpochSecond();
        byte[] body = "{\"orderId\":\"same-op\",\"amount\":150000}"
                .getBytes(StandardCharsets.UTF_8);
        Request r = request(
                now, freshRandomId(random),
                freshRandomId(random), body);
        String signature = sign(r, key);
        NonceStore sharedNonceStore = new NonceStore();

        ExecutorService pool =
                Executors.newFixedThreadPool(attempts);
        CountDownLatch ready = new CountDownLatch(attempts);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<AuthResult>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < attempts; i++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    start.await();
                    return authenticate(
                            r, List.of(signature),
                            keys, sharedNonceStore, clock);
                }));
            }
            require(ready.await(10, TimeUnit.SECONDS),
                    "Workers must become ready");
            start.countDown();

            int accepted = 0, replays = 0;
            for (Future<AuthResult> future : futures) {
                Decision decision = future.get().decision();
                if (decision == Decision.AUTHENTICATED) accepted++;
                if (decision == Decision.REPLAY_REJECTED) replays++;
            }
            require(accepted == 1,
                    "Only one identical nonce may be reserved");
            require(replays == attempts - 1,
                    "Every other identical request rejected");
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        testKnownAnswer();

        SecureRandom rng = new SecureRandom();
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"),
                ZoneOffset.UTC);
        long now = clock.instant().getEpochSecond();

        byte[] secretAOld = new byte[32];
        byte[] secretANew = new byte[32];
        byte[] secretB = new byte[32];
        rng.nextBytes(secretAOld);
        rng.nextBytes(secretANew);
        rng.nextBytes(secretB);

        // Same keyId text "shared" across TWO clients.
        KeyRef aOldRef = new KeyRef(
                AUDIENCE, "merchant-a", "shared");
        KeyRef aNewRef = new KeyRef(
                AUDIENCE, "merchant-a", "a-new");
        KeyRef bRef = new KeyRef(
                AUDIENCE, "merchant-b", "shared");

        KeyRecord aOld = new KeyRecord(
                aOldRef, KeyState.VERIFY_ONLY,
                now + 120L, secretAOld);
        KeyRecord aNew = new KeyRecord(
                aNewRef, KeyState.ACTIVE,
                0L, secretANew);
        KeyRecord b = new KeyRecord(
                bRef, KeyState.ACTIVE,
                0L, secretB);
        Map<KeyRef, KeyRecord> keys = new HashMap<>();
        keys.put(aOldRef, aOld);
        keys.put(aNewRef, aNew);
        keys.put(bRef, b);

        // Different per-client secrets even with the same keyId text.
        require(!Arrays.equals(
                aOld.secret(), b.secret()),
                "Clients must not share key material");

        NonceStore nonces = new NonceStore();
        byte[] bodyA = "{\"orderId\":\"A-123\",\"amount\":150000}"
                .getBytes(StandardCharsets.UTF_8);

        // First authenticated request from A, old key still VERIFY_ONLY.
        String sameNonce = freshRandomId(rng);
        Request firstA = request(
                now, sameNonce, freshRandomId(rng), bodyA);
        String headerA = sign(firstA, aOld);
        AuthResult acceptedA = authenticate(
                firstA, List.of(headerA), keys, nonces, clock);
        require(acceptedA.decision() == Decision.AUTHENTICATED,
                "Client A old key must verify inside overlap");
        require("merchant-a".equals(
                acceptedA.principal().clientId()),
                "Principal comes from trusted A key record");

        // Replay original HTTP request is denied.
        require(authenticate(
                firstA, List.of(headerA), keys, nonces, clock)
                .decision() == Decision.REPLAY_REJECTED,
                "Exact replay must fail");

        // Rotation: new A key, same nonce -> STILL replay.
        String rotatedHeader = sign(firstA, aNew);
        require(authenticate(
                firstA, List.of(rotatedHeader),
                keys, nonces, clock).decision()
                == Decision.REPLAY_REJECTED,
                "Key rotation must not reset nonce namespace");

        // B can independently use the SAME nonce under B secret.
        String headerB = sign(firstA, b);
        AuthResult acceptedB = authenticate(
                firstA, List.of(headerB), keys, nonces, clock);
        require(acceptedB.decision() == Decision.AUTHENTICATED,
                "Different client namespace permits same nonce");
        require("merchant-b".equals(
                acceptedB.principal().clientId()),
                "Verified B principal");
        require(!mayCommitOrder(
                acceptedB.principal(), "merchant-a"),
                "Authenticated B cannot commit order owned by A");

        // Change clientId in A Authorization to B while keeping A tag:
        // Both records use keyId "shared" but secrets differ.
        String identityTampered = headerA.replace(
                "client_id=\"merchant-a\"",
                "client_id=\"merchant-b\"");
        Request freshForForgery = request(
                now, freshRandomId(rng),
                freshRandomId(rng), bodyA);
        String validForFreshA = sign(freshForForgery, aOld);
        String tamperedFreshIdentity = validForFreshA.replace(
                "client_id=\"merchant-a\"",
                "client_id=\"merchant-b\"");
        require(authenticate(
                freshForForgery, List.of(tamperedFreshIdentity),
                keys, nonces, clock).decision()
                == Decision.AUTHN_REJECTED,
                "A MAC cannot authenticate B");
        require(identityTampered.contains(
                "client_id=\"merchant-b\""),
                "Identity tampering setup");

        // B knows only secret B and CANNOT sign as A.
        KeyRecord fakeAWithBSecret =
                fakeSigner(aOldRef, secretB);
        Request fakeRequest = request(
                now, freshRandomId(rng),
                freshRandomId(rng), bodyA);
        String forgedAsA = sign(
                fakeRequest, fakeAWithBSecret);
        require(authenticate(
                fakeRequest, List.of(forgedAsA),
                keys, nonces, clock).decision()
                == Decision.AUTHN_REJECTED,
                "B secret cannot impersonate A");

        // A authentic request with the same nonce as forgery is
        // still allowed: failed MAC must not poison the nonce.
        require(authenticate(
                fakeRequest, List.of(sign(fakeRequest, aOld)),
                keys, nonces, clock).decision()
                == Decision.AUTHENTICATED,
                "Forged request does not reserve A nonce");

        // Tamper key selector from A-old to A-new without re-signing.
        Request keyTamperRequest = request(
                now, freshRandomId(rng),
                freshRandomId(rng), bodyA);
        String oldSigned = sign(keyTamperRequest, aOld);
        String swappedKey = oldSigned.replace(
                "key_id=\"shared\"",
                "key_id=\"a-new\"");
        require(authenticate(
                keyTamperRequest, List.of(swappedKey),
                keys, nonces, clock).decision()
                == Decision.AUTHN_REJECTED,
                "Key selector must be signed");

        // Change raw body after signature creation -> MAC mismatch.
        Request correct = request(
                now, freshRandomId(rng),
                freshRandomId(rng), bodyA);
        String valid = sign(correct, aNew);
        Request modifiedBody = new Request(
                correct.method(), correct.rawTarget(),
                correct.contentType(), correct.timestamp(),
                correct.nonce(), correct.requestId(),
                "{\"orderId\":\"A-123\",\"amount\":900000}"
                    .getBytes(StandardCharsets.UTF_8));
        require(authenticate(
                modifiedBody, List.of(valid),
                keys, nonces, clock).decision()
                == Decision.AUTHN_REJECTED,
                "Body tampering must invalidate MAC");
        require(authenticate(
                correct, List.of(valid),
                keys, nonces, clock).decision()
                == Decision.AUTHENTICATED,
                "Failed MAC must not reserve nonce");

        // Client A tries to use B credential selector but A secret.
        Request wrongOwner = request(
                now, freshRandomId(rng),
                freshRandomId(rng), bodyA);
        KeyRecord claimBWithASecret = fakeSigner(
                bRef, secretAOld);
        require(authenticate(
                wrongOwner, List.of(sign(wrongOwner,
                        claimBWithASecret)),
                keys, nonces, clock).decision()
                == Decision.AUTHN_REJECTED,
                "A secret cannot authenticate B even with same keyId");

        // Key explicitly revoked, despite signer knowing old bytes.
        KeyRef revokedRef = new KeyRef(
                AUDIENCE, "merchant-b", "b-revoked");
        KeyRecord revoked = new KeyRecord(
                revokedRef, KeyState.REVOKED,
                0L, secretB);
        keys.put(revokedRef, revoked);
        Request revokedRequest = request(
                now, freshRandomId(rng),
                freshRandomId(rng), bodyA);
        require(authenticate(
                revokedRequest, List.of(sign(revokedRequest, revoked)),
                keys, nonces, clock).decision()
                == Decision.KEY_REVOKED,
                "Revoked key may not verify");

        // Expired VERIFY_ONLY A old key.
        keys.put(aOldRef, new KeyRecord(
                aOldRef, KeyState.VERIFY_ONLY,
                now - 1L, secretAOld));
        Request expired = request(
                now, freshRandomId(rng),
                freshRandomId(rng), bodyA);
        require(authenticate(
                expired, List.of(sign(expired, aOld)),
                keys, nonces, clock).decision()
                == Decision.KEY_EXPIRED,
                "Verify-only deadline enforced");

        // Stale timestamp is rejected even with a correct MAC.
        Request stale = request(
                now - 301L, freshRandomId(rng),
                freshRandomId(rng), bodyA);
        require(authenticate(
                stale, List.of(sign(stale, aNew)),
                keys, nonces, clock).decision()
                == Decision.TIMESTAMP_REJECTED,
                "Timestamp freshness enforced");

        // Reject duplicate Authorization fields; do not pick first.
        Request duplicateRequest = request(
                now, freshRandomId(rng),
                freshRandomId(rng), bodyA);
        String oneHeader = sign(duplicateRequest, aNew);
        require(authenticate(
                duplicateRequest, List.of(oneHeader, oneHeader),
                keys, nonces, clock).decision()
                == Decision.AUTHN_REJECTED,
                "Duplicate Authorization rejected");

        // Concurrency: 12 identical signed requests, same client/nonce.
        concurrencyTest(aNew, keys, clock, rng);

        // Best-effort cleanup for demo's original byte[] copies.
        Arrays.fill(secretAOld, (byte) 0);
        Arrays.fill(secretANew, (byte) 0);
        Arrays.fill(secretB, (byte) 0);
        System.out.println("PASS multi-client independent-secret HMAC tests");
    }
}
~~~

### 9.2. Cách chạy

Lưu đoạn mã vào `MultiClientHmacDemo.java`, dùng JDK 17 hoặc mới hơn:

~~~bash
javac MultiClientHmacDemo.java
java MultiClientHmacDemo
~~~

Kết quả **dự kiến**:

~~~text
PASS multi-client independent-secret HMAC tests
~~~

Đây là **ví dụ học thuật**: trong STEP 4 không thực hiện chạy `javac`/`java` hay kiểm thử runtime. Những tuyên bố PASS trong ví dụ là **assertions dự kiến khi chạy**, không phải báo cáo đã thực thi.

### 9.3. Mục đích từng test

| Test | Điều chứng minh |
|---|---|
| HMAC RFC 4231 known-answer | JCA primitive có output đúng vector độc lập |
| A và B cùng text `keyId=shared` | Lookup phải gắn `(audience, clientId, keyId)` |
| A dùng old key VERIFY_ONLY còn hạn | Rotation overlap chỉ áp cho A |
| A request được gửi lại y nguyên | Nonce replay bị từ chối |
| A đổi sang new key nhưng giữ nonce | Không bypass replay do rotation |
| B dùng nonce text giống A, ký bằng B secret | Per-client nonce scope tách biệt |
| Đổi `client_id=A` thành B nhưng giữ tag A | Không giả danh được B |
| B dùng secret B để tạo credential khai A | MAC không khớp trusted secret A |
| Forged MAC đến trước A request thật | Không nonce poisoning |
| Đổi A key ID từ old sang new nhưng không ký lại | Selector bị bind vào MAC |
| Thay body amount sau khi ký | MAC fail; không reserve nonce |
| A dùng secret của mình để khai B credential | Server không accept |
| Key B bị `REVOKED` | Key policy từ chối dù biết bytes |
| Key A `VERIFY_ONLY` hết hạn | Không tiếp tục nhận request |
| Timestamp `now - 301` | Chặn request quá cũ |
| Hai `Authorization` fields | Reject, không first/last wins |
| 12 threads replay cùng nonce | Chỉ một `AUTHENTICATED` trong cùng JVM |

### 9.4. Những phần demo không thay thế production

- `HashMap` và `KeyRecord.secret()` chứa bytes trong RAM; production dùng Secret Manager/KMS/key handle, workload IAM, audit material access và lifecycle.
- `NonceStore` chỉ atomic một JVM và không có cleanup nền; multi-region cần shared store có consistency/TTL phù hợp.
- Demo không có Redis, transactional idempotency, persistent business ledger hay gateway HTTP implementation.
- HMAC integrity **không phải** TLS confidentiality; luôn bảo vệ kênh truyền và storage.
- `SecretKeySpec`/JCA provider có thể copy secret; `Arrays.fill` trên một `byte[]` **không bảo đảm** xóa mọi bản copy trong JVM.
- Parser nhận subset custom Authorization; adapter HTTP thật phải kiểm message framing, field multiplicity, signed headers, raw target và body coding.
- `MessageDigest.isEqual` là bước so HMAC tag; toàn bộ pipeline không tự trở thành constant-time.
- Key state từ `Map` có thể stale khi distribute; cần hệ thống revoke propagation và policy fail-safe.
- Tests cùng helper `sign` và `authenticate` có thể cùng mắc lỗi canonicalization. Cần test vectors `RFC 4231`, golden canonical fixtures cross-language và integration tests.


## 10. Ma trận kiểm thử bắt buộc cho mô hình secret riêng từng client

Đối với một endpoint đa client, kiểm tra “MAC đúng thì trả 200” là chưa đủ. Bộ test phải chứng minh **tenant isolation**, **correct key lookup**, **replay namespace** và **authorization** không bị sai khi một client cố ý thao tác với identifiers của client khác.

### 10.1. Test identity, key selection và secret independence

| Case | Key record có sẵn | Request/attacker | Expected |
|---|---|---|---|
| A1 | A/keyA/KA | A khai A/keyA và ký KA | Authentication pass nếu fresh |
| A2 | B/keyB/KB | B khai B/keyB và ký KB | Authentication pass nếu fresh |
| A3 | A/keyA/KA, B/keyB/KB | A khai B/keyB nhưng ký KA | **MAC fail** |
| A4 | A/keyA/KA, B/keyB/KB | B khai A/keyA nhưng ký KB | **MAC fail** |
| A5 | A/`shared`/KA, B/`shared`/KB | A khai B/`shared`, giữ tag A | **MAC fail**, dù key ID text giống |
| A6 | A/`shared`/KA, B/`shared`/KB | B gửi đúng B/`shared`/KB | Pass trong namespace B |
| A7 | A/keyA/KA | A khai A/unknown, tag KA | **Lookup reject**, không fallback |
| A8 | A/keyA/KA | A sửa keyA → keyA2 sau ký | **MAC fail** hoặc lookup reject |
| A9 | A/keyA/KA | A sửa client A → client B sau ký | **MAC fail** hoặc lookup reject |
| A10 | A/keyA/KA | Đổi audience production → staging | Staging không dùng production secret |
| A11 | A-old/KAold VERIFY_ONLY | A ký KAold trước deadline | Có thể verify nếu MAC/nonce/time pass |
| A12 | A-old/KAold VERIFY_ONLY | A ký KAold sau deadline | **KEY_EXPIRED** |
| A13 | A-old/KAold REVOKED | A ký KAold khi key revoked | **KEY_REVOKED**, dù MAC đúng |
| A14 | B/keyB/KB | A gửi secret A qua Authorization để “chọn” secret | Reject: never accept plaintext secret in request |
| A15 | A/keyA/KA | A gửi `alg=none` hoặc HMAC-SHA1 | Reject unsupported scheme/algorithm |
| A16 | A/keyA/KA | Tag truncated/padded/hex | Reject strict signature encoding |

Giá trị KA/KB trong tests là **key material chỉ dành cho fixtures**, không đưa raw bytes vào log production. Tình huống A3 và A4 đặc biệt quan trọng: **kể cả attacker có secret của client khác**, receiver vẫn phải dùng secret của **claimed target client** để verify.

### 10.2. Test nonce và retry trong multi-client

| Client | Key | Nonce | HTTP attempt | Kỳ vọng |
|---|---|---|---|---|
| A | a-old | N1 | Đầu tiên, MAC đúng | Pass, reserve `(audience,A,N1)` |
| A | a-old | N1 | Replay y nguyên | **REPLAY** |
| A | a-new | N1 | Ký lại bằng key mới nhưng reuse nonce | **REPLAY** |
| A | a-new | N2 | Attempt mới, timestamp/signature mới | Pass nếu policy cho phép |
| B | b-key | N1 | Đầu tiên của B, MAC riêng đúng | Pass vì namespace B độc lập |
| B | b-key | N1 | Replay của B | **REPLAY** |
| A | a-new | N3 | MAC giả đến trước MAC thật | MAC giả **không** reserve nonce |
| A | a-new | N3 | Request thật đến sau MAC giả | Pass nếu còn fresh |
| A | a-new | N4 | Hai replicas cùng nhận | **Một** reserve thành công trên distributed store |
| A | a-new | N5 | Nonce store down | Fail closed nếu anti-replay bắt buộc |

**Phân biệt:** Nonce text trùng giữa A và B không đủ để suy hai requests giống nhau. Cùng lúc, **một nonce N1** của A không được tái sử dụng dưới key ID mới của **vẫn A** nếu policy uniqueness theo client.

### 10.3. Test authorization với tenant mapping phức tạp

Cần ít nhất các trường hợp:

1. A-web và A-batch là hai client applications của cùng tenant A; cả hai ký secret **riêng**, nhưng có **permissions khác nhau**.
2. A-web có scope read được xem order thuộc tenant A, **không được commit** nếu thiếu scope.
3. A-batch có scope commit đúng tài nguyên thuộc A.
4. B-web có HMAC hợp lệ nhưng không được xem/sửa order thuộc A.
5. A gửi request body khai `tenantId=B` nhưng DB xác nhận order owner B; **deny**.
6. Client ID không đủ để suy tenant nếu account–tenant relationship bị thu hồi hoặc chuyển; dùng trusted current mapping.
7. User delegation nếu có phải được thiết kế riêng: HMAC client credential không tự đại diện user cuối.
8. Authorization được kiểm **sau authentication** nhưng **trước business side effect**, kể cả khi idempotency key đã từng xuất hiện.

### 10.4. Negative tests cho format và canonicalization

| Input | Mong đợi |
|---|---|
| Thiếu Authorization | Reject |
| Hai Authorization fields (dù cùng value) | Reject tại HTTP adapter |
| Duplicate `client_id`/`key_id`/`signature` auth-params | Reject |
| Client ID chứa CR/LF, NUL, Unicode hoặc whitespace | Reject strict grammar |
| Key ID vượt 64 ký tự | Reject trước key lookup |
| Nonce 22 ký tự Base64URL sai pad bits | Reject canonical round-trip |
| Signature 43 ký tự nhưng decoded không phải 32-byte canonical tag | Reject |
| Signature cắt ngắn/hex/base64 thường | Reject |
| Timestamp milliseconds trong contract seconds | Reject freshness |
| Query thay thứ tự/percent encoding ngoài contract | Reject hoặc MAC mismatch theo raw-target signing |
| JSON body cùng semantics nhưng khác raw bytes | MAC tính trên bytes mới; tag cũ fail |
| Content-Type khác application/json | Reject |
| Proxy tự đổi method hoặc request target | MAC fail |
| HTTP/2 `:path` qua gateway khác HTTP/1.1 origin-form | Phải xác định trusted canonical boundary, cross-protocol integration tests |

### 10.5. Test durability, multi-region và fault injection

- Hai verifier nodes cùng xử lý exact replay: **shared nonce store** bảo đảm một winner, không mỗi node có một `ConcurrentHashMap` riêng.
- Verifier A đã biết key A revoked, verifier B còn cached metadata old ACTIVE: kiểm consistency/cutover SLA và policy khi store unavailable.
- Secret Manager fail trên key A: **không** dùng secret B hoặc default key làm fallback để “cứu request”.
- Audience production/staging có cùng client ID và key ID: records/secret versions phải **tách environment**, không có cross-environment signing.
- Một client gửi nhiều requests giả `clientId=other` nhằm tiêu tốn Secret Manager lookup: rate/resource budgets và audit không gây DoS dây chuyền.
- Retry payment qua key rotation: authentication của hai attempts có thể đều pass nhưng business idempotency chỉ tạo **một** side effect trong retention.
- Crash sau business commit nhưng trước idempotency result: database transaction/outbox/reconciliation tránh tạo duplicate; nonce độc lập không giải quyết vấn đề này.
- Gateway chuyển HTTP/2 ↔ HTTP/1.1 hoặc thêm WAF rules: signed target, signed fields và raw body vẫn được diễn giải nhất quán.
- Thử dùng TLS connection pool của A để gửi credential B: **không** suy client identity từ IP, connection ID hoặc `Host` nếu signing protocol yêu cầu HMAC principal.
- Key theft incident: revoke riêng A thành công; B vẫn hoạt động, không làm lộ key B trong audit/debug.
- KMS IAM policy thay đổi: verifier không có quyền đọc B nếu không được cấp; nếu service identity cần verify nhiều clients, phải có scope, audit và controls cho toàn bộ khả năng đọc đó.

## 11. Proxy/gateway: tính nhất quán per-client trên toàn tuyến

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant G as Gateway
    participant V as Verifier
    participant K as Trusted Key Store
    participant N as Shared Nonce Store
    participant X as Authorization / Business
    A->>G: HMAC(A secret, clientId=A, keyId=A-old)
    B->>G: HMAC(B secret, clientId=B, keyId=B-current)
    G->>G: Strip internal identity headers, validate multiplicity
    G->>V: Preserve signed raw method/target/headers/body
    V->>K: Lookup (audience,A,A-old)
    K-->>V: Secret A, state VERIFY_ONLY
    V->>V: Verify A full HMAC
    V->>N: Reserve nonce in scope A
    V->>X: Principal A if fresh
    V->>K: Lookup (audience,B,B-current)
    K-->>V: Secret B, state ACTIVE
    V->>V: Verify B full HMAC
    V->>N: Reserve nonce in scope B
    V->>X: Principal B if fresh
    X->>X: Authorize each action/resource separately
~~~

### 11.1. Tại sao không tin `X-Client-Id` ở edge?

Header `X-Client-Id` (hoặc `client_id` trong Authorization) là một **selector claim**, cần để lookup candidate key. Nhưng trước HMAC đúng nó chưa được xác thực. Gateway không được:

~~~text
principal = request.header("X-Client-Id")
proxy.setHeader("X-Verified-Client", principal)
backend.authorize(principal)
~~~

Nếu gateway là bên verify HMAC, nó chỉ nên xuất trusted principal metadata **sau verify**, xóa các internal headers client có thể gửi và chuyển kết quả qua kênh trusted (mTLS/service identity hoặc signed internal context theo thiết kế). Backend vẫn phải kiểm authorization.

### 11.2. Những rewrite thường phá HMAC

| Gateway behavior | Ảnh hưởng | Hướng xử lý |
|---|---|---|
| Rewrite `/api/v1/orders` → `/v1/orders` | Sender/verifier ký target khác | Chốt target ở trust boundary hoặc trusted original-target contract |
| Decode `%2F`, normalize `//`, xử lý dot segments | Route và canonical path có thể lệch | Reject ambiguous paths hoặc một canonical rule cố định |
| Reorder/drop duplicate query params | Bytes/semantics có thể khác | Canonical query contract + golden fixtures |
| Re-serialize JSON, decompress/recompress body | SHA-256 raw body khác | Verify trên raw bytes đã quy ước |
| Add/replace signed `X-Request-Id` | HMAC fail | Tạo separate server-side edgeRequestId |
| Remove `Authorization` | Không còn credential | Reject, cấu hình trusted header forwarding |
| Forward duplicate `Authorization` | Parser first/last khác nhau | Reject duplicate trước verify |
| Lowercase HTTP **field names** | HTTP field names case-insensitive | Map tên theo contract, không sửa signed values |
| Lowercase client/key **values** | Identity/key lookup thay đổi | Không normalize values |
| Cache 401/200 trước authentication | Client có thể nhận response của tenant khác | Không bypass HMAC/authz và cache policy |
| Inject `X-Verified-Client` từ Internet | Giả verified principal | Strip và trusted backend channel |

### 11.3. Audience và multi-service protection

Nếu cùng một client có access tới nhiều APIs, **không dùng secret A-production cho A-staging** hoặc không rõ service context. Audience cần được xác định bởi trusted gateway/service config. Trong bài, dòng thứ hai của canonical request là `orders-api-production`. Sender ký audience đó; key lookup cũng chỉ ở audience đó.

Việc đưa audience vào canonical text không đủ nếu receiver tùy ý lấy audience từ untrusted `Host` rồi cấp key theo giá trị ấy. Route-to-audience mapping phải thuộc server trust configuration.

## 12. Observability, audit và vận hành sự cố per-client

### 12.1. Nên ghi gì vào authentication audit?

Một event có thể chứa:

~~~json
{
  "eventType": "HMAC_AUTHENTICATION",
  "schemaVersion": "hmac-auth-audit-v1",
  "serviceAudience": "orders-api-production",
  "edgeRequestId": "server-generated-attempt-0007",
  "outcome": "AUTHENTICATED",
  "claimedClientId": "merchant-a",
  "claimedKeyId": "a-v1",
  "verifiedClientId": "merchant-a",
  "verifiedKeyId": "a-v1",
  "verifiedKeyState": "ACTIVE",
  "canonicalVersion": "hmac-multiclient-v1",
  "nonceOutcome": "RESERVED"
}
~~~

Trong event `MAC_MISMATCH`, **`verifiedClientId` và `verifiedKeyId` phải null** hoặc có trường `macVerifiedKeyId` riêng đúng semantics: không được gọi client B là “verified” chỉ vì attacker A đã khai B. Với replay, MAC có thể đúng nhưng attempt bị từ chối; không đếm `MAC_VERIFIED` thành `AUTHENTICATED`.

### 12.2. Log nào không được chứa secret?

~~~text
DO NOT LOG:
  sharedSecret / SecretKeySpec raw bytes
  full received or expected HMAC
  raw Authorization field
  private API credentials / service tokens
  raw request body carrying PII/payment data
  raw nonce by default
  secret manager plaintext
  stack traces embedding credential values
~~~

Key ID có thể không phải secret nhưng có thể tiết lộ inventory/timeline rotation. Hạn chế quyền xem, pseudonymize nếu cần và không dùng attacker-chosen raw clientId/keyId làm metric labels cardinality không giới hạn. Dùng structured log serializer có escape, reject CR/LF/NUL trước khi ghi.

### 12.3. Những metrics có ích

| Metric | Truy vấn/điều tra |
|---|---|
| `auth_success_count{audience}` | Lượng requests được xác thực |
| `auth_reject_count{reason}` | Replay, key revoked, MAC mismatch, malformed |
| `key_rotation_verify_only_usage` | Client nào còn dùng old key (dựa trên **verified events**) |
| `nonce_store_latency/errors` | Chống replay có đang fail closed? |
| `key_lookup_latency/errors` | IAM/Secret Manager/rate anomalies |
| `secret_cache_hit_rate` | Cache pressure nhưng không suy HMAC success từ cache |
| `authz_deny_count{resourceType}` | Broken access/permission misuse |
| `audit_delivery_lag` | Security logs có bị mất/chậm |
| `gateway_canonical_mismatch_count` | Routing/body transformations gây 401 |
| `credential_revoke_propagation_lag` | Key stale trong nhiều nodes |

Tránh metric labels theo **mọi claimed client ID/key ID** do Internet gửi. Nếu cần drill-down per customer, dùng privileged dashboard trên verified IDs hoặc bounded aggregation. Audit storage phải append-only/durable theo policy, không xem print logs là chứng cứ chắc chắn.

### 12.4. Khi secret của một client bị lộ

Playbook ngắn:

1. Kiểm dấu hiệu leak và các phiên bản credential của client A; bảo toàn audit/traces và resource scope.
2. Revoke A credential lộ; nếu cần cấp A secret mới qua kênh provisioning đáng tin.
3. Kiểm current key state/revocation propagation tới **mọi verifiers**, không để stale cache tiếp tục nhận.
4. Phân tích authenticated attempts của A, timestamp/nonce patterns, operations và authorization denials.
5. So business ledger/idempotency results để phát hiện double charges hoặc unauthorized actions.
6. Kiểm xem incident chỉ thuộc A client/tenant hay ảnh hưởng verifier/KMS master/workload identity — khi đó có thể phải rotate thêm clients.
7. Không đăng raw secret vào ticket hoặc public error; audit key record/version, reason và actions.
8. Test negative cases A-old revoked và positive cases A-new/B-unchanged, xác nhận B không bị downtime vô lý.

Nonce chống replay **không ngăn attacker biết secret A tạo một request A mới**: attacker có thể tạo timestamp/nonce mới, ký HMAC đúng. Phải revoke/rotate và kiểm authorization/rate limiting.


## 13. Các sai lầm phổ biến trong thiết kế multi-client HMAC

1. **Một `GLOBAL_HMAC_SECRET` cho mọi client:** một client bị lộ secret có thể ký request khai client khác.
2. **Dẫn xuất secret bằng `SHA256(clientId)`:** client ID dễ đoán, không có secret entropy.
3. **Lookup secret chỉ theo `keyId`:** có thể lấy nhầm key của tenant/audience khác.
4. **Sau lookup, tin `X-Client-Id` raw là principal:** key ID và claimed ID chỉ là selectors trước HMAC.
5. **Thử mọi secrets khi tag không khớp:** tạo cross-tenant confusion, timing oracle và DoS.
6. **Fallback default secret khi key không tồn tại/KMS fail:** mất isolation, vô hiệu hóa key revocation.
7. **Không đưa client/key ID vào canonical request:** selector dễ bị thay ngoài message đã ký.
8. **Không ký audience:** request bị nhầm service/environment khi routing không đúng.
9. **Dựa vào `Host` untrusted để chọn audience/secret:** attacker có thể thao túng routing context.
10. **Dùng key mới cùng bytes của key cũ:** rotation không thật sự thay vật liệu khóa.
11. **Một tenant nhiều apps nhưng dùng chung credential không cần thiết:** làm tăng blast radius và mất phân quyền riêng.
12. **Lưu secret vào git, logs hoặc URL:** tạo đường lộ dễ bị khai thác.
13. **Không phân biệt key ID với Secret Manager record/version:** audit/rotation không thể giải thích lịch sử.
14. **Coi Base64 là mã hóa secret:** encoding không bảo vệ vật liệu khóa.
15. **Không kiểm key state khi đã cache secret:** `REVOKED` vẫn được chấp nhận.
16. **Dùng request timestamp trước revoke làm căn cứ cho phép key đã revoke:** client kiểm soát timestamp.
17. **Nonce namespace chứa key ID không chủ ý:** rotation có thể cho phép reuse nonce cùng client.
18. **Nonce namespace dùng raw client ID trước MAC:** attacker có thể chiếm nonce của client thật.
19. **Dùng một nonce store local cho mỗi node:** replay được chấp nhận trên nhiều replicas.
20. **Đặt nonce TTL ngắn hơn full timestamp acceptance interval:** replay có thể lọt sau eviction.
21. **Dùng nonce thay business idempotency:** client phải đổi nonce khi retry, nên không ngăn double side effect.
22. **Idempotency scope chứa nonce/timestamp/key ID:** mỗi retry/rotation tạo business operation mới.
23. **Xem MAC đúng là quyền sửa mọi order:** bỏ resource/action authorization gây BOLA/IDOR.
24. **Tin `X-Verified-Client` từ Internet:** bỏ qua bước HMAC verifier đã xác thực.
25. **Proxy tự rewrite signed path/query/body:** HMAC mismatch hoặc router/verifier hiểu khác nhau.
26. **Cho duplicate Authorization hoặc signed headers:** WAF/backend có thể chọn credential khác.
27. **Cho client chọn thuật toán yếu/tag truncated:** algorithm confusion, MAC verification yếu.
28. **So HMAC tag bằng prefix hoặc `String.equals`:** timing/partial-match pitfalls.
29. **Đếm claimed clientId/keyId trong logs là authenticated usage:** attacker có thể làm sai rotation report.
30. **Quên secret storage isolation tại server:** compromised verifier có quyền lấy mọi secret dù clients có key riêng.
31. **Coi HMAC cung cấp confidentiality hoặc non-repudiation tuyệt đối:** HMAC không mã hóa nội dung, shared secret có ít nhất hai phía biết.
32. **Nhầm success HTTP authn với business commit:** side effect còn cần idempotency/transaction/ledger.

## 14. Bài tập thực hành

**Bài 1 — Global secret:** Hệ thống có 1.000 clients dùng chung `GLOBAL_HMAC_SECRET`. A bị lộ key. Hãy mô tả cách attacker giả mạo B và phương án chuyển tiếp sang per-client secrets mà không làm gián đoạn mọi B/C.

**Bài 2 — KeyRef:** A và B đều khai `keyId=primary`. Thiết kế primary key trong metadata store, key cache và audit để verifier không lấy nhầm KA/KB.

**Bài 3 — Client claim:** Attacker gửi `clientId=B` và tag được tính bằng KA. Tại sao server không được dựng principal B chỉ từ client header? Những bước nào chứng minh identity?

**Bài 4 — Key selector binding:** A ký `clientId=A,keyId=A1`, proxy đổi thành `keyId=A2`. Nếu key A2 có secret khác và key ID nằm trong canonical request, điều gì xảy ra?

**Bài 5 — Random secret:** Viết `SecureRandom` sinh 32 bytes cho A và 32 bytes cho B. Vì sao `SHA256("client-A")` không phù hợp làm shared secret?

**Bài 6 — KMS:** Workload verifier cần tra client secret qua Secret Manager. Policy nào phân biệt việc xem metadata, đọc plaintext, rotate, revoke và delete? Tại sao actor của Secret Manager audit không tự bằng authenticated HTTP client?

**Bài 7 — Rotation:** A có A-old VERIFY_ONLY tới D và A-new ACTIVE; B giữ nguyên B-key. Hãy lập kế hoạch key transition, audit verified usage và revoke A-old mà không gây downtime cho B.

**Bài 8 — Nonce:** A đã dùng nonce N. B tình cờ dùng N với KB riêng và MAC đúng. Nếu nonce policy scoped per authenticated client, B có được accept không? Nếu A ký lại bằng A-new với cùng N thì sao?

**Bài 9 — Forged nonce poisoning:** Attacker không biết KA, nhưng gửi claimed A + nonce N + MAC giả. Vì sao reserve nonce trước HMAC là lỗi? Dựng testcase chứng minh request A thật với N vẫn có thể pass.

**Bài 10 — Timestamp:** Sender dùng Unix milliseconds trong khi contract yêu cầu seconds. Tại sao tag có thể vẫn đúng toán học nhưng freshness reject? Làm sao xử lý clock skew?

**Bài 11 — HTTP/2 gateway:** Client ký `:path=/v1/orders?mode=commit`, gateway rewrite path trước verifier. Đề xuất trusted boundary và golden fixtures để SDK Java/Go/Node tạo canonical bytes nhất quán.

**Bài 12 — Cross-tenant BOLA:** A có HMAC hợp lệ và request body chứa order B. Viết hai quyết định riêng: authentication và authorization. Ai là resource owner nguồn tin cậy?

**Bài 13 — One tenant multiple apps:** Tenant A có web và batch. Nếu batch chỉ có quyền commit còn web chỉ có quyền read, nên dùng một secret hay hai? Những mapping nào cần có trong authorization?

**Bài 14 — Idempotency:** A retry payment với key mới, nonce mới, same idempotency key. HMAC authentication events có thể bao nhiêu, còn business commits đúng nên bao nhiêu?

**Bài 15 — Revocation:** Verifier A đã revoke key nhưng verifier B còn cached ACTIVE. Điều gì có thể sai? Cần metadata version, invalidation, max cache TTL và fail-safe policy gì?

**Bài 16 — Shared store concurrency:** Gửi 100 exact signed requests tới 10 replicas. Thiết kế distributed nonce reservation đảm bảo chỉ một request vượt qua; nêu giới hạn của `ConcurrentHashMap` demo.

**Bài 17 — Client B compromise:** Nếu KB bị lộ nhưng KA không lộ, per-client secrets bảo vệ A như thế nào? Trường hợp nào bắt buộc đánh giá lại tất cả clients (ví dụ provider workload/root store bị xâm nhập)?

**Bài 18 — Audit:** Một log `claimedKeyId=B-key` xuất hiện trong hàng triệu requests MAC sai. Có chứng minh B đang sử dụng key không? Cần đọc field nào để đếm legitimate verified usage?

**Bài 19 — Error messages:** Thiết kế public response 401 không cho attacker suy một client/key ID có tồn tại hay không nhưng vẫn có internal reason codes đủ phục vụ troubleshooting.

**Bài 20 — Canonical fixture:** Tạo fixture với audience, client/key IDs, method, exact raw target/body bytes, timestamp, nonce, request ID, test-only secret, canonical LF-delimited bytes và expected HMAC tag. Cross-check bằng hai implementations độc lập.

**Bài 21 — Operational isolation:** Client A có 10.000 HMAC requests/s và thường xuyên lookup key miss. Đề xuất quotas/rate limiting, key cache và log sampling policy bảo đảm không làm B bị DoS.

**Bài 22 — Threat modeling:** Nêu 5 trust boundaries trong tuyến client → gateway → verifier → Secret Manager → backend DB; với mỗi ranh giới, xác định điều gì được tin và điều gì phải xác thực lại.

## 15. Checklist production

| Nhóm | Kiểm tra |
|---|---|
| **Client inventory** | Một principal/client application rõ, mapping tới tenant/actions do server quản lý |
| **Per-client key material** | 32-byte independent CSPRNG secrets, không dùng global secret hoặc derivation yếu |
| **Credential key** | Lookup `(audience,clientId,keyId)` với owner/version/status |
| **Key store** | Secret Manager/KMS, IAM least privilege, production/staging separation |
| **Provisioning** | Secure delivery, controlled reveal, không log/gửi email/plaintext URL |
| **Versioning** | Immutable secret version ID, không reuse key record không kiểm soát |
| **Rotation** | ACTIVE/VERIFY_ONLY/REVOKED, bounded overlap, emergency revoke |
| **Key caching** | Scope có audience/client/key/version, policy invalidation và cache TTL an toàn |
| **Signing contract** | Versioned, signed method/raw URI/query, content type, client/key IDs, timestamp/nonce/requestId, raw body digest |
| **Signature** | HMAC-SHA-256 full 32-byte tag, Base64URL no-pad, strict round-trip decoding |
| **JCA verification** | `Mac.getInstance("HmacSHA256")` và `MessageDigest.isEqual` trên raw bytes |
| **HTTP grammar** | Reject duplicate Authorization/signed fields, control characters, huge headers |
| **Principal creation** | Chỉ lấy từ trusted key record sau MAC/freshness/nonce pass |
| **Replay** | Timestamp seconds, nonce 16 CSPRNG bytes, per authenticated client scope, atomic shared store, TTL đủ |
| **Idempotency** | Business key scoped per authenticated client/audience, giữ qua retries và key rotation |
| **Authorization** | Check action/resource owner/tenant sau authentication, không tin body tenant claim |
| **Gateway** | Không rewrite signed selectors, raw URI/body trước verify, trusted internal identity handoff |
| **Multi-region** | Key-state consistency/revoke propagation, shared nonce enforcement, time sync |
| **Error handling** | Uniform public 401, sanitize internal errors, no secret fallback/algorithm downgrade |
| **Audit** | Claimed vs verified IDs, verified key state, rotation usage, no secret/tag/body logging |
| **Observability** | Per-audience auth/replay/key errors, gateway mismatches, key-store latency |
| **Security QA** | Cross-client impersonation, cross-key rotation replay, concurrent duplicate, BOLA, gateway proxy |
| **Incident response** | Revoke/rotate compromised client, test others unaffected, check backend/KMS exposure |

## 16. Kết luận

**Secret riêng từng client** là nền tảng bảo vệ ranh giới danh tính trong một HTTP API HMAC đa khách hàng. Thay vì để mọi client ký với cùng một key, mỗi client có **secret material độc lập**, còn server dùng tuple **(trusted audience, claimed client ID, claimed key ID)** để chọn đúng record và kiểm owner/key state. Client ID/key ID chỉ là claims trước HMAC; authenticated principal được tạo từ trusted record **sau khi MAC, timestamp và nonce đều hợp lệ**.

Khi client A bị lộ secret, thiết kế đúng giúp hạn chế giả danh sang client B; khi A rotate, B không bị buộc thay key; khi hai clients tình cờ trùng nonce hoặc key ID text, hệ thống vẫn tách namespace rõ. Tuy nhiên, per-client secrets **không thay thế** TLS, Secret Manager/KMS, least privilege, anti-replay, durable key-state propagation, business idempotency hay authorization theo tài nguyên.

**Đích đến của triển khai:** cô lập material theo client, ràng buộc identity trong canonical request, xác minh bằng secret đúng owner/audience, từ chối replay và credential revoked, rồi kiểm quyền riêng cho từng action/resource. Các test cố tình dùng **cùng key ID text giữa A và B** và **đổi secret khi rotation** là những phép thử hiệu quả để phát hiện lỗi cross-client confusion trước khi đưa hệ thống vào production.

**Tài liệu tham khảo:**

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): nguyên lý HMAC với shared secret.
- [RFC 4231 — HMAC-SHA-256 Test Vectors](https://www.rfc-editor.org/rfc/rfc4231): test vectors kiểm HMAC độc lập.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP authentication, Authorization và method semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): framing, duplicate fields, intermediaries.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): `:method`, `:path`, HTTP/2↔HTTP/1.1 gateways.
- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): raw URI syntax và percent-encoding.
- [RFC 4648 — Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL và canonical pad bits.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): chuẩn tham khảo; `hmac-multiclient-v1` là **giao thức học tập riêng**.
- [RFC 5869 — HKDF](https://www.rfc-editor.org/rfc/rfc5869): nếu cần key derivation phải dùng KDF chuẩn có threat-model và domain separation, không tự băm client ID.
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): key lifecycle, states và key management.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lưu, cấp và rotate secrets.
- [OWASP API Security Top 10](https://owasp.org/API-Security/): broken object-level authorization và các lỗi API phổ biến.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ audit, log injection và sensitive data.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nguồn CSPRNG cho secret/nonce.
- [Java SE 17 — Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): `HmacSHA256` trong JCA.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): `isEqual` và SHA-256.
- [Java SE 17 — Base64](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): strict URL-safe encoding/decoding.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `compute` atomic trong cùng JVM, không thay distributed nonce store.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): test freshness/rotation với clock injection.
- [Redis — SET command](https://redis.io/docs/latest/commands/set/): `NX`, `EX` và `PX` trong atomic nonce reservation.









