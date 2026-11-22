# Tính nguyên tử trên một document và giới hạn với nhiều document trong MongoDB

## 1. Nguyên tử là gì, và tại sao ranh giới document quan trọng?

Trong một hệ thống có nhiều người dùng hoặc nhiều service cùng ghi dữ liệu, hai yêu cầu thường xuất hiện cùng lúc:

- Một đơn hàng không được có **status = "paid"** nhưng **paidAt** vẫn rỗng do chỉ mới cập nhật một nửa các trường.
- Một khách hàng không được rút nhiều tiền hơn số dư, kể cả khi có hai yêu cầu rút tiền đến gần như đồng thời.

MongoDB có đặc tính nền tảng: **một thao tác ghi lên một document là nguyên tử**, ngay cả khi thao tác ấy sửa nhiều trường hoặc nhiều phần tử trong document. Tuy nhiên, **tính nguyên tử của một document không tự mở rộng thành tính nguyên tử của nhiều document**.

Ví dụ:

~~~text
Document A: một Order
   status: "draft"
   paidAt: null
   paymentReference: null

Một updateOne thay đổi cả ba trường:
   status: "paid"
   paidAt: một BSON Date
   paymentReference: "pay-001"

=> Một thao tác ghi trên một document:
   không có trạng thái ghi trung gian "chỉ mới sửa một trường"
   hiển thị như một kết quả ghi nửa chừng.
~~~

Nhưng với hai document ví:

~~~text
Wallet A: balance = 100
Wallet B: balance =  40

Chuyển 30 từ A sang B:
  1) A -= 30
  2) B += 30

Hai updateOne độc lập:
  sau bước 1: A=70, B=40 (tổng chỉ còn 110)
  sau bước 2: A=70, B=70 (tổng trở lại 140)
~~~

Mỗi bước có thể nguyên tử **riêng**, nhưng nếu chương trình lỗi sau bước 1 hoặc một request khác đọc ở khoảng giữa, hệ thống có thể quan sát trạng thái **chuyển tiền chưa hoàn tất**. Để có bảo đảm all-or-nothing xuyên hai ví, cần thiết kế transaction hoặc một cơ chế nghiệp vụ khác phù hợp.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích đúng **ranh giới atomicity một document** của MongoDB.
2. Viết **$set**, **$inc**, **$unset** và cập nhật nhiều field trong **một** updateOne.
3. Tránh **lost update** bằng toán tử cập nhật, filter có điều kiện và optimistic concurrency control.
4. Dùng **findOneAndUpdate** để chọn/cập nhật một document trong một thao tác.
5. Hiểu vì sao **updateMany**, **deleteMany** và **bulkWrite** không mặc nhiên all-or-nothing.
6. Nhận diện khi nào nên mô hình hóa dữ liệu trong cùng document, khi nào cần **multi-document transaction**.
7. Phân biệt atomicity với **isolation, durability, write concern, read concern, retry**.
8. Viết kịch bản thực hành trên database lab và giải thích kết quả trong các tình huống cạnh tranh ghi.

> Các lệnh dưới đây dùng database thực hành riêng **mongo_atomic_lab** và nhãn **atomicity-v1**. Nhiều ví dụ sửa dữ liệu, vì vậy mỗi phần sẽ ghi rõ khi nào cần chạy lại seed. Không chạy chúng trên ví hoặc tồn kho của hệ thống thật.

## 2. Tính nguyên tử của một document nghĩa chính xác là gì?

### 2.1. Một lệnh ghi có thể thay đổi nhiều field cùng nhau

Giả sử một order lưu:

~~~javascript
{
  _id: "order-101",
  tenantId: "t001",
  status: "draft",
  paidAt: null,
  paymentReference: null,
  version: 0
}
~~~

Ta muốn chuyển đơn sang paid:

~~~javascript
db.orders.updateOne(
  { _id: "order-101", tenantId: "t001", status: "draft" },
  {
    $set: {
      status: "paid",
      paidAt: new Date(),
      paymentReference: "pay-101"
    },
    $inc: { version: 1 }
  }
);
~~~

MongoDB thực hiện **một cập nhật nguyên tử trên document Order**. Các document đọc được ở những thời điểm thích hợp không thấy một trạng thái chỉ có status đổi thành paid nhưng các trường khác của **cùng update** chưa được áp dụng.

Điều đó **không** bao gồm những side effect ngoài document, như gửi email, ghi log vào hệ thống khác, cập nhật một collection khác, hay gọi API của cổng thanh toán.

### 2.2. Atomic không có nghĩa câu lệnh đọc và câu lệnh ghi tách rời là một thao tác

Mẫu dễ lỗi:

~~~javascript
const order = db.orders.findOne({ _id: "order-101" });

// Giữa findOne và updateOne, service khác có thể sửa order.

db.orders.updateOne(
  { _id: "order-101" },
  { $set: { status: "paid" } }
);
~~~

Đây là **hai thao tác** riêng. Việc findOne đọc status draft **không khóa trạng thái đó** cho tới khi updateOne chạy. Nếu updateOne chỉ filter _id, nó có thể ghi lên order đã bị tác vụ khác chuyển sang cancelled.

Sửa bằng cách đưa **điều kiện nghiệp vụ vào filter của chính updateOne**:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "t001",
    status: "draft"
  },
  {
    $set: {
      status: "paid",
      paidAt: new Date()
    }
  }
);
~~~

MongoDB kiểm tra điều kiện khi áp dụng thao tác ghi. Nếu trạng thái đã đổi trước đó, thao tác sẽ không còn khớp, thay vì ghi đè một cách mù quáng.

### 2.3. “Atomic” không có nghĩa “không bao giờ thất bại”

Một update có thể thất bại do validation, thiếu quyền, lỗi mạng, write conflict, điều kiện filter không khớp hoặc các giới hạn khác. Atomicity nói về **không lộ trạng thái ghi nửa chừng trong một document**, không hứa mọi yêu cầu đều thành công.

Cũng không được đánh đồng:

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Atomicity** | Thay đổi có bị áp dụng nửa chừng hay không? |
| **Isolation** | Các thao tác đồng thời có thể thấy và ảnh hưởng lẫn nhau như thế nào? |
| **Consistency / invariant** | Quy tắc nghiệp vụ có còn đúng sau thao tác không? |
| **Durability** | Ghi thành công được lưu bền vững theo mức xác nhận nào? |
| **Idempotency** | Cùng yêu cầu được gửi lại có gây thêm tác động hay không? |

MongoDB hỗ trợ atomicity một document, nhưng **cách viết filter và update quyết định liệu một invariant nghiệp vụ có được bảo vệ hay không**.

## 3. Khởi tạo lab có thể chạy lại

Ta dùng bốn collection:

- **lab_wallets:** hai ví thuộc cùng tenant; số dư lưu bằng **balanceCents** kiểu Int32 để các ví dụ không bị sai số floating point.
- **lab_stock:** một document tồn kho với **available**, **reserved** và version.
- **lab_orders:** ba đơn có status draft/pending/paid.
- **lab_transfer_audit:** ghi nhận một giao dịch chuyển tiền khi thực hành transaction.

Các ID và giá trị ban đầu cố định để đối chiếu được sau mỗi thí nghiệm.

### 3.1. Script seed

