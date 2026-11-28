# Secret access policy: kiểm soát quyền sử dụng shared secret trong HMAC request authentication

**Secret access policy** là tập quy tắc xác định **chủ thể nào được truy cập hoặc sử dụng một shared secret, cho hành động gì, thuộc môi trường, client, audience và phiên bản khóa nào**. Trong HTTP request authentication bằng HMAC, việc thuật toán HMAC-SHA256 mạnh không có ích nếu mọi service, developer, job CI hoặc gateway đều có thể lấy toàn bộ secret của tất cả client. Một secret bị lộ cho phép kẻ tấn công **tạo chữ ký HMAC hợp lệ**, không chỉ phát lại request cũ.

Bài thuộc chương **Secret management** của module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module thiết kế xác thực HTTP request bằng shared secret cùng canonical request chứa method, URI, signed headers/body theo hợp đồng; thực hành HMAC verification, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**. Trọng tâm riêng của bài là **quyền truy cập vật liệu khóa và quyền thực hiện thao tác mật mã**, không chỉ bảo vệ file cấu hình hay viết hàm so sánh signature.

> **Nguyên tắc cốt lõi:** Mặc định **deny**, cấp quyền **ít nhất cần thiết** theo workload identity, môi trường, client/audience, key version và thao tác (`SIGN`, `VERIFY`, `ROTATE`, `REVOKE`). Quyền quản lý metadata không mặc nhiên là quyền đọc secret; một HTTP header `X-Client-Id` hoặc `X-Key-Id` tự khai không được trở thành identity dùng để cấp quyền vào secret store.

## 1. Mục tiêu học tập

Hoàn thành bài, người học có thể:

1. Phân biệt **key ID**, **secret material**, **key metadata**, **sign/verify operation**, **secret export** và **quyền thao tác nghiệp vụ**.
2. Thiết kế access policy theo **chủ thể đã xác thực + resource scope + action + environment + điều kiện**, nguyên tắc deny by default và separation of duties.
3. Giải thích sự khác nhau giữa **client signer**, **API verifier**, **key provisioner**, **rotation controller**, **support engineer** và **CI/CD runner**.
4. Chọn secret delivery phù hợp: secret manager/KMS/HSM, workload identity, mTLS, short-lived credentials và encryption at rest/in transit.
5. Xây dựng cơ chế key lookup có scope đúng, tránh dùng secret của client/audience khác, không fallback về default key khi unknown key ID hoặc secret store lỗi.
6. Quản lý access khi provisioning, overlap rotation, revoke, incident response và cache/invalidation trên nhiều replica.
7. Viết Java 17 minh họa policy-enforced secret lease, HMAC-SHA256 signer/verifier, timestamp/nonce và các negative tests cho unauthorized access.
8. Kiểm thử secret leakage qua proxy/gateway, CI, log, exception, cache, credential reuse và authorization sau authentication.

## 2. Secret access policy bảo vệ tài sản nào?

Một HTTP HMAC system thường có dữ liệu và quyền sau:

| Tài sản/khả năng | Ý nghĩa | Mức bảo vệ |
| --- | --- | --- |
| `keyId` / `kid` | Định danh phiên bản khóa để lookup. | Metadata có thể xuất hiện trên wire; vẫn phải validate, chống enumeration và scope đúng. |
| **Shared secret bytes** | Bí mật mà signer và verifier/KMS dùng để tạo hoặc xác nhận MAC. | Bảo mật nghiêm ngặt; không đưa vào HTTP request, log, source control hoặc response. |
| Secret reference | Tên/ARN/path nội bộ đến key record. | Chỉ code tin cậy xây dựng; không lấy trực tiếp từ path do client gửi. |
| Key status / validity | `activeFrom`, `expiresAt`, `revoked`, allowed audience/operation. | Kiểm soát bởi trusted registry và quy trình quản trị. |
| `SIGN` capability | Khả năng tính tag HMAC cho message. | Nếu bị lạm dụng, tạo được request “chính chủ”; cần giới hạn signer. |
| `VERIFY` capability | Khả năng xác nhận MAC cho message/tag. | Với HMAC dùng local secret, cũng là quyền **nắm secret và có thể tự SIGN**. |
| `ROTATE` / `REVOKE` | Thay đổi phiên bản, trạng thái và quyền dùng key. | Tách trách nhiệm, có audit và phê duyệt phù hợp. |
| Nonce store | Dữ liệu chống replay theo client/audience. | Quyền claim atomic, retention đầy đủ, không cho arbitrary delete. |
| Business permissions | Quyền chuyển tiền/xem dữ liệu tenant. | **Authorization riêng**, không suy ra từ access vào shared secret. |

### 2.1. Ranh giới quan trọng của HMAC đối xứng

HMAC dùng **secret chung**. Nếu verifier tải **raw secret bytes** vào RAM, về mặt mật mã nó **có khả năng tạo HMAC như signer**, dù application access policy chỉ nói “VERIFY”. Phân tách `SIGN` và `VERIFY` trong IAM giúp giới hạn **API operation**, nhưng **không thể ngăn người nắm raw key ký message khác** bằng thuật toán HMAC.

Nếu cần tách khả năng mật mã mạnh hơn, cân nhắc **non-exportable HMAC key** trong KMS/HSM với API `GenerateMac`/`VerifyMac` hoặc tương đương nếu nhà cung cấp hỗ trợ. Khi ấy:

- Principal signer có thể được cấp **operation tạo MAC** nhưng không export raw key.
- Principal verifier chỉ có thể **gọi operation verify MAC** theo service-specific policy.
- KMS/HSM thực thi phân quyền hoạt động; service không nhận raw key.

**Nhưng:** client bên ngoài có thể không dùng chung KMS của server; HMAC vẫn đòi hai bên có khả năng tính tag. Nếu yêu cầu **server tuyệt đối không biết một secret mà client dùng để ký**, hoặc verifier không được có capability ký, hãy đánh giá **asymmetric digital signature** thay cho HMAC. Không gọi một symmetric HMAC shared secret là “public verification key”.

### 2.2. Threat model: lộ secret khác replay request

~~~mermaid
flowchart LR
    A["Client có secret được cấp"] --> B["Tạo canonical HTTP request"]
    B --> C["HMAC tag + timestamp + nonce"]
    C --> D["Gateway / verifier"]
    D --> E["Key manager / KMS"]
    E --> F["Verify đúng client,audience,kid"]
    G["Attacker ghi lại request"] --> H["Replay nguyên request"]
    H --> D
    I["Attacker lấy được shared secret"] --> J["Tự tạo request mới + tag hợp lệ"]
    J --> D
~~~

**Replay attacker** thường chỉ có request/tag đã ký; timestamp freshness và atomic nonce store có thể chặn replay. **Key compromise attacker** biết secret nên tự tạo `timestamp` mới, `nonce` mới và MAC mới. Replay guard **không giải quyết** được việc secret bị lộ; cần revoke, rotate, giới hạn phạm vi, audit và điều tra side effect.

## 3. Subject, resource, action và context của access policy

Một access decision có thể mô hình hóa:

~~~text
Decision = policy(
    authenticatedWorkloadPrincipal,
    action,
    KeyResource(environment, audience, clientId, keyId),
    trustedContext
)

ALLOW chỉ khi có quyền rõ ràng và mọi điều kiện đạt.
Mặc định: DENY.
~~~

**Subject** phải đến từ một trust boundary phù hợp:

- Workload identity được cấp qua **cloud IAM/OIDC**, mTLS client certificate, SPIFFE/SPIRE hoặc cơ chế tương đương có xác thực, không phải một header client tự gửi.
- CI/CD deploy principal hoặc controller dùng **short-lived identity**, không dùng một root token hard-code lâu dài.
- Operator/incident responder có SSO/MFA, role và audit; quyền emergency/break-glass phải được phê duyệt theo policy.
- Client bên ngoài có **credential provisioning và identity** riêng; không được lấy `X-Client-Id` trong HTTP request làm `workloadPrincipal` trực tiếp.

