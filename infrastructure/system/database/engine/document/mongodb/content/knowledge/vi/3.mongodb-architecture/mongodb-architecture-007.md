# Khóa, điều khiển đồng thời và xung đột ghi trong storage engine MongoDB

Khi nhiều người dùng cùng đọc và cập nhật một cơ sở dữ liệu, các thao tác có thể chạm tới cùng collection, document hoặc index. Vì sao hai cập nhật trên những document khác nhau có thể chạy song song? Vì sao transaction bị hủy dù các lệnh đều hợp lệ? Và tại sao hai lệnh ghi thành công vẫn có thể làm mất một thay đổi nghiệp vụ? Các câu hỏi đó thuộc chủ đề **khóa (locking), điều khiển đồng thời (concurrency control) và xung đột ghi (write conflict)**.

Bài học giải thích kiến trúc MongoDB với **WiredTiger storage engine**: khóa phân cấp của MongoDB Server, kiểm soát ghi mức document của WiredTiger, optimistic concurrency, MVCC, hành vi transaction và cách quan sát tranh chấp. Các ví dụ dùng **mongosh** trên database thực hành `concurrency_lab`.

Sau bài học, bạn có thể:

1. Phân biệt khóa ở **global/database/collection** với kiểm soát ghi ở **document**.
2. Đọc bốn chế độ khóa **IS, IX, S, X**, hiểu tại sao một số thao tác đợi nhau.
3. Giải thích **MVCC**, snapshot và **optimistic concurrency control**.
4. Phân biệt **write conflict**, **lock wait**, **lost update** và lỗi ràng buộc dữ liệu.
5. Thiết kế cập nhật an toàn với **`$inc`, điều kiện trong update, compare-and-set** và transaction khi cần.
6. Dùng `serverStatus`, `currentOp` và các metrics để nhận diện nguyên nhân gây chậm hoặc retry.

> **Giới hạn ngữ cảnh:** WiredTiger là storage engine mặc định trong MongoDB Server thông thường; các triển khai chuyên biệt như Atlas Infinite có kiến trúc lưu trữ khác. Tên metric và tham số có thể khác theo nhánh phát hành. Trước khi sử dụng thao tác quản trị, cần tra cứu tài liệu đúng phiên bản server và môi trường thực tế.

## 1. Hai tầng điều khiển đồng thời

MongoDB Server và WiredTiger cùng tham gia quản lý truy cập dữ liệu, nhưng ở những tầng khác nhau:

~~~text
Ứng dụng / mongosh / driver
           |
           v
MongoDB Server
  - xử lý command, query plan, transaction
  - lock manager nhiều cấp:
      Global -> Database -> Collection
  - intent locks: IS, IX; shared/exclusive: S, X
           |
           v
WiredTiger storage engine
  - document-level write concurrency
  - optimistic concurrency + phát hiện write conflict
  - Multi-Version Concurrency Control (MVCC)
  - cache, journal, checkpoint và admission
           |
           v
     dữ liệu và index
~~~

MongoDB dùng **multi-granularity locking**, cho phép yêu cầu khóa ở những mức khác nhau. Với phần lớn lệnh đọc/ghi dữ liệu, server dùng **intent locks** ở mức global, database và collection. WiredTiger kiểm soát tranh chấp ghi ở **mức document**, nên những client cùng ghi vào **các document khác nhau trong một collection** thường có thể tiến triển đồng thời.

Điều đó không có nghĩa server "không khóa collection": intent lock vẫn là khóa ở mức collection. Đồng thời, một số thao tác quản trị/metadata vẫn cần khóa mạnh hơn, như exclusive lock trong một số trường hợp. Không nên suy từ chế độ khóa ở tầng trên rằng tất cả thao tác bên dưới đều không có tranh chấp.

### 1.1. Lock granularity là mức nào?

Giả sử một lệnh sửa document:

~~~javascript
db.getSiblingDB("shop").orders.updateOne(
  { _id: 42 },
  { $inc: { retryCount: 1 } }
)
~~~

Tài nguyên được truy cập theo thứ bậc:

~~~text
Global: mongod
  └── Database: shop
      └── Collection: orders
          └── Document: _id = 42
~~~

**Lock manager** dùng các mức trên đến collection. Khi muốn truy cập một đối tượng con, thao tác báo "ý định" ở các mức cha; ví dụ muốn ghi ở cấp nhỏ hơn cần một **intent exclusive (IX)** tương ứng. **WiredTiger** xử lý điều khiển đồng thời mức document bên trong storage engine; không phải cứ nói "document-level concurrency" là có một đối tượng `DocumentLock(_id)` độc lập hiển thị trong `currentOp.locks`.

### 1.2. Bốn chế độ khóa IS, IX, S và X

| Chế độ | Tên đầy đủ | Ý nghĩa | Mã trong thống kê khóa MongoDB |
|---|---|---|---|
| **IS** | Intent Shared | Có ý định đọc/khóa chia sẻ tài nguyên cấp dưới. | `r` |
| **IX** | Intent Exclusive | Có ý định ghi/khóa độc quyền ở cấp dưới. | `w` |
| **S** | Shared | Cùng đọc tài nguyên đang được khóa. | `R` |
| **X** | Exclusive | Giữ khóa độc quyền đối với chính tài nguyên đó. | `W` |

Bảng tương thích cho **hai yêu cầu trên cùng một tài nguyên**:

| Đang giữ \ Yêu cầu | IS | IX | S | X |
|---|:---:|:---:|:---:|:---:|
| **IS** | ✓ | ✓ | ✓ | ✗ |
| **IX** | ✓ | ✓ | ✗ | ✗ |
| **S** | ✓ | ✗ | ✓ | ✗ |
| **X** | ✗ | ✗ | ✗ | ✗ |

