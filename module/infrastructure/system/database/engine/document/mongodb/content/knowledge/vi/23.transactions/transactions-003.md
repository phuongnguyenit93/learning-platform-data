# Session, bắt đầu giao dịch, commit và abort trong MongoDB

## Mục tiêu bài học

Trong MongoDB, một thao tác ghi lên **một document** đã có tính nguyên tử ở phạm vi document đó. Tuy nhiên, ứng dụng thực tế có những nghiệp vụ yêu cầu **nhiều thao tác** hoặc **nhiều document** cùng thành công hay cùng không được áp dụng. Ví dụ: chuyển 200.000 đồng từ tài khoản A sang tài khoản B; giảm hàng tồn kho và tạo đơn hàng; cập nhật số dư và ghi sổ giao dịch.

MongoDB hỗ trợ **multi-document transactions** trên những triển khai đáp ứng yêu cầu, để nhiều thao tác đọc/ghi có thể được thực hiện trong một giao dịch. Để dùng giao dịch đúng, trước tiên phải hiểu **session** — ngữ cảnh liên kết các thao tác với nhau. Sau đó cần quản lý vòng đời:

~~~text
Tạo session
    |
    v
startTransaction()
    |
    v
Đọc / ghi trong session
    |
    +--- mọi điều kiện nghiệp vụ hợp lệ ---> commitTransaction()
    |
    +--- lỗi hoặc chủ động hủy -----------> abortTransaction()
    |
    v
Đóng session / giải phóng tài nguyên
~~~

Bài học thuộc chủ đề **Database Engine Document MongoDB**, chương **Giao dịch**, tập trung vào **Session, bắt đầu giao dịch, commit và abort**. Sau bài học, người học có thể:

1. Phân biệt **logical session** với **transaction** và hiểu vì sao chúng không đồng nghĩa.
2. Tạo, sử dụng và đóng `ClientSession` đúng cách.
3. Dùng `startTransaction()`, thực hiện thao tác trong transaction, gọi `commitTransaction()` hoặc `abortTransaction()`.
4. Giải thích tính nguyên tử, tính nhất quán ở phạm vi giao dịch, dữ liệu chưa commit và read-your-own-writes.
5. Chọn `readConcern`, `writeConcern` và `readPreference` phù hợp với giao dịch.
6. Nêu yêu cầu triển khai trên replica set/sharded cluster và giới hạn của MongoDB standalone.
7. Xây một transaction thực hành chuyển tiền, có kiểm tra điều kiện và ghi lịch sử.
8. Phân biệt **lỗi trước commit**, **lỗi tạm thời cần chạy lại transaction** và **kết quả commit không xác định**.
9. Sử dụng callback transaction API của official driver khi phù hợp và hiểu các rủi ro khi tự retry.
10. Tránh giao dịch kéo dài, thao tác song song trên cùng session, external side effects và các operation không hỗ trợ trong transaction.
11. Thiết kế test commit/abort, tính idempotent và quan sát giao dịch trên production.

> **Nguyên tắc:** Session xác định **ngữ cảnh thao tác**; transaction xác định **ranh giới nguyên tử**. `commit` yêu cầu chấp nhận kết quả, còn `abort` hủy những thay đổi **chưa commit** của transaction. Một lỗi mạng ngay lúc commit **không chứng minh** transaction chưa được commit.

---

## 1. Vì sao cần giao dịch nhiều document?

Giả sử có hai tài khoản:

~~~javascript
{
  _id: "ACC-A",
  owner: "An",
  balance: NumberLong("1000000")
}

{
  _id: "ACC-B",
  owner: "Bình",
  balance: NumberLong("300000")
}
~~~

Ứng dụng muốn chuyển 200.000 đồng từ A sang B.

Nếu xử lý bằng hai lệnh update độc lập:

~~~javascript
db.accounts.updateOne(
  { _id: "ACC-A" },
  {
    $inc: {
      balance: NumberLong("-200000")
    }
  }
);

db.accounts.updateOne(
  { _id: "ACC-B" },
  {
    $inc: {
      balance: NumberLong("200000")
    }
  }
);
~~~

thì có một khoảng thời gian hoặc trường hợp lỗi:

- Trừ tiền ở A đã thành công.
- Mạng hoặc ứng dụng lỗi trước khi cộng tiền cho B.
- Hệ thống lưu trạng thái thiếu một nửa nghiệp vụ.

Một thao tác update trên A là atomic **trên document A**; thao tác update trên B là atomic **trên document B**. Hai thao tác riêng biệt **không tự tạo một giao dịch chung**.

### 1.1. Mục tiêu của multi-document transaction

Nghiệp vụ chuyển tiền yêu cầu:

~~~text
Nếu thành công:
  A: 1.000.000 ->   800.000
  B:   300.000 ->   500.000
  Lịch sử chuyển tiền: được ghi cùng giao dịch

Nếu thất bại:
  A: vẫn 1.000.000
  B: vẫn   300.000
  Không có lịch sử chuyển tiền đã hoàn tất
~~~

Transaction cho phép các thao tác ghi ở nhiều document và collection trở thành một đơn vị **all-or-nothing**, theo các ràng buộc được MongoDB hỗ trợ.

### 1.2. Không phải mọi bài toán đều cần transaction

Nếu chỉ thay đổi một document:

~~~javascript
db.accounts.updateOne(
  {
    _id: "ACC-A",
    balance: { $gte: NumberLong("200000") }
  },
  {
    $inc: {
      balance: NumberLong("-200000")
    }
  }
);
~~~

MongoDB đã bảo đảm atomicity của thao tác update trong phạm vi một document. Dùng multi-document transaction cho một điều kiện đơn-document đơn giản có thể không đem lại lợi ích tương xứng.

**Ưu tiên thiết kế document phù hợp** trước khi thêm transaction. Giao dịch nhiều document có chi phí resource, lock/concurrency và thao tác vận hành; nó không thay thế schema design tốt.

---

## 2. Session là gì?

**Session** là ngữ cảnh logic giúp MongoDB và driver liên hệ những thao tác do cùng client thực hiện. Logical session có thể hỗ trợ những tính năng như causal consistency, retryable writes và multi-document transactions theo cấu hình/khả năng tương ứng.

Một session thường có định danh logic (thường được nhắc tới là **`lsid`**) và được quản lý bởi driver/server. Client có thể thực hiện thao tác **trong session** mà chưa bắt đầu một transaction.

### 2.1. Ba đối tượng khác nhau

| Khái niệm | Bản chất | Có tự tạo transaction? |
|---|---|---|
| `MongoClient` | Đối tượng client quản lý kết nối, discovery, pooling | Không |
| `ClientSession` | Ngữ cảnh logic cho thao tác | Không |
| Transaction | Nhóm thao tác có ranh giới begin/commit/abort | Có, khi start transaction trong session |

Trong Java:

~~~java
MongoClient client = MongoClients.create(uri);
ClientSession session = client.startSession();
session.startTransaction();
~~~

Mỗi dòng có trách nhiệm khác nhau:

1. Tạo client.
2. Tạo session gắn với client.
3. Bắt đầu transaction trong session.

### 2.2. Session không có nghĩa mọi thao tác tự tham gia

Nếu một ứng dụng có:

~~~javascript
const session = db.getMongo().startSession();
const sessionDb = session.getDatabase("training_bank");

session.startTransaction();

sessionDb.accounts.updateOne(
  { _id: "ACC-A" },
  { $inc: { balance: -100 } }
);
~~~

thì thao tác trên `sessionDb` thuộc ngữ cảnh session. Nhưng một thao tác viết bằng handle thông thường:

~~~javascript
db.getSiblingDB("training_bank")
  .accounts.updateOne(
    { _id: "ACC-B" },
    { $inc: { balance: 100 } }
  );
~~~

**không tự tham gia** transaction chỉ vì nó được gọi trong cùng file script.

Trong Java cũng tương tự: phải truyền `ClientSession` vào các operations:

~~~java
accounts.updateOne(session, filter, update);
~~~

Không được quên session ở một trong các thao tác mà nghiệp vụ yêu cầu all-or-nothing.

### 2.3. Một session không đồng thời chạy nhiều transaction

Tại một thời điểm, không bắt đầu transaction thứ hai trong cùng session khi transaction trước chưa hoàn tất. Với các driver, **không được chạy các operations trong cùng một transaction song song trên cùng session** nếu API không hỗ trợ.

Ví dụ không nên tạo nhiều tác vụ bất đồng bộ ghi cùng transaction rồi chạy song song bằng `Promise.all`. Các thao tác trong một transaction nên có thứ tự rõ ràng.

### 2.4. Session không phải một transaction vĩnh viễn

Một session có thể trải qua nhiều transaction **tuần tự**:

~~~text
Session S
  |
  +-- Transaction T1: start -> operations -> commit
  |
  +-- Transaction T2: start -> operations -> abort
  |
  +-- Transaction T3: start -> operations -> commit
  |
  +-- endSession()
~~~

Điều đó không có nghĩa cả T1, T2, T3 là một transaction. Mỗi giao dịch có boundary và outcome riêng.

### 2.5. Kết thúc session

