# Phân biệt toán tử truy vấn, biểu thức `$expr` và biểu thức aggregation trong MongoDB

## 1. Ba khái niệm có cùng ký hiệu `$` nhưng khác vai trò

Khi học cách truy vấn document MongoDB, người mới thường gặp những đoạn mã trông rất giống nhau:

```javascript
// (A) Toán tử truy vấn trong điều kiện lọc.
db.orders.find({
  quantity: { $gte: 2 }
});

// (B) $expr cho phép dùng biểu thức aggregation làm điều kiện lọc.
db.orders.find({
  $expr: { $gte: ["$quantity", 2] }
});

// (C) Biểu thức aggregation tạo ra một giá trị tính toán.
db.orders.aggregate([
  {
    $project: {
      quantity: 1,
      hasAtLeastTwo: { $gte: ["$quantity", 2] }
    }
  }
]);
```

Ba ví dụ có thể cùng sử dụng phép so sánh “số lượng từ 2 trở lên”, nhưng **không cùng cú pháp, không cùng vị trí và không cùng vai trò**:

- **Toán tử truy vấn (query operator)** dùng để diễn tả document nào khớp bộ lọc. Chúng thường xuất hiện trong `find()`, `countDocuments()`, `updateOne()` hoặc stage `$match`.
- **`$expr` là một toán tử truy vấn đặc biệt**: cho phép đặt **biểu thức aggregation** vào ngữ cảnh bộ lọc, rồi dùng kết quả của biểu thức để quyết định document có khớp hay không.
- **Biểu thức aggregation (aggregation expression)** nhận trường, giá trị hằng hoặc giá trị của các biểu thức con để tính ra **một giá trị**. Giá trị đó có thể dùng trong `$project`, `$set`, `$group`, `$match` qua `$expr` và nhiều stage khác.

Điểm cần phân biệt thêm: **stage của aggregation pipeline** (ví dụ `$match`, `$project`, `$group`) là một bước xử lý cả luồng document, còn **biểu thức aggregation** (ví dụ `$add`, `$multiply`, `$eq`, `$cond`) tính một giá trị trong ngữ cảnh stage. Cả stage lẫn expression đều thường có tên bắt đầu bằng `$`, nhưng không thể tráo vị trí tùy ý.

```text
                Ứng dụng yêu cầu lọc document
                             |
                             v
                  Ngữ cảnh query filter
                    /                \
       Toán tử truy vấn            $expr
       field: { $gt: 5 }              |
                    \                v
                     \       Biểu thức aggregation
                      \      $gt: ["$field", 5]
                       \             /
                        v           v
                    Đúng / sai cho mỗi document
                             |
                             v
                      Tập document khớp

      aggregate([ ... ]) có các STAGE xử lý luồng tài liệu:
           $match -> $project -> $group -> $sort
                        |
                        +-- các biểu thức tính giá trị
                            $multiply / $eq / $ifNull ...
```

**Nguyên tắc tư duy:** trước khi viết một toán tử bắt đầu bằng `$`, hãy xác định bạn đang ở trong **query filter**, **aggregation expression**, hay **pipeline stage**.

## 2. Bộ dữ liệu ví dụ

Các ví dụ dùng **mongosh** và một collection thử nghiệm `orders`. Giá tiền lưu bằng BSON Decimal128 để tránh nhầm biểu diễn thập phân; `quantity` là số lượng và `minEligibleTotal` là ngưỡng để xét đơn có đủ điều kiện ưu đãi.

```javascript
db.orders.insertMany([
  {
    _id: "O1",
    customerId: "C01",
    status: "PAID",
    quantity: 3,
    unitPrice: NumberDecimal("120000"),
    discount: NumberDecimal("20000"),
    minEligibleTotal: NumberDecimal("300000"),
    tags: ["vip", "bulk"],
    createdAt: ISODate("2026-10-01T09:00:00Z")
  },
  {
    _id: "O2",
    customerId: "C02",
    status: "PAID",
    quantity: 1,
    unitPrice: NumberDecimal("250000"),
    discount: NumberDecimal("0"),
    minEligibleTotal: NumberDecimal("300000"),
    tags: [],
    createdAt: ISODate("2026-10-03T09:00:00Z")
  },
  {
    _id: "O3",
    customerId: "C03",
    status: "PENDING",
    quantity: 4,
    unitPrice: NumberDecimal("90000"),
    discount: NumberDecimal("0"),
    minEligibleTotal: NumberDecimal("300000"),
    tags: ["web"],
    createdAt: ISODate("2026-10-05T09:00:00Z")
  },
  {
    _id: "O4",
    customerId: "C01",
    status: "PAID",
    quantity: 2,
    unitPrice: NumberDecimal("120000"),
    discount: null,
    minEligibleTotal: NumberDecimal("200000"),
    tags: ["vip"],
    createdAt: ISODate("2026-10-07T09:00:00Z")
  }
]);
```

Với dữ liệu này:

| Đơn | Trạng thái | Số lượng | Đơn giá | Thành tiền trước giảm (`quantity × unitPrice`) | Ngưỡng |
|---|---|---:|---:|---:|---:|
| O1 | PAID | 3 | 120.000 | 360.000 | 300.000 |
| O2 | PAID | 1 | 250.000 | 250.000 | 300.000 |
| O3 | PENDING | 4 | 90.000 | 360.000 | 300.000 |
| O4 | PAID | 2 | 120.000 | 240.000 | 200.000 |

Trong bài này, **thành tiền trước giảm** là `quantity × unitPrice`. Nếu cần doanh thu sau giảm, phải lấy thêm trường `discount` và có quy tắc riêng cho trường null; các phép tính đó sẽ xuất hiện bên dưới.

## 3. Toán tử truy vấn: mô tả điều kiện trên trường

Một bộ lọc của `find()` thường có dạng **tên trường → điều kiện cần thỏa**:

```javascript
db.orders.find({
  status: "PAID",
  quantity: { $gte: 2 }
});
```

Truy vấn trên lấy O1 và O4: cả hai đã thanh toán và có số lượng từ 2 trở lên.

Ở ngữ cảnh này:

- `status: "PAID"` là so khớp bằng nhau viết gọn.
- `quantity: { $gte: 2 }` dùng toán tử truy vấn `$gte` đặt dưới trường `quantity`.
- Hai điều kiện ở hai khóa được kết hợp bằng logic **AND** ngầm định.
- Kết quả của `find()` là **những document phù hợp**, không phải một cột Boolean chứa kết quả `$gte`.

