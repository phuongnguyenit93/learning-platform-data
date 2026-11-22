# Isolation, snapshot và dữ liệu nhìn thấy trong giao dịch

Khi hai request cùng thao tác trên một cơ sở dữ liệu NoSQL, câu hỏi không chỉ là **một lệnh ghi có thành công hay không**, mà còn là **giao dịch đang nhìn thấy phiên bản nào của dữ liệu**. Nếu giao dịch A đọc một đơn hàng rồi giao dịch B cập nhật đơn hàng đó, A có nhìn thấy phiên bản mới khi đọc lại không? Nếu A vừa ghi nhưng chưa commit, ai được đọc thay đổi đó? Nếu hai giao dịch cùng kiểm tra một quy tắc rồi ghi hai document khác nhau, quy tắc ấy có còn đúng sau commit không?

Đó là những câu hỏi của **isolation** — tính cô lập trong giao dịch. Trong NoSQL, chúng đặc biệt quan trọng vì mô hình dữ liệu có thể trải trên nhiều document, partition, shard và replica. Một số hệ hỗ trợ thao tác nguyên tử trên một document, một số hỗ trợ transaction nhiều document, một số dùng **snapshot isolation**, và mỗi sản phẩm có phạm vi bảo đảm khác nhau.

Bài học giải thích sự khác biệt giữa **atomicity, isolation và durability**, cơ chế **MVCC/snapshot**, những hiện tượng khi ghi đồng thời như *non-repeatable read*, *phantom*, *lost update*, *write skew*, cùng cách kiểm chứng bằng **hai session MongoDB**. Trọng tâm là hiểu **dữ liệu nào thực sự được phép xuất hiện trong mỗi giao dịch**, thay vì mặc định hễ gọi transaction thì mọi vấn đề đồng thời đều được giải quyết.

## 1. Isolation nằm ở đâu trong ACID?

| Thuộc tính | Điều được bảo vệ | Ví dụ |
| --- | --- | --- |
| **Atomicity** | Các thay đổi trong ranh giới transaction cùng commit hoặc abort | Không tạo đơn thành công nếu bước ghi bắt buộc bị bỏ |
| **Consistency** | Trạng thái dữ liệu tuân thủ những bất biến hợp lệ | Không cho phép tồn kho âm khi nghiệp vụ cấm |
| **Isolation** | Những giao dịch đồng thời có thể nhìn thấy và ảnh hưởng nhau ra sao | T1 có thấy cập nhật chưa commit của T2? |
| **Durability** | Dữ liệu đã commit tồn tại qua loại sự cố được cam kết | Đơn vẫn tồn tại sau crash/failover phù hợp |

Từ *consistency* trong ACID nói về **quy tắc hợp lệ của trạng thái dữ liệu**. Nó khác *consistency level* của hệ phân tán, vốn liên quan việc các node/replica xác nhận và nhìn thấy dữ liệu. Hai lớp này có liên hệ nhưng **không đồng nghĩa**.

### 1.1. Atomicity không tự bảo đảm isolation

Một transaction có thể cập nhật nguyên tử một document mà vẫn góp phần tạo kết quả sai khi chạy cùng transaction khác.

Ví dụ ứng dụng quản lý ca trực có hai bác sĩ A và B. Bất biến nghiệp vụ:

> Trong mọi thời điểm hợp lệ, phải có ít nhất một bác sĩ đang trực.

Hai giao dịch chạy đồng thời:

```text
Ban đầu: A.onCall=true, B.onCall=true

Transaction T1                 Transaction T2
----------------------------   ----------------------------
Đọc A=true, B=true
                               Đọc A=true, B=true
Đặt A.onCall=false
                               Đặt B.onCall=false
COMMIT
                               COMMIT

Cuối cùng: A=false, B=false
```

Mỗi transaction chỉ sửa một document và có thể được commit nguyên tử. Nhưng kết quả cuối vi phạm bất biến. Vấn đề này là **write skew**, và nó có thể xảy ra ở một mô hình snapshot isolation không tự bảo vệ quy tắc tổng thể.

### 1.2. Durability và isolation là hai trục khác nhau

Một giá trị có thể đang được transaction nhìn thấy trong RAM trước khi đạt độ bền theo chính sách sync log; ngược lại, dữ liệu đã lưu bền trên một replica có thể chưa được một replica khác nhìn thấy.

Vì vậy, “đã đọc thấy” không đồng nghĩa “đã lưu bền”, và “đã bền” không có nghĩa mọi transaction đều nhìn cùng một version.

## 2. Giao dịch “nhìn thấy” dữ liệu nghĩa là gì?

Giả sử một đơn hàng ban đầu có `status = PENDING`.

```text
Thời gian →

T1 bắt đầu         T2 cập nhật rồi commit        T1 đọc lại
     |                       |                         |
     | READ=PENDING          | UPDATE=PAID             |
     |                       | COMMIT                  |
     |                       |                         |
     +-----------------------+-------------------------+
```

Lần đọc thứ hai của T1 có thể thấy:

- **PENDING** vì transaction T1 được cố định vào một snapshot cũ.
- **PAID** vì mức isolation cho phép mỗi statement nhìn trạng thái đã commit mới hơn.
- Một giá trị khác hoặc một lỗi nếu có thêm writer, xung đột, replica lag hay quy tắc đọc đặc biệt.

Cần xác định **isolation level**, **thời điểm snapshot được thiết lập**, **session**, **read concern** và **node được đọc** trước khi kết luận.

### 2.1. Ba thời điểm phải tách biệt

1. **Begin transaction:** ứng dụng gọi thao tác bắt đầu giao dịch.
2. **Thiết lập snapshot/read timestamp:** engine chọn góc nhìn logic cho các lần đọc.
3. **Commit:** những write của transaction được chấp thuận và công bố theo hợp đồng.

Không phải hệ nào cũng cố định snapshot **ngay lúc gọi `startTransaction()`**. Có hệ lấy snapshot ở lệnh đầu tiên, lệnh đọc đầu tiên hoặc theo cơ chế phối hợp thời gian riêng.

### 2.2. Nhất quán không nhất thiết là mới nhất

Transaction giữ một snapshot có thể đọc một tập document **nhất quán theo thời điểm cũ**. Đây là điều hữu ích cho báo cáo nhiều truy vấn, nhưng có thể không phù hợp khi một thao tác cần **trạng thái mới nhất tại thời điểm ra quyết định**.

