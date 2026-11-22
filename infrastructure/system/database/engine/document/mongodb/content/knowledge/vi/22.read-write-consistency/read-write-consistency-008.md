# Snapshot read và phạm vi áp dụng bên ngoài hoặc bên trong giao dịch trong MongoDB

## 1. Mục tiêu bài học

Một hệ thống MongoDB đang phục vụ người dùng có thể đồng thời nhận đơn hàng, chuyển tiền, cập nhật tồn kho và chạy báo cáo. Trong lúc một báo cáo đọc dữ liệu, các transaction và các lệnh ghi khác vẫn có thể hoàn tất. Vì vậy, hai lần đọc liên tiếp không nhất thiết cùng phản ánh một trạng thái của cơ sở dữ liệu.

Ví dụ, API phân trang đọc 20 dòng đầu tiên rồi đếm tổng số kết quả. Nếu một đơn hàng mới được tạo giữa hai truy vấn, danh sách có thể mô tả thời điểm T0 trong khi total mô tả thời điểm T1. Cả hai câu lệnh riêng lẻ đều có thể thực hiện đúng, nhưng **cặp kết quả** không nhất quán theo một thời điểm.

MongoDB cung cấp read concern `"snapshot"` để đọc dữ liệu như nó tồn tại tại **một timestamp logic xác định**, trong phạm vi và với điều kiện hỗ trợ của phiên bản server/driver.

Bài thuộc chương **Nhất quán đọc ghi** của **Database Engine Document MongoDB**, tập trung vào **Snapshot read và phạm vi áp dụng bên ngoài hoặc bên trong giao dịch**.

Sau bài học, bạn có thể:

1. Phân biệt `local`, `majority`, `snapshot` và `linearizable`.
2. Hiểu snapshot read bảo đảm điều gì, và không bảo đảm tính chất nào.
3. Sử dụng snapshot trong multi-document transaction với read concern ở **cấp transaction**.
4. Biết vì sao từ **MongoDB 5.0** có thể đọc snapshot **ngoài transaction** cho các command được hỗ trợ.
5. Dùng `find`, `aggregate`, `atClusterTime` và `snapshot:true` session trong mongosh.
6. Dùng snapshot session và transaction trong Java Sync Driver.
7. Xử lý giới hạn history window, `SnapshotTooOld`, secondary lag và sharded cluster.
8. Thiết kế báo cáo và phân trang nhất quán mà không nhầm snapshot với backup, transaction hay retry.

**Thông điệp quan trọng:** `readConcern:"snapshot"` là một yêu cầu về **góc nhìn dữ liệu**. Nó không tự làm mọi thao tác ghi trở thành nguyên tử, không giữ dữ liệu cũ vô hạn và không bảo đảm snapshot là phiên bản mới nhất khi ứng dụng hiển thị kết quả.

## 2. Snapshot read hoạt động về mặt ý tưởng như thế nào?

Giả sử hệ thống lưu hai ví điện tử:

~~~javascript
{ _id: "A", balance: NumberDecimal("500.00") }
{ _id: "B", balance: NumberDecimal("300.00") }
~~~

Một transaction chuyển 50 từ A sang B và commit:

~~~text
T0: A=500, B=300; tổng 800
          |
          |  transaction chuyển 50
          v
T1: A=450, B=350; tổng 800
~~~

Một báo cáo đọc A trước T1 nhưng đọc B sau T1 có thể thấy:

~~~text
A=500 (giá trị trước commit)
B=350 (giá trị sau commit)
Tổng quan sát = 850
~~~

Kết quả 850 không đại diện cho toàn bộ trạng thái tại T0 hay T1. Snapshot giúp chọn một góc nhìn:

~~~text
Thời gian ---------- T0 ------------ T1 ---------->

Snapshot S0:
  Đọc A sau T1  -> vẫn nhìn A=500 tại T0
  Đọc B sau T1  -> vẫn nhìn B=300 tại T0

Snapshot S1:
  Đọc A        -> A=450 tại T1
  Đọc B        -> B=350 tại T1
~~~

### 2.1. Thời điểm snapshot không phải đồng hồ ứng dụng

Timestamp trong cơ chế snapshot của MongoDB là một **BSON Timestamp/cluster time** được dùng theo quy tắc replication và lưu trữ. Nó không đồng nghĩa giá trị `Date` của document, không phải `createdAt` và không thể tùy ý chọn một ISODate rất xa trong quá khứ.

### 2.2. Một snapshot có thể cũ nhưng vẫn nhất quán

Nếu snapshot được chốt tại T0, write majority-committed ở T1 vẫn không tự xuất hiện trong snapshot T0. Đây là hành vi đúng: snapshot đọc phiên bản ở thời điểm đã chọn.

**Snapshot consistency** và **độ tươi dữ liệu** là hai yêu cầu khác nhau. Một ứng dụng cần đọc dữ liệu mới nhất có thể phải chọn read concern/đường đọc khác hoặc dùng một snapshot mới.

### 2.3. Snapshot không làm nhiều update ngoài transaction nguyên tử

Hai thao tác sau là hai write riêng biệt:

~~~javascript
db.accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: NumberDecimal("-50.00") } }
);

db.accounts.updateOne(
  { _id: "B" },
  { $inc: { balance: NumberDecimal("50.00") } }
);
~~~

Ở thời điểm giữa hai write, trạng thái thật có thể là A=450, B=300. Một snapshot chọn đúng thời điểm trung gian đó sẽ phản ánh trạng thái trung gian, **không thể tự biến hai write riêng thành một transaction**.

Nếu nghiệp vụ yêu cầu chuyển tiền nguyên tử giữa nhiều document, cần transaction hoặc mô hình cập nhật nguyên tử khác phù hợp. Nếu yêu cầu chỉ là *nhiều lần đọc có cùng góc nhìn*, snapshot read mới là cơ chế trực tiếp.

## 3. Phân biệt read concern, write concern và read preference

| Khái niệm | Câu hỏi nó giải quyết |
|---|---|
| `readConcern` | Được đọc phiên bản dữ liệu nào? |
| `writeConcern` | Write phải được xác nhận ở mức nào? |
| `readPreference` | Read có thể chạy trên node nào? |
| `session` | Những operation nào chia sẻ ngữ cảnh logic? |
| `transaction` | Những operation nào là một đơn vị commit/abort? |

Ví dụ:

~~~text
readPreference=secondary
readConcern=snapshot
~~~

có thể cho phép read snapshot trên secondary trong phiên bản hỗ trợ. Nó không biến secondary thành primary và không có nghĩa dữ liệu đó là mới nhất trên toàn cluster.

### 3.1. Các mức read concern phổ biến

| Mức | Ý nghĩa khái quát | Điều cần lưu ý |
|---|---|---|
| `local` | Đọc dữ liệu hiện có trên node, không đòi majority-committed | Có thể quan sát dữ liệu sau này bị rollback |
| `majority` | Chỉ đọc dữ liệu đã majority-committed theo bảo đảm của read concern | Hai query riêng có thể đọc hai timestamp khác nhau |
| `snapshot` | Đọc một góc nhìn dữ liệu ở timestamp được chọn | Không tự mới nhất; cần phạm vi/command được hỗ trợ |
| `linearizable` | Bảo đảm mạnh về thứ tự thời gian thực cho các read phù hợp ở primary | Không tương đương snapshot qua nhiều collection/shard |

### 3.2. Tại sao majority không đủ cho nhiều query?

Giả sử đơn 101 từ `NEW` thành `PAID` ở T1 và write đã majority-committed. Read thứ nhất ở T0 thấy `NEW`; read thứ hai ở T2 thấy `PAID`. Hai kết quả đều có thể đúng ở mức majority, nhưng không cùng timestamp.

Snapshot session giúp cố định nhiều read về một timestamp, còn một query majority riêng lẻ không có nghĩa ấy.

### 3.3. Snapshot không đồng nghĩa linearizable

Một snapshot có thể phản ánh quá khứ gần. Linearizable read hướng tới bảo đảm quan hệ với những thao tác đã hoàn tất trong thời gian thực theo điều kiện hỗ trợ. Không gọi mọi snapshot là “dữ liệu mới nhất”; cũng không dùng linearizable làm cách thay thế tự động cho báo cáo snapshot dài trên nhiều collection.

