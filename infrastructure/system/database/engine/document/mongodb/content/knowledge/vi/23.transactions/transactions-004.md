# Read concern, write concern và read preference trong giao dịch MongoDB

Giả sử một ứng dụng chuyển 50 đơn vị tiền từ tài khoản A sang tài khoản B. Nếu thao tác trừ tiền thành công nhưng thao tác cộng tiền thất bại, hệ thống sẽ tạo ra trạng thái sai. MongoDB hỗ trợ **multi-document transaction** để nhóm nhiều thao tác đọc/ghi thành một đơn vị nguyên tử: hoặc các thay đổi cùng được commit, hoặc các thay đổi của giao dịch bị abort.

Tuy nhiên, chỉ gọi `startTransaction()` chưa trả lời hết các câu hỏi quan trọng:

- Khi giao dịch đọc số dư, nó được phép nhìn thấy **phiên bản dữ liệu nào**?
- Sau khi `commitTransaction()` trả thành công, cần **bao nhiêu replica set member xác nhận** để giảm nguy cơ rollback khi failover?
- Các phép đọc trong giao dịch được gửi tới **primary hay secondary**?

Ba nhóm tùy chọn giải quyết những vấn đề này:

| Tùy chọn | Câu hỏi cần giải quyết | Ví dụ |
| --- | --- | --- |
| **Read concern** | Độ nhất quán và nguồn gốc snapshot của dữ liệu giao dịch đọc là gì? | `"local"`, `"majority"`, `"snapshot"` |
| **Write concern** | Khi commit, MongoDB cần xác nhận ghi đến mức nào? | `w: 1`, `w: "majority"`, `j`, `wtimeout` |
| **Read preference** | Thao tác đọc được định tuyến đến replica set member nào? | `"primary"` trong giao dịch có đọc |

Bài học thuộc chương **Giao dịch** của module **Database Engine Document MongoDB**. Nội dung tập trung vào cách phối hợp ba thiết lập ở **cấp transaction**, không nhầm chúng với tùy chọn của từng câu lệnh hoặc quyền bầu cử primary của replica set.

## 1. Điều kiện tiên quyết: transaction và session

MongoDB hỗ trợ transaction nhiều document trên **replica set** và **sharded cluster** phù hợp. Một standalone `mongod` không phải môi trường đầy đủ để thực hành multi-document transaction. Với ứng dụng thực tế, cần dùng phiên bản server, driver và topology hỗ trợ tính năng transaction.

Một transaction gắn với một **client session**:

```text
Ứng dụng
   |
   v
ClientSession
   |
   +-- startTransaction(options)
   |      |
   |      +-- read #1 (kèm session)
   |      +-- update #1 (kèm session)
   |      +-- update #2 (kèm session)
   |      +-- insert #3 (kèm session)
   |
   +-- commitTransaction() hoặc abortTransaction()
   |
   v
Kết thúc session
```

Ba nguyên tắc nền tảng:

1. **Mọi thao tác muốn thuộc transaction phải sử dụng cùng session.** Một `insertOne()` quên truyền session có thể chạy **ngoài giao dịch**, không được bảo vệ bởi `abortTransaction()`.
2. **Một session chỉ có tối đa một transaction đang mở tại một thời điểm.** Không chạy song song các thao tác transaction trên cùng session như thể chúng là nhiều giao dịch độc lập.
3. **Commit và acknowledgment là hai bước khái niệm khác nhau.** Transaction có thể đạt trạng thái commit trên primary trước khi client nhận đủ write concern; lỗi chờ xác nhận không mặc nhiên chứng minh giao dịch đã bị hủy.

MongoDB bảo đảm thao tác trên **một document** có tính nguyên tử ở mức document. Chỉ dùng transaction nhiều document khi nghiệp vụ cần cập nhật đồng bộ các document/collection, không mở transaction cho mọi lệnh CRUD theo phản xạ.

## 2. Đặt cả ba tùy chọn ở cấp transaction

Một cấu hình thường dùng để minh họa:

```javascript
{
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  },
  readPreference: { mode: "primary" }
}
```

Ý nghĩa:

- `readConcern.level: "snapshot"` yêu cầu chế độ snapshot cho các phép đọc của transaction.
- `writeConcern.w: "majority"` yêu cầu **commit** được xác nhận ở mức majority.
- `writeConcern.j: true` thêm yêu cầu journal theo khả năng của server/storage engine.
- `writeConcern.wtimeout: 10000` giới hạn chờ write concern trong 10.000 ms.
- `readPreference.mode: "primary"` dùng primary để xử lý các phép đọc của giao dịch.

Tuy cùng nằm trong một object cấu hình, ba thiết lập này **không được áp dụng vào cùng một thời điểm**:

```text
startTransaction
      |
      v
  Chọn read preference / server
      |
      v
  Thực hiện các thao tác dùng transaction-level read concern
      |
      v
 commitTransaction
      |
      v
  Chờ write concern của transaction
      |
      v
  Xác nhận commit (hoặc lỗi cần phân loại)
```

Lưu ý rằng server có thể thực sự bắt đầu transaction một cách **lazy** ở thao tác đầu tiên sau `startTransaction()`; gọi hàm start phía client không nhất thiết ngay lập tức gửi một command mở transaction tới server.

## 3. Read concern trong transaction: `local`, `majority`, `snapshot`

**Read concern** mô tả các bảo đảm đối với dữ liệu được đọc. Trong transaction, các mức được hỗ trợ là:

1. `"local"`
2. `"majority"`
3. `"snapshot"`

`"available"` và `"linearizable"` không phải lựa chọn read concern hợp lệ cho transaction. Không được coi chúng là hai mức “cao hơn” rồi áp dụng vào `startTransaction()`.

### 3.1. `readConcern: "local"`

```javascript
session.startTransaction({
  readConcern: { level: "local" },
  writeConcern: { w: "majority" }
})
```

`"local"` đọc dữ liệu hiện có trên node theo ngữ nghĩa read concern local; bản thân mức này **không bảo đảm dữ liệu được đọc đã majority committed** và dữ liệu chưa được majority commit có thể bị rollback khi failover.

Với transaction trên một replica set, việc đọc có thể biểu hiện tính cô lập mạnh hơn, chẳng hạn quan sát một snapshot tại thời điểm transaction bắt đầu theo cách server thực thi. Tuy nhiên, **không nên đồng nhất `"local"` với `"snapshot"` trong mọi topology**.

Đặc biệt, ở **sharded cluster**, read concern `"local"` không bảo đảm các shard cung cấp dữ liệu từ cùng một snapshot thời điểm. Nếu báo cáo/giao dịch cần snapshot nhất quán giữa nhiều shard, hãy xem xét `"snapshot"`.

### 3.2. `readConcern: "majority"`

```javascript
session.startTransaction({
  readConcern: { level: "majority" },
  writeConcern: { w: "majority" }
})
```