**Resource** cần nhận dạng chính xác key instance:

~~~text
keyResource = (
    environment,        // prod/staging/dev
    audience,           // payments-api
    clientId,           // partner-42
    keyId               // key-2026-11
)
~~~

**Action** cần phân tách:

| Action | Ví dụ chủ thể phù hợp | Cảnh báo |
| --- | --- | --- |
| `PROVISION` | Key lifecycle service | Có thể tạo/đăng ký khóa, nhưng không đồng nghĩa được đọc tất cả key đã tạo. |
| `SIGN` | Client signer được provision, hoặc signer service | Nếu trả raw secret, subject có khả năng làm nhiều hơn API `SIGN`. |
| `VERIFY` | HMAC verifier của đúng API/audience | Không cho phép một analytics job “tạm mượn secret”. |
| `READ_METADATA` | Monitoring/key inventory với quyền giới hạn | Không trả secret bytes, hạn chế enumeration. |
| `ROTATE` | Rotation controller | Thay key mới, overlap có kiểm soát, không làm rơi nonce history. |
| `REVOKE` | Security controller/incident role | Có thể vô hiệu hóa key nhanh; cần audit/chống lạm quyền. |
| `EXPORT_SECRET` | Tốt nhất **không có**, trừ quy trình provisioning đặc biệt | Export làm mở rộng trust boundary, cần approval/handling cao nhất. |

**Context** có thể gồm môi trường, caller workload ID, audience, method/route, trạng thái key, thời gian server, tổ chức/tenant và policy version. Không cấp quyền **chỉ vì client gửi header `env=prod`**; environment và audience phải được xác định từ **server configuration và authenticated workload**.

### 3.1. Separation of duties

| Vai trò | Provision | Read raw secret | Sign | Verify | Rotate/Revoke |
| --- | --- | --- | --- | --- | --- |
| External client signer | Không | Chỉ secret đã cấp của chính client, nếu mô hình export | Có | Không cần server verifier API | Không |
| Payment API verifier | Không | Chỉ key cần verify, **nếu mô hình raw-key** | Có khả năng mật mã khi giữ raw key | Có | Không |
| KMS-backed verifier | Không | **Không** nếu MAC verify không export | Không qua API nếu deny GenerateMac | Có qua VerifyMac | Không |
| Rotation controller | Có thể được ủy quyền | Không cần đọc raw key cũ | Không cần | Không cần | Có |
| Support engineer | Không | Không | Không | Không | Chỉ yêu cầu/quy trình có duyệt |
| Analytics/CI runner | Không | Không | Không | Không | Không |

Đây là **policy mục tiêu**, không phải sự thật tự động từ tên role. Một credential IAM được cấp cả `GetSecretValue` và `RotateSecret` thì tài khoản đó vẫn có cả hai quyền dù bảng vai trò ghi khác.

## 4. Policy-as-code và deny-by-default

Quy tắc có thể mô tả ở dạng **minh họa**, không phải cú pháp có thể copy trực tiếp vào AWS IAM, Vault ACL hay một sản phẩm cụ thể:

~~~yaml
# PSEUDOCODE — policy engine riêng của bài, KHÔNG phải provider IAM thật.
policyVersion: "hmac-secret-access-v1"
default: DENY
grants:
  - principal: "workload:payments-verifier-prod"
    environment: "prod"
    audience: "payments-api"
    clientId: "partner-42"
    keyIds: ["key-2026-11", "key-2026-12"]
    operations: ["VERIFY"]

  - principal: "workload:partner-42-signer"
    environment: "prod"
    audience: "payments-api"
    clientId: "partner-42"
    keyIds: ["key-2026-11", "key-2026-12"]
    operations: ["SIGN"]

  - principal: "workload:key-rotation-controller-prod"
    environment: "prod"
    audience: "payments-api"
    clientId: "partner-42"
    keyIds: ["key-2026-11", "key-2026-12"]
    operations: ["ROTATE", "REVOKE"]
~~~

Từ policy này:

- Verifier `payments-verifier-prod` **không** tự động đọc key của `admin-api`, `partner-77` hoặc `staging`.
- Signer của `partner-42` **không** được tự ý chuyển sang `VERIFY`/`REVOKE` ở secret service.
- Rotation controller có thể quản lý lifecycle nhưng **không** được export secret nếu thiếu grant cụ thể.
- Dịch vụ `analytics-worker-prod` không được dùng key nào dù có network access tới secret manager.
- Thêm key ID mới đòi hỏi **phê duyệt và cập nhật policy/version** hoặc một template có scope được kiểm soát; không cấp wildcard toàn bộ khách hàng cho tiện.

**Deny-by-default** cần được thực thi bởi provider/store và network policy phù hợp. Một nhánh `if (policy == null) return allow;` phá hỏng hoàn toàn mục tiêu của bảng grant.

### 4.1. ABAC và wildcard có kiểm soát

Với hàng nghìn client, hard-code từng grant có thể quá lớn. Có thể dùng attribute-based access control (ABAC) hoặc token workload được chứng thực có scope:

~~~text
principal.service == "payments-verifier"
AND principal.environment == resource.environment
AND principal.audience == resource.audience
AND resource.clientId IN trustedAssignedClientPartitions
AND action == "VERIFY"
~~~

**Quan trọng:** `trustedAssignedClientPartitions` phải được cấp qua hệ thống phân quyền, không lấy từ `X-Client-Id` chưa được xác minh. Wildcard như `clientId="*"` cho toàn bộ production làm tăng blast radius: nếu verifier bị compromise, attacker có thể truy cập secret của mọi client.

### 4.2. Explicit deny và policy precedence

Trong một policy engine thực, có thể có explicit deny ưu tiên allow. Ví dụ:

~~~text
ALLOW   verifier-prod -> VERIFY client=partner-42
DENY    keyId=key-2026-10 when revoked=true
DENY    workload environment=staging -> prod resources
DENY    all principals -> EXPORT_SECRET
~~~

Không chỉ xét grant thô: **key status, environment, route/audience và emergency revoke** vẫn phải được kiểm tra. Dữ liệu policy/key status cần snapshot/version rõ, tránh một replica dùng policy cũ trong khi replica khác đã thu hồi.

## 5. Provisioning và bootstrap: ai trao secret ban đầu?

Quyền đọc secret thường bị phá ngay ở **bước bootstrap**:

~~~mermaid
sequenceDiagram
    participant O as Authorized operator
    participant K as Key lifecycle service
    participant M as Secret manager/KMS
    participant C as Authorized client signer
    participant V as Payment verifier
    O->>K: Duyệt create/rotate key cho client+audience
    K->>M: Generate random secret / non-exportable key
    M-->>K: Key record + internal reference
    K->>M: Set policy grants theo environment/client/operation
    alt Mô hình export secret cho client
        K->>C: Provision secret qua kênh bảo mật có xác thực
    else Mô hình client dùng key service
        C->>M: Authorized MAC generation API
    end
    V->>M: VerifyMac hoặc retrieve key theo least privilege
    M-->>V: Kết quả verify hoặc leased material phù hợp policy
~~~

### 5.1. Sinh key và cấp phát

- Với **HMAC-SHA256**, dùng **CSPRNG** tạo key có entropy đủ mạnh (ví dụ 32 byte ngẫu nhiên); **không** dùng mật khẩu ngắn, timestamp hoặc UUID thông thường như secret material.
- Không dùng **một shared secret cho toàn bộ khách hàng**. Scope ít nhất theo client và audience, cân nhắc môi trường, độ nhạy và yêu cầu đa tenant.
- Không gửi secret qua email, chat, ticket, log, URL query, HTTP header thông thường hoặc commit vào repository.
- Nếu bắt buộc cấp secret trực tiếp cho client, dùng **kênh phân phối xác thực, mã hóa, giới hạn thời gian**, chỉ hiển thị một lần theo policy; client phải có cơ chế lưu secret an toàn.
- Tách `keyId` công khai khỏi **internal secret reference** trong KMS/secret manager. Header `kid` không được trực tiếp làm path để lấy secret.

