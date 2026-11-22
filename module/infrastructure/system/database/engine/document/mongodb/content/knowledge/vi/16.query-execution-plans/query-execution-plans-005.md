# hint, giới hạn sử dụng và cách kiểm chứng một index được đề xuất trong MongoDB

## Mục tiêu bài học

MongoDB có **query planner** để lựa chọn kế hoạch thực thi cho các truy vấn như `find()` và một số aggregation. Khi collection có nhiều index, một truy vấn có thể có nhiều cách thực hiện: quét collection, duyệt một index, kết hợp lọc và sắp xếp qua compound index, hoặc đọc document sau khi duyệt index.

Trong quá trình tối ưu, kỹ sư đôi khi đề xuất một index mới và muốn biết: **Nếu truy vấn dùng đúng index này thì điều gì xảy ra?** MongoDB hỗ trợ **`hint()`** để yêu cầu hoặc ép lựa chọn một index trong những tình huống API cho phép. Tuy nhiên, `hint` là công cụ có giới hạn: nó không tự sửa thiết kế query, không tạo index chưa tồn tại, không bảo đảm latency thấp hơn, và có những trường hợp không được hỗ trợ hoặc có thể dẫn đến kết quả không đầy đủ nếu ép một index thưa dữ liệu.

Bài học tập trung vào hai năng lực:

1. **Sử dụng `hint` đúng mục đích** — cú pháp, các giới hạn, hành vi đặc biệt và rủi ro khi đưa vào production.
2. **Kiểm chứng index được đề xuất** — so baseline với candidate index bằng `explain()`, bộ đếm thực thi, tính đúng đắn của kết quả, chỉ số ứng dụng và chi phí ghi/lưu trữ.

Sau bài học, bạn có thể:

- Giải thích planner chọn index như thế nào ở mức thực hành và vì sao không nên ép một index theo cảm tính.
- Dùng `cursor.hint("index_name")`, `cursor.hint({field: 1})`, `aggregate(..., {hint: ...})` và `hint({$natural:1})` phù hợp.
- Nhận biết các giới hạn với index không tồn tại, hidden index, `$text`, time-series, query settings/index filters, sparse/partial index và collation.
- Đọc `winningPlan`, `rejectedPlans`, `indexBounds`, `nReturned`, `totalKeysExamined`, `totalDocsExamined`, các bước `IXSCAN`, `FETCH`, `SORT`, `COLLSCAN`.
- Lập thí nghiệm so sánh một query **giữ nguyên filter, sort, projection, limit và collation** khi không hint và khi hint từng candidate.
- Phân biệt `explain("queryPlanner")`, `explain("executionStats")`, `explain("allPlansExecution")`, plan cache và latency ứng dụng dưới tải.
- Đưa ra quyết định: giữ planner tự chọn, thêm index, điều chỉnh query, ép hint tạm thời hoặc bỏ index đề xuất.
- Xây dựng kế hoạch triển khai, giám sát và rollback mà không làm hỏng đường đọc hoặc tăng write overhead ngoài ý muốn.

> **Nguyên tắc:** `hint` là một **phép thử giả thuyết** và đôi khi là một biện pháp can thiệp có kiểm soát. Bằng chứng tối ưu phải đến từ **kết quả đúng, kế hoạch thực thi phù hợp, latency thực tế và tổng chi phí index** — không phải từ việc ép planner dùng một index bất kỳ.

---

## 1. Vì sao cùng một truy vấn có thể có nhiều kế hoạch?

Giả sử hệ thống quản lý đơn hàng sử dụng collection `orders`. Một endpoint hiển thị 20 đơn PAID mới nhất của một khách trong một tenant:

~~~javascript
db.orders.find(
  {
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID"
  },
  {
    orderNo: 1,
    createdAt: 1,
    total: 1,
    _id: 1
  }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Collection có thể có những index sau:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, customerId: 1 },
  { name: "idx_tenant_customer" }
);

db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);

db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_customer_status_recent" }
);
~~~

Planner có những hướng tiềm năng:

1. Dùng index theo `tenantId, customerId` để tìm các đơn của khách, sau đó lọc status và sắp xếp.
2. Dùng index theo `tenantId, status, createdAt`, rồi kiểm tra customerId trong những document tương ứng.
3. Dùng compound index chứa cả các equality field và sort keys, có khả năng giảm lượng key cần duyệt và tránh bước sort riêng.
4. Với dữ liệu rất nhỏ hoặc tính chọn lọc thấp, quét collection có thể được ước lượng rẻ hơn một số kế hoạch index.

Không phải cứ có index nhiều trường nhất là nó luôn thắng. Chi phí phụ thuộc số lượng document khớp, phân bố dữ liệu, tập giá trị ở field, cache, size của document/index, projection, limit, sort và khả năng index bao phủ query.

### 1.1. Index là cấu trúc dữ liệu, plan là cách sử dụng

Cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Index | Cấu trúc được tạo bằng `createIndex()` |
| Query shape | Mẫu truy vấn: filter, sort, projection, collation và những đặc điểm được planner xét |
| Candidate plan | Cách thực thi mà planner xem xét |
| Winning plan | Kế hoạch được chọn cho truy vấn trong một lần phân tích |
| Plan cache | Cơ chế lưu thông tin kế hoạch cho query shape trong điều kiện phù hợp |
| `hint` | Yêu cầu chỉ định index/collection scan thay cho lựa chọn tự động, trừ các quy tắc ưu tiên và giới hạn |
| `explain` | Trả thông tin cấu trúc plan và có thể là thống kê thực thi |

`hint` không sửa collection hoặc tạo index. Nó thay cách **một lệnh** được yêu cầu thực thi, khi cơ chế của server chấp nhận hint đó.

### 1.2. Thấy `IXSCAN` chưa đủ kết luận tốt

Một kế hoạch có `IXSCAN` có thể vẫn rất tốn kém nếu phải duyệt 900.000 key và fetch hàng trăm nghìn document để trả 20 kết quả. Ngược lại, `COLLSCAN` trên một collection 15 document trong lab có thể là lựa chọn hợp lý.

Câu hỏi không phải "có dùng index hay không?" mà là:

- Index đã thu hẹp đủ phạm vi tìm kiếm chưa?
- Có tận dụng được sort và limit không?
- Phải fetch bao nhiêu document?
- Trả về dữ liệu đúng theo query không?
- Thời gian p95/p99 dưới tải thực tế giảm hay tăng?
- Index được đề xuất có làm mỗi thao tác ghi tốn thêm bao nhiêu?

---

## 2. Cú pháp cơ bản của `cursor.hint()`

Trong mongosh, `hint()` được gọi trên cursor tạo từ `find()`.

### 2.1. Chỉ định bằng tên index

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  customerId: "CUS-101"
}).hint(
  "idx_tenant_customer"
);
~~~

Tên index là giá trị `name` lúc tạo index. Nếu không tự đặt tên, MongoDB thường tạo tên theo key pattern, ví dụ `tenantId_1_customerId_1`. Khi quản lý production, nên đặt tên rõ nghĩa để khi hint không phải dựa vào tên tự sinh khó theo dõi.

### 2.2. Chỉ định bằng key pattern

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  customerId: "CUS-101"
}).hint({
  tenantId: 1,
  customerId: 1
});
~~~

Key pattern phải tương ứng với index có thật và tuân theo ràng buộc API. Đây không phải cách để MongoDB tự sinh index `{tenantId:1, customerId:1}` nếu index ấy chưa tồn tại.

### 2.3. Kết hợp filter, projection, sort, limit và explain

~~~javascript
const result = db.orders
  .find(
    {
      tenantId: "TENANT-01",
      customerId: "CUS-101",
      status: "PAID"
    },
    {
      orderNo: 1,
      createdAt: 1,
      total: 1,
      _id: 1
    }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .hint("idx_tenant_customer_status_recent")
  .explain("executionStats");

printjson(result.queryPlanner.winningPlan);
printjson(result.executionStats);
~~~

Chú ý: **`explain()` trả thông tin plan**, không phải danh sách 20 order. Để lấy dữ liệu thật, chạy query tương ứng không gọi explain.

### 2.4. `hint()` không cần thiết cho mọi truy vấn

Query thông thường:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  customerId: "CUS-101"
});
~~~

để planner quyết định. Đây nên là **điểm bắt đầu của thí nghiệm**. Chỉ thêm hint khi có mục tiêu cụ thể, như thử một index mới hoặc tạm thời ứng phó một kế hoạch có bằng chứng suy giảm hiệu năng.

### 2.5. Hint có thể yêu cầu collection scan

Có thể dùng `$natural` để buộc quét collection theo một hướng:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).hint({
  $natural: 1
});
~~~

Hoặc:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).hint({
  $natural: -1
});
~~~

