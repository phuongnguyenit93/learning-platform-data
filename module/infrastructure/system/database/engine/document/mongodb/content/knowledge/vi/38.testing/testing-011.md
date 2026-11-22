# Kiểm thử di chuyển dữ liệu và phục hồi bản sao lưu

Một lần di chuyển MongoDB có thể kết thúc mà không có lỗi trên terminal nhưng vẫn làm mất dữ liệu, sinh bản ghi trùng, sai kiểu BSON hoặc khiến ứng dụng không còn đáp ứng độ trễ mong muốn. Tương tự, một backup có thể được đánh dấu `SUCCESS` nhưng **không thể phục hồi đúng mốc thời gian, đúng quyền truy cập hoặc trong thời hạn mà nghiệp vụ yêu cầu**.

Vì vậy, kiểm thử migration và restore không chỉ là thử chạy `mongodump`, `mongorestore` hay so sánh tổng số document. Cần kiểm chứng **toàn bộ hợp đồng dữ liệu và khả năng phục vụ**: dữ liệu đúng, trạng thái nhất quán, index/ràng buộc/metadata đúng, ứng dụng kết nối được, luồng thay đổi không mất, hiệu năng chấp nhận được, và sự cố có thể khôi phục theo kế hoạch.

Bài học **“Kiểm thử di chuyển dữ liệu và phục hồi bản sao lưu”** trong chương **Kiểm thử** xây dựng một quy trình thực hành có thể áp dụng cho MongoDB standalone, replica set, sharded cluster, Atlas và self-managed. Nội dung tập trung vào phương pháp thiết kế test, các bước chuẩn bị, câu lệnh quan sát, kịch bản lỗi, đánh giá RPO/RTO, và bằng chứng để quyết định **GO/NO-GO**.

> **Định nghĩa thành công:** Di chuyển dữ liệu thành công khi **tập dữ liệu đích đúng với trạng thái nguồn đã cam kết tại mốc đối chiếu**, các invariant/metadata quan trọng được giữ và ứng dụng hoạt động bình thường. Khôi phục backup thành công khi **có thể dựng lại trạng thái được bảo đảm tại recovery point đã chọn**, dữ liệu dùng được và RPO/RTO đạt yêu cầu. Hai tiêu chí này phải được kiểm tra riêng.

---

## 1. Phân biệt migration, backup và restore

| Hoạt động | Mục tiêu chính | Nguy cơ điển hình |
|---|---|---|
| Data migration | Chuyển dữ liệu sang hệ thống/phiên bản/schema/cluster đích | Thiếu/trùng/sai dữ liệu, lỗi chuyển đổi, mất writes trong cutover |
| Schema migration | Thay cấu trúc documents hoặc các ràng buộc | Mất field, sai type, duplicate key, index không phù hợp |
| Version upgrade | Đổi phiên bản MongoDB và các thành phần tương thích | FCV, behavior thay đổi, driver/OS incompatibility |
| Backup | Tạo recovery artifact/restore point | Backup không nhất quán, thiếu collection, không có keys |
| Restore | Khôi phục dữ liệu từ backup | Recovery sai mốc, lỗi index/metadata, vượt RTO |
| Disaster recovery | Phục hồi dịch vụ sau sự cố rộng | DNS, app configuration, dependencies, loss window |
| Reconciliation | Đối soát dữ liệu nguồn và đích | Bỏ sót sai khác khi chỉ so counts |
| Cutover | Chuyển clients/traffic sang đích | Split-brain writes, stale reads, rollback khó |

Các thao tác này có thể xảy ra trong cùng một dự án, nhưng phải có **test cases và tiêu chí đạt riêng**. Di chuyển sang cluster mới không tự chứng minh backup ở cluster mới vẫn phục hồi được. Restore thành công cũng không tự chứng minh business app chạy đúng trên schema mới.

## 2. Những kịch bản MongoDB thường cần kiểm thử

1. **MongoDB self-managed → MongoDB Atlas**.
2. **Atlas cluster A → Atlas cluster B**, khác region hoặc topology.
3. **Standalone → replica set** theo procedure được hỗ trợ.
4. **Replica set → sharded cluster**, có thiết kế shard key.
5. **Nâng MongoDB Server major version**, gồm thay đổi FCV theo quy trình.
6. **Thay đổi schema BSON**: đổi tên field, tách/gộp collection.
7. **Backfill dữ liệu lịch sử** hoặc chuyển dữ liệu sang collection mới.
8. **Logic export/import** giữa collections hoặc services.
9. **Phục hồi từ backup trước release**.
10. **Point-in-time recovery (PITR)** sau xóa nhầm hoặc sự cố logic.
11. **Khôi phục vào region khác** khi mất vùng chính.
12. **Diễn tập disaster recovery** để xác nhận thời gian phục hồi.
13. **Khôi phục subset collection** phục vụ điều tra hoặc sửa lỗi.
14. **Chuyển từ một cấu hình encryption/KMS sang cấu hình được hỗ trợ khác**.
15. **Khôi phục Search/Vector Search workloads** khi index cần đồng bộ lại.

Không nên dùng một kịch bản demo đơn giản cho mọi trường hợp: một collection 1.000 documents trên standalone không mô phỏng được sharded transactions, replication lag, index build hoặc lượng dữ liệu hàng trăm GiB.

## 3. Mô hình trách nhiệm và phạm vi

Trước khi chạy test, xác định:

```text
Business owner
     │
     ├── Xác nhận dữ liệu nào quan trọng và RPO/RTO
     │
Application team
     │
     ├── Test schema, queries, transactions, workflows
     │
DBA / Database platform
     │
     ├── Backup/restore, topology, indexes, consistency
     │
Security team
     │
     ├── Data masking, IAM, KMS, TLS, audit
     │
SRE / Operations
     │
     ├── Load/failover, runbook, monitoring, GO/NO-GO
     │
     ▼
Verified migration / restore
```

Các vai trò có thể thuộc cùng một nhóm ở dự án nhỏ, nhưng **trách nhiệm kiểm tra và người phê duyệt** vẫn cần rõ ràng.

### 3.1. Những điều phải ghi thành văn bản

- Source deployment/database/collections;
- Target deployment/database/collections;
- Cấu trúc MongoDB hiện tại và đích;
- MongoDB Server và Feature Compatibility Version (FCV);
- App/driver/ODM versions;
- Các schema transformations;
- Topology replica set/sharding;
- Số lượng documents, size/index size;
- Quy tắc xử lý dữ liệu mới trong thời gian copy;
- RPO/RTO;
- Maintenance window/cutover;
- Rollback/recovery strategy;
- Phạm vi bảo mật dữ liệu khi thử nghiệm;
- Tiêu chí dừng và owner.

## 4. Định nghĩa ba loại tính đúng đắn

Một bản migration/restore cần được kiểm tra ở ba cấp.

### 4.1. Tính đúng đắn cấu trúc

- Database và collection mong muốn tồn tại;
- Đúng collection type (regular, time-series, capped...) nếu áp dụng;
- Đúng document validation rules;
- Đúng index definitions;
- Đúng unique/TTL/partial index semantics;
- Đúng collation;
- Đúng view definitions;
- Đúng sharding và shard key metadata;
- Đúng quyền users/roles theo kế hoạch.

### 4.2. Tính đúng đắn dữ liệu

- Không thiếu documents phải có tại mốc;
- Không trùng business keys;
- Không tự sinh dữ liệu ngoài phạm vi;
- `_id`/tenantId/relationships đúng;
- Dữ liệu nested/arrays đầy đủ;
- Decimal128, NumberLong, Date, ObjectId đúng type;
- Null và missing fields không bị đánh đồng;
- Các bản ghi xóa hoặc tombstones được phản ánh;
- Tổng tiền, trạng thái, số dư và các invariant nghiệp vụ đúng.

### 4.3. Tính đúng đắn vận hành

- Ứng dụng truy vấn được;
- Authentication/authorization đúng;
- Read/write concern và transactions hoạt động;
- Change streams hoặc CDC tiếp tục xử lý;
- Backup tiếp theo hoạt động;
- Performance và resource usage chấp nhận được;
- Failover/rollback/recovery có thể thực hiện;
- Search/Vector Search index đủ sẵn sàng nếu sản phẩm cần.

**Đếm đủ document chưa chứng minh ba nhóm yêu cầu này đã được đáp ứng.**

## 5. Định nghĩa trạng thái dữ liệu cần so sánh

Một câu hỏi quan trọng:

> Nguồn và đích phải giống nhau **ở thời điểm nào**?

Nếu nguồn đang tiếp tục ghi trong khi copy kéo dài nhiều giờ, so sánh source hiện tại với destination vừa copy xong sẽ tạo ra sai khác **mong đợi**.

Ví dụ:

```text
12:00    T0: bắt đầu snapshot/copy
12:10        Có 10.000 writes mới
13:00    T1: copy ban đầu hoàn tất
13:15        CDC bắt kịp đến watermark W
13:20    T2: cutover với write fence
13:25        Target trở thành source of truth
```

Các test phải nêu rõ:

- Snapshot time T0;
- CDC resume point/watermark W;
- Cutover instant T2;
- Những writes nào nằm trước/sau mốc;
- Khi nào nguồn bị khóa ghi hoặc ngừng routing;
- Trạng thái nào chính thức được coi là đúng.

### 5.1. Không dùng thời gian đồng hồ ứng dụng thay cho database consistency

Clock skew giữa nodes có thể khiến `createdAt` hoặc `updatedAt` không phản ánh commit order. Khi cần bắt đúng stream changes, dùng cơ chế MongoDB hỗ trợ như oplog/change streams và resume token, không chỉ lấy “mọi document có updatedAt lớn hơn giờ local”.

### 5.2. Tạo một reconciliation contract

Ví dụ:

```yaml
migrationId: customer-move-2026-11
sourceCluster: cluster-A
targetCluster: cluster-B
sourceNamespace: commerce.orders
targetNamespace: commerce.orders
scope:
  tenants: all
  status: all
pointOfComparison:
  type: snapshot-plus-cdc-watermark
expected:
  documentIdentity: [tenantId, orderId]
  preserveFields: [amountCents, status, createdAt]
  transformVersion: v2
  uniqueConstraints: [tenantId, orderId]
  allowedDifferences:
    - migrationAudit.generatedAt
```

Đây là **contract minh họa**, không phải định dạng MongoDB mặc định. Nó giúp mọi người cùng hiểu **được phép khác gì và bắt buộc giống gì**.

## 6. Những chỉ số RPO, RTO, RLO

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa chấp nhận được theo thời gian.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận được để khôi phục chức năng.
- **RLO (Recovery Level Objective)** đôi khi được dùng nội bộ để diễn đạt mức chức năng/dịch vụ tối thiểu khi recovery; không phải mọi tổ chức dùng thuật ngữ này.

Ví dụ:

```text
RPO: 10 phút
RTO: 60 phút

Thời điểm sự cố: 14:00
Đã phục hồi tới: 13:56
Dịch vụ hoạt động lúc: 14:42
```

Trong một kịch bản được đo chính xác, lost-window 4 phút và recovery time 42 phút đều trong mục tiêu. Tuy nhiên phải xác minh **commit point thực**, không chỉ timestamp tên file backup hoặc lúc bắt đầu bấm nút restore.

### 6.1. Recovery không chỉ là server chạy

RTO thường nên đo đến khi **dịch vụ quan trọng có thể phục vụ**:

```text
Incident declared
     │
     ▼
Recovery triggered
     │
     ▼
MongoDB data restored
     │
     ▼
Indexes / auth / networking ready
     │
     ▼
Application smoke tests pass
     │
     ▼
Critical customer workflows available  ← RTO endpoint
```

Nếu database mở cổng TCP nhưng chưa có index quan trọng, CDC chưa resume và payment workflow lỗi, chưa nên tuyên bố dịch vụ đã hồi phục hoàn toàn.

## 7. Kiểm thử backup khác việc chỉ có backup job

Một backup artifact có thể:

- Thiếu namespaces;
- Chụp dữ liệu không nhất quán;
- Thiếu oplog để PITR;
- Không tương thích target server/tooling;
- Được mã hóa nhưng mất KMS key;
- Hỏng hoặc chưa được upload xong;
- Chứa dữ liệu đúng nhưng không có users/roles cần thiết;
- Không chứa hoặc không khôi phục được những thành phần bên ngoài MongoDB;
- Quá lớn khiến restore vượt RTO.

Do đó test phải gồm **backup generation → artifact verification → restore → integrity/functional validation → timing**.

### 7.1. Backup “SUCCESS” là tín hiệu ban đầu

Một công cụ báo `SUCCESS` có thể chỉ chứng minh job đã tạo artifact theo kiểm tra nội bộ của tool. Không được tự suy ra:

- RTO đạt;
- Điểm phục hồi đúng;
- Mọi business invariants đúng;
- Mọi KMS keys sẵn sàng;
- MongoDB Search indexes tự phục hồi xong;
- Có thể áp dụng procedure tương tự trên sharded cluster.

**Restore drill là bằng chứng mạnh hơn backup job status.**

## 8. Các phương pháp backup MongoDB cần kiểm thử riêng

| Phương pháp | Cách hoạt động khái quát | Điểm kiểm chứng |
|---|---|---|
| Atlas Cloud Backup | Snapshot/continuous backup theo tier và cấu hình | Chính sách retention, restore target, PITR support |
| `mongodump`/`mongorestore` | Logical BSON dump/restore | Snapshot consistency, namespace, metadata, indexes |
| Filesystem/block snapshot | Ảnh vật lý của storage | Quiescence/consistency, journal, toàn bộ files |
| Oplog-based/PITR | Base backup + log thay đổi | Oplog window, recovery point, operation order |
| Backup agent/vendor | Theo quy trình sản phẩm | Compatibility, encryption, restore drill |
| Application-level export | CSV/JSON/custom pipeline | Type fidelity, completeness, metadata |

### 8.1. Logical dump không mặc nhiên nhất quán

Trong lúc `mongodump` đọc collection, các clients có thể đang update/insert/delete. Nếu không có cơ chế snapshot/point-in-time được hỗ trợ, dữ liệu dump có thể phản ánh **những thời điểm khác nhau**.

Một số chế độ như `mongodump --oplog` hỗ trợ nhất quán theo oplog trong **những điều kiện triển khai cụ thể**, nhưng không phải lựa chọn chung cho mọi topology hoặc sharded cluster. Cần tra đúng tài liệu MongoDB Database Tools và hướng dẫn backup theo deployment.

### 8.2. Snapshot volume cũng cần consistency

Chụp riêng data files khi `mongod` đang ghi mà không theo quy trình hỗ trợ có thể tạo artifact không phục hồi được. Với sharded cluster, chụp các shard ở các thời điểm ngẫu nhiên còn có thể làm metadata/data không khớp.

Không xây DR policy từ câu “cloud disk có nút snapshot” nếu chưa thực hiện restore drill đúng topology.

### 8.3. Replica set không phải backup

Ba replicas cùng lưu phiên bản dữ liệu đã bị xóa nhầm bởi một lệnh hợp lệ sẽ không tự khôi phục business state trước lệnh đó. Replication hỗ trợ availability, **backup/PITR** hỗ trợ khôi phục trạng thái theo thời điểm.

## 9. Lập ma trận kiểm thử

Một ma trận thực tế:

| Nhóm test | Mục tiêu | Bằng chứng | Mức ưu tiên |
|---|---|---|---|
| Inventory | Không bỏ sót collection/index/view | Source/target catalog | Critical |
| Document count | Không mất/trùng số lượng | Counts theo namespace/tenant | Critical |
| Field/type fidelity | Giữ BSON semantics | Golden records, type counts | Critical |
| Business invariants | Tổng tiền/trạng thái đúng | Aggregation/reconciliation | Critical |
| Index constraints | Unique/TTL/partial đúng | `listIndexes` + negative tests | Critical |
| Writes during copy | Không mất delta | Watermark/CDC replay | Critical |
| Cutover | Không có hai nơi nhận write | Write fence/audit | Critical |
| Backup restore | Có artifact khôi phục được | Restore drill logs | Critical |
| RPO/RTO | Đạt mục tiêu đã công bố | Timeline/commit watermark | Critical |
| Authorization | Không lộ tenant/PII | Security tests | Critical |
| Driver/API | Kết nối/CRUD/transactions | Integration tests | High |
| Query performance | Không regression nặng | p95/p99, explain | High |
| Failover | Phục hồi khi mất member/node | Staging chaos tests | High |
| Search/CDC | Index/event catch-up | Lag/consumer checks | High khi dùng |
| Batch/report jobs | Không lỗi sau data move | Run logs | Medium/High |
| Rare edge cases | Null, arrays, large docs | Fixtures | High |

Có thể thêm tiêu chí theo nghiệp vụ. Một hệ thống tài chính sẽ ưu tiên bất biến số dư/giao dịch hơn một trang báo cáo phụ.

## 10. Chuẩn bị môi trường test cô lập

Không restore bản sao production trực tiếp lên một cluster đang có dữ liệu hoạt động khác.

Một môi trường nên có:

```text
Dedicated restore target
   │
   ├── Không public inbound access
   ├── RBAC theo nguyên tắc tối thiểu
   ├── Encryption/TLS/KMS
   ├── Network routing tách production
   ├── Đủ disk/CPU/RAM
   ├── Driver/DB Tools tương thích
   ├── Có monitoring/alert
   └── Cleanup/retention policy
```

### 10.1. Kiểm tra namespace rất quan trọng

Những thao tác như `mongorestore --drop`, `db.dropDatabase()` hoặc tạo index mới có thể xóa/thay dữ liệu. Trước khi chạy, cần kiểm tra:

- MongoDB URI trỏ đúng cluster thử;
- Database name chính xác;
- Namespace mapping đúng;
- Credential đúng scope;
- Không có production application traffic;
- Có snapshot/backup của đích nếu cần.

### 10.2. Bảo vệ PII

Dữ liệu production được copy sang staging/DR drill vẫn là dữ liệu nhạy cảm. Nếu dùng dữ liệu thật, phải tuân thủ policy cho phép, masking, encryption, kiểm soát truy cập và retention.

Không đăng sample documents chứa email, phone, địa chỉ, secret hoặc thông tin thanh toán lên ticket/log chung.

## 11. Inventory dữ liệu nguồn

Trước migration, cần biết chính xác những gì cần chuyển.

Một danh mục có thể bao gồm:

```text
Databases
 Collections
  - Collection options/validators
  - Document counts and sizes
  - Indexes and constraints
  - Collation
  - Views
  - Time-series/capped settings
 Users/roles (theo phạm vi backup/migration)
 Sharding metadata
 GridFS / files nếu có
 Search/Vector indexes
 Change stream consumers
 External dependencies
```

### 11.1. Lệnh `mongosh` chỉ đọc

```javascript
const dbSource = db.getSiblingDB("commerce");

printjson(dbSource.getCollectionNames());
printjson(dbSource.getCollectionInfos());

printjson(dbSource.orders.getIndexes());

printjson(dbSource.runCommand({
  collStats: "orders",
  scale: 1024 * 1024
}));
```

Quyền truy cập và hỗ trợ lệnh tùy deployment/version. `collStats` cung cấp thông tin kích thước theo semantics storage engine, không tự là bảo đảm một snapshot.

### 11.2. Không đọc một node rồi coi là toàn cluster

Với replica set, cần quan sát replication lag và member health. Với sharded cluster, phải kiểm tra dữ liệu/metadata qua đường truy cập được hỗ trợ (`mongos`) và khi cần theo từng shard.

### 11.3. Inventory phải có thời điểm

Nếu nguồn đang tăng 10.000 documents/phút, count đo hôm qua không còn là expected count cho migration hôm nay. Ghi:

```text
Timestamp UTC
Topology
Source version/FCV
Namespace
Count method
Filters
Snapshot/watermark
Measurement owner
```

## 12. Fixture: bộ dữ liệu biên phải có

Một bộ test chỉ gồm documents “đẹp” dễ bỏ qua lỗi chuyển đổi.

Nên có các cases:

- `_id` kiểu `ObjectId`, String hoặc kiểu được business cho phép;
- `NumberInt`, `NumberLong`, `Double`, `Decimal128`;
- Date trước 1970, vùng giờ và daylight saving (nếu ứng dụng liên quan);
- `null` và field missing;
- Array rỗng, array dài, nested object;
- Unicode tiếng Việt, emoji, ký tự kết hợp;
- Strings rỗng/dài và collation-sensitive;
- Values âm/0/rất lớn;
- Duplicate business keys trong dữ liệu lỗi có chủ đích;
- Record đã soft-delete;
- TTL expired/near expiration;
- BSON document gần giới hạn kích thước;
- Transactions có nhiều documents;
- Cross-tenant IDs trùng trong phạm vi business;
- Documents thuộc nhiều shard keys;
- Valid/invalid schema records theo giai đoạn.

### 12.1. Ví dụ fixture

```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "T-01",
  orderNo: "A-0001",
  amount: NumberDecimal("999999999.9999"),
  quantity: NumberLong("9007199254740993"),
  createdAt: ISODate("2026-11-14T02:30:00.000Z"),
  note: "Đơn hàng – thử Unicode 🧪",
  optionalValue: null,
  tags: ["ưu tiên", "quà tặng"],
  nested: {
    flag: true,
    code: 0
  }
}
```

Trường `quantity` lớn hơn độ chính xác integer an toàn của JavaScript Number. Nếu export qua JSON thông thường rồi parse thành `Number`, có thể bị làm tròn, trong khi BSON Long vẫn giữ giá trị.

### 12.2. `null` khác field missing

