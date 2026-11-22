# Các trường hợp mảng rỗng, phần tử `null` và trường không tồn tại trong MongoDB

Khi truy vấn mảng trong MongoDB, ba tình huống nhìn có vẻ giống nhau nhưng có ý nghĩa dữ liệu rất khác nhau: **mảng rỗng `[]`**, **mảng chứa phần tử `null`** và **field không tồn tại**. Ngoài ra còn có tình huống field tồn tại nhưng có giá trị `null`, hoặc được lưu nhầm thành một giá trị đơn thay vì mảng. Nếu bỏ qua những khác biệt này, bộ lọc có thể trả về document ngoài mong đợi, bỏ sót dữ liệu hoặc khiến ứng dụng hiểu sai trạng thái.

Ví dụ, một hệ thống lưu danh sách nhãn của bài viết:

```javascript
{ _id: "a", tags: [] }               // Có field, kiểu array, chưa có nhãn
{ _id: "b", tags: [null] }           // Có array gồm một phần tử null
{ _id: "c", tags: ["mongo", null] }  // Có nhãn và một phần tử null
{ _id: "d", tags: null }             // Có field, nhưng toàn bộ giá trị là null
{ _id: "e" }                         // Không có field tags
```

Đây là **năm trạng thái khác nhau của document BSON**. Bài học đi từ bộ dữ liệu thực hành đến các toán tử `$size`, `$exists`, `$type`, `$elemMatch`, phép so sánh `null`, rồi đến ứng dụng với mảng object, aggregation và Java MongoDB Driver.

## 1. Phân biệt cấu trúc trước khi viết truy vấn

Một field trong MongoDB có thể có nhiều kiểu BSON. Đặc biệt, `null` là một **giá trị BSON**; sự vắng mặt của field là một đặc điểm của cấu trúc document, không phải giá trị `null`.

| Cách lưu | Field có tồn tại? | Kiểu của field | Độ dài mảng | Ý nghĩa có thể có |
| --- | --- | --- | --- | --- |
| `{ tags: [] }` | Có | Array | 0 | Danh sách đã được khởi tạo nhưng chưa có phần tử |
| `{ tags: [null] }` | Có | Array | 1 | Một vị trí có giá trị không xác định |
| `{ tags: ["mongo", null] }` | Có | Array | 2 | Một phần tử có giá trị và một phần tử `null` |
| `{ tags: null }` | Có | Null | Không áp dụng | Cả trường chưa có giá trị xác định |
| `{ /* không có tags */ }` | Không | Missing | Không áp dụng | Trường chưa được ghi vào document |
| `{ tags: "mongo" }` | Có | String | Không áp dụng | Trường được lưu dưới dạng giá trị đơn |
| `{ tags: [[]] }` | Có | Array | 1 | Mảng chứa một phần tử cũng là mảng rỗng |

Không nên đồng nhất `[]` với `[null]`: mảng đầu có **0 phần tử**, mảng sau có **1 phần tử**. Cũng không nên đồng nhất `null` với field thiếu: một document có `tags: null` vẫn có khóa `tags`.

Về nghiệp vụ, cần định nghĩa rõ các trạng thái đó. Chẳng hạn danh sách người nhận `[]` có thể mang nghĩa “đã xác nhận không có người nhận”, còn field không tồn tại có thể có nghĩa “chưa đồng bộ dữ liệu”. MongoDB không tự biết quy ước này; ứng dụng và người thiết kế schema phải nhất quán với nhau.

## 2. Tạo dữ liệu mẫu để quan sát chính xác kết quả

Trong `mongosh`, dùng một database riêng cho thực hành:

```javascript
use mongo_array_lab
```

Thêm các document:

```javascript
db.arrayCases.insertMany([
  {
    _id: "a",
    name: "Mảng rỗng",
    tags: []
  },
  {
    _id: "b",
    name: "Mảng chứa null",
    tags: [null]
  },
  {
    _id: "c",
    name: "Mảng chứa chuỗi và null",
    tags: ["mongo", null]
  },
  {
    _id: "d",
    name: "Field có giá trị null",
    tags: null
  },
  {
    _id: "e",
    name: "Không có field tags"
  },
  {
    _id: "f",
    name: "Mảng chứa chuỗi",
    tags: ["mongo"]
  },
  {
    _id: "g",
    name: "Mảng chứa một mảng rỗng",
    tags: [[]]
  },
  {
    _id: "h",
    name: "Field tags là chuỗi",
    tags: "mongo"
  },
  {
    _id: "i",
    name: "Mảng chứa object",
    tags: [
      { label: null },
      { label: "index" }
    ]
  }
])
```

Các truy vấn trong các mục tiếp theo giả định dữ liệu **chưa bị chỉnh sửa**. Để đọc kết quả gọn và có thứ tự ổn định, thêm projection và sort:

```javascript
db.arrayCases.find(
  { tags: { $exists: true } },
  { _id: 1, name: 1, tags: 1 }
).sort({ _id: 1 })
```

