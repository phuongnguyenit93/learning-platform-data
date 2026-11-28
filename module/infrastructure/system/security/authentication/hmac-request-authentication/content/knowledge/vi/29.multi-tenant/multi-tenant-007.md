# Tenant revocation

**Tenant revocation** là quá trình **chấm dứt quyền sử dụng một tenant hoặc quyền truy cập vào tenant đó** theo chính sách của hệ thống, chẳng hạn khi một tenant bị khóa do sự cố bảo mật, hợp đồng chấm dứt hoặc tổ chức thu hồi ủy quyền. Trong kiến trúc xác thực HTTP request bằng HMAC, đây là một bài toán đặc biệt quan trọng vì **HMAC hợp lệ chỉ xác nhận năng lực sở hữu shared secret**; nó không chứng minh tenant còn hoạt động hay principal được phép thao tác trên tài nguyên của tenant.

Bài học thuộc chương **Multi-tenant**, mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun hướng dẫn thiết kế xác thực HTTP request bằng **HMAC shared secret** và **canonical request** gồm method, URI, signed headers hoặc body theo hợp đồng; thực hành xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**.

> **Nguyên tắc cốt lõi:** Verifier phải xác thực request theo **exact credential ID**, dựng lại canonical bytes và so tag; nhưng **trước khi cho phép hành động trên tenant**, hệ thống phải đánh giá **trạng thái tenant và quyền principal → tenant** từ nguồn đáng tin. Nếu tenant đã bị revoke, **MAC đúng, key còn ACTIVE, nonce mới và timestamp fresh đều không được tạo thành quyền truy cập**. Khi có nhiều nodes/gateways, phải xác định rõ thời điểm và mức nhất quán mà lệnh revoke được bảo đảm.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **tenant revocation**, **key revocation**, **client revocation**, **grant revocation**, **tenant suspension** và **xóa tenant**.
2. Giải thích vì sao xác minh HMAC đúng vẫn có thể phải **từ chối tenant đã bị thu hồi**.
3. Thiết kế dữ liệu registry cho credential, principal, tenant status và principal–tenant grants.
4. Ràng buộc **target tenant/resource** vào canonical request để tránh tráo tenant sau khi ký.
5. Xác định chính sách khi principal sở hữu nhiều tenants hoặc có quyền delegation/cross-tenant.
6. Xây dựng luồng admission với HMAC, timestamp, nonce, tenant status, authorization và business execution.
7. Phân tích revocation propagation trên gateway, verifier cache, replicas, regions và HTTP keep-alive.
8. Xử lý **requests đang chạy, queues, retries, asynchronous workers, webhooks và transactions** sau revoke.
9. Viết Java 17 mô hình policy/revocation gate, fake stores và JUnit 5 negative/boundary tests.
10. Đánh giá logs/metrics, runbook, failure injection và test matrix cho multi-tenant isolation.

## 2. Tenant, client, credential và grant là bốn lớp khác nhau

Một API có nhiều tenant có thể phục vụ:

~~~text
Tenant A ── Client A-app ── Key A3 ── HMAC secret KA3
         └─ Client A-job ── Key A4 ── HMAC secret KA4

Tenant B ── Client B-app ── Key B1 ── HMAC secret KB1

Service partner P ── Key P7 ── principal partner-P
               ├─ grant: read Tenant A
               └─ grant: read Tenant B
~~~

Trong đó:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Tenant** | `tenant-A` | Phạm vi tổ chức/dữ liệu/quan hệ sử dụng dịch vụ |
| **Client** | `app-A` | Phần mềm/workload gửi request |
| **Key ID** | `client-a-k3` | Selector chưa đáng tin trong signed request |
| **Shared secret** | Key bytes của A3 | Đầu vào của HMAC |
| **Principal** | `client-a-service` | Identity từ credential record sau HMAC |
| **Grant** | P được `orders:read` trên A | Quyền do trusted policy cấp |
| **Tenant status** | ACTIVE/SUSPENDED/REVOKED | Trạng thái của tenant, độc lập với key |
| **Key status** | ACTIVE/RETIRING/REVOKED | Vòng đời riêng của credential |
| **Target tenant** | `tenant-A` trong route | Tenant mà request muốn truy cập |
| **Operation ID** | `order-create-O42` | Dùng cho business idempotency |

### 2.1. Thu hồi một key không đồng nghĩa thu hồi tenant

Khi `client-a-k3` bị compromise, có thể phải revoke **riêng k3** và cấp k4 cho A. Nếu tenant A vẫn ACTIVE, các credentials khác của A có thể tiếp tục theo policy.

Ngược lại, nếu **tenant A bị revoke**, mọi key hoặc principal còn có quyền chỉ nhờ quan hệ với A **không được sử dụng để thao tác trên A**, dù một số keys vẫn ACTIVE để phục vụ tenant B hoặc route quản trị được cho phép.

### 2.2. Thu hồi grant không đồng nghĩa thu hồi tenant

Partner P có thể được cấp quyền đọc A và B. Khi tenant A **thu hồi quyền của P**, grant `P→A` bị revoke nhưng tenant A vẫn ACTIVE; P vẫn có thể truy cập B nếu còn grant hợp lệ.

Ví dụ:

~~~text
Tenant A: ACTIVE
Tenant B: ACTIVE
Principal P: HMAC credential P7 ACTIVE
Grant P -> Tenant A: REVOKED
Grant P -> Tenant B: ACTIVE

Request P on A -> DENY
Request P on B -> MAY ALLOW, if action/resource policy matches
~~~

Dễ mắc lỗi khi dùng một boolean `principalDisabled` toàn cục để xử lý việc thu hồi riêng A: nó có thể làm P mất quyền ở B, trái mục tiêu cô lập.

### 2.3. Thu hồi tenant không nhất thiết là xóa dữ liệu

`REVOKED` hoặc `SUSPENDED` thường là **trạng thái kiểm soát truy cập**. Nó không tự định nghĩa xóa dữ liệu, retention, export, backup purge hay nghĩa vụ pháp lý. Data lifecycle/offboarding là một workflow khác, có thể có mốc và approvals riêng. Một tenant bị revoke vẫn có thể cần lưu audit, cung cấp export có kiểm soát hoặc tiếp nhận yêu cầu pháp lý qua một **administrative capability tách biệt**.

## 3. Threat model: request hợp lệ nhưng tenant không còn được phép

Giả sử HMAC credential `client-a-k3` vẫn ACTIVE và client có secret KA3. Admin đã chuyển tenant A sang REVOKED lúc `T_revoke`.

Attacker hoặc client cũ vẫn có thể:

- Tạo timestamp hiện tại, nonce chưa dùng và full HMAC tag hợp lệ.
- Gọi endpoint trực tiếp hoặc qua gateway phụ.
- Dùng key khác cùng tenant, nếu policy chỉ revoke k3.
- Gửi requests ký trước revoke nhưng được **nhận sau** revoke.
- Gửi hàng loạt requests đang chạy trước thời điểm revoke.
- Đặt target tenant trong path/query/header/body khác nhau để khai thác parser mismatch.
- Dùng một principal có quyền trên tenant B để truy cập route tenant A.
- Gửi message vào queue/workflow trước revoke để worker xử lý sau revoke.

Mục tiêu bảo vệ:

1. **Không nhận thêm business operations trái chính sách sau thời điểm revocation có hiệu lực**.
2. Không dùng `X-Tenant-Id`, `X-Role` hoặc key ID prefix do client khai làm nguồn quyền.
3. HMAC verification và tenant policy phải dùng **cùng target resource semantics** được ứng dụng thực thi.
4. Quyền vào B phải không bị thay đổi một cách không chủ đích khi chỉ revoke A.
5. Trạng thái REVOKED phải được cưỡng chế trên mọi verifier/gateway/worker liên quan theo **consistency guarantee** công bố.
6. Không “hồi sinh” tenant từ stale cache, failover snapshot hoặc rollback status ngoài quy trình phê duyệt.
7. Duy trì điều tra/audit/operation status mà không để endpoint public của revoked tenant tiếp tục thao tác tự do.

### 3.1. HMAC hợp lệ không chứng minh tenant còn ACTIVE

~~~text
keyId       = client-a-k3 (ACTIVE)
secret      = KA3
signature   = HMAC(KA3, canonicalRequest) -> MATCH
timestamp   = fresh
nonce       = new
target      = tenant-A
tenantState = REVOKED

Authentication: cryptographic key possession verified
Tenant policy: DENY
Business handler: MUST NOT perform protected action
~~~

Một hệ thống bỏ qua `tenantState` vì MAC đã đúng đã nhầm **authentication** với **authorization/admission policy**.

### 3.2. Replay defense không giải quyết tenant revocation

Timestamp/nonce giúp phát hiện một signed request được gửi lại trái phép. Nhưng một client có secret hợp lệ vẫn có thể ký request **mới** với nonce mới sau lúc tenant bị khóa. Revocation không thể dựa vào “nonce đã dùng hay chưa”.

### 3.3. Signed timestamp trước revoke không phải quyền tiếp tục

Sai:

~~~text
if request.signedTimestamp < tenant.revokedAt:
    acceptEvenAfterTenantRevoke()
~~~

Client có secret có thể tự khai timestamp quá khứ (còn trong freshness window), sau đó ký MAC hợp lệ. `signedTimestamp` do client tạo là một **claim có integrity** theo secret; nó **không** phải một trusted receipt time chứng minh server đã nhận request trước revoke.

Với policy nghiêm, quyết định tenant authorization nên dựa vào **server-authoritative state tại admission/commit boundary**, không chỉ so timestamp do client tự ký với `revokedAt`.

## 4. Phạm vi và trạng thái revocation phải được định nghĩa rõ

Một mô hình trạng thái tenant minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> ACTIVE: activate
    ACTIVE --> SUSPENDED: reversible business/security hold
    SUSPENDED --> ACTIVE: authorized reactivation
    ACTIVE --> REVOKED: final access revocation
    SUSPENDED --> REVOKED: termination
    REVOKED --> DECOMMISSIONED: data offboarding workflow
    DECOMMISSIONED --> [*]
~~~

Đây không phải một state machine chuẩn bắt buộc. Trong nhiều hệ thống, **SUSPENDED** là trạng thái có thể khôi phục sau xác minh; **REVOKED** thể hiện quyết định chấm dứt/quyền truy cập lâu dài. Nếu tổ chức cần hỗ trợ re-onboard tenant sau revoke, nên tạo revision/identity lifecycle mới với approvals rõ, không âm thầm sửa cached REVOKED thành ACTIVE.

### 4.1. Các loại thu hồi khác nhau

| Sự kiện | Đối tượng bị thu hồi | Điều gì phải bị chặn? |
| --- | --- | --- |
| Compromised key | Một credential/key ID | Requests xác thực bằng key đó |
| Client suspension | Một client principal | Requests từ client trên các scope bị khóa |
| Tenant suspension | Một tenant | Các operations nằm trong policy suspend |
| **Tenant revocation** | Một tenant | Mọi operations vào tenant bị revoke, bất kể credential hợp lệ |
| Grant revocation | Principal P → Tenant A | P không còn thao tác trên A |
| Scope revocation | `orders:write` của principal | Thao tác write, còn read nếu policy cho |
| Service/audience revoke | Credential không còn dùng ở `payments-api` | Requests tới service không đúng audience |
| Data deletion | Dữ liệu tenant | Theo retention/offboarding, không tự suy từ access revoke |

### 4.2. Global tenant revoke và principal–tenant grant revoke

Một policy cần tách:

~~~text
tenantStatus(tenant-A) = REVOKED
   -> deny all normal user/workload operations on A

grantStatus(partner-P, tenant-A) = REVOKED
   -> deny P access to A, while A may remain ACTIVE

credentialStatus(client-A-k3) = REVOKED
   -> deny k3 authentication, irrespective of target tenant
