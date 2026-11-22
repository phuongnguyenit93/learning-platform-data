# Kiến trúc đa khách thuê và lựa chọn mức cô lập dữ liệu trong microservices

## 1. Bài toán: một nền tảng phục vụ nhiều khách thuê

**Multi-tenancy (kiến trúc đa khách thuê)** là cách một nền tảng phần mềm cung cấp dịch vụ cho nhiều tổ chức, doanh nghiệp, tài khoản hoặc nhóm khách hàng gọi là **tenant**. Các tenant có thể dùng chung code và hạ tầng nhưng phải được phân biệt về danh tính, quyền truy cập, cấu hình, tài nguyên, dữ liệu và vòng đời vận hành.

Ví dụ một nền tảng quản lý bán hàng SaaS có:
- Tenant A: chuỗi cửa hàng nhỏ, vài nghìn sản phẩm.
- Tenant B: nhà phân phối, hàng triệu bản ghi và lượng truy cập cao.
- Tenant C: tổ chức yêu cầu dữ liệu phải nằm trong một quốc gia và lưu trữ riêng.
- Tenant D: khách hàng doanh nghiệp yêu cầu thời gian khôi phục, bảo mật và SLA chặt chẽ.

Cùng một microservice `order-service` có thể xử lý đơn hàng của mọi tenant, nhưng request của A tuyệt đối không được đọc, sửa hoặc suy ra dữ liệu của B. Khi B chạy một báo cáo nặng, A vẫn cần đáp ứng cam kết độ trễ. Nếu C rời nền tảng, hệ thống phải xuất, xóa và chứng minh phạm vi dữ liệu theo chính sách. Nếu D cần database riêng, sản phẩm vẫn phải giữ khả năng nâng cấp, giám sát và vận hành mà không nhân đôi toàn bộ mã nguồn.

**Cô lập dữ liệu (data isolation)** là mức ranh giới kỹ thuật và vận hành bảo đảm dữ liệu của tenant được phân vùng, truy cập và xử lý theo chính sách. Nó không chỉ là câu lệnh SQL `WHERE tenant_id = ?`; cô lập còn áp dụng cho cache, file, message broker, search index, backup, log, AI/analytics pipeline, key mã hóa và quyền của đội vận hành.

Mục tiêu:
1. Phân biệt tenant, user, account, organization, workspace và resource owner.
2. So sánh các mô hình shared-table, schema-per-tenant, database-per-tenant, cluster/account-per-tenant và hybrid.
3. Thiết kế đường đi của tenant identity từ authentication, authorization tới datastore.
4. Bảo vệ chống cross-tenant data leakage, thao tác nhầm và noisy neighbor.
5. Quản lý migration, backup/restore, data residency, onboarding/offboarding cho từng tenant.
6. Lựa chọn mức cô lập dựa trên rủi ro, tải, chi phí, số tenant và khả năng vận hành.

## 2. Tenant là ai, ranh giới nằm ở đâu?

Một **tenant** thường là đơn vị khách hàng sở hữu dữ liệu và chính sách sử dụng dịch vụ. Trong sản phẩm B2B, tenant có thể là một doanh nghiệp. Trong công cụ cộng tác, tenant có thể là một workspace. Không phải mỗi user là một tenant; một user có thể là thành viên của nhiều tenant với vai trò khác nhau.

Các định danh cần phân biệt:

| Định danh | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| User ID | `user_842` | Danh tính cá nhân hoặc service principal |
| Tenant ID | `tenant_b2f` | Phạm vi tổ chức và cô lập dữ liệu |
| Membership | `user_842` thuộc `tenant_b2f` | Quan hệ được phép tham gia tenant |
| Role / permission | `orders:read`, `billing:admin` | Quyền trong phạm vi tenant |
| Resource ID | `order_572` | Định danh đối tượng nghiệp vụ |
| Environment | `production` | Ranh giới môi trường triển khai |
| Region | `ap-southeast-1` | Khu vực đặt dữ liệu và xử lý |
| Deployment / partition | `shared-eu-2` | Nơi tenant đang được phục vụ thực tế |

Nhiều tenant có thể được đặt cùng shard nhưng không có nghĩa được chia sẻ quyền truy cập. Cũng có thể một tenant có nhiều workspace con; khi đó cần quyết định ranh giới pháp lý và quyền dữ liệu nằm ở tenant hay workspace.

**Tenant context** là thông tin đáng tin cậy mô tả request/job đang hoạt động nhân danh tenant nào. Nó có thể chứa tenant ID, effective user/service identity, scopes, policy revision, region hoặc routing key. Bản thân context phải được **xác thực và ràng buộc quyền**, không đơn giản lấy từ header do client tự gửi.

### 2.1. Không nhầm “đa khách thuê” với “đa môi trường”

Test, staging và production là ranh giới vòng đời phần mềm. Tenant A và Tenant B là ranh giới khách hàng **bên trong một môi trường**. Không dùng chung credential test và production hoặc dùng cấu hình tenant làm cơ chế thay thế network/IAM isolation môi trường.

### 2.2. Phân biệt logical và physical isolation

- **Logical isolation:** chung tài nguyên vật lý, phân quyền bằng tenant key, row-level security, namespace, policy và application routing.
- **Physical isolation:** database instance, cluster, storage account, cloud account hoặc hạ tầng tách riêng.
- **Operational isolation:** quyền vận hành, backup, khóa mã hóa, sự cố, quotas, change window và audit theo tenant.

Một tenant được cấp database riêng nhưng mọi tenant đều dùng cùng root credential và bucket backup có thể xóa chéo vẫn chưa đạt isolation vận hành mong đợi.

## 3. Bốn mô hình lưu trữ chủ đạo

### 3.1. Shared database, shared schema, shared tables

Mọi tenant chia sẻ một database và các bảng chung. Mỗi dòng dữ liệu thuộc tenant có `tenant_id`.

