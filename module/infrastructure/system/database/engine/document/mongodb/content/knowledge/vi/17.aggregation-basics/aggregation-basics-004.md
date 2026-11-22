# Sắp xếp, giới hạn và bỏ qua bằng `$sort`, `$limit`, `$skip` trong MongoDB

Một API danh sách đơn hàng thường phải trả lời ba câu hỏi: **Đơn nào đứng trước? Chỉ lấy bao nhiêu đơn? Bỏ qua bao nhiêu đơn đầu tiên?** Trong MongoDB Aggregation Pipeline, ba stage cơ bản để giải quyết là `$sort`, `$limit` và `$skip`.

- **`$sort`** sắp xếp những document đang chảy qua pipeline theo một hoặc nhiều khóa.
- **`$limit`** chỉ cho tối đa một số lượng document đi tiếp trong pipeline.
- **`$skip`** bỏ qua một số lượng document đầu tiên trong **thứ tự đang có**.

Ba stage này thường đi cùng `$match` để xây dựng phân trang, feed mới nhất, bảng xếp hạng, báo cáo top N và các API có yêu cầu hiển thị ổn định. Tuy cú pháp ngắn, cách đặt stage và thứ tự khóa quyết định **tính đúng đắn** lẫn **hiệu năng**. Đặc biệt, `$skip` không tự sắp xếp, `$limit` không tự chọn “top” nếu không có thứ tự phù hợp, và `$sort` theo field trùng giá trị có thể khiến các trang không ổn định.

Bài nằm trong chương **Aggregation cơ bản** của *Database Engine Document MongoDB*. Các ví dụ chạy trong **mongosh**, database thực hành `aggregation_paging_lab`, sử dụng BSON Date và Decimal128 để thể hiện thời gian và tiền tệ. Tùy phiên bản MongoDB, kết quả `explain()` và khả năng dùng index/ghi tạm ra disk có thể khác nhau; phần vận hành sẽ phân biệt các trường hợp đó.

## 1. Ôn lại cách hoạt động của aggregation pipeline

Aggregation Pipeline xử lý tập document qua **các stage theo thứ tự**. Stage nhận đầu vào từ stage trước, xử lý, rồi truyền kết quả cho stage sau.

~~~mermaid
flowchart LR
    C["Collection orders"] --> M["$match: chọn document"]
    M --> S["$sort: xác định thứ tự"]
    S --> K["$skip: bỏ trang trước"]
    K --> L["$limit: giới hạn trang"]
    L --> P["$project: chọn field trả về"]
    P --> O["Kết quả API"]
~~~

Ví dụ:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 10 },
  { $limit: 5 },
  { $project: { _id: 1, createdAt: 1, amount: 1 } }
])
~~~

Theo ý nghĩa logic:

1. Chỉ giữ đơn đã thanh toán.
2. Sắp đơn mới nhất trước; khi cùng thời điểm, ID nhỏ hơn đứng trước.
3. Bỏ 10 document đầu trong danh sách đã sắp.
4. Lấy tối đa 5 document tiếp theo.
5. Chỉ trả những field ứng dụng cần.

**Thứ tự stage không phải chi tiết trang trí**. Đổi vị trí `$limit` trước `$sort` có thể chọn “5 document đến trước trong pipeline rồi mới sắp” thay vì “5 document mới nhất trong toàn tập”.

### Phân biệt cú pháp aggregation và cursor

MongoDB cũng cho phép thao tác tương tự trên cursor của `find()`:

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: 1 })
  .skip(10)
  .limit(5)
~~~

Trong aggregation, mỗi phép toán là một **stage object**:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 10 },
  { $limit: 5 }
])
~~~

Hai cách có thể giải quyết cùng nhu cầu phân trang đơn giản, nhưng aggregation còn cho phép `$group`, `$unwind`, `$lookup`, `$addFields`, `$facet` và nhiều bước chuyển đổi khác. Phải xác định bạn muốn phân trang **document gốc**, **item sau unwind** hay **nhóm đã tổng hợp**.

## 2. Chuẩn bị dữ liệu lab

Chọn database thử nghiệm riêng:

~~~javascript
use aggregation_paging_lab
~~~

Tạo collection đơn hàng; trường `createdAt` cố ý có những thời điểm bị trùng để minh họa tie-breaker:

~~~javascript
db.orders.insertMany([
  {
    _id: "o-001", tenantId: "t-01", status: "PAID",
    region: "HCM", customerId: "c-101", score: 80,
    amount: NumberDecimal("250000"),
    createdAt: ISODate("2026-07-03T09:00:00Z")
  },
  {
    _id: "o-002", tenantId: "t-01", status: "PAID",
    region: "HN", customerId: "c-102", score: 92,
    amount: NumberDecimal("120000"),
    createdAt: ISODate("2026-07-04T08:00:00Z")
  },
  {
    _id: "o-003", tenantId: "t-01", status: "CREATED",
    region: "HCM", customerId: "c-101", score: 76,
    amount: NumberDecimal("330000"),
    createdAt: ISODate("2026-07-04T08:00:00Z")
  },
  {
    _id: "o-004", tenantId: "t-01", status: "PAID",
    region: "DN", customerId: "c-103", score: 92,
    amount: NumberDecimal("450000"),
    createdAt: ISODate("2026-07-04T08:00:00Z")
  },
  {
    _id: "o-005", tenantId: "t-01", status: "CANCELLED",
    region: "HCM", customerId: "c-104", score: 61,
    amount: NumberDecimal("90000"),
    createdAt: ISODate("2026-07-02T15:00:00Z")
  },
  {
    _id: "o-006", tenantId: "t-01", status: "PAID",
    region: "HN", customerId: "c-102", score: 85,
    amount: NumberDecimal("700000"),
    createdAt: ISODate("2026-07-05T10:00:00Z")
  },
  {
    _id: "o-007", tenantId: "t-01", status: "PAID",
    region: "HCM", customerId: "c-103", score: 88,
    amount: NumberDecimal("520000"),
    createdAt: ISODate("2026-07-05T10:00:00Z")
  },
  {
    _id: "o-008", tenantId: "t-02", status: "PAID",
    region: "HCM", customerId: "c-201", score: 75,
    amount: NumberDecimal("180000"),
    createdAt: ISODate("2026-07-05T10:00:00Z")
  },
  {
    _id: "o-009", tenantId: "t-02", status: "CREATED",
    region: "HN", customerId: "c-202", score: 82,
    amount: NumberDecimal("310000"),
    createdAt: ISODate("2026-07-06T12:00:00Z")
  },
  {
    _id: "o-010", tenantId: "t-02", status: "PAID",
    region: "DN", customerId: "c-201", score: 95,
    amount: NumberDecimal("800000"),
    createdAt: ISODate("2026-07-04T08:00:00Z")
  },
  {
    _id: "o-011", tenantId: "t-02", status: "PAID",
    region: "HCM", customerId: "c-202", score: 90,
    amount: NumberDecimal("640000"),
    createdAt: ISODate("2026-07-06T12:00:00Z")
  },
  {
    _id: "o-012", tenantId: "t-02", status: "CANCELLED",
    region: "HN", customerId: "c-203", score: 65,
    amount: NumberDecimal("100000"),
    createdAt: ISODate("2026-07-03T09:00:00Z")
  },
  {
    _id: "o-013", tenantId: "t-03", status: "PAID",
    region: "HCM", customerId: "c-301", score: 99,
    amount: NumberDecimal("930000"),
    createdAt: ISODate("2026-07-07T13:00:00Z")
  },
  {
    _id: "o-014", tenantId: "t-03", status: "CREATED",
    region: "DN", customerId: "c-302", score: 70,
    amount: NumberDecimal("200000"),
    createdAt: ISODate("2026-07-06T12:00:00Z")
  },
  {
    _id: "o-015", tenantId: "t-03", status: "PAID",
    region: "HN", customerId: "c-301", score: 88,
    amount: NumberDecimal("430000"),
    createdAt: ISODate("2026-07-05T10:00:00Z")
  },
  {
    _id: "o-016", tenantId: "t-03", status: "PAID",
    region: "HCM", customerId: "c-303", score: 90,
    amount: NumberDecimal("500000"),
    createdAt: ISODate("2026-07-07T13:00:00Z")
  }
])
~~~

Chỉ chạy `insertMany()` một lần trên collection lab đang rỗng: chạy lại với cùng `_id` sẽ báo duplicate key. Nếu muốn làm lại, dùng database lab mới; không xóa dữ liệu ngoài phạm vi thực hành.

Kiểm tra:

~~~javascript
db.orders.countDocuments({}) // 16

db.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1, amount: 1, createdAt: 1 }
).sort({ _id: 1 })
~~~

Bộ dữ liệu có:

| Status | Số đơn |
|---|---:|
| PAID | 11 |
| CREATED | 3 |
| CANCELLED | 2 |
| **Tổng** | **16** |