Đây là kỹ thuật hữu ích khi **so sánh index scan với collection scan**. Nó không phải lời khuyên dùng natural order để phân trang nghiệp vụ; natural order không phải hợp đồng sắp xếp theo thời gian hoặc `_id`.

Chỉ sử dụng `1` hoặc `-1` cho `$natural` theo quy tắc các phiên bản MongoDB hiện hành.

---

## 3. Thực hành: tạo bộ dữ liệu để so sánh kế hoạch

Bài dùng database lab riêng `query_plan_lab`. Các lệnh tạo collection và index; không chạy trên database production.

### 3.1. Tạo orders

~~~javascript
use query_plan_lab

db.orders.insertMany([
  {
    _id: "O-001",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    orderNo: "ORD-001",
    total: NumberDecimal("120000")
  },
  {
    _id: "O-002",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-02T09:00:00Z"),
    orderNo: "ORD-002",
    total: NumberDecimal("220000")
  },
  {
    _id: "O-003",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "NEW",
    createdAt: ISODate("2026-11-03T09:00:00Z"),
    orderNo: "ORD-003",
    total: NumberDecimal("320000")
  },
  {
    _id: "O-004",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-04T09:00:00Z"),
    orderNo: "ORD-004",
    total: NumberDecimal("420000")
  },
  {
    _id: "O-005",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "CANCELED",
    createdAt: ISODate("2026-11-05T09:00:00Z"),
    orderNo: "ORD-005",
    total: NumberDecimal("520000")
  },
  {
    _id: "O-006",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-06T09:00:00Z"),
    orderNo: "ORD-006",
    total: NumberDecimal("620000")
  },
  {
    _id: "O-007",
    tenantId: "TENANT-01",
    customerId: "CUS-102",
    status: "PAID",
    createdAt: ISODate("2026-11-07T09:00:00Z"),
    orderNo: "ORD-007",
    total: NumberDecimal("720000")
  },
  {
    _id: "O-008",
    tenantId: "TENANT-01",
    customerId: "CUS-102",
    status: "NEW",
    createdAt: ISODate("2026-11-08T09:00:00Z"),
    orderNo: "ORD-008",
    total: NumberDecimal("820000")
  },
  {
    _id: "O-009",
    tenantId: "TENANT-02",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-09T09:00:00Z"),
    orderNo: "ORD-009",
    total: NumberDecimal("920000")
  },
  {
    _id: "O-010",
    tenantId: "TENANT-02",
    customerId: "CUS-102",
    status: "NEW",
    createdAt: ISODate("2026-11-10T09:00:00Z"),
    orderNo: "ORD-010",
    total: NumberDecimal("1020000")
  },
  {
    _id: "O-011",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-11T09:00:00Z"),
    orderNo: "ORD-011",
    total: NumberDecimal("1120000")
  },
  {
    _id: "O-012",
    tenantId: "TENANT-01",
    customerId: "CUS-101",
    status: "PAID",
    createdAt: ISODate("2026-11-11T09:00:00Z"),
    orderNo: "ORD-012",
    total: NumberDecimal("1220000")
  }
]);
~~~

Tập dữ liệu có chủ ý bao gồm:

- Hai tenant khác nhau.
- Nhiều trạng thái và nhiều khách.
- Hai document `O-011`, `O-012` có cùng timestamp.
- Một query lọc nhiều field và sắp xếp theo timestamp giảm.
- Các trường `total` và `orderNo` để thấy chi phí projection/fetch.

Kiểm tra:

~~~javascript
db.orders.countDocuments({});
db.orders.find({}, { _id: 1, tenantId: 1, status: 1 })
  .sort({ _id: 1 });
~~~

### 3.2. Tạo các index ứng viên

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1
  },
  {
    name: "idx_tenant_customer"
  }
);

db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "idx_tenant_status_created"
  }
);

db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_tenant_customer_status_recent"
  }
);
~~~

Đọc lại đúng tên và key pattern:

~~~javascript
db.orders.getIndexes();
~~~

Trước khi hint index tên nào, hãy xác nhận index đó thực sự đã có. Không tự suy ra từ source code migration rằng index build trên database đang chạy đã hoàn thành.

### 3.3. Truy vấn mục tiêu

~~~javascript
const queryFilter = {
  tenantId: "TENANT-01",
  customerId: "CUS-101",
  status: "PAID"
};

const queryProjection = {
  _id: 1,
  orderNo: 1,
  createdAt: 1,
  total: 1
};

const querySort = {
  createdAt: -1,
  _id: -1
};
~~~

Chúng ta sẽ giữ **đúng cùng ba đối tượng** cho mọi lần so sánh.

---

## 4. Đo baseline: để planner tự chọn

### 4.1. Chạy explain không hint

~~~javascript
const baseline = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .explain("executionStats");

printjson(baseline.queryPlanner.winningPlan);
printjson(baseline.executionStats);
~~~

Dữ liệu lab rất nhỏ nên planner có thể chọn COLLSCAN. Điều này **không chứng minh một index bị lỗi hoặc không cần thiết**. Kết quả đáng quan tâm là cách đọc plan, không phải lấy latency của 12 document làm bằng chứng tối ưu production.

### 4.2. So candidate A: index theo tenant và customer

~~~javascript
const planA = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint("idx_tenant_customer")
  .explain("executionStats");

printjson(planA.queryPlanner.winningPlan);
printjson(planA.executionStats);
~~~

Index này hỗ trợ lọc `tenantId` và `customerId` nhưng không mang `status` hay các khóa `createdAt, _id` để phục vụ toàn bộ query. Có thể cần lọc status sau index scan và phải sắp xếp kết quả.

### 4.3. So candidate B: index theo tenant, status và thời gian

~~~javascript
const planB = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint("idx_tenant_status_created")
  .explain("executionStats");

printjson(planB.queryPlanner.winningPlan);
printjson(planB.executionStats);
~~~

Index này hỗ trợ `tenantId` và `status`, sau đó `createdAt` giảm. Nhưng vì thiếu `customerId` trong key, database có thể phải duyệt nhiều đơn của các khách khác, rồi fetch document hoặc đánh giá thêm để xác định khách cần tìm.

Ngoài ra, index này chưa có `_id` làm khóa sort phụ. Nếu cần thứ tự xác định theo `createdAt DESC, _id DESC`, không thể mặc định chỉ index theo `createdAt` đã thỏa toàn bộ sort.

### 4.4. So candidate C: index ghép sát query shape

~~~javascript
const planC = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint("idx_tenant_customer_status_recent")
  .explain("executionStats");

printjson(planC.queryPlanner.winningPlan);
printjson(planC.executionStats);
~~~

Index C đặt ba equality keys trước, rồi hai sort keys. Nó là ứng viên hợp lý cho mẫu truy vấn này. Nhưng điều đó **không bảo đảm** nó nhanh hơn mọi lựa chọn khác ở mọi tập dữ liệu — nhất là khi projection phải fetch các trường `orderNo`, `total` không có trong index, hoặc khi index lớn làm tăng cache pressure.

### 4.5. So thêm collection scan có chủ ý

~~~javascript
const collscan = db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint({ $natural: 1 })
  .explain("executionStats");

printjson(collscan.queryPlanner.winningPlan);
printjson(collscan.executionStats);
~~~

Đây là phép đối chứng để hiểu lượng công khi không dùng index. Không sử dụng `$natural` làm cơ chế phân trang ổn định theo nghiệp vụ.

### 4.6. Bảng kết quả thực nghiệm

Ghi số liệu thật từ explain của database bạn chạy:

| Phương án | Index được yêu cầu | Keys examined | Docs examined | Returned | Có sort riêng? | Execution millis |
|---|---|---:|---:|---:|---|---:|
| Baseline | Planner chọn | Đo | Đo | Đo | Quan sát | Đo |
| A | tenant + customer | Đo | Đo | Đo | Quan sát | Đo |
| B | tenant + status + created | Đo | Đo | Đo | Quan sát | Đo |
| C | tenant + customer + status + created + ID | Đo | Đo | Đo | Quan sát | Đo |
| D | `$natural:1` | Đo | Đo | Đo | Quan sát | Đo |

Không điền số đo giả vào bảng rồi coi đó là kết quả MongoDB. Có thể plan có các stage khác nhau giữa phiên bản và query engine; hãy đọc cây kế hoạch thực tế.

---

## 5. Hiểu ba mức verbosity của explain

MongoDB cung cấp các mức verbosity thường dùng:

### 5.1. `queryPlanner`

~~~javascript
db.orders.find(queryFilter)
  .explain("queryPlanner");
~~~

