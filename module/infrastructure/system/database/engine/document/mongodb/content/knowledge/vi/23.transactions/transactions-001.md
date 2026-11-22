# Khi nào cần giao dịch nhiều document

MongoDB bảo đảm **một thao tác ghi trên một document là nguyên tử (atomic)**, kể cả khi thao tác đó sửa nhiều field hoặc nhiều phần tử của một mảng. Chính vì thế, không phải cứ có hai giá trị phải thay đổi cùng nhau là cần mở **multi-document transaction**. Nếu những giá trị đó cùng nằm trong một document có mô hình hợp lý, một `updateOne()` có điều kiện thường đã đủ.

**Giao dịch nhiều document (multi-document transaction)** trở nên cần thiết khi một **bất biến nghiệp vụ (business invariant)** hoặc một thao tác **all-or-nothing** phải bao trùm **nhiều documents**, nhiều collections, hoặc nhiều shards, và ứng dụng **không được phép chấp nhận trạng thái chỉ thực hiện một phần**. Khi đó transaction cho phép nhóm các writes trong một ranh giới commit/abort chung.

Ví dụ: chuyển tiền từ tài khoản A sang B đòi cả **trừ tiền ở A** lẫn **cộng tiền ở B** phải có hiệu lực; một lệnh update trên A không tự bảo vệ document của B. Nhưng nếu chỉ tăng số lượng hàng trong *một* inventory document, dùng transaction nhiều document là không cần thiết.

Bài thuộc chương **Giao dịch** của module *Database Engine Document MongoDB*. Trọng tâm là **nhận diện đúng thời điểm cần transaction**, thiết kế phạm vi transaction nhỏ, sử dụng session và xử lý cạnh tranh, cùng những trường hợp **không nên dùng transaction** dù dữ liệu nằm trong nhiều documents.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **single-document atomicity**, **multi-document atomicity**, **read isolation**, **write concern** và **idempotency**.
2. Xác định bất biến nghiệp vụ đang nằm trong một document hay trải qua nhiều documents/collections.
3. Quyết định khi nào nên **nhúng dữ liệu**, dùng **conditional update**, dùng **unique index**, hay mở **multi-document transaction**.
4. Chỉ ra vì sao `updateMany()`, `insertMany()` và `bulkWrite()` **không tự là giao dịch toàn nhóm**.
5. Thiết kế các tình huống chuyển tiền, đặt nhiều SKU, tạo order kèm reservation và cập nhật ledger bằng transaction.
6. Hiểu read/write concern, snapshot, write conflict, commit không rõ kết quả và retry.
7. Viết transaction bằng `mongosh` và **MongoDB Java Sync Driver**, sử dụng đúng `ClientSession`.
8. Nhận ra các giới hạn transaction khi có **external services**, hot documents, tài nguyên lớn, shard/DDL hoặc consistency invariant không được bảo vệ đúng.
9. Áp dụng một **bảng quyết định** trước khi đưa transaction vào hệ thống.

> **Môi trường và phiên bản:** MongoDB hỗ trợ multi-document transactions trên **replica set** và **sharded cluster** với phiên bản hỗ trợ; không chạy transaction nhiều document trên một `mongod` standalone như thể nó là replica set. Ví dụ dùng database riêng `txn_need_lab`, minh họa các API phổ biến trong MongoDB hiện đại. Các giới hạn về lifetime, create collection/index trong transaction, read/write concern và retry khác nhau theo phiên bản server/driver; phải xem tài liệu phù hợp với deployment thực tế. Không thực thi demo trên production.

## 1. Ranh giới nguyên tử: một document khác nhiều documents

Một thao tác ghi MongoDB lên **một document** bảo đảm các thay đổi trong thao tác đó được áp dụng cùng nhau:

~~~javascript
db.inventory.updateOne(
  {
    _id: "SKU-001",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2,
      reserved: 2
    }
  }
)
~~~

Trong `SKU-001`, hai field `available` và `reserved` cùng đổi trong **một update**. Nếu filter không thỏa, cả hai đều không đổi. Có nhiều clients đồng thời, MongoDB kiểm tra filter tại lúc ghi; điều kiện `available >= 2` giúp không đặt vượt số lượng còn lại trong document này.

Tương phản, một nghiệp vụ phải cập nhật **hai documents**:

~~~javascript
// A giảm số dư.
db.accounts.updateOne(
  { _id: "ACC-A" },
  { $inc: { balance: -150 } }
)

// B tăng số dư.
db.accounts.updateOne(
  { _id: "ACC-B" },
  { $inc: { balance: 150 } }
)
~~~

Mỗi `updateOne` nguyên tử với document riêng của nó. Nhưng nếu lệnh đầu thành công còn lệnh sau thất bại, MongoDB **không tự rollback** ACC-A. Hai lệnh nối tiếp không có **all-or-nothing** chung.

### 1.1. Các thuật ngữ dễ nhầm

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| **Atomicity** | Một nhóm thay đổi có thể xảy ra **một phần** không? | Debit A và credit B cùng commit/abort. |
| **Isolation** | Những thao tác đồng thời có thể quan sát/xen vào trạng thái thế nào? | Một transaction đọc snapshot, writer khác cùng sửa tài liệu. |
| **Consistency** | Bất biến nghiệp vụ nào cần duy trì? | Tổng số tiền/stock phải khớp ledger. |
| **Durability / write concern** | Ghi được xác nhận ở replica và bền vững tới mức nào? | `w:"majority"`. |
| **Idempotency** | Gửi lại cùng *yêu cầu nghiệp vụ* có nhân đôi tác động không? | Transfer ID không được chuyển tiền hai lần. |
| **Retryable write / transaction retry** | Driver có thể thử lại lỗi kỹ thuật nào? | `TransientTransactionError`, `UnknownTransactionCommitResult`. |

**Transaction không tự định nghĩa bất biến nghiệp vụ.** Nếu ứng dụng gửi debit 150 và credit 120 **trong cùng transaction**, MongoDB có thể commit cả hai dù tổng tiền sai. Transaction bảo đảm **cùng commit/abort theo lệnh đã viết**, còn điều kiện amount, balance và đối soát là trách nhiệm logic nghiệp vụ.

### 1.2. Tính nguyên tử của các nhóm lệnh

| Cách ghi | Phạm vi atomic mặc định |
|---|---|
| `insertOne`, `updateOne`, `replaceOne`, `deleteOne` | Một document. |
| `findOneAndUpdate` với predicate | Một document, có thể trả bản trước/sau update. |
| `updateMany`, `deleteMany` | Từng document riêng lẻ; **không all-or-nothing trên toàn bộ documents**. |
| `insertMany` | Không tự rollback mọi insert trước đó khi lỗi một phần. |
| `bulkWrite`, kể cả `ordered:true` | Thứ tự/dừng khi lỗi **không đồng nghĩa** transaction toàn batch. |
| Các writes trong cùng một **transaction** được commit thành công | Cùng commit; nếu abort thì không áp dụng các writes của transaction. |

### 1.3. Khi nhiều field có thể nằm chung document

~~~javascript
{
  _id: "ORDER-1",
  state: "DRAFT",
  confirmedAt: null,
  totals: { subtotal: 150, tax: 15, grandTotal: 165 },
  items: [
    { sku: "PEN", qty: 3, price: 20 },
    { sku: "BOOK", qty: 1, price: 90 }
  ]
}
~~~

Nếu xác nhận order chỉ đổi `state`, `confirmedAt` và `totals`, một update nguyên tử trên `ORDER-1` đủ để giữ chúng nhất quán:

~~~javascript
db.orders.updateOne(
  { _id: "ORDER-1", state: "DRAFT" },
  {
    $set: {
      state: "CONFIRMED",
      confirmedAt: new Date(),
      totals: { subtotal: 150, tax: 15, grandTotal: 165 }
    }
  }
)
~~~

Không nên chia thao tác này thành nhiều `updateOne` riêng nếu có thể biểu diễn bằng một update; nhưng cũng **không cần một transaction nhiều document** cho chính thao tác trên một order.

## 2. Câu hỏi quyết định: “Có cần all-or-nothing giữa nhiều documents không?”

Để chọn đúng, hãy bắt đầu với **invariant**, không bắt đầu với số collections.

~~~text
Xác định invariant nghiệp vụ
         |
         v
Có thể đặt tất cả trạng thái cần cập nhật
trong MỘT document hợp lý không?
         |
       +---+
       |
    Có|                          Không
       v                            |
  Một conditional update            v
  + CAS/version nếu cần      Nhiều documents cần thay đổi
                                    |
                                    v
                      Có chấp nhận trạng thái một phần,
                      rồi reconcile/bù trừ sau không?
                             |                |
                            Có               Không
                             |                |
                             v                v
                       Batches, saga,      Transaction
                       outbox, eventual    nếu hệ thống hỗ trợ
                       consistency         và phạm vi phù hợp
~~~

### 2.1. Ba tiêu chí khiến transaction thường là lựa chọn đúng

**Thứ nhất: Có ít nhất hai thay đổi độc lập ở các documents khác nhau.** Ví dụ một reservation record trong `reservations` và một inventory item trong `stock`, hoặc hai account documents.

**Thứ hai: Nghiệp vụ không cho phép commit một phần.** Nếu reservation được lưu nhưng stock chưa giảm, hệ thống có thể bán vượt. Nếu debit đã ghi nhưng credit chưa ghi, sổ cái tạm thời sai.

**Thứ ba: Không có mô hình một document hoặc cơ chế nghiệp vụ khác phù hợp hơn.** Nhúng dữ liệu có thể làm document quá lớn, nhiều writers tranh chấp, hoặc các entity có vòng đời độc lập. Khi muốn giữ chúng là documents riêng mà vẫn all-or-nothing, transaction là ứng viên.

### 2.2. Nhiều documents **chưa đủ** để kết luận cần transaction

Ví dụ:

- Import 100.000 catalog documents. Có thể chấp nhận 10.000 document đầu được chèn, tiếp tục batch sau và retry theo ID.
- Cập nhật hàng nghìn tài liệu thêm `schemaVersion:2`. Mỗi record có thể đổi độc lập và hệ thống hỗ trợ đọc song song hai phiên bản trong giai đoạn migration.
- Ghi log/audit/analytics không ảnh hưởng kết quả nghiệp vụ chính và có thể eventual.
- Đếm view hoặc aggregate dashboard có thể chậm vài giây.
- Xóa soft-deleted records theo retention policy có thể tiến dần.

Đây là các trường hợp có **nhiều writes**, nhưng thường **không có invariant yêu cầu tất cả records cùng commit tại một thời điểm**. Dùng transaction rất lớn chỉ để tránh trạng thái “job chưa xong” có thể tốn tài nguyên và khó khôi phục hơn batching idempotent.

### 2.3. Unique index có thể thay transaction trong bài toán duy nhất

Hai clients cùng tạo account với email `"an@example.test"`. Nếu chỉ cần **không có hai documents mang cùng email**, một **unique index** trên email/canonical email phù hợp thường bảo vệ tốt hơn pattern:

~~~javascript
const existing = db.users.findOne({ email: "an@example.test" })
if (!existing) {
  db.users.insertOne({ email: "an@example.test" })
}
~~~

Pattern check-then-insert có race. Unique index chặn duplicate khi ghi, không yêu cầu transaction mở giữa `findOne` và `insertOne`. Ứng dụng vẫn phải xử lý `E11000`. Nếu **tạo user** còn phải tạo **wallet**, **billing profile** và cả ba phải cùng xuất hiện, yêu cầu đó mới có thể cần transaction trên nhiều documents.

## 3. Bộ dữ liệu thực hành

Dùng database `txn_need_lab` và các collection khác nhau để minh họa. Script giả định fixtures chưa tồn tại; **chỉ chạy trên môi trường demo**. Chạy lại với cùng `_id` sẽ gặp duplicate key — không xóa collection production để tái tạo.

~~~javascript
const lab = db.getSiblingDB("txn_need_lab")

lab.accounts.insertMany([
  {
    _id: "A",
    owner: "Lan",
    currency: "VND",
    balance: NumberLong(1000)
  },
  {
    _id: "B",
    owner: "Minh",
    currency: "VND",
    balance: NumberLong(200)
  }
])

lab.inventory.insertMany([
  {
    _id: "SKU-RED",
    available: 5,
    reserved: 0,
    version: 1
  },
  {
    _id: "SKU-BLUE",
    available: 2,
    reserved: 0,
    version: 1
  }
])