~~~

Dùng đúng **policy dimension** thay vì một flag tổng quát `active` không rõ chủ thể.

### 4.3. Hành vi của các endpoint ngoại lệ

Một tenant REVOKED có thể vẫn cần một số **ngoại lệ hạn chế**, ví dụ health check hệ thống, đọc hóa đơn cuối cùng qua portal quản trị riêng, điều tra có ủy quyền hoặc xuất dữ liệu theo hợp đồng. Không nên cho bypass bằng cách “tenant revoked nhưng nếu header `X-Admin: true` thì allow”.

Nếu có ngoại lệ, hãy thiết kế **separate privileged principal, explicit action allowlist, additional approval/audit**, trusted administrative route và khả năng cưỡng chế độc lập. Bài này mặc định **deny tất cả normal tenant business operations** đối với REVOKED.

## 5. Trusted identity và tenant binding trong HTTP request

Một signed request:

~~~http
POST /v1/tenants/tenant-A/orders?dryRun=false HTTP/1.1
Host: orders.example.test
Content-Type: application/json
X-Key-Id: client-a-k3
X-Timestamp: 1800000030
X-Nonce: 0123456789abcdef0123456789abcdef
X-Signature: <43-char-base64url-hmac-sha256-tag>

{"orderId":"O42","amount":250000}
~~~

Verifier cần xác định:

- **Credential key ID** nào đang được yêu cầu dùng?
- **Principal** đáng tin là ai sau khi tag khớp?
- **Target tenant** nào mà router/handler thực sự sẽ thao tác?
- Key có đúng audience/algorithm/validity không?
- Principal có **grant/action/scope** trên tenant này không?
- Tenant status có đang ACTIVE và revision đáng tin không?
- Nonce đã được admit một lần dưới đúng namespace hay chưa?
- Nếu request dài/chạy async, state có cần được kiểm tại commit không?

### 5.1. Chỉ ký header tenant không đủ cấp quyền tenant

~~~http
X-Tenant-Id: tenant-A
X-Role: owner
~~~

Ngay cả khi client HMAC ký các header này, nó chỉ chứng minh **caller đã khai** tenant A/role owner. Quá trình xác minh HMAC không biến client claim thành server permission. Server phải đối chiếu trusted registry/grant store và resource thực tế.

### 5.2. Canonical path phải chứa tenant được nhắm đến

Nếu route có `/v1/tenants/{tenantId}/orders`, target tenant ID nằm trong path và path phải được HMAC ký **đúng biểu diễn thực thi**. Tránh một tầng xác minh path tenant A nhưng router xử lý tenant B vì decoding/rewrites khác nhau.

Nếu target tenant nằm trong body, ký raw body digest và handler phải dùng body đã được xác minh; không nhận untrusted `X-Target-Tenant` override path theo cách âm thầm.

### 5.3. Tenant ID trong request có thể khác tenant mặc định của principal

Một principal P có thể phục vụ tenant A và B qua grants. Vì thế không nên áp nguyên tắc đơn giản “tenant trong path luôn phải bằng tenant gắn với key”; cần kiểm chính sách:

~~~text
principal P
  allowedTenantGrants = {A:read, B:read}
  requestedTenant = B

if tenant B ACTIVE and grant P->B ACTIVE:
    MAY ALLOW read B
else:
    DENY
~~~

Trong ví dụ một client một tenant, có thể triển khai kiểm equality nhưng phải nói rõ đây là **policy đơn giản hóa**, không phải mô hình duy nhất của multi-tenant.

## 6. Hợp đồng canonical HMAC-HTTP-V1 cho Tenant revocation

Để thực hành, chọn một protocol minh họa cố định (**không phải RFC authentication chung**):

~~~text
HMAC-HTTP-V1
POST
/v1/tenants/tenant-A/orders
dryRun=false
audience:orders-api
host:orders.example.test
content-type:application/json
key-id:client-a-k3
timestamp:1800000030
nonce:0123456789abcdef0123456789abcdef
body-sha256:<lowercase-hex-of-actual-raw-body-digest>
~~~

Các dòng nối bằng LF, encode UTF-8, không thêm LF cuối. Trong contract này:

1. `method`, path, canonical query, host và content-type là các components được ký.
2. `key-id`, `timestamp`, `nonce` được ràng buộc vào signed bytes.
3. `audience:orders-api` là marker phù hợp với route/registry policy; không cho caller đổi tùy ý.
4. `body-sha256` do server tính lại từ raw body bytes thực nhận.
5. Signature là full HMAC-SHA256 32 bytes, encode Base64URL no padding 43 ký tự.
6. `X-Signature` là **tag đầu ra**, không đưa nguyên tag vào input HMAC tạo chính nó.
7. Tenant ID là một phần của **signed path**; verifier và router phải thống nhất chính xác target tenant.
8. Server không đưa `tenantStatus` vào canonical input do client gửi để làm authority; trạng thái tenant được tra **riêng** tại thời điểm policy decision.
9. Path/query percent encoding, duplicate keys, proxy rewrites và signed header whitespace phải có rules versioned, không “thử normalize nhiều kiểu đến khi MAC hợp lệ”.

### 6.1. Tenant revocation là state động, không phải signed claim

Điều này rất quan trọng:

~~~text
Client signs at T0:
    tenant=A, HMAC valid

Server revokes A at T1.

Client sends at T2>T1:
    same valid MAC or new MAC

Server tenant status at T2:
    REVOKED -> DENY.
~~~

Không thể dùng một field `tenant-status:active` được ký từ T0 để ghi đè trạng thái hiện tại. Chữ ký bảo vệ bytes đã khai; **quyết định cho phép cần sử dụng trusted state mới**.

### 6.2. Không ký một tenant khác với tenant được routing

Nếu header `X-Tenant-Id` khai tenant A trong khi path là tenant B, hãy quy định rõ nguồn tenant chuẩn và reject mismatch. Đừng chọn tenant từ header để verify nhưng chọn tenant từ path khi authorize hoặc xử lý business. **Sign what you execute**, rồi enforce policy trên chính resource/tenant đó.

## 7. Tenant policy gate trong pipeline HMAC

Với mỗi HTTP request, phải kiểm tra **ba tầng độc lập**: credential/key policy (key còn hợp lệ), tenant policy (tenant còn được hoạt động), authorization grants (principal có quyền trên resource/tenant không).

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Reject duplicate or malformed signed headers]
    B --> C[Exact key lookup and credential status]
    C --> D[Recreate canonical bytes and compare full HMAC]
    D --> E{HMAC valid?}
    E -- No --> X[Reject authentication]
    E -- Yes --> F[Check timestamp freshness]
    F --> G[Resolve signed target tenant from route]
    G --> H[Read tenant status and principal-tenant grants]
    H --> I{Tenant ACTIVE and grant permits action?}
    I -- No or unknown --> Y[Deny tenant admission]
    I -- Yes --> J[Atomic nonce claim in shared replay store]
    J --> K{Nonce NEW?}
    K -- No or uncertain --> X
    K -- Yes --> L[Business handler with trusted tenant context]
    L --> M[Commit-time policy recheck if contract requires]
    M --> N[Commit durable operation]
~~~

Một số hệ thống kiểm nonce trước tenant/grant, số khác kiểm tenant trước nonce để không tiêu thụ nonce của request đã bị denied. Bài này chọn **HMAC → freshness → tenant/grant → nonce → business**. Bất kể thứ tự, phải bảo đảm:

- MAC sai không được ghi nonce (chống replay-state poisoning).
- Tenant đã REVOKED không được thực thi protected business action dù tag đúng.
- Không tạo trusted principal dựa trên key ID trước khi MAC hợp lệ.
- Không tin client-signed tenant-status là policy hiện thời.
- Không dùng nonce `NEW` như bằng chứng tenant có quyền.
- Nếu nguồn tenant/grant state không tin cậy, **fail closed** cho các operations nhạy cảm.

### 7.1. Phân loại kết quả đúng lớp

| Tình huống | Lớp bị từ chối |
| --- | --- |
| Key ID không tồn tại hoặc revoked | Authentication/credential policy |
| Tag không khớp | Authentication |
| Timestamp stale hoặc nonce replay | Freshness/replay admission |
| HMAC đúng nhưng tenant REVOKED | Tenant policy / authorization |
| Tenant ACTIVE nhưng P→A grant bị revoke | Authorization |
| Tenant ACTIVE, grant đủ nhưng object thuộc tenant khác | Resource authorization |
| Tenant status store timeout, không xác minh được | Fail-closed policy uncertainty |

Ngoài API có thể trả lỗi chung nhằm tránh tiết lộ sự tồn tại của tenant hoặc credential; nội bộ phải có reason codes đủ phân biệt. HTTP status `401`/`403` hay một mã khác là lựa chọn contract, **không** thay yêu cầu deny đúng.

### 7.2. Không biến signed timestamp thành “giấy phép trước revoke”

Nếu request có timestamp được ký tại T0 và tenant bị revoke T1, việc request đến server ở T2 > T1 **không** mặc nhiên được cho qua. Caller có secret có thể tự đặt timestamp T0 trong khoảng freshness. Chỉ một trusted **server-side receipt/admission record** hoặc protocol riêng có thể chứng minh request đã được nhận trước revoke.

## 8. Thời điểm hiệu lực: admission và commit

Một câu hỏi quan trọng: “Admin revoke tenant thì request đang chạy có được commit không?” Phải công bố mức bảo đảm.

### 8.1. Admission-time guarantee

~~~text
T0 R passes ACTIVE check and is admitted
T1 Admin revokes tenant A
T2 R finishes its work
~~~

Nếu contract chỉ chặn **new admissions sau effective revoke**, R có thể hoàn tất. Không được gọi đó là “không side effect nào xảy ra sau revoke”.

### 8.2. Commit-time guarantee (mạnh hơn)

Nếu yêu cầu là **không commit nghiệp vụ sau revoke effective point**, business layer phải kiểm status tại commit trong một consistency boundary phù hợp:

~~~text
Business DB transaction:
  lock tenant_policy row of A
  assert status ACTIVE and expected policy epoch
  check authorization for action/resource
  commit tenant-owned writes while lock/transaction covers check

Admin revoke transaction:
  lock same tenant_policy row of A
  write REVOKED and increment policy epoch
  commit
~~~

Một DB hỗ trợ transactions/locks đúng semantics có thể sắp thứ tự revoke và write. Nếu side effects ở DB khác hoặc external payment processor, chỉ kiểm tenant row trong một DB **không tạo atomicity đa hệ thống**. Khi đó cần fencing/outbox/idempotent workflow/compensation và mô tả limitation rõ.

### 8.3. Policy epoch giúp ngăn quyền đã cũ

~~~text
Tenant A: ACTIVE epoch=17
Request R admitted at epoch=17

Revoke A:
  REVOKED epoch=18

Worker wants to commit R:
  current epoch=18; expected epoch=17 -> ABORT
~~~

Epoch phải lấy từ trusted server policy, không từ header caller khai. Nếu kiểm epoch rồi commit ở hai bước không nguyên tử vẫn có **time-of-check/time-of-use race**. Epoch chỉ có giá trị fencing khi storage/handler thực thi nó đúng boundary.

### 8.4. Không thể thu hồi side effects trong quá khứ

Revoke không đảo ngược transactions đã commit. Muốn hủy order hoặc hoàn tiền, cần compensation nghiệp vụ theo policy. Trong incident response, phải xác định rõ: requests accepted trước revoke, operations in-flight, commits sau revoke, pending queues, external calls và notifications.

### 8.5. Biên policy và đồng hồ

`revokedAt` nên do trusted server/control plane xác định, lưu bằng thời gian UTC đáng tin để audit. Nhưng **timestamp không thay transaction ordering**: nếu hai nodes có clock lệch, dùng client/server timestamp string để “phân xử ai trước” có thể không đủ. Hãy dựa vào durable state transition/epoch/commit ordering của authority theo guarantee đã chọn.