Chủ yếu cho biết cách planner phân tích query, thông tin winning plan và các candidate liên quan. Đây là chế độ nhẹ hơn khi muốn xem đường thực thi mà không yêu cầu thống kê chạy hoàn chỉnh như `executionStats`.

### 5.2. `executionStats`

~~~javascript
db.orders.find(queryFilter)
  .explain("executionStats");
~~~

Planner lựa chọn kế hoạch và server thực thi để trả thống kê của winning plan. Các trường hữu ích:

- `nReturned`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `executionTimeMillis`.
- Các stage và counter bên trong `executionStages`.

### 5.3. `allPlansExecution`

~~~javascript
db.orders.find(queryFilter)
  .explain("allPlansExecution");
~~~

Cung cấp thêm thông tin về các candidate plans trong giai đoạn lựa chọn. **Không hiểu các số liệu của rejected plans là benchmark hoàn chỉnh**: chúng có thể chỉ là thống kê thực thi một phần trong giai đoạn trial.

### 5.4. Phân biệt explain với plan cache

Một điểm thiết yếu: **`explain` bỏ qua các entry plan cache hiện có và không thêm winning plan vào plan cache**. Vì vậy explain rất hữu ích để kiểm tra cách planner suy luận và chi phí một lần chạy, nhưng không phản ánh đầy đủ hành vi truy vấn thường ngày khi plan cache đã nóng.

Nếu ứng dụng production có p95 cao do một query shape với cached plan kém, chỉ chạy explain một lần và thấy candidate mới tốt chưa chứng minh ứng dụng sẽ đổi sang nó ngay theo cách kỳ vọng.

Khi cần, xem thêm `$planCacheStats`, theo dõi telemetry và các cơ chế query settings của phiên bản MongoDB đang chạy. Thay đổi index (create/drop/hide) cũng có thể làm plan cache liên quan thay đổi hoặc bị làm mới.

---

## 6. Cách đọc winning plan và các bộ đếm

### 6.1. `COLLSCAN`

Stage này cho biết MongoDB quét collection. Với collection nhỏ hoặc query lấy gần như mọi document, điều đó có thể hợp lý. Trên collection lớn mà chỉ cần 20 record chọn lọc, COLLSCAN thường là dấu hiệu nên kiểm tra index.

### 6.2. `IXSCAN`

Cho biết duyệt index. Nhưng phải xem **duyệt những key nào** và **bao nhiêu key**.

Ví dụ mang tính minh họa:

~~~text
nReturned: 20
totalKeysExamined: 250000
totalDocsExamined: 80000
~~~

Một plan như vậy có thể không hiệu quả cho đường đọc chỉ lấy 20 order, dù có IXSCAN. Cần xem index bounds, equality prefix, range và phần lọc bị đẩy xuống scan.

Không dùng một tỷ lệ keys/returned cứng cho mọi query: aggregate, count hoặc một số query cố ý xử lý dữ liệu rộng có đặc điểm khác.

### 6.3. `FETCH`

Một index có thể được dùng để xác định candidate IDs nhưng server vẫn phải lấy document để:

- Kiểm tra thêm một filter không có trong index.
- Đọc các field projection chưa có trong index.
- Trả document đầy đủ cho ứng dụng.

`totalDocsExamined` giúp đánh giá lượng công tương ứng. Một **covered query** trong điều kiện phù hợp có thể trả kết quả từ index mà không fetch document, nhưng không phải mọi query chứa projection đều có thể được cover; array/multikey, collation và các điều kiện khác có thể ảnh hưởng.

### 6.4. `SORT`

Một bước sắp xếp riêng có thể xuất hiện khi index không cung cấp thứ tự cần thiết. Với tập kết quả lớn, sort có thể sử dụng đáng kể CPU, bộ nhớ hoặc disk theo chính sách server.

Nếu một index hỗ trợ cả filter và sort, planner có thể tránh bước sort riêng. Nhưng **hint một index chỉ hỗ trợ filter** không tự biến nó thành index hỗ trợ sort.

### 6.5. `indexBounds`

Đây là thông tin về khoảng key được quét trong index, tùy dạng explain. Ví dụ equality trên tenantId, customerId có thể tạo khoảng hẹp; range trên createdAt có thể tạo khoảng mở rộng.

Đọc `indexBounds` giúp trả lời:

- Những field nào thực sự thu hẹp scan?
- Có field nào không được bound dù nằm trong index?
- Query đang quét toàn bộ dải key vì thiếu equality prefix không?
- Có phải sort được thực hiện bằng thứ tự index hay phải dùng SORT stage?

### 6.6. `rejectedPlans` không đồng nghĩa kế hoạch “xấu vĩnh viễn”

Kế hoạch bị loại trong một lần lựa chọn không chứng minh index tương ứng luôn kém. Dữ liệu thay đổi, query literal khác, cache khác, server version khác hoặc điều kiện tải khác có thể khiến plan hợp lý thay đổi.

Không dùng `rejectedPlans` như danh sách index cần xóa ngay. Index có thể phục vụ query shape khác hoặc unique constraint quan trọng.

### 6.7. Hình dạng explain có thể khác nhau

MongoDB có các query engine khác nhau, ví dụ classic và slot-based execution. Các trường nội bộ và bố cục cây plan có thể khác. Không viết script giả định `winningPlan.inputStage.inputStage.stage` lúc nào cũng có, hoặc một stage luôn nằm ở một đường JSON cố định.

Ưu tiên các field thống kê cấp cao được tài liệu hỗ trợ, và đọc toàn cây plan khi cần điều tra.

---

## 7. Đề xuất index theo Equality – Sort – Range

Một index compound thường được thiết kế theo hướng **Equality – Sort – Range (ESR)**, không phải chỉ đếm số field xuất hiện trong query.

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z")
  }
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Index ứng viên:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_status_recent" }
);
~~~

Với equality trên tenant/status và sort theo createdAt/_id, index này có cấu trúc đáng kiểm chứng. Nhưng ESR là **nguyên tắc định hướng**, không phải lời giải duy nhất cho mọi mức chọn lọc; cần đo thực tế.

### 7.1. Không được bỏ qua thứ tự các field

Hai index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
{ createdAt: -1, status: 1, tenantId: 1 }
~~~

không tương đương. Thứ tự field ảnh hưởng cách index dùng equality prefix, range và sort.

### 7.2. Hướng sort cũng có ý nghĩa

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

Index với thứ tự các sort keys tương ứng có thể tránh sort riêng. Một compound index có thể hỗ trợ chiều sort đã định nghĩa hoặc chiều **đảo ngược toàn bộ** phần tương ứng, chứ không tự hỗ trợ mọi tổ hợp đảo dấu của từng field.

### 7.3. Có field lọc nhưng không có trong index

Nếu dùng index:

~~~javascript
{ tenantId: 1, createdAt: -1, _id: -1 }
~~~

mà query lọc thêm `status: "PAID"`, database vẫn có thể phải fetch/kiểm tra status cho các candidate document. Đối với tenant có nhiều order và tỷ lệ PAID thấp, chi phí này có thể cao.

Hint index trên chỉ vì nó hỗ trợ sort chưa chắc hơn index có status trong equality prefix.

### 7.4. Tìm index tối ưu cho toàn workload

Một index rất rộng:

~~~javascript
{
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1,
  orderNo: 1,
  total: 1
}
~~~

có thể giúp một query được cover trong vài điều kiện, nhưng tốn storage và chi phí ghi, đồng thời không phải query khác nào cũng dùng được prefix mong muốn.

Không tự động mở rộng index cho mọi field projection. Hãy so lợi ích đọc với:

- Dung lượng index.
- Insert/update/delete overhead.
- Cache residency.
- Số lượng index trùng lặp.
- Độ ổn định của query patterns.
- Các write-heavy workloads.

---

## 8. Quy trình so sánh nhiều index mà không thay query

### 8.1. Giữ query shape cố định

Trước khi gọi hint, cố định:

~~~javascript
const filter = {
  tenantId: "TENANT-01",
  customerId: "CUS-101",
  status: "PAID"
};

const projection = {
  _id: 1,
  orderNo: 1,
  createdAt: 1,
  total: 1
};

const sort = {
  createdAt: -1,
  _id: -1
};

const limit = 20;
~~~

Tại sao phải giữ nguyên?

Nếu một lần thử trả toàn bộ document, lần khác chỉ trả `_id`; hoặc một lần sort theo createdAt, lần khác không sort, thì bạn đang so sánh **hai yêu cầu nghiệp vụ khác nhau**, không phải chỉ so index.

### 8.2. Script minh họa chạy explain theo candidate

~~~javascript
const candidates = [
  null,
  "idx_tenant_customer",
  "idx_tenant_status_created",
  "idx_tenant_customer_status_recent"
];

