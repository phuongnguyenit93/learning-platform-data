# Chia khoảng bằng $bucket và $bucketAuto

Trong MongoDB, aggregation không chỉ dùng để lọc document hoặc nhóm các giá trị giống nhau. Nhiều báo cáo cần **chia dữ liệu thành các khoảng (bucket)**: giá sản phẩm từ 0 đến dưới 100 nghìn đồng, điểm số từ 50 đến dưới 65, đơn hàng theo tháng, tuổi khách hàng theo nhóm hoặc lượng giao dịch theo các mức giá trị.

Hai aggregation stage chuyên dụng cho bài toán này là:

- **`$bucket`**: lập trình viên **định nghĩa sẵn ranh giới các khoảng**. Thích hợp khi doanh nghiệp có những phân khúc cố định và cần so sánh nhiều kỳ.
- **`$bucketAuto`**: MongoDB **tự tính ranh giới** dựa vào phân bố dữ liệu, với mục tiêu tạo gần một số lượng bucket được yêu cầu và phân bổ số document tương đối cân bằng.

Ví dụ: đội kinh doanh cần thống kê số sản phẩm trong các nhóm giá dưới 100.000, 100.000–dưới 300.000, 300.000–dưới 600.000 đồng: dùng `$bucket`. Nếu đội phân tích chưa biết nên đặt các mốc ở đâu và muốn chia sản phẩm thành bốn nhóm gần bằng nhau về số lượng: dùng `$bucketAuto`.

Bài học sẽ làm rõ cú pháp, tính bao gồm của cận dưới/cận trên, xử lý document ngoài khoảng, accumulator, chia theo thời gian, số lượng bucket thực tế, tính ổn định theo thời gian, hiệu năng, ví dụ Java và các bài tập thực hành.

## 1. Chuẩn bị dữ liệu học tập

Ta sử dụng collection `bucketLabProducts` trong môi trường thử nghiệm. `price` được lưu bằng BSON Decimal128 và có **đơn vị nghìn đồng**; số `100` biểu thị giá 100.000 đồng. Không chạy `drop()` trên collection có dữ liệu thực tế cần giữ.

```javascript
db.bucketLabProducts.drop();

db.bucketLabProducts.insertMany([
  {
    _id: "P01", name: "Bút bi",
    category: "stationery",
    price: NumberDecimal("50"), stock: 80,
    createdAt: ISODate("2026-01-05T08:00:00Z")
  },
  {
    _id: "P02", name: "Sổ tay",
    category: "stationery",
    price: NumberDecimal("90"), stock: 60,
    createdAt: ISODate("2026-01-17T08:00:00Z")
  },
  {
    _id: "P03", name: "Bình nước",
    category: "accessory",
    price: NumberDecimal("100"), stock: 35,
    createdAt: ISODate("2026-02-01T08:00:00Z")
  },
  {
    _id: "P04", name: "Tai nghe",
    category: "electronics",
    price: NumberDecimal("180"), stock: 25,
    createdAt: ISODate("2026-02-10T08:00:00Z")
  },
  {
    _id: "P05", name: "Chuột văn phòng",
    category: "electronics",
    price: NumberDecimal("299"), stock: 20,
    createdAt: ISODate("2026-02-26T08:00:00Z")
  },
  {
    _id: "P06", name: "Bàn phím",
    category: "electronics",
    price: NumberDecimal("300"), stock: 15,
    createdAt: ISODate("2026-03-01T08:00:00Z")
  },
  {
    _id: "P07", name: "Ổ cứng di động",
    category: "electronics",
    price: NumberDecimal("450"), stock: 12,
    createdAt: ISODate("2026-03-12T08:00:00Z")
  },
  {
    _id: "P08", name: "Loa Bluetooth",
    category: "electronics",
    price: NumberDecimal("599"), stock: 10,
    createdAt: ISODate("2026-03-28T08:00:00Z")
  },
  {
    _id: "P09", name: "Màn hình nhỏ",
    category: "electronics",
    price: NumberDecimal("600"), stock: 8,
    createdAt: ISODate("2026-04-03T08:00:00Z")
  },
  {
    _id: "P10", name: "Màn hình lớn",
    category: "electronics",
    price: NumberDecimal("850"), stock: 5,
    createdAt: ISODate("2026-04-19T08:00:00Z")
  },
  {
    _id: "P11", name: "Máy in",
    category: "electronics",
    price: NumberDecimal("1000"), stock: 4,
    createdAt: ISODate("2026-05-01T08:00:00Z")
  },
  {
    _id: "P12", name: "Bộ thiết bị chuyên dụng",
    category: "electronics",
    price: NumberDecimal("1200"), stock: 2,
    createdAt: ISODate("2026-05-15T08:00:00Z")
  },
  {
    _id: "P13", name: "Mẫu có giá null",
    category: "electronics",
    price: null, stock: 1,
    createdAt: ISODate("2026-06-02T08:00:00Z")
  },
  {
    _id: "P14", name: "Mẫu thiếu giá",
    category: "electronics",
    stock: 3,
    createdAt: ISODate("2026-06-12T08:00:00Z")
  },
  {
    _id: "P15", name: "Mẫu giá âm",
    category: "electronics",
    price: NumberDecimal("-20"), stock: 1,
    createdAt: ISODate("2026-06-20T08:00:00Z")
  }
]);
```

Dữ liệu bao gồm những trường hợp được thiết kế có chủ đích: giá bằng đúng ranh giới `100`, `300`, `600`, `1000`; giá ở ngoài phạm vi; giá `null`; và trường `price` không tồn tại. Những trường hợp biên này giúp tránh hiểu sai kết quả histogram.

## 2. Thế nào là một khoảng dữ liệu?

Giả sử báo cáo yêu cầu bốn khoảng giá:

```text
0          100           300            600           1000
|-----------|-------------|--------------|--------------|
 [0,100)     [100,300)     [300,600)      [600,1000)
```

Ký hiệu `[a,b)` có nghĩa:

- Bao gồm giá trị **bằng a**.
- Không bao gồm giá trị **bằng b**.
- Một giá trị thuộc đúng một khoảng được xác định trong chuỗi các cận tăng.

Do đó:

| Giá trị | Bucket chứa nó |
|---:|---|
| 0 | `[0,100)` |
| 99 | `[0,100)` |
| **100** | **`[100,300)`** |
| 299 | `[100,300)` |
| **300** | **`[300,600)`** |
| **600** | **`[600,1000)`** |
| 999 | `[600,1000)` |
| **1000** | **Không thuộc các khoảng trên** |
| -20 | Không thuộc các khoảng trên |

**Đặc điểm của `$bucket`: cả cận trên cuối cùng cũng không được bao gồm.** Nếu một người viết pipeline muốn bao gồm giá `1000`, cần có cận trên lớn hơn nó, hoặc một chính sách phân loại ngoài miền. Đây là khác biệt quan trọng với cách hiển thị của `$bucketAuto` được trình bày sau.

Các giá trị kiểu BSON khác với ranh giới, như String và null, cũng cần được xử lý rõ ràng; không mặc định coi chúng là một giá trị số hợp lệ.

## 3. Cú pháp `$bucket`

Hình thức chung:

```javascript
{
  $bucket: {
    groupBy: <expression>,
    boundaries: [<first>, <second>, ..., <last>],
    default: <defaultBucketId>,
    output: {
      <name1>: { <accumulator1>: <expression1> },
      <name2>: { <accumulator2>: <expression2> }
    }
  }
}
```

Các thuộc tính:

