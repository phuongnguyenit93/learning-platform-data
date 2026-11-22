# Thiết kế bộ index từ truy vấn thực tế và loại index trùng lặp trong MongoDB

## 1. Mục tiêu: thiết kế một bộ index, không phải một index cho mỗi trường

Một collection MongoDB có thể phục vụ nhiều đường truy cập: tìm chi tiết theo mã đơn, xem lịch sử đơn của khách, liệt kê đơn đang xử lý, lọc đơn theo giá trị và xuất báo cáo. Một index có thể giúp một hoặc nhiều truy vấn, nhưng mỗi index cũng làm tăng dung lượng lưu trữ và chi phí của insert, update, delete.

Vì vậy, câu hỏi thiết kế đúng không phải “collection này có những field nào để tạo index?”, mà là:

**Các truy vấn quan trọng nhất được thực thi như thế nào, và tập index nhỏ nhất nào hỗ trợ đủ tốt các truy vấn ấy với chi phí ghi chấp nhận được?**

Giả sử ứng dụng bán hàng có các lệnh sau:

~~~javascript
// Xem lịch sử đơn của một khách, đơn mới nhất trước.
db.orders.find({ tenantId: "t001", customerId: "c001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);

// Xem hàng đợi đơn chờ xử lý.
db.orders.find({ tenantId: "t001", status: "pending" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);

// Xem một đơn theo _id, giới hạn theo tenant.
db.orders.findOne({ _id: "o001", tenantId: "t001" });
~~~

Nếu tạo ba index đơn lẻ trên **tenantId**, **customerId**, **status**, thêm một index trên **createdAt** và một index trên **_id**, MongoDB có thể vẫn phải đọc nhiều document và sort. Một số index trở nên dư thừa khi ta tạo được các **compound index** đúng với bộ lọc và thứ tự truy vấn.

Bài này hướng dẫn một quy trình đầy đủ:

1. Ghi **access patterns** và tải đọc/ghi.
2. Chuyển từng nhóm truy vấn quan trọng thành **index candidate**.
3. Tận dụng tiền tố của compound index, thứ tự trường và quan hệ **equality–sort–range**.
4. Xác định index trùng lặp hoàn toàn, index tiền tố có khả năng dư thừa và index vẫn cần giữ.
5. Quan sát **getIndexes**, **explain**, **$indexStats** và các phép đo workload.
6. Dùng **hidden index** để đánh giá tác động trước khi bỏ một index không còn cần thiết.
7. Xóa index được xác nhận là không cần, có kế hoạch khôi phục và kiểm tra sau thay đổi.

Các số liệu tần suất trong bài là **giả định phục vụ thiết kế**. Không dùng chúng làm cam kết hiệu năng hay số liệu thực tế của hệ thống khác.

## 2. Bắt đầu bằng access patterns

### 2.1. Mô tả truy vấn dưới dạng hợp đồng

Để quyết định index, với mỗi API hoặc job cần ghi:

- **Filter:** equality, range, $in, $exists, array, $elemMatch, text search...
- **Sort:** field nào, chiều tăng/giảm, có khóa phụ để tránh kết quả không ổn định không?
- **Projection:** trả về các field nào? Có cơ hội **covered query** không?
- **Giới hạn kết quả:** limit, pagination và số lượng document trả về.
- **Tần suất:** bao nhiêu request/giây, đọc hay ghi là chủ yếu, thời điểm cao điểm?
- **Độ chọn lọc:** filter loại bỏ được bao nhiêu phần trăm document?
- **Yêu cầu toàn vẹn:** có cần unique, collation, TTL hoặc partial filter không?
- **Phạm vi dữ liệu:** toàn hệ thống hay từng tenant, thời gian lưu bao lâu?

Ví dụ bảng tải giả định cho collection **orders**:

| Mã | Nhu cầu | Filter chính | Sort / kết quả | Tải minh họa |
| --- | --- | --- | --- | --- |
| Q1 | Chi tiết đơn | _id, tenantId | Một document | 120 lượt đọc/giây |
| Q2 | Lịch sử đơn của khách | tenantId =, customerId = | createdAt DESC, _id DESC, 20 bản ghi | 60 lượt đọc/giây |
| Q3 | Hàng đợi pending | tenantId =, status = pending | createdAt DESC, _id DESC, 20 bản ghi | 45 lượt đọc/giây |
| Q4 | Danh sách tất cả đơn của tenant | tenantId = | createdAt DESC, _id DESC, 20 bản ghi | 15 lượt đọc/giây |
| Q5 | Báo cáo đơn theo khoảng tiền | tenantId =, total từ A đến B | Không bắt buộc sort, tổng hợp | 2 lượt đọc/giây |
| Q6 | Kiểm tra orderNo duy nhất | tenantId, orderNo | Một document/insert kiểm tra ràng buộc | Gắn với ghi đơn |
| Q7 | Ghi/chuyển trạng thái đơn | _id, status cũ | Update một document | 40 lượt ghi/giây |

Các ký hiệu dấu **=** biểu thị điều kiện equality. Trong thực tế, cần đo **p95/p99 latency**, số document quét, số index key quét, tỷ lệ lỗi, chi phí ghi và dung lượng index. Một truy vấn hiếm nhưng có SLA đặc biệt vẫn có thể cần index riêng; không phải lúc nào cũng ưu tiên đơn thuần theo tần suất.

### 2.2. Vì sao không tạo index theo từng field?

Giả sử Q2 lọc bằng tenantId/customerId và sort createdAt:

~~~javascript
{ tenantId: "t001", customerId: "c001" }
// sort: { createdAt: -1, _id: -1 }
~~~

Ba index đơn:

~~~javascript
{ tenantId: 1 }
{ customerId: 1 }
{ createdAt: -1 }
~~~

không tương đương một compound index:

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }
~~~

Với compound index, MongoDB có thể thu hẹp theo các giá trị equality rồi đọc theo thứ tự đã được lập index, giảm nhu cầu sort riêng. MongoDB có thể sử dụng **index intersection** trong một số trường hợp, nhưng không nên xem intersection là phương án mặc định tốt ngang một compound index được thiết kế đúng workload.

## 3. Nguyên tắc thiết kế compound index

### 3.1. Tiền tố của index

Giả sử có index:

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }
~~~

Những tiền tố khóa (key prefixes) của nó gồm:

~~~text
{ tenantId: 1 }
{ tenantId: 1, customerId: 1 }
{ tenantId: 1, customerId: 1, createdAt: -1 }
{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }
~~~

Do đó, một index compound có thể phục vụ những truy vấn dùng **tiền tố bên trái** mà không cần index riêng đúng bằng tiền tố ấy, với điều kiện semantics của index tương thích.

Ví dụ:

~~~javascript
db.orders.find({ tenantId: "t001" });
db.orders.find({ tenantId: "t001", customerId: "c001" });
~~~

có thể dùng tiền tố của index trên. Nhưng:

~~~javascript
db.orders.find({ customerId: "c001" });
~~~

không dùng được tiền tố tenantId vì thiếu trường đầu; MongoDB đôi khi vẫn có thể scan index trong một số kế hoạch, nhưng thường kém hiệu quả hơn index có customerId ở đầu khi đây là truy vấn chủ đạo.

Quan trọng hơn, index:

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1 }
~~~

