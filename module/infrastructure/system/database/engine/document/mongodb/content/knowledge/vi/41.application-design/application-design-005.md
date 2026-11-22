# Ứng dụng nhiều khách hàng: phân tách dữ liệu, index và quyền truy cập trong MongoDB

## 1. Bài toán: một SaaS phục vụ hàng nghìn khách hàng

Một nền tảng SaaS cho phép hàng nghìn doanh nghiệp quản lý đơn hàng. Mỗi doanh nghiệp là một **tenant** (khách hàng/tổ chức có vùng dữ liệu và chính sách truy cập riêng). Trong cùng ứng dụng có:

- Tenant `north-shop` với khoảng 20.000 đơn hàng.
- Tenant `big-mart` với khoảng 60 triệu đơn hàng và truy vấn phân tích nhiều.
- Tenant `legal-firm` yêu cầu khả năng cô lập và kiểm toán chặt hơn.
- Tenant `trial-17` đang trong gói thử nghiệm, có giới hạn số request và dung lượng.

Ứng dụng có các endpoint:

```text
GET    /api/orders
GET    /api/orders/{orderId}
POST   /api/orders
PATCH  /api/orders/{orderId}
DELETE /api/orders/{orderId}
GET    /api/reports/revenue
```

Một sai sót như:

```java
orders.find(eq("_id", orderId));
```

có thể trả về đơn hàng thuộc tenant khác nếu `orderId` biết trước hoặc bị lộ. Ngược lại, thêm `tenantId` vào mỗi filter nhưng không có index tương ứng có thể làm truy vấn chậm trên toàn bộ tập dữ liệu. Nếu ứng dụng tạo một database cho mỗi tenant mà không quy hoạch, chi phí connections, indexes, migrations và vận hành có thể tăng mạnh.

Do đó multi-tenancy không chỉ là thêm field `tenantId`. Đây là thiết kế đồng thời của:

1. **Data isolation** — tenants ở chung hay tách database/cluster?
2. **Authorization** — ai được đọc, ghi, quản trị tài nguyên nào?
3. **Query safety** — tất cả đường truy vấn và ghi có gắn tenant boundary không?
4. **Indexing** — sử dụng tài nguyên chia sẻ sao cho truy vấn mỗi tenant vẫn hiệu quả?
5. **Operational isolation** — tránh noisy neighbor, bảo vệ backup, migration, quota, giám sát và deletion.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **shared collection**, **collection per tenant**, **database per tenant**, **cluster per tenant** và mô hình hybrid.
- Chọn mô hình theo số tenants, mức độ cô lập, compliance, kích thước, workload và chi phí.
- Thiết kế document có `tenantId` bất biến, khóa nghiệp vụ duy nhất **trong phạm vi tenant** và references không vượt boundary.
- Viết Java MongoDB Sync Driver code ép tenant filter cho mọi CRUD, pagination, aggregation và bulk operations.
- Giải thích giới hạn của MongoDB RBAC: quyền theo resource không tự tạo row-level authorization trên documents cùng collection.
- Thiết kế compound indexes, unique indexes, partial indexes, TTL, text/search indexes và theo dõi query plans.
- Phân biệt index prefix, sort, cardinality, shard key và các yêu cầu của unique indexes trên sharded collections.
- Phòng chống rò rỉ qua `$lookup`, `$unionWith`, `$graphLookup`, `$facet`, change streams, cache, background jobs và logs.
- Tổ chức tenant provisioning, schema migration, backup/restore, tenant deletion, noisy-neighbor controls và observability.
- Xây test chống cross-tenant data leakage, quyền truy cập và concurrency bằng MongoDB thật.

### 1.2. Phạm vi

Ví dụ sử dụng **MongoDB Java Sync Driver 5.x**, BSON documents và JUnit/Spring Boot khi cần. Các APIs/URI/options có thể khác giữa driver và server versions; khi triển khai cần dùng phiên bản đã được dự án kiểm chứng.

Các lệnh quản trị trong bài chỉ để học trên database lab. Chuyển sang production cần đánh giá bảo mật, topology, write concerns, tải, backup và change plan. Không dùng các đoạn script xóa/drop tenant trên môi trường thật nếu chưa có quyền và phương án khôi phục.

## 2. Tenant là gì? Phân biệt tenant, user và resource

Ví dụ dữ liệu quan hệ:

```text
Tenant north-shop
  - owner Alice
  - staff Bob
  - orders N001, N002
  - products NP01, NP02

Tenant big-mart
  - owner Carol
  - staff Dan
  - orders B001, B002
  - products BP01, BP02
```

Một **user** có thể thuộc một hoặc nhiều tenants với vai trò khác nhau. **Tenant không đồng nghĩa user**.

Ví dụ membership:

```javascript
{
  _id: "membership:alice:north-shop",
  userId: "alice",
  tenantId: "north-shop",
  role: "TENANT_ADMIN",
  status: "ACTIVE"
}

{
  _id: "membership:alice:big-mart",
  userId: "alice",
  tenantId: "big-mart",
  role: "VIEWER",
  status: "ACTIVE"
}
```

Khi Alice chuyển tenant đang thao tác, **effective authorization context thay đổi**, mặc dù identity người dùng vẫn là Alice.

### 2.1. Các thuật ngữ cần tách

| Thuật ngữ | Ý nghĩa |
|---|---|
| Tenant | Đơn vị tổ chức sở hữu/phân vùng dữ liệu |
| User | Danh tính đã xác thực |
| Membership | Quan hệ user–tenant, vai trò/trạng thái |
| Tenant context | Tenant hiện được ủy quyền cho request/job |
| Resource | Order, invoice, document, report, config |
| Authorization | Quyết định user/service được phép thao tác resource nào |
| Isolation | Bảo đảm hoạt động của tenant A không truy cập/tác động dữ liệu tenant B trái phép |
| Noisy neighbor | Một tenant dùng quá nhiều tài nguyên ảnh hưởng tenants còn lại |

### 2.2. Tenant ID phải ổn định

`tenantId` là khóa boundary. Tránh dùng tên hiển thị (có thể đổi) làm tenant ID. Có thể dùng UUID, ULID, ObjectId hay string opaque do backend cấp; cần xác định duy nhất, không tái sử dụng tùy tiện.

### 2.3. Không tin tenant ID chỉ vì client gửi

Client có thể gửi:

```http
X-Tenant-Id: big-mart
```

Header chỉ là **lựa chọn tenant được yêu cầu**, không phải bằng chứng client có quyền ở tenant đó. Server phải xác minh identity + membership/authorization trước khi hình thành tenant context.

### 2.4. Admin xuyên tenant

Một super-admin support có thể cần truy cập nhiều tenants, nhưng phải dùng **đường nghiệp vụ tách biệt**, scope được cấp rõ, xác nhận lý do, audit và break-glass policy. Không đặt Boolean `bypassTenant=true` ở một hàm repository thông thường rồi cho request client lựa chọn.

## 3. Ba kiểu cô lập: logic, database và hạ tầng

### 3.1. Cô lập logic

```text
                 One MongoDB cluster
                         |
                     saas.orders
                         |
       +-----------------+------------------+
       |                 |                  |
tenant=north-shop   tenant=big-mart     tenant=trial-17
```

Mọi document nằm trong cùng collection và được phân tách bằng field `tenantId` và ứng dụng.

### 3.2. Cô lập theo database

```text
                 One MongoDB cluster
                         |
          +--------------+--------------+
          |              |              |
      db_north_shop   db_big_mart    db_trial_17
          |              |              |
        orders          orders          orders
```

Mỗi tenant có database riêng; MongoDB roles có thể giới hạn quyền ở mức database, nếu identities được thiết kế phù hợp.

### 3.3. Cô lập theo cluster

```text
Tenant north-shop ---> MongoDB cluster A
Tenant big-mart   ---> MongoDB cluster B
Tenant legal-firm ---> Dedicated MongoDB cluster C
```

Mức độ cô lập tài nguyên/quyền cao hơn nhưng vận hành và chi phí lớn hơn.

### 3.4. “Tách database” không tự cô lập tất cả tài nguyên

Trong cùng cluster, các database vẫn dùng chung CPU, memory, disk/network, storage engine, connection limits và một phần control plane. Database-per-tenant **không tương đương** dedicated cluster về noisy-neighbor isolation.

## 4. So sánh bốn mô hình lưu trữ

| Mô hình | Cách bố trí | Ưu điểm | Bất lợi chính |
|---|---|---|---|
| Shared collection | Một `orders`, mọi doc có `tenantId` | Nhiều tenants, ít namespaces, index/schema chung | App phải áp tenant scope tuyệt đối; noisy neighbor |
| Collection per tenant | `orders_tenantA`, `orders_tenantB` | Một số chính sách index/collection tách | Nhiều collection/index/catalog overhead, tên động |
| Database per tenant | `dbTenantA.orders`, `dbTenantB.orders` | Database-level RBAC/quản lý tách | Migration, provisioning, connection/database metadata mở rộng theo số tenant |
| Cluster per tenant | Hạ tầng tách hoàn toàn | Isolation, scale, bảo trì độc lập mạnh | Chi phí và operations cao |

### 4.1. Không có một mô hình đúng cho mọi SaaS

Một dịch vụ 50.000 tenants, mỗi tenant vài trăm documents thường ưu tiên shared collections/hybrid. Một khách hàng enterprise xử lý vài trăm triệu records có thể cần database/cluster riêng.

### 4.2. Collection-per-tenant không phải lựa chọn mặc định

Nếu có 30.000 tenants × 20 collections/tenant = **600.000 collections**, chưa kể nhiều indexes mỗi collection, số namespaces và metadata có thể trở thành bottleneck vận hành. Không chọn mô hình này chỉ vì tên collection nhìn “cô lập hơn”.

### 4.3. Database-per-tenant không đồng nghĩa MongoClient-per-tenant

Nhiều databases trên cùng deployment thường có thể dùng chung một `MongoClient` lâu dài:

```java
MongoClient client = MongoClients.create(sharedClusterUri);
MongoDatabase db = client.getDatabase(tenantDatabaseName);
```

Tạo hàng chục nghìn `MongoClient` sẽ sinh monitoring connections và pools độc lập, thường không cần.

### 4.4. Cluster-per-tenant có thể giúp giới hạn blast radius

Một tenant yêu cầu workload, encryption keys hoặc backup/maintenance tách biệt có thể được cấp cluster riêng. Nhưng **đừng coi cluster tách = ứng dụng tự động an toàn**: quyền admin, secrets, logging, cache, deployment và endpoint routing vẫn phải bảo vệ.

## 5. Tiêu chí quyết định data isolation

Một checklist kiến trúc:

| Tiêu chí | Câu hỏi |
|---|---|
| Số lượng tenants | 10, 1.000 hay 100.000? |
| Data volume | Tenant trung bình/lớn nhất bao nhiêu GiB? |
| Query pattern | Theo tenant hay cross-tenant analytics? |
| SLA | Tenant enterprise có SLO riêng không? |
| Regulatory | Có yêu cầu residence/cô lập/retention cụ thể không? |
| Schema customization | Tenants dùng schema/index khác nhau? |
| Resource isolation | Tenant lớn có thể làm CPU/IO tăng mạnh? |
| Lifecycle | Onboard/offboard và restore riêng tenant có thường xuyên? |
| Sharding | Cần chia một collection lớn trên nhiều shards? |
| IAM/RBAC | Có thể cấp DB credentials riêng tenant không? |
| Cost | Bao nhiêu cluster/databases/collections có thể vận hành? |

### 5.1. Mô hình hybrid

```text
Tenant router
      |
      +--> shared-cluster / shared-collections
      |        trial, small, medium tenants
      |
      +--> enterprise-cluster-A / database dedicated
      |        big-mart
      |
      +--> isolated-cluster-B
               legal-firm
```

Hybrid cho phép nâng tenant từ shared → dedicated khi quy mô/SLA tăng, nhưng đòi migration/router được thiết kế an toàn.

### 5.2. Routing metadata

```javascript
{
  _id: "big-mart",
  storageMode: "DEDICATED_DATABASE",
  clusterKey: "enterprise-a",
  databaseName: "tenant_7f3a4d",
  state: "ACTIVE",
  routingVersion: NumberLong("5")
}
```

Đây là metadata điều khiển của backend, **không** là thông tin client được quyền tự thay.

### 5.3. Data residency

Nếu tenant có yêu cầu vùng dữ liệu, routing phải đảm bảo **data, backups, logs, analytics exports và service integrations** tuân thủ policy thực tế. Không chỉ chọn một cluster ở region phù hợp rồi mặc định mọi bản sao khác đã tuân thủ.

## 6. Threat model: rò rỉ giữa tenants có thể xảy ra ở đâu?

```text
               Authenticated request
                         |
                         v
                Tenant authorization
                         |
                         v
           Tenant-aware business service
                         |
           +-------------+-------------+
           |             |             |
       MongoDB CRUD   Aggregation    Cache/search
           |             |             |
        tenantId        $lookup       cache key
        filters         / $facet      tenant scope
           |             |             |
           +-------------+-------------+
                         |
                         v
                  Response / export
```

Các điểm dễ lọt:

- `findById(id)` không có tenant filter.
- `updateOne` hoặc `deleteMany` quên `tenantId`.
- `$lookup` nối theo mã order/product nhưng không nối tenant.
- `$unionWith` truy xuất collection khác không scope.
- Background job và worker chạy không có request context.
- Cache key chỉ dùng `orderId`.
- Search index hoặc report aggregation không có tenant constraint.
- Change stream consumer publish events vào queue không tenant-aware.
- Logs/error messages trả về document của tenant khác.
- File exports/backup restore đi sai tenant destination.
- Signed URLs, attachments và object storage không ràng buộc tenant.

### 6.1. Isolation là thuộc tính end-to-end

Một MongoDB query đúng chưa đủ nếu API cache trả nhầm response. Khi audit multi-tenancy, phải kiểm tra mọi đường dữ liệu, không chỉ collection schemas.

### 6.2. Threat actors không nhất thiết là attacker bên ngoài

Lỗi có thể xuất phát từ:

- Người dùng đổi tenant qua UI.
- Developer quên filter trong một method mới.
- Support script chạy sai scope.
- Scheduled job dùng nhầm tenant.
- Analytics pipeline nhân bản dữ liệu sai tenant.
- Data migration với checkpoint/partition không đủ tenant boundary.

## 7. Shared collection: thiết kế document chuẩn

Đơn hàng:

```javascript
{
  _id: ObjectId("673400000000000000000451"),
  tenantId: "north-shop",
  orderNumber: "PO-2026-0007",
  customerId: ObjectId("673400000000000000000111"),
  status: "PAID",
  amountMinor: NumberLong("350000"),
  currency: "VND",
  createdAt: ISODate("2026-11-14T04:00:00Z"),
  updatedAt: ISODate("2026-11-14T04:05:00Z")
}
```

Khách hàng:

```javascript
{
  _id: ObjectId("673400000000000000000111"),
  tenantId: "north-shop",
  displayName: "Customer N-01",
  status: "ACTIVE"
}
```

### 7.1. `tenantId` là thuộc tính bắt buộc

Mỗi document domain tenant-owned cần:

- Một tenant ID hợp lệ.
- Không bị thay đổi tenant một cách ngầm định.
- Quy tắc tạo và cập nhật thống nhất.
- Tenant filter cho mọi read/write path.

### 7.2. Global _id hay composite identity?

MongoDB mặc định tạo unique index `_id` trên collection. Nếu dùng `ObjectId`, giá trị thường unique trên collection mà không cần nhúng tenant vào `_id`.

Nếu domain dùng số order `PO-2026-0007` có thể lặp ở hai tenants, unique key phải là **`(tenantId, orderNumber)`**, không phải `orderNumber` một mình.

### 7.3. Tenant references phải giữ boundary

`customerId` có thể là ObjectId globally unique nhưng ứng dụng vẫn nên xác minh customer thuộc **cùng tenant**:

```javascript
db.customers.findOne({
  _id: customerId,
  tenantId: "north-shop"
});
```

Không suy ra hợp lệ chỉ vì ID tồn tại.

### 7.4. Chuyển ownership giữa tenants

Đổi `tenantId` của một order là tác vụ nhạy cảm, không phải PATCH thông thường. Nếu nghiệp vụ thật sự cần “move tenant”, hãy dùng workflow được phê duyệt với kiểm tra references, unique constraints, audit, cache/search cleanup và rollback; thường không cho update trực tiếp field boundary.

## 8. Khóa duy nhất trong phạm vi tenant

### 8.1. Sai: unique index toàn collection

```javascript
db.orders.createIndex(
  { orderNumber: 1 },
  { unique: true }
);
```

Index này cấm hai tenant cùng dùng `PO-0007`, dù nghiệp vụ cho phép.

