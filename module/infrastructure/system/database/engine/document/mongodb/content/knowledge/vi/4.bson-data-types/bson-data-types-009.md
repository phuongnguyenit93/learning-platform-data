# Thứ tự so sánh kiểu BSON và ảnh hưởng đến truy vấn, sắp xếp

MongoDB lưu giá trị trong các **kiểu BSON** (Binary JSON), chẳng hạn `null`, số nguyên, số thực, `Decimal128`, chuỗi, document lồng nhau, mảng, `ObjectId`, Boolean, ngày giờ và `Timestamp`. Khi một collection chứa nhiều kiểu cho cùng một trường, kết quả của `sort()`, toán tử so sánh và index có thể khác điều người quen với JavaScript hoặc SQL dự đoán.

Điểm mấu chốt là cần phân biệt **ba ngữ cảnh**:

1. **Thứ tự BSON toàn cục**: dùng khi MongoDB sắp xếp hoặc khi biểu thức aggregation phải so sánh các giá trị thuộc những kiểu BSON khác nhau.
2. **Type bracketing trong query predicate**: các toán tử lọc như `$gt`, `$gte`, `$lt`, `$lte` thường chỉ so sánh những giá trị tương thích về kiểu với toán hạng, thay vì lấy thứ tự BSON toàn cục để lọc mọi kiểu.
3. **Quy tắc riêng cho string, array, object**: collation, việc chọn phần tử mảng để sort và thứ tự trường của embedded document ảnh hưởng trực tiếp đến kết quả.

Bài học sử dụng cú pháp `mongosh`, trình bày cả quy tắc, ví dụ, cách giải thích index và các lỗi thiết kế dữ liệu thường gặp.

## 1. Vì sao thứ tự BSON quan trọng?

Giả sử collection `products` có trường `price` không nhất quán:

```javascript
{ _id: "p1", price: NumberInt(90) }
{ _id: "p2", price: NumberDecimal("120.50") }
{ _id: "p3", price: "100" }
{ _id: "p4", price: null }
{ _id: "p5" } // không có trường price
```

Nếu gọi:

```javascript
db.products.find().sort({ price: 1, _id: 1 });
```

MongoDB không tự chuyển `"100"` thành số `100`. Chuỗi và số thuộc **nhóm BSON khác nhau**. Trong sắp xếp tăng dần, giá trị `null`/thiếu trường nằm trước nhóm số, và chuỗi nằm sau nhóm số. Vì thế, `"100"` không chen giữa `90` và `120.50` như khi so sánh theo giá trị số.

Nếu thay bằng:

```javascript
db.products.find({ price: { $gt: 100 } });
```

MongoDB áp dụng type bracketing, nên phép lọc với toán hạng số không đơn giản chọn tất cả chuỗi mà BSON xếp sau số. Kết quả thuộc nhóm số lớn hơn `100`; `"100"` không phải một số để phép lọc này so sánh. **Sort và filter có thể dựa vào những quy tắc khác nhau**, dù sử dụng cùng tên trường.

## 2. Thứ tự so sánh giữa các kiểu BSON

Khi so sánh **hai giá trị thuộc kiểu khác nhau** để sắp xếp, MongoDB dùng thứ tự sau (từ nhỏ đến lớn):

| Thứ tự | Kiểu/nhóm BSON | Giá trị điển hình |
|---:|---|---|
| 1 | `MinKey` | Giá trị sentinel nhỏ nhất trong thứ tự BSON |
| 2 | `Null` | `null` |
| 3 | **Numbers** | `Int32`, `Int64/Long`, `Double`, `Decimal128` |
| 4 | `Symbol`, `String` | `"MongoDB"`, `"42"` |
| 5 | `Object` / embedded document | `{ city: "Huế" }` |
| 6 | `Array` | `[1, 2]` |
| 7 | `BinData` | Dữ liệu nhị phân |
| 8 | `ObjectId` | `ObjectId("...")` |
| 9 | `Boolean` | `false`, `true` |
| 10 | `Date` | `ISODate("2026-01-01T00:00:00Z")` |
| 11 | `Timestamp` | BSON timestamp gồm phần giây và increment |
| 12 | `Regular Expression` | `/mongodb/i` |
| 13 | `JavaScript Code` | BSON code (kiểu chuyên biệt/legacy) |
| 14 | `JavaScript Code with Scope` | BSON code có scope (legacy) |
| 15 | `MaxKey` | Giá trị sentinel lớn nhất trong thứ tự BSON |

Đây là thứ tự BSON **từ thấp đến cao**, không phải bảng mức độ ưu tiên khi ứng dụng chọn schema. Các kiểu như `Symbol`, JavaScript code và code-with-scope không phải lựa chọn lưu trữ thông dụng cho ứng dụng mới; vẫn cần biết vị trí của chúng khi đọc dữ liệu cũ hoặc dữ liệu hỗn hợp.

