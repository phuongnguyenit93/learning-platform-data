# Di chuyển dữ liệu bằng xuất nhập, CDC hoặc ghi song song theo yêu cầu trong MongoDB

## 1. Bối cảnh: khi nào cần di chuyển dữ liệu?

Một ứng dụng đang lưu hàng chục triệu tài liệu trong MongoDB. Đội phát triển có thể cần:

- Chuyển từ MongoDB self-managed sang MongoDB Atlas.
- Thay đổi cấu trúc document và collection mà vẫn duy trì ứng dụng.
- Tách một hệ đa tenant thành nhiều database/cluster.
- Di chuyển dữ liệu sang công cụ phân tích, tìm kiếm hoặc kho lưu trữ khác.
- Thay đổi shard key hoặc mô hình phân vùng.
- Hợp nhất dữ liệu từ nhiều môi trường.
- Nâng kiến trúc từ một ứng dụng monolith sang các dịch vụ sở hữu dữ liệu riêng.
- Chuyển sang MongoDB cluster mới với cấu hình bảo mật, khu vực địa lý hay năng lực tính toán khác.

Những hoạt động này đều được gọi chung là **data migration**, nhưng yêu cầu khác nhau đáng kể.

Một hệ chỉ được phép dừng ghi trong một cửa sổ bảo trì có thể dùng **xuất/nhập dữ liệu** đơn giản. Hệ thống phải tiếp tục ghi trong thời gian chuyển hàng terabyte dữ liệu cần **initial copy kết hợp CDC**. Còn những hệ cần chuyển từng nhóm người dùng hoặc có logic chuyển đổi dữ liệu ở lớp ứng dụng có thể cân nhắc **ghi song song (dual-write)**, nhưng phải xử lý sự cố ghi một nơi thành công, nơi còn lại thất bại.

```text
                       SOURCE MongoDB
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
        Export/Import     CDC / oplog      Dual writes
             |                |                |
         File / dump      Change events     Application
             |                |                |
             +----------------+----------------+
                              |
                              v
                       TARGET datastore
                              |
                      Validate + cutover
```

**Điểm cốt lõi:** không có một công cụ nào vừa bảo đảm zero downtime, zero data loss, zero engineering effort, lại có thể rollback tức thì trong mọi trường hợp. Chọn chiến lược dựa trên mục tiêu nghiệp vụ và khả năng kiểm soát dữ liệu đang thay đổi.

---

## 2. Mục tiêu học tập

Hoàn thành bài học này, người học có thể:

1. Phân biệt logical export/import, backup/restore, CDC và dual-write.
2. Chọn chiến lược di chuyển theo downtime, dung lượng dữ liệu, RPO và RTO.
3. Hiểu vì sao một bản dump không luôn đại diện snapshot nhất quán trong khi writes tiếp diễn.
4. Dùng `mongodump`/`mongorestore`, `mongoexport`/`mongoimport` đúng mục đích.
5. Thiết kế full load và CDC catch-up không bỏ sót thay đổi trong giai đoạn backfill.
6. Hiểu Change Streams, resume token, oplog history window và sự kiện delete.
7. Xây dựng migration worker Java với upsert theo business key, batch và checkpoint.
8. Nhận diện tính không nguyên tử của ghi song song vào hai database độc lập.
9. Thiết kế transactional outbox, idempotency và đối soát.
10. Thực hiện cutover, kiểm tra dữ liệu và lập phương án rollback có điều kiện.
11. Xử lý các edge cases: TTL, unique index, sharding, transactions, schema versions và dữ liệu nhạy cảm.

---

## 3. Ba chiến lược chính

| Tiêu chí | Xuất/nhập | Full load + CDC | Ghi song song |
| --- | --- | --- | --- |
| Nguồn dữ liệu | Snapshot hoặc tập xuất | Snapshot/backfill và chuỗi thay đổi | Mỗi thao tác ghi của ứng dụng |
| Nhu cầu dừng ghi | Thường cần để bảo đảm nhất quán đơn giản | Có thể giảm thời gian dừng ghi tới cutover | Có thể chuyển theo từng phần nhưng cần đồng bộ |
| Độ phức tạp | Thấp đến vừa | Vừa đến cao | Cao khi có lỗi và nhiều loại writers |
| Dữ liệu lớn | Phụ thuộc công cụ/storage | Tốt khi có full load và oplog/CDC đủ dài | Không tự xử lý dữ liệu lịch sử |
| Xóa document | Thể hiện trong snapshot cuối | Phải xử lý delete events | Phải phát hành delete tới cả hai nơi |
| Recovery | Chạy lại dump/restore hoặc restore snapshot | Resume token + checkpoint | Retry queue/outbox/reconciliation |
| Nguy cơ chính | Dữ liệu thay đổi trong lúc xuất | Mất resume history, sai thứ tự, backfill race | Ghi một bên thành công, bên kia thất bại |
| Best fit | Offline/batch migration | Online migration khối lượng lớn | Canary migration khi ứng dụng kiểm soát writes |

**Không nhầm lẫn:** CDC không tự sao chép toàn bộ lịch sử nếu chỉ bắt đầu nghe events tại thời điểm hiện tại; dual-write cũng không tự đưa dữ liệu cũ sang hệ đích.

---

## 4. Phân loại yêu cầu trước khi chọn phương pháp

Một migration plan nên trả lời:

- **Nguồn** là một standalone server, replica set hay sharded cluster?
- **Đích** là MongoDB khác hay hệ thống khác như PostgreSQL, Elasticsearch, data lake?
- Kích thước dữ liệu, số lượng documents, indexes và tốc độ tăng?
- Dữ liệu cần chuyển **nguyên trạng** hay phải transform?
- Các collection có quan hệ nghiệp vụ cần nhất quán chéo collection không?
- Có các writes đồng thời không? Inserts, updates, deletes, transactions?
- Chấp nhận dừng ghi trong bao lâu?
- Mất tối đa bao nhiêu dữ liệu là chấp nhận được?
- Có thể đảo chiều writes sau cutover không?
- Có cần hai nơi chạy song song để canary?
- Có pháp lý/retention/encryption/key management requirements?
- Ai là chủ sở hữu duy nhất của từng record trong giai đoạn chuyển?

### 4.1. RPO và RTO

- **RPO (Recovery Point Objective):** mức dữ liệu tối đa có thể mất nếu phải phục hồi/cutover.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để phục hồi dịch vụ hoặc hoàn tất chuyển đổi sau một sự cố.

Ví dụ:

```text
Business accepts:
  Planned write downtime: <= 10 phút
  Potential data loss:     0 acknowledged business writes
  Cutover rollback window: 1 giờ
  Dataset size:            500 GiB
  Write rate:              2,000 operations/second
```

Với yêu cầu này, chỉ chạy `mongoexport` trong nhiều giờ rồi `mongoimport` khi ứng dụng tiếp tục ghi sẽ **không đủ**. Cần cơ chế bắt kịp changes, kiểm soát writers và cutover chặt chẽ.

### 4.2. Không hứa “RPO = 0” từ tên công cụ

Một CDC pipeline có thể bị lag, mất oplog history hoặc gặp lỗi sink. Một dual-write pipeline có thể mất ghi ở đích thứ hai. RPO thực phải suy ra từ durable write concern, checkpoints, khả năng replay, cutoff và kiểm chứng tại cutover.

---

# PHẦN I — DI CHUYỂN BẰNG XUẤT / NHẬP

## 5. Những công cụ dễ bị nhầm lẫn

MongoDB có hai nhóm công cụ thường gặp:

| Công cụ | Định dạng | Mục đích |
| --- | --- | --- |
| `mongodump` | BSON dump + metadata | Logical dump để phục hồi dữ liệu MongoDB |
| `mongorestore` | BSON dump | Phục hồi từ `mongodump` |
| `mongoexport` | JSON hoặc CSV | Xuất dữ liệu để trao đổi với ứng dụng/hệ thống khác |
| `mongoimport` | JSON/CSV/TSV theo options | Nhập dữ liệu đã serialize sang MongoDB |

`mongodump` **không** tạo physical filesystem snapshot. `mongoexport` **không** phải full-fidelity backup tương đương `mongodump`.

### 5.1. Khi nào dùng mongodump/mongorestore?

- Chuyển một database giữa các triển khai MongoDB tương thích.
- Tạo logical dump có metadata về indexes/collections theo cách công cụ hỗ trợ.
- Restore tập dữ liệu vào môi trường test hoặc staging.
- Di chuyển trong maintenance window khi không có concurrent writes hoặc có phương án consistency rõ.

### 5.2. Khi nào dùng mongoexport/mongoimport?

- Trao đổi dữ liệu với hệ khác qua CSV hoặc JSON.
- Chuyển một tập fields đã lọc.
- Làm ETL với schema transformation.
- Nhập dữ liệu mẫu, dữ liệu do external system cung cấp.

### 5.3. Khi nào cần snapshot/backup platform?

Nếu yêu cầu point-in-time consistency, cluster sharded nhiều node, PITR hoặc RPO chặt, hãy cân nhắc snapshot/backup được hỗ trợ bởi nền tảng. Đừng mặc định một CSV export bảo toàn toàn bộ metadata, indexes, roles và trạng thái nhất quán chéo collection.

---

## 6. Ví dụ mongodump và mongorestore

Các lệnh dưới đây dành cho **môi trường test hoặc migration được phê duyệt**. Không ghi username/password trực tiếp vào lịch sử terminal.

Xuất một database:

```bash
mongodump \
  --uri="$SOURCE_MONGODB_URI" \
  --db="sales" \
  --archive="./sales.archive.gz" \
  --gzip
```

Nhập lại tại đích:

```bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --archive="./sales.archive.gz" \
  --gzip \
  --nsInclude="sales.*"
```

### 6.1. Restore có thể xung đột dữ liệu có sẵn

Nếu target collection đã có documents cùng `_id`, restore có thể báo duplicate-key hoặc có hành vi không như kỳ vọng. **Không dùng `--drop` vô thức** trên production; option đó có thể xóa collection đích trước restore.

### 6.2. Namespace mapping

Khi đổi tên database/collection, công cụ hỗ trợ namespace mapping, ví dụ:

```bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --archive="./sales.archive.gz" \
  --gzip \
  --nsFrom="sales.*" \
  --nsTo="sales_v2.*"
```

Kiểm chứng patterns và khả năng hỗ trợ theo MongoDB Database Tools version trước khi dùng; đừng chỉ nhìn log “restore completed” mà bỏ qua collection names đã tạo.

### 6.3. Phiên bản công cụ

Database Tools có version riêng so với MongoDB Server. Chọn phiên bản công cụ được công bố tương thích với source/target, đặc biệt khi dữ liệu có new BSON types hoặc collection features.

---

## 7. Nhất quán khi dump đang có writes

Một dump có thể kéo dài hàng giờ. Trong lúc đó:

```text
10:00:00  dump starts
10:15:00  customer name updated
10:30:00  order created
11:00:00  old order deleted
11:30:00  dump ends
```

Không có cơ chế consistency bổ sung, dữ liệu các collection có thể phản ánh **những thời điểm khác nhau**, tạo ra lệch giữa `orders` và `customers`.

