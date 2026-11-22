# Cập nhật có điều kiện và so sánh phiên bản trước khi ghi trong MongoDB

## 1. Bài toán ghi đồng thời: lost update

Giả sử một sản phẩm trong MongoDB có dữ liệu:

~~~javascript
{
  _id: "P-100",
  tenantId: "SHOP-A",
  name: "Wireless Mouse",
  priceCents: NumberLong(250000),
  stock: NumberInt(10),
  status: "ACTIVE",
  version: NumberLong(7)
}
~~~

Hai người dùng A và B cùng mở trang chỉnh sửa sản phẩm. Cả hai đều đọc giá 250000 và version 7. A đổi giá thành 260000; B đổi thành 240000. Nếu hai request chỉ tìm document theo _id:

~~~javascript
// Request A
db.products.updateOne(
  { _id: "P-100" },
  { $set: { priceCents: NumberLong(260000) } }
);

// Request B
db.products.updateOne(
  { _id: "P-100" },
  { $set: { priceCents: NumberLong(240000) } }
);
~~~

Cả hai đều có thể thành công. Request thực hiện sau sẽ ghi đè giá trị của request trước mà không biết nó đã thay đổi. Hiện tượng này gọi là **lost update**.

Đây **không phải lỗi atomicity của MongoDB**: từng lệnh ghi được áp dụng nguyên tử, nhưng filter chỉ theo _id không thể hiện yêu cầu “document phải vẫn ở trạng thái tôi đã đọc”.

**Nguyên tắc cốt lõi:** đưa giá trị hoặc phiên bản được kỳ vọng vào **filter của chính lệnh ghi**, rồi kiểm tra kết quả matchedCount.

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    version: NumberLong(7)
  },
  {
    $set: { priceCents: NumberLong(260000) },
    $inc: { version: NumberLong(1) }
  }
);
~~~

Nếu A ghi thành công, version tăng lên 8. Request B vẫn gửi expectedVersion = 7 sẽ không match và không thể âm thầm ghi đè giá mới. Kỹ thuật này thường được gọi là **optimistic concurrency control (OCC)**, **optimistic locking** hoặc **compare-and-swap (CAS)** ở cấp document.

### Mục tiêu của bài

- Hiểu atomicity một document và những race conditions ứng dụng vẫn phải tự xử lý.
- Viết conditional update dựa vào trạng thái hoặc giá trị cũ.
- Dùng version/revision để chặn các bản ghi dựa trên snapshot đã lỗi thời.
- Phân biệt trường hợp nên dùng **$set**, **$inc**, **findOneAndUpdate** và transaction.
- Xử lý conflict, retry, idempotency và write concern.
- Áp dụng MongoDB Java Sync Driver và Spring Data MongoDB với **@Version**.

## 2. Chuẩn bị dữ liệu thực hành

Dùng **mongosh** trên một database riêng:

~~~javascript
use mongo_concurrency_lab

db.products.insertMany([
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    name: "Wireless Mouse",
    priceCents: NumberLong(250000),
    stock: NumberInt(10),
    status: "ACTIVE",
    version: NumberLong(7),
    updatedAt: ISODate("2026-07-01T00:00:00Z")
  },
  {
    _id: "P-200",
    tenantId: "SHOP-A",
    name: "Mechanical Keyboard",
    priceCents: NumberLong(1000000),
    stock: NumberInt(3),
    status: "DRAFT",
    version: NumberLong(1),
    updatedAt: ISODate("2026-07-01T00:00:00Z")
  },
  {
    _id: "P-300",
    tenantId: "SHOP-B",
    name: "Laptop Stand",
    priceCents: NumberLong(400000),
    stock: NumberInt(8),
    status: "ACTIVE",
    version: NumberLong(2),
    updatedAt: ISODate("2026-07-01T00:00:00Z")
  }
]);
~~~

Mỗi ví dụ sau được giải thích dựa trên **trạng thái ban đầu**, trừ khi có ghi chú khác. Chạy update sẽ thay đổi dữ liệu lab; nên tạo lại dữ liệu có kiểm soát trước khi thử ví dụ độc lập. Nếu lặp lại insertMany với cùng _id, bạn có thể gặp duplicate key.

Các field có vai trò:

| Field | Vai trò |
|---|---|
| **_id** | Định danh document. |
| **tenantId** | Phạm vi tenant cần kiểm soát ở server. |
| **priceCents** | Giá lưu bằng số nguyên nhỏ nhất, tránh tính toán tiền bằng double trong ví dụ. |
| **stock** | Số hàng còn lại. |
| **status** | Trạng thái trong workflow. |
| **version** | Token so sánh để nhận biết document đã được sửa kể từ lần đọc trước. |
| **updatedAt** | Metadata thời gian, không nên mặc định thay cho version. |

**NumberLong** là BSON Int64, tương ứng kiểu **Long/long** ở Java. Version cần nhất quán về type và quy tắc khởi tạo.

## 3. Atomicity cấp document và giới hạn của nó

MongoDB bảo đảm một write operation lên **một document** là nguyên tử, kể cả khi thay đổi nhiều field:

~~~javascript
db.products.updateOne(
  { _id: "P-100" },
  {
    $set: {
      name: "Wireless Mouse Pro",
      status: "ACTIVE"
    },
    $inc: {
      version: NumberLong(1)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

Các thay đổi của lệnh trên được áp dụng cùng nhau trong một document. Với những update cạnh tranh, MongoDB kiểm tra lại điều kiện của filter khi áp dụng thao tác. Đây là cơ sở giúp conditional update đáng tin cậy.

Tuy nhiên, atomicity **không tự bảo đảm**:

1. Hai request cùng đọc dữ liệu cũ sẽ tự phát hiện xung đột.
2. Một chuỗi findOne rồi updateOne ở hai thời điểm khác nhau là nguyên tử.
3. Toàn bộ updateMany trên nhiều document là một transaction.
4. Các thay đổi ở email, thanh toán, message broker hoặc database khác nằm trong cùng atomicity.
5. MongoDB tự biết transition trạng thái nào hợp lệ cho domain.

**Atomicity là tính chất của lệnh ghi; concurrency correctness còn phụ thuộc vào điều kiện lọc và thiết kế nghiệp vụ.**

## 4. Conditional update theo trạng thái mong đợi

Một conditional update điển hình gồm:

~~~javascript
db.collection.updateOne(
  {
    _id: targetId,
    status: expectedStatus
  },
  {
    $set: { status: newStatus }
  }
);
~~~

Ví dụ chỉ cho phép sản phẩm **DRAFT → ACTIVE**:

~~~javascript
db.products.updateOne(
  {
    _id: "P-200",
    tenantId: "SHOP-A",
    status: "DRAFT"
  },
  {
    $set: { status: "ACTIVE" },
    $currentDate: { updatedAt: true }
  }
);
~~~

Khi P-200 đang DRAFT, lệnh có thể match và đổi sang ACTIVE. Nếu có request khác đã chuyển P-200 sang REJECTED hoặc ACTIVE, lệnh yêu cầu status DRAFT sẽ không còn match.

### 4.1. Phân tích UpdateResult

~~~javascript
const result = db.products.updateOne(
  {
    _id: "P-200",
    status: "DRAFT"
  },
  {
    $set: { status: "ACTIVE" }
  }
);

printjson(result);
~~~

Các giá trị thường cần kiểm tra:

- **matchedCount:** số document phù hợp với filter.
- **modifiedCount:** số document thực sự thay đổi.
- **acknowledged:** có nhận kết quả xác nhận từ server hay không.
- **upsertedId/upsertedCount:** chỉ có ý nghĩa nếu thao tác cho phép upsert.

Với P-200 ban đầu DRAFT, lần cập nhật thành công cho kết quả matchedCount = 1, modifiedCount = 1. Nếu chạy lại khi P-200 đã ACTIVE, filter status DRAFT không còn match: matchedCount = 0.

**matchedCount không phải số field đã sửa**, mà là số document. Với updateOne, giá trị thường là 0 hoặc 1.

### 4.2. Vì sao check-then-act không an toàn?

~~~javascript
// Pattern dễ có race condition:
const product = db.products.findOne({ _id: "P-200" });

if (product.status === "DRAFT") {
  db.products.updateOne(
    { _id: "P-200" },
    { $set: { status: "ACTIVE" } }
  );
}
~~~

Giữa findOne và updateOne, request khác có thể đã chuyển status sang REJECTED. Điều kiện trong JavaScript phía client không còn bảo vệ lệnh update.

Đúng hơn:

~~~javascript
db.products.updateOne(
  { _id: "P-200", status: "DRAFT" },
  { $set: { status: "ACTIVE" } }
);
~~~

Điều kiện trạng thái nằm ngay trong **filter của cùng lệnh ghi**, nên được kiểm tra tại thời điểm update.

## 5. Compare-and-swap theo giá trị field hiện tại

CAS có ý tưởng:

~~~text
IF currentValue == expectedValue:
    WRITE newValue
ELSE:
    DO NOT WRITE
~~~

Trong MongoDB:

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    priceCents: NumberLong(250000)
  },
  {
    $set: {
      priceCents: NumberLong(260000)
    }
  }
);
~~~

Hai request cùng kỳ vọng priceCents = 250000, nhưng ghi hai giá mới khác nhau, không thể đều match sau khi một thao tác đã thực sự thay đổi priceCents.

### 5.1. Mô phỏng A/B

~~~javascript
// A:
const a = db.products.updateOne(
  { _id: "P-100", priceCents: NumberLong(250000) },
  { $set: { priceCents: NumberLong(260000) } }
);

// B:
const b = db.products.updateOne(
  { _id: "P-100", priceCents: NumberLong(250000) },
  { $set: { priceCents: NumberLong(240000) } }
);
~~~

Nếu A ghi trước: A match 1, B match 0, giá cuối là 260000. Nếu B ghi trước: B match 1, A match 0, giá cuối là 240000. Thứ tự phụ thuộc scheduling, không được mặc định A luôn thắng.

### 5.2. Giới hạn: chỉ nhận biết field được so sánh

Nếu một request khác sửa **name** nhưng giữ **priceCents**, filter chỉ so sánh priceCents vẫn match. Đây có thể là điều mong muốn khi hai field độc lập, nhưng có thể sai nếu quyết định giá dựa trên bản name/description cũ.

Khi cần bảo vệ **toàn bộ snapshot**, dùng một field **version chung** thường rõ ràng hơn việc liệt kê mọi field cũ.

### 5.3. ABA problem

Giả sử giá lần lượt:

~~~text
250000 -> 260000 -> 250000
~~~

Client cũ chỉ so sánh priceCents = 250000 có thể match lại, dù dữ liệu đã thay đổi hai lần. Đây là **ABA problem**.

Nếu mỗi lần ghi đều tăng version:

~~~text
price 250000, version 7
price 260000, version 8
price 250000, version 9
~~~

thì client giữ version 7 không thể ghi dựa trên snapshot cũ chỉ vì giá quay lại 250000.

## 6. Optimistic locking bằng version

### 6.1. Vòng đời một request

~~~text
Client A và B đọc:
  _id=P-100, price=250000, version=7
               |
       +-------+-------+
       |               |
       v               v
 A sửa giá         B sửa giá
       |               |
       v               v
 UPDATE WHERE       UPDATE WHERE
 version=7          version=7
       |               |
       v               v
 A ghi thành công   B không còn match
 version -> 8       nếu A đã thắng
       |               |
       v               v
  success             conflict
~~~

Ứng dụng không giữ khóa độc quyền trong suốt thời gian người dùng mở form. Chỉ tới lúc ghi mới so sánh version. Vì vậy đây là **optimistic locking**.

### 6.2. Lệnh CAS đầy đủ

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    version: NumberLong(7)
  },
  {
    $set: {
      name: "Wireless Mouse Pro",
      priceCents: NumberLong(260000)
    },
    $inc: {
      version: NumberLong(1)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

Từng phần có nhiệm vụ:

| Thành phần | Vai trò |
|---|---|
| **_id** | Định vị document. |
| **tenantId** | Giới hạn phạm vi tenant; server vẫn phải xác thực quyền. |
| **version:7** | Chỉ ghi nếu document vẫn ở phiên bản client đã đọc. |
| **$set** | Ghi các field nghiệp vụ được phép thay. |
| **$inc version:1** | Bảo đảm write thắng tạo phiên bản mới. |
| **$currentDate** | Cập nhật metadata thời gian phía server. |

**Version mới không do client tự chọn.** Client chỉ gửi expectedVersion, còn server kiểm tra và tăng phiên bản trong cùng update.

### 6.3. Tại sao phải tăng version trong cùng một lệnh?

Không làm:

~~~javascript
// Sai về tính nhất quán: hai lệnh riêng.
db.products.updateOne(
  { _id: "P-100", version: NumberLong(7) },
  { $set: { priceCents: NumberLong(260000) } }
);

db.products.updateOne(
  { _id: "P-100" },
  { $inc: { version: NumberLong(1) } }
);
~~~

Ứng dụng có thể crash giữa hai lệnh. Nếu giá đã đổi nhưng version chưa tăng, OCC sẽ không phát hiện thay đổi này.

Đúng là gộp **$set** và **$inc version** cùng một update:

~~~javascript
{
  $set: { priceCents: NumberLong(260000) },
  $inc: { version: NumberLong(1) }
}
~~~

MongoDB bảo đảm cả hai thay đổi thuộc cùng thao tác nguyên tử trên document.

### 6.4. Tất cả write paths liên quan phải tăng version

Nếu Service A dùng version CAS nhưng Service B cập nhật trực tiếp theo _id mà không tăng version:

~~~javascript
// Service B bypass version:
db.products.updateOne(
  { _id: "P-100" },
  { $set: { name: "Other Name" } }
);
~~~

thì client có thể vẫn giữ version cũ và không phát hiện name đã thay đổi. Phải thống nhất quy ước cho API, batch job, migration, admin script và các worker nền.

Nếu một số field kỹ thuật được phép đổi mà không tăng version, quyết định này phải được xác định rõ và chứng minh không ảnh hưởng snapshot nghiệp vụ.

### 6.5. Khởi tạo và lưu version

Một convention:

~~~javascript
db.products.insertOne({
  _id: "P-NEW",
  name: "New Product",
  version: NumberLong(0)
});
~~~

Sau lần ghi thành công đầu tiên, version = 1. Bắt đầu từ 0 hay 1 đều có thể được lựa chọn, nhưng phải thống nhất theo thư viện và hệ thống.

Nguyên tắc:

1. Dùng kiểu số nguyên phù hợp, thường BSON Int64/Java Long.
2. Không để document cần CAS thiếu version.
3. Không cho client gán version tùy ý.
4. Migration document legacy phải đưa về một convention thống nhất.
5. Tránh làm version quay về giá trị cũ khi restore/migration mà client cũ còn hoạt động.

## 7. API đọc và ghi dữ liệu kèm version

Phía đọc:

~~~javascript
db.products.findOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A"
  },
  {
    name: 1,
    priceCents: 1,
    status: 1,
    version: 1
  }
);
~~~

API trả:

~~~json
{
  "id": "P-100",
  "name": "Wireless Mouse",
  "priceCents": 250000,
  "status": "ACTIVE",
  "version": 7
}
~~~