### 2.1. Số nguyên, số thực và Decimal128 thuộc cùng nhóm so sánh

MongoDB coi các kiểu số là tương đương về **nhóm kiểu khi so sánh**. Hai số khác dạng biểu diễn vẫn được đánh giá theo giá trị số:

```javascript
NumberInt(7)
NumberLong("7")
7.0                     // Double trong cú pháp mongosh thông thường
NumberDecimal("7.0")
```

Các giá trị trên thuộc nhóm Numbers, không bị sắp thành bốn khối theo thứ tự `Int32` → `Int64` → `Double` → `Decimal128`.

Điều này **không có nghĩa mọi kiểu số đều có độ chính xác giống nhau**. `Double` là số dấu phẩy động nhị phân, trong khi `Decimal128` biểu diễn thập phân với độ chính xác theo chuẩn Decimal128. Một số nguyên lớn cũng có thể mất độ chính xác nếu chuyển qua JavaScript `Number`. Với tiền tệ hoặc dữ liệu cần giá trị thập phân chính xác, cần chọn kiểu thống nhất, tránh tự động chuyển qua `Double` và kiểm soát phép tính ở driver.

Ví dụ dùng `mongosh`:

```javascript
db.numericLab.insertMany([
  { _id: "int", value: NumberInt(7) },
  { _id: "long", value: NumberLong("7") },
  { _id: "double", value: 7.0 },
  { _id: "decimal", value: NumberDecimal("7.0") },
  { _id: "larger", value: NumberDecimal("7.5") }
]);

db.numericLab.find(
  { value: { $gt: 7 } },
  { _id: 1, value: 1 }
);
```

Các giá trị số bằng `7` không thỏa `$gt`; `7.5` thỏa. Nếu chỉ muốn lọc một kiểu số cụ thể, sử dụng `$type` hoặc kiểm tra schema thay vì kỳ vọng `$gt` tự phân biệt `Int32` với `Double`.

### 2.2. `Date` khác `Timestamp`

`ISODate("2026-01-01T00:00:00Z")` là giá trị BSON `Date`; `Timestamp` là kiểu BSON riêng thường gặp trong cơ chế nội bộ như oplog, gồm phần thời gian và số tăng. **Date xếp trước Timestamp khi so sánh khác kiểu**, ngay cả khi hai giá trị có thời gian lịch tương ứng.

Không nên dùng `Timestamp` thay cho ngày đặt hàng, ngày hết hạn hoặc thời điểm đăng nhập. Những trường nghiệp vụ đó thường dùng `Date`; còn `Timestamp` có ngữ nghĩa kỹ thuật khác.

### 2.3. `ObjectId` không phải số hoặc ngày

`ObjectId` là kiểu riêng và có vị trí riêng trong bảng. Dù `ObjectId` tiêu chuẩn có chứa thành phần thời gian, so sánh và sắp xếp `ObjectId` **không thay thế một trường `createdAt` được thiết kế rõ ràng**. Ứng dụng có thể tạo ObjectId ngoài máy chủ, các giá trị trong cùng một giây không nhất thiết tương ứng chính xác với thứ tự sự kiện toàn hệ thống, và `_id` còn có thể là kiểu khác.

## 3. Thực hành: sắp xếp collection có nhiều kiểu BSON

Tạo collection thử nghiệm chứa nhiều kiểu nhưng **chưa có mảng**, để quan sát thứ tự BSON trực tiếp:

```javascript
db.typeSortLab.drop();

db.typeSortLab.insertMany([
  { _id: "missing" },
  { _id: "null", value: null },
  { _id: "int", value: NumberInt(10) },
  { _id: "double", value: 2.5 },
  { _id: "decimal", value: NumberDecimal("3.75") },
  { _id: "string", value: "2" },
  { _id: "object", value: { x: 1 } },
  { _id: "binary", value: BinData(0, "AQ==") },
  { _id: "objectId",
    value: ObjectId("65a12f010000000000000001") },
  { _id: "boolean", value: false },
  { _id: "date", value: ISODate("2026-04-01T00:00:00Z") },
  { _id: "timestamp",
    value: Timestamp({ t: 1711929600, i: 1 }) }
]);

db.typeSortLab.find({}, { _id: 1, value: 1 })
  .sort({ value: 1, _id: 1 });
```

Thứ tự nhóm kết quả mong đợi ở lần sort tăng dần:

```text
missing, null
double (2.5), decimal (3.75), int (10)
string ("2")
object
binary
objectId
boolean
date
timestamp
```