Chạy nguyên khối bằng **mongosh**:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_atomic_lab");
  const tag = "atomicity-v1";
  const wallets = lab.getCollection("lab_wallets");
  const stock = lab.getCollection("lab_stock");
  const orders = lab.getCollection("lab_orders");
  const audit = lab.getCollection("lab_transfer_audit");

  // Chỉ xóa document của dataset thực hành.
  wallets.deleteMany({ dataset: tag });
  stock.deleteMany({ dataset: tag });
  orders.deleteMany({ dataset: tag });
  audit.deleteMany({ dataset: tag });

  wallets.insertMany([
    {
      _id: "wallet-a",
      dataset: tag,
      tenantId: "t001",
      ownerId: "alice",
      balanceCents: NumberInt(10000),
      version: NumberInt(0)
    },
    {
      _id: "wallet-b",
      dataset: tag,
      tenantId: "t001",
      ownerId: "bob",
      balanceCents: NumberInt(4000),
      version: NumberInt(0)
    }
  ]);

  stock.insertOne({
    _id: "sku-001",
    dataset: tag,
    tenantId: "t001",
    available: NumberInt(2),
    reserved: NumberInt(0),
    version: NumberInt(0),
    reservations: []
  });

  orders.insertMany([
    {
      _id: "order-101",
      dataset: tag,
      tenantId: "t001",
      status: "draft",
      paidAt: null,
      paymentReference: null,
      version: NumberInt(0)
    },
    {
      _id: "order-102",
      dataset: tag,
      tenantId: "t001",
      status: "draft",
      paidAt: null,
      paymentReference: null,
      version: NumberInt(0)
    },
    {
      _id: "order-103",
      dataset: tag,
      tenantId: "t001",
      status: "pending",
      paidAt: null,
      paymentReference: null,
      version: NumberInt(0)
    }
  ]);

  wallets.createIndex(
    { dataset: 1, tenantId: 1, ownerId: 1 },
    { name: "ix_atomic_wallet_owner" }
  );

  stock.createIndex(
    { dataset: 1, tenantId: 1 },
    { name: "ix_atomic_stock_scope" }
  );

  orders.createIndex(
    { dataset: 1, tenantId: 1, status: 1 },
    { name: "ix_atomic_order_status" }
  );

  printjson({
    wallets: wallets.countDocuments({ dataset: tag }),
    stock: stock.countDocuments({ dataset: tag }),
    orders: orders.countDocuments({ dataset: tag }),
    audit: audit.countDocuments({ dataset: tag })
  });
})();
~~~

**Kết quả mong đợi:** wallets = **2**, stock = **1**, orders = **3**, audit = **0**.

### 3.2. Các giá trị gốc cần ghi nhớ

| Document | Trường | Giá trị |
| --- | --- | ---: |
| wallet-a | balanceCents | 10.000 |
| wallet-b | balanceCents | 4.000 |
| sku-001 | available | 2 |
| sku-001 | reserved | 0 |
| order-101 | status | draft |
| order-102 | status | draft |
| order-103 | status | pending |

Tổng số dư hai ví lúc đầu là **14.000 cents**. Cặp available + reserved của sku-001 ban đầu bằng **2**.

Để xem trạng thái:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_atomic_lab");
  const tag = "atomicity-v1";

  print("Ví:");
  printjson(
    lab.lab_wallets.find(
      { dataset: tag },
      { _id: 1, balanceCents: 1, version: 1 }
    ).sort({ _id: 1 }).toArray()
  );

  print("Tồn kho:");
  printjson(
    lab.lab_stock.findOne(
      { _id: "sku-001", dataset: tag }
    )
  );
})();
~~~

**Các ví dụ ở những mục sau là các thí nghiệm độc lập** trừ khi được ghi rõ. Hãy chạy lại seed ở mục 3.1 trước mỗi thí nghiệm khi muốn so sánh với giá trị mong đợi.

## 4. Một updateOne thay đổi nhiều trường nhưng vẫn nguyên tử

### 4.1. Chuyển trạng thái đơn và ghi thông tin thanh toán

Sau khi chạy seed:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_atomic_lab");
  const orders = lab.getCollection("lab_orders");

  const result = orders.updateOne(
    {
      _id: "order-101",
      dataset: "atomicity-v1",
      tenantId: "t001",
      status: "draft"
    },
    {
      $set: {
        status: "paid",
        paidAt: ISODate("2026-06-01T10:00:00.000Z"),
        paymentReference: "pay-lab-101"
      },
      $inc: { version: 1 }
    }
  );

  printjson(result);
  printjson(orders.findOne({ _id: "order-101" }));
})();
~~~

**Kết quả lần đầu:** matchedCount = **1**, modifiedCount = **1**. Document có status paid, paidAt và paymentReference đã được đặt cùng nhau, version = **1**.

Chạy lại ngay cùng lệnh thì **matchedCount = 0** vì status không còn draft. Đây là hành vi mong muốn: cùng một thao tác không tiếp tục “thanh toán” document đã ở trạng thái paid.

### 4.2. Vì sao cần kiểm tra matchedCount và modifiedCount?

MongoDB driver/mongosh thường trả các thông tin:

- **matchedCount:** số document khớp filter cho updateOne; thường bằng 0 hoặc 1.
- **modifiedCount:** số document thực sự bị thay đổi.
- **upsertedCount/upsertedId:** chỉ xuất hiện khi dùng upsert và có insert mới.

Với **matchedCount = 0**, có thể không tìm thấy _id hoặc các điều kiện tenant/status/version không còn đúng. Không nên gọi đó là lỗi kết nối và tự retry vô hạn. Với **matchedCount = 1, modifiedCount = 0**, có thể update đã đặt trường bằng đúng giá trị hiện có (nếu không có một toán tử thay đổi chắc chắn như tăng version).

Trong nghiệp vụ, việc **không khớp điều kiện trạng thái** nên được trả thành kết quả rõ, chẳng hạn “đơn đã được xử lý hoặc không còn ở trạng thái cho phép”, thay vì ghi đè.

### 4.3. Cập nhật cả một Array nằm trong cùng document

Tính nguyên tử cũng áp dụng khi thao tác sửa **mảng và nhiều field của cùng document**:

~~~javascript
db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_stock")
  .updateOne(
    {
      _id: "sku-001",
      dataset: "atomicity-v1",
      tenantId: "t001",
      available: { $gte: 1 }
    },
    {
      $inc: {
        available: -1,
        reserved: 1,
        version: 1
      },
      $addToSet: {
        reservations: "reservation-001"
      }
    }
  );
~~~

Với seed ban đầu, document stock thành **available = 1**, **reserved = 1**, **version = 1** và reservations chứa reservation-001. Các thay đổi thuộc cùng một thao tác ghi trên document stock.

Lưu ý quan trọng: **$addToSet chỉ tránh chèn giá trị đã tồn tại vào Array**; nó không tự làm cho toàn bộ thao tác trở nên idempotent. Nếu chạy lại lệnh trên khi available vẫn đủ, **$inc vẫn chạy lần nữa** dù reservation-001 đã có trong mảng. Nếu mỗi reservation chỉ được trừ tồn kho một lần, filter phải bảo đảm reservationId chưa tồn tại hoặc cần cơ chế idempotency riêng.

## 5. Cạnh tranh ghi: lost update với read–modify–write

### 5.1. Hai lần đọc cùng một số dư cũ

Giả sử hai yêu cầu gần đồng thời cùng đọc **wallet-a = 10.000 cents**:

~~~text
Request A đọc balance=10.000
Request B đọc balance=10.000

A muốn rút 1.000 => tính trong ứng dụng: 9.000
B muốn rút 2.000 => tính trong ứng dụng: 8.000

A $set balance=9.000
B $set balance=8.000

Kết quả cuối = 8.000
Đúng ra hai khoản rút phải để lại = 7.000
~~~

