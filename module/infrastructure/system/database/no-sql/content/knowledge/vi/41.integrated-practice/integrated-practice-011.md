# Diễn tập backup/restore hoặc xây dựng lại dữ liệu dẫn xuất trong NoSQL

## 1. Bài thực hành tổng hợp: không chỉ có file backup là đã phục hồi được

Một hệ thống Java lưu đơn hàng trong NoSQL, đồng thời xây bảng `orders_by_customer` và chỉ mục tìm kiếm để phục vụ giao diện. Một ngày, có hai sự cố:

- **Sự cố A — mất dữ liệu gốc:** một thao tác sai xóa collection nguồn. Nhóm có bản backup đêm qua nhưng chưa từng kiểm tra có restore được bằng tài khoản, khóa mã hóa và phiên bản phần mềm hiện tại hay không.
- **Sự cố B — dữ liệu dẫn xuất sai:** nguồn vẫn đúng, nhưng một consumer CDC bị lỗi, làm chỉ mục tìm kiếm thiếu đơn, chứa trạng thái cũ và thậm chí hiển thị đơn đã xóa. Khôi phục nguyên database gốc không giải quyết sự cố này; cần **xây dựng lại projection** từ nguồn có thẩm quyền.

Hai bài diễn tập liên quan nhưng không giống nhau:

```text
NHÁNH A: RECOVER SOURCE OF TRUTH

       Backup + recovery metadata
                  |
                  v
          Isolated restore target
                  |
                  v
        Validate data and invariants
                  |
                  v
          Prove RTO, RPO, security


NHÁNH B: REBUILD DERIVED DATA

        Authoritative NoSQL source
             |             |
         Snapshot       Change history
             |             |
             +------v------+
                    |
             Rebuild worker
                    |
                    v
            New projection/index
                    |
                    v
          Verify + guarded cutover
```

Trong chương **Thực hành tổng hợp** của module **Database No SQL**, bạn có thể thực hiện **một trong hai nhánh** hoặc làm cả hai rồi so sánh. Các bước nền chung là xác định ranh giới dữ liệu, dùng nguồn/tài khoản đã được phép, gây lỗi an toàn, thu bằng chứng và xác minh **trạng thái thực sự được phục vụ**, không chỉ sự thành công của một lệnh.

> **Backup/restore khôi phục một nguồn dữ liệu tại recovery point đã xác định; rebuild dữ liệu dẫn xuất tái tạo một biểu diễn có thể mất hoặc sai từ nguồn có thẩm quyền. Cả hai chỉ hoàn tất khi dữ liệu, chỉ mục, quyền truy cập và các bất biến quan trọng đã được xác minh.**

## 2. Kết quả học tập

Sau bài này, bạn cần làm được:

1. Chọn giữa restore source và rebuild projection dựa trên **nguồn nào thực sự bị mất hoặc sai**.
2. Phân biệt backup logic, backup vật lý/snapshot, point-in-time recovery (PITR), change log và derived data.
3. Xác định **RPO, RTO, consistency boundary, source identity và scope dữ liệu**.
4. Thiết kế mục tiêu restore **cô lập**, không ghi đè nhầm môi trường đang phục vụ.
5. Dùng dữ liệu tổng hợp để dựng fixture có updates, deletes, tenants, revisions, indexes và dependencies.
6. Tạo một backup, phục hồi vào target riêng, xác minh bản ghi, checksum/canonical data, index và business invariant.
7. Thiết kế snapshot + CDC/outbox không có khoảng mất updates giữa baseline và replay.
8. Xây projection với deterministic IDs, source revisions, idempotent replay, tombstones và checkpoint bền.
9. Diễn tập crash sau sink commit nhưng trước checkpoint, xử lý ambiguous outcome và kiểm tra reconciliation.
10. Đo thời gian, độ mới, khả năng phục vụ, tỉ lệ khôi phục và sai lệch dữ liệu.
11. Xây runbook phục hồi, phương án rollback/cutover, bảo mật và báo cáo kết quả có thể kiểm toán.

## 3. Phạm vi an toàn: bắt đầu bằng phòng lab

**Không chạy các bước dưới đây trực tiếp trên production.** Một lệnh restore, xóa collection hoặc đổi alias nhầm target có thể gây mất dữ liệu hoặc ngắt dịch vụ. Bài thực hành sử dụng **hai MongoDB containers thử nghiệm** hoặc môi trường NoSQL cô lập tương đương, cùng dữ liệu tổng hợp.

### Quy tắc an toàn bắt buộc

- Sử dụng tenant, order ID, email và số tiền **giả lập**; không export dữ liệu khách hàng thật ra máy cá nhân.
- Tách **source lab**, **restore lab** và mọi production credentials; ưu tiên identity chỉ có quyền trên test database.
- Phê duyệt scope, người chịu trách nhiệm, thời gian, hậu quả được phép và điều kiện dừng trước khi mô phỏng outage thật.
- Không restore đè database/namespace đang phục vụ; restore vào **target riêng và verify trước khi promote**.
- Không dùng wildcard drop hoặc `--drop` ngoài môi trường lab đã xác minh.
- Không hiển thị password, tokens, KMS material, raw PII hoặc toàn bộ database dump lên console/chat.
- Đặt giới hạn CPU/I/O/QPS, dung lượng output và thời gian diễn tập.
- Ghi mã phiên thực hành `runId` và vị trí artifacts để dọn đúng phạm vi sau khi xong.

### Không đủ quyền hoặc không có Docker?

Bạn vẫn làm được phần thiết kế và Nhánh B bằng **Java 17 in-memory fixture**, không truy cập dịch vụ thật. Phần Docker/MongoDB là một tuyến minh họa, không phải yêu cầu bắt buộc để hiểu lý thuyết.

## 4. Chọn nhánh theo loại tổn thất

| Tình huống | Hướng chính | Vì sao? |
|---|---|---|
| Source collection bị xóa nhầm | Restore backup/PITR | Nguồn có thẩm quyền bị mất |
| Một replica chết, majority source còn khỏe | Replica recovery theo engine | Không nhất thiết restore cả cluster |
| Search index sai/mất | Rebuild index từ source + changes | Projection có thể tạo lại |
| Redis cache bị flush | Warm/rebuild cache có kiểm soát | Cache không phải source of truth |
| CDC consumer bị thiếu events | Replay/reconcile; resnapshot nếu thiếu history | Sửa projection và checkpoint |
| Snapshot source backup hết hạn | Restore từ bản còn hợp lệ hoặc xác định blocker | Không thể tái tạo dữ liệu tùy ý |
| Các writes đã được ACK sau thời điểm backup | PITR/log replay hoặc chấp nhận RPO theo chính sách | Backup đơn lẻ cũ hơn hiện tại |
| Source sai do logic ứng dụng | Xác định good recovery point + repair | Restore bản mới nhất có thể vẫn chứa sai |
| Cả source và projection đều hỏng | Phục hồi authority trước, sau đó rebuild derived | Không dùng projection sai làm authority |

**Điểm quyết định:** nếu một dữ liệu chỉ tồn tại duy nhất trong projection và không còn event/source để tạo lại, nó **không thật sự là dữ liệu dẫn xuất có thể rebuild**. Cần đặt lại data ownership và backup plan.

## 5. Bốn thời điểm phải định nghĩa

Một bài tập:

```text
T0  Last verified backup completed
T1  Source receives acknowledged write W11
T2  Source becomes unavailable or data is corrupted
T3  Isolated restore can serve validated reads
T4  Production routing/cutover is completed
```

Các mốc có nghĩa khác nhau:

**Recovery point:** trạng thái dữ liệu có thể khôi phục tại T0 hoặc một vị trí log sau T0.

**RPO (Recovery Point Objective):** mức mất dữ liệu cho phép so với sự cố, có thể diễn đạt bằng thời gian hoặc lượng acknowledged business effects. Phải xác định rõ **mốc nào là write đã cam kết**.

**RTO (Recovery Time Objective):** thời gian phục hồi dịch vụ trong phạm vi mục tiêu đã đặt; không nhất thiết chỉ là thời gian công cụ restore giải nén xong.

**Freshness của dữ liệu dẫn xuất:** thời gian từ source commit đến lúc client query index/cache thấy trạng thái đúng.

### Ví dụ đo

```text
T0 = 09:00  backup captures source data
T1 = 09:15  source confirms 500 later writes
T2 = 09:20  source lost
T3 = 09:55  restore and validation finished
T4 = 10:05  traffic safely routed to recovered service
```

Nếu chỉ có backup T0, dữ liệu đến 09:00 là recovery point; **500 writes sau T0 không tự có trong bản restore**. Recovery point gap là 20 phút, nhưng RPO thực tế của business cần xác định theo acknowledged writes đã mất. Nếu dịch vụ chỉ trở lại an toàn ở T4, một cách đo end-to-end recovery time là 45 phút, không phải 35 phút thời gian restore đến T3.

Các số chỉ là ví dụ phục vụ học tập, không phải benchmark.

## 6. Các loại backup trong NoSQL

| Cơ chế | Nội dung thường có | Cần kiểm tra |
|---|---|---|
| Logical export/dump | Documents/records và một số metadata/index tùy công cụ | Snapshot consistency, types, restore tool/version |
| Filesystem/volume snapshot | Data files tại thời điểm snapshot | Quiesce/crash consistency, WAL/journal, cluster topology |
| Managed provider backup | Snapshot/PITR theo dịch vụ | Retention, IAM/KMS, target account/region, quotas |
| Base snapshot + log replay | State tại snapshot và thay đổi sau mốc | Continuous log coverage, ordering, recovery point |
| Replication | Bản sao đang nhận updates | Không thay thế backup trước delete/corruption |
| CDC event stream | Record changes dùng cho replay | Retention, omissions, completeness, schema |

### Replication không phải backup

Nếu người vận hành xóa nhầm record, thao tác delete có thể nhanh chóng được replicate. Một cluster ba replicas đều khỏe vẫn có thể **không còn phiên bản dữ liệu cần khôi phục**.

### Backup không đồng nghĩa restore khả dụng

Một archive có thể tồn tại nhưng:

- Hỏng hoặc thiếu chunks.
- Không có quyền giải mã.
- Restore tool không tương thích version.
- Snapshot cần log segment đã bị xóa.
- Region dự phòng thiếu capacity.
- Không đủ index/schema/config hay IAM policies.
- Data restore nhưng app không thể authenticate/query đúng.

Một diễn tập restore phải kiểm chứng **end-to-end recoverability**.

## 7. Dữ liệu dẫn xuất là gì?

Một kiến trúc:

```text
                  Authoritative orders
                (one write authority)
                         |
                         v
                  Durable outbox / CDC
                         |
            +------------+-----------+
            |            |           |
            v            v           v
      Search index   Customer view  Analytics table
      (derived)      (derived)      (derived)
```

Source có thể lưu:

```json
{
  "_id": "T01#O001",
  "tenantId": "T01",
  "orderId": "O001",
  "customerId": "C001",
  "status": "PAID",
  "amountMinor": 125000,
  "sourceRevision": 4,
  "deleted": false
}
```

Projection `orders_by_customer` có thể lưu:

```json
{
  "_id": "T01#C001#O001",
  "tenantId": "T01",
  "customerId": "C001",
  "orderId": "O001",
  "status": "PAID",
  "sourceRevision": 4
}
```

Nếu projection sai, ta **không sửa bằng cách coi projection là nguồn**. Thay vào đó rebuild từ source và lưu version/identity để nhận biết stale events.

## 8. Bài tập chung: đặt ra hợp đồng đúng trước khi chạy

Mẫu mục tiêu (giá trị chỉ minh họa):

```yaml
drill:
  run_id: "NOSQL-DR-589"
  environment: "isolated-local-lab"
  source_authority: "orders source"
  allowed_data: "synthetic-only"
  expected:
    no_cross_tenant_records: true
    exact_required_order_ids: true
    no_duplicate_logical_orders: true
    deletes_not_resurrected: true
    projection_matches_authoritative_revision: true
  recovery:
    target: "separate isolated instance"
    backup_boundary: "recorded explicitly"
    log_coverage: "checked if PITR required"
  stop_conditions:
    unexpected_target: true
    authorization_failure: true
    integrity_mismatch: true
    resource_budget_exceeded: true
```

Đây là schema mô tả tự thiết kế, **không phải file cấu hình của MongoDB hay chaos tool**.

## 9. Dataset fixture và bảng bất biến

Một bộ dữ liệu nhỏ nên có cả:

- Hai tenants `T01` và `T02` để kiểm **không đọc chéo**.
- Hai customers trong `T01` để kiểm partition/routing.
- Orders đang `NEW`, `PAID`, `CANCELED` để kiểm filter/sort.
- Một entity bị **soft-delete/tombstone**.
- Source revisions tăng dần.
- Một update xảy ra **sau backup** để đo recovery point.
- Một event đến lặp hoặc đảo thứ tự để test rebuild.

Ví dụ:

| ID | Tenant | Customer | Status | Revision | Deleted |
|---|---|---|---|---:|---|
| O001 | T01 | C001 | PAID | 4 | false |
| O002 | T01 | C001 | NEW | 2 | false |
| O003 | T01 | C002 | CANCELED | 3 | false |
| O004 | T02 | C003 | PAID | 1 | false |
| O005 | T01 | C001 | CANCELED | 5 | true |

### Những bất biến cần chứng minh

1. Mỗi composite ID `(tenantId,orderId)` xác định một logical order.
2. Các bản ghi visible không có `deleted=true`, nhưng tombstone/version phải ngăn hồi sinh.
3. Source revision không bị giảm khi replay.
4. Tổng số và tập keys ở recovery boundary chính xác theo dữ liệu fixture.
5. Customer projection chỉ chứa orders thuộc đúng tenant/customer.
6. Không nhân đôi trạng thái khi retry một chunk/event.
7. Chỉ công bố recovered service khi index/routing/authz trong trạng thái được phép.

## 10. Sơ đồ workflow hai nhánh

```text
          Define requirements / safety boundary
                         |
                         v
              Build synthetic fixture
                         |
                 +-------+-------+
                 |               |
                 v               v
          Backup / restore    Derived rebuild
                 |               |
        Backup checkpoint    Snapshot boundary
                 |               |
           Archive export    Baseline import
                 |               |
       Isolated target read   Event replay
                 |               |
            Verify data      Verify projection
                 |               |
                 +-------+-------+
                         |
                         v
             Fault recovery rehearsal
                         |
                         v
              Evidence + runbook + ADR
```

Bạn có thể thực hiện Nhánh A trước để có **bằng chứng source recovery**, sau đó Nhánh B để thấy ngay rằng dữ liệu gốc đúng **không có nghĩa read model đã đúng**.

---

# Phần I — Nhánh A: diễn tập backup và restore nguồn NoSQL

## 11. Mục tiêu và tiêu chí PASS của Nhánh A

Đề bài:

> Tạo một backup logic từ source MongoDB **được giữ yên trong lúc dump**, sau đó restore vào MongoDB target cô lập, chứng minh các bản ghi tại recovery point vẫn chính xác và nhận biết rõ các writes sau recovery point **không nằm trong backup**.

### Điều kiện PASS

- Archive được tạo và có checksum/metadata đủ truy nguyên.
- Restore vào target **khác source** thành công; không ghi đè dữ liệu đang phục vụ.
- Tập composite keys, source revisions, deleted flags và monetary amounts ở target đúng theo fixture tại backup boundary.
- Các index cần cho API được kiểm tra, không chỉ documents.
- Một write xảy ra sau backup được nhận diện là **chưa có trong backup**, không bị nhầm thành lỗi import.
- Ghi thời gian diễn tập, recovery point, công cụ/phiên bản, quyền và các bước cần làm để production-ready.
- Không dùng dữ liệu thật, không gây tác động ra ngoài lab.

### Điều kiện FAIL/INCONCLUSIVE

