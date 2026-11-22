# Đếm bằng `$count` và tổng hợp tần suất bằng `$sortByCount` trong MongoDB

## 1. Đếm số document và đếm tần suất là hai câu hỏi khác nhau

Trong một ứng dụng bán hàng, nhà quản trị có thể muốn biết:

1. **Có bao nhiêu đơn hàng đã thanh toán?**
2. **Mỗi trạng thái đơn hàng xuất hiện bao nhiêu lần?**
3. **Những thẻ (tag) nào được dùng nhiều nhất?**
4. **Có bao nhiêu quốc gia phát sinh đơn hàng và tỷ trọng từng quốc gia ra sao?**

Hai toán tử dạng **aggregation pipeline stage** của MongoDB thường giúp trả lời nhanh những yêu cầu đầu tiên:

- **`$count`** đếm **số document đi tới stage đó** và trả một document chứa con số tổng.
- **`$sortByCount`** nhóm các document theo giá trị của **một biểu thức**, đếm số document trong từng nhóm, rồi **sắp xếp theo tần suất giảm dần**.

Ví dụ:

```javascript
// Một con số: số đơn hàng có trạng thái PAID.
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "paidOrders" }
]);

// Nhiều nhóm: mỗi trạng thái xuất hiện bao nhiêu lần?
db.orders.aggregate([
  { $sortByCount: "$status" }
]);
```

**Cả hai đều đếm document trong luồng aggregation**, nhưng khác cách trả kết quả:

| Thành phần | Câu hỏi | Hình dạng kết quả |
|---|---|---|
| `$count` | Tổng cộng bao nhiêu document đi tới đây? | Một document như `{ total: 8 }` nếu đầu vào không rỗng |
| `$sortByCount` | Có những giá trị nhóm nào và mỗi giá trị xuất hiện mấy lần? | Nhiều document như `{ _id: "PAID", count: 4 }` |
| `$group` + `$sum: 1` | Tự định nghĩa khóa nhóm và phép đếm/tổng hợp | Linh hoạt: một hoặc nhiều nhóm, thêm nhiều accumulator |

Đây là **stage**, không phải các toán tử đặt trực tiếp vào query filter của `find()`. Cú pháp, vị trí và ý nghĩa phụ thuộc nơi chúng xuất hiện trong pipeline.

## 2. Bộ dữ liệu thực hành

Các ví dụ dùng **mongosh**, collection `salesOrdersLesson` trên database thử nghiệm. Hãy chèn dữ liệu một lần vào collection chưa có những `_id` này:

```javascript
db.salesOrdersLesson.insertMany([
  {
    _id: "O01",
    customerId: "C01",
    status: "PAID",
    country: "VN",
    channel: "web",
    tags: ["new", "vip"],
    amount: 340000,
    items: [
      { sku: "P01", quantity: 1 },
      { sku: "P02", quantity: 2 }
    ],
    createdAt: ISODate("2026-11-01T09:00:00Z")
  },
  {
    _id: "O02",
    customerId: "C02",
    status: "PAID",
    country: "VN",
    channel: "app",
    tags: ["sale"],
    amount: 90000,
    items: [{ sku: "P02", quantity: 1 }],
    createdAt: ISODate("2026-11-02T09:00:00Z")
  },
  {
    _id: "O03",
    customerId: "C03",
    status: "PENDING",
    country: "SG",
    channel: "web",
    tags: [],
    amount: 250000,
    items: [{ sku: "P03", quantity: 1 }],
    createdAt: ISODate("2026-11-03T09:00:00Z")
  },
  {
    _id: "O04",
    customerId: "C04",
    status: "CANCELLED",
    country: "VN",
    channel: "web",
    tags: ["sale", "vip"],
    amount: 120000,
    items: [
      { sku: "P02", quantity: 1 },
      { sku: "P04", quantity: 1 }
    ],
    createdAt: ISODate("2026-11-04T09:00:00Z")
  },
  {
    _id: "O05",
    customerId: "C05",
    status: "PAID",
    country: "TH",
    channel: "app",
    tags: ["new"],
    amount: 180000,
    items: [{ sku: "P05", quantity: 1 }],
    createdAt: ISODate("2026-11-05T09:00:00Z")
  },
  {
    _id: "O06",
    customerId: "C01",
    status: "PAID",
    country: "VN",
    channel: "web",
    tags: ["vip"],
    amount: 450000,
    items: [
      { sku: "P01", quantity: 1 },
      { sku: "P03", quantity: 1 },
      { sku: "P05", quantity: 1 }
    ],
    createdAt: ISODate("2026-11-06T09:00:00Z")
  },
  {
    _id: "O07",
    customerId: "C06",
    status: null,
    country: "TH",
    channel: "app",
    tags: [],
    amount: 0,
    items: [],
    createdAt: ISODate("2026-11-07T09:00:00Z")
  },
  {
    _id: "O08",
    customerId: "C07",
    // Cố ý không có trường status.
    country: "VN",
    channel: "partner",
    tags: ["sale"],
    amount: 110000,
    items: [{ sku: "P04", quantity: 1 }],
    createdAt: ISODate("2026-11-08T09:00:00Z")
  }
]);
```

Dữ liệu có **8 document**. Trong đó có 4 đơn `PAID`, 1 `PENDING`, 1 `CANCELLED`, 1 đơn có `status: null` và 1 đơn **thiếu trường `status`**. Hai trường hợp cuối được đưa vào để xem cách nhóm dữ liệu thiếu/null.

| `_id` | `status` | `country` | `channel` | `tags` |
|---|---|---|---|---|
| O01 | PAID | VN | web | new, vip |
| O02 | PAID | VN | app | sale |
| O03 | PENDING | SG | web | mảng rỗng |
| O04 | CANCELLED | VN | web | sale, vip |
| O05 | PAID | TH | app | new |
| O06 | PAID | VN | web | vip |
| O07 | null | TH | app | mảng rỗng |
| O08 | Không tồn tại | VN | partner | sale |

Tất cả kết quả số liệu trong bài giả định collection chỉ có tám document này và **chưa có thao tác cập nhật dữ liệu** sau khi chèn.

## 3. Cách viết `$count`

### 3.1. Cú pháp

```javascript
db.collection.aggregate([
  { $count: "tenTruongKetQua" }
]);
```

`$count` nhận **một chuỗi** đặt tên trường sẽ chứa kết quả đếm. Tên phải hợp lệ: không rỗng, không bắt đầu bằng `$` và không chứa dấu chấm `.`.

Ví dụ:

```javascript
db.salesOrdersLesson.aggregate([
  { $count: "totalOrders" }
]);
```

Kết quả:

```javascript
{ totalOrders: 8 }
```

Stage `$count` không trả mảng tám document, cũng không thêm trường `totalOrders` vào từng document gốc. Nó **tiêu thụ luồng đầu vào** và tạo **một document tổng hợp** nếu có ít nhất một document đầu vào.

### 3.2. Đếm sau `$match`