**không bảo đảm sort createdAt theo toàn tenant** nếu query chỉ lọc tenantId mà **không** ràng buộc customerId. Các khóa trong index được nhóm theo customerId trước, nên createdAt không có thứ tự toàn cục phù hợp khi qua nhiều khách khác nhau.

### 3.2. Quy tắc ESR: Equality, Sort, Range

Với nhiều truy vấn, một thứ tự khởi đầu hữu ích cho compound index là:

1. **E – Equality:** các trường lọc bằng giá trị xác định.
2. **S – Sort:** những trường phục vụ thứ tự kết quả.
3. **R – Range:** các điều kiện khoảng như lớn hơn, nhỏ hơn.

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "t001",
  status: "pending",
  createdAt: { $gte: ISODate("2026-02-01T00:00:00.000Z") }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Một index ứng viên:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
~~~

Ở đây tenantId và status là equality, createdAt vừa là range vừa là khóa sort đầu. Index có thể thu hẹp theo equality rồi quét một khoảng createdAt theo chiều cần thiết.

**ESR là điểm khởi đầu, không phải luật bất biến.** Với truy vấn có range rất chọn lọc, đặt range trước field sort (ERS) đôi khi hiệu quả hơn vì giảm mạnh số document ứng viên, dù phải chấp nhận SORT. Cần đo latency, totalKeysExamined, totalDocsExamined và sort trên dữ liệu thật.

### 3.3. Chọn chiều sort phù hợp

Index:

~~~javascript
{ tenantId: 1, createdAt: -1, _id: -1 }
~~~

sau khi lọc equality tenantId có thể hỗ trợ:

~~~javascript
.sort({ createdAt: -1, _id: -1 })
~~~

và có thể scan ngược để hỗ trợ:

~~~javascript
.sort({ createdAt: 1, _id: 1 })
~~~

Nhưng sort:

~~~javascript
.sort({ createdAt: -1, _id: 1 })
~~~

có hướng kết hợp khác, nên không mặc định được hỗ trợ bằng cùng thứ tự index. Khi chọn index cho sort nhiều trường, hướng các thành phần và khả năng quét ngược toàn bộ đều quan trọng.

### 3.4. Không tạo index chỉ để tránh một sort hiếm

Một báo cáo tháng lọc đơn theo total, tổng hợp theo customer rồi xuất dữ liệu có thể có thiết kế khác màn hình hiển thị 20 đơn mới nhất. Nếu tạo một index riêng cho mọi phép sort ít gặp, chi phí index có thể lớn hơn lợi ích.

Khi ưu tiên index, hãy xét:

- Truy vấn này chạy bao nhiêu lần và SLA là gì?
- Mỗi lần đọc bao nhiêu document, trả bao nhiêu document?
- Có thể giải quyết bằng index đã có với chi phí chấp nhận được không?
- Có thể chuyển báo cáo nặng sang tiến trình nền, biểu diễn tổng hợp hoặc khoảng thời gian cố định không?
- Chi phí index mới tác động ra sao đến mọi lần ghi?

## 4. Dựng lab mongosh: cùng một workload, nhiều index ứng viên

Ta xây một collection đơn hàng có dữ liệu cố định và một vài index **cố ý chồng lấn**. Sau đó đọc explain, phân biệt index cần giữ và index có khả năng dư thừa.

### 4.1. Bộ dữ liệu

Database: **mongo_index_design_lab**.

Collection: **lab_orders**.

Mọi document của bài có **dataset: "index-design-v1"**.

Chạy trong mongosh:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_index_design_lab");
  const orders = lab.getCollection("lab_orders");
  const tag = "index-design-v1";

  // Chỉ dọn dữ liệu của bài, không drop database hoặc collection.
  orders.deleteMany({ dataset: tag });

  const raw = [
    ["o001", "t001", "c001", "pending",   "2026-02-01T08:00:00Z", "250.00"],
    ["o002", "t001", "c001", "paid",      "2026-02-02T09:00:00Z", "100.00"],
    ["o003", "t001", "c002", "pending",   "2026-02-03T10:00:00Z", "300.00"],
    ["o004", "t001", "c001", "shipped",   "2026-02-04T11:00:00Z", "420.00"],
    ["o005", "t001", "c003", "paid",      "2026-02-05T12:00:00Z", "150.00"],
    ["o006", "t001", "c001", "pending",   "2026-02-06T13:00:00Z", "190.00"],
    ["o007", "t001", "c002", "cancelled", "2026-02-07T14:00:00Z", "270.00"],
    ["o008", "t001", "c003", "pending",   "2026-02-08T15:00:00Z", "360.00"],
    ["o009", "t002", "c004", "pending",   "2026-02-09T16:00:00Z", "500.00"],
    ["o010", "t002", "c004", "paid",      "2026-02-10T17:00:00Z", "200.00"],
    ["o011", "t001", "c001", "paid",      "2026-02-11T18:00:00Z", "110.00"],
    ["o012", "t001", "c002", "pending",   "2026-02-12T19:00:00Z", "280.00"]
  ];

  const documents = raw.map(([id, tenantId, customerId, status, date, total]) => ({
    _id: id,
    dataset: tag,
    tenantId: tenantId,
    customerId: customerId,
    status: status,
    orderNo: "SO-" + id.substring(1),
    createdAt: ISODate(date),
    total: NumberDecimal(total),
    items: [
      { sku: "SKU-" + id.substring(1), quantity: NumberInt(1) }
    ]
  }));

  orders.insertMany(documents);

  // Q2: lịch sử đơn theo khách.
  orders.createIndex(
    {
      dataset: 1, tenantId: 1, customerId: 1,
      createdAt: -1, _id: -1
    },
    { name: "ix_customer_recent" }
  );

  // Index tiền tố cố ý chồng lấn với ix_customer_recent.
  orders.createIndex(
    { dataset: 1, tenantId: 1, customerId: 1 },
    { name: "ix_customer_short" }
  );

  // Q3: hàng đợi xử lý theo status.
  orders.createIndex(
    {
      dataset: 1, tenantId: 1, status: 1,
      createdAt: -1, _id: -1
    },
    { name: "ix_queue_recent" }
  );

  // Index tiền tố cố ý chồng lấn với ix_queue_recent.
  orders.createIndex(
    { dataset: 1, tenantId: 1, status: 1 },
    { name: "ix_queue_short" }
  );

  // Q4: mọi đơn trong tenant theo thời gian, không lọc customerId/status.
  orders.createIndex(
    { dataset: 1, tenantId: 1, createdAt: -1, _id: -1 },
    { name: "ix_tenant_recent" }
  );

  // Q5: lọc giá trị đơn. Phục vụ truy vấn khác sort lịch sử.
  orders.createIndex(
    { dataset: 1, tenantId: 1, total: 1 },
    { name: "ix_tenant_total" }
  );

  // Q6: bắt buộc orderNo duy nhất trong tenant.
  orders.createIndex(
    { tenantId: 1, orderNo: 1 },
    { name: "ux_tenant_order_number", unique: true }
  );

  printjson({
    total: orders.countDocuments({ dataset: tag }),
    tenant001: orders.countDocuments({
      dataset: tag, tenantId: "t001"
    }),
    indexes: orders.getIndexes().map(index => index.name)
  });
})();
~~~