### 5.2. Bootstrap identity: tránh vòng tròn tin cậy

Service không thể “tự khai tôi là payments-verifier” bằng request parameter rồi được lấy secret. Bootstrap nên dùng credential của nền tảng (workload identity/mTLS/service account) với vòng đời quản trị riêng; secret manager xác thực **chủ thể gọi** trước khi trả key/cho VerifyMac.

Nếu cả service và secret manager nằm chung hạ tầng, cần kiểm soát quyền impersonation, token exchange, audience restriction và thời hạn credential. **Cấp quyền đọc toàn bộ secret cho node/host chung** có thể phá isolation giữa nhiều workload trên cùng node.

## 6. Lưu trữ và sử dụng secret: hạn chế xuất material

### 6.1. Các phương án

| Phương án | Thuận lợi | Giới hạn và điều kiện |
| --- | --- | --- |
| KMS/HSM **non-exportable HMAC key** với MAC API | Service không nhận raw secret; có audit theo operation. | Phụ thuộc dịch vụ/cost/latency/availability; client signer phải có cơ chế dùng cùng key. |
| Secret manager trả raw key qua authenticated API | Dễ tích hợp `javax.crypto.Mac` trong Java. | Service process nắm secret, có thể tự tính MAC; phải hạn chế quyền, RAM/log/cache. |
| Secret volume/file được mount chỉ đọc | Hạn chế đưa vào source/config trực tiếp; dễ inject workload. | Phải kiểm soát file permissions, refresh, backup, process access và host isolation. |
| Environment variable | Dễ cấu hình một số runtime. | Dễ lộ qua process diagnostics, crash report, debug/log, deployment metadata hoặc operator access; khó rotate an toàn. |
| Plain configuration / source code | Dễ thử local | **Không phù hợp production**: secret bị lan qua git, artifact, CI logs, image layers. |
| Shared cache of all clients' secrets ở gateway | Lookup nhanh | Blast radius lớn; cần partition, cache bounds, revoke propagation và trust boundary. |

### 6.2. Least exposure time và bộ nhớ Java

Khi lấy secret bytes trong Java:

- Ưu tiên **thời gian sống ngắn**, không copy secret vào immutable `String`, exception message hoặc debug output.
- `byte[]` có thể được zeroized bằng `Arrays.fill(bytes, (byte) 0)` trong `finally` khi không còn sử dụng, nhưng **không thể bảo đảm xóa sạch mọi bản sao** trong heap/GC/JCA provider/native memory.
- `SecretKeySpec` thường cần giữ key bytes trong đối tượng riêng; xóa array gốc **không đồng nghĩa** secret đã biến mất khỏi toàn bộ RAM. Giảm duplicate và giới hạn process privilege quan trọng hơn lời hứa “zeroize hoàn toàn”.
- `Mac` là đối tượng **có trạng thái**, không chia sẻ một instance chưa đồng bộ cho nhiều request.
- Không đưa secret vào `toString()` của record, metrics, trace attributes hoặc lỗi `IllegalArgumentException("key=" + secret)`.

### 6.3. Cache secret có chính sách riêng

Cache ngắn hạn có thể giảm chi phí gọi secret manager/KMS, nhưng phải nêu rõ:

~~~text
cacheKey = (environment, audience, clientId, keyId, policyVersion)
cacheTTL <= configured maximum staleness for key / revoke policy
~~~

Không chỉ cache theo `keyId`: cùng ID có thể dùng cho client khác. Không tự coi lỗi KMS timeout là `NOT_FOUND` rồi sử dụng **secret mặc định**. Nếu cache có thể phục vụ trong outage, cần chính sách explicit về **staleness, revoke SLA, key expiry và thời điểm fail-closed**; không biến cache stale thành đường bypass.

## 7. Lookup, unknown key ID và lỗi secret store

HTTP client có thể gửi:

~~~http
X-Client-Id: partner-42
X-Key-Id: key-2026-99
~~~

Verifier chưa thể tin `partner-42` là identity thực; các trường trên chỉ là **lookup hints**. Dùng các hint đã validate để lấy key **đúng scope**, tính HMAC, rồi mới xác nhận identity.

~~~text
locator = (
    serverConfiguredEnvironment,
    serverConfiguredAudience,
    claimedClientId,
    claimedKeyId
)

lookup(locator):
    ACCESS_DENIED  -> fail closed; không tiết lộ policy chi tiết
    NOT_FOUND      -> authentication failed; không thử key khác
    UNAVAILABLE    -> fail closed; xử lý lỗi hạ tầng riêng
    FOUND_INACTIVE -> authentication failed
    FOUND_ACTIVE   -> dùng đúng key cho HMAC (không fallback)
~~~

### 7.1. Không thử tất cả secret khi `kid` không tìm thấy

Sai:

~~~java
// SAI: nếu kid lạ thì thử toàn bộ secret, khiến key ID mất nghĩa.
// for (byte[] key : allClientSecrets) {
//     if (macMatches(key, request)) return ACCEPT;
// }
~~~

Hậu quả: không kiểm soát được rotation/revoke, tăng CPU theo số key, có thể dùng secret sai scope hoặc để attacker thăm dò key. Key ID phải được **ký trong canonical** và verifier chọn **đúng một key record** theo contract.

### 7.2. Response public và audit nội bộ

Một request có secret bị revoke, unknown key ID hoặc bad HMAC có thể nhận response public 401 chung để hạn chế enumeration:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: HMAC-V1 realm="payments-api"
Content-Type: application/json
Cache-Control: no-store

{"error":"INVALID_AUTHENTICATION"}
~~~

`HMAC-V1` chỉ là auth scheme **ví dụ**. Log nội bộ có thể phân loại `ACCESS_DENIED`, `UNKNOWN_KEY_ID`, `KEY_REVOKED`, `BAD_SIGNATURE`, `KMS_TIMEOUT` dưới mã kiểm soát, nhưng **không log raw secret, raw signature, signed body hoặc một danh sách key hợp lệ**. Không đưa raw `kid` chưa tin cậy làm metrics label không giới hạn cardinality.

### 7.3. Access policy của secret manager khác authentication của HTTP client

~~~text
Secret manager kiểm tra:
    "Workload payments-verifier-prod có quyền VERIFY key của partner-42?"

API HMAC verifier kiểm tra:
    "HTTP request này được ký bởi bên biết key của partner-42 không?"

Business authorization kiểm tra:
    "partner-42 có quyền tạo payment này trong tenant shop-01 không?"
~~~

**Ba quyết định khác nhau.** Một verifier được cấp quyền gọi KMS VerifyMac không có nghĩa HTTP client đã xác thực. Một HTTP client xác thực thành công bằng HMAC cũng không có quyền mặc định với mọi tenant/resource.

## 8. Rotation, revocation và thu hẹp blast radius

### 8.1. Lifecycle của một key version

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> STAGED: Provisioning và policy grants hoàn tất
    STAGED --> ACTIVE: activeFrom theo policy
    ACTIVE --> OVERLAP: Key mới cùng client được kích hoạt
    OVERLAP --> RETIRED: Client chuyển hết sang key mới
    ACTIVE --> REVOKED: Security incident
    OVERLAP --> REVOKED: Security incident
    RETIRED --> REVOKED: Thu hồi khẩn
    REVOKED --> [*]: Retention / deletion theo policy
    RETIRED --> [*]: Deletion sau retention
~~~

Policy và key metadata phải được deploy **trước** khi client dùng ID mới; nếu không, một replica tìm được key, replica khác trả unknown. Trong overlap, verifier có thể dùng **hai key version đang active** nhưng chọn đúng **ID do request khai và được HMAC ký**, không thử fallback.

