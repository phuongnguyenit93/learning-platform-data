# Giao dịch dài, xung đột ghi và ảnh hưởng đến tài nguyên trong MongoDB

## 1. Tình huống mở đầu: một giao dịch giữ trạng thái quá lâu

Giả sử ứng dụng đặt vé tổ chức một thao tác gồm ba bước:

1. Đọc số lượng vé còn lại.
2. Trừ một vé khỏi kho.
3. Tạo đơn và bản ghi thanh toán.

Nhóm phát triển muốn ba bước **cùng thành công hoặc cùng thất bại**, nên dùng một **multi-document transaction**. Đây là lựa chọn hợp lý nếu bất biến nghiệp vụ thực sự nằm ở nhiều document. Nhưng phiên bản đầu tiên lại thực hiện:

```text
BEGIN TRANSACTION
    |
    +-- đọc tồn kho
    |
    +-- gọi cổng thanh toán bên ngoài (chờ 35 giây)
    |
    +-- chờ dịch vụ kiểm tra gian lận (chờ 20 giây)
    |
    +-- cập nhật tồn kho
    |
    +-- tạo đơn
    |
COMMIT
```

Giao dịch này có thể gặp nhiều vấn đề:

- Trong lúc chờ mạng, nó vẫn đang sống trong MongoDB và tiêu thụ tài nguyên theo trạng thái giao dịch.
- Snapshot đọc có thể trở nên cũ trong khi những writer khác tiếp tục thay đổi dữ liệu.
- Khi cập nhật document tồn kho mà giao dịch khác đã thay đổi, nó có thể gặp **write conflict** và bị hủy.
- Giao dịch có thể bị dừng do **thời gian tồn tại quá dài**, thiếu tài nguyên cache, lỗi truy cập lock hoặc thay đổi topology.
- Nếu callback giao dịch được chạy lại tự động, việc gọi cổng thanh toán bên trong callback có nguy cơ **thực hiện side effect ngoài MongoDB nhiều lần**.

Do đó, mục tiêu không chỉ là “sử dụng transaction để mọi thứ nguyên tử”, mà còn phải thiết kế **giao dịch ngắn, có ranh giới rõ, xử lý cạnh tranh đúng cách và không giữ tài nguyên vô ích**.

Bài học **“Giao dịch dài, xung đột ghi và ảnh hưởng đến tài nguyên”** thuộc chương **Giao dịch** của MongoDB. Sau bài, bạn có thể:

- Giải thích multi-document transaction và thời điểm nên hoặc không nên dùng.
- Phân biệt **write conflict**, **lock wait**, **transaction timeout** và **unknown commit result**.
- Hiểu vì sao transaction lâu làm tăng chi phí snapshot, cache, lịch sử dữ liệu và quản lý lock.
- Viết transaction ngắn trong `mongosh` và Node.js driver.
- Xử lý retry theo **error labels**, phân biệt retry toàn transaction với retry commit.
- Thiết kế idempotency và đưa cuộc gọi dịch vụ ngoài database ra khỏi transaction callback.
- Quan sát số transaction đang mở, transaction bị abort và các dấu hiệu nghẽn tài nguyên.
- Lập quy trình khắc phục khi một cluster có nhiều giao dịch dài hoặc tỷ lệ write conflict cao.

## 2. Multi-document transaction làm được gì?

### 2.1. Tính nguyên tử và ranh giới của transaction

MongoDB đã bảo đảm tính **nguyên tử cho một thao tác ghi trên một document**. Khi một yêu cầu chỉ cập nhật các field của một document, nhiều trường hợp có thể dùng ngay `updateOne()` với filter có điều kiện và các operator như `$inc`, `$set`, `$addToSet`.

Multi-document transaction được dùng khi cần nhiều thao tác trên nhiều document hoặc collection cùng có tính **all-or-nothing** trong phạm vi MongoDB hỗ trợ:

```text
BEGIN TRANSACTION
    |
    +-- ghi account A: -100
    +-- ghi account B: +100
    +-- tạo ledger entry
    |
    +-- tất cả hợp lệ? --> COMMIT
    |
    +-- có lỗi? -------> ABORT / ROLLBACK
```

Nếu transaction abort, các thay đổi chưa commit của transaction không trở thành kết quả ghi cuối cùng. Nếu commit thành công theo mức xác nhận yêu cầu, các thao tác trong transaction được áp dụng nguyên tử theo ngữ nghĩa MongoDB.

Một transaction **không thể tự rollback email đã gửi, cuộc gọi HTTP bên ngoài, tiền đã thu ở cổng thanh toán hoặc sự kiện đã publish tới hệ thống khác**. Những side effect này cần kiến trúc phối hợp khác.

### 2.2. Session, transaction và commit

Với MongoDB driver, một transaction chạy trong một **client session**. Luồng khái niệm:

```text
startSession()
      |
startTransaction()
      |
  operation A
  operation B
  operation C
      |
commitTransaction()  hoặc  abortTransaction()
      |
endSession()
```

Điểm cần nhớ:

1. Mọi lệnh thuộc transaction phải dùng **cùng session**.
2. Session có thể tồn tại lâu hơn một transaction; không đồng nhất hai vòng đời.
3. Cần commit hoặc abort, rồi đóng session theo API driver.
4. Không chạy nhiều thao tác đồng thời trong cùng một transaction bằng `Promise.all()` hoặc cơ chế tương tự nếu driver không hỗ trợ; dùng thứ tự tuần tự rõ ràng.
5. Không coi một transaction đang mở là nơi thích hợp để chờ người dùng xác nhận hoặc chờ một dịch vụ chậm.

### 2.3. Transaction có thể đọc snapshot

Khi dùng `readConcern: { level: "snapshot" }` trong transaction, những lệnh đọc của transaction làm việc với một snapshot nhất quán phù hợp với ngữ nghĩa triển khai. Trong khi đó, các transaction và request khác vẫn có thể tiếp tục ghi dữ liệu bên ngoài.

```text
T0: transaction A bắt đầu và đọc snapshot, balance=100
T1: transaction B cập nhật balance=80 rồi commit
T2: transaction A vẫn có ngữ cảnh snapshot trước đó
T3: A cố ghi lên balance dựa trên dữ liệu cũ
    -> có thể gặp write conflict và bị abort
```

Snapshot không có nghĩa MongoDB đặt một **khóa đọc độc quyền trên mọi document được đọc** suốt transaction. Nó giúp có cái nhìn nhất quán, nhưng sự thay đổi đồng thời có thể dẫn đến xung đột khi A thử ghi.

### 2.4. Snapshot isolation không thay cho mọi invariant nghiệp vụ

Ngay cả khi hai transaction đọc snapshot và mỗi transaction ghi thành công lên **những document khác nhau**, một quy tắc trải trên nhiều document vẫn có thể bị vi phạm nếu không có cách cưỡng chế phù hợp. Đây là nhóm vấn đề thường được gọi là *write skew* trong các mô hình snapshot isolation.

Ví dụ hai bác sĩ trực có hai document. Mỗi transaction đọc “có ít nhất hai người trực” rồi tự chuyển **document riêng** của mình sang `offDuty`. Nếu hai transaction không cùng ghi một document và không có điều kiện/ràng buộc bổ sung, cả hai có thể quyết định dựa trên snapshot cũ. Kết quả có nguy cơ **không còn ai trực**.

Muốn bảo vệ invariant này, cần thiết kế phép ghi có tranh chấp trên một nguồn trạng thái chung, kiểm tra và cập nhật đúng trong transaction, hoặc mô hình dữ liệu/ràng buộc khác phù hợp. Đừng cho rằng cứ có transaction là mọi điều kiện logic đã được tuần tự hóa tuyệt đối.

## 3. Khi nào một transaction được coi là “dài”?

Không có một ngưỡng mili giây chung cho tất cả hệ thống. “Dài” có thể là:

- Vài giây đối với một API tương tác vốn chỉ cần cập nhật hai document.
- Hàng chục giây khi transaction phải duyệt lượng lớn dữ liệu.
- Một transaction giữ snapshot lâu hơn tốc độ churn mà storage/cache có thể chịu ổn định.
- Transaction tiến gần hoặc vượt **transaction lifetime limit** của cấu hình server.

Tác hại phụ thuộc **cả thời gian và mức công việc**. Một transaction chỉ đọc, mở quá lâu có thể gây áp lực giữ snapshot; một transaction ghi hàng chục nghìn document có thể gặp áp lực tài nguyên ngay cả khi thời gian chưa vượt ngưỡng cấu hình.

### 3.1. Độ dài theo thời gian

```text
Transaction ngắn:

BEGIN -> validate bằng dữ liệu đã có -> 2 updates -> COMMIT
         [thường trong khoảng thời gian nhỏ]

Transaction dài:

BEGIN -> query lớn -> vòng lặp -> HTTP call -> wait -> updates -> COMMIT
         [nhiều khoảng chờ + lượng dữ liệu lớn]
```

