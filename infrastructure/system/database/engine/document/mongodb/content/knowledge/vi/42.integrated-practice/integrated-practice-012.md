# Sao lưu, phục hồi, kiểm tra quyền và lập checklist vận hành MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Thực hành tổng hợp  
> **Bài học:** Sao lưu, phục hồi, kiểm tra quyền và lập checklist vận hành

## 1. Tình huống: dữ liệu bán hàng phải phục hồi được và chỉ người có quyền mới truy cập được

Giả sử bạn vận hành ứng dụng bán hàng có database `sales_lab` hoặc `sales_prod` gồm các collection `customers`, `products`, `inventory`, `orders`, `payments` và `outbox`. Một buổi sáng, nhân viên vận hành lỡ chạy thao tác cập nhật sai trên hàng nghìn đơn hàng. Bạn phát hiện bản sao lưu đêm qua tồn tại, nhưng chưa ai từng thử restore. Đồng thời tài khoản của ứng dụng đang được gán `root` vì “cho tiện”.

Có bốn câu hỏi phải trả lời trước khi gọi hệ thống là có khả năng vận hành an toàn:

1. **Backup có thật sự dùng được?** File tồn tại và có checksum chưa đủ; phải thử khôi phục, kiểm tra documents, indexes, schema, thời điểm và ứng dụng.
2. **Khôi phục tới đâu?** Backup là snapshot lúc 00:00 hay có thể khôi phục đến 09:57 trước khi ghi nhầm? Đây là câu chuyện RPO và point-in-time recovery.
3. **Ai được phép làm gì?** Tài khoản ứng dụng có cần quyền quản lý users, drop database hoặc restore không? Người đọc báo cáo có cần sửa đơn hàng không?
4. **Vận hành lặp lại ra sao?** Có lịch backup, diễn tập restore, giám sát dung lượng/oplog, xử lý cảnh báo và ghi nhật ký thay đổi không?

Bài này cung cấp quy trình thực hành từ backup logic đến khôi phục cô lập, RBAC, xác minh quyền và checklist theo chu kỳ. Ví dụ dùng MongoDB local, còn những hướng dẫn production được đánh dấu riêng vì sao lưu và khôi phục là thao tác ảnh hưởng trực tiếp tới dữ liệu.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt logical dump, snapshot storage, continuous backup và disaster recovery.
- Giải thích RPO, RTO, retention, restore point và consistency.
- Dùng `mongodump`/`mongorestore` với `--archive` và `--gzip`.
- Nhận biết giới hạn của database-only dump trong khi vẫn có writes.
- Sử dụng `--oplog`/`--oplogReplay` đúng trường hợp **full replica set dump**, không ghép sai với `--db` hoặc namespace remapping.
- Khôi phục một database sang **namespace khác**, tránh ghi đè dữ liệu gốc.
- Kiểm tra checksum, document counts, indexes, BSON types và business invariants.
- Xác minh authentication và authorization bằng `connectionStatus`, `getUser()` và negative privilege tests.
- Thiết kế least-privilege roles cho app, báo cáo, backup và restore.
- Lập checklist daily/weekly/monthly, trước/sau deploy, backup incident và restore drill.
- Ghi nhận bằng chứng phục hồi có thể kiểm toán.

### 1.2. Các quy tắc an toàn của bài

- **Không chạy `mongorestore --drop` trên production hoặc database đang hoạt động.**
- **Không dùng tài khoản `root` làm tài khoản kết nối thường trực của API.**
- **Không đặt mật khẩu trong URI commit vào Git, shell history hoặc log.**
- **Không dùng backup production chứa PII làm fixture tùy tiện trên laptop/CI.**
- **Không giả định một file backup thành công đồng nghĩa restore đã được kiểm thử.**
- **Không khởi chạy bảo mật replica set production bằng cách sao chép cấu hình lab không có auth/TLS.**
- Thực hành restore vào namespace hoặc deployment **riêng**, không chạm nguồn.
- Dữ liệu ví dụ chỉ là giả lập, không chứa số thẻ, tài khoản ngân hàng hoặc thông tin khách hàng thật.

---

## 2. Sơ đồ bảo vệ dữ liệu toàn hệ thống

```text
               API / Workers
                 │      │
            App DB user  Report DB user
                 │      │
                 ▼      ▼
        ┌───────────────────────┐
        │ MongoDB deployment    │
        │ orders / payments /   │
        │ inventory / outbox    │
        └──────────┬────────────┘
                   │
             Backup process
                   │
            (service identity)
                   │
          ┌────────▼─────────┐
          │ Backup artifact  │
          │ + metadata       │
          │ + checksum       │
          └────────┬─────────┘
                   │
         Encrypted immutable/offsite copy
                   │
               Restore drill
                   │
          ┌────────▼─────────┐
          │ Isolated restore │
          │ + verification   │
          └────────┬─────────┘
                   │
       Counts / indexes / BSON / invariants
                   │
                   ▼
         Recovery acceptance record
```

Một hệ thống đáng tin phải kiểm soát cả **đường ghi dữ liệu**, **đường tạo backup**, **quyền đọc backup**, **đường restore** và **bằng chứng dữ liệu đã được khôi phục đúng**.

---

## 3. Thuật ngữ nền tảng

| Thuật ngữ | Ý nghĩa |
|---|---|
| Backup | Bản sao có thể dùng để phục hồi dữ liệu sau một sự cố |
| Restore | Đưa dữ liệu từ backup vào hệ thống đích |
| Recovery | Khôi phục cả hoạt động dịch vụ: dữ liệu, quyền, kết nối, ứng dụng và downstream dependencies |
| RPO | Recovery Point Objective: mức dữ liệu tối đa có thể chấp nhận mất theo thời gian |
| RTO | Recovery Time Objective: thời gian tối đa để phục hồi dịch vụ theo mục tiêu |
| Retention | Thời gian giữ các bản backup/snapshots |
| PITR | Point-in-Time Recovery: phục hồi về một mốc được hỗ trợ trong recovery window |
| Consistent backup | Bản sao đại diện trạng thái nhất quán tại một thời điểm có semantics xác định |
| Restore drill | Diễn tập restore định kỳ lên môi trường cô lập để kiểm chứng khả năng khôi phục |
| Principle of least privilege | Chỉ cấp các quyền thực sự cần cho actor |
| Backup integrity | Kiểm tra artifact không hư hỏng/không bị sửa trái phép, chẳng hạn hash và mã hóa/chữ ký |
| Application-level consistency | Invariants giữa orders, payments, inventory, outbox vẫn đúng sau restore |

### 3.1. RPO khác RTO

Ví dụ:

```text
RPO = 15 phút
RTO = 2 giờ
```

Khi sự cố xảy ra lúc 10:00:

- Mục tiêu là phục hồi trạng thái **không cũ hơn khoảng 09:45**, theo RPO đã phê duyệt.
- Dịch vụ cần hoạt động lại trước khoảng 12:00, theo RTO đã phê duyệt.

Nhưng nếu chỉ backup vào mỗi đêm 00:00, bạn **không thể cam kết RPO 15 phút** trừ khi có cơ chế backup liên tục hoặc capture/replay transaction history phù hợp.

### 3.2. Backup frequency phải phù hợp RPO

| Chính sách | Khả năng mất dữ liệu có thể xảy ra |
|---|---|
| Một snapshot mỗi ngày | Có thể mất phần lớn writes từ snapshot gần nhất |
| Snapshot mỗi giờ | Có thể mất tới gần một giờ, tùy thời điểm và semantics |
| Snapshot + continuous oplog archiving/PITR | Có thể phục hồi trong recovery window theo độ phân giải/giới hạn của giải pháp |
| Không backup, chỉ replica set | Không có lịch sử phục hồi trước thao tác xóa/sửa sai có chủ đích |

Replica set **không thay thế backup**: một lệnh `deleteMany({})` hợp lệ có thể được replicate sang mọi members.

### 3.3. RTO phải tính toàn bộ chuỗi

```text
Phát hiện → xác minh → quyết định restore point
→ cấp môi trường/compute → tải/decrypt backup
→ restore dữ liệu và indexes → kiểm tra quyền
→ chạy ứng dụng smoke tests → chuyển traffic
→ theo dõi và xác nhận phục hồi
```

Đừng tính RTO chỉ bằng thời gian chạy `mongorestore`.

---

## 4. Chọn phương án backup MongoDB

### 4.1. Logical backup: mongodump/mongorestore

Ưu điểm:

- Dễ hiểu và thực hành.
- Dữ liệu BSON cùng metadata/index definitions cần thiết được xuất.
- Có thể xuất một database hoặc chọn namespace.
- Thuận tiện cho restore lab, migration và các bộ dữ liệu nhỏ/vừa.

Hạn chế:

- Chi phí đọc, serialization, CPU, network và storage.
- Với collection/database dump trong lúc vẫn có writes, không bảo đảm snapshot nhất quán toàn phạm vi.
- Không phải hệ thống continuous PITR đầy đủ.
- Restore lớn có thể mất nhiều thời gian.
- Phải kiểm tra compatibility giữa server/tools/FCV.
- User/role, topology settings và secrets có yêu cầu backup riêng.

### 4.2. Storage/physical snapshots

Ưu điểm:

- Có thể phù hợp database rất lớn và RTO khác logical restore.
- Nếu được thiết kế đúng, có thể giảm chi phí dump/restore toàn bộ BSON.

Điều kiện:

- Filesystem/storage snapshots phải nhất quán trên những volumes cần thiết.
- Quan tâm WiredTiger data files, journal, checkpoint và topology.
- Dùng quy trình MongoDB-supported, không tự copy `/data/db` đang mở rồi gọi đó là backup hợp lệ.
- Kiểm tra restore procedure trên cùng platform/storage version.

### 4.3. MongoDB Atlas Cloud Backup

Với deployment Atlas được hỗ trợ, quản lý snapshots và retention bằng backup policy. Continuous Cloud Backup, khi bật và có sẵn cho deployment/tier, kết hợp snapshots với oplog information để phục hồi tới mốc trong PITR window. Khả dụng, chi phí, độ phân giải thời điểm và giới hạn theo server/cluster type phải xem tài liệu Atlas hiện hành.

### 4.4. Replica set không phải snapshot

Replica set giúp high availability và failover, nhưng không tạo lịch sử độc lập chống:

- Human error.
- Bug migration.
- Ransomware/account compromise.
- Logic lỗi cập nhật hàng loạt.
- Schema corruption lan qua replication.
- Sự cố vượt khả năng cả cluster.

Cần backup bên ngoài failure domain của database.

### 4.5. Bảng quyết định