Ví dụ, hai client đều giữ IX trên `orders` là điều có thể xảy ra vì **IX tương thích IX**. Nhưng nếu một tác vụ yêu cầu **X trên cùng collection**, nó không tương thích với IX nên phải chờ hoặc khiến thao tác khác chờ. Nếu lấy X trên collection, hệ thống còn dùng intent lock tương ứng trên database và global để quản lý toàn bộ cây tài nguyên.

Đối với phần lớn CRUD, WiredTiger không cần một X lock trên **toàn collection** cho mỗi lần sửa một document. Tuy nhiên, các thao tác DDL có ngữ nghĩa khác; `renameCollection` chẳng hạn có thể đòi hỏi exclusive database lock trong một số trường hợp. Tùy phiên bản và giai đoạn thực thi, tạo index cũng có các yêu cầu khóa riêng.

### 1.3. Lock contention là gì?

**Lock contention** xảy ra khi một operation cần khóa không tương thích với khóa mà operation khác đang giữ, nên phải **đợi cấp khóa**. Trong hệ thống thực, cần phân biệt:

- **Đợi lock**: lock manager chưa cấp khóa theo yêu cầu.
- **Đợi storage ticket/admission**: operation chưa được cấp suất vào storage engine dù có thể không bị X lock collection.
- **Đợi I/O**: cần tải page hoặc flush dữ liệu, không nhất thiết do khóa.
- **Write conflict**: optimistic storage concurrency phát hiện cạnh tranh ghi không tương thích.

Các trạng thái đều có thể làm tăng latency, nhưng cách xử lý khác nhau. Chỉ thấy một request chậm chưa đủ để kết luận "database bị lock".

## 2. WiredTiger: optimistic concurrency ở mức document

WiredTiger quản lý dữ liệu và index với cơ chế **document-level concurrency control** cho ghi. Hai thao tác sửa các document khác nhau trong cùng collection thường không ngăn nhau chỉ vì cùng sử dụng collection đó.

~~~javascript
// Hai client độc lập có thể thực hiện đồng thời:
db.accounts.updateOne({ _id: "A" }, { $inc: { balance: 10 } })
db.accounts.updateOne({ _id: "B" }, { $inc: { balance: 20 } })
~~~

Hai lệnh cùng có thể giữ IX ở mức collection. Mỗi thao tác làm việc với document riêng. Điều này không đảm bảo throughput tăng tuyến tính vì các client vẫn chia sẻ CPU, cache, disk, index và giới hạn concurrency của storage engine.

### 2.1. Optimistic concurrency control hoạt động như thế nào?

Khác với mô hình **pessimistic locking** cố giữ quyền độc quyền từ sớm, cơ chế **optimistic concurrency control (OCC)** cho phép các thao tác cùng tiến triển khi kỳ vọng phần lớn truy cập không xung đột. Đến lúc cần thực hiện thay đổi, storage engine kiểm tra các phiên bản/trạng thái liên quan. Nếu hai thao tác không thể hoàn tất với giả định ban đầu, hệ thống phát hiện **write conflict** và một thao tác phải thử lại hoặc bị hủy theo ngữ cảnh.

~~~text
Client A                           Client B
    |                                  |
    |  truy cập document X             |  truy cập document X
    |                                  |
    +------- yêu cầu sửa X ------------+------- yêu cầu sửa X
                    |
            WiredTiger kiểm tra
          tính tương thích của ghi
                    |
             WRITE CONFLICT
                    |
        một thao tác tiến triển;
        thao tác kia retry / abort
        tùy lệnh và transaction
~~~

Với **thao tác ghi thông thường ngoài multi-document transaction**, MongoDB có cơ chế **retry nội bộ** khi WiredTiger phát hiện conflict. Client thường chỉ nhận kết quả của lệnh sau xử lý, không thấy từng lần thử lại. Nhưng không nên suy thành "mọi thao tác đều retry vô hạn và chắc chắn thành công": transaction, giới hạn tài nguyên, timeout và các lỗi khác có thể làm yêu cầu thất bại.

Khi nhiều client liên tục sửa **cùng một document nóng (hot document)**, công việc bị xung đột và thực hiện lại có thể chiếm đáng kể tài nguyên. Đây là một hạn chế về contention dù việc khóa collection đã được giảm tối đa.

### 2.2. Vì sao không thể dùng lock mode để suy ra mọi write conflict?

Trên collection, client A và B đều có thể giữ IX vì IX–IX tương thích. Tuy nhiên, hai client vẫn có thể cùng sửa `_id: "A"`. Lock manager tầng trên cho phép cả hai tiến triển; **storage engine** mới phát hiện xung đột tài nguyên dữ liệu phía dưới. Vì vậy:

> **IX compatible không có nghĩa tất cả ghi sẽ thành công mà không tranh chấp.** Nó chỉ nói các yêu cầu khóa IX trên **cùng tài nguyên khóa** có thể cùng tồn tại.

Ngược lại, nếu một operation cần X trên collection, nó có thể gặp **lock wait** từ các khóa intent đang tồn tại trước khi tiến đến bước sửa document. Đây là loại chờ khác với write conflict.

## 3. MVCC và snapshot: người đọc thấy phiên bản nào?

**Multi-Version Concurrency Control (MVCC)** cho phép WiredTiger quản lý các phiên bản dữ liệu để operation có thể quan sát một **snapshot**. Người đọc có một góc nhìn nhất quán phù hợp ngữ nghĩa của thao tác, thay vì nhìn thấy một document đang được ghi dở.

Ví dụ khái niệm:

~~~text
Thời gian ------ t0 -------- t1 ------- t2 ----->

Document X:
  t0: balance = 100 (V1)
  t1: ghi mới
  t2: balance = 130 (V2)

Read A dùng góc nhìn tại t0 -> có thể thấy V1
Read B bắt đầu sau khi ghi  -> có thể thấy V2
~~~

