# Đọc COLLSCAN, IXSCAN, FETCH và SORT trong kế hoạch truy vấn MongoDB

## 1. Mục tiêu: hiểu MongoDB đã làm gì để trả kết quả

Một câu truy vấn MongoDB có thể trả đúng kết quả nhưng vẫn rất chậm. Ví dụ, API chỉ cần 20 đơn hàng mới nhất của một khách, nhưng database phải đọc hàng trăm nghìn document, sắp xếp rồi mới chọn ra 20 bản ghi. Ngược lại, một truy vấn đôi khi nhanh dù MongoDB quét collection, vì collection quá nhỏ hoặc phần lớn dữ liệu đều cần được đọc.

Để quyết định nên thêm index, đổi thứ tự trường trong index hay tối ưu cách phân trang, người phát triển cần **đọc kế hoạch thực thi** thay vì chỉ quan sát thời gian phản hồi.

Bốn stage quan trọng nhất ở mức nhập môn:

- **COLLSCAN — Collection Scan:** duyệt document của collection.
- **IXSCAN — Index Scan:** duyệt các khóa trong index để tìm document ứng viên.
- **FETCH:** đọc document gốc, thường để lấy field chưa có trong index hoặc kiểm tra điều kiện chưa được index giải quyết.
- **SORT:** sắp xếp kết quả trong một bước riêng khi chưa thể lấy đúng thứ tự từ index.

Chúng xuất hiện dưới dạng **cây hoặc chuỗi stage** trong kết quả **explain()**. Tùy phiên bản MongoDB, bộ máy thực thi classic hay slot-based (SBE), plan có thể được biểu diễn khác nhau, nhưng ý nghĩa nền tảng về quét index, đọc document và sắp xếp vẫn rất quan trọng.

Sau bài này, bạn có thể:

1. Lấy explain ở các mức **queryPlanner**, **executionStats** và **allPlansExecution**.
2. Đọc cây plan từ các stage con, hiểu thứ tự xử lý và điều kiện lọc được áp dụng ở đâu.
3. Xác định khi nào một truy vấn COLLSCAN, khi nào dùng IXSCAN nhưng vẫn FETCH rất nhiều.
4. Phân biệt **index hỗ trợ filter** và **index hỗ trợ sort**.
5. Nhận diện **covered query** không cần FETCH nhờ projection và index thích hợp.
6. So sánh **totalKeysExamined**, **totalDocsExamined**, **nReturned** để tìm điểm nghẽn.
7. Dùng **hint** trong môi trường thử nghiệm, tránh kết luận hiệu năng từ vài document hoặc một lần chạy.

> Các ví dụ chạy bằng **mongosh** với database riêng **mongo_plan_lab**. Bài sử dụng các plan mẫu mang tính diễn giải; stage và số liệu thực tế có thể thay đổi theo phiên bản server, query engine, index, dữ liệu và thống kê.

## 2. Kế hoạch truy vấn là gì?

Khi nhận một lệnh find, MongoDB cần quyết định một chuỗi thao tác:

~~~text
Nhận filter + sort + projection + limit
                |
                v
        Xem các index khả dụng
                |
                v
      Ước lượng / chọn kế hoạch
                |
                v
   Đọc khóa index hoặc quét collection
                |
                v
   Kiểm tra điều kiện chưa được giải quyết
                |
                v
       Sort, projection, limit...
                |
                v
           Trả document
~~~

**Query planner** chọn cách truy cập dữ liệu; **execution engine** thực hiện kế hoạch đó. explain cho phép xem một phần quá trình lựa chọn và các chỉ số thực thi để đánh giá.

### 2.1. Phân biệt plan với query text

Hai câu truy vấn nhìn khá giống nhau:

~~~javascript
db.orders.find({ tenantId: "tA", status: "pending" });

