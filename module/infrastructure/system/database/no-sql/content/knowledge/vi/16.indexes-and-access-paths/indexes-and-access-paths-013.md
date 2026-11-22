# Kiểm chứng chỉ mục bằng độ trễ và số bản ghi/byte được đọc

Một truy vấn NoSQL trả về 20 đơn hàng không có nghĩa nó chỉ đọc 20 bản ghi. Nếu hệ thống phải quét hàng trăm nghìn đơn, lọc theo cửa hàng và trạng thái, sắp xếp kết quả rồi mới lấy 20 dòng đầu, truy vấn vẫn có thể chậm và tốn nhiều CPU, bộ nhớ, I/O. Khi dữ liệu còn nhỏ, cách viết này có thể chạy nhanh trong môi trường phát triển; khi số lượng tăng và nhiều người dùng truy cập đồng thời, độ trễ sẽ bộc lộ.

Vì vậy, không nên kết luận **“đã tối ưu bằng chỉ mục”** chỉ vì câu lệnh tạo index thành công hoặc kế hoạch thực thi xuất hiện chữ `IXSCAN`. Một chỉ mục cần được **kiểm chứng bằng số liệu trước và sau thay đổi**:

- **Độ trễ:** Người dùng chờ bao lâu, nhất là p95/p99 khi có tải đồng thời?
- **Số bản ghi và khóa đã xét:** Engine phải xem bao nhiêu document, row, item hoặc index entry để trả kết quả?
- **Số byte được đọc/truyền:** Dữ liệu logic, đĩa, cache, network và phản hồi phát sinh bao nhiêu?
- **Tính đúng:** Truy vấn có trả đủ kết quả, đúng bộ lọc, thứ tự và quyền truy cập không?
- **Chi phí duy trì:** Index làm tăng dung lượng, ghi dữ liệu, RAM, compaction hay thời gian build bao nhiêu?

Bài học giải thích một phương pháp đánh giá có thể áp dụng cho **MongoDB, Cassandra/ScyllaDB, DynamoDB, Redis, Elasticsearch/OpenSearch, Neo4j** và chỉ mục vector. Các hệ không cung cấp những metric cùng tên hay cùng ngữ nghĩa; cần hiểu **phạm vi của từng bộ đếm** trước khi so sánh.

## 1. Bài toán xuyên suốt: 20 đơn cần giao mới nhất

Giả sử một nền tảng bán hàng đa tenant lưu:

~~~json
{
  "tenantId": "merchant-a",
  "orderId": "O900",
  "shopId": "shop-12",
  "status": "READY_TO_SHIP",
  "createdAt": "2026-11-14T09:30:00.000Z",
  "customerId": "U42",
  "totalVnd": 1000000
}
~~~

Màn hình điều phối yêu cầu:

> **Q1:** Lấy tối đa 20 đơn `READY_TO_SHIP` thuộc `merchant-a` và `shop-12`, được tạo trong bảy ngày gần nhất, sắp theo `createdAt DESC`; khi trùng thời điểm, sắp theo `orderId ASC`.

Hợp đồng truy vấn:

| Thuộc tính | Quy định minh họa |
| --- | --- |
| Tenant và shop | Lấy từ ngữ cảnh đã xác thực, kiểm tra quyền |
| Điều kiện | `tenantId`, `shopId`, `status`, khoảng `createdAt` |
| Khoảng thời gian | `[now - 7 ngày, now)`, dùng UTC instant |
| Sort | `createdAt DESC, orderId ASC` |
| Trang | 20 đơn, cursor ổn định |
| Mục tiêu | API p95 không quá 150 ms ở tải dự kiến |
| Độ mới | Theo consistency/freshness được sản phẩm chấp nhận |

SLA và dữ liệu trong bài chỉ là **giả định để học**, không phải benchmark đã chạy hoặc cam kết của một sản phẩm.

### 1.1. Đáp án đúng trước khi đo hiệu năng

| ID | shop | status | createdAt UTC | Có thuộc Q1? |
| --- | --- | --- | --- | --- |
| O900 | shop-12 | READY_TO_SHIP | 14/11 09:30 | Có |
| O899 | shop-12 | SHIPPED | 14/11 09:29 | Không |
| O898 | shop-21 | READY_TO_SHIP | 14/11 09:28 | Không |
| O897 | shop-12 | READY_TO_SHIP | 14/11 09:27 | Có |
| O896 | shop-12 | READY_TO_SHIP | 01/11 10:00 | Không, ngoài khoảng |

Một chỉ mục trả nhanh nhưng bỏ sót O897 hoặc trả O899 vẫn là **đường truy cập sai**. Khi so trước/sau phải kiểm tra tập ID và thứ tự trên dữ liệu hoặc snapshot tương đương, không cắt bớt điều kiện khó để làm truy vấn nhanh giả.

### 1.2. Quy mô giả định

~~~text
Toàn hệ thống:                  10.000.000 đơn
Tenant merchant-a:                800.000 đơn
Shop shop-12:                     120.000 đơn
Shop-12 đang READY trong 7 ngày:    3.500 đơn
Q1 cần trả:                            20 đơn
~~~

Nếu phải xét 800.000 đơn để trả 20 kết quả, mức khuếch đại đọc rất cao. Với index theo `tenantId, shopId, status, createdAt` đã cung cấp thứ tự mong muốn, engine có thể chỉ cần xem một nhóm nhỏ ứng viên rồi dừng. **Có thực sự như vậy không phải đo từ kế hoạch và counters của truy vấn.**

## 2. Chỉ mục là đường truy cập, không phải lời bảo đảm

**Index** lưu một cấu trúc giúp định vị dữ liệu theo các khóa hoặc thuộc tính mà không phải đọc tất cả bản ghi. Trong các hệ NoSQL, đường truy cập có nhiều dạng:

| Cấu trúc | Ví dụ | Trường hợp phù hợp |
| --- | --- | --- |
| Primary key | `(tenantId, orderId)` | Lấy chính xác một đơn |
| Compound secondary index | `(tenantId, shopId, status, createdAt)` | Lọc nhiều trường, sort theo index |
| Partition + clustering | `(shopId, dayBucket)`, `createdAt DESC` | Đọc các hàng có thứ tự trong partition |
| GSI / alternate key | DynamoDB GSI theo shop/status | Truy cập item bằng khóa khác |
| Inverted index | Term → document IDs | Tìm kiếm từ khóa, filter |
| Graph property index | Node theo ID/thuộc tính | Tìm node bắt đầu trước khi duyệt cạnh |
| Vector ANN index | HNSW/IVF/PQ | Tìm vector gần đúng |
| Sorted set | Redis ZSET theo thời gian | Lấy thành viên theo score/rank |

Index có thể giúp **lọc sớm**, **tránh sort lại**, **chỉ đọc những field cần thiết** (*covering index*) hoặc **giảm số partition cần chạm**. Nhưng index cũng có thể:

- Không được query planner chọn.
- Chỉ lọc một phần rồi vẫn phải fetch hàng nghìn document.
- Không phục vụ được sort vì thứ tự khóa không phù hợp.
- Phải duyệt nhiều index entries cho ít kết quả.
- Có kích thước lớn hơn RAM và làm tăng cache miss.
- Tốn nhiều ghi khi thêm, sửa, xóa dữ liệu.

~~~mermaid
flowchart TD
    Q["Q1: 20 đơn READY mới nhất"] --> A["A. Scan -> filter -> sort -> limit"]
    Q --> B["B. Index một phần -> fetch -> sort -> limit"]
    Q --> C["C. Index đúng filter + order -> fetch top 20"]
    A --> X["Đo số hàng, byte và latency"]
    B --> X
    C --> X
~~~

Đường C có triển vọng nhất cho Q1 nhưng **không được tự gán là tốt nhất nếu chưa đo**.

## 3. Phân biệt các lớp đo lường

### 3.1. Độ trễ của database, driver và API

Một request đi qua:

~~~text
HTTP request
  -> authentication / authorization
  -> connection pool
  -> network tới database
  -> planner / index / data fetch / sort
  -> network và driver decoding
  -> application processing / serialization
  -> HTTP response