Client gửi:

~~~json
{
  "name": "Wireless Mouse Pro",
  "priceCents": 260000,
  "expectedVersion": 7
}
~~~

Server lấy tenant/authorization từ ngữ cảnh đã xác thực, validate dữ liệu, sau đó tạo filter theo _id, tenantId và expectedVersion. Không dùng expectedVersion làm bằng chứng quyền truy cập: version không phải bí mật.

### 7.1. Phản hồi conflict

Khi version không match, API có thể trả:

~~~json
{
  "code": "VERSION_CONFLICT",
  "message": "Product was updated by another request.",
  "expectedVersion": 7,
  "currentVersion": 8
}
~~~

Chỉ trả **currentVersion** nếu server đã đọc lại và người dùng có quyền xem resource. Đọc lại là một thao tác riêng và cũng có thể cạnh tranh với các update tiếp theo; không coi đây là lịch sử bất biến.

### 7.2. HTTP status

- **200 / 204:** cập nhật thành công.
- **409 Conflict:** phiên bản stale theo API contract.
- **412 Precondition Failed:** thường phù hợp khi dùng HTTP **If-Match** với ETag.
- **404:** không tìm thấy trong phạm vi được phép.
- **400 / 422:** payload/transition sai contract.

Ví dụ conditional HTTP request:

~~~http
PATCH /products/P-100
If-Match: "v7"
Content-Type: application/json

{"name":"Wireless Mouse Pro"}
~~~

Server chuyển ETag theo contract thành expectedVersion = 7 rồi đưa vào MongoDB filter. **ETag không tự tạo OCC nếu lệnh database không so sánh phiên bản.**

## 8. Đọc đúng matchedCount và modifiedCount

~~~javascript
const result = db.products.updateOne(
  {
    _id: "P-100",
    version: NumberLong(7)
  },
  {
    $set: {
      priceCents: NumberLong(260000)
    },
    $inc: {
      version: NumberLong(1)
    }
  }
);

printjson(result);
~~~

Nếu match và write thành công, thường thấy matchedCount = 1, modifiedCount = 1. Nếu version đã khác, matchedCount = 0, modifiedCount = 0.

**matchedCount = 0 không phải bằng chứng duy nhất của version conflict**, vì còn những nguyên nhân:

- _id không tồn tại.
- Document thuộc tenant khác.
- Status/business precondition không thỏa.
- Version đã đổi.
- Một điều kiện khác trong filter không đúng.

Nếu cần phân biệt, server có thể đọc lại trong phạm vi authorization:

~~~javascript
db.products.findOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A"
  },
  {
    version: 1,
    status: 1,
    stock: 1
  }
);
~~~

**matchedCount = 1, modifiedCount = 0** vẫn có thể hợp lệ khi chỉ $set một field bằng giá trị nó đã có. Với CAS tăng version bằng $inc khi match, version thường thực sự đổi và modifiedCount thường = 1.

### 8.1. Acknowledged write concern

OCC cần biết thao tác có match hay không. Với **WriteConcern.UNACKNOWLEDGED**, ứng dụng không nhận được kết quả write đáng tin cậy để phân loại stale version. Hãy dùng write concern có acknowledgement; có thể cân nhắc **majority** tùy yêu cầu durability.

Write concern giải quyết sự xác nhận/durability của ghi, **không thay thế** filter theo version.

## 9. $inc và atomic arithmetic: khi không cần đọc trước

Với một counter, ứng dụng không nhất thiết phải đọc giá trị rồi tính toán trong RAM:

~~~javascript
db.counters.insertOne({
  _id: "PAGE_VIEWS",
  count: NumberLong(0)
});

db.counters.updateOne(
  { _id: "PAGE_VIEWS" },
  { $inc: { count: NumberLong(1) } }
);

db.counters.updateOne(
  { _id: "PAGE_VIEWS" },
  { $inc: { count: NumberLong(1) } }
);
~~~

Nếu mỗi lệnh thành công một lần, giá trị cuối bằng **2**. Hai thao tác **$inc** không ghi đè giá trị cộng của nhau như cách mỗi client đọc count=0 rồi **$set count=1**.

### 9.1. So sánh với read-modify-write

~~~text
Không an toàn:

A đọc count = 0
B đọc count = 0
A tính 0+1=1
B tính 0+1=1
A $set count=1
B $set count=1
Kết quả có thể = 1

Sử dụng $inc:

A $inc count by 1
B $inc count by 1
Kết quả = 2 nếu cả hai được áp dụng một lần
~~~

### 9.2. $inc không giống CAS trên snapshot

**$inc** phù hợp cho tăng/giảm một giá trị hiện tại, không tự phát hiện mọi thay đổi khác trên document. Nếu client sửa name, price, description dựa trên một snapshot toàn bộ, vẫn có thể cần version.

### 9.3. $inc không idempotent khi application replay

Nếu client gửi lại một request như một **nghiệp vụ mới**, $inc có thể tăng lần nữa. Driver hỗ trợ **retryable writes** trong những điều kiện nhất định bằng cách nhận diện retry của cùng logical write; không có nghĩa ứng dụng có thể tự tạo các lệnh mới rồi gửi lặp không giới hạn mà vẫn đúng exactly-once.

Những nghiệp vụ đặt hàng, ghi tiền, trừ tồn kho cần **idempotency key** hoặc cơ chế chống xử lý trùng phù hợp.

## 10. Giữ tồn kho không âm bằng conditional update

Giả sử **stock=10** và hai request đồng thời muốn mua 7 sản phẩm.

Pattern không an toàn:

~~~javascript
const product = db.products.findOne({
  _id: "P-100"
});

if (product.stock >= 7) {
  db.products.updateOne(
    { _id: "P-100" },
    { $inc: { stock: -7 } }
  );
}
~~~

Giữa **findOne** và **updateOne**, request khác có thể đã trừ stock. Hai client đều đọc stock=10 rồi cùng trừ 7 sẽ tạo stock=-4 nếu không có điều kiện tại thời điểm ghi.

**Đúng:** đặt điều kiện trong filter của chính update:

~~~javascript
const requestedQty = 7;

const result = db.products.updateOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    status: "ACTIVE",
    stock: { $gte: requestedQty }
  },
  {
    $inc: {
      stock: -requestedQty,
      version: NumberLong(1)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);

printjson(result);
~~~

Nếu A thắng, stock đổi từ 10 thành 3. B kiểm tra **stock >= 7** trên giá trị mới và **không match**. Nếu B thắng trước, A bị từ chối tương tự.

**Không phải cứ dùng $inc là stock không âm.** Phải kết hợp điều kiện **stock >= requestedQty** trong filter.

### 10.1. Phải kiểm tra lượng đặt mua

Nếu client gửi requestedQty = -5, phép toán **-requestedQty** trở thành +5, làm stock tăng. Server cần validate lượng đặt mua **là số nguyên dương**, nằm trong giới hạn cho phép, không NaN và không vượt miền kiểu BSON.

### 10.2. Có cần lọc version khi trừ tồn kho?

Với thao tác “trừ nếu stock hiện tại đủ”, filter stock >= qty và $inc âm đủ để bảo vệ invariant trong một document, không bắt buộc phải dựa trên snapshot version.

Bạn có thể **tăng version** để báo document đã đổi cho các UI quản trị, nhưng **lọc expectedVersion** có thể gây conflict không cần thiết với các request mua khác nếu quy tắc chỉ phụ thuộc stock hiện tại.

Phân biệt:

| Nghiệp vụ | Cách làm phù hợp |
|---|---|
| Trừ stock hiện tại nếu đủ | **{stock:{$gte:qty}} + $inc**. |
| Admin sửa stock thành một số tuyệt đối từ form cũ | **{version:expected} + $set stock + $inc version**. |
| Đổi trạng thái đơn khi vẫn NEW | **{status:"NEW"} + $set status**. |
| Ghi cả một snapshot nhiều field | **Version CAS**. |

## 11. findOneAndUpdate: ghi có điều kiện và đọc trạng thái mới

**updateOne()** trả UpdateResult, không trực tiếp trả document mới. **findOneAndUpdate()** có thể cập nhật và trả document trước hoặc sau update theo option.

~~~javascript
db.products.findOneAndUpdate(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    version: NumberLong(7)
  },
  {
    $set: {
      name: "Wireless Mouse Plus"
    },
    $inc: {
      version: NumberLong(1)
    }
  },
  {
    returnDocument: "after",
    projection: {
      _id: 1,
      name: 1,
      version: 1
    }
  }
);
~~~