| Tình trạng | Kết luận |
|---|---|
| Restore thiếu một record thuộc backup boundary | FAIL về integrity |
| Record mới được ghi sau backup không có ở target | Expected RPO gap; không tự là restore bug |
| Archive sai checksum so với manifest | FAIL, không tin dữ liệu |
| Lệnh thành công nhưng target sai namespace | FAIL về procedure |
| Không xác định được backup đã chứa những records nào | INCONCLUSIVE |
| Target trả 200 nhưng index/permissions chưa kiểm | Chưa đủ bằng chứng PASS end-to-end |

## 12. Chuẩn bị môi trường

Bạn cần:

- Docker Engine/Desktop và quyền chạy containers, **chỉ trong lab**.
- MongoDB shell `mongosh`, `mongodump` và `mongorestore` có trong image/được cài đúng version phù hợp.
- Ổ đĩa đủ lưu archive và bản restore.
- Java 17 nếu muốn thực hiện Nhánh B bằng chương trình độc lập.
- Terminal PowerShell, Bash hoặc shell tương đương. Ví dụ lệnh dưới đây dùng cú pháp Docker CLI; nơi cần lệnh PowerShell sẽ ghi rõ.

### Tạo hai containers riêng

```powershell
docker volume create nosql589-source-data
docker volume create nosql589-target-data

docker run -d `
  --name nosql589-source `
  -p 127.0.0.1:27027:27017 `
  -v nosql589-source-data:/data/db `
  mongo:7.0

docker run -d `
  --name nosql589-target `
  -p 127.0.0.1:27028:27017 `
  -v nosql589-target-data:/data/db `
  mongo:7.0
```

PowerShell dùng dấu backtick cuối dòng để nối lệnh. Với Bash/Linux, dùng một dòng cho mỗi `docker run` hoặc dấu gạch chéo ngược thay cho backtick.

### Giới hạn bảo mật

Đây là hai container **không bật authentication để học nội bộ**, nên chỉ dùng trên máy/môi trường tin cậy với cổng host **bind vào 127.0.0.1**, không đem nguyên cấu hình vào production hoặc mạng dùng chung. Với production phải bật TLS/authentication, network policies và least privilege. Containers có thể truy cập qua Docker bridge; không coi ví dụ này là isolation security đủ cho dữ liệu nhạy cảm.

### Kiểm tra môi trường

```powershell
docker ps --filter "name=nosql589-"

docker exec nosql589-source mongosh --quiet --eval "db.adminCommand({ping:1})"
docker exec nosql589-target mongosh --quiet --eval "db.adminCommand({ping:1})"

docker exec nosql589-source mongodump --version
docker exec nosql589-target mongorestore --version
```

Nếu image không chứa MongoDB Database Tools đúng phiên bản hoặc lệnh không có, **dừng phần command lab** và cài bản tools tương thích theo môi trường đã được phép; không tự thay bằng script copy file dữ liệu đang mở.

## 13. Sinh fixture với Mongosh

Mở shell source:

```powershell
docker exec -it nosql589-source mongosh --quiet
```

Trong `mongosh`, chạy:

```javascript
const lab = db.getSiblingDB("nosql589_source");

lab.orders.insertMany([
  {
    _id: "T01#O001",
    labRunId: "NOSQL-DR-589",
    tenantId: "T01",
    orderId: "O001",
    customerId: "C001",
    status: "PAID",
    amountMinor: 125000,
    sourceRevision: 4,
    deleted: false,
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: "T01#O002",
    labRunId: "NOSQL-DR-589",
    tenantId: "T01",
    orderId: "O002",
    customerId: "C001",
    status: "NEW",
    amountMinor: 40000,
    sourceRevision: 2,
    deleted: false,
    createdAt: ISODate("2026-11-02T09:00:00Z")
  },
  {
    _id: "T01#O003",
    labRunId: "NOSQL-DR-589",
    tenantId: "T01",
    orderId: "O003",
    customerId: "C002",
    status: "CANCELED",
    amountMinor: 70000,
    sourceRevision: 3,
    deleted: false,
    createdAt: ISODate("2026-11-03T09:00:00Z")
  },
  {
    _id: "T02#O004",
    labRunId: "NOSQL-DR-589",
    tenantId: "T02",
    orderId: "O004",
    customerId: "C003",
    status: "PAID",
    amountMinor: 90000,
    sourceRevision: 1,
    deleted: false,
    createdAt: ISODate("2026-11-04T09:00:00Z")
  },
  {
    _id: "T01#O005",
    labRunId: "NOSQL-DR-589",
    tenantId: "T01",
    orderId: "O005",
    customerId: "C001",
    status: "CANCELED",
    amountMinor: 30000,
    sourceRevision: 5,
    deleted: true,
    createdAt: ISODate("2026-11-05T09:00:00Z")
  }
]);

lab.orders.createIndex(
  {tenantId: 1, customerId: 1, createdAt: -1, _id: 1},
  {name: "tenant_customer_recent"}
);
```

### Xác minh fixture trước backup

```javascript
lab.orders.countDocuments({labRunId: "NOSQL-DR-589"});

lab.orders.find(
  {labRunId: "NOSQL-DR-589"},
  {_id: 1, tenantId: 1, customerId: 1,
   status: 1, amountMinor: 1, sourceRevision: 1, deleted: 1}
).sort({_id: 1}).toArray();

lab.orders.getIndexes();
```

Kỳ vọng **5 documents** và index `tenant_customer_recent`. Dữ liệu ở đây là fixture; không có payment hoặc khách hàng thật.

### Nếu đã chạy fixture trước đó

`insertMany` sẽ báo duplicate keys; **không xóa data của namespace ngoài lab** để chạy lại. Bạn có thể khởi tạo một run/database mới, hoặc chỉ tiếp tục khi đã xác nhận đây chính là fixture của lần chạy hiện tại. Mục đích là tránh mọi lệnh xóa mơ hồ trên source.

## 14. Ghi mốc backup boundary

Trong bài lab local, source **không nhận writes khác trong khoảng dump**. Ghi vào nhật ký:

```text
runId                 NOSQL-DR-589
sourceIdentity        nosql589-source / nosql589_source
fixtureVersion        1
documentCount         5
expectedIDs           T01#O001..O005 (with exact tenant list)
sourceRevisionMap     O001=4,O002=2,O003=3,O004=1,O005=5
deletedTombstones     T01#O005
indexNames            _id_,tenant_customer_recent
backupType            logical dump with application writes quiesced
backupStart/end       record actual timestamps
```

### Vì sao không gọi đây là online consistent snapshot?

`mongodump` đọc collection khi chạy. Nếu source tiếp tục thay đổi và topology/transaction semantics không được phối hợp, một logical dump thông thường có thể chứa records ở các thời điểm khác nhau. Việc **không có concurrent writes trong lab** làm boundary dễ hiểu.

Trong production, phải chọn documented consistent backup/PITR procedure cho **topology thực tế** (replica set, sharded cluster, managed service). Không lấy kết quả một standalone lab để kết luận dump trong lúc production đang ghi luôn có snapshot consistency.

## 15. Tạo backup logical và lưu manifest tối thiểu

Thoát mongosh (`.exit`), trong PowerShell:

```powershell
docker exec nosql589-source mongodump `
  --db nosql589_source `
  --archive=/tmp/nosql589.archive `
  --gzip

docker cp nosql589-source:/tmp/nosql589.archive ./nosql589.archive

Get-Item -LiteralPath ./nosql589.archive
Get-FileHash -LiteralPath ./nosql589.archive -Algorithm SHA256
```

### Dữ liệu từ lệnh

- `mongodump` tạo archive BSON logic theo các namespaces được chọn.
- `--gzip` nén stream/archive, không mã hóa dữ liệu nhạy cảm.
- `Get-FileHash` trả SHA-256 cho **bytes của file archive hiện tại**.

**Không đặt archive chứa production PII ở một ổ đĩa/đường dẫn không được phép.** Trong bài này file chỉ chứa records tổng hợp.

### Manifest ghi bên ngoài

```yaml
runId: "NOSQL-DR-589"
backupType: "logical-mongodump"
sourceCluster: "nosql589-source"
sourceNamespace: "nosql589_source.orders"
sourceWriteFreeze: true
backupStartUtc: "<record actual UTC>"
backupEndUtc: "<record actual UTC>"
toolVersion: "<mongodump --version>"
archiveFile: "nosql589.archive"
archiveSha256: "<actual command output>"
expectedCount: 5
expectedIndex: "tenant_customer_recent"
expectedRevisionMap: "recorded separately in controlled metadata"
```

Không điền hash giả rồi báo đã verify. Với backup production, manifest cần được bảo vệ chống chỉnh sửa trái phép, thường có signed/authenticated metadata, immutable object generation và audit.

## 16. Integrity và authenticity là hai câu hỏi

Nếu copy archive sang máy restore, chạy lại SHA-256 và so với manifest:

```powershell
Get-FileHash -LiteralPath ./nosql589.archive -Algorithm SHA256
```

**Hash khớp:** bytes của archive khớp digest đã lưu trong một manifest đáng tin.

**Hash không khớp:** artifact có thể hỏng/đổi; dừng restore, điều tra provenance và lấy bản đúng.

**Hash khớp nhưng manifest do attacker sửa:** hash đơn thuần không chứng minh archive là nguồn tin cậy. Production cần IAM, encryption, object versioning và trust boundary phù hợp.

### File hash không chứng minh business correctness

Archive có thể toàn vẹn nhưng được tạo sau khi dữ liệu đã bị lỗi logic. Bài thực hành vẫn cần kiểm record keys, source revisions, indexes và nghiệp vụ.

## 17. Mô phỏng mất đường truy cập source mà không xóa dữ liệu

Sau khi backup xong, thử tạo **hai writes sau recovery point** (vẫn chỉ trong source lab):

```powershell
docker exec -it nosql589-source mongosh --quiet
```

Trong mongosh:

```javascript
const labAfterBackup = db.getSiblingDB("nosql589_source");

labAfterBackup.orders.updateOne(
  {_id: "T01#O001", sourceRevision: 4},
  {$set: {status: "SHIPPED", sourceRevision: 5}}
);

labAfterBackup.orders.insertOne({
  _id: "T01#O006",
  labRunId: "NOSQL-DR-589",
  tenantId: "T01",
  orderId: "O006",
  customerId: "C001",
  status: "NEW",
  amountMinor: 65000,
  sourceRevision: 1,
  deleted: false,
  createdAt: ISODate("2026-11-06T09:00:00Z")
});
```

Kiểm tra update có `matchedCount=1` và insert acknowledged. Nếu script chạy lại sai phiên/source version, **không tự coi second attempt là success**. Vì các records là synthetic, một run mới luôn dễ hơn ghi đè sai trạng thái cũ.

Thoát shell, có thể giả lập outage đường source:

```powershell
docker stop nosql589-source
```

Lệnh chỉ dừng container lab, **không xóa volume và không mô phỏng mất vật lý của data files**. Tùy mục tiêu, bạn có thể bỏ qua bước stop; việc restore vào target khác đã đủ chứng minh tính độc lập của archive.

### Dự đoán trước restore

- Archive đã chụp O001 revision **4** và **không có O006**.
- Source trước khi stop có O001 revision **5**, có O006.
- Nếu chỉ restore archive, target đúng phải trở về **recovery point** chứ không phải state source cuối cùng.

Đây là minh họa **RPO gap** khi không có log/PITR, không phải restore tự động làm mất một write vốn có trong backup.

## 18. Restore vào target cô lập

Trong PowerShell:

```powershell
docker cp ./nosql589.archive nosql589-target:/tmp/nosql589.archive

docker exec nosql589-target mongorestore `
  --archive=/tmp/nosql589.archive `
  --gzip `
  --nsFrom="nosql589_source.*" `
  --nsTo="nosql589_restored.*"
```

### Những điểm phải ghi nhận

- `nosql589-target` là container khác với source.
- Namespace nguồn `nosql589_source` được remap sang `nosql589_restored`, tránh trùng tên ngay trong lab.
- Ví dụ **không dùng `--drop`**, giả định target namespace đang trống.
- Lệnh đang khôi phục **logical dump**, không replay các writes sau backup.
- Ghi actual start/end times và exit status của restore command.

### Trước khi dùng trên hệ khác

Tính năng `--nsFrom`/`--nsTo`, namespace pattern và handling indexes phải được kiểm với version MongoDB Database Tools hiện có. Nếu cần restore lại vào cùng target đã tồn tại, dừng để thiết kế **new target generation** thay vì thêm `--drop` để ép thành công.

## 19. Xác minh dữ liệu target

```powershell
docker exec -it nosql589-target mongosh --quiet
```

Trong mongosh:

```javascript
const recovered = db.getSiblingDB("nosql589_restored");

recovered.orders.countDocuments({});

recovered.orders.find(
  {},
  {_id:1, tenantId:1, customerId:1,
   status:1, amountMinor:1, sourceRevision:1, deleted:1}
).sort({_id:1}).toArray();

