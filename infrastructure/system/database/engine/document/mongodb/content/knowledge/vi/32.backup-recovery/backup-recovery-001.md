# Xác định RPO, RTO và phạm vi dữ liệu cần khôi phục trong MongoDB

## 1. Mục tiêu bài học

Một bản sao lưu thành công không tự bảo đảm hệ thống sẽ phục hồi đúng hạn. MongoDB có thể chứa snapshot còn nguyên nhưng quá cũ, còn thiếu dữ liệu của các collection liên quan, hoặc chưa có các khóa mã hóa để giải mã. Một thao tác khôi phục hoàn tất cũng chưa đồng nghĩa ứng dụng đã có thể nhận đơn hàng, đối soát thanh toán và trả kết quả cho người dùng.

Bài thuộc **Database Engine Document MongoDB → Sao lưu và phục hồi → Xác định RPO, RTO và phạm vi dữ liệu cần khôi phục**. Trọng tâm là xác định **mất dữ liệu bao nhiêu là chấp nhận được**, **được phép mất bao lâu để phục hồi**, và **phải phục hồi những dữ liệu cùng quan hệ nghiệp vụ nào**.

Sau bài này, người học có thể:

- Giải thích RPO và RTO, phân biệt với backup frequency, backup retention, PITR window, availability và actual recovery time.
- Tính RPO/RTO bằng timeline thực tế thay vì chỉ dựa vào việc một backup job đã thành công.
- Đặt mục tiêu khác nhau cho orders, payments, inventory, customer profile, catalog, analytics và cache.
- Chọn phạm vi document, collection, database, tenant, cluster, region và nhóm dữ liệu phải nhất quán.
- Phân biệt replica set failover với phục hồi logical corruption.
- Đánh giá Atlas scheduled snapshots/Continuous Cloud Backup, `mongodump/mongorestore`, filesystem snapshots và phương án dùng event log.
- Nhận diện những giới hạn của backup trên replica set/sharded cluster và selected collection restore.
- Xây runbook cho xóa nhầm, restore cluster, mất region, lỗi ứng dụng, ransomware và thời gian phát hiện muộn.
- Kiểm tra consistency với GridFS, Search indexes, change streams, outbox, payment provider và các hệ thống ngoài MongoDB.
- Đo actual RPO/RTO trong restore drill và chứng minh phương án được chọn đáp ứng yêu cầu nghiệp vụ.

> **Điểm quan trọng nhất:** RPO/RTO là **mục tiêu kinh doanh cần kiểm chứng**, không phải tính năng tự động xuất hiện sau khi bật replica set, Cloud Backup hoặc một lịch chạy `mongodump`.

---

## 2. Ví dụ kinh doanh: một lệnh xóa nhầm orders

Giả sử ứng dụng có các collections:

```text
commerce
  orders
  payments
  inventoryReservations
  shipments
  outboxEvents
  customers
  products
```

Một script thao tác sai:

```javascript
db.orders.deleteMany({
  createdAt: {
    $gte: ISODate("2026-11-14T00:00:00Z")
  }
});
```

Script xóa nhiều đơn hợp lệ. Replica set vẫn hoạt động, vì lệnh được coi là một thao tác ghi hợp lệ và được replicate. Payment provider có thể đã thu tiền, broker có thể đã publish `OrderPlaced`, dịch vụ kho có thể đã giữ hàng.

Những câu hỏi thực sự cần trả lời:

1. Lệnh sai đầu tiên được thực thi lúc mấy giờ?
2. Có **clean recovery point** trước lệnh sai hay không?
3. Phải phục hồi toàn cluster hay chỉ những orders bị ảnh hưởng?
4. Các giao dịch hợp lệ sau thời điểm xóa nhầm sẽ được giữ thế nào?
5. Sau khi restore orders, payments/inventory/outbox có còn nhất quán?
6. Chức năng checkout phải quay lại trong bao lâu?
7. Ai có quyền phê duyệt rollback dữ liệu đã được khách sử dụng?

Đó là ba chiều **RPO, RTO và recovery scope**, không chỉ là câu hỏi “lệnh restore viết thế nào”.

---

## 3. RPO: mức mất dữ liệu tối đa được phép

**Recovery Point Objective (RPO)** là mức mất dữ liệu tối đa có thể chấp nhận được, thường biểu diễn bằng thời gian từ một mốc sự cố đến điểm dữ liệu nhất quán gần nhất có thể khôi phục.

Ví dụ doanh nghiệp chọn:

```text
RPO(orders) = 5 phút
```

Một sự cố xảy ra lúc 14:00:00; điểm khôi phục gần nhất **dùng được** là 13:58:30.

\[
\text{Actual RPO gap}
=T_{\text{incident}}-T_{\text{last usable recovery point}}
\]

\[
14{:}00{:}00-13{:}58{:}30
=90\ \text{giây}
\]

Trong điều kiện tất cả thay đổi sau điểm khôi phục được coi là tổn thất tiềm năng, gap thực tế là **1 phút 30 giây**, nằm trong RPO 5 phút.

### 3.1. RPO không phải backup frequency

Nếu cứ 6 giờ mới chụp một snapshot, không có PITR và job gần nhất thành công lúc 12:00, sự cố lúc 17:59 có thể buộc phục hồi về 12:00 — gần **6 giờ thay đổi** không có trong bản restore.

Backup frequency 6 giờ không đảm bảo RPO=6 giờ trong mọi trường hợp vì:

- Có job thất bại.
- Snapshot chưa hoàn tất/copy đến storage an toàn.
- Snapshot không thể restore.
- Thiếu KMS/decryption key.
- Backup có lỗi consistency.
- Corruption bắt đầu trước snapshot gần nhất.
- Mất vùng hạ tầng chứa cả source và backup.

Ngược lại, nếu có Continuous Cloud Backup/PITR và lịch sử cần thiết, có thể chọn điểm nằm giữa hai snapshots.

### 3.2. RPO=0 có nghĩa gì?

RPO=0 là mục tiêu không mất write hợp lệ đã được xác nhận trong failure scenarios được định nghĩa. Đây là mục tiêu rất nghiêm ngặt; không được hứa RPO=0 chỉ vì có:

- Ba replica set nodes.
- `writeConcern:"majority"`.
- Secondary ở region khác.
- Continuous backup được bật.

Cần tính durability, consistency, failure domain, log capture, retention, external system state và quy trình khôi phục.

### 3.3. RPO kỹ thuật khác tổn thất nghiệp vụ cuối cùng

Nếu MongoDB rollback 2 phút nhưng payment provider còn lưu tất cả transaction IDs, ta có thể **tái dựng** một phần trạng thái đã mất bằng reconciliation. Tuy nhiên RPO kỹ thuật của bản restore vẫn là 2 phút; tổn thất nghiệp vụ sau phục hồi có thể thấp hơn nếu reconstruction thành công.

### 3.4. Phải xác định mốc sự cố phù hợp