Muốn đếm đơn đã thanh toán:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { status: "PAID" } },
  { $count: "paidOrders" }
]);
```

Kết quả:

```javascript
{ paidOrders: 4 }
```

Luồng dữ liệu:

```text
8 document trong salesOrdersLesson
              |
              v
  $match: status = "PAID"
              |
              v
       4 document còn lại
              |
              v
    $count: "paidOrders"
              |
              v
       { paidOrders: 4 }
```

**Vị trí của `$count` quyết định nó đếm cái gì.** Nó không đếm mặc định số document trong collection nếu phía trước có `$match`, `$unwind`, `$group`, `$limit` hoặc những stage khác làm thay đổi số lượng document.

### 3.3. Đếm theo nhiều điều kiện

```javascript
db.salesOrdersLesson.aggregate([
  {
    $match: {
      status: "PAID",
      country: "VN"
    }
  },
  { $count: "paidOrdersInVN" }
]);
```

Kết quả:

```javascript
{ paidOrdersInVN: 3 }
```

Ba đơn là O01, O02 và O06. Nếu muốn tổng đơn ở VN bất kể trạng thái, bỏ điều kiện `status` và kết quả sẽ là **5**.

### 3.4. Đếm trên khoảng thời gian

```javascript
db.salesOrdersLesson.aggregate([
  {
    $match: {
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-11-06T00:00:00Z")
      }
    }
  },
  { $count: "ordersInPeriod" }
]);
```

Kết quả là `{ ordersInPeriod: 5 }`, tương ứng O01 đến O05. Với báo cáo theo ngày/tháng, nên xác định **múi giờ và khoảng thời gian nửa mở** `[start, end)` rõ ràng. Không nên mặc định mọi timestamp trong ứng dụng đều đã ở UTC nếu hệ thống chưa quy định điều đó.

## 4. Điều ít người để ý: `$count` với đầu vào rỗng không trả `{ total: 0 }`

Giả sử không có đơn nào mang trạng thái `"REFUNDED"` trong bộ mẫu:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { status: "REFUNDED" } },
  { $count: "total" }
]);
```

**Kết quả pipeline là không có document đầu ra**:

```javascript
// Trong cách biểu diễn thành mảng:
[]
```

Không phải:

```javascript
// KHÔNG phải kết quả mặc định của $count với đầu vào rỗng.
{ total: 0 }
```

Điều này quan trọng khi viết code ứng dụng:

```javascript
const result = db.salesOrdersLesson.aggregate([
  { $match: { status: "REFUNDED" } },
  { $count: "total" }
]).toArray();

const total = result.length === 0 ? 0 : result[0].total;
print(total); // 0
```

Ở lớp ứng dụng, thường phải **đổi “không có document kết quả” thành số 0** nếu API cần luôn trả `{ total: 0 }`. Không nên gọi `result[0].total` khi `result` có thể rỗng.

### 4.1. Vì sao điều này xảy ra?

Về ý nghĩa, `$count` tương đương quá trình nhóm toàn bộ document đầu vào vào một nhóm rồi đếm số phần tử:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: null,
      total: { $sum: 1 }
    }
  },
  { $project: { _id: 0, total: 1 } }
]);
```

Với đầu vào rỗng, nhóm đó **không được tạo**, nên không có document đầu ra. Cách hiểu này giúp tránh nhầm `$count` với một hàm ứng dụng luôn trả về số nguyên 0.

### 4.2. Cách tạo trường tổng trong một kết quả cố định

Nếu cần đồng thời thống kê tổng và các nhóm cho dashboard, có thể dùng `$facet` rồi chuyển kết quả count rỗng thành 0:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { status: "REFUNDED" } },
  {
    $facet: {
      totals: [{ $count: "value" }],
      byCountry: [{ $sortByCount: "$country" }]
    }
  },
  {
    $project: {
      total: {
        $ifNull: [
          { $arrayElemAt: ["$totals.value", 0] },
          0
        ]
      },
      byCountry: 1
    }
  }
]);
```

Với bộ mẫu, đầu ra có dạng:

```javascript
{
  total: 0,
  byCountry: []
}
```

Ở đây `$facet` tạo một document chứa các mảng kết quả của các nhánh. `totals` là mảng rỗng, nên biểu thức `$ifNull` sử dụng giá trị dự phòng bằng 0. Đoạn này là giải pháp **cho nhu cầu tổng hợp nhiều chỉ số**, không phải lý do để luôn dùng `$facet` cho một phép đếm đơn giản.

## 5. `$count` khác gì `countDocuments()` và `estimatedDocumentCount()`?

MongoDB có nhiều API liên quan đến đếm. Chúng có hình dạng và ngữ nghĩa khác nhau:

| Cách đếm | Cú pháp | Phù hợp khi |
|---|---|---|
| Aggregation `$count` | `aggregate([{ $match: ... }, { $count: "total" }])` | Đếm **sau các bước pipeline**, có thể kết hợp biến đổi dữ liệu |
| `countDocuments()` | `db.orders.countDocuments({ status: "PAID" })` | Đếm số document khớp filter thông thường |
| `estimatedDocumentCount()` | `db.orders.estimatedDocumentCount()` | Cần số lượng document ước tính của collection, không áp dụng filter |

Ví dụ:

```javascript
db.salesOrdersLesson.countDocuments({ status: "PAID" });
// 4

db.salesOrdersLesson.estimatedDocumentCount();
// Số lượng ước tính của collection, khoảng 8 với bộ mẫu.

db.salesOrdersLesson.aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" }
]);
// { total: 4 }
```

`countDocuments()` trả về **một con số** từ API, tiện khi chỉ cần đếm document theo filter. `estimatedDocumentCount()` dựa trên thông tin thống kê/metadata và không dùng điều kiện filter, vì vậy không phù hợp để hỏi “có bao nhiêu đơn PAID?”.

**Không nên xem ba phương thức này luôn tương đương về hiệu năng hoặc kết quả.** Bối cảnh transaction, dữ liệu đang thay đổi, phiên bản triển khai và các yếu tố về độ chính xác/thống kê có thể ảnh hưởng lựa chọn. Nếu đã có một pipeline xử lý dữ liệu, `$count` thường là cách diễn đạt trực tiếp nhất.

## 6. `$sortByCount`: nhóm và xếp hạng tần suất

### 6.1. Cú pháp

```javascript
db.collection.aggregate([
  { $sortByCount: <expression> }
]);
```

**`<expression>` là một aggregation expression**, chẳng hạn:

- `"$status"`: lấy giá trị trường `status`.
- `"$country"`: lấy giá trị trường `country`.
- `{ $toLower: "$channel" }`: tính chuỗi đã chuyển sang chữ thường.
- `{ $cond: [condition, valueIfTrue, valueIfFalse] }`: xác định nhóm theo điều kiện.

Mỗi giá trị khác nhau của expression tạo một nhóm. Stage tính **số document trong mỗi nhóm** rồi sắp xếp nhóm theo `count` giảm dần.