Nếu match, trả document **sau khi cập nhật**; nếu không có document phù hợp và không upsert, thường trả **null**.

Lợi ích là không cần updateOne rồi findOne rời nhau chỉ để lấy version mới. Một request khác có thể sửa document trong khoảng giữa updateOne và findOne của cách hai bước.

**Lưu ý:** findOneAndUpdate không tự bật OCC nếu không có điều kiện version trong filter. Nó cũng có đặc điểm tài nguyên/retryable writes riêng, cần đo trên document lớn và topology thực tế.

## 12. OCC conflict và cách ứng dụng xử lý

### 12.1. Không tự thay expectedVersion rồi ghi lại payload cũ

Khi client gửi expectedVersion=7 nhưng server đang version=8, cách xử lý sai là đọc version=8 rồi **gửi lại payload cũ nguyên vẹn mà không xem thay đổi mới**.

Điều đó biến optimistic locking thành **last-write-wins trá hình**.

Cách xử lý tốt hơn:

1. Từ chối ghi stale với mã lỗi rõ ràng.
2. Cho client tải lại snapshot mới hoặc hiển thị thay đổi của người khác.
3. Nếu domain cho phép, tính **delta** và merge có chủ đích trên snapshot mới.
4. Thực hiện CAS mới với version hiện tại sau khi đã resolve.
5. Giới hạn số lần retry; không lặp vô hạn.

### 12.2. Phân biệt xung đột và lỗi mạng

Một **acknowledged update trả matchedCount=0** là outcome rõ: không có document match điều kiện.

Ngược lại, khi **timeout hoặc mất kết nối sau khi gửi lệnh**, ứng dụng có thể không biết server đã ghi thành công và response bị mất hay thao tác chưa được áp dụng. Đây là **unknown outcome** và cần logic khác với OCC conflict thông thường.

### 12.3. Version CAS hỗ trợ retry nhưng không chứng minh request đã thành công

Giả sử một request CAS version=7 đã thành công, làm version=8, nhưng response bị mất. Một lần gọi lại như request mới với filter version=7 không match.

Điều này tránh cùng payload bị ghi vào version mới, nhưng **matchedCount=0 không chứng minh chính request đầu tiên đã thành công**. Có thể một request khác đã cập nhật trước.

Khi cần phân biệt hai trường hợp, dùng **requestId/idempotency record** được ghi nhất quán với thay đổi nghiệp vụ.

### 12.4. Retry có giới hạn

Không viết:

~~~text
while conflict:
  readLatestVersion()
  writeOldPayloadAgain()
~~~

Với một phép cập nhật được phép tự tính lại như **increase by 1**, có thể dùng $inc thay vì vòng CAS. Với form chỉnh sửa có ý nghĩa, khi conflict cần resolve hoặc hỏi người dùng.

Trong luồng retry hợp lệ, có thể dùng **backoff/jitter**, giới hạn số lần, metrics và không lặp side effects ngoài database.

## 13. Idempotency key cho request có thể được gửi lại

Giả sử API nhận:

~~~json
{
  "requestId": "REQ-001",
  "accountId": "ACC-100",
  "amountCents": 5000
}
~~~

Nếu cùng **REQ-001** được gửi lại do retry, hệ thống không được trừ tiền lần thứ hai.

Một cơ chế thường có **unique index trên idempotency key**:

~~~javascript
db.processed_requests.createIndex(
  {
    tenantId: 1,
    requestId: 1
  },
  {
    unique: true,
    name: "uq_tenant_request"
  }
);
~~~

Nhưng chỉ thêm unique index chưa đủ để bảo đảm hai bước sau nguyên tử:

~~~text
1. INSERT processed_requests
2. UPDATE account balance
~~~

Nếu process crash giữa hai bước, marker đã lưu nhưng tiền chưa trừ, hoặc ngược lại tùy thứ tự.

Giải pháp phù hợp có thể là:

- **Transaction** ghi marker và thay đổi trên nhiều document.
- **Một document** chứa cả marker và state được sửa trong cùng update, nếu kích thước/số lượng marker có giới hạn và domain cho phép.
- **Một protocol nghiệp vụ** có trạng thái, retry reconciliation và unique business keys.

Không lưu vô hạn requestIds trong một mảng duy nhất: document vẫn có giới hạn kích thước BSON thông dụng **16 MiB**.

## 14. updatedAt không mặc định thay được version

Một ứng dụng có thể thử CAS theo timestamp:

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    updatedAt: ISODate("2026-07-01T00:00:00Z")
  },
  {
    $set: {
      priceCents: NumberLong(260000)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

Timestamp có thể đóng vai trò token nếu luôn thay đổi và được giữ đúng precision. Tuy nhiên:

- **BSON Date có độ chính xác mili giây**; hai lần ghi gần nhau có thể tạo cùng timestamp.
- Các service có thể có clock skew.
- Chuyển qua JSON/JavaScript/Java có thể mất precision hoặc thay timezone.
- Có thể có write path quên cập nhật updatedAt.
- Migration/restore có thể giữ timestamp cũ.

Một **version số nguyên tăng theo mỗi lần ghi** thường rõ ràng hơn cho OCC. **updatedAt** vẫn hữu ích cho audit, hiển thị và giám sát.

## 15. CAS trên array embedded documents

Giả sử một đơn hàng:

~~~javascript
db.orders.insertOne({
  _id: "ORD-100",
  tenantId: "SHOP-A",
  status: "OPEN",
  version: NumberLong(3),
  items: [
    {
      lineId: "L1",
      sku: "SKU-A",
      qty: NumberInt(2),
      state: "NEW"
    },
    {
      lineId: "L2",
      sku: "SKU-B",
      qty: NumberInt(1),
      state: "RESERVED"
    }
  ]
});
~~~

Chỉ chuyển **line L1 từ NEW sang PACKED**, nếu order vẫn version=3:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-100",
    tenantId: "SHOP-A",
    version: NumberLong(3),
    items: {
      $elemMatch: {
        lineId: "L1",
        state: "NEW"
      }
    }
  },
  {
    $set: {
      "items.$[line].state": "PACKED"
    },
    $inc: {
      version: NumberLong(1)
    }
  },
  {
    arrayFilters: [
      {
        "line.lineId": "L1",
        "line.state": "NEW"
      }
    ]
  }
);
~~~

### 15.1. Vì sao cần cả $elemMatch và arrayFilters?

**Filter chính** chọn document có đúng version và tồn tại **một item vừa lineId L1 vừa state NEW**.

**arrayFilters** chọn item cần sửa **bên trong document đã được chọn**.

Nếu filter chính chỉ có _id/version và arrayFilters không tìm được item NEW, **$set trên items** có thể không thay đổi phần tử nào, nhưng **$inc version** vẫn được thực hiện vì document chính match. Thêm $elemMatch giúp ngăn tăng version khi không có item đủ điều kiện.

### 15.2. Tránh điều kiện array khớp ở các phần tử khác nhau

