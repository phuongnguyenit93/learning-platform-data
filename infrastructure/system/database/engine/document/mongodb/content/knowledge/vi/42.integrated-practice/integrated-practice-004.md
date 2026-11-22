# Đo truy vấn, thiết kế index và so sánh explain trước sau trong MongoDB

Một truy vấn MongoDB trả đúng dữ liệu chưa chắc đã đáp ứng yêu cầu vận hành. Với vài chục document, một lệnh find không có index thường vẫn rất nhanh. Nhưng khi collection tăng lên hàng trăm nghìn hoặc hàng triệu document, cùng truy vấn có thể phải quét nhiều dữ liệu, thực hiện sort tốn bộ nhớ, khiến API chậm và tăng tải cho cả replica set.

Cách tối ưu đáng tin cậy không bắt đầu bằng việc tạo thật nhiều index. Ta cần **đo hiện trạng, hiểu mẫu truy cập, thiết kế index ứng viên, đo lại với cùng điều kiện và kiểm tra tính đúng đắn**. Bài này xây dựng một phòng thí nghiệm MongoDB theo đúng trình tự đó, kết hợp mongosh, explain, phương pháp benchmarking và một ví dụ Java Sync Driver.

Bài học thuộc chương **Thực hành tổng hợp**, module **Database Engine Document MongoDB**, với đề bài **Đo truy vấn, thiết kế index và so sánh explain trước sau**.

**Lưu ý an toàn:** Tất cả lệnh ghi dữ liệu, tạo/ẩn/xóa index trong bài chỉ dành cho database thực hành riêng. Không chạy trên production. explain và các truy vấn đọc cũng có chi phí; nếu đang chẩn đoán production, giới hạn scope, dùng quyền phù hợp, đo tác động và tuân theo quy trình vận hành.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Xác định một query shape và mục tiêu hiệu năng của nó.
2. Tạo dataset thử nghiệm xác định có nhiều tenants, statuses và timestamps.
3. Ghi lại danh sách index, số documents và trạng thái trước thí nghiệm.
4. Chạy explain với các mức queryPlanner, executionStats và allPlansExecution.
5. Đọc nReturned, totalDocsExamined, totalKeysExamined, các stages như COLLSCAN, IXSCAN, FETCH, SORT.
6. Hiểu cấu trúc explain có thể khác giữa classic engine và slot-based execution engine.
7. Thiết kế compound index theo equality, sort và range predicates.
8. So kết quả truy vấn trước/sau để chắc chắn index không làm thay đổi semantics.
9. Đo độ trễ có warm-up, nhiều lần lặp và workload tương đương.
10. Nhận diện trade-off giữa read latency, index storage và write overhead.
11. Thử covered query, keyset pagination, multi-key, partial index và query hints.
12. Phân biệt kết luận do explain hỗ trợ với kết luận cần đo bằng ứng dụng/APM.
13. Viết báo cáo A/B có evidence, uncertainty, rollback và decision rõ.

## 2. Tổng quan quy trình lab

~~~text
Business request / API SLO
           |
           v
Identify query shape and data distribution
           |
           v
Create isolated, deterministic test dataset
           |
           v
BASELINE
  - getIndexes
  - query result IDs
  - explain executionStats
  - repeated latency measurements
           |
           v
Hypothesis: an index can support filter + sort
           |
           v
Design candidate compound index
           |
           v
Create index in the lab only
           |
           v
AFTER
  - same query and data
  - explain executionStats
  - repeated latency measurements
  - check result correctness
           |
           v
Compare evidence and trade-offs
           |
           v
Document decision, risks and next experiment
~~~

Không dùng câu "có IXSCAN nên chắc chắn tối ưu" làm kết luận cuối. Một index có thể giảm documents examined nhưng thêm write overhead, hoặc một plan nhanh khi dữ liệu nhỏ lại không tốt cho production.

## 3. Bài toán nghiệp vụ xuyên suốt

Giả sử một ứng dụng quản lý đơn thuê có API:

~~~text
GET /tenants/{tenantId}/orders?status=PAID&limit=20

Required behavior:
  Only orders belonging to authenticated tenant
  Only status PAID
  Newest orders first
  Stable order on ties using _id
  Return at most 20 documents
~~~

Mẫu truy vấn MongoDB:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 3.1. Access pattern gồm những gì?

- Equality filter: tenantId = tenant-07.
- Equality filter: status = PAID.
- Sort: createdAt giảm dần, sau đó _id giảm dần.
- Limit: 20.
- Read frequency: giả sử cao, cần được đo bằng ứng dụng thật.
- Security: tenantId phải đến từ authentication context đã xác minh.

### 3.2. Câu hỏi cần trả lời

1. Khi chỉ có index mặc định trên _id, query thực hiện bao nhiêu công việc?
2. Có blocking sort không?
3. Index nào có thể lọc và sắp xếp hiệu quả hơn?
4. Kết quả có giữ nguyên sau khi thêm index không?
5. Lợi ích đọc có xứng với chi phí index mới không?

## 4. Điều kiện môi trường

Cần có:

- Một MongoDB server hoặc replica set **dành riêng cho thực hành**.
- mongosh và một tài khoản được phép tạo collection/index trong database lab.
- Khả năng quan sát kết quả command và lưu số liệu A/B.
- Tùy chọn: Java Sync Driver và một project Java để đo từ ứng dụng.
- Đủ dung lượng để tạo khoảng 48.000 documents nhỏ.

**Không** sử dụng một account production có quyền thay đổi database chỉ vì tên collection là orders.

### 4.1. Database cô lập

Dùng tên:

~~~text
mongo_index_lab_459
~~~

Nếu đã từng chạy lab, hãy tạo database tên khác với cùng ý nghĩa. Không mặc định xóa dữ liệu cũ.

### 4.2. Phần nào là tùy theo phiên bản?

Explain output, các field metrics, cách mô tả plan cache và stage naming có thể khác giữa các phiên bản MongoDB. Bài sẽ giải thích các nhóm tín hiệu ổn định ở mức khái niệm, không yêu cầu mọi kết quả JSON phải giống nhau từng chữ.

### 4.3. Ghi version trước

~~~javascript
db.version();
db.adminCommand({ hello: 1 });
~~~

Các lệnh này để quan sát server/topology. Không dùng hello response từ một node để suy ra toàn bộ cluster chắc chắn khỏe.

## 5. Thiết kế dataset trước khi đo

Một dataset có mục đích cần thỏa:

- Số document đủ để xuất hiện sự khác biệt giữa scan và index lookup.
- Nhiều tenants và statuses để equality filters có tính chọn lọc.
- createdAt trải rộng trên nhiều thời điểm.
- _id cố định, có thứ tự rõ.
- Các field được lưu đúng BSON types.
- Không phụ thuộc Random không seed hoặc Instant.now.
- Có thể tái tạo từ cùng công thức.

Ta chọn **48.000 orders**, **24 tenants**, **4 statuses**, phân phối đồng đều theo công thức. Với mỗi cặp tenant/status sẽ có **500 orders**.

### 5.1. Tránh distribution vô tình bị tương quan

Nếu đặt tenantId = i % 24 và status = i % 4, vì 24 chia hết cho 4 nên một tenant chỉ gặp một status nhất định. Điều này làm dữ liệu không đại diện và khiến query shape sai mục đích.

Thay vào đó:

~~~javascript
tenantIndex = i % 24;
statusIndex = Math.floor(i / 24) % 4;
~~~

Mỗi vòng 24 documents dùng đủ tenants; cứ sau một vòng mới đổi status. Sau 48.000 records, mỗi tenant có 2.000 orders và mỗi status trong tenant có 500 orders.

### 5.2. Kiểm soát số lượng

~~~text
24 tenants x 4 statuses x 500 documents
= 48,000 documents
~~~

Đây là số lượng thiết kế của lab, không phải phép đo thu được từ một cluster thật.

## 6. Tạo dữ liệu mẫu bằng mongosh

**Chỉ chạy trên test deployment đã xác minh.** Script cố ý từ chối chạy khi collection orders đã tồn tại trong database lab để tránh ghi chồng trạng thái từ lần trước.

~~~javascript
var lab = db.getSiblingDB("mongo_index_lab_459");

if (lab.getCollectionInfos({ name: "orders" }).length > 0) {
  throw new Error(
    "Lab orders already exists. Use a fresh lab database."
  );
}

var orders = lab.getCollection("orders");
var statuses = [
  "PENDING",
  "PAID",
  "CANCELLED",
  "COMPLETED"
];

var baseTime = Date.UTC(
  2026, 0, 1, 0, 0, 0
);

var batch = [];
var total = 48000;