Read concern `"majority"` liên quan đến dữ liệu đã được đa số thành viên replica set xác nhận. **Trong transaction, bảo đảm đọc từ dữ liệu majority-committed gắn với điều kiện transaction được commit bằng write concern `"majority"`.**

Nếu transaction được commit với `w: 1`, chỉ đặt `readConcern: "majority"` **không đủ** để khẳng định các phép đọc đã dùng dữ liệu majority-committed theo bảo đảm transaction.

Ở **sharded cluster**, ngay cả khi commit `w: "majority"`, read concern `"majority"` **không bảo đảm các shard được đọc từ cùng một snapshot thời gian**. Đây là sự khác biệt quan trọng khi đối chiếu dữ liệu ở hai shard trong cùng transaction.

### 3.3. `readConcern: "snapshot"`

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})
```

`"snapshot"` là lựa chọn rõ ràng khi nghiệp vụ cần các phép đọc trong transaction nhìn dữ liệu dưới một **snapshot nhất quán**. Với transaction được commit bằng `w: "majority"`, các phép đọc được bảo đảm dựa trên snapshot của dữ liệu **majority-committed**.

Ở sharded cluster, snapshot của transaction được **đồng bộ giữa các shard**, khác với read concern `"local"` hoặc `"majority"` vốn không bảo đảm sự đồng bộ này qua các shard.

**Điều kiện không được bỏ qua:** nếu transaction commit với `w: 1` thay vì `w: "majority"`, read concern `"snapshot"` không còn bảo đảm rằng snapshot đã đọc chứa dữ liệu majority-committed theo ngữ nghĩa transaction.

### Snapshot không nhất thiết là dữ liệu mới nhất ở mọi thời điểm

Ví dụ:

```text
t0: Giao dịch T1 bắt đầu, đọc số dư A = 500
t1: Giao dịch T2 thay đổi A = 450 và commit
t2: T1 đọc A thêm lần nữa
```

T1 dùng snapshot có thể tiếp tục nhìn một trạng thái cũ phù hợp với snapshot của nó, thay vì tự động thấy thay đổi mới của T2. Điều này giúp các phép đọc có cơ sở nhất quán nhưng không bảo đảm rằng mọi lần đọc trong transaction luôn nhìn thấy **mọi cập nhật vừa xảy ra bên ngoài**.

Nếu T1 cố sửa document đã bị một transaction khác sửa theo cách xung đột, MongoDB có thể báo **write conflict** và transaction cần retry theo quy tắc của driver. `"snapshot"` không miễn trừ mọi tranh chấp dữ liệu và không nên coi là mức cô lập serializable tuyệt đối cho mọi mẫu nghiệp vụ.

### 3.4. So sánh ba mức read concern

| Mức trong transaction | Đặc điểm chính | Ở sharded cluster | Lưu ý về commit |
| --- | --- | --- | --- |
| `"local"` | Dữ liệu hiện có trên node; không tự cam kết đã majority committed | Không bảo đảm một snapshot đồng bộ giữa các shard | Không nên suy ra bảo đảm majority từ việc chỉ chọn `local` |
| `"majority"` | Bảo đảm đọc dữ liệu majority-committed theo điều kiện transaction | Có thể không cùng snapshot thời gian giữa các shard | Bảo đảm gắn với **commit `w:"majority"`** |
| `"snapshot"` | Yêu cầu snapshot nhất quán; phù hợp đọc qua nhiều document/shard | Snapshot đồng bộ giữa các shard | Muốn bảo đảm snapshot của majority-committed data, **commit `w:"majority"`** |

Khi lựa chọn, hãy xác định yêu cầu thực tế: chỉ cần các thao tác cùng được commit nguyên tử, cần đọc dữ liệu majority-committed, hay cần các phép đọc qua nhiều shard có **cùng góc nhìn thời điểm**?

## 4. Read concern của transaction không phải read concern của từng phép đọc

Trong transaction, **read concern được xác định ở cấp transaction**. Không truyền một read concern khác vào `find()`, `aggregate()` hoặc thao tác đọc riêng lẻ bên trong transaction.

Ví dụ về cách cấu hình đúng:

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

// Các lệnh đọc qua database handle của session dùng
// read concern của transaction.
const account = sessionDb.accounts.findOne({ _id: "A" })
```

Một phương thức hoặc collection handle có read concern riêng **không được phép lấn át transaction-level read concern**. Trong driver, read concern của transaction có thể kế thừa từ session/client nếu không đặt tường minh, nhưng read concern riêng của một thao tác trong transaction không được dùng như cách đổi mức đọc giữa chừng.

### Thứ tự kế thừa cần hiểu đúng

Với MongoDB drivers, khi không đặt read concern ở cấp transaction, thông thường nó có thể kế thừa theo:

```text
transaction-level read concern (nếu có)
          |
          v
session default transaction options (nếu có)
          |
          v
client-level read concern / default theo cấu hình
```

Read concern ở collection hoặc database **không phải cơ chế thay thế được transaction-level read concern**. Tài liệu MongoDB quy định các thao tác trong transaction sử dụng read concern ở cấp transaction; đừng tưởng rằng thay collection handle từ `majority` sang `local` sẽ làm mỗi thao tác trong một transaction có mức đọc riêng.

## 5. Write concern trong transaction áp dụng khi nào?

Khác với read concern, **transaction-level write concern được áp dụng tại thời điểm commit**, không phải một write concern độc lập trên mỗi `insertOne()` hay `updateOne()` bên trong transaction.

```text
startTransaction(writeConcern = majority)
        |
        +-- update accounts[A]
        +-- update accounts[B]
        +-- insert transfers
        |
        v
commitTransaction()
        |
        v
MongoDB xác nhận commit theo transaction-level write concern
```

**Không truyền `writeConcern` riêng cho từng câu lệnh ghi trong transaction.** Các driver/server có thể trả lỗi khi bạn cố gán một write concern per-operation trong transaction.

### 5.1. Commit với `w: 1`

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: 1 }
})
```

`w: 1` yêu cầu acknowledgment khi commit được áp dụng trên **primary**. Nếu primary lỗi trước khi commit được majority replicated, thay đổi của transaction **có thể bị rollback khi failover**.

Sự khác biệt đáng chú ý:

- Transaction vẫn có tính nguyên tử: không phải chủ đích cho phép “trừ tài khoản A rồi bỏ quên B”.
- Nhưng một commit mới chỉ được primary xác nhận có thể **không tồn tại lâu dài sau failover** nếu chưa majority committed.
- Nếu dùng `readConcern: "majority"` hoặc `"snapshot"` cùng commit `w: 1`, không được tuyên bố bảo đảm đọc dữ liệu majority-committed như khi commit bằng majority.

### 5.2. Commit với `w: "majority"`

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    wtimeout: 10000
  }
})
```

`w: "majority"` yêu cầu commit được xác nhận ở mức majority của replica set. Trong transaction trên replica set bình thường, đây là lựa chọn quan trọng khi muốn giảm rủi ro các ghi đã được ứng dụng báo thành công bị rollback khi primary đổi.

