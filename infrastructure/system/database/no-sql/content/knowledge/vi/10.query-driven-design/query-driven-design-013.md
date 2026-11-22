# Kiểm chứng mô hình bằng bộ truy vấn và dữ liệu đại diện

Trong NoSQL, một mô hình dữ liệu không được xem là tốt chỉ vì tài liệu JSON hợp lệ, ghi thành công hay chạy nhanh với vài bản ghi mẫu. **Thiết kế theo truy vấn** (*query-driven design*) yêu cầu kiểm chứng mô hình bằng **những truy vấn ứng dụng thực sự phải phục vụ**, trên **dữ liệu có kích thước và phân bố giống bài toán dự kiến**, kèm các tiêu chí về kết quả, độ trễ, chi phí và tính nhất quán.

Một lược đồ có thể xử lý rất tốt việc đọc một khách hàng nhưng hoạt động kém khi tìm đơn hàng theo trạng thái trên toàn hệ thống. Một khóa phân vùng có thể phân bố đều trong ví dụ 100 bản ghi nhưng tạo **hot partition** khi một khách hàng phát sinh hàng triệu sự kiện. Một bản sao dữ liệu để tăng tốc trang đọc có thể làm tăng chi phí cập nhật và nguy cơ đọc thông tin đã cũ.

Bài học này trình bày quy trình **đưa ra giả thuyết → thiết kế bộ truy vấn → tạo dữ liệu đại diện → chạy phép đo → kiểm tra tính đúng → quyết định hoặc điều chỉnh mô hình**. Ví dụ sử dụng nghiệp vụ đơn hàng và MongoDB để có thể thực hành, đồng thời chỉ rõ những nguyên tắc áp dụng cho các mô hình NoSQL khác.

## 1. “Kiểm chứng mô hình” thực sự có nghĩa gì?

Kiểm chứng không chỉ là chạy lệnh `find` hoặc `SELECT` mà không bị lỗi. Mô hình cần đáp ứng đồng thời nhiều khía cạnh:

| Khía cạnh | Câu hỏi kiểm chứng | Dấu hiệu cần đo hoặc đối chiếu |
| --- | --- | --- |
| **Tính đúng** | Truy vấn có trả chính xác tập kết quả nghiệp vụ? | Kết quả đối chiếu, điều kiện lọc, thứ tự, xử lý null/thiếu field |
| **Độ trễ đọc** | Người dùng có nhận kết quả đủ nhanh? | p50, p95, p99; timeout, độ trễ mạng |
| **Thông lượng** | Hệ xử lý bao nhiêu request/giây ở tải dự kiến? | RPS/QPS, số yêu cầu thành công, hàng đợi |
| **Hiệu quả truy cập** | Hệ đọc bao nhiêu dữ liệu để trả một kết quả? | Số document/keys examined, scan, lượng byte |
| **Chi phí ghi** | Ghi một thay đổi phải cập nhật bao nhiêu nơi? | Số ghi, index, write amplification, retry |
| **Tính nhất quán** | Dữ liệu dẫn xuất có theo kịp nguồn chân lý? | Độ trễ đồng bộ, sai khác dữ liệu, phiên bản |
| **Khả năng tăng trưởng** | Dữ liệu và lưu lượng tăng thì mô hình còn phù hợp? | Kích thước tài liệu, partition skew, bộ nhớ và lưu trữ |
| **Khả năng vận hành** | Có thể theo dõi, xử lý sự cố và thay đổi mô hình không? | Chỉ số quan sát, kế hoạch backfill, chi phí migration |

Mô hình đạt điểm cao ở một khía cạnh chưa chắc phù hợp tổng thể. Ví dụ, đọc từ **materialized view** có thể rất nhanh, nhưng nếu phải cập nhật ba bản sao cho mỗi thay đổi và hệ thống yêu cầu nhất quán tức thì thì chi phí thiết kế có thể vượt lợi ích.

**Kiểm chứng dựa trên các ràng buộc của nghiệp vụ**, không dựa trên một “điểm hiệu năng NoSQL” duy nhất.

## 2. Xuất phát từ hợp đồng truy vấn, không xuất phát từ collection

Giả sử một ứng dụng bán hàng đa khách thuê (*multi-tenant*) có người dùng, đơn hàng và các dòng sản phẩm. Trước khi viết cấu trúc lưu trữ, hãy xác định **tập truy vấn mục tiêu** (*query workload*) và tần suất của chúng.

### 2.1. Bộ truy vấn mẫu

| Mã | Truy vấn hoặc thao tác | Đầu vào chính | Đầu ra | Tỷ trọng minh họa |
| --- | --- | --- | --- | ---: |
| **Q1** | Lấy **20 đơn gần nhất** của một khách trong một tenant | `tenantId`, `customerId` | ID đơn, ngày tạo, trạng thái, tổng tiền | 55% |
| **Q2** | Xem **chi tiết một đơn** | `tenantId`, `orderId` | Đầu đơn và các dòng hàng | 20% |
| **Q3** | Lấy **20 đơn PENDING cũ nhất** trong một tenant | `tenantId`, trạng thái | Đơn theo thứ tự tạo tăng dần | 10% |
| **Q4** | Chuyển trạng thái đơn từ PENDING sang PAID | `tenantId`, `orderId`, trạng thái kỳ vọng | Kết quả cập nhật, phiên bản mới | 12% |
| **Q5** | Báo cáo doanh thu theo ngày và tenant | Khoảng ngày, tenant | Tổng giá trị và số đơn đủ điều kiện | 3% |

Tỷ trọng trong bảng **là giả định cho bài thực hành**, không phải thống kê của một hệ thống cụ thể. Tổng bằng 100% để tiện hình dung một hỗn hợp tải. Hệ thực tế phải đo traffic, lịch batch, tác vụ nền, tỷ lệ đọc/ghi và tải đỉnh thay vì tự chọn tỷ trọng đẹp.

### 2.2. Cần ghi đầy đủ hợp đồng từng truy vấn

Tên “lấy đơn theo khách hàng” là chưa đủ. Với **Q1**, hợp đồng cần nói rõ:

- Chỉ đọc trong **tenant hiện tại**, tránh lộ dữ liệu tenant khác.
- Lọc đúng **một customerId**; nếu không tồn tại phải trả danh sách rỗng.
- Sắp **`createdAt` giảm dần**, dùng `_id` giảm dần làm **khóa phụ** khi nhiều đơn có cùng thời gian.
- Giới hạn 20 đơn. Không trả toàn bộ lịch sử hàng nghìn đơn.
- Đầu ra là **metadata đơn hàng**, không cần danh sách sản phẩm.
- Dữ liệu có cần phản ánh cập nhật trạng thái **ngay sau khi ghi** hay chấp nhận trễ vài giây?

Câu hỏi cuối đặc biệt quan trọng. Hai phương án có thể đều đúng về tập đơn nhưng khác cam kết nhất quán. Phương án trả dữ liệu cũ hơn không thể được xem là tương đương khi nghiệp vụ yêu cầu *read-your-writes* ngay lập tức.

Với **Q3**, cần xác định chính xác “cũ nhất” là theo thời gian tạo, thời điểm chuyển sang PENDING hay thời hạn xử lý. Nếu hai nhóm dùng hai định nghĩa khác nhau, đo nhanh hơn không có ý nghĩa vì chúng đang trả **hai kết quả khác nhau**.

### 2.3. Tiêu chí chấp nhận

Ví dụ, một nhóm có thể tự đặt **mục tiêu giả định** như sau:

| Thao tác | Mục tiêu minh họa | Ràng buộc không được vi phạm |
| --- | --- | --- |
| Q1 | p95 ≤ 100 ms ở tải thử dự kiến | Đúng 20 đơn gần nhất, không lẫn tenant |
| Q2 | p95 ≤ 150 ms | Đúng chi tiết, đúng tổng tiền |
| Q3 | p95 ≤ 200 ms | Đúng trạng thái và thứ tự |
| Q4 | p95 ≤ 120 ms | Không chuyển trạng thái trùng, không đọc sai phiên bản |
| Q5 | Hoàn tất trước hạn báo cáo | Tổng đúng và có mốc dữ liệu rõ ràng |

Các ngưỡng này chỉ là **mẫu cách viết SLO**, không phải số liệu đảm bảo của MongoDB hay khuyến nghị áp dụng cho mọi ứng dụng. Khi thiết kế test thực tế, phải ghi điều kiện đo: số tenant, số bản ghi, concurrency, phần cứng, cấu hình database, cache và đường mạng.

## 3. Dữ liệu đại diện: yếu tố quyết định độ tin cậy của phép thử