~~~sql
CREATE TABLE orders (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL,
    total_amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

**Ưu điểm:** ít tài nguyên, dễ thêm tenant, chạy migration một schema, thuận lợi cho SaaS có nhiều tenant nhỏ. **Nhược điểm:** rủi ro thiếu tenant predicate, lỗi join, hard delete, query analytics, noisy neighbor và khó restore một tenant độc lập.

Phù hợp khi: số tenant lớn, quy mô mỗi tenant tương đối nhỏ, yêu cầu residency tương đồng và team có cơ chế tenant enforcement mạnh từ thiết kế, test tới database.

### 3.2. Shared database, schema-per-tenant

Mỗi tenant có một schema riêng trong cùng database engine/instance, ví dụ `tenant_a.orders`, `tenant_b.orders`.

**Ưu điểm:** ranh giới namespace và quyền SQL rõ hơn shared table; một số thao tác export/restore, quản lý schema thuận tiện hơn. **Nhược điểm:** số schema, bảng, migration, catalog metadata và connection/config tăng theo tenant; vẫn dùng chung CPU, memory, I/O và instance failure domain. Với nhiều nghìn tenant, migration và catalog có thể trở thành gánh nặng.

Phù hợp khi: lượng tenant vừa phải, yêu cầu tách schema nhưng chưa muốn database instance riêng; team có automation provisioning/migration và quyền database theo schema.

### 3.3. Database-per-tenant

Mỗi tenant có database logic riêng, có thể nằm cùng server/cluster hoặc các instance khác nhau. Mỗi tenant dùng connection/database credentials và migration state riêng.

**Ưu điểm:** dễ tách quyền, giới hạn truy cập và một số thao tác backup/restore; có thể tune, chuyển vùng, scale một tenant riêng dễ hơn tùy topology. **Nhược điểm:** chi phí connection, pooling, monitoring, migration, backup và upgrade tăng; database logic riêng trong cùng instance vẫn chia sẻ phần lớn tài nguyên và miền lỗi.

Cần phân biệt **database logic riêng trên chung database server** với **instance/cluster riêng**. Hai phương án có mức cách ly tài nguyên, giới hạn lỗi và chi phí rất khác.

### 3.4. Cluster/account-per-tenant hoặc deployment chuyên biệt

Khách thuê lớn dùng database, cache, broker, compute, VPC/project/cloud account riêng, thậm chí region chuyên biệt.

**Ưu điểm:** ranh giới mạnh về tài nguyên, quyền, dữ liệu, độ ổn định, tùy chỉnh compliance và năng lực khôi phục. **Nhược điểm:** tăng chi phí, drift cấu hình, số lượng môi trường và gánh nặng nâng cấp, quan sát, security patching.

Phù hợp với tenant có yêu cầu doanh nghiệp hoặc pháp lý đặc biệt, khối lượng lớn, cần isolation cao và có mô hình tính phí hỗ trợ.

### 3.5. So sánh nhanh

| Tiêu chí | Shared tables | Schema riêng | Database riêng | Cluster/account riêng |
| --- | --- | --- | --- | --- |
| Chi phí mỗi tenant | Thấp | Thấp–vừa | Vừa–cao | Cao |
| Provisioning tenant mới | Nhanh | Cần tạo schema | Cần tạo DB/pool | Cần IaC/workflow đầy đủ |
| Cô lập SQL/data namespace | Chủ yếu policy/tenant_id | Mạnh hơn ở namespace/role | Rõ hơn theo DB | Mạnh hơn ở hạ tầng |
| Cô lập CPU/I/O | Thấp | Thấp | Phụ thuộc cùng hay khác instance | Cao nếu tài nguyên tách |
| Migration schema | Một nhóm bảng | Theo từng schema | Theo từng database | Theo từng deployment |
| Restore một tenant | Khó nếu dữ liệu xen kẽ | Tùy engine và quan hệ | Thường đơn giản hơn | Tách biệt nhất |
| Số lượng tenant rất lớn | Thuận lợi hơn | Dễ chịu chi phí catalog | Tốn vận hành | Rất tốn vận hành |
| Tùy chỉnh tenant | Khó tùy biến schema sâu | Linh hoạt hơn nhưng tăng drift | Có thể tùy chỉnh có kiểm soát | Linh hoạt nhất |
| Rủi ro cross-tenant bug | Cao nếu thiếu guard | Vẫn có nếu routing/role sai | Vẫn có nếu chọn sai DB | Giảm nhưng không bằng 0 |
| Residency/retention riêng | Cần phân vùng/chính sách | Một số giới hạn | Dễ thiết kế hơn | Linh hoạt nhất |

Bảng là đánh đổi tổng quát, không phải bảo đảm bảo mật mặc định. **Một hệ thống shared-table với RLS và quy trình kỹ thuật tốt có thể an toàn hơn một hệ thống database-per-tenant nhưng quyền quản trị và credential bị chia sẻ tùy tiện.**

## 4. Mô hình hybrid: một nền tảng, nhiều isolation tier

Trong nhiều sản phẩm SaaS, mô hình phù hợp không phải chọn duy nhất một loại. Có thể dùng:
- Tier tiêu chuẩn: shared table trong một pool database.
- Tier doanh nghiệp: database riêng, vẫn dùng chung application compute.
- Tier regulated: database, key, region và compute chuyên biệt.
- Tenant rất lớn: shard hoặc cluster riêng theo nhu cầu năng lực.

~~~mermaid
flowchart TD
    U[Client / API request] --> ID[Authentication & tenant authorization]
    ID --> RES[Tenant directory / routing service]
    RES --> APP[Shared stateless services]
    APP --> ROUTE{Tenant placement}
    ROUTE --> S[Shared DB pool + RLS]
    ROUTE --> D[Dedicated tenant DB]
    ROUTE --> R[Dedicated region/cluster]
    S --> OBS[Metrics / audit / backup policies]
    D --> OBS
    R --> OBS
~~~

**Tenant directory** là nguồn mapping `tenant_id → isolation tier, shard/database, region, state, config revision`. Nó không được cho phép client tự chọn database bằng một giá trị tự do. Cần version hóa placement, kiểm soát quyền đọc và cache directory với chính sách invalidation phù hợp.

Mô hình hybrid giúp tenant tăng quy mô mà không buộc thay toàn bộ sản phẩm, nhưng đặt ra bài toán chuyển tenant giữa các tier với cutover an toàn, dữ liệu đúng và rollback rõ ràng.

## 5. Tiêu chí lựa chọn mức cô lập

Một phương pháp ra quyết định bắt đầu bằng nhu cầu, không bắt đầu bằng công nghệ:

1. **Độ nhạy dữ liệu:** dữ liệu cá nhân, tài chính, hợp đồng, bí mật kinh doanh hay hồ sơ pháp lý.
2. **Yêu cầu compliance và residency:** dữ liệu ở quốc gia/vùng nào, được sao lưu tới đâu, ai được quản trị.
3. **Quy mô tenant:** số user, traffic, dung lượng, tốc độ tăng, tải burst và workload analytics.
4. **Mức chấp nhận noisy neighbor:** liệu query tenant lớn có được làm tăng p99 của tenant khác?
5. **SLA/SLO:** latency, availability, RTO/RPO, maintenance window và yêu cầu phục vụ riêng.
6. **Đặc tính truy cập:** chủ yếu online transaction, event streaming, search hay batch analytics.
7. **Tùy biến:** khác biệt schema, extension, phiên bản, encryption key hoặc integration.
8. **Vòng đời:** onboarding/offboarding, export, backup/restore và khả năng di chuyển tenant.
9. **Khả năng vận hành:** số lượng database/cluster team có thể patch, migrate, backup, monitor an toàn.
10. **Kinh tế:** chi phí nền trên mỗi tenant so với doanh thu và rủi ro vi phạm hợp đồng.

### 5.1. Ma trận quyết định thực tế

| Nhu cầu | Mô hình nên xem xét đầu tiên | Tại sao |
| --- | --- | --- |
| Hàng chục nghìn tenant nhỏ, schema đồng nhất | Shared table + tenant_id + RLS | Provisioning và chi phí hiệu quả |
| Vài trăm tenant, cần namespace và migration linh hoạt | Schema-per-tenant | Tách schema nhưng chia sẻ database runtime |
| Tenant yêu cầu restore/retention riêng | Database-per-tenant | Dễ xác định nguồn dữ liệu và recovery scope hơn |
| Tenant có workload đột biến rất lớn | DB/shard hoặc cluster riêng | Giảm noisy neighbor trên shared resource |
| Tenant có giới hạn dữ liệu theo quốc gia | Regional placement có kiểm chứng | Đảm bảo storage, backup và processing đúng khu vực |
| Tenant cần hạ tầng và key quản trị độc lập | Dedicated account/cluster + key | Ranh giới IAM, blast radius và vận hành rõ |
| Tenant tăng từ nhỏ lên lớn | Hybrid + migration path | Mở rộng tier mà không thay interface sản phẩm |

Không nên xem mô hình “dedicated” là điều kiện duy nhất để tuân thủ một quy định. Tuân thủ còn phụ thuộc chính sách truy cập, lưu trữ, xóa, logging, hợp đồng, kiểm soát tổ chức và bằng chứng kiểm toán.

### 5.2. Hỏi trước về cross-tenant analytics

Một số tổ chức muốn báo cáo tổng hợp dữ liệu nhiều tenant. Nếu analytics cần truy cập tập trung, không nên vô tình mở quyền trực tiếp vào database nghiệp vụ cho một service thông thường. Có thể đưa dữ liệu đã được phân loại, pseudonymize/aggregate theo cơ sở pháp lý và quyền phù hợp qua pipeline chuyên biệt vào data warehouse. Cross-tenant aggregation là **ngoại lệ được kiểm soát**, không phải lý do bỏ tenant predicate.

## 6. Tenant identity: từ request đến kho dữ liệu

Một request đi qua nhiều lớp:

~~~text
Browser / API client
  → Identity provider (access token)
  → API Gateway (authentication)
  → Application (membership + authorization)
  → Tenant context (trusted)
  → Data access routing / RLS
  → Cache / DB / object store
  → Audit log / metrics
~~~

### 6.1. Nguồn tenant ID đáng tin

Tenant ID có thể lấy từ token claim, subdomain hoặc đường URL như `/tenants/{id}/orders`. Dù xuất hiện ở đâu, server phải **xác minh user/service identity có quyền đối với tenant đó**. Đừng lấy `X-Tenant-Id` tự khai báo rồi truy vấn database mà không kiểm tra membership.

Đặc biệt với user thuộc nhiều tenant, frontend có thể chọn active tenant, nhưng backend vẫn kiểm tra:
- Token còn hợp lệ, chữ ký/issuer/audience được xác minh.
- User hoặc service principal đang có membership đúng tenant.
- Role/permission phù hợp action và resource.
- Tenant còn active, không bị suspended/đang xóa.
- Chuyển tenant có ghi lại audit event khi cần.

**Authentication khác authorization.** Đăng nhập thành công vào nền tảng không đồng nghĩa được đọc dữ liệu của mọi tenant.

### 6.2. Không tin client-supplied tenant_id trong body

Ví dụ request:

~~~http
POST /api/orders
Authorization: Bearer <token-for-tenant-A>
Content-Type: application/json

{
  "tenantId": "tenant-B",
  "productId": "product-42",
  "quantity": 1
}
~~~

Nếu handler lưu `tenantId` từ JSON mà không đối chiếu, người dùng A có thể ghi dữ liệu vào B. Cách đúng là **lấy tenant từ authorization context đã xác thực**; với payload có trường tenant phải kiểm tra khớp và dùng một nguồn canonical.

### 6.3. Context xuyên RPC và async

Một call `order-service → inventory-service` cần truyền tenant identity hoặc một delegated token được xác thực. Header nội bộ không tự đáng tin chỉ vì truyền qua mạng riêng. Có thể dùng mTLS/workload identity kết hợp claims được ký hoặc policy cấp quyền theo service.

Với message broker, event có thể chứa tenant ID và aggregate ID; consumer phải xác nhận producer/workload được phép phát event, schema hợp lệ, version và quyền xử lý. Không tin mọi payload của topic chung như một nguồn identity tuyệt đối.

## 7. Shared-table: thiết kế key và constraint đúng tenant

Nếu nhiều tenant cùng dùng bảng, khóa và constraint cần ngăn lẫn dữ liệu ngay cả khi logic ứng dụng có lỗi.

### 7.1. Composite primary key và foreign key

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE customers (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    email TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, email)
);

