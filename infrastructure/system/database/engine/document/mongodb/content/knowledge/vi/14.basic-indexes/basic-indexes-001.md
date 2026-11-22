# Index hỗ trợ truy vấn như thế nào và chi phí duy trì khi ghi

## 1. Index giải quyết vấn đề gì?

Trong MongoDB, một collection có thể chứa từ vài trăm đến hàng triệu document. Một request như “tìm đơn hàng theo mã” hoặc “lấy 20 đơn mới nhất của khách hàng” thường chỉ cần một phần rất nhỏ dữ liệu. Nếu mỗi lần truy vấn đều phải kiểm tra toàn bộ document, thời gian xử lý và số thao tác đọc có thể tăng nhanh khi collection lớn dần.

**Index** cung cấp một cấu trúc dữ liệu riêng để tìm các document theo giá trị khóa đã được tổ chức trước. MongoDB có thể dùng index để:

1. **Lọc nhanh:** tìm khóa đúng bằng giá trị hoặc thuộc một khoảng thay vì quét rộng.
2. **Sắp xếp:** đọc các khóa theo thứ tự cần trả, có thể tránh bước sort riêng.
3. **Phục vụ kết quả ngay từ index:** trong một số trường hợp không cần đọc document gốc.
4. **Thực thi ràng buộc:** unique index ngăn các giá trị khóa trùng theo quy tắc đã chọn.

Đổi lại, khi **insert**, **update** hoặc **delete** document, MongoDB có thể phải cập nhật những index liên quan. Index cũng chiếm dung lượng đĩa và sử dụng bộ nhớ đệm khi được truy cập.

> **Không phải “nhiều index hơn = nhanh hơn”. Index làm tăng tốc những đường truy vấn phù hợp, nhưng phải trả chi phí lưu trữ và duy trì khi dữ liệu thay đổi.**

| Nhu cầu | Index có thể giúp gì? | Chi phí đánh đổi |
| --- | --- | --- |
| Tra cứu bằng khóa nghiệp vụ | Định vị một vùng khóa nhỏ. | Duy trì index khi thêm/xóa hoặc đổi khóa. |
| Lọc theo thời gian, giá | Quét khoảng khóa tương ứng. | Thêm dung lượng và công việc khi ghi. |
| Lấy N kết quả mới nhất | Dùng thứ tự khóa thay vì sort tập lớn. | Compound index có thể rộng hơn. |
| Trả ít trường dữ liệu | Có thể tránh đọc document gốc. | Index chứa nhiều trường hơn. |
| Kiểm tra tính duy nhất | Ngăn trùng khóa ngay cả khi request đồng thời. | Thêm chi phí kiểm tra và nguy cơ lỗi E11000 khi ghi. |

Bài này tập trung vào các **index cơ bản** phục vụ truy vấn BSON document và lý do chúng có thể ảnh hưởng tới hiệu năng ghi của hệ thống.

---

## 2. Cấu trúc index dưới góc nhìn ứng dụng

Một index thông thường của MongoDB có thể được hình dung là tập **khóa được tổ chức theo thứ tự** cùng thông tin để xác định document tương ứng. Các index thông thường sử dụng cấu trúc dạng B-tree/B-tree-like theo storage engine và kiểu index. Không cần ghi nhớ sơ đồ trang vật lý để hiểu hành vi truy vấn: điều cốt lõi là engine có thể **tìm khóa** và **duyệt vùng khóa liên tiếp**.

Ví dụ:

```javascript
db.customers.insertMany([
  { _id: 1, email: "an@example.com", name: "An" },
  { _id: 2, email: "chi@example.com", name: "Chi" },
  { _id: 3, email: "binh@example.com", name: "Bình" }
]);

db.customers.createIndex({ email: 1 });
```

Có thể tưởng tượng index tổ chức các entry như sau:

```text
Index email (mô hình khái niệm)
───────────────────────────────────────────
"an@example.com"   -> document _id: 1
"binh@example.com" -> document _id: 3
"chi@example.com"  -> document _id: 2
───────────────────────────────────────────
```

Đây chỉ là **minh họa logic**, không phải định dạng byte thực tế trong WiredTiger. Truy vấn:

```javascript
db.customers.findOne({ email: "binh@example.com" });
```

có thể tìm vùng khóa tương ứng thay vì lần lượt thử mọi document.

### 2.1. Ý nghĩa của `1` và `-1`

```javascript
db.customers.createIndex({ email: 1 });   // tăng dần
db.orders.createIndex({ createdAt: -1 });  // giảm dần
```

`1` và `-1` biểu diễn hướng tổ chức khóa. Với index đơn trường, MongoDB thường có thể quét theo cả hai hướng; hướng được chọn trở nên quan trọng hơn khi **nhiều trường trong một compound index** cùng phục vụ filter và sort.

### 2.2. Index không chứa mọi trường của document

Index `{ email: 1 }` không mặc định lưu sẵn `name`, `address`, `lastLogin` hay toàn bộ document. Nếu truy vấn cần trả các trường đó, sau khi duyệt index MongoDB có thể phải **FETCH** document gốc.

Vì vậy cần phân biệt:

- **Index scan:** tìm key và định vị document.
- **Document fetch:** đọc document để lấy field không có trong index.
- **Covered query:** toàn bộ field query cần đã được index phục vụ, nên có thể không phải fetch document.

### 2.3. Index mặc định trên `_id`

MongoDB tạo index duy nhất trên `_id` cho collection thông thường. Vì vậy:

```javascript
db.customers.findOne({ _id: 2 });
```

thường đã có đường tìm kiếm phù hợp. Không nên tạo index trùng chức năng chỉ vì thấy `_id` xuất hiện trong câu truy vấn.

---

## 3. Collection scan và index scan khác nhau thế nào?

Giả sử collection `orders` có một triệu document và cần tra cứu mã:

```javascript
db.orders.findOne({
  orderCode: "ORD-1001"
});
```

Khi không có index phù hợp, query engine có thể thực hiện **COLLSCAN**: lần lượt kiểm tra các document cho đến khi tìm đủ kết quả hoặc hết tập cần xét.

```text
Document 1    không khớp
Document 2    không khớp
Document 3    không khớp
...
Document N    khớp
```

`findOne()` không nhất thiết quét hết collection nếu kết quả được gặp sớm. Tuy nhiên, điều kiện tìm một mã **không tồn tại** hoặc mã ở rất muộn có thể khiến engine phải duyệt rất nhiều document.

Tạo index:

```javascript
db.orders.createIndex(
  { orderCode: 1 },
  { name: "idx_order_code" }
);
```