for (var i = 0; i < total; i++) {
  var tenantIndex = i % 24;
  var statusIndex = Math.floor(i / 24) % 4;

  var doc = {
    _id: "o-" + String(i + 1).padStart(6, "0"),
    tenantId: "tenant-" +
      String(tenantIndex).padStart(2, "0"),
    status: statuses[statusIndex],
    customerId: "customer-" +
      String(i % 300).padStart(4, "0"),
    createdAt: new Date(
      baseTime + i * 60 * 1000
    ),
    totalMinor: NumberLong(
      100000 + (i % 500) * 1000
    ),
    priority: i % 10 === 0,
    items: [
      {
        sku: "sku-" + String(i % 40),
        qty: 1 + (i % 3)
      }
    ]
  };

  batch.push(doc);

  if (batch.length === 1000) {
    orders.insertMany(batch, {
      ordered: true
    });
    batch = [];
  }
}

if (batch.length > 0) {
  orders.insertMany(batch);
}

print("Seeded orders: " + orders.countDocuments({}));
printjson(orders.getIndexes());
~~~

### 6.1. Vì sao batch 1.000?

Nó tránh giữ toàn bộ 48.000 documents trong một mảng ở mongosh và giữ mỗi insertMany trong kích thước hợp lý. Có thể điều chỉnh batch size theo môi trường nhưng cần ghi lại nếu thay đổi.

### 6.2. Không tự động drop collection

Một lab có thể đã chứa dữ liệu dùng cho một lần đo khác. Script báo lỗi thay vì xóa collection có sẵn. Chỉ khi xác định đúng test environment, người học mới chủ động tạo namespace mới hoặc thực hiện cleanup được phép.

### 6.3. Seed trước khi tạo index ứng viên

Để có baseline công bằng, bắt đầu với index mặc định trên _id, không có compound index phục vụ query chính.

### 6.4. Vì sao createdAt cố định?

Không có chênh lệch do thời gian chạy test; sắp xếp kết quả có thể dự đoán và so giữa các lần thực hiện.

### 6.5. Nếu seed dừng giữa chừng?

Collection có thể tồn tại với một phần records. Không lấy dữ liệu thiếu làm baseline. Tạo namespace lab mới hoặc cleanup theo quy trình an toàn, seed lại và kiểm tra đủ 48.000.

## 7. Kiểm tra data distribution

Trước khi đo explain, xác nhận số lượng:

~~~javascript
var lab = db.getSiblingDB("mongo_index_lab_459");
var orders = lab.getCollection("orders");

print("Total: " + orders.countDocuments({}));

print(
  "tenant-07/PAID: " +
  orders.countDocuments({
    tenantId: "tenant-07",
    status: "PAID"
  })
);
~~~

Với seed đúng, expected:

~~~text
Total: 48000
tenant-07/PAID: 500
~~~

Nếu số lượng lệch, dừng thí nghiệm và tìm nguyên nhân seed/namespace trước khi so sánh hiệu năng.

### 7.1. Tính chọn lọc

Query trả 500 documents thỏa filter trong 48.000 documents; sau sort/limit chỉ trả 20.

- Filter match ratio: 500 / 48.000.
- Output ratio: 20 / 48.000.
- Các tỷ lệ này được tính từ mô hình seed, không phải performance metric của server.

### 7.2. Xem group distribution

~~~javascript
orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      n: { $sum: 1 }
    }
  },
  {
    $sort: {
      "_id.tenantId": 1,
      "_id.status": 1
    }
  },
  { $limit: 12 }
]);
~~~

Kết quả mẫu giúp thấy phân phối; có thể bỏ limit trong database lab nếu cần xác nhận toàn bộ 96 groups.

## 8. Xác nhận hiện trạng index

~~~javascript
var orders = db.getSiblingDB(
  "mongo_index_lab_459"
).getCollection("orders");

printjson(orders.getIndexes());
~~~

Trên collection mới, thường chỉ có index mặc định:

~~~javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  }
]
~~~

Hình dạng JSON chính xác có thể khác theo server version. Điều cần ghi là **danh sách key pattern/name và options**, không phải các metadata vô nghĩa đối với thí nghiệm.

### 8.1. Vì sao cần inventory?

Nếu index ứng viên đã có từ lần trước, kết quả gọi là "before" sẽ không còn là baseline thật.

### 8.2. Index trên _id không đương nhiên giúp filter tenantId/status

Một index B-tree theo _id không tổ chức dữ liệu để lọc trước theo tenantId và status. Query có thể dùng COLLSCAN, hoặc một plan khác do optimizer chọn; phải dựa vào explain thực tế.

## 9. Định nghĩa query A bất biến

Sử dụng đúng cùng filter, sort, projection và limit ở trước và sau.

~~~javascript
var lab = db.getSiblingDB("mongo_index_lab_459");
var orders = lab.getCollection("orders");

var filterA = {
  tenantId: "tenant-07",
  status: "PAID"
};

var sortA = {
  createdAt: -1,
  _id: -1
};

var limitA = 20;
~~~

### 9.1. Không đổi query giữa A/B

Nếu trước đo query cho tenant-07 nhưng sau đo tenant-22, độ trễ không còn so sánh công bằng nếu distribution khác.

### 9.2. Giữ projection

Lần trước trả full documents, lần sau chỉ trả _id, thì network payload và index coverage đã thay đổi. Chỉ thay **một biến thiết kế** mỗi lần.

### 9.3. Query correctness trước performance

Một index tốt không được thay yêu cầu tenant isolation, status và thứ tự.

## 10. Lưu kết quả đúng trước khi tạo index

Trong cùng mongosh session:

~~~javascript
var baselineIds = orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .project({ _id: 1 })
  .toArray()
  .map(d => d._id);

printjson(baselineIds);
~~~

### 10.1. Vì sao lưu IDs?

Sau khi tạo index, ta kiểm tra cùng query vẫn trả đúng IDs theo đúng thứ tự. Nếu khác, có thể có thay đổi dữ liệu giữa hai lượt, thiếu sort tie-breaker hoặc query không còn giống nhau.

### 10.2. _id là tie-breaker

Ngay cả khi dữ liệu lab có createdAt duy nhất, thực tế nhiều events có thể cùng timestamp. Sort thêm _id giúp thứ tự xác định.

### 10.3. Dữ liệu không được ghi giữa hai lần đo

Trên lab không có writer khác, mọi kết quả nên cố định. Trong production, concurrent writes có thể khiến danh sách trang đầu thay đổi ngay cả khi query đúng.

## 11. explain trước khi tạo index

~~~javascript
var beforeExplain = orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("executionStats");

printjson({
  queryPlanner: beforeExplain.queryPlanner,
  executionStats: beforeExplain.executionStats
});
~~~

Các số liệu quan trọng thường nằm ở:

~~~javascript
beforeExplain.executionStats.nReturned;
beforeExplain.executionStats.totalKeysExamined;
beforeExplain.executionStats.totalDocsExamined;
beforeExplain.executionStats.executionTimeMillis;
~~~

### 11.1. Đọc stage chứ không tự giả định

Với 48.000 documents và không có compound index, rất có khả năng thấy COLLSCAN và một sort stage. Nhưng query planner có thể khác theo version, query và trạng thái dữ liệu. **Ghi những gì thực sự xuất hiện trong winningPlan.**

### 11.2. Explain không phải bộ đếm mạng

`executionStats.executionTimeMillis` thường mô tả server-side execution theo explain, không bao gồm toàn bộ thời gian Java API, network, decoding hoặc waiting ở connection pool.

### 11.3. Query và sort đều có chi phí

Ngay cả khi chỉ trả 20 records, server có thể cần xem rất nhiều documents để tìm ra 20 phần tử mới nhất theo điều kiện.

## 12. Các mức verbosity của explain

MongoDB hỗ trợ các chế độ thường dùng:

| Chế độ | Cung cấp | Khi dùng |
| --- | --- | --- |
| queryPlanner | Winning plan, plan metadata | Hiểu route/index được chọn |
| executionStats | Planner + execution metrics | Đếm examined và returned |
| allPlansExecution | Thêm thông tin về candidate plans | Điều tra planner choice |

Ví dụ:

~~~javascript
orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("queryPlanner");

orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("executionStats");

orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("allPlansExecution");
~~~

### 12.1. Không bật chế độ tốn kém không cần thiết

Trong lab, có thể xem cả ba. Trên production, explain có thể thực thi workload hoặc tiêu thụ tài nguyên; cân nhắc query scope và số lần chạy.

### 12.2. allPlansExecution không đồng nghĩa mọi candidate đều chạy đến hết

Thông tin candidate execution có thể là thử nghiệm giới hạn theo cách planner hoạt động. Không lấy partial candidate stats làm full-query latency.

### 12.3. Plan cache

Explain không phải bản sao hoàn hảo của đường chạy thông thường có plan cache. Đừng suy ra một explain invocation phản ánh mọi hành vi cache/plan selection của traffic production.