| Workload | Phương án khởi đầu | Bổ sung bắt buộc |
|---|---|---|
| Local learning | mongodump của database lab | Restore thử trên namespace khác |
| Integration test | Fixtures/seed deterministic | Không cần backup production |
| Small self-managed replica set | Logical backup hoặc supported snapshots | Restore drill, offsite copy, RPO/RTO |
| Large self-managed cluster | Storage/enterprise backup giải pháp phù hợp | Snapshot consistency, PITR, monitoring |
| Sharded cluster | Phương án backup hỗ trợ sharding | Consistent point across shards/config metadata |
| Atlas production | Cloud Backup/Continuous Backup nếu hỗ trợ | Policy retention/PITR, test restore, access controls |

Không chọn giải pháp chỉ dựa trên “backup tạo file được”; phải kiểm tra thời gian khôi phục và consistency.

---

## 5. Môi trường lab và phạm vi thực hành

Bài dùng database `sales_lab` gồm một số collections:

```text
sales_lab
  categories
  customers
  products
  inventory
  orders
  payments
  outbox
```

Bạn có thể dùng bộ dữ liệu giả lập của ứng dụng bán hàng hoặc tự tạo sample nhỏ. Các ví dụ sau ưu tiên **không xóa** dữ liệu đã có.

### 5.1. MongoDB local

Giả sử một MongoDB local được khởi động ở `127.0.0.1:27017`, có quyền đọc/ghi database `sales_lab`. Nếu dùng Docker và single-node replica set:

```powershell
docker ps --filter name=sales-mongo
docker exec -it sales-mongo mongosh
```

Trong mongosh:

```javascript
db.adminCommand({ ping: 1 });
db.adminCommand({ hello: 1 });
```

### 5.2. Tạo sample khi chưa có sales_lab

Chỉ làm trên một database lab do bạn sở hữu:

```javascript
const lab = db.getSiblingDB("sales_lab");
const fixed = ISODate("2026-01-01T00:00:00Z");

lab.customers.updateOne(
  { _id: "CUS-001" },
  {
    $setOnInsert: {
      fullName: "Khách hàng mẫu",
      email: "customer001@example.test",
      createdAt: fixed
    }
  },
  { upsert: true }
);

lab.products.updateOne(
  { _id: "SKU-001" },
  {
    $setOnInsert: {
      name: "Sản phẩm mẫu",
      unitPriceVnd: NumberLong("80000"),
      active: true,
      createdAt: fixed
    }
  },
  { upsert: true }
);

lab.orders.updateOne(
  { _id: "ORD-0001" },
  {
    $setOnInsert: {
      requestId: "REQ-0001",
      customerId: "CUS-001",
      status: "PAID",
      totalVnd: NumberLong("160000"),
      items: [
        {
          sku: "SKU-001",
          quantity: 2,
          unitPriceVnd: NumberLong("80000"),
          lineTotalVnd: NumberLong("160000")
        }
      ],
      createdAt: fixed
    }
  },
  { upsert: true }
);
```

Đoạn này chỉ chèn records còn thiếu theo `_id`, không ghi đè chúng khi chạy lại.

### 5.3. Xác nhận không phải production

Trước mọi lệnh backup/restore:

```javascript
db.getName();
db.adminCommand({ hello: 1 });
db.getSiblingDB("sales_lab").getCollectionNames();
```

Ghi lại môi trường, endpoint, owner, ticket và hành động được phép. Không “thử nhanh” restore trên URI từ ứng dụng production.

---

## 6. Mongodump và mongorestore là MongoDB Database Tools

Hai utilities này thuộc bộ **MongoDB Database Tools**, có phiên bản độc lập với MongoDB Server.

### 6.1. Kiểm tra công cụ

Trên host đã cài tools:

```bash
mongodump --version
mongorestore --version
```

Nếu chạy qua container có sẵn tools:

```bash
docker exec sales-mongo mongodump --version
docker exec sales-mongo mongorestore --version
```

Không phải mọi image tùy biến đều chứa Database Tools; nếu thiếu thì cài tools tương thích vào môi trường riêng hoặc dùng một utilities container được kiểm soát.

### 6.2. Version compatibility

Lưu lại:

- MongoDB Server version và Feature Compatibility Version (FCV).
- MongoDB Database Tools version.
- Source và target deployment versions.
- Các tính năng đặc biệt: time series, encrypted collections, views, sharding.

Không giả định dump từ mọi server major version đều restore được tới mọi target version.

### 6.3. Dữ liệu trong dump

Logical dump chứa collection data và metadata hỗ trợ restore collections/indexes. Nó **không đồng nghĩa backup toàn bộ cấu hình hệ thống vận hành** như Kubernetes YAML, TLS certificates, secrets, firewall rules, audit policies, app config và cloud backup policy.

Nếu dump chỉ một database, bạn còn có thể **không có user/role definitions** của deployment. Phải có kế hoạch riêng cho identities/access control.

---

## 7. Sao lưu một database để thực hành phục hồi

Đây là phương án ít nguy hiểm nhất cho bài tập: backup `sales_lab` rồi restore sang `sales_lab_restore`.

### 7.1. Sao lưu bằng mongodump ở host

Khi đã cài MongoDB Database Tools trên host, trong terminal ở thư mục **không nằm trong Git repo**:

```powershell
mongodump --uri="mongodb://127.0.0.1:27017/" --db=sales_lab --archive="sales_lab.archive.gz" --gzip
```

Chỉ dùng URI không auth cho local development instance không công khai. Với deployment được bảo vệ, dùng tài khoản backup có quyền phù hợp, authentication database và secret injection an toàn.

### 7.2. Sao lưu khi công cụ nằm trong Docker

Trên Windows PowerShell:

```powershell
docker exec sales-mongo mongodump --host 127.0.0.1 --port 27017 --db sales_lab --archive=/tmp/sales_lab.archive.gz --gzip
docker cp sales-mongo:/tmp/sales_lab.archive.gz .\sales_lab.archive.gz
```

Lệnh thứ nhất tạo archive **bên trong container**; lệnh thứ hai copy file tới current directory trên máy host.

### 7.3. Ý nghĩa flags

| Flag | Ý nghĩa |
|---|---|
| `--db sales_lab` | Chọn một database |
| `--archive=...` | Ghi single archive |
| `--gzip` | Nén archive bằng gzip |
| `--uri` hoặc `--host/--port` | Kết nối tới source |
| `--username`/auth settings | Chỉ dùng khi được cấp quyền; tránh truyền password qua CLI |

Không ghép `--out` với `--archive` trong cùng lệnh.

### 7.4. Giới hạn consistency

**Quan trọng:** `mongodump --db=sales_lab` đang có writes từ API **không bảo đảm một snapshot transactionally consistent của nhiều collections**. Ví dụ:

```text
10:00:00 mongodump bắt đầu orders
10:00:01 checkout cập nhật inventory
10:00:02 checkout insert order
10:00:03 mongodump đọc inventory
```

Restore có thể phản ánh `orders` và `inventory` ở những thời điểm khác nhau.

Với lab không có writes trong lúc backup, rủi ro này nhỏ. Với production, cần chính sách consistent backup được hỗ trợ (full replica set oplog, physical snapshot/Atlas backup, hoặc maintenance quiescence phù hợp).

### 7.5. Không tuyên bố `--db` + `--oplog` là point-in-time backup

MongoDB Database Tools yêu cầu **full dump của replica set member** khi dùng `--oplog`. Các tùy chọn giới hạn dữ liệu như `--db` hoặc `--collection` không hợp lệ cùng `--oplog`.

Lệnh sau là **sai**:

```bash
mongodump --db sales_lab --oplog --archive=sales.archive.gz
```

---

## 8. Đặt tên, manifest và bảo vệ backup file

### 8.1. File naming

Ví dụ:

```text
sales_lab-2026-11-14T060000Z-logic-v1.archive.gz
```

Tên file nên cho biết deployment, timestamp UTC, scope, format và version kế hoạch. Không để customer PII trong filename.

### 8.2. Metadata manifest

Một backup catalog/manifest quản lý bên ngoài (không phải bài tập tạo file khác) nên ghi:

```yaml
backupId: sales-lab-20261114-060000
sourceEnvironment: lab
sourceNamespace: sales_lab
backupType: logical-database
startedAtUtc: "2026-11-14T06:00:00Z"
completedAtUtc: "2026-11-14T06:00:08Z"
consistentPointInTime: false
tool: mongodump
compression: gzip
archiveName: sales_lab.archive.gz
sha256: "<verified hash>"
retentionClass: lab-short-lived
restoreLastTestedAtUtc: null
owner: database-operations
```

Đừng tự điền `consistentPointInTime:true` chỉ vì lệnh kết thúc exit code 0.

### 8.3. SHA-256 trên Windows

```powershell
Get-FileHash -LiteralPath .\sales_lab.archive.gz -Algorithm SHA256
```

Trên Linux:

```bash
sha256sum sales_lab.archive.gz
```

Lưu hash và kiểm tra lại sau transfer. Hash chỉ chứng minh **bytes không thay đổi so với bản hash tin cậy**, không tự chứng minh data recoverable.

### 8.4. Gzip integrity và restore

Có file gzip đọc được vẫn chưa đủ: BSON có thể chứa dữ liệu không hợp lệ với target version, thiếu index hoặc thiếu collections cần cho ứng dụng. Bắt buộc restore drill.

### 8.5. Bảo vệ dữ liệu trong backup

Backup có thể chứa:

- Email và thông tin giao dịch.
- Address/PII.
- Internal audit events.
- Password hashes nếu full dump chứa system user data.
- Access tokens/secrets nếu ứng dụng lưu sai trong DB.

Cần encryption at rest/in transit, restricted storage ACL, secret management, audit access, retention và secure deletion.

### 8.6. Không để archive trong source repo

Thư mục project Git không phải vị trí lưu backup: archive có thể rất lớn, chứa PII và bị commit tình cờ. Dùng backup storage riêng với quyền tối thiểu.

---

## 9. Khôi phục database vào tên khác để không đụng nguồn

Mục tiêu: đọc `sales_lab.archive.gz` và tạo collection trong **`sales_lab_restore`**.

### 9.1. Chuẩn bị

Chọn instance MongoDB lab riêng hoặc cùng instance chỉ khi đảm bảo database `sales_lab_restore` chưa tồn tại và không được ứng dụng nào dùng.

Không chạy restore vào `sales_lab` gốc ở bước này.

### 9.2. Xem kế hoạch bằng dry run

Nếu Database Tools trên host:

```powershell
mongorestore --uri="mongodb://127.0.0.1:27017/" --archive="sales_lab.archive.gz" --gzip "--nsFrom=sales_lab.*" "--nsTo=sales_lab_restore.*" --dryRun --verbose
```

`--dryRun` liệt kê thông tin dự kiến restore mà **không import dữ liệu**. Nó không thay thế actual restore/validation.

### 9.3. Restore trên host

```powershell
mongorestore --uri="mongodb://127.0.0.1:27017/" --archive="sales_lab.archive.gz" --gzip "--nsFrom=sales_lab.*" "--nsTo=sales_lab_restore.*"
```