Nếu query planner chọn index, MongoDB có thể định vị trực tiếp vùng khóa `orderCode` phù hợp, rồi fetch một hoặc ít document tương ứng.

```text
orderCode = "ORD-1001"
          |
          v
     Tra cứu index
          |
          v
     Index entry phù hợp
          |
          v
     Document tương ứng (nếu cần)
```

**Có index không bảo đảm MongoDB sẽ dùng index đó.** Planner chọn đường thực thi dựa trên các yếu tố như tính chọn lọc của filter, số document cần đọc và chi phí ước lượng. Với collection rất nhỏ, quét collection có thể nhanh hơn. Với query trả gần như toàn bộ collection, dùng index rồi fetch từng document cũng có thể kém hiệu quả hơn.

---

## 4. Dữ liệu mẫu cho các ví dụ

Giả sử collection `orders` ban đầu chưa có các ID trong ví dụ:

```javascript
db.orders.insertMany([
  {
    _id: "O1001",
    orderCode: "ORD-1001",
    customerId: "C01",
    status: "PAID",
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    totalMinor: NumberLong("520000"),
    items: [
      { sku: "P10", quantity: 2 },
      { sku: "P11", quantity: 1 }
    ]
  },
  {
    _id: "O1002",
    orderCode: "ORD-1002",
    customerId: "C01",
    status: "SHIPPED",
    createdAt: ISODate("2026-11-02T09:30:00Z"),
    totalMinor: NumberLong("190000"),
    items: [{ sku: "P20", quantity: 1 }]
  },
  {
    _id: "O1003",
    orderCode: "ORD-1003",
    customerId: "C02",
    status: "PAID",
    createdAt: ISODate("2026-11-03T11:00:00Z"),
    totalMinor: NumberLong("720000"),
    items: [{ sku: "P30", quantity: 3 }]
  },
  {
    _id: "O1004",
    orderCode: "ORD-1004",
    customerId: "C01",
    status: "PAID",
    createdAt: ISODate("2026-11-04T14:10:00Z"),
    totalMinor: NumberLong("870000"),
    items: [{ sku: "P40", quantity: 1 }]
  }
]);
```

Bốn document này minh họa cú pháp và ý nghĩa dữ liệu. Chúng **không đủ để đo hiệu năng**: planner có thể chọn COLLSCAN trên tập quá nhỏ mà hoàn toàn hợp lý.

---

## 5. Quan sát kế hoạch thực thi bằng `explain()`

Để biết MongoDB thực sự dùng index nào, xem:

```javascript
db.orders.find({
  customerId: "C01"
}).explain("executionStats");
```

Các thông tin thường có trong kết quả:

| Trường / stage | Ý nghĩa |
| --- | --- |
| `winningPlan` | Kế hoạch được query planner chọn. |
| `COLLSCAN` | Quét các document trong collection. |
| `IXSCAN` | Duyệt index entries. |
| `FETCH` | Lấy document sau khi xác định key qua index. |
| `SORT` | Sắp xếp kết quả bằng bước riêng. |
| `nReturned` | Số document được trả. |
| `totalKeysExamined` | Số index entry được kiểm tra. |
| `totalDocsExamined` | Số document được kiểm tra. |
| `executionTimeMillis` | Thời gian thực thi trong ngữ cảnh explain. |

Tên và vị trí của stage có thể khác theo phiên bản và query execution engine. Khi xây dashboard, cần dựa trên response của phiên bản đang chạy thay vì giả định một cây JSON cố định.

Tạo index rồi quan sát lại:

```javascript
db.orders.createIndex({ customerId: 1 });

db.orders.find({
  customerId: "C01"
}).explain("executionStats");
```

Nếu planner chọn index, có thể xuất hiện `IXSCAN` và sau đó `FETCH`, vì lệnh `find()` đang trả document đầy đủ.

### 5.1. Đọc số liệu examined

Các con số dưới đây chỉ là **ví dụ giả định**, không phải benchmark:

| Trường hợp | `nReturned` | `totalKeysExamined` | `totalDocsExamined` | Diễn giải |
| --- | ---: | ---: | ---: | --- |
| Equality dùng index chọn lọc | 20 | 20 | 20 | Ít key và document cần đọc. |
| Index chưa phù hợp | 20 | 100.000 | 80.000 | Quét nhiều key và lọc nhiều document. |
| Covered query | 20 | 20 | 0 | Có thể lấy kết quả từ index. |
| Collection scan | 20 | 0 | 1.000.000 | Đọc rất nhiều document để trả ít kết quả. |

Nếu `totalDocsExamined` rất lớn so với `nReturned`, cần điều tra query/index. Nhưng không nên áp dụng cứng tỷ lệ `docsExamined/nReturned` cho mọi trường hợp: aggregation tính tổng có thể phải đọc rất nhiều document; khi `nReturned = 0` phép chia không xác định. Cần xem cả `keysExamined`, CPU, I/O, sort và độ trễ ứng dụng.

### 5.2. Truy vấn nhanh trên máy thử nghiệm chưa chứng minh index tốt

Với cache nóng và dữ liệu nhỏ, kết quả `executionTimeMillis` có thể quá thấp để phân biệt phương án. Cần đánh giá trên dữ liệu có kích thước, phân phối key và mức concurrency gần workload thật.

---

## 6. Index hỗ trợ truy vấn khoảng

Index được sắp thứ tự theo khóa nên thường hữu ích cho truy vấn khoảng thời gian và khoảng giá:

```javascript
db.orders.createIndex({ createdAt: 1 });

db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
});
```

Engine có thể quét vùng khóa tương ứng:

```text
... Oct 30 | Oct 31 | Nov 01 .... Nov 30 | Dec 01 ...
                    ^              ^
                    |--- range -----|
```

Khi điều kiện chỉ khớp 0,1% document, index có thể rất hữu ích. Khi điều kiện khớp 99% document, việc quét index và fetch gần như mọi document có thể không tốt hơn quét collection.

### 6.1. Cách viết filter ảnh hưởng khả năng dùng index

Ví dụ, điều kiện biến đổi trực tiếp field ngày:

```javascript
db.orders.find({
  $expr: {
    $eq: [
      { $year: "$createdAt" },
      2026
    ]
  }
});
```

không nhất thiết tận dụng được index thông thường trên `createdAt` giống filter bằng khoảng trực tiếp. Nếu yêu cầu là năm 2026 theo UTC:

```javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-01-01T00:00:00Z"),
    $lt: ISODate("2027-01-01T00:00:00Z")
  }
});
```

thường là cách diễn đạt điều kiện sargable hơn. Với lịch nghiệp vụ theo múi giờ khác UTC, cần chuyển đúng ranh giới ngày/giờ.

---