for (const candidate of candidates) {
  let cursor = db.orders
    .find(filter, projection)
    .sort(sort)
    .limit(limit);

  if (candidate !== null) {
    cursor = cursor.hint(candidate);
  }

  const report = cursor.explain("executionStats");

  printjson({
    candidate: candidate || "PLANNER_DEFAULT",
    nReturned: report.executionStats.nReturned,
    totalKeysExamined: report.executionStats.totalKeysExamined,
    totalDocsExamined: report.executionStats.totalDocsExamined,
    executionTimeMillis: report.executionStats.executionTimeMillis,
    winningPlan: report.queryPlanner.winningPlan
  });
}
~~~

Script này không giả định query planner chọn index nào ở baseline. Kết quả trả về là dữ liệu kiểm chứng của server đang chạy.

**Chỉ chạy script khi index names tương ứng đã được tạo**. Nếu thiếu index, hint sẽ lỗi. Với dataset lớn, mỗi explain ở chế độ executionStats thực sự chạy truy vấn, do đó cần kiểm soát quyền và tài nguyên.

### 8.3. Đọc các chỉ số theo đúng mục đích

| Chỉ số | Câu hỏi thực tế |
|---|---|
| `nReturned` | Có trả đúng số lượng dự kiến không? |
| `totalKeysExamined` | Có phải quét quá nhiều index entry? |
| `totalDocsExamined` | Có phải fetch/kiểm tra nhiều document? |
| `IXSCAN` vs `COLLSCAN` | Đường truy xuất chính là gì? |
| `SORT` | Có bước sắp xếp riêng không? |
| `indexBounds` | Filter nào được đẩy vào index? |
| `executionTimeMillis` | Thời gian server báo cáo cho lần explain; cần đọc kèm giới hạn |
| Index size | Index mới chiếm thêm bao nhiêu disk/cache? |
| p95/p99 API latency | Người dùng có thực sự nhanh hơn dưới tải? |
| Write latency | Có bị tăng do duy trì thêm index? |

### 8.4. Luôn kiểm tra tính đúng đắn của dữ liệu

Một index đề xuất phải trả **cùng kết quả nghiệp vụ** cho cùng query, trừ các trường hợp có ghi đồng thời hoặc query vốn không định nghĩa thứ tự giữa các giá trị bằng nhau.

Khi so sánh query có sort, hãy thêm khóa phân xử để tạo thứ tự ổn định:

~~~javascript
.sort({
  createdAt: -1,
  _id: -1
});
~~~

Nếu kết quả khác giữa hint và baseline dù dữ liệu đứng yên, phải điều tra:

- Có sử dụng sparse/partial index không chứa toàn bộ tập kết quả không?
- Query có collation khác nhau không?
- Có dữ liệu không đồng nhất kiểu BSON không?
- Có projection/limit/filter bị thay đổi ngoài ý muốn không?
- Có forcing bằng `$natural` và bỏ sort nghiệp vụ không?

Không chấp nhận một kế hoạch “nhanh hơn” nếu nó trả thiếu record.

### 8.5. Không dùng một lần đo để kết luận

Trong lab nhỏ, `executionTimeMillis` thường rất thấp và khác biệt dễ do noise. Trên production, một lần explain cũng không thay thế đo ổn định dưới tải.

Quy trình đáng tin hơn:

1. Warm up dữ liệu/connection ở cả candidate.
2. Chạy lặp lại nhiều lượt ở cùng mức tải.
3. Dùng nhiều filter values đại diện, gồm tenant nhỏ/lớn.
4. Đo p50, p95, p99 và throughput.
5. Giữ write rate và concurrency tương tự production.
6. So biến động cache, index size và I/O.
7. Tách kết quả của plan selection/explain khỏi end-to-end app latency.
8. Không dùng số giả làm kết quả đo.

---

## 9. Giới hạn 1: hint chỉ dùng index tồn tại và được phép

### 9.1. Index không tồn tại

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).hint("idx_does_not_exist");
~~~

Nếu index tên này không tồn tại, operation trả lỗi. `hint` **không** yêu cầu MongoDB tạo index mới.

Thực hành:

~~~javascript
db.orders.getIndexes();
~~~

Kiểm tra tên, key pattern, collation và các thuộc tính index trước khi hint.

### 9.2. Hidden index

MongoDB hỗ trợ **hidden indexes** để loại một index khỏi các lựa chọn của query planner mà chưa cần xóa nó. Nếu hint tới hidden index, operation có thể bị từ chối.

Không làm:

~~~javascript
// Nếu index đang hidden, hint tới nó sẽ bị lỗi.
db.orders.find({ tenantId: "TENANT-01" })
  .hint("idx_hidden_candidate");
~~~

Trong quy trình thử nghiệm, muốn so tác động của việc planner không còn thấy index, hidden index là công cụ hữu ích. Nhưng:

- Hidden index vẫn có thể được duy trì khi ghi và vẫn tốn storage.
- Hidden index không tương đương drop index.
- Không thể dùng hint để "lén" ép query sử dụng hidden index.
- Khi hide/unhide có thể ảnh hưởng plan cache và hành vi của các query khác.
- Chỉ thay đổi trạng thái hidden của index trong môi trường production theo change management.

### 9.3. Time-series collection

Trên **time-series collections**, MongoDB có giới hạn riêng: khi hint index, cần chỉ định **theo tên index** thay vì key pattern trong những API/version mà tài liệu quy định.

Ví dụ ý tưởng:

~~~javascript
db.metrics.find({
  "metadata.deviceId": "SENSOR-01"
}).hint("idx_metrics_device_time");
~~~

Điều này chỉ có ý nghĩa khi time-series collection/index đã thực sự được tạo đúng và tên index có thật. Không tự dùng index key pattern của collection thông thường rồi giả định time-series được xử lý tương tự.

---

## 10. Giới hạn 2: `$text` và những query có quy tắc index đặc biệt

Với query dùng **`$text`**, MongoDB không cho dùng `hint()` để tự chỉ định một index khác cho query đó.

~~~javascript
// Minh họa truy vấn text:
db.articles.find({
  $text: {
    $search: "mongodb index"
  }
});
~~~

Đừng viết:

~~~javascript
// Đây không phải cách được hỗ trợ để ép index cho truy vấn $text.
db.articles.find({
  $text: {
    $search: "mongodb index"
  }
}).hint("idx_articles_created");
~~~

Các truy vấn toàn văn, geospatial, wildcard, hashed hoặc biểu thức đặc biệt có quy tắc hỗ trợ index riêng. `hint` không biến một index thường thành index phục vụ loại predicate mà nó không được thiết kế cho.

Ví dụ một hashed index phù hợp với những tình huống equality nhất định, nhưng không tự hỗ trợ range scan có thứ tự như một index B-tree thường. Một index tồn tại không có nghĩa nó là lựa chọn hợp lệ hoặc hiệu quả cho mọi filter/sort.

---

## 11. Giới hạn 3: sparse và partial index có thể thiếu dữ liệu

### 11.1. Sparse index

Một sparse index trên `email` thường bỏ qua document **không có field email**:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    sparse: true,
    name: "idx_sparse_email"
  }
);
~~~

Truy vấn:

~~~javascript
db.users.find({});
~~~

yêu cầu **mọi user**, kể cả user thiếu email. Nếu ép sparse index làm nguồn dữ liệu cho một query như vậy, có nguy cơ **thiếu kết quả** do những document không có index entry.

Ví dụ:

~~~javascript
// Không dùng để lấy đầy đủ users:
db.users.find({}).hint("idx_sparse_email");
~~~

Đây là lý do query planner thường không tự chọn sparse index khi nó không bao phủ đủ tập kết quả.

Đặc biệt với một phép đếm toàn bộ document, ép sparse index có thể cho số đếm khác thực tế vì các document thiếu field không nằm trong index. **Đừng đánh đổi tính đúng đắn lấy việc thấy IXSCAN.**

### 11.2. Partial index

Partial index chỉ chứa document thỏa filter:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_orders_created"
  }
);
~~~

Query phù hợp:

~~~javascript
db.orders.find({
  status: "OPEN"
}).sort({
  createdAt: -1
});
~~~

Query không đủ điều kiện sử dụng index để trả **toàn bộ** tập kết quả:

~~~javascript
db.orders.find({}).sort({
  createdAt: -1
});
~~~

Query thứ hai cần cả OPEN, PAID, CANCELED. Partial index chỉ chứa OPEN nên không đủ dữ liệu. MongoDB thông thường không dùng partial index cho query nếu điều đó tạo result set không đầy đủ.

Đừng mặc định `hint` làm cho một query thiếu điều kiện lọc trở nên hợp lệ. Tùy API/version và cách ép chỉ số, phải đặc biệt kiểm tra tính đúng đắn và quy tắc planner. Cách đúng là **thiết kế query có predicate tương thích và/hoặc tạo index phục vụ toàn bộ yêu cầu**, không dựa vào hint để bỏ qua giới hạn dữ liệu.