Muốn bảo vệ quyết định phụ thuộc dữ liệu hiện hành, thường cần thêm **conditional write**, version/lock/guard hoặc mức isolation mạnh hơn.

## 3. Các hiện tượng bất thường khi đọc và ghi đồng thời

### 3.1. Dirty read — đọc thay đổi chưa commit

```text
T1                                T2
---------------------------------- --------------------------------
UPDATE price=200
                                   READ price -> 200
ROLLBACK
```

Nếu T2 đọc được 200 khi T1 chưa commit, rồi T1 rollback, T2 đã dùng giá trị **không bao giờ trở thành dữ liệu đã commit**.

Một isolation level ngăn dirty read vẫn có thể cho phép **cùng một giao dịch đọc hai giá trị đã commit khác nhau**.

### 3.2. Non-repeatable read — cùng document, khác giá trị

```text
T1                                T2
---------------------------------- --------------------------------
READ price -> 100
                                   UPDATE price=200
                                   COMMIT
READ price -> 200
```

T1 đọc lại document và nhận giá trị mới đã commit. Đó là *non-repeatable read*. Nếu transaction đang kiểm tra các trường liên quan qua nhiều lần đọc, sự thay đổi này có thể dẫn tới tính toán không nhất quán.

### 3.3. Phantom read — tập kết quả thay đổi

```text
T1                                       T2
----------------------------------------- --------------------------------
COUNT orders WHERE status=PENDING -> 3
                                          INSERT order-4 PENDING
                                          COMMIT
COUNT orders WHERE status=PENDING -> 4
```

Cùng một predicate mà tập document khớp thay đổi do giao dịch khác chèn/sửa/xóa record. Đây là *phantom read*.

**Non-repeatable read** tập trung vào một bản ghi đã đọc; **phantom** liên quan tới **thành viên của tập kết quả**.

### 3.4. Lost update — mất một lần cập nhật

```text
counter = 10

T1 READ counter=10
T2 READ counter=10
T1 WRITE counter=11
T2 WRITE counter=11

Kết quả: 11 thay vì 12.
```

Cả hai client đọc giá trị 10, tự tính rồi ghi đè bằng `11`. Một lần tăng bị mất. Có thể tránh bằng atomic increment, compare-and-set, optimistic version hoặc cơ chế conflict detection phù hợp.

### 3.5. Read skew — đọc tổ hợp trạng thái sai thời điểm

Giả sử hai tài khoản A=60 và B=40; một transaction khác chuyển 10 từ A sang B.

```text
T1 đọc A=60.
T2 chuyển tiền, commit A=50 và B=50.
T1 đọc B=50.

T1 tính tổng 110, trong khi trạng thái hợp lệ đều có tổng 100.
```

T1 đã trộn hai snapshot khác nhau. Một snapshot nhất quán trên cả A và B có thể ngăn hiện tượng này trong phạm vi transaction được hỗ trợ.

### 3.6. Write skew — quyết định dựa trên snapshot, ghi khác document

```text
Constraint: count(doctors where onCall=true) >= 1

T1 đọc: A=true, B=true
T2 đọc: A=true, B=true

T1 UPDATE A.onCall=false
T2 UPDATE B.onCall=false

T1 COMMIT
T2 COMMIT

Final: 0 doctor on call
```

Hai transaction không cập nhật cùng một document, nên cơ chế chỉ phát hiện **write-write conflict trên cùng đối tượng** có thể không chặn chúng. Đây là điểm hạn chế kinh điển của **snapshot isolation**.

## 4. Những mức isolation thường được nhắc tới

| Mức | Ý nghĩa khái quát | Hiện tượng vẫn cần chú ý |
| --- | --- | --- |
| **Read Uncommitted** | Có thể cho đọc dữ liệu chưa commit trong một số mô hình | Dirty read |
| **Read Committed** | Không đọc thay đổi chưa commit của transaction khác | Non-repeatable read, phantom |
| **Repeatable Read** | Hướng tới việc đọc lại record có kết quả ổn định | Phantom và write conflict phụ thuộc implementation |
| **Snapshot Isolation (SI)** | Giao dịch đọc snapshot nhất quán, thường có kiểm soát write-write conflict | **Write skew** |
| **Serializable** | Lịch thực thi tương đương một thứ tự chạy tuần tự các transaction | Có thể tăng xung đột/abort/retry |

Đây là bảng diễn giải, **không phải cam kết mọi NoSQL hỗ trợ đủ năm mức hoặc triển khai giống nhau**. Snapshot isolation không đơn thuần là một “bậc ANSI SQL” có mặt theo cùng tên trong mọi engine.

### 4.1. Serializable có nghĩa gì?

Một lịch nhiều giao dịch được xem là *serializable* nếu hiệu ứng và các quan sát hợp lệ của chúng tương đương một **lịch chạy từng transaction một** theo một thứ tự nào đó.

Trong bài toán hai bác sĩ:

- Nếu T1 chạy trọn trước T2, T2 phải thấy chỉ còn B trực, nên không được cho B nghỉ.
- Nếu T2 chạy trọn trước T1, T1 phải thấy chỉ còn A trực.

Lịch cả hai cùng đọc “còn hai người trực” rồi cùng cho nghỉ không tương đương lịch tuần tự bảo toàn bất biến.

### 4.2. Serializable không đồng nghĩa linearizable

- **Serializability:** nói về tính tương đương với lịch tuần tự của các transaction.
- **Linearizability:** yêu cầu một thứ tự tuyến tính tôn trọng thứ tự thời gian thực của những thao tác liên quan.
- **Strict serializability:** bổ sung yêu cầu thời gian thực cho lịch transaction serializable.

Không nên dùng ba khái niệm đó thay thế nhau khi đánh giá sản phẩm phân tán.

## 5. MVCC: nền tảng phổ biến của snapshot

**Multi-Version Concurrency Control (MVCC)** quản lý nhiều **version logic** của cùng một dữ liệu để reader có thể xem phiên bản phù hợp mà không nhất thiết phải chặn writer.

Ví dụ:

| Version | Giá trị | Commit time logic |
| --- | --- | --- |
| v1 | `balance=500` | 100 |
| v2 | `balance=700` | 120 |
| v3 | `balance=650` | 135 |