### 7.1. `mongodump --oplog`

`mongodump --oplog` trên nguồn replica set tương ứng có thể ghi lại oplog entries trong thời gian dump để phục hồi điểm nhất quán hơn khi replay với `mongorestore --oplogReplay`, theo các giới hạn của MongoDB Database Tools.

Tuy nhiên:

- Không áp `--oplog` như một giải pháp tùy ý cho toàn sharded cluster.
- Một số lựa chọn dump namespace/collection, tình huống DDL, topology hoặc transactions có hạn chế cụ thể.
- Oplog window phải đủ lớn; nếu oplog bị ghi đè trong lúc dump, dump có thể thất bại hoặc không bảo toàn yêu cầu.
- Nếu source có feature mới không được target hỗ trợ, oplog replay cũng không tự giải quyết compatibility.

**Phải đọc đúng tài liệu công cụ trước khi sử dụng `--oplog`/`--oplogReplay`.** Nó không thay một giải pháp online migration có catch-up/rollback.

### 7.2. Cách đơn giản nhất để có điểm dữ liệu tĩnh

Khi business cho phép:

1. Ngừng hoặc đưa tất cả writers vào read-only/maintenance.
2. Xác nhận không còn background writes.
3. Dump hoặc snapshot theo quy trình.
4. Restore sang đích.
5. Kiểm tra dữ liệu, indexes và business constraints.
6. Chuyển application sang đích.
7. Mở lại writes.

Phương án này có logic dễ kiểm chứng hơn, nhưng downtime tăng theo dung lượng và throughput.

---

## 8. Export JSON hoặc CSV

Xuất JSON:

```bash
mongoexport \
  --uri="$SOURCE_MONGODB_URI" \
  --db="sales" \
  --collection="orders" \
  --type=json \
  --out="./orders.json"
```

Xuất CSV chỉ với vài fields:

```bash
mongoexport \
  --uri="$SOURCE_MONGODB_URI" \
  --db="sales" \
  --collection="orders" \
  --type=csv \
  --fields="_id,tenantId,status,totalMinor" \
  --out="./orders.csv"
```

Nhập JSON vào collection đích:

```bash
mongoimport \
  --uri="$TARGET_MONGODB_URI" \
  --db="sales_v2" \
  --collection="orders" \
  --file="./orders.json" \
  --type=json
```

Với file JSON dạng **một document mỗi dòng**, không tự thêm `--jsonArray`; nếu file chứa một JSON array thật thì chỉ định option tương ứng theo Database Tools.

### 8.1. CSV không bảo toàn BSON type hoàn toàn

CSV chứa các giá trị text. `ObjectId`, `Date`, `Decimal128`, `BinData`, nested objects và arrays không thể tự động bảo toàn kiểu trong mọi trường hợp. `mongoimport` có tùy chọn xử lý field types, nhưng phải mapping rõ.

### 8.2. JSON cũng cần xét Extended JSON

MongoDB Extended JSON thể hiện BSON types thông qua các object đặc biệt như `$oid`, `$date`, `$numberDecimal`. Nếu ứng dụng deserialize thành plain JSON rồi serialize lại không cẩn thận, có thể mất type/precision.

### 8.3. Export không bảo toàn mọi metadata

Indexes, collection options, validators, collation, views, sharding configuration, users/roles và cluster settings không tự xuất hiện đầy đủ trong `mongoexport` JSON/CSV. Cần quản lý riêng bằng migration scripts/IaC hoặc công cụ backup phù hợp.

---

## 9. Import mode và idempotency

Khi nhập vào collection đang có dữ liệu, cần chọn semantics:

- Insert mới.
- Upsert theo `_id` hoặc business key.
- Merge field.
- Replace toàn document.
- Reject duplicates.

Ví dụ `mongoimport` có `--mode=upsert` và `--upsertFields` theo phiên bản công cụ:

```bash
mongoimport \
  --uri="$TARGET_MONGODB_URI" \
  --db="sales_v2" \
  --collection="orders" \
  --file="./orders.json" \
  --type=json \
  --mode=upsert \
  --upsertFields="_id"
```

### 9.1. Không nhầm upsert với merge

Nếu import “upsert” nhưng replacement/merge semantics không đúng, có thể xóa fields đích hoặc giữ lại fields cũ không mong muốn. Xác định rõ mục tiêu **replace** hay **merge** trên một dataset test.

### 9.2. Nếu không có `_id` ổn định

Phải thiết kế business key, ví dụ `(tenantId, externalOrderId)`, và tạo unique index phù hợp. Không tạo `_id` mới ngẫu nhiên mỗi lần retry nếu migration cần idempotent.

### 9.3. Thử import hai lần

Một test quan trọng là chạy cùng file hai lần:

- Document count không tăng bất thường.
- Không có duplicate nghiệp vụ.
- Values vẫn đúng.
- Nếu là replace, không mất những fields được bảo vệ.
- Error handling được báo đúng.

---

## 10. Kiểm tra dữ liệu sau export/import

Ít nhất cần:

1. Danh sách collections và namespace mappings.
2. Counts theo collection/tenant/partition.
3. Tổng/giá trị aggregate quan trọng.
4. Kiểm tra `_id` và business keys.
5. Type fidelity cho dates, Decimal128, ObjectId.
6. Indexes, validators, collation, unique constraints.
7. TTL/index settings và retention.
8. Một số sample documents kiểm tra toàn bộ fields.
9. Permission và read/write smoke tests.
10. Dữ liệu cập nhật sau mốc dump có cần bổ sung không?

### 10.1. Count bằng nhau chưa đủ

```text
Source:
  order A: total=100
  order B: total=200

Target:
  order A: total=200
  order B: total=100
```

Cả hai có `count=2`, nhưng dữ liệu khác. Cần canonical comparison theo key và business fields.

### 10.2. Checksum phải tính trên biểu diễn ổn định

Nếu so sánh hashes, hãy chuẩn hóa thứ tự fields/arrays theo semantics và BSON types. Hash raw JSON khác thứ tự fields có thể cho false mismatch; convert Decimal128 sang `double` có thể làm mất chính xác.

---

# PHẦN II — CHANGE DATA CAPTURE (CDC)

## 11. CDC là gì?

**Change Data Capture (CDC)** ghi nhận thay đổi ở source để áp vào target trong khi source tiếp tục phục vụ ghi.

Ví dụ:

```text
SOURCE MongoDB
   |
   +-- initial scan/backfill ---> TARGET MongoDB
   |
   +-- Change Streams events --> Durable CDC buffer
                                        |
                                        v
                                  Apply to TARGET
                                        |
                                        v
                                Catch-up + cutover
```

CDC thường gồm hai giai đoạn tách biệt:

1. **Initial snapshot/backfill:** sao chép những documents đã tồn tại.
2. **Change replay:** xử lý inserts, updates, replaces, deletes diễn ra kể từ mốc bắt CDC, rồi tiếp tục theo dõi đến khi bắt kịp.

**Chỉ chạy Change Streams từ hôm nay không tạo lại được lịch sử collection trong 5 năm.**

---

## 12. MongoDB Change Streams và oplog

Trong replica set/sharded cluster, MongoDB cung cấp **Change Streams** để theo dõi các thay đổi được hỗ trợ:

- `insert`.
- `update`.
- `replace`.
- `delete`.
- Một số thay đổi collection/database như rename, drop, invalidate.
- Transaction-related change events theo semantics của server.
- Những event types mới phụ thuộc version và option.

Change Streams dựa trên lịch sử thay đổi của oplog, có resume token để ứng dụng có thể tiếp tục từ một vị trí được hỗ trợ.

### 12.1. Không tự đọc oplog tùy tiện nếu có Change Streams

Oplog có chi tiết nội bộ có thể thay đổi theo version và khó chuyển hóa chính xác thành các business events. Change Streams là API được thiết kế cho application-level consumption.

### 12.2. Điều kiện topology

Change Streams cần MongoDB deployment hỗ trợ oplog/change streams, thường là **replica set hoặc sharded cluster**. Một standalone `mongod` thông thường không đáp ứng yêu cầu.

### 12.3. Không tự suy ra mọi thay đổi đều là một full document

Một `update` event có thể chứa `updateDescription`, không tự mang toàn bộ document. Tùy `fullDocument` option và event timing, full document có thể được lookup hoặc không tồn tại.

---

## 13. Resume token là gì?

Mỗi change event có một `_id` event token dùng cho resume, thường được Java Driver cung cấp dưới dạng `BsonDocument`.

Ví dụ minh họa cấu trúc:

```javascript
{
  _id: {
    _data: "8269..."
  },
  operationType: "insert",
  ns: {
    db: "sales",
    coll: "orders"
  },
  documentKey: {
    _id: ObjectId("691800000000000000000001")
  },
  fullDocument: {
    _id: ObjectId("691800000000000000000001"),
    status: "PAID"
  }
}
```

`_id` của **event** là resume token. `documentKey._id` là khóa của **document bị thay đổi**. Hai cái khác mục đích.

### 13.1. Lưu token nguyên dạng BSON

Không tự “tách `_data` rồi cắt chuỗi” hoặc convert token sang JSON mất type. Lưu nó đúng kiểu BSON được hỗ trợ cùng metadata của stream/pipeline.

### 13.2. Lúc nào cập nhật checkpoint?

**Sau khi đã xử lý event vào target và xác nhận thành công**, rồi mới lưu token. Nếu lưu token trước, crash có thể khiến event bị bỏ sót.

### 13.3. Khoảng hở giữa apply và checkpoint

Nếu apply thành công nhưng checkpoint thất bại, sau restart event sẽ bị replay. Vì vậy **sink writes phải idempotent** hoặc có cơ chế transaction/outbox phù hợp.

---

## 14. Oplog window: giới hạn của khả năng resume

Oplog là một lịch sử có dung lượng/hạn lưu hữu hạn. Khi writes tiếp tục, records cũ có thể bị ghi đè hoặc bị loại khỏi cửa sổ lịch sử.

```text
13:00    Consumer saves token T
13:10    Consumer crashes
14:00    Heavy write traffic
20:00    Consumer resumes T

If token T no longer within available history:
  resume may fail -> rebootstrap required
```

### 14.1. Điều cần đo

- Source oplog window.
- Throughput thay đổi theo giờ cao điểm.
- Lag lớn nhất của CDC.
- Thời gian initial scan.
- Chiến lược lưu durable event buffer.
- Khoảng thời gian có thể gián đoạn do deployment/restart.
- Tốc độ target áp changes.

### 14.2. Nếu initial scan lâu hơn oplog window

Một CDC pipeline có thể mất events trước khi scan hoàn tất nếu không đọc/persist stream kịp thời. Bắt stream trước snapshot không đủ nếu consumer ngừng poll và resume token đã expired.

**Phải đảm bảo các events sau mốc bắt đầu được persist/replay trong khả năng lưu trữ và retention**, hoặc có snapshot/backup+migration tool chuyên dụng bảo đảm history.

---

## 15. Backfill + CDC: thứ tự quan trọng hơn tốc độ

Một chiến lược tưởng hợp lý nhưng sai:

```text
1. Dump dữ liệu cũ.
2. Đợi vài giờ.
3. Bắt đầu Change Stream.
4. Replay changes.
```

