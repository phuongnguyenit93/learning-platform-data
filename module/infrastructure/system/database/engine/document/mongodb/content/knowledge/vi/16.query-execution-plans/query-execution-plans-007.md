# So sánh kế hoạch trước sau trên bộ dữ liệu đại diện

Khi tối ưu MongoDB, một thay đổi như thêm compound index, đổi thứ tự field trong index, viết lại filter hoặc thêm projection có thể làm truy vấn chạy nhanh hơn đáng kể. Nhưng việc thấy `IXSCAN` thay cho `COLLSCAN` trong `explain()` **chưa đủ** để kết luận tối ưu thành công. Cần trả lời những câu hỏi thực tế hơn:

- Truy vấn có trả **đúng dữ liệu và đúng thứ tự** như trước không?
- MongoDB phải xem xét bao nhiêu **index key** và bao nhiêu **document**?
- Có phải sort trên tập lớn, hay có thể đi theo thứ tự index?
- Sự cải thiện xuất hiện với dữ liệu **có phân bố giống production** hay chỉ với vài chục bản ghi thử?
- Thời gian cải thiện có ổn định qua nhiều lần đo, khi cache nóng/lạnh và khi nhiều request đồng thời?
- Index mới tăng bao nhiêu chi phí ghi, RAM và dung lượng đĩa?
- Query planner có thật sự chọn kế hoạch mới trong ứng dụng, hay kế hoạch tốt chỉ xuất hiện khi dùng `hint()`?

Bài học trình bày quy trình **so sánh trước – sau (before/after)** dựa trên dataset đại diện và một workload truy vấn rõ ràng. Trọng tâm là cách **thu thập bằng chứng**, diễn giải `explain("executionStats")`, tránh những thử nghiệm gây hiểu nhầm, và đưa ra quyết định index/query có thể kiểm chứng.

> Nguyên tắc xuyên suốt: **Giữ ổn định dữ liệu, câu truy vấn và môi trường; thay đổi một yếu tố có chủ đích; đo nhiều chỉ số và nhiều tình huống; chỉ kết luận trong phạm vi đã đo.**

## 1. Vì sao phải dùng bộ dữ liệu đại diện?

Một query trên collection có 30 document có thể chạy nhanh dù dùng `COLLSCAN`. Nhưng khi tăng lên 30 triệu document, việc quét toàn collection cho một endpoint chỉ trả 20 đơn hàng thường trở thành vấn đề lớn.

Ngược lại, một index có vẻ tốt khi dữ liệu phân bố đều có thể không giúp nhiều nếu production có một tenant khổng lồ, một trạng thái chiếm 95% record hoặc các document chứa array dài làm index trở thành multikey.

### 1.1. Những thuộc tính cần đại diện

Một dataset hữu ích không chỉ có **số lượng document**, mà còn có **hình dạng và phân bố** gần workload thực tế:

| Thuộc tính | Ví dụ cần mô phỏng | Tác động đến query plan |
|---|---|---|
| Số document | 100 nghìn, 10 triệu hoặc quy mô thực tế | Chi phí `COLLSCAN`, độ sâu page |
| Kích thước BSON | Document vài trăm byte, có nhóm vài chục KB | I/O, cache, FETCH |
| Phân bố tenant | Tenant A chiếm 80%, tenant khác ít hơn | Selectivity theo tenant |
| Phân bố trạng thái | 70% `PAID`, 25% `PENDING`, 5% `CANCELLED` | Selectivity và tính hữu ích của index |
| Phân bố thời gian | Tập trung gần đây, mùa cao điểm | Range scan, sort, giới hạn kết quả |
| Khóa trùng nhau | Nhiều record có cùng `createdAt` | Tie-breaker và sort |
| Giá trị `null`/missing | Một số record không có `category` | Khả năng index/filter, semantics |
| Array/embedded data | `items` có 1–20 phần tử | Multikey index, fetch |
| Update/delete | Document thường xuyên đổi trạng thái | Index maintenance, kế hoạch theo dữ liệu mới |
| Hot keys | Một user/tenant có tần suất truy cập rất lớn | Cache, contention, p95/p99 |
| Index hiện có | `_id`, compound, partial, multikey | Lựa chọn của planner |

Một dataset **đồng đều một cách giả tạo** có thể dẫn đến lựa chọn index sai. Ví dụ, trong production 90% đơn hàng đều có `status: "PAID"`, thì index chỉ trên `status` có thể ít chọn lọc. Nếu dữ liệu test chia ba trạng thái bằng nhau, bạn có thể đánh giá quá cao index này.

### 1.2. Dữ liệu thử phải bảo toàn tính riêng tư

Khi cần tái hiện phân bố production, nên ưu tiên:

1. Dữ liệu tổng hợp nhưng giữ cardinality, histogram, độ lệch và kích thước gần thực tế.
2. Dữ liệu đã được ẩn danh theo quy trình được phê duyệt.
3. Subset được lấy mẫu theo **tầng phân bố**, không chỉ lấy 10.000 record đầu.

Không sao chép thông tin cá nhân, token, mật khẩu hoặc payload nhạy cảm sang môi trường benchmark không được bảo vệ. Việc thay tên thật bằng một tên giả chưa chắc là ẩn danh đầy đủ nếu các thuộc tính khác có thể tái nhận diện.

### 1.3. Lấy mẫu ngẫu nhiên đơn giản có thể bỏ lỡ long tail

Nếu 80% traffic thuộc một nhóm tenant lớn nhưng chỉ 20% số tenant có phân bố tương tự, sampling theo số tenant có thể làm workload giả trở nên quá đều. Nên kiểm tra đồng thời:

- Phân bố **số document**;
- Phân bố **số request** theo nhóm;
- Tỷ lệ query có filter, sort, projection, limit;
- Tỷ lệ tenant lớn/nhỏ, key nóng/lạnh;
- Các trường hợp biên như date range nhiều tháng, status hiếm, user không có event.

**Dataset đại diện** và **workload đại diện** là hai khía cạnh riêng: dữ liệu giống production nhưng benchmark chỉ một truy vấn hiếm vẫn không đủ.

## 2. Bắt đầu bằng giả thuyết có thể kiểm chứng

Giả sử API lấy 50 đơn hàng đã thanh toán mới nhất của một tenant trong tháng:

```javascript
db.orders.find(
  {
    tenantId: "TENANT-A",
    status: "PAID",
    createdAt: {
      $gte: ISODate("2026-03-01T00:00:00Z"),
      $lt: ISODate("2026-04-01T00:00:00Z")
    }
  },
  {
    _id: 1,
    createdAt: 1,
    total: 1,
    status: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(50);
```

Giả thuyết:

> Index `{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }` sẽ giúp MongoDB giới hạn dữ liệu theo tenant và status, duyệt khoảng createdAt theo thứ tự cần trả, giảm document examined và tránh sort lớn so với collection scan.

Một giả thuyết tốt cần nêu:

- **Workload:** query chính xác và tần suất;
- **Thay đổi:** index nào được thêm hoặc query được viết lại ra sao;
- **Chỉ số kỳ vọng:** số keys/docs examined, latency, sort, memory;
- **Rủi ro:** chi phí index và write amplification;
- **Tiêu chí quyết định:** cải thiện ở những biến thể query quan trọng mà không làm xấu đi đáng kể workload khác.

**Không đo khi chưa biết mình đang kiểm chứng điều gì.** “Tạo index rồi xem có nhanh hơn không” quá mơ hồ để đưa ra kết luận vận hành.

