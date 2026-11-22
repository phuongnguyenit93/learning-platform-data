# Kiểm chứng biểu thức aggregation trên dữ liệu `null`, sai kiểu và trường không tồn tại trong MongoDB

Aggregation pipeline là công cụ mạnh để tính toán và biến đổi document trong MongoDB. Một biểu thức như `$multiply`, `$size`, `$trim` hoặc `$dateToString` rất dễ viết khi mọi document đều có cấu trúc chuẩn. Vấn đề xuất hiện khi dữ liệu thực tế không đồng nhất: một bản ghi có `amount: null`, bản ghi khác thiếu hẳn `amount`, bản ghi thứ ba lưu `amount` thành chuỗi `"99.50"` thay vì kiểu số, và bản ghi thứ tư chứa một mảng không hợp lệ.

Những trạng thái này **không có cùng ý nghĩa** và các aggregation expression **không xử lý chúng theo một quy tắc chung duy nhất**. Có toán tử trả `null`, có toán tử giữ nguyên giá trị, có toán tử so sánh theo thứ tự BSON, và có toán tử khiến cả pipeline báo lỗi. Vì thế, việc kiểm chứng biểu thức phải dựa trên **giá trị, kiểu BSON và sự tồn tại của field**, chứ không chỉ thử với một document “đẹp”.

Bài học thuộc chương **Biểu thức aggregation** và tập trung vào kỹ thuật xây dựng biểu thức chịu được dữ liệu bất thường:

- Nhận diện field **missing**, field mang BSON **Null**, giá trị sai kiểu và giá trị hợp lệ nhưng ở biên như `0`, `""`, `[]`.
- Dùng `$type`, `$isNumber`, `$isArray`, `$ifNull`, `$cond`, `$switch` để **phân loại trước khi tính**.
- Dùng `$convert` với `onError`/`onNull` khi cần chuyển kiểu có kiểm soát.
- Bảo vệ các biểu thức xử lý **số, chuỗi, mảng và ngày tháng** khỏi lỗi do dữ liệu thực tế.
- Thiết kế tập ca kiểm thử và đối chiếu kết quả qua `mongosh` hoặc MongoDB Java Sync Driver.

## 1. Bốn trạng thái dữ liệu thường bị nhầm lẫn

Xem các document:

```javascript
{ _id: "a", amount: NumberInt(100) }
{ _id: "b", amount: null }
{ _id: "c" }
{ _id: "d", amount: "100" }
```

Từ phía ứng dụng, bốn bản ghi có thể đều được hiển thị thành một giá trị “100 hoặc trống”, nhưng ở mức MongoDB:

| Document | Tình trạng field `amount` | Kiểu BSON | Ý nghĩa trong aggregation |
| --- | --- | --- | --- |
| `a` | Có field, giá trị số nguyên | `int` | Có thể dùng làm toán hạng số |
| `b` | Có field, giá trị `null` | `null` | Một giá trị Null thật sự |
| `c` | Không có field | `missing` khi dùng aggregation `$type` | Không có giá trị để tham chiếu |
| `d` | Có field, chữ số lưu dưới dạng chuỗi | `string` | **Không tự động là số** trong mọi toán tử |

Một số điểm quan trọng:

1. **Missing không phải Null**: `{ amount: null }` vẫn có field `amount`; document `c` thì không có field này.
2. **Chuỗi có hình dạng số không phải BSON number**: `"100"` khác `NumberInt(100)`; có thể chuyển kiểu khi chính sách nghiệp vụ cho phép.
3. **Giá trị ở biên không mặc nhiên là lỗi**: số `0`, chuỗi rỗng `""` và mảng `[]` là những giá trị hiện diện, có kiểu cụ thể.
4. **Không phải toán tử nào cũng chấp nhận mọi loại đầu vào**: `$size` đòi hỏi array, còn `$trim` đòi hỏi chuỗi phù hợp.

Quy trình an toàn thường là:

```text
Document đầu vào
       |
       v
Kiểm tra field tồn tại và kiểu BSON
       |
       +---- Hợp lệ ----------> Thực hiện biểu thức
       |                              |
       |                              v
       |                         Kết quả mong muốn
       |
       +---- Null / missing ---> Giá trị thay thế có chủ đích
       |
       +---- Sai kiểu ---------> Báo lỗi, gắn nhãn lỗi,
                                 hoặc chuyển kiểu có kiểm soát
```

Mấu chốt là **phân biệt lỗi dữ liệu với giá trị nghiệp vụ hợp lệ** trước khi chọn có thay thế giá trị hay không.

## 2. Tạo bộ dữ liệu thử nghiệm có cả trường hợp hợp lệ và bất thường

Trong `mongosh`, chọn database thực hành:

```javascript
use mongo_expression_lab
```

Chạy một lần trên collection `expressionCases` mới hoặc trống:

```javascript
db.expressionCases.insertMany([
  {
    _id: "ok",
    amount: NumberDecimal("120.50"),
    quantity: NumberInt(2),
    tags: ["mongodb", "java"],
    title: "  MongoDB cơ bản  ",
    occurredAt: ISODate("2026-11-10T14:20:00Z")
  },
  {
    _id: "zero",
    amount: NumberInt(0),
    quantity: NumberInt(0),
    tags: [],
    title: "",
    occurredAt: ISODate("2026-11-11T14:20:00Z")
  },
  {
    _id: "null",
    amount: null,
    quantity: null,
    tags: null,
    title: null,
    occurredAt: null
  },
  {
    _id: "missing"
    // Thiếu amount, quantity, tags, title, occurredAt
  },
  {
    _id: "numericString",
    amount: "99.50",
    quantity: "3",
    tags: ["mongodb"],
    title: 42,
    occurredAt: "2026-11-12T00:00:00Z"
  },
  {
    _id: "badString",
    amount: "N/A",
    quantity: "unknown",
    tags: "mongodb",
    title: ["không", "phải", "chuỗi"],
    occurredAt: "hôm qua"
  },
  {
    _id: "partial",
    amount: NumberInt(10),
    quantity: NumberInt(3),
    tags: [null],
    title: "  Dữ liệu  ",
    occurredAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: "wrongObject",
    amount: [10],
    quantity: [1],
    tags: { first: "mongodb" },
    title: true,
    occurredAt: { year: 2026 }
  },
  {
    _id: "negative",
    amount: NumberInt(-10),
    quantity: NumberInt(-2),
    tags: ["java"],
    title: "   ",
    occurredAt: ISODate("2026-11-13T03:00:00Z")
  },
  {
    _id: "boolean",
    amount: true,
    quantity: false,
    tags: [],
    title: "Bài viết",
    occurredAt: NumberInt(123)
  },
  {
    _id: "mixedTags",
    amount: NumberDecimal("33.25"),
    quantity: NumberInt(2),
    tags: ["mongodb", NumberInt(1)],
    title: "Báo cáo",
    occurredAt: ISODate("2026-11-13T10:00:00Z")
  }
])
```