CREATE TABLE orders (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
      REFERENCES customers(tenant_id, customer_id)
);
~~~

Foreign key `(tenant_id, customer_id)` bảo vệ khỏi một order thuộc tenant A trỏ nhầm customer của B, nếu dữ liệu tuân thủ constraints. `UNIQUE (tenant_id, email)` cho phép cùng email xuất hiện ở các tenant khác nhau khi chính sách nghiệp vụ cho phép.

ID có tính duy nhất toàn cục (UUID) vẫn không thay thế tenant guard. Một `SELECT ... WHERE order_id = ?` có thể vô tình trả bản ghi tenant khác nếu code không thực thi isolation đúng. Thiết kế schema và authorization nên là các lớp bảo vệ độc lập.

### 7.2. Index theo tenant và hot partitions

Các truy vấn thường có dạng:

~~~sql
SELECT order_id, status
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :from_time
ORDER BY created_at DESC
LIMIT 100;
~~~

Index phù hợp có thể là:

~~~sql
CREATE INDEX ix_orders_tenant_created
  ON orders (tenant_id, created_at DESC);
~~~

Index thực tế phải được quyết định theo workload và query plan. Nếu `tenant_id` luôn là filter chính, đặt tenant_id đầu composite index thường hữu ích; nhưng không có một thứ tự cột tối ưu cho mọi truy vấn. Cần xem selectivity, sort, query frequency và write amplification.

Khi tenant rất lớn, shared table có thể gặp skew, bloat, lock contention và khó partitioning. Có thể partition/hash theo tenant, thời gian hoặc routing sang shard khác; mỗi lựa chọn có trade-off về query và migration.

## 8. Row-Level Security (RLS) trong PostgreSQL

**Row-Level Security** là cơ chế database enforce điều kiện đọc/ghi theo từng row. Đây là lớp phòng vệ quan trọng cho shared-table, nhất là khi developer quên tenant predicate trong truy vấn.

Ví dụ chính sách minh họa:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_policy
ON orders
USING (
  tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
  tenant_id = current_setting('app.tenant_id', true)::uuid
);

ALTER TABLE orders FORCE ROW LEVEL SECURITY;
~~~

`USING` áp dụng cho những row được đọc/sửa/xóa theo policy; `WITH CHECK` áp dụng cho row được insert hoặc giá trị mới khi update. Nếu tenant setting chưa có, điều kiện bằng NULL không thỏa mãn và truy cập bị chặn trong trường hợp hoạt động theo policy mong muốn.

**Những điều kiện bắt buộc để RLS có hiệu quả:**
- Application role không phải superuser và không có `BYPASSRLS`.
- Kiểm soát vai trò chủ bảng; owner có thể bypass RLS trừ khi dùng `FORCE ROW LEVEL SECURITY` theo cơ chế của PostgreSQL.
- Tất cả bảng tenant-scoped liên quan được policy đúng, bao gồm bảng phụ, view và đường SQL khác.
- Tenant context được đặt **bên trong transaction** và lấy từ identity đã được xác thực.
- Tránh SQL injection có khả năng thay đổi session config hoặc chạy code với quyền cao.
- Kiểm soát security-definer functions, migration jobs và tài khoản quản trị.
- Test quyền SELECT, INSERT, UPDATE, DELETE, JOIN, aggregate, bulk import/export.
- Không dùng RLS thay cho authorization cấp resource và thao tác nghiệp vụ.

### 8.1. Thiết lập tenant theo transaction

Với connection pooling, đặt biến session rồi quên reset có thể làm request sau nhận context của tenant trước. Một cách tiếp cận là dùng `SET LOCAL` hoặc `set_config(..., true)` trong transaction:

~~~sql
BEGIN;
SELECT set_config('app.tenant_id', '11111111-1111-4111-8111-111111111111', true);
SELECT order_id, status FROM orders;
COMMIT;
~~~

Tham số thứ ba `true` khiến cấu hình là **transaction-local** theo cơ chế PostgreSQL. Trong ứng dụng, giá trị tenant phải được truyền bằng parameter binding phù hợp, không nối raw string vào SQL. Nếu ORM/query chạy ngoài transaction hoặc trước khi set tenant, cần xử lý fail closed.

Đây không phải quyền bảo mật siêu nhiên: session variable được set bởi application role có thể bị thao túng nếu attacker có khả năng chạy SQL tùy ý dưới cùng role. RLS là **defense in depth**, không thay thế chống SQL injection, least-privilege DB roles và auth.

### 8.2. Kiểm thử RLS

Một bộ test tối thiểu:
1. Tenant A có order A1, tenant B có order B1.
2. Context A SELECT/COUNT/JOIN chỉ thấy A.
3. Context B chỉ thấy B.
4. Context A cố INSERT row mang tenant B phải bị chặn.
5. Context A cố UPDATE tenant_id của row sang B phải bị chặn.
6. Không set tenant context phải không được đọc dữ liệu tenant-scoped.
7. Reuse pooled connection giữa A và B không làm lộ dữ liệu.
8. Background job không có tenant context không được vô tình bypass.
9. Đường export/report và admin API được kiểm thử riêng.
10. Migration/maintenance role có quyền cao chỉ dùng theo policy vận hành.

Khi schema có dữ liệu “global” dùng chung cho mọi tenant, phải định nghĩa những bảng nào được đọc chung và không gắn tenant predicate mù quáng vào mọi query. Bảng global cần được bảo vệ quyền ghi phù hợp và phân biệt rõ với dữ liệu tenant-private.

## 9. Schema-per-tenant: routing và quản lý namespace

Một cách triển khai dùng cùng model/schema logic nhưng tạo namespace cho mỗi tenant. Ví dụ:

~~~text
database shared_saas
  ├── tenant_a.orders
  ├── tenant_a.customers
  ├── tenant_b.orders
  └── tenant_b.customers
~~~

Điểm cần chú ý:
- Không lấy tên schema trực tiếp từ input client rồi nội suy thành SQL identifier.
- Tenant directory mapping `tenant_id → schema_name` được kiểm soát và allowlist.
- DB role chỉ có quyền schema cần thiết nếu mô hình truy cập cho phép.
- Connection pool và search_path phải được đặt/khôi phục đúng; pooling tạo nguy cơ leakage nếu session state rò.
- Migration chạy cho mọi schema, có version tracking và khả năng retry.
- Metadata/catalog cost tăng theo số tenant và đối tượng database.
- Backup/restore một schema có thể cần xử lý dependency, extension và global resources.

Dùng schema không bảo đảm cô lập hiệu năng: tất cả schema vẫn tranh CPU, I/O, WAL, connection cap và instance-level maintenance.

## 10. Database-per-tenant: routing, pool và credentials

Với database riêng, application thường cần chọn `DataSource` hoặc connection pool dựa trên tenant placement. Một yêu cầu quan trọng: **chỉ lookup placement từ danh mục tin cậy**, không tạo URL database từ tên tenant gửi qua request.

Mô hình:

~~~text
Validated tenant context
    ↓
Tenant directory (tenant -> database connection reference)
    ↓
Pool manager / tenant-aware DataSource
    ↓
Database của tenant
~~~

### 10.1. Rủi ro connection explosion

Giả sử có 1.000 tenant, mỗi database được gán một pool 10 kết nối và mọi pool luôn mở đủ 10 kết nối. Tổng số kết nối tiềm năng là **10.000**, có thể vượt năng lực server và tốn bộ nhớ dù hầu hết tenant không hoạt động.

Các lựa chọn:
- Lazy pool creation và idle pool eviction.
- Hạn chế pool size theo workload và tenant tier.
- Proxy/connection pooler với chế độ tương thích transaction semantics.
- Scale theo shard hoặc nhóm tenant thay vì khởi tạo mọi DB cùng lúc.
- Theo dõi tổng connection và áp lực database trước khi thêm replica ứng dụng.

Database-per-tenant thường làm bài toán **control plane provisioning, credential rotation, migration và monitoring** nặng hơn. Cần có service quản lý lifecycle, không dùng thao tác thủ công cho mỗi tenant.