### 8.2. Đúng: compound unique index

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  {
    unique: true,
    name: "uniq_tenant_order_number"
  }
);
```

Hai documents:

```javascript
{ tenantId: "north-shop", orderNumber: "PO-0007" }
{ tenantId: "big-mart",   orderNumber: "PO-0007" }
```

được phép cùng tồn tại. Một tenant tạo lại cùng `orderNumber` sẽ gặp duplicate key.

### 8.3. Index không thay authorization

Compound unique index chỉ chặn trùng khóa, **không** tự chặn một query thiếu tenantId. `find({orderNumber:"PO-0007"})` vẫn có thể đọc nhiều tenants nếu quyền truy cập của DB identity cho phép.

### 8.4. Duplicate key cần domain mapping

`E11000 duplicate key` trên `uniq_tenant_order_number` thường là conflict trong tenant. Ứng dụng nên xác nhận đó đúng là index đang vi phạm, thay vì bắt mọi duplicate key thành thông báo “order đã tồn tại”; có thể là index trên email, externalId, v.v.

### 8.5. Bẫy missing/null trong unique index

Nếu dữ liệu lịch sử thiếu `tenantId` hoặc `orderNumber`, unique compound index có semantics đối với giá trị thiếu/null và có thể fail khi build. Preflight kiểm tra dữ liệu cũ và schema validation trước khi tạo unique index.

## 9. Index: tenant filter thường là phần đầu của compound key

Giả sử API phổ biến:

```javascript
db.orders.find({
  tenantId: "north-shop",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(50);
```

Một index phù hợp:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created_desc" }
);
```

### 9.1. Vì sao tenantId thường đứng đầu?

Ứng dụng luôn filter theo tenant. Đặt `tenantId` ở prefix giúp index support lookup trong phạm vi tenant và có thể dùng các trường sau cho equality và sort.

Nhưng **không có quy tắc cứng “tenantId luôn phải đứng đầu mọi index”**. Query patterns, cardinality, sort, range predicates, MongoDB planner, sharding và index costs quyết định thực tế.

### 9.2. Equality–sort–range (ESR)

Một heuristic hữu ích khi thiết kế compound indexes:

1. Equality fields.
2. Sort fields.
3. Range fields.

Đây không là định luật. Với range rất chọn lọc, ERS có thể hữu ích; phải dùng `explain` và đo workloads.

### 9.3. Index cho truy vấn theo order ID

`_id` đã có unique index. Query:

```javascript
db.orders.findOne({
  tenantId: "north-shop",
  _id: ObjectId("673400000000000000000451")
});
```

có thể dùng `_id_` để tìm nhanh một document rồi kiểm tra `tenantId`. Không nhất thiết thêm compound index `{tenantId:1,_id:1}` chỉ để làm truy vấn này nhanh hơn.

### 9.4. Index cho list theo thời gian

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_created_id_desc" }
);
```

Hỗ trợ filter tenant, sort ổn định theo createdAt và _id khi phân trang.

### 9.5. Index cho search customer

```javascript
db.orders.createIndex(
  { tenantId: 1, customerId: 1, createdAt: -1 },
  { name: "idx_tenant_customer_created_desc" }
);
```

Phù hợp màn hình lịch sử đơn hàng của một customer trong một tenant.

## 10. Bảng chọn index theo access pattern

| Query thường dùng | Filter/sort | Index ứng viên |
|---|---|---|
| Lookup order number | tenantId = ?, orderNumber = ? | `{tenantId:1,orderNumber:1}` unique |
| List recent orders | tenantId = ?, sort createdAt desc/_id desc | `{tenantId:1,createdAt:-1,_id:-1}` |
| Paid orders | tenantId = ?, status = PAID, sort createdAt | `{tenantId:1,status:1,createdAt:-1}` |
| Customer history | tenantId = ?, customerId = ?, sort createdAt | `{tenantId:1,customerId:1,createdAt:-1}` |
| External integration lookup | tenantId = ?, externalId = ? | `{tenantId:1,externalId:1}` |
| Open tasks | tenantId = ?, state = OPEN, sort priority | Cân nhắc compound/partial index theo workload |
| Shared global support ops | Có quyền và scope rõ | Index riêng cho administrative query nếu cần |

### 10.1. Không tạo mọi index “cho chắc”

Mỗi index tiêu thụ storage/cache, cần bảo trì trên writes và làm bulk migration nặng hơn. Việc có hàng chục indexes “dự phòng” làm tăng chi phí ingestion của mọi tenant.

### 10.2. Một index không phục vụ mọi sorts

`{tenantId:1,status:1,createdAt:-1}` không tự tối ưu query sort theo `amountMinor` hoặc `customerName`. Muốn tối ưu cần biết query thực tế và cân nhắc index riêng.

### 10.3. Index tính trên toàn shared collection

Trong mô hình shared collection, index này bao gồm keys của **tất cả tenants**, không phải “mỗi tenant một index riêng” dù prefix là tenantId.

### 10.4. Đo `explain("executionStats")`

```javascript
db.orders.find({
  tenantId: "north-shop",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
```

Quan sát:

- Winning plan `IXSCAN` hay `COLLSCAN`.
- `totalKeysExamined`, `totalDocsExamined`, `nReturned`.
- Blocking `SORT`.
- Index bounds và whether query is covered.

Đừng coi `IXSCAN` đơn thuần là luôn tốt; scan hàng triệu index keys để trả 20 records vẫn có thể không hiệu quả.

## 11. Partial index, sparse index và soft delete

Một ứng dụng hỗ trợ soft delete:

```javascript
{
  tenantId: "north-shop",
  orderNumber: "PO-0007",
  deletedAt: null
}
```

Nếu cho phép tái sử dụng orderNumber sau khi order bị xóa, cần nói rõ policy: chỉ unique với records **active** hay unique xuyên toàn lịch sử?

### 11.1. Partial unique index cho active documents

Giả sử application quy ước **document active khi `deletedAt` không tồn tại**, còn deleted khi `deletedAt` là Date:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  {
    unique: true,
    name: "uniq_active_tenant_order_number",
    partialFilterExpression: {
      deletedAt: { $exists: false }
    }
  }
);
```

Index chỉ bao phủ documents thỏa partial predicate. Nếu records active lại chứa `deletedAt:null` thì **không** match `$exists:false` và có thể lọt unique constraint mong muốn. Phải chuẩn hóa schema/trạng thái.

### 11.2. Soft delete atomic

```javascript
db.orders.updateOne(
  {
    tenantId: "north-shop",
    _id: orderId,
    deletedAt: { $exists: false }
  },
  {
    $currentDate: { deletedAt: true }
  }
);
```

### 11.3. Partial index không thay tenant filter

Nếu query sử dụng index partial mà vẫn thiếu `tenantId`, nó có thể trả active orders của nhiều tenants. Index chỉ cải thiện plan hoặc giới hạn indexed keys, không tự cung cấp authorization.

### 11.4. Query phải phù hợp predicate

MongoDB planner chỉ dùng partial index khi có thể đảm bảo query không bỏ sót documents ngoài partial filter. Query không nêu điều kiện active có thể không tận dụng index như kỳ vọng; xác nhận bằng `explain`.

### 11.5. Sparse khác partial

Sparse index chỉ bao gồm documents có indexed field(s) theo semantics của index; partialFilterExpression cho điều kiện phong phú hơn. Đừng tự kết luận sparse index giải quyết mọi unique-null/soft-delete use cases.

## 12. Collation và tenant-specific uniqueness

Một tenant cần `orderNumber` không phân biệt hoa thường:

```text
INV-001
inv-001
```

MongoDB collation có thể hỗ trợ comparison/case rules trên index/query phù hợp.

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  {
    unique: true,
    name: "uniq_tenant_order_case_insensitive",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

### 12.1. Cẩn thận collation của query

Để tận dụng string comparisons/index theo collation, query cần tương thích với index collation hoặc collection default. Kiểm tra `explain`.

### 12.2. Tenants có quy tắc riêng?

Nếu tenant A coi email case-insensitive còn tenant B dùng quy tắc locale khác, một shared compound index với collation cố định có thể không đáp ứng cả hai.

Các hướng:

- Chuẩn hóa key nghiệp vụ về form canonical theo policy rõ.
- Chọn một policy thống nhất nếu được phép.
- Tách collection/database/cluster theo nhóm yêu cầu khác biệt.
- Dùng keys đã chuẩn hóa với uniqueness phù hợp.

### 12.3. Không tự lowercase mọi trường

Tên người, địa chỉ và dữ liệu locale-sensitive không thể luôn lower-case theo quy tắc phổ quát. Chỉ chuẩn hóa những fields thực sự có domain equality semantics tương ứng.

## 13. TTL và retention theo tenant

Tenant A có retention 30 ngày, tenant B 365 ngày. Một cách thiết kế shared collection là tính `expireAt` theo policy tenant khi tạo/cập nhật record:

```javascript
{
  tenantId: "trial-17",
  eventType: "SESSION_CREATED",
  createdAt: ISODate("2026-11-01T10:00:00Z"),
  expireAt: ISODate("2026-12-01T10:00:00Z")
}
```

TTL index:

```javascript
db.tenantSessions.createIndex(
  { expireAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_expire_at" }
);
```

### 13.1. TTL không xóa chính xác tại giây expire

MongoDB TTL monitor xử lý bất đồng bộ; xóa có thể trễ dưới tải. Nếu dữ liệu không được phép tồn tại sau một deadline nghiêm ngặt, TTL **không** phải toàn bộ giải pháp compliance; cần policy và kiểm soát hệ thống mạnh hơn.

### 13.2. Legal hold

Không tự đặt `expireAt` cho documents đang cần legal hold. Thiết kế quy tắc tính và cập nhật `expireAt` theo authorized retention workflow; thay đổi policy có thể yêu cầu backfill lại timestamps.

### 13.3. TTL index không tự mang tenantId prefix

TTL indexes thông thường được khai báo trên một Date field phù hợp với TTL semantics. Tenant-specific retention được thể hiện bằng **giá trị expireAt mỗi document**, thay vì cố xem compound index `{tenantId,expireAt}` là TTL index chuẩn.

### 13.4. Xóa liên quan nhiều hệ thống

TTL xóa MongoDB record không tự xóa files trong object storage, search index, cache, data lake, analytics exports hay bản sao hợp lệ khác. Tenant offboarding cần inventory tài sản dữ liệu liên quan.

## 14. Tenant-aware pagination

Một màn hình:

```http
GET /api/orders?status=PAID&limit=50&cursor=...
```

phải có tenant scope từ server:

```javascript
db.orders.find({
  tenantId: "north-shop",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(50);
```

### 14.1. Vì sao không chỉ dùng `skip`?

`skip(1000000)` có thể khiến query phải bỏ qua lượng lớn index entries và bị ảnh hưởng bởi inserts/deletes làm lệch vị trí. Với pagination lớn, **keyset/cursor pagination** thường phù hợp hơn.

### 14.2. Keyset theo createdAt + _id

Cursor cuối trang trước:

```javascript
{
  lastCreatedAt: ISODate("2026-11-14T04:00:00Z"),
  lastId: ObjectId("673400000000000000000451")
}
```

Trang tiếp theo:

```javascript
db.orders.find({
  tenantId: "north-shop",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(50);
```

### 14.3. Cursor phải gắn tenant

Không cho phép cursor được tạo từ `north-shop` dùng lại ở `big-mart` mà không kiểm tra. Cursor opaque/signed nên chứa (hoặc gắn server-side) tenant, sort/filter version, expiry và metadata cần thiết.

### 14.4. Cách chống sửa cursor

- Sign cursor bằng MAC hoặc giữ server-side token map.
- Validate tenant equality với authenticated context.
- Reject cursor malformed/stale.
- Không cho user truyền thẳng raw MongoDB filter/aggregation JSON tùy ý.

### 14.5. Sort keys nên bất biến

Nếu createdAt bị sửa sau khi phát cursor, một record có thể lặp/bỏ sót. Thường createdAt bất biến, còn sort status/updatedAt có thể đổi trong lúc phân trang. Chọn consistency contract phù hợp.

## 15. Sharding cho shared multi-tenant collection

Khi shared collection có hàng tỷ documents, một replica set có thể không đáp ứng storage/throughput. MongoDB sharding cho phép phân phối dữ liệu trên nhiều shards.

### 15.1. Shard key quyết định routing và phân bố

Giả sử shard key:

```javascript
sh.shardCollection(
  "saas.orders",
  { tenantId: 1, orderId: 1 }
);
```

Trước lệnh này cần lập index/sharding preconditions đúng cho MongoDB version và deployment. Đây chỉ là shape minh họa, không phải lệnh chạy ngay trên production.

### 15.2. Hỏi ba câu trước khi chọn shard key

1. Truy vấn phổ biến có bao gồm shard key hoặc prefix đủ target không?
2. Phân bố tenants có bị skew: 1 tenant chiếm 80% data không?
3. Workload writes có tạo hotspot trên một chunk/shard không?

### 15.3. Shard key chỉ tenantId có vấn đề gì?

Nếu shard key chỉ `{tenantId:1}`, dữ liệu của một tenant có thể bị giới hạn về khả năng chia nhỏ theo key, đặc biệt tenant rất lớn/hot. Range/hashing strategy và key cardinality cần được tính theo distribution thực.

### 15.4. Compound key có tenantId

`{tenantId:1,orderId:1}` cho nhiều distinct values trong cùng tenant và có thể hữu ích với tenant-aware routing, nhưng targeting cho query thiếu shard key thành phần cần được đánh giá; không mặc định mọi query `tenantId=?` đều chạy trên đúng một shard.

### 15.5. Hashed sharding

Hashed shard keys có thể giúp phân bố các giá trị phù hợp, nhưng ảnh hưởng range targeting, data locality và tính năng unique index. Không dùng “hash tenantId” như mẹo chung nếu có tenant siêu lớn: cùng tenantId hash vẫn là một giá trị shard key component.

### 15.6. Zone sharding

Zone sharding có thể giúp áp placement policies phù hợp, nhưng cần thiết kế zone ranges, shard key và vận hành; không tự bảo đảm regulatory isolation hay data residence end-to-end.

## 16. Unique indexes trên sharded collections

Trong shared replica set, unique index `{tenantId:1,orderNumber:1}` rất tự nhiên.

Trong **sharded collection**, các quy tắc unique index còn phụ thuộc shard key:

- Unique index được hỗ trợ phải tuân thủ yêu cầu prefix liên quan shard key theo MongoDB server rules.
- Không thể tạo unique index tùy ý bỏ qua shard key rồi cho rằng MongoDB có thể bảo đảm uniqueness toàn cluster.
- `_id` uniqueness trên sharded collection có caveat khi `_id` không là shard key; không dùng việc `_id_` index tồn tại để suy mọi collisions xuyên shards đều bị chặn theo cách bạn nghĩ.
- Hashed indexes không cung cấp unique constraints theo cách giống một ordinary unique index.

### 16.1. Ví dụ phù hợp về ý tưởng

Với shard key `{tenantId:1}`, unique index `{tenantId:1,orderNumber:1}` có shard key prefix. Nhưng điều này chưa giải quyết skew/hot tenants; phải đánh giá cả scale.

### 16.2. Khi cần uniqueness toàn tenant

Có thể cần chọn shard key tương thích constraint, hoặc tạo một collection/service quản lý reservation keys với transaction/atomic insert semantics phù hợp.

Không tự tạo một index “unique business key” rồi không kiểm tra lệnh được server chấp nhận và guarantee trên sharded topology.

### 16.3. Shard key có thể khó đổi

Thiết kế shard key cần cân nhắc dài hạn. MongoDB có cơ chế hỗ trợ refine/reshard trong những phiên bản tương ứng, nhưng đây là vận hành tốn tài nguyên và cần migration/runbook, không nên dùng như cách chữa mọi thiết kế chưa đo.

## 17. Database per tenant: isolation và provisioning

Mỗi tenant có:

```text
tenant_north_shop
  orders
  customers
  invoices

tenant_big_mart
  orders
  customers
  invoices
```

### 17.1. Tenant registry

Một registry điều khiển routing:

```javascript
{
  _id: "north-shop",
  mode: "DATABASE_PER_TENANT",
  databaseName: "tenant_b7f32",
  clusterKey: "shared-prod-a",
  schemaVersion: 7,
  status: "ACTIVE"
}
```

**Không** xây database name trực tiếp bằng string do client truyền mà không validate. Registry là dữ liệu đáng tin do backend/quản trị quản lý.

### 17.2. MongoClient reuse

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoDatabase;

public final class TenantDatabaseResolver451 {
    private final MongoClient client;
    private final TenantRegistry registry;

    public TenantDatabaseResolver451(
            MongoClient client, TenantRegistry registry) {
        this.client = client;
        this.registry = registry;
    }

    public MongoDatabase databaseFor(AuthorizedTenant451 scope) {
        String dbName = registry.trustedDatabaseName(scope.tenantId());
        if (dbName == null || dbName.isBlank()) {
            throw new IllegalStateException("Tenant not provisioned");
        }
        return client.getDatabase(dbName);
    }
}
```

`AuthorizedTenant451` và `TenantRegistry` là các abstraction do ứng dụng định nghĩa; đoạn code không tự tạo một thư viện authz đầy đủ.

### 17.3. Khi nào phải tạo MongoClient riêng?

Nếu tenants ở **khác cluster, khác credentials/CA/transport policies**, có thể cần một `MongoClient` mỗi nhóm cấu hình/cluster. Quản lý một cache clients có kích thước/TTL/lifecycle rõ, không tạo client mới cho mỗi request.

### 17.4. Database-level grants

MongoDB có thể cấp role giới hạn theo database. Tuy nhiên nếu application dùng **một super-credential có toàn quyền trên mọi tenant databases**, lỗi routing trong code vẫn có thể đọc nhầm database. Isolation mạnh hơn cần tách DB identities, service deployment, hoặc server-side policies thích hợp.

## 18. Collection per tenant: giới hạn thực tế

Một cách đặt tên:

```text
orders_7f3a4d
orders_b9c27e
orders_03d992
```

### 18.1. Không đưa raw tenant ID vào tên namespace

Một tenant ID có ký tự đặc biệt hoặc rất dài có thể khiến namespace khó quản lý; tên do người dùng kiểm soát cũng tạo risk tên collision hoặc injection. Sử dụng namespace do backend cấp và registry mapping.

### 18.2. Chi phí vận hành tăng theo số tenant

Mỗi collection có thể có:

- Indexes riêng và index build lifecycle.
- Collection options/validators/collation.
- TTL/index metadata.
- Namespace catalog và statistics.
- Backup/restore/monitoring overhead.

### 18.3. Lợi ích thực

Collection-per-tenant cho phép index/retention/validator khác nhau mà không trộn với documents tenants khác; hữu ích khi có **số tenant hạn chế** và yêu cầu customize vừa phải.

### 18.4. Không coi namespace động là bảo mật

`db.getCollection("orders_"+tenantId)` chỉ an toàn nếu tenant ID đã authorized và tên được resolve từ registry. Raw input tùy ý có thể trỏ đến collection tenant khác hoặc internal collection.

## 19. MongoDB RBAC: MongoDB có thể và không thể làm gì?

**Role-Based Access Control (RBAC)** của MongoDB quản lý quyền đối với resources như cluster, database và collection.

### 19.1. Database/collection scope

Có thể cấp:

- Quyền đọc database A.
- Quyền đọc/ghi collection `orders` trong database B.
- Quyền admin/monitoring cho accounts vận hành.

### 19.2. Không có row-level authorization mặc định chỉ vì `tenantId`

Trong một shared collection:

```javascript
db.orders.find({
  tenantId: "north-shop"
});
```

MongoDB không tự thêm filter `tenantId` cho mọi lệnh của một application user chỉ vì user thuộc `north-shop`.

Nếu cùng DB credential có `find` trên shared `orders` collection, MongoDB server **không tự biết** JWT/membership của từng HTTP caller.

### 19.3. Application authorization là bắt buộc với shared collections

Service phải:

- Xác thực caller và lựa chọn tenant.
- Xác thực membership/role.
- Gắn tenant condition vào mọi MongoDB operation.
- Chặn APIs có thể bypass filter.
- Test các cross-tenant cases.

### 19.4. Database-per-tenant dễ hỗ trợ server-side boundary hơn

Nếu application kết nối bằng DB user chỉ được phép database tenant A, MongoDB có thể từ chối truy cập database B. Đây là lớp phòng vệ thêm so với app checks.

### 19.5. Nhưng DB identity cũng cần được quản lý

Secrets rotation, credential mapping, pool reuse, support access và tenant reassignment đều cần operational controls. Mỗi tenant một credential không tự phù hợp với 100.000 tenants nếu không có cơ chế quản lý ở quy mô đó.

## 20. Ví dụ cấp quyền database cho tenant chuyên biệt

Trên **database thử nghiệm**:

```javascript
use tenant_north_shop_lab;

db.createUser({
  user: "tenant_north_reader",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "tenant_north_shop_lab" }
  ]
});
```

User này có role đọc trong database được chỉ định theo RBAC, không có quyền tự nhiên với database của tenant khác.

### 20.1. Kiểm tra thực tế

```javascript
use tenant_north_shop_lab;
db.orders.findOne();
```

Khi kết nối bằng identity đọc của tenant A, thử thao tác ngoài quyền trên tenant B hoặc write vào tenant A và xác minh server từ chối.

### 20.2. Authentication vs authorization

- **Authentication (AuthN):** ai đang kết nối MongoDB?
- **Authorization (AuthZ):** identity đó được làm gì trên database/collection?

HTTP user và DB user có thể khác nhau: một service backend thường kết nối bằng service identity, rồi triển khai HTTP-level authorization cho từng request.

### 20.3. Principle of least privilege

Service xử lý đơn hàng không nên dùng role `root`. Grant quyền cần thiết cho collections mà service thật sự sử dụng; phân biệt app, migrations và DBAs.

### 20.4. Secrets

Không lưu password/connection URI chứa credential trong source code, test snapshots, logs hoặc tenant registry mà user thường có quyền đọc. Dùng secrets management và rotation policy.

### 20.5. Views không thay toàn bộ row-level policy

MongoDB read-only views có thể tạo một lớp abstraction/truy vấn có filter, và quyền có thể được cấp lên view thay vì underlying collection trong các điều kiện phù hợp. Nhưng views không tự cho phép arbitrary writes có tenant isolation và không thay việc kiểm soát all application paths. Khi dùng views như boundary, phải đánh giá privileges, aggregation behavior, direct collection grants và đúng server version.

## 21. Xây tenant context từ identity đã xác thực

Luồng request:

```text
Browser / API client
        |
        | JWT / session + desired tenant
        v
Authentication filter
        |
        v
Verify signature, expiry, audience, issuer
        |
        v
Membership & permission check
        |
        v
AuthorizedTenant tenant context
        |
        v
Tenant-scoped service/repository
        |
        v
MongoDB with mandatory tenantId filter
```

### 21.1. Không lấy tenant từ request body làm authority

Ví dụ:

```json
{
  "tenantId": "big-mart",
  "orderNumber": "PO-100",
  "amountMinor": 550000
}
```

Nếu Alice thuộc `north-shop` gửi body này, server không được tạo order của `big-mart` theo input. Tenant ID phải đến từ **scope đã được xác thực và cấp quyền**.

### 21.2. Tenant switching

User có nhiều memberships có thể yêu cầu một tenant cụ thể; backend cần:

1. Kiểm tra tenant tồn tại/đang active.
2. Kiểm tra user có membership active.
3. Kiểm tra role cho action requested.
4. Tạo `AuthorizedTenant` không thể bị sửa từ body.
5. Gắn scope vào request execution.

### 21.3. Service-to-service

Batch/queue consumers không có người dùng trực tiếp. Chúng cần **service identity** và tenant context từ thông điệp đã validate/authorized, không tin `tenantId` tùy ý trong payload queue.

### 21.4. Async context propagation

ThreadLocal truyền scope qua request thread có thể bị mất trong `CompletableFuture`, reactive chains hoặc message consumers. Ưu tiên scope là tham số explicit; nếu framework dùng context propagation, cần test các boundary async.

## 22. Kiểu dữ liệu tenant scope trong Java

Một kiểu immutable chỉ được tạo sau khi đã kiểm tra authorization:

```java
import java.util.Objects;

public record AuthorizedTenant451(
    String tenantId,
    String actorId,
    String role
) {
    public AuthorizedTenant451 {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(actorId, "actorId");
        Objects.requireNonNull(role, "role");
        if (tenantId.isBlank() || actorId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenant scope");
        }
    }
}
```

### 22.1. Type safety chưa là authorization

Bất kỳ code nào có thể gọi `new AuthorizedTenant451("big-mart",...)`; constructor chỉ validate form, không xác minh membership. Trong production, hạn chế scope creation ở authorized service/factory hoặc sử dụng policy API đủ mạnh.

### 22.2. Authorization factory giả lập

```java
public AuthorizedTenant451 authorizeTenant(
        VerifiedPrincipal principal,
        String requestedTenant,
        String requiredAction) {

    Membership membership = membershipService.findActive(
        principal.userId(), requestedTenant);

    if (membership == null
            || !permissionService.allowed(
                membership, requiredAction)) {
        throw new AccessDeniedException("Tenant access denied");
    }

    return new AuthorizedTenant451(
        requestedTenant, principal.userId(), membership.role());
}
```

Các `VerifiedPrincipal`, `Membership` và services trên là abstraction kiến trúc, không phải APIs có sẵn của MongoDB Java Driver.

### 22.3. Không để shared repository nhận raw tenantId từ public controller

Một method dạng `repository.findOrders(String tenantId)` có nguy cơ bị gọi bằng input chưa authorize. Ưu tiên:

```java
List<Order> listOrders(AuthorizedTenant451 scope, OrderFilter filter);
```

Để caller buộc thực hiện authorization trước khi truy cập dữ liệu.

## 23. Java Sync Driver: repository scoped cho CRUD

Ví dụ repository tối giản, dùng một shared `orders` collection và **không công khai trực tiếp MongoCollection** cho controllers:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.ObjectId;

import java.util.List;
import java.util.ArrayList;
import java.util.Objects;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class TenantOrderRepository451 {
    private final MongoCollection<Document> orders;

    public TenantOrderRepository451(MongoDatabase database) {
        this.orders = database.getCollection("orders");
    }

    private Bson tenantOnly(AuthorizedTenant451 scope) {
        Objects.requireNonNull(scope, "Authorized tenant required");
        return eq("tenantId", scope.tenantId());
    }

    private Bson byId(
            AuthorizedTenant451 scope, ObjectId id) {
        return and(tenantOnly(scope), eq("_id", id));
    }

    public Document findById(
            AuthorizedTenant451 scope, ObjectId id) {
        return orders.find(byId(scope, id)).first();
    }

    public List<Document> recent(
            AuthorizedTenant451 scope, int pageSize) {
        int safeLimit = Math.max(1, Math.min(pageSize, 100));
        return orders.find(tenantOnly(scope))
            .sort(Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")))
            .limit(safeLimit)
            .into(new ArrayList<>());
    }

    public long count(
            AuthorizedTenant451 scope, String status) {
        return orders.countDocuments(
            and(tenantOnly(scope), eq("status", status)));
    }

    public void insert(
            AuthorizedTenant451 scope,
            String orderNumber,
            long amountMinor) {
        if (amountMinor < 0L) {
            throw new IllegalArgumentException("Negative amount");
        }
        orders.insertOne(new Document("_id", new ObjectId())
            .append("tenantId", scope.tenantId())
            .append("orderNumber", orderNumber)
            .append("amountMinor", amountMinor)
            .append("status", "CREATED")
            .append("createdAt", new java.util.Date()));
    }

    public Document markPaid(
            AuthorizedTenant451 scope, ObjectId id) {
        return orders.findOneAndUpdate(
            and(byId(scope, id), eq("status", "CREATED")),
            combine(
                set("status", "PAID"),
                currentDate("updatedAt")),
            new FindOneAndUpdateOptions()
                .returnDocument(ReturnDocument.AFTER));
    }

    public long deleteIfCreated(
            AuthorizedTenant451 scope, ObjectId id) {
        return orders.deleteOne(
            and(byId(scope, id), eq("status", "CREATED")))
            .getDeletedCount();
    }
}
```

### 23.1. Quan trọng hơn import: mọi đường CRUD đều scope

Trong ví dụ:

- `findById` — `tenantId + _id`.
- `recent` — chỉ những documents của tenant.
- `count` — không đếm orders tenant khác.
- `insert` — tenant lấy từ authorized scope.
- `markPaid` — tenant + id + trạng thái nghiệp vụ.
- `deleteIfCreated` — tenant + id + điều kiện domain.

### 23.2. Tránh exposing raw collection

Nếu controller có thể truy cập `orders` trực tiếp, một developer có thể bypass safe wrapper bằng `orders.find()`. Dùng module boundaries, DI, code review, static analysis và integration tests.

### 23.3. Unknown ID trả gì?

Nếu `findById` không tìm thấy record trong tenant, API thường trả 404 hoặc generic not-found/forbidden theo security policy. Tránh tiết lộ “order tồn tại trong tenant khác”.

### 23.4. Chặn update tenantId

Không cho client chọn tên field tùy ý để update:

```java
// Cấm: truyền trực tiếp body được dựng từ user vào update.
orders.updateOne(filter, new Document("$set", userSuppliedPatch));
```

Whitelist các trường được phép; tuyệt đối không cho user sửa `_id`, `tenantId`, `ownership` hoặc những internal migration/security fields.

## 24. Một lớp filter gốc giúp tránh quên tenant scope

Ví dụ:

```java
import org.bson.conversions.Bson;
import com.mongodb.client.model.Filters;

public final class TenantFilters451 {
    private TenantFilters451() {}

    public static Bson within(
            AuthorizedTenant451 scope,
            Bson domainPredicate) {
        if (scope == null) {
            throw new SecurityException("Missing tenant context");
        }
        if (domainPredicate == null) {
            throw new IllegalArgumentException(
                "Explicit domain predicate required");
        }
        return Filters.and(
            Filters.eq("tenantId", scope.tenantId()),
            domainPredicate
        );
    }
}
```

### 24.1. `$and` tốt hơn merge tùy tiện

Nếu ứng dụng gộp hai JSON objects bằng thao tác `putAll`, một user filter có key `tenantId` có thể **ghi đè** tenant filter được server tạo.

```text
Trusted:   { tenantId: "north-shop" }
Untrusted: { tenantId: "big-mart", status: "PAID" }

Unsafe object merge -> filter tenantId="big-mart"
```

Thay vì merge, dùng:

```javascript
{
  $and: [
    { tenantId: "north-shop" },
    { status: "PAID" }
  ]
}
```

Nếu domain predicate cố lọc tenant khác, kết quả là empty; không được override trusted scope.

### 24.2. Filter guard chưa bảo vệ mọi operation

`TenantFilters451.within()` không tự bảo vệ:

- `aggregate` có `$lookup`/`$unionWith`.
- Data được đọc từ cache.
- `insertOne` không dùng filter.
- Index/admin commands.
- Background jobs không gọi wrapper.

Do đó repository/API design cần **closed set of allowed methods**, test toàn bộ paths và phân quyền theo operation.

## 25. BulkWrite: một operation sai có thể làm hại tenant khác

`bulkWrite()` nhận danh sách models; nếu một model thiếu tenant scope, cả request có thể chứa unsafe update/delete.

### 25.1. Sai

```java
new UpdateOneModel<Document>(
    Filters.eq("_id", orderId),
    Updates.set("status", "PAID")
);
```

### 25.2. Đúng

```java
new UpdateOneModel<Document>(
    Filters.and(
        Filters.eq("tenantId", scope.tenantId()),
        Filters.eq("_id", orderId)
    ),
    Updates.set("status", "PAID")
);
```

### 25.3. Bulk insert

Mọi document phải được backend gắn `tenantId` từ authorized context, không giữ `tenantId` bất kỳ do client gửi.

### 25.4. Upsert đặc biệt nguy hiểm

```java
orders.updateOne(
    Filters.eq("externalId", externalId),
    update,
    new UpdateOptions().upsert(true));
```

Nếu thiếu `tenantId` và unique constraints thích hợp, request có thể update document tenant khác hoặc tạo resource không tenant.

An toàn hơn:

```java
orders.updateOne(
    Filters.and(
        Filters.eq("tenantId", scope.tenantId()),
        Filters.eq("externalId", externalId)
    ),
    Updates.combine(
        Updates.set("status", "READY"),
        Updates.setOnInsert("tenantId", scope.tenantId())),
    new UpdateOptions().upsert(true));
```

Và tạo unique index `{tenantId:1,externalId:1}` theo đúng topology. Concurrent upserts vẫn cần xử lý duplicate/retry đúng semantics.

### 25.5. Không tin updateCount

`matchedCount=1` chỉ xác nhận một record match filter. Nó không chứng minh operation đã tác động đúng business resource nếu filter thiếu tenant. Thiết kế filter đúng trước khi diễn giải result.

## 26. Aggregation: `$match` đầu pipeline là cần nhưng không đủ

API báo cáo doanh thu:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "north-shop",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$currency",
      totalMinor: { $sum: "$amountMinor" },
      count: { $sum: 1 }
    }
  }
]);
```

### 26.1. Lý do `$match` sớm

Giúp giới hạn input documents trong tenant, có thể hỗ trợ index và tránh báo cáo lẫn dữ liệu trước khi `$group`.

### 26.2. Không để client tự cung cấp arbitrary stages

Nếu UI gửi nguyên MongoDB aggregation pipeline:

```json
[
  { "$match": { "tenantId": "big-mart" } },
  { "$group": { "_id": null, "count": { "$sum": 1 } } }
]
```

backend không nên execute trực tiếp. Whitelist report types, metrics, sort/filter fields và tự xây pipeline server-side với scope.

### 26.3. `$facet`

`$facet` có nhiều subpipelines. Nếu pipeline nguồn đã được scope và không có stages khác mở rộng nguồn dữ liệu, các facets xử lý input đã giới hạn; nhưng phải hiểu các nested pipelines và không xem một `$match` đầu tiên là lá chắn cho `$unionWith`/lookups khác.

### 26.4. `$out`/`$merge`

Aggregation có thể ghi ra collection đích; phải scope source **và** target semantics. Nếu key của `$merge` thiếu tenant ID, hai tenants có thể overwrite/merge vào cùng target entry.

### 26.5. Cross-tenant reports

Nếu có báo cáo admin trên nhiều tenants, hãy dùng một endpoint/job **được phân quyền rõ** và ghi audit, không reuse query method tenant-specific rồi bỏ filter bằng null.

## 27. `$lookup`: rủi ro liên kết dữ liệu sai tenant

Một order lưu `customerId`. Nếu code join chỉ bằng customerId và customer IDs không globally unique, có thể lấy customer của tenant khác.

### 27.1. Sai: join chỉ theo business ID

```javascript
db.orders.aggregate([
  { $match: { tenantId: "north-shop" } },
  {
    $lookup: {
      from: "customers",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "customer"
    }
  }
]);
```

Nếu tenant `big-mart` cũng có `customerCode:"C001"`, kết quả có thể chứa customer của cả hai.

### 27.2. Đúng: join tenant + business key

```javascript
db.orders.aggregate([
  { $match: { tenantId: "north-shop" } },
  {
    $lookup: {
      from: "customers",
      let: {
        scopedTenant: "$tenantId",
        scopedCustomer: "$customerCode"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$scopedTenant"] },
                { $eq: ["$customerCode", "$$scopedCustomer"] }
              ]
            }
          }
        }
      ],
      as: "customer"
    }
  }
]);
```

### 27.3. Index hỗ trợ join

```javascript
db.customers.createIndex(
  { tenantId: 1, customerCode: 1 },
  { unique: true, name: "uniq_tenant_customer_code" }
);
```

`$lookup` dạng pipeline có điều kiện `$expr` có quy tắc index eligibility riêng theo version và phép so sánh. Hãy đo `explain`, không giả định index luôn được dùng tối ưu.

### 27.4. Một đoạn `$lookup` đúng không bảo vệ pipeline khác

Nếu sau đó có `$unionWith` hoặc nested lookups khác, mỗi đường lấy data phải được scope riêng.

### 27.5. Join bằng global ObjectId vẫn nên guard

Ngay cả khi `_id` globally unique, join tenant equality tăng độ an toàn trước dữ liệu import lỗi, ownership changes và business references không được kiểm soát.

## 28. `$unionWith`, `$graphLookup` và nested pipelines

### 28.1. `$unionWith` cần scope ở collection mới

```javascript
db.orders.aggregate([
  { $match: { tenantId: "north-shop" } },
  {
    $project: {
      tenantId: 1,
      eventType: { $literal: "ORDER" }
    }
  },
  {
    $unionWith: {
      coll: "supportTickets",
      pipeline: [
        { $match: { tenantId: "north-shop" } },
        {
          $project: {
            tenantId: 1,
            eventType: { $literal: "TICKET" }
          }
        }
      ]
    }
  }
]);
```

Nếu thiếu `$match` trong `$unionWith.pipeline`, pipeline có thể nhập tickets từ nhiều tenants, dù input chính đã scope.

### 28.2. `$graphLookup`

Truy vấn cây tổ chức/project references có thể di chuyển giữa documents. Phải hạn chế traversal bằng tenant scope như `restrictSearchWithMatch` phù hợp với một tenant đã authorized.

### 28.3. Không tin chỉ một pipeline AST scanner

Một chức năng “kiểm tra pipeline có `$match tenantId` ở stage đầu” không tự phát hiện mọi nested read source hoặc implicit write stage. An toàn hơn là chỉ cho service tự xây những pipelines đã được review, thay vì cho user điều khiển stages tổng quát.

### 28.4. Collections khác tenant boundary

Tham chiếu `files`, `messages`, `comments`, `invoices`, `auditEvents` cũng cần tenantId hoặc chính sách mapping/ownership được xác minh. Một collection phụ quên tenant scope có thể làm lộ data dù `orders` được bảo vệ tốt.

## 29. Search, text index và Atlas Search

### 29.1. MongoDB text search

Một collection shared có thể tạo text index cho trường có nhu cầu tìm kiếm; mọi search query phải scope tenant:

```javascript
db.products.find({
  tenantId: "north-shop",
  $text: { $search: "wireless keyboard" }
});
```

Text index có những ràng buộc về số lượng/type và query behavior; cần thiết kế theo schema/server version.

### 29.2. Atlas Search

Atlas Search có pipeline `$search` riêng; một `$match` đặt sau `$search` có thể lọc kết quả nhưng **không nhất thiết tối ưu** lượng tài liệu được search engine xử lý.

Nếu feature/index hỗ trợ filter trong `compound.filter`, nên scope tenant **bên trong search query** khi được thiết kế và kiểm chứng.

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_search",
      compound: {
        filter: [
          {
            equals: {
              path: "tenantId",
              value: "north-shop"
            }
          }
        ],
        must: [
          {
            text: {
              query: "wireless keyboard",
              path: "name"
            }
          }
        ]
      }
    }
  },
  { $limit: 20 }
]);
```