Chỉ chạy `insertMany` một lần trên collection trống; các giá trị `_id` cố định sẽ gây lỗi duplicate key nếu chèn lặp. Những ví dụ sửa dữ liệu phía sau dùng lệnh riêng và sẽ thay đổi bộ dữ liệu khi thực thi.

## 3. Tìm mảng thực sự rỗng bằng `$size: 0`

Khi cần tìm document có field `tags` là **một array không có phần tử nào**, dùng:

```javascript
db.arrayCases.find({
  tags: { $size: 0 }
})
```

Trong bộ dữ liệu mẫu, truy vấn này khớp **chỉ `a`**.

`$size` so khớp số lượng phần tử của array tại field được truy vấn. Nó không coi `null`, field thiếu hoặc string là mảng dài 0.

| Document | Giá trị `tags` | Có khớp `$size: 0`? |
| --- | --- | --- |
| `a` | `[]` | Có |
| `b` | `[null]` | Không, có một phần tử |
| `c` | `["mongo", null]` | Không, có hai phần tử |
| `d` | `null` | Không, không phải array |
| `e` | Không tồn tại | Không |
| `f` | `["mongo"]` | Không |
| `g` | `[[]]` | Không, array ngoài có một phần tử |
| `h` | `"mongo"` | Không, không phải array |
| `i` | Hai object | Không |

Có thể tìm các mảng đúng một phần tử:

```javascript
db.arrayCases.find({
  tags: { $size: 1 }
})
```

Với dữ liệu mẫu, kết quả gồm **`b`, `f`, `g`**. Truy vấn không phân biệt phần tử đó là `null`, string hay một array khác; nó chỉ kiểm tra **kích thước mảng ngoài cùng**.

### Tại sao `{ tags: [] }` không hoàn toàn giống `$size: 0`?

MongoDB hỗ trợ **array equality**:

```javascript
db.arrayCases.find({
  tags: []
})
```

Một điểm cần lưu ý khi mảng có thể lồng nhau: điều kiện equality với giá trị là array có thể khớp **nguyên array**, hoặc khớp khi field chứa **phần tử là một array bằng giá trị được chỉ định**. Trong dữ liệu mẫu, điều kiện `tags: []` khớp document có `tags: []` và có thể khớp document `tags: [[]]` vì phần tử bên trong là `[]`.

Do đó, khi yêu cầu là **field `tags` phải là một mảng có đúng 0 phần tử ở cấp ngoài**, `{ tags: { $size: 0 } }` diễn đạt rõ nhất. `{ tags: [] }` nên được đọc theo ngữ nghĩa array equality của MongoDB, đặc biệt khi dữ liệu có nested arrays.

Không dùng `$all: []` để tìm mảng rỗng:

```javascript
db.arrayCases.find({
  tags: { $all: [] }
})
```

`$all` yêu cầu field chứa **tất cả** các phần tử trong danh sách truy vấn; với đối số rỗng, toán tử này **không đóng vai trò tìm mảng rỗng** và không trả kết quả như `$size: 0`.

## 4. Tìm field không tồn tại bằng `$exists: false`

Để tìm document hoàn toàn **không có khóa `tags`**:

```javascript
db.arrayCases.find({
  tags: { $exists: false }
})
```

Kết quả của bộ dữ liệu mẫu: **chỉ `e`**.

Để tìm mọi document **có khóa `tags`**, bất kể giá trị đó là gì:

```javascript
db.arrayCases.find({
  tags: { $exists: true }
})
```

Kết quả gồm **`a`, `b`, `c`, `d`, `f`, `g`, `h`, `i`**. Điều kiện `$exists: true` vẫn khớp với `tags: null` và `tags: []`: field đã có mặt, dù giá trị là null hoặc mảng rỗng.

Trong thực tế:

- `$exists: false` phù hợp khi muốn tìm record cũ chưa được bổ sung một field hoặc một phần dữ liệu chưa khởi tạo.
- `$exists: true` chỉ xác nhận **sự hiện diện**, không xác nhận kiểu dữ liệu hoặc số phần tử.
- Muốn biết field có phải array không, bổ sung điều kiện kiểu BSON bằng `$type`.

Ví dụ chỉ nhận document có field `tags` là array:

```javascript
db.arrayCases.find({
  tags: { $type: "array" }
})
```

Kết quả: **`a`, `b`, `c`, `f`, `g`, `i`**. Các document `d` (null), `e` (missing) và `h` (string) không khớp.

## 5. Phép so sánh với `null`: vì sao thường có kết quả rộng?

Truy vấn:

```javascript
db.arrayCases.find({
  tags: null
})
```

**Không nên hiểu** câu lệnh này là “field `tags` tồn tại và có kiểu BSON Null”. Điều kiện equality với `null` có thể khớp document mà field **vắng mặt**. Khi field là array, MongoDB cũng có thể khớp một array chứa phần tử `null`.

Với dữ liệu mẫu, những trường hợp liên quan gồm:

| Document | Giá trị `tags` | `{ tags: null }` |
| --- | --- | --- |
| `b` | `[null]` | Khớp do phần tử null |
| `c` | `["mongo", null]` | Khớp do phần tử null |
| `d` | `null` | Khớp do cả field bằng null |
| `e` | Thiếu field | Khớp do quy tắc equality với null |
| `a` | `[]` | Không khớp |
| `f` | `["mongo"]` | Không khớp |

Điều này tạo ra một lỗi suy luận thường gặp: một truy vấn `{ tags: null }` trả về document **chưa có field**, **có field null** và **có array chứa null**, trong khi nghiệp vụ có thể cần phân biệt ba trạng thái hoàn toàn khác nhau.

Viết tường minh bằng `$eq` vẫn giữ ngữ nghĩa equality:

```javascript
db.arrayCases.find({
  tags: { $eq: null }
})
```

Để chỉ tìm **field thiếu**, dùng `$exists: false` như mục trước. Để chỉ tìm array chứa phần tử null, dùng `$elemMatch` như mục 7. Để xác định chính xác **kiểu trực tiếp của field** là Null, xem cách dùng `$expr` ở mục 6.

### Vì sao `$in: [null]` cũng phải đọc cẩn thận?

```javascript
db.arrayCases.find({
  tags: { $in: [null] }
})
```

`$in` kiểm tra các giá trị được chỉ định, và đối với array có thể kiểm tra từng phần tử. Khi danh sách có `null`, nó có thể khớp các tình huống null hoặc field thiếu theo quy tắc so sánh tương ứng. Vì vậy `$in: [null]` cũng không phải cách chính xác để phân loại riêng mảng rỗng, field null và field vắng mặt.

## 6. Phân biệt kiểu Null trực tiếp với một array chứa Null

Toán tử truy vấn `$type` thường được sử dụng như sau:

```javascript
db.arrayCases.find({
  tags: { $type: "null" }
})
```

Với field có giá trị array, phép truy vấn `$type` có thể so khớp **kiểu của các phần tử mảng**. Vì vậy bộ lọc trên khớp **`b`, `c`, `d`** trong dữ liệu mẫu: hai document đầu chứa phần tử null, document cuối có field trực tiếp là null. Nó không khớp `e` vì field không tồn tại.

Nếu mục tiêu là kiểm tra **kiểu BSON của chính field**, kể cả khi field đó là array, có thể dùng toán tử aggregation `$type` bên trong `$expr`:

```javascript
db.arrayCases.find({
  $expr: {
    $eq: [
      { $type: "$tags" },
      "null"
    ]
  }
})
```

Truy vấn này khớp **chỉ `d`**, vì:

- Với `tags: null`, aggregation `$type` trả chuỗi `"null"`.
- Với `tags: [null]`, aggregation `$type` trả `"array"`, vì kiểu của **toàn field** là array.
- Với field `tags` không tồn tại, aggregation `$type` trả `"missing"`.

Có thể dùng tương tự để kiểm tra field thiếu:

```javascript
db.arrayCases.find({
  $expr: {
    $eq: [
      { $type: "$tags" },
      "missing"
    ]
  }
})
```

Bộ lọc này khớp `e`. Đối với nhu cầu tìm field thiếu đơn giản, `{ tags: { $exists: false } }` ngắn gọn hơn và thường là cách nên ưu tiên.

### Nhớ phân biệt hai ngữ cảnh của `$type`

```javascript
// Query operator: có thể xét kiểu phần tử array
{ tags: { $type: "null" } }

// Aggregation expression: xét kiểu của biểu thức "$tags" như một giá trị
{
  $expr: {
    $eq: [{ $type: "$tags" }, "null"]
  }
}
```

Cùng tên `$type` nhưng **vị trí sử dụng khác nhau** dẫn đến cách đánh giá khác nhau. Đây là khác biệt đặc biệt hữu ích khi phân loại field null và array chứa null.

## 7. Tìm phần tử `null` bên trong array bằng `$elemMatch`

Khi mục tiêu là “field `tags` phải là array và **có ít nhất một phần tử bằng null**”, dùng:

```javascript
db.arrayCases.find({
  tags: {
    $elemMatch: {
      $eq: null
    }
  }
})
```

Kết quả: **`b` và `c`**.

`$elemMatch` yêu cầu có ít nhất một phần tử của **array** thỏa điều kiện bên trong. Nó không xem `tags: null` là array, cũng không xem field thiếu là array. Vì vậy `d` và `e` không khớp.

Có thể dùng điều kiện kiểu bên trong:

```javascript
db.arrayCases.find({
  tags: {
    $elemMatch: {
      $type: "null"
    }
  }
})
```

Truy vấn này cũng nhằm tìm array chứa phần tử null trực tiếp. Với nested array, cần hiểu kỹ cấp phần tử đang xét; một phần tử là **array `[null]`** không giống phần tử trực tiếp là **`null`**.

### Mảng đúng một phần tử null

Nếu yêu cầu là array ngoài có **chính xác một phần tử và phần tử đó là null**, có thể kết hợp hai điều kiện:

```javascript
db.arrayCases.find({
  $and: [
    { tags: { $size: 1 } },
    { tags: { $elemMatch: { $eq: null } } }
  ]
})
```

Với dữ liệu mẫu, kết quả là **`b`**. `$size: 1` bảo đảm số phần tử, còn `$elemMatch` bảo đảm phần tử đó là null. Cách ghép này tránh nhầm với `["mongo", null]`, vốn có hai phần tử.

Để tìm một array chỉ chứa các chuỗi và không có null, truy vấn cần xác định ràng buộc nghiệp vụ cụ thể. Nếu muốn bảo vệ kiểu dữ liệu lúc ghi, nên thiết lập schema validation cho các phần tử array thay vì chỉ dựa vào một phép lọc đọc.

## 8. Bảng đối chiếu các bộ lọc thường dùng

Giả định các giá trị mẫu của mục 2, chưa sửa đổi:

| Bộ lọc | Mục đích | ID phù hợp |
| --- | --- | --- |
| `{tags: {$size: 0}}` | Array rỗng ở cấp field | `a` |
| `{tags: {$size: 1}}` | Array có một phần tử | `b, f, g` |
| `{tags: {$exists: false}}` | Thiếu field `tags` | `e` |
| `{tags: {$exists: true}}` | Có field `tags`, bất kể giá trị | `a, b, c, d, f, g, h, i` |
| `{tags: {$type: "array"}}` | Field có kiểu array | `a, b, c, f, g, i` |
| `{tags: null}` | Equality với null, có thể gồm field thiếu/array chứa null | `b, c, d, e` |
| `{tags: {$type: "null"}}` | Null trực tiếp hoặc phần tử null trong array | `b, c, d` |
| `{tags: {$elemMatch: {$eq: null}}}` | Array có phần tử null | `b, c` |
| `{$expr: {$eq: [{$type: "$tags"}, "null"]}}` | Field trực tiếp là BSON Null | `d` |
| `{$expr: {$eq: [{$type: "$tags"}, "missing"]}}` | Field thiếu theo aggregation `$type` | `e` |

Để xem đúng ID thay vì in ra document dài:

```javascript
db.arrayCases.find(
  { tags: { $size: 0 } },
  { _id: 1 }
).sort({ _id: 1 })
```

Cách đọc kết quả của các filter cần bám vào **kiểu BSON và cấu trúc array**, không dựa vào cách chúng được hiển thị trong giao diện.

## 9. Trường hợp mảng object: field con `null` và field con thiếu

Mảng của object thường gặp trong đơn hàng, biểu mẫu, danh sách câu trả lời hoặc hồ sơ người dùng. Ví dụ:

```javascript
db.forms.insertMany([
  {
    _id: "form-1",
    answers: [
      { question: "Q1", value: null },
      { question: "Q2", value: "yes" }
    ]
  },
  {
    _id: "form-2",
    answers: [
      { question: "Q1" }
    ]
  },
  {
    _id: "form-3",
    answers: []
  },
  {
    _id: "form-4",
    answers: null
  },
  {
    _id: "form-5"
  }
])
```

Ở đây cần phân biệt **field `answers`** có tồn tại hay không, **mảng `answers`** có rỗng hay không, và **field `value` trong từng object** có là null hay không.

### 9.1. Có object chứa field `value` bằng BSON Null

```javascript
db.forms.find({
  answers: {
    $elemMatch: {
      value: { $type: "null" }
    }
  }
})
```

Truy vấn khớp **`form-1`**. `$elemMatch` đảm bảo có phần tử object trong array; điều kiện `$type: "null"` yêu cầu `value` mang kiểu Null, không chỉ đơn giản là field thiếu.

### 9.2. Có object không chứa field `value`

```javascript
db.forms.find({
  answers: {
    $elemMatch: {
      value: { $exists: false }
    }
  }
})
```

Kết quả là **`form-2`**. Đây là truy vấn về **một phần tử object thiếu field con**, khác với tìm document thiếu toàn bộ mảng `answers`.

### 9.3. Mảng `answers` rỗng

```javascript
db.forms.find({
  answers: { $size: 0 }
})
```

Kết quả là **`form-3`**.

### 9.4. Field `answers` không tồn tại

```javascript
db.forms.find({
  answers: { $exists: false }
})
```

Kết quả là **`form-5`**.

### Vì sao cần `$elemMatch` trong ví dụ này?

Nếu viết `"answers.value": null`, quy tắc equality với null và việc đi qua array có thể cho kết quả rộng hơn ý định “tồn tại một object có field `value` mang BSON Null”. Khi yêu cầu liên quan đến **một phần tử của mảng object**, hãy mô tả điều kiện trong `$elemMatch` rồi kiểm tra `$type` hoặc `$exists` của field con.

Tương tự, với nhiều điều kiện phải đồng thời đúng trên **cùng object**:

```javascript
db.forms.find({
  answers: {
    $elemMatch: {
      question: "Q1",
      value: { $type: "null" }
    }
  }
})
```

