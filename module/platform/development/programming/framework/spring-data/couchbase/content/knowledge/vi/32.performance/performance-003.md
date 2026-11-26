# Tối ưu chỉ mục theo điều kiện lọc và sắp xếp

## 1. Chỉ mục tốt phải phục vụ câu truy vấn thật

Trong một dịch vụ đơn hàng sử dụng **Spring Data Couchbase**, màn hình lịch sử giao dịch cần lấy **20 đơn mới nhất của khách hàng có trạng thái PAID**. Collection `orders` có hàng triệu document, nhưng query chỉ trả 20 row:

~~~sql
SELECT META(o).id AS id, o.status, o.createdAtEpochMs, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "order"
  AND o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Nếu index không phù hợp, Query service có thể phải đọc quá nhiều index entries, fetch nhiều document hoặc sắp xếp một tập trung gian lớn trước khi lấy 20 kết quả. Thêm index một cách tùy ý đôi khi chỉ khiến mutation chậm hơn vì mỗi lần ghi phải duy trì thêm cấu trúc chỉ mục.

Bài **“Tối ưu chỉ mục theo điều kiện lọc và sắp xếp”** thuộc chương **Hiệu năng**, module **SPRING_DATA_COUCHBASE**. Phạm vi module là xây dựng tầng truy cập bằng document mapping, repository, `CouchbaseTemplate` và SQL++; đồng thời thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive để bảo đảm hiệu năng, nhất quán và khả năng vận hành.

**Mục tiêu sau bài học:**

1. Đọc một query SQL++ để nhận diện field lọc bằng, field phạm vi và trường sắp xếp.
2. Thiết kế secondary index và thứ tự key phù hợp với các access pattern.
3. Hiểu index prefix, selectivity, range scan, `ORDER BY`, `LIMIT` và các điều kiện để giảm sorting/fetch.
4. Chọn giữa composite, covering, partial, expression và array index dựa trên nhu cầu.
5. Kiểm tra `EXPLAIN` và metrics thay vì khẳng định optimizer “chắc chắn” chọn index.
6. Hiểu ảnh hưởng của mapper Spring Data, derived query, projection và scan consistency.
7. Đánh giá chi phí ghi, kích thước index, build/rollout và vận hành trong production.
8. Xây benchmark trước/sau với cùng query semantics và độ đúng dữ liệu.

Ví dụ dùng SQL++ trên Couchbase Server có bucket/scope/collection, Java 17, Spring Boot 3.x và Spring Data Couchbase 5.x, SDK Java 3.x tương thích. Một số tính năng, cú pháp, tên operator của `EXPLAIN` và thuật toán optimizer **phụ thuộc phiên bản server**. Mọi khuyến nghị cuối cùng phải được xác minh trên query plan, index definition và dữ liệu của hệ thống đang chạy.

## 2. Phân biệt KV lookup và SQL++ index scan

Nếu ứng dụng đã biết **document ID chính xác** trong đúng collection, `CouchbaseRepository.findById(id)` hoặc SDK `Collection.get(id)` thường đi theo **Key-Value (KV)**. Không cần tạo GSI chỉ để GET một key.

Khi ứng dụng hỏi “những đơn hàng nào thuộc customer A, trạng thái PAID, sắp xếp mới nhất?”, nó **chưa có danh sách document IDs**. SQL++ và secondary indexes mới là công cụ tìm tập tài liệu phù hợp.

~~~mermaid
flowchart TD
    A["Request từ Spring service"] --> B{"Biết đầy đủ document key?"}
    B -- "Có" --> C["KV GET / lookupIn / replace"]
    B -- "Không, cần WHERE/ORDER BY" --> D["SQL++ Query service"]
    D --> E["Chọn index và xác định spans"]
    E --> F["Index scan"]
    F --> G["Fetch nếu cần"]
    G --> H["Filter / Order / Limit / projection"]
    C --> I["Kết quả theo key"]
    H --> I
~~~

Sơ đồ mang tính khái niệm: không phải query plan nào cũng có tất cả các bước. Nếu index bao phủ những dữ liệu cần dùng, Query service có thể **không cần fetch document đầy đủ**. Nếu order/limit được tận dụng tốt từ index, một số bước sắp xếp có thể được giảm hoặc loại bỏ.

### 2.1. Index là tối ưu đường tìm, không thay đổi contract dữ liệu

Một query nhanh nhưng trả sai do thiếu điều kiện tenant, đọc dữ liệu chưa đạt consistency, hoặc lọc nhầm loại document không phải tối ưu hợp lệ.

Luôn chốt trước:

- Predicate nghiệp vụ và quyền truy cập.
- Thứ tự kết quả ổn định.
- Số row cần trả, phân trang.
- Yêu cầu read-after-write và scan consistency.
- Các field projection thật sự cần thiết.

Sau đó mới chọn chỉ mục.

## 3. Mô hình dữ liệu xuyên suốt

Giả sử collection:

~~~text
Bucket: commerce
Scope: sales
Collection: orders
Document ID: order::O-2026-001
~~~

Document JSON:

~~~json
{
  "docType": "order",
  "customerId": "u-42",
  "status": "PAID",
  "createdAtEpochMs": 1795582800000,
  "orderSequence": 10051,
  "total": 150000,
  "currency": "VND",
  "itemCount": 3
}
~~~

Trong ví dụ, `createdAtEpochMs` là số epoch milliseconds, giúp so sánh/sắp xếp theo thời gian. Tên field chỉ là schema minh họa; production phải có quy tắc timestamp, timezone và migration nhất quán.

Một số use case:

| Tên | WHERE | ORDER BY | LIMIT |
| --- | --- | --- | --- |
| A. Lịch sử khách hàng | `customerId = ? AND status = ?` | `createdAtEpochMs DESC` | 20 |
| B. Đơn theo khách hàng | `customerId = ?` | `createdAtEpochMs DESC` | 20 |
| C. Báo cáo đơn PAID | `status = ?` | `createdAtEpochMs DESC` | 100 |
| D. Khoảng thời gian | `customerId = ? AND createdAtEpochMs >= ?` | `createdAtEpochMs DESC` | 50 |
| E. Tìm một order | `META().id = ?` | Không | 1 |
| F. Tổng hợp theo trạng thái | `status = ?` | Không | Aggregation |

**Không có một index luôn tối ưu cho tất cả các hàng trên.** Bài toán là lựa chọn một số index có giá trị cao nhất theo tần suất, selectivity, chi phí và SLO.

## 4. Secondary index được định nghĩa theo collection

Ví dụ chỉ mục tổng hợp cho use case A:

~~~sql
CREATE INDEX ix_orders_customer_status_created
ON `commerce`.`sales`.`orders`
(
    customerId,
    status,
    createdAtEpochMs DESC
);
~~~

