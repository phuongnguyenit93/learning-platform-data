# Gom nhóm bằng `$group` và lựa chọn khóa nhóm trong MongoDB

Khi dùng MongoDB để lưu đơn hàng, sự kiện hay tài khoản, mỗi document thường mô tả một đối tượng hoặc một lần phát sinh nghiệp vụ. Nhưng màn hình báo cáo lại cần câu trả lời ở cấp **nhóm**: mỗi khách hàng có bao nhiêu đơn, doanh thu theo trạng thái là bao nhiêu, số đơn theo ngày thay đổi thế nào, hoặc sản phẩm nào được đặt nhiều nhất.

Trong **aggregation pipeline**, stage **`$group`** giúp gom các document có cùng **khóa nhóm** rồi tính những giá trị tổng hợp bằng các **accumulator** như `$sum`, `$avg`, `$min`, `$max`, `$push` và `$addToSet`.

Điểm cốt lõi không chỉ là nhớ cú pháp `$group`, mà còn là **chọn đúng khóa nhóm**. Chọn `status` cho báo cáo theo trạng thái, chọn `customerId` cho báo cáo theo khách hàng, chọn một object chứa nhiều thành phần cho báo cáo đa chiều, hoặc tính khóa từ ngày tháng khi muốn thống kê theo ngày. Mỗi lựa chọn làm thay đổi ý nghĩa của từng dòng kết quả.

Bài học trong chương **Aggregation cơ bản** sẽ giải thích cách thiết kế khóa nhóm, thực hành với dữ liệu đơn hàng, xử lý khóa thiếu/`null`, phân biệt đếm document và đếm phần tử mảng, đọc kết quả, tối ưu pipeline và vận dụng trong ứng dụng Java.

## 1. `$group` thực hiện công việc gì?

Một pipeline thường gồm các stage, mỗi stage nhận dữ liệu từ stage trước và đưa kết quả cho stage tiếp theo:

```text
Collection orders
       |
       v
  $match (lọc)
       |
       v
  $group (gom + tính toán)
       |
       v
  $sort (sắp xếp nhóm)
       |
       v
  $project (định dạng)
       |
       v
  Báo cáo tổng hợp
```

Ví dụ cần đếm số đơn hàng theo trạng thái:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 }
    }
  }
])
```

Ý nghĩa:

- `aggregate([...])`: chạy các stage aggregation theo thứ tự.
- `$group`: tạo một kết quả cho mỗi giá trị khóa nhóm phân biệt.
- `_id: "$status"`: sử dụng **giá trị của field `status`** trong từng document để quyết định document thuộc nhóm nào.
- `orderCount: { $sum: 1 }`: mỗi document đóng góp số `1` vào nhóm, do đó kết quả là số document thuộc nhóm.

Tên `_id` trong kết quả `$group` là **khóa nhóm**, không nhất thiết là `_id` gốc của một document. Ví dụ `_id: "paid"` có nghĩa đây là nhóm các đơn đã thanh toán; không phải có một đơn hàng mang `_id` là `"paid"`.

**Cú pháp khái quát:**

```javascript
{
  $group: {
    _id: <bieu_thuc_khoa_nhom>,
    tenChiSo1: { <accumulator>: <bieu_thuc> },
    tenChiSo2: { <accumulator>: <bieu_thuc> }
  }
}
```

Các field kết quả khác `_id` trong stage `$group` thông thường được xây bằng **accumulator expression**. Không thể tùy ý đưa một field của document nguồn ra kết quả mà không xác định cách gom nó, vì một nhóm có thể chứa nhiều document mang các giá trị khác nhau.

## 2. Bộ dữ liệu thực hành

Mở `mongosh`, chọn database riêng để thực hành:

```javascript
use mongo_aggregation_lab
```

Tạo collection `orders` mới hoặc trống, rồi chèn mười đơn hàng mẫu:

```javascript
db.orders.insertMany([
  {
    _id: 101,
    customerId: "C01",
    status: "paid",
    channel: "web",
    region: "north",
    total: NumberInt(120),
    createdAt: ISODate("2026-11-10T08:00:00Z"),
    items: [
      { sku: "A", qty: NumberInt(2) },
      { sku: "B", qty: NumberInt(1) }
    ]
  },
  {
    _id: 102,
    customerId: "C01",
    status: "paid",
    channel: "mobile",
    region: "north",
    total: NumberInt(180),
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    items: [{ sku: "A", qty: NumberInt(1) }]
  },
  {
    _id: 103,
    customerId: "C02",
    status: "pending",
    channel: "web",
    region: "south",
    total: NumberInt(90),
    createdAt: ISODate("2026-11-10T10:00:00Z"),
    items: [{ sku: "C", qty: NumberInt(3) }]
  },
  {
    _id: 104,
    customerId: "C03",
    status: "paid",
    channel: "web",
    region: "north",
    total: NumberInt(240),
    createdAt: ISODate("2026-11-11T08:00:00Z"),
    items: [{ sku: "B", qty: NumberInt(2) }]
  },
  {
    _id: 105,
    customerId: "C02",
    status: "cancelled",
    channel: "mobile",
    region: "south",
    total: NumberInt(60),
    createdAt: ISODate("2026-11-11T09:00:00Z"),
    items: []
  },
  {
    _id: 106,
    customerId: "C03",
    status: "paid",
    channel: "mobile",
    region: "north",
    total: NumberInt(150),
    createdAt: ISODate("2026-11-11T10:00:00Z"),
    items: [
      { sku: "A", qty: NumberInt(2) },
      { sku: "C", qty: NumberInt(1) }
    ]
  },
  {
    _id: 107,
    customerId: "C04",
    status: "pending",
    channel: "web",
    region: "south",
    total: NumberInt(110),
    createdAt: ISODate("2026-11-12T08:00:00Z"),
    items: [{ sku: "B", qty: NumberInt(1) }]
  },
  {
    _id: 108,
    customerId: "C01",
    status: "paid",
    channel: "web",
    region: "north",
    total: NumberInt(210),
    createdAt: ISODate("2026-11-12T09:00:00Z"),
    items: [{ sku: "C", qty: NumberInt(2) }]
  },
  {
    _id: 109,
    customerId: "C05",
    status: "pending",
    channel: "web",
    total: NumberInt(85),
    createdAt: ISODate("2026-11-12T10:00:00Z"),
    items: []
    // Không có field region
  },
  {
    _id: 110,
    customerId: "C06",
    channel: "mobile",
    region: null,
    total: NumberInt(45),
    createdAt: ISODate("2026-11-12T11:00:00Z"),
    items: []
    // Không có field status
  }
])
```

Đơn hàng `109` cố ý **thiếu `region`**, còn đơn `110` có `region: null` và **thiếu `status`**. Hai trường hợp giúp kiểm tra cách khóa nhóm xử lý dữ liệu không đầy đủ.

Với bộ dữ liệu này:

| Trạng thái | Số đơn | Tổng `total` |
| --- | ---: | ---: |
| `paid` | 5 | 900 |
| `pending` | 3 | 285 |
| `cancelled` | 1 | 60 |
| Thiếu `status` | 1 | 45 |
| **Tổng** | **10** | **1.290** |

Các truy vấn tiếp theo giả định dữ liệu vẫn giữ nguyên. Không chạy lại `insertMany()` nhiều lần với cùng `_id`; việc chèn lặp sẽ gây lỗi duplicate key. Không xóa collection có dữ liệu quan trọng chỉ để làm lại bài thực hành.

## 3. Chọn một field làm khóa nhóm

### 3.1. Gom đơn hàng theo `status`

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Kết quả tương ứng với dữ liệu mẫu, trình bày gọn theo nhóm:

```javascript
{ _id: null,        orderCount: 1, totalAmount: 45 }
{ _id: "cancelled", orderCount: 1, totalAmount: 60 }
{ _id: "paid",      orderCount: 5, totalAmount: 900 }
{ _id: "pending",   orderCount: 3, totalAmount: 285 }
```

Trong đó:

- `$sum: 1` đếm **mỗi document đầu vào** đúng một lần.
- `$sum: "$total"` cộng **giá trị số** của field `total` trong từng document thuộc nhóm.
- `_id: "$status"` quyết định có bao nhiêu nhóm; hai document cùng `status` sẽ thuộc cùng một nhóm.
- `$sort` ở sau `$group` quyết định thứ tự hiển thị các nhóm.

MongoDB **không bảo đảm thứ tự đầu ra của `$group`**. Nếu báo cáo cần thứ tự xác định, phải thêm `$sort` sau khi gom.

### 3.2. Gom theo khách hàng

Thay khóa nhóm từ `"$status"` thành `"$customerId"`:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { totalAmount: -1, _id: 1 } }
])
```