~~~

Nên phân biệt:

- **Database execution time:** Thời gian engine xử lý theo công cụ đo của nó.
- **Driver latency:** Thời gian client/driver chờ và nhận đủ dữ liệu truy vấn.
- **API end-to-end latency:** Thời gian từ lúc nhận request tới lúc hoàn tất response, gồm xác thực và nghiệp vụ phụ.

Một `executionTimeMillis = 8` từ một lần explain **không chứng minh** API có p95 = 8 ms. Nếu API vẫn gọi 30 truy vấn bổ sung sau đó (*N+1 reads*), điểm nghẽn có thể không nằm ở index của Q1.

### 3.2. p50, p95 và p99

| Metric | Diễn giải | Ứng dụng |
| --- | --- | --- |
| Mean | Trung bình cộng | Tóm tắt, nhưng dễ che request cực chậm |
| p50 | Độ trễ trung vị | Request điển hình |
| p95 | 95% request không vượt mốc này theo mẫu | Phổ biến trong SLO API |
| p99 | Phần đuôi chậm, gần nhóm 1% cuối | Nhìn cache miss, I/O, tranh chấp |
| Error/timeout | Request không hoàn tất | Không được loại khỏi phân tích |
| QPS | Query thành công mỗi giây | Phải xem cùng latency và concurrency |

Nếu một index cải thiện p50 nhưng làm p99 tăng gấp đôi khi nhiều client truy cập, chưa thể kết luận thiết kế mới tốt hơn. Không được bỏ những request timeout để số p95 trông đẹp.

### 3.3. Bản ghi được xét khác kết quả trả về

Ví dụ:

~~~text
documentsExamined = 320000
nReturned         = 20
~~~

Engine đã xem 320.000 document để trả 20 document. Tỷ lệ mô tả:

\[
A_{\mathrm{docs}}=\frac{\mathrm{documentsExamined}}{\mathrm{nReturned}}
\]

Trong ví dụ, `A_docs = 16000`: cần xét 16.000 document cho một kết quả được trả.

Tỷ lệ này không phải chỉ số chung cho mọi hệ. Nếu kết quả trả về bằng 0, **không được chia cho 0**; hãy báo số candidate đã xét riêng. Nếu query được **cover bởi index**, số document phải fetch có thể bằng 0, nhưng engine vẫn phải duyệt index entries.

### 3.4. Keys examined là một metric khác

Một plan có thể:

~~~text
keysExamined = 50000
docsExamined = 20
nReturned    = 20
~~~

Điều này cho biết index đã giảm nhu cầu đọc document nhưng vẫn phải xét **50.000 index entries**. Nguyên nhân có thể là index chỉ lọc một phần, range rộng, multikey hoặc điều kiện còn lại không được index xử lý.

Chỉ nhìn `docsExamined` thấp rồi tuyên bố ít công việc là thiếu căn cứ. Cần xem cả **keys examined, bounds, sort, fetch và số kết quả**.

### 3.5. Byte đọc không giống byte trả về

| Đại lượng | Ý nghĩa |
| --- | --- |
| Logical bytes examined | Dung lượng dữ liệu logic mà query phải xét |
| Physical disk bytes read | Byte được đọc thực tế từ storage trong khoảng đo |
| Cache/buffer pages | Dữ liệu được phục vụ từ RAM hoặc cache |
| Index bytes touched | Dữ liệu index được truy cập |
| Database network bytes | Byte truyền giữa DB và ứng dụng |
| API response bytes | Byte trả tới người dùng |

Một truy vấn quét 100.000 document đã **nằm trong cache** có thể có physical disk reads thấp nhưng vẫn dùng CPU và băng thông RAM lớn. Truy vấn trả 20 document mỗi cái 1 MiB cũng có thể tiêu tốn network lớn dù `docsExamined = 20`.

**Không lấy `docsExamined × documentSize` rồi khẳng định đó là số byte SSD thực sự đọc.** Đó mới là ước tính dữ liệu logic; engine còn có nén, page I/O, index, cache và thuật toán thực thi riêng.

## 4. Read amplification, selectivity và cost per result

Với kết quả khác rỗng:

\[
\text{Document amplification}
=\frac{\text{documents examined}}{\text{documents returned}}
\]

\[
\text{Index-key amplification}
=\frac{\text{index entries examined}}{\text{results returned}}
\]

Nếu có bộ đếm byte cùng tầng:

\[
\text{Byte amplification}
=\frac{\text{bytes read at a defined layer}}{\text{bytes returned at that layer}}
\]

Giả sử query đọc 40 MiB dữ liệu logic và trả 8 KiB dữ liệu logic:

\[
\text{logical-byte amplification}
=\frac{40\times1024}{8}=5120
\]

Đây là **tỷ lệ dữ liệu logic**, không phải tỷ lệ physical disk I/O.

### 4.1. Selectivity

Giả sử một tenant có 500.000 đơn và 5.000 đơn khớp điều kiện:

\[
\text{selectivity}=5000/500000=1\%
\]

Chỉ mục trên một cờ boolean có hai giá trị có thể không giảm dữ liệu nhiều khi đứng riêng. Compound index kết hợp tenant/shop/status/time có thể phù hợp hơn với query Q1.

Tuy nhiên selectivity thay đổi theo tenant, shop và thời gian. Một index tốt với shop nhỏ chưa chắc tốt với shop có vài triệu đơn.

### 4.2. Các phép tổng hợp là ngoại lệ cần giải thích

Một query `COUNT(*)` chính xác trả **một con số**, nhưng có thể phải duyệt hàng triệu dòng. Khi đó ratio `examined/returned` rất lớn **không đủ chứng minh truy vấn bị tối ưu sai**; cần xác định engine có summary/count index phù hợp hay nên pre-aggregate.

Tương tự, export toàn bộ dữ liệu có mục tiêu throughput byte/giây chứ không chỉ latency một trang.

## 5. Quy trình đo trước và sau thay đổi

Một thí nghiệm có kiểm soát:

~~~mermaid
flowchart TD
    A["Chốt contract và dataset"] --> B["Đo baseline chưa có index phù hợp"]
    B --> C["Lưu plan, counters, latency"]
    C --> D["Tạo index hoặc đổi access path"]
    D --> E["Xác nhận index sẵn sàng"]
    E --> F["Chạy lại cùng query / tải / dữ liệu"]
    F --> G["So kết quả và chi phí"]
    G --> H{"Đạt SLA, đúng dữ liệu, chi phí phù hợp?"}
    H -->|Có| I["Canary và giám sát"]
    H -->|Không| J["Điều chỉnh và đo lại"]
~~~

Thực hiện:

1. **Chốt hợp đồng truy vấn:** filter, sort, projection, limit, timezone, consistency, quyền truy cập.
2. **Chọn dữ liệu đại diện:** tenant nhỏ/lớn, ngày có tải cao, trạng thái hiếm/phổ biến, nhiều bản ghi trùng thời gian.
3. **Đo baseline:** explain/tracing, p50/p95/p99, key/row/byte, throughput và error rate.
4. **Thay đúng một biến chính:** tạo index hoặc access path, ghi thông tin môi trường và schema.
5. **Chờ index xây xong:** không đo một kế hoạch chưa sẵn sàng rồi coi là steady state.
6. **Chạy lại workload tương đương:** cùng dataset/snapshot, query, cache state được ghi rõ và concurrency.
7. **Kiểm chứng kết quả:** cùng ID, thứ tự, phân trang, dữ liệu được phép và độ mới.
8. **Đo chi phí ghi và lưu trữ:** index size, RAM, build time, write amplification.
9. **Quyết định theo SLO đã đặt:** không chọn chỉ vì một lần chạy trông nhanh.

### 5.1. Vì sao một thay đổi có thể làm kết luận sai?

Nếu cùng lúc tăng RAM, đổi connection pool, thay cache, nâng phiên bản DB và tạo index, ta khó biết cải thiện đến từ đâu. Khi cần thay nhiều thứ, đo từng giai đoạn và giữ **thông tin cấu hình**.

