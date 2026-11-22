# Các mẫu subset, bucket và dữ liệu tính sẵn

> **Chương:** Thiết kế document  
> **Module:** `SPRING_DATA_MONGODB`

Trong MongoDB, thiết kế document nên bắt đầu từ **dữ liệu mà ứng dụng cần đọc, tần suất ghi, số lượng phần tử có thể tăng và mức độ nhất quán cần bảo đảm**. Ba mẫu thiết kế thường dùng để giải quyết những vấn đề khác nhau:

- **Subset pattern:** đặt một phần dữ liệu thường xuyên được xem ngay trong document chính, còn dữ liệu đầy đủ ở collection riêng.
- **Bucket pattern:** gom nhiều bản ghi nhỏ có cùng khóa hoặc khoảng thời gian vào một document có giới hạn kích thước.
- **Computed pattern (dữ liệu tính sẵn):** lưu kết quả đã tổng hợp hoặc tính toán trước để tránh quét dữ liệu gốc cho mỗi lần đọc.

Đây là **mẫu thiết kế dữ liệu**, không phải ba tính năng cần bật trong cấu hình MongoDB. Chúng có thể phối hợp với nhau và đều có chi phí duy trì dữ liệu. Trong module `SPRING_DATA_MONGODB`, việc chọn mẫu ảnh hưởng trực tiếp đến ánh xạ Java, truy vấn qua `MongoTemplate` hoặc repository, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt mục đích, cấu trúc và đánh đổi của subset, bucket, computed pattern.
2. Thiết kế collection và document theo truy vấn phổ biến, đồng thời xác định dữ liệu nguồn có thẩm quyền (*source of truth*).
3. Đọc và viết ví dụ `mongosh` có giới hạn dữ liệu và có đường cập nhật rõ ràng.
4. Dùng ánh xạ `@Document`, repository và `MongoTemplate` của Spring Data MongoDB để làm việc với các mô hình này.
5. Đánh giá tính nhất quán, khả năng mở rộng, index và hiệu quả thực tế trước khi áp dụng vào sản xuất.

## 2. Chọn mẫu từ vấn đề cần giải quyết

| Tình huống thực tế | Mẫu phù hợp | Lợi ích chính | Chi phí phải quản lý |
| --- | --- | --- | --- |
| Trang danh sách sản phẩm chỉ cần vài đánh giá gần đây, nhưng mỗi sản phẩm có hàng nghìn đánh giá | **Subset** | Đọc thẻ sản phẩm bằng một document nhỏ | Phần dữ liệu sao chép phải được làm mới |
| Thiết bị gửi nhiều phép đo nhỏ liên tục; ứng dụng đọc theo cửa sổ thời gian | **Bucket** | Giảm số document và tổ chức dữ liệu theo khoảng | Giới hạn kích thước, tranh chấp khi ghi, truy vấn cắt qua ranh giới bucket |
| Bảng điều khiển doanh thu ngày bị gọi nhiều lần trong khi dữ liệu đơn hàng thay đổi ít hơn số lần đọc | **Computed** | Trả về tổng đã tính thay vì aggregate lại toàn bộ | Kết quả có độ trễ hoặc cần cơ chế cập nhật chính xác |

Một câu hỏi hữu ích trước khi tạo collection: **trong mỗi lượt đọc, ứng dụng cần bao nhiêu dữ liệu và có phải tính toán lại từ đầu không?** Nếu chi phí chủ yếu là tải dữ liệu không cần thiết, xét subset; nếu số document nhỏ tăng rất nhanh, xét bucket; nếu phép tính tổng hợp lặp đi lặp lại, xét computed.

Không nên áp dụng các mẫu này chỉ để “giảm số collection”. Kích thước document, số lần cập nhật, fan-out truy vấn và yêu cầu chính xác có thể khiến một mẫu kém hiệu quả hơn cách lưu đơn giản.

## 3. Subset pattern: giữ phần thường dùng gần dữ liệu chính

### 3.1. Vấn đề

Ứng dụng thương mại điện tử hiển thị trang danh sách sản phẩm với tên, giá và **ba đánh giá mới nhất**. Khi vào trang đánh giá, người dùng mới cần xem hàng nghìn đánh giá có phân trang.

Nếu nhúng *toàn bộ* đánh giá vào document sản phẩm, document sẽ tăng không giới hạn và mọi lần đọc thẻ sản phẩm có nguy cơ xử lý quá nhiều dữ liệu. Nếu chỉ lưu đánh giá trong collection riêng, việc hiển thị vài đánh giá trên mỗi thẻ có thể phải thực hiện thêm nhiều lượt đọc. Subset pattern kết hợp hai nhu cầu: **nhúng phần nhỏ thường xem** và **giữ toàn bộ bản ghi ở nơi riêng**.