## 9. Consistency và cache invalidation trên cluster

Tenant status có thể được cache trong gateway, verifier, authorization service, các workers và replicas:

~~~mermaid
flowchart LR
    R[Admin revokes Tenant A] --> P[Authoritative tenant policy store]
    P --> G1[Gateway G1 cache]
    P --> G2[Gateway G2 cache]
    P --> V1[Verifier V1]
    P --> V2[Verifier V2]
    V1 --> B1[Business node 1]
    V2 --> B2[Business node 2]
~~~

Nếu G1 nhìn `REVOKED` nhưng V2 vẫn dùng `ACTIVE` từ cache cũ, request qua đường phụ có thể bị chấp nhận. **Một bản ghi REVOKED trong database không chứng minh toàn hệ thống đã ngừng cho tenant truy cập.**

### 9.1. Race: stale ACTIVE đè REVOKED

~~~text
T0 Loader A fetches ACTIVE tenant-A revision 17
T1 Admin revokes A -> REVOKED revision 18
T2 Loader B caches REVOKED revision 18
T3 Loader A completes late and overwrites cache with ACTIVE revision 17
T4 A new request passes stale ACTIVE check
~~~

Cần revision/epoch monotonic, event/version fencing, cache invalidation và audit change. Không cho revision 17 overwrite 18. Nhưng version fencing cục bộ **không tự giải quyết node bị partition chưa từng thấy revision mới**.

### 9.2. Các mô hình và giới hạn

| Giải pháp | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Local cache TTL | Latency thấp | Revocation lag; stale ACCEPT có thể xảy ra |
| Push invalidation với version | Truyền state nhanh | Lost event/network partition cần fallback |
| On-request authoritative lookup | Status gần hiện tại, audit rõ | Tăng latency và phụ thuộc availability |
| Emergency denylist | Chặn một tenant tức thời trên các node nhận lệnh | Phải bảo đảm truyền tới mọi admission path |
| Strong consistency tenant authority | Decision ordering rõ | Tradeoff latency/availability |
| Transactional commit-time check | Bảo vệ ghi trong cùng commit boundary | Không tự bảo vệ external distributed side effects |
| Eventual multi-region replicas | Locality/throughput | Không mặc nhiên bảo đảm global immediate revoke |

### 9.3. Fail-closed khi trạng thái không chắc chắn

Một policy nghiêm không cho phép node bị partition nhận requests vô hạn nhờ stale `ACTIVE`. Cần xác định cache lease/maximum staleness, effective revoke deadline, quyền sở hữu vùng, fallback khi policy authority unavailable, và cơ chế tạm chặn tenant/route nếu không xác minh được current state.

Nếu chọn mô hình eventual consistency, phải ghi rõ **khoảng cửa sổ rủi ro**, không công bố “revoke toàn hệ thống tức thời” khi chưa được bảo đảm. Với API thanh toán hoặc quản trị, có thể cần strong authority hoặc commit-time recheck.

### 9.4. Tenant state và replay state khác nhau

Replay store atomically claim nonce; nó **không biết** tenant có còn ACTIVE hay không. Tenant policy store biết A REVOKED nhưng không biết nonce N đã được dùng. Cả hai phải hoạt động đúng và được test độc lập.

## 10. Delegated principals, grants và tenant hierarchy

Một principal có thể sở hữu một key nhưng có nhiều grants theo tenant. Quyết định cho phép có dạng:

\[
\operatorname{allow}=
\operatorname{credentialValid}
\land\operatorname{tenantActive}
\land\operatorname{grantActive}
\land\operatorname{actionAuthorized}
\land\operatorname{resourceAuthorized}
\]

Trong đó HMAC, freshness và replay vẫn có các gates riêng.

### 10.1. Global tenant revocation

Nếu tenant A REVOKED:

~~~text
Client A-app with key A3 -> DENY normal operations on A
Partner P with key P7, grant P->A -> DENY on A
Tenant B unrelated -> still ACTIVE
Partner P with grant P->B -> MAY continue B
~~~

Grant vào A không override tenant global REVOKED.

### 10.2. Revoke riêng principal–tenant grant

~~~text
Tenant A = ACTIVE
Tenant B = ACTIVE
Principal P key P7 = ACTIVE
Grant P -> A = REVOKED
Grant P -> B = ACTIVE

P requests A -> DENY
P requests B -> MAY ALLOW if resource/action matches
Client A's own request -> MAY ALLOW if all policies pass
~~~

Nếu application dùng boolean `principalHasAnyGrant` rồi cho P truy cập A vì P vẫn có grant B, nó đã làm sai **tenant isolation**.

### 10.3. Parent/child tenant inheritance

Một hệ thống có organization → workspace → project:

~~~text
Org A: REVOKED
   Workspace A1: ACTIVE
      Project A1P: ACTIVE
~~~

Nếu policy quy định **inherited deny**, project A1P vẫn phải bị chặn dù trạng thái leaf là ACTIVE. Phải test tenant moves, inherited grants, stale ancestor cache, tenant hierarchy version và partial delegation.

### 10.4. Shared resources

Nếu một document/order được chia sẻ giữa A và B, việc revoke A không nhất thiết xóa quyền hợp pháp của B, nhưng mọi quyền phát sinh từ A phải được xem xét. Ownership và cross-tenant sharing là domain policy, không suy từ key ID prefix hay client-supplied header.

## 11. Queued jobs, async workers và long-lived connections

**HTTP 202 Accepted không có nghĩa business operation đã commit.** Tenant có thể bị revoke giữa lúc request đi vào queue và worker thực thi:

~~~mermaid
sequenceDiagram
    participant C as Client A
    participant API as HMAC API
    participant Q as Durable Queue
    participant T as Tenant Policy
    participant W as Worker
    participant DB as Business DB

    C->>API: POST /tenant-A/jobs with valid HMAC
    API->>T: Read tenant A ACTIVE epoch=17
    API->>Q: Enqueue trusted tenant+principal+epoch
    API-->>C: 202 Accepted
    T->>T: Revoke A epoch=18
    Q->>W: Deliver pending job
    W->>T: Recheck tenant status and epoch
    T-->>W: REVOKED epoch=18
    W->>Q: Cancel or defer by explicit policy
    W--xDB: Do not create unauthorized side effect
~~~

### 11.1. Trusted context trong queue

Một job có thể lưu:

~~~text
operationId
targetTenantId from verified resource
trustedPrincipalId from authenticated credential
authorizedAction
policyEpochAtAdmission
correlationId
validatedPayloadReference
~~~

Thông tin này phải có integrity và provenance được bảo vệ giữa API/queue/worker. Không dùng chỉ một `X-Tenant-Id` hoặc `X-Role` do caller khai để worker tái cấp quyền, và không coi HMAC tag của request lúc enqueue là **quyền vĩnh viễn**.

### 11.2. Revalidate trước side effect

Worker cần đánh giá tenant ACTIVE không, grant/action còn hiệu lực không, epoch có đổi không, status/credential phụ thuộc có bị revoke không và có cần transaction commit check không.

Không phải mọi job bị revoke đều phải xóa: một số compensation/administrative workflows vẫn cần chạy. Nhưng đây phải là **ngoại lệ có policy/approval/audit rõ ràng**.

### 11.3. Retries, streams và issued tokens

Một job thất bại rồi retry sau vài phút có thể gặp tenant REVOKED. Tương tự WebSocket, HTTP/2 streaming, SSE, long-polling, session đã xác thực trước revoke có thể còn mở. Phải định nghĩa close/reauthorize/invalidate subscriptions theo policy.

Nếu HMAC request trước revoke phát sinh bearer token/session, **thu hồi tenant không tự động vô hiệu hóa những thứ đó** nếu downstream chỉ kiểm token signature mà không đánh giá tenant status. Cần tenant-aware validation/session revocation hoặc policy epoch checks tại từng protected action.

## 12. Nonce, tenant scope và business idempotency

Một replay key theo **credential scope**:

~~~text
hmac-replay:v1:orders-api:client-a-k3:0123456789abcdef0123456789abcdef
~~~

Nó gồm version, trusted audience, exact signed key ID và signed nonce; không dựa vào `X-Tenant-Id` do client tự khai làm namespace.

### 12.1. Tenant revoked không được “cứu” bởi nonce NEW

Attacker có secret A3 có thể tạo timestamp fresh, nonce N2 mới; nonce store trả `NEW` nhưng tenant A REVOKED nên request **vẫn bị từ chối**. Ngược lại, tenant ACTIVE không làm một nonce replay trở nên hợp lệ.

### 12.2. Same nonce across tenants

Theo contract nonce unique **theo key ID**, cùng text nonce N của key A3 và key B1 có thể được claim độc lập lần đầu. Nếu một principal dùng một credential cho cả A và B, nonce được bảo vệ theo **credential**, không cho lặp N ở tenant B chỉ vì đổi tenant path. Muốn nonce per-tenant phải thiết kế một contract khác và bảo vệ signed target tenant.

### 12.3. TTL phù hợp với freshness

Với max past age `A`, future skew `F` và safety margin `M`, một bound bảo thủ khi TTL tính từ lúc claim:

\[
TTL_{\mathrm{nonce}} \ge A+F+M
\]

Ví dụ A=300s, F=30s, M=30s → TTL tối thiểu 360s. Không rút TTL quá ngắn để giảm bộ nhớ khi tenant tạm khóa; điều đó có thể mở replay gap nếu trạng thái tenant thay đổi.

### 12.4. Business idempotency có scope tenant đáng tin

Hai signed requests có nonce N1/N2 và cùng `orderId=O42` có thể qua replay. Business layer nên dùng durable idempotency key theo tenant/principal/operation, ví dụ:

~~~text
idempotencyKey = trustedTenantId + ":" + principalId + ":" + operationId
~~~

Không để key của tenant A va với B hoặc dùng arbitrary caller-supplied tenant header làm trusted scope. Idempotency không cho phép vượt tenant revocation; một operation chưa commit vẫn phải tuân policy hiệu lực tại commit theo hợp đồng đã chọn.

## 13. Java 17: tenant status, grants và policy authority

Để kiểm thử độc lập HMAC và tenant revocation, ta mô hình hóa **đúng hai nguồn trusted state riêng**:

- Credential registry xác định key ID → secret, principal, audience, key lifecycle.
- Tenant authority xác định tenant status/epoch và principal→tenant grants.

Các mẫu Java 17 sau dùng test data và đơn giản hóa storage. Mỗi public enum/record/class/interface nên được đặt trong file Java tương ứng khi tích hợp vào project; ví dụ không phải thư viện production đã qua QA chuyên môn.

### 13.1. Tenant status, snapshot và revision

~~~java
public enum TenantStatusV1 {
    PROVISIONING,
    ACTIVE,
    SUSPENDED,
    REVOKED,
    DECOMMISSIONED
}
~~~

~~~java
import java.time.Instant;
import java.util.Objects;

public record TenantSnapshotV1(
        String tenantId,
        TenantStatusV1 status,
        long epoch,
        Instant stateChangedAt) {

    public TenantSnapshotV1 {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(status);
        Objects.requireNonNull(stateChangedAt);

        if (tenantId.isBlank() || epoch < 0L) {
            throw new IllegalArgumentException("Invalid tenant state");
        }
    }
}
~~~

`epoch` là revision do **trusted tenant authority** tăng lên khi policy thay đổi. Không chấp nhận request header `X-Tenant-Epoch` như nguồn quyết định epoch hiện tại. Một trạng thái REVOKED thường cần được bảo vệ như **terminal/monotonic deny** theo policy, không âm thầm nhận snapshot ACTIVE cũ có revision thấp hơn.

### 13.2. Grant theo exact principal + tenant