```javascript
{ _id: 1, x: null }
{ _id: 2 }
```

Hai documents không giống nhau về cấu trúc. Một migration có thể vô tình biến missing thành null hoặc ngược lại, ảnh hưởng partial indexes, validation và queries.

## 13. Test chuyển đổi BSON không mất thông tin

MongoDB lưu dữ liệu theo BSON; nhiều công cụ xuất sang JSON/CSV hoặc qua ngôn ngữ khác có thể thay đổi type.

| Giá trị nguồn | Lỗi thường gặp | Hệ quả |
|---|---|---|
| `ObjectId` | Chuyển thành String không chủ ý | Join/lookup theo `_id` thất bại |
| `NumberLong` lớn | Convert sang JS double | Mất precision |
| `Decimal128` | Parse thành `double` | Sai tiền/tổng |
| `Date` | Chuyển thành string local timezone | Sai mốc thời gian |
| Binary/UUID | Đổi representation | Không đọc được ID |
| `null`/missing | Tự điền defaults | Query/partial index thay đổi |
| Arrays | Flatten/sắp lại | Sai business semantics |
| Nested document | Đổi tên field không đồng bộ | Application mapping lỗi |
| Collation-sensitive string | Lowercase bừa | Dữ liệu không phục hồi nguyên bản |
| Timestamp/BSON special types | Dùng string | Mất semantics |

### 13.1. Extended JSON

MongoDB có **Extended JSON** để biểu diễn các kiểu BSON trong JSON có cấu trúc bổ sung. Nếu bắt buộc export dạng text, cần chọn canonical/relaxed mode đúng mục đích và kiểm thử vòng chuyển:

```text
BSON source
   → Extended JSON (theo mode đã chọn)
   → Parser
   → BSON target
   → Type and value comparison
```

Không coi JSON.stringify thông thường là cơ chế backup MongoDB bảo toàn kiểu BSON.

### 13.2. Round-trip test

Một test tốt:

1. Ghi fixture vào collection thử.
2. Đọc lại bằng MongoDB Driver.
3. Export và import theo migration path.
4. Đọc document đích.
5. So sánh cả **giá trị và BSON type**.
6. So sánh behavior các queries liên quan.
7. Kiểm tra index/unique constraints.

## 14. So sánh document counts: bước đầu, chưa phải kết luận

Dùng:

```javascript
db.getSiblingDB("commerce").orders.countDocuments({
  tenantId: "T-01"
});
```

Nếu dữ liệu được cố định tại cùng snapshot/watermark, count nguồn và đích nên khớp sau khi áp dụng transformation rules.

### 14.1. Khi count có thể khác đúng theo thiết kế

Migration có thể:

- Loại records hết hạn;
- Gộp duplicates theo business rule;
- Tách một document thành nhiều documents;
- Bỏ những fields/collections cũ;
- Chuyển một số records sang archive.

Do đó cần **expected transformation formula**:

```text
Source eligible documents: 1,000,000
Excluded by approved retention: 20,000
Rejected with documented invalid data: 30
Expected target documents: 979,970
```

Không tự loại 30 records mà vẫn tuyên bố đạt nếu chúng chưa được xử lý theo policy.

### 14.2. Count dưới tải có thể biến động

Nếu source còn writes và target còn CDC replay, counts ở hai thời điểm khác nhau không có nghĩa migration sai. Phải so ở **cùng logical point** hoặc dùng reconciliation theo watermark.

### 14.3. `estimatedDocumentCount()` không dùng để đối soát chính xác

Một estimated count có thể dựa vào metadata, phù hợp cho quan sát sơ bộ nhưng không thay exact count theo predicate/snapshot khi cần chứng minh completeness. `countDocuments()` có thể tốn tài nguyên trên collection lớn; cần chọn index/cửa sổ phù hợp.

## 15. So sánh phân bố thay vì chỉ tổng count

Giả sử:

```text
Source total: 10,000,000
Target total: 10,000,000
```

Vẫn có thể mất 5.000 records tenant A và thừa 5.000 records tenant B.

Một kiểm tra:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Tương tự có thể group theo:

- Tenant;
- Status;
- Ngày/tháng;
- Shard key ranges;
- Document type;
- Product category;
- Soft-delete flag.

### 15.1. Aggregate business totals

Ví dụ:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      orders: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Đối soát `totalAmount` chỉ có ý nghĩa nếu cùng loại dữ liệu tiền, cùng định nghĩa eligible orders và cùng mốc. Với Decimal128 cần giữ precision.

### 15.2. Các checks nên cố định thành báo cáo

```text
count_by_tenant
count_by_status
count_by_day
amount_sum_by_currency
min/max_createdAt
duplicates_by_business_key
missing_required_fields
null/type_distribution
```

Các biểu đồ đẹp không thay bảng expected/actual/difference có thể đối chiếu.

## 16. Kiểm tra thiếu/trùng bằng business key

Ví dụ business identity của `orders` là `(tenantId, orderNo)`.

### 16.1. Tìm duplicate ở đích

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        orderNo: "$orderNo"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 100 }
]);
```

Đây là kiểm tra read-only nhưng có thể quét dữ liệu lớn và gây tải; cần lập kế hoạch chạy và index phù hợp.

### 16.2. Đối soát key sets

Một cách nguyên tắc:

```text
sourceKeys = tập business keys ở source tại watermark W
targetKeys = tập business keys ở target tại watermark W

missing = sourceKeys - targetKeys
extra   = targetKeys - sourceKeys
```

Đối với dữ liệu lớn, không kéo hàng trăm triệu keys về JVM RAM. Có thể:

- Chia key ranges/tenants;
- Hash canonical records theo partition;
- External sort/merge join;
- Dùng pipeline đối soát thích hợp;
- Export key lists ra storage được bảo vệ;
- Lưu diagnostics cho partitions sai.

### 16.3. Anti-pattern: kiểm 100 records đầu

Nếu `find().limit(100)` đều khớp, điều đó chỉ chứng minh 100 records tương ứng, không chứng minh 100 triệu records đúng. Sample testing có giá trị bổ sung nhưng không thay **full reconciliation** khi dữ liệu quan trọng yêu cầu.

## 17. Canonical hashing và checksums

Hash có thể giúp so sánh nội dung theo partition mà không phải in từng document.

Tuy nhiên, một hash đáng tin cần xác định **canonical serialization**:

1. Chọn đúng fields cần so;
2. Chuẩn hóa theo rule migration;
3. Bảo toàn phân biệt BSON types;
4. Đảm bảo thứ tự keys cố định khi serialization;
5. Với arrays, giữ thứ tự nếu business coi có ý nghĩa;
6. Thống nhất handling missing/null;
7. Thống nhất timezone/decimal;
8. Chọn thuật toán hash phù hợp, như SHA-256.

### 17.1. Ví dụ tư duy

```text
Partition: tenant T-01, createdAt 2026-11-14
Source:
  record_count = 50,000
  canonical_hash = abc...

Target:
  record_count = 50,000
  canonical_hash = abc...
```

Nếu hai phía có cùng canonical rules, đây là bằng chứng mạnh hơn chỉ so counts. Nhưng hash vẫn không thay business test, index/metadata test và cơ chế xác nhận mốc nhất quán.

### 17.2. Không chỉ băm raw JSON

Hai documents có field order khác nhau hoặc biểu diễn NumberLong/Decimal128 khác nhau có thể tạo JSON strings khác dù dữ liệu logic phù hợp. Ngược lại, JSON thường có thể làm tròn số rất lớn. Cần design canonicalization có version và test fixtures.

### 17.3. Không dựa duy nhất vào `dbHash`

MongoDB có lệnh `dbHash` trong những ngữ cảnh/phiên bản nhất định, nhưng kết quả và điều kiện sử dụng có những giới hạn, nhất là khi dữ liệu đang thay đổi hoặc deployment sharded. Không coi `dbHash` là giải pháp migration verification phổ quát cho mọi topology và business transformation.

### 17.4. Lưu evidence hash an toàn

Hash phân vùng có thể bị dùng để suy đoán nếu input ít giá trị. Không công khai raw keys/PII; đặt report trong hệ thống kiểm soát truy cập.

## 18. Kiểm tra index, validators, collection options

Data có đủ nhưng index thiếu thì query có thể từ milliseconds thành seconds, hoặc unique constraint không được enforce.

### 18.1. Lệnh kiểm tra

```javascript
const targetDb = db.getSiblingDB("commerce");

printjson(targetDb.orders.getIndexes());

printjson(targetDb.getCollectionInfos({
  name: "orders"
}));
```

So sánh:

- Index keys **đúng thứ tự**;
- `unique`, `sparse`, partial filter;
- `expireAfterSeconds`;
- `collation`;
- `hidden` và options version-specific;
- Collection validator;
- Time-series/capped options;
- Sharding metadata;
- Views;
- Search indexes riêng.

### 18.2. Không so index chỉ bằng tên

Hai indexes cùng tên nhưng key/options khác nhau không tương đương. Đổi field names hoặc key order có thể ảnh hưởng query plan và uniqueness.

### 18.3. Index trên source và target có thể cố ý khác

Nếu migration tối ưu query performance, index list có thể khác theo thiết kế. Test phải so với **desired index manifest**, không nhất thiết byte-for-byte với source.

### 18.4. Index build hoàn thành chưa?

Một migration không được tính hoàn tất nếu index build còn đang lỗi hoặc chưa sẵn sàng cho query cần thiết. Phải chờ trạng thái/command completion theo server/version và xác nhận bằng actual catalog cùng workload test.

## 19. Kiểm thử unique index bằng negative case

Với index unique `(tenantId, orderNo)`, trên collection **staging** có thể thử chèn trùng business key và mong đợi duplicate-key rejection.

```javascript
db.orders_test.insertOne({
  _id: "TEST-UQ-1",
  tenantId: "T-01",
  orderNo: "A-001"
});