**Kết quả mong đợi:** 12 document, trong đó tenant **t001** có 10 document. Index mặc định **_id_** có sẵn. Các index **ix_customer_short** và **ix_queue_short** được tạo **cố ý** để luyện tập phát hiện trùng tiền tố; không phải khuyến nghị giữ chúng trong production.

Vì script dùng ID cố định, chạy lại có thể đưa dữ liệu bài về trạng thái ban đầu sau khi có thao tác sửa/xóa trong lab. Nó không drop database hay các index khác; không dùng để làm sạch collection sản xuất.

### 4.2. Xem index hiện có

~~~javascript
const orders = db.getSiblingDB("mongo_index_design_lab")
  .getCollection("lab_orders");

printjson(orders.getIndexes());
~~~

Mỗi phần tử kết quả thường chứa:

- **name:** tên index.
- **key:** thứ tự field và hướng index.
- **unique**, **partialFilterExpression**, **sparse**, **expireAfterSeconds**, **collation** hoặc những option khác nếu có.
- **hidden:** trạng thái hidden trong những phiên bản hỗ trợ.

Đừng nhìn mỗi field đầu của index để kết luận hai index trùng nhau: các option như unique, partial filter, sparse và collation có thể làm thay đổi **ngữ nghĩa**, không chỉ hiệu năng.

## 5. Ánh xạ từ query thực tế sang bộ index

### 5.1. Q1: tìm theo _id

~~~javascript
orders.findOne({
  _id: "o001",
  dataset: "index-design-v1",
  tenantId: "t001"
});
~~~

MongoDB tự tạo **unique index _id_** cho collection thông thường. Tìm theo _id thường có thể sử dụng index mặc định; thêm điều kiện tenantId vẫn cần thiết để bảo vệ phạm vi nghiệp vụ nhưng không có nghĩa phải lập một compound index riêng cho từng query _id/tenantId.

Không tạo thêm **{ _id: 1 }** với tên khác chỉ để tối ưu truy vấn đã có _id index. _id phải phù hợp với hợp đồng định danh của ứng dụng; nếu dùng chuỗi cho lab thì filter dùng chuỗi, nếu dùng ObjectId thì filter phải dùng ObjectId tương ứng.

### 5.2. Q2: lịch sử đơn của khách

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001",
    customerId: "c001"
  },
  { _id: 1, orderNo: 1, status: 1, createdAt: 1, total: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.toArray();
~~~

**Kết quả mong đợi:** **o011, o006, o004** theo thời gian giảm dần. Index **ix_customer_recent** khớp equality theo dataset/tenant/customer rồi các field sort, nên là ứng viên tự nhiên cho query này.

Index ngắn **ix_customer_short** có cùng ba trường đầu nhưng **không chứa createdAt/_id để hỗ trợ thứ tự**. Nếu planner chọn index ngắn, có thể phải sort thêm. Vì vậy, index ngắn là **ứng viên loại bỏ** khi index dài vẫn phục vụ tốt những query chỉ lọc theo tiền tố.

### 5.3. Q3: hàng đợi pending

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001",
    status: "pending"
  },
  { _id: 1, customerId: 1, createdAt: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.toArray();
~~~

**Kết quả mong đợi:** **o012, o008, o006**.

Index **ix_queue_recent** phục vụ mẫu lọc theo status rồi sort. Index **ix_queue_short** là tiền tố của nó và có thể bị loại nếu không mang lại lợi ích riêng đáng kể.

Không dùng ix_customer_recent thay cho ix_queue_recent chỉ vì hai index đều bắt đầu bằng dataset/tenantId: sau tenantId, một index sắp theo customerId, một index sắp theo status. Trường nằm giữa ảnh hưởng việc chọn lọc và thứ tự kết quả.

### 5.4. Q4: danh sách mọi đơn của tenant

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001"
  },
  { _id: 1, createdAt: 1, status: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.toArray();
~~~

**Kết quả mong đợi:** **o012, o011, o008**.

Tại sao cần **ix_tenant_recent** dù đã có ix_customer_recent và ix_queue_recent? Vì query **không** ràng buộc customerId hoặc status. Trong hai index kia, createdAt xuất hiện **sau** customerId hoặc status nên không có thứ tự createdAt chung cho toàn bộ tenant. Index chuyên **{dataset, tenantId, createdAt, _id}** có tác dụng khác, không phải trùng tiền tố vô nghĩa.

### 5.5. Q5: khoảng tổng tiền

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001",
    total: {
      $gte: NumberDecimal("150.00"),
      $lte: NumberDecimal("300.00")
    }
  },
  { _id: 1, total: 1, status: 1 }
).sort({ total: 1 }).toArray();
~~~

**Kết quả mong đợi:** **o005, o006, o001, o007, o012, o003** theo total tăng dần. Index **ix_tenant_total** có các trường equality trước rồi đến giá trị range/sort.

Nếu Q5 hiếm gặp và bộ index đã quá tốn kém, có thể đánh giá việc không giữ index chuyên biệt này; quyết định phụ thuộc dữ liệu và SLA. Không có lý do tự động rằng mọi field dùng trong filter đều phải có index.

### 5.6. Q6: uniqueness là ràng buộc, không chỉ tối ưu

~~~javascript
orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { name: "ux_tenant_order_number", unique: true }
);
~~~

Index này bảo đảm cặp tenantId/orderNo không trùng **giữa các document**, theo semantics của MongoDB và dữ liệu hợp lệ. Việc nó có thể được dùng để tìm đơn theo orderNo không làm mất vai trò **ràng buộc nghiệp vụ**.

**Không được loại unique index** chỉ vì một non-unique index khác có cùng tiền tố hoặc một phần các trường. Làm vậy có thể khiến duplicate orderNo được ghi vào collection. Khi thiết kế multi-tenant, các index unique còn phải xét dữ liệu thiếu/null, sharding và phạm vi uniqueness thực tế.

## 6. Đọc explain để xác minh một index có phục vụ query hay không

### 6.1. executionStats và các chỉ số cần quan sát

~~~javascript
orders.find({
  dataset: "index-design-v1",
  tenantId: "t001",
  customerId: "c001"
})
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.explain("executionStats");
~~~