Trong mất cluster lúc 14:00, mốc sự cố thường rõ. Nhưng với **logical corruption phát hiện muộn**, điểm an toàn phải nằm **trước thao tác xấu đầu tiên**, có thể cách thời điểm phát hiện nhiều giờ. Không tự lấy “5 phút trước alert” làm điểm phục hồi.

---

## 4. RTO: thời gian tối đa để dịch vụ hoạt động trở lại

**Recovery Time Objective (RTO)** là thời gian tối đa cho phép từ mốc bắt đầu sự cố đã quy định tới khi chức năng của hệ thống **đạt trạng thái sẵn sàng được định nghĩa**.

Ví dụ:

```text
RTO(checkout) = 30 phút
```

Timeline:

```text
14:00  Sự cố bắt đầu
14:04  Alert được nhận và xác nhận
14:10  Incident commander chọn recovery plan
14:12  Bắt đầu restore
14:31  MongoDB restore job hoàn tất
14:36  Indexes, network, secrets sẵn sàng
14:40  Business validations hoàn tất
14:43  API checkout mở traffic và xử lý thành công
```

**Actual recovery time = 43 phút**, không đạt RTO 30 phút.

### 4.1. Vì sao không lấy 19 phút restore làm RTO?

Từ 14:12 đến 14:31 chỉ là **thời gian phục hồi database bytes**. Khách chưa mua hàng được vì phải kiểm tra relationships, indexes và ứng dụng.

### 4.2. Thành phần của RTO

| Giai đoạn | Việc cần làm |
|---|---|
| Detect | Alert, xác định outage/corruption |
| Decide | Chọn failover, restore hay selective repair |
| Approve | Chấp thuận điểm phục hồi và data loss |
| Provision | Tạo target cluster/storage/network |
| Restore | Nạp snapshot/logs hoặc restore collection |
| Rebuild | Indexes, Search/Vector Search, caches |
| Validate | Kiểm tra dữ liệu và business invariants |
| Cutover | DNS/connection strings/traffic routing |
| Reconcile | Payments, broker, outbox, external effects |
| Ready | Chức năng đạt tiêu chí nghiệp vụ/SLO |

### 4.3. RTO phải định nghĩa rõ “ready”

“MongoDB trả `ping` thành công” chưa đủ. Với checkout, phải có thể:

- Tạo đơn hàng và giữ inventory đúng.
- Không double-charge.
- Xác thực khách hàng.
- Không gửi lại side effects ngoài ý muốn.
- Đạt ngưỡng error rate/latency.
- Xử lý các business constraints tối thiểu.

Có thể đặt **hai RTO**:

```text
RTO critical checkout: 30 phút
RTO all services:      4 giờ
```

Catalog read-only có thể phục hồi trước analytics/reports, nhưng không được gọi là **full recovery** khi các chức năng yêu cầu vẫn chưa hoạt động.

---

## 5. Phân biệt các chỉ số thường nhầm

| Khái niệm | Câu hỏi | Đơn vị/ví dụ |
|---|---|---|
| RPO | Tối đa mất bao nhiêu dữ liệu? | 5 phút |
| RTO | Tối đa mất bao lâu để phục vụ lại? | 30 phút |
| Actual RPO | Data gap thực tế sau recovery? | 90 giây |
| Actual recovery time/RTA | Thời gian thực tế đến ready? | 43 phút |
| Snapshot frequency | Chụp backup bao lâu một lần? | 6 giờ |
| Backup retention | Giữ các bản sao bao lâu? | 30 ngày |
| PITR window | Có thể chọn điểm khôi phục trong khoảng nào? | 7 ngày |
| Availability | Uptime theo SLO? | 99,9% |
| Integrity | Restore xong dữ liệu đúng chưa? | Không thiếu payment |

### 5.1. RPO thấp, RTO cao

Snapshot + PITR giúp chọn điểm gần sự cố, nhưng cluster lớn có thể mất nhiều giờ để restore và rebuild indexes.

### 5.2. RPO cao, RTO thấp

Snapshot mỗi 24 giờ có thể restore rất nhanh, nhưng mất nhiều thay đổi đã ghi sau snapshot.

### 5.3. Không có phương án “miễn phí và tốt nhất mọi mặt”

RPO thấp thường cần continuous backup/log retention, storage, monitoring. RTO thấp thường đòi recovery capacity sẵn, automation, mạng nhanh, người trực, diễn tập thường xuyên.

---

## 6. Phân loại dữ liệu theo mức quan trọng

Một ứng dụng có thể có ma trận giả định:

| Domain | RPO ví dụ | RTO ví dụ | Vì sao |
|---|---:|---:|---|
| Orders | 5 phút | 30 phút | Doanh thu/fulfillment |
| Payments | Gần 0 theo policy | 30 phút | Đối soát tiền |
| Inventory reservations | 5 phút | 30 phút | Tránh oversell |
| Customer account | 15 phút | 2 giờ | Quyền/trạng thái tài khoản |
| Product catalog | 1 giờ | 4 giờ | Có thể import từ CMS/ERP |
| Reviews/comments | 15 phút | 4 giờ | Nội dung người dùng |
| Analytics projection | 24 giờ | 8 giờ | Recompute từ source |
| Cache/search index | Rebuild được | 4 giờ | Không cần giữ từng byte index |

**Đây là số minh họa**, không phải cam kết MongoDB. Business owner phải xác nhận dữ liệu nào có thể mất/tái dựng, mức gián đoạn có thể chấp nhận và trách nhiệm pháp lý.

### 6.1. Câu hỏi BIA (Business Impact Analysis)

- Mất 5 phút orders làm mất bao nhiêu doanh thu?
- Có giao dịch tiền nào không được phép mất bản ghi audit?
- Upstream/provider có thể replay những thay đổi nào?
- Chức năng nào cần mở lại đầu tiên?
- Có thể chấp nhận read-only mode không?
- Mất nội dung người dùng có hậu quả pháp lý không?
- Ai phê duyệt data rollback hoặc compensation?

### 6.2. Recovery classification theo tier

Có thể chia:

- Tier 0: critical transactional state.
- Tier 1: tài khoản/catalog/operational data.
- Tier 2: reporting/search projections.
- Tier 3: temporary/cache data.

Tier chỉ có ý nghĩa khi đi kèm **RPO/RTO và tiêu chí validation** được duyệt.

---

## 7. Phạm vi phục hồi là quyết định nhiều chiều

Một yêu cầu “restore MongoDB” chưa đủ. Cần ghi:

| Chiều | Những khả năng |
|---|---|
| Độ hạt | Field/document, collection, database, tenant, cluster |
| Thời gian | Snapshot, PITR point, trước bad write |
| Hạ tầng | Cluster cũ/mới, project khác, region khác |
| Độ nhất quán | Các collections cùng transaction/bounded context |
| Binary data | GridFS files/chunks, external object storage |
| Downstream | Broker, cache, search index, analytics |
| Security | Users/roles, certificates, KMS, secrets |
| Software | MongoDB version/FCV, app schema, driver |
| Readiness | Read-only, critical functions, full service |

### 7.1. Document-level