### 3.2. Mô hình đề xuất

```text
products
└── P-100
    ├── name, priceMinor, currency
    ├── reviewCount
    └── recentReviews: [3 bản tóm tắt mới nhất]

reviews
├── R-901: productId=P-100, stars, body, createdAt
├── R-902: productId=P-100, stars, body, createdAt
└── ...    (đầy đủ, có phân trang)
```

Document sản phẩm:

```javascript
db.products.insertOne({
  _id: "P-100",
  name: "Bàn phím cơ",
  priceMinor: NumberLong(1290000),
  currency: "VND",
  reviewCount: 2,
  recentReviews: [
    {
      reviewId: "R-902",
      stars: 5,
      summary: "Gõ êm, hoàn thiện tốt",
      createdAt: ISODate("2026-11-19T09:00:00Z")
    },
    {
      reviewId: "R-901",
      stars: 4,
      summary: "Đúng mô tả",
      createdAt: ISODate("2026-11-18T09:00:00Z")
    }
  ]
})
```

Document đánh giá đầy đủ, lưu trong collection khác:

```javascript
db.reviews.insertMany([
  {
    _id: "R-901",
    productId: "P-100",
    stars: 4,
    body: "Đúng mô tả, đóng gói kỹ, đã dùng một tuần.",
    createdAt: ISODate("2026-11-18T09:00:00Z")
  },
  {
    _id: "R-902",
    productId: "P-100",
    stars: 5,
    body: "Gõ êm, hoàn thiện tốt.",
    createdAt: ISODate("2026-11-19T09:00:00Z")
  }
])
```

Để lấy thẻ sản phẩm, có thể chỉ chiếu các trường cần hiển thị:

```javascript
db.products.find(
  { _id: "P-100" },
  { name: 1, priceMinor: 1, currency: 1, reviewCount: 1, recentReviews: 1 }
)
```

Để tải trang đánh giá:

```javascript
db.reviews
  .find({ productId: "P-100" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)

db.reviews.createIndex({ productId: 1, createdAt: -1, _id: -1 })
```

Index trên `reviews` phù hợp với thao tác lọc theo sản phẩm và sắp xếp đánh giá mới nhất. Để phân trang sâu trên tập dữ liệu lớn, cân nhắc phân trang theo khóa (dựa trên `createdAt` và `_id`) thay cho `skip` lớn.

### 3.3. Cập nhật subset

Khi đánh giá mới đã được lưu thành công trong `reviews`, ứng dụng cần cập nhật phần tóm tắt trên `products`:

```javascript
db.reviews.insertOne({
  _id: "R-903",
  productId: "P-100",
  stars: 5,
  body: "Phím ổn định sau hai ngày sử dụng.",
  createdAt: ISODate("2026-11-20T07:00:00Z")
})

db.products.updateOne(
  { _id: "P-100" },
  {
    $push: {
      recentReviews: {
        $each: [{
          reviewId: "R-903",
          stars: 5,
          summary: "Phím ổn định",
          createdAt: ISODate("2026-11-20T07:00:00Z")
        }],
        $sort: { createdAt: -1, reviewId: 1 },
        $slice: 3
      }
    },
    $inc: { reviewCount: 1 }
  }
)
```

`$push` kết hợp `$each`, `$sort` và `$slice` giữ **tối đa ba** đánh giá trong document sản phẩm; `$inc` tăng bộ đếm. Cập nhật các trường trong **một** document sản phẩm là nguyên tử. Nhưng thao tác thêm document vào `reviews` và cập nhật `products` là **hai lần ghi vào hai document khác nhau**; chúng không mặc nhiên tạo thành một giao dịch nguyên tử.

Trong sản xuất, cần chọn chính sách cập nhật:

- **Chấp nhận độ trễ:** `reviews` là nguồn có thẩm quyền, sau đó worker/event cập nhật `recentReviews`; phải chống xử lý sự kiện lặp bằng mã sự kiện hoặc `reviewId`.
- **Cần nhìn thấy đồng thời:** cân nhắc transaction nhiều document trên triển khai MongoDB hỗ trợ, nhưng vẫn cần xử lý retry và bảo đảm bộ đếm không tăng hai lần.
- **Sửa/xóa đánh giá:** phải cập nhật lại bộ đếm và có thể **tính lại top 3** từ `reviews`, vì phần tử mới thích hợp có thể nằm ngoài subset hiện tại.

Subset không phải dữ liệu chuẩn để liệt kê **tất cả** đánh giá. Nếu phải bảo đảm đồng bộ nghiêm ngặt nhưng tần suất ghi cao, hãy đánh giá xem chỉ lưu collection `reviews` và truy vấn thêm có đơn giản, tin cậy hơn không.