Hai điều kiện `question` và `value` cùng áp dụng trên **một answer**. Nếu dùng hai dot paths tách rời, mỗi điều kiện có thể khớp ở hai phần tử khác nhau.

## 10. Aggregation: chuẩn hóa giá trị cho mục đích đọc

Nhiều ứng dụng muốn hiển thị danh sách dưới dạng array trong response JSON. MongoDB cung cấp aggregation để chuẩn hóa field null hoặc thiếu thành mảng rỗng **trong kết quả truy vấn**.

Ví dụ dùng `$ifNull`:

```javascript
db.arrayCases.aggregate([
  {
    $project: {
      name: 1,
      normalizedTags: {
        $ifNull: ["$tags", []]
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Ở đây:

- `tags: null` được biểu diễn thành `normalizedTags: []`.
- Field `tags` thiếu cũng được biểu diễn thành `normalizedTags: []`.
- `tags: []` giữ là `[]`.
- `tags: [null]` vẫn là `[null]`, **không bị xóa phần tử null**.
- Field `tags: "mongo"` vẫn là string `"mongo"`, vì `$ifNull` chỉ xử lý null/missing, không ép mọi giá trị thành array.

**Điểm quan trọng:** đây là phép biến đổi **đầu ra**, không cập nhật document đang lưu. Nó có thể phù hợp khi API muốn luôn trả về `[]` cho hai trạng thái “không có danh sách”, nhưng ứng dụng cần cân nhắc liệu việc gộp null và missing có làm mất thông tin nghiệp vụ quan trọng hay không.

### Chỉ chuẩn hóa khi field thực sự là array

Nếu dữ liệu nguồn còn có string, boolean hoặc object ở field đáng lẽ phải là array, ta có thể kiểm tra kiểu bằng `$isArray`:

```javascript
db.arrayCases.aggregate([
  {
    $project: {
      name: 1,
      normalizedTags: {
        $cond: {
          if: { $isArray: "$tags" },
          then: "$tags",
          else: []
        }
      }
    }
  }
])
```

Phép này biến mọi giá trị không phải array thành `[]` trong response, kể cả string sai kiểu. Chỉ dùng khi đây là chính sách hiển thị đã được thống nhất; **không** nên âm thầm che lỗi schema mà không có theo dõi hoặc kế hoạch sửa dữ liệu.

### `$unwind` đối với mảng rỗng và null

`$unwind` tách một document có array thành nhiều document, mỗi document tương ứng một phần tử. Mặc định, mảng rỗng, field null và field thiếu không tạo ra phần tử đầu ra:

```javascript
db.arrayCases.aggregate([
  { $unwind: "$tags" },
  { $project: { name: 1, tags: 1 } }
])
```

Một array `[null]` có **một phần tử**, nên có thể tạo ra một kết quả unwind với `tags: null`. Điều này khác với `[]`, vốn không có phần tử để tách.

Để giữ cả các document có array rỗng, null hoặc thiếu field:

```javascript
db.arrayCases.aggregate([
  {
    $unwind: {
      path: "$tags",
      preserveNullAndEmptyArrays: true
    }
  }
])
```

`preserveNullAndEmptyArrays: true` giúp giữ document đầu vào trong các tình huống không có phần tử để unwind, nhưng hình dạng field sau unwind có thể khác nhau theo nguồn là array rỗng, null hay field thiếu. Khi downstream cần phân biệt các trạng thái, hãy giữ hoặc tính thêm một field mô tả trạng thái trước bước `$unwind`.

## 11. Tính kích thước mảng trong aggregation một cách an toàn

Toán tử truy vấn `$size: 0` ở mục 3 được dùng trực tiếp trong `find()`. Trong aggregation, `$size` là một **biểu thức** dùng để tính độ dài mảng:

```javascript
db.arrayCases.aggregate([
  {
    $project: {
      name: 1,
      tagCount: {
        $cond: {
          if: { $isArray: "$tags" },
          then: { $size: "$tags" },
          else: null
        }
      }
    }
  }
])
```

Trong pipeline này:

- `a` có `tagCount: 0`.
- `b`, `f`, `g` có `tagCount: 1`.
- `c`, `i` có `tagCount: 2`.
- `d`, `e`, `h` có `tagCount: null` vì không phải array.

Nếu viết `{ $size: "$tags" }` trực tiếp khi `tags` có thể null, missing hoặc string, biểu thức aggregation `$size` có thể gây lỗi do nhận giá trị không phải mảng. Do đó, `$cond` kết hợp `$isArray` là cách diễn đạt rõ ràng hơn trên dữ liệu không đồng nhất.

Để tìm document có array rỗng thông qua `$expr`, có thể viết:

```javascript
db.arrayCases.find({
  $expr: {
    $cond: {
      if: { $isArray: "$tags" },
      then: { $eq: [{ $size: "$tags" }, 0] },
      else: false
    }
  }
})
```

Bộ lọc này chỉ khớp khi field thực sự là array và array đó dài 0. Với yêu cầu đơn giản này, **`{ tags: { $size: 0 } }`** thường dễ đọc hơn.

## 12. Cập nhật: tạo mảng rỗng khác với xóa field hoặc gán null

Ba thao tác cập nhật sau có kết quả dữ liệu khác nhau:

### 12.1. Gán mảng rỗng

```javascript
db.arrayCases.updateOne(
  { _id: "f" },
  { $set: { tags: [] } }
)
```

Sau khi chạy, document `f` **vẫn có field** `tags`, và `tags` là mảng có 0 phần tử. Bộ lọc `$exists: true`, `$type: "array"` và `$size: 0` đều khớp.

### 12.2. Gán null

```javascript
db.arrayCases.updateOne(
  { _id: "f" },
  { $set: { tags: null } }
)
```

Sau đó `tags` tồn tại nhưng mang kiểu BSON Null. `$exists: true` vẫn khớp, còn `$size: 0` và `$type: "array"` không khớp.

### 12.3. Xóa field

```javascript
db.arrayCases.updateOne(
  { _id: "f" },
  { $unset: { tags: "" } }
)
```

Sau đó field `tags` **không còn tồn tại**; `$exists: false` mới là bộ lọc tương ứng.

Các lệnh trên cùng sửa `f` liên tiếp; nếu chạy cả ba, kết quả cuối là **field bị xóa**. Để quan sát từng trạng thái, đọc document sau mỗi lệnh bằng:

```javascript
db.arrayCases.findOne({ _id: "f" })
```

### Thêm phần tử null bằng `$push`

```javascript
db.arrayCases.updateOne(
  { _id: "a" },
  { $push: { tags: null } }
)
```

Từ `tags: []`, thao tác này tạo thành `tags: [null]`; độ dài array tăng từ 0 lên 1. Nếu field thiếu, `$push` có thể tạo một array mới; nhưng nếu field có giá trị `null` hoặc một scalar không phải array, `$push` có thể báo lỗi vì không thể thêm phần tử vào một giá trị không phải mảng. Điều này cho thấy “null/missing/[]” không thể mặc nhiên thay thế lẫn nhau trong logic cập nhật.

## 13. Truy vấn tương ứng trong Java MongoDB Sync Driver

Trong ứng dụng Java, có thể sử dụng `Filters` để xây dựng các bộ lọc tương đương với `mongosh`. Ví dụ:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class ArrayEdgeCaseQuery {

    private static void printIds(
            String title,
            MongoCollection<Document> collection,
            org.bson.conversions.Bson filter) {
        System.out.println(title);
        for (Document item : collection.find(filter)
                .projection(new Document("_id", 1))
                .sort(new Document("_id", 1))) {
            System.out.println(item.getString("_id"));
        }
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu biến môi trường MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("mongo_array_lab");
            MongoCollection<Document> cases =
                db.getCollection("arrayCases");

            // tags là array có đúng 0 phần tử
            printIds("Array rỗng", cases, Filters.size("tags", 0));

            // Document không có field tags
            printIds("Thiếu tags", cases, Filters.exists("tags", false));

            // Equality với null có thể khớp cả missing và array chứa null
            printIds("Equality null", cases, Filters.eq("tags", null));

            // Phần tử trực tiếp null ở trong array
            Document arrayContainsNull = new Document(
                "tags",
                new Document("$elemMatch", new Document("$eq", null))
            );
            printIds("Array chứa null", cases, arrayContainsNull);

            // Kiểu BSON của toàn field tags là Null
            Document directNull = Document.parse(
                "{ \"$expr\": { \"$eq\": [ { \"$type\": \"$tags\" }, \"null\" ] } }"
            );
            printIds("Field trực tiếp null", cases, directNull);
        }
    }
}
```