Một customer bị cập nhật sai `loyaltyPoints` nhưng address đã được thay đổi hợp lệ sau snapshot. Restore **toàn document cũ** làm mất address update. Nên extract giá trị cần sửa, đối soát events, rồi conditional update đúng field.

### 7.2. Collection-level

Collection `products` bị drop. Restore collection vào namespace mới rồi diff/merge. Cần kiểm tra các collections `categories`, `inventory`, `priceRules` và indexes.

### 7.3. Database-level

Một tenant có database riêng có thể thuận tiện phục hồi riêng, nhưng vẫn có reference ở các shared databases hoặc bên ngoài.

### 7.4. Tenant-level

Trong shared collections dùng `tenantId`, phục hồi một tenant phải tìm tất cả entity relations, assets, payments, background jobs và unique constraints. Không đơn giản bằng chọn một tên collection.

### 7.5. Cluster/region-level

Phải khôi phục cluster data, topology, config và traffic routing. Với region mới còn có private endpoints, DNS, firewall, TLS, KMS keys, IAM và integrations.

---

## 8. Consistency group giữa orders và payments

Ví dụ:

```javascript
// orders
{
  _id: "ORD-1001",
  status: "PAID",
  paymentId: "PAY-1001",
  total: 500000
}

// payments
{
  _id: "PAY-1001",
  orderId: "ORD-1001",
  status: "CAPTURED",
  amount: 500000
}
```

Nếu restore `orders` về trước payment capture nhưng không restore/reconcile `payments`, dữ liệu bất nhất.

Một nhóm nhất quán có thể gồm:

```text
orders
payments
inventoryReservations
shipments
outboxEvents
invoiceMetadata
```

Không nhất thiết restore mọi collection về cùng timestamp nếu có reconciliation tin cậy, nhưng phải **chủ động quyết định**.

### 8.1. External systems

MongoDB backup không tự rollback:

- Payment gateway đã thu tiền.
- Message broker đã gửi sự kiện.
- Email/notification provider đã gửi thông báo.
- Object storage đã lưu hoặc xóa file.
- Shipping service đã tạo vận đơn.

Đây là lý do **reconciliation và idempotency** phải nằm trong recovery scope.

### 8.2. Scope nhỏ đôi khi khó hơn scope lớn

Restore toàn cluster có thể dễ đảm bảo database-level consistency ở cùng mốc nhưng rollback nhiều good writes. Selective repair một field có ít byte hơn nhưng đòi audit, merge và concurrency control.

---

## 9. Replica set không thay thế backup

### 9.1. High availability khác data recovery

Replica set giúp hoạt động khi một node ngừng, thông qua replication/election khi đủ điều kiện.

```text
Primary -> replication -> Secondary A
        -> replication -> Secondary B
```

Nếu primary hỏng nhưng dữ liệu vẫn đúng, failover có thể đủ; **không cần rollback snapshot**.

### 9.2. Xóa nhầm vẫn replicate

```javascript
db.orders.deleteMany({});
```

Lệnh xóa được majority-acknowledged vẫn có thể là thao tác nghiệp vụ sai. Secondary cũng nhận thay đổi, không giữ phiên bản lịch sử để undo chỉ bằng election.

### 9.3. `writeConcern:"majority"` không tạo backup

Majority write concern nói về xác nhận write trong replica set, không tạo bản sao độc lập chống logical corruption hoặc ransomware.

### 9.4. Oplog có cửa sổ hữu hạn

Oplog được dùng cho replication/change streams và không lưu vô hạn. Nếu không có cơ chế backup + lịch sử oplog được quản lý phù hợp, không thể tự “time travel” tới mọi thời điểm.

---

## 10. Phương án sao lưu và khả năng khôi phục

| Phương án | Điểm mạnh | Giới hạn |
|---|---|---|
| Atlas scheduled snapshots | Managed backup và retention | RPO phụ thuộc snapshot point |
| Atlas Continuous Cloud Backup/PITR | Chọn mốc trong restore window | Cần tier/feature và quy trình restore |
| `mongodump/mongorestore` | Logical dump, chọn namespaces | Không tự PITR; restore lớn chậm |
| `mongodump --oplog` | Consistent full replica set dump khi hỗ trợ | Chỉ oplog trong dump window; không arbitrary PITR |
| Filesystem snapshots | Block-level recovery có thể nhanh | Journal/volume/shard consistency |
| Atlas/Ops Manager | Backup automation/policy | Phụ thuộc deployment/edition |
| Event log + snapshots | Replay good business events | Cần ordering/dedup/idempotency |
| Replication | High availability | Không chống bad writes |

Cần đo hiệu quả theo dataset/topology và tools version. Không có một dòng trong bảng tự cam kết RPO=1 phút/RTO=15 phút.

---

## 11. Atlas Cloud Backup và Continuous Cloud Backup

### 11.1. Scheduled snapshots

Atlas Cloud Backup tạo snapshots theo backup policy và retention. Với các cluster tương ứng, người vận hành có thể chọn mốc snapshot để restore.

Theo tài liệu hiện hành, Cloud Backup managed ở phạm vi được mô tả chủ yếu dành cho **Dedicated M10+**; Free không có managed Cloud Backup như Dedicated. Kiểm tra tier và features cụ thể trước khi thiết kế SLA.

### 11.2. Continuous Cloud Backup/PITR

Continuous Cloud Backup kết hợp snapshot và history để có thể chọn **date/time hoặc oplog timestamp** trong restore window. MongoDB Atlas Architecture Center mô tả khả năng đạt RPO thấp tới khoảng **1 phút** trong các điều kiện phù hợp; không hiểu đó là guarantee mọi cluster/incident đều RPO thực tế 1 phút.

### 11.3. Selective database/collection restore

Atlas hỗ trợ phục hồi **selected databases hoặc collections** từ snapshot hoặc Continuous Cloud Backup trong môi trường được hỗ trợ.

**Quan trọng:** Tài liệu Atlas nêu selective restore **không được thiết kế để giảm RTO**, và có thể **lâu hơn full cluster restore**. Đừng suy “ít collection nên chắc nhanh”.

### 11.4. Create as new vs Overwrite existing

- **Create as new:** khôi phục dữ liệu vào namespace mới khi tên trùng, hỗ trợ diff/merge.
- **Overwrite existing:** ghi đè selected namespaces, có thể làm mất writes trên target.

Với sự cố xóa nhầm, ưu tiên restore vào **cluster/namespace cách ly** để kiểm chứng trước.

### 11.5. Giới hạn selective restore

Theo MongoDB docs hiện hành, có các giới hạn với:

- MongoDB Search indexes: selected restore không khôi phục Search indexes, cần rebuild.
- Individual time-series collection restores.
- Một số Queryable Encryption collections.
- Views, NVMe cluster hoặc điều kiện encryption/network đặc thù.
- Disk space và concurrency restore jobs.

Trước khi thao tác, kiểm tra docs cho deployment và phiên bản thực tế.

### 11.6. Full snapshot và Search indexes