### 3.1. Các nhóm toán tử truy vấn thường gặp

| Nhóm | Toán tử ví dụ | Cách dùng |
|---|---|---|
| So sánh | `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin` | So sánh giá trị một trường với điều kiện |
| Logic | `$and`, `$or`, `$nor`, `$not` | Kết hợp/phủ định các điều kiện lọc |
| Trường/kiểu | `$exists`, `$type` | Kiểm tra trường hiện diện hoặc kiểu BSON phù hợp |
| Mảng | `$all`, `$elemMatch`, `$size` | Kiểm tra nội dung hoặc kích thước mảng |
| Chuỗi/biểu thức chính quy | `$regex`, `$options` | So khớp chuỗi theo mẫu |
| Biểu thức tính toán | `$expr` | Đưa aggregation expression vào bộ lọc |

Một số ví dụ:

```javascript
// O1, O2, O4
db.orders.find({ status: { $eq: "PAID" } });

// O1, O3
db.orders.find({ quantity: { $gt: 2 } });

// O1, O4
db.orders.find({ tags: "vip" });

// O2
db.orders.find({ tags: { $size: 0 } });

// O1, O4: cả hai điều kiện lọc phải đúng.
db.orders.find({
  $and: [
    { status: "PAID" },
    { quantity: { $gte: 2 } }
  ]
});
```

Toán tử truy vấn được đặt **bên trong filter document**. Với những điều kiện đơn giản, đây thường là cách diễn đạt trực tiếp, dễ đọc và dễ xét khả năng sử dụng index nhất.

### 3.2. So sánh một trường với một giá trị hằng

```javascript
db.orders.find({
  unitPrice: { $gte: NumberDecimal("120000") }
});
```

Đây là bài toán **một trường so với một hằng số**. MongoDB biết trước giá trị cần so sánh và có thể xét index trên `unitPrice` khi lập kế hoạch.

```javascript
db.orders.createIndex({ unitPrice: 1 });
```

Điều này khác căn bản với việc yêu cầu “giá của đơn này có lớn hơn **một trường khác trong chính đơn** hay không?”. Trường thứ hai chỉ được biết khi đánh giá từng document, và cú pháp truy vấn thông thường không tự chuyển chuỗi bắt đầu bằng `$` thành tham chiếu đến trường.

### 3.3. Chuỗi `"$otherField"` trong filter thông thường không mang nghĩa tham chiếu trường

Ví dụ sai về mặt ý định:

```javascript
// Không phải so sánh quantity với trường minQuantity!
db.orders.find({
  quantity: { $gt: "$minQuantity" }
});
```

Ở vị trí toán hạng của toán tử truy vấn `$gt`, `"$minQuantity"` không được diễn giải như đường dẫn trường trong aggregation expression. Nó là một giá trị String được đưa vào phép so sánh; kết quả phụ thuộc quy tắc so sánh kiểu BSON, và **không thực hiện** phép “quantity > minQuantity” như mong muốn.

Để so sánh **trường với trường**, dùng `$expr`.

## 4. `$expr`: dùng ngôn ngữ biểu thức aggregation ngay trong filter

`$expr` là một **toán tử truy vấn cấp cao**: nó nhận một biểu thức aggregation, đánh giá biểu thức đó với từng document ứng viên, rồi dùng kết quả như điều kiện lọc.

```javascript
db.orders.find({
  $expr: {
    $gt: ["$quantity", 2]
  }
});
```

Ví dụ này tìm O1 và O3, tương tự `{ quantity: { $gt: 2 } }` trên bộ dữ liệu mẫu. Nhưng bên trong `$expr`, `$gt` đã là **toán tử biểu thức aggregation**, có dạng **mảng gồm hai toán hạng**.

Hình dạng cần nhớ:

```javascript
// Toán tử truy vấn thông thường:
{ quantity: { $gt: 2 } }

// $expr kết hợp aggregation expression:
{ $expr: { $gt: ["$quantity", 2] } }
```

Trong biểu thức thứ hai:

- `"$quantity"` là **đường dẫn trường**, không phải văn bản để so sánh.
- `2` là giá trị số hằng.
- `$gt` đánh giá hai biểu thức và trả Boolean.
- `$expr` sử dụng giá trị của biểu thức trong ngữ cảnh match.

### 4.1. Khi nào thực sự cần `$expr`?

Giả sử muốn tìm những đơn có **thành tiền trước giảm lớn hơn ngưỡng lưu ngay trong mỗi đơn**:

```javascript
db.orders.find({
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

Kết quả của dữ liệu mẫu: **O1, O3 và O4**.

Diễn giải theo từng document:

1. Đọc `quantity` và `unitPrice` từ document hiện tại.
2. Tính `$multiply` để có thành tiền trước giảm.
3. Đọc `minEligibleTotal` của chính document đó.
4. So sánh hai giá trị bằng aggregation expression `$gt`.
5. Giữ lại document nếu kết quả là đúng.

Không thể biểu đạt phép tính này chỉ bằng `{ unitPrice: { $gt: SOME_CONSTANT } }`, vì ngưỡng phụ thuộc vào trường khác và thành tiền là một giá trị được tính.

### 4.2. Kết hợp query filter và `$expr`

Không phải lựa chọn “hoặc dùng tất cả query operator, hoặc dùng tất cả `$expr`”. Có thể đặt điều kiện đơn giản ngoài `$expr`, rồi chỉ dùng expression cho phần tính toán:

```javascript
db.orders.find({
  status: "PAID",
  quantity: { $gte: 2 },
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

Kết quả: **O1 và O4**. Cách viết này thường rõ ý:

- `status` và `quantity` là điều kiện trực tiếp trên trường.
- `$expr` chỉ giải quyết phép so sánh cần tính toán.
- Tất cả điều kiện cùng tham gia bộ lọc.

Khi có index phù hợp, các điều kiện query thông thường còn giúp bộ lập kế hoạch xem xét cách thu hẹp tài liệu trước khi thực hiện những phép tính đắt hơn.

### 4.3. `$expr` không bắt buộc nằm trong `aggregate()`

Một số người cho rằng “đã dùng aggregation expression thì phải gọi `aggregate()`”. Điều này không đúng: `$expr` dùng được trong các bộ lọc phù hợp như `find()` và cũng có thể xuất hiện trong bộ lọc của lệnh cập nhật/xóa document, theo cách hỗ trợ của lệnh đó.

```javascript
// Đếm những đơn có thành tiền trước giảm vượt ngưỡng.
db.orders.countDocuments({
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

Nội dung bên trong `$expr` **là ngôn ngữ biểu thức aggregation**, nhưng bên ngoài vẫn là một **bộ lọc document**.

### 4.4. Dùng toán tử trả Boolean và toán tử trả giá trị

Biểu thức aggregation như `$eq`, `$gte`, `$and`, `$or`, `$not` có thể trực tiếp tạo điều kiện Boolean. Những biểu thức như `$add`, `$multiply`, `$concat`, `$ifNull` thường tạo giá trị số/chuỗi/...; nên lồng chúng vào phép so sánh rõ nghĩa:

```javascript
db.orders.find({
  $expr: {
    $gte: [
      {
        $subtract: [
          { $multiply: ["$quantity", "$unitPrice"] },
          { $ifNull: ["$discount", NumberDecimal("0")] }
        ]
      },
      NumberDecimal("300000")
    ]
  }
});
```

Ở đây `$ifNull` thay `discount: null` hoặc trường không tồn tại bằng Decimal128 bằng 0 trước khi trừ. Câu truy vấn tìm những đơn có thành tiền sau giảm từ 300.000 trở lên; với dữ liệu mẫu, **O1** đạt điều kiện.

**Không nên dựa vào các quy tắc chuyển giá trị sang Boolean ngầm định** để diễn đạt nghiệp vụ. Dùng phép so sánh rõ ràng giúp người đọc biết chính xác vì sao một document được giữ lại.

## 5. Aggregation expression: tính giá trị trong pipeline

Aggregation pipeline được viết bằng `db.collection.aggregate([...])`. Mỗi phần tử mảng pipeline là một **stage**.

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $project: {
      _id: 1,
      customerId: 1,
      gross: {
        $multiply: ["$quantity", "$unitPrice"]
      },
      net: {
        $subtract: [
          { $multiply: ["$quantity", "$unitPrice"] },
          { $ifNull: ["$discount", NumberDecimal("0")] }
        ]
      }
    }
  },
  { $sort: { net: -1 } }
]);
```

Pipeline này:

1. `$match` chỉ giữ đơn `PAID`.
2. `$project` tạo hai giá trị tính toán `gross` và `net` cho mỗi document.
3. `$sort` sắp xếp theo `net` **đã được tạo ra ở stage trước**.

Ở `$project`, biểu thức `$multiply` trả về **một số**, không trả về tập document. `$subtract` trả một giá trị số, còn `$ifNull` trả giá trị thay thế khi null hoặc missing. Đó là lý do các phép tính này không thể đặt trực tiếp thành một stage ở cấp ngoài của pipeline.

### 5.1. Phân biệt stage và expression bằng cách nhìn “đầu vào, đầu ra”

| Thành phần | Nhận gì? | Trả gì? | Ví dụ |
|---|---|---|---|
| Query operator `$gt` | Giá trị trường và điều kiện dưới key của filter | Điều kiện khớp/không khớp | `{ quantity: { $gt: 2 } }` |
| Query operator `$expr` | Một biểu thức aggregation trong filter | Điều kiện khớp/không khớp | `{ $expr: { $gt: ["$quantity", 2] } }` |
| Expression `$gt` | Hai biểu thức/toán hạng | Boolean | `{ $gt: ["$quantity", 2] }` |
| Expression `$multiply` | Các biểu thức số | Giá trị số | `{ $multiply: ["$quantity", "$unitPrice"] }` |
| Expression `$ifNull` | Giá trị nguồn và giá trị dự phòng | Giá trị theo điều kiện null/missing | `{ $ifNull: ["$discount", 0] }` |
| Stage `$match` | Luồng document + bộ lọc | Luồng document đã lọc | `{ $match: { status: "PAID" } }` |
| Stage `$project` | Luồng document + phép chọn/tính trường | Luồng document có cấu trúc mới | `{ $project: { gross: { $multiply: [...] } } }` |
| Stage `$group` | Luồng document + khóa nhóm và accumulator | Một document cho mỗi nhóm | `{ $group: { _id: "$status", count: { $sum: 1 } } }` |

**Tên bắt đầu bằng `$` không đủ để xác định vai trò.** Hãy nhìn vị trí của toán tử trong command.

### 5.2. Cùng phép so sánh dùng được để lọc hoặc tạo cột kết quả

```javascript
// Chỉ giữ document có quantity >= 2.
db.orders.find({
  $expr: { $gte: ["$quantity", 2] }
});

// Giữ tất cả document, nhưng tạo thêm cột Boolean.
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      quantity: 1,
      enoughQuantity: { $gte: ["$quantity", 2] }
    }
  }
]);
```

Biểu thức `{ $gte: ["$quantity", 2] }` giống nhau, nhưng **filter** quyết định document nào xuất hiện, còn **projection** tạo giá trị `true` hoặc `false` trên các document đầu ra.

### 5.3. Cùng expression trong `$match` qua `$expr`

Stage `$match` sử dụng ngữ pháp của **query filter**:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      $expr: { $gte: ["$quantity", 2] }
    }
  },
  { $project: { _id: 1, status: 1, quantity: 1 } }
]);
```

Không viết:

```javascript
// Sai ngữ cảnh: $gte ở top-level của $match không phải
// query filter để biểu diễn phép so sánh hai toán hạng.
db.orders.aggregate([
  { $match: { $gte: ["$quantity", 2] } }
]);
```

Tại vị trí `$match` này, cần `$expr` để tạo cầu nối đến biểu thức aggregation. Ngược lại, trong `$project` không cần bọc toán tử so sánh bằng `$expr`, vì `$project` đã ở ngữ cảnh expression.

## 6. Cùng tên toán tử nhưng cú pháp khác nhau

Đây là nhóm lỗi dễ xảy ra nhất khi chuyển từ `find()` sang `$expr` hoặc `$project`.

### 6.1. `$eq`, `$gt` và các toán tử so sánh

**Trong query filter**:

```javascript
{ status: { $eq: "PAID" } }
{ quantity: { $gt: 2 } }
```

**Trong aggregation expression**:

```javascript
{ $eq: ["$status", "PAID"] }
{ $gt: ["$quantity", 2] }
```

Không thể dùng cú pháp `{ $gt: ["$quantity", 2] }` trực tiếp làm giá trị của `quantity` trong filter rồi kỳ vọng nó tự trở thành aggregation expression.

### 6.2. `$in`: mảng giá trị khác mảng hai toán hạng

**Query operator `$in`**: trường `status` có thuộc danh sách giá trị cho phép hay không?

```javascript
db.orders.find({
  status: { $in: ["PAID", "PENDING"] }
});
```

**Aggregation expression `$in`**: biểu thức thứ nhất có nằm trong mảng được tạo bởi biểu thức thứ hai hay không?

```javascript
db.orders.find({
  $expr: {
    $in: ["$status", ["PAID", "PENDING"]]
  }
});
```

Hai cú pháp trả kết quả tương tự trên bộ dữ liệu đơn giản này, nhưng không thể tráo vị trí toán hạng. Nếu mảng thứ hai của expression `$in` không cho ra một mảng, expression có thể phát sinh lỗi.

### 6.3. `$and` / `$or`: kết hợp điều kiện hay kết hợp biểu thức?

**Query logic** nhận danh sách các **filter document**:

```javascript
db.orders.find({
  $and: [
    { status: "PAID" },
    { quantity: { $gte: 2 } }
  ]
});
```

**Aggregation expression logic** nhận danh sách các **expression**:

```javascript
db.orders.find({
  $expr: {
    $and: [
      { $eq: ["$status", "PAID"] },
      { $gte: ["$quantity", 2] }
    ]
  }
});
```

Trong `$project` có thể dùng chính expression `$and` để tạo trường `eligible`:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      eligible: {
        $and: [
          { $eq: ["$status", "PAID"] },
          { $gte: ["$quantity", 2] }
        ]
      }
    }
  }
]);
```

