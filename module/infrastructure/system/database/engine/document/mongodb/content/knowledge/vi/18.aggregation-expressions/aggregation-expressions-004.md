# Biểu thức số học, làm tròn và tính toán với Decimal128 trong MongoDB

## 1. Vì sao cần quan tâm đến kiểu số ngay từ khi viết aggregation?

MongoDB cung cấp nhiều biểu thức để cộng, trừ, nhân, chia, lấy phần dư, tính lũy thừa, làm tròn và tính tổng trên các document. Chúng thường xuất hiện trong pipeline tính thành tiền đơn hàng, thuế, chiết khấu, điểm trung bình, tỷ lệ tăng trưởng hoặc báo cáo thống kê.

Ví dụ, một dòng hóa đơn có:

```javascript
{
  quantity: 3,
  unitPrice: NumberDecimal("19.95"),
  taxRate: NumberDecimal("0.08")
}
```

Nhu cầu đơn giản là tính:

```text
Tiền hàng  = số lượng × đơn giá
Thuế       = tiền hàng × tỷ lệ thuế
Tổng thanh toán = tiền hàng + thuế
```

Nhưng việc chọn **kiểu số** và **thời điểm làm tròn** có thể khiến hai pipeline nhìn gần giống nhau cho ra kết quả khác nhau. Với thống kê gần đúng, chênh lệch rất nhỏ có thể chấp nhận được. Với tiền tệ, hóa đơn và kế toán, chênh lệch một đơn vị tiền nhỏ nhất có thể trở thành sai lệch nghiệp vụ.

Bài học này làm rõ:

- Cách dùng các toán tử số học trong aggregation: `$add`, `$subtract`, `$multiply`, `$divide`, `$mod`, `$abs`, `$pow` và những toán tử liên quan.
- Khác biệt giữa phép cộng/đếm/tính trung bình trên document và trên toàn nhóm.
- Cách `$round`, `$trunc`, `$ceil`, `$floor` xử lý số dương, số âm và vị trí thập phân.
- Vì sao **BSON Decimal128** hữu ích cho giá trị thập phân cần độ chính xác cao.
- Cách xử lý `null`, dữ liệu sai kiểu, phép chia cho 0, overflow và quy tắc làm tròn.
- Pipeline hóa đơn hoàn chỉnh và cách trao đổi Decimal128 với Java MongoDB Sync Driver.
- Những đánh đổi về độ chính xác, hiệu năng và quy tắc nghiệp vụ khi tính toán trên server.

> **Nguyên tắc cốt lõi:** phép tính chính xác không chỉ phụ thuộc công thức, mà còn phụ thuộc kiểu số của toán hạng, đơn vị đo, độ chính xác yêu cầu và vị trí thực hiện làm tròn.

---

## 2. Biểu thức aggregation là gì?

Trong một aggregation pipeline, biểu thức được đánh giá trên dữ liệu của document hoặc nhóm đang xử lý. Nó khác với việc gõ trực tiếp một biểu thức JavaScript trong `mongosh`.

Ví dụ:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      quantity: 1,
      unitPrice: 1,
      rawAmount: {
        $multiply: ["$quantity", "$unitPrice"]
      }
    }
  }
]);
```

Trong phần `rawAmount`:

- `$multiply` là **toán tử biểu thức**.
- `"$quantity"` tham chiếu giá trị field `quantity` của document hiện tại.
- `"$unitPrice"` tham chiếu field `unitPrice`.
- Hai giá trị được tính trong server; chúng không phải chuỗi literal `"quantity"` và `"unitPrice"`.

### 2.1. Biểu thức có thể lồng nhau

```javascript
{
  $add: [
    { $multiply: ["$quantity", "$unitPrice"] },
    "$shippingFee"
  ]
}
```

Ý nghĩa:

```text
(quantity × unitPrice) + shippingFee
```

Trong tài liệu MongoDB, những biểu thức dạng `{ $operator: ... }` có thể được dùng ở các stage như `$project`, `$set`, `$addFields`, `$group` (theo contract accumulator/expression), hoặc trong `$expr` của một truy vấn phù hợp.

### 2.2. Phân biệt toán tử stage với toán tử expression

```javascript
// $set ở đây là một pipeline stage.
db.orderLines.aggregate([
  {
    $set: {
      lineAmount: {
        $multiply: ["$quantity", "$unitPrice"]
      }
    }
  }
]);
```

`$set` tạo/thay field ở document đang đi qua pipeline. `$multiply` mới là biểu thức tính số học. Cũng cần phân biệt `$sum` là **accumulator trong `$group`** và có thể là **expression trong các stage khác**; cách xử lý mảng của hai ngữ cảnh có điểm khác nhau.

### 2.3. Các toán tử không phải JavaScript arithmetic

Không viết:

```javascript
// Không diễn đạt phép nhân theo từng document trên server:
db.orderLines.aggregate([
  {
    $project: {
      amount: "$quantity" * "$unitPrice"
    }
  }
]);
```

JavaScript ở phía shell không thể lấy giá trị từng field bằng cách nhân hai chuỗi path. Phải dùng:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      amount: { $multiply: ["$quantity", "$unitPrice"] }
    }
  }
]);
```

---

## 3. Chuẩn bị dữ liệu mẫu

Giả sử collection `orderLines` chưa chứa các ID được dùng ở đây:

```javascript
db.orderLines.insertMany([
  {
    _id: "L1",
    orderId: "O100",
    sku: "PEN",
    quantity: 3,
    unitPrice: NumberDecimal("19.95"),
    discountRate: NumberDecimal("0.10")
  },
  {
    _id: "L2",
    orderId: "O100",
    sku: "NOTE",
    quantity: 2,
    unitPrice: NumberDecimal("4.20"),
    discountRate: NumberDecimal("0.00")
  },
  {
    _id: "L3",
    orderId: "O101",
    sku: "CASE",
    quantity: 1,
    unitPrice: NumberDecimal("35.50"),
    discountRate: NumberDecimal("0.05")
  }
]);
```

Dữ liệu có các thuộc tính:

| Field | Kiểu minh họa | Vai trò |
| --- | --- | --- |
| `_id` | String | Định danh dòng hàng. |
| `orderId` | String | Đơn hàng cha. |
| `quantity` | BSON Int32 | Số lượng nguyên. |
| `unitPrice` | BSON Decimal128 | Đơn giá thập phân. |
| `discountRate` | BSON Decimal128 | Tỷ lệ giảm giá ở dạng 0–1. |

Các ví dụ sau dựa trên dataset này hoặc ghi rõ khi dùng dữ liệu riêng. Trước khi chạy lại lệnh `insertMany`, cần dùng collection thử nghiệm trống hoặc ID khác để tránh lỗi trùng `_id`.

### 3.1. Tạo số Decimal128 đúng cách trong `mongosh`

```javascript
NumberDecimal("19.95")
NumberDecimal("0.10")
NumberDecimal("123456789.012345")
```

**Truyền chuỗi** vào `NumberDecimal(...)` giúp mô tả giá trị thập phân dự định một cách rõ ràng. Không nên lấy một phép toán JavaScript Double rồi giả định rằng bọc kết quả trong Decimal128 sẽ xóa sạch mọi sai số đã được tạo ra trước đó.

Ví dụ nên tránh trong mã tiền tệ:

```javascript
// Phép cộng xảy ra trước bằng JavaScript Number (binary floating-point).
const value = 0.1 + 0.2;

// Đây không tương đương về mặt đầu vào với việc truyền "0.3" từ đầu.
```

Để lưu giá trị tiền một cách nhất quán, nhận decimal từ string đã kiểm tra, hoặc dùng `BigDecimal` trong Java.

---

## 4. `$add`: phép cộng nhiều toán hạng

Cú pháp:

```javascript
{
  $add: [<expression1>, <expression2>, ...]
}
```

Ví dụ:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      unitPrice: 1,
      handlingFee: NumberDecimal("2.50"),
      totalForOneUnit: {
        $add: [
          "$unitPrice",
          NumberDecimal("2.50")
        ]
      }
    }
  }
]);
```

Với dòng L1, tổng của `19.95` và `2.50` có giá trị số học **22.45**.

### 4.1. Cộng nhiều field

```javascript
{
  $add: [
    "$subtotal",
    "$taxAmount",
    "$shippingFee"
  ]
}
```

Toán tử nhận một mảng các biểu thức. Nếu field bên trong là `null` hoặc thiếu, cần xác định hành vi và làm sạch đầu vào; với các toán tử số học như `$add`, `null` có thể khiến kết quả thành `null`, không tự được hiểu là số 0.

### 4.2. Dùng `$ifNull` khi nghiệp vụ quy định mặc định 0

Nếu phí vận chuyển là tùy chọn:

```javascript
db.orders.aggregate([
  {
    $project: {
      payable: {
        $add: [
          "$subtotal",
          "$taxAmount",
          { $ifNull: ["$shippingFee", NumberDecimal("0.00")] }
        ]
      }
    }
  }
]);
```

Đặt mặc định **chỉ khi đúng nghiệp vụ**. `shippingFee` bị thiếu do lỗi dữ liệu có thể cần bị từ chối chứ không phải lặng lẽ chuyển thành 0. Khi cần audit tài chính, nên phân biệt “không có phí” với “chưa được nhập phí”.

### 4.3. `$add` với Date

MongoDB còn hỗ trợ cộng một giá trị Date với giá trị số biểu diễn **mili giây** theo contract của toán tử:

```javascript
db.events.aggregate([
  {
    $project: {
      scheduledAt: {
        $add: [
          "$createdAt",
          60 * 60 * 1000
        ]
      }
    }
  }
]);
```

Ví dụ cộng thêm một giờ theo mili giây. Cần nhớ đơn vị số là **millisecond**, không phải second. Nếu xử lý lịch, timezone, DST hoặc tháng/ngày theo lịch, ưu tiên các toán tử date chuyên dụng như `$dateAdd` thay vì tự nhân số mili giây cho một tháng.

---

## 5. `$subtract`: phép trừ và hiệu thời gian

Cú pháp:

```javascript
{
  $subtract: [<minuend>, <subtrahend>]
}
```

Ví dụ tiền:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      afterFixedDiscount: {
        $subtract: [
          "$unitPrice",
          NumberDecimal("2.00")
        ]
      }
    }
  }
]);
```