Những writes trong khoảng giữa bước 1 và bước 3 có thể bị **bỏ sót**.

### 15.1. Mẫu an toàn hơn về mặt khái niệm

```text
T0: establish CDC starting point
    |
    v
Persist changes from T0 into durable log/queue
    |
    +-------------------------------+
    |                               |
    v                               v
Scan and copy baseline          Keep capturing CDC
    |                               |
    v                               |
Baseline copy completes <-----------+
    |
    v
Replay all changes since T0 in valid order
    |
    v
Reach low CDC lag and stable target state
    |
    v
Controlled write pause / drain / cutover
```

### 15.2. Không chạy backfill và CDC apply mù quáng

Nếu hai luồng cùng cập nhật một document:

```text
Backfill reads old version v1
CDC receives update v2
CDC applies v2
Backfill later writes v1 -> target regresses!
```

Giải pháp có thể là:

- **Capture trước, backfill rồi replay changes** sau baseline theo thứ tự.
- Hoặc dùng version/sequence-aware conditional upserts để không ghi đè phiên bản mới.
- Hoặc dùng migration service chuyên dụng bảo đảm sequencing.
- Hoặc tạm ngừng writes để có snapshot/cutover đơn giản.

Mọi phương án phải giải quyết ordering, deletes và snapshot boundary. Không được chỉ vì “hai pipeline đang chạy” mà suy ra target nhất quán.

---

## 16. Sự kiện update và fullDocument

Change Streams có thể trả:

- `operationType: "update"`.
- `updateDescription` với fields đã thay đổi/đã loại.
- `documentKey`.
- `fullDocument` nếu option hỗ trợ và lookup được.

Java thường dùng:

```java
source.watch()
    .fullDocument(FullDocument.UPDATE_LOOKUP)
```

### 16.1. UPDATE_LOOKUP không phải snapshot lịch sử tuyệt đối

`UPDATE_LOOKUP` có thể lookup trạng thái **hiện tại** của document khi event được xử lý, không nhất thiết chính xác after-image tại từng mốc update nếu đã có writes khác theo sau.

Ví dụ:

```text
T1 status = PENDING
T2 update status = PAID
T3 update status = REFUNDED
T4 CDC processes event from T2 using updateLookup
```

Full document tại T4 có thể là `REFUNDED`, không phải `PAID`.

### 16.2. Full document có thể null

Nếu document đã bị xóa trước lookup hoặc do những điều kiện khác, `fullDocument` có thể không có. Worker không được dùng null làm tín hiệu “xóa target ngay” mà không xét event type và thứ tự.

### 16.3. Khi cần pre/post images

Các phiên bản MongoDB hỗ trợ **Change Stream pre- and post-images** khi bật cấu hình collection phù hợp, có chính sách retention và version restrictions. Chọn API/metadata theo release nếu migration cần chính xác before/after-image.

### 16.4. Không dùng CDC để “sửa lịch sử giao dịch” không kiểm soát

Nếu target cần replay từng trạng thái để kích hoạt business side effects, việc dùng updateLookup thay vì event payload bất biến có thể dẫn đến sai semantics. Hãy phân biệt state replication và event sourcing.

---

## 17. CDC phải xử lý deletes

Một pipeline chỉ upsert `insert` và `update` sẽ để lại documents đã xóa ở source.

Ví dụ:

```text
Source:
  insert order A
  update order A
  delete order A

Target without delete handler:
  order A still exists -> stale record
```

### 17.1. Cách áp delete

Dùng `documentKey`, thường chứa `_id` và có thể shard key fields, để xác định record đích.

```java
BsonDocument key = change.getDocumentKey();
target.deleteOne(key);
```

Đoạn code này đúng về ý tưởng khi target dùng cùng key/schema phù hợp. Nếu migration **đổi `_id`** hoặc gộp documents, cần một mapping bền vững từ source key sang target key.

### 17.2. Không mất delete event lúc lag

Trong một hệ thay đổi rất nhanh, document có thể được insert và delete trước khi backfill đọc tới. CDC replay phải có đủ delete events để target hội tụ về trạng thái cuối.

### 17.3. Soft-delete khác hard-delete

Nếu source dùng `deletedAt` hoặc `active:false`, đó có thể là **update**, không phải `operationType: delete`. Worker phải transform theo business rules, không đơn thuần map update event thành hard delete.

---

## 18. CDC và các thao tác DDL

Ngoài insert/update/delete, migration có thể gặp:

- Collection rename/drop.
- Database drop.
- Index create/drop.
- Validator change.
- Collation change.
- Shard metadata changes.
- Change Stream invalidate event.

Các thay đổi về **schema/metadata** không tự được sao chép đầy đủ chỉ vì đang nghe document changes.

### 18.1. Quy định trong migration window

Có thể cần **freeze DDL** hoặc có một schema migration pipeline riêng:

- Index definitions được deploy từ IaC/migration scripts.
- Không đổi tên collection giữa lúc backfill.
- Không bật TTL quá sớm làm target tự xóa records.
- Không tự tạo sharding options khác source khi chưa tính keys.
- Không sửa validators giữa chừng mà không cập nhật transform code.

### 18.2. Resume sau invalidate

Theo API Change Streams, `resumeAfter` không được dùng để resume sau `invalidate` event; `startAfter` dành cho một số trường hợp sau invalidate theo điều kiện server. Không giả định một resume token duy nhất luôn hợp lệ qua drop/rename.

---

## 19. Ví dụ Java: đọc Change Streams

Đoạn dưới đây là **mẫu CDC đơn giản** khi cả hai collection sử dụng `_id` tương thích. Nó minh họa lifecycle và idempotent apply, chưa phải production connector đầy đủ.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.OperationType;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.Filters;

import org.bson.BsonDocument;
import org.bson.Document;

public final class SimpleCdcReplication {

    public static void run(
            MongoCollection<Document> source,
            MongoCollection<Document> target
    ) {
        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 source.watch()
                     .fullDocument(FullDocument.UPDATE_LOOKUP)
                     .cursor()) {

            while (cursor.hasNext()) {
                ChangeStreamDocument<Document> event =
                    cursor.next();

                OperationType type =
                    event.getOperationType();

                if (type == OperationType.INSERT
                        || type == OperationType.REPLACE
                        || type == OperationType.UPDATE) {

                    Document full =
                        event.getFullDocument();

                    if (full == null) {
                        // Không bỏ qua âm thầm.
                        throw new IllegalStateException(
                            "Missing fullDocument for " + type
                        );
                    }

                    target.replaceOne(
                        Filters.eq("_id", full.get("_id")),
                        full,
                        new ReplaceOptions().upsert(true)
                    );

                } else if (type == OperationType.DELETE) {
                    BsonDocument key =
                        event.getDocumentKey();

                    if (key == null) {
                        throw new IllegalStateException(
                            "DELETE event without document key"
                        );
                    }
                    target.deleteOne(key);

                } else {
                    // DDL/invalidate và event types khác cần
                    // policy riêng, không coi là success.
                    throw new IllegalStateException(
                        "Unsupported CDC type: " + type
                    );
                }

                // Production: ghi resume token bền vững SAU
                // target apply thành công; không chỉ log token.
            }
        }
    }
}
```

### 19.1. Hạn chế của ví dụ

- Không có checkpoint store.
- Không có retry/backoff.
- Không có transform schema.
- Không giải quyết ordering khi nhiều workers.
- Không có pre/post-image semantics.
- Không có logic init snapshot/backfill.
- Không có handling đúng cho collection invalidate/rename.
- Không xử lý rollback/cutover.
- Không có progress tracking.

Vì thế đây là **ví dụ học API**, không phải một công cụ CDC hoàn chỉnh.

---

## 20. Java: resumeAfter checkpoint

Khi đã lưu đúng resume token dưới dạng `BsonDocument`:

```java
import org.bson.BsonDocument;

BsonDocument savedToken =
    checkpointStore.loadResumeToken();

var iterable = source.watch()
    .fullDocument(FullDocument.UPDATE_LOOKUP);

if (savedToken != null) {
    iterable.resumeAfter(savedToken);
}

try (var cursor = iterable.cursor()) {
    while (cursor.hasNext()) {
        var event = cursor.next();

        applyToDestination(event);

        // Chỉ sau khi đích xác nhận thành công.
        checkpointStore.saveResumeToken(
            event.getResumeToken()
        );
    }
}
```

`checkpointStore` và `applyToDestination` là interfaces/logic do hệ thống cung cấp, không phải API có sẵn của MongoDB Driver.

### 20.1. Token phải bền vững

Không chỉ giữ trong Java heap:

```java
BsonDocument lastToken;
```

vì process crash sẽ mất token. Dùng một durable store được backup, có ownership/lease rõ nếu nhiều CDC consumers.

### 20.2. Checkpoint sau apply dẫn đến at-least-once

Nếu apply thành công rồi process crash trước checkpoint, event được replay sau restart. Destination operation phải idempotent.

### 20.3. Nếu checkpoint store và target cùng database

Có thể cân nhắc transaction để cập nhật target và token trong cùng atomic boundary khi deployment/driver hỗ trợ và workload phù hợp. Nếu khác clusters, **không có một MongoDB transaction đơn lẻ bao trùm cả hai clusters**.

---

## 21. Idempotent apply với replace/upsert

Với state replication giữa hai MongoDB collections cùng `_id`:

```java
target.replaceOne(
    Filters.eq("_id", doc.get("_id")),
    transformedDoc,
    new ReplaceOptions().upsert(true)
);
```

Chạy lại cùng event có thể giữ trạng thái đích không đổi **nếu**:

- Transformation deterministic.
- Không có writes mới hơn bị ghi đè bởi event cũ.
- Không có concurrent writers ở target.
- `_id` mapping ổn định.
- Không có external side effects.
- Event ordering được bảo vệ.

### 21.1. Idempotency không thay ordering

Có hai events:

```text
E1: order status=PAID
E2: order status=REFUNDED
```

Nếu worker áp E2 rồi E1, `replaceOne` vẫn “idempotent khi lặp E1” nhưng kết quả cuối **sai**.

Giải pháp:

- Một ordered consumer per key/partition.
- Hoặc version/sequence field và conditional write.
- Hoặc migration connector bảo đảm ordering.
- Hoặc replay tuần tự khi throughput cho phép.

### 21.2. Version-aware conditional update

Một pattern tùy schema:

```javascript
db.targetOrders.updateOne(
  {
    _id: "O100",
    appliedVersion: { $lt: 42 }
  },
  {
    $set: {
      status: "REFUNDED",
      appliedVersion: 42
    }
  }
);
```

Lưu ý: upsert với filter chứa version và `_id` có thể bị duplicate key khi document hiện có không match. Một production implementation phải xử lý trường hợp đó an toàn và dùng version **được định nghĩa đáng tin cậy**, không dùng `updatedAt` của nhiều máy với clock skew như total order không điều kiện.

---

## 22. Từ full copy đến CDC catch-up: vấn đề thứ tự

Một mô hình tối thiểu:

```text
STAGE 1: CAPTURE
  Start CDC at point T0
  Write every change to durable log
  Watch oplog retention and consumer lag