Chỉ mục có thứ tự key: `customerId`, sau đó `status`, rồi `createdAtEpochMs DESC`.

Đường query:

~~~sql
SELECT META(o).id AS id, o.status, o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Đây là **ứng viên mạnh** cho truy vấn có hai điều kiện equality và sắp xếp theo thời gian. Query service có thể xác định vùng giá trị index theo `customerId` và `status`, rồi đọc các entries theo `createdAtEpochMs`.

Nhưng chưa có gì bảo đảm tuyệt đối optimizer sẽ dùng index này hoặc tránh mọi sort: còn phụ thuộc query form, index statistics, ordering/null/missing semantics, kế hoạch thực thi và server version. **Dùng `EXPLAIN` để xác minh.**

### 4.1. Namespace phải khớp

Index ở `commerce.sales.orders` không giúp query đang vô tình đọc `commerce.checkout.orders`. Spring Data `@Scope`/`@Collection` cũng phải trỏ đúng namespace.

Tên index có thể giống nhau ở những keyspace khác; hãy lưu đầy đủ bucket/scope/collection khi theo dõi và benchmark.

## 5. Quy tắc thực dụng: equality trước, sort sau

Với access pattern A:

~~~sql
WHERE customerId = $customerId
  AND status = $status
ORDER BY createdAtEpochMs DESC
LIMIT 20
~~~

Một index hợp lý:

~~~text
(customerId, status, createdAtEpochMs DESC)
   equality equality        sort
~~~

**Lý do:** khi hai key đầu được cố định bằng giá trị equality, entries của nhóm đó có thể được duyệt theo key kế tiếp, gần với thứ tự `ORDER BY` cần trả.

Tuy nhiên “đặt mọi equality trước sort” chỉ là **heuristic**:

- Nếu query thường bỏ điều kiện `status`, index bắt đầu `customerId, status, createdAtEpochMs` có thể không duy trì thứ tự thời gian toàn cục mong muốn cho tất cả status.
- Nếu `status IN (...)` gồm nhiều giá trị, mỗi status có thể tạo một nhóm entries riêng; cần xem kế hoạch merge/sort.
- Nếu một predicate range xuất hiện trước sort key khác, khả năng tận dụng order có thể đổi.
- Index cardinality, selectivity, query frequency và mutation cost cũng quan trọng.

Vì vậy thiết kế index **theo workload thực**, không theo một công thức phổ quát.

## 6. Composite index và quy tắc key tiền tố

Index:

~~~text
(customerId, status, createdAtEpochMs DESC)
~~~

Các tình huống:

| Predicate | Độ phù hợp với index trên | Cần kiểm chứng |
| --- | --- | --- |
| `customerId = ?` | Có leading key | Thứ tự thời gian trên mọi status có cần sort không |
| `customerId = ? AND status = ?` | Phù hợp equality prefix | Sort pushdown / span |
| `status = ?` | Không có equality trên key đầu | Optimizer có chọn index khác/scan rộng không |
| `createdAtEpochMs >= ?` | Chỉ lọc key thứ ba | Khả năng index được dùng hiệu quả thấp nếu thiếu prefix |
| `customerId = ? AND status IN (...)` | Nhiều ranges/group | Có bước merge/sort và bao nhiêu entries bị scan |
| `customerId = ? AND status = ? AND createdAtEpochMs >= ?` | Có prefix và range | Scan range, order, limit |

Nói đơn giản: **key đầu quyết định index thích hợp với những predicate nào**. Bỏ qua leading key thường làm vùng scan lớn hoặc khiến optimizer chọn chỉ mục khác. Một số optimizer có tối ưu đặc biệt, nhưng không nên mặc định có skip-scan hay khả năng tìm hiệu quả với mọi key thiếu tiền tố.

### 6.1. Một index duy nhất không tự bao phủ mọi query

Nếu endpoint phổ biến thứ hai chỉ lọc `customerId` và order thời gian, có thể cần:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `commerce`.`sales`.`orders`
(
    customerId,
    createdAtEpochMs DESC
);
~~~

Chỉ mục này phục vụ use case B rõ hơn, nhưng cũng tạo **write amplification**. Trước khi tạo, đo tần suất B và xác nhận index A không đáp ứng SLO; không lập thêm index chỉ vì lý thuyết cho rằng mỗi query phải có index riêng.

## 7. Thứ tự key: equality, range và sorting

Xét use case D:

~~~sql
SELECT META(o).id AS id, o.createdAtEpochMs, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.createdAtEpochMs >= $fromEpochMs
ORDER BY o.createdAtEpochMs DESC
LIMIT 50;
~~~

Một index phù hợp:

~~~sql
CREATE INDEX ix_orders_customer_created_total
ON `commerce`.`sales`.`orders`
(
    customerId,
    createdAtEpochMs DESC,
    total
);
~~~

Ở đây:

- `customerId` là equality prefix.
- `createdAtEpochMs` vừa có range predicate vừa là sort key.
- `total` được thêm để cân nhắc covering projection.

Không tự đưa `total` lên trước `createdAtEpochMs` chỉ vì nó xuất hiện trong SELECT; như vậy có thể phá cấu trúc sort hữu ích.

### 7.1. Range predicate trước trường sort khác

Query:

~~~sql
WHERE customerId = $customerId
  AND total >= $minTotal
ORDER BY createdAtEpochMs DESC
LIMIT 20
~~~

Hai ứng viên:

~~~text
(customerId, total, createdAtEpochMs DESC)
(customerId, createdAtEpochMs DESC, total)
~~~

Ứng viên đầu có thể thu hẹp bằng range `total`, nhưng không nhất thiết cung cấp các kết quả theo `createdAtEpochMs` toàn cục mà không sort. Ứng viên sau có thể duyệt theo thời gian rồi filter `total`, hiệu quả nếu tìm đủ 20 row sớm; nhưng nếu `total >= ?` cực hiếm, có thể scan nhiều.

**Không chọn theo khẩu hiệu.** Dùng cardinality thật, `EXPLAIN` và latency/scan metrics cho những giá trị `$minTotal` phổ biến và hiếm gặp.

## 8. ORDER BY có nhiều trường và tie-breaker

Nếu nhiều order có cùng `createdAtEpochMs`, câu:

~~~sql
ORDER BY o.createdAtEpochMs DESC
LIMIT 20
~~~

có thể không tạo thứ tự ổn định giữa các row bằng timestamp. Điều này gây lặp hoặc thiếu dữ liệu khi phân trang.

Có thể thêm `orderSequence` duy nhất trong ngữ cảnh:

~~~sql
ORDER BY o.createdAtEpochMs DESC,
         o.orderSequence DESC
LIMIT 20;
~~~

Một index ứng viên:

~~~sql
CREATE INDEX ix_orders_customer_created_seq
ON `commerce`.`sales`.`orders`
(
    customerId,
    createdAtEpochMs DESC,
    orderSequence DESC
);
~~~