Một transaction có snapshot ở mốc 110 có thể đọc v1; transaction khác ở 125 có thể đọc v2; một transaction đọc ở 140 có thể đọc v3.

```text
Commit time -->
  100      110      120      125      135      140
   |--------|--------|--------|--------|--------|
   v1     Snap A     v2     Snap B     v3      Snap C

A đọc 500, B đọc 700, C đọc 650.
```

Đây là **timestamp logic sư phạm**, không nhất thiết là timestamp đồng hồ hệ điều hành.

### 5.1. Snapshot không phải bản sao đầy đủ của database

Khi nói “transaction đọc snapshot”, không có nghĩa database copy toàn bộ collection vào RAM cho từng transaction. Engine có thể dùng nhiều version và metadata để tái tạo trạng thái.

Một mô hình gần đúng:

```text
visible(version, snapshotTime):
    version đã được commit
    AND version.commitTime <= snapshotTime
    AND không bị version/tombstone khác hợp lệ che đi
```

Thực tế phải xử lý thêm commit order, transaction chưa commit, metadata của shard, write conflict, tombstone và phiên bản do chính transaction tạo.

### 5.2. MVCC là kỹ thuật, isolation là hợp đồng

Một engine dùng MVCC vẫn có thể cung cấp read committed, snapshot hoặc các ngữ nghĩa khác. **Không thể suy isolation level chỉ từ việc engine sử dụng MVCC**.

### 5.3. Snapshot cũ có thể tốn tài nguyên

Nếu T1 giữ snapshot lâu, engine có thể phải giữ nhiều version cũ cho đến khi T1 kết thúc. Hệ quả:

- Tăng dung lượng lịch sử hoặc cache.
- Tăng nguy cơ conflict.
- Chậm thu hồi phiên bản cũ, compaction hoặc checkpoint theo cách triển khai.
- Tăng latency và khả năng timeout.
- Có thể gặp giới hạn history window/snapshot too old trong những engine có chính sách đó.

Vì vậy, giao dịch snapshot thường nên **ngắn và có phạm vi rõ ràng**.

## 6. Read-your-writes: nhìn được write của chính transaction

Giả sử:

```text
Transaction T1:
    READ status -> PENDING
    UPDATE status=APPROVED
    READ status -> APPROVED
    COMMIT
```

Theo ngữ nghĩa giao dịch phổ biến, T1 nhìn thấy **thay đổi chưa commit do chính T1 tạo ra**, trong khi transaction khác không được tự động đọc thay đổi đó.

Một mô hình tư duy:

```text
Góc nhìn đọc của T1
  = dữ liệu snapshot hợp lệ
  + những write do chính T1 tạo
  - những record do chính T1 xóa
```

Điều này không có nghĩa **mọi replica đều nhìn thấy ngay** sau khi T1 commit. Read-your-writes trong một transaction và read-after-write giữa các request là **hai bảo đảm khác nhau**.

## 7. Snapshot isolation bảo vệ gì, và không bảo vệ gì?

Một mô hình SI điển hình có các đặc điểm:

1. Transaction đọc từ **một snapshot nhất quán**.
2. Không đọc những thay đổi chưa commit của transaction khác.
3. Transaction nhìn thấy những write của chính nó.
4. Một số write-write conflict trên cùng đối tượng sẽ bị từ chối hoặc dẫn tới abort.
5. **Không tự phát hiện mọi xung đột dựa trên tập document đã đọc**, nên có thể gặp write skew.

### 7.1. Non-repeatable read và phantom trong cùng snapshot

Nếu T1 đọc cùng query trước/sau khi T2 commit, T1 thường tiếp tục đọc góc nhìn snapshot cũ. Những document T2 mới chèn không tự xuất hiện trong snapshot T1.

Tuy nhiên, nếu **chính T1** thêm/sửa document làm thay đổi tập kết quả, quy tắc read-your-writes vẫn áp dụng. “Snapshot luôn trả y hệt dữ liệu ở mọi lần đọc” là diễn đạt quá đơn giản.

### 7.2. Snapshot cũ không có nghĩa được ghi đè vô điều kiện

T1 có thể vẫn đọc `status=PENDING` dù T2 đã commit `status=PAID`. Nhưng nếu T1 cố cập nhật **chính document đó**, engine có thể báo **write conflict** và yêu cầu abort/retry.

Khả năng **đọc version cũ** khác với quyền **ghi đè version mới**.

### 7.3. Không thấy phantom nhưng vẫn có thể sai quota

Quy tắc: nhiều nhất 10 đơn PENDING.

```text
Ban đầu có 9 đơn PENDING.
T1 snapshot thấy 9 -> thêm order-X.
T2 snapshot thấy 9 -> thêm order-Y.
T1 commit.
T2 commit, nếu không có xung đột/guard.

Kết quả: 11 đơn PENDING.
```

Mỗi transaction có thể không thấy phantom khi đọc lại snapshot của mình, nhưng bất biến tổng số vẫn bị vi phạm.

## 8. Bảo vệ write skew và bất biến nhiều document

### 8.1. Gom bất biến vào một document

Nếu phạm vi dữ liệu phù hợp:

```json
{
  "_id": "shift-night-01",
  "onCallDoctors": ["doctor-A", "doctor-B"],
  "version": 4
}
```

Mọi thao tác cho bác sĩ nghỉ sửa **cùng document**, kèm điều kiện không để danh sách rỗng. Có thể dùng atomic conditional update hoặc version check.

Ưu điểm: bất biến nằm trong một atomic boundary. Nhược điểm: document có thể thành hot key; có giới hạn kích thước và mức cạnh tranh cần cân nhắc.

### 8.2. Dùng một guard document chung

Giữ thông tin từng doctor ở document riêng, nhưng mọi transaction đổi trạng thái on-call phải ghi một document chung:

```json
{
  "_id": "shift-guard-night-01",
  "revision": 12
}
```

Nếu cả T1 và T2 cùng đọc revision 12 và **cùng phải ghi guard**, cơ chế write-write conflict/conditional update có thể buộc một transaction thất bại rồi retry với snapshot mới.

**Chỉ đọc guard là chưa đủ.** Guard cần được dùng theo giao thức buộc các quyết định cạnh tranh phải xung đột hoặc xác minh lại.