Với snapshot cũ, một thao tác đọc có thể tiếp tục quan sát V1 trong khi hệ thống đã có V2. Tuy nhiên, **không được coi tất cả lệnh đọc MongoDB đều có cùng một bảo đảm isolation**. Kết quả cụ thể phụ thuộc read concern, transaction, replica set và thời điểm đọc.

| Khái niệm | Ý nghĩa cần giữ riêng |
|---|---|
| **WiredTiger snapshot** | Góc nhìn trạng thái dữ liệu mà storage engine cung cấp cho một operation. |
| **`readConcern: "local"`** | Đọc dữ liệu ở node theo mức đảm bảo `local`; không tự đồng nghĩa dữ liệu đã được majority commit. |
| **`readConcern: "majority"`** | Bảo đảm liên quan dữ liệu đã majority committed theo điều kiện của MongoDB. |
| **`readConcern: "snapshot"`** | Bảo đảm snapshot ở ngữ cảnh hỗ trợ, thường dùng trong transaction. |
| **Transaction snapshot** | Góc nhìn dùng trong transaction; có thể không thấy ghi mà client khác vừa commit sau snapshot. |

### 3.1. Stale read trong transaction

Giả sử transaction T đã đọc account A theo snapshot ban đầu. Một client khác sửa A và commit; khi T đọc lại, T **có thể thấy dữ liệu cũ**. Nếu T sau đó cố ghi A dựa trên snapshot không còn tương thích, transaction có thể bị **write conflict** và abort.

Điều này không có nghĩa MongoDB lưu dữ liệu sai: snapshot được thiết kế để giữ một góc nhìn đọc theo hợp đồng isolation. Ứng dụng phải hiểu khi nào mình cần nhìn thấy dữ liệu mới nhất và khi nào phải thử lại toàn bộ transaction.

### 3.2. Snapshot, journal và checkpoint không phải một thứ

WiredTiger có cơ chế **checkpoint** định kỳ để ghi một trạng thái nhất quán ra data files phục vụ phục hồi. **Journal** và **write concern** thuộc cơ chế durability và xác nhận ghi. Chúng khác với:

- **Concurrency**: ai có thể đọc/ghi cùng lúc và xung đột được phát hiện thế nào?
- **Atomicity**: thay đổi ở đơn vị nào là trọn vẹn hoặc không?
- **Isolation**: operation/transaction quan sát những phiên bản nào?
- **Durability**: thay đổi tồn tại sau lỗi máy hoặc failover ra sao?

Ví dụ, sử dụng `w: "majority"` **không** tự ngăn lost update của một lệnh `$set` được tính từ dữ liệu cũ. Đó là vấn đề của điều kiện ghi và logic nghiệp vụ, không phải riêng độ bền.

## 4. Atomicity một document và những lỗi thường bị nhầm

MongoDB bảo đảm **atomicity ở mức một document** cho một thao tác ghi, kể cả khi thay nhiều field trong document:

~~~javascript
db.accounts.updateOne(
  { _id: "A" },
  {
    $inc: { balance: -30 },
    $set: { updatedBy: "payment-service" }
  }
)
~~~

Đối với document A, thao tác này diễn ra trọn vẹn hoặc không. Tuy nhiên, `updateMany()` sửa nhiều document chỉ bảo đảm atomicity **trên từng document**, không tự biến toàn bộ tập cập nhật thành một transaction. Các thao tác khác có thể xen vào giữa các document đang được sửa.

### 4.1. Write conflict của storage engine

**Write conflict** được phát hiện khi những thay đổi đồng thời không phù hợp với quy tắc concurrency của WiredTiger. Server có thể retry một thao tác ghi đơn ngoài transaction, hoặc transaction có thể nhận lỗi/abort. Một counter write conflict tăng **không tự động** có nghĩa có cùng số request từ client đã thất bại.

### 4.2. Lost update ở tầng ứng dụng

Lỗi này có thể xảy ra **khi cả hai request đều được server báo thành công**:

~~~text
balance ban đầu = 100

Client A đọc 100                   Client B đọc 100
Client A tính 100 - 30 = 70       Client B tính 100 - 20 = 80
Client A $set balance = 70        Client B $set balance = 80

Kết quả cuối 80: cập nhật của A đã bị B ghi đè.
~~~

Hai lệnh không an toàn:

~~~javascript
// Giả sử hai client đã đọc balance=100 trước khi bất kỳ client nào ghi.
// Client A:
db.accounts.updateOne(
  { _id: "A" },
  { $set: { balance: 70 } }
)

// Client B:
db.accounts.updateOne(
  { _id: "A" },
  { $set: { balance: 80 } }
)
~~~

Mỗi `$set` vẫn nguyên tử ở mức document. Nhưng filter chỉ dùng `_id`, nên cả hai có thể hợp lệ; ghi sau ghi đè ghi trước. Cơ chế retry nội bộ của WiredTiger **không biết** phép tính `100 - 20` được thực hiện từ dữ liệu cũ trong ứng dụng.

### 4.3. Lock wait khác write conflict

| Hiện tượng | Nguồn gốc | Dấu hiệu / hướng xử lý |
|---|---|---|
| **Lock wait** | Lock manager đợi khóa không tương thích. | `waitingForLock`, `acquireWaitCount`, thời gian chờ; tìm DDL hoặc operation giữ khóa lâu. |
| **Write conflict** | WiredTiger phát hiện ghi không tương thích. | Retry nội bộ hoặc abort transaction; giảm hotspot và retry đúng phạm vi. |
| **Lost update** | Ứng dụng đọc dữ liệu cũ rồi ghi đè không điều kiện. | Dữ liệu nghiệp vụ sai dù lệnh thành công; dùng atomic update hoặc CAS. |
| **Duplicate key** | Unique index từ chối giá trị trùng. | Lỗi duplicate key, thường mã `11000`; xử lý theo bất biến dữ liệu. |
| **Write concern timeout** | Chưa đạt mức xác nhận ghi trong thời hạn. | Kiểm tra replication/trạng thái ghi trước khi tự gửi lại request. |
| **Admission wait** | Chờ read/write ticket vào storage engine. | Quan sát ticket queue và tải storage; không mặc định là collection lock. |

