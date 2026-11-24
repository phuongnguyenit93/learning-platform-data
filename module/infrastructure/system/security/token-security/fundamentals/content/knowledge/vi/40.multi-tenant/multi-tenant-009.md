# Cache validation theo tenant trong hệ thống bảo mật token

## 1. Vì sao cache phải hiểu tenant?

Trong hệ thống multi-tenant, nhiều tổ chức cùng sử dụng một nền tảng và có thể gọi chung một API. Ví dụ Tenant A và Tenant B đều truy cập Orders API, nhưng dữ liệu, người dùng, quyền, cấu hình và chính sách bảo mật của họ phải được cô lập. Access token hợp lệ của người dùng thuộc Tenant A không được trở thành credential truy cập dữ liệu Tenant B chỉ vì hai tenant dùng chung issuer, client hoặc endpoint.

Cache giúp giảm độ trễ khi xác minh token, tra cứu membership, tải chính sách và tính quyền truy cập. Tuy nhiên, nếu cache không gắn kết quả với **tenant đã được xác minh**, một kết quả hợp lệ ở Tenant A có thể bị tái sử dụng ở Tenant B. Đây là dạng *cross-tenant cache confusion* có thể dẫn đến lộ dữ liệu hoặc vượt quyền.

Ví dụ, ứng dụng lưu quyết định `user-123 có quyền orders:read` với cache key chỉ là `user-123`. Người dùng có cùng định danh nội bộ ở Tenant A và Tenant B, hoặc cùng một service account được dùng trong nhiều tenant. Nếu cache hit không kiểm tra tenant, API có thể áp dụng quyền của tenant này cho tenant khác.

Bài học tập trung vào **cache validation theo tenant** trong vòng đời token: xác định tenant từ nguồn tin cậy, kiểm tra token và tenant binding, thiết kế cache key, cache JWT/JWKS/introspection, cache quyền, invalidation và kiểm thử chống truy cập chéo tenant.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Tenant** | Ranh giới tổ chức/khách hàng và dữ liệu trong hệ thống | `tenant-01` |
| **Tenant context** | Tenant đã được xác định và xác minh cho request hiện tại | `tenantId=tenant-01` |
| **Tenant claim** | Claim trong token thể hiện tenant hoặc tổ chức liên quan, theo hợp đồng issuer | `tid=tenant-01` |
| **Subject** | Chủ thể mà token đại diện | `sub=user-123` |
| **Client/workload** | Ứng dụng hoặc service đã xin token | `client_id=orders-service` |
| **Issuer** | Authorization Server phát hành token | `iss=https://auth.example.test` |
| **Audience** | Resource/API được phép nhận token | `aud=api://orders` |
| **Scope/permission** | Loại thao tác hoặc quyền được cấp | `orders:read` |
| **Membership** | Quan hệ user/service thuộc tenant nào và trạng thái của quan hệ đó | Alice là member Tenant A |
| **Policy version** | Phiên bản chính sách dùng để ra quyết định truy cập | `policyVersion=42` |

Không được đồng nhất `sub`, `client_id` và `tenant_id`. `sub` trả lời token đại diện cho ai; `client_id` cho biết OAuth client; tenant claim hoặc tenant binding xác định ngữ cảnh tổ chức theo hợp đồng của hệ thống. Một người có thể là thành viên nhiều tenant, một workload có thể được ủy quyền cho một số tenant, và cùng một API có thể phục vụ nhiều tenant.

**Tenant context không tự trở thành bằng chứng xác thực chỉ vì nó xuất hiện trong URL, hostname hoặc header.** Nó cần được xác định qua cấu hình định tuyến đáng tin cậy và ràng buộc với token/membership/policy đã xác minh.

## 3. Quy trình xác định tenant và xác thực token

### 3.1. Tenant đến từ đâu?

Các hệ thống thường nhận gợi ý tenant từ một trong các nguồn:

- **Subdomain/custom domain:** `tenant-a.api.example.test`, hoặc domain riêng đã được xác minh và ánh xạ tới tenant canonical.
- **Path:** `/tenants/tenant-a/orders`; giá trị path là input cần xác minh membership và quyền.
- **Header:** `X-Tenant-ID`; đây là dữ liệu client gửi, không tự đáng tin.
- **Claim của access token:** ví dụ claim tùy biến `tid`, `tenant_id` hoặc cấu trúc tổ chức do issuer định nghĩa.
- **Service/workload configuration:** service account được gán tenant hoặc tập tenant trong policy do hệ thống quản trị kiểm soát.

Nên dùng resolver để ánh xạ input thành **canonical tenant ID** trong hệ thống. Nếu domain, path và token cùng cung cấp tenant, phải kiểm tra chúng nhất quán. Nếu xung đột, từ chối request hoặc yêu cầu xác thực lại theo flow đã thiết kế; không chọn nguồn “tiện nhất”.

Ví dụ request:

```http
GET /orders/42 HTTP/1.1
Host: tenant-a.api.example.test
Authorization: Bearer <access-token>
X-Tenant-ID: tenant-a
```

`Host` và `X-Tenant-ID` chỉ là tín hiệu định tuyến. Gateway/backend phải xác minh host đã được cấu hình, loại bỏ header tenant giả mạo từ proxy không tin cậy và so khớp tenant với claim/membership theo policy. Nếu ứng dụng cho phép người dùng chuyển tenant, thao tác chuyển tenant cần xác minh họ thực sự là member và được phép truy cập tenant đích.

### 3.2. Trình tự xác minh

Một trình tự khái niệm:

1. **Chuẩn hóa route/host:** chọn tenant từ domain/path đã được cấu hình, kiểm tra proxy và header forwarding.
2. **Xác thực token:** kiểm chữ ký JWT bằng khóa từ issuer tin cậy hoặc introspection opaque token; kiểm thuật toán, `iss`, `exp`, `nbf`, token type.
3. **Kiểm audience:** token phải dành cho API/resource hiện tại.
4. **Kiểm tenant binding:** tenant trong token, issuer-to-tenant mapping hoặc quan hệ membership được xác minh phải phù hợp với tenant context của request.
5. **Kiểm chủ thể/client:** subject hoặc workload phải còn hoạt động và có quan hệ hợp lệ với tenant.
6. **Kiểm scope và quyền:** scope chỉ là một phần của quyết định; cần kiểm permission, role, resource ownership và tenant boundary.
7. **Kiểm sender constraint:** nếu token gắn mTLS/DPoP, xác minh bằng chứng sở hữu khóa theo yêu cầu.
8. **Chỉ sau các bước cần thiết mới đọc/ghi cache authorization decision** bằng cache key bao gồm tenant và phiên bản policy phù hợp.

Không dùng cache hit để bỏ qua bước xác định tenant. Có thể cache một số kết quả mật mã hoặc introspection, nhưng vẫn phải so khớp kết quả đó với tenant context của request hiện tại.

### 3.3. Token minh họa

JWT access token có thể mang claim tenant tùy profile và hợp đồng issuer:

```json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "api://orders",
  "client_id": "web-portal",
  "tid": "tenant-01",
  "scope": "orders:read",
  "iat": 1795000000,
  "exp": 1795000600
}
```

`tid` trong ví dụ là **custom claim**, không phải claim chuẩn bắt buộc của mọi JWT/OAuth provider. Một số hệ thống dùng `tenant_id`, claim dạng object hoặc issuer riêng theo tenant. Resource server phải theo hợp đồng đã thống nhất; không tự đoán tên claim hoặc coi token thiếu `tid` là token toàn tenant.

Nếu AS phát hành issuer riêng cho mỗi tenant, tenant có thể được xác định từ issuer mapping đã cấu hình. Nếu AS dùng issuer chung, cần một claim hoặc cơ chế binding được xác minh để phân biệt tenant. Dù dùng mô hình nào, phải kiểm cả issuer, audience và quyền.

## 4. Phân biệt các loại cache liên quan

Trong một request multi-tenant, có nhiều cache khác nhau. Chúng không nên dùng chung một key hoặc TTL:

| Cache | Nội dung | Phạm vi khóa chính |
| --- | --- | --- |
| **JWKS/public-key cache** | Public key và metadata khóa của issuer | Issuer + JWKS URI/key ID theo hợp đồng tin cậy |
| **Introspection cache** | Kết quả `active`, scope, audience, metadata token | Issuer/AS + fingerprint token; lưu kèm tenant binding đã xác minh nếu có |
| **Access-token cache** | Access token mà OAuth client dùng gọi resource | Issuer + client/principal + audience + scope + tenant/security context + binding |
| **Tenant configuration cache** | Domain mapping, trạng thái tenant, feature/security configuration | Canonical tenant ID + config version |
| **Membership cache** | Quan hệ subject/workload với tenant, trạng thái member | Tenant ID + issuer + subject/client + membership version |
| **Authorization decision cache** | Quyết định cho phép/từ chối một hành động trên resource | Tenant + subject + actor/client + action + resource + policy version |
| **Revocation/denylist cache** | Trạng thái token/credential đã bị thu hồi hoặc chặn | Issuer + token identifier/fingerprint hoặc credential ID |

Ví dụ: JWKS cache có thể dùng chung cho nhiều tenant nếu họ thực sự cùng một issuer/key set và trust policy cho phép. Nhưng kết quả membership của Alice ở Tenant A không thể dùng chung cho Tenant B. Ngược lại, nếu mỗi tenant có issuer hoặc JWKS URI riêng, key cache cũng phải tách theo issuer/URI; không lấy khóa của issuer A để xác minh token issuer B.

**Cache không phải một vùng dữ liệu trung lập.** Mỗi cache cần xác định ai tạo entry, điều kiện để entry được đọc, tenant binding của value, thời gian tồn tại và cách invalidation.

## 5. Thiết kế cache key không gây rò rỉ chéo tenant

### 5.1. Cache key phải chứa tenant đã được xác minh

Ví dụ key cho quyết định quyền:

```text
AuthorizationDecisionKey = (
  canonicalTenantId,
  issuer,
  subject,
  actorOrClientId,
  action,
  resourceType,
  resourceId,
  normalizedScopeSet,
  membershipVersion,
  policyVersion
)
```

Key cho access token:

```text
AccessTokenKey = (
  authorizationServer,
  clientId,
  credentialVersion,
  grantType,
  canonicalTenantId,
  resourceOrAudience,
  normalizedScopeSet,
  tokenBindingKeyId
)
```

Các trường có thể thay đổi theo hệ thống, nhưng phải giữ các yếu tố làm thay đổi quyền hiệu lực. Đặc biệt:

- Dùng **canonical tenant ID** từ resolver đã xác minh, không dùng chuỗi header thô.
- Phân biệt issuer và subject: cùng chuỗi `sub=user-123` từ hai issuer khác nhau không nhất thiết là cùng principal.
- Tách client/workload và subject nếu quyết định phụ thuộc cả hai.
- Gắn audience/resource và scope để không dùng token của API này cho API khác.
- Gắn membership/policy version hoặc một phiên bản invalidation để quyền thay đổi làm cache cũ mất hiệu lực.
- Gắn key/certificate ID khi token có sender constraint.
- Chuẩn hóa scope set ổn định nhưng không tự mở rộng quyền.

### 5.2. Ví dụ lỗi cache chỉ theo user ID

```java
// Sai: tenant không nằm trong key.
String key = "permission:" + subjectId;
PermissionDecision decision = cache.get(key);
```

Nếu `user-123` là member của hai tenant, quyết định cho Tenant A có thể được dùng khi request đến Tenant B.

Thiết kế đúng phải bind tenant và policy:

```java
// Pseudocode: tenantId phải là canonical ID đã được xác minh.
String key = String.join(":",
    "permission",
    tenantContext.canonicalId(),
    verifiedPrincipal.issuer(),
    verifiedPrincipal.subject(),
    action,
    resourceType,
    resourceId,
    policyVersion
);
PermissionDecision decision = cache.get(key);
```