Trường thiếu và `null` **được coi là tương đương về khóa sort**; `_id` được thêm làm khóa phụ để kết quả ổn định trong ví dụ. Trong thực tế, nếu nhiều document cùng một khóa sort mà không có khóa phụ duy nhất, MongoDB không bảo đảm thứ tự tương đối giữa chúng.

Đảo chiều:

```javascript
db.typeSortLab.find({}, { _id: 1, value: 1 })
  .sort({ value: -1, _id: 1 });
```

Các nhóm kiểu đảo ngược vị trí tương đối, nhưng lưu ý `_id: 1` vẫn là sắp xếp tăng dần khi `value` bằng nhau. Nếu chỉ dùng `sort({ value: -1 })`, thứ tự giữa các giá trị bằng nhau có thể thay đổi.

**Lưu ý quan trọng:** ví dụ trên cố ý không có mảng. Với trường có kiểu Array, MongoDB áp dụng các quy tắc chọn **phần tử mảng** để sort, nên không thể đơn giản xếp tất cả document chứa mảng thành một khối ở vị trí Array trong mọi kết quả.

## 4. Truy vấn so sánh: type bracketing khác thứ tự BSON

Các toán tử predicate lọc thường gặp:

- `$eq`, `$ne`: bằng/khác giá trị.
- `$gt`, `$gte`, `$lt`, `$lte`: so sánh lớn hơn, lớn hơn hoặc bằng, nhỏ hơn, nhỏ hơn hoặc bằng.
- `$in`, `$nin`: kiểm tra tập giá trị (có các chi tiết riêng cho mảng).
- `$type`: kiểm tra kiểu BSON.

**Các predicate bất đẳng thức** `$gt`/`$gte`/`$lt`/`$lte` dùng **type bracketing**. Chúng chỉ xét những giá trị phù hợp nhóm kiểu với toán hạng truy vấn. Các kiểu số (int, long, double, decimal) là một nhóm tương đương để so sánh.

### 4.1. Ví dụ phân biệt số, chuỗi và object

```javascript
db.typeQueryLab.drop();

db.typeQueryLab.insertMany([
  { _id: "smallNumber", score: NumberInt(8) },
  { _id: "largeNumber", score: NumberLong("20") },
  { _id: "decimalNumber", score: NumberDecimal("17.5") },
  { _id: "textNumber", score: "100" },
  { _id: "objectValue", score: { amount: 200 } },
  { _id: "missingScore" }
]);

db.typeQueryLab.find(
  { score: { $gt: 15 } },
  { _id: 1, score: 1 }
);
```

Truy vấn trên lấy `largeNumber` và `decimalNumber`. Nó không chọn `textNumber` hoặc `objectValue` chỉ vì String/Object đứng sau Number trong thứ tự BSON. `missingScore` cũng không thỏa điều kiện đó.

Cách hiểu sai thường gặp:

```text
Sai:  "$gt: 15" nghĩa là mọi BSON type xếp sau Number đều thỏa.
Đúng: Predicate so sánh theo nhóm kiểu tương thích của toán hạng.
```

Ngược lại, với **aggregation expression**, các biểu thức so sánh như `$gt` trong `$expr` có thể dùng thứ tự BSON để so sánh khác kiểu:

```javascript
db.typeQueryLab.find({
  $expr: { $gt: ["$score", 15] }
});
```

Biểu thức này có ngữ nghĩa khác predicate `{ score: { $gt: 15 } }`: vì String và Object đứng sau Number theo thứ tự BSON, một biểu thức so sánh khác kiểu có thể cho kết quả đúng với các giá trị như `"100"` hoặc `{ amount: 200 }`. Đây là lý do **không nên thay predicate bằng `$expr` một cách máy móc** mà không xem lại ngữ nghĩa kiểu và khả năng dùng index.

### 4.2. `$ne` và `$nin` không áp dụng type bracketing giống `$gt`

Ví dụ:

```javascript
db.typeQueryLab.find({ score: { $ne: 15 } });
```

`$ne` có thể khớp document thuộc nhiều kiểu khác nhau và cả document thiếu trường (theo semantics của `$ne`). Trường hợp `$nin` cũng cần hiểu rằng phủ định/tập giá trị có quy tắc khớp khác so với so sánh khoảng. Vì vậy, muốn lọc **chỉ số hợp lệ** không thể chỉ dùng `$ne` để loại một giá trị số cụ thể.

### 4.3. Lọc theo kiểu với `$type`

`$type` hữu ích khi dữ liệu có nhiều kiểu do migration, dữ liệu lỗi hoặc thay đổi API:

```javascript
// Chỉ các giá trị thuộc nhóm số
db.typeQueryLab.find({
  score: { $type: "number" }
});

// Chỉ BSON String
db.typeQueryLab.find({
  score: { $type: "string" }
});

// Xem kiểu thực tế của từng giá trị ở aggregation
db.typeQueryLab.aggregate([
  {
    $project: {
      _id: 1,
      score: 1,
      actualType: { $type: "$score" }
    }
  }
]);
```

Trong aggregation, `$type` trên một trường không tồn tại có thể trả về `"missing"`; trên trường có `null` trả về `"null"`. Khi dùng query operator `$type` trực tiếp trên field chứa **mảng**, MongoDB có thể khớp theo kiểu của phần tử mảng, không chỉ kiểu container. Nếu cần kiểm tra kiểu của toàn bộ giá trị field một cách chính xác, dùng aggregation expression `$type` thích hợp.

## 5. Sắp xếp array: chọn phần tử nhỏ nhất hoặc lớn nhất

Đây là ngoại lệ rất quan trọng. Khi `sort()` theo một trường chứa array:

- **Tăng dần `1`**: MongoDB dùng **phần tử nhỏ nhất** của array làm khóa sort.
- **Giảm dần `-1`**: MongoDB dùng **phần tử lớn nhất** của array làm khóa sort theo chiều giảm dần.
- Với array rỗng `[]`, MongoDB đặt nó **trước `null` hoặc trường thiếu** trong sắp xếp tăng dần.
- Với array có một phần tử, việc sort theo khóa đó có thể tương tự sort một giá trị scalar cùng loại.

Ví dụ:

```javascript
db.arraySortLab.drop();

db.arraySortLab.insertMany([
  { _id: "a", scores: [5, 80] },
  { _id: "b", scores: [20, 30] },
  { _id: "c", scores: [10] },
  { _id: "scalar", scores: 50 },
  { _id: "empty", scores: [] },
  { _id: "explicitNull", scores: null },
  { _id: "missing" }
]);

db.arraySortLab.find({}, { _id: 1, scores: 1 })
  .sort({ scores: 1, _id: 1 });

db.arraySortLab.find({}, { _id: 1, scores: 1 })
  .sort({ scores: -1, _id: 1 });
```

Ở các giá trị có thể so sánh như số, ta có:

| Document | `scores` | Khóa sort tăng dần | Khóa sort giảm dần |
|---|---|---:|---:|
| `a` | `[5, 80]` | `5` | `80` |
| `b` | `[20, 30]` | `20` | `30` |
| `c` | `[10]` | `10` | `10` |
| `scalar` | `50` | `50` | `50` |

Thứ tự các document chứa số/mảng số theo **tăng dần** là `a → c → b → scalar`; theo **giảm dần** là `a → scalar → b → c`. Do chọn phần tử khác nhau, thứ tự giảm dần **không đơn giản là đảo ngược danh sách tăng dần**.

Document `empty` với `[]` nằm trước `null`/missing trong chiều tăng, ngoài phần so sánh mảng số ở bảng. Đối với `null` và field missing, MongoDB xem là bằng nhau về khóa sort, nên cần khóa phụ `_id` nếu muốn thứ tự có thể lặp lại.

### 5.1. Filter trên mảng không quyết định phần tử dùng để sort

Xét:

```javascript
db.arraySortLab.find({
  scores: { $gt: 15 }
}).sort({ scores: 1 });
```

Document `a` có phần tử `80` thỏa `$gt: 15`, nhưng khóa sort tăng dần của `[5,80]` vẫn là `5`. Điều kiện lọc không tự biến khóa sort thành `80`. Đây là nguồn lỗi phổ biến khi nghĩ rằng MongoDB sắp theo **phần tử vừa khớp predicate**.

Nếu nghiệp vụ muốn “điểm cao nhất” hoặc “điểm thấp nhất” theo một cách có chủ ý, có thể lưu trước trường summary `maxScore`/`minScore`, hoặc dùng aggregation để tính khóa sắp xếp rõ ràng, tùy workload và yêu cầu index.

### 5.2. So sánh hai array trong biểu thức khác với sort array

Khi **so sánh array với array**, MongoDB áp dụng thứ tự từ điển (lexicographic), so từng phần tử từ đầu đến khi gặp vị trí khác nhau hoặc một array kết thúc:

```text
[1, 3] < [1, 5]
[1, 2] < [1, 2, 0]
```

Ngữ cảnh so sánh array (ví dụ trong biểu thức aggregation) cần phân biệt với quy tắc chọn **min/max element** khi sort trường có giá trị array. Các predicate so sánh trên field array còn có cơ chế dò phần tử và type bracketing riêng. Không nên áp dụng một quy tắc array cho mọi phép toán MongoDB.

## 6. Sắp xếp embedded document: kiểu, tên và thứ tự field