## 5. Cách viết update an toàn dưới tải đồng thời

### 5.1. Ưu tiên toán tử cập nhật nguyên tử

Khi cần tăng lượt truy cập hoặc cộng/trừ một lượng, sử dụng `$inc` thay vì đọc về ứng dụng rồi `$set`:

~~~javascript
db.getSiblingDB("concurrency_lab").counters.updateOne(
  { _id: "downloads" },
  { $inc: { count: 1 } },
  { upsert: true }
)
~~~

Với hai lần tăng thành công, biến đếm tăng hai đơn vị mà không mất một thay đổi do cả hai đọc giá trị cũ. Khi có điều kiện nghiệp vụ (ví dụ số dư phải đủ), đưa điều kiện **vào cùng update**:

~~~javascript
const result = db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A", balance: { $gte: 30 } },
  { $inc: { balance: -30 } }
)

if (result.matchedCount === 0) {
  print("Không tìm thấy account phù hợp hoặc không đủ số dư")
}
~~~

MongoDB kiểm tra điều kiện của lệnh update ngay tại thao tác cập nhật. Nếu một client khác đã trừ tiền khiến `balance < 30`, lệnh này sẽ không khớp. Đây là cách bảo vệ một **bất biến trên một document**.

Lưu ý: ví dụ số dư chỉ để minh họa concurrency, chưa bao gồm định danh giao dịch, ledger, chống xử lý trùng, hoàn tiền và các yêu cầu của hệ thống tài chính thực tế.

### 5.2. Compare-and-set bằng version field

Khi ứng dụng thực sự cần chuỗi **đọc document → chỉnh sửa ngoài database → ghi lại**, nên thêm một field `version` do ứng dụng quản lý:

~~~javascript
const lab = db.getSiblingDB("concurrency_lab")
lab.profiles.replaceOne(
  { _id: "user-1" },
  { _id: "user-1", displayName: "An", city: "Hà Nội", version: 1 },
  { upsert: true }
)

// Ứng dụng đã đọc version = 1.
const result = lab.profiles.updateOne(
  { _id: "user-1", version: 1 },
  {
    $set: { city: "Đà Nẵng" },
    $inc: { version: 1 }
  }
)

if (result.matchedCount === 0) {
  print("Dữ liệu đã được client khác sửa; hãy tải lại và hòa giải thay đổi")
}
~~~

Nếu hai client cùng có version 1, chỉ một update có thể chuyển version từ 1 lên 2. Client đến sau sẽ nhận `matchedCount = 0`. Kết quả này là **predicate không khớp**, không nhất thiết là lỗi `WriteConflict` của storage engine. Retry liên tục với `version: 1` sẽ không tự giải quyết được; phải đọc lại và quyết định merge, báo conflict hoặc thực hiện lại phép tính.

Đừng nhầm `version` logic của document với **Feature Compatibility Version (FCV)** của MongoDB Server hoặc phiên bản nội bộ trong MVCC.

### 5.3. `findOneAndUpdate` cho một bước đọc–sửa nguyên tử

~~~javascript
const updated = lab.accounts.findOneAndUpdate(
  { _id: "A", balance: { $gte: 25 } },
  { $inc: { balance: -25 } },
  { returnDocument: "after" }
)

if (updated === null) {
  print("Không có tài khoản thỏa điều kiện")
} else {
  print("Số dư mới: " + updated.balance)
}
~~~

Lệnh vừa kiểm tra điều kiện, vừa cập nhật một document và trả document theo tùy chọn. Cú pháp `returnDocument` ở đây thuộc `mongosh`; driver/framework khác có thể có kiểu option và kết quả trả về khác. Các side effect bên ngoài MongoDB (gửi email, gọi dịch vụ thanh toán, publish message) **không** trở thành nguyên tử cùng lệnh này.

### 5.4. Ràng buộc duy nhất cần unique index

Chuỗi `findOne({ email })` rồi `insertOne(...)` vẫn có race nếu hai client đồng thời thấy email chưa tồn tại. Cơ sở dữ liệu cần unique index:

~~~javascript
lab.users.createIndex({ email: 1 }, { unique: true })
~~~

Client thua cuộc có thể nhận duplicate key error. Đó là kết quả ràng buộc dữ liệu cần xử lý ở ứng dụng, **không phải** dấu hiệu nên retry mù. Tùy use case cần thêm chuẩn hóa email, collation, partial index hoặc compound key theo tenant.

## 6. Transaction: xử lý nhiều document cùng nhau

Nếu chuyển tiền giữa account A và B, hai lệnh `updateOne` độc lập không thể tự bảo đảm "trừ A và cộng B cùng commit hoặc cùng abort". Khi nghiệp vụ yêu cầu nguyên tử qua **nhiều document**, xem xét **multi-document transaction** trên deployment hỗ trợ.

~~~javascript
// Ví dụ mongosh chạy trên replica set có hỗ trợ transaction.
const session = db.getMongo().startSession()
const accounts = session.getDatabase("concurrency_lab").accounts

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  const debit = accounts.updateOne(
    { _id: "A", balance: { $gte: 20 } },
    { $inc: { balance: -20 } }
  )
  if (debit.matchedCount !== 1) {
    throw new Error("Thiếu A hoặc không đủ số dư")
  }

  const credit = accounts.updateOne(
    { _id: "B" },
    { $inc: { balance: 20 } }
  )
  if (credit.matchedCount !== 1) {
    throw new Error("Thiếu account B")
  }

  session.commitTransaction()
  print("Committed")
} catch (error) {
  // Chỉ minh họa abort; không phải hàm retry production hoàn chỉnh.
  try { session.abortTransaction() } catch (_) {}
  print("Transfer không commit được: " + error.message)
} finally {
  session.endSession()
}
~~~