Lưu ý:

- `NumberInt(0)` là số nguyên hợp lệ và khác `null`.
- `NumberDecimal("120.50")` là Decimal128, không phải string.
- `ISODate(...)` tạo BSON Date; chuỗi `"2026-11-12T00:00:00Z"` vẫn có kiểu String.
- `tags: []` có kiểu Array và độ dài 0; `tags: [null]` có kiểu Array và độ dài 1.
- `tags: { first: "mongodb" }` có kiểu Object, không phải Array.

Bộ dữ liệu cố tình có nhiều giá trị bất thường. Nó dành cho **kiểm chứng biểu thức**, không đại diện cho schema nên được chấp nhận ở hệ thống sản xuất. Các lệnh đọc ở các phần tiếp theo không sửa document. Không chèn lặp các `_id` trên cùng collection vì có thể gặp lỗi duplicate key.

## 3. Dùng aggregation `$type` để biết field là gì

Trong aggregation, `$type` trả về chuỗi mô tả kiểu BSON của giá trị biểu thức:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      quantityType: { $type: "$quantity" },
      tagsType: { $type: "$tags" },
      titleType: { $type: "$title" },
      occurredAtType: { $type: "$occurredAt" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Ví dụ, các giá trị đáng chú ý của `amountType` là:

| `_id` | `amount` nguồn | `{$type: "$amount"}` |
| --- | --- | --- |
| `ok` | `NumberDecimal("120.50")` | `"decimal"` |
| `zero` | `NumberInt(0)` | `"int"` |
| `null` | `null` | `"null"` |
| `missing` | Không có field | `"missing"` |
| `numericString` | `"99.50"` | `"string"` |
| `badString` | `"N/A"` | `"string"` |
| `wrongObject` | `[10]` | `"array"` |
| `boolean` | `true` | `"bool"` |

**Điểm đặc biệt:** aggregation `$type` đánh giá **kiểu của cả giá trị được tham chiếu**. Nếu `tags` là `[null]`, `{$type:"$tags"}` trả `"array"`, không phải `"null"`. Nếu field không tồn tại, biểu thức trả `"missing"`.

### Phân biệt aggregation `$type` với toán tử truy vấn `$type`

```javascript
// Query operator trong $match / find:
db.expressionCases.find({
  tags: { $type: "null" }
})

// Aggregation expression trong $project:
db.expressionCases.aggregate([
  {
    $project: {
      tagsType: { $type: "$tags" }
    }
  }
])
```

Query operator `$type` có thể khớp **kiểu của một phần tử trong mảng**: một field `tags: [null]` có thể khớp `{tags: {$type:"null"}}`. Trong khi đó aggregation `$type` trên `"$tags"` cho biết kiểu của **toàn field** là Array.

Không lấy kết luận của dạng `find({field: {$type: ...}})` áp máy móc cho `{$type:"$field"}` trong `$project` hoặc `$expr`.

### Vì sao `$exists` không thay thế được aggregation `$type`?

`$exists` là **query operator**, thường dùng trong `find()` hoặc `$match`:

```javascript
db.expressionCases.find({
  amount: { $exists: false }
})
```

Nó kiểm tra có khóa `amount` hay không, không phân biệt kiểu khác nhau khi field đã hiện diện. Trong các biểu thức tính toán bên trong `$project`, muốn nhận diện missing hãy dùng:

```javascript
{
  $eq: [
    { $type: "$amount" },
    "missing"
  ]
}
```

Không viết `{$exists: false}` như một aggregation expression ở nơi MongoDB đang chờ một phép tính; đó là hai ngữ cảnh cú pháp khác nhau.

## 4. `$isNumber` và `$isArray`: kiểm tra kiểu trước khi tính

Các biểu thức kiểm tra nhanh:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      amountIsNumber: { $isNumber: "$amount" },
      tagsIsArray: { $isArray: "$tags" }
    }
  },
  { $sort: { _id: 1 } }
])
```

`$isNumber` trả `true` khi giá trị biểu thức là một kiểu số BSON được hỗ trợ, chẳng hạn Int32, Int64, Double hoặc Decimal128. Nó trả `false` cho `null`, missing, boolean, array, object và **chuỗi chứa chữ số**.

`$isArray` trả `true` nếu **toàn giá trị** là array, kể cả `[]` hoặc `[null]`. Nó không kiểm tra liệu **các phần tử bên trong** có đúng kiểu không.

Một số kết quả đáng chú ý:

| Case | `amountIsNumber` | `tagsIsArray` |
| --- | --- | --- |
| `ok` | `true` | `true` |
| `zero` | `true` | `true` |
| `null` | `false` | `false` |
| `missing` | `false` | `false` |
| `numericString` | `false` | `true` |
| `badString` | `false` | `false` |
| `partial` | `true` | `true` |
| `wrongObject` | `false` | `false` |
| `boolean` | `false` | `true` |

Nếu yêu cầu không chỉ là “một kiểu số bất kỳ” mà là **số nguyên BSON**, có thể kiểm tra:

```javascript
{
  $in: [
    { $type: "$quantity" },
    ["int", "long"]
  ]
}
```

`$isNumber` phù hợp cho nhiều phép tính, nhưng ràng buộc chỉ nhận Int32/Int64 hoặc chỉ nhận Decimal128 cần chính sách kiểu cụ thể hơn. Ví dụ `$isNumber: "$amount"` không tự bảo đảm `amount >= 0`.

## 5. `$ifNull`: thay thế Null và missing, không sửa sai kiểu

`$ifNull` chọn giá trị thay thế khi đầu vào có giá trị null hoặc thiếu:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      amountForDisplay: {
        $ifNull: ["$amount", "Chưa có"]
      },
      titleForDisplay: {
        $ifNull: ["$title", "Không có tiêu đề"]
      }
    }
  }
])
```

Với `null` và `missing`, `amountForDisplay` trở thành `"Chưa có"`. Với `amount: 0`, kết quả vẫn là `0`. Với `amount: "N/A"`, kết quả vẫn là `"N/A"`: **`$ifNull` không xác nhận hay sửa kiểu dữ liệu**.