Với dữ liệu mẫu:

| Khách hàng | Số đơn | Tổng tiền |
| --- | ---: | ---: |
| C01 | 3 | 510 |
| C03 | 2 | 390 |
| C02 | 2 | 150 |
| C04 | 1 | 110 |
| C05 | 1 | 85 |
| C06 | 1 | 45 |

Cùng mười document đầu vào, nhưng báo cáo bây giờ có **sáu nhóm** thay vì bốn nhóm. Vì thế, chọn khóa nhóm là chọn **đơn vị phân tích**: một dòng kết quả biểu diễn trạng thái hay biểu diễn khách hàng?

### 3.3. Truy cập field lồng nhau bằng dot notation

Nếu document có:

```javascript
{
  customer: {
    id: "C01",
    address: { city: "Hà Nội" }
  }
}
```

ta có thể nhóm theo field lồng nhau:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customer.address.city",
      orderCount: { $sum: 1 }
    }
  }
])
```

Đường dẫn `"$customer.address.city"` là **aggregation field path**. Đây là ví dụ cấu trúc dữ liệu khác với collection `orders` thực hành ở mục 2, nơi `customerId` đang ở cấp gốc. Nếu chạy ngay trên dữ liệu mẫu, field trên không tồn tại và kết quả sẽ bị gom vào nhóm khóa thiếu thay vì thống kê thành phố.

**Phân biệt hai chuỗi:** `"$status"` đọc giá trị của field `status`; `"status"` (không có `$`) là một chuỗi hằng, khiến mọi document có cùng một khóa nhóm.

## 4. `_id: null` — gom toàn bộ document vào một nhóm

Khi chỉ cần các chỉ số tổng cho **toàn tập dữ liệu**, không phân chia theo field nào, dùng hằng `null` làm khóa nhóm:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: null,
      totalOrders: { $sum: 1 },
      totalAmount: { $sum: "$total" },
      averageAmount: { $avg: "$total" },
      minAmount: { $min: "$total" },
      maxAmount: { $max: "$total" }
    }
  }
])
```

Kết quả tương ứng với mười document mẫu:

```javascript
{
  _id: null,
  totalOrders: 10,
  totalAmount: 1290,
  averageAmount: 129,
  minAmount: 45,
  maxAmount: 240
}
```

Điều này hoàn toàn khác với `_id: "$status"`, vốn tạo các nhóm riêng và **có thể sinh một nhóm có khóa `null`** cho document thiếu `status`. Nói cách khác:

- `_id: null` → một **khóa hằng** cho mọi document đầu vào.
- `_id: "$status"` → khóa là giá trị field; một số document **có thể** rơi vào nhóm `null`.

Nếu không có document đầu vào, `$group` không tạo ra một dòng tổng hợp tùy ý cho nhóm hằng; cần xử lý riêng tình huống kết quả rỗng khi thiết kế API thống kê.

### Kết hợp `$match` để chỉ gom tập dữ liệu cần thiết

Để tính tổng tiền chỉ với đơn `paid`:

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: null,
      paidOrders: { $sum: 1 },
      paidAmount: { $sum: "$total" }
    }
  }
])
```

Kết quả là `paidOrders: 5`, `paidAmount: 900`. Stage `$match` đứng trước `$group` chỉ đưa các document cần thiết vào phép tính, và có cơ hội sử dụng index phù hợp cho bộ lọc.

## 5. Khóa nhóm ghép từ nhiều field (composite key)

Báo cáo thường có nhiều chiều. Ví dụ: **số đơn và tổng tiền theo `status` và `channel`**. Nếu chỉ nhóm theo `status`, ta không phân biệt đơn qua `web` hay `mobile`. Nếu chỉ nhóm theo `channel`, ta không phân biệt `paid` với `pending`.

Khai báo `_id` là một object gồm nhiều thành phần:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        status: "$status",
        channel: "$channel"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  {
    $sort: {
      "_id.status": 1,
      "_id.channel": 1
    }
  }
])
```

Mỗi nhóm được xác định bởi **cặp giá trị** `(status, channel)`. Kết quả minh họa:

| `_id.status` | `_id.channel` | Số đơn | Tổng tiền |
| --- | --- | ---: | ---: |
| `null` / thiếu | mobile | 1 | 45 |
| cancelled | mobile | 1 | 60 |
| paid | mobile | 2 | 330 |
| paid | web | 3 | 570 |
| pending | web | 3 | 285 |