Chỉ thêm tenant vào key là chưa đủ nếu `tenantContext` được lấy trực tiếp từ header không tin cậy. Trình tự bắt buộc là **resolve + verify tenant context trước, rồi mới dùng nó tạo key**. Value trong cache cũng nên lưu `tenantId`, `policyVersion` và thời điểm tạo; khi cache hit, kiểm tra chúng khớp request hiện tại.

### 5.3. Không dùng bearer token nguyên văn làm cache key/log

Với introspection cache, có thể dùng fingerprint một chiều của token, chẳng hạn HMAC-SHA-256 bằng khóa nội bộ được bảo vệ, thay vì đưa token nguyên văn vào key/log. HMAC fingerprint giảm nguy cơ token bị lộ qua hệ thống quan sát hoặc giao diện cache. Cache value phải lưu issuer/AS, trạng thái, audience, scope, expiry và tenant binding theo hợp đồng.

Không coi fingerprint là token mới hay bằng chứng xác thực độc lập. Nó chỉ là khóa định vị entry; token vẫn phải được xác minh theo đúng cơ chế và context.

## 6. Tenant validation khi dùng JWT và opaque token

### 6.1. JWT access token

Với JWT, API có thể xác minh chữ ký offline bằng JWKS, sau đó kiểm claims. Quy trình tenant-aware nên gồm:

- Chọn issuer từ allowlist hoặc trust configuration đã được thiết lập; không tải JWKS URL tùy ý từ claim chưa xác minh.
- Xác minh thuật toán/chữ ký, `iss`, `aud`, `exp`, `nbf`, token type/profile.
- Đọc tenant claim từ token **sau khi chữ ký hợp lệ**; đối chiếu với canonical tenant context.
- Kiểm membership/tenant status và scope/quyền.
- Nếu cùng issuer phát token cho nhiều tenant, yêu cầu claim/binding đủ rõ để xác định tenant; không coi issuer chung là bằng chứng user thuộc mọi tenant.

Một JWT có `tid=tenant-A` nhưng request được định tuyến tới Tenant B phải bị từ chối, dù chữ ký hợp lệ và token còn hạn. Tương tự, token không có claim tenant không được mặc định dùng cho tenant nào trừ khi hợp đồng issuer định nghĩa rõ cách xác định khác.

### 6.2. Opaque access token và introspection

Opaque token không cho phép API tự đọc tenant claim từ chuỗi token. Resource server có thể gọi introspection endpoint (RFC 7662) để lấy `active`, scope, audience và metadata được AS công bố. Sau đó API kiểm tenant binding theo kết quả introspection và tenant resolver.

Nếu introspection chỉ trả `active=true` nhưng không có tenant claim, membership hoặc cơ chế xác minh tenant tương đương, **không thể suy ra token thuộc tenant hiện tại**. Cần bổ sung contract với AS hoặc tra membership bằng nguồn tin cậy trước khi cho phép.

Cache introspection cần key tách theo AS/issuer và fingerprint token; cache value có thể chứa tenant binding đã xác minh. Khi cùng token được gửi trong request tenant khác, không dùng kết quả `active=true` để bỏ qua bước tenant check.

### 6.3. Issuer riêng theo tenant và issuer dùng chung

| Mô hình | Cách xác định tenant | Điều cần kiểm |
| --- | --- | --- |
| Issuer riêng mỗi tenant | Ánh xạ issuer canonical → tenant từ trust configuration | Issuer đúng allowlist, key set đúng, audience và trạng thái tenant |
| Issuer chung, token có tenant claim | Claim tenant đã ký trong access token | Claim đúng schema, tenant tồn tại/active, request context khớp |
| Issuer chung, tenant membership tra riêng | Subject + issuer tra membership trong tenant đã resolve | Membership active, role/permission và policy version |
| Workload dùng được nhiều tenant | Workload identity + danh sách tenant được ủy quyền | Request tenant nằm trong allowlist/authorization của workload; không lấy tenant tùy ý từ client |

Không dùng issuer hostname để suy tenant bằng phép cắt chuỗi hoặc quy tắc dễ bị giả mạo. Dùng mapping được quản trị và có version.

## 7. Cache membership và authorization decision

### 7.1. Membership không đồng nghĩa permission