### 6.4. `$not` ở hai ngữ cảnh khác nhau

Toán tử phủ định cũng có hai hình dạng:

```javascript
// Query operator $not: phủ định một điều kiện trên trường.
db.orders.find({
  quantity: { $not: { $gte: 2 } }
});

// Aggregation expression $not: biểu thức Boolean là đối số.
db.orders.find({
  $expr: {
    $not: [{ $gte: ["$quantity", 2] }]
  }
});
```

Hai ví dụ cùng loại O2 trên bộ dữ liệu mẫu vì `quantity` luôn tồn tại và là số, nhưng **không nên suy luận chúng tương đương với mọi dữ liệu**. Khi trường thiếu, có kiểu khác hoặc là mảng, ngữ nghĩa bộ lọc và biểu thức có thể dẫn đến khác biệt.

### 6.5. `$size`: predicate của mảng và biểu thức tính độ dài

**Query operator `$size`** kiểm tra một trường mảng có đúng số phần tử chỉ định:

```javascript
// O2 có mảng tags rỗng.
db.orders.find({ tags: { $size: 0 } });
```

**Aggregation expression `$size`** trả về **số lượng phần tử** của một mảng:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      tagCount: { $size: "$tags" }
    }
  }
]);
```

Trong bộ dữ liệu mẫu, `tagCount` lần lượt là 2, 0, 1 và 1. Cần chú ý: aggregation expression `$size` yêu cầu toán hạng là mảng; nếu trường bị thiếu, null hoặc khác kiểu, biểu thức có thể lỗi. Có thể kiểm tra trước:

```javascript
db.orders.aggregate([
  {
    $project: {
      tagCount: {
        $cond: [
          { $isArray: "$tags" },
          { $size: "$tags" },
          0
        ]
      }
    }
  }
]);
```

`$isArray` là **aggregation expression**, không phải một query operator dùng theo cách `{ tags: { $isArray: true } }`.

### 6.6. `$regex` của query và `$regexMatch` của expression

Để lọc mã khách bắt đầu bằng `C0` có thể viết:

```javascript
// Query operator.
db.orders.find({
  customerId: { $regex: "^C0" }
});
```

Khi cần biểu thức tính ra Boolean, dùng `$regexMatch`:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      customerId: 1,
      codeStartsWithC0: {
        $regexMatch: {
          input: "$customerId",
          regex: "^C0"
        }
      }
    }
  }
]);
```

Không phải lúc nào hai hình thức regex có cùng khả năng sử dụng index hoặc cùng cách xử lý collation. Cần kiểm tra hình dạng query và kế hoạch thực thi; khi biểu thức lấy dữ liệu từ trường có thể null/thiếu, cần có cơ chế chuyển kiểu hoặc giá trị mặc định phù hợp với yêu cầu của toán tử.

### 6.7. `$exists` là query operator; `$type` trong expression có cách khác

Trong filter:

```javascript
db.orders.find({
  discount: { $exists: false }
});
```

Đây là kiểm tra trường **có tồn tại** hay không. Không dùng `$exists` như một aggregation expression trong `$project`.

Nếu đang ở aggregation expression và cần phân biệt trường thiếu, có thể dùng `$type`:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discountType: { $type: "$discount" },
      discountIsMissing: {
        $eq: [{ $type: "$discount" }, "missing"]
      }
    }
  }
]);
```

Với bộ dữ liệu mẫu, `discount` đều có mặt: ba document có kiểu `decimal` và O4 có kiểu `null`; không có document nào trả `"missing"`.

**Đừng nhầm** phép `{ discount: null }` trong filter với kiểm tra chính xác BSON Null: điều kiện bằng null của query còn khớp trường thiếu. Ngữ nghĩa thiếu/null trong aggregation expression có thể khác và nên được kiểm soát tường minh bằng `$type`, `$ifNull` hoặc cấu trúc khác phù hợp nghiệp vụ.

## 7. Những quy tắc cú pháp chỉ xuất hiện trong aggregation expression

### 7.1. `"$field"` là tham chiếu trường, còn `"text"` là chuỗi hằng

Trong aggregation expression:

```javascript
{ $eq: ["$status", "PAID"] }
```

- `"$status"`: lấy giá trị trường `status` từ document hiện tại.
- `"PAID"`: một chuỗi hằng.

Điều đó cũng có nghĩa một chuỗi hằng **bắt đầu bằng ký tự `$`** cần cách diễn đạt riêng:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      sample: { $literal: "$PROMO" }
    }
  }
]);
```

`$literal` yêu cầu MongoDB sử dụng chuỗi `"$PROMO"` như **giá trị văn bản**, thay vì hiểu nó là tham chiếu tới trường `PROMO`.