db.orders_test.insertOne({
  _id: "TEST-UQ-2",
  tenantId: "T-01",
  orderNo: "A-001"
});
```

Nếu collection đã tạo đúng unique compound index, lệnh insert thứ hai phải bị từ chối theo constraint. Đây là **test có ghi dữ liệu**: chỉ dùng collection được tạo riêng cho test và cleanup có kiểm soát.

### 19.1. Kiểm tra phạm vi multi-tenant

Trường hợp:

```text
T-01 / A-001
T-02 / A-001
```

có thể phải được phép nếu unique theo tenant. Ngược lại, nếu ứng dụng đòi unique toàn cục, phải có test trái ngược.

### 19.2. Null/missing và partial unique

Unique index có semantics cụ thể cho null/missing. Partial unique chỉ áp dụng cho subset documents. Phải test trường hợp records vào/ra partial filter và duplicate sau soft-delete/restore.

## 20. TTL: nguy cơ lớn trong restore drill

Nếu backup chứa documents với `expiresAt` đã ở quá khứ so với thời điểm restore, TTL index có thể khiến MongoDB bắt đầu xóa chúng sau restore.

Ví dụ:

```javascript
{
  _id: "SESSION-001",
  expiresAt: ISODate("2026-11-01T00:00:00Z")
}
```

Restore ngày 14/11/2026 với TTL `expireAfterSeconds: 0` khiến document đã đủ điều kiện xóa. Khi bạn đếm documents vài phút sau, count có thể giảm dù restore ban đầu đã nạp đúng artifact.

### 20.1. Các câu hỏi cần kiểm

- TTL index có tồn tại trong backup/target không?
- Các records đã đủ điều kiện expire bao nhiêu?
- Dữ liệu phục hồi cần khôi phục **lịch sử** hay chỉ trạng thái active?
- Có policy an toàn để quan sát trước khi TTL dọn không?
- Có thể dùng isolated environment theo procedure được phép không?
- Cần giữ bằng chứng restore trước khi TTL chạy không?
- Backup/restore process có hỗ trợ cách xử lý TTL theo yêu cầu không?

### 20.2. Không vô hiệu TTL production một cách tùy hứng

Thay đổi TTL policy có thể làm vi phạm retention hoặc giữ sessions đã hết hạn. Test cần thiết kế môi trường/điều kiện có kiểm soát, không sửa một chính sách dữ liệu nhạy cảm chỉ để counts khớp.

### 20.3. TTL không chạy đúng từng millisecond

MongoDB TTL monitor hoạt động nền. Không thiết kế test đòi document biến mất tại thời điểm chính xác từng millisecond.

## 21. Kiểm tra users, roles và security sau migration/restore

Một restore có thể khôi phục data nhưng **không tự bảo đảm** mọi tài khoản và cơ chế kết nối hoạt động như cũ.

Phải xác định theo backup/migration method:

- Users và custom roles có được copy không?
- App service accounts được cấp đúng quyền không?
- SCRAM/X.509/OIDC/LDAP/Kerberos nếu dùng có hoạt động?
- TLS certificates, CA truststore và hostnames đúng?
- KMS/encryption keys còn khả dụng?
- Client-Side Field Level Encryption/Queryable Encryption metadata phù hợp?
- Atlas project/network/private endpoints đúng?
- Audit logging vẫn bật?
- Không có quyền quá rộng trong restore target?

### 21.1. Không dùng root để che vấn đề

Nếu app không thể query với service account, test bằng root sẽ không phát hiện lỗi RBAC. Phải chạy smoke tests bằng **đúng identity** hoặc identity được mô phỏng có privileges tương đương.

### 21.2. Authorization negative test

Với multi-tenant, test:

```text
Tenant A chỉ đọc được records A.
Tenant A không thể query tenant B.
A service không có quyền index-admin không thể drop index.
Untrusted user không thể truy cập backup artifacts.
```

Không chỉ kiểm tra quyền đọc hợp lệ, cần kiểm tra **truy cập không hợp lệ bị từ chối**.

## 22. Di chuyển offline: cách test đơn giản hơn

**Offline migration** thường có giai đoạn ngừng writes:

```text
Stop/fence writes
      │
      ▼
Take consistent backup/export
      │
      ▼
Copy to target
      │
      ▼
Restore/import
      │
      ▼
Run reconciliation
      │
      ▼
Application smoke/performance
      │
      ▼
Switch traffic
      │
      ▼
Resume writes on target
```

Ưu điểm:

- Dễ xác định source state cố định;
- Dễ đối soát counts/hashes;
- Ít logic CDC và conflict;
- Rollback trước mở target writes đơn giản hơn.

Nhược điểm:

- Có downtime/maintenance window;
- Với dữ liệu lớn, thời gian copy/restore có thể vượt RTO;
- Các background writers phải thực sự được chặn;
- External services cũng cần pause/coordination.

### 22.1. “Ngừng API” chưa chắc ngừng writes

Có thể còn:

- Scheduled jobs;
- Kafka consumers;
- Change stream processors;
- Batch imports;
- Cron maintenance;
- Other microservices;
- Admin scripts;
- TTL deletions.

Cần có **write fence** đáng tin và metrics xác nhận không còn writer không mong đợi.

## 23. Di chuyển online: snapshot cộng CDC

**Online migration** cho phép source tiếp tục nhận writes trong khi sao chép ban đầu.

Một sơ đồ:

```text
                        Source MongoDB
                              │
             ┌────────────────┴─────────────────┐
             ▼                                  ▼
       Initial copy                       Change stream / CDC
             │                                  │
             ▼                                  ▼
       Target MongoDB ←────────────────── Delta apply
             │
             ▼
       Reconciliation to watermark
             │
             ▼
        Write fence / cutover
             │
             ▼
      Target becomes authoritative
```

### 23.1. Những test bắt buộc

- Initial snapshot có trạng thái nhất quán theo method;
- CDC bắt đầu đúng điểm để không bỏ lỡ deltas;
- Inserts/updates/deletes được áp dụng;
- Event order được bảo đảm theo quy tắc cần thiết;
- Retry không tạo double effects;
- Resume token được lưu an toàn;
- Tạm mất kết nối được xử lý;
- Oplog window đủ;
- Deltas được apply khi cùng document thay đổi nhiều lần;
- Transaction events không bị phá semantics;
- Trước cutover, target bắt kịp đến watermark đã cam kết;
- Sau cutover, không có writes nào tới source cũ.

### 23.2. Chỉ lưu `updatedAt` có thể không đủ

`updatedAt` có thể:

- Bị bỏ sót ở một số write paths;
- Bị cập nhật bằng clock lệch;
- Không thể hiện deletes;
- Không giữ transaction order;
- Trùng timestamps.

Vì vậy cần thiết kế change capture thích hợp, có resume token/operation ordering và cơ chế reconciliation.

## 24. Change streams và resume tests

Một consumer MongoDB change stream có thể đọc các sự kiện phù hợp với deployment/version.

Ví dụ khung `mongosh`:

```javascript
const stream = db.getSiblingDB("commerce")
  .orders.watch();

try {
  // Trong staging, consumer sẽ gọi next/tryNext theo logic kiểm thử.
  // Lưu resume token an toàn sau khi apply thành công sang target.
} finally {
  stream.close();
}
```

Đoạn trên chỉ minh họa API. Trong production cần một consumer thật, checkpoint, retry và chính sách bảo mật.

### 24.1. Resume token là state quan trọng

Một consumer cần lưu mốc đã **apply thành công** để sau crash không bỏ qua events. Nếu lưu resume token trước khi ghi target, job có thể đánh dấu event đã xử lý dù target chưa cập nhật.

### 24.2. Test sự cố ở đúng ranh giới

Trong staging:

```text
Read event E1
  │
  ▼
Apply E1 to target
  │
  ▼
Crash before checkpoint
```

Khi restart, E1 có thể được xử lý lại. Target apply phải idempotent hoặc có deduplication/business version guard.

### 24.3. Oplog window

Nếu consumer dừng quá lâu và token không còn resumable, có thể cần resnapshot/reconciliation. Đừng tự cho rằng `resumeAfter` sẽ hoạt động vô hạn trong mọi tình huống.

### 24.4. Transactions và ordering

Một transaction có thể tạo nhiều thay đổi. Nếu migration tách sự kiện và apply không theo đúng business semantics, target có thể tạm hoặc vĩnh viễn thấy trạng thái không hợp lệ. Test rollback/commit và ordering với transaction được hỗ trợ.

## 25. Dual writes: tránh split brain

Một số thiết kế migration cho ứng dụng ghi đồng thời vào source và target:

```text
Application
   ├── write source
   └── write target
```

Đơn giản trên sơ đồ nhưng nguy hiểm:

```text
Source write: SUCCESS
Target write: TIMEOUT
Application: trả 200 hay 500?
```

Hoặc ngược lại.

### 25.1. Hai databases không tự nằm trong một transaction chung

Nếu source và target là hai cluster độc lập, không mặc định có distributed transaction nguyên tử cho cả hai.

### 25.2. Các cách giảm rủi ro

- CDC/outbox thay dual-write trực tiếp khi hợp lý;
- Idempotency key;
- Versioned writes;
- Durable retry queue;
- Write-ahead event log;
- Reconciliation;
- Failure injection tests;
- Một nơi được chỉ định làm authoritative source tại mỗi pha.

### 25.3. Không để cả source và target cùng là primary writers sau cutover

Nếu cả hai nhận ghi không có conflict protocol, có thể xuất hiện split-brain data. Cutover phải định nghĩa rõ **write ownership** và cơ chế chặn đường ghi cũ.

## 26. Cutover test: thời điểm rủi ro cao

Một kế hoạch cutover khái quát:

```text
1. Confirm target baseline healthy
2. Confirm CDC lag below approved threshold
3. Announce change window
4. Fence/pause source writes
5. Drain in-flight requests and consumers
6. Apply final deltas to watermark W
7. Run critical reconciliation
8. Switch app routing/connection configuration
9. Validate target smoke + business invariants
10. Resume writes only on target
11. Monitor stabilization
```

### 26.1. Cần stop criteria từng bước

Ví dụ:

```text
If CDC cannot reach watermark W
or duplicate-key/data-integrity discrepancy remains:
  NO-GO; do not enable target writes.
```

### 26.2. DNS TTL và connection pools

Đổi DNS/URI không đảm bảo mọi application connections được chuyển ngay. Drivers có pools, topology discovery và retry semantics. Test:

- Pods cũ đã drain;
- All worker processes dùng target URI;
- Không còn writes trên source;
- Read/write monitoring ở cả hai phía;
- Secret rotation/config reload;
- Background jobs và connectors.

### 26.3. Cutover không kết thúc khi API trả 200

Một API có thể trả 200 nhưng đọc cache cũ, thiếu search results hoặc chạy trên một tenant chưa migrate. Kiểm tra business workflows và traffic theo namespace/tenant.

## 27. Rollback khác restore

Cần ba thuật ngữ riêng:

- **App rollback:** chạy lại application/configuration cũ.
- **Migration rollback:** quay trở lại nguồn dữ liệu cũ hoặc áp dụng reverse migration.
- **Backup restore:** dựng dữ liệu tại một recovery point.

### 27.1. Sau khi target đã nhận writes mới

Nếu target trở thành source of truth lúc 15:00 và có 10.000 writes mới, quay DNS về source cũ lúc 15:20 mà không replay dữ liệu có thể **làm mất 10.000 writes**.

Một rollback an toàn có thể yêu cầu:

- Fence target writes;
- Capture target-only changes;
- Reconcile/replay về source cũ;
- Verify correctness;
- Confirm old app/schema compatibility;
- Switch routing;
- Observe.

Không hứa rollback chỉ cần “đổi connection string lại”.

### 27.2. Schema mới có thể không đọc được bởi app cũ

Nếu migration đã thay đổi BSON type, field names hoặc constraints, app cũ có thể không tương thích. Cần **expand-and-contract migration** hoặc giữ backward-compatible schema trong rollback window.

### 27.3. Restore backup cũng có thể làm mất writes

Khôi phục snapshot trước cutover có nghĩa phục hồi tới recovery point đó; writes sau mốc có thể mất trừ khi có PITR/replay/reconciliation.

## 28. Phục hồi từ `mongodump` và `mongorestore`: kiểm thử theo quy trình

Ví dụ **trên môi trường thử, với quyền hợp lệ**:

### 28.1. Tạo logical backup

Trong shell Unix-like:

```bash
mongodump \
  --uri "$SOURCE_MONGODB_URI" \
  --db "commerce" \
  --archive="/secure-backups/commerce-test.archive.gz" \
  --gzip