Khi không dùng nữa, đóng session để giải phóng tài nguyên logic của client:

~~~javascript
session.endSession();
~~~

Trong Java, dùng `try-with-resources` cho `ClientSession`. Đừng giữ session mở vô thời hạn hoặc chia sẻ session cho nhiều request không liên quan.

---

## 3. Session với causal consistency khác transaction

Một session có thể được dùng cho **causal consistency** mà **không** chạy transaction.

Ví dụ khi ứng dụng yêu cầu một chuỗi thao tác có quan hệ nhân quả, session phù hợp kết hợp read/write concerns có thể giúp bảo đảm như read-your-writes và các quan hệ thứ tự nhân quả trong những điều kiện được tài liệu hỗ trợ.

~~~javascript
const session = db.getMongo().startSession({
  causalConsistency: true
});

try {
  const sdb = session.getDatabase("training_bank");

  // Hai thao tác trong cùng logical session,
  // nhưng KHÔNG có startTransaction.
  sdb.accounts.updateOne(
    { _id: "ACC-A" },
    { $set: { nickname: "An" } }
  );

  const account = sdb.accounts.findOne({
    _id: "ACC-A"
  });

  printjson(account);
} finally {
  session.endSession();
}
~~~

**Không có startTransaction** trong ví dụ này, nên hai thao tác không được gom thành một giao dịch multi-document.

### 3.1. Causal consistency cần điều kiện

Những bảo đảm causal consistency như monotonic reads, read-your-writes, monotonic writes hoặc writes-follow-reads phụ thuộc vào cách sử dụng session, read/write concern (thường được đề cập với `majority`), khả năng deployment và server/driver. Không tuyên bố “chỉ cần startSession là có tất cả ACID”.

### 3.2. Không nhầm logical session với snapshot session

Một số driver/server hỗ trợ **snapshot sessions** cho những reads nhất quán tại một snapshot. Đó không phải cùng khái niệm với multi-document transaction trong một session. Khi thiết kế cần đọc snapshot, kiểm tra API và quy tắc của version đang dùng thay vì tự gọi mọi snapshot read là transaction.

---

## 4. Điều kiện tiên quyết để sử dụng multi-document transaction

### 4.1. Deployment hỗ trợ

MongoDB hỗ trợ multi-document transactions trên:

- **Replica sets** — tính năng xuất hiện từ MongoDB **4.0**.
- **Sharded clusters** — hỗ trợ distributed transactions từ MongoDB **4.2**.

Một **standalone `mongod`** không cung cấp multi-document transaction theo cùng API. Nếu chỉ có một máy để học, vẫn có thể chạy **single-node replica set**, giúp thử giao dịch về mặt chức năng dù không có high availability.

### 4.2. Storage engine và phiên bản

Transactions dựa trên các khả năng của storage engine và deployment phù hợp, thường là WiredTiger trong triển khai MongoDB hiện đại. Cần đảm bảo server version, driver version và topology hỗ trợ transaction API.

Không viết code chỉ dựa trên sự tồn tại của method `startTransaction()` ở client; khi server không hỗ trợ, thao tác sẽ lỗi.

### 4.3. Kết nối qua replica set URI

Trong lab ba members:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rsLearn
~~~

Với single-node replica set:

~~~text
mongodb://localhost:27017/?replicaSet=rsDev
~~~

Tên `rsLearn`, `rsDev` phải đúng với `_id` của replica set đã khởi tạo. Với Atlas hoặc sharded cluster, dùng URI được hệ thống cung cấp.

### 4.4. Những điều kiện thực hành khác

- User có quyền đọc/ghi trên các collections cần thao tác.
- Các collections/indexes cần cho nghiệp vụ được tạo trước trong lab nếu có thể.
- Client sử dụng official driver có hỗ trợ sessions/transactions.
- Có phương án đọc/ghi xác nhận phù hợp.
- Giao dịch ngắn, không chờ tương tác người dùng ở giữa.
- Có chiến lược xử lý lỗi và retry phù hợp.
- Các thao tác ngoài MongoDB (gọi API thanh toán, gửi email, Kafka...) **không tự thuộc transaction này**.

### 4.5. Giao dịch không biến hai hệ thống khác nhau thành atomic

Ví dụ:

~~~text
1. MongoDB: trừ tồn kho.
2. HTTP API: thu tiền qua cổng thanh toán.
3. MongoDB: tạo đơn.
~~~

Một MongoDB transaction **không rollback được HTTP API** đã thu tiền. Với các hệ thống bên ngoài, cần nghiên cứu outbox, idempotency, saga, reconciliation hoặc transaction/compensation pattern khác. Không gọi email hoặc payment gateway bên trong callback sẽ tự chạy lại nhiều lần.

---

## 5. Vòng đời đầy đủ của transaction

Một transaction có các giai đoạn:

~~~text
NO SESSION
    |
    v
START SESSION
    |
    v
SESSION ACTIVE, NO TRANSACTION
    |
    +--> startTransaction()
                |
                v
         TRANSACTION ACTIVE
                |
         +------+------+
         |             |
         v             v
   operations OK    Có lỗi / user hủy
         |             |
         v             v
  commitTransaction  abortTransaction
         |             |
         v             v
  COMMIT REQUESTED   ABORTED
         |
         +--> commit xác nhận: COMMITTED
         |
         +--> kết quả commit không rõ:
              cần xử lý UNKNOWN outcome
                |
                v
     END SESSION SAU KHI HOÀN TẤT LOGIC
~~~

### 5.1. `startTransaction()`

Đây là lời yêu cầu bắt đầu giao dịch **trong session**. Nó thiết lập trạng thái transaction ở client. Các operation tiếp theo được gửi cùng session/transaction metadata; việc khởi tạo giao dịch ở server được gắn với thao tác thực tế theo cơ chế driver.

### 5.2. Thao tác trong transaction

Có thể gồm:

- `find` hoặc những reads được hỗ trợ.
- `insertOne`, `insertMany`.
- `updateOne`, `updateMany`.
- `deleteOne`, `deleteMany`.
- Những aggregation/operations khác **nếu được phép trong transaction**.

Không phải mọi database command hay aggregation stage đều hợp lệ trong transaction; xem phần giới hạn.

### 5.3. `commitTransaction()`

Yêu cầu server **commit** những thay đổi thuộc transaction. Khi commit thành công theo write concern và semantics liên quan, transaction được chấp nhận như một đơn vị.

**Không** suy luận rằng mọi commit request luôn kết thúc chắc chắn sau một network timeout; transaction có thể đã commit trên server nhưng client chưa nhận được kết quả.

### 5.4. `abortTransaction()`

Yêu cầu hủy transaction đang hoạt động, loại các thay đổi chưa commit của nó. Sau khi abort thành công, không thể gọi commit để “làm sống lại” transaction đó. Muốn thực hiện nghiệp vụ lại, phải **bắt đầu transaction mới**.

### 5.5. `endSession()`

Đóng logical session. Không coi việc đóng session là cách thay thế cho việc xử lý rõ ràng một outcome commit không xác định. Đặc biệt trong hệ thống tiền tệ, cần giải quyết/đối soát kết quả trước khi yêu cầu phát sinh giao dịch mới cùng business ID.

---

## 6. Mongosh: tạo session, start, commit một transaction

### 6.1. Chuẩn bị dữ liệu lab

Sử dụng database `training_bank` trên replica set. Trong lab cô lập, tạo dữ liệu ngoài transaction:

~~~javascript
use training_bank

db.accounts.insertMany([
  {
    _id: "ACC-A",
    owner: "An",
    balance: NumberLong("1000000"),
    currency: "VND"
  },
  {
    _id: "ACC-B",
    owner: "Bình",
    balance: NumberLong("300000"),
    currency: "VND"
  }
]);

db.transfers.createIndex(
  { requestId: 1 },
  {
    name: "uk_transfers_requestId",
    unique: true
  }
);
~~~

Lưu ý: khi chạy lại lab, `insertMany` trên cùng `_id` có thể bị duplicate key. Dùng database lab mới hoặc dọn dữ liệu có chủ đích; không dùng lệnh xóa toàn database production.

### 6.2. Script transaction commit thành công

~~~javascript
const session = db.getMongo().startSession();

try {
  const bankDb = session.getDatabase("training_bank");
  const accounts = bankDb.getCollection("accounts");
  const transfers = bankDb.getCollection("transfers");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  const amount = NumberLong("200000");

  const debit = accounts.updateOne(
    {
      _id: "ACC-A",
      balance: { $gte: amount }
    },
    {
      $inc: { balance: NumberLong("-200000") }
    }
  );

  if (debit.matchedCount !== 1) {
    throw new Error("Nguồn không tồn tại hoặc không đủ tiền");
  }

  const credit = accounts.updateOne(
    { _id: "ACC-B" },
    {
      $inc: { balance: amount }
    }
  );

  if (credit.matchedCount !== 1) {
    throw new Error("Không tìm thấy tài khoản nhận");
  }

  transfers.insertOne({
    _id: "TRANSFER-001",
    requestId: "REQ-TRANSFER-001",
    from: "ACC-A",
    to: "ACC-B",
    amount: amount,
    status: "COMPLETED",
    createdAt: new Date()
  });

  session.commitTransaction();

  print("Transaction commit được xác nhận");
} catch (error) {
  // Dành cho trường hợp lỗi khi transaction đang thực hiện.
  // Nếu lỗi nảy sinh TẠI COMMIT, outcome có thể chưa rõ.
  try {
    session.abortTransaction();
  } catch (abortError) {
    print("Abort không thể kết luận transaction chưa commit");
  }

  throw error;
} finally {
  session.endSession();
}
~~~

