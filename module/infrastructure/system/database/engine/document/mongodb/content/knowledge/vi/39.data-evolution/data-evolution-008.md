# Đối soát số lượng, kiểu dữ liệu, ràng buộc và kết quả nghiệp vụ

Khi một hệ thống MongoDB tiến hóa từ schema cũ sang schema mới, việc migration script chạy hết và trả exit code 0 **không đồng nghĩa dữ liệu đã được chuyển đúng**. Một document có thể được thêm vào đủ số lượng nhưng sai tenant, trường `amount` có thể đổi từ chuỗi `"100.50"` sang số `100.5` làm mất yêu cầu lưu tiền chính xác, hoặc trạng thái đơn hàng có thể được đổi tên thành công nhưng **số dư và tổng doanh thu không còn khớp**.

Bài **“Đối soát số lượng, kiểu dữ liệu, ràng buộc và kết quả nghiệp vụ”** thuộc chương **Tiến hóa dữ liệu** của module *Database Engine Document MongoDB* hướng dẫn cách **chứng minh trạng thái dữ liệu trước và sau migration là tương đương theo hợp đồng đã định nghĩa**, và biết chính xác ngoại lệ nào cần sửa, ngoại lệ nào là thay đổi nghiệp vụ có chủ đích.

Đối soát ở đây không chỉ là đếm documents. Một migration đáng tin cậy cần chứng minh **bốn lớp**:

1. **Số lượng và phạm vi:** Không mất, không tạo trùng, không chuyển nhầm tenant/namespace hoặc bỏ quên partition.
2. **Kiểu dữ liệu và cấu trúc:** Trường có BSON type đúng, xử lý missing/null chính xác, không mất precision, đúng quy tắc đổi tên/chuyển đổi.
3. **Ràng buộc kỹ thuật:** Unique keys, validators, required fields, relationships, referential assumptions và quy tắc lifecycle được giữ.
4. **Kết quả nghiệp vụ:** Tiền, điểm, trạng thái, số dư, quyền truy cập, audit event và các invariants phải đúng, kể cả khi tài liệu vật lý đã đổi hình dạng.

> **Phạm vi:** Ví dụ dùng `mongosh` và MongoDB Aggregation Pipeline, hướng tới MongoDB Server hiện đại. Một số operators/stages, sharded behavior và index validation phụ thuộc phiên bản; hãy đối chiếu manual đúng server/driver/FCV trước triển khai. Các tên collections, số lượng và dữ liệu dưới đây là **dữ liệu phòng lab giả định**. Không chạy các lệnh sửa/xóa trên production khi chưa có backup, phê duyệt và phương án rollback.

## 1. Mục tiêu học tập và thuật ngữ

Sau bài, người học có thể:

- Xác định **source of truth**, phạm vi, snapshot/watermark và cửa sổ đối soát.
- Xây **mapping contract** từ schema cũ sang mới, gồm convert/drop/derive/default.
- Chứng minh chênh lệch **count** theo collection, tenant, trạng thái và khóa nghiệp vụ.
- Phân biệt BSON `int`/`long`/`double`/`decimal`/`string`/`date`/`objectId`/`null`/missing.
- Kiểm tra ràng buộc `$jsonSchema`, unique index, partial index, tình trạng null và duplicate.
- Viết aggregation để tìm records **missing, extra, duplicated, wrong type, invalid range, dangling references**.
- Kiểm invariants như **tổng số dư, giao dịch cân bằng, trạng thái đơn, số lượng inventory, ledger totals**.
- Thiết kế đối soát trong **online migration với dual-write/change streams**.
- Tổ chức reconciliation reports, severity, tolerance, exception handling, fix-and-rerun, canary và rollback.
- Viết kế hoạch kiểm thử và vận hành để một migration được **chấp nhận bằng bằng chứng**, không phải bằng cảm giác.

### 1.1. Từ điển ngắn

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Baseline** | Số liệu và danh sách khóa từ nguồn ở mốc so sánh xác định. |
| **Snapshot/cut** | Mốc dữ liệu nhất quán mà hai phía được so sánh. |
| **Watermark** | Mốc tiến độ CDC/backfill đã xử lý, ví dụ resume token + checkpoint hoặc sequence nội bộ. |
| **Canonical form** | Biểu diễn thống nhất để so semantic equality giữa hai schema. |
| **Invariant** | Điều kiện luôn phải đúng theo nghiệp vụ, ví dụ tổng debit bằng tổng credit. |
| **Reconciliation key** | Khóa ổn định nối một thực thể ở schema cũ với schema mới. |
| **Missing/extra** | Bản ghi phải có mà không có / có ngoài phạm vi dự kiến. |
| **Diff** | Khác biệt có chứng cứ; cần phân loại intentional, transient hay defect. |
| **Tolerance** | Mức sai số được chấp nhận **có định nghĩa**, không phải cho qua mọi mismatch. |
| **Quarantine** | Tách records không chuyển đổi được để xử lý mà không mất thông tin. |
| **Go/no-go** | Quyết định cho phép hay dừng cutover dựa trên tiêu chí định trước. |

### 1.2. Đối soát khác kiểm thử migration script

Unit test cho hàm `convertLegacyOrder` có thể xác nhận 20 fixtures được convert đúng. Nhưng production có thể chứa:

- Trường cũ chưa từng thấy trong tests.
- 1.000 documents thiếu `tenantId`.
- String amount dùng dấu phẩy thập phân.
- Order đã bị cập nhật trong khi backfill chạy.
- Unique business key trùng qua nhiều tenants.
- Transactions cập nhật nhiều collections lệch thời điểm.

**Đối soát** đo dữ liệu thực theo contract, và phân tách **lỗi biến đổi dữ liệu** khỏi **thay đổi đang diễn ra của hệ thống**.

## 2. Tình huống xuyên suốt: đơn hàng schema v1 → v2

Giả sử ứng dụng thương mại điện tử lưu orders theo v1:

~~~javascript
// collection: orders_v1
{
  _id: ObjectId("66f000000000000000000001"),
  tenant: "tenant-a",
  orderNo: "ORD-1001",
  customer: "C-001",
  status: "new",
  amount: "125000",
  created: ISODate("2026-10-01T08:00:00Z"),
  items: [
    { sku: "SKU-01", qty: 2, unitPrice: "50000" },
    { sku: "SKU-02", qty: 1, unitPrice: "25000" }
  ]
}
~~~

Mục tiêu schema v2:

~~~javascript
// collection: orders_v2
{
  _id: "tenant-a:ORD-1001",
  legacyId: ObjectId("66f000000000000000000001"),
  tenantId: "tenant-a",
  orderNo: "ORD-1001",
  customerId: "C-001",
  status: "OPEN",
  amountMinor: NumberLong("125000"),
  createdAt: ISODate("2026-10-01T08:00:00Z"),
  items: [
    { sku: "SKU-01", quantity: 2, unitPriceMinor: NumberLong("50000") },
    { sku: "SKU-02", quantity: 1, unitPriceMinor: NumberLong("25000") }
  ],
  schemaVersion: 2
}
~~~

**Quy tắc chuyển đổi dự kiến:**

| Trường v1 | Trường v2 | Quy tắc | Đối soát |
|---|---|---|---|
| `_id` ObjectId | `legacyId` ObjectId | Bảo toàn nguyên giá trị. | Mapping một-một, không mất legacyId. |
| `tenant` | `tenantId` | Giữ nguyên tenant. | Không record nào chuyển nhầm tenant. |
| `orderNo` | `orderNo` | Không thay business order number. | Unique theo tenant. |
| `customer` | `customerId` | Giữ tham chiếu khách hàng. | Không dangling relation theo policy. |
| `status: "new"` | `status: "OPEN"` | Map theo bảng trạng thái. | Không có giá trị chưa được map. |
| `amount: "125000"` | `amountMinor: NumberLong(125000)` | Parse số nguyên đơn vị nhỏ nhất. | Không rounding, overflow, sai dấu. |
| `created` | `createdAt` | Giữ UTC instant. | Milliseconds/timestamp đúng. |
| `items[].qty` | `items[].quantity` | Giữ integer quantity. | Không âm/0 nếu business cấm. |
| `items[].unitPrice` | `items[].unitPriceMinor` | Parse string → int64. | Tổng line items = order amount theo policy. |
| không có | `schemaVersion` | Thêm constant `2`. | Đúng giá trị/kiểu BSON. |
| `_id` | `_id` mới | Key `tenant + ":" + orderNo`. | Key deterministic, collision-safe. |

Đây là một **mapping contract**, không phải script chuyển đổi hoàn chỉnh. Trong hệ thống thật cần định nghĩa thêm currency, tax/discount/shipping/refund semantics. Ví dụ này giả định amountMinor bằng tổng line items và chưa có taxes/discounts; **không áp invariants sai cho domain có chiết khấu**.

### 2.1. Khóa đối soát ổn định

Không nên so `orders_v1._id` với `orders_v2._id` vì kiểu/giá trị đã đổi. Dùng:

~~~text
v1: (_id ObjectId) --legacyId--> v2
business key: (tenant, orderNo) --mapped--> (tenantId, orderNo)
~~~

Một schema migration có thể **thay đổi identity kỹ thuật** nhưng vẫn bảo toàn identity nghiệp vụ. Nên giữ `legacyId` trong giai đoạn chuyển đổi để điều tra missing/duplicate/collisions; chỉ xóa trường này sau khi retention/audit policy cho phép.

### 2.2. Phân loại thay đổi có chủ đích

Ví dụ đổi `new → OPEN` là khác biệt về raw bytes nhưng **đúng contract**. Ngược lại:

~~~text
v1 amount = "125000"
v2 amountMinor = NumberLong("12500")
~~~

không hợp lệ vì mất một chữ số. Đối soát không nên yêu cầu **raw BSON equality** cho hai schema cố ý khác nhau; phải so **canonical business meaning**.

### 2.3. Phạm vi đối soát

Trước khi chạy, viết rõ:

- Database/collections nguồn và đích.
- Tenants active/inactive, dữ liệu archived/deleted có được chuyển không.
- Khoảng thời gian lịch sử và retention.
- Records nằm trong quarantine/invalid source.
- Field nào chỉ được derive, field nào được drop có lý do.
- Khóa nối, điều kiện membership và business invariants.
- Mốc cut/watermark khi có concurrent writes.

**Không** định nghĩa scope là “mọi documents nhìn thấy lúc query” nếu hai phía đang tiếp tục thay đổi.

## 3. Bốn cấp độ đối soát

| Cấp | Câu hỏi | Ví dụ | Giới hạn |
|---|---|---|---|
| **L1: Count** | Bao nhiêu docs/keys ở mỗi phía? | 10.000 orders trước và sau. | Cùng count vẫn có thể mất A và thêm sai B. |
| **L2: Structure/type** | BSON types, required/optional fields đúng? | `amountMinor` phải `long`, `createdAt` phải `date`. | Đúng type nhưng giá trị sai. |
| **L3: Constraints/references** | Unique/range/enum/relations đúng? | Tenant+orderNo unique, status allowed. | Referential checks vẫn có thể bỏ qua logic tiền. |
| **L4: Business outcome** | Kết quả nghiệp vụ tương đương? | Tổng tiền, các trạng thái, inventory, ledger. | Phải định nghĩa đúng semantic contract. |

Một đối soát đầy đủ thường **đi từ rộng đến sâu**:

~~~text
Baseline count
   |
   v
Partition count by tenant/date/status
   |
   v
Join/compare business keys
   |
   v
Type/field/value validation
   |
   v
Constraints + reference integrity
   |
   v
Business invariants / ledger totals
   |
   v
Exception review -> fix -> rerun -> sign-off
~~~

### 3.1. Đối soát không luôn cần 100% raw comparison

Với dữ liệu hàng TB, full compare có thể tiêu tốn CPU/IOPS đáng kể. Có thể dùng **partitioned counts/checksums + incremental exact checks + risk-based samples**, nhưng phải nói rõ mức bảo đảm:

- **100% exact** cho primary keys, tiền, trạng thái quan trọng, uniqueness.
- **Sample** cho payload ít rủi ro hoặc dữ liệu archival khi SLA cho phép.
- **Checksum** để khoanh vùng, sau đó exact diff tại partition bất thường.

Không tuyên bố sampling 1% chứng minh 100% documents chính xác.

### 3.2. Điểm dừng tối thiểu khi migration quan trọng

Đề xuất tiêu chí **go/no-go** do business phê duyệt:

~~~text
MUST:
  - zero missing critical business keys
  - zero extra unauthorized tenant records
  - zero invalid required BSON types
  - zero duplicate unique business keys
  - zero unexplained ledger imbalance
  - source/target CDC watermark converged
  - rollback/fallback remains possible

MAY:
  - allow documented differences in deprecated optional fields
  - allow bounded informational count drift if cut has not converged
    but NEVER declare final reconciliation pass in that state
~~~

Mức zero ở trên là một **policy minh họa**, không phải MongoDB tự bắt buộc. Với dữ liệu ít rủi ro, business có thể chấp nhận tolerance có lý do; với tiền và quyền truy cập, sai một record cũng có thể là lỗi nghiêm trọng.

## 4. Chọn thời điểm so sánh: baseline, snapshot và watermark

Một sai lầm phổ biến là:

~~~text
10:00:00  count orders_v1 -> 100,000
10:00:30  app inserts 500 new orders
10:01:00  count orders_v2 -> 100,500
~~~

Hai số khác nhau **có thể đúng ở hai thời điểm khác nhau**, không chứng minh migration sai. Để đối soát đáng tin, phải đồng bộ **time boundary**.

### 4.1. Ba chiến lược

| Chiến lược | Phù hợp | Ưu/nhược |
|---|---|---|
| **Quiesce writes** | Migration offline/maintenance window. | Dễ lấy cut nhất quán, nhưng downtime. |
| **Coordinated snapshot/backup point** | Workload cần online nhưng có backup/CDC. | Cần kỹ thuật snapshot timestamp/topology đúng. |
| **Backfill + CDC watermark** | Online migration không dừng writes lâu. | Phức tạp vì ordering, deletes, replay, convergence và duplicates. |

### 4.2. Quiesce writes rõ nghĩa

Nếu tạm dừng requests ghi, consumers/background jobs, DDL và đợi in-flight transactions kết thúc:

1. Chốt thời điểm cut \(T\).
2. Chụp baseline nguồn.
3. Migration sang đích.
4. Đối soát toàn bộ theo scope tại \(T\).
5. Cutover khi đạt tiêu chí.

Không đủ chỉ “bảo frontend ngừng gửi POST”: workers, scheduled tasks, change stream processors, TTL/index behaviors và các dịch vụ khác vẫn có thể mutate dữ liệu.

### 4.3. Backup/snapshot không phải một `Date.now()`

Chạy `new Date()` trước hai queries không tạo snapshot. Nếu nguồn và đích khác collections/clusters, mỗi aggregate bình thường có thể đọc tại thời điểm khác nhau. Khi cần cut nhất quán, dùng **snapshot/transaction/backup strategy hỗ trợ topology** hoặc CDC sequence/watermark được xác minh.

### 4.4. CDC watermark

Một pipeline thường có:

~~~text
Source snapshot @ T0
       |
       v
Backfill historical documents
       |
       v
CDC change stream events since T0
       |
       v
Apply upserts/deletes to target
       |
       v
Durable checkpoint / resume token
       |
       v
Wait until CDC lag small / catch-up at cut T1
       |
       v
Reconciliation of source and target at comparable watermark
~~~

**Không được chỉ dựa vào đồng hồ giữa hai machines** để xác định “đã theo kịp”; cần một sequence/clusterTime/resume token hoặc cơ chế ordering consistent với kiến trúc. MongoDB change streams có retention/oplog window và resume constraints; nếu token không còn resume được, cần resnapshot/rebuild theo runbook.

### 4.5. Dữ liệu được xóa trong lúc migration

Backfill đọc record A, sau đó source xóa A, nhưng consumer chỉ xử lý inserts/updates: target giữ **extra record A**. Đối soát count/key sẽ phát hiện. CDC apply phải xử lý **delete/tombstone** hoặc bảo đảm target purge theo source-of-truth semantics.

### 4.6. Writes trong cả hai hệ thống

Nếu app tạm dual-write source+target, thứ tự write có thể lệch:

~~~text
Source write succeeds
Target write times out
App retries target
Old event later arrives out of order
~~~

Đối soát cần sequence/version, idempotent upsert và **conflict resolution policy**. Không suy “dual-write cùng transaction” khi hai clusters/services không có distributed transaction coordination.

### 4.7. Read concern và write concern

`readConcern: "majority"` đảm bảo dữ liệu đọc đã majority committed theo semantics, **không tự tạo một snapshot timestamp chung cho hai queries**. `writeConcern:"majority"` giúp độ bền ghi, **không** bảo đảm target đã nhận CDC event mới nhất. Với giao dịch/snapshot reads phải kiểm server/version và khả năng long-running snapshot gây tài nguyên/retention pressure.

### 4.8. Lưu metadata của mỗi lần đối soát

~~~json
{
  "reconciliationRunId": "orders-v2-20261114-001",
  "mappingVersion": "orders-v1-to-v2.3",
  "source": "shop.orders_v1",
  "target": "shop.orders_v2",
  "scope": "all active tenants up to cut T",
  "snapshotOrWatermark": "<verified value>",
  "startedAtUtc": "2026-11-14T02:00:00Z",
  "status": "RUNNING",
  "toolVersion": "reconcile-1.5",
  "checksumAlgorithm": "sha256-canonical-v2",
  "approvedTolerancePolicy": "policy-2026-11"
}
~~~

Đây là **manifest của ứng dụng minh họa**, không phải format bắt buộc của MongoDB. `snapshotOrWatermark` phải là mốc **thực sự đã xác minh**, không tự điền theo thời gian chạy scheduler.

## 5. Chuẩn bị phòng lab và baseline

Các lệnh dưới đây minh họa trong database **`schema_reconcile_lab`**. Chỉ chạy trên một MongoDB instance/cluster thử nghiệm có quyền sử dụng; **không tạo hoặc xóa collections trên production**. Chạy fixture một lần vì có giá trị `_id` cố định.

### 5.1. Tạo nguồn

~~~javascript
const lab = db.getSiblingDB("schema_reconcile_lab")

lab.orders_v1.insertMany([
  {
    _id: ObjectId("66f000000000000000000001"),
    tenant: "tenant-a",
    orderNo: "ORD-1001",
    customer: "C-001",
    status: "new",
    amount: "125000",
    created: ISODate("2026-10-01T08:00:00Z"),
    items: [
      { sku: "SKU-01", qty: 2, unitPrice: "50000" },
      { sku: "SKU-02", qty: 1, unitPrice: "25000" }
    ]
  },
  {
    _id: ObjectId("66f000000000000000000002"),
    tenant: "tenant-a",
    orderNo: "ORD-1002",
    customer: "C-002",
    status: "paid",
    amount: "50000",
    created: ISODate("2026-10-02T09:30:00Z"),
    items: [{ sku: "SKU-01", qty: 1, unitPrice: "50000" }]
  },
  {
    _id: ObjectId("66f000000000000000000003"),
    tenant: "tenant-b",
    orderNo: "ORD-2001",
    customer: "C-003",
    status: "new",
    amount: "30000",
    created: ISODate("2026-10-03T10:00:00Z"),
    items: [{ sku: "SKU-03", qty: 2, unitPrice: "15000" }]
  },
  {
    _id: ObjectId("66f000000000000000000004"),
    tenant: "tenant-b",
    orderNo: "ORD-2002",
    customer: "C-004",
    status: "cancelled",
    amount: "40000",
    created: ISODate("2026-10-04T11:00:00Z"),
    items: [{ sku: "SKU-04", qty: 1, unitPrice: "40000" }]
  }
])
~~~

