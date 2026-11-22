# Giới hạn thời gian, dung lượng và các thao tác bị hạn chế trong MongoDB Transaction

**Multi-document transaction** cho phép MongoDB thực hiện nhiều thao tác trên nhiều document, collection hoặc database như một đơn vị nguyên tử trong những topology được hỗ trợ. Ví dụ, một thao tác chuyển tiền có thể cùng lúc trừ ví A, cộng ví B và ghi lịch sử chuyển khoản; nếu transaction abort thì những thay đổi thuộc transaction không được commit một phần.

Tuy nhiên, transaction **không phải vùng làm việc không giới hạn**. Khi một transaction giữ snapshot quá lâu, ghi quá nhiều dữ liệu, tranh chấp khóa, cố chạy lệnh quản trị không được hỗ trợ hoặc thực hiện công việc trên nhiều shard, nó có thể bị abort, timeout hay gây áp lực lớn lên toàn hệ thống. Một câu rất dễ hiểu sai là “MongoDB transaction tối đa 16 MB”: cần phân biệt **giới hạn 16 MiB của từng BSON document/oplog entry** với **tổng dung lượng transaction**, vốn có quy tắc và giới hạn tài nguyên khác nhau theo phiên bản.

Bài học thuộc chương **Giao dịch** của module *Database Engine Document MongoDB*. Mục tiêu là nhận diện những giới hạn cần xét **trước khi** đưa một luồng nghiệp vụ vào transaction, từ thời gian, bộ nhớ, oplog, lock, các lệnh bị hạn chế đến cách xử lý lỗi và thiết kế thay thế. Các ví dụ dùng **mongosh** và **MongoDB Node.js Driver** trong database `txn_limits_lab`. Hãy thử trên replica set hoặc sharded cluster dành cho lab; **MongoDB standalone thông thường không hỗ trợ multi-document transaction**. Những quy tắc liên quan DDL, sharding, error code, timeout và cache có thể thay đổi giữa MongoDB 4.x, 5.x, 6.x, 7.x, 8.x và các phiên bản sau; phải đối chiếu phiên bản, driver và dịch vụ MongoDB đang sử dụng khi triển khai.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ranh giới nguyên tử của transaction và sự khác nhau giữa transaction, atomic single-document update và workflow dài.
2. Nắm ý nghĩa của `transactionLifetimeLimitSeconds`, thời điểm transaction bắt đầu, tình huống timeout và những tham số khác như `maxCommitTimeMS`.
3. Phân biệt **16 MiB mỗi BSON document**, **16 MiB mỗi oplog entry** và việc một transaction có thể chứa nhiều oplog entries; không áp đặt sai “16 MiB tổng transaction”.
4. Hiểu vì sao **WiredTiger cache pressure**, snapshot lâu và transaction có quá nhiều thao tác vẫn có thể gây lỗi hoặc giảm hiệu năng.
5. Nhận biết thao tác CRUD, aggregation, DDL nào được dùng trong transaction, thao tác nào có giới hạn hoặc không được hỗ trợ.
6. Phân biệt giới hạn của replica set và sharded cluster, đặc biệt khi tạo collection/index hoặc có chunk migration.
7. Biết dùng session, read concern, write concern, commit/abort, và tránh thao tác song song không hỗ trợ trên cùng session/transaction.
8. Xử lý `TransientTransactionError`, `UnknownTransactionCommitResult` và các lỗi permanent mà không retry mù.
9. Thiết kế transaction ngắn, có index phù hợp, có idempotency và không chứa HTTP call hay công việc CPU dài.
10. Chia một batch rất lớn thành nhiều transaction có checkpoint/reconciliation khi không thể commit toàn bộ trong một transaction.
11. Giám sát transaction duration, active/aborted transactions, lock waits, cache và ảnh hưởng tới replication.
12. Thực hiện bài lab để quan sát commit/abort, timeout, write conflict và khác biệt giữa lỗi nghiệp vụ với lỗi giới hạn hệ thống.

## 2. Transaction bảo đảm gì, và không bảo đảm gì?

Một transaction phối hợp nhiều thao tác cơ sở dữ liệu trong một session:

~~~mermaid
flowchart TD
    Req["Yêu cầu chuyển tiền"] --> Begin["Bắt đầu transaction"]
    Begin --> Debit["Trừ ví A"]
    Debit --> Credit["Cộng ví B"]
    Credit --> Ledger["Ghi transfer ledger"]
    Ledger --> Decision{"Commit được không?"}
    Decision -->|Có| All["Tất cả thay đổi được commit"]
    Decision -->|Không| Abort["Abort: không commit phần thay đổi trong transaction"]
~~~

Những bảo đảm quan trọng:

- **Atomicity:** các ghi thuộc transaction commit cùng nhau hoặc bị rollback theo transaction.
- **Isolation/snapshot semantics:** những read trong transaction tuân theo read concern/snapshot và quy tắc transaction; không giống chuỗi lệnh đọc/ghi rời rạc.
- **Commit durability:** phụ thuộc write concern và deployment; không được suy ra độ bền majority chỉ từ việc lệnh update tạm thời đã trả kết quả trong transaction.

Những điều **transaction không tự giải quyết**:

- Không biến thao tác bên ngoài MongoDB như gửi email, gọi cổng thanh toán thành atomic.
- Không cho phép transaction mở vô thời hạn.
- Không làm việc ghi/đọc đồng thời trên mọi shard trở nên miễn phí.
- Không tự làm API idempotent nếu client gửi lại cùng yêu cầu như một transaction mới.
- Không bảo đảm mọi invariant nghiệp vụ khi hai transaction cập nhật **những document khác nhau** nhưng cùng phụ thuộc một điều kiện tổng hợp; phải thiết kế điều kiện/constraint đủ mạnh.
- Không cho phép tất cả MongoDB commands hoặc aggregation stages hoạt động trong transaction.

### 2.1. Khi chỉ cần một document, thường không cần transaction

~~~javascript
db.inventory.updateOne(
  { _id: "sku-A", available: { $gte: 1 } },
  { $inc: { available: -1, reserved: 1 } }
)
~~~

MongoDB cập nhật các field của **một document** nguyên tử. Điều kiện `available >= 1` nằm cùng lệnh ghi, tránh kiểm tra stock bằng read trước rồi ghi sau. Nếu invariant chỉ nằm trong một document, conditional update này thường đơn giản hơn tạo multi-document transaction.

Multi-document transaction đáng cân nhắc khi thay đổi phải nhất quán **trên nhiều document** hoặc collection: ví dụ hai ví tiền và record chuyển khoản, hoặc order + inventory + request ledger.

## 3. Bản đồ các loại giới hạn

| Loại giới hạn | Ví dụ | Điều cần nhớ |
|---|---|---|
| **Thời gian sống transaction** | `transactionLifetimeLimitSeconds` | Mặc định thường **60 giây**; transaction quá lâu có thể bị abort |
| **Thời gian chờ khóa** | `maxTransactionLockRequestTimeoutMillis` | Có thể abort khi không lấy được lock cần thiết theo ngân sách |
| **Thời gian commit** | Driver option `maxCommitTimeMS` | Giới hạn/điều khiển thời gian commit theo giao thức; không thay lifetime |
| **Server selection / mạng** | `serverSelectionTimeoutMS`, socket timeout | Client có thể timeout trước hoặc sau khi server đã xử lý thao tác |
| **Kích thước BSON** | Một document tối đa 16 MiB | Áp dụng cho từng document, kể cả document được ghi trong transaction |
| **Oplog entry** | Một entry có giới hạn BSON | Không đồng nghĩa toàn transaction chỉ có một entry |
| **WiredTiger cache** | Transaction ghi/giữ quá nhiều thay đổi | Có thể gặp transaction-too-large hoặc cache pressure |
| **Số thao tác / số document** | Một batch hàng trăm nghìn updates | Không nên dựa vào một con số “unlimited”; vẫn bị chi phối tài nguyên, thời gian và độ phức tạp |
| **Lệnh bị hạn chế** | `$out`, `$merge`, một số DDL/admin commands | Không phải lệnh hợp lệ ngoài transaction nào cũng hợp lệ trong transaction |
| **Topology/sharding** | Cross-shard write, chunk migration | Có thêm ràng buộc và chi phí điều phối |
| **Driver/session** | Callback transaction được retry, thao tác song song | Phải giữ session đúng và tránh side effects không thể rollback |

**Không có một cài đặt “transactionLimit” duy nhất** giải quyết hết các ràng buộc này. Thiết kế tốt phải tính các loại giới hạn cùng lúc.

## 4. Môi trường lab: dữ liệu và yêu cầu transaction

Giả sử cần chuyển điểm thưởng giữa hai ví trong **một tenant** và ghi một bản ghi transfer. Thiết kế dữ liệu:

~~~javascript
// wallets
{
  _id: "wallet-A",
  tenantId: "t-01",
  ownerId: "customer-A",
  balancePoints: 1000,
  version: 1
}

{
  _id: "wallet-B",
  tenantId: "t-01",
  ownerId: "customer-B",
  balancePoints: 200,
  version: 1
}

// transfer_log
{
  tenantId: "t-01",
  requestId: "transfer-R1",
  from: "wallet-A",
  to: "wallet-B",
  amountPoints: 150,
  state: "COMPLETED"
}
~~~

Invariant:

1. Không cho số dư âm.
2. Không được trừ A mà không cộng B.
3. Cùng `requestId` không được áp dụng lần hai.
4. Chỉ chuyển giữa ví hợp lệ trong tenant được xác thực.

### 4.1. Chuẩn bị collection **bên ngoài transaction**

Trên MongoDB replica set lab:

~~~javascript
use txn_limits_lab

db.createCollection("wallets")
db.createCollection("transfer_log")
db.createCollection("request_outbox")

db.wallets.insertMany([
  {
    _id: "wallet-A",
    tenantId: "t-01",
    ownerId: "customer-A",
    balancePoints: 1000,
    version: 1
  },
  {
    _id: "wallet-B",
    tenantId: "t-01",
    ownerId: "customer-B",
    balancePoints: 200,
    version: 1
  }
])

db.transfer_log.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uq_tenant_transfer_request" }
)

db.wallets.createIndex(
  { tenantId: 1, ownerId: 1 },
  { name: "idx_wallet_tenant_owner" }
)
~~~

Chỉ chạy một lần trên **database lab rỗng**; chạy lại insert cùng `_id` sẽ gặp duplicate key. Pre-create collection/index giúp bài tập không phụ thuộc vào các ngoại lệ DDL trong transaction và giảm nguy cơ phát sinh lock metadata bất ngờ.

### 4.2. Kiểm tra trước khi bắt đầu

~~~javascript
db.wallets.find().sort({ _id: 1 })
db.transfer_log.getIndexes()
~~~

Lab dùng `balancePoints` là số nguyên nhỏ để dễ đọc. Với tiền thật, dùng đơn vị nguyên nhỏ nhất hoặc Decimal128, kiểm tra overflow/range và lập quy tắc làm tròn; không dùng số thực dấu phẩy động tùy tiện cho số tiền.

## 5. Giới hạn thời gian sống: `transactionLifetimeLimitSeconds`

Trong MongoDB, một multi-document transaction thường có **giới hạn thời gian sống mặc định 60 giây** do server parameter `transactionLifetimeLimitSeconds` điều khiển. Nếu transaction chạy quá thời gian được cho phép, server có cơ chế tự abort transaction hết hạn.