**Revocation** cần nhanh hơn TTL cache nếu threat model yêu cầu. Có thể dùng key registry versioning, push invalidation, cache TTL ngắn hoặc gateway health/routing gate. Nếu một key bị lộ, chỉ ngừng chấp nhận old secret sau khi **mọi verifier** thực thi revocation mới có thể bảo đảm phạm vi thu hồi.

### 8.2. Quyền rotate không đồng nghĩa quyền ký

Rotation controller cần **tạo key mới, thay policy/metadata và revoke key cũ**, nhưng không nhất thiết cần đọc raw secret. Với HMAC raw-key provisioning cho external client, thao tác export/provision cần kênh/quyền **riêng**; không nên cho một account quản trị vừa tạo, export, approve, audit và xóa mọi secret mà không có giám sát.

### 8.3. Secret bị lộ: phản ứng sự cố

Một incident response điển hình:

1. Giới hạn ngay quyền của principal nghi bị compromise và **revoke key ID bị lộ** trong registry/KMS theo SLA.
2. Xác định phạm vi **client + audience + environment + route** mà key có thể ký; key dùng chung tăng blast radius.
3. Provision key mới qua kênh bảo mật, buộc signer chuyển version; xác thực lại access grants và mọi cache/verifier.
4. Điều tra log **đã giảm thiểu dữ liệu**, các request có chữ ký hợp lệ, nonce/time anomalies và tác vụ nghiệp vụ trong giai đoạn rủi ro.
5. Kết hợp business idempotency, transaction logs, authorization audit để xác định và xử lý side effect không mong muốn.
6. Kiểm tra đường lộ qua CI, container image, log, backup, heap dump, support tools; thu hồi các bản sao có thể kiểm soát.
7. Xem lại nguyên nhân và giảm quyền theo least privilege, cô lập tenant, thiết lập monitor/cảnh báo lặp.

**Timestamp/nonce không bù được key bị lộ.** Attacker biết secret có thể ký timestamp và nonce mới; giải pháp là **vô hiệu hóa quyền ký và thay secret**, cùng các lớp giới hạn quyền nghiệp vụ.

## 9. Hợp đồng ví dụ HMAC-SECRET-ACCESS-V1

Để kiểm thử access policy cùng xác thực, bài sử dụng hợp đồng minh họa:

| Thành phần | Quy định |
| --- | --- |
| Environment | `prod` do server/workload config chọn |
| Audience | `payments-api` do server route policy chọn |
| Method và raw target | `POST /v1/payments?currency=VND` |
| Client / key ID | `partner-42` / `key-2026-11` hoặc `key-2026-12` |
| Signed headers | Client ID, key ID, timestamp, nonce, content type và body SHA-256 |
| Timestamp | Unix epoch seconds chính tắc, `[1-9][0-9]{0,18}` |
| Freshness | `now-300 <= ts <= now+60`, inclusive |
| Nonce | 16 random bytes, lowercase hex 32 ký tự |
| HMAC | Full HMAC-SHA256 32 byte, Base64 chuẩn padded (44 ký tự) |
| Secret access | Explicit grant `(workload,env,audience,client,kid,action)` |
| Key lookup | Exact `(env,audience,client,kid)`, key active/not revoked |
| Replay store | Atomic claim theo `(audience, authenticatedClient, nonce)` |

Canonical request:

~~~text
HMAC-SECRET-ACCESS-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:1795831200
x-nonce:00112233445566778899aabbccddeeff
content-type:application/json
x-content-sha256:<lowercase-hex-sha256-body>
~~~

Các dòng nối bằng **LF**, UTF-8, **không newline cuối**. `<lowercase-hex-sha256-body>` là placeholder. Client ký đúng các bytes ấy; server tính lại từ **method, target, signed headers và body bytes thực nhận**. Header `X-Signature` là tag đã encode, **không** tự nằm trong canonical.

## 10. Java 17: policy-enforced secret lease và HMAC verifier

Chương trình tự chứa `SecretAccessPolicyExample.java` dưới đây minh họa **quyền truy cập secret trước khi sử dụng HMAC**. Ví dụ dùng `Vault` giả lập có grant chính xác; signer và verifier là hai workload principal khác nhau. `Vault.lease` **copy secret test** vào một `SecretLease` ngắn hạn, `close()` cố gắng zeroize bản copy.

**Giới hạn quan trọng:** Đây là **unit-test model**, không phải IAM/KMS thực, không có distributed persistence hay chứng thực workload từ cloud platform; các `Principal` được tạo trong `main` chỉ để mô phỏng trusted identity. Khi provider trả raw key cho Java process, policy chỉ kiểm soát **đường truy xuất**, **không** ngăn process bị chiếm quyền tự tính HMAC bằng key đó. Nonce store chỉ là `ConcurrentHashMap` trong một JVM, không có TTL hoặc replication.