## 13. Đọc COLLSCAN, IXSCAN, FETCH và SORT

| Stage/tín hiệu | Ý nghĩa ở mức khái niệm | Câu hỏi tiếp theo |
| --- | --- | --- |
| COLLSCAN | Quét documents từ collection | Vì sao filter không có access path tốt? |
| IXSCAN | Duyệt các entries trong index | Có bao nhiêu keys examined? |
| FETCH | Lấy document sau khi duyệt index | Có cần field không có trong index? |
| SORT | Sắp xếp dữ liệu ngoài trật tự đã cung cấp | Index có hỗ trợ sort không? |
| LIMIT | Giới hạn số kết quả | Có giảm lượng work trước đó không? |
| PROJECTION | Lấy/biến đổi fields trả về | Query có covered không? |

### 13.1. Stage names có thể khác

MongoDB có classic engine và slot-based execution engine (SBE). Explain có thể mô tả stages bên trong `queryPlan`, `slotBasedPlan` hoặc các cấu trúc khác. Đọc theo ngữ nghĩa query execution, không dựa vào một đường dẫn JSON cố định.

### 13.2. IXSCAN không bảo đảm hiệu quả

Một plan có IXSCAN nhưng `totalKeysExamined` rất lớn và `nReturned` nhỏ vẫn có thể tốn chi phí đáng kể.

### 13.3. COLLSCAN không luôn sai

Khi truy vấn trả phần lớn collection hoặc dataset rất nhỏ, COLLSCAN đôi khi là lựa chọn hợp lý hơn index. Đừng coi tên stage là một lỗi độc lập.

## 14. Bốn số liệu quan trọng

**nReturned:** số documents trả từ execution tới client/limit stage theo explain.

**totalDocsExamined:** số lần kiểm tra documents thực tế trong execution plan. Có thể cao hơn số document được trả.

**totalKeysExamined:** số index keys được duyệt. Không có index scan thì thường thấp hoặc bằng không.

**executionTimeMillis:** thời gian thực thi ghi nhận trong explain; hữu ích tham khảo, nhưng không đủ làm benchmark end-to-end.

### 14.1. Tỷ lệ examined/returned

Với nReturned > 0:

~~~text
Documents-per-result =
  totalDocsExamined / nReturned

Keys-per-result =
  totalKeysExamined / nReturned
~~~

Hai tỷ lệ này giúp phân biệt một index seek hiệu quả với scan rộng.

### 14.2. Không dùng tỷ lệ khi nReturned=0 mà chia cho 0

Nếu query không trả kết quả, xem raw examined counts và selectivity, đừng áp dụng công thức có mẫu số bằng 0.

### 14.3. DocsExamined không bằng bytes read

Tổng bytes, page cache hit/miss và disk I/O phụ thuộc kích thước docs, compression, cache và storage. Cần metrics khác nếu điều tra I/O.

### 14.4. Một giá trị executionTimeMillis không đủ

Server load, cache, warm-up và scheduling có thể làm con số dao động. So nhiều lần, ghi điều kiện môi trường và app latency.

## 15. Mẫu bảng baseline

Điền từ kết quả thực tế, không bịa số:

| Chỉ tiêu | Baseline trước index |
| --- | --- |
| Dataset size | 48.000 theo seed, cần xác nhận |
| Query shape | tenantId + status, sort createdAt/_id |
| Indexes hiện có | Ghi từ getIndexes |
| Winning plan | Ghi từ explain |
| nReturned | Ghi giá trị |
| totalDocsExamined | Ghi giá trị |
| totalKeysExamined | Ghi giá trị |
| executionTimeMillis | Ghi giá trị |
| Blocking sort? | Có/không theo winning plan |
| Query result IDs | Lưu baselineIds |
| p50/p95 từ repeated runs | Ghi riêng |

Không coi số lượng giả định 48.000 là bằng chứng nếu seed dừng ở giữa. Luôn kiểm tra count thật.

## 16. Thiết kế index theo equality, sort, range

Một heuristic được dùng rộng rãi là **Equality → Sort → Range (ESR)** cho compound indexes, nhưng không phải công thức bất biến.

Query A:

~~~javascript
{
  tenantId: "tenant-07",
  status: "PAID"
}
~~~

Sort:

~~~javascript
{
  createdAt: -1,
  _id: -1
}
~~~

Index ứng viên:

~~~javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

### 16.1. Tại sao tenantId, status trước?

Chúng là equality predicates. Index có thể nhanh chóng tìm khoảng keys thuộc tenant và status tương ứng.

### 16.2. Tại sao createdAt và _id sau?

Trong từng nhóm tenant/status, index keys được sắp theo createdAt desc và _id desc, có thể phục vụ cả sort của query.

### 16.3. Tại sao không index chỉ createdAt?

Index createdAt có thể hỗ trợ sort nhưng vẫn phải lọc nhiều orders không thuộc tenant/status cần tìm, đặc biệt ở multi-tenant dataset.

### 16.4. Tại sao không index tất cả fields?

Một compound index có quá nhiều fields tốn dung lượng và write maintenance. Chỉ đưa fields có mục đích dựa trên workload.

## 17. Tạo index ứng viên trong lab

**Lệnh tạo index sau chỉ dùng trên collection lab đã xác minh, không chạy trên production.**

~~~javascript
var lab = db.getSiblingDB("mongo_index_lab_459");
var orders = lab.getCollection("orders");

