# `explain` và các mức `queryPlanner`, `executionStats`, `allPlansExecution` trong MongoDB

Một truy vấn MongoDB viết đúng cú pháp chưa chắc đã chạy hiệu quả. Khi collection có nhiều document, các cách thực thi khác nhau có thể tạo chênh lệch rất lớn: quét toàn collection, đọc index rồi lấy document gốc, hoặc đọc trực tiếp các khóa trong index đã đáp ứng cả bộ lọc và sắp xếp. Để hiểu MongoDB **dự kiến truy vấn sẽ chạy như thế nào** và **đã xử lý bao nhiêu dữ liệu khi thực thi**, chúng ta dùng **`explain`**.

MongoDB cho phép chọn ba mức thông tin, gọi là **verbosity**:

- **`queryPlanner`**: cho biết kế hoạch truy vấn được chọn (winning plan), các kế hoạch ứng viên bị loại và thông tin về lập kế hoạch, nhưng không cung cấp thống kê của việc thực thi đầy đủ truy vấn.
- **`executionStats`**: thêm thống kê khi thực thi kế hoạch được chọn, chẳng hạn số kết quả trả về, số khóa index và document đã xem, thời gian thực thi được báo cáo.
- **`allPlansExecution`**: bao gồm thông tin như `executionStats`, đồng thời bổ sung thống kê **giai đoạn thử nghiệm lựa chọn kế hoạch** của các ứng viên khi có nhiều kế hoạch được cân nhắc; không có nghĩa MongoDB chạy đầy đủ tất cả kế hoạch tới hết tập kết quả.

Bài học thuộc chương **Kế hoạch thực thi**. Mục tiêu là biết gọi đúng mức `explain`, đọc các chỉ số quan trọng, phát hiện dấu hiệu index không phù hợp, hiểu giới hạn của kết quả và lựa chọn công cụ khi điều tra truy vấn chậm.

## 1. Một truy vấn có thể có nhiều đường thực thi

Giả sử collection `orders` có hàng trăm nghìn đơn hàng. Ứng dụng cần xem 10 đơn mới nhất của khách hàng `C0042`:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
```

MongoDB cần trả đúng các đơn của khách hàng đó theo thứ tự mới nhất trước. Nhưng nó có thể đạt kết quả bằng những đường đi rất khác nhau:

```text
                        Truy vấn
       customerId = C0042, sort createdAt/_id, limit 10
                             |
               +-------------+-------------+
               |                           |
    Quét document trong collection    Dùng index phù hợp
               |                           |
         Lọc customerId              Dò tới vùng khóa C0042
               |                           |
       Sắp xếp các kết quả            Đọc theo thứ tự index
               |                           |
         Lấy tối đa 10                 Lấy tối đa 10
               |                           |
               +-------------+-------------+
                             |
                    Cùng kết quả logic
                 nhưng chi phí có thể khác
```

Khi chưa có index phù hợp, máy chủ có thể dùng `COLLSCAN` và một thao tác `SORT`. Với compound index phù hợp, ví dụ `{ customerId: 1, createdAt: -1, _id: -1 }`, MongoDB có thể đọc vùng khóa của khách hàng theo thứ tự cần thiết mà không phải sắp xếp thủ công toàn bộ các đơn của khách đó.

`explain` giúp quan sát **kế hoạch cụ thể được chọn trên dữ liệu và phiên bản MongoDB hiện tại**, thay vì suy đoán từ việc collection đã có index.

## 2. Cú pháp `explain` trong `mongosh`

### 2.1. Gọi trực tiếp trên cursor của `find()`

```javascript
// Mức mặc định: queryPlanner
db.orders.find({ customerId: "C0042" })
  .explain()

// Chỉ xem thông tin kế hoạch
db.orders.find({ customerId: "C0042" })
  .explain("queryPlanner")

// Xem thống kê thực thi của kế hoạch thắng
db.orders.find({ customerId: "C0042" })
  .explain("executionStats")

// Xem thêm thống kê thử nghiệm các kế hoạch ứng viên
db.orders.find({ customerId: "C0042" })
  .explain("allPlansExecution")
```

Để giải thích **đúng truy vấn mà ứng dụng sử dụng**, cần giữ cả `filter`, `sort`, `skip`, `limit`, `projection` và các tùy chọn liên quan:

```javascript
db.orders.find(
  { customerId: "C0042", status: "paid" },
  { _id: 0, customerId: 1, createdAt: 1, total: 1 }
)
  .sort({ createdAt: -1 })
  .skip(20)
  .limit(10)
  .explain("executionStats")
```

Việc chỉ chạy `explain` cho `find({customerId: ...})` rồi áp kết luận cho một truy vấn có thêm `sort`, `skip`, `projection` là không đủ: query shape khác nhau có thể tạo kế hoạch khác nhau.

### 2.2. Gọi qua `db.collection.explain()`

MongoDB cũng có dạng:

```javascript
db.orders.explain("executionStats")
  .find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(10)