Search index mapping cho `tenantId` phải phù hợp với operator như `equals`; kiểm tra version/index definition và output. Đây là **data filtering**, không thay authorization ở tầng ứng dụng.

### 29.3. Vector Search

Với Atlas Vector Search, filter tenant trong vector query chỉ có tác dụng khi index/filter mappings và operator hỗ trợ. Không chấp nhận semantic similarity results từ tenants khác rồi chỉ ẩn ở frontend.

### 29.4. Search pagination và index lifecycle

Nếu user đổi tenant context, phải reset search cursor/continuation token. Metadata index builds/mapping và query rate cần tính vào noisy neighbor/cost controls.

## 30. Change streams, event bus và tenant isolation

Change streams giúp phát hiện thay đổi:

```javascript
const stream = db.orders.watch([
  {
    $match: {
      "fullDocument.tenantId": "north-shop",
      operationType: "insert"
    }
  }
]);
```

### 30.1. Cạm bẫy của `fullDocument`

Change events có hình dạng khác nhau theo operation type và `fullDocument` options. Với delete, document đầy đủ thường không xuất hiện trong event mặc định; chỉ nhìn `fullDocument.tenantId` có thể **bỏ lọt hoặc loại sai events**.

### 30.2. Event consumers cần routing context riêng

Một consumer vận hành chung cho mọi tenants có thể cần:

- Xác định tenant từ stable event/lookup mapping.
- Kiểm tra event type, namespace và version.
- Định tuyến đến queue/topic/bucket có quyền thích hợp.
- Idempotent processing/resume token management.
- Không publish raw data của tenant A sang subscription tenant B.

### 30.3. Resume token khác tenant cursor

Change stream resume token là checkpoint vị trí stream; không dùng nó như bằng chứng membership/authorization. Một subscriber muốn thay tenant phải được authorize và có stream policy tương ứng.

### 30.4. Đảm bảo không rò khi event không có full document

Thiết kế event envelope có `tenantId` được thiết lập từ trusted write path, hoặc lookup document keys theo scope đã biết, hoặc server-side pre/post image khi có requirements/versions phù hợp. Đừng tự giả định mọi delete event có đủ tenantId.

## 31. Transactions: atomicity không tự bảo đảm tenant correctness

Giả sử tạo đơn hàng và trừ tồn kho trong transaction:

```text
Tenant north-shop:
  insert order
  decrement inventory for P01
  insert audit event
  commit all or none
```

### 31.1. Transaction vẫn phải filter tenant

```java
try (ClientSession session = client.startSession()) {
    session.startTransaction();
    try {
        orders.insertOne(session, new Document("_id", new ObjectId())
            .append("tenantId", scope.tenantId())
            .append("orderNumber", "PO-451"));

        inventory.updateOne(
            session,
            Filters.and(
                Filters.eq("tenantId", scope.tenantId()),
                Filters.eq("sku", "P01"),
                Filters.gte("available", 1)),
            Updates.inc("available", -1)
        );

        // Ứng dụng thật cần xác minh matchedCount trước commit.
        session.commitTransaction();
    } catch (RuntimeException ex) {
        try {
            session.abortTransaction();
        } catch (RuntimeException abortError) {
            ex.addSuppressed(abortError);
        }
        throw ex;
    }
}
```

Code trên minh họa **tenant scoping**, không phải implementation transaction recovery hoàn chỉnh. Production cần validate result của inventory update, retry theo transaction labels, giới hạn thời gian và đảm bảo business idempotency.

### 31.2. Transaction lẫn hai tenants vẫn có thể commit

Nếu code cố ý update document A và B trong cùng transaction mà DB identity có quyền, MongoDB không tự coi đó là vi phạm. Atomicity không thay authorization.

### 31.3. Cross-tenant operations thật sự

Một operator migration có thể cần chuyển dữ liệu giữa tenants, nhưng đó phải là action có policy/audit riêng. Không dùng public “transfer order” API cho phép nhập arbitrary source/destination tenant IDs.

### 31.4. Retry transaction

Trong MongoDB, `TransientTransactionError` có thể đòi retry transaction body, còn `UnknownTransactionCommitResult` cần xử lý retry commit theo semantics. Không gửi payment/email trực tiếp trong callback có thể được gọi lại nếu chưa có outbox/idempotency.

### 31.5. Sharded transactions

Distributed transactions có chi phí/giới hạn và performance khác single-shard transaction. Tenant affinity với shard key có thể giảm cross-shard work trong một số patterns, nhưng phải đo actual routing.

## 32. Tenant-scoped cache: lỗi MongoDB đúng nhưng API vẫn lộ dữ liệu

Ví dụ cache sai:

```java
String cacheKey = "order:" + orderId;
```

