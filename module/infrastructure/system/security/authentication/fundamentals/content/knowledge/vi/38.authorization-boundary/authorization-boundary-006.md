# Tenant context — Xác định và bảo vệ ngữ cảnh tenant trong authorization
 
> **Chương:** Authorization boundary  
> **Chủ đề:** Tenant context

**Tenant context** là ngữ cảnh xác định tổ chức hoặc không gian dữ liệu mà một request đang thao tác, ví dụ trường học, doanh nghiệp, khách hàng SaaS hoặc workspace. Trong hệ thống multi-tenant, cùng một người dùng có thể là giảng viên ở tenant A, học viên ở tenant B và không có quyền ở tenant C. Vì vậy, xác thực thành công chỉ cho biết principal là ai; hệ thống vẫn phải xác định tenant đang được chọn, kiểm tra membership và đánh giá quyền trong đúng phạm vi đó.

Tenant context là một phần của ranh giới authorization. Nếu server tin tenant ID do client gửi mà không kiểm tra membership, hoặc lấy tenant từ một claim cũ nhưng không xác minh issuer/audience/scope, attacker có thể truy cập dữ liệu tenant khác. Lỗi này thường xuất hiện dưới dạng cross-tenant access, insecure direct object reference (IDOR/BOLA), cache leakage, truy vấn database thiếu tenant predicate hoặc background job chạy sai tenant.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, tập trung vào mô hình hóa tenant context trong authorization, xác định nguồn tenant đáng tin cậy, truyền context an toàn giữa các tầng, cô lập dữ liệu và kiểm thử truy cập chéo tenant. Người học cần phân biệt principal identity, tenant membership, tenant selection và resource ownership; hiểu rằng tenant context không tự cấp quyền mà phải được kiểm tra cùng policy hiện hành.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích tenant context và vai trò của nó trong ranh giới authorization.
2. Phân biệt principal, tenant, membership, role, resource scope và tenant selection.
3. Thiết kế cách xác định tenant từ host, route, session hoặc token mà không tin dữ liệu client tùy ý.
4. Kiểm tra membership và quyền hiện tại mỗi khi truy cập tài nguyên tenant.
5. Ngăn cross-tenant IDOR/BOLA, confused deputy và tenant spoofing.
6. Truyền tenant context an toàn qua API gateway, service-to-service call, queue và background job.
7. Thiết kế tenant isolation cho database, cache, object storage, search index và analytics.
8. Xử lý account thuộc nhiều tenant, tenant switching, admin support và break-glass.
9. Xây dựng test plan cho tenant boundary, stale token, cache poisoning và race condition.

## 2. Tenant context là gì?

Tenant là một phạm vi quản lý độc lập trong ứng dụng dùng chung hạ tầng. Tùy sản phẩm, tenant có thể là một trường, doanh nghiệp, khách hàng, workspace hoặc tổ chức. Tenant context cho biết request đang được xử lý trong phạm vi tenant nào.

Ví dụ:

- Một giảng viên có membership instructor tại trường A;
- Cùng người đó là học viên tại trường B;
- Người đó không có membership ở trường C;
- Một API request tới lớp học phải được xử lý trong tenant sở hữu lớp đó.

### 2.1. Tenant context không phải danh tính người dùng

Principal xác định ai đang gọi. Tenant context xác định phạm vi tổ chức mà request muốn tác động. Hai thông tin phải được kiểm tra riêng.

Một token có subject user-123 không có nghĩa user-123 được truy cập mọi tenant. Một request có tenant selector school-A cũng không chứng minh principal là thành viên trường A.

### 2.2. Tenant context không phải authorization decision

Tenant context giúp xác định scope. Authorization còn cần kiểm tra:

- Principal có account active không?
- Membership trong tenant còn hiệu lực không?
- Role/permission có cho phép action không?
- Resource có thuộc tenant đó không?
- Điều kiện bổ sung như department, assignment, ownership hoặc trạng thái resource có đạt không?

Không được xem việc chọn tenant thành công là đủ để cấp quyền.

## 3. Các thành phần của quyết định authorization

Một quyết định truy cập trong hệ thống multi-tenant thường cần ít nhất bốn nhóm dữ liệu:

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Principal** | Ai thực hiện request? | user-123 |
| **Tenant context** | Request đang ở phạm vi nào? | school-A |
| **Action** | Muốn làm gì? | grade:read |
| **Resource** | Đối tượng nào bị tác động? | class-42 / gradebook-7 |