## 7. Index hỗ trợ sắp xếp và `limit`

Để lấy 20 đơn hàng mới nhất:

```javascript
db.orders.find({})
  .sort({ createdAt: -1 })
  .limit(20);
```

Nếu không có index phù hợp, MongoDB có thể cần đọc nhiều document rồi duy trì thứ tự để xác định 20 document đầu. `limit(20)` không tự đảm bảo chỉ đọc 20 document.

Index:

```javascript
db.orders.createIndex({ createdAt: -1 });
```

có thể cho phép engine duyệt theo `createdAt` giảm dần rồi dừng sau khi lấy đủ kết quả.

Đặc biệt, với endpoint lịch sử đơn của một khách:

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 }).limit(20);
```

index ghép sau là ứng viên tự nhiên:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1
});
```

Các đơn của một khách nằm trong vùng khóa theo `customerId`; trong vùng đó `createdAt` có thứ tự giảm dần. Nếu planner chọn index này, có thể tránh bước `SORT` riêng.

Index cũng có thể cung cấp thứ tự cho một số aggregation. Tuy nhiên, sau các stage biến đổi như `$group`, `$unwind` hoặc `$lookup`, khả năng dùng index cho `$sort` phụ thuộc pipeline và execution plan, không chỉ dựa vào tên field.

---

## 8. Compound index: nhiều trường trong một index

Index gồm nhiều field:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
```

khóa index được tổ chức có thứ tự theo các thành phần. Hình dung:

```text
(customerId, status, createdAt)
("C01", "PAID",    2026-11-04)
("C01", "PAID",    2026-11-01)
("C01", "SHIPPED", 2026-11-02)
("C02", "PAID",    2026-11-03)
```

Index này là ứng viên phù hợp cho:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
```

### 8.1. Quy tắc tiền tố trái

Với `{ customerId: 1, status: 1, createdAt: -1 }`:

- Truy vấn theo `customerId` có thể khai thác tiền tố đầu.
- Truy vấn theo `customerId` và `status` có thể khai thác hai trường đầu.
- Truy vấn theo hai điều kiện trên rồi sort `createdAt` có thể khai thác thứ tự trường thứ ba.
- Truy vấn **chỉ** theo `status` không có điều kiện `customerId` thường **không khai thác tốt** index này như một index bắt đầu bằng `status`.

MongoDB có thể cân nhắc những phương án quét index khác nhau; không nên khẳng định index không bao giờ được dùng khi thiếu tiền tố. Điểm quan trọng là thứ tự field ảnh hưởng hiệu quả truy vấn.

### 8.2. Nguyên tắc ESR: Equality, Sort, Range

Một hướng dẫn thường dùng khi sắp thứ tự field trong compound index:

1. **E — Equality:** field so sánh bằng.
2. **S — Sort:** field cần sắp xếp.
3. **R — Range:** field với điều kiện khoảng.

Ví dụ:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID",
  totalMinor: { $gte: NumberLong("300000") }
}).sort({ createdAt: -1 }).limit(20);
```

Index ứng viên theo ESR:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1,
  totalMinor: 1
});
```

**ESR không phải quy tắc tối ưu tuyệt đối.** Nếu range trên `totalMinor` rất chọn lọc, thứ tự Equality–Range–Sort có thể giảm số key phải quét, dù có thể phát sinh sort. Cần thử trên dữ liệu thật với `explain`, không tạo index chỉ dựa vào chữ viết tắt.

### 8.3. Index quá rộng không tự tốt

Thêm nhiều field vào compound index làm key dài hơn và có thể làm index lớn hơn. Những query không ràng buộc trường đầu hoặc không cần các field sau có thể ít hưởng lợi. Một index chứa tám field không mặc định tốt hơn index hai field.

---

## 9. Covered query: không cần đọc document gốc

Với index:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
});
```

truy vấn:

```javascript
db.orders.find(
  { customerId: "C01", status: "PAID" },
  {
    _id: 0,
    customerId: 1,
    status: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 });
```

có thể được **cover** nếu các điều kiện khác cũng phù hợp. Khi đó engine có thể trả dữ liệu từ index mà không FETCH document gốc; `totalDocsExamined` có thể bằng 0.

### 9.1. Tại sao dùng `_id: 0`?

Projection MongoDB thường trả `_id` mặc định. Nếu index đang dùng **không chứa `_id`**, việc trả `_id` có thể buộc fetch document. Vì vậy, khi muốn kiểm tra covered query, phải xem **toàn bộ field được trả**, kể cả `_id`.

Nếu yêu cầu thêm `totalMinor` mà index không có field này:

```javascript
db.orders.find(
  { customerId: "C01", status: "PAID" },
  {
    _id: 0,
    createdAt: 1,
    totalMinor: 1
  }
);
```

MongoDB có thể phải fetch document. **Projection ít field không đồng nghĩa query được cover**.

### 9.2. Không mở rộng index vô hạn để được cover

Thêm nhiều field vào index có thể giảm FETCH cho một endpoint nhưng làm index nặng hơn và tăng chi phí ghi. Phải so sánh lợi ích đọc và chi phí duy trì index thực tế.

---

## 10. Độ chọn lọc (*selectivity*) quyết định lợi ích

Một filter có độ chọn lọc cao trả về rất ít document trong tổng collection. Filter kém chọn lọc khớp phần lớn document.

| Field | Phân phối giả định | Khả năng hưởng lợi |
| --- | --- | --- |
| `orderCode` | Mỗi đơn một mã gần như duy nhất. | Equality index thường rất hữu ích. |
| `customerId` | Một khách có ít đơn so với tổng đơn. | Index hữu ích cho lịch sử khách. |
| `status` | 95% đơn là `COMPLETED`. | Query status này có thể vẫn đọc gần toàn collection. |
| `isActive` | 99,9% user là `true`. | Query `true` có thể ít lợi ích từ index đơn. |
| `createdAt` | Trải dài nhiều năm. | Khoảng thời gian hẹp có thể hưởng lợi. |

Không phải field boolean hoặc status luôn không đáng index. Nếu một trạng thái hiếm, chẳng hạn chỉ 0,1% document có `FAILED`, index có thể phục vụ tốt màn hình xử lý lỗi. **Phân phối dữ liệu và điều kiện query quan trọng hơn kiểu field đơn lẻ.**

Một query trả về hàng trăm nghìn document cũng vẫn tốn chi phí truyền mạng, BSON decoding và xử lý ứng dụng. Index không thay thế phân trang, projection hoặc thiết kế API đúng lượng dữ liệu cần trả.

---

## 11. Multikey index: index trên mảng

Ví dụ sản phẩm:

```javascript
{
  _id: "P100",
  name: "Laptop",
  tags: ["sale", "electronics", "featured"]
}
```

Khi tạo:

```javascript
db.products.createIndex({ tags: 1 });
```

MongoDB sử dụng **multikey index** theo quy tắc thích hợp cho field mảng. Một document có thể tạo nhiều index entry từ các phần tử. Truy vấn:

```javascript
db.products.find({ tags: "electronics" });
```

có thể tìm các document chứa tag này nhờ index.

### 11.1. Mảng càng lớn, chi phí duy trì càng đáng chú ý

Một document chứa ba tag thường có chi phí index khác với document chứa vài nghìn tag. Khi thêm/xóa phần tử mảng, engine phải duy trì các index entry tương ứng. Index trên mảng tăng vô hạn có thể làm storage và write cost tăng đáng kể.

### 11.2. Mảng chứa embedded document

Ví dụ:

```javascript
{
  _id: "O2001",
  items: [
    { sku: "P1", quantity: 1 },
    { sku: "P2", quantity: 5 }
  ]
}
```

Yêu cầu “có một dòng SKU P1 với quantity ít nhất 3”:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "P1",
      quantity: { $gte: 3 }
    }
  }
});
```