STAGE 2: BACKFILL
  Scan source documents
  Transform and write to target
  Persist per-range progress

STAGE 3: REPLAY
  Read stored events since T0
  Apply in supported order, including deletes
  Catch up to current source

STAGE 4: CUTOVER
  Temporarily stop/drain source writes
  Reach final CDC marker
  Verify target
  Switch writes/read traffic

STAGE 5: MONITOR
  Stop old writes, monitor and reconcile
```

### 22.1. Vì sao bắt CDC trước full scan?

Để không bỏ lỡ thay đổi xảy ra ngay sau khi backfill bắt đầu.

### 22.2. Vì sao cần durable buffer?

Để source tiếp tục ghi trong khi backfill kéo dài nhiều giờ mà change history không bị mất khi consumer/process gặp sự cố.

### 22.3. Vì sao cần barrier ở cutover?

Phải biết những writes cuối cùng đã được apply, không chỉ nhìn thấy “CDC lag khoảng 0” ở một dashboard. Một controlled marker/handoff và write drain giúp tạo ranh giới có thể xác minh.

---

## 23. Chọn cách đánh dấu mốc đồng bộ cuối

Các hệ thống có thể sử dụng:

- Source write freeze rồi xác nhận không còn in-flight writers.
- Một marker event được ghi **sau** khi tất cả writes trước đó được xác nhận theo policy.
- Resume token/high-water watermark tương ứng.
- Phương án CDC connector có cutover checkpoints được hỗ trợ.
- Đối soát theo partitions sau khi catch-up.

### 23.1. Chỉ timestamp hệ điều hành là chưa đủ

Nếu application clock của nhiều hosts lệch nhau, `updatedAt <= now` không đảm bảo tất cả writes trước cutover đã được copy.

### 23.2. Marker chỉ có nghĩa nếu nằm đúng thứ tự

Với nhiều source partitions/shards, một marker của một collection không luôn là barrier toàn cluster. Thiết kế marker phải phù hợp thứ tự và boundary mà CDC service thực sự bảo đảm.

### 23.3. Đừng tắt source writes rồi bật target writes quá sớm

Nếu còn change events chưa apply hoặc target index chưa ready, writes mới trên target có thể bị ghi đè bởi replay cũ. Cutover plan phải đảm bảo **ownership và event replay order**.

---

## 24. CDC và transactional consistency giữa collections

Một nghiệp vụ có thể ghi:

```text
Transaction:
  insert orders
  decrease inventory
  insert payment record
```

Nếu migration áp events **tách rời và không giữ transaction boundary**, target có thể tạm thời thấy order mà chưa thấy inventory update.

### 24.1. Khi nào điều này chấp nhận được?

Nếu target chỉ dùng cho analytics eventual consistency, có thể chấp nhận khoảng trễ giữa collections.

### 24.2. Khi nào không?

Nếu target đang phục vụ giao dịch tồn kho/thanh toán đòi hỏi invariant xuyên collection, cần:

- Replay theo transaction boundaries khi connector có khả năng.
- Hoặc khóa chuyển đổi/điểm nhất quán.
- Hoặc migration hoàn toàn theo snapshot có bảo đảm.
- Hoặc thiết kế application không cho đọc target trước khi consistency barrier đạt.

### 24.3. Không suy ra mọi CDC event độc lập có commit atomic

MongoDB transaction đảm bảo atomicity ở nguồn theo điều kiện hỗ trợ, nhưng pipeline tới đích cần cơ chế tương ứng mới giữ được invariant đó.

---

## 25. CDC với MongoDB Kafka Connector hoặc dịch vụ migration

Không phải mọi team cần tự viết consumer Java.

Một số lựa chọn:

- MongoDB Kafka Source Connector để đưa Change Streams vào Kafka.
- Kafka Connect Sink tương ứng cho đích phù hợp.
- Managed CDC/ETL services.
- MongoDB native migration tooling phù hợp release, ví dụ `mongosync` cho một số luồng cluster-to-cluster được hỗ trợ.
- Tự triển khai Java consumer khi có nghiệp vụ chuyển đổi chuyên biệt.

### 25.1. Đánh giá connector

- Source/target versions được hỗ trợ?
- Replica set/sharded topology?
- Có initial copy không?
- Có resume/checkpoint recovery không?
- Có quản lý deletes, updates, DDL, transactions không?
- Có transform schema và map `_id` không?
- Có khả năng detect oplog history lost?
- Có dashboard lag/retries không?
- Có cutover barrier và reverse sync không?
- Có exactly-once guarantee hay chỉ at-least-once?

### 25.2. Không tự gán “exactly once” cho Kafka hoặc connector

End-to-end exactly-once cần ranh giới transaction, offset commit và sink semantics cụ thể. Nhiều hệ thực tế dùng **at-least-once delivery + idempotent apply**.

### 25.3. `mongosync` không thay mọi trường hợp

`mongosync` có mục đích, license/feature support, restrictions, FCV/version/topology requirements và bước commit/cutover riêng theo bản đang dùng. Không tự coi nó hỗ trợ mọi kiến trúc, mọi đổi schema hoặc dual-write rollback.

---

# PHẦN III — GHI SONG SONG (DUAL-WRITE)

## 26. Dual-write là gì?

Trong giai đoạn migration, application ghi cùng một thay đổi vào cả nguồn và đích:

```text
                  APPLICATION
                        |
              +---------+---------+
              |                   |
              v                   v
        SOURCE MongoDB       TARGET MongoDB
              |                   |
          primary write       secondary write
```

Ví dụ khi tạo order:

```text
1. Write order to old database.
2. Write equivalent order to new database.
3. Return HTTP response.
```

Điểm hấp dẫn: target nhận các thay đổi mới mà không cần đọc oplog. Nhưng đây là **hai thao tác độc lập**, không tự thành một transaction chung.

### 26.1. Những câu hỏi phải trả lời

- Nếu source success, target failure thì HTTP trả gì?
- Nếu source failure, target success thì rollback target ra sao?
- Nếu timeout và không rõ kết quả ghi thì retry thế nào?
- Nếu writes đến target đảo thứ tự?
- Nếu user sửa cùng record trong lúc retry?
- Nếu một client/service cũ vẫn chỉ ghi nguồn?
- Nếu background jobs không đi qua dual-write code?
- Nếu target có unique index/validation khác nguồn?

---

## 27. Bốn trạng thái kết quả của dual-write

| Ghi nguồn | Ghi đích | Hệ quả |
| --- | --- | --- |
| Success | Success | Cả hai nhận thay đổi |
| Success | Failure | Target thiếu dữ liệu |
| Failure | Success | Target có dữ liệu không có nguồn |
| Failure | Failure | Không nơi nào nhận, có thể retry |
| Unknown due to timeout | Unknown | Cần đọc/đối soát theo operation ID |

### 27.1. Không có transaction xuyên hai cluster độc lập

Một MongoDB transaction chỉ có phạm vi deployment theo topology hỗ trợ. Không thể đơn giản `startTransaction()` trên cluster A rồi kỳ vọng nó atomically commit một write ở cluster B độc lập.

### 27.2. Trả 500 không tự undo write

Nếu source insert thành công rồi target timeout, API trả lỗi có thể khiến client retry. Sau retry, `_id` ở source trùng; target có thể đã nhận hoặc chưa nhận write. Cần idempotency, không chỉ catch exception.

---

## 28. Naive dual-write và rủi ro

```java
public void createOrder(
        MongoCollection<Document> oldOrders,
        MongoCollection<Document> newOrders,
        Document order
) {
    oldOrders.insertOne(order);
    newOrders.insertOne(order);
}
```

**Không nên dùng nguyên mẫu này trong production** vì:

- Target thất bại để lại divergence.
- Không có queue/retry.
- `_id` có thể được thêm/mutate vào `Document` từ lần insert đầu.
- Không xử lý partial timeout.
- Không có ordering/version.
- Không có audit trail và reconciliation.
- Không xử lý delete/update.
- Một request retry có thể duplicate.

Nếu bắt buộc dual-write, cần thiết kế chủ động **một source of truth** và khả năng replay.

---

## 29. Mẫu an toàn hơn: source-of-truth + outbox

Ý tưởng:

```text
Application request
       |
       v
BEGIN transaction on SOURCE
       |
       +--> Update business document
       |
       +--> Insert durable outbox event
       |
       v
COMMIT SOURCE
       |
       v
Outbox worker reads event
       |
       v
Apply idempotently to TARGET
       |
       v
Mark event processed / checkpoint
```

### 29.1. Lợi ích

- Business write và outbox event có thể commit cùng transaction trong **một** MongoDB deployment phù hợp.
- Nếu target tạm thời unavailable, outbox vẫn còn để retry.
- Application không cần giả vờ rằng hai clusters commit atomically.
- Có thể quan sát backlog và retry.
- Cùng một event ID giúp deduplication.

### 29.2. Đánh đổi

- Target eventual consistency, không đồng bộ tuyệt đối ngay sau mọi request.
- Phải vận hành worker.
- Cần retention/outbox cleanup.
- Phải kiểm soát retries/order.
- Business service cần quản lý “target chưa bắt kịp” khi đọc.

### 29.3. Khi nào outbox tốt hơn direct dual-write?

Khi cần bảo đảm không mất yêu cầu đồng bộ vào target do lỗi tạm thời, và có thể chấp nhận **độ trễ nhỏ, có giám sát**.

---

## 30. Ví dụ outbox document

```javascript
{
  _id: "evt-2026-10001",
  aggregateType: "ORDER",
  aggregateId: "O10001",
  operation: "ORDER_UPSERTED",
  version: NumberLong("42"),
  payload: {
    _id: "O10001",
    tenantId: "T100",
    status: "PAID",
    totalMinor: NumberLong("199000")
  },
  state: "PENDING",
  attempts: 0,
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

### 30.1. Payload là snapshot hay patch?

Có hai cách:

- **Snapshot event:** chứa trạng thái mới đầy đủ của document, dễ `replaceOne` nhưng cần kiểm soát version/order.
- **Patch event:** chứa thay đổi tương đối, có thể tiết kiệm bytes nhưng khó idempotent nếu dùng cộng/trừ không kiểm soát.

Ví dụ patch `$inc` rất nguy hiểm khi event bị replay: mỗi lần có thể cộng thêm một lần. Snapshot + version gating thường dễ làm idempotent hơn đối với state replication.

### 30.2. Giữ event ID ổn định

Khi retry cùng nghiệp vụ, không tạo event ID mới tùy tiện nếu điều đó dẫn tới double-processing. Idempotency policy phải rõ từ HTTP request tới outbox và target.

---

## 31. Java: transaction ghi order và outbox

Ví dụ giả định MongoDB replica set/sharded deployment hỗ trợ transactions, hai collections `orders` và `outbox` ở cùng source deployment:

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.TransactionBody;
import com.mongodb.client.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.ReadPreference;

import org.bson.Document;

public final class OrderOutboxWriter {

    public static void create(
            MongoClient client,
            MongoCollection<Document> orders,
            MongoCollection<Document> outbox,
            Document order,
            Document event
    ) {
        TransactionOptions options =
            TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(
                () -> {
                    orders.insertOne(session, order);
                    outbox.insertOne(session, event);
                    return null;
                },
                options
            );
        }
    }
}
```

### 31.1. Lưu ý với retry trong `withTransaction`

Driver có thể retry callback theo error labels và transaction semantics. Callback **không được gọi external API hoặc tạo side effect không idempotent**. Sinh `order`/`event` IDs trước khi gọi hoặc theo policy ổn định để retries không sinh business operations mới.

### 31.2. Không đặt target write trong callback

Nếu `targetOrders.insertOne(...)` kết nối **cluster khác**, nó không thuộc transaction source. Driver retry callback có thể làm target nhận duplicate hoặc state lỗi.

### 31.3. Worker xử lý riêng

Một worker lấy outbox events với lease/claim, apply target, rồi đánh dấu `PROCESSED` sau ack. Cần crash recovery và idempotency.

---

## 32. Direct dual-write có thể được chấp nhận khi nào?

Trong những hệ có yêu cầu đơn giản, direct dual-write có thể dùng **nếu**:

- Một bên được xác định là source of truth.
- Target write thất bại được ghi vào durable retry queue.
- Mọi operations có idempotent keys.
- Có version/ordering.
- Có reconciliation.
- Có khả năng tạm dừng chuyển reads sang target nếu target lag.
- Các writers đều đi qua cùng một pathway.
- Có failure injection tests.

Không chấp nhận tình huống “target lỗi thì ghi log rồi quên” mà vẫn tuyên bố zero data loss.

### 32.1. Ghi song song không bảo đảm cùng thứ tự

Hai HTTP requests A/B cùng sửa một order. Source có thể áp A trước B, nhưng target nhận B trước A do network delays. Bắt buộc có conflict/version policy nếu target state phụ thuộc thứ tự.

### 32.2. Last-write-wins không miễn phí

Dùng `updatedAt` do application cung cấp làm last-write-wins có thể sai khi clocks lệch. Ưu tiên version monotonic được cập nhật theo một source of truth, hoặc một ordered per-key stream.

---

## 33. Dual-read để canary trước khi chuyển traffic

Một chiến lược có ích:

```text
Production request
       |
       v