## 3. Kịch bản thử nghiệm: tạo collection riêng

Các ví dụ sau dùng collection **`planLabOrders`**, chỉ để thử nghiệm. Không chạy lệnh `drop()` trên collection production hoặc collection có dữ liệu cần giữ.

Mục tiêu của script:

- 120.000 document để kế hoạch `COLLSCAN` và `IXSCAN` có khác biệt đáng quan sát hơn một collection vài chục record;
- Tenant A chiếm khoảng 80%, B khoảng 15%, C khoảng 5%;
- Trạng thái `PAID` phổ biến, `PENDING` trung bình, `CANCELLED` hiếm;
- Ngày tạo nằm trong khoảng nhiều tháng, có nhiều timestamp bằng nhau;
- Một phần record chứa payload lớn hơn;
- Bộ sinh số giả ngẫu nhiên có **seed cố định** để chạy lại tạo phân bố tương tự.

### 3.1. Tạo dữ liệu tổng hợp bằng mongosh

```javascript
// CHỈ CHẠY TRÊN DB THỬ NGHIỆM.
// Lệnh drop() sẽ xóa toàn bộ collection planLabOrders nếu tồn tại.
db.planLabOrders.drop();

const totalDocs = 120000;
const batchSize = 1000;
const baseTime = Date.parse("2026-01-01T00:00:00Z");
const dayMillis = 24 * 60 * 60 * 1000;

let seed = 20261114;

// Bộ sinh số giả ngẫu nhiên có seed cố định.
// Math.imul và >>> 0 giữ giá trị ở miền uint32.
function rnd() {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 4294967296;
}

function chooseTenant(x) {
  return x < 0.80
    ? "TENANT-A"
    : (x < 0.95 ? "TENANT-B" : "TENANT-C");
}

function chooseStatus(x) {
  return x < 0.70
    ? "PAID"
    : (x < 0.95 ? "PENDING" : "CANCELLED");
}

let batch = [];

for (let i = 0; i < totalDocs; i++) {
  // Khoảng 180 ngày, giờ/phút/giây giả lập từ giá trị i.
  const daysFromStart = Math.floor(rnd() * 180);
  const secondsInDay = i % 86400;
  const createdAt = new Date(
    baseTime + daysFromStart * dayMillis + secondsInDay * 1000
  );

  const tenantId = chooseTenant(rnd());
  const status = chooseStatus(rnd());
  const total = Math.floor(rnd() * 4000000) + 10000;

  batch.push({
    tenantId: tenantId,
    status: status,
    createdAt: createdAt,
    total: total,
    customerId: "C-" + (i % 18000),
    category: i % 7 === 0 ? "PRIORITY" : "STANDARD",
    itemCount: 1 + (i % 8),
    note: i % 20 === 0 ? "x".repeat(2000) : "ok",
    source: {
      channel: i % 4 === 0 ? "MOBILE" : "WEB",
      importBatch: Math.floor(i / batchSize)
    }
  });

  if (batch.length === batchSize) {
    db.planLabOrders.insertMany(batch, { ordered: false });
    batch = [];
  }
}

if (batch.length > 0) {
  db.planLabOrders.insertMany(batch, { ordered: false });
}

print("Inserted: " + db.planLabOrders.countDocuments({}));
```

Script tạo nhiều document với `_id` do MongoDB/driver bổ sung. Các _id phải được giữ ổn định trong một phiên so sánh. Nếu chạy lại script, nó xóa và tạo collection mới; điều này không phải phép so sánh trên **đúng cùng các BSON record** của lần chạy trước, nên các so sánh quan trọng nên được thực hiện **trong cùng một lần seed**.

### 3.2. Vì sao seed phải cố định nhưng vẫn chưa đủ?

Seed cố định giúp:

- Lần chạy lại có tỷ lệ tenant/status gần như tương tự.
- So sánh script/query dễ hơn.
- Giảm một nguồn thay đổi không mong muốn.

Tuy nhiên, nó không giữ cố định mọi yếu tố: giá trị `_id`, trạng thái cache, vị trí record, index build, tải hệ thống và phiên bản MongoDB có thể khác. Nếu cần A/B nghiêm ngặt, nên dùng cùng collection snapshot hoặc cùng dataset đã materialize, và đo xen kẽ các kế hoạch trên dữ liệu không đổi.

### 3.3. Xem phân bố của dữ liệu thử

Không được giả định dữ liệu tổng hợp đúng phân bố chỉ vì code định nghĩa tỷ lệ. Có thể quan sát:

```javascript
db.planLabOrders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Xem phạm vi thời gian:

```javascript
db.planLabOrders.aggregate([
  {
    $group: {
      _id: null,
      minCreatedAt: { $min: "$createdAt" },
      maxCreatedAt: { $max: "$createdAt" },
      total: { $sum: 1 }
    }
  }
]);
```

Xem kích thước collection và index (các trị số thay đổi theo engine/phiên bản):

```javascript
db.planLabOrders.stats();
db.planLabOrders.getIndexes();
```

Các lệnh này là công cụ khảo sát dataset, **không thay thế benchmark truy vấn**. Những phần sau giả định dataset đã được tạo và không bị tiến trình khác chỉnh sửa trong giai đoạn before/after.

## 4. Đóng băng query shape trước khi đo

Một phép so sánh hợp lệ yêu cầu hai phía cùng **trả cùng loại kết quả**.

Định nghĩa query:

```javascript
const filter = {
  tenantId: "TENANT-A",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
};

const projection = {
  _id: 1,
  createdAt: 1,
  status: 1,
  total: 1
};

const sort = { createdAt: -1, _id: -1 };
const limit = 50;
```

Trong mọi phép đo so sánh kế hoạch chính:

- Filter phải giữ nguyên các field, toán tử và giá trị.
- Projection giữ nguyên: thêm/bỏ một field có thể biến query thành covered hoặc cần FETCH.
- Sort và hướng sort giữ nguyên.
- `limit` và `skip` (nếu có) giữ nguyên.
- Collation, read concern/read preference, cấu hình session và driver phải được ghi nhận.
- Query phải chạy trên **cùng trạng thái dữ liệu** nếu mục đích là đo riêng ảnh hưởng index.

Nếu thay cả query lẫn index đồng thời, bạn có thể chứng minh “giải pháp tổng thể mới nhanh hơn”, nhưng không thể phân biệt phần cải thiện nào đến từ index, phần nào đến từ điều kiện query.

### 4.1. Xác định kết quả đúng trước khi tối ưu

Một query nhanh nhưng trả thiếu document là sai về nghiệp vụ. Cần xác nhận:

- Kết quả thuộc đúng tenant và trạng thái.
- `createdAt` nằm trong khoảng nửa mở `[start, end)` như đặc tả.
- Thứ tự giảm theo `createdAt`, rồi `_id`.
- Không vượt quá 50 document.
- Projection không làm thiếu field client thực sự cần.

Ví dụ: nếu query trước lọc `status: "PAID"` còn query sau bỏ field đó để tận dụng index, kết quả không tương đương và không thể đem latency ra so sánh như một tối ưu đúng.

## 5. Đo kế hoạch trước khi thêm index

Trên collection test mới chỉ có index mặc định `_id`, chạy:

```javascript
const before = db.planLabOrders.find(
  filter,
  projection
)
.sort(sort)
.limit(limit)
.explain("executionStats");

printjson(before);
```

Với query lọc tenant, status và khoảng createdAt, nếu không có index thích hợp, plan có thể gồm:

```text
COLLSCAN
   |
  FILTER (tenantId, status, createdAt)
   |
  SORT (createdAt DESC, _id DESC)
   |
  LIMIT 50