“Dữ liệu đại diện” không chỉ có nghĩa là tạo thật nhiều document. Bộ dữ liệu phải phản ánh các **đặc tính làm thay đổi hành vi truy vấn**.

### 3.1. Những chiều dữ liệu phải hiểu

| Chiều dữ liệu | Ví dụ | Vì sao ảnh hưởng mô hình |
| --- | --- | --- |
| **Cardinality** | 3 tenant, 600 khách, 12.000 đơn | Ảnh hưởng kích thước tập dữ liệu và chỉ mục |
| **Độ lệch phân bố (skew)** | 1% khách tạo 30% đơn | Có thể tạo hot key/partition, tài liệu hoặc mảng rất lớn |
| **Phân bố thời gian** | Đơn tập trung giờ cao điểm, dữ liệu lịch sử nhiều tháng | Ảnh hưởng index theo thời gian và truy vấn gần đây |
| **Kích thước document** | 1–5 dòng bình thường; đơn sỉ có 2.000 dòng | Ảnh hưởng đọc payload, nhúng dữ liệu và giới hạn document |
| **Độ chọn lọc filter** | 5% PENDING, 95% đã xử lý | Ảnh hưởng khả năng lọc bằng index |
| **Tỷ lệ ghi/đọc** | 8 lần đọc cho 1 lần ghi, có burst | Ảnh hưởng index và view nhân bản |
| **Giá trị đặc biệt** | Đơn không có khách, trạng thái null, timestamp trùng | Phát hiện bug đúng kết quả và sort/pagination |
| **Phân vùng theo tenant** | Một tenant gấp nhiều lần tenant khác | Kiểm tra isolation, giới hạn và phân bố tải |
| **Tính cập nhật** | Trạng thái thay đổi nhiều lần/phút | Bộc lộ độ trễ đồng bộ view và race condition |

Bộ dữ liệu ngẫu nhiên đồng đều thường **không đủ** cho các hệ thống có người dùng rất hoạt động, khách hàng doanh nghiệp lớn hoặc thiết bị sinh nhiều sự kiện.

### 3.2. Ba loại bộ dữ liệu nên kết hợp

1. **Dữ liệu chức năng nhỏ, có đáp án biết trước:** vài document bao gồm trường hợp trống, trùng thời gian, không tồn tại và nhiều tenant. Mục tiêu là khẳng định **tính đúng**.
2. **Dữ liệu đại diện quy mô vừa:** giữ tỷ lệ, phân bố độ dài mảng, độ chọn lọc, skew và kích thước tương tự production. Mục tiêu là xem index và hiệu năng.
3. **Dữ liệu cực trị/stress:** tenant lớn nhất, một khách rất “nóng”, đơn có nhiều dòng, số liệu phát sinh đồng thời và tài liệu sắp chạm giới hạn sản phẩm. Mục tiêu là phát hiện **giới hạn thiết kế**.

Các phép thử dùng dữ liệu thật cần che hoặc loại dữ liệu nhạy cảm, có quyền sử dụng hợp lệ và giữ những đặc tính thống kê cần thiết. Dữ liệu giả lập có quy luật phù hợp là lựa chọn tốt khi không được đưa dữ liệu thật sang môi trường thử nghiệm.

## 4. Hai phương án thiết kế cần đem ra kiểm chứng

Chọn cùng nghiệp vụ đơn hàng và giữ **nguồn chân lý** giống nhau để tách chi phí giữa đọc nhanh và cập nhật dữ liệu dẫn xuất.

### Phương án A: đọc trực tiếp collection đơn hàng

Mỗi đơn nằm trong `orders_baseline` với ID, tenant, customer, trạng thái, thời gian, tổng tiền và những dòng sản phẩm.

~~~json
{
  "_id": "ORD-00000004",
  "tenantId": "T02",
  "customerId": "C001",
  "status": "SHIPPED",
  "createdAt": "2026-10-01T00:04:00Z",
  "totalAmount": 70000,
  "items": [
    { "sku": "SKU-0001", "quantity": 2, "unitPrice": 10000 },
    { "sku": "SKU-0002", "quantity": 1, "unitPrice": 20000 },
    { "sku": "SKU-0003", "quantity": 1, "unitPrice": 30000 }
  ]
}
~~~

Các giá trị chỉ minh họa cấu trúc, không nhất thiết trùng mọi giá trị do script seed bên dưới sinh ra.

Q1 có thể truy vấn:

~~~javascript
db.orders_baseline
  .find({ tenantId: "T02", customerId: "C001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Để hỗ trợ đường truy cập này, mô hình cần index thích hợp trên tenant, customer và các khóa sắp xếp. Q3 lại cần đường truy cập theo **tenant + status + thời gian**. Một index không nhất thiết tối ưu cả hai.

### Phương án B: collection đơn hàng + read model chuyên cho Q1

Phương án B vẫn lưu **tất cả đơn hàng canonical** trong `orders_candidate`, có cùng nội dung như A. Ngoài ra, nó duy trì `customer_recent` chứa **20 metadata đơn gần nhất** của từng khách trong một tenant.

~~~json
{
  "_id": "T02|C001",
  "tenantId": "T02",
  "customerId": "C001",
  "recentOrders": [
    {
      "_id": "ORD-00000004",
      "createdAt": "2026-10-01T00:04:00Z",
      "status": "SHIPPED",
      "totalAmount": 70000
    }
  ]
}
~~~

Mảng trên chỉ minh họa hình dạng; thực tế có thể chứa tối đa 20 phần tử. Nó là một **read model được vật hóa** (*materialized read model*) — tức là một bản sao nhỏ được tổ chức theo đúng đường truy vấn Q1.

~~~text
Phương án A
    ┌─────────────────┐
    │ orders_baseline │
    └────────┬────────┘
             ├── Q1: index (tenant, customer, time)
             ├── Q2: lookup theo orderId
             ├── Q3: index (tenant, status, time)
             ├── Q4: cập nhật một document
             └── Q5: quét/tổng hợp nhiều đơn

Phương án B
    ┌─────────────────┐       ┌──────────────────┐
    │ orders_candidate│──────▶│ customer_recent  │
    └────────┬────────┘       └─────────┬────────┘
             │                          └── Q1: lookup theo _id
             ├── Q2: lookup theo orderId
             ├── Q3: index (tenant, status, time)
             ├── Q4: cập nhật nguồn + view liên quan
             └── Q5: quét/tổng hợp nhiều đơn
~~~

Phương án B **không thay thế Q2, Q3, Q5** bằng phép đọc `customer_recent`. View chỉ phục vụ Q1. Nếu phần lớn workload là Q1, view có thể có ích; nếu workload cập nhật trạng thái liên tục, chi phí đồng bộ view có thể khiến B kém phù hợp.

Hai phương án này thể hiện một bài học quan trọng: **mô hình theo truy vấn đôi khi là một cấu trúc phụ trợ để tăng tốc một đường đọc**, đổi lại phải quản lý tính nhất quán và dung lượng. Không được mặc định denormalization là miễn phí.

## 5. Chuẩn bị môi trường thực nghiệm MongoDB

Các ví dụ sau dùng `mongosh` và một database riêng tên `nosql_query_validation_lab`. Cần quyền tạo collection, tạo index và đọc thống kê trên MongoDB thử nghiệm.

Script sẽ **xóa ba collection thử nghiệm** có tên cố định trước khi tạo lại. Không sử dụng những tên collection đó cho dữ liệu thật và không chạy trên môi trường sản xuất.

Bộ dữ liệu gồm:

- **12.000 đơn**, mỗi đơn có 1–5 dòng.
- **3 tenant**, với định danh `T01`, `T02`, `T03`.
- **200 customer ID có thể có trong mỗi tenant**.
- Một nhóm đơn tập trung vào **customer C001** để mô phỏng khách hoạt động mạnh.
- Timestamp phân bố theo từng phút trong khoảng thời gian giả lập.
- Trạng thái PENDING, PAID hoặc SHIPPED theo quy luật có thể tái lập.

Lưu ý: đây là **dữ liệu mô phỏng có skew có chủ ý**, vẫn chưa thay cho thống kê production. Trong hệ thật, cần điều chỉnh seed theo histogram và cardinality thực tế.

### 5.1. Sinh dữ liệu có quy luật, không sử dụng random

Chạy trong `mongosh`:

~~~javascript
const lab = db.getSiblingDB("nosql_query_validation_lab");

[
  "orders_baseline",
  "orders_candidate",
  "customer_recent"
].forEach(name => lab.getCollection(name).drop());

const N = 12000;
const orders = [];

for (let i = 1; i <= N; i++) {
  const tenantId = "T" + String((i % 3) + 1).padStart(2, "0");

  // Khoảng 1/4 số đơn tập trung vào C001.
  const customerNo = i % 4 === 0
    ? 1
    : ((i * 37) % 199) + 2;

  const customerId = "C" + String(customerNo).padStart(3, "0");

  const items = Array.from({ length: 1 + (i % 5) }, (_, j) => ({
    sku: "SKU-" + String((i + j * 7) % 1000).padStart(4, "0"),
    quantity: j === 0 ? 2 : 1,
    unitPrice: (j + 1) * 10000
  }));

  const totalAmount = items.reduce(
    (sum, item) => sum + item.quantity * item.unitPrice,
    0
  );

  orders.push({
    _id: "ORD-" + String(i).padStart(8, "0"),
    tenantId,
    customerId,
    status: i % 7 === 0 ? "PENDING"
      : i % 7 === 1 ? "PAID"
      : "SHIPPED",
    createdAt: new Date(Date.UTC(2026, 9, 1) + i * 60000),
    totalAmount,
    items
  });
}

lab.orders_baseline.insertMany(orders);
lab.orders_candidate.insertMany(orders);

print("baseline =", lab.orders_baseline.countDocuments({}));
print("candidate =", lab.orders_candidate.countDocuments({}));
~~~

Cả hai collection được sinh từ **cùng danh sách đơn**. Kết quả đếm mong đợi là 12.000 và 12.000 khi quá trình ghi hoàn tất thành công.

Không kết luận mô hình B tốt hơn vì hiện tại hai collection này có nội dung giống hệt nhau: điểm khác biệt sẽ xuất hiện khi ta **bổ sung và duy trì view `customer_recent`**.

### 5.2. Xây read model cho 20 đơn gần nhất của mỗi customer

~~~javascript
const groups = new Map();

for (const order of orders) {
  const key = order.tenantId + "|" + order.customerId;

  if (!groups.has(key)) {
    groups.set(key, {
      _id: key,
      tenantId: order.tenantId,
      customerId: order.customerId,
      recentOrders: []
    });
  }

  groups.get(key).recentOrders.push({
    _id: order._id,
    createdAt: order.createdAt,
    status: order.status,
    totalAmount: order.totalAmount
  });
}

const summaries = Array.from(groups.values());

for (const summary of summaries) {
  summary.recentOrders.sort((a, b) =>
    b.createdAt - a.createdAt ||
    b._id.localeCompare(a._id)
  );

  summary.recentOrders = summary.recentOrders.slice(0, 20);
}

if (summaries.length > 0) {
  lab.customer_recent.insertMany(summaries);
}

print("summary documents =", lab.customer_recent.countDocuments({}));
~~~

Việc tạo view ở đây là **backfill một lần**. Khi hệ đang vận hành thật, các đơn mới hoặc thay đổi trạng thái còn cần được đồng bộ vào view; phần sau sẽ kiểm chứng chi phí ghi và nguy cơ stale read.

View chỉ giữ **20 đơn**, tránh mảng tăng vô hạn. Nếu một khách có 500.000 đơn thì view vẫn bị giới hạn kích thước, trong khi collection canonical lưu đầy đủ lịch sử để phân trang khi cần.

### 5.3. Tạo chỉ mục theo bộ truy vấn

~~~javascript
for (const name of ["orders_baseline", "orders_candidate"]) {
  const collection = lab.getCollection(name);

  // Q1: lọc tenant và customer, sắp đơn mới nhất trước.
  collection.createIndex({
    tenantId: 1,
    customerId: 1,
    createdAt: -1,
    _id: -1
  });

  // Q3: lọc theo tenant + status, lấy đơn cũ nhất trước.
  collection.createIndex({
    tenantId: 1,
    status: 1,
    createdAt: 1,
    _id: 1
  });
}

// customer_recent đã có index duy nhất trên _id mặc định.
~~~

Trong MongoDB, collection thông thường có chỉ mục `_id` mặc định. Phương án A và B được tạo **cùng hai chỉ mục trên đơn hàng** để tránh so sánh không công bằng do bên này có index còn bên kia không. Phương án B chịu **thêm dung lượng và chi phí cập nhật của collection `customer_recent`**.

Một vài nguyên tắc đọc composite index:

- Các trường lọc bằng điều kiện bằng nhau (`tenantId`, `customerId`) thường nên đứng trước các trường dùng cho sort/range.
- Trình tự `createdAt: -1, _id: -1` hỗ trợ sắp xếp có khóa phụ xác định.
- Một index được thiết kế cho Q1 không mặc nhiên phục vụ tối ưu Q3, vì Q3 lọc theo `status` thay cho `customerId`.
- Không tạo index cho mọi tổ hợp field: mỗi index tăng chi phí ghi, bộ nhớ và lưu trữ.

Đối với Cassandra hoặc wide-column store, bài toán tương tự nhưng thiết kế thường đặt vào **partition key, clustering columns và bảng dành riêng cho truy vấn** thay vì kỳ vọng secondary index giải quyết mọi trường hợp. Không nên sao chép trực tiếp cú pháp MongoDB sang hệ wide-column.

## 6. Kiểm chứng tính đúng của Q1 trước khi đo tốc độ

**Q1:** trong tenant `T01`, lấy 20 đơn mới nhất của customer `C001`, trả ID, thời gian, trạng thái và tổng tiền.

### 6.1. Đọc trực tiếp theo phương án A

~~~javascript
function listRecentFromOrders(tenantId, customerId) {
  return lab.orders_baseline.find(
    { tenantId, customerId },
    { _id: 1, createdAt: 1, status: 1, totalAmount: 1 }
  )
    .sort({ createdAt: -1, _id: -1 })
    .limit(20)
    .toArray();
}

const q1A = listRecentFromOrders("T01", "C001");

print("Q1 A rows =", q1A.length);
~~~

### 6.2. Đọc materialized view theo phương án B

~~~javascript
function listRecentFromView(tenantId, customerId) {
  const key = tenantId + "|" + customerId;

  const summary = lab.customer_recent.findOne(
    { _id: key },
    { recentOrders: 1 }
  );

  return summary === null ? [] : summary.recentOrders;
}

const q1B = listRecentFromView("T01", "C001");

print("Q1 B rows =", q1B.length);
~~~

Trong phương án A, database lọc và sắp trên collection đơn hàng. Trong B, database đọc một document view theo khóa `_id`, rồi trả mảng 20 phần tử đã được tổ chức sẵn theo truy vấn.

### 6.3. So sánh kết quả nghiệp vụ bằng biểu diễn ổn định

Hai cách đọc có thể trả document với **thứ tự key khác nhau** mà vẫn đúng nghiệp vụ. Do đó, nên chuẩn hóa các field trước khi so sánh thay vì so sánh chuỗi JSON thô.

~~~javascript
function normalizeRecent(rows) {
  return rows.map(row => ({
    id: row._id,
    createdAt: new Date(row.createdAt).toISOString(),
    status: row.status,
    totalAmount: row.totalAmount
  }));
}

const same = JSON.stringify(normalizeRecent(q1A)) ===
  JSON.stringify(normalizeRecent(q1B));

print("Q1 result equivalent =", same);
~~~

Nếu seed và tạo view thành công, **kết quả mong đợi là `true`**. Không được dùng một phép benchmark có đầu ra sai để kết luận mô hình nhanh hơn.

Cần thử thêm các trường hợp:

- Khách thường với ít hơn 20 đơn.
- Khách rất hoạt động với nhiều hơn 20 đơn.
- Khách không tồn tại, phải trả danh sách rỗng.
- Tenant khác có cùng mã khách `C001`, không được lấy chéo tenant.
- Các đơn có `createdAt` bằng nhau; cả hai mô hình phải dùng cùng tie-breaker `_id`.
- Trạng thái vừa thay đổi hoặc đơn mới vừa tạo; view đã bắt kịp nguồn hay chưa?

Ví dụ dữ liệu seed hiện tại có thể chưa chứa timestamp trùng vì được sinh mỗi phút. **Bộ kiểm thử chức năng bổ sung** nên tạo trường hợp trùng timestamp theo chủ đích để xác nhận sắp xếp ổn định.

## 7. Kiểm chứng Q2: xem chi tiết một đơn

**Q2:** đọc đơn `ORD-00000004` của tenant `T02`, bao gồm các dòng sản phẩm.

~~~javascript
function loadOrderA(tenantId, orderId) {
  return lab.orders_baseline.findOne({
    _id: orderId,
    tenantId
  });
}

function loadOrderB(tenantId, orderId) {
  return lab.orders_candidate.findOne({
    _id: orderId,
    tenantId
  });
}

const orderA = loadOrderA("T02", "ORD-00000004");
const orderB = loadOrderB("T02", "ORD-00000004");

print("A found =", orderA !== null);
print("B found =", orderB !== null);
print("Same detail =", EJSON.stringify(orderA) === EJSON.stringify(orderB));
~~~

Hai collection canonical có cùng dữ liệu nên lúc mới seed kết quả dự kiến giống nhau. Q2 **không có lợi thế đọc từ view** trong phương án B: view chỉ chứa metadata của 20 đơn gần nhất, không chứa toàn bộ `items`.

Điều này cho thấy một read model phục vụ **một truy vấn** không tự giúp các truy vấn khác. Khi đo chi phí của phương án B, phải cộng cả việc lưu trữ và đồng bộ view, dù Q2 không sử dụng nó.

Nếu `orderId` có khả năng trùng giữa các tenant, khóa lưu trữ phải được thiết kế để phân biệt tenant; trong script này `_id` được sinh duy nhất toàn bộ bộ dữ liệu, còn điều kiện `tenantId` vẫn giúp thể hiện ranh giới truy cập.

## 8. Kiểm chứng Q3: đơn PENDING cũ nhất theo tenant

**Q3:** lấy 20 đơn PENDING cũ nhất trong tenant `T01`.

~~~javascript
function pendingOrders(collection) {
  return collection.find(
    {
      tenantId: "T01",
      status: "PENDING"
    },
    {
      _id: 1,
      createdAt: 1,
      status: 1,
      totalAmount: 1
    }
  )
    .sort({ createdAt: 1, _id: 1 })
    .limit(20)
    .toArray();
}

const q3A = pendingOrders(lab.orders_baseline);
const q3B = pendingOrders(lab.orders_candidate);

print(
  "Q3 result equivalent =",
  EJSON.stringify(q3A) === EJSON.stringify(q3B)
);
~~~

Index `{ tenantId: 1, status: 1, createdAt: 1, _id: 1 }` được tạo cho truy vấn này. Chỉ mục chỉ phát huy lợi thế khi **điều kiện truy vấn và thống kê dữ liệu thực tế** phù hợp, nên tiếp tục xem execution plan chứ không mặc định query nhanh.

Cần kiểm tra cả tập dữ liệu có **rất ít PENDING** và tập có **phần lớn đơn đang PENDING**, vì độ chọn lọc của status thay đổi chi phí. Nếu nghiệp vụ thường lấy tất cả đơn PENDING trong toàn hệ thống thay vì từng tenant, đường index và cách phân vùng cũng có thể phải khác.

## 9. Kiểm chứng Q4: đọc nhanh không được đánh đổi tính nhất quán

**Q4:** đổi trạng thái một đơn từ PENDING sang PAID. Với phương án A, thay đổi nằm trong một document đơn hàng; với phương án B, trạng thái còn được sao chép trong `customer_recent` nếu đơn đó thuộc 20 đơn gần nhất.

### 9.1. Cập nhật canonical document có điều kiện

Trong phương án A:

~~~javascript
const updateA = lab.orders_baseline.updateOne(
  {
    _id: "ORD-00000007",
    tenantId: "T02",
    status: "PENDING"
  },
  {
    $set: { status: "PAID" }
  }
);

printjson(updateA);
~~~

Vì `7 % 7 = 0`, đơn `ORD-00000007` được seed ở trạng thái PENDING. Vì `7 % 3 = 1` nên tenant của nó là `T02`. Lệnh dùng trạng thái kỳ vọng để tránh chuyển lại đơn đã PAID.

Đây là **một document update**. Nếu cần lưu lịch sử chuyển trạng thái, kiểm soát thanh toán hoặc ghi sự kiện ra hệ ngoài, bài toán nhất quán sẽ rộng hơn một update đơn lẻ.

### 9.2. Với read model, một thay đổi có hai nơi cần được phản ánh

Phương án B phải đảm bảo:

~~~text
orders_candidate[ORD-00000007].status
                 |
                 +----> customer_recent[T02|customerId]
                        recentOrders[].status (nếu đơn nằm trong top 20)
~~~

Nếu chỉ cập nhật `orders_candidate`, Q2 và Q3 có thể trả trạng thái mới trong khi Q1 vẫn trả trạng thái cũ từ view.

Có hai lựa chọn chính, tùy yêu cầu:

- **Đồng bộ chặt:** cập nhật nguồn và view trong một transaction được hệ hỗ trợ, hoặc dùng thiết kế giữ được ràng buộc mà không cần hai bản ghi riêng.
- **Nhất quán cuối cùng:** cập nhật nguồn trước; phát sự kiện/CDC để cập nhật view và công bố rõ khả năng Q1 bị trễ. Cần xử lý retry, sự kiện sai thứ tự và đối chiếu định kỳ.

Mã dưới đây minh họa ý tưởng **transaction hai document**. Chỉ chạy khi MongoDB triển khai có hỗ trợ transaction phù hợp, ví dụ replica set; cần xử lý transient errors và kết quả commit không xác định bằng chiến lược retry của driver trong ứng dụng thực.

~~~javascript
const orderId = "ORD-00000007";
const tenantId = "T02";
const customerId = "C" + String((7 * 37) % 199 + 2).padStart(3, "0");
const summaryId = tenantId + "|" + customerId;

const session = lab.getMongo().startSession();

try {
  session.startTransaction();

  const tx = session.getDatabase("nosql_query_validation_lab");

  const result = tx.orders_candidate.updateOne(
    {
      _id: orderId,
      tenantId,
      status: "PENDING"
    },
    {
      $set: { status: "PAID" }
    }
  );

  if (result.matchedCount !== 1) {
    throw new Error("Trạng thái đã đổi hoặc đơn không tồn tại");
  }

  // Nếu đơn thuộc 20 đơn mới nhất, cập nhật bản sao trạng thái.
  // Nếu không thuộc view, thao tác updateOne không làm thay đổi dữ liệu.
  tx.customer_recent.updateOne(
    { _id: summaryId },
    {
      $set: {
        "recentOrders.$[entry].status": "PAID"
      }
    },
    {
      arrayFilters: [
        { "entry._id": orderId }
      ]
    }
  );

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
~~~

Đây chỉ là **minh họa ranh giới giao dịch**, không phải mô-đun transaction sản xuất hoàn chỉnh. Một đơn không nằm trong top 20 sẽ không cần cập nhật view này; nhưng nếu ứng dụng còn các bản sao khác thì chúng cũng phải được đưa vào quy tắc đồng bộ.

Quan trọng hơn, **tạo đơn mới** có thể khiến một đơn cũ rơi khỏi danh sách top 20. Cập nhật view khi thêm đơn cần duy trì thứ tự, giới hạn 20 và xử lý ghi đồng thời; không thể đơn giản `$push` vô hạn. Đây là chi phí sở hữu của mô hình B mà phép benchmark chỉ đọc Q1 sẽ không nhìn thấy.

### 9.3. Phân biệt tính đúng theo hợp đồng nhất quán

Nếu Q1 phải thấy trạng thái PAID **ngay sau khi Q4 hoàn tất**, mọi phép đo chỉ đọc view cũ đều không đáp ứng hợp đồng. Nếu sản phẩm chấp nhận độ trễ đồng bộ dưới 5 giây, phép kiểm chứng cần **đo phân bố độ trễ đồng bộ** và tỷ lệ lượt đọc stale, chứ không chỉ đánh giá tốc độ Q1.

Không nên so sánh hiệu năng của mô hình A cho kết quả mới nhất với mô hình B cho kết quả cũ mà không nêu rõ khác biệt đó.

## 10. Xem kế hoạch thực thi: index có thực sự được dùng?

Việc tạo index chưa chứng minh truy vấn luôn tối ưu. Trong MongoDB, có thể dùng `explain("executionStats")` để quan sát đường truy cập và số tài liệu được xét.

### Q1 của phương án A

~~~javascript
printjson(
  lab.orders_baseline.find(
    { tenantId: "T01", customerId: "C001" },
    { _id: 1, createdAt: 1, status: 1, totalAmount: 1 }
  )
    .sort({ createdAt: -1, _id: -1 })
    .limit(20)
    .explain("executionStats")
);
~~~

### Q1 của phương án B

~~~javascript
printjson(
  lab.customer_recent
    .find({ _id: "T01|C001" })
    .explain("executionStats")
);
~~~

### Q3 của hai phương án

~~~javascript
printjson(
  lab.orders_baseline.find({
    tenantId: "T01",
    status: "PENDING"
  })
    .sort({ createdAt: 1, _id: 1 })
    .limit(20)
    .explain("executionStats")
);

printjson(
  lab.orders_candidate.find({
    tenantId: "T01",
    status: "PENDING"
  })
    .sort({ createdAt: 1, _id: 1 })
    .limit(20)
    .explain("executionStats")
);
~~~

Các trường thường hữu ích:

| Chỉ số | Ý nghĩa | Cần hiểu đúng |
| --- | --- | --- |
| `nReturned` | Số document trả về | Nhiều hay ít chưa nói truy vấn hiệu quả |
| `totalKeysExamined` | Số entry chỉ mục được xem xét | Index có thể vẫn đọc quá nhiều entry |
| `totalDocsExamined` | Số document được xét | So với `nReturned` để thấy mức scan |
| `executionTimeMillis` | Thời gian trong ngữ cảnh explain | Không đồng nhất với thời gian request của người dùng |
| `winningPlan` | Kế hoạch thực thi được chọn | Hình dạng khác nhau theo phiên bản/engine |
| `SORT` / `COLLSCAN` | Có bước sort hoặc quét collection | Cần xem dữ liệu và truy vấn để hiểu nguyên nhân |

Một truy vấn chỉ trả 20 đơn nhưng quét 500.000 document là dấu hiệu cần xem lại **index, thứ tự field, phân vùng hoặc mô hình dữ liệu**. Ngược lại, `totalDocsExamined` thấp không tự bảo đảm latency thấp nếu mỗi document rất lớn hoặc phải phối hợp nhiều node.

**Kế hoạch thực thi là bằng chứng về cách hệ đang truy cập dữ liệu**, chứ không phải bằng chứng về mọi đặc điểm của tải production.

## 11. Đo độ trễ toàn thao tác thay vì chỉ đo một lệnh

Nếu một nghiệp vụ cần hai lần đọc, một phép benchmark chỉ đo lần đọc đầu sẽ làm kết quả sai lệch. Phải đo **toàn bộ thao tác tạo cùng đầu ra** và kiểm tra kết quả của nó.

### 11.1. Hàm đo đơn giản trong mongosh

~~~javascript
function bench(label, operation, keys, rounds = 5) {
  // Warm-up: giúp loại bớt ảnh hưởng lần thực thi đầu.
  for (const key of keys.slice(0, 20)) operation(key);

  const elapsedMs = [];

  for (let round = 0; round < rounds; round++) {
    const begin = Date.now();

    for (const key of keys) {
      operation(key);
    }

    elapsedMs.push(Date.now() - begin);
  }

  printjson({
    label,
    requestsPerRound: keys.length,
    elapsedMsPerRound: elapsedMs
  });
}

// Bộ keys có cả khách hoạt động mạnh và khách thông thường.
const customers = ["C001", "C002", "C015", "C050", "C100", "C200"];

bench(
  "Q1 baseline",
  customerId => listRecentFromOrders("T01", customerId),
  customers,
  5
);

bench(
  "Q1 view",
  customerId => listRecentFromView("T01", customerId),
  customers,
  5
);
~~~

Đây là **phép đo minh họa cách làm**, không phải benchmark chuẩn sản xuất:

- `Date.now()` có độ phân giải giới hạn.
- Request thực hiện **tuần tự** trong mongosh, chưa mô phỏng concurrency.
- Bộ 6 khách quá nhỏ để suy ra phân bố độ trễ toàn hệ thống.
- Lượt chạy sau có thể hưởng cache từ lượt chạy trước.
- Số mili-giây còn gồm chi phí JavaScript, shell và network.

Khi đánh giá triển khai thực, nên chạy từ tầng ứng dụng với driver và pool kết nối đúng cấu hình, **trộn thứ tự A/B**, thử nhiều mức concurrency, đo p50/p95/p99, lưu throughput/error rate và lặp lại nhiều lần.

### 11.2. Vì sao cần phân vị p95/p99?

Giả sử 99 request hoàn thành trong 20 ms, nhưng request cuối mất 2.000 ms. Trung bình có thể che giấu phần lớn trải nghiệm chậm ở đuôi phân bố.

Các chỉ số:

- **p50:** khoảng trung vị; một nửa request hoàn thành không chậm hơn giá trị này.
- **p95:** phần lớn request (khoảng 95%) không chậm hơn giá trị này.
- **p99:** thể hiện hành vi ở đuôi phân bố, thường đáng chú ý với API yêu cầu độ ổn định.
- **Error/timeout rate:** số request thất bại hoặc quá hạn; không được chỉ tính các request thành công rồi báo kết quả đẹp hơn thực tế.

Cách tính percentile phải được thống nhất (cửa sổ thời gian, phương pháp nội suy, gộp theo endpoint) nếu muốn so sánh qua các lượt chạy.

## 12. Kiểm chứng kích thước dữ liệu và chi phí lưu trữ

Mô hình B bổ sung một collection view, nghĩa là phải trả chi phí lưu trữ và index ngoài collection canonical.

~~~javascript
function collectionSize(name) {
  const stats = lab.getCollection(name).stats();

  return {
    collection: name,
    count: stats.count,
    logicalSizeBytes: stats.size,
    storageSizeBytes: stats.storageSize,
    indexSizeBytes: stats.totalIndexSize
  };
}

printjson(collectionSize("orders_baseline"));
printjson(collectionSize("orders_candidate"));
printjson(collectionSize("customer_recent"));
~~~

Khi tính tổng chi phí của B, cần cộng **orders_candidate + customer_recent** và index tương ứng. `storageSize` còn chịu ảnh hưởng nén, cấp phát, phân mảnh và cơ chế lưu trữ; không nên nhìn vào số lượng document rồi suy đoán dung lượng.

Với hệ phân tán, phải tính thêm:

- Số bản sao (*replication factor*) và lưu lượng nhân bản.
- Shard/partition balance và chi phí di chuyển dữ liệu.
- Backup, retention, log, dung lượng index và bộ nhớ cache.
- Backfill khi mở rộng read model hoặc đổi schema.
- Chi phí tính toán đồng bộ khi nguồn thay đổi.

Một view nhỏ có thể đáng giá nếu giảm đáng kể CPU và độ trễ cho Q1, nhưng “nhỏ” phải được xác nhận bằng dữ liệu phân bố thực, đặc biệt khi mỗi khách có metadata nhiều trường hoặc khi số tenant tăng.

## 13. Kiểm tra phân bố: một truy vấn trung bình chưa đủ

Trong dữ liệu seed, `C001` nhận một tỷ lệ đơn đáng kể. Đây là mô hình cố ý tạo **skew** để bộc lộ trường hợp khách hoạt động nhiều.

### 13.1. Đếm số đơn theo khách

~~~javascript
printjson(
  lab.orders_baseline.aggregate([
    {
      $group: {
        _id: {
          tenantId: "$tenantId",
          customerId: "$customerId"
        },
        orderCount: { $sum: 1 }
      }
    },
    { $sort: { orderCount: -1 } },
    { $limit: 10 }
  ]).toArray()
);
~~~

Tập khách có nhiều đơn có thể gây ra:

- Q1 baseline cần index tốt để tránh quét lịch sử dài.
- Nếu chọn **nhúng tất cả đơn vào document khách**, document của khách “nóng” có thể phát triển bất thường và chịu contention.
- Nếu dùng customerId làm **partition key** ở wide-column store, một vài khóa có thể tập trung nhiều dữ liệu hoặc lưu lượng.
- Một read model chứa **chỉ 20 đơn** không tăng vô hạn theo số đơn, nhưng việc cập nhật nó trên khách rất “nóng” có thể làm tập trung ghi.

**Độ lệch phân bố là một yêu cầu kiểm chứng**, không chỉ là đặc tính thống kê. Một mô hình phân vùng hoạt động đều trên dữ liệu đồng đều có thể mất cân bằng mạnh ở dữ liệu sản xuất.

### 13.2. Mô phỏng và đo ở những kích thước khác nhau

Không nên chỉ thử N = 12.000. Hãy lập kế hoạch chạy cùng workload với các quy mô thích hợp, ví dụ 10 nghìn, 100 nghìn, 1 triệu đơn, nếu nguồn lực thử nghiệm cho phép và có ích với dự báo tăng trưởng.

Không suy rằng latency tăng tuyến tính với số document. Chỉ mục B-tree, cache, shard, kích thước file, concurrency và phân bố dữ liệu có thể tạo các **điểm chuyển pha** khi bộ dữ liệu vượt bộ nhớ hoặc một partition trở nên nóng.

Ngoài tổng số bản ghi, nên tăng riêng từng chiều:

- **Số đơn/khách lớn nhất**, giữ tổng số đơn tương tự.
- **Số tenant** và mức không cân bằng giữa tenant lớn/nhỏ.
- **Số dòng sản phẩm/đơn**, để thử giới hạn document/payload.
- **Số trạng thái phổ biến**, ảnh hưởng index theo status.
- **Tần suất cập nhật Q4**, thử read model dưới tải ghi.
- **Dữ liệu lịch sử**, để thử phân trang và truy vấn theo thời gian.

Đây là cách xác định **nguyên nhân gây chậm** thay vì đo một con số tổng hợp rồi phỏng đoán.

## 14. Kiểm chứng cập nhật đồng thời và lỗi giữa chừng

Một mô hình chỉ chạy đúng khi có một người dùng thường chưa đủ cho hệ thống có nhiều request đồng thời.

### 14.1. Các tình huống cần mô phỏng

| Tình huống | Rủi ro |
| --- | --- |
| Hai request cùng chuyển đơn PENDING → PAID | Ghi trùng, sinh hai sự kiện hoặc trừ tiền hai lần |
| Một request sửa trạng thái khi view đang backfill | View ghi đè dữ liệu mới bằng snapshot cũ |
| Một đơn mới được tạo trong lúc cập nhật top 20 | Sắp xếp sai, mất đơn mới hoặc vượt 20 phần tử |
| Transaction cập nhật nguồn thành công nhưng client timeout khi commit | Client retry có thể tạo hành động trùng |
| Consumer nhận event phiên bản 14 trước phiên bản 13 | View bị lùi về trạng thái cũ |
| Tenant khác gửi ID đơn giống nhau | Truy cập sai dữ liệu nếu khóa thiếu tenant scope |
| Worker đồng bộ view bị lỗi vài phút | Q1 trả dữ liệu cũ nếu không có fallback/chính sách stale |

### 14.2. Mô hình nguồn chân lý và version

Nếu dùng read model không đồng bộ, nên có quy tắc như:

~~~text
orders_candidate (nguồn chân lý)
    |
    +-- ghi thay đổi với version/sequence có thứ tự
    |
    +-- phát sự kiện đáng tin cậy (outbox/CDC hoặc tương đương)
             |
             v
       projection worker
             |
             +-- áp dụng sự kiện idempotent
             +-- bỏ qua version đã cũ
             +-- cập nhật customer_recent
             +-- lưu watermark/trạng thái xử lý
~~~

Một event ví dụ:

~~~json
{
  "eventId": "evt-000001",
  "tenantId": "T02",
  "orderId": "ORD-00000007",
  "sourceVersion": 2,
  "type": "ORDER_STATUS_CHANGED",
  "status": "PAID",
  "occurredAt": "2026-11-14T08:00:00Z"
}
~~~

**Không có transaction nào mặc nhiên bao trùm mọi hệ thống và service.** Dù database hỗ trợ transaction nhiều document, đồng bộ qua message broker, cache hoặc search index vẫn cần retry, idempotency, theo dõi lag và đối chiếu.

Nếu view được phép chậm, phải **đo số giây trễ** và tỷ lệ request thấy dữ liệu cũ dưới tải dự kiến. Nếu view phải phản ánh ngay thay đổi, phải kiểm chứng được ràng buộc đó dưới ghi đồng thời và lỗi, không chỉ ở một script chạy tuần tự.

### 14.3. Trường hợp xóa và thay đổi lịch sử

Khi một đơn bị hủy/xóa hoặc đổi customerId (nếu nghiệp vụ cho phép), cần xác định:

- View của khách cũ có loại đơn hay không?
- View của khách mới được xây lại như thế nào?
- Top 20 có được bổ sung đơn đứng thứ 21 khi một đơn top 20 bị loại?
- Dữ liệu từ backfill trước thời điểm xóa có thể làm đơn “sống lại” trong view không?

Cập nhật một phần tử mảng là chưa đủ cho mọi phép biến đổi. Trong nhiều trường hợp, **tính lại top 20 từ nguồn theo customerId** hoặc dùng một cơ chế projection có thứ tự và khả năng rebuild sẽ đơn giản, đáng tin cậy hơn.

## 15. Kiểm chứng phân trang và thứ tự ổn định

Một bộ truy vấn ít bản ghi có thể bỏ qua vấn đề pagination, nhưng hệ thống thật thường có dữ liệu dài nhiều tháng.

### 15.1. Không chỉ dùng createdAt làm thứ tự

Nếu hai đơn có cùng `createdAt`, truy vấn sort chỉ theo thời gian có thể cho thứ tự không ổn định. Thêm `_id` làm khóa phụ:

~~~javascript
lab.orders_baseline.find({
  tenantId: "T01",
  customerId: "C001"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Để phân trang dạng cursor, cần giữ cả cặp (`createdAt`, `_id`) ở bản ghi cuối và lọc bản ghi “cũ hơn” theo đúng thứ tự từ lớn xuống nhỏ:

~~~javascript
// lastCreatedAt và lastId lấy từ phần tử cuối của trang trước.
const lastCreatedAt = new Date("2026-10-03T12:00:00Z");
const lastId = "ORD-00003000";

lab.orders_baseline.find({
  tenantId: "T01",
  customerId: "C001",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .toArray();
~~~

Các giá trị cursor trên là **minh họa**, không phải cursor đảm bảo lấy từ trang trước trong seed. Thực tế phải xây token cursor từ kết quả đã trả và kiểm tra tính hợp lệ của nó.

### 15.2. Offset và keyset pagination

`skip(N)` có thể phải đi qua nhiều bản ghi trước khi tới trang sâu. Keyset pagination dùng khóa sắp xếp giúp tránh chi phí offset lớn trong nhiều workload, nhưng cần xử lý cập nhật dữ liệu giữa các trang và hợp đồng snapshot phù hợp.

Nếu dùng view chỉ giữ 20 đơn mới nhất, nó **không thể phục vụ toàn bộ phân trang lịch sử**. Phải có đường truy vấn quay về collection canonical; không nên đánh giá một mô hình bằng Q1 top 20 rồi tuyên bố nó cũng đáp ứng lịch sử hàng triệu đơn.

## 16. Q5: truy vấn phân tích có thể đòi một đường dữ liệu riêng

**Q5:** tính tổng doanh thu các đơn PAID và SHIPPED theo ngày và tenant trong khoảng thời gian.

Ví dụ aggregation:

~~~javascript
const start = new Date("2026-10-01T00:00:00Z");
const end = new Date("2026-11-01T00:00:00Z");

lab.orders_baseline.aggregate([
  {
    $match: {
      createdAt: { $gte: start, $lt: end },
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        day: {
          $dateToString: {
            format: "%Y-%m-%d",
            date: "$createdAt",
            timezone: "UTC"
          }
        }
      },
      orderCount: { $sum: 1 },
      revenue: { $sum: "$totalAmount" }
    }
  },
  { $sort: { "_id.tenantId": 1, "_id.day": 1 } }
]).toArray();
~~~

Bài toán này quét/tổng hợp nhiều đơn và **không được tăng tốc đáng kể chỉ bằng read model `customer_recent`**. Nó có thể cần thiết kế index riêng, tiền tổng hợp có kiểm soát hoặc pipeline OLAP tùy quy mô.

Cần làm rõ **định nghĩa doanh thu**: trong hệ thực, “đơn đã giao”, “đã thanh toán”, “đã hoàn tiền” và “đã hủy” có quy tắc hạch toán riêng. Đo đúng query nhưng sai định nghĩa doanh thu vẫn là thất bại của mô hình ứng dụng.

**Không ép một collection hoặc một index tối ưu mọi truy vấn**. Quy trình kiểm chứng nên chỉ ra những truy vấn có kiểu tải khác biệt đủ lớn để cần read model hoặc kho dữ liệu chuyên dụng.

## 17. Trường hợp NoSQL dạng wide-column: kiểm chứng khóa và partition

Dù ví dụ thao tác sử dụng MongoDB, cùng phương pháp kiểm chứng áp dụng cho Cassandra, Bigtable và những hệ wide-column khác.

Giả sử bảng lưu sự kiện theo thiết bị:

~~~sql
CREATE TABLE readings_by_device_day (
    device_id text,
    event_day date,
    observed_at timestamp,
    event_id uuid,
    value double,
    PRIMARY KEY ((device_id, event_day), observed_at, event_id)
);
~~~

Truy vấn mục tiêu:

~~~sql
SELECT observed_at, value
FROM readings_by_device_day
WHERE device_id = 'sensor-42'
  AND event_day = '2026-11-14'
  AND observed_at >= '2026-11-14T08:00:00Z'
  AND observed_at <  '2026-11-14T09:00:00Z';
~~~

Cần kiểm chứng những gì?

- **Tính đúng:** số điểm đo trong khoảng, xử lý timestamp trùng và sự kiện đến muộn.
- **Kích thước partition:** bao nhiêu bản ghi của một thiết bị trong một ngày, thiết bị “nóng” sinh bao nhiêu bản ghi?
- **Phân bố key:** thiết bị nào có tốc độ ghi vượt xa trung bình?
- **Đường đọc:** truy vấn nhiều ngày phải chạm bao nhiêu partition, có yêu cầu truy vấn toàn bộ khu vực không?
- **Compaction/tombstone/TTL:** dữ liệu lịch sử và xóa ảnh hưởng hiệu năng thế nào?
- **Consistency level và replication:** đọc/ghi có đáp ứng ràng buộc nhất quán và độ sẵn sàng cần thiết?

Một bảng phân vùng theo deviceId+day có thể tốt với “lịch sử một thiết bị trong một ngày”, nhưng không mặc nhiên thích hợp với “thống kê trung bình mọi thiết bị trong 90 ngày”. Nếu truy vấn thứ hai quan trọng, cần thiết kế một đường dữ liệu khác rồi kiểm chứng **cả hai**.

Điểm chung là **bộ truy vấn quyết định mô hình**, còn bộ dữ liệu đại diện giúp phát hiện những giả định về cardinality và skew không đúng.

## 18. Thiết kế phép thử tải có thể tái lập

Một bảng kết quả có giá trị khi người khác có thể hiểu **đã đo gì trong điều kiện nào**.

### 18.1. Hồ sơ môi trường thử nghiệm

Ghi lại:

| Thông tin | Ví dụ cần ghi |
| --- | --- |
| Database và phiên bản | MongoDB phiên bản cụ thể, storage engine |
| Phần cứng | CPU, RAM, loại đĩa, băng thông |
| Topology | Single node, replica set, sharded cluster |
| Cấu hình | Read/write concern, connection pool, cache |
| Dữ liệu | Số document, số tenant, phân bố khách, kích thước |
| Index | Tên, field, thứ tự và dung lượng index |
| Tải | Số client đồng thời, RPS mục tiêu, phân bố Q1–Q5 |
| Môi trường | Có tác vụ nền, index build, backup, network latency không |
| Đo | Công cụ, thời gian warm-up, thời lượng test, số lần lặp |
| Tính đúng | Điều kiện so sánh kết quả và tỉ lệ request lỗi |

Nếu thông số topology hoặc concurrency thay đổi giữa hai phương án, kết quả latency **không còn là so sánh trực tiếp của riêng mô hình dữ liệu**.

### 18.2. Tách các lớp phép thử

1. **Functional correctness:** kết quả A và B tương đương; gồm edge cases và cập nhật.
2. **Single-request plan inspection:** `explain` để xem index, scan, sort và dữ liệu được đọc.
3. **Read latency under load:** đo Q1/Q2/Q3 với nhiều client, p50/p95/p99.
4. **Write latency and correctness:** đo Q4, chi phí view sync, retry, duplicate/stale.
5. **Mixed workload:** chạy đúng tỷ lệ Q1–Q5; tránh benchmark tất cả là đọc trong khi production ghi nhiều.
6. **Soak/stress:** duy trì tải đủ lâu để quan sát cache, compaction, replication, storage growth và lỗi.
7. **Scale-out/failure:** thử tenant nóng, mất node, rebalance hoặc mạng chậm nếu những tình huống đó nằm trong yêu cầu vận hành.

Đừng dùng một lệnh `explain` làm thay thế cho load test, cũng đừng dùng load test mà bỏ qua tính đúng kết quả.

### 18.3. Một phép thử có kiểm soát

Để so sánh A và B, thay đổi **một nhóm quyết định chính** tại một thời điểm:

~~~text
Thử nghiệm 1:
  A = đơn hàng canonical + index theo Q1/Q3
  B = cùng đơn hàng canonical + cùng index + customer_recent
  Câu hỏi: lợi ích Q1 có đáng chi phí view và cập nhật?

Thử nghiệm 2:
  Giữ A cố định
  Thay index Q1 bằng một thiết kế khác
  Câu hỏi: kế hoạch truy vấn và chi phí index thay đổi ra sao?

Thử nghiệm 3:
  Giữ schema và index
  Tăng mức skew khách nóng
  Câu hỏi: tail latency và contention thay đổi thế nào?
~~~

Nếu đồng thời đổi schema, index, hardware, số lượng dữ liệu và connection pool, rất khó biết **yếu tố nào thực sự tạo khác biệt**.

## 19. Cách lập bảng quyết định sau khi đo

Sau khi chạy thực nghiệm, có thể ghi lại bảng sau; các ô kết quả **phải điền từ lần đo**, không dùng con số minh họa để giả làm quan sát.

| Tiêu chí | A: canonical collection | B: canonical + recent view | Kết luận cần chứng minh |
| --- | --- | --- | --- |
| Q1 p95/p99 | Số đo | Số đo | View có cải thiện đủ lớn không? |
| Q2 latency | Số đo | Số đo | Có tác dụng phụ lên truy vấn khác không? |
| Q3 index scan | Keys/docs examined | Keys/docs examined | Hai phương án có dùng đúng index? |
| Q4 latency | Số đo | Số đo | Chi phí ghi thêm thế nào? |
| Tỷ lệ dữ liệu Q1 stale | Theo hợp đồng | Theo hợp đồng | Có đáp ứng nhất quán yêu cầu không? |
| Throughput ở tải mục tiêu | Số đo | Số đo | Tải hỗn hợp có đạt không? |
| Dung lượng và index | Số đo | Tổng cả view | Chi phí tài nguyên tăng bao nhiêu? |
| Hot customer | Số đo | Số đo | Tập trung đọc/ghi có trở thành nút nghẽn? |
| Phức tạp vận hành | Mô tả | Mô tả | Backfill, rebuild, replay, monitor |

Có thể áp dụng một **quy tắc quyết định trước khi benchmark**:

- Mô hình phải **đạt tính đúng và ràng buộc phân quyền** trước.
- Các SLO quan trọng phải đạt dưới tải dự kiến, kể cả p95/p99 và error rate.
- Chi phí lưu trữ, index và độ phức tạp cập nhật phải ở mức chấp nhận được.
- Trong hai phương án cùng đạt mục tiêu, ưu tiên phương án **đơn giản hơn và dễ vận hành hơn**, trừ khi lợi ích còn lại có giá trị rõ ràng.

Không nên chọn mô hình B chỉ vì Q1 nhanh hơn vài mili-giây trên 12.000 đơn nếu cả hai đã đạt SLO rất thoải mái, trong khi B làm tăng đáng kể độ phức tạp đồng bộ. Ngược lại, nếu Q1 chiếm phần lớn tải và A không đạt SLO, B có thể là ứng viên đáng đầu tư nếu giải quyết tốt tính nhất quán.

## 20. Những lỗi phổ biến khi “kiểm chứng” mô hình

### Chỉ kiểm tra trên 100 document phân bố đều

Bộ dữ liệu quá nhỏ không bộc lộ quét lớn, index thiếu, tài liệu phình to hay partition nóng. Cần thử skew, dữ liệu lịch sử và tải đại diện.

### Tối ưu truy vấn rất hiếm, bỏ qua truy vấn quan trọng

Một truy vấn báo cáo chạy mỗi đêm không nhất thiết được ưu tiên bằng API Q1 gọi hàng nghìn lần/giây. Ngược lại, báo cáo đêm có deadline nghiêm ngặt và dữ liệu lớn vẫn cần đường xử lý riêng. **Ưu tiên dựa trên tác động**, không chỉ độ khó kỹ thuật.

### Thấy index tồn tại thì mặc định truy vấn dùng index đó

Query planner có thể chọn plan khác theo dữ liệu và thống kê. Cần xem plan thực tế và số keys/docs examined; đừng suy ra hiệu quả từ tên index.

### Chỉ đo truy vấn thành công và bỏ qua timeout

Tỷ lệ lỗi, retry, timeout và request quá hạn là một phần của kết quả. Cần tính toàn bộ request và ghi rõ điều kiện loại trừ hợp lệ.

### So sánh hai mô hình có kết quả khác nhau

B trả 20 đơn gần nhất nhưng A trả 100 đơn; B bỏ field item trong khi A trả cả mảng; hoặc B trả trạng thái cũ. Khi đó phép so sánh latency **không công bằng** vì hợp đồng đầu ra không giống nhau.

### Không tính chi phí ghi và duy trì dữ liệu trùng

Read model có thể tăng tốc truy vấn nhưng kéo theo backfill, cập nhật hai nơi, sync lag, index và tình huống dữ liệu mồ côi. Không được gọi mô hình “nhanh hơn” nếu chỉ đo read latency khi production có nhiều ghi.

### Đo trên máy trống rồi ngoại suy tuyến tính sang production

Concurrency, bộ nhớ cache, mạng, partition và I/O có thể tạo nút nghẽn hoàn toàn khác. Cần thử những lớp tải và topology phù hợp.

### Dùng một global average thay cho nhóm khách nóng/lạnh

Một tenant có 100 lần tải so với tenant thường có thể quyết định p99. Phân đoạn metric theo tenant, nhóm độ lớn khách, loại truy vấn và độ chọn lọc để hiểu nguồn gây chậm.

### Đổi nhiều biến cùng lúc

Nếu đổi schema, index, phần cứng và dữ liệu trong cùng một phép thử, không thể quy kết cải thiện cho thiết kế dữ liệu. Dùng thực nghiệm có kiểm soát.

### Không nói rõ mức nhất quán

Một materialized view eventual consistency không được dùng để thay thế nguồn canonical nếu nghiệp vụ yêu cầu trạng thái vừa cập nhật phải hiển thị ngay. Phải nêu và đo **staleness**.

## 21. Bài tập thực hành

### Bài 1. Định nghĩa lại Q1

Yêu cầu ban đầu là “đơn hàng của khách”. Hãy viết lại thành một hợp đồng có: tenant scope, giới hạn kết quả, thứ tự xác định, danh sách field và mức nhất quán sau khi cập nhật trạng thái.

**Gợi ý:** Ví dụ “Trong tenant T, trả 20 đơn mới nhất của customer C, sắp createdAt DESC và _id DESC, gồm id/status/createdAt/totalAmount, không lấy chéo tenant; cập nhật trạng thái phải hiển thị trong thời hạn đã cam kết.”

### Bài 2. Dữ liệu đại diện

Một người thử mô hình với 10.000 đơn, tất cả khách đều có 50 đơn. Production dự kiến có 1% khách sở hữu 40% đơn. Phép thử đang thiếu thuộc tính gì?

**Gợi ý:** Thiếu **skew và nhóm khách rất hoạt động**. Dữ liệu đồng đều không mô phỏng hot keys, mảng cực lớn, phân vùng nóng và tần suất truy vấn tập trung.

### Bài 3. Nhìn executionStats

Giả sử một truy vấn trả 20 đơn nhưng ghi nhận `totalDocsExamined = 100000`. Ta kết luận được điều gì, và chưa kết luận được điều gì?

**Gợi ý:** Truy vấn đang xét rất nhiều document để trả ít kết quả, đáng xem lại filter/index/plan. Tuy nhiên chưa đủ để khẳng định nguyên nhân hoặc mức latency ngoài thực tế; cần thêm plan, byte read, tải, dữ liệu và môi trường.

### Bài 4. Tính đúng của read model

Q4 cập nhật canonical document thành PAID nhưng Q1 đọc từ view vẫn thấy PENDING. Trong trường hợp nào đây là lỗi, trong trường hợp nào có thể là trạng thái tạm chấp nhận được?

**Gợi ý:** Là lỗi khi hợp đồng yêu cầu đọc ngay kết quả ghi. Có thể tạm chấp nhận nếu sản phẩm công bố eventual consistency và view bắt kịp trong thời gian cho phép; khi đó vẫn phải đo lag và xử lý sự kiện trễ.

### Bài 5. Chỉ mục theo hai truy vấn

Một API lọc `tenantId + customerId` và sort `createdAt DESC`; một API khác lọc `tenantId + status` và sort `createdAt ASC`. Vì sao không nên mặc định một index ghép duy nhất đáp ứng tối ưu cả hai?

**Gợi ý:** Các trường lọc và chiều sắp xếp khác nhau, nên thứ tự field trong index có thể phù hợp với truy vấn này nhưng không phù hợp truy vấn kia. Cần xây ứng viên index theo workload và xem kế hoạch thực thi.

### Bài 6. Quyết định mô hình

Kết quả đo giả định cho thấy A đáp ứng SLO của Q1 và Q2, có chi phí thấp; B cải thiện Q1 một chút nhưng có nguy cơ stale read và phải viết thêm pipeline projection. Nên chọn mô hình nào?

**Gợi ý:** Nếu cả hai đạt yêu cầu và phần cải thiện Q1 không đủ giá trị để bù thêm rủi ro/chi phí, A đơn giản hơn thường là lựa chọn hợp lý. Tuy nhiên quyết định cuối cần dựa trên tiêu chí chấp nhận đã thống nhất và số liệu thực.

### Bài 7. Quy mô dữ liệu

Nếu tăng từ 12.000 lên 12 triệu đơn nhưng giữ nguyên 200 khách/tenant, điều gì không còn đại diện cho hệ thống thực trong nhiều trường hợp?

**Gợi ý:** Một khách có thể tích lũy số đơn phi thực tế, và tỉ lệ cardinality giữa số khách và số đơn có thể thay đổi. Cần mở rộng nhiều chiều phù hợp: số tenant, số khách, phân bố đơn/khách, thời gian lịch sử và traffic; không chỉ nhân một biến N.

### Bài 8. Thiết kế một phép thử đầy đủ

Hãy mô tả một thử nghiệm kiểm chứng hai mô hình trên Q1/Q4 với dữ liệu gồm khách thường và khách nóng, tải đọc/ghi hỗn hợp. Đầu ra phải có:

- Các chỉ số đúng kết quả và tỉ lệ stale.
- Latency p50/p95/p99 và throughput.
- Số document/keys examined ở Q1.
- Tổng dung lượng dữ liệu và index.
- Điều kiện tải, thời lượng test, concurrency.
- Một quy tắc quyết định đã chọn **trước khi nhìn kết quả**.

**Gợi ý:** Chỉ kết luận B đáng dùng nếu lợi ích về Q1 rõ ràng, không vi phạm hợp đồng nhất quán và tổng chi phí nằm trong giới hạn đã được chấp nhận.

## 22. Quy trình làm việc có thể lặp lại cho một mô hình NoSQL mới

Khi gặp một bài toán thực tế, có thể áp dụng tuần tự:

1. **Thu thập truy vấn:** liệt kê các yêu cầu đọc/ghi, bộ lọc, thứ tự, số kết quả, tần suất và cam kết nhất quán.
2. **Đặt tiêu chí:** SLO latency/throughput, yêu cầu đúng dữ liệu, chi phí lưu trữ và giới hạn vận hành.
3. **Thu thập phân bố:** cardinality, tỉ lệ hot key, kích thước dữ liệu, tần suất thay đổi và xu hướng tăng trưởng.
4. **Tạo các phương án mô hình:** cấu trúc canonical, nhúng/tham chiếu, khóa phân vùng, index và read model phục vụ truy vấn quan trọng.
5. **Sinh dữ liệu đại diện:** dùng cùng nguồn dữ liệu, kiểm soát skew và bao phủ trường hợp biên.
6. **Đối chiếu tính đúng:** cùng đầu vào phải cho cùng kết quả nghiệp vụ, bao gồm phân quyền và cập nhật.
7. **Đo đường truy cập:** execution plan, scan, index, số lượt đọc/ghi, bytes.
8. **Đo tải thực tế:** percentile latency, throughput, lỗi, concurrency, chi phí view và điểm nóng.
9. **Thử tăng trưởng và lỗi:** dữ liệu lớn, tenant nóng, ghi đồng thời, sự cố đồng bộ, backfill và retry.
10. **Ra quyết định có bằng chứng:** so sánh với tiêu chí đã đặt, ghi lại trade-off và điều kiện phải kiểm chứng lại trong tương lai.

**Thông điệp cốt lõi:** thiết kế theo truy vấn không kết thúc khi viết xong schema. Một mô hình chỉ được xác nhận phù hợp khi **bộ truy vấn đại diện chạy đúng, đạt yêu cầu trên dữ liệu có phân bố thực tế và không tạo ra chi phí hoặc rủi ro vượt mức chấp nhận**. Dùng truy vấn, dữ liệu và số đo làm bằng chứng — thay vì dựa vào trực giác rằng một kiểu document, index hoặc partition “chắc chắn nhanh”.