### 11.3. Query phải hẹp hơn hoặc bằng predicate của partial index

Với partial index:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  {
    partialFilterExpression: {
      total: { $gte: 1000000 }
    }
  }
);
~~~

Query:

~~~javascript
db.orders.find({
  total: { $gte: 2000000 }
});
~~~

yêu cầu một tập con của những document đã được index, nên có thể đủ điều kiện.

Query:

~~~javascript
db.orders.find({
  total: { $gte: 500000 }
});
~~~

cần cả document không được index, nên partial index không đủ.

### 11.4. Không ép hint khi mục tiêu là đếm hoặc export đầy đủ

Những tác vụ như:

- Đếm tất cả user.
- Export toàn bộ collection.
- Quét dữ liệu kiểm toán.
- Báo cáo kế toán cần mọi trạng thái.

đòi hỏi độ đầy đủ đặc biệt cao. Trước khi sử dụng sparse/partial index hoặc hint, phải chứng minh query filter chỉ yêu cầu đúng tập document nằm trong index.

---

## 12. Giới hạn 4: collation và thứ tự so sánh

Một index dùng collation chuyên biệt cho phép so sánh chuỗi theo một locale. Ví dụ:

~~~javascript
db.customers.createIndex(
  { fullName: 1 },
  {
    name: "idx_name_vi",
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

Query có collation tương thích:

~~~javascript
db.customers.find({
  fullName: "An"
}).collation({
  locale: "vi",
  strength: 2
}).hint("idx_name_vi");
~~~

Khi query và index khác collation, việc hint một index không tự đổi ngữ nghĩa so sánh chuỗi của query. Index có thể không cung cấp khả năng filter/sort string như kỳ vọng; server có thể cần công việc bổ sung hoặc áp dụng các giới hạn riêng.

Các điểm cần kiểm tra:

1. Collection có default collation không?
2. Index được tạo với collation gì?
3. Query có chỉ định collation không?
4. Tính duy nhất của index có phụ thuộc collation không?
5. Sort trên chuỗi có trả đúng thứ tự theo nghiệp vụ tiếng Việt không?

Một explain "dùng được index" chưa đủ nếu query trả sai thứ tự/so sánh do thiết kế collation không nhất quán.

---

## 13. Giới hạn 5: index filters và query settings có thể ưu tiên hơn hint

### 13.1. Index filters

Trong những phiên bản/cấu hình hỗ trợ **index filters**, khi query shape có một index filter áp dụng, MongoDB có thể **bỏ qua `hint()`** cho query shape đó.

Điều này có nghĩa một developer thêm:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01"
}).hint("idx_tenant_customer");
~~~

rồi thấy explain không dùng index được hint, chưa chắc đây là lỗi của cú pháp hint. Cần kiểm tra các quy tắc index filter đang áp dụng cho query shape.

Không nên kết luận mọi lệnh hint luôn có ưu tiên tuyệt đối hơn mọi cấu hình ở cluster.

### 13.2. Query settings

Ở những phiên bản MongoDB hiện đại có **query settings**, cấu hình tại cluster có thể áp đặt index hints hoặc các hạn chế theo query shape. Những cấu hình này có quy tắc ưu tiên so với hints trực tiếp trong command.

Trong trường hợp query settings đã có index hints áp dụng, server có thể bỏ qua hint do ứng dụng truyền. Phải kiểm tra công cụ và trạng thái query settings ở version đang dùng trước khi cho rằng `hint` trong code chắc chắn sẽ được thực thi.

**Phân biệt:**

| Cơ chế | Phạm vi thường gặp | Mục đích |
|---|---|---|
| `cursor.hint()` | Một query/call cụ thể | Thử hoặc chỉ định index |
| Index filter | Query shape được cấu hình | Hạn chế tập index planner xem xét |
| Query settings | Query shape/cluster theo version | Kiểm soát hành vi truy vấn ở tầng vận hành |
| Hidden index | Trạng thái của một index | Loại index khỏi lựa chọn planner, chưa drop |
| Plan cache | Các kế hoạch được cache | Giảm công chọn lại plan trong điều kiện phù hợp |

Cú pháp và mức hỗ trợ của index filters/query settings khác nhau theo phiên bản; chỉ thay đổi trong production sau khi xem tài liệu server hiện tại và có quy trình khôi phục cấu hình.

### 13.3. Hint không thay thế query settings trên toàn hệ thống

Nếu mục tiêu là giảm rủi ro một query shape chọn sai index trên hàng nghìn instance ứng dụng, dùng hint trong source code có thể tạo sự phụ thuộc khó rollback khi index bị đổi tên/drop.

Trong một số phiên bản và tình huống, query settings là lựa chọn vận hành phù hợp hơn. Nhưng không có một lựa chọn đúng cho mọi hệ thống; cần cân nhắc phạm vi thay đổi, tính sẵn có của tính năng và khả năng quan sát.

---

## 14. Hint trong aggregation

`db.collection.aggregate()` hỗ trợ option `hint` cho index của **collection đầu vào** trong những trường hợp API cho phép.

Ví dụ:

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "TENANT-01",
        status: "PAID"
      }
    },
    {
      $sort: {
        createdAt: -1,
        _id: -1
      }
    },
    {
      $limit: 20
    },
    {
      $project: {
        orderNo: 1,
        createdAt: 1,
        total: 1
      }
    }
  ],
  {
    hint: "idx_tenant_status_created"
  }
);
~~~

Lưu ý: option `hint` của aggregation áp dụng cho **collection/view ban đầu** mà pipeline chạy. Nó **không áp dụng cho các collection được truy cập trong stage `$lookup` hoặc `$graphLookup`**.

### 14.1. Không ép được index của collection join qua hint ngoài pipeline

Ví dụ:

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        tenantId: "TENANT-01"
      }
    },
    {
      $lookup: {
        from: "order_items",
        localField: "_id",
        foreignField: "orderId",
        as: "items"
      }
    }
  ],
  {
    hint: "idx_tenant_customer"
  }
);
~~~

Hint ngoài pipeline liên quan collection `orders`, **không phải** index trên `order_items`.

Muốn tăng tốc join, thường cần thiết kế index phù hợp trên foreign collection, ví dụ:

~~~javascript
db.order_items.createIndex(
  { orderId: 1 },
  { name: "idx_order_items_orderId" }
);
~~~

Sau đó đo plan/latency của toàn aggregation và từng lookup path. Không dùng `hint` trên collection đầu vào rồi kết luận foreign side đã được tối ưu.

### 14.2. Pipeline stage order cũng ảnh hưởng

Nếu `$match` có thể được áp dụng sớm, số document qua các stage sau giảm. Nếu `$sort` cần xử lý hàng triệu document sau các stage làm mất khả năng index support, việc ép index đầu vào không tự loại bỏ sort đó.

Ví dụ pipeline:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$customerId",
      totalSpent: { $sum: "$total" }
    }
  },
  {
    $sort: {
      totalSpent: -1
    }
  }
]);
~~~

Sort theo `totalSpent` là sort của **giá trị aggregate được tính**. Một index trên `total` gốc không mặc nhiên giúp trực tiếp sort theo tổng tiền mỗi khách sau `$group`.

### 14.3. Explain aggregation

~~~javascript
db.orders.explain("executionStats").aggregate(
  [
    {
      $match: {
        tenantId: "TENANT-01",
        status: "PAID"
      }
    },
    {
      $sort: {
        createdAt: -1,
        _id: -1
      }
    },
    {
      $limit: 20
    }
  ],
  {
    hint: "idx_tenant_status_created"
  }
);
~~~

Đọc cả plan truy xuất collection đầu vào và những stage của aggregation. Hình dạng explain thay đổi theo engine/version; không so một chỉ số cấp cao mà bỏ qua các stage tốn kém.

---

## 15. Hint trong driver Java và Spring Data MongoDB

### 15.1. Java Sync Driver

MongoDB Java Sync Driver hỗ trợ lựa chọn index trên `FindIterable`, thường bằng `hintString()` cho tên index hoặc `hint()` cho key pattern.

~~~java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;
import static com.mongodb.client.model.Sorts.orderBy;

public class OrderPlanExample {

    public static Document explainCandidate(
            MongoCollection<Document> orders) {

        FindIterable<Document> query = orders.find(
                and(
                    eq("tenantId", "TENANT-01"),
                    eq("customerId", "CUS-101"),
                    eq("status", "PAID")
                )
            )
            .sort(
                orderBy(
                    descending("createdAt"),
                    descending("_id")
                )
            )
            .limit(20)
            .hintString(
                "idx_tenant_customer_status_recent"
            );

        return query.explain(
            ExplainVerbosity.EXECUTION_STATS
        );
    }
}
~~~