Nếu order IDs được tái sử dụng per tenant hoặc có endpoint đọc sai scope, cache có thể trả resource của tenant khác.

### 32.1. Cache key đúng phạm vi

```java
String cacheKey =
    "order:v2:" + scope.tenantId() + ":" + orderId;
```

### 32.2. Cache key cần thêm authorization scope khi cần

Một response có thể khác nhau theo role, region, masking policy, version. Với dữ liệu nhạy cảm, chỉ tenantId đôi khi chưa đủ; design theo **exact authorization and visibility semantics**.

### 32.3. Cache invalidation

Khi order update/delete:

- Invalidate cache key của tenant tương ứng.
- Không invalidate tenant khác qua ID trùng.
- Không tái sử dụng cached projection của admin cho user quyền thấp.
- Đảm bảo các tenant migrations không đẩy dữ liệu cũ vào cache sau cutover.

### 32.4. Cache là một phần của tenant isolation test

Một test phải làm nóng cache bằng tenant A, sau đó dùng tenant B cùng orderNumber/id pattern và xác minh không đọc A.

## 33. Object storage và attachments

MongoDB document có thể lưu `fileKey` trỏ đến S3-compatible bucket hoặc blob storage:

```javascript
{
  _id: ObjectId("673400000000000000000451"),
  tenantId: "north-shop",
  fileKey: "tenant/north-shop/orders/PO-0007.pdf"
}
```

### 33.1. File key không phải authorization

Chỉ vì đường dẫn chứa tenantId không có nghĩa user tự động có quyền tải file. Backend cấp signed URL phải:

1. Xác minh tenant context.
2. Đọc attachment metadata với tenant-scoped MongoDB filter.
3. Kiểm tra quyền đối với resource.
4. Tạo URL ngắn hạn cho đúng object/version.

### 33.2. Không nhận raw fileKey từ client rồi ký URL

Endpoint `/download?key=tenant/big-mart/...` không được ký bất kỳ key nào chỉ vì caller đã đăng nhập. Key cần được resolve từ authorized document.

### 33.3. Delete tenant

Xóa records MongoDB không tự xóa attachments; cần liệt kê object ownership, event/audit trail và retention policy.

## 34. Schema version và custom fields theo tenant

Tenant A thêm một field tùy chỉnh, tenant B không có:

```javascript
{
  tenantId: "north-shop",
  schemaVersion: 4,
  status: "PAID",
  customFields: {
    deliveryZone: "HCM-Q1",
    salesChannel: "WEB"
  }
}
```

### 34.1. Custom fields không nên biến thành arbitrary BSON

Nếu client được gửi bất kỳ field name và type nào:

- Schema/index phát triển khó kiểm soát.
- Query performance bất định.
- Có thể đụng reserved names.
- Payload rất lớn.
- Security policy/masking khó quản lý.

Nên có schema registry/config per tenant, giới hạn số fields/kiểu/độ dài và validate trên server.

### 34.2. Shared schema + extensions

Một phương án:

- Core fields chuẩn: tenantId, _id, status, timestamps, amount.
- `customFields` với tên/kiểu được registry kiểm soát.
- Common indexes trên core fields.
- Chỉ những custom fields quan trọng mới được index theo policy.

### 34.3. Wildcard index

MongoDB hỗ trợ wildcard indexes cho documents có cấu trúc linh hoạt, nhưng không thay schema discipline và không nên dùng để index vô giới hạn mọi custom field khi thiếu đo lường.

### 34.4. Schema validator

Collection validator có thể yêu cầu `tenantId` có type string và status theo enum, nhưng không thể tự chứng minh tenantId trong body là tenant caller được authorize.

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "orderNumber", "status"],
      properties: {
        tenantId: { bsonType: "string" },
        orderNumber: { bsonType: "string" },
        status: {
          enum: ["CREATED", "PAID", "CANCELLED"]
        }
      }
    }
  },
  validationLevel: "moderate"
});
```

Đây là ví dụ cho test collection và `validationLevel:moderate` có semantics dành cho documents cũ không hợp lệ; production chọn strict/moderate và validationAction theo rollout, không sao chép mặc định.

## 35. Tenant provisioning: tạo tài nguyên có kiểm soát

Một tenant mới cần:

```text
Signup approved
      |
      v
Create tenant registry record (PROVISIONING)
      |
      v
Allocate database/cluster or shared namespace
      |
      v
Create required collections/indexes/roles
      |
      v
Seed default configs
      |
      v
Verify connectivity and permission
      |
      v
Tenant state ACTIVE
```

### 35.1. Provisioning phải idempotent

Nếu worker crash sau khi tạo database/indexes nhưng trước khi update registry, retry phải detect existing resources và hoàn tất an toàn, không tạo duplicate tenants/credentials/collections.

### 35.2. State machine

```text
REQUESTED -> PROVISIONING -> ACTIVE
                    |
                    +----> FAILED / REPAIR_REQUIRED

ACTIVE -> SUSPENDED -> DELETING -> DELETED
```

Không kích hoạt API cho tenant state `PROVISIONING` nếu indexes/quyền thiết yếu chưa sẵn sàng.

### 35.3. Registry integrity

Tenant registry có thể dùng unique index trên `_id`/slug và routing metadata version, hạn chế write privilege. Thay đổi `clusterKey`/`databaseName` cần audit và careful cutover.

### 35.4. Index creation race

Nhiều provisioning workers cùng gọi `createIndex` hoặc khởi tạo collections có thể xung đột cấu hình. Dùng orchestration/idempotent DDL plans và xử lý states khi index build thất bại.

### 35.5. Billing và limits

Provisioning có thể khởi tạo quotas/tier. Đừng bắt đầu index builds nặng trên shared production cluster chỉ để tạo tenant thử nghiệm nhỏ nếu policy yêu cầu trì hoãn.

## 36. Online schema migration trong multi-tenancy

Một migration thêm `invoiceStatus` vào `orders` có thể cần cập nhật hàng triệu documents nhiều tenants.

### 36.1. Expand–migrate–contract

```text
Expand:
  allow old and new documents
  deploy readers/writers compatible

Migrate:
  backfill by tenant/range with checkpoints
  throttle to protect user traffic
  fix poison documents

Verify:
  missing/stale counts per tenant
  semantic correctness and sampled values

Contract:
  enforce schema after all tenants ready
  remove old fallback per cutover policy
```

### 36.2. Một checkpoint mỗi partition

```javascript
{
  _id: "invoice-status-v3:north-shop:range-0001",
  tenantId: "north-shop",
  migrationVersion: 3,
  state: "RUNNING",
  lastScannedId: ObjectId("673400000000000000000451"),
  highWatermarkId: ObjectId("6734ffffffffffffffffffff")
}
```

### 36.3. Throttling per tenant và toàn cluster

Nếu mỗi tenant worker chạy ở 100 docs/s và có 500 workers, tổng có thể là 50.000 docs/s. Cần global budget, backpressure và fairness.

### 36.4. Idempotency

Migration nên dùng deterministic `$set`/revision checks, không dùng `$inc` từ giá trị đã tính nếu replay có thể nhân đôi.

### 36.5. Kiểm tra không vượt tenant

Mọi scan/filter, update target và DLQ records phải giữ đúng tenant. Nếu worker partition theo tenant nhưng query bỏ tenantId, checkpoint của tenant A có thể đánh dấu đã xử lý documents B.

### 36.6. Schema version

Một tenant enterprise có thể được cutover muộn hơn. Registry/schemaVersion cần tương thích với application read path; tránh chạy API chỉ hiểu version 5 với database tenant còn version 3.

## 37. Chuyển tenant từ shared sang dedicated storage

Khi tenant `big-mart` quá lớn:

```text
Before:
  shared.orders (tenantId=big-mart)

After:
  dedicated_big_mart.orders
```

### 37.1. Không chỉ `copy rồi đổi URI`

Trong lúc copy, ứng dụng vẫn nhận writes. Nếu chỉ copy snapshot rồi chuyển routing, updates xảy ra sau snapshot có thể mất.

### 37.2. Protocol khái niệm

1. Provision dedicated target và index/schema phù hợp.
2. Ghi nhận source/version/cutover plan.
3. Backfill tenant data bằng bounded scans và checksums/counts.
4. Dùng dual-write hoặc CDC catch-up đảm bảo những writes trong lúc copy không mất.
5. Verify target parity và consistency.
6. Ngăn split-brain writes bằng routing lease/version hoặc controlled brief write gate.
7. Switch tenant routing metadata atomically theo ứng dụng.
8. Canary reads và monitor.
9. Giữ source trong retention/rollback window có kiểm soát.
10. Purge source khi được duyệt.

### 37.3. Routing version là một safety guard

```javascript
{
  tenantId: "big-mart",
  clusterKey: "enterprise-a",
  databaseName: "tenant_big_mart",
  routingVersion: NumberLong("6")
}
```

Nếu hai app instances giữ routing versions khác nhau, chúng có thể ghi vào hai clusters khác nhau. Cần TTL cache, invalidation, fencing/cutover gate và observability.

### 37.4. Không dựa vào high-water mark đơn thuần

ObjectId/orderId cursor không tự tạo snapshot tính nhất quán. Handoff phải xử lý concurrent inserts/updates/deletes, retry, CDC resume window và business idempotency.

### 37.5. Rollback

Rollback routing sau khi đã có writes ở target cần kế hoạch replay ngược/dual-write hoặc controlled freeze; đổi string metadata trở lại không tự hợp nhất dữ liệu.

## 38. Backup và restore cho từng tenant

### 38.1. Shared collection

Backup/PITR thường bảo vệ cluster/database/collections theo giải pháp đang dùng. Muốn restore một tenant **không thể mặc định restore snapshot toàn shared collection đè lên production**, vì sẽ ảnh hưởng tenants khác.

Một kế hoạch:

1. Restore snapshot sang **isolated temporary environment**.
2. Trích những documents có tenantId đích.
3. So sánh revisions/timestamps với production.
4. Quyết định merge vs replace theo domain.
5. Upsert/restore qua guarded migration.
6. Verify references, indexes, search/cache.

### 38.2. Database-per-tenant

Database scope có thể giúp logistics export/restore riêng tenant, nhưng khả năng point-in-time/per-database restore thực tế phụ thuộc Atlas/self-managed backup mechanism. Không khẳng định bất kỳ snapshot service nào có one-click tenant restore.

### 38.3. Cluster-per-tenant

Backup/restore có thể cô lập nhiều hơn, nhưng vẫn cần kiểm tra external data stores, event bus và consistency với các hệ thống khác.

### 38.4. Tenant-level recovery objective

Thiết kế RPO/RTO per tier và biết tenant nào được ưu tiên khi xảy ra outage; lưu backup policy và test restoration như một phần onboarding.

### 38.5. Encryption và retention của backup

Backup có thể chứa data đã xóa khỏi database production. Cần retention/deletion policy, key management và hiểu các giới hạn của giải pháp backup; đừng tuyên bố “xóa document là mọi bản sao không còn”.

## 39. Tenant offboarding và xóa dữ liệu

### 39.1. Xóa tenant là một workflow

```text
Tenant requests deletion
        |
        v
Check legal hold / retention obligations
        |
        v
Mark DELETING and reject new writes
        |
        v
Revoke sessions, API keys, service grants
        |
        v
Delete MongoDB records safely
        |
        v
Delete search/cache/object storage/exports
        |
        v
Verify counts and audit evidence
        |
        v
Mark DELETED
```

### 39.2. Shared collection deletion

Nếu có khối lượng lớn, không nhất thiết gọi một `deleteMany({tenantId})` khổng lồ trong giờ cao điểm. Có thể delete theo lô với keyset/cursor và throttling, checkpoint, tránh vượt latency SLO.

### 39.3. Không drop shared collections

`db.orders.drop()` xóa dữ liệu của **mọi tenants**. Không dùng drop cho tenant offboarding ở shared collection.

### 39.4. Database-per-tenant drop

`dropDatabase()` có thể phù hợp ở chế độ dedicated database **khi tenant ownership đã được xác nhận, backup/hold policy cho phép và operator phê duyệt**. Chỉ một sai sót routing/namespace có thể gây mất dữ liệu tenant khác.

### 39.5. Không tái cấp tenantId

Việc tái sử dụng tenant ID của khách hàng đã xóa có thể làm cache keys, backup metadata, webhook/event references bị gán nhầm tenant mới. Nên dùng ID không tái sử dụng.

### 39.6. Xác nhận deletion scope

Mọi delete job cần thể hiện tenant registry ID, namespace mapping, số documents dự kiến, approval và dry-run counts; không tin trực tiếp tên database/collection do API gửi.

## 40. Encryption theo tenant

### 40.1. Encryption at rest và in transit

TLS bảo vệ đường truyền; encryption at rest bảo vệ lớp lưu trữ theo giải pháp MongoDB/Atlas. Chúng không tự giới hạn việc một DB credential có quyền đọc documents tenant khác.

### 40.2. Client-Side Field Level Encryption (CSFLE)

CSFLE cho phép ứng dụng mã hóa những fields nhất định trước khi gửi tới MongoDB, với key management riêng.

### 40.3. Queryable Encryption

Queryable Encryption hỗ trợ những kiểu query trên dữ liệu mã hóa theo capabilities/version; không tự xem mọi operator/aggregation/index có hành vi giống plaintext.

### 40.4. Tenant-specific DEK

Một thiết kế có thể dùng Data Encryption Key (DEK) khác nhau cho từng tenant hoặc nhóm tài liệu. Điều này giúp một số yêu cầu tách keys, nhưng có trade-offs:

- Quản lý nhiều keys và key metadata.
- Rotation/rekey workflows.
- KMS latency/availability.
- Metadata cần thiết để chọn đúng key.
- Tương tác unique indexes, search, aggregation, collation.

### 40.5. Không coi encryption là authorization

Nếu application service có quyền giải mã mọi tenants, lỗi lấy nhầm tenant key hoặc query thiếu scope vẫn có thể làm lộ dữ liệu ở application. Cần RBAC/authz và key selection guards cùng lúc.

### 40.6. Không log plaintext sau decrypt

Encryption chỉ bảo vệ trước database storage; application logs, tracing và exports có thể vẫn chứa plaintext nếu không có data handling policy.

## 41. Noisy neighbor: một tenant lớn ảnh hưởng mọi tenant

SaaS shared collection:

```text
Tenant trial-17:
  10 requests/sec, 50 MB data

Tenant north-shop:
  100 requests/sec, 2 GB data

Tenant big-mart:
  5,000 requests/sec, 700 GB data,
  full aggregation scans

All share:
  mongod CPU
  WiredTiger cache
  disk IOPS
  storage/network
  connection capacity