Transaction giữ một góc nhìn snapshot phù hợp và làm việc theo quy tắc atomicity nhiều document. **Trước khi commit**, các thay đổi chưa được công bố ra ngoài transaction theo hợp đồng transaction; khi abort, chúng bị loại bỏ.

### 6.1. Ghi cạnh tranh trong transaction

- Transaction T bắt đầu từ snapshot cũ; operation ngoài transaction cập nhật X; khi T cố ghi X, T có thể **abort vì write conflict**.
- Transaction T đang sửa X; một ghi bên ngoài muốn sửa X có thể phải **đợi** T hoàn tất hoặc gặp conflict theo thời điểm và ngữ cảnh.
- Transaction kéo dài có thể giữ tài nguyên khiến DDL liên quan chờ; DDL đang chờ có thể cản transaction mới trên cùng tài nguyên.
- Transaction có thể gặp giới hạn về **thời gian đợi khóa, tuổi thọ, cache** và yêu cầu quyền truy cập, dù lệnh bên trong nhìn riêng lẻ là hợp lệ.

Theo tài liệu production của MongoDB, mặc định transaction chỉ đợi **khoảng 5 ms để lấy khóa cần thiết**; nếu không lấy được, transaction có thể abort. Tham số `maxTransactionLockRequestTimeoutMillis` cho phép thay đổi trong môi trường hỗ trợ. **Đây là giới hạn đợi khóa**, không phải thời gian chạy tối đa của transaction. Transaction lifetime mặc định có giới hạn riêng (thông thường dưới một phút, có thể được cấu hình).

Không nên tự tăng lock timeout chỉ để "giảm lỗi": nó có thể làm chờ lâu hơn hoặc ảnh hưởng đến xử lý deadlock. Cần tìm nguyên nhân contention và đánh giá phiên bản, topology, policy của môi trường trước.

### 6.2. Retry đúng phạm vi

| Lỗi / nhãn | Ý nghĩa | Chiến lược |
|---|---|---|
| **`TransientTransactionError`** | Lỗi tạm thời khiến transaction cần thử lại. | Abort lần thử lỗi và **retry toàn transaction**, có giới hạn. |
| **`UnknownTransactionCommitResult`** | Client chưa xác định commit đã thành công chưa. | **Retry commit** theo hợp đồng driver, không tự động thực thi lại nghiệp vụ. |
| **`TransactionTooLargeForCache`** | Transaction vượt giới hạn phù hợp của WiredTiger cache. | Thiết kế/chia nhỏ workload; retry y nguyên thường không giúp. |
| **Duplicate key / validation error** | Ràng buộc dữ liệu không thỏa. | Xử lý lỗi nghiệp vụ, không retry mù. |

MongoDB driver thường có **callback/convenient transaction API** hỗ trợ một số retry tự động; **core transaction API** có thể yêu cầu ứng dụng tự điều khiển retry. Không nhầm `retryWrites=true` của driver với việc tự động retry toàn transaction.

Trong ứng dụng thực, retry cần **giới hạn thời gian/số lần**, backoff phù hợp, **idempotency key** cho request có thể bị gửi lại và xử lý side effect bên ngoài transaction. Nếu callback transaction có thể chạy nhiều lần, đừng đặt lệnh gửi email hay trừ tiền qua API bên thứ ba trực tiếp trong callback đó mà không có thiết kế chống lặp.

### 6.3. Transaction dài và cache pressure

WiredTiger cần giữ các phiên bản dữ liệu cho snapshot đang hoạt động. Transaction dài hoặc cập nhật quá nhiều dữ liệu có thể tăng pressure lên cache/history, dẫn đến abort hoặc lỗi kiểu `TransactionTooLargeForCache`. Vì vậy:

- Giữ transaction **ngắn**, chỉ gồm thao tác cần atomicity nhiều document.
- Đặt index cho filter trong transaction; tránh quét dữ liệu quá rộng.
- Tránh gọi network API chậm hoặc đợi thao tác người dùng trong transaction.
- Bỏ transaction khi lỗi; không giữ session/transaction bỏ dở.
- Nếu bất biến có thể mô hình hóa trong **một document**, ưu tiên thao tác nguyên tử trên document đó.

## 7. Yield, DDL và admission queue

### 7.1. Yield: nhường tài nguyên khi thao tác chạy dài

Read/update/delete chạy lâu có thể **yield**, tức tạm nhường một số khóa/tài nguyên để các thao tác khác có cơ hội tiến triển và để tránh storage transaction giữ snapshot quá lâu. Một thao tác sửa nhiều document có thể yield giữa các document. Trường `numYields` giúp quan sát hành vi này khi được trả về.

Yield **không phải commit** và không làm `updateMany()` thành một transaction chung. `numYields` cao chỉ là một tín hiệu cần đối chiếu với query plan, thời gian thực thi, I/O và tải hệ thống.

### 7.2. DDL và các thao tác cần khóa mạnh

Các thao tác metadata như đổi tên collection, drop collection hoặc các giai đoạn xây dựng index có yêu cầu khóa khác CRUD. Ví dụ một transaction đang dùng collection C, sau đó DDL cần khóa X trên C có thể phải chờ. Trong lúc DDL xếp hàng, transaction mới muốn dùng C cũng có thể bị ảnh hưởng.

~~~text
Transaction T1 giữ khóa cho hoạt động trên C
          |
DDL cần khóa không tương thích trên C -> WAITING
          |
