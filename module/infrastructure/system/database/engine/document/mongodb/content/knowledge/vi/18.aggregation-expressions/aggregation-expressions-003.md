# Kiểm tra, chuyển đổi kiểu bằng $type, $convert và $to*

MongoDB lưu dữ liệu theo mô hình BSON. Trong cùng một collection, các document không bắt buộc có cùng cấu trúc, và một field có thể tồn tại với **những kiểu BSON khác nhau** nếu ứng dụng không kiểm soát schema. Điều này rất linh hoạt nhưng dễ tạo lỗi khi aggregation cần cộng giá tiền, lọc theo ngày, so sánh số hoặc nối chuỗi định danh.

Giả sử collection `orders` có các document:

```javascript
[
  {
    _id: 1,
    total: NumberDecimal("125000.50"),
    orderedAt: ISODate("2026-03-01T09:30:00Z"),
    customerId: ObjectId("65a12f010000000000000001")
  },
  {
    _id: 2,
    total: "85000.75",
    orderedAt: "2026-03-02T10:00:00Z",
    customerId: "65a12f010000000000000002"
  },
  {
    _id: 3,
    total: "không rõ",
    orderedAt: "ngày hôm qua",
    customerId: null
  },
  {
    _id: 4,
    total: null
  },
  {
    _id: 5
  }
]
```

Các bản ghi trên có nhiều vấn đề:

- `total` có thể là `decimal`, `string`, `null` hoặc không tồn tại;
- `orderedAt` có thể là BSON `date`, chuỗi ngày hợp lệ, chuỗi không hợp lệ hoặc thiếu;
- `customerId` có thể là `objectId`, chuỗi hex hoặc `null`.

Muốn tổng hợp doanh thu, ứng dụng cần đảm bảo `total` thực sự là kiểu số. Muốn lọc theo thời gian, `orderedAt` cần được chuẩn hóa thành BSON Date, không chỉ nhìn giống ngày tháng trong một chuỗi.

Trong aggregation, ba nhóm công cụ giải quyết vấn đề này:

| Nhóm | Vai trò | Ví dụ |
|---|---|---|
| `$type` | **Kiểm tra kiểu BSON** mà biểu thức đang trả về | `{ $type: "$total" }` |
| `$convert` | **Chuyển đổi kiểu** và tự định nghĩa xử lý lỗi/null | `{ $convert: { input: "$total", to: "decimal", onError: null, onNull: null } }` |
| `$to*` | **Cú pháp rút gọn** cho các chuyển đổi thường dùng | `{ $toDecimal: "$total" }`, `{ $toDate: "$orderedAt" }` |

Bài học tập trung vào **aggregation expressions** trong các stage như `$project`, `$addFields`/`$set` và `$match` với `$expr`. Các biểu thức này cũng được sử dụng ở những ngữ cảnh MongoDB hỗ trợ expression tương ứng.

## 1. Kiểu BSON khác kiểu hiển thị trong JSON

Một giá trị như `125000` có thể được lưu theo các kiểu BSON khác nhau:

```javascript
{
  amountInt: NumberInt(125000),
  amountLong: NumberLong("125000"),
  amountDouble: 125000.0,
  amountDecimal: NumberDecimal("125000.00"),
  amountText: "125000",
  amountNull: null
}
```

Về mặt ý nghĩa nghiệp vụ, các giá trị trên có thể đều gợi tới “125.000”, nhưng MongoDB không tự coi chuỗi `"125000"` là một số khi áp dụng mọi phép toán. Kiểu BSON ảnh hưởng đến:

1. Phép cộng, nhân, so sánh và việc kiểm tra input của biểu thức;
2. Cách biểu diễn độ chính xác, phạm vi giá trị và tràn số;
3. Thứ tự so sánh khi dữ liệu khác kiểu;
4. Khả năng dùng index trong truy vấn;
5. Kết quả ánh xạ sang Java/JavaScript và cách xuất JSON.

Các kiểu thường gặp:

| Nhãn từ aggregation `$type` | Ý nghĩa |
|---|---|
| `"double"` | Số dấu phẩy động IEEE 754 double |
| `"string"` | Chuỗi UTF-8 |
| `"object"` | Embedded document |
| `"array"` | Mảng |
| `"binData"` | Dữ liệu nhị phân |
| `"objectId"` | BSON ObjectId |
| `"bool"` | Boolean |
| `"date"` | BSON Date |
| `"null"` | Giá trị null hiện diện |
| `"regex"` | Biểu thức chính quy |
| `"int"` | Số nguyên 32-bit |
| `"long"` | Số nguyên 64-bit |
| `"decimal"` | Decimal128 |
| `"timestamp"` | BSON Timestamp |
| `"missing"` | Trường được tham chiếu không tồn tại |

Ngoài ra BSON có những kiểu ít gặp khác, kể cả các kiểu legacy. Không cần ép toàn bộ dữ liệu về một kiểu duy nhất; **cần thống nhất kiểu theo từng field và hợp đồng nghiệp vụ**.

### 1.1. Chuỗi số không phải số BSON

```javascript
{
  _id: "A",
  price: "125000.50"
}
```

Field `price` ở đây là String. Nếu chạy phép toán có yêu cầu đầu vào số, MongoDB có thể báo lỗi hoặc áp dụng quy tắc riêng của biểu thức, chứ không tự đảm bảo chuyển đúng String sang Decimal128.

Cách rõ ràng là chuyển đổi có kiểm soát:

```javascript
{
  $convert: {
    input: "$price",
    to: "decimal",
    onError: null,
    onNull: null
  }
}
```

Một chuỗi hợp lệ có thể tạo số Decimal128; chuỗi không hợp lệ được đánh dấu bằng kết quả `null` trong ví dụ thay vì làm cả aggregation thất bại.

### 1.2. BSON Date không phải String có định dạng ISO

```javascript
{
  orderedAtDate: ISODate("2026-03-01T09:30:00Z"),
  orderedAtString: "2026-03-01T09:30:00Z"
}
```

Giá trị đầu có kiểu `date` và phù hợp với nhiều phép range trên thời gian. Giá trị thứ hai là `string`. Dù nhìn giống nhau khi hiển thị, chúng không cùng kiểu BSON. Một index trên trường ngày không tự biến string thành date.

## 2. Chuẩn bị collection thực hành

Tạo collection riêng để tránh thay đổi dữ liệu nghiệp vụ:

```javascript
db.typeConversionLab.drop();

db.typeConversionLab.insertMany([
  {
    _id: "O-101",
    total: NumberDecimal("125000.50"),
    quantity: NumberInt(2),
    orderedAt: ISODate("2026-03-01T09:30:00Z"),
    customerId: ObjectId("65a12f010000000000000001"),
    active: true
  },
  {
    _id: "O-102",
    total: "85000.75",
    quantity: "3",
    orderedAt: "2026-03-02T10:00:00Z",
    customerId: "65a12f010000000000000002",
    active: "false"
  },
  {
    _id: "O-103",
    total: "không rõ",
    quantity: "3.5",
    orderedAt: "ngày hôm qua",
    customerId: "không phải objectId",
    active: ""
  },
  {
    _id: "O-104",
    total: null,
    quantity: null,
    orderedAt: null,
    customerId: null
  },
  {
    _id: "O-105"
  },
  {
    _id: "O-106",
    total: NumberLong("9000000000"),
    quantity: NumberInt(1),
    orderedAt: ISODate("2026-03-03T08:00:00Z"),
    active: false
  }
]);
```

**Chú ý:** `db.typeConversionLab.drop()` xóa collection thử nghiệm nếu nó đã tồn tại. Chỉ dùng ví dụ này trong môi trường học tập, không chạy `drop()` trên collection production.