### 8.3. Sử dụng serializable trong phạm vi được hỗ trợ

Nếu engine bảo đảm serializable transaction trên tập dữ liệu liên quan, nó có thể phát hiện lịch không hợp lệ và buộc retry. Nhưng không phải mọi NoSQL đều cung cấp mức đó cho mọi loại operation/shard.

### 8.4. Điều phối nghiệp vụ

Có thể dùng một scheduler độc quyền cho một ca trực, cơ chế lease/token/reservation hoặc state machine sở hữu quyết định. Khi đó database vẫn cần điều kiện ghi an toàn và recovery khi worker mất quyền hoặc crash.

## 9. Lost update: thao tác nguyên tử và conditional write

### 9.1. Cách dễ sai

```javascript
const product = db.products.findOne({ _id: "p1" });
const nextStock = product.stock - 1;

db.products.updateOne(
  { _id: "p1" },
  { $set: { stock: nextStock } }
);
```

Hai client đọc `stock=10` rồi đều ghi 9, khiến một lần giảm bị mất.

### 9.2. Atomic conditional update trong MongoDB

```javascript
const result = db.products.updateOne(
  {
    _id: "p1",
    stock: { $gte: 1 }
  },
  {
    $inc: { stock: -1 }
  }
);
```

MongoDB cập nhật một document một cách nguyên tử. Bộ lọc `stock >= 1` giúp bảo vệ điều kiện tồn kho cục bộ.

**Lưu ý:** nếu client timeout sau khi `$inc` đã áp dụng rồi retry cùng request, có thể giảm **hai lần**. Concurrency safety của atomic update khác **idempotency khi retry**.

### 9.3. Optimistic concurrency bằng version

```javascript
const result = db.products.updateOne(
  { _id: "p1", version: 7 },
  {
    $set: { price: 150000 },
    $inc: { version: 1 }
  }
);
```

Nếu một writer khác đã tăng version trước đó, filter không khớp. Ứng dụng phải tải lại, kiểm tra conflict hoặc merge theo hợp đồng; không mặc nhiên coi `matchedCount=0` là đã hoàn tất tác vụ.

## 10. MongoDB: transaction và readConcern snapshot

MongoDB hỗ trợ transaction nhiều document trong **replica set và sharded cluster** với điều kiện deployment/phiên bản phù hợp. Ví dụ dưới đây **không dành cho một mongod standalone mặc định** không hỗ trợ multi-document transaction.

Một session:

```javascript
const conn = db.getMongo();

const sessionA = conn.startSession({
  causalConsistency: false
});

sessionA.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});
```

Ý nghĩa:

- **Session:** ngữ cảnh quản lý transaction.
- **Transaction:** nhóm thao tác trong phạm vi commit/abort.
- **Read concern `snapshot`:** yêu cầu đọc từ một snapshot nhất quán trong phạm vi được MongoDB hỗ trợ.
- **Write concern `majority`:** mức xác nhận commit được yêu cầu; có vai trò với durability và những bảo đảm liên quan snapshot.
- **Read preference:** vị trí node đọc theo yêu cầu của deployment; transaction ghi tuân thủ hạn chế của MongoDB.

### 10.1. Phân biệt `local`, `majority` và `snapshot`

| MongoDB read concern | Diễn giải gần đúng | Không tự suy ra |
| --- | --- | --- |
| `local` | Đọc trạng thái cục bộ trên node | Mọi dữ liệu đã majority-committed |
| `majority` | Đọc theo bảo đảm majority commit được hỗ trợ | Nhiều statement ngoài transaction có cùng snapshot |
| `snapshot` | Dùng góc nhìn snapshot nhất quán theo API/phạm vi hỗ trợ | Serializable isolation cho mọi bất biến |

Các bảo đảm phụ thuộc cấu hình, write concern, session và topology. **Không xem readConcern `majority` là tên khác của snapshot transaction**.

## 11. Thực hành MongoDB: một giao dịch nhìn trạng thái cũ

Dùng `mongosh` và database thử nghiệm `nosql_isolation_lab`.

> **Cảnh báo:** phần seed xóa collection `orders` trong database thực hành. Không chạy trên dữ liệu sản xuất. Môi trường phải hỗ trợ transaction.

### 11.1. Tạo dữ liệu

```javascript
const lab = db.getSiblingDB("nosql_isolation_lab");

lab.orders.drop();

lab.orders.insertOne({
  _id: "order-01",
  tenantId: "tenant-a",
  status: "PENDING",
  total: 100000,
  version: 1
});
```

### 11.2. Session A đọc với snapshot

```javascript
const conn = db.getMongo();
const sessionA = conn.startSession({ causalConsistency: false });

sessionA.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

const dbA = sessionA.getDatabase("nosql_isolation_lab");

const first = dbA.orders.findOne({ _id: "order-01" });

print("A first:", first.status);
// Kết quả mong đợi: PENDING
```

Lần đọc đầu tiên đặt A trong một góc nhìn snapshot phù hợp với thử nghiệm.

### 11.3. Session B cập nhật và commit độc lập

```javascript
const sessionB = conn.startSession({ causalConsistency: false });
const dbB = sessionB.getDatabase("nosql_isolation_lab");

const updateB = dbB.orders.updateOne(
  {
    _id: "order-01",
    status: "PENDING"
  },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  },
  {
    writeConcern: { w: "majority" }
  }
);

print("B modified:", updateB.modifiedCount);

print(
  "B current:",
  dbB.orders.findOne({ _id: "order-01" }).status
);
// Kết quả mong đợi: PAID
```

### 11.4. A đọc lại trong snapshot của mình

```javascript
const second = dbA.orders.findOne({ _id: "order-01" });

print("A second:", second.status);
// Kết quả mong đợi: PENDING

sessionA.commitTransaction();

sessionA.endSession();
sessionB.endSession();

print(
  "New read:",
  lab.orders.findOne({ _id: "order-01" }).status
);
// Kết quả mong đợi: PAID
```

**Điều quan sát:** B đã commit một giá trị mới, nhưng transaction A vẫn đọc version cũ thuộc snapshot của A. Sau khi A kết thúc, một lần đọc mới có thể thấy PAID.

Ví dụ này kiểm tra **snapshot visibility**, không phải benchmark hay test độ bền khi mất điện.