~~~java
import java.util.Objects;
import java.util.Set;

public record TenantGrantV1(
        String principalId,
        String tenantId,
        Set<String> actions,
        boolean active,
        long revision) {

    public TenantGrantV1 {
        Objects.requireNonNull(principalId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(actions);

        if (revision < 0L) {
            throw new IllegalArgumentException("Invalid revision");
        }
        actions = Set.copyOf(actions);
    }
}
~~~

Một grant P→A đã REVOKED không có nghĩa P→B cũng bị thu hồi. `actions` là trusted server-side permissions, không lấy từ `X-Scopes` do client tự khai.

### 13.3. Authority interface và lỗi kết quả không chắc chắn

~~~java
import java.util.Optional;

public interface TenantAuthorityV1 {
    /**
     * Empty chỉ khi một authoritative lookup xác nhận tenant absent.
     * Timeout/partition phải throw, không đổi thành empty/ACTIVE.
     */
    Optional<TenantSnapshotV1> findTenantExact(String tenantId);

    /**
     * Exact principal + tenant grant, không lấy wildcard/any-grant.
     */
    Optional<TenantGrantV1> findGrantExact(
            String principalId, String tenantId);
}
~~~

~~~java
public final class TenantAuthorityUnavailableV1
        extends RuntimeException {
    public TenantAuthorityUnavailableV1(String message) {
        super(message);
    }
}
~~~

Trong production, trạng thái global tenant và grant có thể nằm ở hai stores. Khi load chúng riêng rẽ, cần chính sách consistency/snapshot/epoch để không tạo một quyết định ALLOW từ tổ hợp data cũ mới không hợp lệ. Test helper trong một JVM **không chứng minh** distributed authorization consistent.

### 13.4. Trusted principal sau HMAC

~~~java
public record VerifiedHmacPrincipalV1(
        String principalId,
        String credentialKeyId,
        String credentialAudience) {}
~~~

Đây là một value type cho **trusted internal context**, chỉ được tạo bởi HMAC verifier sau khi tag/full credentials và freshness hợp lệ. Không map trực tiếp từ JSON, HTTP headers, RPC không được xác thực hoặc queue message do client kiểm soát vào record này rồi dùng để vượt qua verifier.

Production có thể làm constructor package-private, dùng sealed/opaque security context, bảo vệ internal RPC hoặc cấp trusted assertion có integrity để ngăn caller tự dựng identity.

### 13.5. Kết quả policy không là HMAC result

~~~java
public enum TenantPolicyOutcomeV1 {
    ALLOW,
    TENANT_NOT_FOUND,
    TENANT_SUSPENDED,
    TENANT_REVOKED,
    TENANT_NOT_ACTIVE,
    GRANT_NOT_FOUND,
    GRANT_NOT_ALLOWED,
    AUTHORITY_UNAVAILABLE
}
~~~

~~~java
public record TenantPolicyDecisionV1(
        TenantPolicyOutcomeV1 outcome,
        String trustedTenantId,
        long allowedEpoch) {

    public boolean allowed() {
        return outcome == TenantPolicyOutcomeV1.ALLOW;
    }

    public static TenantPolicyDecisionV1 deny(
            TenantPolicyOutcomeV1 outcome) {
        return new TenantPolicyDecisionV1(outcome, null, -1L);
    }
}
~~~

Trường `allowedEpoch` của kết quả ALLOW là **trusted epoch** cần mang tới business commit fence khi contract đòi hỏi. Một response deny không được cho business lấy epoch/tenant context để tiếp tục thực thi.

## 14. Java 17: tenant gate chỉ đánh giá trusted identity

### 14.1. Parser exact target tenant từ signed route

Hợp đồng V1 minh họa chỉ nhận path:

~~~text
/v1/tenants/<tenantId>/orders
tenantId grammar: [A-Za-z0-9_-]{1,64}
~~~

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class TenantRouteV1 {
    private static final Pattern PATH = Pattern.compile(
            "/v1/tenants/([A-Za-z0-9_-]{1,64})/orders");

    private TenantRouteV1() {}

    public static String targetTenantId(String rawPath) {
        if (rawPath == null) {
            throw new IllegalArgumentException("Missing route");
        }

        Matcher matcher = PATH.matcher(rawPath);
        if (!matcher.matches()) {
            // Reject encoded slashes/dot segments/ambiguous paths.
            throw new IllegalArgumentException("Invalid tenant route");
        }
        return matcher.group(1);
    }
}
~~~

Đây là **demo contract chặt**, không hỗ trợ mọi URI/percent-encoding hợp lệ. Production cần một canonicalization spec đầy đủ và thống nhất với router/gateway. Không áp luật V1 lên endpoints khác rồi coi đó là HTTP chuẩn chung.

### 14.2. TenantPolicyGateV1

~~~java
import java.util.Objects;
import java.util.Optional;

public final class TenantPolicyGateV1 {
    private final TenantAuthorityV1 authority;

    public TenantPolicyGateV1(TenantAuthorityV1 authority) {
        this.authority = Objects.requireNonNull(authority);
    }

    /**
     * PRECONDITION:
     * - principal được tạo bởi trusted HMAC verification layer.
     * - rawPath là signed route mà handler thực sự xử lý.
     * - action đến từ server-side route mapping, không do caller tự cấp.
     */
    public TenantPolicyDecisionV1 evaluate(
            VerifiedHmacPrincipalV1 principal,
            String rawPath,
            String requiredAction) {

        if (principal == null || requiredAction == null) {
            return TenantPolicyDecisionV1.deny(
                    TenantPolicyOutcomeV1.GRANT_NOT_ALLOWED);
        }

        final String targetTenant;
        try {
            targetTenant = TenantRouteV1.targetTenantId(rawPath);
        } catch (IllegalArgumentException badRoute) {
            return TenantPolicyDecisionV1.deny(
                    TenantPolicyOutcomeV1.TENANT_NOT_FOUND);
        }

        final Optional<TenantSnapshotV1> tenant;
        try {
            tenant = authority.findTenantExact(targetTenant);
        } catch (TenantAuthorityUnavailableV1 unavailable) {
            return TenantPolicyDecisionV1.deny(
                    TenantPolicyOutcomeV1.AUTHORITY_UNAVAILABLE);
        }

        if (tenant.isEmpty()) {
            return TenantPolicyDecisionV1.deny(
                    TenantPolicyOutcomeV1.TENANT_NOT_FOUND);
        }

        TenantSnapshotV1 snapshot = tenant.get();
        if (!snapshot.tenantId().equals(targetTenant)) {
            // Defend against an incorrect/aliasing registry adapter.
            return TenantPolicyDecisionV1.deny(
                    TenantPolicyOutcomeV1.AUTHORITY_UNAVAILABLE);
        }

        switch (snapshot.status()) {
            case REVOKED, DECOMMISSIONED -> {
                return TenantPolicyDecisionV1.deny(
                        TenantPolicyOutcomeV1.TENANT_REVOKED);
            }
            case SUSPENDED -> {
                return TenantPolicyDecisionV1.deny(
                        TenantPolicyOutcomeV1.TENANT_SUSPENDED);
            }
            case PROVISIONING -> {
                return TenantPolicyDecisionV1.deny(
                        TenantPolicyOutcomeV1.TENANT_NOT_ACTIVE);
            }
            case ACTIVE -> {
                // Continue to exact principal-tenant grant.
            }
        }

        final Optional<TenantGrantV1> foundGrant;
        try {
            foundGrant = authority.findGrantExact(
                    principal.principalId(), targetTenant);
        } catch (TenantAuthorityUnavailableV1 unavailable) {
            return TenantPolicyDecisionV1.deny(
                    TenantPolicyOutcomeV1.AUTHORITY_UNAVAILABLE);
        }

        if (foundGrant.isEmpty()) {
            return TenantPolicyDecisionV1.deny(
                    TenantPolicyOutcomeV1.GRANT_NOT_FOUND);
        }

        TenantGrantV1 grant = foundGrant.get();
        if (!grant.principalId().equals(principal.principalId())
                || !grant.tenantId().equals(targetTenant)
                || !grant.active()
                || !grant.actions().contains(requiredAction)) {
            return TenantPolicyDecisionV1.deny(
                    TenantPolicyOutcomeV1.GRANT_NOT_ALLOWED);
        }

        return new TenantPolicyDecisionV1(
                TenantPolicyOutcomeV1.ALLOW,
                targetTenant,
                snapshot.epoch());
    }
}
~~~

### 14.3. Tính chất của tenant gate

- Global tenant REVOKED **thắng** mọi grant đã cấp vào tenant đó.
- P→A không còn ACTIVE thì P không thể vào A dù P→B vẫn có quyền.
- Key credential không được dùng để suy trạng thái tenant; tenant authority là nguồn riêng.
- `targetTenant` được parse từ **signed route thực sự**.
- Authority trả record không khớp exact ID bị coi là lỗi đáng tin, không âm thầm accept.
- Authority timeout không mặc định tenant ACTIVE.
- Kết quả ALLOW chứa policy epoch, **chưa chứng minh side effect sẽ an toàn nếu sau đó policy đổi**.

### 14.4. Một ví dụ dùng đúng thứ tự

~~~java
// 1) Upstream: strict HTTP parsing, key lookup, MAC verification,
//    timestamp validation have ALL succeeded.
// 2) Only trusted verifier creates this principal.
VerifiedHmacPrincipalV1 principal =
        new VerifiedHmacPrincipalV1(
                "partner-P", "partner-p-k7", "orders-api");

// 3) Tenant policy is independent from HMAC success.
TenantPolicyDecisionV1 decision = tenantGate.evaluate(
        principal, "/v1/tenants/tenant-A/orders", "orders:create");

if (!decision.allowed()) {
    // Deny. Do not invoke business handler.
}

// 4) Next: atomic nonce claim; then handler authorization and
//    optional commit-time tenant epoch fencing.
~~~

Mẫu trên mô tả trusted internal code path; **không** chấp nhận client gửi serialized `VerifiedHmacPrincipalV1` để đi thẳng tới `tenantGate`.

### 14.5. Điều gì còn thiếu trong ví dụ?

- Chưa thực hiện HMAC primitive, strict Base64URL tag decode và canonicalizer ở chính class `TenantPolicyGateV1`; đó là **precondition của verifier trước gate**.
- Chưa làm timestamp freshness hoặc replay claim; phải có middleware riêng.
- Chưa kiểm cụ thể object owner, hierarchy, security groups và delegated scopes ngoài `requiredAction`.
- Chưa có cross-store atomic snapshot cho tenant/grant và business writes.
- Chưa có mTLS/trusted context transport từ gateway.
- Chưa có authorization exception dành riêng cho privileged offboarding endpoints.

Ví dụ cố tình tách các trách nhiệm để không nhầm **policy decision** thành HMAC authentication.

## 15. Java 17: HMAC verifier phải binding tenant route

Để tenant gate có ý nghĩa, HMAC phải ký đúng route mà tenant gate sử dụng.

### 15.1. Canonical bytes minh họa

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Pattern;

public final class TenantHmacCanonicalV1 {
    private static final Pattern KEY =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");
    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");

    private TenantHmacCanonicalV1() {}

    public static byte[] bytes(
            String method, String rawPath, String rawQuery,
            String host, String contentType, byte[] rawBody,
            String keyId, long timestampSeconds, String nonceHex)
            throws NoSuchAlgorithmException {

        // Validate before creating a canonical representation.
        TenantRouteV1.targetTenantId(rawPath);
        if (!"POST".equals(method)
                || !("dryRun=false".equals(rawQuery)
                     || "dryRun=true".equals(rawQuery)
                     || rawQuery == null)
                || !"orders.example.test".equals(host)
                || !"application/json".equals(contentType)
                || keyId == null || !KEY.matcher(keyId).matches()
                || nonceHex == null
                || !NONCE.matcher(nonceHex).matches()
                || timestampSeconds < 0
                || rawBody == null
                || rawBody.length > 1_048_576) {
            throw new IllegalArgumentException("Invalid canonical input");
        }

        String digest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(rawBody));

        String canonical = String.join("\n",
                "HMAC-HTTP-V1",
                method,
                rawPath,
                rawQuery == null ? "" : rawQuery,
                "audience:orders-api",
                "host:" + host,
                "content-type:" + contentType,
                "key-id:" + keyId,
                "timestamp:" + timestampSeconds,
                "nonce:" + nonceHex,
                "body-sha256:" + digest);

        return canonical.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Cùng V1 contract dùng cho signer/verifier. `rawPath` là signed route được tenant gate và business handler hiểu giống nhau. Không dùng raw body digest do caller cung cấp thay digest server tự tính.

### 15.2. Full HMAC-SHA256 tag comparison

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSha256V1 {
    private HmacSha256V1() {}

    public static byte[] tag(byte[] trustedSecret, byte[] canonical)
            throws GeneralSecurityException {

        if (trustedSecret == null || trustedSecret.length == 0
                || canonical == null) {
            throw new IllegalArgumentException("Invalid HMAC input");
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(trustedSecret, "HmacSHA256"));
        return mac.doFinal(canonical);
    }

    public static boolean sameTag(
            byte[] expected32, byte[] presented32) {

        return expected32 != null && expected32.length == 32
                && presented32 != null && presented32.length == 32
                && MessageDigest.isEqual(expected32, presented32);
    }
}
~~~

Server phải lookup **một exact key record**, validate lifecycle/audience/algorithm, strict decode full Base64URL tag 32 bytes, xây canonical bytes từ request đã được parse đúng boundary rồi so expected/presented. Không thử toàn bộ secrets khi mismatch, không cho client chọn `algorithm=none`, không tạo principal trước MAC.

### 15.3. Một end-to-end chain không được đảo

~~~text
Client signed request
  -> edge strict header/URI parsing
  -> exact key lookup + credential policy
  -> server canonical bytes include signed tenant path
  -> HMAC tag verify
  -> timestamp freshness
  -> trusted principal from key record
  -> tenant/grant policy gate
  -> atomic nonce admission
  -> business handler and object-level authorization
  -> commit-time tenant epoch check when required
~~~

Nếu backend lỡ dùng route khác sau HMAC (ví dụ gateway strip prefix không được contract ký), tenant gate có thể kiểm A trong khi handler thao tác B. Đó là **routing/canonicalization mismatch**, phải reject/test qua gateway thay vì “tự sửa” path cho MAC khớp.

## 16. JUnit 5: test tenant revoke, cross-tenant grants và fail-closed

Các ví dụ dùng **Java 17 + JUnit Jupiter**, cùng các kiểu ở mục 13–15. Mỗi public class/enum/record nên đặt trong file Java riêng nếu chạy thực tế. Chúng là tài liệu thực hành, **không phải bằng chứng STEP 4 đã chạy build/tests**.

### 16.1. Fake trusted tenant authority

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class FakeTenantAuthorityV1
        implements TenantAuthorityV1 {

    private final Map<String, TenantSnapshotV1> tenants =
            new ConcurrentHashMap<>();

    private final Map<String, TenantGrantV1> grants =
            new ConcurrentHashMap<>();

    private volatile boolean unavailable;

    public void putTenant(TenantSnapshotV1 tenant) {
        tenants.put(tenant.tenantId(), tenant);
    }

    public void putGrant(TenantGrantV1 grant) {
        grants.put(key(grant.principalId(), grant.tenantId()), grant);
    }

    public void setUnavailable(boolean state) {
        unavailable = state;
    }

    private static String key(String principal, String tenant) {
        // Only trusted test fixtures; production should use a
        // structured unique key / database composite key.
        return principal + "|" + tenant;
    }

    @Override
    public Optional<TenantSnapshotV1> findTenantExact(String tenantId) {
        if (unavailable) {
            throw new TenantAuthorityUnavailableV1(
                    "Test tenant store unavailable");
        }
        return Optional.ofNullable(tenants.get(tenantId));
    }

    @Override
    public Optional<TenantGrantV1> findGrantExact(
            String principalId, String tenantId) {
        if (unavailable) {
            throw new TenantAuthorityUnavailableV1(
                    "Test grant store unavailable");
        }
        return Optional.ofNullable(
                grants.get(key(principalId, tenantId)));
    }
}
~~~

Fake `ConcurrentHashMap` này **không** mô phỏng replication, transaction isolation, hierarchy hay distributed cache. Nó chỉ giúp kiểm các nhánh quyết định policy trên dữ liệu đã được cấp phép.

### 16.2. Bộ tests chính

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public final class TenantPolicyGateV1Test {
    private static final Instant NOW =
            Instant.parse("2026-06-15T12:00:00Z");

    private FakeTenantAuthorityV1 store;
    private TenantPolicyGateV1 gate;

    private final VerifiedHmacPrincipalV1 partnerP =
            new VerifiedHmacPrincipalV1(
                    "partner-P", "partner-p-k7", "orders-api");

    private final VerifiedHmacPrincipalV1 clientA =
            new VerifiedHmacPrincipalV1(
                    "client-A", "client-a-k3", "orders-api");

    private static String path(String tenant) {
        return "/v1/tenants/" + tenant + "/orders";
    }

    private static TenantSnapshotV1 tenant(
            String id, TenantStatusV1 status, long epoch) {
        return new TenantSnapshotV1(
                id, status, epoch, NOW);
    }

    private static TenantGrantV1 grant(
            String principal, String tenant,
            boolean active, String... actions) {

        return new TenantGrantV1(
                principal, tenant, Set.of(actions), active, 5L);
    }

    @BeforeEach
    void setup() {
        store = new FakeTenantAuthorityV1();
        store.putTenant(tenant(
                "tenant-A", TenantStatusV1.ACTIVE, 17));
        store.putTenant(tenant(
                "tenant-B", TenantStatusV1.ACTIVE, 4));

        store.putGrant(grant(
                "partner-P", "tenant-A", true, "orders:create"));
        store.putGrant(grant(
                "partner-P", "tenant-B", true, "orders:create"));
        store.putGrant(grant(
                "client-A", "tenant-A", true, "orders:create"));

        gate = new TenantPolicyGateV1(store);
    }

    @Test
    void validPrincipalAndActiveTenantAreAllowed() {
        var result = gate.evaluate(
                clientA, path("tenant-A"), "orders:create");
        assertTrue(result.allowed());
        assertEquals("tenant-A", result.trustedTenantId());
        assertEquals(17L, result.allowedEpoch());
    }

    @Test
    void globalTenantRevokeDeniesOwnClientAndPartner() {
        store.putTenant(tenant(
                "tenant-A", TenantStatusV1.REVOKED, 18));

        var own = gate.evaluate(
                clientA, path("tenant-A"), "orders:create");
        var partner = gate.evaluate(
                partnerP, path("tenant-A"), "orders:create");

        assertEquals(TenantPolicyOutcomeV1.TENANT_REVOKED,
                own.outcome());
        assertEquals(TenantPolicyOutcomeV1.TENANT_REVOKED,
                partner.outcome());
        assertFalse(own.allowed());
        assertNull(own.trustedTenantId());
    }

    @Test
    void revokingTenantADoesNotRevokeTenantB() {
        store.putTenant(tenant(
                "tenant-A", TenantStatusV1.REVOKED, 18));

        assertEquals(TenantPolicyOutcomeV1.ALLOW,
                gate.evaluate(partnerP,
                        path("tenant-B"), "orders:create").outcome());
    }

    @Test
    void revokingGrantPToADoesNotRevokePToB() {
        store.putGrant(grant(
                "partner-P", "tenant-A", false, "orders:create"));

        assertEquals(TenantPolicyOutcomeV1.GRANT_NOT_ALLOWED,
                gate.evaluate(partnerP,
                        path("tenant-A"), "orders:create").outcome());

        assertEquals(TenantPolicyOutcomeV1.ALLOW,
                gate.evaluate(partnerP,
                        path("tenant-B"), "orders:create").outcome());

        assertEquals(TenantPolicyOutcomeV1.ALLOW,
                gate.evaluate(clientA,
                        path("tenant-A"), "orders:create").outcome());
    }

    @Test
    void authenticatedPrincipalWithoutGrantCannotAccess() {
        var stranger = new VerifiedHmacPrincipalV1(
                "client-C", "client-c-k1", "orders-api");

        assertEquals(TenantPolicyOutcomeV1.GRANT_NOT_FOUND,
                gate.evaluate(stranger,
                        path("tenant-A"), "orders:create").outcome());
    }

    @Test
    void wrongActionIsRejectedDespiteExistingGrant() {
        assertEquals(TenantPolicyOutcomeV1.GRANT_NOT_ALLOWED,
                gate.evaluate(clientA,
                        path("tenant-A"), "orders:delete").outcome());
    }

    @Test
    void suspendedAndProvisioningAreNotActive() {
        store.putTenant(tenant(
                "tenant-A", TenantStatusV1.SUSPENDED, 18));
        assertEquals(TenantPolicyOutcomeV1.TENANT_SUSPENDED,
                gate.evaluate(clientA,
                        path("tenant-A"), "orders:create").outcome());

        store.putTenant(tenant(
                "tenant-A", TenantStatusV1.PROVISIONING, 19));
        assertEquals(TenantPolicyOutcomeV1.TENANT_NOT_ACTIVE,
                gate.evaluate(clientA,
                        path("tenant-A"), "orders:create").outcome());
    }

    @Test
    void unknownTenantAndMalformedPathAreRejected() {
        assertEquals(TenantPolicyOutcomeV1.TENANT_NOT_FOUND,
                gate.evaluate(clientA,
                        path("tenant-Z"), "orders:create").outcome());

        assertEquals(TenantPolicyOutcomeV1.TENANT_NOT_FOUND,
                gate.evaluate(clientA,
                        "/v1/tenants/%2e%2e/orders",
                        "orders:create").outcome());
    }

    @Test
    void authorityUnavailableFailsClosed() {
        store.setUnavailable(true);

        var result = gate.evaluate(
                clientA, path("tenant-A"), "orders:create");

        assertEquals(TenantPolicyOutcomeV1.AUTHORITY_UNAVAILABLE,
                result.outcome());
        assertFalse(result.allowed());
    }
}
~~~

### 16.3. MAC hợp lệ nhưng tenant REVOKED

Một test cần chứng minh hai lớp **đưa ra kết quả khác nhau mà vẫn đúng**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;

public final class HmacVsTenantRevocationV1Test {
    @Test
    void validMacStillCannotAccessRevokedTenant()
            throws Exception {

        byte[] testSecret =
                "test-only-independent-hmac-secret-A"
                .getBytes(StandardCharsets.US_ASCII);

        byte[] body = "{\"orderId\":\"O42\"}"
                .getBytes(StandardCharsets.UTF_8);

        byte[] canonical = TenantHmacCanonicalV1.bytes(
                "POST",
                "/v1/tenants/tenant-A/orders",
                "dryRun=false",
                "orders.example.test",
                "application/json",
                body,
                "client-a-k3",
                1_800_000_030L,
                "0123456789abcdef0123456789abcdef");

        byte[] presented = HmacSha256V1.tag(
                testSecret, canonical);
        byte[] expected = HmacSha256V1.tag(
                testSecret, canonical);

        // HMAC primitive proves key possession over signed bytes.
        assertTrue(HmacSha256V1.sameTag(
                expected, presented));

        var store = new FakeTenantAuthorityV1();
        store.putTenant(new TenantSnapshotV1(
                "tenant-A", TenantStatusV1.REVOKED, 18L,
                Instant.parse("2026-06-15T12:00:00Z")));
        store.putGrant(new TenantGrantV1(
                "client-A", "tenant-A",
                Set.of("orders:create"), true, 5L));

        // In a real pipeline this trusted principal is created
        // only after HMAC, key status, timestamp verification.
        var principal = new VerifiedHmacPrincipalV1(
                "client-A", "client-a-k3", "orders-api");

        var result = new TenantPolicyGateV1(store).evaluate(
                principal,
                "/v1/tenants/tenant-A/orders",
                "orders:create");

        assertFalse(result.allowed());
        assertEquals(TenantPolicyOutcomeV1.TENANT_REVOKED,
                result.outcome());
    }
}
~~~

Điểm của test là **MAC hợp lệ không làm tenant ACTIVE**. Đây không phải full e2e test vì dùng fixture và tạo trusted principal nội bộ; production test phải gửi request qua thật gateway/verifier và chứng minh handler không chạy.

### 16.4. Vì sao test cả P→A và P→B?

Nếu chỉ test một tenant A bị revoke, code có thể vô tình đặt `principal.disabled=true` rồi chặn luôn B. Test `revokingTenantADoesNotRevokeTenantB` và `revokingGrantPToADoesNotRevokePToB` bảo vệ yêu cầu **thu hồi có phạm vi chính xác**.

### 16.5. Strict policy và public response

Các enum outcome giúp test/metrics phân biệt nguyên nhân. Không nhất thiết trả `TENANT_REVOKED` trực tiếp ra Internet cho unauthenticated caller, vì có thể tiết lộ sự tồn tại/trạng thái tenant. API nên phân biệt trusted caller/admin và policy redaction.

## 17. Commit-time fencing và test race

### 17.1. Kiểm epoch trước khi commit là cần nhưng có thể chưa đủ

Ví dụ helper kiểm có còn khớp epoch:

~~~java
public final class TenantEpochCheckV1 {
    private final TenantAuthorityV1 authority;

    public TenantEpochCheckV1(TenantAuthorityV1 authority) {
        this.authority = authority;
    }

    public boolean stillAllowed(
            String tenantId, long admittedEpoch) {

        try {
            var current = authority.findTenantExact(tenantId);

            return current.isPresent()
                    && current.get().tenantId().equals(tenantId)
                    && current.get().status() == TenantStatusV1.ACTIVE
                    && current.get().epoch() == admittedEpoch;
        } catch (TenantAuthorityUnavailableV1 bad) {
            return false;
        }
    }
}
~~~

**Cảnh báo:** Helper kiểm epoch là một **điều kiện cần nhưng không tự đủ** để hứa “không commit sau revoke”, vì sau `stillAllowed` có thể xảy ra revoke trước transaction commit. Cần check + business write trong **cùng transaction/locking boundary** hoặc distributed fencing scheme tương đương.

### 17.2. Test phân biệt admission và commit policy

~~~text
1. Store tenant A ACTIVE epoch=17.
2. HMAC request R is valid.
3. Tenant gate ALLOW with epoch=17.
4. Pause worker before write using a barrier.
5. Revoke tenant A: status=REVOKED epoch=18.
6. Worker resumes.
7. Commit fence sees epoch mismatch or REVOKED.
8. No new business write under strict commit-time guarantee.
~~~

Dùng barriers/latches thay vì `Thread.sleep` để điều phối race. Unit test trên fake authority chỉ chứng minh branch; integration test phải kiểm rollback thật và transactional guarantees. Nếu revoke và business writes ở hai stores khác nhau, test cả failure giữa hai commits, retries và external side effects.

### 17.3. Một SQL pattern mang tính minh họa

~~~sql
-- Business transaction, on a DB supporting row locks
BEGIN;

SELECT status, epoch
FROM tenant_policy
WHERE tenant_id = :tenantId
FOR UPDATE;

-- Require status = 'ACTIVE', epoch = :admittedEpoch.
-- If not, ROLLBACK.
-- Enforce principal grants/object ownership under policy.

INSERT INTO tenant_orders(tenant_id, order_id, payload)
VALUES (:tenantId, :orderId, :payload);

COMMIT;
~~~

Lệnh revoke phải cùng tranh lock:

~~~sql
BEGIN;

SELECT status, epoch
FROM tenant_policy
WHERE tenant_id = :tenantId
FOR UPDATE;

UPDATE tenant_policy
SET status = 'REVOKED', epoch = epoch + 1
WHERE tenant_id = :tenantId;

COMMIT;
~~~

Đây là **một pattern nếu tenant policy và business writes nằm chung transactional datastore**; cú pháp, isolation level và deadlock handling phụ thuộc DB. Trong môi trường microservices, không thể chỉ copy SQL trên để có cross-service atomicity.

### 17.4. In-flight action có thể không hỗ trợ cancellation

Nếu một payment đã gửi tới external processor trước revoke, internal tenant epoch check sau đó không thu hồi được external side effect. Thiết kế cần đặt điểm check trước external call, dùng idempotency/operation tracking và có compensation/refund theo business rules; ghi rõ rủi ro còn lại.

## 18. Gateway, proxy và cross-tenant routing

Một hệ thống multi-tenant thường có:

~~~mermaid
sequenceDiagram
    participant C as HMAC client
    participant G as Edge gateway
    participant V as Verifier
    participant T as Tenant authority
    participant A as Application
    participant DB as Tenant DB

    C->>G: Signed request for Tenant A
    G->>G: Reject duplicate auth/tenant headers and bad framing
    G->>V: Trusted signed request semantics
    V->>V: Exact key lookup, canonical bytes, full HMAC
    V->>T: Tenant A status + principal-A grant
    T-->>V: ACTIVE or REVOKED with epoch
    V->>V: Timestamp freshness and nonce admission
    V->>A: Trusted principal + tenant context
    A->>A: Authorize action and object ownership
    A->>DB: Commit with tenant fence when required
~~~

### 18.1. Header injection và tenant ambiguity

Một client có thể gửi:

~~~http
X-Tenant-Id: tenant-A
x-tenant-id: tenant-B
~~~

HTTP field names **case-insensitive**. Nếu gateway first-wins và handler last-wins, hai tầng có thể đồng ý về HMAC trên A nhưng ứng dụng xử lý B. Reject duplicate signed/identity headers ở ingress, kể cả duplicate values giống nhau, trước khi proxy merge/drop evidence.

Nếu chỉ có path tenant, có thể **cấm hoàn toàn `X-Tenant-Id`** thay vì cho hai nguồn lựa chọn tenant. Nếu protocol yêu cầu cả hai, phải ký và kiểm **equality exact** giữa signed path tenant và header claim.

### 18.2. `X-Forwarded-*` và original URI

Các field như `X-Original-URI`, `X-Forwarded-Host` hoặc `X-Authenticated-Tenant` do caller tự khai **không phải trusted metadata**. Gateway phải strip/overwrite theo trusted proxy contract, và backend chỉ tin context được truyền qua mTLS/integrity-protected assertion hoặc cơ chế tương đương.

Không dùng `X-Original-URI` từ Internet để “sửa” canonical path khi verifier thấy HMAC mismatch; hãy xác định signing boundary cố định và test proxy path rewrite.

### 18.3. HTTP/1.1 ↔ HTTP/2 conversion

Kiểm tra:

- HTTP field name case normalization.
- Duplicate `Authorization`, `X-Key-Id`, `X-Tenant-Id`.
- HTTP/2 pseudo-headers `:authority` và `:path`.
- Encoded slashes/dot segments và percent-encoded query.
- Path-prefix stripping hoặc service-mesh rewrite.
- Content-Length/Transfer-Encoding/framing ambiguity.
- Body bytes khác do proxy decompress/re-serialize.
- Host/authority mismatch với audience và server routing.

**Tenant gate phải kiểm cùng resource semantics mà business handler thực thi**. Nếu gateway và backend có thể hiểu khác nhau, từ chối thay vì thử nhiều cách normalize.

### 18.4. Bypass gateway hoặc secondary ingress

Nếu public gateway đã deny tenant A nhưng một backend endpoint nội bộ hoặc disaster recovery hostname vẫn accept A, revoke chưa hoàn thành. Test các path: public ingress, alternate hostname, internal ingress, service mesh, blue-green deployment và background workers.

### 18.5. Connection và cache

Một HTTP keep-alive/HTTP/2 connection tồn tại trước revoke **không cấp quyền vĩnh viễn**. Mỗi request mới cần policy phù hợp; stream dài có thể phải reauthorize/close sau một event revoke. Gateway-authenticated context cũ không được giữ mãi trong thread-local/mutable global cache rồi áp nhầm tenant khác.

### 18.6. Tenant context leakage giữa threads

Một anti-pattern Java:

~~~java
// SAI: mutable global state shared by concurrent requests.
static String currentTenant = "tenant-A";
~~~

Khi requests từ A/B xử lý đồng thời, B có thể đọc context của A. Tenant context phải là **request-scoped**, immutable khi được truyền tới handler, và được dọn đúng khi dùng thread-local/reactive context. Context chỉ được tạo sau authentication + tenant policy, không từ raw header.

## 19. Runbook vận hành Tenant revocation

Một runbook rõ cần phân vai:

- **Requesting authority:** bên có quyền đề nghị revoke.
- **Approver/incident commander:** người quyết định phạm vi và mức khẩn cấp.
- **Control-plane operator:** thực thi tenant policy transition.
- **Application/data owner:** quyết định xử lý in-flight jobs, data retention và compensation.
- **Security/audit:** lưu evidence, monitoring và kiểm tra bypass.

### 19.1. Phase 1 — Scope và quyết định

1. Xác nhận tenant ID exact trong trusted tenant registry.
2. Phân biệt revoke toàn tenant, suspend tạm, revoke một grant, hay revoke credential cụ thể.
3. Xác định parent/child tenants, shared resources và delegated principals.
4. Liệt kê normal business routes, API gateways, services, queues, workers, sessions và external integrations.
5. Chọn **admission-time** hoặc **commit-time** guarantee theo mức độ rủi ro.
6. Xác nhận exception endpoints có approval riêng; không dùng “admin header” tự khai.
7. Ghi correlation/incident ID, actor, reason code, expected scope và thời điểm.

### 19.2. Phase 2 — Control-plane revoke

1. Ghi transition từ ACTIVE/SUSPENDED sang REVOKED với epoch/revision mới.
2. Lưu trusted state change audit, không chỉ thay một cache flag.
3. Phát invalidation/revocation event với revision để chống stale overwrite.
4. Nếu yêu cầu immediate containment, chặn gateway/backend/commit paths theo authority đáng tin.
5. Tùy chính sách, revoke tenant-scoped tokens/sessions, disable background jobs và grants có liên quan; không revoke credentials của tenant B chỉ vì chung một principal.
6. Không tự hạ status từ REVOKED về ACTIVE khi có lỗi rollout; cần approval/re-onboarding workflow.

### 19.3. Phase 3 — Kiểm tra hiệu lực

1. Ký request test cho tenant A bằng một **credential hợp lệ**; xác nhận HMAC có thể đúng nhưng tenant policy DENY.
2. Kiểm qua gateway, backend, secondary ingress, nodes, regions, HTTP versions được hỗ trợ.
3. Gửi request cho tenant B bằng principal có grant B và xác nhận B **không bị ảnh hưởng**.
4. Revoke riêng grant P→A; kiểm P→B còn hợp lệ.
5. Xem queue/worker pending, streams và in-flight operations theo guarantee.
6. Quan sát cache epoch, replica lag, authority outages và old-policy admissions.
7. Kiểm logs/metrics để xác định **effectiveRejectTime** theo topology.

### 19.4. Phase 4 — Business, dữ liệu và audit

1. Liệt kê operations accepted trước mốc revoke nhưng completed sau.
2. Đối chiếu durable transaction records, outbox, queue retries, idempotency store và external side effects.
3. Áp dụng data retention/offboarding riêng, không tùy tiện delete database chỉ vì tenant bị khóa.
4. Thực hiện compensation/notification theo policy nếu có tác động ngoài ý muốn.
5. Hoàn thiện audit: actor, approval, old/new state, epoch, propagation deadline, exceptions và uncertainty.
6. Bổ sung regression tests cho nguyên nhân đã phát hiện.

### 19.5. Tình huống cần canary/drill

Trước khi chạy lệnh revoke production, có thể luyện tập với tenant test và keys test để xác nhận pipeline. Không thực hiện tác động tài chính hoặc xóa dữ liệu thật trong thử nghiệm nếu không có phạm vi được phê duyệt.

Một drill có ích là **pause một worker trước commit**, thực hiện revoke, rồi resume để xác nhận commit fence; một drill khác là cố tình ngắt kết nối một verifier khỏi tenant authority và kiểm fail-closed.

## 20. Ma trận kiểm thử Tenant revocation

### 20.1. Credential, HMAC và tenant binding

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| HMAC hợp lệ, A ACTIVE | Principal có grant A | Có thể qua tenant gate |
| HMAC hợp lệ, A REVOKED | Same key, nonce mới | Deny A |
| HMAC hợp lệ, A SUSPENDED | Same key | Deny normal operations |
| HMAC hợp lệ, A PROVISIONING | Chưa activate | Deny |
| HMAC hợp lệ, A DECOMMISSIONED | Data offboarding | Deny normal operations |
| HMAC sai, A ACTIVE | Tag bị sửa | Reject trước policy principal |
| Key REVOKED, A ACTIVE | MAC có thể tính đúng dưới old secret | Reject credential |
| Key A3 ACTIVE, tenant A REVOKED | Các status độc lập | Deny tenant |
| Timestamp trước `revokedAt`, request tới sau | Signed timestamp fresh | Deny tenant |
| Nonce NEW, tenant REVOKED | Replay gate có thể NEW | Không business |
| Nonce REPLAY, tenant ACTIVE | MAC đúng nhưng nonce đã dùng | Reject replay |
| Key ID sai grammar | Unicode/CRLF/leading space | Reject trước lookup |
| Duplicate Authorization/Key-ID | Casing khác nhau | Reject HTTP ambiguity |
| Signed path A bị đổi sang B | Giữ tag cũ | MAC mismatch |
| Path tenant A, signed header tenant B | Hai nguồn trái nhau | Reject mismatch |
| Body target tenant bị sửa | Body digest signed | MAC mismatch hoặc request reject |
| Wrong audience | Orders key gọi payments | Reject |
| Client tự khai `X-Role: admin` | Không có trusted grant | Deny |

### 20.2. Grant, tenant scope và hierarchy

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| P có grant A và B, A revoked | P truy cập A | Deny A |
| P có grant A và B, A revoked | P truy cập B | May allow B |
| P→A revoked, tenant A ACTIVE | P truy cập A | Deny P |
| P→A revoked, tenant A ACTIVE | Client A truy cập A | May allow |
| P chỉ có `orders:read` | Thử `orders:create` | Deny action |
| P có create trên tenant A | Object thuộc B | Deny object |
| A ancestor REVOKED, child ACTIVE | Inherited deny policy | Deny child |
| Tenant B unrelated | A global revoke | B không bị tác động |
| Trusted administrative operation | A revoked | Chỉ allow qua riêng privilege policy |
| Tenant A unknown | Caller đoán ID | Deny, tránh tenant enumeration |

### 20.3. Distributed consistency và race

| Test | Failure mode | Kỳ vọng |
| --- | --- | --- |
| Cache A ACTIVE v17, revoke v18 | Refresh cũ đến sau | Không overwrite v18 |
| Gateway G1 nhận revoke, G2 chưa | Propagation lag | Đúng guarantee; cảnh báo nếu vượt |
| Region B partitioned | Authority không xác minh được | Strict fail-closed |
| Tenant authority timeout | Không rõ current state | Deny |
| Grant store timeout | Không rõ quyền | Deny |
| Registry timeout | Credential không xác minh được | Reject |
| Nonce store timeout | Admission không chắc | Reject |
| HTTP keep-alive request sau revoke | Same connection | Deny |
| WebSocket stream sau revoke | Subscription đang mở | Close/reauthorize theo policy |
| Request admitted trước revoke | Commit sau revoke | Theo admission/commit guarantee |
| Commit-time strict policy | Epoch đổi 17→18 trước commit | Abort business write |
| DB và payment processor khác transaction | External side effect in-flight | Không tuyên bố atomicity nếu không có |
| Queue job sau revoke | Enqueued trước revoke | Worker rechecks policy |
| Outbox retry sau revoke | Delayed publish | Theo explicit business policy |
| Replica failover với snapshot cũ | REVOKED state biến mất | Test fencing/durable authority |
| Backend direct access | Gateway đã deny | Không bypass policy |

### 20.4. Operational và audit

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Global revoke A | P/B vẫn có quyền hợp lệ | Không revoke nhầm B |
| Revoke một grant | Exact principal–tenant | Không sửa global tenant state |
| Unknown tenant flood | Nhiều raw IDs | Bounded metrics/cardinality |
| Logs | HMAC secrets/expected tags | Không ghi raw values |
| Admin revoke audit | Change status và epoch | Có actor/time/reason/approval |
| Cancellation | Jobs đang chạy | Có outcome và business reconciliation |
| Rollback deployment | Old cache/policy version | Không hồi sinh REVOKED |
| Emergency override | Admin privileged route | Separate approval, audit và least privilege |
| Incident tabletop | Multi-node stale ACTIVE | Xác minh hiệu lực từ mọi admission paths |

## 21. Sai lầm triển khai thường gặp

### 21.1. “HMAC hợp lệ thì tenant chắc chắn còn quyền”

Không. HMAC chỉ bảo vệ signed bytes và chứng minh bên ký sử dụng shared secret tương ứng. Tenant status/grants là **trusted state động** phía server; một key còn ACTIVE không kéo tenant REVOKED trở lại ACTIVE.

### 21.2. “Chỉ revoke key A3 là đã revoke tenant A”

Tenant A có thể có nhiều keys A3/A4 và partner P có grant vào A. Nếu mục tiêu là global tenant revoke, chặn đúng **tenant scope** trên tất cả principals, credentials và admission paths. Key revoke là một thao tác khác.

### 21.3. “Revoke tenant A thì tắt mọi principal từng có grant A”

Một principal P có thể vẫn có grant vào B. Thu hồi A phải không làm P mất quyền trên B ngoài scope được phê duyệt.

### 21.4. “Đã ghi REVOKED trong database là đủ”

Gateway, verifier, worker, replica và tenant cache có thể vẫn thấy ACTIVE. Phải kiểm propagation, failover, stale snapshot và guarantee thực tế.

### 21.5. “Client ký timestamp trước revokedAt thì vẫn được xử lý”

Client có secret có thể ký lùi thời gian trong freshness window. Signed timestamp không phải trusted server admission receipt.

### 21.6. “Chỉ kiểm status trước handler là chắc chắn không commit sau revoke”

Có race giữa status check và side effect. Commit-time guarantee cần transactional lock/fencing/consistency ở write boundary, không chỉ một boolean check sớm.

### 21.7. “Epoch đã được truyền trong queue nên worker khỏi kiểm lại”

Epoch được cấp tại admission chỉ cho biết **state từng được quan sát**. Worker phải kiểm current status/epoch theo chính sách, đặc biệt khi job có độ trễ.

### 21.8. “Cache revision lớn hơn tự giải quyết network partition”

Revision fencing chống stale overwrite khi node đã thấy bản mới, nhưng node bị partition có thể chưa từng biết revoke. Cần lease/authority/fail-closed và SLA được công bố.

### 21.9. “Tenant ID trong X-Role/X-Tenant-Id là nguồn quyền vì được ký”

HMAC chứng minh caller đã khai dữ liệu đó, không chứng minh server cấp quyền. Tenant target phải khớp resource route đã ký; grants lấy từ trusted policy.

### 21.10. “Chỉ kiểm tenant leaf khi có hierarchy”

Nếu parent REVOKED và policy inherited deny, child ACTIVE vẫn không đủ. Kiểm status của các ancestors liên quan trong một authority/epoch đáng tin.

### 21.11. “Revoke tenant nghĩa là phải xóa ngay dữ liệu”

Access revocation và data retention/deletion/offboarding khác nhau. Xóa dữ liệu cần chính sách riêng và approvals; có thể vẫn phải giữ audit hoặc cho export có kiểm soát.

### 21.12. “Nonce NEW chứng minh request được phép”

Nonce chỉ cho biết request chưa bị claim trước đó trong namespace đã định nghĩa. Tenant REVOKED vẫn phải deny.

### 21.13. “Key còn ACTIVE nên lệnh background đã enqueue luôn hợp lệ”

Policy có thể đổi trước worker chạy. Revalidation theo tenant/grant và commit policy là bắt buộc khi contract yêu cầu.

### 21.14. “Gateway đã reject tenant A thì backend không cần policy”

Có thể có secondary ingress, direct backend route, stale gateway hoặc trusted context giả mạo. Backend phải bảo vệ boundary và yêu cầu tenant-aware authorization tương ứng.

### 21.15. “Có thể tắt toàn bộ authorization cho admin bằng X-Admin:true”

Một header do caller tự khai không đủ quyền. Administrative exceptions phải dùng trusted principal, separate permission, audit và approval.

### 21.16. “Giữ toàn bộ request trong logs để tiện điều tra”

Có thể lộ HMAC tags, secrets, raw bodies và dữ liệu tenant. Log theo policy, redact sensitive fields và dùng correlation IDs.

### 21.17. “Khi tenant store lỗi, dùng cached ACTIVE mãi để tránh downtime”

Đó là fail-open nếu không thể khẳng định tenant còn hoạt động. Một API rủi ro cao cần fail closed hoặc một bounded staleness contract thực sự có thể chấp nhận.

### 21.18. “Idempotency giải quyết tenant revocation”

Idempotency ngăn tác động trùng theo operation ID, nhưng không ngăn một request mới khác operation ID hoặc một công việc đã enqueue thực hiện sau revoke trái policy.

## 22. Bài tập thực hành

### Bài tập 1 — Global tenant revoke khác key revoke

Tạo tenant A có client keys k2/k3 và partner P có grant P→A. Khi revoke riêng k2, xác định requests nào vẫn có thể hợp lệ. Sau đó revoke toàn tenant A và chứng minh mọi normal business requests vào A đều bị từ chối dù keys k3/P7 vẫn có MAC đúng.

### Bài tập 2 — Revoke grant P→A nhưng giữ P→B

Dùng `TenantPolicyGateV1` và fake authority. Principal P có grants A/B. Revoke chỉ P→A, assert P→A bị DENY còn P→B vẫn có thể ALLOW nếu B ACTIVE; client A có grant riêng trên A không bị ảnh hưởng.

### Bài tập 3 — HMAC đúng nhưng tenant REVOKED

Tạo raw body, canonical bytes và HMAC full 32 bytes bằng một test secret. Chứng minh `HmacSha256V1.sameTag` là true, nhưng gate trả `TENANT_REVOKED`. Giải thích đây không phải lỗi HMAC.

### Bài tập 4 — Backdate timestamp để lách revoke

Tạo `serverNow=T` và `tenant.revokedAt=T-10s`. Client có secret ký một request với `signedTimestamp=T-20s` vẫn nằm trong freshness window. Test phải từ chối tenant dù timestamp trước revokedAt.

### Bài tập 5 — Commit-time fence

Cho R vượt tenant gate ở epoch 17; dùng barrier giữ worker trước DB write, rồi revoke A epoch 18. Resume worker; business transaction phải abort theo strict commit-time contract. Giải thích tại sao gọi `TenantEpochCheckV1.stillAllowed` rồi ghi DB ở transaction khác **chưa đủ**.

### Bài tập 6 — Stale cache race

Loader A lấy snapshot ACTIVE revision 17 và pause. Admin revoke thành revision 18, loader B ghi snapshot mới. Loader A resume; cache không được overwrite revision 18 bằng 17. Test cả một node bị partition không nhận được revision mới và nêu fail-closed policy.

### Bài tập 7 — Parent tenant bị revoke

Org A có workspace A1/project A1P. Cho leaf ACTIVE nhưng parent REVOKED; theo inherited-deny policy, mọi protected operations trên child phải deny. Test di chuyển A1 sang org khác qua một workflow được ủy quyền.

### Bài tập 8 — Queue sau revoke

Enqueue job khi tenant A ACTIVE epoch 17, sau đó revoke thành 18 trước khi worker nhận job. Worker đọc current state và hủy/defer theo policy. Test không có side effect, status/correlation ID được audit đầy đủ.

### Bài tập 9 — Gateway path/tenant mismatch

Gửi signed request path tenant A nhưng thêm `X-Tenant-Id: tenant-B`; test edge reject theo contract. Lặp với duplicate tenant header khác case, HTTP/2 downgrade và encoded slash. Xác minh handler và verifier không nhận hai targets khác nhau.

### Bài tập 10 — Nonce và idempotency

Cho A REVOKED nhưng nonce mới N1; kết quả vẫn deny. Cho B ACTIVE gửi N1 ở namespace của key B; nó có thể qua replay nếu HMAC/grant đúng. Tạo hai requests cùng orderId nhưng nonce khác; business idempotency phải tránh duplicate.

### Bài tập 11 — Multi-region emergency revoke

Region A nhận REVOKED ngay, B bị network partition và còn ACTIVE cache. Xác định security guarantee mong muốn, test requests tới B và chọn fail-closed/strong authority/tenant kill-switch tương ứng. Không tuyên bố immediate global revoke nếu architecture không hỗ trợ.

### Bài tập 12 — Audit và business reconciliation

Một tenant A bị revoke trong khi 40 jobs đang chạy, 12 committed trước revoke, 8 timeout, 20 pending. Thiết kế cách phân loại theo durable operations/commit timestamps và epoch, không suy từ HTTP responses rằng tất cả requests chưa rõ trạng thái đều đã hoặc chưa thành công.

## 23. Checklist triển khai Tenant revocation

### 23.1. Credential và signed request

- [ ] HMAC key ID được parse strict, lookup exact và không thử default/other-client secrets.
- [ ] Key status/audience/algorithm/validity được kiểm trước khi tạo trusted principal.
- [ ] Canonical request ký đúng method, URI/tenant path, signed headers và body digest theo contract.
- [ ] Key ID, timestamp, nonce và audience được ràng buộc vào signed bytes.
- [ ] Full HMAC tag được decode/so an toàn; không so prefix hoặc chấp nhận truncated tags.
- [ ] HTTP edge reject duplicate/ambiguous authentication/tenant headers và framing lỗi.
- [ ] Gateway/router/backend dùng cùng tenant target semantics và signing boundary.
- [ ] Client-supplied role/tenant/admin headers không tự trở thành trusted authority.

### 23.2. Tenant policy và phân quyền

- [ ] Phân biệt global tenant revoke, principal grant revoke, client revoke và credential revoke.
- [ ] Tenant status có owner, enum/transition/epoch và audit rõ.
- [ ] Chỉ tenant ACTIVE được thực thi normal business operations theo contract.
- [ ] Global REVOKED deny mọi normal grants tới tenant đó.
- [ ] Grant kiểm exact principal + target tenant + action + resource, không dùng `anyGrant`.
- [ ] Revoke A không tự động phá quyền của P trên B ngoài scope được phê duyệt.
- [ ] Hierarchical parent REVOKED được enforce nếu policy inherited deny.
- [ ] Administrative exceptions có trusted principal, explicit allowlist/approval và audit.
- [ ] Tenant state và grant state không được lấy từ signed client claims.
- [ ] Tenant status store/authorization store unavailable không bị fail open.

### 23.3. Revocation propagation và operations đang chạy

- [ ] Định nghĩa admission-time hay commit-time revocation guarantee.
- [ ] Có effective revoke point, actor, reason, trusted timestamp và epoch.
- [ ] Cache invalidation/version fencing ngăn stale ACTIVE overwrite newer REVOKED.
- [ ] Có propagation deadline/SLA và metrics trên gateways, verifier nodes, regions.
- [ ] Node bị partition không nhận stale ACTIVE vô hạn khi policy yêu cầu nghiêm.
- [ ] Có direct-backend bypass protections, secondary ingress tests và HTTP versions tests.
- [ ] Có chính sách cho in-flight requests, background jobs, retries, streams và sessions.
- [ ] Commit-time fencing được enforce trong transactional/consistency boundary khi yêu cầu.
- [ ] External side effects có idempotency/operation tracking và compensation policy.
- [ ] Không coi revoke là xóa dữ liệu; offboarding/retention có workflow riêng.

### 23.4. Replay, monitoring và tests

- [ ] Timestamp/nonce được ký, freshness window và replay TTL nhất quán.
- [ ] Nonce claim atomic trên shared authority và namespace không nhập nhằng.
- [ ] MAC sai không poison nonce store; nonce NEW không override tenant REVOKED.
- [ ] Replay store unknown/outage không cho side effect qua fail open.
- [ ] Business idempotency có scope trusted tenant + principal + operation ID.
- [ ] Có test HMAC đúng nhưng tenant revoked, grant revoke A/B, ancestor deny và async worker.
- [ ] Có test races admission-vs-revoke-vs-commit, failover và stale-cache epochs.
- [ ] Có test registry/tenant authority unavailable và gateway tenant mismatch.
- [ ] Metrics tách key failure, tenant revoke, grant denial, stale-cache, replay và commit abort.
- [ ] Logs/traces redact shared secret, raw signature/signed sensitive request; hạn chế key/tenant enumeration.
- [ ] Incident runbook xác nhận revoke hiệu lực trên **mọi admission path**, không chỉ DB.

## 24. Câu hỏi tự kiểm tra

1. **Tenant revocation là gì?** Thu hồi khả năng sử dụng/truy cập một tenant theo trusted policy, không đơn thuần thay HMAC secret.
2. **Vì sao HMAC tag đúng mà request vẫn bị deny?** Tenant có thể REVOKED hoặc principal thiếu grant/resource permission.
3. **Key revocation khác tenant revocation thế nào?** Key revoke chặn credential; tenant revoke chặn normal operations vào tenant qua mọi credentials/principals.
4. **Revoke P→A có phải revoke P→B không?** Không, nếu chỉ grant A bị thu hồi.
5. **Tenant A bị revoke nhưng key A3 còn ACTIVE thì sao?** Key có thể cryptographically valid, nhưng tenant gate phải deny A.
6. **Signed timestamp trước revokedAt có chứng minh request đến trước revoke không?** Không; client có secret có thể tự khai timestamp.
7. **Nonce NEW có cho phép tenant revoked không?** Không, nonce và tenant authorization là hai gates độc lập.
8. **Vì sao phải ký target tenant path?** Để signer/verifier/handler không thực thi resource của tenant khác với request đã ký.
9. **Client-supplied X-Tenant-Id đã được ký có trở thành quyền không?** Không; signed claim không thay trusted policy.
10. **Global revoke A có override grant P→A ACTIVE không?** Có, trong normal business policy.
11. **Tenant ACTIVE và P→A grant REVOKED thì sao?** Deny P trên A.
12. **Admission-time revoke có chặn mọi commit sau revoke không?** Không nhất thiết, in-flight requests có thể hoàn tất.
13. **Commit-time guarantee cần gì?** Kiểm status/epoch trong transactional/fencing boundary tương ứng với side effects.
14. **Epoch so sánh bằng một đọc rồi ghi sau có đủ không?** Không, có TOCTOU race.
15. **Một cache version lớn hơn có giải quyết network partition không?** Không, node chưa thấy revision mới vẫn có thể stale.
16. **Tenant policy store outage thì API nhạy cảm có thể dùng cache ACTIVE vô hạn không?** Không nếu strict revocation policy yêu cầu fail closed.
17. **Vì sao worker queue phải revalidate tenant?** Policy có thể thay đổi sau khi job được enqueue.
18. **Một WebSocket được authenticated trước revoke có thể dùng mãi không?** Không mặc định; cần policy reauthorization/close.
19. **Parent REVOKED mà child ACTIVE có được phép không?** Không khi policy quy định inherited deny.
20. **Thu hồi tenant có đồng nghĩa xóa dữ liệu tenant không?** Không; data retention/offboarding là workflow riêng.
21. **Tại sao idempotency không thay tenant revoke?** Nó chỉ ngăn duplicate operations theo key, không chặn new unauthorized operations.
22. **HMAC valid có đủ quyền sửa object của tenant khác không?** Không, object-level authorization cần kiểm riêng.
23. **Revoke ghi ở DB nhưng một gateway cũ vẫn accept có hoàn thành chưa?** Chưa theo strict global guarantee.
24. **Đo hiệu lực revoke bằng gì?** Trusted epoch/status, propagation metrics và e2e tests trên mọi admission paths.
25. **Có cần test tenant B sau khi revoke A không?** Có, để chứng minh không revoke nhầm scope.

## 25. Tài liệu tham khảo

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Nền tảng MAC đối xứng; giới hạn của HMAC đối với authorization và tenant status.
- **RFC 4231 — HMAC-SHA-224/256/384/512 Test Vectors.** Known-answer tests cho HMAC primitive.
- **RFC 9110 — HTTP Semantics.** Request methods, HTTP fields, authentication và status semantics.
- **RFC 9112 / RFC 9113 — HTTP/1.1 / HTTP/2.** Header parsing, framing và proxy/gateway conversion.
- **RFC 3986 — URI Generic Syntax.** Path/query và percent-encoding ảnh hưởng target tenant binding.
- **NIST SP 800-57 Part 1 — Recommendation for Key Management.** Key lifecycle, scopes và revocation.
- **NIST SP 800-61 — Incident handling guidance.** Phân tích, cô lập và khôi phục sự cố truy cập.
- **OWASP API Security guidance.** Broken Object Level Authorization, authentication và multi-tenant resource access.
- **OWASP Authorization Cheat Sheet.** Least privilege, deny-by-default và revalidation quyền truy cập.
- **OWASP Secrets Management Cheat Sheet.** Credential isolation, secret storage, key rotation và audit.
- **Java SE 17 — `javax.crypto.Mac`, `MessageDigest.isEqual`, `Instant`, `Clock`, `Pattern`.** APIs được dùng trong ví dụ.
- **JUnit Jupiter User Guide.** Boundary, negative, mutation và integration tests cho policy.
- **Cơ chế transactional locking, isolation và row versioning của DB triển khai thực tế.** Phải đối chiếu tài liệu DB cụ thể khi áp dụng commit-time fencing.

**Kết luận:** **Tenant revocation là một quyết định policy động ở cấp tenant**, không phải kết quả của phép toán HMAC. Một credential hợp lệ có thể ký request mới đúng tag, timestamp và nonce nhưng **vẫn phải bị từ chối nếu tenant đã REVOKED hoặc grant/action/resource không còn hợp lệ**. Hệ thống cần binding target tenant vào canonical request, exact key lookup, tenant/grant authority đáng tin, distributed cache consistency, fail-closed và chính sách rõ cho in-flight/queued operations. Đặc biệt, hãy phân biệt **chặn admissions mới** với **ngăn commit sau revoke**; các bảo đảm mạnh cần được thực thi đúng transaction/fencing boundary và kiểm thử qua gateway, nodes, regions cùng business side effects.