### 5.2. Tạo đích cố ý chứa ba loại sai lệch

~~~javascript
lab.orders_v2.insertMany([
  {
    _id: "tenant-a:ORD-1001",
    legacyId: ObjectId("66f000000000000000000001"),
    tenantId: "tenant-a",
    orderNo: "ORD-1001",
    customerId: "C-001",
    status: "OPEN",
    amountMinor: NumberLong("125000"),
    createdAt: ISODate("2026-10-01T08:00:00Z"),
    items: [
      { sku: "SKU-01", quantity: 2,
        unitPriceMinor: NumberLong("50000") },
      { sku: "SKU-02", quantity: 1,
        unitPriceMinor: NumberLong("25000") }
    ],
    schemaVersion: NumberInt(2)
  },
  {
    _id: "tenant-a:ORD-1002",
    legacyId: ObjectId("66f000000000000000000002"),
    tenantId: "tenant-a",
    orderNo: "ORD-1002",
    customerId: "C-002",
    status: "PAID",
    amountMinor: "50000", // sai kiểu: string thay cho BSON long
    createdAt: ISODate("2026-10-02T09:30:00Z"),
    schemaVersion: NumberInt(2)
  },
  {
    _id: "tenant-b:ORD-2001",
    legacyId: ObjectId("66f000000000000000000003"),
    tenantId: "tenant-b",
    orderNo: "ORD-2001",
    customerId: "C-003",
    status: "OPEN",
    amountMinor: NumberLong("3000"), // sai giá trị: thiếu một số 0
    createdAt: ISODate("2026-10-03T10:00:00Z"),
    schemaVersion: NumberInt(2)
  },
  {
    _id: "tenant-a:ORD-ORPHAN",
    legacyId: ObjectId("66f000000000000000000099"),
    tenantId: "tenant-a",
    orderNo: "ORD-ORPHAN",
    customerId: "C-999",
    status: "OPEN",
    amountMinor: NumberLong("500"),
    createdAt: ISODate("2026-10-05T08:00:00Z"),
    schemaVersion: NumberInt(2)
  }
])
~~~

**Kết quả đã thiết kế để người học phát hiện:**

- Nguồn có **4**, đích có **4** documents: tổng count **bằng nhau**.
- `ORD-2002` **missing** ở đích.
- `ORD-ORPHAN` là **extra** record ở đích.
- `ORD-1002.amountMinor` là **string**, sai BSON type.
- `ORD-2001.amountMinor` là long nhưng **sai giá trị**.
- `ORD-1001` chuyển đúng theo quy tắc ví dụ.

Fixture minh họa chủ ý **không có `items` ở một số v2 records** để người học thấy thêm lớp **required-field/nested-invariant** cũng có thể sai. Không dùng các bản ghi cố ý sai để kết luận một pipeline MongoDB production hoạt động như vậy; đây là dữ liệu được chèn thủ công để luyện phân tích.

### 5.3. Index hỗ trợ đối soát

~~~javascript
lab.orders_v1.createIndex({ tenant: 1, orderNo: 1 })
lab.orders_v2.createIndex({ tenantId: 1, orderNo: 1 })
lab.orders_v2.createIndex({ legacyId: 1 })
lab.orders_v2.createIndex({ tenantId: 1, status: 1, createdAt: 1 })
~~~

Các indexes phục vụ fixture/query, **không tự là unique constraints**. Trước khi tạo unique indexes thật, phải xử lý duplicates; `createIndex` trên dữ liệu lớn có ảnh hưởng I/O/CPU và cần rollout plan. Thêm index phù hợp keyset pagination/partition scan dựa trên query shape thực tế.

### 5.4. Không reset lab bằng lệnh nguy hiểm

Khi cần chạy lại fixture, xác minh đúng cluster/db sandbox trước khi dọn. Bài không đưa một lệnh `dropDatabase()` chung để người học vô tình copy vào production. Đối soát thực tế ưu tiên **read-only credentials**, chỉ chương trình migration/remediation riêng mới có quyền sửa.

## 6. Đối soát số lượng: từ tổng count đến từng phân vùng

### 6.1. `countDocuments`, `estimatedDocumentCount` và `$count`

~~~javascript
const sourceCount = lab.orders_v1.countDocuments({})
const targetCount = lab.orders_v2.countDocuments({})

printjson({
  sourceCount,
  targetCount,
  delta: targetCount - sourceCount
})
~~~

Với lab trên, tổng đều bằng 4, delta 0; **không thể kết luận PASS**.

| API | Dùng khi | Giới hạn |
|---|---|---|
| `countDocuments(filter)` | Muốn đếm matching documents theo filter. | Có thể scan/index scan tốn tài nguyên trên collection lớn; không tự là snapshot với query khác. |
| `estimatedDocumentCount()` | Cần **ước lượng nhanh từ metadata**. | Không dùng để chứng minh đối soát exact count; metadata có thể không phản ánh exact scope/filters. |
| Aggregation `$count` | Đếm sau các stages lọc/biến đổi. | Kết quả là aggregate cursor; phải định nghĩa cut và filter. |
| `$group` + `$sum:1` | Đếm theo tenant/status/bucket. | Cần normalize labels và giữ scope. |

**Lưu ý:** MongoDB `countDocuments({})` có thể tốn chi phí khi tập dữ liệu lớn, nên xem index/hint/measurement theo tài liệu. Đừng dùng `estimatedDocumentCount` để ra quyết định go/no-go có yêu cầu exact.

### 6.2. Count theo tenant

~~~javascript
lab.orders_v1.aggregate([
  { $group: {
      _id: "$tenant",
      count: { $sum: 1 }
  }},
  { $sort: { _id: 1 } }
])

lab.orders_v2.aggregate([
  { $group: {
      _id: "$tenantId",
      count: { $sum: 1 }
  }},
  { $sort: { _id: 1 } }
])
~~~

Trong lab:

| Tenant | v1 count | v2 count | Delta |
|---|---:|---:|---:|
| tenant-a | 2 | 3 | +1 |
| tenant-b | 2 | 1 | −1 |
| **Tổng** | **4** | **4** | **0** |

Tổng delta 0 che giấu **tenant-a dư 1 và tenant-b thiếu 1**. Vì vậy phải so theo partition key có ý nghĩa.

### 6.3. Count theo trạng thái đã normalize

Nếu v1 dùng `new/paid/cancelled` còn v2 dùng `OPEN/PAID/CANCELLED`, không so raw status strings:

~~~javascript
lab.orders_v1.aggregate([
  { $project: {
      tenantId: "$tenant",
      normalizedStatus: {
        $switch: {
          branches: [
            { case: { $eq: ["$status", "new"] }, then: "OPEN" },
            { case: { $eq: ["$status", "paid"] }, then: "PAID" },
            { case: { $eq: ["$status", "cancelled"] },
              then: "CANCELLED" }
          ],
          default: "__UNMAPPED__"
        }
      }
  }},
  { $group: {
      _id: { tenantId: "$tenantId", status: "$normalizedStatus" },
      count: { $sum: 1 }
  }},
  { $sort: { "_id.tenantId": 1, "_id.status": 1 } }
])
~~~

Mọi giá trị `__UNMAPPED__` là một **exception cần điều tra**, không được silently map thành `OPEN` chỉ để totals khớp.

### 6.4. Count theo ngày nhưng kiểm timezone

~~~javascript
lab.orders_v2.aggregate([
  { $group: {
      _id: {
        tenantId: "$tenantId",
        day: {
          $dateToString: {
            format: "%Y-%m-%d",
            date: "$createdAt",
            timezone: "UTC"
          }
        }
      },
      count: { $sum: 1 }
  }},
  { $sort: { "_id.tenantId": 1, "_id.day": 1 } }
])
~~~

Nếu business định nghĩa ngày theo **Asia/Ho_Chi_Minh**, thay `timezone` phù hợp ở **cả hai phía**. Dùng UTC ở nguồn và local time ở đích có thể tạo mismatch giả gần midnight.

### 6.5. Công thức count delta

Với mỗi partition \(p\):

\[
\Delta_p = N_{\mathrm{target},p} - N_{\mathrm{source},p}
\]

Khi cut/watermark thực sự tương đương và không có filter intentional:

\[
\forall p,\quad \Delta_p = 0
\]

Nhưng **\(\Delta_p=0\) chưa đủ**, vì A có thể mất và B được thêm. Phải so **tập keys** ở bước kế tiếp.

### 6.6. Phân vùng có ý nghĩa nghiệp vụ

Một bộ partitions thường gồm:

- Tenant/region/data residency.
- SchemaVersion/status.
- Created date hoặc ObjectId range theo migration plan.
- Currency hoặc payment method.
- Soft-delete/archived/active.
- Shard key ranges nếu sharded.

**Không** chỉ group theo `status` nếu một tenant có thể bị chuyển sang tenant khác mà tổng theo status vẫn bằng nhau.

### 6.7. Xử lý soft delete và TTL

Nếu nguồn có `deletedAt` và target loại bỏ deleted records theo business rule, count target **phải được so với baseline đã lọc nguồn**, không với toàn nguồn. MongoDB TTL monitor cũng có thể xóa documents tự động theo policy. Ghi rõ retention/time boundary và tránh đối soát qua hai thời điểm không cùng lifecycle.

## 7. Đối soát tập khóa: tìm thiếu, thừa, trùng và sai ánh xạ

**Count chỉ là tín hiệu sơ bộ.** Phải chứng minh mỗi record thuộc scope nguồn có **đúng một** bản tương ứng ở đích và ngược lại. Với fixture, `legacyId` là khóa nối từ `orders_v2` đến `orders_v1._id`.

### 7.1. Tìm bản ghi nguồn không có trong đích

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "targetMatches"
    }
  },
  {
    $match: {
      $expr: { $eq: [{ $size: "$targetMatches" }, 0] }
    }
  },
  {
    $project: {
      _id: 1, tenant: 1, orderNo: 1,
      reason: { $literal: "MISSING_TARGET" }
    }
  }
])
~~~

Ở fixture, query trả `ORD-2002`. `$lookup` này hoạt động trong **cùng database**; nếu source và target ở **hai clusters độc lập**, không thể dùng một `$lookup` để join trực tiếp qua hai clusters. Khi đó cần reconcile service đọc hai bên qua driver, so keysets hoặc export key manifests/partition hashes đã được kiểm soát.

### 7.2. Tìm bản ghi đích không có trong nguồn

~~~javascript
lab.orders_v2.aggregate([
  {
    $lookup: {
      from: "orders_v1",
      localField: "legacyId",
      foreignField: "_id",
      as: "sourceMatches"
    }
  },
  {
    $match: {
      $expr: { $eq: [{ $size: "$sourceMatches" }, 0] }
    }
  },
  {
    $project: {
      _id: 1, tenantId: 1, orderNo: 1, legacyId: 1,
      reason: { $literal: "EXTRA_TARGET" }
    }
  }
])
~~~

Ở fixture, `ORD-ORPHAN` là extra. **Không tự xóa** mọi extra record: có thể là bản ghi sinh ra ở target sau cut, seed hợp lệ, hoặc dữ liệu của scope khác. Cần điều tra mốc thời gian, business rule và ownership trước remediation.

### 7.3. Phát hiện một nguồn map ra nhiều đích

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "targets"
    }
  },
  {
    $match: {
      $expr: { $gt: [{ $size: "$targets" }, 1] }
    }
  },
  {
    $project: {
      orderNo: 1,
      targetCount: { $size: "$targets" },
      targetIds: "$targets._id"
    }
  }
])
~~~

Trên collection lớn, `$lookup` sinh array kết quả có thể tốn nhiều RAM/đụng giới hạn BSON; phương pháp group key trên target thường hiệu quả hơn khi chỉ muốn tìm duplicates:

~~~javascript
lab.orders_v2.aggregate([
  {
    $group: {
      _id: "$legacyId",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } }
])
~~~

`$push` toàn bộ IDs vào một group có thể tạo memory/output lớn; trong production ưu tiên chỉ đếm và giới hạn sample IDs khi cardinality cao. Trường `legacyId` missing sẽ group vào nhóm tương ứng (theo BSON expression), cần kiểm missing/null riêng để không chẩn đoán nhầm.

### 7.4. Duplicates theo khóa nghiệp vụ

~~~javascript
lab.orders_v2.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        orderNo: "$orderNo"
      },
      n: { $sum: 1 }
    }
  },
  { $match: { n: { $gt: 1 } } }
])
~~~

Đây là kiểm tra **cặp (tenantId, orderNo)**, không phải `orderNo` đơn lẻ vì hai tenants có thể hợp lệ cùng một order number. Nếu business yêu cầu uniqueness global thì đổi contract và index tương ứng.

### 7.5. Một-một chưa bảo đảm đúng cặp tenant

Một target có `legacyId` hợp lệ nhưng `tenantId` sai vẫn được join. Kiểm thêm:

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "t"
    }
  },
  { $unwind: "$t" },
  {
    $match: {
      $expr: {
        $or: [
          { $ne: ["$tenant", "$t.tenantId"] },
          { $ne: ["$orderNo", "$t.orderNo"] },
          { $ne: ["$customer", "$t.customerId"] }
        ]
      }
    }
  },
  {
    $project: {
      sourceId: "$_id",
      sourceTenant: "$tenant",
      targetId: "$t._id",
      targetTenant: "$t.tenantId",
      sourceOrderNo: "$orderNo",
      targetOrderNo: "$t.orderNo"
    }
  }
])
~~~

Nếu một nguồn map thành nhiều đích, `$unwind` phát nhiều rows; phải xử lý **duplicate cardinality** trước khi diễn giải mỗi diff row là một thực thể duy nhất.

### 7.6. So theo tập khóa với `$setDifference`

Với **tập nhỏ đã được giới hạn** có thể đưa vào memory:

~~~javascript
// Chỉ cho lab nhỏ; KHÔNG dùng toArray() cho hàng triệu keys.
const sourceKeys = lab.orders_v1
  .find({}, { tenant: 1, orderNo: 1, _id: 0 })
  .toArray()
  .map(x => x.tenant + "|" + x.orderNo)

const targetKeys = lab.orders_v2
  .find({}, { tenantId: 1, orderNo: 1, _id: 0 })
  .toArray()
  .map(x => x.tenantId + "|" + x.orderNo)

const missing = sourceKeys.filter(x => !targetKeys.includes(x))
const extra = targetKeys.filter(x => !sourceKeys.includes(x))
printjson({ missing, extra })
~~~

Đây là script minh họa **chỉ với vài records**. `Array.includes` khiến phép so có thể gần \(O(n^2)\), còn nối chuỗi với delimiter `|` có thể tạo **collision** nếu tên tenant/orderNo chứa delimiter. Trong production dùng key encoding có chiều dài/từng field rõ ràng, `Set`/merge sort/indexed lookups, streaming chunks và memory budget.

### 7.7. Phân biệt “mất record” và “chưa chuyển xong”

Trong online migration, record source mới commit lúc 10:00:05 nhưng CDC checkpoint target mới tới 10:00:03. Nếu đối soát ngay lúc đó, record sẽ trông missing **tạm thời**. Không cho qua vĩnh viễn: phân loại `NOT_CAUGHT_UP` trong trạng thái RUNNING, chỉ quyết định final **sau khi hai phía cùng mốc so sánh**.

### 7.8. Reconciliation key có thể đổi vì update nghiệp vụ

Nếu `orderNo` có thể sửa sau khi tạo, khóa đối soát theo orderNo không ổn định. Ưu tiên immutable source ID hoặc một migration ID được persist; nếu business key có thể đổi, dùng mapping table lưu **old key → stable entity ID → current key** và xử lý rename events.

### 7.9. Khóa ghép và collation

MongoDB collation có thể quyết định việc `"ABC"` bằng `"abc"` khi unique/query; client app so chuỗi bằng Java `String.equals` có semantics khác. Quy định:

- Có phân biệt chữ hoa/thường không?
- Có trim whitespace hoặc Unicode normalization không?
- Có bỏ dấu tiếng Việt khi search nhưng không khi identity không?
- Có padding leading zeros trong orderNo không?

Đối soát key phải dùng **cùng normalization/collation contract**, không tự `toLowerCase` mọi ID khiến hai thực thể khác bị nhập làm một.

## 8. Kiểm tra kiểu BSON, missing, null và cấu trúc lồng nhau

### 8.1. BSON type khác JavaScript type

MongoDB lưu các BSON types như `int` (32-bit), `long` (64-bit), `double` (floating point), `decimal` (Decimal128), `string`, `date`, `objectId`, `bool`, `array`, `object` và `null`. Trong `mongosh`, biểu diễn số JavaScript có thể khác kiểu BSON thực trên server, nên **không chỉ dùng `typeof`**.

Ví dụ:

~~~javascript
// Explicit BSON constructors trong mongosh:
NumberInt(12)          // BSON int32
NumberLong("12")       // BSON int64
NumberDecimal("12.30") // BSON Decimal128
ISODate("2026-11-14T00:00:00Z") // BSON Date
ObjectId("66f000000000000000000001")
~~~

### 8.2. Thống kê phân phối kiểu một field

