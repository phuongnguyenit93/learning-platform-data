# Tenant isolation trong xác thực HTTP request bằng HMAC

> **Chương:** Multi-tenant  
> **Đề bài:** Tenant isolation  
> **Module:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request bao gồm phương thức HTTP, URI, header và/hoặc body theo hợp đồng ký; xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền.

## 1. Tenant isolation là gì và vì sao HMAC chưa đủ?

**Multi-tenancy** là mô hình một nền tảng phục vụ nhiều tổ chức/khách hàng (**tenant**) trên một hoặc nhiều thành phần hạ tầng chung. **Tenant isolation** nghĩa là một tenant không được tự ý đọc, sửa, thực thi nghiệp vụ hay sử dụng bí mật/khả năng thuộc tenant khác, ngay cả khi họ có tài khoản hoặc credential hoàn toàn hợp lệ của chính mình.

Trong một API machine-to-machine dùng HMAC, mỗi client được cấp **shared secret** để chứng minh rằng request được tạo bởi một chủ thể biết secret tương ứng. Nhưng một HMAC hợp lệ **không tự chứng minh request được phép truy cập bất kỳ tenant nào**. Nếu ứng dụng dùng raw `X-Tenant-Id`, query `tenantId` hoặc JSON `tenantId` từ client làm nguồn quyết định quyền, một client đã được xác thực vẫn có thể khai tenant khác và gây **cross-tenant access**.

Ví dụ:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Tenant-Id: tenant-b
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Request-Id: dRGla0slwS-KGNO1VKGbyw
Authorization: HMAC-SHA256 client_id="client-a", key_id="a-2026-11", signature="<tag>"

{"orderId":"order-owned-by-tenant-b","amount":150000}
~~~

Giả sử `client-a` có secret hợp lệ của **tenant A**. Dù `<tag>` được tính **đúng** cho toàn bộ request, **tenant B không tự trở thành tenant được xác thực hoặc được cấp quyền**. Client A có quyền chọn nội dung mình ký; việc ký `X-Tenant-Id: tenant-b` không biến giá trị ấy thành một chứng cứ rằng A thuộc B.

Thiết kế đúng phải có ít nhất ba lớp:

1. **Credential isolation:** secret của tenant/client A không dùng để ký giả danh credential của B.
2. **Authenticated tenant binding:** verifier ràng buộc credential đã xác minh với **tenant owner từ trusted key store**, không tin tenant claim như danh tính đã verify.
3. **Resource authorization/data isolation:** service kiểm action, resource owner và policy từ nguồn tin cậy trước khi truy cập dữ liệu hoặc gây side effect.

Một request có thể **HMAC authentication thành công** nhưng **authorization thất bại** vì client thuộc tenant A đang hỏi resource tenant B. Tùy hợp đồng, nếu client **ký tenant claim B trong khi credential chỉ thuộc A**, hệ thống cũng có thể từ chối ngay ở **bước tenant-binding** của authentication. Hai quyết định này khác nhau về nguyên nhân và nên được audit rõ.

### 1.1. Thuật ngữ cần phân biệt

| Khái niệm | Ý nghĩa | Nguồn tin cậy |
|---|---|---|
| **Tenant ID** | Định danh tổ chức/không gian dữ liệu được cô lập | Tenant registry/IAM/server-side mapping |
| **Client ID** | Định danh một ứng dụng/tích hợp gửi HTTP request | Client registry, verified credential |
| **Key ID** | Selector phiên bản credential để chọn HMAC secret | Trusted key record theo audience/client/key |
| **Shared secret** | Bytes mật mã dùng để tính HMAC | Secret Manager/KMS hoặc protected key store |
| **Claimed tenant ID** | Tenant mà caller khai trong header/path/body | **Untrusted** trước khi kiểm credential và binding |
| **Verified tenant ID** | Tenant thực được gắn với credential đã xác minh | Metadata chủ sở hữu khóa đã được tin cậy |
| **Authenticated principal** | Actor được tạo sau MAC, freshness và nonce pass | HMAC verifier |
| **Authorization scope** | Tập action/resources principal được phép dùng | Server-side policy/role/permission store |
| **Resource owner tenant** | Tenant sở hữu order/document/account trong DB | Trusted database/domain model |
| **Audience** | API/environment được credential phép sử dụng | Trusted routing/service config, key policy |

**Tenant và client không phải lúc nào quan hệ 1–1.** Tenant A có thể cấp credential cho `billing-bot`, `warehouse-sync` và `checkout-api`, mỗi ứng dụng có secret và permissions riêng. Một client kỹ thuật có thể vận hành cho nhiều tenants trong hệ thống SaaS, nhưng khi đó cần **ủy quyền rõ từng tenant** và nguyên tắc tenant context per request; không mặc định một credential được chuyển tenant tùy ý.

### 1.2. Mục tiêu học tập

Sau bài, người học có thể:

1. Giải thích tenant isolation ở lớp HMAC credential, authenticated identity, authorization, data access, cache và background jobs.
2. Phân biệt `claimedTenantId` với `verifiedTenantId`, chỉ tạo tenant principal từ trusted record/policy.
3. Thiết kế key record ràng buộc audience, client ID, key ID, immutable secret version và owner tenant.
4. Ký tenant context, client/key selectors, method, raw URI, timestamp, nonce và body digest bằng canonical request versioned.
5. Chống giả mạo tenant bằng một HMAC hợp lệ nhưng ký bởi **secret của tenant khác**.
6. Thiết kế nonce, idempotency và cache namespace không tạo cross-tenant collision/bypass.
7. Kiểm BOLA/IDOR và tenant-scoped SQL/ORM, queue worker, object storage và outbound integrations.
8. Quản lý key rotation/revocation, least privilege, audit và propagation trên nhiều replicas.
9. Viết Java 17 demo với multiple tenants, same textual key ID, strict parsing, JCA HMAC, tenant binding và replay tests.
10. Xây golden fixtures và gateway integration tests, phân biệt authn success, tenant-binding rejection và authz denial.

## 2. Threat model: tấn công vượt ranh giới tenant

### 2.1. Sai lầm “có chữ ký thì tenantId đã đáng tin”

Giả sử verifier chỉ kiểm HMAC theo `client_id` và handler:

~~~java
// SAI: HMAC có thể đúng cho client A, nhưng tenantId là
// giá trị A tự chọn. Không có quyền tenant B chỉ vì ký B.
String tenant = request.getHeader("X-Tenant-Id");
orderRepository.findById(request.getParameter("orderId"));
orderRepository.updateOwner(tenant);
~~~

A biết secret của chính A, nên A có thể tính tag cho request `X-Tenant-Id: tenant-b`. Nếu ứng dụng chuyển thẳng tenant claim vào `SET search_path`, query filter, cache key hoặc downstream headers, **A có thể điều khiển vùng dữ liệu B**.

Thay vào đó, trong mô hình một credential thuộc đúng một tenant:

~~~text
claimedClientId = client-a
claimedKeyId    = a-2026-11
claimedTenantId = tenant-b

record = keyStore.lookup(
  trustedAudience, client-a, a-2026-11
)
record.tenantId = tenant-a

verify full HMAC using record.secret
if claimedTenantId != record.tenantId:
    REJECT TENANT_BINDING_MISMATCH

authenticatedPrincipal:
  clientId = client-a
  tenantId = tenant-a
  keyId = a-2026-11
~~~

Nếu client A đổi header từ tenant A sang tenant B **sau khi ký**, HMAC fail nếu tenant field nằm trong canonical request. Nếu A **tự ký một request mới** khai tenant B bằng secret A, MAC có thể đúng — lúc đó **tenant binding** phải từ chối vì trusted owner vẫn là A. Đây là hai cơ chế bổ sung, không thay thế nhau.

### 2.2. Attack surface thường gặp

| Mặt tấn công | Ví dụ | Điều kiện bảo vệ |
|---|---|---|
| **Key selection** | Tenant A dùng key ID trùng text với B | Lookup scoped và owner validation |
| **Signed tenant header** | A tự ký `X-Tenant-Id: B` | HMAC pass chưa đủ; so với trusted tenant mapping |
| **Host/subdomain routing** | `b.api.example` với credential A | Host chỉ routing hint; enforce audience/tenant |
| **Path/query routing** | `/tenants/B/orders` | Không cấp B bằng path tenant claim |
| **Resource IDs** | A đọc `/orders/order-of-B` | Check owner từ DB (BOLA/IDOR) |
| **Bulk exports** | A yêu cầu export tất cả tenants | Scope query/job/object storage theo authenticated tenant |
| **Cache** | Key chỉ bằng `orderId` | Cache key chứa tenant và permissions context phù hợp |
| **Background jobs** | Worker dùng tenant mặc định hoặc mutable thread-local | Truyền trusted tenant context, kiểm ở worker |
| **Object storage** | A đoán blob path của B | Enforce tenant prefix/bucket policy + authz |
| **Database pool** | Connection còn session tenant ID của request trước | Reset tenant context khi trả connection, test RLS |
| **Logs/search** | Dashboard lọc raw claimed tenant B | Audit phân biệt claimed/verified tenant |
| **Rate limits** | A giả tenant B để dùng quota của B | Tính theo verified identity/trusted client |
| **Nonce/idempotency** | Key/nonce trùng giữa A và B | Namespace theo verified tenant và client |
| **Gateway internal headers** | A gửi `X-Verified-Tenant: B` | Strip ở edge, mTLS/trusted handoff |
| **Key lifecycle** | Metadata cache cho A map nhầm secret B | Immutable owner/version, safe invalidation |
| **Platform compromise** | Verifier workload có quyền đọc mọi secret | IAM least privilege, storage isolation, audit |

### 2.3. Tính xác thực ≠ tính toàn vẹn của authorization

HMAC-SHA-256 bảo vệ **tính toàn vẹn và nguồn gốc theo secret** của canonical bytes. Nó không mã hóa nội dung HTTP, không xác định một người dùng cuối nếu không có delegation, và không kiểm resource ownership.

Ví dụ khi A ký một JSON:

~~~json
{
  "orderId": "order-b-1009",
  "tenantId": "tenant-b",
  "amount": 500000
}
~~~

HMAC đúng chỉ chứng minh **bên biết secret A đã tạo/đồng ý các bytes đó**. Vì A có thể chọn các bytes, HMAC không biến `tenantId=tenant-b` thành một **quyền sở hữu**. Bước kiểm từ DB cần đảm bảo `order-b-1009` thuộc tenant đã xác thực và scope action được cấp.

### 2.4. Ranh giới bảo vệ của per-tenant secret

Secret riêng cho mỗi tenant giảm blast radius khi secret A bị lộ; attacker không có mặc định KB để ký B. Nhưng nếu **verifier/Secret Manager bị xâm nhập**, workload có thể có quyền đọc nhiều tenants, nên per-tenant secret không tuyệt đối cô lập. Cần phân tầng:

- Key material độc lập theo credential; không dùng một global shared secret cho toàn bộ tenants.
- Key ownership và audience binding.
- IAM/KMS permissions và tenant/environment isolation trong secret storage.
- Tenant-aware authentication principal + authorization.
- Tenant-scoped data, caches, queues, storage và APIs.
- Secret rotation, revocation, least privilege, audit và incident response.

## 3. Thiết kế identity và key-store contract

### 3.1. Credential phải ràng buộc với tenant thực

Một record server-managed minh họa:

~~~yaml
  # Chỉ mô tả metadata; không chứa plaintext shared secret.
  audience: orders-api-production
  clientId: client-a
  keyId: a-2026-11
  ownerTenantId: tenant-a
  immutableKeyRecordId: credential-00017
  secretVersionId: v7
  secretReference: opaque://secret-store/credential-00017/v7
  keyState: ACTIVE
  verifyOnlyUntilEpochSeconds: null
  allowedActions:
    - orders:commit
  environment: production
~~~

Record thứ hai:

~~~yaml
  audience: orders-api-production
  clientId: client-b
  keyId: a-2026-11
  ownerTenantId: tenant-b
  immutableKeyRecordId: credential-00042
  secretVersionId: v2
  secretReference: opaque://secret-store/credential-00042/v2
  keyState: ACTIVE
  verifyOnlyUntilEpochSeconds: null
  allowedActions:
    - orders:read
  environment: production
~~~

**Cố ý dùng cùng text `keyId=a-2026-11` ở hai records** để minh họa rằng key ID không nhất thiết global-unique. Namespace dựa vào `(audience, clientId, keyId)` **và** trusted tenant owner. Nếu một API cho phép **trùng cả client ID giữa tenants**, phải đưa tenant vào khóa lookup theo policy với tenant context đã được ràng buộc và xác minh cẩn thận, hoặc đổi thiết kế thành client ID duy nhất trong audience. Demo Java chọn **client ID duy nhất trong audience** để không có selector ambiguity.

### 3.2. Cấp secret độc lập, không dẫn xuất từ tenant ID

Một thuật toán sai:

~~~java
// SAI: tenantId thường dễ đoán, KHÔNG đủ entropy để làm secret.
byte[] secret = MessageDigest.getInstance("SHA-256")
        .digest(tenantId.getBytes(StandardCharsets.UTF_8));
~~~

Đúng hơn: tạo **secret CSPRNG độc lập** cho từng credential, chẳng hạn 32 bytes, rồi quản lý qua Secret Manager/KMS hoặc HSM handle:

~~~java
SecureRandom random = new SecureRandom();
byte[] independentSecret = new byte[32];
random.nextBytes(independentSecret);

// Provision một lần qua kênh được bảo vệ.
// Không print, commit, log, đính vào URL hoặc gửi plaintext qua ticket.
~~~

Nếu dùng key derivation như HKDF từ root secret, cần thiết kế được đánh giá về `salt`, `info` domain separation, tenant/client/version/audience, root compromise và rotation. Không tự dùng `HMAC(master, tenantId)` làm key cho mọi tenant mà chưa phân tích blast radius: lộ master có thể ảnh hưởng tất cả tenants.

### 3.3. Key lookup an toàn

Contract ví dụ:

~~~text
select(
  trustedAudience,
  claimedClientId,
  claimedKeyId
) -> trusted KeyRecord {
       ownerTenantId,
       immutableRecordId,
       secretVersion,
       state,
       allowedActions,
       secretReference
     }
~~~

Thứ tự:

1. Parse `Authorization` theo custom grammar không cho duplicate param/field.
2. Xác định audience bằng **trusted service/gateway route config**, không lấy một `X-Audience` không đáng tin làm policy.
3. Lookup chính xác record của `(audience, claimedClientId, claimedKeyId)`.
4. Kiểm record owner, state và effective deadline trước khi verify.
5. Dùng secret đúng version của record, **không thử tất cả secrets** nếu lookup/match thất bại.
6. Tính expected HMAC trên **canonical request**, bao gồm claimed tenant ID.
7. Sau MAC đúng, so `claimedTenantId` với `record.ownerTenantId` (trong mô hình một client–một tenant).
8. Kiểm timestamp, reserve nonce theo **trusted tenant/client**, sau đó tạo principal.
9. Authorization dựa trên principal và trusted resource ownership.

**Không dùng một “global fallback secret”** để cứu unknown tenant/key: nó làm mất key isolation và có thể vô hiệu hóa revocation, audit attribution.

### 3.4. Credential vs tenant delegation

Bài minh họa **credential thuộc một tenant cố định**. Một use case khác là aggregator/service provider có quyền gọi nhiều tenant:

~~~text
clientId=integration-partner
allowedTenantMemberships=[tenant-a,tenant-b]
requestedTenantId=tenant-b
~~~

Khi ấy không thể đơn giản so `claimedTenantId == ownerTenantId` vì một client có thể hợp pháp đại diện nhiều tenants. Thay vào đó, cần **delegation record/authorization grant do server cấp**, tenant context được ký, scope/expiry/consent rõ ràng và policy kiểm actor/action/resource. **Không tự suy “có HMAC secret của partner thì có quyền mọi tenant”.** Để tránh nhập nhằng, ví dụ Java chỉ xử lý one-client-one-tenant và nhắc rõ giới hạn này.

## 4. Hợp đồng canonical request có tenant context

### 4.1. Vì sao phải ký tenant ID mà vẫn phải kiểm tenant binding?

Nếu `X-Tenant-Id` không được ký, trung gian có thể đổi từ `tenant-a` sang `tenant-b` sau khi client ký mà MAC vẫn khớp với phần message còn lại. Đưa tenant ID vào canonical request ngăn **unsigned tenant-header tampering**.

Tuy nhiên, client A **biết secret A**, nên có thể ký một request **mới** khai tenant B. Vì thế verifier phải so tenant claim với **trusted credential owner/membership** sau khi xác minh MAC.

**Hai điều kiện độc lập:**

\[
\text{MAC\_valid}(K_A,\text{canonicalBytes}) \quad\land\quad
\text{tenantClaim}=\text{trustedOwner}(K_A).
\]

Chỉ khi cả hai (và freshness/nonce) đúng mới tạo authenticated principal mang tenant A.

### 4.2. Hợp đồng học tập `hmac-tenant-bound-v1`: 12 dòng

Đây là **hợp đồng minh họa riêng**, không phải định dạng tự nhận tương thích RFC 9421 HTTP Message Signatures.

| Dòng | Signed component | Ví dụ/quy tắc |
|---|---|---|
| 1 | Protocol version | `hmac-tenant-bound-v1` |
| 2 | Service audience | `orders-api-production`, trusted config |
| 3 | HTTP method | `POST` |
| 4 | Raw request target | `/v1/orders?mode=commit` |
| 5 | Content-Type | `application/json` canonical |
| 6 | Claimed tenant ID | `tenant-a`, strict syntax |
| 7 | Claimed client ID | `client-a`, strict syntax |
| 8 | Claimed key ID | `key-shared`, strict syntax |
| 9 | Timestamp | Unix epoch **seconds** canonical |
| 10 | Nonce | Base64URL no padding của 16 CSPRNG bytes |
| 11 | Client request ID | Base64URL no padding của 16 CSPRNG bytes |
| 12 | Body digest | SHA-256 của **exact raw request body**, lowercase hex |

Nối 12 dòng bằng LF (`\n`), **không có LF cuối**, encode UTF-8. Tính full `HMAC-SHA-256` 32-byte tag, encode Base64URL **không padding**, dài 43 ký tự. Trong `Authorization` chứa `client_id`, `key_id`, `signature`; `X-Tenant-Id` là signed header. Không đưa nguyên raw `Authorization` có chính signature vào canonical bytes để tránh vòng tự tham chiếu.

Ví dụ canonical text cho tenant A:

~~~text
hmac-tenant-bound-v1
orders-api-production
POST
/v1/orders?mode=commit
application/json
tenant-a
client-a
key-shared
1795824000
b75sZVQmhTBcfnX-bNbGqw
dRGla0slwS-KGNO1VKGbyw
<sha256-hex-of-exact-body>
~~~

Dòng hash cuối và signature HTTP là **placeholders**, không phải test vector thật. Timestamp là ví dụ cú pháp, không mặc nhiên nằm trong freshness window ở thời điểm chạy bài. Canonical bytes và expected tag production phải được đối chiếu bằng **golden fixtures độc lập**.

### 4.3. Cú pháp request ví dụ

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Tenant-Id: tenant-a
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Request-Id: dRGla0slwS-KGNO1VKGbyw
Authorization: HMAC-SHA256 client_id="client-a", key_id="key-shared", signature="<43-char-base64url-tag>"

{"orderId":"order-a-01","amount":150000}
~~~

Quy tắc:

- **Đúng một** mỗi signed field (`Authorization`, `X-Tenant-Id`, `X-Timestamp`, `X-Nonce`, `X-Request-Id`, `Content-Type`) trong trusted HTTP adapter, không để first/last wins.
- Custom `Authorization` có đúng một auth-scheme `HMAC-SHA256` và ba params theo contract.
- Tenant/client/key IDs là `[a-z0-9][a-z0-9_-]{0,63}` (demo dùng lowercase identifiers để giảm alias ambiguity); cùng grammar ở signer/verifier.
- Không chấp nhận URI có percent-encoded path separators, double slash, dot segments hoặc query ambigous ngoài route grammar demo.
- Signed nonce/request ID là 22 Base64URL no-padding chars, round-trip decode đúng 16 bytes.
- Timestamp Unix seconds, không convert milliseconds một cách đoán mò.
- Signature là 43 Base64URL no-padding chars, decode đúng 32 bytes, canonical round-trip.
- HMAC raw body digest tính trên **bytes giao dịch thực**, không tự chuẩn hóa JSON nếu contract không cho phép.
- HTTP field names có semantics case-insensitive; **values** của signed fields phải tuân hợp đồng, không bị proxy tự đổi trước verify.

## 5. Authentication, tenant binding và authorization là ba lớp

### 5.1. Ba quyết định cần tách

~~~mermaid
flowchart TD
    A["Incoming signed HTTP request"] --> B["Strict HTTP/header parser"]
    B --> C["Key lookup by trusted audience + client + keyId"]
    C --> D["Key state/version/owner checks"]
    D --> E["Verify full HMAC over tenant-bound canonical bytes"]
    E --> F{"MAC matches?"}
    F -->|No| G["AUTHENTICATION_REJECTED"]
    F -->|Yes| H{"Claimed tenant == trusted key owner?"}
    H -->|No| I["TENANT_BINDING_REJECTED"]
    H -->|Yes| J["Fresh timestamp and atomic nonce reservation"]
    J --> K{"Fresh and nonce unused?"}
    K -->|No| L["REPLAY/STALE_REJECTED"]
    K -->|Yes| M["Authenticated principal with trusted tenant/client"]
    M --> N["Authorize action/resource using trusted DB owner"]
    N --> O{"Policy allows?"}
    O -->|No| P["AUTHORIZATION_DENIED"]
    O -->|Yes| Q["Business operation with tenant-scoped data"]
~~~

**Authentication** chứng minh sender biết shared secret đúng key record; **tenant binding** chứng minh tenant request được phép gắn với record ấy; **authorization** chứng minh hành động trên tài nguyên được cho phép. Trong mô hình có delegation nhiều tenants, tenant binding chuyển thành **membership/role check** nhưng không thể bỏ.

### 5.2. Authenticated principal phải chứa tenant từ nguồn tin cậy

Không nên:

~~~java
// SAI: dùng raw tenant claim làm principal dù MAC đã được
// verify theo client, bởi client có thể tự ký tenant khác.
String tenant = request.getHeader("X-Tenant-Id");
AuthenticatedPrincipal principal =
        new AuthenticatedPrincipal(tenant, clientId);
~~~

Nên:

~~~java
// Chỉ minh họa ý tưởng, class cụ thể ở chương Java 17.
KeyRecord record = trustedKeyStore.get(keyRef);
verifyHmac(request, record.secret());
requireClaimedTenantEqualsRecordOwner(
        request.claimedTenantId(), record.tenantId());
verifyTimestampAndReserveNonce(record.tenantId(), record.clientId());
Principal principal = Principal.fromTrustedRecord(record);
~~~

Verifier không nên nhận `X-Verified-Tenant` từ Internet. Nếu gateway verify HMAC rồi chuyển tenant context cho backend, ingress phải **strip internal headers do client gửi**, tạo trusted metadata **sau verify**, truyền qua kênh được xác thực (ví dụ mTLS hoặc signed internal context) và backend phải phân quyền resource.

### 5.3. BOLA/IDOR: HMAC đúng vẫn có thể đọc dữ liệu B

Ví dụ principal tenant A gửi một request chứa order ID của B:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
X-Tenant-Id: tenant-a
Authorization: HMAC-SHA256 client_id="client-a", key_id="key-shared", signature="<valid-for-A>"
Content-Type: application/json
X-Timestamp: <fresh-epoch-seconds>
X-Nonce: <new-nonce>
X-Request-Id: <new-id>

{"orderId":"order-b-999","amount":150000}
~~~

HMAC có thể đúng (client A ký nội dung tùy ý). **Business handler** phải lấy `orderOwnerTenantId` từ **trusted DB** và kiểm:

~~~text
authenticatedPrincipal.tenantId == order.ownerTenantId
AND principal.permissions contains "orders:commit"
AND order is in an allowed state
~~~

Nếu chỉ query `SELECT * FROM orders WHERE id=?` và không kiểm owner, attacker có thể đoán order ID rồi tác động dữ liệu B. Ký `orderId` bằng secret A không biến order B thành tài sản A.

### 5.4. Thay tenant trong URL/path không phải delegation

Các dạng `/tenants/{tenantId}/orders`, subdomain `tenant-b.api.example` hoặc query `?tenantId=tenant-b` có thể được dùng để **định tuyến hoặc chọn tài nguyên**, không phải nguồn tin cậy quyết định quyền. Backend phải so route tenant với authenticated tenant (hoặc kiểm delegation grant) **và** kiểm owner tài nguyên cụ thể.

## 6. Replay, retry và idempotency phải tenant-aware

### 6.1. Reserve nonce chỉ sau xác minh MAC và tenant binding

Nonce giúp ngăn phát lại **một request đã được ký hợp lệ**. Một scope hợp lý:

~~~text
NonceScope(
    trustedServiceAudience,
    verifiedTenantId,
    authenticatedClientId,
    nonce
)
~~~

Với mô hình one-client-one-tenant của bài, chứa cả tenant ID và client ID giúp semantics rõ: hai clients của cùng tenant có nonce namespace riêng, và hai tenants khác nhau có thể tình cờ dùng cùng nonce text mà không ảnh hưởng nhau.

**Không reserve nonce dưới claimed tenant trước MAC**: attacker có thể tự khai tenant B và nonce N để **poison** namespace B, chặn request hợp lệ từ B. Đúng trình tự:

1. Lookup record đúng client/key.
2. Verify HMAC.
3. So claimed tenant với trusted owner.
4. Kiểm timestamp trong freshness window.
5. Reserve nonce atomically theo **verified tenant/client**, fail closed nếu store unavailable.
6. Chỉ sau đó tạo principal và đi authorization.

### 6.2. Timestamp window và TTL phải đủ dài

Policy minh họa:

~~~text
signedTimestamp: Unix epoch seconds (ASCII canonical)
accept if: now-300 <= timestamp <= now+300
nonce: 16 random bytes from SecureRandom
nonce text: 22 Base64URL no-pad characters
nonce namespace: (audience, verifiedTenant, authenticatedClient, nonce)
reserve: atomic insert-if-absent
retention example: 660 seconds
~~~

Window ±300 giây cho phép một signed timestamp có giá trị trong khoảng **600 giây** từ đầu đến cuối. TTL nonce 300 giây kể từ lần chấp nhận đầu sớm nhất **có thể hết trước khi timestamp hết hiệu lực**. Ví dụ 660 giây có margin so với 600 giây; thực tế chọn theo exact validity, clock skew, failover và SLA.

Redis `SET key value NX EX 660` dùng TTL **seconds**; `PX 660` chỉ là **660 milliseconds** (phải `PX 660000` mới tương đương). Redis/cache phân tán cần đảm bảo atomic semantics ở topology thật, không chỉ eventual replication khiến hai replicas cùng accept replay.

### 6.3. Key rotation không reset nonce namespace

Tenant A có client A và hai keys `key-old`, `key-new`. Trong cùng freshness interval, một nonce N của A **không được tái sử dụng** chỉ vì đổi key ID: `NonceScope` không chứa key ID. Một **client khác** của A hoặc client thuộc B có thể dùng nonce text giống N nếu mỗi client dùng CSPRNG và HMAC đúng.

### 6.4. Idempotency là chuyện nghiệp vụ

Retry một POST sau timeout có thể có **timestamp, nonce, request ID và signature mới**, nhưng giữ **idempotency key cũ** cho cùng logical operation. Scope ví dụ:

~~~text
IdempotencyScope(
    verifiedServiceAudience,
    verifiedTenantId,
    authenticatedClientId,
    idempotencyKey
)
~~~

Các requests cùng idempotency key phải tương ứng cùng operation fingerprint/method/body/authorization context theo policy; một key không thể dùng cho hai payload khác nhau mà không phát hiện mismatch.

**Không scope idempotency theo raw tenant claim**, bởi client A có thể cố tình claim B rồi gây collision ở B. **Không đưa nonce/timestamp/key ID vào idempotency scope** nếu muốn retries và key rotation vẫn giữ cùng business operation identity. Nonce chống replay ở HTTP attempt; idempotency ngăn side effect lặp ở **logical operation**; còn authorization quyết định liệu operation có được phép thực hiện không.


## 7. Tenant isolation không dừng ở lớp HMAC: database, cache, queue và storage

Một hệ thống có thể xác thực HMAC và tenant context hoàn toàn đúng nhưng **vẫn rò dữ liệu** nếu business service truy vấn/cached resource không tenant-aware. Isolation cần được duy trì trên toàn bộ **data plane**.

### 7.1. Tenant-scoped SQL và BOLA/IDOR

Ví dụ một bảng:

~~~sql
CREATE TABLE orders (
    tenant_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    amount BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Đọc order chỉ theo `order_id` dễ gây lỗi:

~~~sql
-- SAI nếu order_id có thể trùng giữa tenants hoặc không kiểm owner.
SELECT tenant_id, order_id, status
FROM orders
WHERE order_id = :orderId;
~~~

Query phải dùng **tenantId từ authenticated principal**:

~~~sql
SELECT tenant_id, order_id, status
FROM orders
WHERE tenant_id = :authenticatedTenantId
  AND order_id = :orderId;
~~~

Update cũng cần scope:

~~~sql
UPDATE orders
SET status = :newStatus
WHERE tenant_id = :authenticatedTenantId
  AND order_id = :orderId
  AND status = :expectedOldStatus;
~~~

**Không bind `:authenticatedTenantId` từ raw HTTP `X-Tenant-Id`**. Query builder/repository method nên nhận một immutable `AuthenticatedTenantContext` do security filter/verifier tạo, và caller không được tự ghi đè.

Dùng composite primary key `(tenant_id,order_id)` giúp biểu diễn domain isolation, nhưng không thay permission checks: một principal thuộc tenant A vẫn có thể thiếu scope `orders:commit` trong tenant A.

### 7.2. Row-Level Security (RLS) là defense in depth, không phải phép màu

Với PostgreSQL, có thể dùng RLS để bổ sung điều kiện tenant ở database:

~~~sql
-- Ví dụ minh họa ý tưởng. Cấu hình production cần role/RLS review.
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_by_tenant ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

Cần chú ý:

- `app.tenant_id` phải do **server authenticated context** đặt, không nhận trực tiếp untrusted client header.
- Thiết lập biến **theo transaction** và đảm bảo không rò tenant context khi pool tái sử dụng kết nối.
- Service role dùng để truy vấn **không** được có `BYPASSRLS`; cần hiểu quyền table owner/superuser và `FORCE ROW LEVEL SECURITY`.
- Một SQL injection có thể làm vô hiệu hóa giả định nếu attacker có thể gọi `set_config` trong cùng DB session. RLS là defense in depth, không thay input validation, parameterized queries và least-privilege DB role.
- Backup, migration, admin reports, ETL và background jobs có thể dùng role bypass; cần controls/audit riêng.
- Isolation test phải đi qua **connection pool thực**: request tenant A → tenant B trên cùng connection không được nhìn thấy state A.

Không lấy `tenantId` từ JWT/HMAC header rồi đặt session variable trước khi xác thực. Nếu có database-per-tenant/schema-per-tenant architecture, vẫn cần xác nhận trusted tenant-to-connection mapping và không tin raw routing claim.

### 7.3. Cache keys và CDN

Một cache nguy hiểm:

~~~text
cacheKey = "order:" + orderId
~~~

Nếu `orderId=123` tồn tại ở tenant A và B, response A có thể được trả cho B. Key an toàn hơn:

~~~text
cacheKey = (
    environment,
    serviceAudience,
    verifiedTenantId,
    resourceType,
    resourceId,
    authorizationVariantIfNeeded
)
~~~

Cần kiểm **cache fill** cũng như cache lookup: nếu worker vô tình đưa dữ liệu B vào key tenant A, tên key đúng vẫn không cứu được dữ liệu. Cache value validation, TTL, invalidation khi chuyển quyền và negative caching phải được xem xét.

Đối với HTTP shared CDN cache, `Authorization` và tenant context có thể ảnh hưởng cacheability. Không mặc định proxy/cache sẽ tự tách responses theo HMAC principal. Với dữ liệu private, thường dùng `Cache-Control: private, no-store` hoặc cấu hình edge policy được kiểm soát chặt; không chỉ thêm `Vary: X-Tenant-Id` rồi coi là đã an toàn nếu field này do client tự đặt.

### 7.4. Queues, event consumers và background jobs

Một request HMAC hợp lệ có thể enqueue job xử lý bất đồng bộ:

~~~text
HTTP authenticated principal:
  tenantId=tenant-a
  clientId=client-a
  actions=[orders:commit]

Queue message (trusted producer):
  jobId=server-generated
  tenantId=tenant-a
  actorClientId=client-a
  operation=COMMIT_ORDER
  orderId=order-a-01
  correlationId=trusted-edge-request-id
~~~

Worker không nên tin một `tenantId` tự do trong message nếu queue producer không được xác thực/ủy quyền. Nên:

1. Chỉ service producer được IAM/mTLS authorization publish vào trusted queue.
2. Worker nhận tenant context đã được server xác thực; có thể dùng signed internal envelope hay token có audience/TTL rõ nếu qua trust boundary.
3. Worker **kiểm lại resource owner và current policy** nếu công việc dài hạn hoặc quyền có thể bị thu hồi.
4. Không giữ mutable global/static `currentTenant` hoặc thread-local tenant chưa cleanup giữa jobs.
5. Partition/consumer group, retries và DLQ có namespace tenant phù hợp; dead-letter không để lộ raw body/PII.
6. Log/audit actor, tenant, job ID và result theo trusted context; không nhầm queued thành committed.

Một queue shared có thể là kiến trúc hợp lý, nhưng tenant-specific quotas, fairness và resource limits cần ngăn tenant A tiêu hết worker capacity của B.

### 7.5. Object storage, exports và search indexes

- **Object storage:** path `tenant-a/orders/report.csv` chỉ là convention. S3/GCS/Blob IAM policy, bucket rules và pre-signed URL minting phải đảm bảo actor tenant A không tự yêu cầu object B.
- **Export jobs:** filter phải dùng verified tenant; export artifact cần owner metadata và expiring scoped download link. Không chỉ lấy `?tenantId=B` cho batch export.
- **Search/index:** index query filter theo trusted tenant, kiểm facet aggregation/suggestions/highlights, search-cache key và vector search metadata. Cross-tenant similarity search có thể lộ snippets ngay cả khi document read endpoint đã bảo vệ.
- **Analytics:** background ETL có quyền toàn hệ thống không được vô tình xuất dữ liệu cross-tenant vào tenant-specific reports.
- **Logs/traces:** raw tenant identifiers và request body có thể là nhạy cảm; dashboards phải giới hạn quyền xem, không dùng public metrics label cho mọi claimed tenant.
- **Outbound webhooks:** chọn endpoint/secret theo verified tenant; nếu tenant ID/URL tự chọn từ request, thêm SSRF/credential leak risks.

### 7.6. Isolation còn là khả dụng (availability)

Tenant isolation không chỉ confidentiality/integrity. Tenant A có thể gửi hàng triệu HMAC attempts nhằm làm cạn:

- CPU HMAC, JSON parser hoặc body buffering.
- Key lookup/Secret Manager/KMS quota.
- Redis nonce store memory/cardinality.
- Database pool/queue workers hoặc storage bandwidth.
- Audit/log pipeline vì hàng triệu claimed tenant IDs.

Rate limits có thể cần **hai pha**: trước authn theo ingress/network signals chống volumetric abuse, sau authn theo **verified tenant/client** để đảm bảo fairness. Không lấy raw `X-Tenant-Id: tenant-b` làm quota identity, vì A có thể dùng field đó để tiêu quota B. Với invalid credentials chưa có principal, dùng nguồn tín hiệu không yêu cầu tin tenant claim và global budgets phù hợp.

## 8. Gateway, proxy, routing và tenant context

~~~mermaid
sequenceDiagram
    participant C as External Tenant A Client
    participant G as API Gateway / WAF
    participant V as HMAC Verifier
    participant K as Trusted Key Store
    participant N as Shared Nonce Store
    participant A as Business Authorization
    participant D as Tenant-scoped Data
    C->>G: Signed request, X-Tenant-Id=A
    G->>G: Drop client-provided internal identity headers
    G->>G: Validate HTTP framing and unique signed fields
    G->>V: Preserve signed method/target/headers/body
    V->>K: Lookup (trusted audience, clientId, keyId)
    K-->>V: Secret, ownerTenant=A, state
    V->>V: HMAC full-tag verify and tenant binding
    V->>N: Fresh timestamp, reserve (audience,A,client,nonce)
    N-->>V: Reserved or replay
    V->>A: Authenticated tenant principal A
    A->>D: Query/update WHERE tenant_id=A + policy
    D-->>A: Authorized tenant-scoped result
    A-->>C: Response per tenant A
~~~

### 8.1. Subdomain và header không phải bằng chứng membership

Một hệ thống có thể có route `https://tenant-b.api.example.test` hoặc `/tenants/tenant-b/orders`. Tuy nhiên, Host/path được client điều khiển ở mức request (dù TLS có ràng buộc hostname). Nó có thể là **routing hint**, không phải grant tenant B.

Các bước đúng:

- Gateway xác định **service audience** từ trusted route config và xác nhận request target phù hợp.
- Verifier dùng đúng secret/key record, MAC toàn bộ request target và tenant context.
- Tenant claim/route tenant phải match trusted owner hoặc server-issued delegation.
- Business layer kiểm resource tenant owner.
- Không cho attacker dùng `X-Original-URI`, `X-Forwarded-Host` hoặc `X-Verified-Tenant` từ Internet làm nguồn tin cậy nếu gateway chưa strip/validate và bảo vệ provenance.

### 8.2. HMAC và proxy rewriting

| Thay đổi qua gateway | Hậu quả | Phòng vệ |
|---|---|---|
| `/v1/orders` → `/api/orders` | Canonical target khác | Verify tại boundary đã công bố hoặc preserve trusted raw target |
| Thêm/bớt `//`, dot-segments, decode `%2F` | Router/verifier có thể hiểu khác | Reject ambiguous forms hoặc versioned canonical path policy |
| Đổi thứ tự query params, collapse duplicates | Canonical bytes/semantics khác | Strict signed query contract và regression tests |
| Lowercase HTTP field names | HTTP field names case-insensitive | Không nhầm với lowercasing values |
| Lowercase/trim tenant ID value ngoài contract | Tenant claim bị đổi | Sender/verifier dùng một grammar canonical |
| Hai `Authorization` hoặc hai `X-Tenant-Id` | Proxy và app chọn first/last khác nhau | Reject multiplicity tại ingress |
| Proxy thêm `X-Verified-Tenant: B` | Có thể thành spoofed principal | Strip inbound internal headers, trusted handoff only |
| Re-serialize JSON, đổi content encoding | SHA-256 raw body khác | Verify exact agreed body representation |
| Gateway chuyển HTTP/1.1 ↔ HTTP/2/3 | `:path`/origin-form và field mapping | Test cross-protocol fixtures |
| CDN trả response trước verifier | Cross-tenant cache leak | Chống cache bypass/poisoning |
| Proxy thay signed `X-Request-Id` | HMAC fail | Server-generated `edgeRequestId` riêng |

HTTP adapter phải lấy **đúng raw request target/body** ở boundary đã quy định, không mù quáng tin forwarded original URI headers do bất kỳ upstream nào gửi. Với API gateway verify hộ backend, cần **mTLS/zero-trust network controls** hoặc internal assertion được ký và ràng buộc audience/expiry, backend không được tin request headers “verified” từ mọi kết nối.

### 8.3. Lỗi tenant context qua connection pooling hoặc thread pools

Các frameworks có thể giữ `ThreadLocal<TenantContext>` hoặc session variable trên DB connection. Trong asynchronous/reactive pipeline, thread có thể đổi trong quá trình xử lý; một `ThreadLocal` cũ có thể gây **cross-tenant bleed** nếu không truyền context và cleanup đúng.

Khuyến nghị:

- Dùng **immutable authenticated context** được chuyển tường minh qua service/repository APIs.
- Nếu dùng thread-local framework context, khởi tạo/clear trong `try/finally`, không tin mặc định context luôn đúng.
- Ở reactive/async pipelines, dùng context propagation mechanism được hỗ trợ thay vì tự sao chép thread-local.
- RLS/session variables đặt ở transaction scope với connection reset.
- Test tuần tự request A → request B trên cùng thread/connection và kiểm không thấy dữ liệu A trong B.

## 9. Secret lifecycle và key rotation theo tenant

### 9.1. State machine của credential

| State | Ý nghĩa | Verify policy |
|---|---|---|
| `ACTIVE` | Credential đang được phép verify | Cho phép nếu MAC/tenant/time/nonce pass |
| `VERIFY_ONLY` | Credential cũ trong transition | Chỉ verify đến trusted deadline |
| `REVOKED` | Đã thu hồi | Reject, dù secret còn trong cache |
| `EXPIRED` | Deadline hiệu lực đã qua | Reject |
| `NOT_FOUND` | Không có key theo trusted lookup tuple | Reject, không fallback |

Một tenant A có thể rotate `client-a/key-old` sang `client-a/key-new` mà tenant B không phải đổi secret. Trong overlap:

~~~text
tenant-a / client-a / key-old / version-v6 / VERIFY_ONLY until D
tenant-a / client-a / key-new / version-v7 / ACTIVE
tenant-b / client-b / key-shared / version-v3 / ACTIVE
~~~

Tuy vậy, nếu **server-wide KMS access key/root encryption key** bị lộ, phạm vi tác động có thể gồm nhiều tenants. Cần phân biệt **tenant-specific secret compromise** với **control-plane/provider compromise**.

### 9.2. Quy trình rotate có audit

1. Xác minh actor (tenant admin/workload) được phép rotate đúng tenant/client.
2. Tạo secret **mới độc lập** với `SecureRandom`/KMS, không tái sử dụng key bytes cũ.
3. Lưu immutable key record/version và binding audience/owner/allowed actions.
4. Cấp secret mới qua kênh an toàn; không đưa raw material vào logs/tickets.
5. Đánh dấu key cũ `VERIFY_ONLY` với deadline hữu hạn, key mới `ACTIVE`.
6. Monitor **verifiedKeyId** usage (không đếm raw claimedKeyId) để xác định client đã migrate.
7. Revoke key cũ theo policy, invalidate caches ở mọi replicas/regions.
8. Đối chiếu management audit (actor/target/version/state) và request audit (verified tenant/key/outcome).
9. Test B tenant không bị thay đổi và cross-tenant MAC không được accept.
10. Với compromised secret, dùng emergency revoke/threat mitigation thay vì cho overlap kéo dài.

### 9.3. Lookup cache và policy invalidation

Một cache key đúng:

~~~text
KeyMaterialCacheKey(
    environment,
    serviceAudience,
    ownerTenantId,
    clientId,
    keyId,
    immutableSecretVersionId
)
~~~

Nếu chỉ cache theo `keyId`, tenant A và B có cùng `key-shared` sẽ bị lẫn material. Nếu chỉ cache theo tenant ID và mutable alias, một tenant có nhiều keys/versions sẽ bị lẫn khi rotate.

Cần **key-state check độc lập với plaintext cache lifetime**. Một key đã `REVOKED` phải bị reject theo current policy dù secret vẫn còn bytes trong process. Java `Arrays.fill(secret,0)` chỉ best-effort xóa bản copy ứng dụng sở hữu, không bảo đảm xóa tất cả copies trong JCA/JVM/GC.

### 9.4. IAM isolation và provider audit

Workload verifier có thể cần đọc secrets của nhiều tenant; đây là một điểm nguy cơ tập trung. Giải pháp tùy kiến trúc:

- Workload identity least privilege theo service/audience/environment, secrets resources có owner tags.
- Tách workload deployments theo tenant groups khi blast-radius/threat model yêu cầu.
- KMS/Secret Manager audit **material read** theo workload actor, target record/version và outcome.
- Không đồng nhất actor `svc-hmac-verifier-prod` đang fetch secret với raw claimed `client-a` trên HTTP.
- Management-plane audit ghi actor, approval/ticket, tenant target, previous/new state, version và deadline.
- Key ID không phải secret, nhưng có thể tiết lộ inventory và rotation timeline; quyền xem audit phải được hạn chế.

### 9.5. Revoke key không tự vô hiệu hóa các side effects đã commit

Nếu trước revoke, client A đã thực hiện một payment được DB commit, key revocation không tự rollback giao dịch. Incident response cần:

- Xác định thời gian có thể xảy ra secret exposure.
- Revoke credential, kiểm mọi replicas đã enforce policy.
- Correlate HMAC authentication, tenant binding, authorization và business transaction audit.
- Đánh giá request forgery với **timestamp/nonce mới**: anti-replay không ngăn attacker đã biết secret tạo message mới.
- Dùng ledger/idempotency/reconciliation để xử lý side effects; không suy số giao dịch từ số lần HMAC verify.


## 10. Java 17: verifier ràng buộc tenant với secret và principal

Ví dụ `TenantIsolationHmacDemo.java` sử dụng **JDK 17+**, không cần thư viện ngoài, minh họa các điểm an toàn:

1. Hai tenants `tenant-a`, `tenant-b` sở hữu **secrets CSPRNG độc lập**, có thể dùng **cùng text `keyId=key-shared`**.
2. Một tenant có nhiều clients với permissions khác nhau và một client có nhiều keys trong rotation.
3. Custom `Authorization` parser yêu cầu **đúng một field**, grammar nghiêm ngặt cho client/key ID/tag.
4. `X-Tenant-Id` được đưa vào canonical request **nhưng chỉ là claimed tenant** cho đến khi có binding với trusted record.
5. Key lookup dùng `(audience, claimedClientId, claimedKeyId)`; record lưu immutable `ownerTenantId` và actions.
6. Canonical message **12 dòng**: version, audience, method, raw URI, Content-Type, tenant/client/key IDs, timestamp, nonce, request ID, raw-body SHA-256.
7. HMAC-SHA-256 full tag, strict 43-char Base64URL no-padding, `MessageDigest.isEqual`.
8. Sau MAC đúng, kiểm `claimedTenantId == keyRecord.ownerTenantId`, rồi timestamp và reserve nonce theo trusted tenant/client.
9. Chỉ tạo `Principal` **sau toàn bộ authentication**, mang owner tenant từ record và permissions từ trusted store.
10. Business authorization so tenant với DB resource owner **và** required scope; cache dùng tenant-keyed resource ID.
11. Audit sự kiện có `claimedTenantId` (untrusted) và `macVerifiedOwnerTenantId` (trusted key owner sau MAC) tách khỏi `authenticatedTenantId`.
12. Tests giả tenant khác, giả client bằng secret B, header tampering, key rotation, stale/replay/nonce poisoning, rate-limited sink failure, cache separation và concurrent duplicates.

**Giới hạn được chủ động áp đặt để dễ học:** mỗi client ID là duy nhất trong một audience và gắn với **một tenant cố định**. Nếu một service account được ủy quyền nhiều tenants, phải thay phép so trực tiếp bằng **trusted tenant membership/delegation policy** — xem `3.4`. Mã này là core verifier học tập, không phải một implementation HTTP/2 gateway hoặc hệ thống KMS/Secret Manager thật.

### 10.1. Mã nguồn `TenantIsolationHmacDemo.java`

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
import java.util.Set;
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

public final class TenantIsolationHmacDemo {
    private static final String VERSION = "hmac-tenant-bound-v1";
    private static final String AUDIENCE = "orders-api-production";
    private static final String ALGORITHM = "HmacSHA256";
    private static final long WINDOW_SECONDS = 300L;
    private static final long NONCE_TTL_SECONDS = 660L;

    // Hợp đồng custom: scheme, param names case-insensitive;
    // identifiers/canonical values lowercase và case-sensitive.
    private static final Pattern AUTH = Pattern.compile(
            "(?i:HMAC-SHA256) "
          + "(?i:client_id)=\"([a-z0-9][a-z0-9_-]{0,63})\", "
          + "(?i:key_id)=\"([a-z0-9][a-z0-9_-]{0,63})\", "
          + "(?i:signature)=\"([A-Za-z0-9_-]{43})\"");

    private TenantIsolationHmacDemo() {}

    public record KeyRef(
            String audience, String clientId, String keyId) {}

    public enum KeyState {
        ACTIVE, VERIFY_ONLY, REVOKED
    }

    // Một credential được gắn owner tenant bất biến.
    public record KeyRecord(
            KeyRef ref, String ownerTenantId,
            KeyState state, long verifyUntilEpochSeconds,
            Set<String> permissions, byte[] secret) {
        public KeyRecord {
            if (ref == null || ownerTenantId == null
                    || state == null || permissions == null
                    || secret == null || secret.length != 32) {
                throw new IllegalArgumentException(
                        "Invalid key record");
            }
            permissions = Set.copyOf(permissions);
            secret = secret.clone();
        }

        @Override
        public byte[] secret() {
            return secret.clone();
        }
    }

    public record Request(
            String method, String rawTarget, String contentType,
            String claimedTenantId, String timestamp,
            String nonce, String clientRequestId,
            byte[] rawBody) {
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
            String claimedClientId,
            String claimedKeyId,
            String signature) {}

    // Principal luôn được xây từ trusted key metadata SAU MAC
    // + tenant binding + freshness + nonce.
    public record Principal(
            String tenantId, String clientId,
            String verifiedKeyId, Set<String> permissions) {
        public Principal {
            permissions = Set.copyOf(permissions);
        }
    }

    public record NonceScope(
            String audience, String authenticatedTenantId,
            String authenticatedClientId, String nonce) {}

    public enum Decision {
        AUTHENTICATED,
        BAD_AUTHORIZATION,
        UNKNOWN_CREDENTIAL,
        KEY_REVOKED,
        KEY_EXPIRED,
        BAD_SIGNED_REQUEST,
        MAC_MISMATCH,
        TENANT_BINDING_DENIED,
        TIMESTAMP_REJECTED,
        REPLAY_REJECTED,
        NONCE_STORE_UNAVAILABLE,
        AUDIT_UNAVAILABLE,
        CRYPTO_ERROR
    }

    public record AuthResult(
            Decision decision, Principal principal) {}

    // MAC-verified tenant khác authenticated tenant:
    // nonce replay/tenant binding failure KHÔNG được coi authn pass.
    public record AuditEvent(
            String eventId, Instant occurredAt,
            String claimedTenantId, String claimedClientId,
            String claimedKeyId, String macVerifiedOwnerTenantId,
            String authenticatedTenantId, String authenticatedClientId,
            String verifiedKeyId, String decision) {}

    public interface AuditSink {
        void append(AuditEvent event);
    }

    public static final class MemoryAuditSink implements AuditSink {
        private final ConcurrentLinkedQueue<AuditEvent> events =
                new ConcurrentLinkedQueue<>();
        private final AtomicBoolean available =
                new AtomicBoolean(true);

        public void setAvailable(boolean enabled) {
            available.set(enabled);
        }

        @Override
        public void append(AuditEvent event) {
            if (!available.get()) {
                throw new IllegalStateException("Audit unavailable");
            }
            events.add(event);
        }

        public List<AuditEvent> snapshot() {
            return List.copyOf(events);
        }
    }

    // DEMO: atomic trong 1 JVM, KHÔNG chia sẻ với replicas khác.
    public static final class LocalNonceStore {
        private final ConcurrentHashMap<NonceScope, Long> expiry =
                new ConcurrentHashMap<>();
        private final AtomicBoolean available =
                new AtomicBoolean(true);

        public void setAvailable(boolean enabled) {
            available.set(enabled);
        }

        public boolean reserve(
                NonceScope key, long now, long ttlSeconds) {
            if (!available.get()) {
                throw new IllegalStateException(
                        "Nonce store unavailable");
            }
            AtomicBoolean inserted = new AtomicBoolean(false);
            expiry.compute(key, (scope, oldExpiry) -> {
                if (oldExpiry != null && oldExpiry > now) {
                    return oldExpiry;
                }
                inserted.set(true);
                return Math.addExact(now, ttlSeconds);
            });
            return inserted.get();
        }
    }

    public record ResourceKey(String tenantId, String resourceId) {}

    // Demo cache: key bao gồm verified tenant, không chỉ resourceId.
    public static final class TenantResourceCache {
        private final Map<ResourceKey, String> values =
                new ConcurrentHashMap<>();

        public void put(
                Principal owner, String resourceId, String value) {
            values.put(
                    new ResourceKey(owner.tenantId(), resourceId), value);
        }

        public String get(Principal viewer, String resourceId) {
            return values.get(
                    new ResourceKey(viewer.tenantId(), resourceId));
        }
    }

    private static String newRandomId(SecureRandom random) {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    private static String strictSelector(String text) {
        if (text == null
                || !text.matches("[a-z0-9][a-z0-9_-]{0,63}")) {
            throw new IllegalArgumentException(
                    "Invalid signed tenant/client/key selector");
        }
        return text;
    }

    private static String strict16ByteRandom(String text) {
        if (text == null
                || !text.matches("[A-Za-z0-9_-]{22}")) {
            throw new IllegalArgumentException(
                    "Expected 22 Base64URL no-pad chars");
        }
        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(text);
        } catch (IllegalArgumentException invalid) {
            throw new IllegalArgumentException(
                    "Malformed Base64URL identifier", invalid);
        }
        if (bytes.length != 16
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes).equals(text)) {
            throw new IllegalArgumentException(
                    "Non-canonical 16-byte random identifier");
        }
        return text;
    }

    private static long parseEpochSeconds(String text) {
        if (text == null
                || !text.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException(
                    "Timestamp must be Unix epoch seconds");
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException overflow) {
            throw new IllegalArgumentException(
                    "Timestamp overflow", overflow);
        }
    }

    private static boolean timestampFresh(
            String text, long nowSeconds) {
        try {
            long delta = Math.subtractExact(
                    parseEpochSeconds(text), nowSeconds);
            return delta >= -WINDOW_SECONDS
                    && delta <= WINDOW_SECONDS;
        } catch (IllegalArgumentException | ArithmeticException error) {
            return false;
        }
    }

    public static Credential parseAuthorization(
            List<String> values) {
        if (values == null || values.size() != 1) {
            throw new IllegalArgumentException(
                    "Exactly one Authorization field required");
        }
        String header = values.get(0);
        if (header == null || header.length() > 300) {
            throw new IllegalArgumentException(
                    "Bad Authorization length");
        }
        Matcher m = AUTH.matcher(header);
        if (!m.matches()) {
            throw new IllegalArgumentException(
                    "Ambiguous/custom HMAC auth grammar");
        }
        return new Credential(
                m.group(1), m.group(2), m.group(3));
    }

    private static byte[] decodeTagStrict(String signature) {
        if (signature == null
                || !signature.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException(
                    "Expected 43 Base64URL characters");
        }
        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException invalid) {
            throw new IllegalArgumentException(
                    "Malformed HMAC tag", invalid);
        }
        if (bytes.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes).equals(signature)) {
            throw new IllegalArgumentException(
                    "Non-canonical/wrong-length HMAC tag");
        }
        return bytes;
    }

    public static byte[] canonicalBytes(
            Request r, String clientId, String keyId)
            throws GeneralSecurityException {
        if (r == null || !"POST".equals(r.method())) {
            throw new IllegalArgumentException(
                    "Only POST supported");
        }
        if (r.rawTarget() == null
                || !r.rawTarget().matches(
                    "/v1/orders\\?mode=(?:commit|preview)")) {
            throw new IllegalArgumentException(
                    "Unsupported raw target");
        }
        if (!"application/json".equals(r.contentType())) {
            throw new IllegalArgumentException(
                    "Content-Type must be application/json");
        }

        String tenant = strictSelector(r.claimedTenantId());
        String client = strictSelector(clientId);
        String key = strictSelector(keyId);
        String timestamp = r.timestamp();
        parseEpochSeconds(timestamp);
        String nonce = strict16ByteRandom(r.nonce());
        String requestId = strict16ByteRandom(
                r.clientRequestId());
        byte[] body = r.rawBody();
        if (body.length > 64 * 1024) {
            throw new IllegalArgumentException("Body too large");
        }

        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(body));
        String canonical = String.join("\n",
                VERSION, AUDIENCE,
                r.method(), r.rawTarget(), r.contentType(),
                tenant, client, key,
                timestamp, nonce, requestId, bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(
            byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        if (secret == null || canonicalBytes == null
                || secret.length == 0) {
            throw new IllegalArgumentException("Bad HMAC input");
        }
        Mac engine = Mac.getInstance(ALGORITHM);
        engine.init(new SecretKeySpec(secret, ALGORITHM));
        return engine.doFinal(canonicalBytes);
    }

    // Sender dùng secret của chính họ. Mọi tenant claim đều có
    // thể được sender ký, vì thế server PHẢI kiểm tenant binding.
    public static String sign(Request request, KeyRecord clientKey)
            throws GeneralSecurityException {
        String tag = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(
                    clientKey.secret(),
                    canonicalBytes(request,
                            clientKey.ref().clientId(),
                            clientKey.ref().keyId())));
        return "HMAC-SHA256 client_id=\""
                + clientKey.ref().clientId()
                + "\", key_id=\""
                + clientKey.ref().keyId()
                + "\", signature=\"" + tag + "\"";
    }

    private static boolean keyMayVerify(
            KeyRecord record, long now) {
        if (record == null || record.ref() == null
                || !AUDIENCE.equals(record.ref().audience())) {
            return false;
        }
        return record.state() == KeyState.ACTIVE
                || (record.state() == KeyState.VERIFY_ONLY
                    && now <= record.verifyUntilEpochSeconds());
    }

    // Append một terminal authentication event cho mỗi attempt.
    // Verified owner sau MAC khác authenticated tenant sau nonce.
    private static AuthResult finish(
            Decision decision, Request request,
            Credential claim, KeyRecord macVerified,
            AuditSink sink, Clock clock, SecureRandom rng) {
        Principal principal = decision == Decision.AUTHENTICATED
                ? new Principal(
                    macVerified.ownerTenantId(),
                    macVerified.ref().clientId(),
                    macVerified.ref().keyId(),
                    macVerified.permissions())
                : null;

        // Không ghi raw tenant claim không hợp grammar vào log.
        String safeTenantClaim = null;
        if (request != null
                && request.claimedTenantId() != null
                && request.claimedTenantId().matches(
                    "[a-z0-9][a-z0-9_-]{0,63}")) {
            safeTenantClaim = request.claimedTenantId();
        }

        try {
            sink.append(new AuditEvent(
                    newRandomId(rng), clock.instant(),
                    safeTenantClaim,
                    claim == null ? null : claim.claimedClientId(),
                    claim == null ? null : claim.claimedKeyId(),
                    macVerified == null ? null :
                            macVerified.ownerTenantId(),
                    principal == null ? null : principal.tenantId(),
                    principal == null ? null : principal.clientId(),
                    macVerified == null ? null :
                            macVerified.ref().keyId(),
                    decision.name()));
        } catch (RuntimeException auditFailure) {
            // Fail closed: không trả authenticated principal khi
            // mandatory audit sink unavailable.
            return new AuthResult(
                    Decision.AUDIT_UNAVAILABLE, null);
        }
        return new AuthResult(decision, principal);
    }

    public static AuthResult authenticate(
            Request request, List<String> authValues,
            Map<KeyRef, KeyRecord> trustedKeyStore,
            LocalNonceStore nonceStore, AuditSink sink,
            Clock clock, SecureRandom rng) {
        if (trustedKeyStore == null || nonceStore == null
                || sink == null || clock == null || rng == null) {
            throw new IllegalArgumentException(
                    "Missing trusted dependencies");
        }

        final Credential claim;
        try {
            claim = parseAuthorization(authValues);
        } catch (IllegalArgumentException badHeader) {
            return finish(Decision.BAD_AUTHORIZATION,
                    request, null, null, sink, clock, rng);
        }

        KeyRef lookup = new KeyRef(
                AUDIENCE, claim.claimedClientId(),
                claim.claimedKeyId());
        KeyRecord candidate = trustedKeyStore.get(lookup);
        if (candidate == null
                || !lookup.equals(candidate.ref())) {
            return finish(Decision.UNKNOWN_CREDENTIAL,
                    request, claim, null, sink, clock, rng);
        }

        long now = clock.instant().getEpochSecond();
        if (candidate.state() == KeyState.REVOKED) {
            return finish(Decision.KEY_REVOKED,
                    request, claim, null, sink, clock, rng);
        }
        if (!keyMayVerify(candidate, now)) {
            return finish(Decision.KEY_EXPIRED,
                    request, claim, null, sink, clock, rng);
        }

        final byte[] suppliedTag;
        final byte[] expectedTag;
        try {
            suppliedTag = decodeTagStrict(
                    claim.signature());
            expectedTag = hmac(
                    candidate.secret(),
                    canonicalBytes(request,
                        claim.claimedClientId(),
                        claim.claimedKeyId()));
        } catch (IllegalArgumentException badSignedInput) {
            return finish(Decision.BAD_SIGNED_REQUEST,
                    request, claim, null, sink, clock, rng);
        } catch (GeneralSecurityException cryptoError) {
            return finish(Decision.CRYPTO_ERROR,
                    request, claim, null, sink, clock, rng);
        }

        if (!MessageDigest.isEqual(
                expectedTag, suppliedTag)) {
            return finish(Decision.MAC_MISMATCH,
                    request, claim, null, sink, clock, rng);
        }

        // Từ đây candidate chỉ là MAC-verified record, CHƯA
        // phải principal authenticated.
        if (!candidate.ownerTenantId().equals(
                request.claimedTenantId())) {
            return finish(Decision.TENANT_BINDING_DENIED,
                    request, claim, candidate, sink, clock, rng);
        }

        if (!timestampFresh(request.timestamp(), now)) {
            return finish(Decision.TIMESTAMP_REJECTED,
                    request, claim, candidate, sink, clock, rng);
        }

        NonceScope nonceKey = new NonceScope(
                candidate.ref().audience(),
                candidate.ownerTenantId(),
                candidate.ref().clientId(),
                request.nonce());
        final boolean reserved;
        try {
            reserved = nonceStore.reserve(
                    nonceKey, now, NONCE_TTL_SECONDS);
        } catch (RuntimeException storeFailure) {
            return finish(Decision.NONCE_STORE_UNAVAILABLE,
                    request, claim, candidate, sink, clock, rng);
        }
        return finish(
                reserved ? Decision.AUTHENTICATED
                         : Decision.REPLAY_REJECTED,
                request, claim, candidate, sink, clock, rng);
    }

    // Tenant binding không thay thế authorization action/resource.
    public static boolean canCommitOrder(
            AuthResult authResult,
            String ownerTenantIdFromTrustedDatabase) {
        return authResult != null
                && authResult.decision() == Decision.AUTHENTICATED
                && authResult.principal() != null
                && authResult.principal().permissions()
                        .contains("orders:commit")
                && authResult.principal().tenantId()
                        .equals(ownerTenantIdFromTrustedDatabase);
    }

    private static Request request(
            String tenant, long epochSeconds,
            String nonce, String requestId, byte[] body) {
        return new Request(
                "POST", "/v1/orders?mode=commit",
                "application/json", tenant,
                Long.toString(epochSeconds), nonce, requestId, body);
    }

    private static void require(
            boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    private static void knownAnswerHmac() throws Exception {
        // RFC 4231, HMAC-SHA-256 Test Case 1.
        byte[] secret = new byte[20];
        Arrays.fill(secret, (byte) 0x0B);
        String actual = HexFormat.of().formatHex(
                hmac(secret, "Hi There".getBytes(
                    StandardCharsets.US_ASCII)));
        String expected =
                "b0344c61d8db38535ca8afceaf0bf12b"
              + "881dc200c9833da726e9376c2e32cff7";
        require(actual.equals(expected),
                "HMAC RFC 4231 known answer");
    }

    private static KeyRecord testSignerWithForeignSecret(
            KeyRef claimedKey, String claimedOwner,
            byte[] foreignSecret) {
        return new KeyRecord(
                claimedKey, claimedOwner,
                KeyState.ACTIVE, 0L,
                Set.of("orders:commit"),
                foreignSecret);
    }

    private static void raceSameNonce(
            Request request, String header,
            Map<KeyRef, KeyRecord> keys,
            Clock clock, SecureRandom rng)
            throws Exception {
        int attempts = 12;
        LocalNonceStore shared = new LocalNonceStore();
        MemoryAuditSink sink = new MemoryAuditSink();
        ExecutorService executor =
                Executors.newFixedThreadPool(attempts);
        CountDownLatch ready = new CountDownLatch(attempts);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<AuthResult>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < attempts; i++) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return authenticate(
                            request, List.of(header), keys,
                            shared, sink, clock, rng);
                }));
            }
            require(ready.await(10, TimeUnit.SECONDS),
                    "All verifier workers ready");
            start.countDown();

            int accepted = 0, replayed = 0;
            for (Future<AuthResult> future : futures) {
                Decision decision = future.get().decision();
                if (decision == Decision.AUTHENTICATED) accepted++;
                if (decision == Decision.REPLAY_REJECTED) replayed++;
            }
            require(accepted == 1,
                    "Exactly one nonce reservation wins");
            require(replayed == attempts - 1,
                    "Every other same-tenant nonce rejected");
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        knownAnswerHmac();
        SecureRandom rng = new SecureRandom();
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"),
                ZoneOffset.UTC);
        long now = clock.instant().getEpochSecond();

        byte[] secretA = new byte[32];
        byte[] secretANew = new byte[32];
        byte[] secretAReader = new byte[32];
        byte[] secretB = new byte[32];
        rng.nextBytes(secretA);
        rng.nextBytes(secretANew);
        rng.nextBytes(secretAReader);
        rng.nextBytes(secretB);

        // A and B deliberately share the same textual key ID.
        KeyRef aRef = new KeyRef(
                AUDIENCE, "client-a", "key-shared");
        KeyRef aNewRef = new KeyRef(
                AUDIENCE, "client-a", "key-new");
        KeyRef aReaderRef = new KeyRef(
                AUDIENCE, "client-a-reader", "key-shared");
        KeyRef bRef = new KeyRef(
                AUDIENCE, "client-b", "key-shared");

        KeyRecord a = new KeyRecord(
                aRef, "tenant-a", KeyState.VERIFY_ONLY,
                now + 120, Set.of("orders:commit"), secretA);
        KeyRecord aNew = new KeyRecord(
                aNewRef, "tenant-a", KeyState.ACTIVE,
                0L, Set.of("orders:commit"), secretANew);
        KeyRecord aReader = new KeyRecord(
                aReaderRef, "tenant-a", KeyState.ACTIVE,
                0L, Set.of("orders:read"), secretAReader);
        KeyRecord b = new KeyRecord(
                bRef, "tenant-b", KeyState.ACTIVE,
                0L, Set.of("orders:read"), secretB);

        Map<KeyRef, KeyRecord> keys = new HashMap<>();
        for (KeyRecord k : List.of(a, aNew, aReader, b)) {
            keys.put(k.ref(), k);
        }
        require(!Arrays.equals(
                a.secret(), b.secret()),
                "Independent secrets across tenants");
        require(!Arrays.equals(
                a.secret(), aNew.secret()),
                "Rotation requires new secret material");

        byte[] body = "{\"orderId\":\"order-01\",\"amount\":150000}"
                .getBytes(StandardCharsets.UTF_8);
        MemoryAuditSink sink = new MemoryAuditSink();
        LocalNonceStore nonceStore = new LocalNonceStore();

        // Tenant A with a valid old credential.
        String nonce = newRandomId(rng);
        Request reqA = request(
                "tenant-a", now, nonce, newRandomId(rng), body);
        String headerA = sign(reqA, a);
        AuthResult resultA = authenticate(
                reqA, List.of(headerA),
                keys, nonceStore, sink, clock, rng);
        require(resultA.decision() == Decision.AUTHENTICATED,
                "Tenant A authenticated");
        require("tenant-a".equals(
                resultA.principal().tenantId()),
                "Trusted owner is A");
        require(canCommitOrder(resultA, "tenant-a"),
                "A has orders:commit on A resources");
        require(!canCommitOrder(resultA, "tenant-b"),
                "A cannot commit B resources");

        // Exact replay and cross-key reuse of same tenant/client nonce.
        require(authenticate(
                reqA, List.of(headerA), keys, nonceStore,
                sink, clock, rng).decision()
                == Decision.REPLAY_REJECTED,
                "Exact replay rejected");
        require(authenticate(
                reqA, List.of(sign(reqA, aNew)), keys,
                nonceStore, sink, clock, rng).decision()
                == Decision.REPLAY_REJECTED,
                "Rotation does not reset nonce namespace");

        // B may use same nonce under its own trusted tenant/client.
        Request reqB = request(
                "tenant-b", now, nonce, newRandomId(rng), body);
        AuthResult resultB = authenticate(
                reqB, List.of(sign(reqB, b)), keys,
                nonceStore, sink, clock, rng);
        require(resultB.decision() == Decision.AUTHENTICATED,
                "Tenant B nonce namespace independent");
        require("tenant-b".equals(
                resultB.principal().tenantId()),
                "Trusted owner is B");

        // Authenticated B does NOT have orders:commit.
        require(!canCommitOrder(resultB, "tenant-b"),
                "B lacks commit action even on B resources");

        // Same tenant A, different client ID: a-reader has independent
        // nonce scope but cannot commit orders.
        Request readerReq = request(
                "tenant-a", now, nonce, newRandomId(rng), body);
        AuthResult reader = authenticate(
                readerReq, List.of(sign(readerReq, aReader)),
                keys, nonceStore, sink, clock, rng);
        require(reader.decision() == Decision.AUTHENTICATED,
                "Different client inside A can use same nonce");
        require(!canCommitOrder(reader, "tenant-a"),
                "Reader-only client cannot commit");

        // Most important case: A KNOWS secret A and signs tenant-b.
        // MAC matches, but tenant is not owned by that credential.
        Request signedForForeignTenant = request(
                "tenant-b", now, newRandomId(rng),
                newRandomId(rng), body);
        AuthResult foreignTenantAttempt = authenticate(
                signedForForeignTenant,
                List.of(sign(signedForForeignTenant, aNew)),
                keys, nonceStore, sink, clock, rng);
        require(foreignTenantAttempt.decision()
                == Decision.TENANT_BINDING_DENIED,
                "Valid A HMAC must NOT authenticate tenant B");
        require(foreignTenantAttempt.principal() == null,
                "Foreign tenant claim cannot become principal");

        // Change signed tenant field after A signed: MAC mismatch.
        Request honestA = request(
                "tenant-a", now, newRandomId(rng),
                newRandomId(rng), body);
        String honestHeader = sign(honestA, aNew);
        Request changedTenant = new Request(
                honestA.method(), honestA.rawTarget(),
                honestA.contentType(), "tenant-b",
                honestA.timestamp(), honestA.nonce(),
                honestA.clientRequestId(), honestA.rawBody());
        require(authenticate(changedTenant,
                List.of(honestHeader), keys, nonceStore,
                sink, clock, rng).decision()
                == Decision.MAC_MISMATCH,
                "Tenant header tampering changes signed bytes");

        // Compromised B secret cannot forge client A despite same keyId.
        KeyRecord forgedAWithBSecret =
                testSignerWithForeignSecret(
                        aRef, "tenant-a", secretB);
        Request forgery = request(
                "tenant-a", now, newRandomId(rng),
                newRandomId(rng), body);
        require(authenticate(forgery,
                List.of(sign(forgery, forgedAWithBSecret)),
                keys, nonceStore, sink, clock, rng).decision()
                == Decision.MAC_MISMATCH,
                "B secret cannot impersonate A");
        require(authenticate(forgery,
                List.of(sign(forgery, a)), keys,
                nonceStore, sink, clock, rng).decision()
                == Decision.AUTHENTICATED,
                "Invalid MAC never poisons A nonce");

        // Try replacing A key ID without recomputing signature.
        Request keySwapRequest = request(
                "tenant-a", now, newRandomId(rng),
                newRandomId(rng), body);
        String oldSigned = sign(keySwapRequest, a);
        String changedKey = oldSigned.replace(
                "key_id=\"key-shared\"",
                "key_id=\"key-new\"");
        require(authenticate(
                keySwapRequest, List.of(changedKey),
                keys, nonceStore, sink, clock, rng).decision()
                == Decision.MAC_MISMATCH,
                "Key selector is signed");

        // BOLA: A MAC valid but DB resource owner is tenant B.
        require(!canCommitOrder(resultA, "tenant-b"),
                "Verified tenant A cannot access B order");

        // Data/cache isolation: same resource ID for A and B.
        TenantResourceCache cache = new TenantResourceCache();
        cache.put(resultA.principal(), "order-123", "A-PRIVATE");
        cache.put(resultB.principal(), "order-123", "B-PRIVATE");
        require("A-PRIVATE".equals(
                cache.get(resultA.principal(), "order-123")),
                "A scoped cache");
        require("B-PRIVATE".equals(
                cache.get(resultB.principal(), "order-123")),
                "B scoped cache");

        // Body tampering fails HMAC; proper request can still pass.
        Request untouched = request(
                "tenant-a", now, newRandomId(rng),
                newRandomId(rng), body);
        String validTag = sign(untouched, aNew);
        Request tamperedBody = new Request(
                untouched.method(), untouched.rawTarget(),
                untouched.contentType(), untouched.claimedTenantId(),
                untouched.timestamp(), untouched.nonce(),
                untouched.clientRequestId(),
                "{\"orderId\":\"order-01\",\"amount\":900000}"
                    .getBytes(StandardCharsets.UTF_8));
        require(authenticate(tamperedBody,
                List.of(validTag), keys, nonceStore,
                sink, clock, rng).decision()
                == Decision.MAC_MISMATCH,
                "Raw body must be signed");
        require(authenticate(untouched,
                List.of(validTag), keys, nonceStore,
                sink, clock, rng).decision()
                == Decision.AUTHENTICATED,
                "Tampered body did not reserve nonce");

        // Key REVOKED even if caller still knows secret.
        KeyRef revokedRef = new KeyRef(
                AUDIENCE, "client-b", "key-revoked");
        KeyRecord revoked = new KeyRecord(
                revokedRef, "tenant-b", KeyState.REVOKED,
                0L, Set.of("orders:commit"), secretB);
        keys.put(revokedRef, revoked);
        Request revokedRequest = request(
                "tenant-b", now, newRandomId(rng),
                newRandomId(rng), body);
        require(authenticate(revokedRequest,
                List.of(sign(revokedRequest, revoked)),
                keys, nonceStore, sink, clock, rng).decision()
                == Decision.KEY_REVOKED,
                "Revoked key rejected");

        // Expired VERIFY_ONLY state.
        keys.put(aRef, new KeyRecord(
                aRef, "tenant-a", KeyState.VERIFY_ONLY,
                now - 1L, Set.of("orders:commit"), secretA));
        Request expired = request(
                "tenant-a", now, newRandomId(rng),
                newRandomId(rng), body);
        require(authenticate(expired,
                List.of(sign(expired, a)), keys,
                nonceStore, sink, clock, rng).decision()
                == Decision.KEY_EXPIRED,
                "Verify-only deadline honored");

        // Correct MAC with timestamp older than 300 seconds.
        Request stale = request(
                "tenant-a", now - 301L, newRandomId(rng),
                newRandomId(rng), body);
        require(authenticate(stale,
                List.of(sign(stale, aNew)), keys,
                nonceStore, sink, clock, rng).decision()
                == Decision.TIMESTAMP_REJECTED,
                "Timestamp freshness enforced");

        // Header ambiguity and invalid selector are rejected.
        Request malformed = request(
                "tenant-a", now, newRandomId(rng),
                newRandomId(rng), body);
        String h = sign(malformed, aNew);
        require(authenticate(malformed, List.of(h, h),
                keys, nonceStore, sink, clock, rng).decision()
                == Decision.BAD_AUTHORIZATION,
                "Duplicate Authorization rejected");

        // Nonce-store outage: fail closed; no authenticated result.
        nonceStore.setAvailable(false);
        Request noNonce = request(
                "tenant-a", now, newRandomId(rng),
                newRandomId(rng), body);
        require(authenticate(noNonce,
                List.of(sign(noNonce, aNew)),
                keys, nonceStore, sink, clock, rng).decision()
                == Decision.NONCE_STORE_UNAVAILABLE,
                "Nonce-store outage cannot bypass anti-replay");
        nonceStore.setAvailable(true);

        // Mandatory application audit unavailable: no principal.
        sink.setAvailable(false);
        Request noAudit = request(
                "tenant-a", now, newRandomId(rng),
                newRandomId(rng), body);
        require(authenticate(noAudit,
                List.of(sign(noAudit, aNew)), keys,
                nonceStore, sink, clock, rng).decision()
                == Decision.AUDIT_UNAVAILABLE,
                "Mandatory audit failure is fail closed");
        sink.setAvailable(true);

        // Verify the meaning of audit fields.
        boolean sawTenantBinding = false;
        boolean sawSuccessA = false;
        for (AuditEvent event : sink.snapshot()) {
            if (event.decision().equals("TENANT_BINDING_DENIED")) {
                require("tenant-b".equals(event.claimedTenantId()),
                        "Claim records untrusted requested tenant");
                require("tenant-a".equals(
                        event.macVerifiedOwnerTenantId()),
                        "MAC verified against actual owner A");
                require(event.authenticatedTenantId() == null,
                        "A cannot authenticate as B");
                sawTenantBinding = true;
            }
            if (event.decision().equals("AUTHENTICATED")
                    && "tenant-a".equals(
                        event.authenticatedTenantId())) {
                sawSuccessA = true;
            }
            if (event.decision().equals("MAC_MISMATCH")
                    || event.decision().equals("UNKNOWN_CREDENTIAL")) {
                require(event.macVerifiedOwnerTenantId() == null,
                        "Unverified selector cannot claim owner");
            }
        }
        require(sawTenantBinding && sawSuccessA,
                "Audit preserves claimed-vs-verified semantics");

        // 12 simultaneous attempts same tenant/client/nonce:
        // only one passes in this single-JVM demonstration.
        Request racing = request(
                "tenant-b", now, newRandomId(rng),
                newRandomId(rng), body);
        raceSameNonce(
                racing, sign(racing, b), keys, clock, rng);

        Arrays.fill(secretA, (byte) 0);
        Arrays.fill(secretANew, (byte) 0);
        Arrays.fill(secretAReader, (byte) 0);
        Arrays.fill(secretB, (byte) 0);
        System.out.println("PASS HMAC tenant-isolation tests");
    }
}
~~~

