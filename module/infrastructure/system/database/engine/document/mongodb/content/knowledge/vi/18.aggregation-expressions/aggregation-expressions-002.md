# Điều kiện $cond, $switch, $ifNull và xử lý dữ liệu thiếu trong MongoDB Aggregation

## Mục tiêu bài học

Trong **MongoDB Aggregation Framework**, biểu thức điều kiện giúp biến đổi document dựa trên dữ liệu đang có, thay vì phải đọc document rồi viết các nhánh `if/else` hoàn toàn ở phía ứng dụng. Ba biểu thức đặc biệt quan trọng là:

- **`$cond`**: chọn **một trong hai** kết quả theo điều kiện đúng/sai.
- **`$switch`**: chọn **nhánh đầu tiên phù hợp** trong một tập nhiều điều kiện.
- **`$ifNull`**: lấy giá trị thay thế khi một biểu thức trả về `null`, **missing** hoặc giá trị undefined được coi tương đương null.

Một bài toán thường gặp: document đơn hàng có trường `discount`, nhưng các bản ghi cũ có thể thiếu field, bản ghi khác có `discount: null`, hoặc có giá trị hợp lệ `discount: 0`. Nếu thiết kế không đúng, pipeline có thể coi 0 là thiếu, tính sai thành tiền hoặc làm mất khả năng phân biệt trạng thái của dữ liệu.

Sau bài học, người học có thể:

1. Viết hai cú pháp `$cond` (object và array) và chọn nhánh theo biểu thức boolean.
2. Viết `$switch` với nhiều `branches`, `case`, `then` và `default`, hiểu thứ tự ưu tiên.
3. Dùng `$ifNull` cho fallback hai đối số và fallback nhiều nguồn theo phiên bản hỗ trợ.
4. Phân biệt **field thiếu**, **BSON null**, **false**, **0**, **chuỗi rỗng** và **mảng rỗng**.
5. Kết hợp `$type`, `$convert`, `$isNumber`, `$isArray`, `$$REMOVE` để xử lý dữ liệu lệch hoặc thiếu.
6. Áp dụng biểu thức trong `$project`, `$addFields`/`$set`, `$group`, `$match` với `$expr`, và update bằng aggregation pipeline.
7. Thiết kế pipeline rõ ràng, có kiểu dữ liệu đầu ra nhất quán, giới hạn chi phí tính toán và hiểu ảnh hưởng đến khả năng dùng index.
8. Thực hành bằng mongosh, đọc kết quả và xây bộ test cho các trường hợp biên.

> **Quy tắc cốt lõi:** `$ifNull` xử lý **nullish**; `$cond` xử lý **đúng/sai**; `$switch` xử lý **nhiều nhánh có thứ tự**. Đây là ba cơ chế khác nhau, không thay thế nhau trong mọi tình huống.

---

## 1. Biểu thức trong aggregation khác thao tác đọc field trực tiếp như thế nào?

Một pipeline aggregation gồm nhiều stage. Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $project: {
      _id: 1,
      amount: 1,
      discount: 1,
      netAmount: {
        $subtract: [
          "$amount",
          { $ifNull: ["$discount", 0] }
        ]
      }
    }
  }
]);
~~~

Trong `$project`:

- `"_id": 1`, `"amount": 1`, `"discount": 1` là cách yêu cầu giữ các field.
- `"$amount"` là **field path expression**, nghĩa là lấy giá trị của field amount tại document hiện tại.
- `{ $ifNull: ["$discount", 0] }` là **aggregation expression**, chọn discount hiện có hoặc 0 khi discount nullish.
- `$subtract` thực hiện phép trừ trên các giá trị biểu thức.

Hai chuỗi này khác nhau về ý nghĩa:

~~~javascript
// Truy cập field amount:
"$amount"

// Chuỗi literal có nội dung "$amount":
{ $literal: "$amount" }
~~~

Aggregation hiểu string bắt đầu bằng `$` ở vị trí biểu thức là một tham chiếu field/biến, không phải chuỗi text thông thường. Khi muốn chuỗi literal thực sự bắt đầu bằng dấu `$`, sử dụng `$literal`.

### 1.1. Ba toán tử điều kiện làm ba công việc khác nhau

| Nhu cầu | Công cụ | Ví dụ |
|---|---|---|
| Kiểm tra một điều kiện rồi chọn hai kết quả | `$cond` | Amount lớn thì "HIGH", ngược lại "NORMAL" |
| Phân loại theo nhiều trạng thái | `$switch` | NEW, PAID, CANCELLED, còn lại UNKNOWN |
| Có giá trị ưu tiên, không thì dùng giá trị dự phòng | `$ifNull` | nickname → fullName → "Khách hàng" |
| Phân biệt field thiếu và field có null | `$type` kết hợp điều kiện | "missing" khác "null" |
| Bỏ field đầu ra theo điều kiện | `$$REMOVE` kết hợp `$cond` | Không xuất field warning khi không có cảnh báo |
| Đổi dữ liệu string-number dễ lỗi sang number | `$convert` | "1200" → 1200, lỗi → null/fallback |

### 1.2. `$cond` không phải update operator

`$cond`, `$switch` và `$ifNull` thường được sử dụng như **biểu thức** bên trong những stage như `$project`, `$addFields` và `$set` của aggregation. Chúng không phải các lệnh ghi độc lập vào database.

Pipeline đọc:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      label: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "Đã thanh toán",
          "Chưa thanh toán"
        ]
      }
    }
  }
]);
~~~

không tự lưu `label` trở lại các document. Muốn ghi kết quả xuống database, cần một thao tác update có aggregation pipeline được hỗ trợ hoặc thiết kế ghi khác có chủ đích.

---

## 2. Chuẩn bị dữ liệu thực hành

Các ví dụ dùng mongosh, database **`aggregation_condition_lab`**. Chỉ chạy trên database thử nghiệm. Nếu đã có dữ liệu từ lần học trước, dùng collection khác hoặc làm sạch theo quy trình lab để tránh trùng `_id`.

~~~javascript
use aggregation_condition_lab

db.orders.insertMany([
  {
    _id: "ORD-101",
    status: "PAID",
    amount: 1200000,
    discount: 100000,
    shippingFee: 30000,
    customer: {
      nickname: "An",
      fullName: "Nguyễn Văn An",
      email: "an@example.test"
    },
    items: [
      { sku: "A-01", quantity: 2 },
      { sku: "B-01", quantity: 1 }
    ]
  },
  {
    _id: "ORD-102",
    status: "PAID",
    amount: 850000,
    discount: 0,
    shippingFee: null,
    estimatedShippingFee: 25000,
    customer: {
      nickname: "",
      fullName: "Trần Bình",
      email: null
    }
  },
  {
    _id: "ORD-103",
    status: "NEW",
    amount: 500000,
    customer: {
      fullName: "Lê Chi"
    }
  },
  {
    _id: "ORD-104",
    status: "CANCELLED",
    amount: 200000,
    discount: null,
    shippingFee: 0,
    customer: {
      nickname: "Dung",
      fullName: "Phạm Dung"
    }
  },
  {
    _id: "ORD-105",
    status: "PAID",
    amount: "900000",
    discount: "50000",
    shippingFee: 15000,
    customer: {
      fullName: "Hà"
    }
  },
  {
    _id: "ORD-106",
    status: "PAID",
    amount: null,
    discount: null,
    customer: null
  },
  {
    _id: "ORD-107",
    amount: 0,
    discount: false,
    customer: {
      nickname: null,
      fullName: "Khánh"
    },
    items: []
  },
  {
    _id: "ORD-108",
    status: "REFUNDED",
    amount: 300000,
    discount: 10000,
    shippingFee: 0,
    customer: {
      fullName: "Lan",
      email: "lan@example.test"
    }
  },
  {
    _id: "ORD-109",
    status: "NEW",
    customer: {
      fullName: "Minh"
    }
  }
]);
~~~

Kiểm tra:

~~~javascript
db.orders.countDocuments({});
db.orders.find({}, {
  _id: 1,
  status: 1,
  amount: 1,
  discount: 1,
  shippingFee: 1
}).sort({ _id: 1 });
~~~

Nếu dữ liệu được tạo đúng một lần, số document là **9**.

### 2.1. Các trường hợp biên được tạo cố ý

| Document | `discount` | `amount` | Đặc điểm |
|---|---|---|---|
| ORD-101 | 100000 | 1200000 | Dữ liệu số bình thường |
| ORD-102 | **0** | 850000 | 0 là giá trị hợp lệ, không phải null |
| ORD-103 | **Missing** | 500000 | Field discount không tồn tại |
| ORD-104 | **null** | 200000 | Field tồn tại nhưng null |
| ORD-105 | **"50000"** | **"900000"** | Dữ liệu số lưu sai kiểu string |
| ORD-106 | **null** | **null** | Dữ liệu nullish |
| ORD-107 | **false** | **0** | Discount boolean sai kiểu, amount 0 hợp lệ |
| ORD-108 | 10000 | 300000 | Status khác các nhánh thông dụng |
| ORD-109 | **Missing** | **Missing** | Thiếu nhiều field |

Chính sự đa dạng này giúp nhìn rõ khi nào toán tử điều kiện hoạt động đúng và khi nào cần kiểm tra kiểu dữ liệu.

---

## 3. Hiểu các trạng thái Missing, null và những giá trị dễ nhầm

### 3.1. Missing khác null

Hai document:

~~~javascript
{ _id: "X", discount: null }
{ _id: "Y" }
~~~

không có cùng cấu trúc.

- X **có field discount** và giá trị là BSON null.
- Y **không có field discount**.

Để kiểm tra sự tồn tại ở mức truy vấn:

~~~javascript
db.orders.find({
  discount: { $exists: true }
});

db.orders.find({
  discount: { $exists: false }
});
~~~

Ở đây `$exists` là **query operator**, dùng trong filter `find()` hoặc `$match` thông thường, không phải aggregation expression dùng trực tiếp làm điều kiện `$cond`.