Trong dự án thực tế, collection được lấy từ `MongoClient` đã kết nối, và query cần cùng projection với API thật để phép đo sát workload. Method/package cụ thể cần được đối chiếu với phiên bản driver đang dùng.

Nếu muốn chỉ định key pattern:

~~~java
FindIterable<Document> query = orders
    .find(eq("tenantId", "TENANT-01"))
    .hint(
        new Document("tenantId", 1)
            .append("customerId", 1)
    );
~~~

Đừng để tên index trong code phụ thuộc một migration chưa chắc đã chạy trên mọi môi trường. Nếu index không có, operation có thể lỗi và làm endpoint đang dùng hint thất bại.

### 15.2. Spring Data MongoDB

Trong Spring Data MongoDB, đối với các phiên bản hỗ trợ, `Query` có thể chỉ định tên index bằng `withHint()`.

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("tenantId").is("TENANT-01")
        .and("customerId").is("CUS-101")
        .and("status").is("PAID")
);

query.with(
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")
    )
);

query.limit(20);

query.withHint(
    "idx_tenant_customer_status_recent"
);

var orders = mongoTemplate.find(
    query,
    OrderDocument.class,
    "orders"
);
~~~

Đoạn code giả định có `mongoTemplate` và lớp entity `OrderDocument` tương ứng. Nếu entity dùng `@Field`, `@Id` hoặc custom converter, cần kiểm tra tên field thực sự trong BSON và index key.

Trong production, chỉ thêm `withHint` sau khi có bằng chứng và kế hoạch rollback. Không dùng hint như cấu hình “đảm bảo nhanh” bất chấp thay đổi dữ liệu hoặc MongoDB version.

### 15.3. Ghi log query shape thay vì log dữ liệu nhạy cảm

Khi điều tra một endpoint bị chậm, hữu ích nếu log:

- Operation/API name.
- Tenant class hoặc nhóm quy mô dữ liệu, không nhất thiết tenant ID thật.
- Query shape hoặc field filter.
- Index name được hint, nếu có.
- Latency và sample rate.
- Query comment/tracing ID khi được phép.
- MongoDB version/cluster/deployment khi so sánh.

Không tự log nguyên document và PII chỉ để chứng minh một index được dùng.

---

## 16. Khi hint cho kết quả chậm hơn: phân tích nguyên nhân

### 16.1. Index quá ít chọn lọc

Nếu query `status: "ACTIVE"` khớp 95% collection, ép index chỉ trên status có thể đòi hỏi duyệt rất nhiều key rồi fetch nhiều document, trong khi COLLSCAN có thể thuận lợi hơn trong một số tình huống.

~~~javascript
db.users.find({
  status: "ACTIVE"
}).hint({
  status: 1
});
~~~

Đừng cho rằng mọi equality predicate đều tạo index có độ chọn lọc tốt.

### 16.2. Index không hỗ trợ sort

Một index chỉ có `tenantId` có thể lọc tenant nhưng không cung cấp thứ tự `createdAt DESC, _id DESC`. Database phải sắp xếp bổ sung.

### 16.3. Index thiếu field cần đọc

Một query chỉ cần document IDs và status có thể cover bởi index phù hợp. Nhưng nếu projection yêu cầu `note` hoặc `items` rất lớn ngoài index, server phải fetch document.

Ép index chỉ vì `totalKeysExamined` thấp mà không nhìn `totalDocsExamined` có thể che giấu chi phí fetch.

### 16.4. Độ chọn lọc theo tenant khác nhau

Tenant nhỏ có 500 order, tenant lớn có 20 triệu order. Cùng một query shape có thể có hành vi chi phí rất khác theo giá trị và phân bố dữ liệu.

Khi kiểm thử hint, hãy lấy samples đại diện cho:

- Tenant nhỏ và lớn.
- Giá trị status phổ biến và hiếm.
- Khoảng thời gian hẹp và rộng.
- Trang đầu và trang sâu.
- Trường hợp limit 20 và không limit.
- Query có sort/projection khác nhau.

### 16.5. Index quá lớn làm tăng áp lực cache

Compound index chứa nhiều field có thể lớn hơn đáng kể. Khi working set index không vừa RAM/cache, query khác có thể chậm đi, dù endpoint đang kiểm thử có vẻ nhanh.

### 16.6. Write amplification

Mỗi index thêm vào collection có chi phí bảo trì khi insert/update/delete các field liên quan. Một index đề xuất phải được đánh giá trên **cả đường ghi**.

Không tối ưu một query đọc có lưu lượng thấp bằng cách tạo index nặng làm giảm throughput của hàng triệu writes.

### 16.7. Planner đã chọn index tốt hơn

Nếu planner baseline chọn index A và bạn ép index B, nhiều khả năng B không phải tốt nhất dưới dữ liệu/truy vấn hiện tại. Hãy kiểm chứng với explain và benchmark thay vì giả định planner luôn sai.

---

## 17. Khi nào nên hoặc không nên dùng hint trong production?

### 17.1. Những tình huống có thể cân nhắc

- Một query rất quan trọng có regression đã được đo và biết rõ index nào có lợi dưới workload đại diện.
- Cần một giải pháp tạm thời trong khi điều tra query planner, plan cache hoặc thay đổi dữ liệu.
- Query shape ổn định, index được quản lý bằng migration/rollout và có giám sát.
- Có cấu hình dễ rollback hint mà không phải gỡ một phần lớn code.
- Đã xác minh filter không rơi vào trường hợp sparse/partial không đầy đủ.

### 17.2. Những tình huống nên tránh

- Chưa đo baseline và không biết planner đã chọn gì.
- Index chỉ vừa được tạo nhưng chưa sẵn sàng ở toàn bộ môi trường.
- Query thay đổi thường xuyên, nhiều filter/sort tổ hợp.
- Dữ liệu có độ chọn lọc thay đổi mạnh theo tenant hoặc theo thời gian.
- Index có thể bị hide/drop/rename bởi migration.
- Truy vấn full-text hoặc time-series mà hint không tuân theo giới hạn API.
- Cần trả toàn bộ document nhưng index thưa không chứa đủ tập kết quả.
- Muốn dùng hint như cách "chữa cháy" cho thiếu index, projection quá rộng hoặc schema không phù hợp.

### 17.3. Ưu tiên sửa gốc vấn đề

Nếu index C nhanh hơn hẳn baseline:

1. Xác minh index C có thật và được planner xem xét.
2. Xem query có filter/sort đúng cách để planner chọn C không.
3. Kiểm tra index filter/query settings có ảnh hưởng không.
4. Đo trên dataset lớn, nhiều giá trị tham số.
5. Xem có thể bỏ index trùng hoặc điều chỉnh query để planner tự chọn đúng không.
6. Chỉ giữ hint lâu dài nếu có lý do được chứng minh và giám sát.

Một index được đề xuất tốt nên **được đánh giá cho toàn workload**, không chỉ chứng minh bằng một lần hint trong mongosh.

---

## 18. Đánh giá index mới như một thay đổi hệ thống

### 18.1. Đừng tạo index trong production chỉ để thử tùy tiện

Tạo index trên collection lớn có thể tiêu thụ CPU, disk I/O, cache và dung lượng. Tạo unique index còn có thể thất bại nếu dữ liệu đã có duplicate keys. Ngoài ra, việc tạo/drop/hide index có thể ảnh hưởng plan cache và các query shapes khác.

Thử nghiệm có kiểm soát nên bắt đầu bằng:

- Snapshot hoặc dataset staging đại diện.
- Thống kê phân bố dữ liệu.
- Quyền thao tác index phù hợp.
- Theo dõi tài nguyên và thời gian build.
- Kế hoạch canary/rollback.
- Biên bản index name, key pattern, collation, unique/sparse/partial properties.

### 18.2. Hiding index là một công cụ đánh giá

Đối với MongoDB phiên bản hỗ trợ hidden indexes, có thể tạm ẩn index khỏi planner để xem các query khác có cần nó không.

**Không nhầm hide index với drop index:**

- Index vẫn được lưu.
- Ghi có thể vẫn phải duy trì index.
- Query planner không chọn index đang hidden.
- Hint index hidden trả lỗi.
- Unhide sau thí nghiệm khôi phục khả năng planner xem xét index, nhưng kết quả chọn plan còn phụ thuộc dữ liệu/cache/cấu hình.

Thao tác hide/unhide là thay đổi hành vi của toàn bộ workload; chỉ thực hiện ở production khi được phê duyệt và có quan sát phù hợp.

### 18.3. Index cũ có thể phục vụ query khác