Policy có thể bổ sung environment, device posture, thời điểm, risk signal và trạng thái account. Kết quả chỉ ALLOW khi mọi điều kiện bắt buộc đều đạt.

~~~mermaid
flowchart TD
    P["Principal đã xác thực"] --> C["Resolve tenant context"]
    C --> M["Kiểm tra membership"]
    M --> R["Resolve resource và tenant owner"]
    R --> A["Đánh giá action + role + policy"]
    A --> D{"Tất cả điều kiện đạt?"}
    D -->|"Có"| X["ALLOW trong đúng tenant"]
    D -->|"Không"| N["DENY"]
~~~

### 3.1. Invariant quan trọng

Với request tác động tới resource thuộc tenant T:

- Principal phải được xác thực;
- Tenant context phải là T;
- Principal phải có membership/ủy quyền hợp lệ trong T;
- Resource phải thực sự thuộc T;
- Role/permission phải cho phép action trên resource;
- Account và membership phải còn active tại thời điểm quyết định.

## 4. Tenant selection và tenant resolution

Người dùng có thể chủ động chọn tenant, nhưng server phải xác minh lựa chọn đó.

### 4.1. Các nguồn tenant thường gặp

- Hostname/subdomain, ví dụ school-a.example.com;
- URL path, ví dụ /tenants/school-a/...;
- Header do API gateway đáng tin cậy thiết lập;
- Tenant được chọn trong session server-side;
- Claim trong token do issuer tin cậy phát hành;
- Resource owner được tra cứu từ database;
- Context do service-to-service credential và policy xác định.

Mỗi nguồn có giới hạn. Host hoặc path có thể là lựa chọn của client; token claim có thể cũ; resource ID có thể bị thay đổi; header có thể bị giả mạo nếu gateway không xóa giá trị đầu vào. Không có một nguồn nào tự động đáng tin trong mọi kiến trúc.

### 4.2. Resolve tenant theo server-side policy

Một flow an toàn:

1. Xác thực request và xác định principal.
2. Lấy tenant selector từ nguồn đã định nghĩa.
3. Chuẩn hóa và resolve selector thành tenant record nội bộ.
4. Kiểm tra tenant tồn tại và trạng thái active.
5. Kiểm tra principal có membership/ủy quyền trong tenant.
6. Kiểm tra resource thuộc tenant khi request nhắm tới resource.
7. Đưa tenant context đã xác minh vào request context nội bộ.
8. Authorization policy quyết định action.

### 4.3. Không tin tenant ID từ body

Client có thể gửi tenant_id trong URL/body để chọn phạm vi. Server không được dùng giá trị này làm bằng chứng membership. Nếu request sửa tenant ID từ A sang B, server phải chạy lại resolve và membership check; không được tiếp tục dùng quyền đã kiểm tra cho A.

## 5. Hostname, subdomain và custom domain

SaaS có thể dùng subdomain riêng cho mỗi tenant hoặc custom domain do khách hàng cấu hình.

### 5.1. Subdomain resolution

Nếu school-a.example.com ánh xạ tới tenant A:

- Host phải được parse và canonicalize đúng;
- Chỉ tin Host/forwarded host từ proxy đã cấu hình;
- Chặn host không nằm trong domain registry;
- Tra cứu domain đã xác minh và tenant active;
- Không suy ra tenant chỉ bằng cách cắt chuỗi hostname;
- Kiểm tra TLS certificate và domain ownership theo quy trình.

Không dùng phép kiểm tra chuỗi kiểu host.endsWith("example.com") mà không xử lý ranh giới domain. Một hostname như example.com.attacker.invalid không thuộc example.com.

### 5.2. Custom domain

Custom domain cần gắn với tenant qua quy trình xác minh ownership, kiểm tra DNS/TLS và chống domain takeover. Khi domain bị gỡ hoặc hết hiệu lực, cache mapping phải được invalidated và request tới domain đó không được tự động tiếp tục trỏ vào tenant cũ.

### 5.3. Forwarded host

Ứng dụng sau reverse proxy có thể nhận Forwarded hoặc X-Forwarded-Host. Chỉ tin header do proxy nằm trong trust boundary tạo hoặc ghi đè. Proxy phải loại header do client tự gửi. Không để người dùng tự đặt forwarded host để chọn tenant khác.

## 6. Tenant context trong token và session

Token có thể chứa tenant claim, nhưng claim chỉ đáng tin sau khi token được xác minh và vẫn còn phù hợp với membership hiện tại.