### 9.4. Restore bằng Docker

Đưa file archive vào container nếu cần:

```powershell
docker cp .\sales_lab.archive.gz sales-mongo:/tmp/sales_lab.archive.gz
```

Dry run:

```powershell
docker exec sales-mongo mongorestore --host 127.0.0.1 --port 27017 --archive=/tmp/sales_lab.archive.gz --gzip "--nsFrom=sales_lab.*" "--nsTo=sales_lab_restore.*" --dryRun --verbose
```

Restore:

```powershell
docker exec sales-mongo mongorestore --host 127.0.0.1 --port 27017 --archive=/tmp/sales_lab.archive.gz --gzip "--nsFrom=sales_lab.*" "--nsTo=sales_lab_restore.*"
```

### 9.5. Tại sao phải dùng nsFrom/nsTo?

MongoDB backup logical archive chứa namespace gốc `sales_lab.orders`. Remapping:

```text
sales_lab.orders       → sales_lab_restore.orders
sales_lab.customers    → sales_lab_restore.customers
sales_lab.inventory    → sales_lab_restore.inventory
```

tránh ghi đè database nguồn và giúp so sánh before/after. Khi `mongorestore --oplogReplay` thì không được dùng cách đổi namespace này.

### 9.6. Không dùng --drop trong lab restore đầu tiên

`--drop` làm `mongorestore` drop collections trong backup trên target trước khi restore. Nếu target vô tình là source, dữ liệu có thể bị mất hoặc service gián đoạn.

Đối với target mới trống, không cần `--drop`. Nếu restore thử lại vào cùng target, có thể gặp duplicate keys; hãy tạo một **target namespace mới** hoặc làm sạch đúng target disposable theo thủ tục có chủ đích và được xác minh.

### 9.7. Kết quả mong đợi

Sau restore:

```javascript
const restored = db.getSiblingDB("sales_lab_restore");

printjson(restored.getCollectionNames());
printjson({
  customers: restored.customers.countDocuments({}),
  products: restored.products.countDocuments({}),
  orders: restored.orders.countDocuments({})
});
```

Không mặc định counts bằng 24/30/120 nếu dataset nguồn của bạn khác; so với manifest hoặc counts được chụp ở đúng thời điểm backup.

---

## 10. Kiểm tra restored data: đừng chỉ xem exit code

### 10.1. So counts

```javascript
const source = db.getSiblingDB("sales_lab");
const target = db.getSiblingDB("sales_lab_restore");

const names = [
  "categories", "customers", "products",
  "inventory", "orders", "payments", "outbox"
];

for (const name of names) {
  printjson({
    collection: name,
    sourceNow: source.getCollection(name).countDocuments({}),
    restored: target.getCollection(name).countDocuments({})
  });
}
```

**Cẩn thận:** Nếu source tiếp tục nhận writes sau backup, counts hiện tại khác restored counts là bình thường. Phải so với snapshot manifest hoặc expected backup cut, không so trực tiếp hai database ở hai thời điểm rồi kết luận restore lỗi.

### 10.2. So key samples

```javascript
const restored = db.getSiblingDB("sales_lab_restore");

printjson(restored.orders.findOne({ _id: "ORD-0001" }));
printjson(restored.customers.findOne({ _id: "CUS-001" }));
printjson(restored.products.findOne({ _id: "SKU-001" }));
```

### 10.3. Kiểm tra indexes

```javascript
printjson(restored.orders.getIndexes());
printjson(restored.customers.getIndexes());
printjson(restored.products.getIndexes());
```

Kiểm tra:

- `_id` index.
- Business unique indexes.
- Compound index key order.
- Collation/partial/sparse settings khi có.
- Index không bị ẩn ngoài ý muốn.

### 10.4. Kiểm tra types

```javascript
restored.orders.aggregate([
  {
    $group: {
      _id: {
        createdAt: { $type: "$createdAt" },
        total: { $type: "$totalVnd" }
      },
      count: { $sum: 1 }
    }
  }
]);
```

Nếu chuẩn dữ liệu là BSON Date và Int64, hãy xác minh không có String dates hoặc money strings bất ngờ.

### 10.5. Kiểm tra business invariants

Ví dụ tổng tiền order:

```javascript
restored.orders.aggregate([
  {
    $project: {
      _id: 1,
      totalVnd: 1,
      calculated: { $sum: "$items.lineTotalVnd" }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$totalVnd", "$calculated"] }
    }
  }
]);
```

Expected: không có mismatch đối với dataset được seed đúng.

### 10.6. Kiểm tra orphan references

```javascript
restored.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $match: { customer: { $size: 0 } } },
  { $project: { _id: 1, customerId: 1 } }
]);
```

Đây là application-level consistency check, không phải MongoDB foreign key constraint.

### 10.7. App smoke test

Dùng ứng dụng bản phù hợp schema để kết nối **restore target**, chạy read-only API tests:

- Lấy order theo ID.
- Liệt kê orders theo customer.
- Hiển thị product price.
- Chạy aggregation/report.
- Kiểm tra auth/tenant isolation.
- Kiểm tra app logs và compatibility.

Chỉ cho traffic thật chuyển sang target sau khi có quyết định recovery, credentials/roles/config và monitoring phù hợp.

---

## 11. Full replica set backup với --oplog

Database-only backup giúp học restore một namespace, nhưng một production replica set nhận writes đồng thời có thể cần point-in-time consistent logical dump.

### 11.1. `--oplog` có tác dụng gì?

Với **full dump một replica set member**, `mongodump --oplog` ghi lại oplog entries xuất hiện trong thời gian dump, cho phép `mongorestore --oplogReplay` đưa backup về một trạng thái nhất quán của lần dump theo khả năng hỗ trợ.

### 11.2. Lệnh ví dụ trên self-managed replica set

Trên **môi trường riêng được phép backup toàn bộ instance**, không chọn một database:

```bash
mongodump --uri="mongodb://127.0.0.1:27017/?replicaSet=rs0" --archive=rs0-full.archive.gz --gzip --oplog
```

Nếu dùng Docker cho một replica set local:

```powershell
docker exec sales-mongo mongodump --host 127.0.0.1 --port 27017 --archive=/tmp/rs0-full.archive.gz --gzip --oplog
docker cp sales-mongo:/tmp/rs0-full.archive.gz .\rs0-full.archive.gz
```

### 11.3. Không kết hợp với các flags giới hạn dữ liệu

Với `--oplog`, MongoDB Database Tools yêu cầu full dump của replica set member. Không dùng:

- `--db`.
- `--collection`.
- `--query`.
- `--dumpDbUsersAndRoles`.

Không sử dụng `--oplog` trên `mongos` để kỳ vọng có consistent full sharded cluster backup: cơ chế khác và có giới hạn đặc thù.

### 11.4. Vẫn có các điều kiện có thể làm dump thất bại

Theo Database Tools documentation, một số operations như rename collection, `$out`, thay users/roles/privileges hoặc cluster-wide settings trong quá trình backup có thể khiến `mongodump --oplog` fail.

Cần hạn chế schema/security migrations trong backup window, đọc exit code và logs, không coi file tồn tại nghĩa là backup thành công.

### 11.5. Oplog window

Oplog của replica set có retention hữu hạn tùy cấu hình/khối lượng writes. Nếu backup kéo dài và cần oplog entries đã bị cuộn mất, cần xử lý failure. Theo dõi tốc độ ghi, oplog window và backup duration.

### 11.6. Backup trên secondary?

Có thể giảm tải primary theo topology/command options phù hợp, nhưng cần:

- Kiểm tra replication lag.
- Đảm bảo secondary phù hợp source selection.
- Đọc chính sách readPreference/backup tool.
- Kiểm soát tác động I/O trên node.
- Xác định timestamp/RPO của backup.

Đừng mặc định secondary luôn có dữ liệu mới nhất.

---

## 12. Full restore có oplog replay: chỉ vào deployment trống cô lập

### 12.1. Quy trình logic

```text
Full replica set dump (--oplog)
          │
          ▼
Encrypted archive + checksum
          │
          ▼
Fresh isolated restore deployment
          │
          ▼
mongorestore --oplogReplay
          │
          ▼
Verify data / users / indexes / app
          │
          ▼
Recovery acceptance
```

### 12.2. Lệnh ví dụ

Trong môi trường restore được chuẩn bị riêng, với URI dành riêng cho target:

```bash
mongorestore --uri="mongodb://RESTORE_TARGET_HOST:27017/" --archive=rs0-full.archive.gz --gzip --oplogReplay
```

**Đây là mẫu lệnh, không được copy nguyên hostname placeholder.** Xác nhận target là disposable/empty và compatible, không phải production source.

### 12.3. Không dùng nsFrom/nsTo hoặc namespace filters

`--oplogReplay` với full dump không hỗ trợ kết hợp các tùy chọn như:

- `--db`.
- `--collection`.
- `--nsInclude` hoặc `--nsExclude`.
- `--nsFrom` hoặc `--nsTo`.

Nếu chỉ cần khôi phục database `sales_lab` thành `sales_lab_restore`, sử dụng **database-only dump không oplog** trong bài lab, với điều kiện consistency được hiểu rõ.

### 12.4. Vì sao không minh họa --drop ở đây?

Full dump có thể chứa `admin` và dữ liệu user/roles. `mongorestore --drop` có thể drop/recreate collections, thay users đang dùng để authenticate và làm mất quyền truy cập giữa chừng. Trên shared/production deployment, việc này nguy hiểm.

Chỉ dùng `--drop` theo một approved restoration plan có backup hiện trạng, recovery credential path, change window và target identity được xác minh. Fresh empty target là lựa chọn học tập an toàn hơn.

### 12.5. Oplog replay không phải “time machine” vô hạn

`mongodump --oplog` lưu các thay đổi **trong khoảng thời gian dump**, không tự cung cấp continuous transaction history nhiều ngày. Không thể tùy ý yêu cầu restore đến 16:37 tuần trước nếu bạn không có backup chain/PITR infrastructure tương ứng.

### 12.6. Time series/FCV compatibility

Những MongoDB releases mới có thể thay đổi internal format của time series collections khi đổi FCV. Oplog replay xuyên format conversion có hạn chế; luôn xem Database Tools/server documentation đúng versions, đặc biệt khi nâng cấp MongoDB 8.x/9.x.

---

## 13. Sharded cluster và backup có tính nhất quán

### 13.1. Tại sao khác replica set đơn?

Một sharded cluster gồm:

```text
mongos routers
    │
    ├── shard A replica set
    ├── shard B replica set
    ├── shard C replica set
    └── config server replica set
```

Dữ liệu và cluster metadata có thể thay đổi trên nhiều shards, có migrations/chunk moves và distributed transactions.

### 13.2. Không dùng một mongodump --oplog qua mongos để bảo đảm consistent snapshot