### 10.1. Java 17 full example

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
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SecretAccessPolicyExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String ENV = "prod";
    private static final String AUDIENCE = "payments-api";
    private static final String CLIENT = "partner-42";
    private static final String METHOD = "POST";
    private static final String TARGET = "/v1/payments?currency=VND";
    private static final String TYPE = "application/json";
    private static final String KID_OLD = "key-2026-11";
    private static final String KID_NEW = "key-2026-12";
    private static final String KID_UNKNOWN = "key-2026-99";
    private static final long PAST = 300;
    private static final long FUTURE = 60;

    enum Operation { SIGN, VERIFY, ROTATE, REVOKE }

    enum VerificationResult {
        AUTHENTICATED, MALFORMED, UNKNOWN_KEY, ACCESS_DENIED, INACTIVE_KEY,
        STALE_TIMESTAMP, BAD_SIGNATURE, REPLAY, STORE_UNAVAILABLE
    }

    // WorkloadPrincipal đến từ TRUSTED platform identity trong production.
    record Principal(String name, String environment) {}
    record Locator(
        String environment, String audience,
        String clientId, String keyId
    ) {}
    record Grant(String principalName, Locator locator,
                 Operation operation) {}
    record KeyRecord(
        Locator locator, byte[] secret,
        Instant activeFrom, Instant expiresAt, boolean revoked
    ) {}
    record Request(
        String method, String target, String clientId, String keyId,
        String timestamp, String nonce, String contentType,
        String bodyDigest, String signature, byte[] body
    ) {}

    static final class AccessFailure extends RuntimeException {
        final VerificationResult reason;
        AccessFailure(VerificationResult reason) {
            super(reason.name()); // Không chứa secret trong exception.
            this.reason = reason;
        }
    }

    static final class SecretLease implements AutoCloseable {
        private byte[] bytes;
        SecretLease(byte[] copied) { this.bytes = copied; }
        byte[] material() {
            if (bytes == null) {
                throw new IllegalStateException("Lease closed");
            }
            return bytes;
        }
        @Override public void close() {
            if (bytes != null) {
                Arrays.fill(bytes, (byte) 0);
                bytes = null;
            }
        }
    }

    // Chỉ mô phỏng access checks trên local map. KHÔNG phải real Vault.
    static final class Vault {
        private final Map<Locator, KeyRecord> keys = new HashMap<>();
        private final Set<Grant> grants = new HashSet<>();
        private boolean available = true;

        void putTestRecord(KeyRecord record) {
            keys.put(record.locator(), record);
        }
        void allow(Principal principal, Locator loc, Operation op) {
            grants.add(new Grant(principal.name(), loc, op));
        }
        void setAvailable(boolean value) { available = value; }

        boolean may(Principal principal, Locator loc, Operation op) {
            return principal != null && loc != null &&
                principal.environment().equals(loc.environment()) &&
                grants.contains(new Grant(principal.name(), loc, op));
        }

        SecretLease lease(Principal principal, Locator loc,
                Operation purpose, Instant serverNow) {
            if (!available) {
                throw new AccessFailure(VerificationResult.STORE_UNAVAILABLE);
            }
            if (purpose != Operation.SIGN &&
                purpose != Operation.VERIFY) {
                throw new AccessFailure(VerificationResult.ACCESS_DENIED);
            }
            if (!may(principal, loc, purpose)) {
                throw new AccessFailure(VerificationResult.ACCESS_DENIED);
            }
            KeyRecord r = keys.get(loc);
            if (r == null) {
                throw new AccessFailure(VerificationResult.UNKNOWN_KEY);
            }
            if (!loc.equals(r.locator()) || r.revoked() ||
                r.secret() == null || r.secret().length < 32 ||
                r.activeFrom() == null || r.expiresAt() == null ||
                serverNow.isBefore(r.activeFrom()) ||
                !serverNow.isBefore(r.expiresAt())) {
                throw new AccessFailure(VerificationResult.INACTIVE_KEY);
            }
            // Production nên dùng non-exportable KMS VerifyMac API.
            // Copy ra raw secret ở đây CHỈ để dạy javax.crypto.Mac.
            return new SecretLease(r.secret().clone());
        }

        void revoke(Principal principal, Locator loc) {
            if (!available) {
                throw new AccessFailure(VerificationResult.STORE_UNAVAILABLE);
            }
            if (!may(principal, loc, Operation.REVOKE)) {
                throw new AccessFailure(VerificationResult.ACCESS_DENIED);
            }
            KeyRecord r = keys.get(loc);
            if (r == null) {
                throw new AccessFailure(VerificationResult.UNKNOWN_KEY);
            }
            keys.put(loc, new KeyRecord(r.locator(), r.secret(),
                r.activeFrom(), r.expiresAt(), true));
        }
    }

    // Demo trong một JVM: không TTL, không bảo vệ cluster.
    static final class Nonces {
        private final Set<String> claimed =
            ConcurrentHashMap.newKeySet();
        boolean claim(String audience, String clientId, String nonce) {
            String k = audience.length() + ":" + audience
                + clientId.length() + ":" + clientId
                + nonce.length() + ":" + nonce;
            return claimed.add(k);
        }
    }

    static byte[] randomSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return bytes;
    }

    static String randomNonce() {
        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    static boolean validId(String text) {
        return text != null &&
            text.matches("[a-z0-9][a-z0-9-]{0,39}");
    }

    static String sha256Hex(byte[] input)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(input));
    }

    static byte[] hmac(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8));
    }

    static Long parseTs(String text) {
        if (text == null || !text.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException overflow) {
            return null;
        }
    }

    static boolean fresh(long ts, long now) {
        try {
            return ts >= Math.subtractExact(now, PAST)
                && ts <= Math.addExact(now, FUTURE);
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static String canonical(String audience, Request r, String hash) {
        if (r == null || !METHOD.equals(r.method()) ||
            !TARGET.equals(r.target()) ||
            !TYPE.equals(r.contentType()) ||
            !validId(r.clientId()) || !validId(r.keyId()) ||
            parseTs(r.timestamp()) == null ||
            r.nonce() == null || !r.nonce().matches("[0-9a-f]{32}") ||
            hash == null || !hash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Signing contract invalid");
        }
        return String.join("\n",
            "HMAC-SECRET-ACCESS-V1",
            r.method(), r.target(),
            "audience:" + audience,
            "x-client-id:" + r.clientId(),
            "x-key-id:" + r.keyId(),
            "x-timestamp:" + r.timestamp(),
            "x-nonce:" + r.nonce(),
            "content-type:" + r.contentType(),
            "x-content-sha256:" + hash);
    }

    static byte[] strictDecodeTag(String value) {
        if (value == null ||
            !value.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] bytes = Base64.getDecoder().decode(value);
            if (bytes.length != 32 ||
                !Base64.getEncoder().encodeToString(bytes)
                    .equals(value)) {
                return null;
            }
            return bytes;
        } catch (IllegalArgumentException malformed) {
            return null;
        }
    }

    static Request sign(Principal signer, Vault vault,
            String kid, Clock clock, String nonce, byte[] body)
            throws GeneralSecurityException {
        String ts = Long.toString(clock.instant().getEpochSecond());
        String hash = sha256Hex(body);
        Request unsigned = new Request(
            METHOD, TARGET, CLIENT, kid, ts, nonce,
            TYPE, hash, "", body.clone());
        String text = canonical(AUDIENCE, unsigned, hash);
        Locator loc = new Locator(ENV, AUDIENCE, CLIENT, kid);
        String signature;
        try (SecretLease lease = vault.lease(
                signer, loc, Operation.SIGN, clock.instant())) {
            signature = Base64.getEncoder().encodeToString(
                hmac(lease.material(), text));
        }
        return new Request(
            METHOD, TARGET, CLIENT, kid, ts, nonce,
            TYPE, hash, signature, body.clone());
    }

    // Trả mã nội bộ; public HTTP mapping cần response chung/không leak ID.
    static VerificationResult verify(Principal verifier, Vault vault,
            Request r, Clock clock, Nonces nonces)
            throws GeneralSecurityException {
        if (r == null || r.body() == null ||
            r.body().length > 65536 ||
            !validId(r.clientId()) || !validId(r.keyId())) {
            return VerificationResult.MALFORMED;
        }
        byte[] supplied = strictDecodeTag(r.signature());
        Long ts = parseTs(r.timestamp());
        if (supplied == null || ts == null) {
            return VerificationResult.MALFORMED;
        }
        Instant nowInstant = clock.instant();
        if (!fresh(ts, nowInstant.getEpochSecond())) {
            return VerificationResult.STALE_TIMESTAMP;
        }

        final String text;
        try {
            String actualHash = sha256Hex(r.body());
            if (!actualHash.equals(r.bodyDigest())) {
                return VerificationResult.BAD_SIGNATURE;
            }
            text = canonical(AUDIENCE, r, actualHash);
        } catch (IllegalArgumentException malformed) {
            return VerificationResult.MALFORMED;
        }

        Locator loc =
            new Locator(ENV, AUDIENCE, r.clientId(), r.keyId());
        byte[] expected;
        try (SecretLease lease = vault.lease(
                verifier, loc, Operation.VERIFY, nowInstant)) {
            expected = hmac(lease.material(), text);
        } catch (AccessFailure denied) {
            return denied.reason; // Không claim nonce.
        }
        if (expected.length != 32 ||
            !MessageDigest.isEqual(expected, supplied)) {
            return VerificationResult.BAD_SIGNATURE;
        }
        // Chỉ claim nonce sau HMAC và policy PASS.
        return nonces.claim(AUDIENCE, r.clientId(), r.nonce())
            ? VerificationResult.AUTHENTICATED
            : VerificationResult.REPLAY;
    }

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    static void rfc4231Vector() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        String actual =
            HexFormat.of().formatHex(hmac(key, "Hi There"));
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        check(expected.equals(actual),
            "RFC 4231 HMAC-SHA256 known-answer test");
    }

    public static void main(String[] args) throws Exception {
        rfc4231Vector();
        Principal signer =
            new Principal("workload:partner-42-signer", ENV);
        Principal verifier =
            new Principal("workload:payments-verifier-prod", ENV);
        Principal rotation =
            new Principal("workload:key-rotation-controller-prod", ENV);
        Principal analytics =
            new Principal("workload:analytics-worker-prod", ENV);
        Principal stagingVerifier =
            new Principal("workload:payments-verifier-prod", "staging");

        Locator oldLoc = new Locator(
            ENV, AUDIENCE, CLIENT, KID_OLD);
        Locator newLoc = new Locator(
            ENV, AUDIENCE, CLIENT, KID_NEW);
        Locator unknownLoc = new Locator(
            ENV, AUDIENCE, CLIENT, KID_UNKNOWN);
        Instant from = Instant.parse("2026-01-01T00:00:00Z");
        Instant until = Instant.parse("2027-01-01T00:00:00Z");
        Vault vault = new Vault();
        vault.putTestRecord(
            new KeyRecord(oldLoc, randomSecret(), from, until, false));
        vault.putTestRecord(
            new KeyRecord(newLoc, randomSecret(), from, until, false));
        vault.allow(signer, oldLoc, Operation.SIGN);
        vault.allow(signer, newLoc, Operation.SIGN);
        vault.allow(verifier, oldLoc, Operation.VERIFY);
        vault.allow(verifier, newLoc, Operation.VERIFY);
        vault.allow(verifier, unknownLoc, Operation.VERIFY);
        vault.allow(rotation, oldLoc, Operation.REVOKE);
        vault.allow(rotation, newLoc, Operation.REVOKE);

        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"),
            ZoneOffset.UTC);
        byte[] body =
            "{\"orderId\":\"ord-123\",\"amount\":50000}"
                .getBytes(StandardCharsets.UTF_8);
        Request signed = sign(
            signer, vault, KID_OLD, fixed, randomNonce(), body);
        HttpRequest sample = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + TARGET))
            .header("Content-Type", signed.contentType())
            .header("X-Client-Id", signed.clientId())
            .header("X-Key-Id", signed.keyId())
            .header("X-Timestamp", signed.timestamp())
            .header("X-Nonce", signed.nonce())
            .header("X-Content-SHA256", signed.bodyDigest())
            .header("X-Signature", signed.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(signed.body()))
            .build(); // Không gửi HTTP qua mạng.
        check(METHOD.equals(sample.method()), "HTTP method");
        check(verify(verifier, vault, signed, fixed, new Nonces())
                == VerificationResult.AUTHENTICATED, "Verifier explicitly granted should pass");

        // Mặc định DENY: một workload không có grant không lấy secret.
        check(verify(analytics, vault, signed, fixed, new Nonces())
                == VerificationResult.ACCESS_DENIED,
            "Analytics worker must not use HMAC key");
        check(verify(stagingVerifier, vault, signed, fixed, new Nonces())
                == VerificationResult.ACCESS_DENIED,
            "Staging workload cannot access prod secret");
        check(verify(signer, vault, signed, fixed, new Nonces())
                == VerificationResult.ACCESS_DENIED,
            "SIGN grant does not authorize VERIFY API");

        // Quyền quản lý/revoke không phải quyền export/use key.
        check(verify(rotation, vault, signed, fixed, new Nonces())
                == VerificationResult.ACCESS_DENIED,
            "Rotation controller cannot use verifier secret");

        // Client/key ID đúng format nhưng key không tồn tại.
        Request unknown = new Request(
            signed.method(), signed.target(), signed.clientId(),
            KID_UNKNOWN, signed.timestamp(), signed.nonce(),
            signed.contentType(), signed.bodyDigest(),
            signed.signature(), signed.body());
        check(verify(verifier, vault, unknown, fixed, new Nonces())
                == VerificationResult.UNKNOWN_KEY,
            "Permitted lookup, missing key must fail closed");

        // Đổi client ID sẽ chuyển sang một locator không được grant.
        Request otherClient = new Request(
            signed.method(), signed.target(), "partner-77",
            signed.keyId(), signed.timestamp(), signed.nonce(),
            signed.contentType(), signed.bodyDigest(),
            signed.signature(), signed.body());
        check(verify(verifier, vault, otherClient, fixed, new Nonces())
                == VerificationResult.ACCESS_DENIED,
            "No access to another client secret");

        // Key mới được cấp đúng 2 principal; HMAC mới đúng.
        Request newRequest = sign(
            signer, vault, KID_NEW, fixed, randomNonce(), body);
        check(verify(verifier, vault, newRequest, fixed, new Nonces())
                == VerificationResult.AUTHENTICATED, "Rotation overlap new key must pass");

        // Tamper signature giữ nguyên key => BAD_SIGNATURE, không fallback.
        byte[] changedTag =
            strictDecodeTag(signed.signature());
        check(changedTag != null, "full tag");
        changedTag[0] ^= 1;
        Request tampered = new Request(
            signed.method(), signed.target(), signed.clientId(),
            signed.keyId(), signed.timestamp(), signed.nonce(),
            signed.contentType(), signed.bodyDigest(),
            Base64.getEncoder().encodeToString(changedTag),
            signed.body());
        Nonces nonceGuard = new Nonces();
        check(verify(verifier, vault, tampered, fixed, nonceGuard)
                == VerificationResult.BAD_SIGNATURE,
            "Invalid HMAC must not be accepted");
        check(verify(verifier, vault, signed, fixed, nonceGuard)
                == VerificationResult.AUTHENTICATED, "Bad HMAC must not burn nonce");
        check(verify(verifier, vault, signed, fixed, nonceGuard)
                == VerificationResult.REPLAY, "Same nonce must not be accepted twice");

        // Timestamp quá hạn dù key active và HMAC đúng.
        Request stale = sign(signer, vault, KID_OLD,
            Clock.offset(fixed, Duration.ofSeconds(-301)),
            randomNonce(), body);
        check(verify(verifier, vault, stale, fixed, new Nonces())
                == VerificationResult.STALE_TIMESTAMP,
            "Stale timestamp must be rejected");

        // Key được revoke bởi controller có quyền; verifier từ chối.
        vault.revoke(rotation, oldLoc);
        check(verify(verifier, vault, signed, fixed, new Nonces())
                == VerificationResult.INACTIVE_KEY,
            "Revoked old key must be denied");
        check(verify(verifier, vault, newRequest, fixed, new Nonces())
                == VerificationResult.AUTHENTICATED, "New key still active after old key revoked");

        // KMS/Vault outage không phải unknown key; phải fail closed.
        vault.setAvailable(false);
        check(verify(verifier, vault, newRequest, fixed, new Nonces())
                == VerificationResult.STORE_UNAVAILABLE,
            "Secret store outage cannot bypass access policy");
        System.out.println(
            "PASS: secret grants, scoped HMAC, revoke, replay, outage");
    }
}
~~~