```

Lệnh này **không tự cam kết** consistency point-in-time trong khi source đang ghi; việc chọn phương pháp backup nhất quán phải căn cứ topology và tài liệu Database Tools. File chứa dữ liệu nhạy cảm, phải mã hóa/bảo vệ.

### 28.2. Khôi phục sang target rỗng, cô lập

```bash
mongorestore \
  --uri "$ISOLATED_TARGET_MONGODB_URI" \
  --archive="/secure-backups/commerce-test.archive.gz" \
  --gzip
```

Ví dụ giả định target phù hợp và không chứa dữ liệu cần giữ. Trên Windows PowerShell, cú pháp biến môi trường khác với `$SOURCE_MONGODB_URI`.

**Không thêm `--drop` hoặc nhắm URI vào production khi chỉ định thử restore**, vì có thể xóa dữ liệu đích. Nếu cần xử lý collections đã tồn tại, phải theo runbook đã phê duyệt.

### 28.3. Các điểm bắt buộc xác minh

- Công cụ dump/restore exit status;
- Log errors/warnings;
- Backup file size/checksum;
- Namespace mapping;
- Actual collections;
- Counts/partition checks;
- Index build/unique constraints;
- Views/collection options;
- Documents/typed fixtures;
- App smoke;
- KMS/auth/TLS/roles theo phương pháp;
- RTO measured end-to-end.

### 28.4. Không suy ra users/roles tự được sao chép

`mongodump` theo database scope và các công cụ khác có cách xử lý users/roles riêng. Cần xác minh backup artifact và restore procedure **có bao gồm các thành phần bảo mật dự kiến hay không**, không mặc định một archive của `commerce` là bản sao toàn bộ cluster.

## 29. Oplog-consistent logical backup: giới hạn phải hiểu

Một số mô hình backup từ replica set hỗ trợ tùy chọn oplog để tạo recovery-consistent logical dump. Nhưng các điều kiện liên quan:

- Source topology;
- Dump scope;
- Tool/server versions;
- Oplog availability;
- Thời gian dump;
- Operations đồng thời;
- Những thao tác không được hỗ trợ trong cửa sổ dump;
- Target restore procedure.

Không chạy `mongodump --oplog` như “bí quyết nhất quán” cho bất cứ sharded cluster nào.

### 29.1. Test thực tế nên có marker writes

Trong staging:

```text
Before backup window:
  Write marker PRE

During backup window:
  Write marker MID

After chosen recovery point:
  Write marker POST
```

Sau khôi phục, kiểm tra tập markers đúng với recovery point đã yêu cầu. Không suy từ timestamp marker ứng dụng mà bỏ qua commit/transaction semantics.

### 29.2. Oplog replay cũng có lỗi có thể xảy ra

Nếu oplog interval thiếu, phiên bản tool không hỗ trợ hoặc restore thiếu metadata, việc replay có thể lỗi. Một successful base dump không tự chứng minh PITR restoration khả thi.

## 30. Atlas backup/PITR restore drill

Với Atlas, việc backup/restore và PITR phụ thuộc **cluster tier, tính năng, region, retention và cấu hình**. Không giả định mọi Free/Flex/Dedicated tier có cùng bảo đảm hoặc nút restore.

Một kịch bản:

1. Xác định backup policy và tier hỗ trợ.
2. Chọn snapshot hoặc PITR point trong khoảng cho phép.
3. Chọn isolated target region/cluster.
4. Xác minh project/network/IAM/KMS.
5. Thực hiện restore theo Atlas workflow được hỗ trợ.
6. Chờ cluster/data/index readiness.
7. Xác nhận `db.version()`/FCV/driver compatibility nếu liên quan.
8. Test integrity/uniqueness/queries/Search/CDC.
9. Đo RPO/RTO.
10. Lưu evidence và hủy target đúng policy.

### 30.1. KMS là dependency của recovery

Nếu encrypted backup không thể decrypt vì customer-managed key đã bị thu hồi/mất quyền, backup artifact gần như vô ích. Test recovery với đúng quyền/key path, không chỉ dùng môi trường root đã được cấu hình sẵn mọi quyền.

### 30.2. Restore test target có thể có connection strings khác

Sau restore, cần cập nhật app configuration/allowlist/private endpoints. Test cả network và TLS hostname verification; không sử dụng `tlsInsecure=true` để vượt lỗi cấu hình.

### 30.3. Search index readiness

Nếu dùng Atlas Search/Vector Search, việc collection data sẵn sàng không luôn đồng nghĩa Search indexes đã queryable/caught up. Ghi điều kiện phụ thuộc vào thời điểm RTO của dịch vụ nếu user workflow yêu cầu Search.

## 31. Khôi phục sharded cluster: khó hơn replica set đơn lẻ

Một sharded cluster:

```text
Application
     │
   mongos
     │
     ├── Config server replica set
     ├── Shard A replica set
     ├── Shard B replica set
     └── Shard C replica set
```

Nếu chụp snapshots từng shard ở các thời điểm khác nhau mà không có cơ chế phối hợp được hỗ trợ, metadata và dữ liệu có thể không nhất quán.

### 31.1. Những điều phải kiểm thử

- Config metadata restored correctly;
- Shard keys;
- Chunk placement/metadata;
- Mongos connectivity;
- Sharded collection identity;
- Cross-shard reads/aggregations;
- Distributed transactions;
- Unique index constraints;
- Balancer/chunk migration operations;
- Data consistency per shard;
- Backup/PITR recovery point globally meaningful.

### 31.2. “Tôi thấy document trên một shard” chưa chứng minh cluster đúng

Cần query qua `mongos` và theo application path. Sau restore, kiểm tra shards/members sẵn sàng và tránh trực tiếp sửa config metadata.

### 31.3. Không tự viết script snapshot thủ công cho toàn cluster

Quy trình sharded backup đòi hỏi consistency rất cụ thể. Ưu tiên phương pháp được MongoDB/Atlas/backup vendor hỗ trợ cho topology và phiên bản đó, rồi diễn tập restore.

## 32. Replica set: test dữ liệu và tính sẵn sàng

Trong replica set, migration/restore phải xác nhận:

- Primary/secondary roles;
- Members healthy;
- Replication lag;
- Majority availability;
- Write concern behavior;
- Read preference;
- Oplog window;
- Election/failover;
- Backup agent connectivity.

Lệnh read-only:

```javascript
rs.status();
```

Chỉ dùng khi kết nối vào deployment phù hợp và có quyền.

### 32.1. Khi nào read-after-write có thể khác nhau?

Một ứng dụng đọc từ secondary có thể thấy dữ liệu cũ do replication lag, kể cả khi primary vừa nhận write. Nếu test đối soát trên secondary, phải nêu read preference/concern và mốc dữ liệu.

### 32.2. Không kiểm tra phục hồi bằng cách restart cả replica set production

Chaos/failover tests chỉ nên chạy trong staging hoặc môi trường có phê duyệt rõ, với stop conditions và người trực. Kiểm tra HA là quan trọng nhưng không được biến test thành sự cố thật.

## 33. Kiểm thử Point-in-Time Recovery (PITR)

Một PITR drill chất lượng phải chứng minh phục hồi về một **thời điểm trước hành động lỗi**, không chỉ chọn bất kỳ snapshot.

Giả sử:

```text
09:00  Snapshot base
09:10  Order A committed
09:20  Order B committed
09:30  Accidental delete of order collection
09:40  Incident detected
09:50  Desired recovery point = 09:29
```

Test expected:

- Order A có;
- Order B có;
- Delete lúc 09:30 không xuất hiện;
- Writes sau 09:29 không mặc nhiên có;
- Các transactions được xử lý theo recovery method.

### 33.1. PITR chọn mốc có thể thực thi

Không phải mọi mốc thời gian tùy ý trong ngày đều có thể restore: phải nằm trong retention/continuous backup window, dữ liệu oplog/backup coverage đầy đủ và phương pháp hỗ trợ.

### 33.2. Đồng hồ và commit point

Xác nhận recovery point bằng metadata của backup tool/MongoDB, không chỉ dựa vào datetime do client gửi. Clock skew, transaction commit time và timezone có thể ảnh hưởng.

### 33.3. Test ranh giới

Kiểm tra records/transactions:

- Commit trước mốc;
- Commit đúng biên;
- Commit sau mốc;
- Transaction bắt đầu trước nhưng commit sau;
- Delete trước/sau;
- TTL/background actions.

Expected result phải được định nghĩa theo semantics của phương pháp PITR đang dùng.

## 34. Failure injection test: phát hiện vấn đề trước production

Một migration có thể chạy tốt khi không có sự cố nhưng thất bại khi network chập chờn hoặc worker restart.

Thử trong staging:

| Sự cố giả lập | Điều muốn chứng minh |
|---|---|
| Kill/restart migration process | Resume không bỏ records |
| Mất kết nối MongoDB tạm thời | Retry có giới hạn, reconnect |
| Secondary stepdown/failover | Driver phục hồi, không double writes |
| Cursor timeout | Checkpoint/keyset an toàn |
| CDC consumer crash | Token và idempotent replay đúng |
| Source write xảy ra khi copy | Final reconciliation đúng |
| Target disk gần giới hạn | Dừng an toàn, không đánh dấu complete |
| Duplicate unique key | Failed records được xử lý |
| KMS/key permission revoked trong test | Recovery fail rõ ràng, không bypass security |
| Restore target thiếu index | Postcondition fail |
| Search index rebuilding | Readiness gate đúng |
| Backup artifact hỏng | Integrity check phát hiện |
| Job crash sau apply trước checkpoint | Retry không double effects |

### 34.1. Không retry vô hạn

Một retry policy nên có:

```text
Transient errors → bounded exponential backoff + jitter
Permanent data errors → dead-letter/remediation
Authentication errors → stop/security review
Disk full → stop/capacity recovery
Unknown write outcome → reconciliation/idempotency
```

### 34.2. Không coi network timeout là “chưa ghi”

Một write có thể đã được server commit nhưng ACK không về. Nếu retry `$inc` như thao tác mới, có thể tăng số tiền/counter lần thứ hai. Dùng idempotency keys, version guards và kiểm tra trạng thái.

## 35. Thiết kế migration idempotent

Một thao tác idempotent cho cùng input có thể được chạy lại mà không làm thay đổi kết quả ngoài ý định.

Ví dụ upsert theo business identity:

```javascript
db.order_exports.updateOne(
  {
    _id: {
      tenantId: "T-01",
      orderNo: "A-0001"
    }
  },
  {
    $set: {
      status: "PAID",
      amountCents: NumberLong("249900")
    }
  },
  { upsert: true }
);
```

Nếu input giữ nguyên, thao tác `$set` thường hội tụ về cùng trạng thái.

### 35.1. `$inc` không tự idempotent

```javascript
db.totals.updateOne(
  { _id: "T-01" },
  { $inc: { amountCents: 249900 } }
);
```

Chạy hai lần sẽ cộng hai lần. Nếu migration phải tính tổng, có thể dùng `$set` tới giá trị tổng đã tính theo một version/watermark, hoặc dùng một hệ thống deduplication theo event ID.

### 35.2. Upsert vẫn cần unique keys

Hai workers cùng upsert theo filter không có unique index phù hợp có thể tạo duplicate documents. Unique business key và concurrency reconciliation là phần của test.

### 35.3. Bản ghi mới có version cao hơn không được overwrite bởi dữ liệu cũ

Nếu migration worker đọc revision 7 rồi CDC worker đã ghi revision 8, worker cũ không được overwrite bản mới. Thiết kế atomic compare-and-set/version guard hoặc ordering phù hợp; test tình huống race.

## 36. Test schema transformation

Ví dụ chuyển từ:

```javascript
{
  _id: "ORDER-1",
  total: 249900,
  customerEmail: "alice@example.com"
}
```

sang:

```javascript
{
  _id: "ORDER-1",
  amount: {
    value: NumberDecimal("2499.00"),
    currency: "VND"
  },
  customer: {
    emailNormalized: "alice@example.com"
  }
}
```

Nếu input `total=249900` biểu diễn cents thì việc biến thành `"2499.00"` phụ thuộc **currency minor unit** và quy tắc chính xác. Với VND, không nên mặc định “cents” theo USD. Test phải định nghĩa rõ đơn vị và cách rounding. Ví dụ chỉ minh họa thay cấu trúc.

### 36.1. Golden transformation tests

Tạo bảng:

| Input | Expected output |
|---|---|
| Missing `customerEmail` | Field absent hoặc null theo contract |
| Email Unicode/case | Normalization theo policy |
| Amount 0 | Đúng 0 và đúng type |
| Amount lớn | Không overflow |
| Nested object | Không mất fields |
| Unknown enum | Reject/retain theo policy |
| Soft-deleted record | Preserve/archive theo rule |
| Invalid date | Error/dead-letter rõ |

### 36.2. Không tự sửa sai dữ liệu rồi quên báo

Migration nên ghi số records rejected/adjusted. Nếu policy cho phép bỏ invalid records, phải có expected count, owner và evidence. Không nuốt lỗi parse BSON khiến job vẫn `COMPLETED`.

### 36.3. Expand-and-contract

Khi app cũ và mới có thể cùng chạy:

```text
Expand schema
    ↓