| Đầu vào | `$ifNull: ["$amount", 0]` |
| --- | --- |
| `NumberInt(0)` | Giữ `0` |
| `NumberDecimal("25.00")` | Giữ số Decimal128 |
| `null` | Trả `0` |
| Missing | Trả `0` |
| `"99.50"` | Giữ chuỗi `"99.50"` |
| `"N/A"` | Giữ chuỗi `"N/A"` |
| `[10]` | Giữ array `[10]` |

Đối với báo cáo, **thay null bằng 0 là một quyết định nghiệp vụ**. Nếu `amount: null` nghĩa là “chưa xác nhận giá trị”, gán 0 có thể làm tổng hoặc trung bình bị sai. Đôi khi cần giữ null, tách riêng số bản ghi thiếu, hoặc trả thêm một nhãn trạng thái.

Trong những phiên bản hỗ trợ nhiều đối số `$ifNull`, có thể xét nhiều nguồn thay thế; ví dụ ở đây dùng dạng hai đối số để làm rõ quy tắc cơ bản.

## 6. `$convert`: chuyển kiểu có kiểm soát bằng `onError` và `onNull`

Khi nguồn dữ liệu cũ lưu giá tiền dạng chuỗi `"99.50"`, hệ thống có thể muốn chuyển thành Decimal128 cho báo cáo. Nếu dùng chuyển kiểu dạng rút gọn:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      amountDecimal: { $toDecimal: "$amount" }
    }
  }
])
```

pipeline có thể **báo lỗi** khi gặp `amount: "N/A"` hoặc một giá trị không thể chuyển. Một record sai kiểu có thể khiến toàn bộ lệnh aggregation thất bại; vì thế kiểm tra duy nhất record `"99.50"` là chưa đủ.

Sử dụng `$convert` để chọn cách xử lý lỗi:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      originalType: { $type: "$amount" },
      convertedAmount: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Ý nghĩa:

- `input`: biểu thức lấy giá trị cần chuyển.
- `to`: kiểu BSON đích; `"decimal"` biểu diễn Decimal128.
- `onError`: giá trị khi gặp lỗi chuyển kiểu, ví dụ chuỗi không có định dạng số hợp lệ.
- `onNull`: giá trị khi input là null hoặc missing.

Với `"99.50"`, kết quả là một Decimal128 tương ứng. Với `"N/A"`, `onError: null` ngăn lỗi chuyển kiểu và đánh dấu không chuyển được.

**Quan trọng:** chuyển kiểu thành công **không đồng nghĩa đầu vào hợp lệ theo nghiệp vụ**. Một số kiểu như boolean có thể có quy tắc chuyển sang số trong MongoDB, nhưng nếu hợp đồng dữ liệu yêu cầu `amount` phải là một số hoặc chuỗi số thì bạn vẫn phải **kiểm tra kiểu nguồn trước**. Đừng mặc định chấp nhận mọi kiểu chỉ vì `$convert` có thể tạo ra một số.

### 6.1. Chỉ cho phép giá trị nguồn thuộc các kiểu xác định

Ví dụ chính sách nhập liệu: chấp nhận số BSON và chuỗi có thể chuyển thành Decimal128; không chấp nhận boolean hay array.

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      rawType: { $type: "$amount" },
      safeAmount: {
        $cond: {
          if: {
            $in: [
              { $type: "$amount" },
              ["int", "long", "double", "decimal", "string"]
            ]
          },
          then: {
            $convert: {
              input: "$amount",
              to: "decimal",
              onError: null,
              onNull: null
            }
          },
          else: null
        }
      }
    }
  }
])
```

Giá trị `true` (bool), object và array bị loại ngay từ điều kiện kiểu. Chuỗi `"99.50"` có thể chuyển thành Decimal128; chuỗi `"N/A"` đi qua nhánh chuyển nhưng trả null nhờ `onError`.

Nếu cần phân biệt **missing**, **null**, **sai kiểu** và **chuỗi chuyển lỗi**, không nên chỉ trả `safeAmount: null`, vì các nguyên nhân này bị gộp. Hãy giữ `rawType` và thêm nhãn kiểm chứng ở mục tiếp theo.

### 6.2. Lỗi dữ liệu không nên bị che giấu hoàn toàn

Trong một số pipeline giao diện, `onError: null` là cách chấp nhận được để không làm sập màn hình đọc. Nhưng đối với báo cáo tài chính hoặc nhập liệu sản xuất, nhiều giá trị chuyển lỗi có thể làm báo cáo thiếu tiền mà người dùng không biết.

Một lựa chọn tốt hơn là trả kèm `sourceType`, `conversionSucceeded` hoặc đếm số bản ghi không chuyển được, đồng thời có chính sách sửa dữ liệu nguồn. `$convert` là công cụ chuyển kiểu, **không thay thế schema validation hoặc giám sát chất lượng dữ liệu**.

## 7. `$switch`: phân loại nguyên nhân dữ liệu bất thường

`$switch` cho phép kiểm tra nhiều trường hợp theo thứ tự, mỗi nhánh gồm `case` và `then`, với nhánh mặc định `default`.

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountStatus: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [{ $type: "$amount" }, "missing"]
              },
              then: "missing"
            },
            {
              case: {
                $eq: [{ $type: "$amount" }, "null"]
              },
              then: "null"
            },
            {
              case: { $isNumber: "$amount" },
              then: "numeric"
            },
            {
              case: {
                $eq: [{ $type: "$amount" }, "string"]
              },
              then: "string"
            }
          ],
          default: "unsupported-type"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Phân loại một số document:

| Case | `amountStatus` |
| --- | --- |
| `ok`, `zero`, `partial`, `negative`, `mixedTags` | `numeric` |
| `null` | `null` |
| `missing` | `missing` |
| `numericString`, `badString` | `string` |
| `wrongObject`, `boolean` | `unsupported-type` |

Điều kiện `$isNumber` xác nhận **kiểu**, không xác nhận dấu của giá trị: `amount: -10` vẫn ở nhóm numeric. Nếu nghiệp vụ không cho phép tiền âm, cần ràng buộc bổ sung.

