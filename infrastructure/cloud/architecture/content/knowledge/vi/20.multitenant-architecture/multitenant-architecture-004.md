# Phân quyền và ngăn truy cập chéo giữa các tenant

## 1. Vì sao tenant isolation là ranh giới bảo mật cốt lõi?

Trong nền tảng đa khách hàng (multi-tenant), nhiều tổ chức cùng sử dụng một ứng dụng và một phần hạ tầng. Mỗi tổ chức là một **tenant** với người dùng, dữ liệu, cấu hình và quyền riêng. Một lỗi lọc dữ liệu có thể khiến người dùng của Tenant A đọc, sửa hoặc xóa tài nguyên của Tenant B. Đây là sự cố cô lập dữ liệu nghiêm trọng, dù cả hai người dùng đều đăng nhập hợp lệ.

Trong module **CLOUD_ARCHITECTURE**, kiến trúc được thiết kế từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai; sau đó đánh giá theo các chiều độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Với SaaS đa tenant, ranh giới tenant phải được thực thi xuyên suốt request, database, cache, object storage, queue, search, log, backup và công cụ quản trị.

**Tenant isolation** không chỉ là thêm cột tenant_id vào bảng. Nó là một tập quy tắc về danh tính, quyền, ownership, truy cập tài nguyên, xử lý bất đồng bộ và quan sát, bảo đảm mỗi thao tác chỉ tác động tới tenant mà principal được phép đại diện.

Sau bài này, bạn có thể:

- Phân biệt authentication, tenant resolution và authorization.
- Xây dựng tenant context từ identity đã xác thực, không tin tenant ID do client tự khai báo.
- Ngăn IDOR và truy cập chéo tenant ở mức object/resource.
- So sánh shared database, schema-per-tenant và database-per-tenant.
- Bảo vệ database bằng tenant-scoped query, composite key và row-level security.
- Thiết kế cache key, object path, queue message, search index và background job có tenant scope.
- Kiểm soát quyền support/admin, export, backup và thao tác break-glass.
- Viết negative tests, audit và cảnh báo để phát hiện tenant leakage.

## 2. Các khái niệm và ranh giới tin cậy

### 2.1. Tenant, user, principal và resource

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Tenant | Tổ chức/khách hàng sở hữu một miền dữ liệu | Công ty An Phát |
| User | Người dùng cuối thuộc một hoặc nhiều tenant | Nhân viên đặt thiết bị |
| Principal | Danh tính đã được xác thực dùng để ra quyết định | User token hoặc service identity |
| Membership | Quan hệ giữa user và tenant kèm trạng thái/role | User U có role booking-admin ở Tenant A |
| Resource | Đối tượng cần bảo vệ | Booking, invoice, device, file, report |
| Tenant context | Tenant mà request/operation hiện tại đang đại diện | tenant A trong request đã xác thực |
| Policy | Điều kiện cho phép principal thực hiện action | User chỉ đọc booking thuộc tenant mình có quyền |

Một user có thể là thành viên của nhiều tenant. Vì vậy, không nên giả định user ID ánh xạ một-một sang tenant ID. Quyền phải xét cả principal, tenant context, membership, role/scope và resource được truy cập.

### 2.2. Authentication không phải authorization

- **Authentication (AuthN):** xác định principal là ai, ví dụ kiểm tra token, session hoặc service identity.
- **Tenant resolution:** xác định request đang hoạt động trong tenant nào, dựa trên thông tin đã được xác minh và membership.
- **Authorization (AuthZ):** quyết định principal có được thực hiện action cụ thể trên resource cụ thể trong tenant đó hay không.

Token hợp lệ chỉ chứng minh danh tính hoặc claims do issuer cấp. Nó không tự chứng minh user được phép đọc mọi booking có ID hợp lệ.

### 2.3. Tenant context phải có nguồn tin cậy

Một request có thể mang tenant slug trong hostname, path, header hoặc claim. Các giá trị từ client chỉ là **đầu vào để chọn context**, không phải bằng chứng quyền.

Ví dụ:

~~~http
GET /tenants/tenant-a/bookings/bkg-8124
Authorization: Bearer <access-token>
~~~

Server cần:

1. Xác thực token/session và lấy subject, issuer, audience, expiry cùng claims đáng tin cậy.
2. Xác minh user còn membership active ở Tenant A.
3. Kiểm tra role/scope cho operation.
4. Đọc booking theo tenant scope và kiểm tra ownership/relationship.
5. Trả response phù hợp mà không tiết lộ sự tồn tại của tài nguyên tenant khác ngoài chính sách đã chọn.

Không được làm kiểu:

~~~text
tenant_id = request.header["X-Tenant-ID"]
query("SELECT * FROM bookings WHERE booking_id = ?", booking_id)
~~~

Đoạn logic này vừa tin header không xác thực vừa query thiếu tenant scope. Nếu proxy hoặc client tự đặt header, attacker có thể thử đổi tenant.

### 2.4. Luồng request an toàn

~~~mermaid
flowchart TD
    CLIENT["Client request"] --> AUTHN["Verify token / session"]
    AUTHN --> ID["Trusted principal"]
    ID --> RESOLVE["Resolve requested tenant"]
    RESOLVE --> MEMBER{"Active membership?"}
    MEMBER -->|"No"| DENY["Deny without data access"]
    MEMBER -->|"Yes"| POLICY["Check action / role / scope"]
    POLICY --> RESOURCE{"Resource belongs to tenant?"}
    RESOURCE -->|"No"| DENY
    RESOURCE -->|"Yes"| ACCESS["Tenant-scoped data access"]
    ACCESS --> AUDIT["Audit security-relevant action"]
    AUDIT --> RESPONSE["Return allowed result"]