~~~text
T = 0s    Bắt đầu transaction
T = 5s    Đọc wallet A
T = 12s   Ghi wallet A
T = 35s   Chờ API ngoài (không nên!)
T = 61s   Transaction có thể bị abort do hết lifetime
T = 62s   Ứng dụng thử commit => thất bại
~~~

**Transaction không nên kéo dài đến sát ngưỡng** dù chưa báo lỗi: lock contention, failover, mạng chậm và garbage collection trong application có thể làm request chậm hơn dự kiến.

### 5.1. Xem tham số trên deployment của bạn

Nếu có quyền quản trị và server cho phép:

~~~javascript
db.adminCommand({
  getParameter: 1,
  transactionLifetimeLimitSeconds: 1
})
~~~

Đây là lệnh xem **server configuration**, không chạy bên trong transaction. Dịch vụ managed MongoDB có thể hạn chế quyền thay đổi tham số hoặc thay đổi bằng control plane riêng.

### 5.2. Mặc định 60 giây không phải “transaction luôn chạy đủ 60 giây”

Transaction có thể thất bại **sớm hơn** do:

- Write conflict với transaction khác.
- Không lấy được lock cần thiết.
- Session/connection bị lỗi hoặc primary thay đổi.
- Dữ liệu/payload lớn khiến cache không đáp ứng.
- Command không được phép bên trong transaction.
- Application timeout và tự abort.
- Giới hạn bộ nhớ/thực thi của stage liên quan.

Ngược lại, việc transaction bị quá hạn và bị server dọn/abort chịu các chi tiết vận hành; không viết ứng dụng dựa trên giả định “chính xác giây 60.000 thì mọi transaction bị hủy đồng thời”. Thiết kế deadline **ngắn hơn ngưỡng server** và có handling rõ ràng.

### 5.3. Đừng tăng lifetime như giải pháp đầu tiên

Tăng `transactionLifetimeLimitSeconds` có thể hữu ích cho workload đặc biệt, nhưng transaction càng lâu càng dễ:

- Giữ snapshot đọc/ghi cũ, cản trở thu hồi phiên bản dữ liệu.
- Làm tăng áp lực cache và lưu trữ.
- Kéo dài thời gian giữ lock hoặc tài nguyên transaction.
- Tăng khả năng gặp write conflict với những transaction/ghi khác.
- Tăng rủi ro khi failover, chunk migration hoặc job bị treo.

**Ưu tiên cắt công việc, giảm phạm vi thao tác và bỏ network call khỏi transaction** trước khi nâng giới hạn toàn server.

## 6. Các mốc thời gian và timeout không phải một

Một request thực tế trải qua nhiều giai đoạn:

~~~mermaid
flowchart LR
    API["API request deadline"] --> Select["Chọn server"]
    Select --> Tx["Transaction body"]
    Tx --> Lock["Chờ lock / thực thi"]
    Lock --> Commit["commitTransaction"]
    Commit --> Response["Phản hồi client"]
~~~

| Tham số/giới hạn | Phạm vi | Rủi ro khi nhầm lẫn |
|---|---|---|
| `transactionLifetimeLimitSeconds` | Thời gian sống transaction trên server | Tưởng chỉ giới hạn từng query |
| `maxTransactionLockRequestTimeoutMillis` | Thời gian chờ lấy lock theo cơ chế server | Tưởng đây là thời gian sống transaction |
| `maxCommitTimeMS` | Giới hạn liên quan quá trình commit transaction theo driver/server hỗ trợ | Tưởng tăng giá trị này sẽ cho transaction body chạy dài hơn |
| `maxTimeMS` trên các operation được hỗ trợ | Thời gian thực thi lệnh | Tưởng có thể dùng thay toàn bộ transaction deadline |
| `serverSelectionTimeoutMS` | Driver chờ chọn server đủ điều kiện | Tưởng query đã được server chạy |
| Socket/connect timeout | Mạng/driver | Client timeout không chứng minh commit chưa xảy ra |
| Application deadline | Toàn bộ yêu cầu nghiệp vụ | Nếu dài hơn lifetime server, không bảo đảm hoàn tất |

### 6.1. `maxCommitTimeMS`

Trong driver hỗ trợ, transaction option `maxCommitTimeMS` điều khiển thời gian tối đa ở bước commit theo semantics của lệnh. Ví dụ:

~~~javascript
// Node.js Driver: một phần của transaction options
{
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  maxCommitTimeMS: 10000
}
~~~

Không diễn giải rằng transaction có “60s body + 10s commit” như một bảo đảm cứng. Thời gian sống transaction, commit timeout, retry commit và lịch trình của server là những cơ chế tương tác. Nếu kết quả commit chưa rõ, cần **reconcile/retry commit đúng cách**, không mặc định transaction chưa ghi.

### 6.2. Thời gian chờ khóa

Tham số `maxTransactionLockRequestTimeoutMillis` kiểm soát ngân sách chờ lock của transaction ở những tình huống liên quan. Trong một số phiên bản/cấu hình, thời gian chờ mặc định **khá ngắn**; DDL hoặc thao tác cạnh tranh có thể làm transaction abort trước khi chạm lifetime 60 giây.

Có thể xem (khi có quyền):

~~~javascript
db.adminCommand({
  getParameter: 1,
  maxTransactionLockRequestTimeoutMillis: 1
})
~~~

Không chỉnh tăng tùy tiện trên production vì chờ lock lâu hơn có thể kéo dài hàng đợi, ảnh hưởng những operation khác và che giấu vấn đề về index/thiết kế transaction.

### 6.3. Timeout ở client không xác định outcome commit

~~~text
Client -> commitTransaction
Server  -> commit thành công
Mạng    -> mất phản hồi
Client  -> nhận timeout
~~~

Trong tình huống này, client **không được coi timeout là bằng chứng transaction rollback**. Thiết kế idempotency key và lưu business result trong database để có thể kiểm tra/replay khi request gửi lại.

## 7. Vì sao transaction dài gây áp lực trên storage engine?

MongoDB với WiredTiger sử dụng MVCC/snapshot để hỗ trợ nhiều reader/writer. Một transaction dài có thể giữ một trạng thái quan sát cũ trong khi các transaction khác tiếp tục ghi.

### 7.1. Snapshot được giữ lâu

~~~text
T0: Transaction T đọc snapshot
T1: Các writer khác thay đổi hàng nghìn documents
T2: Transaction T vẫn chưa commit/abort
T3: Storage engine cần duy trì thông tin cần thiết để T đọc nhất quán
~~~

Chi phí có thể thể hiện ở cache, lịch sử phiên bản/đường lưu dữ liệu, áp lực eviction và thời gian giải phóng tài nguyên. Không phải mọi transaction đều khóa toàn bộ collection từ lúc bắt đầu; nhưng **snapshot lâu vẫn có giá** ngay cả khi transaction đang chờ ứng dụng.

### 7.2. Ghi nhiều document tăng footprint

Một transaction sửa 100.000 documents:

~~~javascript
// Pseudocode ý tưởng, KHÔNG dùng trong một transaction khổng lồ.
for (const id of 100000Ids) {
  db.records.updateOne(
    { _id: id },
    { $set: { processed: true } }
  )
}
~~~

có thể tạo lượng thay đổi trong bộ nhớ lớn, nhiều index modifications, oplog work và khả năng tranh chấp với writer khác. Dù không có một giới hạn đơn giản “transaction tối đa X documents” áp dụng cho mọi phiên bản, **transaction quá rộng vẫn có thể bị lỗi và giảm throughput**.

### 7.3. Chi phí abort cũng tăng theo kích thước

Nếu một transaction lớn abort sau khi đã ghi rất nhiều thao tác chưa commit, server phải bỏ phần việc đó và ứng dụng có thể phải chạy lại. Một transaction 2 giây bị retry đôi khi chấp nhận được; một transaction 50 giây bị abort sau nhiều lần ghi có thể tạo tải nhân lên và ảnh hưởng SLO.

### 7.4. Tránh thao tác chậm bên trong transaction

Không đặt:

~~~javascript
// Ví dụ KHÔNG NÊN làm trong transaction callback:
await callExternalPaymentGateway();
await uploadBigFile();
await waitForUserApproval();
await slowRemoteHttpRequest();
await sleep(30000);
~~~

Các thao tác đó không nằm trong ranh giới commit MongoDB và có thể làm transaction giữ tài nguyên trong khi không thực hiện công việc database.

## 8. Giới hạn dung lượng 16 MiB: ba thứ rất dễ bị nhầm

### 8.1. Giới hạn một BSON document

MongoDB có giới hạn **16 MiB cho một BSON document**. Ví dụ một document order chứa mảng `items` hoặc payload quá lớn vẫn không hợp lệ dù được insert trong transaction:

~~~javascript
{
  _id: "order-too-big",
  items: [ /* dữ liệu khiến document vượt 16 MiB */ ]
}
~~~

**Transaction không làm tăng kích thước tối đa cho một document.** Nếu dữ liệu tự nhiên vượt giới hạn, hãy chia document, đưa dữ liệu lớn sang mô hình lưu khác hoặc dùng GridFS cho binary file theo use case phù hợp.

### 8.2. Giới hạn mỗi oplog entry

Oplog ghi nhận các thay đổi phục vụ replication. **Một BSON oplog entry có giới hạn kích thước liên quan tới giới hạn BSON 16 MiB.** Trong những phiên bản MongoDB hiện đại (từ 4.2), một transaction có nhiều thao tác có thể tạo **nhiều oplog entries**, thay vì buộc toàn bộ transaction vào **một oplog entry duy nhất** như cơ chế cũ.

Vì thế:

> Không đúng khi khẳng định “mọi multi-document transaction ở MongoDB hiện nay có giới hạn tổng 16 MiB”.

Hạn mức thực tế của transaction còn phụ thuộc bộ nhớ/cache, thời gian sống, số thao tác, oplog, khả năng ghi và phiên bản. Trong các môi trường MongoDB rất cũ, cách ghi oplog/giới hạn tổng từng khác; phải đối chiếu phiên bản nếu bảo trì cluster legacy.

### 8.3. Tổng byte của transaction vẫn không vô hạn

Giả sử transaction cập nhật 30.000 documents, mỗi document nhỏ. Tổng thay đổi có thể **lớn hơn 16 MiB** mà không nhất thiết vi phạm “một BSON document 16 MiB”. Nhưng transaction có thể vẫn thất bại vì:

- Cache không đủ giữ thay đổi/snapshot liên quan.
- Đã vượt thời gian sống.
- Write conflict hoặc lock timeout.
- Oplog/storage/network quá tải.
- Một document cụ thể vượt 16 MiB.
- Một command/request riêng có giới hạn BSON/message size.

**Đúng cách là đo và giới hạn đơn vị công việc**, không dùng 16 MiB tổng như một con số thiết kế duy nhất.

### 8.4. Bảng phân biệt

| Câu hỏi | Câu trả lời |
|---|---|
| Một document ghi trong transaction có thể lớn hơn 16 MiB? | **Không** theo giới hạn BSON document |
| Một transaction hiện đại chỉ có một oplog entry? | **Không nhất thiết**; có thể nhiều entries |
| Tổng ghi transaction lớn hơn 16 MiB luôn lỗi? | **Không**; phụ thuộc giới hạn khác |
| Tổng ghi 1 GiB trong một transaction luôn an toàn? | **Không**; áp lực cache, lifetime và tài nguyên rất lớn |
| Bật `allowDiskUse` có giải quyết giới hạn document? | **Không**; spill stage không nâng giới hạn BSON |
| Đổi write concern có tăng giới hạn BSON? | **Không**; đó là cơ chế xác nhận/độ bền |