Một user có thể là member Tenant A nhưng chỉ được đọc báo cáo, không được xem đơn hàng. Membership trả lời “principal có thuộc tenant này và còn hoạt động không?”; authorization decision trả lời “principal có được thực hiện hành động này trên resource này không?”.

Do đó, nên tách:

- **Tenant membership cache:** principal, tenant, trạng thái member, vai trò nền và membership version.
- **Permission/decision cache:** principal, actor, action, resource, tenant, policy version và kết quả allow/deny.
- **Resource ownership cache (nếu có):** quan hệ tài nguyên với tenant; không được suy ownership chỉ từ ID.

Một decision cache key chỉ có `(tenant, subject, action)` có thể vẫn thiếu `resourceId` hoặc resource version nếu quyền phụ thuộc vào từng bản ghi. Ví dụ Alice được đọc Order 42 nhưng không được đọc Order 99; cache theo action `orders:read` chung có thể cấp quyền quá rộng.

### 7.2. Ví dụ quyết định

Giả sử Alice thuộc Tenant A và Tenant B:

- Tenant A: Alice có `orders:read` với Order 42.
- Tenant B: Alice chỉ có `reports:read`.
- Request 1 đọc Order 42 ở Tenant A: policy cho phép.
- Request 2 đọc Order 42 ở Tenant B: phải kiểm membership, resource ownership và policy Tenant B; kết quả của Tenant A không được tái sử dụng.

Cache decision cần key tối thiểu phân biệt hai tenant và resource:

```text
(tenant-A, issuer-X, alice, orders:read, order-42, policy-v7) -> ALLOW
(tenant-B, issuer-X, alice, orders:read, order-42, policy-v3) -> DENY
```

Không nên cache `ALLOW` quá lâu khi quyền có thể thay đổi nhanh. Negative decision `DENY` cũng cần TTL và invalidation hợp lý: nếu user vừa được cấp quyền, cache deny cũ không nên khiến họ bị khóa ngoài quá lâu.

## 8. TTL, stale data và invalidation theo tenant

Thời hạn cache cần gắn với nguồn dữ liệu và yêu cầu thu hồi. Một entry chỉ nên được dùng tới thời điểm sớm nhất trong các giới hạn liên quan:

```text
usableUntil = min(
    tokenExpiry,
    introspectionFreshUntil,
    membershipFreshUntil,
    policyFreshUntil,
    tenantConfigFreshUntil
)
```

Đây là mô hình tư duy; không phải mọi cache entry đều có đủ các mốc trên. Nếu một loại cache chỉ lưu JWKS, thời hạn và refresh policy theo metadata khóa; nếu là authorization decision, TTL phải tính đến membership, policy và resource state.

Các sự kiện cần invalidation hoặc bump version:

| Sự kiện | Cache cần xem xét |
| --- | --- |
| Tenant bị khóa, xóa hoặc chuyển trạng thái | Tenant configuration, membership, authorization decision, token acceptance policy |
| User bị xóa/khóa khỏi tenant | Membership và decision của subject trong tenant đó |
| User đổi role/permission | Membership/role và authorization decision |
| Resource chuyển tenant hoặc đổi owner | Resource ownership và decision liên quan |
| Policy thay đổi | Decision cache theo policy version |
| Client secret/private key/certificate bị rotate hoặc thu hồi | Credential state, token acquisition cache, trust/binding state |
| Token bị thu hồi hoặc phát hiện replay | Introspection/revocation cache và access-token cache theo token |
| Issuer đổi signing key/JWKS | JWKS cache và trạng thái xác minh token theo chính sách |
| Tenant domain được chuyển/đổi | Domain-to-tenant mapping cache và route resolver |

**JWT offline validation có thể không phát hiện thu hồi ngay lập tức.** Nếu tenant bị đình chỉ hoặc user bị gỡ membership, resource server phải có cơ chế kiểm trạng thái/membership/policy đủ mới, introspection/denylist nếu cần hoặc access token ngắn hạn. Không để cache allow kéo dài hơn cửa sổ thu hồi mà tổ chức chấp nhận.