~~~javascript
lab.orders_v2.aggregate([
  {
    $project: {
      amountType: { $type: "$amountMinor" }
    }
  },
  {
    $group: {
      _id: "$amountType",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
~~~

Với fixture, kỳ vọng `long` có 3 records và `string` có 1. Chênh lệch **kiểu** này không thể nhìn thấy qua count tổng.

### 8.3. Liệt kê records sai kiểu

~~~javascript
lab.orders_v2.aggregate([
  {
    $match: {
      $expr: {
        $ne: [{ $type: "$amountMinor" }, "long"]
      }
    }
  },
  {
    $project: {
      orderNo: 1,
      tenantId: 1,
      amountMinor: 1,
      actualType: { $type: "$amountMinor" }
    }
  }
])
~~~

**Khác biệt quan trọng:** Aggregation `$type` trả chuỗi `"missing"` khi field không tồn tại, `"null"` khi field có BSON null. Query-language `{field: {$type: "long"}}` có semantics riêng, đặc biệt với arrays; nên dùng `$expr` và ``$type` expression khi muốn phân loại chính xác một **field ở path cụ thể**.

### 8.4. Missing và null không đồng nghĩa

~~~javascript
// Document A:
{ _id: "A" } // amountMinor missing

// Document B:
{ _id: "B", amountMinor: null } // amountMinor explicitly null
~~~

Trong MongoDB query:

~~~javascript
// Có thể match cả null và missing:
db.orders_v2.find({ amountMinor: null })

// Chỉ field tồn tại với BSON null:
db.orders_v2.find({ amountMinor: { $type: "null" } })

// Chỉ field không tồn tại:
db.orders_v2.find({ amountMinor: { $exists: false } })
~~~

`$exists:true` cũng bao gồm field có giá trị null. Đối với field required, cả missing và null có thể phải bị cấm; nhưng với optional “chưa biết” thì missing và null có thể mang nghĩa khác nhau theo contract.

### 8.5. Một thống kê missing/null/wrong type

~~~javascript
lab.orders_v2.aggregate([
  {
    $project: {
      kind: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [{ $type: "$amountMinor" }, "missing"]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: [{ $type: "$amountMinor" }, "null"]
              },
              then: "NULL"
            },
            {
              case: {
                $eq: [{ $type: "$amountMinor" }, "long"]
              },
              then: "OK_LONG"
            }
          ],
          default: "WRONG_TYPE"
        }
      }
    }
  },
  { $group: { _id: "$kind", count: { $sum: 1 } } }
])
~~~

Kết quả là **các categories loại trừ nhau**, hữu ích hơn một counter “bad” chung vì remediation cho missing/null/string khác nhau.

### 8.6. Kiểu của các fields bắt buộc

Một profile schema v2 có thể đặt:

| Field | BSON type cần có | Bắt buộc? | Ý nghĩa |
|---|---|---|---|
| `_id` | string | Có | Deterministic target ID. |
| `legacyId` | objectId | Có trong transition | Join ngược nguồn. |
| `tenantId` | string | Có | Tenant boundary. |
| `orderNo` | string | Có | Business ID. |
| `customerId` | string | Có | Relation ID. |
| `status` | string | Có | Enum contract. |
| `amountMinor` | long | Có | Số nguyên đơn vị tiền nhỏ nhất. |
| `createdAt` | date | Có | UTC instant. |
| `items` | array | Có theo ví dụ | Line items. |
| `schemaVersion` | int | Có | Phiên bản schema. |

Không mặc định `int` và `long` có thể thay nhau chỉ vì cả hai là integer theo toán học. Nếu hệ thống Java đọc bằng `Long`, một tài liệu lưu BSON int32 có thể được converter xử lý khác tùy layer; khi contract yêu cầu **long**, phải đối soát đúng type và mapping.

### 8.7. Field lồng nhau và array elements

~~~javascript
lab.orders_v2.aggregate([
  { $unwind: { path: "$items", preserveNullAndEmptyArrays: true } },
  {
    $project: {
      orderNo: 1,
      itemType: { $type: "$items" },
      skuType: { $type: "$items.sku" },
      qtyType: { $type: "$items.quantity" },
      priceType: { $type: "$items.unitPriceMinor" }
    }
  }
])
~~~

Lệnh giúp xem từng item; với array missing/empty, `preserveNullAndEmptyArrays:true` vẫn giữ order row nhưng không chứng minh “có item hợp lệ”. Phải tách kiểm **items array tồn tại, non-empty** (nếu required) khỏi kiểm từng element type. Dùng `$isArray`, `$size`/`$filter` có guards để tránh lỗi khi field không phải array.

### 8.8. `$isNumber` không thay exact type requirement

`$isNumber` xác nhận biểu thức có kiểu numeric BSON (`int`, `long`, `double`, `decimal`) nhưng **không đảm bảo exact int64**. Với tiền `amountMinor` phải luôn là `long`, dùng `$type` (và range rules) thay vì chỉ `$isNumber`.

### 8.9. Date là instant, không phải string trông giống ISO

~~~javascript
{ createdAt: "2026-10-01T08:00:00Z" }   // BSON string
{ createdAt: ISODate("2026-10-01T08:00:00Z") } // BSON Date
~~~

Hai biểu diễn nhìn giống trong JSON nhưng **khác type**, ảnh hưởng sort/range queries, TTL indexes, timezone logic và serialization. Trong đối soát, so UTC instant/millisecond theo contract, không mặc định chuỗi input đã được parse đúng múi giờ.

### 8.10. ObjectId và string

`ObjectId("66...")` khác string `"66..."` về BSON type và index comparison. Nếu đổi ObjectId → String ID là chủ đích, cần canonical mapping (ví dụ ObjectId hex chuẩn) và giữ legacy link; **không** coi hai values raw-equal khi query `$lookup`.

## 9. Đối soát quy tắc convert: kiểu hợp lệ chưa đủ

Một value có BSON type đúng vẫn có thể **sai giá trị**. Nguồn `"30000"` chuyển thành `NumberLong("3000")` là long hợp lệ nhưng kết quả sai 10 lần. Vì vậy cần so **source chuẩn hóa theo contract** với target, thay vì chỉ kiểm type của target.

### 9.1. Phát hiện lỗi parse trước khi convert

~~~javascript
lab.orders_v1.aggregate([
  {
    $project: {
      orderNo: 1,
      tenant: 1,
      originalAmount: "$amount",
      originalType: { $type: "$amount" },
      parsed: {
        $convert: {
          input: "$amount",
          to: "long",
          onError: "__INVALID__",
          onNull: "__NULL_OR_MISSING__"
        }
      }
    }
  }
])
~~~

`$convert` cho phép xử lý lỗi mà không abort cả aggregation. Nhưng dùng sentinel string ``__NULL_OR_MISSING__` tự nó không phân biệt missing và null; phải xem `originalType` để phân loại. Trong production nên lưu **error code và raw value redacted** trong quarantine manifest, không âm thầm bỏ record vì `onError:null`.

### 9.2. Khi nào không dùng `$toLong` mù?

~~~javascript
{ $toLong: "$amount" }
~~~

Nếu `amount` là `"N/A"` hoặc vượt int64 range, aggregation có thể thất bại; nếu input double, conversion có thể truncate fractional part theo semantics và mất precision. Với migration tiền:

1. Validate input format/scale/currency.
2. Parse theo quy tắc đã ký.
3. Kiểm range/overflow.
4. Kiểm target type và giá trị.
5. Quarantine nếu không convert được.

`$convert` với `onError` giúp tạo báo cáo lỗi thay vì làm toàn batch chết, nhưng **không được biến invalid source thành zero**.

### 9.3. Quy định rõ đơn vị tiền

Trong ví dụ, nguồn `"125000"` là **minor units (đồng)** và target `NumberLong(125000)`. Nếu nguồn là `"1250.00"` major units, mapping phải biết **currency exponent**:

~~~text
USD: 12.34 dollars -> 1234 cents (scale=2)
JPY: 100 yen       -> 100 yen   (scale=0)
VND: 125000 dong   -> 125000 dong (scale=0 in this example)
~~~

Không áp `×100` cho mọi currency. Đối soát phải xác nhận currency và rounding policy, không so numbers khác đơn vị rồi gọi là pass.

### 9.4. `Double` và `Decimal128` không giống nhau

Double lưu nhị phân dấu phẩy động, nhiều số thập phân không biểu diễn chính xác (ví dụ `0.1`). Decimal128 lưu số thập phân theo độ chính xác/scale semantics phù hợp hơn nhiều nghiệp vụ tài chính. Nếu contract yêu cầu `Decimal128("12.30")`, đích `double 12.3` **khác kiểu và có thể khác precision**, dù khi in ra có vẻ bằng.

Với tiền nên ưu tiên:

- Int64 minor units nếu scale/currency/range phù hợp; hoặc
- Decimal128 + quy tắc rounding/scale rõ ràng.

Java `BigDecimal` ↔ MongoDB Decimal128 cần kiểm mapper/converter và overflow; đừng convert BigDecimal sang `doubleValue()` trước khi lưu.

### 9.5. Overflow int64 và dữ liệu âm

Int64 signed có giới hạn từ \(-2^{63}\) đến \(2^{63}-1\). Một string numeric vượt phạm vi không thể chuyển chính xác sang BSON long. Nên đối soát:

- Số lượng records không parse được.
- Số lượng ngoài khoảng cho phép theo business.
- Negative amounts được phép ở refund/adjustment hay không.
- Tổng theo currency/tenant và kiểu của kết quả aggregate.

Không dùng sentinel `0` cho lỗi parse nếu 0 là một giá trị business hợp lệ.

### 9.6. So giá trị source với target sau canonical convert

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "targets"
    }
  },
  { $unwind: "$targets" },
  {
    $addFields: {
      expectedAmount: {
        $convert: {
          input: "$amount",
          to: "long",
          onError: null,
          onNull: null
        }
      },
      targetType: { $type: "$targets.amountMinor" }
    }
  },
  {
    $match: {
      $expr: {
        $or: [
          { $ne: ["$targetType", "long"] },
          { $eq: ["$expectedAmount", null] },
          { $ne: ["$expectedAmount", "$targets.amountMinor"] }
        ]
      }
    }
  },
  {
    $project: {
      orderNo: 1, tenant: 1,
      sourceAmount: "$amount",
      expectedAmount: 1,
      targetAmount: "$targets.amountMinor",
      targetType: 1
    }
  }
])
~~~

Trong lab, `ORD-1002` sai type và `ORD-2001` sai giá trị. **Điều kiện trong ví dụ là một phép check đầu vào đơn giản**, không tự thay đầy đủ validation về format/rounding/currency. Đặc biệt với BSON numeric type khác nhau, phép so toán học có thể cho kết quả bằng dù raw type khác, vì thế ta **tách `targetType`**.

### 9.7. Đối soát status mapping

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "t"
    }
  },
  { $unwind: "$t" },
  {
    $addFields: {
      expectedStatus: {
        $switch: {
          branches: [
            { case: { $eq: ["$status", "new"] }, then: "OPEN" },
            { case: { $eq: ["$status", "paid"] }, then: "PAID" },
            { case: { $eq: ["$status", "cancelled"] },
              then: "CANCELLED" }
          ],
          default: "__UNMAPPED__"
        }
      }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$expectedStatus", "$t.status"] }
    }
  },
  {
    $project: {
      orderNo: 1,
      sourceStatus: "$status",
      expectedStatus: 1,
      targetStatus: "$t.status"
    }
  }
])
~~~

**Phải kiểm cả source status không nằm trong mapping**, kể cả khi target cũng chứa cùng sentinel. Không dùng `"__UNMAPPED__"` làm trạng thái hợp lệ chỉ để số lượng diff bằng 0.

### 9.8. Rounding và phép so có tolerance

Với tiền ở minor units, nên đối soát **integer exact**. Với số đo sensor có sai số từ thuật toán đã định nghĩa, có thể chấp nhận:

\[
|v_{\mathrm{target}} - v_{\mathrm{expected}}| \le \epsilon
\]

Nhưng \(\epsilon\) phải được business duyệt **theo field/unit/currency/source**, không đặt toàn hệ thống một tolerance chung 0,01 và bỏ qua drift. Với dữ liệu tỷ lệ, có thể dùng absolute + relative tolerance có guard cho denominator 0; test cả giá trị gần 0, âm, cực lớn và overflow.

### 9.9. So thời gian và timezone

MongoDB BSON Date lưu milliseconds từ Unix epoch. Nếu source có Date và target Date, nên so **instant UTC**. Nếu source là local date string không timezone, phải nêu cách gán timezone/DST ambiguity. Trường `createdAt` không được dịch thêm 7 giờ chỉ vì ứng dụng chạy ở Việt Nam.

### 9.10. Arrays: set hay sequence?

~~~json
// Hai arrays cùng phần tử nhưng thứ tự khác:
{"tags": ["a", "b"]}
{"tags": ["b", "a"]}
~~~

Nếu tags là **set semantic**, có thể canonicalize bằng sort+deduplicate. Nếu `items` có `lineNumber` và thứ tự hiển thị quan trọng, không được sort bừa rồi gọi hai orders tương đương. Mapping contract phải định nghĩa **order-sensitive** hoặc **order-insensitive**, cách xử lý duplicates và nested field defaults.

### 9.11. Trường đã bị drop cần điều kiện

Nếu schema v2 bỏ `legacyNotes` vì “không sử dụng”, phải kiểm có dữ liệu không rỗng, có yêu cầu audit/legal retention không. “Không map sang target” chỉ hợp lệ khi policy cho phép. Một quy tắc drop an toàn:

~~~text
Drop allowed if:
  field is deprecated AND
  no current business consumer AND
  retention policy allows omission AND
  migration manifest records decision.
~~~

Không lặng lẽ mất các fields chưa biết do serializer `ignoreUnknownProperties` rồi coi convert thành công.

## 10. Ràng buộc kỹ thuật: `$jsonSchema`, unique index và phiên bản schema

MongoDB có **document validation** và indexes để cưỡng chế một phần invariants tại storage layer. Nhưng validators/indexes **không thay thế đối soát dữ liệu lịch sử**, và những ràng buộc nghiệp vụ xuyên collections thường phải kiểm ở ứng dụng/aggregation.

### 10.1. Ví dụ validator schema v2

Trên **collection mới của lab** sau khi đã làm sạch fixture (hoặc một collection test khác), có thể định nghĩa:

~~~javascript
db.createCollection("orders_v2_validated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "orderNo", "customerId",
        "status", "amountMinor", "createdAt", "schemaVersion"
      ],
      properties: {
        _id: { bsonType: "string" },
        tenantId: { bsonType: "string", minLength: 1 },
        orderNo: { bsonType: "string", minLength: 1 },
        customerId: { bsonType: "string" },
        status: {
          enum: ["OPEN", "PAID", "CANCELLED"]
        },
        amountMinor: { bsonType: "long", minimum: 0 },
        createdAt: { bsonType: "date" },
        schemaVersion: { bsonType: "int", enum: [2] },
        items: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["sku", "quantity", "unitPriceMinor"],
            properties: {
              sku: { bsonType: "string" },
              quantity: { bsonType: "int", minimum: 1 },
              unitPriceMinor: { bsonType: "long", minimum: 0 }
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

**Đây là validator cho mô hình lab**, không phải schema chung mọi hệ thống. Nếu `items` phải luôn tồn tại và non-empty, thêm `items` vào `required` và dùng `minItems:1` theo supported JSON Schema keyword/version. Nếu refund cho phép negative amount, không dùng `minimum:0` chung cho mọi transaction.

### 10.2. `required` và `bsonType` là hai điều kiện

~~~javascript
required: ["amountMinor"],
properties: {
  amountMinor: { bsonType: "long" }
}
~~~

`required` bắt buộc field hiện diện; `bsonType:"long"` yêu cầu value có kiểu long. Nếu chỉ có `bsonType` nhưng field không có trong `required`, missing field có thể vẫn hợp lệ. Nếu chỉ required mà không kiểm BSON type, `"1000"` string có thể lọt qua.

### 10.3. Thay đổi validator bằng `collMod`

~~~javascript
db.runCommand({
  collMod: "orders_v2_validated",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "orderNo", "amountMinor"],
      properties: {
        tenantId: { bsonType: "string" },
        orderNo: { bsonType: "string" },
        amountMinor: { bsonType: "long" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Chỉ minh họa cú pháp cập nhật validator trên **collection lab**. Lệnh này thay validator hiện có bằng rule mới, **không phải phép merge từng field**, nên nếu dùng trên production có thể vô tình bỏ ràng buộc cũ. Cần versioned schema change, review và rollback plan.

### 10.4. `validationLevel` và `validationAction`

| Tùy chọn | Ý nghĩa thực hành |
|---|---|
| `validationLevel:"strict"` | Kiểm các inserts/updates thuộc phạm vi validation theo rule. |
| `validationLevel:"moderate"` | Một số updates lên documents đã không hợp lệ trước đó có thể không bị validate như documents hợp lệ; cần hiểu chính xác docs. |
| `validationAction:"warn"` | Cho phép một số writes không đạt validator nhưng log warning; hữu ích trong rollout quan sát. |
| `validationAction:"error"` | Từ chối writes không hợp lệ theo rule, trừ khi được phép bypass. |

Khi đổi validator, **MongoDB không tự sửa hoặc quét rồi xóa mọi document lịch sử không hợp lệ**. Cần chủ động dùng **`$jsonSchema` matching/đối soát toàn collection** để tìm và remediate dữ liệu cũ trước khi siết strict/error.

### 10.5. Tìm documents không phù hợp validator

~~~javascript
const v2Schema = {
  bsonType: "object",
  required: ["tenantId", "orderNo", "amountMinor"],
  properties: {
    tenantId: { bsonType: "string" },
    orderNo: { bsonType: "string" },
    amountMinor: { bsonType: "long" }
  }
}

lab.orders_v2.find({
  $nor: [{ $jsonSchema: v2Schema }]
}, { tenantId: 1, orderNo: 1, amountMinor: 1 })
~~~

Với rule tối giản này, `ORD-1002` sai type. Ở production nên dùng **cùng một definition versioned** giữa validator rollout và đối soát; nhưng đừng tưởng một schema rule ngắn bao trùm toàn bộ business invariants.

### 10.6. Unique business key

~~~javascript
// Chỉ thực hiện trên collection sạch/được phép.
lab.orders_v2.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uniq_tenant_orderNo" }
)
~~~

Unique index kiểm uniqueness theo **key + collation/index semantics**, không tự kiểm rằng `orderNo` đúng format hoặc thuộc đúng tenant. Nếu collection hiện có duplicates, build unique index có thể fail; **đếm/giải quyết duplicates trước**.

### 10.7. Missing/null với unique index

Một unique single-field index có semantics đặc biệt với documents thiếu field hoặc có null; các values có thể được index theo null-like key và gây duplicate key conflict. Compound unique cũng cần xét combinations of missing/null values. **Không suy unique index tự bắt mọi required-field validation**. Phải kết hợp `required`/BSON type validation và index.

### 10.8. Partial unique index

Nếu chỉ yêu cầu unique với records active:

~~~javascript
lab.orders_v2.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uniq_active_tenant_orderNo",
    partialFilterExpression: { isActive: true }
  }
)
~~~

Đây là **một alternative design**, không tạo cùng lúc với unique index toàn collection rồi kỳ vọng partial index thay nó. Business phải định nghĩa rõ `isActive` có tồn tại và bool đúng trên mọi active record. Partial index chỉ bao gồm documents **khớp filter**, nên một document thiếu `isActive` có thể nằm ngoài uniqueness enforcement của index đó. Đối soát phải kiểm missing/invalid flags và scope.

### 10.9. Unique index và sharding

Trong sharded collections, unique index guarantees có **ràng buộc liên quan shard key prefix** và kiểu sharding/version. Không tạo một unique index arbitrary trên vài shards rồi kết luận uniqueness toàn cluster được bảo đảm. Xác minh sharded-cluster docs, shard key design và business key trước migration.

### 10.10. Enforce tuần tự, không siết đột ngột

Một quy trình khả thi:

~~~text
Observe existing shape/types
        |
        v
Report invalid source records
        |
        v
Backfill and fix target data
        |
        v
Reconcile exact required/unique fields
        |
        v
Create indexes and introduce validator warn
        |
        v
Monitor new writes / exceptions
        |
        v
Switch to validator strict/error after approval
~~~

Không để `warn` vĩnh viễn rồi tuyên bố schema được enforce; cũng không bật `error` trước khi app/consumers cũ tương thích, làm writes production thất bại hàng loạt.

## 11. Đối soát quan hệ giữa collections và ràng buộc ngầm

MongoDB không tự cung cấp foreign-key constraint giống RDBMS theo mặc định. Nếu `orders.customerId` tham chiếu `customers._id`, ứng dụng phải quyết định liệu một dangling reference có hợp lệ trong retention, soft delete, tenant isolation hay không.

### 11.1. Tạo customer fixture có kiểm soát

Trên cùng database lab:

~~~javascript
lab.customers_v2.insertMany([
  { _id: "C-001", tenantId: "tenant-a", active: true },
  { _id: "C-002", tenantId: "tenant-a", active: true },
  { _id: "C-003", tenantId: "tenant-b", active: true },
  { _id: "C-004", tenantId: "tenant-b", active: false }
])

lab.customers_v2.createIndex({ tenantId: 1, _id: 1 })
~~~

Với dữ liệu cố ý này, `ORD-ORPHAN.customerId="C-999"` không có customer tương ứng. **Không** tự xác nhận mọi archived order bắt buộc tham chiếu tới current customer: nếu hệ thống cho phép xóa khách hàng theo privacy policy, phải định nghĩa retention/anonymization semantics trước.

### 11.2. Tìm dangling customer reference

~~~javascript
lab.orders_v2.aggregate([
  {
    $lookup: {
      from: "customers_v2",
      localField: "customerId",
      foreignField: "_id",
      as: "customerMatches"
    }
  },
  {
    $match: {
      $expr: {
        $eq: [{ $size: "$customerMatches" }, 0]
      }
    }
  },
  {
    $project: {
      tenantId: 1, orderNo: 1, customerId: 1,
      reason: { $literal: "MISSING_CUSTOMER" }
    }
  }
])
~~~

`$lookup` từ `orders_v2` sang `customers_v2` trong **cùng database**. Nếu references dùng composite key (tenantId+customerId), lookup theo `customerId` đơn lẻ có thể match **customer ở tenant khác**, che lỗ hổng isolation.

### 11.3. Kiểm match đúng tenant

~~~javascript
lab.orders_v2.aggregate([
  {
    $lookup: {
      from: "customers_v2",
      let: {
        cid: "$customerId",
        tid: "$tenantId"
      },
      pipeline: [
        { $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$cid"] },
                { $eq: ["$tenantId", "$$tid"] }
              ]
            }
        }}
      ],
      as: "validCustomer"
    }
  },
  {
    $match: {
      $expr: { $eq: [{ $size: "$validCustomer" }, 0] }
    }
  },
  { $project: { orderNo: 1, tenantId: 1, customerId: 1 } }
])
~~~