Mỗi **$set trên một document** là nguyên tử; lỗi xuất hiện vì cả hai tính toán dựa trên **snapshot cũ** rồi ghi đè lẫn nhau. Đây là **lost update**, không phải MongoDB “ghi nửa document”.

### 5.2. Mô phỏng lost update trong một phiên mongosh

Chạy lại seed trước đoạn này. Ta chủ động mô phỏng **hai kết quả đọc cũ giống nhau**, không cần tạo hai tiến trình đồng thời:

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_wallets");
  const filter = {
    _id: "wallet-a",
    dataset: "atomicity-v1",
    tenantId: "t001"
  };

  const snapshotA = c.findOne(filter);
  const snapshotB = c.findOne(filter);

  const resultA = c.updateOne(
    filter,
    { $set: { balanceCents: snapshotA.balanceCents - 1000 } }
  );
  const resultB = c.updateOne(
    filter,
    { $set: { balanceCents: snapshotB.balanceCents - 2000 } }
  );

  printjson({ first: resultA.modifiedCount,
              second: resultB.modifiedCount });
  print("Số dư cuối: " +
    c.findOne(filter).balanceCents);
})();
~~~

**Kết quả mong đợi:** số dư cuối = **8.000 cents**, không phải 7.000. Lệnh thứ hai dùng giá trị đọc cũ 10.000 nên đã ghi đè kết quả 9.000 của lệnh thứ nhất.

**Bài học:** atomic update không tự sửa lỗi **read–modify–write ở phía ứng dụng** khi giá trị mới được tính từ một lần đọc cũ mà không có điều kiện cạnh tranh.

## 6. Dùng toán tử cập nhật để tránh ghi đè

### 6.1. $inc là thao tác tăng/giảm tại server

Chạy lại seed. Thay vì đọc số dư rồi $set, gửi lượng thay đổi:

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_wallets");
  const filter = {
    _id: "wallet-a",
    dataset: "atomicity-v1",
    tenantId: "t001"
  };

  const first = c.updateOne(
    filter,
    { $inc: { balanceCents: -1000 } }
  );
  const second = c.updateOne(
    filter,
    { $inc: { balanceCents: -2000 } }
  );

  printjson({ first: first.modifiedCount,
              second: second.modifiedCount });
  print("Số dư cuối: " +
    c.findOne(filter).balanceCents);
})();
~~~

**Kết quả mong đợi:** **7.000 cents**. Cả hai $inc tác động lên giá trị hiện tại của cùng document; mỗi update là nguyên tử và không cần ghi đè bằng snapshot cũ.

Nhưng một điều khác phải nhớ: **$inc âm không tự bảo đảm số dư không âm**. Nếu có nhiều khoản rút vượt số dư, MongoDB vẫn có thể áp dụng phép giảm nếu filter không cấm nó.

### 6.2. Filter có điều kiện bảo vệ invariant số dư

Chạy lại seed. Để rút 3.000 cents chỉ khi tài khoản còn đủ tiền:

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_wallets");
  const amount = 3000;

  const result = c.updateOne(
    {
      _id: "wallet-a",
      dataset: "atomicity-v1",
      tenantId: "t001",
      balanceCents: { $gte: amount }
    },
    {
      $inc: {
        balanceCents: -amount,
        version: 1
      }
    }
  );

  printjson(result);
  printjson(
    c.findOne(
      { _id: "wallet-a", dataset: "atomicity-v1" },
      { _id: 1, balanceCents: 1, version: 1 }
    )
  );
})();
~~~

**Kết quả mong đợi lần đầu:** matchedCount = 1, số dư còn **7.000**, version = 1. Nếu tiếp tục yêu cầu rút **8.000** với filter balanceCents >= 8.000, sẽ có **matchedCount = 0** và số dư vẫn 7.000.

Khi hai yêu cầu rút cùng đến, việc kiểm tra **balanceCents >= amount** nằm trong **chính updateOne**. Với cách thiết kế này, mỗi khoản rút chỉ có thể thành công khi document vẫn thỏa điều kiện tại thời điểm update; nó không dựa vào số dư đã đọc từ trước.

**Quy tắc nghiệp vụ phải được thiết kế đầy đủ.** Đoạn lab không thay thế hệ thống ledger, fraud checks, idempotency hoặc kiểm soát quyền. Nếu một request rút 3.000 được gửi hai lần với hai lệnh $inc độc lập, nó vẫn có thể trừ **6.000** nếu cả hai lần số dư đều đủ.

### 6.3. Conditional update là compare-and-set theo điều kiện

Mô hình:

~~~text
UPDATE document
  IF version == phiên bản đã đọc
  THEN sửa field và version += 1
  ELSE không sửa
~~~

Trong MongoDB, không cần một API riêng tên CAS: filter **version** cùng toán tử cập nhật thể hiện phép so sánh rồi ghi trên một document.

## 7. Optimistic concurrency control với version

### 7.1. Vì sao cần version?

Với một số field, thay đổi không phải phép cộng có thể dùng $inc. Ví dụ hai người cùng sửa địa chỉ giao hàng:

~~~text
Người A đọc version=3, địa chỉ cũ
Người B đọc version=3, địa chỉ cũ

A sửa địa chỉ thành X
B sửa địa chỉ thành Y

Nếu chỉ filter _id, yêu cầu chạy sau có thể ghi đè yêu cầu chạy trước.
~~~

**Optimistic concurrency control** lưu một số phiên bản trong document, bắt người ghi xác nhận phiên bản chưa đổi.

### 7.2. Ví dụ trên order lab

Chạy lại seed:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_orders");

  const identity = {
    _id: "order-101",
    dataset: "atomicity-v1",
    tenantId: "t001"
  };

  const readByA = orders.findOne(identity);
  const readByB = orders.findOne(identity);

  const resultA = orders.updateOne(
    { ...identity, version: readByA.version },
    {
      $set: { shippingNote: "Giao vào buổi sáng" },
      $inc: { version: 1 }
    }
  );

  const resultB = orders.updateOne(
    { ...identity, version: readByB.version },
    {
      $set: { shippingNote: "Giao vào buổi chiều" },
      $inc: { version: 1 }
    }
  );

  printjson({
    firstMatched: resultA.matchedCount,
    secondMatched: resultB.matchedCount
  });
  printjson(
    orders.findOne(identity, {
      _id: 1, version: 1, shippingNote: 1
    })
  );
})();
~~~

**Kết quả mong đợi:**

- A matchedCount = **1**, shippingNote là “Giao vào buổi sáng”, version tăng từ 0 lên 1.
- B matchedCount = **0** vì nó vẫn dùng version 0.
- Thay đổi của A không bị B ghi đè.

Ứng dụng nên phản hồi một **conflict có nghĩa nghiệp vụ**, ví dụ yêu cầu client tải lại và quyết định có ghi đè hay hợp nhất. Không tự retry B bằng version mới rồi ghi đè A nếu chưa có quy tắc xử lý xung đột.

### 7.3. Những giới hạn của version

Version chỉ hữu ích khi **mọi đường ghi có liên quan đều cập nhật và kiểm tra version theo hợp đồng nhất quán**. Một tác vụ khác cập nhật document nhưng không tăng version có thể khiến client không phát hiện xung đột. Version cũng không khóa document liên tục giữa hai request.

Nếu cần dùng **updatedAt** làm mốc, phải cẩn thận với độ phân giải thời gian và các thao tác cùng timestamp. Một số nguyên tăng đơn điệu rõ nghĩa thường dễ quản lý hơn cho optimistic concurrency.