## 4. Hỗ trợ theo phiên bản và theo phạm vi

### 4.1. Snapshot bên trong transaction

MongoDB hỗ trợ snapshot read concern trong multi-document transactions theo phạm vi transaction được hỗ trợ:

- Replica set hỗ trợ multi-document transactions từ MongoDB **4.0**.
- Sharded clusters hỗ trợ transactions từ MongoDB **4.2**.
- Read concern của transaction được đặt ở cấp **`startTransaction`**, không ở từng lệnh đọc.
- Để có bảo đảm đọc từ majority-committed snapshot theo MongoDB Manual, transaction cần **commit với write concern `"majority"`**.

### 4.2. Snapshot bên ngoài transaction

**Từ MongoDB 5.0**, những read operation được hỗ trợ có thể sử dụng `readConcern:"snapshot"` mà **không cần mở multi-document transaction**.

| Operation ngoài transaction | Hỗ trợ snapshot? | Lưu ý |
|---|---|---|
| `find` | Có | Cursor có thể thuộc snapshot |
| `aggregate` | Có | Pipeline đọc thuộc phạm vi được phép |
| `distinct` | Có đối với **unsharded collections** | Không mở rộng tùy ý sang sharded collection |
| `count` command | Không | Dùng aggregation `$count` nếu cần snapshot |
| `insert`/`update`/`delete` ngoài transaction | Không | Snapshot read concern không biến write thành transaction |
| Command khác | Không mặc nhiên | Phải xem bảng hỗ trợ của version |

Không nên lấy câu “snapshot read có thể chạy ngoài transaction” để suy ra mọi MongoDB read command đều hỗ trợ.

### 4.3. Primary, secondary và sharding

Ngoài transaction, snapshot read được hỗ trợ trên primary và secondary trong các deployment phù hợp; sharded cluster có thể phối hợp snapshot đọc nhiều shard tại một thời điểm logic thống nhất.

**Không** suy luận rằng transaction ghi có thể chạy trên secondary chỉ vì snapshot read ngoài transaction có thể chọn secondary. Giao dịch đa document thông thường sử dụng read preference `primary`.

### 4.4. Capped collections thay đổi theo phiên bản

MongoDB 8.0 có thay đổi hỗ trợ `readConcern:"snapshot"` trên capped collections. Trong các phiên bản trước đó có hạn chế. Khi dùng capped collection hoặc hệ thống nhiều server versions, phải đối chiếu tài liệu đúng phiên bản.

### 4.5. Không dùng standalone như môi trường chứng minh mọi tính năng

Những ví dụ transaction/snapshot ở đây nên chạy trên replica set hoặc sharded cluster đã cấu hình phù hợp. Một standalone mongod hoặc môi trường managed bị hạn chế không nhất thiết hỗ trợ mọi thao tác được mô tả.

## 5. Chuẩn bị bộ dữ liệu thực hành

Mở `mongosh` kết nối tới replica set thử nghiệm, rồi chọn database riêng:

~~~javascript
use snapshot_read_lab
~~~

Tạo ba tài khoản:

~~~javascript
const demoAccounts = [
  {
    _id: "A",
    tenantId: "tenant-1",
    owner: "Lan",
    balance: NumberDecimal("500.00"),
    version: NumberInt(1)
  },
  {
    _id: "B",
    tenantId: "tenant-1",
    owner: "Minh",
    balance: NumberDecimal("300.00"),
    version: NumberInt(1)
  },
  {
    _id: "C",
    tenantId: "tenant-2",
    owner: "An",
    balance: NumberDecimal("200.00"),
    version: NumberInt(1)
  }
];

demoAccounts.forEach(account => {
  db.accounts.replaceOne(
    { _id: account._id },
    account,
    { upsert: true, writeConcern: { w: "majority" } }
  );
});

db.accounts.find().sort({ _id: 1 });
~~~

Tạo sáu đơn hàng:

~~~javascript
const demoOrders = [
  {
    _id: 101,
    tenantId: "tenant-1",
    customerId: "A",
    status: "PAID",
    amount: NumberDecimal("40.00"),
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: 102,
    tenantId: "tenant-1",
    customerId: "B",
    status: "PAID",
    amount: NumberDecimal("15.00"),
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: 103,
    tenantId: "tenant-1",
    customerId: "A",
    status: "NEW",
    amount: NumberDecimal("20.00"),
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: 104,
    tenantId: "tenant-1",
    customerId: "B",
    status: "PAID",
    amount: NumberDecimal("30.00"),
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: 105,
    tenantId: "tenant-2",
    customerId: "C",
    status: "NEW",
    amount: NumberDecimal("12.00"),
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: 106,
    tenantId: "tenant-2",
    customerId: "C",
    status: "PAID",
    amount: NumberDecimal("55.00"),
    createdAt: ISODate("2026-10-06T08:00:00Z")
  }
];

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true, writeConcern: { w: "majority" } }
  );
});

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created_id" }
);
~~~

Với collection mới và rỗng, có:

- **6 orders**: tenant-1 có bốn đơn, tenant-2 có hai đơn.
- Tenant-1 có **3 PAID**, 1 NEW; tổng đơn PAID tenant-1 là **85.00**.
- Ba accounts: A=500, B=300 và C=200.
- `amount`/`balance` dùng Decimal128.

`replaceOne(...,{upsert:true})` giúp nạp lại những ID mẫu nhưng **sẽ ghi đè dữ liệu thử nghiệm đã sửa** ở các ID đó. Không chạy trên collection production. Các kết quả kỳ vọng trong bài giả định bạn không thêm record khác và không có ghi đồng thời ngoài các thao tác được mô tả.

### 5.1. Vì sao nạp mẫu dùng majority write concern?

Snapshot read ngoài transaction quan sát dữ liệu majority-committed. Nếu vừa nạp document với write concern yếu hơn, snapshot mới chưa chắc đã thấy mọi dữ liệu mẫu vào thời điểm bạn đọc.

Lệnh ghi với `w:"majority"` giúp kết quả kiểm tra dễ dự đoán hơn, với điều kiện replica set đang có đủ thành viên lưu dữ liệu để xác nhận.

### 5.2. Kiểm tra thông thường

~~~javascript
db.accounts.find(
  {},
  { _id: 1, balance: 1 }
).sort({ _id: 1 });

db.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
}).sort({ createdAt: -1, _id: -1 });
~~~

Đơn PAID của tenant-1 có ID **104, 102, 101** theo thứ tự trên.

## 6. Một snapshot read ngoài transaction bằng find

Có thể đặt read concern trên cursor của mongosh:

~~~javascript
db.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.readConcern("snapshot")
.toArray();
~~~

Lệnh đọc này dùng một snapshot của dữ liệu majority-committed tại timestamp do MongoDB chọn theo cơ chế hỗ trợ.

### 6.1. Đọc một query không đồng nghĩa giữ snapshot cho query sau

Chạy:

~~~javascript
db.orders.find({ tenantId: "tenant-1" })
  .readConcern("snapshot")
  .toArray();

db.orders.find({ tenantId: "tenant-1" })
  .readConcern("snapshot")
  .toArray();
~~~

Nếu một write majority-committed ở giữa, hai command riêng có thể nhận **hai timestamp khác nhau**. Chỉ cùng read concern không đủ để ràng buộc chúng cùng thời điểm.

### 6.2. Cần phân biệt sự ổn định của một query và nhiều query

- Một find snapshot dùng góc nhìn tại snapshot của **query đó**.
- Hai find riêng biệt chưa chắc dùng cùng timestamp.
- Nhiều find trong **snapshot session** có thể dùng cùng timestamp.
- Những find bên trong **transaction snapshot** cũng thuộc cùng góc nhìn transaction.

### 6.3. Một find snapshot có tự khóa người ghi không?

Không cần xem snapshot read như write lock trên tất cả document đã đọc. Người khác vẫn có thể ghi dữ liệu mới. Snapshot read tiếp tục nhìn phiên bản cũ tại timestamp của nó, miễn lịch sử còn được giữ.

## 7. Một snapshot read ngoài transaction bằng aggregate