Để nhận diện trong một biểu thức aggregation:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discountType: {
        $type: "$discount"
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Kết quả có thể cho thấy:

~~~text
ORD-101 -> int
ORD-102 -> int
ORD-103 -> missing
ORD-104 -> null
ORD-105 -> string
ORD-106 -> null
ORD-107 -> bool
ORD-108 -> int
ORD-109 -> missing
~~~

`$type` dạng aggregation expression có thể trả chuỗi `"missing"` nếu tham chiếu field không tồn tại. Với dữ liệu `NumberInt`/`NumberLong`/`Decimal128`, tên kiểu có thể khác nhau; trong lab trên, number viết trực tiếp trong mongosh thường được lưu theo dạng số phù hợp BSON nên không nên biến bảng minh họa thành giả định cố định về mọi kiểu số.

### 3.2. Một giá trị nullish không giống một giá trị falsy

Trong nhiều ngôn ngữ lập trình có các khái niệm như nullish và truthy/falsy. MongoDB cũng có quy tắc đánh giá biểu thức dưới dạng boolean.

Một vài giá trị quan trọng:

| Giá trị | Nullish đối với `$ifNull`? | Boolean trong điều kiện `$cond` |
|---|---|---|
| Missing field | **Có** | Falsy trong những ngữ cảnh được đánh giá như undefined/nullish |
| BSON `null` | **Có** | False |
| Undefined (legacy) | **Có** | False |
| `false` | **Không** | False |
| `0` | **Không** | False |
| `""` | **Không** | Thường được coi là truthy theo quy tắc boolean của aggregation, không được giả định giống JavaScript |
| `[]` | **Không** | Truthy |
| `{}` | **Không** | Truthy |
| Số khác 0 | **Không** | True |
| Chuỗi không rỗng | **Không** | True |

**Điểm đặc biệt:** `$ifNull` không phải "giá trị falsy thì dùng mặc định". Nó chỉ xét các trường hợp được coi tương đương null. Trong dữ liệu thanh toán, discount **0** phải được giữ nguyên, không được coi là missing.

### 3.3. Query equality null có thể khớp missing

~~~javascript
db.orders.find({
  discount: null
});
~~~

Trong MongoDB, query equality đối với `null` có thể khớp cả document có `discount: null` **và document thiếu `discount`**.

Nếu chỉ muốn field có giá trị BSON null:

~~~javascript
db.orders.find({
  discount: { $type: "null" }
});
~~~

Nếu chỉ muốn field bị thiếu:

~~~javascript
db.orders.find({
  discount: { $exists: false }
});
~~~

Ở mức aggregation expression, dùng `$type` để xử lý riêng từng trạng thái thay vì tự suy đoán qua `$eq` với null.

---

## 4. `$cond`: chọn một trong hai nhánh

### 4.1. Hai dạng cú pháp

MongoDB hỗ trợ dạng object:

~~~javascript
{
  $cond: {
    if: <boolean-expression>,
    then: <true-case-expression>,
    else: <false-case-expression>
  }
}
~~~

và dạng array:

~~~javascript
{
  $cond: [
    <boolean-expression>,
    <true-case-expression>,
    <false-case-expression>
  ]
}
~~~

Trong mã thực tế, thay các placeholder bằng biểu thức hoặc giá trị cụ thể. **Cả ba thành phần đều cần có**; không bỏ `else` chỉ vì nghĩ MongoDB sẽ tự dùng null.

Ví dụ cùng ý nghĩa:

~~~javascript
// Dạng object
{
  $cond: {
    if: { $gte: ["$amount", 1000000] },
    then: "HIGH_VALUE",
    else: "NORMAL"
  }
}

// Dạng array
{
  $cond: [
    { $gte: ["$amount", 1000000] },
    "HIGH_VALUE",
    "NORMAL"
  ]
}
~~~

Nên dùng dạng object khi biểu thức dài vì tên `if`, `then`, `else` giúp người đọc không nhầm vị trí. Dạng array phù hợp khi điều kiện và giá trị ngắn.

### 4.2. Một pipeline thực hành

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: { $in: ["ORD-101", "ORD-102"] }
    }
  },
  {
    $project: {
      _id: 1,
      amount: 1,
      amountLevel: {
        $cond: {
          if: {
            $gte: ["$amount", 1000000]
          },
          then: "HIGH_VALUE",
          else: "NORMAL"
        }
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Với hai document này có amount dạng số:

| `_id` | Amount | Amount level |
|---|---:|---|
| ORD-101 | 1.200.000 | HIGH_VALUE |
| ORD-102 | 850.000 | NORMAL |

**Không mở rộng ví dụ này sang mọi document mà chưa kiểm tra kiểu amount.** ORD-105 lưu amount dưới dạng string và ORD-106 có amount null; phép so sánh có thể dùng thứ tự so sánh BSON thay vì ý nghĩa số học nghiệp vụ.

### 4.3. Kết hợp `$and`, `$or`

Yêu cầu: chỉ cho phép giảm phí vận chuyển nếu đơn PAID và tổng tiền đủ lớn.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: { $in: ["ORD-101", "ORD-102"] }
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      amount: 1,
      shippingDiscountEligible: {
        $cond: {
          if: {
            $and: [
              { $eq: ["$status", "PAID"] },
              { $gte: ["$amount", 1000000] }
            ]
          },
          then: true,
          else: false
        }
      }
    }
  }
]);
~~~

Kết quả:

- ORD-101: PAID và amount 1.200.000 → true.
- ORD-102: PAID nhưng amount 850.000 → false.

Với dữ liệu có thể sai kiểu, nên chuẩn hóa/kiểm tra amount trước khi so sánh. Không dựa vào `$and` như một cơ chế short-circuit được bảo đảm để chặn mọi phép toán không hợp lệ; hãy thiết kế biểu thức và type conversion có kiểm soát.

### 4.4. Không dùng trường làm boolean một cách mơ hồ

Nếu viết:

~~~javascript
{
  $cond: [
    "$discount",
    "HAS_DISCOUNT",
    "NO_DISCOUNT"
  ]
}
~~~

thì `discount: 0` và `discount: null` đều dẫn tới nhánh false, nhưng ý nghĩa nghiệp vụ khác nhau:

- 0: có mức giảm hợp lệ bằng 0.
- null: giá trị chưa xác định.
- missing: field chưa tồn tại.
- string không rỗng: có thể được coi true dù không phải số.

Một điều kiện rõ hơn là:

~~~javascript
{
  $cond: {
    if: {
      $and: [
        { $isNumber: "$discount" },
        { $gt: ["$discount", 0] }
      ]
    },
    then: "POSITIVE_DISCOUNT",
    else: "NO_POSITIVE_DISCOUNT"
  }
}
~~~

Tuy nhiên, `"NO_POSITIVE_DISCOUNT"` đang gom cả 0, null, missing và sai kiểu vào một nhóm. Nếu ứng dụng cần tách các nhóm này, dùng `$switch` hoặc thêm một trường báo lỗi dữ liệu.

### 4.5. Nested `$cond`

Một phân loại có ba mức có thể viết nhiều `$cond` lồng nhau:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: { $in: ["ORD-101", "ORD-102", "ORD-103"] }
    }
  },
  {
    $project: {
      amount: 1,
      amountBand: {
        $cond: {
          if: { $gte: ["$amount", 1000000] },
          then: "HIGH",
          else: {
            $cond: {
              if: { $gte: ["$amount", 500000] },
              then: "MEDIUM",
              else: "LOW"
            }
          }
        }
      }
    }
  }
]);
~~~

Với ba document có amount numeric, kết quả là HIGH, MEDIUM, MEDIUM. Nhưng khi số nhánh tăng, nested `$cond` khó đọc và dễ sai thứ tự. `$switch` thường rõ ràng hơn.

---

## 5. `$switch`: chọn nhánh đầu tiên khớp

### 5.1. Cú pháp

~~~javascript
{
  $switch: {
    branches: [
      {
        case: <condition-expression-1>,
        then: <result-expression-1>
      },
      {
        case: <condition-expression-2>,
        then: <result-expression-2>
      }
    ],
    default: <fallback-expression>
  }
}
~~~

Quy tắc:

1. MongoDB xét `branches` theo **thứ tự khai báo**.
2. Nhánh đầu tiên có `case` đánh giá true được chọn.
3. Kết quả là biểu thức `then` của nhánh đó.
4. Nếu không nhánh nào đúng, `default` được sử dụng nếu có.
5. Nếu không có nhánh phù hợp **và không khai báo `default`**, aggregation có thể báo lỗi thay vì tự trả null.

### 5.2. Phân loại trạng thái đơn hàng

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      statusLabel: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$status", "NEW"] },
              then: "Chờ xử lý"
            },
            {
              case: { $eq: ["$status", "PAID"] },
              then: "Đã thanh toán"
            },
            {
              case: { $eq: ["$status", "CANCELLED"] },
              then: "Đã hủy"
            },
            {
              case: { $eq: ["$status", "REFUNDED"] },
              then: "Đã hoàn tiền"
            }
          ],
          default: "Không xác định"
        }
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Với dữ liệu lab:

| Status | Label |
|---|---|
| NEW | Chờ xử lý |
| PAID | Đã thanh toán |
| CANCELLED | Đã hủy |
| REFUNDED | Đã hoàn tiền |
| Missing hoặc trạng thái không hỗ trợ | Không xác định |

Nhờ `default`, các document như ORD-107 thiếu status vẫn có giá trị đầu ra phù hợp thay vì làm pipeline báo lỗi vì không có nhánh nào khớp.

### 5.3. Thứ tự nhánh là một phần của logic

Ví dụ muốn phân loại đơn dựa trên amount số:

~~~javascript
{
  $switch: {
    branches: [
      {
        case: { $gte: ["$amount", 500000] },
        then: "MEDIUM_OR_MORE"
      },
      {
        case: { $gte: ["$amount", 1000000] },
        then: "HIGH"
      }
    ],
    default: "LOW"
  }
}
~~~

**Vấn đề:** Mọi amount ≥ 1.000.000 cũng ≥ 500.000. Nhánh đầu đã khớp nên nhánh HIGH không có cơ hội được chọn cho những amount đó.

Đúng hơn:

~~~javascript
{
  $switch: {
    branches: [
      {
        case: { $gte: ["$amount", 1000000] },
        then: "HIGH"
      },
      {
        case: { $gte: ["$amount", 500000] },
        then: "MEDIUM"
      }
    ],
    default: "LOW"
  }
}
~~~

Với dữ liệu sai kiểu, cần kiểm tra/chuẩn hóa amount; ví dụ trên chỉ giải thích thứ tự điều kiện cho các giá trị số hợp lệ.

### 5.4. Nhiều điều kiện có thể cùng đúng

`$switch` **không** tự tìm nhánh “cụ thể nhất”. Nó chọn **nhánh đúng đầu tiên**.