## 8. findOneAndUpdate: chọn và cập nhật trong cùng một thao tác

### 8.1. Thay cho tìm ứng viên rồi cập nhật riêng

Giả sử worker cần lấy một job đang pending và chuyển sang processing. Mẫu:

~~~text
findOne({status:"pending"})
  ->
updateOne({_id:job._id}, {$set:{status:"processing"}})
~~~

có khoảng cạnh tranh: hai worker có thể cùng chọn một job pending trước khi một worker kịp đánh dấu. **findOneAndUpdate** cho phép chọn và cập nhật một document như một thao tác, cùng điều kiện filter.

Ví dụ với order-103 của lab:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_orders");

  const claimed = orders.findOneAndUpdate(
    {
      dataset: "atomicity-v1",
      tenantId: "t001",
      status: "pending"
    },
    {
      $set: {
        status: "processing",
        claimedBy: "worker-A",
        claimedAt: ISODate("2026-06-01T11:00:00.000Z")
      },
      $inc: { version: 1 }
    },
    {
      sort: { _id: 1 },
      returnDocument: "after"
    }
  );

  printjson(claimed);
})();
~~~

**Kết quả sau seed:** trả **order-103** với status processing và claimedBy worker-A. Chạy lần nữa sẽ trả **null** nếu không còn document pending.

**returnDocument: "after"** yêu cầu trả trạng thái document **sau update**. Không nhầm với API của các driver khác nhau, nơi kết quả có thể được bọc trong đối tượng metadata tùy phiên bản; ví dụ trên dùng mongosh.

### 8.2. Tại sao returnDocument không phải một read riêng biệt?

Khi dùng findOneAndUpdate, MongoDB xác định một document khớp và cập nhật nó trong một thao tác nguyên tử. Đó là cơ chế phù hợp để claim một job hoặc đổi trạng thái có điều kiện.

Tuy vậy:

- Không tự đảm bảo job chỉ được **xử lý thực tế một lần** nếu worker crash sau khi claim.
- Không tự bảo vệ side effect nằm ngoài database.
- Cần thiết kế timeout/lease, retry và idempotency cho hệ thống queue thực.
- Nếu có nhiều document cùng khớp, dùng sort rõ ràng và index phù hợp để chọn thứ tự; không mặc định một document bất kỳ sẽ luôn được chọn.

Atomic claim một document là bước cần thiết, nhưng không phải toàn bộ giao thức xử lý job tin cậy.

## 9. updateMany và deleteMany: nguyên tử từng document, không nguyên tử toàn tập

### 9.1. updateMany

Ví dụ chuyển tất cả draft orders của t001 thành pending:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_orders");

  const result = orders.updateMany(
    {
      dataset: "atomicity-v1",
      tenantId: "t001",
      status: "draft"
    },
    {
      $set: { status: "pending" },
      $inc: { version: 1 }
    }
  );

  printjson(result);
})();
~~~

Từ seed, lần đầu **matchedCount = 2** và **modifiedCount = 2** (order-101 và order-102).

**Mỗi document được update là nguyên tử**, nhưng **toàn bộ updateMany không được bao bọc trong một transaction tự động**. Khi updateMany đang chạy, các tác vụ khác có thể quan sát một phần document đã đổi, một phần chưa đổi (tùy mô hình đọc/đồng thời). Nếu thao tác bị lỗi hoặc gián đoạn, có thể đã có một số document được thay đổi.

### 9.2. deleteMany

~~~javascript
db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_orders")
  .deleteMany({
    dataset: "atomicity-v1",
    tenantId: "t001",
    status: "draft"
  });
~~~

deleteMany cũng xóa nhiều document; **mỗi lần xóa một document là nguyên tử**, nhưng toàn bộ số document khớp không tự tạo một đơn vị all-or-nothing. Đừng coi deleteMany là “hoặc xóa hết, hoặc không xóa gì” khi không có transaction thích hợp.

### 9.3. bulkWrite không tự là transaction

~~~javascript
db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_orders")
  .bulkWrite(
    [
      {
        updateOne: {
          filter: { _id: "order-101", dataset: "atomicity-v1" },
          update: { $set: { status: "pending" } }
        }
      },
      {
        updateOne: {
          filter: { _id: "order-102", dataset: "atomicity-v1" },
          update: { $set: { status: "pending" } }
        }
      }
    ],
    { ordered: true }
  );
~~~

**ordered: true** điều khiển cách thực hiện thao tác theo thứ tự và cách dừng khi có lỗi. **ordered: false** cho phép linh hoạt thứ tự và tiếp tục các operation khác theo cơ chế của bulk write. Cả hai **không tự bảo đảm rollback mọi thao tác đã thành công nếu thao tác sau thất bại**.

### 9.4. So sánh nhanh

| Thao tác | Phạm vi nguyên tử mặc định | Có thể sửa/xóa nhiều document? |
| --- | --- | --- |
| **updateOne** | Một document được chọn | Không, tối đa một |
| **replaceOne** | Một document được chọn | Không, tối đa một |
| **deleteOne** | Một document được chọn | Không, tối đa một |
| **findOneAndUpdate** | Chọn và cập nhật một document | Không, tối đa một |
| **updateMany** | Từng document riêng rẽ | Có |
| **deleteMany** | Từng document riêng rẽ | Có |
| **bulkWrite** | Từng thao tác/document theo semantics riêng | Có |
| **Multi-document transaction** | Các thao tác trong transaction được commit/abort chung | Có, trong giới hạn triển khai |

Nếu một document đồng thời chứa nhiều phần tử trong Array, updateOne có thể sửa nhiều phần tử của Array **mà vẫn ở trong một document**. Số phần tử bị sửa không phải cách xác định giới hạn nguyên tử; **số document bị sửa** mới là ranh giới chính.

## 10. Chuyển tiền giữa hai ví: vì sao cần transaction?

### 10.1. Hai updateOne độc lập có khoảng trống

Sau seed, muốn chuyển **3.000 cents** từ wallet-a sang wallet-b:

~~~javascript
// Đây là MẪU CỐ Ý THIẾU transaction, chỉ dùng để giải thích.
const wallets = db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_wallets");

const debit = wallets.updateOne(
  {
    _id: "wallet-a",
    dataset: "atomicity-v1",
    tenantId: "t001",
    balanceCents: { $gte: 3000 }
  },
  { $inc: { balanceCents: -3000 } }
);

// Nếu ứng dụng crash ở đây, chỉ ví A đã bị trừ.

if (debit.matchedCount === 1) {
  wallets.updateOne(
    {
      _id: "wallet-b",
      dataset: "atomicity-v1",
      tenantId: "t001"
    },
    { $inc: { balanceCents: 3000 } }
  );
}
~~~

Nếu cả hai thành công, A = **7.000**, B = **7.000**, tổng = **14.000**. Nhưng nếu chỉ debit thành công, A = 7.000 và B = 4.000, tổng còn 11.000. Một updateOne nguyên tử không có khả năng rollback updateOne khác đã chạy trước nó.

**Đừng dùng mẫu này làm giao dịch tài chính production.** Nó được đưa ra để làm rõ giới hạn của nguyên tử một document.

### 10.2. Multi-document transaction bảo đảm all-or-nothing trong database

MongoDB hỗ trợ **multi-document transactions** trên **replica set** và **sharded cluster** theo điều kiện phiên bản/triển khai. Một transaction có thể gom:

1. Kiểm tra và trừ ví nguồn.
2. Cộng ví đích.
3. Ghi document audit cho transfer.
4. **Commit** tất cả hoặc **abort** tất cả.

Sơ đồ:

~~~text
START TRANSACTION
       |
       +-- UPDATE wallet-a: -3.000 nếu còn đủ
       |
       +-- UPDATE wallet-b: +3.000
       |
       +-- INSERT transfer-audit
       |
       +-- COMMIT
             |
             +-- thành công: cả ba thay đổi có hiệu lực
             |
             +-- abort: các thay đổi trong transaction không commit
~~~

Transaction là giải pháp khi **invariant cần giữ trải trên nhiều document**. Nhưng nó có chi phí về tài nguyên, thời gian, xung đột và độ phức tạp xử lý lỗi. Nếu mô hình có thể đặt các trường liên quan vào **một document có giới hạn và vòng đời phù hợp**, một single-document update thường đơn giản hơn.

## 11. Ví dụ transaction bằng MongoDB Node.js driver

Ví dụ này là mã Node.js dành cho môi trường lab có MongoDB **replica set hoặc sharded cluster hỗ trợ transaction**; nó không chạy thành công trên một standalone mongod không hỗ trợ transaction. Cần cài package **mongodb** và cung cấp URI có quyền đọc/ghi database lab.

Chạy lại seed mục 3 trước khi thử. Ví dụ dùng **transferId cố định** để xác định yêu cầu nghiệp vụ; nó chỉ thay đổi các document có dataset lab và ID cố định.

~~~javascript
// Lưu thành ví dụ JavaScript nếu cần chạy với Node.js (ES module).
// npm install mongodb
import { MongoClient } from "mongodb";

async function transferOnce(uri, transferId, amountCents) {
  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    throw new Error("amountCents phải là số nguyên dương");
  }

  const client = new MongoClient(uri);
  await client.connect();

  const session = client.startSession();
  const lab = client.db("mongo_atomic_lab");
  const wallets = lab.collection("lab_wallets");
  const audit = lab.collection("lab_transfer_audit");
  const dataset = "atomicity-v1";
  const tenantId = "t001";

  try {
    await session.withTransaction(async () => {
      // Nếu yêu cầu đã commit trước đó với cùng ID, không chuyển lần hai.
      const existing = await audit.findOne(
        { _id: transferId, dataset },
        { session }
      );

      if (existing) {
        if (
          existing.amountCents !== amountCents ||
          existing.fromWalletId !== "wallet-a" ||
          existing.toWalletId !== "wallet-b"
        ) {
          throw new Error("transferId đã được dùng cho nội dung khác");
        }
        return;
      }

      const debit = await wallets.updateOne(
        {
          _id: "wallet-a",
          dataset,
          tenantId,
          balanceCents: { $gte: amountCents }
        },
        {
          $inc: {
            balanceCents: -amountCents,
            version: 1
          }
        },
        { session }
      );

      if (debit.matchedCount !== 1) {
        throw new Error("Ví nguồn không đủ tiền hoặc không hợp lệ");
      }

      const credit = await wallets.updateOne(
        {
          _id: "wallet-b",
          dataset,
          tenantId
        },
        {
          $inc: {
            balanceCents: amountCents,
            version: 1
          }
        },
        { session }
      );

      if (credit.matchedCount !== 1) {
        throw new Error("Không tìm thấy ví đích hợp lệ");
      }

      await audit.insertOne(
        {
          _id: transferId,
          dataset,
          tenantId,
          fromWalletId: "wallet-a",
          toWalletId: "wallet-b",
          amountCents,
          createdAt: new Date()
        },
        { session }
      );
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      readPreference: "primary"
    });
  } finally {
    await session.endSession();
    await client.close();
  }
}

// Gọi ví dụ với URI của replica set/sharded cluster thử nghiệm:
// await transferOnce(process.env.MONGODB_URI, "transfer-lab-001", 3000);
~~~

Sau khi transfer thành công một lần, trạng thái mong đợi:

~~~text
wallet-a: 7.000 cents
wallet-b: 7.000 cents
Tổng:    14.000 cents
lab_transfer_audit: có document transfer-lab-001
~~~

### 11.1. Tại sao truyền session vào từng thao tác?

Các lệnh **findOne, updateOne, insertOne** trong callback phải nhận cùng **session**. Nếu một updateOne không được truyền session, nó có thể chạy **ngoài transaction** và không được rollback khi callback thất bại.

Transaction không đơn giản là gọi **startTransaction** ở đầu rồi tất cả lệnh trong toàn chương trình tự động thuộc transaction. Phạm vi session cần được quản lý đúng.

### 11.2. Vì sao cần kiểm tra matchedCount?

Nếu ví nguồn không đủ tiền, filter **balanceCents >= amountCents** không khớp; callback ném lỗi để transaction bị abort. Nếu ví đích không tồn tại, thao tác credit matchedCount = 0; cũng cần abort thay vì commit chỉ khoản debit.

Một transaction **không tự hiểu ràng buộc kinh doanh**. Nếu bỏ điều kiện đủ tiền, transaction có thể commit việc rút số dư âm **một cách nguyên tử nhưng sai nghiệp vụ**.

### 11.3. Audit ID và idempotency

Trường **_id = transferId** của audit làm khóa xác định một transfer. Trong transaction, code kiểm tra transferId đã tồn tại và đối chiếu thông tin. Nếu yêu cầu cùng transferId được lặp sau khi commit thành công, code không tiếp tục trừ/cộng tiền.

Tuy nhiên, với **hai request đồng thời cùng transferId**, một request có thể gặp write conflict hoặc duplicate key khi cùng cố ghi audit; cách xử lý cần dựa trên kết quả transaction và kiểm tra lại trạng thái. Đây là **một phần của thiết kế idempotency**, không phải cam kết rằng mọi lỗi mạng đều đã được giải quyết.

Trong hệ thống thanh toán thật, cần định nghĩa thêm tính duy nhất toàn hệ thống/tenant, chữ ký yêu cầu, cách xử lý side effect ngoài MongoDB và các sự kiện đã xử lý.

### 11.4. Callback transaction có thể chạy lại

Một số helper như **withTransaction** hỗ trợ xử lý các loại lỗi transaction có thể retry. Callback có thể được gọi lại sau một **transient transaction error**. Vì vậy:

- **Không gửi email, gọi cổng thanh toán hoặc tạo side effect bên ngoài trực tiếp trong callback** nếu chúng không idempotent.
- Không dựa vào biến đếm cục bộ tăng trong callback như bằng chứng “callback chỉ chạy một lần”.
- Các thao tác MongoDB trong callback phải dùng session và nhất quán với cơ chế retry.
- **UnknownTransactionCommitResult** cần được xử lý đúng để không tự tạo một transaction mới chuyển tiền lần hai.

Mẫu dùng **transferId cố định** chỉ là điểm khởi đầu. Với sản phẩm thực, xem tài liệu driver/version, trạng thái commit không xác định và chiến lược đối soát.

### 11.5. Vì sao không đặt toàn bộ quy trình lớn vào transaction?

Transaction nhiều document có giới hạn vận hành về thời lượng, tài nguyên, xung đột và khả năng abort; giá trị mặc định của một số ngưỡng có thể khác theo cấu hình triển khai. Không gom hàng triệu document vào một transaction khổng lồ chỉ để tránh phải thiết kế checkpoint.

Nếu quy trình cần cập nhật hàng triệu bản ghi có thể chạy nhiều phút/giờ, thường phải chia thành các đơn vị nghiệp vụ có thể **retry**, **resume** và **đối soát**. Transaction phù hợp cho nhóm document nhỏ cần commit cùng nhau, không phải công cụ thay thế cho mọi batch job.