Các ví dụ dưới đây dùng `{_id: 1}` hoặc `{_id: 1, createdAt: 1}` để dễ đối chiếu kết quả, không phải để thay đổi logic sắp xếp.

## 3. `$sort`: sắp xếp document

### 3.1. Cú pháp

~~~javascript
{
  $sort: {
    fieldA: 1,
    fieldB: -1
  }
}
~~~

Trong đó:

- `1`: sắp xếp tăng dần theo field.
- `-1`: sắp xếp giảm dần theo field.
- Khi giá trị `fieldA` bằng nhau, xét `fieldB`.
- Có thể dùng đường dẫn lồng nhau như `"customer.address.city"` khi field tồn tại theo schema phù hợp.

Ví dụ lấy đơn có số tiền lớn trước:

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1 } },
  { $project: { _id: 1, amount: 1 } }
])
~~~

Trong tập lab, những đơn có amount lớn nhất đứng đầu gồm:

~~~text
o-013  930000
o-010  800000
o-006  700000
o-011  640000
o-007  520000
~~~

### 3.2. Nhiều khóa trong `$sort`

~~~javascript
db.orders.aggregate([
  {
    $sort: {
      status: 1,
      createdAt: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      createdAt: 1
    }
  }
])
~~~

MongoDB sắp trước theo status; bên trong cùng status, mới xét createdAt giảm dần; nếu ngày trùng nhau, xét `_id` tăng dần.

**Không đồng nghĩa** với việc MongoDB lần lượt chạy ba phép sort độc lập rồi “giữ nguyên” thứ tự cũ. Đây là **một bộ khóa so sánh nhiều field**.

### 3.3. Sort theo field lồng nhau

Giả sử document:

~~~javascript
{
  _id: "p-01",
  customer: {
    profile: {
      loyaltyScore: 82
    }
  }
}
~~~

Ta có thể sắp theo đường dẫn:

~~~javascript
db.profiles.aggregate([
  {
    $sort: {
      "customer.profile.loyaltyScore": -1
    }
  }
])
~~~

Nếu không phải mọi document đều có đường dẫn này, cần xác định ngữ nghĩa của missing/null và cân nhắc chuẩn hóa schema.

### 3.4. Sort theo một giá trị tính toán

`$sort` sử dụng field hoặc sort specification được hỗ trợ, không phải nơi đặt tùy ý một phép tính như một expression trong value thay cho `1`/`-1`. Muốn sort theo giá trị tính được, hãy tạo field trước:

~~~javascript
db.orders.aggregate([
  {
    $addFields: {
      amountWithFee: {
        $multiply: ["$amount", NumberDecimal("1.05")]
      }
    }
  },
  {
    $sort: {
      amountWithFee: -1,
      _id: 1
    }
  },
  {
    $project: {
      _id: 1,
      amount: 1,
      amountWithFee: 1
    }
  }
])
~~~

Vì `amountWithFee` được tính trong pipeline, một index thông thường trên field `amount` không mặc nhiên cung cấp thứ tự của biểu thức đã tính trong mọi trường hợp; khả năng tối ưu phụ thuộc biến đổi và query shape.

## 4. `$sort` không ổn định khi khóa trùng giá trị

MongoDB **không bảo đảm thứ tự của những document có cùng toàn bộ sort key**. Nếu chỉ sắp theo `createdAt`, hai đơn tạo cùng giây có thể xuất hiện ở thứ tự khác giữa các lần chạy hoặc kế hoạch khác nhau.

Ví dụ hai đơn:

~~~text
o-006 createdAt = 2026-07-05T10:00:00Z
o-007 createdAt = 2026-07-05T10:00:00Z
~~~

Truy vấn:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1 } }
])
~~~

không chỉ rõ `o-006` hay `o-007` đứng trước. Khi phân trang bằng `$skip`, sự không xác định này có thể khiến một document xuất hiện ở hai trang hoặc bị bỏ sót nếu thứ tự tie thay đổi.

### Thêm tie-breaker duy nhất

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  {
    $sort: {
      createdAt: -1,
      _id: 1
    }
  }
])
~~~

Nếu `_id` là duy nhất, bộ khóa `createdAt + _id` tạo thứ tự xác định trong một tập dữ liệu **không thay đổi**. Với bộ lab, các đơn PAID của `t-01` theo thứ tự:

~~~text
o-006  2026-07-05 10:00
o-007  2026-07-05 10:00
o-002  2026-07-04 08:00
o-004  2026-07-04 08:00
o-001  2026-07-03 09:00
~~~

**Cần phân biệt hai bảo đảm:**

- *Tie-breaker* tạo thứ tự xác định khi tập dữ liệu tại thời điểm đọc là như nhau.
- *Snapshot consistency qua nhiều request* là bài toán khác: nếu có đơn mới được thêm hoặc đơn cũ bị sửa giữa hai lần lấy trang, dữ liệu vẫn có thể dịch chuyển dù có `_id` làm tie-breaker.

### Khi sort theo score

Nếu nhiều document có `score: 92`, dùng:

~~~javascript
{ $sort: { score: -1, _id: 1 } }
~~~

để kết quả bảng xếp hạng ổn định theo cùng snapshot. Không nên tin vào thứ tự “tự nhiên” của collection như một tie-breaker.

## 5. `$limit`: chỉ cho tối đa N document đi tiếp

### 5.1. Cú pháp

~~~javascript
{ $limit: 5 }
~~~

`$limit` nhận một số nguyên dương biểu diễn **số document tối đa** cho đi tiếp. MongoDB hỗ trợ giới hạn số nguyên 64-bit trong các phiên bản hiện đại; giá trị phải phù hợp khả năng biểu diễn và quy tắc của phiên bản đang chạy.

Ví dụ lấy 3 đơn có amount cao nhất:

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 3 },
  { $project: { _id: 1, amount: 1 } }
])
~~~

Kết quả:

~~~text
o-013  930000
o-010  800000
o-006  700000
~~~

`$limit` **không chọn top N theo nghĩa nghiệp vụ** nếu không có stage sắp xếp phù hợp ở phía trước.

### 5.2. `$limit` không phải điều kiện lọc

~~~javascript
db.orders.aggregate([
  { $limit: 3 }
])
~~~

chỉ giữ tối đa ba document đến đầu pipeline theo thứ tự đang có. Không được gọi đó là “ba đơn mới nhất” nếu chưa sắp theo ngày.

### 5.3. Giới hạn sau `$match`

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 }
])
~~~

Ý nghĩa: lấy **5 đơn PAID mới nhất**. Nếu đặt `$limit` trước `$match` thì kết quả có thể không đủ năm đơn PAID và không phải năm đơn PAID mới nhất trên toàn collection.

### 5.4. `$limit` không đảm bảo có đủ N document

Nếu sau `$match` chỉ có ba document, `{ $limit: 10 }` vẫn chỉ trả ba. `$limit` là **giới hạn tối đa**, không phải yêu cầu tự tạo thêm document hay bảo đảm đầy đủ một trang.

### 5.5. Giá trị giới hạn từ API phải được kiểm soát

Trong API thực, không chuyển vô hạn một `pageSize` do client gửi vào `$limit`. Ví dụ ở tầng ứng dụng:

~~~javascript
// Minh họa biến đã qua validation tại API.
const requestedPageSize = 25
const pageSize = Math.min(Math.max(requestedPageSize, 1), 100)

db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: pageSize }
])
~~~

Giới hạn page size giúp bảo vệ tải database, số document serialize và dung lượng response. MongoDB không tự biết mức page size phù hợp với SLA của ứng dụng.

## 6. `$skip`: bỏ N document đầu theo thứ tự hiện có

### 6.1. Cú pháp

~~~javascript
{ $skip: 5 }
~~~

`$skip` nhận số nguyên **không âm**. `{ $skip: 0 }` không bỏ qua document nào. Giá trị âm, không phải số nguyên hoặc vượt phạm vi cho phép sẽ không hợp lệ.

### 6.2. Bỏ qua sau khi sắp

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 5 },
  { $project: { _id: 1, createdAt: 1 } }
])
~~~

Pipeline sẽ bỏ **năm document đầu tiên trong thứ tự đã xác định**, rồi trả những document còn lại. Nếu bỏ `$sort`, `$skip` chỉ cắt dòng document trong thứ tự thực thi hiện tại; đó không phải cơ sở an toàn cho phân trang.

### 6.3. `$skip` không phải truy vấn nhảy trực tiếp tới vị trí N

Đối với phân trang offset, cơ sở dữ liệu thường vẫn phải duyệt hoặc xử lý những kết quả đứng trước vị trí cần trả, kể cả khi có index phục vụ sort. Ví dụ `$skip: 100000` không có nghĩa index có thể nhảy tức thì đến “record 100001” mà không phải tính/duyệt vùng trước đó.

Đây là lý do **phân trang sâu bằng offset thường đắt dần** khi page number tăng. Phần phân trang keyset ở mục sau trình bày phương án khác.