Full snapshot có thể khôi phục **Search index definitions**, nhưng dữ liệu của Search index thường cần được search process **initial sync/rebuild**. Thời gian search endpoint hoạt động lại có thể kéo dài sau khi CRUD đã ready.

### 11.7. Restore target

Tài liệu Atlas khuyến cáo ngăn client operations trên target đang restore. Restore vào **cluster mới** rồi cutover thường giúp hạn chế tác động đến production và giữ source cho forensic.

---

## 12. Logical backup bằng `mongodump` và `mongorestore`

### 12.1. Backup một collection trong lab

```bash
mongodump \
  --uri="$SOURCE_MONGODB_URI" \
  --db=shop \
  --collection=products \
  --out=./shop-products-backup
```

Dùng terminal MongoDB Database Tools, không phải mongosh. Nếu writes tiếp tục trong dump, output không tự bảo đảm consistency toàn database.

### 12.2. Restore vào namespace tạm

```bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --nsInclude="shop.products" \
  --nsFrom="shop.products" \
  --nsTo="recovery.products" \
  ./shop-products-backup
```

Các URIs và paths là ví dụ. Phải xác minh source/target/dump thực tế trước khi chạy. Không dùng `--drop` trên production target nếu chưa có phương án phê duyệt, vì nó xóa dữ liệu target collection trước restore.

### 12.3. Khi nào phù hợp?

- Export collection trước migration.
- Restore một namespace vào staging để trích dữ liệu.
- Backup bổ sung dataset nhỏ/vừa.
- Reconciliation và đối chiếu documents.

### 12.4. Khi nào chưa đủ?

Không thể mặc định logical dump nhiều TB sẽ đáp ứng RPO/RTO rất thấp. Restore cần nạp BSON, xây indexes, network/disk resources và validation.

### 12.5. Compatibility

Database Tools và source/target MongoDB Server có các ràng buộc theo major version/FCV. Đừng mặc định có thể restore dump version mới vào server cũ bất kỳ.

---

## 13. `mongodump --oplog` không phải PITR tùy ý

### 13.1. Dùng để làm gì?

Nếu một full replica set dump chạy trong lúc hệ thống vẫn ghi, `--oplog` ghi những oplog operations xảy ra **trong quá trình dump**. Khi restore với `--oplogReplay`, công cụ có thể đưa data về trạng thái nhất quán theo cơ chế được hỗ trợ.

### 13.2. Ví dụ full replica set dump

```bash
mongodump \
  --uri="$SOURCE_REPLICA_SET_URI" \
  --oplog \
  --archive=./replica-set.archive.gz \
  --gzip
```

Restore vào target **cách ly**:

```bash
mongorestore \
  --uri="$TARGET_REPLICA_SET_URI" \
  --archive=./replica-set.archive.gz \
  --gzip \
  --oplogReplay
```

### 13.3. Giới hạn cần nhớ

- `--oplog` dành cho **full dump replica set**; không dùng chung tùy ý với `--db`, `--collection`, `--query`.
- Không dùng cùng phương án full `--oplogReplay` trên sharded cluster.
- `mongodump --oplog` từ `mongos` không trở thành PITR toàn sharded cluster.
- DDL/role changes hoặc FCV/time-series format conversion có thể gây vấn đề theo Database Tools version.
- Atlas Free/Flex có những lựa chọn `mongorestore` không được hỗ trợ, gồm `--oplogReplay` theo tài liệu.

### 13.4. `--oplogReplay` không arbitrary PITR

Công cụ replay oplog entries **đã ghi trong lần dump**, không tự cung cấp lịch sử liên tục để restore đến một timestamp bất kỳ nhiều giờ/ngày sau. PITR thật cần snapshot base và log capture/retention được thiết kế cho mục tiêu đó.

---

## 14. Filesystem snapshots và sharded consistency

### 14.1. Block-level snapshot

Storage snapshot có thể tạo nhanh hơn logical dump nhưng consistency phụ thuộc MongoDB journal, storage volumes, file layout và procedure đúng.

Không copy một số data files của `dbPath` trong lúc MongoDB ghi rồi coi là bản sao nhất quán.

### 14.2. Sharded cluster có nhiều thành phần

```text
mongos
  |---- Shard A replica set
  |---- Shard B replica set
  |---- Shard C replica set
  |---- Config server replica set
```

Backup phải xét các shards và config metadata. Snapshot shard A lúc 13:00, shard B lúc 13:15 có thể không phản ánh trạng thái toàn cục đồng nhất.

### 14.3. Balancer, migrations và distributed transactions

Chunk migrations, resharding và giao dịch xuyên shards khiến backup thủ công phức tạp. Tài liệu MongoDB về self-managed sharded filesystem backup có các bước dừng writes/balancer, lock và snapshot đúng trình tự.

### 14.4. Chọn giải pháp phù hợp

Nếu không đủ năng lực thiết kế snapshot consistency trên sharded deployment, ưu tiên phương án managed backup được MongoDB hỗ trợ hơn là ghép thủ công các dumps không có global recovery point.

### 14.5. Topology compatibility

Restore sharded cluster còn phụ thuộc cấu hình shards/config, target version và shard topology. Kiểm tra giới hạn snapshot restore của Atlas khi target topology thay đổi trước khi đặt RTO.

---

## 15. Corruption phát hiện muộn: chọn clean point

Timeline:

```text
13:55:07 bad script bắt đầu xóa/sửa dữ liệu sai
13:55:20 thêm nhiều bad writes
14:10:00 hệ thống mới phát hiện
```

Nếu chỉ restore về “5 phút trước khi phát hiện” (14:05), dữ liệu vẫn chứa bad writes từ 13:55. Clean point có thể phải ở **13:55:06** hoặc trước đó.

### 15.1. Vì sao chọn điểm cũ có giá?

Trong 15 phút từ 13:55 đến 14:10, các orders/payments khác có thể được ghi hợp lệ. Full-cluster rollback về 13:55 có thể làm mất good writes.

### 15.2. Các chiến lược

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| Full PITR trước bad write | Dễ hiểu về clean database state | Rollback good writes |
| Selective restore collection | Giảm scope | Dễ lệch relationships |
| Restore tạm rồi extract docs | Giữ current data | Merge phức tạp |
| Compensating repair | Giữ nhiều good writes | Script sửa cũng có thể sai |
| Replay good business events | Có thể tái dựng | Cần reliable log và dedup |

### 15.3. Không replay tất cả operations sau điểm sạch

Nếu áp toàn bộ oplog sau clean point, bad delete có thể được thực thi lần nữa. Cần chọn lọc good events và business reconciliation.

### 15.4. Kết quả RPO phải trung thực

Nếu full rollback làm mất 15 phút good writes, không được báo “RPO 1 phút” chỉ vì PITR service về lý thuyết hỗ trợ các điểm cách nhau ngắn. Ghi actual loss/reconstructed events và residual gaps.

---

## 16. Document-level repair mà không mất update hợp lệ

Trước sự cố:

```javascript
{
  _id: "CUS-101",
  loyaltyPoints: 250,
  addressVersion: 3
}
```