Giả sử có hai document cùng `status: "paid"` nhưng một document có `channel: "web"` và document kia có `channel: "mobile"`. Hai document này **không thuộc cùng nhóm**, vì composite key khác nhau.

### 5.1. Vì sao nên dùng object thay vì nối chuỗi?

Một cách tưởng như đơn giản là ghép hai giá trị thành chuỗi:

```javascript
// Không phải lựa chọn tốt khi muốn cấu trúc khóa rõ ràng
{
  $group: {
    _id: {
      $concat: ["$status", "|", "$channel"]
    },
    orderCount: { $sum: 1 }
  }
}
```

Cách nối chuỗi có rủi ro:

- Giá trị gốc có thể chứa ký tự phân cách, gây trùng khóa ngoài ý muốn.
- Một field thiếu hoặc `null` có thể khiến phép nối không cho kết quả như mong đợi.
- Kiểu dữ liệu và cấu trúc các thành phần bị mất.
- Muốn lọc/sắp xếp theo từng thành phần phải tách chuỗi trở lại.

Object có tên field rõ ràng thường dễ mở rộng, ví dụ thêm `region` hoặc ngày vào khóa, và không phải tự thiết kế quy tắc escape ký tự phân cách.

### 5.2. Đưa thành phần khóa ra field ở cấp gốc

