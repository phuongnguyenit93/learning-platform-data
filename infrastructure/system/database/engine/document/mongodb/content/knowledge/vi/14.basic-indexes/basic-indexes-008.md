# Độ chọn lọc, phân bố giá trị và kích thước index trong MongoDB

Tạo index là một trong những cách quan trọng để tăng tốc truy vấn MongoDB. Tuy nhiên, **không phải cứ có index là truy vấn sẽ nhanh**, và **không phải index trên field có ít giá trị khác nhau đều vô ích**. Hiệu quả của index phụ thuộc vào dữ liệu thực tế: có bao nhiêu document khớp điều kiện, các giá trị xuất hiện đồng đều hay tập trung ở một vài giá trị, trường nào đứng trước trong compound index, truy vấn cần sắp xếp thế nào và bản thân index chiếm bao nhiêu bộ nhớ, dung lượng lưu trữ.

Bài học thuộc chương **Index cơ bản**, tập trung vào ba khái niệm liên quan chặt chẽ:

1. **Độ chọn lọc (selectivity)**: một điều kiện truy vấn thu hẹp tập document mạnh đến đâu.
2. **Phân bố giá trị (value distribution)**: tần suất các giá trị trong field có đồng đều hay bị lệch.
3. **Kích thước index (index size)**: dữ liệu và cấu trúc index chiếm tài nguyên ra sao, từ đó ảnh hưởng đến đọc, ghi và vận hành.

Mục tiêu là biết giải thích vì sao cùng một index có thể hiệu quả với truy vấn này nhưng không hiệu quả với truy vấn khác, đồng thời biết sử dụng `explain()`, thống kê collection và các mẫu truy vấn thực tế để ra quyết định thiết kế index.

## 1. Nhắc lại: index giải quyết vấn đề gì?

Trong một collection MongoDB, document không nhất thiết được lưu theo thứ tự giúp đáp ứng mọi truy vấn. Nếu cần tìm các đơn hàng có `customerId: "C001"`, MongoDB có thể phải xem nhiều document nếu không có index phù hợp.

Một index thông thường lưu các **index key** cùng thông tin tham chiếu đến document. Khi điều kiện có thể dùng thứ tự của index, MongoDB có thể tìm vào một vùng khóa rồi đọc những mục liên quan, thay vì xem mọi document trong collection.

```text
Collection orders:
  [doc 1] [doc 2] [doc 3] ... [doc 100000]
      \       |       /             |
       \      |      /              |
        +-----+-----+----------------+
              |
     Index theo customerId
      "C001" -> các document liên quan
      "C002" -> các document liên quan
      "C003" -> các document liên quan
         ...
```

Ví dụ tạo index:

```javascript
db.orders.createIndex(
  { customerId: 1 },
  { name: "idx_customerId" }
)
```

`1` biểu thị hướng tăng dần của trường trong index. MongoDB tự tạo index trên `_id` đối với collection thông thường; những index khác cần được thiết kế từ các truy vấn thực tế.

**Index không phải bản sao đầy đủ của collection.** Với các truy vấn cần nhiều field không có trong index, máy chủ vẫn có thể phải lấy document gốc (thường thể hiện bằng bước `FETCH` trong một số kế hoạch). Index hữu ích nếu phần chi phí tìm và lấy kết quả thấp hơn các phương án còn lại.

## 2. Độ chọn lọc: bao nhiêu document thỏa bộ lọc?

Giả sử collection `orders` có `N = 100.000` document.

- Điều kiện `{ customerId: "C001" }` khớp 4 document.
- Điều kiện `{ status: "delivered" }` khớp 90.000 document.
- Điều kiện `{ status: "cancelled" }` khớp 1.000 document.

Để mô tả trực quan, dùng **tỷ lệ khớp**:

\[
\text{matchRate}(q)
= \frac{\text{số document khớp điều kiện } q}
        {\text{tổng số document được xét}}.
\]

Đối với các ví dụ trên:

| Điều kiện | Số khớp / 100.000 | Tỷ lệ khớp | Mức thu hẹp tập kết quả |
| --- | ---: | ---: | --- |
| `customerId = "C001"` | 4 | 0,004% | Rất mạnh |
| `status = "cancelled"` | 1.000 | 1% | Khá mạnh |
| `status = "delivered"` | 90.000 | 90% | Rất yếu |

Theo cách nói thông dụng, truy vấn khớp **ít document** được gọi là **có tính chọn lọc cao**; truy vấn khớp phần lớn collection được gọi là **có tính chọn lọc thấp**.

Lưu ý thuật ngữ: một số tài liệu định nghĩa chỉ số *selectivity* bằng tỷ lệ loại trừ hoặc dùng tỷ lệ giá trị phân biệt, nên chiều lớn/nhỏ của con số có thể khác nhau. Trong bài này, ta luôn gọi con số `matched / total` là **tỷ lệ khớp**: **tỷ lệ khớp càng thấp, điều kiện càng chọn lọc**.

### 2.1. Vì sao độ chọn lọc ảnh hưởng đến index?

Với một điều kiện khớp rất ít document, index thường có cơ hội giúp MongoDB tránh đọc phần lớn collection:

```javascript
db.orders.find({ customerId: "C001" })
```

Nếu một giá trị xuất hiện trong gần như mọi document:

```javascript
db.orders.find({ status: "delivered" })
```

thì việc đi qua index rồi đọc hàng loạt document gốc có thể không hấp dẫn bằng một phương án quét collection, nhất là khi kết quả phải lấy nhiều field không có trong index. MongoDB query planner cân nhắc các kế hoạch khả thi; **không có quy tắc cố định** rằng tỷ lệ khớp 1% thì chắc chắn dùng index, còn 50% thì chắc chắn bỏ index.

Kế hoạch thực thi còn phụ thuộc vào projection, sort, giới hạn kết quả, index hiện có, thống kê và cách dữ liệu được lưu trên đĩa/bộ nhớ.

### 2.2. Selectivity là thuộc tính của điều kiện, không chỉ của field

Field `status` có thể có rất ít giá trị phân biệt, nhưng:

```javascript
db.orders.find({ status: "cancelled" })
```

có thể chọn lọc hơn nhiều so với:

```javascript
db.orders.find({ status: "delivered" })
```

Dù cả hai đều dùng cùng field và cùng index `{ status: 1 }`, số lượng document khớp khác nhau làm cho lợi ích của index khác nhau. Bởi vậy, không nên đánh giá index chỉ từ **tên field** hoặc số lượng giá trị có thể có theo lý thuyết.

## 3. Cardinality khác với selectivity như thế nào?

**Cardinality** của một field thường chỉ **số giá trị phân biệt** mà field có trong tập dữ liệu đang xét. Ví dụ:

- `status` chỉ có `"pending"`, `"delivered"`, `"cancelled"` → khoảng 3 giá trị phân biệt.
- `customerId` có hàng chục nghìn khách hàng khác nhau → cardinality cao hơn.
- `_id` là duy nhất → mỗi document có một khóa riêng trong phạm vi collection.

Cardinality cao **thường tạo cơ hội** cho equality lookup chọn lọc, nhưng không đồng nghĩa mọi giá trị có tần suất ngang nhau.

| Field | Cardinality minh họa | Điều cần xem thêm |
| --- | --- | --- |
| `isActive` | 2 | `true` có chiếm 99,9% không? |
| `status` | 3–10 | Mỗi trạng thái có bao nhiêu document? |
| `region` | Vài chục | Có một vùng chiếm đa số bản ghi không? |
| `customerId` | Hàng nghìn/hàng triệu | Có khách hàng rất lớn tạo phần lớn đơn không? |
| `_id` | Gần bằng số document | Truy vấn có thực sự lọc theo `_id` không? |

### 3.1. Ví dụ về sự phân bố đồng đều và lệch

Hai collection đều có field `status` với ba giá trị, nhưng phân bố khác nhau:

```text
Collection A (khá đồng đều):
  pending     33%
  delivered   34%
  cancelled   33%

Collection B (lệch mạnh):
  pending      8%
  delivered   90%
  cancelled    2%
```

Cả hai có cùng **cardinality = 3**, nhưng đối với collection B, truy vấn `status: "cancelled"` chỉ cần khoảng 2% document còn `status: "delivered"` cần khoảng 90%.

Vì vậy:

> Cardinality mô tả có bao nhiêu giá trị khác nhau; phân bố mô tả mỗi giá trị xuất hiện bao nhiêu lần; selectivity mô tả một điều kiện cụ thể thu hẹp kết quả đến mức nào.

### 3.2. Một field có cardinality cao vẫn có thể phân bố lệch

Một hệ thống thương mại điện tử có thể có một “khách hàng hệ thống” phát sinh 300.000 đơn hàng, còn hàng nghìn khách hàng khác chỉ có vài đơn. `customerId` vẫn có cardinality cao, nhưng truy vấn bằng ID của khách hàng hệ thống không hề chọn lọc như truy vấn bằng ID của một khách hàng bình thường.

Thiết kế index nên dựa trên **workload** và **tần suất giá trị thực tế**, không chỉ dựa vào cấu trúc schema hoặc một con số distinct value.

## 4. Thực hành: tạo tập dữ liệu lệch phân bố

Mở `mongosh` và chọn database riêng:

```javascript
use mongo_index_lab
```

Ví dụ sau tạo 100 đơn hàng có phân bố `status` bị lệch. Chạy trên collection `orders` mới hoặc trống:

```javascript
const sampleOrders = Array.from({ length: 100 }, (_, i) => ({
  _id: i + 1,
  customerId: "C" + String((i % 50) + 1).padStart(3, "0"),
  status: i < 90
    ? "delivered"
    : (i < 98 ? "pending" : "cancelled"),
  createdAt: new Date(Date.UTC(2026, 0, 1) + i * 60000),
  amount: 100 + (i % 10) * 10,
  tags: i % 3 === 0 ? ["mobile", "sale"] : ["web"]
}));

db.orders.insertMany(sampleOrders);
```

Kết quả theo cách xây mẫu:

| Giá trị `status` | Số document | Tỷ lệ |
| --- | ---: | ---: |
| `delivered` | 90 | 90% |
| `pending` | 8 | 8% |
| `cancelled` | 2 | 2% |
| **Tổng** | **100** | **100%** |

Mỗi `customerId` từ `C001` đến `C050` có hai đơn hàng, nên điều kiện equality trên một khách hàng khớp 2/100 document trong bộ dữ liệu này.

Các `_id` cố định chỉ để minh họa; nếu chạy `insertMany()` nhiều lần trên cùng collection, lệnh gặp lỗi duplicate key. Không dùng `drop()` trên collection chứa dữ liệu sản xuất để chạy lại bài.

### 4.1. Đếm tần suất theo giá trị bằng aggregation

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

Kết quả gồm ba nhóm với số lượng 90, 8 và 2. Đây là cách xem phân bố của giá trị thay vì chỉ nhìn tên field.

Kiểm tra một điều kiện cụ thể:

```javascript
const total = db.orders.countDocuments({});
const cancelled = db.orders.countDocuments({ status: "cancelled" });
const byCustomer = db.orders.countDocuments({ customerId: "C001" });

printjson({
  total,
  cancelled,
  cancelledMatchRate: cancelled / total,
  byCustomer,
  customerMatchRate: byCustomer / total
});
```

Trên dữ liệu mẫu: `cancelledMatchRate = 0.02`, `customerMatchRate = 0.02`. Với dữ liệu thật, phép đếm chính xác có thể tốn tài nguyên, đặc biệt ở collection lớn; không tự chạy nhiều phép đếm nặng liên tục trên hệ thống đang chịu tải.

### 4.2. Tìm các giá trị có tần suất lớn nhất

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$customerId",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } },
  { $limit: 10 }
])
```

Trong bộ dữ liệu mẫu, mỗi khách hàng có đúng hai đơn; thực tế, phép tổng hợp này giúp phát hiện khách hàng hoặc nhóm dữ liệu **chiếm tỷ trọng lớn bất thường**. Phân bố dữ liệu theo thời gian cũng cần được xem lại: các chiến dịch, đợt nhập dữ liệu, mùa vụ hoặc thay đổi nghiệp vụ có thể làm phân bố khác trước.

## 5. So sánh truy vấn chọn lọc cao và thấp

Tạo index đơn trên `status`:

```javascript
db.orders.createIndex(
  { status: 1 },
  { name: "idx_status" }
)
```

Sau đó xem hai điều kiện:

```javascript
// Khớp 2/100 document
db.orders.find({ status: "cancelled" })