**Lưu ý đặc biệt của ví dụ:** Mẫu trên tập trung minh họa ba lệnh `startTransaction()`, `commitTransaction()` và `abortTransaction()`. Trong production, **không được dùng việc gọi abort trong catch để suy luận chắc chắn transaction chưa được commit**, nhất là khi lỗi ở `commitTransaction()`. Phải dùng API callback/retry phù hợp và xử lý nhãn lỗi như phần sau.

### 6.3. Kiểm tra sau commit

Ở một phiên mongosh bình thường, kiểm tra:

~~~javascript
db.getSiblingDB("training_bank")
  .accounts.find(
    {},
    { _id: 1, balance: 1, currency: 1 }
  )
  .sort({ _id: 1 });

db.getSiblingDB("training_bank")
  .transfers.find({
    requestId: "REQ-TRANSFER-001"
  });
~~~

Nếu bộ dữ liệu đúng như đã tạo và transaction commit một lần:

| Account | Trước | Sau |
|---|---:|---:|
| ACC-A | 1.000.000 | 800.000 |
| ACC-B | 300.000 | 500.000 |

Có thêm một document transfers tương ứng.

### 6.4. Vì sao filter trừ tiền có điều kiện?

Điều kiện:

~~~javascript
{
  _id: "ACC-A",
  balance: {
    $gte: NumberLong("200000")
  }
}
~~~

giúp ngăn việc trừ tiền khiến số dư âm trong một lần update phù hợp. Nếu không khớp, `matchedCount` là 0 và ứng dụng ném lỗi để abort toàn bộ nghiệp vụ.

Một transaction **không tự thay thế business validation**. Cần kiểm tra tài khoản tồn tại, currency phù hợp, amount dương, số dư, trạng thái tài khoản và các ràng buộc khác.

### 6.5. Vì sao ghi lịch sử cùng transaction?

Nếu chỉ cập nhật hai balances nhưng ghi transfer log bên ngoài transaction, có thể xảy ra:

~~~text
Hai balances được commit
         |
         v
Ứng dụng lỗi trước khi insert transfer record
         |
         v
Không có dấu vết nghiệp vụ tương ứng
~~~

Đặt thao tác ghi transfer record **cùng transaction** giúp all-or-nothing giữa số dư và lịch sử nội bộ MongoDB.

Điều này không thay thế audit trail độc lập hoặc sổ kế toán đầy đủ trong một hệ thống tài chính chuyên nghiệp, nhưng làm rõ nguyên tắc atomic boundaries.

---

## 7. Mongosh: chủ động abort một transaction

Giả sử ứng dụng phát hiện dữ liệu không hợp lệ sau khi thực hiện thao tác tạm thời.

~~~javascript
const session = db.getMongo().startSession();

try {
  const sdb = session.getDatabase("training_bank");
  const accounts = sdb.getCollection("accounts");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  accounts.updateOne(
    { _id: "ACC-A" },
    {
      $inc: {
        balance: NumberLong("-10000")
      }
    }
  );

  // Giả lập quyết định của nghiệp vụ: phải hủy.
  const approved = false;

  if (!approved) {
    session.abortTransaction();
    print("Transaction đã abort theo nghiệp vụ");
  } else {
    session.commitTransaction();
    print("Transaction đã commit");
  }
} finally {
  session.endSession();
}
~~~

### 7.1. Kết quả sau abort

Nếu ban đầu ACC-A là 800.000, sau transaction bị abort, số dư vẫn là **800.000**. Việc chạy `updateOne` bên trong transaction **không** làm thay đổi đã hủy trở thành dữ liệu tồn tại lâu dài.

### 7.2. Abort không phải “undo bất kỳ điều gì”

Nếu một write đã **commit ở transaction trước**, transaction mới không thể dùng `abortTransaction()` để đảo write đó.

Ví dụ:

~~~text
Transaction T1:
  Trừ 100.000
  commit thành công

Transaction T2:
  abort
~~~

Abort T2 không đảo T1. Muốn hoàn tiền hoặc hủy nghiệp vụ đã commit, cần một nghiệp vụ bù trừ (compensation) có kiểm soát, ví dụ tạo transaction hoàn tiền mới, không “gọi abort lại”.

### 7.3. Abort không hủy side effects ngoài MongoDB

Nếu trong lúc transaction đang chạy ứng dụng đã gửi email hoặc thu tiền qua API bên thứ ba, `abortTransaction()` không thể tự thu hồi email/API call đó. Đừng thực hiện external side effects không idempotent giữa start và commit rồi hy vọng rollback được tất cả.

---

## 8. Atomicity: điều gì được bảo đảm và điều gì không?

### 8.1. All-or-nothing đối với transaction operations

Khi một transaction đã được commit thành công:

- Các thay đổi thuộc transaction được chấp nhận như một đơn vị.
- Nếu transaction abort, các write chưa commit của nó không được giữ lại như kết quả đã commit.
- Ứng dụng không nên quan sát một phần những ghi chưa commit theo cách thông thường như dữ liệu đã commit.

Ví dụ:

~~~text
Transaction:
  A.balance -= 200000
  B.balance += 200000
  transfers.insert(...)

Commit thành công:
  Các cập nhật nội bộ cùng được chấp nhận.

Abort:
  Không có thay đổi nào của transaction được commit.
~~~

### 8.2. Đọc bên trong transaction có thể thấy write của chính nó

Trong cùng session/transaction:

~~~javascript
const sdb = session.getDatabase("training_bank");

session.startTransaction();

sdb.accounts.updateOne(
  { _id: "ACC-A" },
  { $set: { flag: "PENDING" } }
);

const withinTransaction = sdb.accounts.findOne({
  _id: "ACC-A"
});

printjson(withinTransaction);
~~~

Giao dịch có thể đọc những thay đổi do chính nó thực hiện. Đây không có nghĩa các client ngoài transaction đã nhìn thấy flag PENDING trước commit.

### 8.3. Transactions không tự tạo serializability tuyệt đối

Giao dịch với read concern snapshot cung cấp snapshot isolation theo những semantics phù hợp, nhưng **không nên tự suy rằng tất cả nghiệp vụ đồng thời đều được thực thi như một hàng đợi tuần tự lý tưởng**.

Ví dụ write skew: hai transactions cùng đọc một ràng buộc phân tán trên nhiều document và sửa **hai document khác nhau**; nếu ràng buộc không được cưỡng chế bằng unique index, conditional write hoặc chiến lược đồng bộ phù hợp, có thể phát sinh kết quả không đúng business invariant.

Cần:

- Thiết kế predicates có điều kiện.
- Unique indexes cho các ràng buộc duy nhất.
- Thao tác trên một document khi có thể.
- Write-conflict handling và retry.
- Tránh suy luận rằng cứ dùng transaction là không thể có race condition.

### 8.4. Snapshot đọc có thể cũ so với thay đổi bên ngoài

Một transaction dài có thể đọc theo snapshot đã xác lập, trong khi transaction khác đã commit dữ liệu mới. Đọc trong transaction không phải cách để nhìn thấy mọi thay đổi mới nhất ngay tức thời.

Đối với một số bài toán cần “lock” hoặc ràng buộc cập nhật chặt, có thể cần thao tác ghi có điều kiện hoặc cơ chế lock pattern để phát hiện xung đột. Transaction giúp atomicity nhưng không thay thế thiết kế concurrency controls.

---

## 9. Read Concern, Write Concern và Read Preference trong transaction

### 9.1. Ba lựa chọn khác nhau

| Thuộc tính | Câu hỏi |
|---|---|
| `readConcern` | Những bản ghi giao dịch được phép đọc theo mức bảo đảm nào? |
| `writeConcern` | Commit cần mức acknowledgment/durability nào? |
| `readPreference` | Giao dịch được hướng đến member nào để đọc? |

### 9.2. TransactionOptions mẫu

~~~javascript
session.startTransaction({
  readConcern: {
    level: "snapshot"
  },
  writeConcern: {
    w: "majority"
  },
  readPreference: "primary"
});
~~~

- `snapshot`: hướng tới consistent snapshot trong transaction theo semantics MongoDB.
- `majority`: write concern xác nhận commit với mức majority được hỗ trợ.
- `primary`: giao dịch đọc/ghi được định tuyến theo yêu cầu transaction.

### 9.3. Write concern trong transaction đặt ở cấp transaction/commit

Khi đang trong transaction, không chỉ định một mức write concern riêng cho từng insert/update trong transaction như thể chúng độc lập.

**Write concern của transaction được áp dụng ở commit.**

Ví dụ ý tưởng:

~~~javascript
session.startTransaction({
  writeConcern: {
    w: "majority"
  }
});