Ví dụ dùng MongoDB Java Sync Driver với dependency `mongodb-driver-sync` tương thích. Nó đọc collection `arrayCases` đã được tạo trong phần thực hành và lấy URI từ biến môi trường để tránh viết mật khẩu trong mã nguồn.

Những helper chính:

| Java Driver | Ý nghĩa tương ứng trong `mongosh` |
| --- | --- |
| `Filters.size("tags", 0)` | `{tags: {$size: 0}}` |
| `Filters.exists("tags", false)` | `{tags: {$exists: false}}` |
| `Filters.eq("tags", null)` | `{tags: null}` |
| `new Document("tags", new Document("$elemMatch", ...))` | Điều kiện trên một phần tử của array |
| `Document.parse(... $expr ...)` | So sánh kiểu BSON trực tiếp bằng aggregation expression |

Các truy vấn không sửa dữ liệu. Khi giao tiếp qua JSON API, cần giữ rõ ranh giới giữa field không có trong payload, field bằng `null` và field bằng `[]`, vì trình tuần tự hóa hoặc lớp mapping có thể làm chúng trở nên giống nhau ở tầng ứng dụng nếu cấu hình không cẩn thận.

## 14. Thiết kế schema để giảm các trạng thái mơ hồ

MongoDB cho phép document linh hoạt khi không có validator, nhưng một collection sản xuất có thể đặt hợp đồng rõ ràng cho `tags`. Ví dụ: field `tags` là tùy chọn; nếu có, nó phải là **array chứa string**, có thể rỗng:

```javascript
db.createCollection("articles", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        tags: {
          bsonType: "array",
          items: {
            bsonType: "string"
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

Với validator này:

- `{ title: "Bài chưa có tags" }` có thể hợp lệ vì `tags` không nằm trong `required`.
- `{ tags: [] }` hợp lệ.
- `{ tags: ["mongodb", "java"] }` hợp lệ.
- `{ tags: [null] }`, `{ tags: null }` và `{ tags: "mongodb" }` không hợp lệ vì không đúng schema đã khai báo.

Nếu nghiệp vụ muốn **field luôn tồn tại**, thêm:

```javascript
required: ["tags"]
```

ở cấp object schema. Khi đó missing không còn được chấp nhận, nhưng `[]` vẫn hợp lệ. Nếu bắt buộc array có **ít nhất một phần tử**, thêm `minItems: 1` vào schema của `tags`:

```javascript
tags: {
  bsonType: "array",
  minItems: 1,
  items: { bsonType: "string" }
}
```

Không nên áp `minItems: 1` nếu mảng rỗng là trạng thái nghiệp vụ hợp pháp, chẳng hạn bài viết chưa được gắn nhãn.

Khi collection hiện có đã chứa dữ liệu sai kiểu, việc thêm validator bằng `collMod` **không tự sửa các document cũ**. Cần quyết định cách migration, chế độ `validationLevel` và `validationAction` phù hợp trước khi buộc toàn bộ thao tác ghi mới tuân thủ schema.

## 15. Hiệu năng và index liên quan đến mảng

MongoDB có thể tạo index trên field array, tạo ra **multikey index** khi cần. Ví dụ:

```javascript
db.arrayCases.createIndex({
  tags: 1
})
```

Index trên array có thể hỗ trợ một số truy vấn tìm **giá trị phần tử** như `{ tags: "mongo" }`. Tuy nhiên, điều kiện `$size` **không sử dụng index để giải quyết trực tiếp phần so sánh kích thước mảng**. Nếu ứng dụng thường xuyên cần lọc theo số lượng phần tử ở quy mô lớn, có thể cân nhắc lưu thêm một trường `tagsCount` được cập nhật nhất quán với `tags`, rồi đánh index trên trường đếm đó.

Ví dụ:

```javascript
{
  _id: "article-01",
  tags: ["mongodb", "query"],
  tagsCount: 2
}
```

Nhược điểm của cách lưu thêm số đếm là phải bảo đảm cập nhật `tagsCount` đồng thời mỗi khi `tags` thay đổi. Nếu không, truy vấn dựa trên số đếm có thể trả về kết quả sai. Chỉ đưa dữ liệu dẫn xuất này vào schema khi yêu cầu hiệu năng và cách duy trì tính nhất quán được xác định rõ.

Với `$exists` và `$type`, hiệu quả index cũng phụ thuộc loại index, tính phân bố dữ liệu và kế hoạch truy vấn. Không nên suy diễn từ việc collection có index rằng mọi truy vấn null/missing/array sẽ nhanh; nên dùng:

```javascript
db.arrayCases.find({
  tags: { $size: 0 }
}).explain("executionStats")
```

để quan sát kế hoạch thực thi trên dữ liệu và môi trường mục tiêu.

## 16. Các nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
| --- | --- | --- |
| `[]` và `[null]` đều là “không có phần tử” | Đếm phần tử sai | `[]` có 0, `[null]` có 1 phần tử |
| `tags: null` và thiếu `tags` giống nhau | Không phân biệt đã khởi tạo hay chưa có dữ liệu | Một bên có field kiểu Null, bên kia thiếu field |
| `{tags: null}` chỉ tìm field trực tiếp bằng null | Trả cả document thiếu field hoặc chứa null trong array | Dùng `$exists`, `$elemMatch` hoặc aggregation `$type` tùy nhu cầu |
| `{tags: {$type: "null"}}` chỉ tìm field trực tiếp bằng null | Có thể khớp array chứa phần tử null | Dùng `$expr` với `{$type: "$tags"}` để xét kiểu toàn field |
| `{tags: {$exists: true}}` nghĩa là có phần tử | Khớp cả `tags: []` và `tags: null` | `$exists` kiểm tra sự hiện diện của field, không đo kích thước |
| `{tags: {$size: 0}}` khớp null/missing | Bỏ sót các document đó | `$size: 0` chỉ khớp array rỗng |
| `{tags: []}` luôn đồng nghĩa array ngoài cùng rỗng | Nhầm khi có nested array | Dùng `$size: 0` nếu cần chắc chắn kích thước array ngoài |
| `$all: []` dùng để tìm array rỗng | Kết quả không đúng | Dùng `$size: 0` |
| `$ifNull` biến `[null]` thành `[]` | Diễn giải sai kết quả aggregation | `$ifNull` chỉ thay khi giá trị biểu thức là null/missing, không tự lọc phần tử |
| `$push` vào `tags: null` tự hoạt động như mảng rỗng | Thao tác update lỗi | Khởi tạo array đúng kiểu hoặc sửa dữ liệu trước |
| Đổi validator sẽ tự sửa dữ liệu cũ | Document sai kiểu vẫn tồn tại | Schema validation không phải migration |

## 17. Bài tập thực hành

### Bài 1. Phân loại năm trạng thái của field

Cho các document:

```javascript
{ _id: 1, values: [] }
{ _id: 2, values: [null] }
{ _id: 3, values: null }
{ _id: 4 }
{ _id: 5, values: ["A"] }
```

Hãy cho biết `values: {$size: 0}`, `values: {$exists: false}` và `values: null` khớp những `_id` nào.

**Đáp án tham khảo:**

- `{ values: { $size: 0 } }` khớp `1`.
- `{ values: { $exists: false } }` khớp `4`.
- `{ values: null }` khớp `2, 3, 4`.

### Bài 2. Tìm array có phần tử null nhưng không lấy field null

Dùng dữ liệu bài 1, viết truy vấn chỉ lấy document có `values` là array chứa phần tử `null`.

**Đáp án tham khảo:**

```javascript
db.sample.find({
  values: {
    $elemMatch: { $eq: null }
  }
})
```

Kết quả là `_id: 2`. Collection `sample` ở đây là tên gợi ý; để chạy trực tiếp, hãy chèn dữ liệu vào collection này trước.

### Bài 3. Phân biệt mảng rỗng và mảng chứa mảng rỗng

Cho:

```javascript
{ _id: "x", a: [] }
{ _id: "y", a: [[]] }
{ _id: "z", a: [[], []] }
```

Truy vấn nào chắc chắn chỉ tìm `x` khi muốn **mảng ngoài cùng có 0 phần tử**?

**Đáp án:**

```javascript
db.sample.find({ a: { $size: 0 } })
```

`y` có một phần tử, `z` có hai phần tử; dù các phần tử bên trong là mảng rỗng, mảng ngoài của chúng không rỗng.

### Bài 4. Field con null trong array object

Cho:

```javascript
{ _id: "p1", contacts: [{ type: "email", value: null }] }
{ _id: "p2", contacts: [{ type: "email" }] }
{ _id: "p3", contacts: [] }
```

Hãy viết hai bộ lọc:

1. Có contact loại `email` với `value` thực sự mang kiểu Null.
2. Có contact loại `email` nhưng hoàn toàn thiếu field `value`.

**Đáp án:**

```javascript
// 1. Field con value là BSON Null
db.people.find({
  contacts: {
    $elemMatch: {
      type: "email",
      value: { $type: "null" }
    }
  }
})