## 9. WiredTiger cache và `TransactionTooLargeForCache`

Một transaction có tập thay đổi chưa commit quá lớn so với tài nguyên cache có thể gây áp lực lên WiredTiger và bị abort. MongoDB có những lỗi như `TransactionTooLargeForCache` trong các phiên bản tương ứng. Từ MongoDB 6.2, driver/server có thay đổi liên quan cách xử lý một transaction quá lớn so với cache: **không nên kỳ vọng retry tự động vô hạn sẽ giúp một transaction vốn vượt khả năng cache trở nên thành công**.

### 9.1. Phân biệt lỗi tạm thời và lỗi vì kích thước

Hai transaction có thể đều abort, nhưng:

~~~text
A: WriteConflict vì hai writer chạm một document
   -> Retry có backoff trên snapshot mới có thể thành công.

B: Cùng 200.000 updates khiến transaction quá lớn cho cache
   -> Retry y nguyên số updates có thể lại thất bại.
   -> Cần giảm batch, scope, document size hoặc đổi kiến trúc.
~~~

Không phân loại mọi lỗi transaction thành `TransientTransactionError` rồi thử lại mãi. Đọc error code, error labels và tài liệu phiên bản; với lỗi cấu trúc/tài nguyên, **chỉnh workload**.

### 9.2. Tại sao tăng cache không phải giải pháp duy nhất?

Tăng cache có thể giúp một số workload, nhưng:

- Transaction vẫn có giới hạn lifetime.
- Dataset lớn cần nhiều I/O và thời gian commit.
- Concurrent transactions cùng tăng footprint.
- Batch lớn có thể cản trở other workloads và recovery.
- Không loại được lỗi 16 MiB của document hoặc lệnh không hỗ trợ.

Ưu tiên transaction nhỏ, chỉ chạm tài liệu cần thiết, có index và thiết kế khả năng tiếp tục khi thất bại.

## 10. Lock contention và transaction bị abort sớm

MongoDB dùng cơ chế khóa ở nhiều mức và concurrency control của storage engine. Một transaction cập nhật các document đang bị transaction khác ghi có thể gặp write conflict; một số thao tác liên quan metadata/DDL có thể khiến transaction phải chờ lock.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant T1 as Transaction A
    participant DB as MongoDB
    participant T2 as Transaction B
    T1->>DB: Đọc rồi update wallet-A
    T2->>DB: Cố update wallet-A
    DB-->>T2: WriteConflict / transaction abort có thể xảy ra
    T1->>DB: commit
    DB-->>T1: Thành công
    Note over T2: Retry transaction mới, đọc lại state
~~~

### 10.1. Write conflict khác business conflict

~~~javascript
const result = db.wallets.updateOne(
  {
    _id: "wallet-A",
    balancePoints: { $gte: 150 }
  },
  {
    $inc: { balancePoints: -150 }
  }
)
~~~

Nếu `matchedCount = 0`, có thể do ví không tồn tại hoặc không đủ điểm. Đây là **kết quả lọc có điều kiện**, không nhất thiết là lỗi MongoDB `WriteConflict`.

Ngược lại, transaction bị abort với lỗi transient write conflict cần được retry đúng tầng, vì snapshot/điều kiện trước đó có thể đã cũ.

### 10.2. Thời gian chờ khóa khác thời gian ứng dụng chờ

Không có nghĩa transaction lifetime 60 giây thì mỗi lock cũng được chờ 60 giây. Lock timeout có cơ chế riêng và có thể ngắn hơn rất nhiều. Đừng tăng lock timeout chỉ để một DDL/batch transaction nặng hoàn thành bằng mọi giá; điều này có thể kéo dài downtime và tăng contention.

### 10.3. Index hỗ trợ transaction ngắn

~~~javascript
db.wallets.updateOne(
  { _id: "wallet-A", tenantId: "t-01" },
  { $inc: { balancePoints: -100 } }
)
~~~

Query theo `_id` dùng index mặc định, tìm nhanh document cần sửa. Nếu một transaction trước khi ghi phải scan hàng triệu document vì thiếu index, thời gian sống và tài nguyên transaction tăng mạnh.

**Tối ưu query trước khi tăng transaction timeout** là nguyên tắc có giá trị cao.

## 11. Những thao tác CRUD được hỗ trợ trong transaction

Trong điều kiện topology/phiên bản phù hợp, transaction hỗ trợ nhiều thao tác dữ liệu thông dụng:

| Nhóm | Ví dụ | Ghi chú |
|---|---|---|
| Read | `find`, `findOne`, aggregation read-only được hỗ trợ | Đọc theo session/read concern |
| Insert | `insertOne`, `insertMany` | Mỗi document vẫn chịu BSON limit; có thể bị duplicate key |
| Update | `updateOne`, `updateMany` | Cần điều kiện đúng và index phù hợp |
| Delete | `deleteOne`, `deleteMany` | Tập bị xóa lớn có thể tạo transaction quá lớn |
| Find-and-modify | `findOneAndUpdate`, `findOneAndDelete` | Hữu ích cho atomic conditional update |
| Bulk | Một số dạng `bulkWrite` | Phải dùng session đúng; tránh batch quá lớn |
| Aggregation | `$match`, `$group`, `$project`, `$lookup` và stage tương thích | Một số stage/namespace bị hạn chế, và pipeline có thể rất tốn tài nguyên |

### 11.1. Có thể dùng nhiều collection

~~~javascript
// Bên trong cùng transaction:
wallets.updateOne(/* trừ ví A */)
wallets.updateOne(/* cộng ví B */)
transfer_log.insertOne(/* ghi result */)
~~~

Đây là lý do chính để dùng multi-document transaction. Nhưng mỗi document bổ sung làm tăng phạm vi công việc và cơ hội tranh chấp.

### 11.2. Có thể dùng nhiều database, nhưng không vô điều kiện

MongoDB transaction có thể làm việc với nhiều collections/databases trong những trường hợp được hỗ trợ. Tuy nhiên, **admin/config/local namespaces, DDL, topology sharded và các lệnh đặc biệt có những hạn chế riêng**. Không suy ra rằng mọi namespace mà ứng dụng truy cập được ngoài transaction cũng có thể đọc/ghi tùy ý trong một transaction.

### 11.3. Không lạm dụng `updateMany` và `deleteMany`

~~~javascript
// Rủi ro nếu tập kết quả rất lớn:
db.events.updateMany(
  { expireAt: { $lt: new Date() } },
  { $set: { archived: true } }
)
~~~

Nếu đưa vào transaction lớn, thao tác có thể chạm rất nhiều document, vượt lifetime/cache budget. Với archival và cleanup, thường thích hợp hơn khi chạy **batch nhỏ có checkpoint** thay vì bao toàn bộ lịch sử trong một transaction.

## 12. Những lệnh và stage không được dùng trong transaction

Một số hoạt động không tương thích với transaction hoặc có giới hạn nghiêm ngặt. Danh sách dưới đây nhấn mạnh những nhóm quan trọng; **không thay thế bảng hỗ trợ chính thức theo server version**.

### 12.1. `$out` và `$merge`

Hai aggregation stages này ghi kết quả pipeline sang collection:

~~~javascript
// KHÔNG dùng như stage output trong transaction:
db.orders.aggregate([
  { $group: { _id: "$status", n: { $sum: 1 } } },
  { $out: "order_status_report" }
])
~~~

~~~javascript
// Cũng không dùng $merge trong transaction:
db.orders.aggregate([
  { $group: { _id: "$status", n: { $sum: 1 } } },
  {
    $merge: {
      into: "order_status_report",
      whenMatched: "merge",
      whenNotMatched: "insert"
    }
  }
])
~~~

`$out` và `$merge` **không được dùng trong aggregation pipeline bên trong multi-document transaction**. Nếu cần materialize báo cáo, hãy dùng pipeline ngoài transaction và thiết kế nhất quán/idempotency theo yêu cầu, hoặc tính toán trong transaction bằng các stage read-only được hỗ trợ rồi dùng lệnh ghi rõ ràng trên tập nhỏ.

### 12.2. `mapReduce`

Map-reduce command không hỗ trợ bên trong multi-document transaction. Với nhu cầu tổng hợp, ưu tiên aggregation pipeline được hỗ trợ; với job ETL nặng hãy chạy ngoài transaction hoặc dùng mô hình batch/checkpoint.

### 12.3. `count` command

Lệnh `count` cũ không được hỗ trợ trong transaction. Muốn đếm theo điều kiện, dùng aggregation tương thích:

~~~javascript
// Trong transaction, qua collection thuộc session:
txDb.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "n" }
])
~~~

`countDocuments()` của driver được triển khai qua aggregation và là lựa chọn hiện đại phù hợp với những điều kiện được hỗ trợ. Đừng nhầm `db.collection.count()` legacy với `countDocuments()` rồi giả định hai API giống nhau trong transaction.

### 12.4. `explain` và các lệnh chẩn đoán

Không kỳ vọng chạy `explain`/các lệnh quản trị như thể đang ở ngoài transaction. Ví dụ:

~~~javascript
// Không dùng explain như một phần business transaction.
db.orders.explain("executionStats").find({ status: "PAID" })
~~~

Để phân tích hiệu năng, chạy query/explain **ngoài transaction trong môi trường kiểm thử** với điều kiện đại diện. Không thực hiện DDL, serverStatus, replSet admin commands hoặc monitor/debug tools trong transaction body.

### 12.5. System collections và special namespaces

Các collections đặc biệt, đặc biệt trong `local`, `config`, `admin` hay system namespaces, có thể bị hạn chế đối với transaction. Đừng cố dùng transaction của ứng dụng để cập nhật metadata hệ thống hoặc sửa replica set configuration.

### 12.6. Capped collections

Write operations trên capped collections có những hạn chế trong transaction; **không dùng transaction đa document để ghi capped collection theo cách giả định tương đương collection thường**. Tùy phiên bản, đọc capped collection dưới snapshot cũng có thể có hạn chế. Nếu nghiệp vụ cần event log bền vững trong transaction, dùng collection thường với index/retention và outbox, không dùng capped như thay thế mặc định.

### 12.7. Change streams

Change stream là cơ chế **theo dõi các thay đổi đã commit** và hoạt động độc lập với transaction nghiệp vụ. Không tạo một change stream cursor trong transaction rồi cho rằng nó sẽ chờ các event của chính transaction chưa commit. Consumer change stream cần thiết kế resume token, checkpoint và dedupe bên ngoài transaction.

## 13. DDL trong transaction: tránh hai khẳng định cực đoan

Hai câu sau đều có thể sai:

1. “MongoDB không bao giờ cho phép tạo collection/index trong transaction.”
2. “Đã hỗ trợ transaction thì muốn tạo/drop/rename bất kỳ collection/index nào trong transaction cũng được.”

Kể từ MongoDB **4.4**, có những trường hợp được hỗ trợ để **tạo collection và index bên trong transaction**, với những điều kiện quan trọng. Tính năng này không biến mọi DDL thành hợp lệ và còn có giới hạn trên sharded cluster.

### 13.1. Cách thiết kế khuyến nghị

Với một luồng nghiệp vụ online:

~~~text
Deployment / migration:
  tạo collections
  tạo unique và supporting indexes
  kiểm tra schema validation