### 10.2. Đọc flow xác minh

Chương trình gọi `vault.lease(verifier, locator, Operation.VERIFY, serverNow)` **sau khi xác định locator từ request nhưng trước HMAC**. Policy ở `Vault` chỉ cho đúng workload, môi trường, audience, client ID, key ID và operation; **unknown/denied/inactive** đều không tạo nonce claim. Trạng thái public HTTP cần được map từ `Failure` sang lỗi an toàn, không trả chi tiết key registry.

~~~mermaid
flowchart TD
    R["Request có client ID, key ID, ts, nonce, body và signature"] --> C["Strict parse + server-fixed environment/audience"]
    C --> P["Policy check: workload principal + resource + VERIFY"]
    P -->|DENY| X["Fail closed"]
    P -->|ALLOW| K["Get scoped key / call KMS VerifyMac"]
    K -->|Unknown / inactive / unavailable| X
    K -->|Active| M["Canonical + expected HMAC tag"]
    M --> E{"Full tag đúng?"}
    E -->|Không| X
    E -->|Có| T["Freshness và atomic nonce claim"]
    T -->|Pass| A["Business authorization và idempotency"]
~~~

### 10.3. Phân biệt operation-level và material-level security

`Vault` giả lập kiểm tra `SIGN` hoặc `VERIFY` **trước khi cấp một bản copy secret**, nên unit test có thể xác nhận signer không được **gọi API VERIFY**. Nhưng sau khi signer đã nhận bản copy raw key để ký, **mã bị compromise có thể tính HMAC cho bất kỳ message nào**. Demo cố ý cho thấy giới hạn của access control trong ứng dụng khi secret được export.

Để thực thi separation-of-operation đáng tin hơn, dùng KMS/HSM non-exportable keys và API MAC có phân quyền độc lập, hoặc cân nhắc chữ ký bất đối xứng nếu kiến trúc yêu cầu.