Output `$group` có thể mang `_id` là object lồng nhau. Để đưa về hình dạng dễ trả cho API:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        status: "$status",
        channel: "$channel"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  {
    $project: {
      _id: 0,
      status: "$_id.status",
      channel: "$_id.channel",
      orderCount: 1,
      totalAmount: 1
    }
  },
  { $sort: { status: 1, channel: 1 } }
])
```

`$project` chỉ biến đổi **hình dạng kết quả**. Nó không sửa các đơn hàng trong collection.

Nếu cần đặt tên trường đầu ra như `paymentStatus` hoặc `sourceChannel`, có thể đổi tên khi `$project` mà không thay đổi logic nhóm.

## 6. Khóa nhóm là một biểu thức, không nhất thiết là field có sẵn

`_id` của `$group` nhận một **aggregation expression**. Điều đó cho phép gom dữ liệu theo một giá trị được tính ra, chẳng hạn ngày, khoảng giá, nhóm độ tuổi hoặc trạng thái đã chuẩn hóa.

### 6.1. Gom theo ngày từ field `Date`

Field `createdAt` là timestamp; nếu nhóm trực tiếp bằng `_id: "$createdAt"`, các đơn có thời điểm khác nhau (dù trong cùng ngày) sẽ thuộc những nhóm khác nhau. Khi cần báo cáo **theo ngày**, phải tính một khóa biểu diễn **ngày lịch**.

Ví dụ dùng `$dateToString` với múi giờ Việt Nam:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Với dữ liệu mẫu, mọi thời điểm đều nằm trong cùng ngày UTC và ngày địa phương nên kết quả là:

| Khóa ngày `_id` | Số đơn | Tổng tiền |
| --- | ---: | ---: |
| `2026-11-10` | 3 | 390 |
| `2026-11-11` | 3 | 450 |
| `2026-11-12` | 4 | 450 |

`$dateToString` ở đây tạo **chuỗi** như `"2026-11-10"`. Khi chỉ cần tính ngày và vẫn muốn một giá trị BSON Date đại diện cho đầu ngày của mỗi nhóm, có thể dùng `$dateTrunc` trên các phiên bản MongoDB hỗ trợ:

```javascript
{
  $group: {
    _id: {
      $dateTrunc: {
        date: "$createdAt",
        unit: "day",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    orderCount: { $sum: 1 }
  }
}
```

`$dateTrunc` trả về một **Date** biểu diễn ranh giới khoảng thời gian, được lưu/hiển thị theo thời gian UTC dù ranh giới ngày được tính theo múi giờ chỉ định. Hãy phân biệt kiểu Date này với chuỗi ngày từ `$dateToString`.

### Vì sao timezone quan trọng?

Thời điểm `2026-11-10T20:00:00Z` thuộc ngày **10/11 ở UTC**, nhưng thuộc **11/11 theo Asia/Ho_Chi_Minh**. Nếu báo cáo dùng ngày nghiệp vụ Việt Nam, nhóm theo UTC một cách mặc định có thể đưa giao dịch vào sai ngày so với kỳ vọng của người dùng.

Khi thiết kế khóa theo ngày/tuần/tháng, cần thống nhất **múi giờ, đơn vị thời gian và quy tắc kỳ báo cáo** trước khi viết pipeline.

### 6.2. Khóa nhóm từ biểu thức phân loại giá trị

Giả sử cần chia đơn hàng thành nhóm `low` nếu `total < 150`, ngược lại là `high`:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $cond: {
          if: { $lt: ["$total", 150] },
          then: "low",
          else: "high"
        }
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Với dữ liệu mẫu, nhóm `low` gồm các tổng tiền `120, 90, 60, 110, 85, 45` (6 đơn), còn `high` gồm `180, 240, 150, 210` (4 đơn). Đây là ví dụ **khóa nhóm tính toán**, không cần lưu sẵn field `priceBand`.

Khi dùng các giá trị phân loại, cần xác định rõ ranh giới: ở ví dụ trên, `150` thuộc nhóm `high` vì điều kiện là `$lt`, không phải `$lte`.

### 6.3. Kết hợp ngày và một dimension khác

Muốn báo cáo **số đơn từng trạng thái theo từng ngày**:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        day: {
          $dateToString: {
            format: "%Y-%m-%d",
            date: "$createdAt",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        status: { $ifNull: ["$status", "unknown"] }
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { "_id.day": 1, "_id.status": 1 } }
])
```

Khóa nhóm là object gồm **ngày đã tính toán** và **trạng thái đã chuẩn hóa**. Đây là một ví dụ điển hình của báo cáo nhiều chiều.

## 7. Xử lý khóa nhóm thiếu, `null` và kiểu dữ liệu khác nhau

Trong dữ liệu mẫu:

```javascript
{ _id: 109, /* không có region */ }
{ _id: 110, region: null }
```

Truy vấn:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$region",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

cho các nhóm tương ứng:

```javascript
{ _id: null,    orderCount: 2, totalAmount: 130 }
{ _id: "north", orderCount: 5, totalAmount: 900 }
{ _id: "south", orderCount: 3, totalAmount: 260 }
```

Với khóa field path đơn giản, document có giá trị `region: null` và document **không có `region`** đều có thể rơi vào nhóm khóa `null`. Nếu nghiệp vụ cần phân biệt "chưa khai báo" với "đã khai báo nhưng giá trị null", đừng mặc nhiên xem kết quả trên là ba trạng thái đầy đủ.

### 7.1. Gộp các giá trị không xác định bằng `$ifNull`

Trong một báo cáo giao diện, có thể dùng nhãn `"unknown"`:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $ifNull: ["$region", "unknown"] },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
```

`$ifNull` xem các trường hợp null/missing/undefined tương ứng là không có giá trị và thay bằng `"unknown"`. Trên dữ liệu mẫu, các đơn `109` và `110` cùng vào nhóm `"unknown"` với hai đơn.

**Lưu ý xung đột nhãn:** Nếu dữ liệu thật đã có `region: "unknown"` như một giá trị hợp lệ, cách chuẩn hóa trên sẽ gộp nó cùng những bản thiếu/null. Khi cần phân biệt chính xác về mặt nghiệp vụ, nên dùng một khóa cấu trúc hoặc mã phân loại được thiết kế để không xung đột với giá trị thật.

### 7.2. Giữ riêng null và missing

Aggregation expression `$type` có thể trả `"missing"` khi field không tồn tại và `"null"` khi giá trị field là BSON Null. Ta có thể dựng khóa nhóm chứa loại trạng thái:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        regionType: { $type: "$region" },
        regionValue: { $ifNull: ["$region", null] }
      },
      orderCount: { $sum: 1 }
    }
  },
  {
    $sort: {
      "_id.regionType": 1,
      "_id.regionValue": 1
    }
  }
])
```

Lúc này một nhóm có `regionType: "missing"` và nhóm khác có `regionType: "null"`; người đọc báo cáo biết rõ hai nguồn dữ liệu khác nhau. Nếu schema của hệ thống đã quy định field luôn là string, nhu cầu phân loại này có thể ít gặp hơn; nó hữu ích trong giai đoạn migration hoặc xử lý dữ liệu không đồng nhất.

### 7.3. Kiểu BSON của khóa nhóm ảnh hưởng kết quả

Giả sử một collection có document lưu `groupCode: 1` là số và document khác lưu `groupCode: "1"` là chuỗi. Hai giá trị không nên được mặc nhiên coi là một nhóm. Kiểu BSON của dữ liệu có thể thay đổi cách equality/grouping hoạt động.

Để thống nhất nhóm, nên chuẩn hóa schema lúc ghi hoặc dùng aggregation expression chuyển kiểu **có chủ đích**, sau khi xác định trường hợp lỗi chuyển kiểu. Với chuỗi còn có quy tắc collation: so sánh theo ngôn ngữ, hoa/thường và dấu có thể ảnh hưởng các giá trị được coi là tương đương trong điều kiện và nhóm.

**Nguyên tắc:** khóa nhóm phải có kiểu và ý nghĩa ổn định. Nếu dữ liệu nguồn lẫn lộn `Date` và chuỗi ngày, `"01"` và `1`, hoặc viết hoa/viết thường không nhất quán, hãy quyết định quy tắc chuẩn hóa trước khi giải thích số nhóm.

## 8. Những accumulator thường dùng cùng `$group`

Các accumulator lấy nhiều đầu vào trong một nhóm và tạo ra chỉ số hoặc giá trị đại diện.

| Accumulator | Công dụng | Ví dụ |
| --- | --- | --- |
| `$sum` | Cộng giá trị số hoặc đếm document | `{ $sum: "$total" }`, `{ $sum: 1 }` |
| `$avg` | Trung bình các giá trị số | `{ $avg: "$total" }` |
| `$min` | Giá trị nhỏ nhất theo quy tắc so sánh BSON | `{ $min: "$total" }` |
| `$max` | Giá trị lớn nhất | `{ $max: "$total" }` |
| `$first` | Giá trị từ document đầu tiên đi vào nhóm | `{ $first: "$createdAt" }` |
| `$last` | Giá trị từ document cuối cùng đi vào nhóm | `{ $last: "$createdAt" }` |
| `$push` | Gom giá trị thành array, giữ các lần xuất hiện | `{ $push: "$_id" }` |
| `$addToSet` | Gom các giá trị phân biệt thành array | `{ $addToSet: "$channel" }` |

Ví dụ tạo báo cáo theo khách hàng với nhiều chỉ số:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" },
      averageAmount: { $avg: "$total" },
      smallestOrder: { $min: "$total" },
      largestOrder: { $max: "$total" },
      allOrderIds: { $push: "$_id" },
      channelsUsed: { $addToSet: "$channel" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Với nhóm `C01`, ta có `orderCount = 3`, `totalAmount = 510`, `averageAmount = 170`, `smallestOrder = 120`, `largestOrder = 210`. Các ID là `101, 102, 108`, còn tập kênh có `web` và `mobile`.

**Thứ tự phần tử trong array của `$addToSet` không được bảo đảm.** Với `$push`, thứ tự phản ánh thứ tự document đi vào stage; nếu thứ tự quan trọng, phải thiết kế pipeline sắp xếp trước khi gom.

### 8.1. Sự khác nhau giữa đếm dòng và tính tổng giá trị

```javascript
{
  $group: {
    _id: "$customerId",
    numberOfOrders: { $sum: 1 },
    totalAmount: { $sum: "$total" }
  }
}
```

`$sum: 1` cộng một hằng số cho mỗi document, còn `$sum: "$total"` lấy **giá trị của field**. Hai biểu thức này có ý nghĩa khác hẳn nhau dù đều dùng `$sum`.

Nếu `total` có giá trị không phải số, các accumulator số có quy tắc xử lý riêng: `$sum` và `$avg` bỏ qua các giá trị không phải số; nếu không có giá trị số thích hợp, kết quả của chúng cũng khác. Vì thế, `orderCount` không nhất thiết bằng số phần tử tham gia vào phép tính trung bình nếu dữ liệu thiếu/sai kiểu. Schema validation hoặc xử lý dữ liệu nên bảo đảm kiểu số trước khi báo cáo tài chính.

Đối với giá trị tiền tệ cần độ chính xác thập phân, nên cân nhắc **BSON Decimal128** (`NumberDecimal` trong `mongosh`) thay vì lưu số tiền dưới string hoặc dùng số dấu phẩy động nhị phân không phù hợp.

### 8.2. Chỉ lấy giá trị đầu hoặc cuối khi có thứ tự rõ ràng

Muốn tìm ngày đơn hàng đầu tiên và cuối cùng của mỗi khách hàng, có thể dùng trực tiếp `$min` và `$max` vì trường là Date:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      earliestCreatedAt: { $min: "$createdAt" },
      latestCreatedAt: { $max: "$createdAt" }
    }
  }
])
```

Nếu muốn lấy **toàn bộ đơn hàng mới nhất** hoặc một field gắn với đúng đơn mới nhất, dùng `$sort` trước `$group`, rồi chọn `$first` hoặc `$last`:

```javascript
db.orders.aggregate([
  { $sort: { customerId: 1, createdAt: -1, _id: -1 } },
  {
    $group: {
      _id: "$customerId",
      newestOrderId: { $first: "$_id" },
      newestOrderTotal: { $first: "$total" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Với `C01`, `newestOrderId` là `108` và `newestOrderTotal` là `210`.

Không thêm `$sort` rồi mặc định `$first` là document có `_id` nhỏ nhất: **`$first` lấy document đến đầu tiên theo thứ tự pipeline**, không tự tìm giá trị min/max. Khi dữ liệu trùng timestamp, nên thêm khóa duy nhất như `_id` để ổn định cách chọn.

## 9. Khóa nhóm theo mảng: nhóm nguyên array hay từng phần tử?

Nếu document chứa:

```javascript
{
  _id: 101,
  items: [
    { sku: "A", qty: 2 },
    { sku: "B", qty: 1 }
  ]
}
```

thì khóa:

```javascript
{
  $group: {
    _id: "$items",
    orderCount: { $sum: 1 }
  }
}
```

không có nghĩa “nhóm theo từng mặt hàng”. Nó nhóm các document theo **giá trị của toàn array `items`**; những array có nội dung khác nhau tạo khóa khác nhau.

Nếu muốn thống kê **theo từng SKU bên trong array**, cần tách các phần tử trước bằng **`$unwind`**:

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      orderLines: { $sum: 1 },
      unitsOrdered: { $sum: "$items.qty" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Kết quả trên dữ liệu mẫu:

| SKU | Số dòng mặt hàng `orderLines` | Tổng số lượng `unitsOrdered` |
| --- | ---: | ---: |
| A | 3 | 5 |
| B | 3 | 4 |
| C | 3 | 6 |

Lý do:

- Sản phẩm A xuất hiện trong đơn `101` với số lượng 2, đơn `102` với số lượng 1, đơn `106` với số lượng 2 → tổng 5.
- Sản phẩm B xuất hiện trong đơn `101` (1), `104` (2), `107` (1) → tổng 4.
- Sản phẩm C xuất hiện trong đơn `103` (3), `106` (1), `108` (2) → tổng 6.

`$unwind` biến **một đơn hàng có nhiều items thành nhiều dòng đầu vào** cho `$group`. Do vậy, sau unwind, `$sum: 1` đếm **số dòng item**, **không phải số đơn hàng duy nhất**.

### 9.1. Đếm số đơn hàng duy nhất theo SKU

Nếu cùng một SKU có thể xuất hiện nhiều lần trong một order, `orderLines` không tương đương số đơn hàng chứa SKU đó. Có thể gom các `_id` đơn hàng phân biệt:

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      orderIds: { $addToSet: "$_id" },
      unitsOrdered: { $sum: "$items.qty" }
    }
  },
  {
    $project: {
      _id: 0,
      sku: "$_id",
      uniqueOrderCount: { $size: "$orderIds" },
      unitsOrdered: 1
    }
  },
  { $sort: { sku: 1 } }
])
```

Ví dụ này nhấn mạnh việc **xác định đơn vị đếm**: document đơn hàng, dòng mặt hàng hay số lượng mặt hàng là ba chỉ số khác nhau.

### 9.2. Mảng rỗng và field mảng không tồn tại

`$unwind: "$items"` mặc định không phát ra dòng cho document có `items: []`, `items: null` hoặc thiếu field. Vì thế các đơn `105`, `109`, `110` không đóng góp vào bảng nhóm SKU ở trên.

Khi cần giữ những document này cho một báo cáo khác, có thể sử dụng:

```javascript
{
  $unwind: {
    path: "$items",
    preserveNullAndEmptyArrays: true
  }
}
```

Nhưng cần quyết định khóa nhóm/giá trị tích lũy dành cho đơn không có items để tránh tạo một nhóm SKU `null` ngoài ý định. Tùy mục tiêu, có thể lọc các dòng không có SKU hợp lệ trước `$group`.

## 10. `$match` trước hay sau `$group`?

Vị trí của `$match` làm thay đổi **đối tượng được lọc** và có thể ảnh hưởng hiệu năng.

### 10.1. Lọc document trước khi gom

Câu hỏi: **"Tổng tiền các đơn đã thanh toán theo từng khách hàng?"**

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$customerId",
      paidOrders: { $sum: 1 },
      paidAmount: { $sum: "$total" }
    }
  },
  { $sort: { paidAmount: -1 } }
])
```

Ở đây chỉ các đơn `paid` được đưa vào group. Với dữ liệu mẫu, các nhóm là `C01` có 3 đơn tổng 510 và `C03` có 2 đơn tổng 390.

### 10.2. Lọc nhóm sau khi gom

Câu hỏi: **"Khách hàng nào có ít nhất hai đơn hàng, bất kể trạng thái?"**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $match: { orderCount: { $gte: 2 } } },
  { $sort: { orderCount: -1, _id: 1 } }
])
```

Kết quả gồm `C01` (3 đơn), `C02` (2 đơn), `C03` (2 đơn). Field `orderCount` **chỉ được tạo ra sau `$group`**, nên điều kiện này phải xuất hiện ở phía sau.

### Phân biệt hai loại điều kiện

| Loại điều kiện | Ví dụ | Vị trí logic |
| --- | --- | --- |
| Điều kiện trên document gốc | `status: "paid"`, `createdAt: {$gte: ...}` | `$match` trước `$group` |
| Điều kiện trên chỉ số tổng hợp | `orderCount: {$gte: 2}`, `totalAmount: {$gt: 500}` | `$match` sau `$group` |

Đặt `$match` sớm để giới hạn document đầu vào thường giúp giảm số bản ghi phải tổng hợp và có thể tận dụng index. Nhưng không thể chuyển một điều kiện trên `orderCount` lên trước khi `orderCount` được tính mà vẫn giữ nguyên ý nghĩa.

## 11. Lựa chọn khóa nhóm theo yêu cầu nghiệp vụ

Việc chọn khóa nhóm nên bắt đầu từ **một câu hỏi nghiệp vụ rõ ràng**: "Mỗi dòng của báo cáo đại diện cho cái gì?"

| Yêu cầu báo cáo | Khóa nhóm `_id` | Mỗi dòng kết quả đại diện cho |
| --- | --- | --- |
| Tổng doanh thu toàn hệ thống | `null` | Toàn bộ document đã lọc |
| Số đơn theo trạng thái | `"$status"` | Một trạng thái |
| Tổng tiền theo khách hàng | `"$customerId"` | Một khách hàng |
| Số đơn theo trạng thái và kênh | `{status:"$status",channel:"$channel"}` | Một cặp trạng thái–kênh |
| Số đơn theo ngày Việt Nam | `{$dateToString:{date:"$createdAt",format:"%Y-%m-%d",timezone:"Asia/Ho_Chi_Minh"}}` | Một ngày lịch tại múi giờ đã chọn |
| Số đơn theo ngày và vùng | `{day:<ngay_da_tinh>,region:"$region"}` | Một cặp ngày–vùng |
| Số lượng mặt hàng theo SKU | `"$items.sku"` **sau** `$unwind` | Một SKU từ các dòng item |
| Số đơn theo dải giá | `{$cond: ...}` hoặc biểu thức phân nhóm mức giá | Một khoảng giá được xác định |

### 11.1. Khóa quá rộng hoặc quá chi tiết

Nếu chọn `_id: "$_id"` cho mỗi đơn, vì `_id` gốc thường duy nhất nên gần như **mỗi document thành một nhóm riêng**. Cách này ít hữu ích khi muốn tổng hợp nhiều đơn theo khách hàng. Ngược lại, `_id: null` chỉ cho **một dòng tổng** và không còn phân biệt khách hàng.

Ví dụ:

```javascript
// Gần như mỗi đơn thành một nhóm riêng
{ $group: { _id: "$_id", orderCount: { $sum: 1 } } }