Runtime transaction:
  đọc/ghi trên collections đã tồn tại
  commit kết quả nghiệp vụ
~~~

Lợi ích:

- Tránh metadata locks/index build trong request transaction.
- Giảm bất ngờ do version/topology khác nhau.
- Dễ triển khai migration có review/rollback.
- Tránh để request đầu tiên là request “tạo collection”.

### 13.2. Khi thực sự cần tạo collection/index trong transaction

Cần kiểm tra:

- MongoDB server version và driver hỗ trợ.
- Transaction read concern và các yêu cầu riêng của thao tác DDL (một số trường hợp yêu cầu `local`).
- Collection/index có tồn tại chưa.
- Transaction có ghi cross-shard hay không.
- Lệnh cụ thể (create/index) có nằm trong danh sách cho phép không.
- Các lock và metadata operations đang diễn ra đồng thời.

Không dùng ví dụ:

~~~javascript
// Không coi đây là mẫu production phổ quát:
session.startTransaction()
db.createCollection("some_dynamic_collection")
db.some_dynamic_collection.createIndex({ arbitrary: 1 })
// ...
~~~

nếu chưa xác nhận toàn bộ điều kiện. Thực tế thường **tốt hơn pre-create schema** và không mở transaction dài trong lúc thao tác DDL.

### 13.3. Drop, rename, collMod và admin DDL

Không được suy ra từ việc hỗ trợ một số create/index rằng `dropCollection`, `renameCollection`, `collMod`, thay đổi shard key hoặc cấu hình replSet đều hợp lệ bên trong transaction. Những lệnh này có ràng buộc riêng và thường phải chạy qua quy trình migration/operation độc lập.

### 13.4. DDL đồng thời với transaction

Khi một transaction đang đọc/ghi collection mà admin bắt đầu tạo index hoặc thay metadata, các thao tác có thể phải chờ lock hoặc transaction gặp timeout/abort tùy thứ tự và phiên bản. Không nên chạy index build nặng cùng lúc với batch transactions quan trọng khi chưa có kế hoạch vận hành và monitoring.

## 14. Sharded transactions: giới hạn bổ sung

MongoDB hỗ trợ distributed transactions trên sharded cluster ở các phiên bản có tính năng phù hợp, nhưng chi phí lớn hơn transaction chỉ trên một shard/replica set.

### 14.1. Điều phối commit qua nhiều shard

~~~mermaid
flowchart TD
    App["Ứng dụng"] --> Router["mongos"]
    Router --> S1["Shard A: wallet-A"]
    Router --> S2["Shard B: wallet-B"]
    Router --> S3["Shard C: transfer_log"]
    S1 --> Coord["Điều phối commit phân tán"]
    S2 --> Coord
    S3 --> Coord
    Coord --> Outcome["Commit hoặc abort toàn giao dịch"]
~~~

Khi transaction chạm nhiều shard, có thêm công việc routing, điều phối commit, network, replication và xử lý failure. Điều này làm **thời gian và độ rủi ro timeout** tăng so với atomic update trên một document.

### 14.2. Không tạo collection tùy ý trong cross-shard write transaction

Một số thao tác tạo collection/index được hỗ trợ trong transaction có giới hạn riêng khi transaction ghi trên nhiều shard. Đặc biệt, cần xem các quy tắc **implicit collection creation** và **cross-shard write**. Không thiết kế runtime transaction vừa tạo một collection mới ở shard A vừa ghi collection khác ở shard B rồi mặc định sẽ chạy trên mọi deployment.

### 14.3. Chunk migration và metadata changes

Sharded cluster có thể đang cân bằng lại chunk hoặc thay metadata. Một transaction có thể tác động đến việc migration có thể tiến hành và ngược lại; một số tình huống thay đổi placement/chunk có thể dẫn tới transaction abort/retry. Cần:

- Giữ transaction ngắn.
- Dùng shard key trong filter khi thích hợp để tránh routing rộng.
- Tránh số lượng shards tham gia quá lớn.
- Có retry handling theo error labels.
- Đo thời gian commit và failures trên topology thật.

### 14.4. Read trong distributed transaction

Read concern `snapshot` có thể cung cấp snapshot nhất quán trong phạm vi transaction theo các điều kiện hỗ trợ. Tuy nhiên, không suy ra rằng mọi read preference thứ cấp hoặc mọi aggregation đặc thù đều được dùng được trong transaction; multi-document transaction thường yêu cầu **read preference primary** ở phía driver.

## 15. Read concern, write concern và transaction options

Ba lựa chọn chính:

~~~javascript
{
  readPreference: "primary",
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
}
~~~

### 15.1. `readPreference: primary`

Transactions phải tuân thủ yêu cầu đọc trên primary. Không đặt `secondary` để “chia tải các read trong transaction” rồi kỳ vọng session transaction vẫn hoạt động như mọi truy vấn read-only ngoài transaction.

### 15.2. `readConcern: snapshot`

Snapshot giúp các thao tác đọc trong transaction quan sát dữ liệu theo một điểm nhìn nhất quán trong điều kiện hỗ trợ. Nhưng snapshot không biến transaction thành một cơ chế serializable toàn phần cho mọi invariant phức tạp; write skew và quyết định dựa trên điều kiện tổng hợp vẫn cần thiết kế ràng buộc dữ liệu.

### 15.3. `writeConcern: majority` ở transaction commit

Write concern của transaction thường được chỉ định ở **cấp transaction/commit**, không phân tán tùy ý từng operation bên trong. Dùng majority khi cần cam kết độ bền qua failover theo semantics MongoDB. Majority acknowledgment có thể tốn thời gian hơn w:1 tùy tình trạng replication.

### 15.4. Chỉ thay read/write concern khi hiểu yêu cầu

Không giảm `w` hoặc chuyển `snapshot` sang `local` chỉ để một transaction đang lỗi timeout chạy được nếu nghiệp vụ cần độ bền/nhất quán cao. Tối ưu phải cân bằng correctness, throughput và SLO.

## 16. Session và thứ tự thao tác: không chạy song song vô điều kiện

Các thao tác của một transaction cần dùng **cùng session**. Trong Node.js Driver, **không được giả định chạy `Promise.all()` nhiều lệnh cùng transaction là an toàn/được hỗ trợ**.

Không nên:

~~~javascript
await session.withTransaction(async () => {
  await Promise.all([
    wallets.updateOne(filterA, updateA, { session }),
    wallets.updateOne(filterB, updateB, { session })
  ]);
});
~~~

Driver Node.js không hỗ trợ parallel operations bên trong một transaction theo cách trên. Không dùng cùng session đồng thời cho hai transaction độc lập.

Nên chạy theo trình tự được kiểm soát:

~~~javascript
await session.withTransaction(async () => {
  const a = await wallets.updateOne(filterA, updateA, { session });
  if (a.matchedCount !== 1) throw new Error("SOURCE_NOT_FOUND");

  const b = await wallets.updateOne(filterB, updateB, { session });
  if (b.matchedCount !== 1) throw new Error("DEST_NOT_FOUND");
});
~~~

### 16.1. Cursor phải được quản lý trong transaction

Nếu đọc nhiều documents qua cursor, thực hiện các thao tác cursor trong thời gian session/transaction còn hợp lệ. Không return một cursor chưa được tiêu thụ rồi đóng session/commit và kỳ vọng tiếp tục đọc với snapshot transaction cũ vô hạn.

### 16.2. Không dùng session ngoài đời sống đã kết thúc

Driver session có lifecycle. Một transaction đã commit/abort không thể tiếp tục thực hiện thao tác như đang ở cùng snapshot. Trong helper như `withTransaction()`, callback có thể chạy lại trong một attempt mới; mọi biến trạng thái phụ thuộc snapshot phải được đọc/tính lại trong callback.

### 16.3. Phạm vi một transaction nên rõ ràng

Một transaction dành cho **một intent nghiệp vụ** dễ hiểu và dễ retry hơn một transaction gom hàng nghìn intent không liên quan chỉ để “giảm số commit”.

## 17. Ví dụ mongosh: commit/abort một chuyển điểm

Giả sử đã chạy setup ở mục 4. Tạo session:

~~~javascript
const session = db.getMongo().startSession()
const txDb = session.getDatabase("txn_limits_lab")

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  const amount = 150
  const debit = txDb.wallets.updateOne(
    {
      _id: "wallet-A",
      tenantId: "t-01",
      balancePoints: { $gte: amount }
    },
    {
      $inc: { balancePoints: -amount, version: 1 }
    }
  )

  if (debit.matchedCount !== 1) {
    throw new Error("INSUFFICIENT_POINTS_OR_WALLET_MISSING")
  }

  const credit = txDb.wallets.updateOne(
    {
      _id: "wallet-B",
      tenantId: "t-01"
    },
    {
      $inc: { balancePoints: amount, version: 1 }
    }
  )

  if (credit.matchedCount !== 1) {
    throw new Error("DESTINATION_WALLET_MISSING")
  }

  txDb.transfer_log.insertOne({
    tenantId: "t-01",
    requestId: "transfer-R1",
    from: "wallet-A",
    to: "wallet-B",
    amountPoints: amount,
    state: "COMPLETED",
    createdAt: new Date()
  })

  session.commitTransaction()
  print("COMMITTED")
} catch (e) {
  print("TRANSACTION ERROR: " + e.message)
  try { session.abortTransaction() } catch (_) {}
} finally {
  session.endSession()
}
~~~

Nếu commit thành công:

~~~text
wallet-A: 1000 -> 850
wallet-B:  200 -> 350
transfer_log: thêm bản ghi transfer-R1
~~~

### 17.1. Chạy lại nguyên transaction không phải một lần retry an toàn

Trong ví dụ, unique index trên `{tenantId,requestId}` sẽ chặn insert trùng `transfer-R1`. Nếu gọi lại không có bước kiểm tra ledger trước, transaction có thể fail duplicate key. Dù cuối cùng không commit lần hai, API vẫn cần **replay kết quả cũ** hoặc báo conflict thích hợp. Một thiết kế production nên tra cứu request ledger trước, so khớp fingerprint và trả result đã commit.

### 17.2. Tại sao cần catch abort?

Nếu transaction lỗi giữa chừng, bạn phải đóng/abort transaction đúng quy trình. Nhưng trong trường hợp **commit outcome chưa rõ** do mạng, không tự coi mọi exception là bằng chứng chưa commit; có thể cần retry commit hoặc reconcile bằng requestId. Đoạn mongosh này minh họa commit/abort cơ bản, **không phải implementation đầy đủ cho unknown commit**.

### 17.3. Kiểm tra kết quả **sau** transaction

~~~javascript
db.wallets.find().sort({ _id: 1 })
db.transfer_log.find({ requestId: "transfer-R1" })
~~~

Với mức read/write concern và topology thích hợp, quan sát kết quả từ nguồn đáng tin cậy theo yêu cầu nghiệp vụ. Nếu client vừa mất phản hồi commit, phải áp dụng quy tắc reconciliation, không lập tức chuyển thêm một lần với requestId mới.

## 18. Node.js Driver: transaction ngắn với helper

Ví dụ dùng driver hiện đại, replica set/sharded cluster có transaction support:

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI, {
  serverSelectionTimeoutMS: 5000
});

await client.connect();

const database = client.db("txn_limits_lab");
const wallets = database.collection("wallets");
const transfers = database.collection("transfer_log");