| Thuộc tính | Ý nghĩa | Bắt buộc |
|---|---|---|
| `groupBy` | Biểu thức tính giá trị cần chia khoảng cho mỗi document | Có |
| `boundaries` | Các cận, theo thứ tự **tăng nghiêm ngặt**, ít nhất hai giá trị | Có |
| `default` | Giá trị `_id` của bucket nhận các input ngoài phạm vi | Không |
| `output` | Accumulator dùng để tính thông tin mỗi bucket | Không |

Mảng `boundaries` có `N+1` phần tử tạo tối đa `N` khoảng xác định trước. Ví dụ `[0,100,300]` tạo **hai bucket** `[0,100)` và `[100,300)`, không phải ba.

Các ranh giới phải thỏa quy tắc về kiểu BSON và thứ tự MongoDB yêu cầu: thông thường cùng kiểu, có ngoại lệ được phép pha trộn những kiểu thuộc nhóm numeric. Với dữ liệu tiền, nên dùng cùng một kiểu như Decimal128 cho các cận để tránh nhầm về độ chính xác và đơn vị.

### 3.1. Hình dạng đầu ra

Mỗi document output của `$bucket` đại diện một khoảng có dữ liệu. Field `_id` là **cận dưới** của khoảng; với những document ngoài phạm vi, `_id` là giá trị `default`.

Ví dụ:

```javascript
{
  _id: NumberDecimal("100"),
  count: 3
}
```

nghĩa là bucket có cận dưới bằng 100. Cận trên không xuất hiện mặc định trong `_id`; ứng dụng cần biết nó từ cấu hình boundaries tương ứng.

Khi bỏ `output`, MongoDB dùng mặc định tương đương:

```javascript
output: {
  count: { $sum: 1 }
}
```

Nếu muốn nhiều thống kê hơn số đếm, khai báo `output` rõ ràng.

## 4. Thực hành `$bucket`: thống kê sản phẩm theo giá

Ví dụ sau chia sản phẩm thành bốn phân khúc và một nhóm ngoài phạm vi:

```javascript
db.bucketLabProducts.aggregate([
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      default: "OTHER",
      output: {
        productCount: { $sum: 1 },
        productIds: { $push: "$_id" }
      }
    }
  }
]);
```

Phân nhóm theo nội dung dữ liệu:

| `_id` bucket | Khoảng/ý nghĩa | Các sản phẩm | Số lượng |
|---|---|---|---:|
| `0` | `[0,100)` | P01, P02 | 2 |
| `100` | `[100,300)` | P03, P04, P05 | 3 |
| `300` | `[300,600)` | P06, P07, P08 | 3 |
| `600` | `[600,1000)` | P09, P10 | 2 |
| `"OTHER"` | Ngoài miền hoặc không thuộc các khoảng số đã định | P11, P12, P13, P14, P15 | 5 |

Thứ tự các ID bên trong mảng do `$push` tạo ra không nên được xem là thứ tự đã cam kết nếu pipeline không chủ động thiết kế cách sắp xếp.

### 4.1. Vì sao P11 có giá 1000 đi vào OTHER?

Bucket cuối là `[600,1000)`, nên `1000` **bằng cận trên bị loại**, còn `1200` lớn hơn cận trên. P15 có giá âm nằm dưới cận nhỏ nhất. P13 có giá null, P14 thiếu giá; chúng không thuộc các khoảng numeric đang xét.

`default: "OTHER"` gom những document này vào một output. Điều đó **không** cho biết chúng thuộc cùng một nguyên nhân. Trong báo cáo nghiêm ngặt, cần phân biệt giá cao hợp lệ, giá âm bất thường và giá thiếu/null.

### 4.2. Nếu không khai báo `default`

```javascript
db.bucketLabProducts.aggregate([
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: { count: { $sum: 1 } }
    }
  }
]);
```

Vì tập dữ liệu có những input nằm ngoài các khoảng, `$bucket` **báo lỗi** khi không có bucket mặc định để chứa chúng. Đây là khác biệt với việc tự động bỏ các document không khớp.

Có hai lựa chọn thiết kế:

- Khai báo `default` để vẫn ghi nhận những document ngoài miền.
- Dùng `$match` **lọc input hợp lệ trong miền trước** `$bucket` khi nghiệp vụ chỉ muốn thống kê tập đó.

Ví dụ lọc những giá số không âm và nhỏ hơn 1000:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: { count: { $sum: 1 } }
    }
  }
]);
```

Trên schema học tập này, `price` là scalar. Query `$type: "number"` hướng tới các kiểu BSON numeric. Với dữ liệu có array phức tạp, cần kiểm soát kiểu thật của field để tránh những điều kiện query match các phần tử khác nhau theo cách không mong muốn.

### 4.3. Một record chỉ thuộc một bucket

Khi `price = 300`, nó thuộc `[300,600)`, **không** đồng thời thuộc `[100,300)`. Việc dùng cận dưới bao gồm và cận trên không bao gồm giúp các khoảng kề nhau không bị chồng lặp.

Nhờ vậy, với tập giá trị hợp lệ đã lọc và các khoảng phủ toàn miền, tổng `count` của các bucket bằng số document input.

## 5. Tính nhiều chỉ số trong mỗi bucket

`$bucket` hỗ trợ các accumulator quen thuộc của aggregation như `$sum`, `$avg`, `$min`, `$max` và `$push`.

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: {
        productCount: { $sum: 1 },
        stockUnits: { $sum: "$stock" },
        averagePrice: { $avg: "$price" },
        lowestActualPrice: { $min: "$price" },
        highestActualPrice: { $max: "$price" }
      }
    }
  }
]);
```

Ý nghĩa:

- `productCount`: số document thuộc bucket.
- `stockUnits`: tổng số sản phẩm tồn kho theo số đơn vị.
- `averagePrice`: giá trung bình của những document trong bucket.
- `lowestActualPrice`: giá nhỏ nhất thực tế có trong bucket.
- `highestActualPrice`: giá lớn nhất thực tế có trong bucket.

**Giá nhỏ nhất thực tế không nhất thiết bằng cận dưới**, và giá lớn nhất thực tế không nhất thiết bằng cận trên. Ví dụ `[100,300)` có thể chỉ chứa các giá 180 và 299, nhưng vẫn có `_id` bucket bằng 100.

### 5.1. Giá trị tồn kho theo từng khoảng

Nếu cần số tiền tương ứng với tồn kho:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      },
      stock: { $type: "number" }
    }
  },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: {
        productCount: { $sum: 1 },
        inventoryValue: {
          $sum: {
            $multiply: ["$price", "$stock"]
          }
        }
      }
    }
  }
]);
```

`$multiply` tính giá trị tồn kho của từng document, rồi `$sum` cộng trong bucket. Với nghiệp vụ tiền tệ, phải thống nhất kiểu số và đơn vị tiền; nếu `price` tính bằng nghìn đồng thì tổng tính ra cũng theo nghìn đồng.

### 5.2. Không nên `$push` toàn bộ document trong bucket lớn

```javascript
output: {
  allProducts: { $push: "$$ROOT" }
}
```

Cách này có thể tạo một document output chứa mảng rất lớn, tốn RAM và có nguy cơ vượt giới hạn kích thước BSON document. Một histogram thường chỉ cần **thống kê**, không phải chuyển cả collection thành vài array lớn.

Nếu muốn lấy một vài document đại diện, hãy thiết kế cách lấy mẫu/giới hạn riêng theo tính năng và phiên bản MongoDB phù hợp.

## 6. Quy tắc boundaries và các lỗi phổ biến

### 6.1. Các cận phải tăng nghiêm ngặt

Hợp lệ:

```javascript
boundaries: [0, 100, 300, 1000]
```

Không hợp lệ:

```javascript
// Có hai giá trị bằng nhau.
boundaries: [0, 100, 100, 300]