// Mọi đơn thành một nhóm
{ $group: { _id: null, orderCount: { $sum: 1 } } }

// Một nhóm cho từng khách hàng
{ $group: { _id: "$customerId", orderCount: { $sum: 1 } } }
```

Không phải khóa nhóm càng nhiều thành phần càng tốt. Một khóa quá chi tiết có thể tạo số nhóm gần bằng số document, làm báo cáo khó đọc và tốn thêm bộ nhớ xử lý. Chỉ thêm chiều khi nó thực sự mang ý nghĩa phân tích.

### 11.2. Cân nhắc cardinality

**Cardinality của khóa nhóm** là số giá trị/nhóm phân biệt trong tập document đầu vào.

- Khóa `status` thường có ít nhóm.
- Khóa `customerId` có thể có hàng triệu nhóm.
- Khóa ghép `customerId + ngày + SKU` có thể tạo số nhóm rất lớn.
- Khóa theo timestamp chính xác đến mili giây có thể gần như duy nhất, dù nghiệp vụ chỉ muốn nhóm theo ngày.

Số nhóm lớn làm tăng khối lượng trạng thái accumulator cần giữ. Nếu có thể, hãy gom ở **độ hạt cần thiết**: theo ngày thay vì theo timestamp, theo khách hàng thay vì từng đơn, hoặc lọc dữ liệu trước khi nhóm.

### 11.3. Chọn loại khóa dễ tái sử dụng và không mơ hồ

Trong một báo cáo có thể dùng:

```javascript
_id: {
  customerId: "$customerId",
  yearMonth: {
    $dateToString: {
      format: "%Y-%m",
      date: "$createdAt",
      timezone: "Asia/Ho_Chi_Minh"
    }
  }
}
```

Khóa ghép này dễ truy cập từng thành phần và phản ánh rõ “doanh thu từng khách hàng mỗi tháng”. Nó tốt hơn việc nối các giá trị thành một chuỗi không có quy ước phân cách/escape ổn định.

## 12. Hiệu năng và giới hạn thực tế của `$group`

`$group` là một **blocking stage** trong nhiều trường hợp: stage phải xử lý đủ dữ liệu đầu vào cần thiết để tính các nhóm và accumulator trước khi có thể hoàn tất kết quả tổng hợp. Điều này khác với một số thao tác streaming có thể đưa từng document đi tiếp ngay.

Chi phí của group thường phụ thuộc vào:

- **Số document đầu vào** sau `$match`.
- **Số nhóm phân biệt** được tạo bởi `_id`.
- **Kích thước trạng thái mỗi nhóm**, nhất là khi dùng `$push` hoặc `$addToSet` để tích lũy mảng lớn.
- **Chi phí biểu thức khóa nhóm**, chẳng hạn xử lý ngày hoặc chuỗi.
- **Phân bố dữ liệu**, số lượng giá trị khác nhau và sự lệch nhóm.
- **Khả năng sử dụng index** ở những stage trước đó, cùng các chiến lược tối ưu của phiên bản MongoDB.

### 12.1. Index giúp ở đâu?

Giả sử phần lớn báo cáo bắt đầu bằng:

```javascript
{ $match: { status: "paid" } }
```

Index trên `status` có thể hỗ trợ lọc sớm khi phù hợp. Nếu pipeline cần sắp xếp trước khi lấy `$first`/`$last`, compound index khớp filter và sort cũng có thể hữu ích.

Tuy nhiên, việc có index trên `customerId` **không tự bảo đảm** câu `$group: {_id:"$customerId", total:{$sum:"$total"}}` sẽ chỉ cần đọc vài index entries. Để tính tổng tất cả đơn cho từng khách hàng, MongoDB vẫn phải xử lý các giá trị đóng góp vào tổng. Một số tối ưu đặc biệt có thể tận dụng index cho các mẫu group nhất định, nhưng không nên suy ra rằng mọi `$group` đều được tăng tốc trực tiếp nhờ index trên khóa nhóm.

### 12.2. Quản lý bộ nhớ khi có nhiều nhóm

Trong những phiên bản/cấu hình MongoDB nhất định, các stage như `$group` có giới hạn sử dụng bộ nhớ trong RAM và có thể ghi dữ liệu tạm ra đĩa khi được cho phép. Có thể cấu hình tùy chọn:

```javascript
db.orders.aggregate(
  [
    {
      $group: {
        _id: "$customerId",
        orderCount: { $sum: 1 },
        totalAmount: { $sum: "$total" }
      }
    }
  ],
  { allowDiskUse: true }
)
```

`allowDiskUse: true` cho phép các thao tác tương ứng dùng bộ nhớ đĩa tạm theo khả năng của server; đây **không phải** công tắc làm group nhanh hơn. Sử dụng đĩa có thể làm tăng I/O và thời gian chạy. Các giới hạn và hành vi mặc định liên quan đến `allowDiskUse` có thể thay đổi theo phiên bản và tham số cấu hình, nên cần đối chiếu môi trường đang sử dụng.

Khi pipeline dùng `$push: "$$ROOT"` để giữ **toàn bộ document của mọi nhóm**, trạng thái tích lũy có thể rất lớn. Cần cân nhắc chỉ giữ những field thực sự cần, giới hạn tập đầu vào hoặc thiết kế lại báo cáo. Đồng thời, mỗi document kết quả vẫn chịu giới hạn kích thước BSON của MongoDB; cho phép spill ra đĩa không tự loại bỏ giới hạn kích thước document đầu ra.

### 12.3. `$sort` trước và sau group có tác dụng khác nhau

```javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: -1 } },
  {
    $group: {
      _id: "$customerId",
      newestOrderId: { $first: "$_id" }
    }
  }
])
```

`$sort` **trước** group quyết định thứ tự dòng đầu vào, từ đó xác định `$first`.

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1, _id: 1 } }
])
```