```

Một aggregation của `big-mart` có thể tạo I/O/CPU pressure khiến latency của `north-shop` tăng, dù các tenants không bao giờ đọc dữ liệu của nhau.

### 41.1. Các lớp bảo vệ

- Tenant-aware API rate limits.
- Concurrency caps theo tenant cho những operations đắt.
- Query deadlines/`maxTimeMS` hoặc client-side timeout theo supported APIs.
- Bounded report/export jobs, background queues.
- Compound indexes cho patterns phổ biến.
- Giới hạn số records/export size.
- Per-tier quotas về data volume và retention.
- Workload partitioning: tách analytics khỏi OLTP khi phù hợp.
- Chuyển tenant quá lớn sang dedicated cluster khi cần.

### 41.2. Không chỉ giới hạn requests/s

100 `find({_id})` rất rẻ có thể ít tốn hơn một aggregation scan 300 triệu records. Cần tính **cost model** hoặc ít nhất chia operation class (simple lookup, list, report, export, write).

### 41.3. Database profiler

Slow query logging/profiler có thể giúp xác định query shapes, nhưng không tự hiểu tenant business context nếu log không có thông tin được phép sử dụng. Không bật profiler chi tiết với data payload nhạy cảm tùy tiện.

### 41.4. Rate limit fairness

Nếu chia per-tenant rate limit mà mỗi tenant có nhiều user/API keys, hãy giới hạn đúng scope để không bị vượt tổng bằng cách tạo nhiều keys.

### 41.5. Không hứa isolation hiệu năng tuyệt đối

Shared cluster chỉ giảm noisy-neighbor risk; không bảo đảm tài nguyên dedicated như một cluster riêng.

## 42. Capacity planning cho mô hình shared

Một ước lượng khối lượng:

\[
\text{TotalData} =
\sum_{t=1}^{T} \text{DataSize}(t)
\]

Nhưng chi phí thực tế còn gồm indexes, replication, oplog, temporary space, backups và query working sets.

### 42.1. Ví dụ

```text
Tenants: 10,000
Average documents/tenant: 50,000
Average BSON document: 1 KiB

Raw logical data (before storage/index overhead):
10,000 * 50,000 * 1 KiB
≈ 477 GiB
```

Con số trên là ước lượng thô; storage size thực chịu ảnh hưởng compression, document sizes, indexes, replication và database internals.

### 42.2. P99 tenant có thể khác trung bình rất xa

Nếu 1% tenants tạo ra 90% I/O, trung bình không dự đoán được hotspot. Phải tính:

- Top 1/10 tenants by storage.
- Top 1/10 tenants by read/write QPS.
- P95/p99 API latency theo tenant tier.
- Large aggregations và index working set.
- Peak seasonal spikes.

### 42.3. Namespace overhead trong database-per-tenant

Nếu mỗi tenant có 25 collections × 7 indexes/collection, 5.000 tenants có thể kéo theo lượng collection/index metadata rất lớn. Dù số byte data nhỏ, catalog/index maintenance có thể thành bài toán riêng.

### 42.4. Dedicated clusters có fixed cost

Tách mỗi tenant ra cluster riêng tạo overhead cho compute, monitoring, backup, patching, credentials và on-call. Đặt tier thresholds dựa trên dữ liệu, không chỉ mong muốn “cô lập tối đa”.

## 43. Connection pools trong Java SaaS

`MongoClient` quản lý server discovery và connection pools; thường nên là object sống lâu.

### 43.1. Shared cluster

```java
MongoClient client = MongoClients.create(sharedUri);

MongoDatabase shared = client.getDatabase("saas");
MongoCollection<Document> orders = shared.getCollection("orders");
```

Không tạo MongoClient mới cho mỗi HTTP request hoặc mỗi tenant nếu tất cả cùng dùng cluster/credentials.

### 43.2. Database-per-tenant

```java
MongoDatabase tenantDb = client.getDatabase(trustedDbName);
```

Lấy `MongoDatabase` handle rẻ hơn mở một client mới; namespace phải được resolve từ registry.

### 43.3. Cluster-per-tenant

Có thể cần clients theo connection settings, host, credentials, TLS certificates. Dùng cache có:

- Maximum entries/capacity.
- Idle eviction/controlled close.
- Metrics for pools and active clients.
- Credential rotation support.
- Reference counting hoặc lifecycle tránh close khi request còn dùng.

### 43.4. Tính toán connection upper bound

Nếu có 100 app pods, mỗi pod dùng pool max 100 tới một server:

```text
Potential pooled connections per server
≈ 100 pods × 100 = 10,000
```

Chưa tính monitoring sockets/other services; không suy từ một `maxPoolSize=100` rằng cluster chỉ nhận tối đa 100 connections.

### 43.5. Dynamic tenant client cache không tự an toàn

Nếu connection config lấy từ untrusted tenant metadata, một attacker có thể gây SSRF/credential leakage bằng cách đổi URI. Cluster keys phải đến từ allowlisted registry và secrets store đáng tin.

## 44. Monitoring, alerting và cost attribution

Gợi ý metrics:

| Metric | Đơn vị | Labels nên cân nhắc |
|---|---|---|
| `tenant_api_requests_total` | Requests | Tier, route, outcome |
| `tenant_api_latency_seconds` | Histogram | Tier, route |
| `tenant_query_errors_total` | Errors | Query family, error class |
| `mongodb_command_duration_seconds` | Histogram | Command name, service |
| `mongodb_pool_checkout_seconds` | Histogram | Cluster, service |
| `tenant_storage_bytes` | Bytes | Tenant bucket/tier hoặc export ngoài TSDB |
| `tenant_report_queue_depth` | Jobs | Tier, priority |
| `tenant_quota_rejections_total` | Counts | Operation class, tier |
| `tenant_security_denials_total` | Counts | Reason class, route |

### 44.1. Tenant ID và cardinality

Gắn 50.000 tenant IDs vào mọi Prometheus histogram route/status/method có thể gây cardinality explosion. Cân nhắc:

- Metrics aggregate theo tier, cluster, plan.
- Separate top-N tenant dashboards.
- Logs/traces có tenant ID pseudonymous và access-controlled.
- Billing/cost attribution trong data warehouse thay vì mọi ID làm TSDB label.

### 44.2. Đếm không phải quyền

Metering cho thấy tenant A gửi 500 requests, nhưng không xác định một request có được phép đọc B hay không. Security audit cần correlation actor–tenant–resource/action–decision.

### 44.3. Alerts

- Cross-tenant access denials tăng đột ngột.
- Query thiếu tenant scope bị guard từ chối.
- P99 latency theo tier/cluster cao.
- Một tenant chiếm quá nhiều CPU/IO.
- Replica set election, pool checkout timeouts.
- Tenant routing version mismatch.
- Provisioning stuck/failed.
- Data migration parity failures.

### 44.4. Missing telemetry

Nếu instrumentation bị tắt, failure count = 0 không chứng minh không có lỗi. Monitor chính pipeline metrics/logs và dùng application SLO độc lập.

## 45. Audit logging và support access

Security log nên mô tả:

```text
timestamp=...
actorId=staff-123
tenantId=north-shop
action=orders.read
resourceType=order
resourceId=opaque-order-id
decision=ALLOW
policyVersion=17
requestTraceId=...
```

### 45.1. Không log raw order document

Order có thể chứa PII/payment/shipping data. Logs cần metadata tối thiểu để điều tra, không dump toàn bộ BSON hoặc JWT.

### 45.2. Break-glass support

Support access xuyên tenants nên yêu cầu:

- Identity quản trị riêng.
- Lý do/ticket và thời gian hiệu lực.
- Policy hoặc phê duyệt bổ sung theo mức nhạy cảm.
- Audit có thể đối soát.
- Revocation dễ thực hiện.

### 45.3. Đọc qua support tool vẫn là truy cập tenant data

Không bỏ authorization chỉ vì người gọi là internal service. Internal endpoints có thể có blast radius lớn hơn public API nếu credentials bị lộ.

### 45.4. Đổi tenant context

Mọi tenant switch cần cập nhật UI/cache/traces theo đúng scope; không giữ kết quả tenant cũ trên màn hình tenant mới.

## 46. Spring Data MongoDB: repository methods có tenant filter

Spring Data cung cấp `MongoTemplate` và repositories. Một phương án method rõ:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class SpringTenantOrderQueries451 {
    private final MongoTemplate template;

    public SpringTenantOrderQueries451(MongoTemplate template) {
        this.template = template;
    }

    public Order451 findOne(
            AuthorizedTenant451 scope, ObjectId orderId) {
        Query query = Query.query(
            Criteria.where("tenantId").is(scope.tenantId())
                .and("_id").is(orderId)
        );
        return template.findOne(query, Order451.class, "orders");
    }
}
```

`Order451` là entity do project định nghĩa. Code minh họa việc xây query chặt, không giả định Spring Data đã tự thêm tenant filter trên mọi repository.

### 46.1. Cẩn thận với `CrudRepository.findById`

Một repository thông thường có `findById(id)`, không bắt buộc filter tenant. Nếu app dùng shared collection và gọi method này trực tiếp, nó có thể bypass tenant-aware rules.

Hãy:

- Tạo custom tenant-scoped repository/service facade.
- Giới hạn những methods được expose.
- Viết integration tests cho mọi public data access paths.
- Kiểm tra derived query methods, custom `@Query` và aggregation methods.

### 46.2. `@Query` là contract của từng method

```java
@Query("{ 'tenantId': ?0, 'orderNumber': ?1 }")
Optional<Order451> findByTenantIdAndOrderNumber(
    String tenantId, String orderNumber);
```

Đây là ví dụ ký pháp; nó chỉ an toàn khi `tenantId` đến từ context đã authorize. Không expose public controller cho phép gọi arbitrary tenantId.

### 46.3. Context-bound interceptors

Một số ứng dụng custom instrumentation/hooks để inject tenant filters. Nhưng tenant-aware behavior phải bao quát read, update, delete, aggregation, count, exists, repository methods, pipeline lookups và non-Spring direct driver calls.

Không tin một “automatic filter” tự phát triển đã bảo vệ 100% khi chưa có integration tests kiểm tra mọi operation.

### 46.4. Reactive applications

Trong Spring WebFlux, tenant context có thể truyền qua Reactor Context chứ không dựa ThreadLocal của servlet. Test async boundary và message processing rõ.

## 47. Tenant authorization test matrix

Một ma trận tối thiểu:

| Action | Tenant A user | Tenant B user | Global admin theo policy |
|---|---|---|---|
| Read A order | Có nếu role cho phép | **Không** | Có nếu được cấp quyền và audit |
| Read B order | **Không** | Có nếu role cho phép | Có nếu được cấp quyền và audit |
| Update A order | Theo role/status | **Không** | Theo policy |
| Delete A order | Theo role/status | **Không** | Theo policy |
| List A orders | Chỉ A | Không | Theo scope explicit |
| Count A orders | Chỉ A | Không | Theo scope explicit |
| Aggregate A revenue | Chỉ A | Không | Theo scope explicit |
| Lookup customer của A | Chỉ A | Không | Theo scope explicit |
| Download file của A | Chỉ A | Không | Theo scope explicit |
| Export A report | Chỉ A | Không | Theo scope explicit |

### 47.1. Cần test cả “không nhìn thấy dữ liệu”

Một method trả empty với scope B khi truyền ID của tenant A là một assertion security quan trọng. Không chỉ assert A đọc được A.

### 47.2. Test update/delete

Chạy update/delete từ scope B trên ID của A và assert:

- `matchedCount/deletedCount=0`.
- Document A giữ nguyên.
- Audit ghi DENY/NOT_FOUND đúng policy, không rò nội dung A.

### 47.3. Test aggregation

Seed cùng `customerCode` ở hai tenants, thực hiện `$lookup` từ scope A, assert chỉ có customer A trong response.

### 47.4. Test pagination

Cursor được phát cho tenant A không dùng được với tenant B.

### 47.5. Test concurrent tenant switch

Trong cùng browser/session, chuyển A→B nhanh khi requests A còn in-flight; response không được hiển thị trong B context nếu UI policy không cho phép.

## 48. JUnit 5 + Testcontainers: kiểm thử cô lập dữ liệu

Ví dụ sử dụng **Testcontainers Java 2.x** với class `org.testcontainers.mongodb.MongoDBContainer`, single-node replica set; vẫn có thể dùng một MongoDB container để kiểm tra CRUD isolation cơ bản.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class TenantBoundary451IT {
    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void tenantBCannotReadOrMutateTenantAOrder() {
        try (MongoClient client =
                 MongoClients.create(mongo.getReplicaSetUrl())) {
            MongoDatabase db = client.getDatabase("tenant_test_451");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            ObjectId aId = new ObjectId();
            orders.insertOne(new Document("_id", aId)
                .append("tenantId", "north-shop")
                .append("orderNumber", "PO-7")
                .append("status", "CREATED"));

            var filterForB = and(
                eq("tenantId", "big-mart"),
                eq("_id", aId));

            assertNull(orders.find(filterForB).first());

            long changed = orders.updateOne(
                filterForB, set("status", "PAID"))
                .getMatchedCount();
            assertEquals(0L, changed);

            long deleted = orders.deleteOne(filterForB)
                .getDeletedCount();
            assertEquals(0L, deleted);

            Document a = orders.find(
                and(eq("tenantId", "north-shop"), eq("_id", aId)))
                .first();
            assertNotNull(a);
            assertEquals("CREATED", a.getString("status"));
        }
    }
}
```

### 48.1. Test này chứng minh gì?

MongoDB thực thi đúng các filters có tenantId. Nó **chưa** tự chứng minh production repository/controller luôn gọi đúng filters. Phải thêm tests qua service/API layer để ngăn bypass.

### 48.2. Test negative paths quan trọng hơn chỉ smoke test

Thêm tests:

- A đọc A thành công.
- B đọc ID của A → not found.
- B update/delete A → không sửa.
- Client gửi tenantId giả trong body → backend bỏ qua/deny.
- `$lookup` không join customer B vào order A.
- Admin path có audit và authorization riêng.

### 48.3. Không dùng database production

Giữ namespace test riêng và container disposable; đừng thay URI bằng production trong integration tests có seed/drop.

### 48.4. Test concurrency

Chạy A/B requests song song với khác scope trên thread pool, đảm bảo không có ThreadLocal leakage hoặc reused mutable query object mang filter tenant trước.

## 49. Property-based tests và security regression

Một cách test mạnh hơn vài IDs cố định:

1. Tạo 20 tenants test.
2. Mỗi tenant có 100 orders, customer codes trùng nhau giữa tenants.
3. Tạo random action sequences: insert, find, update, delete, count, aggregate.
4. Mọi action chạy với authorized scope.
5. Assert không có result document có `tenantId != scope.tenantId`.
6. Assert actions từ tenant khác không làm thay đổi state tenant mục tiêu.

### 49.1. Invariant

\[
\forall d \in \text{QueryResults}(t),\; d.\text{tenantId}=t
\]

Với writes:

\[
\forall d \in \text{ChangedDocuments}(op_t),\; d.\text{tenantId}=t
\]

Các invariant này áp dụng cho ordinary tenant-specific operations, không phải admin cross-tenant workflows được cấp phép riêng.

### 49.2. Mutation testing theo ý tưởng

Cố ý bỏ `tenantId` khỏi một repository method trong môi trường test rồi xác minh security regression test thất bại. Nếu test vẫn pass, có lỗ hổng coverage.

### 49.3. Không phụ thuộc orderId trùng

Ngay cả khi dùng globally unique ObjectId, phải thử một caller biết ID của tenant khác. Security boundary không nên dựa vào ID khó đoán.

### 49.4. Test error responses

Không để exception message/report/log phản hồi chứa fields của tenant khác, kể cả khi operation bị từ chối.

## 50. API test: tenant context phải đến từ server

Một flow:

```text
POST /api/orders
Authorization: Bearer <valid user token>
X-Tenant-Id: north-shop