```

Đây là **explainable collection helper**; thích hợp khi muốn dùng cùng một cách gọi cho các thao tác như `find`, `aggregate` và một số thao tác khác được hỗ trợ. Với `find`, hai cách gọi trên đều thể hiện mục đích lấy explain của truy vấn.

### 2.3. Gọi bằng database command

Khi cần điều khiển rõ command hoặc tích hợp qua driver, dùng lệnh `explain` ở database:

```javascript
db.runCommand({
  explain: {
    find: "orders",
    filter: { customerId: "C0042" },
    sort: { createdAt: -1, _id: -1 },
    limit: 10
  },
  verbosity: "executionStats"
})
```

Phần `find: "orders"` nằm bên trong command cần giải thích; `verbosity` nằm ngoài để chọn mức thông tin. Lệnh chạy trong **database hiện tại**, vì thế cần xác định đúng database trước khi thực hành.

## 3. Đối chiếu ba mức verbosity

| Mức | Mục tiêu | Thông tin thường có | Câu hỏi nên dùng |
| --- | --- | --- | --- |
| `queryPlanner` | Hiểu lựa chọn kế hoạch | `queryPlanner`, `winningPlan`, `rejectedPlans`, thông tin hình dạng truy vấn và các stage | MongoDB định dùng index nào, có cần `SORT` hay `FETCH` không? |
| `executionStats` | Đo hoạt động của kế hoạch thắng | Thông tin planner cộng `executionStats`: `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis`, cây stage thực thi | Có phải đi qua quá nhiều keys/docs để trả vài kết quả không? |
| `allPlansExecution` | Tìm hiểu quá trình so sánh ứng viên | Thông tin của hai mức trên cùng phần `allPlansExecution` khi có dữ liệu về các kế hoạch ứng viên | Những ứng viên cạnh tranh đã xử lý thế nào trong giai đoạn chọn kế hoạch? |

Một quy trình đọc hợp lý là **bắt đầu với `queryPlanner`**, chuyển sang `executionStats` khi cần số liệu hoạt động, rồi dùng `allPlansExecution` nếu nghi ngờ quá trình lựa chọn giữa nhiều index/kế hoạch có vấn đề.

Ba mức không đại diện cho ba thuật toán truy vấn khác nhau; chúng là ba **mức độ thông tin trả về** từ cơ chế giải thích kế hoạch. Mức chi tiết tăng thường kéo theo thêm công việc quan sát và lượng dữ liệu explain phải đọc.

## 4. Chuẩn bị dữ liệu thực hành

Sử dụng một database lab có quyền đọc/ghi. Những lệnh tạo dữ liệu dưới đây chỉ phù hợp với môi trường thực hành:

```javascript
use mongo_explain_lab
```

Tạo 2.400 đơn hàng mẫu:

```javascript
const sampleOrders = Array.from({ length: 2400 }, (_, i) => ({
  _id: i + 1,
  orderCode: "ORD-" + String(i + 1).padStart(5, "0"),
  customerId: "C" + String((i % 300) + 1).padStart(4, "0"),
  status: i % 10 < 8 ? "delivered" : "pending",
  total: 100 + (i % 100) * 5,
  createdAt: new Date(Date.UTC(2026, 0, 1) + i * 60000),
  channel: i % 3 === 0 ? "mobile" : "web"
}));

db.orders.insertMany(sampleOrders);
```

Bộ dữ liệu có một số đặc điểm chủ đích:

- Mỗi khách hàng từ `C0001` đến `C0300` có 8 đơn hàng.
- `status: "delivered"` chiếm 80% document; `status: "pending"` chiếm 20%.
- `createdAt` thay đổi theo từng phút để có thứ tự thời gian rõ ràng.
- Trường `_id` được chọn duy nhất để giúp sắp xếp ổn định và làm rõ phép tìm theo index `_id_`.

Với dữ liệu nhỏ, MongoDB có thể chọn kế hoạch khác dự kiến vì quét collection cũng rất rẻ. Không được xem những con số minh họa trong bài là kết quả đo thực tế của server.

Chỉ chạy `insertMany()` một lần trên collection mới/trống; nếu chạy lặp với cùng `_id`, sẽ gặp duplicate key. Tránh xóa collection thật để tạo lại dữ liệu mẫu.

Kiểm tra dữ liệu bằng các truy vấn thường:

```javascript
db.orders.countDocuments({})
db.orders.countDocuments({ customerId: "C0042" })
db.orders.countDocuments({ status: "pending" })
```

Theo công thức tạo mẫu, kết quả lần lượt là `2400`, `8` và `480`.

## 5. Mức `queryPlanner`: MongoDB định làm gì?

Chạy:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("queryPlanner")
```

Phản hồi explain có thể chứa các nhóm thông tin:

```text
explain
├── explainVersion              (tùy phiên bản)
├── queryPlanner
│   ├── namespace               database.collection
│   ├── parsedQuery             biểu thức bộ lọc đã xử lý
│   ├── winningPlan             cây kế hoạch được chọn
│   ├── rejectedPlans           các kế hoạch ứng viên không được chọn
│   └── ...                     thông tin khác theo phiên bản
├── serverInfo                  thông tin máy chủ (khi có)
└── ...                         metadata, thông số lệnh
```

Cấu trúc cụ thể **khác nhau giữa các phiên bản MongoDB và bộ máy thực thi**. Một số bản dùng cây kế hoạch classic với `stage`; các bản khác có thêm `queryPlan` và `slotBasedPlan` khi truy vấn được xử lý bằng **slot-based execution engine (SBE)**. Vì vậy, nên đọc **ý nghĩa các stage và index được chọn**, không viết công cụ chỉ nhận đúng một kiểu cây JSON cố định.

### 5.1. `winningPlan` và `rejectedPlans`

`winningPlan` thể hiện kế hoạch MongoDB chọn để thực thi trong lần giải thích đó. Các stage có thể được lồng nhau:

```text
LIMIT
  └── FETCH
        └── IXSCAN
              indexName: idx_customer_created_id
```

Đây là một **cây minh họa**, không phải cam kết mọi phiên bản sẽ trả đúng những stage hoặc thứ tự trình bày trên. Nó diễn tả ý tưởng: quét index, lấy document gốc nếu cần và giới hạn đầu ra.