Nếu muốn so sánh trường `coupon` với chuỗi hằng `"$PROMO"`:

```javascript
{
  $expr: {
    $eq: ["$coupon", { $literal: "$PROMO" }]
  }
}
```

### 7.2. Phân biệt đường dẫn trường và biến `$$variable`

`"$quantity"` tham chiếu đến một trường ở document hiện tại. Ngược lại, `"$$NOW"` là một **biến hệ thống** trong ngôn ngữ aggregation expression:

```javascript
db.orders.find({
  $expr: {
    $lte: ["$createdAt", "$$NOW"]
  }
});
```

Ví dụ này lọc những đơn có thời gian tạo không muộn hơn giá trị thời gian hiện tại mà biểu thức hệ thống cung cấp.

Trong những expression có phạm vi biến như `$map`, `$filter` hoặc `$let`, ta còn dùng `$$tenBien` để tham chiếu đến biến tự đặt:

```javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      upperCaseTags: {
        $map: {
          input: "$tags",
          as: "tag",
          in: { $toUpper: "$$tag" }
        }
      }
    }
  }
]);
```

`$map` lần lượt duyệt từng phần tử của mảng `tags`; `$$tag` chỉ phần tử hiện tại. Chỉ viết `"$tag"` sẽ chuyển thành tham chiếu đến trường ở document đang xử lý, **không phải biến của vòng lặp**.

### 7.3. Expression thường có thể lồng nhau

```javascript
{
  $subtract: [
    { $multiply: ["$quantity", "$unitPrice"] },
    { $ifNull: ["$discount", NumberDecimal("0")] }
  ]
}
```

Toán tử ở ngoài nhận **kết quả** của các toán tử bên trong. Đây là tư duy quan trọng khi viết công thức nghiệp vụ bằng MongoDB. Một toán tử ở ngữ cảnh query filter có thể có cú pháp và ràng buộc khác; không thể kết luận “mọi toán tử có dấu `$` đều có thể lồng tùy ý”.

## 8. Vì sao `$match` vẫn dùng query operators?

Một sự nhầm lẫn phổ biến là cho rằng khi bước vào `aggregate()`, toàn bộ cú pháp đều đổi sang aggregation expressions. Thực tế, mỗi stage định nghĩa **ngôn ngữ đầu vào riêng**.

Stage `$match` nhận một **bộ lọc kiểu query**:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      quantity: { $gte: 2 }
    }
  }
]);
```

Nếu điều kiện cần so sánh trường với trường hoặc tính toán, bọc expression bằng `$expr`:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      $expr: {
        $gte: [
          { $multiply: ["$quantity", "$unitPrice"] },
          "$minEligibleTotal"
        ]
      }
    }
  }
]);
```

Kết quả: O1 và O4. Stage `$match` vẫn lọc document, chỉ có điều một phần điều kiện được đánh giá bằng aggregation expression.

### 8.1. Khi nên đặt `$match` sớm