Ví dụ tổng hợp đơn PAID:

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "tenant-1",
        status: "PAID"
      }
    },
    {
      $group: {
        _id: null,
        count: { $sum: 1 },
        totalAmount: { $sum: "$amount" }
      }
    }
  ],
  {
    readConcern: { level: "snapshot" },
    maxTimeMS: 5000
  }
);
~~~

Với dữ liệu mẫu, `count = 3` và `totalAmount = 85.00`.

### 7.1. Tại sao chọn $count trong aggregation?

Command `aggregate` thuộc nhóm hỗ trợ snapshot ngoài transaction. Nếu muốn đếm:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-1" } },
    { $count: "total" }
  ],
  { readConcern: { level: "snapshot" } }
);
~~~

Lệnh này cho tổng document theo snapshot của command. `count` command độc lập không nằm trong danh sách snapshot operations ngoài transaction. Một số helper `countDocuments()` dựa trên aggregation, nhưng phạm vi hỗ trợ tùy API/driver; dùng aggregation trong bài này giúp minh họa rõ contract command được phép.

### 7.2. $count rỗng trả gì?

Với filter không khớp, pipeline:

~~~javascript
[
  { $match: { tenantId: "not-found" } },
  { $count: "total" }
]
~~~

có thể trả **mảng rỗng**, không tự sinh `{total:0}`. Tầng ứng dụng nên chuẩn hóa nếu API cần tổng bằng 0.

### 7.3. readConcern không thay đổi filter hay quyền

Snapshot không có chức năng tự giới hạn tenant. Nếu quên `tenantId` trong `$match`, query vẫn có thể đọc dữ liệu của tenant khác theo quyền database được cấp.

## 8. Snapshot session: nhiều lần đọc cùng thời điểm không cần transaction

Từ MongoDB 5.0, **snapshot session** có thể chia sẻ một timestamp cho nhiều read operation được hỗ trợ mà không cần mở multi-document transaction.

Trong mongosh:

~~~javascript
const s = db.getMongo().startSession({
  snapshot: true
});

const sdb = s.getDatabase("snapshot_read_lab");

try {
  const a = sdb.accounts.findOne({ _id: "A" });
  const b = sdb.accounts.findOne({ _id: "B" });

  printjson({
    balanceA: a.balance,
    balanceB: b.balance
  });
} finally {
  s.endSession();
}
~~~

Ở đây không có `startTransaction()`, `commitTransaction()` hay `abortTransaction()`. Session chỉ tạo phạm vi cho các read cùng snapshot.

### 8.1. Lần đọc đầu chọn timestamp

~~~text
startSession({snapshot:true})
            |
            v
Read #1 ---> Server chọn timestamp T và trả atClusterTime
            | Driver/shell giữ T
            v
Read #2 ---> Đọc tại T
            |
            v
Read #3 ---> Đọc tại T
            |
            v
endSession()
~~~

Timestamp không nhất thiết được chốt ngay tại lệnh `startSession()`. Nó được thiết lập khi một operation được hỗ trợ đầu tiên lấy snapshot.

### 8.2. Snapshot session có thể đọc nhiều collection

~~~javascript
const s = db.getMongo().startSession({ snapshot: true });
const d = s.getDatabase("snapshot_read_lab");

try {
  const accounts = d.accounts.find({
    tenantId: "tenant-1"
  }).toArray();

  const paid = d.orders.find({
    tenantId: "tenant-1",
    status: "PAID"
  }).toArray();

  printjson({
    accountsRead: accounts.length,
    paidOrdersRead: paid.length
  });
} finally {
  s.endSession();
}
~~~

Hai collection khác nhau nhưng các read vẫn thuộc **một timestamp** vì cùng snapshot session. Đây là khác biệt lớn so với chạy hai query riêng ở mức majority.

### 8.3. Snapshot session khác transaction

| Snapshot session ngoài transaction | Transaction snapshot |
|---|---|
| Dành cho các read được hỗ trợ | Có thể gồm các CRUD operations được phép, kể cả ghi |
| Không cung cấp atomic commit/abort nhiều write | Có commit/abort |
| Không cần mở transaction | Bắt buộc startTransaction |
| Cùng timestamp giữa nhiều read | Góc nhìn transaction được chốt theo cơ chế transaction |
| Hỗ trợ đọc trên secondary theo điều kiện | Transaction thông thường dùng primary |
| Có thể thấy `SnapshotTooOld` nếu giữ session quá lâu | Có transaction lifetime và giới hạn tài nguyên riêng |
| Không dùng để chuyển tiền nguyên tử | Có thể thực hiện chuyển tiền nhiều document nguyên tử |

### 8.4. Snapshot và causal consistency loại trừ nhau trong một session

Trong mongosh, `snapshot:true` và `causalConsistency:true` không được dùng cùng nhau.

~~~javascript
const good = db.getMongo().startSession({
  snapshot: true
});
good.endSession();
~~~

Không viết:

~~~javascript
// Không hợp lệ:
db.getMongo().startSession({
  snapshot: true,
  causalConsistency: true
});
~~~

Causal consistency và snapshot consistency giải quyết hai bài toán khác nhau. Causal consistency theo dõi quan hệ thứ tự giữa thao tác; snapshot cố định nhiều read ở cùng một thời điểm.

## 9. Thực hành có write xen vào giữa hai snapshot reads

Nạp lại `accounts` từ mục 5 để đảm bảo B=300 rồi chạy:

~~~javascript
const s = db.getMongo().startSession({
  snapshot: true
});

const d = s.getDatabase("snapshot_read_lab");

try {
  // Read đầu tiên chốt timestamp T.
  const aAtT = d.accounts.findOne({ _id: "A" });

  // Write này KHÔNG thuộc snapshot session.
  db.accounts.updateOne(
    { _id: "B" },
    {
      $set: {
        balance: NumberDecimal("350.00")
      }
    },
    { writeConcern: { w: "majority" } }
  );

  // Read tiếp vẫn dùng timestamp T.
  const bAtT = d.accounts.findOne({ _id: "B" });

  // Read thông thường ngoài session quan sát thời điểm mới.
  const bCurrent = db.accounts.findOne({ _id: "B" });

  printjson({
    aAtT: aAtT.balance,
    bAtT: bAtT.balance,
    bCurrent: bCurrent.balance
  });
} finally {
  s.endSession();
}
~~~

Trên dữ liệu mẫu không có ghi khác:

~~~javascript
{
  aAtT: NumberDecimal("500.00"),
  bAtT: NumberDecimal("300.00"),
  bCurrent: NumberDecimal("350.00")
}
~~~

**Giải thích:** Read A đầu tiên cố định snapshot ở thời điểm B vẫn bằng 300. Write bên ngoài sửa B thành 350. Read B trong session vẫn thấy giá trị ở snapshot cũ, trong khi read ngoài session có thể thấy giá trị mới.

Không dùng hai write riêng biệt như ví dụ này để triển khai nghiệp vụ chuyển tiền thực. Đây là bài kiểm tra **read consistency**, không phải hướng dẫn chuyển tiền.

Sau bài, nạp lại đúng account B hoặc toàn bộ `demoAccounts` để tiếp tục.

## 10. atClusterTime: chọn timestamp cho snapshot read ngoài transaction

Trong phạm vi ngoài transaction, snapshot read cho phép tùy chọn `atClusterTime`.

~~~javascript
db.runCommand({
  find: "orders",
  filter: { tenantId: "tenant-1" },
  readConcern: {
    level: "snapshot",
    atClusterTime: Timestamp(1760000000, 1)
  }
});
~~~

Giá trị timestamp ở trên **chỉ minh họa cú pháp**. Một thời điểm tùy chọn theo đồng hồ không bảo đảm có snapshot còn lưu. Ứng dụng phải dùng BSON Timestamp hợp lệ trong lịch sử snapshot của server.

### 10.1. Đọc timestamp từ response

Theo snapshot reads protocol, response `find`/`aggregate` có thể chứa `cursor.atClusterTime`. Ví dụ:

~~~javascript
const first = db.runCommand({
  find: "orders",
  filter: { tenantId: "tenant-1" },
  projection: { _id: 1, status: 1 },
  batchSize: 20,
  readConcern: { level: "snapshot" }
});

const t = first.cursor.atClusterTime;