### 6.4. Bỏ nhiều hơn số document đang có

~~~javascript
db.orders.aggregate([
  { $sort: { _id: 1 } },
  { $skip: 1000 }
])
~~~

Với 16 document trong lab, kết quả rỗng. Không báo lỗi chỉ vì bỏ qua nhiều hơn số phần tử, miễn giá trị skip hợp lệ.

## 7. Ghép `$sort`, `$skip` và `$limit` để phân trang offset

Đây là pipeline kinh điển:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 2 },
  { $limit: 2 },
  {
    $project: {
      _id: 1,
      amount: 1,
      createdAt: 1
    }
  }
])
~~~

Ý nghĩa: trong các đơn PAID của tenant `t-01`, bỏ hai đơn đầu rồi lấy hai đơn tiếp theo.

### 7.1. Công thức offset

Với trang đánh số từ **1**:

\[
\mathrm{offset} = (\mathrm{page} - 1) \times \mathrm{pageSize}
\]

~~~text
page = 1, pageSize = 2 => skip = 0, limit = 2
page = 2, pageSize = 2 => skip = 2, limit = 2
page = 3, pageSize = 2 => skip = 4, limit = 2
~~~

### 7.2. Dữ liệu minh họa ba trang

Với tập PAID của `t-01`:

| Vị trí sau sort | `_id` | `createdAt` |
|---:|---|---|
| 1 | `o-006` | 2026-07-05 10:00 UTC |
| 2 | `o-007` | 2026-07-05 10:00 UTC |
| 3 | `o-002` | 2026-07-04 08:00 UTC |
| 4 | `o-004` | 2026-07-04 08:00 UTC |
| 5 | `o-001` | 2026-07-03 09:00 UTC |

<escape>Vì vậy:</escape>

| Trang | `$skip` | `$limit` | ID kết quả |
|---|---:|---:|---|
| 1 | 0 | 2 | `o-006`, `o-007` |
| 2 | 2 | 2 | `o-002`, `o-004` |
| 3 | 4 | 2 | `o-001` |
| 4 | 6 | 2 | Rỗng |

### 7.3. Mẫu pipeline tham số hóa

~~~javascript
const page = 2
const pageSize = 2
const offset = (page - 1) * pageSize

if (!Number.isSafeInteger(page) || page < 1) {
  throw new Error("INVALID_PAGE")
}
if (!Number.isSafeInteger(pageSize) || pageSize < 1 || pageSize > 100) {
  throw new Error("INVALID_PAGE_SIZE")
}
if (!Number.isSafeInteger(offset)) {
  throw new Error("OFFSET_OUT_OF_RANGE")
}

db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: offset },
  { $limit: pageSize },
  { $project: { _id: 1, amount: 1, createdAt: 1 } }
])
~~~

Trong ứng dụng, `tenantId` thường phải lấy từ ngữ cảnh xác thực; không tin một tenant ID do client tự khai báo như cơ chế cấp quyền. Kiểm tra thêm giới hạn offset/page phù hợp với API, vì số nguyên hợp lệ vẫn có thể dẫn tới truy vấn phân trang rất tốn kém.

## 8. Thứ tự stage thay đổi kết quả thế nào?

### 8.1. Đúng: sort trước, limit sau

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

Lấy ba đơn có amount cao nhất toàn collection.

### 8.2. Sai ý định: limit trước, sort sau

~~~javascript
db.orders.aggregate([
  { $limit: 3 },
  { $sort: { amount: -1, _id: 1 } }
])
~~~

Pipeline này trước hết chỉ nhận ba document xuất hiện đầu trong thứ tự pipeline đang có, **sau đó** sắp những document ấy. Nó không phải truy vấn “top 3 amount trên toàn collection”.

Đặt `$sort` sau `$limit` chỉ hợp lý nếu bạn cố ý muốn chọn một tập con trước rồi sắp riêng tập con ấy; đó là nghiệp vụ khác.

### 8.3. Sai ý định: limit trước skip

~~~javascript
db.orders.aggregate([
  { $sort: { _id: 1 } },
  { $limit: 2 },
  { $skip: 2 }
])
~~~

Theo ý nghĩa logic, `$limit` chỉ cho hai document đi tiếp, `$skip` bỏ cả hai nên kết quả rỗng. Không tương đương:

~~~javascript
db.orders.aggregate([
  { $sort: { _id: 1 } },
  { $skip: 2 },
  { $limit: 2 }
])
~~~

Trong một số chuỗi stage, query optimizer có thể **biến đổi cách thực thi mà vẫn giữ ngữ nghĩa**, nhưng lập trình viên vẫn phải viết pipeline theo logic mình muốn. Không tự đảo vị trí hai stage và mong optimizer sửa sai.

### 8.4. Sai ý định: skip trước sort

~~~javascript
db.orders.aggregate([
  { $skip: 10 },
  { $sort: { createdAt: -1 } },
  { $limit: 5 }
])
~~~

Ở đây 10 document đầu tiên của **thứ tự đầu vào chưa xác định** đã bị loại trước khi sort. Các đơn mới nhất có thể đã bị bỏ mất. Để lấy trang của danh sách theo ngày, phải sắp **trước khi skip**.

### 8.5. Match ở đâu?

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

nghĩa là ba đơn PAID mới nhất.

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 3 },
  { $match: { status: "PAID" } }
])
~~~

nghĩa là lấy ba đơn mới nhất **bất kể status**, rồi chỉ giữ những đơn PAID trong ba đơn đó. Kết quả có thể ít hơn ba hoặc bỏ qua một đơn PAID mới kế tiếp. Hai pipeline không tương đương.

## 9. Sort là stage blocking: bộ nhớ và chi phí

`$sort` là một **blocking stage** theo cách xử lý tổng quát: muốn xác định thứ tự toàn bộ đầu vào, engine có thể cần thu thập, tổ chức hoặc quản lý nhiều document trước khi trả kết quả. Nó có thể gây áp lực bộ nhớ, CPU và I/O, nhất là khi không tận dụng được thứ tự index.

### 9.1. Sort toàn bộ rồi mới giới hạn

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1 } }
])
~~~

Nếu đầu vào có hàng triệu document và không có index phục vụ thứ tự này, sort có thể tốn nhiều tài nguyên.

### 9.2. Top-K: sort rồi limit

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 20 }
])
~~~

MongoDB có thể áp dụng **`$sort` + `$limit` coalescence** (*top-k sort optimization*): khi điều kiện cho phép, thay vì giữ toàn bộ đầu vào để sort, engine duy trì nhóm ứng viên tốt nhất theo giới hạn N. Điều này thường giảm nhu cầu bộ nhớ đáng kể.

Đây là tối ưu của query planner; không được hiểu thành “chỉ đọc 20 document” nếu không có index hữu ích. Để tìm top 20 của một tập lớn, engine có thể vẫn phải xem rất nhiều document dù chỉ giữ top K.

### 9.3. Sort, skip, limit và giới hạn K nội bộ

Với:

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 1000 },
  { $limit: 20 }
])
~~~

Khi planner áp dụng tối ưu tương ứng, sort có thể cần giữ các ứng viên cho **1000 + 20 = 1020** vị trí đầu để xác định 20 document sau khi bỏ qua 1000. Con số **offset + limit** cho thấy phân trang sâu vẫn đắt: page 10000 không rẻ bằng page 1 chỉ vì `$limit` cuối cùng vẫn là 20.

Không viết một công thức cứng để dự đoán mọi plan: tối ưu còn phụ thuộc các stage chen giữa, khả năng dùng index và phiên bản MongoDB.

### 9.4. Memory limit và disk spill

Nhiều stage aggregation cần bộ nhớ để thực thi. Với `$sort` không tận dụng index, khi lượng tài nguyên vượt giới hạn, server có thể cần ghi dữ liệu tạm ra disk (*spill*). Trong các phiên bản MongoDB hiện đại, ngưỡng thường liên quan **100 MB** cho những stage cần nhiều bộ nhớ; từ MongoDB 6.0, tham số `allowDiskUseByDefault` có vai trò quyết định mặc định spill hay báo lỗi khi vượt giới hạn, với khả năng override theo lệnh.

Một lệnh minh họa:

~~~javascript
db.orders.aggregate(
  [
    { $match: { status: "PAID" } },
    { $sort: { amount: -1, _id: 1 } },
    { $limit: 100 }
  ],
  { allowDiskUse: true }
)
~~~

`allowDiskUse: true` **cho phép** một số stage ghi file tạm ra disk khi cần; nó không làm query tự động nhanh, không thay thế index, và có thể tăng disk I/O. `allowDiskUse: false` hoặc mặc định cụ thể có thể dẫn tới lỗi nếu sort vượt ngưỡng mà không được phép spill. Hãy kiểm tra phiên bản và cấu hình MongoDB thực tế.

### 9.5. Giảm đầu vào trước khi sort