Read SOURCE -> response cho user
       |
       +--> Shadow read TARGET (async)
                    |
                    v
           Compare normalized result
                    |
                    v
             Metrics / diff logs
```

### 33.1. Shadow read khác dual-write

Shadow read kiểm tra target trả kết quả có tương đương source không. Nó không sửa dữ liệu target, không bảo đảm catch-up.

### 33.2. Những thứ cần so sánh

- Document hiện diện/không hiện diện.
- Field values sau transformation.
- Decimal128 và timezone.
- Array order nếu nghiệp vụ quan trọng.
- Quy tắc soft-delete và TTL.
- Query pagination/sort.
- Aggregation total.
- Index/collation behavior.
- p95/p99 latency.

### 33.3. Không log dữ liệu nhạy cảm thô

Khi phát hiện diff, log document key, rule ID, field names và hashes đã được canonicalize, tránh đưa PII/payment fields nguyên dạng vào log.

---

## 34. Tạo phiên bản dữ liệu để bảo vệ thứ tự

Một record với `version`:

```javascript
{
  _id: "O100",
  version: NumberLong("42"),
  status: "PAID"
}
```

Mọi update ở source tăng `version` theo logic atomically phù hợp.

CDC/dual-write events:

```text
E41: O100 version 41, PENDING
E42: O100 version 42, PAID
E43: O100 version 43, REFUNDED
```

Target chỉ chấp nhận thay đổi **mới hơn phiên bản đang lưu**.

### 34.1. Đây là một protocol nghiệp vụ

MongoDB không tự tạo field `version` monotonic cho tất cả documents. Ứng dụng phải bảo đảm version thật sự tăng dưới concurrency.

### 34.2. Không được quên deletes

Nếu delete event chỉ xóa document, một stale upsert event cũ có thể làm record **sống lại** khi tới sau.

Có thể dùng **tombstone** hoặc trạng thái deleted kèm version:

```javascript
{
  _id: "O100",
  version: NumberLong("44"),
  deleted: true
}
```

Sau khi migration/cutover hội tụ và an toàn, mới cleanup tombstones theo policy. Không xóa tombstone quá sớm nếu còn khả năng replay events cũ.

---

# PHẦN IV — QUY TRÌNH MIGRATION TOÀN DIỆN

## 35. Các giai đoạn đề xuất

```text
DISCOVER
    |
    v
PREPARE source/target + backup
    |
    v
INITIAL COPY / BACKFILL
    |
    v
CDC OR DUAL-WRITE CATCH-UP
    |
    v
RECONCILE
    |
    v
SHADOW READ / CANARY
    |
    v
CUTOVER (single writer authority)
    |
    v
MONITOR & ROLLBACK WINDOW
    |
    v
DECOMMISSION source (after approval)
```

Từng giai đoạn có mục tiêu riêng, không được dùng “copy script chạy xong” làm định nghĩa duy nhất của thành công.

---

## 36. Pha 1 — Discovery và inventory

Thu thập:

| Nhóm | Câu hỏi |
| --- | --- |
| Topology | Standalone/replica set/sharded? FCV? |
| Volume | Documents, average/max size, storage/index sizes |
| Write patterns | Inserts/updates/deletes, TPS, peak load |
| Data shape | BSON types, arrays, references, GridFS |
| Constraints | Unique/partial/TTL, validators, collation |
| Partition | Shard keys, tenant ownership, zones |
| Transactions | Multi-document/cross-collection invariants |
| Operations | Backup, PITR, KMS, auditing, monitoring |
| Consumers | Java services, jobs, BI, CDC, Change Streams |
| Retention | TTL, legal hold, data residency |
| Performance | Read/write p95/p99, indexes, disk throughput |

### 36.1. Mọi writers phải được tìm ra

Không chỉ API chính. Còn có:

- Scheduled jobs.
- Admin scripts.
- Batch loaders.
- Import pipelines.
- Mobile clients ghi trực tiếp nếu có.
- Background retry workers.
- Change Streams processors ghi kết quả.
- Data repair tasks.

Nếu một writer không được chuyển sang CDC hoặc dual-write pathway, target có thể thiếu thay đổi.

---

## 37. Pha 2 — Chuẩn bị target

Trước khi backfill:

1. Chọn server version/FCV tương thích với dữ liệu và công cụ.
2. Tạo namespaces theo mapping.
3. Thiết kế indexes, collation và validators.
4. Quyết định thời điểm bật unique/TTL index.
5. Bảo đảm đủ disk/RAM/IOPS/throughput.
6. Thiết lập TLS, access control và encryption.
7. Tạo monitoring/alerts.
8. Chạy smoke CRUD trên collection test.
9. Kiểm tra hỗ trợ transactions/change streams nếu cần.
10. Lập kế hoạch backups trước cutover.

### 37.1. Unique index có thể chặn dirty data

Nếu source có dữ liệu không thỏa unique key đích, target index build hoặc writes sẽ thất bại. Cần profiling/dedup/migration policy trước khi import.

### 37.2. TTL có thể xóa tài liệu backfill quá sớm

Nếu source đang lưu lịch sử đã hết hạn logic nhưng chưa cleanup, tạo TTL index ngay trên target có thể khiến documents biến mất trong lúc đối soát counts.

Cần xác định:

- Target có phải giữ y nguyên snapshot trước cutover?
- Có cho phép exclude expired docs không?
- Khi nào bật TTL?
- Có cần copy TTL configuration nhưng chưa enable deletion trước validation?

### 37.3. Shard key ảnh hưởng upsert

Khi target là sharded collection, upsert/update/delete filters phải tuân thủ quy tắc shard routing và index uniqueness theo phiên bản. Không chỉ dùng `_id` nếu target sharding schema/uniqueness requirements khác.

---

## 38. Pha 3 — Backfill theo batches, không giữ toàn bộ RAM

Với Java Sync Driver, một cách điển hình:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.WriteModel;
import com.mongodb.client.model.ReplaceOneModel;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.Document;
import java.util.ArrayList;
import java.util.List;

public final class MongoBackfill {

    public static long copy(
            MongoCollection<Document> source,
            MongoCollection<Document> target
    ) {
        final int BATCH = 500;
        long count = 0;
        List<WriteModel<Document>> writes =
            new ArrayList<>(BATCH);

        try (MongoCursor<Document> cursor =
                 source.find()
                     .sort(Sorts.ascending("_id"))
                     .batchSize(BATCH)
                     .cursor()) {

            while (cursor.hasNext()) {
                Document original = cursor.next();
                Document migrated = transform(original);

                writes.add(
                    new ReplaceOneModel<>(
                        Filters.eq("_id", migrated.get("_id")),
                        migrated,
                        new ReplaceOptions().upsert(true)
                    )
                );

                if (writes.size() >= BATCH) {
                    target.bulkWrite(writes);
                    count += writes.size();
                    writes.clear();
                }
            }

            if (!writes.isEmpty()) {
                target.bulkWrite(writes);
                count += writes.size();
                writes.clear();
            }
        }

        return count;
    }

    private static Document transform(Document source) {
        Document result = new Document(source);
        result.put("schemaVersion", 2);
        return result;
    }
}
```

### 38.1. Ví dụ chưa phải migration production hoàn chỉnh

Nó chưa có CDC catch-up, checkpoint, retries, concurrency, conflict management, backfill snapshot boundary hay rollback. Đây là một **batch copy nguyên tắc**, không cam kết consistent online migration.

### 38.2. `bulkWrite` có thể thành công một phần

Nếu batch có duplicate-key, schema validation error hoặc network timeout, một số documents có thể đã ghi trước khi exception. Không mặc định cả batch rollback. Cần idempotency và checkpoint dựa vào acknowledged results.

### 38.3. Không giữ một cursor hàng giờ nếu dễ gián đoạn

Với dữ liệu rất lớn, chia keyset ranges theo `_id`, tenant hoặc partition với checkpoint bền vững để có thể resume mà không bắt đầu từ đầu.

---

## 39. Backfill có checkpoint theo `_id`

Ý tưởng:

```text
Page size = 1000
Checkpoint = last fully applied _id

Read 1000 documents where _id > checkpoint
Transform + bulk upsert
Confirm destination writes
Persist checkpoint
Repeat
```

Java query:

```java
Bson filter = lastId == null
    ? new Document()
    : Filters.gt("_id", lastId);

List<Document> page = source.find(filter)
    .sort(Sorts.ascending("_id"))
    .limit(1000)
    .into(new ArrayList<>());
```

Ở đây `into(List)` được giới hạn bởi `limit(1000)`, phù hợp với bounded page.

### 39.1. Không checkpoint trước khi bulk thành công

```text
WRONG:
  store lastId
  -> target bulkWrite fails
  -> restart skips missing docs
```

### 39.2. Replay của page phải idempotent

```text
RIGHT:
  apply target
  -> persist checkpoint
  -> if checkpoint persist fails, retry same page
```

### 39.3. Với schema transformation và `_id` đổi

Không thể resume chỉ bằng `_id` đích. Phải lưu **source key**, target mapping và idempotency protocol ổn định.

---

## 40. Những bất biến cần giữ khi transform

Một migration từ:

```javascript
{
  _id: "O100",
  amount: 19.99,
  currency: "USD"
}
```

sang:

```javascript
{
  _id: "O100",
  totalMinor: NumberLong("1999"),
  currency: "USD",
  schemaVersion: 2
}
```

phải xác định:

- Rounding policy.
- Precision/Decimal128 conversion.
- Handling null/missing.
- Default fields.
- Timezone.
- Boolean/string migrations.
- Nested arrays/maps.
- Referential integrity.
- Validation rules.
- Search index metadata.
- Privacy masking.

### 40.1. Không chuyển tiền bằng double tùy tiện

Nếu source dùng Decimal128, hãy dùng `BigDecimal` theo business rounding policy; không tự `(long)(double * 100)` nếu có thể gây mất precision.

### 40.2. Mapping phải có version

Ghi lại transformation version để có thể phân tích:

```text
source schema v1
  -> transform v2.3
  -> target schema v2
```

Nếu deploy code transform mới giữa backfill, cùng source record có thể được convert khác nhau. Cần freeze transform version hoặc reprocess partitions với quy tắc rõ.

---

## 41. Pha 4 — CDC catch-up và lag

Sau backfill, target có thể sau source một lượng events. Theo dõi:

```text
Source event rate:       2,000 changes/s
Destination apply rate:  3,000 changes/s
Backlog:                600,000 events

Net drain speed:         ~1,000 events/s
Estimated drain:         ~10 minutes
```

Đây là mô hình gần đúng nếu tốc độ ổn định, không phải ETA đảm bảo.

### 41.1. Metrics cần đo

- Events captured per second.
- Events applied per second.
- Last durable resume token.
- CDC backlog size/age.
- Oldest unprocessed event age.
- Source oplog window.
- Retry/error rate.
- Apply conflicts.
- Target write latency.
- Dead-letter/quarantine counts.
- Delete/update/insert event counts.
- Per-partition lag nếu xử lý song song.

### 41.2. Lag = 0 không tự chứng minh target đúng

Có thể consumer bỏ qua unsupported event hoặc transform sai. Vì vậy phải có data reconciliation ngoài chỉ số lag.

---

## 42. Pha 5 — Reconciliation

Đối soát nhiều cấp độ:

### Cấp 1: inventory

- Collection tồn tại.
- Indexes và options.
- Validators/collation.
- Sharding/TTL settings.
- Data residency/permissions.

### Cấp 2: số lượng

- Tổng document count.
- Count theo tenant.
- Count theo thời gian.
- Count theo status/category.
- Deleted/tombstone counts.

### Cấp 3: business aggregates

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      totalMinor: { $sum: "$totalMinor" }
    }
  }
]);
```

### Cấp 4: sample và hash

- So document theo source key/target key mapping.
- Canonicalize fields theo transform.
- Kiểm tra money/date/ObjectId fidelity.
- Hash từng partition hoặc từng record.
- Đánh dấu mismatches và retry/rebuild có kiểm soát.

### Cấp 5: ứng dụng

- Critical read/write workflows.
- Transactions/unique constraints.
- Search indexes.
- Pagination/sort.
- Change Streams/CDC consumers.
- Access control.

### 42.1. Chỉ so sánh dữ liệu ở cùng logical cut

Nếu source tiếp tục ghi, count source lúc 13:00 và target lúc 13:05 có thể khác dù CDC hoạt động đúng. Reconciliation phải gắn với watermark hoặc kiểm soát writers để so dữ liệu tại cùng mốc.

---

## 43. Pha 6 — Shadow reads và canary

Trong giai đoạn này:

```text
User request
   |
   v
SOURCE read -> user response
   |
   +-- TARGET shadow read
             |
             v
       Compare under same filter
```

Sau khi diff rate gần mức chấp nhận:

- Chuyển một nhóm internal users.
- Chuyển một tenant/canary cohort.
- Giữ metric alerting.
- Không cho hai bên cùng tự do ghi bản ghi có cùng ownership mà không có conflict policy.

### 43.1. Nếu target eventual lag

Một shadow read target ngay sau write source có thể thấy stale state. So sánh chỉ có ý nghĩa khi đã xác nhận event đến target hoặc chấp nhận một lag tolerance định nghĩa trước.

### 43.2. Performance cũng cần test

Một target có count đúng nhưng thiếu index/collation phù hợp có thể làm API p99 tăng mạnh. Đánh giá latency, resource capacity, TTL và query plans.

---

## 44. Pha 7 — Cutover có kiểm soát

Một runbook ví dụ:

1. Thông báo maintenance/cutover window.
2. Dừng schema changes/index builds không cần thiết.
3. Ngừng hoặc drain nguồn writes theo application policy.
4. Chờ in-flight transactions hoàn tất.
5. Xác lập final source checkpoint/watermark.
6. Chờ CDC apply qua final watermark.
7. Xác nhận không còn event gaps và DLQ chưa xử lý.
8. Chạy reconciliation trên những partitions quan trọng.
9. Kiểm tra target indexes, validators và backup readiness.
10. Chuyển **writer authority** duy nhất sang target.
11. Chuyển reads/API traffic sang target.
12. Smoke tests cho critical workflows.
13. Theo dõi p95/p99/errors/replication/CDC.
14. Bảo toàn source read-only trong rollback window theo policy.

### 44.1. Cutover nên “một source of truth”

Không để hai application versions cùng ghi source và target theo hướng khác nhau mà không có conflict resolution.

### 44.2. Nếu phải giữ một cửa sổ mixed traffic

Dùng routing theo tenant/cohort ổn định:

```text
tenant T1 -> source owns writes
tenant T2 -> target owns writes
```

và đánh dấu ownership trong control plane. Đây là phương án phức tạp, cần kiểm thử chuyển ownership, retries và read consistency.

---

## 45. Rollback sau cutover khó hơn tưởng tượng

Trước cutover:

```text
SOURCE authoritative
TARGET follower
```

Sau cutover:

```text
TARGET authoritative
SOURCE no longer receiving writes
```

Nếu target đã nhận writes mới, source cũ **không còn đồng bộ**. Chỉ đổi connection string về source sẽ làm mất những writes sau cutover.

### 45.1. Các lựa chọn rollback

- Có reverse CDC từ target về source được kiểm chứng.
- Có dual-write theo hướng mới với idempotency/version.
- Tạm dừng target writes và reconcile ngược rồi mới đổi routing.
- Khôi phục backup/PITR với business-approved data loss/replay.
- Forward-fix target nếu rollback không an toàn.

### 45.2. Quy định rollback boundary

Một runbook phải nói rõ **điểm nào còn rollback đơn giản**, điểm nào đã “point of no return” và cần reverse sync hoặc forward-fix.

### 45.3. Ngoài database còn side effects

Payments, emails, Kafka events, cache invalidation và webhooks không tự rollback theo database. Cần reconciliation ở mức business, không chỉ dữ liệu MongoDB.

---

# PHẦN V — CÁC RỦI RO CHUYÊN BIỆT

## 46. Unique index và dữ liệu duplicate

Nếu target có unique index mà source không có:

```javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { unique: true }
);
```

thì backfill có thể thất bại vì duplicates ở nguồn. Tình huống này cần:

1. Phát hiện conflicts trước migration.
2. Quy định xử lý theo business: merge, reject, quarantine.
3. Ghi mapping/decision audit.
4. Không xóa dữ liệu tự động để index build pass.
5. Kiểm thử concurrent writers trong cutover.

### 46.1. Không tạo unique index sau khi target đã nhận duplicates rồi hy vọng server tự sửa

MongoDB unique index build có thể thất bại trên dữ liệu trùng. Hãy giải quyết dữ liệu hoặc thay schema đúng quy trình.

---

## 47. TTL và retention trong migration

TTL cleanup diễn ra bất đồng bộ. Một document đã hết hạn logic vẫn có thể chưa bị xóa ở source, trong khi target TTL monitor có thể xóa nhanh hơn sau import.

Hậu quả:

- Counts source/target khác.
- Reconciliation báo “missing target” dù do TTL.
- Backfill lưu lại record đã được TTL xóa sau đó ở source.
- Unique key có thể còn bị chiếm ở source nhưng đã rảnh ở target.

### 47.1. Chọn chính sách

- Chuyển cả expired docs hay chỉ live docs?
- Có tạm tắt TTL ở target trong backfill không?
- Có cần giữ record vì legal hold không?
- Cần so sánh dữ liệu tại mốc thời gian nào?
- CDC có nhận delete events từ TTL ở source không?
- Sau cutover, khi nào mở TTL tại target?

Không coi TTL là chính sách xóa chính xác từng giây hoặc bảo đảm count luôn bằng nhau.

---

## 48. Sharded clusters và routing

Khi nguồn/đích là sharded cluster:

- Migration có thể quét nhiều shards.
- Change Streams ở cấp cluster có behavior, resume tokens và ordering do `mongos` điều phối.
- Unique index phải tuân thủ shard key restrictions.
- Upsert/delete filter cần target shard routing phù hợp.
- Balancer/resharding có thể tác động performance.
- Config server metadata và target sharding configuration cần deploy đúng.
- Không tự dùng `mongodump --oplog` như cách lấy một snapshot nhất quán toàn cluster.

### 48.1. Tránh hot shard

Nếu mọi dữ liệu đang chuyển vào một giá trị shard key, target có thể bão hòa dù tổng tài nguyên cluster rất lớn.

### 48.2. Cross-shard transactions

Nếu business relies on cross-shard transaction semantics, một pipeline update từng collection độc lập không bảo toàn invariant tại mọi thời điểm. Cần kiểm soát thời điểm target được đọc/ghi.

---

## 49. Driver và BSON compatibility

Những vấn đề chuyển đổi dễ bị bỏ sót:

| Kiểu | Rủi ro |
| --- | --- |
| `ObjectId` | Convert thành string và mất join/key semantics |
| `Decimal128` | Convert thành `double`, mất precision |
| BSON Date | Timezone/epoch milliseconds |
| Int32 vs Int64 | Overflow hoặc type mismatch |
| Binary/BinData | Encode sai subtype |
| Arrays | Thay đổi thứ tự ngoài ý muốn |
| Nested documents | Null/missing khác nhau |
| DBRef/references | Target key mapping không đúng |
| UUID | Binary representation/subtype |
| Encrypted fields | Không có KMS/CSFLE keys |
| Time-series | Bucket/retention/schema behavior |
| Collation | Query/sort/unique khác |
| Text/search indexes | Cần rebuild ngoài dữ liệu document |

### 49.1. Test chuyển đổi nguyên vẹn

Tạo fixtures gồm null/missing, dữ liệu Unicode, Decimal128 biên, arrays dài, trường optional và các Date ở ranh giới timezone. So sánh ở mức BSON/business rules, không chỉ JSON string.

---

## 50. Change Streams và query transformation

Nếu target schema khác source, một event update kiểu:

```javascript
{
  $set: { "address.city": "Da Nang" }
}
```

có thể không map trực tiếp sang target đã tách collection `addresses`.

Cần xây dựng một transformation protocol:

- Xác định target records bị ảnh hưởng.
- Chỉ định source key → target keys.
- Áp theo thứ tự.
- Duy trì version/concurrency controls.
- Xử lý delete/move.
- Có khả năng rebuild từ source.
- Có quarantine cho unknown schema versions.

### 50.1. Full-document transformation

Một lựa chọn là đọc fullDocument rồi tạo lại target projection. Cần hiểu updateLookup không luôn là exact event after-image và có thể null nếu document đã bị delete.

### 50.2. Transactional consistency

Nếu một source document thành nhiều target documents, worker phải định nghĩa atomicity của các target writes hoặc đảm bảo chỉ expose dữ liệu sau khi toàn nhóm hoàn tất.

---

## 51. Security và compliance

Migration thường sao chép dữ liệu nhạy cảm qua network/temporary storage.

Checklist:

- TLS cho source và target.
- Least-privilege roles cho dump/CDC/write.
- Secret management qua environment/vault.
- Không đưa URI credentials vào logs hoặc shell history.
- Encryption cho archive và temporary files.
- KMS/CMK và key rotation/restore access.
- Data residency/cross-region restrictions.
- Audit migration operations.
- Retention và xóa file tạm sau xác minh.
- Access controls trên monitoring/dashboard.
- Không log raw documents khi phát hiện diff.
- Tách quyền CDC reader với target writer.
- Không chạy destructive restore/cleanup ngoài namespace được phê duyệt.

### 51.1. Dùng kết nối riêng có identity

Một migration user chỉ nên có những quyền cần thiết. Không dùng root/admin credentials làm mặc định chỉ vì đơn giản.

### 51.2. Temporary dump là bản sao dữ liệu thật

Một file `.archive.gz` có thể chứa PII/tokens/financial records. Phải có policy bảo vệ như với primary database, không để trên shared disk hoặc trong CI artifacts công khai.

---

# PHẦN VI — KIỂM THỬ VÀ VẬN HÀNH

## 52. Test matrix trước migration

| Test case | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Initial copy | 1.000 documents, no writes | Đích đủ records |
| Update during backfill | Document thay đổi sau khi scan | CDC catch-up ra phiên bản mới nhất |
| Insert during backfill | Document mới ở cuối scan | Không bị bỏ sót |
| Delete during backfill | Document bị xóa | Đích không giữ stale record |
| Rapid updates | v1→v2→v3 | Kết quả cuối v3 |
| CDC restart | Crash sau target write trước token save | Replay không duplicate harmful effects |
| Oplog lost | Consumer offline quá lâu | Detect failure, không silently skip |
| Duplicate source keys | Unique index target chặn | Quarantine hoặc migration policy rõ |
| TTL expiry | Source/target monitor khác nhịp | Reconcile theo retention policy |
| Changed BSON type | Decimal128/Date/ObjectId | Đúng type/precision |
| Shard routing | Upserts theo shard key | Không lỗi routing/conflicts |
| Concurrent writes | Hai writers cùng key | Version/order đúng |
| Partial target outage | Target fails, source available | Retry durable/backlog |
| Cutover drain | In-flight writes ở source | Không bỏ sót |
| Rollback rehearsal | Writes mới sau cutover | Không mất acknowledged writes |
| Application canary | Shadow read/critical endpoints | Diff và latency đạt mục tiêu |

---

## 53. Failure injection: nên thử lỗi ở đâu?

Một migration worker cần test:

1. Process crash trước khi apply event.
2. Crash sau khi apply nhưng trước checkpoint.
3. Target timeout sau khi write thực tế có thể đã thành công.
4. Network partition giữa source và target.
5. Primary failover khi đang giữ change stream.
6. Source oplog history hết hạn.
7. Target full disk/IOPS throttling.
8. Schema validator hoặc unique constraint từ chối document.
9. Một bad document gây decode/transform error.
10. Retry queue backlog tăng quá giới hạn.
11. Concurrent source updates đảo thứ tự ở target.
12. DDL change không hỗ trợ.
13. Worker lease timeout và hai instances cùng apply.
14. Cutover bị hủy giữa chừng.
15. Application connection string có cache lâu chưa switch.
16. Reverse sync không hoạt động khi rollback.

### 53.1. Không dùng production làm chaos test

Các lỗi này cần staging/test environment hoặc diễn tập được phê duyệt. Không ngắt network primary production để “thử xem CDC có tự phục hồi” mà không có change ticket và rollback.

---

## 54. Monitoring migration

Các bảng thông tin quan trọng:

| Chỉ số | Dùng để |
| --- | --- |
| Backfill docs/s | Đo tốc độ copy |
| Backfill checkpoint | Phát hiện job stuck |
| Source write rate | Ước lượng CDC load |
| CDC queue depth/age | Theo dõi lag |
| Last durable resume token | Điểm có thể resume |
| Oldest unprocessed event age | Phát hiện nguy cơ mất oplog history |
| Source oplog window | Tính khoảng an toàn |
| Target apply errors | Unique/schema/permission failures |
| Retry/DLQ | Không bỏ qua những records lỗi |
| Mismatches by partition | Dữ liệu không đồng nhất |
| Target disk/CPU/IOPS | Capacity |
| Critical API p95/p99 | Performance |
| Duplicate business effects | Correctness |
| Cutover readiness | Decision go/no-go |

### 54.1. Lag thấp nhưng DLQ không rỗng là chưa an toàn

Một pipeline có thể áp 99,99% events rất nhanh nhưng bỏ 1 event chứa giao dịch quan trọng vào DLQ. Không xem consumer lag = 0 là đủ để cutover nếu unresolved errors còn tồn tại.

### 54.2. Alerts phải gắn hành động

Ví dụ:

```text
CDC lag > safe threshold
  -> Stop cutover
  -> Scale/repair consumer
  -> Check oplog window
  -> Do not drop source