## 12. Isolation, snapshot và các dạng xung đột

### 12.1. Atomicity và isolation không giống nhau

Hãy phân biệt:

- **Atomicity một document:** một update trên document không để lộ trạng thái chỉ mới cập nhật nửa các field của lệnh đó.
- **Isolation của transaction:** các thao tác đọc/ghi trong transaction được nhìn nhận dưới quy tắc đọc/ghi của transaction và read concern.
- **Serializability:** mức bảo đảm cao hơn, các transaction có kết quả tương đương một thứ tự chạy nối tiếp trong mọi tình huống được xét.

Không được tự coi **snapshot isolation** là bảo đảm **serializability** cho mọi invariant xuyên nhiều document. Một số ràng buộc có thể cần thêm **ghi vào cùng document bảo vệ**, unique index, điều kiện ghi hoặc thiết kế transaction/lock nghiệp vụ phù hợp.

### 12.2. Write conflict

Nếu hai transaction cùng cố sửa một document, MongoDB có thể phát hiện **write conflict**, abort một transaction hoặc yêu cầu retry theo cơ chế hỗ trợ. Điều đó giúp tránh một số kiểu ghi chồng lấn không hợp lệ nhưng có thể tăng độ trễ và tỷ lệ retry khi document nóng.

Ví dụ nhiều worker cập nhật cùng document stock:

~~~text
Transaction A: đọc stock, định cập nhật sku-001
Transaction B: đọc stock, định cập nhật sku-001

Khi cả hai cố ghi cùng document, có thể xảy ra write conflict.
Ứng dụng phải xử lý abort/retry có giới hạn và idempotency.
~~~

Không nên retry không giới hạn khi nhiều client cùng tranh chấp một document. Có thể cần backoff, hàng đợi hoặc thay đổi mô hình dữ liệu để giảm hot spot.

### 12.3. Write skew trên nhiều document

Giả sử một chính sách yêu cầu **ít nhất một nhân viên trực ca**. Có hai document nhân viên A và B, đều đang onCall = true. Hai transaction có thể đồng thời nhìn thấy người kia vẫn trực, rồi mỗi transaction sửa **một document khác nhau** thành onCall = false. Nếu chỉ dựa vào snapshot và không tạo điểm xung đột bắt buộc trên cùng một document, invariant **ít nhất một người trực** có thể bị vi phạm trong những mô hình isolation cho phép write skew.

Phương án khắc phục tùy hệ thống:

- Đặt trạng thái trực ca của nhóm trong **một document** và cập nhật có điều kiện.
- Ghi một **guardian/version document** chung để tạo điểm cạnh tranh có kiểm soát.
- Thiết kế ràng buộc dữ liệu hoặc giao thức cập nhật phù hợp với mức isolation mong muốn.

Nêu ví dụ này để nhớ rằng **transaction là công cụ, không phải phép màu tự chứng minh mọi quy tắc nghiệp vụ**.

## 13. Ranh giới atomicity khi thiết kế document

### 13.1. Embedding có thể giúp gom invariant vào một document

Giả sử số lượng tồn kho gồm:

~~~javascript
{
  _id: "sku-001",
  available: 2,
  reserved: 0,
  reservations: []
}
~~~

Một updateOne có thể giữ invariant **available + reserved = 2** khi chuyển một đơn vị từ available sang reserved:

~~~javascript
db.inventory.updateOne(
  { _id: "sku-001", available: { $gte: 1 } },
  {
    $inc: {
      available: -1,
      reserved: 1
    }
  }
);
~~~

Hai field nằm trong **cùng document**, nên ứng dụng không thấy available đã trừ nhưng reserved chưa cộng trong phạm vi chính update đó.

Nếu available và reserved được tách thành hai document độc lập, việc bảo đảm tổng không đổi sẽ khó hơn và có thể cần transaction.

### 13.2. Nhưng không nhúng vô hạn để “lấy atomicity”

Một document MongoDB có giới hạn **16 MiB BSON**. Nếu nhúng hàng triệu giao dịch hoặc reservation vào một document:

- Document có thể tăng rất lớn.
- Mọi cập nhật đều tranh chấp cùng một document nóng.
- Khó phân trang hoặc tìm kiếm các phần tử độc lập.
- Khác biệt vòng đời và retention của các phần tử bị che lấp.

Vì vậy, **atomicity một document là một yếu tố thiết kế**, không phải lý do để gom toàn bộ hệ thống vào một document.

### 13.3. Một số tình huống

| Invariant/nhu cầu | Có thể đặt trong một document? | Khi cần phương án khác |
| --- | --- | --- |
| Status, paidAt, reference của một Order | Có, thường phù hợp | Khi phải ghi Payment/Audit ở collection khác cùng nguyên tử |
| available/reserved của một SKU | Có, nếu cùng vòng đời và cập nhật hợp lý | Nếu tồn kho phân vùng nhiều kho/document |
| Thêm một tag vào mảng của Product | Có | Khi quan hệ tags tăng vô hạn hoặc cập nhật độc lập |
| Chuyển tiền A → B | Không, nếu hai ví là hai document | Transaction hoặc ledger/giao thức nghiệp vụ khác |
| Xóa User và tất cả dữ liệu liên quan | Thường trải nhiều collection | Transaction phạm vi nhỏ, saga hoặc job có checkpoint |
| Ghi Order cùng một Payment record | Có thể nhiều document | Transaction khi cần cùng commit trong MongoDB |
| Gửi email sau khi commit Order | Không phải thao tác MongoDB | Outbox pattern, queue và idempotent consumer |

## 14. Unique index và atomicity: đừng check-then-insert

### 14.1. Race condition khi kiểm tra tồn tại rồi insert

Mẫu dễ lỗi:

~~~javascript
if (!db.users.findOne({ email: "a@example.com" })) {
  db.users.insertOne({ email: "a@example.com" });
}
~~~

Hai request có thể cùng không tìm thấy email, rồi cùng insert. Mỗi **insertOne** là nguyên tử một document, nhưng việc **“chỉ được có một email duy nhất”** là invariant **xuyên nhiều document**.

**Unique index** là cách đúng để MongoDB thực thi uniqueness ở mức storage cho khóa được index:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { unique: true, name: "ux_tenant_email_normalized" }
);
~~~

Application chuẩn hóa email và xử lý **duplicate key error**, không chỉ dựa vào câu findOne kiểm tra trước. Với ứng dụng multi-tenant, định nghĩa khóa unique phải phản ánh phạm vi thực sự muốn đảm bảo; cần xét null/missing và sharding nếu có.

### 14.2. Unique index không thay thế transaction

Unique index bảo vệ một dạng invariant cụ thể về **khóa**, nhưng không tự chuyển tiền giữa hai ví, ghi audit và gửi thông báo cùng lúc. Khi lựa chọn giải pháp:

- **Filter có điều kiện** cho invariant một document.
- **Unique index** cho uniqueness giữa document.
- **Transaction** cho nhóm thao tác MongoDB cần commit cùng nhau.
- **Outbox/saga/idempotency** cho quy trình trải nhiều hệ thống.

Mỗi công cụ giải quyết một lớp vấn đề khác nhau.

## 15. Write concern, read concern và độ bền của dữ liệu

### 15.1. Một update nguyên tử có thể được xác nhận theo nhiều mức

Atomicity không trả lời câu hỏi “thay đổi đã được ghi nhận bền vững qua failover chưa?”. Đó là vai trò của **write concern**.

Ví dụ:

~~~javascript
db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_orders")
  .updateOne(
    {
      _id: "order-101",
      dataset: "atomicity-v1",
      tenantId: "t001",
      status: "draft"
    },
    {
      $set: { status: "pending" }
    },
    {
      writeConcern: {
        w: "majority",
        wtimeout: 5000
      }
    }
  );
~~~

Với **replica set** phù hợp, majority yêu cầu xác nhận ghi ở mức đa số thành viên ghi dữ liệu theo cơ chế của MongoDB. Khi nhận **write concern timeout/error**, trạng thái thao tác có thể đã thay đổi trên server nhưng chưa được xác nhận theo mức yêu cầu; **không kết luận chắc chắn “chưa ghi”** nếu chưa đối chiếu.

Tùy topology, standalone và cấu hình triển khai, mức write concern có thể hành xử khác; phải xác định trước khi áp dụng mẫu vào hệ thống thật.

### 15.2. Read concern là vấn đề khác

Các mức read concern như **local**, **majority**, **snapshot** được dùng trong những ngữ cảnh khác nhau. Chúng kiểm soát đặc tính dữ liệu đọc được; không biến nhiều updateOne độc lập thành một transaction.

Ví dụ, dùng majority read concern không làm cho một quy trình chuyển tiền hai bước trở nên all-or-nothing. Nếu logic cần thấy **một trạng thái nhất quán xuyên hai ví**, phải thiết kế transaction/đọc phù hợp.

### 15.3. Đừng đánh đồng atomicity với exactly-once

Một thao tác **$inc** trên một document là nguyên tử. Nhưng nếu client gửi cùng yêu cầu hai lần do người dùng bấm hai lần hoặc request bị retry thủ công, $inc có thể tác động **hai lần**.

Trong môi trường hỗ trợ **retryable writes** của driver/session, một số thao tác single-document đủ điều kiện có thể được retry tự động với cơ chế tránh lặp tác động của **cùng một statement**. Điều đó không đồng nghĩa mọi lần gửi lại HTTP request qua một workflow mới đều được nhận diện là một sự kiện.

Muốn “mỗi payment/transfer chỉ áp dụng một lần”, cần **business idempotency key**, ràng buộc dữ liệu và cách đối soát trạng thái sau lỗi không xác định.

## 16. Ghi dữ liệu và side effect bên ngoài MongoDB

### 16.1. Transaction không bao trùm hệ thống email hoặc payment gateway

Giả sử transaction commit chuyển trạng thái Order thành paid và ghi Payment record. Sau đó ứng dụng gọi email service để gửi hóa đơn. Nếu email service lỗi, **transaction MongoDB đã commit vẫn không tự rollback**.

Không nên gọi một dịch vụ không idempotent bên trong transaction callback: callback có thể retry, và side effect bên ngoài không nằm trong commit/abort của MongoDB.

### 16.2. Transactional outbox

Một cách phổ biến:

~~~text
Trong MongoDB transaction:
  1) Update Order -> paid
  2) Insert Payment
  3) Insert OutboxEvent: "SendReceipt"
  COMMIT

Worker riêng:
  4) Đọc OutboxEvent chưa xử lý
  5) Gửi email
  6) Đánh dấu kết quả; retry có idempotency
~~~

Order/Payment/OutboxEvent có thể commit cùng nhau trong MongoDB, nhưng **email có thể đến muộn**. Consumer cần chịu được gửi lại sự kiện (at-least-once delivery) và dùng idempotency khi mục tiêu là tránh gửi email trùng.

Outbox không tạo một distributed transaction giữa MongoDB và email service; nó giúp đồng bộ nghiệp vụ một cách bền vững và có thể retry.

### 16.3. Saga và bù trừ

Nếu một workflow trải nhiều dịch vụ (đặt hàng, thanh toán, kho, vận chuyển) và không thể đặt tất cả bước trong một transaction database, có thể cần **saga**:

~~~text
ReserveStock
  -> ChargePayment
     -> CreateShipment
        -> nếu thất bại, chạy các bước bù trừ phù hợp
~~~

Bù trừ không phải rollback nguyên tử ở mức storage: các bước đã có thể được quan sát ở bên ngoài và việc bù trừ cũng có thể thất bại. Phải mô hình trạng thái và retry rõ ràng.

## 17. Sharded cluster và phạm vi nguyên tử

### 17.1. Một document vẫn là ranh giới cơ bản

Trong sharded collection, một document nằm ở vị trí được định tuyến theo shard key và quy tắc của cluster. Một lệnh ghi có điều kiện trên một document vẫn có ranh giới atomicity của document, nhưng hiệu năng và khả năng định tuyến phụ thuộc filter/shard key và phiên bản server.

Không dựa vào tính nguyên tử một document để suy luận rằng **một updateMany trên nhiều shard** sẽ nguyên tử xuyên cluster.

### 17.2. Transaction xuyên shard

MongoDB hỗ trợ distributed transactions trên sharded cluster theo yêu cầu triển khai. Chúng có thêm chi phí coordination, network và xử lý lỗi. Khi thiết kế:

- Chọn shard key và access pattern giúp giảm truy vấn phân tán không cần thiết.
- Không mặc định transaction xuyên nhiều shard có chi phí giống single-document update.
- Dùng timeout/budget phù hợp và quan sát transaction abort/write conflict.
- Xem xét khả năng đặt các field gắn cùng invariant trong cùng một document nếu quy mô/đường đọc cho phép.

Các quy tắc về transaction, sharding và phiên bản phải được đối chiếu với MongoDB Manual của bản đang chạy trước khi triển khai production.

## 18. Mẫu lỗi và cách phòng tránh

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Hai khoản rút 1.000 và 2.000 nhưng chỉ trừ 2.000 | Hai request đọc cùng giá trị cũ rồi $set | Dùng $inc hoặc version + conditional update |
| Số dư âm sau hai yêu cầu rút | $inc âm nhưng filter không kiểm tra đủ tiền | Thêm balance >= amount vào filter update |
| Payment status đã paid nhưng paymentReference chưa có | Hai field được sửa bằng hai update riêng | Gom trong một updateOne nếu cùng document |
| updateMany dừng giữa chừng, chỉ một phần order đổi trạng thái | Không nguyên tử toàn tập document | Transaction khi cần all-or-nothing, hoặc batch idempotent |
| bulkWrite ordered=true vẫn để lại update trước khi lỗi | Ordered không phải transaction | Xử lý partial success hoặc dùng transaction |
| Chuyển tiền chỉ bị trừ ví nguồn | Hai updateOne độc lập, crash ở giữa | Multi-document transaction hoặc giao thức bù trừ |
| Transaction vẫn commit số dư âm | Thiếu điều kiện nghiệp vụ trong filter | Kiểm tra invariant ngay trong thao tác ghi |
| Hai user cùng tạo email trùng | Check-then-insert không đồng bộ | Unique index và xử lý duplicate key |
| Version không bắt được update khác | Một số writer quên tăng/kiểm tra version | Thống nhất quy ước cho mọi đường ghi |
| findOneAndUpdate claim job nhưng job vẫn được xử lý lặp | Worker crash/retry sau claim, side effect ngoài DB | Lease/queue protocol và idempotency |
| Callback transaction gửi email hai lần | Callback có thể retry sau lỗi tạm thời | Không đặt side effect không idempotent trong callback |
| Hết thời gian chờ ghi, client retry $inc thủ công | Không biết ghi đã xảy ra hay chưa | Dùng retryable writes phù hợp và business idempotency key |
| Snapshot transaction vẫn vi phạm invariant hai document độc lập | Write skew, không có điểm ghi cạnh tranh chung | Guardian doc, ràng buộc hoặc mô hình transaction đúng |
| Rất nhiều write conflict ở một document stock | Hot document chịu cạnh tranh cao | Giới hạn concurrency, backoff hoặc phân vùng dữ liệu |
| Đọc giữa hai lệnh chuyển tiền thấy tổng ví thay đổi | Không có transaction xuyên hai document | Transaction hoặc mô hình ledger thích hợp |
| Transaction trên standalone bị lỗi | Topology không hỗ trợ multi-document transactions | Dùng replica set/sharded cluster phù hợp |
| Transaction quá lớn thường bị abort | Giữ tài nguyên lâu, xung đột hoặc vượt giới hạn | Thu nhỏ transaction boundary; batch/resume |
| Có atomic update nhưng dữ liệu mất sau failover | Atomicity khác durability/acknowledgment | Cấu hình write concern và phục hồi phù hợp |