Đây là kiểm existence và **tenant consistency**, không kiểm status active/inactive. Nếu đơn cũ được phép tham chiếu khách hàng inactive, thêm `active:true` sẽ tạo false positives. Nếu customer IDs chỉ unique trong tenant (không global), schema source/target cũng cần thiết kế khóa ghép chính xác, không chỉ `_id`.

### 11.4. Kiểm quan hệ một-nhiều

Các quan hệ thường gặp:

- Order → orderItems: mọi item phải thuộc một order hợp lệ.
- Customer → addresses: addresses không trỏ tenant khác.
- Payment → order: mỗi captured payment thuộc order phù hợp, amounts/currency match.
- Invoice → order: một invoice number không map nhiều orders sai quy tắc.
- User → roles: quyền mới không rộng hơn quyền cũ.

Với mối quan hệ nhiều-nhiều hoặc embedded documents, đôi khi cần **unwind + group** trước khi đối soát; không giả sử mỗi `$lookup` match một document.

### 11.5. Referential integrity và xử lý delete

Nếu source soft-delete customer, target có thể giữ order nhưng anonymize thông tin cá nhân. “Mọi order phải có customer record” có thể sai về privacy compliance. Cần tách:

1. **Active order** phải có active customer?
2. **Historical order** có thể giữ hashed/tombstone customer?
3. Sau quyền yêu cầu xóa dữ liệu, trường nào phải bị xóa/masked?
4. Quản lý orphan có timestamp và reason code không?

Đối soát kiểm đúng **policy** từng lớp dữ liệu, không tự dùng một foreign-key rule cho mọi trạng thái.

### 11.6. Embedded và referenced model đổi qua migration

Nếu v1 nhúng `order.items[]` còn v2 tách `order_items`:

~~~text
source orders_v1:
  1 order, 3 embedded items

target:
  orders_v2: 1 order
  order_items_v2: 3 documents
~~~

Không so total document count của nguồn với tổng hai collections đích. Phải so **entity count**:

- Order count = số orders duy nhất.
- Item count = tổng `$size(items)` theo order nguồn.
- Target item count = số item documents thuộc cùng orders.
- Sum quantity/amount theo order phải bằng nhau.

Đây là lý do **cardinality contract** phải nằm trong mapping specification.

### 11.7. Unique constraint không chứng minh reference đúng

Một `order_items` row có unique (orderId,lineNo) nhưng `orderId` trỏ order không tồn tại vẫn có thể qua unique index. Dùng join/invariant kiểm orphans; kết hợp application validation/transaction khi dữ liệu cần atomicity.

### 11.8. Dữ liệu thuộc tenant khác là lỗi bảo mật

Một migration có thể copy đúng count và đúng amount nhưng gán `tenantId` khác. Đây là **security defect**, ưu tiên cao hơn “khác biệt báo cáo số lượng 0,1%”. Đặt:

~~~text
Cross-tenant reference mismatch = CRITICAL
Source record assigned wrong tenant = CRITICAL
~~~

Với dữ liệu nhạy cảm, không phát tán raw document trong exception report; chỉ lưu khóa đã masking/hash và metadata cần điều tra dưới quyền phù hợp.

## 12. Đối soát kết quả nghiệp vụ: số dư, tổng tiền, trạng thái

### 12.1. Đừng so tổng `amount` khi chưa thống nhất semantics

Tổng `amountMinor` trên **tất cả orders** không nhất thiết bằng **doanh thu**. Đơn `CANCELLED` có thể vẫn có gross order amount, nhưng không tạo recognized revenue. Refund có thể là negative cash flow hoặc separate transaction. Trước khi tạo aggregate, business phải định nghĩa:

| Metric | Scope chính xác |
|---|---|
| Gross order amount | Tổng line-item price trước discount/tax/shipping theo policy. |
| Net payable | Gross - discounts + tax + shipping. |
| Paid amount | Payments captured/settled theo time/currency policy. |
| Net revenue | Recognized revenue theo accounting rules, không đồng nhất paid orders. |
| Refund amount | Refunds thực hiện, thời điểm và sign convention. |
| Inventory balance | Opening + receipts - shipments + returns + adjustments. |
| Account balance | Opening balance + signed ledger movements. |

**Đối soát sai định nghĩa metric còn nguy hiểm hơn không đối soát**, vì có thể chấp nhận hai kết quả cùng sai.

### 12.2. Total amount theo tenant sau normalize source

~~~javascript
lab.orders_v1.aggregate([
  {
    $project: {
      tenantId: "$tenant",
      amountLong: {
        $convert: {
          input: "$amount",
          to: "long",
          onError: null,
          onNull: null
        }
      },
      rawType: { $type: "$amount" }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      totalAmountMinor: { $sum: "$amountLong" },
      count: { $sum: 1 },
      invalidConversionCount: {
        $sum: {
          $cond: [
            { $eq: ["$amountLong", null] }, 1, 0
          ]
        }
      }
    }
  }
])
~~~

Nếu invalidConversionCount khác 0, **không dùng totalAmountMinor làm kết quả PASS** vì `$sum` không tính các null. Tạo exception report trước rồi chỉ so totals của cùng scope sau khi nguồn được chuẩn hóa hợp lệ.

### 12.3. Total amount đích nhưng phải kiểm type riêng

~~~javascript
lab.orders_v2.aggregate([
  {
    $group: {
      _id: "$tenantId",
      totalAmountMinor: { $sum: "$amountMinor" },
      count: { $sum: 1 },
      invalidTypeCount: {
        $sum: {
          $cond: [
            { $ne: [{ $type: "$amountMinor" }, "long"] },
            1, 0
          ]
        }
      }
    }
  }
])
~~~

MongoDB `$sum` accumulator bỏ qua các values không phải numeric trong `$group`. Vì vậy **một string amount có thể làm tổng giảm thay vì ném lỗi**. Đối soát phải đồng thời có `invalidTypeCount` và exact value checks, không chỉ so aggregate sum.

### 12.4. Ví dụ tổng sai dù số lượng bằng nhau

Trong fixture:

| Tenant | Source amount sau parse | Target `$sum` theo typed values | Tình trạng |
|---|---:|---:|---|
| tenant-a | 175.000 | 125.500 | Sai vì amount string bị bỏ qua và có extra order 500. |
| tenant-b | 70.000 | 3.000 | Sai vì order missing và value 3.000 thay 30.000. |
| **Tổng** | **245.000** | **128.500** | Không đạt. |

Các số trong bảng dựa trên fixture được định nghĩa ở phần lab, **không phải kết quả đã chạy trên MongoDB thật**. Nếu business chỉ tính paid orders, phải áp cùng trạng thái normalized `PAID` ở cả hai phía và nhận một bảng khác.

### 12.5. Kiểm invariant dòng hàng = tổng order

Với **mô hình ví dụ không có tax/discount/shipping**, giả sử:

\[
\text{order.amountMinor}
=\sum_{i=1}^{n}\text{items}[i].\text{quantity}
\times\text{items}[i].\text{unitPriceMinor}
\]

Trước tiên phải kiểm `items` là array hợp lệ, mọi `quantity` numeric integer và `unitPriceMinor` long. Với các documents có đúng kiểu:

~~~javascript
lab.orders_v2.aggregate([
  {
    $match: {
      $expr: {
        $and: [
          { $isArray: "$items" },
          { $eq: [{ $type: "$amountMinor" }, "long"] }
        ]
      }
    }
  },
  {
    $addFields: {
      itemTotal: {
        $reduce: {
          input: "$items",
          initialValue: NumberLong("0"),
          in: {
            $add: [
              "$$value",
              { $multiply: [
                  "$$this.quantity",
                  "$$this.unitPriceMinor"
              ]}
            ]
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$itemTotal", "$amountMinor"] }
    }
  },
  {
    $project: {
      orderNo: 1,
      amountMinor: 1,
      itemTotal: 1
    }
  }
])
~~~

Pipeline này **chỉ áp lên records có items array và amount long**. Nó **không** thay các checks tìm thiếu items, phần tử sai type hoặc overflow; nếu `items` là array malformed, phép multiply có thể lỗi. Trong production, cần profile dữ liệu trước hoặc dùng guarded conversion/error reporting. Đối với tiền, nên đối soát từng line item theo int64/Decimal128 và test overflow nếu lượng lớn.

### 12.6. So tổng trên cùng scope/state/currency

Không được cộng VND và USD rồi so một số duy nhất. Partition theo `currency`, tenant, ledger date, status:

~~~text
key = (tenantId, currency, recognizedDate, statusCategory)
sourceTotalMinor(key) == targetTotalMinor(key)
sourceCount(key) == targetCount(key)
~~~

Nếu có currency exchange, phải dùng cùng tỷ giá tại cùng thời điểm và rounding policy. Không so total converted USD ở target với raw VND ở source khi không có conversion contract.

### 12.7. Ledger là nơi cần exact checks

Giả sử mỗi ledger entry lưu `deltaMinor` signed, còn account có openingBalance. Invariant:

\[
\text{ClosingBalance}_{a}
=\text{OpeningBalance}_{a}
+\sum_{e\in a}\text{deltaMinor}_e
\]

Đối với chuyển tiền giữa hai accounts:

\[
\sum_{e\in \text{transferId}}\text{deltaMinor}_e=0
\]

Đây là mô hình **double-entry** đơn giản, giả định không có phí/ngoại tệ; production phải điều chỉnh cho hệ thống kế toán cụ thể.

### 12.8. Lab ledger để đối soát

~~~javascript
lab.ledger_v2.insertMany([
  {
    _id: "T1:A", transferId: "T1",
    accountId: "A", tenantId: "tenant-a",
    deltaMinor: NumberLong("-30000")
  },
  {
    _id: "T1:B", transferId: "T1",
    accountId: "B", tenantId: "tenant-a",
    deltaMinor: NumberLong("30000")
  },
  {
    _id: "T2:A", transferId: "T2",
    accountId: "A", tenantId: "tenant-a",
    deltaMinor: NumberLong("-10000")
  },
  {
    _id: "T2:B", transferId: "T2",
    accountId: "B", tenantId: "tenant-a",
    deltaMinor: NumberLong("9000") // sai 1000
  }
])
~~~

Kiểm mỗi transfer cân bằng:

~~~javascript
lab.ledger_v2.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        transferId: "$transferId"
      },
      netDeltaMinor: { $sum: "$deltaMinor" },
      nEntries: { $sum: 1 }
    }
  },
  {
    $match: {
      $or: [
        { netDeltaMinor: { $ne: 0 } },
        { nEntries: { $ne: 2 } }
      ]
    }
  }
])
~~~

Theo fixture, `T2` lệch −1.000. Check `nEntries=2` là quy tắc **chỉ của lab**, không phải mọi ledger đều có hai postings (có thể nhiều accounts/fees/taxes). Quan trọng là định nghĩa **cân bằng theo currency + transferId + tenant** và kiểm types/identities trước `$sum`.

### 12.9. Không cho phép lỗi hai phía tự triệt tiêu

Một ledger có một entry +1000 sai và một entry −1000 sai trong cùng group vẫn có net 0. Cần thêm:

- Tập keys entries matching nguồn/đích.
- Count debit/credit legs theo contract.
- Account IDs/tenant/currency đúng.
- Amount per leg, not only total.
- Duplicate transferId/leg ID và sequence rules.

**Aggregate totals là điều kiện cần, không phải điều kiện đủ.**

### 12.10. Inventory

Một stock balance có thể phải thỏa:

\[
\mathrm{stockEnd}
=\mathrm{stockStart}
+\mathrm{receipts}
-\mathrm{shipments}
+\mathrm{returns}
+\mathrm{adjustments}
\]

Nhưng có thể có backorders/negative inventory theo business. Nếu migration đổi inventory snapshots sang event sourcing, kiểm **snapshot+event replay result** tại cùng watermark và theo SKU/warehouse/tenant; không chỉ đếm số event documents.

### 12.11. Workflow/status invariant

Ví dụ một order `PAID` phải có payment captured record, một order `CANCELLED` không được tiếp tục nhận fulfillment event sau cancel (trừ reversal rules). Khi đổi enum, đối soát:

- State count theo tenant/time.
- State transition lịch sử hợp lệ.
- Related payment/fulfillment rows.
- Business dashboards mà khách hàng đang dùng.

Nếu migration chỉ giữ **trạng thái cuối cùng**, không thể chứng minh lịch sử transition chưa mất từ snapshot hiện tại. Muốn kiểm lịch sử phải giữ event/audit logs và event identity.

### 12.12. Privacy/business outcome

Một migration có thể bảo toàn mọi giá trị thô nhưng **vi phạm yêu cầu xóa dữ liệu cá nhân**, vì target vẫn giữ field đã phải anonymize. Business reconciliation phải bao gồm **quyền dữ liệu, retention, masking và data residency**, không chỉ tiền và count.

## 13. Chuẩn hóa để so hai schema: canonical representation

Nếu hai schemas khác nhau về tên trường, kiểu ID hoặc status label, cần biến đổi cả hai về **cùng một biểu diễn logic** trước khi so giá trị.

### 13.1. Canonical order hợp đồng v2

Với `ORD-1001`, canonical form có thể là:

~~~json
{
  "entityKey": ["tenant-a", "ORD-1001"],
  "tenantId": "tenant-a",
  "customerId": "C-001",
  "status": "OPEN",
  "amountMinor": "125000",
  "createdAt": "2026-10-01T08:00:00.000Z",
  "items": [
    ["SKU-01", "2", "50000"],
    ["SKU-02", "1", "25000"]
  ]
}
~~~

Ở đây `amountMinor` được biểu diễn dạng **decimal string chuẩn hóa** để hai languages có thể so chính xác int64 mà không mất precision do JavaScript Number; `createdAt` được chuẩn về **UTC ISO instant với milliseconds cố định**. Canonical form **không phải** schema MongoDB đích bắt buộc, mà là định dạng đối soát nội bộ chứa các fields có ý nghĩa business theo mapping contract.

### 13.2. Một hợp đồng canonical phải nêu

1. **Trường nào giữ/đổi tên/derive/drop** và lý do.
2. **Key encoding**: không ghép tùy tiện bằng delimiter có thể collision.
3. **Type normalization**: int32 → int64 có cho phép không; tiền long hay decimal; dates epochMs.
4. **Null/missing rules**: có khác nhau không, default có hợp lệ không.
5. **Unicode/case/collation**: giữ nguyên hay NFKC/trim/case fold có policy.
6. **Arrays**: list có thứ tự hay set/multiset không thứ tự, duplicates có ý nghĩa không.
7. **Nested objects**: field order không có ý nghĩa hay có consumer dựa raw bytes.
8. **Unknown fields**: được drop theo whitelist hay là exception.
9. **Numeric precision/rounding**: exact vs tolerance theo field.
10. **Version** của contract và hàm canonicalization; mỗi reconciliation run ghi version.

### 13.3. Phân biệt null, missing và default

~~~text
source: field missing
target: field = null
~~~

Nếu contract ghi **missing ≠ explicit null**, canonical form phải giữ tag `MISSING` và `NULL` riêng. Nếu contract cho phép default null từ missing, chênh lệch này có thể intentional; nhưng phải ghi rõ vì thay đổi có thể ảnh hưởng query, index và application serialization.

### 13.4. Sắp xếp arrays đúng nghĩa

Nếu `items` có `lineNumber`, thứ tự có thể được xác định theo lineNumber. Nếu target đã reorder items nhưng vẫn giữ đúng lineNumber, canonicalize bằng sort theo lineNumber **chỉ khi contract định nghĩa như vậy**. Với tags là set, có thể sort/deduplicate; với ledger postings, duplicates có thể có nghĩa và không được deduplicate.

### 13.5. Mẫu Java canonicalization ở mức thiết kế

~~~java
record CanonicalItem(
    String sku,
    long quantity,
    long unitPriceMinor) {}

record CanonicalOrder(
    String tenantId,
    String orderNo,
    String customerId,
    String normalizedStatus,
    long amountMinor,
    java.time.Instant createdAt,
    java.util.List<CanonicalItem> items) {}

// Hai adapters dùng cùng contract nhưng input schema khác nhau:
CanonicalOrder fromLegacy(org.bson.Document legacy);
CanonicalOrder fromTarget(org.bson.Document target);
~~~

Hai hàm phải trả **cùng object** cho data tương đương; cần parse fields theo contract và reject invalid values. Không tự tính source/target bằng đúng một hàm migration bị lỗi rồi xem equality là bằng chứng đủ: **bug chung** có thể làm cả hai bên so khớp sai.

### 13.6. Không dùng thứ tự BSON fields để so semantic equality

Hai BSON documents có thể khác raw bytes do field order, numeric BSON type hoặc serializer version. Nếu business chỉ quan tâm tập fields/value, cần canonical order ổn định. Raw `JSON.stringify` của hai JavaScript objects cũng không được coi là equality oracle khi property ordering/undefined handling khác. 

### 13.7. Kiểm độc lập ngoài canonical compare

Ví dụ converter nguồn và converter đích đều dùng bug “chia amount cho 10”, hai canonical objects có thể vẫn bằng nhau. Cần **invariants độc lập**: gross order amount = line items, balances = ledger, state mapping đúng, timestamp giữ UTC instant, cardinality/keys không đổi. Canonical equality mạnh hơn raw compare, nhưng không thay business checks.

## 14. Hash/checksum để khoanh vùng sai lệch

### 14.1. Tại sao không hash raw BSON trực tiếp?

Hai document có cùng ý nghĩa business có thể khác `_id`, tên field, status labels, raw string/long type sau transform, metadata intentional. Hash raw BSON/JSON có thể báo mismatch giả. Cần **canonicalize theo contract** rồi hash, và dùng cùng encoding/version ở cả hai phía.

### 14.2. Xây hash cho từng record

~~~text
Source doc                          Target doc
    |                                   |
    v                                   v
Canonicalize v1                     Canonicalize v2
    |                                   |
    v                                   v
Deterministic encoding             Same encoding/version
    |                                   |
    v                                   v
SHA-256 fingerprint                SHA-256 fingerprint
    |                                   |
    +---------- compare by stable key --+
~~~