// Các thao tác qua collection thuộc session:
sdb.orders.insertOne({ _id: "O-TX-1" });
sdb.ledger.insertOne({ _id: "L-TX-1" });

// Mức acknowledgment được yêu cầu tại commit:
session.commitTransaction();
~~~

Một lệnh update chạy trong transaction có thể hoàn thành ở client trước commit, nhưng không phải vì thế mà nó đã được công bố như một write độc lập.

### 9.4. `readConcern:"snapshot"` và `writeConcern:"majority"`

Cặp lựa chọn này thường được dùng để yêu cầu một snapshot nhất quán cùng mức durability mạnh hơn khi commit.

Cần hiểu chính xác: các bảo đảm snapshot-majority-committed liên quan đến transaction-level read concern và việc commit transaction với `w:"majority"` theo tài liệu server. Không lấy một option riêng lẻ để bảo đảm tất cả read/write trên cluster luôn latest/linearizable.

### 9.5. `readPreference:"primary"`

Multi-document transactions **chứa ghi** yêu cầu thực thi theo các quy tắc primary. Thực hành an toàn thông dụng là chọn `primary` cho transaction.

Đừng cố chuyển một transaction ghi tới secondary bằng `secondaryPreferred` vì muốn tăng tốc: secondary không nhận ghi thường như primary.

### 9.6. Các read concern khác

MongoDB còn có `local`, `majority` và các mức khác. Mỗi mức bảo đảm/chi phí khác nhau; tính thích hợp với transactions phụ thuộc server version, topology và các điều kiện tài liệu quy định.

Trong chương này, `snapshot` là lựa chọn minh họa rõ cho bài toán nhất quán multi-document. Nhưng không có nghĩa mọi transaction phải luôn chọn snapshot bằng tay; official driver và triển khai có defaults, kế thừa options phù hợp.

---

## 10. Commit không giống “đã gửi lệnh commit”

Đây là một trong những khác biệt quan trọng nhất.

### 10.1. Ba thời điểm

~~~text
T1: Client gửi commitTransaction tới server.
T2: Server commit transaction.
T3: Client nhận acknowledgment commit.
~~~

Nếu kết nối mất giữa T2 và T3, client có thể thấy **network error**, dù transaction đã commit trên server.

Nếu lỗi trước T2, server có thể chưa commit. Chỉ từ lỗi mạng, client **không biết chắc** trường hợp nào xảy ra.

### 10.2. Lỗi tại commit là kết quả không rõ

MongoDB drivers gắn **error labels** trong một số trường hợp, ví dụ:

- `UnknownTransactionCommitResult`: kết quả commit chưa được xác định.
- `TransientTransactionError`: lỗi tạm thời khiến transaction cần được chạy lại từ đầu theo quy tắc phù hợp.

**Không** coi mọi error là “transaction thất bại và dữ liệu chắc chắn không ghi”.

### 10.3. Retry commit khác retry toàn bộ nghiệp vụ

Nếu commit result unknown, hướng giải quyết có thể là **retry `commitTransaction()` trên cùng transaction/session** theo API và error label, không chạy lại ngay các thao tác trừ/cộng tiền như một transaction mới.

Nếu transaction bị lỗi tạm thời trước commit, hướng xử lý thường là **abort transaction cũ rồi chạy lại toàn bộ transaction** trong một transaction mới.

Đây là hai vòng retry **khác nhau**, không được gom làm một.

### 10.4. Bảng quyết định

| Vị trí và trạng thái lỗi | Nguy cơ | Hướng xử lý |
|---|---|---|
| Business validation thất bại trước commit | Nghiệp vụ không hợp lệ | Abort, trả lỗi nghiệp vụ, không retry tự động |
| Lỗi write conflict/transient khi đang thực hiện | Transaction có thể cần làm lại | Retry **toàn bộ transaction** khi có nhãn/điều kiện phù hợp |
| Mất kết nối đúng lúc commit, outcome unknown | Có thể server đã commit | Retry **commit** theo nhãn/driver contract; không tự chạy lại nghiệp vụ |
| Commit trả success | Transaction được xác nhận theo semantics | Đóng session, hoàn thành |
| Abort được xác nhận | Thay đổi chưa commit không được giữ | Có thể thực hiện nghiệp vụ khác trong transaction mới |
| Write concern timeout tại commit | Outcome có thể cần kiểm tra | Phân loại kết quả/lỗi, theo dõi commit và đối soát business ID |

### 10.5. Không dùng catch-all retry không giới hạn

Một vòng:

~~~javascript
while (true) {
  // chạy lại toàn bộ nghiệp vụ
}
~~~

là nguy hiểm vì:

- Có thể gây ghi lặp.
- Có thể đẩy server đang quá tải vào retry storm.
- Không phân biệt business error với transient server error.
- Không xử lý commit unknown đúng cách.
- Giao dịch có thể tiếp tục thất bại vì một constraint cố định.

Nên dùng helper transaction của driver khi phù hợp; nếu tự xử lý, phải có retry budget, phân loại lỗi và observability.

---

## 11. Cách xử lý lỗi và retry bằng callback API

Official drivers thường cung cấp **callback transaction API** (ví dụ `withTransaction`) để thực hiện retry logic phù hợp với những lỗi tạm thời và commit outcome uncertainty theo khả năng driver.

Ý tưởng:

~~~text
withTransaction(callback):
    startTransaction()
    try:
        chạy callback chứa database operations
        commitTransaction()
    nếu lỗi transient phù hợp:
        abort và thực hiện lại callback
    nếu kết quả commit chưa rõ:
        thử xác định bằng commit retry theo quy tắc driver
    nếu lỗi nghiệp vụ hoặc lỗi không retryable:
        abort và trả lỗi
~~~

Đây là **sơ đồ ý tưởng**, không phải mã thực thi của bất kỳ driver nào. Driver có deadline và chính sách retry cụ thể; không giả định mọi lỗi đều retry được.

### 11.1. Callback có thể chạy nhiều lần

Nếu callback bị chạy lại, mọi việc bên trong nó có thể lặp:

~~~text
Mong muốn:
  MongoDB transfer operations -> retry trong transaction.

Không mong muốn:
  Gửi email 3 lần khi callback retry 3 lần.
  Gọi payment gateway 3 lần.
  Publish Kafka event 3 lần.
~~~

**Không đưa external side effects không idempotent vào callback**. Một kiến trúc tốt hơn có thể ghi một **outbox document** trong MongoDB transaction, rồi worker riêng publish sự kiện sau commit, với idempotency và retry rõ ràng.

### 11.2. Idempotency key

Khi client gửi transfer request:

~~~javascript
{
  requestId: "REQ-TRANSFER-001",
  from: "ACC-A",
  to: "ACC-B",
  amount: 200000
}
~~~

sử dụng unique index:

~~~javascript
db.transfers.createIndex(
  { requestId: 1 },
  {
    unique: true,
    name: "uk_transfer_requestId"
  }
);
~~~

Mục đích: nếu client timeout sau commit và gửi lại cùng request ID, hệ thống có cơ sở xác định đó là một yêu cầu đã xử lý, thay vì trừ tiền thêm lần nữa.

Nhưng **unique index một mình chưa giải quyết toàn bộ idempotency**: ứng dụng còn phải xác minh request ID cũ có cùng amount/from/to, phân biệt pending/completed và trả kết quả phù hợp. Khi có duplicate key, không tự kết luận mọi lỗi khác nhau đều là transaction thành công.

### 11.3. Dùng bounded retry và logs

Thông tin nên log (không lộ dữ liệu nhạy cảm):

- Operation name / business request ID đã được bảo vệ.
- Transaction attempt number.
- Error label.
- Commit attempt count.
- Duration.
- Whether outcome known/unknown.
- MongoDB deployment/version.
- Error category, không dump nguyên thông tin tài khoản và secrets.

Đặt retry budget để tránh treo request vô hạn.

---

## 12. Java Sync Driver: session và transaction thủ công

### 12.1. Phụ thuộc ở mức khái niệm

Một Java application kết nối replica set sử dụng MongoDB Java Sync Driver, lấy `MongoClient`, `MongoDatabase` và `MongoCollection`.