### 6.2. Tần suất trạng thái đơn hàng

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$status" }
]);
```

Kết quả có dạng:

```javascript
{ _id: "PAID", count: 4 }
{ _id: null, count: 2 }
{ _id: "PENDING", count: 1 }
{ _id: "CANCELLED", count: 1 }
```

**Thứ tự của hai nhóm có `count: 1` không được bảo đảm** khi chỉ sort theo tần suất. Trong bộ mẫu, `null` ở kết quả đại diện cho O07 có `status: null` và O08 thiếu trường `status`; hai trạng thái đó được nhóm chung khi dùng trực tiếp đường dẫn `"$status"` làm khóa nhóm.

Hình dạng mỗi document đầu ra:

| Trường kết quả | Ý nghĩa |
|---|---|
| `_id` | Giá trị nhóm được tính từ expression |
| `count` | Số document đi vào nhóm đó |

Đây **không phải** document gốc của đơn hàng: các trường `customerId`, `amount`, `createdAt`... đã không còn trong kết quả nhóm.

### 6.3. Tần suất quốc gia

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$country" }
]);
```

Kết quả:

```javascript
{ _id: "VN", count: 5 }
{ _id: "TH", count: 2 }
{ _id: "SG", count: 1 }
```

Đây là câu hỏi khác với `$count`: ta không chỉ cần **8 đơn hàng**, mà cần biết **5 đơn ở VN, 2 đơn ở TH và 1 đơn ở SG**.

### 6.4. Tần suất theo kênh

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$channel" }
]);
```

Kết quả:

```javascript
{ _id: "web", count: 4 }
{ _id: "app", count: 3 }
{ _id: "partner", count: 1 }
```

Lưu ý: con số là **số đơn**, không phải doanh thu. `$sortByCount` mặc định đếm mỗi document một đơn vị, không sử dụng giá trị `amount` để làm trọng số.

## 7. Vì sao `$sortByCount` tương đương `$group` rồi `$sort`?

Đây là nguyên lý quan trọng nhất để hiểu stage này:

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$country" }
]);
```

có cùng mục đích với:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: "$country",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Luồng xử lý:

```text
        8 document đơn hàng
                  |
                  v
    Tính giá trị $country cho mỗi đơn
                  |
                  v
     $group theo giá trị country
       VN: 5, TH: 2, SG: 1
                  |
                  v
        $sort count giảm dần
                  |
                  v
    { _id: "VN", count: 5 }
    { _id: "TH", count: 2 }
    { _id: "SG", count: 1 }
```

`$sortByCount` là dạng viết ngắn gọn của mẫu **`$group` theo một expression + `$sum: 1` + `$sort` giảm dần theo count**.

### 7.1. Khi nào dùng bản rút gọn?

Chọn `$sortByCount` khi câu hỏi chỉ là:

> “Mỗi giá trị nhóm xuất hiện bao nhiêu lần, và nhóm nào phổ biến nhất?”

Ví dụ tần suất trạng thái, quốc gia, kênh đặt hàng hoặc các mã tag sau khi đã tách mảng.

### 7.2. Khi nào cần `$group` đầy đủ?

Nếu còn cần tổng tiền, giá trị trung bình hoặc thời gian gần nhất:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: "$country",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" },
      averageAmount: { $avg: "$amount" },
      latestOrderAt: { $max: "$createdAt" }
    }
  },
  { $sort: { orderCount: -1, _id: 1 } }
]);
```

Lúc này `$group` thích hợp hơn vì `$sortByCount` chỉ tạo `_id` và `count`; nó **không có cú pháp để thêm nhiều accumulator** trong cùng stage.

Tương tự, nếu cần sort theo nhiều tiêu chí hoặc đổi tên trường đếm, dùng `$group` + `$sort` / `$project` để diễn đạt rõ hơn.

### 7.3. Ổn định thứ tự khi các nhóm có tần suất bằng nhau

`$sortByCount` sắp theo `count` giảm dần, **không tự bảo đảm thứ tự giữa các nhóm có cùng count**. Với phân trang hoặc xuất báo cáo cần kết quả ổn định:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } }
]);
```

Quy tắc trên thêm khóa `_id` tăng dần để phá hòa. Nếu `_id` có kiểu dữ liệu khác nhau, MongoDB sắp theo thứ tự so sánh BSON tương ứng; cần cân nhắc chuẩn hóa nhóm nếu yêu cầu báo cáo có thứ tự định nghĩa riêng.

## 8. Vị trí các stage làm thay đổi ý nghĩa của phép đếm

MongoDB pipeline xử lý document **theo thứ tự stage**. Vì vậy, đặt `$match`, `$limit`, `$unwind`, `$group` trước `$count` hay `$sortByCount` sẽ thay đổi tập đầu vào được đếm.

### 8.1. `$match` trước `$sortByCount`: tần suất trong một tập con

Đếm tần suất quốc gia **chỉ trong các đơn đã thanh toán**:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { status: "PAID" } },
  { $sortByCount: "$country" }
]);
```

Kết quả:

```javascript
{ _id: "VN", count: 3 }
{ _id: "TH", count: 1 }
```

Stage `$match` loại bốn đơn không có trạng thái `PAID` trước khi nhóm; những quốc gia không còn đơn phù hợp sẽ không xuất hiện trong kết quả.

### 8.2. `$limit` trước `$count` không phải đếm toàn collection

```javascript
db.salesOrdersLesson.aggregate([
  { $limit: 3 },
  { $count: "total" }
]);
```

Kết quả `{ total: 3 }` vì `$count` chỉ nhận tối đa ba document đã qua `$limit`.

Đổi thứ tự:

```javascript
db.salesOrdersLesson.aggregate([
  { $count: "total" },
  { $limit: 3 }
]);
```

Kết quả `{ total: 8 }`, bởi `$count` đã biến tất cả đầu vào thành **một document tổng**. `$limit: 3` sau đó không thay đổi con số trong document tổng.

**Không được đếm trên một trang để suy ra tổng số kết quả**:

```javascript
// Đếm chỉ số document của một trang.
[
  { $skip: 20 },
  { $limit: 10 },
  { $count: "total" }
]
```

Đây không phải công thức tính tổng document khớp filter ban đầu. Tổng kết quả và số document trong trang là hai chỉ số khác nhau.

### 8.3. `$count` sau `$sortByCount` đếm số nhóm

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$country" },
  { $count: "countryGroupCount" }
]);
```

Kết quả:

```javascript
{ countryGroupCount: 3 }
```

Vì `$sortByCount` đã biến tám đơn hàng thành **ba nhóm quốc gia**, `$count` ở sau đếm ba document nhóm, không phải tám đơn hàng.

Đây là một cách đơn giản để đếm **số giá trị quốc gia phân biệt** trong bộ dữ liệu:

```javascript
db.salesOrdersLesson.aggregate([
  { $group: { _id: "$country" } },
  { $count: "distinctCountries" }
]);
```

Kết quả tương tự: `{ distinctCountries: 3 }`. Nếu chỉ cần số nhóm chứ không cần sắp xếp, dạng `$group` rồi `$count` tránh diễn đạt một bước sort không cần thiết.