Một nguyên tắc vận hành thực tế:

> Chuẩn bị input và gọi các dịch vụ có thể gọi trước ở **ngoài transaction**. Chỉ giữ trong transaction những lệnh MongoDB thật sự phải cùng commit, cùng các kiểm tra dữ liệu bắt buộc phải thực hiện trên trạng thái nhất quán.

### 3.2. Độ dài theo tài nguyên

Một transaction có thể ngắn nhưng **rất nặng**:

- Quét nhiều document hoặc index không phù hợp.
- Ghi số lượng lớn document.
- Làm nhiều cập nhật tới các document đang bị tranh chấp.
- Chạm nhiều shard, collection hoặc namespace.
- Cần giữ nhiều phiên bản dữ liệu vì snapshot đã đọc.

Trong những trường hợp này, việc chỉ tăng thời gian cho phép của transaction thường không giải quyết gốc vấn đề.

## 4. Ảnh hưởng của transaction dài tới tài nguyên MongoDB

### 4.1. Giữ snapshot và lịch sử phiên bản dữ liệu

MongoDB với storage engine WiredTiger sử dụng cơ chế hỗ trợ snapshot và quản lý các phiên bản dữ liệu. Một transaction sống lâu có thể giữ một **mốc snapshot cũ** khiến engine phải duy trì những thông tin lịch sử cần thiết cho các reader còn hoạt động.

Hình dung:

```text
T0              T1              T2              T3
|---------------|---------------|---------------|
   Txn A đọc snapshot T0
   |-------------------------------------------|
      các writer khác tiếp tục đổi document
            |        |           |
            v        v           v
         version 2  version 3   version 4

Nếu snapshot T0 còn cần thiết, engine có thể phải duy trì
khả năng phục vụ trạng thái cũ thay vì bỏ hết lịch sử ngay.
```

Tác động có thể biểu hiện bằng áp lực **WiredTiger cache**, lịch sử phiên bản, eviction, dirty pages và hiệu năng đọc/ghi. Cách quản lý chi tiết phụ thuộc phiên bản MongoDB, workload và storage engine; không nên suy luận rằng “transaction giữ nguyên cả bản sao database trong RAM”.

### 4.2. Áp lực cache và các lỗi liên quan kích thước transaction

Nếu một transaction tạo hoặc phải giữ quá nhiều thay đổi chưa commit, hệ thống có thể gặp áp lực cache, khó eviction hoặc lỗi như **`TransactionTooLargeForCache`** ở những phiên bản hỗ trợ thông báo này.

Nguyên tắc:

- Transaction càng lớn, số document/byte thay đổi càng nhiều thì chi phí có thể càng cao.
- Không dùng transaction để cập nhật hàng triệu document một cách mặc định.
- Chia một batch theo nhiều transaction nhỏ **chỉ khi nghiệp vụ cho phép chia tính nguyên tử**.
- Với lỗi do transaction quá lớn cho cache, retry toàn bộ y nguyên mà không giảm lượng việc thường không giúp ích.
- Cần xem dữ liệu đo thực tế thay vì chỉ tăng `WiredTiger` cache một cách mù quáng.

Một transaction không có giới hạn “chính xác 16 MB cho **toàn bộ** dữ liệu” như những mô tả từ cơ chế oplog cũ. MongoDB hiện đại có thể ghi nhiều entry oplog cho một transaction; giới hạn BSON document và các giới hạn tài nguyên/thời gian khác vẫn áp dụng. Hãy tra phiên bản triển khai trước khi kết luận về số lượng operations hoặc dung lượng hợp lệ.

### 4.3. Lock và tranh chấp tài nguyên

MongoDB không giữ một **global exclusive lock trên toàn database** trong suốt mọi transaction. Cơ chế lock gồm nhiều cấp và storage engine có concurrency control ở cấp document/record cùng các khóa/intent lock liên quan.

Tuy nhiên, transaction có thể:

- Giữ một số lock/resource cho tới khi transaction kết thúc.
- Cạnh tranh với transaction khác ghi cùng document hoặc truy cập metadata.
- Đợi một lock cần thiết trong giới hạn thời gian cho phép.
- Bị abort vì không lấy được lock hoặc vì write conflict.
- Kéo dài thời gian mà tài nguyên liên quan đến session/transaction còn bị sử dụng.

**Đợi lock** và **write conflict** là hai tình huống liên quan nhưng khác nhau. Chờ lock có thể kết thúc bằng thành công hoặc timeout. Write conflict có thể khiến transaction bị hủy và cần quyết định retry.

### 4.4. Connection, session và số transaction đang mở

Transaction dùng session và cần những tài nguyên thực thi phù hợp với topology. Nhiều transaction đang mở hoặc idle có thể tạo áp lực cho:

- Connection pool và session lifecycle ở ứng dụng.
- Tài nguyên server để theo dõi transaction.
- Snapshot/cache và lịch sử phiên bản.
- Khả năng phục vụ các transaction mới khi nhiều transaction đang cạnh tranh.

Không nên suy ra một transaction luôn **ghim một connection theo cùng cách trên mọi driver/topology**. Cơ chế pinning và server selection có khác biệt giữa replica set và sharded cluster, phiên bản driver, loại thao tác. Nhưng ứng dụng vẫn phải bảo đảm không để transaction hoặc session rò rỉ.

### 4.5. Replication, oplog và commit

Các thay đổi của transaction được phản ánh trong cơ chế ghi/oplog và replication theo ngữ nghĩa MongoDB. Một transaction lớn có thể tạo nhiều oplog entry và chi phí áp dụng trên secondary.

Khi transaction commit:

- Server phải hoàn thành công việc cần thiết cho các thay đổi trong transaction.
- Write concern như `"majority"` có thể làm client chờ xác nhận theo cấu hình replica set.
- Secondary có thể chịu tải apply đáng kể.
- Không có quy tắc mọi transaction đều chỉ tạo **một** entry oplog.

**Commit chậm** không nhất thiết là write conflict. Cần xem riêng thời gian thao tác, replication/majority acknowledgment, network và tài nguyên storage.

### 4.6. Một phép đo tổng hợp

| Dấu hiệu | Có thể liên quan đến | Cần điều tra thêm |
| --- | --- | --- |
| Nhiều transaction `open` hoặc `active` | Vòng đời transaction dài, rò rỉ session hoặc tải cao | Duration, loại operation, nguồn ứng dụng |
| Tỷ lệ abort tăng | Write conflict, timeout, lock, resource hoặc lỗi khác | Error codes/labels và server logs |
| Cache pressure, eviction tăng | Snapshot/history, đọc/ghi lớn, workload khác | Metrics WiredTiger và transaction duration |
| P95/P99 latency ghi tăng | Lock contention, I/O, CPU, replication | Command monitoring, disk, serverStatus |
| Nhiều `WriteConflict` | Nhiều writer tranh document hoặc index | Query patterns, hot keys, retry |
| Transaction lifetime exceeded | Transaction mở quá lâu | Thời gian chờ bên ngoài, query lớn, timeout |
| Commit latency cao | Majority replication, disk, network, topology | Write concern, replication lag, logs |
| Lỗi `TransactionTooLargeForCache` | Transaction vượt khả năng giữ thay đổi trong cache | Kích thước transaction, thiết kế batch |

Đây là **triệu chứng cần tương quan**. Ví dụ cache tăng không chứng minh duy nhất nguyên nhân là transaction dài; còn rất nhiều workload khác dùng chung cache.

## 5. Write conflict là gì?

### 5.1. Hai transaction cùng muốn sửa một document

Giả sử có document:

```javascript
{
  _id: "SKU-100",
  available: 10,
  version: 1
}
```

Hai transaction A và B đều đọc trạng thái ban đầu. B thay đổi số lượng và commit trước khi A cố ghi:

```text
T0: A bắt đầu; đọc snapshot available = 10
T1: B cập nhật available = 8 rồi commit
T2: A cố update available = 7 trên document đó
    |
    v
MongoDB phát hiện A không thể áp dụng ghi một cách an toàn
trên snapshot cũ -> có thể trả WriteConflict / abort transaction.
```

Nếu không có cơ chế bảo vệ, A có thể ghi đè thay đổi của B. MongoDB có concurrency control để ngăn việc ghi dựa trên một phiên bản không còn hợp lệ mà vẫn báo thành công như không có chuyện gì.

### 5.2. Error code và error label

Một write conflict thường xuất hiện với tên lỗi như **`WriteConflict`**, thường có mã MongoDB **`112`**. Trong transaction, driver có thể nhận error label **`TransientTransactionError`** cho những lỗi tạm thời cần retry.

Ví dụ dạng thông tin lỗi:

```javascript
{
  code: 112,
  codeName: "WriteConflict",
  errorLabels: ["TransientTransactionError"]
}
```

Đây là **hình minh họa**, không phải mọi lỗi write conflict luôn có đúng toàn bộ field, message hoặc label giống nhau ở mọi version/driver.