```

Đây chỉ là sơ đồ trực quan; MongoDB có thể hiển thị stage theo thứ tự, cấu trúc hoặc tên khác tùy **classic engine/SBE**, phiên bản và cách tối ưu `SORT + LIMIT`.

Điều kỳ vọng từ baseline là MongoDB phải xem nhiều document để tìm record khớp và sắp xếp các ứng viên phù hợp. Nhưng không ghi trước số đo tưởng tượng như “120.000 docs examined” nếu chưa có output thực tế.

### 5.1. Các giá trị trong explain cần ghi

```javascript
const s = before.executionStats;

printjson({
  nReturned: s.nReturned,
  totalKeysExamined: s.totalKeysExamined,
  totalDocsExamined: s.totalDocsExamined,
  executionTimeMillis: s.executionTimeMillis
});
```

Một baseline **minh họa giả định**, không phải kết quả từ script đã chạy:

| Chỉ số | Trước index (ví dụ minh họa) |
|---|---:|
| `nReturned` | 50 |
| `totalKeysExamined` | 0 |
| `totalDocsExamined` | 120.000 |
| `executionTimeMillis` | 85 ms |
| Kế hoạch | `COLLSCAN` + sort |

Chỉ dùng bảng để hình dung cách đọc. Số liệu thật thay đổi theo máy, bản MongoDB, bộ nhớ đệm, mức tải và dữ liệu.

### 5.2. Đọc `nReturned` đúng nghĩa

`nReturned` là số document kế hoạch thực thi trả về. Khi query có `limit(50)` và thực tế có hàng nghìn record khớp, `nReturned` chỉ là 50; nó **không nói rằng tổng số document thỏa filter chỉ có 50**.

Để biết độ chọn lọc tổng của filter, có thể đo `countDocuments(filter)` riêng. Nhưng đây là một query khác, cần được đánh giá riêng và có thể tốn tài nguyên. Tránh đưa count vào thời gian của query pagination chính nếu ứng dụng không thực hiện count cùng đường code.

### 5.3. Vì sao `executionTimeMillis` chưa đủ?

`executionTimeMillis` trong explain có giá trị tham khảo, nhưng có thể bị ảnh hưởng bởi:

- Thời điểm thử nghiệm, cache và tài nguyên máy;
- Việc planner thử nhiều candidate;
- Số record được tiêu thụ trong chế độ explain;
- Server load và trạng thái lưu trữ;
- Phiên bản query engine và cách công cụ báo thời gian.

Nó **không phải một chỉ số hoàn chỉnh** thay thế p95/p99 latency nhìn từ ứng dụng. Phải kết hợp plan statistics với benchmark thực thi có tiêu thụ kết quả.

## 6. Thêm compound index sau khi đã có baseline

Sau khi lưu số liệu trước:

```javascript
db.planLabOrders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_tenant_status_created_id"
  }
);
```

Index có:

1. `tenantId` và `status`: hai điều kiện bằng nhau, thường được ưu tiên trong prefix.
2. `createdAt` giảm: hỗ trợ range trên ngày cùng thứ tự sort.
3. `_id` giảm: tie-breaker cho nhiều document trùng ngày/giờ, giúp sort có thứ tự xác định.

Index này được chọn theo một **query shape cụ thể**, không có nghĩa mọi query trên collection đều được tối ưu.

Chạy lại query y hệt:

```javascript
const after = db.planLabOrders.find(
  filter,
  projection
)
.sort(sort)
.limit(limit)
.explain("executionStats");

printjson(after);
```

Nếu planner tận dụng index theo kỳ vọng, có thể thấy đường đi tương tự:

```text
IXSCAN idx_tenant_status_created_id
   |
  FETCH (vì projection cần total ngoài index)
   |
  LIMIT / PROJECTION
```

Index có thể cung cấp thứ tự `createdAt DESC, _id DESC` sau prefix equality, từ đó tránh một **blocking SORT** lớn trong trường hợp phù hợp. Nhưng không được khẳng định mọi MongoDB version hiển thị đúng chuỗi stage trên, hoặc query planner chắc chắn chọn index mới: hãy dựa vào output thực tế.

### 6.1. Sau index không phải lúc nào cũng bằng 0 docs examined

Projection của ví dụ có `total: 1`, nhưng index chỉ gồm tenantId, status, createdAt và _id. Vì MongoDB phải lấy `total` từ document, query có thể có `FETCH` và `totalDocsExamined` lớn hơn 0.

Với limit 50 và index đủ tốt, MongoDB có thể chỉ cần fetch số document gần với số record trả, thay vì xem phần lớn collection. **Mục tiêu là giảm công việc thừa**, không bắt buộc `totalDocsExamined = 0` trong mọi query.

### 6.2. Covered query là một thí nghiệm riêng

Nếu chỉ cần field có trong index:

```javascript
db.planLabOrders.find(
  filter,
  {
    tenantId: 1,
    status: 1,
    createdAt: 1,
    _id: 1
  }
)
.sort(sort)
.limit(limit)
.explain("executionStats");
```

Trong điều kiện phù hợp, query có thể được index cover và có `totalDocsExamined: 0`. Tuy nhiên, **projection đã khác** so với query có `total`, nên không được dùng con số này để kết luận chỉ riêng việc thêm index đã cải thiện query gốc tới mức nào.

Nếu API thực sự không cần `total`, đổi projection là một tối ưu hợp lệ; nhưng cần báo cáo đó là **thay đổi thứ hai**.

## 7. So sánh các số liệu trước và sau một cách đúng đắn

Khi có hai output, lập bảng:

| Chỉ số | Before | After | Cách diễn giải |
|---|---:|---:|---|
| `nReturned` | Giá trị đo | Giá trị đo | Kiểm tra cùng số lượng mong đợi |
| `totalKeysExamined` | Giá trị đo | Giá trị đo | Chi phí duyệt index |
| `totalDocsExamined` | Giá trị đo | Giá trị đo | Chi phí kiểm tra/fetch document |
| `executionTimeMillis` | Giá trị đo | Giá trị đo | Tín hiệu thời gian của explain |
| Có `COLLSCAN`? | Có/không | Có/không | Có quét toàn collection không |
| Có `IXSCAN`? | Có/không | Có/không | Dùng index nào |
| Có `SORT` blocking? | Có/không | Có/không | Có phải sắp xếp tập trung gian không |
| Có `FETCH`? | Có/không | Có/không | Cần document ngoài index không |
| Index size | Giá trị đo | Giá trị đo | Chi phí lưu trữ thêm |
| Latency thực ở client | Giá trị đo | Giá trị đo | Trải nghiệm ứng dụng |

### 7.1. Tỷ lệ examined/returned

Nếu `nReturned > 0`, một tỷ lệ tham khảo:

```text
docsPerResult = totalDocsExamined / nReturned
keysPerResult = totalKeysExamined / nReturned
```

Ví dụ giả định:

```text
Before:
  nReturned = 50
  totalDocsExamined = 120000
  docsPerResult = 2400

After:
  nReturned = 50
  totalDocsExamined = 50
  totalKeysExamined = 50
  docsPerResult = 1
  keysPerResult = 1