Các điểm quan trọng:

| Thuộc tính / stage | Cách hiểu |
| --- | --- |
| **winningPlan** | Kế hoạch MongoDB chọn cho truy vấn |
| **IXSCAN** | Đọc entry của một index |
| **indexName** | Index cụ thể được scan |
| **indexBounds** | Khoảng khóa được scan cho từng field |
| **FETCH** | Đọc document thật để trả field hoặc kiểm tra filter còn lại |
| **SORT** | Có bước sort blocking thay vì hoàn toàn dùng thứ tự index |
| **COLLSCAN** | Quét collection |
| **nReturned** | Số document trả về |
| **totalKeysExamined** | Số khóa index được xem xét |
| **totalDocsExamined** | Số document được xem xét |
| **executionTimeMillis** | Thời gian thực thi được báo trong explain; không thay thế phân bố latency thực tế |

**Đừng kết luận một index tốt chỉ vì thấy IXSCAN.** Nếu truy vấn trả 20 document mà quét 200.000 key và 50.000 document, cần tìm hiểu vì sao. Ngược lại, với 12 document lab, COLLSCAN có thể rẻ hơn index scan; đó không phải chứng cứ index được thiết kế sai.

### 6.2. So sánh hai ứng viên bằng hint trong lab

~~~javascript
const query = {
  dataset: "index-design-v1",
  tenantId: "t001",
  customerId: "c001"
};
const sorting = { createdAt: -1, _id: -1 };

print("Index dài:");
printjson(
  orders.find(query)
    .sort(sorting)
    .limit(3)
    .hint("ix_customer_recent")
    .explain("executionStats")
);

print("Index ngắn:");
printjson(
  orders.find(query)
    .sort(sorting)
    .limit(3)
    .hint("ix_customer_short")
    .explain("executionStats")
);
~~~

Hãy quan sát stage SORT và sự khác nhau về indexBounds. Index dài có thể cung cấp thứ tự createdAt/_id theo customer; index ngắn chỉ lọc theo ba equality field và có thể cần SORT. Trong lab ít document, chênh lệch tuyệt đối là rất nhỏ.

**hint là công cụ thí nghiệm, không phải lời khuyên ép index trong production.** Việc ép dùng một index có thể ngăn planner chọn kế hoạch tốt hơn khi phân bố dữ liệu thay đổi.

### 6.3. Covered query có thể giúp giảm FETCH

Một query có thể được giải quyết từ index nếu các field filter và projection đều được đáp ứng mà không phải đọc document gốc, trong giới hạn semantics của index. Ví dụ dùng ix_customer_recent:

~~~javascript
orders.find(
  {
    dataset: "index-design-v1",
    tenantId: "t001",
    customerId: "c001"
  },
  { _id: 0, tenantId: 1, customerId: 1, createdAt: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.hint("ix_customer_recent")
.explain("executionStats");
~~~

Projection bỏ _id nhưng index có _id ở cuối để hỗ trợ sort. Nếu tất cả điều kiện cần thiết đều thỏa, MongoDB có thể tránh FETCH. Nếu projection có **status**, **total** hoặc **orderNo**, index này không chứa các field đó nên thường phải đọc document.

Không tự thêm mọi field cần hiển thị vào index để cố đạt covered query: index càng rộng càng tốn lưu trữ, RAM và chi phí ghi. Quyết định dựa trên query cực kỳ quan trọng và chênh lệch đo được.

## 7. Phân loại index chồng lấn và trùng lặp

### 7.1. Trùng khóa hoàn toàn

Hai định nghĩa:

~~~javascript
{ tenantId: 1, status: 1 }
{ tenantId: 1, status: 1 }
~~~

có cùng key pattern. MongoDB thường không cho tạo hai index giống hệt nhau chỉ bằng cách đặt tên khác; các option và phiên bản server vẫn cần được xét. Vì vậy, trong thực tế tình trạng phổ biến hơn là **nhiều index chồng lấn/tiền tố**, không phải hai index y hệt.

Không đánh giá trùng lặp chỉ bằng tên index. Tên giống nhau trên collection khác là chuyện bình thường; ngược lại, tên khác nhau không chứng minh hai index có tác dụng khác nhau.

### 7.2. Trùng tiền tố: ứng viên có thể loại bỏ

Trong lab:

~~~javascript
// A: index ngắn.
{ dataset: 1, tenantId: 1, customerId: 1 }

// B: index dài có A ở tiền tố.
{
  dataset: 1, tenantId: 1, customerId: 1,
  createdAt: -1, _id: -1
}
~~~

Index B có thể hỗ trợ các truy vấn chỉ lọc theo ba field đầu, đồng thời hỗ trợ sort createdAt/_id. Do đó A là một **ứng viên dư thừa**.

Nhưng **“index A là tiền tố của B” không đồng nghĩa “luôn an toàn xóa A”**. Cần xem:

- Index A có **unique**, **sparse**, **partialFilterExpression**, **collation** hoặc option đặc biệt khác không?
- Có truy vấn cực kỳ phổ biến chỉ cần A và nhanh hơn đáng kể nhờ index ngắn/nhỏ không?
- Có workload ghi nhiều khiến giữ B nhưng bỏ A cải thiện write latency rõ rệt không?
- Có query bị ảnh hưởng khi thiếu A mà chưa được liệt kê trong access patterns không?
- Planner đã chọn A/B ra sao trên tải dữ liệu đại diện?

Trong nhiều tình huống, index ngắn không còn đáng giữ nếu index dài thay thế tốt các query của nó. Nhưng kết luận phải dựa trên **bằng chứng từ workload**, không chỉ phép so sánh khóa.

### 7.3. Hai index có cùng tiền tố không nhất thiết trùng

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1 }
{ tenantId: 1, status: 1, createdAt: -1 }
{ tenantId: 1, createdAt: -1 }
~~~

Ba index này phục vụ ba pattern:

- Lịch sử đơn **theo khách**.
- Hàng đợi đơn **theo trạng thái**.
- Toàn bộ đơn **của tenant** theo thời gian.

Điểm giống nhau chỉ là tenantId ở đầu. Không thể bỏ index thứ ba bằng lập luận “đã có tenantId và createdAt trong hai index khác” vì customerId/status nằm giữa và ngăn đảm bảo thứ tự createdAt chung cho tenant.

### 7.4. Chiều index không luôn tạo nhu cầu thêm index mới

Nếu index:

~~~javascript
{ tenantId: 1, createdAt: -1, _id: -1 }
~~~

đã hỗ trợ sort createdAt/_id giảm dần sau equality tenantId, scan ngược có thể hỗ trợ sort cùng hai field tăng dần. Không tự tạo thêm index thứ hai:

~~~javascript
{ tenantId: 1, createdAt: 1, _id: 1 }
~~~

chỉ để đảo toàn bộ hai chiều sort; nên xác nhận khả năng scan ngược qua explain. Tuy nhiên sort hỗn hợp khác như createdAt giảm dần nhưng _id tăng dần không nhất thiết được đáp ứng bởi cùng index.

### 7.5. Những index nhìn giống nhưng khác semantics

| Khác biệt | Vì sao không tự loại bỏ? |
| --- | --- |
| **unique** so với không unique | Unique bảo vệ tính duy nhất của khóa |
| **partial index** so với full index | Partial chỉ chứa document khớp filter; có thể dùng cho tập truy vấn khác |
| **sparse** so với non-sparse | Sparse bỏ document thiếu key; khác hành vi và khả năng phục vụ query |
| **collation** khác nhau | So sánh, sắp xếp và case/accent sensitivity có thể khác |
| **TTL** với expireAfterSeconds | TTL thực thi chính sách tự động xóa, không chỉ tăng tốc lọc |
| **text, geospatial, hashed, wildcard** | Có semantics và khả năng truy vấn đặc biệt |
| **hidden** so với visible | Hidden không được planner chọn, nhưng vẫn phải duy trì index khi ghi |
| **multikey** trên field Array | Cần xét giới hạn mảng, index bounds, covered query và sort |

Không loại bỏ một index vì “chưa thấy query dùng” nếu index đó là **ràng buộc dữ liệu** hoặc **cơ chế retention**. Những thứ này có giá trị vượt ra ngoài một query plan.

### 7.6. Index intersection không phải lý do giữ mọi index đơn lẻ

MongoDB có thể sử dụng nhiều index để xử lý một query qua **index intersection** trong những trường hợp thích hợp. Tuy vậy:

- Planner không cam kết luôn chọn intersection.
- Intersection không mặc nhiên cung cấp thứ tự sort mong muốn.
- Chi phí kết hợp candidate IDs có thể cao hơn một compound index.
- Các index đơn lẻ vẫn phải được cập nhật ở mỗi lần ghi.

Nếu query theo tenant/status/sort createdAt là đường nóng, một compound index chuyên biệt thường là ứng viên tốt hơn việc tạo ba index đơn rồi chờ planner giao chúng. Cần kiểm chứng bằng explain.

## 8. Đo index nào đang được sử dụng bằng $indexStats

### 8.1. Truy vấn thống kê truy cập index

MongoDB cung cấp aggregation stage **$indexStats**:

~~~javascript
db.getSiblingDB("mongo_index_design_lab")
  .getCollection("lab_orders")
  .aggregate([
    { $indexStats: {} }
  ]).toArray();
~~~

Kết quả có thông tin như tên index, máy chủ/shard, và số **accesses.ops** kể từ mốc được báo trong **accesses.since**. Đây là số liệu quan sát được ở một môi trường/chặng thời gian, không phải lời cam kết rằng index sẽ không còn cần trong tương lai.

### 8.2. Đọc số liệu đúng ngữ cảnh

| Quan sát | Cách diễn giải |
| --- | --- |
| Index có nhiều accesses.ops | Có workload đã sử dụng index này; cần biết query nào và hiệu quả ra sao |
| Index có accesses.ops = 0 | Chưa ghi nhận lần dùng trong giai đoạn quan sát; **chưa đủ để kết luận vô dụng** |
| Index ít dùng trong ngày | Có thể chỉ dành cho báo cáo tuần/tháng hoặc khắc phục sự cố |
| Chỉ số tăng ở một node | Node/shard khác có thể có workload khác |
| Trước/sau restart thấy số liệu thay đổi | Bộ đếm không phải lịch sử vĩnh viễn; phải xét accesses.since |
| Khi chạy explain không thấy access counter tăng | Explain không nên được dùng như nguồn đo usage thực tế thông thường |

Khi phân tích production, lấy thống kê **qua toàn bộ chu kỳ workload phù hợp**: giờ cao điểm, tác vụ cuối ngày, cuối tháng, báo cáo định kỳ và các luồng ít gặp nhưng quan trọng. Nếu có replica set hoặc sharded cluster, phải kiểm tra phạm vi thu thập, node và vai trò của từng nơi, không dựa vào một snapshot đơn lẻ.

### 8.3. Không dùng $indexStats thay explain

**$indexStats** trả lời: “Index đã được sử dụng bao nhiêu lần trong khoảng quan sát?”.

**explain("executionStats")** trả lời: “Truy vấn này, với filter/sort/projection này, đã dùng kế hoạch gì và quét bao nhiêu key/document?”.

Hai câu hỏi đều quan trọng. Một index có nhiều accesses.ops nhưng luôn tạo plan kém vẫn có thể cần điều chỉnh; một index chưa được dùng tuần này nhưng giữ unique constraint thì không thể xóa vì usage thấp.

## 9. Quy trình loại index trùng lặp có kiểm soát

Một index dư thừa có thể được loại bỏ để giảm dung lượng và chi phí ghi, nhưng **dropIndex là thay đổi vận hành có tác động lên cả collection**. Không nên thử trực tiếp trên production chỉ vì một ví dụ lab cho thấy index có cùng tiền tố.

### 9.1. Bước 1 — Chụp lại định nghĩa hiện tại

Trong lab:

~~~javascript
const lab = db.getSiblingDB("mongo_index_design_lab");
const orders = lab.getCollection("lab_orders");

printjson(orders.getIndexes());
~~~

Khi làm trên hệ thống thật, lưu cấu hình index ở nơi quản lý phiên bản/migration và đối chiếu với các quyền, unique, partial, collation, TTL và thay đổi từ các dịch vụ khác. Phải có đủ thông tin để **tạo lại đúng index** nếu phát hiện lỗi sau khi bỏ.

### 9.2. Bước 2 — Xác định ứng viên từ tiền tố

Trong bài, có hai cặp:

~~~text
ix_customer_short
   -> là tiền tố của ix_customer_recent

ix_queue_short
   -> là tiền tố của ix_queue_recent
~~~

Đây là hai **ứng viên**, chưa phải hai index đã chứng minh an toàn để xóa. Cần liệt kê toàn bộ query sử dụng customer/status, so sánh plan và đánh giá query có độ trễ nghiêm ngặt.

### 9.3. Bước 3 — Quan sát bằng explain và statistics

Ví dụ tập query sử dụng customer:

~~~javascript
const historyFilter = {
  dataset: "index-design-v1",
  tenantId: "t001",
  customerId: "c001"
};

printjson(
  orders.find(historyFilter)
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .explain("executionStats")
);

printjson(
  orders.find(historyFilter)
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_customer_recent")
    .explain("executionStats")
);
~~~

Nếu planner hiện chọn ix_customer_short cho truy vấn chỉ lọc customer, cần đánh giá truy vấn đó khi chỉ còn ix_customer_recent. Nếu có query liên quan khác, thêm chúng vào bộ kiểm thử/giám sát; không tối ưu một query mẫu và bỏ qua toàn bộ ứng dụng.

### 9.4. Bước 4 — Hide một index để thử tác động của việc không chọn nó

MongoDB hỗ trợ **hidden index** trên những phiên bản phù hợp (từ MongoDB 4.4). Index hidden **không được query planner sử dụng**, nhưng MongoDB vẫn **duy trì index khi insert/update/delete**.

Trong lab:

~~~javascript
orders.hideIndex("ix_customer_short");

printjson(
  orders.find({
    dataset: "index-design-v1",
    tenantId: "t001",
    customerId: "c001"
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
  .explain("executionStats")
);
~~~

Khi index ngắn bị hidden, planner phải chọn kế hoạch khác, ví dụ index dài ix_customer_recent. Đây là cơ hội so sánh tính đúng đắn và độ trễ khi không có ứng viên ngắn. **Không cần drop ngay** để thử việc planner không dùng index đó.

Điểm cần nhấn mạnh:

- Hide index là thay đổi **ở cấp collection**, ảnh hưởng các query khác, không chỉ phiên mongosh của người thực hiện.
- Hidden index **vẫn chiếm dung lượng và chi phí ghi**, nên hide không đo trực tiếp toàn bộ lợi ích về write performance của drop.
- Planner không dùng hidden index, và không thể hint tới index hidden như index khả dụng.
- Không thể hide index **_id_**.
- Nếu phát hiện regression, có thể **unhide** để planner cân nhắc lại index trước khi thực hiện drop.

### 9.5. Bước 5 — Unhide hoặc drop

Nếu muốn khôi phục index đang thử:

~~~javascript
orders.unhideIndex("ix_customer_short");
~~~

Nếu đã xác nhận đủ bằng chứng rằng index ngắn không cần thiết, có thể xóa **đúng index có tên cụ thể** trong môi trường lab:

~~~javascript
// Chỉ thực hiện sau khi đã xác nhận collection và tên index của lab.
const lab = db.getSiblingDB("mongo_index_design_lab");
const orders = lab.getCollection("lab_orders");

const candidate = "ix_customer_short";
const found = orders.getIndexes().find(x => x.name === candidate);

if (!found) {
  print("Index không tồn tại: " + candidate);
} else {
  print("Dropping named lab index: " + candidate);
  printjson(orders.dropIndex(candidate));
}
~~~

Lệnh trên chỉ drop **ix_customer_short** trong **lab_orders** của **mongo_index_design_lab**. Không drop unique index hay _id index. Không dùng tên index lấy trực tiếp từ request không tin cậy.

Nếu đã thử và phát hiện cần phục hồi, tạo lại index ngắn bằng định nghĩa ban đầu:

~~~javascript
orders.createIndex(
  { dataset: 1, tenantId: 1, customerId: 1 },
  { name: "ix_customer_short" }
);
~~~

Tạo lại index có thể tốn thời gian và tài nguyên, nhất là trên collection lớn. Đây là lý do **hide trước, quan sát rồi mới drop** có ích.

### 9.6. Bước 6 — Đối chiếu sau thay đổi

Sau khi drop, theo dõi:

- p95/p99 latency của các query dùng customerId.
- Sự xuất hiện thêm COLLSCAN hoặc SORT không mong muốn.
- totalDocsExamined/nReturned và totalKeysExamined.
- CPU, cache pressure, disk I/O, connection pool.
- Tốc độ insert/update/delete và độ trễ ghi.
- Dung lượng index và tác động tới replication/backup.
- Những job định kỳ chỉ chạy vào các thời điểm khác nhau.

Không kết luận thành công chỉ vì một truy vấn mongosh vẫn trả đúng dữ liệu. Một index bị bỏ có thể khiến query trả **đúng nhưng chậm** khi dữ liệu tăng hoặc khi tác vụ cuối tháng chạy.

## 10. Index trùng lặp: ma trận quyết định

| Cặp index | Nhận định ban đầu | Hành động hợp lý |
| --- | --- | --- |
| **{tenantId}** và **{tenantId,customerId,createdAt}** | Index ngắn là tiền tố | Đánh giá loại index ngắn nếu không có option đặc biệt hoặc lợi ích riêng |
| **{tenantId,customerId}** và **{tenantId,status}** | Cùng trường đầu nhưng trường thứ hai khác | Có thể cần cả hai cho query khác nhau |
| **{tenantId,customerId,createdAt}** và **{tenantId,createdAt}** | Không phải cùng thứ tự tiền tố | Query sort toàn tenant có thể cần index thứ hai |
| Index cùng key nhưng một index **unique** | Khác ràng buộc dữ liệu | Không drop unique nếu chưa có phương án tương đương |
| Full index và partial index có cùng key | Tập document được lập index khác | Kiểm tra filter và phạm vi query trước khi quyết định |
| Index thường và TTL index có cùng field | TTL còn có tác dụng tự xóa | Không coi TTL là trùng vô ích |
| Index khác collation | So sánh/sort có thể khác | Giữ nếu cả hai collation phục vụ nhu cầu thật |
| Index chứa array và index scalar khác | Quy tắc multikey/covered/sort khác nhau | Đọc query plan và hiểu kiểu dữ liệu trước |
| Index A và B có toàn bộ sort chiều ngược nhau | Có thể scan ngược cùng index | Xem các equality prefix và hướng sort trước khi tạo thêm |
| Index có accesses.ops = 0 một ngày | Chưa được dùng trong khoảng ngắn | Chưa đủ căn cứ xóa; xét chu kỳ workload và constraint |

## 11. Chi phí index: đánh đổi giữa đọc và ghi

### 11.1. Mỗi index đều cần được duy trì

Khi insert một Order, MongoDB phải ghi document và cập nhật những index liên quan. Khi update một field có trong index, key index có thể phải thay đổi. Khi delete document, MongoDB phải loại các index entry của document.

Nếu có nhiều index chồng lấn, một lần ghi có thể đụng tới nhiều cấu trúc gần giống nhau. Tác động có thể gồm:

- Tăng độ trễ insert/update/delete.
- Tăng write amplification và lượng dữ liệu phải sao chép/backup.
- Tăng dung lượng lưu index và sức ép lên cache.
- Tăng thời gian index build/migration và độ phức tạp vận hành.

Do đó, loại index trùng lặp được xác nhận là không cần là công việc tối ưu đáng kể, nhất là hệ thống ghi nhiều.

### 11.2. Index càng dài không phải lúc nào cũng tốt hơn

Một compound index chứa nhiều field:

~~~javascript
{
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  total: 1,
  orderNo: 1
}
~~~

không tự động thay thế tốt mọi index ngắn:

- Query chỉ lọc tenantId và sort createdAt có thể không tận dụng thứ tự createdAt do customerId/status nằm trước.
- Index có key rộng hơn có thể tốn nhiều dung lượng.
- Projection khác nhau dẫn đến kết quả FETCH khác nhau.
- Chỉ dùng một index cho mọi access pattern có thể đẩy nhiều query vào scan/sort không mong muốn.

Mục tiêu là **bộ index vừa đủ**, không phải **một index khổng lồ**.

### 11.3. Mảng làm tăng fan-out

Nếu một field trong index là Array, MongoDB có thể tạo **multikey index** với nhiều entry cho một document. Ví dụ index trên items.sku sẽ chịu chi phí theo số SKU khác nhau trong từng Order. Hai Array độc lập trong một compound multikey index còn có giới hạn parallel arrays.

Chỉ thêm multikey index nếu có truy vấn tìm theo phần tử cần thiết. Không lập index cho mọi trường nằm trong Array vì “có thể sau này cần tìm”.

## 12. Các điều kiện đặc biệt cần xét trước khi bỏ index

### 12.1. Partial index

Ví dụ một workload chỉ xem đơn pending:

~~~javascript
orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "ix_pending_by_tenant",
    partialFilterExpression: { status: "pending" }
  }
);
~~~

Index này chỉ chứa các document có **status: "pending"**; có thể nhỏ và hiệu quả khi chỉ một phần nhỏ đơn còn pending. MongoDB chỉ dùng partial index cho query mà điều kiện đủ để bảo đảm không bị thiếu document ngoài tập đã index. Nó **không** thay thế index toàn collection cho truy vấn lịch sử mọi trạng thái.

**Lưu ý đối với lab:** index trên dùng tenantId và createdAt, còn index thật của ứng dụng nhiều tenant có thể cần thêm dữ liệu phân vùng/định tuyến; chọn tùy workload. Chỉ tạo index khi có use case và đo lường.

### 12.2. Sparse index

Sparse index bỏ qua document thiếu field được index. Điều này có thể hữu ích khi nhiều document không có email hoặc externalId, nhưng khác với full index trong truy vấn null/missing và khả năng dùng cho query.

Không loại sparse index chỉ vì cùng key pattern với một full index mà chưa kiểm tra semantics, tính duy nhất và các loại document thiếu trường.

### 12.3. Unique index

Unique index giữ ràng buộc dữ liệu, không chỉ tăng tốc query. Một index non-unique cùng prefix chưa đủ thay thế. Khi xóa unique index, nguy cơ duplicate phải được đánh giá như một **thay đổi business constraint**.

### 12.4. TTL index

TTL index xóa document đủ hạn qua tiến trình nền. Nếu một session collection có TTL, không được drop chỉ vì $indexStats cho thấy ít truy vấn đọc index đó. Công dụng TTL là **retention**, không phải một truy vấn thường xuyên của ứng dụng.

### 12.5. Collation

Index xây với collation khác nhau có thể phục vụ so sánh và sort chuỗi theo quy tắc khác, ví dụ case-sensitive hoặc case-insensitive. Query thường cần collation tương thích để dùng index cho so sánh String/sort theo cách dự kiến. Kiểm tra option collation trong getIndexes và query trước khi kết luận một index thay thế được index khác.

### 12.6. Text, geospatial, hashed, wildcard

Những index chuyên biệt có giới hạn và mục đích khác:

- **Text:** hỗ trợ text search theo cơ chế text index.
- **Geospatial:** hỗ trợ truy vấn tọa độ/địa lý.
- **Hashed:** index giá trị băm, thường liên quan phân phối equality/sharding.
- **Wildcard:** hữu ích khi nhiều đường dẫn field chưa cố định, nhưng không có nghĩa tốt hơn các index chuyên cho query nóng.

Không dựa vào việc cùng nhắc tới một field để drop chúng thay bằng B-tree index thông thường.

## 13. Quy trình từ yêu cầu đến bộ index trong dự án thực tế

Có thể áp dụng tuần tự:

**Bước 1 — Thu thập query shape:** Lấy mẫu các API/query quan trọng, đầy đủ filter, sort, projection, limit, page size, tần suất, độ trễ và tenant context. Đừng dựa vào danh sách field schema.

**Bước 2 — Phân nhóm truy vấn:** Những query có cùng equality prefix và sort có thể dùng chung index; những query có sort khác hoặc field được lọc khác có thể cần index riêng.

**Bước 3 — Đề xuất index ứng viên:** Bắt đầu với ESR, prefix, hướng sort và các ràng buộc unique/partial/TTL. Chọn các index có khả năng phục vụ nhiều query thật.

**Bước 4 — Kiểm tra dữ liệu thực:** Đếm cardinality, phân bố status/tenant/customer, tỷ lệ null/missing, độ dài Array và mức tăng trưởng. Một index hữu ích cho tenant nhỏ có thể kém với tenant rất lớn.

**Bước 5 — Đo executionStats:** So sánh kế hoạch tự chọn và các index ứng viên trên tập dữ liệu đại diện. Đọc IXSCAN, FETCH, SORT, indexBounds và các con số quét/đọc.

**Bước 6 — Xác định chồng lấn:** So sánh key pattern **và toàn bộ options**. Chỉ đánh dấu index tiền tố là **ứng viên**, chưa tự động drop.

**Bước 7 — Thu thập usage:** Dùng $indexStats, profiler/slow query logs, telemetry API và chu kỳ tải. Chú ý job ít xuất hiện và ràng buộc dữ liệu.

**Bước 8 — Thử hidden index có kiểm soát:** Trên staging hoặc theo quy trình rollout an toàn, hide ứng viên, theo dõi query plan và latency. Có phương án unhide ngay nếu xuất hiện regression.

**Bước 9 — Drop đúng index đã được phê duyệt:** Lưu định nghĩa/rollback, chọn thời gian triển khai phù hợp, giám sát tải. Không drop đồng loạt nhiều index khi chưa biết ảnh hưởng riêng từng index.

**Bước 10 — Theo dõi sau thay đổi:** Kiểm tra p95/p99, số key/document được xét, write latency, kích thước index, errors và job định kỳ. Cập nhật tài liệu index ownership để lần thay đổi sau không tạo lại index dư thừa.

Một quy trình duy trì index tốt cần có người chịu trách nhiệm về **mục đích của từng index**. Nếu không ai biết index phục vụ query nào, vấn đề không chỉ nằm ở dung lượng mà còn là chi phí bảo trì.

## 14. Những sai lầm thường gặp

| Sai lầm | Vì sao không đúng | Cách xử lý |
| --- | --- | --- |
| Lập index cho mọi field | Tạo chi phí ghi/dung lượng lớn; không bảo đảm hỗ trợ sort | Thiết kế theo query shape |
| Cho rằng nhiều index đơn tương đương một compound index | Intersection không mặc nhiên tối ưu hoặc hỗ trợ sort | Đo compound index theo ESR |
| Xóa mọi index là tiền tố của index dài hơn | Index ngắn có thể có option khác hoặc hiệu quả hơn cho một số query | Xét semantics và workload trước khi drop |
| Xóa index unique vì usage bằng 0 | Unique duy trì ràng buộc dữ liệu | Không bỏ khi chưa thay thế constraint |
| Xóa index TTL vì không có query nào dùng | TTL phục vụ tự động xóa dữ liệu | Giữ theo retention policy |
| Cho rằng index {tenant,customer,createdAt} đủ cho sort mọi đơn theo tenant | customer đứng giữa tenant và createdAt | Cân nhắc {tenant,createdAt} cho query toàn tenant |
| Có IXSCAN nghĩa query tối ưu | Vẫn có thể quét nhiều key/document hoặc SORT | Đọc executionStats và latency |
| Dùng hint cố định trên production | Bỏ qua khả năng planner chọn index tốt hơn khi dữ liệu thay đổi | Chỉ hint có chủ đích sau đo đạc |
| Kết luận index vô dụng từ $indexStats trong vài giờ | Chưa bao phủ job ngày/tuần/tháng | Quan sát đủ chu kỳ và node |
| Hide index rồi coi write cost đã giảm | Hidden vẫn được duy trì khi ghi | Hide chỉ kiểm tra việc planner không chọn index |
| Drop nhiều index cùng lúc | Khó truy nguyên regression và rollback | Bỏ từng ứng viên có quan sát |
| Tạo một index rất dài cho mọi query | Field trung gian có thể cản trở lọc/sort; index cồng kềnh | Tách theo access pattern |
| Chỉ đo trong lab rất nhỏ | COLLSCAN có thể thắng vì tập dữ liệu quá nhỏ | Kiểm thử tải đại diện |
| Quên collation/partial/sparse | Khác semantics dù field giống nhau | Đối chiếu getIndexes đầy đủ |
| Bỏ index dựa trên trùng tên | Tên không phản ánh nội dung/semantics | So sánh key/options và ownership |

## 15. Bài tập thực hành

### Bài 1 — Viết access pattern

Với hệ thống bán hàng, hãy viết hợp đồng truy vấn cho các màn hình: lịch sử đơn của khách, danh sách pending, toàn bộ đơn theo tenant và báo cáo đơn theo khoảng tiền. Với mỗi query, xác định equality, sort, range, projection và tần suất giả định.

### Bài 2 — Tiền tố và sort

Cho index:

~~~javascript
{ tenantId: 1, customerId: 1, createdAt: -1, _id: -1 }
~~~

Hãy phân loại các truy vấn:

1. Tìm tất cả order theo tenantId/customerId.
2. Tìm order theo tenantId/customerId và sort createdAt giảm.
3. Tìm order theo tenantId và sort createdAt giảm.
4. Tìm order theo customerId, không có tenantId.

Giải thích truy vấn nào khai thác tiền tố thuận lợi và truy vấn nào cần index khác.

### Bài 3 — ESR và ERS

Thiết kế index cho query lọc tenantId/status và total từ A đến B, sort createdAt giảm dần. Đề xuất hai thứ tự index, một thiên về ESR và một thiên về range chọn lọc. Nêu dữ liệu nào cần đo để quyết định phương án có tổng chi phí thấp hơn.

### Bài 4 — Đo index ngắn và dài

Sau khi chạy seed, so sánh explain với **ix_customer_short** và **ix_customer_recent** khi truy vấn lịch sử c001. Quan sát indexBounds, FETCH, SORT, totalKeysExamined, totalDocsExamined và nReturned. Vì sao kết quả ở 12 document chưa đủ để khẳng định chênh lệch latency production?

### Bài 5 — Loại index trùng tiền tố

Kiểm tra getIndexes, dùng hideIndex cho **ix_customer_short**, xem lại các query theo customer, sau đó unhideIndex. Nêu điều kiện nào cần thỏa trước khi dropIndex trên production và tại sao hidden index không giúp đo lợi ích giảm chi phí ghi.

### Bài 6 — Không xóa nhầm index quan trọng

Giả sử collection có các index:

~~~text
{tenantId:1,orderNo:1} unique
{tenantId:1,orderNo:1,createdAt:-1} non-unique
{expiresAt:1} TTL
{tenantId:1,status:1} partial(status="pending")
{tenantId:1,status:1,createdAt:-1} full
~~~

Hãy phân loại index có thể chồng lấn và index có semantics riêng. Giải thích vì sao không được drop unique hoặc TTL chỉ vì có index khác hoặc $indexStats chưa ghi nhận usage.

### Bài 7 — Ước lượng chi phí ghi

Giả sử đơn hàng có 6 index, tốc độ 2.000 ghi/giây và collection tăng nhanh. Hãy nêu nhóm metric cần theo dõi khi thêm hoặc bỏ một index. Tại sao không thể tính chính xác dung lượng index chỉ bằng số document nhân số field được index?

### Bài 8 — Truy vấn bị blocking SORT

Chạy explain cho query Q4 với hint **ix_customer_recent** rồi với **ix_tenant_recent**. Xác định xem query có cần SORT khi dùng index chứa customerId ở giữa hay không. Giải thích vì sao dữ liệu của nhiều customer không có thứ tự createdAt toàn cục trong index đầu.

### Bài 9 — Quy trình rollout

Hãy thiết kế quy trình ngừng sử dụng một index được cho là dư thừa trên collection nhiều triệu document: thu thập usage đủ chu kỳ, lưu metadata, hide ở môi trường phù hợp, giám sát regressions, drop đúng tên và lên kế hoạch build lại. Nêu điều kiện dừng rollout.

### Bài 10 — Bộ index tối thiểu

Từ danh sách index trong lab, chọn bộ index tối thiểu hợp lý cho Q1–Q6 với các giả định workload đã nêu. Chỉ rõ index nào nên giữ vì **hiệu năng**, index nào giữ vì **uniqueness**, index nào là **ứng viên bỏ**, và điều gì cần đo thêm trước khi ra quyết định cuối.

## 16. Tài liệu tham khảo MongoDB

- MongoDB Manual — [Indexes](https://www.mongodb.com/docs/manual/indexes/).
- MongoDB Manual — [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/).
- MongoDB Manual — [The ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Index Stats Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/).
- MongoDB Manual — [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/).
- MongoDB Manual — [db.collection.getIndexes()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getIndexes/).
- MongoDB Manual — [db.collection.dropIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.dropIndex/).

**Kết luận:** Thiết kế index bắt đầu từ **filter, sort, projection, limit và tần suất truy vấn thực tế**, không bắt đầu từ danh sách field. Compound index có thể thay thế nhiều index tiền tố, nhưng **trùng tiền tố mới chỉ là dấu hiệu để điều tra**. Trước khi bỏ một index, phải hiểu toàn bộ option, uniqueness/retention, query plan, usage và tác động vận hành. **Tập index tốt là tập nhỏ đủ đáp ứng các đường đọc quan trọng, bảo vệ ràng buộc cần thiết và giữ chi phí ghi trong giới hạn chấp nhận được.**