Điều kiện “orderSequence duy nhất” phải được đảm bảo bằng thiết kế dữ liệu ở phạm vi cần phân trang. Nếu không, hãy có tie-breaker thực sự duy nhất.

### 8.1. Chiều ASC/DESC và NULL/MISSING

Chiều index keys ảnh hưởng khả năng phục vụ `ORDER BY`, đặc biệt khi có nhiều trường trộn ASC/DESC. Với dữ liệu không đủ field hoặc field có `NULL`, thứ tự và predicate có thể khác kỳ vọng.

Nên:

- Chuẩn hóa schema để các trường sort quan trọng luôn có mặt.
- Dùng kiểu dữ liệu nhất quán, ví dụ epoch milliseconds dạng số.
- Xem `EXPLAIN` để biết có operator `Order` hay không.
- Test trường hợp thiếu/null khi API có thể trả row dạng đó.

Không coi một index `DESC` là cam kết mọi câu ORDER BY sẽ được push down.

## 9. `LIMIT` giúp giảm chi phí khi kế hoạch tận dụng index

Query top-N:

~~~sql
SELECT META(o).id AS id, o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Nếu index duyệt đúng thứ tự và điều kiện, Query engine có thể lấy đủ N entries mà không cần xử lý toàn bộ tập match. Nhưng nếu query yêu cầu sort ngoài index hoặc còn filter residual không sớm loại được, `LIMIT 20` **không có nghĩa chỉ 20 entries được scan**.

Cần nhìn:

- Có operator `Order` hay không và có sort trung gian?
- Có `Limit` pushdown xuống scan không?
- Index scan thực sự đi qua bao nhiêu entries?
- Có `Fetch` bao nhiêu document?
- Có filter sau fetch không?

**LIMIT là một phần tối ưu plan, không phải phép màu cắt mọi công việc xuống N rows.**

## 10. Phân trang OFFSET có thể đắt ở trang sâu

Ví dụ:

~~~sql
SELECT META(o).id AS id, o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAtEpochMs DESC
LIMIT 20 OFFSET 20000;
~~~

Ngay cả với index hỗ trợ sort, để bỏ qua 20.000 entries đầu, hệ thống vẫn có thể phải duyệt nhiều hơn 20 row. Trang càng sâu, tổng công việc thường tăng.

Nếu use case phù hợp, xem **keyset/cursor pagination**:

~~~sql
SELECT META(o).id AS id,
       o.createdAtEpochMs,
       o.orderSequence
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND (
       o.createdAtEpochMs < $lastCreatedAt
       OR (
           o.createdAtEpochMs = $lastCreatedAt
           AND o.orderSequence < $lastSequence
       )
  )
ORDER BY o.createdAtEpochMs DESC,
         o.orderSequence DESC
LIMIT 20;
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_orders_cursor
ON `commerce`.`sales`.`orders`
(
    customerId,
    createdAtEpochMs DESC,
    orderSequence DESC
);
~~~

Đừng tự cho rằng predicate có `OR` luôn được push down tối ưu. Kiểm tra `EXPLAIN` và thử trên các cursor sâu. Cursor phải gắn với cùng filter/sort và được ký/bảo vệ nếu client có thể sửa bất hợp pháp. Keyset pagination cũng không tự tạo snapshot bất biến khi dữ liệu thay đổi giữa các trang; cần xác định consistency yêu cầu.

## 11. Covering index là gì?

Một **covering index** có đủ thông tin cần thiết để thực thi query mà không phải fetch toàn bộ document từ Data service. Ví dụ màn hình danh sách chỉ cần:

~~~text
id, status, createdAtEpochMs, total
~~~

Index ứng viên:

~~~sql
CREATE INDEX ix_orders_list_cover
ON `commerce`.`sales`.`orders`
(
    customerId,
    status,
    createdAtEpochMs DESC,
    total
);
~~~

Query:

~~~sql
SELECT META(o).id AS id,
       o.status,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Với index/keyspace/server phù hợp, `META().id` và các field được chọn có thể lấy từ index entries. `EXPLAIN` sẽ cho thấy query có được cover hay còn operator fetch.

### 11.1. Vì sao `SELECT o.*` thường không cover?

~~~sql
SELECT o.*
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Nếu document chứa rất nhiều fields ngoài index, Query service thường cần fetch content đầy đủ để trả `o.*`. Một index chỉ chứa vài field không thể mặc định đáp ứng mọi projection.

**Không mở rộng index với toàn bộ field JSON chỉ để “cover tất cả”.** Index rộng hơn có thể chiếm thêm disk/memory, tăng write amplification và làm scan kém hiệu quả.

### 11.2. Projection theo DTO khác đọc full entity

Một repository finder trả `OrderDocument` đầy đủ có thể cần các field/type metadata của mapper. Một query DTO projection chỉ chọn `status`, `total` có thể giảm response bytes và cơ hội dùng covering index.

Cần kiểm tra Spring Data projection thật đã tạo SQL++ nào, có thêm điều kiện type filter/field mapping không, rồi mới thiết kế index.

## 12. Partial index: chỉ lưu các document liên quan

Nếu collection chứa nhiều loại document hoặc chỉ một tập nhỏ có trạng thái cần query, **partial index** có thể giảm kích thước index và chi phí duy trì so với index mọi document.

Ví dụ các order có `docType="order"`:

~~~sql
CREATE INDEX ix_orders_paid_like
ON `commerce`.`sales`.`orders`
(
    customerId,
    status,
    createdAtEpochMs DESC
)
WHERE docType = "order";
~~~

Ở đây index chỉ chứa các document thỏa điều kiện partial predicate theo semantics server. Để optimizer cân nhắc index một cách an toàn, **query cần có predicate được chứng minh là phù hợp/bao hàm điều kiện WHERE của index**:

~~~sql
SELECT META(o).id AS id, o.status, o.createdAtEpochMs
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "order"
  AND o.customerId = $customerId
  AND o.status = $status
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Không viết partial index rồi bỏ `docType` khỏi query và kỳ vọng optimizer luôn tự biết dữ liệu đều là order.

### 12.1. Partial index theo trạng thái

Nếu workload chủ yếu đọc đơn PAID, có thể xem:

~~~sql
CREATE INDEX ix_orders_paid_recent
ON `commerce`.`sales`.`orders`
(
    customerId,
    createdAtEpochMs DESC,
    total
)
WHERE status = "PAID"
  AND docType = "order";
~~~

Query ứng viên:

~~~sql
SELECT META(o).id AS id,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.docType = "order"
  AND o.status = "PAID"
  AND o.customerId = $customerId
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