Một index A không tốt cho endpoint "recent orders" vẫn có thể:

- Phục vụ tra cứu customer.
- Hỗ trợ report theo tenant.
- Áp đặt unique constraint.
- Phục vụ sort/filter khác.
- Là thành phần quan trọng khi một index khác bị ẩn/drop.

Không xóa index chỉ vì một hint chứng minh index B tốt hơn cho một query.

### 18.4. Theo dõi index sử dụng thế nào

~~~javascript
db.orders.getIndexes();
db.orders.stats();

db.orders.aggregate([
  { $indexStats: {} }
]);
~~~

`$indexStats` cung cấp thông tin truy cập index trong một giai đoạn thống kê. Các counter có thể reset sau restart hoặc sự kiện vận hành. Index ít được truy vấn vẫn có thể cần để thực thi uniqueness. Kết hợp access stats với query logs, profiler có kiểm soát và danh mục ứng dụng trước khi quyết định drop.

---

## 19. Quy trình kiểm chứng chính thức một index được đề xuất

Một đề xuất tốt nên có đủ các thành phần sau.

### Bước 1 — Mô tả truy vấn và SLA

~~~text
Operation: GetPaidOrdersByCustomer
Filter:
  tenantId = ?
  customerId = ?
  status = PAID
Sort:
  createdAt DESC, _id DESC
Projection:
  orderNo, createdAt, total, _id
Limit:
  20
Traffic:
  lấy số đo thật
Latency target:
  p95/p99 theo SLA
Cardinality:
  phân bố đơn theo tenant/customer/status
~~~

Không viết "query đơn hàng chậm" rồi đề xuất index ngẫu nhiên.

### Bước 2 — Xác nhận index hiện có

~~~javascript
db.orders.getIndexes();
~~~

Ghi tên, key pattern, options và những index gần giống. Đừng tạo trùng nếu đã có index hỗ trợ tương đương.

### Bước 3 — Đo baseline

~~~javascript
db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .explain("executionStats");
~~~

Ghi plan, keys/docs examined, returned và sort/fetch stages.

### Bước 4 — Nêu giả thuyết index

Ví dụ:

~~~text
Candidate:
  { tenantId:1, customerId:1, status:1,
    createdAt:-1, _id:-1 }

Giả thuyết:
  Thu hẹp equality bounds theo tenant/customer/status.
  Hỗ trợ sort recent orders.
  Giảm keys/docs examined khi status không phổ biến.
  Không thêm chi phí write vượt ngưỡng đã định.
~~~

### Bước 5 — Tạo index trong môi trường thử thích hợp

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_tenant_customer_status_recent"
  }
);
~~~

### Bước 6 — So cùng query với hint

~~~javascript
db.orders
  .find(queryFilter, queryProjection)
  .sort(querySort)
  .limit(20)
  .hint("idx_tenant_customer_status_recent")
  .explain("executionStats");
~~~

So số liệu với baseline và candidate indexes khác, cùng điều kiện.

### Bước 7 — Xác minh không thiếu/sai kết quả

Đặc biệt khi có:

- Sparse/partial index.
- Collation.
- Array/multikey.
- Query sort + limit.
- Filter theo tenant/permission.
- Các document có field thiếu/null.
- Ghi đồng thời làm tập kết quả thay đổi.

Một index có vẻ nhanh hơn nhưng trả thiếu record là **không đạt**.

### Bước 8 — Benchmark end-to-end

Đo p50/p95/p99 API latency và throughput ở mức concurrency đại diện. Theo dõi CPU/RAM/disk/cache, network, write latency và replication lag. Lặp lại với nhiều tập giá trị filter.

### Bước 9 — Đánh giá tổng chi phí

So:

- Lợi ích đọc.
- Index storage.
- Build cost.
- Write amplification.
- Mức độ trùng index.
- Thay đổi trong plan cache.
- Rủi ro vận hành khi ứng dụng phụ thuộc tên index.

### Bước 10 — Triển khai và rollback

Nếu lựa chọn triển khai:

1. Tạo index và xác nhận đã sẵn sàng.
2. Canary một nhóm traffic nếu có.
3. Quan sát plan và latency thực.
4. Nếu dùng hint, cấu hình để tắt/rollback được.
5. Giám sát query regressions và chi phí write.
6. Không drop index cũ trước khi biết mọi query liên quan vẫn được đáp ứng.
7. Lưu kết quả thí nghiệm và thời điểm review lại hint/index.

---

## 20. Ma trận quyết định: sau khi thử hint nên làm gì?

| Kết quả đo | Ý nghĩa tiềm năng | Hành động |
|---|---|---|
| Planner baseline đã chọn candidate tốt | Index phù hợp và optimizer hoạt động ổn | Thường không cần hint |
| Hint candidate giảm keys/docs examined và p95 rõ rệt | Candidate có giá trị | Kiểm tra đầy đủ workload và chi phí ghi trước triển khai |
| Hint candidate nhanh hơn explain nhưng app p95 không đổi | Bottleneck có thể không ở database scan | Xem network/driver/cache/serialization |
| Hint candidate chậm hơn baseline | Index không phù hợp query/data hiện tại | Không giữ hint; phân tích bounds/sort/fetch |
| Hint sparse trả thiếu | Không bao phủ tập kết quả | Loại phương án hoặc sửa predicate/index |
| Hint index không tồn tại | Không có index được chỉ định | Kiểm tra migration/index deployment |
| Hint hidden index lỗi | Hidden index không được phép dùng | Kiểm tra trạng thái index, không ép workaround |
| Hint không được áp dụng như kỳ vọng | Có thể có index filter/query settings | Kiểm tra cấu hình và explain |
| Candidate giúp read nhưng làm write p99 tăng mạnh | Trade-off không đạt SLA | Thiết kế index khác hoặc điều chỉnh workload |
| Kết quả thay đổi mạnh giữa tenants | Distribution skew | Đánh giá thêm query shapes/độ chọn lọc và giải pháp theo workload |

Mục tiêu là chọn phương án có **tổng chi phí thấp và hành vi ổn định**, không phải cố ép một index vào mọi query.

---

## 21. Các hiểu lầm thường gặp

### “Có hint thì MongoDB luôn dùng đúng index này”

Không tuyệt đối. Index phải tồn tại và hợp lệ. Hidden index, `$text`, time-series key pattern, query settings/index filters và các giới hạn khác có thể gây lỗi hoặc thay đổi hành vi.

### “Hint tạo index nếu chưa có”

Sai. `createIndex()` mới tạo index; `hint()` chỉ định index/collection scan theo API.

### “IXSCAN nghĩa là truy vấn đã tối ưu”

Sai. Có thể quét rất nhiều keys và fetch nhiều documents. Cần nhìn `totalKeysExamined`, `totalDocsExamined`, `SORT`, latency và tính đúng đắn kết quả.

### “Hint luôn nhanh hơn để planner tự chọn”

Sai. Planner có thể chọn kế hoạch tốt hơn. Hint ép đường truy xuất không phù hợp có thể tăng CPU, I/O hoặc sort.

### “`executionTimeMillis` là latency của người dùng”

Sai. Nó không bao gồm toàn bộ network, driver, serialization và tải ứng dụng; explain còn có hành vi riêng với plan selection/cache.

### “Explain chứng minh plan cache production đang dùng gì”

Không hoàn toàn. Explain bỏ qua plan cache hiện có và không thêm entry mới. Cần quan sát đường chạy thực tế khi điều tra vấn đề cache.

### “Rejected plan không cần cho mọi query”

Sai. Một index bị loại cho một query shape có thể có giá trị cho query khác.

### “Partial index luôn phục vụ query có cùng sort key”

Sai. Query phải không yêu cầu document ngoài phạm vi index.

### “Ép sparse index để đếm toàn collection vẫn chính xác”

Không đáng tin. Sparse index thiếu document không có indexed field; forcing có thể cho kết quả thiếu.

### “Hint outer aggregation giúp `$lookup` dùng index của foreign collection”

Sai. Aggregate hint ở collection đầu vào không áp dụng cho `$lookup`/`$graphLookup`.

### “Hidden index có thể dùng bằng hint dù planner không thấy”

Sai. Hint vào hidden index bị từ chối.

### “Đổi thứ tự key trong compound index không quan trọng”

Sai. Equality prefix, sort, range và direction phụ thuộc key order.

### “Một lần benchmark dữ liệu nhỏ là đủ”

Sai. Cần distribution, concurrency, p95/p99, cache, read/write mix và nhiều lần đo.

### “Index ít được `$indexStats` truy cập nên xóa luôn”

Sai. Có thể cần cho unique constraint hoặc workload hiếm nhưng quan trọng; counter cũng có cửa sổ thống kê.

### “Đặt hint trong code rồi quên cũng không sao”