Đặt `$match` sớm khi logic cho phép:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 20 }
])
~~~

Ít document cần sort hơn có thể giảm tài nguyên. Tuy nhiên, không được đẩy `$match` lên trước nếu điều kiện phụ thuộc field tính toán chưa tồn tại hoặc thay đổi ý nghĩa sau `$unwind`/`$group`. Query optimizer có thể đẩy một số filter khi an toàn, nhưng nên viết pipeline minh bạch theo mục tiêu nghiệp vụ.

## 10. Index có thể phục vụ `$sort` khi nào?

Một pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 20 }
])
~~~

có thể hưởng lợi từ compound index:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_tenant_status_date_id" }
)
~~~

Hai field đầu được lọc equality, hai field sau cung cấp thứ tự ngày giảm dần, ID tăng dần. Đây là một ví dụ áp dụng nguyên tắc **Equality – Sort – Range** (ESR) khi thiết kế index cho query phổ biến.

### 10.1. Ví dụ sort có thể dùng index

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 }
])
~~~

Trên dữ liệu và plan phù hợp, MongoDB có thể duyệt index theo thứ tự và trả kết quả mà không cần stage SORT riêng trong memory.

### 10.2. Ví dụ sort không được index phục vụ trọn vẹn

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $sort: { createdAt: -1, _id: 1 } }
])
~~~

Index `{tenantId:1,status:1,createdAt:-1,_id:1}` có field **status nằm giữa** tenantId và createdAt. Nếu không có equality trên status, các key bị nhóm theo status trước ngày tạo; index ấy không mặc định cho thứ tự ngày mới nhất trên **toàn tenant**. Có thể cần index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: 1 },
  { name: "idx_tenant_date_id" }
)
~~~

### 10.3. Sort sau các stage chuyển đổi

Ví dụ:

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$region", revenue: { $sum: "$amount" } } },
  { $sort: { revenue: -1, _id: 1 } }
])
~~~

`revenue` được tính sau `$group` nên index trên field `amount` của document gốc không tự cung cấp thứ tự theo **doanh thu tổng**. Sort này áp dụng trên các document nhóm mới tạo.

Tương tự, sau `$unwind` hoặc `$addFields`, khả năng giữ được index sort từ collection gốc phụ thuộc kế hoạch, không thể suy ra chỉ từ việc field từng có index.

### 10.4. Sort trên index một field

Nếu chỉ sort:

~~~javascript
{ $sort: { createdAt: -1 } }
~~~

index đơn `{createdAt:1}` trong nhiều trường hợp có thể được quét **ngược chiều** để đáp ứng sort giảm dần. Nhưng với sort nhiều field **khác hướng nhau**, compound index phải có pattern tương ứng hoặc pattern đảo chiều toàn bộ.

Không cần tạo cả index tăng và giảm cho một field đơn chỉ vì API có hai hướng sort.

## 11. Dùng `explain()` để quan sát hiệu năng

Có thể dùng:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 2 },
  { $limit: 2 },
  { $project: { _id: 1, createdAt: 1, amount: 1 } }
])
~~~

Những thành phần cần quan sát:

| Trường/stage | Cách hiểu |
|---|---|
| `winningPlan` | Kế hoạch được chọn |
| `IXSCAN` | Stage đọc index key |
| `COLLSCAN` | Stage quét collection |
| `FETCH` | Stage đọc document để kiểm tra/trả field |
| `SORT` | Có thao tác sắp xếp riêng |
| `LIMIT`/`SKIP` hoặc biểu diễn tương đương | Phần điều khiển số lượng/vị trí khi optimizer triển khai |
| `nReturned` | Số document được trả ở giai đoạn thống kê liên quan |
| `totalKeysExamined` | Số index key đã kiểm tra |
| `totalDocsExamined` | Số document đã kiểm tra |
| `executionTimeMillis` | Thời gian thực thi được ghi nhận trong lần chạy |

Cấu trúc JSON `explain` có thể khác giữa classic engine và Slot-Based Execution, và optimizer có thể gộp các stage. Vì vậy, **không giả định mỗi stage trong pipeline đều phải xuất hiện với đúng một node tương ứng** trong kế hoạch thực thi.

### 11.1. Phân biệt COLLSCAN và sort trong memory

`COLLSCAN` nghĩa là đọc collection; query có thể vẫn không cần sort nếu không yêu cầu sắp xếp. `IXSCAN` không tự bảo đảm không có SORT; một index có thể giúp filter nhưng không cung cấp thứ tự. Cần xem **cả đường truy cập và cách sắp xếp**.

### 11.2. Các câu hỏi kiểm tra

- Index nào được dùng cho `$match`?
- `$sort` có tận dụng thứ tự index không?
- Có stage SORT riêng không?
- Nhiều key/document có bị xét trước khi `$skip` bỏ qua không?
- `$limit` có làm giảm tài nguyên sort hoặc số document cần FETCH không?
- Query có spill ra disk không, theo thông tin quan sát từ server/profiler?
- Độ trễ ở trang 1 và trang 10000 khác nhau thế nào?

**Đừng benchmark trên 16 document rồi kết luận nhanh/chậm.** Với tập dữ liệu nhỏ, MongoDB có thể chọn COLLSCAN hợp lý; thời gian vài mili giây không đại diện cho dữ liệu thực.

## 12. Phân trang sâu: hạn chế của offset pagination

Một API:

~~~http
GET /orders?page=10000&pageSize=20
~~~

dẫn tới:

~~~text
offset = (10000 - 1) × 20 = 199980
limit = 20
~~~

Pipeline:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 199980 },
  { $limit: 20 }
])
~~~

Ngay cả khi có index phục vụ thứ tự, database vẫn thường phải **đi qua rất nhiều kết quả trước đó** mới trả trang yêu cầu. Nếu dữ liệu liên tục được thêm/xóa, vị trí offset còn có thể dịch chuyển giữa các lần gọi.

### 12.1. Khi offset pagination vẫn phù hợp

- Trang đầu hoặc vài trang đầu, offset nhỏ.
- Admin UI có lượng dữ liệu vừa phải.
- Cần người dùng nhảy tới trang có số cụ thể.
- Workload đủ nhẹ và đã đo chi phí.
- Độ biến động dữ liệu thấp hoặc chấp nhận lệch giữa các trang.

### 12.2. Khi nên cân nhắc keyset pagination

- Feed vô hạn hoặc “Xem thêm”.
- Có nhiều triệu document và page sâu.
- Cần phân trang theo thứ tự ổn định dựa vào indexed key.
- Không cần nhảy trực tiếp tới trang 10.000 theo số trang.
- Muốn giảm chi phí duyệt offset lớn.

## 13. Keyset pagination: phân trang theo khóa cuối của trang trước

Thay vì truyền `skip: 100000`, client truyền **khóa sắp xếp cuối của trang trước**. Với:

~~~javascript
{ $sort: { createdAt: -1, _id: 1 } }
~~~

ta cần cursor gồm hai giá trị:

~~~javascript
{
  lastCreatedAt: ISODate("2026-07-05T10:00:00Z"),
  lastId: "o-007"
}
~~~

Vì createdAt giảm dần, những document **sau** cursor có:

1. `createdAt` nhỏ hơn thời điểm cursor, **hoặc**
2. `createdAt` bằng thời điểm cursor và `_id` lớn hơn ID cursor (vì `_id` tăng dần trong nhóm cùng ngày).

### 13.1. Trang đầu tiên

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 2 },
  { $project: { _id: 1, createdAt: 1, amount: 1 } }
])
~~~

Kết quả: `o-006`, `o-007`. Client giữ `createdAt` và `_id` của `o-007` để lấy trang tiếp.

### 13.2. Trang tiếp theo

~~~javascript
const cursorDate = ISODate("2026-07-05T10:00:00Z")
const cursorId = "o-007"

db.orders.aggregate([
  {
    $match: {
      tenantId: "t-01",
      status: "PAID",
      $or: [
        { createdAt: { $lt: cursorDate } },
        {
          createdAt: cursorDate,
          _id: { $gt: cursorId }
        }
      ]
    }
  },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 2 },
  { $project: { _id: 1, createdAt: 1, amount: 1 } }
])
~~~

Kết quả: `o-002`, `o-004`. Không cần `$skip` vì điều kiện cursor loại toàn bộ document ở các vị trí trước.

### 13.3. Index phù hợp

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_tenant_status_date_id" }
)
~~~

Đây là index ứng viên cho filter equality + điều kiện keyset + sort. Với `$or`, planner có thể thực hiện nhiều nhánh/bounds; cần dùng `explain` để đánh giá.

### 13.4. Khi sort theo chiều khác, dấu điều kiện phải thay

Nếu dùng:

~~~javascript
{ $sort: { amount: -1, _id: -1 } }
~~~

thì trang tiếp theo cần:

~~~javascript
{
  $or: [
    { amount: { $lt: lastAmount } },
    {
      amount: lastAmount,
      _id: { $lt: lastId }
    }
  ]
}
~~~