## 19. Bài tập thực hành

### Bài 1 — Chuyển trạng thái một Order

Sau seed, dùng **updateOne** để chuyển order-101 từ draft sang paid, đồng thời cập nhật paidAt, paymentReference và version. Chạy lần thứ hai. Giải thích matchedCount ở hai lần và vì sao không có trạng thái “paid nhưng chỉ mới ghi một trong ba field” do chính update đó.

### Bài 2 — Mô phỏng lost update

Cho hai client A và B cùng đọc balanceCents của wallet-a bằng 10.000. A muốn rút 1.000, B muốn rút 2.000. Mô phỏng hai lệnh **$set** dựa trên snapshot cũ. Vì sao kết quả có thể là 8.000 thay vì 7.000, dù hai update đều nguyên tử?

### Bài 3 — Sửa lost update bằng $inc

Chạy lại seed và thực hiện hai **$inc** -1.000, -2.000 lên cùng ví. Dự đoán số dư cuối. Khi nào $inc là cách phù hợp hơn đọc–tính–$set? Nếu một khoản rút bị gửi lại hai lần, cần thêm điều gì?

### Bài 4 — Bảo vệ không âm

Viết updateOne rút 8.000 cents từ wallet-a khi chỉ còn 7.000. Filter phải có điều kiện balanceCents >= amount. Ghi matchedCount, modifiedCount và số dư cuối. Nêu vì sao một câu find kiểm tra tiền trước rồi update sau vẫn có race condition.

### Bài 5 — Optimistic concurrency

Hai người cùng đọc order-101 version 0 rồi mỗi người sửa shippingNote. Dùng filter version trong updateOne và $inc version. Dự đoán matchedCount của lệnh thứ hai và cách phản hồi conflict ở tầng HTTP/API.

### Bài 6 — Atomic Array update

Trên sku-001 có available=2 và reserved=0, viết một updateOne để chuyển 1 đơn vị sang reserved đồng thời thêm reservationId vào Array. Khi chạy lại với cùng reservationId, $addToSet có ngăn $inc chạy lần nữa không? Đề xuất filter hoặc cơ chế idempotency để tránh giữ chỗ trùng.

### Bài 7 — Claim một job bằng findOneAndUpdate

Dùng order-103 pending để mô phỏng một worker claim job. Sau claim, gọi lại cùng lệnh để xem có còn kết quả không. Nếu worker crash sau khi claim nhưng trước khi xử lý, quy trình cần bổ sung điều gì?

### Bài 8 — updateMany không phải transaction

Chạy updateMany đổi cả hai draft order của t001 sang pending. Giải thích atomicity áp dụng cho từng order như thế nào, và điều gì có thể xảy ra nếu lệnh bị gián đoạn sau khi chỉ một document được xử lý. Có thể giải quyết bằng một transaction trong trường hợp nào?

### Bài 9 — Chuyển tiền hai ví

Vẽ sơ đồ hai updateOne: debit wallet-a 3.000 và credit wallet-b 3.000. Chỉ ra trạng thái trung gian sau bước debit. Sau đó viết pseudocode transaction đảm bảo cả debit, credit và audit cùng commit hoặc cùng abort.

### Bài 10 — Phân tích Node.js transaction

Trong ví dụ transferOnce, bỏ **{session}** khỏi thao tác credit. Điều gì nguy hiểm có thể xảy ra khi transaction abort sau đó? Vì sao code phải kiểm tra matchedCount của debit/credit và throw khi không hợp lệ?

### Bài 11 — Transaction callback retry

Nếu callback withTransaction bị chạy lại sau transient error, việc gửi email trong callback có thể gây hậu quả gì? Đề xuất transactional outbox để phát thông báo sau commit.

### Bài 12 — Unique index

Hai request cùng kiểm tra email chưa tồn tại rồi cùng insert hai document. Vì sao mỗi insertOne nguyên tử vẫn không đảm bảo email duy nhất? Viết unique index theo tenantId/emailNormalized và mô tả cách xử lý duplicate key error.

### Bài 13 — Snapshot và write skew

Hai nhân viên A/B đều onCall=true, hệ thống yêu cầu ít nhất một người còn trực. Hai transaction mỗi cái sửa một document khác nhau dựa trên snapshot ban đầu có thể gặp vấn đề gì? Đề xuất một guardian document và conditional write để bảo vệ invariant.

### Bài 14 — Thiết kế document boundary

Phân loại các tình huống: cập nhật trạng thái/paidAt của Order, chuyển tồn kho available/reserved, chuyển tiền giữa hai Wallet, xóa User cùng Orders, gửi email khi Order paid. Chọn một-document update, transaction, unique index, outbox hoặc saga thích hợp và giải thích đánh đổi.

### Bài 15 — Unknown result và retry

Client gửi một lệnh rút tiền bằng $inc, nhưng kết nối đứt trước khi nhận response. Những trạng thái nào có thể xảy ra? Vì sao không được tự gửi lại một $inc mới mà không có cơ chế idempotency? Phân biệt retryable write của driver với gửi lại một HTTP request mới.

### Bài 16 — Quan sát xung đột ghi

Giả sử một SKU rất phổ biến bị cập nhật hàng nghìn lần mỗi giây. Thiết kế thí nghiệm đo **matchedCount**, write latency, tần suất conflict/retry và mức cạnh tranh. Đề xuất hai thay đổi mô hình dữ liệu hoặc luồng xử lý để giảm hot spot mà không làm mất invariant tồn kho.

## 20. Tài liệu tham khảo chính thức

- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Manual — [db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/).
- MongoDB Manual — [db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/).
- MongoDB Manual — [db.collection.findOneAndUpdate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/).
- MongoDB Manual — [db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/).
- MongoDB Manual — [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Node.js Driver — [Transactions](https://www.mongodb.com/docs/drivers/node/current/fundamentals/transactions/).

**Kết luận:** MongoDB bảo đảm **một thao tác ghi trên một document là nguyên tử**, kể cả khi sửa nhiều field hoặc phần tử Array. Điều đó không tự ngăn **lost update**, **rút quá số dư**, hay **trùng request** nếu ứng dụng dùng read–modify–write và filter thiếu điều kiện. Hãy dùng **$inc, conditional updates, version và findOneAndUpdate** để bảo vệ các invariant nằm trong một document. Với nhiều document, **updateMany, deleteMany và bulkWrite không mặc nhiên all-or-nothing**; khi cần commit/abort chung, dùng **multi-document transaction** với session, kiểm tra nghiệp vụ và xử lý lỗi/retry đúng cách. Thiết kế document boundary theo invariant, vòng đời và tải đồng thời là chìa khóa để đạt tính đúng đắn mà không trả chi phí transaction không cần thiết.