Nên dựa trên **error labels do driver/server cung cấp** để quyết định chính sách retry transaction, và log code cùng tình huống cụ thể. Không retry mù quáng theo thao tác so sánh chuỗi `error.message.includes("write conflict")`.

### 5.3. Write conflict không phải duplicate key

Nếu hai request cùng tạo một business key có unique index:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
```

request thứ hai có thể gặp **`E11000` / mã 11000 (DuplicateKey)**. Đây không phải cùng loại với **WriteConflict (112)**.

Khác biệt:

- **Write conflict**: một kế hoạch ghi trong transaction xung đột với thay đổi đồng thời, có thể phù hợp để chạy lại transaction từ snapshot mới.
- **Duplicate key**: dữ liệu/khóa muốn ghi vi phạm ràng buộc unique; nếu không đổi key hoặc chính sách, retry cùng payload thường vẫn thất bại.

Đừng biến một duplicate key thành retry vô hạn. Hãy đối soát theo khóa nghiệp vụ hoặc trả lỗi conflict phù hợp.

### 5.4. Write conflict không phải lock timeout

Một transaction có thể không lấy được lock trong khoảng chờ cấu hình và gặp lỗi khác với WriteConflict. MongoDB có tham số như `maxTransactionLockRequestTimeoutMillis` trong những môi trường/phiên bản hỗ trợ, quy định thời gian tối đa mà một transaction chờ một số lock cần thiết.

Đặt giá trị timeout cao hơn có thể giảm lỗi lock wait trong một số tình huống, nhưng cũng **kéo dài thời gian chờ và tiêu thụ tài nguyên**. Không thay đổi tham số này để “chữa” toàn bộ lỗi cạnh tranh ghi mà chưa xác định được nguồn.

### 5.5. Cạnh tranh bên ngoài transaction

Không phải chỉ hai transaction mới có thể xung đột. Một update bình thường bên ngoài transaction cũng có thể làm document mà một transaction đã đọc trở nên không thể ghi an toàn theo snapshot của transaction.

```text
Transaction A:   đọc document X ở snapshot cũ
Writer B:        updateOne(X), commit
Transaction A:   updateOne(X) theo snapshot của A
                 -> write conflict có thể xảy ra
```

Điều này hữu ích để mô phỏng write conflict một cách có kiểm soát **trên document thử nghiệm riêng** mà không cần hai luồng lớn chạy song song.

## 6. Các giới hạn thời gian và kích thước cần biết

### 6.1. `transactionLifetimeLimitSeconds`

MongoDB có tham số **`transactionLifetimeLimitSeconds`** để giới hạn thời gian sống của multi-document transaction. Trong nhiều cấu hình `mongod` tự quản lý, giá trị mặc định phổ biến là **60 giây**, nhưng giá trị thực tế tùy phiên bản và dịch vụ.

Khi transaction tồn tại quá lâu, cơ chế dọn transaction hết hạn có thể **abort** nó. Nếu transaction đang chạy một vòng lặp hoặc chờ tác vụ bên ngoài, việc “đợi thêm một chút” có thể khiến mọi thay đổi chưa commit bị hủy.

Đối với cluster sharded, cấu hình và cách đồng bộ tham số liên quan transaction lifetime có thể cần được quản trị thống nhất. Managed service có thể không cho sửa trực tiếp.

Đừng mặc định 60 giây là “mục tiêu nên dùng hết”. API có SLA 200 ms nên chủ động giữ transaction ngắn hơn rất nhiều, dù server cho phép 60 giây.

### 6.2. Kiểm tra tham số khi có quyền

Trên môi trường được cấp quyền, một DBA có thể xem:

```javascript
db.adminCommand({
  getParameter: 1,
  transactionLifetimeLimitSeconds: 1
});
```

Để khảo sát lock wait parameter khi server hỗ trợ:

```javascript
db.adminCommand({
  getParameter: 1,
  maxTransactionLockRequestTimeoutMillis: 1
});
```

Đây là **lệnh đọc cấu hình**, không chỉnh server. Nếu gặp lỗi do thiếu quyền hoặc tham số không tồn tại trong phiên bản, không tự nâng quyền hay đổi setting.

### 6.3. Không tăng giới hạn như giải pháp đầu tiên

Trước khi thay `transactionLifetimeLimitSeconds`:

1. Vì sao transaction lại dài?
2. Query có COLLSCAN hoặc scan nhiều document không?
3. Có gọi HTTP, chờ queue hoặc user input trong transaction không?
4. Có xử lý batch quá lớn mà không cần nguyên tử toàn batch không?
5. Có write conflict lặp lại ở document nóng?
6. Storage/cache có còn headroom không?

Tăng lifetime có thể làm các transaction dài **tồn tại lâu hơn và tạo áp lực tài nguyên lớn hơn**, không phải tăng thông lượng một cách tự nhiên.

### 6.4. Giới hạn document và những giới hạn khác

MongoDB vẫn có giới hạn **16 MiB cho một BSON document**. Transaction có thể chứa nhiều thao tác và có cơ chế ghi oplog phụ thuộc phiên bản, nhưng không vì thế mà một document có thể tùy ý lớn.

Cần xem thêm các giới hạn về:

- Loại operation được phép trong transaction.
- DDL và namespace restrictions.
- Kích thước và áp lực WiredTiger cache.
- Thời gian transaction và thời gian chờ lock.
- Transaction trên nhiều shard.
- Phiên bản MongoDB/driver và cấu hình write concern.

**Không dùng giới hạn từ một phiên bản MongoDB cũ như điều kiện bất biến cho mọi release mới.**

## 7. Ví dụ an toàn: mô phỏng write conflict bằng `mongosh`

### 7.1. Điều kiện thực hành

Ví dụ cần **MongoDB replica set hoặc sharded cluster hỗ trợ transactions**, không phải standalone `mongod` thông thường. Chỉ chạy trên database test và document riêng do bạn vừa tạo, không tạo xung đột cố ý trên dữ liệu production.

Để kết nối tới replica set local thử nghiệm:

```bash
mongosh "mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019/?replicaSet=rs0"
```

Điều chỉnh URI cho môi trường và quyền truy cập thực tế.

### 7.2. Tạo document thử nghiệm

Trong `mongosh`:

```javascript
const lab = db.getSiblingDB("mongo_tx_row252_lab");
const inventory = lab.getCollection("inventory_demo");

const runId = "row252-" + new ObjectId().toHexString();
const skuId = new ObjectId();

inventory.insertOne({
  _id: skuId,
  runId,
  sku: "ROW252-ITEM",
  available: 10,
  revision: 1,
  updatedAt: new Date()
});

print("database=" + lab.getName());
print("runId=" + runId);
printjson(inventory.findOne({ _id: skuId, runId }));
```

Chúng ta sử dụng `_id` và `runId` để mọi lệnh chỉ chạm vào document demo. Không dùng collection inventory thật hoặc ID đoán được từ người khác.

### 7.3. Cố ý tạo xung đột trên đúng một document test

Trong **cùng phiên `mongosh`**:

```javascript
const session = db.getMongo().startSession();
const txInventory = session
  .getDatabase(lab.getName())
  .getCollection("inventory_demo");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  // Transaction A đọc snapshot trước.
  const before = txInventory.findOne({
    _id: skuId,
    runId
  });
  printjson({ snapshotRevision: before.revision });

  // Writer B, BÊN NGOÀI transaction A, sửa chính document demo.
  const outsideResult = inventory.updateOne(
    { _id: skuId, runId },
    {
      $inc: { available: -1, revision: 1 },
      $set: { updatedAt: new Date() }
    }
  );
  printjson({ outsideResult });

  // Transaction A cố ghi với snapshot đã đọc trước writer B.
  try {
    const insideResult = txInventory.updateOne(
      { _id: skuId, runId },
      {
        $inc: { available: -1, revision: 1 },
        $set: { updatedAt: new Date() }
      }
    );
    printjson({ insideResult });
  } catch (error) {
    print("Transaction write error code: " + error.code);
    print("Message: " + error.message);
    printjson(error.errorLabels ?? []);
  }
} finally {
  // Giao dịch A không commit trong ví dụ; luôn kết thúc an toàn.
  try {
    session.abortTransaction();
  } catch (_ignored) {
    // Có thể transaction đã bị server hủy khi xảy ra lỗi.
  }
  session.endSession();
}