Document trên **không khớp**. Dòng P1 chỉ có quantity 1, dù dòng P2 có quantity 5. Viết hai dotted path độc lập có thể ghép điều kiện từ hai phần tử khác nhau và trả kết quả sai.

Index ứng viên:

```javascript
db.orders.createIndex({
  "items.sku": 1,
  "items.quantity": 1
});
```

`$elemMatch` vừa thể hiện đúng ngữ nghĩa “cùng phần tử”, vừa có thể giúp planner kết hợp index bounds trong những trường hợp phù hợp.

Compound multikey index còn có giới hạn đối với **parallel arrays** khi những field độc lập đều là mảng. Không tạo bừa index ghép nhiều field array mà chưa kiểm tra schema và quy tắc hỗ trợ.

---

## 12. INSERT: một document có thể tạo nhiều công việc index

Giả sử collection có:

```javascript
{ _id: 1 }                        // index mặc định
{ orderCode: 1 }
{ customerId: 1, createdAt: -1 }
{ status: 1, createdAt: -1 }
{ "items.sku": 1 }
```

Khi insert:

```javascript
db.orders.insertOne({
  _id: "O9001",
  orderCode: "ORD-9001",
  customerId: "C01",
  status: "PAID",
  createdAt: new Date(),
  totalMinor: NumberLong("320000"),
  items: [
    { sku: "P10", quantity: 1 },
    { sku: "P20", quantity: 2 }
  ]
});
```

MongoDB không chỉ ghi document, mà còn phải duy trì các index liên quan.

```text
INSERT đơn hàng
     |
     +--> Ghi BSON document
     +--> Duy trì index _id
     +--> Duy trì index orderCode
     +--> Duy trì index (customerId, createdAt)
     +--> Duy trì index (status, createdAt)
     +--> Duy trì các key của index items.sku
     `--> Thực hiện cơ chế durability/replication liên quan
```

Một document có hai SKU có thể tạo nhiều entry ở multikey index.

### 12.1. Write amplification

**Write amplification** nghĩa là một thao tác nghiệp vụ có thể dẫn đến nhiều công việc lưu trữ hơn việc ghi trực tiếp phần dữ liệu mới. Index là một nguyên nhân: dữ liệu thay đổi phải được phản ánh trong nhiều cấu trúc.

Không được đơn giản hóa thành “có năm index thì đúng năm lần ghi vật lý”. WiredTiger dùng cache, các trang, journal, checkpoint, nén và cách gom thay đổi; chi phí thực tế phụ thuộc dữ liệu, workload và hạ tầng.

### 12.2. Unique index kiểm tra xung đột

```javascript
db.orders.createIndex(
  { orderCode: 1 },
  { unique: true, name: "uk_order_code" }
);
```

Khi insert, MongoDB phải bảo đảm ràng buộc duy nhất. Nếu một mã đã tồn tại, insert có thể bị từ chối với **E11000 duplicate key**.

Unique index không chỉ tối ưu đọc mà còn bảo vệ tính đúng đắn. Khi xây index unique trên dữ liệu cũ, nếu đã có duplicate key, index build có thể thất bại; phải xử lý dữ liệu trùng theo nghiệp vụ trước.

### 12.3. Tác động tới ingest throughput

Hệ thống ghi nhiều event/giây thường chịu tác động rõ của các index không cần thiết. Nếu hầu hết query chỉ theo `deviceId` và `timestamp`, một compound index hữu ích có thể đáng giữ hơn hàng chục index trên metadata không được truy vấn. Nhưng không nên bỏ những index bắt buộc bảo vệ uniqueness.

---

## 13. UPDATE: thay đổi index key hay chỉ thay document?

Không phải mọi update đều đòi hỏi cùng một lượng công việc index.

### 13.1. Field không thuộc index

Giả sử `internalNote` không được lập index:

```javascript
db.orders.updateOne(
  { _id: "O1001" },
  { $set: { internalNote: "Kiểm tra đóng gói" } }
);
```

Khi giá trị của các index key không đổi, thông thường không cần đổi những entry index chỉ vì field này. Tuy vậy, document vẫn được cập nhật, phát sinh chi phí cache, lưu trữ và durability. Không nên gọi thao tác này “miễn phí”.

### 13.2. Field được lập index

```javascript
db.orders.updateOne(
  { _id: "O1001" },
  { $set: { status: "SHIPPED" } }
);
```

Nếu có index chứa `status`, index phải phản ánh khóa mới:

```text
Index key cũ: ("PAID", createdAt)
                 |
                 v
        Document đổi status
                 |
                 v
Index key mới: ("SHIPPED", createdAt)
```

Ở mức khái niệm, có thể cần loại entry cũ và thêm entry mới. Nếu `status` xuất hiện trong nhiều index, nhiều cấu trúc phải được duy trì.

### 13.3. Update array có multikey index

```javascript
db.products.updateOne(
  { _id: "P100" },
  { $push: { tags: "clearance" } }
);