### 8.4. `$sortByCount` sau `$limit` đếm tần suất trong mẫu giới hạn

```javascript
db.salesOrdersLesson.aggregate([
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 },
  { $sortByCount: "$country" }
]);
```

Ba đơn mới nhất là O08, O07 và O06. Kết quả tần suất:

```javascript
{ _id: "VN", count: 2 }
{ _id: "TH", count: 1 }
```

Đây là tần suất quốc gia **trong ba đơn gần nhất**, không phải tần suất trong toàn bộ tám đơn. Khi nói “top k quốc gia của tháng”, đừng vô tình `$limit` số đơn trước khi nhóm nếu nghiệp vụ muốn thống kê trên **toàn tháng**.

## 9. Đếm tần suất phần tử mảng: phải hiểu `$unwind`

Đây là bẫy quan trọng khi làm việc với document database.

Mỗi đơn hàng có một trường `tags` dạng **mảng**:

```javascript
{ _id: "O01", tags: ["new", "vip"] }
{ _id: "O02", tags: ["sale"] }
{ _id: "O03", tags: [] }
```

### 9.1. Dùng `$sortByCount: "$tags"` trực tiếp sẽ nhóm theo cả mảng

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$tags" }
]);
```

Ở đây aggregation expression `"$tags"` trả về **toàn bộ giá trị mảng của document**, nên khóa nhóm `_id` có thể là một mảng như `["new", "vip"]`, `["sale"]` hoặc `[]`.

Điều này trả lời câu hỏi:

> “Những **tổ hợp tag nguyên mảng** nào xuất hiện ở các đơn hàng và mỗi tổ hợp xuất hiện mấy lần?”

Nó **không** trả lời:

> “Mỗi **tag riêng lẻ** xuất hiện trong bao nhiêu đơn?”

Hai mảng có các phần tử giống nhau nhưng **thứ tự khác nhau** cũng có thể là hai khóa nhóm khác nhau theo ngữ nghĩa so sánh mảng. Không dựa vào `$sortByCount: "$tags"` để thống kê từng nhãn riêng lẻ.

### 9.2. `$unwind` biến phần tử mảng thành document trong luồng

Để đếm từng tag, cần làm “phẳng” mảng bằng `$unwind`:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  { $sortByCount: "$tags" }
]);
```

Kết quả:

```javascript
{ _id: "vip", count: 3 }
{ _id: "sale", count: 3 }
{ _id: "new", count: 2 }
```

Hai nhóm có count 3 không có thứ tự cố định với nhau. Chúng tương ứng:

- `vip`: xuất hiện ở O01, O04, O06.
- `sale`: xuất hiện ở O02, O04, O08.
- `new`: xuất hiện ở O01, O05.

### 9.3. Vì sao tổng tần suất tag bằng 8 nhưng chỉ có 6 đơn có tag?

Mỗi document có mảng `tags` không rỗng sẽ sinh **một document đầu ra cho mỗi phần tử** khi qua `$unwind`. Hai document O03 và O07 có mảng rỗng nên bị loại theo hành vi mặc định của `$unwind`.

```text
O01: ["new", "vip"]     -> 2 document sau $unwind
O02: ["sale"]           -> 1 document
O03: []                 -> 0 document
O04: ["sale", "vip"]     -> 2 document
O05: ["new"]            -> 1 document
O06: ["vip"]            -> 1 document
O07: []                 -> 0 document
O08: ["sale"]           -> 1 document
-----------------------------------------
Tổng                     8 document
```

Như vậy:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  { $count: "tagOccurrences" }
]);
// { tagOccurrences: 8 }
```

Đây là **8 lượt xuất hiện của tag**, không phải tám đơn khác nhau có tag.

Muốn đếm **số đơn có ít nhất một tag**, trong bộ mẫu có thể dùng:

```javascript
db.salesOrdersLesson.aggregate([
  { $match: { "tags.0": { $exists: true } } },
  { $count: "ordersWithTags" }
]);
// { ordersWithTags: 6 }
```

Đoạn filter trên phù hợp với schema `tags` luôn là mảng và kiểm tra phần tử ở vị trí 0. Nếu collection có nhiều kiểu dữ liệu hoặc mảng lồng nhau, cần áp dụng schema validation và quy tắc truy vấn tương ứng.

### 9.4. Lựa chọn `preserveNullAndEmptyArrays`

`$unwind` mặc định bỏ qua trường mảng thiếu, null hoặc rỗng. Có thể giữ các document không có phần tử bằng:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $unwind: {
      path: "$tags",
      preserveNullAndEmptyArrays: true
    }
  },
  { $sortByCount: "$tags" }
]);
```

Khi đó các đơn có mảng rỗng cũng còn trong luồng sau `$unwind` và có thể góp vào một nhóm biểu thị dữ liệu không có tag. Kết quả có thể có thêm nhóm `_id: null` cho các giá trị null/missing sau khi unwind.

**Cần chọn rõ yêu cầu:** đang đếm “tần suất các tag thực sự xuất hiện” hay cần nhóm riêng “đơn không gắn tag”? Với câu hỏi thứ nhất, cách `$unwind` mặc định thường đơn giản và dễ hiểu hơn.

### 9.5. Tag bị lặp trong cùng đơn

Giả sử một đơn có:

```javascript
{ _id: "O09", tags: ["vip", "vip", "sale"] }
```

`$unwind` sẽ tạo **hai lượt `vip`** từ O09. Vì thế `$sortByCount` đếm **số lần phần tử xuất hiện**, không nhất thiết đếm số đơn **phân biệt** chứa tag.

Nếu nghiệp vụ yêu cầu “mỗi tag được tính tối đa một lần trên mỗi đơn”, có thể:

- Chuẩn hóa `tags` thành tập giá trị không trùng ngay khi ghi.
- Hoặc loại trùng theo cặp `(orderId, tag)` trước khi đếm.

Ví dụ pipeline loại trùng ở cấp cặp:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  {
    $group: {
      _id: {
        orderId: "$_id",
        tag: "$tags"
      }
    }
  },
  { $sortByCount: "$_id.tag" }
]);
```

Sau `$group`, mỗi cặp đơn-tag chỉ còn một document trong luồng. `$sortByCount` lúc này biểu thị **số đơn khác nhau chứa mỗi tag**. Đây là ví dụ vì sao phải định nghĩa đơn vị đếm trước khi chọn stage.

## 10. Nhóm theo biểu thức tính toán, không chỉ theo một trường có sẵn

`$sortByCount` nhận **aggregation expression**, nên có thể dùng biểu thức để tạo nhóm.

### 10.1. Nhóm theo khoảng giá trị bằng `$switch`

Giả sử muốn chia đơn theo số tiền:

- `LOW`: dưới 100.000.
- `MID`: từ 100.000 đến dưới 300.000.
- `HIGH`: từ 300.000 trở lên.

```javascript
db.salesOrdersLesson.aggregate([
  {
    $sortByCount: {
      $switch: {
        branches: [
          {
            case: { $lt: ["$amount", 100000] },
            then: "LOW"
          },
          {
            case: { $lt: ["$amount", 300000] },
            then: "MID"
          }
        ],
        default: "HIGH"
      }
    }
  }
]);
```

Với tám đơn:

- `LOW`: O02 (90.000) và O07 (0) → **2**.
- `MID`: O03, O04, O05, O08 → **4**.
- `HIGH`: O01, O06 → **2**.

Kết quả:

```javascript
{ _id: "MID", count: 4 }
{ _id: "LOW", count: 2 }
{ _id: "HIGH", count: 2 }
```

Trong ví dụ, `amount` đều là số. Nếu có document mà `amount` thiếu, null hoặc chứa chuỗi, cần quyết định cách xử lý trước khi so sánh để tránh nhóm sai do quy tắc so sánh kiểu BSON.

### 10.2. Chuẩn hóa chữ hoa/chữ thường

Giả sử một số đơn được ghi `"web"` và số khác là `"WEB"`. Nếu nghiệp vụ coi chúng là cùng một kênh, có thể chuẩn hóa trước khi nhóm:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $sortByCount: {
      $toLower: {
        $ifNull: ["$channel", "(unknown)"]
      }
    }
  }
]);
```