```

Điều này cho thấy **công việc đọc thừa giảm mạnh** trong ví dụ. Nhưng một query chỉ trả 1 record hiếm có thể vẫn phải examine nhiều key hợp lý; dùng tỷ lệ theo cùng query shape/độ chọn lọc, không đặt một ngưỡng chung như “mọi query phải dưới 2”.

Nếu `nReturned = 0`, không tính tỷ lệ bằng phép chia cho 0; cần xét số key/doc examined và ý nghĩa truy vấn không có kết quả.

### 7.2. Phần trăm cải thiện thời gian

Có thể báo:

```text
improvementPct = (beforeMs - afterMs) / beforeMs * 100%
speedup = beforeMs / afterMs
```

Nếu before là 100 ms và after là 25 ms:

```text
Giảm latency = 75%
Speedup = 4 lần
```

Nhưng nếu chỉ đo một lần, đây mới là phép tính từ một quan sát. Để kết luận có tính vận hành, cần nhiều lần chạy, phân bố latency và mức biến thiên.

### 7.3. Không xem `keysExamined = 0` là luôn tốt

Một `COLLSCAN` có thể có `totalKeysExamined = 0` nhưng `totalDocsExamined` rất lớn. Ngược lại, một query dùng index có thể xem vài nghìn keys và chỉ fetch 50 document; đó thường là cải thiện đáng kể.

Phải đọc hai chỉ số **cùng nhau**, không chọn số nhỏ nhất của một chỉ số đơn lẻ.

## 8. Tìm các stage quan trọng trong explain

Kết quả `explain()` có thể có cấu trúc phức tạp. Những vùng thường gặp:

- `queryPlanner`: thông tin planner, `winningPlan` và các rejected plans khi có;
- `executionStats`: số liệu thực thi của kế hoạch trong chế độ được yêu cầu;
- `executionStats.executionStages`: cây stage ở định dạng tùy engine;
- `serverInfo`, index filters, query shape hoặc metadata khác tùy phiên bản.

### 8.1. COLLSCAN

`COLLSCAN` nghĩa là quét collection. Nó không phải lúc nào cũng xấu:

- Query cần trả phần lớn document;
- Collection rất nhỏ;
- Không có filter chọn lọc;
- Việc truy cập index rồi fetch gần toàn bộ collection đắt hơn một sequential scan.

Vì vậy, mục tiêu không phải “loại mọi COLLSCAN” mà là **giảm tổng chi phí của những query có SLA quan trọng**.

### 8.2. IXSCAN

`IXSCAN` nghĩa là duyệt index. Cần quan sát **indexName**, điều kiện bounds và số key examined.

Có index scan không đồng nghĩa hiệu quả. Một index có thứ tự trường không phù hợp có thể phải duyệt hàng trăm nghìn key rồi vẫn fetch nhiều document. Ví dụ index `{ status: 1 }` thường không tối ưu cho query “PAID của tenant A trong một tháng, sorted by createdAt” nếu PAID chiếm 70% collection.

### 8.3. FETCH

`FETCH` thể hiện việc lấy document (hoặc xác minh điều kiện) ngoài phần có trong index, tùy engine. Nếu index chỉ chứa `tenantId` và `status` nhưng projection cần `total`, `createdAt` và `customerId`, MongoDB có thể phải fetch document.

Một số `FETCH` là **đúng và cần thiết**. Nếu chỉ fetch 50 document thay vì hàng chục nghìn, query có thể rất tốt dù không covered.

### 8.4. SORT

Một stage `SORT` có thể báo rằng dữ liệu phải được sắp xếp thay vì chỉ đọc theo thứ tự index. Với `limit(50)`, engine có thể dùng **top-k sort** để tối ưu bộ nhớ; chi tiết stage tùy phiên bản.

Đừng chỉ nhìn tên SORT; hãy xem số lượng candidate, memory/spill nếu được báo và latency. Một sort trên 20 record không giống sort trên 2 triệu record.

### 8.5. Các engine và phiên bản khác nhau

Ở các bản MongoDB hiện đại, explain có thể xuất hiện những tên stage/định dạng khác như `PROJECTION_COVERED`, `PROJECTION_SIMPLE`, `LIMIT`, `SORT_KEY_GENERATOR`, `EQ_LOOKUP`, `EXPRESS_IXSCAN` hoặc phần `slotBasedPlan`.

Điều quan trọng là **ngữ nghĩa**: có quét collection không, có index lookup không, có fetch document không, có sort blocking không, và bao nhiêu key/document được examine. Không viết tool so sánh chỉ dựa vào một đường dẫn JSON cố định mà không tính đến phiên bản server.

## 9. So sánh công bằng bằng hint trên cùng trạng thái dữ liệu

So sánh before và after ở hai thời điểm có thể bị nhiễu: việc build index làm nóng cache, hệ thống thay đổi tải hoặc dữ liệu bị ghi thêm giữa hai lần.

Một phép thử bổ sung là **sau khi tạo index**, sử dụng `hint()` để yêu cầu hai cách truy cập khác nhau trên **cùng dữ liệu**:

```javascript
// Ép dùng collection scan trong môi trường thử.
const scanPlan = db.planLabOrders.find(
  filter,
  projection
)
.sort(sort)
.limit(limit)
.hint({ $natural: 1 })
.explain("executionStats");

// Ép index ứng viên.
const indexPlan = db.planLabOrders.find(
  filter,
  projection
)
.sort(sort)
.limit(limit)
.hint("idx_tenant_status_created_id")
.explain("executionStats");

printjson({
  scan: {
    keys: scanPlan.executionStats.totalKeysExamined,
    docs: scanPlan.executionStats.totalDocsExamined,
    ms: scanPlan.executionStats.executionTimeMillis
  },
  index: {
    keys: indexPlan.executionStats.totalKeysExamined,
    docs: indexPlan.executionStats.totalDocsExamined,
    ms: indexPlan.executionStats.executionTimeMillis
  }
});
```

**Ý nghĩa:** hint cho phép xem kế hoạch scan và kế hoạch index trên cùng trạng thái collection. Nhưng:

- `hint({ $natural: 1 })` là cách ép truy cập theo natural order ở tình huống phù hợp, không phải cách tự động tái tạo hoàn toàn mọi chi tiết của baseline cũ.
- Ép index có thể tạo plan **tệ hơn** kế hoạch planner tự chọn.
- Kết quả hint chỉ chứng minh kế hoạch có điều kiện của **thí nghiệm**, không chứng minh ứng dụng sẽ tự dùng index đó.
- Hãy đo thêm **không hint** để biết plan mặc định sau tối ưu.

Không đưa hint vào production chỉ vì kết quả benchmark nhỏ; nó có thể chặn planner chọn index tốt hơn khi phân bố dữ liệu và truy vấn thay đổi.

### 9.1. Explain và plan cache

`explain()` thường **không dùng plan cache để chọn kế hoạch theo cách một truy vấn thông thường dùng** và không ghi kế hoạch winning của explain vào plan cache như một lần chạy thường. Vì thế, `explain()` hữu ích để xem cách planner đánh giá query nhưng **không đủ** để kết luận ứng dụng đang sử dụng plan cache nào hay sẽ có latency giống hệt.

Khi cần nghiên cứu plan cache thực tế, kết hợp số liệu từ truy vấn thật, công cụ theo dõi query, plan cache metadata/command tương ứng với phiên bản đang dùng và so sánh execution behavior.

Không tùy tiện clear plan cache trên production chỉ để “đo lại”, vì điều này có thể làm hệ thống phải chọn lại plan và ảnh hưởng latency diện rộng.

## 10. Đo thời gian chạy thực, không chỉ explain

Một thí nghiệm nên có hai lớp:

1. **Explain:** giúp phân tích vì sao query thực hiện ít/nhiều công việc.
2. **Benchmark ứng dụng:** đo latency thực khi code tiêu thụ kết quả, qua network/driver/serialization trong điều kiện tương tự sản phẩm.

Ví dụ phép đo đơn giản bằng `mongosh`:

```javascript
function runTimedQuery(hintName) {
  const startedAt = Date.now();

  let cursor = db.planLabOrders.find(
    filter,
    projection
  )
  .sort(sort)
  .limit(limit);

  if (hintName !== null) {
    cursor = cursor.hint(hintName);
  }

  let count = 0;

  while (cursor.hasNext()) {
    cursor.next();
    count++;
  }

  return {
    elapsedMillis: Date.now() - startedAt,
    returned: count
  };
}