orders.createIndex(
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

printjson(orders.getIndexes());
~~~

### 17.1. Ghi index build time và resource

Trong production, tạo index mới có thể ảnh hưởng CPU, disk, I/O, replication và write load. Lab nhỏ không đủ để kết luận chi phí index build ở quy mô lớn.

### 17.2. Mỗi lần thử đặt tên index rõ

Tên explicit giúp thống nhất báo cáo, hints, indexStats và rollback.

### 17.3. Index mới không tự được dùng cho mọi query

Optimizer sẽ chọn plan theo shape, selectivity và statistics/điều kiện phù hợp. Phải xem winning plan, không chỉ getIndexes.

## 18. explain sau khi tạo index

Dùng lại chính query A:

~~~javascript
var afterExplain = orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .explain("executionStats");

printjson({
  queryPlanner: afterExplain.queryPlanner,
  executionStats: afterExplain.executionStats
});
~~~

Quan sát index name:

~~~text
idx_tenant_status_created_id
~~~

nếu winning plan sử dụng index này. Cũng quan sát liệu còn blocking SORT hay không và số documents/keys examined.

### 18.1. Kỳ vọng ở mức nguyên lý

Trong điều kiện dataset và planner phù hợp, index compound có thể giúp đọc một khoảng nhỏ theo tenant/status và dừng sau khi có 20 kết quả đúng thứ tự.

### 18.2. Không gán các số cụ thể trước khi chạy

Số docsExamined có thể gần 20 nếu query cần fetch 20 docs và index phù hợp. Nhưng không được công bố đây là kết quả thực tế khi chưa chạy.

### 18.3. Query shape phải y hệt

Chỉ thay trạng thái index, không đổi tenant, status, projection, read preference, limit hay sort giữa hai lượt.

## 19. So sánh A/B bằng bảng

| Chỉ tiêu | Trước | Sau | Diễn giải |
| --- | --- | --- | --- |
| Winning access path | Ghi plan A | Ghi plan B | COLLSCAN hay IXSCAN? |
| Index used | Ghi name | Ghi name | Có đúng candidate? |
| nReturned | Số đo | Số đo | Phải cùng semantics |
| totalDocsExamined | Số đo | Số đo | Ít work hơn? |
| totalKeysExamined | Số đo | Số đo | Index scan có chọn lọc? |
| Blocking SORT | Có/không | Có/không | Sort index có hỗ trợ? |
| executionTimeMillis | Số đo | Số đo | Chỉ tham khảo |
| p50/p95 end-to-end | Số đo | Số đo | SLO thực |
| Result IDs/order | Baseline | After | Phải tương đương |
| Storage/write overhead | Baseline | Sau index | Trade-off |

### 19.1. Ví dụ minh họa KHÔNG phải số đo

Giả sử một truy vấn trước index examine 48.000 docs để trả 20; sau index examine 20 docs và scan 20 index keys. Số lần examine giảm lớn, nhưng không thể từ đó khẳng định p95 API giảm tương ứng 2.400 lần.

Đây là ví dụ học nguyên lý. **Báo cáo thực tế phải dùng số liệu đo trên môi trường đang thử**.

### 19.2. Tỷ lệ cải thiện

Với phép đo có giá trị dương:

~~~text
Reduction (%) =
  (before - after) / before * 100

Speedup ratio =
  before_latency / after_latency
~~~

Đừng tính speedup khi after_latency bằng 0 do timer độ phân giải thấp; dùng phương pháp đo chính xác hơn.

## 20. Kiểm chứng tính đúng đắn sau tạo index

Trong cùng mongosh session đã lưu baselineIds:

~~~javascript
var afterIds = orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .project({ _id: 1 })
  .toArray()
  .map(d => d._id);

if (
  JSON.stringify(baselineIds) !==
  JSON.stringify(afterIds)
) {
  throw new Error(
    "Result IDs/order changed between A and B"
  );
}

print("Result IDs and order are unchanged");
~~~

### 20.1. Vì sao index không được làm đổi kết quả?

Index là access path cho query, không phải một thay đổi về điều kiện nghiệp vụ. Nếu result sets đổi, xem query shape/data mutations/collation/consistency trước khi kết luận.

### 20.2. Dữ liệu cố định làm việc so dễ hơn

Lab không có app writers, timestamps được seed cố định. Trên production, concurrent writes có thể làm các kết quả ở hai thời điểm khác nhau một cách hợp lệ.

### 20.3. Kiểm tra count riêng

~~~javascript
orders.countDocuments(filterA);
~~~

Theo seed, query A match 500 docs; không chỉ giới hạn 20 trả về.

## 21. Đo latency nhiều lần trong mongosh

Explain cung cấp execution metrics, nhưng để xem query duration trong môi trường lab có thể đo repeated executions. Ví dụ sau đo **wall-clock group averages** bằng Date.now; đây không phải công cụ benchmark thay thế APM hay microbenchmark chuẩn.

~~~javascript
function measureQuery(groups, queriesPerGroup) {
  for (var warm = 0; warm < 5; warm++) {
    orders.find(filterA)
      .sort(sortA)
      .limit(limitA)
      .toArray();
  }

  var samples = [];

  for (var g = 0; g < groups; g++) {
    var startMs = Date.now();

    for (var q = 0; q < queriesPerGroup; q++) {
      orders.find(filterA)
        .sort(sortA)
        .limit(limitA)
        .toArray();
    }

    var durationMs = Date.now() - startMs;
    samples.push(
      durationMs / queriesPerGroup
    );
  }

  samples.sort((a, b) => a - b);

  var medianIndex = Math.floor(samples.length / 2);
  var p95Index = Math.min(
    samples.length - 1,
    Math.ceil(0.95 * samples.length) - 1
  );

  return {
    groups: groups,
    queriesPerGroup: queriesPerGroup,
    medianMs: samples[medianIndex],
    p95Ms: samples[p95Index],
    samplesMs: samples
  };
}

printjson(measureQuery(20, 10));
~~~

### 21.1. Chạy trước và sau

Đo trước khi tạo index, lưu output; rồi đo sau khi tạo index với cùng script, không thay group/repetition count.

### 21.2. Hạn chế của Date.now

Clock có độ phân giải hữu hạn; một query rất nhanh có thể đo thành 0 ms. Chia thời gian của nhóm 10 requests giảm sai số lượng tử nhưng vẫn chưa tương đương high-resolution benchmark.

### 21.3. Thử nghiệm có thể làm nóng cache

Nhiều repeated reads sẽ làm dữ liệu/index vào cache. Ghi rõ warm vs cold, run order và tài nguyên dùng chung.

### 21.4. SLO phải đo ở ứng dụng

Mongosh timing không gồm mọi yếu tố của Java service: connection acquisition, network round trip, DTO mapping, service concurrency, API middleware và payload serialization.

## 22. Thiết kế phép đo công bằng

Một A/B experiment tối thiểu nên giữ:

- Cùng server version và topology.
- Cùng dữ liệu và indexes ngoại trừ index ứng viên.
- Cùng query shape, projection, sort, limit và read preference.
- Cùng user/tenant distribution.
- Cùng concurrency và request rate.
- Cùng cache condition khi có thể.
- Không có batch import/index build/backup lớn xen giữa.
- Cùng mức CPU/IO/disk pressure theo metrics.
- Cùng ứng dụng/driver version khi đo end-to-end.

### 22.1. Một lượt A trước B có bias

Sau khi tạo index, cache có thể ấm hơn, thời gian khác và workload host khác. Với benchmark nghiên cứu, có thể lặp ở môi trường cô lập và đảo thứ tự/chạy nhiều phiên.

### 22.2. Không làm lạnh cache production để thí nghiệm

Thao tác restart/drop cache có thể gây gián đoạn và làm mất tính đại diện. Dùng staging nếu cần phân biệt cold-cache.

### 22.3. Explain và benchmark trả lời câu hỏi khác

- Explain: server làm những bước gì?
- Latency benchmark: request tốn bao lâu dưới điều kiện đo?
- Metrics theo thời gian: hiệu quả có bền vững dưới tải thực không?

Cần cả ba để kết luận.

## 23. Equality, Sort, Range (ESR) chi tiết hơn

Heuristic ESR:

~~~text
Equality fields
      |
      v
Sort fields
      |
      v
Range fields
~~~

Nhưng phải dựa vào query patterns và chọn lọc. Ví dụ query:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  status: "PAID",
  totalMinor: { $gte: NumberLong(400000) }
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 23.1. Index thiên về sort

~~~javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1,
  totalMinor: 1
}
~~~

Query có thể tận dụng thứ tự createdAt, đồng thời kiểm tra totalMinor. Nhưng nếu rất ít records đạt totalMinor, nó có thể phải scan nhiều keys trước khi đủ 20 results.

### 23.2. Index thiên về range

~~~javascript
{
  tenantId: 1,
  status: 1,
  totalMinor: 1,
  createdAt: -1,
  _id: -1
}
~~~

Có thể lọc theo totalMinor tốt hơn, nhưng sort theo createdAt có thể không được hỗ trợ liền mạch sau range field, dẫn tới blocking sort.

### 23.3. Không có một thứ tự tốt cho mọi query

Với low selectivity range, index thiên về sort có thể hiệu quả. Với very selective range và ít results, index theo range có thể tốt hơn. Hãy dùng explain và measurements, không chỉ lý thuyết ESR.

## 24. Thực hành truy vấn B có range theo thời gian

Tìm orders tenant-07 PAID từ ngày 15/01/2026 tới trước 01/02/2026:

~~~javascript
var filterB = {
  tenantId: "tenant-07",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-01-15T00:00:00Z"),
    $lt: ISODate("2026-02-01T00:00:00Z")
  }
};

orders.find(filterB)
  .sort({
    createdAt: -1,
    _id: -1
  })
  .limit(20)
  .explain("executionStats");
~~~

### 24.1. Khoảng [from, to)

Dùng biên trái inclusive và biên phải exclusive để các khoảng liền kề không trùng hoặc mất record ở ranh giới.

### 24.2. Cùng index có thể hỗ trợ

Index (tenantId,status,createdAt desc,_id desc) có thể đáp ứng equality và range/sort trên createdAt khi conditions phù hợp.

### 24.3. Luôn kiểm tra nReturned và examined

Nếu khoảng thời gian không có records, explain có thể trả nReturned=0. Không dùng kết quả đó để kết luận index “siêu nhanh” trên workload có nhiều records.

### 24.4. Date phải là BSON Date

Nếu createdAt được lưu thành string, filter bằng ISODate có thể không match như kỳ vọng và sort semantics có thể khác.

## 25. Thực hành index cho customer history

Mẫu truy vấn khác:

~~~javascript
var filterC = {
  tenantId: "tenant-07",
  customerId: "customer-0007"
};

var sortC = {
  createdAt: -1,
  _id: -1
};
~~~

Index dành cho AP này có thể là:

~~~javascript
{
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
}
~~~

### 25.1. Index của query A không thay index của query C

Index tenantId,status,createdAt không có customerId ở prefix; nó không phải lựa chọn tốt nhất cho mọi customer-history query.

### 25.2. Test với dữ liệu representative

Trong seed, customerId được sinh từ i % 300; distribution có thể tương quan với tenantId. Hãy xem countDocuments(filterC) trước khi suy luận về selectivity.

### 25.3. Không tạo index cho mỗi endpoint theo quán tính

Tập hợp read/write workloads rồi chọn một bộ index nhỏ có khả năng phục vụ nhiều query shapes. Mỗi index thêm overhead.

## 26. Thứ tự khóa trong compound index

Hai indexes:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }

{ status: 1, tenantId: 1, createdAt: -1 }
~~~

Có thể đều phục vụ query có equality trên cả tenantId và status, nhưng khác nhau về khả năng hỗ trợ queries chỉ có tenantId hoặc chỉ có status.

### 26.1. Prefix rule

Index có các fields ở đầu (prefix) phù hợp thường tái sử dụng tốt cho query theo prefix đó. Trường đứng sau một field bị bỏ qua có thể không đem lại cùng hiệu quả.

### 26.2. Query multi-tenant