### 3.4. Khi nào nên và không nên dùng?

Nên cân nhắc khi dữ liệu con có thể rất lớn, nhưng phần được đọc nhiều nhất nhỏ và tương đối ổn định (ví dụ vài địa chỉ gần nhất, vài thông báo gần đây, thumbnail của các ảnh). Tránh nhúng subset khi bản ghi con biến động liên tục đến mức việc nhân bản/cập nhật tốn hơn việc truy vấn trực tiếp, hoặc khi yêu cầu nghiệp vụ không cho phép kết quả cũ dù chỉ trong thời gian ngắn.

## 4. Bucket pattern: nhóm bản ghi nhỏ thành document có giới hạn

### 4.1. Vấn đề

Một cảm biến gửi giá trị nhiệt độ mỗi vài giây. Nếu lưu mỗi phép đo vào một document riêng, hệ thống sẽ tạo nhiều document và ứng dụng thường phải đọc chúng theo từng khoảng thời gian. Bucket pattern gom các phép đo chung thiết bị và cửa sổ thời gian vào một document.

**Ranh giới bucket phải hữu hạn.** Số phần tử trong array, kích thước document và tần suất nhiều writer cùng cập nhật một document là các ràng buộc chính. MongoDB có giới hạn **16 MiB cho một BSON document** thông thường; trong thực tế nên thiết kế giới hạn thấp hơn đáng kể.

### 4.2. Ví dụ bucket theo phút

```javascript
db.readingBuckets.insertOne({
  _id: "S-01|2026-11-20T09:00:00Z|0",
  deviceId: "S-01",
  bucketStart: ISODate("2026-11-20T09:00:00Z"),
  bucketEnd: ISODate("2026-11-20T09:01:00Z"),
  segmentNo: 0,
  sampleCount: 3,
  sumValue: 75.2,
  minValue: 24.8,
  maxValue: 25.3,
  samples: [
    { at: ISODate("2026-11-20T09:00:05Z"), value: 24.8 },
    { at: ISODate("2026-11-20T09:00:15Z"), value: 25.1 },
    { at: ISODate("2026-11-20T09:00:25Z"), value: 25.3 }
  ]
})
```

- `deviceId` là khóa phân nhóm. `bucketStart` và `bucketEnd` xác định khoảng **[start, end)** theo UTC.
- `segmentNo` cho phép chia một khoảng thời gian thành nhiều document nếu có quá nhiều phép đo; `_id` của ví dụ ghép các thành phần để bảo đảm định danh.
- `samples` chứa các bản ghi gốc của một bucket; `sampleCount`, `sumValue`, `minValue`, `maxValue` là số liệu tính cùng bucket để phục vụ thống kê.
- Với mẫu dữ liệu này, trung bình nhiệt độ của bucket là `sumValue / sampleCount`; chỉ lấy trung bình từ các bucket khác nhau rồi chia đều sẽ sai khi số mẫu mỗi bucket khác nhau.

Tạo index theo mẫu truy vấn:

```javascript
db.readingBuckets.createIndex({
  deviceId: 1,
  bucketStart: 1,
  segmentNo: 1
})

db.readingBuckets
  .find({
    deviceId: "S-01",
    bucketStart: {
      $gte: ISODate("2026-11-20T09:00:00Z"),
      $lt: ISODate("2026-11-20T10:00:00Z")
    }
  })
  .sort({ bucketStart: 1, segmentNo: 1 })
```

Truy vấn trên lấy bucket **bắt đầu** trong khoảng đã cho. Nếu bộ lọc yêu cầu các phép đo ở một khoảng *không trùng ranh giới bucket*, phải lấy cả bucket giao với khoảng đó rồi lọc thêm từng `samples.at`; nếu không dễ bỏ sót phép đo trong bucket bắt đầu trước mốc truy vấn.

### 4.3. Ghi thêm phép đo và kiểm soát sức chứa

Giả sử hệ thống quy định mỗi segment chứa tối đa **100 phép đo**. Khi bucket đã tồn tại:

```javascript
db.readingBuckets.updateOne(
  {
    _id: "S-01|2026-11-20T09:00:00Z|0",
    sampleCount: { $lt: 100 }
  },
  {
    $push: {
      samples: {
        at: ISODate("2026-11-20T09:00:35Z"),
        value: 25.0
      }
    },
    $inc: { sampleCount: 1, sumValue: 25.0 },
    $min: { minValue: 25.0 },
    $max: { maxValue: 25.0 }
  }
)
```