printjson(inventory.findOne({ _id: skuId, runId }));
```

Ý nghĩa:

- Transaction A cố định một snapshot khi đọc.
- Writer B thay đổi document **ở ngoài A**.
- Khi A ghi trên snapshot cũ, MongoDB có thể phát hiện write conflict và abort A; mã lỗi thường liên quan `WriteConflict`.
- Lệnh update của B độc lập với A nên **không được tự rollback** khi A abort.
- Transaction A **không commit** trong ví dụ, vì vậy kết quả cuối chỉ phản ánh thao tác của B.

Kết quả và thông điệp lỗi cụ thể phụ thuộc server version, timing, topology và shell. Mục tiêu là hiểu cơ chế xung đột, không phải yêu cầu một dòng stderr phải giống chính xác trên mọi môi trường. Nếu có lỗi không liên quan (topology, authorization, kết nối), dừng để xác định nguyên nhân thay vì coi đó là WriteConflict.

### 7.4. Dọn document demo

Trước khi xóa, xác nhận chính xác:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);
printjson(
  inventory.findOne(
    { _id: skuId, runId },
    { _id: 1, runId: 1, sku: 1, revision: 1 }
  )
);
```

Nếu đúng document bạn tạo:

```javascript
const deleted = inventory.deleteOne({
  _id: skuId,
  runId
});

printjson(deleted);
print("remaining=" + inventory.countDocuments({
  _id: skuId,
  runId
}));
```

Không `deleteMany({})` hoặc `dropDatabase()` trên môi trường dùng chung. Ví dụ transaction không cần sửa cấu hình replica set, xóa oplog hay thay đổi election.

## 8. Ví dụ multi-document transaction ngắn bằng Node.js

### 8.1. Nghiệp vụ chuyển điểm giữa hai ví

Giả sử ứng dụng có:

```javascript
// wallets
{
  _id: ObjectId("66a000000000000000000011"),
  tenantId: "TENANT-A",
  points: 1000
}

{
  _id: ObjectId("66a000000000000000000012"),
  tenantId: "TENANT-A",
  points: 300
}
```

Yêu cầu chuyển 120 điểm từ ví A sang ví B và ghi ledger, sao cho:

1. A không bị âm.
2. A giảm đúng 120.
3. B tăng đúng 120.
4. Ledger entry được tạo cùng transaction.

Đây là trường hợp có invariant trải nhiều document. Ta muốn một transaction **ngắn**, chỉ gồm các lệnh database liên quan.

### 8.2. Chuẩn bị trước khi bắt đầu transaction

Trước khi bắt đầu:

- Kiểm tra người dùng có quyền chuyển điểm.
- Parse `amount` thành số nguyên hợp lệ và lớn hơn 0.
- Xác định tenant và ID ví từ ngữ cảnh đã xác thực.
- Sinh `operationId` ổn định cho request nghiệp vụ.
- Tạo **unique index** cho khóa idempotency/operation ID ở collection ledger theo thiết kế.
- Chuẩn bị điều kiện và các giá trị cần ghi.

Không gọi API thanh toán hay chờ người dùng xác nhận **bên trong** transaction.

### 8.3. Code Node.js với `withTransaction`

Ví dụ dùng Node.js MongoDB driver, giả định client đã kết nối và các collection/index đã được chuẩn bị, ID có kiểu BSON phù hợp:

```javascript
import { MongoClient } from "mongodb";

async function transferPoints({
  client,
  database,
  tenantId,
  fromWalletId,
  toWalletId,
  amount,
  operationId
}) {
  if (!Number.isSafeInteger(amount) || amount <= 0) {
    throw new Error("INVALID_AMOUNT");
  }
  if (fromWalletId.equals(toWalletId)) {
    throw new Error("SAME_WALLET");
  }

  const wallets = database.collection("wallets");
  const ledger = database.collection("transferLedger");
  const session = client.startSession();

  try {
    return await session.withTransaction(
      async () => {
        // Idempotency key phải được bảo vệ unique ở database.
        // Nếu operationId đã tồn tại, insertOne có thể báo E11000.
        await ledger.insertOne(
          {
            _id: operationId,
            tenantId,
            fromWalletId,
            toWalletId,
            amount,
            status: "COMPLETED",
            createdAt: new Date()
          },
          { session }
        );

        const debit = await wallets.updateOne(
          {
            _id: fromWalletId,
            tenantId,
            points: { $gte: amount }
          },
          { $inc: { points: -amount } },
          { session }
        );

        if (debit.matchedCount !== 1) {
          throw new Error("INSUFFICIENT_POINTS_OR_WALLET_MISSING");
        }

        const credit = await wallets.updateOne(
          { _id: toWalletId, tenantId },
          { $inc: { points: amount } },
          { session }
        );

        if (credit.matchedCount !== 1) {
          throw new Error("DESTINATION_WALLET_MISSING");
        }

        // Không gọi HTTP, gửi mail hoặc publish sự kiện ở đây.
        return { operationId, amount };
      },
      {
        readPreference: "primary",
        readConcern: { level: "snapshot" },
        writeConcern: { w: "majority" }
      }
    );
  } finally {
    await session.endSession();
  }
}
```

**Các giả định quan trọng:**

- `points` được lưu nhất quán dưới kiểu BSON số nguyên tương thích và không có thao tác âm thầm chuyển sang floating point ngoài quy ước. Với số lớn vượt phạm vi JS safe integer, dùng kiểu `Long`/Decimal128 và validation phù hợp thay vì `Number`.
- `operationId` là khóa ổn định cho **một lần chuyển**, do hệ thống kiểm soát và được bảo vệ bằng unique index, ở đây dùng `_id` trên `transferLedger` không sharded hoặc thiết kế sharding có uniqueness tương đương.
- Những ví cùng tenant phải là document hợp lệ và có đủ quyền truy cập.
- Không tự coi lỗi duplicate ledger là “chuyển thành công” trước khi **đối chiếu nội dung** bản ghi cùng operationId.
- Nếu callback bị retry, các thao tác MongoDB trong transaction trước đó phải rollback khi transaction thất bại; side effect ngoài database không được đặt trong callback.

Mẫu này cố tình dùng các update **có điều kiện trực tiếp**. Đối với trừ điểm, predicate `points: {$gte: amount}` giúp kiểm tra không âm **tại lúc ghi**, thay vì tin kết quả đọc trước đó từ một snapshot có thể đã cũ.

### 8.4. Vì sao không đọc rồi `$set` số dư cũ?

Cách dễ bị lost update:

```javascript
const wallet = await wallets.findOne(
  { _id: fromWalletId },
  { session }
);

await wallets.updateOne(
  { _id: fromWalletId },
  { $set: { points: wallet.points - amount } },
  { session }
);
```

Transaction có cơ chế phát hiện write conflict, nhưng cách tính từ snapshot cũ vẫn làm logic phức tạp hơn cần thiết. Dùng **atomic conditional update** trực tiếp với `$inc` và kiểm tra `matchedCount` là lựa chọn đơn giản, rõ bất biến hơn trong ví dụ này.

### 8.5. Không tự retry bằng cách tạo operationId mới

Nếu client không nhận được phản hồi do timeout nhưng transaction thực tế đã commit, việc gọi lại hàm với **operationId mới** có thể chuyển điểm lần thứ hai.

Để xử lý đúng:

- Client/API duy trì cùng operation ID cho cùng ý định chuyển điểm.
- Ledger có unique constraint phù hợp.
- Sau lỗi không rõ commit, đối soát ledger theo ID và so input nghiệp vụ.
- Nếu đã commit đúng operation, trả kết quả tương ứng.
- Nếu chưa có bản ghi và chưa biết chắc kết quả, áp chính sách recovery/retry được thiết kế rõ.

**Transaction bảo đảm atomicity trong MongoDB; idempotency bảo vệ một ý định nghiệp vụ khỏi bị thực hiện lặp giữa các request.**

## 9. Retry transaction: phân biệt lỗi tạm thời và kết quả commit chưa rõ

### 9.1. Hai error label quan trọng

MongoDB drivers có thể cung cấp những **error label** phục vụ phân loại:

| Label | Ý nghĩa vận hành | Hướng xử lý điển hình |
| --- | --- | --- |
| `TransientTransactionError` | Transaction gặp lỗi tạm thời trước khi commit hoàn tất, ví dụ một số write conflict/topology errors | Hủy transaction cũ và chạy lại **toàn bộ transaction** từ trạng thái/snapshot mới, có giới hạn |
| `UnknownTransactionCommitResult` | Client không biết chắc kết quả `commitTransaction` (ví dụ mất response khi commit) | Thường cần **retry commit** theo cơ chế driver hoặc đối soát; không tự chạy lại toàn bộ nghiệp vụ ngay |

Không phải mọi lỗi đều có một trong hai label. **DuplicateKey**, lỗi validation, thiếu quyền, sai schema hay transaction quá lớn có thể là lỗi quyết định cần sửa input/thiết kế, không phải retry vô hạn.

### 9.2. Vì sao retry cả transaction khi gặp write conflict?

Transaction A đã đọc snapshot cũ, nên **chỉ retry câu lệnh update bị lỗi** trong transaction đang thất bại thường không đủ. Snapshot của transaction không tự làm mới theo document B vừa commit.

Cách đúng về nguyên tắc:

```text
Attempt 1:
  start txn -> read old state -> write conflict -> abort

Attempt 2:
  start NEW txn -> read current state -> recompute -> write -> commit
```