printjson({
  items: first.cursor.firstBatch,
  timestamp: t
});
~~~

`t` có kiểu BSON Timestamp; nó không phải giá trị `createdAt` của một order.

### 10.2. Tái sử dụng timestamp cho aggregate khác

~~~javascript
const sameTime = db.runCommand({
  aggregate: "orders",
  pipeline: [
    { $match: { tenantId: "tenant-1" } },
    { $group: { _id: "$status", n: { $sum: 1 } } }
  ],
  cursor: {},
  readConcern: {
    level: "snapshot",
    atClusterTime: t
  },
  maxTimeMS: 5000
});

printjson(sameTime.cursor.firstBatch);
~~~

Hai operation được yêu cầu cùng timestamp T.

**Lưu ý:** Không tự gửi `atClusterTime` cùng `afterClusterTime`, và không dùng cơ chế này trong một causally consistent session có tùy chọn xung đột. Nếu không có nhu cầu tự điều khiển timestamp, snapshot session cho driver quản lý thường đơn giản và ít lỗi hơn.

### 10.3. Secondary chưa bắt kịp T

Nếu read được chuyển tới secondary mới chỉ áp dụng oplog tới T1 nhưng bạn yêu cầu `atClusterTime:T2`, server có thể chờ cho đến khi node có dữ liệu tại T2. `maxTimeMS` giúp giới hạn thời gian chờ/tính toán.

### 10.4. Timestamp quá cũ

Nếu T đã ngoài lịch sử WiredTiger đang giữ, MongoDB có thể báo `SnapshotTooOld`. Retry nguyên command với cùng timestamp đã quá cũ thường không sửa được; cần snapshot mới hoặc thiết kế lưu lịch sử khác.

## 11. Snapshot trong transaction: thiết lập ở cấp startTransaction

Một multi-document transaction cung cấp đơn vị commit/abort. Để các thao tác của transaction đọc theo snapshot, đặt read concern tại **lúc bắt đầu transaction**:

~~~javascript
const session = db.getMongo().startSession({
  readPreference: { mode: "primary" }
});

const txdb = session.getDatabase("snapshot_read_lab");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  const a = txdb.accounts.findOne({ _id: "A" });
  const b = txdb.accounts.findOne({ _id: "B" });

  printjson({
    balanceA: a.balance,
    balanceB: b.balance
  });

  session.commitTransaction();
} catch (e) {
  try { session.abortTransaction(); } catch (_) {}
  throw e;
} finally {
  session.endSession();
}
~~~

### 11.1. Không gắn read concern riêng cho từng read trong transaction

Sai về cách dùng:

~~~javascript
session.startTransaction();

// Không dùng readConcern cấp cursor thay cho transaction option:
txdb.accounts.find({ _id: "A" })
  .readConcern("snapshot");
~~~

Đúng:

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});
~~~

Read concern của transaction áp dụng cho những operation thuộc transaction, không phải một cấu hình ngẫu nhiên của từng query. Nếu collection/database có read concern riêng, transaction-level option có precedence theo quy tắc driver/server.

### 11.2. Read nhiều collection trong một transaction

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

const accounts = txdb.accounts.find({
  tenantId: "tenant-1"
}).toArray();

const orders = txdb.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
}).toArray();

session.commitTransaction();
~~~

Hai read thuộc cùng góc nhìn snapshot transaction, phù hợp báo cáo cần tính toán với các thao tác ghi khác cùng đơn vị transaction nếu cần.

### 11.3. startTransaction không tự chốt timestamp ngay lập tức

Trong mongosh, `startTransaction()` khởi tạo ngữ cảnh; transaction thực trên server bắt đầu khi operation đầu tiên được gửi. Không giả định snapshot timestamp luôn bằng thời gian đồng hồ ở câu lệnh `startTransaction` trước khi có read/write đầu tiên.

### 11.4. Chỉ một transaction đang mở trên một session

Không mở hai transaction đồng thời trong cùng `ClientSession`. Nếu muốn công việc song song, tổ chức session/transaction riêng theo quy tắc concurrency của driver và yêu cầu nghiệp vụ.

## 12. Write concern majority và bảo đảm snapshot transaction

Theo MongoDB Manual, read concern snapshot trong transaction mang bảo đảm đọc từ snapshot majority-committed khi transaction **commit với write concern majority**.

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});
~~~

So sánh:

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: 1 }
});
~~~

Cấu hình thứ hai không có đầy đủ bảo đảm majority-committed snapshot tương đương như cấu hình commit majority.

### 12.1. Không gắn write concern vào từng update trong transaction

Ví dụ không nên làm:

~~~javascript
txdb.accounts.updateOne(
  { _id: "A" },
  { $set: { owner: "Lan" } },
  { writeConcern: { w: "majority" } }
);
~~~

Nếu operation đang thuộc transaction, write concern của transaction được dùng ở **commit**. Đặt writeConcern riêng ở từng write có thể bị từ chối.

### 12.2. Commit có thể có kết quả chưa rõ

Nếu mạng ngắt sau khi client gửi commit, ứng dụng có thể không biết chắc transaction đã commit hay chưa. Cần xử lý error labels như `UnknownTransactionCommitResult`, `TransientTransactionError` và cơ chế retry của driver.

Không xem timeout là bằng chứng transaction chưa thực hiện; cũng không tự gửi lại một nghiệp vụ thanh toán khác không có idempotency.

## 13. Transaction có nhìn thấy write của chính nó không?

**Có.** Snapshot transaction giữ góc nhìn với các thay đổi bên ngoài, nhưng các thao tác ghi của **chính transaction** được nhìn thấy bởi các read tiếp theo trong cùng transaction.

Ví dụ chuyển 50 từ A sang B trong database thực hành:

~~~javascript
const s = db.getMongo().startSession({
  readPreference: { mode: "primary" }
});

const d = s.getDatabase("snapshot_read_lab");

try {
  s.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  d.accounts.updateOne(
    { _id: "A" },
    { $inc: { balance: NumberDecimal("-50.00") } }
  );

  d.accounts.updateOne(
    { _id: "B" },
    { $inc: { balance: NumberDecimal("50.00") } }
  );

  const a = d.accounts.findOne({ _id: "A" });
  const b = d.accounts.findOne({ _id: "B" });

  printjson({
    inTxA: a.balance,
    inTxB: b.balance
  });

  s.commitTransaction();
} catch (e) {
  try { s.abortTransaction(); } catch (_) {}
  throw e;
} finally {
  s.endSession();
}
~~~

Nếu trạng thái ban đầu A=500, B=300, read bên trong transaction sau hai update thấy A=450, B=350.

**Quan trọng:** Đoạn code **ghi dữ liệu thật trong database thực hành**. Nạp lại `demoAccounts` trước các bài sau. Trong production, cần thêm xác thực quyền chuyển, số dư, idempotency và xử lý transaction retry đầy đủ.

### 13.1. Snapshot không tự đưa các write mới bên ngoài vào transaction

Nếu một transaction khác update A sau timestamp snapshot, read trong transaction hiện tại có thể vẫn nhìn A cũ. Không dùng snapshot transaction khi yêu cầu là đọc “giá trị mới nhất tuyệt đối” mà không có chiến lược đồng bộ tương ứng.

### 13.2. Write conflict

Khi transaction dựa trên snapshot cũ rồi cố sửa document đã bị transaction hoặc write khác cập nhật, MongoDB có thể trả `WriteConflict` và abort transaction.

Ứng dụng phải retry theo transaction protocol và **đánh giá lại điều kiện nghiệp vụ**, không cố ghi đè mọi xung đột.

## 14. Snapshot isolation không bảo đảm serializable cho mọi invariant

Xét nghiệp vụ luôn phải có ít nhất một nhân viên trực:

~~~text
T0:
  Alice.onCall = true
  Bob.onCall   = true

Transaction T1 đọc cùng snapshot T0:
  thấy Bob đang trực
  -> cập nhật Alice.onCall = false

Transaction T2 đọc cùng snapshot T0:
  thấy Alice đang trực
  -> cập nhật Bob.onCall = false

Nếu hai write trên hai document không xung đột trực tiếp,
cả hai transaction có thể tạo trạng thái:
  Alice.onCall = false
  Bob.onCall   = false