### 10.2. Chạy ví dụ

Lưu code vào `TenantIsolationHmacDemo.java`, dùng JDK 17+:

~~~bash
javac TenantIsolationHmacDemo.java
java TenantIsolationHmacDemo
~~~

Kết quả **kỳ vọng**:

~~~text
PASS HMAC tenant-isolation tests
~~~

Trong STEP 4 này, **không chạy** `javac` hoặc `java`. Các assertions và output ở trên mô tả hành vi cần kiểm khi chạy ở bước QA/thử nghiệm tiếp theo; chưa được coi là bằng chứng runtime đã pass.

### 10.3. Test quan trọng nhất: MAC đúng nhưng tenant sai

Khối mã sau thể hiện chính xác điều cần học:

~~~java
Request attempt = request(
        "tenant-b", now, newRandomId(rng),
        newRandomId(rng), body);

// Sender A CÓ secret A, nên có thể tự ký message khai B.
String signedByA = sign(attempt, aNew);

// MAC thực sự khớp secret A, nhưng key owner là tenant A.
AuthResult result = authenticate(
        attempt, List.of(signedByA), keys,
        nonceStore, sink, clock, rng);

require(result.decision() == Decision.TENANT_BINDING_DENIED,
        "Valid MAC is not tenant B membership");
require(result.principal() == null,
        "A must never receive principal of B");