printjson(runTimedQuery(null));
printjson(runTimedQuery("idx_tenant_status_created_id"));
```

Ví dụ này tiêu thụ toàn bộ result của query giới hạn 50 record, thay vì chỉ đo thời gian xây đối tượng cursor. Nhưng nó vẫn chỉ là **microbenchmark đơn luồng**. Nó chưa đo đúng latency của HTTP endpoint, business logic, connection pool hoặc độ cạnh tranh từ request khác.

### 10.1. Đo lặp lại và dùng median/p95

Một lần đo có thể bị ảnh hưởng bởi scheduler, page fault, garbage collection hoặc cache. Nên:

- Warm-up nhiều lần trước khi lấy mẫu.
- Đo ít nhất hàng chục lần trong môi trường ít nhiễu.
- Lưu **toàn bộ mẫu**, không chỉ số trung bình.
- Báo median (p50), p95 và khoảng biến động.
- So sánh cùng query shape, cùng số kết quả và cùng phương thức tiêu thụ cursor.
- Chạy xen kẽ các biến thể A/B nếu muốn giảm hiệu ứng thời gian; không luôn chạy A trước B.

Ví dụ hàm thu thập số đo:

```javascript
function measureMany(hintName, iterations) {
  const samples = [];

  for (let i = 0; i < iterations; i++) {
    const result = runTimedQuery(hintName);
    samples.push(result.elapsedMillis);
  }

  samples.sort((a, b) => a - b);

  const n = samples.length;
  const p50 = samples[Math.floor(0.50 * (n - 1))];
  const p95 = samples[Math.floor(0.95 * (n - 1))];

  return { samples, p50, p95 };
}

// Warm-up trước khi thu mẫu.
for (let i = 0; i < 5; i++) {
  runTimedQuery(null);
}