### 10.4. Tại sao `SecretLease.close()` chưa đủ “xóa secret”?

~~~java
try (SecretLease lease = vault.lease(
        verifier, loc, Operation.VERIFY, now)) {
    byte[] tag = hmac(lease.material(), canonicalText);
    // Không log lease.material(), không giữ tham chiếu lâu dài.
}
~~~

`close()` zeroize **bản copy trong lease**, nhưng `SecretKeySpec`, JCA provider hoặc runtime có thể đã tạo thêm copy. Không hứa zeroization tuyệt đối trong managed memory. Bảo vệ process, giới hạn quyền debug/heap dump, dùng provider/HSM phù hợp và tránh log sẽ giảm rủi ro thực tế hơn.

### 10.5. Nonce store trong demo không phải production

`Nonces` chỉ dùng một `Set` atomic trong một JVM và **không có TTL**. Production cần store dùng chung các replica, **atomic claim-if-absent** với retention tới sau `signedTimestamp + pastWindow + safetyMargin` hoặc TTL tương đối đủ `P+F+margin`. Với `P=300,F=60,M=10`, TTL bảo thủ có thể là **370 giây**, không phải 60 hoặc 300 giây tính từ claim sớm nhất.

## 11. Proxy/gateway và đường truy cập secret manager

~~~mermaid
sequenceDiagram
    participant C as External client
    participant G as Trusted gateway
    participant V as Verifier workload
    participant K as KMS/secret manager
    participant N as Shared nonce store
    participant B as Backend
    C->>G: HTTP HMAC (client ID, key ID, ts, nonce, sig)
    G->>G: Reject duplicate/ambiguous security headers
    G->>V: Verified ingress path + actual canonical input bytes
    V->>K: Workload identity + VERIFY scoped key request
    alt Principal không được grant hoặc key invalid
        K-->>V: DENY / NOT_FOUND / UNAVAILABLE
        V-->>C: Fail closed
    else Scoped key/capability hợp lệ
        K-->>V: MAC verify outcome hoặc key lease đúng scope
        V->>V: HMAC + freshness policy
        V->>N: Atomic nonce claim sau HMAC
        N-->>V: Created / Replay
        V->>B: Verified client identity, method, route, body
        B->>B: Authorization + idempotency
    end
~~~

### 11.1. Các điểm bypass thường gặp

| Tình huống | Nguy cơ | Biện pháp |
| --- | --- | --- |
| Gateway có quyền đọc secret của **mọi client** | Compromise một gateway lộ toàn bộ khách hàng | Partition theo audience/client/shard, workload policy và KMS boundary. |
| Backend tin `X-Verified: true` từ Internet | Bypass HMAC, secret policy vô nghĩa | Strip incoming identity headers, xác thực gateway→backend, chặn direct access. |
| Header `X-Key-Id` trùng | Gateway/backend chọn key ID khác nhau | Reject duplicate security header tại ingress, case-insensitive. |
| Proxy thay raw path/query hoặc body sau verify | MAC bảo vệ một action, backend thực thi action khác | Verify signed method/target/body ở boundary nhất quán. |
| Secret manager path lấy thẳng từ `kid` | Path traversal, privilege crossover | Validate kid, map sang internal reference qua trusted registry. |
| Service account dùng chung giữa staging và prod | Staging compromise truy cập prod secrets | Tách IAM principal và resource environment. |
| CI job có root secrets | Build log/image/developer access gây lộ key | Dùng workload identity/ephemeral credentials, không inject prod secret vào build. |
| KMS outage được catch rồi bỏ verify | Authentication bypass trong outage | Fail closed và báo lỗi dịch vụ, không “allow by default”. |
| CDN/cache lưu response nhạy cảm theo URL | Client khác thấy dữ liệu xác thực | Cache-Control/no-store theo policy, business authz ở mỗi request. |

### 11.2. HTTP/1.1, HTTP/2 và signing contract

HTTP header names thường không phân biệt hoa/thường, còn `X-Key-Id` **value** có định dạng theo contract. HTTP/2 có pseudo-headers như `:method` và `:path`; gateway có thể rewrite path/query, host hoặc content encoding. **Access policy không sửa được canonicalization sai**: verifier phải dùng đúng signed method/raw target/headers/body representation mà backend xử lý, reject ambiguity và bảo toàn integrity qua các hop.

## 12. Audit, monitoring và quyền của con người

Một secret access audit record nên mô tả **sự kiện truy cập** mà không tiết lộ chính secret:

~~~json
{
  "event": "secret_use",
  "principal": "workload:payments-verifier-prod",
  "operation": "VERIFY",
  "resourceScope": "prod/payments-api/partner-42",
  "keyId": "key-2026-11",
  "policyVersion": "v17",
  "decision": "ALLOW",
  "requestId": "req-opaque-123"
}
~~~

Ví dụ JSON là telemetry giả định; không ghi full signature, MAC input nhạy cảm hoặc raw secret. Key ID dù không phải secret vẫn có thể là metadata nhạy cảm; hạn chế retention/access theo policy. Đặc biệt, request ID phải là identifier an toàn, không chứa credential.

**Nên theo dõi:**

- Access `ALLOW`/`DENY` theo principal, environment, audience và **nhãn cardinality có kiểm soát**.
- Thay đổi grant/revoke, secret export, break-glass, key creation/rotation, policy version drift.
- Unknown key ID spike, wrong audience, inactive/revoked key attempts, invalid MAC, clock skew, nonce replay.
- KMS/Vault p95/p99 latency, timeout, throttling, quota, cache TTL, key propagation lag.
- Secret scanning events, debug/heap dump permissions, CI pipeline exposure và image registry access.

### 12.1. Break-glass không phải wildcard vĩnh viễn

Đôi khi incident responder cần quyền khẩn cấp. Quy trình nên có **MFA, mục đích cụ thể, phê duyệt hoặc just-in-time elevation, thời hạn ngắn, session recording/audit và thu hồi tự động**. Không giữ một credential “admin-vĩnh-viễn” trong code, shared chat hoặc máy developer để xử lý mọi outage.

### 12.2. Không dùng metrics label từ input không tin cậy

Attacker có thể gửi một triệu `X-Key-Id` khác nhau. Nếu metrics tạo label `kid=<raw value>`, hệ thống có thể bị bùng nổ cardinality/memory và lộ dữ liệu metadata. Dùng nhãn theo **loại lỗi** và cardinality có giới hạn; lưu truy vết chi tiết trong audit an toàn khi cần.

## 13. Ma trận kiểm thử Secret access policy

Các ca ở bảng là yêu cầu unit/integration. `SecretAccessPolicyExample` chỉ test policy trong một JVM; test KMS/mTLS/CI/multi-replica thực phải chạy trong môi trường tương ứng.