~~~

Đây là lý do **“đã ký `tenantId`” chưa đủ để cách ly tenants**. Chữ ký chứng minh integrity của tenant claim *theo secret của A*, không chứng minh A có membership B. Phải so với trusted record hoặc grant policy.

### 10.4. Những giới hạn cố ý của demo

- `MemoryAuditSink` **không durable/WORM**, chỉ mô phỏng fail-closed; nonce có thể đã reserve trước khi audit sink fail, nên retry phải gửi request mới với nonce mới. Production cần chính sách audit durability/outbox và thứ tự side effects rõ.
- `LocalNonceStore` chỉ atomic trong một JVM, không có eviction nền, không xử lý multi-region replication/failover. Real system cần distributed atomic nonce store với TTL phù hợp.
- `KeyRecord` chứa secret trong RAM để demo; production dùng Secret Manager/KMS/key handle, versioning, workload IAM và short-lived protected cache.
- Demo **không** triển khai HTTP framing parser hay actual servlet/gateway; giả định adapter đã reject duplicate signed fields và có raw target/body đúng.
- `Authorization` grammar strict chỉ là subset custom-v1, không phải HTTP auth grammar tổng quát hay RFC 9421.
- `TenantResourceCache` chỉ minh họa tenant-keyed resources; không chứa permission variants, invalidation, encryption hay multi-region cache coherence.
- Principal trong demo dùng permission set tại thời điểm key record được tạo. Product thật cần policy refresh/revocation/delegation semantics để permission changes có hiệu lực đúng.
- Code kiểm resource owner bằng một string từ trusted DB; production cần DB-level enforcement/parameterized queries, policy checks, RLS, pagination/bulk/export tests và transactional integrity.
- `Arrays.fill` trên demo-owned arrays **không bảo đảm xóa mọi secret copy** bên trong JCA/JVM/GC.
- `MessageDigest.isEqual` so full 32-byte MAC tag, không biến mọi bước lookup/parse thành constant-time; cần threat model và rate limiting.
- `sign` và `authenticate` dùng chung canonical helper nên có thể cùng sai. Phải có **golden fixtures cross-language**, RFC 4231 known-answer và integration tests qua gateway.
- Audit mô hình hóa `claimedTenantId`, `macVerifiedOwnerTenantId` và `authenticatedTenantId`; deployment thực phải cân nhắc privacy, log injection, correlation và log retention.