**Cẩn thận với parameterized status:** một query `status = $status` có thể mang nhiều giá trị; việc optimizer chứng minh query phù hợp partial index cố định `status="PAID"` phụ thuộc cách bind/preparation và plan. Không tối ưu bằng cách nhét trực tiếp input người dùng vào SQL string. Nếu cần hai access patterns cố định/động, đánh giá plan và thiết kế query/index rõ ràng.

## 13. Index không tự chứa document có field thiếu

Trong nhiều trường hợp, secondary index có semantics về field **MISSING** và các entries được lập chỉ mục. Nếu predicate truy vấn những document thiếu field dẫn đầu, chỉ mục hiện tại có thể không phục vụ theo cách bạn tưởng.

Nên xác định:

- Field lọc/sort có bắt buộc trong mọi document không?
- Entity cũ có schema khác hoặc thiếu field không?
- Có thể dùng normalized field/giá trị mặc định một cách đúng nghiệp vụ không?
- Index expression có dùng `IFMISSING`, `IFNULL` hoặc cơ chế tương đương không, và query có dùng đúng expression tương ứng không?

Đừng tự thêm default `0` hoặc chuỗi rỗng nếu làm sai thứ tự business. Hãy xử lý schema migration và query semantics có chủ đích.

## 14. Function trên field có thể phá khả năng dùng index thường

Giả sử tìm email không phân biệt hoa/thường:

~~~sql
WHERE LOWER(o.email) = LOWER($email)
~~~

Một index chỉ trên `email` không nhất thiết có thể dùng hiệu quả cho expression `LOWER(email)`. Hai hướng:

1. Lưu trường đã chuẩn hóa, ví dụ `emailNormalized`, index trực tiếp.
2. Tạo **expression index** phù hợp với biểu thức trong query, nếu version hỗ trợ.

~~~sql
CREATE INDEX ix_customers_email_lower
ON `commerce`.`crm`.`customers`
(
    LOWER(email)
);
~~~

Query:

~~~sql
SELECT META(c).id AS id
FROM `commerce`.`crm`.`customers` AS c
WHERE LOWER(c.email) = LOWER($email);
~~~

**Phải kiểm tra** expression matching, collation và query plan. Chọn normalized persisted field nếu muốn giảm chi phí gọi function trong write/query hoặc cần kiểm soát Unicode/case-folding theo nghiệp vụ. Việc chuẩn hóa email có nhiều quy tắc; không tự coi `LOWER` là giải pháp chuẩn tuyệt đối cho mọi định danh.

### 14.1. Date parsing trên hot predicate

Nếu mọi query phải parse timestamp string thành number khi lọc, index/key schema có thể không khớp. Một field `createdAtEpochMs` dạng số nhất quán giúp query range/order đơn giản hơn.

Tuy nhiên migration cần xác minh toàn bộ document đã có đủ giá trị; không chuyển kiểu trên một phần data rồi so sai kết quả.

## 15. LIKE và prefix search

Một truy vấn tiền tố có thể có cơ hội dùng index tốt hơn truy vấn chứa chuỗi tùy vị trí, tùy collation/optimizer:

~~~sql
WHERE o.referenceCode LIKE "ORD-2026%"
~~~

So với:

~~~sql
WHERE o.referenceCode LIKE "%2026%"
~~~

Leading wildcard thường khiến một range scan theo prefix B-tree khó hiệu quả hơn. Nếu cần contains/full-text search, nên cân nhắc Search service hay thiết kế search index riêng, thay vì cố ép một secondary index thường giải quyết tất cả.

Không khẳng định mọi dạng LIKE sẽ push down: hãy dùng `EXPLAIN` và kiểm thử parameterization.

## 16. `IN`, `OR` và nhiều spans

Query:

~~~sql
WHERE o.customerId = $customerId
  AND o.status IN ["PAID", "SHIPPED"]
ORDER BY o.createdAtEpochMs DESC
LIMIT 20
~~~

Nếu index là:

~~~text
(customerId, status, createdAtEpochMs DESC)
~~~

mỗi trạng thái có thể tương ứng một nhóm/range, và kết quả toàn cục cần merge/sort theo `createdAtEpochMs`. Không được giả định Query sẽ đọc đúng 20 index entries.

Khi use case “mọi trạng thái, mới nhất trước”, index:

~~~text
(customerId, createdAtEpochMs DESC, status)
~~~

có thể giúp duy trì thứ tự thời gian tốt hơn, nhưng status là residual filter có thể làm scan nhiều entries. Đo theo tỷ lệ từng status, số rows scanned và p95/p99.

### 16.1. Không dàn nhiều OR thành SQL bằng string nối thiếu an toàn

Hãy dùng parameterized SQL++ hoặc repository query binding thay vì ghép giá trị người dùng trực tiếp vào statement. Query injection là rủi ro correctness/bảo mật, không phải tối ưu.

## 17. Array index cho predicate trên phần tử mảng

Một order có thể có:

~~~json
{
  "customerId": "u-42",
  "status": "PAID",
  "tags": ["fragile", "express"],
  "createdAtEpochMs": 1795582800000
}
~~~

Tìm các order có tag:

~~~sql
SELECT META(o).id AS id
FROM `commerce`.`sales`.`orders` AS o
WHERE ANY tag IN o.tags SATISFIES tag = "express" END;
~~~

Với workload thường xuyên như vậy, **array index** có thể phù hợp:

~~~sql
CREATE INDEX ix_orders_tags
ON `commerce`.`sales`.`orders`
(
    DISTINCT ARRAY tag FOR tag IN tags END
);
~~~

Cú pháp ARRAY index và matcher/optimizer có những giới hạn theo version. Mọi order có nhiều tags có thể tạo nhiều index entries, tăng footprint và write cost. Nếu query còn lọc customer/sort theo time, cần đánh giá compound array index và plan thực tế; không tự nối thêm field tùy ý rồi cho rằng order pushdown sẽ hoạt động.

## 18. Primary index không phải câu trả lời cho mọi query production

Primary index có thể hỗ trợ truy vấn ad hoc hoặc trường hợp không có secondary index phù hợp, nhưng không biến một predicate chọn lọc trên triệu document thành query tối ưu.

Một câu:

~~~sql
SELECT o.*
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = "u-42";
~~~

nếu chạy nhờ primary scan lớn, có thể gây tải không cần thiết.

Đối với workload sản xuất đã biết, ưu tiên **secondary index đúng predicate và projection**, xem `EXPLAIN` thay vì phụ thuộc primary index như một phương án mặc định. Đừng xóa primary index đang dùng bởi công cụ khác mà không kiểm kê phụ thuộc; đây là thay đổi vận hành riêng.

## 19. Dùng EXPLAIN để kiểm chứng thiết kế index

Chạy cùng query và predicate thực tế:

~~~sql
EXPLAIN
SELECT META(o).id AS id,
       o.status,
       o.createdAtEpochMs,
       o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = "u-42"
  AND o.status = "PAID"