So hash theo **immutable entity key** và snapshot/watermark. Nếu mismatch, fetch data có quyền và tạo **field-level diff**. Hash là công cụ triage, không thay validation về keys/counts/relations/business.

### 14.3. Deterministic encoding cần định nghĩa chặt

~~~text
reconcile-contract-version: 3
record:
  for each field in sorted canonical name order:
    nameLength + UTF-8 name
    explicit type tag
    valueLength + value bytes
  arrays:
    element count + elements in business-defined order
  null: explicit NULL tag
  missing: explicit MISSING tag if semantically distinct
~~~

Đừng nối `tenantId + orderNo + amount` không có độ dài/tags; `("ab","c")` và `("a","bc")` cùng thành `"abc"`. Với Java có thể dùng `MessageDigest.getInstance("SHA-256")` trên encoding chuẩn; **hash không tự chuẩn hóa dữ liệu**.

### 14.4. Hash bằng nhau có chứng minh tuyệt đối?

Hash hữu hạn vẫn có khả năng collision về lý thuyết; SHA-256 được thiết kế để collision cực khó. Tuy nhiên, lỗi lớn nhất trong thực tế thường là **sai normalization, quên field hoặc so dữ liệu khác thời điểm**. Với tiền và quyền, vẫn cần exact business checks và kiểm field-level những partitions quan trọng.

### 14.5. Hash theo partition

~~~text
Partition by (tenantId, month, key-range)
  |
  +-- source count and sorted canonical fingerprints
  +-- target count and sorted canonical fingerprints
  |
  v
Deterministic partition checksum
  |
  +-- equal => likely identical under contract
  |
  +-- mismatch => drill down to key and field diffs
~~~

Đừng xây partition hash bằng cách nối records theo **collection natural order**, vì MongoDB không đảm bảo natural order ổn định. Phải sort theo deterministic key hoặc dùng commutative aggregation có phân tích collision/cancellation rõ; tốt nhất là sorted merge.

### 14.6. Merkle tree cho dữ liệu cực lớn

~~~text
               ROOT HASH
               /       \
           Range A     Range B
           /   \       /    \
         A1     A2   B1      B2
~~~

So root rồi drill xuống branches khác. Nhưng phải bảo đảm boundaries, record ordering, snapshot và hash schema version đồng bộ. Nếu một record bị map vào **khác partition do key sai**, cần quay lại kiểm key mapping trước.

### 14.7. Checksums không thay báo cáo exception

Hash mismatch chỉ nói có khác biệt, không giải thích **lỗi nào**. Reconciliation report cần key/partition, expected/actual canonical field hashes, diff code, severity, source snapshot/watermark và link remediation ticket. Không log PII/credentials ra báo cáo chia sẻ rộng rãi.

### 14.8. Tránh memory spike

Không dùng `collection.find().toArray()` cho hàng TB. Dùng indexed cursor/key-range, streaming hash, memory budget, batch limit và throttle. Một checksum job làm DB CPU/IOPS saturated có thể phá SLO; kiểm `explain("executionStats")` và vận hành tại thời điểm được phép.

## 15. Đối soát dữ liệu lớn: streaming merge join và phân vùng

`$lookup` thuận tiện nếu hai collections cùng database và có index. Nhưng migration source→target có thể ở **hai clusters**, rất lớn hoặc khác quyền truy cập, khi đó nên dùng **reconciliation service** không nạp tất cả docs vào RAM.

### 15.1. Streaming merge join hai nguồn đã sort

Giả sử hai readers đều phát dòng:

~~~text
CanonicalKey(tenantId, orderNo) | canonicalFingerprint | version
~~~

Đã sort tăng theo khóa:

~~~text
Source                           Target
("a","001"), h1                  ("a","001"), h1
("a","002"), h2                  ("a","003"), hX
("a","004"), h4                  ("a","004"), hY
~~~

Thuật toán:

~~~text
while source.hasRow and target.hasRow:
    if source.key < target.key:
        emit MISSING_TARGET(source)
        advance source
    else if source.key > target.key:
        emit EXTRA_TARGET(target)
        advance target
    else:
        if hash/source-values differ:
            emit VALUE_DIFF(source,target)
        advance both

emit remaining source rows as MISSING_TARGET
emit remaining target rows as EXTRA_TARGET
~~~

Nếu mỗi reader có stream đã sort theo cùng **canonical key/collation**, memory gần \(O(1)\) theo số hàng trong cursor buffers, còn CPU đối soát \(O(N+M)\) **không tính chi phí sort**. Với MongoDB, phải có index/sort plan phù hợp; nếu server phải sort lớn thì I/O/memory vẫn đắt.

### 15.2. Duplicates phải phát hiện trước khi merge

Nếu source hoặc target có hai rows cùng key, thuật toán một-một đơn giản có thể sinh kết luận sai. Thay vì chỉ so từng row, reader cần:

- Group adjacent identical keys thành run.
- Nếu cardinality > expected, emit `DUPLICATE_SOURCE`/`DUPLICATE_TARGET`.
- So multiple records theo domain contract (nếu một-một thì fail).
- Không chọn một record ngẫu nhiên để “bỏ duplicate” rồi đánh dấu PASS.

### 15.3. Partition theo key range

~~~text
Reconcile Run 2026-11-14
  Partition 00: tenant-a, IDs A000-A999
  Partition 01: tenant-a, IDs B000-B999
  Partition 02: tenant-b, IDs A000-A999
  ...
~~~

Partition boundary phải **stable, không overlap và không có gap**. Không dùng các partitions theo `skip/limit` offset trong collection đang ghi vì inserts/deletes làm pages dịch chuyển. Dùng **keyset/range filters** theo immutable indexed key hoặc snapshot cut.

### 15.4. Retry chỉ partition lỗi

Khi partition #17 thất bại do network:

1. Giữ manifest/run ID/mappingVersion/snapshot cut.
2. Ghi trạng thái `FAILED_RETRYABLE` và error reason.
3. Retry đúng partition với cùng mốc/canonical rules, bounded attempts/backoff.
4. Không merge kết quả của hai snapshots khác nhau vào một PASS.
5. Nếu snapshot/watermark không còn duy trì được, chạy lại theo recovery plan thay vì tiếp tục bằng dữ liệu khác thời điểm.

### 15.5. Đừng lấy consistency bằng `readPreference=secondary` tự động

Đọc secondary có thể giảm tải primary, nhưng **replication lag và sự khác biệt giữa nodes** làm baseline không còn cùng mốc nếu không có snapshot/optime coordination. Với reconciliation critical, đọc qua phương thức đáp ứng consistency contract trước rồi mới tối ưu read routing.

### 15.6. Bảo vệ database khỏi reconciliation job

Giới hạn:

- Số partitions active và queries đồng thời.
- Cursor batch size, max duration, retry attempts.
- `maxTimeMS`/client deadline theo operation.
- CPU/IOPS/network budgets trong maintenance window.
- Chỉ index được hỗ trợ; tránh `COLLSCAN` toàn cluster bất ngờ.
- Pause/resume khi production latency/replication lag vượt ngưỡng.

**Đối soát cũng là workload**: một job quá hung hãn có thể làm hệ thống production kém ổn định, khiến nguồn và đích tiếp tục drift vì retries.

### 15.7. Sampling có phân tầng

Nếu business cho phép sampling với dữ liệu không critical:

~~~text
Stratify by:
  tenant size
  migration transform type
  schema version
  date range
  rare enum values
  known malformed source groups
~~~

Lấy 1% ngẫu nhiên trên toàn collection thường bỏ qua những trường hợp rất hiếm nhưng rủi ro cao. Nên **oversample các groups mới, ít gặp, nhiều convert hoặc từng có errors**, và ghi rõ confidence/coverage. Không dùng sample PASS để miễn kiểm mọi payments/permissions.

### 15.8. So kết quả query sử dụng thật

Ngoài document diff, chạy **dual-read/shadow query** cùng tham số được phép:

~~~text
query: listPaidOrders(tenant, dateRange)
source adapter -> canonical result
target adapter -> canonical result
compare IDs/order/totals and latency
~~~

Shadow reads không nên tạo side effects; sampling có quyền/PII masking, consistent cut khi cần. Query results có thể khác do writes đang chạy, sort không stable hoặc search index lag, nên khi diff phải có **watermark và query semantics** trước khi kết luận defect.

## 16. Đối soát trong migration online: backfill + CDC

### 16.1. Trạng thái migration

Một workflow online thực tế:

~~~text
PREPARE
   |
   v
BASELINE / SNAPSHOT T0
   |
   v
BACKFILL historical partitions
   |
   v
CAPTURE/APPLY CDC since T0
   |
   v
SHADOW READ + CONTINUOUS RECONCILIATION
   |
   v
CATCH-UP / VERIFIED WATERMARK T1
   |
   v
FREEZE OR COORDINATE FINAL WRITES
   |
   v
FINAL EXACT RECONCILIATION
   |
   +-- FAIL -> repair/rollback/hold
   |
   +-- PASS -> CUTOVER
                   |
                   v
              MONITOR/ROLLBACK WINDOW
~~~

Không bắt đầu CDC **sau** backfill mà không có cách replay writes phát sinh trong khoảng quét lịch sử; có thể mất records thay đổi giữa snapshot và CDC start.

### 16.2. Xử lý insert, update, replace, delete

| Event type | Target action theo contract | Check cần có |
|---|---|---|
| Insert | Canonical convert + deterministic upsert. | Một target key, đúng tenant/type. |
| Update | Convert current state hoặc patch version-aware. | Không overwrite event mới bằng event cũ. |
| Replace | Recompute target fields từ full replacement. | Không giữ stale fields đã bị remove. |
| Delete | Delete/tombstone/archive theo policy. | Không còn extra target record. |
| DDL/rename/drop | Theo runbook hỗ trợ hoặc halt. | Không âm thầm bỏ sót namespace. |

MongoDB change streams cung cấp `resume token` và change events tùy options; **không mặc định mỗi update event luôn chứa toàn document sau update**. Nếu cần fullDocument lookup, đọc docs về `fullDocument`, race với thay đổi tiếp theo và retention. CDC consumer phải định nghĩa cách tái tạo **trạng thái cuối đúng version**.

### 16.3. Idempotent apply

Một event có thể được xử lý lại khi crash trước checkpoint:

~~~text
Apply event E100 to target
Target write succeeds
Process crashes before recording E100 checkpoint
Restart resumes at E100
Event E100 delivered again
~~~

Muốn an toàn:

- Deterministic target `_id`/business key.
- Idempotent upsert theo version/sequence.
- Checkpoint chỉ sau apply durable theo policy.
- Không tạo child docs/side effects trùng khi replay.
- Duplicate key errors được phân loại, không coi mọi E11000 là success.

### 16.4. Ordering và stale events

Nếu record có sourceVersion:

~~~text
target version 21
incoming event version 20  -> do not overwrite version 21
incoming event version 22  -> apply, then checkpoint
~~~

MongoDB change stream ordering/transaction event ordering có semantics riêng theo topology; **không tự tạo một global increment counter** nếu source không có. Với multi-shard/multi-collection workflows, version gate cần đủ để chống out-of-order writes; nếu không có version, nên dùng connector/CDC protocol giữ ordering per key và resync khi gap.

### 16.5. Dual-write có thể tạo partial success

~~~text
App writes source: SUCCESS
App writes target: TIMEOUT
App returns HTTP 500
Retry comes in with same business request
~~~

Timeout target **không chứng minh write chưa commit**. Cần stable idempotency key + unique business index + read-repair; một distributed transaction tự phát giữa hai MongoDB clusters không xuất hiện chỉ vì app gọi hai `save`.

### 16.6. Watermark convergence

Không chốt PASS khi:

~~~text
Source high watermark = E13000
Target applied = E12700
Lag = 300 events
~~~

Ngay cả khi counts “tình cờ bằng nhau”, target còn thiếu changes. Một tiêu chí cutover có thể yêu cầu:

~~~text
1. All historical partitions completed.
2. No unresolved transform errors/quarantine blockers.
3. Target applied every event through agreed cut T.
4. No replay gap; resume token/lag verified.
5. Key, type, constraint and business checks PASS at T.
~~~

Không lấy “lag dưới 1 giây” làm bằng chứng **exactly caught up** nếu cùng lúc có 100 writes/s và deadline cần zero-loss.

### 16.7. Change streams không có history vô hạn

Oplog/change stream retention window có thể bị rút ngắn khi tốc độ writes tăng. Nếu migration backfill kéo dài 3 ngày mà history giữ 1 ngày, consumer có thể **mất khả năng resume từ T0**. Theo dõi window/lag và lên phương án snapshot rebuild, không tiếp tục rồi suy từ counts rằng mọi update đã được replay.

### 16.8. Final cut và rollback

Một migration online thường cần **mốc cuối được điều phối** (quiesce ngắn hoặc write-routing fence) để:

1. Chốt source-of-truth/writer.
2. Đợi CDC bắt kịp qua mốc chốt.
3. Chạy final critical reconciliation.
4. Chuyển reads/writes sang target.
5. Ngăn old writers tiếp tục mutate source sai hướng.
6. Giữ rollback/run-forward strategy với dữ liệu phát sinh sau cutover.

Sau khi target nhận writes mới, rollback về source cũ **không còn đơn giản** nếu thiếu reverse replication/reconcile strategy. Không ghi “rollback chỉ cần đổi connection string” mà không tính new writes.

## 17. Exception reports, quarantine và sửa sai có kiểm soát

Một hệ thống đối soát cần **sản phẩm đầu ra** có thể audit, không chỉ một dòng log “count mismatch”. Mỗi exception phải có loại lỗi, bằng chứng, phân loại severity, người xử lý và trạng thái sau khi remediation.

### 17.1. Phân loại lỗi có tính hành động

| Mã | Mô tả | Hành động thường gặp |
|---|---|---|
| `MISSING_TARGET` | Source record không có target tại cùng cut. | Kiểm CDC lag; resync key/partition. |
| `EXTRA_TARGET` | Target không có source tương ứng. | Kiểm delete/tombstone/seed/excluded scope. |
| `DUPLICATE_KEY` | Nhiều records cho một business key. | Dừng unique rollout, phân tích collision. |
| `WRONG_BSON_TYPE` | Field tồn tại nhưng BSON type sai. | Reconvert từ source với kiểm precision. |
| `MISSING_REQUIRED` | Field bắt buộc không tồn tại. | Truy nguồn/mapping, không default tùy ý. |
| `INVALID_ENUM` | State không thuộc mapping. | Quarantine, cập nhật contract nếu có state mới hợp lệ. |
| `VALUE_DIFF` | Canonical fields khác nhau. | Field-level diff, so source/version. |
| `REFERENCE_ORPHAN` | Relation trỏ entity không tồn tại. | Kiểm tenant/soft delete/retention. |
| `CROSS_TENANT` | Relation hoặc record map sang tenant khác. | Security incident, ngăn cutover và báo đúng nhóm. |
| `BUSINESS_INVARIANT` | Ledger/order/inventory balance không khớp. | Điều tra độc lập, không “fix tổng” bằng số bù. |
| `CDC_GAP` | Thiếu history/replay gap, không cùng watermark. | Không chốt PASS, resnapshot/resync. |
| `INVALID_SOURCE` | Record nguồn đã sai contract. | Quarantine và business remediation, không silently skip. |

### 17.2. Exception record mẫu

~~~json
{
  "runId": "orders-v2-20261114-001",
  "partitionId": "tenant-b:2026-10",
  "category": "VALUE_DIFF",
  "severity": "HIGH",
  "entityKeyHash": "sha256:<computed>",
  "fieldPath": "amountMinor",
  "expectedCanonical": "30000",
  "actualCanonical": "3000",
  "mappingVersion": "orders-v1-to-v2.3",
  "snapshotOrWatermark": "<verified cut>",
  "status": "OPEN",
  "ownerTeam": "migration",
  "createdAtUtc": "2026-11-14T02:10:00Z",
  "resolution": null
}
~~~

Ví dụ chỉ minh họa JSON report. `entityKeyHash` phải **được tính thực**, không giả vờ chuỗi placeholder là checksum. Với PII, không lưu raw input nếu không có quyền/cơ chế mã hóa; lưu redacted/hashed identifiers và secure evidence reference.

### 17.3. Severity phải dựa vào tác động

Một matrix có thể dùng:

- **CRITICAL:** cross-tenant data leak, payment/ledger imbalance, mất critical keys, CDC gap chưa phục hồi, dữ liệu bị xóa trái retention.
- **HIGH:** wrong financial types/values, duplicate unique key, broken required relationships.
- **MEDIUM:** optional field mang ý nghĩa UI/analytics bị khác hoặc derived summary lệch có thể rebuild.
- **LOW/INFO:** thay đổi đã được ghi nhận intentional, metadata không ảnh hưởng business theo contract.

**Tuyệt đối không** chỉ dựa vào tỷ lệ lỗi: một bản ghi critical sai có thể nghiêm trọng hơn 1.000 optional metadata mismatches.

### 17.4. Trạng thái exception

~~~text
OPEN
  |
  +--> INVESTIGATING
  |        |
  |        +--> FIX_PENDING
  |        |       |
  |        |       v
  |        |     RECHECK
  |        |       |
  |        |       +--> RESOLVED (verified)
  |        |       +--> OPEN (still mismatched)
  |        |
  |        +--> ACCEPTED_INTENTIONAL (approved)
  |
  +--> FALSE_POSITIVE (with evidence)
~~~

Không chuyển tất cả lỗi thành `IGNORED` bằng một filter chung. Một exception intentional cần có **policy ID, người phê duyệt, phiên bản và expiry**, đặc biệt nếu dữ liệu tiếp tục được ingest.

### 17.5. Quarantine dữ liệu không convert được

Một hàng nguồn `amount:"12,50"` không parse được theo contract số nguyên; không nên tạo target `amountMinor:0` để “đủ count”. Cần:

1. Giữ raw source reference và lý do lỗi.
2. Quarantine key (trong collection/bucket chỉ dành cho remediation với RBAC).
3. Phân loại source đã sai hay mapping thiếu quy tắc.
4. Business phê duyệt cách chuyển/repair.
5. Replay deterministic cùng idempotency key.
6. Reconcile lại key/partition và lưu chứng cứ.

Không để quarantine vô hạn làm “cho phép bỏ data” mà không có owner/SLA.

### 17.6. Remediation không được làm mất source

Nếu target có wrong amount, cách sửa an toàn:

~~~text
Identify stable key + source version
      |
      v
Re-read authoritative source at approved cut/version
      |
      v
Apply deterministic mapping
      |
      v
Conditional update with expected version
      |
      v
Verify target type/value/invariants
      |
      v
Record fix ticket/audit/reconciliation evidence
~~~

Đừng sửa target bằng cách “cộng 27.000 vào tổng” hoặc set tất cả invalid values thành mean/0. Nếu target đã có writes mới sau cut, repair phải kiểm version để không ghi đè thay đổi hợp lệ.

### 17.7. Đối soát nên có owner độc lập

Migration job tự báo “mình đã chuyển đủ” là chưa đủ. Tốt hơn có **reconciliation implementation độc lập** đọc authoritative source/target và contract được review. Cùng một bug trong converter và checker có thể tạo false PASS nếu cả hai dùng chung logic không được kiểm chứng.

## 18. Đối soát bằng Java MongoDB Driver: streaming, type-safe

Ví dụ Java dưới đây dùng MongoDB Java Sync Driver để đối soát **bounded source cursor + indexed target lookup**. Nó thể hiện kỹ thuật, không phải production-ready distributed reconcile engine; cần bổ sung metrics, snapshots, retries, sharding, pagination và reverse-scan.