Transaction T2 mới truy cập C -> có thể WAIT / TIMEOUT
~~~

Cơ chế khóa chính xác thay đổi tùy lệnh và phiên bản. Không suy rằng một thao tác xây index luôn khóa độc quyền toàn bộ thời gian chạy, cũng không khẳng định tác vụ "background" là hoàn toàn không ảnh hưởng hệ thống.

### 7.3. Read/write tickets là giới hạn khác với lock

WiredTiger còn quản lý số storage transactions được phép chạy đồng thời qua **read/write tickets**. Khi không còn ticket, một operation có thể phải xếp hàng **trước khi vào storage engine**.

Từ MongoDB **7.0**, thuật toán mặc định có thể điều chỉnh động lượng ticket tối đa. Tên metric thay đổi theo phiên bản:

- Các nhánh mới mô tả **`queues.execution`** trong `serverStatus`.
- Một số nhánh/phiên bản hiển thị **`wiredTiger.concurrentTransactions`**.

Không kết luận quá tải chỉ vì số ticket `available` thấp. Hãy xem **số operation queued, thời gian chờ, throughput và latency**. Cũng không tự ý tăng tối đa tickets như cách chữa chung: nếu nguyên nhân ở I/O hoặc hot document, cấp nhiều concurrency hơn có thể làm tranh chấp nặng thêm.

## 8. Cách quan sát lock và write conflict

Các ví dụ dưới đây **chỉ đọc thống kê** và thường cần quyền giám sát phù hợp. Trong replica set, cần biết mình đang xem **node nào**, lúc đó là primary/secondary hay đang rolling upgrade; output có thể khác nhau theo phiên bản.

### 8.1. Các bộ đếm trong `serverStatus`

~~~javascript
// Chạy trên mongod cần quan sát.
const s = db.serverStatus()

print("Server version: " + db.version())

print("Write conflict counter:")
printjson(s.metrics?.operation?.writeConflicts)

print("Lock metrics:")
printjson(s.locks)

print("Global lock information:")
printjson(s.globalLock)

print("Storage admission (tùy phiên bản):")
printjson(s.queues?.execution ?? s.wiredTiger?.concurrentTransactions)
~~~

Ý nghĩa:

- **`metrics.operation.writeConflicts`** đếm những conflict mà server ghi nhận theo định nghĩa metric; **không phải** số request client đã thất bại.
- **`locks`** có thể cung cấp các bộ đếm như `acquireCount`, `acquireWaitCount`, `timeAcquiringMicros` theo tài nguyên và lock mode.
- **`globalLock`** là nhóm thông tin tổng quát về hoạt động/queue; không có nghĩa mọi ghi đều lấy global X lock.
- **`queues.execution`** hoặc **`wiredTiger.concurrentTransactions`** giúp xem admission; chi tiết đúng theo phiên bản server.

Nhiều metric là **cumulative counters kể từ khi mongod khởi động**. Để xem xu hướng, lấy chênh lệch giữa hai thời điểm trên cùng node:

~~~text
T0: writeConflicts = 1000
T1 (sau 60 giây): writeConflicts = 1240
Chênh lệch = 240 / 60 giây = 4 write conflicts/giây
~~~

Đây chỉ là ví dụ tính toán. Bốn conflicts/giây không đủ để kết luận hệ thống gặp sự cố: cần xem tốc độ request, latency, throughput và số transaction abort. Counter có thể về 0 khi process restart.

### 8.2. Xem operation đang đợi khóa

~~~javascript
db.currentOp({ waitingForLock: true })
~~~

Để xem một số thông tin của các operation đang hoạt động:

~~~javascript
const active = db.currentOp({ active: true })
printjson(active.inprog?.map(op => ({
  opid: op.opid,
  ns: op.ns,
  op: op.op,
  secs_running: op.secs_running,
  waitingForLock: op.waitingForLock,
  locks: op.locks,
  lockStats: op.lockStats,
  numYields: op.numYields,
  writeConflicts: op.writeConflicts
})))
~~~

`currentOp` là ảnh chụp ngắn của hoạt động, không phải bản ghi đầy đủ mọi conflict từng xảy ra. `waitingForLock: false` **không bác bỏ** việc operation đang chờ I/O, admission hoặc đã hết tranh chấp trước khi bạn quan sát. Với sharded cluster, thao tác có thể xuất hiện ở nhiều node với những trạng thái khác nhau.

### 8.3. Slow log và database profiler

Khi lệnh chậm, kết hợp slow operation log, database profiler (nếu được phép bật) và monitoring:

| Chỉ số | Gợi ý điều tra |
|---|---|
| `millis` / duration | Mức độ chậm của operation; phải so với bình thường. |
| `locks` / `lockStats` | Số lần lấy khóa, đợi khóa và tổng thời gian đợi. |
| `numYields` | Operation từng nhường tài nguyên bao nhiêu lần. |
| `writeConflicts` | Số lần có xung đột ghi theo metric của operation. |
| `docsExamined` / `keysExamined` | Có đang quét quá nhiều dữ liệu hay không. |
| storage queue / ticket metrics | Có đang chờ suất vào storage engine không. |
| transaction aborts | Transaction nào/thời điểm nào đang thất bại. |

Database profiler có **overhead** và có thể ghi chi tiết command chứa dữ liệu nhạy cảm; chỉ sử dụng ở mức được phép. Bắt đầu từ metrics, slow log và query plan rồi mới cân nhắc profiler nếu cần.

## 9. Ba thí nghiệm về concurrency

Dùng database riêng `concurrency_lab` để thực hành. Thí nghiệm cạnh tranh cần **hai cửa sổ mongosh** kết nối cùng deployment. Nếu các câu lệnh quá nhanh khiến bạn không thấy write conflict hiện rõ, đó là kết quả bình thường: server có thể đã retry nội bộ hoặc hai thao tác không thật sự đụng nhau tại cùng thời điểm.