Ví dụ:

~~~javascript
{
  $switch: {
    branches: [
      {
        case: {
          $and: [
            { $eq: ["$status", "PAID"] },
            { $gte: ["$amount", 1000000] }
          ]
        },
        then: "PAID_HIGH_VALUE"
      },
      {
        case: { $eq: ["$status", "PAID"] },
        then: "PAID_OTHER"
      }
    ],
    default: "OTHER"
  }
}
~~~

Cả hai case có thể đúng cho đơn PAID giá trị cao. Nhánh cụ thể hơn phải được đặt trước.

### 5.5. Không bỏ `default` nếu dữ liệu có thể phát sinh trạng thái mới

Giả sử hiện tại chỉ có NEW/PAID, nhóm phát triển bỏ default. Về sau có trạng thái REFUNDED, pipeline có thể báo lỗi khi gặp document không nhánh nào đúng.

Một `default` thích hợp giúp forward compatibility:

~~~javascript
default: "UNKNOWN_STATUS"
~~~

Tuy nhiên, cũng không nên dùng default để **che giấu** lỗi dữ liệu quan trọng. Nếu nghiệp vụ bắt buộc xử lý mọi status đã công bố, vẫn cần log/monitor số lượng UNKNOWN_STATUS để phát hiện schema drift.

---

## 6. `$ifNull`: lấy giá trị fallback khi nullish

### 6.1. Cú pháp cơ bản

~~~javascript
{
  $ifNull: [
    <input-expression>,
    <replacement-expression>
  ]
}
~~~

Nếu input có giá trị **khác nullish**, `$ifNull` trả chính giá trị đó. Nếu input là null, missing hoặc undefined được coi tương đương null, nó trả replacement.

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discount: 1,
      effectiveDiscount: {
        $ifNull: [
          "$discount",
          0
        ]
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Kết quả đáng chú ý:

| Document | Giá trị gốc | `effectiveDiscount` |
|---|---|---|
| ORD-101 | 100000 | 100000 |
| ORD-102 | 0 | **0**, không chuyển fallback |
| ORD-103 | Missing | 0 |
| ORD-104 | null | 0 |
| ORD-105 | "50000" | **"50000"**, vẫn là string |
| ORD-106 | null | 0 |
| ORD-107 | false | **false**, vẫn là bool |
| ORD-108 | 10000 | 10000 |
| ORD-109 | Missing | 0 |

**Bài học:** `$ifNull` giải quyết **thiếu/null**, không tự giải quyết **sai kiểu**. Nếu dữ liệu có discount là string hoặc false, lấy fallback 0 không khiến chúng biến thành số.

### 6.2. Fallback không nhất thiết là literal

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      shippingFee: 1,
      estimatedShippingFee: 1,
      chargeableShippingFee: {
        $ifNull: [
          "$shippingFee",
          "$estimatedShippingFee"
        ]
      }
    }
  }
]);
~~~

Nếu `shippingFee` nullish, lấy `estimatedShippingFee`. Nếu cả hai nullish, kết quả cũng có thể là nullish, và tùy stage/output semantics có thể không tạo một giá trị hữu ích. Nên cung cấp fallback cuối rõ ràng khi nghiệp vụ cần giá trị luôn tồn tại.

### 6.3. `$ifNull` với nhiều nguồn — MongoDB 5.0+

Từ MongoDB **5.0**, `$ifNull` hỗ trợ nhiều input expressions theo thứ tự ưu tiên, với **replacement ở cuối**.

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      chargeableShippingFee: {
        $ifNull: [
          "$shippingFee",
          "$estimatedShippingFee",
          0
        ]
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Ý nghĩa:

1. Nếu shippingFee không nullish → dùng shippingFee.
2. Nếu shippingFee nullish và estimatedShippingFee không nullish → dùng estimatedShippingFee.
3. Nếu cả hai nullish → dùng 0.

ORD-102 có shippingFee null, estimatedShippingFee 25.000 nên kết quả 25.000. ORD-104 có shippingFee **0** nên kết quả **0**, không chuyển sang fallback khác.

Nếu phải hỗ trợ MongoDB trước 5.0, dùng nested `$ifNull` hai đối số thay vì cú pháp nhiều input:

~~~javascript
{
  $ifNull: [
    "$shippingFee",
    {
      $ifNull: [
        "$estimatedShippingFee",
        0
      ]
    }
  ]
}
~~~

Với code dùng nhiều input, hãy ghi rõ version server tối thiểu được hỗ trợ.

### 6.4. Fallback cho tên hiển thị

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      displayName: {
        $ifNull: [
          "$customer.nickname",
          "$customer.fullName",
          "Khách hàng"
        ]
      }
    }
  }
]);
~~~

Điểm đáng chú ý: ORD-102 có `nickname: ""`. Chuỗi rỗng **không nullish**, vì vậy `$ifNull` giữ nguyên chuỗi rỗng, **không** tự chuyển sang `"Trần Bình"`. Nếu ứng dụng muốn chuỗi rỗng được xem như thiếu, phải bổ sung kiểm tra rõ ràng.

### 6.5. Xử lý chuỗi rỗng

Với dữ liệu nickname có thể `""`:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      displayName: {
        $let: {
          vars: {
            nickname: {
              $ifNull: ["$customer.nickname", ""]
            }
          },
          in: {
            $cond: {
              if: {
                $ne: ["$$nickname", ""]
              },
              then: "$$nickname",
              else: {
                $ifNull: [
                  "$customer.fullName",
                  "Khách hàng"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

`$let` đặt biến tạm để tránh lặp logic. Cách trên xem null/missing/chuỗi rỗng là không có nickname, nhưng chưa xử lý nickname chứa toàn khoảng trắng hoặc sai kiểu như array. Nếu cần chuẩn hóa khoảng trắng, có thể kết hợp `$trim` với kiểm tra `$type` trước khi xử lý.

---

## 7. Khi nào dùng toán tử nào?

| Bài toán | Nên ưu tiên | Lý do |
|---|---|---|
| Có một điều kiện đúng/sai | `$cond` | Hai nhánh rõ ràng |
| Có nhiều trạng thái hoặc nhiều khoảng | `$switch` | Dễ đọc hơn nested `$cond` |
| Dùng giá trị mặc định khi field thiếu/null | `$ifNull` | Diễn đạt trực tiếp fallback nullish |
| Dùng thứ tự ưu tiên nhiều nguồn dữ liệu | `$ifNull` nhiều input | Trả nguồn không nullish đầu tiên |
| Phải phân biệt missing và explicit null | `$type` + `$cond`/`$switch` | `$ifNull` gộp hai trạng thái |
| 0 và false là giá trị hợp lệ | `$ifNull` nếu chỉ muốn xử lý nullish | Không gộp 0/false vào missing |
| Chuỗi rỗng cũng phải thay bằng fallback | `$cond` hoặc `$switch` với điều kiện rỗng | `$ifNull` không thay chuỗi rỗng |
| Cần kiểm tra number trước khi tính toán | `$isNumber`/`$convert` + biểu thức điều kiện | Tránh phụ thuộc so sánh BSON trên dữ liệu sai kiểu |
| Cần bỏ field đầu ra khi không có giá trị | `$$REMOVE` + điều kiện | Trả cấu trúc document phù hợp |

### 7.1. Ví dụ tương đương giữa `$cond` và `$switch`

Một trường hợp hai nhánh:

~~~javascript
{
  $cond: [
    { $eq: ["$status", "PAID"] },
    "Đã thanh toán",
    "Khác"
  ]
}
~~~

Có thể dùng `$switch`:

~~~javascript
{
  $switch: {
    branches: [
      {
        case: { $eq: ["$status", "PAID"] },
        then: "Đã thanh toán"
      }
    ],
    default: "Khác"
  }
}
~~~

Cả hai biểu diễn logic tương tự, nhưng `$cond` ngắn và rõ hơn khi chỉ có một điều kiện. `$switch` phù hợp khi có nhiều case có thứ tự.

### 7.2. `$ifNull` không phải thay thế cho điều kiện true/false

Ví dụ:

~~~javascript
{
  $ifNull: [
    "$isVerified",
    false
  ]
}
~~~

Nếu isVerified là false, kết quả vẫn là false. Đúng vì cần fallback **chỉ khi nullish**.

Trong khi đó:

~~~javascript
{
  $cond: [
    "$isVerified",
    "VERIFIED",
    "NOT_VERIFIED"
  ]
}
~~~

biến điều kiện thành nhãn. Hai biểu thức này **không tạo cùng loại output**.

---

## 8. Phân biệt field thiếu với field có null bằng `$type`

Trong nhiều nghiệp vụ, missing và null có ý nghĩa khác:

- Missing: bản ghi cũ chưa được migration.
- Null: field được định nghĩa nhưng người dùng chưa cung cấp giá trị.
- Zero: giá trị có nghĩa, không phải “chưa có”.
- Sai kiểu: dữ liệu lệch schema cần sửa.

### 8.1. Dùng `$switch` để phân loại

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discountState: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [
                  { $type: "$discount" },
                  "missing"
                ]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: [
                  { $type: "$discount" },
                  "null"
                ]
              },
              then: "EXPLICIT_NULL"
            },
            {
              case: {
                $isNumber: "$discount"
              },
              then: "NUMERIC"
            }
          ],
          default: "INVALID_TYPE"
        }
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Dự kiến:

| Document | `discountState` |
|---|---|
| ORD-101 | NUMERIC |
| ORD-102 | NUMERIC |
| ORD-103 | MISSING |
| ORD-104 | EXPLICIT_NULL |
| ORD-105 | INVALID_TYPE |
| ORD-106 | EXPLICIT_NULL |
| ORD-107 | INVALID_TYPE |
| ORD-108 | NUMERIC |
| ORD-109 | MISSING |

Trong cách phân loại này, 0 vẫn là NUMERIC; false là INVALID_TYPE.

### 8.2. Dùng `$cond` khi chỉ cần kiểm tra missing

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      hasDiscountField: {
        $cond: {
          if: {
            $eq: [
              { $type: "$discount" },
              "missing"
            ]
          },
          then: false,
          else: true
        }
      }
    }
  }
]);
~~~

Với `discount: null`, `hasDiscountField` trả true, vì **field tồn tại**. Nếu chỉ dùng `$ifNull`, hai trạng thái missing và null đã bị gom lại, không thể dùng kết quả fallback để phân biệt một cách đáng tin.