db.orders.find({ tenantId: "tA", status: "pending" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Nhưng yêu cầu của chúng khác nhau. Truy vấn đầu chỉ cần tìm đúng document; truy vấn sau còn yêu cầu **thứ tự** và **giới hạn số bản ghi**. Một index tốt cho truy vấn đầu có thể không cung cấp được thứ tự cho truy vấn thứ hai.

Ngoài filter, lựa chọn index và plan còn chịu ảnh hưởng từ:

- Dữ liệu và tính chọn lọc của điều kiện.
- Có hay không có sort, limit, skip, projection.
- Thứ tự trường trong compound index.
- Mảng và multikey index.
- Collation và các tùy chọn index như partial/sparse.
- Phân bố dữ liệu, số lượng document và trạng thái bộ nhớ cache.
- Topology replica set/sharded cluster và phiên bản MongoDB.

**Một plan được xem là tốt khi đáp ứng nhu cầu query với tổng chi phí thấp**, không phải đơn giản vì nó có stage IXSCAN.

### 2.2. Stage là các bước thực hiện, không phải thông báo lỗi

Ví dụ cây minh họa:

~~~text
LIMIT
  |
  +-- FETCH
        |
        +-- IXSCAN
~~~

Có thể đọc từ **dưới lên** để thấy đường đi của dữ liệu: **IXSCAN** tìm khóa trong index, **FETCH** lấy document tương ứng, **LIMIT** giới hạn số kết quả trả về. Đây là sơ đồ khái niệm; MongoDB có thể đặt projection, limit hoặc filter ở những vị trí khác tùy plan và cách biểu diễn.

Tương tự:

~~~text
SORT
  |
  +-- COLLSCAN
~~~

nghĩa là database quét document, sau đó thực hiện sắp xếp riêng. Với dữ liệu nhiều và chưa có index phù hợp, cả việc quét lẫn sort đều có thể tốn tài nguyên.

## 3. Cách gọi explain và đọc cấu trúc trả về

### 3.1. Ba mức verbosity

Trong mongosh:

~~~javascript
db.orders.find({ status: "pending" })
  .explain("queryPlanner");

db.orders.find({ status: "pending" })
  .explain("executionStats");

db.orders.find({ status: "pending" })
  .explain("allPlansExecution");
~~~

| Mức | Thông tin chính | Khi nên dùng |
| --- | --- | --- |
| **queryPlanner** | Kế hoạch được chọn, thông tin các candidate/rejected plans | Muốn xem cấu trúc kế hoạch, chưa cần số đo thực thi |
| **executionStats** | Thêm số liệu thực thi của winning plan | Chẩn đoán số key/document đã duyệt và số kết quả |
| **allPlansExecution** | Thêm thông tin về việc thực thi thử các candidate plans, khi có | Phân tích sâu quyết định chọn plan |

Trong nhiều trường hợp, gọi **.explain("executionStats")** là điểm bắt đầu hữu ích nhất: vừa thấy cấu trúc plan vừa có các con số đánh giá.

Lưu ý:

- **Explain thực thi theo cơ chế phục vụ chẩn đoán**, không giống hoàn toàn một lời gọi ứng dụng bình thường.
- Explain bỏ qua hoặc không làm nóng plan cache theo cách các lệnh bình thường sử dụng, nên không dùng một lần explain làm benchmark latency production.
- Nếu muốn biết độ trễ thực tế, cần đo bằng application metrics, profiler hoặc hệ thống quan sát phù hợp, ngoài việc đọc explain.
- Các query có thể trả kết quả rất nhanh nhưng bị chậm do mạng hoặc serialization; chỉ số server trong explain không bao trùm mọi phần của API.

### 3.2. Những vị trí thường đọc trong kết quả

Một kết quả explain cho find thường có các nhánh:

~~~text
explain
  queryPlanner
    namespace
    parsedQuery
    winningPlan
    rejectedPlans
  executionStats
    nReturned
    executionTimeMillis
    totalKeysExamined
    totalDocsExamined
    executionStages
  serverInfo
  ...
~~~

Trong classic engine, stage thường xuất hiện dưới **winningPlan.stage** và các nhánh **inputStage** hoặc **inputStages**. Với SBE, có thể thấy **winningPlan.queryPlan** cùng biểu diễn **slotBasedPlan**, hoặc các stage chi tiết khác trong **executionStats.executionStages**.

Vì vậy, **đừng viết công cụ phân tích chỉ giả định stage luôn nằm tại một đường dẫn JSON duy nhất**. Khi xem trực tiếp, hãy tìm cấu trúc **queryPlanner.winningPlan** và **executionStats.executionStages**, đi theo các nhánh kế hoạch mà server thực sự trả về.

### 3.3. Đọc stage từ dưới lên

Ví dụ minh họa, không phải kết quả được chép từ một server cụ thể:

~~~json
{
  "stage": "FETCH",
  "inputStage": {
    "stage": "IXSCAN",
    "indexName": "ix_tenant_status_created",
    "indexBounds": {
      "tenantId": ["[\"tA\", \"tA\"]"],
      "status": ["[\"pending\", \"pending\"]"]
    }
  }
}
~~~

Diễn giải:

1. **IXSCAN** đọc index có tên ix_tenant_status_created.
2. **indexBounds** thể hiện vùng khóa được duyệt trên các field.
3. **FETCH** đọc document để hoàn thành phần việc chưa thể lấy trực tiếp từ index.

Đây là cách đọc kế hoạch, không phải cam kết MongoDB sẽ luôn có chính xác hai stage đó cho mọi truy vấn dùng index tương tự.

## 4. Lab: tạo dữ liệu và index có thể chạy lại

Bộ dữ liệu gồm **36 đơn hàng** có ID cố định từ **o001** đến **o036**; tenant **tA** có 24 đơn, tenant **tB** có 12 đơn. Dữ liệu gồm trạng thái pending/paid/shipped/cancelled, thời điểm createdAt, giá trị total và customerId.

Các index được chọn để tạo ra nhiều tình huống: quét collection, quét index có FETCH, quét index có thể cover query và sort có/không được hỗ trợ bởi index.

### 4.1. Script tạo dữ liệu

Chạy nguyên khối sau trong mongosh. Script chỉ dọn document mang **dataset: "plan-stages-v1"** trong **mongo_plan_lab.lab_orders**, sau đó tạo lại dữ liệu.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_plan_lab");
  const orders = lab.getCollection("lab_orders");
  const tag = "plan-stages-v1";

  orders.deleteMany({ dataset: tag });

  const statuses = ["pending", "paid", "shipped", "cancelled"];
  const documents = [];

  for (let i = 1; i <= 36; i++) {
    const id = "o" + String(i).padStart(3, "0");

    documents.push({
      _id: id,
      dataset: tag,
      tenantId: i <= 24 ? "tA" : "tB",
      customerId: "c" + String(((i - 1) % 3) + 1),
      status: statuses[(i - 1) % statuses.length],
      createdAt: new Date(Date.UTC(2026, 3, 1, 0, i, 0)),
      total: NumberInt(60 + ((i * 7) % 19) * 13),
      note: i % 5 === 0 ? "manual-review" : "normal",
      lines: [
        { sku: "SKU-" + String(i).padStart(3, "0"), qty: 1 }
      ]
    });
  }

  orders.insertMany(documents);

  // Có thể lọc tenant rồi lấy đơn mới nhất.
  orders.createIndex(
    { dataset: 1, tenantId: 1, createdAt: -1, _id: -1 },
    { name: "ix_tenant_created" }
  );

  // Lọc tenant, status và sort theo thời gian.
  orders.createIndex(
    {
      dataset: 1, tenantId: 1, status: 1,
      createdAt: -1, _id: -1
    },
    { name: "ix_tenant_status_created" }
  );

  // Lọc theo khách, không chứa note/lines.
  orders.createIndex(
    { dataset: 1, tenantId: 1, customerId: 1 },
    { name: "ix_tenant_customer" }
  );

  // Lọc/sort theo số tiền trong một tenant.
  orders.createIndex(
    { dataset: 1, tenantId: 1, total: 1 },
    { name: "ix_tenant_total" }
  );

  printjson({
    all: orders.countDocuments({ dataset: tag }),
    tenantA: orders.countDocuments({ dataset: tag, tenantId: "tA" }),
    pendingTenantA: orders.countDocuments({
      dataset: tag, tenantId: "tA", status: "pending"
    })
  });
})();
~~~

Kết quả mong đợi:

| Bộ lọc | Số document |
| --- | ---: |
| dataset = plan-stages-v1 | 36 |
| dataset và tenantId = tA | 24 |
| dataset, tenantId = tA, status = pending | 6 |

Do ID và các giá trị được tạo theo công thức cố định, chạy lại script sẽ đưa dữ liệu thực hành về trạng thái ban đầu. Không dùng script này trên database sản xuất hoặc collection chia sẻ dữ liệu quan trọng.

### 4.2. Kiểm tra index hiện có

~~~javascript
const orders = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

printjson(orders.getIndexes());
~~~

Bạn sẽ thấy index mặc định **_id_** và bốn index vừa tạo. **getIndexes** cho biết định nghĩa index; để biết query **có sử dụng** index hay không, cần xem explain chứ không suy luận từ việc index tồn tại.

### 4.3. Hàm phụ để xem thống kê ngắn gọn

Đầu ra explain rất dài. Hàm sau lấy những thống kê **cấp operation** và in ra hình dạng winningPlan để tiện quan sát:

~~~javascript
function inspectExplain(label, cursor) {
  const e = cursor.explain("executionStats");
  const stats = e.executionStats || {};

  print("== " + label + " ==");
  printjson({
    nReturned: stats.nReturned,
    totalKeysExamined: stats.totalKeysExamined,
    totalDocsExamined: stats.totalDocsExamined,
    executionTimeMillis: stats.executionTimeMillis
  });

  print("Winning plan:");
  printjson(e.queryPlanner && e.queryPlanner.winningPlan);
  return e;
}
~~~

Hàm này phục vụ **find không sharded** trong lab. Với aggregate có $cursor, môi trường sharded hoặc kết quả SBE phức tạp, thông tin có thể nằm trong nhánh khác và cần đọc cấu trúc mà server trả về; không coi hàm phụ là một thư viện explain đa phiên bản.

## 5. COLLSCAN: đọc document trực tiếp từ collection

### 5.1. COLLSCAN nghĩa là gì?

**COLLSCAN** là collection scan: MongoDB đi qua document trong collection để kiểm tra điều kiện. Nếu filter không có index phù hợp, hoặc collection quá nhỏ, planner có thể chọn COLLSCAN.

Một cách diễn giải:

~~~text
COLLSCAN:
  đọc document 1 -> kiểm tra filter
  đọc document 2 -> kiểm tra filter
  đọc document 3 -> kiểm tra filter
  ...
~~~

Nếu collection có 10 triệu document, một câu truy vấn tìm một document rất hiếm mà phải duyệt phần lớn collection có thể cực kỳ tốn kém. Nhưng nếu bạn thật sự cần đọc phần lớn collection để xuất báo cáo, một scan tuần tự có thể là lựa chọn hợp lý hơn so với đi index rồi FETCH gần như mọi document.

**COLLSCAN không tự đồng nghĩa query sai.** Cần xét kích thước dữ liệu, tỷ lệ kết quả, độ trễ mục tiêu và tài nguyên phải bỏ ra.

### 5.2. Buộc COLLSCAN để học cơ chế

Trong lab, dùng **hint({ $natural: 1 })** để yêu cầu quét theo thứ tự tự nhiên của collection, thay vì để planner chọn index:

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "Buộc collection scan",
  c.find({
    dataset: "plan-stages-v1",
    tenantId: "tA",
    status: "pending"
  }).hint({ $natural: 1 })
);
~~~

Kỳ vọng nhìn thấy **COLLSCAN** hoặc hình dạng tương ứng trong plan. Từ dữ liệu seed, truy vấn trả **6** document, nhưng để tìm chúng, scan có thể phải duyệt gần như toàn bộ **36** document.

**Không dùng $natural như một mẹo tối ưu mặc định**; nó ở đây để tạo trường hợp so sánh. Không dựa vào natural order để bảo đảm phân trang ổn định.

### 5.3. Khi nào COLLSCAN là cảnh báo?

COLLSCAN đáng điều tra nếu:

- API chạy liên tục, chỉ trả vài document nhưng collection rất lớn.
- totalDocsExamined cao hơn nReturned nhiều lần.
- p95/p99 latency cao hoặc tăng theo kích thước collection.
- Filter có tính chọn lọc nhưng không có index phù hợp.
- Có sort/aggregation blocking tiếp theo khiến phải xử lý tập lớn.

Ngược lại, COLLSCAN có thể bình thường đối với collection cực nhỏ hoặc query thật sự phải lấy gần hết dữ liệu.

## 6. IXSCAN: dùng khóa index để chọn ứng viên

### 6.1. IXSCAN không phải “đọc xong là có document”

**IXSCAN** duyệt entry của index. Nếu index có khóa:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

và query có:

~~~javascript
{
  dataset: "plan-stages-v1",
  tenantId: "tA",
  status: "pending"
}
~~~

MongoDB có thể giới hạn scan vào nhóm khóa có đúng dataset, tenant và status; không cần duyệt mọi document trong collection.

### 6.2. Dùng hint để quan sát index cụ thể

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "Index theo tenant + status",
  c.find({
      dataset: "plan-stages-v1",
      tenantId: "tA",
      status: "pending"
    })
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_tenant_status_created")
);
~~~

Từ dữ liệu seed, ba đơn pending mới nhất của tenant tA là **o021**, **o017**, **o013**.

Trong plan, tìm:

- **IXSCAN**: đang duyệt khóa index.
- **indexName**: tên index được dùng.
- **keyPattern**: thứ tự và hướng các trường trong index.
- **indexBounds**: khoảng khóa được xét cho từng trường.
- **direction**: chiều duyệt index, khi có trong plan.
- **isMultiKey/multiKeyPaths**: thông tin về multikey nếu index có field Array.

Ví dụ về **indexBounds khái niệm** (các field và ký hiệu thật có thể khác):

~~~text
dataset:   đúng "plan-stages-v1"
tenantId:  đúng "tA"
status:    đúng "pending"
createdAt: quét theo thứ tự giảm dần
_id:       quét theo thứ tự giảm dần khi cần
~~~