Deploy app đọc được cả hai
    ↓
Backfill/migrate data
    ↓
Verify correctness
    ↓
Switch reads/writes
    ↓
Contract/remove old fields later
```

Điều này giảm rủi ro rollback, nhưng cần kiểm tra trường hợp dual-writing và data races.

## 37. Test index performance sau migration/restore

Index có thể tồn tại nhưng query plan mới khác.

Một query:

```javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Quan sát:

- `winningPlan`;
- `IXSCAN`/`COLLSCAN` hoặc stages tương đương;
- `totalKeysExamined`;
- `totalDocsExamined`;
- `nReturned`;
- Blocking sort;
- Execution time;
- Query targeting.

### 37.1. Khác engine/version có thể khác plan shape

Không yêu cầu tên stage giống nhau tuyệt đối giữa MongoDB versions. Quan trọng là query returns đúng và performance/resource đáp ứng SLO.

### 37.2. Warm vs cold cache

Sau restore, cache có thể lạnh. Một query đầu tiên có thể chậm hơn. Test cả:

- Cold-start latency;
- Warm-cache steady state;
- Mixed read/write workload;
- Peak traffic;
- Background index build;
- Replication catch-up;
- Search index readiness.

### 37.3. Không chỉ đo mean

Read p95/p99 có thể tăng dù mean gần như không đổi. Một recovery chỉ mở được API nhưng p99 rất xấu có thể chưa đạt mục tiêu thực tế.

## 38. Test application flows sau restore

Một số smoke tests tối thiểu:

1. App dùng đúng URI/TLS/auth;
2. Health check/ping có ý nghĩa;
3. Đọc record có thật;
4. Ghi record thử trên collection được phép;
5. Unique validation và tenant scope;
6. Aggregation/report mẫu;
7. Transaction nghiệp vụ;
8. Pagination/sort;
9. Search/Vector Search nếu có;
10. Background consumer/CDC;
11. Backup agent hoạt động;
12. Critical business workflow end-to-end.

Ví dụ domain:

```text
Create order
    ↓
Reserve inventory
    ↓
Confirm payment
    ↓
Update order status
    ↓
Read customer history
    ↓
Generate invoice
```

Không thực hiện thanh toán thật hoặc gửi email thật trong restore drill. Sử dụng sandbox providers và test identities.

## 39. Kiểm thử dữ liệu liên quan bên ngoài MongoDB

Ứng dụng thường không chỉ có MongoDB.

```text
MongoDB
  ├── Search index
  ├── Redis cache
  ├── Kafka topics
  ├── Object storage/GridFS
  ├── Data warehouse
  ├── Notification service
  ├── Payment provider
  └── Analytics dashboards
```

Nếu restore MongoDB về một mốc cũ nhưng Kafka consumer hoặc warehouse đã tiến tới thời điểm mới, hệ thống có thể không nhất quán.

### 39.1. External consistency plan

Phải quyết định:

- Cache invalidate/rebuild;
- Search index rebuild/catch-up;
- CDC resume/reseed;
- Warehouse reconciliation;
- External side effects có cần bù trừ không;
- Job scheduler restart từ watermark nào;
- Payment reconciliation với provider thế nào;
- Các files/blobs tham chiếu còn tồn tại không.

### 39.2. Khôi phục một phần có thể nguy hiểm

Restore riêng `orders` về hôm qua trong khi `payments` vẫn là hôm nay có thể tạo order/payment mismatch. Cần xác định **recovery consistency domain** theo business transactions.

## 40. GridFS, files và lớn hơn một document

Nếu ứng dụng lưu files bằng GridFS, cần kiểm tra cả metadata và chunks tương ứng, ví dụ các collections theo bucket naming.

Không chỉ so số documents trong `fs.files` mà quên `fs.chunks`.

Test:

- File count;
- Chunks đầy đủ;
- File hashes theo format dùng trong ứng dụng;
- Download/stream một số files lớn và nhỏ;
- MIME/metadata;
- Access control;
- Orphan chunks;
- Delete behavior.

Công cụ backup/migration phải bao gồm namespaces cần thiết; một filter chỉ copy business collections có thể bỏ GridFS.

## 41. Time-series/capped collections và giới hạn đặc thù

Với time-series/capped collections, phục hồi cần xét:

- Collection options;
- Time field và meta field;
- TTL/retention;
- Bucket storage;
- Index support theo MongoDB version;
- Compression/space usage;
- Query semantics;
- Ingest order/time;
- Capped rollover/truncation behavior.

Không biến một time-series collection thành regular collection rồi coi như không thay đổi gì nếu ứng dụng phụ thuộc feature đó.

### 41.1. Thử nghiệm với dữ liệu đã quá hạn

Nếu restore time-series/logs từ backup cũ và TTL policy loại dữ liệu quá hạn, expected count phải xét retention. Không khôi phục để điều tra lịch sử rồi để TTL tự xóa bằng môi trường không được chuẩn bị.

## 42. Data privacy và bảo vệ backup artifact

Backup/restore test thường chạm tới toàn bộ dữ liệu người dùng.

Bắt buộc có:

- Encryption at rest;
- Encryption in transit;
- KMS/key custody;
- Access logs;
- Least privilege;
- Network isolation;
- Approved data masking khi dùng outside production;
- Retention/deletion của restore target;
- Không dùng tài khoản chung admin không có audit;
- Không lưu secrets trong script/CI logs;
- Không paste raw sample PII vào tickets;
- Chặn backup bucket public access;
- Quy trình xử lý khi test phát hiện leak.

### 42.1. Kiểm tra khả năng phục hồi của keys

Một encrypted backup mà recovery environment không dùng được KMS key có thể không phục hồi. DR drill phải kiểm tra cả **quyền và đường truy cập key**, không chỉ nội dung file.

### 42.2. Test khôi phục là thay đổi có thể ghi dữ liệu

Ngay cả khi không tác động source, restore vào target có thể tạo records nhạy cảm trong một hệ mới. Phải có phê duyệt bảo mật và cleanup.

## 43. Theo dõi metrics của migration

Một dashboard nên bao gồm:

| Metric | Ý nghĩa |
|---|---|
| Source documents eligible | Quy mô nguồn theo contract |
| Documents copied | Số records đọc/chuyển |
| Documents acknowledged | Số records đã ghi có xác nhận |
| Failed/rejected records | Các bản ghi cần xử lý |
| CDC lag | Mức target chậm hơn source |
| Last applied resume token | Checkpoint luồng thay đổi |
| Throughput documents/s | Tốc độ di chuyển |
| Network bytes/s | Băng thông |
| Read/write p95/p99 | Tác động latency |
| Connection pool wait | Bottleneck phía driver |
| CPU, disk IOPS/latency | Saturation |
| Replication lag | Tác động lên replica set |
| Index build progress | Readiness của đích |
| Reconciliation mismatches | Sai khác dữ liệu |
| RPO estimate | Cửa sổ mất dữ liệu |
| Restore elapsed time | Tác động RTO |
| Search indexing lag | Readiness Search |

### 43.1. Phân biệt copied với committed

Nếu worker đọc 1 triệu records nhưng chỉ nhận ACK của 980.000 writes, không được báo migration 100% hoàn tất.

### 43.2. Counters là tích lũy

Để tính throughput:

\[
\text{documents/s} = \frac{\Delta \text{acknowledged documents}}{\Delta t}
\]

Xử lý counter resets khi process restart và phân tách metrics theo job/worker/collection.

### 43.3. Quan sát cả source và target

Một migration gây 90% disk utilization trên source có thể làm production API chậm dù target khỏe. Đo CPU/cache/disk/network của **cả hai phía** và đưa load limits vào runbook.

## 44. Đo tốc độ phục hồi có cấu trúc

Một timeline:

```text
14:00 Incident declared
14:05 Recovery decision approved
14:10 Restore target provisioned
14:15 Restore initiated
14:38 Data copy completed
14:45 Indexes verified
14:50 Security/network ready
14:57 App smoke tests passed
15:05 Critical business operations restored
```

Nếu RTO được định nghĩa từ incident declaration đến critical service restored thì đo 65 phút, **không phải 23 phút** chỉ từ lúc restore bắt đầu đến lúc copy xong.

### 44.1. Ghi rõ điểm bắt đầu/kết thúc

Tùy SLO/DR policy, có thể dùng incident detection, declaration hoặc recovery activation làm mốc. Nhưng phải công bố trước và dùng nhất quán trong diễn tập.

### 44.2. Kích thước dữ liệu ảnh hưởng mạnh

Một restore 10 GiB không chứng minh restore 10 TiB đạt cùng RTO. Cần workload/size representative hoặc phép dự báo được kiểm chứng qua drill đủ quy mô.

### 44.3. DR drill phải có khó khăn thực tế

Nếu team dùng sẵn một cluster đã restore trước và chỉ switch URI, đó không chứng minh thời gian **tạo infrastructure, lấy backup, decrypt, restore, build indexes và validate** khi sự cố thật.

## 45. Automation scripts và điều kiện an toàn

Có thể tự động hóa:

- Inventory;
- Read-only catalog comparison;
- Counts và aggregates theo partition;
- Hash reports;
- Backup artifact checksum;
- Staging restore orchestration;
- Smoke tests;
- Metrics collection;
- Evidence export;
- Alert gating.

Nhưng những hành động có thể phá dữ liệu như:

```text
dropDatabase
drop collection
mongorestore --drop
shard metadata changes
setFeatureCompatibilityVersion
rs.stepDown
```

phải có quy trình riêng, approval và môi trường đúng.

### 45.1. Tách DRY_RUN và APPLY

```text
DRY_RUN:
  read configuration
  inspect source and target
  generate plan and risk report
  perform no mutations

APPLY:
  validate approved change ID
  confirm target identity
  execute procedure
  collect evidence
  validate postconditions
```

### 45.2. Không kết luận “script exit code 0” là dữ liệu đúng

Script phải chạy các postconditions và trả trạng thái failed nếu reconciliation hoặc business checks không đạt. Cần phân biệt:

- Command execution success;
- Transfer success;
- Data completeness;
- Data correctness;
- Application readiness.

## 46. Ví dụ bảng kiểm dữ liệu cho collection `orders`

| Kiểm tra | Nguồn tại mốc W | Đích tại mốc W | Kết quả |
|---|---|---|---|
| Tổng orders eligible | 5.000.000 | 5.000.000 | PASS |
| Orders T-01 | 1.200.000 | 1.200.000 | PASS |
| Orders PAID | 3.600.000 | 3.599.999 | FAIL |
| Tổng amount PAID | 900.000.000.000 | 899.999.750.100 | FAIL |
| Duplicate `(tenantId,orderNo)` | 0 | 0 | PASS |
| Null/missing `currency` | 21 | 25 | FAIL |
| Unique index | Có | Có | PASS |
| App read smoke | Thành công | Thành công | PASS |
| App write smoke | Thành công | Thành công | PASS |

**Số liệu chỉ minh họa.** Không coi migration PASS vì tổng số documents trùng khi một partition và tổng tiền lệch.

### 46.1. Xử lý mismatch

Mỗi sai khác cần:

```text
Mismatch ID
Namespace + partition
Expected vs actual
Impact
Suspected cause
Owner
Remediation plan
Re-test result
Approval
```

### 46.2. Không tự sửa record ở target mà không để lại dấu

Nếu sửa trực tiếp 20 records để counts khớp mà không có mapping/lineage, có thể tạo lỗi mới. Sửa phải idempotent, có audit và giữ hợp đồng nguồn/đích.

## 47. Tạo runbook phục hồi

Một mẫu ngắn:

```text
CHANGE / DRILL ID:
DATE:
BUSINESS OWNER:
DBA OWNER:
SRE ON-CALL:

SOURCE:
  Cluster / topology:
  MongoDB version / FCV:
  Namespace scope:
  Write status:
  Backup source:

TARGET:
  Isolated cluster:
  Version / FCV:
  Region:
  Storage / capacity:
  Security configuration:

RECOVERY:
  Backup artifact ID:
  Snapshot timestamp:
  PITR target:
  Expected RPO:
  Expected RTO:
  KMS/access prerequisites:

EXECUTION:
  Preconditions:
  Exact approved procedure:
  Stop conditions:
  Rollback actions:
  Communication:

VALIDATION:
  Data counts:
  Partition reconciliation:
  BSON type checks:
  Business invariants:
  Indexes / validators:
  Auth / tenant isolation:
  App smoke:
  Search / CDC:
  p95/p99:
  Actual RPO/RTO:

DECISION:
  GO / HOLD / NO-GO / RECOVER

EVIDENCE:
  Logs (redacted):
  Metric snapshots:
  Reconciliation report:
  Approvals:
```

### 47.1. Runbook phải có người nhận sự cố

Không đủ nếu chỉ có một file README nhưng không ai biết ai có quyền chuyển traffic, pause source writers hoặc sử dụng KMS keys.

### 47.2. Không lưu passwords trong runbook

Dùng secret references, IAM/workload identity và kiểm soát truy cập. Tên backup bucket và network details cũng cần phân loại bảo mật.

## 48. GO/NO-GO gates

| Hạng mục | GO khi | NO-GO khi |
|---|---|---|
| Backup artifact | Có và integrity verified | Không tìm thấy/hỏng |
| Restore drill | Đã phục hồi thành công | Chưa chạy hoặc thất bại |
| RPO | Recovery point đủ gần | Lost window vượt budget |
| RTO | Dịch vụ đạt trong thời hạn | Vượt time budget |
| Data completeness | Required key sets đầy đủ | Missing/extra không được phép |
| Data correctness | Types/invariants đúng | Sai tiền/trạng thái/relationships |
| Index/metadata | Đúng required contract | Thiếu unique/TTL/validators quan trọng |
| CDC | Lag bắt kịp watermark | Delta gap không xử lý được |
| Cutover | Chỉ một nơi nhận writes | Split brain |
| Driver/app | Critical workflows pass | API errors hoặc mapping lỗi |
| Security | TLS/auth/KMS/ACL pass | Rò dữ liệu hoặc bypass |
| Search/analytics | Đáp ứng feature SLO | Index không sẵn sàng mà không có fallback |
| Performance | p95/p99 trong guardrails | Severe regression |
| Rollback | Path có điều kiện và evidence | Không có cách kiểm soát writes mới |
| Ownership | Có approver/on-call | Không có người chịu trách nhiệm |

Một dòng `UNKNOWN` ở phần critical không nên tự coi như `PASS`.

## 49. Sau cutover hoặc restore: thời gian ổn định

Dù các test vừa qua đều thành công, vẫn phải theo dõi:

- Writes vào source cũ có còn không;
- Target CDC lag và checkpoint;
- Query p95/p99;
- Error rate và retries;
- Replication health;
- Disk/cache/CPU;
- Backup/PITR jobs;
- TTL deletions;
- Search/Vector index synchronization;
- Batch/BI/ETL jobs;
- Business totals;
- User reports;
- Network/authentication alerts.

### 49.1. Quan sát nhiều chu kỳ

Một batch chạy mỗi đêm có thể phát hiện vấn đề sau 24 giờ. Một báo cáo cuối tháng có thể chỉ chạy một lần/tháng. Stabilization window cần phản ánh workload thực, không chỉ 10 phút sau deploy.

### 49.2. Khi nào được xóa source cũ?

Chỉ sau khi:

- Rollback window đóng;
- Target được xác nhận authoritative;
- Dữ liệu/migrations đầy đủ;
- Các consumers không phụ thuộc source cũ;
- Backup/restore ở target đã được thử;
- Retention/legal hold được đáp ứng;
- Quyền và approvals đầy đủ.

Không drop source cluster ngay sau khi một smoke test chạy thành công.

## 50. Anti-patterns cần tránh

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| Chỉ so total count | Có thể thiếu/thừa bằng nhau | Partition/key reconciliation |
| So dữ liệu ở hai mốc khác | False mismatches | Snapshot/watermark |
| Dùng JSON thường cho BSON | Mất Decimal/Long/Date | BSON/Extended JSON fidelity |
| Đếm 100 sample rồi PASS | Không chứng minh completeness | Representative/full verification |
| `estimatedDocumentCount` làm proof | Không exact theo scope | Exact/partition counts |
| Backup SUCCESS = recovery PASS | Chưa restore thử | Restore drill |
| Replica set = backup | Deletes/corruption replicate | Independent backups/PITR |
| Snapshot mỗi shard tùy ý | Metadata inconsistency | Supported sharded backup |
| Bỏ KMS keys khỏi DR plan | Artifact không giải mã | Key access test |
| Dùng root trong app smoke | Che RBAC lỗi | Service identity |
| Không thử negative authorization | Có thể lộ tenant | ACL tests |
| Không xét TTL khi restore | Data bị xóa sau import | Retention preflight |
| Source còn writers sau cutover | Split brain | Fence/monitor |
| Chỉ copy initial snapshot | Mất writes trong quá trình copy | CDC/catch-up |
| Checkpoint trước khi target ACK | Bỏ event khi crash | Commit-then-checkpoint |
| Retry `$inc` mù | Double writes | Idempotency/dedup |
| Quên deletes | Stale target records | Tombstones/CDC |
| Bỏ Search/Vector index | API Search trả rỗng | Readiness/index lag tests |
| Bỏ GridFS chunks | Files bị hỏng | File/chunk validation |
| Restore riêng orders không xét payments | Business inconsistency | Recovery domain |
| Chỉ đo data import time | RTO bị đánh giá thấp | End-to-end recovery timing |
| Dùng staging quá nhỏ | RTO/performance ảo | Representative drill |
| Không có rollback strategy | Mắc kẹt sau cutover | Write ownership/replay |
| Rollback URI là xong | Mất target-only writes | Reconciliation/reverse migration |
| Không kiểm index options | Mất unique/TTL constraints | Catalog diff |
| Không verify backup sau nâng cấp | Backup agent incompatibility | Post-change restore drill |
| Log raw PII vào report | Rò dữ liệu | Redaction/access control |
| Không xác định stop criteria | Tiếp tục khi đã mất dữ liệu | GO/NO-GO gates |

## 51. Bài tập thực hành

### Bài 1 — Xác định hợp đồng migration

Dữ liệu `orders` di chuyển từ cluster A sang B.

1. Xác định document identity.
2. Chọn recovery/migration watermark.
3. Liệt kê fields bắt buộc giữ.
4. Ghi allowed transformations.
5. Đặt business invariants và owner.

### Bài 2 — Count chưa đủ

Nguồn có 1.000.000 documents, đích cũng 1.000.000.