Khi invalidation message bị mất, dùng TTL tối đa và version check như lớp dự phòng. Với dữ liệu quan trọng, có thể kiểm policy version hiện tại hoặc membership version từ nguồn có độ tin cậy cao trước thao tác nhạy cảm.

## 9. Multi-tenant và cache phân tán

Một Redis hoặc distributed cache có thể được chia sẻ giữa nhiều service/tenant. Cần thiết kế:

1. **Namespace:** key có prefix hệ thống và tenant canonical ID, ví dụ `prod:authz:tenant-01:...`.
2. **ACL:** workload chỉ được truy cập namespace/key pattern cần thiết; không cho tenant tự chọn key hoặc đọc namespace khác.
3. **Encryption:** bảo vệ dữ liệu nhạy cảm khi truyền/lưu; quản lý khóa mã hóa và rotation.
4. **Data minimization:** cache claims tối thiểu; tránh lưu token nguyên văn, PII hoặc dữ liệu nghiệp vụ không cần thiết.
5. **Tenant binding trong value:** lưu tenant ID, issuer, version và expiry để kiểm tra lại khi hit.
6. **Eviction/invalidation:** có cơ chế xóa hoặc bump version theo tenant mà không xóa nhầm dữ liệu tenant khác.
7. **Concurrency:** single-flight/lock theo cache key đầy đủ, không khóa chung tất cả tenant hoặc chỉ theo subject.
8. **Observability:** log tenant ID dạng canonical/đã giảm nhạy cảm, cache hit/miss và decision code; không log token.

Namespace chỉ hỗ trợ phân vùng, không thay thế authorization. Nếu service có quyền đọc mọi key Redis, một bug trong code vẫn có thể truy cập entry tenant khác. ACL/network isolation và kiểm tra tenant binding trong ứng dụng đều cần thiết.

Không dùng cache key do client gửi trực tiếp. Nếu key chứa tenant từ header chưa xác minh, attacker có thể điều khiển lookup tới namespace của tenant khác hoặc tạo nhiều key rác gây cache exhaustion (*cache pollution*).

## 10. Chống cache poisoning, tenant confusion và enumeration

### 10.1. Cache poisoning

Attacker gửi tenant ID không tồn tại hoặc tenant alias không chuẩn hóa để tạo nhiều entry, hoặc lợi dụng host/header forwarding để ánh xạ nhầm domain. Biện pháp:

- Chỉ cache sau khi tenant resolver xác minh tenant tồn tại và trạng thái cho phép.
- Chuẩn hóa domain/ID theo một quy tắc duy nhất; xử lý Unicode/IDN, chữ hoa/thường, trailing dot, port và percent-encoding.
- Không tin `X-Forwarded-Host` từ proxy ngoài allowlist.
- Giới hạn kích thước cache, số tenant key trên principal, TTL và tốc độ tạo context.
- Dùng allowlist cho issuer, resource/audience và tenant routing.

### 10.2. Cross-tenant cache confusion

Kịch bản: API cache `ALLOW` theo `sub` và scope; Alice có quyền ở Tenant A. Attacker chuyển header `X-Tenant-ID` sang Tenant B, khiến API lấy lại `ALLOW` cũ. Giải pháp là xác minh tenant trước lookup, key bao gồm tenant/resource/policy version, và value được kiểm binding khi cache hit.

### 10.3. Tenant enumeration

Thông báo khác biệt quá rõ giữa “tenant không tồn tại”, “tenant bị khóa” và “user không phải member” có thể giúp attacker dò danh sách khách hàng. Cần response/error mapping và rate limit phù hợp; log nội bộ vẫn giữ mã lý do chi tiết để điều tra. Không tiết lộ token, membership hoặc dữ liệu tenant khác qua error response.

### 10.4. Cache stampede và denial of service

Khi tenant lớn hết hạn cache cùng lúc, nhiều request có thể đồng thời gọi AS hoặc membership service. Dùng single-flight theo key đầy đủ, jitter, timeout, bounded concurrency, backoff và rate limiting. Không dùng một lock toàn cục gây ảnh hưởng mọi tenant, cũng không cho tenant riêng chiếm toàn bộ tài nguyên cache.