### 8.3. Kiểm tra missing bên trong embedded document

Nếu field lồng nhau:

~~~javascript
{
  customer: {
    email: null
  }
}
~~~

thì:

~~~javascript
{ $type: "$customer.email" }
~~~

trả `"null"`.

Nếu email không có:

~~~javascript
{
  customer: {
    fullName: "An"
  }
}
~~~

thì `$type` trên `"$customer.email"` có thể trả `"missing"`.

Nếu `customer` tự nó null hoặc missing, truy cập `customer.email` cũng không cho một email hợp lệ. Khi cần phân biệt lỗi cấu trúc parent với thiếu child, có thể kiểm tra riêng:

~~~javascript
{
  parentType: { $type: "$customer" },
  emailType: { $type: "$customer.email" }
}
~~~

Không dùng một nhãn "MISSING_EMAIL" để che giấu trường hợp `customer` bị lưu sai kiểu nếu nghiệp vụ cần xử lý schema drift.

---

## 9. `$$REMOVE`: không xuất field khi điều kiện không thỏa

Một yêu cầu thường gặp: chỉ thêm field `warning` nếu đơn hàng có trạng thái cần lưu ý. Nếu không, field `warning` phải **vắng mặt**, không phải `null` hay chuỗi rỗng.

MongoDB có biến hệ thống **`$$REMOVE`** để loại một field trong những stage hỗ trợ tạo/định hình document như `$project` và `$addFields`.

### 9.1. Ví dụ với `$cond`

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      warning: {
        $cond: {
          if: {
            $eq: ["$status", "CANCELLED"]
          },
          then: "Đơn đã hủy",
          else: "$$REMOVE"
        }
      }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Với ORD-104, output có `warning: "Đơn đã hủy"`. Với các order khác, field warning **không có trong document đầu ra**.

So sánh:

~~~javascript
else: null
~~~

Cách này tạo field với giá trị null, khác với `$$REMOVE`.

### 9.2. Loại field theo trạng thái dữ liệu

Giả sử muốn chỉ xuất `customerEmail` nếu email tồn tại và không null:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      customerEmail: {
        $cond: {
          if: {
            $in: [
              { $type: "$customer.email" },
              ["missing", "null"]
            ]
          },
          then: "$$REMOVE",
          else: "$customer.email"
        }
      }
    }
  }
]);
~~~

Cách này loại missing/null, nhưng vẫn cho phép email sai kiểu như number hoặc array đi qua. Nếu yêu cầu chỉ xuất email string, dùng `$type` và nhánh rõ ràng:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      customerEmail: {
        $cond: {
          if: {
            $eq: [
              { $type: "$customer.email" },
              "string"
            ]
          },
          then: "$customer.email",
          else: "$$REMOVE"
        }
      }
    }
  }
]);
~~~

### 9.3. Không dùng `$$REMOVE` như cách sửa dữ liệu gốc khi chỉ chạy aggregate

Nếu dùng `aggregate()` thông thường, `$$REMOVE` chỉ định hình kết quả trả về. Nó **không xóa field khỏi collection**. Nếu cập nhật bằng aggregation pipeline, `$$REMOVE` trong `$set` stage có thể tác động đến document được lưu; cần phân biệt hoàn cảnh rõ ràng.

---

## 10. Kiểu BSON và phép so sánh: đừng dựa vào trật tự type khi cần số học

Một dữ liệu có:

~~~javascript
{ amount: 900000 }
~~~

khác với:

~~~javascript
{ amount: "900000" }
~~~

Trong aggregation, so sánh các kiểu BSON khác nhau theo quy tắc MongoDB có thể cho thứ tự không giống mong đợi số học. Ví dụ so sánh string với number không nhất thiết ép string thành number.

Nếu sử dụng:

~~~javascript
{
  $gte: ["$amount", 1000000]
}
~~~

mà amount là string, kết quả không nên được hiểu là "so sánh số tiền". Với số tiền có thể bị lưu sai kiểu, tốt hơn dùng `$convert`.

### 10.1. `$convert` với `onError` và `onNull`

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      amount: 1,
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
~~~

Ý nghĩa:

- `amount` là số hợp lệ → chuyển sang Decimal128 phù hợp.
- `amount` là string numeric như `"900000"` → có thể chuyển thành decimal.
- `amount` là string không thể chuyển như `"unknown"` → `onError: null` tránh làm pipeline lỗi toàn bộ ở bước conversion.
- `amount` missing hoặc null → `onNull: null`.
- `onError` và `onNull` ở đây đều cho ra null; có thể chọn sentinel khác nếu muốn phân biệt lý do.

Nếu không đặt `onError`, lỗi chuyển đổi kiểu có thể làm pipeline thất bại. `$ifNull` không thay thế xử lý `onError`, vì một string sai kiểu là **non-nullish**.

### 10.2. Chuẩn hóa trước rồi phân loại

Một pipeline hai stage:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      amountBand: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [
                  { $type: "$amountDecimal" },
                  "null"
                ]
              },
              then: "UNKNOWN_AMOUNT"
            },
            {
              case: {
                $gte: [
                  "$amountDecimal",
                  NumberDecimal("1000000")
                ]
              },
              then: "HIGH"
            },
            {
              case: {
                $gte: [
                  "$amountDecimal",
                  NumberDecimal("500000")
                ]
              },
              then: "MEDIUM"
            }
          ],
          default: "LOW"
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      amount: 1,
      amountDecimal: 1,
      amountBand: 1
    }
  }
]);
~~~

Stage đầu chuyển amount về một kiểu phù hợp. Stage sau đưa document thiếu/null/không convert được vào UNKNOWN_AMOUNT, và so sánh khoảng tiền trên Decimal128 hợp lệ.

**Lưu ý:** Nếu trong stage đầu `onError: null` và `onNull: null`, output không còn biết nguyên nhân cụ thể là missing hay parse error. Nếu cần audit, giữ thêm một field như `amountOriginalType` hoặc `amountConversionState` trước khi gộp.

### 10.3. Chọn kiểu tiền cẩn thận

Đối với tiền:

- Tránh trộn string, double và decimal tùy tiện.
- Có thể lưu integer minor units (ví dụ đồng hoặc xu) theo mô hình nghiệp vụ, hoặc Decimal128 nếu yêu cầu decimal precision.
- Chuẩn hóa input tại biên API.
- Dùng phép toán với kiểu tương thích.
- Quy định rounding, currency và giới hạn âm/số lớn theo nghiệp vụ.
- Không để một fallback `0` tùy tiện che giấu dữ liệu tiền không hợp lệ.

---

## 11. Kết hợp `$ifNull` với chuyển đổi số an toàn

Giả sử tính discount hiệu lực.

### 11.1. Chỉ fallback missing/null, không xử lý sai kiểu

~~~javascript
{
  effectiveDiscount: {
    $ifNull: [
      "$discount",
      0
    ]
  }
}
~~~

Cách này vẫn để string `"50000"` và bool `false` đi qua. Không phù hợp nếu bước tiếp theo trừ tiền với `$subtract`.

### 11.2. Chuyển đổi trước rồi fallback

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      discount: 1,
      effectiveDiscount: {
        $ifNull: [
          {
            $convert: {
              input: "$discount",
              to: "decimal",
              onError: null,
              onNull: null
            }
          },
          NumberDecimal("0")
        ]
      }
    }
  }
]);
~~~

Với các discount numeric hoặc string numeric, kết quả là Decimal128. Với missing/null hoặc dữ liệu không thể convert, kết quả 0 Decimal128.

**Đánh đổi:** Gộp parse error vào 0 có thể che giấu dữ liệu sai. Nếu khoản giảm giá là dữ liệu tài chính quan trọng, nên xuất thêm lỗi chất lượng dữ liệu hoặc chặn giao dịch thay vì âm thầm giảm về 0.

### 11.3. Giữ trạng thái lỗi riêng

Một hướng rõ hơn:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      discountOriginalType: {
        $type: "$discount"
      },
      discountDecimal: {
        $convert: {
          input: "$discount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $set: {
      discountState: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$discountOriginalType", "missing"]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: ["$discountOriginalType", "null"]
              },
              then: "EXPLICIT_NULL"
            },
            {
              case: {
                $eq: [
                  { $type: "$discountDecimal" },
                  "null"
                ]
              },
              then: "INVALID_OR_UNCONVERTIBLE"
            }
          ],
          default: "VALID"
        }
      },
      effectiveDiscount: {
        $ifNull: [
          "$discountDecimal",
          NumberDecimal("0")
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      discount: 1,
      discountOriginalType: 1,
      discountState: 1,
      effectiveDiscount: 1
    }
  }
]);
~~~

Với ORD-107 có discount boolean false, cần đặc biệt cẩn thận: `$convert` giữa BSON types có những quy tắc riêng, và boolean có thể có phép chuyển hợp lệ sang numeric. Nếu mục tiêu là **chỉ nhận các giá trị vốn là số hoặc chuỗi số được cho phép**, thêm kiểm tra **kiểu gốc** trước conversion, không chỉ xem conversion thành công.

Ví dụ quyết định nghiệp vụ:

~~~javascript
{
  $cond: {
    if: {
      $in: [
        { $type: "$discount" },
        ["int", "long", "double", "decimal", "string"]
      ]
    },
    then: {
      $convert: {
        input: "$discount",
        to: "decimal",
        onError: null,
        onNull: null
      }
    },
    else: null
  }
}
~~~

Ở đây bool bị từ chối theo thiết kế. Với string, vẫn cần chuyển và có thể phát sinh parse error; `onError: null` xử lý trường hợp đó. Lưu ý chính sách accept string numeric cũng cần được kiểm tra tại API khi ghi dữ liệu mới.

---

## 12. Một pipeline nghiệp vụ hoàn chỉnh: đơn hàng và cảnh báo dữ liệu

### 12.1. Yêu cầu

Với collection orders:

1. Gắn nhãn trạng thái theo business mapping.
2. Chuẩn hóa amount và discount về Decimal128 khi hợp lệ.
3. Tính net amount chỉ khi amount hợp lệ.
4. Discount thiếu/null được xem bằng 0 theo quy tắc demo.
5. Nếu amount không convert được, không xuất net amount.
6. Hiển thị tên khách theo nickname nếu có và không rỗng, nếu không dùng fullName hoặc placeholder.
7. Gắn cảnh báo nếu dữ liệu amount không hợp lệ.