| Case | Setup/hành động | Kết quả mong đợi |
| --- | --- | --- |
| Verifier được cấp `VERIFY` | Đúng workload/environment/audience/client/kid | Có thể dùng VerifyMac/lease phù hợp và xác minh tag. |
| Signer được cấp `SIGN` | Tạo request bằng đúng key đã provision | MAC đúng nếu contract và key active. |
| Signer gọi API `VERIFY` | Chỉ có grant SIGN | **ACCESS_DENIED** ở service policy; chú ý raw-key limitation. |
| Verifier gọi `SIGN` | Chỉ có grant VERIFY | API policy deny; raw key trong RAM vẫn có khả năng ký. |
| Analytics job không có grant | Tự khai “payments-verifier” qua HTTP | Không có trusted workload identity → **DENY**. |
| Staging gọi prod secret | Principal `environment=staging` | **DENY** dù key ID trùng. |
| Cross-client | Verifier grant cho `partner-42`, request dùng `partner-77` | Lookup/permission deny, không mượn secret client khác. |
| Cross-audience | Key payments dùng cho admin API | **DENY**, audience server-controlled. |
| Unknown key ID | ID hợp lệ nhưng key record không có | Reject, không fallback, không claim nonce. |
| Malformed key ID | `../prod/secret` hoặc CR/LF, oversized | Reject trước key store. |
| Key revoked | Record đã revoke | Reject dù MAC cũ khớp. |
| Key expired/not yet active | Server verify time nằm ngoài validity | Reject theo key policy. |
| Rotation overlap | Key cũ/mới active, grant đúng | Chọn đúng kid đã ký, không thử key khác. |
| Revoke khi cache stale | Một replica chưa nhận policy mới | Test phát hiện propagation gap; không hứa revoke instant nếu kiến trúc không bảo đảm. |
| Missing secret manager | KMS/Vault timeout | **Fail closed**, không dùng default key. |
| Key lookup permission denied | Key có trong registry nhưng workload không được grant | Không trả key/không verify, public error generic. |
| Provider VerifyMac denied | KMS không cấp permission dù key tồn tại | Fail closed; không fallback local. |
| Secret export attempt | Support/CI gọi export | Deny và audit. |
| Break-glass expired | Operator dùng JIT privilege đã hết hạn | Deny, session audited. |
| CI logs | Build vô tình print config/environment | Secret redaction/scan test bắt lỗi; không publish artifact. |
| Heap dump access | Untrusted operator đọc heap verifier | Kiểm soát process/OS debug; đánh giá raw-key blast radius. |
| Nonce replay | Gửi lại full signed request | HMAC vẫn đúng, nonce store reject. |
| Timestamp sai | Ký request `now-301` với `P=300` | Stale reject dù secret access hợp lệ. |
| Tampered body/key ID | Sửa wire sau ký | MAC mismatch hoặc lookup fail, không side effect. |
| Gateway header spoofing | Client gửi `X-Verified: true` | Header bị strip, không cấp quyền. |
| Business tenant denied | HMAC/secret policy pass, client sai tenant | **Authorization DENY**; không cho hành động. |
| Retry nonce mới, same business ID | Chữ ký hợp lệ và nonce mới | HMAC có thể pass, **idempotency** phải chống side effect lặp. |
| Multi-region policy drift | Key đã revoke ở A nhưng còn active ở B | Detect, enforce revoke SLA/consistency yêu cầu. |

### Câu hỏi tự đánh giá

1. Vì sao `X-Key-Id` và `X-Client-Id` không được trở thành workload identity cho secret manager trước khi HMAC xác minh?
2. Một service được cấp `VERIFY` nhưng đã nhận **raw HMAC secret** vào RAM có thực sự không thể tự ký request khác không?
3. Nêu sự khác biệt giữa `NOT_FOUND`, `ACCESS_DENIED` và `UNAVAILABLE` trong key lookup. Vì sao cả ba đều không được dẫn tới “allow”?
4. Vì sao secret của `partner-42` tại `prod/payments-api` không nên dùng chung với `staging/admin-api`?
5. Rotation controller có nhất thiết phải đọc được secret cũ để revoke hoặc tạo key mới không?
6. Nếu verifier cache secret 24 giờ nhưng revoke yêu cầu có hiệu lực trong vài phút, thiết kế gặp xung đột gì?
7. Điều gì xảy ra nếu proxy thay `X-Key-Id` sau khi client đã ký canonical request? Vì sao key ID phải nằm trong phần ký?
8. HMAC request hợp lệ, timestamp fresh, nonce mới có đảm bảo client được chuyển tiền từ mọi tenant không? Tại sao?
9. Khi secret bị lộ, vì sao chỉ dựa vào nonce store và freshness window là chưa đủ?
10. Những dữ liệu nào tuyệt đối không nên có trong secret access audit log hoặc tracing span?

## 14. Checklist triển khai production

- [ ] Xác định **trusted workload identity** cho client signer, verifier, gateway, key controller, CI và operator; không dùng header do HTTP client tự khai làm IAM principal.
- [ ] Thiết kế **resource scope** theo environment, audience, client ID, key ID và operation; mặc định **DENY**, explicit grants, không wildcard ngoài nhu cầu.
- [ ] Phân quyền `SIGN`, `VERIFY`, `PROVISION`, `ROTATE`, `REVOKE`, `READ_METADATA` và `EXPORT_SECRET` theo separation of duties.
- [ ] Nếu bắt buộc tách khả năng SIGN khỏi verifier, đánh giá KMS/HSM non-exportable VerifyMac hoặc chữ ký bất đối xứng; không nghĩ raw-key HMAC có thể khóa khả năng ký bằng metadata IAM.
- [ ] Sinh secret HMAC bằng CSPRNG có entropy đủ, scope từng client/audience/môi trường; không lưu trong source, CI log, image, URL hoặc chat.
- [ ] Provision tới client qua kênh xác thực/mã hóa hoặc dịch vụ MAC được ủy quyền; không lấy trực tiếp internal secret path từ `kid` do client cung cấp.
- [ ] Secret manager xác thực workload bằng IAM/mTLS/OIDC tương ứng, credential ngắn hạn; chống impersonation và cross-environment access.
- [ ] Key lookup qua exact locator **(environment, audience, claimedClientId, keyId)**; kiểm tra activeFrom/expiresAt/revoked, algorithm và route policy.
- [ ] Phân biệt `NOT_FOUND`, `ACCESS_DENIED`, `UNAVAILABLE`; **fail closed**, không default key, không auto-create, không fallback hoặc dò toàn bộ secret.
- [ ] Ràng buộc client ID, key ID, timestamp/nonce, method, raw URI/query, signed headers và body digest trong canonical request đúng contract.
- [ ] HMAC full SHA-256 tag, strict Base64 decode, `MessageDigest.isEqual`; `Mac` instance không chia sẻ giữa các request mà không đồng bộ.
- [ ] Sau HMAC và freshness PASS mới atomic claim nonce với shared store, TTL đủ `signedTs+P+margin` hoặc `P+F+margin`, namespace ổn định qua key rotation.
- [ ] Key rotation có provision-before-use, overlap, revoke và rollout consistency; cache secret/policy có TTL/invalidation đáp ứng revoke SLA.
- [ ] Không log/trace raw secret, raw signature, token nhạy cảm hoặc body nhạy cảm; kiểm soát heap dump, debugger, backup và hỗ trợ vận hành.
- [ ] Giám sát IAM DENY, unexpected secret use, KMS errors, key lifecycle, permission changes, negative cache, clock drift và replay metrics không lộ high-cardinality raw IDs.
- [ ] Gateway/backend có trust boundary rõ, reject duplicate security header, strip spoofed identity headers, bảo toàn signed method/target/body và chặn direct bypass.
- [ ] Sau authentication hợp lệ, kiểm tra **authorization theo tenant/action/resource**, rate limits và **idempotency cho side effect**; secret access không thay thế business policy.
- [ ] Có test IAM/integration cho signer/verifier/rotation role, wrong client/audience/environment, unknown/revoked key, outage, cache/revoke propagation, proxy, replay và leak qua CI/log.

**Kết luận:** **Secret access policy** xác định **ai có thể sử dụng hoặc quản lý shared secret nào, cho mục đích gì và trong phạm vi nào**. HMAC-SHA256, canonical request, timestamp và nonce chỉ đáng tin khi secret material được cấp phát, sử dụng, xoay vòng và thu hồi dưới một chính sách **least privilege, deny-by-default, audit và fail-closed**. Với HMAC đối xứng, đặc biệt phải hiểu rằng **cấp raw secret cho verifier cũng trao khả năng tạo MAC về mặt mật mã**; KMS/HSM non-exportable hoặc thiết kế chữ ký bất đối xứng có thể cần thiết khi yêu cầu tách quyền mạnh hơn. Cuối cùng, **secret access policy** bảo vệ quyền dùng khóa, **HMAC authentication** bảo vệ nguồn gốc/tính toàn vẹn request, còn **business authorization** vẫn quyết định hành động nào được phép.