// Khớp 90/100 document
db.orders.find({ status: "delivered" })
```

Truy vấn đầu có **tỷ lệ khớp thấp hơn** và thường có cơ hội tận dụng index để giảm phạm vi cần xem. Truy vấn thứ hai trả phần lớn collection nên dù index tồn tại, query planner có thể thấy quét collection là hợp lý hơn trong một số tình huống.

Tuy nhiên, với chỉ 100 document, toàn bộ dữ liệu có thể nằm gọn trong cache, nên tốc độ hoặc kế hoạch có thể không thể hiện rõ chênh lệch. **Đừng suy từ một thử nghiệm nhỏ rằng index chắc chắn thắng hoặc thua ở production.**

### Projection cũng ảnh hưởng đến chi phí

So sánh:

```javascript
// Cần cả document, có thể phải đọc nhiều document gốc
db.orders.find({ status: "delivered" })

// Chỉ cần một số field
db.orders.find(
  { status: "delivered" },
  { _id: 0, status: 1 }
)
```

Nếu mọi field cần lọc/trả về đều có trong index và điều kiện khác cho phép, truy vấn có thể được **covered** bởi index, tránh bước đọc document gốc. Vì vậy một điều kiện khớp nhiều document vẫn có thể hưởng lợi khi index đáp ứng phần lớn công việc và truy vấn chỉ lấy những field có sẵn trong khóa.

Đây là một lý do để không kết luận hiệu quả index từ selectivity riêng lẻ.

## 6. Compound index: ghép điều kiện để tăng hiệu quả

Một field ít giá trị phân biệt đôi khi hữu ích khi nằm trong **compound index** cùng field khác.

Ví dụ màn hình hiển thị “các đơn `pending` của khách hàng C001, mới nhất trước”:

```javascript
db.orders.find({
  customerId: "C001",
  status: "pending"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

Có thể thiết kế index:

```javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_customer_status_created_id" }
)
```

Hình dung đường đi:

```text
customerId = C001
        |
        v
status = pending
        |
        v
createdAt giảm dần, _id giảm dần
        |
        v
Lấy tối đa 20 document đầu tiên
```

Khi điều kiện equality thu hẹp được phần đầu index và thứ tự các khóa sau phù hợp với `sort`, MongoDB có thể vừa lọc vừa đọc kết quả theo thứ tự mong muốn. Điều này đôi khi hữu ích hơn chỉ tạo `{status: 1}` hoặc `{createdAt: -1}` riêng lẻ.

### 6.1. Thứ tự field trong compound index có ý nghĩa

Hai index:

```javascript
{ customerId: 1, status: 1, createdAt: -1 }
{ createdAt: -1, customerId: 1, status: 1 }
```

không tương đương về khả năng hỗ trợ những hình dạng truy vấn khác nhau. Với equality `customerId` và `status`, index đầu tổ chức các đơn theo các khóa đó trước, rồi mới theo thời gian. Index thứ hai sắp theo thời gian ở mức rộng trước và có thể phải đi qua nhiều mục để chọn đúng khách hàng.

Một nguyên tắc thiết kế thường dùng là **Equality – Sort – Range (ESR)**:

1. Xem các field có điều kiện equality.
2. Xem các field phục vụ `sort`.
3. Xem các field dùng điều kiện range như `$gt`, `$gte`, `$lt`, `$lte`.

Đây là **hướng dẫn thiết kế**, không phải quy tắc bất biến. Trong một số workload, range rất chọn lọc có thể đáng ưu tiên; khả năng sử dụng index cho sort phụ thuộc thứ tự khóa và điều kiện trước nó. Hãy đo bằng truy vấn thực tế.

### 6.2. Không nhân tỷ lệ khớp một cách máy móc

Giả sử:

- `status: "pending"` khớp 8%.
- `customerId: "C001"` khớp 2%.

Không thể luôn kết luận điều kiện kết hợp khớp `8% * 2% = 0,16%`. Phép nhân đó ngầm giả định hai field độc lập, điều có thể không đúng. Một khách hàng có thể chỉ có đơn pending hoặc không có đơn pending nào.

Khi thiết kế index, cần xem **phân bố kết hợp (joint distribution)** của các field: truy vấn thực tế đang lọc giao của những nhóm nào, số document khớp là bao nhiêu và chúng phân bố ra sao theo thời gian.

### 6.3. Phần tiền tố của compound index

Index:

```javascript
{ customerId: 1, status: 1, createdAt: -1 }
```

thường có thể hỗ trợ điều kiện trên **tiền tố** `customerId`, hoặc `customerId` cùng `status`. Nó không tương đương một index chỉ trên `status` cho mọi truy vấn:

```javascript
db.orders.find({ status: "pending" })
```

không có equality trên field đầu `customerId`. MongoDB vẫn có thể dùng một số cách quét index trong điều kiện cụ thể, nhưng không nên dựa vào index trên chỉ để phục vụ tốt mọi truy vấn `status` đứng riêng.

## 7. Phân bố dữ liệu ảnh hưởng đến query planner như thế nào?

MongoDB query planner chọn giữa những kế hoạch khả thi dựa trên truy vấn và các index hiện có. Cùng một query shape nhưng với giá trị tham số khác nhau, lượng dữ liệu khớp có thể khác lớn:

```javascript
db.orders.find({ status: "delivered" })
db.orders.find({ status: "cancelled" })
```

Trong các hệ thống dùng plan cache, việc tái sử dụng kế hoạch giữa những lần chạy tương tự có thể làm hiệu năng phụ thuộc vào phân bố giá trị và tình trạng dữ liệu. Không nên khẳng định một kế hoạch duy nhất tối ưu cho mọi tham số.

Tác động của phân bố còn thấy rõ với:

- **Range query**: `amount: {$gte: 100}` có thể khớp phần lớn đơn, còn `amount: {$gte: 100000}` rất hiếm.
- **Điều kiện thời gian**: “7 ngày gần đây” có thể chứa nhiều hoặc ít document tùy nhịp ghi.
- **Phân bố có nhiều `null` hoặc missing**: field tùy chọn chỉ xuất hiện ở một phần collection.
- **Dữ liệu đa tenant**: một tenant lớn có thể chiếm phần lớn document, trong khi các tenant khác rất nhỏ.
- **Mảng đa trị**: một document chứa nhiều giá trị index, làm thay đổi số index keys và chi phí quét.

Khi workload có sự lệch mạnh, hãy thử **giá trị phổ biến**, **giá trị hiếm** và **giá trị ở giữa**, thay vì chỉ chạy `explain()` trên một ID ngẫu nhiên.

## 8. Quan sát index bằng `explain("executionStats")`

Một cách thực tế để đánh giá hiệu quả của index là so sánh kế hoạch và thống kê thực thi của các query cụ thể:

```javascript
db.orders.find({ status: "cancelled" })
  .explain("executionStats")

db.orders.find({ status: "delivered" })
  .explain("executionStats")
```

Với compound index:

```javascript
db.orders.find({
  customerId: "C001",
  status: "pending"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Các chỉ số nên chú ý:

| Thuộc tính | Ý nghĩa khi diễn giải |
| --- | --- |
| `nReturned` | Số document thực sự được trả trong truy vấn được giải thích |
| `totalKeysExamined` | Số mục khóa index được xem xét trong quá trình thực thi |
| `totalDocsExamined` | Số document được xem xét ở các bước cần đọc document |
| `executionTimeMillis` | Thời gian thực thi được báo cáo trong môi trường đo |
| `winningPlan` | Kế hoạch được chọn để thực thi truy vấn |
| `IXSCAN` | Một bước quét index trong dạng kế hoạch tương ứng |
| `COLLSCAN` | Một bước quét collection |
| `FETCH` | Một bước lấy document gốc |
| `SORT` | Có công đoạn sắp xếp trong kế hoạch tương ứng |
| `indexBounds` | Các khoảng giá trị khóa index được dùng khi áp dụng |

Tên stage và cách lồng các trường có thể thay đổi theo phiên bản và bộ máy thực thi MongoDB. Đặc biệt, không nên mong mọi kế hoạch đều hiển thị đúng một cấu trúc stage cố định.

### 8.1. Thế nào là dấu hiệu index lọc hiệu quả?

Ví dụ truy vấn trả 10 document:

```text
Trường hợp A:
  nReturned          = 10
  totalKeysExamined  = 12
  totalDocsExamined  = 10

Trường hợp B:
  nReturned          = 10
  totalKeysExamined  = 100000
  totalDocsExamined  = 10000
```

Trong ví dụ giả định này, trường hợp A đi qua ít mục hơn rõ rệt. Trường hợp B có thể đang quét một vùng khóa rộng, dùng index không phù hợp hoặc phải kiểm tra điều kiện còn lại trên nhiều document.

Tuy nhiên, **không có một ngưỡng `keysExamined / nReturned` duy nhất đúng cho mọi query**. Ví dụ:

- Query `limit(10)` có thể ngừng sớm sau 10 kết quả, che khuất chi phí của toàn bộ tập kết quả.
- Multikey index có thể có nhiều key cho một document.
- Query có aggregation, sort hoặc phân trang sâu có thể cần đi qua nhiều mục vì lý do hợp lệ.
- Covered query có thể có `totalDocsExamined = 0` nhưng vẫn cần duyệt các index keys.

Hãy so sánh các chỉ số với **mục tiêu của truy vấn**, kích thước collection và các phương án khác, không đánh giá một trường riêng lẻ.

### 8.2. Có thể thử `hint()` để quan sát một index

Ví dụ:

```javascript
db.orders.find({ status: "cancelled" })
  .hint("idx_status")
  .explain("executionStats")
```

`hint()` yêu cầu MongoDB sử dụng index được chỉ định khi phù hợp, thay vì để query planner chọn bình thường. Cách này hữu ích khi **nghiên cứu** kế hoạch của index, nhưng số liệu sau `hint` không chứng minh đó là kế hoạch tối ưu cho workload.

Không mặc định ép `hint` trong mã ứng dụng sản xuất nếu chưa có lý do và phép đo cụ thể; index có thể bị xóa hoặc thay đổi, phân bố dữ liệu có thể đổi, và hint cố định có thể trở nên kém hiệu quả về sau.

## 9. Kích thước index gồm những gì?

Index cần lưu **khóa**, **cấu trúc tổ chức khóa** và thông tin liên kết đến document. Đối với index thông thường, MongoDB dùng cấu trúc sắp xếp thích hợp để tìm kiếm theo khóa và hỗ trợ những mẫu filter/sort nhất định.

Kích thước thực tế của index chịu ảnh hưởng bởi:

1. **Số lượng document và số lượng index entries**: càng nhiều mục cần lập chỉ mục, index thường càng lớn.
2. **Kiểu và độ dài của khóa**: chuỗi dài có thể cần nhiều byte hơn giá trị số ngắn; đặc điểm mã hóa BSON ảnh hưởng cách lưu.
3. **Số field trong compound index**: mỗi key phải biểu diễn nhiều thành phần hơn, dù việc nén có thể giảm chi phí thực.
4. **Mảng được index (multikey)**: một document có thể tạo nhiều index entries.
5. **Loại index**: B-tree thông thường, text, wildcard, hashed, geospatial và các loại khác có chi phí lưu trữ khác nhau.
6. **Collation**: index hỗ trợ so sánh theo ngôn ngữ có thể có representation khóa khác so với simple binary collation.
7. **Nén và cấu trúc lưu trữ**: trên WiredTiger, cách nén, prefix compression, trang dữ liệu và các overhead ảnh hưởng kích thước đo được.
8. **Biến động ghi/xóa/cập nhật và phân mảnh lưu trữ**: kích thước quan sát được không chỉ là tổng độ dài các giá trị hiện tại.

Vì những lý do này, không thể tính chính xác `indexSize = số document × kích thước một khóa` bằng phép nhân đơn giản. Công thức đó bỏ qua overhead, mã hóa, nén, multikey và cách phân bổ trang lưu trữ.

### 9.1. Index lớn ảnh hưởng điều gì?

| Tài nguyên | Ảnh hưởng có thể xảy ra |
| --- | --- |
| Dung lượng lưu trữ | Index chiếm thêm chỗ ngoài dữ liệu collection |
| Bộ nhớ cache | Những phần index thường truy cập cần cạnh tranh chỗ trong cache với dữ liệu và index khác |
| Đọc | Index phù hợp giúp giảm số mục cần tìm; index quá lớn hoặc không phù hợp có thể làm tăng I/O/cache miss |
| Ghi | Insert/update/delete có thể phải duy trì những index bị ảnh hưởng |
| Tạo index | Quá trình xây dựng index tốn thời gian và tài nguyên, cần cân nhắc tải hệ thống |
| Sao lưu/khôi phục, triển khai | Tổng lượng dữ liệu và cấu trúc index ảnh hưởng vận hành tùy cơ chế sao lưu/khôi phục |

**Index chiếm chỗ trên đĩa không có nghĩa toàn bộ index bắt buộc nằm trong RAM.** MongoDB/WiredTiger sử dụng cơ chế cache cho các trang được truy cập; điều quan trọng là kích thước và mô hình truy cập của **working set** (tập dữ liệu và trang index được dùng thường xuyên) so với bộ nhớ/cache sẵn có.

## 10. Đo kích thước index và collection

Trong `mongosh`, có thể dùng:

```javascript
db.orders.stats()
```

Kết quả có các trường liên quan như `count`, `size`, `storageSize`, `totalIndexSize`, `indexSizes` và `nindexes` trên những phiên bản hỗ trợ. Tên và cách biểu diễn có thể khác theo phiên bản, nhưng ý nghĩa chính là:

| Trường | Thông tin |
| --- | --- |
| `count` | Số document trong collection tại thời điểm thống kê |
| `size` | Kích thước logic dữ liệu theo thống kê collection |
| `storageSize` | Dung lượng lưu trữ được cấp phát cho dữ liệu collection |
| `nindexes` | Số index của collection |
| `totalIndexSize` | Tổng kích thước lưu trữ của các index theo thống kê |
| `indexSizes` | Kích thước theo từng tên index |

Ví dụ đọc một số trường mà không in toàn bộ metadata:

```javascript
const s = db.orders.stats();
printjson({
  count: s.count,
  dataSizeBytes: s.size,
  dataStorageBytes: s.storageSize,
  totalIndexBytes: s.totalIndexSize,
  indexes: s.indexSizes
});
```

Không nên xem `size`, `storageSize` và `totalIndexSize` là ba đại lượng giống nhau. Dữ liệu logic, dung lượng cấp phát cho dữ liệu và dung lượng index phản ánh các lớp khác nhau.

### 10.1. Đọc dung lượng theo MiB

```javascript
const stat = db.orders.stats();
const toMiB = bytes => bytes / (1024 * 1024);

print("Dữ liệu logic: " +
  toMiB(stat.size).toFixed(2) + " MiB");
print("Lưu trữ dữ liệu: " +
  toMiB(stat.storageSize).toFixed(2) + " MiB");
print("Tổng index: " +
  toMiB(stat.totalIndexSize).toFixed(2) + " MiB");
```

Đây là cách **đổi đơn vị từ byte** để hiển thị. Chỉ số có thể thay đổi sau các thao tác ghi, xóa hoặc xây dựng index. Trong collection thực hành 100 document, kích thước rất nhỏ, không đại diện cho chi phí ở hàng triệu document.

### 10.2. Xem các index hiện có

```javascript
db.orders.getIndexes()
```

`getIndexes()` mô tả cấu hình index như tên, key pattern, `unique`, `partialFilterExpression` hoặc `hidden` khi có; nó không thay thế trực tiếp cho `indexSizes` trong collection stats.

Các phương thức thống kê có thể yêu cầu quyền truy cập phù hợp; không chạy thao tác sửa/xóa index để “xem thử” trên database đang vận hành.

### 10.3. `$indexStats` là thống kê sử dụng, không phải kích thước

```javascript
db.orders.aggregate([
  { $indexStats: {} }
])
```

Stage `$indexStats` cung cấp thông tin về lượt sử dụng index trên node tương ứng, thường gồm tên index và các bộ đếm `accesses`. Dữ liệu sử dụng này phục vụ đánh giá index nào được truy vấn đến; **nó không phải số byte index** và không thay thế `indexSizes`.

Các bộ đếm sử dụng có phạm vi và chu kỳ theo node/process hoặc từ khi index được tạo lại theo triển khai; số thấp không tự chứng minh index thừa, nhất là khi index phục vụ workload hiếm nhưng quan trọng, ràng buộc unique hoặc công việc định kỳ.

## 11. Multikey index và ảnh hưởng của mảng đến kích thước

Giả sử mỗi sản phẩm có nhiều nhãn:

```javascript
{
  _id: "p01",
  tags: ["mongodb", "database", "backend"]
}
```

Tạo index:

```javascript
db.products.createIndex(
  { tags: 1 },
  { name: "idx_tags" }
)
```

Vì `tags` là array, index này có thể trở thành **multikey index**: một document với nhiều phần tử có thể đóng góp nhiều index key entries thay vì chỉ một.

```text
Document p01:
  tags = ["mongodb", "database", "backend"]

Index theo tags (minh họa ý nghĩa khóa):
  "backend"  -> p01
  "database" -> p01
  "mongodb"  -> p01
```

Nếu mỗi document có mảng dài hàng trăm phần tử, số mục index có thể tăng đáng kể. Kích thước index có thể lớn hơn nhiều so với index trên một field scalar ngắn ở cùng số lượng document.

**Không suy ra chính xác** một document có mảng N phần tử sẽ luôn tạo đúng N mục index: sự trùng lặp giá trị, cách mã hóa và quy tắc xây index ảnh hưởng số khóa cuối cùng. Với compound multikey còn có các hạn chế riêng; không phải cứ ghép nhiều field array vào một compound index là hợp lệ.

Ví dụ truy vấn:

```javascript
db.products.find({ tags: "mongodb" })
```

Index theo `tags` có thể giúp tìm sản phẩm chứa phần tử tương ứng. Nhưng khi xem `totalKeysExamined`, cần nhớ số index entries có thể lớn hơn số document khớp vì multikey.

### Dấu chấm trong đường dẫn nested field

Index cũng có thể nằm trên field lồng nhau:

```javascript
db.products.createIndex(
  { "seller.country": 1 },
  { name: "idx_seller_country" }
)
```

Selectivity vẫn tính theo **điều kiện thực tế**: `country: "VN"` có thể phổ biến, còn một quốc gia rất ít seller có thể hiếm. Việc field nằm sâu trong object không tự làm index chọn lọc hơn.

## 12. Kích thước compound index và lợi ích của covered query

Một compound index chứa nhiều thành phần trong khóa nên có thể tốn thêm dung lượng:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1, status: 1 },
  { name: "idx_customer_date_status" }
)
```

Đổi lại, index này có thể hỗ trợ cả lọc, sort và projection trong những trường hợp phù hợp:

```javascript
db.orders.find(
  { customerId: "C001" },
  {
    _id: 0,
    customerId: 1,
    createdAt: 1,
    status: 1
  }
)
  .sort({ createdAt: -1 })
```

Khi mọi field cần lọc, sắp xếp và trả về đều nằm trong index, truy vấn có thể được thực thi theo kiểu **covered query**, tránh lấy document gốc. Trong một số kế hoạch, `totalDocsExamined` có thể bằng 0.

Nhưng index `{customerId:1,createdAt:-1,status:1}` không tự covered được truy vấn cần thêm `amount` nếu `amount` không có trong index:

```javascript
db.orders.find(
  { customerId: "C001" },
  { _id: 0, customerId: 1, createdAt: 1, amount: 1 }
)
  .sort({ createdAt: -1 })
```

MongoDB có thể phải đọc document gốc để lấy `amount`. Việc thêm `amount` vào compound index **có thể** giảm đọc document cho query này, nhưng cũng làm index lớn hơn và tăng chi phí duy trì. Không nên nhồi mọi field hiển thị vào index chỉ để đạt covered query trên một màn hình ít truy cập.

### Chú ý projection `_id`

MongoDB thường trả `_id` nếu không yêu cầu loại trừ. Nếu `_id` không nằm trong index đang dùng, việc trả field này có thể khiến truy vấn không còn covered. Trong ví dụ trên, `_id: 0` là lựa chọn chủ đích.

Covered query cũng có các hạn chế theo loại index, multikey, collation và cú pháp bộ lọc. Hãy xác nhận bằng `explain()` thay vì chỉ suy từ danh sách field.

## 13. Giảm kích thước index bằng cách chọn đúng phạm vi

Không phải mọi document đều cần xuất hiện trong mọi index. Trong phạm vi được MongoDB hỗ trợ, **partial index** chỉ lập chỉ mục các document khớp một điều kiện xác định.

Ví dụ hệ thống thường truy vấn các đơn `pending` theo khách hàng và thời gian; trong khi phần lớn đơn đã `delivered`:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    name: "idx_pending_customer_createdAt",
    partialFilterExpression: {
      status: "pending"
    }
  }
)
```

Index này chứa khóa cho những document thỏa `status: "pending"`, thay vì toàn bộ các document trong collection. Trên dữ liệu mẫu, đó là 8/100 document.

Truy vấn phù hợp:

```javascript
db.orders.find({
  customerId: "C041",
  status: "pending"
})
  .sort({ createdAt: -1 })