### 9.1. Chuẩn bị

~~~javascript
const lab = db.getSiblingDB("concurrency_lab")

lab.accounts.replaceOne(
  { _id: "A" },
  { _id: "A", balance: 100, version: 1 },
  { upsert: true }
)

lab.accounts.replaceOne(
  { _id: "B" },
  { _id: "B", balance: 100, version: 1 },
  { upsert: true }
)
~~~

### 9.2. Hai phép cộng trên cùng document

Ở hai terminal, cùng gọi:

~~~javascript
db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: 1 } }
)
~~~

Nếu hai lần đều thành công và số dư ban đầu là 100, cuối cùng là 102. Mỗi phép tăng được thực hiện nguyên tử trên document. Sau đó thử nhiều lần với tải nhỏ, quan sát `writeConflicts` trước/sau nếu có quyền; không cần tạo tải lớn trên môi trường dùng chung.

### 9.3. Lost update không sinh lỗi client

Đặt lại A về `balance: 100` rồi **ở cả hai terminal đọc trước khi bên nào ghi**:

~~~javascript
const old = db.getSiblingDB("concurrency_lab").accounts.findOne({ _id: "A" })
printjson(old)
~~~

Terminal 1:

~~~javascript
db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A" },
  { $set: { balance: old.balance - 30 } }
)
~~~

Terminal 2 vẫn giữ biến `old.balance = 100` đã đọc trước đó:

~~~javascript
db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A" },
  { $set: { balance: old.balance - 20 } }
)
~~~

Kết quả cuối có thể là 80 (nếu terminal 2 ghi sau) thay vì 50. Hai lệnh đều có thể báo thành công. Đó là **lost update** do logic ứng dụng.

Thử lại với filter `{ _id: "A", version: old.version }` và `$inc: { version: 1 }`: lần ghi sau với version cũ không còn khớp, `matchedCount` trả 0.

### 9.4. Hai lần rút tiền có điều kiện

Đặt lại `balance = 100`. Ở hai terminal, mỗi bên cố rút 80:

~~~javascript
db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A", balance: { $gte: 80 } },
  { $inc: { balance: -80 } }
)
~~~

Chỉ một update có thể khớp và đưa số dư về 20; lần còn lại sẽ không khớp vì `20 < 80`. Đây là lợi ích của việc **kiểm tra bất biến ngay trong atomic update**.

### 9.5. Thí nghiệm transaction conflict

Trên replica set, có thể bắt đầu hai transaction cùng đọc/ghi một document và điều khiển thứ tự ghi để quan sát transaction abort. Kết quả chính xác phụ thuộc scheduling, version và điều kiện hệ thống; **không gắn assert cứng vào thời gian chờ hay mã lỗi cụ thể**. Mục đích là quan sát sự khác nhau giữa:

~~~text
Atomic $inc          -> không làm mất một phép tăng đã thành công
Stale read + $set    -> có thể lost update dù không thấy lỗi
CAS version          -> phát hiện dữ liệu đã thay đổi bằng matchedCount=0
Transaction conflict -> có thể abort, cần retry cả transaction
~~~

## 10. Quy trình chẩn đoán thực tế

Khi nghi ngờ hệ thống chậm do lock hoặc write conflict:

1. **Khoanh phạm vi:** request, collection, node, khoảng thời gian, server version, workload mới thay đổi.
2. **Phân loại triệu chứng:** lock wait, write conflict, admission queue, I/O, CPU, network, query plan hay logic ứng dụng.
3. **Đo theo thời gian:** latency p50/p95/p99, throughput, `metrics.operation.writeConflicts`, lock wait metrics, queue, transaction aborts.
4. **Tìm thao tác và truy cập nóng:** nhiều client có ghi cùng một `_id` không? Có DDL trùng giờ cao điểm? Transaction có dài không? Có thiếu index làm quét nhiều dữ liệu không?
5. **Đổi cơ chế cập nhật nếu cần:** atomic update, CAS, unique index, transaction đúng phạm vi; giảm batch hoặc giới hạn concurrency có cơ sở.
6. **Đo lại dưới workload tương đương:** so sánh cả latency, throughput và error rate, không kết luận chỉ từ một counter.

| Triệu chứng | Giả thuyết | Điều cần kiểm tra |
|---|---|---|
| Write-conflict counter tăng cùng latency update | Hot document hoặc nhiều ghi cùng vùng dữ liệu | Phân bố `_id`, thao tác ghi, transaction retries. |
| `waitingForLock` tăng khi triển khai migration | DDL và thao tác lâu đang tranh khóa | Lock mode, namespace, transaction đang chạy. |
| Transaction abort tăng, cache pressure cao | Transaction quá lớn/dài hoặc nhiều xung đột | Lifetime, số document, index, kích thước cache, error label. |
| Read/write ticket queue tăng | Bão hòa storage admission | CPU, disk, throughput, queue depth; không tăng ticket tùy tiện. |
| Chậm nhưng lock wait thấp, `docsExamined` cao | Query scan/thiếu index | `explain()` và access pattern. |
| Ghi thành công nhưng giá trị cuối sai | Lost update hoặc race nghiệp vụ | Chuỗi read–calculate–write, điều kiện update, CAS. |
| Duplicate key error tăng | Nhiều client cùng insert key duy nhất | Unique index, idempotency và xử lý nghiệp vụ trùng. |

Tối ưu thường có lợi hơn việc điều chỉnh cấu hình khóa: giữ transaction ngắn, đặt index phù hợp filter, giảm ghi vào một document quá nóng, đặt điều kiện nghiệp vụ trong update, và retry có giới hạn với idempotency. Chỉ chỉnh server parameter khi đã có bằng chứng và hiểu tác động của phiên bản đang chạy.

## 11. Câu hỏi thường gặp