Điều kiện `sampleCount < 100` và các thay đổi trong **một** update được MongoDB thực thi nguyên tử trên document. Nếu `matchedCount = 0`, ứng dụng cần phân biệt bucket không tồn tại với bucket đã đầy. Khi đầy, nó phải chọn segment mới theo quy tắc phân bổ đã định và xử lý tranh chấp tạo segment; khi không tồn tại, có thể tạo bucket với dữ liệu khởi tạo đúng.

Đoạn mã **không tự tạo segment mới**, cũng không bảo đảm một phép đo được ghi đúng một lần khi client retry. Trong hệ thống thực tế cần:

1. Một khóa định danh phép đo hoặc chiến lược deduplication để tránh append trùng khi retry/nhận lại message.
2. Giới hạn phần tử **và kích thước byte** của bucket (khi payload từng mẫu không đồng đều, giới hạn phần tử chưa đủ).
3. Cơ chế tạo/chọn segment có xử lý ghi đồng thời và xung đột unique key.
4. Theo dõi contention nếu nhiều producer cùng ghi vào một bucket “nóng”; có thể dùng các segment độc lập hoặc chia khóa.

Không nên hiểu việc đưa nhiều sự kiện vào một document là cách tự động tăng thông lượng ghi. Bucket quá lớn hoặc quá nóng có thể trở thành điểm nghẽn.

### 4.4. Tổng hợp trực tiếp từ bucket

Vì mỗi bucket có `sumValue` và `sampleCount`, ta tính nhiệt độ trung bình cho thiết bị trong khoảng bucket đầy đủ bằng:

```javascript
db.readingBuckets.aggregate([
  {
    $match: {
      deviceId: "S-01",
      bucketStart: {
        $gte: ISODate("2026-11-20T09:00:00Z"),
        $lt: ISODate("2026-11-20T10:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$deviceId",
      sum: { $sum: "$sumValue" },
      count: { $sum: "$sampleCount" },
      min: { $min: "$minValue" },
      max: { $max: "$maxValue" }
    }
  },
  {
    $project: {
      _id: 0,
      deviceId: "$_id",
      count: 1,
      min: 1,
      max: 1,
      average: {
        $cond: [
          { $gt: ["$count", 0] },
          { $divide: ["$sum", "$count"] },
          null
        ]
      }
    }
  }
])
```

Kết quả chỉ đúng khi `sumValue`, `sampleCount`, `minValue`, `maxValue` được duy trì chính xác và **mỗi phép đo thực sự thuộc đúng một bucket**. Với truy vấn cắt giữa bucket, cần tính lại trên các `samples` nằm trong khoảng hoặc có cấu trúc rollup hạt mịn hơn.

### 4.5. Bucket thủ công và time-series collection

MongoDB có **time-series collection** được tối ưu hóa cho dữ liệu đo đạc có timestamp; máy chủ tự quản lý chi tiết lưu trữ kiểu bucket nội bộ. Trước khi tự xây bucket bằng array, hãy đánh giá time-series collection nếu dữ liệu chủ yếu là phép đo theo thời gian. Bucket thủ công thích hợp khi nghiệp vụ cần kiểm soát rõ cấu trúc nhóm, số mục trong một trang lịch sử, dữ liệu tổng hợp gắn với nhóm hoặc cách phân đoạn riêng.

Hai hướng này không đồng nhất: time-series collection vẫn được ứng dụng truy vấn như các phép đo, còn document trong `readingBuckets` ở ví dụ là một schema do **ứng dụng** tự thiết kế.

## 5. Computed pattern: lưu kết quả đã tính để đọc nhanh

### 5.1. Vấn đề

Một dashboard cần hiển thị **doanh thu từng ngày của từng cửa hàng**. Nếu mỗi lần mở trang đều chạy aggregation trên hàng triệu đơn hàng, số lần tính lặp lại có thể cao hơn nhiều so với tốc độ thay đổi đơn.

Computed pattern lưu kết quả phép tính dưới dạng một document riêng hoặc field tính sẵn. Dữ liệu nguồn vẫn là collection `orders`; collection `dailyRevenue` được dùng như **bảng tổng hợp có thể tái tạo**.

```text
orders (nguồn có thẩm quyền)
    │
    └── lọc đơn đã thanh toán + group theo cửa hàng/ngày/tiền tệ
           │
           ▼
dailyRevenue (kết quả tính sẵn)
    └── { storeId, day, currency, orderCount, amountMinor }
           │
           ▼
    Dashboard đọc vài document tổng hợp
```

### 5.2. Định nghĩa phép tính trước khi lưu

Ví dụ nghiệp vụ quy định một đơn được tính khi `status = "PAID"`; `totalMinor` là số tiền ở **đơn vị tiền tệ nhỏ nhất** (VND có thể dùng số đồng nguyên), và `paidAt` là thời điểm thanh toán.