Nếu logic nghiệp vụ tính giá, tồn kho hoặc hạn mức từ dữ liệu đọc, mỗi lần retry phải **tính lại** dựa trên dữ liệu của attempt mới.

### 9.3. `withTransaction` và automatic retry

Hàm `session.withTransaction(callback, options)` của MongoDB Node.js driver hỗ trợ transaction lifecycle và retry theo các trường hợp được driver quy định. Nó giúp tránh phải tự viết toàn bộ vòng lặp commit/abort.

Tuy nhiên:

- Callback có thể được gọi **nhiều lần** do retry transaction.
- Không được đặt side effect không idempotent ngoài MongoDB trong callback.
- Lỗi không retryable vẫn phải được trả ra và xử lý.
- Không nên đặt vòng retry ngoài vô hạn, khiến cluster bị thêm tải khi đã có contention.
- Trong các trường hợp timeout/unknown commit, API vẫn cần idempotency và quy trình đối soát nghiệp vụ.

Một service phải có **timeout/deadline và retry budget** phù hợp SLA, không để request chiếm tài nguyên mãi vì luôn có transient error.

### 9.4. Retry commit khác retry toàn bộ body

Giả sử:

```text
begin transaction
  debit A
  credit B
commitTransaction() -> MongoDB đã commit
                    -> response bị mất
client nhận lỗi UnknownTransactionCommitResult
```

Nếu client **chạy lại debit/credit như một nghiệp vụ mới** thì có thể chuyển tiền/điểm hai lần. Nếu driver có thể retry **chính commit của transaction đó**, đó là luồng khác: nó không đồng nghĩa tạo một giao dịch nghiệp vụ mới.

Vì vậy tuyệt đối không viết:

```javascript
// Ví dụ chống chỉ định:
try {
  await transferMoney();
} catch (error) {
  // Sai nếu mất phản hồi ở COMMIT mà chưa đối soát:
  await transferMoney(); // Đặc biệt nguy hiểm nếu ID nghiệp vụ mới.
}
```

Thay bằng thao tác có **operationId ổn định**, nhờ driver xử lý retry commit khi hỗ trợ, sau đó đối soát khi cần.

### 9.5. Retry quá nhiều có thể làm vấn đề nặng hơn

Khi 200 request cùng tranh một document “hot”, cùng bị write conflict rồi cùng retry tức thì:

```text
200 writers
   |
   +-- nhiều write conflicts
   |
   +-- retry ngay lập tức
   |
   +-- contention tăng
   |
   +-- thêm conflicts
```

Cần cân nhắc:

- Giới hạn số attempt.
- Backoff có jitter.
- Hạn chế số request đồng thời vào cùng aggregate.
- Queue/serialize ở tầng ứng dụng nếu nghiệp vụ phù hợp.
- Mô hình lại dữ liệu hoặc dùng atomic operator thay transaction khi đủ.
- Giảm lượng công việc trong transaction.

Không có một giá trị retry cố định tối ưu cho mọi workload.

## 10. Khóa lạc quan và giao dịch có thay thế nhau không?

### 10.1. Atomic update trên một document

Trong nhiều bài toán tồn kho, có thể dùng một thao tác:

```javascript
db.inventory.updateOne(
  {
    _id: skuId,
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2 }
  }
);
```

Điều kiện **được kiểm tra tại bước ghi nguyên tử**, nên hai writer không thể cùng trừ hai lần dựa vào cùng số tồn mà vượt điều kiện một cách âm thầm.

Nếu yêu cầu chỉ nằm trong **một document**, transaction nhiều document không tạo thêm lợi ích atomicity cần thiết.

### 10.2. Optimistic locking với `version`

Một cách phát hiện client gửi bản chỉnh sửa dựa trên dữ liệu cũ:

```javascript
db.products.updateOne(
  {
    _id: productId,
    version: expectedVersion
  },
  {
    $set: { priceCents: newPriceCents },
    $inc: { version: 1 }
  }
);
```

Nếu `matchedCount:0`, không có document khớp cả ID lẫn version. Cần phân biệt not found và stale version nếu API muốn trả lỗi chi tiết.

Đây là **compare-and-set** (CAS), hữu ích cho chỉnh sửa một document. Nó không tự làm nhiều document cùng commit, nhưng cũng không đòi mở transaction dài chỉ để kiểm tra version.

### 10.3. Multi-document transaction

Transaction phù hợp khi bất biến nghiệp vụ trải nhiều thao tác:

```text
Debit A + Credit B + Insert ledger
              |
              v
       one transaction
```

Nhưng ngay cả transaction cũng có thể cần:

- Unique index cho khóa nghiệp vụ.
- CAS/version hoặc điều kiện trạng thái khi người dùng chỉnh từ snapshot cũ.
- Idempotency key cho duplicate request.
- Transaction retry/abort policy.
- Định nghĩa isolation/invariant phù hợp.

Không có giải pháp nào trong ba giải pháp trên thay thế hoàn toàn hai giải pháp còn lại.

### 10.4. Bảng quyết định

| Tình huống | Công cụ khởi đầu thường phù hợp |
| --- | --- |
| Trừ tồn kho trong một document nếu đủ | `updateOne` với predicate và `$inc` |
| Chỉnh thông tin một document từ form có version | `updateOne` với `version` (CAS) |
| Tạo đơn và ghi ledger ở hai collection cần atomicity | Multi-document transaction |
| Ngăn hai lệnh tạo cùng business ID | Unique index; thêm idempotency khi cần |
| Gửi email sau khi commit transaction | Transactional outbox / idempotent worker |
| Update một triệu document có thể chia nhỏ | Batch có checkpoint, không mặc định một transaction lớn |
| Nhiều writer tranh một counter đơn | Atomic update, sharded counter hoặc mô hình phù hợp tùy contention |

## 11. Những anti-pattern khiến transaction kéo dài

### 11.1. Đặt gọi HTTP trong transaction

```javascript
await session.withTransaction(async () => {
  await orders.updateOne(
    { _id: orderId },
    { $set: { status: "PROCESSING" } },
    { session }
  );

  // KHÔNG NÊN: latency bên ngoài kéo dài transaction,
  // và callback có thể được driver retry.
  await paymentGateway.capture(paymentId);
});
```

Vấn đề không chỉ là chậm:

- Nếu transaction abort, thanh toán ngoài MongoDB không tự được hoàn tác.
- Nếu callback retry, charge có thể xảy ra lần nữa.
- Transaction giữ tài nguyên trong lúc chờ network.

Kiến trúc thay thế thường là **state machine + outbox + idempotent consumer**:

```text
Transaction ngắn:
  update order state
  insert outbox event
  COMMIT
       |
       v
Worker đọc outbox (sau commit)
       |
       v
Gọi paymentGateway với idempotency key
       |
       v
Ghi lại kết quả bằng transaction/update thích hợp
```

Đây là một mô hình **eventual workflow**, không có nghĩa toàn bộ MongoDB và cổng thanh toán tự trở thành một giao dịch nguyên tử phân tán. Cần xử lý retry, trạng thái trung gian, đối soát và compensation theo nghiệp vụ.

### 11.2. Chờ người dùng trong transaction

```text
BEGIN -> tạo bản nháp -> chờ người dùng click xác nhận -> COMMIT
```

Đây là anti-pattern. Thời gian phản hồi của người dùng có thể là vài giây hoặc vài giờ, vượt xa transaction lifetime và tốn tài nguyên vô ích.

Thay thế:

1. Lưu trạng thái nháp/đề nghị riêng theo hợp đồng nghiệp vụ.
2. Đợi xác nhận **ngoài transaction**.
3. Khi nhận xác nhận, mở transaction **mới** ngắn.
4. Kiểm lại giá, tồn kho, version và điều kiện đã thay đổi.
5. Commit hoặc trả xung đột nếu điều kiện không còn đúng.

### 11.3. Duyệt cursor lớn trong transaction

```javascript
await session.withTransaction(async () => {
  // Nguy cơ: đọc nhiều dữ liệu và chạy vòng lặp rất lâu.
  const cursor = orders.find(
    { status: "PENDING" },
    { session }
  );
  for await (const order of cursor) {
    await processOrderWithMoreQueries(order, session);
  }
});
```

Nếu không có yêu cầu atomicity cho toàn bộ batch, hãy chia nhỏ theo page/key có checkpoint và transaction theo đơn/nhóm nhỏ. Nếu thật sự cần tính nguyên tử cho toàn bộ batch, cần đánh giá mô hình thay thế (materialized state, staging collection, versioned release) thay vì mặc định một transaction khổng lồ.

### 11.4. Transaction chứa truy vấn không dùng index

Ví dụ trong transaction:

```javascript
await orders.findOne(
  {
    tenantId,
    externalOrderId
  },
  { session }
);
```

Nếu API thực thi hàng nghìn lần mỗi giây, không có index phù hợp trên `{tenantId,externalOrderId}` thì truy vấn có thể quét nhiều document, kéo dài transaction và tăng cạnh tranh.