MongoDB Database Tools không hỗ trợ `--oplog` cho full sharded-cluster backup theo cách dùng với một replica set member. Một lệnh chạy được không đồng nghĩa có consistent point toàn cluster.

### 13.3. Khuyến nghị

- Atlas: dùng backup được quản lý và PITR nếu deployment hỗ trợ.
- Self-managed sharded cluster: dùng **MongoDB-supported sharded backup procedure**/enterprise solution phù hợp version.
- Cần capture config server metadata và coordinate shards.
- Kiểm soát chunk migrations, distributed transactions và cluster-wide settings.
- Restore rehearsal phải là **sharded topology test** khi production dùng sharding.

### 13.4. Backup từng shard thủ công có thể không nhất quán

Chụp shard A lúc 10:00, shard B lúc 10:05 và config metadata lúc 10:08 có thể gây trạng thái routing/data inconsistency. Không chắp vá các full replica set dumps thành “cluster consistent backup” nếu không có coordinated procedure.

### 13.5. Shard key và restore validation

Sau restore, kiểm tra:

- Shard/catalog metadata.
- Distribution/chunks.
- Indexes theo sharded requirements.
- Routing/read/write correctness.
- Distributed transaction behavior.
- Cluster balancer state.
- Application workloads.

---

## 14. Point-in-time recovery với cloud backup

### 14.1. PITR là gì?

PITR cho phép chọn một recovery timestamp trong window có backup history phù hợp:

```text
Snapshot S0 ── oplog/change history ──→ T1 ──→ T2 ──→ T3
                                        ▲
                                        │
                              chọn restore point
```

Ví dụ một user chạy sai `updateMany` lúc 10:12; nếu recovery window cho phép, chọn mốc ngay trước thao tác đó theo độ phân giải và tính năng của hệ thống.

### 14.2. Atlas Continuous Cloud Backup

MongoDB Atlas có giải pháp continuous cloud backup trên các loại deployment được hỗ trợ, sử dụng snapshot và oplog để khôi phục đến một điểm trong thời gian. Khả dụng và giới hạn phụ thuộc tier/cluster type, policy retention, restore window, server version và chi phí.

### 14.3. Không đoán thời gian restore

Trước khi thực hiện:

1. Xác minh incident timeline.
2. Xác định giờ UTC và timezone.
3. Xác định recovery window cho phép.
4. Xem backup snapshot và latest recoverable point.
5. Chọn target isolated trước.
6. Kiểm tra data consistency/application correctness.
7. Quyết định cutover.

### 14.4. RPO phút không đồng nghĩa không mất data

Ngay cả continuous backup có giới hạn về việc writes mới nhất đã được persist vào history hay chưa, backup window và restore granularity. Phải ghi lại “latest recoverable timestamp” thực tế.

### 14.5. PITR không tự chữa mọi sự cố

Nếu lỗi nghiệp vụ tồn tại hàng tuần, phục hồi nguyên cluster về ngày cũ có thể làm mất các giao dịch hợp lệ. Có thể cần **selective data repair** bằng cách đọc snapshot và đối chiếu affected records, không chỉ rollback toàn cluster.

---

## 15. RBAC: authentication khác authorization

- **Authentication**: xác minh “ai đang kết nối?”.
- **Authorization**: user được làm gì trên database/collection/cluster?

Một ứng dụng kết nối thành công không có nghĩa user chỉ có quyền cần thiết.

### 15.1. Các vai trò được cân nhắc

| Actor | Nhu cầu | Quyền gợi ý |
|---|---|---|
| Sales API | CRUD trên collections được quản lý | Role custom hoặc `readWrite` scoped database khi phù hợp |
| Read-only dashboard | Truy vấn thống kê | `read` hoặc role custom với `find` |
| Outbox worker | Đọc/update outbox | Custom collection-level actions |
| DBA operator | DDL/index/diagnostics | Role admin theo nhiệm vụ, time-bound |
| Backup service | Đọc dữ liệu/metadata cho backup | `backup` role hoặc cấu hình tối thiểu phù hợp |
| Restore operator | Tái tạo dữ liệu trên target | `restore` role và quyền bổ sung khi cần |
| Root/break-glass | Disaster/administration đặc biệt | Kiểm soát nghiêm ngặt, không làm app account |

Quyền cụ thể cần được kiểm tra với MongoDB version và command sử dụng; một số hoạt động như restore users/roles hoặc oplog replay có yêu cầu cao hơn restore dữ liệu thông thường.

### 15.2. Nguyên tắc least privilege

Không cấp:

```javascript
roles: ["root"]
```

cho user của API chỉ cần đọc/ghi orders. Ngoài ra còn cần giới hạn network, TLS, secrets, audit logs và account rotation.

### 15.3. Built-in roles có phạm vi cụ thể

- `read` trên `sales_lab`: đọc dữ liệu trong database theo permissions của role.
- `readWrite` trên `sales_lab`: đọc/ghi và một số thao tác liên quan trong database; vẫn rộng với một API chỉ cần một collection.
- `dbAdmin`: quản lý database/metadata; không tương đương đọc/ghi mọi dữ liệu.
- `userAdmin`: quản lý users/roles trong scope.
- `backup`/`restore`: built-in roles được gán tại `admin` database cho backup/restore operations theo MongoDB documentation.
- `clusterMonitor`: phục vụ monitoring, không phải data writer.

Vai trò “có vẻ an toàn” vẫn có privilege escalation risks nếu cho phép quản trị roles/users. Review toàn bộ effective privileges.

---

## 16. Tạo môi trường RBAC riêng, không sửa instance lab đang có

Một MongoDB local không bật auth không phù hợp để **chứng minh kiểm soát truy cập**. Để luyện RBAC, ta tạo **container khác**, trên host port 27019, dùng standalone `mongod --auth`. Điều này không hỗ trợ multi-document transaction nhưng đủ để học user/role permissions.

### 16.1. Chạy isolated auth lab

Windows PowerShell:

```powershell
docker run -d --name sales-rbac-lab -p 127.0.0.1:27019:27017 -v sales-rbac-data:/data/db mongo:8.0 --auth
```

**Chỉ dùng trên máy development riêng**. Không dùng container này làm source backup/restore production.

### 16.2. Tạo user quản trị đầu tiên

Nếu deployment chưa có user, MongoDB có localhost exception giúp tạo **user hoặc role đầu tiên** từ localhost theo điều kiện được hỗ trợ. Từ trong container:

```powershell
docker exec -it sales-rbac-lab mongosh
```

Trong mongosh:

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "lab_admin",
  pwd: passwordPrompt(),
  roles: [
    { role: "root", db: "admin" }
  ]
});
```

`passwordPrompt()` cho phép nhập password tương tác thay vì ghi plaintext vào script/history.

**Root chỉ dành cho user quản trị của lab này**, không dùng làm application identity. Với production replica set, bật authorization còn cần cơ chế internal member authentication như keyFile/x.509 và TLS/network setup phù hợp; **không chuyển nguyên lệnh standalone `--auth` sang replica set nhiều node** mà bỏ qua thiết kế nội bộ.

### 16.3. Đăng nhập administrator

```powershell
docker exec -it sales-rbac-lab mongosh --username lab_admin --authenticationDatabase admin --password
```

Mongosh sẽ hỏi password theo kiểu tương tác tùy client version. Không đưa mật khẩu vào shell command argument.

### 16.4. Có thể học RBAC bằng deployment đã bảo mật sẵn

Nếu bạn có một secure development deployment, không cần dựng container mới. Nhưng phải có quyền create users/roles và tuyệt đối không thực hành cấp/revoke root trên production account.

---

## 17. Tạo user ứng dụng và user đọc báo cáo

Đăng nhập `lab_admin` vào `sales-rbac-lab` trước, sau đó:

```javascript
const sales = db.getSiblingDB("sales_lab");

sales.createUser({
  user: "sales_app",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "sales_lab" }
  ]
});

sales.createUser({
  user: "sales_reporter",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "sales_lab" }
  ]
});
```

### 17.1. Tại sao vẫn gọi readWrite là demo?

`readWrite` trên cả database có thể quá rộng với một service chỉ cần collections nhất định. Lab dùng để hiểu RBAC cơ bản; production nên xét custom roles, cơ chế riêng mỗi service và scoped actions.

### 17.2. Authentication database

Hai users trên được tạo trong `sales_lab`, nên authentication source là `sales_lab`:

```text
mongodb://HOST:27019/sales_lab?authSource=sales_lab
```

Không đặt password vào URI được commit. Nếu chạy mongosh:

```powershell
docker exec -it sales-rbac-lab mongosh --username sales_reporter --authenticationDatabase sales_lab --password
```

### 17.3. User không tự có quyền trên admin

User được gán `read` trên `sales_lab` không tự có `root`, `userAdminAnyDatabase` hay quyền đọc dữ liệu của mọi database khác.

### 17.4. Role scopes không thay network isolation

Ngay cả user đọc-only cũng phải kết nối qua TLS/allowlist phù hợp trên shared deployment. RBAC không ngăn được network access hoặc data exfiltration nếu credentials bị lộ và user có read quyền.

---

## 18. Tạo custom role chỉ đọc orders

Trong môi trường đã login bằng `lab_admin`:

```javascript
const sales = db.getSiblingDB("sales_lab");

sales.createRole({
  role: "ordersReader",
  privileges: [
    {
      resource: { db: "sales_lab", collection: "orders" },
      actions: ["find"]
    }
  ],
  roles: []
});

sales.createUser({
  user: "orders_reporter",
  pwd: passwordPrompt(),
  roles: [
    { role: "ordersReader", db: "sales_lab" }
  ]
});
```

### 18.1. Custom role có ích khi nào?

Nếu một reporting job chỉ được đọc orders, không được đọc customers/payment PII, collection-scoped permissions giúp giảm blast radius.

### 18.2. `find` không tự cấp các quyền khác

Một custom role chỉ có `find` trên orders không được tạo index, insert, delete, quản lý users hoặc xem collections khác. Query đặc thù có thể cần thêm actions phù hợp, phải cấp dựa trên nghiệp vụ thực và thử privilege errors.

### 18.3. Đặt role đúng database

Custom role trong ví dụ định nghĩa ở `sales_lab`. Khi grant, chỉ rõ `{role:"ordersReader",db:"sales_lab"}`. Đừng nhầm role DB với authentication DB của một account khác.

### 18.4. Không chỉ tin vào tên role

Role tên `ordersReader` vẫn có thể nguy hiểm nếu ai đó sửa định nghĩa role để thêm `dropDatabase`/`anyAction`. Xác minh effective privileges và review role changes như code.

---

## 19. Xác minh session đang xác thực bằng ai

### 19.1. connectionStatus

Đăng nhập dưới actor cần kiểm tra rồi chạy:

```javascript
db.getSiblingDB("admin").runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

Kết quả có `authInfo` với:

- `authenticatedUsers`.
- `authenticatedUserRoles`.
- `authenticatedUserPrivileges` khi `showPrivileges:true`.

### 19.2. Không phải lúc nào nhìn thấy role cũng đủ

Effective privileges có thể đến từ roles được kế thừa. Kiểm tra action/resource thực tế, không chỉ nhìn tên `read`/`ordersReader`.

### 19.3. Xem user definition

Với quyền quản trị phù hợp, trên database tạo user:

```javascript
const sales = db.getSiblingDB("sales_lab");

printjson(sales.getUser("sales_reporter", {
  showPrivileges: true,
  showCredentials: false
}));
```

Không bật `showCredentials:true` trong troubleshooting thông thường; việc đó có thể để lộ password hash metadata không cần thiết.

### 19.4. Xem danh sách users

```javascript
db.getSiblingDB("sales_lab").getUsers();
```

Đừng coi `getUsers()` trong `sales_lab` là liệt kê mọi MongoDB user ở các authentication databases khác.

### 19.5. Atlas có quản lý người dùng khác self-managed

MongoDB Atlas quản lý database users/roles và project access qua Atlas UI/API; một số commands quản lý `usersInfo` không được hỗ trợ giống self-managed deployments. Dùng công cụ quản trị do Atlas cung cấp và kiểm tra policy.

---

## 20. Positive tests và negative tests về quyền

Một bài kiểm thử quyền phải chứng minh cả:

- Thao tác **được phép** có thể thực hiện.
- Thao tác **bị cấm** thực sự bị từ chối.

### 20.1. Positive test cho reporter

Đăng nhập `sales_reporter`:

```javascript
const sales = db.getSiblingDB("sales_lab");

sales.orders.findOne({});
sales.orders.countDocuments({});
```

Trong RBAC lab rỗng, `findOne` có thể trả null nhưng không bị Unauthorized, cho thấy quyền read hoạt động.

### 20.2. Negative test cho reporter

Chỉ trong disposable lab, thử:

```javascript
db.getSiblingDB("sales_lab").orders.insertOne({
  _id: "DENIED-TEST-001",
  marker: "write-should-be-denied"
});
```

Kỳ vọng lỗi `Unauthorized` hoặc tương đương vì reporter chỉ có `read`. Nếu lệnh unexpectedly thành công, **dừng test**, xác minh account/roles và dọn đúng record lab theo quyền administrator. Không thực hiện negative writes trên production.

### 20.3. Negative test custom role

Đăng nhập `orders_reporter`:

- `sales_lab.orders.findOne()`: cho phép.
- `sales_lab.customers.findOne()`: phải bị từ chối nếu không có role khác cấp quyền.
- `sales_lab.orders.deleteOne()`: phải bị từ chối.

### 20.4. Kiểm tra lỗi thật

Phân biệt:

- Authentication failed (sai user/password/authSource).
- Unauthorized (đã xác thực nhưng thiếu action).
- Network/TLS error.
- Namespace không tồn tại.
- Driver/server incompatibility.

Một read trả null vì collection rỗng không phải privilege denial.

---

## 21. Backup service identity và restore operator

### 21.1. Backup user

Trên self-managed RBAC lab, dưới user admin:

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "backup_agent",
  pwd: passwordPrompt(),
  roles: [
    { role: "backup", db: "admin" }
  ]
});
```

Role `backup` được thiết kế cho backup operations. Tùy dữ liệu đặc thù, encryption và options `mongodump`, có thể cần xem thêm required privileges trong documentation chính xác.

### 21.2. Restore user

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "restore_operator",
  pwd: passwordPrompt(),
  roles: [
    { role: "restore", db: "admin" }
  ]
});
```

Restore users/roles hoặc replay oplog có thể yêu cầu các privileges bổ sung. Không tự cấp `root` không giới hạn; ưu tiên tài khoản/tokens tạm, được approve, tắt sau incident.

### 21.3. Backup role không có nghĩa có thể restore

Tách identities backup/restore là một cách giảm rủi ro: service chạy tự động mỗi ngày cần đọc dữ liệu để backup, không cần quyền xóa/sửa database.

### 21.4. Recovery credentials

Phải có quy trình break-glass lưu bảo mật, kiểm toán sử dụng, rotate sau incident và test truy cập. Không khóa backup mà không có khóa giải mã phục hồi.

### 21.5. Privilege validation

Dưới user backup:

```javascript
db.getSiblingDB("admin").runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

Xác minh backup actions có, nhưng không xuất hiện quyền write/drop không cần thiết. Với restore operator, kiểm tra target namespace và quyền theo workflow cụ thể.

---

## 22. Vì sao không nên bật authorization bừa bãi trên replica set lab cũ?

### 22.1. Replica set cần internal authentication

Một replica set nhiều nodes cần các members xác thực lẫn nhau khi bật security authorization theo cấu hình hỗ trợ, thường dùng keyFile hoặc x.509 cùng TLS/network controls. Chỉ thêm `--auth` vào mongod đã dùng `--replSet` mà thiếu internal authentication/secret provisioning có thể làm deployment không hoạt động.

### 22.2. Tránh mất quyền admin khi chuyển trạng thái

Nếu bật auth trước khi tạo admin user đúng cách, bạn có thể bị khóa quyền, trừ những điều kiện localhost exception giới hạn. Production nên thực hiện security enablement bằng runbook có backup/rollback và change window.

### 22.3. Local RBAC lab là standalone có chủ đích

Container `sales-rbac-lab` dùng `--auth` standalone để học user/role. Nó không thay thế lab replica set để học transaction/backup oplog.

### 22.4. Không truyền keyfile/credentials trong repo

Keyfiles, passwords, TLS private keys phải nằm trong secret storage với permissions phù hợp. Không lưu trong Markdown tutorial hoặc Git dù “chỉ để thử”.

---

## 23. Kiểm tra backup có phù hợp các quyền đang dùng không

Trong disaster recovery, dữ liệu restore thành công nhưng ứng dụng không kết nối được vì:

- User/role definitions không được backup hoặc restore.
- Authentication DB khác.
- Secrets đã rotate.
- Target TLS CA/hostname khác.
- Project/IAM policy khác.
- Target network allowlist chưa mở.
- App user có quyền quá rộng hoặc quá hẹp.
- Database name/namespace đã đổi nhưng URI vẫn trỏ DB cũ.

### 23.1. Tách hai phần khôi phục

```text
Data Recovery
  ├── Data documents
  ├── Indexes and collection options
  └── Schema validation / TTL / views

Access Recovery
  ├── Database users and roles
  ├── Secrets and KMS keys
  ├── TLS / network policy
  ├── Service identities
  └── Application connection configuration
```

Không tự copy user credentials từ source production vào shared staging mà không xem policy. Restore target cần identities phục vụ xác minh và app smoke tests với quyền tối thiểu.

### 23.2. Kiểm tra effective privileges sau restore

Khi có đủ permission:

```javascript
db.getSiblingDB("admin").runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

Sau đó chạy read/write checks dưới từng service user, trên namespace test được phép.

---

## 24. Bảo mật backup storage và chống xóa/sửa trái phép

### 24.1. Encrypt

Bản backup có thể chứa toàn bộ dữ liệu nghiệp vụ. Cần:

- Encryption in transit (TLS).
- Encryption at rest với managed keys.
- Access audit.
- Secret/KMS key management.
- Key recovery procedure.

### 24.2. Immutable copies

Một backup nằm cùng server/volume với database có thể bị mất khi disk/hardware/ransomware incident. Lưu thêm bản offsite/khác failure domain, cân nhắc Object Lock/WORM/immutable retention khi công cụ hỗ trợ.

### 24.3. Phân quyền xóa backup

Tài khoản tạo backup không nhất thiết có quyền xóa mọi bản sao lịch sử. Tách role retention/purge và đặt approval khi cần.

### 24.4. Retention policy

Ví dụ một chính sách cần được tổ chức phê duyệt:

| Tầng | Tần suất | Thời gian giữ |
|---|---|---|
| Operational | Daily | 14 ngày |
| Recovery | Weekly | 8 tuần |
| Audit/Compliance | Monthly/Yearly | Theo quy định và hợp đồng |
| PITR | Continuous window | Theo RPO và chi phí |

Đây là **minh họa**, không phải tiêu chuẩn pháp lý. Phải dựa trên nhu cầu pháp lý, privacy/retention nghĩa vụ và ngân sách.

### 24.5. Data deletion request và backup retention

Nếu có yêu cầu xóa dữ liệu cá nhân, cần chính sách xử lý backup copies, expiration, legal holds và restore contamination. Không cam kết “xóa mọi nơi ngay lập tức” nếu backup bất biến còn giữ trong retention window.

---

## 25. Backup monitoring: không chỉ kiểm tra lịch cron chạy

Một backup job “exit code 0” có thể vẫn chưa đạt RPO hoặc không thể khôi phục do thiếu key/metadata.

### 25.1. Metrics

- Last successful backup timestamp.
- Backup duration.
- Output size.
- Snapshot/backup age.
- Upload completion.
- Checksum verification status.
- Oplog window.
- Replication lag.
- Restore drill status.
- Available disk/bucket capacity.
- Encryption/key access.
- Errors/retries.
- Backup service identity/credential expiration.

### 25.2. Alert thiết yếu

- Backup không có lần thành công mới trong giới hạn.
- Backup quá tuổi so với RPO.
- Archive size giảm/tăng bất thường.
- Oplog window ngắn hơn backup duration.
- Disk/storage capacity sắp đầy.
- Restore drill chưa được thực hiện trong chu kỳ.
- Backup account unauthorized.
- Encrypt/decrypt key unavailable.

### 25.3. Dữ liệu nhạy cảm trong backup logs

Không log toàn bộ MongoDB URI có password, không log customer documents, không copy archive vào public artifact store.

### 25.4. Backup không thành công khi có file

Tool có thể tạo partial file rồi exit nonzero. Chỉ đánh dấu “SUCCESS” khi command hoàn tất, artifact checksum hợp lệ và các bước validation theo policy đạt.

---

## 26. Restore drill: tiêu chí thành công

Một diễn tập phục hồi thực tế cần có **acceptance criteria** trước khi bắt đầu.

### 26.1. Tối thiểu

1. Xác định backupId và source timestamp.
2. Tải/decrypt archive bằng operator được phép.
3. Verify checksum.
4. Restore trên isolated environment.
5. Kiểm tra collection counts và ID samples.
6. Kiểm tra indexes/options.
7. Kiểm tra BSON types, unique constraints.
8. Kiểm tra business invariants.
9. App smoke tests với auth/roles.
10. Đo elapsed recovery time.
11. Ghi discovered gaps.
12. Xác nhận target không còn exposed sau drill theo retention.

### 26.2. Bằng chứng restore

Một record có thể ghi:

```yaml
drillId: restore-drill-20261114
backupId: sales-lab-20261114-060000
sourceVersion: "MongoDB version captured in manifest"
targetVersion: "MongoDB version captured during drill"
restoreTarget: isolated-lab-restore
requestedPointUtc: "2026-11-14T06:00:00Z"
actualRecoveredPointUtc: "from backup metadata"
checksumVerified: true
restoreExitCode: 0
collectionChecks: pass
indexChecks: pass
bsonTypeChecks: pass
businessInvariantChecks: pass
rbacChecks: pass
appSmokeTests: pass
observedRtoMinutes: 12
approval: "<responsible reviewer>"
```

Các giá trị minh họa. Không tự điền `pass` trước khi có bằng chứng.

### 26.3. Phải kiểm tra vấn đề metadata

Một restore có đủ documents nhưng thiếu index sẽ có correctness test pass nhưng hiệu năng production suy giảm nghiêm trọng. Kiểm tra cả index definitions và application query plans.

### 26.4. Người không tạo backup nên tham gia restore drill

Để tránh quy trình chỉ tồn tại trong đầu một DBA, thỉnh thoảng để một operator khác làm theo runbook. Nếu không thể hoàn thành, cải thiện tài liệu và quyền truy cập.

---

## 27. Phục hồi sau khi xóa nhầm orders: phương án nào tốt?

### 27.1. Tình huống

Lúc 10:12, một deployment lỗi chạy:

```javascript
db.orders.deleteMany({ status: "PAID" });
```

Lúc 10:20 phát hiện và dừng writers có liên quan.

### 27.2. Không restore vào DB đang hoạt động ngay

Đầu tiên:

- Xác định chính xác phạm vi data bị xóa.
- Bảo toàn incident evidence.
- Ghi affected collections/IDs.
- Dừng hoặc giới hạn những writers gây hại theo incident policy.
- Kiểm tra latest good restore point.
- Ước lượng tác động nếu rollback toàn cluster (những writes hợp lệ từ 10:12 đến nay).
- Chọn **isolated restore** để lấy dữ liệu đối chiếu.

### 27.3. Selective repair có thể tốt hơn full rollback

Nếu hệ thống vẫn nhận các orders mới hợp lệ từ 10:12–10:20, full PITR về 10:11 có thể xóa các orders mới đó. Có thể restore snapshot lên môi trường cô lập rồi **reconcile/merge** từng affected document theo business rules, với approvals và transaction safety.

### 27.4. Cần business invariants

Một order phục hồi có thể liên quan:

- Payment capture.
- Inventory deduction.
- Outbox events.
- Shipping fulfillment.

Không chỉ insert order document vào production mà bỏ qua downstream side effects. Cần reconciliation giữa các systems.

### 27.5. Audit trail và idempotency

Phải có log những IDs đã restore, mapping old/new IDs, actor, thời điểm, approval và rerun safety. Nếu repair script chạy hai lần, không được tạo duplicate orders/payments.

---

## 28. Phục hồi sau ransomware hoặc credential compromise

Một trường hợp nghiêm trọng hơn accidental delete:

1. Ngăn credentials/compromised identities tiếp tục truy cập.
2. Isolate source và bảo toàn forensic evidence.
3. Rotate credentials/TLS/KMS access theo security policy.
4. Xác định điểm phục hồi trước sự kiện compromise.
5. Chọn immutable/offsite backup không bị attacker thay đổi.
6. Khôi phục vào **clean infrastructure**, không tái sử dụng host đã bị compromise chưa làm sạch.
7. Kiểm tra database users/roles, application binaries và infrastructure config.
8. Kiểm tra data consistency, index/schema, logs/audit.
9. Cutover có phê duyệt.
10. Theo dõi bất thường và cập nhật incident report.

Không chỉ restore data rồi giữ nguyên admin password đã bị lộ.

---

## 29. Quy trình thay đổi backup policy

### 29.1. Trước khi sửa

- Xác định owners, RPO/RTO và compliance constraints.
- Kiểm tra storage cost/retention.
- Xem backup jobs có đủ permissions.
- Đánh giá impact lên primary/secondary.
- Review oplog window.
- Đảm bảo có restore drill gần đây.

### 29.2. Thay đổi có kiểm soát

- Version policy-as-code nếu phù hợp.
- Áp thay đổi trên staging/test trước.
- Theo dõi backup success và resource overhead.
- Xác minh latest backup point.
- Giữ bản backup an toàn trước thay đổi.

### 29.3. Sau khi sửa

- Run restore drill.
- Đo observed RTO.
- Xác minh alerting.
- Cập nhật runbook.
- Document rollback nếu policy gây lỗi hoặc chi phí quá cao.

---

## 30. Checklist hằng ngày

Một operator hoặc automation nên xem:

- [ ] MongoDB cluster healthy, members/trạng thái đúng.
- [ ] Backup job gần nhất hoàn tất theo lịch.
- [ ] Latest successful backup age đạt RPO policy.
- [ ] Checksums/backup metadata được ghi và upload hoàn tất.
- [ ] Backup không nhỏ bất thường so với baseline.
- [ ] Không có authorization failure bất thường của backup service.
- [ ] Không có replication lag/oplog window alarm.
- [ ] CPU, memory, cache, disk, connections trong ngưỡng.
- [ ] Slow-operation rate không tăng đột biến.
- [ ] Không có index build/schema migration đang đụng backup window.
- [ ] Outbox/payment queues không backlog bất thường.
- [ ] Backup destination storage chưa gần quota.
- [ ] Không có credentials/secrets hết hạn sắp tới.

### 30.1. Ghi nhận khi không đạt

Mỗi mục fail nên có owner, timestamp, severity, evidence link và next action. Không chỉ đánh dấu “đã kiểm tra” mà không có dữ liệu.

---

## 31. Checklist hằng tuần

- [ ] Rà soát backup retention và offsite copy.
- [ ] Kiểm tra một archive bất kỳ bằng checksum từ manifest.
- [ ] Review backup errors/retries và duration trends.
- [ ] Review oplog window/replication events.
- [ ] Xem access logs của backup storage.
- [ ] Review users/roles mới hoặc changed privileges.
- [ ] Kiểm tra tài khoản app có quyền cao hơn cần thiết không.
- [ ] Kiểm tra index changes và growth.
- [ ] Xem restore drill schedule và open findings.
- [ ] Kiểm tra cloud/provider backup policy còn active.
- [ ] Xem lifecycle/cost của backup copies.
- [ ] Kiểm tra runbook links và contacts.

### 31.1. Chính sách weekly restore

Với hệ thống critical, có thể chạy restore vào test environment định kỳ tự động (lịch phụ thuộc RPO/RTO và chi phí) và validate canary queries. Nhưng không kết luận backup khỏe chỉ vì cron chạy đúng giờ.

---

## 32. Checklist hằng tháng hoặc trước release lớn

- [ ] Diễn tập full restore hoặc PITR theo risk assessment.
- [ ] Đo RTO thực tế và so với mục tiêu.
- [ ] Chọn ngẫu nhiên một backup khác, test restore.
- [ ] Kiểm tra archived encryption key còn truy cập được.
- [ ] Review break-glass user usage/rotation.
- [ ] Review collection/user privilege grants.
- [ ] Kiểm tra users không còn nhân sự sở hữu.
- [ ] Review cluster/server/database tools compatibility.
- [ ] Thử app smoke test với restored data đã sanitize.
- [ ] Rà soát data growth so với capacity plan.
- [ ] Kiểm tra index cardinality/storage và query plans critical.
- [ ] Audit permission của các automation/cross-account backups.
- [ ] Update incident contacts, runbook, ownership.

### 32.1. Sau schema migration lớn

Nếu migration đổi BSON types, collection options, time series, index/collation hoặc FCV, cần **backup/restore compatibility rehearsal** trên target version, không chỉ kiểm tra CRUD.

---

## 33. Checklist trước deploy hoặc thay đổi schema

### 33.1. Trước deploy

- [ ] Đã có current backup/snapshot mới và valid.
- [ ] Backup point timestamp được lưu.
- [ ] Có rollback strategy rõ cho application/schema/data.
- [ ] Data migrations được thử trên staging với representative data.
- [ ] Migration idempotent hoặc có safe resume.
- [ ] Có capacity/lock/index build impact assessment.
- [ ] User thực thi migration có minimum permissions cần thiết.
- [ ] Không dùng tài khoản API root.
- [ ] Đã cân nhắc tương thích app version cũ/mới.
- [ ] Có monitoring/abort criteria.

### 33.2. Sau deploy

- [ ] App APIs smoke tests pass.
- [ ] Data invariants vẫn đúng.
- [ ] Index catalog/validation settings đúng.
- [ ] Không có unauthorized errors bất thường.
- [ ] Backup jobs vẫn thành công.
- [ ] RPO window không bị ảnh hưởng.
- [ ] Query p95/p99 và write errors ổn.
- [ ] Data growth, disk và replication lag được theo dõi.
- [ ] Có record hoàn thành change.

---

## 34. Checklist sự cố cần phục hồi

### 34.1. Triage

- [ ] Ghi incident ID, owner, severity.
- [ ] Xác định thời gian xảy ra theo UTC.
- [ ] Khoanh vùng affected namespaces/records.
- [ ] Giữ evidence/logs và ngăn lỗi tiếp diễn.
- [ ] Xác định backup set và latest recoverable point.
- [ ] Chọn recovery approach: PITR/full restore/selective repair.
- [ ] Xác minh backup checksum/keys/permissions.

### 34.2. Restore

- [ ] Target là isolated/clean và được phê duyệt.
- [ ] Không trỏ lệnh nhầm source.
- [ ] Khôi phục đúng backup/version/namespace.
- [ ] Không dùng `--drop` tùy tiện.
- [ ] Có logs, exit code và timestamps.
- [ ] Chạy data/index/type checks.
- [ ] Chạy application smoke tests.
- [ ] Xác minh RBAC/secrets/network.
- [ ] Đo RTO và thống kê data loss theo RPO.

### 34.3. Cutover

- [ ] Có approval và thông báo affected teams.
- [ ] Application connections/traffic switch theo runbook.
- [ ] Writers/consumers/outbox được mở lại an toàn.
- [ ] Không tạo duplicate side effects.
- [ ] Monitoring và alerting hoạt động.
- [ ] Xác nhận business owners chấp thuận kết quả.
- [ ] Postmortem ghi lessons và follow-up actions.

---

## 35. Phương án bảo vệ credentials và secrets

### 35.1. Không dùng CLI password argument khi có thể

Sai:

```bash
mongodump --username=backup_agent --password=plaintext-password --uri="mongodb://host/db"
```

Argument có thể lộ qua shell history, process listings hoặc logs.

### 35.2. Dùng interactive prompt hoặc secret injection

Tùy Database Tools version, omitting password value có thể prompt theo shell/connection options. Với automation, dùng secret manager/injection không lộ secret trong command line và log. Kiểm tra đúng cơ chế của tool/version trước khi triển khai.