~~~

Tenant resolution và resource authorization là hai lần kiểm tra khác nhau. Một user có membership ở Tenant A vẫn không được đọc tài nguyên Tenant B chỉ vì client gửi ID của B.

## 3. Các kiểu tấn công truy cập chéo tenant

### 3.1. Insecure Direct Object Reference (IDOR)

API dùng object ID do client gửi mà không kiểm tra resource có thuộc tenant của principal hay không.

Ví dụ:

~~~http
GET /api/bookings/bkg-1002
Authorization: Bearer <token-of-tenant-a-user>
~~~

Nếu bkg-1002 thuộc Tenant B và server chỉ query theo booking_id, người dùng Tenant A có thể đọc dữ liệu B. UUID khó đoán hơn số tuần tự nhưng không phải cơ chế authorization.

### 3.2. Mass assignment và over-posting

Client gửi thêm field như tenant_id, owner_id, role hoặc status để ghi đè thuộc tính mà server không cho user tự chỉnh.

~~~json
{
  "deviceId": "dev-017",
  "slotId": "slot-0900",
  "tenantId": "tenant-b",
  "status": "confirmed"
}
~~~

API tạo booking nên chỉ bind các field được phép từ request; tenant ID, owner ID và trạng thái workflow phải do server xác định theo context và business logic. Không deserialize toàn bộ body trực tiếp vào entity rồi lưu.

### 3.3. Confused deputy

Một service có quyền rộng thực hiện yêu cầu thay mặt caller mà không giữ tenant context hoặc không kiểm tra scope. Ví dụ report-export service có quyền đọc mọi object; user Tenant A truyền object key thuộc Tenant B và service tải file đó về.

Service có quyền rộng phải kiểm tra caller context, resource ownership và purpose trước khi dùng quyền của mình. Không xem service-to-service authentication là sự cho phép truy cập mọi tenant.

### 3.4. Rò rỉ qua cache hoặc shared storage

Ứng dụng query database đúng tenant nhưng dùng cache key chỉ dựa trên booking ID. Nếu ID có thể trùng giữa tenant hoặc cache entry không gắn tenant scope, request sau có thể nhận response của tenant khác.

Các nguồn rò rỉ khác gồm object path đoán được, signed URL không gắn quyền/expiry phù hợp, search index thiếu tenant filter, queue consumer dùng tenant ID không xác thực, log/export chứa dữ liệu chéo tenant.

## 4. Authorization phải gắn với resource

### 4.1. Policy principal + tenant + action + resource

Một quyết định authorization tối thiểu cần xem:

- Principal: user/service nào?
- Tenant: đang đại diện tenant nào?
- Action: read, create, update, delete, export, approve hay administer?
- Resource: object nào, thuộc tenant nào, có quan hệ nào với principal?
- Context: môi trường, trạng thái, purpose, thời gian hoặc risk signal liên quan?

Có thể mô tả quyết định:

~~~text
ALLOW when:
  principal is authenticated
  AND membership(principal, tenant) is active
  AND role permits action
  AND resource.tenant_id == tenant.id
  AND resource-specific policy permits this principal
~~~

Không phải mọi endpoint đều cần kiểm tra tất cả yếu tố như nhau, nhưng hệ thống phải xác định rõ policy áp dụng. Ví dụ user thường có thể đọc booking do mình tạo; tenant-admin có thể đọc mọi booking trong tenant; support agent có thể có quyền hỗ trợ theo ticket và thời hạn.

### 4.2. Role-based và attribute-based access

**RBAC** (Role-Based Access Control) cấp quyền theo role trong phạm vi tenant:

| Role trong tenant | Quyền ví dụ | Giới hạn |
|---|---|---|
| tenant-owner | Quản lý billing, thành viên và cấu hình tenant | Chỉ tenant mình sở hữu/quản trị |
| tenant-admin | Quản lý thành viên và tài nguyên | Không tự động có quyền cross-tenant |
| booking-manager | Xem và xử lý booking của tenant | Chỉ operation được phân công |
| member | Tạo và xem booking thuộc phạm vi của mình | Không xem mọi dữ liệu tenant nếu policy không cho |
| auditor | Đọc báo cáo/audit được phép | Thường không được ghi dữ liệu nghiệp vụ |

**ABAC** (Attribute-Based Access Control) xét thuộc tính như tenant ID, department, resource classification, owner, support ticket, environment hoặc time-bound approval. ABAC linh hoạt cho tổ chức phức tạp nhưng policy khó debug hơn; cần công cụ giải thích vì sao quyết định allow/deny.

Có thể kết hợp RBAC cho role ổn định và ABAC cho resource scope. Không biến role thành một chuỗi string tự khai từ client.

### 4.3. Quyền object-level và relationship-based

Vai trò “member” không đồng nghĩa được đọc mọi object trong tenant. Ví dụ:

- Nhân viên chỉ xem booking mình tạo hoặc được phân công.
- Quản lý nhóm xem booking của nhóm.
- Tenant-admin xem tài nguyên trong tenant.
- Auditor đọc bản sao hoặc view chỉ đọc.

Khi rule phụ thuộc quan hệ giữa user, team, project và resource, có thể dùng relationship-based access control (ReBAC) hoặc policy engine. Dù dùng framework nào, quyết định cuối vẫn cần tenant boundary và kiểm tra resource ownership.

### 4.4. Deny by default