Không nên. Index có thể được đổi tên, hidden hoặc drop; phân bố dữ liệu có thể thay đổi. Hint kéo dài cần monitoring và kế hoạch review/rollback.

---

## 22. Bài tập thực hành

### Bài tập 1 — Baseline và hai candidate indexes

Từ dữ liệu `query_plan_lab`:

1. Chạy query danh sách đơn PAID của một khách, sort createdAt DESC/_id DESC, limit 20.
2. Đo explain không hint.
3. Hint `idx_tenant_customer`.
4. Hint `idx_tenant_customer_status_recent`.
5. So `totalKeysExamined`, `totalDocsExamined`, `winningPlan` và `SORT`.
6. Giải thích tại sao dữ liệu 12 document chưa đủ để chứng minh latency thực tế.

### Bài tập 2 — Hiểu indexBounds

Tạo index:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_time_lab" }
);
~~~

Chạy:

~~~javascript
db.orders.find({
  tenantId: "TENANT-01",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-05T00:00:00Z")
  }
}).hint("idx_tenant_status_time_lab")
  .explain("executionStats");
~~~

Phân tích equality bounds cho tenant/status, range trên createdAt, số key/docs examined và tác động của thêm sort theo `_id`.

### Bài tập 3 — Force collection scan

Chạy cùng query với và không có:

~~~javascript
.hint({ $natural: 1 })
~~~

Điều gì thay đổi trong winning plan? Vì sao không dùng natural order làm hợp đồng phân trang theo thời gian?

### Bài tập 4 — Hint index không tồn tại

Gọi `hint("index_missing")` trong collection lab. Ghi lại lỗi. Xây một đoạn code xử lý lỗi có khả năng phát hiện migration index chưa chạy. Vì sao một tên index hard-code có thể làm endpoint production lỗi sau đổi schema?

### Bài tập 5 — Sparse index và tính đầy đủ

Tạo:

~~~javascript
db.users.insertMany([
  { _id: 1, name: "An", email: "an@example.test" },
  { _id: 2, name: "Bình" },
  { _id: 3, name: "Chi", email: null }
]);

db.users.createIndex(
  { email: 1 },
  { sparse: true, name: "idx_lab_sparse_email" }
);
~~~

So số lượng document của:

~~~javascript
db.users.find({}).toArray();
db.users.find({}).hint("idx_lab_sparse_email").toArray();
~~~

Phân tích vì sao không được dùng sparse index ép buộc cho một query yêu cầu mọi user.

### Bài tập 6 — Partial index chỉ ACTIVE

Tạo index:

~~~javascript
db.users.createIndex(
  { score: -1 },
  {
    partialFilterExpression: { status: "ACTIVE" },
    name: "idx_lab_active_score"
  }
);
~~~

Truy vấn nào tương thích?

~~~javascript
db.users.find({ status: "ACTIVE" });
db.users.find({ status: "INACTIVE" });
db.users.find({});
~~~

Giải thích bằng tập hợp document thuộc partial index. Không mặc định hint sẽ hợp thức hóa một truy vấn không có filter phù hợp.

### Bài tập 7 — Aggregation và `$lookup`

Có collection `orders` và `order_items`. Viết pipeline `$match` theo tenant rồi `$lookup` items theo `orderId`.

- Hint index trên collection orders.
- Tạo index `{orderId:1}` trên `order_items`.
- Giải thích vì sao hint trên orders không áp dụng trực tiếp cho foreign collection.
- Đo execution plan/latency tổng thể với dữ liệu đại diện.

### Bài tập 8 — Query settings/index filter

Tìm hiểu cấu hình index filters hoặc query settings được hỗ trợ trên môi trường MongoDB đang học. Mô tả tình huống hint có thể bị bỏ qua do cấu hình áp dụng. Phân biệt một query-level hint với cluster-level settings và plan cache.

Không thay đổi query settings của production khi chưa có runbook và quyền phù hợp.

### Bài tập 9 — Java Driver

Viết hàm Java nhận `MongoCollection<Document>` và string `indexName`. Hàm chạy một query với `hintString(indexName)` và `ExplainVerbosity.EXECUTION_STATS`, in `nReturned`, `totalKeysExamined`, `totalDocsExamined`. Xử lý lỗi nếu index không tồn tại.

### Bài tập 10 — Đề xuất index production

Một collection có 20 triệu orders, 80% đã PAID, 15% CANCELED, 5% OPEN. Dashboard đọc 100 request/giây các order OPEN gần nhất của mỗi tenant, trong khi hệ thống có 500 write/giây.

Hãy:

1. Đề xuất compound index thông thường và một partial index thay thế.
2. Giải thích query nào mỗi index có thể phục vụ.
3. Lập kế hoạch đo p95/p99, key/doc examined, index size và write amplification.
4. Đánh giá có cần hint production không.
5. Xây kế hoạch canary và rollback.
6. Nêu rủi ro khi chỉ tối ưu dashboard mà quên endpoint lịch sử.

---

## 23. Câu hỏi ôn tập

1. `hint()` có vai trò gì so với query planner?
2. Khác biệt giữa hint tên index và hint key pattern?
3. `hint()` có tạo index không?
4. `hint({$natural:1})` dùng để làm gì? Vì sao không thay sort nghiệp vụ?
5. Khi nào planner có thể chọn COLLSCAN dù index tồn tại?
6. Vì sao IXSCAN chưa đủ chứng minh query tối ưu?
7. `totalKeysExamined` và `totalDocsExamined` thể hiện chi phí nào?
8. Tại sao phải xem `SORT` và `FETCH`?
9. `indexBounds` giúp hiểu điều gì?
10. Vì sao khi so index phải giữ filter/sort/projection/limit/collation giống nhau?
11. `executionStats` khác `allPlansExecution` ở đâu?
12. Explain ảnh hưởng plan cache như thế nào?
13. `executionTimeMillis` có phải latency p95 của API không?
14. Vì sao hint hidden index hoặc index không tồn tại gây lỗi?
15. Với `$text`, có thể tự ép index tùy ý không?
16. Time-series collection có giới hạn nào với cách chỉ định hint?
17. Index filter/query settings có thể ảnh hưởng hint thế nào?
18. Vì sao sparse index có thể không trả đủ kết quả của query toàn collection?
19. Partial index cần điều kiện gì để query được phục vụ đầy đủ?
20. Hint trong aggregation có tác động tới foreign side của `$lookup` không?
21. Vì sao độ chọn lọc khác nhau giữa các tenant ảnh hưởng hiệu quả index?
22. Index mới có thể làm tăng chi phí ghi như thế nào?
23. Khi nào nên tránh giữ hint lâu dài trong source code?
24. Cần những bằng chứng gì trước khi quyết định drop một index cũ?
25. Làm thế nào để rollback khi triển khai index/hint làm query production chậm hơn?

## 24. Tổng kết

`hint()` là công cụ quan trọng để **kiểm chứng một kế hoạch index được đề xuất**. Nó cho phép yêu cầu một index cụ thể bằng tên hoặc key pattern, hoặc dùng `$natural` để thử collection scan. Tuy nhiên, hint có giới hạn kỹ thuật và có thể làm query tệ hơn nếu không xét predicate, thứ tự sort, lượng dữ liệu fetch và trạng thái của index.

Quy trình đánh giá đáng tin cậy gồm:

1. **Mô tả đúng query shape và SLA.**
2. **Đọc `getIndexes()` và baseline explain không hint.**
3. **Tạo candidate index đúng workload.**
4. **Dùng hint để so plan và execution statistics trên cùng query.**
5. **Kiểm tra result set không thiếu hoặc sai.**
6. **Benchmark latency thật, concurrency và phân bố dữ liệu đại diện.**
7. **Đo index storage và write overhead.**
8. **Triển khai có canary, monitoring và rollback.**

Không biến hint thành cách cưỡng ép planner theo cảm tính. Một index nên được giữ lại khi nó **phục vụ đúng kết quả, giảm tổng chi phí ở workload thật và vẫn vận hành được khi dữ liệu hoặc hệ thống thay đổi**.

## Tài liệu MongoDB chính thức tham khảo

- [MongoDB Manual — cursor.hint()](https://www.mongodb.com/docs/manual/reference/method/cursor.hint/)
- [MongoDB Manual — db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual — Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/)
- [MongoDB Manual — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB Manual — db.collection.aggregate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.aggregate/)
- [MongoDB Manual — Query Settings](https://www.mongodb.com/docs/manual/reference/query-settings/)
- [MongoDB Manual — $planCacheStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/planCacheStats/)
- [MongoDB Manual — $indexStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [MongoDB Java Sync Driver — Explain Query Results](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/aggregation-examples/)
- [Spring Data MongoDB — Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