### 35.3. Rotation

- App credentials.
- Backup service credentials.
- Restore/break-glass identity.
- KMS/decryption keys.
- TLS certs.

Cần kế hoạch rotation đảm bảo backup job không ngừng hoạt động và restore được những archives cũ khi keys thay đổi.

### 35.4. URI encoding

Nếu dùng password trong connection string từ secret injection, reserved URL characters phải được percent-encoded đúng cách; không tự nối các phần string rồi làm sai parser.

### 35.5. Ranh giới CI

CI nên dùng disposable MongoDB/database và synthetic fixtures, không tự có quyền đọc production backups. Nếu thực sự cần restore production data cho test, phải có data sanitization và approval riêng.

---

## 36. Least privilege cho ứng dụng: nên chọn role nào?

### 36.1. Không có một role “app” dùng chung mọi nơi

Các services có nhiệm vụ khác nhau:

```text
product-catalog-api:
  read products/categories

checkout-api:
  read products, update inventory, insert orders/outbox

reporting-service:
  read orders/payments, no update

outbox-publisher:
  find/update outbox, no access customers
```

### 36.2. Role custom theo collection

Ví dụ role checkout (chỉ minh họa, cần đánh giá actions theo API thật):

```javascript
const sales = db.getSiblingDB("sales_lab");

sales.createRole({
  role: "checkoutService",
  privileges: [
    {
      resource: { db: "sales_lab", collection: "products" },
      actions: ["find"]
    },
    {
      resource: { db: "sales_lab", collection: "inventory" },
      actions: ["find", "update"]
    },
    {
      resource: { db: "sales_lab", collection: "orders" },
      actions: ["find", "insert"]
    },
    {
      resource: { db: "sales_lab", collection: "outbox" },
      actions: ["insert"]
    }
  ],
  roles: []
});
```

Role này không có `dropDatabase`, quản lý users hay backup all databases. Các operations như upsert, index creation hoặc aggregation `$out/$merge` có thể cần privileges khác; kiểm thử commands thực và thêm đúng action khi có business need.

### 36.3. Không đoán app chỉ cần insert

Một checkout endpoint có thể cần lookup orders theo idempotency key. Nếu thiếu `find`, app gặp Unauthorized dù insert permission đúng. Viết test integration dưới đúng service identity thay vì dùng admin rồi suy ra quyền đủ.

### 36.4. RBAC không thay business authorization

MongoDB role có thể cho checkout service đọc tất cả orders trong database, nhưng customer A vẫn không được phép xem order customer B. Tenant/user-level access cần application authorization, query scoping, audit và test.

---

## 37. Xác minh quyền bằng test matrix

| Tài khoản | Find orders | Insert orders | Delete orders | Find customers | Create user |
|---|---|---|---|---|---|
| sales_reporter (read DB) | Cho phép | Từ chối | Từ chối | Cho phép | Từ chối |
| orders_reporter (custom) | Cho phép | Từ chối | Từ chối | Từ chối | Từ chối |
| sales_app (readWrite DB) | Cho phép | Cho phép | Theo role, thường có | Cho phép | Không có userAdmin |
| backup_agent | Theo backup role | Không được giả định | Không cần | Theo backup role | Không cần |
| restore_operator | Theo restore role | Phụ thuộc restore actions | Phụ thuộc restore actions | Không phải app identity | Không cấp mặc định |
| lab_admin (root) | Cho phép | Cho phép | Cho phép | Cho phép | Cho phép |

Bảng minh họa quyền cơ bản, **không thay việc kiểm tra effective actions** bằng `connectionStatus showPrivileges` trên đúng server/version.

### 37.1. Test cả denied và permitted

Dưới identity riêng:

- Positive operation pass.
- Negative operation thật sự `Unauthorized`.
- Error messages/logs không chứa secrets.
- Không có role inheritance bất ngờ.

### 37.2. Không chạy destructive negative tests trên production

Nếu một “denied test” bất ngờ được phép, lệnh `deleteMany({})` có thể xóa dữ liệu thật. Chỉ thử writes được kiểm soát trên disposable lab.

---

## 38. Lưu vết người vận hành và kiểm toán thao tác

Một operational change record nên gồm:

```text
Change ID: CHG-2026-001
Actor: database-operations service account
Action: backup policy update / user grant / restore
Target: named environment and database
Approved by: change owner
Timestamp UTC: ...
Reason: ...
Before/after: ...
Validation evidence: ...
Rollback: ...
```

### 38.1. Database audit logs

Tùy deployment/edition, MongoDB có audit facility cho những events bảo mật. Cấu hình và dữ liệu log cần phù hợp retention, storage và privacy policy.

### 38.2. Application audit khác operational audit

- Application audit: ai sửa order/status, lúc nào, giá trị nào.
- Operational audit: ai tạo user, đổi role, restore backup, đổi backup policy.

Một trường `updatedBy` trên orders không thay operational audit logs.

### 38.3. Backup access là sự kiện nhạy cảm

Download một full backup có thể tương đương truy cập toàn bộ customer/payment data. Cần log và alert downloads/copies bất thường.

---

## 39. Khi restore thành công nhưng ứng dụng chưa hoạt động

Ví dụ:

```text
mongorestore exit code 0
collections present
application still failing
```

Các nguyên nhân:

- MongoDB URI sai database/hostname.
- Authentication DB và user definitions khác.
- App role thiếu actions.
- Missing/incorrect indexes.
- Schema version không tương thích.
- App expects fields đã migration.
- External payment system references không đồng bộ.
- Outbox consumer phát lại events không idempotent.
- Search/cache/report pipelines chưa rebuild.
- TLS/network allowlist chưa mở.
- Read preference topology mismatched.

### 39.1. Recovery test phải bao gồm ứng dụng

Không dừng ở counts. Cần smoke tests, permission tests, job/worker readiness và observed RTO.

### 39.2. Đừng mở toàn bộ writers ngay

Sau restore, bật services theo thứ tự kiểm soát, đảm bảo idempotency và reconciliation trước khi xử lý backlog.

---

## 40. Vì sao restore order không đồng nghĩa restore trạng thái kinh doanh?

Một order có thể có:

```text
MongoDB order document
      │
      ├── Payment capture ở gateway
      ├── Inventory movement
      ├── Warehouse shipment
      ├── Email/SMS confirmation
      └── Outbox → broker → consumers
```

MongoDB backup không backup external payment gateway, warehouse hoặc message broker. Phục hồi lại document không hủy các side effects đã xảy ra.

### 40.1. Thiết kế reconciliation

- Kiểm tra payment gateway status theo payment ID.
- Kiểm tra warehouse fulfillment.
- Đối chiếu inventory snapshot/ledger.
- Dedupe outbox events.
- Ghi compensation/recovery actions có approval.

### 40.2. Không tự resend messages sau restore

Nếu outbox records được phục hồi về trạng thái `processed:false`, một worker có thể phát lại nhiều events đã từng phát. Cần event IDs và consumer dedupe.

### 40.3. Point-in-time consistency có giới hạn hệ thống

Một MongoDB-consistent restore point không đồng nghĩa tất cả external systems cùng ở đúng thời điểm đó. Cần business-level recovery plan.

---

## 41. Kiểm tra khả năng nâng phiên bản qua backup/restore

### 41.1. Trước major upgrade

- Ghi MongoDB Server/FCV và Database Tools versions.
- Xác minh backup compatibility với target.
- Kiểm tra time series, encrypted collections, index types.
- Restore trên target version trong isolated environment.
- Chạy schema/index/permission/invariant tests.
- Benchmark critical queries.
- Xác minh rollback plan thực sự khả thi.

### 41.2. FCV/time series đặc thù

Oplog replay khi chuyển format time series qua một số FCV boundaries có restrictions và có thể bị tools từ chối. Không dùng full dump+oplog như một “rollback tự động” không kiểm tra release notes.

### 41.3. Backup không phải binary downgrade strategy

MongoDB không bảo đảm data files hoặc logical dumps có thể restore tới mọi phiên bản thấp hơn. Kiểm tra compatibility thay vì giả định `mongorestore` tự chuyển schema server.

---

## 42. Bài tập 1: backup database sales_lab

1. Xác định MongoDB instance đang chạy và namespace đúng.
2. Kiểm tra database counts hiện tại.
3. Tạo `sales_lab.archive.gz` bằng `mongodump --db --archive --gzip`.
4. Ghi exit code, duration, size.
5. Tính SHA-256.
6. Lưu manifest nêu rõ **không guaranteed point-in-time consistent nếu có writes**.
7. Đảm bảo file không nằm trong Git repo chứa customer data.

Câu hỏi: nếu API vẫn nhận checkout trong lúc dump, bạn có thể khẳng định orders/inventory cùng trạng thái không?

---

## 43. Bài tập 2: restore cô lập

1. Chuẩn bị database đích `sales_lab_restore` trống.
2. Chạy `mongorestore --dryRun --verbose`.
3. Restore với `--nsFrom` và `--nsTo`.
4. Không dùng `--drop`.
5. Kiểm tra `getCollectionNames()`.
6. Kiểm tra counts và sample IDs.
7. Kiểm tra index definitions.
8. Ghi observed restore time.

Câu hỏi: nếu source tiếp tục có orders mới sau backup, vì sao count của sourceNow và target khác nhau chưa chứng minh restore lỗi?

---

## 44. Bài tập 3: kiểm tra checksum và tính toàn vẹn

1. Tính SHA-256 trước upload.
2. Copy artifact tới nơi lưu trữ an toàn.
3. Tính SHA-256 sau download.
4. So hai hashes.
5. Chạy real restore.
6. Xác minh indexes, BSON types và business invariants.

Giải thích vì sao checksum match chưa chứng minh database có thể phục hồi thành công.

---

## 45. Bài tập 4: phân biệt RPO và RTO

Một business yêu cầu:

```text
RPO 5 phút
RTO 1 giờ
```

Nhưng hiện chỉ chạy mongodump lúc 02:00 mỗi ngày.

Hãy:

1. Giải thích vì sao không đáp ứng RPO.
2. Đề xuất backup/PITR solution.
3. Ước lượng các thành phần RTO.
4. Thiết kế restore drill.
5. Xây alert cho backup age.
6. Đề xuất retention policy.

---

## 46. Bài tập 5: full replica set backup

1. Dùng self-managed replica set lab.
2. Chạy full `mongodump --oplog --archive --gzip`.
3. Giải thích tại sao không đi cùng `--db`.
4. Xác định backup này chứa oplog interval nào.
5. Lập kế hoạch restore vào disposable target.
6. Giải thích giới hạn `--oplogReplay` khi dùng `--nsFrom/--nsTo`.
7. Trả lời vì sao nó không tự tạo PITR window 7 ngày.

---

## 47. Bài tập 6: kiểm thử read-only role