### 6.1. JWT tenant claim

Một token có thể chứa:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "aud": "learning-api",
  "tenant_id": "school-a",
  "roles": ["instructor"],
  "iat": 1795334400,
  "exp": 1795338000
}
~~~

Đây là ví dụ minh họa. API phải xác minh chữ ký, issuer, audience, thời hạn và các claim cần thiết. Sau đó vẫn phải kiểm tra tenant membership và resource scope theo freshness policy. Claim tenant_id không tự chứng minh quyền trên mọi resource thuộc tenant đó.

### 6.2. Single-tenant token và multi-tenant token

Có thể thiết kế token gắn một tenant để giảm nhầm lẫn và giới hạn blast radius. Khi người dùng đổi tenant, ứng dụng tạo context/token mới sau khi xác minh membership.

Token chứa nhiều tenant/role có thể tiện, nhưng dễ lớn, khó revoke và có nguy cơ dùng nhầm scope. Nếu sử dụng, cần xác định rõ tenant đang active trong request và kiểm tra membership/permission tương ứng.

### 6.3. Session server-side

Một session có thể lưu tenant đã chọn. Khi tenant switching:

- Kiểm tra membership của tenant mới;
- Thay context server-side;
- Xoay session identifier hoặc cập nhật session version theo policy;
- Xóa cache/permission context cũ;
- Không để tab hoặc request song song sử dụng nhầm tenant;
- Ghi audit tenant switch nếu hành động nhạy cảm.

### 6.4. Stale claim và role change

Membership có thể bị thu hồi sau khi token phát hành. API cần TTL ngắn, introspection, authorization version hoặc truy vấn policy hiện tại cho hành động nhạy cảm. Refresh token không tự làm claim membership mới hơn nếu authorization server vẫn dùng dữ liệu cũ.

## 7. Membership và role trong tenant

Một principal có thể thuộc nhiều tenant với role khác nhau. Membership là quan hệ riêng, có trạng thái và vòng đời.

Ví dụ:

~~~text
Principal: user-123

Tenant school-A:
  membership: ACTIVE
  roles: [INSTRUCTOR]
  scope: [class-42, class-51]

Tenant school-B:
  membership: ACTIVE
  roles: [LEARNER]
  scope: [course-9]

Tenant school-C:
  membership: NONE
~~~

### 7.1. Membership state

Membership có thể là invited, pending, active, suspended, expired hoặc revoked. Chỉ trạng thái được policy cho phép mới có thể tham gia quyết định authorization.

### 7.2. Role scope

Role instructor ở tenant A không mặc nhiên áp dụng ở tenant B. Một role có thể bị giới hạn theo lớp học, department hoặc resource. Policy cần đánh giá effective permission, bao gồm quyền kế thừa và điều kiện ABAC.

### 7.3. Tenant owner/admin

Tenant administrator có quyền quản trị trong tenant cụ thể. Không được nhầm tenant admin với platform/global admin. Quyền global cần một role và approval path riêng, có blast radius lớn hơn.

## 8. Resource ownership và chống IDOR/BOLA

Lỗi phổ biến là server kiểm tra user đã đăng nhập nhưng không kiểm tra resource thuộc tenant nào.

Ví dụ nguy hiểm:

~~~http
GET /api/gradebooks/gradebook-900
Authorization: Bearer <valid-token>
~~~

Nếu API chỉ tải gradebook-900 theo ID mà không kiểm tra tenant owner và membership, user ở tenant A có thể đoán ID của tenant B và đọc dữ liệu.

### 8.1. Kiểm tra resource tenant

Một truy vấn an toàn cần kết hợp resource ID và tenant đã xác minh:

~~~sql
SELECT *
FROM gradebooks
WHERE id = :resource_id
  AND tenant_id = :verified_tenant_id;
~~~

Sau khi lấy resource, tiếp tục kiểm tra role/permission và scope. Không dùng tenant_id do request gửi làm verified_tenant_id.

### 8.2. Authorization tại service layer

Không chỉ kiểm tra trong controller hoặc frontend. Domain/service layer cần nhận một context đã xác minh và kiểm tra resource/action. Các đường gọi nội bộ, GraphQL resolver, export job và admin endpoint đều phải đi qua policy.

### 8.3. Trả lỗi an toàn

Với một số resource nhạy cảm, trả 404 thay vì tiết lộ resource có tồn tại ở tenant khác có thể giảm enumeration. Dù chọn 403 hay 404, không được để response body, timing hoặc metadata tiết lộ dữ liệu tenant khác.