Không sao chép nguyên điều kiện `_id: {$gt: ...}` của sort hỗn hợp hướng sang sort cả hai field giảm dần. Điều kiện cursor phải cùng ngữ nghĩa với thứ tự so sánh của bộ khóa.

### 13.5. Keyset cũng có giới hạn

- Cần bộ khóa sort có thứ tự tổng ổn định (thường thêm ID duy nhất).
- Sort key có thể thay đổi sau khi đã phân trang, làm document dịch chuyển.
- Thêm/xóa document giữa các request vẫn ảnh hưởng tập dữ liệu; keyset **không tự cung cấp snapshot toàn phiên**.
- Không hỗ trợ nhảy trực tiếp đến một trang số bất kỳ mà không có cursor.
- Cursor nên mã hóa và kiểm tra hợp lệ, gắn với filter/sort/tenant để tránh dùng nhầm.

Nếu cần xem một snapshot nhất quán ở nhiều thời điểm, phải thiết kế khả năng đọc theo một version/cutoff hoặc cơ chế consistency phù hợp, không chỉ dựa vào `$sort`.

## 14. Phân trang kèm tổng số kết quả bằng `$facet`

API thường muốn trả:

~~~javascript
{
  items: [/* document của trang hiện tại */],
  total: 5
}
~~~

Một pipeline có thể dùng `$facet` để tạo hai nhánh trên cùng tập đầu vào **đã được match**:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  {
    $facet: {
      items: [
        { $sort: { createdAt: -1, _id: 1 } },
        { $skip: 2 },
        { $limit: 2 },
        {
          $project: {
            _id: 1,
            createdAt: 1,
            amount: 1
          }
        }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
])
~~~

Với dữ liệu lab:

~~~javascript
{
  items: [
    { _id: "o-002", /* createdAt và amount */ },
    { _id: "o-004", /* createdAt và amount */ }
  ],
  metadata: [
    { total: 5 }
  ]
}
~~~

**Ý nghĩa:** nhánh `items` trả một trang, nhánh `metadata` đếm tất cả document đã qua `$match` trước `$facet`, chứ không chỉ đếm số item trong trang.

### 14.1. Chú ý chi phí `$facet`

`$facet` không miễn phí: các nhánh phải xử lý dữ liệu đầu vào, và kết quả cuối là **một document** chứa các mảng. Stage này có giới hạn bộ nhớ/kích thước kết quả riêng và không phải lúc nào cũng áp dụng được tối ưu index giống một pipeline tuyến tính `$match → $sort → $limit`.

Nếu `$facet` nằm ngay đầu pipeline, nó có thể buộc xử lý toàn bộ collection theo cách không mong muốn. Thường nên đặt `$match` có thể dùng index trước `$facet`, và benchmark trên workload thật.

### 14.2. Vì sao metadata có thể rỗng?

Nếu không document nào khớp, nhánh:

~~~javascript
metadata: [{ $count: "total" }]
~~~

có thể trả `[]`, không phải `[{total:0}]`. Tầng API cần chuẩn hóa thành `0` nếu contract yêu cầu, hoặc thêm stage biến đổi phù hợp để trả kết quả ổn định.

### 14.3. Hai query riêng cũng có thể hợp lý

Không bắt buộc dùng `$facet` cho mọi API. Có thể chạy:

~~~javascript
db.orders.countDocuments({ tenantId: "t-01", status: "PAID" })
~~~

và một pipeline lấy trang. Cách này có thể tận dụng index theo hai kế hoạch khác nhau, nhưng hai request tách rời có thể nhìn thấy trạng thái dữ liệu khác nhau nếu có ghi đồng thời. Chọn phương án theo yêu cầu nhất quán, hiệu năng và giao diện API.

## 15. `$sort` sau `$group`: bảng xếp hạng từ dữ liệu đã tổng hợp

Khi cần bảng xếp hạng doanh thu theo khu vực, mỗi document đầu vào là một đơn hàng nhưng mỗi kết quả đầu ra là **một nhóm**.

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$region",
      totalRevenue: { $sum: "$amount" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { totalRevenue: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

Luồng:

~~~mermaid
flowchart LR
    O["N đơn hàng"] --> M["Chỉ PAID"]
    M --> G["$group theo region"]
    G --> R["3 document nhóm: HCM/HN/DN"]
    R --> S["$sort theo totalRevenue"]
    S --> L["$limit: top 3 vùng"]
~~~

### 15.1. Đặt limit trước group là bài toán khác

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 },
  { $group: { _id: "$region", count: { $sum: 1 } } }
])
~~~

Pipeline này đếm **theo region trong 5 đơn mới nhất**, không phải đếm mọi đơn của cả collection rồi lấy top 5 region.

### 15.2. Đặt sort trước group ảnh hưởng `$first` và `$last`

Ví dụ lấy đơn mới nhất theo customer:

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  {
    $group: {
      _id: "$customerId",
      latestOrder: { $first: "$$ROOT" }
    }
  },
  {
    $project: {
      _id: 1,
      latestOrderId: "$latestOrder._id",
      latestCreatedAt: "$latestOrder.createdAt"
    }
  }
])
~~~

`$first` lấy giá trị đầu tiên theo thứ tự document đến `$group`. Nếu cần “mới nhất”, phải xác định thứ tự trước khi nhóm hoặc dùng các accumulator chuyên biệt phù hợp với phiên bản MongoDB. **Sort theo khóa xác định**, có tie-breaker, để tránh chọn ngẫu nhiên trong trường hợp cùng timestamp.

## 16. `$sort` với `$unwind`: thứ tự document và phần tử mảng

Giả sử:

~~~javascript
db.baskets.insertMany([
  {
    _id: "basket-1",
    items: [
      { sku: "A", qty: 1 },
      { sku: "B", qty: 5 }
    ]
  },
  {
    _id: "basket-2",
    items: [
      { sku: "C", qty: 3 },
      { sku: "D", qty: 2 }
    ]
  }
])
~~~

Muốn lấy **top 3 dòng hàng** theo qty:

~~~javascript
db.baskets.aggregate([
  { $unwind: "$items" },
  { $sort: { "items.qty": -1, _id: 1 } },
  { $limit: 3 },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.qty"
    }
  }
])
~~~

Sau `$unwind`, mỗi document trung gian đại diện **một item**, nên `$limit: 3` giới hạn **ba item**, không phải ba basket.

Ngược lại:

~~~javascript
db.baskets.aggregate([
  { $limit: 1 },
  { $unwind: "$items" }
])
~~~

chỉ chọn một basket đầu vào rồi bung tất cả item của basket ấy. Kết quả có thể có nhiều hơn một document dù đã dùng `$limit: 1` ở đầu pipeline.

### Tư duy kiểm tra khi dùng `$skip` sau `$unwind`

Hãy hỏi “một document ở stage này là gì?” Nếu sau unwind, một document là item, thì `$skip: 10` nghĩa là bỏ **10 item đã bung**, không phải bỏ 10 giỏ hàng gốc. Muốn phân trang giỏ hàng, thường đặt `$sort/$skip/$limit` ở giai đoạn còn giữ mỗi giỏ hàng là một document, trước khi unwind, nếu yêu cầu nghiệp vụ cho phép.

## 17. Thứ tự của field thiếu, `null` và kiểu BSON

Sắp xếp phải dựa trên quy tắc so sánh BSON của MongoDB. Những document có field sort bị thiếu hoặc là `null` có thể đứng khác vị trí so với các document chứa string/number/Date.

### 17.1. Field thiếu

~~~javascript
db.sort_values.insertMany([
  { _id: "v-1", rank: 3 },
  { _id: "v-2", rank: null },
  { _id: "v-3" },
  { _id: "v-4", rank: 1 }
])

db.sort_values.aggregate([
  { $sort: { rank: 1, _id: 1 } }
])
~~~

Trong so sánh phục vụ sort, missing và null có ngữ nghĩa gần nhau; thêm `_id` giúp tạo thứ tự xác định giữa những document có khóa sort tương đương.

Nếu sản phẩm thật cần “đưa document thiếu rank xuống cuối” bất kể sort tăng/giảm, hãy **tạo một sort key riêng** với logic rõ:

~~~javascript
db.sort_values.aggregate([
  {
    $addFields: {
      missingRank: {
        $cond: [
          { $in: [{ $type: "$rank" }, ["missing", "null"]] },
          1,
          0
        ]
      }
    }
  },
  { $sort: { missingRank: 1, rank: 1, _id: 1 } }
])
~~~

Ví dụ đánh dấu cả missing và explicit null ở cuối. Khi dùng expression tính toán, khả năng tận dụng index cho sort có thể thay đổi.

### 17.2. Kiểu dữ liệu hỗn hợp

Nếu `amount` ở document này là Decimal128, ở document khác là string `"500000"`, sort có thể nhóm các giá trị theo thứ tự BSON type, không tự hiểu chuỗi là tiền. Nguyên tắc:

- Dùng BSON numeric type nhất quán cho field số.
- Dùng BSON Date cho thời gian.
- Chuẩn hóa timezone và quy ước format ở API.
- Dùng schema validation nếu hệ thống yêu cầu kiểu cố định.

### 17.3. Sort theo mảng

Khi field sort là mảng, MongoDB có những quy tắc chọn giá trị đại diện từ mảng: trong trường hợp thông thường, **sort tăng dần dùng phần tử nhỏ nhất**, còn **sort giảm dần dùng phần tử lớn nhất** của mảng để so sánh. Điều kiện `$match` trên mảng không nhất thiết làm phần tử được chọn cho sort thay đổi theo mong muốn.

Ví dụ:

~~~javascript
db.array_sort_lab.insertMany([
  { _id: "a-1", scores: [30, 90] },
  { _id: "a-2", scores: [45, 60] },
  { _id: "a-3", scores: [10, 100] }
])

db.array_sort_lab.aggregate([
  { $sort: { scores: 1, _id: 1 } }
])

db.array_sort_lab.aggregate([
  { $sort: { scores: -1, _id: 1 } }
])
~~~

Ở sort tăng, giá trị so sánh đại diện là 30, 45, 10; thứ tự sẽ khác khi sort giảm dùng 90, 60, 100. Nếu nghiệp vụ muốn sort theo **trung bình**, **tổng** hoặc **một phần tử được lọc cụ thể**, hãy tính field tương ứng trước khi `$sort` (ví dụ `$avg` hoặc `$max`), không dựa vào sort mặc định của mảng.

## 18. Collation: sắp xếp chuỗi theo ngôn ngữ

Nếu có field `displayName`, sort chuỗi chịu ảnh hưởng của collation. Các lựa chọn về hoa/thường, dấu và locale có thể làm thứ tự khác nhau.

~~~javascript
db.customers.aggregate(
  [
    { $sort: { displayName: 1, _id: 1 } },
    { $limit: 20 }
  ],
  {
    collation: {
      locale: "vi",
      strength: 2
    }
  }
)
~~~

Ý nghĩa của `locale` và `strength` phụ thuộc quy tắc collation của MongoDB/ICU. Không được giả định mọi collation đều cho một thứ tự giống byte/string binary.

### Collation và index

Nếu index được tạo với collation khác query, MongoDB có thể không dùng được index đó để đáp ứng một phần equality/sort chuỗi. Khi xây dựng bảng danh sách tên:

1. Xác định collation mà API cần.
2. Tạo index với collation phù hợp nếu workload quan trọng.
3. Đảm bảo query dùng cùng collation theo hợp đồng.
4. Đo `explain()` để xác nhận không có SORT ngoài dự kiến.

Collation không thay thế chuẩn hóa identifier hoặc kiểm tra quyền truy cập.

## 19. Sort sau `$project` và các phép biến đổi khác

Nếu một stage loại field cần sort, stage tiếp theo có thể không còn dữ liệu để so sánh:

~~~javascript
// Không phù hợp nếu muốn sort theo createdAt vì field đã bị loại.
db.orders.aggregate([
  { $project: { _id: 1, status: 1 } },
  { $sort: { createdAt: -1, _id: 1 } }
])
~~~

Ở mức logic, `createdAt` không còn trong document sau projection. Query optimizer có thể hoán đổi các stage khi chứng minh an toàn trong một số trường hợp, nhưng lập trình viên không nên thiết kế pipeline dựa vào giả định “optimizer sẽ luôn sửa lại”.

Cách minh bạch:

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 },
  { $project: { _id: 1, status: 1 } }
])
~~~

Ở đây giữ field cần thiết đến khi sort xong rồi mới loại.

### 19.1. Khi cần sort trên field được tạo mới

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      customerId: 1,
      normalizedScore: { $multiply: ["$score", 10] }
    }
  },
  { $sort: { normalizedScore: -1, _id: 1 } },
  { $limit: 5 }
])
~~~

Đây là ví dụ **phải tính trước rồi mới sort**. Không thể sort theo `normalizedScore` trước khi nó tồn tại, nếu không có field cùng tên tương đương trong collection gốc.

### 19.2. Ghi nhận ranh giới thay đổi số lượng

| Stage | Có thể thay đổi số document đi tiếp? | Ảnh hưởng đến phân trang |
|---|---|---|
| `$match` | Có, lọc bớt | Page dựa trên tập đã lọc |
| `$sort` | Không tự thêm/bỏ | Quyết định thứ tự |
| `$skip` | Có, loại prefix | Dịch điểm bắt đầu |
| `$limit` | Có, giữ tối đa N | Giới hạn trang |
| `$project` | Thông thường giữ số lượng | Thay field để trả hoặc dùng cho sort |
| `$unwind` | Có thể tăng/giảm | Page sau unwind là page phần tử |
| `$group` | Có thể giảm/thay cardinality | Page sau group là page nhóm |
| `$lookup` | Thường giữ số document nếu chưa unwind | Có thể làm document rộng hơn, ảnh hưởng sort/memory |

Thực hành tốt: **vẽ lại một document ở mỗi stage đang đại diện cho thực thể nào** trước khi đặt pagination.

## 20. Sort theo score và tạo bảng xếp hạng

Ứng dụng game/đánh giá có thể xếp hạng:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { score: -1, createdAt: 1, _id: 1 } },
  { $limit: 5 },
  {
    $project: {
      _id: 1,
      score: 1,
      createdAt: 1
    }
  }
])
~~~

Khi score bằng nhau, ưu tiên thời điểm tạo cũ hơn; nếu vẫn bằng, ID nhỏ hơn. Đây là một **quy tắc nghiệp vụ** cụ thể. Hãy công bố rõ thứ tự phụ để người dùng không thấy bảng xếp hạng thay đổi bất ngờ.

### 20.1. Top N mỗi nhóm khác top N toàn collection

Pipeline:

~~~javascript
db.orders.aggregate([
  { $sort: { score: -1, _id: 1 } },
  { $limit: 3 }
])
~~~

lấy top 3 của **toàn bộ collection**.

Nếu cần **top 3 theo mỗi tenant**, chỉ `$sort + $limit` ở cấp toàn cục là không đủ. Cần pipeline có `$group`, toán tử cửa sổ hoặc accumulator top-N phù hợp với phiên bản; mỗi nhóm có bộ giới hạn riêng. Đây là bài toán nâng cao hơn phân trang toàn tập.

### 20.2. Rank không bằng vị trí sau limit

Nếu hai document có cùng score, khái niệm **rank** có thể cho đồng hạng, còn thứ tự `$sort` với tie-breaker vẫn xếp một document trước document kia. Nếu cần rank có đồng hạng, xem xét window functions như `$rank`/`$denseRank` trong pipeline phù hợp, thay vì tự suy ra rank từ vị trí thứ tự.

## 21. Phân trang và độ nhất quán khi dữ liệu thay đổi

Giả sử trang 1:

~~~text
o-006
o-007
~~~

giữa lúc client gọi trang 1 và trang 2, một đơn mới `o-new` được chèn với `createdAt` lớn hơn tất cả đơn hiện tại. Danh sách đã sort có thể dịch:

~~~text
Trước insert:
1 o-006
2 o-007
3 o-002
4 o-004

Sau insert:
1 o-new
2 o-006
3 o-007
4 o-002
5 o-004
~~~

Khi gọi trang 2 với `$skip: 2`, client có thể lại thấy `o-007` — một bản ghi đã có ở trang 1.

### 21.1. Có tie-breaker vẫn chưa đủ

`_id` giúp thứ tự xác định khi dữ liệu giống nhau, nhưng **insert/delete/update giữa hai request** có thể làm offset thay đổi.

### 21.2. Keyset giảm dịch chuyển offset

Nếu dùng cursor sau `o-007`, một đơn mới có ngày lớn hơn cursor sẽ không khiến trang sau bắt đầu lệch vị trí theo offset. Keyset vì thế thường thân thiện với feed được cập nhật liên tục hơn. Tuy nhiên:

- Document cũ bị sửa sort key có thể vẫn tạo thay đổi.
- Document bị xóa giữa các trang sẽ biến mất.
- Query chạy sau có thể thấy document mới lọt phía sau cursor.

Không được quảng cáo keyset là snapshot tuyệt đối.

### 21.3. Khi cần một tập dữ liệu cố định

Với xuất báo cáo kiểm toán hoặc duyệt toàn bộ dataset nhất quán, có thể phải:

- Đóng băng phạm vi dữ liệu bằng cutoff/version.
- Gắn query với một snapshot/transaction trong giới hạn hỗ trợ.
- Tạo một danh sách ID tạm hoặc materialized result ổn định.
- Dùng batch export được thiết kế cho tính nhất quán.

Không nên giữ một transaction kéo dài hàng giờ chỉ để phân trang API thông thường; giới hạn transaction và tài nguyên phải được xét trong kiến trúc.