ORDER BY o.createdAtEpochMs DESC
LIMIT 20;
~~~

Trong plan, tìm thông tin tương đương (tên có thể khác theo phiên bản):

- **IndexScan/IndexScan3:** index nào được chọn, có spans chọn lọc không?
- **Covers/index projection:** các field trả về có nằm trong index không?
- **Fetch:** có fetch document đầy đủ sau index scan không?
- **Filter:** còn predicate nào chỉ được áp sau scan/fetch?
- **Order:** Query có phải sort lại không?
- **Limit/Offset:** có thể giảm scan sớm không?
- **Estimated cost/cardinality:** optimizer ước lượng bao nhiêu rows?

Đừng chỉ nhìn tên index đã xuất hiện rồi kết luận tối ưu thành công. Một index được dùng nhưng scan hàng triệu entries vẫn có thể không đáp ứng mục tiêu.

### 19.1. Phân biệt IndexScan với Fetch

Ví dụ suy luận khái niệm:

~~~text
IndexScan(ix_orders_customer_status_created)
  -> Fetch(full documents)
  -> Order(createdAtEpochMs DESC)
  -> Limit(20)
~~~

Đây là **sơ đồ minh họa**, không phải EXPLAIN JSON thật. Hãy xem liệu fetch/order có thể được giảm bằng index covering, query projection và thứ tự keys; đồng thời kiểm tra chi phí maintain index rộng hơn.

### 19.2. PLAN có thể đổi theo version và statistics

Optimizer có thể chọn plan khác khi dữ liệu, statistics, index state hoặc server version thay đổi. Không pin một plan trong tài liệu như cam kết vĩnh viễn. Nếu plan không như mong đợi, kiểm tra query form, index definition và khả năng cập nhật thống kê trong version tương ứng.

## 20. Từ EXPLAIN đến profile/metrics chạy thật

EXPLAIN mô tả kế hoạch dự kiến; latency thật còn phụ thuộc key distribution, CPU, I/O và queue. Khi cần sâu hơn, dùng profiling/query metrics được server hoặc SDK hỗ trợ ở phiên bản hiện tại.

Nên đo:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Query p50/p95/p99 | Trải nghiệm dưới tải và tail |
| Index scan entries | Query phải xét bao nhiêu index entries |
| Returned rows | Số row thực trả |
| Fetch count/bytes | Chi phí lấy document từ Data service |
| Query CPU/service time | Nút thắt ở Query |
| Index CPU/scan latency | Nút thắt ở Index |
| Data service read ops | Tải do fetch/KV |
| Network response bytes | Projection tiết kiệm được bao nhiêu |
| Timeout/error rate | Index mới có ổn định dưới tải không |
| Write latency | Chi phí của index bổ sung trên mutation |

**Scanned entries / returned rows** là một tín hiệu hữu ích về scan amplification, nhưng số cụ thể có thể được báo theo operator/version khác nhau; không tự suy mọi index API đều có cùng metric name.

## 21. Đo đường cơ sở trước khi tạo thêm index

Không tối ưu chỉ vì thấy query mất 150 ms ở một lần chạy. Một baseline có giá trị ghi:

~~~text
Use case: 20 order PAID mới nhất của customer
Query: parameterized SQL++ theo customerId/status
Dataset: 5 triệu orders, size distribution đã biết
Index hiện tại: tên và DDL
Load: 100, 300, 600 request/s
Consistency: NOT_BOUNDED hoặc REQUEST_PLUS theo yêu cầu
Result count: <=20
Measurement: warm-up + steady state
Metrics: p50/p95/p99, goodput, errors,
         scanned/returned rows, fetch, bytes, CPU
Run ID: baseline-orders-recent
~~~

Đây là **mẫu**, không phải số liệu đã đo. Sau tối ưu, giữ cùng dataset, key distribution, server topology, query semantics, consistency và load.

### 21.1. Đừng so query khác chức năng

Query A trả 20 row gồm 4 fields; query B trả 20 entity `SELECT *`. Nếu B chậm hơn, nguyên nhân có thể là data size/mapping, không chỉ index choice.

Một cải tiến hợp lệ cần giữ business fields cần thiết và auth/tenant conditions, hoặc giải thích rõ contract thay đổi.

## 22. Chọn index theo tần suất và selectivity

Xem ba query:

~~~text
Q1  70% traffic: customerId + status, recent 20
Q2  20% traffic: customerId, recent 20
Q3  10% traffic: status, recent 100
~~~

Ứng viên:

~~~text
I1 (customerId, status, createdAtEpochMs DESC)
I2 (customerId, createdAtEpochMs DESC)
I3 (status, createdAtEpochMs DESC)
~~~

Không nhất thiết lập cả ba. Hãy hỏi:

1. SLO riêng từng query là gì?
2. Q2 có đủ nhanh trên I1 với dữ liệu thực không?
3. Q3 có tần suất/độ chọn lọc đáng đầu tư I3 không?
4. Mỗi index làm tăng mutation latency, storage, memory ra sao?
5. Index có trùng lặp gần như hoàn toàn với index khác không?
6. Có thể sửa query hoặc dùng KV theo ID thay vì SQL++ không?

**Portfolio index** là một bài toán tối ưu toàn hệ thống, không phải một index cho mỗi câu query theo thói quen.

## 23. Spring Data derived query ảnh hưởng SQL++ thật

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    private String customerId;
    private String status;
    private Long createdAtEpochMs;
    private Long total;

    protected OrderDocument() {
    }

    public String getId() { return id; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public Long getCreatedAtEpochMs() { return createdAtEpochMs; }
    public Long getTotal() { return total; }
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.domain.Pageable;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerIdAndStatus(
            String customerId,
            String status,
            Pageable pageable
    );
}
~~~

Gọi với sort/paging:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

var page = PageRequest.of(
        0, 20,
        Sort.by(Sort.Direction.DESC, "createdAtEpochMs")
);

var orders = repository.findByCustomerIdAndStatus(
        "u-42", "PAID", page
);
~~~

Cú pháp derived query, sort và return type cần kiểm tra theo Spring Data release. Điểm mấu chốt là **index phải phù hợp với SQL++ thật sự phát sinh**, gồm field names do mapping quy đổi, type filters, pagination và sorting.

### 23.1. Đừng đoán SQL++ từ tên method

Khi tối ưu:

- Bật log/observability của query ở môi trường test theo khả năng phiên bản.
- Xác nhận statement thực và parameter binding.
- Kiểm tra `EXPLAIN` trên statement đó.
- So khớp field mapping (Java property vs JSON field).
- Kiểm tra các điều kiện type discriminator được mapper thêm.
- Xem `Page`/count query có khiến hệ thống phát thêm query ngoài SELECT chính không.