Trong hệ thống tenant-scoped, tenantId thường xuất hiện gần như mọi query. Đặt tenantId đầu index có thể có giá trị tái sử dụng, nhưng vẫn cần kiểm tra cardinality và dữ liệu thật.

### 26.3. Status một mình

Status PAID thường có cardinality thấp và match nhiều documents; một index chỉ status có thể không mang lợi ích như kỳ vọng.

## 27. Sort direction và index direction

Index:

~~~javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

Với tenantId/status equality, index có thể hỗ trợ thứ tự createdAt desc, _id desc và trong trường hợp thích hợp có thể quét ngược để hỗ trợ createdAt asc, _id asc.

### 27.1. Mixed directions cần xem key pattern

Một sort createdAt desc, _id asc không giống việc đảo chiều hoàn toàn của createdAt desc, _id desc. Có thể cần index khác tùy query.

### 27.2. Không đổi business sort để khớp index

Nếu API yêu cầu createdAt desc, không tự sửa thành asc chỉ để thấy IXSCAN.

### 27.3. Explicit sort giúp correctness

Không dựa vào natural order/index order khi query không khai báo sort.

## 28. Covered query và projection

Một query có thể được đáp ứng hoàn toàn từ index keys nếu query filter, sort và projection chỉ cần các fields có trong index, không cần fetch full documents.

Ví dụ:

~~~javascript
orders.find(
  filterA,
  {
    _id: 0,
    tenantId: 1,
    status: 1,
    createdAt: 1
  }
).sort(sortA)
 .limit(20)
 .explain("executionStats");
~~~

### 28.1. Tại sao exclude _id đôi khi quan trọng?

_id thường được trả theo mặc định. Nếu index không chứa _id và projection cần _id, MongoDB có thể phải fetch document. Trong lab index có _id ở key pattern nên trường đó vẫn có thể được cover; phải đọc explain thực tế.

### 28.2. Dấu hiệu covered query

Có thể thấy không cần FETCH, totalDocsExamined rất thấp hoặc bằng 0 theo plan, nhưng cách thể hiện phụ thuộc engine/plan shape.

### 28.3. Covered query không tự đồng nghĩa response nhanh vô điều kiện

Mất thời gian network, JSON decode, client pool và serialization vẫn có thể chi phối với query rất nhỏ.

### 28.4. Không lẫn hai thí nghiệm

Khi muốn đo lợi ích của index, giữ projection như baseline. Khi muốn đo projection coverage, coi đó là thí nghiệm thứ hai có baseline riêng.

## 29. Multikey index và arrays

Seed có field items là array:

~~~javascript
{
  items: [
    { sku: "sku-7", qty: 2 }
  ]
}
~~~

Nếu thường truy vấn theo SKU:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  "items.sku": "sku-7"
});
~~~

Candidate index:

~~~javascript
{
  tenantId: 1,
  "items.sku": 1
}
~~~

### 29.1. Index array trở thành multikey

Một document có nhiều phần tử array có thể tạo nhiều index entries. totalKeysExamined có thể lớn hơn số documents examined/returned.

### 29.2. $elemMatch đúng semantics

Nếu cần cùng một item có sku X và qty >=2, dùng $elemMatch để ràng buộc hai predicates vào cùng phần tử. Hai dot predicates riêng có thể match hai elements khác nhau.

### 29.3. Hạn chế compound multikey

Có quy tắc với các array fields/parallel arrays trong compound indexes; phải kiểm tra schema và MongoDB version thay vì thêm nhiều array fields tùy tiện.

### 29.4. Không tạo array index vì chỉ có array

Nếu API không truy vấn items.sku, index đó chỉ tăng chi phí writes/storage.

## 30. Partial indexes

Một partial index chỉ lưu các documents thỏa điều kiện filter được khai báo.

Ví dụ index cho các orders PAID:

~~~javascript
// Lab-only design candidate:
db.orders.createIndex(
  {
    tenantId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_paid_tenant_created",
    partialFilterExpression: {
      status: "PAID"
    }
  }
);
~~~

### 30.1. Query phải đủ điều kiện dùng partial index

Một query không giới hạn status không thể tùy ý dùng index chỉ chứa PAID mà vẫn trả đủ tất cả records. Planner chỉ dùng partial index khi query predicate bảo đảm không bỏ sót kết quả.

### 30.2. Tách thí nghiệm

Đừng tạo partial index cùng lúc với index A rồi suy ra index nào làm hiệu năng cải thiện. Chạy variant trong lab riêng hoặc ghi chính xác winningPlan/hint khi được phép.

### 30.3. Partial không phải unique toàn tập

Nếu partial index có unique, uniqueness chỉ được áp dụng trên subset thuộc partial filter. Thiết kế business constraint phải hiểu điều này.

## 31. Sparse và TTL indexes không thay index query

- **Sparse index:** chỉ bao gồm documents có field theo semantics của index; không bảo đảm phù hợp mọi filter.
- **TTL index:** xóa documents theo thời gian server một cách bất đồng bộ; không phải công cụ tối ưu mọi truy vấn date.
- **Text index:** phục vụ text search semantics, không giống regex hay index compound cho sort.
- **Wildcard index:** có thể hỗ trợ schemas linh hoạt, nhưng không luôn tốt bằng index có key pattern rõ.
- **Hashed index:** phục vụ một số mục đích phân phối/equality, không hỗ trợ range/sort như B-tree tương ứng.

### 31.1. Mỗi loại phục vụ mục tiêu khác

Đừng đưa TTL vào thí nghiệm hiệu năng query A, vì nó có thể làm dữ liệu biến mất và phá baseline.

### 31.2. Tránh index explosion

Nếu mỗi query shape có một index riêng, writes có thể chậm và storage/index build khó quản lý. Ưu tiên workload review.

## 32. Collation và case-insensitive queries

Một query dùng collation khác có thể không tận dụng index được tạo với collation không tương thích.

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  status: "PAID"
}).collation({
  locale: "en",
  strength: 2
}).explain("executionStats");
~~~

### 32.1. Đừng chỉ xem field names

Index key pattern giống nhau nhưng collation options khác có thể làm planner chọn đường đi khác.

### 32.2. Khi nào cần collation?

Tên khách, sắp xếp chuỗi và case-insensitive matching có thể cần collation. Status enums/tenant IDs thường có semantics exact; đừng thay collation chỉ để chữa một query plan mà chưa xác định yêu cầu.

### 32.3. SBE/classic và collation

Output stages có thể thay đổi theo phiên bản. Quy tắc kiểm chứng vẫn là query semantics đúng và công việc thực thi hợp lý.

## 33. Regex và query patterns không tận dụng index tốt

Ví dụ:

~~~javascript
db.orders.find({
  customerId: {
    $regex: "0007"
  }
});
~~~

Regex không có anchored prefix có thể khiến index kém hiệu quả. Nếu business cần exact customer ID, dùng equality thay vì regex.

### 33.1. Prefix regex là trường hợp khác

Một số anchored prefix regex có thể sử dụng index tốt hơn tùy collation/pattern. Đừng khái quát tất cả regex đều không dùng được index.

### 33.2. Text search dùng cơ chế riêng

Khi người dùng muốn tìm nội dung tự do, cần cân nhắc text index, Atlas Search hoặc giải pháp search chuyên dụng theo yêu cầu.

## 34. $in, $or và nhiều nhánh query

Ví dụ nhiều statuses:

~~~javascript
db.orders.find({
  tenantId: "tenant-07",
  status: {
    $in: ["PAID", "PENDING"]
  }
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 34.1. Một index không bảo đảm sort toàn tập

Khi status có nhiều giá trị, dữ liệu có thể nằm ở nhiều index ranges. Planner có thể merge sorted streams hoặc thực hiện SORT tùy plan và version.

### 34.2. Chọn lọc và kích thước $in

Một danh sách $in nhỏ khác với hàng nghìn values. Hãy đo actual examined keys, plan stages và latency.

### 34.3. $or

Nếu có nhiều branches, từng branch có thể dùng index khác nhau hoặc bị scan. Đọc plan chi tiết, đừng đánh giá chỉ bằng top-level stage.

## 35. Aggregation pipeline: $match, $sort, $limit

Tương đương query A dưới dạng aggregation:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-07",
      status: "PAID"
    }
  },
  {
    $sort: {
      createdAt: -1,
      _id: -1
    }
  },
  { $limit: 20 }
]);
~~~

Explain:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-07",
      status: "PAID"
    }
  },
  {
    $sort: {
      createdAt: -1,
      _id: -1
    }
  },
  { $limit: 20 }
]);
~~~

### 35.1. Pipeline optimizer có thể đẩy/hoán đổi stages

Không giả định thứ tự văn bản trong pipeline chính xác là thứ tự mọi bước vật lý. Explain cho biết execution plan được tối ưu.

### 35.2. $group thay đổi bài toán