Các điều kiện equality giúp giảm vùng index được duyệt; phần createdAt/_id giúp giữ thứ tự kết quả. Nhưng **IXSCAN mới chỉ tạo ứng viên**. Nếu query cần field chưa có trong index, MongoDB vẫn phải FETCH document.

### 6.3. IXSCAN nhiều key chưa chắc ít document

Giả sử index trên trường tags là multikey và một document có hàng chục tag. Một document có thể đóng góp nhiều key. Query scan nhiều key nhưng trả ít document có thể xảy ra do:

- Có nhiều key index cho cùng một document.
- Index bounds rộng.
- Một phần filter không được áp ở IXSCAN, phải kiểm tra sau.
- Nhiều entry bị loại trong quá trình đọc index.

Do đó, **totalKeysExamined** và **totalDocsExamined** cần được đọc cùng **nReturned**; không so một chỉ số duy nhất rồi kết luận.

## 7. FETCH: khi phải đọc document gốc

### 7.1. Tại sao dùng index rồi vẫn FETCH?

Index lưu các giá trị trường được index và thông tin cần để truy cập document, **không mặc nhiên lưu mọi field của document**. Ví dụ index:

~~~javascript
{
  dataset: 1, tenantId: 1, status: 1,
  createdAt: -1, _id: -1
}
~~~

không chứa **note** hoặc **lines**. Nếu ứng dụng cần trả note hoặc lines, MongoDB thường phải đọc document từ collection sau khi IXSCAN xác định ứng viên.

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "IXSCAN rồi FETCH để lấy note",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA",
        status: "pending"
      },
      {
        _id: 1,
        createdAt: 1,
        note: 1,
        lines: 1
      }
    )
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_tenant_status_created")
);
~~~

Trong cách biểu diễn plan classic, có thể thấy **FETCH > IXSCAN**, cùng một projection stage ở phía trên. Với SBE, FETCH hoặc các thao tác tương đương có thể được trình bày theo những lớp khác; cần đọc plan thực tế.

### 7.2. FETCH cũng có thể là nơi kiểm tra điều kiện lọc

Không chỉ projection, một điều kiện **không nằm trong index** có thể được kiểm tra sau khi lấy document.

~~~javascript
inspectExplain(
  "Điều kiện note không nằm trong index",
  c.find({
      dataset: "plan-stages-v1",
      tenantId: "tA",
      status: "pending",
      note: "manual-review"
    })
    .hint("ix_tenant_status_created")
);
~~~

Với index đó, ba equality đầu có thể giảm tập ứng viên, nhưng **note** cần được kiểm tra sau. Trong classic plan, filter residual thường xuất hiện ở FETCH; trong SBE, biểu diễn có thể khác.

Giả sử query cuối cùng trả một document nhưng MongoDB phải FETCH hàng nghìn document ứng viên để xét note. Đó là dấu hiệu cần cân nhắc:

- note có phải field filter quan trọng chạy thường xuyên không?
- Có nên đưa note vào compound index hoặc dùng partial index không?
- Cách viết filter có thể chọn lọc hơn ở các trường đứng đầu index không?
- Truy vấn này có thật sự quan trọng để chấp nhận thêm chi phí index cho mọi lần ghi không?

**FETCH không tự là lỗi cần loại bỏ bằng mọi giá.** Một query trả 20 document nhưng cần trường lines lớn ngoài index có thể FETCH 20 document và vẫn đáp ứng SLA tốt. Việc thêm lines vào index để cover có thể làm index lớn hoặc gặp giới hạn với Array.

### 7.3. Phân biệt FETCH với COLLSCAN

Hai hình dạng có thể cùng đọc document nhưng khác cách chọn ứng viên:

~~~text
COLLSCAN
  -> duyệt document của collection để tìm document khớp

FETCH
  +-- IXSCAN
  -> duyệt index để tìm ứng viên, sau đó lấy document cần thiết
~~~

Nếu IXSCAN rất chọn lọc, FETCH ít document thường tốt. Nếu IXSCAN trả gần như toàn bộ collection rồi FETCH tất cả, công việc có thể không tốt hơn COLLSCAN, thậm chí tệ hơn.

## 8. Covered query: IXSCAN mà không cần FETCH

### 8.1. Khi nào truy vấn được cover?

Một **covered query** có thể lấy đủ thông tin cần cho filter, sort và projection từ index mà không phải đọc document gốc. Ví dụ index:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

và query chỉ cần những field đã có trong index:

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "Query có khả năng được cover",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA",
        status: "pending"
      },
      {
        _id: 0,
        status: 1,
        createdAt: 1
      }
    )
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_tenant_status_created")
);
~~~

Query vẫn sort theo _id, nhưng _id đã nằm trong index ở vị trí cuối. Projection chỉ trả status/createdAt, và các field filter cũng nằm trong index.

Khi thực sự được cover, các dấu hiệu thường gặp:

- **totalDocsExamined = 0**.
- Có **IXSCAN**, nhưng không có FETCH đọc document gốc.
- Có thể thấy **PROJECTION_COVERED** hoặc cấu trúc projection tương đương trong plan.

**Covered query là thuộc tính của cả câu truy vấn và index**, không phải index có “nhãn covered” cố định.

### 8.2. Chỉ đổi projection có thể xuất hiện FETCH

Giữ nguyên filter và sort, nhưng thêm field **note**:

~~~javascript
inspectExplain(
  "Thêm note nên cần đọc document",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA",
        status: "pending"
      },
      {
        _id: 0,
        status: 1,
        createdAt: 1,
        note: 1
      }
    )
    .sort({ createdAt: -1, _id: -1 })
    .limit(3)
    .hint("ix_tenant_status_created")
);
~~~

Vì note không nằm trong index, document phải được lấy để trả field này. So sánh **totalDocsExamined** của hai explain sẽ thấy vì sao projection có thể ảnh hưởng trực tiếp đến kế hoạch và I/O.

### 8.3. Những ngoại lệ cần lưu ý

Không phải cứ filter/projection nhắc tới trường indexed thì query chắc chắn được cover:

- Nếu projection trả **_id** nhưng index không chứa _id, thường phải FETCH; có thể loại _id bằng **_id: 0** khi API không cần.
- Khi có **Array/multikey index**, điều kiện covered query có giới hạn bổ sung: không trả về field Array và không dùng $elemMatch trong những trường hợp yêu cầu cover.
- **Collation**, **partial index**, giá trị null/missing và các điều kiện không thể được giải quyết đầy đủ từ index có thể ảnh hưởng.
- Query có filter ngoài index có thể cần FETCH để kiểm tra.

Vì vậy, chỉ kết luận query được cover sau khi đọc explain thật, đặc biệt là **totalDocsExamined = 0** và cấu trúc winning plan.

## 9. SORT: sắp xếp riêng và sắp xếp nhờ index

### 9.1. SORT là gì?

Nếu không có index đáp ứng được thứ tự yêu cầu, MongoDB phải thu thập/đánh giá ứng viên rồi **sắp xếp**. Stage **SORT** thường là một **blocking stage**: nó cần xem đủ dữ liệu đầu vào liên quan trước khi xác định thứ tự đầu ra.

~~~text
SORT by total descending
  |
  +-- FETCH
        |
        +-- IXSCAN using index ordered by createdAt
~~~

Một query vẫn có IXSCAN nhưng thêm SORT, vì **index dùng để lọc chưa chắc giúp sort**. SORT có thể tiêu tốn bộ nhớ hoặc dùng không gian tạm nếu khối lượng lớn và cấu hình/phiên bản cho phép spill.

### 9.2. Buộc dùng index không phù hợp thứ tự sort

Trong lab:

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

inspectExplain(
  "Index createdAt nhưng sort total",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA"
      },
      {
        _id: 1,
        total: 1,
        createdAt: 1
      }
    )
    .sort({ total: -1 })
    .limit(5)
    .hint("ix_tenant_created")
);
~~~

Index **ix_tenant_created** tổ chức các key sau dataset/tenant theo **createdAt**, không phải total. MongoDB phải sắp xếp lại theo total khi cần, nên có thể thấy **SORT** hoặc stage tương đương trong plan.

**LIMIT không có nghĩa MongoDB chỉ phải xem năm document**. Để biết năm giá trị total lớn nhất, query có thể phải xét nhiều ứng viên trước; khi kết hợp sort và limit, MongoDB có các tối ưu như top-k sort, nhưng vẫn cần công việc tương ứng với tập đầu vào.

### 9.3. Dùng index hỗ trợ sort

Index khác đã có:

~~~javascript
{ dataset: 1, tenantId: 1, total: 1 }
~~~

Nếu equality dataset/tenant đã cố định, MongoDB có thể đọc index theo **chiều ngược** để cung cấp sort **total: -1** mà không cần SORT riêng:

~~~javascript
inspectExplain(
  "Index theo total hỗ trợ sort",
  c.find(
      {
        dataset: "plan-stages-v1",
        tenantId: "tA"
      },
      {
        _id: 1,
        total: 1,
        createdAt: 1
      }
    )
    .sort({ total: -1 })
    .limit(5)
    .hint("ix_tenant_total")
);
~~~

Vì projection lấy **createdAt**, index total vẫn có thể cần FETCH. Nhưng **không có FETCH không phải điều kiện để loại SORT**: một index có thể cung cấp thứ tự đúng dù MongoDB vẫn cần đọc document để lấy field khác.

### 9.4. Thứ tự compound index quyết định SORT

Giả sử index:

~~~javascript
{ dataset: 1, tenantId: 1, status: 1, createdAt: -1 }
~~~

Query:

~~~javascript
{
  dataset: "plan-stages-v1",
  tenantId: "tA",
  status: "pending"
}
// sort: { createdAt: -1 }
~~~

có các equality trước createdAt; index có thể cung cấp đúng thứ tự cho nhóm status pending.

Nhưng query:

~~~javascript
{
  dataset: "plan-stages-v1",
  tenantId: "tA"
}
// sort: { createdAt: -1 }
~~~

không cố định status. Trong index, các key được nhóm theo status trước rồi mới createdAt, nên thứ tự createdAt **không phải thứ tự chung toàn tenant**. MongoDB có thể cần SORT nếu dùng index đó.

Đó là lý do có thể vẫn cần index riêng **{dataset, tenantId, createdAt}** cho màn hình xem tất cả đơn của tenant.

### 9.5. Một SORT không phải lúc nào cũng nghiêm trọng

SORT trên vài chục document có thể rất rẻ. SORT trên hàng triệu document hoặc trên field lớn có thể đắt. Khi đánh giá:

- Bao nhiêu document đi vào SORT?
- Có filter đủ chọn lọc trước SORT không?
- Sort có kết hợp limit để giảm bộ nhớ không?
- Query có thường xuyên được gọi không?
- Có thể sử dụng index theo đúng thứ tự, hay đổi index khiến filter tệ đi?

Không nên tạo index riêng cho từng sort hiếm gặp chỉ vì nhìn thấy stage SORT trong explain.

## 10. Bốn tình huống cùng một collection

Từ một tập document, có thể đối chiếu bốn loại kế hoạch:

| Trường hợp | Query / index | Stage quan trọng | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| A | Filter tenant/status, **hint $natural** | COLLSCAN | totalDocsExamined so với nReturned |
| B | Filter tenant/status, index theo status, projection cần **lines** | IXSCAN + FETCH | Keys đã giảm nhưng vẫn đọc document |
| C | Filter tenant/status, index theo status, projection chỉ field index | IXSCAN, có thể không FETCH | totalDocsExamined có bằng 0 không? |
| D | Filter tenant, index createdAt nhưng sort total | IXSCAN/FETCH + SORT | SORT có biến mất khi đổi sang index total không? |

Trong lab có 36 document, các phép đo mang tính hướng dẫn. Một plan không có FETCH có thể vẫn không phải lựa chọn tối ưu trên một workload khác; và một COLLSCAN trên vài chục document có thể là lựa chọn hoàn toàn hợp lý của planner.

### 10.1. Script so sánh nhanh

Chạy sau khi đã định nghĩa **inspectExplain** ở mục 4.3:

~~~javascript
const c = db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders");

const queue = {
  dataset: "plan-stages-v1",
  tenantId: "tA",
  status: "pending"
};