```

Vì filter truy vấn **bao hàm điều kiện partial** `status: "pending"`, index có thể là ứng viên phục vụ truy vấn này.

Ngược lại:

```javascript
db.orders.find({ customerId: "C041" })
```

không thể tùy tiện dùng partial index nói trên để coi như lấy đủ mọi đơn của C041, vì index thiếu các document `delivered` và `cancelled`. Query planner phải giữ tính đúng đắn của kết quả.

### Khi nào partial index đáng cân nhắc?

- Truy vấn chủ yếu tập trung vào một **tập con nhỏ**, ổn định theo điều kiện nghiệp vụ.
- Điều kiện truy vấn thường xuyên **nêu rõ hoặc hàm ý đủ mạnh** điều kiện của partial index.
- Việc giảm index entries giúp tiết kiệm dung lượng và chi phí duy trì so với index đầy đủ.

Tuy nhiên, nếu status thay đổi liên tục từ `pending` sang `delivered`, hệ thống vẫn phải cập nhật index khi document đi vào hoặc đi ra khỏi tập được lập chỉ mục. Partial index không có nghĩa “không tốn chi phí ghi”.

Index sparse cũng có thể loại bỏ một số document thiếu field được index, nhưng ngữ nghĩa của sparse và partial khác nhau. Không nên thay thế tùy tiện `sparse: true` cho partial filter khi nghiệp vụ muốn loại một trạng thái cụ thể.

## 14. Đánh đổi giữa hiệu năng đọc, chi phí ghi và dung lượng

Một index rất hữu ích cho một truy vấn hiếm gặp vẫn có chi phí trong quá trình vận hành.

Khi chèn document:

```javascript
db.orders.insertOne({
  _id: 201,
  customerId: "C201",
  status: "pending",
  createdAt: new Date(),
  amount: 250
})
```

MongoDB phải duy trì các index liên quan đến document mới. Khi cập nhật field được index, ví dụ đổi `status`, có thể cần thay đổi các mục index tương ứng. Khi xóa document, mục index của document cũng cần được xử lý.

Vì vậy, tạo 10 index có thể cải thiện nhiều truy vấn đọc nhưng làm tăng tổng index size và công việc ghi so với 2–3 index phù hợp nhất. Đây là sự **đánh đổi**, không phải lời khuyên cố định về số index tối đa.

### Tình huống ra quyết định

Giả sử một collection có 5 triệu đơn, `status` phân bố:

```text
delivered: 4.700.000
pending:     250.000
cancelled:    50.000
```

Các workload chính:

1. Hầu hết request cần đơn của một `customerId` cụ thể, mới nhất trước.
2. Dashboard quản trị cần xem các đơn `pending` theo thời gian.
3. Báo cáo tháng đọc hàng triệu đơn `delivered`.

Một cách tiếp cận là:

- Ưu tiên compound index bắt đầu bằng `customerId`, theo sau là trường thời gian/sort, cho truy vấn số 1.
- Cân nhắc index theo `status` và `createdAt`, hoặc partial index trên `pending`, cho truy vấn số 2.
- Không mặc định bổ sung index đơn `{status:1}` chỉ vì báo cáo số 3 có filter theo `delivered`; báo cáo có thể cần quét nhiều document bất kể index. Cần quan sát kế hoạch thực tế và cân nhắc phương pháp xử lý báo cáo phù hợp.

Lựa chọn tốt nhất phụ thuộc tần suất truy vấn, độ trễ mục tiêu, dung lượng, tốc độ ghi và tài nguyên máy. Một index hỗ trợ sort tốt có thể đáng giá dù độ chọn lọc của filter không cao, đặc biệt khi query có `limit` nhỏ.

## 15. Quy trình đánh giá trước khi thêm index

Một quy trình cơ bản, có thể lặp lại và đưa vào tài liệu vận hành:

**Bước 1 — Ghi lại query shape.**

```javascript
db.orders.find({
  customerId: "C001",
  status: "pending"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

Ghi đầy đủ filter, sort, limit, projection và giá trị tham số điển hình. Index thiết kế cho một query thiếu `sort` có thể không phục vụ đúng truy vấn thực.

**Bước 2 — Quan sát phân bố và mức khớp.**

Dùng số liệu phù hợp trên tập dữ liệu đại diện; kiểm tra giá trị phổ biến và hiếm, các tenant lớn/nhỏ, thời điểm cao điểm và dữ liệu `null`/missing.

**Bước 3 — Kiểm tra index hiện có.**

```javascript
db.orders.getIndexes()
```

Tránh tạo index gần trùng với một compound index đã phục vụ tốt workload nếu nó không mang lại lợi ích đáng kể.

**Bước 4 — Đo baseline.**

```javascript
db.orders.find({
  customerId: "C001",
  status: "pending"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Quan sát `totalKeysExamined`, `totalDocsExamined`, plan và thời gian. Ghi bối cảnh dữ liệu/phiên bản để các lần đo sau có thể so sánh.

**Bước 5 — Chọn index hợp lý.**

Cân nhắc vị trí field equality, sort, range, khả năng index prefix, tính chọn lọc và nhu cầu covered query. Đánh giá index đơn, compound hoặc partial tùy workload.

**Bước 6 — Đo sau thay đổi trên môi trường phù hợp.**

Chạy lại query với một số giá trị phổ biến/hiếm, quan sát plan và ảnh hưởng ghi. Không vội triển khai nhiều index chỉ từ kết quả của bộ dữ liệu rất nhỏ.

**Bước 7 — Theo dõi dung lượng và sử dụng.**

```javascript
const stats = db.orders.stats();
printjson(stats.indexSizes);

db.orders.aggregate([
  { $indexStats: {} }
]);
```

Kết hợp dữ liệu này với monitoring về bộ nhớ, cache, throughput, latency và đặc điểm ghi. `$indexStats` có giới hạn về phạm vi đo, vì vậy không nên xóa một index chỉ do thấy số lượt truy cập thấp trong một khoảng ngắn.

**Bước 8 — Rà soát khi workload thay đổi.**

Phân bố không bất biến: thêm khách hàng lớn, trạng thái mới hoặc một màn hình tìm kiếm mới có thể thay đổi thứ tự ưu tiên index. Theo dõi theo giai đoạn, không coi index là cấu hình “tạo một lần rồi quên”.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Field có 2 giá trị thì index luôn vô ích” | Một giá trị có thể rất hiếm; index còn có thể phục vụ sort/partial query | Xem phân bố từng giá trị và query shape |
| “Cardinality cao đồng nghĩa mọi equality đều nhanh” | Một giá trị có thể xuất hiện rất nhiều do phân bố lệch | Xem tần suất cụ thể của giá trị truy vấn |
| “90% document khớp mà index chắc chắn luôn chậm hơn” | Covered query, sort và limit có thể thay đổi chi phí | Quan sát kế hoạch và thống kê thực thi |
| “Index làm truy vấn nhanh mà không có đánh đổi” | Index chiếm dung lượng và cần được duy trì khi ghi | Đánh giá cả read, write và storage |
| “`indexSize = N × kích thước key` chính xác” | Bỏ qua nén, overhead, multikey và bố trí trang | Đo qua `stats()`, không dự đoán từ phép nhân đơn giản |
| “Index `{a:1,b:1}` phục vụ tốt mọi truy vấn theo `b`” | `b` không phải tiền tố của index | Xem quy tắc prefix và query shape |
| “Số khóa index bằng số document” | Multikey array có thể sinh nhiều khóa | Xem `totalKeysExamined` và đặc tính index |
| “Có index thì luôn được chọn” | Query planner có thể chọn COLLSCAN hoặc kế hoạch khác | Đọc `winningPlan` thực tế |
| “Thêm thật nhiều field để luôn covered” | Index lớn hơn, chi phí ghi tăng, chỉ lợi cho một số query | Chọn field dựa trên workload có giá trị |
| “Partial index có thể dùng cho bất kỳ truy vấn nào” | Index chỉ chứa document thỏa điều kiện partial | Query phải bảo đảm không bỏ sót kết quả |
| “`$indexStats` là kích thước index” | Đây chủ yếu là thống kê truy cập | Dùng `indexSizes`/`totalIndexSize` để đo storage |
| “Index phải nằm toàn bộ trong RAM” | Engine dùng cache theo trang/working set | Theo dõi truy cập thực tế, không chỉ tổng dung lượng |
| “Dữ liệu test 100 document chứng minh được lợi ích production” | Tập nhỏ và cache khác rất xa dữ liệu thật | Đo trên tập đại diện và nhiều loại tham số |

## 17. Bài tập thực hành

### Bài 1. Tính tỷ lệ khớp và nhận xét selectivity

Collection có 200.000 document:

- `status: "complete"` khớp 170.000 document.
- `status: "failed"` khớp 2.000 document.
- `customerId: "C017"` khớp 5 document.

Hãy tính tỷ lệ khớp của ba điều kiện và xếp thứ tự từ chọn lọc cao đến thấp.

**Đáp án:**

| Điều kiện | Tỷ lệ khớp | Mức chọn lọc |
| --- | --- | --- |
| `customerId = "C017"` | 5/200.000 = 0,0025% | Cao nhất |
| `status = "failed"` | 2.000/200.000 = 1% | Cao |
| `status = "complete"` | 170.000/200.000 = 85% | Thấp |

Đây là đánh giá phạm vi kết quả, **không phải** bảo đảm planner sẽ chọn index nào trong mọi query.

### Bài 2. Cardinality và phân bố

Hai collection đều có field `isActive` với hai giá trị `true` và `false`:

- Collection A: `true = 50%`, `false = 50%`.
- Collection B: `true = 99,9%`, `false = 0,1%`.

Hỏi cardinality có khác không? Truy vấn `isActive: false` khác nhau như thế nào về mức chọn lọc?

**Đáp án:** Cardinality của cả hai đều là 2. Nhưng `isActive: false` khớp 50% ở A, chỉ 0,1% ở B; vì vậy điều kiện này chọn lọc hơn nhiều ở B. Việc có dùng index hay không còn tùy query shape và chi phí thực thi.

### Bài 3. Chọn index cho truy vấn kết hợp

Ứng dụng thường truy vấn:

```javascript
db.orders.find({
  customerId: "C008",
  status: "pending"
})
  .sort({ createdAt: -1 })
  .limit(10)
```

Hãy đề xuất một compound index.

**Đáp án tham khảo:**

```javascript
db.orders.createIndex(
  { customerId: 1, status: 1, createdAt: -1 },
  { name: "idx_customer_status_created" }
)
```

Hai field equality đứng trước; `createdAt` hỗ trợ thứ tự thời gian trong nhóm đã lọc. Cần dùng `explain()` trên dữ liệu thực tế để xác nhận hiệu quả; nếu cần thứ tự hoàn toàn xác định khi nhiều document trùng `createdAt`, bổ sung `_id` vào sort và cân nhắc index tương ứng.

### Bài 4. Phân biệt dữ liệu và index size

Thống kê một collection cho thấy:

```text
size           = 800 MiB
storageSize    = 500 MiB
totalIndexSize = 320 MiB
```

Hỏi có thể kết luận điều gì và không nên kết luận điều gì?

**Đáp án:** `size` phản ánh kích thước logic dữ liệu, `storageSize` phản ánh phần lưu trữ dữ liệu được cấp phát/báo cáo, còn `totalIndexSize` phản ánh dung lượng index được báo cáo. Không cộng ba số để coi đó là ba bản sao độc lập của cùng dữ liệu; cũng không suy rằng đúng 320 MiB index luôn phải nằm trong RAM.

### Bài 5. Mảng và multikey

So sánh:

```javascript
{ _id: 1, tags: ["a"] }
{ _id: 2, tags: ["a", "b", "c", "d"] }
```

Khi có index `{tags:1}`, vì sao document thứ hai có thể góp nhiều index entries hơn?

**Đáp án:** `tags` là array, nên index dạng multikey có thể lập khóa cho nhiều giá trị phần tử của cùng một document. Kích thước index không nhất thiết chỉ tỷ lệ với số document. Số entries thực tế còn chịu ảnh hưởng quy tắc xử lý phần tử trùng và cấu trúc index.

### Bài 6. Partial index và tính đầy đủ kết quả

Có partial index:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    partialFilterExpression: { status: "pending" },
    name: "idx_pending_only"
  }
)
```

Hỏi vì sao truy vấn `find({customerId:"C001"})` không thể coi index này như nguồn đầy đủ cho toàn bộ đơn hàng của khách?

**Đáp án:** Vì index chỉ chứa các document `status: "pending"`. Dùng nó như một tập đầy đủ cho truy vấn không có điều kiện trạng thái sẽ bỏ sót các đơn `delivered` và `cancelled`. Index phù hợp hơn với truy vấn có `status: "pending"` cùng điều kiện khách hàng.

### Bài 7. Đọc số liệu `explain`

Hai kế hoạch cho cùng một truy vấn có thống kê giả định:

```text
Kế hoạch A: nReturned=20, totalKeysExamined=24,
            totalDocsExamined=20
Kế hoạch B: nReturned=20, totalKeysExamined=80000,
            totalDocsExamined=7000
```

Kế hoạch nào có dấu hiệu lọc hiệu quả hơn qua số lượng mục được xem?

**Đáp án:** A đi qua ít keys và documents hơn nhiều để trả cùng 20 kết quả. Nhưng để quyết định trong môi trường thực tế vẫn cần xem thời gian thực thi, cache, thao tác sort, index size, tần suất ghi và dữ liệu đại diện.

## 18. Kết luận

Ba khái niệm **độ chọn lọc**, **phân bố giá trị** và **kích thước index** luôn cần được xem cùng nhau:

- **Độ chọn lọc** trả lời: điều kiện cụ thể giảm tập kết quả còn bao nhiêu?
- **Phân bố giá trị** trả lời: giá trị phổ biến và giá trị hiếm của cùng field khác nhau đến mức nào?
- **Kích thước index** trả lời: để tăng tốc các query quan trọng, hệ thống phải trả chi phí lưu trữ, cache và cập nhật index bao nhiêu?

Quy tắc thực tế là **thiết kế index cho những truy vấn thật và những giá trị thật**, không chỉ cho cấu trúc field. Khi xem một index, hãy hỏi nó giúp lọc bao nhiêu document, có phục vụ sort/limit/projection hay không, có chịu tác động của skew và multikey không, và liệu lợi ích đọc có đáng với dung lượng cùng chi phí ghi. Dùng `explain("executionStats")`, `db.collection.stats()`, `getIndexes()` và thống kê truy cập index để đưa ra quyết định có căn cứ, rồi tiếp tục đánh giá khi workload thay đổi.