async function transferPoints({
  tenantId, requestId, sourceId, destinationId, amountPoints
}) {
  if (!tenantId || !requestId ||
      !sourceId || !destinationId || sourceId === destinationId ||
      !Number.isSafeInteger(amountPoints) || amountPoints <= 0) {
    throw new Error("INVALID_TRANSFER");
  }

  const session = client.startSession();

  try {
    return await session.withTransaction(async () => {
      // Callback có thể được driver chạy lại trên transient error.
      // Không gọi HTTP/payment/email ở đây.
      const previous = await transfers.findOne(
        { tenantId, requestId },
        { session }
      );

      if (previous) {
        if (previous.from !== sourceId ||
            previous.to !== destinationId ||
            previous.amountPoints !== amountPoints) {
          throw new Error("IDEMPOTENCY_KEY_REUSED");
        }
        return {
          ok: true,
          requestId,
          replayed: true
        };
      }

      // Có conditional filter để tránh số dư âm.
      const debit = await wallets.updateOne(
        {
          _id: sourceId,
          tenantId,
          balancePoints: { $gte: amountPoints }
        },
        { $inc: { balancePoints: -amountPoints, version: 1 } },
        { session }
      );

      if (debit.matchedCount !== 1) {
        throw new Error("INSUFFICIENT_POINTS_OR_SOURCE_MISSING");
      }

      const credit = await wallets.updateOne(
        { _id: destinationId, tenantId },
        { $inc: { balancePoints: amountPoints, version: 1 } },
        { session }
      );

      if (credit.matchedCount !== 1) {
        throw new Error("DESTINATION_MISSING");
      }

      await transfers.insertOne({
        tenantId,
        requestId,
        from: sourceId,
        to: destinationId,
        amountPoints,
        state: "COMPLETED",
        createdAt: new Date()
      }, { session });

      return {
        ok: true,
        requestId,
        replayed: false
      };
    }, {
      readPreference: "primary",
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      maxCommitTimeMS: 10000
    });
  } finally {
    await session.endSession();
  }
}

// Gọi từ API chỉ sau khi kiểm tra authorization:
// await transferPoints({
//   tenantId: "t-01",
//   requestId: "transfer-R2",
//   sourceId: "wallet-A",
//   destinationId: "wallet-B",
//   amountPoints: 100
// });

// Đóng client khi application shutdown:
// await client.close();
~~~

### 18.1. Điều helper có thể làm

`withTransaction()` điều phối start/commit/abort và một số retry theo error labels do MongoDB Driver specification quy định. Callback transaction **có thể bị gọi lại** khi gặp lỗi transient. Đừng giữ side effect không thể rollback trong callback.

### 18.2. Điều helper không tự giải quyết

- Không mở rộng lifetime transaction vô hạn.
- Không làm một transaction quá lớn vừa cache.
- Không cho phép commands bị cấm hoạt động.
- Không làm hai lần gửi HTTP với requestId khác nhau trở thành một intent.
- Không bảo đảm hai business requests concurrent cùng key sẽ luôn trả cùng response ở attempt đầu; có thể có duplicate key/write conflict cần xử lý ngoài helper.
- Không tự phục hồi từ mọi lỗi permanent.

**Đoạn code này là khung học tập.** Production cần xử lý duplicate-key collision theo unique index cụ thể, fingerprint được canonicalize, unknown commit outcome, retry budget, response replay, request authorization, monitoring và lifecycle của session. Không dùng trong hệ thống tiền thật nếu chưa thiết kế/kiểm thử các tình huống đó.

### 18.3. Transaction không phải chỗ giữ logic tính toán lâu

Nếu tính phí/định tuyến cần gọi API bên ngoài, thực hiện trước transaction khi có thể; nhưng phải biết dữ liệu có thể thay đổi giữa tính toán và commit. Trong transaction, kiểm tra **điều kiện cuối cùng** một lần nữa bằng update có điều kiện hoặc version.

## 19. `TransientTransactionError` và retry **toàn transaction**

Trong môi trường cạnh tranh, transaction có thể bị abort với error label `TransientTransactionError`. Đối với những lỗi này, cách xử lý thường là:

1. Abort/để helper abort attempt hiện tại.
2. Tạo một attempt transaction mới.
3. **Đọc lại dữ liệu và điều kiện**.
4. Thực hiện lại các ghi MongoDB thuộc transaction.
5. Commit với timeout/budget hợp lý.

Không chỉ retry lệnh update cuối và giữ snapshot cũ khi toàn transaction đã bị abort.

### 19.1. Lỗi transient không làm quyết định nghiệp vụ cố định

~~~text
Attempt 1:
  Đọc balance = 100
  Định chuyển 80
  -> Write conflict, transaction abort

Attempt 2:
  Đọc balance mới = 50
  -> Không đủ điểm, trả business rejection
~~~

Đây là đúng về mặt concurrency. Không được nhớ “attempt 1 đủ tiền” rồi bỏ điều kiện trong attempt 2.

### 19.2. Transaction lớn retry quá nhiều lần có thể khuếch đại tải

Nếu một transaction mất 20 giây và thường phải retry ba lần, một request có thể giữ tài nguyên đáng kể và vượt API deadline. Giảm phạm vi transaction và contention thường có lợi hơn tăng số retry.

### 19.3. Một số lỗi không nên retry nguyên vẹn

- Validation lỗi.
- Duplicate key từ business unique constraint không được giải quyết.
- Collection/namespace command không hỗ trợ trong transaction.
- Transaction quá lớn cho cache.
- Document BSON vượt 16 MiB.
- Tính toán cần dữ liệu mới nhưng điều kiện nghiệp vụ không còn thỏa.

Khi lỗi có nhãn/codes riêng theo phiên bản, dùng **đúng hợp đồng của driver và server**. Không quyết định chỉ dựa vào chuỗi text chứa “transaction aborted”.

## 20. `UnknownTransactionCommitResult`: kết quả commit chưa rõ

Lỗi `UnknownTransactionCommitResult` đặc biệt quan trọng vì transaction **có thể đã commit**:

~~~mermaid
sequenceDiagram
    participant API as Application
    participant DB as MongoDB
    API->>DB: commitTransaction
    DB->>DB: Commit thành công
    DB--xAPI: Mất phản hồi
    Note over API: Không biết đã commit hay chưa
    API->>DB: Retry commit / tra cứu request ledger
    DB-->>API: Outcome được xác định hoặc tiếp tục cần reconcile
~~~

### 20.1. Không bắt đầu business transaction khác ngay

Sai:

~~~text
Commit R1 timeout
=> API tạo requestId R2
=> Chuyển tiền lại
~~~

Đúng hơn:

~~~text
Commit R1 timeout
=> Driver retry commit của attempt thích hợp nếu còn context
=> Nếu vẫn chưa rõ, đọc/reconcile ledger R1
=> Client retry cùng requestId R1
=> Không tự gửi giao dịch mới với R2
~~~

### 20.2. Vì sao unique request ID giúp được?

Nếu transaction ghi `transfer_log` cùng cập nhật hai ví, khi đọc thấy bản ghi `requestId = R1` đã commit và payload khớp, có bằng chứng business effect đã được áp dụng trong commit đó. Nếu chưa thấy bản ghi ngay do read preference/consistency, **không tự suy ra chắc chắn transaction chưa commit**; cần đọc/retry/reconcile theo chính sách.

### 20.3. Retry budget

Retry commit và retry transaction cần **giới hạn** để không tạo vòng lặp vô hạn khi database đang suy giảm. Khi hết deadline, API có thể trả trạng thái PENDING/UNKNOWN kèm requestId và endpoint tra cứu trạng thái thay vì xác nhận sai thành công/thất bại.

## 21. Transaction và external side effects

Mẫu không nên:

~~~javascript
await session.withTransaction(async () => {
  await inventory.updateOne(..., { session });
  await sendEmail("Đặt hàng thành công");
  await chargeExternalCard(...);
});
~~~

Vì:

1. Email/payment không được MongoDB transaction rollback.
2. Callback có thể bị retry, khiến email/payment chạy hai lần.
3. Network call có thể kéo dài transaction tới giới hạn lifetime.
4. Timeout external call có thể tạo trạng thái không chắc chắn cả ngoài DB lẫn trong DB.

### 21.1. Transactional outbox

Trong cùng transaction MongoDB, ghi:

~~~javascript
// Pseudocode: các thao tác phải có cùng session.
await inventory.updateOne(/* business update */, { session });
await orders.insertOne(/* order */, { session });
await outbox.insertOne({
  _id: "event-order-101",
  type: "OrderCreated",
  orderId: "order-101",
  state: "PENDING",
  createdAt: new Date()
}, { session });
~~~

Sau commit, một worker đọc outbox và phát event tới broker. Relay vẫn có thể publish lại sau crash, nên consumer phải dedupe theo event ID ổn định.

### 21.2. Không giữ transaction mở chờ người dùng

Nếu workflow cần duyệt khoản vay, kiểm tra giấy tờ, thanh toán ngoài hệ thống hoặc chờ người dùng xác nhận, dùng **state machine/saga**:

~~~text
PENDING_APPROVAL
  -> APPROVED
  -> PAYMENT_REQUESTED
  -> PAYMENT_CONFIRMED
  -> COMPLETED
~~~

Mỗi bước có transaction ngắn để lưu state/ledger/outbox phù hợp, không duy trì một MongoDB transaction xuyên nhiều phút hoặc giờ.

## 22. Khi batch lớn: chia thành nhiều transaction có checkpoint

Ví dụ phải cập nhật trạng thái 2 triệu records:

~~~javascript
// Không đưa cả 2 triệu records vào một transaction.
db.records.updateMany(
  { jobId: "recalc-2026" },
  { $set: { processed: true } }
)
~~~

Nếu mọi thay đổi phải commit cùng một lần, transaction khổng lồ có thể bất khả thi do lifetime/cache. Trước hết, hãy hỏi lại **yêu cầu atomicity thật sự**:

- Có cần “2 triệu records cùng nhìn thấy trạng thái mới trong một thời điểm” không?
- Hay chỉ cần **job hoàn tất đúng, có thể chạy lại, không bỏ sót/không xử lý trùng**?
- Có thể dùng một **version/cutover flag** sau khi dữ liệu đã được chuẩn bị chưa?

### 22.1. Phân lô với checkpoint

Mô hình:

~~~mermaid
flowchart TD
    Job["Job 2 triệu records"] --> Read["Đọc batch 500 IDs"]
    Read --> Tx["Transaction ngắn: update batch + checkpoint"]
    Tx --> Done{"Còn records?"}
    Done -->|Có| Read
    Done -->|Không| Final["Đánh dấu job COMPLETED / cutover"]
~~~

Giả mã:

~~~javascript
// Pseudocode, minh họa kiến trúc, không phải script tự chạy.
while (true) {
  const ids = await loadNextBatchAfterCheckpoint(jobId, 500);
  if (ids.length === 0) break;

  await withShortTransaction(async (session) => {
    await updateRecordsByIds(ids, { session });
    await saveCheckpoint(jobId, ids[ids.length - 1], { session });
  });
}
await markJobCompleted(jobId);
~~~

Với cách này:

- Mỗi transaction có **tập ghi có giới hạn**.
- Checkpoint và thay đổi batch commit cùng nhau.
- Sau crash, job có thể tiếp tục từ checkpoint.
- Update phải idempotent hoặc có bảo vệ để không tính lặp.
- Không có atomicity cho **toàn 2 triệu records cùng lúc**; cần công bố semantics.