Bad script làm `loyaltyPoints:0`, sau đó user đổi địa chỉ thành version 4. Restore toàn document cũ sẽ làm mất address update.

Nên:

1. Restore backup vào namespace tạm.
2. Lấy giá trị loyaltyPoints trước lỗi.
3. Reconcile giao dịch cộng/trừ điểm sau mốc.
4. Chỉ sửa loyaltyPoints theo điều kiện/version.
5. Ghi recovery ticket và audit.

Ví dụ **minh họa, không dùng khi chưa tính chính xác số điểm**:

```javascript
const result = db.customers.updateOne(
  {
    _id: "CUS-101",
    loyaltyPoints: 0
  },
  {
    $set: {
      loyaltyPoints: 250,
      recoveryTicket: "INC-2026-101"
    }
  }
);

print(result.modifiedCount);
```

Đây là lý do **phạm vi một field** đôi khi cần business audit phức tạp hơn restore một collection.

---

## 17. GridFS là một consistency group

GridFS lưu tệp qua:

```text
fs.files  -> metadata
fs.chunks -> binary chunks
```

Nếu chỉ restore `fs.files` mà thiếu chunks, file download hỏng. Nếu chỉ restore chunks mà thiếu metadata, driver không thể tìm nội dung bình thường.

Còn có thể có:

```text
invoiceMetadata
assetVersions
assets.currentFileId
fs.files
fs.chunks
```

Sau restore, pointer `currentFileId` có thể trỏ tới file không tồn tại nếu metadata và bucket được phục hồi ở các thời điểm khác nhau.

### 17.1. Kiểm tra integrity

- Mọi referenced fileId phải tồn tại.
- Chunk sequence/size phải hợp lệ.
- Stream toàn bộ file mẫu và tính SHA-256 nếu có.
- Kiểm tra quyền truy cập, legal hold và retention.
- Không tự xóa orphan chunks quá sớm khi upload có thể đang diễn ra.

### 17.2. Attachments ngoài MongoDB

S3/GCS/Azure Blob có backup/versioning riêng. MongoDB Cloud Backup không tự restore object store về cùng timestamp.

---

## 18. Change streams, outbox và systems bên ngoài

### 18.1. Source rollback, consumer ở mốc tương lai

```text
MongoDB source restored to T1
Consumer checkpoint / broker state still at T2
```

Resume token có thể không còn hợp lệ hoặc projection chứa changes sau T1. Không chỉ restart consumer từ checkpoint T2 rồi mặc định mọi thứ nhất quán.

### 18.2. Recovery plan

- Dừng consumers/workers có thể gây side effects.
- Xác định source-of-truth.
- Bootstrap hoặc rebuild projections theo source đã phục hồi.
- Reconcile broker/outbox event IDs.
- Dùng inbox/dedup tránh double charges/emails.
- Kiểm tra event ordering và gaps.
- Chỉ mở lại processing khi state đã hợp lệ.

### 18.3. Payment provider

Nếu MongoDB rollback order về PENDING nhưng provider đã CAPTURED, cần truy vấn/đối soát transaction ID. Không gửi lại lệnh capture bừa bãi.

### 18.4. Search indexes

Search/Vector Search index có thể phải rebuild/initial sync sau restore. CRUD hoạt động không có nghĩa retrieval/full-text query đã sẵn sàng.

---

## 19. Đo RPO từ metadata recovery point

Ví dụ **backup catalog của ứng dụng**, không phải response chuẩn Atlas:

```json
{
  "backupId": "BK-20261114-1358",
  "sourceCluster": "commerce-prod",
  "type": "pitr-snapshot",
  "lastConsistentPoint": "2026-11-14T13:58:30Z",
  "completedAt": "2026-11-14T14:01:00Z",
  "status": "VERIFIED",
  "restoreTest": "DRILL-20261107"
}
```

`completedAt` là thời gian job hoàn thành, **không phải** timestamp trạng thái dữ liệu. RPO phải dựa vào `lastConsistentPoint` có thể khôi phục và đúng với incident.

### 19.1. Các chỉ số nên có

- Last usable consistent recovery point.
- Age của recovery point.
- PITR window start/end.
- Backup job failures.
- Restore test age.
- Cross-region copy lag.
- Encryption key availability.
- Immutable retention policy.

### 19.2. Không chỉ đếm “backup SUCCESS”

Nếu RPO target 5 phút nhưng latest usable point cách hiện tại 90 phút, phải alert dù job tuần trước thành công.

---

## 20. Phân rã RTO thành time budget

Ví dụ mục tiêu **60 phút**:

| Công đoạn | Budget |
|---|---:|
| Detect và triage | 5 phút |
| Quyết định và phê duyệt | 5 phút |
| Provision target | 8 phút |
| Restore data | 25 phút |
| Index/search warm-up | 7 phút |
| Validation | 5 phút |
| Cutover + smoke tests | 5 phút |
| **Tổng** | **60 phút** |

Nếu restore data lâu 40 phút thay vì 25, cần thay đổi strategy/capacity hoặc chấp nhận target RTO khác; không thể “giấu” thời gian bằng cách báo completed sớm.

### 20.1. Băng thông ví dụ

Với 2 TiB phải truyền qua 1 Gbit/s hiệu dụng:

\[
T \approx \frac{2\times2^{40}\times8}{10^9}
\approx 17\,592\text{ giây}
\]

Tức gần **4,9 giờ** ở mức truyền raw bytes lý tưởng, chưa tính overhead/index/validation. Không thể hứa RTO 30 phút nếu recovery path thực tế bắt buộc copy khối dữ liệu theo cách đó.

### 20.2. Storage snapshot có tối ưu khác

Block-level snapshot/Atlas restore có thể dùng cơ chế khác raw copy, nên không dùng phép tính trên để suy rằng mọi restore 2 TiB mất 4,9 giờ. **Phải benchmark chính recovery path đã chọn**.

### 20.3. Critical path

Một số bước có thể chạy song song (provision target trong khi xác nhận restore point), nhưng RTO được xác định theo elapsed time tới readiness thực tế, không phải tổng “lý thuyết” riêng lẻ.

---

## 21. New recovery cluster hay overwrite target cũ?

### 21.1. Restore ở cluster/namespace mới

```text
Production lỗi
   |
   v
Backup/PITR
   |
   v
Recovery target cách ly
   |
Validation + reconciliation
   |
Traffic cutover
```

Ưu điểm:

- Giữ nguyên source cho forensic.
- Có thể diff dữ liệu và kiểm chứng.
- Giảm rủi ro làm mất good writes.
- Cho phép canary/smoke tests trước cutover.

Đánh đổi: cần storage/compute/network/keys và kế hoạch chuyển traffic.

### 21.2. Restore overwrite

Có thể đơn giản về hạ tầng nhưng có rủi ro xóa good writes ở target, gây partial state nếu job thất bại và khó forensic.

### 21.3. Write fencing

Khi cutover, không được để source và recovery target cùng nhận writes độc lập. Cần maintenance/freeze/routing và một source of truth rõ. Những writes hợp lệ giữa recovery point và cutover phải được **reconcile/replay** theo chính sách.