Với sharded transaction, quá trình commit có thể có nhiều bước và điều phối qua các shard; MongoDB có các bước nội bộ sử dụng majority/journaling trong commit phân tán. Không nên rút gọn toàn bộ quá trình này thành “chỉ gửi một lệnh lên một primary”.

### 5.3. `j` và `wtimeout` trong commit

```javascript
{
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 8000
  }
}
```

- `j: true`: yêu cầu acknowledgment đáp ứng điều kiện **journal** theo storage engine/cấu hình phù hợp. Nó không thay thế majority replication.
- `wtimeout: 8000`: giới hạn thời gian **chờ write concern** (mili giây). Nó không biến tất cả thời hạn mạng/driver và thời gian thực thi transaction thành đúng tám giây.
- Nếu không đạt write concern kịp thời, có thể xuất hiện **write concern error**. Điều đó không tự chứng minh rằng transaction chưa từng được commit hoặc chắc chắn đã rollback.

Với nhiều phiên bản MongoDB, cấu hình như `writeConcernMajorityJournalDefault` ảnh hưởng hành vi journaling khi dùng `w: "majority"`; nên xác nhận phiên bản và cài đặt đích, không mặc định một quy tắc journal duy nhất cho mọi deployment.

### 5.4. `w: 0` không phù hợp với transaction

Multi-document transaction yêu cầu cơ chế commit có acknowledgment; MongoDB Java Driver từ chối **unacknowledged write concern** cho transaction. Không dùng `WriteConcern.UNACKNOWLEDGED` hoặc `{w:0}` để cố tăng throughput của một transaction.

Nếu nghiệp vụ chỉ cần log best-effort và chấp nhận không có xác nhận, hãy xem xét một luồng ghi độc lập phù hợp, thay vì kết hợp `w:0` vào transaction nhiều document.

### 5.5. Không sửa mức write concern giữa transaction

Một transaction có các options của riêng nó từ khi bắt đầu. Không có khái niệm “ghi tài khoản A bằng `w:1`, rồi ghi tài khoản B bằng `w:majority` trong cùng transaction” theo dạng đặt per-operation write concern. Mức commit xác định **toàn bộ giao dịch** cần được xác nhận ra sao.

## 6. Commit timeout và trạng thái chưa rõ

Đây là một trường hợp phải được xử lý cẩn thận trong mọi giao dịch quan trọng:

```text
Client                          MongoDB
  |                               |
  | commitTransaction             |
  |------------------------------>|
  |                               | Áp dụng quyết định commit
  |                               | Chờ majority acknowledgment
  |      lỗi mạng hoặc timeout    |
  |<------------------------------x
  |
  v
Client KHÔNG THỂ kết luận từ timeout:
    "Chắc chắn đã abort"
    hoặc "Chắc chắn chưa chuyển tiền".
```

Cần phân biệt **hai nhóm lỗi**:

1. **`TransientTransactionError`**: một số lỗi có thể cho phép **chạy lại toàn bộ transaction** theo hướng dẫn của driver, vì transaction hiện tại không thể tiếp tục như dự định.
2. **`UnknownTransactionCommitResult`**: kết quả commit chưa rõ đối với client; cách xử lý thường là **retry bước commit của cùng transaction**, không tự động khởi tạo một lần chuyển tiền mới.

MongoDB drivers có callback API như `withTransaction()` để quản lý nhiều trường hợp retry phổ biến. Tuy nhiên callback có thể được **gọi lại**; không nên phát email, trừ tiền tại một hệ thống ngoài MongoDB hoặc gọi API thanh toán không idempotent ngay trong callback mà không có cơ chế chống lặp.

**Write concern timeout không phải lệnh rollback.** Nếu transaction đã commit nhưng client không nhận được ACK, chạy lại **một transaction mới** với cùng mục đích mà không có idempotency key có thể chuyển tiền hai lần. Thiết kế `transferId` duy nhất và kiểm tra trạng thái giao dịch là yêu cầu nghiệp vụ độc lập với read/write concern.

## 7. Read preference trong giao dịch: tại sao `primary` quan trọng?

**Read preference** bình thường cho phép MongoDB driver định tuyến truy vấn đọc đến primary hoặc các secondary, chẳng hạn:

```text
primary
primaryPreferred
secondary
secondaryPreferred
nearest
```

Nhưng **transaction có thao tác đọc phải sử dụng read preference `primary`**. Các thao tác trong một transaction cần được định tuyến nhất quán tới cùng member phù hợp theo quy tắc giao dịch. Không thể dùng `readPreference: "secondary"` để vừa giảm tải primary vừa giữ nguyên transaction đọc/ghi như thông thường.

### 7.1. Ví dụ đúng

```javascript
const session = db.getMongo().startSession({
  readPreference: { mode: "primary" }
});
```

Khi transaction bắt đầu và dùng session đó, các phép đọc không bị chuyển tới một secondary ngẫu nhiên. Trong Java Driver, cấu hình rõ ở `TransactionOptions`:

```java
.readPreference(ReadPreference.primary())
```

### 7.2. Ví dụ sai

```javascript
// Chỉ minh họa cấu hình không phù hợp
const session = db.getMongo().startSession({
  readPreference: { mode: "secondary" }
});

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

// Một thao tác đọc trong transaction với read preference secondary
// có thể bị driver/server từ chối.
```

Read concern `"snapshot"` **không cho phép bỏ qua giới hạn read preference của transaction**. Hai tùy chọn kiểm soát hai khía cạnh khác nhau: snapshot là **dữ liệu nào**, còn primary là **đọc ở member nào**.

### 7.3. Hành vi kế thừa read preference

Khi transaction không có read preference riêng:

```text
transaction-level read preference
           |
           v
session-level read preference
           |
           v
client-level read preference
           |
           v
default = primary (nếu không cấu hình khác)
```

Giả sử một dịch vụ tạo `MongoClient` với `readPreference=secondaryPreferred` để chạy báo cáo ngoài transaction. Nếu session transaction kế thừa read preference này mà không ghi đè, các phép đọc trong transaction có thể bị từ chối. **Khắc phục tại transaction:** đặt `ReadPreference.primary()` tường minh, không phụ thuộc ý đồ của client read-only.

### Read-only transaction có được tự ý đọc secondary?

Không nên suy rằng “chỉ đọc, không ghi” thì luôn được chọn `secondary` trong transaction. Theo quy tắc read preference của transaction nêu trên, **transaction chứa read operation phải dùng `primary`**. Nếu mục tiêu chỉ là giảm tải primary bằng các truy vấn đọc secondary, hãy cân nhắc thao tác đọc **ngoài multi-document transaction** với read preference/read concern phù hợp, thay vì biến mọi báo cáo thành transaction.

## 8. Bảng phối hợp ba thiết lập

Giả sử các giao dịch bên dưới có read operations và read preference `primary`.