Ví dụ:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class TransactionManualExample {

    public static void main(String[] args) {

        String uri =
            "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/"
            + "?replicaSet=rsLearn";

        MongoClientSettings clientSettings =
            MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .build();

        try (MongoClient client = MongoClients.create(clientSettings);
             ClientSession session = client.startSession()) {

            MongoDatabase database =
                client.getDatabase("training_bank");

            MongoCollection<Document> accounts =
                database.getCollection("accounts");

            MongoCollection<Document> transfers =
                database.getCollection("transfers");

            TransactionOptions options =
                TransactionOptions.builder()
                    .readPreference(ReadPreference.primary())
                    .readConcern(ReadConcern.SNAPSHOT)
                    .writeConcern(
                        WriteConcern.MAJORITY.withWTimeout(
                            5,
                            TimeUnit.SECONDS
                        )
                    )
                    .build();

            session.startTransaction(options);

            boolean commitAttempted = false;

            try {
                var debit = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", "ACC-A"),
                        Filters.gte("balance", 200000L)
                    ),
                    Updates.inc("balance", -200000L)
                );

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Không đủ số dư hoặc thiếu tài khoản nguồn"
                    );
                }

                var credit = accounts.updateOne(
                    session,
                    Filters.eq("_id", "ACC-B"),
                    Updates.inc("balance", 200000L)
                );

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Thiếu tài khoản nhận"
                    );
                }

                transfers.insertOne(
                    session,
                    new Document("_id", "TRANSFER-JAVA-001")
                        .append("requestId", "REQ-JAVA-001")
                        .append("from", "ACC-A")
                        .append("to", "ACC-B")
                        .append("amount", 200000L)
                        .append("status", "COMPLETED")
                );

                commitAttempted = true;
                session.commitTransaction();

            } catch (RuntimeException ex) {
                if (!commitAttempted) {
                    try {
                        session.abortTransaction();
                    } catch (RuntimeException ignored) {
                        // Ghi log trong ứng dụng thực.
                    }
                }

                // Nếu lỗi tại commit, không suy luận chắc
                // giao dịch đã thất bại. Ví dụ này chưa
                // triển khai vòng commit retry.
                throw ex;
            }
        }
    }
}
~~~

**Giới hạn của mã trên:** Nó diễn đạt rõ các bước manual và ranh giới abort/commit, **không phải mẫu error-handling production đầy đủ**. Nếu lỗi xảy ra trong commit, code **không** chạy lại toàn bộ transfer; nó trả lỗi để tầng ứng dụng xử lý kết quả chưa rõ theo yêu cầu. Trong production nên dùng API transaction callback khi phù hợp hoặc triển khai retry commit theo error labels đúng hướng dẫn driver.

### 12.2. Vì sao operations phải nhận `session`?

Trong Java driver:

~~~java
accounts.updateOne(session, filter, update);
~~~

phải khác:

~~~java
accounts.updateOne(filter, update);
~~~

Lệnh thứ hai không truyền session; nó có thể chạy ngoài transaction hiện tại. Một transaction chỉ bảo vệ các operations được thực hiện đúng session.

### 12.3. Vì sao dùng `try-with-resources`?

~~~java
try (ClientSession session = client.startSession()) {
    // ...
}
~~~

giúp đóng session khi khối hoàn tất. `MongoClient` cũng nên được quản lý vòng đời dài hạn cho application thay vì tạo một client mới trên mỗi request.

Ví dụ main trên tạo client để minh họa; trong service production nên dùng một MongoClient được quản lý bởi dependency injection/ứng dụng.

### 12.4. Dùng typed model hay Document?

`Document` thuận tiện cho lab. Với domain models, có thể dùng POJOs/codecs, repositories, schema validation và custom mapping. Nhưng dù model nào, transaction semantics vẫn phụ thuộc **ClientSession** và đúng deployment.

---

## 13. Java Sync Driver: callback transaction với `withTransaction`

Khi không muốn tự xây toàn bộ retry/commit loop, có thể dùng callback API của driver (tên và signature cụ thể cần đối chiếu version).

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public class TransactionCallbackExample {

    public static void doTransfer(
            ClientSession session,
            MongoCollection<Document> accounts,
            MongoCollection<Document> transfers) {

        TransactionOptions options =
            TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        session.withTransaction(() -> {

            var debit = accounts.updateOne(
                session,
                new Document("_id", "ACC-A")
                    .append("balance",
                        new Document("$gte", 100000L)),
                new Document("$inc",
                    new Document("balance", -100000L))
            );

            if (debit.getMatchedCount() != 1) {
                throw new IllegalStateException(
                    "Không đủ số dư"
                );
            }

            var credit = accounts.updateOne(
                session,
                new Document("_id", "ACC-B"),
                new Document("$inc",
                    new Document("balance", 100000L))
            );

            if (credit.getMatchedCount() != 1) {
                throw new IllegalStateException(
                    "Không có tài khoản đích"
                );
            }

            transfers.insertOne(
                session,
                new Document("_id", "TRANSFER-CALLBACK-001")
                    .append("requestId", "REQ-CALLBACK-001")
                    .append("amount", 100000L)
            );

            return null;

        }, options);
    }
}
~~~

Ở ví dụ này:

- `session.withTransaction` tự quản lý start/commit/abort và một phần retry theo contract driver.
- Callback chỉ thực hiện các **MongoDB operations thuộc session** và logic cần thiết.
- Không gửi email, gọi payment gateway hoặc ghi file không idempotent bên trong callback.
- Request ID phải được thiết kế để xử lý client-level retry ngoài callback.
- Một business exception như không đủ số dư không nên được giả định là transient và không cần retry vô hạn.

### 13.1. Callback API có thay thế idempotency không?

**Không.** Driver có thể retry ở cấp transaction/commit trong những trường hợp hỗ trợ, nhưng application request có thể được người dùng/API gateway gửi lại sau timeout. Đó là một lớp retry khác. Unique business ID và trạng thái xử lý vẫn cần thiết.

### 13.2. Nhãn lỗi và quyết định retry

Official driver dựa trên những error labels thích hợp để quyết định behavior. Không nên tự bắt **mọi** `MongoException` rồi chạy lại toàn callback:

- Duplicate key do dữ liệu trùng thường là lỗi cần xử lý nghiệp vụ.
- Validation error không tự hết sau retry.
- Thiếu quyền/authentication không phải transient conflict.
- Unknown commit result đòi chiến lược riêng.
- Một số lỗi tạm thời có thể retry toàn transaction.

### 13.3. Quyền kiểm soát transaction duration

Dù dùng callback, phải bảo đảm transaction ngắn và không chờ người dùng, dịch vụ mạng bên ngoài hoặc xử lý tính toán dài. Callback có retry budget giới hạn; tránh tạo vòng chờ lâu dẫn đến transaction lifetime limit và tăng contention.

---

## 14. Spring Data MongoDB và ranh giới session

Trong ứng dụng Spring, có thể sử dụng `MongoTransactionManager` và phương thức `@Transactional` khi đã cấu hình transaction support tương ứng với replica set/sharded cluster và Spring Data version.

Ví dụ ở mức ý tưởng:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransferRepository transferRepository;

    public TransferService(
            AccountRepository accountRepository,
            TransferRepository transferRepository) {
        this.accountRepository = accountRepository;
        this.transferRepository = transferRepository;
    }

    @Transactional
    public void transfer(String fromId,
                         String toId,
                         long amount,
                         String requestId) {

        // Pseudocode nghiệp vụ:
        // 1. Trừ tiền có điều kiện và kiểm tra matchedCount.
        // 2. Cộng tiền.
        // 3. Lưu transfer log cùng transaction.
        // 4. Throw exception khi kiểm tra thất bại.
    }
}
~~~

Ví dụ trên minh họa ranh giới service; các repository methods cụ thể và cấu hình manager phải do dự án cung cấp.

### 14.1. `@Transactional` không tự hoạt động trong mọi cấu hình

Muốn transaction MongoDB thực sự:

- MongoDB deployment phải hỗ trợ transactions.
- Spring Data/MongoTransactionManager phải được cấu hình phù hợp.
- Các thao tác database phải đi qua thành phần tham gia session/transaction.
- Transaction semantics và exception rollback rules phải được hiểu.
- Self-invocation hoặc lời gọi không đi qua proxy Spring có thể làm `@Transactional` không có hiệu lực như mong muốn trong cấu hình proxy thông thường.
- Giao dịch MongoDB không tự bao phủ database SQL hay REST API bên ngoài.

### 14.2. Không lẫn transaction manager của các resource khác nhau

Ứng dụng có cả PostgreSQL và MongoDB không tự có một transaction phân tán ACID chỉ vì cả hai đều dùng `@Transactional`. Phải chọn rõ transaction manager và cơ chế phối hợp xuyên resource, hoặc dùng saga/outbox/compensation.

### 14.3. Chỉ dùng cách này khi đã nắm được manual API

Hiểu `ClientSession`, `startTransaction`, `commitTransaction`, `abortTransaction` giúp phân tích lỗi thực tế khi Spring abstraction báo timeout, transient failure hoặc commit uncertain. Framework đơn giản hóa API, không làm các giới hạn cơ bản biến mất.

---

## 15. Những lỗi thường gặp trong transaction

### 15.1. Ghi ngoài session một cách vô ý

~~~javascript
const session = db.getMongo().startSession();
const sdb = session.getDatabase("shop");

session.startTransaction();

sdb.orders.insertOne({ _id: "O-001" });

// LỖI THIẾT KẾ: không thuộc session phía trên.
db.getSiblingDB("shop")
  .inventory.updateOne(
    { _id: "SKU-001" },
    { $inc: { stock: -1 } }
  );
~~~

Nếu transaction abort, order có thể bị hủy nhưng inventory đã bị thay đổi bên ngoài. Dùng cùng session cho **mọi thao tác** phải atomic.

### 15.2. Bắt đầu transaction lồng nhau

~~~javascript
session.startTransaction();
// ...
session.startTransaction(); // Không phải nested transaction hợp lệ.
~~~