### 21.4. Failback

Nếu về sau chuyển traffic lại cluster cũ, phải xử lý những writes đã sinh trên target. Không chuyển ngược bằng DNS đơn thuần mà bỏ qua dữ liệu mới.

---

## 22. Ransomware và backup immutability

Một attacker có quyền xóa production và backup cùng tài khoản có thể phá cả hai. Recovery design nên xét:

- Immutable/indelible backup policy phù hợp.
- Separation of duties và least privilege.
- MFA/SSO, audit và break-glass process.
- Cross-region/cross-account copy.
- Encryption/KMS key recovery.
- Clean-room restore.
- Containment compromised accounts trước khi mở traffic.

Nếu dữ liệu bị sửa âm thầm nhiều tuần, PITR window ngắn có thể không còn **clean point**. Retention phải xét **time-to-detection** và legal obligations.

Không restore ứng dụng cùng compromised secrets rồi khiến bad writes tiếp tục lặp lại.

---

## 23. Runbook cho xóa nhầm collection

1. **Declare incident**, ghi affected namespace, mốc lỗi đầu tiên và impact.
2. **Dừng/chặn writes** liên quan theo policy.
3. **Xác định clean recovery point** trước bad operation.
4. **Chọn isolated target/namespace**, tránh overwrite production.
5. **Restore selected data** theo khả năng backup product.
6. **Kiểm tra schema/index/validator và data samples**.
7. **Tìm good writes sau clean point**, không replay bad writes.
8. **Merge có điều kiện**, dùng dry-run/version checks và audit.
9. **Reconcile** related collections, payments và broker.
10. **Smoke tests, business sign-off, cutover**.
11. **Ghi actual RPO/RTO, missing events và postmortem**.

### 23.1. Vì sao cần cân nhắc selective restore latency?

Atlas docs nêu selected database/collection restore không nhằm giảm RTO và có thể lâu hơn full restore. Chọn vì **scope và khả năng giữ good data**, không vì giả định luôn nhanh hơn.

---

## 24. Runbook mất toàn cluster/region

1. Xác định là node failover hay data loss thực.
2. Kích hoạt incident commander và RPO/RTO tier liên quan.
3. Tìm latest usable backup/restore window, xác nhận encryption keys.
4. Kiểm tra target topology, server version/FCV và network.
5. Provision target trong region/project phù hợp.
6. Restore data và giám sát job/disk/capacity.
7. Khôi phục users/roles, secrets, config, indexes/search.
8. Validate business invariants và authorization/tenant isolation.
9. Đưa application critical services vào trạng thái sẵn sàng.
10. Cutover traffic có write fencing.
11. Reconcile payments/outbox/broker/object storage.
12. Ghi actual RPO/RTO, các gaps và failback plan.

Không coi restore job SUCCESS là mọi service đều sẵn sàng. Một cluster mới vẫn có thể thiếu private endpoint, TLS cert hoặc Search index data.

---

## 25. Kiểm tra tính đúng sau khôi phục

### 25.1. Document counts chỉ là bước đầu

```javascript
db.orders.countDocuments();
db.payments.countDocuments();
db.customers.countDocuments();
```

Cùng số document không chứng minh nội dung và relationships đúng.

### 25.2. Đối soát gần mốc sự cố

```javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-14T00:00:00Z")
  }
}).sort({
  createdAt: -1
}).limit(20);
```

Mốc timestamp cần thay theo incident thực tế. Không dùng output count làm kết luận đầy đủ.

### 25.3. Business invariants

- Order PAID phải có payment CAPTURED tương ứng.
- Không double-charge cùng provider transaction ID.
- Inventory reservations không vượt nguồn lực.
- Invoice metadata trỏ file tồn tại.
- Không vi phạm tenant isolation.
- Outbox/inbox event IDs không bị xử lý trùng.
- Dữ liệu bị yêu cầu xóa hợp pháp không được tái xuất bản trái policy.

### 25.4. Ví dụ tìm order thiếu payment document

```javascript
db.orders.aggregate([
  {
    $match: {
      paymentId: { $exists: true }
    }
  },
  {
    $lookup: {
      from: "payments",
      localField: "paymentId",
      foreignField: "_id",
      as: "matchingPayments"
    }
  },
  {
    $match: {
      matchingPayments: { $size: 0 }
    }
  },
  {
    $project: {
      _id: 1,
      paymentId: 1
    }
  },
  {
    $limit: 50
  }
]);
```

Đây chỉ là **một loại kiểm tra**, chưa chứng minh toàn bộ nghiệp vụ đúng. Với dữ liệu lớn, chọn index/sampling/batching để validation không làm cluster vừa restore quá tải.

### 25.5. Index và query readiness

Kiểm tra:

- Unique indexes, partial/TTL indexes, collations.
- MongoDB Search/Vector Search rebuild/initial sync.
- Query plans quan trọng.
- Cache/buffer warm-up.
- Change stream consumer projections.
- External dependency health.

---

## 26. Dashboard RPO/RTO và cảnh báo

| Metric | Mục đích |
|---|---|
| `backup_last_success_timestamp` | Backup job gần nhất |
| `backup_last_usable_recovery_point` | Điểm restore dùng được |
| `backup_lag_seconds` | Mức cũ của recovery point |
| `backup_job_failures_total` | Backup lỗi |
| `backup_restore_validation_failures_total` | Lỗi integrity |
| `pitr_window_seconds` | Cửa sổ restore |
| `cross_region_copy_lag_seconds` | Backup copy DR |
| `restore_job_duration_seconds` | Thời gian phục hồi data |
| `restore_validation_duration_seconds` | Thời gian validation |
| `cutover_duration_seconds` | Chuyển traffic |
| `drill_actual_rpo_seconds` | RPO trong diễn tập |
| `drill_actual_rto_seconds` | RTO trong diễn tập |
| `unreconciled_business_events` | Good events chưa khôi phục |
| `search_rebuild_seconds` | Tìm kiếm quay lại |

Alert khi last usable recovery point quá cũ so với business RPO **dù backup job trước đó báo SUCCESS**.

---

## 27. Buổi diễn tập phục hồi (restore drill)

Ví dụ timeline diễn tập:

```text
Tincident       = 14:00
Talert          = 14:03
Tdecision       = 14:08
TrestoreStart   = 14:12
TrestoreEnd     = 14:28
TvalidationDone = 14:37
TserviceReady   = 14:43
```

Actual RTO là 43 phút. Actual RPO tính từ **clean recovery point được phục hồi** tới mốc sự cố, kết hợp đánh giá dữ liệu hợp lệ đã replay/reconcile.

### 27.1. Nội dung drill

- Restore một collection vào namespace tạm.
- PITR trước một bad write mô phỏng.
- Full cluster restore sang new target.
- Cross-region recovery.
- GridFS files/chunks và app references.
- Payment/order reconciliation.
- Search index rebuilding.
- KMS key access.
- Change stream projection rebuild.

### 27.2. Diễn tập phải an toàn