printjson(measureMany(null, 30));
```

Hàm percentile minh họa phương pháp chọn một phần tử theo thứ tự; các công cụ observability có thể dùng quy ước nội suy percentile khác. Đối với query rất nhanh dưới 1 ms, độ phân giải `Date.now()` có thể không đủ; nên dùng timer có độ phân giải cao do môi trường đo hỗ trợ.

### 10.2. Cold cache và warm cache

Một lần đầu có thể cần đọc disk page từ storage, những lần sau lấy dữ liệu từ RAM. Cần tách:

- **Cold-cache behavior:** gần tình huống working set chưa có trong cache.
- **Warm-cache behavior:** gần traffic đều đặn nơi dữ liệu/index nóng.

Không tùy tiện khởi động lại MongoDB hay xóa cache hệ điều hành trên production để tạo cold cache. Trong môi trường thử, có thể dùng quy trình reset nhất quán nếu được phép và đánh giá tác động. Thực tế, mô phỏng cold cache hoàn toàn là khó; nên mô tả chính xác điều kiện đo thay vì ghi nhãn “cold” khi chỉ là lần đầu của một script.

### 10.3. Thứ tự đo có thể tạo thiên lệch

Ví dụ:

```text
1. Chạy baseline với cache lạnh.
2. Build index (đọc dữ liệu, làm nóng cache).
3. Chạy after với cache nóng.
4. Kết luận index giúp nhanh hơn 100 lần.
```

Phép đo trên **trộn hiệu ứng của index và cache**. Để hạn chế, cần chạy warm-up phù hợp cả hai, đo xen kẽ trong môi trường thử, hoặc sử dụng snapshot/hệ thống tương đương để so sánh với điều kiện cache đã được mô tả.

## 11. Không chỉ đo một tổ hợp giá trị filter

Một query shape có nhiều giá trị thực tế:

```javascript
{
  tenantId: tenant,
  status: status,
  createdAt: { $gte: from, $lt: to }
}
```

Planner có thể chọn kế hoạch tốt cho tenant nhỏ và một tháng, nhưng không tối ưu cho tenant lớn và sáu tháng.

Nên tạo **ma trận biến thể**:

| Trường hợp | Tenant | Status | Khoảng thời gian | Mục đích |
|---|---|---|---|---|
| A | Tenant A rất lớn | PAID phổ biến | 1 ngày | Lọc rất hẹp theo thời gian |
| B | Tenant A rất lớn | PAID phổ biến | 1 tháng | Truy vấn thường gặp |
| C | Tenant A rất lớn | PAID phổ biến | 6 tháng | Truy vấn rộng |
| D | Tenant C nhỏ | PAID | 1 tháng | Tenant ít dữ liệu |
| E | Tenant A | CANCELLED hiếm | 1 tháng | Giá trị ít gặp |
| F | Tenant A | PAID | Không có range | Thử khả năng sort/limit toàn tenant |

Đối với mỗi dòng:

1. Chạy query trước/sau hoặc so sánh plans có kiểm soát.
2. Ghi nReturned, keys/docs examined, stage, latency.
3. Ghi tần suất thực tế của query.
4. Xem p95/p99 và tải đồng thời nếu endpoint quan trọng.

Không chỉ báo “trường hợp tốt nhất” mà bỏ qua trường hợp phần lớn người dùng gặp.

### 11.1. Độ chọn lọc và cardinality

Nếu trạng thái PAID chiếm 70% dữ liệu, index chỉ trên status có thể phải xem rất nhiều khóa. Nhưng compound index có `tenantId`, `status` và `createdAt` có thể giới hạn mạnh hơn.

Một cách tư duy:

```text
N = tổng số document
selectivity(tenantId) ≈ tỷ lệ document của tenant
selectivity(status)   ≈ tỷ lệ document có status
selectivity(date)     ≈ tỷ lệ document trong khoảng thời gian
```

Không đơn giản nhân các tỷ lệ trên nếu các cột **tương quan**. Ví dụ tenant A có 95% PAID còn tenant B chỉ 10% PAID; phân bố độc lập giả định sẽ cho ước lượng sai. Dataset đại diện cần giữ được những tương quan quan trọng.

### 11.2. Thử query không trả dữ liệu

Một truy vấn hiếm có `nReturned = 0` cũng quan trọng:

```javascript
db.planLabOrders.find({
  tenantId: "TENANT-C",
  status: "UNKNOWN",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
})
.limit(50);
```

Query không có kết quả vẫn có thể phải quét cả collection nếu thiếu index, làm endpoint “không tìm thấy” bị chậm. Đừng bỏ các trường hợp zero-result khỏi benchmark chỉ vì không có nReturned để tính tỷ lệ.

## 12. Khi index mới làm plan tốt hơn nhưng hệ thống chậm hơn

Thêm index có chi phí. Chỉ đo một truy vấn đọc rồi kết luận thắng có thể bỏ qua hệ quả vận hành.

### 12.1. Write amplification

Khi insert một document, MongoDB phải cập nhật những index liên quan. Khi update field nằm trong index, có thể phải xóa/chèn khóa index tương ứng. Thêm nhiều index rộng có thể làm:

- Insert/update/delete tốn CPU/I/O hơn;
- Tăng dung lượng index trên disk;
- Tăng working set trong cache;
- Tăng thời gian index build, backup hoặc phục hồi;
- Làm giảm thông lượng ghi dưới tải lớn.

Một tối ưu tốt cho API đọc rất quan trọng có thể vẫn đáng giá, nhưng cần mô tả trade-off bằng số liệu.

### 12.2. Index rộng hơn không tự động tốt hơn

Giả sử thêm `total` vào cuối index:

```javascript
db.planLabOrders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1,
  total: 1
});
```

Index này có thể giúp query chỉ cần các field tương ứng trở thành covered trong điều kiện phù hợp, giảm FETCH. Nhưng nó cũng tăng số byte khóa index và chi phí bảo trì.

Nếu collection có rất nhiều write nhưng request đọc chỉ cần 50 record, một index nhỏ hơn với 50 FETCH có thể tốt hơn tổng thể so với một index rất rộng. Chọn theo **end-to-end workload** thay vì “càng covered càng tốt”.

### 12.3. Partial index và điều kiện khác nhau

Nếu query luôn chỉ lấy `status: "PAID"`, một partial index có thể giảm số khóa phải quản lý:

```javascript
db.planLabOrders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  {
    name: "idx_paid_orders_partial",
    partialFilterExpression: { status: "PAID" }
  }
);
```

Query muốn tận dụng partial index thường phải có điều kiện hàm ý `status: "PAID"`; query chỉ lọc tenant và thời gian nhưng muốn cả PAID/PENDING/CANCELLED không thể dựa duy nhất vào index chỉ chứa PAID.

Đó là một thí nghiệm **index ứng viên khác**, cần so sánh riêng về độ chọn lọc, size và chi phí ghi, không được xem như một “tối ưu hiển nhiên” cho mọi endpoint.

## 13. Dữ liệu có thể thay đổi làm so sánh méo đi

Phép đo before/after yêu cầu dữ liệu càng ổn định càng tốt. Trong production, điều này hiếm khi đạt được hoàn toàn:

- Job import thêm nhiều document;
- Đơn hàng đổi status, làm tăng/giảm selectivity;
- TTL hoặc retention xóa dữ liệu cũ;
- Tenant mới xuất hiện;
- Một chiến dịch tạo đột biến lưu lượng;
- Index build đang chạy cùng các workload khác.

### 13.1. Không so sánh hai thời điểm quá xa mà bỏ qua drift

Nếu đo baseline trên 1 triệu document tháng 1, rồi đo after trên 20 triệu document tháng 7, hai kết quả không thể chỉ quy cho index. Ngược lại, nếu dữ liệu sau bị purge và nhỏ đi, query có thể nhanh hơn dù index không tốt hơn.

Một báo cáo tốt phải ghi:

```text
Collection/doc count tại mỗi phép đo:
Kích thước data/index:
Thời gian đo:
Phiên bản MongoDB:
Topology:
Số tenant và phân bố trọng yếu:
Index tồn tại:
Read concern/read preference:
Concurrency/tải nền:
```

### 13.2. Thử trên cùng snapshot hoặc bản sao môi trường

Tùy điều kiện, có thể:

- Dùng một môi trường thử với dataset bất biến;
- Tạo clone/snapshot từ trạng thái dữ liệu phù hợp và so sánh A/B;
- Chạy nhiều kế hoạch trên cùng dataset với hint trong môi trường thử;
- Phân tích ảnh hưởng index bằng canary nếu triển khai production phải kiểm soát rủi ro.

Cần xem cache, máy chủ, cấu hình và tải, tránh gọi hai bản sao có phần cứng/kích thước bộ nhớ khác nhau là “so sánh công bằng”.

## 14. Query planner và plan cache có thể đổi hành vi

MongoDB query planner chọn một kế hoạch dựa trên query shape, các index ứng viên, statistics/trial execution và những cơ chế theo phiên bản. Trong các môi trường phù hợp, plan cache giúp tái sử dụng thông tin kế hoạch cho các query shape tương ứng.

Tác động tới before/after:

- Thêm hoặc xóa index có thể làm tập kế hoạch ứng viên thay đổi.
- Một shape tốt cho giá trị ít xuất hiện chưa chắc tốt cho giá trị phổ biến.
- Replanning có thể xảy ra khi một kế hoạch không còn hiệu quả.
- Sự thay đổi về query shape, collation hoặc thứ tự sort có thể dẫn đến một plan khác.
- Explain không phản ánh đầy đủ cơ chế dùng plan cache của các request bình thường.

### 14.1. Rejected plan không nhất thiết là “sai”

Trong explain có thể thấy `rejectedPlans`. Đó là các kế hoạch từng được xem xét nhưng không được chọn cho lần lập kế hoạch đó. Một rejected plan chưa chắc tệ cho **mọi giá trị filter và mọi phân bố dữ liệu**.

Không tự động kết luận planner có lỗi chỉ vì một index mà developer kỳ vọng không thắng. Cần so sánh cost trên workload và hiểu vì sao planner đánh giá khác.

### 14.2. Ảnh hưởng của hint

Khi dùng:

```javascript
db.planLabOrders.find(filter, projection)
  .sort(sort)
  .limit(limit)
  .hint("idx_tenant_status_created_id");
```

ứng dụng đang yêu cầu một index cụ thể. Điều này có thể hữu ích cho benchmark, nhưng trong production một hint cố định có thể gây regression khi:

- Dataset thay đổi;
- Query shape thay đổi;
- Index bị drop/rename;
- Giá trị filter có selectivity rất khác;
- Planner của phiên bản mới có phương án tốt hơn.

Hint chỉ nên là quyết định có chủ đích dựa trên bằng chứng và được giám sát, không phải phản xạ mỗi khi thấy kế hoạch ngoài dự đoán.

## 15. Explain cho aggregation pipeline

Nhiều query không chỉ là `find()`; hệ thống có thể dùng aggregation:

```javascript
db.planLabOrders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-03-01T00:00:00Z"),
        $lt: ISODate("2026-04-01T00:00:00Z")
      }
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 50 },
  {
    $project: {
      _id: 1,
      createdAt: 1,
      total: 1,
      status: 1
    }
  }
]);
```

Một cách xem explain cho aggregation là:

```javascript
db.planLabOrders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-03-01T00:00:00Z"),
        $lt: ISODate("2026-04-01T00:00:00Z")
      }
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 50 },
  {
    $project: {
      _id: 1,
      createdAt: 1,
      total: 1,
      status: 1
    }
  }
]);
```

MongoDB có thể đẩy `$match`, tối ưu `$sort + $limit` hoặc gom các stage trong plan tùy phiên bản. Cấu trúc explain của aggregation có thể không giống find: một số stage có execution statistics riêng, một số phần được nhúng trong query planner.

### 15.1. Chỉ so sánh pipeline tương đương ngữ nghĩa

Nếu bạn di chuyển `$limit` lên trước `$match`:

```javascript
[
  { $limit: 50 },
  { $match: { status: "PAID" } }
]
```

thì ý nghĩa không còn là “50 đơn hàng PAID đầu tiên” mà là “lấy 50 document rồi lọc PAID”, có thể trả ít hơn 50 và bỏ qua document hợp lệ. Không được coi việc nhanh hơn nhờ làm ít công việc **nhưng đổi kết quả** là tối ưu hợp lệ.

Tương tự, di chuyển `$project` trước `$match` mà loại mất field filter có thể làm pipeline sai. Mọi rewrite phải bảo toàn semantics, trường cần thiết và thứ tự.

### 15.2. Khi sort spill ra disk

Một pipeline sort/group lớn có thể dùng nhiều bộ nhớ và trong các trường hợp hỗ trợ cấu hình/phiên bản có thể spill ra disk. Cần quan sát các chỉ số spill, memory usage và latency thay vì chỉ nhìn `executionTimeMillis`.

Index phù hợp với `$match` và `$sort` có thể giúp tránh sort blocking, nhưng không phải mọi pipeline đều được index hỗ trợ sau các stage biến đổi dữ liệu. Cần xem vị trí các stage được tối ưu và query plan thực tế.

## 16. Thí nghiệm index có nhiều cách lựa chọn

Giả sử có ba index ứng viên:

```javascript
// I1: lọc tenant + status.
db.planLabOrders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "I1_tenant_status" }
);