1. Có thể kết luận PASS không?
2. Thiết kế counts theo tenant/status/date.
3. Tìm duplicate keys.
4. So tổng tiền.
5. Cách tìm missing/extra keys trên dataset lớn?

### Bài 3 — BSON long overflow

Fixture có `NumberLong("9007199254740993")`.

1. Nếu export qua JSON/JavaScript Number có rủi ro gì?
2. Cách dùng Extended JSON/BSON?
3. Test type fidelity nào?
4. Vì sao so JSON strings không đủ?
5. Khi nào dùng `Decimal128`?

### Bài 4 — Null vs missing

Nguồn:

```javascript
{ _id: 1, x: null }
{ _id: 2 }
```

Đích có cả hai records với `x:null`.

1. Count có khớp không?
2. Dữ liệu có đúng không?
3. Kiểm thử type/presence như thế nào?
4. Partial indexes chịu ảnh hưởng gì?

### Bài 5 — Unique/partial/TTL

Một collection có unique index cho active users và TTL cho sessions.

1. Viết test unique theo tenant.
2. Viết test soft-deleted record.
3. Kiểm tra TTL candidates trước restore.
4. Vì sao TTL xóa sau restore không phải lỗi backup?
5. Khi nào là lỗi retention policy?

### Bài 6 — Restore `mongodump`

Trong staging:

1. Tạo collection test;
2. Dump theo scope có thể nhất quán;
3. Restore vào target rỗng cô lập;
4. Compare documents và indexes;
5. Test app read/write;
6. Ghi elapsed RTO và evidence.

### Bài 7 — RPO/RTO

Một ứng dụng có RPO=5 phút, RTO=45 phút.

```text
14:00 incident
14:12 recovery triggered
14:50 database restored
15:00 app healthy
last recovered commit = 13:57
```

1. Lost window là bao nhiêu?
2. RTO theo incident declaration là bao nhiêu?
3. SLO đạt hay không?
4. Nếu chỉ đo database copy time có sai gì?

### Bài 8 — PITR boundary

Chọn recovery point trước lệnh xóa nhầm.

1. Đặt marker writes trước/sau.
2. Xác định expected documents.
3. Transaction commit sau boundary xử lý sao?
4. Oplog coverage cần thế nào?
5. Đo real recovered point bằng evidence gì?

### Bài 9 — Replica set và sharding

1. Vì sao replica set không thay backup?
2. Restore sharded cluster cần nhất quán metadata thế nào?
3. Có thể snapshot từng shard tùy lúc không?
4. Test cross-shard transaction nào?
5. Read preference ảnh hưởng đối soát ra sao?

### Bài 10 — CDC crash

Consumer apply event E1 nhưng crash trước checkpoint.

1. Khi restart có thể thấy E1 nữa không?
2. Làm sao dedup?
3. Có thể checkpoint trước apply không?
4. Oplog window có ảnh hưởng gì?
5. Nếu token không còn valid thì làm sao?

### Bài 11 — Source writes trong lúc copy

Initial copy bắt đầu lúc T0, kết thúc T1, cutover T2.

1. Những writes nào có thể bị bỏ sót?
2. CDC phải bắt đầu từ đâu?
3. Chọn watermark như thế nào?
4. Làm sao kiểm tra consumer lag?
5. Khi nào được fence source?

### Bài 12 — Rollback sau cutover

Target nhận 20.000 writes mới trong 30 phút.

1. Có thể đổi URI về source ngay không?
2. Dữ liệu mới được xử lý ra sao?
3. Nêu phương án reverse replay.
4. Cần đảm bảo một write owner thế nào?
5. Khi schema target mới, app cũ có đọc được không?

### Bài 13 — Search index

Source data đã restore đầy đủ nhưng `$search` trả kết quả thiếu.

1. Data có nhất thiết mất không?
2. Kiểm tra Search index status/lag gì?
3. Phải rebuild hoặc catch-up thế nào?
4. Khi nào API có thể báo ready?
5. Test authorization đối với Search results.

### Bài 14 — Security restore drill

1. Kiểm tra encrypted backup và KMS keys.
2. Test service account thay vì root.
3. Kiểm tra tenant isolation.
4. Kiểm tra network private endpoint/TLS.
5. Lập policy cleanup restore target.

### Bài 15 — Hash đối soát

Thiết kế canonical hash cho mỗi tenant/time partition.

1. Chọn fields.
2. Giữ BSON types thế nào?
3. Null/missing phân biệt?
4. Arrays có preserve order không?
5. Cách drill down khi hash lệch?

### Bài 16 — Performance

Sau migration:

```text
Read p95: 80 ms → 420 ms
Write p95: 120 ms → 115 ms
Total docs: equal
```

1. Có được GO không?
2. Kiểm tra index catalog/explain.
3. Kiểm tra cache cold/plan changes.
4. Đo p99/API errors và CPU/disk.
5. Xác định rollback/optimization action.

### Bài 17 — Failure injection

Dựng trong staging:

- Worker kill khi copy 60%;
- DB connection loss;
- Cursor timeout;
- Duplicate key;
- Partial bulk failure;
- Full disk simulation ở target an toàn;
- Backup artifact corrupt.

Đối với mỗi kịch bản, ghi expected recovery, idempotency và điều kiện job FAILED/PASS.

### Bài 18 — DR runbook và quyết định

Một tổ chức có:

```text
Backup artifact exists: YES
Restore drill: NOT DONE
RPO proof: UNKNOWN
Index catalog: PASS
Business invariant: FAIL
Rollback: UNKNOWN
On-call owner: READY
```

1. GO hay NO-GO?
2. Những blockers cần xử lý?
3. Thiết kế restore drill.
4. Ai phê duyệt?
5. Bằng chứng nào phải lưu trước cutover?

## 52. Checklist kiểm thử migration

### Trước migration

- [ ] Xác định source/target và topology.
- [ ] Xác định business owner, DBA/SRE và on-call.
- [ ] Chọn snapshot/watermark hợp lệ.
- [ ] Xác định RPO/RTO và downtime budget.
- [ ] Inventory collections, indexes, validators, views, users/roles.
- [ ] Kiểm tra BSON types và edge cases.
- [ ] Có dữ liệu staging đại diện.
- [ ] Có backup và recovery plan.
- [ ] Xác định writes trong lúc copy xử lý thế nào.
- [ ] Có test security/tenant isolation.
- [ ] Có resource headroom và load limits.
- [ ] Có stop/rollback gates.

### Trong migration

- [ ] Đo documents copied/acknowledged/failed.
- [ ] Bảo vệ resume token/checkpoint.
- [ ] Retry idempotent, có giới hạn.
- [ ] Theo dõi CDC lag và oplog window.
- [ ] Không để source/target cùng nhận writes trái kế hoạch.
- [ ] Lưu errors và data rejects rõ.
- [ ] Theo dõi latency/CPU/disk/replication ở cả hai phía.
- [ ] Không log PII/credentials.

### Sau migration

- [ ] Counts và key sets đúng tại watermark.
- [ ] Hash/partition/business aggregates đúng.
- [ ] BSON types/nested data đúng.
- [ ] Unique/TTL/partial indexes đúng.
- [ ] Validators/views/sharding metadata đúng.
- [ ] App smoke/transaction/CDC/Search pass.
- [ ] p95/p99 và error rate trong guardrails.
- [ ] Backup ở target hoạt động và restore drill đạt.
- [ ] Source cũ không còn writes ngoài dự kiến.
- [ ] Stabilization và rollback window được quản lý.

## 53. Checklist kiểm thử restore/DR

- [ ] Backup artifact xác định được ID, timestamp và scope.
- [ ] Artifact integrity/encryption đã xác minh.
- [ ] Key access/KMS sẵn sàng.
- [ ] PITR target nằm trong retention window.
- [ ] RPO/RTO được định nghĩa trước.
- [ ] Restore target cô lập, đủ tài nguyên.
- [ ] DB Tools/Server versions tương thích.
- [ ] Quy trình đúng replica set/sharded topology.
- [ ] Không vô tình dùng `--drop` trên môi trường sai.
- [ ] Khôi phục được collection/index/metadata theo scope.
- [ ] Count + business invariants pass.
- [ ] TTL expiry behavior được đánh giá.
- [ ] Service auth/RBAC/TLS hoạt động.
- [ ] Search/Vector/CDC/GridFS được kiểm tra nếu dùng.
- [ ] App critical flows pass.
- [ ] Actual recovery point được xác minh.
- [ ] Actual end-to-end RTO được đo.
- [ ] Có post-drill report và remediation.
- [ ] Restore target/PII được cleanup đúng policy.

## 54. Tài liệu tham khảo chính thức

Khi triển khai thực tế, đối chiếu **MongoDB Server, Database Tools, Atlas tier và topology** đang sử dụng:

- [MongoDB Back Up and Restore](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB `mongodump`](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB `mongorestore`](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Atlas Cloud Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/)
- [MongoDB Atlas Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Replica Set Backups](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/)
- [MongoDB Sharded Cluster Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/#backup-and-restore-sharded-clusters)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/)
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitoring-alerts/)
- [MongoDB Search](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/)

## Kết luận

Kiểm thử di chuyển dữ liệu và phục hồi bản sao lưu trong MongoDB phải được thiết kế như **bằng chứng về tính đúng đắn và khả năng phục hồi của toàn bộ hệ thống**, không phải như việc kiểm tra một command đã trả về exit code 0.

Đối với **di chuyển dữ liệu**, cần xác định trạng thái nguồn tại một snapshot/watermark cụ thể, sau đó đối chiếu key sets, partitions, BSON types, business invariants, uniqueness, index metadata và các thành phần liên quan. Nếu nguồn vẫn tiếp tục ghi trong lúc copy, phải có **CDC/catch-up, idempotency, checkpoint và write fence** tại cutover; chỉ copy snapshot rồi đổi connection string không bảo đảm không mất dữ liệu.

Đối với **phục hồi backup**, phải thực hiện **restore drill thật** trên môi trường cô lập, kiểm tra artifact/KMS keys, dữ liệu, indexes, users/roles, Search/Vector/CDC, ứng dụng và đo **RPO/RTO theo recovery point và thời điểm dịch vụ phục vụ trở lại**. Những rủi ro như TTL xóa records sau restore, backup thiếu metadata, sharded snapshots không nhất quán, hay schema không tương thích với app cũ phải được đưa vào test ngay từ trước.

Cuối cùng, **GO/NO-GO phải dựa trên kết quả kiểm thử có thể kiểm chứng**. Nếu còn mismatch dữ liệu quan trọng, chưa có restore drill hoặc không xác định được hành động khi lỗi, dự án chưa đủ bằng chứng để chuyển traffic production.

**Di chuyển thành công nghĩa là dữ liệu đúng và dịch vụ dùng được. Backup thành công nghĩa là đã chứng minh có thể phục hồi đúng, đủ và kịp thời — ngay cả khi sự cố xảy ra đúng lúc khó khăn nhất.**