### 10.2. Cấp quyền DB

Mỗi tenant có credential riêng giúp giảm blast radius khi một credential lộ, nhưng chỉ đúng nếu quyền được giới hạn tới đúng database và secret store. Nếu root credential được nhúng trong mọi pod, ý nghĩa cách ly bị suy giảm đáng kể. Application workload identity và secret manager nên map tới những database được phép.

## 11. Tách compute, database, cache và broker: isolation là nhiều trục

Một tenant có database riêng vẫn có thể chia sẻ:
- API pod/worker pool.
- Redis cluster.
- Kafka broker và consumer group.
- Object storage bucket hoặc search cluster.
- CI/CD runner, secret manager, IAM.
- Observability backend và admin console.

Do đó nên mô tả isolation theo vector:

`Isolation = (compute, data, network, identity, keys, backups, observability, operations)`

Ví dụ:
- Tier Standard: shared compute, shared DB với RLS, shared Redis với key namespace, IAM theo service.
- Tier Enterprise: shared stateless compute, DB riêng, secret riêng, backup riêng.
- Tier Regulated: compute/account/network/DB/keys/backup riêng, giám sát qua control plane có quyền giới hạn.

Không gắn một nhãn “single tenant” hoặc “dedicated” mà bỏ qua những tài nguyên còn chia sẻ. Tài liệu kiến trúc và hợp đồng cần mô tả đúng các trục có giá trị đối với khách hàng.

## 12. Cô lập cache và tránh cross-tenant cache leak

Ví dụ cache product price:
- Key **không an toàn**: `product:42` nếu giá khác nhau theo tenant.
- Key **tốt hơn**: `tenant:<tenantId>:product:42:price:<currency>`, với quy tắc canonicalization.
- Entry chứa tenant ID/owner khi cần để kiểm tra lúc đọc.
- Cache key phải phân biệt permission scope, locale, feature flag nếu chúng thay đổi response.

Cache nhiều tầng gồm in-process cache, Redis, CDN/API gateway. Nếu Redis key đúng nhưng HTTP cache trả lại response cá nhân hóa của tenant B cho A thì hệ thống vẫn lộ dữ liệu. Với dữ liệu tenant-private, phải cấu hình HTTP Cache-Control, Vary/cache key, authorization và CDN policy thích hợp.

**Đừng dựa vào tiền tố key làm hàng rào bảo mật duy nhất.** Có thể cần Redis ACL/instance riêng hoặc keyspace/account separation theo tier; đồng thời giới hạn command nguy hiểm, bulk delete và credential scope.

### 12.1. Invalidation đúng tenant

Khi ProductUpdated của tenant A xảy ra, consumer chỉ invalidate key A liên quan. Một sự kiện thiếu tenant ID có thể xóa nhầm dữ liệu tenant khác hoặc gây cache miss storm toàn hệ thống.

Event nên có `tenantId`, `aggregateId`, `version`, `eventId` và nguồn phát tin cậy. Handler kiểm tra context và version, xử lý idempotent, và không cho event từ tenant A ghi bản sao tenant B.

## 13. Cô lập object storage và tài liệu tải lên

File và ảnh thường nằm ngoài database:
- Bucket riêng theo tenant, hoặc bucket chung với prefix được kiểm soát.
- IAM policy/resource policy ràng buộc tenant identity với object path.
- Không dùng mỗi một tên file như `invoice.pdf` để xác định quyền.
- Signed URL phải ngắn hạn, đúng method/object/tenant và không bị phát cho user khác.
- Server kiểm tra tenant ownership trước khi tạo URL tải xuống.
- Metadata/DB record liên kết object key với tenant để hỗ trợ retention, export, delete.
- Backup/versioning và lifecycle của storage phù hợp chính sách tenant.

Một URL khó đoán không phải thay thế authorization. Nếu tenant A biết object key B, server không được cho phép đọc chỉ vì cùng bucket.

### 13.1. Cross-tenant path traversal và upload

Không ghép raw path từ client vào storage key mà không chuẩn hóa. Kiểm soát tên file, content type, malware scanning khi cần, size quota, object ownership, overwrite behavior và upload destination. Tên tenant nên là opaque ID được server cấp, không phải chuỗi tổ chức có thể gây lỗi path.

## 14. Cô lập message broker và event processing

Multi-tenant broker có thể sử dụng:
1. Topic/queue riêng theo tenant.
2. Topic chung, message có tenant ID và phân vùng theo tenant/aggregate.
3. Broker/namespace/cluster riêng cho tenant quan trọng.
4. Hybrid: shared cho long tail, dedicated cho tenant lớn.

Các đánh đổi:
- **Topic per tenant:** quyền và quota tách tốt hơn nhưng số topic/partition/consumer tăng.
- **Shared topic:** ít đối tượng hạ tầng, thuận lợi vận hành; consumer phải kiểm soát tenant context, filtering và fairness cẩn thận.
- **Dedicated broker:** isolation cao hơn nhưng chi phí và replication/monitoring tăng.

Mỗi message phải ràng buộc đúng tenant nguồn. Không tin `tenantId` payload trần nếu bất kỳ producer nào có thể publish tự do vào topic. Dùng authenticated producer identity, ACL, schema validation và trace/audit.

### 14.1. Consumer lag và noisy neighbor

Một tenant gửi triệu message có thể làm chậm tenant khác trên cùng consumer pool. Cần fairness scheduler hoặc quota per tenant, backpressure, partitioning phù hợp, dead-letter handling và timeouts.

Lưu ý việc partition Kafka theo tenant ID có thể làm một tenant lớn chiếm một partition và không scale tốt; có thể kết hợp `tenantId + aggregateId` hoặc chiến lược shard riêng nhưng phải hiểu ordering semantics. Không mặc định partition theo tenant duy nhất khi một tenant có tải lớn.

### 14.2. Async context và correlation

Trong Java, thread-local tenant context của HTTP request không tự truyền qua executor, scheduler, Kafka listener hoặc reactive pipeline. Worker phải lấy tenant identity từ một nguồn tin cậy gắn vào job/message, thiết lập context cho phạm vi xử lý và **xóa trong finally** hoặc dùng cơ chế context propagation theo framework. Rò tenant context giữa pooled threads có thể gây lỗi cross-tenant nghiêm trọng.

## 15. Cô lập search index, vector store và analytics

Dữ liệu tenant có thể được sao chép sang Elasticsearch/OpenSearch, warehouse hoặc vector database. RLS của PostgreSQL **không tự bảo vệ các bản sao này**.

Với search:
- Index per tenant hoặc shared index có tenant filter được enforce phía server.
- Query, facet, autocomplete, count và highlighting đều phải tuân tenant scope.
- Search document chứa tenant ID và source version.
- Delete/move tenant phải xóa/reindex dữ liệu liên quan.
- Role/search API không cho bypass tenant filter tùy tiện.
- Snapshot/search backup xử lý retention và residency.

Với vector search hoặc AI retrieval:
- Metadata filter tenant phải được áp dụng trong truy vấn và kiểm tra kết quả.
- Các vector/embedding là dữ liệu dẫn xuất có thể chứa thông tin nhạy cảm.
- Không bỏ tenant scope khi rerank, cache kết quả, fetch document gốc hoặc trích dẫn.
- Test tình huống truy vấn tương tự semantic trả nhầm tài liệu tenant khác.
- Quản lý deletion/re-embedding khi tài liệu nguồn bị thu hồi.

Với analytics:
- Pipeline CDC/ETL lưu tenant provenance.
- Access policy áp dụng cả raw/staging/derived tables.
- Dữ liệu cross-tenant chỉ tổng hợp khi có quyền và mục đích rõ ràng.
- Audit ai đã export, chia sẻ hoặc tải dữ liệu tenant.

## 16. API authorization: RBAC, ABAC và ownership

**RBAC** gán vai trò (viewer, editor, admin) trong tenant. **ABAC** đánh giá thuộc tính như tenant, owner, trạng thái tài liệu, nhãn dữ liệu, region, mức nhạy cảm và policy.

Một rule ở order-service có thể là:

~~~text
ALLOW readOrder when
    authenticatedUser IS memberOf(context.tenant)
    AND user HAS permission orders:read IN context.tenant
    AND requestedOrder.tenantId == context.tenantId
    AND requestedOrder.visibilityPolicy ALLOWS thisUser
ELSE DENY
~~~

Database RLS bảo vệ ranh giới tenant, nhưng quyền đọc một order **bên trong cùng tenant** có thể còn phụ thuộc role, team hoặc người sở hữu. Không nhầm `tenantId` đúng với đủ quyền nghiệp vụ.

### 16.1. Một user thuộc nhiều tenant