Một pipeline $group theo status hoặc sum totalMinor cần xử lý nhiều documents hơn dù cuối cùng trả vài groups. Không so nReturned giữa query detail và aggregation report như cùng loại workload.

### 35.3. $lookup là một thí nghiệm khác

$lookup có thể chịu ảnh hưởng của indexes ở collection được join, cardinality và engine. Giữ riêng query shape khi đánh giá.

## 36. Query hints — dùng cho chẩn đoán, không làm mặc định

Sau khi index ứng viên đã tồn tại, có thể so một query với hint:

~~~javascript
orders.find(filterA)
  .sort(sortA)
  .limit(limitA)
  .hint("idx_tenant_status_created_id")
  .explain("executionStats");
~~~

### 36.1. Hint giúp cô lập index candidate

Nếu planner chưa chọn index, hint cho phép kiểm tra index đó thực thi như thế nào trong lab.

### 36.2. Hint không phải bằng chứng index tốt hơn

Một forced plan có thể chậm hơn winning plan. So metrics và correctness trước khi dùng.

### 36.3. Không nhúng hint cứng trong production chỉ để làm explain đẹp

Một hint cố định có thể trở nên xấu khi distribution, workload hay indexes thay đổi. Chỉ áp dụng khi có justification, monitoring và kế hoạch cập nhật.

## 37. Hidden indexes và phép thử khả năng thiếu index

MongoDB hỗ trợ hidden indexes trong các phiên bản tương thích, cho phép planner bỏ qua index bị ẩn mà vẫn duy trì nó trong write path.

Ví dụ trong lab:

~~~javascript
orders.hideIndex(
  "idx_tenant_status_created_id"
);

// Compare explain while hidden.

orders.unhideIndex(
  "idx_tenant_status_created_id"
);

// Compare explain when visible again.
~~~

### 37.1. Hidden index vẫn có write/storage cost

Ẩn index không phải drop index. Nó thường vẫn được bảo trì, tiêu tốn storage và write overhead.

### 37.2. Không bật/tắt hidden trên production tùy tiện

Đây là thay đổi planner-visible behavior có thể gây latency regression. Cần change approval, metrics và rollback.

### 37.3. Lab dùng index visibility như biến thí nghiệm

Ẩn rồi hiện có thể giúp so plan trong cùng collection mà không xóa dữ liệu, nhưng lưu ý plan cache và quá trình planner thay đổi khi visibility đổi.

## 38. Plan cache và tính biến thiên của kế hoạch

Một query shape có thể dùng cached plan hoặc được replan theo điều kiện nhất định. Explain query có thể không mô phỏng toàn bộ production plan cache behavior.

### 38.1. Đừng so một explain duy nhất rồi kết luận vĩnh viễn

Mẫu dữ liệu, distribution, indexes và server version thay đổi có thể làm planner chọn khác.

### 38.2. Theo dõi truy vấn thực tế

APM, slow query logs và telemetry qua thời gian cần được đối chiếu với explain lab.

### 38.3. Đừng xóa plan cache trong production chỉ để benchmark

Đây có thể là thay đổi ảnh hưởng traffic; nếu cần thí nghiệm, dùng staging hoặc thao tác được phê duyệt.

## 39. Quan sát mức sử dụng index

MongoDB có aggregation stage $indexStats:

~~~javascript
orders.aggregate([
  {
    $indexStats: {}
  }
]);
~~~

### 39.1. IndexStats cho biết gì?

Có thông tin usage/counters của index theo ngữ cảnh node/version. Có thể giúp kiểm kê index chưa được dùng trong một window.

### 39.2. Cẩn thận với counters

Counters có thể reset khi restart hoặc trải qua khoảng thời gian không đại diện. Một index ít dùng hôm nay có thể rất quan trọng cho monthly reports.

### 39.3. Không dùng indexStats làm quyết định drop duy nhất

Cần biết query workload, reports định kỳ, unique constraints, dependency của ứng dụng và phương án rollback.

## 40. Index storage và chi phí ghi

Thêm index có thể giúp reads nhưng cũng có:

- Storage bổ sung cho index keys.
- Memory/cache pressure.
- Chi phí insert/update/delete.
- Thời gian index build.
- Chi phí replication và recovery trong một số trường hợp.
- Chi phí quản lý schema/DDL.
- Một số update trên indexed fields cần cập nhật index entries.

### 40.1. Đo index size

Trong lab có thể quan sát collection stats:

~~~javascript
var stats = lab.runCommand({
  collStats: "orders",
  scale: 1024 * 1024
});

printjson({
  count: stats.count,
  sizeMiB: stats.size,
  storageSizeMiB: stats.storageSize,
  totalIndexSizeMiB: stats.totalIndexSize,
  indexSizesMiB: stats.indexSizes
});
~~~

Các field và units cần kiểm tra theo server version/collStats response; chỉ ghi số liệu thực từ môi trường lab.

### 40.2. Thử write overhead trong bài test riêng

Một test đo inserts trước và sau index cần cùng batch size, cùng distribution, không trùng id, warm-up và load conditions. Không trộn vào phép đo query A vì nó làm thay đổi dataset.

### 40.3. Index ít vẫn chưa đủ

Giữ indexes thiết yếu cho correctness/unique constraints. Đừng hy sinh uniqueness để giảm write overhead.

## 41. Sharding và query targeting

Nếu production là sharded cluster, index tốt trên từng shard chưa đủ nếu mongos phải fan-out tới tất cả shards.

### 41.1. Query phải xem shard key

Nếu query có shard key đầy đủ, mongos có thể route tới shard phù hợp. Nếu không, có thể scatter-gather, làm tổng latency cao.

### 41.2. Explain trên sharded cluster

Có thể có kết quả per-shard execution và mongos merge stages. Không so trực tiếp với single-node lab rồi khẳng định production sẽ có cùng latency.

### 41.3. Tenant skew

Một tenant chiếm phần lớn data/traffic có thể tạo hotspot; index tenantId/status không tự giải quyết shard distribution.

### 41.4. Thực hành nâng cao

Lấy query shape production đã sanitize, kiểm tra shard targeting và explain trên môi trường staging sharded có topology tương đương.

## 42. Replica set, read preference và trạng thái cache

Một thí nghiệm A/B cần thống nhất nơi đọc.

### 42.1. Reads từ secondary có thể lag

Nếu query trước đọc primary và sau đọc secondary, data state/latency có thể khác. Pin read preference theo mục tiêu thử nghiệm và ghi rõ.

### 42.2. Primary và secondary có tải khác

Một secondary phục vụ analytics có thể đang bận, khiến query p95 cao dù plan giống.

### 42.3. Cần workload tương đương

Đo trong giờ cao điểm so với giờ thấp điểm có nhiều confounders hơn tác động index.

### 42.4. Index DDL có chi phí trên members

Trong replica set, index changes có tác động trên topology. Không dùng lab nhỏ để đánh giá toàn bộ operational risk.

## 43. Metrics ứng dụng cần đi cùng explain

Để quyết định index cho endpoint production, nên có:

| Tầng | Metric | Ý nghĩa |
| --- | --- | --- |
| HTTP | p50/p95/p99 response latency | Người dùng cảm nhận |
| HTTP | 5xx/timeouts | Độ ổn định |
| Java driver | Command duration | Round trip MongoDB command |
| Java driver | Pool acquisition wait | Chờ connection |
| MongoDB | Query docs/keys examined | Công việc của server |
| MongoDB | CPU/disk/cache | Ảnh hưởng tài nguyên |
| MongoDB | Slow query rate | Regression theo thời gian |
| MongoDB | Write latency | Chi phí index thêm |
| MongoDB | Replication lag | Sức khỏe replica |
| Business | Exact result correctness | Không làm sai dữ liệu |

### 43.1. Không gộp mọi latency

Một query server chạy 5 ms vẫn có thể làm API mất 400 ms do waiting/serialization. Index không chữa mọi tầng.

### 43.2. Phân tách bằng tracing

Một trace nên biểu diễn HTTP handler, DB operation và external calls. So trước/sau cùng version và request distribution.

## 44. Java Sync Driver: xem explain

Khi đã có Java Sync Driver version tương thích, có thể dùng API `FindIterable.explain` để xem plan.

~~~java
import com.mongodb.ExplainVerbosity;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

import org.bson.Document;
import org.bson.conversions.Bson;

public class QueryExplainDemo {