`$sort` **sau** group sắp xếp **các nhóm kết quả** theo số đơn. Một `$sort` sau group không thể quay lại điều khiển document nào đã được `$first` chọn trong group trước đó.

### 12.4. Kiểm tra pipeline bằng `explain`

Khi cần nghiên cứu đường thực thi:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$customerId",
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { totalAmount: -1 } }
])
```

Phản hồi có thể trình bày query planner, các stage và thống kê thực thi dưới cấu trúc khác nhau tùy phiên bản MongoDB và query engine. Không có một số liệu cố định áp dụng cho mọi dữ liệu; cần quan sát stage lọc, số lượng đầu vào và chi phí của group/sort trong bối cảnh thực tế.

## 13. Sử dụng `$group` trong Java MongoDB Sync Driver

Trong ứng dụng Java, MongoDB Sync Driver có thể xây pipeline từ các `Bson` stage. Ví dụ nhóm đơn hàng theo `status`, đếm số đơn và tính tổng tiền:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;
import java.util.List;

public class GroupOrdersDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu biến MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_aggregation_lab");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            List<Bson> pipeline = Arrays.asList(
                Aggregates.group(
                    "$status",
                    Accumulators.sum("orderCount", 1),
                    Accumulators.sum("totalAmount", "$total")
                ),
                Aggregates.sort(Sorts.ascending("_id"))
            );

            orders.aggregate(pipeline)
                .forEach(result ->
                    System.out.println(result.toJson())
                );
        }
    }
}
```