## 9. Database isolation

Tenant isolation có thể được thực hiện bằng shared tables có tenant key, schema riêng hoặc database riêng. Mỗi lựa chọn có trade-off vận hành và rủi ro.

| Mô hình | Cách hoạt động | Điểm cần bảo vệ |
| --- | --- | --- |
| Shared database/shared schema | Mọi tenant dùng chung bảng, mỗi row có tenant_id | Mọi truy vấn phải có tenant predicate; RLS và constraint |
| Shared database/separate schema | Mỗi tenant có schema riêng | Schema routing, migration và connection pool |
| Separate database | Mỗi tenant có database riêng | Credential/database routing và vận hành nhiều DB |
| Hybrid | Tenant lớn có DB riêng, tenant nhỏ dùng shared | Policy nhất quán giữa các mô hình |

### 9.1. Tenant key và foreign key

Bảng multi-tenant nên lưu tenant ID và có constraint phù hợp. Với quan hệ giữa hai bảng, có thể dùng composite foreign key (tenant_id, parent_id) để ngăn record của tenant A tham chiếu parent thuộc tenant B.

### 9.2. Row-level security

Database RLS có thể cung cấp lớp bảo vệ bổ sung. Ứng dụng thiết lập tenant context trong transaction bằng cơ chế an toàn; policy RLS dùng giá trị đó để lọc row. Cần tránh connection pooling làm rò tenant context giữa request và không cho role ứng dụng bypass RLS ngoài chủ đích.

### 9.3. Query helper không đủ một mình

Repository helper tự động thêm tenant predicate giúp giảm lỗi, nhưng không thay thế constraint, RLS, review và test. Raw SQL, migration, admin query hoặc analytics pipeline có thể bỏ qua helper.

## 10. Cache, object storage và search index

Tenant isolation phải được giữ ở mọi nơi dữ liệu được lưu hoặc truy xuất.

### 10.1. Cache key

Cache key cần chứa tenant scope khi dữ liệu phụ thuộc tenant, ví dụ:

~~~text
tenant:school-A:gradebook:gradebook-900
~~~

Không dùng key chỉ theo resource ID nếu ID có thể trùng hoặc dữ liệu có scope tenant. Cache invalidation khi tenant membership/role thay đổi phải theo policy.

### 10.2. Shared cache và cache poisoning

Không cho client tự đặt namespace cache. Tenant context phải được xác minh trước khi tạo key. Nếu reverse proxy cache response theo URL nhưng bỏ qua tenant/session, dữ liệu riêng có thể bị phục vụ cho tenant khác.

### 10.3. Object storage

Object key/prefix nên gắn tenant reference, nhưng prefix không phải authorization. Dùng policy/bucket permission hoặc signed URL có scope, TTL và audience phù hợp. Không cho client tự chọn object path rồi coi path là bằng chứng quyền.

### 10.4. Search index và analytics

Search query cần filter tenant bắt buộc ở server, không phụ thuộc filter do client gửi. Export, reporting, data lake và analytics pipeline cũng cần giữ tenant lineage. Dữ liệu đã tổng hợp có thể vẫn nhạy cảm nếu có thể suy ra thông tin của tenant nhỏ.

## 11. Truyền tenant context giữa các service

Trong kiến trúc microservices, tenant context thường đi qua gateway, service-to-service call, event bus và background worker. Đây là ranh giới dễ bị giả mạo hoặc mất context.

### 11.1. Gateway

Gateway xác thực token và resolve tenant theo policy. Header nội bộ như X-Verified-Tenant chỉ được gateway tin cậy tạo sau khi loại bỏ header cùng tên do client gửi. Downstream service chỉ tin header này nếu kết nối và identity của gateway được xác thực, ví dụ mTLS hoặc workload identity.

### 11.2. Service-to-service

Khi service A gọi service B:
- Xác thực workload/service identity của A;
- Xác định tenant context từ request đã được xác minh;
- Kiểm tra service A được phép hành động thay mặt tenant đó;
- Truyền tenant context dưới dạng metadata được ký hoặc qua kênh nội bộ tin cậy;
- Service B vẫn kiểm tra scope và action theo policy của nó.

Không dùng một shared secret/header đơn giản mà mọi workload đều có thể tự đặt để giả tenant.

### 11.3. Delegation và confused deputy