### 12.2. Pipeline

~~~javascript
db.orders.aggregate([
  // Bước 1: Chuẩn hóa trường nguồn.
  {
    $set: {
      amountOriginalType: {
        $type: "$amount"
      },
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      discountDecimal: {
        $convert: {
          input: "$discount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      },
      customerNickname: {
        $ifNull: [
          "$customer.nickname",
          ""
        ]
      }
    }
  },

  // Bước 2: Tính toán dựa trên trường đã chuẩn hóa ở stage trước.
  {
    $set: {
      statusLabel: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$status", "NEW"] },
              then: "Chờ xử lý"
            },
            {
              case: { $eq: ["$status", "PAID"] },
              then: "Đã thanh toán"
            },
            {
              case: { $eq: ["$status", "CANCELLED"] },
              then: "Đã hủy"
            },
            {
              case: { $eq: ["$status", "REFUNDED"] },
              then: "Đã hoàn tiền"
            }
          ],
          default: "Trạng thái không xác định"
        }
      },
      displayName: {
        $cond: {
          if: {
            $and: [
              {
                $eq: [
                  { $type: "$customerNickname" },
                  "string"
                ]
              },
              { $ne: ["$customerNickname", ""] }
            ]
          },
          then: "$customerNickname",
          else: {
            $ifNull: [
              "$customer.fullName",
              "Khách hàng"
            ]
          }
        }
      },
      effectiveDiscount: {
        $ifNull: [
          "$discountDecimal",
          NumberDecimal("0")
        ]
      }
    }
  },

  // Bước 3: Tính tiền và chỉ xuất cảnh báo khi cần.
  {
    $set: {
      netAmount: {
        $cond: {
          if: {
            $isNumber: "$amountDecimal"
          },
          then: {
            $subtract: [
              "$amountDecimal",
              "$effectiveDiscount"
            ]
          },
          else: "$$REMOVE"
        }
      },
      amountWarning: {
        $cond: {
          if: {
            $isNumber: "$amountDecimal"
          },
          then: "$$REMOVE",
          else: "AMOUNT_MISSING_OR_INVALID"
        }
      }
    }
  },

  // Bước 4: Tạo read model đầu ra.
  {
    $project: {
      _id: 1,
      status: 1,
      statusLabel: 1,
      displayName: 1,
      amount: 1,
      discount: 1,
      amountOriginalType: 1,
      amountDecimal: 1,
      effectiveDiscount: 1,
      netAmount: 1,
      amountWarning: 1
    }
  },

  { $sort: { _id: 1 } }
]);
~~~

**Giải thích thiết kế:**

- Stage đầu dùng `$convert` có `onError`/`onNull`, giúp không làm hỏng toàn pipeline nếu amount sai kiểu.
- `$switch` chuyển status sang nhãn có fallback.
- `$cond` chọn tên khách và quyết định có xuất netAmount.
- `$ifNull` fallback cho discount nullish.
- `$$REMOVE` không thêm field netAmount/amountWarning khi không phù hợp.
- `$project` bỏ các trường trung gian không cần thiết như `customerNickname` khi trả về.
- Hai/ba stage `$set` tách biệt tránh phụ thuộc việc một field mới tính trong **cùng một stage** đã được tham chiếu ngay lập tức; cách chia này giúp logic rõ ràng.

### 12.3. Vì sao không âm thầm tính netAmount khi thiếu amount?

Nếu một đơn hàng không có amount, trả `netAmount: 0` có thể khiến ứng dụng nghĩ đây là đơn giá trị 0 hợp lệ. Thay vì vậy, pipeline dùng `$$REMOVE` để không xuất netAmount, đồng thời tạo `amountWarning`. Đây là một quyết định mô hình hóa rõ hơn cho dữ liệu không hợp lệ.

Với sản phẩm thật, có thể phải đánh dấu record lỗi, cho phép remediation hoặc chặn thanh toán. Các biểu thức aggregation chỉ là một phần của chiến lược đảm bảo chất lượng dữ liệu.

### 12.4. Giới hạn của cách chuyển đổi demo

Pipeline trên có thể chuyển string numeric sang decimal và chọn 0 khi discount lỗi chuyển đổi. Đây là chính sách minh họa, không phải khuyến nghị tự động cho tất cả dữ liệu tài chính.

Nếu discount âm hoặc lớn hơn amount, netAmount có thể âm. Nếu điều này không được phép, cần bổ sung các điều kiện như:

~~~javascript
{
  $and: [
    { $gte: ["$discountDecimal", NumberDecimal("0")] },
    { $lte: ["$discountDecimal", "$amountDecimal"] }
  ]
}
~~~

nhưng chỉ nên chạy sau khi đã xác nhận các giá trị có kiểu numeric hợp lệ. Một hệ thống tính tiền đúng còn phải xử lý currency, thuế, rounding và các ràng buộc nghiệp vụ khác.

---

## 13. `$project`, `$addFields` và `$set`: dùng điều kiện ở đâu?

### 13.1. `$project`: quyết định đầu ra

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      isPaid: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          true,
          false
        ]
      }
    }
  }
]);
~~~

`$project` tạo output chỉ chứa các field được yêu cầu và các field tính toán (ngoài quy tắc mặc định của `_id`). Thích hợp để tạo DTO/read model cho API.

### 13.2. `$addFields` và `$set`: thêm hoặc ghi đè field trong luồng aggregation

~~~javascript
db.orders.aggregate([
  {
    $addFields: {
      effectiveDiscount: {
        $ifNull: ["$discount", 0]
      }
    }
  }
]);
~~~

`$set` là alias của `$addFields` trong aggregation:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      effectiveDiscount: {
        $ifNull: ["$discount", 0]
      }
    }
  }
]);
~~~

Các stage này giữ những field khác và thêm hoặc ghi đè field được nêu. Nếu field mới có cùng tên field cũ, giá trị đầu ra thay thế giá trị ở field đó trong pipeline.

### 13.3. `$set` aggregation stage khác `$set` update operator

Hai cú pháp khác ngữ cảnh:

~~~javascript
// Aggregation expression: "$legacyStatus" là tham chiếu field.
db.orders.aggregate([
  {
    $set: {
      normalizedStatus: "$legacyStatus"
    }
  }
]);
~~~

~~~javascript
// Update operator thông thường:
// "$legacyStatus" là chuỗi literal cần gán.
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      normalizedStatus: "$legacyStatus"
    }
  }
);
~~~

Khi muốn **update dựa trên biểu thức**, dùng update với aggregation pipeline nếu phiên bản hỗ trợ, ví dụ:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  [
    {
      $set: {
        normalizedStatus: {
          $ifNull: [
            "$status",
            "UNKNOWN"
          ]
        }
      }
    }
  ]
);
~~~

Lúc này `"$status"` được hiểu như field expression vì đang nằm trong aggregation pipeline update.

---

## 14. Sử dụng `$match` với điều kiện biểu thức và `$expr`

### 14.1. So sánh kiểu query predicate

Một query thông thường:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  }
]);
~~~

có thể tận dụng index trên `status` khi query planner xác định phù hợp.

Nếu cần so sánh hai field trong cùng document, dùng `$expr`:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      $expr: {
        $gt: [
          "$amount",
          "$discount"
        ]
      }
    }
  }
]);
~~~

Tuy nhiên, với dữ liệu lab có amount/discount null, string hoặc missing, ví dụ này chưa bảo đảm so sánh số học đúng. Cần chuẩn hóa dữ liệu hoặc lọc kiểu phù hợp.

### 14.2. Điều kiện phức tạp trong `$expr`

~~~javascript
db.orders.aggregate([
  {
    $match: {
      $expr: {
        $cond: {
          if: {
            $eq: ["$status", "PAID"]
          },
          then: {
            $gte: [
              "$amount",
              500000
            ]
          },
          else: false
        }
      }
    }
  }
]);
~~~

Đây là cách biểu diễn logic trong `$expr`; nhưng nếu predicate có thể viết trực tiếp dạng query:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      amount: { $gte: 500000 }
    }
  }
]);
~~~

thì cách trực tiếp thường rõ hơn và dễ có index bounds phù hợp hơn cho workload truy vấn cơ bản. Không cần dùng `$cond` bên trong `$expr` cho mọi tình huống.

### 14.3. Kết hợp `$match` sớm với `$project` muộn

Khi có thể, nên lọc giảm số document trước khi chạy chuyển đổi hoặc tính toán nặng:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $set: {
      effectiveDiscount: {
        $ifNull: ["$discount", 0]
      }
    }
  },
  {
    $project: {
      status: 1,
      effectiveDiscount: 1
    }
  }
]);
~~~

MongoDB có optimizer có thể sắp xếp lại một số stage theo điều kiện, nhưng không nên giả định mọi phép tính động đều được index hoặc tự pushdown. Đọc `explain` khi workload lớn.

---

## 15. Update document bằng aggregation pipeline với biểu thức điều kiện

Khi muốn **lưu** giá trị tính toán vào collection, MongoDB hỗ trợ update với aggregation pipeline trong các phiên bản phù hợp.

### 15.1. Backfill field mặc định

Ví dụ chỉ đặt `shippingFee` mặc định khi field missing/null:

~~~javascript
db.orders.updateMany(
  {
    _id: {
      $in: [
        "ORD-103",
        "ORD-106"
      ]
    }
  },
  [
    {
      $set: {
        shippingFee: {
          $ifNull: [
            "$shippingFee",
            0
          ]
        }
      }
    }
  ]
);
~~~

Đây là update thật, khác với `aggregate()`. Khi chạy lần sau, shippingFee đã là 0, `$ifNull` giữ nguyên 0 nên thao tác có thể không làm thay đổi giá trị.

### 15.2. Chỉ tạo field khi status phù hợp

~~~javascript
db.orders.updateMany(
  {
    _id: {
      $in: ["ORD-101", "ORD-102", "ORD-103"]
    }
  },
  [
    {
      $set: {
        accountingLabel: {
          $cond: {
            if: {
              $eq: ["$status", "PAID"]
            },
            then: "BOOKED",
            else: "$$REMOVE"
          }
        }
      }
    }
  ]
);
~~~

Với PAID, field kế toán được đặt. Với status khác, biến `$$REMOVE` khiến field không được lưu ở output của stage. Nếu trong document cũ đã có accountingLabel, cách này có thể loại field khi điều kiện false; cần hiểu đó là thao tác mutate dữ liệu, không chỉ lọc output.