Một compound index tương thích với query pattern và unique constraint (nếu cần) giúp giới hạn thời gian truy vấn, nhưng mỗi index cũng làm tăng chi phí ghi. Thiết kế index theo workload và xác minh kế hoạch **ngoài transaction** khi thích hợp; không chỉ thêm index hàng loạt.

### 11.5. Gửi song song các operation trong cùng transaction

```javascript
// Không nên:
await session.withTransaction(async () => {
  await Promise.all([
    accounts.updateOne(filterA, updateA, { session }),
    accounts.updateOne(filterB, updateB, { session })
  ]);
});
```

MongoDB Node.js driver không hỗ trợ chạy nhiều operation song song trong cùng một transaction theo kiểu này. Hãy chạy **tuần tự**:

```javascript
await session.withTransaction(async () => {
  await accounts.updateOne(filterA, updateA, { session });
  await accounts.updateOne(filterB, updateB, { session });
});
```

Nếu muốn tăng throughput, hãy thiết kế concurrency **giữa những transaction độc lập**, với giới hạn tài nguyên và kiểm soát xung đột, không phải Promise.all trên cùng session/transaction.

## 12. Monitoring: nhìn thấy transaction dài ở đâu?

### 12.1. `serverStatus().transactions`

Khi có quyền đọc metrics:

```javascript
const status = db.serverStatus();

printjson(status.transactions);
```

Trong các phiên bản phù hợp, nhóm này có thể chứa những số liệu như:

- `currentOpen`: số transaction đang mở.
- `currentActive`: số transaction đang thực thi operation.
- `currentInactive`: transaction mở nhưng hiện không thực thi operation.
- `totalStarted`: tổng số transaction đã bắt đầu.
- `totalCommitted`: tổng số transaction đã commit.
- `totalAborted`: tổng số transaction đã abort.

Tên và định nghĩa field có thể khác theo phiên bản. Nếu một phiên bản không có field nào đó, không tự coi nó bằng 0. Theo dõi **chuỗi thời gian** thay vì chỉ một snapshot.

`currentInactive` cao là dấu hiệu cần điều tra; có thể đến từ transaction đang chờ ứng dụng, nhưng cũng có workload hợp lệ hoặc đặc điểm đo lường khác. Cần correlating application traces và thời lượng transaction.

### 12.2. Xem operation đang hoạt động

Tùy quyền và phiên bản:

```javascript
const active = db.currentOp({ active: true });

printjson(active);
```

Khi có nhiều operation, kết quả có thể lớn và chứa namespace/query. Trong môi trường thật, lọc theo thông tin cần điều tra và tránh ghi log dữ liệu nhạy cảm. Một số phiên bản hỗ trợ lệnh `$currentOp` với các field transaction/session liên quan; xác định cú pháp theo phiên bản đang chạy.

Điều cần tìm:

- Operation nào đang chạy lâu?
- Session/transaction nào liên quan?
- Nó đang chạy command gì, trên namespace nào?
- Có chờ lock, wait hoặc có thời gian inactive lớn?
- Thời lượng query và thời lượng transaction có khác nhau không?

Không có một lệnh `currentOp` nào tự động chứng minh “request này chắc chắn là nguyên nhân duy nhất của cache pressure”. Phải kết hợp server metrics.

### 12.3. WiredTiger cache và eviction

Một cách khảo sát tổng quan:

```javascript
const server = db.serverStatus();

printjson({
  transactions: server.transactions ?? null,
  wiredTigerCache: server.wiredTiger?.cache ?? null
});
```

Đây là **read-only diagnostic**. `wiredTiger.cache` có thể chứa nhiều field và tên trường giữa các version không giống nhau. Trong production nên trích metric cần thiết từ monitoring thay vì dump toàn bộ cache output vào log.

Nếu transaction lâu đồng thời cache dirty/eviction pressure tăng, có thể nghi ngờ liên quan snapshot và write workload. Nhưng một bản đồ metric có thể chịu tác động của index, checkpoint, read query và các tác vụ khác.

### 12.4. Tracing ở tầng ứng dụng

Mỗi transaction quan trọng nên có correlation ID:

```text
request_id
business_operation_id
transaction_attempt
transaction_duration_ms
db_operations_inside_txn
write_conflict_count
commit_duration_ms
commit_outcome: CONFIRMED / UNKNOWN / FAILED
```

Những điểm nên ghi:

- Thời điểm bắt đầu và kết thúc transaction.
- Tên nhóm operation, không nhất thiết log toàn bộ câu query có dữ liệu cá nhân.
- Tỷ lệ retry, abort và các error labels.
- Kích thước batch, số document chạm tới.
- Thời gian chờ dịch vụ ngoài database — tốt nhất **nằm ngoài transaction**.

Nếu driver sử dụng command monitoring, lọc thông tin nhạy cảm trước khi xuất metrics; không log credentials, nội dung thanh toán hoặc payload khách hàng.

## 13. Điều tra sự cố: nhiều WriteConflict và transaction timeout

### 13.1. Phân loại triệu chứng

| Hiện tượng | Nguyên nhân cần kiểm tra | Biện pháp khởi đầu |
| --- | --- | --- |
| `WriteConflict` trên cùng document | Contention/hot key, snapshot cũ | Transaction ngắn, update nguyên tử, giảm đồng thời |
| `TransientTransactionError` | Write conflict hoặc lỗi tạm thời khác | Retry toàn transaction trong budget, kiểm error label |
| `UnknownTransactionCommitResult` | Kết quả commit chưa rõ | Theo retry commit của driver và đối soát operationId |
| `TransactionTooLargeForCache` | Quá nhiều thay đổi/snapshot cache | Giảm batch, thiết kế lại transaction |
| Transaction lifetime expired | Mở quá lâu | Bỏ wait/HTTP, tối ưu query, giảm số thao tác |
| Lock acquisition timeout | Đợi lock quá lâu | Xem operations cạnh tranh, metadata/DDL |
| `E11000` | Trùng unique key | Xử lý business conflict hoặc idempotency |
| Tốc độ commit chậm | Disk, network, majority write concern | Quan sát replication và I/O |
| Snapshot too old / history pressure | Transaction/snapshot lâu, churn cao | Giảm thời lượng, điều tra cache/history |
| Rất nhiều transaction inactive | Code mở nhưng chưa commit/abort, session lifecycle | Tracing, finally cleanup, kiểm driver usage |

Trước khi tăng retry, nên xác định liệu retry có **khả năng thành công** hay không. Một transaction vi phạm unique key hoặc dữ liệu invalid sẽ không tự hết lỗi chỉ vì thử lại.

### 13.2. Một quy trình triage ít xâm lấn

1. **Xác nhận lỗi**: mã lỗi, nhãn lỗi, operation, thời lượng, tỷ lệ xảy ra.
2. **Xác định hot key**: nhiều request có cập nhật cùng account/inventory/counter không?
3. **Đo duration**: thời gian toàn transaction so với từng query và commit.
4. **Kiểm tra lock/cache**: serverStatus, currentOp, Atlas/monitoring, disk latency.
5. **Kiểm tra query plan**: có lọc hiệu quả và index phù hợp không?
6. **Đánh giá topology/replication**: commit majority có chờ lâu do secondary hoặc mạng không?
7. **Giảm rủi ro**: throttle batch, giới hạn concurrency, tách side effect, giảm transaction scope.
8. **Xác minh**: tỷ lệ abort/commit, P95/P99 latency và resource metrics cải thiện sau điều chỉnh.

Không tự ý chạy lệnh `killOp`, thay transaction lifetime, tắt majority write concern hoặc reshard collection khi chưa có runbook/quyền, đặc biệt trên production.

### 13.3. Nếu hot document là nguồn tranh chấp

Ví dụ một document `dailyCounter` được hàng nghìn transaction cùng sửa:

```javascript
{
  _id: "daily-2026-11-14",
  count: 123456
}
```

Nếu mọi transaction đều update document này, nó trở thành một **điểm tranh chấp**, kể cả các transaction sửa những document khác. Có thể cân nhắc:

- Thực hiện cập nhật counter ngoài transaction nếu invariant cho phép và dùng atomic `$inc`.
- Dùng **bucketed/sharded counter** nếu chấp nhận tổng hợp từ nhiều document và consistency semantics thích hợp.
- Tạo queue hoặc nhóm ghi theo business key.
- Đổi mô hình để không phải cập nhật một document toàn cục trong mỗi transaction.
- Nếu vẫn phải bảo vệ invariant toàn cục, thiết kế serialization/lock ở một điểm rõ ràng thay vì vô tình ép mọi transaction tranh nhau.

Việc shard một collection không tự loại write conflict trên **cùng một document**. Đổi shard key chỉ thay phân bố dữ liệu, không cho phép hai transaction cùng sửa một record mà bỏ qua concurrency control.

## 14. Transaction trên sharded cluster có thêm chi phí gì?

### 14.1. Transaction chỉ chạm một shard và nhiều shard