| Read concern | Write concern tại commit | Read preference | Bảo đảm/giới hạn nổi bật |
| --- | --- | --- | --- |
| `local` | `w:1` | primary | Ít yêu cầu xác nhận; dữ liệu đọc không tự bảo đảm majority, commit có nguy cơ rollback khi failover |
| `local` | `w:"majority"` | primary | Commit được majority acknowledged; read concern local vẫn không phải yêu cầu snapshot majority nhất quán giữa shards |
| `majority` | `w:1` | primary | **Không** có bảo đảm transaction-level rằng reads là majority-committed |
| `majority` | `w:"majority"` | primary | Reads từ dữ liệu majority-committed theo ngữ nghĩa transaction; **không** đồng bộ một snapshot qua các shards |
| `snapshot` | `w:1` | primary | Dùng cơ chế snapshot nhưng **không có bảo đảm** reads từ snapshot majority-committed |
| `snapshot` | `w:"majority"` | primary | Snapshot majority-committed; với sharded cluster, snapshot được đồng bộ qua shards |
| `snapshot` | `w:"majority"` | secondary | **Không phù hợp** với transaction có thao tác đọc |

Bảng không nói rằng mọi kết hợp hợp lệ đều có cùng latency. `snapshot`, journal, majority replication, vị trí shard và mức cạnh tranh ghi đều có thể ảnh hưởng chi phí. Quan trọng hơn, chọn cấu hình chỉ sau khi đã định nghĩa yêu cầu **độ bền**, **mức nhất quán đọc**, **khả năng chịu lỗi** và **hiệu năng** của ứng dụng.

## 9. Thực hành: giao dịch chuyển tiền giữa hai document

Ví dụ sử dụng database thực hành `mongo_transaction_concern_lab` trên replica set hoặc sharded cluster phù hợp. Không chạy trên database chứa tiền thật. Các lệnh chuẩn bị cần thực hiện **ngoài transaction**.

```javascript
use mongo_transaction_concern_lab

db.accounts.insertMany([
  {
    _id: "A",
    owner: "An",
    balance: NumberDecimal("500.00"),
    currency: "VND"
  },
  {
    _id: "B",
    owner: "Bình",
    balance: NumberDecimal("100.00"),
    currency: "VND"
  }
])

db.createCollection("transfers")
```

Số dư ban đầu:

| Tài khoản | Balance |
| --- | ---: |
| A | 500.00 |
| B | 100.00 |
| **Tổng** | **600.00** |

Mục tiêu: chuyển `50.00` từ A sang B, đồng thời tạo một document lịch sử giao dịch mang `_id: "transfer-001"`. Sau commit thành công, A còn `450.00`, B có `150.00`, tổng vẫn `600.00`.

### 9.1. Mở session và cấu hình transaction

```javascript
const session = db.getMongo().startSession({
  readPreference: { mode: "primary" }
});

const txDb = session.getDatabase(
  "mongo_transaction_concern_lab"
);

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  }
});
```

Đây là session handle được lấy từ MongoDB connection. **Mọi lệnh bên dưới phải dùng `txDb`**, không chuyển sang `db.accounts` thông thường để rồi vô tình ghi ngoài transaction.

### 9.2. Thực hiện các thay đổi bên trong transaction

```javascript
// 1. Chỉ trừ tiền nếu A còn đủ số dư
const debit = txDb.accounts.updateOne(
  {
    _id: "A",
    balance: { $gte: NumberDecimal("50.00") }
  },
  { $inc: { balance: NumberDecimal("-50.00") } }
);

if (debit.matchedCount !== 1) {
  throw new Error("Tài khoản A không đủ số dư");
}

// 2. Cộng tiền vào B
const credit = txDb.accounts.updateOne(
  { _id: "B" },
  { $inc: { balance: NumberDecimal("50.00") } }
);

if (credit.matchedCount !== 1) {
  throw new Error("Không tồn tại tài khoản B");
}

// 3. Ghi lịch sử cùng transaction
txDb.transfers.insertOne({
  _id: "transfer-001",
  from: "A",
  to: "B",
  amount: NumberDecimal("50.00"),
  status: "committed",
  createdAt: new Date()
});
```

Các lệnh trên chỉ minh họa **đường đi thành công**. Nếu bất kỳ thao tác nào báo lỗi **trước khi commit**, transaction phải được abort/được helper quản lý abort; không được tiếp tục commit các thao tác còn lại như thể không có lỗi.

### 9.3. Commit và kết thúc session

```javascript
session.commitTransaction();
session.endSession();
```

Khi commit được xác nhận thành công theo cấu hình đã đặt, ba thay đổi thuộc cùng một transaction. Để xem dữ liệu sau commit, sử dụng một phiên đọc phù hợp:

```javascript
db.accounts.find(
  {},
  { _id: 1, balance: 1 }
).sort({ _id: 1 });

db.transfers.findOne({ _id: "transfer-001" });
```

**Quan trọng:** Đoạn `mongosh` ở các mục 9.1–9.3 được tách ra để người học nhìn rõ từng bước; nó **chưa phải cấu trúc xử lý lỗi production**. Nếu có exception sau `startTransaction()`, hãy abort khi phù hợp và luôn giải phóng session trong `finally`. Nếu `commitTransaction()` trả kết quả chưa rõ, **không phát lại toàn bộ logic chuyển tiền bằng session mới một cách mù quáng**; dùng helper transaction/retry theo driver và operation ID duy nhất. Không chạy lại ví dụ trên cùng dữ liệu nếu chưa đặt lại bộ dữ liệu thực hành có kiểm soát.

## 10. Vì sao một giao dịch có thể đọc được ghi của chính nó?

Trong transaction, nếu bạn cập nhật số dư A rồi đọc lại A **bằng cùng session và transaction**, phép đọc có thể nhìn thấy thay đổi chưa commit của chính transaction đó:

```javascript
// Dùng bên trong transaction trước commit
const currentA = txDb.accounts.findOne({ _id: "A" });
printjson(currentA.balance);
```

Điều đó không có nghĩa một client khác, bên ngoài transaction, được đọc thấy các thay đổi chưa commit. Khi transaction đang mở, các ghi thuộc transaction chưa được công bố ra bên ngoài như các ghi đã commit.

```text
Transaction T:
    update A: 500 -> 450
    read A trong T -> thấy thay đổi của T
    update B: 100 -> 150

Client ngoài T:
    trước commit -> không thấy bộ thay đổi chưa commit
    sau commit   -> thấy dữ liệu theo read policy và thời điểm
```

**Read-your-own-writes bên trong transaction** không được nhầm với cấu hình `readConcern: "majority"` hoặc `"snapshot"`: một loại nói về **thấy các sửa đổi của chính transaction**, còn loại kia nói về **bảo đảm đối với dữ liệu snapshot được đọc từ hệ thống**.

## 11. Transaction và read preference ngoài transaction

Ngoài transaction, một ứng dụng có thể sử dụng:

```javascript
db.getMongo().setReadPref("secondaryPreferred")
```

để phục vụ báo cáo ít yêu cầu độ mới, hoặc tạo client riêng với `ReadPreference.secondary()`. Nhưng đối với transaction chứa read operations, lựa chọn đó không biến secondary thành nơi thực thi transaction được hỗ trợ.

Một kiến trúc phổ biến là:

```text
                         ỨNG DỤNG
                             |
           +-----------------+-----------------+
           |                                   |
           v                                   v
  Giao dịch chuyển tiền                 Báo cáo thống kê
  readPref = primary                    readPref = secondaryPreferred
  readConcern = snapshot                readConcern = majority/local
  commit writeConcern = majority        Thao tác đọc ngoài transaction
```

Tách biệt mục tiêu giúp tránh vô tình kế thừa read preference của báo cáo vào giao dịch. Nếu cần báo cáo nhiều document nhất quán tại một snapshot, hãy đánh giá khả năng dùng snapshot reads ngoài transaction trên những phiên bản và thao tác hỗ trợ, thay vì mặc định mở transaction dài.

## 12. Trường hợp sharded cluster: vì sao read concern quan trọng hơn?

Trên một replica set, các document có thể nằm trong cùng một tập bản sao. Với sharded cluster, transaction có thể đọc/ghi dữ liệu từ nhiều shard khác nhau:

```text
        Transaction T
           /    \
          /      \
      Shard A   Shard B
      accounts  transfers
          \      /
           \    /
       Điều phối commit
```

Ba điểm cần nhớ:

1. **`"local"`** không bảo đảm các shard trả dữ liệu từ cùng một thời điểm.
2. **`"majority"`** có thể bảo đảm nguồn dữ liệu majority-committed khi commit `w:"majority"`, nhưng các shard vẫn có thể cung cấp những góc nhìn thời gian khác nhau.
3. **`"snapshot"`** cung cấp một snapshot đồng bộ qua các shard theo ngữ nghĩa transaction, với bảo đảm majority-committed khi commit `w:"majority"`.

### Ví dụ về hai phép đọc liên quan

Một transaction đọc tổng tồn kho ở shard A và bảng giữ chỗ ở shard B. Nếu hai nguồn chỉ hợp lệ khi được nhìn trong **cùng một mốc trạng thái**, cấu hình `readConcern:"snapshot"` giúp biểu diễn ý định tốt hơn `"majority"`, vốn không bảo đảm đồng bộ snapshot xuyên shard.

Tuy nhiên, snapshot **không tự khóa tất cả document để ngăn ghi đồng thời**. Một transaction có thể đọc dữ liệu cũ; nếu tranh chấp cập nhật, cần xử lý write conflicts hoặc áp dụng kỹ thuật đồng bộ hóa phù hợp với nghiệp vụ.

### Không hứa các client ngoài transaction sẽ thấy commit ngay trên mọi shard

Một distributed transaction đã commit có tính nguyên tử đối với những thay đổi của transaction. Nhưng với những phép đọc **ngoài transaction** và mức read concern không phù hợp, một client có thể quan sát thời điểm hiển thị cập nhật khác nhau giữa các shard trong quá trình hệ thống công bố kết quả. Không suy từ việc `commitTransaction()` thành công rằng **mọi phép đọc local trên mọi shard** đều tức khắc thấy cùng một trạng thái.

Khi hệ thống yêu cầu quan sát đồng bộ qua nhiều shard, cần lựa chọn read concern và cơ chế đọc tương ứng.

## 13. Ví dụ Java MongoDB Sync Driver với `TransactionOptions`

Trong Java, `TransactionOptions` tập hợp ba quyết định ở cấp transaction. Với driver đồng bộ:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;

import java.util.concurrent.TimeUnit;

TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(
        WriteConcern.MAJORITY
            .withJournal(true)
            .withWTimeout(10, TimeUnit.SECONDS)
    )
    .readPreference(ReadPreference.primary())
    .build();
```

Tương đương về ý nghĩa với cấu hình:

```javascript
{
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  },
  readPreference: { mode: "primary" }
}
```

**Không** đặt write concern riêng trên từng `updateOne(session, ...)` bên trong transaction. Nếu collection handle có cấu hình write concern mặc định, transaction vẫn sử dụng **transaction-level write concern tại commit**; đừng hiểu rằng từng update đang được majority acknowledged trước khi commit.

### 13.1. Mã Java đầy đủ: chuyển tiền và dùng callback API

Ví dụ dưới đây minh họa cùng nghiệp vụ ở mục 9 bằng Java Sync Driver. Nó giả định `accounts` và `transfers` đã được tạo ngoài transaction, tài khoản A/B có số dư Decimal128 và chưa có document `transfer-java-001`.

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.util.Date;
import java.util.concurrent.TimeUnit;

public class MoneyTransferTransaction {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        Decimal128 amount =
            new Decimal128(new BigDecimal("50.00"));
        Decimal128 negativeAmount =
            new Decimal128(new BigDecimal("-50.00"));

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(
                WriteConcern.MAJORITY
                    .withJournal(true)
                    .withWTimeout(10, TimeUnit.SECONDS)
            )
            .readPreference(ReadPreference.primary())
            .build();

        try (MongoClient client = MongoClients.create(uri);
             ClientSession session = client.startSession()) {

            MongoDatabase db =
                client.getDatabase("mongo_transaction_concern_lab");
            MongoCollection<Document> accounts =
                db.getCollection("accounts");
            MongoCollection<Document> transfers =
                db.getCollection("transfers");

            String transferId = "transfer-java-001";

            session.withTransaction(() -> {
                UpdateResult debit = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", "A"),
                        Filters.gte("balance", amount)
                    ),
                    new Document("$inc",
                        new Document("balance", negativeAmount))
                );
                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Tài khoản A không đủ số dư");
                }

                UpdateResult credit = accounts.updateOne(
                    session,
                    Filters.eq("_id", "B"),
                    new Document("$inc",
                        new Document("balance", amount))
                );
                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Không tìm thấy tài khoản B");
                }

                transfers.insertOne(session,
                    new Document("_id", transferId)
                        .append("from", "A")
                        .append("to", "B")
                        .append("amount", amount)
                        .append("status", "committed")
                        .append("createdAt", new Date())
                );

                return transferId;
            }, options);

            System.out.println("Transaction hoàn tất");
        }
    }
}
```

Giải thích các phần quan trọng:

- `session.withTransaction(callback, options)` giúp driver khởi tạo, commit/abort và áp dụng quy tắc retry cho các lỗi transaction phù hợp.
- Mỗi thao tác ghi đều nhận **`session`** ở đối số đầu tiên.
- Cả ba thay đổi có chung transaction-level **read concern, write concern và read preference**.
- Điều kiện `balance >= amount` tránh trừ vượt số dư tại thời điểm cập nhật; các giao dịch cạnh tranh có thể gây write conflict và được xử lý theo retry policy.
- `transferId` là khóa nghiệp vụ duy nhất. Nếu gọi **một transaction mới** với cùng ID sau khi transaction trước đã commit, unique key có thể ngăn tạo lịch sử trùng, nhưng ứng dụng vẫn phải xử lý duplicate theo nghiệp vụ.