### 18.1. Kiểm target có chính xác một match

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;
import java.util.ArrayList;
import java.util.List;

public final class OrderReconcileExample {
    public static void run(
            MongoCollection<Document> source,
            MongoCollection<Document> target) {

        long missing = 0;
        long duplicate = 0;
        long wrongAmount = 0;
        long examined = 0;

        try (MongoCursor<Document> cursor = source
                .find()
                .batchSize(200)
                .iterator()) {
            while (cursor.hasNext()) {
                Document s = cursor.next();
                ObjectId legacyId = s.getObjectId("_id");

                // Requires index on target.legacyId for large datasets.
                List<Document> hits = target.find(
                        Filters.eq("legacyId", legacyId))
                    .limit(2)
                    .into(new ArrayList<>());

                examined++;

                if (hits.isEmpty()) {
                    missing++;
                    continue;
                }
                if (hits.size() > 1) {
                    duplicate++;
                    continue;
                }

                Document t = hits.get(0);
                Long expected;
                try {
                    expected = Long.valueOf(s.getString("amount"));
                } catch (RuntimeException invalid) {
                    // Production: report INVALID_SOURCE and quarantine key.
                    wrongAmount++;
                    continue;
                }

                Object actual = t.get("amountMinor");
                if (!(actual instanceof Long)
                        || !expected.equals(actual)) {
                    wrongAmount++;
                }
            }
        }

        System.out.printf(
            "examined=%d missing=%d duplicate=%d wrongAmount=%d%n",
            examined, missing, duplicate, wrongAmount);
    }
}
~~~

**Lưu ý:**

- Java Sync Driver maps BSON int64 to `java.lang.Long` in a `Document`; `instanceof Long` kiểm **đúng type** thay vì chỉ so giá trị numeric.
- `Long.valueOf(s.getString("amount"))` chỉ đúng khi source contract dùng integer-string và input hợp lệ. Cần kiểm missing, null, Unicode digits, leading/trailing whitespace, overflow/currency trước khi coi là production conversion.
- `limit(2)` đủ phát hiện **có hơn 1 target match**, không xác định tổng số duplicate lớn hơn 2; với báo cáo cần query riêng.
- Script chưa kiểm **extra target**, cross-tenant mismatch, statuses, children, checksum, ledger, CDC cut.
- Cần readConcern/snapshot/watermark phù hợp; đọc hai clusters tại hai thời điểm không tự consistent.
- Khi báo cáo, không print raw PII hay credentials.

### 18.2. Không tạo MongoClient cho từng record

**Sai:**

~~~java
for (Document sourceRow : sourceRows) {
    try (MongoClient c = MongoClients.create(uri)) {
        // check one record ...
    }
}
~~~

Mỗi record lại mở topology/pools/TLS handshakes. Tạo **MongoClient dùng chung** cho mỗi cluster/reconcile job, với pool/concurrency có giới hạn; đóng sau khi job hoàn tất. Nếu source và target hai clusters, dùng hai clients lâu dài, không tạo/đóng trong hot loop.

### 18.3. Bounded parallelism

Muốn tăng throughput có thể chạy một số partitions song song:

~~~text
partitionQueue (bounded)
       |
       +-- worker 1 -> source cursor + target batch lookups
       +-- worker 2 -> source cursor + target batch lookups
       +-- worker 3 -> source cursor + target batch lookups
       +-- worker 4 -> source cursor + target batch lookups
       |
       v
append-only reconciliation report + checkpoints
~~~

Không spawn 1 future/task cho từng document của 100 triệu records; vừa tạo memory pressure vừa saturate MongoDB. Nếu 4 workers chưa đủ, tăng dần và đo CPU/IOPS/checkout wait/replication lag thay vì vô hạn.

### 18.4. Tối ưu target lookups theo batch

Trên mỗi source batch kích cỡ 200, có thể dùng `Filters.in("legacyId", ids)` lấy target matches một lần:

~~~java
var sourceBatch = /* max 200 source Documents */;
var legacyIds = sourceBatch.stream()
    .map(s -> s.getObjectId("_id"))
    .toList();

List<Document> targetBatch = target
    .find(Filters.in("legacyId", legacyIds))
    .into(new ArrayList<>());
~~~

Đoạn mã minh họa chỉ thể hiện **batch lookup**, cần group hits theo legacyId, phát hiện duplicates/extra, đảm bảo query BSON/response size và memory cap. Không sử dụng `$in` với hàng triệu IDs trong một command.

### 18.5. Canonical comparison trong Java

Trong production, nên tách:

~~~java
record Diff(String code, String entityKey, String fieldPath) {}

CanonicalOrder parseLegacy(Document source);
CanonicalOrder parseTarget(Document target);

List<Diff> compare(CanonicalOrder expected, CanonicalOrder actual);
~~~

Các method signatures là **mô hình thiết kế**, không phải một Java class được viết đầy đủ trong snippet. Hãy test bằng fixtures với missing/null, invalid enum, int32-vs-int64, date timezone, Decimal128, array reordering, overflow, tenant mismatch và unknown fields.

### 18.6. Cursor, timeout và resume

Java cursor lớn cần `try-with-resources`/`close()`, `batchSize` và checkpoint theo **last processed stable key**, không theo row offset. Nếu job dừng giữa chừng, resume từ key range chưa hoàn tất **với cùng snapshot/cut**; nếu không thể giữ snapshot, chạy reconciliation lại với cut mới và không gộp báo cáo như một run duy nhất.

## 19. Spring Data MongoDB và đối soát ứng dụng

Spring Data MongoDB giúp quản lý mapping, repositories và transactional operations. Tuy nhiên, đối soát production cần **phân biệt schema validation ở entity level, dữ liệu BSON thật trong collection, và quy tắc business**.

### 19.1. DTO của schema v2

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders_v2")
public class OrderV2 {
    @Id
    private String id;
    private String tenantId;
    private String orderNo;
    private String customerId;
    private String status;
    private Long amountMinor;
    private Instant createdAt;
    private List<OrderItemV2> items;
    private Integer schemaVersion;
    @Version
    private Long version;

    // Constructor/accessors theo Spring Data mapping.
}
~~~

Trong Java, `Long amountMinor` **không tự chứng minh BSON lưu trên server là `long`** nếu dữ liệu được viết từ nhiều clients/scripts. Spring Data có conversion mapping, nhưng reconciliation exact-type nên truy vấn **BSON type trong MongoDB** hoặc đọc raw `Document/BsonDocument` thay vì chỉ tin DTO được deserialize.

### 19.2. Bean Validation không thay MongoDB validator

Annotation:

~~~java
@NotNull
@PositiveOrZero
private Long amountMinor;
~~~

có tác dụng khi ứng dụng kích hoạt Bean Validation tại đúng boundary. Nó **không chặn** một admin script, legacy service hoặc job khác ghi trực tiếp MongoDB. Với ràng buộc storage cần `$jsonSchema`/unique indexes; với business invariants xuyên collections cần query/transaction/application checks.

### 19.3. `MongoTemplate` tìm documents sai schema

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import java.util.List;

public List<Document> findWrongAmountTypes(MongoTemplate template) {
    BasicQuery q = new BasicQuery(
        "{ $expr: { $ne: [" +
        "    { $type: '$amountMinor' }, 'long' " +
        "] } }");
    q.limit(100);

    return template.find(q, Document.class, "orders_v2");
}
~~~

Snippet dùng `BasicQuery` raw expression để đọc **tối đa 100 exception samples**, không đủ chứng minh toàn collection không còn lỗi. Với reconciliation full scale, nên dùng aggregation `$group`/streaming cursors, không lặp một query lấy 100 documents rồi báo PASS.

### 19.4. `ReactiveMongoTemplate`

Trong WebFlux:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import org.bson.Document;
import reactor.core.publisher.Flux;

Flux<Document> findWrongTypes(ReactiveMongoTemplate template) {
    BasicQuery q = new BasicQuery(
        "{ $expr: { $ne: [" +
        "    { $type: '$amountMinor' }, 'long' " +
        "] } }");
    q.limit(100);
    return template.find(q, Document.class, "orders_v2");
}
~~~

Reactive I/O có thể giảm số blocked threads, nhưng không biến `$expr` query thiếu index thành rẻ. Giới hạn concurrent partitions/streaming buffers, và không gọi `collectList()` trên hàng triệu docs.

### 19.5. Repository finder không đủ cho reconciliation

~~~java
interface OrderV2Repository extends MongoRepository<OrderV2, String> {
    long countByTenantIdAndStatus(String tenantId, String status);
}
~~~

Method thuận tiện cho **count metric**, nhưng để kiểm BSON types, `$lookup` cross collections, duplicates, CDC watermarks, ledger balance và canonical equivalence, cần `MongoTemplate`/aggregation hoặc reconciliation service. Không ép mọi phép đối soát thành derived repository method dài khó audit.

### 19.6. Hai datasources và transaction scope

Nếu nguồn và đích là hai MongoDB clusters, hai MongoTemplates/clients thường có **transaction contexts riêng**. `@Transactional` áp vào target không tự bảo đảm một transaction xuyên source cluster, target cluster và Kafka. Khi cần online migration, dùng snapshot+CDC/idempotent apply và reconciliation watermark; không giả định các hệ thống tự commit atomically.

### 19.7. Optimistic locking và race khi sửa sai

`@Version` trên entity có thể giúp phát hiện stale writes ở những repository save paths phù hợp. Nhưng remediation sửa `amountMinor` trong khi target nhận order update mới cần kiểm **expected source/target version** trong update filter hoặc CAS policy:

~~~java
// Pseudocode: chỉ sửa nếu sourceVersion vẫn bằng 42.
Query q = Query.query(Criteria.where("_id").is(targetId)
    .and("sourceVersion").is(42L));
Update u = new Update()
    .set("amountMinor", correctAmount)
    .set("sourceVersion", 43L);

template.updateFirst(q, u, "orders_v2");
~~~

`sourceVersion` và `43L` chỉ là ví dụ; version phải đến từ authoritative source event/contract, không tự cộng một chỉ số tùy ý rồi gọi là event ordering.

### 19.8. Đọc BSON raw khi exactness quan trọng

Với Decimal128, ObjectId, BSON Date và int32/int64, mapper có thể biểu diễn bằng Java types dễ dùng nhưng làm mất thông tin raw type nếu DTO dùng số chung. Đối soát chính xác nên đọc:

~~~java
MongoCollection<org.bson.BsonDocument> raw = database
    .getCollection("orders_v2", org.bson.BsonDocument.class);
~~~

Rồi kiểm `BsonValue.getBsonType()`/`isInt64()`/`isDecimal128()` khi cần. Không đoán BSON storage type chỉ từ JSON response của REST API.

## 20. Kiểm thử chiến lược đối soát

### 20.1. Unit tests cho mapping contract

Mỗi rule cần tối thiểu một positive case, negative case và boundary case:

| Rule | Positive | Negative/boundary |
|---|---|---|
| amount string → int64 | `"125000" → 125000L` | `"12,50"`, empty, null, overflow, whitespace. |
| status mapping | `"new" → "OPEN"` | `"unknown"`, uppercase variant nếu không hợp lệ. |
| Date | Giữ đúng UTC instant. | Local date thiếu timezone, DST ambiguous. |
| tenant | Giữ nguyên tenant-a. | Target tenant-b, missing tenant. |
| ObjectId legacy link | ObjectId bằng nguồn. | String hex thay ObjectId, duplicate legacyId. |
| items | Sum đúng và giữ quantity. | Array missing, empty, element wrong type, reordered semantics. |
| currency | Integer minor units đúng. | Mix VND/USD, wrong scale, rounding. |
| optional fields | Missing/null theo contract. | Default tự thay ý nghĩa. |

### 20.2. Fixtures đối kháng

Tạo một dataset test có:

- Tổng count bằng nhau nhưng keysets khác.
- Duplicate business key trong một tenant.
- Cùng orderNo ở hai tenants **hợp lệ**.
- Field đúng value nhưng sai BSON type.
- Field đúng type nhưng sai value.
- Source invalid format, conversion overflow.
- Missing/null/type mismatch.
- Array đảo thứ tự (allowed/not allowed theo rule).
- Cross-tenant reference.
- Payment/ledger lệch 1 đơn vị tiền nhỏ nhất.
- Update xảy ra sau backfill, delete/tombstone, CDC replay.

Nếu checker vẫn PASS khi cố ý inject các defects đó, cần sửa **checker** chứ không chỉ sửa migration code.

### 20.3. Property-based và metamorphic testing

Một số tính chất hữu ích:

~~~text
for every valid legacy order x:
  canonicalizeLegacy(x) == canonicalizeTarget(migrate(x))

for every target accepted by validator:
  required types / enum / indexes obey contract

for every business transfer:
  sum(postings.deltaMinor) == 0

applying the same CDC event twice:
  final target state is unchanged
~~~

Property-based tests sinh nhiều combinations để bắt edge cases. Nhưng phép thử canonicalizeLegacy so với migrate dùng cùng bug vẫn có thể false PASS; phải có **independent expected fixtures và invariants**.

### 20.4. Integration tests trên MongoDB thật

Mock repositories không đủ xác nhận `$convert`/`$type`, indexes, unique constraints, `$lookup`, BSON mapping và transaction semantics. Dùng MongoDB lab/Testcontainers replica set khi features cần, với server version gần production. Test:

1. Tạo fixture.
2. Chạy migration trên collection test.
3. Chạy reconciliation.
4. Khẳng định expected exceptions / khi sửa thì PASS.
5. Test duplicate key/validator errors và rollback.
6. Dọn lab có kiểm soát.

**Không** dùng migration/reconciliation test để xóa dữ liệu ở database production do URI config nhầm; cần guard environment/credentials.

### 20.5. So với source-of-truth độc lập

Nếu business có accounting ledger/export được audit, dùng nó để đối chiếu totals sau migration. Khi cả source và target cùng bị một bug ứng dụng từ trước, source-target equality vẫn có thể PASS nhưng business balance sai. Đối soát với **invariant độc lập** giảm false confidence.

### 20.6. Load test reconciliation job

Kiểm không chỉ tốc độ, mà còn:

- DB p95/p99 latency trong khi chạy checker.
- CPU/IOPS/cache/lock impact.
- Memory của checker khi stream keys.
- Network transfer/driver pool checkout.
- CDC lag và history window.
- Retry behavior khi node stepdown.
- Restart/resume từ partition checkpoint.

Checker không nên trở thành nguyên nhân production outage ngay trước cutover.

### 20.7. Dry-run và canary

Thực hiện:

~~~text
Small lab fixture -> dev contract tests
       |
       v
Staging copy/snapshot -> full reconciliation
       |
       v
Production read-only shadow comparison
       |
       v
Small tenant/range canary
       |
       v
Full rollout + final exact reconciliation
~~~

Canary phải có guard để tenant nhỏ nhưng rủi ro cao vẫn được kiểm. Không chọn mỗi “tenant dễ nhất” rồi dùng làm bảo đảm cho toàn dữ liệu.

### 20.8. Phép thử hồi quy sau đổi mapping rule

Nếu mapping contract nâng từ v2.3 sang v2.4:

1. Ghi lý do đổi và data ranges ảnh hưởng.
2. Khóa expected behaviors của v2.3 bằng fixtures.
3. Thêm fixtures cho rule mới.
4. Re-run các partitions đã đánh dấu PASS nếu rules ảnh hưởng chúng.
5. Không ghép hash v2.3 với v2.4 trong một partition summary.
6. Cập nhật migration manifest/exception resolutions có version.

## 21. SLO, monitoring và dashboard đối soát

Một reconciliation run có thể thành công về kỹ thuật nhưng **không đủ coverage**. Dashboard nên có metrics theo batch, tenant, schema version, business criticality và cut/watermark.

### 21.1. Metrics cơ bản

| Metric | Đơn vị | Ý nghĩa |
|---|---|---|
| `source_count` / `target_count` | Documents | Count theo scope/partition. |
| `source_unique_keys` / `target_unique_keys` | Keys | Phát hiện duplicate vs count. |
| `missing_target_count` | Keys | Source không có target tại cùng cut. |
| `extra_target_count` | Keys | Target không có source hợp lệ. |
| `duplicate_key_count` | Keys/groups | Số key có cardinality sai. |
| `wrong_bson_type_count` | Documents/fields | Sai loại dữ liệu theo schema. |
| `missing_required_count` | Documents/fields | Thiếu required fields. |
| `invalid_enum_count` | Documents/fields | State mapping thiếu. |
| `reference_orphan_count` | References | Broken links theo business policy. |
| `business_invariant_failures` | Groups | Ledger/payment/inventory outcomes sai. |
| `value_diff_count` | Keys/fields | Canonical compare khác. |
| `unresolved_critical_count` | Exceptions | Cutover blocker. |
| `cdc_lag_events` / `cdc_lag_seconds` | Events/seconds | Target còn xa watermark nguồn. |
| `verified_partitions` | Partitions | Coverage thực sự đã PASS. |
| `reconcile_duration_seconds` | Seconds | Tốc độ và khả năng đạt cutover window. |
| `reconcile_failure_rate` | % | Lỗi tool/network/convert. |

### 21.2. Coverage phải định nghĩa denominator

~~~text
coverage = verified_in_scope_keys / all_in_scope_source_keys
~~~

Nếu target còn extra keys hoặc source duplicates, coverage theo source alone chưa đủ; cũng cần **reverse coverage** và partition completion. Không dùng `99.9% coverage` để lờ 0.1% payments critical chưa kiểm.

### 21.3. Differential dashboard

Một dashboard minh họa:

~~~text
Reconciliation run: orders-v2-20261114-001
Mapping version:   v2.3
Cut/Watermark:     VERIFIED T1
Partitions:        180/200 verified
Missing keys:      12
Extra keys:        3
Wrong BSON types:  21
Value diffs:       8
Critical blockers: 2
Ledger imbalance:  1
Go/No-Go:          NO-GO
~~~

**Không tô tất cả xanh chỉ vì migration rows processed = source count**. Ở ví dụ, 180/200 partitions chưa là full coverage, còn các blockers critical; status phải NO-GO.

### 21.4. Cảnh báo chất lượng và tiến độ

Thiết kế alerts theo mức severity:

- **Critical:** bất kỳ cross-tenant record, unexplained ledger imbalance, CDC gap không thể replay, hoặc thiếu critical business key.
- **High:** tăng invalid types/duplicates hoặc missing keys sau catch-up.
- **Operational:** không hoàn thành partition, checksum job failed, lag tăng gần oplog history window.
- **Warning:** low-risk field diffs vượt tolerance đã duyệt.

Đặt số liệu theo **source/target cut và mapping version**, không trộn runs ở phiên bản khác nhau.

### 21.5. Đo ảnh hưởng lên MongoDB

Theo dõi riêng:

- CPU/IOPS/network và WiredTiger cache.
- Query latency p95/p99 của application.
- Driver pool checkout wait/in-use connections.
- `$lookup`/`$group` execution time và explain plan.
- Replication lag/CDC lag.
- Reconciliation queue/backpressure.

Nếu checker làm tăng p99 production, **throttle/pause** theo runbook và giữ checkpoint; không tiếp tục vì muốn “kịp deadline” rồi tạo incident lớn hơn.

### 21.6. Metrics labels và bảo mật

Đừng gắn `orderNo`, `customerId` hoặc PII vào Prometheus labels; cardinality sẽ bùng nổ. Dùng `runId` (với cardinality được kiểm soát), `partitionGroup`, `errorCode`, `severity`, `schemaVersion`. Chi tiết record nằm trong **secure exception store** có retention/RBAC.