Khi user chuyển tenant:
- Backend xác minh membership ở mỗi request hoặc theo policy phiên được xác thực.
- Session/token phải xác định tenant context hoặc reauthorization đúng.
- Không để tab trình duyệt A vô tình gửi mutation tới tenant B sau khi đổi active tenant.
- Cache client/query key chứa tenant ID để tránh hiển thị dữ liệu từ tenant trước.
- Logout/revoke membership làm các quyền tương ứng không còn hiệu lực theo yêu cầu an toàn.

### 16.2. IDOR/BOLA

Insecure Direct Object Reference (IDOR) / Broken Object Level Authorization (BOLA) thường xuất hiện khi endpoint `GET /orders/{orderId}` chỉ lookup bằng orderId rồi trả kết quả. Dù UUID khó đoán, vẫn phải xác minh tenant và ownership. ID khó đoán làm giảm khả năng dò, **không phải quyền truy cập**.

## 17. Ví dụ Java/Spring Boot: tenant context đúng phạm vi

Ví dụ tối giản cho tầng xử lý yêu cầu:

~~~java
public record TenantPrincipal(
    String userId,
    String tenantId,
    Set<String> permissions
) {}

public final class TenantContextHolder {
    private static final ThreadLocal<TenantPrincipal> CURRENT =
        new ThreadLocal<>();

    public static void set(TenantPrincipal principal) {
        CURRENT.set(principal);
    }

    public static TenantPrincipal require() {
        TenantPrincipal principal = CURRENT.get();
        if (principal == null) {
            throw new IllegalStateException("Missing tenant context");
        }
        return principal;
    }

    public static void clear() {
        CURRENT.remove();
    }
}
~~~

Đây là skeleton minh họa, cần import `java.util.Set` và tích hợp đúng Spring Security. Chỉ cho phép code đã xác thực và kiểm tra membership đặt context. Không tạo principal từ một HTTP header chưa được kiểm chứng.

Với servlet filter, khung xử lý:

~~~java
try {
    TenantPrincipal trustedPrincipal =
        tenantAuthorizer.resolveAndAuthorize(request);
    TenantContextHolder.set(trustedPrincipal);
    filterChain.doFilter(request, response);
} finally {
    TenantContextHolder.clear();
}
~~~

Các kiểu `tenantAuthorizer`, `request`, `response` và `filterChain` phụ thuộc dự án. ThreadLocal chỉ phù hợp luồng servlet đồng bộ tương ứng; **không áp dụng máy móc cho WebFlux hoặc asynchronous execution**. Trong Reactor, sử dụng Reactor Context và security context propagation theo framework; tránh việc nhầm ThreadLocal giữa các nonblocking requests.

### 17.1. Thiết lập RLS trong cùng transaction

Một service đọc theo tenant có thể dùng transaction boundary và đặt tenant context trong kết nối, ví dụ pseudocode:

~~~text
tenant = validatedTenantFromSecurityContext()
BEGIN TRANSACTION
  SELECT set_config('app.tenant_id', tenant.uuid, true)
  SELECT ... FROM orders ...
COMMIT OR ROLLBACK
~~~

Những câu SQL nghiệp vụ phải chạy **trong cùng transaction/connection**. Nếu dùng ORM và connection pooling, cần bảo đảm việc set tenant xảy ra trước câu query đầu tiên; không relying vào session state còn sót. Đối với exception, rollback để database giải phóng transaction-local setting.

Với RLS, truy vấn không có tenant context phải fail closed. Background processing cần context xác thực từ job và transaction của riêng job, không mượn tenant gần nhất trong thread pool.

## 18. Data isolation cho background jobs và batch processing

Các công việc không khởi phát từ HTTP request dễ bị bỏ quên:
- Scheduled invoice generation.
- Rebuild search index.
- Notification fan-out.
- Data retention/deletion.
- Billing aggregation.
- Import/export lớn.
- Database migration.

Với job cụ thể của tenant, record nên có tenantId, jobId, owner/issuer, permissions hoặc một scope xử lý hợp lệ, placement version và idempotency key khi phù hợp.

~~~json
{
  "jobId": "job-9021",
  "tenantId": "tenant-b2f",
  "type": "EXPORT_ORDERS",
  "requestedBy": "user-842",
  "authorizedScope": "orders:export",
  "idempotencyKey": "export-2026-11-12-tenant-b2f"
}
~~~

Ví dụ chỉ minh họa payload. Trước khi xử lý, worker phải xác thực nguồn job, kiểm tra quyền hiện hành nếu policy yêu cầu, truy vấn đúng datastore tenant và ghi audit. Không chấp nhận một job tùy ý từ queue với tenantId giả mạo.

**Platform-wide jobs** thực sự cần đọc nhiều tenant phải có identity và allowlist riêng, audit và thiết kế batch theo từng tenant để giới hạn blast radius. Không dùng tài khoản root database cho mọi tác vụ chỉ vì tiện.

## 19. Noisy neighbor và cách giới hạn tài nguyên

**Noisy neighbor** xảy ra khi một tenant dùng quá nhiều CPU, I/O, memory, connection, queue hoặc quota API khiến tenant khác suy giảm. Vấn đề tồn tại ở shared-table, schema-per-tenant và cả database-per-tenant nếu cùng instance/compute.

Ví dụ Tenant B chạy export 50 triệu dòng:
- Connection pool bị chiếm.
- Disk I/O và DB CPU tăng.
- Query cache bị đẩy khỏi bộ nhớ.
- p99 API của Tenant A tăng dù A không thay traffic.
- Background jobs của A bị chờ phía sau hàng đợi của B.

Biện pháp:
1. **Rate limit per tenant** cho requests, read/write operations và external API calls.
2. **Concurrency budget** theo tenant và operation, nhất là export/report.
3. **Queue/fair scheduler** để mỗi tenant có phần năng lực xử lý tối thiểu.
4. **Database query timeout/statement timeout** và quota hợp lý.
5. **Connection pool partitioning** hoặc semaphore theo tenant.
6. **Resource quotas** cho background workers và dedicated tenant workloads.
7. **Workload tiering:** tách OLTP khỏi analytics, read replicas hoặc warehouse khi phù hợp.
8. **Hot tenant migration:** chuyển tenant quá lớn sang shard/DB/cluster riêng.

Một quota quá chặt có thể khiến tenant trả phí cao bị throttled vô cớ; cần gắn với SLA và capacity plan. Tối ưu noisy neighbor không chỉ giảm chi phí mà còn bảo vệ tính dự đoán của latency.

### 19.1. Per-tenant metrics nhưng tránh cardinality bùng nổ

Nên đo tổng latency/error theo service/tier/region và có cách drill-down tenant lớn/top offender. Nếu có hàng triệu tenant, gắn tenant ID vào mọi Prometheus metric có thể gây cardinality rất cao. Có thể dùng:
- Sampled logs/traces với tenant metadata theo chính sách dữ liệu.
- Aggregation theo tier/shard, tenant top-K hoặc analytics riêng.
- Audit event và billing counters có retention phù hợp.
- Per-tenant dashboard được tạo theo nhu cầu có giới hạn.

Không đưa PII hoặc token vào metric labels. Tenant ID có thể được coi là dữ liệu nhạy cảm tùy bối cảnh; thiết kế quyền truy cập telemetry phù hợp.

## 20. Mã hóa, secret và tenant-specific keys

Cô lập dữ liệu có thể cần mã hóa ở nhiều lớp:
- **Transport:** TLS/mTLS giữa service và datastore.
- **At rest:** mã hóa database, storage, backup.
- **Application/field level:** mã hóa các trường nhạy cảm trước khi lưu.
- **Tenant-specific envelope keys:** key cấp cho từng tenant hoặc nhóm tenant theo policy.
- **KMS/HSM policy:** quyền decrypt theo workload và tenant scope.

**Key per tenant** tạo khả năng phân tách quyền và rotation/crypto-erasure trong một số trường hợp nhưng tăng chi phí, độ phức tạp và phụ thuộc key management. Không được suy ra “xóa key là đủ xóa tất cả dữ liệu” nếu bản plaintext tồn tại ở cache, log, backup hoặc hệ thống dẫn xuất.

Khi key rotation:
1. Theo dõi key version dùng cho ciphertext.
2. Có kế hoạch re-encrypt hoặc decrypt bằng key cũ trong cửa sổ chuyển đổi.
3. Kiểm tra application rollout và background jobs.
4. Backup và disaster recovery phải tiếp tục giải mã được.
5. Audit quyền KMS, các lần decrypt và sự cố key unavailable.

Nếu tenant yêu cầu tự quản lý khóa (BYOK), cần tính rõ tác động khi khách hàng thu hồi key: dữ liệu có thể không truy cập được và backup vẫn tồn tại dưới ciphertext. Quy trình onboarding, rotation, revoke và recovery cần có hợp đồng rõ.

## 21. Data residency và multi-region tenants