    public static void main(String[] args) {
        String uri = System.getenv(
            "MONGODB_TEST_URI"
        );

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "MONGODB_TEST_URI is required"
            );
        }

        try (
            MongoClient client = MongoClients.create(uri)
        ) {
            MongoDatabase db = client.getDatabase(
                "mongo_index_lab_459"
            );

            MongoCollection<Document> orders =
                db.getCollection("orders");

            Bson filter = Filters.and(
                Filters.eq(
                    "tenantId", "tenant-07"
                ),
                Filters.eq(
                    "status", "PAID"
                )
            );

            Bson sort = Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")
            );

            Document explain = orders
                .find(filter)
                .sort(sort)
                .limit(20)
                .explain(
                    ExplainVerbosity.EXECUTION_STATS
                );

            System.out.println(
                explain.toJson()
            );
        }
    }
}
~~~

### 44.1. Dùng test URI riêng

Không fallback sang MongoDB production nếu biến môi trường test thiếu. Tài khoản và network phải thuộc deployment thực hành.

### 44.2. MongoClient lifecycle

Với service backend, MongoClient thường được tái sử dụng thay vì tạo/đóng theo mỗi request. Ví dụ này chạy một lần nên try-with-resources phù hợp.

### 44.3. Đừng gắn explain vào mỗi production request

Explain có overhead và có thể làm thay đổi đặc điểm thực thi. Dùng telemetry/APM cho production hot path.

## 45. Java: đo client-observed wall clock

Một phép đo đơn giản:

~~~java
long startNanos = System.nanoTime();

List<Document> result = orders
    .find(filter)
    .sort(sort)
    .limit(20)
    .into(new ArrayList<>());

long durationNanos =
    System.nanoTime() - startNanos;

double durationMs =
    durationNanos / 1_000_000.0;

System.out.println(
    "Documents: " + result.size()
);

System.out.println(
    "Elapsed ms: " + durationMs
);
~~~

### 45.1. Cần warm-up và repetitions

Một sample có thể bị ảnh hưởng bởi JIT, class loading, connection establishment, GC, cache và network. Dùng test harness phù hợp với warm-up và nhiều lần chạy.

### 45.2. Đo time inclusive có chủ đích

Đoạn code này bao gồm driver operation và materialization result vào List, không phải chỉ server execution time.

### 45.3. Không tạo client mới cho mỗi sample

Nếu làm vậy, đo connection setup thay vì query performance.

### 45.4. Không đưa toàn bộ collection vào List

Ở đây limit=20. Với datasets lớn, cần cursor/pagination chứ không đọc vô hạn vào heap.

## 46. Kiểm thử correctness cùng hiệu năng

Một bài lab không kết thúc khi p95 giảm.

Các assertions nên gồm:

- Chỉ trả tenant-07.
- Chỉ status PAID.
- Thứ tự createdAt desc và _id desc.
- Không quá 20 records.
- Kết quả cùng IDs theo thứ tự trước/sau.
- Không duplicate ở một page.
- CountDocuments(filterA) đúng với seed.
- Projection phù hợp API contract.
- Query không bỏ dữ liệu do collation/type mismatch.
- Không có update/delete phát sinh khi thử nghiệm.

### 46.1. Không dùng explain để chứng minh correctness toàn bộ

Explain ghi plan và counters nhưng không thay assertions về tenant isolation và business semantics.

### 46.2. Test concurrent updates là phạm vi khác

Nếu production có writes liên tục, pagination consistency cần test riêng; một lab data tĩnh chỉ chứng minh behavior tại một snapshot.

## 47. Checklist kết luận một index có đáng tạo không

1. Query shape đủ phổ biến hoặc ảnh hưởng SLO.
2. Baseline explain có work lớn so với nReturned.
3. Candidate index hỗ trợ filter/sort/range cần thiết.
4. After explain cho thấy work giảm hoặc plan tốt hơn.
5. Query result correctness không thay đổi.
6. Client-observed p95 cải thiện khi workload tương đương.
7. Server CPU/I/O không tăng bất thường.
8. Write overhead và index storage chấp nhận được.
9. Unique/index constraints không bị vi phạm.
10. Không tạo duplicate indexes không cần thiết.
11. Index build/rollout có kế hoạch an toàn.
12. Có rollback và monitoring regression.
13. Biết phạm vi kết luận: lab vs staging vs production.

### 47.1. Nếu plan đẹp nhưng latency không giảm

Đó không nhất thiết là thất bại. Có thể query đã quá nhanh và network/app mới là bottleneck; hoặc storage cache/CPU khác điều kiện.

### 47.2. Nếu latency giảm nhưng docsExamined không đổi

Có thể cache, load, topology hoặc run order gây khác. Cần đo thêm trước khi gán công cho index.

## 48. Những lỗi đo lường phổ biến

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Dùng 10 documents để so index | Planner khác production | Representative dataset |
| Đo mỗi lượt một lần | Noise và warm-up bias | Repeated samples |
| So hai queries khác filter | Không cùng workload | Query shape cố định |
| Thêm index rồi đổi projection | Confounded change | Tách thí nghiệm |
| Không đo correctness | Có thể trả sai dữ liệu | Exact result assertions |
| Nhầm explain millis với API latency | Đánh giá sai SLO | Driver/APM/end-to-end |
| Thấy IXSCAN là kết luận tối ưu | Scan keys rất nhiều | Keys/docs examined |
| Thấy COLLSCAN là kết luận sai | Có thể hợp lý với data nhỏ | Cost/selected plan |
| Không xem SORT | Sort có thể chi phối | Stage interpretation |
| Thiếu tie-breaker | Pagination không ổn định | Sort thêm _id |
| Giả định stage JSON cố định | Lỗi automation giữa versions | Version-aware parsing |
| Không ghi MongoDB version | Khó tái hiện | Environment metadata |
| Không ghi index inventory | Baseline bẩn | getIndexes trước/sau |
| Tạo nhiều candidate indexes cùng lúc | Không biết index nào giúp | Một biến mỗi trial |
| Dùng hint mặc định cho production | Forced bad plan | Hint chỉ khi có bằng chứng |
| Quên partial-index predicate | Query không dùng được index | Check implication |
| Thay collation mà không ghi | Index compatibility đổi | Preserve collation |
| Bỏ qua multikey array | KeysExamined lớn | Inspect array cardinality |
| Dùng skip cực lớn | Pagination chậm | Keyset khi phù hợp |
| Kết luận từ cold vs warm cache | False speedup | Controlled repetitions |
| Restart production để cold cache | Gây gián đoạn | Staging |
| Không đo write overhead | Index trade-off bị bỏ qua | Write/storage metrics |
| Bỏ qua sharded routing | Chậm do scatter-gather | Shard targeting metrics |
| Quên read preference | So các nodes khác nhau | Pin/report read path |
| Chạy load test production đang quá tải | Gây sự cố | Isolated staging |
| Không có rollback | Khó đảo index change | Change plan |

## 49. Bài tập về query và explain

### Bài 1 — Baseline query

Với dataset 48.000 orders, viết find tenant-07/status PAID, sort createdAt desc/_id desc và limit 20. Ghi exact query shape.

### Bài 2 — Phân phối

Vì sao status = statuses[i % 4] không phù hợp khi tenant = i % 24? Tính số records mỗi tenant/status với công thức seed đã chọn.

### Bài 3 — Baseline explain

Chạy explain executionStats trước index. Ghi winningPlan, nReturned, docsExamined, keysExamined, executionTimeMillis.

### Bài 4 — Query planner verbosity

So queryPlanner, executionStats và allPlansExecution. Điều nào cung cấp runtime counters, điều nào gồm candidate plan observations?

### Bài 5 — Explain stage

Một plan có IXSCAN, FETCH và SORT. Mỗi stage có ý nghĩa gì? Vì sao IXSCAN chưa đủ để kết luận sort được index hỗ trợ?

### Bài 6 — Selectivity

Query match 500/48.000 docs và limit 20. Viết khác nhau giữa số match và nReturned.

## 50. Bài tập về compound indexes

### Bài 7 — ESR

Thiết kế compound index cho tenantId/status equality và createdAt/_id descending sort; giải thích thứ tự khóa.

### Bài 8 — Index prefix

So `{tenantId,status,createdAt}` với `{status,tenantId,createdAt}` khi query chỉ có tenantId.

### Bài 9 — Sort directions

Một index createdAt:-1,_id:-1 hỗ trợ sort nào khi quét thuận hoặc ngược? Phân tích sort createdAt:-1,_id:1.

### Bài 10 — Range vs sort

Thêm totalMinor>=400000 vào query. So ưu và nhược của đặt totalMinor trước createdAt so với sau.

### Bài 11 — Index scan lớn

Một plan có keysExamined=5000, docsExamined=20, nReturned=20. Tại sao vẫn cần điều tra scan keys?

### Bài 12 — Covered query

Viết projection chỉ các fields nằm trong compound index, sau đó quan sát FETCH/docsExamined.

### Bài 13 — Partial index

Thiết kế index chỉ cho PAID orders. Khi nào query có thể dùng index đó? Vì sao query không lọc PAID có nguy cơ thiếu dữ liệu?

### Bài 14 — Array index