## 22. Runbook: chốt đối soát trước và sau cutover

### Giai đoạn A — Chuẩn bị

1. Xác định authoritative source, schemas v1/v2, tenants/partitions, exclusions có phê duyệt.
2. Ghi mapping contract version, canonicalization rules, expected key cardinality.
3. Ghi business invariants theo currency/status/time, owner và tolerance policy.
4. Chuẩn bị backups/recovery point và restore test tương thích.
5. Chuẩn bị read-only reconciliation credentials, indexes/permissions và resource budget.
6. Định nghĩa snapshot/quiesce/CDC watermark cut và cách lấy evidence.
7. Lập dashboard, exception store, on-call escalation, go/no-go criteria.
8. Rehearse trên staging/canary, kiểm cả deliberate wrong-data injection.

### Giai đoạn B — Chạy baseline trước migration

1. Chốt nguồn dữ liệu và cut \(T_0\) có kiểm chứng.
2. Tính counts/unique keys theo tenant, date, schemaVersion, status.
3. Profile BSON types, missing/null, invalid enum/source anomalies.
4. Lưu summary financial/ledger/inventory metrics ở source theo business definition.
5. Ghi hash/manifest canonicalization version cho partitions.
6. Quarantine source anomalies có policy, không tự bỏ records.

### Giai đoạn C — Migration/backfill

~~~text
Read source partition at agreed cut
    |
    +-- validate input format and identity
    |
    +-- convert via versioned mapping
    |
    +-- write target with idempotent key/version
    |
    +-- record applied checkpoint and errors
    |
    v
Reconcile count, keyset, BSON type, value, constraints, business
~~~

Nếu online, song song xử lý CDC với cơ chế ordering/version, delete events và resume token; không đánh dấu partition đã sẵn sàng khi còn CDC gap.

### Giai đoạn D — Exception review và remediation

1. Export summary không lộ PII; tạo tickets theo severity.
2. Với mỗi exception, phân loại **true defect, transient lag, intentional transform, source invalid hoặc checker defect**.
3. Sửa migration mapping, data source hoặc target theo runbook.
4. Dùng conditional version-aware update, không overwrite dữ liệu mới.
5. Re-run **đúng cut/mappingVersion** hoặc tạo run mới rõ ràng.
6. Kiểm related business invariants sau fix, không chỉ riêng field lỗi.
7. Lưu evidence resolution và người phê duyệt.

### Giai đoạn E — Final gate

Một bảng quyết định ví dụ:

| Điều kiện | Yêu cầu ở thời điểm go/no-go |
|---|---|
| Historical partitions | 100% in-scope partitions completed and verified. |
| Source/target compare cut | Same approved logical cut/watermark. |
| Missing critical keys | 0 unresolved. |
| Extra/duplicate keys | 0 unexplained. |
| BSON required type mismatches | 0 unresolved. |
| Unique/validator violations | 0 unresolved relevant violations. |
| Referential/tenant violations | 0 cross-tenant; orphans theo approved policy. |
| Ledger/payment/inventory | Invariants đạt exact/tolerance policy. |
| CDC | Caught up at final cut, no missing resume history. |
| Rollback | Feasible, tested, owners ready. |
| Business sign-off | Data owner, operations, security/finance as needed. |

Nếu bất kỳ critical condition FAIL hoặc coverage không xác định, kết quả là **NO-GO**. Không được đổi tolerance sau khi nhìn thấy lỗi chỉ để “vừa ngưỡng” mà không có phê duyệt và audit.

### Giai đoạn F — Cutover

1. Freeze/fence writers theo kiến trúc đã phê duyệt.
2. Verify final source→target watermark.
3. Chạy critical reconciliation cuối (hoặc xác nhận các immutable proof đã đạt).
4. Route reads/writes sang target.
5. Theo dõi correctness, write errors, latency, authorization và duplicate events.
6. Có phương án rollback/run-forward tính tới **new writes** sau cutover.
7. Không xóa nguồn hoặc backups trước khi hết rollback/retention policy.

### Giai đoạn G — Sau cutover

- Chạy periodic reconciliation cho high-risk business invariants trong cửa sổ quan sát.
- Theo dõi exception trends, false positives, new enum/type anomalies.
- Cập nhật validators/indexes sang trạng thái enforce sau khi mọi app versions tương thích.
- Review unresolved low-risk exceptions và retention.
- Lưu final manifest, checksums, sign-off, tickets, source cut, tool/mapping versions.
- Rút kinh nghiệm và bổ sung regressions vào mapping tests.

### 22.1. Khi nào nên rollback và khi nào run-forward?

**Rollback** phù hợp khi target chưa nhận significant new writes hoặc có reverse-sync đáng tin. **Run-forward** là sửa target trên schema mới khi rollback làm mất dữ liệu mới, không có reverse migration hoàn chỉnh hoặc data shape không thể chuyển ngược an toàn. Quyết định cần:

- Time since cutover và khối lượng new writes.
- Tính tương thích ứng dụng cũ với schema mới.
- Backup/recovery point thực.
- Khả năng replay/reconcile từ target → source.
- Business criticality/data loss window.

Không gọi “đổi DNS/connection string” là rollback đầy đủ nếu hai sides đã phân kỳ.

## 23. Chẩn đoán khi các số liệu không khớp

| Dấu hiệu | Nghi vấn đầu tiên | Hành động xác minh |
|---|---|---|
| Tổng count bằng nhưng count theo tenant lệch | Missing và extra bù nhau, tenant mapping sai. | Keyset diff per tenant, join legacyId. |
| Target count lớn hơn source | CDC duplicate, extra seed, soft-delete policy. | Unique keys, watermark, deletes/tombstones. |
| Target count nhỏ hơn source | Backfill skip, invalid source quarantine, CDC gap. | Partition progress, errors, keyset missing. |
| `wrong_type_count` tăng | Driver/serializer khác, conversion bỏ sót. | `$type` distribution, mapping version, app writer inventory. |
| `$sum` target thấp bất thường | String/null ignored hoặc missing records. | Type count, exact value diff, unique keys. |
| Keysets equal nhưng business totals lệch | Wrong amount/precision/currency/status. | Canonical values, ledger and invariant checks. |
| Hashes khác tất cả partitions | Schema version/encoding/timezone/field ordering sai. | Canonical contract version, sample field diffs. |
| Hashes equal nhưng report sai | Checker bỏ field hoặc business invariant thiếu. | Independent ledger/business source, test checker. |
| Cross-tenant references | Key mapping/join thiếu tenant dimension. | Composite key joins, tenant auth policy. |
| Counts dao động mỗi lần chạy | Hai phía đang ghi hoặc cut không cố định. | Snapshot/watermark, TTL/CDC lag/clock semantics. |
| Quarantine ngày càng tăng | Source drift, validator/app compatibility. | New source writers, schemaVersions, invalid examples. |
| Unique index build fail | Pre-existing duplicates/null key combinations. | Duplicate grouping, required fields, index semantics. |
| Checker chạy quá lâu | Collection scan, huge joins, memory/unbounded concurrency. | Explain, indexes, partitioning, throttle. |
| Sau cutover drift tái xuất hiện | Old writers vẫn hoạt động, dual-write out-of-order. | Fencing, CDC versions, app deployment inventory. |
| Report nói PASS nhưng khách hàng báo sai đơn | Scope/invariant không đầy đủ, security mapping. | Trace business request, compare entity + related records. |

### 23.1. Đừng chữa mọi sai lệch bằng “chạy migration lại”

Nếu migration không idempotent, chạy lại có thể:

- Tạo duplicate child documents.
- Ghi đè target values mới.
- Reapply tiền/điểm nhiều lần.
- Đổi timestamps thành giờ chạy lại.
- Làm mất audit trail.

Trước replay, yêu cầu **stable keys, versioned mapping, deterministic transform, upsert/condition semantics và checkpoint**. Bất kỳ remediation nào tác động tiền phải có audit/approval.

### 23.2. “Có error nhưng count vẫn đúng”

Một exception malformed record có thể được bỏ qua, đồng thời một extra record được tạo, làm totals bằng. Vì vậy report phải gồm:

~~~text
source_count
target_count
unique_key_count
missing_keys
extra_keys
type_errors
value_errors
business_errors
quarantine_count
watermark_gap
~~~

Chỉ một metric không đủ để kết luận migration thành công.

## 24. Những hiểu lầm thường gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
|---|---|---|
| “Migration script exit 0 là dữ liệu đúng.” | Script có thể bỏ qua errors hoặc viết sai mapping. | Independent reconciliation theo contract. |
| “Count tổng bằng nhau là đủ.” | A mất, B thêm, tenant drift vẫn sum 0. | Keyset/partition diff và constraints. |
| “`estimatedDocumentCount` là exact.” | Là ước lượng dựa metadata. | `countDocuments`/aggregation tại same cut. |
| “Count trên source/target cách nhau 1 phút vẫn so được.” | Concurrent writes làm khác snapshot. | Verified logical cut/watermark. |
| “`readConcern:majority` tự tạo snapshot toàn bộ queries.” | Mỗi read có thể ở timestamp khác. | Snapshot/transaction/CDC coordination. |
| “Số documents mới bằng số docs cũ khi tách embedded items.” | Entity cardinalities khác. | Mapping cardinality per entity. |
| “ObjectId hex string bằng ObjectId raw.” | BSON types khác. | Canonical ID mapping và type check. |
| “String `'1000'` và NumberLong 1000 giống nhau.” | Storage type/behavior khác. | Exact BSON `long` và value contract. |
| “`$sum` báo lỗi khi gặp string amount.” | Non-numeric values có thể bị ignore trong aggregation. | Invalid type counter + exact checks. |
| “`$isNumber` chứng minh field là long.” | Nó chấp nhận int/double/decimal. | `$type:"long"`. |
| “Missing và null là một.” | Query/validator/index semantics khác. | Separate missing/null flags. |
| “`$convert onError:0` giúp đủ records.” | Biến invalid data thành business zero. | Quarantine lỗi parse; không silent default. |
| “Double đủ chính xác cho mọi currency.” | Floating-point precision/scale risk. | Int64 minor units hoặc Decimal128 theo policy. |
| “Có validator mới là dữ liệu cũ tự đúng.” | Validator không sửa historical documents. | Scan và remediate dữ liệu cũ. |
| “Unique index tự đảm bảo required field.” | Null/missing và partial filter nuances. | `required` + type validation + unique index. |
| “Unique compound index luôn unique toàn sharded cluster.” | Shard-key constraints/versions. | Thiết kế index theo sharded docs. |
| “`$lookup` có thể join mọi clusters khác nhau.” | MongoDB aggregation không tự join cross independent clusters. | Reconciliation app/external compare. |
| “Foreign key kiểm xong thì tenant chắc đúng.” | Join theo ID đơn không kiểm tenant. | Composite tenant-aware joins. |
| “Hash raw BSON đủ để so schema v1/v2.” | Intentional field/type changes gây false diff. | Canonical form trước hash. |
| “SHA-256 bằng nhau nghĩa mọi nghiệp vụ đúng.” | Contract bỏ field/bug shared vẫn false PASS. | Independent invariants, exact critical checks. |
| “Array đảo thứ tự luôn sai.” | Có arrays mang set semantics. | Rule định nghĩa order-sensitive hay không. |
| “Array đảo thứ tự luôn đúng.” | Line order có thể quan trọng. | Check stable lineNumber/sequence. |
| “CDC lag 1 giây nghĩa đã catch up tuyệt đối.” | Vẫn có events chưa apply. | Exact watermark cut verification. |
| “Change stream giữ history vô hạn.” | Phụ thuộc oplog retention/resume window. | Monitor lag/window, resnapshot if gap. |
| “Dual-write hai clusters là atomic.” | Partial success và timeout ambiguous. | Idempotent apply/CDC/reconcile. |
| “Rollback chỉ đổi connection string.” | New writes có thể chỉ nằm target. | Reverse sync/restore/run-forward plan. |
| “Mọi extra target đều nên xóa.” | Có thể valid seed/new writes/retention. | Verify scope/ownership before mutation. |
| “Sample 1% chứng minh toàn bộ 100%.” | Rare defects có thể không được chọn. | Risk-based exact checks + sampling có ghi coverage. |
| “Count/money totals bằng là chắc mọi ledger entry đúng.” | Lỗi dấu +/− bù nhau. | Per-key/per-leg checks. |
| “Cho qua 0.01 tolerance mọi field là hợp lý.” | Money/security cần exact. | Field/business-specific tolerance policy. |
| “Đối soát phải chạy nhanh nhất có thể.” | Full scans có thể phá production SLO. | Throttle, index, partitions, headroom. |
| “Sửa data rồi không cần recheck liên quan.” | Fix có thể làm hỏng quan hệ/tổng. | Reconcile key + linked business invariants. |
| “Báo cáo chi tiết cứ log toàn document.” | PII/credentials/security exposure. | Redacted evidence/RBAC/retention. |

## 25. Bài tập thực hành và đáp án

Các bài dựa trên tình huống giả định/fixture lab ở bài; không phải kết quả một lần test production. Với bài có write/DDL/validator, chỉ thao tác trên **MongoDB lab/staging được phép**. Cách đánh giá là **giải thích nguyên nhân, viết phép kiểm đúng, và xác định tiêu chí PASS/NO-GO**, không phải chạy lệnh sửa dữ liệu trên môi trường thật.

### Bài 1 — Tổng count bằng

**Đề:** Nguồn 4 documents, đích 4. Có thể kết luận migration thành công?

**Đáp án:** Không. Fixture có source `ORD-2002` missing, target `ORD-ORPHAN` extra, nên count 4 bù trừ. Phải so keysets, tenant partitions, types, values, references và business invariants.

### Bài 2 — Count theo tenant

**Đề:** Source tenant-a=2, tenant-b=2; target tenant-a=3, tenant-b=1. Tổng cùng 4. Báo cáo điều gì?

**Đáp án:** Tenant-a dư 1 và tenant-b thiếu 1. Reconcile theo tenant+orderNo/legacyId; có thể là extra/missing hoặc cross-tenant mapping. Không pass chỉ vì tổng delta 0.

### Bài 3 — `estimatedDocumentCount`

**Đề:** Collection lớn; `estimatedDocumentCount()` trả 10.000.000 và source cũng 10.000.000. Đủ làm exact go/no-go?

**Đáp án:** Không. Đây là ước lượng từ metadata, không filter scope. Cần count/keyset exact tại cut phù hợp, có capacity planning cho scan/index.

### Bài 4 — Keyset difference

**Đề:** Source keys `{A,B,C}`, target `{A,C,D}`. Count có khớp không? Missing/extra?

**Đáp án:** Count cùng 3 nhưng `B` missing, `D` extra. Đối soát hai chiều, không chỉ source→target.

### Bài 5 — Khóa mapping

**Đề:** v1 `_id` là ObjectId, v2 `_id` là string `tenantId:orderNo`. Có thể join trực tiếp hai `_id`?

**Đáp án:** Không. Dùng stable `legacyId`/business key đã được định nghĩa, hoặc mapping table; kiểm cardinality một-một và type.

### Bài 6 — Duplicate legacyId

**Đề:** Hai target docs có cùng `legacyId` nhưng hai `_id` khác. Target có unique `_id` nên dữ liệu đã đúng?

**Đáp án:** Không. Unique `_id` chỉ ngăn trùng target primary ID, không ngăn cùng source entity map ra nhiều targets. Đếm `$group _id:"$legacyId"` hoặc unique index trên field nếu contract cho phép.

### Bài 7 — Wrong tenant

**Đề:** Source order tenant-a được map target tenant-b, amount/status đúng. Severity?

**Đáp án:** **Critical** trong multi-tenant system vì có thể rò rỉ dữ liệu. Kiểm tenant equality và composite references, ngăn cutover, điều tra authorization/data residency.

### Bài 8 — BSON `long` vs `string`

**Đề:** `amountMinor:"50000"` và `amountMinor:NumberLong("50000")` có giống nhau?

**Đáp án:** Không. BSON types khác; schema v2 yêu cầu long. Dùng `$type` trong aggregation hoặc validator `bsonType:"long"`, không chỉ so giá trị khi stringify.

### Bài 9 — Wrong value cùng type

**Đề:** Source `amount:"30000"`, target `NumberLong("3000")`. Kiểm type có phát hiện không?

**Đáp án:** Không, target vẫn là long. Phải `$convert` source theo contract và exact compare, đồng thời kiểm item sum/ledger.

### Bài 10 — Missing và null

**Đề:** Document A không có `amountMinor`, B có `amountMinor:null`. Query `{amountMinor:null}` có thể trả cả hai?

**Đáp án:** Có. Query equality-to-null có thể match cả missing và null. Dùng `$exists:false` hoặc `$type:"null"` để phân biệt, và `required` + `bsonType` khi field bắt buộc.

### Bài 11 — `$isNumber`

**Đề:** Query `$isNumber:"$amountMinor"` trả true. Có chứng minh field là BSON long?

**Đáp án:** Không; int32/double/Decimal128 cũng numeric. Nếu contract exact long, dùng `$type` expression và kiểm value/range.

### Bài 12 — Parse invalid

**Đề:** Source amount `"12,50"`, migration dùng `$convert onError:0` nên target amount=0. Có thể coi record converted?

**Đáp án:** Không. 0 là business value hợp lệ và che lỗi. Quarantine/report `INVALID_SOURCE`, review locale/scale policy, parse được mới write target rồi recheck.

### Bài 13 — Overflow

**Đề:** Nguồn string biểu diễn số lớn hơn `Long.MAX_VALUE`, target muốn int64. Làm gì?

**Đáp án:** Đánh dấu conversion overflow, không truncate/wrap. Business quyết định Decimal128 hoặc loại dữ liệu/schema mới; kiểm source/value constraints và replay theo mappingVersion.

### Bài 14 — Currency

**Đề:** Source amount 10.00 USD nhưng target integer 10, source JPY 10 cũng target integer 10. Count/value thô bằng nhau. Có hợp lý?

**Đáp án:** Không nếu target định nghĩa minor units; USD 10.00 phải thành 1.000 cents, JPY 10 thành 10 yen theo currency exponent giả định. So theo currency và correct scale, không gộp toàn bộ currencies.

### Bài 15 — Double vs Decimal128

**Đề:** Migration chuyển `NumberDecimal("0.10")` sang Java `double` rồi lưu MongoDB Double. Có đúng preservation of precision/type?

**Đáp án:** Không. Binary floating point có sai số biểu diễn và BSON type khác Decimal128. Dùng `BigDecimal/Decimal128` hoặc int64 minor units theo contract, tránh `doubleValue()` khi yêu cầu exact money.

### Bài 16 — Ngày UTC

**Đề:** Source `2026-10-01T08:00:00Z`, target `2026-10-01T15:00:00Z` vì ứng dụng ở GMT+7. Có đúng cùng instant?

**Đáp án:** Không; target đã dịch 7 giờ so với instant nguồn. Local rendering 15:00+07:00 tương ứng 08:00Z, nhưng BSON Date target đúng phải giữ 08:00Z instant. So epoch milliseconds/UTC.

### Bài 17 — Status mapping

**Đề:** Source có status `"returned"` chưa trong mapping table, script default `"OPEN"`. Có an toàn?

**Đáp án:** Không. Unknown state phải được báo `INVALID_ENUM/UNMAPPED`, cập nhật contract có approval hoặc quarantine, không silent default thành trạng thái nghiệp vụ khác.

### Bài 18 — Validator yêu cầu