## 12. Thực hành MongoDB: read-your-writes

Đưa document về trạng thái nền:

```javascript
lab.orders.updateOne(
  { _id: "order-01" },
  {
    $set: { status: "PENDING", version: 1 }
  }
);
```

Mở session C:

```javascript
const sessionC = conn.startSession({ causalConsistency: false });

sessionC.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

const dbC = sessionC.getDatabase("nosql_isolation_lab");

print(
  "Before:",
  dbC.orders.findOne({ _id: "order-01" }).status
);

dbC.orders.updateOne(
  { _id: "order-01", status: "PENDING" },
  {
    $set: { status: "APPROVED" },
    $inc: { version: 1 }
  }
);

print(
  "After own write:",
  dbC.orders.findOne({ _id: "order-01" }).status
);
// Kết quả mong đợi: APPROVED

sessionC.commitTransaction();
sessionC.endSession();
```

Giá trị APPROVED xuất hiện trong **lần đọc của chính C trước commit**. Điều đó không có nghĩa session khác được đọc thay đổi chưa commit của C.

## 13. Thực hành MongoDB: hai bác sĩ và write skew

### 13.1. Seed dữ liệu

```javascript
lab.doctors.drop();

lab.doctors.insertMany([
  { _id: "doctor-A", shiftId: "night-01", onCall: true },
  { _id: "doctor-B", shiftId: "night-01", onCall: true }
]);
```

Quy tắc: **luôn có ít nhất một doctor với `onCall=true` trong ca night-01**.

### 13.2. Hai transaction cùng đọc trước khi ghi

```javascript
const sa = conn.startSession({ causalConsistency: false });
const sb = conn.startSession({ causalConsistency: false });

sa.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

sb.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

const da = sa.getDatabase("nosql_isolation_lab");
const dbb = sb.getDatabase("nosql_isolation_lab");

const seenA = da.doctors.find({
  shiftId: "night-01",
  onCall: true
}).toArray();

const seenB = dbb.doctors.find({
  shiftId: "night-01",
  onCall: true
}).toArray();

print("A sees:", seenA.length);
print("B sees:", seenB.length);
// Kết quả mong đợi: cả A và B đều thấy 2.
```

### 13.3. Mỗi transaction ghi document khác nhau

```javascript
if (seenA.length >= 2) {
  da.doctors.updateOne(
    { _id: "doctor-A", onCall: true },
    { $set: { onCall: false } }
  );
}

if (seenB.length >= 2) {
  dbb.doctors.updateOne(
    { _id: "doctor-B", onCall: true },
    { $set: { onCall: false } }
  );
}
```

### 13.4. Commit và kiểm tra

```javascript
try {
  sa.commitTransaction();
  sb.commitTransaction();
} catch (error) {
  print("One transaction may abort:", error.message);
  try { sa.abortTransaction(); } catch (_) {}
  try { sb.abortTransaction(); } catch (_) {}
} finally {
  sa.endSession();
  sb.endSession();
}

printjson(
  lab.doctors.find({ shiftId: "night-01" })
    .sort({ _id: 1 })
    .toArray()
);
```

Trong một lịch snapshot isolation **cho phép cả hai transaction commit** vì chúng ghi các document riêng biệt, dữ liệu cuối có thể là:

```json
[
  { "_id": "doctor-A", "shiftId": "night-01", "onCall": false },
  { "_id": "doctor-B", "shiftId": "night-01", "onCall": false }
]
```

Đây là **write skew**: mỗi transaction có góc nhìn nhất quán nhưng cả hai cùng vi phạm bất biến tổng thể sau commit.

**Không cam kết mọi lượt chạy trên mọi deployment sẽ ra chính xác kết quả trên.** Engine, xung đột tài nguyên và lịch điều phối có thể khiến một transaction abort. Trong sản phẩm thực, không nên chỉ kiểm tra `seen.length >= 2` trên snapshot rồi sửa những document độc lập mà không có cơ chế bảo vệ bất biến.

## 14. Khi transaction bị write conflict

Một lịch khác:

```text
A đọc order.status=PENDING trong snapshot cũ.
B cập nhật cùng order thành PAID rồi commit.
A vẫn đọc PENDING trong snapshot.
A cố sửa chính order đó.
```

A có thể bị **write conflict**. Vì vậy:

- Snapshot cho phép **đọc lại trạng thái cũ**.
- Snapshot không có nghĩa có thể **ghi đè trạng thái mới tùy ý**.
- Khi abort, phải **đọc lại và tính lại logic** trong transaction mới.

Nếu ứng dụng bắt lỗi rồi bỏ transaction, tiếp tục ghi ngoài transaction bằng dữ liệu snapshot cũ, nó có thể phá đúng bảo đảm mà isolation định mang lại.

## 15. Giao dịch dài và chi phí giữ snapshot

Giả sử A giữ snapshot trong 15 phút, trong khi hàng chục nghìn cập nhật xảy ra. Để A tiếp tục đọc bản cũ, engine MVCC có thể phải giữ nhiều version không còn cần cho những reader mới.

Rủi ro:

- Chiếm bộ nhớ và dung lượng lịch sử.
- Làm chậm quá trình thu hồi phiên bản cũ.
- Tăng xung đột khi giao dịch cũ muốn ghi.
- Tăng thời gian chạy, lock wait hoặc timeout.
- Có thể gặp lỗi khi snapshot vượt giới hạn history window của sản phẩm.

Thiết kế thông thường nên:

```text
Chuẩn bị request ở ngoài transaction
    |
    v
BEGIN
    |
    v
Đọc tập dữ liệu tối thiểu
    |
    v
Kiểm tra ràng buộc
    |
    v
Ghi những thay đổi cần nguyên tử
    |
    v
COMMIT sớm
```

Không giữ transaction để chờ người dùng bấm xác nhận, tải file lớn, gọi API bên ngoài hoặc chờ một tác vụ nền dài nếu không có lý do và cơ chế riêng.

## 16. Transaction retry và unknown commit result

Trong các engine có optimistic concurrency, transaction có thể abort vì write conflict. Driver có thể cung cấp helper retry; mỗi lần retry cần **đọc lại dữ liệu theo snapshot mới**, kiểm tra lại điều kiện và ghi lại nếu hợp lệ.

Một mẫu minh họa ý tưởng dùng MongoDB session:

```javascript
const session = conn.startSession();

try {
  session.withTransaction(
    () => {
      const txDb = session.getDatabase("nosql_isolation_lab");

      const current = txDb.orders.findOne({
        _id: "order-01"
      });

      if (!current || current.status !== "PENDING") {
        throw new Error("Order not eligible");
      }

      txDb.orders.updateOne(
        {
          _id: "order-01",
          status: "PENDING"
        },
        {
          $set: { status: "PAID" }
        }
      );
    },
    {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" }
    }
  );
} finally {
  session.endSession();
}
```

Ví dụ minh họa ranh giới; mã production phải xử lý đầy đủ lỗi giao dịch, commit không rõ kết quả và API của driver/phiên bản.

### 16.1. Không gọi side effect ngoài database trong callback retry

```text
Transaction callback:
  UPDATE order
  CALL payment gateway
  SEND email

Gặp conflict -> callback có thể chạy lại
=> payment/email có thể bị phát sinh hai lần.
```

Transaction MongoDB **không rollback** được một yêu cầu đã gửi sang cổng thanh toán hay email provider.

Một mô hình thường dùng:

1. Transaction ghi dữ liệu nghiệp vụ và **outbox event** cùng ranh giới nguyên tử được hỗ trợ.
2. Sau commit, worker đọc sự kiện và gọi bên ngoài.
3. Mỗi consumer dùng **operationId/idempotency key** để chịu được retry.
4. Trạng thái gửi/đối soát được theo dõi độc lập.

Outbox hỗ trợ tính nhất quán giữa hệ, **không tự biến snapshot isolation thành serializable**.

### 16.2. Lỗi commit không có nghĩa transaction đã abort

Client có thể gửi commit rồi mất phản hồi. Nếu lặp lại nghiệp vụ bằng operation ID mới, có nguy cơ áp dụng lần hai.

Cần phân biệt **unknown commit result** với transaction chắc chắn thất bại, sử dụng khả năng retry commit/đối soát của driver và một business operation ID ổn định.

## 17. Isolation không mở rộng tự động sang cache và search

Một transaction có thể bao gồm hai thao tác trên MongoDB:

```text
MongoDB transaction:
  UPDATE products
  INSERT orders
```

Nhưng các hệ liên quan có thể gồm:

```text
MongoDB committed state
    |
    +--> Redis cache: có thể còn dữ liệu cũ
    +--> Search index: cập nhật bất đồng bộ
    +--> Event broker: event có thể đang chờ
    +--> Analytics: xử lý theo batch
```

MongoDB transaction không mặc nhiên làm cho Redis, search và message broker cùng commit hoặc cùng nhìn snapshot.

Nếu sản phẩm bị thu hồi quyền truy cập, một cache cũ vẫn trả nội dung là rủi ro nghiêm trọng. Cần outbox, CDC, invalidation/suppression, kiểm tra quyền tại đường đọc hoặc cơ chế khác đáp ứng yêu cầu.

**Transaction isolation ở một database** và **eventual consistency giữa các read model** là hai trục cần thiết kế riêng.

## 18. Replica consistency khác snapshot isolation

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Read-your-writes trong transaction** | Giao dịch nhìn thấy write của chính mình |
| **Read-after-write giữa request** | Một client đọc sau write có nhìn thấy write đó không? |
| **Causal consistency** | Giữ quan hệ nhân quả của thao tác trong phạm vi hỗ trợ |
| **Monotonic reads** | Client không nhìn thấy dữ liệu đi lùi theo model đã chọn |
| **Snapshot isolation** | Các read của transaction nhìn một snapshot nhất quán |
| **Durability** | Dữ liệu commit còn sau sự cố trong fault model |
| **Replica consistency level** | Những replica nào xác nhận/đọc theo giao thức của hệ |

Client ghi trên primary rồi đọc secondary bị lag có thể thấy dữ liệu cũ, ngay cả khi transaction ghi ban đầu đã commit.

Một giải pháp read-after-write có thể phải chọn read preference/session/causal consistency/read concern phù hợp. **Tăng isolation bên trong transaction không tự làm mọi replica cập nhật tức thì.**

## 19. Hệ NoSQL khác có transaction semantics khác

### 19.1. MongoDB

- Việc sửa **một document** có tính nguyên tử.
- Multi-document transaction được hỗ trợ trong deployment phù hợp.
- Có `readConcern: "snapshot"` và cơ chế phát hiện xung đột.
- Không nên suy transaction snapshot mặc nhiên tương đương serializable.

### 19.2. DynamoDB

- Conditional writes giúp bảo vệ version và trạng thái của một item.
- Có `TransactWriteItems` và `TransactGetItems` với phạm vi/giới hạn transaction riêng.
- `BatchWriteItem` **không phải transaction toàn batch**.
- Cần xem bảo đảm isolation giữa transactional APIs và thao tác đơn lẻ.

### 19.3. Redis

- `WATCH` và `MULTI/EXEC` hỗ trợ optimistic concurrency trong một số nghiệp vụ.
- Không phải một mô hình snapshot MVCC dài nhiều câu lệnh giống MongoDB.
- `EXEC` có semantics riêng và không cung cấp rollback tùy ý các command đã thực thi nếu một command gặp runtime error.

Ví dụ ý tưởng với Redis:

```redis
WATCH inventory:item-1
GET inventory:item-1
MULTI
DECR inventory:item-1
EXEC
```

Ứng dụng còn phải kiểm tra điều kiện tồn kho và xử lý trường hợp `EXEC` bị từ chối vì key thay đổi. Không nên coi đoạn lệnh này đã là một giải pháp hoàn chỉnh chống tồn kho âm.

### 19.4. Cassandra

- Có consistency levels, timestamp và mô hình transaction khác database document.
- **Lightweight transactions (LWT)** hỗ trợ conditional operation trong phạm vi được sản phẩm định nghĩa.
- CQL `BEGIN BATCH` **không tự tạo serializable multi-partition transaction** giống giao dịch SQL.
- Không áp bảo đảm của LWT cho mọi thao tác CQL thông thường.

### 19.5. Các graph/document store khác

Mỗi hệ có thể giới hạn transaction theo một document, partition, shard hoặc cluster. Cần xác định:

- Read timestamp được lấy khi nào?
- Có đọc uncommitted data không?
- Có read-your-writes không?
- Việc update cùng document phát hiện conflict thế nào?
- Predicate/range constraint có được bảo vệ không?
- Có serializable trong phạm vi đó không?

Không chỉ nhìn thấy từ **transaction** để suy ra tất cả bảo đảm.

## 20. Lựa chọn theo yêu cầu nghiệp vụ

| Bài toán | Rủi ro | Cách tiếp cận đáng cân nhắc |
| --- | --- | --- |
| Danh sách công khai | Dữ liệu mới có thể đến trễ | Read concern/replica phù hợp SLO |
| Báo cáo nhiều document | Read skew | Snapshot nhất quán |
| Giảm số lượng tồn kho một SKU | Lost update, số âm | Atomic conditional update |
| Đơn hàng cùng ledger | Chỉ commit một phần | Transaction đúng phạm vi |
| Ít nhất một bác sĩ trực | Write skew | Guard chung, mô hình một document hoặc serializable |
| Không quá 10 đơn đang chờ | Predicate constraint | Quota document, conditional counter hoặc serializable |
| Ghi xong đọc secondary | Replica lag | Read-after-write/causal routing phù hợp |
| Cache/search sau cập nhật | Stale projection | Outbox/invalidation và lag monitoring |
| Workflow dài nhiều phút | Transaction dài, timeout | Reservation/saga/idempotency |
| Thanh toán | Retry trùng, audit, durability | Operation ID, ledger, transaction và kiểm chứng |

Không nhất thiết chọn isolation mạnh nhất cho mọi request. Isolation mạnh hơn có thể tăng xung đột, abort, retry và latency. Cần tìm **mức phù hợp với bất biến** và tổ chức dữ liệu sao cho ranh giới atomic nhỏ, dễ kiểm chứng.

## 21. Thiết kế thí nghiệm đồng thời

Một unit test chạy T1 rồi T2 tuần tự sẽ không phát hiện nhiều anomaly. Cần có lịch thực thi được điều phối.

| Test | Lịch mô phỏng | Kết quả cần quan sát |
| --- | --- | --- |
| I1 | A đọc, B commit, A đọc lại | Non-repeatable read |
| I2 | A truy vấn range, B insert, A truy vấn lại | Phantom |
| I3 | Hai writer sửa cùng document | Lost update/write conflict |
| I4 | Hai writer sửa khác document dựa trên cùng constraint | Write skew |
| I5 | A update rồi tự đọc trong transaction | Read-your-writes |
| I6 | B đọc khi A chưa commit | Dirty read |
| I7 | A commit, client đọc secondary | Read-after-write |
| I8 | A giữ snapshot lâu trong khi nhiều writer cập nhật | Snapshot age/resource |
| I9 | Mất response lúc commit | Unknown result |
| I10 | Transaction callback retry, có external call | Side effect trùng |

### 21.1. Barrier trong test write skew

```text
T1: BEGIN -> READ doctors ------ BARRIER -> WRITE A -> COMMIT
T2: BEGIN -> READ doctors ------ BARRIER -> WRITE B -> COMMIT
```

Hai transaction phải đọc snapshot cũ trước khi bắt đầu ghi để có thể quan sát lịch quan trọng.

Nếu T1 chạy trọn rồi T2 mới đọc, T2 sẽ nhìn trạng thái đã thay đổi và có thể không vi phạm quy tắc. Không nên lấy một test tuần tự thành công làm bằng chứng chống write skew.

### 21.2. Kiểm tra bất biến cuối cùng

Ngoài số transaction commit/abort, cần kiểm tra:

- Số bác sĩ trực còn ít nhất một không?
- Tồn kho có âm không?
- Quota số đơn có bị vượt không?
- Có một logical payment bị áp dụng hai lần không?
- Retry có đọc snapshot mới và quyết định lại không?
- Search/cache có phục vụ dữ liệu trái quyền sau commit không?

Một giao dịch bị abort do xung đột ngoài ý muốn **không chứng minh toàn bộ isolation level là serializable**. Cần dựa trên bảo đảm được công bố và test nhiều lịch.

## 22. Quan sát isolation trong vận hành

| Chỉ số | Mục đích |
| --- | --- |
| Transaction latency p50/p95/p99 | Độ trễ giao dịch |
| Commit/abort counts | Số giao dịch hoàn tất/hủy |
| Write conflict rate | Tranh chấp trên hot key/guard |
| Retry attempts | Nguy cơ retry storm |
| Snapshot age | Giao dịch giữ lịch sử cũ quá lâu |
| History/cache pressure | Chi phí MVCC |
| Lock wait/timeout | Điểm nghẽn concurrency |
| Replica/read lag | Ảnh hưởng tới read-after-write |
| Unknown commit outcomes | Khả năng đối soát |
| Invariant violations | Mức sai lệch nghiệp vụ thực tế |

Một số abort là **cơ chế bảo vệ dữ liệu**, không phải lỗi cần triệt tiêu bằng cách tắt kiểm tra. Nhưng abort cao hoặc retry vô hạn có thể là dấu hiệu ranh giới giao dịch quá rộng, hot key hoặc mô hình concurrency không phù hợp.

## 23. Các hiểu lầm thường gặp

### 23.1. “Có transaction thì mặc nhiên serializable”

Không. Transaction có thể hỗ trợ một isolation level yếu hơn.

### 23.2. “Snapshot luôn phản ánh dữ liệu mới nhất”

Không. Snapshot là một góc nhìn nhất quán, có thể cũ.

### 23.3. “Trong transaction không đọc được write chưa commit của chính mình”

Không đúng với ngữ nghĩa giao dịch phổ biến. Transaction thường đọc thấy **own writes**.

### 23.4. “Không có phantom nghĩa là không có write skew”

Sai. Snapshot có thể không thấy phantom nhưng vẫn vi phạm bất biến đa document.

### 23.5. “Write conflict là lỗi có thể bỏ qua rồi ghi lại ngoài transaction”

Sai. Nó có thể là cơ chế ngăn ghi dựa trên snapshot cũ. Cần retry đúng ranh giới.

### 23.6. “Read concern majority là một snapshot cố định cho mọi request”

Không mặc nhiên. Mức dữ liệu được đọc và góc nhìn ổn định của nhiều statement là hai điều khác nhau.