Nếu tenant context thiếu, membership không xác định, policy engine timeout hoặc resource không tìm thấy trong tenant scope, mặc định phải từ chối hoặc trả trạng thái an toàn. Không fallback thành “cho phép” để tăng availability.

Đặc biệt, khi authorization service không sẵn sàng, lựa chọn fail-closed có thể làm giảm availability nhưng bảo vệ confidentiality. Nếu cần cache authorization decision để giảm latency, phải giới hạn TTL, scope, policy version và cách revoke; không cache allow vô thời hạn.

## 5. Chiến lược lưu trữ cho hệ thống đa tenant

Mức cô lập dữ liệu phụ thuộc mô hình lưu trữ. Không có một mô hình tốt nhất cho mọi sản phẩm.

### 5.1. Shared database, shared schema

Mọi tenant dùng chung database và bảng; mỗi row có tenant_id.

Ưu điểm:

- Chi phí hạ tầng thấp, sử dụng tài nguyên hiệu quả.
- Migration và vận hành tập trung.
- Phù hợp số lượng tenant lớn và tenant có tải vừa phải.

Đánh đổi:

- Một query thiếu tenant filter có thể lộ dữ liệu.
- Noisy neighbor có thể ảnh hưởng tenant khác.
- Backup/restore riêng một tenant phức tạp hơn.
- Quản trị quyền ở row-level và connection context cần cẩn thận.

### 5.2. Schema-per-tenant

Mỗi tenant có schema riêng trong cùng database instance.

Ưu điểm: phân tách namespace rõ hơn; có thể áp quyền/schema migration riêng; chia sẻ compute/database engine.

Đánh đổi: số schema lớn làm migration/catalog/quota phức tạp; connection/search path dễ cấu hình sai; một credential quá rộng vẫn có thể đọc nhiều schema; noisy neighbor ở instance vẫn còn.

### 5.3. Database-per-tenant

Mỗi tenant có database riêng hoặc cụm/database instance riêng.

Ưu điểm: blast radius dữ liệu nhỏ hơn, backup/restore, key, quota và performance isolation rõ hơn; thuận lợi cho tenant có yêu cầu compliance riêng.

Đánh đổi: chi phí và số lượng resource tăng; provisioning, migration, connection management, monitoring và patching phức tạp; tenant nhỏ có thể lãng phí tài nguyên.

### 5.4. So sánh mô hình

| Tiêu chí | Shared schema | Schema-per-tenant | Database-per-tenant |
|---|---|---|---|
| Cô lập logic | Dựa mạnh vào tenant predicate/RLS | Namespace riêng, vẫn cần privilege | Ranh giới database rõ hơn |
| Chi phí | Thường thấp nhất | Trung bình | Thường cao hơn |
| Migration | Một schema chung | Lặp qua nhiều schema | Orchestration nhiều database |
| Backup/restore một tenant | Khó hơn | Có thể tách theo schema/tool | Thường dễ khoanh vùng hơn |
| Noisy neighbor | Cao hơn | Vẫn chia sẻ instance | Có thể tách compute/storage |
| Quản trị số tenant lớn | Đơn giản hơn nếu policy tốt | Catalog và migration phức tạp | Provisioning/monitoring phức tạp |
| Phù hợp | Nhiều tenant nhỏ/vừa | Cần namespace và lifecycle riêng | Tenant lớn, yêu cầu isolation cao |

### 5.5. Tiered/hybrid isolation

Một nền tảng có thể dùng shared database cho phần lớn tenant, còn tenant lớn hoặc có yêu cầu riêng chuyển sang database/cluster chuyên dụng. Đây là hybrid/tiered model.

Thiết kế hybrid phải giữ một interface truy cập dữ liệu thống nhất nhưng mapping tenant-to-database được quản lý bởi control plane tin cậy. Không nhận hostname/database name từ client rồi kết nối trực tiếp. Phải có migration, failover, backup, tenant move và kiểm tra mapping rõ ràng.

~~~mermaid
flowchart TB
    API["Tenant-aware API"] --> RES["Trusted tenant directory"]
    RES --> ROUTE{"Tenant placement"}
    ROUTE -->|"Standard tier"| SHARED[("Shared DB / schema")]
    ROUTE -->|"Dedicated tier"| DED[("Dedicated DB")]
    ROUTE -->|"Regional tier"| REG[("Regional DB cluster")]
    SHARED --> POLICY["Tenant authorization + data access layer"]
    DED --> POLICY
    REG --> POLICY
~~~

Directory xác định nơi lưu dữ liệu và policy theo tenant; service vẫn phải authorization resource và tenant. Route tới đúng database không đồng nghĩa user được phép đọc mọi record ở database đó.

## 6. Database isolation: composite key, query scope và RLS

### 6.1. Composite key và foreign key có tenant scope

Với shared schema, có thể đưa tenant ID vào primary/unique key để database hỗ trợ ownership consistency:

~~~sql
CREATE TABLE bookings (
    tenant_id   UUID NOT NULL,
    booking_id  UUID NOT NULL,
    customer_id UUID NOT NULL,
    status      TEXT NOT NULL,
    PRIMARY KEY (tenant_id, booking_id)
);

CREATE TABLE booking_items (
    tenant_id  UUID NOT NULL,
    booking_id UUID NOT NULL,
    item_id    UUID NOT NULL,
    PRIMARY KEY (tenant_id, booking_id, item_id),
    FOREIGN KEY (tenant_id, booking_id)
      REFERENCES bookings (tenant_id, booking_id)
);
~~~