~~~

Đây là tình huống thường gọi là *write skew*. Snapshot isolation bảo đảm nhiều read nhất quán về thời điểm, nhưng không tự ràng buộc mọi quy tắc xuyên document như một lịch serializable.

Các hướng thiết kế:

- Dùng một document điều phối chứa điều kiện cần bảo vệ, cập nhật nguyên tử.
- Dùng unique index/schema constraints nếu invariant biểu diễn được.
- Trong transaction, tạo một phép ghi có điều kiện khiến các transaction cạnh tranh xung đột trực tiếp.
- Sử dụng optimistic concurrency và version field.
- Kiểm tra lại điều kiện sau retry với dữ liệu mới.

**Không xem readConcern snapshot là giải pháp mặc định cho mọi điều kiện toàn cục hoặc race condition.**

## 15. Causal consistency khác snapshot session thế nào?

Causal consistency quan tâm đến mối quan hệ nhân quả giữa các thao tác như “đọc thấy write trước đó của mình”. Snapshot session quan tâm đến đọc **cùng một timestamp**, dù có nhiều write mới ở ngoài.

Ví dụ:

~~~text
Causal session:
  write X xong
  read Y sau X -> bảo đảm thứ tự nhân quả theo điều kiện hỗ trợ

Snapshot session:
  read X tại T
  read Y tại T
  write mới ngoài session sau T không tự xuất hiện
~~~

Hai khái niệm không thay thế nhau.

### 15.1. Không truyền atClusterTime và afterClusterTime xung đột

`afterClusterTime` liên quan causal consistency, còn `atClusterTime` yêu cầu đọc đúng snapshot timestamp. Không gộp hai thông số này trái quy tắc command.

Để dùng `atClusterTime` chủ động, cần có session/command setup phù hợp, không tự bật causal consistency trong cùng snapshot session rồi thêm atClusterTime.

### 15.2. Causal consistency có thể phù hợp hơn khi nào?

Nếu ứng dụng chỉ muốn đọc thấy kết quả của những write đã thực hiện trước đó trong cùng luồng, causal consistency/majority concern có thể phù hợp hơn việc cố định snapshot cũ.

Nếu ứng dụng muốn báo cáo qua nhiều collection ở cùng thời điểm, snapshot session rõ nghĩa hơn.

## 16. Phân trang nhất quán: total và items

Giả sử API:

~~~text
GET /orders?tenantId=tenant-1&status=PAID&page=1&pageSize=2
~~~

Cần:

- `items`: 2 đơn đầu theo thời gian.
- `total`: tổng số đơn thỏa filter.
- `totalPages`: số trang dựa trên total.

Hai operation thông thường:

~~~javascript
const filter = {
  tenantId: "tenant-1",
  status: "PAID"
};

const total = db.orders.countDocuments(filter);

const items = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .limit(2)
  .toArray();
~~~

không tự có cùng timestamp. Một insert/update giữa hai lệnh có thể làm total và items khác thời điểm.

### 16.1. Dùng snapshot session cho items và count

~~~javascript
const s = db.getMongo().startSession({ snapshot: true });
const d = s.getDatabase("snapshot_read_lab");

try {
  const filter = {
    tenantId: "tenant-1",
    status: "PAID"
  };

  const items = d.orders.find(filter)
    .sort({ createdAt: -1, _id: -1 })
    .limit(2)
    .toArray();

  const counted = d.orders.aggregate([
    { $match: filter },
    { $count: "total" }
  ]).toArray();

  const total = counted.length === 0
    ? 0
    : counted[0].total;

  printjson({
    ids: items.map(x => x._id),
    total: total,
    totalPages: Math.ceil(total / 2)
  });
} finally {
  s.endSession();
}
~~~

Với dữ liệu mẫu, IDs 104, 102 và total=3.

**Điểm then chốt:** Cả `find` và `aggregate` đều được chạy thông qua `d` của **cùng snapshot session**. Nếu một thao tác lỡ dùng `db.orders` thông thường, nó sẽ không tự chia sẻ snapshot session.

### 16.2. Vì sao $facet cũng là một lựa chọn?

Một aggregation duy nhất có thể trả data và count:

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "tenant-1",
        status: "PAID"
      }
    },
    {
      $facet: {
        data: [
          { $sort: { createdAt: -1, _id: -1 } },
          { $limit: 2 }
        ],
        metadata: [
          { $count: "total" }
        ]
      }
    }
  ],
  {
    readConcern: { level: "snapshot" }
  }
);
~~~

Cách này dùng **một command** có snapshot read concern, nhưng nhánh count vẫn phải xét toàn bộ tập phù hợp. `$facet` có giới hạn bộ nhớ và kích thước BSON output riêng. Không coi nó là cách đếm miễn phí.

### 16.3. Phân trang qua nhiều HTTP request

Khi người dùng tải trang 1 rồi quay lại trang 2 sau vài phút, một snapshot session không nên được giữ vô hạn ở server chỉ để làm giao diện.

Có thể dùng snapshot timestamp `atClusterTime` trong một khoảng ngắn nếu history còn lưu, nhưng token phải có chính sách hết hạn. Nếu yêu cầu không bắt buộc total cố định, keyset pagination với sort ổn định và `hasNext` thường đơn giản hơn.

## 17. Snapshot time, keyset và offset pagination

Với filter/sort:

~~~javascript
const filter = {
  tenantId: "tenant-1",
  status: "PAID"
};

const sort = { createdAt: -1, _id: -1 };
~~~

Nếu muốn phân trang ổn định khi nhiều document có cùng `createdAt`, cần tie-breaker như `_id`.

### 17.1. Offset không giải quyết việc thay đổi dữ liệu

~~~javascript
db.orders.find(filter)
  .sort(sort)
  .skip(20)
  .limit(10);
~~~

`skip` có thể tốn kém ở trang sâu và vị trí bị dịch khi dữ liệu thêm/xóa. Snapshot có thể cố định tập dữ liệu ở một timestamp, nhưng không biến skip sâu thành phép nhảy O(1).

### 17.2. Keyset cũng không tự giữ snapshot

Keyset pagination dùng khóa cuối trang trước:

~~~javascript
{
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}
~~~

giúp tiếp tục theo thứ tự mà không skip sâu, nhưng các page query ở thời điểm khác nhau vẫn có thể nhìn dữ liệu thay đổi. Nếu cần các page phản ánh cùng tập cố định, ngoài keyset còn phải quản lý snapshot hoặc quy tắc sản phẩm.

### 17.3. Thiết kế token có timestamp

Một token có thể chứa hoặc tham chiếu:

~~~json
{
  "after": {
    "createdAt": "2026-10-02T08:00:00Z",
    "_id": 102
  },
  "snapshot": "<opaque-reference>",
  "pageSize": 20
}
~~~

Đây là cấu trúc minh họa ở tầng API, **không phải** BSON Timestamp đã mã hóa sẵn. Token cần được ký/xác thực và gắn với tenant, filter, sort, thời hạn. Khi snapshot hết history, không thể tiếp tục dùng timestamp cũ.

## 18. Giới hạn snapshot history: minSnapshotHistoryWindowInSeconds

Storage engine cần giữ các phiên bản cũ để phục vụ snapshot timestamp. Tham số:

~~~text
minSnapshotHistoryWindowInSeconds
~~~

liên quan khoảng thời gian lịch sử snapshot tối thiểu được lưu.

Tài liệu MongoDB về long-running snapshot queries dùng giá trị mặc định **300 giây** cho WiredTiger history window trong ngữ cảnh đó. Tuy nhiên, cấu hình thực tế có thể khác theo phiên bản, topology và dịch vụ managed.

### 18.1. SnapshotTooOld xảy ra khi nào?

~~~text
T0: read đầu tiên chốt snapshot T0
    |
    | nhiều write mới + thời gian trôi
    |
T1: các phiên bản cần cho T0 không còn được giữ
    |
    v
    SnapshotTooOld
~~~

Một query/session snapshot kéo dài vượt cửa sổ snapshot khả dụng có thể thất bại.

### 18.2. Không có bảo đảm “chạy chính xác 300 giây”