Không chạy restore destructive vào production chỉ để đo. Dùng isolated target, bảo vệ dữ liệu nhạy cảm và chỉ thực hiện thao tác được cho phép.

### 27.3. Đo trên dữ liệu gần production

Restore dataset 10 GiB trong lab năm ngoái không chứng minh RTO với 5 TiB production năm nay. Khi volume, topology, sharding hoặc search indexes đổi, cần đo lại.

---

## 28. Vai trò trong incident

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander | Chỉ huy, quyết định ưu tiên, truyền thông |
| DBA/SRE | Backup, restore, topology, monitoring |
| Application owner | API readiness, writes/cutover |
| Business owner | Chấp thuận recovery point và data-loss trade-off |
| Security | Compromise containment, secrets/KMS, forensic |
| Finance/Operations | Đối soát payments/logistics |
| Compliance/Legal | Retention, legal hold, privacy |

Các quyết định có thể xóa good writes (ví dụ overwrite production, rollback nhiều giờ) cần được duyệt theo runbook. Quyền break-glass/backup recovery phải được chuẩn bị trước, nhưng vẫn có audit và least privilege.

---

## 29. Kịch bản tổng hợp: lỗi ứng dụng rồi mất region

```text
09:00 bad deployment làm sai status 20.000 orders
09:15 lỗi được phát hiện
11:00 region chứa MongoDB gặp outage
```

### 29.1. Restore latest 10:59

Giúp khôi phục region loss nhưng status orders vẫn sai từ 09:00.

### 29.2. Rollback toàn cluster về 08:59

Có thể loại bad writes nhưng làm mất good writes từ 09:00–11:00 trên những domains khác.

### 29.3. Phương án kết hợp

1. Restore cluster ở region mới tới điểm mới nhất đáng tin cho hạ tầng.
2. Tìm các orders bị corruption.
3. Dùng snapshot/PITR trước 09:00 để lấy clean values.
4. Reconstruct legitimate changes sau 09:00 từ audit/event/provider.
5. Repair chọn lọc có CAS.
6. Reconcile payments/inventory/outbox/shipments.
7. Ghi actual RPO/RTO từng domain và residual gaps.

Một recovery plan duy nhất không luôn tối ưu cả ba mục tiêu: **mất ít dữ liệu, phục vụ lại nhanh, phạm vi sửa nhỏ**.

---

## 30. Sai lầm thường gặp

1. **“Replica set có backup rồi.”** Nó replicate logical errors.
2. **“Majority write bảo đảm RPO=0 mọi trường hợp.”** Không.
3. **“Snapshot mỗi giờ nghĩa là RPO chính xác một giờ.”** Cần usable recovery point.
4. **“Backup SUCCESS đồng nghĩa restore được.”** Phải thử.
5. **“RTO là thời gian mongorestore.”** RTO đến service ready.
6. **“Collection restore luôn nhanh hơn cluster restore.”** Atlas docs không khẳng định như vậy.
7. **“Restore một collection không ảnh hưởng collection khác.”** Relationships có thể lệch.
8. **“Replay mọi operations sau corruption.”** Có thể tái tạo bad writes.
9. **“mongodump --oplog là PITR tùy ý.”** Không.
10. **“mongodump --oplog dùng được cho toàn sharded cluster.”** Không theo cách replica set dump.
11. **“Mọi Atlas tiers đều có PITR giống nhau.”** Phải kiểm tra.
12. **“Search definitions khôi phục tức index data ready.”** Có thể cần rebuild.
13. **“GridFS chỉ cần fs.files.”** Thiếu chunks.
14. **“Chỉ restore data, không cần IAM/KMS/network.”** Sai.
15. **“Overwrite target không làm mất data mới.”** Có thể làm mất.
16. **“Oplog giữ vô hạn.”** Không.
17. **“Snapshot một shard là đủ.”** Không.
18. **“Backup mã hóa không cần decryption key.”** Sai.
19. **“MongoDB rollback cũng rollback payment provider.”** Không.
20. **“Document count đủ xác minh.”** Cần invariants.
21. **“Chọn mốc restore không cần business approval.”** Sai.
22. **“Một RPO cho mọi domain.”** Không phù hợp đa số hệ thống.
23. **“Bản dump nào cũng restore được vào version cũ.”** Kiểm tra FCV/version.
24. **“Index warm-up không tính RTO.”** Có thể ảnh hưởng readiness.
25. **“Drill một lần là đủ.”** Dữ liệu và hạ tầng thay đổi liên tục.

---

## 31. Checklist xây DR policy

### 31.1. Business

- [ ] Liệt kê critical domains/services.
- [ ] Xác định mức mất data tối đa từng domain.
- [ ] RTO critical và full-service.
- [ ] Nguồn dữ liệu có thể tái dựng.
- [ ] Retention/legal/privacy requirements.
- [ ] Business owner phê duyệt RPO/RTO.

### 31.2. Recovery scope

- [ ] Document/collection/database/tenant/cluster/region.
- [ ] Orders/payments/inventory/outbox consistency groups.
- [ ] GridFS files/chunks + app metadata.
- [ ] Search indexes/cache/projections.
- [ ] Broker/checkpoints/external services.
- [ ] Version/FCV/sharded topology.
- [ ] IAM/TLS/KMS/DNS/private endpoints.

### 31.3. Backup

- [ ] Snapshot schedule và retention.
- [ ] PITR window nếu cần.
- [ ] Last usable consistent point.
- [ ] Restore verification cadence.
- [ ] Immutability và offsite policy.
- [ ] Key availability.
- [ ] Restore tools compatibility.
- [ ] Backup failure alerts.

### 31.4. Execution

- [ ] Detect/decision budget.
- [ ] Provision automation.
- [ ] Measured restore throughput.
- [ ] Search/index warm-up.
- [ ] Business validation.
- [ ] Traffic cutover/write fencing.
- [ ] Failback/rollback plan.
- [ ] Actual RPO/RTO từ drill.

---

## 32. Bài tập thực hành

### Bài tập 1 — Tính RPO

Sự cố lúc 14:00, latest usable consistent point lúc 13:56:40. Tính actual RPO gap và so với target 5 phút.

### Bài tập 2 — Tính RTO

Outage 09:00, database restore xong 09:22, indexes ready 09:30, checkout mở traffic 09:41. RTO target 30 phút có đạt không?

### Bài tập 3 — Worst-case snapshot gap

Snapshot mỗi 4 giờ, không có PITR. Xác định worst-case loss window và tác động của một job backup thất bại.

### Bài tập 4 — Matrix theo nghiệp vụ

Đề xuất RPO/RTO cho orders, payments, catalog và analytics, giải thích bằng business impact.

### Bài tập 5 — Replica set

Vì sao election không undo được `deleteMany({})` đã replicate?

### Bài tập 6 — Clean PITR point

Bad writes bắt đầu 10:10:15, phát hiện 10:30. Tại sao 10:25 không phải clean point?

### Bài tập 7 — Selected restore