Trong sharded cluster, một transaction có thể liên quan đến một hoặc nhiều shard tùy dữ liệu và routing. Khi chạm nhiều shard, commit cần sự phối hợp để các participant đạt trạng thái nguyên tử.

```text
Application
    |
  mongos
    |
    +-------------+
    |             |
    v             v
  Shard A       Shard B
   debit         credit
    |             |
    +---- commit coordination ----+
```

Chi phí có thể tăng vì network giữa các thành phần, transaction metadata, locking và các bước phối hợp commit. Với dữ liệu thường cùng được truy cập, lựa chọn shard key và mô hình document có thể ảnh hưởng số shard phải tham gia.

### 14.2. Cần đưa shard key vào filter khi phù hợp

Trong ứng dụng đa tenant:

```javascript
{
  _id: orderId,
  tenantId: authenticatedTenantId
}
```

Nếu collection sharded theo `tenantId`, điều kiện đầy đủ giúp định tuyến và kiểm soát phạm vi. Thiếu shard key có thể khiến truy vấn phải đi qua nhiều shard, tùy operation và phiên bản.

Không nên tự giả định mọi transaction nhiều shard chậm hơn mọi transaction một shard: hãy **đo** với workload thực tế. Nhưng nếu business invariant nằm trọn trong một document hoặc một shard, thiết kế dữ liệu phù hợp có thể giảm chi phí phối hợp.

### 14.3. DDL, chunk migration và giới hạn theo phiên bản

Transaction có tương tác với các thao tác quản trị/DDL như tạo collection, tạo index, đổi cấu trúc và di chuyển chunk. Khả năng thực hiện DDL trong transaction và cách các thao tác này chờ nhau **phụ thuộc phiên bản MongoDB và loại deployment**.

Không mở transaction dài bao phủ một đợt migration dữ liệu rồi chạy DDL tùy ý, kỳ vọng mọi thay đổi đều được hỗ trợ. Phối hợp lịch thay đổi schema/index với transaction workload, test trên môi trường tương đương production và tham khảo tài liệu phiên bản cụ thể.

## 15. Timeout: transaction, lock, lệnh, server selection và HTTP

### 15.1. Nhiều loại timeout hoạt động ở các tầng khác nhau

```text
HTTP request deadline
    |
    +-- driver server selection timeout
    |
    +-- MongoDB command maxTimeMS / socket timeout
    |
    +-- transaction lifetime limit
    |
    +-- transaction lock request timeout
    |
    +-- commit writeConcern wtimeout
```

Không nên dùng một con số “timeout 30 giây” mà không chỉ rõ nó thuộc tầng nào.

| Timeout/giới hạn | Phạm vi | Kết quả có thể gặp |
| --- | --- | --- |
| HTTP/API deadline | Request ứng dụng | Client bỏ chờ, nhưng operation DB có thể chưa dừng ngay |
| `serverSelectionTimeoutMS` | Driver chọn node phù hợp | Không tìm được primary/secondary trong thời hạn |
| `maxTimeMS` hoặc driver deadline | Thời gian chạy một lệnh trong phạm vi hỗ trợ | Command có thể bị ngắt theo chính sách server |
| `transactionLifetimeLimitSeconds` | Vòng đời transaction | Transaction quá tuổi có thể bị abort |
| `maxTransactionLockRequestTimeoutMillis` | Đợi lock cần thiết trong transaction | Lock timeout/abort tùy tình huống |
| `wtimeout` | Chờ write concern acknowledgment | Kết quả ghi có thể chưa rõ theo mức xác nhận |

Một số timeout dùng đơn vị **mili giây**, trong khi lifetime dùng **giây**. Không nhân/chia thiếu đơn vị khi chuyển cấu hình.

### 15.2. Một request timeout không có nghĩa transaction đã abort

Nếu reverse proxy kết thúc HTTP request trước khi callback MongoDB hoàn tất, backend có thể vẫn đang thực thi transaction nếu code không quản lý cancellation/deadline. Cần thiết kế:

- Deadline được truyền và kiểm soát xuyên tầng.
- `finally` để kết thúc session và abort khi cần.
- Không để background callback vô tình tiếp tục ghi sau khi client đã nhận lỗi mà không có idempotency.
- Theo dõi transaction duration thực tế, không chỉ thời gian trả response HTTP.

Đừng đánh đồng việc client ngắt kết nối với một lệnh `abortTransaction` chắc chắn đã chạy.

### 15.3. Commit timeout cần đối soát

Nếu `commitTransaction` gặp timeout/unknown result:

```text
Database: commit có thể đã hoàn tất.
Client:    chưa nhận được lời xác nhận chắc chắn.
```

Đây là trạng thái **chưa xác định**, không phải chắc chắn failed. Phải nhờ driver xử lý retry commit theo tài liệu và dùng business operation ID để đối soát thay vì tạo lại transaction nghiệp vụ bằng khóa mới.

## 16. Thiết kế transaction ngắn: phương pháp thực hành

### 16.1. Tách chuẩn bị khỏi vùng nguyên tử

Ví dụ quy trình tạo đơn:

```text
NGOÀI TRANSACTION
  - xác thực người dùng
  - validate input
  - tính thuế/phí dự kiến
  - lấy thông tin tham chiếu không cần giữ snapshot
  - chuẩn bị operationId

TRONG TRANSACTION NGẮN
  - kiểm điều kiện tồn kho hiện tại
  - trừ số lượng
  - tạo đơn
  - tạo outbox event
  - commit

SAU COMMIT
  - worker gửi sự kiện/thông báo
  - gọi dịch vụ bên ngoài bằng idempotency key
  - đối soát nếu có lỗi
```

Thông tin chuẩn bị ngoài transaction có thể **đã cũ** trước khi commit. Vì thế những điều kiện ảnh hưởng trực tiếp đến tính đúng đắn (giá có còn hiệu lực, tồn kho đủ, phiên bản catalog, quyền vận hành...) phải được **kiểm tra lại hoặc cưỡng chế trong transaction/atomic write** khi cần.

### 16.2. Chỉ giữ các câu query thực sự cần thiết

Thay:

```text
BEGIN
  query 1.000 orders
  fetch customer details nhiều lần
  tính báo cáo
  gọi HTTP
  update hai documents
COMMIT
```

bằng:

```text
Outside:
  đọc dữ liệu tham khảo, tính dữ liệu dự kiến

BEGIN:
  đọc/check những field phải nhất quán
  update đúng tài liệu theo khóa
  insert ledger/outbox
COMMIT

Outside:
  phát sự kiện và trả phản hồi
```

Đối với những truy vấn bắt buộc trong transaction, thiết kế index phục vụ filter. Nếu thấy COLLSCAN trên collection lớn, transaction dài có thể chỉ là **triệu chứng của query kém**, không phải vấn đề do API transaction.

### 16.3. Xử lý bulk data bằng checkpoint

Một script migration 500.000 document không nhất thiết phải đặt trong **một transaction**:

1. Chia thành các lô theo khóa ổn định.
2. Mỗi lô xử lý một tập document rõ.
3. Ghi checkpoint/idempotency state.
4. Có khả năng chạy lại hoặc tiếp tục sau lỗi.
5. Có bước xác minh tính nhất quán cuối cùng.

Nếu nghiệp vụ bắt buộc chuyển toàn bộ dữ liệu “một lần” với không thời gian thấy trạng thái trung gian, cân nhắc staging collection, versioned pointer/swap hoặc mô hình chuyển đổi khác được thiết kế riêng. Không mặc định chia batch là đúng nếu nó làm mất invariant toàn cục.

### 16.4. Điều chỉnh contention trước khi tăng tài nguyên

Thêm CPU/RAM có thể giúp khi thiếu capacity, nhưng nếu 1000 writer cùng update một document nóng, contention về tính đúng đắn vẫn còn. Các hướng xử lý:

- Giảm độ dài transaction.
- Giảm số operation trên hot record.
- Giảm concurrency theo business key.
- Dùng atomic update nếu transaction không cần.
- Đổi mô hình aggregate/bucket.
- Retry có budget và backoff.

Đo lại abort rate và latency sau thay đổi, không chỉ xem CPU.