Dữ liệu cố tình không đồng nhất để thấy rõ sự khác biệt giữa “không chuyển được”, `null` và trường thiếu. Trong ứng dụng thật, nên chặn dữ liệu sai kiểu ở write path bằng schema validation, API validation và migration có kiểm soát.

## 3. $type: xem kiểu BSON của một biểu thức

Cú pháp cơ bản:

```javascript
{ $type: <expression> }
```

Thông dụng nhất, truyền đường dẫn field:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      total: 1,
      totalType: { $type: "$total" },
      orderedAtType: { $type: "$orderedAt" },
      customerIdType: { $type: "$customerId" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Với những document đã tạo:

- O-101: `totalType = "decimal"`, `orderedAtType = "date"`, `customerIdType = "objectId"`.
- O-102: cả ba field tương ứng có kiểu `"string"`.
- O-103: các trường đó cũng là string, dù **giá trị chuỗi không hợp lệ để chuyển**.
- O-104: các trường có mặt với `null` trả nhãn `"null"`.
- O-105: các trường không tồn tại trả nhãn `"missing"`.
- O-106: `totalType = "long"`.

**$type kiểm tra kiểu, không kiểm tra giá trị có hợp lệ theo nghiệp vụ hay không.** Chuỗi `"85000.75"` và `"không rõ"` đều trả `"string"`, nhưng chỉ chuỗi đầu có thể chuyển trực tiếp sang Decimal128 theo cú pháp số hợp lệ.

### 3.1. Phân biệt null và missing

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      typeOfTotal: { $type: "$total" }
    }
  }
]);
```

Ở O-104, kết quả có `typeOfTotal: "null"`.

Ở O-105, kết quả có `typeOfTotal: "missing"`.

Sự khác biệt:

- **null:** field tồn tại, giá trị BSON là `null`;
- **missing:** field không tồn tại trong document.

Nhiều biểu thức khác có thể xử lý hai trạng thái này giống nhau. Chẳng hạn `$ifNull` thường coi giá trị missing và null như nhau trong việc chọn fallback. Khi cần thống kê chất lượng dữ liệu, `$type` giúp giữ được thông tin phân biệt.

### 3.2. $type trên field array

Giả sử:

```javascript
db.typeConversionLab.insertOne({
  _id: "O-107",
  values: [1, "2", null],
  metadata: { source: "legacy" }
});
```

Query:

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-107" } },
  {
    $project: {
      valuesType: { $type: "$values" },
      metadataType: { $type: "$metadata" }
    }
  }
]);
```

Kết quả `valuesType = "array"` và `metadataType = "object"`. **Aggregation expression `$type` không tự đi qua từng phần tử của array** để trả ra `["int", "string", "null"]`.

Nếu muốn xem kiểu của từng phần tử, kết hợp `$map` và `$type`:

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-107" } },
  {
    $project: {
      _id: 0,
      elementTypes: {
        $map: {
          input: "$values",
          as: "v",
          in: { $type: "$$v" }
        }
      }
    }
  }
]);
```

Một kết quả:

```javascript
{
  elementTypes: ["int", "string", "null"]
}
```

Cần phân biệt field array không tồn tại/null với array thật: `$map` có quy tắc riêng với null/missing và giá trị không phải array; có thể dùng `$isArray` và `$cond` nếu schema legacy không thống nhất.

## 4. $type trong aggregation khác $type ở query filter

MongoDB có **query operator `$type`** và **aggregation expression `$type`**. Chúng có liên quan nhưng không cùng cú pháp và không phải lúc nào cũng giống hành vi trên array.

### 4.1. Query operator trong $match thường

```javascript
// Tìm document có total thuộc BSON String.
db.typeConversionLab.find({
  total: { $type: "string" }
});
```

Đây là điều kiện của ngôn ngữ query. MongoDB có thể dùng index phù hợp với các loại predicate, tùy truy vấn.

### 4.2. Aggregation expression trong $project

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      totalType: { $type: "$total" }
    }
  }
]);
```

Đây là phép **tính ra tên kiểu** cho mỗi document.

### 4.3. Dùng $expr khi muốn kiểm tra kiểu bằng biểu thức

```javascript
db.typeConversionLab.aggregate([
  {
    $match: {
      $expr: {
        $eq: [{ $type: "$total" }, "string"]
      }
    }
  }
]);
```

Query lọc các document có expression `$type: "$total"` cho ra `"string"`. Khi query chỉ cần kiểm tra một field thuộc kiểu BSON, cú pháp trực tiếp `{ total: { $type: "string" } }` thường dễ đọc hơn; khi cần điều kiện biểu thức phức tạp mới cân nhắc `$expr`.

### 4.4. Khác biệt quan trọng với array

Với document:

```javascript
{
  _id: "array-demo",
  values: [1, "abc"]
}
```

Query predicate:

```javascript
db.typeConversionLab.find({
  values: { $type: "string" }
});
```

có thể khớp document nếu **ít nhất một phần tử array** thuộc kiểu String theo semantics của query operator.

Trong khi đó:

```javascript
{
  $type: "$values"
}
```

trong aggregation trả `"array"` vì giá trị biểu thức là cả array. Không nên áp dụng kết luận “field type là string” từ query array vào aggregation mà không tính đến khác biệt này.

## 5. $convert: cú pháp đầy đủ và kiểm soát lỗi

Cú pháp phổ biến:

```javascript
{
  $convert: {
    input: <expression>,
    to: <targetType>,
    onError: <expression>,
    onNull: <expression>
  }
}
```

Các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `input` | Biểu thức trả giá trị cần chuyển |
| `to` | Kiểu BSON đích: ví dụ `"int"`, `"long"`, `"double"`, `"decimal"`, `"string"`, `"date"`, `"bool"`, `"objectId"` |
| `onError` | Giá trị/biểu thức trả về khi **không thể chuyển đổi** (nếu không khai báo, lỗi có thể dừng pipeline) |
| `onNull` | Giá trị/biểu thức khi input là null hoặc missing (nếu không khai báo, thông thường trả null) |

Những phiên bản MongoDB mới còn hỗ trợ tham số liên quan chuyển đổi BinData như `format`/`byteOrder` và những dạng `to` nâng cao. Khi dùng BinData/UUID hoặc cú pháp phụ thuộc phiên bản, cần kiểm tra tài liệu của **server đang chạy**, thay vì sao chép option từ phiên bản mới hơn.

Ví dụ chuyển `total` sang Decimal128 và không làm pipeline sập vì chuỗi không hợp lệ:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      original: "$total",
      originalType: { $type: "$total" },
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Diễn giải:

- `NumberDecimal("125000.50")` vẫn là giá trị decimal tương ứng.
- Chuỗi `"85000.75"` có thể chuyển sang Decimal128.
- Chuỗi `"không rõ"` không chuyển được, nhưng `onError: null` biến lỗi thành kết quả null.
- `total: null` và field total không tồn tại đều cho kết quả null theo `onNull`.

Điều này giúp **pipeline chạy tiếp** trên dữ liệu bẩn. Nhưng không có nghĩa dữ liệu sai đã được sửa. Nếu bỏ qua những record này khi tính doanh thu mà không ghi log/đối soát, báo cáo có thể thiếu tiền.

### 5.1. onError không giống onNull

Giả sử:

```javascript
{
  $convert: {
    input: "$quantity",
    to: "int",
    onError: "INVALID",
    onNull: "MISSING_OR_NULL"
  }
}
```

Kết quả ý nghĩa:

| Giá trị quantity | Kết quả |
|---|---|
| `NumberInt(2)` | `2` |
| `"3"` | `3` |
| `"3.5"` | `"INVALID"` |
| `null` | `"MISSING_OR_NULL"` |
| Không tồn tại | `"MISSING_OR_NULL"` |