### 5.2. Kết quả trên tập nhỏ không đại diện tập lớn

Với 500 document, collection scan có thể nhanh hơn đi qua index do mọi dữ liệu đều vừa RAM. Với 50 triệu document, cùng kế hoạch có thể trở thành nút thắt. **Mục tiêu không phải ép planner luôn dùng index; mục tiêu là đạt SLA ở quy mô thực.**

## 6. MongoDB: kiểm chứng bằng explain và executionStats

MongoDB hỗ trợ `explain("executionStats")` để quan sát:

- `nReturned`: số document được trả trong kế hoạch tương ứng.
- `totalKeysExamined`: số index key đã được xét.
- `totalDocsExamined`: số document đã được xét.
- `executionTimeMillis`: thời gian được ghi nhận cho một lần explain, **không phải API p95**.
- `queryPlanner.winningPlan`: kế hoạch được chọn, với các dạng operator như `COLLSCAN`, `IXSCAN`, `FETCH`, `SORT` hoặc tên khác theo phiên bản và execution engine.

Đường dẫn JSON của từng stage có thể thay đổi giữa các phiên bản/engine; **không viết kết luận chỉ bằng cách tìm một chuỗi stage**.

### 6.1. Query ban đầu

Document mẫu MongoDB:

~~~javascript
{
  tenantId: "merchant-a",
  shopId: "shop-12",
  status: "READY_TO_SHIP",
  createdAt: ISODate("2026-11-14T09:30:00Z"),
  orderId: "O900",
  customerId: "U42",
  totalVnd: NumberLong("1000000")
}
~~~

Query Q1 trong mongosh:

~~~javascript
const from = ISODate("2026-11-07T12:00:00.000Z");
const to = ISODate("2026-11-14T12:00:00.000Z");

const filter = {
  tenantId: "merchant-a",
  shopId: "shop-12",
  status: "READY_TO_SHIP",
  createdAt: { $gte: from, $lt: to }
};

const projection = {
  _id: 0,
  orderId: 1,
  createdAt: 1,
  customerId: 1,
  totalVnd: 1
};

db.orders.find(filter, projection)
  .sort({ createdAt: -1, orderId: 1 })
  .limit(20)
  .explain("executionStats");
~~~

Trước khi có index phù hợp, planner có thể phải quét lớn hoặc dùng index ít chọn lọc rồi sort. Một ví dụ **giả lập**:

~~~text
nReturned           = 20
totalKeysExamined   = 0
totalDocsExamined   = 800000
plan                = COLLSCAN + SORT/LIMIT
executionTimeMillis = 640
~~~

Các con số trên **không được đo thật** và không có nghĩa mọi MongoDB đều chọn COLLSCAN trong tình huống ấy.

### 6.2. Tạo compound index phù hợp

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    shopId: 1,
    status: 1,
    createdAt: -1,
    orderId: 1
  },
  { name: "idx_shop_ready_time" }
);
~~~

Lý do:

- `tenantId`, `shopId`, `status`: equality filters.
- `createdAt`: vừa là range vừa là sort giảm dần.
- `orderId`: tie-breaker tăng dần khi timestamp bằng nhau.

Với các trường equality ở tiền tố index, phần còn lại có thể hỗ trợ đọc theo đúng thứ tự mà Q1 cần. **Thứ tự tối ưu còn phụ thuộc workload**, đặc biệt khi có những query khác muốn dùng chung index.

Chạy lại nguyên câu lệnh explain. Một kết quả **giả lập** sau khi index được dùng đúng:

~~~text
nReturned           = 20
totalKeysExamined   = 23
totalDocsExamined   = 20
plan                = IXSCAN -> FETCH -> LIMIT
executionTimeMillis = 8
~~~

So về document examination ratio:

~~~text
Trước = 800000 / 20 = 40000
Sau   =     20 / 20 =     1
~~~

Số document được xét giảm mạnh, nhưng không được suy ra **API p95 = 8 ms** từ một lần explain.

### 6.3. Chỉ thấy IXSCAN vẫn chưa đủ

Giả sử index chỉ có:

~~~javascript
{ tenantId: 1, status: 1 }
~~~

Nó có thể định vị các đơn READY trong một tenant, nhưng chưa hỗ trợ tốt `shopId`, `createdAt` và thứ tự sort:

~~~text
totalKeysExamined = 100000
totalDocsExamined = 100000
nReturned         = 20
~~~

Một plan có `IXSCAN` nhưng vẫn phải xét 100.000 key/document chưa chắc tốt hơn phương án khác. Hãy xem **index bounds**, filter còn lại, `FETCH` và operator sort.

### 6.4. Sort và limit

Nếu index không cung cấp đúng thứ tự, query có thể phải xét nhiều bản ghi, sắp xếp rồi mới `LIMIT 20`. **Giới hạn kết quả sau sort không giới hạn số bản ghi cần xem trước sort**.

Một compound index không tự đáp ứng sort khi:

- Tiền tố trước sort không bị ràng buộc bằng điều kiện phù hợp.
- Chiều hoặc thứ tự khóa không tương thích.
- Điều kiện range/multikey tạo kế hoạch khác.
- Planner chọn chiến lược khác vì chi phí thực tế.

Khi so trước/sau, kiểm tra có còn sort tốn bộ nhớ hoặc spill không và bao nhiêu đầu vào đã được xét.

### 6.5. Covered query

Nếu projection chỉ chứa những trường tương thích có trong index, MongoDB có thể trả từ index mà không phải fetch document nguồn. Khi đó `totalDocsExamined` có thể bằng 0 nhưng `totalKeysExamined` vẫn dương.

Q1 còn cần `customerId` và `totalVnd`, nên query thường phải fetch document vì hai field này không nằm trong index trên. Thêm chúng vào index để covering có thể giảm I/O nhưng sẽ **tăng index size và write amplification**.

Chỉ nên mở rộng index sau khi đo lợi ích lên p95, cache và chi phí ghi.

### 6.6. Kích thước và mức dùng index

Trong mongosh:

~~~javascript
db.orders.getIndexes();
db.orders.stats().indexSizes;
db.orders.aggregate([{ $indexStats: {} }]);
~~~

`getIndexes()` cho biết định nghĩa index; `indexSizes` cho dung lượng theo thống kê engine; `$indexStats` cung cấp thông tin sử dụng trong cửa sổ đo. Không coi index ít được dùng là chắc chắn thừa nếu workload hoặc khoảng quan sát chưa đại diện.

Đồng thời đo **insert/update/delete latency**, storage và cache pressure sau khi tạo index; tối ưu một API hiếm dùng không nhất thiết đáng đổi chi phí ghi của mọi document.

## 7. Đo latency phía client với Python/PyMongo

Explain giúp biết **engine làm gì**; benchmark giúp biết **client mất bao lâu để lấy và giải mã kết quả**.

~~~bash
python -m pip install pymongo
~~~

Ví dụ file `bench_orders.py`:

~~~python
import os
import time
import statistics
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING, DESCENDING