## 22. Truy vấn nào nên dùng `$sort`, `$limit`, `$skip`?

| Nhu cầu | Mẫu pipeline | Ghi chú |
|---|---|---|
| 10 đơn mới nhất | `$sort → $limit` | Dùng tie-breaker |
| Trang 3, mỗi trang 20 | `$sort → $skip:40 → $limit:20` | Offset lớn có thể đắt |
| 5 đơn PAID mới nhất | `$match → $sort → $limit` | Match trước giới hạn |
| 5 vùng doanh thu cao nhất | `$match → $group → $sort → $limit` | Sort trên kết quả group |
| Top 10 item sau khi tách mảng | `$unwind → $sort → $limit` | Phân trang theo item |
| Trang kèm tổng bản ghi | `$match → $facet(items,metadata)` | Đo footprint/độ trễ |
| Feed trang tiếp theo theo cursor | `$match(cursor) → $sort → $limit` | Tránh offset sâu |
| Danh sách tên theo locale | `$sort` + `collation` | Index cần collation tương thích |
| Sắp theo field tính toán | `$addFields/$project → $sort → $limit` | Có thể không dùng index cho sort |

## 23. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `$skip` mà không `$sort` | Trang không có thứ tự ổn định | Sort theo khóa xác định trước skip |
| Sort chỉ theo timestamp trùng nhau | Document có thể đảo vị trí giữa các trang | Thêm `_id` hoặc khóa duy nhất làm tie-breaker |
| `$limit` trước `$sort` để lấy top N | Chỉ sort một tập con tùy ý | Sort toàn tập phù hợp rồi limit |
| `$limit` trước `$skip` khi phân trang | Bỏ từ một tập đã bị cắt, có thể rỗng | Sort → skip → limit |
| `$match` sau `$limit` để tìm top PAID | Bỏ qua đơn PAID phù hợp nằm ngoài giới hạn đầu | Match → sort → limit |
| `$sort` sau `$project` đã loại sort key | Mọi document có thể bị coi như thiếu field | Sort trước khi loại field hoặc giữ field |
| Coi `$skip` lớn là nhảy tức thì | Query trang sâu chậm | Keyset/cursor pagination |
| Không xét số document sau `$unwind` | Page item thay vì page đơn | Đặt stage theo thực thể muốn phân trang |
| Tưởng index filter tự giúp sort mọi kiểu | Có thể còn stage SORT | Index filter+sort tương thích, dùng explain |
| Cho rằng `allowDiskUse:true` luôn nhanh | Disk spill có thể tốn I/O | Match sớm, top-k, index phù hợp |
| Quên validation số trang | Skip âm, limit không hợp lệ hoặc offset quá lớn | Kiểm tra page/pageSize/offset |
| Coi tie-breaker là snapshot qua nhiều request | Insert/delete vẫn làm lệch tập dữ liệu | Keyset, cutoff/version/snapshot khi cần |
| Đếm số kết quả sau `$limit` làm total | Total sai | Count trên tập đã match trước pagination |
| Sort array mà tưởng theo trung bình | MongoDB dùng quy tắc sort array riêng | Tính sort key mong muốn trước |
| So sánh tiền số với chuỗi | Thứ tự BSON không phản ánh tiền | Chuẩn hóa kiểu dữ liệu |

## 24. Thực hành tổng hợp trên `orders`

Hãy dùng bộ dữ liệu 16 document trong mục 2. Trước khi chạy, dự đoán các ID và giải thích **mỗi stage đang xử lý tập nào**.

### Bài 1 — Sort theo amount

Viết aggregation lấy 5 đơn có amount lớn nhất, trả `_id` và `amount`, dùng `_id` làm tie-breaker. Dự đoán thứ tự năm ID.

### Bài 2 — Sort theo hai field

Lấy mọi đơn của `t-01`, sắp theo `createdAt` giảm dần và `_id` tăng dần. Vì sao chỉ sort createdAt có thể không đủ?

### Bài 3 — Ba trang liên tiếp

Lấy các đơn PAID của `t-01` với `pageSize = 2`. Chạy:

- Trang 1: skip 0, limit 2.
- Trang 2: skip 2, limit 2.
- Trang 3: skip 4, limit 2.

Ghi kết quả và giải thích vì sao trang 3 chỉ có một document.

### Bài 4 — Thứ tự stage

So hai pipeline:

~~~javascript
// A
[
  { $sort: { amount: -1 } },
  { $limit: 3 }
]

// B
[
  { $limit: 3 },
  { $sort: { amount: -1 } }
]
~~~

Chúng có cùng ý nghĩa không? Trong trường hợp nào B có thể hợp lý?

### Bài 5 — Lọc trước hay sau limit?

Viết hai pipeline: một lấy **3 đơn PAID mới nhất**, một lấy **3 đơn mới nhất toàn collection rồi chỉ giữ PAID**. Giải thích vì sao số kết quả khác nhau.

### Bài 6 — Group rồi sort

Tính tổng `amount` cho đơn PAID theo `region`, sắp từ cao xuống thấp, lấy top 2 vùng. Vì sao không thể đặt `$limit:2` trước `$group` nếu muốn tổng của toàn bộ đơn PAID?

### Bài 7 — Thêm `$project`

Lấy 5 đơn mới nhất nhưng response chỉ có `_id`, `tenantId` và `status`. Đặt `$project` ở đâu để vẫn sort đúng theo `createdAt`?

### Bài 8 — Index

Tạo:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: 1
})
~~~

Chạy `db.orders.explain("executionStats").aggregate(...)` với query danh sách PAID của tenant. Quan sát plan và thảo luận tại sao dữ liệu 16 document không đủ kết luận về performance.

### Bài 9 — Keyset

Trang 1 PAID của `t-01` có `o-006`, `o-007`. Viết filter trang 2 từ cursor của `o-007` theo thứ tự `createdAt:-1,_id:1`. Không dùng `$skip`.

### Bài 10 — Total count

Xây `$facet` trả trang 2 và `total` cho đơn PAID của `t-01`. Đếm total từ tập trước khi `$skip`.

### Bài 11 — Sort theo array

Tạo ba document có mảng score ở mục 17.3, so kết quả sort tăng và giảm; giải thích phần tử mảng nào được dùng làm giá trị so sánh mặc định.

### Bài 12 — Deep pagination

Với page 10.000 và size 20, tính offset và giải thích vì sao index phục vụ sort vẫn không làm `$skip` trở thành thao tác O(1). Đề xuất phương án phân trang khác và hạn chế của nó.

## 25. Đáp án định hướng

### Bài 1

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 5 },
  { $project: { _id: 1, amount: 1 } }
])
~~~

Kết quả: `o-013`, `o-010`, `o-006`, `o-011`, `o-007`.

### Bài 2

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01" } },
  { $sort: { createdAt: -1, _id: 1 } }
])
~~~

`o-006` và `o-007` cùng timestamp. Thêm `_id` đảm bảo thứ tự của hai document này được xác định khi tập dữ liệu không đổi.

### Bài 3

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $skip: 2 },
  { $limit: 2 },
  { $project: { _id: 1, createdAt: 1 } }
])
~~~

Trang 1: `o-006`, `o-007`; trang 2: `o-002`, `o-004`; trang 3: `o-001`. Có năm document khớp nên trang thứ ba không đủ hai document.

### Bài 4

A trả top 3 toàn tập. B giới hạn ba document đến đầu pipeline trước, rồi mới sắp chúng; không giải quyết cùng bài toán. B chỉ hợp lý khi việc **chọn một tập con trước** là ý định nghiệp vụ.

### Bài 5

~~~javascript
// 3 đơn PAID mới nhất.
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 3 }
])

// Lấy 3 đơn mới nhất, sau đó mới lọc PAID.
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 3 },
  { $match: { status: "PAID" } }
])
~~~

Hai pipeline có tập ứng viên khác nhau. Nếu top 3 toàn tập chứa đơn CREATED, pipeline thứ hai có thể trả ít hơn 3 PAID.

### Bài 6

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$region",
      totalRevenue: { $sum: "$amount" }
    }
  },
  { $sort: { totalRevenue: -1, _id: 1 } },
  { $limit: 2 }
])
~~~

Giới hạn trước group chỉ tính tổng trên subset đã bị cắt, không phải tổng toàn bộ đơn PAID.

### Bài 7

~~~javascript
db.orders.aggregate([
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 5 },
  { $project: { _id: 1, tenantId: 1, status: 1 } }
])
~~~

Sort trước khi loại `createdAt` khỏi kết quả trả về.

### Bài 9

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "t-01",
      status: "PAID",
      $or: [
        {
          createdAt: { $lt: ISODate("2026-07-05T10:00:00Z") }
        },
        {
          createdAt: ISODate("2026-07-05T10:00:00Z"),
          _id: { $gt: "o-007" }
        }
      ]
    }
  },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 2 }
])
~~~