## 11. Pseudocode tenant-aware validation

Đoạn Java sau minh họa thứ tự xử lý; các interface là thành phần giả định, không phải API của một thư viện cụ thể:

```java
TenantContext tenant = tenantResolver.resolveAndVerify(request);
// Chỉ trả canonical ID từ host/path/config được tin cậy.

VerifiedToken token = tokenVerifier.verify(
    request.bearerToken(),
    trustedIssuers,
    expectedAudience
);

if (!token.isValidAt(clock.instant())) {
    throw new InvalidTokenException();
}

if (!tenantBinding.matches(token, tenant)) {
    throw new InvalidTenantContextException();
}

VerifiedPrincipal principal = principalMapper.from(token);

MembershipKey membershipKey = new MembershipKey(
    tenant.canonicalId(),
    token.issuer(),
    principal.subject()
);

Membership membership = membershipCache.getOrLoad(
    membershipKey,
    membershipService::loadAndVerify
);

if (!membership.isActive()) {
    throw new AccessDeniedException();
}

AuthorizationKey decisionKey = new AuthorizationKey(
    tenant.canonicalId(),
    token.issuer(),
    principal.subject(),
    principal.actor(),
    request.action(),
    request.resourceType(),
    request.resourceId(),
    policyVersion.current(tenant)
);

Decision decision = authorizationCache.getOrLoad(
    decisionKey,
    () -> policyEngine.evaluate(tenant, principal, request)
);

if (!decision.allowed()) {
    throw new AccessDeniedException();
}

return businessService.execute(tenant, principal, request);
```

Các điểm quan trọng:

- `tenantResolver` xác minh và trả canonical tenant context; không trả nguyên header.
- `tokenVerifier` xác thực token trước khi đọc claims.
- `tenantBinding` đối chiếu token với tenant context theo hợp đồng issuer.
- Membership cache và authorization cache có key riêng, bao gồm tenant.
- `policyVersion` giúp tránh dùng quyết định cũ sau khi policy thay đổi.
- `businessService` nhận tenant context đã xác minh và phải áp dụng tenant filter khi truy vấn dữ liệu.

Nếu token không có tenant claim nhưng hệ thống dùng issuer riêng theo tenant hoặc membership lookup, `tenantBinding` phải triển khai đúng mô hình đó. Không tự tạo claim giả hoặc mặc định tenant từ `sub`.

## 12. HTTP response và ranh giới phân quyền

Một số tình huống thường gặp:

| Tình huống | Phản hồi thường dùng | Giải thích |
| --- | --- | --- |
| Token thiếu, sai chữ ký, hết hạn, sai issuer/audience | `401 Unauthorized` | Credential không được chấp nhận |
| Token hợp lệ nhưng tenant context xung đột với tenant binding | Thường từ chối như `403` hoặc lỗi xác thực theo contract | Không cho phép chuyển token sang tenant khác |
| Subject không còn membership trong tenant | `403 Forbidden` hoặc response tổng quát theo chính sách | Danh tính có thể hợp lệ nhưng không có quyền trong tenant |
| Scope không đủ | `403 Forbidden` (`insufficient_scope` khi phù hợp) | Token không được cấp quyền thao tác |
| Tenant bị khóa | Response tổng quát theo policy, thường từ chối | Không tiết lộ trạng thái tenant cho caller không có quyền |
| Resource thuộc tenant khác | Từ chối và tránh lộ resource existence | Không để ID đoán được vượt tenant boundary |

Không có một status code bắt buộc duy nhất cho mọi thiết kế tenant binding. Điều quan trọng là thống nhất hợp đồng, không tiết lộ thông tin nhạy cảm và không để cache hit làm thay đổi kết quả phân quyền.

## 13. Kịch bản kiểm thử cache validation theo tenant