Không nên diễn giải mốc mặc định thành deadline cứng bảo đảm mọi read kéo dài đúng 300 giây rồi mới lỗi. Timestamp được chọn, lịch sử thực giữ lại, resource pressure, phiên bản server và cấu hình đều có tác động.

### 18.3. Xử lý khi timestamp đã hết hạn

1. Đừng retry cùng timestamp cũ liên tục.
2. Phân loại đây là snapshot expired thay vì kết quả rỗng.
3. Nếu UX chấp nhận, tạo snapshot mới rồi bắt đầu lại báo cáo.
4. Nếu phải giữ lịch sử lâu dài, dùng materialized report, audit/versioning hoặc backup/PITR thích hợp.
5. Đo query latency và tối ưu để giảm thời gian giữ snapshot.

### 18.4. Có nên tăng history window?

Tăng thời gian giữ lịch sử có thể tăng chi phí lưu nhiều phiên bản, I/O và storage. Đây là quyết định vận hành cần DBA đánh giá theo workload, không phải nút sửa đơn giản cho mọi báo cáo chậm.

## 19. Snapshot trên secondary và dữ liệu trễ

Snapshot read ngoài transaction có thể chạy trên secondary được hỗ trợ. Lợi ích là chuyển một phần read workload khỏi primary, nhưng cần hiểu độ tươi.

~~~text
Primary: đã majority-commit tới T2
Secondary: mới áp dụng tới T1

Snapshot không ép thời điểm:
  có thể chọn snapshot majority-committed cũ hơn T2

Snapshot yêu cầu atClusterTime=T2:
  secondary phải chờ bắt kịp T2
  hoặc query timeout nếu không đạt trong deadline
~~~

### 19.1. Dữ liệu cũ không có nghĩa snapshot sai

Nếu snapshot được lấy tại T1 và dữ liệu đồng nhất ở T1, nó vẫn đúng về tính nhất quán. Nhưng API cần biết người dùng có chấp nhận độ trễ so với primary hay không.

### 19.2. Transaction ghi không chuyển sang secondary được

Read preference secondary cho snapshot ngoài transaction không phải con đường để gửi update/commit transaction tới secondary trong lúc không có primary.

### 19.3. Đọc lâu vẫn tốn tài nguyên secondary

Một báo cáo lớn có thể tạo áp lực CPU/RAM/disk trên secondary, ảnh hưởng replication. Không coi “read trên secondary” là miễn phí hay không bao giờ tác động tới workload ghi.

## 20. Snapshot trong sharded cluster

Trong sharded cluster, dữ liệu phân phối qua nhiều shard. Một báo cáo đọc cả shard A và shard B cần xác định có muốn chúng phản ánh **cùng timestamp** hay không.

### 20.1. Tính nhất quán across shards

`readConcern:"snapshot"` cho phép đọc dữ liệu majority-committed theo một góc nhìn đồng bộ across shards trong trường hợp hỗ trợ.

### 20.2. Transaction majority khác snapshot

Trong transaction ở sharded cluster, `readConcern:"majority"` **không bảo đảm** mọi shard được quan sát tại một snapshot timestamp giống nhau. Khi nghiệp vụ yêu cầu một thời điểm đồng bộ trên mọi shard, dùng `readConcern:"snapshot"` trong transaction.

### 20.3. Distinct trên sharded collection

Ngoài transaction, `distinct` với snapshot bị hạn chế ở **unsharded collection**. Trong transaction, `distinct` command trên sharded collection cũng có giới hạn.

Để lấy giá trị khác nhau bằng aggregation:

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$status" } },
  { $sort: { _id: 1 } }
]);
~~~

Khi chạy thực tế trên sharded cluster, cần kiểm tra quyền, dữ liệu, index và quy tắc stage tương ứng.

### 20.4. Chờ shard bắt kịp timestamp

Một truy vấn snapshot phối hợp nhiều shard có thể phải chờ các shard đáp ứng timestamp, do đó latency không chỉ phụ thuộc số document trả về.

## 21. Read concern snapshot không phải backup hoặc time travel vô hạn

| Mục tiêu | Giải pháp chính |
|---|---|
| Một query dài cần cùng góc nhìn | Snapshot read ngoài transaction |
| Nhiều query ngắn cần cùng thời điểm | Snapshot session |
| Nhiều write phải commit/abort nguyên tử | Transaction |
| Nhiều collection/shards cần snapshot transaction | Transaction với readConcern snapshot |
| Phục hồi dữ liệu sau xóa nhầm | Backup/restore hoặc PITR được hỗ trợ |
| Lưu lịch sử dữ liệu tháng trước | Event log, versioned documents, materialized snapshots |
| API cần xem lại kết quả sau nhiều giờ | Lưu báo cáo hoặc tập kết quả theo hợp đồng, không dựa vào history window |
| Báo cáo định kỳ có thể chạy lại | Có thể materialize output vào collection riêng |

BSON Timestamp của `atClusterTime` chỉ có ý nghĩa khi lịch sử phiên bản ở thời điểm đó còn khả dụng. Nó không phải một khóa mở cổng quay lại mọi trạng thái database trong nhiều tháng.

## 22. Hiệu năng và chi phí vận hành

### 22.1. Read concern không thay index

Query:

~~~javascript
db.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
}).readConcern("snapshot");
~~~

vẫn cần index/filter phù hợp để chạy hiệu quả trên collection lớn. Snapshot không khiến mọi collection scan tự biến thành index scan.

### 22.2. Match và project đúng phạm vi

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-1", status: "PAID" } },
    { $sort: { createdAt: -1, _id: -1 } },
    { $limit: 20 },
    { $project: { _id: 1, status: 1, amount: 1 } }
  ],
  {
    readConcern: { level: "snapshot" },
    maxTimeMS: 5000
  }
);
~~~

Một kết quả nhỏ không nhất thiết có nghĩa chi phí thấp, nhưng lọc đúng và index phù hợp thường giúp giảm thời gian giữ snapshot.

### 22.3. Những giới hạn khác vẫn còn

- BSON document output tối đa 16 MiB.
- Một số blocking stage cần RAM/spill.
- Transaction có lifetime limit và write-conflict constraints.
- Cursor trả dữ liệu theo batch.
- Secondary có thể bị lag.
- Snapshot timestamp có history-window limit.

Bật snapshot không vô hiệu hóa các giới hạn này.

### 22.4. Đo và giám sát

Theo dõi query latency, `totalDocsExamined`/`totalKeysExamined`, replication lag, `SnapshotTooOld`, transaction aborts, memory/I/O và độ trễ end-to-end của API.

Không chỉ đo một lệnh trên vài document mẫu rồi kết luận về tải hàng triệu bản ghi.

## 23. MongoDB Java Sync Driver: snapshot session ngoài transaction

Java Driver hỗ trợ `ClientSessionOptions.builder().snapshot(true)` từ các phiên bản driver tương thích với MongoDB 5.0+.

Ví dụ giả định `client` kiểu `MongoClient` đã kết nối đúng replica set:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

MongoDatabase database =
    client.getDatabase("snapshot_read_lab");

MongoCollection<Document> orders =
    database.getCollection("orders");

ClientSessionOptions sessionOptions =
    ClientSessionOptions.builder()
        .snapshot(true)
        .build();

try (ClientSession session =
         client.startSession(sessionOptions)) {

    List<Document> items = orders.find(
            session,
            Filters.and(
                Filters.eq("tenantId", "tenant-1"),
                Filters.eq("status", "PAID")
            )
        )
        .limit(2)
        .into(new ArrayList<>());

    List<Document> countRows = orders.aggregate(
            session,
            List.of(
                Aggregates.match(
                    Filters.and(
                        Filters.eq("tenantId", "tenant-1"),
                        Filters.eq("status", "PAID")
                    )
                ),
                Aggregates.count("total")
            )
        )
        .into(new ArrayList<>());

    long total = countRows.isEmpty()
        ? 0
        : ((Number) countRows.get(0).get("total")).longValue();

    System.out.println("items=" + items.size());
    System.out.println("total=" + total);
}
~~~

**Quan trọng:** Phải truyền `session` vào **từng** read, ví dụ `orders.find(session,...)` và `orders.aggregate(session,...)`. Một query vô tình bỏ session không thuộc cùng snapshot.