// Không theo thứ tự tăng.
boundaries: [0, 300, 100, 1000]

// Chỉ có một mốc, không tạo được khoảng.
boundaries: [0]
```

Không thể tạo một bucket `[100,100)` để gom những giá đúng bằng 100. Nếu muốn nhóm theo từng giá trị rời rạc, `$group` thường phù hợp hơn.

### 6.2. Cận trên cuối cũng bị loại

Với:

```javascript
boundaries: [0, 100, 300]
```

chỉ có `[0,100)` và `[100,300)`. Giá `300` **không thuộc bucket thứ hai**. Nếu business muốn bao gồm 300, phải định nghĩa cận trên lớn hơn hoặc một quy tắc xử lý đặc biệt.

Đừng tự động cộng 1 vào cận cuối khi giá có thể là số thập phân: `300.50` và `300.99` có thể xuất hiện, nên “cộng 1” chỉ hợp lý khi đã xác định độ phân giải đơn vị và miền hợp lệ.

### 6.3. Chọn kiểu dữ liệu nhất quán

Nếu `price` là Decimal128, nên dùng Decimal128 cho boundaries:

```javascript
boundaries: [
  NumberDecimal("0"),
  NumberDecimal("100"),
  NumberDecimal("300"),
  NumberDecimal("1000")
]
```

MongoDB có quy tắc cho sự kết hợp các kiểu số BSON trong boundaries, nhưng không nên trộn Date và Number hoặc dùng String chứa số làm boundary rồi kỳ vọng so sánh theo ý nghĩa số học.

### 6.4. Bucket rỗng không tự có document count 0

Ví dụ dữ liệu chỉ có giá 50 và 850, boundaries `[0,100,300,600,1000]`. MongoDB có thể chỉ trả:

```javascript
{ _id: 0, count: 1 }
{ _id: 600, count: 1 }
```

Hai khoảng `[100,300)` và `[300,600)` không có document nên **không được xuất như những hàng count 0 mặc định**.

Nếu dashboard phải hiển thị đủ bốn cột, tầng ứng dụng có thể ghép kết quả với cấu hình boundaries đã biết và điền 0 cho những khoảng vắng mặt.

### 6.5. `default` không phải một khoảng liên tục

`default: "OTHER"` có thể gom cả giá âm, giá vượt cận trên, null và missing. Nó không đại diện một khoảng số có cận dưới/cận trên duy nhất. Khi vẽ histogram, có thể hiển thị OTHER như một thông tin riêng “Ngoài phạm vi hoặc dữ liệu không hợp lệ”, không nhất thiết đặt nó thành một cột cùng độ rộng với các khoảng số.

## 7. Phân loại dữ liệu bẩn trước khi tạo histogram

Giả sử nhiều document legacy chứa:

```javascript
[
  { price: NumberDecimal("125.50") },
  { price: "125.50" },
  { price: "không có" },
  { price: null },
  {}
]
```

Nếu chia khoảng mà không chuẩn hóa, các String không tự thành Number. Dùng `$convert` có `onError` và `onNull` để xử lý:

```javascript
db.legacyProducts.aggregate([
  {
    $set: {
      normalizedPrice: {
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
      normalizedPrice: {
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$normalizedPrice",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: { count: { $sum: 1 } }
    }
  }
]);
```

Pipeline trên chỉ tính **những record chuyển được và nằm trong phạm vi**. Nó không tính các record invalid hoặc missing vào một bucket. Đây là chính sách hợp lệ cho một báo cáo cụ thể, nhưng nếu tên báo cáo là “phân bố tất cả sản phẩm” thì phải công khai số lượng bị loại.

### 7.1. Đếm record không hợp lệ riêng

```javascript
db.legacyProducts.aggregate([
  {
    $project: {
      price: 1,
      sourceType: { $type: "$price" },
      normalizedPrice: {
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
    $set: {
      quality: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$sourceType", "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: ["$sourceType", "null"] },
              then: "NULL"
            },
            {
              case: { $eq: ["$normalizedPrice", null] },
              then: "INVALID"
            },
            {
              case: {
                $lt: ["$normalizedPrice", NumberDecimal("0")]
              },
              then: "NEGATIVE"
            }
          ],
          default: "VALID"
        }
      }
    }
  },
  {
    $group: {
      _id: "$quality",
      count: { $sum: 1 }
    }
  }
]);
```

Như vậy, báo cáo có thể có hai phần: histogram giá hợp lệ và bảng chất lượng dữ liệu đầu vào. Cách này tốt hơn việc lặng lẽ coi giá lỗi là 0, vì 0 có thể là một giá trị kinh doanh hợp lệ.

## 8. Chia khoảng thời gian bằng `$bucket`

`groupBy` không nhất thiết là số. Nếu dữ liệu là BSON Date, có thể chia theo ranh giới Date.

Ví dụ thống kê sản phẩm được tạo trong quý I năm 2026:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      createdAt: {
        $gte: ISODate("2026-01-01T00:00:00Z"),
        $lt: ISODate("2026-04-01T00:00:00Z")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$createdAt",
      boundaries: [
        ISODate("2026-01-01T00:00:00Z"),
        ISODate("2026-02-01T00:00:00Z"),
        ISODate("2026-03-01T00:00:00Z"),
        ISODate("2026-04-01T00:00:00Z")
      ],
      output: {
        productsCreated: { $sum: 1 }
      }
    }
  }
]);
```

Ba khoảng:

```text
[2026-01-01, 2026-02-01)
[2026-02-01, 2026-03-01)
[2026-03-01, 2026-04-01)
```

Một sản phẩm tạo đúng `2026-03-01T00:00:00Z` nằm ở bucket tháng 3, không phải tháng 2.

### 8.1. Tháng lịch không có số ngày cố định

Nếu cần nhóm theo tháng, không nên chia timestamp thành các khoảng `30 × 24 giờ` rồi gọi tất cả là “tháng”. Tháng có 28, 29, 30 hoặc 31 ngày. Sử dụng Date boundaries phù hợp hoặc `$dateTrunc` để xác định đầu tháng theo timezone.

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$orderedAt",
          unit: "month",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

`$dateTrunc` + `$group` phù hợp khi cần báo cáo tháng tự động qua nhiều năm; `$bucket` phù hợp khi báo cáo phải dùng đúng một tập Date boundaries đã chốt.

### 8.2. Timezone có thể làm lệch bucket

`ISODate("2026-03-01T00:00:00Z")` là nửa đêm UTC, không phải nửa đêm giờ Việt Nam. Một sự kiện lúc 00:30 giờ Việt Nam ngày 1/3 vẫn có ngày UTC là 28/2. Nếu doanh nghiệp định nghĩa “tháng” theo giờ Việt Nam, phải tính ranh giới UTC tương ứng hoặc dùng biểu thức thời gian có `timezone`.

**Ranh giới thời gian là quy tắc nghiệp vụ**, không chỉ là định dạng ngày đẹp để hiển thị.

## 9. Phân nhóm bằng biểu thức tính toán

`groupBy` nhận aggregation expression. Có thể chia các document theo **kết quả tính** từ những trường khác.

Ví dụ tập `orderLines` có `unitPrice` và `quantity`:

```javascript
db.orderLines.aggregate([
  {
    $match: {
      unitPrice: { $type: "number" },
      quantity: { $type: "number" }
    }
  },
  {
    $bucket: {
      groupBy: {
        $multiply: ["$unitPrice", "$quantity"]
      },
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100000"),
        NumberDecimal("500000"),
        NumberDecimal("1000000")
      ],
      default: "OTHER",
      output: {
        lineCount: { $sum: 1 }
      }
    }
  }
]);
```

Đây là chia khoảng **tổng giá trị một dòng hàng**, không phải theo giá một đơn vị sản phẩm. Trước khi sử dụng, phải kiểm soát `quantity`, `unitPrice`, đơn vị tiền và kiểu số; nếu đầu vào có String sai định dạng, phép tính có thể lỗi.

Có thể tách biểu thức ra stage `$set` để dễ giải thích:

```javascript
db.orderLines.aggregate([
  {
    $set: {
      lineValue: {
        $multiply: ["$unitPrice", "$quantity"]
      }
    }
  },
  {
    $bucket: {
      groupBy: "$lineValue",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100000"),
        NumberDecimal("500000"),
        NumberDecimal("1000000")
      ],
      default: "OTHER",
      output: { count: { $sum: 1 } }
    }
  }
]);
```

Stage `$set` trong aggregation ở đây chỉ bổ sung một field trong **kết quả pipeline**, không tự ghi `lineValue` vào document gốc.

## 10. Khi cần `$group` thay vì `$bucket`

`$group` gom theo **giá trị khóa giống nhau**:

```javascript
db.bucketLabProducts.aggregate([
  {
    $group: {
      _id: "$category",
      productCount: { $sum: 1 }
    }
  }
]);
```

Ví dụ nhóm theo chính xác một giá:

```javascript
db.bucketLabProducts.aggregate([
  {
    $group: {
      _id: "$price",
      count: { $sum: 1 }
    }
  }
]);
```

Trường hợp trên tạo nhóm riêng cho giá 50, 90, 100,...; nó **không gom** mọi giá từ 0 đến dưới 100 vào chung một nhóm.

So sánh:

| Mục tiêu | Công cụ |
|---|---|
| Đếm theo exact status/category | `$group` |
| Giá rơi vào các khoảng fixed | `$bucket` |
| Chọn khoảng tự động theo phân bố | `$bucketAuto` |
| Nhãn nghiệp vụ phi liên tục, nhiều điều kiện | `$switch`/`$cond` rồi `$group` |
| Báo cáo ngày/tháng lịch theo timezone | `$dateTrunc` + `$group` |
| Nhiều thống kê độc lập từ cùng input | `$facet` |

Không nên ép mọi nhu cầu phân nhóm vào `$bucket` chỉ vì dữ liệu là số. Nếu cần nhóm các giá trị không liên tục, hoặc một nhãn phụ thuộc nhiều field, tính nhãn bằng `$switch` rồi `$group` thường linh hoạt hơn.

## 11. `$bucketAuto`: MongoDB tự xác định ranh giới

Cú pháp tổng quát:

```javascript
{
  $bucketAuto: {
    groupBy: <expression>,
    buckets: <positiveInteger>,
    output: {
      <fieldName>: { <accumulator>: <expression> }
    },
    granularity: <preferredNumberSeries>
  }
}
```

Các thuộc tính:

- `groupBy`: biểu thức xác định giá trị để xếp thành các bucket.
- `buckets`: **số bucket mong muốn**, phải là số nguyên dương.
- `output`: các accumulator của mỗi bucket, tương tự `$bucket`; mặc định là đếm.
- `granularity`: tùy chọn để làm ranh giới numeric theo một dãy số ưu tiên, ví dụ `"R5"`.

Điểm cốt lõi:

> `$bucketAuto` cố tạo những bucket có **số document tương đối cân bằng**, không cố tạo những khoảng có **độ rộng giá trị bằng nhau**.

Ví dụ:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0")
      }
    }
  },
  {
    $bucketAuto: {
      groupBy: "$price",
      buckets: 4,
      output: {
        productCount: { $sum: 1 },
        averagePrice: { $avg: "$price" },
        actualMin: { $min: "$price" },
        actualMax: { $max: "$price" }
      }
    }
  }
]);
```

Với 12 sản phẩm có giá numeric không âm trong dữ liệu thử, yêu cầu bốn bucket hướng tới khoảng ba sản phẩm mỗi nhóm, nhưng ranh giới và số record thực tế **phụ thuộc giá trị phân bố**. Không nên ghi sẵn những số cận tự động như thể chúng là hợp đồng cố định.

### 11.1. Hình dạng `_id` của `$bucketAuto`

`$bucket` có `_id` là một giá trị cận dưới. `$bucketAuto` khác:

```javascript
{
  _id: {
    min: NumberDecimal("..."),
    max: NumberDecimal("...")
  },
  productCount: 3
}
```

`min` và `max` ở đây là **ranh giới bucket**, không nhất thiết bằng min/max giá thực tế đã xuất hiện nếu dùng granularity. Nếu cần hai giá trị thực tế, dùng accumulator `$min` và `$max` riêng.

### 11.2. Quy tắc ranh giới của `$bucketAuto`

Các bucket tự động được mô tả bằng cận dưới và cận trên. Các bucket trung gian có cận dưới bao gồm và cận trên không bao gồm; **bucket cuối bao gồm cận trên** để có thể chứa giá trị cực đại.

Không áp dụng máy móc quy tắc của `$bucket` rằng *mọi* cận trên đều bị loại cho output của `$bucketAuto`. Khi biến ranh giới thành điều kiện truy vấn lại, phải hiểu đúng ngoại lệ của bucket cuối.

## 12. `$bucketAuto` không đảm bảo chính xác số bucket hoặc số record mỗi bucket

Giả sử có 100 document và yêu cầu:

```javascript
{
  $bucketAuto: {
    groupBy: "$price",
    buckets: 5
  }
}
```

Mục tiêu là gần 20 document/bucket, nhưng không phải cam kết tuyệt đối. Một số lý do:

1. Nhiều document có **cùng giá trị groupBy**.
2. Số distinct value có thể nhỏ hơn số bucket yêu cầu.
3. Không thể chia cùng một giá trị vào hai khoảng giá khác nhau chỉ để bằng số lượng.
4. `granularity` có thể dịch chuyển ranh giới để thành các mốc dễ đọc.

Ví dụ:

```text
Giá trị:
10, 10, 10, 10, 10, 10, 20, 20, 20, 30, 30, 30