`rejectedPlans` cho biết các ứng viên bị loại khi planner có nhiều phương án để cân nhắc. **Rejected không nhất thiết có nghĩa sai**; ứng viên đó chỉ không được chọn trong bối cảnh lập kế hoạch hiện tại. Nếu không có nhiều ứng viên, mảng `rejectedPlans` có thể rỗng.

### 5.2. `parsedQuery` khác với chuỗi lệnh người dùng

`parsedQuery` phản ánh biểu thức mà MongoDB xử lý sau khi phân tích bộ lọc. Ví dụ một điều kiện equality đơn giản có thể được biểu diễn lại dưới dạng toán tử rõ ràng. Vì thế không nên đòi hỏi `parsedQuery` giống từng ký tự với bộ lọc được viết trong shell; điều cần kiểm tra là **ngữ nghĩa lọc**.

### 5.3. Những câu hỏi nên đặt khi đọc planner

1. Có stage `COLLSCAN` hay `IXSCAN` không?
2. Nếu dùng `IXSCAN`, đó có phải index mong đợi?
3. Phần `sort` được đáp ứng bằng thứ tự index hay xuất hiện stage `SORT`?
4. Có stage `FETCH` nghĩa là phải đọc document gốc không?
5. Kế hoạch có `LIMIT` và vị trí giới hạn dữ liệu phù hợp không?
6. Có những kế hoạch `rejectedPlans` đáng chú ý nào?

`queryPlanner` thường đủ để trả lời “MongoDB định đi theo con đường nào”, nhưng **không đủ** để khẳng định con đường đó đã đọc bao nhiêu document hoặc mất bao nhiêu mili giây trong lần chạy.

## 6. Các stage thường gặp và cách diễn giải

| Stage / khái niệm | Vai trò | Điều đáng chú ý |
| --- | --- | --- |
| `COLLSCAN` | Quét collection để xem document | Có thể hợp lý ở collection nhỏ hoặc khi phần lớn dữ liệu cần được đọc |
| `IXSCAN` | Duyệt các khóa trong index | Xem tên index, khoảng khóa và số key examined |
| `FETCH` | Lấy document từ collection sau khi tìm khóa | Có thể cần vì bộ lọc/projection thiếu field trong index |
| `SORT` | Sắp xếp kết quả tại một bước thực thi | Có thể tăng chi phí khi index không hỗ trợ sort |
| `LIMIT` | Giới hạn số kết quả | Không có nghĩa chi phí tìm/lọc trước đó luôn nhỏ |
| `SKIP` | Bỏ qua một số kết quả | Offset lớn có thể phải đi qua nhiều mục |
| `PROJECTION` hoặc biến thể covered | Chọn các field được trả về | Covered query có thể không phải fetch document gốc |
| `COUNT_SCAN` | Đếm bằng một cách quét index trong trường hợp phù hợp | Phụ thuộc loại truy vấn và kế hoạch |
| `EOF` | Kế hoạch không có kết quả để xử lý trong bối cảnh đó | Cần đọc cùng filter và phần explain khác |

Không được coi đây là **danh sách đầy đủ stage**. Query engine có thể trình bày thêm `OR`, `AND_HASH`, `SHARD_MERGE` hoặc những tên stage khác theo loại truy vấn, cách tối ưu và cấu hình sharding. Với SBE, phần mô tả cấp thấp có thể dùng các toán tử riêng, không trùng tên stage của classic engine.

### `IXSCAN` không đồng nghĩa truy vấn được tối ưu hoàn toàn

Ví dụ query planner chọn index `{ status: 1 }` cho:

```javascript
db.orders.find({ status: "delivered" })
```

Nếu 80% dữ liệu có `status: "delivered"`, truy vấn có thể vẫn phải xem rất nhiều khóa và document, dù stage là `IXSCAN`. Ngược lại, một `COLLSCAN` trên collection rất nhỏ có thể là lựa chọn hiệu quả.

**Kết luận cần dựa trên khối lượng công việc thực tế**, không chỉ gắn nhãn “`IXSCAN` là tốt” và “`COLLSCAN` là xấu”.

### `indexBounds`: index duyệt vùng khóa nào?

Khi có `IXSCAN`, một phần kế hoạch có thể hiển thị `indexBounds`, mô tả khoảng khóa được quét. Với equality `customerId: "C0042"`, khoảng khóa của trường này thường được giới hạn quanh giá trị đó; với range `total: {$gte: 500}`, khoảng khóa rộng hơn.

Hình dung:

```text
Index theo customerId:

... C0040 | C0041 | [C0042 ... C0042] | C0043 | ...
                      ^ vùng cần xem
```

Nếu `indexBounds` quá rộng hoặc phần điều kiện quan trọng không thể thành bound trên index, MongoDB có thể phải đi qua nhiều keys rồi mới lọc. Việc đọc index bounds cần kết hợp với filter, thứ tự khóa index, multikey và các trường thống kê thực thi.

## 7. Mức `executionStats`: MongoDB đã xử lý bao nhiêu dữ liệu?