Với L1: `19.95 - 2.00 = 17.95`.

### 5.1. Thứ tự toán hạng là bắt buộc

```javascript
{ $subtract: [20, 5] }   // 15
{ $subtract: [5, 20] }   // -15
```

`$subtract` nhận hai toán hạng theo thứ tự; không giống `$add` có thể cộng nhiều giá trị theo tính giao hoán.

### 5.2. Trừ Date với Date

```javascript
db.deliveryEvents.aggregate([
  {
    $project: {
      elapsedMs: {
        $subtract: ["$completedAt", "$startedAt"]
      }
    }
  }
]);
```

Nếu cả hai toán hạng là Date, kết quả là **thời gian chênh lệch tính bằng mili giây**. Nếu cần giây, có thể chia kết quả cho 1000:

```javascript
{
  $divide: [
    { $subtract: ["$completedAt", "$startedAt"] },
    1000
  ]
}
```

Khi dùng đơn vị như giây/phút/giờ, hãy đặt tên field rõ (`elapsedMs`, `elapsedSeconds`) để tránh lỗi đổi đơn vị. Tính chênh lệch theo ngày lịch nên cân nhắc `$dateDiff`.

---

## 6. `$multiply`: nhân nhiều toán hạng

Cú pháp:

```javascript
{
  $multiply: [<expression1>, <expression2>, ...]
}
```

Một dòng hàng có số lượng và đơn giá:

```javascript
db.orderLines.aggregate([
  {
    $project: {
      orderId: 1,
      sku: 1,
      quantity: 1,
      unitPrice: 1,
      lineSubtotal: {
        $multiply: ["$quantity", "$unitPrice"]
      }
    }
  }
]);
```

Với L1: `3 × 19.95 = 59.85`.

Với L2: `2 × 4.20 = 8.40`.

### 6.1. Nhân với tỷ lệ phần trăm

Tỷ lệ `discountRate = 0.10` nghĩa là 10%, không phải giá trị số 10. Biểu thức:

```javascript
{
  $multiply: [
    "$lineSubtotal",
    "$discountRate"
  ]
}
```

tính phần giảm giá. Nếu client gửi 10 để diễn đạt 10%, ứng dụng phải có quy ước chuyển đổi rõ ràng; không được lẫn lộn percent và ratio.

### 6.2. Số nguyên và Decimal128 khi nhân

Trong dữ liệu mẫu, `quantity` là Int32 và `unitPrice` là Decimal128. MongoDB sử dụng quy tắc **numeric type promotion**, nên phép nhân có Decimal128 thường cho kết quả Decimal128. Có thể chuyển `quantity` sang Decimal128 tường minh nếu muốn làm rõ contract:

```javascript
{
  $multiply: [
    { $toDecimal: "$quantity" },
    "$unitPrice"
  ]
}
```

Điều quan trọng là đầu vào `unitPrice` đã thực sự là Decimal128. Nếu đơn giá được lưu dưới dạng Double, việc ép kiểu ở bước cuối không tự bảo đảm khôi phục ý nghĩa thập phân đã bị sai lệch khi nhập liệu.

---

## 7. `$divide`: chia và kiểm soát mẫu số

Cú pháp:

```javascript
{
  $divide: [<dividend>, <divisor>]
}
```

Ví dụ, tính giá bình quân trên mỗi sản phẩm:

```javascript
db.orders.aggregate([
  {
    $project: {
      unitAverage: {
        $divide: [
          "$totalAmount",
          "$totalQuantity"
        ]
      }
    }
  }
]);
```

### 7.1. Phân biệt Double và Decimal128 khi chia

Theo ngữ nghĩa aggregation, `$divide` mặc định có thể trả **Double** cho các toán hạng không phải Decimal128; nếu có toán hạng Decimal128 thì kết quả dùng kiểu decimal theo quy tắc nâng kiểu số.

Ví dụ:

```javascript
db.numbers.aggregate([
  {
    $project: {
      divideIntegers: { $divide: [1, 3] },
      divideDecimals: {
        $divide: [
          NumberDecimal("1"),
          NumberDecimal("3")
        ]
      }
    }
  }
]);
```

Kết quả của `1 / 3` dù biểu diễn bằng Decimal128 cũng **không thể có vô hạn chữ số 3**. Decimal128 có độ chính xác hữu hạn; nó chính xác với nhiều giá trị thập phân hữu hạn nhưng không biến mọi phân số thành số hữu tỷ vô hạn chính xác.

### 7.2. Chia cho 0 là lỗi, không phải một giá trị bình thường

Không viết:

```javascript
{
  $divide: ["$amount", "$quantity"]
}
```

nếu `quantity` có thể bằng 0. Phép chia cho 0 có thể khiến aggregation thất bại.

Một cách bảo vệ:

```javascript
db.orders.aggregate([
  {
    $project: {
      avgUnitAmount: {
        $cond: [
          { $eq: ["$quantity", 0] },
          null,
          {
            $divide: [
              "$amount",
              "$quantity"
            ]
          }
        ]
      }
    }
  }
]);
```

Biểu thức này minh họa trường hợp `quantity` đã được validate là số và có thể bằng 0. Nếu field còn có thể **thiếu**, **null** hoặc sai kiểu, cần kiểm tra những trạng thái đó trước khi chia.

Quyết định trả `null`, 0, báo lỗi hay loại document có mẫu số 0 là **quy tắc nghiệp vụ**, không nên chọn tùy tiện chỉ để pipeline luôn chạy được.

### 7.3. Tỷ lệ phần trăm

Tỷ lệ hoàn thành:

```javascript
{
  $multiply: [
    {
      $divide: [
        "$completedTasks",
        "$totalTasks"
      ]
    },
    100
  ]
}
```

Nếu cần hiển thị tỷ lệ với hai chữ số thập phân, đặt `$round` ở bên ngoài phép tính sau khi đã quyết định kiểu số:

```javascript
{
  $round: [
    {
      $multiply: [
        {
          $divide: [
            { $toDecimal: "$completedTasks" },
            { $toDecimal: "$totalTasks" }
          ]
        },
        NumberDecimal("100")
      ]
    },
    2
  ]
}
```

Mẫu số vẫn phải được kiểm soát. Ngoài ra, tỷ lệ hiển thị đã được làm tròn không nên dùng làm đầu vào duy nhất cho phép tổng hợp tiếp theo nếu cần độ chính xác cao hơn.

---

## 8. `$mod` và `$abs`: phần dư và trị tuyệt đối

### 8.1. `$mod`

Cú pháp:

```javascript
{ $mod: [<dividend>, <divisor>] }
```

Ví dụ tìm số phần tử dư khi chia sản phẩm thành các hộp chứa 6 chiếc:

```javascript
db.packages.aggregate([
  {
    $project: {
      leftover: {
        $mod: ["$itemCount", 6]
      }
    }
  }
]);
```

Nếu `itemCount = 20`, số dư là `2`.

Ứng dụng thường dùng `$mod` để kiểm tra chia hết, chu kỳ hoặc phân nhóm theo số dư. Không chia cho 0. Với số âm, phép phần dư không nhất thiết trùng khái niệm “modulo luôn không âm” trong lý thuyết số; nếu nghiệp vụ yêu cầu mã nhóm nằm trong `[0, n)`, phải định nghĩa lại biểu thức chuẩn hóa thích hợp.

### 8.2. `$abs`

```javascript
{ $abs: <expression> }
```

Ví dụ:

```javascript
db.payments.aggregate([
  {
    $project: {
      absoluteDifference: {
        $abs: {
          $subtract: [
            "$actualAmount",
            "$expectedAmount"
          ]
        }
      }
    }
  }
]);
```

`$abs` trả độ lớn tuyệt đối, giúp tính sai lệch không phân biệt hướng tăng/giảm. Với báo cáo tài chính, đôi khi dấu chênh lệch lại mang ý nghĩa nghiệp vụ quan trọng; không xóa dấu âm chỉ vì muốn số dễ nhìn.

---

## 9. Lũy thừa, căn và logarit

MongoDB còn có các biểu thức toán học hữu ích cho phân tích:

| Toán tử | Ví dụ | Mục đích |
| --- | --- | --- |
| `$pow` | `{ $pow: [2, 3] }` | Lũy thừa `2^3 = 8`. |
| `$sqrt` | `{ $sqrt: 81 }` | Căn bậc hai, kết quả 9. |
| `$exp` | `{ $exp: 1 }` | Hàm mũ tự nhiên. |
| `$ln` | `{ $ln: 10 }` | Logarit tự nhiên. |
| `$log10` | `{ $log10: 100 }` | Logarit cơ số 10. |
| `$log` | `{ $log: [8, 2] }` | Logarit theo cơ số được chỉ định, kết quả 3. |

Ví dụ phân tích tăng trưởng kép:

```javascript
db.investments.aggregate([
  {
    $project: {
      futureValue: {
        $multiply: [
          "$principal",
          {
            $pow: [
              {
                $add: [
                  1,
                  "$ratePerPeriod"
                ]
              },
              "$numberOfPeriods"
            ]
          }
        ]
      }
    }
  }
]);
```

Đây là mô hình công thức tăng trưởng lý thuyết, chưa xử lý tất cả quy tắc thực tế như lịch dòng tiền, lãi ghép bất quy tắc, thuế và quy ước tính lãi.

**Lưu ý miền giá trị:**

- `$sqrt` yêu cầu đầu vào hợp lệ cho căn bậc hai số thực (không âm, tùy trường hợp đặc biệt).
- `$ln`, `$log10` yêu cầu đối số dương.
- `$log` yêu cầu cơ số hợp lệ (dương, khác 1), và đối số phù hợp.
- `$pow` có các trường hợp đặc biệt với 0, số âm, số mũ phân số và các kiểu số; cần kiểm tra dữ liệu trước khi dùng.