lab.orders.insertOne({
  _id: "O-100",
  customerId: "C-1",
  status: "DRAFT",
  items: [
    { sku: "SKU-RED", qty: 3 },
    { sku: "SKU-BLUE", qty: 1 }
  ],
  total: 480,
  version: 1
})

lab.profiles.insertOne({
  _id: "C-1",
  displayName: "Khách hàng A",
  addresses: [
    { label: "home", city: "Hà Nội" }
  ]
})

// Tạo trước collections/indexes cho demo transaction.
lab.createCollection("transfers")
lab.createCollection("reservations")
lab.createCollection("outbox")

lab.transfers.createIndex(
  { requestId: 1 },
  { unique: true, name: "ux_transfer_request" }
)

lab.reservations.createIndex(
  { orderId: 1, sku: 1 },
  { unique: true, name: "ux_order_sku" }
)
~~~

Với hệ thống tài chính thật, số tiền phải dùng **integer minor units** hoặc **BSON Decimal128** theo currency/precision chuẩn, có kiểm toán và đối soát. Ví dụ dùng số nguyên nhỏ để làm rõ transaction, **không phải** một kiến trúc banking/ledger production-ready.

### 3.1. Các invariant được dùng trong bài

| Nghiệp vụ | Invariant | Ranh giới dữ liệu |
|---|---|---|
| Đổi tên hiển thị/địa chỉ | Các field profile được cập nhật cùng nhau. | Một document `profiles.C-1`. |
| Giảm tồn một SKU | `available >= 0`; tăng reserved cùng lượng giảm available. | Một document `inventory.SKU-RED`. |
| Chuyển tiền A → B | Debit A và credit B phải cùng hoàn thành. | Hai documents trong `accounts`. |
| Đặt một order gồm hai SKU | Giữ đủ mọi SKU hoặc không giữ SKU nào. | Hai inventory documents, thêm reservation/order. |
| Tạo user cùng wallet | Không được có user mà thiếu wallet nếu domain bắt buộc. | Hai collections. |
| Cập nhật status rồi gửi email | MongoDB state phải nhất quán với ý định phát event. | MongoDB + hệ thống ngoài; cần outbox/consumer. |

## 4. Các trường hợp **không cần** giao dịch nhiều document

### 4.1. Một document và một conditional update

~~~javascript
const lab = db.getSiblingDB("txn_need_lab")

const result = lab.inventory.updateOne(
  {
    _id: "SKU-RED",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2,
      reserved: 2
    }
  }
)

printjson(result)
~~~

Trong fixture, nếu update chạy một lần thì SKU-RED chuyển từ `available:5,reserved:0` sang `available:3,reserved:2`. Nếu hai clients đặt quá số còn lại, filter `available >= 2` được đánh giá ở lúc cập nhật, giúp tránh giảm xuống số âm. **Không cần multi-document transaction** khi chỉ có một stock document và không phải ghi reservation record trong cùng atomic business operation.

### 4.2. CAS chống lost update trên một document

~~~javascript
const expectedVersion = 1

const result = lab.orders.updateOne(
  { _id: "O-100", version: expectedVersion, status: "DRAFT" },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 }
  }
)

if (result.matchedCount === 0) {
  print("Có thể đã bị cập nhật bởi request khác.")
}
~~~

CAS/filter theo `version` giúp phát hiện concurrent modification; tránh `findOne` rồi `$set` trên snapshot cũ. Giao dịch nhiều document không thay thế việc thiết kế đúng **state transition** khi chỉ sửa một order.

### 4.3. Nhúng những phần có vòng đời và invariant chung

`profiles.C-1` có mảng `addresses` nhỏ, thường đọc cùng user profile. Nếu chỉ thay địa chỉ home và `updatedAt`, cả hai nằm trong một document nên có thể dùng một update:

~~~javascript
lab.profiles.updateOne(
  { _id: "C-1", "addresses.label": "home" },
  {
    $set: {
      "addresses.$.city": "Đà Nẵng",
      updatedAt: new Date()
    }
  }
)
~~~

Nhúng dữ liệu **không phải luôn tốt**: mảng không giới hạn như hàng triệu audit events, quan hệ many-to-many, dữ liệu cập nhật độc lập tần suất cao dễ tạo document lớn/hot. Nếu cần nhiều documents riêng, quyết định transaction dựa trên invariant của những documents đó.

### 4.4. Nhiều document nhưng **không** cần all-or-nothing

~~~javascript
lab.orders.updateMany(
  { migrationVersion: { $ne: 3 } },
  { $set: { migrationVersion: 3 } }
)
~~~

Đây không atomic trên toàn collection, nhưng nếu ứng dụng hỗ trợ đồng thời version 2 và 3, có thể chạy theo lô, checkpoint, retry, reconcile. Transaction toàn bộ migration thường không cần thiết.

### 4.5. Dùng unique constraint thay vì transaction chống duplicate

~~~javascript
lab.orders.createIndex(
  { customerId: 1, externalOrderNo: 1 },
  { unique: true, name: "ux_customer_orderNo" }
)
~~~

Nếu chỉ cần mỗi khách không có hai order mang cùng externalOrderNo, unique compound index trực tiếp thực thi constraint khi ghi. Transaction không tự thay thế unique index; ngay trong transaction, hai documents trùng unique key vẫn bị từ chối. Tuy nhiên, nếu mỗi order còn phải cập nhật inventory hoặc ledger cùng commit, có thể cần transaction cho **những thao tác đó**.

## 5. Trường hợp kinh điển: chuyển giá trị giữa hai documents

Giả sử hai tài khoản trong fixture có số dư:

~~~text
Account A: 1000
Account B:  200
Tổng:      1200
~~~

Một nghiệp vụ chuyển **150** từ A sang B có trạng thái hợp lệ:

~~~text
Account A:  850
Account B:  350
Tổng:      1200
~~~

Yêu cầu **không được** để trạng thái dài hạn `A=850,B=200` hoặc `A=1000,B=350`. Vì hai account là **hai MongoDB documents**, một `updateOne()` không thể thay đổi cả hai trong một ranh giới atomic. Đây là ứng viên rõ ràng cho multi-document transaction.

### 5.1. Rủi ro khi chạy hai update độc lập

~~~javascript
const lab = db.getSiblingDB("txn_need_lab")

const debit = lab.accounts.updateOne(
  { _id: "A", currency: "VND", balance: { $gte: 150 } },
  { $inc: { balance: -150 } }
)

// Giả sử tiến trình bị tắt đột ngột trước bước credit.
const credit = lab.accounts.updateOne(
  { _id: "B", currency: "VND" },
  { $inc: { balance: 150 } }
)
~~~

Phần **debit** có thể đã thành công. Nếu phần **credit** chưa chạy hoặc không match B, trạng thái sổ cái bị lệch. Hai update có filter đúng cũng không tạo **all-or-nothing** giữa hai documents.

### 5.2. Vì sao không nhúng tất cả accounts vào một document?

Về kỹ thuật, bạn có thể thiết kế một document `bank.accounts[]` chứa mọi tài khoản để sửa chúng nguyên tử. Nhưng mô hình đó không thực tế:

- Tài khoản có vòng đời, quyền truy cập và số lượng độc lập.
- Một document có giới hạn **16 MiB BSON**.
- Hàng trăm writers cùng cạnh tranh cập nhật một document cực nóng.
- Khó index và truy vấn tài khoản riêng một cách hiệu quả.
- Khó chia dữ liệu theo tenant/shard/retention policy.

Transaction cho phép giữ **mỗi account là document riêng** và vẫn bảo vệ nghiệp vụ chuyển giá trị khi cần commit/abort chung.

### 5.3. Cần thêm một transfer record

Giao dịch hai balances có thể đúng mà vẫn khó **nhận biết request đã được xử lý chưa** khi client timeout. Vì vậy một mô hình thực tế thường có `transfers` hoặc ledger records với `requestId`/`transferId` ổn định:

~~~javascript
{
  _id: "TX-1001",
  requestId: "TX-1001",
  fromAccountId: "A",
  toAccountId: "B",
  amount: NumberLong(150),
  currency: "VND",
  state: "POSTED",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

Transfer record, debit và credit cần được ghi **trong cùng transaction** nếu mọi thứ phải đúng cùng lúc. Unique index trên `requestId` giúp phát hiện một yêu cầu được gửi lặp (sau đó phải kiểm tra **payload gốc có khớp** không).

> **Phạm vi ví dụ:** Đây là mô phỏng chuyển giá trị bằng số nguyên. Hệ thống thanh toán thực phải có ledger, idempotency toàn hệ thống, kiểm toán, trạng thái pending/settlement, risk controls, currency precision, tích hợp payment provider và reconciliation. Không dùng mỗi ví dụ balance này làm hệ thống tài chính production.

## 6. Ví dụ transaction bằng `mongosh`

Script sau dùng **`ClientSession` ở phía shell** thông qua `startSession()` và helper `withTransaction()`. Cần chạy trên replica set/sharded cluster hỗ trợ transactions. Collection `accounts` và `transfers`, unique index đã được chuẩn bị ở mục 3.

### 6.1. Gọi `withTransaction` và kiểm tra business conditions

~~~javascript
const lab = db.getSiblingDB("txn_need_lab")
const session = db.getMongo().startSession()
const txdb = session.getDatabase("txn_need_lab")

const transferId = "TX-1001"
const amount = NumberLong(150)

try {
  await session.withTransaction(async () => {
    // Trạng thái transfer và balances đều nằm trong transaction.
    txdb.transfers.insertOne({
      _id: transferId,
      requestId: transferId,
      fromAccountId: "A",
      toAccountId: "B",
      amount,
      currency: "VND",
      state: "POSTED",
      createdAt: ISODate("2026-11-14T08:00:00Z")
    })

    const debit = txdb.accounts.updateOne(
      {
        _id: "A",
        currency: "VND",
        balance: { $gte: amount }
      },
      { $inc: { balance: NumberLong(-150) } }
    )

    if (debit.matchedCount !== 1) {
      throw new Error("Account A missing or insufficient funds")
    }

    const credit = txdb.accounts.updateOne(
      { _id: "B", currency: "VND" },
      { $inc: { balance: amount } }
    )

    if (credit.matchedCount !== 1) {
      throw new Error("Account B missing")
    }
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  print("Transaction committed")
} finally {
  session.endSession()
}

lab.accounts.find().sort({ _id: 1 })
lab.transfers.findOne({ _id: transferId })
~~~

Với fixtures ban đầu, nếu transaction commit thành công, A còn **850**, B có **350**, và transfer TX-1001 được ghi. Nếu một trong các điều kiện debit/credit không match, callback ném exception và helper thực hiện abort theo semantics của driver/session.

**Tất cả thao tác ghi bên trong callback dùng `txdb` lấy từ `session.getDatabase(...)`**, không dùng nhầm `lab.accounts` không nằm trong session. Một write bên ngoài session **không được transaction bao trùm**.

### 6.2. Tại sao dùng helper thay vì tự retry mọi lỗi?

`withTransaction()` và driver transaction API hỗ trợ xử lý những retry cases được phép, gồm **`TransientTransactionError`** và **`UnknownTransactionCommitResult`** theo quy định. Một callback transaction **có thể được thực hiện lại**, nên:

- Không gọi payment gateway, gửi email hay publish message **trực tiếp trong callback**.
- Không dùng biến ngoài callback để cộng dồn số lần debit mà không đặt lại.
- Không tự retry vô hạn một business exception như “insufficient funds”.
- Không coi mỗi lỗi client nhận được là “transaction chưa commit”; outcome của commit có thể **không rõ**.
- Dùng một **business operation ID** ổn định khi request được gửi lại ở cấp API, không tạo ID mới cho cùng nghiệp vụ.

Nếu người dùng gửi lại TX-1001 như một **HTTP request mới** sau khi transaction trước đã commit, insert transfer ID có thể bị duplicate key. Ứng dụng nên **tra transfer đã có và đối chiếu amount/from/to/currency**, rồi trả kết quả idempotent nếu cùng nghiệp vụ; không tự mở transaction TX-1002 để debit/credit lại.

### 6.3. Đọc trạng thái sau commit

Trong demo:

~~~javascript
const a = lab.accounts.findOne({ _id: "A" })
const b = lab.accounts.findOne({ _id: "B" })
const transfer = lab.transfers.findOne({ _id: "TX-1001" })

printjson({ a, b, transfer })
~~~

Nếu kiểm tra bằng nhiều reads độc lập trong môi trường đang có writes song song, giá trị có thể tiếp tục đổi sau commit. Khi cần một snapshot nhất quán cho **báo cáo nhiều documents**, phải thiết kế read concern/snapshot phù hợp. Transaction ghi thành công **không biến mọi dãy lệnh find sau đó** thành một snapshot bất biến.

### 6.4. Điều kiện phiên bản và prepared metadata

`insertOne` trên một collection mới chưa có index hoặc tạo collection giữa transaction có những giới hạn thay đổi theo server version và topology. Demo tạo `transfers` và unique index **trước** transaction. Production nên triển khai schema/indexes cùng migration, không tạo index bất chợt giữa mỗi giao dịch.

### 6.5. Một biến thể có audit ghi cùng transaction

Nếu business yêu cầu thêm hai ledger entries — DEBIT ở A và CREDIT ở B — và cả hai cùng balance update, có thể thêm `insertMany` vào ledger **trong transaction**. Nhưng ledger phải có unique event/transfer keys, schema hợp lệ và kiểm soát mỗi entry debit/credit. MongoDB chỉ bảo đảm các writes đã được yêu cầu được commit cùng nhau; không tự chứng minh tổng debit bằng tổng credit.

## 7. Khi một order cần nhiều SKU: transaction hay saga?

Giả sử order O-100 cần:

~~~text
SKU-RED: cần 3; available hiện 5.
SKU-BLUE: cần 1; available hiện 2.
~~~

Nghiệp vụ yêu cầu **chỉ xác nhận order nếu đủ hàng ở cả hai SKU**. Khi có nhiều orders đồng thời, stock của SKU-RED và SKU-BLUE có thể thay đổi giữa các request.

### 7.1. Hai conditional updates **chưa** bảo vệ toàn order

~~~javascript
const red = lab.inventory.updateOne(
  { _id: "SKU-RED", available: { $gte: 3 } },
  { $inc: { available: -3, reserved: 3 } }
)

const blue = lab.inventory.updateOne(
  { _id: "SKU-BLUE", available: { $gte: 1 } },
  { $inc: { available: -1, reserved: 1 } }
)
~~~

Mỗi update bảo vệ **một SKU** không bị giảm âm. Nhưng nếu red thành công còn blue hết hàng, red vẫn bị giữ. Nếu nghiệp vụ **không cho phép trạng thái giữ một phần**, transaction là lựa chọn trực tiếp.

### 7.2. Gói inventory updates và order transition

~~~javascript
const session = db.getMongo().startSession()
const txdb = session.getDatabase("txn_need_lab")

try {
  await session.withTransaction(async () => {
    const red = txdb.inventory.updateOne(
      { _id: "SKU-RED", available: { $gte: 3 } },
      { $inc: { available: -3, reserved: 3 } }
    )
    if (red.matchedCount !== 1) {
      throw new Error("SKU-RED unavailable")
    }

    const blue = txdb.inventory.updateOne(
      { _id: "SKU-BLUE", available: { $gte: 1 } },
      { $inc: { available: -1, reserved: 1 } }
    )
    if (blue.matchedCount !== 1) {
      throw new Error("SKU-BLUE unavailable")
    }

    const order = txdb.orders.updateOne(
      { _id: "O-100", status: "DRAFT" },
      {
        $set: {
          status: "RESERVED",
          reservedAt: ISODate("2026-11-14T09:00:00Z")
        },
        $inc: { version: 1 }
      }
    )
    if (order.matchedCount !== 1) {
      throw new Error("Order already processed or missing")
    }

    txdb.reservations.insertMany([
      { _id: "O-100-RED", orderId: "O-100", sku: "SKU-RED", qty: 3 },
      { _id: "O-100-BLUE", orderId: "O-100", sku: "SKU-BLUE", qty: 1 }
    ])
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })
} finally {
  session.endSession()
}
~~~

Nếu mọi bước thành công và commit, stock, order và reservation records cùng có hiệu lực. Nếu SKU-BLUE không đủ hoặc order đã được xử lý, transaction abort và reservation SKU-RED **không bị giữ lại** từ transaction đó.

**Lưu ý thực thi:** Ví dụ trên giả định một request O-100 chạy từ fixture ban đầu. Không chạy lại ngay sau ví dụ reservation độc lập ở mục 4; state sẽ khác. Trong hệ thống thật, dùng orderId/eventId ổn định và unique `(orderId,sku)` để nhận biết replay; cần đối soát khi đã xử lý, không đơn giản retry với số lượng mới.

### 7.3. Vì sao cần cả filter theo status và unique reservation key?

Nếu hai requests cùng xử lý O-100:

- Filter `status:"DRAFT"` giúp không chuyển trạng thái từ RESERVED thêm lần nữa.
- Unique reservation key `(orderId,sku)` chặn duplicate line reservation.
- Conditional stock update giúp không giữ vượt available.
- Transaction gắn những thay đổi **cùng commit/abort**.

Bốn lớp kiểm soát giải quyết **bốn rủi ro khác nhau**. Có transaction không có nghĩa có thể bỏ unique keys và business filters. Nếu order bị cập nhật bởi request khác, transaction có thể gặp write conflict hoặc match 0; application cần phân loại đúng.

### 7.4. Khi saga hợp lý hơn

Không phải mọi hệ thống cần đồng thời commit ở thời điểm giữ từng SKU. Một marketplace có thể cho phép:

~~~text
Order -> PENDING_RESERVATION
    |
    +--> Giữ RED với reservationId
    |
    +--> Giữ BLUE với reservationId
              |
         +----+----+
         |         |
       Đủ hết     Thiếu/lỗi
         |         |
         v         v
   CONFIRMED     Release RED
                 (compensation)
                 Order FAILED
~~~

Đây là **saga / reservation workflow**: có trạng thái trung gian, **timeout**, **expiry**, **idempotent release**, **repair worker** và monitoring. Nó chấp nhận eventual consistency nhưng mở rộng tốt hơn với những hệ thống phân tán/phân quyền độc lập, nếu nghiệp vụ cho phép tạm giữ một phần.

Nếu “không bao giờ thấy order giữ một phần SKU” là yêu cầu cứng ở MongoDB, transaction ngắn vẫn phù hợp hơn. Nếu nghiệp vụ cho phép trạng thái PENDING và có compensation, không nhất thiết cần transaction kéo dài qua nhiều services.

## 8. Tạo hai documents ở hai collections: user và wallet

Một trường hợp khác: đăng ký người dùng bắt buộc phải có cả:

~~~javascript
// users:
{
  _id: "U-100",
  emailCanonical: "an@example.test",
  status: "ACTIVE"
}

// wallets:
{
  _id: "W-U-100",
  userId: "U-100",
  available: NumberLong(0),
  currency: "VND"
}
~~~

Nếu domain yêu cầu **không bao giờ tồn tại user ACTIVE mà không có wallet**, thì hai inserts phải cùng commit/abort hoặc được tổ chức theo một lifecycle phù hợp.

### 8.1. Transaction là một lựa chọn trực tiếp

~~~javascript
const session = db.getMongo().startSession()
const txdb = session.getDatabase("txn_need_lab")

try {
  await session.withTransaction(async () => {
    txdb.users.insertOne({
      _id: "U-100",
      emailCanonical: "an@example.test",
      status: "ACTIVE"
    })

    txdb.wallets.insertOne({
      _id: "W-U-100",
      userId: "U-100",
      available: NumberLong(0),
      currency: "VND"
    })
  }, {
    writeConcern: { w: "majority" }
  })
} finally {
  session.endSession()
}
~~~

**Chuẩn bị trước** collections `users`/`wallets`, unique index email và userId khi production cần; một số thay đổi metadata trong transaction bị giới hạn theo topology/version. Sau commit, cả hai documents cùng tồn tại. Nếu ví dụ được chạy trên database chưa có `users`/`wallets`, hành vi tạo collection trong transaction phụ thuộc phiên bản và sharding; nên tạo sẵn ngoài transaction cho bài thực hành.

### 8.2. Có thể không cần transaction bằng lifecycle

Nếu domain **cho phép user tồn tại tạm ở trạng thái PENDING**:

~~~text
Create user: status = PENDING_WALLET
       |
       v
Create wallet idempotently
       |
       v
Set user status = ACTIVE
~~~

Luồng này có thể dùng những writes độc lập, retry/reconcile sau lỗi. Điều kiện thiết yếu: các thành phần khác **không được coi PENDING là ACTIVE**, và phải có worker sửa user bị kẹt. Như vậy nghiệp vụ không yêu cầu “hai documents cùng tồn tại ngay lập tức”, mà yêu cầu “user chỉ được ACTIVE khi wallet đã sẵn sàng”. **Định nghĩa lại trạng thái hợp lệ** có thể loại bỏ nhu cầu transaction toàn flow.

### 8.3. Vì sao chỉ unique index chưa đủ?

Unique index trên `users.emailCanonical` ngăn hai user trùng email. Unique index trên `wallets.userId` ngăn hai wallets trùng userId. Nhưng **hai unique indexes riêng** không bảo đảm “nếu user được insert thì wallet cũng phải được insert”. Đó là một **ràng buộc tồn tại xuyên documents/collections**, cần transaction hoặc workflow đảm bảo một trạng thái trung gian được phép.

## 9. Transaction để đọc snapshot nhất quán: khi nào thật sự cần?

Đến đây các ví dụ đều là **giao dịch ghi**. Nhưng có những use cases đọc nhiều documents và cần các giá trị tương ứng **cùng một ảnh chụp dữ liệu**: kiểm toán số dư, phát hành báo cáo chốt kỳ, ra quyết định dựa trên nhiều records liên quan.

### 9.1. Hai lệnh đọc độc lập có thể thấy hai thời điểm khác nhau

~~~text
T0: A=1000, B=200

Reader: read A -> 1000
Writer: chuyển 150 từ A sang B trong một transaction, commit
Reader: read B -> 350

Reader tính A+B = 1350, dù trước và sau transfer tổng đều 1200.
~~~

Đây không phải lỗi atomicity của transaction writer; reader đã lấy **hai snapshot khác thời điểm**. Nếu muốn tổng từ **cùng một thời điểm logic**, phải sử dụng **read concern/snapshot semantics** phù hợp, có thể là read-only transaction với `readConcern:"snapshot"` khi yêu cầu hỗ trợ.

### 9.2. Read-only snapshot không phải luôn cần

Nếu dashboard chấp nhận số liệu trễ hoặc không đồng bộ vài giây, một transaction đọc snapshot có thể không cần. Nếu báo cáo cho mục đích pháp lý/chốt sổ/đối soát đòi **nhất quán nhiều documents**, mới nên thiết kế read path có snapshot/transaction hoặc một dữ liệu chốt sổ versioned.

Không nên mở read-only transaction dài vài phút để người dùng cuộn màn hình. Nó có thể giữ snapshot, tăng pressure lên storage history và gây chi phí cho cluster.

### 9.3. Snapshot không tự làm mọi invariant serializable

**Snapshot isolation không đồng nghĩa serializable isolation cho mọi bất biến liên documents.** Một ví dụ thường gọi là **write skew**:

~~~text
Hai bác sĩ A/B trực:
  doctors.A.onCall = true
  doctors.B.onCall = true

Quy tắc: ít nhất một bác sĩ luôn trực.

Transaction T1 đọc snapshot: A=true, B=true
Transaction T2 đọc snapshot: A=true, B=true

T1 sửa riêng A.onCall = false
T2 sửa riêng B.onCall = false

Hai transactions ghi hai documents KHÁC nhau.
Sau khi cùng commit, có nguy cơ A=false, B=false.
~~~

Do hai transactions cập nhật **những documents khác nhau**, một số cơ chế write conflict phát sinh khi cùng sửa một document không nhất thiết bảo vệ invariant “ít nhất một bác sĩ trực”. Đây là lớp lỗi cần nghĩ đến ngay cả khi dùng transaction.

**Cách thiết kế:** đặt invariant vào **một shared guard document** (ví dụ `onCallCount` và mỗi transaction thực hiện một conditional decrement khi count vẫn đủ), hoặc lưu trạng thái chung trong một aggregate nhỏ có thể cập nhật nguyên tử. Khi hai transactions cùng phải ghi **guard document**, write conflict/CAS giúp tuần tự hóa cạnh tranh trên điều kiện chung. Không chỉ “đọc cả hai rồi sửa document của mình”.

### 9.4. Vấn đề stale reads trong transaction

Một transaction có read snapshot có thể đọc trạng thái đã cũ so với writers bên ngoài. Nếu thao tác phải bảo đảm document không đổi giữa lúc bắt đầu và lúc cập nhật, **thực hiện conditional write/`findOneAndUpdate`** với filter bảo vệ trạng thái, hoặc thay đổi cấu trúc invariant. Một read concern mạnh không tự thay thế filter/version trên các biến nghiệp vụ đang cạnh tranh.

## 10. Concurrency và write conflicts trong transaction

MongoDB cho phép nhiều operations chạy đồng thời, nhưng khi transaction sửa một document mà writer khác cũng thay đổi document đó, transaction có thể **bị abort với write conflict**.

### 10.1. Một sơ đồ write conflict

~~~text
Transaction T1 bắt đầu:
  read stock SKU-RED
        |
        +----------- Writer T2 update SKU-RED, commit
        |
  T1 cố update SKU-RED dựa trên snapshot cũ
        |
        v
  Có thể bị write conflict / transaction abort
        |
        v
  Application retry toàn transaction khi phù hợp
~~~

Đây là một trong những lý do cần dùng **convenient transaction APIs** của driver và xử lý nhãn lỗi phù hợp. Tuy nhiên, retry toàn transaction không có nghĩa được bỏ qua điều kiện stock/amount; điều kiện phải được kiểm tra lại trong lần thực thi mới.

### 10.2. Retry phải phân loại lỗi

| Tình huống | Hướng xử lý |
|---|---|
| `TransientTransactionError` | Driver thường có thể retry **toàn transaction** (với giới hạn/hướng dẫn driver). |
| `UnknownTransactionCommitResult` | **Retry commit**/đối soát outcome; không mặc nhiên chạy lại nghiệp vụ với ID mới. |
| Insufficient stock/funds (`matchedCount:0`) | Đây là **business rejection**; không retry vô hạn nếu số lượng không đủ. |
| `E11000 DuplicateKey` | Kiểm tra unique key gây trùng và idempotency; không coi mọi duplicate là thành công. |
| Transaction quá lớn/timeout | Cần giảm scope, workload, thời gian; retry cùng transaction khổng lồ chưa chắc giải quyết. |
| Network/server unavailable | Phân loại khả năng commit đã xảy ra, dùng session API và operation ID để reconcile. |

Một ứng dụng gọi lại **một HTTP request mới** vẫn có thể tạo transaction mới. Dù driver có retry technical writes, đó **không bảo vệ exactly-once của business request** nếu requestId mới mỗi lần.

### 10.3. Dùng cùng session, tránh operations song song

Khi transaction đang chạy, mọi MongoDB write/read thuộc transaction phải dùng **cùng session**. Đặc biệt với Java/Node drivers, không mặc định được phép chạy nhiều operations **song song** trong một transaction với cùng session. Thực hiện operations theo trình tự API hỗ trợ; không dùng thread pool hoặc `Promise.all` trên cùng session như một cách “tăng tốc transaction” nếu driver cảnh báo không hỗ trợ.

### 10.4. Phân biệt lỗi write conflict và lost update

- **Lost update** có thể xảy ra với hai `$set` đơn lẻ trên cùng document khi ứng dụng tính trạng thái từ snapshot cũ nhưng filter chỉ theo `_id`. Mỗi update là atomic, nhưng không phát hiện ghi đè.
- **Write conflict trong transaction** khiến một transaction có thể bị abort/retry, bảo vệ storage-level consistency trên những document có cạnh tranh.
- **Business invariant** vẫn cần `$inc`, CAS/version, unique key hoặc shared guard tùy yêu cầu; transaction không tự biết cập nhật nào hợp lệ.

## 11. Read concern và write concern không phải giao dịch

Một câu hỏi thường gặp: “Nếu đã dùng `writeConcern:{w:'majority'}`, tôi có cần transaction không?” Câu trả lời: **đây là hai vấn đề khác nhau**.

### 11.1. Write concern

Write concern quy định mức xác nhận ghi. Ví dụ:

~~~javascript
lab.accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: NumberLong(-10) } },
  { writeConcern: { w: "majority" } }
)
~~~