### Phân loại giá trị âm nhưng tránh so sánh sai kiểu

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountIsNonNegative: {
        $cond: {
          if: { $isNumber: "$amount" },
          then: { $gte: ["$amount", 0] },
          else: false
        }
      }
    }
  }
])
```

Biểu thức chỉ so sánh `$gte` khi `amount` là number. `negative` nhận `false`, `zero` nhận `true`, còn `null`, missing, string và bool nhận `false`.

**Không nên chỉ viết** `{$gte:["$amount",0]}` rồi hiểu mọi kết quả true là “số không âm”. Trong aggregation expressions, phép so sánh giữa **những kiểu BSON khác nhau** có thể dựa trên thứ tự so sánh BSON thay vì ép mọi giá trị thành số. Một chuỗi có thể so sánh với số theo thứ tự kiểu, dẫn đến kết luận sai về miền giá trị. Hãy kiểm tra kiểu trước khi áp dụng phép so sánh số.

## 8. Bảo vệ phép toán số: `$multiply`, `$divide` và số 0

Giả sử một document đại diện cho giao dịch có `amount` là đơn giá và `quantity` là số lượng. Mục tiêu là tính `lineTotal = amount * quantity`.

### 8.1. Phép tính trực tiếp có thể không an toàn

```javascript
// Chỉ thích hợp khi nguồn đã bảo đảm kiểu số phù hợp
db.expressionCases.aggregate([
  {
    $project: {
      lineTotal: {
        $multiply: ["$amount", "$quantity"]
      }
    }
  }
])
```

Collection mẫu có string, array, bool và null/missing, vì vậy không thể coi tất cả document đều là đối số hợp lệ của phép nhân. Một phép toán gặp đầu vào sai kiểu có thể khiến lệnh aggregation báo lỗi; chính sách trả null của một trường hợp không đại diện cho mọi trường hợp.

### 8.2. Kiểm tra kiểu và miền giá trị trước khi nhân

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      lineTotal: {
        $cond: {
          if: {
            $and: [
              { $isNumber: "$amount" },
              {
                $in: [
                  { $type: "$quantity" },
                  ["int", "long"]
                ]
              },
              {
                $cond: {
                  if: { $isNumber: "$amount" },
                  then: { $gte: ["$amount", 0] },
                  else: false
                }
              },
              {
                $cond: {
                  if: {
                    $in: [
                      { $type: "$quantity" },
                      ["int", "long"]
                    ]
                  },
                  then: { $gte: ["$quantity", 0] },
                  else: false
                }
              }
            ]
          },
          then: { $multiply: ["$amount", "$quantity"] },
          else: null
        }
      }
    }
  }
])
```

Ở ví dụ này:

- `ok`: `120.50 * 2 = 241.00`.
- `zero`: `0 * 0 = 0` — **số 0 hợp lệ**.
- `partial`: `10 * 3 = 30`.
- `mixedTags`: `33.25 * 2 = 66.50`.
- `negative`: trả null do giá trị âm bị chính sách nghiệp vụ từ chối.
- `numericString`: trả null vì chuỗi `"99.50"` và `"3"` không được chấp nhận là số BSON trong biểu thức nghiêm ngặt này.
- `null`, `missing`, `badString`, `wrongObject`, `boolean`: trả null thay vì cố nhân kiểu không hợp lệ.

Các nhánh `$cond` bao quanh phép so sánh và `$multiply` nhằm chỉ thực hiện chúng khi đã có đầu vào phù hợp. Đừng dựa vào giả định rằng mọi nhánh `$and` tùy ý sẽ được đánh giá theo đúng thứ tự viết để “bảo vệ” một toán tử có thể báo lỗi. Cách rõ ràng là đưa phép tính cần bảo vệ vào nhánh `then` của `$cond`.

### 8.3. Chia cho 0: lỗi riêng với sai kiểu

Giả sử cần tính đơn giá trung bình `amount / quantity`. Ngay cả khi cả hai là số, `quantity = 0` vẫn là trường hợp cần xử lý:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      averageUnitAmount: {
        $cond: {
          if: {
            $and: [
              { $isNumber: "$amount" },
              { $isNumber: "$quantity" },
              { $ne: ["$quantity", 0] }
            ]
          },
          then: {
            $divide: ["$amount", "$quantity"]
          },
          else: null
        }
      }
    }
  }
])
```

Trường hợp `zero` không bị coi là “thiếu dữ liệu”: nó là số 0, nhưng **không phải mẫu số hợp lệ**. Trả null ở đây là lựa chọn hiển thị cho phép tính không xác định, không phải một phép chia thực sự đã có kết quả.

## 9. Bảo vệ xử lý chuỗi: `$trim`, `$toUpper`, `$strLenCP`

Một pipeline chuẩn hóa tiêu đề thường cần bỏ khoảng trắng và chuyển chữ hoa/thường. Tuy nhiên, collection mẫu có `title` là string, `null`, missing, number, boolean và array.

```javascript
// Không an toàn trên collection có title sai kiểu
{
  $project: {
    normalizedTitle: {
      $toUpper: {
        $trim: { input: "$title" }
      }
    }
  }
}
```

`$trim` hoạt động trên giá trị chuỗi; một đầu vào như `title: 42` hoặc `title: ["x"]` có thể làm biểu thức báo lỗi. Kiểm tra kiểu trước:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      titleType: { $type: "$title" },
      normalizedTitle: {
        $cond: {
          if: {
            $eq: [{ $type: "$title" }, "string"]
          },
          then: {
            $toUpper: {
              $trim: { input: "$title" }
            }
          },
          else: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Ví dụ:

- `ok`: bỏ khoảng trắng đầu/cuối, chuyển thành `"MONGODB CƠ BẢN"` theo quy tắc xử lý ký tự mà toán tử áp dụng.
- `partial`: từ `"  Dữ liệu  "` thành chuỗi đã được trim và chuyển chữ hoa.
- `zero`: chuỗi rỗng `""` vẫn là **string hợp lệ** và kết quả là `""`, không phải `null`.
- `negative`: chuỗi chỉ gồm khoảng trắng thành `""`.
- `numericString`: `title: 42` bị trả null vì chính sách chỉ chấp nhận nguồn string.

**Lưu ý Unicode:** một số toán tử chuyển hoa/thường của MongoDB có giới hạn nhất định đối với các ký tự không phải ASCII, tùy toán tử. Khi cần biến đổi chữ Việt hoặc so khớp ngôn ngữ chính xác, hãy kiểm tra hành vi phiên bản và cân nhắc collation hoặc chuẩn hóa ở tầng phù hợp, không mặc định `$toUpper` là bộ xử lý Unicode hoàn chỉnh.

### Kiểm tra chuỗi sau trim có rỗng không

Nếu yêu cầu là “tiêu đề phải là string không trống sau khi bỏ khoảng trắng”:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      hasNonBlankTitle: {
        $cond: {
          if: {
            $eq: [{ $type: "$title" }, "string"]
          },
          then: {
            $gt: [
              {
                $strLenCP: {
                  $trim: { input: "$title" }
                }
              },
              0
            ]
          },
          else: false
        }
      }
    }
  }
])
```