`onError` dùng cho trường hợp **có input nhưng không thể chuyển thành kiểu đích**; `onNull` xử lý **input null hoặc missing**.

Nếu cần phân biệt null với missing, hãy dùng thêm `$type` để ghi trạng thái gốc. `$convert` tự nó không có hai tham số riêng tên `onMissing` và `onNull`.

### 5.2. Fallback là một expression, không chỉ hằng số

Ví dụ giữ thông tin lỗi:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      normalizedQuantity: {
        $convert: {
          input: "$quantity",
          to: "int",
          onError: -1,
          onNull: 0
        }
      }
    }
  }
]);
```

Trên mặt kỹ thuật đây là một cách tạo sentinel, nhưng về nghiệp vụ cần cân nhắc: `-1` và `0` có thể là giá trị hợp lệ. Tốt hơn là trả thêm **trạng thái chuyển đổi** hoặc ghi lỗi vào collection audit/quarantine. Nếu sentinel bị coi như dữ liệu thật, kết quả tổng hợp sẽ sai.

### 5.3. Pipeline dừng khi không có onError

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      quantityInt: {
        $convert: {
          input: "$quantity",
          to: "int"
        }
      }
    }
  }
]);
```

Nếu gặp `quantity: "3.5"`, phép chuyển chuỗi sang int theo định dạng không hợp lệ có thể báo lỗi và **toàn bộ aggregation thất bại**. Không có bảo đảm “trả các document đã chạy trước rồi tự bỏ qua document lỗi” ở mức API tổng hợp theo hợp đồng nghiệp vụ.

Với ETL trên dữ liệu legacy, khai báo `onError` và `onNull` rõ ràng là một phần quan trọng của thiết kế.

## 6. Các toán tử $to*: cú pháp rút gọn

MongoDB cung cấp các shortcut cho nhiều chuyển đổi phổ biến:

| Shortcut | Kiểu đích | Cú pháp |
|---|---|---|
| `$toInt` | BSON Int32 | `{ $toInt: "$quantity" }` |
| `$toLong` | BSON Int64 | `{ $toLong: "$views" }` |
| `$toDouble` | BSON Double | `{ $toDouble: "$ratio" }` |
| `$toDecimal` | Decimal128 | `{ $toDecimal: "$price" }` |
| `$toString` | String | `{ $toString: "$customerId" }` |
| `$toDate` | BSON Date | `{ $toDate: "$orderedAt" }` |
| `$toBool` | Boolean | `{ $toBool: "$active" }` |
| `$toObjectId` | BSON ObjectId | `{ $toObjectId: "$customerId" }` |

Các shortcut trên thường tương đương dạng `$convert` chỉ gồm `input` và `to` tương ứng:

```javascript
{ $toInt: "$quantity" }

{
  $convert: {
    input: "$quantity",
    to: "int"
  }
}
```

Khác biệt quan trọng: các shortcut **không có vị trí khai báo `onError` và `onNull` riêng**. Khi input null/missing, các chuyển đổi thông dụng trả null. Khi gặp giá trị không thể chuyển, lỗi có thể khiến pipeline dừng.

### 6.1. Chọn shortcut khi nào?

Dùng `$to*` khi:

- Schema đã được kiểm soát, input chắc chắn đúng định dạng;
- Dữ liệu đã qua validation và cần biểu thức gọn;
- Lỗi chuyển đổi là hành vi mong muốn để phát hiện dữ liệu bất thường ngay.

Dùng `$convert` khi:

- Dữ liệu đầu vào lẫn kiểu hoặc có giá trị không hợp lệ;
- ETL không được dừng toàn bộ khi một record lỗi;
- Cần default, đánh dấu lỗi hoặc tách bản ghi cần kiểm tra;
- Cần phân biệt nhánh null/missing với nhánh conversion error.

Đừng xem shortcut là “nhanh hơn” chỉ vì cú pháp ngắn. Quyết định chính là **hợp đồng xử lý lỗi**.

## 7. Chuyển đổi sang số nguyên: $toInt và $toLong

### 7.1. $toInt

Ví dụ:

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-102" } },
  {
    $project: {
      quantityOriginal: "$quantity",
      quantityInt: { $toInt: "$quantity" }
    }
  }
]);
```

Với `quantity: "3"`, kết quả có `quantityInt` kiểu BSON Int32 giá trị 3.

Một số quy tắc quan trọng:

- Chuỗi phải có dạng số nguyên hợp lệ; `"3"` hợp lệ, nhưng chuỗi thập phân `"3.5"` không thể tùy tiện chuyển bằng `$toInt`.
- Từ số thực sang integer, phép chuyển có thể **cắt phần thập phân về phía 0** khi giá trị nằm trong giới hạn kiểu đích. Đây là chuyển đổi kiểu, không phải làm tròn theo nghiệp vụ.
- Giá trị nằm ngoài miền Int32 gây lỗi.
- Null hoặc missing thường trả null.
- Giá trị không hỗ trợ chuyển sang integer có thể báo lỗi.

Ví dụ kiểm tra có fallback:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      quantityInt: {
        $convert: {
          input: "$quantity",
          to: "int",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Nếu nghiệp vụ yêu cầu nguyên dương, chuyển sang int **chưa đủ**; cần ràng buộc thêm `quantityInt > 0`, và có thể kiểm tra rằng input không chứa phần thập phân mà thao tác cắt bỏ làm mất.

### 7.2. Phạm vi Int32

Int32 lưu số nguyên từ:

```text
-2,147,483,648 đến 2,147,483,647
```

Với chuỗi:

```javascript
{ quantity: "9000000000" }
```

`$toInt` không biểu diễn được vì vượt phạm vi Int32. Có thể dùng `$toLong` nếu đây là số nguyên 64-bit phù hợp:

```javascript
{
  $toLong: "$quantity"
}
```

### 7.3. $toLong và giới hạn Int64

Int64 hỗ trợ:

```text
-9,223,372,036,854,775,808
đến
 9,223,372,036,854,775,807
```

`$toLong` phù hợp với counter lớn, timestamp dạng mili-giây hoặc ID số trong phạm vi tương ứng.

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-106" } },
  {
    $project: {
      originalType: { $type: "$total" },
      totalLong: { $toLong: "$total" },
      longType: { $type: { $toLong: "$total" } }
    }
  }
]);
```

Tránh chuyển Int64 lớn qua JavaScript `Number` hoặc BSON Double nếu cần giữ **từng đơn vị chính xác**. Double có giới hạn độ chính xác nguyên tuyệt đối theo IEEE 754; với những giá trị đủ lớn, biểu diễn có thể mất đơn vị thấp.

### 7.4. Cắt phần thập phân không phải quy tắc làm tròn tiền

Giả sử có:

```javascript
{ units: 3.9 }
```

Việc chuyển sang số nguyên có thể cho kết quả 3 theo quy tắc truncate. Nếu đơn hàng phải làm tròn lên thành 4, phải dùng phép toán có ngữ nghĩa như `$ceil`, `$floor` hoặc `$round` rồi mới chuyển kiểu, không dựa vào `$toInt` thay cho quy tắc nghiệp vụ.

Ví dụ:

```javascript
db.lineItems.aggregate([
  {
    $project: {
      billedUnits: {
        $toInt: { $ceil: "$requestedUnits" }
      }
    }
  }
]);
```

Ví dụ giả định requestedUnits là numeric hợp lệ, không chứa null hoặc các giá trị ngoài phạm vi Int32.

## 8. Chuyển đổi sang Double và Decimal128

### 8.1. $toDouble

```javascript
db.metrics.aggregate([
  {
    $project: {
      responseSeconds: {
        $toDouble: "$responseSecondsRaw"
      }
    }
  }
]);
```