| Test | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| T1 | Token `tid=tenant-A`, request Tenant A | Có thể tiếp tục nếu issuer, audience, membership và quyền hợp lệ |
| T2 | Token `tid=tenant-A`, request Tenant B | Bị từ chối tenant mismatch |
| T3 | Cùng `sub=user-123` ở hai tenant, quyền khác nhau | Cache entry tách theo tenant; không rò quyền |
| T4 | Cùng client ID nhưng audience Ledger và Orders | Token cache tách theo audience/resource |
| T5 | Cùng issuer, hai subject trùng chuỗi nhưng principal khác tenant | Không dùng nhầm membership/decision |
| T6 | Header `X-Tenant-ID` bị client giả mạo | Resolver xác minh hoặc từ chối; header không tự tạo tenant context |
| T7 | Host tenant alias không nằm allowlist | Không tạo cache entry và không định tuyến nhầm |
| T8 | Token JWT chữ ký hợp lệ nhưng sai audience | Resource server từ chối |
| T9 | Opaque token introspection `active=true` nhưng không xác minh tenant binding | Không suy tenant; yêu cầu contract/lookup tin cậy |
| T10 | Tenant bị khóa sau khi có cache allow | Invalidation/version/TTL làm quyết định cũ không còn được dùng theo SLA |
| T11 | User bị gỡ khỏi tenant | Membership/decision cache bị invalidated hoặc hết hạn đúng giới hạn |
| T12 | Policy version tăng | Cache decision version cũ không được sử dụng |
| T13 | Resource chuyển từ Tenant A sang Tenant B | Ownership cache và authorization decision được cập nhật |
| T14 | JWKS key rotation của issuer A | Cache key/refresh đúng issuer; không dùng key set của issuer B |
| T15 | Token mTLS/DPoP bound với khóa A được dùng bằng khóa B | Request bị từ chối |
| T16 | Nhiều request đồng thời cho một tenant cache miss | Single-flight theo key, không gây stampede toàn cụm |
| T17 | Attacker gửi hàng loạt tenant ID ngẫu nhiên | Rate limit/size limit ngăn cache pollution và tenant enumeration |
| T18 | Distributed cache trả value có tenant ID khác key | Ứng dụng phát hiện binding mismatch và từ chối |
| T19 | Tenant A có `ALLOW`, Tenant B có `DENY` cho cùng subject/resource/action | Kết quả B vẫn là DENY; không tái sử dụng ALLOW của A |
| T20 | Introspection result cũ `active=true`, token đã bị thu hồi | Cache freshness/revocation policy giới hạn cửa sổ chấp nhận |

Nên chạy test với cả JWT và opaque token, issuer chung và issuer riêng theo tenant, một user thuộc nhiều tenant, workload dùng nhiều tenant, tenant bị đình chỉ, và request đi thẳng tới backend bỏ qua Gateway. Cần kiểm cả log/cache dashboard để chắc chắn không có bearer token hoặc dữ liệu tenant khác bị lộ.

## 14. Ghi nhớ và tài liệu tham khảo

**Cache validation theo tenant là một phần của authorization boundary.** Tenant phải được xác định từ nguồn đã xác minh; token phải đúng issuer, audience, hạn và tenant binding; membership và quyền phải được kiểm theo tenant/resource cụ thể. Mọi cache có thể ảnh hưởng quyết định bảo mật đều cần key/value gắn với tenant canonical, issuer/principal, audience/scope và policy version phù hợp. Khi tenant, membership, credential hoặc policy thay đổi, cache phải được invalidated hoặc hết hiệu lực trong cửa sổ đã chấp nhận.

Không dùng một cache key chỉ theo `sub`, `client_id` hoặc scope; không tin tenant header do client tự gửi; không dùng token hợp lệ ở Tenant A cho Tenant B; và không để cache allow cũ vượt qua cơ chế thu hồi quyền.

Tài liệu chuẩn và hướng dẫn nên đối chiếu:

- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): claims `iss`, `sub`, `aud`, `exp` và cấu trúc JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh issuer/audience và tránh nhầm ngữ cảnh token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile access token JWT và kiểm tra ở resource server.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái `active` và metadata của opaque token.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền Bearer token và xử lý lỗi.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): ràng buộc token với chứng chỉ.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token và giảm replay.
- [OWASP Multi-Tenant Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html): các thực hành cô lập tenant và kiểm soát truy cập đa tenant.