**Lưu ý về `withTransaction`:** callback có thể được driver chạy lại trong một số lỗi tạm thời. Đừng tạo phí thanh toán ngoài MongoDB, gửi email hoặc phát một sự kiện không thể hoàn tác bên trong callback nếu hành động đó chưa có cơ chế idempotency. Code chỉ có ý nghĩa thực hành trên database lab; với hệ thống tiền tệ cần thiết kế ledger, chống trùng và xử lý lỗi đầy đủ hơn.

### 13.2. Ví dụ sai: quên truyền session

```java
session.withTransaction(() -> {
    accounts.updateOne(
        Filters.eq("_id", "A"),
        new Document("$inc", new Document("balance", negativeAmount))
    );

    // ...
    return null;
}, options);
```

Lệnh `updateOne()` ở trên **không truyền `session`**. Nó có thể chạy như một thao tác ghi bình thường **ngoài transaction**, nên nếu callback phía sau thất bại, thao tác đó không được rollback cùng transaction.

Cách đúng là:

```java
accounts.updateOne(
    session,
    Filters.eq("_id", "A"),
    new Document("$inc", new Document("balance", negativeAmount))
);
```

### 13.3. Ví dụ sai: cấu hình collection để đổi concern giữa chừng

Không làm như sau để cố đổi read concern của riêng một lệnh trong transaction:

```java
MongoCollection<Document> oneCollection =
    accounts.withReadConcern(ReadConcern.LOCAL);

oneCollection.find(session, Filters.eq("_id", "A")).first();
```

Read concern có hiệu lực của thao tác thuộc transaction lấy từ **transaction-level configuration**, không phải một mức local mới đặt riêng ở collection handle để ghi đè giữa chừng.

Tương tự, không tự đặt `withWriteConcern(WriteConcern.W1)` trên một collection để “giảm yêu cầu” cho một ghi con của transaction đã chọn commit majority.

## 14. Ví dụ `mongosh`: ba cấu hình dẫn đến ba cam kết khác nhau

Giả sử một replica set P–S1–S2 có ba data-bearing voting members. Hệ thống chạy cùng nghiệp vụ ở ba môi trường thử nghiệm tách biệt:

### Trường hợp A — `local` + commit `w:1`

```javascript
{
  readConcern: { level: "local" },
  writeConcern: { w: 1 }
}
```

Ưu tiên acknowledgment trên primary, nhưng không bảo đảm snapshot của dữ liệu đã majority-committed và commit có thể bị rollback khi failover.

### Trường hợp B — `majority` + commit `w:"majority"`

```javascript
{
  readConcern: { level: "majority" },
  writeConcern: { w: "majority" }
}
```

Các bảo đảm đọc majority-committed của transaction đi kèm commit majority. Nhưng khi dữ liệu phân tán nhiều shard, `"majority"` không bảo đảm một snapshot **đồng bộ thời gian** xuyên shard.

### Trường hợp C — `snapshot` + commit `w:"majority"`

```javascript
{
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority", j: true },
  readPreference: { mode: "primary" }
}
```

Đây là lựa chọn minh họa cho giao dịch cần snapshot nhất quán và xác nhận commit majority. Nó vẫn không loại bỏ các vấn đề như stale snapshot đối với thay đổi mới bên ngoài, write conflict, transaction timeout hoặc nhu cầu idempotency.

**Không có phép chọn mức nào tự biến giao dịch thành hệ thống thanh toán hoàn chỉnh.** ACID transaction giúp tổ chức nguyên tử các ghi trong MongoDB; với ngoại tác nằm ngoài MongoDB, ứng dụng cần pattern thích hợp như outbox, idempotency key và xử lý đối soát.

## 15. Phân biệt đọc snapshot với khóa dữ liệu

Một quan niệm dễ nhầm là: dùng `readConcern:"snapshot"` có nghĩa MongoDB đã khóa mọi document mà transaction đọc và không cho giao dịch khác thay đổi chúng.

Điều đó **không đúng**. Snapshot isolation cho phép transaction quan sát một phiên bản dữ liệu nhất quán; nó không tự giữ toàn bộ document đã đọc khỏi bị cập nhật bởi transaction khác. Một tình huống:

```text
T1: đọc document account A trong snapshot
T2: cập nhật account A và commit
T1: cố cập nhật A dựa trên snapshot cũ
    |
    v
  Có thể gặp write conflict -> cần retry transaction
```

Nếu nghiệp vụ phải bảo đảm một điều kiện trên dữ liệu hiện hành, hãy dùng **conditional write**, kiểm soát phiên bản hoặc các phương thức khóa/cập nhật phù hợp. Ví dụ:

```javascript
txDb.accounts.updateOne(
  {
    _id: "A",
    balance: { $gte: NumberDecimal("50.00") }
  },
  { $inc: { balance: NumberDecimal("-50.00") } }
)
```

là một cập nhật có điều kiện, không chỉ là đọc rồi quyết định trừ dựa trên một giá trị có thể đã thay đổi.

### Có thể gặp stale read bên trong transaction

Do snapshot được giữ ổn định, transaction dài có thể đọc một trạng thái đã cũ so với cập nhật mới của transaction khác. Với một số trường hợp cần ép một document được khóa/cập nhật để bảo vệ điều kiện, MongoDB hướng dẫn các mẫu như `findOneAndUpdate()` nhằm ghi thay đổi và lấy lock phù hợp. Đây là lựa chọn phải đánh giá theo nghiệp vụ, vì nó phát sinh write và tăng khả năng tranh chấp; không dùng chỉ để “làm mới mọi snapshot”.

## 16. Transaction không tự xử lý được mọi lần đọc nhất quán bên ngoài

Giả sử transaction cập nhật A và B rồi commit bằng `w:"majority"`. Client khác đọc từ một secondary có thể vẫn thấy trạng thái cũ tùy read preference/read concern và replication lag.

```text
             T1 commit majority
                     |
          +----------+-----------+
          |                      |
   Đọc primary              Đọc secondary
   theo read concern        có thể đang lag
          |                      |
   Trạng thái tùy           Trạng thái tùy
   thời điểm/concern        thời điểm/concern
```

Write concern majority xác nhận mức bền của commit; nó **không bắt mọi secondary lập tức trả phiên bản mới nhất**. Cần phối hợp read concern/read preference/session của **lần đọc tiếp theo** nếu ứng dụng yêu cầu read-your-writes hay causal consistency.

Ngoài transaction, read preference khác `primary` có thể hợp lệ khi nghiệp vụ chấp nhận stale reads. Nhưng read preference trong transaction có quy tắc riêng như đã trình bày ở mục 7.