client = MongoClient(os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017"))
collection = client["nosql_lab"]["orders"]

condition = {
    "tenantId": "merchant-a",
    "shopId": "shop-12",
    "status": "READY_TO_SHIP",
    "createdAt": {
        "$gte": datetime(2026, 11, 7, 12, tzinfo=timezone.utc),
        "$lt": datetime(2026, 11, 14, 12, tzinfo=timezone.utc),
    },
}
projection = {
    "_id": 0, "orderId": 1, "createdAt": 1,
    "customerId": 1, "totalVnd": 1,
}


def fetch_page():
    cursor = (
        collection.find(condition, projection)
        .sort([("createdAt", DESCENDING), ("orderId", ASCENDING)])
        .limit(20)
    )
    return list(cursor)  # Buộc đọc toàn bộ trang, không chỉ tạo cursor.


def nearest_rank(values_sorted, percentile):
    import math
    rank = math.ceil(percentile / 100.0 * len(values_sorted))
    return values_sorted[max(0, rank - 1)]


for _ in range(30):
    fetch_page()  # Warm up: connection, cache, thư viện.

durations_ms = []
returned_counts = []
for _ in range(300):
    start = time.perf_counter_ns()
    result = fetch_page()
    durations_ms.append((time.perf_counter_ns() - start) / 1_000_000)
    returned_counts.append(len(result))

ordered = sorted(durations_ms)
print("samples:", len(ordered))
print("returned min/max:", min(returned_counts), max(returned_counts))
print("mean ms:", round(statistics.mean(ordered), 3))
print("p50 ms:", round(nearest_rank(ordered, 50), 3))
print("p95 ms:", round(nearest_rank(ordered, 95), 3))
print("p99 ms:", round(nearest_rank(ordered, 99), 3))
~~~

Để so trước/sau, chạy cùng script trên cùng dữ liệu và query, ghi environment, index setup và tải. Không chạy `explain` bên trong mỗi lượt benchmark. Đoạn mã trên **không tạo dữ liệu** và chỉ mô phỏng **một client chạy tuần tự**, không đo API HTTP hay network bytes riêng; với quyết định production cần chạy lâu hơn, nhiều client, ghi timeout và độ trễ dưới concurrency.

Sử dụng `time.perf_counter_ns()` để đo **elapsed time**, không dùng `datetime.now()` rồi trừ nếu wall clock có thể bị điều chỉnh.

## 8. Cassandra/ScyllaDB: partition, rows và tombstones

Wide-column store tối ưu khi query biết **partition key** và có thể duyệt **clustering order**. Không có một bộ `totalDocsExamined` phổ quát giống MongoDB cho mọi đường đọc.

### 8.1. Bảng theo orderId không phục vụ Q1

~~~sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id text,
    shop_id text,
    status text,
    created_at timestamp,
    total_vnd bigint,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Q1 không biết trước `order_id`. Điều kiện `shop_id` và `status` không tạo được đường đọc theo khóa chính này. Thêm `ALLOW FILTERING` không tự xây index và có thể dẫn tới xét lượng dữ liệu rất lớn.

### 8.2. Bảng đọc đúng query

~~~sql
CREATE TABLE orders_by_shop_status_day (
    tenant_id text,
    shop_id text,
    status text,
    day_utc date,
    created_at timestamp,
    order_id text,
    customer_id text,
    total_vnd bigint,
    PRIMARY KEY (
        (tenant_id, shop_id, status, day_utc),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Một truy vấn:

~~~sql
SELECT created_at, order_id, customer_id, total_vnd
FROM orders_by_shop_status_day
WHERE tenant_id = 'merchant-a'
  AND shop_id = 'shop-12'
  AND status = 'READY_TO_SHIP'
  AND day_utc = '2026-11-14'
LIMIT 20;
~~~

định vị **một partition** và có sẵn thứ tự trong partition. So với quét toàn tenant, đường đọc này thường hợp lý hơn cho Q1. Nhưng **một partition ngày không phải toàn bộ bảy ngày**.

### 8.3. Truy vấn xuyên ngày

API phải:

1. Tính các ngày UTC giao với cửa sổ bảy ngày.
2. Đọc partition của ngày mới trước, hoặc fan-out có kiểm soát.
3. Ở ranh giới, lọc đúng `[from, to)`.
4. Merge theo `createdAt DESC, orderId ASC`.
5. Dừng khi đủ 20 kết quả hợp lệ hoặc hết khoảng.

Bảy lần 24 giờ có thể giao **tám ngày lịch UTC**. Query nhanh trên một partition không bảo đảm tổng API nhanh sau nhiều round trip.

### 8.4. Cách quan sát Cassandra

Trong `cqlsh`, tùy phiên bản:

~~~sql
TRACING ON;

SELECT created_at, order_id
FROM orders_by_shop_status_day
WHERE tenant_id = 'merchant-a'
  AND shop_id = 'shop-12'
  AND status = 'READY_TO_SHIP'
  AND day_utc = '2026-11-14'
LIMIT 20;

TRACING OFF;
~~~

Theo dõi bằng tracing, driver telemetry và metrics của engine:

| Tín hiệu | Câu hỏi |
| --- | --- |
| Partitions/read | Có phải fan-out quá nhiều không? |
| Live rows read/returned | Có đang xét quá nhiều hàng sống không? |
| Tombstones scanned | Có phải đi qua nhiều dấu xóa không? |
| SSTables per read | Mỗi lần đọc chạm bao nhiêu tệp/bảng? |
| Read latency p95/p99 | Tail latency nằm ở coordinator/replica/driver? |
| Disk I/O / cache / network | Tầng nào tiêu thụ nhiều byte? |
| Compaction/repair | Việc nền có cạnh tranh tài nguyên với đọc không? |

Tên counter, cách gộp và mức chi tiết **khác nhau theo Cassandra/ScyllaDB và phiên bản**. Nếu không có counter bytes cụ thể, không được suy số physical bytes từ số row trả.

### 8.5. Tombstone làm LIMIT 20 vẫn chậm

Một đơn chuyển `READY_TO_SHIP -> SHIPPED` có thể được xóa khỏi bảng đọc theo trạng thái. Trong Cassandra, thao tác xóa tạo **tombstone**. Nếu nhiều đơn liên tục chuyển trạng thái, query `LIMIT 20` có thể phải xét nhiều tombstone trước khi tìm ra 20 row sống.

Khi tối ưu hãy đo tombstone, partition size, SSTables và read latency; cân nhắc bucket/compaction và mô hình dữ liệu. Không tùy tiện giảm thời gian bảo vệ tombstone hoặc bỏ quy trình repair chỉ để tăng tốc, vì ảnh hưởng an toàn dữ liệu ở replica.

### 8.6. Secondary index/SAI không tự bằng primary-key lookup

Những phiên bản phù hợp có thể hỗ trợ secondary index hoặc **Storage-Attached Index (SAI)**. Cần kiểm tra:

- Field/toán tử được hỗ trợ.
- Selectivity, phân bố key và số partition phải chạm.
- Có cần fetch row sau khi chọn ứng viên?
- Có cung cấp thứ tự toàn cục cho Q1 hay phải sort/merge?
- Chi phí cập nhật/index build và độ trễ khi nhiều ghi?

Không chỉ nhìn “query chạy được” rồi coi chỉ mục phụ tương đương đọc một partition đã sắp đúng.

## 9. DynamoDB: Count, ScannedCount, ConsumedCapacity và phân trang

DynamoDB có các counter khác MongoDB:

- **`ScannedCount`**: số item được đánh giá trước khi áp dụng FilterExpression trong phạm vi response.
- **`Count`**: số item được trả sau filter trong phạm vi response.
- **`ConsumedCapacity`**: capacity tiêu thụ nếu yêu cầu `ReturnConsumedCapacity`; không phải byte SSD đọc.
- **`LastEvaluatedKey`**: dấu hiệu có thể cần tiếp tục duyệt bằng `ExclusiveStartKey`.

### 9.1. Đường đọc theo key

Một thiết kế:

~~~text
PK = TENANT#merchant-a#SHOP#shop-12#READY#2026-11-14
SK = 2026-11-14T09:30:00.000Z#O900
~~~

Nếu chỉ những order READY có mặt trong đường này, Query theo PK trả các item tương ứng. `ScanIndexForward=False` cho sort key giảm dần. **Chú ý:** đảo thứ tự toàn bộ khóa `createdAt#orderId` cũng đảo phần orderId ở các timestamp bằng nhau; nó **không tự đáp ứng `orderId ASC`**. Phải có key encoding/merge và tie-breaker phù hợp hoặc điều chỉnh contract nếu hợp lệ.

### 9.2. Ví dụ boto3

~~~python
import boto3
from boto3.dynamodb.conditions import Key

table = boto3.resource("dynamodb").Table("OrdersReadModel")
pk = "TENANT#merchant-a#SHOP#shop-12#READY#2026-11-14"

response = table.query(
    KeyConditionExpression=Key("PK").eq(pk),
    ScanIndexForward=False,
    Limit=20,
    ReturnConsumedCapacity="TOTAL",
)

print(response["Count"])
print(response["ScannedCount"])
print(response.get("ConsumedCapacity"))
print("More pages:", "LastEvaluatedKey" in response)
~~~

Cần có AWS credentials, region và key schema tương ứng để chạy. Query trên **một partition/ngày** chưa giải quyết Q1 xuyên bảy ngày.

### 9.3. Key condition và filter khác nhau

Nếu status không nằm trong key, query có thể dùng:

~~~python
from boto3.dynamodb.conditions import Key, Attr

response = table.query(
    KeyConditionExpression=Key("PK").eq(
        "TENANT#merchant-a#SHOP#shop-12#2026-11-14"
    ),
    FilterExpression=Attr("status").eq("READY_TO_SHIP"),
    Limit=20,
    ReturnConsumedCapacity="TOTAL",
)
~~~

FilterExpression được áp **sau khi đọc/đánh giá item theo KeyCondition**. `Limit=20` giới hạn **số item được đánh giá** trong request theo quy tắc API, không bảo đảm 20 item còn lại sau lọc.

Ví dụ minh họa:

~~~text
ScannedCount = 20
Count = 2
LastEvaluatedKey = present
~~~

Ứng dụng có thể phải đọc nhiều trang mới đủ 20 đơn READY, kéo theo thêm RCU, network và round trips. Một request Query cũng có giới hạn kích thước dữ liệu xử lý theo trang (thường **tối đa 1 MB** trước pagination), nên không được suy ra một response là toàn bộ tập kết quả.

### 9.4. Cần cộng trên mọi trang

Muốn so công việc **để trả đủ 20 đơn hợp lệ**, hãy ghi:

~~~text
TotalCount = SUM(Count của các trang)
TotalScannedCount = SUM(ScannedCount của các trang)
TotalConsumedCapacity = SUM(ConsumedCapacity của các trang)
RoundTrips = số request Query thực hiện
EndToEndLatency = thời gian toàn đường đọc
~~~

Khi còn `LastEvaluatedKey`, request tiếp theo dùng `ExclusiveStartKey`. Không lấy chỉ trang đầu rồi so với một MongoDB query đã trả đủ kết quả.

### 9.5. RCU không phải physical disk bytes

Capacity DynamoDB phụ thuộc item size, kiểu đọc và consistency. Đọc eventual consistent, strong consistent hoặc transaction read có quy tắc capacity khác nhau; GSI còn có kích thước projected item riêng. FilterExpression không làm biến mất capacity của những item đã đọc để xét.

**Không quy đổi ConsumedCapacity thành số byte SSD vật lý**, vì DynamoDB không công bố API đó như một bộ đếm physical I/O trực tiếp. Để biết payload, đo network bytes; để hiểu capacity, dùng chỉ số DynamoDB theo đơn vị của dịch vụ.

Một `ProjectionExpression` chỉ trả các field cần thiết có thể giảm response payload, nhưng **không mặc định làm RCU giảm tương ứng** khi engine vẫn phải xét item nguồn.

### 9.6. GSI giúp định vị, không tự làm Query tổng quát rẻ

Một GSI theo `shop/status/time` có thể giảm ScannedCount nếu status là điều kiện key thay vì filter sau đọc. Nhưng GSI thêm chi phí storage/write, có đặc tính consistency và projection riêng. Nếu Q1 thường xuyên, cần benchmark **cả query latency, capacity và write amplification**.

## 10. Redis: command latency, key size và số phần tử

Redis core truy cập theo key và cấu trúc (String, Hash, Sorted Set,...), không có query planner giống MongoDB cho mọi lệnh.

Nếu ứng dụng duy trì sorted set:

~~~text
ZADD ready:merchant-a:shop-12 1794623400123 O900
ZADD ready:merchant-a:shop-12 1794623340000 O897
ZRANGE ready:merchant-a:shop-12 0 19 REV WITHSCORES
~~~

truy vấn đọc theo score có thể rẻ, nhưng:

- Set phải được cập nhật khi order rời READY; nếu không sẽ nhanh **nhưng sai**.
- Score Redis là double; không dùng epoch nanoseconds lớn rồi kỳ vọng chính xác từng đơn vị.
- Khi timestamp trùng, thứ tự phụ của member theo quy tắc Redis không tự đáp ứng mọi tie-breaker nghiệp vụ.
- Để lấy chi tiết đơn có thể cần thêm lệnh `MGET`, `HGETALL` hoặc gọi DB khác, ảnh hưởng round trips.

### 10.1. Đo những gì?

~~~text
SLOWLOG GET 20
INFO commandstats
INFO stats
MEMORY USAGE ready:merchant-a:shop-12
ZCARD ready:merchant-a:shop-12
~~~

| Counter/lệnh | Điều nó cho biết | Không tự cho biết |
| --- | --- | --- |
| SLOWLOG | Thời gian Redis xử lý lệnh trên ngưỡng theo cấu hình | Network RTT và toàn bộ API latency |
| INFO commandstats | Thống kê tổng hợp theo command | Phần tử xét trong mỗi lần gọi |
| MEMORY USAGE | Bộ nhớ ước tính của một key | Disk bytes hoặc response bytes |
| ZCARD | Số phần tử trong set | Có bao nhiêu còn hợp lệ nghiệp vụ |
| Driver timings | RTT và số lệnh/pipeline | Index/read model có đúng dữ liệu nguồn không |

Không dùng `KEYS order:*` trên keyspace lớn rồi GET tất cả để tìm 20 đơn như một “index” giả. `SCAN` hỗ trợ duyệt tăng dần để thực hiện tác vụ nền, nhưng **không tự biến thành secondary index chọn lọc** và có thể trả trùng/khác dữ liệu khi keyspace thay đổi.

## 11. Elasticsearch/OpenSearch: profile và shard cost

Search engine sử dụng inverted index, doc values và những cấu trúc phục vụ filter/sort. Một query trả ít hit vẫn có thể phải xử lý nhiều ứng viên hoặc fan-out trên nhiều shard.

Ví dụ DSL:

~~~json
{
  "size": 20,
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "merchant-a" } },
        { "term": { "shopId": "shop-12" } },
        { "term": { "status": "READY_TO_SHIP" } },
        {
          "range": {
            "createdAt": {
              "gte": "2026-11-07T12:00:00Z",
              "lt": "2026-11-14T12:00:00Z"
            }
          }
        }
      ]
    }
  },
  "sort": [
    { "createdAt": { "order": "desc" } },
    { "orderId": { "order": "asc" } }
  ],
  "track_total_hits": true
}
~~~