Filter:

~~~javascript
{
  "items.lineId": "L1",
  "items.state": "NEW"
}
~~~

có thể match document nếu hai điều kiện đúng ở **hai phần tử khác nhau**. Với yêu cầu cùng một item, dùng **$elemMatch** như trên.

### 15.3. Version phải tăng cùng thao tác sửa mảng

Một document có nhiều embedded items vẫn là **một document MongoDB**. Update items và tăng version trong cùng updateOne là một thao tác nguyên tử ở cấp document. Các client khác dùng version cũ sẽ biết document đã thay đổi, kể cả họ đang sửa một item khác.

Nếu conflict giữa các item độc lập xảy ra quá thường xuyên, có thể cân nhắc chia item thành collection riêng hoặc dùng điều kiện chi tiết theo item khi domain cho phép, thay vì bỏ toàn bộ OCC.

## 16. updateMany và atomicity xuyên document

~~~javascript
db.products.updateMany(
  {
    tenantId: "SHOP-A",
    status: "DRAFT"
  },
  {
    $set: {
      status: "ACTIVE"
    },
    $inc: {
      version: NumberLong(1)
    }
  }
);
~~~

Mỗi document được cập nhật nguyên tử, nhưng **toàn bộ nhiều document không tự trở thành một transaction**. Một số document có thể đã đổi trước khi các thao tác khác xen vào.

Với updateMany, không dùng **một expectedVersion chung** nếu mỗi document đang có version khác nhau mà không có chủ đích. Nếu nghiệp vụ yêu cầu tất cả document cùng commit hoặc rollback, cần thiết kế **multi-document transaction** hoặc một cơ chế ứng dụng phù hợp.

## 17. CAS không thay thế unique index

Giả sử hai request cùng kiểm tra xem email đã tồn tại:

~~~javascript
db.users.findOne({
  emailNormalized: "user@example.test"
});
~~~

Cả hai có thể đọc null rồi đều cố insert. Đây là race condition của pattern “check chưa tồn tại rồi tạo”.

Unique index:

~~~javascript
db.users.createIndex(
  {
    tenantId: 1,
    emailNormalized: 1
  },
  {
    unique: true,
    name: "uq_tenant_email"
  }
);
~~~

giúp MongoDB từ chối các document trùng unique key theo phạm vi được index bảo đảm. Với sharded collection, các unique constraints phải tuân theo yêu cầu shard key/index riêng.

| Kỹ thuật | Bất biến được bảo vệ |
|---|---|
| **Version CAS** | Không ghi snapshot lỗi thời lên một document đã đổi. |
| **Unique index** | Không tạo các khóa trùng bị cấm giữa nhiều document. |
| **Filter nghiệp vụ + $inc** | Không làm stock âm trong một document. |
| **Transaction** | Các thay đổi nhiều document commit/rollback cùng nhau theo semantics của transaction. |

## 18. Khi nào cần transaction?

Nếu một nghiệp vụ đặt hàng cần đồng thời:

1. Trừ stock của product.
2. Tạo order.
3. Ghi inventory movement.

thì một updateOne trên product chỉ bảo vệ stock ở document đó; nó **không bảo đảm** order và inventory movement cũng được tạo.

Trên topology MongoDB hỗ trợ transactions, có thể cân nhắc:

~~~text
BEGIN TRANSACTION
  UPDATE products with stock >= qty
  INSERT orders
  INSERT inventory_movements
COMMIT / ABORT
~~~

Transactions có chi phí, timeout/retry và ràng buộc vận hành riêng. Một transaction callback có thể được thực hiện lại khi gặp transient error, nên **không trực tiếp charge thẻ hay gửi email không-idempotent trong callback**.

Transaction giúp atomicity nhiều document, nhưng không thay thế version CAS nếu yêu cầu nghiệp vụ là **ngăn user lưu form từ snapshot cũ**. Không giữ transaction mở trong suốt thời gian người dùng đang chỉnh sửa; dùng read snapshot → user edits → conditional write hoặc short transaction lúc submit.

## 19. Java Sync Driver: cập nhật có điều kiện và version CAS

MongoDB Java Sync Driver cung cấp builders **Filters**, **Updates** và đối tượng kết quả **UpdateResult**.

### 19.1. Service cập nhật giá khi version còn đúng

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

public final class ProductCasService {
    private final MongoCollection<Document> products;

    public ProductCasService(MongoDatabase database) {
        this.products = database.getCollection("products");
    }

    public boolean updatePrice(
            String productId,
            String tenantId,
            long expectedVersion,
            long newPriceCents) {

        if (newPriceCents < 0) {
            throw new IllegalArgumentException(
                    "Price must be nonnegative"
            );
        }

        Bson filter = Filters.and(
                Filters.eq("_id", productId),
                Filters.eq("tenantId", tenantId),
                Filters.eq("version", expectedVersion)
        );

        Bson update = Updates.combine(
                Updates.set("priceCents", newPriceCents),
                Updates.inc("version", 1L),
                Updates.currentDate("updatedAt")
        );

        UpdateResult result = products.updateOne(
                filter,
                update
        );

        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                    "Optimistic locking needs acknowledged writes"
            );
        }

        return result.getMatchedCount() == 1;
    }
}
~~~

Giải thích:

- **expectedVersion** lấy từ snapshot client đã đọc.
- **Filters.eq("version", expectedVersion)** là điều kiện CAS.
- **Updates.inc("version",1L)** tăng version trong cùng thao tác ghi.
- **Updates.currentDate("updatedAt")** cập nhật metadata trên MongoDB server.
- **matchedCount=1** nghĩa filter đã match; **0** có thể là conflict, resource missing hoặc một điều kiện khác không thỏa.

Đây là một lớp persistence mẫu. Ứng dụng thực tế còn cần authorization, validation, exception handling, write concern và metrics.

### 19.2. Trừ tồn kho trong Java

Một method khác dùng cùng field products của service:

~~~java
public boolean reserveStock(
        String productId,
        String tenantId,
        int requestedQty) {

    if (requestedQty <= 0) {
        throw new IllegalArgumentException(
                "requestedQty must be positive"
        );
    }

    Bson filter = Filters.and(
            Filters.eq("_id", productId),
            Filters.eq("tenantId", tenantId),
            Filters.eq("status", "ACTIVE"),
            Filters.gte("stock", requestedQty)
    );

    Bson update = Updates.combine(
            Updates.inc("stock", -requestedQty),
            Updates.inc("version", 1L)
    );

    UpdateResult result = products.updateOne(
            filter,
            update
    );

    if (!result.wasAcknowledged()) {
        throw new IllegalStateException(
                "Acknowledged write required"
        );
    }

    return result.getMatchedCount() == 1;
}
~~~

Method này không cần đọc stock trước khi trừ. Nếu stock không đủ, update không match. Tuy nhiên nếu client phát lại cùng ý định như request mới khi stock vẫn đủ, có thể trừ thêm lần nữa; cần idempotency ở cấp nghiệp vụ.

### 19.3. findOneAndUpdate trả document sau cập nhật

~~~java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;

Document updated = products.findOneAndUpdate(
        Filters.and(
                Filters.eq("_id", "P-100"),
                Filters.eq("version", 7L)
        ),
        Updates.combine(
                Updates.set("status", "ACTIVE"),
                Updates.inc("version", 1L)
        ),
        new FindOneAndUpdateOptions()
                .returnDocument(ReturnDocument.AFTER)
);

if (updated == null) {
    // Không có document thỏa filter.
}
~~~

Đây là conditional write trả document trong cùng thao tác. Nó không tự bật OCC nếu filter không có expectedVersion.

### 19.4. replaceOne với snapshot cũ: một rủi ro lớn