Một service có quyền rộng có thể vô tình dùng quyền của chính nó để truy cập tài nguyên tenant khác theo yêu cầu của caller. Service phải phân biệt quyền workload của mình với quyền được ủy quyền từ principal gốc. Không để caller chọn tenant tùy ý rồi service dùng credential đặc quyền thực hiện.

### 11.4. Queue và event

Message nên mang tenant reference, principal/actor reference, purpose và correlation ID cần thiết. Consumer xác minh producer và kiểm tra tenant scope; không tin payload chỉ vì message nằm trong queue. Với event đến trễ, membership có thể đã thay đổi, nên action nhạy cảm cần kiểm tra trạng thái hiện tại khi xử lý.

## 12. Background job và scheduled task

Background job thường chạy sau khi request ban đầu kết thúc. Nếu job chỉ lưu resource ID mà không lưu tenant context, nó có thể truy cập sai tenant hoặc dùng quyền quá rộng.

Một job record nên gắn:
- Tenant reference đã xác minh;
- Actor/requester hoặc workload identity;
- Action/purpose;
- Resource references;
- Thời điểm tạo và hết hạn;
- Policy/authorization context cần tái kiểm tra;
- Correlation ID và idempotency key.

Khi job thực thi, kiểm tra tenant active, resource ownership và quyền hiện tại. Với export nhạy cảm, nếu actor đã mất membership trước khi job chạy, policy phải xác định hủy job hay yêu cầu approval mới.

## 13. Tenant switching an toàn

Một người dùng có thể chọn tenant khác từ menu. Đây là thay đổi context có ảnh hưởng tới mọi request sau đó.

### 13.1. Quy trình switching

1. Nhận tenant selector từ client.
2. Resolve selector thành tenant record.
3. Kiểm tra account active và membership của principal trong tenant.
4. Kiểm tra tenant active và không bị suspension.
5. Cập nhật server-side session/context hoặc phát token scope mới.
6. Xóa permission cache của tenant cũ.
7. Xác minh các request song song không dùng context lẫn lộn.
8. Ghi audit event và phản hồi tenant hiện tại.

### 13.2. Không chỉ đổi dropdown

Frontend đổi tên tenant không thay đổi authorization state. Mỗi API request phải mang hoặc tham chiếu context đã được xác minh; backend phải kiểm tra lại membership và resource scope.

### 13.3. Multi-tab và race condition

Nếu hai tab cùng dùng một session nhưng chọn tenant khác nhau, session-wide tenant selector có thể gây nhầm lẫn. Có thể dùng context riêng theo request/tab hoặc token/session scope riêng, tùy kiến trúc. Dù chọn cách nào, server phải ràng buộc request với đúng tenant và không cho race tạo cross-tenant access.

## 14. Admin support và platform administrator

Nhân viên support hoặc platform admin có thể cần hỗ trợ nhiều tenant. Quyền này có blast radius lớn và không nên dựa trên tenant context do caller cung cấp.

### 14.1. Scoped support access

- Chỉ cấp tenant access cho case cụ thể;
- Ghi requester, approver, tenant, purpose và thời hạn;
- Yêu cầu step-up cho hành động nhạy cảm;
- Giới hạn read/write theo nhiệm vụ;
- Ghi audit chi tiết và thông báo tenant theo policy;
- Tự hết hạn và thu hồi session/role tạm thời.

### 14.2. Break-glass

Platform-level break-glass cần credential riêng, approval/dual control, thời hạn ngắn, giám sát độc lập và diễn tập. Không dùng một global admin token dài hạn cho mọi tác vụ hỗ trợ.

### 14.3. Không dùng support role để bỏ qua tenant isolation

Support có thể được phép truy cập một số tenant theo policy, nhưng mỗi request vẫn cần scope, purpose và audit. Không tạo bypass chung kiểu is_support=true làm mọi tenant check bị bỏ qua.

## 15. Tenant context trong SSO và federation

IdP có thể xác thực người dùng và gửi group/tenant claims, nhưng RP phải kiểm tra trust và mapping.

### 15.1. Xác minh token/assertion

Với OIDC, kiểm tra chữ ký, issuer, audience, nonce, thời hạn và subject. Với SAML, kiểm tra signature, issuer, audience restriction, recipient/destination, time condition và replay protection. Sau đó mới diễn giải claim.

### 15.2. Tenant claim mapping

Không tin một claim tenant_id hoặc groups chỉ vì tên trường đúng. Cần:
- Allowlist issuer và client;
- Mapping claim theo issuer + subject;
- Tenant registry có thẩm quyền;
- Kiểm tra tenant active;
- Kiểm tra membership hiện tại hoặc freshness phù hợp;
- Role mapping allowlist;
- Xử lý claim cũ và account deprovision.