### 15.3. Kết hợp nhiều stage để dùng field trung gian

~~~javascript
db.orders.updateMany(
  {
    status: "PAID"
  },
  [
    {
      $set: {
        amountDecimal: {
          $convert: {
            input: "$amount",
            to: "decimal",
            onError: null,
            onNull: null
          }
        }
      }
    },
    {
      $set: {
        amountBand: {
          $cond: {
            if: {
              $isNumber: "$amountDecimal"
            },
            then: {
              $cond: [
                {
                  $gte: [
                    "$amountDecimal",
                    NumberDecimal("1000000")
                  ]
                },
                "HIGH",
                "NORMAL"
              ]
            },
            else: "UNKNOWN"
          }
        }
      }
    }
  ]
);
~~~

Việc backfill này có thể đổi kiểu hoặc bổ sung field cho nhiều document; trong production phải đánh giá schema validator, write load, index maintenance, tính idempotent và số document dự kiến trước khi chạy.

### 15.4. Không tự bật upsert khi chỉ sửa bản ghi có sẵn

Update pipeline cũng có thể được dùng trong `updateOne` với `upsert`, nhưng nếu nghiệp vụ chỉ cập nhật document đang tồn tại, không tự thêm `upsert: true`. Một filter sai có thể dẫn đến document mới thiếu những field bắt buộc.

---

## 16. Điều kiện bên trong array: `$map`, `$ifNull` và `$cond`

Một document có thể chứa mảng line items. Nhu cầu: mỗi item có `quantity`; nếu thiếu/null thì mặc định 1; nếu quantity ≥ 10 thì phân loại BULK.

### 16.1. Với array hợp lệ

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: "ORD-101"
    }
  },
  {
    $project: {
      _id: 1,
      normalizedItems: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            quantity: {
              $ifNull: [
                "$$line.quantity",
                1
              ]
            },
            lineType: {
              $cond: {
                if: {
                  $gte: [
                    "$$line.quantity",
                    10
                  ]
                },
                then: "BULK",
                else: "STANDARD"
              }
            }
          }
        }
      }
    }
  }
]);
~~~

`$$line` là biến của `$map`, không phải field top-level. `$$line.quantity` truy cập field trong mỗi phần tử đang xử lý.

### 16.2. Nếu items thiếu hoặc null

`$map` xử lý input nullish theo quy tắc riêng, có thể trả null. Nếu ứng dụng muốn luôn có mảng đầu ra, kết hợp `$ifNull`:

~~~javascript
{
  $map: {
    input: {
      $ifNull: [
        "$items",
        []
      ]
    },
    as: "line",
    in: {
      sku: "$$line.sku"
    }
  }
}
~~~

### 16.3. Nếu items có thể sai kiểu

Nếu `items` là object hoặc string chứ không phải array, `$map` có thể báo lỗi. `$ifNull` không thay giá trị sai kiểu, nên cần kiểm tra bằng `$isArray`:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      normalizedItems: {
        $map: {
          input: {
            $cond: {
              if: {
                $isArray: "$items"
              },
              then: "$items",
              else: []
            }
          },
          as: "line",
          in: {
            sku: "$$line.sku",
            quantity: {
              $ifNull: [
                "$$line.quantity",
                1
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

Cách này tránh lỗi kiểu input không phải array, nhưng **ẩn đi dữ liệu sai kiểu** bằng mảng rỗng. Với dữ liệu quan trọng, nên xuất thêm một field cảnh báo hoặc chặn nguồn dữ liệu sai schema.

### 16.4. Điều kiện lồng nhau ở từng phần tử

Nếu quantity có thể là string, boolean hoặc null, tránh dùng so sánh đơn thuần:

~~~javascript
{
  $cond: {
    if: {
      $isNumber: "$$line.quantity"
    },
    then: {
      $cond: [
        { $gte: ["$$line.quantity", 10] },
        "BULK",
        "STANDARD"
      ]
    },
    else: "INVALID_QUANTITY"
  }
}
~~~

Nếu quyết định cho phép string numeric, có thể thêm `$convert` với `onError`, nhưng cần định nghĩa kiểu dữ liệu đầu ra và chính sách validation.

---

## 17. `$group` sau phân loại và xử lý dữ liệu thiếu

Khi đã tạo label bằng `$switch` hoặc `$cond`, có thể nhóm kết quả theo label.

### 17.1. Nhóm theo status label

~~~javascript
db.orders.aggregate([
  {
    $set: {
      statusGroup: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$status", "PAID"] },
              then: "PAID"
            },
            {
              case: { $eq: ["$status", "NEW"] },
              then: "OPEN"
            },
            {
              case: { $eq: ["$status", "CANCELLED"] },
              then: "CLOSED"
            },
            {
              case: { $eq: ["$status", "REFUNDED"] },
              then: "CLOSED"
            }
          ],
          default: "UNKNOWN"
        }
      }
    }
  },
  {
    $group: {
      _id: "$statusGroup",
      orderCount: { $sum: 1 }
    }
  },
  {
    $sort: {
      orderCount: -1,
      _id: 1
    }
  }
]);
~~~

Do `default` là UNKNOWN, document thiếu status vẫn được đếm vào một nhóm rõ ràng thay vì làm pipeline báo lỗi. Sắp xếp theo count và `_id` làm tie-breaker nếu các nhóm có cùng số lượng.

### 17.2. Tổng amount chỉ khi số hợp lệ

~~~javascript
db.orders.aggregate([
  {
    $set: {
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $group: {
      _id: "$status",
      orderCount: {
        $sum: 1
      },
      totalKnownAmount: {
        $sum: {
          $ifNull: [
            "$amountDecimal",
            NumberDecimal("0")
          ]
        }
      },
      unknownAmountCount: {
        $sum: {
          $cond: [
            {
              $isNumber: "$amountDecimal"
            },
            0,
            1
          ]
        }
      }
    }
  }
]);
~~~

Kết quả có tổng những amount đã chuyển đổi thành công và số record có amount không hợp lệ hoặc nullish. Đây là cách báo cáo tốt hơn việc coi toàn bộ amount missing bằng 0 rồi không ghi nhận lỗi dữ liệu.

### 17.3. Đừng quên type và rounding khi tổng hợp

Nếu amount là tiền, sử dụng Decimal128 nhất quán và quy tắc rounding phù hợp. Trước khi chạy pipeline nhóm toàn collection trên dữ liệu lớn, đánh giá chi phí aggregation, memory và khả năng tận dụng index của `$match`.

---

## 18. Hiệu năng: điều kiện nên đặt ở đâu trong pipeline?

### 18.1. Ưu tiên các filter có thể dùng index

Nếu query chỉ cần đơn PAID:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $set: {
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  {
    $project: {
      amountDecimal: 1
    }
  }
]);
~~~

Thường tốt hơn khi biểu thức conversion chỉ chạy trên document đã qua filter. Index trên `status` có thể giúp `$match` nếu planner quyết định phù hợp.

### 18.2. Biểu thức tính động thường không tự dùng được index thường

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      isHigh: {
        $cond: [
          { $gte: ["$amount", 1000000] },
          true,
          false
        ]
      }
    }
  },
  {
    $match: {
      isHigh: true
    }
  }
]);
~~~

Nếu `isHigh` là field mới tính trong pipeline, không thể mặc định dùng index B-tree trên `isHigh` trong dữ liệu gốc — field đó chưa tồn tại trước pipeline. Tùy optimizer và hình dạng biểu thức, MongoDB có thể có tối ưu hóa nhất định, nhưng đừng dựa vào điều đó như một bảo đảm.

Nếu query chỉ cần amount ≥ 1 triệu trên field numeric chuẩn hóa, viết:

~~~javascript
db.orders.find({
  amount: { $gte: 1000000 }
});
~~~

thường rõ hơn và có cơ hội tận dụng index trực tiếp trên amount, trong khi query với dữ liệu amount kiểu string sẽ cần quy tắc dữ liệu riêng.

### 18.3. Khi nào materialize computed field?

Nếu API lọc và sort liên tục theo một phân loại tính toán, có thể cân nhắc lưu một field dẫn xuất trong document:

~~~javascript
{
  _id: "ORD-101",
  status: "PAID",
  amount: NumberDecimal("1200000"),
  amountBand: "HIGH"
}
~~~

rồi tạo index theo query:

~~~javascript
db.orders.createIndex({
  status: 1,
  amountBand: 1,
  _id: 1
});
~~~

Đánh đổi: mỗi khi amount đổi, ứng dụng phải cập nhật amountBand nhất quán. Materialized field giảm chi phí đọc nhưng tăng complexity và write maintenance. Chọn dựa trên workload thay vì mặc định mọi phép `$cond` đều cần lưu trước.

### 18.4. Tách rõ conversion và nhánh condition

Một biểu thức dài lồng rất nhiều `$convert`, `$ifNull` và `$switch` có thể khó đọc và khó bảo trì. Chia thành các stage tính trường trung gian rồi project bỏ chúng ở cuối thường rõ hơn, dù cần benchmark để kiểm tra chi phí.

Tuy nhiên, không tạo hàng chục stage nhỏ chỉ vì muốn “đẹp”; cân nhắc readability, optimizer và reuse biểu thức.

### 18.5. Không dùng fallback để che giấu sai dữ liệu

Nếu một endpoint tài chính trả 0 khi amount invalid, điều đó có thể làm báo cáo doanh thu sai. Đôi khi tốt hơn:

- Đặt `amountState` = INVALID.
- Loại record khỏi tổng và đếm số lỗi.
- Gửi cảnh báo dữ liệu.
- Thực hiện migration hoặc validation tại nguồn.
- Không hiển thị số tiền được suy đoán.

Aggregation không tự quyết định chính sách nghiệp vụ khi dữ liệu thiếu; người thiết kế phải làm điều đó.

---

## 19. Các lưu ý về kiểu dữ liệu và truthiness

### 19.1. 0 không phải null

~~~javascript
{
  $ifNull: [
    0,
    100
  ]
}
~~~

kết quả là **0**, không phải 100. Tương tự:

~~~javascript
{
  $ifNull: [
    false,
    true
  ]
}
~~~

kết quả là **false**.

### 19.2. Chuỗi rỗng không phải null

~~~javascript
{
  $ifNull: [
    "",
    "UNKNOWN"
  ]
}
~~~