`w:"majority"` yêu cầu mức xác nhận theo majority voting data-bearing members phù hợp của replica set. Nó **không biến** update A và update B độc lập thành cùng một transaction.

### 11.2. Read concern

Read concern điều khiển consistency/recency guarantees của reads; các mức như `local`, `majority`, `snapshot` có semantics khác nhau. **`snapshot`** trong transaction giúp các reads trong transaction nhìn một snapshot theo quy tắc server, với các điều kiện của deployment/commit.

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})
~~~

Đây là transaction options, không phải “mặc định mọi find trên toàn cluster giờ đọc cùng snapshot”.

### 11.3. Transaction và độ bền ghi

Transaction đảm bảo atomic commit/abort trong ranh giới MongoDB của nó, nhưng mức bảo đảm durability khi failover phụ thuộc write concern/commit conditions. Một transaction commit với `w:1` có thể có đặc điểm độ bền khác với commit `w:"majority"`. Chọn concerns theo dữ liệu quan trọng và SLO, không ngầm coi mọi commit message là mức durability cao nhất.

### 11.4. Kết quả commit không rõ

Trong một mạng không hoàn hảo:

~~~text
Client -> commitTransaction
MongoDB -> commit thành công
Mạng đứt trước khi response tới client
Client -> không biết commit đã xong chưa
~~~

**Không** coi mọi lỗi từ commit là bằng chứng transaction đã abort. Với `UnknownTransactionCommitResult`, theo hướng dẫn driver, cần tiếp tục xác định/retry **commit** hoặc reconcile theo stable requestId. Đưa một business request vào transaction không giải quyết được bài toán **khách hàng gửi lại HTTP request sau timeout**.

## 12. Idempotency: transaction không tự chống request nghiệp vụ bị gửi lại

Giả sử transaction chuyển 150 từ A sang B đã commit, nhưng HTTP client timeout và gửi lại cùng request. Nếu backend tạo **transferId mới** rồi chạy thêm một transaction, database có thể commit **một lần chuyển tiền thứ hai** rất đúng về atomicity, nhưng sai về nghiệp vụ.

### 12.1. Một operation ID ổn định

Client cung cấp (hoặc backend cấp từ một yêu cầu đã lưu) `requestId = "TX-1001"`, gắn với nội dung:

~~~javascript
{
  requestId: "TX-1001",
  from: "A",
  to: "B",
  amount: 150,
  currency: "VND"
}
~~~

Một record trong `transfers` có unique index `{requestId:1}`. Khi transaction chuyển tiền được commit, record này commit cùng debit/credit.

Nếu request lặp:

1. Tìm transfer theo `requestId`.
2. So sánh **payload đã lưu** với request mới.
3. Nếu cùng request và đã POSTED, trả kết quả idempotent.
4. Nếu cùng ID nhưng payload khác, trả **conflict**; không tự sửa record để hợp request mới.
5. Nếu record chưa có hoặc outcome không rõ, áp dụng transaction/đối soát và retry phù hợp.

**Đừng chỉ dựa trên số dư** để nhận diện request đã chạy: nhiều giao dịch hợp lệ khác có thể làm số dư giống một trạng thái dự đoán.

### 12.2. Unique key và transaction phải phục vụ cùng ranh giới

~~~javascript
// Trong cùng transaction:
txdb.transfers.insertOne({
  _id: "TX-1001",
  requestId: "TX-1001",
  amount: NumberLong(150),
  state: "POSTED"
})

txdb.accounts.updateOne(
  { _id: "A", balance: { $gte: NumberLong(150) } },
  { $inc: { balance: NumberLong(-150) } }
)

txdb.accounts.updateOne(
  { _id: "B" },
  { $inc: { balance: NumberLong(150) } }
)
~~~

Đây chỉ là **đoạn minh họa vị trí của các writes trong callback**, không phải một transaction hoàn chỉnh: khi triển khai phải kiểm tra `matchedCount`, scope/currency, sử dụng session, và abort nếu điều kiện không thỏa. Unique transferId có ý nghĩa khi nó được ghi **trong cùng transaction** với những tác động cần dedupe.

### 12.3. Retryable writes khác business idempotency

Một số write operations được MongoDB driver tự retry khi có lỗi kỹ thuật qua **retryable writes** với session/statement tracking. Nhưng điều đó không đảm bảo toàn bộ **HTTP request** chỉ được thực hiện một lần nếu phía caller gửi **request mới**. Một `$inc` được thực thi hai lần trong hai business requests khác nhau vẫn thay đổi số dư hai lần.

Tương tự, `withTransaction()` giúp retry **một invocation** theo các error labels; không tự nhớ idempotency cho **một invocation khác** sau client timeout.

### 12.4. Dedupe cần có hạn mức lưu trữ hợp lý

Một service có thể lưu idempotency record trong một khoảng thời gian phù hợp. Nhưng xóa record quá sớm hoặc thay requestId sau retry khiến dedupe mất tác dụng. Hãy xác định retention, key scope (toàn hệ thống hay theo tenant/account), uniqueness, và xử lý trường hợp **requestId trùng nhưng payload khác**.

## 13. Transaction không bao trùm dịch vụ bên ngoài MongoDB

Một đơn hàng vừa được đặt có thể cần:

~~~text
1. Giữ inventory trong MongoDB
2. Đổi trạng thái order sang CONFIRMED
3. Gọi payment gateway
4. Gửi email
5. Publish message sang vận chuyển
~~~

MongoDB transaction chỉ quản lý những thay đổi **thuộc MongoDB transaction/session**, không tự commit/abort lời gọi payment provider, SMTP hoặc message broker.

### 13.1. Sai: charge payment bên trong transaction callback

~~~text
START TRANSACTION
  Update order
  Call payment gateway -> CHARGE SUCCESS
  Insert reservation -> FAIL
ABORT TRANSACTION

MongoDB order/reservation rollback
Payment gateway vẫn đã CHARGE!
~~~

Nếu driver tự retry transaction callback, lời gọi gateway có thể **bị thực hiện thêm lần nữa**. Không đặt external side effect không idempotent trong transaction callback.

### 13.2. Transactional outbox khi cần đồng bộ MongoDB state với ý định phát event

Một lựa chọn:

~~~text
MongoDB transaction:
  Update order -> CONFIRMED
  Insert reservation records
  Insert outbox event:
      {eventId:"EV-ORDER-100",type:"ORDER_CONFIRMED",orderId:"O-100"}
COMMIT
       |
       v
Outbox dispatcher đọc các events chưa phát
       |
       +--> Publish message / gửi email
       |
       +--> Đánh dấu trạng thái phát hoặc ghi checkpoint
~~~

Order/reservations/outbox có thể commit cùng nhau. Nhưng dispatcher có thể publish thành công rồi chết **trước khi đánh dấu dispatched**, nên khi restart có thể publish lần nữa. Do đó **outbox thường có tính at-least-once delivery**, cần **consumer idempotent theo eventId**.

### 13.3. Saga/compensation cho nhiều hệ thống

Nếu mỗi bước do một service riêng quản lý:

~~~text
Reserve inventory
       |
       v
Charge payment
       |
       v
Book shipment

If payment fails -> Release inventory
If shipment fails -> Refund or compensate according to policy
~~~

Đây là **saga**: các bước không cùng một transaction atomic, mà mỗi bước có trạng thái bền vững, **compensating action**, retry/idempotency và đối soát. Compensation **không phải rollback vật lý tức thời**; nó cũng có thể thất bại, nên cần trạng thái PENDING/COMPENSATING/FAILED và cảnh báo vận hành.

### 13.4. Chọn transaction ở đâu trong saga?

Ngay cả khi workflow tổng thể dùng saga, **mỗi service** có thể dùng **một transaction nhỏ** cho state và outbox của chính nó. Ví dụ service Inventory cập nhật stock và reservation trong một transaction, rồi ghi outbox để báo bước tiếp theo. Không cần một transaction MongoDB mở xuyên cả quá trình chờ payment gateway, vì gateway không tham gia commit protocol đó.

## 14. Cách chọn mô hình dữ liệu trước khi thêm transaction

Multi-document transaction rất hữu ích, nhưng MongoDB ưu tiên **thiết kế document để những dữ liệu thường phải đổi cùng nhau có thể nằm trong một aggregate hợp lý**. Transaction không nên thay thế quyết định mô hình dữ liệu.