**MongoDB có khóa document không?**  
Với WiredTiger, MongoDB hỗ trợ **document-level write concurrency**. Server vẫn dùng intent locks trên global/database/collection. Không nên hình dung mọi document có một đối tượng khóa công khai có thể xem trong `currentOp.locks`.

**Hai reader có ngăn nhau không?**  
Trong phần lớn hoạt động đọc thông thường, các thao tác đọc có thể cùng tiến triển. Dữ liệu phiên bản nào được thấy phụ thuộc read concern và ngữ cảnh snapshot.

**`$inc` có bảo đảm không mất phép cộng không?**  
Những phép `$inc` thành công trên cùng document được thực hiện nguyên tử; khác với hai client đọc cùng giá trị rồi `$set` kết quả cũ. Nhưng ứng dụng vẫn phải xử lý retry/idempotency nếu request có thể được gửi lại.

**Có write conflict nghĩa là đã hỏng dữ liệu?**  
Không. Nó là tín hiệu phát hiện tranh chấp và có thể dẫn đến retry/abort để bảo đảm tính đúng đắn. Ngược lại, dữ liệu nghiệp vụ vẫn có thể sai do lost update mà không thấy lỗi conflict.

**`w: "majority"` có tránh lost update không?**  
Không. Write concern quy định mức xác nhận ghi; lost update là vấn đề về điều kiện cập nhật và dữ liệu cũ phía ứng dụng.

**`updateMany()` có atomicity toàn bộ tập không?**  
Không. Mỗi document được sửa là nguyên tử riêng; các document trong một lệnh nhiều document có thể được quan sát từng phần bởi thao tác khác.

**Tại sao write-conflict counter tăng mà client không thấy lỗi?**  
Vì MongoDB có thể retry một số xung đột nội bộ. Counter không tương đương số request thất bại.

**Khi nào dùng transaction?**  
Khi nhiều document phải cùng commit/abort và không thể biểu diễn bất biến một cách an toàn trong một atomic update. Transaction có chi phí, giới hạn và quy tắc retry riêng.

**Có thể dùng `SELECT ... FOR UPDATE` như SQL không?**  
MongoDB không có cú pháp truy vấn thông thường tương đương trực tiếp. Thường dùng conditional update, `findOneAndUpdate` hoặc transaction với ngữ nghĩa phù hợp.

## 12. Bài tập tự kiểm tra

1. **IX với IX:** Hai ghi vào hai document khác nhau cùng có IX trên collection. Hai khóa đó tương thích không? **Có**; xung đột ở mức document vẫn có thể xảy ra nếu chúng cùng đụng một document.
2. **Lost update:** Hai client cùng đọc `count=10` và đều `$set` thành 11. Kết quả sau cả hai lệnh thành công? **11**; một lần tăng bị mất. Dùng `$inc` cho phép tăng nguyên tử.
3. **CAS:** Update yêu cầu `version=3` nhưng document đã ở `version=4`, trả `matchedCount=0`. Đây chắc chắn là WiredTiger WriteConflict? **Không**; đó là filter không khớp.
4. **Retry transaction:** `TransientTransactionError` và `UnknownTransactionCommitResult` có cùng chiến lược không? **Không**: thường retry **toàn transaction** đối với lỗi tạm thời, retry **commit** với kết quả commit chưa rõ.
5. **Counter:** `writeConflicts` tăng từ 1000 lên 1120 sau 30 giây. Đã biết gì? **Có 120 đơn vị tăng** theo metric; chưa biết request nào thất bại hay latency có cao không.
6. **Atomicity:** Một `updateMany` sửa 200 document, các client có thể thấy một số document đã sửa trước khi tất cả hoàn tất không? **Có thể**; không có atomicity chung ngoài transaction.
7. **Phạm vi khóa:** Một operation cần X collection có thể bỏ qua mức khóa cha không? **Không**; cơ chế khóa nhiều cấp sử dụng intent lock tương ứng tại database/global.

## 13. Tài liệu chính thức

Các trang sau thuộc **MongoDB Database Manual**. Chọn đúng nhánh tài liệu server khi áp dụng vào một phiên bản cụ thể; `/docs/manual/` có thể trỏ đến dòng phát hành hiện hành và khác môi trường của bạn.

- [FAQ: Concurrency](https://www.mongodb.com/docs/manual/faq/concurrency/) — multi-granularity locking, IS/IX/S/X, lock yield và quan sát khóa.
- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — concurrency mức document, optimistic control, MVCC, checkpoint, read/write tickets.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — atomicity, concurrent updates, lost update và filter có điều kiện.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — commit và abort nhiều document.
- [Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — write conflicts, lock acquisition, DDL, snapshot, cache và lifetime.
- [Handle Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — lỗi có nhãn và quy tắc retry transaction.
- [`serverStatus` command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — lock metrics, write conflicts, queue.
- [Database Profiler Output](https://www.mongodb.com/docs/manual/reference/database-profiler/) — số lần đợi khóa, thời gian chờ, write conflicts.
- [`db.currentOp()`](https://www.mongodb.com/docs/manual/reference/method/db.currentOp/) — operation đang hoạt động và lock status.
- [WiredTiger — Manual 7.0](https://www.mongodb.com/docs/v7.0/core/wiredtiger/) và [WiredTiger — Manual 8.0](https://www.mongodb.com/docs/v8.0/core/wiredtiger/) — ví dụ tài liệu cố định theo phiên bản.

Khi chẩn đoán hệ thống thực, luôn ghi lại **server version, topology, storage engine, thời điểm lấy số liệu, driver version và loại operation**. Cùng một triệu chứng "ghi chậm" có thể là lock wait, write conflict, admission, I/O hoặc một race của ứng dụng; chỉ khi xác định đúng tầng gây vấn đề mới chọn được hướng giải quyết phù hợp.