db.products.updateOne(
  { _id: "P100" },
  { $pull: { tags: "clearance" } }
);
```

Nếu `tags` được lập multikey index, các thao tác trên có thể thêm hoặc loại index entries. Mảng cập nhật thường xuyên, lại có nhiều index, dễ làm chi phí ghi tăng.

### 13.4. Concurrency và những trang index nóng

Nhiều writer cùng thao tác các khóa gần nhau có thể gây áp lực index pages, cache và I/O. Nếu write latency tăng, phải xét tốc độ ghi, phân phối khóa, số index, storage latency, replication và contention; không mặc định “chỉ cần thêm RAM”.

---

## 14. DELETE: tìm nhanh không có nghĩa xóa miễn phí

```javascript
db.orders.deleteOne({
  _id: "O1001"
});
```

Khi một document bị xóa, MongoDB phải duy trì những index liên quan để các truy vấn sau không còn thấy entry tương ứng.

Xóa nhiều document cũ:

```javascript
db.events.deleteMany({
  createdAt: {
    $lt: ISODate("2026-01-01T00:00:00Z")
  }
});
```

Index trên `createdAt` có thể giúp **xác định** document cần xóa, nhưng sau đó engine vẫn phải xóa nội dung và cập nhật các index khác. Một thao tác delete quy mô lớn có thể gây I/O và write pressure đáng kể.

TTL index cũng phát sinh công việc xóa nền và index maintenance; TTL không khiến việc xóa dữ liệu tự nhiên không tốn tài nguyên.

---

## 15. Index và tài nguyên: đĩa, RAM, cache, I/O

### 15.1. Dung lượng lưu trữ

Một index sử dụng thêm dung lượng đĩa. Index nhiều field hoặc multikey index trên array lớn có thể đáng kể.

Có thể xem thống kê:

```javascript
db.orders.stats();
```

Tùy phiên bản và môi trường, kết quả có các thông tin như `storageSize`, `totalIndexSize`, `indexSizes`.

Không lấy kích thước index đã nén trên đĩa rồi suy ra trực tiếp lượng RAM mà WiredTiger phải giữ. Định dạng trang, nén và working set quyết định lượng bộ nhớ được sử dụng thực tế.

### 15.2. Bộ nhớ đệm và working set

Các index được truy cập thường xuyên có những trang “nóng” trong WiredTiger cache. Những trang đó cạnh tranh RAM với các trang dữ liệu document. Index ít được dùng vẫn chiếm đĩa nhưng không đồng nghĩa toàn bộ nó thường trú trong RAM.

### 15.3. Page split và chi phí nội bộ

Vì index tổ chức khóa theo thứ tự, thêm key có thể làm storage engine điều chỉnh cấu trúc trang, thực hiện hòa giải dữ liệu hoặc **page split** khi cần. Không phải mỗi insert đều tạo một split; đây là cơ chế bình thường, không phải một lỗi truy vấn.

### 15.4. Journal, checkpoint và replication

Thay đổi dữ liệu/index tham gia cơ chế durability của storage engine. Journal, checkpoint và việc ghi trang vật lý là các hoạt động liên quan nhưng không đồng nhất. Trong replica set, các node liên quan cũng phải duy trì dữ liệu và index của mình. Chi phí index không chỉ xuất hiện trên primary.

Không có công thức chính xác “nhiều gấp đôi index thì insert chậm gấp đôi”. Cần đo trên workload thật.

---

## 16. Các loại index cơ bản và đánh đổi

| Loại/tùy chọn | Hữu ích cho | Chi phí, giới hạn |
| --- | --- | --- |
| Single-field | Equality, range hoặc sort trên một field. | Tăng dung lượng, công việc khi field thay đổi. |
| Compound | Filter kết hợp sort, đôi khi covered query. | Thứ tự field quan trọng; key có thể lớn. |
| Multikey | Tìm phần tử trong array. | Một document có thể tạo nhiều entry. |
| Unique | Bảo đảm giá trị hoặc tổ hợp khóa duy nhất. | Ghi trùng có thể bị E11000; index build có thể lỗi vì dữ liệu cũ. |
| Partial | Chỉ index document thỏa filter. | Query phải phù hợp filter mới tận dụng đầy đủ. |
| Sparse | Bỏ qua một số document thiếu field theo quy tắc. | Cần hiểu null/missing, nhất là khi kết hợp unique. |
| TTL | Xóa document hết hạn qua nền. | Delete không tức thời và vẫn tạo write I/O. |
| Wildcard | Một số field động không biết trước. | Không thay thế compound index tối ưu cho query cố định. |
| Text | Tìm kiếm từ ngữ theo text index. | Ngữ nghĩa khác index equality/range, cần thiết kế riêng. |

### 16.1. Partial index giúp giảm kích thước

Giả sử 2% đơn đang ở trạng thái `OPEN`, và API vận hành thường chỉ đọc nhóm này:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    name: "idx_open_orders",
    partialFilterExpression: {
      status: "OPEN"
    }
  }
);
```

Truy vấn:

```javascript
db.orders.find({
  customerId: "C01",
  status: "OPEN"
}).sort({ createdAt: -1 });
```

có thể tận dụng index do query chỉ cần những document thuộc tập đã index.

Index này có thể nhỏ hơn index trên toàn collection. Nhưng khi trạng thái chuyển từ `OPEN` sang `PAID`, membership trong index cũng thay đổi và có chi phí ghi. Query không filter `status: "OPEN"` không thể mặc định dựa vào index này để trả đủ document.

### 16.2. TTL index có chi phí xóa

```javascript
db.sessions.createIndex(
  { expireAt: 1 },
  { expireAfterSeconds: 0 }
);
```

Với field Date phù hợp, TTL index giúp loại document hết hạn, nhưng việc xóa do tiến trình nền không có bảo đảm chính xác từng mili giây. Nếu session phải bị từ chối ngay thời điểm hết hạn, API vẫn cần kiểm tra `expireAt`.

### 16.3. Collation cho dữ liệu chuỗi

Nếu cần truy vấn không phân biệt chữ hoa/thường:

```javascript
db.users.createIndex(
  { displayName: 1 },
  {
    collation: { locale: "en", strength: 2 },
    name: "idx_display_name_ci"
  }
);

db.users.find({ displayName: "alex" }).collation({
  locale: "en",
  strength: 2
});
```

Index có collation cụ thể không mặc định phục vụ mọi query dùng collation khác. Cấu hình `locale: "en"` chỉ minh họa cú pháp; ứng dụng tiếng Việt hoặc đa ngôn ngữ phải xác định quy tắc so sánh phù hợp.

---

## 17. Không tạo index cho mọi field

Giả sử một sản phẩm:

```javascript
{
  _id: "P1",
  sku: "SKU-001",
  sellerId: "S01",
  categoryId: "LAPTOP",
  status: "ACTIVE",
  priceMinor: 15900000,
  createdAt: new Date(),
  stock: 12,
  viewCount: 5000,
  tags: ["sale", "electronics"],
  description: "..."
}
```

Một cách làm sai là lập index cho mọi trường, rồi tạo thêm compound index cho mọi tổ hợp “có thể sẽ dùng”. Hệ quả:

1. Insert phải duy trì nhiều index không liên quan tới query phổ biến.
2. Update `stock`, `viewCount`, `status` có thể cần duy trì các index tương ứng.
3. Index chiếm thêm đĩa và working set cache.
4. Index build/rebuild tạo chi phí triển khai.
5. Query planner có thêm ứng viên nhưng không bảo đảm plan tốt hơn.
6. Index nào không được dùng sẽ khó phát hiện nếu không có ownership và monitoring.

**Bắt đầu từ query, không bắt đầu từ danh sách field.**

Ví dụ các endpoint quan trọng:

| API | Filter | Sort |
| --- | --- | --- |
| Chi tiết sản phẩm | `sku = ?` | Không |
| Sản phẩm của shop | `sellerId = ?`, `status = ACTIVE` | `createdAt DESC` |
| Sản phẩm theo danh mục | `categoryId = ?`, `status = ACTIVE` | `priceMinor ASC` |

Index ứng viên:

```javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_product_sku" }
);

db.products.createIndex(
  { sellerId: 1, status: 1, createdAt: -1 },
  { name: "idx_seller_active_recent" }
);

db.products.createIndex(
  { categoryId: 1, status: 1, priceMinor: 1 },
  { name: "idx_category_status_price" }
);
```

Đây là **ứng viên cho các query đã nêu**, không phải bộ index mặc định cho mọi hệ thống bán hàng. Nếu một báo cáo tồn kho chạy mỗi đêm và quét collection là chấp nhận được, index riêng cho nó có thể không đáng làm mọi update stock chậm hơn.

---

## 18. Index chồng lấp và index dư thừa

Hai index:

```javascript
{ customerId: 1 }
{ customerId: 1, createdAt: -1 }
```

có chung tiền tố `customerId`. Compound index thứ hai có thể phục vụ nhiều query chỉ filter `customerId`; vì vậy index đơn đầu **có thể** dư thừa.

Tuy nhiên, không nên drop ngay vì:

- Index đơn có thể nhỏ hơn, phù hợp với query cực kỳ thường xuyên.
- Index có thể có `unique`, collation, partial filter hoặc thuộc tính đặc biệt khác.
- Một query/báo cáo định kỳ có thể sử dụng index đơn.
- Lợi ích và chi phí của từng index còn phụ thuộc query planner và dữ liệu thật.

Mục tiêu là giảm **tổng chi phí đọc, ghi và vận hành**, không chỉ giảm số lượng index cho đẹp dashboard.

---

## 19. Theo dõi index nào được sử dụng

### 19.1. Liệt kê index

```javascript
db.orders.getIndexes();
```

Kết quả cho biết key pattern, tên và các tùy chọn đã tồn tại. Đây là bước đầu trước khi đề xuất một index mới.

### 19.2. Thống kê truy cập

```javascript
db.orders.aggregate([
  { $indexStats: {} }
]);
```

`$indexStats` giúp quan sát hoạt động sử dụng index. Tuy nhiên, thống kê có phạm vi và thời điểm reset, và cần xét các node/chu kỳ nghiệp vụ liên quan. Một index không được dùng trong hai giờ **không chứng minh nó vô ích**, vì có thể phục vụ job cuối tháng hoặc thao tác khẩn cấp.

### 19.3. Slow-query log, profiler và monitoring

Các công cụ này giúp tìm query có latency cao, keys/docs examined lớn hoặc sort tốn tài nguyên. Khi bật profiling chi tiết trên production, cần cân nhắc overhead và thông tin nhạy cảm có thể xuất hiện trong log.

### 19.4. Đo trước và sau thay đổi

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

So sánh plan, keys/docs examined, sort và thời gian, nhưng nên đo cả p95/p99 ứng dụng, read/write IOPS, throughput ghi và kích thước index trong môi trường đại diện.

---

## 20. `hint()`, hidden index và quá trình loại index

`hint()` có thể dùng để **thử nghiệm** một index cụ thể:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 })
  .hint({ customerId: 1, status: 1, createdAt: -1 })
  .explain("executionStats");
```

Ví dụ này giả định index tương ứng đã tồn tại. Không nên ép plan bằng `hint()` ở mọi query production chỉ để “chắc chắn dùng index”; dữ liệu thay đổi có thể làm plan bị ép trở nên kém hơn.

**Hidden index** cho phép ẩn một index khỏi lựa chọn của query planner trong những phiên bản hỗ trợ:

```javascript
db.orders.hideIndex("idx_customer_status_recent");

// Khi cần kiểm tra lại:
// db.orders.unhideIndex("idx_customer_status_recent");
```

Tên phải là index thực tế đang có. **Ẩn không xóa index và không giảm write maintenance**: index vẫn được cập nhật khi ghi. Hidden index hữu ích để đánh giá tác động tới đường đọc trước khi quyết định drop.

Nếu drop thật:

```javascript
db.orders.dropIndex("idx_customer_status_recent");
```

các query phụ thuộc có thể chậm hơn; khôi phục index có thể phải build lại trên toàn collection. Không xóa những index bảo vệ tính duy nhất hoặc thuộc về workflow quan trọng khi chưa đánh giá ràng buộc dữ liệu và tác động.

---

## 21. Index build trên collection lớn

Tạo index mới trên collection rất lớn có thể cần đọc lượng dữ liệu đáng kể, xây các trang index và sử dụng CPU, I/O, RAM, dung lượng đĩa. Cơ chế build và mức ảnh hưởng tới đọc/ghi phụ thuộc phiên bản MongoDB và deployment.

Trước khi chạy:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1
});
```

cần xác định:

1. Số lượng document và dung lượng hiện tại.
2. Dung lượng index dự kiến và khoảng trống lưu trữ.
3. Tải đọc/ghi ở thời điểm build.
4. Tình trạng dữ liệu trùng nếu tạo unique index.
5. Cách điều phối replica set/sharded cluster.
6. Các chỉ số monitor khi build và sau build.
7. Phương án quay lại nếu query plan hoặc latency xấu đi.

Index build không phải một lệnh cấu hình không có chi phí chỉ vì cú pháp ngắn. Với unique index, việc build còn có thể thay đổi **contract ghi dữ liệu**: những insert trùng khóa trước đây thành công sẽ bắt đầu bị từ chối.

---

## 22. Phân trang: index không làm `skip` sâu miễn phí

Truy vấn:

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 }).skip(200000).limit(20);
```

có thể phải duyệt nhiều entry để bỏ qua 200.000 kết quả đầu, dù có compound index. `skip` sâu không trở thành thao tác nhảy tới vị trí cố định với chi phí bằng 0.

Một giải pháp là **keyset pagination** với thứ tự ổn định:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1,
  _id: -1
});
```