Nếu bộ lọc chỉ phụ thuộc vào trường đã có trong document gốc, thường nên đặt `$match` đủ sớm để giảm số document đi qua các stage xử lý đắt như `$unwind` hoặc `$group`:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 }
    }
  }
]);
```

MongoDB còn có trình tối ưu pipeline có thể dịch chuyển một số điều kiện khi bảo toàn ngữ nghĩa. Không cần cố gắng tự viết mọi bộ lọc thành `$expr`, vì query operator đơn giản vừa thể hiện rõ ý vừa thường thuận lợi khi xem index.

### 8.2. Khi `$match` phải ở sau `$project` hoặc `$set`

Nếu bộ lọc phụ thuộc vào **trường tính toán mới được tạo**, phải bảo đảm trường tồn tại ở vị trí đặt bộ lọc:

```javascript
db.orders.aggregate([
  {
    $set: {
      netAmount: {
        $subtract: [
          { $multiply: ["$quantity", "$unitPrice"] },
          { $ifNull: ["$discount", NumberDecimal("0")] }
        ]
      }
    }
  },
  { $match: { netAmount: { $gte: NumberDecimal("300000") } } },
  { $project: { _id: 1, netAmount: 1 } }
]);
```

Ở đây `netAmount` chưa có trong tài liệu nguồn; nếu đặt điều kiện `netAmount` trước stage `$set`, nó sẽ không có giá trị tính toán cần dùng. Với pipeline đơn giản, có thể viết `$match + $expr` trực tiếp trên các trường nguồn để tránh phải tạo field trung gian; cách nào tốt hơn còn phụ thuộc khả năng đọc hiểu và kế hoạch thực thi.

## 9. Sự khác biệt về index và chi phí thực thi

MongoDB sử dụng bộ lập kế hoạch truy vấn để quyết định cách đọc dữ liệu. Một filter đơn giản:

```javascript
db.orders.find({
  status: "PAID",
  quantity: { $gte: 2 }
});
```

có thể hưởng lợi từ compound index:

```javascript
db.orders.createIndex({ status: 1, quantity: 1 });
```

Bộ lập kế hoạch có khả năng dùng điều kiện bằng nhau của `status` và điều kiện khoảng trên `quantity` để giảm số khóa/tài liệu cần xét.

Nhưng bộ lọc tính toán:

```javascript
db.orders.find({
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

phải tính giá trị từ **nhiều trường** của mỗi document. Index bình thường trên `quantity` hoặc `unitPrice` không tự chứa kết quả phép nhân theo từng document, nên không thể giả định MongoDB sẽ dùng index để giải quyết phép so sánh đó mà không đọc dữ liệu liên quan.

Một cách thực hành phổ biến là **giữ điều kiện có thể index trong query filter, chỉ để phần cần tính toán trong `$expr`**:

```javascript
db.orders.find({
  status: "PAID",
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
});
```

Không nên kết luận tuyệt đối rằng “`$expr` không bao giờ dùng được index”. Một số phép so sánh ở dạng phù hợp và trong một số ngữ cảnh (đặc biệt các pipeline `$lookup` có ràng buộc về trường và hằng) có thể được tối ưu bằng index, tùy phiên bản, loại index và điều kiện cụ thể. Ngược lại, có index không có nghĩa bất kỳ biểu thức nào cũng sử dụng được index.

### 9.1. Quan sát thay vì đoán

```javascript
db.orders.find({
  status: "PAID",
  quantity: { $gte: 2 }
}).explain("executionStats");

db.orders.find({
  status: "PAID",
  $expr: {
    $gt: [
      { $multiply: ["$quantity", "$unitPrice"] },
      "$minEligibleTotal"
    ]
  }
}).explain("executionStats");
```

Khi đọc `explain()`, xem:

| Dấu hiệu | Ý nghĩa |
|---|---|
| `IXSCAN` | Có bước đọc khóa index |
| `COLLSCAN` | Có bước quét collection |
| `FETCH` | Có bước lấy tài liệu sau khi đọc khóa |
| `totalKeysExamined` | Số khóa index được xem xét |
| `totalDocsExamined` | Số document được xem xét |
| `nReturned` | Số document kết quả |
| `executionTimeMillis` | Thời gian thực thi do thống kê ghi nhận; cần xem cùng bối cảnh đo |

Định dạng explain có thể khác tùy phiên bản MongoDB và execution engine. Với bộ mẫu chỉ có bốn đơn, MongoDB có thể chọn quét collection do dữ liệu quá nhỏ; mục tiêu trước tiên là hiểu **đường thực thi**, không suy diễn hiệu năng production từ ví dụ vài document.

### 9.2. Khi nào lưu trường đã tính?

Nếu nghiệp vụ thường xuyên lọc theo `netAmount` hoặc `grossAmount` mà biểu thức phải tính trên hàng triệu document, có thể cân nhắc **lưu một trường dẫn xuất** ngay trên document, rồi tạo index cho trường này:

```javascript
{
  _id: "O1",
  quantity: 3,
  unitPrice: NumberDecimal("120000"),
  discount: NumberDecimal("20000"),
  grossAmount: NumberDecimal("360000"),
  netAmount: NumberDecimal("340000")
}
```

`grossAmount` và `netAmount` được **ứng dụng tính và duy trì nhất quán khi ghi**. Nếu số lượng, đơn giá hoặc giảm giá thay đổi mà ứng dụng quên cập nhật hai trường dẫn xuất, truy vấn theo index của `netAmount` sẽ nhanh nhưng cho **kết quả nghiệp vụ sai**.

Vì vậy, tối ưu khả năng truy vấn phải đi kèm thiết kế cập nhật, ranh giới nguyên tử và kiểm soát dữ liệu dẫn xuất; không thêm trường chỉ để tránh viết `$expr` trong mọi trường hợp.

## 10. So sánh với dữ liệu mảng: `$elemMatch` và các biểu thức mảng

Khi cấu trúc document chứa mảng, cần biết mình đang **lọc document dựa trên phần tử** hay **tính toán trên các phần tử**.

Giả sử collection `carts`:

```javascript
db.carts.insertMany([
  {
    _id: "CART1",
    items: [
      { sku: "BOOK", quantity: 1, price: 100000 },
      { sku: "PEN", quantity: 5, price: 10000 }
    ]
  },
  {
    _id: "CART2",
    items: [
      { sku: "BOOK", quantity: 3, price: 100000 },
      { sku: "PEN", quantity: 1, price: 10000 }
    ]
  }
]);
```

### 10.1. Query operator `$elemMatch`

Tìm giỏ có ít nhất một dòng hàng **vừa là BOOK, vừa có quantity từ 2**:

```javascript
db.carts.find({
  items: {
    $elemMatch: {
      sku: "BOOK",
      quantity: { $gte: 2 }
    }
  }
});
```

Chỉ CART2 khớp. Nếu viết:

```javascript
db.carts.find({
  "items.sku": "BOOK",
  "items.quantity": { $gte: 2 }
});
```

CART1 cũng có thể khớp vì điều kiện `sku` và `quantity` có thể được thỏa bởi **hai phần tử khác nhau**. `$elemMatch` ở đây là query operator giúp kiểm soát ngữ nghĩa cùng phần tử.

### 10.2. Aggregation expression `$filter`

Nếu muốn **trả về chính những dòng hàng BOOK có quantity từ 2**, có thể dùng `$filter` trong `$project`:

```javascript
db.carts.aggregate([
  {
    $project: {
      _id: 1,
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $and: [
              { $eq: ["$$item.sku", "BOOK"] },
              { $gte: ["$$item.quantity", 2] }
            ]
          }
        }
      }
    }
  }
]);
```

Pipeline này vẫn trả **cả hai giỏ**, nhưng `eligibleItems` của CART1 là `[]` và của CART2 chứa phần tử BOOK có quantity 3.

Vì vậy:

- `$elemMatch` trong query: **lọc document** dựa trên một phần tử thỏa điều kiện.
- `$filter` trong aggregation: **tạo mảng mới** gồm những phần tử thỏa biểu thức Boolean.
- Có thể kết hợp `$expr`, `$size` và `$filter` nếu muốn lọc document dựa trên số phần tử thỏa điều kiện tính toán, nhưng cách này không tự tương đương về hiệu năng với một predicate có thể index.

Ví dụ chỉ giữ giỏ có ít nhất một phần tử BOOK và quantity từ 2 bằng aggregation expression:

```javascript
db.carts.find({
  $expr: {
    $gt: [
      {
        $size: {
          $filter: {
            input: "$items",
            as: "item",
            cond: {
              $and: [
                { $eq: ["$$item.sku", "BOOK"] },
                { $gte: ["$$item.quantity", 2] }
              ]
            }
          }
        }
      },
      0
    ]
  }
});
```

Kết quả logic của ví dụ này cũng là CART2, nhưng nếu mục đích chỉ là lọc trên điều kiện mảng đơn giản, `$elemMatch` thường ngắn hơn và rõ yêu cầu hơn.

## 11. Biểu thức trong update pipeline khác với update operators truyền thống

MongoDB có hai hình thức cập nhật rất dễ nhầm:

### 11.1. Cập nhật truyền thống bằng toán tử `$set`

```javascript
db.orders.updateOne(
  { _id: "O1" },
  {
    $set: {
      status: "SHIPPED"
    }
  }
);
```

Ở đây đối số thứ hai là **update document**, `$set` là toán tử cập nhật (update operator), không phải aggregation stage. Giá trị của trường thường được dùng làm dữ liệu để gán, không phải một công thức pipeline tự động.

### 11.2. Cập nhật bằng aggregation pipeline

```javascript
db.orders.updateOne(
  { _id: "O1" },
  [
    {
      $set: {
        netAmount: {
          $subtract: [
            { $multiply: ["$quantity", "$unitPrice"] },
            { $ifNull: ["$discount", NumberDecimal("0")] }
          ]
        }
      }
    }
  ]
);
```

Ở đây đối số thứ hai là **mảng các stage cập nhật được hỗ trợ**, và `$set` đóng vai trò **aggregation stage**, nơi `netAmount` được tính từ các trường trong document.

Đó là một trường hợp điển hình cùng tên `$set` nhưng hai hình thức khác nhau. Sự khác biệt được quyết định bởi **đối số update là object hay mảng stage**. Một update pipeline chỉ chấp nhận tập stage được MongoDB hỗ trợ cho cập nhật; không phải mọi stage của `aggregate()` đều dùng được.

**Lưu ý:** những ví dụ update ở phần này thay đổi dữ liệu thử nghiệm. Nếu cần so sánh kết quả truy vấn với bảng ban đầu, hãy thực hiện các ví dụ đọc trước hoặc khởi tạo lại collection.

## 12. `$expr` trong `$lookup`: so sánh trường ở hai ngữ cảnh

Trong aggregation pipeline, `$lookup` có thể kết hợp document từ collection khác. Với dạng `pipeline` và `let`, `$expr` giúp so sánh trường của collection được kết hợp với biến lấy từ document nguồn.

Giả sử:

```javascript
// Collection customers
{ _id: "C01", tier: "GOLD" }
{ _id: "C02", tier: "STANDARD" }
{ _id: "C03", tier: "STANDARD" }
```

Khi kết hợp đơn hàng với khách hàng:

```javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      let: { wantedCustomerId: "$customerId" },
      pipeline: [
        {
          $match: {
            $expr: {
              $eq: ["$_id", "$$wantedCustomerId"]
            }
          }
        },
        { $project: { _id: 1, tier: 1 } }
      ],
      as: "customer"
    }
  }
]);
```

Diễn giải:

1. `let` tạo biến `wantedCustomerId` từ trường `customerId` của mỗi đơn hàng bên ngoài.
2. Bên trong pipeline của `$lookup`, `"$_id"` tham chiếu tới `_id` của document từ collection `customers`.
3. `"$$wantedCustomerId"` tham chiếu tới biến do `let` khai báo, không phải trường của collection `customers`.
4. `$expr` đưa phép so sánh giữa trường và biến vào bộ lọc `$match`.

Trong một số điều kiện, các phép so sánh `$eq`, `$lt`, `$lte`, `$gt`, `$gte` trong `$expr` của pipeline `$lookup` có thể tận dụng index trên collection `from` khi toán hạng thích hợp là một giá trị hằng theo ngữ cảnh tra cứu; những ràng buộc về mảng, giá trị thiếu và loại index có thể giới hạn khả năng này. Đừng mặc định mọi pipeline `$lookup` có `$expr` đều dùng index.

Nếu chỉ cần kết hợp bằng equality giữa hai trường, dạng `localField` / `foreignField` của `$lookup` thường đơn giản hơn. Dạng `let` / `pipeline` hữu ích khi điều kiện kết hợp hoặc phép xử lý cần linh hoạt hơn.

## 13. Những lỗi cú pháp và ngữ nghĩa thường gặp

| Cách viết hoặc suy nghĩ | Vì sao có vấn đề? | Hướng đúng |
|---|---|---|
| `{ quantity: { $gt: "$minimum" } }` | Chuỗi ở query operand không phải field reference của expression | Dùng `{ $expr: { $gt: ["$quantity", "$minimum"] } }` |
| `{ $match: { $gt: ["$quantity", 2] } }` | `$match` chờ query filter, `$gt` expression đặt sai ngữ cảnh | Bọc bằng `$expr` |
| `{ $project: { valid: { $expr: ... } } }` | `$project` đã nhận expression; `$expr` là cầu nối dành cho query context | Viết expression Boolean trực tiếp |
| `{ $expr: { quantity: { $gte: 2 } } }` | Bên trong `$expr` cần aggregation expression, không phải filter theo field | `{ $expr: { $gte: ["$quantity", 2] } }` |
| Dùng `$size: 0` làm phép tính số phần tử trong `$project` | Query `$size` kiểm tra độ dài; expression `$size` cần một biểu thức mảng | `{ $size: "$tags" }` |
| Dùng `{ $exists: true }` trong `$project` như expression | `$exists` là query operator | Dùng `$type`, điều kiện khác phù hợp |
| Nghĩ `"$field"` luôn là văn bản nguyên dạng | Trong aggregation expression, nó là tham chiếu trường | Dùng `$literal` nếu cần chuỗi bắt đầu bằng `$` |
| Nghĩ `"$tag"` là biến trong `$map` | Biến do `as` khai báo cần tiền tố hai dấu `$` | Dùng `"$$tag"` |
| Nghĩ mọi `$expr` đều không dùng index | Khả năng index phụ thuộc cấu trúc, ngữ cảnh và phiên bản | Đọc `explain()` và tối ưu filter đơn giản |
| Nghĩ aggregation pipeline chỉ dùng expression | Các stage có ngữ pháp riêng; `$match` nhận query filter | Phân biệt stage/query/expression |
| Thấy `$set` thì coi đều là update operator | `$set` còn là aggregation stage | Xem update argument là object hay mảng stage |
| Nghĩ `{ field: null }` chỉ tìm explicit null | Query equality với null còn khớp field thiếu | Dùng điều kiện kiểu/tồn tại theo mục tiêu |

## 14. Phương pháp chọn đúng công cụ cho yêu cầu

Hãy hỏi ba câu theo thứ tự:

**Câu 1: Tôi chỉ cần quyết định document nào được giữ lại?**

Nếu có, bắt đầu bằng **query filter**. Ví dụ `status = "PAID"`, `quantity >= 2`, `tags` có phần tử `"vip"` đều là điều kiện dễ viết bằng toán tử truy vấn.

**Câu 2: Điều kiện có cần tính toán từ nhiều trường hoặc so sánh trường với trường?**

Nếu có, dùng **`$expr` trong query filter**, hoặc tạo giá trị tính toán trong aggregation pipeline rồi lọc theo giá trị đó. Giữ các predicate đơn giản ở ngoài `$expr` nếu phù hợp.

**Câu 3: Tôi cần trả thêm giá trị tính toán, thay đổi cấu trúc hoặc nhóm nhiều document?**

Nếu có, dùng **aggregation pipeline**, đặt biểu thức trong những stage thích hợp như `$project`, `$set` hoặc `$group`. `$expr` có thể nằm trong `$match` nếu stage đó cần tính toán để lọc.

Một bảng quyết định:

| Yêu cầu | Công cụ phù hợp | Ví dụ |
|---|---|---|
| Lọc đơn có `quantity >= 2` | Query operator | `{ quantity: { $gte: 2 } }` |
| Lọc đơn có `quantity > minimumQuantity` lưu cùng document | `$expr` | `{ $expr: { $gt: ["$quantity", "$minimumQuantity"] } }` |
| Lọc đơn có `quantity × unitPrice > minEligibleTotal` | `$expr` + aggregation expressions | `$gt` lồng `$multiply` |
| Trả thêm cột `grossAmount` | Stage `$project` / `$set` + expression `$multiply` | `{ grossAmount: { $multiply: [...] } }` |
| Đếm đơn theo `status` | Pipeline `$group` + accumulator | `{ $group: { _id: "$status", count: { $sum: 1 } } }` |
| Tìm mảng chứa phần tử thỏa nhiều điều kiện | Query `$elemMatch` | `{ items: { $elemMatch: {...} } }` |
| Tạo mảng đã lọc rồi trả về | Aggregation expression `$filter` | `{ eligibleItems: { $filter: {...} } }` |
| Dùng trường bên ngoài trong `$lookup` pipeline | `let` + `$expr` | `$eq: ["$_id", "$$wantedId"]` |

## 15. Bài thực hành tự kiểm chứng

### Bài 1 — Viết ba cách cho một điều kiện

Với collection `orders` ở phần 2, hãy biểu diễn điều kiện **quantity từ 2 trở lên** theo ba cách:

1. Query operator trong `find()`.
2. `$expr` trong `find()`.
3. Aggregation `$project` trả một trường Boolean `enoughQuantity` mà không lọc bỏ đơn nào.

Hãy giải thích vì sao hai cách đầu trả tập document phù hợp còn cách thứ ba trả một giá trị Boolean trên mỗi document.

### Bài 2 — Tính thành tiền và lọc theo trường khác

Viết `find()` để tìm những đơn có `quantity × unitPrice > minEligibleTotal`; kết hợp thêm điều kiện `status: "PAID"`. Với bộ mẫu, hãy dự đoán `_id` nào xuất hiện.

Gợi ý: dùng `$multiply` và `$gt` **bên trong `$expr`**, nhưng dùng `status` ở bộ lọc ngoài.

### Bài 3 — So sánh `$size` ở hai ngữ cảnh

Với các tài liệu có `tags`, hãy:

- Dùng query operator để lấy những đơn có **mảng tags rỗng**.
- Dùng aggregation expression để tạo trường `tagCount`.
- Tìm hiểu pipeline sẽ xử lý ra sao nếu một document thiếu `tags`; thêm kiểm tra kiểu bằng `$isArray`.

### Bài 4 — Sửa cú pháp sai

Cho ba đoạn:

```javascript
// a
db.orders.find({ quantity: { $gt: "$minimum" } });

// b
db.orders.aggregate([
  { $match: { $eq: ["$status", "PAID"] } }
]);

// c
db.orders.aggregate([
  { $project: { valid: { $expr: { $gte: ["$quantity", 2] } } } }
]);
```

Hãy sửa từng đoạn theo đúng ngữ cảnh query hoặc expression và giải thích sự khác nhau giữa “so sánh một trường với hằng” và “so sánh hai trường”.

### Bài 5 — Chọn bộ lọc thay vì biểu thức tính toán

Giả sử collection đã có index `{ status: 1, quantity: 1 }`. Hãy đề xuất cách diễn đạt điều kiện **status = PAID và quantity >= 2**, sau đó so sánh với một cách viết hoàn toàn bằng `$expr`. Chạy `explain("executionStats")` trên dữ liệu thử nghiệm đủ lớn để quan sát kế hoạch, tránh kết luận máy móc rằng cách nào chắc chắn nhanh hơn.

### Bài 6 — Tách filter, phép tính và nhóm

Viết pipeline trả về doanh thu **sau giảm** theo `customerId`, chỉ tính các đơn `PAID`:

1. `$match` lọc `status`.
2. `$project` tính `netAmount = quantity × unitPrice − discount`; nếu `discount` null thì dùng 0.
3. `$group` theo `customerId` với accumulator cộng `netAmount`.
4. `$sort` theo tổng doanh thu giảm dần.

Sau đó thử biến thể chỉ lấy những đơn có `netAmount >= 300000` trước khi nhóm, và giải thích khi nào cần `$expr` để thay cho việc tạo một trường trung gian.

### Bài 7 — Phạm vi biến trong `$lookup`

Viết `$lookup` từ `orders` tới `customers` sao cho `orders.customerId` được gắn với `customers._id`. Thử hai cách:

- `localField` / `foreignField`.
- `let` / `pipeline` / `$match` / `$expr`.

Hãy giải thích sự khác nhau giữa `"$_id"` và `"$$wantedCustomerId"` trong pipeline con.

## 16. Ghi nhớ

**Query operator** diễn tả điều kiện khớp document, thường theo cú pháp `field: { $operator: value }`. Đây là điểm bắt đầu tự nhiên cho bộ lọc đơn giản và những truy vấn cần tối ưu index.

**`$expr` là cầu nối vào ngôn ngữ aggregation expression ngay trong query filter**. Nó giúp so sánh trường với trường và tính toán như `$multiply`, `$subtract`, `$ifNull` trước khi quyết định giữ document.

**Aggregation expression tính một giá trị; pipeline stage xử lý luồng document.** Trong `$project`, `$set` hoặc `$group`, biểu thức giúp tạo dữ liệu kết quả; trong `$match`, muốn dùng biểu thức đó làm bộ lọc thì đặt nó dưới `$expr`.

Khi đọc MongoDB, đừng chỉ nhìn tên toán tử có dấu `$`. Hãy xác định **đang ở ngữ cảnh nào**, **toán hạng là giá trị hay đường dẫn trường**, và **mục tiêu là lọc document hay tính ra giá trị**. Ba câu hỏi này giúp tránh phần lớn lỗi khi chuyển đổi giữa query operator, `$expr` và aggregation expression.