## 11. Ma trận kiểm thử security tenant isolation

Một bộ kiểm thử chỉ xác nhận “client A ký được HMAC” chưa chứng minh **tenant isolation**. Test phải cố tình thao túng `tenantId`, `clientId`, `keyId`, route/host, resource owner, cache/DB context và trạng thái rotation trong khi phân biệt **MAC result**, **tenant-binding result** và **authorization result**.

### 11.1. HMAC credential và tenant-binding tests

| Case | Credential/claim | Điều xảy ra | Kỳ vọng |
|---|---|---|---|
| T01 | Client A ký tenant A bằng KA | MAC đúng, owner A | `AUTHENTICATED` nếu fresh |
| T02 | Client B ký tenant B bằng KB | MAC đúng, owner B | `AUTHENTICATED` nếu fresh |
| T03 | Client A ký tenant B bằng KA | **MAC đúng**, owner A ≠ B | **TENANT_BINDING_DENIED** |
| T04 | Client A ký tenant A, attacker sửa header thành B | Canonical bytes thay | **MAC_MISMATCH** |
| T05 | Client B biết KB, tạo header khai client A/key A | Server lookup KA | **MAC_MISMATCH** |
| T06 | A và B có cùng text `keyId=key-shared` | Tuple lookup owner khác | Không nhầm KA/KB |
| T07 | Cùng client ID text tại hai audiences | Keys scoped by audience | Không dùng prod key verify staging |
| T08 | Unknown client hoặc key ID | Không có record | **Reject**, không fallback secret |
| T09 | Key A `VERIFY_ONLY` còn hạn | MAC/tenant/time/nonce hợp lệ | Có thể authenticate |
| T10 | Key A `VERIFY_ONLY` quá deadline | Server time quyết định | **KEY_EXPIRED** |
| T11 | Key B `REVOKED` | MAC có thể tính đúng | **KEY_REVOKED** |
| T12 | A ký request tenant A nhưng raw body bị đổi | Body digest khác | **MAC_MISMATCH** |
| T13 | A ký tenant A, query target bị thay | Signed URI khác | **MAC_MISMATCH** |
| T14 | Scheme HMAC-SHA1 hoặc `alg=none` | Không trong contract | Reject |
| T15 | HMAC tag bị truncate/đổi encoding | Base64URL không canonical/32 byte | Reject |
| T16 | A ký claimed tenant B, nonce N; sau đó A ký tenant A, nonce N | Attempt B MAC đúng nhưng tenant mismatch; không reserve | Request tenant A vẫn được xét hợp lệ nếu chưa sử dụng N |

T03 và T04 là **hai test khác nhau**: T03 cho thấy ký một tenant claim bằng secret của A không cấp quyền B; T04 cho thấy chữ ký phải bảo vệ tenant claim khỏi thay đổi sau khi ký.

### 11.2. Replay, multi-client và rotation

| Tenant | Client | Key | Nonce | Kết quả |
|---|---|---|---|---|
| A | client-a | a-old | N1 (lần đầu) | Pass nếu MAC/freshness đúng |
| A | client-a | a-old | N1 (replay) | Reject |
| A | client-a | a-new | N1 | Reject xuyên key rotation |
| A | client-a-reader | reader-key | N1 | Có thể pass vì client khác |
| B | client-b | b-key | N1 | Có thể pass vì tenant/client khác |
| B | client-b | b-key | N1 (replay B) | Reject |
| A | client-a | a-new | N2, MAC giả trước | MAC fail, không poison N2 |
| A | client-a | a-new | N2, MAC thật sau | Pass nếu fresh và N2 chưa reserved |
| A | client-a | a-new | N3 trên 12 threads | Một winner trong shared atomic nonce scope |
| A | client-a | a-new | N4 khi store down | Fail closed |
| A | client-a | a-new | N5, timestamp `now-301` | Reject stale |
| A | client-a | a-new | N6, timestamp `now+301` | Reject too-far future |

Với multi-region, yêu cầu **distributed linearizable/atomic reservation theo đúng namespace**; việc mỗi node dùng `ConcurrentHashMap` độc lập không đáp ứng. Nếu architecture dùng active-active regions, phải phân tích network partitions và fail-closed behavior để không có hai winners trên cùng nonce.

### 11.3. Database và resource authorization

| Principal đã authenticate | Resource | Action | Kết quả |
|---|---|---|---|
| tenant A / client A, `orders:commit` | Order thuộc A | Commit | Có thể cho phép nếu business state hợp lệ |
| tenant A / client A, `orders:commit` | Order thuộc B | Commit | **DENY** |
| tenant A / reader-only client | Order thuộc A | Commit | **DENY**, thiếu scope |
| tenant A / reader-only client | Order thuộc A | Read | Có thể cho phép |
| tenant B / client B | Order thuộc A | Read | **DENY** |
| tenant A / client A | URI `/tenants/B/...` | Read/commit | **DENY** nếu không có trusted delegation |
| tenant A / client A | Body `tenantId=B` | Commit B | **DENY** |
| Tenant A privileged reporting job | Tenant B dữ liệu | Export B | Chỉ được nếu có **explicit delegated/admin policy** |

Phải test:

- Single-row read/write, pagination/list, bulk operations, search facets, audit/export.
- Update/delete bằng ID đoán được và object IDs trùng giữa tenants.
- New resource creation: `tenant_id` phải được gán từ principal server-side, không từ request body.
- Row-Level Security, query filters, ORM scopes, transaction/connection pooling.
- Role changes/revocation sau authentication nhưng trước async job execution.
- Multi-tenant analytics, Elasticsearch/vector index và object storage signed download links.
- Tenant A → B trên **cùng DB connection/thread** không rò session context.

### 11.4. Cache, queue, background và idempotency

1. Tạo `orderId=123` ở A và B, cache key chỉ `orderId`: negative test phải **phát hiện collision**.
2. Dùng `(verifiedTenant,orderId)` làm cache key: A và B thấy dữ liệu riêng.
3. User/client permission khác nhau trong **cùng tenant**: nếu response phụ thuộc role/scope thì cache key cũng cần permission context hoặc kiểm quyền trước lookup.
4. Một request A có `X-Tenant-Id=B` gửi vào queue: worker không được nhận B từ raw claim.
5. Worker dùng mutable thread-local `tenant=A` rồi xử lý job B: test cleanup/context propagation.
6. DLQ/retry không ghi full HMAC secret, raw Authorization hoặc sensitive body không cần thiết.
7. A và B gửi cùng text idempotency key `abc`: scope theo verified tenant/client nên không collision.
8. Client A gửi lại idempotency key cũ nhưng body intent khác: phải reject mismatch, không trả thành công cũ cho operation mới.
9. Client A rotate key nhưng retry cùng intent: idempotency key vẫn giữ operation identity, HMAC nonce mới.
10. Tenant A traffic flood không làm cạn hết quota mà B cần; test fairness/resource limits.

### 11.5. Golden fixtures và fuzzing

Một fixture để đối chiếu Java/Go/Node/Python nên chứa:

~~~text
protocolVersion=hmac-tenant-bound-v1
audience=orders-api-production
method=POST
rawTarget=/v1/orders?mode=commit
contentType=application/json
claimedTenantId=tenant-a
claimedClientId=client-a
claimedKeyId=key-shared
timestamp=<canonical-epoch-seconds>
nonce=<22-char-canonical-base64url>
clientRequestId=<22-char-canonical-base64url>
rawBodyBase64=<exact-request-bytes>
testOnlySecretHex=<32-random-test-bytes>
expectedCanonicalText=<12-LF-delimited-lines-no-final-LF>
expectedRawHmacHex=<64-lowercase-hex-chars>
expectedSignatureBase64UrlNoPad=<43-character-tag>
expectedAuthorization=<custom-v1-credential>
~~~

**Expected canonical bytes và HMAC phải được kiểm độc lập** bằng implementation tham chiếu hoặc ít nhất hai ngôn ngữ. Nếu client và server cùng dùng một helper sai, test round-trip vẫn có thể pass. RFC 4231 cung cấp known-answer vectors cho primitive HMAC-SHA-256, không định nghĩa canonical HTTP request của bài.

Fuzz:

- Duplicate headers/params và request smuggling/framing ambiguities.
- Tenant/client/key IDs dài quá mức, Unicode normalization, control characters, case changes.
- Signature Base64URL wrong alphabet, padding, non-canonical pad bits, truncated tag.
- Nonce/hash bytes, timestamp overflow/milliseconds/negative values.
- URL percent encodings, empty path segments, query duplicates, JSON byte changes.
- Multiple tenants with same key ID, client IDs colliding across audiences.
- Race conditions ở shared nonce and key-state rotation.

Fuzz có bounded input sizes/timeouts/rate; không làm stress production credentials hay public endpoints khi chưa được phép.

## 12. E2E test qua gateway và kiểm soát dữ liệu

### 12.1. Điểm quan sát cần ghi mà không lộ bí mật

Một end-to-end test có thể chụp metadata **không nhạy cảm** (không dump raw secret/tag/body):