Body:
  { "orderNumber": "PO-451", "amountMinor": 350000 }

Backend:
  verify token
  check active north-shop membership + permission
  create AuthorizedTenant451
  insert document tenantId=north-shop
```

### 50.1. Khách hàng cố tình đổi header

```text
Same user token
X-Tenant-Id: big-mart
```

Nếu user không có membership của `big-mart`, backend phải deny; không “tự chuyển tenant” theo header.

### 50.2. Role checks

Một user Viewer có thể đọc order trong tenant A nhưng không được hủy hoặc export dữ liệu nhạy cảm. Tenant equality cần thiết nhưng **không đủ** cho authorization.

### 50.3. Client-supplied query fields

API nên whitelist status, createdAt ranges, sort direction, pageSize. Không cho client truyền raw MongoDB operators như `$where`, `$lookup` hoặc serialized pipeline để thực thi không giới hạn.

### 50.4. Default-deny

Nếu tenant context null, membership service timeout hoặc registry chưa ready, không fallback sang `find({})` hoặc database mặc định. Phải fail closed theo policy.

## 51. Runbook 1 — Nghi ngờ API trả dữ liệu sai tenant

### Dấu hiệu

- User báo nhìn thấy order/customer không thuộc tổ chức.
- Response có `tenantId` khác scope đã xác thực.
- Logs cho thấy `findById` gọi chỉ theo `_id`.
- Analytics/export trả dữ liệu rộng hơn tenant yêu cầu.

### Ưu tiên xử lý

1. **Giới hạn ngay tác động**: vô hiệu hóa endpoint/report bị ảnh hưởng hoặc chặn bằng feature flag/gateway.
2. Bảo tồn logs và trace metadata an toàn, không phát tán thêm raw PII.
3. Xác định actor, tenant, request time, document IDs liên quan và các cache keys.
4. Soát query path: CRUD, aggregation, `$lookup`, cache, search, signed URLs.
5. Sửa repository để bắt buộc `AuthorizedTenant` và guard mọi operations.
6. Thêm regression test A/B tenants với overlapping business keys.
7. Đánh giá incident reporting, notifications và obligations theo chính sách tổ chức.

### Không làm

Không coi đây chỉ là lỗi giao diện và ẩn tenantId ở frontend. **Dữ liệu đã truyền về client vẫn là exposure**, kể cả UI không hiển thị.

### Điều kiện đóng incident

Đã chặn leak, có root cause, affected scope/time window, telemetry đáng tin, tests chống regression và kế hoạch xử lý dữ liệu/cache đã lộ.

## 52. Runbook 2 — Một tenant khiến toàn cluster chậm

### Dấu hiệu

```text
Tenant big-mart starts massive report
Cluster disk IOPS and CPU rise
API p99 for north-shop increases
Pool checkout and command latency rise
```

### Điều tra

1. Xem resource usage, currentOp/slow query logs theo policy.
2. Tìm query shapes gây scan/sort/aggregation lớn.
3. So sánh `totalDocsExamined` và `nReturned`.
4. Kiểm tra index prefix tenantId và sort.
5. Xem concurrency/queue per tenant.
6. Đánh giá workload hot tenant có cần tách cluster không.

### Xử lý

- Pause/giảm report workers của tenant gây tải theo policy.
- Thêm concurrency cap/rate limit và bounded query deadline.
- Tối ưu index/pagination/sampling hoặc materialized reports.
- Chuyển workload analytics sang resource phù hợp.
- Nếu cần, lập kế hoạch migrate tenant sang dedicated infrastructure.

### Không làm

Không tăng connection pool vô hạn để chữa collection scan hay I/O saturation.

## 53. Runbook 3 — Unique index không cho hai tenants dùng cùng orderNumber

### Dấu hiệu

Tenant A đã có `PO-001`; tenant B insert `PO-001` nhận `E11000 duplicate key` dù nghiệp vụ cho phép.

### Điều tra

```javascript
db.orders.getIndexes();
```

Tìm index `{orderNumber:1}` unique toàn collection thay vì `{tenantId:1,orderNumber:1}`.

### Xử lý

1. Kiểm tra dữ liệu hiện có: null/missing tenantId, duplicate trong cùng tenant.
2. Xác nhận business uniqueness scope.
3. Tạo compound unique index thích hợp theo capacity/change plan.
4. Rollout query/code đảm bảo đúng tenant filter.
5. Xử lý index cũ theo migration plan.
6. Test two tenants can reuse orderNumber, one tenant cannot duplicate it.

### Không làm

Không tự xóa unique index cũ trước khi có compound unique index, khi chưa hiểu writes concurrent; không đổi orderNumber của tenant B tùy tiện để che schema lỗi.

## 54. Runbook 4 — MongoDB DB user bị unauthorized

### Dấu hiệu

```text
MongoCommandException code 13 (Unauthorized)
MongoSecurityException / authentication error
```

### Điều tra

- Tenant đang dùng shared hay database-per-tenant?
- Service identity có quyền đúng namespace không?
- `authSource` và role mapping chính xác không?
- Tenant registry có trỏ nhầm database?
- Secret rotation có deploy hoàn chỉnh?
- App có bypass routing registry?

### Xử lý

Sửa DB role/credential/registry mapping dựa trên least privilege và phê duyệt; audit change.

### Không làm

Không cấp `root` cho app user hoặc tắt authentication để “tạm hết lỗi”. Không coi mã 13 là lỗi transient để retry vô hạn.

## 55. Runbook 5 — Tenant routing bị split-brain sau migration

### Dấu hiệu

Hai pods phục vụ `big-mart` nhưng một pod ghi shared cluster, pod khác ghi dedicated cluster.

### Nguyên nhân có thể

- Routing cache stale.
- Registry version không đồng nhất.
- Cutover thiếu write gate/fencing.
- CDC catch-up chưa kết thúc.
- Retry từ old background worker vẫn ghi source.

### Xử lý

1. Pause affected tenant writes nếu cần bảo vệ consistency.
2. Xác định authoritative target theo approved cutover version.
3. Thu log routingVersion và operation IDs từ các pods.
4. Reconcile writes trên hai destinations theo business identity.
5. Chặn stale writers bằng routing version/fencing.
6. Verify data parity và only then resume writes.

### Không làm

Không thay routing metadata ngược qua lại nhiều lần mà không giải quyết dữ liệu đã phát sinh ở mỗi bên.

## 56. Runbook 6 — Backup cần khôi phục riêng một tenant

### Dấu hiệu

Tenant `north-shop` yêu cầu khôi phục records bị xóa nhầm lúc 10:00, còn các tenants khác vẫn hoạt động bình thường.

### Phương án an toàn

1. Xác định RPO/RTO, trạng thái hiện tại và nghiệp vụ muốn restore.
2. Khôi phục snapshot/PITR vào môi trường tạm **tách biệt**.
3. Trích đúng tenant scope.
4. Xem docs mới được tạo sau thời điểm restore để tránh overwrite.
5. Dùng merge/restore procedure có identity/version checks.
6. Rebuild/invalidate indexes/search/cache cần thiết.
7. Verify references và audit impact.

### Không làm

Không restore toàn shared database đè lên production chỉ để khôi phục một tenant: tenants khác có thể mất writes hợp lệ.

## 57. Runbook 7 — Tenant deletion còn dữ liệu trong cache/search

### Dấu hiệu

MongoDB records đã xóa, nhưng search results/signed URL/export cũ vẫn truy cập được.

### Phản ứng

- Kiểm kê storage surfaces: MongoDB, object storage, search, cache, CDC sink, backups.
- Disable API keys/sessions và tenant routing trước.
- Purge cache keys theo tenant+resource.
- Xóa search documents bằng tenant scope và kiểm tra index state.
- Revoke signed URLs khi có cơ chế hỗ trợ, hoặc chờ TTL/đổi object keys theo policy.
- Kiểm tra legal hold/retention trước destructive operations.
- Ghi verification evidence, không chỉ log “deleteMany succeeded”.

### Không làm

Không kết luận “đã xóa tất cả” chỉ dựa trên `db.orders.countDocuments({tenantId}) == 0`.

## 58. Runbook 8 — Index mới làm tốc độ ghi giảm

### Dấu hiệu

Sau rollout thêm nhiều compound indexes, insert/update latency tăng và storage/index working set lớn.

### Điều tra

1. Liệt kê index mới và access patterns chúng phục vụ.
2. Dùng `explain` cho representative queries.
3. Kiểm tra index utilization/hidden indexes nếu feature phù hợp.
4. Đo write amplification, cache pressure, disk utilization và index build impact.
5. Phân biệt regression do app rollout hay background index builds.

### Xử lý

- Giữ các indexes chứng minh có lợi cho SLO.
- Loại bỏ/restructure indexes dư thừa theo migration plan.
- Cân nhắc materialized views hoặc phân lớp query/report.
- Với tenant cực lớn có custom patterns, xem database/cluster isolation nếu hợp lý.

### Không làm

Không drop index chỉ vì “không thấy dùng trong 5 phút”; workload weekly/monthly/report có thể phụ thuộc.

## 59. Tổng hợp anti-patterns trong thiết kế multi-tenant

| Anti-pattern | Hậu quả | Cách thay |
|---|---|---|
| `find({_id})` trong shared collection | Cross-tenant read | `tenantId + _id` |
| `updateOne/deleteMany` không tenant scope | Cross-tenant modification | Mandatory scoped filter |
| Tin `X-Tenant-Id` hoặc body | Client chọn tenant bất kỳ | Authenticate + membership check |
| Header được ký nhưng role đã revoke | Quyền stale | Revalidate theo policy/expiry |
| Mutable global currentTenant variable | Scope leak giữa threads | Explicit immutable context |
| ThreadLocal không cleanup | Scope còn từ request trước | Safe lifecycle/context propagation |
| Cho client raw MongoDB filter/pipeline | Bypass policy/complex queries | Whitelisted query builder |
| `$lookup` chỉ join customerCode | Lẫn customer các tenants | Join tenant+business key |
| `$unionWith` không filter nguồn phụ | Expose dữ liệu ngoài tenant | Scope subpipeline |
| `$merge` target key không có tenant | Overwrite shared report record | Tenant-aware target identity |
| Cache key chỉ orderId | Trả nhầm cache | Scope key theo tenant/visibility |
| Signed URL ký raw fileKey client gửi | Lộ attachments | Resolve from authorized resource |
| MongoDB RBAC được hiểu là row-level | False security assumption | App authz + server scopes |
| Mọi service dùng `root` | Blast radius rất lớn | Least-privilege identities |
| DB-per-tenant nhưng app có all-DB credential | Routing bug vẫn có quyền | Tách identities/policies nếu cần |
| Không có `tenantId` trên một collection phụ | Data leak qua relation | Ownership schema |
| Cho PATCH sửa `tenantId` | Chuyển dữ liệu trái phép | Immutable field/workflow riêng |
| Unique `orderNumber` toàn collection | Tenants xung đột | Unique composite tenant+orderNumber |
| Index chỉ `status` cho query tenant-specific | Scan rộng/slow | Compound index theo query |
| Tạo mỗi tenant một collection mặc định | Namespace/index explosion | Shared model/hybrid |
| Tạo MongoClient mỗi request/tenant | Connection storm | Reuse per cluster/config |
| Shard key chỉ tenantId với giant tenant | Data/hotspot limitations | Chọn compound/distribution phù hợp |
| Unique index sharded bỏ qua shard key rules | Không bảo đảm uniqueness | Check sharding constraints |
| Tự dùng `tenantId` như global commit order | Misleading correctness | Stable IDs/version/CDC |
| Search chỉ filter tenant ở UI | Kết quả đã lộ | Server-side search filter |
| Change stream luôn lấy tenant từ fullDocument | Delete event không có field | Trusted event envelope |
| Tenant restore đè shared DB | Mất dữ liệu tenants khác | Restore temp + scoped merge |
| Xóa MongoDB là offboard xong | Cache/files/search còn | End-to-end deletion |
| Nhiều tenants cùng budget 100% cluster | Noisy neighbor | Global/per-tenant quotas |
| Index mọi custom field | Memory/storage/write overhead | Allowlist/index by measured need |
| Claim “encrypted = authorized” | App có thể đọc chéo | RBAC + key selection + authz |
| Client cấp databaseName | Wrong namespace/SSRF risk | Trusted routing registry |
| Migration switch URI khi writes đang chạy | Split-brain/lost data | CDC/dual-write/fencing |
| Chỉ test happy-path tenant A | Không phát hiện cross-tenant | Negative A/B security tests |
| Log raw BSON, JWT hoặc credential | PII/secret exposure | Redacted structured metadata |
| Prometheus tag mọi tenantId | Cardinality explosion | Tier/top-N separate views |
| Coi cluster tách là hết rủi ro | App/cache/export vẫn có thể leak | End-to-end threat model |

## 60. Bảng chọn mô hình theo tình huống

| Tình huống | Ưu tiên xem xét | Câu hỏi cần kiểm chứng |
|---|---|---|
| 20.000 tenants rất nhỏ | Shared collections | Có authz guards và indexing tốt? |
| 100 tenants, mỗi tenant schema/retention khác | Database/collection per tenant | Index/catalog overhead chịu được? |
| Một enterprise tenant chiếm phần lớn I/O | Hybrid/dedicated cluster | Resource isolation/SLO ra sao? |
| Tenant có residency region riêng | Cluster routing theo region | Backups/logs/exports có đúng vùng? |
| Multi-tenant analytics across all tenants | Shared data model hoặc analytics copy | Có admin authorization/audit? |
| Tenant-level DB credentials bắt buộc | DB per tenant hoặc cluster per tenant | Identity/pool management mở rộng thế nào? |
| Cần restore thường xuyên từng tenant | DB/cluster riêng hoặc restore workflow | Backup mechanism hỗ trợ granularity nào? |
| Custom Atlas Search ranking per tenant | Hybrid/index strategy | Index mapping/cost phù hợp? |
| Hàng tỷ shared documents | Sharding | Shard key targeting, skew và uniqueness? |
| Gói thử miễn phí rất nhiều tenants | Shared model + quotas/TTL | Noisy-neighbor và retention policy? |

Đây là gợi ý thiết kế, không phải tiêu chuẩn bắt buộc. Quyết định cuối dựa trên prototype, threat modeling, compliance thực tế, SLO và chi phí vận hành.

## 61. Bài tập thực hành

### Bài 1 — Phân biệt tenant và user

Alice thuộc tenant A với vai trò Admin và tenant B với vai trò Viewer. Giải thích vì sao identity của Alice không đủ để xác định quyền trên một order.

### Bài 2 — Chọn mô hình

Một SaaS có 30.000 tenants, trung bình 500 documents/tenant. So sánh shared collection, collection per tenant và database per tenant, nêu chi phí namespace/index.

### Bài 3 — Enterprise tenant

Một tenant chiếm 70% disk IOPS và có SLO riêng. Phân tích khi nào cần dedicated database/cluster, và điều gì database-per-tenant vẫn chưa cô lập được.

### Bài 4 — Threat model

Vẽ đường đi GET /orders/{id} qua authentication, membership, service, MongoDB, cache và response. Đánh dấu ít nhất năm điểm có thể rò dữ liệu.

### Bài 5 — Header giả mạo

Một user chỉ thuộc tenant A gửi `X-Tenant-Id:B`. Viết pseudocode validate identity/membership trước khi tạo `AuthorizedTenant`.

### Bài 6 — Global ObjectId

Giải thích vì sao ObjectId khó đoán không thể thay authorization. Viết filter an toàn cho `findById`.

### Bài 7 — Unique index per tenant

Hai tenants đều có orderNumber `INV-100`. Viết compound unique index cho phép trường hợp này và chặn duplicate trong cùng tenant.

### Bài 8 — Soft delete

Thiết kế partial unique index khi active document được định nghĩa bởi `deletedAt` **không tồn tại**. Tại sao dùng `deletedAt:null` không nhất thiết tương đương?

### Bài 9 — Case-insensitive uniqueness

Tenant A muốn `INV-001` và `inv-001` được coi là trùng. Thiết kế collation/index hoặc canonical key có quy tắc rõ.

### Bài 10 — Access pattern indexing

Query `find({tenantId,status}).sort({createdAt:-1}).limit(50)` cần index nào? Giải thích equality/sort và cách đo bằng `explain`.

### Bài 11 — Index quá nhiều

Service có 25 indexes trên `orders`, QPS writes tăng mạnh. Nêu cách đo index usage, query latency và quyết định indexes nào có thể bỏ.

### Bài 12 — Pagination

Viết keyset query theo `createdAt DESC, _id DESC` trong tenant, không dùng offset lớn. Tại sao phải có tie-breaker?

### Bài 13 — Cursor replay giữa tenants

Thiết kế cursor đã ký chứa tenant/context. Điều gì xảy ra khi user lấy cursor tenant A rồi chuyển sang B?

### Bài 14 — Upsert

Một API import đơn hàng dùng `updateOne({externalId},...,upsert:true)`. Xác định lỗ hổng và viết lại filter/index đúng.

### Bài 15 — BulkWrite

Batch 500 updates của tenant A có một `UpdateOneModel` chỉ filter `_id`. Tại sao chỉ kiểm tra tổng `matchedCount` chưa đủ để phát hiện rò isolation?

### Bài 16 — $lookup

Customer code `C001` tồn tại ở A và B. Viết `$lookup` pipeline có match cả tenantId và customerCode.

### Bài 17 — $unionWith

Một dashboard union orders và supportTickets. Viết tenant filter cho cả main pipeline và union pipeline.

### Bài 18 — Aggregation sandbox

Client gửi arbitrary pipeline chứa `$lookup`/`$unionWith`. Vì sao việc tự prepend `$match tenantId` không đủ? Thiết kế allowlisted report API.

### Bài 19 — $merge

Ứng dụng ghi collection `monthlyRevenue`. Thiết kế target identity có tenantId+month+currency để không ghi đè kết quả của tenant khác.

### Bài 20 — Shard key

Một tenant có 200 triệu orders, 10.000 tenants khác rất nhỏ. So sánh shard key `{tenantId:1}` và compound key, nêu skew/targeting/uniqueness trade-offs.

### Bài 21 — Unique index trên sharded collection

Giải thích vì sao không thể tạo unique constraint tùy ý xuyên shards mà không quan tâm shard key. Đề xuất một unique key design được server version mục tiêu hỗ trợ.

### Bài 22 — Database-per-tenant registry

Thiết kế registry mapping tenant ID → cluster/database name. Làm sao tránh client inject tên database hoặc URI riêng?

### Bài 23 — RBAC

Tạo read-only DB identity cho tenant A và thử truy cập database tenant B. Phân biệt server RBAC với HTTP application authorization.

### Bài 24 — Read-only view

Đánh giá khi nào một MongoDB view có thể giúp giới hạn read access, và vì sao views không thay tenant isolation cho writes, cache, search.

### Bài 25 — Spring Data

Trong ứng dụng shared collection, `CrudRepository.findById(id)` tạo rủi ro gì? Thiết kế custom repository bắt buộc `AuthorizedTenant`.

### Bài 26 — Cache

Hai tenants dùng cùng orderNumber `PO-001`. Viết cache key và test cho việc chuyển tenant nhanh trong UI.

### Bài 27 — Search

Ứng dụng dùng Atlas Search. Thiết kế query filter tenant bên trong compound search nếu index/operator hỗ trợ; giải thích vì sao chỉ filter ở UI là sai.

### Bài 28 — Change streams

Consumer xử lý delete event nhưng `fullDocument` không xuất hiện. Làm sao routing event về đúng tenant mà không đoán?

### Bài 29 — Transaction

Tạo order và trừ inventory trong transaction. Tại sao transaction commit thành công không chứng minh code đã tác động đúng tenant?

### Bài 30 — Tenant provisioning

Worker crash sau khi tạo database/indexes nhưng chưa đánh dấu tenant ACTIVE. Thiết kế provisioning idempotent có states và retry.

### Bài 31 — Tenant migration

Chuyển big-mart từ shared sang dedicated cluster khi traffic còn ghi. Thiết kế backfill/CDC/routingVersion/cutover/rollback.

### Bài 32 — Restore

Tenant A bị xóa nhầm đơn hàng, tenants B/C vẫn hoạt động. Vì sao không restore toàn shared database đè lên production? Thiết kế scoped restore.

### Bài 33 — Deletion

Tenant yêu cầu xóa tài khoản. Lập inventory MongoDB, object storage, cache, search, exports, backups và legal holds.

### Bài 34 — Noisy neighbor

Một tenant tạo 500 aggregations/giây. Thiết kế per-tenant concurrency caps, global resource budget, query deadline, alerts.

### Bài 35 — CSFLE

Tenant enterprise yêu cầu riêng DEK. Mô tả key management/rotation và vì sao encryption không thể thay application authorization.

### Bài 36 — Cardinality

Hệ thống có 100.000 tenants. Nếu Prometheus histograms gắn tenantId, route, outcome, method, sẽ gặp vấn đề gì? Đề xuất metrics tổng hợp và tracing khác.

### Bài 37 — Negative integration test

Dùng Testcontainers tạo orders tenant A/B với ID và business keys đan xen. Viết tests khẳng định B không read/update/delete A và không join customer A sai scope.

### Bài 38 — Incident response

Sau một deploy, logs cho thấy 10 requests thiếu tenant filter. Hãy xác định phạm vi ảnh hưởng, bước containment, audit, data exposure review và regression tests.

### Bài 39 — Tenant tier capacity

Một service có 100 app pods, MongoClient pool max 100/server. Ước tính upper bound pooled connections tới server đó và thảo luận cách thay đổi nếu dùng 50 MongoClients riêng/instance.

### Bài 40 — Capstone

Thiết kế kiến trúc MongoDB cho một SaaS B2B gồm:

1. 50.000 tenants miễn phí, 500 tenants thương mại và 20 tenants enterprise.
2. Một tenant lớn chiếm 60% traffic.
3. Unique order number theo tenant.
4. List/pagination recent orders và full-text search.
5. Customer lookup và monthly revenue reports.
6. Role Owner/Editor/Viewer và support break-glass.
7. Multi-region/residency constraints.
8. Onboarding/offboarding, tenant backup/restore.
9. Online migration từ shared sang dedicated.
10. SLO, noisy-neighbor rate limits, security tests và audit.

Trình bày sơ đồ routing/storage, indexes, access policies, query examples, migration/rollback protocol và test matrix chứng minh tenant isolation.

## 62. Blueprint kiến trúc SaaS MongoDB

Một ví dụ tổng hợp:

```text
  Web / Mobile / API clients
               |
               v
     Identity & Authentication
               |
               v
 Tenant Membership / Permissions
               |
               v
        AuthorizedTenant
               |
               v
         Application API
               |
          Tenant Router
               |
      +--------+-----------+
      |                    |
      v                    v