Chạy cùng truy vấn nhưng tăng verbosity:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("executionStats")
```

Phản hồi gồm thông tin planner **và** phần `executionStats`, thường có các trường:

```javascript
// Phần minh họa cấu trúc, không phải kết quả đo của dữ liệu mẫu
{
  executionStats: {
    nReturned: 5,
    executionTimeMillis: 2,
    totalKeysExamined: 5,
    totalDocsExamined: 5,
    executionStages: {
      // Cây stage và các bộ đếm chi tiết tùy MongoDB version
    }
  }
}
```

Các con số `5` và `2` **chỉ minh họa một trường hợp có kế hoạch hiệu quả**. Kết quả thực tế có thể khác và không được suy ra chỉ từ cú pháp truy vấn.

| Trường | Diễn giải |
| --- | --- |
| `nReturned` | Số document/giá trị kết quả được trả về trong thực thi giải thích |
| `executionTimeMillis` | Thời gian thực thi được báo cáo, thường tính theo ms; chịu ảnh hưởng môi trường |
| `totalKeysExamined` | Tổng số index keys được duyệt/kiểm tra theo thống kê |
| `totalDocsExamined` | Tổng số document được xem xét ở những bước phải đọc document |
| `executionStages` | Chi tiết cây thực thi, có thể chứa bộ đếm từng stage |

### 7.1. Phân biệt examined với returned

Giả sử một truy vấn trả `nReturned = 10` nhưng `totalDocsExamined = 50.000`. Điều đó cho thấy rất nhiều document đã được xem xét so với số kết quả trả ra. Có thể index không phù hợp, bộ lọc chỉ được đánh giá sau khi fetch, hoặc truy vấn phải đọc lượng dữ liệu lớn để sort/skip.

Một ví dụ giả định:

| Truy vấn | `nReturned` | `totalKeysExamined` | `totalDocsExamined` | Nhận xét sơ bộ |
| --- | ---: | ---: | ---: | --- |
| A | 10 | 12 | 10 | Ít mục cần xem so với kết quả |
| B | 10 | 80.000 | 20.000 | Xem rất nhiều key và document |
| C (covered) | 10 | 10 | 0 | Có thể trả kết quả từ index, không fetch document |
| D (COLLSCAN) | 10 | 0 | 2.400 | Quét document không qua index |

Bảng chỉ nhằm luyện đọc chỉ số; không phải mỗi dòng luôn tương ứng một kế hoạch đã đo. **Chi phí tốt hay xấu phải xét truy vấn cần làm gì**, không chỉ so ratio. Ví dụ phép đếm hàng triệu document, truy vấn phân trang sâu hoặc aggregation có thể hợp lý khi `examined` lớn.

### 7.2. Khi nào `totalDocsExamined = 0`?

Một **covered query** có thể chỉ dùng index để lọc và lấy các field trả về, không cần fetch document gốc. Ví dụ khi có index:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_created_id" }
)
```

câu truy vấn chỉ cần những field trong index:

```javascript
db.orders.find(
  { customerId: "C0042" },
  { _id: 1, customerId: 1, createdAt: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("executionStats")
```

có thể được đáp ứng từ index mà không đọc document gốc, tùy planner và cấu hình. Nhưng nếu projection cần thêm `total` mà index không chứa field này, MongoDB có thể phải `FETCH` document để lấy `total`.

Đừng nhầm **`totalDocsExamined = 0`** với “không làm công việc nào”: truy vấn vẫn có thể phải duyệt nhiều index keys hoặc thực hiện các bước khác.

### 7.3. `executionTimeMillis` không phải lời hứa về độ trễ production

Thời gian explain chịu ảnh hưởng của:

- Kích thước dữ liệu, phân bố giá trị và index.
- Trạng thái cache, I/O đĩa, tải CPU và yêu cầu khác đang chạy.
- Phiên bản MongoDB, cấu hình máy, triển khai replica set/sharded cluster.
- Việc phải thử nghiệm kế hoạch và cách explain thực thi/trình bày thống kê.
- Khác biệt giữa một phép đo trong shell và request thực tế còn có network, driver, giải mã BSON, xử lý ứng dụng.

Vì vậy, `executionTimeMillis = 2` trong một lần đo không bảo đảm endpoint luôn mất 2 ms. Nên kết hợp `explain` với monitoring, slow-query log/profiler khi có quyền và phép đo trên workload đại diện.

## 8. Thực hành so sánh trước và sau khi tạo index

Giữ một query shape nhất quán:

```javascript
const filter = { customerId: "C0042" };
const order = { createdAt: -1, _id: -1 };

db.orders.find(filter)
  .sort(order)
  .limit(5)
  .explain("executionStats")
```

Quan sát `queryPlanner.winningPlan`, `totalKeysExamined`, `totalDocsExamined` và thông tin sort. Trong môi trường lab với 2.400 document và chỉ có index `_id_`, một kế hoạch có thể quét nhiều document rồi sort; nhưng **không khẳng định trước winning plan** mà không chạy MongoDB.

Tạo index cho đúng filter và sort:

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_created_id" }
)
```

Chạy lại:

```javascript
db.orders.find(filter)
  .sort(order)
  .limit(5)
  .explain("executionStats")
```

Các điểm cần quan sát là liệu `idx_customer_created_id` xuất hiện trong winning plan hay không, MongoDB có tránh được bước `SORT` bổ sung hay không và lượng keys/docs examined có thay đổi hay không.

Nếu muốn chỉ nhìn các field cụ thể của kết quả explain trong `mongosh`:

```javascript
const result = db.orders.find(filter)
  .sort(order)
  .limit(5)
  .explain("executionStats");

printjson(result.queryPlanner);
printjson({
  nReturned: result.executionStats?.nReturned,
  keysExamined: result.executionStats?.totalKeysExamined,
  docsExamined: result.executionStats?.totalDocsExamined,
  executionTimeMillis: result.executionStats?.executionTimeMillis
});
```

`executionStats` tồn tại ở mức `executionStats`/ `allPlansExecution`, nhưng không nên giả định nó có trong `queryPlanner`. Ký pháp optional chaining `?.` ở đây là cú pháp JavaScript của `mongosh`, không phải cú pháp MongoDB query.

### Không so sánh hai truy vấn khác shape

Những khác biệt sau đều có thể ảnh hưởng kế hoạch:

```javascript
// Truy vấn theo customerId, không sort
db.orders.find({ customerId: "C0042" })