```javascript
db.orders.insertMany([
  {
    _id: "O-001",
    storeId: "STORE-01",
    status: "PAID",
    paidAt: ISODate("2026-11-19T02:00:00Z"),
    currency: "VND",
    totalMinor: NumberLong(150000)
  },
  {
    _id: "O-002",
    storeId: "STORE-01",
    status: "PAID",
    paidAt: ISODate("2026-11-19T05:00:00Z"),
    currency: "VND",
    totalMinor: NumberLong(250000)
  }
])
```

Trong ví dụ, doanh thu ngày địa phương 19/11 là **400.000 VND từ 2 đơn**. Cần định nghĩa rõ liệu hoàn tiền, đơn bị hủy, thuế, phí vận chuyển và thay đổi trạng thái có được cộng/trừ trong chỉ số hay không. Một tên field như `revenue` không đủ để bảo đảm báo cáo đúng nghiệp vụ.

### 5.3. Tạo và cập nhật collection tổng hợp bằng aggregation

Ví dụ yêu cầu MongoDB hỗ trợ `$dateTrunc` (MongoDB 5.0 trở lên). Trước khi dùng `$merge` với khóa ghép tùy chỉnh, collection đích cần có unique index tương thích các field `on`.

```javascript
db.dailyRevenue.createIndex(
  { storeId: 1, day: 1, currency: 1 },
  { unique: true }
)

db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: {
        storeId: "$storeId",
        day: {
          $dateTrunc: {
            date: "$paidAt",
            unit: "day",
            timezone: "Asia/Ho_Chi_Minh"
          }
        },
        currency: "$currency"
      },
      orderCount: { $sum: 1 },
      amountMinor: { $sum: "$totalMinor" }
    }
  },
  {
    $project: {
      _id: 0,
      storeId: "$_id.storeId",
      day: "$_id.day",
      currency: "$_id.currency",
      orderCount: 1,
      amountMinor: 1
    }
  },
  {
    $merge: {
      into: "dailyRevenue",
      on: ["storeId", "day", "currency"],
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
])
```

`$dateTrunc` gom theo ngày ở múi giờ `Asia/Ho_Chi_Minh`; trường BSON Date vẫn biểu diễn một thời điểm UTC tương ứng với đầu ngày địa phương. Nhóm theo `currency` để **không cộng lẫn các loại tiền**. `$merge` ghi kết quả vào collection đích; chạy lại cùng tập dữ liệu và cùng khóa có thể thay thế giá trị nhóm thay vì cộng dồn hai lần.

Đọc kết quả:

```javascript
db.dailyRevenue.find({
  storeId: "STORE-01",
  currency: "VND",
  day: {
    $gte: ISODate("2026-11-18T17:00:00Z"),
    $lt: ISODate("2026-11-19T17:00:00Z")
  }
})
```

**Chú ý tính đúng đắn khi làm mới:** `$merge` chỉ xử lý những nhóm còn xuất hiện trong nguồn aggregation. Nếu một ngày trước có đơn `PAID` nhưng sau đó **không còn đơn nào đủ điều kiện**, nhóm cũ có thể vẫn tồn tại trong `dailyRevenue`. Khi triển khai quy trình rebuild, phải xử lý cả việc **xóa nhóm đã biến mất** hoặc xây tập mới rồi hoán đổi theo chiến lược phù hợp; không nên xem `$merge` là lệnh đồng bộ xóa.

### 5.4. Tính theo lịch hay cập nhật khi ghi?

| Cách duy trì | Phù hợp khi | Điểm cần giải quyết |
| --- | --- | --- |
| Batch định kỳ tính lại từ `orders` | Dashboard chấp nhận trễ vài phút/giờ | Lập lịch, chi phí quét, nhóm cũ cần xóa, chạy lại an toàn |
| Incremental khi đơn chuyển sang `PAID` | Muốn kết quả cập nhật nhanh | Cộng/trừ đúng một lần, chuyển trạng thái, duplicate event, xử lý thất bại giữa các lần ghi |
| Transaction nhiều document | Có yêu cầu nhất quán chặt giữa nguồn và tổng hợp | Môi trường hỗ trợ transaction, retry khi xung đột, chi phí giao dịch |
| Đọc tổng hợp trực tiếp mỗi lần | Dữ liệu nhỏ hoặc yêu cầu luôn tính từ nguồn | Độ trễ truy vấn và chi phí aggregation |

Ví dụ khi xử lý **một sự kiện thanh toán đã được xác thực là mới**, hệ thống có thể cập nhật document tổng hợp bằng `$inc` và `upsert`:

```javascript
db.dailyRevenue.updateOne(
  {
    storeId: "STORE-01",
    day: ISODate("2026-11-18T17:00:00Z"),
    currency: "VND"
  },
  {
    $inc: {
      orderCount: 1,
      amountMinor: NumberLong(150000)
    }
  },
  { upsert: true }
)
```

Lệnh này **không tự chống sự kiện trùng**: nếu xử lý lại cùng một đơn, `$inc` sẽ cộng hai lần. Cần giữ trạng thái đã áp dụng của từng sự kiện/đơn và áp dụng idempotency (ví dụ unique key của ledger cập nhật cùng transaction phù hợp, hoặc tính lại từ dữ liệu nguồn theo chu kỳ). Hoàn tiền hoặc đơn đổi trạng thái cũng cần quy tắc bù trừ rõ ràng.

Nếu một field tính sẵn nằm ngay trên document chính, chẳng hạn `ratingCount` và `ratingSum` ở sản phẩm, có thể cập nhật cùng document bằng `$inc`; `ratingAverage = ratingSum / ratingCount` khi đọc. Đây cũng là computed pattern. Tuy nhiên nếu bản ghi đánh giá gốc nằm ở collection khác thì câu hỏi đồng bộ nhiều document vẫn còn.

## 6. Áp dụng trong Spring Data MongoDB

Spring Data MongoDB không áp đặt subset, bucket hay computed pattern. Ta ánh xạ **schema đã thiết kế** sang Java, sau đó chọn repository hoặc `MongoTemplate` phù hợp với cách đọc/ghi.

### 6.1. Ánh xạ một bucket

Ví dụ dùng Java record; mã sau có thể đặt trong file `ReadingBucket.java`:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "readingBuckets")
public record ReadingBucket(
    @Id String id,
    String deviceId,
    Instant bucketStart,
    Instant bucketEnd,
    int segmentNo,
    int sampleCount,
    double sumValue,
    double minValue,
    double maxValue,
    List<Sample> samples
) {
    public record Sample(Instant at, double value) {}
}
```

Tên thuộc tính Java được ánh xạ trực tiếp đến field tương ứng trong ví dụ BSON. Vì `_id` là chuỗi ghép do ứng dụng tạo, `String id` biểu diễn đúng kiểu lưu trữ được chọn.

Đọc các bucket bằng `MongoTemplate` trong một service:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ReadingBucketQueryService {
    private final MongoTemplate mongoTemplate;

    public ReadingBucketQueryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<ReadingBucket> findBuckets(
            String deviceId, Instant from, Instant to) {
        Query query = Query.query(
                Criteria.where("deviceId").is(deviceId)
                    .and("bucketStart").gte(from).lt(to))
            .with(Sort.by(
                Sort.Direction.ASC, "bucketStart", "segmentNo"));

        return mongoTemplate.find(query, ReadingBucket.class);
    }
}
```

Hàm này được dùng khi `from`, `to` là ranh giới bucket thích hợp. Nếu cần truy vấn phép đo theo khoảng bất kỳ, service phải tìm những bucket **giao khoảng** và lọc theo `Sample.at` trước khi trả dữ liệu.

**Lưu ý về độ chính xác:** `double` phù hợp với nhiều giá trị đo có sai số chấp nhận được, nhưng không phù hợp để biểu diễn tiền tệ. Với tổng tiền, dùng kiểu số nguyên theo đơn vị nhỏ nhất hoặc `Decimal128` với quy ước rõ ràng.

### 6.2. Ánh xạ kết quả tính sẵn qua repository

File `DailyRevenue.java`:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "dailyRevenue")
public record DailyRevenue(
    @Id String id,
    String storeId,
    Instant day,
    String currency,
    long orderCount,
    long amountMinor
) {}
```

File `DailyRevenueRepository.java`:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface DailyRevenueRepository
        extends MongoRepository<DailyRevenue, String> {

    List<DailyRevenue>
    findByStoreIdAndCurrencyAndDayGreaterThanEqualAndDayLessThan(
        String storeId,
        String currency,
        Instant fromInclusive,
        Instant toExclusive
    );
}
```

Spring Data suy ra điều kiện lọc từ tên thuộc tính Java của `DailyRevenue`. Nếu dùng tên field BSON khác tên Java, hãy khai báo `@Field` tương ứng và nhớ kiểm tra index trên **tên field lưu trữ**. Với định dạng này, repository hỗ trợ việc *đọc*, nhưng quy trình tạo lại tổng hợp vẫn cần được triển khai tường minh bằng job, aggregation hoặc xử lý sự kiện.