### 23.7. “MongoDB transaction có thể rollback email và thanh toán ngoài hệ”

Sai. Cần outbox và idempotency cho external side effects.

### 23.8. “Transaction càng dài càng tốt”

Không. Long-running transaction có thể làm tăng chi phí MVCC, xung đột và timeout.

### 23.9. “Serializable, linearizable và strict serializable là một”

Không. Chúng có những yêu cầu khác nhau về lịch giao dịch và thứ tự thời gian thực.

### 23.10. “Mọi NoSQL triển khai isolation giống nhau”

Không. Phạm vi key, document, partition, shard và semantics API thay đổi theo sản phẩm.

## 24. Bài tập thực hành

### Bài 1: đọc giá trị cũ

A đọc `price=100`, B commit `price=200`, A đọc lại vẫn 100. Kết quả này có thể đúng không?

**Gợi ý:** Có, khi A giữ snapshot trước commit của B.

### Bài 2: non-repeatable read

A đọc `price=100`, B commit `price=200`, A đọc lại thành 200 trong cùng giao dịch. Hiện tượng gì?

**Gợi ý:** Non-repeatable read.

### Bài 3: phantom

A đếm 3 đơn PENDING, B thêm một đơn PENDING rồi commit, A đếm lại thành 4. Đây là gì?

**Gợi ý:** Phantom read.

### Bài 4: lost update

Hai client cùng đọc stock=10 rồi đều ghi stock=9, dù thực tế cần giảm hai lần. Sửa thế nào?

**Gợi ý:** Atomic `$inc` với điều kiện tồn kho hoặc optimistic locking theo version.

### Bài 5: read-your-writes

A sửa status thành APPROVED trong transaction, chưa commit rồi đọc lại. A có thể thấy APPROVED không?

**Gợi ý:** Có, theo ngữ nghĩa read-your-writes trong transaction.

### Bài 6: write skew

Hai bác sĩ cùng trực, hai transaction mỗi bên cho một người nghỉ dựa trên snapshot ban đầu. Tại sao có thể vi phạm bất biến?

**Gợi ý:** Hai giao dịch cập nhật hai document khác nhau, nên không có write-write conflict trực tiếp.

### Bài 7: guard chung

Nếu mọi transaction phải cập nhật `shift-guard-night-01`, điều đó giúp gì?

**Gợi ý:** Biến quyết định cạnh tranh thành xung đột trên cùng một write target hoặc version, buộc retry và kiểm tra lại.

### Bài 8: majority và snapshot

Hai lệnh đọc độc lập đều dùng read concern majority. Có thể mặc định chúng thuộc cùng snapshot không?

**Gợi ý:** Không. Phải có cơ chế snapshot/transaction cụ thể.

### Bài 9: replica lag

Client ghi primary, đọc secondary lại thấy trạng thái cũ. Chỉ thay isolation của transaction ghi đã đủ chưa?

**Gợi ý:** Chưa. Cần xem read preference, read-after-write/causal consistency và replication lag.

### Bài 10: retry callback

Callback transaction gọi cổng thanh toán rồi bị retry. Rủi ro chính?

**Gợi ý:** Thanh toán bị gọi hai lần. Cần operation ID và cơ chế idempotency/outbox.

### Bài 11: serializable và real time

Một lịch tương đương thứ tự tuần tự nhưng không tôn trọng thứ tự thời gian thực có tự là strict serializable không?

**Gợi ý:** Không. Strict serializability bổ sung yêu cầu thời gian thực.

### Bài 12: MongoDB standalone

Vì sao phần thực hành multi-document transaction có thể lỗi nếu dùng một mongod standalone mặc định?

**Gợi ý:** Cần deployment hỗ trợ transaction, như replica set hoặc sharded cluster phù hợp.

### Bài 13: snapshot dài

Một giao dịch giữ snapshot 20 phút trong lúc nhiều writer cập nhật. Rủi ro?

**Gợi ý:** History retention, snapshot stale, write conflict, timeout và sử dụng tài nguyên lớn.

### Bài 14: test write skew

Vì sao chạy T1 trọn vẹn rồi T2 mới bắt đầu không tái hiện write skew?

**Gợi ý:** T2 sẽ thấy trạng thái sau T1. Cần barrier để cả hai cùng đọc snapshot ban đầu trước khi ghi.

## 25. Checklist áp dụng isolation cho một mô hình NoSQL

Trước khi chọn transaction, hãy lần lượt trả lời:

1. **Bất biến nghiệp vụ** nằm trên một document, nhiều document hay nhiều hệ?
2. Engine hỗ trợ atomicity tới phạm vi nào?
3. Isolation level là gì; có snapshot hay serializable không?
4. Snapshot/read timestamp được xác lập lúc nào?
5. Transaction có read-your-writes không?
6. Dirty read, non-repeatable read, phantom, lost update và write skew có thể xảy ra không?
7. Conflict được phát hiện trên write target hay cả predicate đã đọc?
8. Có thể dùng một atomic conditional update thay transaction lớn không?
9. Có cần guard chung, version hoặc một giao thức reservation không?
10. Khi abort, ứng dụng có tính lại quyết định bằng snapshot mới không?
11. Khi commit result chưa rõ, có operation ID để đối soát không?
12. Có cache, search, replica hoặc API ngoài nằm **ngoài** transaction không?
13. Read concern, write concern và durability có đáp ứng yêu cầu không?
14. Transaction có bị giữ lâu và gây history pressure/retry storm không?
15. Có test concurrency đúng lịch và kiểm tra bất biến cuối không?

**Kết luận:** Isolation quy định dữ liệu nào một giao dịch được phép nhìn thấy và những lịch đọc/ghi đồng thời nào được chấp nhận. **Snapshot** giúp các lần đọc có một góc nhìn nhất quán, nhưng góc nhìn đó có thể cũ; **MVCC** là một cơ chế phổ biến để hiện thực nhiều phiên bản; **read-your-writes** cho phép giao dịch đọc thay đổi của chính mình. Quan trọng hơn, **snapshot isolation không tự động ngăn write skew hay bảo vệ mọi bất biến đa document**. Thiết kế đúng cần kết hợp mức isolation, conditional write, guard/serializable khi cần, transaction retry an toàn và sự phân biệt rõ ràng giữa **isolation, replica consistency và durability**.