inspectExplain(
  "A - COLLSCAN",
  c.find(queue).hint({ $natural: 1 })
);

inspectExplain(
  "B - IXSCAN + FETCH",
  c.find(queue, { _id: 0, status: 1, lines: 1 })
    .hint("ix_tenant_status_created")
);

inspectExplain(
  "C - Có thể cover",
  c.find(queue, { _id: 0, status: 1, createdAt: 1 })
    .hint("ix_tenant_status_created")
);

inspectExplain(
  "D - SORT theo total",
  c.find({
      dataset: "plan-stages-v1",
      tenantId: "tA"
    })
    .sort({ total: -1 })
    .limit(5)
    .hint("ix_tenant_created")
);
~~~

Tập kết quả có thể có thứ tự không ổn định ở những truy vấn **không dùng sort**. Không lấy thứ tự in ra khi không có sort làm cơ sở phân trang.

## 11. Các chỉ số executionStats: đọc bằng tỷ lệ, không chỉ bằng tên stage

### 11.1. Ba con số quan trọng

**nReturned:** số document mà operation trả về, sau khi áp các phần cần thiết trong plan.

**totalDocsExamined:** số lần document được xem xét trong quá trình thực thi. Không nhất thiết bằng số document phân biệt nếu plan có thể duyệt cùng document nhiều lần.

**totalKeysExamined:** số entry index được xem xét trong quá trình thực thi. Với COLLSCAN thuần túy có thể bằng 0.

Giả sử một explain minh họa cho query trả 20 document:

~~~text
nReturned         = 20
totalKeysExamined = 50000
totalDocsExamined = 12000
~~~

Đây là các **con số giả định**, không phải kết quả của lab. Truy vấn đã xét rất nhiều key và document để trả 20 kết quả; cần kiểm tra index bounds, filter còn lại ở FETCH và phần sort.

Một trường hợp khác:

~~~text
nReturned         = 20
totalKeysExamined = 20
totalDocsExamined = 20
~~~

thường là tín hiệu tốt đối với query trả 20 document, nhưng vẫn cần biết latency, kích thước document, tài nguyên và ảnh hưởng trên hệ thống thật.

### 11.2. Tỷ lệ quét để hỗ trợ chẩn đoán

Có thể theo dõi những tỷ lệ tham khảo:

~~~text
documentsExamined / max(nReturned, 1)
keysExamined      / max(nReturned, 1)
~~~

Tỷ lệ cao cho thấy MongoDB đang làm nhiều việc để trả mỗi kết quả. Nhưng không có một ngưỡng “xấu” dùng cho mọi query:

- **Aggregation** tính tổng trên tất cả document có thể cố ý trả một dòng sau khi quét hàng triệu document.
- **countDocuments** cũng có ý nghĩa khác một query top 20.
- **Pagination với skip lớn** có thể cần duyệt nhiều key trước khi trả 20.
- **Multikey index** có thể có nhiều key cho một document do Array.
- **Covered query** có thể totalDocsExamined = 0 nhưng vẫn quét rất nhiều key.

Vì thế, tỷ lệ là dấu hiệu để đặt câu hỏi, không phải thước đo chất lượng tuyệt đối.

### 11.3. nReturned ở từng stage có thể khác nhau

Trong explain, một stage IXSCAN có thể tạo ra nhiều ứng viên; FETCH hoặc FILTER loại bớt; LIMIT chỉ giữ số lượng cần trả. Vì vậy **nReturned** ở từng stage không luôn bằng **executionStats.nReturned** ở cấp operation.

Ví dụ khái niệm:

~~~text
IXSCAN:  1.000 candidate index entries
FETCH:     200 document ứng viên phù hợp sau kiểm tra
LIMIT:      20 document trả cho client
~~~

Nếu chỉ đọc con số 20 rồi cho rằng database làm đúng 20 đơn vị công việc, bạn sẽ bỏ qua khối lượng quét ở các stage bên dưới.

### 11.4. executionTimeMillis và thời gian thật

**executionTimeMillis** là số liệu được MongoDB báo trong explain, nhưng nó không đại diện đầy đủ cho:

- Thời gian chờ network/connection pool.
- Serialization/deserialize document và mapping trong ứng dụng.
- Thời gian chờ API gateway hoặc xác thực.
- Cache warm/cold khác nhau giữa các lần chạy.
- Workload đồng thời và biến động tải thực.

Vì thế, đánh giá hiệu năng phải kết hợp explain với **latency p50/p95/p99 ở ứng dụng**, server metrics và tình trạng tài nguyên.

## 12. Khi explain khác tài liệu minh họa: SBE, aggregation và sharding

### 12.1. Classic engine và slot-based execution (SBE)

MongoDB có nhiều cách biểu diễn kế hoạch, tùy phiên bản và các đặc điểm query. Bạn có thể gặp:

- **queryPlanner.winningPlan.stage** trong cách biểu diễn classic.
- **queryPlanner.winningPlan.queryPlan** và **slotBasedPlan** trong những trường hợp SBE.
- **executionStats.executionStages** với các stage/đầu vào khác nhau.
- Những stage tối ưu hóa đặc biệt cho các pattern đơn giản, không nhất thiết luôn in đúng chuỗi COLLSCAN/IXSCAN/FETCH/SORT.

Đừng gắn logic giám sát vào một vị trí JSON cố định mà không xử lý các biến thể. Một query vẫn có thể dùng index dù explain hiển thị tên stage tối ưu chuyên biệt, không nhất thiết chữ **IXSCAN** nằm ở chỗ bạn quen tìm.

**Khái niệm cần giữ ổn định:** truy vấn có đọc collection hay index, có cần lấy document gốc không, có sort blocking không, và tổng lượng key/document được xét là bao nhiêu.

### 12.2. Aggregation pipeline

Ví dụ:

~~~javascript
db.getSiblingDB("mongo_plan_lab")
  .getCollection("lab_orders")
  .explain("executionStats")
  .aggregate([
    {
      $match: {
        dataset: "plan-stages-v1",
        tenantId: "tA",
        status: "pending"
      }
    },
    { $sort: { createdAt: -1, _id: -1 } },
    { $limit: 3 },
    { $project: { _id: 1, status: 1, createdAt: 1 } }
  ]);