Đối với BSON Object, MongoDB so sánh các cặp key–value theo **thứ tự chúng xuất hiện trong document**. Ở mỗi vị trí, hệ thống xét kiểu của giá trị, rồi tên field và giá trị theo quy tắc so sánh BSON; nếu các cặp tương ứng bằng nhau thì chuyển sang cặp kế tiếp. Một document đã hết cặp có thể được xem là nhỏ hơn document tương ứng còn cặp bổ sung.

Vì vậy:

```javascript
{ a: 1, b: 2 }
{ b: 2, a: 1 }
```

không nên coi là hai BSON object có thứ tự field hoàn toàn không quan trọng. Điều này đặc biệt quan trọng với truy vấn **exact equality** trên toàn embedded document:

```javascript
db.objectLab.insertMany([
  { _id: "first", details: { a: 1, b: 2 } },
  { _id: "second", details: { b: 2, a: 1 } }
]);

// So sánh toàn bộ embedded document; thứ tự field có ý nghĩa
db.objectLab.find({ details: { a: 1, b: 2 } });

// Truy vấn từng trường con; không phụ thuộc thứ tự field trong document
db.objectLab.find({ "details.a": 1, "details.b": 2 });
```

Khi cần tìm các thuộc tính mà không quan tâm thứ tự khai báo, nên dùng **dot notation**, bộ lọc theo trường con, hoặc thiết kế schema nhất quán, thay vì ghép cả object vào phép so sánh bằng.

## 7. String: binary comparison, collation và `numericOrdering`

### 7.1. Mặc định là so sánh nhị phân đơn giản

Nếu không có collation khác ở collection hoặc thao tác, MongoDB sử dụng **simple binary comparison** cho chuỗi. Thứ tự đó không nhất thiết giống thứ tự chữ cái mà người đọc tiếng Việt kỳ vọng:

- Chữ hoa, chữ thường có thể được xếp khác nhau.
- Chữ có dấu có biểu diễn byte khác chữ không dấu.
- Chuỗi `"10"` thường xếp trước `"2"` theo thứ tự từ điển của ký tự.
- Thứ tự byte không tự áp dụng quy tắc ngôn ngữ của từ điển.

Ví dụ:

```javascript
db.stringLab.drop();

db.stringLab.insertMany([
  { _id: 1, label: "2" },
  { _id: 2, label: "10" },
  { _id: 3, label: "An" },
  { _id: 4, label: "an" },
  { _id: 5, label: "Ánh" },
  { _id: 6, label: "ánh" }
]);

db.stringLab.find({}, { _id: 0, label: 1 })
  .sort({ label: 1 });
```

Để có thứ tự phù hợp ngôn ngữ, sử dụng **collation**.

### 7.2. Collation thay đổi cách so sánh chuỗi

Collation cung cấp quy tắc phân biệt chữ hoa/thường, dấu, cách xếp chữ cái theo locale:

```javascript
db.stringLab.find({}, { _id: 0, label: 1 })
  .sort({ label: 1 })
  .collation({
    locale: "vi",
    strength: 1
  });
```

Với `strength: 1`, quy tắc so sánh ở mức chính (primary) tập trung vào ký tự cơ sở theo locale; nhiều khác biệt về hoa/thường và dấu không dùng để phân biệt tại mức này. Khi hai chuỗi tương đương ở mức collation đã chọn, **thứ tự giữa chúng không tự được bảo đảm**, trừ khi có tiêu chí phụ phù hợp.

Một số tùy chọn đáng chú ý:

| Tùy chọn | Ý nghĩa |
|---|---|
| `locale` | Ngôn ngữ/quy tắc ICU, ví dụ `"vi"` hoặc `"en"`; `"simple"` là nhị phân |
| `strength: 1` | So sánh ở mức ký tự cơ sở, thường bỏ qua khác biệt case và dấu |
| `strength: 2` | Xem xét khác biệt dấu theo quy tắc locale; thường chưa phân biệt case |
| `strength: 3` | Thêm phân biệt case/biến thể ký tự, là mức mặc định cho đa số locale |
| `caseLevel` | Cho phép xét case ngay cả với `strength: 1` hoặc `2` |
| `caseFirst` | Tác động đến thứ tự hoa/thường khi mức so sánh phù hợp |
| `numericOrdering` | So sánh các chuỗi chứa chuỗi chữ số nguyên không âm theo giá trị số trong những điều kiện được hỗ trợ |

### 7.3. `numericOrdering: true` chỉ tác động đến chuỗi, có giới hạn

Nếu lưu `"2"` và `"10"` dưới dạng String, phép sort nhị phân thường đưa `"10"` trước `"2"`. Có thể dùng:

```javascript
db.stringLab.find({}, { _id: 0, label: 1 })
  .sort({ label: 1 })
  .collation({
    locale: "en",
    numericOrdering: true
  });
```