**Data residency** giới hạn dữ liệu được lưu hoặc xử lý ở phạm vi địa lý/quyền tài phán theo yêu cầu. Không chỉ primary database phải nằm đúng region; còn:
- Backup, snapshot, replica, WAL/transaction log.
- Cache và CDN edge behavior.
- Object storage và file upload.
- Logs, traces, support tickets, alert payload.
- Analytics/warehouse, search index, embedding/vector store.
- Egress đến third-party providers và cross-region support tools.

Tenant directory cần xác định region/placement được phép. Application request routing phải không tự chuyển sang region khác chỉ vì latency thấp hơn nếu việc đó vi phạm chính sách.

### 21.1. Failover có thể xung đột residency

DR multi-region phổ biến nhưng một khách hàng có thể yêu cầu dữ liệu không rời quốc gia. Nếu region dự phòng thuộc quốc gia khác, DR đó có thể không hợp lệ. Cần thiết kế region dự phòng được phép, backup trong phạm vi phù hợp hoặc một chế độ degraded có quy trình doanh nghiệp chấp thuận.

### 21.2. Region không đồng nghĩa tenant authorization

Có dữ liệu nằm tại region yêu cầu không đảm bảo user tenant A không đọc được dữ liệu tenant B ở cùng region. Phải bảo vệ cả location và authorization.

## 22. Backup, restore và xóa dữ liệu một tenant

Trong mô hình shared-table, backup thường chứa dữ liệu của nhiều tenant. Khi Tenant A yêu cầu restore về ngày hôm qua, restore toàn DB sẽ làm mất cập nhật mới của Tenant B — điều không thể chấp nhận.

Các chiến lược:
- **Logical export theo tenant** dựa trên tenant_id và toàn bộ dependency liên quan, lưu thành artifact có kiểm chứng.
- **Database riêng:** backup/restore tương đối độc lập, nhưng cần xử lý hệ thống phụ.
- **Point-in-time copy tạm:** restore toàn DB sang môi trường cô lập, trích xuất dữ liệu tenant và merge/reconcile có kiểm soát.
- **Event log/replay:** tái dựng một số read model theo tenant nếu có đủ retention, ordering và schema compatibility.
- **Object storage:** khôi phục đúng object/prefix cùng metadata tenant.
- **Search/analytics:** reindex/rebuild tài liệu tương ứng, bảo đảm không làm mất tenant khác.

Một quy trình restore cần chốt **recovery target, consistency và merge semantics**: overwrite toàn bộ tenant? Chỉ khôi phục record bị xóa? Dùng idempotency hoặc version để tránh ghi đè dữ liệu mới? Các service khác có event nào cần replay/compensate?

**Backup của shared database không tự tạo tenant-level restore.** Tính năng này phải được thiết kế, tự động hóa và diễn tập.

### 22.1. Tenant offboarding và data deletion

Khi khách hàng rời nền tảng:
1. Xác định yêu cầu export/retention, quyền ký kết và thời điểm đóng.
2. Khóa thay đổi dữ liệu hoặc chuyển state tenant sang deprovisioning.
3. Xuất dữ liệu được phép cùng metadata/schema/version.
4. Thu hồi token, API keys, webhook, IAM, signed URLs.
5. Xóa hoặc purge dữ liệu trong database, cache, object storage, search, queue và derived stores theo chính sách.
6. Xử lý backup theo retention và khả năng xóa/giữ bắt buộc hợp pháp.
7. Ghi audit evidence: phạm vi, thời gian, hệ thống đã xử lý, exceptions còn tồn tại.
8. Giải phóng dedicated resources và quota/billing.
9. Giữ tenant tombstone/ID reservation đủ an toàn để tránh reuse định danh gây nhầm dữ liệu.

Không coi thao tác `DELETE FROM tenants WHERE id=?` là đã hoàn thành xóa dữ liệu. Dữ liệu có thể còn nằm ở object storage, event, log, warehouse, backup và index.

## 23. Tenant provisioning và lifecycle

Một tenant mới có thể qua trạng thái:

~~~mermaid
flowchart LR
    A[Requested] --> B[Validated]
    B --> C[Provisioning]
    C --> D[Active]
    D --> E[Suspended]
    E --> D
    D --> F[Deprovisioning]
    E --> F
    F --> G[Deleted / Retained metadata]
~~~

### 23.1. Provisioning idempotent

Thêm tenant có thể cần tạo:
- Tenant record và placement mapping.
- Schema/DB hoặc namespace resource.
- Credentials, keys, IAM bindings.
- Default roles, admin membership và quotas.
- Initial migration, seed dữ liệu tham chiếu.
- Object storage prefix/bucket, broker namespace.
- Dashboard/alert/billing và backup policy.

Các bước có thể thất bại giữa chừng. Nên có workflow/state machine idempotent, retry có giới hạn, compensation và audit. Không công bố tenant ở trạng thái Active trước khi ranh giới bảo mật và database migration đã sẵn sàng.

### 23.2. Suspended tenant

Tenant bị suspended do billing hoặc policy không có nghĩa dữ liệu bị xóa. Cần ràng buộc những operation còn được phép (ví dụ xem hóa đơn, export theo hợp đồng), ngăn mutation trái phép và kiểm tra background jobs có tiếp tục chạy hay không. Không dùng tenant status chỉ ở frontend.

## 24. Schema migration trên hàng nghìn tenant

Mô hình shared-table thường chạy migration một lần trên các bảng chung, nhưng tác động lớn và cần lock management. Schema-per-tenant/database-per-tenant lại cần triển khai trên nhiều namespace/DB.

Các câu hỏi:
- Có thể chạy migration online, giới hạn lock, statement timeout?
- Các tenant đang ở schema version nào?
- Migration có thể retry/idempotent không?
- Tenant nhỏ và lớn có thể được nâng cấp theo batch khác nhau?
- App có tương thích với cả schema cũ và mới trong cửa sổ rollout?
- Có tenant đã tạm suspended hoặc offline nhiều tháng?
- Rollback code có bị vướng migration không?

Mẫu **expand → migrate → contract**:
1. Expand: thêm cột/bảng/index tương thích.
2. Deploy app hỗ trợ cả cấu trúc cũ và mới.
3. Backfill dữ liệu theo batch/tenant với kiểm tra tiến độ.
4. Chuyển đường đọc/ghi khi dữ liệu sẵn sàng.
5. Contract: chỉ xóa cấu trúc cũ khi mọi tenant và consumer không còn cần.

Với database-per-tenant, control plane có thể duy trì `schema_version` từng tenant và rollout theo cohort. Không chạy hàng nghìn DDL đồng thời nếu có thể làm cạn connections, CPU hoặc I/O của cluster. Các migration thất bại phải có retry/repair policy rõ.

### 24.1. Tránh schema drift tùy tiện

Tenant doanh nghiệp đôi khi yêu cầu thêm trường riêng. Tạo bespoke schema cho mỗi tenant dễ dẫn đến phân nhánh version không kiểm soát. Có thể ưu tiên extensible attributes, JSON document có schema validation, plugin/feature flag hoặc một chiến lược module được version hóa. Chỉ cho phép schema riêng khi đã tính được chi phí upgrade/test/DR.

## 25. Di chuyển tenant từ shared sang dedicated

Tenant phát triển vượt năng lực shared pool hoặc yêu cầu compliance mới. Có thể cần move mà không làm mất cập nhật.

Các bước khái niệm:
1. Chốt nguồn và đích, schema version, placement revision và quyền truy cập.
2. Provision DB/cluster riêng, secret, policy, monitoring, backup.
3. Tạo initial snapshot/export dữ liệu tenant từ source.
4. Dùng CDC/outbox hoặc cơ chế đồng bộ incremental bắt kịp các write phát sinh.
5. Kiểm tra count/checksum theo bảng, version, quan hệ nghiệp vụ và event offsets.
6. Tạm hạn chế write hoặc dùng giao thức cutover bảo đảm **single writer**.
7. Cập nhật tenant directory placement theo revision có kiểm soát.
8. Chuyển traffic, kiểm tra read/write/business flows và stale cache.
9. Giữ source ở chế độ read-only/rollback window theo chính sách.
10. Kết thúc migration, loại bỏ dữ liệu cũ sau retention và audit.

### 25.1. Cẩn trọng với dual-write

Ghi cùng lúc vào shared và dedicated DB nghe đơn giản nhưng có thể xảy ra một write thành công, một write thất bại; nếu retry không idempotent, dữ liệu bị phân kỳ. Nên thiết kế CDC/change log, transactional outbox, sequence/version và cutover có rào chắn. Nếu dùng dual-write, phải công bố consistency model, retry, reconciliation và ownership rõ ràng.

### 25.2. Tenant directory cache

Sau cutover, một instance có thể còn cached placement cũ và tiếp tục ghi vào shared DB. Cần placement version, invalidation, fencing và kiểm soát writer để tránh split-brain. Không chỉ hạ TTL rồi hy vọng tất cả request tự chuyển đúng.