Unresolved transform error
  -> Quarantine + investigate
  -> Reprocess from checkpoint
  -> Block final reconciliation

Target unique violation
  -> Inspect source/target key
  -> Apply explicit conflict policy
  -> Do not silently ignore
```

---

## 55. Quyết định chọn phương pháp theo tình huống

### Tình huống A: chuyển 5 GiB trong cửa sổ bảo trì 2 giờ

- Có thể ngừng writes.
- Schema gần như không đổi.
- Ít collections.

**Hướng:** dump/restore hoặc công cụ backup phù hợp, verify, cutover. Không cần vận hành CDC phức tạp nếu downtime đáp ứng.

### Tình huống B: chuyển 2 TiB, vẫn ghi liên tục

- Full copy mất nhiều giờ/ngày.
- RPO chặt.
- Writes lớn.

**Hướng:** initial copy + CDC hoặc migration tool được hỗ trợ; đặc biệt chú ý oplog window, durable capture, throughput và final cutover barrier.

### Tình huống C: chuyển dần từng tenant

- T1 cần canary trước T2.
- Application kiểm soát routing.
- Có ownership mapping.

**Hướng:** tenant-by-tenant migration; có thể kết hợp CDC/dual-write/outbox, shadow reads và explicit writer ownership.

### Tình huống D: sao chép tới hệ search/analytics

- Có thể chấp nhận eventual consistency.
- Schema chuyển đổi nhiều.
- Không dùng target làm transactional source of truth.

**Hướng:** CDC/streaming connector với idempotent sink, DLQ và rebuild path; không cần direct dual-write trong mọi request.

### Tình huống E: tái thiết kế document schema trong cùng cluster

- Collection cũ và mới cùng MongoDB deployment.
- App có thể đọc cả hai schema một giai đoạn.

**Hướng:** expand–migrate–contract, backfill + change propagation, feature flags và controlled read cutover. Transaction có thể hữu ích cho nhóm writes ngắn trong cùng deployment.

---

## 56. Bài tập 1 — Chọn chiến lược

Hệ thống có database 8 GiB, cho phép maintenance 3 giờ, không có writes trong thời gian đó.

**Hỏi:** Cần CDC không?

**Đáp án:** Không nhất thiết. Export/import hoặc dump/restore có kiểm chứng thường đơn giản hơn và đủ đáp ứng nếu duration, compatibility và restore tests đạt yêu cầu.

---

## 57. Bài tập 2 — Gap giữa dump và stream

Một team dump từ 10:00 đến 11:00, sau đó bắt Change Streams lúc 11:05.

**Hỏi:** Nguy cơ?

**Đáp án:** Những writes trong khoảng 10:00–11:05 có thể bị thiếu hoặc không được phản ánh chính xác. Cần snapshot boundary và change capture từ mốc phù hợp trước/during backfill.

---

## 58. Bài tập 3 — CDC lag lớn hơn oplog window

Backfill 24 giờ, oplog chỉ giữ khoảng 6 giờ thay đổi và consumer không persist events.

**Đáp án:** Có nguy cơ mất change history để replay. Cần tăng retention/capacity, stream/persist changes liên tục hoặc dùng migration tool/chiến lược khác.

---

## 59. Bài tập 4 — Apply trước checkpoint

Target apply event thành công nhưng worker crash trước khi save resume token.

**Đáp án:** Event có thể được replay; phải idempotent hoặc transactionally cập nhật offset và target trong boundary hỗ trợ.

---

## 60. Bài tập 5 — Lưu token trước apply

Worker lưu token rồi mới ghi target, target ghi thất bại.

**Đáp án:** Có thể bỏ sót event vĩnh viễn sau restart. Không checkpoint trước khi effect được xác nhận.

---

## 61. Bài tập 6 — Delete event

Source xóa order, CDC consumer chỉ xử lý inserts/updates.

**Đáp án:** Target sẽ giữ stale document. Cần map delete/tombstone theo schema và ordering.

---

## 62. Bài tập 7 — Update lookup

Event update v2 được consumer xử lý sau khi document đã đạt v3.

**Đáp án:** `fullDocument: updateLookup` có thể trả trạng thái hiện tại v3, không phải exact after-image v2. Chọn state replication/versioning/pre-post images phù hợp.

---

## 63. Bài tập 8 — Direct dual-write

Source write success, target timeout, HTTP trả 500, client retry.

**Đáp án:** Có nguy cơ duplicate/unknown effects. Cần source of truth, idempotent request key, durable retry/outbox và reconciliation.

---

## 64. Bài tập 9 — Transaction qua hai cluster

Một MongoDB transaction trên source có làm target write ở cluster riêng commit atomically không?

**Đáp án:** Không. Cần protocol khác như outbox, connector hoặc distributed coordination được thiết kế riêng; không giả định cross-cluster ACID.

---

## 65. Bài tập 10 — Target nhận events đảo thứ tự

Order có version 40 và 41. Target áp 41 trước rồi 40.

**Đáp án:** Final state có thể sai dù mỗi operation idempotent. Phải giữ per-key order hoặc version-aware conditional writes.

---

## 66. Bài tập 11 — TTL gây lệch count

Source và target có cùng expired documents nhưng TTL monitor ở target xóa trước.

**Đáp án:** Count khác không nhất thiết do migration mất dữ liệu. Reconcile theo retention/business policy và mốc nhất quán, không chỉ raw count.

---

## 67. Bài tập 12 — CSV mất kiểu dữ liệu

`Decimal128("19.99")` được export/import qua một spreadsheet rồi trở thành floating-point 19.9900000002.

**Đáp án:** CSV không bảo toàn BSON precision. Dùng BSON/Extended JSON có mapping type hoặc biến đổi bằng `BigDecimal` theo policy.

---

## 68. Bài tập 13 — Same document, new `_id`

Mỗi retry tạo ObjectId đích mới.

**Đáp án:** Có thể tăng duplicate records. Cần stable source→target key mapping và idempotency.

---

## 69. Bài tập 14 — Cutover nhưng còn events tồn đọng

Dashboard lag báo 0 trên một partition, nhưng còn event lỗi trong DLQ.

**Đáp án:** Chưa đủ điều kiện cutover. Cần giải quyết/reprocess DLQ và xác nhận final source marker/partitions.

---

## 70. Bài tập 15 — Rollback chỉ đổi URI

Sau khi target nhận 10.000 writes mới, team đổi app URI về source cũ.

**Đáp án:** Source thiếu writes sau cutover; cần reverse sync/reconciliation hoặc forward-fix theo kế hoạch.

---

## 71. Bài tập 16 — Outbox được tạo sau business write

Ứng dụng update order thành công rồi crash trước khi tạo outbox event.

**Đáp án:** Target có thể không bao giờ nhận event. Nếu cần durable propagation, ghi business update và outbox event atomically trong cùng transaction được hỗ trợ.

---

## 72. Bài tập 17 — Shadow read ngay sau write

Target eventual lag 5 giây, shadow read lập tức báo mismatch.

**Đáp án:** Có thể là lag hợp lệ. So sánh theo watermark hoặc lag tolerance rõ, không nhầm transient stale read với permanent data loss.

---

## 73. Bài tập 18 — Migration trước index

Target đã có unique key design mới nhưng source có duplicate.

**Đáp án:** Phải phát hiện và xử lý conflicts bằng policy, không xóa tùy tiện hoặc để mọi event fail.

---

## 74. Bài tập 19 — Ứng dụng còn writer cũ

Một scheduled job vẫn ghi source sau cutover.

**Đáp án:** Tạo split-brain dữ liệu. Inventory mọi writers và ngăn source writes sau chuyển ownership, hoặc có routing/CDC bridge rõ.

---

## 75. Bài tập 20 — Một document làm hai target records

Migration transform một source order thành order + invoice ở target; chỉ order được ghi thành công.

**Đáp án:** Target có thể vi phạm invariant. Cần transaction ở target nếu phù hợp, hoặc staged publish/completion marker với retry/reconciliation.

---

## 76. Checklist tiền di chuyển

- [ ] Đã xác định source/target topology, versions và FCV?
- [ ] Đã xác định RPO/RTO và downtime allowance?
- [ ] Có danh sách writers/consumers đầy đủ?
- [ ] Có dữ liệu/namespace inventory?
- [ ] Đã xác định schema/transform version?
- [ ] Có kế hoạch `_id`/business key mapping?
- [ ] Có unique, partial, sparse, TTL, collation, validator inventory?
- [ ] Có read/write throughput baseline?
- [ ] Có backup có thể phục hồi và key/KMS access?
- [ ] Công cụ Database Tools/CDC tương thích?
- [ ] Có lựa chọn snapshot consistency?
- [ ] Có enough target capacity và network bandwidth?
- [ ] Có kế hoạch DDL freeze?
- [ ] Có data privacy/retention policy?
- [ ] Có staging rehearsal với dataset đại diện?

---

## 77. Checklist CDC/dual-write

- [ ] CDC start point được thiết lập trước backfill?
- [ ] Changes được capture/persist bền vững?
- [ ] Oplog window đủ và được monitor?
- [ ] Có resume token checkpoint sau apply?
- [ ] Có retry/backoff và DLQ?
- [ ] Có xử lý insert/update/replace/delete?
- [ ] Có policy cho DDL/invalidate?
- [ ] Có handling fullDocument null và updateLookup semantics?
- [ ] Có per-key order/version control?
- [ ] Có idempotent apply?
- [ ] Có bounded worker concurrency?
- [ ] Có durable outbox nếu dùng dual-write?
- [ ] External effects có idempotency?
- [ ] Có backfill/CDC race prevention?
- [ ] Có checkpoints theo partition?
- [ ] Có monitoring lag/errors?
- [ ] Có khả năng detect/rebootstrap sau history loss?

---

## 78. Checklist cutover và hậu kiểm

- [ ] Backfill đã complete theo partitions?
- [ ] CDC đã apply tới final watermark?
- [ ] Không còn unresolved DLQ/transform errors?
- [ ] Count/hash/business aggregates đạt mục tiêu?
- [ ] Unique/TTL/index/validator phù hợp?
- [ ] Search/analytics indexes đã ready?
- [ ] Critical workflows pass smoke/integration tests?
- [ ] Đã drain các source writers?
- [ ] Có chỉ một writer authority sau cutover?
- [ ] Route/DNS/config cache đã chuyển?
- [ ] Có rollback boundary và reverse sync plan?
- [ ] Có bảo vệ source read-only trong rollback window?
- [ ] Có alerts p95/p99/errors/CDC?
- [ ] Có access control và KMS/backup trên target?
- [ ] Có ownership/retention/decommission approval?

---

## 79. Những ngộ nhận phổ biến

| Ngộ nhận | Hiểu đúng |
| --- | --- |
| “Export/import luôn là backup nhất quán.” | Phụ thuộc công cụ và concurrent writes/snapshot policy. |
| “mongoexport là mongodump dạng JSON.” | JSON/CSV không bảo toàn toàn bộ BSON metadata và indexes. |
| “Copy xong documents là migration xong.” | Còn indexes, constraints, security, catch-up, cutover. |
| “Chỉ cần nghe CDC sau khi copy.” | Có thể mất changes giữa snapshot và stream start. |
| “CDC luôn có full document chính xác cho mỗi update.” | `updateLookup` không phải exact historical after-image. |
| “Resume token sống mãi.” | Phụ thuộc oplog/change history và invalidate semantics. |
| “Checkpoint trước apply giúp nhanh hơn.” | Có thể mất events khi crash. |
| “Apply idempotent là không cần thứ tự.” | Stale events có thể ghi đè new state. |
| “Chỉ xử lý inserts/updates là đủ.” | Deletes/DDL/schema cần policy. |
| “CDC lag=0 nghĩa hai DB giống nhau.” | Có thể transform sai hoặc bỏ event vào DLQ. |
| “Dual-write là transaction across two databases.” | Không có atomicity xuyên hai clusters độc lập. |
| “Ghi cả hai nơi thành công nghĩa sẽ không divergence.” | Có thể đảo thứ tự writes hoặc target chưa đồng bộ deletes. |
| “Application retry tự làm dual-write an toàn.” | Cần idempotency, ordering và durable retry. |
| “Outbox tự có exactly-once.” | Thường at-least-once; sink phải idempotent. |
| “Count bằng nhau là data equality.” | Values/types có thể khác. |
| “TTL xóa đồng thời source và target.” | TTL asynchronous và phụ thuộc clock/monitor. |
| “Unique key ở target chắc giống source.” | Cần thiết kế index/partial/collation/sharding. |
| “ObjectId luôn là commit timestamp.” | Không; có client-generated IDs và clock considerations. |
| “Tăng worker là tăng throughput.” | Có thể bão hòa storage/CPU/downstream. |
| “Chuyển read trước write không có rủi ro.” | Target có thể stale và chưa có writer ownership. |
| “Rollback chỉ là đổi connection string.” | Target có thể đã có writes mà source chưa nhận. |
| “Backup archive không nhạy cảm.” | Nó chứa dữ liệu thật, cần encryption/retention. |

---

## 80. Tài liệu tham khảo chính thức

1. [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/) — logical dump, archive, gzip và giới hạn oplog.
2. [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/) — restore, namespace mapping và oplog replay.
3. [MongoDB Database Tools — mongoexport](https://www.mongodb.com/docs/database-tools/mongoexport/) — xuất JSON/CSV và các giới hạn.
4. [MongoDB Database Tools — mongoimport](https://www.mongodb.com/docs/database-tools/mongoimport/) — import modes, type handling, upsert.
5. [MongoDB — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — operations, resume tokens, pipeline và topology.
6. [MongoDB — Change Streams Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/) — oplog, deployment và vận hành.
7. [MongoDB — Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream) — resumeAfter, startAfter, invalidate considerations.
8. [MongoDB — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images) — các lựa chọn image và retention.
9. [MongoDB — Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — history window và replication.
10. [MongoDB — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — atomicity và session/transaction scope.
11. [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — business key constraints.
12. [MongoDB — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — asynchronous retention cleanup.
13. [MongoDB — Sharded Cluster Unique Constraints](https://www.mongodb.com/docs/manual/core/index-unique/#sharded-clusters-and-unique-indexes) — shard key restrictions.
14. [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — consumption/resume.
15. [MongoDB Java Sync Driver — Bulk Write](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/) — batch errors và ordered/unordered.
16. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — withTransaction/session scope.
17. [MongoDB Kafka Connector](https://www.mongodb.com/docs/kafka-connector/current/) — connector-based change pipelines.
18. [MongoDB mongosync](https://www.mongodb.com/docs/mongosync/current/) — những đường migration được hỗ trợ và hạn chế công cụ.
19. [MongoDB Atlas — Migrate or Import Data](https://www.mongodb.com/docs/atlas/import/) — các lựa chọn migration vào Atlas.
20. [MongoDB — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — fidelity của Decimal128, Date, ObjectId và Binary.

**Lưu ý phiên bản:** hỗ trợ `mongosync`, Change Stream pre/post-images, MongoDB Database Tools options, resume semantics, sharding constraints và connector versions thay đổi theo MongoDB Server/FCV/driver. Trước khi thực hiện production migration, phải đối chiếu tài liệu đúng nguồn/đích và release đang dùng.

---

## 81. Tổng kết

Để di chuyển dữ liệu MongoDB an toàn, phải chọn đúng cơ chế cho đúng yêu cầu:

- **Xuất/nhập (`mongodump`/`mongorestore`, `mongoexport`/`mongoimport`)** thích hợp khi có snapshot/cửa sổ bảo trì, hoặc cần một lô dữ liệu được kiểm soát. Nó không tự bắt các writes xảy ra sau thời điểm xuất.
- **CDC (Change Streams, connector hoặc migration tool)** giúp sao chép những thay đổi trong lúc backfill, nhưng cần **điểm bắt đầu đúng, durable capture, oplog retention, resume token, ordering, deletes và catch-up barrier**.
- **Ghi song song (dual-write)** có thể hỗ trợ chuyển đổi dần nhưng không có atomicity giữa hai cluster độc lập. Để giảm mất dữ liệu, thường cần **source of truth + outbox/durable retry + idempotency + version control + reconciliation**.

Dù chọn cách nào, migration chỉ hoàn thành khi **target có dữ liệu và hành vi đúng, mọi writers đã chuyển ownership, các lỗi chưa xử lý được giải quyết, business workflows hoạt động, backup/rollback posture rõ và metrics ổn định**.

**Một migration thành công không chỉ sao chép được documents; nó bảo toàn ý nghĩa nghiệp vụ của dữ liệu trong toàn bộ quá trình dữ liệu còn thay đổi.**