`$ifNull` xử lý giá trị null hoặc trường thiếu bằng một chuỗi dự phòng, sau đó `$toLower` chuyển chuỗi thành chữ thường. Nếu `channel` có thể chứa giá trị **khác kiểu chuỗi**, cần thêm kiểm tra kiểu hoặc chuẩn hóa đầu vào; không coi `$toLower` là hàm tự hiểu mọi loại BSON.

Lưu ý về chuỗi Unicode và ngôn ngữ: quy tắc chuyển chữ thường của các toán tử có giới hạn riêng. Nếu nghiệp vụ đòi so sánh không phân biệt chữ hoa/chữ thường theo ngôn ngữ cụ thể, cần xem xét **collation** hoặc chuẩn hóa ngoài database, đồng thời xác nhận cách xử lý dữ liệu thực.

### 10.3. Tần suất theo ngày bằng `$dateToString`

```javascript
db.salesOrdersLesson.aggregate([
  {
    $sortByCount: {
      $dateToString: {
        format: "%Y-%m-%d",
        date: "$createdAt",
        timezone: "Asia/Ho_Chi_Minh"
      }
    }
  }
]);
```

Biểu thức tạo một chuỗi ngày theo múi giờ chỉ định, rồi nhóm đơn theo ngày. Vì các document của bộ mẫu cách nhau một ngày, mỗi ngày có một đơn; kết quả có tám nhóm count 1 (thứ tự giữa chúng không được `$sortByCount` bảo đảm).

Khi xây báo cáo thực tế, cần thống nhất thời gian UTC lưu trong BSON Date và múi giờ nghiệp vụ khi chia ngày/tháng. Không nên nhóm theo chuỗi cắt từ ngày UTC nếu sản phẩm tính ngày theo múi giờ khác.

### 10.4. Nhóm theo nhiều trường bằng một document expression

Nếu muốn tần suất của từng cặp `(country, channel)`, dùng một biểu thức tạo object:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $sortByCount: {
      country: "$country",
      channel: "$channel"
    }
  }
]);
```

Mỗi khóa nhóm `_id` là một document như:

```javascript
{
  _id: { country: "VN", channel: "web" },
  count: 3
}
```

Với bộ mẫu, VN-web gồm O01, O04, O06 và có count 3; VN-app gồm O02 (count 1); VN-partner gồm O08 (count 1); TH-app gồm O05, O07 (count 2); SG-web gồm O03 (count 1).

Khi nhóm theo object hoặc mảng, cần quan tâm **kiểu dữ liệu và cấu trúc khóa**. Nếu chỉ cần một cặp khóa rõ ràng, cách viết đầy đủ bằng `$group` cũng có thể dễ đọc:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $group: {
      _id: {
        country: "$country",
        channel: "$channel"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

## 11. Phân biệt `null` và trường không tồn tại khi thống kê

Trong bộ mẫu:

```javascript
{ _id: "O07", status: null, /* ... */ }
{ _id: "O08", /* không có status */ }
```

Khi `$sortByCount: "$status"`, hai document này được gom chung vào một nhóm `_id: null`. Nhưng trong hệ thống quản trị chất lượng dữ liệu, hai trạng thái có thể mang ý nghĩa khác nhau:

- **Missing:** ứng dụng chưa ghi trường, có thể là lỗi migration hoặc dữ liệu cũ.
- **Null:** ứng dụng có ghi trường nhưng giá trị được chỉ định là null.

Muốn tách chúng, phân loại theo `$type` trong aggregation:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $set: {
      statusGroup: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [{ $type: "$status" }, "missing"]
              },
              then: "(missing)"
            },
            {
              case: {
                $eq: [{ $type: "$status" }, "null"]
              },
              then: "(null)"
            }
          ],
          default: "$status"
        }
      }
    }
  },
  { $sortByCount: "$statusGroup" }
]);
```

Lúc này các nhóm không còn bị gộp vô ý:

```javascript
{ _id: "PAID", count: 4 }
{ _id: "PENDING", count: 1 }
{ _id: "CANCELLED", count: 1 }
{ _id: "(null)", count: 1 }
{ _id: "(missing)", count: 1 }
```

Các nhóm cùng count 1 có thể xuất hiện theo thứ tự khác nhau. Ví dụ trên phù hợp khi những giá trị trạng thái thực tế không trùng với nhãn đặc biệt `"(null)"` và `"(missing)"`; trong hệ thống thật có thể dùng object chứa cả `type` và `value` để tránh va chạm nhãn.

**Không nên “làm sạch” null thành một giá trị mặc định trước khi xác định nghiệp vụ có cần phân biệt null với missing hay không.**

## 12. Kết hợp hai phép thống kê cho dashboard bằng `$facet`

Một dashboard thường cần cả:

- Tổng số đơn.
- Số đơn đã thanh toán.
- Tần suất trạng thái.
- Tần suất quốc gia.
- Ba kênh được dùng nhiều nhất.