### 15.3. JIT provisioning

Nếu RP tạo membership lần đầu khi SSO login, phải có policy rõ về tenant mapping và role mặc định. Không cho người dùng tự chọn một tenant bất kỳ từ claim hoặc request. JIT không được biến một login IdP hợp lệ thành quyền truy cập toàn bộ tenant.

## 16. Tenant context và authorization cache

Authorization decision có thể được cache để tăng hiệu năng. Cache sai scope có thể làm lộ dữ liệu.

### 16.1. Cache key đầy đủ

Một decision cache key có thể cần:
- Principal ID;
- Tenant ID đã xác minh;
- Action;
- Resource ID/type;
- Authorization version;
- Policy version;
- Context attribute có ảnh hưởng quyết định.

Nếu bỏ tenant khỏi cache key, quyết định ALLOW cho tenant A có thể bị tái sử dụng tại tenant B.

### 16.2. Invalidation

Khi membership, role, tenant state hoặc resource ownership thay đổi:
- Tăng authorization version;
- Invalidate cache theo principal/tenant;
- Phát event qua outbox;
- Có TTL tối đa cho stale decision;
- Kiểm tra online cho hành động nhạy cảm.

### 16.3. Không cache quyết định vượt scope

Một kết quả ALLOW cho course:read không có nghĩa được đọc mọi course. Resource-specific authorization phải gắn resource ID và tenant. Tránh cache một boolean chung theo user.

## 17. Threat model cho tenant context

| Threat | Mục tiêu attacker | Kiểm soát |
| --- | --- | --- |
| Tenant spoofing | Gửi tenant ID khác để truy cập dữ liệu | Resolve server-side và kiểm tra membership |
| IDOR/BOLA | Đoán resource ID tenant khác | Resource ownership + tenant predicate |
| Host header injection | Giả host để chọn tenant | Trusted proxy, domain registry và canonicalization |
| Forwarded header spoofing | Giả forwarded host/tenant | Proxy xóa header client và xác thực gateway |
| Stale token claim | Dùng membership/role cũ | Version, introspection và freshness check |
| Cache leakage | Dùng quyết định/data cache của tenant khác | Tenant-aware cache key và invalidation |
| SQL omission | Query thiếu tenant filter | RLS, composite constraints và query review |
| Confused deputy | Service đặc quyền làm thay caller | Delegation, workload identity và scope check |
| Queue tampering | Sửa tenant trong message | Authenticated producer, integrity và consumer validation |
| Background job drift | Job chạy sau khi membership bị revoke | Recheck current state khi execute |
| Support bypass | Support truy cập mọi tenant | Justification, scoped JIT và audit |
| Cross-tenant token reuse | Token tenant A dùng ở tenant B | Audience/scope/tenant binding và policy |
| Race on switching | Request dùng nhầm tenant context | Context per request/tab và transaction binding |

## 18. Pseudocode resolve tenant và authorize resource

~~~text
authorize_request(request):
    principal = authenticate_request(request)
    require principal exists
    require principal.account_status == ACTIVE

    selector = resolve_tenant_selector_from_trusted_source(request)
    tenant = tenant_registry.lookup(selector)
    require tenant exists
    require tenant.status == ACTIVE

    membership = membership_store.get(
        principal.id,
        tenant.id
    )
    require membership exists
    require membership.status == ACTIVE

    resource = resource_store.load(request.resource_id)
    require resource exists
    require resource.tenant_id == tenant.id

    decision = policy_engine.evaluate(
        principal = principal,
        tenant = tenant,
        membership = membership,
        action = request.action,
        resource = resource,
        context = trusted_request_context(request)
    )

    require decision == ALLOW
    return execute_action_with_verified_tenant(
        principal,
        tenant,
        resource,
        request
    )
~~~

Pseudocode mô tả thứ tự kiểm tra. Thực tế cần xử lý transaction isolation, resource lookup không tiết lộ tồn tại cross-tenant, cache/version, service delegation và kiểm tra lại quyền tại điểm commit cho action nhạy cảm.

## 19. Kiểm thử tenant context