~~~

Khi MongoDB có thể đẩy **$match**, **$sort**, **$limit** về query layer, plan có thể sử dụng index tương tự find. Khi pipeline chứa **$group**, **$lookup**, **$unwind** hoặc những stage khác, explain có thể gồm cả **$cursor** lẫn các stage aggregation riêng.

Một pipeline có SORT ở tầng aggregation không nhất thiết được mô tả giống hệt SORT trong find. Cần xem các phần tương ứng, lượng đầu vào của mỗi stage và cách optimizer đã hoán đổi/đẩy stage để giảm công việc.

### 12.3. Sharded cluster

Với collection sharded, một query có thể được thực thi trên nhiều shard và phải gộp kết quả:

~~~text
mongos / router
     |
     +---- shard A: IXSCAN -> FETCH
     |
     +---- shard B: IXSCAN -> FETCH
     |
     +---- merge / sort / limit
                  |
                  v
              kết quả
~~~

Explain có thể có nhánh **shards**, stage liên quan merge và các thống kê theo từng shard. Tổng lượng công việc không chỉ nằm trong một winningPlan. Với query không có shard key, MongoDB có thể phải khảo sát nhiều shard; index trên mỗi shard vẫn chưa đủ nếu việc định tuyến và merge tốn kém.

Trước khi kết luận “plan chỉ đọc 20 document”, phải kiểm tra tổng và từng shard nếu hệ thống thực tế có sharding.

## 13. Quy trình tối ưu từ một explain cụ thể

Giả sử màn hình cần 20 đơn pending mới nhất của tenant tA nhưng p95 latency cao. Có thể theo trình tự:

**Bước 1 — Chụp query shape thực tế.** Ghi filter, sort, projection, limit, collation, read preference và phiên bản server. Cần biết có dùng skip hoặc xử lý mảng không.

**Bước 2 — Thu thập explain("executionStats").** Xem winning plan, các stage, indexBounds, totalKeysExamined, totalDocsExamined và nReturned.

**Bước 3 — Đặt giả thuyết từ plan.**

- Nếu **COLLSCAN** trên collection lớn và filter rất chọn lọc → có thể thiếu index.
- Nếu **IXSCAN + FETCH** với nhiều document bị loại sau FETCH → filter chưa đủ được hỗ trợ trong index.
- Nếu **IXSCAN + SORT** với tập đầu vào lớn → index chưa giúp sort.
- Nếu **IXSCAN không FETCH** nhưng quét quá nhiều key → index bounds có thể chưa chọn lọc, hoặc cấu trúc mảng gây fan-out.

**Bước 4 — Đề xuất index ứng viên** dựa trên trường equality, sort, range và những query dùng chung collection. Đừng chọn index chỉ cho một query mà không xem tác động đến write workload.

**Bước 5 — So sánh bằng hint trong lab/staging.** Buộc dùng hai index để hiểu khác biệt ở các stage; sau đó bỏ hint và kiểm tra planner tự chọn gì. Hint trong production chỉ nên dùng khi có lý do vận hành đã được xác minh.

**Bước 6 — Đo latency và tải đại diện.** Tạo index không phải thành công nếu query nhanh hơn vài ms nhưng insert/update chậm quá mức hoặc index tăng dung lượng cache đáng kể.

**Bước 7 — Triển khai có giám sát.** Kiểm tra các query khác, phản ứng khi workload đổi, loại index chồng lấn không cần thiết sau khi có bằng chứng và chiến lược khôi phục.

### 13.1. Ví dụ index phục vụ hàng đợi pending

Query:

~~~javascript
db.orders.find({
  dataset: "plan-stages-v1",
  tenantId: "tA",
  status: "pending"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Index phù hợp với lab:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

Tuy nhiên, nếu một trang khác cần **tất cả trạng thái** sort theo createdAt, index có status trước createdAt sẽ không mặc nhiên cung cấp được thứ tự chung; có thể cần index khác. **Một query plan tốt phải được xem trong bối cảnh cả bộ access patterns.**

### 13.2. Index và sort với pagination

Phân trang bằng:

~~~javascript
.skip(100000).limit(20)
~~~

có thể khiến MongoDB phải duyệt nhiều bản ghi trước khi lấy trang. Một index hỗ trợ sort sẽ giúp tránh SORT blocking, nhưng **không loại chi phí bỏ qua 100.000 kết quả**. Khi phân trang sâu thường xuyên, keyset/cursor pagination theo (createdAt, _id) có thể phù hợp hơn.

Trong explain, hãy xem số key được duyệt so với chỉ 20 document cuối cùng được trả; hiểu được sự chênh lệch này thường quan trọng hơn chỉ tìm stage SORT.

## 14. Các sai lầm thường gặp khi đọc plan

| Sai lầm | Vì sao chưa đúng? | Cách đọc phù hợp |
| --- | --- | --- |
| Thấy COLLSCAN là phải thêm index | Collection nhỏ hoặc query đọc phần lớn dữ liệu có thể COLLSCAN hợp lý | Xem totalDocsExamined, nReturned, latency và tải |
| Thấy IXSCAN là chắc chắn nhanh | Có thể quét rất nhiều key hoặc FETCH nhiều document | Đọc indexBounds, totalKeysExamined và totalDocsExamined |
| Thấy FETCH là index vô ích | FETCH có thể chỉ lấy vài document để trả field không có trong index | Xem số document FETCH, projection và SLA |
| Không thấy FETCH nghĩa query tốt tuyệt đối | Covered query vẫn có thể scan lượng key rất lớn | So sánh keysExamined với nReturned |
| Có SORT nghĩa thiếu index | Một SORT nhỏ có thể rẻ hơn index bổ sung | Đo đầu vào SORT và tần suất query |
| Limit(10) nghĩa chỉ đọc 10 document | Filter/sort/skip có thể cần xét nhiều ứng viên | Đọc số examinded của các stage |
| Sort xuất hiện trong query nên nhất định có SORT stage | Index có thể cung cấp thứ tự sẵn | Xem compound index và winning plan |
| Index tồn tại nghĩa MongoDB sẽ dùng | Planner có thể chọn COLLSCAN hoặc index khác | Xem winningPlan, có thể thử hint để đối chiếu |
| Hiệu năng đo bằng một lần explain | Explain không thay benchmark và workload production | Kết hợp p95/p99 app, profiler và metrics server |
| Không thấy stage ở đường dẫn JSON quen thuộc | Classic/SBE/aggregation/sharding có cách trình bày khác | Đọc cây thực tế và nhánh queryPlan/slotBasedPlan |
| totalDocsExamined phải luôn bằng nReturned | Nhiều document ứng viên bị filter loại sau khi đọc | Kiểm tra stage filter và index bounds |
| totalKeysExamined phải bằng totalDocsExamined | Multikey, index-only query và scan/filter tạo quan hệ khác | Hiểu index key, FETCH và projection |
| Hễ có hint là plan tối ưu | Hint có thể ép index kém hoặc lỗi nếu index không có | Dùng trong thí nghiệm có so sánh, bỏ khi không cần |
| Query trả đúng thì plan ổn | Query đúng có thể đọc/sort khối dữ liệu rất lớn | Kết hợp correctness và execution metrics |
| Cùng query shape luôn một plan | Dữ liệu, index, plan cache và phiên bản có thể đổi | Theo dõi regression và cập nhật đo đạc |

## 15. Bài tập thực hành

### Bài 1 — Đọc cây stage

Cho sơ đồ:

~~~text
PROJECTION_SIMPLE
   |
   +-- FETCH
         |
         +-- IXSCAN
~~~

Hãy trình bày thứ tự dữ liệu đi từ index đến kết quả. Vì sao có FETCH, và phải thay đổi gì về projection/index để một số truy vấn có thể được cover?

### Bài 2 — So sánh COLLSCAN và IXSCAN

Từ lab, tìm các đơn pending của tenant tA. Lần đầu ép **hint({$natural:1})**, lần hai ép **ix_tenant_status_created**. Ghi lại winning plan, nReturned, totalDocsExamined và totalKeysExamined. Giải thích sự khác biệt mà không lấy thời gian từ 36 document làm kết luận production.

### Bài 3 — Projection và FETCH

Chạy cùng filter tenant/status với hai projection:

~~~javascript
{ _id: 0, status: 1, createdAt: 1 }

{ _id: 0, status: 1, createdAt: 1, lines: 1 }
~~~

Dùng hint **ix_tenant_status_created**. Dự đoán cái nào có khả năng cover, cái nào phải FETCH, sau đó so sánh explain và totalDocsExamined.

### Bài 4 — SORT với index không đúng thứ tự

Lọc tenant tA rồi sort total giảm dần, limit 5. So sánh plan khi hint **ix_tenant_created** và **ix_tenant_total**. Vì sao cả hai index có thể giúp filter nhưng chỉ một index cung cấp thứ tự sort phù hợp?

### Bài 5 — Điều kiện ở FETCH

Lọc tenant/status/note = manual-review với index **ix_tenant_status_created**. Note có trong index không? Đo số document được xét. Nếu query chạy hàng trăm lần mỗi giây, bạn sẽ cân nhắc index nào và phải đo điều gì trước khi thêm index?

### Bài 6 — Compound index có field trung gian

Index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Query A lọc tenant/status và sort createdAt; query B chỉ lọc tenant nhưng sort createdAt. Giải thích vì sao query B có thể cần SORT nếu ép index trên. Đề xuất index thích hợp khi query B là màn hình nóng.

### Bài 7 — Tỷ lệ quét

Ba query có số liệu minh họa:

| Query | nReturned | totalKeysExamined | totalDocsExamined |
| --- | ---: | ---: | ---: |
| A | 20 | 20 | 20 |
| B | 20 | 100000 | 20000 |
| C | 1 | 1000000 | 0 |

Với mỗi query, hãy tính keysExamined/nReturned và docsExamined/nReturned, đề xuất bước điều tra tiếp theo. Vì sao C có thể không FETCH document nhưng vẫn đắt?

### Bài 8 — Plan khác cấu trúc do SBE

So sánh hai ví dụ giả định: một explain có **winningPlan.stage = "FETCH"** và **inputStage.stage = "IXSCAN"**, một explain có **winningPlan.queryPlan** cùng nhánh **slotBasedPlan**. Hãy chỉ ra cách xác định cùng nội dung “đọc index và có thể lấy document” mà không phụ thuộc duy nhất vào một đường dẫn JSON.

### Bài 9 — Aggregation và sharding

Giả sử aggregation dùng $match, $sort, $group trên collection sharded. Hãy phân biệt plan của từng shard với giai đoạn merge. Vì sao chỉ xem một IXSCAN trên một shard chưa đủ kết luận toàn query nhanh?

### Bài 10 — Quy trình xử lý query chậm

Một API list đơn theo tenant/status có p95 = 2 giây, nReturned = 20 nhưng totalDocsExamined = 100.000 và stage SORT trên một tập lớn. Hãy lập kế hoạch: thu thập query shape, kiểm tra index bounds/filter, thiết kế compound index, đo trên staging, so sánh hint và thực hiện rollout có giám sát.

## 16. Tài liệu tham khảo MongoDB

- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [cursor.explain()](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/).
- MongoDB Manual — [Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/).
- MongoDB Manual — [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/).
- MongoDB Manual — [The ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/).
- MongoDB Manual — [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/).
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/).

**Kết luận:** **COLLSCAN** cho biết MongoDB đang duyệt collection; **IXSCAN** cho biết nó đang duyệt key của index; **FETCH** cho biết cần đọc document gốc hoặc kiểm tra thêm điều kiện; **SORT** cho biết dữ liệu cần được sắp xếp ở một bước riêng khi không có thứ tự phù hợp từ index. Nhưng tên stage chỉ là điểm bắt đầu. Muốn đánh giá một truy vấn, hãy kết hợp **indexBounds, totalKeysExamined, totalDocsExamined, nReturned, projection, sort và ngữ cảnh workload**. Khi đọc explain như một cây công việc thay vì chỉ tìm chữ IXSCAN, bạn có thể chọn index và điều chỉnh truy vấn dựa trên bằng chứng thay vì suy đoán.