Ví dụ cần dependency `mongodb-driver-sync` tương thích, database thực hành có dữ liệu và biến môi trường `MONGODB_URI`. Trong Java:

- `Aggregates.group("$status", ...)` tương ứng `{$group:{_id:"$status",...}}`.
- `Accumulators.sum("orderCount", 1)` tương ứng `orderCount:{$sum:1}`.
- `Accumulators.sum("totalAmount", "$total")` tương ứng `totalAmount:{$sum:"$total"}`.
- `Aggregates.sort(...)` sắp xếp các nhóm sau khi tính xong.

### 13.1. Khóa nhóm ghép trong Java

Muốn nhóm theo `status` và `channel`:

```java
Document compoundId = new Document("status", "$status")
    .append("channel", "$channel");

List<Bson> pipeline = Arrays.asList(
    Aggregates.group(
        compoundId,
        Accumulators.sum("orderCount", 1),
        Accumulators.sum("totalAmount", "$total")
    ),
    Aggregates.sort(Sorts.ascending("_id.status", "_id.channel"))
);
```

Ở đây `Document` là đối tượng dựng **biểu thức khóa nhóm**, không phải document dữ liệu được chèn vào collection. Giá trị `"$status"` và `"$channel"` là field paths của MongoDB, không phải hằng text `"status"` và `"channel"`.

Khi dùng Spring Data MongoDB hoặc các framework khác, API tạo aggregation có thể khác, nhưng nguyên tắc `_id` quyết định nhóm và accumulator tính trên đầu vào vẫn giữ nguyên.

## 14. Các lỗi thường gặp khi dùng `$group`

| Tình huống | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Mọi document bị gom vào một nhóm `"status"` | Viết `_id: "status"` thay vì `_id: "$status"` | Dùng field path có `$` |
| Mọi document bị gom vào một nhóm `null` ngoài ý định | Field path sai hoặc dữ liệu thiếu field cần nhóm | Kiểm tra schema và đường dẫn, thử `$project` field trước |
| Nhóm thiếu/null bị gộp | Khóa field path không phân biệt hai trạng thái | Chuẩn hóa có chủ đích hoặc dùng `$type` trong composite key |
| Group theo `createdAt` tạo quá nhiều nhóm | Khóa là timestamp chính xác, không phải ngày | Dùng `$dateTrunc` hoặc `$dateToString` |
| Báo cáo theo ngày lệch khi gần nửa đêm | Không thống nhất timezone | Chỉ định timezone nghiệp vụ |
| Tổng tiền khác số đơn nhân mức giá dự kiến | `$sum: "$total"` khác `$sum: 1`; dữ liệu có thể sai kiểu | Kiểm tra kiểu BSON và ý nghĩa chỉ số |
| Số đơn theo SKU bị đếm sai | `$unwind` biến một đơn nhiều items thành nhiều dòng | Phân biệt order lines, units và unique order IDs |
| `$group` theo `items` không chia ra từng SKU | Đang gom theo **toàn array** | Dùng `$unwind` trước khi nhóm theo field của item |
| `$first` cho đơn không mới nhất | Thiếu sort đầu vào hoặc sort không xác định | `$sort` theo thời gian và khóa duy nhất trước group |
| Kết quả group lúc này sắp khác lúc trước | `$group` không bảo đảm thứ tự kết quả | `$sort` sau group |
| `$match` trên `orderCount` đặt trước group | Field tổng hợp chưa tồn tại | Đặt match trên chỉ số sau group |
| Nhiều nhóm làm pipeline tốn RAM | Cardinality khóa quá cao hoặc dùng array accumulator lớn | Lọc sớm, chọn độ hạt thích hợp và đánh giá memory/spill |
| Dùng `$addToSet` rồi kỳ vọng array có thứ tự cố định | Tập giá trị phân biệt không có cam kết thứ tự | Sắp xếp kết quả theo yêu cầu |
| Muốn lấy field gốc nhưng đặt trực tiếp cạnh `_id` | Field output của group cần accumulator phù hợp | Dùng `$first`, `$last` hoặc phép tổng hợp tương ứng sau khi xác định ý nghĩa |