// Có sort + limit
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)

// Có thêm điều kiện status và projection
db.orders.find(
  { customerId: "C0042", status: "pending" },
  { _id: 0, customerId: 1, status: 1 }
)
```

Muốn quy kết lợi ích cho index mới, hãy so sánh **cùng filter, sort, projection, limit**, trên dữ liệu tương đương và có lưu lại bối cảnh phiên bản/điều kiện đo.

## 9. `allPlansExecution`: xem xét ứng viên cạnh tranh

Khi một truy vấn có nhiều index thích hợp, query planner có thể cần lựa chọn giữa các kế hoạch. Ví dụ, tạo thêm index đơn theo `customerId` và `createdAt` trong lab:

```javascript
db.orders.createIndex(
  { customerId: 1 },
  { name: "idx_customer" }
)

db.orders.createIndex(
  { createdAt: -1 },
  { name: "idx_created_desc" }
)
```

Với truy vấn:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("allPlansExecution")
```

có thể tồn tại những hướng tiếp cận: dùng compound index theo khách hàng/thời gian; dùng index khách hàng rồi sort; hoặc một phương án dùng index thời gian và lọc khách hàng. Việc planner thực sự xem xét ứng viên nào phụ thuộc điều kiện của phiên bản và dữ liệu.

Ở mức này, phần `executionStats` có thể chứa `allPlansExecution`:

```javascript
// Chỉ minh họa vị trí các trường
{
  queryPlanner: {
    winningPlan: { /* ... */ },
    rejectedPlans: [ /* ... */ ]
  },
  executionStats: {
    nReturned: 5,
    totalKeysExamined: 5,
    totalDocsExamined: 5,
    executionStages: { /* ... */ },
    allPlansExecution: [
      // Thống kê giai đoạn thử nghiệm của ứng viên,
      // nếu planner đã có các ứng viên và dữ liệu để báo cáo
    ]
  }
}
```

**Điểm cần hiểu đúng:** `allPlansExecution` không có nghĩa là MongoDB đã chạy **toàn bộ** mỗi kế hoạch ứng viên cho đến khi hết dữ liệu và đo thời gian đầy đủ của mọi kế hoạch. Thường đó là thống kê ở **giai đoạn thử nghiệm/đánh giá ứng viên** để chọn kế hoạch thắng, trong khi thống kê thực thi đầy đủ phản ánh kế hoạch được chọn.

### `winningPlan` và `rejectedPlans` có cần giống số lượng `allPlansExecution`?

Không nên áp giả định một-một đơn giản. Cấu trúc báo cáo và số ứng viên có thể khác theo phiên bản và cách planner xử lý; đôi khi chỉ có một kế hoạch khả thi hoặc không có thông tin thử nghiệm chi tiết cần báo. Khi `allPlansExecution` rỗng hoặc ít mục, điều này **không tự chứng minh** một index đã bị hỏng.

Khi điều tra, nên đọc đồng thời:

1. `queryPlanner.winningPlan`: kế hoạch được chọn.
2. `queryPlanner.rejectedPlans`: các phương án được nêu là không chọn.
3. `executionStats`: hoạt động của kế hoạch thắng.
4. `executionStats.allPlansExecution`: dữ liệu thử nghiệm ứng viên nếu có.

### Khi nào dùng mức này?

- Có nhiều index gần giống nhau, không rõ vì sao planner chọn một index.
- Query chậm với một số giá trị tham số nhưng nhanh với giá trị khác.
- Nghi ngờ phân bố dữ liệu lệch làm kế hoạch được chọn thiếu phù hợp.
- Muốn hiểu phạm vi planner đã cân nhắc, không chỉ nhìn index của winning plan.

Với câu hỏi đơn giản “có quét collection không?”, `queryPlanner` thường là đủ; với câu hỏi “quét bao nhiêu document?”, `executionStats` trực tiếp hơn.

## 10. `explain` và plan cache: một giới hạn quan trọng

MongoDB có thể lưu **kế hoạch truy vấn đã chọn** trong plan cache để tránh phải lập kế hoạch lại từ đầu cho những lần chạy tương tự. Nhưng `explain` được thiết kế để **giải thích quá trình lập kế hoạch và thực thi truy vấn được yêu cầu**, không phải công cụ đọc nguyên xi kế hoạch đã cache của một request production bất kỳ.

Một điều cần nhớ là **`explain` không sử dụng các plan cache entry hiện có theo cách truy vấn thông thường và không tạo entry mới vào plan cache từ việc explain**. Vì thế, kế hoạch explain có thể khác kế hoạch mà ứng dụng đang dùng khi cache ảnh hưởng đến truy vấn bình thường.

Hệ quả:

- `winningPlan` trong explain là kế hoạch thắng **trong lần explain đó**.
- Không khẳng định ngay rằng mọi request sản xuất đều dùng chính plan này.
- Khi điều tra sự khác biệt theo thời gian hoặc theo tham số, cần xem cả dữ liệu monitoring và thông tin plan cache nếu có quyền và công cụ phù hợp.
- Đừng xóa plan cache trên hệ thống đang vận hành chỉ để một phép explain trông “đúng hơn”; đó là thao tác vận hành khác và có thể ảnh hưởng nhiều truy vấn.

Trong các phiên bản MongoDB khác nhau, có những trường nhận dạng query shape/kế hoạch như `queryHash`, `planCacheKey` hoặc `planCacheShapeHash`. Tên trường và khả năng hiện diện có thể thay đổi, nên không viết script phụ thuộc vào một tên duy nhất nếu chưa kiểm tra phiên bản máy chủ.