Thiết kế runbook restore `products` sang namespace tạm, diff, merge và validation.

### Bài tập 8 — Logical dump

Tạo `mongodump` của một collection lab và `mongorestore` trên target lab. Giải thích consistency limitations.

### Bài tập 9 — `--oplog`

Viết full replica set dump với `--oplog`, restore với `--oplogReplay`; nêu giới hạn sharded clusters và arbitrary PITR.

### Bài tập 10 — Sharding

Vẽ 3 shards + config server; giải thích vì sao snapshot từng shard không cùng mốc có thể sai.

### Bài tập 11 — GridFS

Lập scope restore invoice metadata + `fs.files` + `fs.chunks` + asset references.

### Bài tập 12 — Search index

Giải thích tại sao CRUD phục hồi nhưng Vector Search chưa sẵn sàng.

### Bài tập 13 — Network time

Tính lower bound truyền 2 TiB qua 1 Gbit/s và nêu yếu tố khiến snapshot-based restore khác raw copy.

### Bài tập 14 — Payment reconciliation

MongoDB order rollback về PENDING, provider vẫn CAPTURED. Thiết kế không double-charge.

### Bài tập 15 — Drill

Thiết kế restore drill 60 phút, ghi timeline, actual RPO/RTO và checks.

### Bài tập 16 — Ransomware

Đề xuất immutable backup, IAM isolation, KMS key recovery và clean-room restore.

### Bài tập 17 — Một field sai

Restore loyaltyPoints cũ nhưng giữ address update mới, có conditional version check.

### Bài tập 18 — Change stream recovery

MongoDB source về T1, consumer checkpoint còn T2. Làm sao bootstrap/reconcile mà không bỏ hoặc double-process events?

### Bài tập 19 — Tenant recovery

Tenant-a dùng shared collections; xác định những relationships cần phục hồi riêng và risk của namespace-level restore.

### Bài tập 20 — RTO khi scale

So sánh restore 10 GiB lab với 5 TiB production, phân loại bottlenecks và phương pháp benchmark.

---

## 33. Câu hỏi ôn tập

1. RPO là gì?
2. RTO là gì?
3. RPO khác backup frequency ở đâu?
4. RTO khác restore command duration ở đâu?
5. Actual recovery time/RTA là gì?
6. Retention và PITR window khác nhau thế nào?
7. Vì sao RPO=0 khó bảo đảm?
8. Vì sao RPO của payments có thể khác analytics?
9. Backup SUCCESS có chứng minh restore được không?
10. Replica set có thay backup không?
11. Majority write có chống logical corruption không?
12. Oplog có giữ vô hạn không?
13. Atlas Continuous Cloud Backup bổ sung khả năng nào?
14. Mọi Atlas tiers có cùng Cloud Backup không?
15. Atlas selective restore có mặc định nhanh hơn full restore không?
16. Create-as-new khác overwrite thế nào?
17. `mongodump` là logical hay physical backup?
18. `--oplogReplay` có restore bất kỳ timestamp lâu sau dump không?
19. Sharded backup cần những thành phần nào?
20. Vì sao corruption phát hiện muộn gây khó chọn recovery point?
21. Vì sao không replay toàn bộ oplog sau bad writes?
22. Restore một document cũ có thể làm mất update tốt thế nào?
23. GridFS cần phục hồi những collections nào?
24. Search indexes có thể cần rebuild sau restore không?
25. Change stream token mới hơn restored source có rủi ro gì?
26. Nếu provider đã CAPTURED nhưng MongoDB rollback, cần làm gì?
27. Khi nào nên restore vào target mới?
28. Write fencing khi cutover là gì?
29. KMS keys liên quan recovery thế nào?
30. Ransomware response cần làm gì ngoài restore?
31. RTO có tính index/cache warm-up không?
32. Vì sao backup completedAt không đồng nghĩa last consistent point?
33. Document counts có chứng minh consistency không?
34. Business invariants nên kiểm tra loại nào?
35. Vì sao DR drill phải dùng production-like data?
36. Ai cần phê duyệt recovery point có data loss?
37. Khi nào dùng read-only degraded mode?
38. Retention phải xét attacker dwell time thế nào?
39. Vì sao restore drills cần định kỳ?
40. Đạt RPO nhưng không đạt RTO có đáp ứng cam kết không?

---

## 34. Tổng kết

Để bảo vệ dữ liệu MongoDB có ý nghĩa, phải bắt đầu từ yêu cầu nghiệp vụ:

- **RPO:** Mức mất dữ liệu tối đa chấp nhận được. Phải dựa trên **consistent recovery point thực sự restore được**, không chỉ backup frequency.
- **RTO:** Thời gian tối đa đến khi **chức năng dịch vụ sẵn sàng**, gồm detect, quyết định, provision, restore, rebuild, validate và cutover.
- **Recovery scope:** Dữ liệu được sửa/khôi phục và quan hệ consistency, từ một document tới toàn cluster/region, bao gồm external dependencies.

Những nguyên tắc đáng nhớ:

1. Replica set/failover không thay backup.
2. Atlas snapshots/PITR, `mongodump` và filesystem snapshots có giới hạn khác nhau.
3. `mongodump --oplog` không là arbitrary PITR hoặc backup sharded cluster hoàn chỉnh.
4. Selected restore không mặc nhiên giảm RTO.
5. Restore vào target cách ly có thể bảo vệ dữ liệu tốt hơn khi cần diff/merge.
6. Khôi phục dữ liệu phải kèm indexes, GridFS, broker, provider và business reconciliation.
7. KMS/keys, IAM, topology và network là một phần của recovery scope.
8. RPO/RTO phải được chứng minh trong **restore drills**, với timeline, validation và business sign-off.

Một kế hoạch tốt phải trả lời được: **Có thể khôi phục về mốc nào? Những dữ liệu nào phải nhất quán? Mất bao lâu để khách dùng lại chức năng quan trọng? Và bằng chứng thực tế nào cho thấy kế hoạch đó có thể chạy được?**

## Tài liệu tham khảo

- [MongoDB Atlas — Back Up, Restore and Archive Data](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Atlas Architecture Center — Guidance for Backups](https://www.mongodb.com/docs/atlas/architecture/current/backups/)
- [MongoDB Atlas — Continuous Cloud Backup Restore](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-continuous/)
- [MongoDB Atlas — Recover a Point In Time](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/)
- [MongoDB Atlas — Selected Databases and Collections Restore](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-db-coll/)
- [MongoDB Atlas — Restore Your Cluster](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-overview/)
- [MongoDB Atlas — Cloud Backup Overview](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/)
- [MongoDB Manual — Backups for Self-Managed](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Manual — Backup and Restore Tools](https://www.mongodb.com/docs/manual/tutorial/backup-and-restore-tools/)
- [MongoDB Manual — Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/)
- [MongoDB Manual — Sharded Cluster Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-filesystem-snapshots/)
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Database Tools — mongorestore Behavior and Usage](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/)
- [MongoDB Manual — Replica Set High Availability](https://www.mongodb.com/docs/manual/core/replica-set-high-availability/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