Một index chỉ tối ưu SELECT nhưng count query trong pagination vẫn phải scan rộng có thể khiến endpoint chậm. Nếu chỉ cần “có thêm trang hay không”, cân nhắc Slice hoặc cursor pagination theo API/version thích hợp.

## 24. Mapping type filter và partial index

Spring Data Couchbase thường có type information/discriminator để phân biệt entity; ở một số đường query, framework có thể thêm predicate lọc theo type. Nếu index partial chỉ dựa trên `docType="order"` do ứng dụng tự thêm, còn generated SQL++ chỉ lọc theo metadata type khác, optimizer không thể tự đoán hai loại bằng nhau.

Lựa chọn:

1. Thiết kế index theo predicate thật mà Spring Data phát ra.
2. Sử dụng field `docType` nhất quán trong entity/query nếu nghiệp vụ cần.
3. Kiểm tra cụ thể `@Query`, derived methods và type discriminator theo version.
4. Không sửa/xóa type metadata để làm query “nhanh” nếu phá entity mapping.

Đây là ví dụ vì sao nên xem **SQL++ thực tế**, không chỉ nhìn Java method.

## 25. `@Query` và projection có chủ đích

Khi derived query khó kiểm soát statement hoặc cần projection chuyên biệt, Spring Data Couchbase hỗ trợ `@Query` trong các phiên bản phù hợp.

Một mẫu có thể dùng các biến SpEL do Spring Data cung cấp:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderQueryRepository
        extends CouchbaseRepository<OrderDocument, String> {

    @Query(
        "#{#n1ql.selectEntity} WHERE #{#n1ql.filter} " +
        "AND customerId = $1 AND status = $2 " +
        "ORDER BY createdAtEpochMs DESC LIMIT 20"
    )
    List<OrderDocument> recentByCustomerAndStatus(
            String customerId, String status);
}
~~~

Đoạn này **minh họa** cơ chế tạo entity SELECT và type filter, không phải khẳng định đoạn query luôn phủ index hay không có FETCH. `selectEntity` thường cần entity fields đầy đủ. Cần kiểm tra SpEL placeholders, kết quả generated query và version đang sử dụng.

Với projection ít field, có thể dùng SQL++ trực tiếp qua SDK `Cluster.query`, DTO mapping theo contract và named parameters. Không lấy chuỗi input người dùng ghép vào câu SQL++.

## 26. SDK SQL++ với parameter binding

Ví dụ:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

public final class RecentOrderQuery {

    private final Cluster cluster;

    public RecentOrderQuery(Cluster cluster) {
        this.cluster = cluster;
    }

    public java.util.List<JsonObject> findRecent(
            String customerId,
            String status) {

        String sql = """
                SELECT META(o).id AS id,
                       o.status,
                       o.createdAtEpochMs,
                       o.total
                FROM `commerce`.`sales`.`orders` AS o
                WHERE o.customerId = $customerId
                  AND o.status = $status
                ORDER BY o.createdAtEpochMs DESC
                LIMIT 20
                """;

        var result = cluster.query(
                sql,
                QueryOptions.queryOptions()
                        .parameters(
                                JsonObject.create()
                                        .put("customerId", customerId)
                                        .put("status", status))
                        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
        );

        return result.rowsAsObject();
    }
}
~~~

**Lưu ý:** `REQUEST_PLUS` là ví dụ cho use case yêu cầu query đợi index cập nhật theo contract. Nó có thể làm tăng latency và không cần thiết cho mọi màn hình lịch sử. Trong benchmark phải so đúng consistency requirement; dùng mặc định/`NOT_BOUNDED` khi business cho phép và đánh giá chi phí tương ứng.

### 26.1. SQL string và scope

Câu ví dụ định danh đủ bucket/scope/collection. Với query context và namespace khác, SQL++ có thể tham chiếu ngắn hơn; luôn kiểm tra đường thực tế và RBAC.

## 27. Query scan consistency và độ trễ index

SQL++ Query service dùng Index service; các mutation KV có thể được index bất đồng bộ. Những khái niệm thường gặp:

- `NOT_BOUNDED`: không đòi index scan đợi tới mức mutation mới nhất theo request.
- `REQUEST_PLUS`: yêu cầu độ mới index phù hợp contract tại lúc query bắt đầu, có thể cần chờ.
- Token-based consistency: ràng buộc index nhìn thấy một số mutation xác định, khi SDK/API hỗ trợ.

**Không loại bỏ consistency chỉ để giảm p99** nếu endpoint cần read-after-write. Cũng không đặt `REQUEST_PLUS` trên mọi query vì tưởng nó làm index “nhanh hơn”; đây là lựa chọn về **độ mới dữ liệu**, không phải tối ưu index geometry.

Với document key đã biết, dùng KV GET khi phù hợp, tránh phụ thuộc index visibility không cần thiết.

## 28. Indexes làm tăng chi phí ghi

Mỗi index thêm vào collection có thể tạo công việc khi document được insert/update/delete/expire, tùy field và engine. Một index cover nhiều field có thể chiếm thêm disk, memory và tài nguyên Index service.

Bảng đánh đổi:

| Tối ưu đọc | Chi phí tiềm ẩn |
| --- | --- |
| Composite index hẹp | Duy trì thêm entries khi ghi |
| Covering index rộng | Index size lớn hơn, tốn tài nguyên |
| Partial index | Chỉ mục nhỏ hơn nhưng query phải match predicate |
| Expression index | Tính/duy trì expression và storage |
| Array index | Nhiều entries cho nhiều phần tử |
| Nhiều index tương tự | Write amplification và overhead vận hành |
| Index replicas/partitioning | Tài nguyên, topology và behavior theo version |

Vì vậy đánh giá cả **write p95/p99, mutation throughput, index memory/disk và backlog**, không chỉ query p50.

### 28.1. Đo tốc độ ghi sau khi thêm index

Nếu service có 80% GET, 20% UPSERT, một index có thể giảm query latency nhưng tăng độ trễ của một nhóm writes. Chạy một workload mixed đủ đại diện, không chỉ SELECT query đơn lẻ.

## 29. Index build và rollout trong production

Một thay đổi index có vòng đời riêng:

~~~mermaid
flowchart TD
    A["Chốt query và baseline"] --> B["Soạn DDL / quyền"]
    B --> C["Build trên staging gần production"]
    C --> D["EXPLAIN + correctness test"]
    D --> E["Load test read và write"]
    E --> F{"Đạt SLO, resource budget?"}
    F -- "Không" --> G["Điều chỉnh index/SQL"]
    F -- "Có" --> H["Rollout production có quan sát"]
    H --> I["Xác minh index online và plan"]
    I --> J["Đánh giá loại bỏ index cũ nếu an toàn"]
~~~

Khi build index trên dataset lớn, có thể phát sinh CPU/I/O và tăng tải Index service. Cần:

1. Thông báo/điều phối với vận hành.
2. Đánh giá capacity và thời gian xây dựng.
3. Chọn tính năng defer build/batch build nếu phù hợp phiên bản và quy trình.
4. Theo dõi trạng thái index cho đến khi online.
5. Triển khai application change chỉ khi index đã sẵn sàng nếu query phụ thuộc nó.
6. Quan sát p95/p99, errors và Index/Data resource sau rollout.
7. Không xóa index cũ ngay trước khi chứng minh không còn query cần nó.

**Không chạy `DROP INDEX` hoặc tạo hàng chục index trực tiếp trên production chỉ để thử.**

## 30. Index hints chỉ nên dùng sau khi hiểu optimizer

Một số phiên bản SQL++ có cú pháp hint như `USE INDEX` để hướng optimizer cân nhắc chỉ mục cụ thể.

Có thể hữu ích khi:

- Optimizer chọn index không như mong đợi dù statistics/DDL đúng.
- Cần workaround tạm thời cho một query quan trọng.
- Có bằng chứng benchmark và đã thử tối ưu predicate/index.

Nhưng hint có rủi ro: khi dữ liệu, schema, index hoặc server version đổi, forced plan có thể trở nên kém. Không dùng hint như “cách sửa đầu tiên” thay vì `EXPLAIN`, query rewrite và statistics/index health.

### 30.1. Cập nhật statistics không phải phương thuốc vạn năng

Một số bản Couchbase có cơ chế optimizer statistics và lệnh quản trị tương ứng. Chúng có thể giúp estimation, nhưng không sửa một index thiếu leading key hay truy vấn không có sargable predicate.

Đối chiếu syntax/version và đo lại trước khi kết luận. Không chạy thống kê trên cluster tải cao mà không hiểu chi phí vận hành.

## 31. Kiểm thử kết quả trước khi đo tốc độ

Tối ưu index phải **không thay đổi tập kết quả và thứ tự nghiệp vụ**.

Các test nên bao phủ:

1. Customer không có order: kết quả rỗng.
2. Khách hàng có nhiều status: filter đúng.
3. Hai order cùng createdAt: tie-breaker ổn định.
4. Trường sort NULL/MISSING (nếu schema cho phép).
5. Status IN nhiều giá trị: sort toàn cục đúng.
6. Customer thuộc tenant khác: không bị lộ.
7. Document mới ghi và query ngay: consistency theo contract.
8. Phân trang sâu: không bỏ/lặp item ngoài quy tắc khi dữ liệu ổn định.
9. Entity Spring Data type filter: không lọc thiếu tài liệu đúng.
10. Index chưa online: có hành vi error/fallback đã thiết kế.

Nên tạo **test data nhỏ có expected order rõ ràng** rồi chạy các biến thể query. Không dùng performance test làm cách duy nhất xác minh correctness.

## 32. Integration test cho index và SQL++

Một test trong môi trường riêng có thể:

~~~text
Arrange
  - Tạo đúng bucket/scope/collection test.
  - Provision index cần thiết.
  - Chờ index online.
  - Ghi dataset đã biết: customer, status, timestamp, total.

Act
  - Query bằng parameters.
  - Dùng scan consistency phù hợp test vừa ghi.

Assert
  - Đúng row IDs, fields và ORDER BY.
  - LIMIT đúng.
  - Không lọt row tenant/status khác.
  - EXPLAIN kiểm tra plan nếu cần.

Cleanup
  - Xóa document test và resource riêng an toàn.
~~~

Khi test `EXPLAIN`, tránh assert toàn bộ JSON plan byte-for-byte: plan có thể đổi theo version/optimizer. Nếu muốn regression guard, kiểm tra các đặc điểm quan trọng như index name, tránh primary scan, operator fetch/order không mong đợi, rồi review khi nâng version.

## 33. Benchmark trước/sau: ba trục hiệu năng

Bài trước đã nhấn mạnh baseline **độ trễ, thông lượng và dữ liệu truyền**; khi đánh giá index, cần bổ sung scan/fetch và write amplification.

| Metric | Baseline | Candidate |
| --- | --- | --- |
| Query p50/p95/p99 | Đo dưới tải tương đương | Đo lại |
| Goodput query req/s | Số query hữu ích | Số query hữu ích |
| Unexpected errors/timeouts | Phân loại rõ | Phân loại rõ |
| Index entries scanned | Theo profile/metric | So với baseline |
| Document fetch count | Theo plan/metric | Xem có giảm |
| Response bytes | Projection giữ nguyên | So sánh cùng contract |
| Query/Index CPU/memory | Trước index | Sau index |
| Index disk/footprint | Trước | Sau |
| KV write p95/p99 | Trước | Sau |
| Write throughput | Trước | Sau |

Ví dụ số liệu **giả định**, không phải benchmark thực tế:

| Metric | Chưa tối ưu | Sau index cover |
| --- | ---: | ---: |
| Query p95 | 170 ms | 38 ms |
| Query p99 | 350 ms | 85 ms |
| Scan entries/query | 25.000 | 70 |
| Fetch docs/query | 2.000 | 0 |
| Index footprint thêm | 0 | 1,2 GiB |
| Write p95 | 18 ms | 21 ms |

Nếu đây là kết quả thực, cần xét lợi ích đọc so với chi phí index/write và tài nguyên. Chỉ báo p95 giảm mà bỏ write regression là chưa đầy đủ.

## 34. Chẩn đoán những tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Query lọc customer rất chậm | Không có index leading `customerId` | `EXPLAIN`, spans |
| Index đúng tên nhưng vẫn sort | Thứ tự key không phục vụ ORDER BY; nhiều ranges | Operator Order, query predicates |
| LIMIT 20 vẫn scan nhiều entries | Residual filter hoặc sorting | Scan/fetch/limit pushdown |
| Query `SELECT *` fetch nhiều | Index không cover entity fields | Projection/cover, đo index width |
| Index partial không được chọn | Query không bao hàm WHERE của index | Kiểm tra predicate thực |
| Query dùng `LOWER(email)` chậm | Index trên raw email không match expression | Expression/normalized index |
| `status IN` top 20 chậm | Nhiều spans, merge/sort | Đổi index strategy theo workload |
| Trang sâu OFFSET chậm | Bỏ qua nhiều rows | Keyset pagination |
| Derived query khác SQL viết tay | Mapping, type filter, sort/page khác | Ghi query phát sinh |
| Query trả thiếu dữ liệu vừa ghi | Index consistency chưa đủ | `REQUEST_PLUS`/token semantics |
| Index tạo xong nhưng query lỗi | Build chưa online, quyền/schema | Trạng thái index, Query plan |
| Write p99 tăng sau thêm index | Write amplification, Index service load | Mixed benchmark |
| Index size tăng quá nhanh | Cover nhiều fields, array entries, trùng index | Review definitions/footprint |
| Optimizer chọn index khác dự kiến | Statistics, selectivity, version | EXPLAIN/profile, cập nhật thống kê phù hợp |
| Không cải thiện dù query index tốt | Bottleneck ở app/network/DTO | Trace end-to-end |
| GET theo ID đang dùng SQL++ | Chọn sai đường truy cập | Dùng KV repository.findById/SDK get |