## 11. So sánh kế hoạch tự chọn và kế hoạch có `hint()`

Khi có nhiều index, đôi khi cần nghiên cứu một index cụ thể:

```javascript
// MongoDB tự chọn kế hoạch
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("executionStats")

// Yêu cầu dùng index theo tên
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .hint("idx_customer_created_id")
  .explain("executionStats")
```

`hint()` giúp cô lập một kế hoạch sử dụng index cụ thể nếu hợp lệ. Đây là công cụ **điều tra**, không tự chứng minh rằng index bị ép luôn tốt hơn.

Không ép `hint` một cách máy móc trong production: nếu index bị đổi tên/xóa, phân bố dữ liệu thay đổi hoặc truy vấn thay đổi, hint cố định có thể trở thành gánh nặng hoặc gây lỗi.

Nếu muốn so sánh hai kế hoạch trong môi trường kiểm soát, ghi lại `totalKeysExamined`, `totalDocsExamined`, `executionTimeMillis`, winning plan và trạng thái dữ liệu. Khi so sánh có hint với không hint, cần nhớ quá trình lập kế hoạch và điều kiện đo có thể khác nhau.

## 12. `explain` đối với aggregation

`explain` không chỉ dành cho `find()`. Nếu ứng dụng tổng hợp dữ liệu bằng `aggregate()`, có thể giải thích pipeline:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { customerId: "C0042" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 5 },
  {
    $project: {
      _id: 1,
      customerId: 1,
      createdAt: 1,
      total: 1
    }
  }
])
```

Phản hồi của aggregation có thể thể hiện `queryPlanner`, `executionStats`, hoặc một mảng `stages` tùy vào pipeline, các bước có thể đẩy xuống query engine và phiên bản server. Không nên suy rằng kết quả aggregation sẽ luôn có đúng cùng vị trí field như explain của `find()`.

### Pipeline có thể được tối ưu lại

Người dùng viết:

```javascript
[
  { $match: { status: "pending" } },
  { $sort: { createdAt: -1 } },
  { $limit: 10 }
]
```

MongoDB có thể tối ưu cách thực thi để tận dụng index hoặc gộp một số bước tương đương. Explain mô tả **kế hoạch sau quá trình lập kế hoạch/tối ưu**, không nhất thiết lặp lại nguyên văn từng stage theo thứ tự hiển thị của pipeline nguồn.

Một stage aggregation có thể tự tính chi phí đáng kể sau khi đầu vào đã được lấy từ index. Vì thế với pipeline phức tạp, đọc cả thông tin **đọc dữ liệu ở đầu pipeline** lẫn các **stage phía sau**, đặc biệt là `$group`, `$sort`, `$lookup` hoặc `$unwind` nếu có.

### Explain cho `countDocuments()` không tự hiện bằng cùng dạng như `find`

Các helper tiện ích có thể sử dụng các lệnh/pipeline khác nhau bên dưới. Nếu muốn tìm hiểu kế hoạch của một phép đếm, hãy giải thích lệnh/pipeline tương ứng thay vì giả định có thể thêm `.explain()` vào mọi phương thức nhận kết quả số:

```javascript
db.orders.explain("executionStats").aggregate([
  { $match: { status: "pending" } },
  { $count: "total" }
])
```

Đây là ví dụ pipeline đếm. Khi đối chiếu với `countDocuments()` thật trong ứng dụng, cần bảo đảm filter, collation và điều kiện thực thi tương ứng.

## 13. Đọc explain trong môi trường sharded cluster

Trên một **sharded cluster**, truy vấn có thể được gửi đến một shard hoặc nhiều shard, sau đó dữ liệu được hợp nhất. Explain có thể chứa thông tin theo từng shard, các bước merge hoặc phần báo cáo nhiều tầng.

Ví dụ khái niệm:

```text
Client
  |
 mongos
  |-- shard A: lọc / IXSCAN / FETCH
  |-- shard B: lọc / IXSCAN / FETCH
  '-- merge/sort/limit kết quả
```

Khi truy vấn chậm trong hệ sharded, cần trả lời thêm:

- Query có nhắm đến shard phù hợp dựa trên shard key không?
- Có truy vấn **scatter-gather** tới nhiều shard không?
- Số liệu thống kê phản ánh công việc tại shard nào, và bước merge có chi phí bao nhiêu?
- Có sort và limit thực hiện ở shard, router hay cả hai theo kế hoạch tối ưu không?

Không nên gộp các chỉ số ở nhiều nhánh giải thích một cách tùy ý rồi so với kết quả của standalone server. Cấu trúc báo cáo tùy phiên bản và loại truy vấn; hãy đọc theo phạm vi từng node/shard cũng như phần tổng hợp khi tồn tại.

## 14. Java Sync Driver: gọi database command `explain`

Trong ứng dụng Java sử dụng MongoDB Sync Driver, ta có thể gửi database command `explain` để quan sát cùng một truy vấn như trong `mongosh`.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ExplainQueryExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu biến MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_explain_lab");

            Document findCommand = new Document("find", "orders")
                .append("filter",
                    new Document("customerId", "C0042"))
                .append("sort",
                    new Document("createdAt", -1).append("_id", -1))
                .append("limit", 5);

            Document explainCommand =
                new Document("explain", findCommand)
                    .append("verbosity", "executionStats");

            Document explanation =
                database.runCommand(explainCommand);

            System.out.println(
                explanation.toJson()
            );

            Document stats =
                explanation.get("executionStats", Document.class);
            if (stats != null) {
                System.out.println(
                    "nReturned = " + stats.get("nReturned")
                );
                System.out.println(
                    "totalKeysExamined = "
                    + stats.get("totalKeysExamined")
                );
                System.out.println(
                    "totalDocsExamined = "
                    + stats.get("totalDocsExamined")
                );
            }
        }
    }
}
```