### 14.1. Khi embedding hợp lý

Ví dụ các trường cùng order:

~~~javascript
{
  _id: "O-200",
  status: "DRAFT",
  shippingAddressSnapshot: {
    city: "Hà Nội",
    postalCode: "100000"
  },
  totals: {
    subtotal: 300,
    fee: 15,
    grandTotal: 315
  },
  lines: [
    { lineId: "L1", sku: "SKU-RED", qty: 2 },
    { lineId: "L2", sku: "SKU-BLUE", qty: 1 }
  ]
}
~~~

Nếu cần chuyển status và ghi `confirmedAt`, tất cả ở một order document. Nếu cần đồng thời thay số lượng trong **inventory collection**, đó lại là nhiều documents và phải xét invariant. Không nên khẳng định “đã nhúng lines vào order là mọi thứ trong checkout đều atomic”, vì inventory và payment records vẫn tách biệt.

### 14.2. Khi reference tốt hơn

Reference phù hợp khi:

- Quan hệ **one-to-many không giới hạn**: audit logs, comments, ledger entries.
- Documents có **vòng đời độc lập**, quyền truy cập/retention khác nhau.
- Cần index/pagination riêng trên child records.
- Nhiều writers độc lập, nhúng vào một document sẽ gây **hot document**.
- Dữ liệu riêng lẻ có thể đạt tới giới hạn **16 MiB** nếu nhúng tất cả.

Khi tách dữ liệu, đừng mặc định phải thêm transaction cho mọi write. Hãy phân loại mỗi bất biến: **đòi nhất quán tức thì** hay chấp nhận **eventual consistency**.

### 14.3. Materialized summary có thể eventual

Ví dụ `orders` là nguồn sự thật, còn `dailyRevenue` là một bảng đọc được tổng hợp định kỳ. Nếu report chấp nhận độ trễ 5 giây và không dùng để trừ tiền, không cần mỗi order insert cập nhật `dailyRevenue` trong một transaction. Một change stream/outbox/job tổng hợp có thể cập nhật summary theo checkpoint.

Nếu summary được dùng làm **quyết định giới hạn tín dụng** hoặc chốt sổ tức thì, phải đưa ra thiết kế nhất quán thích hợp (transaction, shared counter, ledger, versioned snapshot) thay vì giả định eventual summary luôn đúng trong mọi thời điểm.

### 14.4. Không nhúng một ledger vô hạn chỉ để tránh transaction

~~~javascript
{
  _id: "ACC-A",
  balance: 1000,
  ledgerEntries: [
    // Hàng triệu bản ghi trong nhiều năm.
  ]
}
~~~

Đây là một design có rủi ro kích thước, hiệu năng và contention. Nếu ledger entries cần lưu lâu dài, mô hình **mỗi entry là một document** thường phù hợp hơn. Khi cần balance và ledger entry cùng commit, **transaction ngắn** là một giải pháp; nếu ledger là source of truth, balance có thể là projection dẫn xuất theo version với reconciliation theo chính sách hệ thống.

### 14.5. Dữ liệu có chung vòng đời không đồng nghĩa dữ liệu phải đồng cập nhật

Một customer profile và nhiều orders thường được hiển thị cùng trang, nhưng không có nghĩa chúng phải cùng transaction khi user đổi tên. Orders có thể chứa **snapshot lịch sử tên/địa chỉ tại thời điểm đặt hàng**. Giữ snapshot có thể đúng nghiệp vụ hơn việc cố sửa mọi order trong một transaction chỉ để đồng bộ tên mới.

## 15. Giới hạn và chi phí của multi-document transactions

Một transaction giúp đơn giản hóa lý luận all-or-nothing nhưng không miễn phí. MongoDB phải quản lý session, snapshot, transaction state, writes chưa commit, concurrency conflicts, commit protocol và các giới hạn tài nguyên liên quan.

### 15.1. Transaction nên ngắn và có scope rõ

Một transaction hợp lý:

~~~text
Start transaction
  Insert transferId
  Conditional debit
  Conditional credit
Commit
~~~

Một transaction dễ rủi ro:

~~~text
Start transaction
  Scan 10 million documents
  Call remote payment gateway
  Wait for user confirmation
  Update thousands of documents
  Sleep for a long retry delay
Commit
~~~

Không giữ transaction chờ người dùng, network call bên ngoài hoặc batch migration kéo dài. Chia công việc thành **đơn vị nghiệp vụ nhỏ** với idempotency/checkpoints nếu toàn bộ job không có invariant all-or-nothing.

### 15.2. Các giới hạn cần kiểm tra ở production

| Chủ đề | Lưu ý |
|---|---|
| **Transaction lifetime** | MongoDB có tham số `transactionLifetimeLimitSeconds`, mặc định thường **60 giây**; có thể cấu hình khác. Transaction quá lâu có thể bị abort. |
| **WiredTiger cache** | Snapshot/history và writes của transaction có thể tạo memory pressure; transaction quá lớn có thể gặp `TransactionTooLargeForCache`. |
| **Write conflicts** | Transaction có thể bị abort khi cạnh tranh cập nhật, cần bounded retry. |
| **Lock acquisition** | Transaction có thể gặp lock timeout nếu không lấy lock kịp, tùy cấu hình/server. |
| **Sharded transactions** | Có chi phí điều phối nhiều shards, commit và constraints riêng. |
| **DDL/metadata** | Tạo collection/index, rename/drop và DDL đồng thời có giới hạn phụ thuộc version/topology. |
| **Read/write concern** | Thiết lập tại transaction level theo API; không thay bằng tùy chọn per-write tùy tiện. |
| **Parallel session use** | Không chạy các thao tác song song trên cùng session nếu driver không hỗ trợ. |
| **External services** | SMTP, payment, message broker không thuộc MongoDB transaction. |
| **Large number of writes** | Không coi transaction là một cơ chế commit cho mọi record trong một job không giới hạn. |

Các giới hạn cụ thể có thể đổi giữa các dòng MongoDB. Nên kiểm tra **MongoDB Database Manual đúng server version** và workload đại diện thay vì dùng một con số cố định làm bảo đảm cho mọi deployment.

### 15.3. Chia transaction theo ranh giới nghiệp vụ

Giả sử một job cần tạo 20.000 invoices. Nếu mỗi invoice độc lập và invoice + invoiceLines của nó phải cùng commit, thiết kế **một transaction cho từng invoice** hoặc từng nhóm nghiệp vụ nhỏ có kiểm soát; không nên tự chọn một transaction duy nhất cho 20.000 invoices. Điều này giúp lỗi ở invoice 500 không bắt buộc rollback 499 invoices đã hoàn tất nếu domain cho phép tiến từng phần.

### 15.4. Index trước khi thêm transaction

Một transfer cần tìm account theo `_id`, reservations theo `(orderId,sku)`. Tạo indexes phù hợp giúp:

- Giảm thời gian read/update và thời gian transaction giữ tài nguyên.
- Giảm số records phải kiểm tra và contention không cần thiết.
- Bảo vệ uniqueness của request/line records.

Transaction không biến query filter kém hoặc thiếu index thành nhanh. Đừng thêm transactions quanh một `updateMany` quét cả collection mà chưa hiểu execution plan và số documents.

### 15.5. Monitor các chỉ số

| Chỉ số | Dấu hiệu cần điều tra |
|---|---|
| P95/P99 transaction duration | Có transaction giữ snapshot lâu, làm chậm commit? |
| Abort/write conflict rate | Hot documents/transaction scope quá rộng hoặc contention cao. |
| Transaction retries | Retry tăng nhanh, dễ tạo retry storm. |
| WiredTiger cache usage/history pressure | Nhiều long-running snapshots, cache thiếu chỗ. |
| Lock waits/timeouts | DDL, metadata, documents cạnh tranh. |
| Replication lag/majority commit latency | Mức xác nhận ghi/cluster health ảnh hưởng latency. |
| Number of participating shards | Có scatter-gather/cross-shard transaction không cần thiết? |
| Idempotency conflicts | Nhiều request lặp, dữ liệu key không ổn định hoặc payload mismatch. |
| Outbox lag | External workflow bị trễ dù transaction local commit tốt. |

### 15.6. Transaction trong sharded cluster

MongoDB hỗ trợ distributed transactions trên sharded clusters ở các phiên bản thích hợp. Nhưng nhiều-shard transaction có thêm chi phí coordination/commit và failure modes; đôi khi một **data model giúp các records liên quan nằm trong một shard** có thể giảm chi phí. Tuy vậy, placement không biến hai documents thành **một**: nếu phải all-or-nothing giữa hai documents cùng shard thì vẫn cần transaction trừ khi đã đổi ranh giới aggregate.

**Không nhầm "cùng shard" với "cùng document".**

### 15.7. Khi một transaction không đủ vì bất biến trải qua nhiều independent systems

MongoDB transaction chỉ quản lý dữ liệu nó điều phối trong cluster hỗ trợ. Nếu business invariant trải qua một **external SQL database**, payment gateway hay Kafka, sẽ cần kiến trúc **distributed workflow**/outbox/saga/2PC chuyên biệt khi thực sự phù hợp — không thể mặc định gói tất cả vào MongoDB transaction.

## 16. Java Sync Driver: transaction an toàn theo một business unit

Java Sync Driver hỗ trợ multi-document transactions qua `ClientSession`. Với API tiện lợi `withTransaction()`, driver giúp xử lý nhiều trường hợp retry/commit theo error labels. Đoạn dưới là ví dụ **transfer** độc lập; giả định collections và unique indexes ở mục 3 đã tồn tại và MongoClient kết nối tới replica set/sharded cluster hỗ trợ.

### 16.1. One-document conditional update bằng Java (đối chứng)

Trước khi mở transaction, hãy kiểm tra xem một update có đủ không:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;

// database là MongoDatabase của "txn_need_lab".
MongoCollection<Document> inventory = database.getCollection("inventory");
int quantity = 2;

UpdateResult result = inventory.updateOne(
    and(
        eq("_id", "SKU-RED"),
        gte("available", quantity)
    ),
    combine(
        inc("available", -quantity),
        inc("reserved", quantity)
    )
);

if (result.getMatchedCount() == 1) {
    System.out.println("Reserved");
} else {
    System.out.println("Stock insufficient or SKU missing");
}
~~~

Một SKU trong một document và không có yêu cầu ghi reservation document cùng lúc ⇒ **không cần transaction nhiều document**. Nhưng nếu request bị replay ở cấp API, `$inc` có thể chạy lần nữa; cần stable request ID/ledger hoặc conditional business transition phù hợp.

### 16.2. Transaction dùng `ClientSession.withTransaction()`

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.inc;

// client: MongoClient đã kết nối đến deployment hỗ trợ transactions.
MongoDatabase database = client.getDatabase("txn_need_lab");
MongoCollection<Document> accounts = database.getCollection("accounts");
MongoCollection<Document> transfers = database.getCollection("transfers");

TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();

String requestId = "TX-JAVA-2001";
long amount = 150L;

try (ClientSession session = client.startSession()) {
    String committedId = session.withTransaction(() -> {
        transfers.insertOne(
            session,
            new Document("_id", requestId)
                .append("requestId", requestId)
                .append("fromAccountId", "A")
                .append("toAccountId", "B")
                .append("amount", amount)
                .append("currency", "VND")
                .append("state", "POSTED")
        );

        UpdateResult debit = accounts.updateOne(
            session,
            and(
                eq("_id", "A"),
                eq("currency", "VND"),
                gte("balance", amount)
            ),
            inc("balance", -amount)
        );
        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Source account missing or insufficient funds"
            );
        }

        UpdateResult credit = accounts.updateOne(
            session,
            and(eq("_id", "B"), eq("currency", "VND")),
            inc("balance", amount)
        );
        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Destination account missing"
            );
        }

        return requestId;
    }, options);

    System.out.println("Transfer committed: " + committedId);
}
~~~

Trong mẫu:

- **Mọi write** có tham số `session`. Quên session ở một call sẽ khiến write đó chạy ngoài transaction.
- Ghi requestId cùng debit/credit cho phép những thay đổi **cùng commit hoặc abort**.
- Filter `balance >= amount` vẫn kiểm tra business condition tại update; transaction không tự kiểm tra số dư không âm.
- Callback có thể được gọi lại theo driver retry semantics. Nó không chứa email/gateway/side effect ngoài MongoDB.
- Unique index trên `requestId` cần được tạo trước. Khi duplicate request, dịch vụ phải đối soát record cũ và payload, không retry như transient error vô hạn.
- Nếu nguồn/đích đã được sử dụng bởi transaction khác, có thể gặp write conflict; driver retry theo điều kiện được hỗ trợ.