recovered.orders.findOne({_id: "T01#O001"});
recovered.orders.findOne({_id: "T01#O006"});
recovered.orders.getIndexes();
```

### Kỳ vọng

| Assertion | Kết quả |
|---|---|
| Total records at backup boundary | 5 |
| O001 status | `PAID` |
| O001 revision | 4 |
| O006 exists? | Không |
| O005 tombstone | `deleted=true,sourceRevision=5` |
| T02 O004 present | Có |
| Compound index | `tenant_customer_recent` hiện diện |

Lưu ý: O001 trong source trước khi stop là `SHIPPED` revision 5; target restore đúng là **PAID** revision 4 vì backup xảy ra trước update.

### Chưa phải kiểm chứng production end-to-end

Một lab không có authentication/TLS/cluster/sharding không kiểm hết:

- Tài khoản ứng dụng sau restore.
- Index build hiệu năng trên volume thật.
- Tenant authorization policy.
- Driver routing/read preference.
- Multi-AZ/region recovery.
- Recovery của các CDC/search consumers.
- KMS/decrypt grant thực.

Bảng trên là expected assertions cho **lab isolated**; production drill phải bổ sung.

## 20. Vì sao checksum và count đều cần nhưng chưa đủ?

Hai datasets đều có 5 records có thể khác nhau:

```text
Source keys: O001,O002,O003,O004,O005
Target keys: O001,O002,O003,O004,O999
```

Counts bằng nhau nhưng target có missing O005 và extra O999.

### Các cấp verification

| Cấp | Đo gì | Giới hạn |
|---|---|---|
| Archive integrity | Digest/size/object generation | Chưa chứng minh nội dung nguồn đúng |
| Counts | Số records theo tenant/range | Không phát hiện hoán đổi IDs |
| Key sets | Missing/extra IDs | Chưa phát hiện sai field |
| Canonical record hashes | Values theo mapping/version | Cần normalization đúng |
| Index/schema | Query path restore | Chưa bảo đảm p99 |
| Business invariants | Unique, money, tenant, deletes | Cần domain oracle |
| Query parity | API truy vấn được dữ liệu đúng | Cần same recovery boundary |

### Hash theo canonical data

Nếu so hash của JSON serializer khác nhau, field order, numeric precision, timestamps hoặc binary encoding có thể làm hash khác dù business data tương đương. Định nghĩa canonical representation có version, sort keys, normalize types/timezones và **chỉ so các fields hợp đồng yêu cầu**.

## 21. Phạm vi nhất quán khi backup có concurrent writes

Local lab dùng freeze writes để có boundary đơn giản. Trong một cụm production nhận nhiều writes:

```text
09:00 dump begins
09:02 order O1 changes v11 -> v12
09:05 collection page containing O1 is dumped
09:10 dump ends
```

Một dump duyệt từng records có thể không đại diện snapshot toàn collection tại cùng thời điểm nếu engine/tool/topology không cung cấp barrier/snapshot hợp lệ.

### Cần chọn đúng kỹ thuật

- Snapshot-consistent backup hoặc managed PITR theo provider.
- Với MongoDB replica set, một số backup strategies dùng oplog capture/replay theo documented constraints; không dùng `mongodump --oplog` tùy tiện với standalone/sharded topologies hoặc nhầm nó thành cơ chế PITR arbitrary.
- Với managed DB, ưu tiên backup/recovery API chính thức, kiểm retention và region/identity.
- Với Cassandra/wide-column, snapshot SSTables cùng incremental backup/repair/commitlog theo engine, không copy một file đang ghi rồi gọi là consistent snapshot.
- Với Redis, RDB/AOF và replica-persistence semantics phải được phân biệt.
- Với DynamoDB, PITR/export to object storage tuân provider API/retention và quy trình restore thành **table mới** theo khả năng dịch vụ.

**Chọn kỹ thuật theo topology và failure model, không theo thói quen của một hệ khác.**

## 22. RPO: viết sau backup có thể không phục hồi nếu thiếu log

Trong lab:

```text
Backup boundary: O001 rev4, no O006.
Later ACKs:      O001 rev5, O006 created.
Restore archive: O001 rev4, no O006.
```

Đây là **đúng nội dung của backup**. Nhưng nếu business yêu cầu RPO≈0 cho acknowledged order writes, một lịch backup theo giờ không đáp ứng.

### Cách cải thiện trong production

1. Capture changes/logs liên tục với retention phù hợp.
2. Chọn backup + log recovery strategy có checkpoint/boundary rõ.
3. Verify log không có gap trước khi target nhận traffic.
4. Đối soát acknowledged writes và durable ledger.
5. Định nghĩa ứng xử nếu một phần events cuối chưa chắc commit.

### RPO không chỉ là độ tuổi file

Một backup tạo lúc 09:00 nhưng hoàn thành lúc 09:20 không có nghĩa mọi write tới 09:20 đều nằm trong backup. Cần xác định **consistent recovery point/commit position** chính xác.

## 23. RTO: thời gian giải nén không phải thời gian phục vụ lại

Một recovery timeline:

```text
T0 incident detected
T1 backup identified, access approved
T2 restore started
T3 data files loaded
T4 indexes ready
T5 permissions/routes/services verified
T6 app and derived views ready
T7 production traffic cut over
```

### Các thước đo

- **MTTD:** time to detect failure.
- **Restore duration:** T2→T3.
- **Data readiness:** T2→T4 hoặc T5, theo scope.
- **Business service RTO observation:** T0→T7, nếu đó là contract.
- **Projection rebuild time:** tính riêng nếu derived read model critical.

### Điều kiện dừng

Đừng mở traffic vì `mongorestore` exit code 0 nếu indexes còn build, app secrets chưa cấp, source identity/tenant permissions chưa kiểm hoặc replication/catch-up chưa đủ.

## 24. Restore user/roles, secrets, indexes và schema

Logical dump có thể mang một số collection metadata/index definitions, nhưng **không thể mặc định** nó gồm toàn bộ:

- Database users/roles và external identity provider policies.
- Secrets, TLS certificates và network rules.
- Application schema migrations/configuration.
- Atlas/provider IAM/KMS grants.
- Change stream connectors và stream offsets.
- Search index mappings/aliases.
- Time-series retention/TTL policies ở các hệ khác.

### Production-ready checklist

1. Khôi phục dữ liệu vào đúng namespace/target.
2. Khôi phục hoặc tái áp **indexes** và verify query plans.
3. Khôi phục database roles/authorization theo policy.
4. Kết nối application bằng identity thật, kiểm quyền tenant.
5. Kiểm data types, TTL, timestamps, unique constraints và collation.
6. Kiểm backup catalog retention, encryption, audit và recovery artifacts.
7. Chỉ tiếp tục CDC/outbox khi biết source recovery point.

Một restore đọc được documents từ admin shell nhưng application không có quyền read/write **chưa phải khôi phục dịch vụ**.

## 25. PITR: backup cộng thay đổi theo thứ tự

Mô hình:

```text
Base snapshot at source position C100
      |
      v
Log C101, C102, C103, ... C180
      |
      v
Restore base + replay through C160
      |
      v
Verified recovery point C160
```

### Điều kiện cần

- Base snapshot có **boundary** phù hợp với change log.
- Log không có khoảng trống C101..C160.
- Replay semantics hiểu transactions, ordering, deletes và schema versions.
- Chọn consistent recovery timestamp/position, không lấy wall clock đơn giản thay log position.
- Có cách xác định transaction incomplete tại recovery boundary.
- Có kiểm integrity của snapshot/log segments và authority.

### Không tự replay application events như transaction log tùy ý

Một outbox event có thể chỉ chứa business-level changes hoặc projection payload, không chứa mọi nội dung database state. Nếu muốn PITR đầy đủ, phải biết logs có đủ data và ordering cho source recovery.

## 26. Restore sau lỗi logic khác restore sau mất node

Một corruption:

```text
10:00 good source state.
10:10 buggy job changes all order amounts.
10:11 replicas propagate corruption.
10:12 new backup captures corrupted values.
```

Restore bản **mới nhất** có thể vẫn sai. Cần:

1. Tìm nguồn phát sinh lỗi và dừng writes hỏng.
2. Xác định last-known-good source position.
3. Chọn restore/PITR boundary trước corruption.
4. Cẩn thận với **các writes hợp lệ xảy ra sau thời điểm đó**.
5. Reconcile selectively hoặc replay business-valid changes theo policy.

### Không tự rewind production toàn bộ

Một bản phục hồi trước sự cố có thể làm mất các orders mới hợp lệ. Có thể cần restore **vào target cô lập**, diff và selective repair thay vì đổi authority wholesale.

## 27. Kết thúc Nhánh A: báo cáo có cấu trúc

```text
Run ID: NOSQL-DR-589
Environment: isolated local Docker
Source: nosql589_source.orders
Restore: nosql589_restored.orders
Backup type: logical dump, writes quiesced
Expected at backup: 5 records
Observed after restore: [fill actual result]
Expected O001: rev4 PAID
Expected O006: missing (post-backup write)
Expected indexes: _id_, tenant_customer_recent
Archive SHA-256: [actual digest]
Backup tool version: [actual]
Restore tool version: [actual]
Backup duration: [measured]
Restore duration: [measured]
Business-read readiness: [measured]
RPO evidence: [known post-boundary acknowledged changes]
Result: PASS / FAIL / INCONCLUSIVE
Blockers / next actions: ...
```

Đánh dấu **PASS cho lab đã thực sự chạy** không phải chứng nhận DR production. Cần ghi rõ những gì lab **chưa thử**: multi-AZ, auth/TLS/KMS, large data, app traffic, PITR, index rebuild cost và vùng dự phòng.

---

# Phần II — Nhánh B: xây dựng lại dữ liệu dẫn xuất từ nguồn có thẩm quyền

## 28. Khi nào nên rebuild thay vì restore?

Một projection có thể được tái tạo hoàn toàn nếu:

1. Source of truth còn **đúng và có thể truy cập**.
2. Có schema/transform logic và version phù hợp.
3. Có dữ liệu đầu vào đầy đủ: snapshot hoặc event history bảo đảm coverage.
4. Có cách xử lý deletes, TTL, out-of-order events và duplicates.
5. Có một target generation riêng để rebuild và verify.
6. Có quy trình đổi route/alias an toàn, bảo vệ readers đang sử dụng.

Nếu một projection chứa **trường duy nhất chỉ được ghi trực tiếp vào projection** mà source không có, việc rebuild có thể mất thông tin. Khi đó projection không thật sự “derived” đối với field ấy; cần đổi data ownership hoặc backup/restore chính projection.

## 29. Hợp đồng của projection `orders_by_customer`

Source:

```json
{
  "_id": "T01#O001",
  "tenantId": "T01",
  "orderId": "O001",
  "customerId": "C001",
  "status": "PAID",
  "amountMinor": 125000,
  "sourceRevision": 4,
  "deleted": false
}
```

Projection:

```json
{
  "_id": "T01#C001#O001",
  "tenantId": "T01",
  "customerId": "C001",
  "orderId": "O001",
  "status": "PAID",
  "sourceRevision": 4
}
```

### Identity và transform

```text
projectionId = tenantId + "#" + customerId + "#" + orderId
```

Các thành phần phải được mã hóa/escape theo quy tắc tránh collision. Ví dụ đơn giản giả định các fixture IDs **không chứa dấu `#`**. Trong ứng dụng thật nên dùng structured composite key/encoding được kiểm chứng, không nối chuỗi tự do nếu IDs có ký tự đặc biệt.

### Các invariant

- Một logical order active tạo **một projection row đúng customer**.
- Tenant khác nhau không chia sẻ projection key.
- Source revision v11 không bị snapshot/event v10 ghi đè.
- Source delete phải làm record **không còn visible**.
- Nếu customerId có thể đổi, projection key cũ phải được xóa/tombstone.
- Read model được dùng sau cutover chỉ khi verified theo source boundary.

## 30. Snapshot + CDC: không được có khoảng trống

Một anti-pattern:

```text
09:00 start scanning source
09:10 scan record O001 as rev8
09:20 source changes O001 to rev9
09:40 scan complete
09:41 start CDC from "now"
```

Update rev9 **không nằm trong snapshot đã đọc** và cũng không có trong CDC bắt đầu 09:41. Target giữ rev8 mãi đến khi có update tiếp theo.

### Mô hình đúng

```text
Source change position C100 / consistent snapshot S
    |
    +-- Baseline snapshot at S ----------+
    |                                    |
    +-- Changes from boundary C100 ------+--> Versioned sink
                                               |
                                               v
                                       Verified source state
```

Tùy engine, snapshot và CDC boundary phải được thiết lập bằng **API/protocol có guarantee**. Có thể cần connector start trước snapshot, high-water/low-water marks, snapshot transaction, transaction log position hoặc change-stream resume token với documented ordering.

### Không thay source position bằng `Instant.now()`

Một wall-clock timestamp do app ghi có thể không tương ứng vị trí commit/replication log. Nếu source có transactions hoặc concurrent updates, “bắt đầu CDC theo giờ hiện tại” dễ mất events.

## 31. Phân biệt thứ tự snapshot và thứ tự events

Giả sử snapshot ở boundary C100:

```text
Snapshot S:
  O001 revision 4 = PAID
  O002 revision 2 = NEW
  O003 revision 3 = CANCELED

Change events after C100:
  C101: O001 revision 5 -> SHIPPED
  C102: O002 revision 3 -> deleted
  C103: O006 revision 1 -> NEW
```

Mục tiêu target sau C103:

```text
O001 -> SHIPPED, rev5
O002 -> deleted tombstone, rev3
O003 -> CANCELED, rev3
O006 -> NEW, rev1
```

Nếu một worker chậm ghi snapshot O001 rev4 **sau khi** event C101 đã apply rev5, target có thể quay lại `PAID` nếu writer chỉ dùng unconditional upsert. Cần **revision guard** hoặc barrier stage rõ.

## 32. Quy tắc idempotent apply theo source revision

Trong scope một entity và source incarnation:

```text
if incomingRevision > storedRevision:
    apply new state

if incomingRevision == storedRevision
   AND incoming payload is identical:
    treat as harmless retry

if incomingRevision < storedRevision:
    skip obsolete update

if same revision but conflicting payload:
    stop and investigate data/model corruption
```

### Điều kiện ngầm của thuật toán

- Revision do **source authority** phát, tăng đơn điệu theo entity.
- Delete được biểu diễn bằng tombstone revision mới hơn.
- Identity bao gồm tenant và source incarnation nếu ID có thể tái sử dụng.
- Mỗi event mang **full state after** hoặc payload được so sánh đúng.

### Với delta-only events

Nếu event là `ADD_QUANTITY(+1)`, “giữ revision lớn nhất và skip bản nhỏ hơn” có thể **mất delta**. Cần ordered event processing và exactly-once logical effect qua inbox/ledger hoặc tái tạo absolute state từ nguồn.

## 33. Tombstones và việc không hồi sinh record đã xóa

Lịch sử:

```text
T1 Snapshot worker fetches O002 revision 2, NEW.
T2 CDC consumer applies DELETE O002 revision 3.
T3 Snapshot worker retries UPSERT O002 revision 2.
```

Nếu target hard-delete không giữ version, thao tác T3 có thể **hồi sinh O002**.

### Giải pháp

Giữ:

```json
{
  "projectionKey": "T01#C001#O002",
  "sourceRevision": 3,
  "deleted": true
}
```

Serving query luôn lọc `deleted=false`. Tombstone được giữ ít nhất đến khi **không còn replay cũ** có thể đến theo retention/snapshot/CDC protocol. Với privacy deletion, cần cân nhắc không giữ payload nhạy cảm trong tombstone.

### Khi key thay đổi

Nếu O002 chuyển từ customer C001 sang C009, target cần:

- Xóa/tombstone projection key cũ `T01#C001#O002`.
- Tạo projection key mới `T01#C009#O002`.

Một source event chỉ chứa after-image mà không có old key có thể không đủ để xóa bản cũ. Cần pre-image, source lookup, reverse registry hoặc rebuild từ scratch + guarded cutover theo design.

## 34. Hands-on rebuild offline bằng MongoDB aggregation

Đây là **phiên bản tối giản**, không mô phỏng CDC. Nó chỉ có ý nghĩa nếu không có concurrent writes vào source trong lúc xây dựng read model hoặc ta chấp nhận đây là snapshot không nhất quán cho mục đích thử nghiệm.

Nếu đã dừng source ở Nhánh A:

```powershell
docker start nosql589-source
docker exec -it nosql589-source mongosh --quiet
```

Trong `mongosh`, sử dụng source **sau** khi đã thêm O006 và sửa O001:

```javascript
const sourceDb = db.getSiblingDB("nosql589_source");

sourceDb.orders.aggregate([
  {
    $match: {
      labRunId: "NOSQL-DR-589",
      deleted: false
    }
  },
  {
    $project: {
      _id: {
        $concat: [
          "$tenantId", "#", "$customerId", "#", "$orderId"
        ]
      },
      tenantId: 1,
      customerId: 1,
      orderId: 1,
      status: 1,
      sourceRevision: 1
    }
  },
  {
    $merge: {
      into: "orders_by_customer_v2",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]).toArray();

sourceDb.orders_by_customer_v2.createIndex(
  {tenantId: 1, customerId: 1, orderId: 1},
  {name: "tenant_customer_order"}
);
```

### Giới hạn rất quan trọng

- Collection `orders_by_customer_v2` là **target generation mới và trống** trong một lab sạch.
- Pipeline `$merge` ở đây **không tự xóa records đã tồn tại ở target nhưng source không còn**. Vì thế rerun một projection đang có sẵn không phải full reconciliation. Rebuild đúng nên tạo target generation mới hoặc có explicit delete handling.
- `whenMatched:"replace"` không bảo vệ source revision khi snapshot và CDC chạy song song. **Không áp nguyên lệnh vào một index đang nhận live events**.
- Pipeline dùng `deleted:false` nên O005 không visible, nhưng tombstone metadata **không được lưu trong projection**. Online replay cần một nơi lưu source version/deletion state.
- Không có user/tenant authorization ở ví dụ shell; ứng dụng thật phải enforce access scope.
- Đây là demo Mongo aggregation, không phải CDC/outbox engine.

### Verify read model

```javascript
sourceDb.orders_by_customer_v2.countDocuments({});

sourceDb.orders_by_customer_v2.find(
  {tenantId: "T01", customerId: "C001"},
  {_id: 1, orderId: 1, status: 1, sourceRevision: 1}
).sort({_id: 1}).toArray();

sourceDb.orders_by_customer_v2.getIndexes();
```

Nếu Nhánh A đã chạy đầy đủ, kỳ vọng:

| Phép kiểm | Kỳ vọng |
|---|---|
| Total source documents | 6, bao gồm O005 tombstone |
| Total active source documents | 5 |
| Derived active documents | 5 |
| T01/C001 active | O001, O002, O006 |
| O001 derived status/revision | `SHIPPED` / 5 |
| O005 derived visible | Không |
| T02/C003 derived | O004 |
| Index | `tenant_customer_order` |

Nếu không chạy bước post-backup updates, expected counts và version sẽ khác; **không coi mismatch với một fixture chưa được thiết lập là lỗi database**.

## 35. Java 17: một chương trình rebuild có thể chạy độc lập