Đoạn mã yêu cầu MongoDB Java Sync Driver tương thích và biến môi trường `MONGODB_URI` hợp lệ. Không ghi connection string chứa mật khẩu trực tiếp trong source code.

Với Java Driver phù hợp, một số iterable query còn có API `explain` cùng verbosity tương ứng. Dùng database command là cách thể hiện minh bạch payload `find` và `verbosity`; khi ứng dụng có collection/view/aggregation phức tạp, cần chọn cách gọi theo đúng API và phiên bản driver đang dùng.

**Cẩn thận khi tự phân tích JSON:** ở ví dụ Java, chỉ truy cập top-level `executionStats` nếu tồn tại. Với aggregation phức tạp hoặc sharded explain, phần thống kê có thể ở vị trí khác. Một công cụ giám sát nghiêm túc cần xử lý biến thể cấu trúc theo phiên bản/loại truy vấn thay vì giả định toàn bộ explain là một JSON cố định.

## 15. Những sai lầm thường gặp

| Nhầm lẫn | Điều xảy ra | Cách hiểu và xử lý |
| --- | --- | --- |
| “`queryPlanner` cho biết truy vấn mất bao nhiêu ms” | Mức này chủ yếu trả thông tin lập kế hoạch, không có thống kê thực thi đầy đủ | Dùng `executionStats` khi cần số liệu |
| “`IXSCAN` nghĩa là truy vấn chắc chắn nhanh” | Index có thể quét một vùng rất rộng rồi fetch nhiều document | Xem `keysExamined`, `docsExamined`, `nReturned` và filter |
| “`COLLSCAN` là lỗi MongoDB” | Quét collection đôi khi là kế hoạch hợp lý | Xem dữ liệu, selectivity, sort và chi phí thật |
| “`rejectedPlans` là các kế hoạch không hợp lệ” | Rejected chỉ có nghĩa không được chọn | Đọc ngữ cảnh planner và thống kê ứng viên |
| “`allPlansExecution` chạy đầy đủ mọi kế hoạch ứng viên” | Phần ứng viên chủ yếu mô tả giai đoạn thử nghiệm chọn plan | Đừng so thời gian ứng viên như benchmark toàn truy vấn |
| “`explain` chắc chắn dùng đúng plan cache của ứng dụng” | Explain không sử dụng plan cache theo cách truy vấn thông thường | Kết hợp quan sát cache/monitoring nếu cần |
| “`totalKeysExamined = nReturned` thì không còn công việc khác” | Có thể còn fetch, projection, network, xử lý ứng dụng | Đọc toàn bộ plan và bối cảnh |
| “`totalDocsExamined = 0` nghĩa là truy vấn không tốn tài nguyên” | Covered query vẫn có thể duyệt nhiều index keys | Xem thêm `totalKeysExamined`, thời gian, sort |
| “Tăng `limit` hoặc `skip` không làm đổi plan” | Query shape và chi phí có thể thay đổi | Explain đúng truy vấn của ứng dụng |
| “Chỉ một lần `executionTimeMillis` đủ để kết luận” | Cache, tải hệ thống và trial planner làm số đo thay đổi | Đo trên workload đại diện và kết hợp monitoring |
| “Plan của aggregation giống hệt find” | Pipeline có stage, tối ưu và biểu diễn riêng | Đọc cả pipeline stage và phần query planner |
| “Script có thể phụ thuộc cố định vào `winningPlan.stage`” | SBE/sharding/phiên bản làm cấu trúc khác nhau | Xử lý cấu trúc theo phiên bản và phạm vi |
| “Có thể ép hint là giải quyết mọi vấn đề” | Hint không phù hợp có thể làm truy vấn kém hơn hoặc lỗi | Chỉ dùng khi có phép đo và quy trình theo dõi |

## 16. Bài tập thực hành

### Bài 1. Chọn verbosity

Cho ba yêu cầu:

1. Muốn biết truy vấn đang dùng index nào, có `SORT` không.
2. Muốn biết truy vấn trả 20 document nhưng đã đọc bao nhiêu index keys/document.
3. Muốn xem thống kê giai đoạn thử nghiệm các ứng viên khi planner phải chọn giữa nhiều index.

**Đáp án:**

1. `queryPlanner`.
2. `executionStats`.
3. `allPlansExecution`.

Mức cao hơn cũng chứa một phần thông tin của mức thấp hơn, nhưng không cần luôn dùng mức chi tiết nhất cho mọi câu hỏi.

### Bài 2. Viết explain đúng query shape

Yêu cầu: lấy 15 đơn `pending` mới nhất, sort `createdAt` giảm dần và `_id` giảm dần, chỉ lấy `status`, `createdAt` và `_id`. Viết lệnh xem thống kê thực thi.

**Đáp án:**

```javascript
db.orders.find(
  { status: "pending" },
  { status: 1, createdAt: 1, _id: 1 }
)
  .sort({ createdAt: -1, _id: -1 })
  .limit(15)
  .explain("executionStats")
```

Khi phân tích, kiểm tra index/sort và số lượng document được xem xét thay vì chỉ tìm một `IXSCAN`.

### Bài 3. Đọc các chỉ số

Hai truy vấn cùng trả `nReturned = 10`, nhưng số liệu giả định:

```text
A: totalKeysExamined = 12, totalDocsExamined = 10
B: totalKeysExamined = 70000, totalDocsExamined = 25000
```

Truy vấn nào có dấu hiệu tìm/lọc hiệu quả hơn? Có thể khẳng định chắc chắn A nhanh hơn mọi lúc không?