**Không chạy ví dụ Java này ngay sau ví dụ TX-1001 mà vẫn kỳ vọng số dư ban đầu 1000/200.** Fixture có thể đã đổi. Ví dụ chỉ mô tả cấu trúc; chạy độc lập trên collection lab đã reset phù hợp.

### 16.3. Transaction cần trả gì cho API?

Một API không nên chỉ trả “success/fail” không phân loại. Các trường hợp:

| Kết quả | API xử lý gợi ý |
|---|---|
| Commit thành công, requestId mới | Thành công và trả transfer ID. |
| requestId đã có với payload **giống** và state POSTED | Trả thành công idempotent, không debit lần nữa. |
| requestId đã có nhưng payload khác | Báo conflict; có thể là lỗi client hoặc reuse ID. |
| Insufficient funds | Trả từ chối nghiệp vụ, không retry mù. |
| Transient database error | Retry có giới hạn theo API/driver. |
| Commit result unknown | Xử lý đúng transaction API và reconcile trước khi tạo business operation mới. |
| Validation/authorization error | Không thực thi transfer; ghi log/response theo chính sách. |

### 16.4. Vì sao callback không nên chứa hoạt động ngoài MongoDB?

~~~java
session.withTransaction(() -> {
    // BAD IDEA:
    // paymentGateway.charge(...); // Có thể thực thi lại khi retry callback.
    ...
}, options);
~~~

Không gửi email, charge card hoặc publish event không idempotent trực tiếp trong callback. Thay bằng **outbox record trong MongoDB transaction**, rồi dispatcher xử lý sau khi commit. Nếu phải gọi gateway trong workflow, dùng idempotency key của gateway và orchestration/saga có trạng thái rõ.

### 16.5. Java Driver và transaction retries

API helper của driver xử lý một số retry cases, nhưng **business logic vẫn phải bounded và deterministic**. Ngoài ra, một số errors (validation, duplicate key, transaction quá lớn) không phải lỗi tạm thời. Nếu ứng dụng tự bao thêm vòng retry ở ngoài helper, cần tránh retry storm, double side effect, và đặc biệt không tự đổi requestId giữa các lần thử của cùng nghiệp vụ.

## 17. Spring Data MongoDB: khi nào dùng `@Transactional`?

Với ứng dụng Spring Data MongoDB, một transaction manager thích hợp có thể quản lý MongoDB transaction và propagation theo cấu hình. Ví dụ:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {

    private final AccountRepository accounts;
    private final TransferRepository transfers;

    public TransferService(
        AccountRepository accounts,
        TransferRepository transfers
    ) {
        this.accounts = accounts;
        this.transfers = transfers;
    }

    @Transactional
    public void transfer(String requestId, String fromId,
                         String toId, long amount) {
        // Minh họa ranh giới dịch vụ; các repository methods
        // phải dùng MongoDB session/transaction đúng cấu hình.
        // Thực tế cần atomic conditional debit, credit,
        // unique requestId, check modified counts và error handling.
        transfers.record(requestId, fromId, toId, amount);
        accounts.debitIfEnough(fromId, amount);
        accounts.credit(toId, amount);
    }
}
~~~

Đây là **pseudocode tầng service**, không phải code compile-ready vì các repository methods `record`/`debitIfEnough`/`credit` chỉ là API giả định. Nó diễn đạt transaction boundary; khi triển khai, phải:

- Cấu hình **MongoTransactionManager** và transaction support phù hợp với MongoDB deployment.
- Đảm bảo các repository/database calls tham gia **cùng session**.
- Kiểm tra debit/credit success; một method update không match **không tự ném exception** nếu code không kiểm tra.
- Hiểu **Spring AOP proxy/self-invocation**: một lời gọi trực tiếp từ method cùng class có thể không đi qua interceptor transaction.
- Hiểu rollback semantics theo loại exception. Không giả định mọi checked exception đều rollback nếu không cấu hình.
- Không coi annotation là cơ chế chống idempotency/retry.

Nếu dịch vụ chỉ cập nhật một embedded order document, dùng `@Transactional` bao một update đơn lẻ có thể thêm complexity không cần thiết. Chọn transaction theo invariant, không theo thói quen annotation cho mọi service method.

## 18. Bảng quyết định: khi nào cần, khi nào không?

Thay vì dùng một quy tắc “cứ nhiều document thì cần transaction”, hãy xét đồng thời **tính tức thì**, **khả năng commit một phần**, **số hệ thống liên quan** và **mô hình dữ liệu**.

| Tình huống | Có nhiều documents cần thay đổi? | Chấp nhận partial state? | Lựa chọn thường phù hợp |
|---|---|---|---|
| Giảm tồn kho và tăng reserved **trong cùng SKU document** | Không | Không cần partial giữa hai field | **Một conditional `updateOne`** với `$inc`. |
| Đổi status và timestamp trong một order | Không | Không | **Một atomic update** với filter status/version. |
| Sửa địa chỉ embedded trong user profile | Không | Không | **Một update**; không cần transaction nhiều docs. |
| Chuyển tiền giữa account A và B | Có | **Không** | **Multi-document transaction** + stable transfer ID. |
| Chuyển tiền đồng thời ghi transfer/ledger record | Có | **Không** | Transaction trên balances và ledger/transfer records. |
| Giữ hai SKU, order chỉ hợp lệ nếu đủ cả hai ngay lập tức | Có | **Không** | Transaction ngắn, conditional updates từng SKU. |
| Giữ SKU từng bước, cho phép PENDING và release khi thất bại | Có | **Có**, trong một workflow có kiểm soát | **Reservation saga/compensation**, idempotency. |
| Tạo user và wallet: không thể có ACTIVE user không có wallet | Có | Không nếu ACTIVE tức thì | Transaction hoặc **PENDING lifecycle** nếu domain cho phép. |
| Import hàng chục nghìn independent products | Có | Có | `insertMany`/`bulkWrite` theo batches, checkpoint. |
| Nâng schemaVersion của nhiều documents | Có | Thường có | Migration idempotent; không cần transaction khổng lồ. |
| Mỗi order ghi một analytics event không critical | Có | Có | Eventual consistency/outbox tùy mức đảm bảo. |
| Order PAID và gửi email | MongoDB + hệ thống ngoài | MongoDB không thể commit email cùng lúc | Transaction local + **outbox**; consumer idempotent. |
| Đổi account profile và mọi order snapshot lịch sử | Có | Có thể không nên đổi order cũ | Thiết kế **snapshot semantics**, không giao dịch hàng loạt. |
| Dashboard đọc số liệu đa collection nhưng chấp nhận trễ | Có nhiều documents đọc | Có | Aggregation/read model eventual, không nhất thiết snapshot transaction. |
| Báo cáo chốt kỳ cần snapshot nhiều documents tại cùng thời điểm | Đọc nhiều documents | **Không chấp nhận read skew** | Snapshot read semantics/transaction hoặc snapshot versioned. |
| Enforce username duy nhất | Hai inserts có thể cạnh tranh | Không có duplicate | **Unique index**, không cần transaction chỉ để chống trùng. |
| Đếm audit events theo ngày | Có | Có | Asynchronous materialization/aggregation. |
| Bảo vệ invariant “ít nhất một bác sĩ trực” qua hai documents | Có | Không | **Shared guard/CAS** hoặc mô hình một doc; transaction chỉ đọc snapshot chưa đủ. |

### 18.1. Cây quyết định rút gọn

~~~text
1. Bất biến nào cần bảo vệ?
  |
  +-- Chỉ nằm trong một document?
  |      |
  |      +-- Có -> Conditional update + CAS/version/unique constraint.
  |
  +-- Trải nhiều documents?
         |
         +-- Nghiệp vụ chấp nhận partial progress hay PENDING state?
         |      |
         |      +-- Có -> Saga/outbox/batches/reconciliation.
         |
         +-- Không thể chấp nhận partial commit?
                |
                +-- Tất cả writes thuộc MongoDB deployment hỗ trợ?
                |      |
                |      +-- Có -> Multi-document transaction ngắn,
                |                 check predicates và idempotency.
                |
                +-- Có external systems?
                       |
                       +-- MongoDB transaction không bao trùm chúng.
                           Thiết kế outbox/saga/compensation.
~~~

### 18.2. Bốn câu hỏi phải trả lời trước khi bật transaction

1. **Nếu dừng tiến trình sau bước ghi thứ nhất, dữ liệu có thể được sửa sau theo một workflow hợp lệ không?** Nếu có, eventual consistency có thể đủ.
2. **Nếu clients đồng thời, bất biến nào có thể bị vi phạm dù mỗi update atomic?** Đây là nơi cần CAS/unique/transaction/shared guard.
3. **Một request bị gửi lại có cần chạy lại không?** Thiết kế idempotency ID và đối soát.
4. **Có yếu tố nằm ngoài MongoDB không?** Nếu có, transaction MongoDB không giải quyết toàn bộ bài toán.

## 19. Những cạm bẫy thường gặp khi quyết định sử dụng transaction

| Nhầm lẫn | Giải thích đúng |
|---|---|
| “MongoDB không có ACID transactions.” | Có multi-document transactions trên deployment được hỗ trợ. |
| “Có transaction thì mọi thao tác đều nên đưa vào.” | Transaction cần **scope nhỏ theo invariant**, tránh giữ tài nguyên lâu. |
| “Mỗi updateOne atomic nên hai updateOne cũng atomic chung.” | Hai updates độc lập có thể thành công một phần. |
| “`bulkWrite({ordered:true})` tương đương transaction.” | Ordered điều khiển thứ tự/dừng; không rollback các operations đã chạy. |
| “`updateMany` nguyên tử trên mọi documents.” | Mỗi document được cập nhật nguyên tử riêng; operation không all-or-nothing. |
| “Muốn đảm bảo email unique thì phải mở transaction find+insert.” | Unique index chống race trực tiếp; find trước không đủ. |
| “Nhúng mọi documents vào một document là cách tốt nhất.” | Dễ chạm 16 MiB, hot document, các entities có vòng đời khác nhau. |
| “Mọi quan hệ reference đều cần transaction.” | Chỉ khi có một invariant đòi **cùng commit**; nhiều relations cho phép eventual. |
| “Giao dịch nhiều docs giải quyết được mọi lost update.” | Vẫn cần CAS/`$inc`/write conditions và xử lý write conflict. |
| “Snapshot transaction tự đảm bảo serializable cho mọi invariant.” | Snapshot isolation có thể có **write skew** với documents ghi khác nhau. |
| “`writeConcern:majority` làm hai lệnh độc lập cùng commit.” | Write concern chỉ điều khiển acknowledgment/durability. |
| “Commit timeout nghĩa là transaction đã abort.” | Outcome có thể không rõ; xử lý `UnknownTransactionCommitResult`. |
| “Driver retry transaction thì không cần idempotency.” | Một **HTTP/business request mới** vẫn có thể chạy lại. |
| “`$inc` được retry an toàn trong mọi trường hợp.” | Technical retryable writes khác replay nghiệp vụ; `$inc` không idempotent nếu thực thi hai lần. |
| “Có unique transferId thì chắc chắn mọi duplicate request là success.” | Cần kiểm tra record cũ có **payload giống** và trạng thái đúng. |
| “Ngoài transaction có một MongoDB write cũng sẽ bị rollback.” | Chỉ writes gắn đúng session/transaction được bao trùm. |
| “Mở transaction quanh external payment gateway giúp rollback charge.” | MongoDB không kiểm soát gateway; cần saga/compensation/idempotency. |
| “Outbox bảo đảm message được gửi exactly once.” | Thường **at-least-once**, consumer phải dedupe. |
| “Transaction dài vẫn okay vì default lifetime không giới hạn.” | Có lifetime limit/cache/lock constraints; kiểm tra server config. |
| “Transaction trên cùng shard không cần nữa.” | Hai documents vẫn là hai atomic boundaries nếu không có transaction. |
| “Nếu có nhiều transactions, không cần transaction trên read path.” | Nhiều reads độc lập có thể thấy những thời điểm khác nhau. |
| “Nếu callback transaction trả exception thì chắc chắn mọi exception đều retry được.” | Business errors và resource errors phải được phân loại, không retry mù. |
| “Chỉ cần gọi `@Transactional` là mọi MongoDB repository cùng session.” | Phải cấu hình transaction manager/proxy và session đúng; self-invocation có thể bypass. |