## 26. Thiết kế kiến trúc microservices và ownership

Trong hệ thống microservices, mỗi service lý tưởng sở hữu dữ liệu nghiệp vụ của mình. Nếu dùng chung tenant directory, cần tránh service khác ghi trực tiếp vào database của service sở hữu chỉ vì cùng tenant.

Ví dụ:

~~~text
Tenant API / Identity
       │
       ├── Order Service ─── Order DB (tenant isolation)
       ├── Catalog Service ─ Catalog DB (tenant isolation)
       ├── Billing Service ─ Billing DB (tenant isolation)
       └── Search / Analytics (derived tenant-scoped projections)
~~~

`order-service` có thể dùng shared DB với RLS, trong khi `billing-service` dùng DB riêng do rủi ro và retention. **Không bắt buộc mọi service dùng cùng một mô hình tenant isolation.** Cần chọn theo đặc tính dữ liệu và hợp đồng riêng của service, song tenant identity/policy, audit, provisioning và lifecycle phải nhất quán ở mức platform.

### 26.1. Cross-service transaction

Một order gồm dữ liệu ở order, inventory và billing. Không nên tạo một transaction SQL xuyên nhiều database chỉ để “giữ tenant”. Có thể dùng saga/outbox và các thao tác idempotent, nhưng mọi step phải mang tenant context tin cậy. Lỗi tenant ID ở một step có thể làm sai dữ liệu ở nhiều service, nên cần correlation/audit và test toàn luồng.

### 26.2. Tenant ownership của event schema

Event nên có tenant ID, aggregate ID, schema version, event ID và producer identity; consumer cần xác minh scope. Không phát toàn bộ hồ sơ khách hàng vào shared topic chỉ vì mọi service đều cần vài trường.

## 27. Quản trị vận hành và quyền của đội hỗ trợ

Các ranh giới cần bảo vệ cả trước lỗi vận hành:
- Support agent chỉ xem dữ liệu tenant theo ticket và quyền được phê duyệt.
- Admin console không mặc định có query cross-tenant.
- Break-glass phải có lý do, approval/notification và audit.
- Tài khoản DB migration khác application role.
- Backup operator không mặc định có quyền giải mã dữ liệu không cần thiết.
- Export dữ liệu tenant cần kiểm soát requester, phạm vi và thời hạn file.
- Secret quản lý theo môi trường, tier và tenant; rotation có kế hoạch.
- Không dùng production data trong test nếu chưa có quy trình phù hợp và loại bỏ nhạy cảm.

Một lệnh chạy nhầm `DELETE FROM orders` trên shared table có thể xóa dữ liệu của nhiều tenant. Dùng DB constraints/RLS, quyền hạn chế, review/change management, dry-run và backup/PITR; nhưng với maintenance role có quyền cao, cần thêm lớp phê duyệt và giới hạn thao tác.

### 27.1. Audit trail theo tenant

Audit event nên trả lời:
- Ai/identity nào thực hiện?
- Nhân danh tenant nào?
- Operation, resource và kết quả ra sao?
- Khi nào, từ workload/region nào?
- Có policy override hoặc break-glass không?
- Đã có dữ liệu export/delete/restore nào?
- Event có correlation ID phục vụ điều tra không?

Không lưu secret hoặc toàn bộ nội dung nhạy cảm trong audit một cách tùy tiện. Phân quyền truy cập audit log phải tách khỏi tenant data khi cần, với retention phù hợp.

## 28. SLO, billing, quota và cost attribution

Multi-tenancy cần chia chi phí và hiệu năng:
- Request rate, successful throughput, latency và error rate theo tier/tenant khi có thể.
- DB QPS, connections, storage bytes, I/O, backup volume.
- Broker messages, queue lag, job runtime.
- Object storage bytes/requests và egress.
- External API usage, AI tokens hoặc compute seconds khi phù hợp.
- Cache memory và hit ratio.

**Billing metrics** cần nguồn đếm bền và audit đủ rõ; không nhất thiết dùng Prometheus metrics có thể scrape thiếu mẫu làm cơ sở tính tiền. Với hoạt động cần chính xác, có thể ghi durable usage events/idempotent aggregations.

### 28.1. SLO theo tenant tier

Ví dụ tier Enterprise cam kết p95 thấp và RTO ngắn hơn tier Standard. Nếu tất cả đều dùng một shared DB không có quota, workload của tenant lớn có thể khiến tier khác vi phạm SLO. Chiến lược isolation tier cần gắn với capacity planning và chính sách throttle/migration.

Không suy ra chỉ cần database riêng là đạt SLA tốt hơn: ứng dụng, DNS, IAM, network, broker và external provider còn có thể chung failure domain.

## 29. Backup/DR nhiều khách thuê: lỗi toàn vùng và lỗi một tenant

Có hai lớp phục hồi:
1. **Platform disaster:** mất vùng, mất cluster, compromised shared account. Cần phục hồi nhiều tenant theo thứ tự nghiệp vụ và RTO/RPO.
2. **Tenant-specific incident:** tenant xóa nhầm dữ liệu, bị tấn công credential, yêu cầu restore một bộ dữ liệu. Cần phục hồi tenant đó mà không làm hại tenant khác.

Trong shared database, tenant restore cần bản sao tạm và trích xuất. Trong dedicated database, restore dễ cô lập hơn nhưng phải khớp các hệ thống ngoài như object storage, search và event broker. Khi khôi phục tenant B về 10:00 mà billing event đã chạy tới 10:10, cần reconciliation tránh gửi hóa đơn trùng.

### 29.1. Thử khôi phục theo isolation tier

Một DR drill tốt cần chứng minh:
- RTO/RPO theo tenant/tier đã đặt.
- Backup có thể giải mã và dùng được.
- Chỉ dữ liệu tenant mục tiêu được restore.
- Không phá tenant khác trên shared DB/cluster.
- Search, cache, file, queue và analytics được cập nhật tương thích.
- Event replay idempotent, tránh side effect lặp.
- Tenant routing và permission đúng sau khi phục hồi.

## 30. Threat model: các đường rò dữ liệu thường gặp

| Đường rò | Ví dụ | Kiểm soát |
| --- | --- | --- |
| Bỏ tenant predicate | `SELECT * FROM orders WHERE order_id=?` | RLS, repository API, test |
| Client giả mạo tenant | `X-Tenant-Id: tenant-B` | Membership và auth từ token đáng tin |
| JOIN không giữ tenant key | order A trỏ customer B | Composite FK và query scope |
| ThreadLocal không cleanup | Worker tái dùng context tenant trước | `finally`, context propagation đúng |
| Connection pooling session leak | search_path/session setting còn tenant A | Transaction-local scope/reset |
| Cache key thiếu tenant | product:42 dùng cho hai tenant | Key canonical, ACL và cache policy |
| CDN cache response private | Response B phục vụ cho A | Cache-Control/Vary và auth |
| Object storage URL sai scope | Signed URL cho invoice B | Ownership check và short-lived URL |
| Consumer dùng tenant từ payload giả | Event ghi chéo database | Producer auth, schema/ACL và authorization |
| Search index thiếu tenant filter | Search trả tài liệu tenant khác | Server-enforced filter/index policy |
| Analytics export không kiểm soát | Support tải toàn bộ khách hàng | Scope, approval và audit |
| Shared backup permissions | Operator tenant A truy cập backup B | IAM, encryption và backup boundary |
| Tenant migration cutover sai | Instance vẫn ghi source cũ | Placement version/fencing |
| Admin console quá quyền | Hỗ trợ xem mọi tenant mặc định | Least privilege, break-glass, audit |

Threat model còn cần xét side channels như response time/count/facet cho phép suy ra tồn tại dữ liệu tenant khác. Việc lọc kết quả cuối sau khi truy vấn/search tất cả dữ liệu có thể vẫn lộ aggregate count, suggestion hoặc lỗi khác biệt. Enforce scope **tại thời điểm truy vấn**, không chỉ sau khi lấy dữ liệu.

## 31. Ví dụ thiết kế đầy đủ: nền tảng quản lý đơn hàng SaaS

Giả sử một nền tảng có 12.000 tenant nhỏ, 120 tenant vừa và 8 tenant enterprise.

### 31.1. Phân tier

**Standard:** shared PostgreSQL tables, RLS, tenant ID ở PK/FK/index; rate limit và quota job. **Growth:** có thể đặt trên shard riêng hoặc schema/DB riêng nếu tải cao. **Enterprise:** database/cluster riêng theo hợp đồng; secret/backup/retention riêng, có thể yêu cầu region và KMS key riêng.

Đây là phương án minh họa. Số lượng tenant không tự quyết định tier; workload, dữ liệu và compliance cần được đánh giá.

### 31.2. Đường yêu cầu tạo đơn