### 22.2. Chọn batch size theo dữ liệu thực

Không có “batch 500 luôn đúng”. Kích thước phù hợp phụ thuộc:

- Document size và số index bị cập nhật.
- Số shard tham gia.
- Write conflict rate.
- Transaction duration p95/p99.
- Cache/disk/CPU và replication health.
- Độ quan trọng của transaction khác trên cùng collection.

Hãy bắt đầu nhỏ, đo thực tế, tăng dần trong điều kiện an toàn. Không tăng batch size tới sát lifetime và cache threshold.

### 22.3. Cần atomic cutover?

Ví dụ thay bảng giá có 100.000 sản phẩm. Thay vì cập nhật từng giá đang active trong một transaction khổng lồ:

1. Ghi bảng giá mới dưới `priceVersion: "v2"`.
2. Kiểm tra đầy đủ dữ liệu v2 và index.
3. Commit một thay đổi nhỏ vào document cấu hình `activePriceVersion = "v2"`.
4. Reader dùng active version để truy vấn.

Đây là **versioned read model + atomic pointer switch**, có thể giải bài toán “người đọc thấy phiên bản hoàn chỉnh” mà không cần một transaction trên toàn bộ documents. Cần thiết kế consistency, cache invalidation và migration/rollback phù hợp.

## 23. Vì sao transaction không thay thế unique constraints và data model?

Một transaction có snapshot nhất quán không tự làm mọi điều kiện **toàn cục** thành invariant.

Ví dụ hệ thống cho phép tối đa một coupon active trên mỗi `tenantId + campaignId`. Nếu hai transaction cùng đọc “chưa có coupon active” rồi insert hai document khác nhau, nếu không có unique constraint phù hợp, có thể phát sinh lỗi kiểu **write skew** tùy mô hình và lịch thực thi.

Giải pháp mạnh hơn:

~~~javascript
db.coupons.createIndex(
  { tenantId: 1, campaignId: 1 },
  {
    unique: true,
    partialFilterExpression: { status: "ACTIVE" },
    name: "uq_active_coupon_per_campaign"
  }
)
~~~

Index này phải tạo **bên ngoài transaction runtime** và cần kiểm tra dữ liệu hiện có/điều kiện partial index. Unique constraint giúp chặn hai bản ghi active trùng key ngay cả khi hai writer cạnh tranh.

### 23.1. Snapshot isolation không đồng nghĩa mọi nghiệp vụ đều serializable

Ví dụ hai bác sĩ cùng kiểm tra “còn ít nhất một bác sĩ trực” rồi mỗi người tự bỏ ca trên **hai document khác nhau**. Nếu chỉ đọc tổng số và cập nhật document của mình, hệ thống có thể vi phạm invariant “luôn có bác sĩ trực” dù mỗi transaction thấy snapshot hợp lệ. Cần thiết kế invariant bằng một record chung có atomic conditional update, unique/constraint phù hợp, hoặc mô hình coordination khác.

### 23.2. Dữ liệu có giới hạn rõ giúp transaction nhỏ

Nếu một order nhúng danh sách items nhỏ, toàn bộ thay đổi có thể nằm trong một document. Nếu tách vô số dòng và lịch sử ghi bất biến, không nên tạo một transaction chạm toàn bộ lịch sử khi cập nhật trạng thái order.

## 24. Thực hành xử lý lỗi: không retry mọi exception

Một bảng phản ứng:

| Tình huống | Hậu quả thường gặp | Phản ứng |
|---|---|---|
| `TransientTransactionError` | Attempt transaction có thể abort do lỗi tạm thời | Retry **cả transaction** theo driver/helper với ngân sách |
| `UnknownTransactionCommitResult` | Chưa biết commit đã thành công | Retry **commit** hoặc reconcile bằng request identity |
| `TransactionTooLargeForCache` | Transaction quá lớn cho cache | Giảm scope/batch hoặc đổi kiến trúc, không retry y nguyên vô hạn |
| Transaction lifetime exceeded | Transaction hết thời gian sống | Thu ngắn công việc, review timeout; không tăng server limit mù |
| Lock timeout | Không lấy được lock | Giảm contention/DDL overlap; retry có backoff nếu transient phù hợp |
| `DuplicateKey` | Vi phạm unique index | Đối chiếu business/idempotency key; không coi là transient chung |
| BSON document quá lớn | Một document vượt 16 MiB | Đổi schema/payload, không giải quyết bằng retry |
| Unsupported command/stage | Operation không được phép trong transaction | Chuyển stage/DDL ngoài transaction hoặc đổi giải pháp |
| Validation error | Dữ liệu không hợp lệ | Sửa dữ liệu, không retry cùng payload |
| Application deadline | Client đã hết ngân sách | Hủy/abort nếu còn an toàn; nếu commit uncertain thì reconcile |

### 24.1. Không coi mọi timeout là rollback

Một lỗi network xảy ra **trước commit** thường khác với lỗi mất phản hồi **sau khi commit có thể thành công**. Driver error labels có thể hướng dẫn retry đúng cách; đồng thời ứng dụng cần lưu requestId/ledger để xác định business outcome.

### 24.2. Retry limit và backoff

Pseudocode:

~~~javascript
// Pseudocode minh họa cho tầng orchestration khi chưa có helper
// xử lý các retry tương ứng. Không bọc helper tự retry vô hạn.
async function runWithBudget(operation, maxAttempts = 4) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await operation();
    } catch (error) {
      const transient =
        error.hasErrorLabel?.("TransientTransactionError");

      if (!transient || attempt === maxAttempts - 1) {
        throw error;
      }

      const base = Math.min(1000, 25 * (2 ** attempt));
      const jitter = 0.5 + Math.random();
      await new Promise(resolve =>
        setTimeout(resolve, Math.floor(base * jitter))
      );
    }
  }
}
~~~

Đừng áp dụng nguyên hàm này cho `UnknownTransactionCommitResult` rồi chạy lại **business operation** như một transaction mới. Khi outcome commit chưa rõ, cần retry commit theo giao thức hoặc reconcile, không coi là transient body.

## 25. Monitor transaction trong server và ứng dụng

Một query transaction có thể thất bại vì thời gian/tài nguyên trước khi API có đủ thông tin. Cần instrumentation ở cả server và application.

### 25.1. `serverStatus().transactions`

Khi có quyền:

~~~javascript
const stats = db.serverStatus()
printjson(stats.transactions)
~~~

Các trường cụ thể tùy phiên bản, nhưng những thống kê hữu ích có thể gồm transaction đang hoạt động, đang mở, commit/abort và số lượng liên quan. Không viết dashboard phụ thuộc cứng vào mọi field của một phiên bản khi triển khai đa môi trường.

### 25.2. `currentOp` và profiler/logs

Trong môi trường có quyền, có thể quan sát operations/session đang chạy, thời gian, lock waits và các thuộc tính tương ứng bằng công cụ như `currentOp` hoặc profiler/diagnostic logs. Việc truy vấn công cụ quản trị phải thực hiện **ngoài transaction nghiệp vụ**.

### 25.3. Chỉ số ứng dụng nên đo

| Metric | Ý nghĩa |
|---|---|
| `txn_duration_ms_p50/p95/p99` | Transaction sống bao lâu |
| `txn_attempts_per_business_request` | Một intent cần bao nhiêu attempt |
| `txn_commit_latency_ms` | Thời gian bước commit |
| `txn_abort_count_by_error_code` | Nguyên nhân abort |
| `transient_retry_count` | Mức contention/lỗi tạm thời |
| `unknown_commit_count` | Mức kết quả commit chưa rõ |
| `txn_docs_modified` | Phạm vi ghi |
| `txn_bytes_changed_estimate` | Quy mô thao tác/footprint gần đúng |
| `lock_wait_ms` | Cạnh tranh lock |
| `cache_pressure`, `eviction` | Tải WiredTiger |
| `replication_lag`, `majority_commit_latency` | Tác động độ bền/failover |
| `idempotency_replay_count` | Retry API được nhận diện |

Đây là tên **metric đề xuất của hệ thống**, không phải toàn bộ metric có sẵn nguyên tên trong MongoDB. Một số cần tổng hợp từ driver instrumentation và application logs.

### 25.4. Log session an toàn

Một log có thể chứa:

~~~text
traceId=...
tenantId=t-01
businessRequestId=transfer-R2
attempt=2
transactionDurationMs=...
commitOutcome=COMMITTED|ABORTED|UNKNOWN
errorCode=...
errorLabels=[...]
documentsModified=...
~~~

Không log mật khẩu, connection string đầy đủ hoặc payload tài chính nhạy cảm. Sử dụng ID ổn định để nối kết các attempt và truy vấn reconciliation.

## 26. Thử giới hạn thời gian trong lab

**Chỉ chạy trên replica set lab**; không cố tạo transaction timeout để đo bằng cách giữ một transaction thật trên production.

### 26.1. Quan sát server parameter

~~~javascript
db.adminCommand({
  getParameter: 1,
  transactionLifetimeLimitSeconds: 1
})
~~~

Ghi lại giá trị thực tế. Nếu là 60, nó là ngưỡng lifetime mặc định phổ biến. Không sửa tham số để “demo lỗi” trên môi trường dùng chung.

### 26.2. Transaction ngắn

~~~javascript
const s = db.getMongo().startSession()
const d = s.getDatabase("txn_limits_lab")

try {
  s.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  d.wallets.findOne({ _id: "wallet-A" })
  d.wallets.updateOne(
    { _id: "wallet-A" },
    { $inc: { version: 1 } }
  )

  s.commitTransaction()
  print("COMMITTED")
} catch (err) {
  print(err.message)
  try { s.abortTransaction() } catch (_) {}
} finally {
  s.endSession()
}
~~~

### 26.3. Quan sát transaction sống lâu

Để hiểu ngưỡng lifetime, trong **lab độc lập**, bạn có thể start transaction, thực hiện một thao tác đọc/ghi, đợi lâu hơn ngưỡng server theo cách có kiểm soát rồi thử commit. Có thể nhận lỗi transaction đã abort/không còn active, nhưng **không bắt buộc mã lỗi giống nhau ở mọi phiên bản**.

Đừng chèn `sleep` dài vào callback có external side effect. Nếu thử với mongosh, cần chắc session được abort/end trong mọi nhánh sau khi quan sát. Bài học quan trọng không phải “ép commit thất bại chính xác tại giây 60”, mà là **transaction sống lâu không phải cơ chế xử lý batch dài**.

## 27. Thử giới hạn thao tác bị hạn chế

### 27.1. `$out` trong transaction

Trên database lab, có thể thử bằng session:

~~~javascript
const s = db.getMongo().startSession()
const d = s.getDatabase("txn_limits_lab")

try {
  s.startTransaction()

  // Stage $out không được hỗ trợ trong transaction.
  d.wallets.aggregate([
    { $group: { _id: "$tenantId", n: { $sum: 1 } } },
    { $out: "wallet_summary" }
  ]).toArray()

  s.commitTransaction()
} catch (e) {
  printjson({
    code: e.code,
    codeName: e.codeName,
    message: e.message
  })
  try { s.abortTransaction() } catch (_) {}
} finally {
  s.endSession()
}
~~~

Kỳ vọng một lỗi unsupported/incompatible operation theo server version. Thao tác này **không được dùng như giải pháp production**; dùng ngoài transaction để tạo báo cáo và có cơ chế version/cutover nếu cần.