Cần commit/abort transaction trước rồi mới bắt đầu transaction mới.

### 15.3. Bỏ quên `commitTransaction()`

Chỉ start và update:

~~~javascript
session.startTransaction();
sdb.orders.insertOne({ _id: "O-101" });
session.endSession();
~~~

không phải một cách hợp lệ để bảo đảm transaction đã được commit. Phải gọi commit có chủ đích, xử lý kết quả, rồi đóng session.

### 15.4. Chạy giao dịch trên standalone

Nếu dùng standalone không hỗ trợ transactions, operation sẽ lỗi. Để học một máy, dùng single-node replica set thay vì giả định MongoDB standalone hoạt động giống production replica set.

### 15.5. Dùng `secondary` read preference cho transaction ghi

Giao dịch ghi cần được xử lý theo các quy tắc primary. Đừng tùy tiện cấu hình secondary reads cho cả transaction ghi rồi mong secondary nhận insert/update.

### 15.6. Thao tác DDL không được hỗ trợ

Không phải mọi operation đều được dùng trong transaction. Một số DDL/index operations và aggregation stages như `$out`, `$merge` có những hạn chế; không thiết kế schema migration như một phần của transfer transaction thông thường.

Nên tạo collections/indexes và schema validation phù hợp trước khi xử lý giao dịch. DDL support chính xác phụ thuộc MongoDB version, topology và các quy tắc liên quan; kiểm tra tài liệu khi có nhu cầu đặc biệt.

### 15.7. Transaction quá dài

Giữ transaction mở trong lúc:

- Gọi API ngoài.
- Chờ người dùng thanh toán.
- Xử lý batch hàng triệu document.
- Tạo báo cáo nặng.
- Sleep một khoảng dài.

có thể làm tăng lock contention, snapshot/cache pressure, replication cost và nguy cơ vượt transaction lifetime limit.

### 15.8. Retry mù một khoản tiền

Lỗi mạng tại commit không chứng minh chưa commit. Nếu client gọi lại “chuyển tiền” bằng request ID mới, có thể double transfer. Thiết kế idempotency trước khi xử lý timeout.

---

## 16. Write Conflict và các thao tác đồng thời

### 16.1. Hai transactions cùng sửa một account

T1 và T2 cùng bắt đầu trên một trạng thái:

~~~text
T1: Đọc A.balance = 500000
T2: Đọc A.balance = 500000

T1: A.balance -= 400000
T2: A.balance -= 300000
~~~

MongoDB sử dụng các cơ chế concurrency control và write-conflict detection để không đơn giản cho mọi cập nhật cùng document cùng commit trái quy tắc transaction. Một transaction có thể nhận **write conflict/transient transaction error** và phải thực hiện lại theo chính sách.

### 16.2. Không tự đọc rồi update không điều kiện

Sai về nghiệp vụ:

~~~javascript
const a = accounts.findOne({ _id: "ACC-A" });

if (a.balance >= amount) {
  accounts.updateOne(
    { _id: "ACC-A" },
    { $inc: { balance: -amount } }
  );
}
~~~

Nếu không bảo đảm concurrency, quyết định dựa vào một bản đọc cũ có thể không còn hợp lệ.

An toàn hơn với predicate ở thao tác ghi:

~~~javascript
const result = accounts.updateOne(
  {
    _id: "ACC-A",
    balance: { $gte: amount }
  },
  {
    $inc: {
      balance: -amount
    }
  }
);

if (result.matchedCount !== 1) {
  throw new Error("Không đủ số dư");
}
~~~

Đặt điều kiện vào write giúp áp đặt invariant ở điểm ghi, ngay cả khi transaction phải retry.

### 16.3. Write skew và ràng buộc nhiều document

Giả sử có hai bác sĩ trực, quy tắc “luôn phải còn ít nhất một bác sĩ trực”. Hai transactions có thể đọc cùng snapshot, mỗi transaction tắt trạng thái trực của một người **khác nhau**. Nếu chỉ đọc đếm rồi sửa hai document tách biệt, một số mô hình isolation có thể cho phép write skew, khiến invariant bị vi phạm.

Giải pháp không chỉ là thêm transaction, mà phải thiết kế điểm ghi chung, conditional update, constraint hoặc cơ chế đồng bộ phù hợp. Transaction atomicity và business serializability là hai câu hỏi khác nhau.

---

## 17. Giao dịch trên replica set và sharded cluster

### 17.1. Replica set

Trong replica set, primary nhận operations của transaction. Transaction có thể trải nhiều collections trên deployment được hỗ trợ.

Độ bền của commit phụ thuộc write concern và tình trạng replication. Nếu primary failover trong lúc transaction đang thực hiện, driver/client có thể nhận transient error và cần retry.

### 17.2. Sharded cluster

MongoDB hỗ trợ distributed transactions trên sharded clusters từ 4.2. Khi thao tác chạm nhiều shards, quá trình commit phức tạp hơn transaction chỉ trên một replica set, có thể liên quan phối hợp commit trên nhiều participants.

Đánh đổi:

- Latency commit có thể cao hơn.
- Khả năng gặp timeout/transient errors cao hơn ở một số workloads.
- Các hạn chế DDL, chunk migration, namespace và operations cần được kiểm tra.
- Vẫn cần bounded retry và idempotency.
- Nên giữ transaction càng nhỏ/ngắn càng tốt.

### 17.3. Không đưa toàn bộ batch vào một transaction nếu không cần

Ví dụ import 1 triệu documents vào 20 collections không nên mặc định gom thành một transaction duy nhất. Cần phân hoạch theo đơn vị atomic nghiệp vụ, dùng bulk writes phù hợp, idempotency và checkpoint.

### 17.4. Sharding không tự sửa lỗi transaction

Phân tán dữ liệu nhiều shards giúp scale một số workloads, nhưng transaction vẫn cần đúng session, start/commit/abort và consistency settings. Không xem sharding là cách miễn phí để chạy transactions vô hạn.

---

## 18. Giới hạn về thời gian, tài nguyên và thao tác

### 18.1. Transaction lifetime

MongoDB có tham số **`transactionLifetimeLimitSeconds`**; giá trị mặc định thường là **60 giây** trong những triển khai tương ứng. Transactions chạy quá thời gian giới hạn có thể bị server abort.

Đây không phải “mỗi transaction luôn có đúng 60 giây ở mọi MongoDB version”. Cần đọc cấu hình và môi trường thực tế.

### 18.2. Transaction dùng snapshot và tài nguyên

Transaction có thể giữ trạng thái snapshot và làm tăng áp lực WiredTiger cache, memory, locks và replication. Giao dịch chạy dài có thể gây:

- TransactionTooLargeForCache hoặc các lỗi tài nguyên liên quan.
- Write conflicts.
- Disk/cache pressure.
- Tăng latency cho hoạt động khác.
- Độ trễ commit cao.

Không đồng nhất **16 MB giới hạn kích thước BSON document** với “mọi transaction chỉ tối đa 16 MB”. Transaction có các ràng buộc oplog entries, resources và operations khác; giới hạn cụ thể phụ thuộc phiên bản.

### 18.3. Thao tác không được hỗ trợ

Một số aggregation stages như `$out`/`$merge` và các lệnh quản trị/DDL không được phép bên trong transactions trong nhiều cấu hình. Không dựa vào “mọi lệnh mongosh chạy được ngoài transaction” để suy rằng chúng chạy được trong transaction.

### 18.4. Một session không được dùng song song tùy tiện

Trong Node.js hoặc hệ thống async, không dùng nhiều operations song song cùng session/transaction bằng `Promise.all` khi driver không hỗ trợ. Trong Java, không chia sẻ một `ClientSession` giữa nhiều threads cho các thao tác transaction song song.

### 18.5. Không thực hiện I/O ngoài giữa transaction

Thay vì:

~~~text
start transaction
  update account
  gọi payment gateway mất 20 giây
  gửi email
  update ledger
commit
~~~

nên cân nhắc:

~~~text
MongoDB transaction:
  update nội bộ
  insert outbox event
commit

Worker sau commit:
  đọc outbox event
  gọi external API với idempotency key
  đánh dấu kết quả / retry / compensation
~~~

Đây là một kiến trúc để phân tách atomic database changes khỏi side effects bên ngoài.

---

## 19. Phân biệt lỗi nghiệp vụ, lỗi thao tác và lỗi commit

### 19.1. Business error

Ví dụ không đủ tiền:

~~~javascript
const result = accounts.updateOne(
  {
    _id: "ACC-A",
    balance: { $gte: amount }
  },
  { $inc: { balance: -amount } }
);

if (result.matchedCount === 0) {
  throw new Error("INSUFFICIENT_FUNDS");
}
~~~

Đây không phải transient server error. Retry tự động ngay lập tức không làm số dư tăng lên. Giao dịch nên abort và báo lỗi hợp lệ cho người dùng.

### 19.2. Transient database error

Các tình huống như write conflict hoặc election có thể khiến transaction phải được làm lại. Khi driver cung cấp label `TransientTransactionError`, follow transaction retry guidance của API.

Không tự nhận diện lỗi bằng cách so text message chính xác vì message có thể khác phiên bản/ngôn ngữ; dùng error labels/codes phù hợp.