Kết quả: `o-002`, `o-004`. Điều kiện `_id: {$gt: ...}` đúng vì ID được sort tăng dần trong nhóm có cùng createdAt.

### Bài 10

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "t-01", status: "PAID" } },
  {
    $facet: {
      items: [
        { $sort: { createdAt: -1, _id: 1 } },
        { $skip: 2 },
        { $limit: 2 }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
])
~~~

`total = 5` dù trang 2 chỉ có hai document.

### Bài 12

`offset = 199980`. `$skip` vẫn phải loại các kết quả trước vùng cần trả; keyset dùng điều kiện theo khóa cuối của trang trước, phù hợp feed tuần tự, nhưng không thể nhảy tới trang bất kỳ và không tự cung cấp snapshot qua nhiều request.

## 26. Câu hỏi ôn tập

**1. `$sort` khác `$limit` thế nào?**

`$sort` quyết định thứ tự document; `$limit` giữ tối đa N document đi tiếp. Muốn top N theo một tiêu chí, thường phải sort trước limit.

**2. `$skip` có tự sắp xếp document không?**

Không. Nó chỉ bỏ qua N document đầu của thứ tự input đang có. Phân trang ổn định cần sort rõ ràng.

**3. Vì sao sort theo createdAt đơn lẻ chưa đủ cho phân trang?**

Nhiều document có thể cùng timestamp. MongoDB không đảm bảo thứ tự giữa các giá trị sort bằng nhau; thêm `_id` duy nhất làm tie-breaker.

**4. Đặt `$limit` trước `$sort` có luôn sai không?**

Không sai cú pháp, nhưng nó giải bài toán khác: giới hạn đầu vào trước rồi mới sort subset. Nó không phải top N toàn tập.

**5. Công thức trang thứ p, size n đánh số từ 1?**

`skip = (p - 1) × n`, sau đó `limit = n`, với điều kiện sort đã xác định.

**6. Trang có ít hơn n document có phải lỗi không?**

Không. `$limit` chỉ giới hạn tối đa; có thể không còn đủ document sau filter/skip.

**7. `$sort` có thể dùng index trong aggregation không?**

Có, khi query shape/stage và index phù hợp, ví dụ `$match` equality theo tiền tố rồi sort theo các key tiếp theo. Không phải mọi `$sort` đều được index phục vụ.

**8. Tại sao sort sau `$group` thường cần xử lý kết quả nhóm?**

Field tổng hợp như `totalRevenue` không tồn tại ở collection gốc; nó được tính từ `$group`. Index trên amount gốc không tự cung cấp thứ tự theo tổng doanh thu.

**9. `allowDiskUse:true` có làm mọi sort nhanh hơn không?**

Không. Nó cho phép một số stage ghi tạm ra disk khi cần; disk spill có thể tốn I/O. Index và giảm đầu vào vẫn quan trọng.

**10. `$sort + $limit` có lợi thế hiệu năng nào?**

Planner có thể áp dụng top-k/coalescence để chỉ giữ các ứng viên tốt nhất theo N, giảm nhu cầu bộ nhớ trong trường hợp phù hợp. Nhưng không có nghĩa chỉ cần xem N document.

**11. Vì sao skip 100.000 thường chậm hơn skip 20?**

Database vẫn phải duyệt hoặc xử lý nhiều kết quả đứng trước vị trí offset lớn. Index không biến skip thành phép nhảy vị trí tức thì.

**12. Keyset pagination khác offset pagination thế nào?**

Offset bỏ N document đầu. Keyset dùng điều kiện trên khóa sort cuối của trang trước rồi lấy `limit` tiếp theo, thường tránh quét offset sâu và giảm lệch do insert phía trước cursor.

**13. Keyset có bảo đảm snapshot của toàn bộ các trang không?**

Không. Thay đổi dữ liệu giữa các request vẫn có thể ảnh hưởng. Cần cutoff/version/snapshot khi yêu cầu nhất quán cao.

**14. Muốn trả total của tập lọc, nên đếm sau hay trước skip/limit?**

Đếm trên tập đã match **trước pagination**. `$facet` có thể tạo một nhánh count và một nhánh items.

**15. `$sort` sau `$unwind` sắp xếp đối tượng gì?**

Sắp xếp các document trung gian sau khi mỗi phần tử mảng đã được tách. `$limit` sau đó giới hạn số phần tử đã bung, không nhất thiết số document gốc.

**16. Có cần thêm `$project` để giới hạn số document không?**

Không. `$project` chọn/biến đổi field; `$limit` và `$skip` mới điều khiển số document. Tuy nhiên `$project` có thể thay sort key nếu đặt sai vị trí.

**17. Dữ liệu string tiền tệ và numeric tiền tệ có sort giống nhau không?**

Không nên giả định. BSON có quy tắc thứ tự theo type; lưu numeric nhất quán và dùng schema validation.

**18. Tại sao collation quan trọng khi sort tên?**

Vì cách so sánh chữ hoa, dấu và locale ảnh hưởng thứ tự. Query và index cần collation tương thích để tận dụng index cho sort chuỗi.

## 27. Bảng lệnh ghi nhớ nhanh

| Mục đích | Stage / pipeline |
|---|---|
| Sort tăng | `{$sort:{amount:1}}` |
| Sort giảm | `{$sort:{createdAt:-1}}` |
| Sort có tie-breaker | `{$sort:{createdAt:-1,_id:1}}` |
| Giữ tối đa N document | `{$limit:N}` với N dương |
| Bỏ qua N document đầu | `{$skip:N}` với N không âm |
| Top N document | `$sort → $limit` |
| Trang p, size n | `$sort → $skip:(p-1)*n → $limit:n` |
| Top N sau filter | `$match → $sort → $limit` |
| Xếp hạng nhóm theo tổng | `$group → $sort → $limit` |
| Top item sau bung mảng | `$unwind → $sort → $limit` |
| Trang kèm total | `$match → $facet(items, metadata)` |
| Trang tiếp không dùng offset | `$match(cursor) → $sort → $limit` |
| Sort field tính toán | `$addFields/$project → $sort` |
| Cho phép spill khi hỗ trợ | `aggregate(pipeline,{allowDiskUse:true})` |
| Kiểm tra execution plan | `db.orders.explain("executionStats").aggregate(pipeline)` |

## 28. Checklist trước khi triển khai API phân trang

- [ ] Filter trước phân trang đã đúng ranh giới tenant, quyền truy cập và trạng thái?
- [ ] Thứ tự sort phản ánh yêu cầu nghiệp vụ?
- [ ] Đã có tie-breaker duy nhất như `_id` để xử lý giá trị sort trùng?
- [ ] `$sort` xuất hiện trước `$skip` và `$limit` nếu cần top/page theo thứ tự?
- [ ] Page/pageSize/offset được kiểm tra số nguyên và giới hạn theo API?
- [ ] Có hạn chế page sâu hoặc phương án keyset/cursor khi dữ liệu lớn?
- [ ] Các khóa sort có kiểu nhất quán, null/missing/array được xử lý theo contract?
- [ ] Có index phù hợp với `$match` và thứ tự `$sort`?
- [ ] Đã xem `explain` để phân biệt IXSCAN, FETCH, SORT và số key/document examined?
- [ ] Có kiểm soát memory/disk spill cho pipeline sort lớn?
- [ ] Count total được tính trên tập lọc trước pagination?
- [ ] Các stage `$unwind`/`$group` có được đặt đúng theo thực thể muốn phân trang?
- [ ] Có kế hoạch xử lý document được thêm/xóa/sửa giữa các trang?
- [ ] API trả cursor gắn với filter/sort/tenant và xác thực đầu vào nếu dùng keyset?
- [ ] Đã đo trang đầu và trang sâu trên dữ liệu đủ lớn thay vì chỉ bộ lab?

## 29. Kết luận

`$sort`, `$limit` và `$skip` là ba stage cơ bản nhưng quyết định trực tiếp **độ đúng đắn của danh sách và khả năng mở rộng của API phân trang**. `$sort` xác định thứ tự, `$skip` bỏ những phần tử đầu tiên theo thứ tự đó, còn `$limit` giữ một số lượng tối đa. Để trả “trang thứ N”, cần có thứ tự xác định, thường là bộ khóa gồm field nghiệp vụ và một ID duy nhất.

Ở workload lớn, chú ý rằng `$sort` có thể tốn bộ nhớ hoặc cần disk spill, còn `$skip` với offset sâu thường vẫn phải xử lý rất nhiều document. Kết hợp `$match` sớm, index phù hợp, top-k optimization, `explain()` và **keyset pagination** khi cần feed sâu là những bước quan trọng. Cuối cùng, hãy luôn hỏi **“một document ở stage hiện tại đại diện cho thực thể nào?”** trước khi đặt sort/skip/limit — đặc biệt khi pipeline đã dùng `$group`, `$unwind` hoặc tạo field tính toán.