Chạy riêng nhiều query có thể đơn giản, nhưng `$facet` cho phép tạo nhiều nhánh xử lý **từ cùng một luồng đầu vào**:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $facet: {
      allOrders: [
        { $count: "value" }
      ],
      paidOrders: [
        { $match: { status: "PAID" } },
        { $count: "value" }
      ],
      byStatus: [
        { $sortByCount: "$status" }
      ],
      byCountry: [
        { $sortByCount: "$country" }
      ],
      topChannels: [
        { $sortByCount: "$channel" },
        { $limit: 3 }
      ]
    }
  },
  {
    $project: {
      total: {
        $ifNull: [
          { $arrayElemAt: ["$allOrders.value", 0] },
          0
        ]
      },
      paid: {
        $ifNull: [
          { $arrayElemAt: ["$paidOrders.value", 0] },
          0
        ]
      },
      byStatus: 1,
      byCountry: 1,
      topChannels: 1
    }
  }
]);
```

Đầu ra có cấu trúc:

```javascript
{
  total: 8,
  paid: 4,
  byStatus: [
    { _id: "PAID", count: 4 },
    { _id: null, count: 2 },
    // Các nhóm tần suất 1...
  ],
  byCountry: [
    { _id: "VN", count: 5 },
    { _id: "TH", count: 2 },
    { _id: "SG", count: 1 }
  ],
  topChannels: [
    { _id: "web", count: 4 },
    { _id: "app", count: 3 },
    { _id: "partner", count: 1 }
  ]
}
```

### 12.1. Phân biệt `$facet` với “query miễn phí”

`$facet` hữu ích khi nhiều phép thống kê cùng cần dùng tập dữ liệu nền và ứng dụng muốn một phản hồi có cấu trúc. Nhưng nó **không làm mọi phép tổng hợp trở nên rẻ hơn**:

- Mỗi nhánh vẫn phải nhóm, đếm hoặc sắp xếp dữ liệu phù hợp.
- `$facet` có giới hạn bộ nhớ/kích thước đầu ra riêng.
- Nếu đặt `$facet` ngay đầu pipeline, một số cách dùng index ở bước đầu có thể bị hạn chế; `$match` chọn lọc đặt trước có thể giúp.
- Nhiều nhánh rất nặng trong một pipeline có thể tạo yêu cầu tài nguyên lớn hơn nhiều query được phân tách hợp lý.

Ví dụ, nếu dashboard chỉ dành cho một tháng, nên đặt `$match` theo ngày trước `$facet` để mọi nhánh được thống kê trên **cùng tháng cần xem**.

### 12.2. Đừng đặt `$count` sau `$facet` để lấy tổng đơn

`$facet` thường trả **một document** chứa các mảng thống kê. Vì thế:

```javascript
db.salesOrdersLesson.aggregate([
  {
    $facet: {
      byCountry: [{ $sortByCount: "$country" }]
    }
  },
  { $count: "outputDocuments" }
]);
```

đếm số document **đầu ra của `$facet`**, chứ không đếm số đơn hàng gốc. Nếu cần tổng đơn trong cùng dashboard, tạo một nhánh `allOrders: [{ $count: "value" }]` như pipeline trên.

## 13. Lấy nhóm phổ biến nhất: top N và tie

`$sortByCount` đã sắp tần suất giảm dần, nên lấy ba nhóm phổ biến nhất chỉ cần thêm `$limit`:

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$country" },
  { $limit: 3 }
]);
```

Trong bộ mẫu có đúng ba quốc gia, nên kết quả chứa cả ba nhóm.

Nếu một báo cáo cần **chỉ hai nhóm được dùng nhiều nhất**, có thể dùng:

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$channel" },
  { $limit: 2 }
]);
```

Kết quả:

```javascript
{ _id: "web", count: 4 }
{ _id: "app", count: 3 }
```

### 13.1. `$limit` sau `$sortByCount` không giảm số document nguồn phải nhóm

Nếu muốn “top 3 quốc gia của tất cả 10 triệu đơn”, MongoDB vẫn phải xác định tần suất các quốc gia từ các document đủ điều kiện, rồi mới biết ba nhóm nào đứng đầu. `$limit: 3` **không có nghĩa chỉ xem ba document nguồn**.

Để giảm dữ liệu đầu vào một cách đúng nghiệp vụ, dùng `$match` theo khoảng thời gian, tenant hoặc điều kiện lọc thích hợp trước khi nhóm.

### 13.2. Tie: hai nhóm bằng tần suất

Trong thống kê tag của bộ mẫu, `vip` và `sale` đều xuất hiện ba lần. Nếu pipeline là:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  { $sortByCount: "$tags" },
  { $limit: 1 }
]);
```

không nên kỳ vọng top 1 luôn là `vip` hoặc luôn là `sale`. Vì hai nhóm có count bằng nhau, `$sortByCount` không xác định thứ tự thứ hai.

Nếu sản phẩm yêu cầu kết quả có tính ổn định và muốn phá hòa theo mã tag:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$tags" },
  {
    $group: {
      _id: "$tags",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } },
  { $limit: 1 }
]);
```

Với collation mặc định của bộ mẫu, thứ tự tăng dần theo `_id` khiến `"sale"` đứng trước `"vip"` khi số lần bằng nhau. Nếu dùng collation khác, thứ tự so sánh chuỗi có thể khác.

### 13.3. Top N với cả những nhóm đồng hạng

Yêu cầu “top 3 nhóm” khác với “tất cả nhóm có tần suất bằng hoặc lớn hơn nhóm thứ ba”. Khi có đồng hạng, `$limit: 3` chỉ trả **tối đa ba document nhóm**, có thể bỏ những nhóm cùng điểm ở vị trí thứ ba.

Nếu nghiệp vụ cần giữ cả nhóm đồng hạng, phải thiết kế pipeline khác (ví dụ tính thứ hạng bằng các window stage được hỗ trợ) hoặc xử lý ngưỡng tần suất rõ ràng. Không mặc định `$sortByCount + $limit` có ngữ nghĩa “with ties”.

## 14. Đếm đơn, đếm dòng hàng và đếm số lượng sản phẩm

Một ví dụ khác cho thấy **đơn vị đếm** quyết định đúng/sai của kết quả.

Trong bộ mẫu, `items` là mảng các dòng hàng:

```javascript
{
  _id: "O01",
  items: [
    { sku: "P01", quantity: 1 },
    { sku: "P02", quantity: 2 }
  ]
}
```

### 14.1. Đếm số đơn

```javascript
db.salesOrdersLesson.aggregate([
  { $count: "orders" }
]);
// { orders: 8 }
```

### 14.2. Đếm số dòng hàng

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$items" },
  { $count: "itemLines" }
]);
```

Tổng số dòng hàng trong tám đơn là **11**:

```text
O01: 2
O02: 1
O03: 1
O04: 2
O05: 1
O06: 3
O07: 0
O08: 1
-----------
Tổng: 11
```

### 14.3. Đếm tần suất SKU theo số dòng hàng

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$items" },
  { $sortByCount: "$items.sku" }
]);
```

`count` của mỗi SKU ở đây là **số dòng hàng** mang SKU đó, **không phải số đơn vị sản phẩm đã bán**.

### 14.4. Tổng số lượng sản phẩm dùng `$sum`, không dùng `$sortByCount`

Nếu một dòng hàng có `quantity: 5` thì cần cộng năm đơn vị, không phải cộng một lượt xuất hiện. Sử dụng `$group`:

```javascript
db.salesOrdersLesson.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      lines: { $sum: 1 },
      units: { $sum: "$items.quantity" }
    }
  },
  { $sort: { units: -1, _id: 1 } }
]);
```

Ở đây:

- `lines` đếm số dòng hàng.
- `units` cộng số lượng `quantity`.
- Hai con số chỉ bằng nhau khi mọi dòng hàng có quantity 1.

**`$sortByCount` không thể thay thế `$sum: "$items.quantity"`** khi cần tổng trọng số/số lượng. Đây là điểm cần kiểm tra trước khi dùng tần suất để báo cáo doanh thu, số hàng hoặc điểm tích lũy.

## 15. Hiệu năng và kế hoạch thực thi

`$count` và `$sortByCount` thường dùng trong báo cáo và dashboard, nơi collection có thể rất lớn. Để cải thiện hiệu năng, phải phân biệt **công việc tìm document đầu vào** với **công việc nhóm/sắp xếp**.

### 15.1. `$match` trước phép tổng hợp có thể tận dụng index

Ví dụ lọc đơn `PAID` của Việt Nam:

```javascript
db.salesOrdersLesson.createIndex({
  country: 1,
  status: 1
});