### 19.1. Những dấu hiệu cho thấy transaction đang bị lạm dụng

- Một transaction chạy vài phút để migrate hàng trăm nghìn documents độc lập.
- Trong transaction có HTTP call, chờ người dùng hoặc sleep/backoff.
- Không có business invariant được mô tả rõ, chỉ vì “muốn mọi lệnh được gói lại”.
- Mỗi API đọc/ghi **một document** cũng mở multi-document transaction không cần thiết.
- Application dựa vào transaction để sửa lỗi data model như nhúng audit events không giới hạn.
- Không có stable business request ID cho flows có `$inc` hoặc external charges.
- Không đo abort/retry/cache overhead khi rollout.

### 19.2. Những dấu hiệu cho thấy đang thiếu transaction hoặc thiếu ranh giới nhất quán

- Debit A đã thành công nhưng credit B đôi khi thất bại và không có reconciliation.
- Order đã CONFIRMED nhưng không có reservation record, dù domain khẳng định điều đó không bao giờ được phép.
- Hai SKU cùng phải giữ nhưng code chỉ gọi hai updateOne rồi trả success nếu lệnh cuối thành công.
- User đã ACTIVE nhưng wallet bắt buộc chưa được tạo; không có PENDING state hoặc repair worker.
- Ledger record ghi trước balance update và có thể tồn tại một mình khi error.
- Một service cố bảo vệ cross-document invariant bằng find+write mà không có shared guard/transaction.

### 19.3. Khi giao dịch không cần nhưng vẫn muốn audit nhất quán

Audit record **đôi khi là một phần của business invariant**: ví dụ một order phải có audit “transition to PAID” cùng lúc với status. Khi đó:

- Nếu audit chỉ là vài entries giới hạn và vòng đời chung, có thể nhúng event trong **order document** và update atomically.
- Nếu audit phải lưu vô hạn trong collection riêng **và** không được bỏ sót, có thể dùng transaction cho status + audit/outbox record.
- Nếu audit chỉ là telemetry có thể trễ/mất một số entries theo policy, bất biến nhẹ hơn và có thể dùng asynchronous pipeline.

Từ “audit” không tự quyết định transaction; **mức bảo đảm nghiệp vụ yêu cầu với audit** mới là yếu tố phân biệt.

## 20. Kịch bản phân tích toàn diện

### 20.1. Một đơn hàng thương mại điện tử

Đơn O-100 gồm:

~~~text
Order document:
  status = DRAFT
  lines = [SKU-RED qty3, SKU-BLUE qty1]

Inventory documents:
  SKU-RED, SKU-BLUE

Reservation documents:
  R-RED, R-BLUE

Payment provider:
  External service

Outbox:
  Events to publish
~~~

Phân loại từng yêu cầu:

| Yêu cầu | Phạm vi | Quyết định |
|---|---|---|
| Chỉ đổi status/updatedAt trên order | Một doc | Conditional update. |
| Giữ đúng SKU-RED không âm | Một inventory doc | Conditional `$inc`. |
| Giữ cả RED và BLUE, cùng reservation records và đổi order | Nhiều MongoDB docs | Transaction nếu không cho partial commit. |
| Gửi email ngay sau order confirmed | MongoDB + SMTP | Outbox dispatcher, không SMTP trong transaction. |
| Chờ thanh toán vài phút | MongoDB + gateway | Payment saga/state machine, không mở transaction chờ. |
| Update dashboard doanh thu | Dữ liệu dẫn xuất | Có thể eventual theo version/checkpoint. |
| Đọc báo cáo khớp một thời điểm | Nhiều read docs | Snapshot consistency nếu nghiệp vụ đòi. |

### 20.2. Transaction boundary phải tách khỏi business workflow dài

Một workflow tốt có thể là:

~~~text
Step A (MongoDB transaction ngắn):
  Reserve all local SKUs
  Create reservation records
  Set order = RESERVED
  Insert outbox event
Commit
         |
         v
Step B (ngoài transaction):
  Request payment with idempotency key
         |
      +-- success --> Step C (transaction ngắn):
      |                  Mark order PAID
      |                  Insert outbox ORDER_PAID
      |                Commit
      |
      +-- failure --> Step D (transaction/compensation):
                         Release reservation
                         Mark order PAYMENT_FAILED
                         Insert outbox ORDER_RELEASED
                       Commit
~~~

Đây là một ví dụ **kết hợp transaction local và saga toàn flow**. Không có transaction nào mở xuyên bước gọi payment gateway. Nếu bước D thất bại, cần retry idempotent/repair worker. Nếu Step C commit thành công nhưng event chưa phát, outbox dispatcher có thể tiếp tục.

### 20.3. Bảo vệ chống replay ở từng bước

Mỗi bước nên có ID:

~~~text
orderId = O-100
reservationId = RES-O-100
paymentRequestId = PAY-O-100
outboxEventId = ORDER_PAID-O-100
~~~

Khi retry:

- Nếu reservation đã giữ, không trừ stock lần nữa.
- Nếu payment đã thành công, không charge lại với request ID mới.
- Nếu order đã PAID, không chuyển lại như một sự kiện mới.
- Nếu event đã phát, consumer không thực hiện side effect hai lần.

**Atomicity xử lý lỗi một phần bên trong một ranh giới; idempotency xử lý việc cùng ý định nghiệp vụ bị lặp qua nhiều ranh giới.**

### 20.4. Khi business thay đổi invariant

Một startup có thể ban đầu chỉ bán sản phẩm có một SKU/order: một conditional update inventory đủ. Sau đó giỏ hàng hỗ trợ nhiều SKU/order và cần cùng giữ tất cả: ranh giới consistency đã thay đổi và transaction trở thành ứng viên. Sau nữa hệ thống tách inventory sang service riêng: MongoDB transaction không còn bao trùm remote service, cần saga/reservations. **Quyết định dùng transaction thay đổi theo kiến trúc và policy**, không phải một đặc điểm bất biến của MongoDB.

## 21. Bài tập thực hành và đáp án gợi ý

Mỗi bài tập là một **tình huống độc lập**. Nếu chạy lệnh trên database `txn_need_lab` đã bị thay đổi bởi ví dụ trước đó, hãy tạo một collection demo khác hoặc thiết lập lại fixture trong môi trường lab. Không dùng các lệnh thay đổi số dư/tồn kho trên production để thử nghiệm.

### Bài 1 — Một document, hai field

**Đề:** Inventory document `{_id:"SKU-1",available:10,reserved:0}`. Một request cần giảm available 3 và tăng reserved 3. Có cần multi-document transaction không?

**Đáp án:** Không, vì cả hai field ở **cùng một document**:

~~~javascript
db.inventory.updateOne(
  { _id: "SKU-1", available: { $gte: 3 } },
  { $inc: { available: -3, reserved: 3 } }
)
~~~

Đây là **một conditional atomic update**. Lọc available trong chính operation để tránh race.

### Bài 2 — Hai documents nhưng không có invariant chung

**Đề:** Một job cần đánh dấu 50.000 products `lastIndexedVersion:7`. Nếu dừng giữa chừng, job tiếp tục sau bằng filter version cũ; query tiêu dùng chấp nhận dữ liệu cũ vài phút. Cần transaction cho 50.000 products không?

**Đáp án:** Không. `updateMany`/`bulkWrite` theo batch với checkpoint và idempotency thường phù hợp hơn. Partial progress là trạng thái **được phép**.

### Bài 3 — Chuyển tiền giữa hai tài khoản

**Đề:** Debit 150 ở account A, credit 150 ở B. Cần tính nhất quán tức thì qua hai documents. Chọn gì?

**Đáp án:** Multi-document transaction, kiểm tra debit/credit matchedCount và ghi stable transfer record cùng transaction; chọn read/write concern thích hợp. Không dùng hai updateOne độc lập như một atomic unit.

### Bài 4 — `bulkWrite(ordered:true)`

~~~javascript
db.accounts.bulkWrite([
  {
    updateOne: {
      filter: { _id: "A" },
      update: { $inc: { balance: -50 } }
    }
  },
  {
    updateOne: {
      filter: { _id: "B" },
      update: { $inc: { balance: 50 } }
    }
  }
], { ordered: true })
~~~

**Đề:** Nếu B không tồn tại, ordered bulk có tự rollback debit A không?

**Đáp án:** Không. `updateOne` không match B **không mặc định là lỗi**, mà trả matchedCount 0 trong result; ordered bulk không biết invariant “phải có B”. Nếu cần cả hai cùng thành công, dùng transaction và **kiểm tra business condition**, không chỉ nhìn command có ném exception hay không.

### Bài 5 — Unique username

**Đề:** Hai requests đồng thời đăng ký cùng username. Mục tiêu chỉ là không tạo hai users có cùng username. Có cần transaction bao `findOne + insertOne` không?

**Đáp án:** Thông thường **không**. Unique index trên username (với canonicalization/collation và null policy phù hợp) là cơ chế bảo vệ ở database; ứng dụng xử lý `E11000`. Check trước chỉ nâng UX, không chống race.

### Bài 6 — User và wallet

**Đề:** Khi tạo user ACTIVE, phải tạo wallet document cùng lúc; không có trạng thái PENDING được phép. Hai inserts ở hai collections. Nên dùng gì?

**Đáp án:** Transaction trên hai inserts, cùng session; nếu wallet insert lỗi thì user insert cũng abort. Tạo indexes/collections trước khi triển khai và dùng stable request ID.

### Bài 7 — Có trạng thái PENDING

**Đề:** Đổi policy: user mới được `PENDING_WALLET`, chỉ ACTIVE sau khi wallet được tạo thành công. Worker có thể retry. Transaction vẫn bắt buộc không?

**Đáp án:** Không. Có thể dùng workflow eventual với create wallet idempotent, transition theo trạng thái và repair worker. Invariant mới là “ACTIVE user phải có wallet”, không phải “mọi PENDING user đã có wallet”.

### Bài 8 — Hai SKU, yêu cầu all-or-nothing

**Đề:** Order cần SKU-A qty2 và SKU-B qty4. Nếu SKU-B thiếu, SKU-A không được giữ. Hai SKUs là hai inventory documents. Chọn cách nào?

**Đáp án:** Transaction với hai conditional updates và reservation/order state trong cùng phạm vi, abort nếu bất kỳ matchedCount=0. Hoặc thay đổi nghiệp vụ cho phép PENDING + compensation, khi đó saga là phương án khác; không coi hai independent conditional updates là all-or-nothing.

### Bài 9 — CAS trong một document

**Đề:** Hai admins cùng sửa order version 3. Bạn muốn chỉ một update thành công, người còn lại thấy conflict.

**Đáp án:**

~~~javascript
db.orders.updateOne(
  { _id: "O-1", version: 3 },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 }
  }
)
~~~

Nếu update đầu tăng version lên 4, update còn lại có `matchedCount:0`. Không cần multi-document transaction cho một order document.

### Bài 10 — Balance query và snapshot

**Đề:** Một report đọc account A, sau đó một transaction chuyển tiền A → B commit, rồi report đọc B. Report cộng A+B có thể sai so với cả trạng thái trước/sau transaction không?

**Đáp án:** Có, vì hai reads độc lập ở **hai thời điểm**. Nếu cần report nhất quán, chọn read concern/snapshot transaction hoặc một bản chốt sổ versioned. Atomicity của transaction ghi không biến mọi reads không thuộc snapshot thành nhất quán đa tài liệu.

### Bài 11 — Write skew

**Đề:** Hai bác sĩ A/B đang trực; quy tắc ít nhất một người trực. T1 đọc cả hai, cho A nghỉ; T2 đọc cả hai, cho B nghỉ. T1/T2 cập nhật **hai documents khác nhau**. Chỉ đặt chúng trong snapshot transactions đã đủ chắc chắn invariant không bị vi phạm chưa?

**Đáp án:** Chưa. **Write skew** có thể xảy ra dưới snapshot isolation nếu chúng không tranh cùng document/guard. Cần một shared guard document cập nhật có điều kiện hoặc thiết kế invariant trong một aggregate, kiểm soát conflicts và retry.

### Bài 12 — `w:"majority"`