Số distinct giá trị = 3
Số bucket yêu cầu    = 5
```

Không hợp lý khi hứa tạo năm **khoảng giá khác nhau** mà vẫn giữ toàn bộ các giá trị bằng nhau được phân vào một khoảng thống nhất. `$bucketAuto` có thể tạo **ít bucket hơn** hoặc nhóm có số document khác nhau rõ rệt.

### 12.1. Số lượng gần đều không có nghĩa khoảng rộng gần đều

Ví dụ:

```text
10, 11, 12, 13, 14, 15, 16, 17, 18, 1000, 5000, 15000
```

Để chia dữ liệu thành bốn bucket có số document gần nhau, các bucket vùng 10–18 sẽ **hẹp**, trong khi bucket chứa vùng 1000–15000 có thể **rất rộng**.

Nếu biểu đồ hiển thị trục giá với độ rộng thực, những cột sẽ không đều nhau. Nếu biểu đồ chỉ hiển thị “Bucket 1–4” có chiều rộng cột giống nhau, phải ghi rõ cột đại diện **các khoảng giá khác độ rộng**.

### 12.2. Nhãn “25%, 50%, 75%” cần cẩn trọng

`buckets: 4` gợi ý chia thành các phân vị gần một phần tư document. Nhưng nếu nhiều giá trùng, không nhất thiết có đúng 25% record trong mỗi bucket. Nên tính và trình bày **tỷ lệ quan sát thực** chứ không chỉ in nhãn “Quartile 1–4” mà không kiểm tra số lượng.

## 13. Granularity: tạo ranh giới số dễ đọc

Một số ranh giới tự động có thể có nhiều chữ số thập phân, làm nhãn trên biểu đồ khó hiểu. `$bucketAuto` hỗ trợ tùy chọn `granularity` với các dãy số ưu tiên.

Ví dụ:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gt: NumberDecimal("0")
      }
    }
  },
  {
    $bucketAuto: {
      groupBy: "$price",
      buckets: 4,
      granularity: "R5",
      output: {
        count: { $sum: 1 },
        avgPrice: { $avg: "$price" }
      }
    }
  }
]);
```

`"R5"` là một dãy số ưu tiên có mốc dễ trình bày. Khi chọn granularity:

- Input phải phù hợp với **kiểu số** và điều kiện của dãy số; phần lớn những dãy số ưu tiên đòi input dương, còn trường hợp zero có quy tắc riêng theo dãy và phiên bản.
- Granularity **không sửa giá trị price được lưu**; nó ảnh hưởng tới việc chọn mốc biên.
- Các mốc được làm “đẹp” có thể khiến số document giữa bucket kém cân bằng hơn.
- Không dùng granularity số như một phép nhóm Date theo tuần hoặc tháng.

Nếu doanh nghiệp muốn **chính xác** mốc 100, 300 và 1000, hãy dùng `$bucket` thay vì hy vọng `$bucketAuto` với granularity tự sinh đúng các mốc đó.

## 14. `$bucket` so với `$bucketAuto`

| Tiêu chí | `$bucket` | `$bucketAuto` |
|---|---|---|
| Ai chọn ranh giới? | Người viết pipeline | MongoDB dựa trên phân bố |
| Tham số bắt buộc nổi bật | `boundaries` | `buckets` |
| Mục tiêu | Khoảng cố định | Số record mỗi bucket tương đối cân bằng |
| Độ rộng khoảng | Theo boundaries; có thể bằng hoặc khác nhau | Không được đảm bảo |
| Số document/bucket | Có thể lệch rất lớn | Cố gắng cân bằng nhưng không tuyệt đối |
| Số bucket trả về | Chỉ nhóm có dữ liệu, cộng default nếu xuất hiện | Có thể ít hơn số yêu cầu |
| `_id` output | Cận dưới hoặc giá trị default | Object `{ min, max }` |
| Cận trên cuối | Không bao gồm | Bucket cuối có cận trên bao gồm |
| Input ngoài khoảng | `default` hoặc lỗi | Tự xác định miền từ input |
| Có granularity | Không | Có |
| Ranh giới có đổi khi dữ liệu tăng? | Không, nếu cấu hình không đổi | Có thể đổi |
| Dùng cho phân khúc nghiệp vụ | Rất phù hợp | Chỉ phù hợp nếu nhãn không phải thang cố định |
| Khám phá dữ liệu chưa biết ngưỡng | Cần quyết định ngưỡng trước | Phù hợp |

**Khác biệt mang tính sản phẩm:** Nếu tháng trước bucket số 2 có khoảng `[100,200)` và tháng này bucket số 2 thành `[120,260)`, so sánh số lượng bucket số 2 giữa hai tháng là **không cùng một miền giá**.

## 15. Thiết kế biểu đồ ổn định qua nhiều kỳ

Đối với dashboard dùng qua nhiều tháng:

```text
Tháng 1: [0,100), [100,300), [300,600), [600,1000)
Tháng 2: [0,100), [100,300), [300,600), [600,1000)
Tháng 3: [0,100), [100,300), [300,600), [600,1000)
```

Cùng một `_id` bucket luôn mang cùng ý nghĩa. Điều này giúp so sánh xu hướng.

Với `$bucketAuto`, khi phân bố thay đổi:

```text
Tháng 1:
  Bucket A [10,40)
  Bucket B [40,80)
  ...

Tháng 2:
  Bucket A [10,50)
  Bucket B [50,95)
  ...
```

Các số trên chỉ minh họa hiện tượng ranh giới dịch chuyển. Một sản phẩm không đổi giá vẫn có thể nằm ở nhóm tương đối khác sau khi danh mục thay đổi.

**Quy trình thường hợp lý:**

1. Dùng `$bucketAuto` trên dữ liệu đại diện để khám phá phân bố.
2. Thảo luận với nghiệp vụ để chọn ngưỡng có ý nghĩa.
3. Lưu boundaries cùng **phiên bản phân khúc**.
4. Dùng `$bucket` để báo cáo lặp lại với cùng ngưỡng.
5. Khi đổi boundaries, ghi version mới và tránh trộn so sánh lịch sử không tương đương.

Nếu mục tiêu thật sự là theo dõi **vị trí phân vị** thay vì nhóm giá cố định, `$bucketAuto` vẫn phù hợp, nhưng dashboard phải hiển thị rõ min/max của từng bucket ở từng kỳ.

## 16. Tính tỷ lệ phần trăm theo bucket

Sau khi có số document trong mỗi bucket, có thể tính tỷ lệ trên **tập input đã lọc**.

Ví dụ:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$price",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("300"),
        NumberDecimal("600"),
        NumberDecimal("1000")
      ],
      output: { count: { $sum: 1 } }
    }
  },
  {
    $group: {
      _id: null,
      buckets: {
        $push: {
          lowerBound: "$_id",
          count: "$count"
        }
      },
      totalCount: { $sum: "$count" }
    }
  },
  { $unwind: "$buckets" },
  {
    $project: {
      _id: 0,
      lowerBound: "$buckets.lowerBound",
      count: "$buckets.count",
      totalCount: 1,
      percent: {
        $cond: [
          { $gt: ["$totalCount", 0] },
          {
            $multiply: [
              {
                $divide: [
                  "$buckets.count",
                  "$totalCount"
                ]
              },
              100
            ]
          },
          null
        ]
      }
    }
  },
  { $sort: { lowerBound: 1 } }
]);
```

**Mẫu số `totalCount`** ở đây là số sản phẩm có giá numeric trong `[0,1000)`, không phải số tất cả sản phẩm trong collection. Nếu cần tỷ lệ trên toàn bộ danh mục, phải đưa các document giá ngoài khoảng/null/missing vào mẫu số theo đúng quy tắc nghiệp vụ.

Nếu query đầu vào không có document, pipeline có thể không tạo output bucket; API cần xử lý trường hợp kết quả rỗng thay vì giả định luôn có đủ bốn dòng và một total dương.

## 17. Kết hợp với `$facet` để có nhiều góc nhìn

Một màn hình phân tích có thể muốn đồng thời:

- Histogram theo thang giá chính thức;
- Bốn nhóm giá tự động;
- Giá thấp nhất, cao nhất và trung bình.

`$facet` cho phép nhiều pipeline con xử lý cùng input sau bộ lọc:

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0")
      }
    }
  },
  {
    $facet: {
      fixedRanges: [
        {
          $bucket: {
            groupBy: "$price",
            boundaries: [
              NumberDecimal("0"),
              NumberDecimal("100"),
              NumberDecimal("300"),
              NumberDecimal("600"),
              NumberDecimal("1000")
            ],
            default: "ABOVE_RANGE",
            output: {
              count: { $sum: 1 }
            }
          }
        }
      ],
      autoRanges: [
        {
          $bucketAuto: {
            groupBy: "$price",
            buckets: 4,
            output: {
              count: { $sum: 1 },
              averagePrice: { $avg: "$price" }
            }
          }
        }
      ],
      overall: [
        {
          $group: {
            _id: null,
            totalProducts: { $sum: 1 },
            minPrice: { $min: "$price" },
            maxPrice: { $max: "$price" },
            averagePrice: { $avg: "$price" }
          }
        }
      ]
    }
  }
]);
```