Giả định các trường tenant/shop/status/orderId được ánh xạ kiểu phù hợp cho **exact-match và sort** (thường là keyword), còn createdAt là date.

### 11.1. Đọc những counter nào?

- Query `took` và latency phía client/API.
- Số shard được truy vấn, shard thất bại và tải mỗi shard.
- `hits.total` với ngữ nghĩa của `track_total_hits`.
- Search profiling theo operator/collector/sort.
- Cache hit/miss, segment behavior và I/O.
- Response payload bytes và network.
- Indexing lag nếu search index là bản chiếu từ database chuẩn.

Chế độ `profile: true` có thể giúp phân tích từng pha nhưng **cũng thêm overhead**; không dùng thời gian profiling làm số p95 duy nhất. `hits.total` là số kết quả khớp theo ngữ nghĩa cấu hình, **không phải tổng số postings/document engine đã phải xét**.

### 11.2. Nhanh nhưng dữ liệu cũ vẫn là sai

Nếu O900 đã chuyển SHIPPED ở nguồn nhưng search index chưa cập nhật, query có thể vẫn trả O900. Phải đo **indexing lag**, chính sách quyền và khả năng đối soát ngoài query speed.

## 12. Neo4j: DB Hits và rows khi duyệt đồ thị

Graph query có thể bắt đầu từ node tìm bằng index rồi duyệt hàng triệu cạnh.