Composite foreign key ngăn item của tenant này trỏ sang booking tenant khác trong cùng schema. Nó không thay query authorization, nhưng bổ sung một invariant ở tầng database.

### 6.2. Tenant-scoped query

Mọi query đọc/ghi resource cần gắn tenant scope từ context tin cậy:

~~~sql
SELECT booking_id, status
FROM bookings
WHERE tenant_id = :trusted_tenant_id
  AND booking_id = :booking_id;
~~~

Update/delete cũng cần điều kiện tenant:

~~~sql
UPDATE bookings
SET status = :new_status
WHERE tenant_id = :trusted_tenant_id
  AND booking_id = :booking_id;
~~~

Kiểm tra row count và business transition. Không tìm row theo ID trước rồi chỉ kiểm tra tenant ở một nhánh code sau khi đã đọc dữ liệu nhạy cảm.

### 6.3. Row-level security (RLS)

Database có thể áp chính sách row-level security để giới hạn row mà role được truy cập. Ví dụ khái niệm với PostgreSQL:

~~~sql
ALTER TABLE bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON bookings
USING (
  tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
  tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

Ứng dụng cần thiết lập tenant context trong transaction trước khi query:

~~~sql
BEGIN;
SET LOCAL app.tenant_id = '2c0e2c3d-5a10-4b8e-ae8d-6e0a8ea7a4c1';
SELECT booking_id, status FROM bookings;
COMMIT;
~~~

Đây là ví dụ minh họa, phải kiểm thử theo phiên bản/configuration database. Các điểm quan trọng:

- Connection pool tái sử dụng connection; session-level setting không được rò sang request tiếp theo. Dùng transaction-scoped setting phù hợp và luôn reset/rollback.
- Role sở hữu bảng, superuser hoặc role có quyền bypass RLS có thể bỏ qua policy tùy database. Runtime application không nên kết nối bằng role quá mạnh.
- RLS chỉ bảo vệ bảng đã bật policy; bảng mới hoặc query path mới có thể bị bỏ sót.
- Tenant context do application set vẫn phải đến từ identity đã xác minh; nếu attacker điều khiển được setting, RLS không cứu được.
- Policy test cần cover SELECT, INSERT, UPDATE, DELETE và mọi role/partition liên quan.

### 6.4. Phòng lỗi ở data-access layer

Có thể dùng repository/query abstraction bắt buộc nhận TenantContext thay vì cho phép developer viết query tuỳ ý:

~~~text
bookingRepository.findById(tenantContext, bookingId)
bookingRepository.update(tenantContext, bookingId, command)
~~~

Không cung cấp method phổ biến như findById(bookingId) cho đường đi multi-tenant nếu nó bỏ tenant scope. Static analysis, code review và integration tests cần phát hiện query không có tenant predicate.

## 7. Tenant isolation ở cache

Cache là nơi rất dễ phát sinh rò rỉ chéo tenant vì nhiều service cùng chia sẻ một cluster.

### 7.1. Cache key phải chứa security scope

Thiết kế:

~~~text
tenant:{tenant_id}:booking:{booking_id}
tenant:{tenant_id}:catalog:{catalog_id}
tenant:{tenant_id}:user:{user_id}:preferences
~~~

Không nên dùng:

~~~text
booking:{booking_id}
user:{user_id}:preferences
~~~

nếu ID không globally unique hoặc dữ liệu phụ thuộc tenant. Ngay cả khi ID globally unique, thêm tenant scope vào cache key có thể giúp ngăn sai sót ở các lớp gọi và làm rõ isolation boundary.

### 7.2. Cache authorization decision

Nếu cache quyền:

- Key phải bao gồm principal, tenant, resource/action scope và policy version đủ cần thiết.
- TTL phải ngắn theo mức rủi ro; có cơ chế invalidate khi membership/role bị revoke.
- Không chia sẻ một allow decision giữa các tenant hoặc user.
- Khi thiếu tenant context hoặc cache lỗi, không fallback thành quyền rộng.
- Không cache raw token hoặc secret trong key/log.

### 7.3. Invalidation và tenant lifecycle

Khi user bị remove khỏi tenant, dữ liệu session/cache authorization có thể còn tồn tại. Cần event/version để invalidate hoặc dùng TTL giới hạn exposure. Khi tenant bị suspend/disable, cần áp dụng ngay policy cho API, cache, worker, signed URL và export job đang chạy.

## 8. Object storage, file và signed URL

### 8.1. Object namespace có tenant scope

Path ví dụ:

~~~text
tenants/{tenant_id}/bookings/{booking_id}/documents/{document_id}
~~~

Path chứa tenant ID giúp tổ chức, nhưng **không phải một cơ chế authorization**. Bucket/object policy và ứng dụng vẫn phải xác minh principal có quyền với tenant/resource.

Không cho client tùy ý cung cấp toàn bộ object key rồi backend đọc bằng quyền service rộng. Thay vào đó, backend nhận resource ID, kiểm tra tenant ownership, ánh xạ sang object key từ metadata đáng tin cậy, rồi mới đọc.

### 8.2. Signed URL

Signed URL cho phép client truy cập object trong một khoảng thời gian mà không cần chia sẻ credential của service. Tuy nhiên URL hoạt động như bearer capability: ai có URL còn hạn có thể dùng đúng scope được ký.

Quy tắc:

- Chỉ phát URL sau authorization object-level.
- Giới hạn đúng object, HTTP method và thời hạn ngắn phù hợp.
- Không ghi URL đầy đủ vào log, analytics hoặc ticket.
- Không dùng signed URL dài hạn cho dữ liệu nhạy cảm nếu có phương án khác.
- Cân nhắc cách revoke: nhiều signed URL chỉ mất hiệu lực khi hết hạn hoặc khi resource/credential/policy liên quan bị thay đổi.
- Khi tenant bị suspend hoặc user bị revoke, cân nhắc tác động tới URL đã phát hành.

### 8.3. Upload an toàn

Upload cần kiểm tra tenant ownership, file size/type, malware scan, checksum, content disposition và nơi lưu. Nếu dùng pre-signed upload:

- Backend tạo key trong tenant prefix sau khi xác thực context.
- Chỉ cấp quyền PUT cho object/method cụ thể.
- Không cho client ghi đè object của tenant khác.
- Sau upload, backend xác minh metadata/object rồi mới đánh dấu file được chấp nhận.
- Không tin MIME type hoặc file extension do client tự khai.

## 9. Queue, event và background job

Request đồng bộ có tenant context, nhưng message bất đồng bộ có thể chạy vài phút hoặc nhiều giờ sau khi user đã logout, membership đã đổi hoặc tenant bị suspend. Không được dựa vào thread-local/request context của process gốc.

### 9.1. Tenant metadata trong message

Event/command có thể bao gồm:

~~~json
{
  "eventId": "evt-7812",
  "tenantId": "tenant-a",
  "eventType": "booking.export.requested",
  "actorId": "user-120",
  "resourceId": "export-812",
  "correlationId": "corr-991",
  "occurredAt": "2026-11-18T09:00:00Z",
  "schemaVersion": 1
}
~~~

Đây là metadata để định tuyến, audit và kiểm tra; message không tự chứng minh tenant ID là hợp lệ. Consumer cần:

1. Xác thực nguồn message qua broker identity/ACL và chữ ký nếu thiết kế yêu cầu.
2. Validate schema và loại event được phép.
3. Kiểm tra tenant tồn tại/active và resource thuộc tenant.
4. Kiểm tra actor/authorization context hoặc policy service-to-service phù hợp với workflow.
5. Tạo tenant-scoped data access context mới trong process consumer.
6. Ghi kết quả với idempotency key/event ID và audit.

### 9.2. Tenant context trong job dài

Job cần lưu tenant ID, actor/service identity, purpose, scope tài nguyên, thời điểm tạo, policy version nếu phù hợp, deadline và correlation ID. Khi chạy, worker tái xác thực quyền theo policy hiện hành hoặc theo snapshot authority đã được business phê duyệt. Không mặc định quyền tại thời điểm enqueue vẫn còn hiệu lực nhiều giờ sau.

Ví dụ tenant bị suspend trong lúc export:

- Nếu export chưa bắt đầu, worker có thể dừng ngay.
- Nếu đang xử lý, worker cần checkpoint/cancel an toàn.
- Nếu artifact đã tạo nhưng chưa phát URL, không phát URL sau khi quyền bị revoke.
- Nếu URL đã phát, cần xét expiry/revocation strategy.

### 9.3. Queue isolation và fairness

Một tenant gửi hàng triệu job có thể làm chậm các tenant khác. Có thể dùng per-tenant quota, concurrency limit, fair scheduling, priority class hoặc dedicated queue cho tenant lớn. Điều này vừa là performance isolation vừa giảm rủi ro một tenant gây denial of service cho phần còn lại.

## 10. Search, analytics và export

### 10.1. Search index

Document trong search index phải có tenant identifier và filter bắt buộc ở server-side. Không cho client tự gửi filter tenant bất kỳ rồi coi đó là authorization.

Các câu hỏi cần kiểm tra:

- Search API có gắn tenant filter từ trusted context không?
- Aggregation/facets có thể cộng dữ liệu của nhiều tenant không?
- Autocomplete, suggestion, vector embedding và index alias có tenant scope?
- Reindex/backfill có giữ tenant ID và policy?
- Admin/debug query có bypass filter không?

Nếu index dùng chung, một lỗi filter trong aggregation cũng có thể rò dữ liệu dù hit document đã được lọc. Với tenant nhạy cảm, cân nhắc index riêng hoặc cluster riêng.

### 10.2. Analytics và data lake

Data warehouse thường gom dữ liệu từ nhiều tenant để tính báo cáo tổng hợp. Phân tích cross-tenant có thể được phép cho platform operator theo purpose cụ thể nhưng không có nghĩa tenant user được xem dữ liệu thô của tenant khác.

Thiết kế nên:

- Phân tách raw, curated và aggregate zone.
- Row/column-level security theo tenant.
- Mask/pseudonymize trường định danh khi không cần plaintext.
- Không để export job tạo file chứa nhiều tenant rồi phát URL riêng lẻ.
- Ghi lineage, owner, purpose và retention.
- Kiểm tra dashboard/shared query có filter server-side.

### 10.3. Export và báo cáo

Một export request cần authorization ở thời điểm tạo và trước khi phát kết quả. File export nên gắn tenant ownership, storage policy, encryption key, TTL, audit và người tạo. Nếu report có dữ liệu cross-tenant cho mục đích platform operations, nó cần quy trình approval và access riêng.

## 11. Identity, tenant provisioning và lifecycle

### 11.1. Membership lifecycle

Membership thay đổi theo thời gian:

- Invite, accept và activate.
- Thêm/bớt role hoặc scope.
- Suspend user hoặc tenant.
- Remove user khỏi tenant.
- Chuyển ownership hoặc hợp nhất tenant.

Các thay đổi này phải cập nhật authorization, session/token claims, cache, API key, job và access link. Nếu token chứa role cũ quá lâu, hệ thống cần token lifetime ngắn, introspection, revocation hoặc policy-version check phù hợp.

### 11.2. Tenant directory/control plane

Control plane có thể quản lý:

- Tenant ID ổn định và trạng thái active/suspended/closing.
- Domain/slug và mapping sang region/database/tier.
- Subscription/quota và feature enablement.
- Encryption key, data residency và backup policy.
- Membership/role và owner.
- Lifecycle event: provision, migrate, suspend, delete.

Tenant directory là nguồn thông tin control plane; không nên để mọi request tùy tiện query một bảng cấu hình không được bảo vệ. Directory cần availability, audit, authorization và cache policy riêng.

### 11.3. Offboarding và xóa tenant

Khi đóng tenant, cần xác định:

1. Chặn tạo request/job mới.
2. Thu hồi membership, API key, session và service grant.
3. Dừng hoặc drain workflow đang chạy.
4. Xử lý retention, legal hold, export quyền sở hữu và yêu cầu xóa.
5. Xóa/ẩn dữ liệu chính, cache, search index, object, queue/DLQ và các bản sao theo policy.
6. Quản lý key nếu crypto-erasure được sử dụng và phù hợp.
7. Ghi bằng chứng, audit và thông báo hoàn tất.

Không xóa key hoặc backup vội vàng nếu còn retention/legal hold. Tenant lifecycle phải liên hệ với data lifecycle và backup restore design.

## 12. Quyền support và platform administrator

Nhân viên support hoặc platform admin có thể cần hỗ trợ nhiều tenant, nhưng quyền cross-tenant phải là ngoại lệ được kiểm soát.

### 12.1. Support access có thời hạn

Một mô hình an toàn:

- Support mở ticket gắn tenant và purpose.
- Người có thẩm quyền phê duyệt scope: loại dữ liệu, action và thời hạn.
- Nhân viên xác thực mạnh (MFA/SSO) và kích hoạt quyền just-in-time.
- Chỉ cấp read hoặc action tối thiểu cần thiết.
- User/tenant được thông báo nếu chính sách yêu cầu hoặc nếu có thể.
- Mọi truy cập dữ liệu nhạy cảm được audit.
- Quyền tự hết hạn; sau đó review access log.

### 12.2. Break-glass

Break-glass dành cho incident nghiêm trọng khi luồng phê duyệt thông thường không đủ nhanh. Cần:

- Điều kiện kích hoạt và approver rõ.
- MFA, credential riêng, thời hạn rất ngắn.
- Giới hạn resource/action và ghi lý do.
- Audit không thể bị người thao tác sửa/xóa.
- Alert ngay cho security/on-call.
- Post-incident review bắt buộc và thu hồi quyền.

Không dùng một admin credential thường trực cho mọi support engineer. Không dùng “support mode” làm cách bỏ qua tenant checks trong toàn bộ application.

## 13. Kiểm thử tenant isolation

Không thể chỉ kiểm thử happy path của một tenant rồi suy ra tenant boundary đúng. Cần test âm có tenant A và tenant B cùng hoạt động.

### 13.1. Ma trận kiểm thử

| Tình huống | Kỳ vọng |
|---|---|
| User A đọc booking A | Allow nếu role/resource policy cho phép |
| User A đọc booking B bằng ID đoán được | Deny; không lộ dữ liệu B |
| User A cập nhật booking B | Deny; không thay đổi dữ liệu |
| User A xóa file B | Deny; audit attempt |
| User A đổi header/host/path sang tenant B | Membership/context được xác minh lại |
| User chưa có membership chọn Tenant A | Deny trước khi truy vấn dữ liệu |
| User đã bị remove nhưng token cũ còn hạn | Quyền bị thu hồi theo revocation policy |
| Cache có key trùng giữa tenant | Không trả giá trị chéo tenant |
| Search query thiếu tenant filter | Test phải fail hoặc query layer tự áp filter |
| Queue message tenant ID bị sửa | Consumer reject hoặc quarantine |
| Worker chạy job sau khi tenant suspend | Cancel/block theo policy |
| Support access hết hạn | Không còn đọc dữ liệu tenant |
| Export file có tenant khác | Test phát hiện và chặn trước phát hành |

### 13.2. Integration test hai tenant

~~~text
tenantA = createTenant("A")
tenantB = createTenant("B")
userA = createMember(tenantA, role="member")
userB = createMember(tenantB, role="member")

bookingA = createBooking(as=userA, tenant=tenantA)
bookingB = createBooking(as=userB, tenant=tenantB)

assert readBooking(as=userA, tenant=tenantA, id=bookingA.id) == ALLOW
assert readBooking(as=userA, tenant=tenantA, id=bookingB.id) == DENY
assert updateBooking(as=userA, tenant=tenantA, id=bookingB.id) == DENY
assert deleteDocument(as=userA, tenant=tenantA, id=documentB.id) == DENY
~~~

Pseudocode cần chạy qua API/repository thật và kiểm tra cả side effect: row không đổi, event không phát, cache không bị ghi, audit có record phù hợp. Chỉ assert HTTP 403 là chưa đủ nếu thao tác ghi đã xảy ra trước lúc deny.

### 13.3. Property/fuzz testing

Có thể sinh nhiều tổ hợp user/tenant/resource và kiểm tra invariant:

~~~text
for every request:
    if resource.tenant_id != trusted_context.tenant_id:
        assert no_read
        assert no_write
        assert no_export
        assert no_side_effect
~~~

Thử ID tuần tự, UUID giả, tenant bị disable, header trùng lặp, token audience sai, tenant slug Unicode/case variation và race khi membership bị revoke. Fuzz phải chạy trong môi trường test có dữ liệu giả và giới hạn tài nguyên.

### 13.4. RLS và database test

Tạo test kết nối bằng đúng runtime role, không phải admin role. Chạy transaction theo connection pool thực tế; xác minh SELECT/INSERT/UPDATE/DELETE chỉ thấy row tenant hiện tại; xác minh connection tái sử dụng không mang tenant context trước; xác minh table mới không vô tình thiếu RLS/policy.

## 14. Audit, observability và phát hiện leakage

### 14.1. Event audit nên có

- Principal/user/service identity.
- Tenant context và membership/role liên quan.
- Action và resource type/ID.
- Outcome allow/deny, policy/version hoặc reason code phù hợp.
- Correlation/trace ID và thời gian.
- Support/break-glass ticket, approver và expiry nếu có.
- Export/download/delete và thay đổi role/key/policy.

Không log access token, secret hoặc nội dung PII không cần thiết. Log tenant ID cần access control và retention riêng vì nó có thể giúp lập bản đồ khách hàng.

### 14.2. Cảnh báo cần thiết

- Một principal liên tục truy cập resource thuộc tenant khác.
- Một request có nhiều tenant context mâu thuẫn.
- Tăng đột biến 403/404 theo một dải resource ID.
- Search/export trả số row vượt quy mô thông thường của tenant.
- Service role dùng quyền cross-tenant ngoài job/approval dự kiến.
- Support session hết hạn nhưng vẫn gọi API.
- Cache key hoặc object prefix không có tenant scope.
- RLS policy/table privilege thay đổi ngoài change window.

Không nhất thiết mọi cross-tenant attempt là tấn công; có thể do client bug hoặc stale link. Tuy nhiên phải đo, phân loại và điều tra theo severity.

### 14.3. Metric không làm lộ dữ liệu

Có thể đo request count, deny count, export size, support access và tenant quota theo nhóm/tier. Tránh tạo metric label cho mọi user/resource ID vì cardinality lớn và tăng nguy cơ lộ định danh. Dùng sampled logs/traces có kiểm soát để điều tra cụ thể.

## 15. Giảm noisy neighbor và bảo vệ fairness

Tenant isolation không chỉ là confidentiality. Một tenant có thể làm ảnh hưởng availability/performance của tenant khác bằng cách tiêu thụ hết CPU, DB connection, queue throughput, cache memory hoặc storage IOPS.

Biện pháp:

- Quota theo tenant cho API request, concurrent jobs, storage, upload và export.
- Rate limit theo tenant/client/operation.
- Fair scheduling hoặc per-tenant queue/concurrency budget.
- Connection pool và query timeout có giới hạn.
- Cache memory namespace/eviction policy phù hợp.
- Admission control cho batch job và report nặng.
- Dedicated tier cho tenant lớn/regulated nếu cần.

Quota cần có cách xử lý khi vượt mức: trả 429/403 phù hợp, thông báo quota, Retry-After hoặc chuyển sang tier khác. Không để một tenant có thể làm nghẽn control plane hoặc worker toàn hệ thống.

## 16. Kiến trúc tham chiếu cho BookingCloud

~~~mermaid
flowchart TB
    U["Tenant user / client"] --> GW["API gateway"]
    GW --> AUTH["Identity + membership resolver"]
    AUTH --> CTX["Trusted TenantContext"]
    CTX --> SVC["Tenant-aware services"]
    SVC --> AUTHZ["Resource authorization"]
    AUTHZ --> DAL["Tenant-scoped data access"]
    DAL --> DB[("Shared DB with RLS/composite keys")]
    DAL --> CACHE[("Tenant-scoped cache keys")]
    DAL --> OBJ[("Private object storage prefixes")]
    SVC --> Q["Tenant-tagged commands/events"]
    Q --> W["Workers revalidate tenant/resource"]
    W --> DAL
    SVC --> AUDIT["Audit / security telemetry"]
    AUTHZ --> AUDIT
    W --> AUDIT
~~~

Trong thiết kế này:

- Gateway xác thực kết nối và chuyển identity token đã xác minh.
- Membership resolver tạo tenant context có nguồn tin cậy.
- Authorization kiểm tra role và quan hệ resource.
- Data-access layer buộc query/cache/object access có tenant scope.
- Worker khôi phục context từ message đã xác thực và kiểm tra trạng thái tenant hiện tại.
- Audit liên kết operation nhưng hạn chế dữ liệu nhạy cảm.

Với tenant dedicated database, DAL chọn đúng datastore từ tenant directory nhưng vẫn áp identity và object policy ở application layer.

## 17. Đánh giá tenant isolation theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Ai sở hữu tenant policy, membership lifecycle và support access? | Tenant catalog, runbook, access review, audit, automation và incident drill |
| **Security** | Tenant context có nguồn tin cậy? Mọi resource/query/cache/export có kiểm tra scope? | Threat model, IAM/RBAC/ABAC, RLS test, negative tests, signed-URL controls |
| **Reliability** | Authorization service, tenant directory hoặc policy cache lỗi thì hệ thống xử lý an toàn ra sao? | Fail-closed behavior, bounded cache TTL, recovery path, multi-tenant fault tests |
| **Performance Efficiency** | Tenant resolution và authorization có tạo latency/DB contention? | p95/p99 theo operation, policy cache metrics, query plans và load test |
| **Cost Optimization** | Mức isolation nào phù hợp với từng tier và backup/restore có quá tốn kém? | Cost per tenant, dedicated-tier utilization, provisioning và restore cost |
| **Sustainability** | Tenant đã đóng có còn dữ liệu/cache/index/job không cần thiết? | Retention/deletion evidence, resource lifecycle, storage and compute utilization |

Thiết kế phải cân bằng mức cô lập với chi phí và khả năng vận hành. Shared schema tiết kiệm tài nguyên nhưng đòi hỏi query enforcement chặt; dedicated database tăng blast-radius isolation nhưng cần automation để quản lý nhiều resource. Quyết định nên dựa trên sensitivity, workload, hợp đồng dịch vụ và khả năng chứng minh policy.

## 18. Bài thực hành: review lỗi truy cập chéo tenant

Một SaaS quản lý thiết bị có API:

- GET /bookings/{bookingId}
- PATCH /bookings/{bookingId}
- POST /exports
- GET /files/{fileId}/download

Token có subject và role, còn client gửi X-Tenant-ID trong header. Database dùng shared schema có tenant_id nhưng repository hiện query booking chỉ theo booking_id. Cache key là booking:{bookingId}. Export worker nhận tenant_id trong message và dùng service role có quyền đọc mọi object. Support team dùng admin role chung để điều tra.

Hãy thực hiện:

**Bài 1 — Threat model:** liệt kê ít nhất năm đường truy cập chéo tenant hoặc confused deputy.

**Bài 2 — Tenant context:** thiết kế cách resolve tenant từ membership đã xác minh. Xử lý trường hợp user thuộc hai tenant và request chọn tenant chưa được cấp quyền.

**Bài 3 — API authorization:** viết policy cho GET/PATCH booking, export và file download. Phân biệt role-level với object-level authorization.

**Bài 4 — Database:** sửa query để có tenant scope; đề xuất composite key/foreign key và đánh giá RLS cùng connection pooling.

**Bài 5 — Cache/object:** thiết kế key và object namespace có tenant scope; quy định cách tạo signed URL.

**Bài 6 — Worker:** sửa message contract, xác thực nguồn, kiểm tra tenant/resource/actor và xử lý tenant bị suspend khi job đang chạy.

**Bài 7 — Support:** thiết kế just-in-time access, purpose, approval, expiry và audit thay cho admin role dùng chung.

**Bài 8 — Test/monitoring:** lập negative test matrix, log/metric/cảnh báo và điều kiện incident response khi phát hiện dữ liệu đã bị trả chéo tenant.

### Khung đáp án tự kiểm tra

| Hiện trạng | Rủi ro | Hướng sửa |
|---|---|---|
| Tin X-Tenant-ID | Client giả mạo tenant context | Resolve qua verified principal và membership |
| Query chỉ theo booking ID | IDOR/cross-tenant read/write | Tenant-scoped query và resource authorization |
| Cache key không tenant | Cache response của tenant khác | Tenant-scoped key và authorization cache scope |
| Worker tin tenant_id trong message | Forged/replayed message hoặc quyền cũ | Authenticate publisher, validate tenant/resource, recheck policy |
| Service role đọc mọi object | Confused deputy, blast radius lớn | Prefix/resource scope, short-lived identity và policy |
| Shared support admin | Truy cập không truy vết và vượt purpose | JIT, MFA, ticket, approval, expiry, audit |

Đáp án cần chứng minh không chỉ từ chối request mà còn không tạo side effect, không phát event, không ghi cache và không sinh export trước khi authorization hoàn tất.

## 19. Checklist trước khi đưa multi-tenant workload vào production

- [ ] Tenant model, tenant owner và membership lifecycle được định nghĩa.
- [ ] Authentication, tenant resolution và resource authorization là các bước riêng.
- [ ] Tenant context lấy từ principal/membership đã xác minh, không tin header/path/query đơn thuần.
- [ ] Mỗi query read/write/export/delete có tenant scope.
- [ ] Object-level authorization kiểm tra resource thực sự thuộc tenant và principal có quyền.
- [ ] Composite key/foreign key/RLS được sử dụng và kiểm thử với runtime database role.
- [ ] Cache key, authorization cache và invalidation có tenant scope.
- [ ] Object path, upload, download và signed URL được cấp sau authorization.
- [ ] Queue/event xác thực nguồn, tenant/resource và worker revalidate policy khi chạy.
- [ ] Search, aggregation, analytics, report và export có tenant filter server-side.
- [ ] Background job có actor, purpose, deadline, idempotency và cancellation path.
- [ ] Support/admin dùng just-in-time access, approval, expiry và audit.
- [ ] Backup, snapshot, restore và offboarding giữ đúng data ownership/retention.
- [ ] Có negative tests giữa ít nhất hai tenant cho read/write/delete/export/cache/queue.
- [ ] Có audit, cảnh báo truy cập chéo tenant và quy trình incident response.
- [ ] Có quota/fairness để một tenant không làm suy giảm dịch vụ của tenant khác.

Phân quyền và ngăn truy cập chéo tenant đòi hỏi bảo vệ cùng một ranh giới xuyên suốt identity, request, resource và mọi nơi dữ liệu được sao chép hoặc xử lý. Tenant ID chỉ là một thuộc tính; nó trở thành ranh giới bảo mật khi được ràng buộc với principal tin cậy, policy cụ thể và query/resource enforcement. Kiểm thử âm, audit và vận hành quyền có thời hạn giúp chứng minh ranh giới đó vẫn được giữ khi hệ thống mở rộng và thay đổi.