Kết quả có một document chứa các mảng `fixedRanges`, `autoRanges`, `overall`.

**Lưu ý:** `$match` nằm trước `$facet` đã loại null/missing/âm, vì vậy `overall.totalProducts` chỉ đếm **giá hợp lệ theo filter**. Nếu còn muốn đếm lỗi dữ liệu, có thể đặt một `$facet` nhận toàn bộ input và lọc khác nhau ở từng nhánh. Đừng lọc bỏ dữ liệu lỗi **trước** nhánh có trách nhiệm báo cáo lỗi.

### 17.1. Giới hạn bộ nhớ và kích thước output

`$facet` không phải cách miễn phí để chạy vô hạn biểu đồ. Những nhánh có `$bucketAuto`, `$group`, `$push` hoặc quá nhiều output có thể gây áp lực bộ nhớ/disk. Một document output tổng của `$facet` vẫn chịu giới hạn BSON và các giới hạn stage tương ứng. Với dashboard nhiều request, nên đo thực tế và cân nhắc pre-aggregation.

## 18. Phân tích theo độ tuổi hoặc điểm số

Một ví dụ khác: nhóm học sinh theo điểm thi.

```javascript
db.examResults.aggregate([
  {
    $match: {
      score: {
        $type: "number",
        $gte: 0,
        $lte: 100
      }
    }
  },
  {
    $bucket: {
      groupBy: "$score",
      boundaries: [0, 50, 65, 80, 90, 101],
      output: {
        studentCount: { $sum: 1 },
        averageScore: { $avg: "$score" }
      }
    }
  }
]);
```

Cận trên 101 cho phép nhóm cuối bao gồm score 100 nếu điểm được giới hạn tối đa là 100. Nhưng về ngữ nghĩa, bucket cuối là `[90,101)`, **không tự xác nhận** điểm 100.5 là hợp lệ. Filter `score <= 100` đang bảo vệ domain; cần mô tả điều này trong báo cáo.

Nếu muốn chia thành bốn nhóm phân vị tương đối thay vì nhóm điểm chính thức:

```javascript
db.examResults.aggregate([
  {
    $match: {
      score: { $type: "number" }
    }
  },
  {
    $bucketAuto: {
      groupBy: "$score",
      buckets: 4,
      output: {
        studentCount: { $sum: 1 },
        minActualScore: { $min: "$score" },
        maxActualScore: { $max: "$score" }
      }
    }
  }
]);
```

Nếu nhiều học sinh cùng điểm, số record giữa các bucket có thể chênh lệch. Không dùng kết quả auto để thay thế thang đậu/rớt hoặc xếp loại chính thức có ngưỡng được quy định trước.

### 18.1. Chia nhóm tuổi bằng biểu thức

```javascript
db.members.aggregate([
  {
    $match: {
      birthDate: { $type: "date" }
    }
  },
  {
    $set: {
      ageYears: {
        $dateDiff: {
          startDate: "$birthDate",
          endDate: "$$NOW",
          unit: "year",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  },
  {
    $bucket: {
      groupBy: "$ageYears",
      boundaries: [0, 18, 25, 35, 50, 120],
      default: "OTHER",
      output: {
        memberCount: { $sum: 1 }
      }
    }
  }
]);
```

`$dateDiff` tính khoảng theo đơn vị year theo quy tắc của MongoDB. Nếu báo cáo cần tuổi **tại ngày chốt** thay vì tuổi khi chạy query, dùng một BSON Date chốt trước thay cho `$$NOW` để kết quả ổn định giữa các lần chạy. Với yêu cầu pháp lý về ngày sinh/ngày nhuận, cần đối chiếu quy tắc tuổi cụ thể.

## 19. Nhóm theo nhiều chiều: khi một bucket chưa đủ

`$bucket` phân chia theo một biểu thức groupBy trong một stage. Nếu cần thống kê **giá × category**, có thể tạo nhãn khoảng bằng `$switch` rồi `$group` theo cặp giá/category.

```javascript
db.bucketLabProducts.aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0"),
        $lt: NumberDecimal("1000")
      }
    }
  },
  {
    $set: {
      priceBand: {
        $switch: {
          branches: [
            {
              case: {
                $lt: ["$price", NumberDecimal("100")]
              },
              then: "UNDER_100"
            },
            {
              case: {
                $lt: ["$price", NumberDecimal("300")]
              },
              then: "100_TO_299"
            },
            {
              case: {
                $lt: ["$price", NumberDecimal("600")]
              },
              then: "300_TO_599"
            }
          ],
          default: "600_TO_999"
        }
      }
    }
  },
  {
    $group: {
      _id: {
        band: "$priceBand",
        category: "$category"
      },
      count: { $sum: 1 }
    }
  },
  {
    $sort: {
      "_id.band": 1,
      "_id.category": 1
    }
  }
]);
```

Đây là một giải pháp khi cần nhóm **hai chiều**. Nhưng nếu một báo cáo dùng `$bucket` và báo cáo khác dùng `$switch` cho cùng thang giá, nên quản lý boundaries tập trung/phiên bản để không vô tình dùng ngưỡng 300 ở nơi này và 299 ở nơi khác.

## 20. Hiệu năng và index

Cả `$bucket` và `$bucketAuto` cần xử lý những document đầu vào. Một histogram chỉ trả bốn dòng **không đồng nghĩa server chỉ đọc bốn document**.

### 20.1. `$match` sớm để giảm input

Ví dụ báo cáo đơn hàng của một tenant và một khoảng thời gian:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: "PAID",
      orderedAt: {
        $gte: ISODate("2026-01-01T00:00:00Z"),
        $lt: ISODate("2026-07-01T00:00:00Z")
      }
    }
  },
  {
    $bucket: {
      groupBy: "$total",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100000"),
        NumberDecimal("500000"),
        NumberDecimal("1000000")
      ],
      default: "OTHER",
      output: {
        orderCount: { $sum: 1 }
      }
    }
  }
]);
```

Một index ứng viên:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  orderedAt: 1
});
```

Index có thể hỗ trợ `$match` theo tenant/status/range, giúp giảm số document đi tới stage bucket. Nhưng nó **không tự làm toàn bộ việc tổng hợp trở nên miễn phí**.

### 20.2. `$bucketAuto` cần hiểu phân bố toàn tập đầu vào

`$bucketAuto` phải xác định ranh giới theo giá trị của những document đi qua stage. Nếu pipeline đầu vào có hàng chục triệu record, việc phân bố và xử lý bucket có thể dùng CPU/RAM/disk đáng kể.

Nếu một dashboard rất nhiều người xem liên tục yêu cầu cùng một histogram:

- Cân nhắc tạo collection thống kê định kỳ;
- Sử dụng cache với TTL và quy tắc invalidation;
- Giới hạn scope theo tenant/thời gian/status;
- Dùng bucket cố định khi business cho phép;
- Cân nhắc sampling khi chấp nhận sai số và công khai mức xấp xỉ.

Không chạy `$bucketAuto` trên toàn bộ hệ thống cho mỗi lần client thay đổi một option giao diện mà chưa đánh giá quy mô, throughput và SLA.

### 20.3. Memory limits và allowDiskUse

Các stage aggregation liên quan grouping/sorting/bucketing có giới hạn tài nguyên. Trong những phiên bản/cấu hình hỗ trợ, `allowDiskUse: true` cho phép những stage có cơ chế spill ghi tạm ra disk khi cần:

```javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "TENANT-A",
        status: "PAID"
      }
    },
    {
      $bucketAuto: {
        groupBy: "$total",
        buckets: 10,
        output: {
          count: { $sum: 1 },
          averageTotal: { $avg: "$total" }
        }
      }
    }
  ],
  { allowDiskUse: true }
);
```

`allowDiskUse` **không xóa mọi giới hạn**: vẫn có chi phí I/O, giới hạn của stage và giới hạn kích thước một document BSON. Cần theo dõi query chậm, spill, CPU, RAM và disk usage.

### 20.4. Phân tích bằng explain

```javascript
db.bucketLabProducts.explain("executionStats").aggregate([
  {
    $match: {
      price: {
        $type: "number",
        $gte: NumberDecimal("0")
      }
    }
  },
  {
    $bucketAuto: {
      groupBy: "$price",
      buckets: 4,
      output: {
        count: { $sum: 1 }
      }
    }
  }
]);
```

Các thông tin cần xem:

| Chỉ số hoặc stage | Ý nghĩa |
|---|---|
| `winningPlan` | Planner chọn cách đọc nào |
| `IXSCAN` | Có dùng index không |
| `COLLSCAN` | Có quét collection không |
| `FETCH` | Có đọc document ngoài index không |
| `totalDocsExamined` | Số document đã xem |
| `totalKeysExamined` | Số index key đã duyệt |
| Sort/group/spill metrics | Chi phí tạo bucket |
| `nReturned` | Số kết quả ở tầng thống kê tương ứng |

Cấu trúc explain khác theo phiên bản/query engine. Một pipeline đọc hàng triệu document nhưng chỉ trả năm bucket không thể được đánh giá là “rẻ” chỉ bởi output có năm dòng.

## 21. Histogram cần cột bằng 0

Với boundaries cố định:

```javascript
const expectedBuckets = [
  { min: 0, max: 100, label: "Dưới 100" },
  { min: 100, max: 300, label: "100–dưới 300" },
  { min: 300, max: 600, label: "300–dưới 600" },
  { min: 600, max: 1000, label: "600–dưới 1000" }
];
```

Ứng dụng có thể nhận kết quả `$bucket`, lấy `_id` làm lower bound, ghép với `expectedBuckets` và điền `count: 0` cho những bucket không có document.

Ví dụ response:

```javascript
[
  { min: 0, max: 100, count: 15 },
  { min: 100, max: 300, count: 0 },
  { min: 300, max: 600, count: 7 },
  { min: 600, max: 1000, count: 12 }
]
```

Đây là việc bổ sung **hình dạng báo cáo cố định**, không thay đổi số liệu gốc. Với Date/Decimal128, cần so sánh theo đúng kiểu và cùng đơn vị khi nối kết quả.

`default` như `"OTHER"` nên được hiển thị riêng vì nó không có độ rộng giá trị xác định.

## 22. Cần snapshot không khi dữ liệu thay đổi?

Nếu chạy `$bucketAuto` sáng nay và chiều nay, trong khi hàng nghìn sản phẩm mới được thêm, ranh giới có thể đổi. Đây là hành vi **đúng với mục tiêu phân bố dữ liệu hiện tại**.

Nếu cần một báo cáo “tại 00:00 ngày cuối tháng”:

- Phải xác định thời điểm chốt;
- Dùng read concern/snapshot hoặc tập dữ liệu bất biến phù hợp với yêu cầu nhất quán;
- Không suy từ việc có một histogram rằng mọi lần đọc sau đều nhìn cùng snapshot;
- Không coi `readConcern: "majority"` trên nhiều request là bảo đảm một snapshot cố định xuyên các request.

Với `$bucket`, boundaries có thể giữ nguyên, nhưng **số liệu vẫn thay đổi** nếu tập input thay đổi. Một dashboard dùng bucket cố định chỉ đảm bảo **ý nghĩa của khoảng ổn định**, không đảm bảo count bất biến.

## 23. Dùng từ Java MongoDB Driver

MongoDB Java Sync Driver có thể xây dựng stage bucket bằng API builders hoặc bằng BSON `Document`. Ví dụ sau dùng `Document` để thể hiện rõ cấu trúc.

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

MongoCollection<Document> products =
    database.getCollection("bucketLabProducts");

List<Decimal128> boundaries = Arrays.asList(
    new Decimal128(new BigDecimal("0")),
    new Decimal128(new BigDecimal("100")),
    new Decimal128(new BigDecimal("300")),
    new Decimal128(new BigDecimal("600")),
    new Decimal128(new BigDecimal("1000"))
);

Document bucket = new Document(
    "$bucket",
    new Document("groupBy", "$price")
        .append("boundaries", boundaries)
        .append("default", "OTHER")
        .append(
            "output",
            new Document("count", new Document("$sum", 1))
                .append("stockUnits", new Document("$sum", "$stock"))
        )
);

for (Document result : products.aggregate(Arrays.asList(bucket))) {
    System.out.println(result.toJson());
}
```

Ví dụ `$bucketAuto`:

```java
Document bucketAuto = new Document(
    "$bucketAuto",
    new Document("groupBy", "$price")
        .append("buckets", 4)
        .append(
            "output",
            new Document("count", new Document("$sum", 1))
        )
);