## 17. Một số hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| “MongoDB transaction giống lock cả database” | MongoDB dùng concurrency control/lock nhiều cấp; không giữ global exclusive lock cho mọi transaction |
| “Mở transaction càng sớm càng an toàn” | Mở sớm tăng thời gian giữ snapshot/tài nguyên |
| “Chỉ commit ở cuối là đủ, chờ HTTP trong transaction cũng được” | Chờ bên ngoài làm txn dài và side effect không rollback theo MongoDB |
| “Snapshot có nghĩa mọi writer khác phải chờ tôi” | Writer khác có thể tiếp tục; transaction của bạn có thể gặp write conflict |
| “WriteConflict nghĩa database bị hỏng” | Thường là cạnh tranh ghi hợp lệ; cần retry/đổi thiết kế |
| “WriteConflict và DuplicateKey là một” | Khác mã lỗi và chính sách xử lý |
| “Cứ tăng maxTransactionLockRequestTimeoutMillis là hết conflict” | Lock wait timeout không bao trùm mọi write conflict |
| “Transaction 60 giây là mặc định nên nên dùng gần đủ 60 giây” | 60 giây chỉ là default phổ biến cho lifetime, không phải mục tiêu SLA |
| “Cứ retry ngay liên tục sẽ thành công” | Có thể làm contention cao hơn; cần backoff/limit |
| “Retry một câu update trong transaction cũ là đủ” | Snapshot cũ không tự làm mới sau write conflict; thường cần transaction mới |
| “Unknown commit result nghĩa chưa ghi” | Commit có thể đã thành công; cần retry commit/đối soát |
| “Driver tự retry nên callback có thể gửi email” | Callback có thể chạy nhiều lần; side effect có thể lặp |
| “Unique index không cần nếu đã có transaction” | Transaction không tạo invariant uniqueness nếu không có ràng buộc phù hợp |
| “Một update trên một document phải dùng transaction” | MongoDB vốn bảo đảm atomicity ở cấp một document |
| “Batch một triệu document trong một transaction luôn tốt hơn” | Cache, time, contention và replication cost có thể rất lớn |
| “Thêm RAM là hết contention cùng hot document” | Contention logic vẫn tồn tại |
| “Mọi transaction đều tạo một entry oplog duy nhất” | Có thể tạo nhiều oplog entries theo cơ chế/phiên bản |
| “Retryable error và business conflict có thể xử lý giống nhau” | Lỗi tạm thời, duplicate, validation, unknown commit cần chính sách khác |

## 18. Bài tập thực hành

### Bài A. Nhận diện giao dịch dài

Cho quy trình:

```text
BEGIN
  find customer
  HTTP call: check fraud (8 giây)
  find inventory
  update inventory
  HTTP call: charge card (12 giây)
  insert order
COMMIT
```

Hãy trả lời:

1. Các bước nào nên chuyển ra ngoài transaction?
2. Bước nào cần kiểm tra lại bên trong transaction?
3. Vì sao đặt charge card trong callback có retry là nguy hiểm?
4. Nếu charge đã thành công nhưng transaction abort, cần workflow/compensation nào?

### Bài B. Write conflict sau snapshot cũ

Document `{_id:"P1",version:3,price:100}`:

```text
A: start transaction, read version 3
B: update price=110, version=4, commit
A: update price=105 trong transaction cũ
```

Giải thích:

- Vì sao A có thể gặp WriteConflict?
- A có nên chỉ retry lệnh update trong transaction cũ không?
- Muốn A thực hiện cập nhật có kiểm tra phiên bản, có thể dùng CAS như thế nào?
- Nếu A và B cùng sửa một field giá, liệu tự động ưu tiên A có đúng nghiệp vụ?

### Bài C. Hai lỗi có cách retry khác nhau

So sánh:

```text
Case 1:
  Transaction update -> WriteConflict (TransientTransactionError)

Case 2:
  commitTransaction -> mạng mất, UnknownTransactionCommitResult
```

Trong mỗi case, nên retry cái gì: **toàn bộ transaction**, **commit của transaction hiện tại**, hay **đối soát business operation**? Vì sao việc tạo operationId mới khi retry case 2 có thể nguy hiểm?

### Bài D. Tranh chấp một document nóng

Hệ thống có một document `globalCounter`. Mỗi request tạo đơn đều:

```text
BEGIN
  update globalCounter
  insert order
COMMIT
```

Khi có 500 request đồng thời, WriteConflict tăng mạnh. Hãy đề xuất ít nhất ba thay đổi có thể giảm contention **mà vẫn giữ invariant cần thiết**, và chỉ rõ invariant nào phải phân tích lại nếu tách counter thành nhiều document.

### Bài E. Không thể giải quyết bằng tăng lifetime

Một transaction đã được nâng `transactionLifetimeLimitSeconds` từ 60 lên 300. Tỷ lệ abort vẫn cao; `wiredTiger.cache` đang chịu áp lực lớn.

Hãy nêu:

- Những metric cần quan sát.
- Vì sao tăng lifetime có thể làm tình hình tệ hơn.
- Những bước tối ưu không cần thay config.
- Khi nào nên cân nhắc mô hình batch/checkpoint.

### Bài F. Transaction trên nhiều shard

Một transaction chuyển điểm giữa hai ví ở hai tenant khác shard:

1. Tại sao commit có thể cần thêm coordination?
2. Việc có đủ shard key trong filter ảnh hưởng gì tới routing?
3. Cách nào có thể giảm thời gian transaction?
4. Vì sao không nên chỉ tối ưu cho “một shard” mà bỏ yêu cầu phân quyền/uniqueness?

## 19. Hướng dẫn dọn dữ liệu thử nghiệm

Phần thử nghiệm `mongosh` chỉ tạo một document ở `mongo_tx_row252_lab.inventory_demo`. Trước khi dọn, phải xác nhận đúng kết nối, database, document ID và `runId` trong phiên hiện tại:

```javascript
print("database=" + lab.getName());
print("collection=" + inventory.getName());
print("runId=" + runId);

const owned = inventory.findOne(
  { _id: skuId, runId },
  { _id: 1, runId: 1, sku: 1, available: 1 }
);

printjson(owned);
```

Khi đã kiểm tra đây chính là document bạn tạo:

```javascript
const result = inventory.deleteOne({
  _id: skuId,
  runId
});

printjson(result);
print("remaining=" + inventory.countDocuments({
  _id: skuId,
  runId
}));
```

Không chạy `deleteMany({})`, `drop()` hoặc `dropDatabase()` trong database dùng chung. Nếu transaction test đã để lại một session mở hoặc đang hoạt động, hãy **abort/endSession** theo quyền và chính sách trước khi dọn. Không sửa `local.oplog.rs`, cấu hình replica set hoặc những document không thuộc lượt thực hành.

## 20. Tài liệu tham khảo chính thức

Khi triển khai, sử dụng tài liệu ứng với **phiên bản MongoDB và driver thực tế**:

- [Transactions — MongoDB Manual](https://www.mongodb.com/docs/manual/core/transactions/) — cơ chế và phạm vi multi-document transactions.
- [Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — thời gian, locks, cache và vận hành.
- [Transactions and Read Concern](https://www.mongodb.com/docs/manual/core/transactions/#transactions-and-read-concern) — ngữ nghĩa đọc trong transaction.
- [Transactions and Write Concern](https://www.mongodb.com/docs/manual/core/transactions/#transactions-and-write-concern) — xác nhận commit.
- [TransactionTooLargeForCache](https://www.mongodb.com/docs/manual/reference/error-codes/) — đối chiếu mã lỗi/tên lỗi theo server version.
- [Node.js Driver — Transactions](https://www.mongodb.com/docs/drivers/node/current/fundamentals/transactions/) — `withTransaction`, session, retry và giới hạn driver.
- [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — metrics server.
- [currentOp](https://www.mongodb.com/docs/manual/reference/method/db.currentOp/) — quan sát operations.
- [Transaction Lifetime Limit](https://www.mongodb.com/docs/manual/reference/parameters/#mongodb-parameter-param.transactionLifetimeLimitSeconds) — cấu hình lifetime theo phiên bản.

## 21. Kết luận

MongoDB multi-document transaction giúp **nhiều thao tác MongoDB cùng commit hoặc cùng abort**, nhưng không có nghĩa transaction nên bao trùm mọi bước của một quy trình nghiệp vụ. **Giao dịch dài** giữ snapshot và tài nguyên lâu hơn, có thể gây áp lực WiredTiger cache, tăng thời gian chờ lock, tăng khả năng gặp write conflict, timeout và abort, đặc biệt khi khối lượng ghi hoặc số request đồng thời lớn.

**WriteConflict** là dấu hiệu quan trọng của concurrency control: transaction đang dựa trên snapshot/điều kiện không còn phù hợp với thay đổi đồng thời. Lỗi tạm thời có thể cần **retry toàn transaction từ snapshot mới**; trong khi **UnknownTransactionCommitResult** cần cách xử lý commit và đối soát khác. Không retry mù quáng một business operation với ID mới, không bỏ unique constraint, và không gọi dịch vụ ngoài MongoDB trong callback có thể được retry.

Thiết kế an toàn bắt đầu bằng ba nguyên tắc: **giữ transaction ngắn**, **cưỡng chế bất biến ở bước ghi bằng điều kiện/index phù hợp**, và **giới hạn retry kèm idempotency/quan sát tài nguyên**. Khi một thao tác chỉ cần atomicity của một document, ưu tiên lệnh ghi nguyên tử đơn giản; khi thật sự cần multi-document atomicity, dùng transaction có phạm vi chặt, đo duration/abort rate và chuẩn bị quy trình xử lý xung đột rõ ràng.