## 15. Bài tập thực hành

Các bài sau dùng bộ dữ liệu mười đơn ở mục 2, chưa bị thay đổi. Hãy đọc từng yêu cầu như một quyết định **mỗi nhóm đại diện cho điều gì** trước khi viết cú pháp.

### Bài 1. Đếm số đơn theo trạng thái

Yêu cầu: tạo báo cáo gồm trạng thái, số đơn và tổng tiền. Sắp xếp theo số đơn giảm dần.

**Đáp án tham khảo:**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  },
  { $sort: { orderCount: -1, _id: 1 } }
])
```

Nhóm `paid` có 5 đơn, `pending` 3, `cancelled` 1 và nhóm thiếu status 1.

### Bài 2. Thống kê doanh thu theo khách hàng

Yêu cầu: chỉ lấy các đơn đã thanh toán, gom theo khách hàng và trả về khách hàng có tổng tiền đã thanh toán lớn hơn 400.

**Đáp án tham khảo:**

```javascript
db.orders.aggregate([
  { $match: { status: "paid" } },
  {
    $group: {
      _id: "$customerId",
      paidAmount: { $sum: "$total" }
    }
  },
  { $match: { paidAmount: { $gt: 400 } } },
  { $sort: { paidAmount: -1 } }
])
```

Kết quả chỉ có `C01` với `paidAmount: 510`. `C03` có tổng 390, không vượt 400.

### Bài 3. Khóa nhóm ghép

Yêu cầu: đếm số đơn và tổng tiền theo từng cặp `status`–`channel`.

**Đáp án tham khảo:**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        status: "$status",
        channel: "$channel"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$total" }
    }
  }
])
```

Hai nhóm `{status:"paid",channel:"web"}` và `{status:"paid",channel:"mobile"}` là **hai nhóm khác nhau**, dù cùng status.

### Bài 4. Gom theo ngày tại Việt Nam

Yêu cầu: tính số đơn mỗi ngày theo lịch Việt Nam, trả về ngày dạng chuỗi `YYYY-MM-DD`.

**Đáp án tham khảo:**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$createdAt",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
```

Kết quả theo ngày là 3, 3 và 4 đơn cho các ngày 10, 11 và 12/11/2026.

### Bài 5. Tính tổng số lượng bán theo SKU

Yêu cầu: mỗi dòng kết quả đại diện cho **một mã SKU**, tổng số lượng được tính từ `items.qty`.

**Đáp án tham khảo:**

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.qty" }
    }
  },
  { $sort: { _id: 1 } }
])
```

Kết quả: SKU `A` = 5, `B` = 4, `C` = 6. Nếu chỉ dùng `_id: "$items"` mà không unwind, ta sẽ nhóm theo **toàn mảng items của từng đơn**, không theo SKU.

### Bài 6. Phân biệt null và missing trong khóa nhóm

Yêu cầu: nhóm theo `region` nhưng phải phân biệt document **không có region** và document có `region: null`.

**Đáp án tham khảo:**

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        regionType: { $type: "$region" },
        regionValue: { $ifNull: ["$region", null] }
      },
      orderCount: { $sum: 1 }
    }
  }
])
```

Trong dữ liệu mẫu, `109` nằm ở nhóm có `regionType: "missing"`, còn `110` ở nhóm có `regionType: "null"`.

### Bài 7. Vì sao `$first` không bảo đảm là đơn sớm nhất?

Một pipeline viết:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      earliestOrderId: { $first: "$_id" }
    }
  }
])
```

Hỏi: Có thể chắc chắn `earliestOrderId` là đơn được tạo sớm nhất của khách hàng không?

**Đáp án:** Không. `$first` dùng document đầu tiên **theo thứ tự đi vào stage**, không tự tìm thời gian nhỏ nhất. Cần `$sort: {customerId:1, createdAt:1, _id:1}` trước `$group` rồi mới dùng `$first`, hoặc dùng phép tính min thích hợp nếu chỉ cần ngày nhỏ nhất.

### Bài 8. Nhận biết nhóm quá chi tiết

Yêu cầu báo cáo là “số đơn theo từng khách hàng”, nhưng một người dùng `_id: {customerId:"$customerId",orderId:"$_id"}`. Kết quả này có còn là báo cáo theo khách hàng không?

**Đáp án:** Không đúng độ hạt mong muốn. Mỗi `orderId` thường duy nhất nên gần như mỗi đơn là một nhóm, khiến `orderCount` gần như luôn bằng 1. Hãy chỉ dùng `_id: "$customerId"` cho báo cáo theo khách hàng.

## 16. Tóm tắt cách chọn khóa nhóm

Trước khi viết `$group`, hãy diễn đạt yêu cầu bằng câu **“mỗi dòng kết quả tương ứng với một ...”**. Phần còn lại của câu chính là gợi ý thiết kế `_id`:

1. **Một tổng chung:** `_id: null`.
2. **Một giá trị field:** `_id: "$fieldName"`.
3. **Một tổ hợp nhiều chiều:** `_id: {a:"$fieldA",b:"$fieldB"}`.
4. **Một ngày, một khoảng hay một loại giá trị:** `_id` là aggregation expression như `$dateToString`, `$dateTrunc` hoặc `$cond`.
5. **Một phần tử bên trong array:** cân nhắc `$unwind` rồi nhóm theo field của phần tử.

Sau khi chọn khóa, mới quyết định **accumulator**: `$sum:1` để đếm dòng đầu vào, `$sum:"$total"` để cộng giá trị, `$avg` để lấy trung bình, `$min`/`$max` để tìm cực trị, và `$push`/`$addToSet` khi thực sự cần tập hợp các giá trị.

Cuối cùng, nhớ rằng `$group` **không bảo đảm thứ tự đầu ra**; `$first`/`$last` chỉ có ý nghĩa rõ khi đầu vào được sắp xếp đúng; khóa thiếu hoặc null cần chính sách riêng; và số nhóm cùng kích thước trạng thái accumulator có thể ảnh hưởng đáng kể đến chi phí bộ nhớ. Thiết kế khóa nhóm dựa trên **độ hạt nghiệp vụ**, không chỉ trên những field sẵn có, là nền tảng để xây dựng báo cáo MongoDB chính xác và dễ duy trì.