### 19.3. Commit outcome unknown

Khi lỗi có nhãn `UnknownTransactionCommitResult`, đừng chạy lại body như một transaction mới ngay. Giao dịch có thể đã commit. Cần dùng commit retry trong cùng transaction/session theo driver, hoặc đối soát trạng thái business khi không thể xác định trực tiếp.

### 19.4. Transaction bị server abort

Một số lỗi khiến server hủy transaction. Khi đó tiếp tục gọi các writes như thể transaction vẫn active có thể phát sinh lỗi thứ cấp. Cần xác định trạng thái, abort nếu phù hợp rồi bắt đầu transaction mới cho retry.

### 19.5. Retryable writes khác transaction retry

**Retryable writes** là tính năng ở mức một số thao tác ghi; **transaction retry** là cơ chế chạy lại cả nhóm operations hoặc commit. Hai cơ chế không thay thế nhau và có các điều kiện khác nhau.

---

## 20. Transaction và tính idempotent cho request API

### 20.1. Bài toán request bị gửi lại

Client gửi:

~~~json
{
  "requestId": "REQ-2026-001",
  "fromAccount": "ACC-A",
  "toAccount": "ACC-B",
  "amount": 200000
}
~~~

Server commit nhưng response tới client bị mất. Client gửi lại cùng request.

Nếu API chỉ tạo transaction mới và trừ/cộng tiền lần nữa, có thể gây chuyển tiền hai lần.

### 20.2. Dùng business ID ổn định

Tạo unique index:

~~~javascript
db.transfers.createIndex(
  { requestId: 1 },
  {
    name: "uk_requestId",
    unique: true
  }
);
~~~

Trong transaction, ghi transfer record cùng changes vào accounts. Một request ID đã commit sẽ tồn tại để kiểm tra.

### 20.3. Quy trình API nên xét

~~~text
Nhận requestId
     |
     v
Có transfer đã hoàn tất với requestId?
     |
     +-- Có, payload khớp --> trả kết quả đã xử lý
     |
     +-- Có, payload khác --> báo conflict
     |
     +-- Chưa có ---------> thử transaction
                               |
                               +--> commit success
                               |
                               +--> business failure + abort
                               |
                               +--> transient retry
                               |
                               +--> unknown commit -> xác định/đối soát
~~~

Một sơ đồ idempotency production còn phải xử lý **hai request cùng requestId đến đồng thời** và trạng thái pending. Unique index là nền tảng quan trọng, nhưng cần kiểm tra atomicity của record và chính sách trả kết quả.

### 20.4. Không gửi external event ngay trong body transaction

Nếu body có:

~~~text
accounts.update...
emailService.send("Chuyển tiền thành công")
transfers.insert...
~~~

callback có thể chạy lại, gửi email nhiều lần trong khi MongoDB chỉ commit một lần. Sử dụng outbox, idempotent message processing hoặc một chiến lược phân tán phù hợp.

---

## 21. Transaction và một thao tác đơn document

MongoDB đảm bảo atomicity cho một thao tác ghi trên một document. Ví dụ dùng một document cho giỏ hàng:

~~~javascript
{
  _id: "CART-101",
  items: [
    { sku: "A", quantity: 1 },
    { sku: "B", quantity: 2 }
  ],
  totalItems: 3
}
~~~

Nếu toàn bộ nghiệp vụ update nằm trong cùng document và có thể thực hiện bằng một atomic update, thường không cần transaction nhiều document.

Ví dụ:

~~~javascript
db.carts.updateOne(
  { _id: "CART-101" },
  {
    $inc: { totalItems: 1 },
    $push: {
      items: {
        sku: "C",
        quantity: 1
      }
    }
  }
);
~~~

Một update duy nhất thay đổi nhiều field của một document theo atomicity document. Trước khi thêm session/transaction, hỏi:

- Có nhiều document phải cập nhật đồng bộ không?
- Có thể mô hình hóa dữ liệu cần bất biến chung trong một document không?
- Một conditional update có đủ không?
- Tác vụ có thể thiết kế idempotent thay vì giao dịch lớn không?

Transactions hữu ích nhưng không thay thế document modeling.

---

## 22. Bảo đảm sau commit và các thao tác quan sát

### 22.1. Sau commit thành công

Giả sử transaction cập nhật A/B rồi commit với `w:"majority"`. Client được xác nhận commit theo mức đó. Việc một secondary khác vẫn có lag không trái với majority semantics.

### 22.2. Trước commit

Các thao tác trong transaction có thể có kết quả tạm thời đối với chính session. Các client khác không được xem chúng như thay đổi đã commit theo các semantics isolation.

### 22.3. Sau abort

Các write chưa commit của transaction không được giữ lại như dữ liệu cuối. Nhưng:

- Một transaction đã commit trước đó không bị ảnh hưởng.
- Thao tác ngoài session không được rollback.
- Side effects bên ngoài MongoDB không được rollback.

### 22.4. Trong failover

Nếu primary thay đổi khi transaction đang hoạt động, transaction có thể bị abort hoặc nhận transient error, và caller cần xử lý theo driver API. Đừng hứa một transaction sẽ tự động tiếp tục nguyên trạng sau mọi election.

### 22.5. Commit majority không tương đương mọi secondary đã theo kịp

Replica set ba members có thể đạt majority sau khi primary và một secondary đạt tiến độ, còn secondary thứ ba vẫn chậm. Điều đó có thể ảnh hưởng read preference secondary và việc kiểm tra ngay sau commit.

---

## 23. Quan sát transaction trên MongoDB

### 23.1. `db.currentOp()`

Với quyền phù hợp:

~~~javascript
db.currentOp();
~~~

Có thể quan sát các operations đang chạy và thông tin transaction khi server cung cấp. Không nên dựa vào một field nội bộ duy nhất cho mọi phiên bản.

### 23.2. `serverStatus()`

~~~javascript
db.serverStatus();
~~~

MongoDB công bố các metrics liên quan đến transactions, operations, connections và storage engine trong những trường hợp phù hợp. Các field/format thay đổi theo version.

### 23.3. Log/monitoring

Theo dõi:

- Số transactions active/open/aborted/committed nếu metrics được hỗ trợ.
- Transaction duration (p50, p95, p99).
- Write conflicts.
- Commit latency.
- Unknown commit results.
- Retry attempts.
- Replica set elections.
- Write concern timeouts.
- Cache/memory pressure.
- Slow operations.
- Business ID reconciliation failures.

Không chỉ nhìn latency của một insert trong transaction; chi phí end-to-end gồm toàn bộ body + commit/retry.

### 23.4. Đặt comment/tracing khi phù hợp

Một số MongoDB operations hỗ trợ `comment` để gắn nhãn truy vết. Trong ứng dụng, nên dùng request correlation IDs không chứa dữ liệu nhạy cảm và log error labels/attempts có giới hạn.

---

## 24. Kiểm thử transaction: điều gì cần chứng minh?

### 24.1. Commit thành công

Tạo A=1.000.000, B=300.000; chuyển 200.000. Sau commit:

- A = 800.000.
- B = 500.000.
- Có một transfer record.
- Tổng A+B không đổi nếu không có phí.

### 24.2. Abort do business validation

Thử chuyển 2.000.000 từ A khi A chỉ có 1.000.000. Sau abort:

- A vẫn 1.000.000.
- B vẫn 300.000.
- Không có transfer COMPLETED.
- API trả lỗi INSUFFICIENT_FUNDS.

### 24.3. Destination không tồn tại

Trừ A tạm trong transaction, sau đó update B không khớp. Abort. Kiểm tra A không bị trừ.

### 24.4. Lỗi giữa các bước

Chèn lỗi có chủ đích sau bước debit nhưng trước credit. Abort. Kiểm tra không có partial effects.

### 24.5. Duplicate request ID

Commit request `REQ-001`, sau đó gửi lại cùng request ID. Kiểm tra không trừ tiền lần hai và response phù hợp.

### 24.6. Concurrent transactions

Chạy hai transfers cùng trừ từ A. Kiểm tra balance không âm và retry/abort được xử lý đúng. Dùng controlled concurrency test với dataset đủ, không chỉ một lần chạy.

### 24.7. Failover trong transaction

Trong môi trường staging/replica set lab, mô phỏng primary election khi transaction đang chạy. Kiểm tra driver retry labels, API result, idempotency và không có ghi đôi.

### 24.8. Commit outcome unknown

Mô phỏng mất kết nối tại commit trong test harness. Kiểm tra ứng dụng không tự thực hiện transfer hai lần và có cơ chế reconcile theo request ID.

### 24.9. Transaction timeout

Tạo tình huống transaction vượt thời gian giới hạn trong môi trường lab; kiểm tra error handling. Không giữ một transaction production mở chỉ để thử.

### 24.10. Read outside transaction

Chạy transaction chưa commit rồi đọc từ một client khác. Kiểm tra chỉ thấy dữ liệu đã commit theo semantics/concerns đã chọn, tránh đánh đồng dữ liệu tạm trong session với dữ liệu ngoài session.

---

## 25. Bài tập thực hành