~~~java
Document old = products.find(
        Filters.eq("_id", productId)
).first();

if (old != null) {
    old.put("priceCents", 260000L);
    products.replaceOne(
            Filters.eq("_id", productId),
            old
    );
}
~~~

**replaceOne** có thể thay cả document từ snapshot cũ, ghi đè những field bị worker khác sửa giữa find và replace. Nếu buộc phải replace, cần điều kiện version:

~~~java
long expected = old.getLong("version");

Document replacement = new Document(old);
replacement.put("priceCents", 260000L);
replacement.put("version", expected + 1L);

UpdateResult result = products.replaceOne(
        Filters.and(
                Filters.eq("_id", productId),
                Filters.eq("version", expected)
        ),
        replacement
);
~~~

Nhưng replacement toàn document còn có nguy cơ làm mất field không được mapper/DTO load. Khi chỉ sửa vài field, **$set + $inc** thường rõ phạm vi và dễ kiểm soát hơn.

### 19.5. Kiểu BSON của version

Nếu document lưu version dạng BSON Int64, Java dùng **Long/long**. Với org.bson.Document, **getLong("version")** có thể không phù hợp nếu document legacy lưu BSON Int32; cần migration/convert có kiểm tra.

Không dùng string **"7"** khi database lưu version bằng số: chuỗi và BSON number không phải một kiểu giá trị.

## 20. Spring Data MongoDB: optimistic locking qua @Version

Spring Data MongoDB hỗ trợ **@Version** trong các thao tác CRUD thích hợp, tương tự ý tưởng optimistic locking của JPA.