Shared deployment     Dedicated deployments
  saas.orders          tenant_X.orders
  saas.customers       tenant_X.customers
  saas.events          tenant_X.events
      |                    |
      +--------+-----------+
               |
          CDC / Outbox
               |
      +--------+-----------+
      |        |           |
      v        v           v
    Cache    Search     Analytics
      |        |           |
      +--------+-----------+
               |
       Tenant-aware access
               |
               v
        User-scoped response
```

### 62.1. Boundary ở mỗi lớp

| Lớp | Invariant |
|---|---|
| Identity | Caller được xác thực |
| Membership | Caller được cấp quyền tenant/action |
| Router | Trusted tenant maps tới storage đúng |
| MongoDB shared | Mọi document read/write có tenant scope |
| MongoDB dedicated | Credential/database scope đúng tenant |
| Index | Unique keys/query plans phù hợp scope |
| Search | Query có tenant filter và index support |
| Cache | Key và visibility policy có tenant |
| Event bus | Event envelope/routing/consumer được authorize |
| Object storage | File access qua authorized metadata |
| Observability | Metadata đủ audit, không lộ secrets |
| Backup/restore | Scoped recovery, không tác động tenants khác |

### 62.2. Quy tắc thiết kế quan trọng nhất

**Không cho rằng tenant boundary tồn tại nếu chỉ một tầng đã thêm tenantId.** Authorization phải được đảm bảo nhất quán từ request cho đến MongoDB và mọi data sinks.

## 63. Checklist trước production

### 63.1. Chọn mô hình

1. Có mô tả lý do chọn shared/database/cluster/hybrid.
2. Có dự báo tenants count, p95/p99 tenant size và QPS.
3. Có ngưỡng chuyển tenant lớn sang dedicated storage.
4. Đã đánh giá noisy-neighbor, backup/restore và data residency.
5. Đã thống nhất tenant registry là source of routing truth.

### 63.2. Data model

1. Mọi tenant-owned document có `tenantId` hợp lệ.
2. `tenantId` không được sửa qua public update.
3. Related documents luôn verify tenant ownership.
4. Unique constraints chứa tenant ID khi đúng business scope.
5. Partial indexes/soft delete có schema semantics rõ.
6. Time-based retention và legal hold có policy.

### 63.3. Authorization

1. Tenant context được tạo sau AuthN + membership/role checks.
2. Missing context fail closed.
3. Repository methods dùng tenant-scoped APIs.
4. Không expose raw MongoDB filter/pipeline từ user.
5. CRUD/bulk/upsert/aggregation/search/change streams được audit.
6. Admin cross-tenant access tách path và có audit.
7. MongoDB service identities theo least privilege.
8. Cache/file/export/event paths giữ scope.

### 63.4. Index và scale

1. Có index theo top query shapes.
2. `explain` được kiểm tra trên data representative.
3. Không có quá nhiều indexes dư thừa.
4. Shard key có phân tích hotspot/tenant skew.
5. Unique sharded indexes thỏa server constraints.
6. Có pool/concurrency/quota metrics.
7. Có kế hoạch scale tenant lớn.

### 63.5. Vận hành

1. Tenant provisioning idempotent.
2. Migration có dual-write/CDC/checkpoint/verification.
3. Tenant move có routing version/fencing.
4. Restore từng tenant đã được thử.
5. Offboarding bao phủ data sinks và retention.
6. Logs/metrics đã redact, kiểm soát cardinality.
7. Security incidents có runbook.
8. Có alert và ownership trực on-call.

### 63.6. Kiểm thử

1. Có negative tests A/B ở API/repository layer.
2. Có tests update/delete không làm đổi dữ liệu tenant khác.
3. Có tests aggregation `$lookup`/`$unionWith`.
4. Có tests cache/search/exports/file download.
5. Có tests admin path permission/audit.
6. Có tests tenant switch/async propagation.
7. Có tests DB roles khi dùng DB-per-tenant.
8. Có tests migration/cutover/rollback.

## 64. Tổng kết

Một ứng dụng MongoDB nhiều tenant cần chọn **đúng mô hình cô lập** theo tải, quy định và chi phí. Shared collection giúp phục vụ rất nhiều tenants trên một schema/index chung, nhưng đòi application tenant scoping nghiêm ngặt. Database/collection per tenant tăng linh hoạt quản lý namespace và có thể dùng RBAC ở mức resource, nhưng không tự cô lập CPU/IO của cluster. Dedicated cluster mạnh hơn về vận hành và blast radius, đổi lại cost/complexity cao hơn.

**Dữ liệu phải có identity và quyền đúng.** `tenantId` cần là một invariant bất biến do backend kiểm soát, không phải input client tùy ý. MongoDB RBAC không tự cung cấp document-level authorization trong shared collection. Mọi `find`, `update`, `delete`, `bulkWrite`, `aggregate`, `$lookup`, `$unionWith`, search, cache, event consumer và file download đều cần boundary phù hợp.

**Index phải đồng hành với access patterns.** Những compound keys như `{tenantId:1,status:1,createdAt:-1}` hoặc `{tenantId:1,orderNumber:1}` có thể quan trọng, nhưng phải đo `explain`, nhận thức index maintenance và điều kiện unique indexes trên sharded collections. “Có index” không đồng nghĩa “đã cô lập dữ liệu”.

**Vận hành cũng là multi-tenancy.** Provisioning, dynamic routing, online migration, backup/restore từng tenant, data deletion, search/cache cleanup, encryption key selection và quota/noisy-neighbor controls đều là một phần của thiết kế. Cross-tenant data leak có thể xảy ra ngoài MongoDB dù database query gốc đã đúng.

Một thiết kế đáng tin cậy phải có **security regression tests xác minh tenant B không thể nhìn hoặc thay đổi dữ liệu tenant A**, có observability và runbook để phát hiện/sửa lỗi, đồng thời giữ đường mở rộng từ shared sang dedicated khi khách hàng lớn lên.

## 65. Tài liệu tham khảo

- [MongoDB — Building with Patterns: Multi-Tenant Applications](https://www.mongodb.com/docs/atlas/build-multi-tenant-arch/): các lựa chọn multi-tenant architecture trên Atlas.
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/): resource privileges và role semantics.
- [MongoDB Manual — Create a User](https://www.mongodb.com/docs/manual/reference/method/db.createUser/): users và database roles.
- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/): least privilege, TLS, security controls.
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/): index strategies và costs.
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/): key order/prefix.
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): uniqueness semantics.
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): partialFilterExpression và query applicability.
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/): locale comparison/index interactions.
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/): expiration behavior.
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/): shards, mongos và shard keys.
- [MongoDB Manual — Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/): cardinality, frequency, monotonicity.
- [MongoDB Manual — Unique Indexes and Sharded Collections](https://www.mongodb.com/docs/manual/core/index-unique/#sharded-clusters-and-unique-indexes): shard key prefix rules.
- [MongoDB Manual — Aggregation $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): joins và pipeline syntax.
- [MongoDB Manual — Aggregation $unionWith](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unionWith/): multiple collections.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): event streams, deletes và resume tokens.
- [MongoDB Manual — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/): encryption/key management.
- [MongoDB Manual — Queryable Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/): query capabilities trên encrypted fields.
- [MongoDB Java Sync Driver — Read and Write Data](https://www.mongodb.com/docs/drivers/java/sync/current/crud/): CRUD, filters, updates và aggregation.
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/): MongoClient/pool lifecycle.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): MongoTemplate, repositories và mapping.
- [Testcontainers Java — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): integration testing MongoDB với Testcontainers.