// I2: lọc + range/sort.
db.planLabOrders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "I2_full_query" }
);

// I3: lọc tenant + sort, không có status.
db.planLabOrders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "I3_tenant_time" }
);
```

Không nhất thiết giữ tất cả ba index lâu dài. Trong môi trường thử, có thể dùng `hint()` để đo từng index trên cùng query:

```javascript
for (const indexName of [
  "I1_tenant_status",
  "I2_full_query",
  "I3_tenant_time"
]) {
  const plan = db.planLabOrders.find(filter, projection)
    .sort(sort)
    .limit(limit)
    .hint(indexName)
    .explain("executionStats");

  printjson({
    index: indexName,
    keys: plan.executionStats.totalKeysExamined,
    docs: plan.executionStats.totalDocsExamined,
    returned: plan.executionStats.nReturned,
    ms: plan.executionStats.executionTimeMillis
  });
}
```

Một cách lý giải có thể xảy ra:

- **I1:** lọc tenant/status nhưng vẫn phải kiểm tra ngày và sort nhiều ứng viên.
- **I2:** tận dụng tenant/status và thứ tự createdAt/_id, có thể dừng sớm theo limit.
- **I3:** đọc theo thời gian trong tenant nhưng phải bỏ qua những record status không khớp; vẫn có thể tốt nếu PAID cực kỳ phổ biến và limit nhỏ.

Vì vậy, **I2 có vẻ phù hợp nhất về query shape** nhưng không được khẳng định luôn thắng trong mọi dataset. Nếu status 99% PAID, I3 có thể cạnh tranh; nếu một tenant ít PAID, I2 có thể vượt trội.

Thí nghiệm tốt là thí nghiệm **cho phép bác bỏ giả thuyết ban đầu**, không phải chỉ chọn số liệu chứng minh một index đã quyết định trước.

## 17. Chi phí tạo index và thay đổi production

Khi thêm index vào collection lớn, chi phí không chỉ là latency query sau đó.

Các yếu tố cần cân nhắc:

- Tài nguyên CPU/I/O/memory trong quá trình build;
- Tăng storage và cache working set;
- Tác động đến các thao tác ghi đang hoạt động;
- Replication và khả năng failover trong giai đoạn thay đổi;
- Kế hoạch rollback nếu query bị regression hoặc write throughput giảm;
- Giám sát sau deploy qua nhiều chu kỳ tải.

Một kết quả benchmark trên local máy phát triển **không tương đương** với cam kết production trên replica set/sharded cluster. Với production, nên làm thay đổi có kiểm soát, quan sát p95/p99, slow query rate, CPU/IOPS, replication lag và kích thước index.

Nếu cần xóa một index cũ sau khi thêm index mới, hãy xác định nó có được những query khác sử dụng không. Một index có vẻ dư thừa cho query đang xét vẫn có thể rất quan trọng cho endpoint khác.

## 18. Những yếu tố cần ghi trong báo cáo thí nghiệm

Một báo cáo có thể cấu trúc như sau:

```text
MỤC TIÊU
  Endpoint: GET /tenants/{id}/orders
  Query shape: tenantId = ?, status = PAID,
               createdAt in [from, to),
               sort createdAt DESC, _id DESC, limit 50
  KPI mục tiêu: giảm p95 latency, không tăng write latency quá mức

MÔI TRƯỜNG
  MongoDB version:
  Topology: standalone / replica set / sharded cluster
  CPU/RAM/storage:
  Read concern/read preference:
  Driver/version:
  Background load:

DATASET
  Document count:
  Avg / p95 document size:
  Tenant distribution:
  Status distribution:
  Time distribution:
  Existing indexes:

CAN THIỆP
  Before:
  After index/query change:
  Các yếu tố giữ nguyên:

KẾT QUẢ
  nReturned:
  totalKeysExamined:
  totalDocsExamined:
  winningPlan/indexName:
  SORT/FETCH/spills:
  executionTimeMillis:
  Client p50/p95/p99:
  Write throughput/latency:
  Index size:
  Query correctness:

KẾT LUẬN
  Query shapes được cải thiện:
  Query shapes bị regression:
  Chi phí duy trì index:
  Quyết định triển khai/không triển khai:
  Cách theo dõi sau rollout:
```

### 18.1. Ví dụ bảng số liệu minh họa

**Bảng sau là số liệu giả định để học cách trình bày, không phải kết quả đã chạy trên một máy MongoDB cụ thể.**

| Chỉ số | Before | After |
|---|---:|---:|
| Document count | 120.000 | 120.000 |
| `nReturned` | 50 | 50 |
| `totalDocsExamined` | 120.000 | 50 |
| `totalKeysExamined` | 0 | 50 |
| Blocking sort | Có | Không |
| `executionTimeMillis` | 92 ms | 4 ms |
| Client p50 | 105 ms | 9 ms |
| Client p95 | 160 ms | 18 ms |
| Thêm index storage | 0 MB | +một lượng đo được |
| Write throughput | Baseline | Cần đo ảnh hưởng |

Từ bảng giả định có thể nói kế hoạch mới **giảm mạnh số document examined** và cải thiện latency của **workload này**. Không thể khẳng định index “tối ưu toàn hệ thống” nếu chưa đo các query khác và write workload.

## 19. Theo dõi query sau triển khai

Benchmark trước deploy là một bước. Sau deploy, query plan có thể đổi khi dữ liệu tăng hoặc phân bố thay đổi.

Những tín hiệu nên theo dõi:

- p50/p95/p99 latency của endpoint theo tenant/status/query pattern;
- Số lượng slow operations và các query shape gây tải;
- `docsExamined`/`keysExamined` trên những query quan trọng;
- Thông tin plan/index được chọn khi điều tra query;
- Cache pressure, disk IOPS, CPU, memory;
- Index size, index usage theo quan sát thực tế;
- Write latency và throughput;
- Replication lag trên replica set;
- Trạng thái shard routing và cân bằng tải khi có sharding.

MongoDB cung cấp các công cụ như profiler, diagnostic logs, `explain()`, `$indexStats` và công cụ monitoring theo triển khai. **Profiler/diagnostic logging chi tiết có thể tăng overhead và lưu thông tin truy vấn nhạy cảm**, vì vậy không bật mức thu thập cao vô thời hạn trên production mà không có kế hoạch.

### 19.1. Quan sát index usage không đủ để quyết định drop

Có thể dùng aggregation `$indexStats` để xem chỉ số truy cập index theo những giới hạn của cơ chế thống kê đó:

```javascript
db.planLabOrders.aggregate([
  { $indexStats: {} }
]);
```

Tuy nhiên, thống kê truy cập index phụ thuộc thời gian quan sát, node và hoạt động query. Một index ít được dùng hôm nay có thể phục vụ job cuối tháng hoặc sự cố quan trọng. Không nên drop index chỉ vì số lần truy cập thấp trong một khoảng ngắn.

## 20. Những sai lầm thường gặp khi so sánh before/after

| Sai lầm | Vì sao kết luận sai lệch | Cách khắc phục |
|---|---|---|
| Dùng 20 document test | Quét collection vẫn rất rẻ | Dữ liệu có quy mô/phân bố gần thực tế |
| Chỉ đo một tenant nhỏ | Bỏ qua tenant nóng | Ma trận tenant lớn/nhỏ |
| Seed dữ liệu đồng đều giả tạo | Sai selectivity | Mô phỏng độ lệch và tương quan |
| Thay query và index cùng lúc | Không biết yếu tố nào tạo cải thiện | Tách thí nghiệm |
| Chỉ so `executionTimeMillis` một lần | Cache/tải gây nhiễu | Nhiều mẫu, median/p95 |
| Trước cache lạnh, sau cache nóng | Cải thiện bị quy sai cho index | Điều kiện cache có kiểm soát |
| Không đọc hết cursor | Đo chỉ thời gian tạo query object | Tiêu thụ kết quả khi benchmark |
| Chỉ thấy `IXSCAN` rồi kết luận tốt | Có thể scan hàng triệu key | Xem keys/docs examined, sort, fetch |
| Nghĩ `COLLSCAN` luôn sai | Query trả gần hết collection có thể hợp lý | Xem chi phí tổng và SLA |
| Chỉ benchmark query có kết quả | Bỏ qua truy vấn miss/zero-result | Thêm variant không khớp |
| Không giữ nguyên limit/sort/projection | Hai query không cùng ngữ nghĩa | Cố định query shape |
| Đo sau index nhưng dùng `hint()` rồi coi đó là planner tự chọn | Hint ép plan | Đo thêm query không hint |
| Xem explain như phản ánh plan cache thực tế | Explain có ngữ nghĩa planner riêng | Quan sát request thật |
| Tạo index rộng và bỏ qua chi phí ghi | Có thể gây regression toàn hệ thống | Đo write latency/throughput/index size |
| Không đo sau deploy | Phân bố data đổi theo thời gian | Giám sát và kế hoạch rollback |

## 21. Bài tập thực hành

### Bài 1 — Baseline trên dataset đại diện

Tạo collection `planLabOrders` theo script ở phần 3. Chạy query của phần 4 khi chưa có compound index. Ghi `nReturned`, `totalDocsExamined`, `totalKeysExamined`, `executionTimeMillis` và winning plan. Giải thích vì sao kết quả baseline trên 120.000 document khác thử nghiệm trên 50 document.

### Bài 2 — Đo trước và sau khi tạo index

Tạo index:

```javascript
db.planLabOrders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Chạy lại query y hệt. So sánh các metric và nhận diện index được dùng. Có `SORT` không? Có `FETCH` không? Vì sao query còn phải đọc `total` từ document?

### Bài 3 — Dùng hint để phân biệt hai kế hoạch

Sau khi tạo index, so sánh:

```javascript
// Ép natural scan.
db.planLabOrders.find(filter, projection)
  .sort(sort).limit(50)
  .hint({ $natural: 1 })
  .explain("executionStats");

// Ép compound index.
db.planLabOrders.find(filter, projection)
  .sort(sort).limit(50)
  .hint("idx_tenant_status_created_id")
  .explain("executionStats");
```

Giải thích vì sao phép đo này bổ sung cho before/after, và tại sao nó chưa chứng minh query production không hint sẽ chọn index tương ứng.

### Bài 4 — Thay đổi selectivity

Với cùng index, thử:

1. Tenant A, status PAID, range sáu tháng.
2. Tenant C, status PAID, range một ngày.
3. Tenant A, status CANCELLED, range một tháng.
4. Tenant A, status PAID, không có date range.

Lập bảng key/doc examined và thời gian thực thi. Giải thích vì sao số record và phân bố giá trị ảnh hưởng hiệu quả index dù query có cùng field.

### Bài 5 — Projection và covered query

Chạy hai query:

- Query A trả `total` cùng các field có trong index.
- Query B chỉ trả `tenantId`, `status`, `createdAt` và `_id`.

Quan sát `totalDocsExamined` và FETCH. Vì sao không được nói kết quả B chứng minh index đã cải thiện **đúng query A** đến mức không đọc document?

### Bài 6 — Ma trận benchmark có p95

Tạo hàm gọi query 50 lần trong `mongosh` hoặc Java driver, có warm-up và tiêu thụ đầy đủ kết quả. Đo p50/p95, rồi so sánh index I1/I2/I3 cho ba nhóm tenant/status. Trình bày nguyên tắc kiểm soát cache và tải nền.

### Bài 7 — Tính chi phí index

Giả sử index mới giảm p95 của API đọc từ 120 ms xuống 25 ms nhưng tăng p95 insert từ 15 ms lên 22 ms. API đọc có 3.000 request/giây, insert có 2.500 request/giây, hệ thống đang gần giới hạn CPU. Có nên giữ index không? Hãy đề xuất cách thu thập thêm số liệu để quyết định, không chỉ nhìn mức cải thiện của query đọc.

### Bài 8 — Báo cáo cho review kỹ thuật

Viết một báo cáo 1–2 trang cho một đề xuất index, gồm giả thuyết, dataset, query shape, môi trường, before/after explain, p50/p95, các query bị ảnh hưởng, dung lượng index, kết quả correctness và phương án rollback. Phân biệt rõ **số liệu đã đo** với **dự đoán**.

## 22. Tài liệu MongoDB tham khảo

- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [db.collection.explain()](https://www.mongodb.com/docs/manual/reference/method/db.collection.explain/)
- [Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [Sort Results with Indexes](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/)
- [Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [Plan Cache](https://www.mongodb.com/docs/manual/core/query-plans/#plan-cache)
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [Index Statistics](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)

## Kết luận

So sánh kế hoạch thực thi **trước và sau** là một thí nghiệm kỹ thuật, không chỉ là nhìn thấy tên stage `IXSCAN` thay cho `COLLSCAN`. Một kết quả đáng tin cậy cần **dataset đại diện**, query tương đương, môi trường được ghi nhận rõ, nhiều biến thể selectivity và nhiều lượt đo.

Dùng `explain("executionStats")` để hiểu chi phí: `nReturned`, `totalKeysExamined`, `totalDocsExamined`, `FETCH`, `SORT` và index được chọn. Dùng benchmark thực tế để đo latency p50/p95, kiểm soát cache và query plan, rồi đánh giá thêm dung lượng index và write amplification. Khi cần, so sánh bằng `hint()` trên cùng dataset để phân biệt chi phí các kế hoạch, nhưng luôn đo cả query không hint và theo dõi plan cache/query behavior trong ứng dụng.

**Chỉ kết luận index hoặc query mới tốt hơn khi nó trả đúng kết quả, giảm chi phí cho những workload quan trọng và không tạo regression không chấp nhận được cho toàn hệ thống.** Bằng chứng từ dữ liệu thực tế quan trọng hơn cảm giác rằng một kế hoạch “trông đẹp hơn” trên explain.