Kiểm thử trong staging với ít nhất hai tenant độc lập, user có membership khác nhau và resource giả lập. Không dùng dữ liệu khách hàng thật.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Valid membership | User A truy cập resource tenant A | ALLOW nếu role/action hợp lệ |
| No membership | User A chọn tenant C không có membership | DENY |
| Wrong tenant ID | Đổi tenant A thành B trong body/query | DENY nếu không có membership |
| Cross-tenant IDOR | Dùng resource ID thuộc tenant B trong tenant A | Không trả dữ liệu; DENY/404 theo policy |
| Resource ownership | Resource có tenant_id không khớp context | DENY |
| Host spoof | Gửi Host/forwarded host giả | Bị từ chối hoặc resolve theo proxy trust |
| Domain suffix | Host example.com.attacker.invalid | Không ánh xạ vào tenant example.com |
| Custom domain | Domain đã gỡ khỏi tenant | Không tiếp tục resolve tenant cũ |
| JWT claim | Token tenant A dùng tại tenant B | DENY |
| Stale membership | Membership bị revoke sau token issue | Bị từ chối trong SLA |
| Role scope | Instructor A truy cập lớp không được phân công | DENY |
| Multi-tenant user | User có role khác nhau ở A và B | Áp dụng role đúng tenant |
| Cache isolation | ALLOW của A được cache rồi request B | Không tái sử dụng quyết định A |
| Cache invalidation | Membership bị revoke | Cache được invalidated trong SLA |
| RLS | Query bỏ tenant predicate | Database policy vẫn chặn row khác tenant |
| Composite FK | Record A tham chiếu parent B | Constraint từ chối |
| Object storage | Signed URL dùng cho tenant khác | Không cấp hoặc không truy cập được |
| Search | Query bỏ filter tenant ở client | Server áp dụng tenant filter bắt buộc |
| Service-to-service | Service giả tenant header | Downstream từ chối nếu nguồn không tin cậy |
| Queue event | Message có tenant không hợp lệ | Consumer từ chối hoặc quarantine |
| Background job | Membership bị revoke trước khi job chạy | Job bị hủy/chặn theo policy |
| Tenant switch race | Hai request song song chọn tenant khác | Không lẫn context |
| Support access | Support không có case/approval hợp lệ | DENY |
| SSO mapping | Claim từ issuer không allowlist | Không tạo membership |
| Deprovision | Tenant/user bị suspend | Session và quyền bị xử lý theo SLA |

### 19.1. Bất biến bảo mật

- Client không thể tự chọn tenant và nhận quyền chỉ bằng cách đổi ID;
- Mọi resource có tenant ownership được kiểm tra với tenant context đã xác minh;
- Membership và role được kiểm tra trong đúng scope;
- Cache, queue, storage và service-to-service không làm mất tenant boundary;
- Token claim cũ không ghi đè trạng thái membership hiện tại;
- Tenant switching không tái sử dụng authorization decision của tenant trước;
- Support/platform admin chỉ truy cập theo scope, purpose và thời hạn;
- Không trả dữ liệu hoặc metadata tenant khác qua error, cache hay search.

## 20. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tin tenant_id từ request body | Tenant spoofing và cross-tenant access | Resolve server-side và kiểm tra membership |
| Chỉ kiểm tra user đã đăng nhập | User đọc resource tenant khác | Kiểm tra principal + tenant + resource + action |
| Query theo resource ID đơn lẻ | IDOR/BOLA | Tenant predicate và ownership check |
| Dùng host string parsing ngây thơ | Host giả ánh xạ sai tenant | Canonicalization, exact domain registry |
| Tin forwarded header từ client | Attacker chọn tenant qua proxy metadata | Trusted proxy chain |
| JWT claim được tin mãi | Membership cũ vẫn cấp quyền | Freshness/version/introspection |
| Cache key thiếu tenant | Data/ALLOW leakage | Tenant-aware cache key |
| Background job không lưu tenant | Job chạy sai scope | Persist verified context và recheck |
| Service dùng quyền riêng quá rộng | Confused deputy | Delegation và caller scope |
| Support bypass toàn cục | Ranh giới tenant mất hiệu lực | Scoped JIT, approval và audit |
| Chỉ filter ở frontend | API trực tiếp vẫn truy cập chéo | Server-side authorization |
| RLS dùng session variable không reset | Context request trước rò sang request sau | Transaction-local setting và pool hygiene |
| Tenant switch chỉ đổi UI | Backend giữ context/permission cũ | Server-side context transition |
| Không kiểm tra event đến trễ | Quyền đã revoke bị phục hồi | Versioning và reconciliation |

## 21. Checklist production