Trong RBAC lab:

1. Tạo `sales_reporter` với `read` trên `sales_lab`.
2. Đăng nhập bằng user đó.
3. `findOne` orders: không bị unauthorized.
4. `insertOne` marker riêng: phải bị Unauthorized.
5. Chạy `connectionStatus({showPrivileges:true})`.
6. Ghi role actions theo resource.
7. Không dùng root làm account reporter.

---

## 48. Bài tập 7: custom collection role

1. Tạo `ordersReader` với `find` trên sales_lab.orders.
2. Tạo user `orders_reporter`.
3. Test read orders cho phép.
4. Test read customers bị từ chối.
5. Test delete orders bị từ chối.
6. Giải thích khác `read` database-wide ra sao.
7. Xác định những reporting queries nào cần thêm actions.

---

## 49. Bài tập 8: backup và restore identities

1. Tạo backup_agent/restore_operator identities riêng.
2. Xác minh privileges.
3. Xác định lệnh mongodump cần quyền nào.
4. Xác định restore users/roles cần quyền gì ngoài normal data restore.
5. Mô tả rủi ro của full dump chứa admin.
6. Viết kế hoạch break-glass/credential rotation.
7. Đưa ra phương án không dùng root thường xuyên.

---

## 50. Bài tập 9: incident xóa nhầm PAID orders

Một deployment sai chạy `deleteMany({status:"PAID"})` trong production. Có PITR window bao phủ thời điểm trước lỗi, nhưng sau đó xuất hiện 300 orders hợp lệ.

1. Đề xuất điểm restore và target.
2. Giải thích vì sao không rollback production ngay.
3. Thiết kế selective repair.
4. Đối chiếu payments, inventory, outbox.
5. Chống duplicate khi chạy repair nhiều lần.
6. Ghi evidence và approval.

---

## 51. Bài tập 10: simulated ransomware

1. Xác định bản immutable offsite.
2. Xác định keys cần decrypt.
3. Chọn clean infrastructure.
4. Rotate credentials.
5. Restore và kiểm tra roles.
6. Validate data/invariants.
7. App smoke tests và controlled cutover.
8. Ghi incident timeline/observed RTO.

---

## 52. Bài tập 11: backup khi nâng FCV

1. Ghi current server/FCV/tools versions.
2. Liệt kê time series collections.
3. Xem giới hạn oplog replay khi format conversion.
4. Thử restore vào target version tương thích.
5. Test index/schema/roles.
6. Xác định rollback feasibility.
7. Viết checklist nâng cấp và backup window.

---

## 53. Bài tập 12: viết SOP cho team

Soạn Standard Operating Procedure tối thiểu:

- Daily backup checks.
- Weekly storage/access reviews.
- Monthly restore drill.
- Incident escalation/contact.
- Approval required for restore/cutover.
- Evidence template.
- Retention và key management.
- Recovery acceptance criteria.

Mỗi bước phải có owner, cách đo, điều kiện pass/fail và hướng xử lý khi fail.

---

## 54. Bảng lỗi thường gặp và cách phân biệt

| Lỗi | Nguyên nhân khả dĩ | Điều tra |
|---|---|---|
| mongodump authentication failed | Sai user/password/authSource | Xem connection options và user |
| mongodump unauthorized | Backup role thiếu actions | connectionStatus/getUser |
| File backup quá nhỏ | Dump sai database hoặc interrupted | Exit code/logs/namespaces |
| Backup có file nhưng corrupt | Partial archive/truncated transfer | SHA-256 + real restore |
| `--oplog` bị từ chối | Đang dùng `--db`/không phải full replica member | Kiểm tra flags/topology |
| `--oplogReplay` lỗi với nsFrom | Oplog replay không hỗ trợ rename | Dùng full restore riêng |
| Restore duplicate key | Target đã có documents | Tạo target mới, không drop vội |
| Restore ghi nhầm source | URI/namespace sai | Dừng, dùng incident runbook |
| --drop làm mất users | Admin database included | Khôi phục access theo runbook |
| Restore đủ counts nhưng query chậm | Missing indexes/collation | getIndexes/explain |
| App không đăng nhập được | Users/roles/authSource không đúng | Kiểm tra RBAC/secrets |
| App Unauthorized sau restore | Effective privileges thiếu | connectionStatus/test user |
| Data thiếu writes mới | Backup point cũ/RPO chưa đạt | Kiểm tra timestamp/PITR |
| SourceNow count khác target | Source có writes sau backup | So backup manifest |
| PITR không có mốc mong muốn | Window/retention/granularity | Kiểm tra backup policy |
| Backup job timeout | Network/disk/load | Logs, duration, resources |
| Oplog window quá ngắn | Writes lớn hoặc backup dài | Theo dõi oplog/capacity |
| No backup in sharded cluster | Dùng sai phương án mongos | Sharded-supported procedure |
| Role tên read-only nhưng delete được | Role inheritance hoặc extra grants | Effective privileges |
| Docker lab unauthed test RBAC pass giả | Authorization chưa bật | Separate secure RBAC instance |
| Restore sau external payment lệch | Mongo only backup | Business reconciliation |
| Backup storage bị xóa | Cùng failure domain/quyền xóa quá rộng | Immutable offsite copies |
| Restore không đạt RTO | Archive quá lớn/index rebuild chậm | Drill/throughput capacity plan |

---

## 55. Checklist tổng hợp trước khi vận hành thật

### 55.1. Backup và RPO/RTO

- [ ] RPO/RTO đã được business phê duyệt.
- [ ] Backup strategy phù hợp topology và data size.
- [ ] Có latest successful backup point.
- [ ] Backup/continuous history đủ đáp ứng RPO.
- [ ] Có retention, offsite và immutable strategy.
- [ ] Backup encryption và KMS keys có khả năng phục hồi.
- [ ] Backup jobs có monitoring/alerting.
- [ ] Mongodump/restore tools versions được quản lý.
- [ ] Không dựa vào replica set như backup.

### 55.2. Restore và kiểm chứng

- [ ] Có restore target cô lập.
- [ ] Restore runbook có xác minh URI/namespace.
- [ ] Có checksum verification.
- [ ] Có actual restore drill, không chỉ dryRun.
- [ ] Data counts/IDs/BSON types được kiểm tra.
- [ ] Indexes/options/validators được kiểm tra.
- [ ] Business invariants được kiểm tra.
- [ ] App smoke tests pass dưới accounts thích hợp.
- [ ] Observed RTO được đo.
- [ ] Recovery acceptance được ghi nhận.

### 55.3. Quyền và bảo mật

- [ ] Authentication được bật phù hợp deployment.
- [ ] Replica set internal auth/TLS đúng cấu hình.
- [ ] App không dùng root.
- [ ] Reporter chỉ read trong scope.
- [ ] Backup/restore identities tách biệt.
- [ ] RBAC custom roles được kiểm tra actions/resources.
- [ ] Có positive và negative privilege tests.
- [ ] Secrets/keys không nằm trong Git/logs.
- [ ] Break-glass credentials được bảo vệ/rotate.
- [ ] Backup storage access được audit.

### 55.4. Vận hành và sự cố

- [ ] Daily/weekly/monthly checklists có owner.
- [ ] Trước schema/index migration có backup/rollback.
- [ ] Cảnh báo replication/oplog/cache/disk được theo dõi.
- [ ] Có incident contacts và escalation.
- [ ] Recovery decision cân nhắc external systems.
- [ ] Outbox/event replay có idempotency.
- [ ] Backup policy được kiểm tra sau upgrade.
- [ ] Restore drill findings được đóng.
- [ ] Có postmortem cho sự cố thực tế.

---

## 56. Tài liệu tham khảo chính thức

Các link dưới đây giúp đối chiếu theo MongoDB Server/Database Tools và deployment edition hiện tại:

- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Manual — Back Up and Restore](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Manual — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Manual — Built-In Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/)
- [MongoDB Manual — Create a User](https://www.mongodb.com/docs/manual/tutorial/create-users/)
- [MongoDB Manual — Create a Role](https://www.mongodb.com/docs/manual/tutorial/define-roles/)
- [MongoDB Manual — connectionStatus command](https://www.mongodb.com/docs/manual/reference/command/connectionStatus/)
- [MongoDB Manual — db.getUser()](https://www.mongodb.com/docs/manual/reference/method/db.getUser/)
- [MongoDB Manual — db.getUsers()](https://www.mongodb.com/docs/manual/reference/method/db.getUsers/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Query Explain](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Atlas — Backup Overview](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Atlas — Point-in-Time Restore](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/)
- [MongoDB Atlas — Backup Guidance](https://www.mongodb.com/docs/atlas/architecture/current/backups/)

**Lưu ý:** Mongodump oplog, oplogReplay, sharded backup, users/roles restores, FCV compatibility và Atlas PITR có các giới hạn theo version/topology/edition. Không dùng lệnh full backup/restore production trước khi kiểm tra đúng tài liệu tương ứng và có maintenance/change approval.

---

## 57. Tổng kết

1. **Backup không đồng nghĩa recovery**: file và checksum có tồn tại vẫn cần real restore drill, kiểm tra indexes, documents, schema, quyền và app smoke tests.
2. **RPO/RTO là mục tiêu nghiệp vụ** quyết định backup cadence, retention, PITR strategy và restore capacity. Chỉ backup một lần mỗi đêm không đáp ứng RPO vài phút.
3. **`mongodump --db --archive --gzip`** phù hợp lab restore một database, nhưng không tạo một consistent point cho database có concurrent writes trên nhiều collections.
4. **`mongodump --oplog`** yêu cầu full dump của replica set member, không đi với `--db/--collection`. **`mongorestore --oplogReplay`** dành cho full dump tương ứng và không đi với namespace filters/remapping.
5. **Sharded clusters** cần cơ chế backup/restore cluster-consistent riêng; không dùng một lệnh oplog qua mongos để khẳng định dữ liệu nhất quán toàn cluster.
6. **Least privilege** yêu cầu tách app, reporter, backup, restore và administrator identities. Kiểm tra bằng `connectionStatus` cùng positive/negative operations trên lab có authorization bật.
7. **Restore phải được diễn tập trên target riêng**, tránh `--drop` và nhầm URI, đồng thời xác minh business invariants, external systems và idempotency khi mở lại writers.
8. **Checklist daily/weekly/monthly và incident** biến khả năng sao lưu/khôi phục từ một tập lệnh ad hoc thành quy trình có owner, bằng chứng và ngưỡng pass/fail.

**Nguyên tắc cuối cùng:** Một hệ MongoDB được vận hành tốt không chỉ có bản sao dữ liệu; nó có **điểm phục hồi rõ, quyền truy cập đúng, backup bảo vệ khỏi cùng failure domain, quy trình restore đã được tập luyện và bằng chứng đủ để tin rằng ứng dụng có thể trở lại hoạt động an toàn**.