kết quả là **chuỗi rỗng**. Nếu muốn thay chuỗi rỗng, dùng `$cond` với `$eq`, hoặc kết hợp xử lý trim khi kiểu dữ liệu cho phép.

### 19.3. Mảng rỗng không phải null

~~~javascript
{
  $ifNull: [
    [],
    ["fallback"]
  ]
}
~~~

kết quả là **mảng rỗng**, không phải mảng fallback.

Nếu ứng dụng muốn “mảng không có phần tử thì thay bằng một mảng mặc định”, dùng điều kiện về `$size` sau khi đã xác nhận input là array.

### 19.4. Không dùng coercion boolean để thay validation

MongoDB có quy tắc boolean cho điều kiện; một string, array hay object có thể được coi true dù nghiệp vụ yêu cầu boolean chuẩn. Nếu field `isEnabled` phải là bool, nên lưu bool và dùng schema validation, không mặc định một giá trị string `"false"` sẽ được diễn giải thành false.

### 19.5. Nếu cần coi field sai kiểu như missing, phải nêu rõ

`$ifNull` không tự loại giá trị sai kiểu. Ví dụ document có `phone: 12345` trong khi API chỉ chấp nhận phone string. Nếu muốn fallback sang `alternatePhone`, cần kết hợp `$type`:

~~~javascript
{
  $cond: {
    if: {
      $eq: [
        { $type: "$phone" },
        "string"
      ]
    },
    then: "$phone",
    else: {
      $ifNull: [
        "$alternatePhone",
        "UNKNOWN"
      ]
    }
  }
}
~~~

Ở đây nếu `alternatePhone` cũng sai kiểu thì vẫn có thể bị chấp nhận. Với ứng dụng quan trọng, cần kiểm tra kiểu cả hai nguồn hoặc chuẩn hóa schema trước khi dùng fallback.

---

## 20. Java Sync Driver: xây aggregation có điều kiện

MongoDB Java Driver cho phép tạo pipeline bằng BSON Documents hoặc helpers trong `Aggregates`. Ví dụ dùng `Document` để dễ nhìn ánh xạ từ MQL.

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public class ConditionalAggregationExample {

    public static void run(MongoCollection<Document> collection) {

        Document statusLabel = new Document(
            "$switch",
            new Document("branches", Arrays.asList(
                new Document("case",
                    new Document("$eq",
                        Arrays.asList("$status", "PAID")
                    )
                ).append("then", "Đã thanh toán"),

                new Document("case",
                    new Document("$eq",
                        Arrays.asList("$status", "NEW")
                    )
                ).append("then", "Chờ xử lý")
            )).append("default", "Khác")
        );

        Document discountFallback = new Document(
            "$ifNull",
            Arrays.asList("$discount", 0)
        );

        Document project = new Document("$project",
            new Document("_id", 1)
                .append("status", 1)
                .append("statusLabel", statusLabel)
                .append("effectiveDiscount", discountFallback)
        );

        List<Bson> pipeline = Arrays.asList(project);

        collection.aggregate(pipeline)
            .forEach(System.out::println);
    }
}
~~~

Đoạn code giả định `collection` đã được lấy từ `MongoClient` với cấu hình kết nối phù hợp. Nếu dùng Spring Data MongoDB, cũng có thể biểu diễn `$cond`/`$switch`/`$ifNull` qua aggregation DSL hoặc BSON pipeline theo khả năng phiên bản.

**Quan trọng:** API Java không tự chữa lỗi kiểu dữ liệu của document. Nếu field discount có string hoặc boolean, `$ifNull` vẫn có thể giữ kiểu đó như trong mongosh. Lớp Java DTO nên thể hiện rõ kiểu expected và xử lý trường hợp missing/null.

### 20.1. Giữ biểu thức và contract API nhất quán

Ví dụ một endpoint trả:

~~~json
{
  "orderId": "ORD-101",
  "statusLabel": "Đã thanh toán",
  "effectiveDiscount": 100000
}
~~~

Nếu aggregation có khi trả number, khi trả string, deserializer Java có thể lỗi hoặc phải dùng `Object` kém an toàn. Nên chuẩn hóa type đầu ra bằng `$convert` và validator thay vì chỉ xử lý trường hợp null.

### 20.2. Nên test cả kết quả lẫn sự hiện diện của field

Khi dùng `$$REMOVE`, kiểm thử không chỉ so giá trị:

~~~text
expected warning == null
~~~

vì field **không tồn tại** khác field tồn tại với giá trị null. Test nên kiểm tra document có chứa key hay không, ví dụ `containsKey("warning")` với loại object thích hợp.

---

## 21. Lỗi thường gặp và cách xử lý

### Lỗi 1 — Dùng `$cond` thiếu else

Sai:

~~~javascript
{
  $cond: {
    if: { $eq: ["$status", "PAID"] },
    then: "PAID"
  }
}
~~~

`$cond` cần đủ `if`, `then`, `else`. Viết đầy đủ:

~~~javascript
{
  $cond: {
    if: { $eq: ["$status", "PAID"] },
    then: "PAID",
    else: "OTHER"
  }
}
~~~

### Lỗi 2 — `$switch` không có default, gặp trạng thái mới

Khi không nhánh nào match và không có default, pipeline có thể lỗi. Thêm `default` theo chính sách và theo dõi những trạng thái lạ.

### Lỗi 3 — Đặt nhánh rộng trước nhánh hẹp

Ví dụ check amount ≥ 500.000 trước amount ≥ 1.000.000 khiến nhóm HIGH không bao giờ nhận những record lớn. Đặt nhánh cụ thể/ưu tiên cao trước.

### Lỗi 4 — Cho rằng `$ifNull` thay cả 0, false và chuỗi rỗng

`$ifNull` chỉ thay nullish, nên 0/false/`""`/`[]` vẫn được giữ. Nếu muốn coi chuỗi rỗng là thiếu, viết điều kiện riêng.

### Lỗi 5 — Dùng `$ifNull` để xử lý string sai kiểu

`$ifNull` không chuyển `"900000"` thành số 900.000. Dùng `$convert` với `onError` và `onNull`, đồng thời quy định dữ liệu sai kiểu được xử lý thế nào.

### Lỗi 6 — Không phân biệt missing và null

`$ifNull` gom missing/null. Nếu cần phân biệt bản ghi cũ chưa có field với explicit null, dùng `$type` và kiểm tra `"missing"`/`"null"`.

### Lỗi 7 — Dùng `$exists` như aggregation expression

`$exists` là query predicate, không phải phép expression có thể đặt trực tiếp vào vị trí `if` của `$cond`. Trong aggregation expression, dùng `$type` và so sánh với `"missing"` khi muốn kiểm tra field có tồn tại không.

### Lỗi 8 — Nhầm field path với literal string bắt đầu bằng `$`

`"$amount"` trong expression là field reference. Muốn chuỗi literal đó, dùng `{ $literal: "$amount" }`.

### Lỗi 9 — Dùng field mới tính trong cùng một stage như thể nó đã sẵn có

Một stage `$set` tính `amountDecimal` và `amountBand` rồi tham chiếu `"$amountDecimal"` trong cùng stage có thể không đọc giá trị mới như mong muốn. Tách thành hai stage để bảo đảm amountBand được tính từ output của stage trước.

### Lỗi 10 — Dùng `$$REMOVE` rồi tưởng đã xóa trong database

`$$REMOVE` trong một `aggregate()` định hình output, không tự ghi vào collection. Chỉ khi dùng trong thao tác ghi như update pipeline thì mới có thể làm thay đổi document được lưu.

### Lỗi 11 — Dùng `$map` trên field sai kiểu

`$map` đòi input là array/nullish theo ngữ nghĩa của nó; input string/object có thể gây lỗi. Kiểm tra `$isArray` hoặc schema validation.

### Lỗi 12 — Dùng `$gte` trên string-number rồi tin là so sánh tiền

`$gte` giữa các giá trị BSON khác kiểu có quy tắc riêng. Chuẩn hóa field về Decimal128/integer trước khi phân loại tài chính.

### Lỗi 13 — Không có nhãn cho dữ liệu không hợp lệ

Nếu amount missing được fallback thành 0, báo cáo có thể coi một đơn chưa có dữ liệu là đơn giá 0. Tạo thêm trường trạng thái/cảnh báo hoặc loại khỏi phép tổng theo chính sách.

### Lỗi 14 — Để pipeline tính động trước filter có thể dùng index

Nếu phải xử lý hàng triệu document với `$convert` và `$switch` chỉ để lọc một nhóm nhỏ, nên xem có thể `$match` sớm bằng các field đã chuẩn hóa và index được không.

### Lỗi 15 — Dùng `$project`/`$set` mà không hiểu khác biệt output

`$project` có thể loại các field không được liệt kê. `$set`/`$addFields` giữ các field cũ rồi thêm/ghi đè. Chọn stage theo contract đầu ra thay vì hoán đổi tùy tiện.

---

## 22. Quy trình thiết kế biểu thức điều kiện cho API và báo cáo

### Bước 1 — Xác định ngữ nghĩa nghiệp vụ

Ví dụ "không có discount" có nghĩa gì?

- Missing và null đều được coi là 0?
- Discount false là dữ liệu không hợp lệ?
- Chuỗi `"50000"` có được chấp nhận và chuyển kiểu?
- Discount âm có được cho phép?
- Có cần biết record nào đang lệch schema?

Chưa trả lời các câu này thì chưa nên viết fallback.

### Bước 2 — Phân nhóm dữ liệu đầu vào

Lấy mẫu các document thuộc trạng thái:

~~~text
missing | null | 0 | false | "" | số | string số | object | array
~~~

Đặc biệt với dữ liệu legacy, phải kiểm tra type distribution thay vì giả định mọi field đồng nhất.

### Bước 3 — Chọn biểu thức nhỏ nhất đủ dùng

- Hai kết quả: `$cond`.
- Nhiều nhánh có ưu tiên: `$switch`.
- Fallback nullish: `$ifNull`.
- Phân biệt missing và null: `$type` + condition.
- Kiểm tra/convert kiểu: `$isNumber`/`$convert`.
- Không xuất field khi không áp dụng: `$$REMOVE`.

### Bước 4 — Quy định output type

Nếu field `netAmount` là Decimal128, đừng để một nhánh trả string `"unknown"` còn nhánh khác trả decimal nếu DTO yêu cầu numeric. Có thể tách field numeric và field warning.