## 17. Các giới hạn vận hành đáng chú ý

### 17.1. Transaction dài làm tăng chi phí

Transaction dài có thể giữ snapshot và tài nguyên lưu trữ lâu hơn cần thiết, tăng áp lực cache và khả năng xung đột khi ghi. MongoDB có các giới hạn thời gian transaction; giá trị mặc định của `transactionLifetimeLimitSeconds` thường là 60 giây ở những cấu hình thông thường, nhưng có thể được điều chỉnh theo phiên bản/triển khai.

Đừng giữ transaction mở trong khi gọi HTTP API, chờ người dùng nhập biểu mẫu hoặc chạy một báo cáo nhiều phút. Nên tính trước những dữ liệu có thể tính ngoài transaction, sau đó chỉ giữ phần đọc/ghi cần nguyên tử ở bên trong.

### 17.2. Không chạy song song nhiều thao tác trong cùng transaction

Không nên dùng nhiều thread cùng thao tác trên một `ClientSession` hoặc chạy các truy vấn trong transaction như một batch parallel tùy ý. MongoDB drivers có quy tắc tuần tự hóa hoạt động session/transaction. Với Java Sync Driver, thực hiện các thao tác cần thiết **tuần tự** trong callback.

### 17.3. Một số command không hợp lệ trong transaction

Không thể mặc nhiên đưa mọi loại command (ví dụ những thao tác quản trị/DDL nhất định hoặc aggregation có `$out`/`$merge`) vào transaction như lệnh CRUD thông thường. Khi tạo collection/index tường minh trong transaction ở những phiên bản hỗ trợ, read concern có hạn chế riêng, bao gồm yêu cầu `"local"` cho thao tác tạo tường minh. Phải kiểm tra tài liệu theo phiên bản và loại collection/sharding.

### 17.4. Không thay thế backup bằng majority

Commit majority giúp giảm rủi ro rollback khi failover theo giao thức. Nó không bảo vệ trước mọi lỗi thao tác của con người, xóa nhầm dữ liệu đã commit, phá hủy đồng thời nhiều failure domains hoặc yêu cầu khôi phục theo thời điểm. Backup và phục hồi là một lớp thiết kế riêng.

### 17.5. `wtimeout` khác transaction lifetime và commit deadline

`wtimeout` nằm trong write concern; nó không phải số giây tối đa cho toàn bộ callback transaction. Driver còn có thể có timeout cho giao dịch hoặc `maxCommitTimeMS` theo API/phiên bản, và server có giới hạn thời gian transaction. Khi điều tra timeout, xác định **tầng gây lỗi** thay vì tăng mọi tham số thời gian tùy ý.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Transaction thì không cần read concern” | Mức đọc quyết định dữ liệu được phép quan sát | Chọn `local`, `majority` hoặc `snapshot` theo yêu cầu |
| “`majority` read concern luôn bảo đảm đọc majority trong transaction” | Bảo đảm gắn với commit `w:"majority"` | Kiểm tra cả read concern **và** commit write concern |
| “`snapshot` tự bảo đảm dữ liệu majority-committed dù commit `w:1`” | Điều kiện commit majority là thiết yếu | Dùng `snapshot + majority` nếu cần bảo đảm đó |
| “`majority` là snapshot đồng bộ xuyên shard” | Majority không bảo đảm cùng thời điểm giữa các shards | Cần `snapshot` cho synchronized cross-shard view |
| “Có thể đọc secondary trong transaction để giảm tải primary” | Transaction chứa read operations cần read preference primary | Tách báo cáo secondary ra ngoài transaction nếu phù hợp |
| “Read concern trên collection tự ghi đè transaction” | Transaction sử dụng transaction-level read concern | Cấu hình ở session/transaction |
| “Có thể đặt `w:1` cho update A, `w:majority` cho update B trong một transaction” | Write concern per-operation trong transaction không được hỗ trợ | Đặt transaction-level write concern tại commit |
| “Mọi update trong transaction được majority ack ngay trước commit” | Write concern được dùng ở thời điểm commit | Phân biệt thao tác nội bộ và xác nhận commit |
| “`commitTransaction` bị timeout nghĩa là transaction đã abort” | Commit có thể đã diễn ra nhưng ACK bị mất/chậm | Phân biệt unknown commit và abort |
| “Gọi lại callback luôn an toàn với mọi thao tác” | Callback có thể chạy nhiều lần | Không đặt side effect ngoài DB chưa idempotent trong callback |
| “Quên truyền session vào một update cũng không sao” | Update đó có thể chạy ngoài transaction | Truyền cùng session cho tất cả thao tác |
| “Snapshot luôn là dữ liệu mới nhất” | Snapshot có thể cũ so với ghi đồng thời | Xử lý stale read và write conflict |
| “Chọn `j:true` thay cho majority replication” | Journal và replica acknowledgment là hai bảo đảm khác nhau | Kết hợp theo mục tiêu durability |
| “`readPreference:secondaryPreferred` từ client vẫn ổn với transaction” | Transaction có read operations phải dùng primary | Ghi đè `ReadPreference.primary()` ở transaction |
| “Multi-document transaction luôn thay thế thiết kế document tốt” | Transaction có overhead/giới hạn vận hành | Ưu tiên atomic single-document khi mô hình dữ liệu đáp ứng |

## 19. Bài tập thực hành

### Bài 1. Chọn read concern để đồng bộ thời điểm giữa shards

Một transaction đọc hai bảng dữ liệu trên hai shard khác nhau. Báo cáo phải dựa trên **cùng một góc nhìn thời điểm** và cần bảo đảm snapshot của dữ liệu majority-committed.

**Đáp án:** Dùng read concern `"snapshot"` ở cấp transaction và commit với write concern `w:"majority"`. Read concern `"majority"` không tự bảo đảm snapshot đồng bộ xuyên shards.

### Bài 2. Tìm lỗi trong cấu hình commit

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: 1 }
})
```

Người lập trình khẳng định: “Đã dùng snapshot nên transaction chắc chắn đọc snapshot majority-committed và commit không thể rollback trong failover.”

**Đáp án:** Kết luận sai. Với transaction commit `w:1`, read concern snapshot **không bảo đảm snapshot majority-committed** theo tài liệu MongoDB. Commit chỉ được primary xác nhận và vẫn có thể rollback nếu chưa đạt majority trước failover.

### Bài 3. Write concern đặt sai vị trí

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" }
})

txDb.accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: -10 } },
  { writeConcern: { w: "majority" } }
)
```

Sai ở đâu?

**Đáp án:** Không được đặt write concern riêng cho một lệnh update trong transaction. Hãy khai báo `writeConcern: {w:"majority"}` ở **cấp transaction** khi start, để MongoDB áp dụng vào commit.

### Bài 4. Read preference kế thừa từ client

Ứng dụng dùng một `MongoClient` có read preference `secondaryPreferred` cho báo cáo. Nó dùng cùng client mở transaction cần `findOne()` và `updateOne()`, nhưng không đặt read preference ở transaction.