~~~cypher
PROFILE
MATCH (shop:Shop {id: 'shop-12'})<-[:BELONGS_TO]-(o:Order)
WHERE o.tenantId = 'merchant-a'
  AND o.status = 'READY_TO_SHIP'
RETURN o.id AS orderId,
       o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId ASC
LIMIT 20;
~~~

`EXPLAIN` cho kế hoạch ước lượng, `PROFILE` thực thi và báo thống kê từng operator tùy phiên bản Neo4j.

Cần quan sát:

- Operator **NodeIndexSeek** hay scan.
- **Rows** đi qua từng bước.
- **DB Hits** cho hoạt động truy cập theo engine.
- **Expand** tạo bao nhiêu relationship/path.
- Operator Sort/Top, memory và page cache.
- Query latency và mức tải đồng thời.

Ví dụ:

~~~text
NodeIndexSeek shop-12: 1 node
Expand BELONGS_TO: 1.000.000 relationship
Filter READY: 10.000 order
Sort + LIMIT: 20 result
~~~

Chỉ nhìn NodeIndexSeek ở đầu không cho thấy **chi phí expand 1 triệu cạnh**. Với variable-length traversal, kết quả trung gian có thể là nhiều path dẫn tới cùng node; cần xem rows/DB Hits theo operator và cách dùng DISTINCT nếu đếm entity.

## 13. Vector ANN: đo candidates và Recall@k cùng latency

ANN như HNSW/IVF có thể giảm số vector cần xét nhưng kết quả chỉ **gần đúng**. Phải đo thêm chất lượng retrieval.

~~~text
Exact top-10: A, B, C, D, E, F, G, H, I, J
ANN top-10:   A, B, C, D, E, F, G, H, X, Y
~~~

\[
\operatorname{Recall@10} = 8/10 = 0.8
\]

Recall@k so kết quả ANN với exact kNN theo cùng metric, tập dữ liệu và filter; **không phải tỷ lệ câu trả lời nghiệp vụ đúng**.

Các metric cần ghép:

| Metric | Điều cần quan sát |
| --- | --- |
| Recall@k | Mức tìm đủ top-k exact |
| p95/p99 search | Độ trễ ở tải thực tế |
| Candidates/graph nodes visited | Mức mở rộng theo thuật toán, nếu engine đo được |
| Distance calculations | Số phép so điểm nếu có counter |
| Index bytes/RAM | Footprint HNSW/IVF/PQ |
| I/O/cache | Truy cập SSD/RAM |
| Build/update costs | Thời gian build và thay đổi index |
| Filter efficiency | Tác động của bộ lọc metadata rất hẹp |

Một index ANN rất nhanh nhưng Recall@10 = 0,3 trong workload cần recall cao **chưa đạt yêu cầu**. Counter “visited nodes” không có định nghĩa chung ở mọi engine, nên không so số thô giữa các thuật toán nếu ngữ nghĩa khác nhau.

## 14. Bảng so sánh giả định trước/sau

Một phép đo minh họa (không phải benchmark đã thực hiện):

| Metric | Baseline | Sau compound index |
| --- | ---: | ---: |
| Kết quả hợp lệ | 20 | 20 |
| Documents examined | 800.000 | 20 |
| Keys examined | 0 | 23 |
| Document examination ratio | 40.000× | 1× |
| Driver p50 | 410 ms | 11 ms |
| Driver p95 | 920 ms | 28 ms |
| API p95 | 1.050 ms | 65 ms |
| Index footprint bổ sung | Không | Phải đo |
| Chi phí write mới | Không | Phải đo |

Nếu những số này được đo thật trong điều kiện tương đương, ta có thể kết luận **khối lượng document cần xét giảm mạnh và độ trễ p95 cải thiện trong workload ấy**. Nhưng vẫn cần:

- Cold/mixed cache và các query shape khác.
- p99 và mức tải đồng thời.
- Write throughput, update/delete cost.
- Dung lượng index, RAM và rebuild time.
- Độ mới dữ liệu và quyền truy cập.

### 14.1. Docs examined giảm mà latency gần như không đổi

Ví dụ:

~~~text
docsExamined giảm 1000 lần
API p95 chỉ giảm 5%
~~~

Khả năng:

- Phần lớn latency nằm ở app/network, không ở query này.
- API còn N+1 reads hoặc serialization lớn.
- Connection pool chờ lâu.
- Cache làm baseline nhanh sẵn, giảm scan chưa tác động nhiều.
- Query plan/explain không đại diện cho tải thực.

Cần **tracing end-to-end và phân rã latency**, không tiếp tục thêm index ngẫu nhiên.

### 14.2. p50 cải thiện nhưng p99 xấu đi

Khả năng:

- Index mới không vừa RAM, gây tail I/O.
- Tenant rất lớn có phân bố lệch.
- Workload cập nhật index cạnh tranh tài nguyên.
- Background compaction hoặc index build gây đỉnh.
- Nhiều request cùng chạm hot partition/key.

Không chỉ nhìn trung bình; phải đo p95/p99 **theo tenant, query shape và tải**.

## 15. Kiểm soát biến gây nhiễu

### 15.1. Warm và cold cache

Truy vấn đầu có thể phải lấy index/data pages từ SSD, những lần tiếp theo được cache. Thử:

- **Warm steady-state** sau giai đoạn khởi động.
- **Mixed working set** nhiều tenant/shop.
- **Cold-ish start** ở môi trường thử nghiệm an toàn, nếu làm được.

Không restart database production hoặc xóa cache production chỉ để đo “cold”.

### 15.2. Dữ liệu lệch và không có kết quả

Thử shop có 100, 10.000, 1.000.000 đơn. Thử status có selectivity 0,1% và 70%. Thử query không có kết quả: **index tốt có thể chứng minh không có kết quả mà không quét cả tenant**.

### 15.3. Concurrency và saturation

Ở concurrency 1, query có thể mất 10 ms. Với hàng trăm client, p99 có thể tăng vì CPU, I/O, connection pool, hot key hay throttling.

Mỗi lần đo cần ghi:

~~~text
client count / concurrency
offered QPS / completed QPS
p50/p95/p99
errors / timeouts / throttling
CPU / RAM / disk / network
cache hit rate
~~~

Đừng loại request timeout khỏi phân tích để giữ latency đẹp.

### 15.4. Giữ mức nhất quán tương đương

Đọc từ replica eventual consistency có thể nhanh hơn strong consistency, nhưng đó **không chỉ là lợi ích index**. Hãy so cùng hợp đồng consistency, đồng thời đo **index/read-model lag** nếu dữ liệu được đồng bộ bất đồng bộ.

### 15.5. Đo build riêng steady-state

Index build trên collection lớn có thể tiêu tốn CPU, I/O và thời gian. Đo:

- Build duration và tải trong lúc build.
- Dung lượng tạm và dung lượng thường trực.
- Rebuild/restore cost.
- Latency ghi khi index đã hoạt động.

Không cộng nhầm thời gian build vào mọi query, nhưng cũng không được bỏ chi phí triển khai/vận hành khỏi quyết định.

## 16. Chọn metric đúng cho loại query

| Query | Mục tiêu | Metric nổi bật |
| --- | --- | --- |
| Point lookup theo ID | Một bản ghi | Keys/rows examined, latency |
| Top-20 đã sort | 20 bản ghi đúng thứ tự | Keys/docs/rows examined, blocking sort, p95 |
| COUNT chính xác | Một con số | Tập dữ liệu phải xét, latency, precompute |
| Group theo ngày/shop | Nhiều nhóm | Input rows, group memory, shard merge |
| Full-text search | Relevance | Candidates, latency, index/search cost |
| ANN top-k | Láng giềng gần đúng | Recall@k, candidates, latency, RAM |
| Export lớn | Toàn bộ dữ liệu | Throughput bytes/s, cost per batch |

Một `COLLSCAN` không mặc nhiên sai nếu nghiệp vụ phải export tất cả bản ghi. Một `IXSCAN` cũng không mặc nhiên tốt nếu nó quét gần toàn bộ index rồi sort/fetch rất nhiều.