`$strLenCP` đo độ dài theo **Unicode code points**, không đơn thuần là số byte UTF-8. `title: ""` và `title: "   "` không đạt điều kiện, còn string có nội dung sau trim đạt điều kiện.

Đừng dùng `$ifNull` một mình để kiểm tra chuỗi rỗng: `""` không phải Null, và `$ifNull` không tự trim hay kiểm tra độ dài.

## 10. Bảo vệ biểu thức mảng: `$size`, `$filter`, `$map`

Với `tags`, ứng dụng có thể muốn đếm số nhãn và kiểm tra tất cả nhãn đều là string.

### 10.1. `$size` không chấp nhận mọi kiểu

```javascript
// Có thể báo lỗi khi tags không phải array
db.expressionCases.aggregate([
  {
    $project: {
      tagCount: { $size: "$tags" }
    }
  }
])
```

`$size` trong aggregation cần toán hạng là array. Field missing, null, string hoặc object có thể khiến pipeline lỗi nếu đưa thẳng vào `$size`.

Cách xử lý an toàn:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      tagsType: { $type: "$tags" },
      tagCount: {
        $cond: {
          if: { $isArray: "$tags" },
          then: { $size: "$tags" },
          else: null
        }
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Kết quả đáng chú ý:

| Case | `tags` | `tagCount` |
| --- | --- | --- |
| `ok` | `["mongodb","java"]` | 2 |
| `zero` | `[]` | 0 |
| `partial` | `[null]` | 1 |
| `mixedTags` | `["mongodb",1]` | 2 |
| `null` | `null` | `null` |
| `missing` | Missing | `null` |
| `badString` | `"mongodb"` | `null` |
| `wrongObject` | Object | `null` |

`[null]` có **một phần tử**; `[]` có **không phần tử nào**. `$isArray` giúp phân biệt null/missing với array, nhưng **không kiểm tra kiểu từng phần tử**.

Nếu nghiệp vụ muốn coi field thiếu như danh sách rỗng, có thể thay nhánh `else: null` bằng `else: 0`. Tuy nhiên, như vậy cả string/object sai kiểu cũng bị coi như 0, che giấu lỗi. Nên tách chính sách “missing nghĩa là rỗng” khỏi chính sách “sai kiểu cần cảnh báo”.

### 10.2. Đếm phần tử sai kiểu bằng `$filter`

Yêu cầu: `tags` là array và **mọi phần tử đều là string**. Chỉ kiểm tra `$isArray` chưa đủ. Hãy đếm số phần tử không phải string:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      invalidTagCount: {
        $cond: {
          if: { $isArray: "$tags" },
          then: {
            $size: {
              $filter: {
                input: "$tags",
                as: "tag",
                cond: {
                  $ne: [
                    { $type: "$$tag" },
                    "string"
                  ]
                }
              }
            }
          },
          else: null
        }
      }
    }
  }
])
```

Ở đây:

- `$$tag` là **biến đại diện phần tử** trong `$filter`; `$tags` là field của document đầu vào.
- `$type: "$$tag"` đánh giá kiểu của **phần tử đang xét**.
- `$ne: [..., "string"]` giữ lại phần tử có kiểu khác string.
- `$size` đếm các phần tử sai kiểu.

Trên dữ liệu mẫu, `partial` có `invalidTagCount = 1` vì chứa `null`; `mixedTags` có `invalidTagCount = 1` vì chứa số `1`; `ok` và `zero` có `invalidTagCount = 0`. Đối với field không phải array, kết quả null để **không nhầm lẫn với “array hợp lệ và không có phần tử sai kiểu”**.

### 10.3. `$map` cũng cần kiểm tra đầu vào

Để biến đổi từng tag, `$map` nhận `input` là array:

```javascript
{
  $map: {
    input: "$tags",
    as: "tag",
    in: "$$tag"
  }
}
```

Theo ngữ nghĩa MongoDB, `$map` có thể trả null khi input null/missing, nhưng nếu input là giá trị **không phải array** (và không phải null), thao tác có thể báo lỗi. Do đó, khi collection có `tags: "mongodb"` hoặc object, hãy dùng `$isArray` để bảo vệ trước.

Nếu muốn áp dụng hàm chuỗi cho từng phần tử, cần bảo vệ **cả mảng ngoài và từng phần tử bên trong**, không chỉ dùng `$isArray` rồi mặc định `$$tag` luôn là string.

### 10.4. Mảng rỗng có thỏa điều kiện “mọi phần tử đều hợp lệ” không?

Theo logic tập hợp, một mảng rỗng không chứa phần tử sai kiểu; phép “mọi phần tử đều là string” có thể được xem là đúng khi mảng rỗng. Nhưng nghiệp vụ đôi khi còn yêu cầu **ít nhất một phần tử**. Khi đó phải kết hợp:

```javascript
// Một array có phần tử
{ $gt: [{ $size: "$tags" }, 0] }
```

với kiểm tra `$isArray` ở bên ngoài và điều kiện các phần tử đúng kiểu. **“Đúng kiểu”** và **“không rỗng”** là hai ràng buộc riêng.

## 11. Ngày tháng: BSON Date khác chuỗi ISO

Ngày trong JSON có thể xuất hiện dưới dạng chuỗi `"2026-11-12T00:00:00Z"`. Trong MongoDB, đây vẫn là **BSON String**, không phải **BSON Date**. Một biểu thức format ngày như `$dateToString` không nên được áp dụng tùy ý trên mọi giá trị.

### 11.1. Chỉ xử lý khi nguồn là Date

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      dateType: { $type: "$occurredAt" },
      dayInVietnam: {
        $cond: {
          if: {
            $eq: [{ $type: "$occurredAt" }, "date"]
          },
          then: {
            $dateToString: {
              format: "%Y-%m-%d",
              date: "$occurredAt",
              timezone: "Asia/Ho_Chi_Minh"
            }
          },
          else: null
        }
      }
    }
  }
])
```

Với document `ok`, `occurredAt = 2026-11-10T14:20:00Z` tương ứng **21:20 ngày 10/11/2026 tại Việt Nam**, nên chuỗi ngày là `"2026-11-10"`. Với `numericString`, thời gian đang là string nên kết quả null theo chính sách nghiêm ngặt, dù chuỗi trông giống ISO date.

### 11.2. Chuyển chuỗi ngày khi thực sự được phép