### 23.1. Đọc tuần tự trên cùng session

`ClientSession` không được dùng đồng thời trên nhiều thread. Với nhiều query trong một snapshot session, hãy tổ chức việc đọc tuần tự hoặc thiết kế cơ chế khác theo driver specification.

### 23.2. Không startTransaction trên snapshot session

Một Java session tạo bằng `snapshot(true)` dành cho snapshot reads ngoài transaction. Driver không cho dùng nó như transaction session bằng cách gọi `startTransaction()`. Hãy tạo session thông thường nếu cần multi-document transaction.

## 24. Java Sync Driver: transaction snapshot

Trong Java, dùng `TransactionOptions` để cấu hình read concern ở cấp transaction:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> accounts =
    client.getDatabase("snapshot_read_lab")
        .getCollection("accounts");

TransactionOptions txOptions =
    TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();

try (ClientSession session = client.startSession()) {
    session.startTransaction(txOptions);

    try {
        Document a = accounts.find(
            session,
            new Document("_id", "A")
        ).first();

        Document b = accounts.find(
            session,
            new Document("_id", "B")
        ).first();

        System.out.println(a);
        System.out.println(b);

        session.commitTransaction();
    } catch (Exception e) {
        try {
            session.abortTransaction();
        } catch (Exception ignored) {
            // Có thể transaction đã kết thúc.
        }
        throw e;
    }
}
~~~

Đoạn này minh họa cú pháp, không phải một chương trình Java độc lập có credentials hoặc khởi tạo MongoClient. Trong production cần xử lý transaction retry theo error labels của driver.

### 24.1. Phân biệt hai cách tạo session

| Cách tạo | Mục tiêu |
|---|---|
| `client.startSession(ClientSessionOptions.builder().snapshot(true).build())` | Nhiều read snapshot **ngoài transaction** |
| `client.startSession()` rồi `session.startTransaction(txOptions)` | Transaction có read concern snapshot và write concern majority |

Không trộn hai cách vào một session.

### 24.2. Read concern ở collection không thay transaction-level concern

Bên ngoài transaction có thể cấu hình:

~~~java
MongoCollection<Document> snapshotOrders =
    orders.withReadConcern(ReadConcern.SNAPSHOT);
~~~

Nhưng khi vào transaction, read concern được chọn theo transaction options. Để trình bày rõ yêu cầu nghiệp vụ, đừng dựa vào việc collection vốn đã có read concern rồi bỏ qua cấu hình transaction.

## 25. Mongosh: phiên đọc tương tác và các giới hạn

### 25.1. Session trong mongosh

~~~javascript
const s = db.getMongo().startSession({
  snapshot: true
});

const d = s.getDatabase("snapshot_read_lab");

try {
  const first = d.orders.find({
    status: "PAID"
  }).toArray();

  const second = d.accounts.find({
    tenantId: "tenant-1"
  }).toArray();

  printjson({
    firstCount: first.length,
    secondCount: second.length
  });
} finally {
  s.endSession();
}
~~~

### 25.2. Một số lỗi do thiếu endSession

Không đóng session khi request đã kết thúc có thể làm rò rỉ tài nguyên hoặc kéo dài các ngữ cảnh đọc. Dùng `try/finally` để bảo đảm `endSession()` được gọi.

### 25.3. Session không phải một đối tượng có thể chia sẻ tùy ý

Không truyền cùng session sang các worker thread chạy đồng thời hoặc lưu trong cache toàn ứng dụng để mọi người dùng dùng chung. Session chứa ngữ cảnh timestamp/transaction và cần ranh giới rõ ràng.

## 26. MongoDB Compass

MongoDB Compass hữu ích để quan sát collection và chạy aggregation, nhưng các tùy chọn session, read concern và `atClusterTime` có thể không được expose đầy đủ giống mongosh hoặc driver ở mọi phiên bản.

Quy trình thực hành:

1. Kết nối Compass vào replica set/sharded cluster thử nghiệm.
2. Mở `snapshot_read_lab.orders`.
3. Trong tab **Aggregations**, thử `$match` + `$count` để tính tổng PAID.
4. Quan sát kết quả và đối chiếu với mongosh chạy `readConcern:"snapshot"`.
5. Nếu Compass cho cấu hình read concern, kiểm tra chính xác options được gửi.
6. Dùng mongosh để thực hành snapshot session, transaction hoặc `atClusterTime` khi UI không hỗ trợ.
7. Không xem việc hai lần làm mới Compass trả cùng dữ liệu là bằng chứng chúng dùng cùng snapshot.

Một pipeline chạy trong Compass không tự trở thành multi-document transaction chỉ vì có các stage `$match` hoặc `$group`.

## 27. Lỗi và ngộ nhận thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai majority read khác kết quả | Không cùng timestamp | Snapshot session hoặc cùng `atClusterTime` |
| Hai lệnh `readConcern:snapshot` khác kết quả | Chạy độc lập, có thể chọn snapshot khác | Gắn phạm vi session/timestamp |
| Snapshot thấy giá trị cũ | Đúng theo timestamp T | Dùng snapshot mới nếu cần độ tươi |
| Cần hai update nguyên tử nhưng chỉ bật snapshot | Nhầm read consistency với write atomicity | Transaction hoặc atomic data model |
| `count` command không hỗ trợ snapshot ngoài transaction | Không thuộc danh sách lệnh cho phép | Dùng aggregation `$count` |
| `distinct` trên sharded collection lỗi | Giới hạn command | Xem `$group`/cách khác |
| MongoDB 4.4 từ chối snapshot ngoài transaction | Tính năng bắt đầu 5.0 | Dùng transaction hoặc nâng cấp có kế hoạch |
| Snapshot session đi kèm causalConsistency:true | Mode loại trừ nhau | Chọn đúng loại session |
| atClusterTime truyền ISODate | Sai kiểu và ý nghĩa timestamp | Dùng BSON Timestamp thực |
| Secondary bị lag so với atClusterTime | Node chưa bắt kịp T | Chờ/timeout hoặc chọn primary phù hợp |
| `SnapshotTooOld` | Timestamp đã ngoài history | Đọc snapshot mới, không retry T cũ vô hạn |
| Transaction đọc stale document | Snapshot không tự lấy write mới ngoài transaction | Đánh giá lại sau transaction, dùng lock khi cần |
| Transaction abort do write conflict | Cập nhật đồng thời không tương thích | Retry đúng transaction protocol |
| Transaction snapshot commit w:1 | Thiếu đầy đủ bảo đảm majority-committed snapshot | Commit majority |
| API total khác items | Filter/tenant/session khác hoặc T khác | Cùng filter và snapshot |
| Transaction giữ nhiều phút | Lifetime và history/tài nguyên | Rút ngắn, thiết kế báo cáo riêng |
| Snapshot trên secondary chậm | Lag/I/O/query plan | Đo metrics, index và khả năng node |
| Có snapshot nhưng dữ liệu nghiệp vụ vẫn trung gian | Các write nguồn không nguyên tử | Dùng transaction cho write workflow |
| Snapshot isolation vẫn cho write skew | Không bảo đảm mọi invariant serializable | Atomic constraint/version/coordination |
| Thay read concern làm query nhanh hơn | Read concern không tối ưu filter/index | Tối ưu query/index |
| Dùng atClusterTime để đọc dữ liệu năm trước | Không còn version trong history | Backup/PITR/materialized history |

## 28. Bài thực hành

Các bài dùng database `snapshot_read_lab`. Bài có write cần chạy trên hệ thống thử nghiệm và có thể phải nạp lại dữ liệu mục 5.

### Bài 1. Phân biệt các mức read concern

Giải thích vì sao hai read ở mức majority có thể phản ánh hai thời điểm khác nhau, và khi nào cần snapshot session thay vì majority.

### Bài 2. Snapshot cho một find

~~~javascript
db.orders.find({
  tenantId: "tenant-1",
  status: "PAID"
})
.readConcern("snapshot")
.sort({ createdAt: -1, _id: -1 });
~~~

**Kỳ vọng ban đầu:** 104, 102, 101. Lệnh này tự giữ timestamp cho lần chạy thứ hai sau vài giây không?