**Đáp án:** Transaction có read operations phải dùng `primary`. Nếu kế thừa `secondaryPreferred`, driver có thể từ chối thao tác đọc trong transaction. Khai báo `ReadPreference.primary()` trong `TransactionOptions` hoặc tạo session/client phù hợp.

### Bài 5. Timeout commit và xử lý retry

Ứng dụng chuyển tiền bằng transaction, gọi `commitTransaction()` nhưng nhận lỗi có nhãn `UnknownTransactionCommitResult`. Có nên bắt đầu một transaction mới và trừ tiền lại ngay?

**Đáp án:** Không. Trạng thái commit của transaction cũ có thể đã thành công. Cần retry **commit của cùng transaction** theo hướng dẫn driver, hoặc dùng helper `withTransaction` và cơ chế idempotency nghiệp vụ. Không tạo một lần chuyển tiền mới mà không kiểm tra/deduplicate.

### Bài 6. Phân biệt `local`, `majority` và `snapshot`

Điền mục tiêu thích hợp:

1. Chỉ yêu cầu dữ liệu hiện có trên node, không cam kết majority.
2. Cần bảo đảm đọc majority-committed khi commit transaction bằng majority.
3. Cần snapshot đồng bộ khi đọc dữ liệu qua nhiều shard và commit majority.

**Đáp án:** (1) `local`; (2) `majority`; (3) `snapshot`.

### Bài 7. Java: thao tác nào nằm ngoài transaction?

```java
session.withTransaction(() -> {
    accounts.updateOne(session, Filters.eq("_id", "A"), debit);
    accounts.updateOne(Filters.eq("_id", "B"), credit);
    return null;
}, options);
```

**Đáp án:** Update của B **không truyền session**, nên có thể chạy ngoài transaction. Phải dùng `accounts.updateOne(session, Filters.eq("_id","B"), credit)`.

### Bài 8. Snapshot có khóa toàn bộ dữ liệu đọc không?

T1 bắt đầu transaction snapshot và đọc account A. T2 sửa A rồi commit. T1 tiếp tục và cố cập nhật A. Có thể bảo đảm T1 luôn update thành công vì nó đã đọc snapshot không?

**Đáp án:** Không. T1 có thể nhìn dữ liệu cũ và gặp **write conflict** khi cập nhật. Cần xử lý retry transaction và dùng các điều kiện cập nhật phù hợp để bảo vệ quy tắc nghiệp vụ.

### Bài 9. Read-your-writes bên trong transaction

T1 cập nhật A từ 500 xuống 450, chưa commit. T1 đọc A bằng cùng session; client B ở ngoài transaction đọc A ngay lúc đó. Hỏi có thể kết luận gì?

**Đáp án:** T1 có thể đọc thấy thay đổi của chính mình trong transaction. Client B không được tự nhìn thấy thay đổi chưa commit của T1 như dữ liệu đã được công bố; kết quả đọc của B phụ thuộc trạng thái đã commit và read policy. Hai hành vi không mâu thuẫn nhau.

### Bài 10. Cấu hình cho một nghiệp vụ chuyển tiền

Bạn cần chuyển tiền giữa hai tài khoản trong cùng replica set; việc đọc số dư phải dựa trên snapshot được majority committed và các thay đổi phải được majority acknowledged khi commit. Đề xuất ba tùy chọn.

**Đáp án tham khảo:**

```javascript
{
  readConcern: { level: "snapshot" },
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 10000
  },
  readPreference: { mode: "primary" }
}
```

`j:true` và `wtimeout` cần được lựa chọn theo cấu hình journal, độ trễ và khả năng xử lý lỗi thực tế. Bên cạnh ba tùy chọn, nghiệp vụ vẫn cần idempotency, điều kiện số dư, xử lý write conflict và retry an toàn.

## 20. Checklist triển khai transaction

Khi viết transaction MongoDB trong một ứng dụng, kiểm tra các câu hỏi sau:

1. **Có thật sự cần multi-document transaction không?** Một document chứa đủ dữ liệu liên quan có thể đã đáp ứng yêu cầu nguyên tử.
2. **Đang kết nối replica set hoặc sharded cluster hỗ trợ?** Standalone không thay thế môi trường transaction thực tế.
3. **Tất cả thao tác đều dùng cùng session?** Không có một câu lệnh ghi ngoài session do quên tham số.
4. **Read concern được đặt ở transaction?** Chỉ chọn `local`, `majority`, `snapshot` theo ngữ nghĩa cần bảo đảm.
5. **Nếu cần majority-committed snapshot, commit có `w:"majority"`?** Không dựa vào `snapshot` kết hợp `w:1` rồi hứa dữ liệu đã majority committed.
6. **Read preference có phải primary?** Đặc biệt khi client báo cáo mặc định đọc từ secondary.
7. **Write concern đặt ở transaction, không ở từng lệnh?** Phải kiểm tra `w`, `j`, `wtimeout` tại commit.
8. **Đã xử lý lỗi commit chưa rõ?** Phân biệt `UnknownTransactionCommitResult` với lỗi cần retry toàn transaction.
9. **Callback có side effect ngoài DB không?** Nếu có, cần idempotency/outbox phù hợp vì callback có thể được chạy lại.
10. **Transaction có ngắn và tuần tự không?** Tránh giữ snapshot trong lúc gọi API ngoài, chờ người dùng hoặc chạy job dài.
11. **Đọc sau commit cần độ mới thế nào?** Thiết kế read concern/read preference/session phù hợp cho các thao tác ngoài transaction.
12. **Đã đối chiếu server/driver version và deployment chưa?** Đặc biệt với sharding, journaling, DDL và các giới hạn production.

## 21. Kết luận

Trong MongoDB, ba tùy chọn có vai trò **khác nhau nhưng liên kết chặt chẽ**:

- **Read concern** xác định bảo đảm của dữ liệu được đọc trong transaction: `"local"`, `"majority"` hoặc `"snapshot"`.
- **Write concern** xác định mức xác nhận **commit**: `w:1` chỉ primary acknowledgment, còn `w:"majority"` cho các bảo đảm majority cần thiết; `j` và `wtimeout` bổ sung yêu cầu journal và thời gian chờ.
- **Read preference** xác định nơi gửi read operations. **Transaction có thao tác đọc phải dùng `primary`**, không phải secondary.

Tổ hợp `readConcern:"snapshot"` + `writeConcern:{w:"majority"}` + `readPreference:"primary"` là một ví dụ quan trọng khi cần snapshot majority-committed và commit với mức xác nhận mạnh. Nhưng cấu hình đúng vẫn cần đi kèm **session xuyên suốt**, **conditional writes**, **xử lý retry/unknown commit**, **idempotency** và quan sát replication trên môi trường thực tế.

### Tài liệu chính thức để đối chiếu theo phiên bản

- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Java Sync Driver — Configure Read and Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/read-write-config/)