| Chặng | Kiểm tra |
|---|---|
| SDK client | Contract version, audience, canonical digest của test fixture |
| CDN/WAF | Signed fields không bị rewrite, duplicates bị reject |
| Gateway | Server edge ID; không tin incoming verified-tenant headers |
| HMAC verifier | Key lookup scope, MAC verdict, trusted owner, tenant binding, nonce verdict |
| Internal hop | Tenant principal được truyền qua authenticated channel, audience-bound |
| Authorization | Action/owner/tenant policies applied |
| Repository | Tenant ID từ principal, query WHERE/RLS đúng |
| Cache | Verified tenant + resource + permission context |
| Queue worker | Trusted tenant context, owner/policy recheck |
| Object storage | Tenant namespace/IAM and presigned URL policies |
| Audit | Claimed vs verified tenant, outcome and correlation |
| Ledger | Durable operation commit count vs auth attempt count |

Không xuất ra raw full HMAC tag, expected tag, Secret Manager plaintext hoặc production body chỉ để debug. Với test fixtures non-sensitive, có thể log canonical **digest** và exact expected bytes trong môi trường test theo chính sách.

### 12.2. Test tấn công gateway tenant spoofing

Tình huống:

~~~http
POST /v1/orders?mode=commit HTTP/1.1
Host: tenant-b.api.example.test
X-Tenant-Id: tenant-b
X-Verified-Tenant: tenant-b
Authorization: HMAC-SHA256 client_id="client-a", key_id="key-shared", signature="<tag-made-by-A>"
~~~

Gateway phải:

1. Strip `X-Verified-Tenant` do external client gửi.
2. Ràng buộc Host/request target với trusted service audience/routing policy.
3. Reject signed header duplicates và malformed framing.
4. Không gắn principal tenant B chỉ từ host/header.
5. Chuyển request tới verifier bảo toàn signed material hoặc verify tại trusted boundary.
6. Verifier lookup key A, kiểm MAC, rồi reject tenant claim B vì record owner A.
7. Backend không được tự nhận B qua forwarded header sau khi verifier đã reject.
8. Security audit ghi **claimedTenant=B**, **MAC-verified owner=A** (nếu MAC đúng) và `TENANT_BINDING_DENIED`, không ghi authenticated tenant B.

Nếu application có delegated multi-tenant client hợp lệ, dùng policy grant được server chứng thực thay vì hardcoded equality check. Negative test trên một tenant không được làm mất quyền của những tenants khác.

### 12.3. Chẩn đoán một lỗi 401/403 có tenant context

Khi client phản ánh “HMAC đúng nhưng gọi tenant B bị lỗi”, phân tầng:

1. Có đúng một `Authorization`, `X-Tenant-Id`, timestamp/nonce, và signed body không?
2. Parser strict có nhận tenant ID theo grammar/hợp đồng không?
3. Audience có đúng production/staging và trusted routing không?
4. Key lookup có tìm đúng `(audience, clientId, keyId)` record với owner tenant không?
5. Key state còn `ACTIVE` hoặc `VERIFY_ONLY` chưa hết deadline không?
6. MAC có khớp raw canonical bytes của **chính request** không?
7. **Claimed tenant có được owner/delegation policy cho phép không?**
8. Timestamp có trong ±300s và nonce chưa reserve không?
9. Nếu authentication pass nhưng 403: action scope/role/DB resource owner ra sao?
10. Nếu business commit timeout: kiểm idempotency/ledger trước retry để không gây duplicate side effect.

Lỗi public nên dùng cách phân loại phù hợp contract và giảm key/tenant enumeration oracle; internal audit có reason codes với access control. Tránh trả “tenant B có tồn tại nhưng client A không được vào” nếu việc tiết lộ tồn tại của tenant cũng nhạy cảm.


## 13. Audit và observability cho tenant isolation

### 13.1. Claimed tenant khác MAC-verified owner, khác authenticated tenant

Một event thành công:

~~~json
{
  "schemaVersion": "hmac-tenant-auth-audit-v1",
  "eventId": "srv-event-0001",
  "occurredAt": "2026-11-28T00:00:00Z",
  "edgeRequestId": "trusted-ingress-request-0001",
  "serviceAudience": "orders-api-production",
  "eventType": "HMAC_AUTHENTICATION",
  "decision": "AUTHENTICATED",
  "claimedTenantId": "tenant-a",
  "claimedClientId": "client-a",
  "claimedKeyId": "key-shared",
  "macVerifiedOwnerTenantId": "tenant-a",
  "authenticatedTenantId": "tenant-a",
  "authenticatedClientId": "client-a",
  "verifiedKeyId": "key-shared",
  "keyState": "ACTIVE",
  "canonicalVersion": "hmac-tenant-bound-v1",
  "nonceOutcome": "RESERVED"
}
~~~

Event khi client A **có MAC đúng nhưng tự khai tenant B**:

~~~json
{
  "schemaVersion": "hmac-tenant-auth-audit-v1",
  "eventType": "HMAC_AUTHENTICATION",
  "decision": "TENANT_BINDING_DENIED",
  "claimedTenantId": "tenant-b",
  "claimedClientId": "client-a",
  "claimedKeyId": "key-shared",
  "macVerifiedOwnerTenantId": "tenant-a",
  "authenticatedTenantId": null,
  "authenticatedClientId": null,
  "verifiedKeyId": "key-shared",
  "nonceOutcome": "NOT_RESERVED"
}
~~~

Event `MAC_MISMATCH`:

~~~json
{
  "schemaVersion": "hmac-tenant-auth-audit-v1",
  "eventType": "HMAC_AUTHENTICATION",
  "decision": "MAC_MISMATCH",
  "claimedTenantId": "tenant-b",
  "claimedClientId": "client-a",
  "claimedKeyId": "key-shared",
  "macVerifiedOwnerTenantId": null,
  "authenticatedTenantId": null,
  "authenticatedClientId": null,
  "verifiedKeyId": null
}
~~~

Mọi giá trị **claimed** đến từ request chưa verify; chỉ có `macVerifiedOwnerTenantId` lấy từ trusted key record **sau MAC** mới có tính xác minh mật mã theo credential. Nhưng `macVerifiedOwnerTenantId` trong event `REPLAY_REJECTED` **không phải một authentication success mới**. Vì vậy dashboard đếm `decision=AUTHENTICATED` mới được gọi là authentication success; đừng gộp vào tổng “MAC matches”.

### 13.2. Security event taxonomy

| Event | Ý nghĩa | Ghi chú trust |
|---|---|---|
| `BAD_AUTHORIZATION` | Header format/multiplicity sai | Chưa có verified identity |
| `UNKNOWN_CREDENTIAL` | Không có tuple key hợp lệ | Không khẳng định tenant claim tồn tại |
| `KEY_REVOKED/EXPIRED` | Key không được phép verify | Candidate record có thể tồn tại nhưng chưa chứng minh sender |
| `MAC_MISMATCH` | Tag không khớp key owner record | `claimedTenantId` vẫn untrusted |
| `TENANT_BINDING_DENIED` | MAC đúng nhưng claimed tenant không được key owner cho phép | Có MAC-verified owner, **không có authenticated principal** |
| `TIMESTAMP_REJECTED` | MAC/tenant binding có thể pass, timestamp stale | Không tạo principal |
| `REPLAY_REJECTED` | MAC đúng nhưng nonce đã dùng | Không đếm thành authn success |
| `NONCE_STORE_UNAVAILABLE` | Không thể bảo đảm anti-replay | Fail closed |
| `AUTHENTICATED` | MAC/tenant/time/nonce đều pass | Principal mang trusted tenant |
| `AUTHORIZATION_DENIED` | Principal không có quyền action/resource | Event riêng sau authn |
| `BUSINESS_COMMITTED` | Transaction được commit bền vững | Từ domain ledger, không suy từ HMAC |
| `KEY_ROTATION/REVOKED` | Secret state thay đổi | Management-plane actor/target khác authn principal |

Có thể có audit `RESOURCE_CROSS_TENANT_DENIED` khi principal tenant A yêu cầu order B, nhưng log này phải dựa trên **resource owner đã được server tra tin cậy**, không chỉ một `tenantId` body field do A tự khai.

### 13.3. Không log secret hoặc identity chưa được verify như đã xác minh

~~~text
NEVER INCLUDE IN SECURITY AUDIT:
  plaintext HMAC shared secret
  full received/expected HMAC signature
  raw Authorization field
  raw request body containing PII/payment details
  bearer/session tokens
  private KMS material or environment secrets
  raw nonce by default
  exception stack traces with secret values
~~~

Tenant ID, client ID và key ID có thể là metadata nhạy cảm (tenant inventory/rotation timeline). Cân nhắc role-based access, retention, pseudonymization và giới hạn cardinality. Key ID **không phải secret** nhưng cũng không nên xuất hiện trong public 401 body hay metrics labels có thể bị attacker tự tạo.

Để chống **log injection**, reject control chars/oversized IDs và dùng structured serialization đúng escaping. Không nối raw `X-Tenant-Id` vào text log rồi parse lại như một trusted event. Một malicious client có thể gửi hàng triệu tenant IDs giả để làm sai dashboard hoặc làm cạn audit storage.

### 13.4. Metrics nên phục vụ isolation, không tạo leak

| Metric | Hữu ích khi |
|---|---|
| `hmac_authn_success_count{audience}` | Theo dõi tỷ lệ authentication pass |
| `hmac_authn_reject_count{reason}` | MAC mismatch/replay/bad header/key revoked |
| `tenant_binding_denied_count` | Phát hiện HMAC client cố chọn tenant không thuộc key |
| `resource_authz_denied_count{resourceType}` | Phát hiện cross-tenant read/write attempts |
| `key_rotation_verify_only_usage` | Kiểm tenant/client còn dùng key cũ dựa trên **verified events** |
| `key_store_lookup_latency` | Giám sát key metadata/Secret Manager |
| `nonce_store_errors` | Replay protection availability |
| `tenant_cache_collision_test_failures` | Cảnh báo regression ở cache |
| `db_rls_policy_denials` | Dấu hiệu data access sai tenant |
| `gateway_canonical_mismatch_count` | Proxy rewrite/SDK serialization problems |
| `audit_pipeline_lag` | Mất/chậm security evidence |
| `tenant_resource_saturation` | Kiểm fairness và noisy-neighbor risk |

Không dùng raw `claimedTenantId` làm prometheus label không giới hạn. Nếu cần điều tra riêng một tenant, dùng **verified tenant ID** và privileged drill-down trên audit store có access control. Với thất bại trước authentication, dùng aggregate reason counts hoặc pseudonymized claims theo chính sách.

### 13.5. Tính toàn vẹn của audit

Một audit pipeline có thể có append-only/WORM storage, quyền writer khác quyền delete, authenticated transport, event IDs dedup, event-time/ingestion-time, durable buffering/outbox và alert khi sink unavailable. Khi cần chứng cứ chống sửa/xóa, có thể hash-chain/ký batches bằng key độc lập. Không giả định `logger.info` là audit đã được persist.

HMAC shared secret không tạo **non-repudiation tuyệt đối**: server verifier/key custodian cũng có thể tạo HMAC nếu biết cùng secret. Audit giúp xác định record nào hệ thống đã chấp nhận, **không tự chứng minh với bên thứ ba chỉ riêng client đã ký**.

## 14. Incident response và các sai lầm thường gặp

### 14.1. Playbook khi nghi ngờ cross-tenant access

Giả sử phát hiện tenant A nhận dữ liệu của tenant B:

1. **Khoanh vùng thời gian/scope:** xác định edge request IDs, verified tenant/client, resource owner, route, key version và các services bị tác động.
2. **Bảo toàn evidence:** giữ HMAC authn audit, tenant-binding decisions, authorization logs, DB access logs, cache/queue records, deployments và key lifecycle events.
3. **Xác định trust boundary bị vượt:** key lookup sai owner, gateway header spoofing, tenant context từ body/path, DB query thiếu filter, stale thread-local, cache key collision hay queue worker lỗi?
4. **Ngăn rò tiếp diễn:** tắt endpoint/cấu hình lỗi, invalidate cache, chặn affected route, thu hẹp service permissions; không tự xóa audit.
5. **Đánh giá key compromise:** nếu secret tenant A bị lộ, revoke/rotate đúng client/tenant; nếu verifier/KMS root bị ảnh hưởng, mở rộng scope điều tra.
6. **Đối chiếu business effects:** đọc ledger/idempotency/DB transactions; authenticated event không đủ chứng minh side effect.
7. **Khắc phục theo chiều sâu:** sửa trusted context propagation, query/RLS, cache namespace, gateway stripping, IAM, policy/grants và runtime tests.
8. **Kiểm thử lại:** reproduce A→B negative cases, B unaffected positive cases, multi-region state/caches/nonce races.
9. **Hậu kiểm:** security review, audit access/retention, tenant notifications theo pháp lý/chính sách, bổ sung automated regression fixtures.

Nếu một HMAC credential của tenant A bị lộ, attacker có thể tạo **request mới** với nonce/timestamp mới. Anti-replay chỉ chặn việc **gửi lại cùng signed request**, không chặn attacker đã biết secret ký message mới. Cần revoke key, kiểm authorization và hạn chế rate/abuse.

### 14.2. Những sai lầm phổ biến

1. **Dùng một global HMAC secret cho mọi tenants:** một tenant leak có thể giả các tenants khác.
2. **Đọc tenant từ raw header rồi dựng authenticated principal:** bỏ qua trusted credential owner.
3. **Ký tenant ID nhưng không kiểm membership:** client biết secret của mình có thể ký tenant claim bất kỳ.
4. **Chỉ so tenant claim trước MAC, coi như đã xác thực:** attacker có thể spoof để gây sai audit/nonce rate quota.
5. **Lookup secret chỉ bằng key ID:** hai tenants có thể dùng cùng key text.
6. **Dùng Host/subdomain `tenant-b` như quyền:** routing hint không là authorization grant.
7. **Không tách client ID với tenant ID:** một tenant có nhiều apps và scopes.
8. **Dùng `SHA256(tenantId)` tạo secret:** không đủ secret entropy.
9. **Cho aggregator tự chọn mọi tenant không có delegation:** privilege escalation xuyên tenant.
10. **Dùng client-provided `X-Verified-Tenant`:** bypass trusted gateway-to-backend boundary.
11. **Không ký method/raw URI/body:** MAC có thể bị tái sử dụng cho hành vi khác.
12. **Proxy canonicalizes URI/body khác signer:** false rejects hoặc verifier/router mismatch.
13. **Nhận duplicate `Authorization`/`X-Tenant-Id`:** gateway/backend chọn values khác.
14. **Dùng nonce scope theo raw claimed tenant trước MAC:** attacker poison namespace tenant B.
15. **Dùng nonce store local ở mỗi replica:** replay được accept nhiều lần.
16. **Nonce TTL không phủ full timestamp window:** replay sau record expiry.
17. **Đưa key ID vào nonce scope không chủ ý:** key rotation làm reset replay uniqueness.
18. **Idempotency key global không tenant/client scope:** A và B collision/cross-tenant leak.
19. **Idempotency scope chứa timestamp/nonce:** retries tạo business operation mới.
20. **Query DB chỉ theo order ID:** BOLA/IDOR dù HMAC A đúng.
21. **RLS dùng tenant session variable lấy từ raw request:** tin nhầm client.
22. **Không reset tenant context khi connection/thread reuse:** dữ liệu A có thể chảy sang B.
23. **Cache key chỉ có resource ID:** A/B colliding keys và cache poisoning.
24. **CDN cache response private trước authn:** rò dữ liệu giữa tenants.
25. **Queue worker tin raw tenant field không có producer authentication:** async tenant spoof.
26. **Object storage dùng folder prefix mà không có IAM/policy:** đoán path vẫn đọc được.
27. **Search/index query không tenant filter:** leak snippets, facets, vector neighbors.
28. **Cho key `REVOKED` verify từ plaintext cache:** policy bị bypass.
29. **Không sync key-state multi-region:** một node nhận key đã revoke.
30. **Tính rate limits theo claimed tenant:** A có thể tiêu quota của B.
31. **Ghi raw shared secret/HMAC/body để debug:** tự tạo credential/data breach.
32. **Đếm claimed tenant/key là verified usage:** attacker làm sai dashboard.
33. **Authentication pass coi như đủ quyền:** thiếu owner/action authorization.
34. **HMAC không có non-repudiation nhưng được dùng làm bằng chứng ký độc lập:** nhầm tính chất shared secret.
35. **Chỉ kiểm positive path, thiếu cross-tenant negative tests:** không phát hiện isolation regression.