1. Client gửi JWT có danh tính user; tenant được chọn trong endpoint hoặc session.
2. Gateway xác thực chữ ký/issuer/audience và chuyển identity đáng tin.
3. Order-service xác minh user còn thuộc tenant và có `orders:create`.
4. Tenant directory xác định placement và trạng thái Active.
5. Data layer chọn database/transaction; shared DB đặt RLS tenant context.
6. Order được ghi với tenant ID từ trusted context, composite constraint bảo vệ quan hệ.
7. Transaction lưu outbox event cùng tenant ID và aggregate ID.
8. Event relay publish tới broker với identity tin cậy.
9. Worker inventory xử lý với tenant scope, idempotency và quota.
10. Response, audit và telemetry ghi tenant/tier/operation ở mức cần thiết.

### 31.3. Đường đọc qua cache

1. Handler yêu cầu `orders:read`.
2. Cache key có tenant ID, resource ID và phiên bản nếu cần.
3. Nếu miss, query database theo tenant context.
4. Application kiểm tra quyền trong tenant, không chỉ membership.
5. Response private không được shared CDN lưu sai.
6. Trace/log có correlation để điều tra, không nhúng dữ liệu nhạy cảm.

### 31.4. Khi tenant Enterprise tăng gấp 10 lần

Quan sát per-tenant/tier SLO, pool pending, DB I/O, queue lag và chi phí. Nếu dùng shared pool bị ảnh hưởng, lập kế hoạch chuyển tenant sang database riêng qua snapshot + CDC + fencing + placement cutover. Sau đó chạy kiểm tra dữ liệu và traffic, theo dõi cùng digest/config version và cập nhật backup/DR.

## 32. Quy trình chọn kiến trúc từ đầu

**Bước 1 — Xác định tenant model.** Tenant đại diện ai, user có thể thuộc bao nhiêu tenant, quyền nào là global, quyền nào thuộc tenant?

**Bước 2 — Phân loại dữ liệu và hành vi.** Bản ghi nào private, shared reference, sensitive; có cross-tenant analytics không; luồng nào phải cô lập mạnh?

**Bước 3 — Định lượng scale.** Số tenant hiện tại/dự kiến, phân bố dữ liệu, top tenant traffic, burst, connections, growth và backup volume.

**Bước 4 — Xác định contract.** Data residency, retention, RTO/RPO, availability, security, export/restore riêng.

**Bước 5 — Chọn isolation tier.** Shared table/RLS, schema, database, cluster/account hoặc hybrid, có đường nâng cấp từ tier thấp lên cao.

**Bước 6 — Thiết kế trust boundary.** Tenant identity, membership, authorization, DB role, routing directory, credential/key và audit.

**Bước 7 — Bao phủ mọi bản sao dữ liệu.** Database, cache, message, object storage, search, analytics, logs, backup và hỗ trợ khách hàng.

**Bước 8 — Tự động hóa lifecycle.** Provisioning, schema migration, credential rotation, billing/quota, suspend, export, offboarding, restore.

**Bước 9 — Kiểm thử failure modes.** Cross-tenant access, pooled context leak, missing tenant predicate, hot tenant, out-of-order event, migration cutover, restore.

**Bước 10 — Gắn với vận hành.** Per-tier SLO, alert/noisy neighbor, capacity, compliance evidence và diễn tập.

## 33. Bài tập thực hành

Một công ty SaaS quản lý đơn hàng cho nhiều cửa hàng có:
- Một PostgreSQL database, bảng orders không có tenant_id trong PK.
- API dùng `X-Tenant-Id` do frontend gửi, chưa kiểm membership.
- Redis key dạng `order:{orderId}`.
- Kafka shared topic với event không chứa tenantId.
- Background job dùng một ThreadLocal tenant context nhưng không cleanup.
- Support agent có quyền SELECT mọi bảng để xử lý ticket.
- Khách hàng lớn yêu cầu database riêng và restore dữ liệu trong 30 phút.

**Yêu cầu A — Threat model:** liệt kê ít nhất 6 đường rò hoặc sai scope dữ liệu; phân loại theo API, DB, cache, event, worker và operation.

**Yêu cầu B — Thiết kế schema:** viết PK/FK/index có tenant_id cho orders/customers; giải thích lợi ích của composite FK và RLS.

**Yêu cầu C — Auth:** mô tả cách backend xác minh tenant membership và không tin header tùy ý; thiết kế với user thuộc nhiều tenant.

**Yêu cầu D — Isolation tier:** đề xuất shared-table cho nhóm nhỏ và dedicated DB cho nhóm lớn; đưa ra tiêu chí chuyển tenant gồm load, residency, RTO/RPO và cost.

**Yêu cầu E — Cô lập bản sao:** viết key Redis, event envelope, object storage policy và search filter để không lẫn tenant.

**Yêu cầu F — Cutover:** mô tả snapshot, incremental sync, fencing, placement version, reconcile, rollback window khi chuyển tenant lớn sang DB riêng.

**Yêu cầu G — Vận hành:** thiết kế quotas, alert, support break-glass và tenant-specific restore không tác động tenant khác.

Một kết quả thuyết phục phải nêu được **nguồn tenant identity đáng tin**, **ranh giới dữ liệu được thực thi ở đâu**, **những lớp có thể lộ dữ liệu dù database đã tách**, và **cách chứng minh tenant migration/restore là đúng**.

## 34. Câu hỏi tự kiểm tra

1. Tenant khác user và workspace như thế nào?
2. Vì sao `WHERE tenant_id = ?` trong application không đủ làm ranh giới bảo mật duy nhất?
3. Sự khác nhau giữa shared table, schema riêng, database riêng và instance riêng là gì?
4. Một database riêng trên shared instance có bảo đảm cách ly CPU/I/O không?
5. RLS trong PostgreSQL bảo vệ gì và khi nào role có thể bypass?
6. Tại sao setting tenant ở connection session và không reset lại nguy hiểm?
7. Vì sao token hợp lệ chưa đủ để chọn bất kỳ tenant ID?
8. Khi user thuộc nhiều tenant, cách nào tránh frontend cache hiển thị dữ liệu tenant trước?
9. Search index và CDN có thể làm lộ dữ liệu dù SQL đã đúng như thế nào?
10. Tại sao tenant ID trong event payload cần kiểm tra provenance/producer?
11. Nguy cơ noisy neighbor tồn tại ở những shared resources nào?
12. Vì sao không nên gắn tenant ID không kiểm soát vào mọi Prometheus metric?
13. Tenant-level restore khó hơn trong shared-table vì sao?
14. Vì sao replication và backup không tự đồng nghĩa với khả năng restore độc lập một tenant?
15. Điều gì khiến tenant migration dual-write bị mất consistency?
16. Kiến trúc hybrid cần tenant directory và placement revision để làm gì?
17. Data residency bao gồm những bản sao ngoài primary database nào?
18. Những điều kiện nào khiến “dedicated database” vẫn không đáp ứng yêu cầu security?
19. Khi xóa tenant, vì sao phải xét cache, warehouse, object storage, event và backup?
20. Khi nào nên chọn dedicated cluster thay vì shared-table có RLS?

## 35. Tổng kết

**Kiến trúc multi-tenancy là thiết kế ranh giới dữ liệu, quyền và tài nguyên cho nhiều khách hàng trên một nền tảng.** Shared-table tối ưu chi phí và tốc độ mở rộng số tenant nhưng đòi hỏi tenant enforcement chặt từ identity, schema, RLS tới mọi bản sao dữ liệu. Schema-per-tenant và database-per-tenant tăng khả năng phân tách, nhưng tạo chi phí quản lý namespace, connection, migration và backup. Dedicated cluster/account cho phép ranh giới mạnh hơn nhưng phải đánh đổi chi phí và độ phức tạp vận hành.

Không có một mức cô lập tối ưu cho mọi tenant. Lựa chọn cần dựa trên **độ nhạy dữ liệu, yêu cầu compliance/residency, quy mô, noisy neighbor, khả năng khôi phục, chi phí và năng lực tự động hóa**. Mô hình hybrid thường hữu ích khi nền tảng phục vụ cả hàng nghìn tenant nhỏ và một số khách hàng lớn.

Một hệ thống thực sự an toàn không chỉ ngăn `SELECT` xuyên tenant, mà còn bảo vệ cache, file, event, search, analytics, backup, log và đường hỗ trợ vận hành. Tenant ID phải bắt nguồn từ identity đã được kiểm chứng, được truyền và quản lý đúng ngữ cảnh qua microservices; mọi quyền truy cập và chuyển vị trí dữ liệu cần có audit, test và khả năng phục hồi. Khi các điều kiện đó được giải quyết ngay trong kiến trúc, nền tảng có thể tăng số tenant và đáp ứng những cấp độ cô lập khác nhau mà không đánh mất tính nhất quán và an toàn dữ liệu.