Tạo compound index tenantId/items.sku và phân tích vì sao là multikey. Khi nào dùng $elemMatch?

## 51. Bài tập về đo đạc và benchmarking

### Bài 15 — A/B timing

Chạy 20 groups x 10 queries trước và sau index. Ghi median/p95, index inventory và environment info.

### Bài 16 — Cold vs warm

Vì sao query sau index có thể nhanh hơn chỉ vì cache đã ấm? Thiết kế phép đo giảm bias.

### Bài 17 — Server vs client

Explain báo executionTimeMillis=5 nhưng API p95=450 ms. Nêu các tầng có thể tạo chênh lệch và telemetry cần thêm.

### Bài 18 — Result correctness

Lưu baselineIds, tạo index, chạy cùng query và so exact result IDs. Vì sao cần cùng sort/limit?

### Bài 19 — Dataset thiếu

Seed dừng ở 25.000/48.000 records. Có được dùng làm baseline không? Nêu điều kiện để bắt đầu lại an toàn.

### Bài 20 — Storage cost

Đo totalIndexSize trước/sau thêm index. Vì sao chưa thể suy ra write impact chỉ từ size?

### Bài 21 — Concurrent load

So hai p95 thu ở workload khác QPS/concurrency. Vì sao kết luận speedup là không công bằng?

## 52. Bài tập nâng cao

### Bài 22 — Customer history

Thiết kế index cho tenantId/customerId và sort createdAt/_id; chỉ ra query A index không nhất thiết tối ưu cho query này.

### Bài 23 — $in và sort

Query PAID hoặc PENDING cùng tenant và sort time. Có thể dùng index A thế nào? Những stages nào cần kiểm tra?

### Bài 24 — Collation

Case-insensitive query thay collation. Tại sao planner có thể không dùng index cũ?

### Bài 25 — Hint

Giải thích tình huống dùng hint để so candidate index nhưng không bắt buộc ứng dụng production dùng hint.

### Bài 26 — Hidden index

Thiết kế một thí nghiệm hide/unhide index trên lab, ghi metrics và xác nhận index vẫn có storage/write overhead.

### Bài 27 — Sharded routing

Một query không chứa shard key, fan-out nhiều shards. Index trên mỗi shard có giải quyết trọn vấn đề không?

### Bài 28 — Index write regression

Sau thêm index, read p95 giảm nhưng insert p95 tăng. Những metrics và business trade-offs nào cần cân nhắc?

### Bài 29 — Production change

Viết một change proposal gồm index DDL, expected benefit, load risk, monitoring gates, rollback và owner.

### Bài 30 — Báo cáo tổng hợp

Điền bảng trước/sau bằng số đo thực tế, phân biệt observed evidence, hypothesis và recommendation. Đề xuất giữ hay bỏ candidate index, có caveats.

## 53. Mẫu báo cáo A/B cho team review

~~~yaml
experimentId: "mongo-index-lab-459"
environment:
  type: "isolated MongoDB lab"
  serverVersion: "record actual version"
  driverVersion: "record if using Java"
  topology: "record actual topology"

dataset:
  collection: "orders"
  documents: 48000
  tenants: 24
  statuses: 4
  verified: true

query:
  filter:
    tenantId: "tenant-07"
    status: "PAID"
  sort:
    createdAt: -1
    _id: -1
  limit: 20
  projection: "same before and after"

before:
  indexes: "record actual names"
  winningPlan: "record actual stages"
  nReturned: "measured"
  totalDocsExamined: "measured"
  totalKeysExamined: "measured"
  explainExecutionTimeMillis: "measured"
  clientMedianMs: "measured"
  clientP95Ms: "measured"

candidate:
  keyPattern:
    tenantId: 1
    status: 1
    createdAt: -1
    _id: -1
  name: "idx_tenant_status_created_id"

after:
  indexes: "record actual names"
  winningPlan: "record actual stages"
  nReturned: "measured"
  totalDocsExamined: "measured"
  totalKeysExamined: "measured"
  explainExecutionTimeMillis: "measured"
  clientMedianMs: "measured"
  clientP95Ms: "measured"

correctness:
  sameIdsAndOrder: "true or false"
  sameDataset: "true or false"

costs:
  indexStorage: "measured"
  writeImpact: "requires separate test"

decision:
  recommendation: "pending actual measurements"
  caveats: "lab results do not prove production p95"
  owner: "reviewer"
~~~

### 53.1. Không điền measured bằng số giả định

Báo cáo mẫu là khung để người học ghi bằng chứng thật, không tự cung cấp kết quả lab đã chạy.

### 53.2. Decision cần phạm vi

Một index tốt cho query A trong lab có thể chưa tối ưu cho hệ thống nhiều queries/write-heavy ở production.

## 54. Checklist thực hiện end-to-end

### Chuẩn bị

1. Test deployment được xác minh, không phải production.
2. Credentials và network được giới hạn.
3. MongoDB version/topology được ghi.
4. Database lab chưa có dữ liệu/index từ test cũ.
5. Dữ liệu deterministic, đủ records và đúng BSON types.
6. Seed count/distribution đã xác minh.
7. Query shape và SLO mục tiêu được viết rõ.

### Baseline

8. getIndexes được lưu.
9. Query result IDs/order được lưu.
10. explain verbosity được ghi.
11. nReturned/docsExamined/keysExamined được ghi.
12. WinningPlan và blocking SORT được nhận diện.
13. Repeated latency samples được lưu.
14. Không có writer khác thay đổi dataset.

### Candidate index

15. Equality/sort/range được phân loại.
16. Key order có rationale.
17. Index name explicit.
18. Có đánh giá storage/write cost.
19. DDL chỉ thực hiện trên lab hoặc theo change approval.
20. Không thêm nhiều indexes cùng lúc vào một phép đo.

### After và kết luận

21. Query và settings giống baseline.
22. Index inventory after được lưu.
23. Explain after được phân tích.
24. Result IDs/order giữ đúng.
25. Median/p95 được đo nhiều lần.
26. Cache/load differences được ghi lại.
27. Docs/keys examined và sort stages được đối chiếu.
28. Write/storage impact được cân nhắc.
29. Không suy từ explain millis sang end-to-end SLO.
30. Report có observations, caveats và decision.
31. Nếu triển khai, có canary/rollback/monitoring.
32. Không xóa dữ liệu hoặc index production theo thao tác lab.

## 55. Runbook thực hành nhanh

~~~text
DEFINE:
  Choose one important query shape
  Record filters, projection, sort, limit and SLO

SETUP:
  Verify dedicated lab DB
  Seed fixed data
  Check count and distribution
  Ensure no candidate index exists

BASELINE:
  Capture getIndexes
  Capture result IDs
  Capture explain executionStats
  Capture repeated wall-clock samples

DESIGN:
  Write hypothesis
  Choose compound index key pattern
  Estimate index/write trade-offs

APPLY:
  Create named index in lab

REMEASURE:
  Same query and same dataset
  Capture explain and timing
  Compare IDs, nReturned, examined, SORT

INTERPRET:
  Separate facts from assumptions
  Check confounding cache/load/topology
  Decide whether candidate index is useful

REPORT:
  Save before/after metrics
  State limitations
  Propose production rollout only with approval
~~~

## 56. Kết luận

Thực hành tối ưu MongoDB bằng index không kết thúc ở lệnh **createIndex**. Quy trình đáng tin cậy là:

- **Bắt đầu từ mẫu truy cập:** filter, sort, limit, data distribution và SLO.
- **Đo baseline trước:** index inventory, explain, examined counters và repeated latency samples.
- **Thiết kế index có giả thuyết:** equality/sort/range, cardinality và chi phí.
- **Chỉ đổi một biến mỗi lần:** không thay query/projection/dataset cùng lúc với index.
- **Đọc explain sau:** thấy query planner thực hiện ít công việc hơn hay không, có còn blocking sort không.
- **Kiểm chứng kết quả đúng:** IDs, thứ tự, tenant scope và business semantics không đổi.
- **Đo ở nhiều tầng:** explain cho server work; Java/APM cho client latency; load metrics cho tác động toàn hệ thống.
- **Cân nhắc trade-offs:** storage, writes, replication, sharding, cache và index maintenance.
- **Báo cáo trung thực:** không gán các con số giả định thành kết quả thực nghiệm, không xem một lần IXSCAN là chứng minh tối ưu vĩnh viễn.

Khi có **bằng chứng trước/sau và khả năng tái hiện**, việc thêm index trở thành một quyết định kỹ thuật được chứng minh, thay vì một hành động may rủi. Đó là nền tảng để tối ưu MongoDB an toàn khi dữ liệu và traffic tăng trưởng.

## Tài liệu tham khảo

- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/)
- [MongoDB Manual — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/#covered-query)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB Manual — Index Statistics](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