## 17. Khi nào nên thay index, read model hay cache?

| Hiện tượng | Hướng thử | Đo lại |
| --- | --- | --- |
| Quét cả collection dù filter hẹp | Compound index | Docs/keys examined, p95, index size |
| Index lọc được nhưng sort lớn | Điều chỉnh key order hoặc query | Blocking sort, p99, memory/spill |
| Fetch document rất lớn chỉ lấy vài field | Projection/covering index | DocsExamined, network bytes, write cost |
| Query chạm nhiều partition không phù hợp | Bảng đọc theo khóa/bucket/shard khác | Fan-out, rows/tombstones, merge latency |
| DynamoDB filter loại hầu hết item | Key/GSI theo predicate cần thiết | ScannedCount/Count/RCU và trang |
| Lặp một query nóng liên tục | Cache + invalidation | Hit ratio, stale data, API p95 |
| COUNT/SUM thường xuyên trên hàng triệu hàng | Pre-aggregation/summary | Read latency, write amp, reconciliation |
| Index footprint quá lớn | Giảm index dư, điều chỉnh read model | Cache hit, disk/ram, write latency |
| Filter/sort ad hoc nhiều chiều | Search/OLAP | Query cost, freshness, vận hành |

Chọn theo workload và SLO. Bản read model không được trở thành nguồn sự thật độc lập nếu chỉ là hình chiếu từ bản ghi chuẩn; cần thiết kế đồng bộ khi insert/update/delete.

## 18. Một index không phục vụ mọi query shape

Index cho Q1:

~~~text
(tenantId, shopId, status, createdAt DESC, orderId ASC)
~~~

rất phù hợp với truy vấn cố định ba field equality. Nhưng query khác:

~~~text
Lấy mọi trạng thái của shop-12,
sort createdAt DESC
~~~

không cố định `status` ở tiền tố trước `createdAt`. Do đó index trên **không tự cung cấp thứ tự toàn cục createdAt DESC cho mọi trạng thái**. Cần kiểm tra kế hoạch của từng query shape.

Một heuristic thường hữu ích cho compound index là cân nhắc **equality, sort, range** theo truy vấn, nhưng đây **không phải công thức tuyệt đối**. Cardinality, index bounds, sort direction và nhiều query dùng chung index đều có ảnh hưởng.

### 18.1. Filter sau LIMIT không đúng Q1

Nếu:

~~~text
Lấy 20 đơn mới nhất của shop
-> ứng dụng lọc status READY
~~~

kết quả có thể chỉ còn 2 đơn, dù phía sau vẫn có rất nhiều đơn READY. Giảm examined bằng cách **bỏ qua 18 kết quả đáng ra phải tìm** không phải tối ưu hợp lệ.

### 18.2. Cursor và timestamp trùng

Hai đơn có thể có cùng `createdAt`. Nếu chỉ sort theo `createdAt DESC` rồi phân trang, có nguy cơ trùng/bỏ đơn giữa các trang. Nên có tie-breaker như `orderId ASC`, cùng điều kiện cursor tương ứng và chính sách snapshot khi dữ liệu đổi trong lúc phân trang.

Đường đọc phải phục vụ **toàn bộ filter + sort + pagination**, không chỉ predicate đầu tiên.

## 19. Mẫu báo cáo thí nghiệm

~~~yaml
experimentId: orders-ready-index-01
queryName: latestReadyOrdersByShop
dataset:
  documents: 10000000
  tenantSize: 800000
  shopSize: 120000
  snapshot: test-snapshot-2026-11-14
query:
  filter: tenantId + shopId + READY_TO_SHIP + createdAtRange
  sort: createdAt DESC, orderId ASC
  limit: 20
  projection: [orderId, createdAt, customerId, totalVnd]
environment:
  databaseVersion: "điền phiên bản thực tế"
  hardware: "điền CPU/RAM/storage"
  concurrency: 20
  cacheState: warm
results:
  before:
    p95Ms: "đo thực tế"
    rowsOrDocumentsExamined: "đo theo engine"
    keysExamined: "đo nếu có counter"
    bytesRead: "ghi tầng đo và tên counter"
  after:
    p95Ms: "đo thực tế"
    rowsOrDocumentsExamined: "đo theo engine"
    keysExamined: "đo nếu có counter"
    bytesRead: "ghi tầng đo và tên counter"
correctness:
  identicalIdsAndOrder: "kiểm chứng trên snapshot tương ứng"
  authorization: "tenant và shop đã được xác thực"
~~~

Giá trị `đo thực tế` chỉ là **placeholder**, không phải số được thu thập. Nếu engine không có metric tương đương, ghi `N/A` kèm cách đo thay thế, không bịa một bộ đếm rồi so như cùng đơn vị.

### 19.1. Bộ trường hợp phải có

| Nhóm | Trường hợp | Vì sao cần |
| --- | --- | --- |
| Dữ liệu nhỏ | Shop có 10–100 đơn | Tránh thêm index phức tạp vô ích |
| Dữ liệu lớn | Shop có hàng triệu đơn | Phát hiện scan lớn |
| Status hiếm | READY 0,1% | Đánh giá filter selectivity |
| Status phổ biến | READY 70% | Đánh giá sort/range |
| Zero results | Không có đơn phù hợp | Kiểm tra chi phí chứng minh rỗng |
| Concurrency | Nhiều request cùng shop | Kiểm tra hotspot/tail latency |
| Cold cache | Index/data không ở RAM | Kiểm tra I/O |
| Dữ liệu thay đổi | READY → SHIPPED | Kiểm tra freshness |
| Phân trang | Nhiều ID cùng timestamp | Không bỏ/trùng kết quả |

Một kết luận tốt cần nêu **query, dataset, tải, phạm vi counter và giới hạn**. Không viết “index nhanh hơn 100 lần trong mọi tình huống” nếu chỉ có một thử nghiệm với một tenant.

## 20. Các lỗi diễn giải thường gặp

| Nhận định sai | Vì sao không đúng | Cách làm tốt hơn |
| --- | --- | --- |
| “Có IXSCAN là xong.” | Có thể vẫn quét 100.000 key | Xem key/doc counters và plan đầy đủ |
| “Trả 20 hàng tức đọc 20 hàng.” | Lọc/sort trước LIMIT có thể rất lớn | Đo candidates/rows/partitions |
| “executionTimeMillis là API p95.” | Explain khác driver/end-to-end | Đo cả ba lớp |
| “docsExamined=0 nghĩa zero work.” | Covered query vẫn đọc index | Xem keys examined/cache/I/O |
| “ConsumedCapacity là SSD bytes.” | RCU theo quy tắc dịch vụ | Không quy đổi sang physical I/O |
| “DynamoDB Limit=20 trả 20 sau filter.” | Limit tác động trước FilterExpression | Duyệt trang đúng |
| “CQL LIMIT 20 đủ cho 7 ngày.” | Bảng ngày có nhiều partition | Merge và kiểm tra đủ bucket |
| “Tombstone không liên quan khi LIMIT nhỏ.” | Có thể phải duyệt nhiều dấu xóa | Quan sát tombstones scanned |
| “NodeIndexSeek làm graph query rẻ.” | Expand có thể duyệt triệu cạnh | Xem rows/DB Hits từng operator |
| “Search hits.total là docs examined.” | Tổng hit khác candidates/segments | Dùng profile/metrics tương ứng |
| “ANN rất nhanh chắc chắn tốt.” | Có thể mất recall | Đo Recall@k |
| “p50 tốt là đủ.” | p99/timeout có thể xấu | Đo tail và lỗi ở tải đồng thời |
| “Index càng nhiều field càng tốt.” | Footprint/write amp tăng | Tối ưu theo query quan trọng |
| “Số document × size = disk bytes.” | Cache/nén/page I/O khác | Đo đúng tầng physical |
| “Cứ scan rồi filter sau LIMIT.” | Trả thiếu/không đúng thứ tự | Giữ contract trong access path |
| “Một lần chạy đại diện production.” | Cache, tải, dữ liệu thay đổi | Benchmark nhiều mẫu/tenant |
| “Nhanh hơn dù stale data cũng được.” | Kết quả sai nghiệp vụ | Đo correctness và freshness |