**Đề:** `properties.amountMinor.bsonType:"long"` nhưng không có `required:["amountMinor"]`. Một document thiếu amountMinor có thể hợp lệ?

**Đáp án:** Có thể. `properties` chỉ ràng buộc field khi có mặt, còn `required` quyết định presence. Dùng cả hai nếu field bắt buộc.

### Bài 19 — Validator rollout

**Đề:** Đổi `validationAction:"error"` trên collection chứa dữ liệu lịch sử sai. MongoDB có tự sửa chúng?

**Đáp án:** Không. Validator chủ yếu áp cho writes theo validationLevel/action; cần scan/remediate historical invalid records và triển khai phased `warn→error` có đo, không kỳ vọng auto-repair.

### Bài 20 — Unique index

**Đề:** `orders_v2` có unique index `{tenantId:1,orderNo:1}`. Hai tenants khác nhau dùng cùng orderNo có bị chặn?

**Đáp án:** Không nếu tenantId khác và compound key khác nhau. Nhưng hai records cùng cặp tenantId/orderNo sẽ bị chặn; cần đối soát missing/null và collation semantics.

### Bài 21 — Partial unique

**Đề:** Index unique trên `{tenantId:1,orderNo:1}` có `partialFilterExpression:{isActive:true}`. Một document không có isActive có được bảo vệ bởi index không?

**Đáp án:** Không nếu nó không match filter. Cần `isActive` required/type validation và kiểm scope/business uniqueness. Partial index không thay đảm bảo toàn bộ records.

### Bài 22 — Sharded unique constraint

**Đề:** Collection sharded, developer tạo unique index không xét shard key rồi cho rằng uniqueness global. Đủ an toàn không?

**Đáp án:** Không. Unique indexes trên sharded collections có constraints về shard key prefix/index compatibility theo MongoDB version. Kiểm docs/topology và test thực tế trước cutover.

### Bài 23 — Dangling reference

**Đề:** `orders_v2.customerId="C-999"` nhưng không có customer tương ứng. Count/status/amount đều hợp lệ. Còn lỗi không?

**Đáp án:** Có thể là `REFERENCE_ORPHAN`; xem domain policy về deleted/anonymized customers. Với active order yêu cầu customer, đây là defect; dùng `$lookup` và tenant-aware matching để đối soát.

### Bài 24 — Cross-tenant join

**Đề:** CustomerId `"C-010"` tồn tại trong tenant-b, order ở tenant-a dùng same ID. Join chỉ bằng customerId có thể báo valid?

**Đáp án:** Có thể, nhưng đó là **false PASS** nếu IDs không unique global. Join theo cả customerId và tenantId; authorization/data residency là critical invariants.

### Bài 25 — Embedded → referenced

**Đề:** Nguồn có một order nhúng ba items, target có một order và ba item documents. Có nên so total source docs=1 với target docs=4?

**Đáp án:** Không. So **entity cardinality**: số orders 1→1, số items 3→3, line IDs/quantity/unitPrice/totals; mapping contract phải mô tả tách collections.

### Bài 26 — Total amount chỉ tính PAID?

**Đề:** Source có 3 PAID và 5 CANCELLED, target vẫn có amount ở cancelled docs. Dashboard doanh thu nên sum tất cả?

**Đáp án:** Không nếu business metric là recognized revenue từ PAID/settled. Phải định nghĩa status, payment captured/refunded và currency/date/cut rõ ràng. Cùng tổng gross chưa chứng minh cùng doanh thu.

### Bài 27 — Ledger totals

**Đề:** Ledger transfer T2 có entries −10000 và +9000. Invariant transfer net là 0. Kết quả?

**Đáp án:** Net = −1000; `BUSINESS_INVARIANT` severity critical/high theo domain. Không sửa bằng một posting bù tùy ý; truy authoritative source, kiểm currency/fees và remediation có audit.

### Bài 28 — Lỗi bù nhau

**Đề:** Hai sai lệch ledger +1000 và −1000 làm sum 0. Có đủ chứng minh không mất tiền?

**Đáp án:** Không. Cần per-entry/per-transfer keyset/value, account assignments và double-entry constraints. Sums chỉ là điều kiện cần.

### Bài 29 — Canonical comparison

**Đề:** Source status `"new"`, target `"OPEN"`. Raw JSON diff nhưng mapping contract quy định new→OPEN. Phải báo lỗi?

**Đáp án:** Không, nếu đúng contract. Canonicalize source status về OPEN rồi so identity, amount, dates và related invariants. Đừng yêu cầu raw BSON equality khi schema cố ý đổi.

### Bài 30 — Hash raw BSON

**Đề:** Hash SHA-256 raw BSON v1/v2 khác vì tên fields khác. Có thể kết luận migration sai?

**Đáp án:** Không. Canonicalize semantic data và dùng deterministic encoding/version rồi hash theo stable key. Sau hash mismatch phải drill đến field-level diff; không chỉ dựa vào hash.

### Bài 31 — Hashes bằng nhau nhưng checker sai

**Đề:** Cả hai canonicalizers đều bỏ quên field currency, hashes bằng nhau nhưng VND/USD bị đổi. Có thể PASS?

**Đáp án:** Không. Mapping contract thiếu field critical. Dùng independent business invariants, sample oracle và test mutation/field coverage; version hóa canonicalization contract rồi chạy lại.

### Bài 32 — Arrays

**Đề:** Tags từ `["x","y"]` thành `["y","x"]`. Sai không?

**Đáp án:** Phụ thuộc contract: nếu tags là set, có thể equivalent sau sort; nếu là sequence có ý nghĩa thứ tự, mismatch. Không canonicalize arrays bằng sort mặc định cho mọi collection.

### Bài 33 — Hai lần count khác mốc

**Đề:** Count nguồn lúc 10:00 là 100000, target lúc 10:01 là 100500 sau 500 inserts. Có chắc lỗi?

**Đáp án:** Không. Hai snapshots khác nhau. Chọn quiesce/snapshot hoặc CDC watermark cut và so cùng scope tại mốc xác minh.

### Bài 34 — CDC gap

**Đề:** Target đã apply E12700 trong khi source high watermark E13000, nhưng source/target count tình cờ bằng nhau. Có final PASS không?

**Đáp án:** Không. Còn 300 events chưa xử lý; cần catch-up/verify no gap rồi kiểm count/keys/types/business at same cut. Nếu oplog history mất, resnapshot theo runbook.

### Bài 35 — Dual-write partial success

**Đề:** Source write OK, target timeout, app retry cùng request. Có thể tạo target record mới với random ID mỗi lần?

**Đáp án:** Không an toàn. Target timeout có thể đã commit. Dùng stable target ID/idempotency, versioned upsert và verify outcome; không giả định hai MongoDB clusters commit atomically.

### Bài 36 — Delete trong lúc backfill

**Đề:** A được copy sang target rồi source xóa A; CDC consumer bỏ qua delete events. Đối soát sẽ thấy gì?

**Đáp án:** Target **extra record A**. Cần tombstone/delete handling theo retention policy, checkpoint đúng thứ tự và recheck.

### Bài 37 — Mất quyền resume

**Đề:** Backfill kéo dài 72 giờ, change stream history window chỉ còn 24 giờ. Có thể tiếp tục rồi so counts không?

**Đáp án:** Không nếu CDC đã gap và không resume được. Có thể bỏ sót updates/deletes. Phải khôi phục từ snapshot/CDC protocol được hỗ trợ hoặc resnapshot/rebuild, ghi run mới, không đánh dấu PASS vì count ngẫu nhiên khớp.

### Bài 38 — Sampling

**Đề:** Kiểm 1% random records và không tìm thấy lỗi. Có thể chấp nhận dữ liệu thanh toán còn lại chưa kiểm?

**Đáp án:** Không nếu policy đòi exactness. Sampling chỉ chứng minh phần đã lấy mẫu; cần full key/type/ledger exact checks cho critical data, stratified samples cho low-risk data được business duyệt.

### Bài 39 — Rollback sau target nhận writes

**Đề:** Sau cutover 5 giờ, target có 20.000 new orders chưa reverse-sync về source. Có thể rollback chỉ bằng đổi URI về source?

**Đáp án:** Không. Source thiếu 20.000 orders, sẽ gây data loss/inconsistent identity. Cần reverse synchronization/reconciliation, restore/run-forward strategy và business sign-off theo rollback plan.

### Bài 40 — Thiết kế một đợt đối soát hoàn chỉnh

**Đề:** Dữ liệu MongoDB orders 200 triệu documents ở replica set, schema v1 có amount string, v2 có int64 minor units và status enum mới; ứng dụng ghi liên tục, tenants có quyền truy cập nhạy cảm. Hãy trình bày kế hoạch đối soát có thể audit và đạt go/no-go.

**Đáp án gợi ý:**

1. Định nghĩa authoritative source, mapping contract version, business key bất biến, scope tenants/retention/soft deletes.
2. Định nghĩa expected cardinality, BSON required types, status mapping, tenant isolation, value precision/currency/date rules.
3. Chọn online snapshot+CDC protocol với T0, resume token/checkpoint, idempotent upsert/delete apply; tránh gap.
4. Baseline source count/unique keys/type distribution/ledger totals theo tenant, ngày, currency, status.
5. Partition source/target theo immutable indexed keys; streaming merge join/batch lookups, bounded workers, no full `toArray()`.
6. Tìm missing/extra/duplicate keys, cross-tenant mapping, required fields, wrong BSON type, mismatched values.
7. Canonicalize source/target theo cùng contract; hash theo partition để triage, exact diff cho critical fields.
8. Kiểm independent invariants: line item totals, paid/refund totals, ledger balanced, customer refs, permission/PII retention.
9. Lưu exception report có severity, mapping version, verified cut, redacted key/hash, remediation owner và proof.
10. Có quarantine cho invalid source; sửa bằng version-aware update/idempotent replay, không silent defaults.
11. Monitor MongoDB CPU/IOPS/cache/replication lag và checker progress; throttle/pause khi production SLO bị ảnh hưởng.
12. Final catch-up tại T1, tạm freeze/fence writes nếu kiến trúc yêu cầu, re-run critical checks cùng cut.
13. Go/no-go: zero critical missing keys, type/tenant/ledger defects, no CDC gap, full required coverage, rollback feasible.
14. Canary cutover, theo dõi query results/business dashboards/errors, giữ source/backups trong retention window.
15. Lưu final manifest/checksums/owner approvals, không trộn mapping versions/snapshots trong một report.

Kế hoạch chỉ hợp lệ nếu **số lượng, kiểu dữ liệu, ràng buộc và kết quả nghiệp vụ** đều được xác minh ở cùng logical cut. Một báo cáo “200 triệu rows processed” hoặc “0 script failures” không thay thế các bằng chứng đó.

## 26. Bảng quyết định nhanh: chọn phép đối soát đúng mục tiêu

| Mục tiêu | Phép kiểm đầu tiên | Phép kiểm tiếp theo | Điều cần tránh |
|---|---|---|---|
| Không mất orders | Count theo tenant/date. | Source→target missing keys và target→source extra keys. | Chỉ nhìn total count. |
| Không duplicate entity | Group business/legacy key cardinality. | Unique indexes theo scope/collation/shard key. | Dựa duy nhất vào target `_id`. |
| Kiểu dữ liệu chuẩn | `$type` distribution + required/missing/null. | `$jsonSchema` validator/collection scan. | Chỉ kiểm Java DTO type. |
| Convert amount đúng | `$convert` nguồn theo contract. | Exact compare target long/Decimal128 và sum invariants. | Ép lỗi thành 0, dùng Double cho money. |
| State đúng | Mapping enum/version. | Status count + transition/payment/fulfillment invariants. | Raw string compare khi có intentional rename. |
| Quan hệ đúng | `$lookup`/application join theo stable key. | Tenant-aware reference checks, one-to-many cardinality. | Join ID đơn mà bỏ tenant. |
| Tiền/ledger đúng | Count + sum theo currency/tenant/time. | Per-entry/per-transfer exact balance. | Tổng sai lệch tự triệt tiêu. |
| Không drift khi online | CDC watermark/resume checkpoint. | Final exact compare tại verified cut. | So hai thời điểm tùy ý. |
| Dữ liệu khổng lồ | Partition counts/hash. | Streaming sorted merge/diff từng key. | `toArray` toàn bộ data. |
| Kiểm sau cutover | Shadow reads + critical invariants. | Monitor new writes, reverse sync/rollback feasibility. | Xóa nguồn quá sớm. |

### 26.1. Mẫu báo cáo chấp nhận

~~~text
Reconciliation run:      orders-v2-20261114-001
Migration contract:      orders-v1-to-v2.3
Source/target cut:       VERIFIED logical watermark T1
Scope:                   ALL approved in-scope tenant partitions
Source count:            <measured>
Target count:            <measured>
Distinct business keys:  <measured>
Missing target:          0
Extra target:            0 (or approved exceptions)
Duplicate business key:  0
Required BSON type:      PASS
Validator/index checks:  PASS
Cross-tenant mapping:    0
Business invariants:     PASS
CDC gap:                 NONE
Critical unresolved:     0
Rollback strategy:       VERIFIED
Decision:                GO (requires owner sign-off)
~~~

**Các placeholders phải được thay bằng evidence thực**, không đưa báo cáo mẫu làm bằng chứng tự động. Nếu một điều kiện chưa đo, trạng thái phải là `UNKNOWN/INCOMPLETE`, không mặc định PASS.

### 26.2. Một kiểm tra “đủ bốn lớp” cho từng entity

~~~text
Entity identity:
  exactly one source key maps to exactly one target key

Shape:
  BSON field type/required/optional/nested arrays as contract

Constraint:
  unique + tenant-aware relationships + allowed state/range

Outcome:
  amount/ledger/inventory/status behavior as business oracle
~~~

Chỉ khi bốn lớp cùng đạt tại **cùng cut**, việc chấp nhận migration mới có căn cứ.

## 27. Tài liệu MongoDB và Spring Data chính thức

Các liên kết dưới đây dùng để tra cú pháp/semantics và điều kiện phiên bản. Trang `/manual/` có thể trỏ đến nhánh MongoDB Server hiện hành; khi hệ thống chạy phiên bản cũ, chọn đúng **Server version, FCV, Database Tools và Java Driver** đang vận hành. Không copy lệnh `collMod`/index từ ví dụ vào production mà chưa xét dữ liệu hiện có, cluster sharding và rollout policy.

### 27.1. Đếm, nhóm và so kiểu

1. [`countDocuments()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.countDocuments/) — đếm matching documents và chi phí/limitations.
2. [`estimatedDocumentCount()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.estimatedDocumentCount/) — ước lượng theo metadata, không thay exact counts.
3. [`$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — group theo tenant/status/currency và accumulators.
4. [`$sum`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/) — xử lý numeric/non-numeric values theo accumulator context.
5. [`$type` aggregation expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/) — BSON type, missing/null trong aggregation.
6. [`$type` query operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/) — query semantics và lưu ý với arrays.
7. [`$convert`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/) — convert BSON types, `onError` và `onNull`, giới hạn chuyển đổi.
8. [`$toLong`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toLong/) — conversion và error cases.
9. [`$dateToString`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateToString/) — timezone/date buckets.
10. [`$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — joins trong database và điều kiện hỗ trợ/index/performance.

### 27.2. Validation, unique và schema evolution

11. [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — document validation, `$jsonSchema` và rollout.
12. [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — `bsonType`, `required` và validator examples.
13. [`collMod`](https://www.mongodb.com/docs/manual/reference/command/collMod/) — cập nhật validator/validation action trên collection.
14. [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness, missing/null và sharded considerations.
15. [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — partialFilterExpression, uniqueness chỉ với indexed subset.
16. [Index Strategies](https://www.mongodb.com/docs/manual/applications/indexes/) — query/index planning cho scans/reconciliation.
17. [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — int32, int64, double, Decimal128, ObjectId, Date và so sánh.
18. [Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/) — biểu diễn type-safe khi export/report.

### 27.3. Snapshot, change streams và transactions

19. [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — local/majority/snapshot semantics.
20. [Read Concern `snapshot`](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — snapshot read behavior và prerequisites.
21. [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — events, resume tokens và oplog retention.
22. [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — history window/retention và implications cho online migration.
23. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — atomicity, snapshot, concurrency và limitations.
24. [Sharded Clusters](https://www.mongodb.com/docs/manual/sharding/) — shard key, routing và cluster-wide constraints.

### 27.4. Java/Spring Data và hiệu năng

25. [Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/) — typed BSON, cursors, aggregate, connection pooling và error handling.
26. [Java Driver BSON/Document API](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/documents/) — `Document`, BSON types và serialization.
27. [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — mapping, `MongoTemplate`, repositories, `@Version` và transactions.
28. [Spring Data MongoDB — Template Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `Query`/`Criteria`/`BasicQuery`.
29. [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query plans, indexed scans và chi phí reconciliation.
30. [MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/) — nguồn tham khảo export/backup/mongodump; không tự coi một dump là snapshot online consistent nếu không đúng phương pháp.

### 27.5. Câu hỏi bắt buộc trước khi dùng một câu lệnh

1. Source/target cùng database hay **hai clusters**? `$lookup` có dùng được không?
2. Snapshot/cut đã được xác minh hay đang so data live ở hai thời điểm?
3. MongoDB version/FCV hỗ trợ operator/validator/index semantics này không?
4. Numeric values là long/Decimal128 hay string/double, có precision loss không?
5. Tenant, currency, date/timezone và soft-delete scope có giống nhau ở hai bên?
6. Aggregate có thể dùng index không? Có chạy quá tải primary hoặc mất CDC window không?
7. Kết quả diff được ghi vào đâu, ai có quyền đọc, có lộ PII không?
8. Nếu phát hiện lỗi, có remediation version-aware và recheck/rollback không?

## 28. Kết luận

Đối soát trong **tiến hóa dữ liệu MongoDB** là quá trình xác nhận **cùng một tập thực thể nghiệp vụ** vẫn giữ **đúng giá trị và đúng các ràng buộc** sau khi thay đổi biểu diễn vật lý, đồng thời không phá vỡ quyền truy cập hoặc logic giao dịch.

Một bộ kiểm có sức thuyết phục phải trả lời được cả bốn câu hỏi:

1. **Số lượng:** Có đủ tất cả business keys, đúng từng tenant/partition và không có duplicates/extra records ngoài policy không?
2. **Kiểu dữ liệu:** Required fields, BSON types, missing/null, numeric precision, dates và arrays có đúng contract không?
3. **Ràng buộc:** Unique keys, JSON Schema, reference integrity, trạng thái và tenant isolation có được bảo vệ không?
4. **Kết quả nghiệp vụ:** Order totals, ledger balances, inventory, payments, lifecycle và privacy/retention có còn đúng không?

Khi hệ thống còn tiếp tục ghi, tất cả kiểm tra phải dựa trên **snapshot hoặc watermark logic được phối hợp**, không so hai con số lấy ở hai thời điểm tùy ý. Với data lớn, dùng **partition counts, canonical fingerprints, streaming exact diff và bounded workloads**; với lỗi critical, phải **quarantine, điều tra, sửa có audit và chạy lại kiểm chứng**, không được mặc định bằng 0 hoặc đưa vào ngoại lệ chung.

**Migration chỉ nên được chấp nhận khi có bằng chứng đối soát đồng nhất về số lượng, kiểu BSON, ràng buộc và bất biến nghiệp vụ tại cùng một mốc dữ liệu, cùng khả năng giải thích mọi ngoại lệ và phục hồi nếu cutover thất bại.**