Không dùng các biểu thức này cho dữ liệu tài chính có ràng buộc làm tròn mà chưa xác định precision, overflow và quy tắc nghiệp vụ.

---

## 10. Kiểu số BSON: Int32, Int64, Double và Decimal128

MongoDB không có một kiểu “number” duy nhất.

| Kiểu BSON | Ví dụ trong mongosh | Đặc điểm |
| --- | --- | --- |
| Int32 | `NumberInt(25)` | Số nguyên có dấu 32-bit. |
| Int64 | `NumberLong("9000000000")` | Số nguyên có dấu 64-bit. |
| Double | `0.1` hoặc `NumberDouble("0.1")` | Số thực nhị phân IEEE 754 double precision. |
| Decimal128 | `NumberDecimal("0.1")` | Số thập phân IEEE 754 Decimal128. |

### 10.1. Vì sao Double có thể lệch khi biểu diễn tiền?

Trong hệ số thực nhị phân, nhiều phân số thập phân hữu hạn như `0.1` không có biểu diễn chính xác tuyệt đối. Điều này có thể dẫn đến:

```javascript
// Trong JavaScript:
0.1 + 0.2
// Thường hiển thị: 0.30000000000000004
```

Cộng hai giá trị Decimal128 được tạo từ chuỗi `"0.1"` và `"0.2"` cho phép biểu diễn giá trị toán học 0.3 chính xác trong phạm vi precision decimal.

```javascript
db.decimalExamples.aggregate([
  {
    $project: {
      decimalSum: {
        $add: [
          NumberDecimal("0.1"),
          NumberDecimal("0.2")
        ]
      }
    }
  }
]);
```

**Không đồng nhất `NumberDecimal("0.1")` với giá trị Double `0.1`.** Chúng là hai kiểu BSON khác nhau và có tính chất biểu diễn khác nhau.

### 10.2. Decimal128 không phải số chính xác vô hạn

Decimal128 hỗ trợ **34 chữ số có nghĩa** trong biểu diễn thập phân, với phạm vi số mũ lớn theo chuẩn IEEE 754 Decimal128. Nó rất hữu ích cho các giá trị tài chính được biểu diễn bằng decimal, nhưng:

- Phân số vô hạn thập phân như `1/3` vẫn phải làm tròn theo precision hữu hạn.
- Phép toán có thể vượt phạm vi giá trị có thể biểu diễn.
- Số `NaN` hoặc vô cực có thể xuất hiện trong những điều kiện nhất định và không phù hợp với đa số quy trình ghi nhận tiền.
- Khi phép tính chứa nhiều chữ số hơn precision cho phép, vẫn có quy tắc làm tròn số học ở cấp biểu diễn.

**Decimal128 giảm sai lệch do biểu diễn nhị phân**, không thay thế chính sách làm tròn, validation, đơn vị tiền và kiểm soát độ lớn dữ liệu.

### 10.3. Numeric type promotion

Các toán tử số học của MongoDB có quy tắc nâng kiểu để xử lý nhiều kiểu số:

```text
Int32 -> Int64 -> Double -> Decimal128
```

Đây là mô hình khái quát cho thứ tự precision/type promotion ở nhiều phép toán. Kiểu kết quả có thể chịu ảnh hưởng của các toán hạng và overflow; **không phải mọi toán tử đều trả cùng kiểu theo một công thức duy nhất**.

Một số điểm quan trọng:

- Cộng/nhân các số nguyên có thể cần nâng kiểu nếu vượt giới hạn Int32 hoặc Int64.
- Chia hai số nguyên bằng `$divide` thường cho kết quả Double, trừ khi có toán hạng Decimal128 để tạo kết quả decimal.
- `$round`, `$trunc`, `$ceil`, `$floor` thường duy trì kiểu số của giá trị đầu vào theo contract tương ứng.
- Khi một toán hạng là Decimal128, nhiều phép toán số học sẽ cho kết quả kiểu Decimal128.

Không nên suy ra kiểu trả về từ việc “trông kết quả giống số nguyên”; nên kiểm tra `$type` hoặc kiểu BSON khi cần contract chính xác.