Các chuỗi số hợp lệ có thể chuyển sang Double. Nhưng Double sử dụng biểu diễn dấu phẩy động nhị phân, không thể biểu diễn chính xác mọi số thập phân.

Đặc biệt, các giá trị tiền như `0.1` và `0.2` có thể tạo sai số nhị phân khi tính toán. Không nên dùng Double cho số tiền cần chính xác theo số chữ số thập phân được quy định, trừ khi hệ thống đã có mô hình làm tròn và sai số chấp nhận rõ ràng.

### 8.2. $toDecimal

Với giá tiền:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      priceDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Decimal128 lưu số thập phân với độ chính xác hữu hạn theo chuẩn decimal, phù hợp với nhiều nghiệp vụ tiền tệ cần biểu diễn cơ số 10.

Ví dụ tính thuế từ giá đã chuẩn hóa:

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $match: {
      totalDecimal: { $ne: null }
    }
  },
  {
    $project: {
      _id: 1,
      totalDecimal: 1,
      tax: {
        $multiply: [
          "$totalDecimal",
          NumberDecimal("0.10")
        ]
      }
    }
  }
]);
```

Ví dụ tính 10% thuế minh họa phép nhân, không phản ánh quy tắc thuế của một quốc gia hoặc yêu cầu làm tròn tiền cụ thể.

### 8.3. Dữ liệu có định dạng theo địa phương

`$toDecimal` và `$toDouble` không mặc nhiên hiểu mọi định dạng số theo locale.

Ví dụ các chuỗi:

```text
"1250.50"      // Dạng thập phân với dấu chấm
"1,250.50"     // Có dấu tách hàng nghìn
"1.250,50"     // Quy ước ở một số locale
"1 250,50"     // Có khoảng trắng và dấu phẩy
"1250 VND"     // Có đơn vị tiền
```

Không nên chỉ áp dụng `$toDecimal` lên toàn bộ mà kỳ vọng đều hợp lệ hoặc cho cùng giá trị. Cần xác định **nguồn dữ liệu/locale**, làm sạch theo một quy tắc được kiểm chứng rồi mới chuyển kiểu. Thay toàn bộ dấu phẩy bằng dấu chấm một cách máy móc có thể biến `"1,250.50"` thành chuỗi sai định dạng.

Một pipeline ETL chất lượng nên giữ giá trị gốc, tên nguồn, trạng thái parse và số lượng record bị lỗi để đối soát.

### 8.4. Chuyển từ Double sang Decimal không phục hồi độ chính xác đã mất

Nếu một số tiền đã được lưu như Double và từng bị mất độ chính xác, việc chạy:

```javascript
{ $toDecimal: "$priceDouble" }
```

không thể tự phục hồi **giá trị tiền chính xác ban đầu** mà hệ thống đã bỏ mất. Chuyển kiểu chỉ dựa trên giá trị thực sự đang lưu. Với dữ liệu cần tính toán tài chính, nên chuẩn hóa ngay từ lúc nhập và tránh tuyến chuyển đổi qua Double không cần thiết.

## 9. Chuyển đổi sang String: $toString

`$toString` thường hữu ích khi chuẩn hóa một mã định danh để xuất dữ liệu, làm khóa nối chuỗi hoặc tạo display label:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      customerIdText: {
        $convert: {
          input: "$customerId",
          to: "string",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Với BSON ObjectId hợp lệ, chuyển sang String thường cho biểu diễn hex 24 ký tự. Với chuỗi đầu vào, giá trị chuỗi được giữ phù hợp.

Ví dụ nối label:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      label: {
        $concat: [
          "Order ",
          { $toString: "$_id" }
        ]
      }
    }
  }
]);
```

`_id` trong dataset thực hành là String, nên lệnh hoạt động đơn giản. Nếu document có ID là kiểu khác, cần kiểm tra khả năng chuyển và cách hiển thị.

### 9.1. Không phải BSON type nào cũng chuyển thành String

Đừng mặc định có thể áp dụng `$toString` cho array hoặc embedded document và nhận được chuỗi JSON hoàn chỉnh:

```javascript
{
  details: { a: 1, b: 2 },
  values: [1, 2, 3]
}
```

Các kiểu phức tạp có thể không được chuyển trực tiếp bằng `$toString` theo cơ chế chuyển đổi thông thường. Nếu mục tiêu là JSON serialization, đó là chức năng ở driver/ứng dụng hoặc một pipeline được thiết kế tương ứng, **không phải lời hứa của `$toString`**.

### 9.2. Chuyển ID sang String và vấn đề $lookup

Nếu collection `orders.customerId` chứa ObjectId còn `customers._id` chứa ObjectId, join nên dùng đúng kiểu ObjectId ở cả hai phía. Nếu một collection lưu String ID, một collection lưu ObjectId, việc không đồng nhất kiểu có thể khiến equality join không khớp như mong muốn.

Có thể chuyển tạm trong aggregation, nhưng chuẩn hóa schema là hướng bền vững hơn. Việc tính toán chuyển đổi field ở thời gian truy vấn có thể làm giảm khả năng tận dụng index hoặc làm join phức tạp hơn.

## 10. Chuyển đổi sang ObjectId: $toObjectId

ObjectId là kiểu BSON định danh phổ biến của MongoDB. Một chuỗi **24 ký tự hex hợp lệ** có thể chuyển sang ObjectId.

```javascript
db.typeConversionLab.aggregate([
  { $match: { _id: "O-102" } },
  {
    $project: {
      _id: 1,
      original: "$customerId",
      customerObjectId: {
        $toObjectId: "$customerId"
      }
    }
  }
]);
```

Với giá trị `"65a12f010000000000000002"`, biểu thức có thể tạo BSON ObjectId tương ứng.

### 10.1. Chuỗi sai định dạng gây lỗi

Với O-103:

```javascript
{ customerId: "không phải objectId" }
```

Dùng:

```javascript
{ $toObjectId: "$customerId" }
```

có thể làm aggregation thất bại vì chuỗi không đúng định dạng.