### 20.1. Entity mẫu

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class ProductDocument {

    @Id
    private String id;

    private String tenantId;
    private String name;
    private Long priceCents;

    @Version
    private Long version;

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Long getPriceCents() {
        return priceCents;
    }

    public void setPriceCents(Long priceCents) {
        this.priceCents = priceCents;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

Field **@Version** giúp Spring Data thêm điều kiện phiên bản khi thực hiện những thao tác lưu entity được hỗ trợ và tăng version sau khi lưu thành công.

### 20.2. Hai bản sao cùng đọc và save

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ProductDocument copyA = mongoTemplate.findOne(
        Query.query(Criteria.where("_id").is("P-100")),
        ProductDocument.class
);

ProductDocument copyB = mongoTemplate.findOne(
        Query.query(Criteria.where("_id").is("P-100")),
        ProductDocument.class
);

copyA.setName("Wireless Mouse Pro");
mongoTemplate.save(copyA);

copyB.setName("Wireless Mouse V2");
mongoTemplate.save(copyB);
~~~

Giả sử cả hai bản sao có version 7 trước khi save. Nếu copyA lưu thành công và version tăng lên 8, thao tác save copyB có thể ném **OptimisticLockingFailureException**, thay vì ghi đè dữ liệu từ version cũ.

### 20.3. Bắt và xử lý exception

~~~java
import org.springframework.dao.OptimisticLockingFailureException;

try {
    mongoTemplate.save(copyB);
} catch (OptimisticLockingFailureException ex) {
    // Map thành HTTP 409 hoặc 412 theo API contract.
    // Không âm thầm ghi đè payload cũ.
    throw ex;
}
~~~

### 20.4. Spring Data khởi tạo version ra sao?

Theo tài liệu Spring Data MongoDB, một **@Version** chưa được set khi insert có thể khởi tạo:

- **Wrapper type** như Long/Integer: **0**.
- **Primitive type** như long/int: **1**.

Đây là convention của framework, không phải luật chung bắt buộc của MongoDB server. Với collection legacy, phải thống nhất dữ liệu/version trước khi trông chờ OCC.

### 20.5. Raw template update không tự trở thành CAS snapshot

Spring Data cho biết **chỉ những CRUD operations nhất định** xử lý version theo semantics của framework. Một số template updates có thể tự tăng version nếu field version không có trong Update, **nhưng không có nghĩa mọi updateFirst/updateMulti đều tự thêm expectedVersion của entity client đã đọc vào filter**.

Ví dụ không có CAS tường minh:

~~~java
Query query = Query.query(
        Criteria.where("_id").is("P-100")
);

Update update = new Update()
        .set("name", "Another Name");

mongoTemplate.updateFirst(
        query,
        update,
        ProductDocument.class
);
~~~

Muốn dùng template update cho CAS:

~~~java
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

Query query = Query.query(
        Criteria.where("_id").is("P-100")
                .and("tenantId").is("SHOP-A")
                .and("version").is(7L)
);

Update update = new Update()
        .set("priceCents", 260000L)
        .inc("version", 1L);

UpdateResult result = mongoTemplate.updateFirst(
        query,
        update,
        ProductDocument.class
);
~~~

Vì version đã được chỉ định trong Update, Spring Data không cần tự tăng thêm theo quy tắc version-absent. Với version cụ thể của Spring Data, hãy kiểm tra tài liệu API để tránh trùng logic version.

### 20.6. Acknowledged writes và delete

Optimistic locking cần **write acknowledgement** để biết thao tác stale. Với WriteConcern.UNACKNOWLEDGED, Spring Data có thể không phát hiện conflict đúng.

Với xóa document chỉ khi không thay đổi:

~~~javascript
db.products.deleteOne({
  _id: "P-100",
  tenantId: "SHOP-A",
  version: NumberLong(7)
});
~~~

Đọc **deletedCount** để biết có document phù hợp. Trong Spring Data, **delete(entity)** có thể xét version, còn **deleteById(id)** có semantics khác và có thể bypass kiểm tra version. Phải chọn API phù hợp với nghiệp vụ.

## 21. Xung đột giả và phạm vi version

Một version dùng cho toàn document có thể gây conflict dù hai người dùng sửa hai field độc lập:

- A sửa name, version 7 → 8.
- B đọc từ version 7, chỉ định sửa stock.
- B không match dù name và stock có thể độc lập.

Đây có thể là **false conflict** theo domain. Các cách giảm:

1. Dùng update operator chỉ sửa field cần thiết thay vì replace toàn document.
2. Dùng **$inc** cho counters và filter invariant theo giá trị hiện tại.
3. Tách các vùng dữ liệu có vòng đời ghi độc lập thành documents riêng.
4. Dùng version cho một sub-aggregate nếu có quy ước rõ ràng và mọi writer tuân thủ.
5. Rebase delta lên snapshot mới khi business rule cho phép.

Không giảm xung đột giả bằng cách bỏ toàn bộ version check rồi chấp nhận lost update.

### 21.1. Version không tự validate payload

Ngay cả khi expectedVersion đúng, client vẫn có thể gửi price âm, quantity không hợp lệ hoặc status transition bị cấm.

Kết hợp:

- **Authorization** để kiểm soát ai được cập nhật.
- **Business preconditions** trong filter để kiểm soát trạng thái hiện tại.
- **Schema validation** để kiểm soát kiểu/cấu trúc.
- **Unique index** cho uniqueness.
- **Version CAS** cho snapshot freshness.
- **Transaction** khi cần phối hợp nhiều document.

## 22. Quy trình production

### Bước 1 — Định nghĩa invariant

Liệt kê những điều phải bảo đảm:

- Stock không âm.
- Không chuyển từ CANCELLED sang PACKED.
- Một request payment/reservation không bị xử lý lặp.
- Form chỉnh sửa stale không ghi đè thay đổi khác.
- Business key không được trùng.

Chọn conditional update, CAS, idempotency, unique index hoặc transaction tùy invariant.

### Bước 2 — Thống nhất schema

~~~javascript
{
  _id: "P-100",
  tenantId: "SHOP-A",
  priceCents: NumberLong(250000),
  stock: NumberInt(10),
  version: NumberLong(7),
  updatedAt: ISODate("2026-07-01T00:00:00Z")
}
~~~

Version phải có type ổn định, tồn tại trên các document cần OCC, không do client tự chọn giá trị mới. Kiểm kê cả batch jobs/migrations.

### Bước 3 — Đọc dữ liệu kèm version

Khi client mở form, API trả các field cần sửa và version trong cùng snapshot. Nếu dùng cache, xác định freshness và cách giải quyết xung đột.

### Bước 4 — Ghi với precondition trong cùng thao tác

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    version: NumberLong(7),
    status: "ACTIVE"
  },
  {
    $set: {
      priceCents: NumberLong(260000)
    },
    $inc: {
      version: NumberLong(1)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

Đưa mọi điều kiện có thể bị request khác thay đổi vào filter khi cập nhật phụ thuộc chúng.

### Bước 5 — Phân loại kết quả

**matchedCount=1:** thao tác đã match filter.

**matchedCount=0:** có thể là version conflict, precondition không thỏa, document không tồn tại hoặc nằm ngoài scope. Đọc lại có kiểm soát nếu cần phân loại, không retry payload cũ vô điều kiện.

### Bước 6 — Theo dõi metrics

| Chỉ số | Ý nghĩa |
|---|---|
| **OCC conflict rate** | Tỷ lệ stale version đã được phân loại. |
| **Precondition failures** | Stock không đủ, status sai hoặc lỗi domain. |
| **Update latency p95/p99** | Contention trên document nóng. |
| **Retry count** | Theo dõi retry storm hoặc retry sai loại lỗi. |
| **Idempotency duplicates** | Số requestId đã được xử lý trước. |
| **Write concern latency** | Chi phí xác nhận/durability. |
| **WriteConflict/timeout errors** | Tình trạng transaction, mạng và tải server. |

### Bước 7 — Kiểm thử nhiều request cạnh tranh

Những tình huống nên có trong test suite:

1. Hai client đọc version 7 và cùng ghi: chỉ một CAS thành công.
2. Version tăng cùng thay đổi, không có trạng thái nửa chừng.
3. Hai request mua 7 từ stock 10: chỉ một request trừ được.
4. Retry cùng business requestId không double charge/double decrement.
5. Không thể sửa document thuộc tenant khác dù biết ID và version.
6. Batch job/migration không bypass version.
7. Spring Data @Version phát hiện stale save với acknowledged writes.

## 23. Index cho conditional update

Với thao tác:

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    version: NumberLong(7)
  },
  {
    $set: { name: "New Name" },
    $inc: { version: NumberLong(1) }
  }
);
~~~

MongoDB thường có thể dùng **unique index mặc định trên _id** để tìm document ứng viên rồi kiểm tra tenant/version. Không cần mặc định tạo compound index **{_id:1,version:1}** cho mọi collection chỉ vì dùng OCC.

**Index giúp định vị document; CAS filter giúp quyết định có được ghi hay không.** Index version không tự ngăn lost update nếu câu lệnh ghi vẫn chỉ lọc _id.

Nếu ứng dụng thường xuyên cập nhật theo nhiều field mà không có _id, ví dụ:

~~~javascript
db.jobs.updateOne(
  {
    tenantId: "SHOP-A",
    queue: "EMAIL",
    status: "PENDING"
  },
  {
    $set: {
      status: "RUNNING"
    }
  }
);
~~~

thì có thể cần index phù hợp với query theo tenant/queue/status. Nhưng nếu nhiều job cùng match, **updateOne không tự chọn theo FIFO**. Nếu muốn nhận job theo độ ưu tiên hoặc thời điểm tạo, cân nhắc **findOneAndUpdate** với sort rõ ràng và index phù hợp.

## 24. Những lỗi thường gặp

### 24.1. Chỉ lọc theo _id rồi replace snapshot cũ

~~~javascript
db.products.replaceOne(
  { _id: "P-100" },
  staleDocumentFromClient
);
~~~

Có thể ghi đè các field được request khác sửa. Dùng expectedVersion CAS và chỉ cập nhật những field được phép.

### 24.2. Kiểm tra stock bằng find rồi trừ bằng update

Điều kiện ở client có thể lỗi thời giữa hai lệnh. Đưa **stock >= requestedQty** vào filter của update.

### 24.3. Tăng version sau lệnh ghi chính

Ứng dụng có thể crash giữa hai write. Dùng **$set + $inc version** trong một update.

### 24.4. Một service hoặc migration bypass version

OCC toàn document không còn phản ánh mọi thay đổi. Cần chuẩn hóa write paths và có kế hoạch migration.

### 24.5. Tự retry payload stale lên version mới

Làm mất mục đích của OCC. Đọc lại, resolve conflict theo business rule hoặc báo người dùng.

### 24.6. Bật upsert:true cho CAS update

~~~javascript
// Không nên làm:
db.products.updateOne(
  {
    _id: "P-100",
    version: NumberLong(7)
  },
  {
    $set: { name: "New" },
    $inc: { version: 1 }
  },
  { upsert: true }
);
~~~

Nếu document có version mới hơn, filter không match. **upsert:true có thể khiến MongoDB cố insert một document mới**, gây duplicate key hoặc tạo dữ liệu không mong muốn tùy filter/constraints. Với CAS update document hiện có, **không bật upsert**; phân biệt rõ create và update.

### 24.7. Dùng modifiedCount=0 làm bằng chứng conflict

Với $set giá trị bằng đúng giá trị cũ, document có thể match nhưng không modified. Cần hiểu sự khác nhau giữa matchedCount và modifiedCount.

### 24.8. Dùng updatedAt không bảo đảm độ phân giải

Timestamp có thể bị trùng do độ phân giải mili giây hoặc conversion sai type/precision. Version số nguyên tăng rõ ràng thường phù hợp hơn cho OCC.

### 24.9. Nghĩ @Version bảo vệ mọi raw driver update

@Version chỉ giúp các CRUD APIs được framework hỗ trợ. Custom driver updates, scripts và migrations vẫn phải tuân thủ version strategy.

### 24.10. Dùng unacknowledged writes

Không có kết quả matchedCount đáng tin cậy để phát hiện stale version.

### 24.11. Giữ transaction mở khi người dùng nhập form

Transaction dài tiêu tốn tài nguyên và dễ bị timeout/conflict. Dùng snapshot + conditional write lúc submit.

### 24.12. Nhầm unique index với CAS

Unique index chống khóa trùng giữa documents; version CAS ngăn stale updates trên document hiện có. Hai kỹ thuật không thay thế nhau.

### 24.13. Bỏ qua tenant và authorization

Version không phải một credential. API phải xác thực và kiểm tra quyền của người gọi, không chỉ dựa vào _id/version mà client gửi.

### 24.14. Không kiểm soát input quantity

requestedQty âm hoặc quá lớn có thể gây sai tính toán hoặc vượt miền kiểu BSON. Validate đầu vào trước khi tạo filter/update.

### 24.15. Dựa vào một lần retry để suy ra request đầu tiên đã thành công

Khi retry CAS với expectedVersion cũ cho matchedCount=0, có thể request đầu tiên đã thành công, nhưng cũng có thể request khác đã thắng. Muốn phân biệt cần requestId/idempotency record nhất quán.

## 25. Bài thực hành

### Bài 1 — Mô phỏng lost update

Từ P-100, hai client cùng đọc priceCents=250000 và lần lượt $set hai giá mới khác nhau chỉ theo _id. Dự đoán giá nếu B ghi sau A. Vì sao MongoDB vẫn bảo đảm atomicity?

### Bài 2 — CAS theo giá trị cũ

Viết hai update cùng filter **priceCents:250000**, A muốn 260000, B muốn 240000. Sau khi một request ghi thành công, request còn lại có matchedCount bao nhiêu?

### Bài 3 — ABA problem

Giả sử giá thay đổi theo chuỗi **250000 → 260000 → 250000**. Vì sao so sánh chỉ giá cũ có thể không phát hiện thay đổi, còn so sánh version 7 với version 9 thì có?

### Bài 4 — CAS theo version

Viết update P-100 kiểm tra version=7, thay name và tăng version trong cùng thao tác. Chạy lại với expectedVersion=7 thì điều gì xảy ra?

### Bài 5 — Transition trạng thái

Từ P-200 DRAFT, chỉ chuyển ACTIVE nếu status vẫn DRAFT. Sau khi đã ACTIVE, cùng lệnh còn match không?

### Bài 6 — Tồn kho không âm

Hai request muốn mua mỗi request 7 sản phẩm từ stock=10. Viết một updateOne dùng stock >= requestedQty và $inc âm. Giải thích vì sao chỉ một request có thể thành công nếu cả hai được áp dụng đúng một lần.

### Bài 7 — Validate request

Nếu requestedQty = -5 hoặc 0, reserveStock phải làm gì? Giải thích tại sao kiểm soát concurrency không thay thế validation.

### Bài 8 — Phân loại matchedCount=0

Một update có filter:

~~~javascript
{
  _id: "P-100",
  tenantId: "SHOP-A",
  version: NumberLong(7),
  status: "ACTIVE"
}
~~~

trả matchedCount=0. Nêu ít nhất bốn nguyên nhân và cách phân loại an toàn không tiết lộ dữ liệu tenant khác.

### Bài 9 — Cập nhật array có version

Với ORD-100, chỉ đổi line L1 từ NEW sang PACKED khi version=3. Dùng **$elemMatch** ở filter chính, **$[line]** và **arrayFilters** ở update, tăng version thành 4. Vì sao cần cả hai tầng điều kiện?

### Bài 10 — Java Sync Driver

Viết method updateName nhận productId, tenantId, expectedVersion, newName; validate name, dùng Filters.and, Updates.combine và UpdateResult. Phân biệt conflict và validation error.

### Bài 11 — Spring Data @Version

Hai entity cùng đọc version 7; copyA save thành công rồi copyB save. Dự đoán exception của copyB. Vì sao write concern phải được acknowledged?

### Bài 12 — Retry

Request REQ-001 đã trừ stock bằng $inc nhưng response bị mất. Client gửi lại như một request mới khi stock vẫn đủ. Có thể xảy ra điều gì? Thiết kế idempotency key và cách ghi dấu nhất quán.

### Bài 13 — HTTP If-Match

API trả ETag **"v7"**, client gửi If-Match **"v7"**, nhưng MongoDB đang version=8. Đề xuất response **412** hoặc **409** theo API contract. Vì sao việc so sánh ETag ở controller mà không đặt version vào filter vẫn chưa an toàn?

### Bài 14 — Multi-document transaction

Một nghiệp vụ cần trừ stock ở products, insert orders và ghi inventory_movements. Vì sao updateOne trên product không đảm bảo cả ba thay đổi? Khi nào nên dùng transaction?

### Bài 15 — Migration và OCC

Một batch job update trực tiếp theo _id mà không tăng version. Mô tả cách UI có thể bỏ sót thay đổi. Đề xuất quy ước version cho mọi write paths.

## 26. Câu hỏi ôn tập

1. Lost update là gì? Nó có mâu thuẫn với atomicity cấp document của MongoDB không?
2. Vì sao filter chỉ theo _id thường không phát hiện stale snapshot?
3. Conditional update khác với findOne rồi kiểm tra trong Java như thế nào?
4. CAS theo field cũ có giới hạn gì?
5. ABA problem là gì?
6. Một version CAS update cần những điều kiện và update operators nào?
7. Vì sao version cần tăng trong cùng lệnh với field nghiệp vụ?
8. matchedCount=0 có luôn là version conflict không?
9. modifiedCount=0 có luôn là update thất bại không?
10. Vì sao $inc phù hợp hơn read-modify-write cho counter?
11. Điều kiện nào giúp phép trừ stock không làm stock âm?
12. findOneAndUpdate có lợi gì so với updateOne khi cần document mới?
13. Vì sao upsert:true không phù hợp cho stale-version CAS?
14. Tại sao cần idempotency key cho request có thể được gửi lặp?
15. Vì sao updatedAt không luôn phù hợp làm version token?
16. $elemMatch có vai trò gì trong conditional update trên embedded array?
17. updateMany có nguyên tử trên toàn bộ nhiều document không?
18. @Version trong Spring Data giúp phát hiện conflict thế nào?
19. Raw updateFirst có luôn tự kiểm tra expectedVersion không?
20. Write concern ảnh hưởng phát hiện optimistic locking thế nào?
21. Unique index giải quyết race nào mà version CAS không giải quyết?
22. Khi nào transaction thích hợp hơn một updateOne?

## 27. Tổng kết

Trong MongoDB, **mỗi write trên một document là nguyên tử**, nhưng ứng dụng vẫn có thể mất thay đổi nếu ghi dựa trên dữ liệu cũ mà không kiểm tra điều kiện ở thời điểm ghi.

Ba kỹ thuật trọng tâm:

~~~text
1. Conditional state transition
   WHERE status = expectedStatus
   SET status = newStatus

2. Atomic arithmetic with invariant
   WHERE stock >= qty
   INC stock BY -qty

3. Optimistic locking
   WHERE version = expectedVersion
   SET payload mới
   INC version BY 1
~~~

Mẫu CAS tổng quát:

~~~javascript
db.collection.updateOne(
  {
    _id: documentId,
    tenantId: authorizedTenantId,
    version: expectedVersion
    // Các business preconditions cần thiết.
  },
  {
    $set: {
      // Chỉ những field được phép sửa.
    },
    $inc: {
      version: 1
    }
  }
);
~~~

Điểm cần nhớ:

1. **Filter là nơi biểu diễn điều kiện phải còn đúng ngay khi ghi.**
2. **Dữ liệu và version phải đổi trong cùng update nguyên tử.**
3. **Version chỉ đáng tin nếu mọi write paths có liên quan đều tăng version.**
4. **matchedCount=0 cần được phân loại**, không tự động retry payload cũ.
5. **Retryable writes khác application replay**; nghiệp vụ không-idempotent cần cơ chế chống ghi lặp.
6. **Spring Data @Version** hỗ trợ các CRUD APIs phù hợp nhưng không thay thế kiểm tra raw updates và write concern.
7. **Atomicity một document không phải transaction nhiều document.**
8. **Authorization, validation, unique constraints, metrics** phải được thiết kế cùng OCC để đạt correctness trong production.

### Tài liệu chính thức

- [MongoDB: Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — atomicity cấp document và conditional updates.
- [db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — filter/update/options và UpdateResult.
- [db.collection.findOneAndUpdate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/) — conditional update có document trả về.
- [$inc Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/inc/) — phép tăng/giảm nguyên tử.
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — phối hợp thay đổi nhiều document.
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retry logical writes.
- [MongoDB Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness.
- [MongoDB Java Sync Driver: Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/) — Filters, Updates, UpdateResult.
- [Spring Data MongoDB: Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — @Version, save, optimistic locking exception và write concern.

Khi viết một thao tác cập nhật, đừng chỉ hỏi **“muốn ghi giá trị gì?”** mà còn phải hỏi **“điều gì phải vẫn đúng tại thời điểm ghi?”**. Đặt câu trả lời vào filter của MongoDB giúp tránh ghi đè snapshot cũ, bảo vệ bất biến nghiệp vụ và xử lý các request cạnh tranh một cách có thể dự đoán.