## 21. Bài tập

### Bài 1 — Tính read amplification

Hai kế hoạch đều trả 20 document:

~~~text
Plan A: docsExamined=400000, keysExamined=0
Plan B: docsExamined=20, keysExamined=30
~~~

Hãy tính document examination ratio của mỗi plan và key ratio của Plan B. Giải thích vì sao không thể kết luận về **disk bytes** nếu chỉ có những số đó.

### Bài 2 — Phân tích IXSCAN chưa tốt

MongoDB báo:

~~~text
nReturned=20
totalKeysExamined=180000
totalDocsExamined=170000
winningPlan có IXSCAN, FETCH, SORT
~~~

Hãy đề xuất compound index tương ứng Q1, cách kiểm tra sort có còn blocking không và các metric cần đo lại. Nêu trường hợp index trên field `status` đứng riêng có thể kém chọn lọc.

### Bài 3 — Covered index

Index gồm `tenantId, shopId, status, createdAt, orderId`. Query trả thêm `customerId` và `totalVnd`.

- Vì sao có thể cần fetch document?
- Thêm hai field có thể giảm chi phí đọc nào?
- Nó làm tăng những chi phí ghi/cache nào?
- Với một query được gọi rất ít, có nên thêm index lớn không?

### Bài 4 — DynamoDB sau filter

Một Query có:

~~~text
ScannedCount=40
Count=3
LastEvaluatedKey=present
ConsumedCapacity=10 (capacity units minh họa)
~~~

API cần 20 kết quả. Hãy mô tả cách phân trang, tổng hợp counters qua các request, đánh giá RCU và lựa chọn key/GSI mới để giảm lượng item bị filter loại.

### Bài 5 — Cassandra và tombstones

Bảng `READY_TO_SHIP` trả 20 hàng sống nhưng tracing cho thấy phải xét nhiều tombstone. Hãy mô tả vì sao trạng thái READY → SHIPPED gây xóa, tác động tới LIMIT, những metric cần xem và vì sao không nên thay đổi cấu hình repair/tombstone safety tùy tiện.

### Bài 6 — Byte vật lý và byte logic

Một nhóm đo `docsExamined` giảm từ 100.000 xuống 20, size document trung bình 1 KiB. Nhóm khẳng định “SSD đọc giảm từ 100 MiB xuống 20 KiB”.

Hãy giải thích vì sao chưa đủ căn cứ: các yếu tố index, nén, page cache, disk reads và network payload ảnh hưởng thế nào? Đề xuất counter/telemetry bổ sung.

### Bài 7 — Tenant lớn và lệch dữ liệu

~~~text
Tenant A: 1.000 order
Tenant B: 5.000.000 order
Tenant C: 20.000 order
~~~

Thiết kế benchmark cho cả ba tenant, thêm status hiếm/phổ biến, cửa sổ thời gian hẹp/rộng, cold/warm cache và concurrency. Chỉ ra vì sao benchmark chỉ trên A dễ kết luận sai.

### Bài 8 — Sort và phân trang

Có 100 đơn cùng `createdAt`. Nếu API chỉ sort theo thời gian rồi phân trang, điều gì xảy ra? Đề xuất tie-breaker, cursor và quy tắc khi dữ liệu được thêm/xóa giữa các trang.

### Bài 9 — Query SUM/COUNT

Dashboard tính SUM và COUNT 90 ngày trên hàng chục triệu Order. So:

- Quét trực tiếp theo query.
- Compound index.
- Materialized summary theo shop/ngày.

Với mỗi phương án, nêu read latency, rows examined, chi phí ghi, độ mới và cách đối soát. Vì sao index không mặc nhiên biến mọi phép SUM thành truy vấn O(1)?

### Bài 10 — Thiết kế phép thử quyết định triển khai

Lập thí nghiệm cho Q1 gồm baseline và index mới; đo p50/p95/p99, errors, QPS, keys/rows examined, bytes với tầng đo rõ, index footprint, write latency và freshness. Đề xuất ngưỡng chấp nhận và cách ghi báo cáo không vượt quá những gì đã quan sát.

## 22. Quy trình ra quyết định

~~~mermaid
flowchart TD
    A["Query chậm hoặc tốn capacity"] --> B["Chốt đúng query contract"]
    B --> C["Đo latency + examined + bytes + errors"]
    C --> D{"Nút thắt ở đâu?"}
    D -->|Scan/filter/sort| E["Thử index đúng predicate/order"]
    D -->|Fan-out partition| F["Thử read model/bucket mới"]
    D -->|Network/app/N+1| G["Tối ưu API, batch, payload"]
    D -->|Aggregation lớn| H["Thử pre-aggregation/OLAP"]
    E --> I["Đo lại và so correctness"]
    F --> I
    G --> I
    H --> I
    I --> J{"Đạt SLA + đúng dữ liệu + chi phí hợp lý?"}
    J -->|Có| K["Triển khai có kiểm soát"]
    J -->|Không| L["Phân tích bottleneck và điều chỉnh"]
    L --> C
~~~

Nhớ sáu nguyên tắc:

1. **Đúng truy vấn trước:** Filter, sort, pagination, projection, consistency và quyền truy cập phải được giữ nguyên.
2. **Đo đúng phạm vi:** Database time khác API time; row/key examined khác byte SSD; trả 20 không đồng nghĩa đọc 20.
3. **Xem toàn bộ kế hoạch:** Index scan, fetch, post-filter, sort, partition fan-out và merge đều có chi phí.
4. **So trước/sau công bằng:** Cùng dữ liệu, query, cấu hình tải và trạng thái cache được ghi rõ.
5. **Không bỏ chi phí ghi:** Index size, build, RAM, compaction và update/delete latency là một phần quyết định.
6. **Chỉ kết luận theo số liệu:** Index tốt khi trả đúng dữ liệu, giảm công việc cần thiết và đạt SLO trong ngân sách chấp nhận.

## Kết luận

**Kiểm chứng chỉ mục không phải hỏi “có dùng index không?”, mà hỏi “index làm giảm bao nhiêu công việc cần thiết để trả đúng kết quả ở độ trễ và chi phí phù hợp?”** Trong NoSQL, các số đo cần thay đổi theo hệ:

- **MongoDB:** `totalKeysExamined`, `totalDocsExamined`, query plan và driver/API latency.
- **Cassandra/ScyllaDB:** Partitions, rows, tombstones, SSTables, tracing và tail latency.
- **DynamoDB:** `ScannedCount`, `Count`, `ConsumedCapacity`, số trang và round trips.
- **Redis:** Command latency, key memory/size, số lệnh và độ đúng của cấu trúc đã tính trước.
- **Elasticsearch/OpenSearch:** Shard/query profile, hits, cache, indexing lag và latency.
- **Neo4j:** Rows/DB Hits theo operator, traversal expansion và sort.
- **ANN:** Candidates, RAM/I/O, latency **cùng Recall@k**.

Một đánh giá đáng tin cậy có **ba lớp**: **tính đúng của kết quả**, **khối lượng dữ liệu/khóa cần xét** và **độ trễ/chi phí ở tải thực**. Nếu examined giảm mà API p95 không giảm, cần tìm bottleneck ở lớp khác. Nếu API nhanh hơn nhưng dữ liệu cũ hoặc thiếu, index chưa đạt yêu cầu. Nếu đọc nhanh hơn nhưng chi phí ghi và RAM tăng quá mức, thiết kế vẫn có thể cần điều chỉnh.

Khi đo đủ những lớp này, nhóm phát triển có thể phân biệt **chỉ mục thực sự hữu ích** với chỉ mục chỉ chuyển chi phí sang nơi khác, và biết khi nào cần thay đổi đường truy cập hoặc mô hình dữ liệu thay vì tiếp tục thêm index.