db.salesOrdersLesson.aggregate([
  {
    $match: {
      country: "VN",
      status: "PAID"
    }
  },
  { $count: "total" }
]);
```

Index có thể giúp thu hẹp tập document được xét, tùy bộ lập kế hoạch, dữ liệu và cách thực thi. Tạo index không bảo đảm mọi query hay mọi pipeline đều chọn index đó.

### 15.2. Nhóm và sort có thể tốn bộ nhớ

`$sortByCount` tương đương với `$group` rồi `$sort`. Nếu khóa nhóm có rất nhiều giá trị khác nhau (ví dụ nhóm theo `userId` của hàng chục triệu người dùng), pipeline có thể phải giữ nhiều nhóm và sắp xếp kết quả.

Một số aggregation stage có thể sử dụng bộ nhớ lớn và chịu giới hạn tài nguyên; tùy phiên bản/cấu hình, chúng có thể được phép ghi dữ liệu tạm ra đĩa khi bật hoặc mặc định cho phép disk use:

```javascript
db.salesOrdersLesson.aggregate(
  [
    { $match: { status: "PAID" } },
    { $sortByCount: "$customerId" },
    { $limit: 20 }
  ],
  { allowDiskUse: true }
);
```

`allowDiskUse` không làm bài toán group/sort miễn phí; nó có thể giảm rủi ro lỗi giới hạn bộ nhớ cho những stage được hỗ trợ, nhưng đánh đổi bằng I/O đĩa và tài nguyên. Không phải mọi lỗi hiệu năng đều được giải quyết bằng tùy chọn này.

### 15.3. `$limit` sau khi nhóm không làm giảm lượng dữ liệu nguồn phải đọc

Đối với:

```javascript
[
  { $match: { status: "PAID" } },
  { $sortByCount: "$customerId" },
  { $limit: 10 }
]
```

MongoDB phải xác định các tần suất từ **tất cả đơn PAID đầu vào** trước khi biết top 10 khách hàng. Tối ưu chính là đặt filter phù hợp, thiết kế index/mô hình truy vấn hoặc dùng dữ liệu tổng hợp đã được duy trì nếu báo cáo chạy quá thường xuyên.

### 15.4. `explain()` cho aggregation

```javascript
db.salesOrdersLesson.explain("executionStats").aggregate([
  { $match: { status: "PAID" } },
  { $sortByCount: "$country" }
]);
```

Tùy phiên bản MongoDB, `explain` có thể thể hiện pipeline đã được tối ưu thành những stage khác nhau, gồm `$group` và `$sort` hoặc dạng thực thi tương đương.

Khi đọc, chú ý:

- `COLLSCAN` hay `IXSCAN` cho tập document đầu vào.
- `totalDocsExamined` và `totalKeysExamined` ở phần truy cập dữ liệu.
- Số document đi vào bước nhóm.
- Chi phí sort, khả năng tràn ra đĩa và thông tin thời gian nếu được báo cáo.
- `nReturned` cuối pipeline có thể nhỏ hơn rất nhiều so với số document được quét vì mỗi nhóm chỉ tạo một document.

Đừng lấy `nReturned` của `$sortByCount` (số nhóm) rồi kết luận truy vấn “chỉ đọc vài document”. Số document đầu vào mới là yếu tố quyết định lượng công việc nhóm.

### 15.5. Kết quả tổng hợp lưu sẵn (pre-aggregation)

Với dashboard cần tần suất trạng thái mỗi phút trên hàng trăm triệu document, chạy `$sortByCount` trên toàn collection cho mỗi lần mở trang có thể quá đắt. Có thể:

- Lưu tổng hợp theo ngày hoặc theo tenant.
- Duy trì các counter theo sự kiện ghi đơn hàng.
- Cập nhật định kỳ bằng batch/stream.
- Có cơ chế tính lại và đối soát để xử lý sự kiện trùng, retry hoặc đơn hàng đổi trạng thái.

Ví dụ một document tổng hợp:

```javascript
{
  _id: "2026-11-08:VN:PAID",
  day: "2026-11-08",
  country: "VN",
  status: "PAID",
  orderCount: 1250
}
```

Đây là **dữ liệu dẫn xuất**, không phải số đếm tự động được MongoDB đảm bảo luôn đúng nếu ứng dụng không có quy trình duy trì. Khi số liệu ảnh hưởng thanh toán hoặc báo cáo tài chính, phải xác định ranh giới nhất quán và cách khôi phục sai lệch trước khi dùng pre-aggregation.

## 16. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `$count` đếm toàn bộ collection bất kể stage trước | Nó đếm những document **đến được vị trí `$count`** |
| `$count` với đầu vào rỗng trả `{ total: 0 }` | Nó không trả document; ứng dụng có thể cần chuyển thành 0 |
| `$count` là giá trị số trả trực tiếp từ `aggregate()` | Kết quả aggregation là cursor, thường chứa một document tổng nếu có đầu vào |
| `$sortByCount` đếm số document toàn collection | Nó nhóm theo expression và tạo một document cho mỗi giá trị nhóm |
| `$sortByCount` luôn sắp ổn định khi count bằng nhau | Nó chỉ sort theo count giảm dần; cần khóa phụ nếu muốn thứ tự ổn định |
| `$sortByCount: "$tags"` đếm mỗi tag trong mảng | Nó nhóm theo **giá trị mảng nguyên vẹn**; dùng `$unwind` trước nếu muốn đếm từng phần tử |
| `$unwind` không làm thay đổi số document | Một document có thể thành nhiều document; mảng rỗng có thể bị loại |
| Đếm tag sau unwind là số đơn chứa tag | Nó đếm **lượt xuất hiện**; có thể cần loại trùng cặp đơn-tag |
| `$sortByCount` thay được tổng số lượng bán | Nó cộng **1 cho mỗi document**; cần `$sum` để cộng quantity |
| `$count` sau `$group` vẫn đếm document nguồn | Nó đếm **số nhóm** do `$group` tạo |
| `$limit` trước `$sortByCount` giúp lấy top nhóm của toàn bộ dữ liệu | Nó chỉ nhóm trên tập document đã bị giới hạn |
| `$limit` sau `$sortByCount` chỉ cần đọc N document nguồn | Phải tính các nhóm từ tập đầu vào trước khi biết top N |
| `countDocuments()` và `estimatedDocumentCount()` luôn tương đương | Một bên đếm theo filter, bên kia là ước lượng tổng collection |
| `$sortByCount` không thể nhóm theo giá trị tính toán | Nó nhận một aggregation expression, có thể là `$switch`, `$toLower`, object... |
| Có index nghĩa tần suất trên hàng triệu nhóm luôn nhanh | Nhóm và sort vẫn có chi phí bộ nhớ/CPU/I/O |

## 17. Bài tập thực hành

### Bài 1 — Đếm theo điều kiện

Với collection `salesOrdersLesson`:

1. Đếm số document của toàn collection bằng `$count`.
2. Đếm số đơn `PAID`.
3. Đếm số đơn thuộc `country: "VN"`.
4. Đếm số đơn vừa `PAID` vừa thuộc `VN`.
5. Đếm số đơn có trạng thái `"REFUNDED"` và giải thích hình dạng kết quả.

Tự dự đoán trước khi chạy. Chú ý trường hợp thứ năm **không trả một document có số 0**.

### Bài 2 — Tính tần suất

Viết các pipeline dùng `$sortByCount` để trả:

- Tần suất `status`.
- Tần suất `country`.
- Tần suất `channel`.
- Tần suất `country` chỉ trong các đơn `PAID`.

Với mỗi pipeline, hãy xác định `_id` và `count` của các nhóm. Giải thích vì sao kết quả có thể chứa nhóm `_id: null`.

### Bài 3 — Chuyển `$sortByCount` thành `$group`

Chuyển pipeline:

```javascript
db.salesOrdersLesson.aggregate([
  { $sortByCount: "$channel" }
]);
```

thành dạng dùng `$group` với `$sum: 1` rồi `$sort`. Sau đó thêm khóa phụ `_id: 1` khi hai nhóm có tần suất bằng nhau. Giải thích tại sao bản đầy đủ linh hoạt hơn.

### Bài 4 — Đếm tag

Cho:

```javascript
{
  _id: "X1",
  tags: ["mongo", "java"]
}
{
  _id: "X2",
  tags: ["mongo", "mongo"]
}
{
  _id: "X3",
  tags: []
}
```

Hãy phân biệt:

1. `$sortByCount: "$tags"` trực tiếp.
2. `$unwind: "$tags"` rồi `$sortByCount: "$tags"`.
3. `$unwind`, loại trùng theo cặp đơn-tag, rồi `$sortByCount`.

Mỗi cách đang đếm **tổ hợp mảng**, **số lượt xuất hiện** hay **số document phân biệt có tag**?

### Bài 5 — Đếm số nhóm khác nhau

Viết pipeline để tìm số `country` phân biệt bằng:

```javascript
{ $group: { _id: "$country" } }
{ $count: "distinctCountries" }
```

Sau đó thử dùng `$sortByCount` trước `$count` và giải thích vì sao con số bằng nhau, nhưng cách thứ nhất tránh thêm bước sắp xếp không cần thiết.

### Bài 6 — Tổng số lượng hàng khác tần suất SKU

Dùng `items` trong bộ mẫu:

1. Đếm số đơn.
2. Đếm số dòng hàng sau `$unwind`.
3. Đếm số dòng hàng của mỗi SKU bằng `$sortByCount`.
4. Tính tổng `quantity` của mỗi SKU bằng `$group` + `$sum`.

Hãy giải thích tại sao “SKU xuất hiện 3 dòng” chưa cho biết đã bán bao nhiêu **đơn vị** của SKU đó.

### Bài 7 — Thống kê nhiều chỉ số bằng `$facet`

Thiết kế pipeline trả:

```javascript
{
  totalOrders: 8,
  paidOrders: 4,
  byStatus: [ /* các nhóm và count */ ],
  byChannel: [ /* các nhóm và count */ ]
}
```

Chú ý các nhánh `$count` tạo mảng gồm một document hoặc mảng rỗng. Dùng `$arrayElemAt` và `$ifNull` để tạo số 0 khi thích hợp.

### Bài 8 — Top N và đồng hạng

Lấy **top 1 tag phổ biến nhất** từ bộ mẫu sau `$unwind`. Giải thích vì sao kết quả có thể là `sale` hoặc `vip`. Viết lại bằng `$group` và `$sort: { count: -1, _id: 1 }` để có quy tắc phá hòa.

Nếu yêu cầu sản phẩm là “trả tất cả tag đồng hạng nhất”, `$limit: 1` đã đủ chưa? Hãy đề xuất cách xác định ngưỡng count cao nhất để giữ tất cả các nhóm đạt ngưỡng đó.

### Bài 9 — Nhóm theo mức giá

Viết `$sortByCount` với `$switch` để chia `amount` thành ba mức:

- Dưới 100.000.
- Từ 100.000 đến dưới 300.000.
- Từ 300.000 trở lên.

Hãy dự đoán số đơn từng nhóm, rồi thay đổi ngưỡng và quan sát cách phân bố tần suất. Nếu `amount` thiếu/null, quy tắc nghiệp vụ sẽ được bổ sung ở đâu?

### Bài 10 — Thực hành với kế hoạch thực thi

Tạo index thử nghiệm trên `{ status: 1, country: 1 }`, rồi giải thích:

```javascript
db.salesOrdersLesson.explain("executionStats").aggregate([
  {
    $match: {
      status: "PAID",
      country: "VN"
    }
  },
  { $count: "total" }
]);
```

Hãy quan sát index được chọn, `totalDocsExamined`, `totalKeysExamined` và đầu ra. Vì bộ mẫu nhỏ, nếu MongoDB chọn `COLLSCAN`, có thể kết luận rằng index đó vô dụng trên production không? Vì sao?

## 18. Ghi nhớ

**`$count` tạo một kết quả tổng** từ những document đã qua các stage trước nó. Nếu đầu vào rỗng, pipeline không sinh document đếm; ứng dụng cần xử lý thành số 0 khi hợp đồng API yêu cầu.

**`$sortByCount` tạo bảng tần suất** bằng cách nhóm theo một aggregation expression rồi sắp theo `count` giảm dần. Nó tương đương `$group` với `$sum: 1` và `$sort`, nhưng ngắn gọn hơn khi chỉ cần biết các nhóm phổ biến nhất.

**Đơn vị đếm phụ thuộc vị trí trong pipeline.** `$count` trước `$unwind` đếm đơn hàng; `$count` sau `$unwind` đếm phần tử mảng; `$count` sau `$group` đếm số nhóm. `$sortByCount` trên toàn bộ mảng khác hoàn toàn với `$unwind` rồi đếm từng phần tử.

**Đếm tần suất không phải cộng trọng số.** Nếu cần doanh thu, số đơn vị hàng hóa, điểm số hoặc các phép thống kê khác, hãy dùng `$group` với accumulator thích hợp.

**Hiệu năng và tính đúng phải được thiết kế cùng nhau.** Lọc đúng bằng `$match`, xử lý missing/null có chủ đích, quyết định quy tắc phá hòa khi xếp hạng, và chỉ tối ưu index/summary sau khi xác định rõ tập dữ liệu cũng như đại lượng cần đếm.