### Bước 5 — Dùng `$match` sớm khi có thể

Filter theo các field gốc có index trước khi xử lý expression nặng. Nếu chỉ có thể lọc qua computed field, đo chi phí bằng explain và cân nhắc materialization.

### Bước 6 — Kiểm tra các trường hợp biên

Dùng bộ dữ liệu có missing, null, 0, false, empty string, invalid type, unknown status, array rỗng, nested field vắng và numeric string.

### Bước 7 — Phân biệt read projection và write migration

Nếu chỉ muốn response fallback, dùng aggregation đọc. Nếu muốn lưu field mới, cần kế hoạch update pipeline, audit, schema validator và rollback.

### Bước 8 — Giám sát dữ liệu lạ

Một nhánh default như `"UNKNOWN"` nên có cách đếm hoặc báo cáo khi xuất hiện, tránh âm thầm che lỗi dữ liệu trong nhiều tháng.

---

## 23. Bài tập thực hành

### Bài tập 1 — `$cond` hai cú pháp

Với document ORD-101 và ORD-102:

1. Viết `$cond` dạng object tạo `amountLevel` = HIGH nếu amount ≥ 1.000.000, else NORMAL.
2. Viết lại dạng array.
3. So kết quả hai truy vấn.
4. Mở rộng tới ORD-105 có amount string, phân tích vì sao phải chuẩn hóa trước khi áp dụng vào production.

### Bài tập 2 — Phân loại trạng thái với `$switch`

Tạo `statusLabel`:

- NEW → CHO_XU_LY.
- PAID → DA_THANH_TOAN.
- CANCELLED → DA_HUY.
- REFUNDED → HOAN_TIEN.
- Các trường hợp còn lại → UNKNOWN.

Thử đổi vị trí các branches và bỏ default; giải thích thứ tự ưu tiên và hành vi khi status thiếu.

### Bài tập 3 — `$ifNull` và giá trị 0

Trên dữ liệu lab, tạo `effectiveDiscount` bằng `$ifNull:["$discount",0]`. Liệt kê kết quả ORD-102, ORD-103, ORD-104, ORD-105, ORD-107. Vì sao 0 không kích hoạt fallback? Vì sao string và false vẫn được giữ?

### Bài tập 4 — Fallback nhiều nguồn (MongoDB 5.0+)

Tạo `chargeableShippingFee` ưu tiên:

1. shippingFee.
2. estimatedShippingFee.
3. 0.

So sánh ORD-102, ORD-104 và ORD-103. Viết thêm bản nested `$ifNull` tương thích với cú pháp hai đối số.

### Bài tập 5 — Missing khác null

Dùng `$type` và `$switch` tạo `discountState` với các giá trị:

- MISSING
- EXPLICIT_NULL
- NUMERIC
- INVALID_TYPE

Giải thích ORD-103, ORD-104, ORD-102 và ORD-107.

### Bài tập 6 — Không xuất field

Tạo trường `warning` bằng `$cond`:

- Nếu status CANCELLED → "Cancelled order".
- Ngược lại → `$$REMOVE`.

So sánh với trường hợp else trả `null`. Kiểm tra sự có mặt của key `warning` trong output.

### Bài tập 7 — Sửa dữ liệu số sai kiểu

Tạo `amountDecimal` bằng `$convert`, xử lý onError/onNull. Tạo `amountBand`:

- UNKNOWN nếu không convert được.
- HIGH nếu ≥ 1.000.000.
- MEDIUM nếu ≥ 500.000.
- LOW nếu còn lại.

Đối chiếu ORD-101, ORD-102, ORD-105, ORD-106 và ORD-109. Không dùng phép so sánh trực tiếp trên string amount.

### Bài tập 8 — Chuỗi rỗng là missing theo nghiệp vụ

ORD-102 có nickname `""` và fullName `"Trần Bình"`. Xây displayName sao cho:

- Nickname string không rỗng được ưu tiên.
- Nếu nickname missing/null/empty, dùng fullName.
- Nếu fullName cũng missing/null, dùng "Khách hàng".

Vì sao `$ifNull` đơn thuần không giải quyết nickname rỗng?

### Bài tập 9 — Array items thiếu hoặc sai kiểu

Tạo ba document lab có:

- `items` là array hợp lệ.
- `items` missing.
- `items` là string sai schema.

Dùng `$isArray`, `$cond` và `$map` để tránh lỗi input type, đồng thời xuất `itemsWarning` khi field không phải array. Đừng che dữ liệu sai bằng mảng rỗng mà không báo cáo.

### Bài tập 10 — Report nhóm và số liệu không hợp lệ

Nhóm đơn theo status, tính:

- orderCount.
- totalKnownAmount đã convert về decimal.
- unknownAmountCount.
- paidOrderCount bằng `$cond` bên trong `$sum`.

Giải thích cách phân biệt đơn hợp lệ có amount 0 với đơn thiếu amount.

### Bài tập 11 — Update pipeline

Trong collection lab, dùng `updateMany` với pipeline:

- Backfill shippingFee = 0 cho các document có shippingFee nullish.
- Chỉ lưu accountingLabel khi status PAID, nếu không thì `$$REMOVE`.
- Kiểm tra bản ghi trước/sau và độ idempotent khi chạy lại.

Không chạy lệnh update trên production.

### Bài tập 12 — Hiệu năng và index

Trên dataset đủ lớn:

1. So query lọc status PAID trước rồi convert amount với pipeline convert tất cả amount rồi mới match.
2. Tạo index trên status nếu workload phù hợp.
3. Dùng explain xem plan và docs examined.
4. Thảo luận khi nào nên materialize amountBand và index nó.
5. Đánh giá chi phí ghi khi amountBand phải cập nhật theo amount.

---

## 24. Câu hỏi ôn tập

1. `$cond` có những dạng cú pháp nào? Cần những thành phần gì?
2. `$switch` chọn nhánh nào nếu nhiều case cùng true?
3. Khi nào `$switch` báo lỗi nếu không có default?
4. `$ifNull` khác `$cond` về điều kiện chọn kết quả như thế nào?
5. Từ phiên bản nào `$ifNull` hỗ trợ nhiều input?
6. `$ifNull` có coi 0 là null không?
7. `$ifNull` có coi false là null không?
8. `$ifNull` có thay chuỗi rỗng bằng fallback không?
9. Missing và BSON null khác nhau như thế nào?
10. `$type` trên field thiếu có thể trả giá trị gì?
11. Vì sao query `{field:null}` có thể khớp document thiếu field?
12. Khi cần kiểm tra field thiếu trong biểu thức, vì sao không dùng `$exists` trực tiếp?
13. Khi nào dùng `$$REMOVE` thay vì null?
14. `$$REMOVE` trong `aggregate` có tự sửa database không?
15. Phải xử lý dữ liệu string-number như thế nào trước khi so sánh số học?
16. `$convert.onError` và `$convert.onNull` khác nhau ở đâu?
17. Tại sao một pipeline nên giữ field trạng thái lỗi dữ liệu thay vì luôn fallback 0?
18. Khi nào nên dùng nested `$cond`, khi nào nên dùng `$switch`?
19. Vì sao thứ tự branches của `$switch` quan trọng?
20. Dùng `$ifNull` trong array có tránh được mọi lỗi sai kiểu không?
21. `$isArray` hỗ trợ `$map` như thế nào?
22. Tại sao field vừa tạo ở stage trước nên được sử dụng ở stage tiếp theo?
23. Khi nào một computed field nên được materialize?
24. `$match` với query predicate có thể dùng index khác gì với biểu thức tính toán trong `$expr`?
25. Khi thay đổi dữ liệu bằng update pipeline, cần những biện pháp an toàn nào?

---

## 25. Tổng kết

Trong MongoDB aggregation, **`$cond`**, **`$switch`** và **`$ifNull`** giải quyết ba kiểu quyết định thường gặp:

- **`$cond`**: chọn hai nhánh theo điều kiện boolean, có dạng object và array, yêu cầu đủ nhánh true/false.
- **`$switch`**: mô tả nhiều nhánh có thứ tự, chọn **case đúng đầu tiên**, nên có `default` để xử lý dữ liệu chưa được nhận diện.
- **`$ifNull`**: chọn giá trị thay thế khi một input nullish; trong MongoDB 5.0+ có thể kiểm tra nhiều nguồn theo thứ tự ưu tiên.

Dữ liệu thiếu là điểm dễ gây sai lầm nhất:

- **Missing** khác **null**, và cả hai khác **0**, **false**, **`""`** hay **`[]`**.
- `$ifNull` không tự sửa dữ liệu sai kiểu.
- `$type` giúp phân biệt missing/null/kiểu BSON.
- `$convert`, `$isNumber` và `$isArray` giúp kiểm soát các phép tính và array transformations.
- `$$REMOVE` dùng để loại field đầu ra khi cần, thay vì giữ một giá trị null.
- Trong các phép tính quan trọng, không nên chuyển mọi lỗi dữ liệu thành 0 rồi làm mất dấu vết.

Một pipeline tốt cần **rõ ngữ nghĩa nghiệp vụ, xử lý các trường hợp biên, trả kiểu dữ liệu nhất quán, không làm mất thông tin lỗi và dùng index/chi phí tính toán hợp lý**.

## Tài liệu MongoDB chính thức tham khảo

- [MongoDB Manual — $cond](https://www.mongodb.com/docs/manual/reference/operator/aggregation/cond/)
- [MongoDB Manual — $switch](https://www.mongodb.com/docs/manual/reference/operator/aggregation/switch/)
- [MongoDB Manual — $ifNull](https://www.mongodb.com/docs/manual/reference/operator/aggregation/ifNull/)
- [MongoDB Manual — $type (aggregation)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/)
- [MongoDB Manual — $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB Manual — $isNumber](https://www.mongodb.com/docs/manual/reference/operator/aggregation/isNumber/)
- [MongoDB Manual — $isArray](https://www.mongodb.com/docs/manual/reference/operator/aggregation/isArray/)
- [MongoDB Manual — $map](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/)
- [MongoDB Manual — $project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/)
- [MongoDB Manual — $addFields / $set](https://www.mongodb.com/docs/manual/reference/operator/aggregation/addFields/)
- [MongoDB Manual — Aggregation Variables / $$REMOVE](https://www.mongodb.com/docs/manual/reference/aggregation-variables/)
- [MongoDB Manual — Update with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