### Bài tập 1 — Session không phải transaction

Tạo session, thực hiện hai operations mà không gọi startTransaction. Giải thích vì sao không có multi-document atomicity.

### Bài tập 2 — Commit

Tạo hai tài khoản có số dư ban đầu. Viết transaction chuyển 100.000 và ghi transfer record. Gọi commit rồi kiểm tra cả ba document.

### Bài tập 3 — Abort

Viết transaction trừ tiền, sau đó chủ động abort. Chứng minh dữ liệu giữ nguyên. Giải thích vì sao abort không hủy các writes của transaction trước đã commit.

### Bài tập 4 — Quên session

Trong một transaction, cập nhật collection accounts qua session nhưng insert transfer log qua handle bình thường. Mô phỏng lỗi trước commit. Phân tích vì sao log có thể không rollback và sửa mã.

### Bài tập 5 — Điều kiện số dư

Dùng `updateOne` filter với `balance: {$gte: amount}` và kiểm tra `matchedCount`. Nếu số dư không đủ, abort và trả lỗi nghiệp vụ.

### Bài tập 6 — Ghi lịch sử

Mở rộng bài 2 để transfer log chứa request ID, from/to, amount, status, createdAt và unique index requestId. Kiểm thử duplicate request.

### Bài tập 7 — Error labels

Vẽ hai flow xử lý:

- `TransientTransactionError` → retry toàn transaction theo điều kiện phù hợp.
- `UnknownTransactionCommitResult` → retry commit/đối soát, không tự chạy lại body.

### Bài tập 8 — Java Sync Driver

Viết mã Java có `MongoClient`, `ClientSession`, `TransactionOptions`, hai updateOne(session,..), insertOne(session,..) và commit/abort. Đảm bảo session được đóng.

### Bài tập 9 — Callback API

Chuyển bài 8 sang `session.withTransaction(...)` và chỉ đặt MongoDB operations trong callback. Giải thích vì sao không gọi emailService.send trong callback.

### Bài tập 10 — Read/Write Concern

Chọn readConcern snapshot, writeConcern majority và readPreference primary. Giải thích chúng kiểm soát những khía cạnh khác nhau và tại sao majority commit không đảm bảo mọi secondary đã theo kịp.

### Bài tập 11 — Standalone vs replica set

Chạy transaction trên standalone lab và quan sát lỗi; sau đó dùng single-node replica set để thử lại. Vì sao single-node replica set có thể hỗ trợ API transaction nhưng không có HA?

### Bài tập 12 — Write conflict

Chạy hai transactions đồng thời cập nhật cùng account. Quan sát một số lỗi transient/write conflict và mô tả bounded retry strategy.

### Bài tập 13 — Không đủ tiền và duplicate transfer

Trong một transfer transaction, nếu debit không khớp hoặc request ID đã được xử lý, phải abort hoặc trả kết quả idempotent phù hợp. Viết bảng trạng thái lỗi và response API.

### Bài tập 14 — External side effects

Thiết kế quy trình tạo order và phát event ORDER_CREATED sao cho event chỉ được publish sau commit. Nêu giải pháp outbox và idempotent consumer.

### Bài tập 15 — Transaction quá dài

Giả sử một giao dịch xử lý 50.000 products và gọi hai external APIs. Phân tích rủi ro lifetime, cache pressure, retry storm; đề xuất chia theo đơn vị atomic nhỏ hơn.

### Bài tập 16 — Sharded transaction

Mô tả sự khác nhau giữa transaction chỉ trên một replica set và distributed transaction chạm nhiều shards về phối hợp commit, latency và failure modes. Không cần triển khai cơ chế nội bộ bằng tay.

### Bài tập 17 — Kiểm thử failover

Trong môi trường staging, dừng primary khi một transaction đang chạy. Quan sát lỗi, retry và trạng thái tài khoản cuối cùng. Vì sao không kết luận thất bại chỉ vì request timeout?

### Bài tập 18 — Monitoring

Đề xuất dashboard cho transaction count, commit rate, abort rate, write conflict rate, latency, timeout và unknown commit result. Nêu ngưỡng/alert dựa trên workload thật.

---

## 26. Câu hỏi ôn tập

1. Logical session là gì?
2. Session khác transaction như thế nào?
3. Tạo session có tự tạo transaction không?
4. `startTransaction()` có ý nghĩa gì?
5. Vì sao mọi thao tác cần atomic phải dùng cùng session?
6. Một session có thể chạy hai transactions đồng thời không?
7. `commitTransaction()` làm gì?
8. `abortTransaction()` làm gì?
9. Abort có đảo được transaction đã commit trước đó không?
10. Gọi `endSession()` có thay thế commit không?
11. Transactions được hỗ trợ trên những deployment nào?
12. Single-node replica set khác standalone ra sao về API transaction?
13. Vì sao write concern được xét tại commit thay vì từng write trong transaction?
14. ReadConcern snapshot giúp gì?
15. WriteConcern majority bảo đảm điều gì và không bảo đảm điều gì?
16. ReadPreference primary có vai trò gì với transaction?
17. Vì sao thao tác ghi đã trả kết quả trong transaction chưa đồng nghĩa đã commit?
18. Vì sao mất kết nối tại commit tạo outcome unknown?
19. `TransientTransactionError` và `UnknownTransactionCommitResult` khác nhau thế nào?
20. Vì sao retry commit khác retry toàn transaction?
21. Tại sao không retry mọi business exception?
22. Vì sao callback `withTransaction` có thể chạy lại?
23. Vì sao không gửi email trong transaction callback?
24. Unique request ID giúp idempotency thế nào?
25. Vì sao unique index chưa phải toàn bộ giải pháp idempotency?
26. Transaction có tự ngăn mọi race condition hoặc write skew không?
27. Khi nào một atomic single-document update đủ thay transaction?
28. Transaction kéo dài có các chi phí gì?
29. TransactionLifetimeLimitSeconds thường dùng để giới hạn điều gì?
30. Vì sao DDL và một số aggregation stages bị hạn chế trong transaction?
31. Transactions trên sharded cluster có thể tốn thêm chi phí nào?
32. Vì sao không tự triển khai retry loop vô hạn?
33. Những chỉ số nào cần theo dõi khi giao dịch hay bị abort?
34. Tại sao failover có thể làm transaction đang chạy bị lỗi?
35. Thiết kế test nào chứng minh debit/credit/ledger all-or-nothing?

---

## 27. Tổng kết

Giao dịch nhiều document trong MongoDB cần hai cấp khái niệm rõ ràng:

- **Session:** ngữ cảnh logic liên kết các database operations.
- **Transaction:** ranh giới gồm các thao tác cần atomicity, bắt đầu bằng `startTransaction()` và kết thúc bằng `commitTransaction()` hoặc `abortTransaction()`.

Những nguyên tắc quan trọng:

1. **Dùng đúng cùng session** cho mọi thao tác cần atomicity.
2. **Giữ transaction ngắn**, có điều kiện nghiệp vụ và ràng buộc dữ liệu rõ ràng.
3. **Commit** mới là bước yêu cầu chấp nhận transaction; thao tác tạm bên trong chưa đồng nghĩa đã commit.
4. **Abort** chỉ hủy những thay đổi chưa commit của transaction đó, không rollback writes ngoài transaction hoặc external API.
5. **Lỗi commit unknown** khác lỗi transient trước commit; cần xử lý retry khác nhau.
6. **Callback transaction API** giúp giảm lỗi tự triển khai retry, nhưng vẫn cần idempotency cho request cấp ứng dụng.
7. **Read/write concerns** quyết định mức độ nhất quán/durability; transaction không tự biến mọi thao tác thành serializable.
8. **Replica set/sharded cluster** là deployment phù hợp; standalone không có cùng multi-document transaction support.
9. **Transaction không thay document model, schema validation hoặc outbox/saga** cho nghiệp vụ bên ngoài MongoDB.
10. **Kiểm thử commit, abort, concurrent updates, failover và timeout** trước khi đưa các nghiệp vụ tiền tệ/tồn kho lên production.

Một transaction tốt không chỉ “chạy không báo lỗi”. Nó phải trả lời đúng câu hỏi: **những thay đổi nào thật sự thuộc cùng giao dịch, khi nào kết quả được xác nhận, điều gì phải làm nếu commit không rõ, và làm sao ngăn một request bị xử lý hai lần?**

## Tài liệu MongoDB chính thức tham khảo

- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions and Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/)
- [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Transactions and Read Concern](https://www.mongodb.com/docs/manual/core/transactions/#read-concern-write-concern-read-preference)
- [MongoDB Manual — Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [MongoDB Manual — Read Concern Snapshot](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Session Commands](https://www.mongodb.com/docs/manual/reference/command/startSession/)
- [MongoDB Manual — Commit Transaction Command](https://www.mongodb.com/docs/manual/reference/command/commitTransaction/)
- [MongoDB Manual — Abort Transaction Command](https://www.mongodb.com/docs/manual/reference/command/abortTransaction/)
- [MongoDB Manual — MongoDB Shell Transactions](https://www.mongodb.com/docs/mongodb-shell/reference/methods/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver — Sessions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/#client-sessions)
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