1. **Tenant model:** Tenant, principal, membership, role và resource scope có định nghĩa rõ?
2. **Resolution:** Nguồn tenant selector nào được tin cậy và cách canonicalize ra sao?
3. **Membership:** Mỗi request có kiểm tra membership active theo tenant?
4. **Resource ownership:** Resource được xác minh thuộc đúng tenant?
5. **Authorization:** Action, role, permission và ABAC conditions được đánh giá server-side?
6. **Host/domain:** Host, custom domain và forwarded header có trust boundary rõ?
7. **Token/session:** Tenant claim, audience, issuer, freshness và tenant switching được xử lý?
8. **Database:** Tenant predicate, RLS, composite FK và connection pool isolation được kiểm tra?
9. **Cache:** Key chứa tenant/principal/resource/version cần thiết; invalidation có SLA?
10. **Storage/search:** Object storage, signed URL, search và analytics giữ tenant filter?
11. **Service boundary:** Gateway/workload identity xác thực; internal tenant context không thể giả mạo?
12. **Queue/job:** Message integrity, tenant reference và reauthorization lúc thực thi?
13. **Support:** Support access có scope, purpose, approval, TTL và audit?
14. **Federation:** OIDC/SAML claims được xác minh và mapping theo issuer/tenant?
15. **Lifecycle:** Tenant suspension, membership revoke và deprovision lan tới session/token/cache?
16. **Observability:** Có metric/alert cho cross-tenant deny, tenant mismatch và policy failure?
17. **Testing:** Có test IDOR/BOLA, spoofed host, stale claim, cache leakage, race và background job?

## 22. Bài tập tình huống

Một nền tảng học tập phục vụ nhiều trường. API nhận tenant_id từ request body, xác thực JWT chỉ dựa trên chữ ký và thời hạn. Bảng gradebooks có cột id nhưng truy vấn chỉ lọc theo id, không có tenant_id. Cache dùng key gradebook:<id>. Một background export job chỉ lưu gradebook ID. Người dùng có thể thuộc nhiều trường và chuyển tenant bằng dropdown.

**Yêu cầu:**

1. Xác định ít nhất **tám lỗ hổng** có thể dẫn đến cross-tenant access hoặc data leakage.
2. Thiết kế lại tenant resolution từ domain/session/token và membership.
3. Viết truy vấn resource có tenant predicate và đề xuất constraint/RLS.
4. Thiết kế cache key và invalidation khi membership/role thay đổi.
5. Xác định metadata cần lưu trong background job và điều kiện reauthorization lúc chạy.
6. Mô tả tenant switching an toàn trong tình huống multi-tab.
7. Viết test cho forged tenant ID, IDOR, stale JWT, cache leakage và queue tampering.

**Gợi ý đối chiếu:** tenant ID từ body chỉ là selector; resolve và membership check ở server; kiểm tra resource owner; tenant-aware cache key; job lưu verified tenant và actor rồi recheck; switching gắn context rõ cho request/session; JWT claim cần freshness policy.

## 23. Ghi nhớ

- **Tenant context** xác định phạm vi tổ chức của request; nó không chứng minh danh tính và không tự cấp authorization.
- Principal, tenant, membership, role, action và resource phải được kiểm tra riêng rồi kết hợp trong policy.
- Tenant selector từ host, path, header hoặc token chỉ là đầu vào cần được resolve và xác minh server-side.
- Mỗi resource phải được kiểm tra tenant ownership để ngăn IDOR/BOLA và cross-tenant data leakage.
- Tenant boundary phải tồn tại xuyên suốt database, cache, object storage, search, service-to-service, queue và background job.
- Multi-tenant user cần role/membership riêng theo từng tenant; tenant switching phải thay đổi context an toàn và loại bỏ cache cũ.
- OIDC/SAML claims cần xác minh issuer/audience/signature và freshness; claim cũ không thay thế membership hiện tại.
- Support và platform admin cần scoped access, purpose, approval, TTL và audit; không có bypass toàn cục.
- Tenant suspension hoặc membership revocation phải lan tới session, token, cache và job theo SLA có thể kiểm chứng.

Tenant context an toàn khi hệ thống luôn biết **principal nào đang hành động, request thuộc tenant nào, resource thực sự thuộc tenant đó và policy nào cho phép hành động**. Giữ các điều kiện này nhất quán qua mọi tầng giúp ngăn một lỗi chọn tenant hoặc một resource ID đoán được trở thành sự cố lộ dữ liệu giữa các tổ chức.