Nếu chính sách hệ thống chấp nhận chuỗi ISO hợp lệ, có thể thử `$convert` về kiểu Date:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      originalDateType: { $type: "$occurredAt" },
      convertedDate: {
        $cond: {
          if: {
            $in: [
              { $type: "$occurredAt" },
              ["date", "string"]
            ]
          },
          then: {
            $convert: {
              input: "$occurredAt",
              to: "date",
              onError: null,
              onNull: null
            }
          },
          else: null
        }
      }
    }
  }
])
```

`numericString` có chuỗi ISO hợp lệ nên có thể tạo BSON Date; `badString` có `"hôm qua"` nên không chuyển được và nhận null. Các kiểu number, bool và object bị loại trước khi chuyển để tránh cách diễn giải ngày ngoài dự định.

**Không được đánh đồng chuyển đổi thành công với lựa chọn timezone nghiệp vụ.** Một timestamp có dấu `Z` đại diện cho UTC; khi trình bày theo ngày tại Việt Nam cần thêm `timezone` phù hợp ở bước format. Với chuỗi ngày không mang timezone, phải có quy tắc rõ ràng trước khi chuyển đổi.

## 12. Dùng `$match` và `$expr` để lọc document sai kiểu

Không phải lúc nào cũng cần biến đổi mọi document. Có khi muốn lấy ra danh sách lỗi để sửa.

### 12.1. Lấy những document có `amount` không phải số BSON

```javascript
db.expressionCases.aggregate([
  {
    $addFields: {
      amountType: { $type: "$amount" }
    }
  },
  {
    $match: {
      amountType: {
        $nin: ["int", "long", "double", "decimal"]
      }
    }
  },
  {
    $project: {
      _id: 1,
      amountType: 1
    }
  },
  { $sort: { _id: 1 } }
])
```

Truy vấn này giữ cả missing, null, string, bool và array. Những giá trị số âm vẫn là **kiểu số** nên không bị liệt kê vào nhóm lỗi kiểu; nếu âm không hợp lệ, thêm điều kiện miền giá trị.

### 12.2. Lọc bằng `$expr` và aggregation `$type`

```javascript
db.expressionCases.find({
  $expr: {
    $eq: [
      { $type: "$amount" },
      "missing"
    ]
  }
})
```

Đây là cách chọn document **thiếu field `amount`** bằng aggregation expression trong bộ lọc. Nếu chỉ cần kiểm tra field thiếu, cú pháp query operator ngắn hơn:

```javascript
db.expressionCases.find({
  amount: { $exists: false }
})
```

### 12.3. Tách lỗi kiểu và lỗi miền giá trị

Ví dụ cần hai nhãn:

- `"invalid-type"`: `amount` không phải số BSON.
- `"negative"`: `amount` là số nhưng nhỏ hơn 0.
- `"valid"`: `amount` là số không âm.

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      validationStatus: {
        $cond: {
          if: { $isNumber: "$amount" },
          then: {
            $cond: {
              if: { $gte: ["$amount", 0] },
              then: "valid",
              else: "negative"
            }
          },
          else: "invalid-type"
        }
      }
    }
  }
])
```

Ví dụ này phân loại missing/null vào `invalid-type` vì chính sách yêu cầu trường số. Nếu cần báo riêng missing và null, dùng `$switch` kết hợp `$type` như mục 7.

## 13. Kiểm chứng trên nhiều trường hợp, không chỉ happy path

Một biểu thức được xem là đã kiểm chứng về mặt nghiệp vụ khi ta biết **đầu vào nào được chấp nhận, đầu vào nào phải bị từ chối và kết quả mong đợi của từng nhóm**. Tập trường hợp tối thiểu nên có:

| Loại thử nghiệm | Giá trị mẫu | Câu hỏi cần trả lời |
| --- | --- | --- |
| Đúng kiểu, giá trị thông thường | `NumberDecimal("120.50")` | Phép tính trả đúng giá trị không? |
| Giá trị 0 | `NumberInt(0)` | Có bị nhầm với null/missing không? |
| Giá trị âm | `NumberInt(-10)` | Có hợp lệ theo nghiệp vụ không? |
| Giá trị Null | `null` | Biểu thức trả null, fallback hay lỗi? |
| Field thiếu | Không có khóa | Có phân biệt được missing với null không? |
| Chuỗi số | `"99.50"` | Có chuyển kiểu không, và có được phép không? |
| Chuỗi lỗi | `"N/A"` | Chuyển lỗi có làm hỏng pipeline không? |
| Boolean | `true` | Có bị chuyển thành số ngoài ý muốn không? |
| Array sai vị trí | `[10]` thay cho số | Có bị đưa vào phép toán số không? |
| Array rỗng | `[]` | Độ dài 0 có được coi là hợp lệ không? |
| Array chứa Null | `[null]` | Có bị nhầm với field Null không? |
| Array chứa phần tử sai kiểu | `["mongodb", 1]` | Có kiểm tra từng phần tử không? |
| Chuỗi rỗng/toàn khoảng trắng | `""`, `"   "` | Có tách “đúng kiểu” khỏi “có nội dung” không? |
| Ngày dưới dạng chuỗi | `"2026-11-12T00:00:00Z"` | Có được chuyển thành BSON Date không? |

### 13.1. Lưu kết quả chẩn đoán thành một phép đọc tập trung