for (Document result : products.aggregate(
        Arrays.asList(bucketAuto))) {
    System.out.println(result.toJson());
}
```

Ví dụ auto nên được thêm `$match`/validation khi collection chứa null/missing hoặc những giá trị không thuộc miền cần phân tích. Khi xử lý Decimal128 ở Java, DTO phải dùng kiểu phù hợp như `BigDecimal` qua ánh xạ được cấu hình, không tự chuyển mọi giá trị tiền sang `double` nếu cần chính xác.

### 23.1. DTO của hai stage khác nhau

Với `$bucket`:

```javascript
{ _id: NumberDecimal("100"), count: 25 }
```

Với `$bucketAuto`:

```javascript
{
  _id: {
    min: NumberDecimal("100"),
    max: NumberDecimal("250")
  },
  count: 25
}
```

Hai dạng `_id` **không tương đương**. API cần quyết định có chuẩn hóa cả hai thành `{min,max,count}` hay giữ hai response schema riêng. `$bucket` không tự trả `max`; muốn biết cận trên, phải lấy từ cấu hình boundaries đã dùng.

## 24. Những lỗi thường gặp

| Sai lầm | Hậu quả | Giải pháp |
|---|---|---|
| Nghĩ có N boundaries sẽ có N bucket | Thực tế N cận tạo N-1 khoảng | Đếm các cặp ranh giới liên tiếp |
| Nghĩ giá đúng 100 nằm trong `[0,100)` | Phân loại sai | Cận dưới bao gồm, cận trên loại |
| Nghĩ cận cuối của `$bucket` bao gồm | Giá cực biên bị loại hoặc vào default | Thêm cận phù hợp/định nghĩa default |
| Không có `default` và tồn tại outlier | Pipeline lỗi | Lọc hoặc khai báo default |
| Gom null/missing/âm vào `"HIGH_PRICE"` | Báo cáo sai ý nghĩa | Phân loại chất lượng input trước |
| Boundaries trùng hoặc giảm | Sai cấu hình | Dùng mốc tăng nghiêm ngặt |
| Trộn Date và Number trong boundaries | Sai kiểu | Chuẩn hóa BSON type |
| Tin bucket rỗng tự có `count: 0` | Thiếu cột trên UI | Bù khoảng rỗng khi tạo response |
| Dùng `$push: "$$ROOT"` cho hàng triệu record | Output lớn/quá bộ nhớ | Ưu tiên thống kê tổng hợp |
| Nghĩ `$bucketAuto` tạo khoảng rộng bằng nhau | Histogram bị hiểu sai | Giải thích cân bằng số document |
| Nghĩ `buckets: 5` luôn trả chính xác năm nhóm | Giá trùng/ít distinct làm lệch | Xử lý số bucket thực tế |
| So sánh bucket #2 của hai kỳ auto | Ranh giới có thể khác | Dùng `$bucket` để so theo ngưỡng cố định |
| Dùng granularity như một hàm parse Date | Không đúng mục đích | Date boundaries hoặc `$dateTrunc` |
| Giá có kiểu String nhưng phân tích như numeric | Sai kết quả/lỗi | `$convert`, validation, migration |
| Đếm phần trăm với mẫu số không xác định | Diễn giải sai | Nêu rõ input/filter và số bị loại |
| Chỉ xem số output và bỏ qua input | Đánh giá sai hiệu năng | `explain` + đo tải thật |

## 25. Bài tập thực hành

### Bài 1 — Kiểm tra chính xác ranh giới

Dùng `bucketLabProducts` và boundaries `[0,100,300,600,1000]`.

1. Ghi nhóm của P03 có giá 100.
2. Ghi nhóm của P06 có giá 300.
3. Ghi nhóm của P09 có giá 600.
4. Giải thích vì sao P11 có giá đúng 1000 đi vào `OTHER`.
5. Bỏ `default`, chạy lại và mô tả lỗi khi có input ngoài miền.

### Bài 2 — Nhiều accumulator

Viết pipeline `$bucket` để tính theo phân khúc giá:

- Số loại sản phẩm;
- Tổng số lượng tồn kho;
- Giá trung bình;
- Giá thực thấp nhất và cao nhất;
- Tổng giá trị tồn kho từ `price × stock`.

Giải thích sự khác biệt giữa cận bucket và min/max giá thực.

### Bài 3 — Bucket rỗng

Tạo collection chỉ có hai giá 50 và 850, chia bốn khoảng cố định. MongoDB trả mấy document bucket? Hãy xây response có đủ bốn khoảng và điền `count: 0` cho hai khoảng rỗng.

### Bài 4 — Phân phối dữ liệu lệch

Sinh 1.000 document: 800 sản phẩm giá dưới 100, 150 giá từ 100 đến dưới 1000 và 50 giá từ 1000 trở lên.

1. Chạy `$bucket` với các khoảng độ rộng cố định.
2. Chạy `$bucketAuto` với năm bucket.
3. So sánh độ rộng khoảng và số document.
4. Giải thích phương án nào phù hợp cho khám phá phân bố và phương án nào phù hợp thang phân khúc chính thức.

### Bài 5 — Giá trị trùng

Tạo 100 document nhưng chỉ ba giá trị 10, 20, 30. Yêu cầu `$bucketAuto` tạo năm bucket. Tại sao có thể không thu được năm nhóm cân bằng? Nên diễn giải kết quả thế nào với người đọc báo cáo?

### Bài 6 — Granularity

Trên tập giá dương, chạy `$bucketAuto` không có granularity rồi chạy với `"R5"`. So sánh ranh giới, count và số nhóm; nhận xét khi nào ngưỡng dễ đọc quan trọng hơn độ cân bằng. Nêu cách xử lý giá bằng 0/âm theo quy tắc của dãy số được chọn.

### Bài 7 — Ngày giờ và timezone

Dùng `$bucket` để nhóm đơn hàng theo tháng 1, 2, 3 năm 2026. Thêm đơn hàng lúc `2026-03-01T00:00:00Z` và xác định nhóm. Nếu doanh nghiệp muốn tháng theo `Asia/Ho_Chi_Minh`, cần thay đổi ranh giới thế nào hoặc dùng toán tử nào?

### Bài 8 — `$facet` cho dashboard

Viết một pipeline có bốn nhánh:

1. Nhóm giá theo mốc cố định;
2. Bốn nhóm giá tự động;
3. Min/max/average giá hợp lệ;
4. Số document null/missing/invalid.

Giải thích vì sao đặt `$match` loại null trước `$facet` làm nhánh thứ tư không thể thống kê dữ liệu đã bị loại.

### Bài 9 — Tỷ lệ và mẫu số

Tính phần trăm sản phẩm ở mỗi khoảng. Nêu rõ mẫu số là sản phẩm có giá hợp lệ trong miền 0–1000 hay là tất cả sản phẩm; nếu có nhóm `OTHER`, cách trình bày tỷ lệ cần thay đổi thế nào?

### Bài 10 — Đánh giá hiệu năng

Trên dataset một triệu đơn hàng:

1. Đặt `$match` theo tenant và thời gian trước `$bucketAuto`.
2. Tạo index ứng viên cho filter.
3. Xem `explain("executionStats")`.
4. So sánh 5 bucket với 100 bucket về runtime/tài nguyên.
5. Đề xuất pre-aggregation hoặc cache khi dashboard có nhiều lượt xem.
6. Phân biệt số bucket output với số document phải duyệt để tạo chúng.

## 26. Tài liệu MongoDB tham khảo

- [MongoDB $bucket](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucket/)
- [MongoDB $bucketAuto](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucketAuto/)
- [MongoDB $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB Accumulators](https://www.mongodb.com/docs/manual/reference/mql/accumulators/)
- [MongoDB $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/)
- [MongoDB $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

## Kết luận

**`$bucket`** là lựa chọn khi cần phân nhóm theo **các ranh giới cố định**, ví dụ các phân khúc giá, ngưỡng điểm hoặc mốc thời gian được nghiệp vụ quy định. Mỗi khoảng bao gồm cận dưới, loại cận trên; input ngoài miền cần được lọc hoặc đưa vào bucket `default`. Bucket rỗng không tự hiện với count 0, và kết quả `_id` thường là cận dưới.

**`$bucketAuto`** phù hợp để **khám phá phân bố**: MongoDB tự chọn ranh giới nhằm cân bằng số document giữa các nhóm, có thể dùng `granularity` để làm ngưỡng số dễ đọc. Số bucket thực tế hoặc số document mỗi bucket không được đảm bảo tuyệt đối khi giá trị trùng hay dữ liệu phân bố lệch, và ranh giới có thể thay đổi giữa các lần chạy.

Trong cả hai trường hợp, cần chuẩn hóa kiểu BSON, làm rõ đơn vị đo, xử lý null/missing/outlier có chủ đích và đo hiệu năng khi input lớn. Một histogram đáng tin cậy không chỉ cần câu lệnh aggregation đúng, mà còn cần **định nghĩa chính xác mỗi khoảng biểu thị điều gì, tập document nào được tính và các kỳ báo cáo có thực sự đang so sánh cùng một miền giá trị hay không**.