### 34.1. Cây quyết định

~~~mermaid
flowchart TD
    A["SQL++ WHERE/ORDER BY chậm"] --> B{"Đã biết exact document ID?"}
    B -- "Có" --> C["Ưu tiên KV get/findById"]
    B -- "Không" --> D["Chạy EXPLAIN"]
    D --> E{"Index có leading predicate phù hợp?"}
    E -- "Không" --> F["Thiết kế composite/partial index"]
    E -- "Có" --> G{"Có Sort/Fetch/scan rộng?"}
    G -- "Có" --> H["Xem order, cover, range và projection"]
    G -- "Không" --> I["Kiểm tra Query/Index resource + app mapping"]
    F --> J["Benchmark read + write + consistency"]
    H --> J
    I --> J
~~~

## 35. Bài tập thực hành: hệ thống đơn hàng

Ứng dụng có:

~~~text
commerce.sales.orders
commerce.sales.invoices
commerce.checkout.carts
~~~

Truy vấn:

- Q1: 20 đơn PAID mới nhất của customer.
- Q2: 20 đơn mới nhất của customer, bất kể status.
- Q3: 100 đơn PAID mới nhất toàn hệ thống.
- Q4: Top 20 order với `total >= threshold`, sắp xếp theo ngày tạo.
- Q5: Filter theo `LOWER(email)`.
- Q6: Find order theo document ID.
- Q7: Phân trang history theo cursor.
- Q8: Lọc order có tag `express`.

**Câu hỏi:**

1. Vì sao Q6 nên dùng KV thay vì tạo GSI cho `META().id`?
2. Đề xuất composite index cho Q1; phân tích leading equality và sort key.
3. Vì sao Q2 không chắc được tối ưu tốt bởi index của Q1?
4. Vì sao `status IN [...]` có thể làm mất ưu thế sort của index bắt đầu bằng status?
5. So sánh hai index `(customerId,total,createdAt)` và `(customerId,createdAt,total)` cho Q4.
6. Khi nào nên thêm `total` vào covering index? Khi nào không nên?
7. Vì sao partial index cần predicate tương ứng trong query?
8. Q5 nên dùng expression index hay normalized field, và trade-off gì?
9. Q7 cần tie-breaker nào để paging không nhập nhằng?
10. Với Q8, array index có thể tạo chi phí ghi gì?
11. Tại sao `LIMIT 20` không đồng nghĩa chỉ scan 20 entries?
12. Hãy dùng `EXPLAIN` để kiểm tra index name, spans, Fetch, Order và Limit.
13. Thiết kế baseline p95/p99 + scan/fetch + write p95 trước/sau thêm index.
14. Nếu index mới khiến query nhanh nhưng update order chậm hơn 30%, cần điều tra gì?
15. Nếu query qua repository trả entity đủ fields, tại sao index cover vài fields có thể chưa loại được Fetch?

**Định hướng:** mỗi query cần được hiểu theo predicate, sort, projection và độ chọn lọc. Đầu tư index theo workload/SLO, kiểm tra plan và đo đủ read/write/consistency; không tạo index chỉ vì field xuất hiện trong SELECT.

## 36. Checklist production

- [ ] Biết rõ từng use case có document ID hay cần query predicate.
- [ ] Đã đọc SQL++ thật của repository/template/SDK, không chỉ tên method.
- [ ] Đã xác định bucket/scope/collection và type filters.
- [ ] Đã phân loại equality, range, IN/OR và order fields.
- [ ] Composite index có leading keys phục vụ các query thường gặp.
- [ ] ORDER BY nhiều trường có tie-breaker ổn định khi cần paging.
- [ ] Đã kiểm tra DESC/ASC, null/missing và kiểu dữ liệu sort.
- [ ] LIMIT/OFFSET được đánh giá theo mức scan thực.
- [ ] Có xem xét cursor pagination cho trang sâu.
- [ ] Covering index chỉ thêm fields có lợi ích đáng chi phí.
- [ ] Partial index có query predicate tương ứng.
- [ ] Expression/array index được dùng đúng nhu cầu và version.
- [ ] Không xem primary index như phương án mặc định production.
- [ ] EXPLAIN cho thấy index, spans, Fetch, Order và Limit phù hợp.
- [ ] Có profile/metrics thật, không chỉ EXPLAIN.
- [ ] Kiểm tra query cardinality/selectivity trên dữ liệu đại diện.
- [ ] Consistency được giữ theo business contract khi benchmark.
- [ ] Không gỡ CAS/TTL/security filter chỉ để tăng tốc.
- [ ] Đo read p50/p95/p99, throughput, errors, bytes.
- [ ] Đo write p95/p99, index footprint và Index service load.
- [ ] Kiểm tra duplicate/unneeded indexes.
- [ ] Có kế hoạch build index staging, rollout, trạng thái online và rollback.
- [ ] Không DROP index đang được dùng khi chưa kiểm kê.
- [ ] Query parameters được bind an toàn, không nối input vào SQL string.
- [ ] Đã kiểm thử correctness, sort order, pagination và tenant isolation.
- [ ] Có regression test cho generated query/mapping khi nâng Spring Data/Server.
- [ ] Lưu baseline/run ID/config và so candidate cùng workload.

## 37. Tổng kết

Tối ưu chỉ mục SQL++ trong **Spring Data Couchbase** bắt đầu từ **điều kiện lọc và thứ tự sắp xếp thực tế**, không phải từ việc thêm index cho mọi field. Một composite index phù hợp thường kết hợp equality prefix với sort/range keys; covering index có thể tránh fetch, partial index thu hẹp tập document và expression/array index xử lý các predicate đặc biệt.

Nhưng thứ tự index chỉ là giả thuyết cho query plan: `IN`, range, `ORDER BY` nhiều trường, `LIMIT/OFFSET`, projection, field thiếu và generated SQL++ từ Spring Data đều có thể thay đổi kết quả. Vì vậy cần **EXPLAIN + số đo thực tế** để xác nhận index scan, sort, fetch, latency và throughput.

Cuối cùng, một index tốt phải cân bằng **đọc nhanh**, **chi phí ghi chấp nhận được**, **độ mới dữ liệu đúng yêu cầu**, **kích thước index** và **khả năng vận hành**. Bằng cách thiết kế theo access pattern, benchmark trước/sau và rollout có kiểm soát, bạn có thể đạt hiệu năng SQL++ ổn định mà vẫn giữ đúng metadata, CAS, TTL và tính nhất quán của ứng dụng.