// 2. Field con value không tồn tại
db.people.find({
  contacts: {
    $elemMatch: {
      type: "email",
      value: { $exists: false }
    }
  }
})
```

Truy vấn đầu khớp `p1`; truy vấn sau khớp `p2`. `p3` có mảng rỗng nên không chứa phần tử nào thỏa `$elemMatch`.

### Bài 5. Cần field luôn là array

Một hệ thống muốn mọi bài viết đều có `tags`, dù không gắn nhãn nào. Field này phải là array các string và có thể bằng `[]`. Hỏi quy tắc JSON Schema nào phù hợp?

**Đáp án tham khảo:**

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["tags"],
    properties: {
      tags: {
        bsonType: "array",
        items: { bsonType: "string" }
      }
    }
  }
}
```

Quy tắc này phân biệt dứt khoát field thiếu, field null, array chứa null và array rỗng hợp lệ.

## 18. Cách chọn bộ lọc theo ý định

Khi đọc yêu cầu nghiệp vụ, hãy chuyển thành một câu mô tả kiểu BSON thật rõ trước khi viết query:

1. **“Danh sách tồn tại nhưng chưa có phần tử”** → `{ tags: { $size: 0 } }`.
2. **“Chưa từng lưu field danh sách”** → `{ tags: { $exists: false } }`.
3. **“Có field tags, kiểu array”** → `{ tags: { $type: "array" } }`.
4. **“Mảng có ít nhất một phần tử null”** → `{ tags: { $elemMatch: { $eq: null } } }`.
5. **“Toàn field tags có giá trị BSON Null”** → `$expr` kiểm tra `{$type: "$tags"}` bằng `"null"`.
6. **“Một phần tử object của array thiếu field con”** → dùng `$elemMatch` với `$exists: false` tại field con.

Truy vấn mảng trong MongoDB chính xác khi ta giữ riêng ba khái niệm: **số phần tử của array**, **kiểu/giá trị của phần tử** và **sự tồn tại của field**. Mảng `[]` không phải `[null]`; `null` không phải missing; và truy vấn equality với `null` thường rộng hơn trực giác ban đầu. Việc xác định đúng cấu trúc trước khi lọc giúp ứng dụng xử lý dữ liệu linh hoạt mà vẫn giữ được ý nghĩa nghiệp vụ.