Với các chuỗi số nguyên dương đơn giản, `"2"` được xem nhỏ hơn `"10"`. Tuy nhiên, `numericOrdering` **không có nghĩa chuyển mọi chuỗi thành Number**: cách so sánh này không hỗ trợ dấu âm `-`, dấu cộng `+`, dấu thập phân hoặc số mũ như một số hoàn chỉnh. Nó cũng **không hợp nhất nhóm BSON String với Numbers** trong thứ tự BSON toàn cục.

Nếu trường mang ý nghĩa định lượng, nên lưu bằng BSON numeric thích hợp thay vì phụ thuộc collation để sửa dữ liệu sai kiểu.

### 7.4. Collation phải phù hợp với index

Index có thể hỗ trợ sắp xếp/lọc chuỗi nếu quy tắc collation của thao tác **phù hợp** với collation index. Ví dụ:

```javascript
db.users.createIndex(
  { displayName: 1 },
  { collation: { locale: "vi", strength: 2 } }
);

db.users.find({ displayName: "ánh" })
  .collation({ locale: "vi", strength: 2 });

// Sort sử dụng cùng collation có thể tận dụng index phù hợp
db.users.find()
  .sort({ displayName: 1 })
  .collation({ locale: "vi", strength: 2 });
```

Nếu truy vấn dùng `locale: "simple"` nhưng index được tạo với `locale: "vi"`, MongoDB thường không thể dùng index đó để thực hiện **so sánh chuỗi theo simple collation**. Một số phần index không dựa trên String có thể vẫn được tận dụng tùy query. Cần xem `explain()` và hiểu default collation ở collection, index và thao tác.

## 8. `null`, trường thiếu và `undefined`

### 8.1. `null` và missing trong sort

Xét:

```javascript
db.nullSortLab.drop();

db.nullSortLab.insertMany([
  { _id: "missing" },
  { _id: "explicitNull", x: null },
  { _id: "zero", x: 0 },
  { _id: "text", x: "" }
]);

db.nullSortLab.find().sort({ x: 1, _id: 1 });
```

Trong sort theo `x`, trường **không tồn tại** được so sánh như `null`; vì vậy `missing` và `explicitNull` tương đương về khóa sort, đều đứng trước Number. Dùng khóa phụ độc nhất `_id` để ổn định thứ tự.

Đối với một array rỗng `[]`, quy tắc sort array còn đặt nó trước `null`/missing trong chiều tăng. Do đó không nên viết hàm ứng dụng giả định mọi giá trị rỗng có cùng thứ tự.

### 8.2. Cách tìm rõ `null` và missing

```javascript
// null equality thường khớp cả explicit null và trường bị thiếu
db.nullSortLab.find({ x: null });

// Chỉ document có trường x, bất kể giá trị là gì
db.nullSortLab.find({ x: { $exists: true } });

// Chỉ document không có trường x
db.nullSortLab.find({ x: { $exists: false } });

// Chỉ document có kiểu BSON Null
db.nullSortLab.find({ x: { $type: "null" } });
```

Phân biệt `null`, missing và các giá trị mặc định ngay từ schema giúp pagination, sort và filter ít bất ngờ hơn.

### 8.3. Khác biệt phiên bản với BSON Undefined

`undefined` là BSON type đã bị loại khỏi các cách dùng khuyến nghị. Với MongoDB **8.0 trở lên**, equality query `{ x: null }` không còn khớp giá trị BSON `undefined`; ở các phiên bản cũ hơn, hành vi tương thích `undefined` có khác biệt. Nếu dữ liệu legacy chứa `undefined`, nên kiểm tra phiên bản và có kế hoạch chuyển dữ liệu, thay vì cho rằng `undefined` đồng nghĩa hoàn toàn với `null`.

## 9. Index, sort và hệ quả của kiểu dữ liệu lẫn lộn

Index của MongoDB lưu các khóa phù hợp với kiểu giá trị BSON và quy tắc so sánh liên quan. Một index hỗ trợ `sort({ field: 1 })` có thể phản ánh thứ tự BSON của các giá trị trong field đó. Tuy nhiên, hiệu quả truy vấn còn phụ thuộc filter, thứ tự khóa compound index, collation và array/multikey.

Ví dụ:

```javascript
db.events.createIndex({ category: 1, createdAt: -1, _id: 1 });

db.events.find({ category: "payment" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(20)
  .explain("executionStats");
```

Nếu mọi `createdAt` đều là BSON Date, index có thể phục vụ truy vấn theo thời gian hợp lý. Nhưng nếu một phần document lưu `createdAt` dưới dạng String ISO, số epoch hoặc `null`, sort sẽ chia theo **nhóm BSON type** và có thể không phản ánh trật tự thời gian nghiệp vụ:

```javascript
{ createdAt: ISODate("2026-01-02T00:00:00Z") }  // Date
{ createdAt: "2026-01-01T00:00:00Z" }            // String
{ createdAt: NumberLong("1767225600000") }      // Number
```

Dù String có định dạng ISO 8601 giống Date về hình thức, MongoDB không tự đồng nhất chúng. **Index không sửa được sự bất nhất về kiểu**; nó chỉ tăng tốc truy cập theo quy tắc mà cơ sở dữ liệu thực sự dùng.

### 9.1. Khi nào cần khóa phụ để sort ổn định?

`sort({ createdAt: -1 })` không bảo đảm thứ tự ổn định giữa các document có cùng `createdAt` hoặc cùng khóa `null`. Với phân trang, điều này có thể khiến document đổi vị trí giữa các lần đọc, nhất là khi có dữ liệu mới.

Một cách làm rõ thứ tự là:

```javascript
db.events.find({ category: "payment" })
  .sort({ createdAt: -1, _id: 1 })
  .limit(20);
```

Thứ tự trên dùng `_id` làm tie-breaker duy nhất. Nếu dùng cursor pagination, điều kiện trang kế tiếp phải khớp **cả hai chiều sort** (`createdAt` giảm, `_id` tăng) và xử lý biên null/missing nhất quán; không chỉ thay một `skip()` lớn là đủ để ổn định dữ liệu đang thay đổi.

### 9.2. Khi nào filter dùng index khác với sort?

Một index có thể phục vụ tìm kiếm `{ score: { $gt: 20 } }` rất tốt khi dữ liệu là số. Nhưng nếu schema cho phép String lẫn Number, việc dùng index không có nghĩa predicate sẽ bỏ type bracketing và tìm cả `"30"`. Index tổ chức dữ liệu theo quy tắc BSON; **query semantics do toán tử quyết định**.

Khi truy vấn cần ép kiểu, cân nhắc migration (ưu tiên nếu có thể) hoặc chuyển đổi trong aggregation với `$convert`/`$toDecimal` có xử lý lỗi. Chuyển kiểu ở runtime có thể tăng chi phí và hạn chế khả năng dùng index; không nên ngầm xem đó là giải pháp hiệu năng tương đương trường numeric chuẩn hóa.

### 9.3. Chống dữ liệu sai kiểu bằng schema validation

Ví dụ một collection chỉ nhận `price` dưới dạng `decimal` và `createdAt` dưới dạng `date`:

```javascript
db.createCollection("validatedProducts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "price", "createdAt"],
      properties: {
        name: { bsonType: "string" },
        price: { bsonType: "decimal" },
        createdAt: { bsonType: "date" }
      }
    }
  }
});
```

Tùy yêu cầu, có thể cho phép nhiều kiểu numeric bằng `bsonType: ["int", "long", "double", "decimal"]`, nhưng với đơn vị tiền hoặc số đo cần độ chính xác cố định, một kiểu chuẩn thường giúp đơn giản hóa phân tích. Validator không thay thế kiểm tra nghiệp vụ ở API và quy trình migration dữ liệu cũ.

## 10. Bảng tra cứu nhanh: sort, predicate và aggregation

| Tình huống | Quy tắc quan trọng | Sai lầm cần tránh |
|---|---|---|
| `sort({ x: 1 })`, `x` có nhiều kiểu scalar | So sánh theo thứ tự BSON từ thấp đến cao | Nghĩ String `"10"` được so như Number `10` |
| `sort({ x: -1 })` | Đảo thứ tự loại/giá trị của khóa sort | Quên tie-breaker cho giá trị bằng nhau |
| `find({ x: { $gt: 10 } })` | Predicate dùng type bracketing | Kết luận mọi String/Object lớn hơn Number đều khớp |
| `$expr: { $gt: ["$x", 10] }` | Aggregation expression có thể so sánh khác kiểu theo thứ tự BSON | Coi giống hệt query predicate `$gt` |
| `sort({ x: 1 })` với array | Dùng phần tử nhỏ nhất làm khóa | Sắp xếp theo phần tử vừa lọc |
| `sort({ x: -1 })` với array | Dùng phần tử lớn nhất làm khóa | Cho rằng kết quả luôn là đảo ngược sort tăng |
| So sánh object lồng nhau | Thứ tự các key/value có thể ảnh hưởng | Coi hai object có cùng field nhưng đảo thứ tự luôn tương đương |
| `sort` trên `null` và missing | Missing được xem tương đương `null` khi so sánh khóa sort | Đòi một thứ tự cố định giữa hai trường hợp |
| Sort String với `simple` | So sánh nhị phân, không phải thứ tự từ điển theo locale | Dùng mặc định cho tên tiếng Việt khi cần thứ tự ngôn ngữ |
| Sort String có collation | Theo locale, strength và các tùy chọn tương ứng | Tạo index collation khác rồi kỳ vọng index hỗ trợ sort |
| Index trên field lẫn Date/String | Index giữ khác biệt BSON type | Nghĩ index tự đưa mọi giá trị về cùng đơn vị thời gian |