### Bài 3. Đếm bằng aggregation snapshot

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-1", status: "PAID" } },
    { $count: "total" }
  ],
  { readConcern: { level: "snapshot" } }
);
~~~

**Kỳ vọng:** total = 3. Vì sao không dùng `count` command trực tiếp với snapshot read concern ngoài transaction?

### Bài 4. Hai read trong snapshot session

~~~javascript
const s = db.getMongo().startSession({ snapshot: true });
const d = s.getDatabase("snapshot_read_lab");

try {
  const a = d.accounts.findOne({ _id: "A" });
  const b = d.accounts.findOne({ _id: "B" });
  printjson({ a: a.balance, b: b.balance });
} finally {
  s.endSession();
}
~~~

Cả hai read theo timestamp nào? Timestamp chốt lúc tạo session hay read đầu tiên?

### Bài 5. Write xen vào

Dùng ví dụ mục 9, đọc A trong snapshot, sửa B ngoài session rồi đọc B trong snapshot.

**Kỳ vọng:** Read snapshot B vẫn thấy 300, read bình thường sau write thấy 350 khi điều kiện phù hợp. Giải thích vì sao đây không phải rollback.

### Bài 6. Trong transaction đặt read concern ở đâu?

Viết lại đoạn sau cho đúng:

~~~javascript
session.startTransaction();
txdb.accounts.find({ _id: "A" }).readConcern("snapshot");
~~~

**Gợi ý:** Đặt `readConcern:{level:"snapshot"}` trong `startTransaction({...})`.

### Bài 7. Read-your-own-writes

Trong transaction snapshot, cập nhật A giảm 50 rồi đọc lại A. Vì sao read trong transaction thấy giá trị mới do chính transaction ghi?

### Bài 8. Write concern majority

Giải thích vì sao transaction snapshot commit `w:1` không có cùng bảo đảm majority-committed snapshot như commit `w:"majority"`.

### Bài 9. atClusterTime

Chạy command `find` snapshot, lấy `first.cursor.atClusterTime` và truyền vào command `aggregate` snapshot tiếp theo.

**Hỏi:** Vì sao không truyền ISODate tùy ý vào `atClusterTime`?

### Bài 10. SnapshotTooOld

Một token API giữ timestamp snapshot của người dùng từ nhiều giờ trước, nhưng server đã không còn version cũ.

**Hỏi:** Nên xử lý lỗi thế nào? Vì sao retry mãi cùng T không giúp?

### Bài 11. Secondary lag

Primary đã tới T2, secondary mới tới T1. Khi yêu cầu snapshot tại T2 trên secondary, server có thể phải chờ gì? `maxTimeMS` ảnh hưởng ra sao?

### Bài 12. Sharded cluster

Vì sao read concern `majority` trong transaction sharded không phải lựa chọn tương đương `snapshot` khi cần một góc nhìn đồng bộ across shards?

### Bài 13. Phân trang và count

Dùng snapshot session để lấy top 2 đơn PAID và tính total bằng aggregation `$count`.

**Kỳ vọng:** items có 104/102; total = 3. Tại sao cả hai câu lệnh phải dùng cùng session object?

### Bài 14. Long-running report

Một báo cáo mất 10 phút và liên tục gặp `SnapshotTooOld`.

**Yêu cầu:** Đề xuất tối ưu filter/index, giảm dữ liệu, chạy báo cáo gọn hơn hoặc materialize, thay vì tự tăng history window vô hạn.

### Bài 15. Write skew

Hai transaction cùng đọc Alice/Bob đang trực, mỗi transaction sửa một người về off-duty.

**Hỏi:** Vì sao snapshot chưa đủ để giữ invariant “còn ít nhất một người trực”? Đề xuất document điều phối có version hoặc conditional update.

### Bài 16. Chọn công cụ

| Nhu cầu | Lựa chọn |
|---|---|
| Một query thống kê dài cần dữ liệu nhất quán | Snapshot read ngoài transaction |
| Nhiều query liên quan, không ghi | Snapshot session |
| Nhiều update phải commit cùng nhau | Multi-document transaction |
| Read + write trong transaction trên nhiều shard | Transaction read concern snapshot |
| Đọc dữ liệu vừa ghi trong chuỗi request | Xem causal consistency/majority và read preference phù hợp |
| Bản lưu báo cáo cần mở lại sau một năm | Materialized report/backup/history, không dùng snapshot window |
| List lớn chỉ cần nút “Tải thêm” | Keyset pagination, có thể không cần exact snapshot count |

## 29. Checklist triển khai production

- [ ] Biết rõ MongoDB server/driver version và loại cluster.
- [ ] Xác định yêu cầu là **một command**, **nhiều read**, hay **nhiều write**.
- [ ] Chỉ dùng snapshot ngoài transaction cho lệnh được hỗ trợ.
- [ ] Nếu dùng snapshot session, không bật causalConsistency trong cùng session.
- [ ] Mọi read muốn chia sẻ snapshot đều truyền cùng session.
- [ ] Nếu dùng atClusterTime, truyền BSON Timestamp hợp lệ và xử lý hết hạn.
- [ ] Trong transaction, read concern ở cấp transaction.
- [ ] Transaction cần majority-committed snapshot thì commit với w:majority.
- [ ] Không đặt writeConcern cho từng write trong transaction.
- [ ] Hiểu snapshot transaction có thể đọc stale data từ bên ngoài.
- [ ] Không kỳ vọng snapshot bảo vệ mọi invariant chống write skew.
- [ ] Có index cho filter/sort và giới hạn số document trả về.
- [ ] Có maxTimeMS/deadline và xử lý lỗi khác với kết quả rỗng.
- [ ] Có giám sát SnapshotTooOld, transaction aborts và replication lag.
- [ ] Không giữ session/transaction mở quá lâu.
- [ ] Không coi read secondary là dữ liệu mới nhất hay có quyền ghi.
- [ ] API total/items dùng cùng filter, tenant, sort và snapshot nếu bắt buộc.
- [ ] Có chính sách hết hạn snapshot trong pagination/report.
- [ ] Không dùng snapshot như backup hoặc time travel vô hạn.
- [ ] Các write nghiệp vụ quan trọng có idempotency/transaction phù hợp.

## 30. Tổng kết

Snapshot read là công cụ quan trọng của MongoDB để một query hoặc một nhóm query quan sát **cùng một phiên bản dữ liệu tại một thời điểm logic**.

- **Bên ngoài transaction, từ MongoDB 5.0:** `find`, `aggregate` và `distinct` trên unsharded collection được hỗ trợ; nhiều read cần cùng timestamp thì dùng `snapshot:true` session hoặc `atClusterTime` có kiểm soát.
- **Bên trong transaction:** đặt `readConcern:{level:"snapshot"}` ở cấp `startTransaction`; commit với write concern majority khi cần bảo đảm đọc từ majority-committed snapshot.
- **Snapshot session không phải transaction:** nó không làm các write riêng lẻ nguyên tử, không có commit/abort và không được dùng như transaction ghi.
- **Snapshot không phải dữ liệu mới nhất:** một góc nhìn cố định có thể cũ, đặc biệt khi secondary lag hoặc dữ liệu thay đổi sau timestamp.
- **Snapshot không tồn tại vô hạn:** thời gian giữ lịch sử hữu hạn, có thể gặp `SnapshotTooOld`.
- **Ứng dụng vẫn phải thiết kế đúng:** filter/authorization, index, pagination, transaction retry, invariant chống write skew và báo cáo dài hạn là những vấn đề riêng.

Khi xác định rõ phạm vi **một lệnh, một snapshot session hay một transaction**, bạn có thể chọn snapshot read đúng nhu cầu nhất quán, giảm các báo cáo lệch thời điểm và tránh chi phí không cần thiết của những transaction kéo dài.

## Tài liệu tham khảo chính thức

- [MongoDB Manual — Read Concern snapshot](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Perform Long-Running Snapshot Queries](https://www.mongodb.com/docs/manual/tutorial/long-running-queries/)
- [MongoDB Manual — Mongo.startSession](https://www.mongodb.com/docs/manual/reference/method/mongo.startsession/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver — Configure Operations on Replica Sets](https://www.mongodb.com/docs/drivers/java/sync/current/crud/read-write-config/)