### 27.2. Thay bằng aggregation read-only

~~~javascript
const s = db.getMongo().startSession()
const d = s.getDatabase("txn_limits_lab")

try {
  s.startTransaction()

  const summary = d.wallets.aggregate([
    { $group: { _id: "$tenantId", wallets: { $sum: 1 } } }
  ]).toArray()

  printjson(summary)
  s.commitTransaction()
} catch (e) {
  print(e.message)
  try { s.abortTransaction() } catch (_) {}
} finally {
  s.endSession()
}
~~~

`$group` read-only có thể được hỗ trợ trong transaction, nhưng không nên dùng transaction chỉ để chạy một aggregation báo cáo dài nếu không có nhu cầu atomic multi-document workflow.

### 27.3. Thử `countDocuments()`

Trong Node.js Driver, thử:

~~~javascript
const total = await wallets.countDocuments(
  { tenantId: "t-01" },
  { session }
);
~~~

trong callback transaction hợp lệ, thay vì gọi lệnh `count` legacy. Nếu đếm hàng triệu documents để quyết định ghi, cần index và cân nhắc snapshot/invariant; count rất lớn có thể làm transaction sống quá lâu.

## 28. Thử cạnh tranh write conflict trong lab

Hai phiên mongosh kết nối tới replica set lab, cùng sửa `wallet-A`:

### Phiên A

~~~javascript
use txn_limits_lab

const sessionA = db.getMongo().startSession()
const txA = sessionA.getDatabase("txn_limits_lab")
sessionA.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

printjson(txA.wallets.findOne({ _id: "wallet-A" }))

txA.wallets.updateOne(
  { _id: "wallet-A" },
  { $inc: { version: 1 } }
)

// Chưa commit ngay; chuyển sang phiên B.
~~~

### Phiên B trong khi A còn mở

~~~javascript
use txn_limits_lab

const sessionB = db.getMongo().startSession()
const txB = sessionB.getDatabase("txn_limits_lab")
sessionB.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

try {
  printjson(txB.wallets.findOne({ _id: "wallet-A" }))
  printjson(txB.wallets.updateOne(
    { _id: "wallet-A" },
    { $inc: { version: 1 } }
  ))
} catch (e) {
  printjson({
    code: e.code,
    codeName: e.codeName,
    errorLabels: e.errorLabels,
    message: e.message
  })
  try { sessionB.abortTransaction() } catch (_) {}
}
~~~

### Kết thúc phiên A và B

~~~javascript
// Phiên A:
try {
  sessionA.commitTransaction()
} finally {
  sessionA.endSession()
}

// Phiên B, chỉ trong phiên B:
try { sessionB.abortTransaction() } catch (_) {}
sessionB.endSession()
~~~

Khi hai transaction chồng lấn, B có thể nhận lỗi write conflict/transient và bị abort. **Không đảm bảo lần thử nào cũng tạo cùng code/label**, vì timing và locking thay đổi. Nếu transaction B đã bị abort, không thể “commit tiếp” snapshot cũ; cần transaction mới và đọc lại document.

## 29. Khi nào nên dùng transaction, khi nào nên chọn mô hình khác?

| Trường hợp | Phương án ưu tiên | Lý do |
|---|---|---|
| Giảm stock một SKU trong một document | Conditional atomic `updateOne` | Invariant nằm trong một document, chi phí thấp |
| Chuyển điểm giữa hai ví và lưu ledger | Multi-document transaction ngắn | Nhiều document phải commit/abort cùng nhau |
| Đổi status một order và ghi outbox | Transaction ngắn | Atomic giữa business state và event metadata |
| Import hàng triệu records | Batch có checkpoint | Transaction khổng lồ dễ timeout/cache |
| Xuất báo cáo bằng `$out`/`$merge` | Job ngoài transaction | Stage không được phép trong transaction |
| Thay bảng giá toàn hệ thống | Versioned data + atomic pointer cutover | Tránh transaction cập nhật toàn bộ dữ liệu |
| Workflow cần duyệt nhiều giờ | Saga/state machine | Không giữ transaction trong thời gian chờ |
| Thanh toán qua provider ngoài | Provider idempotency + outbox/reconciliation | Transaction MongoDB không rollback network call |
| Hàng nghìn writers tranh một counter | Xem shard counter/bucket hay giảm contention | Transaction/retry không giải quyết hot key tận gốc |
| Thay schema/index | Migration ngoài transaction runtime | Tránh DDL lock và version restrictions |

## 30. Bài tập tổng hợp

### Bài A — Chọn transaction hay atomic update

Với ba nhiệm vụ:

1. Trừ một đơn vị tồn kho trong cùng document `inventory`.
2. Trừ ví A, cộng ví B và ghi log.
3. Cập nhật 800.000 sản phẩm để thêm field `searchVersion`.

Chọn giải pháp phù hợp và giải thích trade-off.

### Bài B — 60 giây có nghĩa gì?

Một transaction bắt đầu lúc 10:00:00, gọi API đối tác 50 giây, rồi update 3 documents thêm 20 giây. Vì sao transaction có thể bị abort? Nên đặt API call ở đâu?

### Bài C — Phân biệt timeout

Giải thích sự khác nhau giữa:

- `transactionLifetimeLimitSeconds`
- `maxCommitTimeMS`
- `serverSelectionTimeoutMS`
- `maxTransactionLockRequestTimeoutMillis`

Cái nào quyết định driver có tìm thấy primary? Cái nào liên quan transaction sống quá lâu?

### Bài D — “Transaction chỉ tối đa 16 MB”

Đánh giá câu khẳng định này. Một transaction sửa 10.000 documents nhỏ có tổng thay đổi lớn hơn 16 MiB có luôn bị từ chối không? Những giới hạn thực sự nào cần tính?

### Bài E — Một document quá lớn

Một order document nhúng 20.000 items và tạo BSON hơn 16 MiB. Đưa insert vào transaction có giải quyết được không? Nêu hai phương án data modeling.

### Bài F — Cache

Một transaction có 200.000 updates, mỗi attempt thất bại do `TransactionTooLargeForCache`. Tăng retry lên 100 lần có hợp lý không? Đề xuất batch/checkpoint.

### Bài G — Lệnh bị hạn chế

Cho:

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$status", n: { $sum: 1 } } },
  { $merge: { into: "daily_status" } }
])
~~~

Có nên đặt trong transaction không? Nếu yêu cầu báo cáo được materialize nhất quán, làm cách nào khác?

### Bài H — Index creation

Ứng dụng muốn mỗi tenant tạo collection mới trong request transaction. Vì sao cần kiểm tra phiên bản, sharding, DDL restrictions? Tại sao pre-create schema thường dễ vận hành hơn?

### Bài I — Transaction retry

Hai transaction cùng sửa `wallet-A`; một attempt nhận `TransientTransactionError`. Nên retry toàn transaction hay chỉ lệnh update cuối? Vì sao?

### Bài J — Unknown commit

Driver gửi `commitTransaction`, database commit thành công nhưng client mất kết nối. Ứng dụng có được tạo một transfer mới với requestId khác để “chắc chắn thực hiện” không? Thiết kế bước reconcile.

### Bài K — Parallel commands

Trong Node.js:

~~~javascript
await session.withTransaction(async () => {
  await Promise.all([
    updateWalletA({ session }),
    updateWalletB({ session })
  ]);
});
~~~

Vì sao không nên chạy các thao tác của cùng transaction song song theo cách này?

### Bài L — Workload qua nhiều shard

Một transaction phải ghi 5 shards và mở gần 50 giây. Liệt kê các nguồn rủi ro so với transaction một shard và đề xuất phương án thiết kế.

### Bài M — Write skew

Hai transaction cùng thấy hai nhân viên đang trực, rồi mỗi transaction cho nghỉ một người trên hai document khác nhau. Vì sao chỉ dùng snapshot không bảo đảm “luôn còn một người trực”? Thiết kế invariant khác.

### Bài N — Outbox

Một transaction cập nhật order và gửi email ngay trong callback. Nếu callback được retry, điều gì xảy ra? Chuyển sang outbox và giải thích tại sao consumer vẫn cần dedupe.

### Bài O — Monitoring

Lập bảng metric với transaction duration p95/p99, abort by reason, write conflict, lock waits, cache, majority commit latency. Đặt ngưỡng cảnh báo dựa trên hệ thống thật thay vì tự bịa ngưỡng chung.

## 31. Gợi ý đáp án

**Bài A:** Một document dùng conditional atomic update. Chuyển ví + ledger cần multi-document transaction ngắn. Import lớn dùng batch/checkpoint hoặc versioned migration.

**Bài B:** Transaction sống quá lifetime phổ biến 60 giây và có thể abort. API call nằm ngoài transaction; transaction chỉ kiểm tra/commit các điều kiện DB cần thiết.

**Bài C:** Server selection giới hạn thời gian tìm node; transaction lifetime giới hạn tuổi transaction; maxCommitTimeMS liên quan commit; lock request timeout liên quan chờ lock. Các timeout không thay nhau.

**Bài D:** Câu khẳng định “tổng transaction chỉ 16 MiB” không đúng với phiên bản hiện đại có nhiều oplog entries. Từng document vẫn bị giới hạn 16 MiB, từng oplog entry có giới hạn, tổng còn chịu cache/lifetime/resource.

**Bài E:** Transaction không nâng giới hạn document. Có thể tách items thành nhiều documents tham chiếu order hoặc đưa binary/blob lớn sang lưu trữ phù hợp (như GridFS cho file).

**Bài F:** Retry nguyên transaction quá lớn thường lặp lại lỗi. Chia batch nhỏ, checkpoint cùng transaction, tối ưu index và giảm thời gian sống.

**Bài G:** `$merge` không hợp lệ trong transaction. Chạy job ngoài transaction, dùng materialized report theo version và atomic pointer cutover hoặc phương thức consistency phù hợp.

**Bài H:** DDL trong transaction có giới hạn version/read concern/cross-shard. Pre-create collections/indexes qua migration giảm rủi ro metadata lock và lỗi runtime.

**Bài I:** Retry toàn transaction và đọc lại dữ liệu trên snapshot mới. Không giữ điều kiện từ attempt đã abort.

**Bài J:** Không tạo requestId khác. Retry commit theo helper hoặc reconcile ledger của requestId gốc; nếu chưa xác định, trả PENDING/UNKNOWN theo API contract.

**Bài K:** Node Driver không hỗ trợ parallel operations trong cùng transaction theo `Promise.all`. Chạy tuần tự và quản lý cùng session rõ ràng.

**Bài L:** Thêm routing, network, coordinator, commit latency, failover/chunk migration, contention. Giảm shards touched và transaction lifetime; xem versioned workflow/saga nếu không cần atomic cross-shard.

**Bài M:** Hai transaction có thể cập nhật hai document khác nhau dựa trên một invariant tổng hợp, dẫn tới write skew. Dùng guard document chung, counter điều kiện hoặc constraint mô hình hóa invariant để buộc xung đột thật sự.

**Bài N:** Callback retry có thể gửi email hai lần dù DB cuối cùng chỉ commit một lần. Ghi outbox trong transaction, relay gửi sau commit, consumer dedupe theo event ID.

**Bài O:** Tập trung xu hướng p95/p99, tỷ lệ abort, lock/cache, commit latency và tác động tới throughput; chọn threshold theo SLO và baseline.

## 32. Câu hỏi ôn tập