Trang đầu:

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1, _id: -1 }).limit(20);
```

Trang sau sử dụng cặp khóa cuối trang trước:

```javascript
const lastCreatedAt = ISODate("2026-11-02T09:30:00Z");
const lastId = "O1002";

db.orders.find({
  customerId: "C01",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
}).sort({ createdAt: -1, _id: -1 }).limit(20);
```

Đây là ví dụ theo `_id` string và sort descending. Phải giữ kiểu và collation nhất quán. Với nhiều điều kiện lọc, cần phân tích index và query plan tương ứng.

---

## 23. Java MongoDB Sync Driver

Trong Java có thể tạo index bằng `Indexes` và `IndexOptions`, rồi truy vấn qua `Filters` và `Sorts`:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class OrderIndexExample {

    private final MongoCollection<Document> orders;

    public OrderIndexExample(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public void createIndexes() {
        orders.createIndex(
            Indexes.ascending("orderCode"),
            new IndexOptions()
                .unique(true)
                .name("uk_order_code")
        );

        orders.createIndex(
            Indexes.compoundIndex(
                Indexes.ascending("customerId"),
                Indexes.descending("createdAt")
            ),
            new IndexOptions()
                .name("idx_customer_recent")
        );
    }

    public void printRecentOrders(String customerId) {
        orders.find(Filters.eq("customerId", customerId))
            .sort(Sorts.descending("createdAt"))
            .limit(20)
            .forEach(order -> System.out.println(order.toJson()));
    }
}
```

Không gọi `createIndexes()` ở mỗi HTTP request. Index nên được quản lý như một phần schema/migration/deployment. Nếu dữ liệu cũ có `orderCode` trùng, tạo unique index sẽ thất bại và cần xử lý nguồn dữ liệu trước.

Với Spring Data MongoDB, có thể dùng `@Indexed`, `@CompoundIndex` hoặc thao tác qua `MongoTemplate`; việc annotation có tự tạo index khi ứng dụng khởi động hay không tùy cấu hình và phiên bản. Khi vận hành, luôn kiểm tra index thực tế từ MongoDB.

**Query chậm không chắc do thiếu index.** Thời gian API còn gồm network, connection pool, BSON encoding/decoding, số lượng document và chi phí truyền response lớn. Index không thay thế phân trang và thiết kế API đúng khối lượng dữ liệu cần trả.

---

## 24. Thiết kế index theo workload đọc/ghi

| Tiêu chí | Đọc nhiều | Ghi nhiều |
| --- | --- | --- |
| Ưu tiên | Trả lời query phổ biến với p95/p99 thấp. | Duy trì throughput insert/update/delete. |
| Index thích hợp | Compound filter/sort, có thể cover query. | Tập index tối thiểu hỗ trợ query và ràng buộc cần thiết. |
| Rủi ro | Index rộng và chồng lấp, working set lớn. | Write amplification, contention, nhiều index trên field cập nhật thường xuyên. |
| Cách đo | Keys/docs examined, sort, latency đọc. | Writes/s, latency ghi, index size, cache và I/O. |

**Ví dụ đọc nhiều:** Catalog có hàng nghìn request/giây nhưng cập nhật sản phẩm ít; index theo danh mục, trạng thái, giá có thể đáng trả chi phí lưu trữ.

**Ví dụ ghi nhiều:** Event ingestion ghi hàng chục nghìn document/giây, chủ yếu truy vấn theo `deviceId` và `timestamp`; index `{ deviceId: 1, timestamp: -1 }` có thể hợp lý hơn nhiều index trên metadata hiếm khi truy vấn.

**Ví dụ hỗn hợp:** Đơn hàng cần ràng buộc mã đơn duy nhất, lịch sử theo khách và màn hình vận hành theo trạng thái; phải giữ những index phục vụ query quan trọng nhưng không tạo index mới cho mọi báo cáo hiếm dùng.

Không có quy tắc “mỗi collection nên có ba index” hoặc “index tối đa mười cái”. Phải đánh giá từ access pattern, phân phối dữ liệu và hệ thống thật.

---

## 25. Quy trình ra quyết định trước khi tạo index

1. **Ghi rõ query:** filter, sort, projection, limit, tần suất, p95/p99 yêu cầu.
2. **Xem index đã có:** `db.collection.getIndexes()`.
3. **Đo baseline:** `explain("executionStats")`, latency và I/O trong workload đại diện.
4. **Chọn index ứng viên:** equality, sort, range, prefix, selectivity, multikey và partial.
5. **Ước lượng chi phí ghi:** index mới ảnh hưởng bao nhiêu insert/update/delete, có field thường xuyên thay đổi không?
6. **Đánh giá dung lượng/cache:** index dự kiến lớn bao nhiêu, có tranh working set với dữ liệu không?
7. **Triển khai có kiểm soát:** lưu ý chi phí index build, unique constraints và replication.
8. **Đo lại:** query plan, keys/docs examined, sort, latency đọc/ghi, throughput, storage và cache.
9. **Quan sát đủ chu kỳ:** không xóa index chỉ vì ít truy cập trong một khoảng ngắn.
10. **Ghi chủ sở hữu và mục tiêu:** endpoint nào dùng index, vì sao thứ tự field như vậy, khi nào cần đánh giá lại.

Ví dụ thông tin quản trị index:

```text
Index name   : idx_customer_recent
Collection   : orders
Query        : GET /customers/{id}/orders
Filter       : customerId = ?
Sort         : createdAt DESC
Goal         : p95 nhỏ hơn ngưỡng nghiệp vụ
Trade-off    : tốn thêm đĩa và chi phí insert
Owner        : Nhóm phát triển dịch vụ đơn hàng
```

---

## 26. Bài tập vận dụng

### Bài 1 — Chọn index cho lịch sử đơn

```javascript
db.orders.find({
  customerId: "C42"
}).sort({ createdAt: -1 }).limit(50);
```

**Câu hỏi:** Index đơn `customerId`, index đơn `createdAt`, hay compound index?  
**Gợi ý:** `{ customerId: 1, createdAt: -1 }` là ứng viên tự nhiên vì lọc theo khách rồi duyệt đơn theo thời gian.

### Bài 2 — Khi index không đủ chọn lọc

98% đơn có `status = "COMPLETED"`.

```javascript
db.orders.find({ status: "COMPLETED" });
```

**Câu hỏi:** Tạo index `{ status: 1 }` có chắc mọi lần query nhanh hơn không?  
**Gợi ý:** Không; engine vẫn có thể phải đọc gần toàn collection. Hãy đo selectivity và execution plan.