**Đáp án:** A xem ít key và document hơn nhiều so với số kết quả. Đây là tín hiệu thuận lợi. Nhưng chưa thể khẳng định A luôn nhanh hơn ở mọi điều kiện nếu chưa xem query shape, cache, I/O, sort, kích thước tài liệu, độ trễ và workload thực tế.

### Bài 4. So sánh trước và sau index

Collection `orders` thường truy vấn:

```javascript
db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
```

Hãy đề xuất index phù hợp, rồi viết lệnh explain để kiểm tra.

**Đáp án:**

```javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1, _id: -1 },
  { name: "idx_customer_created_id" }
)

db.orders.find({ customerId: "C0042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(5)
  .explain("executionStats")
```

So sánh với baseline trước khi tạo index, đặc biệt là `winningPlan`, số keys/docs examined và sự xuất hiện của `SORT`. Index mới chỉ là **ứng viên**, không bảo đảm query planner luôn chọn nó ở mọi tập dữ liệu.

### Bài 5. Vì sao `rejectedPlans` rỗng?

Một truy vấn trả `rejectedPlans: []`. Có thể kết luận rằng MongoDB không hoạt động đúng không?

**Đáp án:** Không. Có thể không có nhiều ứng viên phù hợp để so sánh hoặc cách planner báo cáo không có plan bị loại. Hãy đọc toàn bộ explain và bối cảnh; `rejectedPlans` rỗng không tự là dấu hiệu lỗi.

### Bài 6. Hiểu `allPlansExecution`

Một báo cáo có winning plan, hai rejected plans và vài thống kê ứng viên. Có nên lấy `executionTimeMillis` hoặc các bộ đếm thử nghiệm của từng ứng viên rồi tuyên bố “đây là thời gian đầy đủ để chạy toàn bộ truy vấn bằng index X” không?

**Đáp án:** Không. Thống kê ứng viên ở mức `allPlansExecution` liên quan giai đoạn thử nghiệm lựa chọn kế hoạch; chúng không bảo đảm phản ánh việc chạy trọn truy vấn trên từng phương án. Để nghiên cứu một phương án riêng, có thể explain cùng truy vấn với `hint` thích hợp trên môi trường kiểm soát và so sánh kết quả đầy đủ, nhưng vẫn cần xét bối cảnh đo.

### Bài 7. Khi xuất hiện `FETCH`

Truy vấn chỉ lọc `customerId` nhưng cần trả `total`, trong khi index chỉ có `customerId` và `createdAt`. Vì sao MongoDB có thể phải `FETCH` document gốc?

**Đáp án:** Index không chứa giá trị `total`, nên máy chủ có thể cần lấy document để đọc field này. Nếu thực sự đáng giá với workload, cân nhắc index có thêm field phục vụ truy vấn, nhưng cần tính chi phí dung lượng và ghi. Không mở rộng index chỉ để tránh `FETCH` cho một truy vấn ít dùng.

## 17. Quy trình điều tra truy vấn chậm bằng `explain`

Khi một endpoint MongoDB bị chậm, có thể đi theo thứ tự:

1. **Ghi lại truy vấn thật**: bộ lọc, sort, limit, skip, projection, collation, tham số và database/collection. Đừng chỉ nhớ câu mô tả “tìm đơn của khách”.
2. **Chạy `queryPlanner`**: xem winning plan, các index được cân nhắc, stage sort/fetch, bounds và trường hợp quét collection.
3. **Chạy `executionStats` trên môi trường phù hợp**: so `nReturned` với `totalKeysExamined`, `totalDocsExamined`; chú ý limit, offset và phần hoạt động của các stage.
4. **Nếu có cạnh tranh giữa nhiều kế hoạch**, dùng `allPlansExecution` để tìm hiểu dữ liệu thử nghiệm ứng viên; đừng coi đó là benchmark đầy đủ của từng plan.
5. **Đối chiếu index hiện có** bằng `getIndexes()`; cân nhắc index mới theo equality, sort, range, projection và phân bố giá trị, không chỉ theo tên field.
6. **Thử nghiệm có kiểm soát**: khi phù hợp, so sánh trước/sau index hoặc dùng `hint` ở môi trường thử nghiệm, giữ query shape và điều kiện đo tương đương.
7. **Xem bối cảnh production**: cache, plan cache, sharding, concurrency, slow-query monitoring, dung lượng index và chi phí ghi. `explain` là công cụ chẩn đoán, không thay thế toàn bộ hệ thống quan sát.

## Kết luận

`explain` là cầu nối giữa câu truy vấn người lập trình viết và cách MongoDB thực hiện nó. **`queryPlanner` trả lời “MongoDB định làm gì?”**; **`executionStats` trả lời “kế hoạch thắng đã làm bao nhiêu công việc?”**; còn **`allPlansExecution` giúp hiểu thêm “các ứng viên đã được thử nghiệm ra sao trong quá trình chọn kế hoạch?”**.

Khi đánh giá một truy vấn, hãy quan sát **cả kế hoạch lẫn số liệu**. Một `IXSCAN` có thể quét quá nhiều key; một `COLLSCAN` có thể phù hợp trên dữ liệu nhỏ; một `FETCH` có thể cần thiết nếu projection đòi hỏi field ngoài index; và một `executionTimeMillis` đẹp trong explain không bảo đảm độ trễ ứng dụng luôn thấp. Hiểu đúng ba mức verbosity, sự khác nhau giữa query plan với execution metrics và các giới hạn của explain sẽ giúp thiết kế index và tối ưu truy vấn MongoDB dựa trên chứng cứ thay vì phỏng đoán.