Có thể tổ chức một pipeline chỉ **đọc và gắn nhãn** cho mọi case:

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" },
      amountIsNumber: { $isNumber: "$amount" },
      tagsType: { $type: "$tags" },
      tagCount: {
        $cond: {
          if: { $isArray: "$tags" },
          then: { $size: "$tags" },
          else: null
        }
      },
      titleType: { $type: "$title" },
      dateType: { $type: "$occurredAt" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Bộ dữ liệu thử nghiệm cho phép nhìn cùng lúc những trường hợp **lỗi kiểu**, **missing** và **giá trị biên**. Nếu đang thiết kế pipeline thật, nên định nghĩa bảng kết quả mong đợi trước, rồi đối chiếu với kết quả của MongoDB trên phiên bản server đích.

### 13.2. Kiểm chứng bằng aggregation `$group` theo trạng thái

Tổng số case có thể được phân loại theo kiểu `amount`:

```javascript
db.expressionCases.aggregate([
  {
    $group: {
      _id: { $type: "$amount" },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
```

Đây là cách tổng hợp phân bố dữ liệu không đồng nhất mà không phải tự đọc thủ công từng document. Có thể áp dụng tương tự cho `tags`, `title` và `occurredAt`.

**Chú ý:** `$group` theo `"$amount"` khác `$group` theo `{$type:"$amount"}`. Cách đầu tạo nhóm theo **giá trị**, cách sau tạo nhóm theo **kiểu**. Khi tìm dữ liệu sai kiểu, cách sau thường đúng mục tiêu hơn.

## 14. Java MongoDB Sync Driver: chạy pipeline chẩn đoán an toàn

Java Sync Driver có thể gửi pipeline aggregation dưới dạng các đối tượng `Document` hoặc các helper `Aggregates`. Với biểu thức lồng nhau, `Document.parse()` giúp viết gần giống lệnh trong `mongosh`.

Ví dụ Java 15+:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public class AggregationTypeDiagnostics {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        List<Bson> pipeline = List.of(
            Document.parse("""
                {
                  "$project": {
                    "_id": 1,
                    "amountType": { "$type": "$amount" },
                    "amountIsNumber": { "$isNumber": "$amount" },
                    "safeAmount": {
                      "$convert": {
                        "input": "$amount",
                        "to": "decimal",
                        "onError": null,
                        "onNull": null
                      }
                    },
                    "tagCount": {
                      "$cond": {
                        "if": { "$isArray": "$tags" },
                        "then": { "$size": "$tags" },
                        "else": null
                      }
                    }
                  }
                }
                """),
            Document.parse("""
                { "$sort": { "_id": 1 } }
                """)
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_expression_lab");
            MongoCollection<Document> collection =
                database.getCollection("expressionCases");

            collection.aggregate(pipeline)
                .forEach(result -> System.out.println(result.toJson()));
        }
    }
}
```

Đoạn code cần dependency `mongodb-driver-sync` tương thích và biến môi trường `MONGODB_URI`. Nó **không sửa dữ liệu**. `Document.parse` xử lý cú pháp JSON của pipeline, không phải JavaScript của shell như `NumberDecimal(...)` hay `ISODate(...)`; những giá trị đó đã được tạo ở phần chèn dữ liệu qua `mongosh`.

Ví dụ này dùng `$convert` để không làm lệnh thất bại vì `"N/A"`, nhưng như đã phân tích, việc có thể chuyển từ boolean sang số **không đồng nghĩa** dữ liệu đó hợp lệ với chính sách nghiêm ngặt. Khi dùng pipeline cho nghiệp vụ thật, thêm guard kiểu nguồn như mục 6.1 và giữ các trường chẩn đoán để phát hiện sai dữ liệu.

## 15. Khi nào cần schema validation thay vì chỉ sửa biểu thức đọc?

Các biểu thức an toàn giúp endpoint không bị sập khi gặp dữ liệu bất thường, nhưng **không tự sửa nguyên nhân**. Nếu hệ thống yêu cầu:

- `amount` bắt buộc là Decimal128 không âm;
- `quantity` bắt buộc là Int32 không âm;
- `tags`, nếu tồn tại, phải là array chứa string;
- `occurredAt` bắt buộc là BSON Date;

thì có thể đưa quy tắc này vào schema validation của collection:

```javascript
db.createCollection("validatedEvents", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["amount", "quantity", "occurredAt"],
      properties: {
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        quantity: {
          bsonType: "int",
          minimum: 0
        },
        tags: {
          bsonType: "array",
          items: { bsonType: "string" }
        },
        occurredAt: {
          bsonType: "date"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

Ví dụ này tạo collection `validatedEvents` mới và không tác động tới collection `expressionCases` dùng để học các dữ liệu sai kiểu. Nó minh họa cách **ngăn sai kiểu khi ghi** thay vì chỉ kiểm tra lúc đọc.

Khi collection hiện có đã có dữ liệu không đồng nhất, thay validator không tự di chuyển hoặc sửa dữ liệu cũ; cần chiến lược migration và cấu hình validation phù hợp. Bên cạnh validation ở database, ứng dụng cũng nên xác thực payload, quản lý kiểu BSON chính xác và không âm thầm đổi chuỗi lỗi thành số 0.

## 16. Các lỗi thường gặp khi kiểm chứng aggregation expression

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `$size` làm pipeline báo lỗi | Field là null/missing/string/object thay vì array | Dùng `$isArray` và `$cond` trước `$size` |
| `$trim` hoặc `$strLenCP` báo lỗi | Field không phải string | Kiểm tra `{$type:"$field"} = "string"` |
| `$toDecimal` làm cả truy vấn thất bại | Có chuỗi `"N/A"` hoặc kiểu không chuyển được | Dùng `$convert` với `onError` và xử lý lỗi dữ liệu |
| Chuỗi `"99.50"` không được `$isNumber` chấp nhận | String không phải kiểu số BSON | Chuyển kiểu có kiểm soát nếu nghiệp vụ cho phép |
| `amount: 0` bị coi là thiếu | Logic ứng dụng coi mọi giá trị falsy như missing | Kiểm tra kiểu và `null` tường minh; 0 là số hợp lệ |
| `$ifNull` giữ lại string/object sai kiểu | Toán tử chỉ thay null/missing | Bổ sung `$type`, `$isNumber`, `$isArray` |
| Lọc `$gte: ["$amount",0]` cho kết quả khó hiểu | So sánh chéo kiểu BSON, không phải kiểm tra số | Guard `$isNumber` trước phép so sánh |
| Chuỗi ngày ISO không được xử lý như BSON Date | String khác Date | Chuyển kiểu có chính sách hoặc yêu cầu lưu Date |
| `tags: [null]` có kiểu `array`, không phải `null` | `$type` aggregation đánh giá toàn field | Dùng `$filter`/`$map` nếu cần kiểm tra từng phần tử |
| `$isArray` trả true nhưng mảng chứa số lẫn chuỗi | Nó chỉ kiểm tra kiểu array ngoài | Kiểm tra phần tử bằng `$filter` và `$type` |
| `$ifNull` gộp missing với null | Cả hai kích hoạt giá trị thay thế | Dùng `$type` trước khi gộp nếu cần báo cáo riêng |
| `$group` theo giá trị field không phát hiện được phân bố kiểu | Các giá trị khác nhau vẫn là nhóm khác nhau | Nhóm theo `{$type:"$field"}` để thống kê loại dữ liệu |
| Dùng `onError: null` nhưng không log số bản lỗi | Lỗi chuyển đổi bị che trong output | Bổ sung nhãn trạng thái và đếm bản ghi cần sửa |
| Biểu thức chạy tốt trên 1 document nhưng lỗi với collection | Tập kiểm tra chỉ chứa trường hợp hợp lệ | Có fixture đủ null/missing/sai kiểu/biên |

Khi một aggregation báo lỗi, hãy đọc **toán tử và loại giá trị** được thông báo, sau đó thu hẹp dữ liệu đầu vào bằng `$match` hoặc xuất `$type` qua một pipeline chẩn đoán độc lập. Không nên đơn giản thay hết mọi giá trị sai bằng `null` mà chưa hiểu chúng sai do schema, serialization hay luồng nhập liệu.

## 17. Bài tập thực hành

Các bài tập dựa trên `expressionCases` của mục 2 và dùng pipeline đọc, không làm thay đổi dữ liệu.

### Bài 1. Phân biệt missing với null

Viết aggregation chỉ xuất `_id` và `amountType`, sao cho `missing` cho `"missing"`, document `null` cho `"null"`.

**Đáp án:**

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" }
    }
  }
])
```

Nếu dùng `$ifNull` để thay hai trường hợp bằng một giá trị chung, sẽ mất thông tin phân biệt mà đề bài yêu cầu.

### Bài 2. Đếm tags nhưng không lỗi trên string

Viết biểu thức `tagCount` chỉ trả số phần tử khi `tags` là array, còn lại trả null.

**Đáp án:**

```javascript
db.expressionCases.aggregate([
  {
    $project: {
      _id: 1,
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

`zero` có `tagCount = 0`; `partial` có `tagCount = 1`; `badString` có `tagCount = null`.

### Bài 3. Chuyển chuỗi số nhưng không làm vỡ pipeline

Yêu cầu: chuyển `amount` thành Decimal128 nếu chuyển được, trả null nếu chuyển lỗi hoặc null/missing.

**Đáp án:**

```javascript
{
  $convert: {
    input: "$amount",
    to: "decimal",
    onError: null,
    onNull: null
  }
}
```

Nhưng nếu yêu cầu còn phải **loại boolean và object ngay từ kiểu nguồn**, cần kết hợp `$cond` kiểm tra `$type`, vì việc chuyển thành số không tự bảo đảm dữ liệu gốc hợp lệ.

### Bài 4. Kiểm tra số nguyên không âm

Viết biểu thức trả `true` khi `quantity` là BSON `int` hoặc `long` và không âm; các trường hợp khác trả `false`.

**Đáp án tham khảo:**

```javascript
{
  $cond: {
    if: {
      $in: [
        { $type: "$quantity" },
        ["int", "long"]
      ]
    },
    then: { $gte: ["$quantity", 0] },
    else: false
  }
}
```

`zero` đạt yêu cầu; `negative`, `null`, `missing` và `numericString` không đạt.

### Bài 5. Tìm array có phần tử sai kiểu

Yêu cầu: `tags` là array các string; nếu là array thì đếm số phần tử không phải string. Từ dữ liệu mẫu, những document nào có `invalidTagCount > 0`?

**Đáp án:** Sử dụng biểu thức `$filter` với điều kiện:

```javascript
cond: {
  $ne: [
    { $type: "$$tag" },
    "string"
  ]
}
```

rồi `$size` của array sau lọc, có `$isArray` bảo vệ ở ngoài. Kết quả `partial` và `mixedTags` đều có 1 phần tử sai kiểu. Array `[]` có 0 phần tử sai kiểu chứ không phải là null.

### Bài 6. Nhận biết phép so sánh chéo kiểu

Một người viết:

```javascript
{
  $project: {
    validAmount: { $gte: ["$amount", 0] }
  }
}
```

và kết luận rằng `validAmount: true` luôn chứng minh `amount` là số không âm. Vì sao kết luận này không chắc đúng?

**Đáp án:** Aggregation comparison có quy tắc so sánh BSON giữa các kiểu, không phải phép xác thực kiểu số. Cần dùng `$isNumber` hoặc `$type` để xác nhận kiểu, rồi mới so sánh miền giá trị trong nhánh `$cond`.

### Bài 7. Kiểm chứng chuỗi rỗng và khoảng trắng

Yêu cầu: `title` phải là string, sau khi `$trim` phải chứa ít nhất một code point. Hãy nêu hai loại document có string nhưng vẫn không hợp lệ.

**Đáp án:** `zero` có `title: ""` và `negative` có `title: "   "`; cả hai đều có kiểu string, nhưng sau trim độ dài bằng 0. Dùng `$cond` kiểm tra `$type`, rồi `$strLenCP` trên giá trị `$trim` như mục 9.

### Bài 8. Ngày string và ngày BSON

Yêu cầu: chỉ định dạng ngày tại múi giờ `Asia/Ho_Chi_Minh` đối với document có `occurredAt` là BSON Date. Với `numericString` có chuỗi ISO, kết quả phải là null.

**Đáp án:**

```javascript
{
  $cond: {
    if: {
      $eq: [{ $type: "$occurredAt" }, "date"]
    },
    then: {
      $dateToString: {
        format: "%Y-%m-%d",
        date: "$occurredAt",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    else: null
  }
}
```

Đây là chính sách chấp nhận Date nghiêm ngặt. Nếu được phép nhận ISO string, thêm bước `$convert` hoặc `$dateFromString` có xử lý lỗi và thống nhất timezone.

## 18. Kết luận: kiểm tra kiểu trước, biến đổi sau

Kiểm chứng một aggregation expression không chỉ là thử câu lệnh trên một document mẫu. Một pipeline đáng tin cậy cần có **hợp đồng dữ liệu rõ ràng**:

1. **Nhận diện dữ liệu** bằng `$type`: missing, null, string, number, bool, array, object, date.
2. **Phân loại giá trị có hợp lệ không**: `$isNumber`, `$isArray`, điều kiện miền giá trị và điều kiện kiểu phần tử.
3. **Đặt phép tính trong nhánh được bảo vệ**: `$cond` hoặc `$switch` để các toán tử nhạy kiểu không xử lý sai đầu vào.
4. **Chuyển kiểu chỉ khi có chính sách**: dùng `$convert` với `onError`/`onNull`, đồng thời tránh biến dữ liệu sai thành số hợp lệ ngoài ý muốn.
5. **Giữ thông tin chẩn đoán khi cần**: không tùy tiện gộp missing, null và sai kiểu thành một nhãn hoặc một số 0.
6. **Thử tập dữ liệu chứa giá trị biên**: `0`, `""`, `[]`, `[null]`, chuỗi số, chuỗi lỗi, boolean, object và BSON Date.
7. **Ngăn lỗi ở nguồn** bằng schema validation, xác thực payload và migration phù hợp; biểu thức chịu lỗi ở bước đọc chỉ là một lớp bảo vệ.

Điểm cần ghi nhớ là **null, sai kiểu và field thiếu có thể dẫn đến hành vi khác nhau tùy toán tử**. Khi hiểu chính xác loại giá trị đang đi vào từng biểu thức, bạn sẽ xây được các pipeline MongoDB vừa linh hoạt với dữ liệu thực tế, vừa minh bạch về những bản ghi không đáp ứng hợp đồng dữ liệu.