**1. Vì sao MongoDB có giới hạn thời gian sống transaction?**

Vì transaction dài có thể giữ snapshot/tài nguyên, tăng contention, cache pressure và chi phí phục hồi. Server giới hạn thời gian sống để không cho transaction giữ tài nguyên vô hạn.

**2. Transaction lifetime mặc định thường là bao nhiêu?**

Thông thường **60 giây**, do `transactionLifetimeLimitSeconds` kiểm soát. Kiểm tra giá trị thực tế trong deployment.

**3. Transaction quá 60 giây có luôn bị abort chính xác tại mili giây thứ 60.000 không?**

Không nên giả định thời điểm chính xác. Có cơ chế dọn/abort và các lỗi khác có thể xảy ra sớm hơn; thiết kế deadline an toàn trước ngưỡng.

**4. `maxCommitTimeMS` có thay transactionLifetimeLimitSeconds không?**

Không. Một tham số liên quan commit; một tham số liên quan tuổi transaction. Cần thiết kế tổng deadline và error handling phù hợp.

**5. Một BSON document trong transaction có thể vượt 16 MiB không?**

Không. Giới hạn BSON document vẫn áp dụng.

**6. Một transaction hiện đại có phải luôn bị giới hạn tổng 16 MiB không?**

Không. Các phiên bản hiện đại có thể ghi nhiều oplog entries cho một transaction; tổng transaction vẫn chịu nhiều giới hạn tài nguyên khác.

**7. `allowDiskUse: true` có giải quyết lỗi document 16 MiB không?**

Không. Nó có phạm vi ở những stage aggregation được phép spill; không nâng BSON document limit và không cứu một transaction quá lớn cho cache.

**8. Một transaction chứa hàng trăm nghìn updates có thể thất bại dù mỗi document nhỏ?**

Có. Lifetime, WiredTiger cache, contention, oplog/storage workload và topology vẫn có giới hạn thực tế.

**9. `TransactionTooLargeForCache` có phải lỗi nên retry mãi?**

Không. Cần thu nhỏ transaction/batch, điều chỉnh mô hình hoặc tài nguyên; retry y nguyên có thể thất bại liên tiếp.

**10. `$out` và `$merge` có được dùng trong transaction không?**

Không. Chạy materialization ngoài transaction hoặc thiết kế workflow/versioned output khác.

**11. Có thể dùng `countDocuments()` trong transaction không?**

Trong những trường hợp hỗ trợ, có; nó sử dụng cơ chế aggregation. Lệnh count legacy không được hỗ trợ như vậy.

**12. Có bao giờ được tạo collection/index trong transaction không?**

Có những trường hợp được hỗ trợ từ MongoDB 4.4 nhưng có nhiều điều kiện version/read concern/topology, đặc biệt trong sharded transactions. Pre-create thường an toàn hơn cho runtime.

**13. Có thể dùng `Promise.all()` để chạy hai updates cùng một Node.js transaction không?**

Không nên; Node.js Driver không hỗ trợ parallel operations trong cùng transaction. Chạy tuần tự.

**14. `TransientTransactionError` dẫn đến hành động gì?**

Abort attempt và retry **toàn transaction** theo giao thức driver với giới hạn; đọc lại trạng thái.

**15. `UnknownTransactionCommitResult` dẫn đến hành động gì?**

Retry commit phù hợp hoặc reconcile bằng idempotency ledger; không coi là chưa commit rồi phát business intent mới.

**16. Vì sao không gọi payment API trong transaction callback?**

Callback có thể được retry, payment không rollback theo MongoDB, network call làm transaction sống lâu.

**17. Vì sao update một document thường tốt hơn multi-document transaction cho một invariant đơn giản?**

Atomic update đơn giản hơn, ít overhead và tránh giữ snapshot/điều phối commit nhiều document.

**18. Transaction có tự bảo đảm mọi business invariant không?**

Không. Snapshot isolation và write conflict không tự ngăn mọi write skew trên các document khác nhau; cần mô hình hóa constraints đúng.

**19. Có thể chia job lớn thành nhiều transaction mà vẫn giữ atomicity toàn job không?**

Không tự động. Mỗi batch atomic riêng; muốn các reader thấy một phiên bản hoàn chỉnh, cần thiết kế version/cutover hoặc mô hình khác.

**20. Tại sao transaction cross-shard thường đắt hơn một shard?**

Cần routing, giao tiếp giữa shards và điều phối commit; có thêm failure modes và chi phí latency.

## 33. Những sai lầm thường gặp

| Sai lầm | Vấn đề | Cách khắc phục |
|---|---|---|
| Cho rằng transaction có thể chạy bao lâu cũng được | Hết lifetime, giữ tài nguyên | Giữ transaction ngắn, deadline rõ |
| Tăng lifetime để cứu batch khổng lồ | Cache/contestion vẫn còn | Chia batch/checkpoint |
| Lẫn 16 MiB document với tổng transaction | Thiết kế sai giới hạn | Phân biệt BSON doc, oplog entries và resource limits |
| Cho rằng nhiều entries nghĩa là transaction vô hạn | Cache/lifetime/IO vẫn giới hạn | Đo tải, giảm scope |
| Retry mọi lỗi transaction cùng một cách | Permanent lỗi lặp, unknown commit có thể double apply | Phân loại code/labels và outcome |
| Gọi HTTP/email/payment trong transaction | Không rollback, callback retry tạo side effect lặp | Outbox/external idempotency |
| `Promise.all` trên một session transaction | Không được hỗ trợ trong Node Driver | Await tuần tự |
| Đặt `$out`/`$merge` trong transaction | Unsupported stage | Chạy ngoài transaction |
| Đặt DDL bất kỳ trong transaction | Version/topology/lock restrictions | Migration bên ngoài, kiểm tra hỗ trợ |
| Transaction truy vấn không index | Scan lâu, dễ timeout | Tối ưu index và filter |
| Dùng transaction để đọc báo cáo dài | Giữ snapshot và tăng tải | Read-only query ngoài transaction, batch/snapshot model phù hợp |
| Nhầm matchedCount=0 với WriteConflict | Xử lý nghiệp vụ sai | Phân biệt conditional failure và transient abort |
| Kết luận timeout nghĩa là chưa commit | Có thể double apply khi retry | Request ledger và reconciliation |
| Một transaction chạm nhiều shard không cần thiết | Tăng commit latency và failure modes | Shard-key-aware design |
| Quên unique index cho requestId | Concurrent retries tạo side effect trùng | Idempotency ledger + unique constraint |
| Tin rằng snapshot chặn mọi write skew | Invariant tổng hợp có thể bị vi phạm | Guard document/unique constraint/data model |
| Test trên standalone mongod | Không chạy được transaction đa document | Dùng replica set lab |
| Không quan sát p95/p99 duration | Chỉ thấy lỗi sau khi production quá tải | Instrumentation, alert và SLO |

## 34. Bảng ghi nhớ nhanh

| Nhu cầu | Công cụ / nguyên tắc |
|---|---|
| Xem transaction lifetime | `db.adminCommand({getParameter:1,transactionLifetimeLimitSeconds:1})` |
| Xem lock wait parameter | `db.adminCommand({getParameter:1,maxTransactionLockRequestTimeoutMillis:1})` |
| Bắt đầu session mongosh | `db.getMongo().startSession()` |
| Bắt đầu transaction | `session.startTransaction({readConcern:{level:"snapshot"},writeConcern:{w:"majority"}})` |
| Commit | `session.commitTransaction()` |
| Abort | `session.abortTransaction()` |
| Node Driver helper | `session.withTransaction(async()=>{...})` |
| Commit time budget | `maxCommitTimeMS` ở transaction options theo driver |
| Lỗi transient | Retry toàn transaction theo label và budget |
| Commit chưa rõ | Retry commit/reconcile, giữ cùng requestId |
| BSON document limit | 16 MiB **mỗi document** |
| Ghi batch lớn | Nhiều transaction ngắn + checkpoint |
| Lệnh materialization | `$out`/`$merge` ngoài transaction |
| Data migration | Pre-create collection/index, versioned cutover |
| Quan sát transaction | `db.serverStatus().transactions`, currentOp, metrics |
| Giảm lock/cache pressure | Transaction ngắn, index tốt, phạm vi ghi nhỏ |
| External events | Transactional outbox + consumer dedupe |

## 35. Checklist trước khi dùng transaction trên production

- [ ] Có thật sự cần **multi-document atomicity**, hay một atomic update đủ?
- [ ] Dữ liệu cần chạm nằm trên bao nhiêu documents, collections và shards?
- [ ] Những thao tác này có nằm trong danh sách được phép trong transaction của phiên bản chạy không?
- [ ] Đã tạo collection/index trước runtime, tránh DDL bất ngờ?
- [ ] Transaction không chứa HTTP request, email, payment hoặc công việc chờ người dùng?
- [ ] Có giới hạn batch/number of touched documents/estimated bytes theo workload thực?
- [ ] Mỗi document vẫn dưới 16 MiB và không nhầm với giới hạn tổng transaction?
- [ ] Đã đánh giá WiredTiger cache, disk, oplog và replication health?
- [ ] Có index đủ tốt cho những read/filter/update bên trong transaction?
- [ ] Có deadline ngắn hơn lifetime server và xử lý lock timeout/commit timeout?
- [ ] Read concern, write concern và read preference được chọn theo business consistency?
- [ ] Mọi lệnh transaction dùng cùng session và thực thi tuần tự trong Node.js?
- [ ] Helper retry có thể gọi lại callback và callback không có side effect ngoài DB?
- [ ] Có phân biệt transient abort, unknown commit, duplicate key, BSON size và cache error?
- [ ] Có unique business constraints/idempotency key khi HTTP request có thể retry?
- [ ] Có thể reconcile outcome sau mất phản hồi commit?
- [ ] Với sharded cluster, đã kiểm tra cross-shard writes, DDL và chunk migration?
- [ ] Với workflow dài, đã cân nhắc batch/checkpoint, saga hoặc versioned cutover?
- [ ] Có đo transaction duration/abort reason/lock waits/cache trong môi trường đại diện?
- [ ] Có plan rollback/mitigation nếu thay đổi transaction làm giảm throughput?

## 36. Kết luận

MongoDB transaction giải quyết bài toán **nguyên tử của nhiều ghi** trong một phạm vi được hỗ trợ, nhưng nó đi kèm **ngân sách thời gian, cache, dung lượng và giới hạn thao tác**. Thời gian sống mặc định thường khoảng 60 giây; từng BSON document vẫn bị giới hạn 16 MiB; các phiên bản hiện đại có thể dùng nhiều oplog entries cho một transaction, nhưng điều đó **không làm transaction vô hạn**. Những lệnh như `$out`, `$merge`, một số DDL/admin operations hoặc các thao tác với special namespaces có các hạn chế riêng. Distributed transactions còn có thêm chi phí điều phối và giới hạn topology.

Chiến lược vững chắc là **giữ transaction nhỏ, ngắn và tập trung vào invariant nghiệp vụ**, pre-create schema/index, truy vấn bằng index tốt, dùng session/concern đúng, xử lý `TransientTransactionError` và `UnknownTransactionCommitResult` theo hai cách khác nhau, và không đặt side effects bên ngoài trong transaction callback. Với tác vụ hàng triệu documents hoặc workflow kéo dài, hãy dùng **batch có checkpoint, outbox, saga hoặc versioned cutover** thay vì cố mở rộng một transaction cho mọi việc.