Để diễn tập crash/replay mà không cần broker hoặc database thật, lưu đoạn sau thành `DerivedRebuildLab.java` trong một thư mục thực hành riêng. Đó là file người học tạo nếu muốn chạy; bài Markdown hiện tại không tự tạo file Java nào.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class DerivedRebuildLab {
    record Row(
        String tenant,
        String orderId,
        String customer,
        String status,
        long revision,
        boolean deleted
    ) {}

    record Change(long position, Row after) {}

    static final class Projection {
        private final Map<String, Row> state = new HashMap<>();

        private static String key(Row row) {
            // Synthetic IDs cannot contain "|".
            return row.tenant() + "|" + row.orderId();
        }

        void apply(Row next) {
            String id = key(next);
            Row current = state.get(id);

            if (current == null
                    || next.revision() > current.revision()) {
                state.put(id, next);
                return;
            }

            if (next.revision() == current.revision()
                    && !Objects.equals(next, current)) {
                throw new IllegalStateException(
                    "Conflicting payload for same revision: " + id
                );
            }
            // Older versions and identical duplicate events are no-ops.
        }

        Row get(String tenant, String orderId) {
            return state.get(tenant + "|" + orderId);
        }

        List<Row> visibleForCustomer(
                String tenant, String customer) {
            var result = new ArrayList<Row>();
            for (Row row : state.values()) {
                if (row.tenant().equals(tenant)
                        && row.customer().equals(customer)
                        && !row.deleted()) {
                    result.add(row);
                }
            }
            result.sort((a, b) ->
                a.orderId().compareTo(b.orderId()));
            return result;
        }

        long visibleCount() {
            return state.values().stream()
                .filter(row -> !row.deleted())
                .count();
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        var projection = new Projection();

        // Snapshot S has a consistent change boundary C100.
        var snapshot = List.of(
            new Row("T01", "O001", "C001", "PAID", 4, false),
            new Row("T01", "O002", "C001", "NEW", 2, false),
            new Row("T01", "O003", "C002", "CANCELED", 3, false),
            new Row("T02", "O004", "C003", "PAID", 1, false),
            new Row("T01", "O005", "C001", "CANCELED", 5, true)
        );

        for (Row row : snapshot) {
            projection.apply(row);
        }

        var changes = List.of(
            new Change(
                101,
                new Row("T01", "O001", "C001",
                        "SHIPPED", 5, false)
            ),
            new Change(
                102,
                new Row("T01", "O002", "C001",
                        "CANCELED", 3, true)
            ),
            new Change(
                103,
                new Row("T01", "O006", "C001",
                        "NEW", 1, false)
            )
        );

        long checkpoint = 100;

        // Simulated crash: sink applied C101, checkpoint not saved.
        projection.apply(changes.get(0).after());

        // On restart, replay from the older checkpoint C100.
        for (Change change : changes) {
            if (change.position() > checkpoint) {
                projection.apply(change.after());
                checkpoint = change.position();
            }
        }

        // Simulate a late snapshot row after CDC newer revision.
        projection.apply(snapshot.get(0));

        require(checkpoint == 103, "checkpoint not advanced");
        require(projection.get("T01", "O001").revision() == 5,
                "stale snapshot overwrote O001");
        require(projection.get("T01", "O001")
                .status().equals("SHIPPED"),
                "wrong O001 status");
        require(projection.get("T01", "O002").deleted(),
                "deleted O002 resurrected");
        require(projection.visibleCount() == 4,
                "incorrect active order count");
        require(
            projection.visibleForCustomer("T01", "C001")
                .size() == 2,
            "wrong customer projection membership"
        );

        System.out.println(
            "PASS: replay idempotent, tombstones preserved, "
                + "checkpoint=" + checkpoint
        );
    }
}
```

### Chạy ví dụ

```powershell
javac --release 17 DerivedRebuildLab.java
java DerivedRebuildLab
```

Kết quả mong đợi từ **chương trình** là:

```text
PASS: replay idempotent, tombstones preserved, checkpoint=103
```

Đây là output dự kiến nếu người học chạy chương trình thành công; tài liệu không khẳng định chương trình đã được chạy trong lượt soạn bài này.

## 36. Ý nghĩa và giới hạn của Java lab

Chương trình minh họa ba failure modes:

1. **Sink áp C101 nhưng checkpoint chưa tiến:** sau restart, C101 được replay. Revision guard giữ nguyên đúng kết quả.
2. **Delete event C102:** tombstone có revision 3 ngăn snapshot O002 rev2 hồi sinh.
3. **Snapshot O001 rev4 tới muộn:** projection đã có rev5 nên không ghi đè bằng v4.

### Điều mà chương trình **chưa** chứng minh

- `checkpoint` chỉ là biến RAM, không phải durable DB checkpoint.
- Snapshot S/C100 và change stream C101..103 là fixture **được cho sẵn**, không phải source APIs bảo đảm gap-free capture.
- Không có network timeout, concurrent workers, lease/epoch hoặc multi-shard ordering.
- Không có transactional sink write/checkpoint; một production pipeline phải giải quyết crash windows giữa hai systems.
- Không có persisted index, full-text analyzer, search refresh hoặc ACL.
- Nếu source revision bị reset sau entity recreate, comparator phải thêm source incarnation/epoch.
- Nếu event là delta thay vì full after-image, comparator đơn giản này **không đủ**.

Một PASS ở lab in-memory chỉ chứng minh một phần nhỏ của **replay algorithm**, không chứng nhận production rebuild.

## 37. Projection key thay đổi: cần xử lý membership cũ

Java lab lưu state theo `(tenant,orderId)`, rồi tạo customer view từ record hiện tại. Một target KV/DB thường lại dùng physical key:

```text
projection key = (tenant,customer,orderId)
```

Nếu customerId đổi:

```text
rev8:  (T01,C001,O001)
rev9:  (T01,C009,O001)
```

Chỉ viết bản mới tạo **hai projection rows**. Cần một protocol:

- Change event chứa old/new projection keys hoặc source pre-image.
- Writer tombstone/remove old key, upsert new key, có version guards.
- Nếu không có atomic multi-key update, có thể phải chịu temporary inconsistency/compensation với explicit freshness contract.
- Hoặc rebuild toàn bộ target generation mới, verify và cutover thay cho incremental repair.

### Với search engine

Chọn document ID ổn định theo source identity (ví dụ tenant+order) thường tránh chuyện key thay đổi khi customerId đổi; customerId là **field được index**, không phải document ID. Nhưng bản cũ vẫn có thể search-visible tới refresh, và delete/version ordering vẫn phải xử lý.

## 38. Checkpoint trong production phải đặt sau sink durable effect

Một pipeline:

```text
Read source event E101
  |
  v
Apply to search / customer projection
  |
  v
Confirm sink outcome (per-item, correct durability)
  |
  v
CAS checkpoint to E101
```

### Crash windows

| Khi crash | Tình trạng | Phản ứng |
|---|---|---|
| Sau read, trước apply | Source event chưa được ghi | Replay |
| Sau checkpoint, trước sink apply | Gap/mất event | **Sai protocol** |
| Sau sink commit, trước checkpoint | Sink đã ghi, metadata cũ | Replay idempotent |
| Sink commit nhưng ACK mất | Unknown outcome | Reconcile/conditional replay |
| Checkpoint CAS commit nhưng ACK mất | Metadata outcome unknown | Readback checkpoint |

### Contiguous progress

Nếu một worker song song hoàn tất events:

```text
Received:  101,102,103,104
Applied:   101,103,104
Pending:   102
```

Không checkpoint vượt 102 chỉ vì đã xử lý 104. Với nhiều stream partitions, lưu checkpoint **per partition** hoặc theo documented source position; không lấy max offset toàn bộ topic thay thế.

## 39. Worker lease, generation và fencing

Một controller giao rebuild range A cho W1 với epoch 7. W1 bị pause lâu; lease hết hạn, W2 nhận epoch 8. W1 tỉnh lại:

```text
W1(epoch7) attempts stale apply or checkpoint
W2(epoch8) already owns the range
```

### Yêu cầu

- Checkpoint CAS phải reject epoch cũ.
- Target writes phải có revision/epoch guard phù hợp; chặn checkpoint **không tự chặn** W1 ghi dữ liệu cũ vào target.
- Worker dùng bounded retry, không tạo duplicates.
- Lease expiry không có nghĩa process cũ đã chết.

### Nếu không thể fence sink trực tiếp

Dùng deterministic keys, source revision guard và reconciliation; có thể cô lập generation target mới hoặc single-writer ownership protocol. Không nói “distributed lock giải quyết hết” nếu stale worker vẫn có quyền ghi.

## 40. Batching và backpressure khi rebuild hàng triệu records

Một thiết kế:

```text
Flush page when:
  items >= maxItems
  OR bytes >= maxBytes
  OR wait time >= maxWait

In-flight batches <= maxConcurrentWrites
Buffered bytes <= maxQueuedBytes
```

### Vì sao cần byte limit?

Một batch 100 documents có thể rất nhỏ hoặc rất lớn. API có item/request byte limits và network/memory/GC cost. Khi sink throttle, reader không thể tiếp tục fetch unbounded dữ liệu vào heap.

### Throughput mismatch

```text
Reader:  10,000 records/s
Writer:   3,000 records/s
Queue:   +7,000 records/s
```

Sau 120 giây, backlog lý thuyết tăng:

\[
7000\times120=840000\ \text{records}
\]

Đây là lý do dùng bounded queues, rate limiting, backoff/jitter và stop fetching khi downstream quá tải. **Không tiến checkpoint theo tốc độ reader**.

## 41. Partial bulk success

Một request:

```text
Input:   A B C D E
Result: OK OK FAIL OK WAIT
```

Không đánh dấu toàn batch là COMPLETE dựa vào HTTP status chung. Nhiều APIs có per-item status:

- DynamoDB `BatchWriteItem` trả `UnprocessedItems`.
- Elasticsearch/OpenSearch Bulk API trả item-level `status/error`.
- MongoDB bulk write có thể có write errors/write concern errors và partial outcome.
- Cassandra/Redis batched requests có semantics riêng, không tự atomic qua mọi keys.

### Quy tắc

1. Gắn mỗi request item với deterministic source identity/revision.
2. Ghi rõ item nào success, retryable, permanent, unknown.
3. Retry với idempotency và bounded budget.
4. Quarantine permanent errors theo approved policy, không âm thầm bỏ.
5. Chỉ checkpoint qua một **contiguous completed prefix**.

### Không tự coi duplicate key là PASS

Target có cùng key nhưng payload khác tenant hoặc revision sai là **conflict**, không phải một duplicate đã xử lý hợp lệ.

## 42. Verifier phải so cùng một source boundary

Nếu source tiếp tục cập nhật:

```text
Source now: C150
Target verified: C140
```

So target C140 với source live C150 có thể báo mismatch hợp lệ do lag. Cần một trong các cách:

- Đọc source snapshot tương ứng C140.
- Replay target tới một boundary C150 và giữ source freeze/commit barrier phù hợp trước khi verify.
- Tính expected model từ snapshot + changes đến chính boundary C140.

### Ba phép đối soát

1. **Coverage:** mọi required key có mặt, không có extra key.
2. **Version/content:** mỗi key có sourceRevision/tombstone và relevant fields đúng.
3. **Query semantics:** query theo tenant/customer, sort/pagination/index visibility trả kết quả đúng.

### Hash và canonicalization

Nếu source và target dùng schema khác, hash raw JSON/BSON thường không bằng nhau. Cần transform hai bên về **canonical business representation** với documented schema version, numeric precision, timezone và missing-vs-null policy.

## 43. Search refresh và cutover

Một index Bulk API trả success nhưng search query có thể chưa nhìn thấy bản mới vì refresh semantics. Khi rebuild search:

```text
Create index-v2
  |
  v
Bulk import baseline
  |
  v
Apply incremental changes
  |
  v
Wait for query-visible checkpoint
  |
  v
Verify query parity
  |
  v
Switch read alias / routing under guarded protocol
```

### Những điều không được suy

- `index write ACK` không luôn bằng `search-visible`.
- `consumer lag=0` không có nghĩa source connector không bị dừng.
- `alias switched` không có nghĩa mọi app clients lập tức chuyển route hoặc dữ liệu không tiếp tục stale.
- `search count matches` không có nghĩa không missing/duplicate entities.

### Cutover rollback

Giữ `index-v1` trong observation/rollback window đã phê duyệt. Nếu after-cutover writes chỉ tới v2, rollback về v1 không an toàn nếu chưa sync; cần forward fix hoặc reverse replay/reconciliation theo protocol.

## 44. Có nên backup chính projection không?

Một index lớn có thể mất nhiều giờ rebuild, trong khi restore snapshot index mất ít thời gian hơn:

```text
Source (authoritative)
    |
    +--> Derived index backup at C100
             |
             v
        Restore index at C100
             |
             v
        Replay CDC C101..C180
             |
             v
        Verify against source C180
```

### Khi nên cân nhắc

- Tốc độ rebuild từ full source quá chậm so RTO.
- Index mapping/model version tương thích.
- Có log coverage từ index snapshot boundary.
- Có thể verify và apply updates/deletes an toàn.
- Backup index có data protection/retention phù hợp.

### Nhưng index backup không thay source backup

Một search index có thể thiếu fields, transaction metadata hoặc historical events. Nó không đủ để tái tạo **source ledger**. Nếu source mất, không coi index là authoritative backup trừ khi đã cố ý thiết kế và chứng minh tính đầy đủ.

## 45. Source identity và generation phải theo suốt job

Một source collection bị drop và recreate cùng tên `orders`. Rebuild worker vẫn giữ checkpoint token cũ:

```text
Old source:
  clusterId=A, incarnation=K1, position=C100

New source:
  clusterId=A, incarnation=K2, position=C100?
```

Tên collection giống nhau không đảm bảo token có nghĩa giống nhau. Metadata cần:

- Source cluster/table/collection identity.
- Source incarnation/generation nếu có.
- Snapshot ID và consistent boundary.
- Query/partition scope.
- Mapping/schema version.
- Checkpoint version/owner epoch.
- Target index generation.

### Khi identity mismatch

**Dừng**, không tự “tiếp tục” ở token cũ. Xác định resnapshot/new target generation và replay strategy. Một source revision số lớn từ incarnation K1 không được tự dùng để chặn writes hợp lệ của K2.

## 46. Opaque continuation token không phải offset chung

Trong một số engines:

```text
Source scan -> page records + opaque nextToken
```

Token có thể gắn:

- Session/transaction state.
- Query/filter/sort.
- Partition/segment.
- Driver version hoặc topology.
- Snapshot lifetime.

Không được parse/sửa/token+1 để “bỏ qua lỗi”.

### Khi token hết hạn

1. Xác định source snapshot/log position còn hợp lệ không.
2. Nếu có stable keyset: restart range từ last durable key theo same snapshot.
3. Nếu có sealed chunks: import từ files mà không cần source cursor.
4. Nếu source history mất: resnapshot và rebuild target generation mới.
5. Báo progress reset/version change rõ; không che bằng một con số 99%.

### Offset không thay keyset

`skip(80_000_000)` có thể phải scan sâu và bị lệch nếu source insert/delete. Khi dựng lại source snapshot dài, cần deterministic traversal hoặc engine-managed snapshot/restore procedure.

## 47. Source retention và thời hạn có thể catch up

Giả sử:

```text
CDC log retention:     60 minutes
Full baseline rebuild: 55 minutes
Catch-up backlog:      20 minutes at current consumer rate
```

Nếu new changes liên tục và retention chỉ 60 phút, rebuild có thể bị **log truncation trước khi bắt kịp**.

### Nguyên tắc

- Đặt retention headroom theo worst-case rebuild, catch-up và incident response.
- Theo dõi source earliest available position và consumer required start position.
- Đặt alert trước khi retention headroom về 0.
- Khi gap đã mất, không skip offset để “tiếp tục”; resnapshot/reconcile theo protocol.

### Throughput điều kiện hội tụ

Nếu change stream sinh:

\[
\lambda_{\mathrm{in}}=3000\ \text{events/s}
\]

và consumer chỉ xử lý:

\[
\mu_{\mathrm{out}}=2500\ \text{events/s}
\]

thì backlog tăng trung bình khoảng 500 events/s (trước khi tính bursts/retries); **không thể catch up** khi tình trạng này kéo dài. Cần tăng bounded capacity, giảm offered load theo chính sách hoặc đổi chiến lược rebuild.

## 48. Progress: đếm nhiều pha, không dùng một thanh “99%”

Một bảng:

| Counter | Có nghĩa | Có dùng làm cutover gate? |
|---|---|---|
| `source_scanned` | Source records được đọc | Không một mình |
| `snapshot_exported` | Records/chunks ra staging | Không |
| `sink_attempted` | Writes đã gửi | Không |
| `sink_confirmed` | Items có durable outcomes | Một phần |
| `checkpointed` | Contiguous durable source progress | Một phần |
| `verified` | Records/chunks đã đối soát | Một phần |
| `cdc_caught_up` | Đến source boundary đã xác nhận | Một phần |
| `search_visible` | API query thấy index mới | Có, theo SLO |
| `cutover_eligible` | Tất cả hard gates đạt | Tổng hợp |

### Có thể hiển thị

```text
Snapshot export:     100% of sealed chunks
Import:               98% of items durably applied
Verification:         95% of required items
CDC oldest event age: 47s
Search visibility:    23s behind source
Cutover-ready:        NO (verification mismatch)
```

Một estimate tổng record từ scan statistics không phải số chính xác. Nếu không có exact denominator, hiển thị bytes/records và ranges completed **không bịa phần trăm**.

## 49. ETA và RTO khi rebuild

Nếu còn \(D\) bytes và throughput bền là \(v\) bytes/s:

\[
\mathrm{ETA}_{\mathrm{baseline}}\approx D/v
\]

Nhưng **RTO toàn hệ** còn:

```text
Baseline data transfer
+ sink indexing / compaction
+ CDC catch-up
+ verification and repair
+ application validation
+ cutover/routing
```

### Ví dụ

Một pipeline copy 100 GiB ở 50 MiB/s:

\[
100\times1024/50=2048\ \mathrm{s}\approx34.1\ \mathrm{phút}
\]

Đó chỉ là thành phần bytes/throughput lý tưởng, chưa tính serializer, index builds, throttling, source log retention, network variance và verification.

### Tránh false ETA

Giá trị “remaining 5 minutes” có thể kéo dài hàng giờ nếu stage cuối là một hot shard hoặc 1% records lỗi. Nên báo **pha, blocker, cửa sổ đo và độ không chắc**.

## 50. Rebuild ở background nhưng người dùng vẫn truy cập

Một cách giảm downtime:

```text
Read alias "orders-current" -> index-v1

Rebuild process:
  snapshot + CDC -> index-v2
  validate index-v2

Cutover:
  move alias/routes -> index-v2
```

### Điều kiện

- `index-v1` vẫn phục vụ trong lúc v2 được dựng.
- Writes mới tiếp tục được capture với source boundary không gap.
- Khi switch alias, v2 đã đủ mới theo business freshness contract.
- Có rollback observation window nhưng phải xử lý target-only writes.
- App clients/pools có route/version caching; verify actual traffic.

### Không áp với mọi source

Nếu chính **source database** đã mất, không có authority để dùng trong khi rebuild; đó là Nhánh A/DR. Blue-green index rebuild chỉ giúp khi nguồn còn đúng và khả dụng.

## 51. Shadow reads và query parity

Để verify v2 trước cutover:

```text
Application read:
   |
   +-- active index-v1 -> response user
   |
   +-- shadow index-v2 -> compare asynchronously
```

Đo:

- Tập keys, thứ tự sort, page tokens.
- Tenant filters và authorization.
- Status/revisions/deletes.
- Search relevance/geo/vector recall nếu có.
- p95/p99 query latency và error rate.

### So ở cùng source boundary

Nếu v1 đang ở C180 còn v2 ở C175, một diff có thể là expected freshness lag, không phải corruption. Dùng source revisions/canonical expected state hoặc đợi v2 bắt kịp trước khi so.

### Không tạo side effect

Shadow path chỉ nên chạy read-only, sampling/throttling có kiểm soát, không trigger payments hoặc state mutation. Không log raw PII trong comparator output.

## 52. Một số projection không thể chỉ “clear and rebuild”

Ví dụ:

```text
Search index: derived from orders -- rebuildable.

Marketing list:
  source orders + manual curation tags stored ONLY in list.
```

Nếu xóa marketing list rồi build lại từ orders, **manual tags biến mất**. Trước khi coi bảng nào derived:

1. Liệt kê từng field và authority của field đó.
2. Kiểm events/snapshots có đủ phục hồi field không.
3. Tách user-managed overrides vào source riêng có backup.
4. Mô tả merge policy giữa source và overrides.

### Quy tắc

Đơn vị “rebuildable” không chỉ là **collection**; có thể là một subset fields trong collection. Phải xác minh ownership per field.

## 53. Partial failure và quarantine

Một record:

```json
{
  "tenantId": "T01",
  "orderId": "O999",
  "amountMinor": "not-a-number",
  "sourceRevision": 4
}
```

Transform không thể chuyển sang long an toàn.

### Phản ứng

- **FAIL_FAST:** dừng nếu strict correctness yêu cầu mọi records.
- **REPAIR_THEN_RETRY:** sửa schema/transform version rồi apply lại.
- **QUARANTINE:** nếu business policy cho phép, giữ terminal exception bền và report rõ số records chưa nhập.

### Tuyệt đối tránh

```text
catch (Exception ignored) { continue; }
```

Một loop bỏ records lỗi sẽ làm job đạt “100% scanned” nhưng projection thiếu dữ liệu. Nếu error vĩnh viễn, retry vô hạn cũng không giải quyết. Cần error category, max retries, owner và cutover blocker phù hợp.

### Security của quarantine

DLQ/quarantine có thể chứa full payload nhạy cảm. Encryption/least privilege/retention áp dụng giống source, không gửi record raw vào log/chat.

## 54. Fault injection cho Nhánh B

Trong lab, thử các cửa sổ:

| Lỗi được giả lập | Kết quả mong đợi |
|---|---|
| Crash sau read, trước sink | Checkpoint không tiến; replay |
| Crash sau sink commit, trước checkpoint | Replay idempotent |
| Checkpoint CAS commit, ACK mất | Re-read metadata, không đếm trùng |
| CDC event tới hai lần | Một logical effect |
| Event rev5 tới trước snapshot rev4 | Revision guard chặn stale overwrite |
| Delete rev3 tới trước snapshot rev2 | Tombstone chặn resurrection |
| Source cursor token hết hạn | Dừng/resnapshot theo protocol |
| Object chunk upload dở | Không seal manifest |
| Source log bị truncate trước catch-up | Báo rebuild-required, không skip |
| Target index throttling | Backpressure, không OOM |
| Worker lease mất rồi tỉnh lại | Old epoch bị fence |
| Mapping version thay giữa run | Không trộn silent versions |
| Alias switch thất bại một phần | Kiểm routing, rollback/forward-fix |
| Search API vẫn stale sau bulk ACK | Không coi cutover-ready |
| Tenant filter bug | Fail hard gate trước promote |

### Một test không đủ để tuyên bố exactly-once

Khi event E101 được replay hai lần mà state vẫn đúng, bạn chỉ chứng minh **idempotency theo mô hình đã thử**. Network, concurrent partitions, failures và transactional boundaries có thể tạo lịch sử khác; production cần nhiều test + reasoning về protocol.

## 55. Bài tập fault injection nối hai nhánh

Một kịch bản:

```text
1. Source backup at C100.
2. Source receives C101..C120.
3. Source becomes unavailable.
4. Restore snapshot C100.
5. Replay logs through C115 only (C116..C120 missing).
6. Rebuild search projection from restored source C115.
```

### Câu hỏi

- RPO thực tế liên quan 5 events chưa phục hồi là gì?
- Search projection có thể “bắt kịp” tới C120 không nếu source đã dừng tại C115?
- Nếu search index cũ chứa C120 nhưng source restore chỉ C115, có nên dùng index cũ làm authority để hồi phục không?
- Cần policy nào cho acknowledged writes bị mất?

### Kết luận đúng

Projection rebuilt đến C115 có thể **hoàn toàn đúng so với source đã restore**, nhưng end-to-end business có thể **vi phạm RPO** vì thiếu events C116..C120. Đừng lấy projection parity với source sau restore làm bằng chứng không mất business writes.

## 56. So sánh chi phí của restore projection và full rebuild

| Phương án | Ưu điểm | Rủi ro/chi phí |
|---|---|---|
| Full rebuild từ source hiện tại | Ít phụ thuộc backup projection cũ | Scan lớn, indexing cost, source load |
| Restore projection snapshot + replay CDC | Có thể nhanh hơn | Snapshot mapping/source boundary compatibility |
| Reprocess toàn bộ event log | Dễ giữ event semantics nếu log đủ | Retention/ordering/schema evolution |
| Selective repair theo mismatches | Ít ghi hơn | Cần oracle phát hiện đầy đủ differences |
| Blue-green rebuild | Tránh phá index đang phục vụ | Tăng storage/CPU tạm thời, cutover complexity |

### Quyết định theo

1. Source còn đầy đủ/đúng không?
2. Projection có thể tái tạo 100% fields không?
3. Có log và schema history đủ retention không?
4. Rebuild time so với RTO/freshness SLO?
5. Cost/source impact và target indexing capacity?
6. Có thể verify/cutover/rollback an toàn không?

## 57. Multi-tenant và data residency khi rebuild

Một full export source có thể chứa nhiều tenants và khu vực dữ liệu:

```text
Region VN: tenant group A
Region EU: tenant group B
```

Một projection rebuild job chạy tại region khác có thể vi phạm residency ngay cả khi cuối cùng filter đúng. Cần:

- Tenant-scoped extract/processing.
- Region-specific workers/object storage.
- Index alias và authorization tương thích.
- Không gửi PII vào debugging topics.
- Retention/delete propagation trên snapshots, backup và DLQ.
- Audit truy cập, restore credentials và KMS.

### “Hash ID” vẫn có thể nhạy cảm

Hash/embeddings/pseudonyms có thể liên kết tới cá nhân hoặc entity khác. Tuân chính sách dữ liệu theo nội dung/threat model, không tự coi chúng là ẩn danh hoàn toàn.

## 58. Khi dữ liệu derived đã từng phục vụ sai kết quả

Khôi phục projection đúng **không xóa hậu quả** của một response sai đã được người dùng hoặc downstream sử dụng:

```text
Stale inventory search -> user sees room available.
Downstream workflow acted on stale data.
Projection rebuilt correctly.
```

Nếu downstream đã tạo booking/payment sai, cần:

- Xác định affected time window và request histories.
- Reconcile với authoritative transaction ledger.
- Thực hiện compensation/hỗ trợ khách hàng theo chính sách.
- Cập nhật guard để critical action không dùng stale projection làm authority.

**Rebuild dữ liệu không thay thế việc đối soát các side effects đã xảy ra do dữ liệu sai.**

## 59. Product/UI: trạng thái “pending” đôi khi đúng hơn dữ liệu cũ

Nếu user vừa thanh toán, source ledger đã ACK nhưng search projection chưa catch up:

```text
Authoritative booking: CONFIRMED
Search view:           PENDING
```

Nếu ứng dụng hứa read-your-writes:

- Có thể đọc trực tiếp authority cho booking vừa cập nhật.
- Dùng minimum source revision gate, đợi projection trong deadline.
- Hiển thị trạng thái `processing/syncing` nếu business cho phép.
- Nếu không có state đủ mới, trả lỗi/pending rõ, không tuyên bố confirmed hay failed sai.

Với catalog/search kết quả eventual, có thể có freshness SLO rộng hơn. Không áp cùng một read contract cho mọi màn hình.

## 60. Nhánh B hoàn tất khi nào?

Điều kiện **READY_TO_CUTOVER**:

1. Snapshot/baseline generation đầy đủ và immutable boundary được ghi lại.
2. Changes từ boundary đến cutover position có coverage không gap.
3. Tất cả required records có terminal outcomes: applied/verified hoặc exception được phê duyệt.
4. Không có conflict về source revision/tombstone/tenant identity.
5. Canonical data và business invariants đúng.
6. Index/search query visibility đạt freshness contract.
7. Query parity/latency/capacity ở workload đại diện.
8. Authz, region/data policy, KMS và security review hợp lệ.
9. Old/new routing, rollback/forward-fix và owner rõ ràng.
10. Có monitoring sau cutover và retained source/old target theo observation window.

Khi chỉ một mục bắt buộc chưa đạt, không tự chuyển job sang `COMPLETED` vì `records_read=100%`.

---

# Phần III — Vận hành, kiểm chứng và các hệ NoSQL khác

## 61. MongoDB trong một DR drill thật

MongoDB lab dùng standalone container và freeze writes. Với production replica set/sharded cluster, kế hoạch có thêm:

- Thẩm định **backup topology**: node, shard, config server, roles, index metadata.
- Lựa chọn backup snapshot/log/PITR theo provider/tooling được hỗ trợ.
- Ghi majority commit/cluster time hoặc consistent recovery boundary theo protocol.
- Kiểm shard key/index/collation/validation rules và mapping version.
- Khôi phục vào **replica set/cluster riêng**, không chỉ một local standalone.
- Kiểm driver connection strings/read preference sau routing cutover.
- Đối soát acknowledged writes với write concern cần bảo đảm.
- Rebuild/change stream resume tokens sau restore và khôi phục read projections.

### Không dùng `mongodump --oplog` như câu thần chú

Oplog-based backup workflows có điều kiện về topology, thời điểm capture và tương thích restore. `mongodump --oplog` không áp dụng như một general PITR API cho mọi MongoDB topology, đặc biệt sharded clusters. Phải dùng tài liệu, phiên bản và restore strategy phù hợp với cụm thực tế.

### Thử đúng business read paths

Một restore đã có record trong collection nhưng compound index không được phục hồi đúng có thể khiến API liệt kê orders bị scan chậm. Kiểm MongoDB query plans và p99, không chỉ `countDocuments`.

## 62. DynamoDB: backup/PITR, table restore và Streams

Một managed NoSQL như DynamoDB có thể cung cấp on-demand backup/PITR và restore thành table mới theo capability của dịch vụ. Kế hoạch cần:

1. Chọn backup/recovery timestamp trong retention window đã cấu hình.
2. Xác minh table ARN/account/region và quyền IAM/KMS.
3. Restore vào **new table name**, tránh overwrite nguồn.
4. Kiểm PK/SK, GSI, TTL configuration, capacity settings, encryption và streams setup theo provider semantics.
5. Kiểm dữ liệu với `GetItem`/`Query` đúng consistency mode.
6. Đổi application config/route chỉ sau acceptance checks.
7. Thiết kế lại CDC/Streams consumers nếu source stream ARN/sequence/retention thay đổi.

### Cẩn thận với GSI

Một strongly consistent read trên base table không chứng minh GSI đã cập nhật trong target, và GSI không hỗ trợ strong consistency như base table. Khi restore và cho app query qua GSI, đo **index ready state và query parity**.

### PITR không tự đưa dữ liệu vào app

Ngay cả khi restore table hoàn tất, cần IAM, encryption keys, index configuration, streams/TTL, connection config, quotas và testing. **Table restored ≠ user workflow recovered**.

## 63. Cassandra/ScyllaDB: snapshots, SSTables và repair

Một Cassandra-family database có snapshot mechanisms (ví dụ `nodetool snapshot`) và incremental backup/config riêng:

- Schema/keyspace/table definitions.
- Replication factor và placement theo DC/rack.
- SSTables/snapshot files và compatibility version.
- Commit logs, incremental changes và rebuild policy nếu cần PITR-like recovery.
- Token ownership/ring topology và restored node identity.
- Tombstones/TTL và compaction/repair state.
- Read/write consistency levels sau restore.

### Đừng copy một SSTable tùy tiện vào live node

Đường restore có thể yêu cầu stop/restart, validated file placement, `sstableloader` hoặc documented import mechanisms tùy engine/version. Copy trực tiếp files khi engine đang ghi có thể phá consistency hoặc làm data orphaned. Bài này không đưa lệnh ghi đè SSTable để tránh áp sai cho topology không rõ.

### Derived query tables

Nếu `orders_by_customer` là bảng duplicate từ `orders_by_id`, có hai con đường:

1. Restore snapshots của cả hai tables ở một recovery point nhất quán.
2. Chọn một table/ledger có authority rồi rebuild query table còn lại.

Nếu cả hai tables cùng có writes độc lập không có sync protocol, **không rõ cái nào là source**, cần ownership/reconciliation trước khi rebuild.

### Test failure

Mất một DC, repair/read CL và rebuild table dưới tombstone-heavy workload. Không coi RF=3 mặc nhiên là ba fault domains nếu replicas đặt sai.

## 64. Redis: RDB, AOF và cache rebuild

Redis có thể là:

- **Cache**, có thể refill từ authoritative database.
- **Session store**, cần durability/expiry policy.
- **Authoritative key-value state**, cần đánh giá persistence và failover/RPO.

### RDB

RDB lưu snapshot theo policy; recent acknowledged writes sau snapshot có thể không nằm trong file.

### AOF

AOF lưu log commands với fsync policy được cấu hình. Durability window và recovery behavior phụ thuộc cấu hình/engine/version; không suy AOF tự có global transaction semantics.

### Cache rebuild

Nếu Redis bị flush trong lab:

```text
Source NoSQL -> bounded warm-up -> Redis cache
```

Cần:

- Tránh stampede: singleflight/request coalescing, rate limit, prewarm hot keys.
- TTL không kéo dài lifetime dữ liệu ngoài policy.
- Versioned cache entries không ghi rev cũ đè rev mới.
- Không cache sensitive authz allow quá freshness contract.
- Quan sát DB fallback p99/capacity khi cache cold.

### Redis Cluster

Slot placement, primary/replica failover và keys ở nhiều hash slots có impact tới rebuild/cross-key operations. Backup một node không tự bảo đảm snapshot consistent cho toàn cluster.

## 65. Elasticsearch/OpenSearch: restore snapshot hay reindex?

Khi search index mất:

**Restore engine snapshot** nếu có index snapshot tương thích, được bảo vệ đúng và đủ mới.

**Rebuild/reindex từ source** nếu source đúng, mapping mới khác, snapshot cũ không tin cậy hoặc muốn loại corruption.

### Các yếu tố cần kiểm

- Snapshot repository có quyền đọc/giải mã từ recovery domain.
- Index mapping/analyzer/settings/version compatibility.
- Shard allocation/replicas và disk watermark.
- Index alias/query routing và field-level access.
- Partial snapshot failures và dữ liệu chưa được capture.
- Restore đến source revision nào, còn CDC events nào cần replay.
- Refresh/PIT/query-visible semantics.

### Không tự dùng `_reindex` từ index đã hỏng làm nguồn đúng

Nếu source index chứa missing/stale documents, reindex chính nó chỉ sao chép lỗi. Khi cần correctness, rebuild từ authoritative DB/log theo documented boundary.

### Search recovery finish

Chỉ coi query-ready sau:

```text
source-to-target coverage verified
index mappings/query parity verified
search refresh complete enough
tenant filters and deletes correct
latency and shard availability acceptable
```

## 66. Graph database: nodes, edges và dữ liệu dẫn xuất

Nếu graph chỉ là projection phục vụ recommendation/fraud:

```text
Customers + Orders + Devices -> Graph nodes and relationships
```

Rebuild cần:

- Stable node IDs/tenant scope.
- Mapping source ID → graph node identity.
- Node creation trước hoặc cùng consistency protocol với edges.
- Edge type, direction, uniqueness, properties.
- Delete/relationship detach semantics.
- Schema constraints/indexes và graph query parity.

### Integrity

Một graph có đúng số nodes nhưng thiếu 10% edges **không hoàn tất**. Cần:

- Dangling edge checks.
- Degree distribution/hot-node checks.
- Representative path/traversal assertions.
- Cross-tenant edge isolation.
- Query latency/relevance checks nếu graph dùng online.

### Khi graph còn chứa manual edges

Nếu người dùng tự tạo relationship trực tiếp trong graph và source DB không có records đó, graph **không phải projection hoàn toàn rebuildable**. Cần backup graph hoặc chuyển những edges này vào authority riêng.

## 67. Vector index: model version là một phần dữ liệu

Một vector projection:

```json
{
  "documentId": "T01#P003",
  "embeddingModel": "embedding-v3",
  "embeddingDimension": 768,
  "sourceRevision": 42,
  "tenantId": "T01"
}
```

Rebuild cần xác định:

- Cùng embedding model/tokenization/normalization và dimension.
- Approximate nearest neighbor index config.
- Metadata filters và tenant scoping.
- Source updates/deletes/TLL propagation.
- Cost tính embeddings và index rebuild.
- Query recall@k, p99 và correctness của filters.

### Nếu đổi embedding model

Một query vector v4 không nhất thiết so similarity trực tiếp với toàn index v3 một cách có nghĩa. Cần index generation/model version riêng, validate relevance rồi cutover.

### Exact vs approximate

ANN không trả nearest exact trong mọi trường hợp; đó có thể là behavior được chấp nhận theo recall SLO. Nhưng **tenant filter hoặc deleted-record exclusion phải đúng**, không được viện lý do “approximate” để bỏ qua security/business constraints.

## 68. Analytics projection và mốc báo cáo

Một bảng tổng hợp:

```text
daily_revenue_by_tenant
  tenantId, businessDate, paidAmountMinor
```

Nếu rebuild từ event log:

- Define timezone/business-day boundary.
- Define paid/refunded/canceled status semantics.
- Avoid double-counting duplicate events.
- Handle late events and corrections.
- Select source recovery/reporting cut-off.

### Test số tiền

Không dùng floating-point arbitrary để tính tổng tiền. Sử dụng integer minor units/Decimal theo currency exponent và business rules. Reconciliation cần so với authoritative payment ledger, không chỉ raw booking statuses.

### Không gộp snapshot từ các thời điểm khác

Một bảng analytics báo “as of 12:00” phải thực sự mô tả consistent source boundary; nếu kết hợp orders tới 12:00 và refunds tới 11:00 mà không ghi nhận, có thể tạo báo cáo sai.

## 69. Backup của dữ liệu nhạy cảm có thời hạn tồn tại riêng

Giả sử user xóa địa chỉ lúc 10:00:

```text
Live source: delete applied at 10:00.
Old backup: contains address from 09:00.
Derived search: may still contain stale address.
Restore at 11:00: could reintroduce deleted data.
```

### Trong DR policy cần

- Deletion ledger/tombstone với authoritative revision.
- Privacy retention/backup lifecycle có phê duyệt.
- Reapply deletion obligations sau restore khi quy trình yêu cầu.
- Cleanup/quarantine old exports và snapshots theo policy.
- Kiểm search/cache/index không hiển thị dữ liệu đã bị xóa.

### Không giữ tombstone payload quá nhiều

Một tombstone chỉ cần identity/revision/deleted flag nếu đủ để chặn resurrection. Lưu raw PII “để debug” sau delete có thể vi phạm retention/data minimization.

## 70. Backup encryption và khả năng giải mã trong DR

Một lỗi phổ biến:

```text
Region R1: production DB and KMS access.
Region R2: backup archive stored.
Incident: R1 unavailable.
Restore worker in R2: no decrypt grant/key access.
```

Backup vẫn có, nhưng **không phục hồi được**.

### Diễn tập đúng

1. Dùng bản backup synthetic hoặc được phê duyệt trong security-controlled environment.
2. Chạy restore với **standby identity**, không dùng credential cá nhân có quyền rộng.
3. Kiểm read/list/decrypt permissions theo least privilege.
4. Kiểm key policy/rotation/multi-region capability.
5. Verify object integrity và manifest provenance.
6. Ghi audit access/restore operations.

### Không sửa bằng cách bỏ mã hóa

Tắt encryption, mở public bucket hoặc hard-code secrets để “rút ngắn RTO” có thể tạo sự cố bảo mật nghiêm trọng. DR readiness và security là **hai điều kiện đồng thời**.

## 71. Backup isolation trước ransomware/sai thao tác

Replication cùng account và cùng quyền admin có thể khiến attacker hoặc lỗi script xóa luôn backups. Một kế hoạch cần:

- Identity/quyền backup tách khỏi primary write role.
- Immutable/locked backup retention theo policy.
- Versioned objects/snapshots, deletion protection.
- Cross-account/region copy nếu cần DR.
- Audit và alert khi backup retention/immutability đổi.
- Restore test độc lập.

### Không có bảo đảm tuyệt đối

Một backup “immutable” vẫn phụ thuộc provider config, retention expiry, KMS access và governance; cần thử thực sự khôi phục bằng quyền khẩn cấp hợp lệ.

## 72. Đo khả năng chịu tải sau restore

Một restore hoàn tất dữ liệu nhưng service không đủ capacity:

```text
Recovered database: 100% required records present.
Recovered indexes: building.
Client requests: high pool waits and 30% timeouts.
```

Kết quả:

- **Data recovery** có thể PASS.
- **Application availability/RTO** có thể FAIL.

### Cần đo thêm

- Warm-up of caches/indexes.
- p95/p99 read/write latency.
- Throughput at expected/peak load.
- CPU/memory/disk I/O, network, replication lag.
- Query plans/index usage.
- Authz and tenant isolation.

Nếu dùng backup khôi phục sang instance nhỏ hơn production, cần ghi đó là test functional recovery chứ **không đủ chứng minh capacity RTO**.

## 73. Replication repair và secondary incident

Khi source/replicas rejoin sau outage:

```text
Replica catch-up
Index rebuild
Cache rewarm
CDC backlog drain
Compaction / repair
```

Những công việc đó tranh CPU, disk, network với user operations. Sau khi “network đã trở lại”, p99 có thể **xấu hơn** do repair storm.

### Điều khiển

- Giới hạn restore/repair concurrency.
- Theo dõi disk headroom cho compaction/rebuild.
- Đặt ưu tiên traffic nghiệp vụ quan trọng.
- Không scale down quá sớm khi catch-up chưa xong.
- Theo dõi post-fault recovery phase, không chỉ thời điểm hết fault.

### Không lạm dụng force leader/primary

Một thao tác forced promotion không có fencing/quorum phù hợp có thể tạo split-brain/conflicting writes, khiến restore khó hơn. Dùng documented failover protocol và audit quyết định.

## 74. RPO=0 có thể không phù hợp mọi workflow

Ví dụ:

| Dữ liệu | Recovery contract có thể cân nhắc |
|---|---|
| Payment ledger | Cần đối soát từng acknowledged business effect |
| Confirmed booking | Không chấp nhận âm thầm mất |
| Search index | Có thể rebuild từ source nếu đủ log |
| Recommendation cache | Có thể refill, chấp nhận cold start |
| Analytics hourly aggregate | Có thể rebuild từ event history |
| Session cache | TTL/UX policy quyết định |

### Nhấn mạnh

Đây là **gợi ý phân loại**, không phải mức RPO chuẩn để áp cho doanh nghiệp. RPO/RTO phải được business, security và vận hành thống nhất, có bằng chứng thực hiện.

---

# Phần IV — Runbook và bằng chứng diễn tập

## 75. Runbook tổng quát khi dữ liệu bị mất hoặc sai

```text
ALERT / INCIDENT
       |
       v
Identify affected workflows and authority
       |
       +-- Authority missing/corrupted?
       |          |
       |          v
       |   Choose backup/PITR restore (Branch A)
       |
       +-- Authority healthy, projection wrong?
                  |
                  v
           Rebuild/repair derived data (Branch B)
       |
       v
Safely isolate target and select recovery boundary
       |
       v
Restore/rebuild with bounded resources
       |
       v
Verify data + business invariants + app query paths
       |
       v
Guarded cutover, observe, reconcile and report
```

### Bước 1 — Triage

1. Phân loại symptom: missing source, corrupted source, stale index, failed CDC, authz issue, query outage.
2. Xác định source of truth và các biểu diễn phụ.
3. Chặn process đang tiếp tục gây corruption, theo incident policy.
4. Ghi incident start, các writes/ACKs bị ảnh hưởng và source recovery position.
5. Bảo toàn logs, audit, backups và operation histories.

### Bước 2 — Safety/approval

1. Xác minh tên cluster/account/region/namespace trước mọi lệnh.
2. Chuẩn bị **target cô lập**, rollback/forward-fix và abort conditions.
3. Đảm bảo identity/permissions/KMS đúng scope.
4. Không chạy destructive commands trên source đang phục vụ.

### Bước 3 — Execution

- Với Branch A: chọn verified backup/recovery point, restore, replay logs nếu cần.
- Với Branch B: chọn consistent snapshot+CDC boundary, build new generation, verify catch-up.

### Bước 4 — Acceptance

Kiểm records/keys/revisions/deletes/tenant isolation, ứng dụng API, latency/SLO và RPO. Có explicit sign-off trước khi đổi routing.

## 76. Kế hoạch trước khi gây lỗi trong game day

Một kế hoạch:

```yaml
experiment:
  id: "NOSQL-DR-589-EX1"
  environment: "isolated-preproduction"
  owner: "data-platform-oncall"
  approved_scope: "synthetic datasets only"
  scenario: "restore after source unavailable"
  hypothesis:
    target_restore_isolated: true
    data_matches_recorded_backup_boundary: true
    post_backup_writes_not_silently_claimed_recovered: true
  evidence:
    - "source-fixture-manifest"
    - "archive-integrity-hash"
    - "restore-command-audit"
    - "verification-results"
    - "elapsed-time-and-recovery-point"
  safety:
    max_data_bytes: "<approved>"
    max_duration: "<approved>"
    abort_if_unexpected_target: true
    no_real_customer_data: true
```

Đây là **mẫu kế hoạch**, không được dùng làm quyền phê duyệt tự động. Các giá trị `<approved>` phải được một người có trách nhiệm xác nhận trong môi trường thực tế.

### Điều kiện dừng

- Mệnh lệnh sắp chạy nhắm vào production/namespace ngoài phạm vi.
- Backup digest/manifest không khớp.
- Restore identity không có quyền hợp lệ.
- Có dấu hiệu dữ liệu nhạy cảm bị lộ.
- Source hoặc target production SLO bị ảnh hưởng ngoài budget.
- Verification có mismatch nghiêm trọng chưa được giải thích.

## 77. Không nên hành động gì khi restore thất bại?

| Phản ứng hấp tấp | Vì sao nguy hiểm | Thay thế |
|---|---|---|
| Thêm `--drop` vào target không kiểm | Xóa dữ liệu đang phục vụ | Target generation mới và xác minh tên |
| Dùng credential admin chung | Mở rộng blast radius/audit khó | Short-lived least-privilege role |
| Bỏ checksum vì công cụ báo success | Có thể restore artifact sai/hỏng | Xác minh manifest và integrity |
| Chuyển traffic ngay khi import xong | Index/ACL/CDC còn chưa sẵn | Acceptance gate và query parity |
| Restore thẳng trên source để “đỡ tốn máy” | Ghi đè state mới hợp lệ | Isolated restore rồi selective repair |
| Skip lỗi một chunk | Mất records âm thầm | Retry/quarantine có owner và evidence |
| Reset CDC offset về “latest” | Có thể mất updates | Resnapshot hoặc replay gap-free |
| Force promote replica cũ | Split-brain/data loss | Fencing/quorum protocol |
| Retry payment với ID mới | Duplicate charge | Provider idempotency và reconciliation |
| Tắt encryption để lấy backup | Rủi ro compliance/security | Break-glass audited key access |

## 78. Phân biệt readiness của dữ liệu và readiness của dịch vụ

Một timeline:

```text
Data files restored           10:10
Indexes rebuilt               10:35
App authz verified            10:45
CDC read models caught up     11:00
API latency SLO restored      11:05
Routing cutover completed     11:10
```

Nếu contract là “người dùng có thể đặt hàng lại”, thời điểm phục hồi không phải 10:10.

### Một completion matrix

| Trục | Trạng thái độc lập |
|---|---|
| Storage data completeness | PASS/FAIL/INCONCLUSIVE |
| Index/schema correctness | PASS/FAIL/INCONCLUSIVE |
| Tenant/security access | PASS/FAIL/INCONCLUSIVE |
| Application queries | PASS/FAIL/INCONCLUSIVE |
| Durability/RPO | PASS/FAIL/INCONCLUSIVE |
| Availability/RTO | PASS/FAIL/INCONCLUSIVE |
| Derived freshness | PASS/FAIL/INCONCLUSIVE |
| Business side-effect reconciliation | PASS/FAIL/INCONCLUSIVE |

Một dòng PASS không bù cho dòng FAIL của invariant tiền hoặc authorization.

## 79. Kiểm chứng tính đúng bằng một oracle đơn giản

Với fixture:

```text
Expected at backup:
  T01#O001 rev4 PAID
  T01#O002 rev2 NEW
  T01#O003 rev3 CANCELED
  T02#O004 rev1 PAID
  T01#O005 rev5 deleted
```

### Các câu hỏi

1. Có đúng 5 keys không?
2. Có thêm `T01#O006` sau restore archive không? Nếu có, target có còn thật sự cô lập?
3. O005 tombstone có được giữ không?
4. Source revision của O001 là 4, không phải 5?
5. Query theo tenant T01 có trả nhầm O004 của T02 không?
6. Amounts/Decimal/Date types có giữ đúng?
7. Index phục vụ query by customer có hiện diện?

### So với recovered live source

Sau source incident, có thể không đọc được live source để so. Bởi vậy fixture manifest/recovery boundary và checksum **phải tồn tại độc lập với source** trước khi bắt đầu drill.

### Real production

Một oracle tốt có thể là authoritative ledger/external transaction history, signed manifest hoặc consistent backup catalog. Nếu expected state không thể xác minh, kết luận phải là **INCONCLUSIVE**, không bịa để báo pass.

## 80. Metrics cần thu khi diễn tập

| Metric | Đơn vị | Ý nghĩa |
|---|---|---|
| `backup_duration_seconds` | s | Thời gian tạo backup |
| `backup_bytes` | bytes | Kích thước archive/chunks |
| `backup_integrity_verified` | boolean | Manifest/hash match |
| `restore_duration_seconds` | s | Thời gian DB restore |
| `restore_index_ready_seconds` | s | Thời gian index ready |
| `source_recovery_point_age_seconds` | s | Age của recovery boundary |
| `acknowledged_writes_unrecovered_total` | operations | RPO/data-loss evidence |
| `rebuild_records_read_total` | records | Work đã đọc |
| `rebuild_records_applied_total` | records | Sink đã confirmed |
| `rebuild_records_verified_total` | records | Đối soát thành công |
| `rebuild_retry_total` | attempts | Retry amplification |
| `rebuild_checkpoint_age_seconds` | s | Progress có đứng không |
| `cdc_oldest_unapplied_age_seconds` | s | Freshness lag |
| `projection_mismatch_total` | records | Correctness gap |
| `app_read_p99_seconds` | s | User latency |
| `availability_success_ratio` | fraction | Business operation success |

Các tên là đề xuất cho **instrumentation**, không phải metrics sẵn có trong MongoDB/Redis/Elasticsearch.

### Không gây metric cardinality explosion

Labels hợp lý: `environment,service,region,job_type,phase,error_class` với cardinality giới hạn.

Không gắn raw `orderId`, `customerId`, `email`, session tokens hay full exception messages vào mỗi metric series; dùng structured logs/traces được kiểm soát khi cần điều tra.

### No-data alert

Nếu exporter/worker biến mất, stale-rate metric có thể không còn series và dashboard nhìn “xanh”. Có heartbeat/no-data alert độc lập với data-plane logs.

## 81. Kết quả một drill có thể INCONCLUSIVE vì sao?

Ví dụ:

- Backup tool đã tạo file nhưng không có timestamp/recovery boundary rõ.
- Restore target không có index/schema mới và query bị khác.
- Không có tenant authorization như production để test leak.
- Source thay đổi trong lúc dump, không có consistent snapshot protocol.
- Không có business ACK history để tính mất dữ liệu.
- CDC log gap không được phát hiện.
- Fault injector không thật sự cô lập node/region.
- Dataset không đại diện cho size/cardinality/skew.
- Monitoring mất khi fault xảy ra.
- Không ghi được đầu ra của verifier.

**Inconclusive không phải FAIL của datastore**, nhưng cũng **không phải PASS của DR design**.

## 82. Mẫu báo cáo tích hợp hai nhánh

```text
EXPERIMENT ID: NOSQL-DR-589
OWNER: training-team
ENVIRONMENT: isolated lab
DATE: [actual]

BASELINE:
  source: nosql589_source.orders
  fixture count: 5
  source revision map: recorded
  backup boundary: before O001 rev5/O006

BRANCH A:
  backup tool/version: [actual]
  archive SHA-256: [actual]
  isolated target: nosql589_restored.orders
  document count: [observed]
  index ready: [observed]
  post-backup writes present?: [observed]
  restore duration: [measured]
  RPO evidence: [specific versions/IDs]
  verdict: PASS/FAIL/INCONCLUSIVE

BRANCH B:
  source boundary: [actual]
  target generation: [actual]
  snapshot records: [observed]
  replayed events: [observed]
  checkpoint: [actual durable position]
  missing/extra keys: [observed]
  tombstone/revision checks: [observed]
  source-to-visible lag: [measured]
  cutover eligible: YES/NO
  verdict: PASS/FAIL/INCONCLUSIVE

SAFETY:
  approved scope respected?: [verified]
  real PII used?: NO
  unauthorized network access?: [checked]

FOLLOW-UP:
  problem:
  severity:
  owner:
  remediation:
  retest criteria:
```

Không điền các ô `[observed]` bằng expected values mà chưa kiểm thực sự. Báo cáo minh bạch **sự khác nhau giữa mong đợi và điều đã quan sát**.

## 83. Các vai trò cần có trong một bài production-like drill

| Vai trò | Trách nhiệm |
|---|---|
| Drill owner/incident commander | Scope, approval, stop/continue |
| Database engineer | Source/recovery boundary, backup/restore protocol |
| Application owner | User journey và business invariants |
| Data pipeline owner | CDC/projection/checkpoint/replay |
| Security owner | IAM/KMS/PII/data residency |
| SRE/observability | SLO, timing, alerts, fault containment |
| Auditor/reviewer | Evidence integrity, PASS/FAIL rationale |

Một người có thể đảm nhiệm nhiều vai trò trong lab, nhưng production cần **trách nhiệm và quyền dừng rõ**.

## 84. Cleanup sau lab và vòng đời artifacts

Sau khi có report và không còn cần điều tra:

1. Đảm bảo không có lab client đang dùng source/target.
2. Xác minh backup/manifest/evidence đã lưu ở nơi được phép.
3. Dừng các **containers có đúng tên `nosql589-source` và `nosql589-target`**.
4. Nếu muốn dọn volumes/archive, chỉ thực hiện theo approved data retention, sau khi **xác nhận tuyệt đối chúng là fixture test** và không chứa dữ liệu khác.
5. Thu hồi lab credentials/tokens, hạn chế quyền tiếp tục sử dụng.
6. Không giữ dumps hoặc quarantine raw payload vô hạn “để phòng hờ”.

### Chỉ dừng containers

```powershell
docker stop nosql589-source
docker stop nosql589-target
```

Không hướng dẫn `docker volume prune` hay xóa hàng loạt vì có thể tác động dữ liệu Docker ngoài lab. Nếu cần xóa volume, người vận hành phải đối chiếu **đúng resource names, ownership và retention policy**.

## 85. Vòng học tập liên tục

Một game day thành công chưa bảo đảm DR mãi mãi:

- Schema/driver/tool version thay đổi.
- Backup policy/retention/KMS key rotation thay đổi.
- Dataset tăng 100 lần, restore time có thể vượt RTO.
- Một index mới thêm vào khiến rebuild lâu.
- CDC connector chuyển topology và mất log headroom.
- Team thay đổi runbook hoặc region deployment.

### Triggers cần diễn tập lại

1. Database major version upgrade.
2. Cross-region replication or DR architecture change.
3. New critical index/read model.
4. New compliance/data residency requirement.
5. Material traffic/data volume growth.
6. Incident phát hiện gap trong current runbook.

**Diễn tập là hoạt động xác minh định kỳ**, không chỉ một lần chạy và đóng ticket.

## 86. Case study A: restore thành công nhưng thiếu acknowledged writes

### Tình huống

```text
09:00 Backup at position C100.
09:10 ACKed booking B1002 at C108.
09:20 Source data lost.
09:50 Restore backup C100.
09:55 API can query restored database.
```

Nếu RPO yêu cầu không mất confirmed bookings, báo “restore PASS” không có nghĩa **DR PASS**. Booking B1002 không nằm trong C100 và không được replay; user có thể thấy booking biến mất dù đã nhận xác nhận.

### Phản ứng đúng

1. Tách **restore integrity** và **RPO violation**.
2. Kiểm outbox/payment/provider ledger cho B1002.
3. Xác định có log C101..C108 hay backup mới hơn hợp lệ không.
4. Reconcile confirmed effects theo runbook; không tái tạo payment mù.
5. Không chuyển traffic nếu business data safety gate chưa đạt.

### Bài học

Backup là một recovery mechanism; **số lượng bản backup và việc restore nhanh không tự xác nhận RPO**.

## 87. Case study B: rebuild search nhưng delete bị hồi sinh

### Tình huống

```text
Source O001 rev10 ACTIVE captured by snapshot worker.
CDC O001 rev11 DELETE applied to search.
Snapshot worker writes rev10 document after delete.
Search again returns O001.
```

### Root cause

Không có tombstone/version guard ở sink; một snapshot row cũ có thể thắng delete mới.

### Khắc phục

- Dùng authoritative source revision.
- Giữ delete marker đủ replay window.
- Nếu rebuild từ scratch, target generation mới và log barrier.
- Kiểm test “delete before late snapshot” và “duplicate delete”.
- Đối soát search result và source ở cùng boundary.

### Bài học

Một index có total count hợp lý nhưng chứa deleted record vẫn **sai nghiêm trọng**, đặc biệt với thông tin nhạy cảm.

## 88. Case study C: restore target đúng dữ liệu nhưng sai quyền

### Tình huống

Admin shell đọc được mọi order. Application login của tenant T01 cũng đọc được O004 thuộc T02 vì restore target thiếu authorization policy/index filter.

### Kết luận

Data restore có thể thành công về bytes/record count, nhưng **end-to-end recovery FAIL** vì cross-tenant data exposure.

### Hướng xử lý

- Block route, điều tra security incident.
- Khôi phục IAM/roles/row/tenant policies theo môi trường.
- Test adversarial cross-tenant requests.
- Ghi audit các reads trong affected interval.
- Không dùng “data integrity PASS” để miễn trừ security gate.

## 89. Case study D: CDC consumer mất source retention

### Tình huống

```text
Earliest available source event now: C150
Projection durable checkpoint: C120
Consumer restarts at C121 -> history missing
```

### Sai lầm

Đổi consumer offset sang `latest` rồi báo “caught up”. Events C121..C149 đã bị bỏ; projection có thể thiếu deletes/updates vĩnh viễn.

### Khắc phục

1. Dừng khai báo caught-up.
2. Kiểm khả năng lấy source historical snapshot/PITR khác.
3. Nếu không đủ, lấy **new consistent source snapshot + CDC boundary**.
4. Rebuild target generation mới.
5. Verify trước cutover.
6. Tăng retention/monitoring headroom dựa vào worst-case rebuild time.

## 90. Case study E: backup có nhưng thiếu KMS grant

### Tình huống

Backup đã copy sang region R2. Region R1 outage. Restore identity ở R2 không thể decrypt, dù archive tồn tại và checksum hợp lệ.

### Kết luận

**Recoverability FAIL**. Backup integrity không thay key accessibility/role/cross-region policy.

### Sửa

- Thiết kế standby identity/key policy và rotation.
- Verify backup decrypt trong isolated restore drill định kỳ.
- Break-glass chỉ theo policy, MFA/audit/time-limited credentials.
- Không mở public access, không tắt encryption.

### Bài học

Một file backup chỉ có ích khi **đúng người, đúng vùng, đúng phần mềm có thể khôi phục nó trong thời gian cần thiết**.

## 91. Ba mươi bài tập thực hành

### Bài 1 — Phân loại sự cố

Source MongoDB vẫn đúng nhưng Elasticsearch bị xóa index. Chọn restore source hay rebuild projection? Nêu điều kiện chứng minh projection thật sự rebuildable.

### Bài 2 — Replication và backup

Ba replicas cùng xóa nhầm order O123 và cập nhật thành công. Vì sao replica khỏe không có nghĩa có backup để undo?

### Bài 3 — Tính RTO

Incident detected 09:10, restore started 09:20, data loaded 09:45, indexes ready 10:00, application verified 10:05, route completed 10:12. Tính restore duration và end-to-end observed recovery time từ detection.

### Bài 4 — RPO thực tế

Backup C100, sau đó 40 acknowledged business writes C101..C140, chỉ replay được C101..C132. Những writes nào còn thiếu? Kết luận gì nếu RPO yêu cầu không mất confirmed transactions?

### Bài 5 — Backup boundary

Một logical dump bắt đầu 10:00, kết thúc 10:10 trong lúc source ghi. Vì sao không thể tự gọi recovery point “10:10” mà không có consistent snapshot/log protocol?

### Bài 6 — Archive integrity

SHA-256 archive khớp manifest nhưng manifest do attacker cùng quyền sửa. Hash có chứng minh provenance không? Đề xuất trust boundary/immutable metadata.

### Bài 7 — Isolated restore

Một người muốn dùng `mongorestore --drop` lên collection production vì thử ở staging đã chạy tốt. Hãy viết quy trình an toàn hơn và điều kiện bắt buộc trước khi có bất kỳ destructive step.

### Bài 8 — Tenant scope

Backup chứa T01 và T02; restore application chỉ nên cho T01 xem order thuộc T01. Thiết kế một negative authorization test.

### Bài 9 — Không có index

Restore đưa đủ 1 triệu records nhưng index theo customer bị mất. Hệ thống có coi là recovered không nếu p99 tăng từ 40 ms lên 10 giây? Cần kiểm chứng gì?

### Bài 10 — Logical vs physical

So sánh logical export, physical snapshot và managed PITR về data consistency, version compatibility, restoration cost và recovery point.

### Bài 11 — Source identity

Collection `orders` bị drop/recreate cùng tên. Vì sao CDC token cũ không mặc định hợp lệ? Cần metadata generation nào trong checkpoint?

### Bài 12 — Snapshot + CDC gap

Full scan O1 rev8 lúc 09:05, source update rev9 lúc 09:20, CDC bắt đầu lúc 09:41. Vì sao target thiếu rev9? Đề xuất consistent boundary protocol.

### Bài 13 — Out-of-order

CDC v12 được apply trước snapshot v10. Nếu snapshot writer upsert unconditional thì điều gì xảy ra? Viết rule theo revision.

### Bài 14 — Tombstone

O2 bị delete v3 rồi snapshot v2 đến muộn. Vì sao hard delete target không lưu version có thể hồi sinh O2?

### Bài 15 — Duplicate event

Event E101 cập nhật tuyệt đối `status=PAID,revision=5` được gửi hai lần. Event delta `balance += 100` được gửi hai lần. Cơ chế idempotency có khác nhau thế nào?

### Bài 16 — Source data change projection key

Order O1 chuyển customer C001→C009. Target projection key chứa customerId. Nếu chỉ upsert key mới, gì xảy ra? Nêu cách xóa key cũ có version guard.

### Bài 17 — Checkpoint crash window

Worker apply event E103 vào sink, crash trước lưu checkpoint E103. Sau restart đọc lại E103. Cần điều kiện gì để kết quả business không đổi?

### Bài 18 — Partial bulk

Batch A..E có kết quả OK,OK,FAIL,OK,WAIT. Mốc checkpoint contiguous được phép tiến tới đâu và vì sao không dựa vào HTTP 200 chung?

### Bài 19 — Worker fencing

W1 giữ epoch 7, W2 nhận epoch 8, W1 tỉnh lại. Chỉ dùng CAS cho checkpoint có chặn được W1 ghi stale data vào target không? Đề xuất bảo vệ thêm.

### Bài 20 — Token expired

Snapshot/scan token của source hết hạn ở 80% progress. Có thể reset token về null rồi tiếp tục ghi index không? Khi nào phải resnapshot?

### Bài 21 — Log retention

CDC retention 60 phút, rebuild baseline 70 phút. Nếu không có cách giữ log/start-position lâu hơn, rủi ro nào xuất hiện?

### Bài 22 — Throughput convergence

Events vào 5.000/s, sink xử lý 4.500/s. Sau 10 phút backlog tăng bao nhiêu nếu rate giữ nguyên? Có thể catch up không?

### Bài 23 — ETA

Còn 50 GiB dữ liệu, sink confirmed throughput 25 MiB/s. Tính ETA lý tưởng. Liệt kê năm lý do RTO thực tế có thể lâu hơn.

### Bài 24 — Quarantine

Một record source có amount không parse được. Có được skip và báo 100% verified không? Điều kiện nào cho phép terminal quarantine hợp lệ?

### Bài 25 — Search visibility

Bulk import trả thành công, nhưng Search query vẫn trả index cũ 15 giây. Phân biệt sink commit với query-visible freshness, thiết kế cutover gate.

### Bài 26 — Cache rebuild

Redis cache bị mất; app fallback vào DB khiến QPS tăng 8 lần. Đề xuất bounded warm-up, versioned entries và cách tránh stampede.

### Bài 27 — Backup restore vs projection parity

Restore source tới C115 dù trước outage source đã ACK C120. Projection rebuilt đúng đến C115. Có thể tuyên bố toàn bộ user data đã phục hồi không? Vì sao?

### Bài 28 — Data deletion/privacy

Một backup cũ chứa thông tin người dùng đã được xóa hợp lệ sau khi backup tạo. Nếu restore lại, phải xét những nghĩa vụ privacy/tombstone/retention nào?

### Bài 29 — DR failover

Restore standby region có data đúng nhưng không có KMS decrypt grant và app roles. Những phần nào thuộc hard gate? Đề xuất preflight drill.

### Bài 30 — Thiết kế tổng hợp

Thiết kế kế hoạch cho kiến trúc:

```text
Java Orders API (3 AZ)
    |
    v
MongoDB order authority
    |
    +-- Backup/PITR to separate domain
    |
    +-- Outbox/CDC -> Kafka -> Elasticsearch search
    |
    +-- Redis cache
```

Yêu cầu bài làm gồm:

- Owner/approval/scope/synthetic fixture.
- Source backup boundary, archive integrity, isolation và restore target.
- RPO/RTO definitions, acknowledged-write reconciliation.
- Snapshot + CDC boundary cho search rebuild không gap.
- Idempotency, tombstone, revision guard và per-partition checkpoint.
- Index/alias cutover, cache versioning, fallback.
- Authz/KMS/tenant isolation và deletion propagation.
- Fault matrix, progress/lag/ETA, PASS/FAIL/INCONCLUSIVE.
- Rollback/forward-fix, cleanup và report.

## 92. Checklist trước diễn tập backup/restore

1. **Source of truth** và những dữ liệu dẫn xuất đã được phân loại?
2. Mục tiêu diễn tập là node recovery, backup restore, PITR, rebuild hay DR failover?
3. Có run ID, approved scope và owner?
4. Test dùng synthetic data hoặc môi trường được phê duyệt?
5. Không có production credentials hoặc dữ liệu nhạy cảm ngoài phạm vi?
6. Có xác định RPO/RTO theo business workflows và acknowledged-write semantics?
7. Backup type, engine/version/tool version và topology được ghi lại?
8. Có consistent snapshot/recovery boundary, không chỉ backup start/end time?
9. Có source identity/cluster incarnation và namespace?
10. Backup manifest ghi size, checksum, encryption key reference và retention?
11. Có immutable/object version/permissions phù hợp?
12. Có standby identity đủ quyền đọc, decrypt, restore?
13. Có cách truy xuất logs/change history sau snapshot nếu RPO yêu cầu?
14. Có kiểm backup gồm documents, index/schema/config cần thiết?
15. Restore target tách biệt source, có đủ CPU/disk/I/O?
16. Có kế hoạch chặn lệnh destructive ngoài approved target?
17. Có baseline counts, keys, revisions và business invariants?
18. Có độc lập monitoring/audit/abort criteria?
19. Có kế hoạch rollback/forward-fix và cách cô lập traffic?
20. Có xác minh region/data residency và quyền IAM/KMS?

## 93. Checklist trong quá trình restore

1. Target identity đã được xác nhận lần cuối trước lệnh?
2. Archive hash có khớp manifest đáng tin?
3. Không có backup chunk bị thiếu/hỏng?
4. Công cụ restore có version tương thích?
5. Restore command exit status và logs đã ghi?
6. Có dùng đúng namespace mapping, không ghi đè source?
7. Cùng recovery boundary có được dùng cho các source entities liên quan?
8. Có xem transaction/log replay continuity và incomplete transactions?
9. Có phân biệt counts imported với counts verified?
10. Có kiểm key sets và field/revision canonical values?
11. TTL/tombstones/deletes có đúng theo recovery point?
12. Unique/index/validation/collation có khôi phục đúng?
13. Application identity/roles/tenant isolation đã được test?
14. Có đối soát ACKed writes xảy ra sau backup?
15. Nếu RPO chưa đạt, có chặn cutover?
16. Resource throttling, quota, disk headroom có được giám sát?
17. Có independent read probes từ app path, không chỉ admin shell?
18. Index build/caches/CDC có tình trạng rõ?
19. Mọi lỗi permanent/unknown outcome có owner và resolution?
20. Không đóng DR incident khi data chưa query-ready theo contract?

## 94. Checklist trước khi rebuild projection

1. Projection thực sự derived cho **từng field** chưa?
2. Source authority còn đúng, đầy đủ và sẵn sàng?
3. Có consistent snapshot/CDC boundary không gap?
4. Source version/incarnation và mapping version được pin?
5. Có thể lấy mọi partitions/ranges cần thiết?
6. Snapshot/CDC resume token còn hạn, có log retention headroom?
7. Có source revision/causal ordering per entity?
8. Event chứa full state hay delta? Idempotency strategy tương ứng?
9. Delete/TTL được biểu diễn và propagate thế nào?
10. Nếu projection key thay đổi, old-key removal có đủ info?
11. Target generation mới và immutable metadata được định danh?
12. Có index mapping/analyzer/ANN model version phù hợp?
13. Có bounded batches, retries, backpressure và concurrency?
14. Có per-item outcomes và quarantine policy?
15. Có per-range/partition checkpoint bền, CAS và owner epoch?
16. Có cách chống stale worker writes ở target?
17. Có kiểm corruption/missing source event trước khi rebuild?
18. Có khả năng đối soát target với source at same boundary?
19. Có sandbox/shadow reads để test query semantics?
20. Có cutover/rollback/forward-fix runbook?

## 95. Checklist xác nhận projection đủ điều kiện phục vụ

1. Snapshot export/import đã đầy đủ đến boundary?
2. CDC replay đủ đến cutover position, không có gaps?
3. Không còn unknown/pending outcomes quan trọng?
4. Mọi error quarantine đều được business chấp nhận rõ?
5. Source-to-target keys match không missing/extra?
6. Canonical field values/revisions bằng nhau theo schema mapping?
7. Tombstones/deletes không bị hồi sinh khi replay out of order?
8. TTL/expiry không bị kéo dài sai?
9. Tenant/customer/partition boundaries đúng?
10. Search refresh/PIT/query visibility đã được kiểm?
11. Full-text/geo/vector recall và filters đạt SLO?
12. App RYW/causal minimum revision path đạt yêu cầu?
13. Query parity/pagination/order/aggregation có evidence?
14. p95/p99/throughput đủ dưới load dự kiến?
15. Cache cold-start/fallback không phá source capacity?
16. Không có unexpected cross-tenant data exposure?
17. Cutover alias/routing dựa approved owner/epoch?
18. Old generation giữ trong rollback window đúng policy?
19. Có monitor CDC backlog, stale reads, mismatch sau cutover?
20. Mới đánh dấu `COMPLETED` khi **business acceptance criteria** đạt?

## 96. Các hiểu lầm thường gặp

| Hiểu lầm | Điều đúng hơn |
|---|---|
| “Ba replicas là ba backup” | Replication có thể lan truyền xóa nhầm/corruption |
| “File backup có tồn tại nên chắc restore được” | Cần verify integrity, tool compatibility, IAM/KMS/capacity |
| “Backup end timestamp là exact recovery point” | Cần documented snapshot/log boundary |
| “RPO bằng tuổi backup file” | RPO cần đối chiếu acknowledged writes có thể mất |
| “RTO bằng thời gian giải nén” | RTO service có indexes, authz, app queries, routing |
| “Mongodump lúc production đang ghi luôn nhất quán” | Tùy topology/options/snapshot protocol |
| “Copy file DB đang mở là physical backup” | Có thể không crash/transaction-consistent |
| “Restore vào cùng source dễ nhất” | Rủi ro overwrite state hợp lệ và phá forensic evidence |
| “Hash khớp là dữ liệu đúng nghiệp vụ” | Hash xác nhận bytes; vẫn cần key/value/invariant checks |
| “Count bằng nhau nghĩa datasets bằng nhau” | Có thể missing và extra IDs |
| “Admin shell đọc được là app phục hồi” | Còn IAM/tenant/index/routing |
| “Backup gồm mọi secrets/roles/indexes” | Phạm vi metadata tùy tool/provider; phải verify |
| “Mới nhất luôn là backup tốt nhất” | Backup mới có thể chứa corruption |
| “Có log thì cứ replay tới hiện tại” | Log cần continuous coverage, ordering, correct boundaries |
| “Search index là backup thay source” | Projection có thể thiếu fields/history và stale |
| “CDC lag=0 là target mới nhất” | Connector/source position/sink visibility có thể chưa đúng |
| “Snapshot xong mới bật CDC là ổn” | Có gap updates trong lúc scan |
| “UPSERT theo ID đủ chống mọi replay” | Stale version có thể overwrite; deletes có thể hồi sinh |
| “Bỏ qua delete làm projection nhỏ” | Có thể lộ dữ liệu cũ hoặc sai trạng thái |
| “Checkpoint khi đã đọc page là đủ” | Checkpoint phải sau sink durable outcome |
| “Network timeout nghĩa sink chưa ghi” | Có thể commit nhưng ACK mất |
| “Lease hết hạn nghĩa old worker chết” | Cần epoch/fencing/version guard |
| “Một bulk request là một transaction” | Nhiều APIs trả partial per-item success |
| “Import 100% nghĩa query-ready” | Có verify, refresh, indexes, ACL và app SLO |
| “Rebuild từ source luôn an toàn” | Nếu source đã corrupted/missing thì copy lỗi |
| “Restore projection xong mọi hậu quả cũ biến mất” | Side effects từ stale data cần reconcile |
| “Có backup ở region R2 là DR chắc chắn” | Có thể thiếu KMS grant, quota, identity |
| “Khi network nối lại là sự cố kết thúc” | Repair/rebalance/cache/CDC có thể kéo dài |
| “Một game day PASS là bảo đảm mãi” | Workload, config, versions và topology thay đổi |

## 97. Bảng đối chiếu hai nhánh ở cùng một trang

| Câu hỏi | Backup/restore source | Rebuild derived |
|---|---|---|
| Source of truth có còn đúng không? | Thường bị mất/sai hoặc cần quay về recovery point | Phải còn đúng hoặc có bản nguồn phục hồi tin cậy |
| Input | Backup + optional logs | Source snapshot + change history |
| Boundary | Recovery point | Snapshot/CDC checkpoint/cutover position |
| Output | Authoritative database state | Projection/index/cache/read model |
| Core correctness | Không mất/ghi sai required records, RPO | Bằng source at boundary, replay idempotent |
| Các lỗi đặc trưng | Archive hỏng, thiếu log, KMS, schema/index | Gaps, duplicate/out-of-order events, stale overwrite |
| Completion | Data/transaction/app restored and validated | Data/index freshness/query parity and routing ready |
| Rủi ro cutover | Mất writes mới, app trỏ sai source | Alias/routing, stale read, source-to-index lag |
| Có thể làm offline không? | Có, lab freeze writes | Có, dùng snapshot immutable |
| Online path cần gì? | Engine-supported consistent backup/PITR | Snapshot + CDC không gap, versioned sink |

### Câu hỏi phân nhánh nhanh

Nếu **nguồn còn đúng, chỉ index/cache sai**, ưu tiên sửa/rebuild projection để tránh rewind source đang khỏe.

Nếu **nguồn bị mất**, phục hồi authority trước; đừng đưa một projection vốn thiếu dữ liệu vào vai trò source of truth mà chưa chứng minh nó đầy đủ.

Nếu **nguồn bị corruption logic**, cần chọn good recovery point, selective repair và phân biệt valid post-boundary writes.

## 98. Kết luận

Diễn tập backup/restore và xây dựng lại dữ liệu dẫn xuất không phải hai thao tác thay thế nhau hoàn toàn. Chúng giải quyết **hai loại recovery boundary khác nhau** và phải được kiểm bằng bằng chứng khác nhau.

### Những nguyên tắc cần nhớ

1. **Xác định authority trước khi phục hồi.** Không lấy cache/search index làm nguồn mặc định cho order/payment ledger.
2. **Restore vào target cô lập.** Không ghi đè source đang phục vụ chỉ để thử archive.
3. **Ghi source/recovery point và version.** File backup mới không đồng nghĩa nhất quán hoặc đủ recent.
4. **Đo RPO theo acknowledged business effects và RTO theo dịch vụ thực.** Không chỉ đo lệnh CLI.
5. **Integrity, security và application readiness là những tiêu chí riêng.** File hash/record count không thể thay tenant/authz checks.
6. **Rebuild online cần snapshot + CDC không gap.** Đừng bắt đầu CDC “từ bây giờ” sau khi scan xong.
7. **Replay phải idempotent và version-aware.** Late snapshot, duplicate events và deletes không được làm dữ liệu quay lùi.
8. **Checkpoint sau durable sink effect.** Crash trước checkpoint có thể replay; đó là tình huống phải được thiết kế, không phải lỗi hiếm.
9. **Bảo vệ worker ownership và resource budgets.** Lease expiry không dừng old worker, write-heavy rebuild có thể làm source production chậm.
10. **Chỉ công bố phục hồi khi query và bất biến đúng.** Derived data có thể 100% imported nhưng vẫn stale/chưa refresh, còn source restore có thể đủ records nhưng chưa giữ RPO.

### Một câu hỏi cuối để đánh giá bài thực hành

> **“Nếu hệ thống hỏng ngay sau một write đã được ACK, chúng ta có nguồn/backup/log nào chứng minh trạng thái phải phục hồi, có thể khôi phục vào đâu mà không phá dữ liệu khác, và những phép đối soát nào xác nhận ứng dụng trở lại phục vụ đúng — kể cả các chỉ mục, cache và workflow phụ thuộc?”**

Khi có thể trả lời bằng **recovery boundary, manifest và integrity checks, RPO/RTO timeline, versioned replay, query parity, tenant/security validation và runbook cutover/rollback**, bạn đã biến “có backup” hoặc “có thể rebuild index” thành **khả năng phục hồi đã được diễn tập và kiểm chứng trong phạm vi cụ thể**.