Hãy dùng `$convert` nếu dữ liệu legacy có thể sai:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      originalCustomerId: "$customerId",
      parsedCustomerId: {
        $convert: {
          input: "$customerId",
          to: "objectId",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Nếu parse thất bại, parsedCustomerId thành null; có thể ghi thêm status theo type gốc hoặc đưa record vào luồng xử lý lỗi.

### 10.2. ObjectId không phải bất kỳ chuỗi định danh nào

Ví dụ các giá trị:

```text
"user-1234"             // String nghiệp vụ, không phải ObjectId
"65a12f010000000000000001" // Chuỗi hex 24 ký tự, có thể parse ObjectId
"65a12f01000000000000000Z" // Có ký tự Z, không phải hex hợp lệ
```

Không nên ép một String ID nghiệp vụ thành ObjectId chỉ vì MongoDB thường dùng ObjectId cho `_id`. Collection có thể được thiết kế với `_id` kiểu String hoặc UUID theo hợp đồng riêng.

### 10.3. Ví dụ sửa lỗi $lookup do sai kiểu

Giả sử `legacyOrders.customerId` là chuỗi hex, `customers._id` là ObjectId. Có thể chuẩn hóa trong aggregation:

```javascript
db.legacyOrders.aggregate([
  {
    $set: {
      customerObjectId: {
        $convert: {
          input: "$customerId",
          to: "objectId",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $lookup: {
      from: "customers",
      localField: "customerObjectId",
      foreignField: "_id",
      as: "customer"
    }
  },
  {
    $project: {
      orderNo: 1,
      customerId: 1,
      customer: 1
    }
  }
]);
```

Điều này xử lý đúng kiểu để join, nhưng còn phải xem query planner, lượng dữ liệu cần convert và khả năng tận dụng index. Việc migrate String hex sang ObjectId thật trong schema thường làm các truy vấn sau đó đơn giản hơn; cần chuẩn bị kế hoạch update, rollback và xử lý dữ liệu không hợp lệ.

## 11. Chuyển đổi sang Date: $toDate

BSON Date dùng để biểu diễn một **thời điểm**. `$toDate` có thể chuyển một số loại input hợp lệ sang Date, như chuỗi ngày đúng định dạng, số mili-giây tính từ Unix epoch hoặc BSON ObjectId (theo phần timestamp của ID).

Ví dụ:

```javascript
db.typeConversionLab.aggregate([
  {
    $project: {
      _id: 1,
      originalType: { $type: "$orderedAt" },
      parsedDate: {
        $convert: {
          input: "$orderedAt",
          to: "date",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

- O-101: Date hợp lệ được giữ theo kiểu Date.
- O-102: chuỗi ISO với `Z` có thể chuyển thành Date.
- O-103: chuỗi `"ngày hôm qua"` không phải ngày hợp lệ theo phép chuyển, nên nhánh onError trả null.
- O-104/O-105: null/missing trả nhánh onNull.

### 11.1. Number khi chuyển thành Date là milliseconds

Ví dụ:

```javascript
db.epochLab.insertMany([
  {
    _id: 1,
    timestampMillis: NumberLong("0")
  },
  {
    _id: 2,
    timestampMillis: NumberLong("86400000")
  }
]);

db.epochLab.aggregate([
  {
    $project: {
      _id: 1,
      asDate: { $toDate: "$timestampMillis" }
    }
  }
]);
```

Về ý nghĩa:

- `0` milliseconds kể từ Unix epoch tương ứng 1970-01-01T00:00:00Z.
- `86400000` milliseconds tương ứng sau 24 giờ, 1970-01-02T00:00:00Z.

**Rủi ro phổ biến:** hệ thống nguồn cung cấp epoch **seconds**, nhưng ứng dụng chuyển trực tiếp bằng `$toDate` và nhận ngày năm 1970 thay vì mốc hiện đại. Khi nguồn dữ liệu lưu seconds, cần chuyển sang milliseconds bằng phép nhân `1000` có kiểm soát:

```javascript
db.epochSeconds.aggregate([
  {
    $project: {
      eventAt: {
        $toDate: {
          $multiply: [
            { $toLong: "$eventSeconds" },
            NumberLong("1000")
          ]
        }
      }
    }
  }
]);
```

Ví dụ giả định eventSeconds là số nguyên hợp lệ, nằm trong giới hạn khi nhân và đơn vị thực sự là seconds.

### 11.2. ObjectId có timestamp nhưng không phải thời gian nghiệp vụ tuyệt đối

`$toDate` trên ObjectId có thể dùng timestamp được mã hóa trong ObjectId. Nhưng ObjectId có thể được tạo tại client, độ phân giải thời gian có giới hạn và không bảo đảm là thời điểm transaction commit hay thời gian sự kiện nghiệp vụ.

Không nên dùng ngày rút từ ObjectId thay cho `createdAt` nếu nghiệp vụ yêu cầu thời gian chính xác do server/application ghi theo hợp đồng.

### 11.3. Chuỗi ngày và timezone

Các chuỗi như:

```text
"2026-03-01T09:30:00Z"
"2026-03-01"
"01/03/2026"
"03/01/2026"
```

không cùng mức rõ ràng. ISO 8601 có timezone như `Z` hoặc offset là lựa chọn tốt khi biểu diễn thời điểm. Chuỗi `"01/03/2026"` có thể mơ hồ giữa ngày 1 tháng 3 và ngày 3 tháng 1.

Nếu cần parse định dạng tùy chỉnh hoặc timezone được quy định riêng, hãy dùng `$dateFromString` với `format`, `timezone`, `onError` và `onNull` khi phù hợp:

```javascript
db.legacyOrders.aggregate([
  {
    $project: {
      legacyDate: 1,
      parsedAt: {
        $dateFromString: {
          dateString: "$legacyDate",
          format: "%d/%m/%Y %H:%M:%S",
          timezone: "Asia/Ho_Chi_Minh",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Ở đây `$dateFromString` diễn giải chuỗi theo định dạng ngày/tháng/năm và timezone được chỉ định. Không tùy tiện truyền thêm `timezone` nếu chuỗi đầu vào đã mang timezone theo cách xung đột với biểu thức. Khi chỉ cần chuyển String ISO hợp lệ, `$toDate` hoặc `$convert` là ngắn gọn hơn.

## 12. Chuyển đổi sang Boolean: $toBool có thể gây bất ngờ

Trong nhiều hệ thống, dữ liệu legacy có:

```javascript
{ isActive: "true" }
{ isActive: "false" }
{ isActive: 0 }
{ isActive: 1 }
{ isActive: "" }
{ isActive: null }
```

Có thể bạn kỳ vọng `$toBool: "false"` sẽ cho false. Nhưng **không nên suy nghĩ theo parse chuỗi ngôn ngữ tự nhiên**.

Quy tắc chuyển Boolean thường gặp:

- Giá trị số bằng 0 → `false`;
- Giá trị số khác 0 → `true`;
- Boolean giữ ý nghĩa tương ứng;
- Null/missing → `null`;
- Những giá trị non-null thuộc các kiểu khác, **bao gồm String rỗng và chuỗi `"false"`**, thường chuyển thành `true` theo semantics của `$toBool`.

Ví dụ:

```javascript
db.boolLab.insertMany([
  { _id: "A", raw: false },
  { _id: "B", raw: true },
  { _id: "C", raw: 0 },
  { _id: "D", raw: 5 },
  { _id: "E", raw: "false" },
  { _id: "F", raw: "" },
  { _id: "G", raw: null },
  { _id: "H" }
]);

db.boolLab.aggregate([
  {
    $project: {
      _id: 1,
      original: "$raw",
      rawType: { $type: "$raw" },
      converted: { $toBool: "$raw" }
    }
  }
]);
```

Phần quan trọng là E và F **không** được parse theo nội dung chuỗi để thành false.

### 12.1. Parse chuỗi true/false một cách có chủ đích

Nếu nguồn chỉ chấp nhận String `"true"`, `"false"` hoặc Boolean, hãy xây biểu thức xác minh giá trị:

```javascript
db.boolLab.aggregate([
  {
    $project: {
      _id: 1,
      normalizedActive: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$raw", true] },
              then: true
            },
            {
              case: { $eq: ["$raw", false] },
              then: false
            },
            {
              case: { $eq: ["$raw", "true"] },
              then: true
            },
            {
              case: { $eq: ["$raw", "false"] },
              then: false
            }
          ],
          default: null
        }
      }
    }
  }
]);
```

Nếu nguồn chấp nhận `"TRUE"`, `"False"` hoặc khoảng trắng, có thể chuẩn hóa String bằng các biểu thức chuỗi phù hợp trước khi so sánh, nhưng cần **kiểm tra kiểu** để không gọi phép toán String lên Boolean/Number không hợp lệ.

Không dùng `$toBool` để “đọc hiểu” các chuỗi giống ngôn ngữ người dùng nếu yêu cầu nghiệp vụ là parse đúng true/false.

## 13. Xây pipeline chuẩn hóa mà vẫn giữ dấu vết lỗi

Một pipeline ETL có chất lượng không chỉ ép kiểu. Nó nên trả:

- Giá trị gốc;
- Kiểu BSON gốc;
- Giá trị đã chuyển;
- Trạng thái **valid/invalid/missing/null**;
- Nguồn dữ liệu hoặc ID để đối soát.

Ví dụ kiểm tra `total` trong `typeConversionLab`:

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      originalTotalType: { $type: "$total" },
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      totalStatus: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$originalTotalType", "missing"]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: ["$originalTotalType", "null"]
              },
              then: "NULL"
            },
            {
              case: {
                $eq: ["$totalDecimal", null]
              },
              then: "INVALID"
            }
          ],
          default: "VALID"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      total: 1,
      originalTotalType: 1,
      totalDecimal: 1,
      totalStatus: 1
    }
  }
]);
```

Ưu điểm:

- Chuỗi số hợp lệ được chuyển;
- Chuỗi sai không phá cả pipeline;
- Field null khác field missing ở trạng thái đầu ra;
- Khi `totalDecimal` là null do conversion error, `totalStatus` phản ánh `INVALID`;
- Không xóa thông tin gốc trước khi đối soát.

Nếu schema có các giá trị Decimal128 NaN, Infinity hoặc các giá trị đặc biệt được MongoDB chấp nhận ở những phép chuyển, nghiệp vụ còn cần **kiểm tra tính hữu hạn và miền giá trị**; “chuyển kiểu thành công” không đồng nghĩa “giá hợp lệ”.

### 13.1. Đếm số document theo chất lượng dữ liệu

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      originalType: { $type: "$total" },
      normalized: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      status: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$originalType", "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: ["$originalType", "null"] },
              then: "NULL"
            },
            {
              case: { $eq: ["$normalized", null] },
              then: "INVALID"
            }
          ],
          default: "VALID"
        }
      }
    }
  },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Thống kê như vậy giúp lập kế hoạch migration theo quy mô lỗi thực tế, thay vì chỉ biết một aggregate tổng doanh thu bị sai.

## 14. Tính tổng chỉ trên các giá trị đã được chuyển hợp lệ

Giả sử muốn tính tổng `total` với dữ liệu hỗn hợp.

Một cách an toàn hơn cho báo cáo là tách giá trị chuyển hợp lệ ra trước:

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $match: {
      totalDecimal: { $ne: null }
    }
  },
  {
    $group: {
      _id: null,
      totalRevenue: {
        $sum: "$totalDecimal"
      },
      includedCount: { $sum: 1 }
    }
  }
]);
```

Lệnh này tính tổng các giá trị chuyển thành Decimal128 được và đếm số document tham gia.

**Cảnh báo về diễn giải:** Những record invalid/missing/null đã bị bỏ qua. Nếu báo cáo tài chính cần bao gồm mọi đơn hàng, phải xử lý hoặc báo rõ số record bị loại, không được ghi kết quả là “doanh thu toàn bộ” khi dữ liệu nguồn chưa đầy đủ.

### 14.1. Không che lỗi bằng giá trị 0 nếu 0 có nghĩa nghiệp vụ

Thao tác:

```javascript
{
  $convert: {
    input: "$total",
    to: "decimal",
    onError: NumberDecimal("0"),
    onNull: NumberDecimal("0")
  }
}
```

sẽ làm mọi giá trị lỗi/null trở thành tiền bằng 0. Điều này đôi khi là yêu cầu hợp lệ (ví dụ một phép thống kê có quy ước thiếu là 0), nhưng trong doanh thu, nó thường **che giấu lỗi**.

Nên tách giá trị chuẩn hóa và trạng thái hợp lệ, sau đó chỉ chọn default 0 khi nghiệp vụ chính thức định nghĩa như vậy.

## 15. Chuyển đổi array với $map, không ép toàn bộ array thành Number

Giả sử collection lưu dãy số dưới dạng String:

```javascript
db.measurements.insertOne({
  _id: "M-01",
  rawValues: ["10.5", "12.25", "bad", null, "15"]
});
```

Nếu muốn chuyển từng phần tử:

```javascript
db.measurements.aggregate([
  {
    $project: {
      convertedValues: {
        $map: {
          input: "$rawValues",
          as: "value",
          in: {
            $convert: {
              input: "$$value",
              to: "double",
              onError: null,
              onNull: null
            }
          }
        }
      }
    }
  }
]);
```

Kết quả về ý nghĩa:

```javascript
{
  _id: "M-01",
  convertedValues: [10.5, 12.25, null, null, 15]
}
```

Một lỗi phổ biến là áp dụng `$toDouble: "$rawValues"` trực tiếp trên cả array. Nó không có nghĩa tự map từng phần tử sang Double. Hãy dùng `$map`.

### 15.1. Giữ đồng thời giá trị gốc và trạng thái parse

```javascript
db.measurements.aggregate([
  {
    $project: {
      parsed: {
        $map: {
          input: "$rawValues",
          as: "v",
          in: {
            original: "$$v",
            originalType: { $type: "$$v" },
            asDouble: {
              $convert: {
                input: "$$v",
                to: "double",
                onError: null,
                onNull: null
              }
            }
          }
        }
      }
    }
  }
]);
```

Kết quả cho từng phần tử là một object gồm giá trị gốc, kiểu gốc và kết quả chuyển. Nếu có phần tử invalid, ứng dụng dễ chỉ ra vị trí lỗi thay vì chỉ thấy null không có ngữ cảnh.

### 15.2. $map với field không phải array

Nếu `rawValues` có lúc là String hoặc Object, `$map` có thể lỗi. Dùng `$isArray` trước:

```javascript
db.measurements.aggregate([
  {
    $project: {
      parsed: {
        $cond: {
          if: { $isArray: "$rawValues" },
          then: {
            $map: {
              input: "$rawValues",
              as: "v",
              in: {
                $convert: {
                  input: "$$v",
                  to: "double",
                  onError: null,
                  onNull: null
                }
              }
            }
          },
          else: []
        }
      }
    }
  }
]);
```

Mặc định `[]` trong ví dụ chỉ là một chính sách fallback minh họa. Trong ETL cần phân biệt “array rỗng hợp lệ” với “kiểu sai” nếu điều này ảnh hưởng báo cáo.

## 16. Chuyển đổi kiểu ngay trong $match với $expr

Có lúc cần lọc các document có giá trị String có thể biểu diễn số lớn hơn 100:

```javascript
db.legacyPrices.aggregate([
  {
    $set: {
      parsedPrice: {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $match: {
      parsedPrice: {
        $gt: NumberDecimal("100")
      }
    }
  }
]);
```

Hoặc dùng `$expr`:

```javascript
db.legacyPrices.find({
  $expr: {
    $gt: [
      {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      NumberDecimal("100")
    ]
  }
});
```

Hai cách đều biểu diễn “chuyển giá trị trước khi so sánh”, nhưng cần hiểu rằng query đã trở thành **tính toán trên dữ liệu gốc**.

### 16.1. Ảnh hưởng đến index

Giả sử có B-tree index:

```javascript
db.legacyPrices.createIndex({ price: 1 });
```

Index này sắp xếp theo **BSON value gốc**, không theo giá trị Decimal128 sau phép chuyển. Nếu dữ liệu chứa `price: "100"`, `price: "9"` và `price: "200"`, thứ tự String không giống thứ tự Number.

Vì vậy, điều kiện:

```javascript
{
  $expr: {
    $gt: [
      { $toDecimal: "$price" },
      NumberDecimal("100")
    ]
  }
}
```

**không tự trở thành range scan hiệu quả trên index `{ price: 1 }`**. MongoDB có thể phải đọc và tính biểu thức trên nhiều document. Một số biểu thức `$expr` có thể có tối ưu index nhất định theo query shape/version, nhưng không nên giả định phép `$convert` của field sẽ tận dụng được index gốc như thể field đã là Decimal128.

Giải pháp bền vững cho query thường xuyên:

1. Chuẩn hóa field tại **write path**;
2. Migration dữ liệu cũ sang field có kiểu thống nhất;
3. Tạo index trên field chuẩn hóa;
4. Dùng filter trực tiếp trên field chuẩn hóa.

Ví dụ schema sau migration:

```javascript
{
  _id: "P-101",
  priceRaw: "125.50",
  priceDecimal: NumberDecimal("125.50")
}
```

Index:

```javascript
db.products.createIndex({ priceDecimal: 1 });
```

Query:

```javascript
db.products.find({
  priceDecimal: { $gt: NumberDecimal("100") }
});
```

Đây là cách tránh phải parse toàn bộ dữ liệu trong mỗi request đọc.

### 16.2. Dùng pre-filter nhưng không đổi semantics

Nếu dữ liệu hỗn hợp, một bước filter theo kiểu có thể giảm số record cần convert:

```javascript
db.legacyPrices.aggregate([
  {
    $match: {
      price: { $type: "string" }
    }
  },
  {
    $set: {
      priceDecimal: {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Nhưng lệnh trên **loại toàn bộ giá trị price vốn đã là Number/Decimal128**. Vì vậy, nó chỉ đúng nếu mục tiêu thật sự là xử lý riêng field String. Không được thêm pre-filter để tối ưu nếu nó làm bỏ sót dữ liệu hợp lệ theo yêu cầu nghiệp vụ.

## 17. Chuẩn hóa dữ liệu khi ghi và migration

Chuyển đổi trong aggregation **không tự thay đổi document lưu trữ**. Một pipeline:

```javascript
db.typeConversionLab.aggregate([
  {
    $set: {
      totalDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

chỉ tạo/biến đổi trường trong kết quả của pipeline; document gốc không có `totalDecimal` mới trừ khi dùng thao tác ghi phù hợp.

### 17.1. Update với aggregation pipeline

MongoDB hỗ trợ update pipeline để chuyển và lưu field đã chuẩn hóa:

```javascript
db.typeConversionLab.updateMany(
  {},
  [
    {
      $set: {
        totalDecimal: {
          $convert: {
            input: "$total",
            to: "decimal",
            onError: null,
            onNull: null
          }
        }
      }
    }
  ]
);
```

**Thận trọng:** lệnh này có thể tạo `totalDecimal: null` trên các record không hợp lệ/missing. Nếu policy yêu cầu đưa record lỗi sang quarantine thay vì ghi null, cần chia batch và điều kiện phù hợp.

Ví dụ chỉ chuyển các String numeric parse được nhưng không phá dữ liệu gốc là một quy trình migration có nhiều bước:

1. Đọc và thống kê `$type` của field;
2. Thử `$convert` với onError/onNull để nhận diện dữ liệu lỗi;
3. Ghi danh sách record cần sửa/chủ sở hữu xử lý;
4. Chạy update batch có filter rõ trên tập hợp đủ điều kiện;
5. Kiểm tra số record bị ảnh hưởng và đối soát tổng số;
6. Bật schema validation/write-path normalization để không tái phát.

Theo hợp đồng bài học, đây là **ví dụ** quy trình, không phải hướng dẫn chạy update toàn bộ production mà không backup/migration plan.

### 17.2. $merge và $out cần được hiểu là ghi dữ liệu

Aggregation thuần như `$project`/`$set` chỉ tạo output. Nhưng stage `$merge` hoặc `$out` có thể **ghi kết quả vào collection đích**. Khi thiết kế ETL, cần phân biệt pipeline chỉ đọc với pipeline có side effect, quyết định policy upsert/replace và giới hạn quyền.

Không thêm `$merge` vào một pipeline khám phá dữ liệu nếu chưa xác định rõ collection đích, uniqueness, cách xử lý lỗi và rollback.

### 17.3. Validation sau migration

Sau khi chuẩn hóa:

- Một field tiền nên thống nhất BSON Decimal128 hoặc integer theo đơn vị tiền nhỏ nhất;
- Field ngày nên thống nhất BSON Date;
- Field định danh nên thống nhất ObjectId/String theo schema;
- Field số lượng nên là Int32/Int64 trong miền giá trị cho phép;
- Field Boolean nên có Boolean thật, không chứa String `"false"`;
- Null/missing cần quy tắc rõ.

MongoDB JSON Schema validator và validation phía ứng dụng có thể ngăn những thao tác ghi sai kiểu. Tuy nhiên, các hệ thống import và job nền cũng phải tuân thủ cùng schema, tránh để API web đúng nhưng ETL tiếp tục ghi dữ liệu lệch kiểu.

## 18. Dùng trong Java và Spring Data MongoDB

Một ứng dụng Java có thể lưu số tiền bằng `BigDecimal` (ánh xạ thành Decimal128 theo cấu hình phù hợp), thời gian bằng kiểu thời gian Java thích hợp và định danh bằng `ObjectId`. Nhưng dữ liệu legacy có thể đã được ghi qua nhiều client, nên vẫn cần aggregation để chuẩn hóa.

### 18.1. MongoDB Java Driver: dựng stage bằng Document

Ví dụ xây pipeline kiểm tra và chuyển giá:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

MongoCollection<Document> orders =
    database.getCollection("typeConversionLab");

Document conversion = new Document(
    "$convert",
    new Document("input", "$total")
        .append("to", "decimal")
        .append("onError", null)
        .append("onNull", null)
);

Document projection = new Document(
    "$project",
    new Document("_id", 1)
        .append("originalType",
            new Document("$type", "$total"))
        .append("totalDecimal", conversion)
);

List<Document> pipeline = Arrays.asList(projection);

for (Document result : orders.aggregate(pipeline)) {
    System.out.println(result.toJson());
}
```

Ví dụ dùng `Document` trực tiếp để làm rõ JSON/BSON expression. Java Driver còn có các builders cho aggregation, nhưng khả năng hỗ trợ từng expression/option phụ thuộc phiên bản driver. Khi triển khai thật, nên dùng helper/abstraction thống nhất để tránh gõ nhầm tên operator ở nhiều nơi.

### 18.2. Kiểu trả về ở Java cần được kiểm soát

Ngay cả khi MongoDB trả BSON Decimal128 đúng, code Java có thể đọc ra wrapper `Decimal128` hoặc đối tượng được mapping theo cấu hình. Không nên tự ép mọi giá trị về `double` rồi lưu sang `BigDecimal` nếu cần giữ chính xác tiền tệ.

Tương tự, BSON Date biểu diễn mốc thời gian; code Java cần xử lý timezone và cách biểu diễn nhất quán. Định dạng ngày để hiển thị khác việc lưu trữ một instant.

### 18.3. Spring Data MongoDB

Spring Data MongoDB có DSL cho aggregation, projection, conversion hoặc custom expression theo phiên bản. Có thể dùng biểu thức raw khi API thiếu builder tương ứng, nhưng cần kiểm tra tên field đã được mapping và kiểu output trong DTO.

Đối với read model, nên dùng DTO có kiểu rõ:

```java
public record NormalizedOrder(
    String id,
    java.math.BigDecimal total,
    java.time.Instant orderedAt,
    String validationStatus
) {}
```

Đây là ví dụ kiểu đối tượng của tầng ứng dụng. Mapping từ BSON ObjectId/Decimal128/Date sang DTO phụ thuộc serializer và cấu hình; không mặc nhiên coi mã Java trên sẽ tự map mọi field nếu source còn sai kiểu.

## 19. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ `$type` tự chuyển giá trị | Chỉ nhận tên BSON type | Dùng `$convert` hoặc shortcut |
| Coi `"123"` như BSON Number | Phép toán số có thể lỗi hoặc khác ngữ nghĩa | Chuyển số có chủ đích |
| Nhầm null với missing | Không nhận diện lỗi dữ liệu legacy | Kết hợp `$type` |
| Dùng `$toInt` trên chuỗi `"3.5"` | Pipeline lỗi | Dùng `$convert onError` hoặc parse đúng quy tắc |
| Dùng `$toInt` để làm tròn | Có thể truncate thay vì round | Dùng `$ceil`/`$floor`/`$round` theo nghiệp vụ |
| Chuyển Int64 lớn sang Double | Mất độ chính xác nguyên | Giữ Int64/Decimal128 |
| Dùng Double cho tiền cần chính xác | Sai số nhị phân | Decimal128 hoặc integer đơn vị tiền |
| Dùng `$toBool` trên `"false"` | Có thể nhận true | Parse chuỗi bằng `$switch`/so sánh |
| Dùng `$toDate` với epoch seconds | Sai mốc thời gian | Nhân thành milliseconds trước |
| Dùng chuỗi ngày mơ hồ | Parse không đúng locale/timezone | `$dateFromString` với format/timezone |
| Dùng `$toObjectId` trên user ID tùy ý | Lỗi vì không phải hex 24 ký tự | Giữ String ID hoặc convert có onError |
| Chuyển cả array bằng `$toDouble` | Không tự map phần tử | Dùng `$map` |
| Đặt `onError: 0` cho doanh thu | Che giấu record không hợp lệ | Ghi trạng thái lỗi và đối soát |
| Dùng `$expr + $convert` cho mọi truy vấn | Có thể giảm hiệu quả index | Chuẩn hóa schema, tạo index trên field chuẩn |
| Nghĩ `$set` trong aggregation tự lưu vào DB | Chỉ biến đổi kết quả pipeline | Update pipeline hoặc write stage có kiểm soát |
| Nghĩ chuyển đổi thành công = dữ liệu hợp lệ | Vẫn có thể ngoài miền, âm tiền, sai logic | Validation nghiệp vụ sau convert |

## 20. Bài tập thực hành

### Bài 1 — Khảo sát kiểu của dữ liệu legacy

Trên `typeConversionLab`:

1. Dùng `$project` và `$type` để hiển thị kiểu của `total`, `quantity` và `orderedAt`.
2. Phân biệt `"null"` với `"missing"`.
3. Dùng `$group` để đếm số document có từng kiểu `total`.
4. Giải thích vì sao `"85000.75"` và `"không rõ"` có cùng kiểu nhưng khác khả năng chuyển đổi.

### Bài 2 — Chuyển quantity sang số nguyên

Hãy thử:

```javascript
{ $toInt: "$quantity" }
```

và:

```javascript
{
  $convert: {
    input: "$quantity",
    to: "int",
    onError: null,
    onNull: null
  }
}
```

So sánh hành vi khi quantity là `2`, `"3"`, `"3.5"`, `null` và missing. Giải thích tại sao một pipeline có thể lỗi toàn bộ trong khi pipeline kia trả kết quả có null.

### Bài 3 — Tính doanh thu sau chuẩn hóa

Dùng `$convert to "decimal"` để tạo `totalDecimal`. Viết pipeline:

1. Giữ nguyên giá trị total gốc.
2. Gắn totalStatus = VALID/INVALID/NULL/MISSING.
3. Tính tổng chỉ các giá trị VALID.
4. Đếm số document INVALID và MISSING riêng.
5. Đề xuất cách không để báo cáo bị hiểu nhầm là đã tính đủ toàn bộ đơn hàng.

### Bài 4 — Ngày giờ, timezone và epoch

Dữ liệu:

```javascript
[
  { _id: 1, rawTime: "2026-03-01T08:30:00Z" },
  { _id: 2, rawTime: NumberLong("1772353800000") },
  { _id: 3, rawTime: "01/03/2026 15:30:00" },
  { _id: 4, rawTime: "yesterday" }
]
```

Hãy:

1. Dùng `$convert to "date"` có onError/onNull.
2. Chọn giải pháp parse chuỗi dd/MM/yyyy HH:mm:ss ở timezone `Asia/Ho_Chi_Minh`.
3. Giải thích cách phân biệt epoch seconds và milliseconds.
4. Nêu vì sao chuỗi ngày thiếu timezone có thể dẫn đến sai giờ khi lưu.

### Bài 5 — Chuyển mã khách hàng

Có `customerId` dạng ObjectId, String hex hợp lệ, String không hợp lệ và null. Dùng `$type` để phân loại, `$convert to "objectId"` để chuyển an toàn. Viết aggregation `$lookup` với collection `customers` có `_id` là ObjectId. Phân tích tác động đến index và lý do nên migration schema về cùng kiểu.

### Bài 6 — Hiểu đúng $toBool

Dự đoán kết quả của:

```javascript
[
  { raw: false },
  { raw: 0 },
  { raw: 1 },
  { raw: "false" },
  { raw: "" },
  { raw: null }
]
```

khi dùng `$toBool`. Sau đó viết pipeline dùng `$switch` để parse String `"true"`/`"false"` theo nội dung. Tại sao không nên dùng `$toBool` trực tiếp cho cờ dữ liệu legacy là String?

### Bài 7 — Convert array

Dữ liệu:

```javascript
{
  rawValues: ["1.5", "bad", "3", null]
}
```

Viết `$map` kết hợp `$convert to "double"` để tạo array kết quả và array trạng thái tương ứng. Nếu rawValues đôi lúc không phải array, thêm `$isArray` để tránh lỗi.

### Bài 8 — Tối ưu truy vấn sau migration

Collection có một triệu sản phẩm với `price` lẫn String và Decimal128. API lọc giá lớn hơn 100. So sánh:

- Query dùng `$expr` và `$toDecimal` trên mọi document;
- Query trên field `priceDecimal` đã được chuẩn hóa và có B-tree index.

Giải thích vì sao giải pháp thứ hai thường có tiềm năng tối ưu range scan hơn, và những chi phí migration/duy trì field cần tính đến.

## 21. Tài liệu MongoDB tham khảo

- [Aggregation Expressions](https://www.mongodb.com/docs/manual/reference/mql/expressions/)
- [Aggregation $type Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/)
- [Query $type Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/)
- [Aggregation $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [Aggregation $toInt](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toInt/)
- [Aggregation $toLong](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toLong/)
- [Aggregation $toDouble](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDouble/)
- [Aggregation $toDecimal](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDecimal/)
- [Aggregation $toString](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toString/)
- [Aggregation $toDate](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDate/)
- [Aggregation $toBool](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toBool/)
- [Aggregation $toObjectId](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toObjectId/)
- [Aggregation $dateFromString](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateFromString/)
- [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)

## Kết luận

Khi dữ liệu MongoDB có thể chứa nhiều BSON type, bước đầu tiên là **nhìn đúng kiểu đang lưu** bằng `$type`. Biểu thức này giúp phân biệt String với Number, Date với chuỗi ngày, ObjectId với chuỗi hex, và đặc biệt là `null` với field `missing`.

**`$convert`** giải quyết bài toán chuyển kiểu có kiểm soát: `input` xác định giá trị, `to` xác định kiểu đích, `onError` xử lý lỗi chuyển và `onNull` xử lý null/missing. Các shortcut **`$toInt`, `$toLong`, `$toDouble`, `$toDecimal`, `$toString`, `$toDate`, `$toBool` và `$toObjectId`** giúp code ngắn hơn khi input đã được đảm bảo hợp lệ, nhưng không có cơ chế fallback linh hoạt như `$convert`.

Chuyển đổi kiểu thành công **chưa đồng nghĩa dữ liệu đúng nghiệp vụ**: vẫn phải kiểm tra miền giá trị, dấu tiền, độ chính xác Decimal128, timezone, định dạng Boolean và khả năng bị lỗi khi migration. Với truy vấn chạy thường xuyên, việc lưu dữ liệu thống nhất ngay từ đầu và tạo index trên field chuẩn hóa thường đáng tin cậy hơn chuyển đổi trên từng record ở mỗi lượt đọc. Một pipeline tốt không chỉ trả giá trị mới, mà còn giúp nhận diện, thống kê và đối soát những document chưa thể chuyển hợp lệ.