### Bài 3 — Covered query

Có index `{ customerId: 1, status: 1, createdAt: -1 }`.

```javascript
// A
db.orders.find(
  { customerId: "C01", status: "PAID" },
  { _id: 0, customerId: 1, status: 1, createdAt: 1 }
);

// B
db.orders.find(
  { customerId: "C01", status: "PAID" },
  { customerId: 1, status: 1, createdAt: 1, totalMinor: 1 }
);
```

**Gợi ý:** A có khả năng được cover hơn vì dùng các field trong index và loại `_id`; B đòi `totalMinor` ngoài index.

### Bài 4 — Chi phí update

Có index chứa `status`, nhưng không chứa `internalNote`:

```javascript
// A
db.orders.updateOne(
  { _id: "O1001" },
  { $set: { internalNote: "OK" } }
);

// B
db.orders.updateOne(
  { _id: "O1001" },
  { $set: { status: "SHIPPED" } }
);
```

**Gợi ý:** B có thể cần cập nhật index key; A thường không làm thay đổi index key nhưng vẫn ghi document.

### Bài 5 — Index trên mảng lớn

Một sản phẩm có 1.000 tag, có index `{ tags: 1 }`.

**Yêu cầu:** giải thích vì sao truy vấn membership được hỗ trợ, nhưng index size và chi phí thêm/xóa tag có thể tăng. **Gợi ý:** multikey index có thể chứa nhiều entry cho một document.

### Bài 6 — Partial index

Chỉ 2% đơn có `status = "OPEN"`; endpoint vận hành thường lọc theo customerId và lấy mới nhất.

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { partialFilterExpression: { status: "OPEN" } }
);
```

**Câu hỏi:** Vì sao index này có thể nhỏ hơn index toàn collection? Vì sao query không giới hạn OPEN không thể mặc định dùng index đó để trả đủ?

### Bài 7 — Index thừa?

Collection có `{ customerId: 1 }` và `{ customerId: 1, createdAt: -1 }`.

**Gợi ý:** Có thể chồng lấp, nhưng trước khi drop cần xem query statistics, thuộc tính index, size, tần suất sử dụng và các báo cáo định kỳ.

### Bài 8 — Ghi nhiều bị chậm sau khi thêm index

Một dịch vụ ghi event có tám index, nhưng query chỉ thường xuyên dùng `deviceId + timestamp`.

**Yêu cầu:** đề xuất thứ tự điều tra: đo write latency, xem index usage, kiểm tra query hiếm, thử hidden index khi phù hợp, đo lại, chỉ drop khi chắc chắn không ảnh hưởng SLA/ràng buộc dữ liệu.

---

## 27. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Càng nhiều index database càng nhanh.” | Index chỉ giúp query phù hợp, nhưng tăng chi phí ghi và lưu trữ. |
| “Có index thì MongoDB luôn dùng nó.” | Planner có thể chọn COLLSCAN hoặc index khác. |
| “Index chỉ giúp WHERE, không giúp sort.” | Thứ tự key có thể hỗ trợ sort và limit. |
| “Thứ tự field trong compound index không quan trọng.” | Prefix, range và sort phụ thuộc thứ tự field. |
| “ESR luôn là thứ tự duy nhất đúng.” | ESR là hướng dẫn; phân phối dữ liệu có thể khiến phương án khác tốt hơn. |
| “Projection ít field là covered query.” | Các field phải được index đáp ứng; cần xem `_id` và plan. |
| “Mọi index đều chứa `_id`.” | Index mặc định `_id` không làm các index khác chứa nó. |
| “Một array chỉ tạo một index entry.” | Multikey index có thể tạo nhiều entry. |
| “Index chỉ ảnh hưởng SELECT.” | INSERT/UPDATE/DELETE phải duy trì index tương ứng. |
| “Update field không index thì không cần ghi gì.” | Document vẫn thay đổi và cần xử lý lưu trữ. |
| “DELETE không có index maintenance.” | Các index phải phản ánh document bị xóa. |
| “Index nằm trên đĩa bao nhiêu sẽ chiếm RAM đúng bấy nhiêu.” | Working set, cache và nén làm các đại lượng khác nhau. |
| “Field boolean không bao giờ nên index.” | Điều kiện chọn lọc, giá trị hiếm và partial index có thể hữu ích. |
| “Index ít dùng hôm nay nên drop ngay.” | Nó có thể phục vụ job định kỳ hoặc ràng buộc dữ liệu. |
| “Hidden index tiết kiệm write overhead.” | Hidden index vẫn được duy trì khi ghi. |
| “TTL xóa tức thì và không có chi phí.” | TTL là cơ chế nền, vẫn phát sinh delete và index updates. |
| “Có index thì API trả 100.000 document cũng nhanh.” | Network, decoding và khối lượng dữ liệu trả vẫn tốn tài nguyên. |

## 28. Tổng kết

Index giúp MongoDB tìm document bằng khóa, quét vùng dữ liệu cần thiết, tận dụng thứ tự sắp xếp và đôi khi trả kết quả ngay từ index. Lợi ích thường rõ nhất với **truy vấn chọn lọc, filter + sort phù hợp và các endpoint thường xuyên được gọi**.

Mỗi index lại là một cấu trúc cần duy trì. **Insert** tạo các entry, **update** khóa có thể thay đổi entry, **delete** loại entry; các thao tác đó tốn thêm tài nguyên bộ nhớ, lưu trữ và I/O. Unique, partial, multikey và TTL cũng có các quy tắc chi phí hoặc ràng buộc riêng.

Thiết kế index tốt không hướng tới **nhiều nhất** hoặc **ít nhất**. Nó chọn tập index **đủ** để đáp ứng truy vấn và bảo vệ dữ liệu với tổng chi phí đọc/ghi/vận hành hợp lý, được xác nhận bằng `explain()`, thống kê sử dụng và monitoring thực tế.

## 29. Tài liệu MongoDB chính thức

- [Indexes — MongoDB Manual](https://www.mongodb.com/docs/manual/indexes/): tổng quan các loại index.
- [Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): filter, sort và covered query.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/): index ghép và tiền tố.
- [Equality, Sort, Range Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/): nguyên tắc ESR.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): index trên mảng.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): index trên tập document có điều kiện.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): ràng buộc khóa duy nhất.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): execution plan và chỉ số.
- [$indexStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/): thống kê sử dụng index.
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/): đánh giá tác động khi không dùng index.
- [Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/): tạo index với driver Java.

Các chi tiết về planner, index build và cấu trúc kết quả explain có thể khác giữa các phiên bản. Khi triển khai hãy đối chiếu với phiên bản MongoDB và driver thực tế.