## 11. Bài tập thực hành

### Bài 1 — Tạo dữ liệu trộn kiểu và dự đoán `sort`

Tạo các document có `value` lần lượt là `null`, `NumberInt(5)`, `NumberDecimal("5.5")`, `"1"`, `{}`, `ObjectId`, `true` và `ISODate`. Dự đoán thứ tự `sort({ value: 1 })` trước khi chạy lệnh. Giải thích vì sao `"1"` không nằm trước `5`, và vì sao `Date` được xếp sau `Boolean` khi khác kiểu.

### Bài 2 — Phân biệt query predicate với `$expr`

Trên `typeQueryLab`, thử:

```javascript
db.typeQueryLab.find({ score: { $gt: 15 } }, { _id: 1 });
db.typeQueryLab.find({ $expr: { $gt: ["$score", 15] } }, { _id: 1 });
```

So sánh hai tập kết quả. Chỉ ra vai trò của type bracketing trong predicate và thứ tự BSON trong aggregation expression. Sau đó thêm bộ lọc chỉ số hợp lệ bằng `$type` hoặc migration sang một kiểu thống nhất.

### Bài 3 — Tìm ra khóa sort của mảng

Với `scores` là `[5,80]`, `[20,30]`, `[10]` và `50`, viết thứ tự tăng/giảm trước khi chạy. Sau đó thử lọc `scores: { $gt: 15 }` và sort tăng dần. Giải thích vì sao phần tử `5` của `[5,80]` vẫn có thể quyết định vị trí sort dù `80` mới là phần tử thỏa bộ lọc.

### Bài 4 — Sửa sự cố sort tên sản phẩm

Một hệ thống hiển thị danh sách tên tiếng Việt theo `simple` collation và nhận phản ánh rằng tên có dấu/hoa thường không theo thứ tự mong muốn. Hãy:

1. Tạo bộ dữ liệu thử gồm các tên có/không có dấu và chữ hoa/chữ thường.
2. So sánh `simple` với `{ locale: "vi", strength: 2 }`.
3. Tạo index có collation phù hợp với truy vấn.
4. Dùng `explain("executionStats")` để quan sát query plan và xác định có sort bổ sung hay không.

### Bài 5 — Thiết kế schema an toàn

Collection giao dịch có `amount` lẫn `"100.50"`, `NumberDecimal("100.50")` và `100.5`. Hãy đưa ra lộ trình chuyển thành `Decimal128` thống nhất, bao gồm xác định đơn vị tiền, xử lý giá trị không hợp lệ, migration có kiểm tra, cập nhật validator và rà soát index. Giải thích vì sao chỉ sửa `sort()` hoặc collation không giải quyết tận gốc sự cố.

## 12. Tài liệu MongoDB tham khảo

- [Comparison/Sort Order — thứ tự BSON, array, object, null và BinData](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [Type Bracketing in Query Predicates — cách `$gt`/`$lt` lọc theo kiểu](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/type-bracketing/)
- [Comparison Query Predicate Operators — khác nhau giữa predicate và expression](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/comparison/)
- [Collation — locale, strength, numericOrdering và quy tắc dùng index](https://www.mongodb.com/docs/manual/reference/collation/)
- [Migrate Undefined Data and Queries — thay đổi hành vi `null` từ MongoDB 8.0](https://www.mongodb.com/docs/manual/reference/bson-types/migrate-undefined/)

## Kết luận

MongoDB có **thứ tự BSON rõ ràng khi sort**: `MinKey`, `Null`, nhóm số, chuỗi, object, array, binary, `ObjectId`, Boolean, Date, Timestamp và các kiểu chuyên biệt khác. Nhưng **query predicate dùng type bracketing**, aggregation expression có cách so sánh khác, array có quy tắc chọn phần tử min/max riêng và string có thể dùng collation theo ngôn ngữ.

Vì vậy, một truy vấn MongoDB đúng cần xác định cả **kiểu BSON của dữ liệu**, **toán tử đang dùng**, **collation**, **cách index được tạo** và **khóa sort phụ**. Lưu schema nhất quán cho những trường có ý nghĩa như số tiền, ngày giờ và trạng thái là cách hiệu quả nhất để tránh kết quả lọc/sắp xếp gây bất ngờ.