Với phép tính phức tạp, `MongoTemplate` cung cấp Aggregation API; khi tính bằng Java nên dùng `Aggregation` và `AggregationOperation` thay vì lắp ghép pipeline từ chuỗi JSON khó kiểm soát. `ReactiveMongoTemplate` và reactive repository thay đổi mô hình thực thi bất đồng bộ nhưng **không tự giải quyết tính nhất quán của dữ liệu tính sẵn**.

### 6.3. Cập nhật theo nguồn hay theo bản sao?

Đặt quy tắc sở hữu dữ liệu ngay trong service:

- `reviews` giữ nội dung đánh giá đầy đủ; `products.recentReviews` là bản tóm tắt hiển thị có thể xây lại.
- Nếu dùng bucket thủ công, `readingBuckets.samples` có thể là nguồn có thẩm quyền cho phép đo **khi** ingestion bảo đảm không mất/trùng; các field `sumValue`, `sampleCount` là dẫn xuất.
- `orders` giữ thông tin đơn hàng; `dailyRevenue` là kết quả có thể tái tạo từ các đơn đủ điều kiện.

Việc ghi dữ liệu dẫn xuất cần có kế hoạch **retry, đối soát, rebuild, giám sát độ trễ**. Annotation ánh xạ không thay thế được các quy tắc nghiệp vụ này.

## 7. Index, giới hạn lưu trữ và hiệu năng

Các mẫu không tự động nhanh hơn. Đánh giá chúng dựa trên truy vấn và chi phí ghi thực tế:

| Mẫu | Index tiêu biểu | Chỉ số nên quan sát | Rủi ro phổ biến |
| --- | --- | --- | --- |
| Subset | `reviews(productId, createdAt, _id)` | Số document đọc để dựng thẻ; kích thước document `products`; số lượt truy vấn | Subset lỗi thời, nhân bản dữ liệu, document lớn vì nhúng quá nhiều |
| Bucket | `readingBuckets(deviceId, bucketStart, segmentNo)` | Kích thước và số mẫu mỗi bucket; write latency; contention; số bucket/khung thời gian | Bucket nóng, array không giới hạn, trùng phép đo, sai ở ranh giới |
| Computed | Unique `dailyRevenue(storeId, day, currency)` | Thời gian đọc dashboard; thời gian chạy job; độ trễ so với nguồn; chênh lệch tổng | Dữ liệu cũ, tính trùng, nhóm đã biến mất còn tồn tại |

Ví dụ dùng `explain("executionStats")` để xem kế hoạch truy vấn:

```javascript
db.reviews
  .find({ productId: "P-100" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Theo dõi `totalDocsExamined`, `totalKeysExamined`, thời gian xử lý, kích thước document và chỉ số hệ thống trong môi trường có dữ liệu đại diện. Với các document bucket, cần đo chi phí **ghi** chứ không chỉ tốc độ truy vấn.

Một số nguyên tắc:

1. Index giúp tìm document, nhưng không khắc phục được việc tải nhiều field/array không cần thiết. Dùng projection khi phù hợp.
2. Index cần chọn theo điều kiện lọc và thứ tự sắp xếp thực tế. Mỗi index bổ sung tiêu tốn bộ nhớ, dung lượng và công sức cập nhật khi ghi.
3. Dữ liệu nguồn và dữ liệu tính sẵn nên có thời hạn lưu/chiến lược làm mới rõ ràng; TTL hoặc chính sách xóa phải khớp nhu cầu báo cáo và truy vết.
4. Ranh giới document ảnh hưởng đến tính nguyên tử. Một lệnh update trên một document là nguyên tử; thao tác trải qua nhiều document cần giao thức ứng dụng hoặc transaction khi cần.

## 8. Kiểm thử và đối soát

Chỉ kiểm thử “đã insert được” chưa đủ để chứng minh một mẫu thiết kế hoạt động chính xác.

**Subset**

- Tạo nhiều hơn ba đánh giá và kiểm tra `recentReviews` luôn có tối đa ba mục, đúng thứ tự.
- Tạo đánh giá cùng timestamp và kiểm tra tie-break nhất quán.
- Mô phỏng cập nhật lặp do retry, sửa/xóa đánh giá, consumer mất kết nối; đối chiếu `reviewCount` và các đánh giá mới nhất với `reviews`.

**Bucket**

- Ghi đến đúng giới hạn 100 mục, rồi ghi mục thứ 101; kiểm tra quy tắc tạo segment mới và không mất bản ghi.
- Kiểm tra nhiều producer cùng ghi, retry cùng phép đo, phép đo đến muộn, dữ liệu lệch thứ tự.
- Kiểm tra truy vấn có hai đầu mút nằm giữa bucket, trường hợp bucket rỗng và trường hợp kích thước payload tăng đột biến.

**Computed**

- So sánh tổng từ `dailyRevenue` với aggregation trực tiếp trên `orders` theo cùng bộ lọc, múi giờ và tiền tệ.
- Mô phỏng đổi trạng thái `PAID` sang trạng thái không đủ điều kiện, hoàn tiền và nhóm không còn đơn; kiểm tra việc trừ/xóa.
- Chạy job rebuild nhiều lần để kiểm tra idempotency; mô phỏng mất job, cập nhật đồng thời và sự kiện lặp.

Trong Spring Data, có thể viết kiểm thử tích hợp trên MongoDB chạy trong môi trường cô lập (chẳng hạn Testcontainers khi hạ tầng dự án cho phép) để xác nhận BSON, mapping, update operator, index và transaction ở cấu hình tương đương thực tế. Test đơn vị chỉ mock repository không đủ để phát hiện sai cú pháp aggregation hoặc sai khác kiểu BSON.

## 9. Ba sai lầm thiết kế thường gặp

### “Subset là cache, nên có thể cập nhật tùy ý”

Subset là bản sao có **hợp đồng rõ ràng**: lấy mấy phần tử, sắp theo khóa nào, làm mới khi nào, chấp nhận trễ bao lâu. Nếu không có nguồn có thẩm quyền và quy trình rebuild, việc nhân bản field có thể làm dữ liệu mâu thuẫn.

### “Bucket càng lớn thì càng tối ưu”

Bucket lớn hơn có thể giảm số document, nhưng tăng chi phí đọc/cập nhật, làm phình array và tạo tranh chấp giữa producer. Kích thước phù hợp phụ thuộc phân bố lượng dữ liệu, khoảng thời gian truy vấn, giới hạn byte và tải đồng thời; không có một số lượng mục tối ưu cho mọi hệ thống.

### “Dữ liệu tính sẵn luôn chính xác như nguồn”

Số liệu tính sẵn có thể trễ, bị cộng lặp hoặc không được xóa khi nguồn thay đổi. Muốn có độ chính xác cao cần quy tắc trạng thái, cập nhật idempotent, transaction khi phù hợp, và phép đối soát/rebuild theo nguồn.

## 10. Bài tập áp dụng

Một dịch vụ logistics có 50.000 kiện hàng; mỗi kiện có hàng nghìn sự kiện vị trí và trạng thái. Trang danh sách hiển thị **trạng thái mới nhất**, trang chi tiết mở **50 sự kiện gần đây**, còn dashboard hiển thị **số kiện giao thành công theo ngày và khu vực**.

Hãy xác định:

1. Dữ liệu gốc nào cần lưu đầy đủ và có thể phân trang?
2. Có nên đặt `latestStatus` và 50 sự kiện gần nhất vào document kiện hàng? Giới hạn và cách cập nhật ra sao?
3. Khi sự kiện vị trí sinh liên tục, có nên dùng bucket thủ công, time-series collection hay document riêng theo sự kiện?
4. Số kiện giao thành công theo ngày được tính bằng aggregation trực tiếp hay duy trì một collection tổng hợp? Cần xử lý thế nào nếu trạng thái đơn bị sửa?

**Hướng giải tham khảo:** giữ lịch sử sự kiện làm nguồn đầy đủ; có thể lưu `latestStatus` và một subset có giới hạn khi các màn hình đọc nhiều. Chọn cách lưu chuỗi sự kiện dựa trên tốc độ phát sinh, yêu cầu truy vấn/TTL và tải ghi; dữ liệu thuần theo thời gian có thể phù hợp với time-series collection. Dashboard có thể dùng computed pattern nếu lượng đọc lớn, với định nghĩa chính xác về “giao thành công” và quy trình hiệu chỉnh khi trạng thái thay đổi. Kết luận cuối cùng phải được kiểm chứng bằng truy vấn, tần suất cập nhật và đo hiệu năng thực tế.

## Ghi nhớ

**Subset** tối ưu lượng dữ liệu đọc trong luồng phổ biến; **bucket** tổ chức một lượng lớn sự kiện nhỏ thành nhóm có giới hạn; **computed** chuyển chi phí tính toán lặp lại sang giai đoạn cập nhật hoặc xử lý định kỳ. Với cả ba mẫu, hãy giữ rõ nguồn có thẩm quyền, ranh giới document, cách cập nhật, khả năng phục hồi và mức độ nhất quán cần thiết. Spring Data MongoDB cung cấp công cụ ánh xạ, truy vấn, aggregation và giao dịch để hiện thực hóa lựa chọn đó, nhưng chính thiết kế dữ liệu và quy trình vận hành quyết định kết quả.