**Đề:** Nếu debit A và credit B là hai independent writes đều dùng `w:"majority"`, MongoDB có đảm bảo cùng commit hoặc cùng rollback không?

**Đáp án:** Không. Majority write concern điều khiển mức xác nhận ghi **của từng lệnh**. Nó không biến hai writes độc lập thành transaction.

### Bài 13 — Transaction callback có thể retry

**Đề:** Trong `session.withTransaction()`, code gọi payment gateway charge, rồi commit MongoDB. Driver gặp transient error và retry callback. Rủi ro gì?

**Đáp án:** Payment có thể bị charge **lần thứ hai** vì call ra hệ thống ngoài không thuộc transaction. Không đặt external side effect trong callback. Dùng gateway idempotency key, outbox/saga và trạng thái workflow tách khỏi transaction MongoDB.

### Bài 14 — Unknown commit result

**Đề:** Client nhận `UnknownTransactionCommitResult` sau commit chuyển tiền. Có nên lập tức mở transaction mới với transfer ID mới không?

**Đáp án:** Không. Transaction trước **có thể đã commit**. Sử dụng transaction API để retry commit theo hướng dẫn, tra stable transferId/đối soát khi cần; không replay nghiệp vụ với ID mới vô điều kiện.

### Bài 15 — Duplicate transfer ID

**Đề:** Một HTTP request lặp lại cùng `requestId:"TX-1"` nhưng payload lần hai có amount khác. Unique index báo duplicate. Backend nên trả “đã chuyển thành công” hay gì?

**Đáp án:** Phải **so sánh payload** với record cũ. Nếu khác amount/from/to/currency, trả **conflict** và không chuyển tiền lần nữa. Không coi mọi duplicate key là idempotent success.

### Bài 16 — Migration không thể lộ dữ liệu nửa cũ nửa mới

**Đề:** Một hệ thống muốn chuyển đổi 1 triệu documents, nhưng không được để reader thấy một phần schema cũ, một phần schema mới. Có nên dùng một transaction khổng lồ?

**Đáp án:** Không mặc định. Cân nhắc **versioned datasets**, dual-read/write tương thích, backfill vào collection mới rồi **atomic pointer/metadata switch** khi sẵn sàng, hoặc workflow phù hợp. Một transaction triệu records có thể vượt lifetime/cache limits và gây contention. Chỉ dùng transaction ở ranh giới nhỏ thật sự cần commit cùng nhau.

### Bài 17 — Outbox và event lặp

**Đề:** Transaction commit order và outbox event. Dispatcher publish event thành công nhưng chết trước khi đánh dấu dispatched. Khi restart, event publish lại. Outbox có thất bại không?

**Đáp án:** Không hẳn. Đây là tình huống **at-least-once delivery**. Consumer cần dedupe theo eventId; outbox bảo đảm ý định phát event được lưu cùng DB state, không tự bảo đảm exactly-once của hệ thống ngoài.

### Bài 18 — Same shard

**Đề:** Hai account documents cùng nằm trên một shard của sharded cluster. Vì cùng shard, có thể dùng hai updateOne độc lập thay transaction để bảo đảm debit/credit cùng commit không?

**Đáp án:** Không. **Cùng shard không phải cùng document**. Nếu cần all-or-nothing giữa hai documents thì transaction hoặc thay đổi mô hình/logic nghiệp vụ vẫn cần thiết.

### Bài 19 — Hai fields trong một embedded order

**Đề:** Một order document chứa `status`, `confirmedAt`, `shippingAddressSnapshot` và `items`. Chỉ cần sửa status/confirmedAt cùng nhau. Dùng transaction nhiều documents có lợi gì?

**Đáp án:** Thường không cần. Một conditional `updateOne` trên order document đã đảm bảo atomicity; thêm multi-document transaction làm API phức tạp hơn mà không giải quyết một invariant liên document nào.

### Bài 20 — Transaction quá dài

**Đề:** Một transaction mở trong 8 phút, scan nhiều documents, gọi HTTP service, rồi commit. Nguy cơ gì?

**Đáp án:** Transaction có lifetime limit/cache/lock constraints, dễ abort/conflict, external service không nằm trong commit và có thể bị gọi lại. Tách thành transactions ngắn cho local invariants; còn workflow HTTP dùng saga/outbox/idempotency.

### Bài 21 — Khi nào transaction vẫn không bảo vệ business rule?

**Đề:** Trong transaction, code update A giảm 150 và B tăng **120**, tất cả lệnh thành công. MongoDB có ngăn commit vì tổng tiền thay đổi không?

**Đáp án:** Không tự ngăn. Transaction bảo đảm các **lệnh đã viết cùng commit/abort**, không hiểu số tiền phải bảo toàn. Application cần kiểm tra amount và ledger invariants; có thể dùng thiết kế double-entry, validation và đối soát.

### Bài 22 — “Update không match” trong transaction

**Đề:** Transaction gọi `updateOne({balance:{$gte:500}},{$inc:{balance:-500}})` nhưng trả `matchedCount:0`, không có exception. Nếu code không kiểm tra và vẫn credit account B, transaction có thể commit không?

**Đáp án:** Có. Update không match không mặc định ném lỗi; nếu application vẫn commit, B có thể được cộng tiền mà A không bị trừ. **Phải kiểm tra matchedCount** và throw/abort khi business precondition không thỏa.

### Bài 23 — Transaction để tạo dữ liệu ở nhiều collections

**Đề:** Một đơn hàng phải có một `orders` document và một `invoice` document để được coi là POSTED. Nếu invoice insert thất bại, order không được tồn tại ở trạng thái POSTED. Mô hình nào hợp lý?

**Đáp án:** Transaction tạo/cập nhật order và invoice cùng commit, hoặc workflow có trạng thái PENDING_INVOICE và không công bố POSTED trước khi invoice có. Lựa chọn phụ thuộc khả năng chấp nhận trạng thái trung gian.

### Bài 24 — Dùng transaction để đảm bảo email duy nhất?

**Đề:** Trong transaction, hai requests đồng thời chạy find email rồi insert email như nhau, nhưng **không** có unique index. Có thể đảm bảo không có duplicate email không?

**Đáp án:** Không nên dựa vào điều đó. Hai transactions có thể đọc snapshot không thấy email rồi ghi **hai documents khác nhau**; không có unique constraint để chặn key trùng. Dùng **unique index** làm điểm bảo vệ, không thay bằng check-then-insert trong transactions.

### Bài 25 — Tách business workflow

**Đề:** Một flow cần (a) tạo reservation trong MongoDB, (b) gọi payment gateway và (c) gửi email. Có thể mở một MongoDB transaction xuyên cả ba để đảm bảo all-or-nothing không?

**Đáp án:** Không. Payment/email không nằm trong MongoDB transaction; thiết kế transaction ngắn cho reservation/outbox, gateway idempotency, saga với compensation và dispatcher/consumer idempotent. Kết quả tổng thể có thể eventual với trạng thái rõ ràng.

## 22. Tài liệu MongoDB chính thức và hướng học tiếp

Các liên kết sau giúp kiểm tra cú pháp và giới hạn **theo MongoDB Server/Driver version**. Với deployment thực tế, hãy tham chiếu phiên bản MongoDB đang chạy (cùng FCV, topology và driver version), không áp dụng nguyên văn một giới hạn của phiên bản khác.

1. [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — bảo đảm atomic một document; concurrent updates và điều kiện lọc tại thời điểm ghi.
2. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — các loại transaction, all-or-nothing, replica set/sharded cluster, read/write concerns.
3. [Transactions — Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — lock, WiredTiger cache, lifetime, DDL, sharded concerns và operational constraints.
4. [Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — error labels và retry logic, drivers/convenient APIs.
5. [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — khác biệt technical retries và business request replay.
6. [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — `local`, `majority`, `snapshot` và tính nhất quán khi đọc.
7. [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j` và mức xác nhận ghi.
8. [Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — các mô hình quan sát của reads, single-document atomicity và transaction snapshot.
9. [`db.collection.updateOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — filter + update operators + matchedCount, arrayFilters và upsert.
10. [`db.collection.updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — atomicity từng document khi sửa nhiều documents.
11. [`db.collection.bulkWrite()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/) — ordered/unordered, xử lý lỗi từng operation và partial success.
12. [`db.collection.findOneAndUpdate()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/) — đọc/sửa/trả một document nguyên tử.
13. [Model Data for Atomic Operations](https://www.mongodb.com/docs/manual/tutorial/model-data-for-atomic-operations/) — thiết kế document để nhiều field cần đổi cùng nhau.
14. [Embedded Data](https://www.mongodb.com/docs/manual/data-modeling/embedding/) — lợi ích embedding và giới hạn cardinality/vòng đời.
15. [References](https://www.mongodb.com/docs/manual/data-modeling/references/) — khi dữ liệu nên là documents riêng.
16. [Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — giới hạn BSON 16 MiB và các giới hạn hệ thống.
17. [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — bảo vệ business key khỏi duplicate giữa requests đồng thời.
18. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `withTransaction()`, `TransactionOptions` và error handling.
19. [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/) — `updateOne()`, builders và xử lý kết quả.
20. [MongoDB 8.0 — Transactions](https://www.mongodb.com/docs/v8.0/core/transactions/) — tài liệu cố định ở nhánh 8.0 để kiểm tra hành vi/giới hạn.
21. [MongoDB 7.0 — Transactions](https://www.mongodb.com/docs/v7.0/core/transactions/) — tham chiếu nhánh 7.0 cho hệ thống chưa nâng cấp.
22. [MongoDB Drivers API — Transactions Specification](https://github.com/mongodb/specifications/blob/master/source/transactions/transactions.md) — các khái niệm session, retry và behavior ở mức driver specification, dành cho người học nâng cao.

### 22.1. Tóm tắt từng câu hỏi cho một pull request

Trước khi merge một thay đổi có dùng transaction, người review có thể tự hỏi:

1. **Invariant nào phải được giữ?** Viết dưới dạng kiểm chứng được, ví dụ “không có transfer chỉ debit mà chưa credit”.
2. **Invariant nằm trên bao nhiêu documents?** Có thể đặt hợp lý trong một document không?
3. **Trạng thái PENDING/partial progress có được phép không?** Nếu có, liệu saga/batching với reconciliation đủ không?
4. **Mọi write thuộc transaction có dùng cùng session không?** Có write nào vô tình chạy ngoài transaction?
5. **Các conditional updates đã kiểm tra `matchedCount` chưa?** Transaction không tự ném lỗi khi filter không match.
6. **Có unique business ID và idempotency không?** Timeout sau commit có thể dẫn tới API replay.
7. **Có external calls trong transaction callback không?** Chuyển sang outbox/saga nếu có side effect.
8. **Retry/commit outcome được phân loại đúng không?** Không replay vô điều kiện khi commit chưa rõ.
9. **Có write skew/invariant qua nhiều documents không được tranh chấp không?** Có cần shared guard/CAS?
10. **Phạm vi transaction có nhỏ, có index và đủ giới hạn tài nguyên không?** Cần đo dưới concurrency.

## 23. Kết luận

**Chỉ cần giao dịch nhiều document khi bất biến nghiệp vụ đòi những thay đổi trên nhiều MongoDB documents phải cùng commit hoặc cùng abort, hoặc khi một chuỗi đọc cần snapshot nhất quán tương ứng mà các phép đọc độc lập không bảo đảm.** Số lượng document/collection tự nó **không** quyết định có cần transaction: điều quyết định là **mức nhất quán được yêu cầu**.

Trước khi thêm transaction, hãy chọn đúng **aggregate/document boundary**, khai thác **atomic conditional update**, `$inc`, CAS/version và **unique indexes** cho những ràng buộc có thể bảo vệ ở một document hoặc một khóa. Nếu dữ liệu có vòng đời riêng và bất biến thật sự trải nhiều documents, một **transaction ngắn, có session, read/write concern và kiểm tra matchedCount** thường là lựa chọn rõ ràng.

Cuối cùng, transaction không phải “phép màu chống mọi race”: ứng dụng vẫn phải định nghĩa business invariants, tránh write skew bằng shared guards hoặc mô hình phù hợp, xử lý write conflicts/commit outcome, sử dụng **stable idempotency keys**, và chuyển **external side effects** sang outbox/saga khi cần. Thiết kế tốt nhất là thiết kế dùng **ít transaction nhất mà vẫn giữ chính xác những bảo đảm nghiệp vụ bắt buộc**.