### 14.3. Các câu hỏi tự kiểm trước khi release

**Nếu client A ký một request khai tenant B bằng chính secret A, HMAC có thể đúng không?** Có, vì A biết secret của mình và tự chọn tenant claim. **Tenant binding phải reject** nếu A không có trusted delegation tới B.

**Nếu client A và B có cùng `keyId=primary`, có nguy hiểm không?** Không nhất thiết, **nếu** key lookup namespace đúng audience/client/owner và secret độc lập. Nguy hiểm nếu lookup global chỉ theo `keyId`.

**Nếu request có MAC đúng nhưng resource owner là tenant B, A có quyền không?** Không theo mặc định. Phải có explicit authorization grant và các kiểm tra action/resource/tenant; HMAC chỉ xác thực credential A.

**Nếu tenant ID được đưa vào signed body, có cần signed `X-Tenant-Id` không?** Tùy hợp đồng routing/security. Nếu backend dùng header tenant để route hoặc chọn policy, **header đó phải được ràng buộc** với canonical request hoặc bị rút từ trusted principal, không cho client sửa sau ký mà không bị phát hiện. Nhưng ký header vẫn không thay authorization.

**Nếu tenant A có nhiều client applications, nonce của hai apps có thể trùng text không?** Theo nonce scope `(audience,tenant,client,nonce)` của bài, có thể. Mỗi app nên dùng CSPRNG; uniqueness được kiểm riêng per authenticated client. Một client rotate key không được reuse nonce.

**Nếu gateway đã verify tenant rồi, backend có thể tin một header nội bộ không?** Chỉ khi trusted gateway identity/transport và header stripping được bảo vệ, có expiry/audience boundary, backend không nhận traffic bypass edge và vẫn tự kiểm resource authorization.


## 15. Bài tập thực hành và checklist production

### 15.1. Bài tập theo tình huống

**Bài 1 — Phân biệt principal.** Một request chứa `client_id=client-a`, `X-Tenant-Id=tenant-b`. Key record của client A thực sự thuộc tenant A. Hãy mô tả riêng ba điều kiện: MAC có thể đúng hay sai, tenant binding cho phép hay từ chối, và business authorization có được gọi hay không.

**Bài 2 — MAC đúng nhưng sai tenant.** Client A được biết secret KA. A tạo request mới `X-Tenant-Id=B` và tính HMAC đúng bằng KA. Giải thích vì sao ký tenant context không đủ để chứng minh membership B; viết assertion `TENANT_BINDING_DENIED`.

**Bài 3 — Header tampering.** Client A ký `X-Tenant-Id=A`. Proxy thay thành B mà không ký lại. HMAC có còn khớp không nếu tenant nằm trong canonical bytes? Vì sao?

**Bài 4 — Key collision.** Hai tenants có client IDs khác nhau nhưng cùng `keyId=primary`. Xây schema key store và SQL unique constraint hợp lý, kèm test không lấy nhầm secret.

**Bài 5 — Shared secret toàn cục.** Một hệ thống dùng `GLOBAL_HMAC_SECRET` cho tất cả tenants. Tenant A bị leak key. Chỉ ký `tenantId` trong canonical request có giải quyết được giả danh tenant B không? Thiết kế migration sang keys độc lập.

**Bài 6 — Tenant routing.** Client A gọi `https://tenant-b.api.example.test` với HMAC ký bằng KA. Gateway có thể dùng Host để định tuyến nhưng phải kiểm điều gì trước khi dựng principal B?

**Bài 7 — Delegated access.** Một aggregator có quyền thao tác tenant A và B trong một khoảng thời gian, nhưng không phải C. Mở rộng tenant-binding từ equality sang grant membership. Nêu audience, tenant scope, action, expiry, consent và audit fields.

**Bài 8 — BOLA.** Principal tenant A đã authn pass và biết order ID thuộc B. Hãy viết pseudo-SQL scoped tenant và phân biệt lỗi 403 với 401.

**Bài 9 — RLS.** Một service dùng PostgreSQL RLS với `app.tenant_id` trong connection session. Nếu connection reused mà không reset tenant, điều gì xảy ra? Thiết kế transaction-scoped setter và integration test A→B.

**Bài 10 — Cache collision.** Tenant A và B đều có `orderId=123`. Cache key `order:123` gây leak như thế nào? Khi cùng tenant có các permission tiers, cache key hay response validation cần thêm gì?

**Bài 11 — Queue worker.** API xác thực tenant A rồi enqueue job chứa `tenantId`. Vì sao worker không được tin một job bất kỳ đến queue? Thiết kế producer IAM, signed internal context, worker authz/resource recheck.

**Bài 12 — Secret rotation.** Tenant A có key old `VERIFY_ONLY` tới D và key new `ACTIVE`; tenant B không đổi. Làm sao kiểm A-old hết hạn mà không ảnh hưởng request B?

**Bài 13 — Nonce namespace.** A/client-1 đã reserve nonce N. A/client-2 và B/client-1 dùng N dưới secrets riêng. Theo `(audience,tenant,client,nonce)`, requests nào được phép nếu MAC đúng? A/client-1 dùng key mới với N thì sao?

**Bài 14 — Nonce poisoning.** Attacker gửi MAC giả khai tenant B với nonce N, rồi B gửi request thật có N. Tại sao nonce phải reserve sau MAC và tenant binding?

**Bài 15 — Clock/TTL.** Nếu freshness window là ±300s nhưng nonce TTL chỉ 180s kể từ lần accept đầu, nêu một timeline phát lại lọt khi timestamp vẫn hợp lệ. Chọn TTL/boundary thích hợp.

**Bài 16 — Idempotency.** Tenant A và B cùng dùng key text `payment-123`. Làm sao scope tránh collision? Khi tenant A retry bằng nonce mới nhưng key HMAC rotate, operation identity nên thay đổi không?

**Bài 17 — Authorization scope.** Tenant A có `client-a-reader` với `orders:read` và `client-a-committer` với `orders:commit`. Cả hai có secret HMAC hợp lệ của A. Thiết kế policy để reader không commit, kể cả khi body hợp lệ/đã ký.

**Bài 18 — Proxy internal header.** Client Internet gửi `X-Verified-Tenant: tenant-b`. Viết chuỗi controls ingress-strip, gateway HMAC verify, internal authenticated channel và backend resource authz.

**Bài 19 — Multi-region replay.** 10 replicas phân bố ở hai regions cùng nhận request HMAC hợp lệ của A với nonce N. So sánh `ConcurrentHashMap` local, Redis eventually replicated và shared atomic store dưới network partition.

**Bài 20 — Cache/revoke.** Một node đã biết key A bị revoke, node khác còn plaintext và state ACTIVE trong cache. Đưa ra phương án invalidate/short TTL/server-owned state version và test cutover.

**Bài 21 — Audit trust.** Phân biệt `claimedTenantId=B`, `macVerifiedOwnerTenantId=A`, `authenticatedTenantId=null` trong một event `TENANT_BINDING_DENIED`. Dashboard nào được phép đếm lượt authenticated của B?

**Bài 22 — Forensic.** Tenant A báo thấy order của B. Liệt kê nguồn chứng cứ từ gateway, HMAC verifier, key store, authorization, DB connection/RLS, cache, queue và business ledger. Những fields nào tuyệt đối không đưa vào ticket?

**Bài 23 — Rate-limit fairness.** A gửi hàng triệu requests sai MAC với `X-Tenant-Id=B`. Nếu quota theo claimed tenant, B bị ảnh hưởng ra sao? Thiết kế pre-auth và post-auth rate limits.

**Bài 24 — HMAC vs non-repudiation.** Verifier của API biết secret KA để tính expected tag. Một successful audit HMAC có chứng minh chỉ client A mới có thể tạo message không? Cần những cơ chế nào khi cần chứng cứ ký độc lập mạnh hơn?

**Bài 25 — Golden fixture.** Xây test vector độc lập gồm audience, tenant/client/key IDs, method/raw target, timestamp/nonce/request ID, raw body SHA-256, canonical UTF-8 LF bytes, test-only KA và expected full HMAC-256 tag. Kiểm negative test ký tenant B bằng KA đúng MAC nhưng binding deny.

### 15.2. Checklist trước triển khai production

| Nhóm kiểm tra | Điều cần chứng minh |
|---|---|
| **Tenant model** | Tenant ID khác client ID; mapping một/nhiều clients do server sở hữu |
| **Credential ownership** | Key record có immutable ownerTenantId, audience/client/key IDs và version |
| **Key material isolation** | Secret CSPRNG độc lập, không dùng global secret hoặc hash(tenantId) |
| **Key lookup** | Select exact tuple; không scan mọi secret, không fallback key |
| **Tenant binding** | MAC đúng **vẫn** phải match trusted owner hoặc delegated membership |
| **Canonical request** | Tenant, client, key, audience, method, raw URI/query, timestamp, nonce, request ID, body hash đều được ký |
| **Signature** | HMAC-SHA-256 full 32 bytes, strict 43-char Base64URL no-padding |
| **Key lifecycle** | ACTIVE/VERIFY_ONLY/REVOKED và server time/deadline, emergency invalidation |
| **Nonce** | Reserve sau MAC/tenant binding; atomic shared store và TTL phủ freshness interval |
| **Nonce namespace** | `(audience, verifiedTenant, authenticatedClient, nonce)`; không reset khi rotate key |
| **Idempotency** | Scoped per authenticated tenant/client, giữ logical operation qua retries |
| **Principal** | Created only after complete authn; tenant từ trusted record |
| **Delegation** | Cross-tenant access phải có trusted grant scope/action/expiry/audit |
| **Business authz** | Resource owner/action checks riêng, không tin raw body/path tenant |
| **Database** | Tenant-scoped queries, parameterization, RLS theo trusted context khi áp dụng |
| **Connection pool** | Tenant session/transaction state reset; test A→B reuse |
| **Cache** | Cache key theo verified tenant/resource/permission variant, an toàn khi invalidation |
| **Queues** | Trusted producer/consumer, immutable tenant context, authz recheck và DLQ privacy |
| **Object storage/search** | Tenant policies cho blobs, exports, vector search, analytics |
| **Gateway** | Reject duplicate signed fields, strip internal identity headers, preserve signed bytes |
| **Multi-region** | Revoke propagation, clock sync và cross-node nonce atomicity |
| **IAM/KMS** | Least privilege, tenant/audience/environment scoping, access audit |
| **Public errors** | Không tiết lộ secret/key/tenant existence qua 401/403, rate limits |
| **Audit** | Claimed vs MAC-verified vs authenticated tenant; no raw secret/tag/body |
| **Availability** | Noisy-neighbor fairness và bounded resource use cho pre-auth attempts |
| **QA** | Tenant spoofing signed-by-A, A→B BOLA, cache/RLS, rotation, replay, gateway |
| **Incident** | Revoke tenant-specific key, kiểm ảnh hưởng server-wide nếu KMS/workload lộ |

### 15.3. Tiêu chí chấp nhận cuối cùng

Một release chỉ nên được đánh giá tenant-isolated khi các kiểm thử **đồng thời** chứng minh:

- HMAC request A **không bao giờ** tạo authenticated principal B chỉ vì A đặt tenant claim B.
- Secret KB không bị sử dụng làm secret KA do key ID text trùng hoặc sai audience.
- Principal A không thể đọc/sửa order B qua **bất kỳ** route, query, export, cache, search hay async worker.
- Nonce/retry/idempotency isolation không tạo cross-tenant collision hoặc bypass khi key rotation.
- Key revocation được enforce ở mọi nodes trong policy SLA; không dùng key material cached để bypass.
- Gateway/backend trust boundary không cho client inject verified-tenant metadata.
- Security audit có đủ claims/outcomes/trusted owner mà không tiết lộ key/secret hoặc làm sai attribution.
- Negative tests được chạy qua production-like path, không chỉ unit tests trên helper HMAC.

## 16. Kết luận và tài liệu tham khảo

**Tenant isolation** trong HMAC request authentication không chỉ là “mỗi tenant có một shared secret”. Nền tảng an toàn phải ràng buộc **key record → owner tenant → authenticated principal**, ký tenant context trong canonical request và **vẫn kiểm membership** sau MAC. Người giữ secret của tenant A có thể tạo HMAC đúng cho mọi nội dung do họ chọn, nhưng họ **không được phép tự gán danh tính tenant B**.

Sau khi xác thực hoàn tất, hệ thống còn phải bảo đảm authorization cho từng action/resource, tenant-scoped SQL/RLS, cache keys, queue jobs, object storage, audit và quotas. Timestamp/nonce chống replay của **một request đã ký**, còn business idempotency chống side effect lặp; cả hai phải dùng **verified tenant/client** làm namespace theo policy. Key rotation và revocation phải có ownership/version rõ, không vượt qua được bằng cache stale hoặc một proxy header giả.

**Bài học then chốt:** Một request có thể **MAC đúng nhưng tenant binding sai**, hoặc **authentication đúng nhưng authorization sai**. Thiết kế và kiểm thử từng tầng độc lập mới phát hiện được cross-tenant vulnerabilities trước khi chạy production.

**Tài liệu tham khảo:**

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): nguyên lý HMAC với shared secret.
- [RFC 4231 — Test Vectors for HMAC-SHA-224/256/384/512](https://www.rfc-editor.org/rfc/rfc4231): known-answer vectors cho thuật toán.
- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): URI canonicalization và percent-encoding.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP method, fields, authentication/authorization semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): framing và intermediary behavior.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-headers và gateway protocol mapping.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): chuẩn ký HTTP riêng; `hmac-tenant-bound-v1` trong bài là **giao thức minh họa khác**.
- [RFC 4648 — Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL, canonical pad bits và no-padding contract.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF)](https://www.rfc-editor.org/rfc/rfc5869): khi kiến trúc yêu cầu KDF, cần domain separation và review.
- [NIST SP 800-57 Part 1 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): lifecycle, protection và key management.
- [OWASP API Security Top 10](https://owasp.org/API-Security/): Broken Object Level Authorization và API authorization risks.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, resource-level policy, least privilege.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ, cấp, rotate và audit secrets.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log injection, forensic logging và không lộ credential.
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, table owner/`BYPASSRLS` và `FORCE ROW LEVEL SECURITY`.
- [Java SE 17 — Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): JCA `HmacSHA256`, `init` và `doFinal`.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 và `isEqual` so binary tags.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): secrets/nonces ngẫu nhiên.
- [Java SE 17 — Base64](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html): URL-safe encoding/decoding.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): injected UTC/fixed clock cho tests.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `compute` atomic trong một JVM, không thay distributed nonce store.
- [Redis — SET command](https://redis.io/docs/latest/commands/set/): `NX`/`EX`/`PX` khi implement atomic nonce reservation.