### 10.4. Kiểm tra kiểu bằng `$type`

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      unitPriceType: { $type: "$unitPrice" },
      quantityType: { $type: "$quantity" },
      resultType: {
        $type: {
          $multiply: [
            "$unitPrice",
            "$quantity"
          ]
        }
      }
    }
  }
]);
```

Với dataset mẫu, `unitPriceType` là `"decimal"`, `quantityType` thường là `"int"` và kết quả nhân theo quy tắc nâng kiểu sử dụng `"decimal"`.

---

## 11. Vì sao nên tạo Decimal128 từ chuỗi?

Trong mongosh:

```javascript
NumberDecimal("19.95")
```

mô tả trực tiếp một giá trị decimal có chủ đích. Ngược lại:

```javascript
const unitPrice = 19.95; // JavaScript Number, kiểu nhị phân.
```

nếu dữ liệu đã đi qua các phép tính binary floating-point, việc chuyển sang decimal ở cuối pipeline không tự đảo ngược tất cả các sai lệch đó.

Với Java:

```java
new BigDecimal("19.95")
```

là cách tạo giá trị dựa trên chuỗi decimal. Tránh:

```java
new BigDecimal(0.1)
```

khi định biểu diễn đúng số thập phân 0.1: constructor từ Double có thể đưa phần xấp xỉ nhị phân vào BigDecimal.

Nếu đang có `double` từ một nguồn khác, `BigDecimal.valueOf(double)` thường dùng biểu diễn chuỗi của Double để tránh một số bất ngờ của `new BigDecimal(double)`, nhưng **không biến dữ liệu đầu vào sai ý nghĩa thành đúng**. Với tiền, tốt hơn là truyền decimal string hoặc đơn vị tiền nhỏ nhất dưới dạng integer.

### 11.1. Decimal128 trong Extended JSON

Khi chuyển dữ liệu BSON sang định dạng Extended JSON, một giá trị decimal có thể được biểu diễn như:

```json
{
  "unitPrice": {
    "$numberDecimal": "19.95"
  }
}
```

Cách biểu diễn này bảo tồn thông tin kiểu BSON tốt hơn so với ép mọi giá trị thành JSON number thông thường. Các client API cần thống nhất cách serialize/deserialize Decimal128; không nên tùy tiện chuyển nó sang JavaScript Number khi độ chính xác là bắt buộc.

---

## 12. `$round`: làm tròn theo vị trí thập phân

Cú pháp:

```javascript
{
  $round: [<number>, <place>]
}
```

`<place>` là tùy chọn; nếu bỏ qua, MongoDB làm tròn tới vị trí số nguyên (tương đương `0`). Giá trị `place` là số nguyên trong phạm vi MongoDB hỗ trợ.

```javascript
db.orderLines.aggregate([
  {
    $project: {
      _id: 1,
      roundedUnitPrice: {
        $round: ["$unitPrice", 1]
      }
    }
  }
]);
```

Với `19.95`, làm tròn một chữ số sau dấu thập phân sẽ phụ thuộc quy tắc **half-even**; từ `19.95` đến một chữ số thập phân, kết quả là **20.0** vì chữ số hàng phần mười được chọn là 0 (chẵn) trong trường hợp đúng giữa.

### 12.1. Quy tắc tie-breaking: half to even

MongoDB `$round` áp dụng kiểu làm tròn **“round half to even”**, thường gọi là *banker's rounding*, khi giá trị ở đúng giữa hai ứng viên.

Ví dụ với `place = 0`:

| Đầu vào Decimal128 | Kết quả về mặt giá trị | Giải thích |
| --- | --- | --- |
| `2.4` | `2` | Gần 2 hơn. |
| `2.6` | `3` | Gần 3 hơn. |
| `2.5` | `2` | Giữa 2 và 3; chọn 2 chẵn. |
| `3.5` | `4` | Giữa 3 và 4; chọn 4 chẵn. |
| `-1.5` | `-2` | Giữa -1 và -2; chọn -2 chẵn. |
| `-2.5` | `-2` | Giữa -2 và -3; chọn -2 chẵn. |

Có thể thử:

```javascript
db.roundingExamples.aggregate([
  {
    $project: {
      value: 1,
      rounded: { $round: ["$value", 0] }
    }
  }
]);
```

Các ví dụ bảng có thể được dùng để tạo dữ liệu thử; không cần thiết phải đổi kiểu về Double.

**Điểm cực kỳ quan trọng:** half-even **không giống** làm tròn “.5 luôn tăng lên” hoặc “.5 luôn ra xa 0”. Nếu pháp luật, quy định thuế hoặc hợp đồng yêu cầu `HALF_UP`, cần triển khai và kiểm chứng **chính sách làm tròn phù hợp**, không mặc định `$round` đáp ứng mọi trường hợp tiền tệ.

### 12.2. Làm tròn hai chữ số thập phân

```javascript
{
  $round: [
    "$grossAmount",
    2
  ]
}
```

Với số tiền cần biểu diễn 2 chữ số sau dấu thập phân, `place = 2` thường phù hợp. Tuy nhiên, không phải mọi loại tiền đều có hai chữ số thập phân và không phải mọi loại phép tính đều làm tròn ở cùng bước. Quy tắc phải đến từ domain.

### 12.3. Làm tròn bên trái dấu thập phân

`place` âm làm tròn ở hàng chục, hàng trăm, v.v.:

```javascript
{ $round: [NumberDecimal("1234.56"), -1] } // 1230
{ $round: [NumberDecimal("1234.56"), -2] } // 1200
```

Không dùng `place = -2` với ý định “giữ hai chữ số sau dấu thập phân”: đó là **làm tròn đến hàng trăm**.

### 12.4. Dạng trả về

Khi đầu vào `$round` là Decimal128, kết quả theo contract toán tử được giữ ở kiểu decimal. Phần **biểu diễn chữ số 0 cuối** khi in ra có thể phụ thuộc encoding/formatting; muốn trả chuỗi tiền tệ như `"20.00"` cần tách rõ bước format ở ứng dụng hoặc presentation layer.

### 12.5. `null` và giá trị đặc biệt

Một số phép làm tròn trả `null` cho đầu vào `null`/missing theo ngữ nghĩa toán tử và có quy tắc riêng với NaN/Infinity. Với dữ liệu tài chính, không nên cho các giá trị đặc biệt này đi qua pipeline mà không validation. Không coi `null` như 0 trừ khi đó là quyết định nghiệp vụ rõ ràng.

---

## 13. `$trunc`: cắt phần thập phân, không làm tròn đến số gần nhất

Cú pháp:

```javascript
{
  $trunc: [<number>, <place>]
}
```

Ví dụ:

```javascript
{ $trunc: [NumberDecimal("12.987"), 2] }
```

cho giá trị **12.98** về mặt số học.

Sự khác nhau:

```javascript
{ $round: [NumberDecimal("12.987"), 2] } // 12.99
{ $trunc: [NumberDecimal("12.987"), 2] } // 12.98
```

### 13.1. Với số âm, truncation hướng về 0

```javascript
{ $trunc: [NumberDecimal("-1.9"), 0] } // -1
```

Nó **không** tương đương với làm tròn xuống âm vô cực. Đây là lý do `$trunc` và `$floor` không thể hoán đổi trên số âm.

### 13.2. `place` âm

```javascript
{ $trunc: [NumberDecimal("1234.56"), -2] } // 1200
```

Phần từ hàng chục trở xuống bị bỏ khi cắt về hàng trăm. Giá trị âm cũng được cắt về 0 ở độ lớn tương ứng.

### 13.3. Khi nào dùng `$trunc`?

- Cắt bớt precision cho các chỉ số đo hoặc báo cáo theo quy tắc rõ ràng.
- Tách phần nguyên theo hướng về 0.
- Chuyển số theo một quy tắc nghiệp vụ “bỏ phần lẻ” thay vì “làm tròn gần nhất”.

**Không dùng `$trunc` thay cho chính sách làm tròn tiền** nếu yêu cầu phải dùng half-even/half-up. Việc cắt thập phân có xu hướng tạo thiên lệch khác với làm tròn.

---

## 14. `$ceil` và `$floor`: làm tròn theo hướng xác định

Cú pháp:

```javascript
{ $ceil: <expression> }
{ $floor: <expression> }
```

- `$ceil`: số nguyên nhỏ nhất **lớn hơn hoặc bằng** đầu vào (hướng về dương vô cực).
- `$floor`: số nguyên lớn nhất **nhỏ hơn hoặc bằng** đầu vào (hướng về âm vô cực).

| Đầu vào | `$ceil` | `$floor` | `$trunc` với place 0 |
| --- | ---: | ---: | ---: |
| `1.2` | 2 | 1 | 1 |
| `1.9` | 2 | 1 | 1 |
| `-1.2` | -1 | -2 | -1 |
| `-1.9` | -1 | -2 | -1 |
| `-2.0` | -2 | -2 | -2 |

Ví dụ đếm số hộp cần dùng nếu mỗi hộp chứa tối đa 6 sản phẩm:

```javascript
db.packages.aggregate([
  {
    $project: {
      boxesNeeded: {
        $ceil: {
          $divide: ["$itemCount", 6]
        }
      }
    }
  }
]);
```

Nếu có 13 sản phẩm, cần 3 hộp. Ứng dụng phải validate `itemCount >= 0` và capacity > 0. Nếu không, công thức có thể tạo kết quả không có ý nghĩa vận hành.

### 14.1. Đừng dùng `$round` khi cần luôn đủ tài nguyên

Nếu phân bổ container, trang, thùng hàng hoặc lượt xe, thường cần **ceiling**, không phải làm tròn gần nhất:

```text
13 / 6 = 2.166...
round -> 2  (không đủ)
ceil  -> 3  (đủ)
```

### 14.2. Đừng dùng `$floor` cho số âm mà mong truncation

`floor(-1.9) = -2`, còn `trunc(-1.9) = -1`. Nếu dữ liệu có thể âm, kết quả khác nhau rõ ràng.

---

## 15. Bảng so sánh các toán tử làm tròn

| Nhu cầu | Toán tử | Quy tắc |
| --- | --- | --- |
| Làm tròn số gần nhất, tie to even | `$round` | Có thể chỉ định `place`. |
| Bỏ phần vượt quá số chữ số cần giữ | `$trunc` | Cắt theo hướng về 0, có thể chỉ định `place`. |
| Luôn làm tròn lên hướng dương vô cực | `$ceil` | Không nhận `place` theo dạng `$round`; cho giá trị số nguyên. |
| Luôn làm tròn xuống hướng âm vô cực | `$floor` | Không nhận `place` theo dạng `$round`; cho giá trị số nguyên. |

Với số tiền dạng Decimal128 và quy tắc hai chữ số sau dấu thập phân, `$round: ["$amount", 2]` rất tiện, nhưng phải xác nhận **half-even** đúng chính sách thanh toán.

### 15.1. Không làm tròn quá sớm

Giả sử có hai số thập phân:

```text
A = 0.005
B = 0.005
```

Nếu làm tròn từng phần tử tới 2 chữ số bằng half-even:

```text
round(A, 2) = 0.00
round(B, 2) = 0.00
Tổng        = 0.00
```

Nếu cộng trước rồi làm tròn:

```text
A + B       = 0.010
round(...,2)= 0.01
```

**Hai quy trình khác nhau cho kết quả khác nhau.** Không thể tuyên bố một quy trình luôn đúng cho mọi hóa đơn. Cần quyết định nghiệp vụ làm tròn theo dòng hàng, theo nhóm thuế hay theo tổng hóa đơn.

Trong kế toán, còn phải quy định cách xử lý sai lệch do phân bổ phần dư, ngoại tệ và tỷ giá. Decimal128 chỉ giúp thực hiện phép tính theo kiểu số phù hợp, không tự quyết định chính sách đó.

---

## 16. `$sum` và `$avg`: phép tính trên mảng và trên nhóm

Các toán tử `$sum` và `$avg` vừa xuất hiện trong aggregation expression, vừa phổ biến với `$group`. **Ngữ cảnh có thể ảnh hưởng cách chúng xử lý một field mảng.**

### 16.1. Cộng các field trong một document

Trong `$project` hoặc `$set`:

```javascript
db.testScores.aggregate([
  {
    $project: {
      totalScore: {
        $sum: "$scores"
      },
      avgScore: {
        $avg: "$scores"
      }
    }
  }
]);
```

Nếu document có `scores: [80, 90, 100]`, trong ngữ cảnh expression với một toán hạng trỏ tới mảng, `$sum` có thể duyệt các phần tử số để lấy 270, còn `$avg` cho 90.

### 16.2. Cộng qua nhiều document bằng `$group`

Với collection `orderLines`:

```javascript
db.orderLines.aggregate([
  {
    $set: {
      lineSubtotal: {
        $multiply: [
          "$quantity",
          "$unitPrice"
        ]
      }
    }
  },
  {
    $group: {
      _id: "$orderId",
      subtotal: {
        $sum: "$lineSubtotal"
      },
      averageLineAmount: {
        $avg: "$lineSubtotal"
      },
      lineCount: { $sum: 1 }
    }
  }
]);
```

Pipeline:

1. Tính `lineSubtotal` cho mỗi document dòng hàng.
2. Nhóm theo `orderId`.
3. Cộng tất cả giá trị của các document trong cùng nhóm.
4. Tính trung bình các dòng có giá trị số phù hợp.
5. Đếm số document dòng hàng bằng `$sum: 1`.

Trong dataset mẫu:

```text
L1: 3 × 19.95 = 59.85
L2: 2 ×  4.20 =  8.40
Tổng O100     = 68.25
```

`$sum` trong `$group` là accumulator qua **nhiều document**, không phải cú pháp cộng trực tiếp tất cả phần tử của một array field theo cách của expression ngoài `$group`.

### 16.3. Bẫy array traversal

Giả sử document có `scores: [80, 90]`.

Trong `$project`:

```javascript
{
  $project: {
    scoreTotal: { $sum: "$scores" }
  }
}
```

có thể duyệt mảng và cộng thành 170.

Nhưng trong `$group`:

```javascript
{
  $group: {
    _id: "$studentId",
    scoreTotal: { $sum: "$scores" }
  }
}
```

`$sum` accumulator **không tự duyệt từng phần tử mảng** như trường hợp expression một toán hạng ở `$project`. Một giá trị array không được xử lý như một số cần cộng. Nếu muốn tổng điểm qua mọi document, hãy tính tổng mảng của từng document trước `$group`, hoặc `$unwind` phù hợp.

Một cách rõ ràng:

```javascript
db.students.aggregate([
  {
    $set: {
      scoreTotalOfDocument: {
        $sum: "$scores"
      }
    }
  },
  {
    $group: {
      _id: "$classId",
      classTotal: {
        $sum: "$scoreTotalOfDocument"
      }
    }
  }
]);
```

### 16.4. `null`, giá trị phi số trong `$sum` và `$avg`

Các accumulator/expression này có quy tắc riêng về việc bỏ qua giá trị không phải số. `$sum` có thể cho 0 khi không có toán hạng số hợp lệ, còn `$avg` có thể cho `null` khi không có giá trị số để tính trung bình.

**Đừng suy ra cùng một hành vi cho `$add`, `$divide`, `$sum` và `$avg`.** Từng toán tử có contract về `null`, missing và kiểu dữ liệu. Nếu dữ liệu bắt buộc là decimal, nên chặn dữ liệu sai bằng validation thay vì chỉ dựa vào việc `$sum` bỏ qua một giá trị không hợp lệ.

---

## 17. Chuyển kiểu bằng `$toDecimal` và `$convert`

Trong hệ thống đã hoạt động lâu, một collection có thể chứa:

```javascript
{ _id: "A", unitPrice: NumberDecimal("19.95") }
{ _id: "B", unitPrice: "19.95" }
{ _id: "C", unitPrice: 19.95 }
{ _id: "D", unitPrice: null }
{ _id: "E", unitPrice: "N/A" }
```

Một pipeline tính tiền không nên giả định mọi document đều có Decimal128. Có thể dùng `$toDecimal`:

```javascript
db.prices.aggregate([
  {
    $project: {
      convertedPrice: {
        $toDecimal: "$unitPrice"
      }
    }
  }
]);
```

Tuy nhiên, nếu chuỗi là `"N/A"` hoặc kiểu không chuyển đổi được, pipeline có thể lỗi. Dữ liệu sai không nên được giấu đi bằng việc ép sang 0.

### 17.1. `$convert` với xử lý lỗi chuyển kiểu

```javascript
db.prices.aggregate([
  {
    $project: {
      original: "$unitPrice",
      decimalValue: {
        $convert: {
          input: "$unitPrice",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Cách này chủ động cho `null` khi chuyển kiểu lỗi hoặc đầu vào null. Nó hữu ích cho bước **kiểm kê/làm sạch dữ liệu**, nhưng cần kiểm soát:

- `null` do thiếu giá trị có khác `null` do chuỗi `"N/A"` không?
- Báo cáo có được phép loại những dòng không chuyển được không?
- Nếu là tiền, dữ liệu sai có phải vào hàng lỗi thay vì tự coi như 0?
- Sau conversion, có cần ràng buộc số tiền không âm và giới hạn giá trị không?

**Chuyển Double sang Decimal128 sau khi đã lưu Double không bảo đảm khôi phục decimal ban đầu mà người dùng dự định.** Có thể chỉ giữ lại hoặc diễn giải lại giá trị đã qua biểu diễn nhị phân. Khi cần độ chính xác tài chính, nên chuẩn hóa ngay từ điểm nhận dữ liệu.

### 17.2. `$isNumber` và `$type`

```javascript
db.prices.aggregate([
  {
    $project: {
      sourceType: {
        $type: "$unitPrice"
      },
      numeric: {
        $isNumber: "$unitPrice"
      }
    }
  }
]);
```

`$isNumber` giúp nhận diện các kiểu số BSON, nhưng nó không có nghĩa đơn giá đã là Decimal128. Nếu quy tắc yêu cầu **đúng decimal**, hãy kiểm tra `$type` là `"decimal"` hoặc áp schema validation từ trước.

---

## 18. Một pipeline hóa đơn hoàn chỉnh bằng Decimal128

Giả sử collection `invoices` có một document:

```javascript
db.invoices.insertOne({
  _id: "INV-100",
  currency: "USD",
  items: [
    {
      sku: "A",
      quantity: 2,
      unitPrice: NumberDecimal("19.95")
    },
    {
      sku: "B",
      quantity: 3,
      unitPrice: NumberDecimal("4.20")
    }
  ],
  discountRate: NumberDecimal("0.10"),
  taxRate: NumberDecimal("0.08"),
  shippingFee: NumberDecimal("5.00")
});
```

**Quy tắc minh họa:**

1. Tính thành tiền của từng dòng bằng số lượng nhân đơn giá.
2. Cộng tất cả dòng thành `subtotal`.
3. Giảm giá 10% trên `subtotal`, làm tròn đến 2 chữ số bằng `$round`.
4. Tính thuế 8% trên `subtotal` sau chiết khấu, làm tròn 2 chữ số.
5. Cộng phí vận chuyển 5.00.
6. Giữ kiểu Decimal128 xuyên suốt các phép tính tiền.

### 18.1. Pipeline từng bước

```javascript
db.invoices.aggregate([
  {
    $match: {
      _id: "INV-100"
    }
  },
  {
    $set: {
      calculatedLines: {
        $map: {
          input: "$items",
          as: "item",
          in: {
            sku: "$$item.sku",
            quantity: "$$item.quantity",
            unitPrice: "$$item.unitPrice",
            lineAmount: {
              $multiply: [
                "$$item.unitPrice",
                { $toDecimal: "$$item.quantity" }
              ]
            }
          }
        }
      }
    }
  },
  {
    $set: {
      subtotal: {
        $sum: "$calculatedLines.lineAmount"
      }
    }
  },
  {
    $set: {
      discountAmount: {
        $round: [
          {
            $multiply: [
              "$subtotal",
              "$discountRate"
            ]
          },
          2
        ]
      }
    }
  },
  {
    $set: {
      taxableAmount: {
        $subtract: [
          "$subtotal",
          "$discountAmount"
        ]
      }
    }
  },
  {
    $set: {
      taxAmount: {
        $round: [
          {
            $multiply: [
              "$taxableAmount",
              "$taxRate"
            ]
          },
          2
        ]
      }
    }
  },
  {
    $set: {
      grandTotal: {
        $add: [
          "$taxableAmount",
          "$taxAmount",
          "$shippingFee"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      currency: 1,
      calculatedLines: 1,
      subtotal: 1,
      discountRate: 1,
      discountAmount: 1,
      taxableAmount: 1,
      taxRate: 1,
      taxAmount: 1,
      shippingFee: 1,
      grandTotal: 1
    }
  }
]);
```

### 18.2. Giải thích chi tiết

**Stage 1 — `$match`**

Tìm một hóa đơn cụ thể. Nếu `_id` được lập index mặc định, MongoDB có thể tìm nhanh document trước khi thực hiện phép tính.

**Stage 2 — `$map`**

Duyệt từng phần tử của mảng `items`. Biến `$$item` là phần tử hiện tại. Kết quả mỗi phần tử có thêm `lineAmount`, được tính bằng Decimal128 nhờ `unitPrice` và chuyển `quantity` sang decimal.

**Stage 3 — `$sum`**

Ở `$set`, biểu thức `$sum: "$calculatedLines.lineAmount"` nhận mảng các line amount và cộng các giá trị số. Đây không phải accumulator `$sum` trong `$group`.

**Stage 4 — giảm giá**

Tính `subtotal × discountRate`, sau đó dùng `$round` với `place = 2`.

**Stage 5 — giá trị tính thuế**

Lấy `subtotal - discountAmount`.

**Stage 6 — thuế**

Tính `taxableAmount × taxRate`, làm tròn 2 chữ số.

**Stage 7 — tổng thanh toán**

Cộng `taxableAmount`, `taxAmount` và `shippingFee`.

### 18.3. Kết quả số học mong đợi

| Thành phần | Phép tính | Giá trị |
| --- | --- | ---: |
| Line A | `2 × 19.95` | 39.90 |
| Line B | `3 × 4.20` | 12.60 |
| Subtotal | `39.90 + 12.60` | 52.50 |
| Discount | `52.50 × 0.10` | 5.25 |
| Taxable amount | `52.50 - 5.25` | 47.25 |
| Tax | `round(47.25 × 0.08, 2)` | 3.78 |
| Shipping | Giá trị có sẵn | 5.00 |
| Grand total | `47.25 + 3.78 + 5.00` | **56.03** |

Các giá trị trong bảng là **giá trị toán học**; khi xem BSON Decimal128, dạng biểu diễn chữ số 0 cuối có thể khác mà vẫn cùng giá trị số. API cần định dạng tiền theo quy ước riêng.

### 18.4. Vì sao chia pipeline thành nhiều `$set`?

Các stage tách biệt giúp minh bạch thứ tự:

```text
items
  |
  v
lineAmount (Decimal128)
  |
  v
subtotal
  |
  +--> discountAmount
          |
          v
      taxableAmount
          |
          v
       taxAmount
          |
          v
       grandTotal
```

Trong một `$set` stage, không nên dựa vào việc field mới được tính trước đó cùng stage chắc chắn có thể tham chiếu như document đầu vào đã đổi. Tách stage giúp biểu thức sau đọc giá trị được tạo bởi stage trước theo contract pipeline.

### 18.5. Cần validation trước pipeline

Pipeline giả định:

- `items` là mảng.
- `quantity` là số nguyên không âm hoặc dương theo nghiệp vụ.
- `unitPrice`, `discountRate`, `taxRate`, `shippingFee` đều hợp lệ, dùng Decimal128.
- `discountRate` và `taxRate` theo quy ước 0–1.
- Không có giá trị `null`, NaN hoặc dữ liệu sai kiểu ở các field bắt buộc.

Nếu một document sai schema, có thể cần báo lỗi, loại khỏi xử lý hoặc đưa vào workflow sửa dữ liệu. Không nên tự đặt mọi trường lỗi thành 0, vì có thể tạo hóa đơn sai mà không phát hiện.

### 18.6. Quy tắc thuế và làm tròn chỉ mang tính minh họa

Ví dụ áp chiết khấu trước thuế và tính thuế trên phần còn lại. Trong thực tế, các quốc gia, loại thuế, đơn vị tiền và hóa đơn có thể quy định **phải làm tròn ở dòng hàng**, theo thuế suất hoặc theo tổng; có thể có thuế đã bao gồm trong giá hay nhiều mức thuế.

Không dùng trực tiếp pipeline ví dụ làm engine tính thuế production nếu chưa xác nhận quy định nghiệp vụ và kiểm thử với các ca biên.

---

## 19. Làm tròn theo dòng hay theo tổng: khác biệt có thật

Giả sử hai dòng có giá trị thuế thô:

```text
Dòng 1: 0.005
Dòng 2: 0.005
```

**Cách A — làm tròn mỗi dòng rồi cộng:**

```text
round(0.005, 2) = 0.00
round(0.005, 2) = 0.00
Tổng thuế        = 0.00
```

**Cách B — cộng thuế thô rồi mới làm tròn:**

```text
0.005 + 0.005   = 0.010
round(0.010, 2) = 0.01
```

Kết quả lệch một cent. Không thể gọi một cách “đúng” nếu chưa xác định quy tắc của hệ thống.

Trong MongoDB, sự khác nhau còn thể hiện ở vị trí đặt `$round`:

```javascript
// Tính thuế từng dòng, làm tròn từng dòng,
// rồi dùng $sum trên các dòng đã làm tròn.
{
  $sum: {
    $map: {
      input: "$items",
      as: "item",
      in: {
        $round: [
          {
            $multiply: [
              "$$item.amount",
              "$taxRate"
            ]
          },
          2
        ]
      }
    }
  }
}
```

So với:

```javascript
// Cộng các giá trị gốc rồi tính thuế/làm tròn một lần.
{
  $round: [
    {
      $multiply: [
        { $sum: "$items.amount" },
        "$taxRate"
      ]
    },
    2
  ]
}
```

Hai biểu thức giả định `items.amount` và `taxRate` đã là Decimal128 hợp lệ. Chúng có thể cho kết quả khác nhau vì **thời điểm rounding khác**, không phải do MongoDB tính sai.

### 19.1. Phép làm tròn có thể phá tính kết hợp

Về toán học thực, phép cộng có tính kết hợp. Nhưng khi chèn bước làm tròn:

```text
round(round(a, 2) + round(b, 2), 2)
```

không nhất thiết bằng:

```text
round(a + b, 2)
```

Nếu ứng dụng tính line total trước, sau đó lại dùng các line total đã làm tròn để tính tỷ lệ, sai lệch có thể tích lũy. Cần định nghĩa rõ field nào là **raw high precision** và field nào là **display/settlement amount**.

---

## 20. Tiền bằng Decimal128 hay integer minor units?

Hai phương pháp phổ biến trong hệ thống tài chính là:

### 20.1. Decimal128

```javascript
{
  price: NumberDecimal("19.95"),
  currency: "USD"
}
```

Ưu điểm:

- Phù hợp phép tính tỷ lệ và giá trị decimal.
- Biểu diễn chính xác nhiều giá trị thập phân thông dụng.
- Có toán tử aggregation trực tiếp.

Cần chú ý:

- Precision hữu hạn 34 chữ số có nghĩa.
- Chọn quy tắc rounding và thời điểm rounding.
- Kiểm tra range, overflow và số đặc biệt.
- Driver/client phải giữ đúng kiểu BSON.

### 20.2. Integer minor units

```javascript
{
  priceMinor: NumberLong("1995"),
  currency: "USD"
}
```

Ở đây đơn vị là **cent**, không phải USD. Ưu điểm là phép cộng/trừ trên integer đơn vị nhỏ nhất dễ kiểm soát nếu số tiền nằm trong giới hạn. Nhưng:

- Phải biết đơn vị nhỏ nhất của từng currency.
- Phân bổ thuế/chiết khấu thường tạo giá trị phân số minor unit, vẫn cần quy tắc làm tròn.
- Có nguy cơ tràn Int64 nếu tổng hoặc phép nhân quá lớn.
- Không nên giả định mọi currency có đúng hai chữ số thập phân.

### 20.3. Chuyển Decimal128 thành minor units

Ví dụ khi chính sách đã xác định giá trị tiền có hai chữ số thập phân:

```javascript
db.invoices.aggregate([
  {
    $project: {
      grandTotalMinor: {
        $toLong: {
          $round: [
            {
              $multiply: [
                "$grandTotal",
                NumberDecimal("100")
              ]
            },
            0
          ]
        }
      }
    }
  }
]);
```

Nhân Decimal128 với 100, làm tròn theo quy tắc đã chọn, sau đó chuyển sang Long. Phải validate:

- Kết quả nằm trong phạm vi Int64.
- Currency thực sự có scale tương ứng.
- Nghiệp vụ chấp nhận half-even.
- `grandTotal` không null, NaN, vô cực hoặc sai kiểu.

Nếu chuyển thẳng `$toLong` mà không quyết định làm tròn, conversion có thể cắt phần thập phân theo contract, dẫn đến kết quả không như kỳ vọng.

---

## 21. Null, missing, dữ liệu lỗi và overflow

### 21.1. Các toán tử không xử lý null giống nhau

| Toán tử | Hành vi cần chú ý |
| --- | --- |
| `$add`, `$multiply`, `$subtract`, `$divide` | Đầu vào null/missing có thể làm kết quả null hoặc gây vấn đề tùy biểu thức; phải đọc contract từng toán tử. |
| `$round`, `$trunc`, `$ceil`, `$floor` | Có ngữ nghĩa riêng khi đầu vào null/missing và với giá trị đặc biệt. |
| `$sum` | Có thể bỏ qua giá trị phi số và trả 0 nếu không có giá trị số hợp lệ. |
| `$avg` | Có thể bỏ qua giá trị phi số; nếu không có số phù hợp, có thể trả null. |
| `$toDecimal` | Có thể lỗi nếu chuỗi/kiểu không chuyển được; dùng `$convert` để xử lý có chủ đích. |

Không viết pipeline tính tiền mà xem mọi giá trị thiếu như 0 trừ khi domain quy định rõ.

### 21.2. Validation ở collection

Ví dụ một collection yêu cầu đơn giá kiểu decimal không âm và số lượng Int32 ít nhất 1:

```javascript
db.createCollection("validatedLines", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["unitPrice", "quantity"],
      properties: {
        unitPrice: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        quantity: {
          bsonType: "int",
          minimum: 1
        }
      }
    }
  },
  validationAction: "error"
});
```

Validator này chỉ minh họa hai điều kiện. Để dùng thật, cần thêm các ràng buộc như currency, giới hạn số lượng, giới hạn tiền, khả năng âm của refund và cấu trúc line items.

**Collection validation không thay thế business validation ở Java.** Nó bảo vệ dữ liệu trong DB ngay cả khi một tiến trình khác ghi trực tiếp qua driver.

### 21.3. Chia cho 0 và các phép toán ngoài miền

- `$divide` và `$mod` cần mẫu số hợp lệ, không bằng 0.
- `$sqrt`, `$ln`, `$log` có miền giá trị đầu vào.
- Những biểu thức lũy thừa/tính lãi có thể overflow hoặc tạo giá trị đặc biệt.
- Không để số `NaN`/Infinity đi vào dữ liệu tiền mà không phát hiện.

Nếu dữ liệu bất hợp lệ, nên quyết định **reject, quarantine hoặc return null** có chủ đích. Trả 0 trong mọi trường hợp có thể làm báo cáo tài chính sai nhưng không báo lỗi.

### 21.4. Decimal128 có thể overflow hoặc mất chữ số có nghĩa

34 chữ số có nghĩa là giới hạn về precision chứ không phải “34 chữ số sau dấu thập phân”. Giá trị rất lớn hoặc phép chia có phần lẻ dài có thể cần làm tròn ở cấp Decimal128. Các giá trị vượt phạm vi biểu diễn có thể gặp trường hợp đặc biệt.

Nếu một ứng dụng đòi độ chính xác cao hơn Decimal128 hoặc tính toán kế toán phức tạp, cần đánh giá kiến trúc lưu trữ và phép tính phù hợp, không mặc định Decimal128 giải quyết tất cả.

---

## 22. Tính tỷ lệ tăng trưởng và tránh sai lệch công thức

Một báo cáo doanh thu có:

```javascript
{
  oldRevenue: NumberDecimal("1250.00"),
  newRevenue: NumberDecimal("1375.00")
}
```

Tỷ lệ tăng trưởng phần trăm:

```text
(newRevenue - oldRevenue) / oldRevenue × 100
```

Biểu thức:

```javascript
db.revenueSnapshots.aggregate([
  {
    $project: {
      growthPercent: {
        $cond: [
          { $eq: ["$oldRevenue", NumberDecimal("0")] },
          null,
          {
            $round: [
              {
                $multiply: [
                  {
                    $divide: [
                      {
                        $subtract: [
                          "$newRevenue",
                          "$oldRevenue"
                        ]
                      },
                      "$oldRevenue"
                    ]
                  },
                  NumberDecimal("100")
                ]
              },
              2
            ]
          }
        ]
      }
    }
  }
]);
```

Với 1250 lên 1375, tăng trưởng là **10.00%**.

Đây là công thức giả định `oldRevenue` và `newRevenue` có cùng currency, cùng cách ghi nhận doanh thu và cùng kỳ so sánh. Nếu số gốc bằng 0, phần trăm tăng trưởng thường **không xác định** theo công thức này; trả `null` là một lựa chọn minh bạch hơn tự động trả 100%.

Nếu số gốc âm, cách diễn giải “phần trăm tăng trưởng” có thể đặc biệt trong nghiệp vụ; phải xác nhận policy thay vì chỉ tin kết quả toán học.

---

## 23. Decimal128 trong MongoDB Java Sync Driver

### 23.1. Ghi Decimal128 từ BigDecimal

Java có `java.math.BigDecimal` cho decimal arithmetic, còn BSON dùng `org.bson.types.Decimal128`.

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;

public final class DecimalWriteExample {

    public static void insertLine(MongoCollection<Document> collection) {
        BigDecimal price = new BigDecimal("19.95");
        BigDecimal rate  = new BigDecimal("0.08");

        Document document = new Document("_id", "LINE-JAVA-1")
            .append("quantity", 3)
            .append("unitPrice", new Decimal128(price))
            .append("taxRate", new Decimal128(rate));

        collection.insertOne(document);
    }
}
```

Nếu BigDecimal vượt phạm vi Decimal128, phép chuyển có thể không được chấp nhận theo contract của driver. Không nên âm thầm chuyển sang Double để “cứ ghi cho được” một giá trị tài chính không biểu diễn được.

### 23.2. Dùng `Decimal128.parse`

```java
Decimal128 amount = Decimal128.parse("123.45");
```

Hữu ích khi đầu vào là chuỗi thập phân hợp lệ, nhưng vẫn cần validation ở tầng API. Với tiền tệ, input không nên chấp nhận các chuỗi tùy tiện hoặc giá trị đặc biệt ngoài contract.

### 23.3. Đọc Decimal128 về BigDecimal

```java
Document line = collection.find(
    new Document("_id", "LINE-JAVA-1")
).first();

if (line != null) {
    Decimal128 bsonDecimal =
        line.get("unitPrice", Decimal128.class);

    BigDecimal price = bsonDecimal.bigDecimalValue();

    System.out.println(price.toPlainString());
}
```

Trước khi gọi `bigDecimalValue()`, bảo đảm giá trị không null và là giá trị Decimal128 hữu hạn mà ứng dụng hỗ trợ. Không ép sang `double` chỉ để format tiền, vì có thể làm mất ý nghĩa decimal mong muốn.

### 23.4. Đọc kết quả aggregation bằng Java

Ví dụ tính thành tiền và làm tròn hai chữ số trên server:

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.util.List;

public final class DecimalAggregationExample {

    public static BigDecimal calculate(
            MongoCollection<Document> collection,
            String lineId
    ) {
        Bson match = new Document("$match",
            new Document("_id", lineId));

        Document raw = new Document("$multiply",
            List.of("$quantity", "$unitPrice"));

        Bson project = new Document("$project",
            new Document("_id", 0)
                .append("roundedAmount",
                    new Document("$round", List.of(raw, 2))));

        Document result = collection.aggregate(
            List.of(match, project)
        ).first();

        if (result == null) {
            throw new IllegalArgumentException(
                "Line not found: " + lineId
            );
        }

        Decimal128 bsonAmount = result.get(
            "roundedAmount",
            Decimal128.class
        );

        if (bsonAmount == null) {
            throw new IllegalStateException(
                "Rounded amount missing or not decimal"
            );
        }

        return bsonAmount.bigDecimalValue();
    }
}
```

Đoạn code dựa trên schema `quantity` numeric và `unitPrice` Decimal128 để toán tử `$multiply` cho kết quả Decimal128. Trong ứng dụng production, cần xử lý chính sách với số đặc biệt, null, lỗi driver và validation dữ liệu.

### 23.5. Quy tắc làm tròn trong Java không tự giống MongoDB

Java `BigDecimal` có nhiều `RoundingMode`, ví dụ:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal value = new BigDecimal("2.5");

BigDecimal halfEven = value.setScale(0, RoundingMode.HALF_EVEN);
// 2

BigDecimal halfUp = value.setScale(0, RoundingMode.HALF_UP);
// 3
```

MongoDB `$round` áp dụng **half-even** khi tie. Nếu business dùng `HALF_UP` trong Java nhưng dùng `$round` trong aggregation, cùng một giá trị đúng giữa có thể cho kết quả khác nhau. Cần thống nhất policy giữa service, database, báo cáo, import/export và UI.

### 23.6. DTO, JSON và API contract

Nếu API trả:

```json
{
  "amount": 19.95
}
```

một client JavaScript có thể đọc nó thành Number dạng Double. Nếu hệ thống cần bảo toàn decimal đầu-cuối, có thể sử dụng chuỗi decimal:

```json
{
  "amount": "19.95",
  "currency": "USD"
}
```

hoặc integer minor units:

```json
{
  "amountMinor": 1995,
  "currency": "USD"
}
```

Cách nào tốt hơn tùy contract hệ thống. Không dùng cách thứ nhất một cách vô thức rồi kỳ vọng mọi client và ngôn ngữ đều giữ kiểu Decimal128.

---

## 24. Khả năng tận dụng index và chi phí tính toán

Aggregation cho phép tính nhiều field ngay trên MongoDB, nhưng điều đó không có nghĩa mọi biểu thức đều dùng index hiệu quả.

### 24.1. Đặt `$match` sớm khi phù hợp

```javascript
db.orderLines.aggregate([
  {
    $match: {
      orderId: "O100"
    }
  },
  {
    $set: {
      lineSubtotal: {
        $multiply: [
          "$quantity",
          "$unitPrice"
        ]
      }
    }
  }
]);
```

Nếu có index trên `orderId`, server có thể thu hẹp tập document trước khi nhân các giá trị. Điều này thường hiệu quả hơn việc tính số học trên toàn collection rồi mới lọc.

### 24.2. Filter trên biểu thức có thể hạn chế index

Ví dụ:

```javascript
db.orderLines.find({
  $expr: {
    $gt: [
      {
        $multiply: [
          "$quantity",
          "$unitPrice"
        ]
      },
      NumberDecimal("100")
    ]
  }
});
```

MongoDB phải đánh giá biểu thức để biết thành tiền, và không thể mặc định dùng index đơn trên `quantity` hoặc `unitPrice` như một điều kiện range trực tiếp. Tùy phiên bản và hình dạng query, một số biểu thức `$expr` có thể được tối ưu, nhưng **không nên mặc định mọi phép tính động đều indexable**.

Nếu đây là filter quan trọng xuất hiện thường xuyên, có thể cân nhắc lưu `lineSubtotal` dưới dạng field dẫn xuất và duy trì đồng bộ khi dữ liệu thay đổi; khi ấy index trên `lineSubtotal` có thể phù hợp. Đổi lại, update `quantity`/`unitPrice` phải cập nhật trường tính sẵn và các index liên quan.

### 24.3. `$group` có thể cần nhiều bộ nhớ

Aggregation tính tổng từ hàng triệu dòng có thể phải đọc và nhóm rất nhiều document. Một index chọn lọc giúp lọc đầu vào, nhưng không khiến phép tính tổng tất cả các dòng trở thành chi phí bằng 0.

Khi dashboard phải tính cùng tổng nhiều lần, mô hình pre-aggregation hoặc computed pattern có thể tốt hơn tính lại mọi lần; cần quy tắc cập nhật, đối soát và xử lý dữ liệu đến muộn.

### 24.4. Số học không thay thế tối ưu dữ liệu

Nếu pipeline trả quá nhiều document, network, BSON decode và mapping ở Java vẫn đắt. Tính số trên server giúp giảm truyền dữ liệu thô trong một số trường hợp, nhưng phải đo execution plan và end-to-end latency để quyết định nơi thực hiện phép tính.

---

## 25. Những tình huống nghiệp vụ dễ sai

### Tình huống A — Tổng tiền lệch vì dùng Double

Đơn giá được nhận qua JSON number `0.1`, sau đó cộng nhiều lần bằng số thực nhị phân. Kết quả có thể có sai số biểu diễn nhỏ.

**Hướng xử lý:** xác định contract decimal từ đầu vào, dùng Decimal128/BigDecimal hoặc integer minor units nhất quán, không chuyển sang decimal sau khi phép tính Double đã gây sai lệch rồi coi như đã sửa triệt để.

### Tình huống B — Half-even khác HALF_UP

Giá trị `2.5`:

- MongoDB `$round(..., 0)` chọn **2** theo half-even.
- Java `BigDecimal.setScale(0, HALF_UP)` cho **3**.

**Hướng xử lý:** thống nhất chính sách làm tròn ngay ở domain. Không gán nhãn chung “làm tròn thông thường” cho cả hai.

### Tình huống C — Cắt số âm bằng `$floor`

`-1.9` nếu cắt phần thập phân hướng về 0 phải thành `-1`. `$floor` lại cho `-2`.

**Hướng xử lý:** dùng `$trunc` nếu nghiệp vụ yêu cầu loại phần lẻ theo hướng về 0.

### Tình huống D — Chia cho 0

Một báo cáo tính tỷ lệ `completed / total` khi `total = 0`. Chỉ viết `$divide` có thể làm query lỗi.

**Hướng xử lý:** định nghĩa trạng thái “không xác định”, bảo vệ mẫu số và phân biệt 0 với missing/null.

### Tình huống E — Tính trung bình khi dữ liệu có string

Collection có `scores: [80, "90", 100]`, dùng `$avg` có thể bỏ qua giá trị không phải số thay vì tự chuyển chuỗi `"90"` theo ý người dùng.

**Hướng xử lý:** validation và chuyển kiểu có kiểm soát; không tin rằng accumulator đã làm sạch dữ liệu.

### Tình huống F — Làm tròn mỗi dòng trước khi cộng

Hai dòng thuế `0.005` và `0.005` có thể tổng thành `0.00` nếu làm tròn từng dòng half-even, nhưng `0.01` nếu cộng trước rồi làm tròn.

**Hướng xử lý:** quy định thứ tự tính và rounding rõ ràng trong engine hóa đơn.

### Tình huống G — Số nguyên minor units vượt phạm vi

Giá được lưu Int64, nhưng phép nhân số lượng lớn khiến tổng vượt giới hạn. MongoDB có thể nâng kiểu hoặc gặp trường hợp overflow tùy toán tử; nếu chuyển ngầm sang Double, độ chính xác nguyên có thể không còn như mong muốn.

**Hướng xử lý:** kiểm tra range, thiết kế giới hạn nghiệp vụ và chuyển kiểu có chủ đích. Không dựa vào overflow tự động để giữ tính chính xác tài chính.

### Tình huống H — API làm mất Decimal128

MongoDB trả Decimal128 nhưng tầng JSON serialize thành number, frontend JavaScript lại dùng Double và tiếp tục tính toán.

**Hướng xử lý:** xác định DTO contract: decimal string hoặc minor units, cộng với quy tắc parse/format thống nhất ở client.

---

## 26. Bài tập thực hành và gợi ý

### Bài 1 — Tổng dòng hàng

Dòng hàng:

```javascript
{
  quantity: 4,
  unitPrice: NumberDecimal("12.75")
}
```

Hãy viết `$multiply` và xác định kết quả.

**Gợi ý:**

```javascript
{
  $multiply: [
    "$quantity",
    "$unitPrice"
  ]
}
```

Kết quả số học là **51.00**.

### Bài 2 — Khác biệt `$round` và `$trunc`

Với `NumberDecimal("8.987")` và `place = 2`:

- `$round` cho giá trị **8.99**.
- `$trunc` cho giá trị **8.98**.

Thử trường hợp âm `-8.987` và giải thích vì sao hai phép vẫn khác nhau.

### Bài 3 — Half-even

Dự đoán:

```javascript
{ $round: [NumberDecimal("4.5"), 0] }
{ $round: [NumberDecimal("5.5"), 0] }
{ $round: [NumberDecimal("-2.5"), 0] }
```

**Đáp án:** giá trị lần lượt là **4**, **6**, **-2**; khi đúng giữa, chọn kết quả có chữ số hàng đơn vị chẵn.

### Bài 4 — Phòng lỗi chia cho 0

Viết biểu thức `completed / total × 100` làm tròn 2 chữ số, trả null khi total bằng 0.

**Gợi ý:** `$cond` ở ngoài, `$eq` kiểm tra mẫu số, bên trong dùng `$divide`, `$multiply`, `$round` và Decimal128. Mở rộng validation cho null/missing.

### Bài 5 — Decimal128 hay Double?

Một service nhận giá `"0.10"` và `"0.20"` từ payload. Hãy nêu sự khác nhau giữa:

```javascript
NumberDecimal("0.10")
NumberDecimal("0.20")
```

và các giá trị Double `0.1`, `0.2`. Vì sao chuyển sang Decimal128 **sau khi đã tính bằng Double** không phải chiến lược đảm bảo chính xác tối ưu?

### Bài 6 — `$sum` trong `$project` và `$group`

Document:

```javascript
{
  studentId: "S1",
  classId: "C1",
  scores: [80, 90, 100]
}
```

Giải thích khác biệt giữa:

```javascript
{ $project: { total: { $sum: "$scores" } } }
```

và:

```javascript
{
  $group: {
    _id: "$classId",
    total: { $sum: "$scores" }
  }
}
```

**Gợi ý:** expression ngoài `$group` có thể duyệt array theo quy tắc một toán hạng; accumulator `$group` không coi toàn bộ array là một số. Có thể tính tổng từng document trước khi `$group`.

### Bài 7 — Rounding policy của hóa đơn

Hai dòng có thuế thô `0.005`, `0.005`. Tính tổng khi:

1. Round từng dòng rồi cộng.
2. Cộng rồi round một lần.

Giải thích vì sao cần xác định chính sách trước khi triển khai pipeline.

### Bài 8 — Đọc Decimal128 trong Java

Viết code đọc field `total` kiểu `Decimal128` từ `Document`, chuyển sang `BigDecimal`, sau đó định dạng hai chữ số bằng `toPlainString()` sau `setScale(2, ...)` với một `RoundingMode` được chỉ định rõ.

**Gợi ý:** không chuyển qua `double` ở giữa; kiểm tra null và giá trị đặc biệt.

### Bài 9 — Tính tiền sau giảm giá

Document:

```javascript
{
  subtotal: NumberDecimal("80.00"),
  discountRate: NumberDecimal("0.125")
}
```

Viết các biểu thức:

- `discountAmount = $round($multiply(...), 2)`.
- `net = $subtract(subtotal, discountAmount)`.

**Đáp án:** giảm **10.00**, còn **70.00**.

### Bài 10 — Chuyển sang minor units

Cho `grandTotal = NumberDecimal("56.03")`, hãy dùng `$multiply`, `$round`, `$toLong` để có **5603** minor units. Nêu điều kiện về scale currency, range và chính sách rounding.

---

## 27. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Mọi BSON number đều giống nhau.” | Int32, Int64, Double và Decimal128 có phạm vi, precision, conversion khác nhau. |
| “Double lưu chính xác mọi số thập phân.” | Nhiều giá trị như 0.1 không biểu diễn chính xác dưới dạng nhị phân. |
| “Decimal128 chính xác vô hạn.” | Decimal128 có 34 chữ số có nghĩa và phạm vi hữu hạn. |
| “Đổi Double sang Decimal128 ở cuối sẽ sửa mọi sai số cũ.” | Không tự khôi phục decimal đúng ý định nếu dữ liệu đã mất precision/đã tính sai từ trước. |
| “`$round` là quy tắc .5 luôn tăng.” | MongoDB dùng half-even khi tie. |
| “`$round` và `$trunc` tương đương.” | Một cái làm tròn gần nhất, một cái cắt theo hướng về 0. |
| “`$trunc` với số âm giống `$floor`.” | Với -1.9, trunc=-1 nhưng floor=-2. |
| “`$ceil` và `$floor` chỉ khác `$round` ở tên.” | Chúng làm tròn theo hướng dương/âm vô cực. |
| “Place = -2 là giữ hai số sau dấu thập phân.” | Place âm làm tròn/cắt bên trái dấu thập phân, ví dụ hàng trăm. |
| “Làm tròn từng dòng hay sau khi cộng đều giống nhau.” | Có thể lệch do phép làm tròn không phân phối qua phép cộng. |
| “MongoDB tự biết luật làm tròn hóa đơn.” | Phải định nghĩa từ domain, kể cả thuế và currency. |
| “`$divide` cho 0 thì tự trả null.” | Chia cho 0 có thể gây lỗi; phải kiểm soát mẫu số. |
| “`$sum` luôn hành xử giống `$add`.” | `$sum` có quy tắc accumulator/expression và xử lý dữ liệu phi số riêng. |
| “`$sum` trên array trong `$group` sẽ tự cộng từng phần tử.” | Accumulator `$group` không tự traverse array như expression một toán hạng trong `$project`. |
| “`$avg` tự chuyển string số thành numeric.” | Cần validation/conversion có chủ đích. |
| “Mọi phép chia hai integer trả integer.” | `$divide` có thể trả Double; Decimal128 operand giúp kết quả decimal. |
| “Một số hiển thị 20.00 nghĩa là BSON lưu fixed scale 2.” | Presentation formatting và precision/scale của số cần được xử lý tách biệt. |
| “JSON number giữ nguyên Decimal128 ở mọi client.” | Nhiều client dùng binary floating point; cần API contract. |
| “`$expr` tính trên field luôn tận dụng index như range trực tiếp.” | Biểu thức động có thể hạn chế cách index được sử dụng. |
| “Tính trong aggregation không tốn CPU.” | Biểu thức, `$map`, `$group` và conversion có chi phí; phải đo. |

## 28. Quy trình thiết kế phép tính số an toàn

Một nhóm phát triển nên làm rõ lần lượt:

1. **Đơn vị dữ liệu:** USD, VND, cent, phần trăm, tỷ lệ 0–1, milliseconds hay seconds?
2. **Kiểu lưu trữ:** Int32/Int64, Double, Decimal128; kiểu nào được phép ở từng field?
3. **Nguồn nhập:** chuỗi decimal, BigDecimal, integer minor units; có bị đổi sang Double ở client không?
4. **Miền giá trị:** giá trị tối thiểu/tối đa, có được âm, null, zero hoặc missing không?
5. **Công thức nghiệp vụ:** thứ tự trừ chiết khấu, áp thuế, phí và tỷ giá?
6. **Chính sách rounding:** half-even, half-up hay quy tắc khác; place nào và làm tròn ở bước nào?
7. **Điểm tổng hợp:** làm tròn theo dòng, theo thuế suất, theo hóa đơn hay chỉ khi hiển thị?
8. **Bất biến dữ liệu:** tổng hóa đơn có bằng các dòng sau khi áp policy không?
9. **Contract API:** decimal string, BSON Extended JSON hay integer minor units?
10. **Hiệu năng:** `$match` có giảm tập dữ liệu trước khi tính không, có cần computed field/index?
11. **Đối soát:** Java BigDecimal, aggregation và báo cáo có cùng kết quả cho các ca biên không?
12. **Theo dõi:** ghi mã lỗi/định danh bài toán thay vì lặng lẽ nuốt conversion error.

Ví dụ một quy trình tính tiền rõ ràng:

```text
Input decimal string / integer minor units
               |
               v
       Validate schema + currency
               |
               v
     Chuyển sang kiểu numeric chuẩn
               |
               v
     Tính giá trị raw có precision đủ
               |
               v
     Áp dụng rounding theo policy
               |
               v
     Kiểm tra invariant và giới hạn
               |
               v
      Lưu/đối soát BSON Decimal128
               |
               v
    Trả API theo contract thống nhất
```

---

## 29. Tài liệu MongoDB chính thức

- [Aggregation Expressions](https://www.mongodb.com/docs/manual/reference/operator/aggregation/): danh sách biểu thức aggregation.
- [`$add`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/add/), [`$subtract`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/subtract/), [`$multiply`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/multiply/), [`$divide`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/divide/): phép số học cơ bản.
- [`$mod`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/mod/), [`$abs`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/abs/): số dư và trị tuyệt đối.
- [`$round`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/round/) và [`$trunc`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/trunc/): làm tròn và cắt phần thập phân.
- [`$ceil`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/ceil/) và [`$floor`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/floor/): làm tròn theo hướng.
- [`$sum`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/) và [`$avg`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/avg/): tổng và trung bình.
- [`$toDecimal`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDecimal/) và [`$convert`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/): chuyển kiểu có kiểm soát.
- [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): Int32, Int64, Double, Decimal128 và các kiểu BSON.
- [Decimal128 trong MongoDB](https://www.mongodb.com/docs/manual/tutorial/model-monetary-data/): các cân nhắc khi mô hình hóa dữ liệu tiền.
- [Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/): thao tác BSON và aggregation trong Java.

Chi tiết kết quả, kiểm tra miền giá trị và kiểu dữ liệu có thể khác theo phiên bản MongoDB/driver. Khi triển khai thật, đối chiếu tài liệu với phiên bản đang vận hành và kiểm tra các trường hợp biên theo yêu cầu nghiệp vụ.

## 30. Kết luận

MongoDB có bộ biểu thức số học mạnh để tính trực tiếp trên document và nhóm kết quả. `$add`, `$subtract`, `$multiply`, `$divide`, `$mod`, `$sum` và `$avg` giải quyết nhiều bài toán phổ biến; `$round`, `$trunc`, `$ceil`, `$floor` diễn đạt **những quy tắc làm tròn khác nhau**.

Khi xử lý tiền, **Decimal128 giúp biểu diễn các giá trị decimal chính xác trong giới hạn 34 chữ số có nghĩa**, tránh nhiều sai lệch vốn có của binary floating-point. Nhưng Decimal128 không có precision vô hạn và không tự quyết định policy làm tròn. Hãy thống nhất kiểu từ đầu vào tới driver, kiểm soát null/zero/overflow, quyết định thời điểm rounding và duy trì cùng một contract giữa MongoDB, Java và API.

**Kết quả số học đúng = công thức đúng + kiểu số đúng + đơn vị đúng + quy tắc rounding đúng + dữ liệu đầu vào hợp lệ.**
