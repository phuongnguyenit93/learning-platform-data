# Phân trang, sắp xếp và lọc trên dữ liệu nhiều nguồn trong Microservices

## Mục tiêu học tập

Trong kiến trúc Microservices, dữ liệu về một nghiệp vụ thường được quản lý bởi nhiều bounded context: Order sở hữu đơn hàng, Payment sở hữu trạng thái thanh toán, Customer sở hữu hồ sơ người mua, Catalog sở hữu sản phẩm. Một màn hình quản trị lại có thể yêu cầu tìm tất cả đơn hàng **đã thanh toán**, của khách hàng ở một phân khúc nhất định, có sản phẩm thuộc nhóm Điện tử, sắp xếp giảm dần theo thời điểm thanh toán và phân trang 20 mục mỗi lần.

Bài toán không chỉ là gọi vài API rồi ghép JSON. **Pagination, sorting và filtering xác định một tập kết quả logic cùng một thứ tự toàn cục**. Khi field lọc/sắp xếp thuộc nhiều service, việc lấy một trang cục bộ từ mỗi nguồn thường không đủ để tạo một trang toàn cục đúng. Cần quyết định query owner, cách join, consistency, cursor, authorization, chi phí và giới hạn dữ liệu.

Sau bài học, người học có thể:

1. Phân biệt phân trang trong một nguồn với phân trang trên nhiều nguồn.
2. Giải thích vì sao “mỗi service lấy page N, rồi merge” hoặc “lấy 20 Orders rồi lọc Payment” thường sai.
3. Thiết kế thứ tự toàn phần có **unique tie-breaker** và phân biệt offset với keyset/cursor pagination.
4. Sử dụng filter pushdown, batch enrichment, live fan-out, sorted-stream merge và materialized read model đúng ngữ nghĩa.
5. Hiểu cursor đa nguồn cần **per-source consumed positions**, không được bỏ qua item đã fetch nhưng chưa sử dụng.
6. Phân tích các mức nhất quán: live best-effort, snapshot, event-driven projection và read-your-writes.
7. Thiết kế hợp đồng API có whitelist filter/sort, cursor opaque, page size, hasNext, count semantics, error và freshness metadata.
8. Xử lý quyền truy cập, dữ liệu multi-tenant, partial failure, retry và timeout trong query liên dịch vụ.
9. Đo cost/SLO và kiểm thử không lặp, không bỏ sót trên tập dữ liệu tĩnh; mô tả hạn chế khi dữ liệu thay đổi.
10. Lập ADR lựa chọn giải pháp phù hợp mà không biến query layer thành một shared database cho mọi domain.

**Phạm vi:** Bài thuộc nhóm **Truy vấn liên dịch vụ** của Software Design / System Architecture / Microservices. Ví dụ Order–Payment–Customer–Catalog minh họa cách một read API đáp ứng yêu cầu truy vấn; không ngụ ý các service có chung quyền ghi hoặc chung database.

## 1. Một yêu cầu tưởng đơn giản nhưng không đơn giản

Màn hình “Danh sách đơn hàng” có các điều kiện:

- tenantId được suy ra từ identity đã xác thực;
- createdAt nằm trong một khoảng ngày;
- orderStatus=CONFIRMED;
- paymentStatus=PAID;
- customerSegment=LOYAL;
- productCategory=ELECTRONICS;
- sort=-paidAt,orderId;
- limit=20 và có nextCursor;
- có thể hiển thị tên khách hàng, tổng tiền và số sản phẩm.

Nguồn dữ liệu:

| Nguồn | Chủ sở hữu | Field minh họa |
|---|---|---|
| Order | Order Service | orderId, tenantId, customerId, createdAt, orderStatus, totalAmount |
| Payment | Payment Service | paymentId, orderId, status, paidAt, refundedAt |
| Customer | Customer Service | customerId, displayName, customerSegment |
| Catalog | Catalog Service | productId, category, productName |
| Order lines | Order hoặc một aggregate liên quan | orderId, productId, quantity |
| Query projection | Dịch vụ đọc nếu có | Các field đã tổng hợp/index nhằm phục vụ search |

Một cách làm sai dễ gặp:

~~~text
1. GET Order?page=1&size=20
2. Lấy 20 orderIds
3. Hỏi Payment xem đơn nào PAID
4. Hỏi Customer xem khách nào LOYAL
5. Hỏi Catalog xem sản phẩm thuộc ELECTRONICS
6. Lọc, sắp xếp rồi trả còn 3 items
~~~

Nếu 20 Orders đầu chỉ có 3 đơn thỏa điều kiện, còn 100 đơn thỏa điều kiện nằm ở những trang Order chưa đọc, kết quả trả 3 items là **không phải trang 1 đúng** của query toàn cục. Hơn nữa, sort theo paidAt sau khi chỉ đọc 20 orders sẽ không tìm được 20 orders có paidAt mới nhất trên toàn bộ dữ liệu.

### 1.1. Semantics chính xác của một page

Một cách hình thức:

~~~text
D = tập entity thuộc phạm vi người gọi được phép đọc

F = bộ lọc đã chuẩn hóa trên những thuộc tính cần thiết
K = thứ tự toàn phần có tie-breaker duy nhất

Filtered = {x ∈ D | F(x) đúng}
Sorted = sort(Filtered, K)
Page = đoạn liên tiếp của Sorted theo cursor/offset hợp lệ
~~~

Đây là **mô hình logic**, không yêu cầu dữ liệu phải lưu trong một DB. Tuy nhiên kiến trúc triển khai phải cung cấp bằng chứng rằng các item được trả phù hợp filter, order và cursor trong mức consistency đã công bố.

### 1.2. Không có JOIN toàn cục tự động

Trong một monolith với cùng database, có thể dùng JOIN, WHERE, ORDER BY, LIMIT. Khi mỗi service sở hữu database riêng, không được âm thầm giả định chúng có một transaction snapshot hay index toàn cục. Query aggregator có thể gọi API, subscribe events hoặc duy trì projection, nhưng phải quyết định ai chịu trách nhiệm cho **global membership, global sorting và page continuity**.

## 2. Phân biệt ba công việc: lọc, sắp xếp, phân trang

**Lọc (filtering):** Xác định entity nào thuộc kết quả. Ví dụ chỉ Orders mà Payment đã PAID, không chỉ những Orders có một payment attempt bất kỳ.

**Sắp xếp (sorting):** Định nghĩa quan hệ thứ tự giữa mọi entity trong tập kết quả. Ví dụ paidAt DESC, orderId ASC. Nếu paidAt ở Payment mà Order không biết, Order không thể tự sắp xếp đúng.

**Phân trang (pagination):** Chọn một phần liên tục của kết quả đã lọc và sắp xếp. Một page chỉ có nghĩa khi filter và sort đã được xác định.

Thứ tự logic:

~~~text
Identify authorized universe
      ↓
Join/derive fields needed by predicates
      ↓
Apply all required filters
      ↓
Establish total order
      ↓
Select page or continuation
      ↓
Optionally enrich display-only fields
      ↓
Return response and cursor
~~~

Tối ưu hóa có thể đẩy một số bước xuống nguồn riêng hoặc chuyển sang index, nhưng **không được thay đổi semantics**. Trường nào chỉ dùng hiển thị thì có thể enrich sau pagination; trường quyết định filter hoặc sort thì không thể đơn giản bổ sung sau khi page đã chọn.

## 3. Offset pagination trong một nguồn

Ví dụ truy vấn Order với createdAt thuộc Order:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE tenant_id = :tenant_id
  AND status = 'CONFIRMED'
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 40;
~~~

### Ưu điểm

- Dễ triển khai và giải thích: page 1, page 2, page 3.
- Có thể nhảy đến trang cụ thể.
- Phù hợp với tập dữ liệu nhỏ/tương đối tĩnh và query index có thể đáp ứng SLO.

### Hạn chế

- Offset sâu có thể đắt vì DB cần xác định/skip nhiều records.
- Nếu bản ghi mới được chèn lên đầu hoặc bản ghi trước đó bị xóa, page offset sau có thể lặp hoặc bỏ item.
- OFFSET 40 trên Order khác hoàn toàn OFFSET 40 trên tập Order kết hợp Payment.
- Với kết quả nhiều nguồn, cộng offset cục bộ không tạo vị trí toàn cục.

Ví dụ, khi trang 1 đã lấy Orders 1–20, một Order mới được thêm phía trước. Trang 2 OFFSET 20 có thể bắt đầu bằng Order 20 cũ: một item được lặp. Đây là đặc tính của vị trí tương đối trong tập đang thay đổi, không phải chỉ là lỗi lập trình.

## 4. Keyset/seek pagination

Thay vì bỏ qua số dòng cố định, dùng khóa cuối trang trước:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE tenant_id = :tenant_id
  AND status = 'CONFIRMED'
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at
           AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Query mẫu trên dùng cả createdAt và orderId theo thứ tự DESC. Đây là **keyset cursor**: trang kế tiếp là các bản ghi đứng sau vị trí xác định trong total order.

### Ưu điểm

- Thường tốt cho infinite scroll và dữ liệu lớn với index phù hợp.
- Chèn record mới trước cursor ít làm shift vị trí đã xem.
- Không cần duyệt từ đầu để skip offset rất sâu.
- Cursor là một continuation token có thể mang metadata và snapshot context.

### Giới hạn

- Khó nhảy trực tiếp tới trang thứ 500 nếu chưa có điểm neo.
- Nếu sort key của record thay đổi, item có thể di chuyển qua cursor, gây lặp/bỏ item trong live view.
- Không tự đảm bảo snapshot bất biến.
- Cursor cần giữ đủ thông tin để tái tạo đúng filter, sort, tenant scope và phiên bản contract.

### 4.1. Thứ tự phải toàn phần và duy nhất

~~~sql
ORDER BY created_at DESC
~~~

không đủ nếu nhiều orders trùng createdAt. Database có thể thay đổi thứ tự các dòng trùng khóa giữa hai lần query. Nên có tie-breaker:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Trong tập nhiều nguồn có local IDs trùng nhau, có thể dùng:

~~~text
GlobalSortKey = (
    createdAt DESC,
    sourceId ASC,
    entityId ASC
)
~~~

Comparator phải quy định rõ NULLS FIRST/LAST, timezone, collation, case/accent rules và kiểu dữ liệu. Một timestamp lấy từ nhiều máy không mặc nhiên tạo causal order tuyệt đối giữa các events.

## 5. Vì sao phân trang ở từng nguồn rồi merge sai?

Giả sử hai nguồn trả records giảm dần:

~~~text
Nguồn A:
A1 (12:00)
A2 (11:58)
A3 (11:55)
A4 (11:30)

Nguồn B:
B1 (11:59)
B2 (11:57)
B3 (11:56)
B4 (11:20)

Global:
A1, B1, A2, B2, B3, A3, A4, B4
~~~

Với pageSize=3:

- Trang 1 đúng: A1, B1, A2.
- Trang 2 đúng: B2, B3, A3.

Nếu lấy page=2,size=3 ở cả A và B, ta nhận A4 và B4, thiếu toàn bộ phần tử đầu của trang 2 thật.

### 5.1. Kể cả over-fetch cũng có giới hạn

Có thể fetch 30 hoặc 100 items từ mỗi nguồn để có nhiều ứng viên hơn. Nhưng “lấy gấp 5 lần page size” chỉ là heuristic:

- Một nguồn có thể chứa hàng nghìn items mới hơn nguồn khác.
- Filter có thể loại 99,9% candidates.
- Một số items có quyền truy cập không hợp lệ và phải loại.
- Sort key có thể không có trong nguồn đang paginate.
- Cần xử lý trùng entity từ nhiều nguồn.
- Khi page sâu, số records phải xét có thể không có giới hạn nhỏ.

Over-fetch có thể giảm round trips, nhưng không tự chứng minh pagination đúng cho mọi query.

## 6. Global sorting: chọn nơi có đủ dữ liệu

### 6.1. Sort do owner chính quản lý

Nếu API trả Orders theo Order.createdAt, Order có thể lọc và phân trang đúng theo các field của mình; Query API sau đó enrich tên khách hàng và trạng thái thanh toán **chỉ để hiển thị**.

~~~mermaid
sequenceDiagram
    participant U as UI
    participant Q as Query API
    participant O as Order
    participant P as Payment
    participant C as Customer
    U->>Q: List Orders theo createdAt
    Q->>O: Filter + keyset pagination
    O-->>Q: 20 Orders + cursor
    par Enrichment song song
        Q->>P: Batch payment statuses
        P-->>Q: Payment statuses
    and
        Q->>C: Batch customer names
        C-->>Q: Customer names
    end
    Q-->>U: 20 Orders theo thứ tự gốc
~~~

**Điều kiện:** Payment status và customer name không ảnh hưởng membership/order của query này. Nếu cần filter paymentStatus=PAID hoặc sort customerName, phải thiết kế khác.

### 6.2. Sort thuộc Payment

Nếu client yêu cầu sort=-paidAt, Order Service không thể tự lấy top 20 theo paidAt nếu không có field được đồng bộ/index theo contract. Có thể:

- Dùng Payment làm driving source, trả orderIds theo paidAt rồi join Order; vẫn cần áp Order filters và quyền.
- Xây read model chứa paidAt và order fields cần thiết.
- Chạy distributed join/materialization theo request, thường đắt và khó đảm bảo SLO.
- Giới hạn tính năng sort nếu chưa có kiến trúc hỗ trợ đúng.

### 6.3. Sort theo giá trị tổng hợp

Ví dụ sort theo netRevenue = capturedPayments - refunds. Định nghĩa netRevenue có thể thuộc Reporting/Finance. Để tìm top N toàn cục, cần tính cho **mọi ứng viên phù hợp** hoặc duy trì chỉ mục/materialization. Chỉ tính netRevenue cho 20 items đã lấy là sai về top N.

### 6.4. Sort monetary values

Sort totalAmount giữa nhiều currency cần quy tắc chuyển đổi hoặc lọc currency. Không so sánh 100 VND và 100 USD bằng giá trị số thuần. Cần amount, currency, FX rate semantics và thời điểm tỷ giá phù hợp.

### 6.5. Stable sorting across versions

Khi đổi collation, timezone interpretation hoặc cách tính field trong triển khai mới, cursor từ schema cũ có thể trở nên không tương thích. Cursor cần version và cơ chế xử lý index generation/schema generation.

## 7. Filter pushdown và truy vấn liên nguồn

**Filter pushdown** nghĩa là đưa một predicate xuống nguồn có thể đánh giá hiệu quả bằng index, thay vì truyền toàn bộ dữ liệu lên aggregator rồi lọc.

Ví dụ các điều kiện thuộc Order:

~~~text
tenantId = T-5
createdAt >= 2026-11-01
status = CONFIRMED
~~~

hãy để Order lọc trong database. Lợi ích gồm ít bytes truyền, ít memory ở query layer, giảm fan-out và tận dụng index.

Nhưng với:

~~~text
Order.status = CONFIRMED
AND Payment.status = PAID
AND Customer.segment = LOYAL
AND Catalog.category = ELECTRONICS
~~~

không một service riêng nào có đủ tất cả field. Có thể đẩy từng phần predicate xuống nguồn, nhưng cần một nơi xác định membership cuối cùng.

### 7.1. Driving source

Nếu Payment.status=PAID rất hiếm, bắt đầu với tập payment orderIds có thể hiệu quả. Nếu Order date range chỉ có 30 records còn Payment có hàng triệu, bắt đầu với Order hợp lý hơn. Quyết định phụ thuộc selectivity, cardinality, index, network cost, quyền dữ liệu và tần suất query.

Không chọn driving source chỉ dựa trên tên service hoặc một ước lượng cố định: data distribution theo tenant có thể rất khác nhau.

### 7.2. Cross-service filtering khó vì thiếu snapshot

Order được đọc lúc T1 và Payment tại T2. Một đơn có thể đổi trạng thái giữa T1/T2. Query layer đang tạo một mixed-time view nếu không có cơ chế snapshot liên miền.

Đối với dashboard, mixed-time/best-effort có thể chấp nhận. Với báo cáo kiểm toán yêu cầu ảnh chụp nhất quán, có thể cần materialization, checkpoint hoặc cơ chế phối hợp mạnh hơn.

### 7.3. Nên lọc khi nào?

- **Trước phân trang:** Mọi field quyết định item có thuộc kết quả không.
- **Trước hoặc trong sắp xếp:** Mọi field quyết định order của kết quả.
- **Sau phân trang:** Chỉ những field không ảnh hưởng membership/order và dùng để enrich hiển thị.

Điều kiện bảo mật là một phần của universe hợp lệ, không thể xem nhẹ như một display filter.

## 8. Ba lựa chọn kiến trúc

### A. Owner pagination + display-only enrichment

Order lọc, sắp xếp và tạo cursor; Query API gọi Payment/Customer để bổ sung thông tin hiển thị.

**Phù hợp khi:**

- Filter và sort nằm ở Order.
- Số items mỗi trang có giới hạn.
- Enrichment có batch APIs hoặc cache đúng.
- Display-only source failure có partial display contract.

**Không phù hợp khi:** Payment, Customer hoặc Catalog quyết định filter/sort. Post-filtering sau owner page làm sai membership.

### B. Live fan-out và sorted-stream merge

Query API gọi nhiều nguồn, mỗi nguồn trả một stream đã sort theo **cùng comparator** và có local cursor. Query API merge thành global order.

**Phù hợp khi:**

- Nguồn chia partition/region cho cùng loại entity;
- Mỗi nguồn có sort key tương thích;
- Số nguồn giới hạn;
- Query volume và data size cho phép fan-out;
- Contract chấp nhận failure/freshness semantics được xác định.

**Khó khi:**

- Sort key khác nhau giữa nguồn;
- Filter liên miền cần nhiều joins;
- Deep pagination;
- Quá nhiều nguồn/cursor state;
- Nhiều instances đồng thời thay đổi dữ liệu.

### C. Materialized read model/search index

Các domain phát events hoặc thay đổi qua cơ chế chuẩn; Projection Builder duy trì document/row chứa các field dùng cho search. API query một index có thể filter/sort/page toàn cục.

**Phù hợp khi:**

- Filter/sort trải nhiều bounded contexts;
- Full-text search, facets và aggregate counts;
- Query volume cao;
- Cần latency ổn định;
- Có đội vận hành projection/replay;
- Eventual consistency chấp nhận được cho đường đọc.

**Đánh đổi:** Read model trễ so với nguồn, phải xử lý event trùng/sai thứ tự, index rebuild, schema evolution, quyền dữ liệu và retention.

### Bảng so sánh

| Tiêu chí | Owner + enrichment | Live merge | Read model |
|---|---|---|---|
| Filter/sort của một owner | Rất phù hợp | Có thể nhưng thừa | Phù hợp nếu đã có |
| Filter theo nhiều domains | Không đủ nếu chỉ enrich | Có thể đắt | Thường phù hợp |
| K-way merge dữ liệu cùng schema | Không bắt buộc | Phù hợp | Phù hợp |
| Query latency | Thường khá tốt nếu batch | Phụ thuộc nhiều sources | Tối ưu bằng index |
| Dữ liệu mới | Gần source | Nguồn đọc khác thời điểm | Eventual, cần lag metadata |
| Chi phí vận hành | Thấp hơn | Truy vấn phức tạp | Cần pipeline/index |
| Partial failure | Enrichment có thể tùy chọn | Có thể ảnh hưởng global page | Query vẫn chạy khi producer lỗi nếu index có sẵn |
| Cursor toàn cục | Owner quản lý | Cần per-source state | Index quản lý |
| Reporting/export | Giới hạn | Có thể đắt | Phù hợp hoặc tạo snapshot job |
| Security | Owner auth + Query layer | Nhiều nguồn phải tuân policy | Index ACL/cache phải đúng |

## 9. K-way merge trên sorted streams

Giả sử A, B, C đều cung cấp entity với cùng global sort key:

~~~text
A: A1(100), A2(97), A3(91)
B: B1(99),  B2(98), B3(90)
C: C1(101), C2(96), C3(95)
~~~

Thứ tự toàn cục:

~~~text
C1(101), A1(100), B1(99), B2(98),
A2(97), C2(96), C3(95), A3(91), B3(90)
~~~

Với pageSize=4, trang đầu là C1, A1, B1, B2. Trang kế tiếp phải bắt đầu A2, C2, C3, A3.

### 9.1. Thuật toán khái niệm

1. Fetch candidate head của mỗi nguồn theo cursor của nguồn đó.
2. Đưa các heads vào priority queue với **global comparator**.
3. Chọn phần tử đứng đầu toàn cục.
4. Áp những predicate/ACL còn cần xử lý, dedup theo entity grain nếu cần.
5. Đánh dấu phần tử đã được **tiêu thụ** trong tiến trình nguồn tương ứng.
6. Nạp phần tử tiếp theo của nguồn đó.
7. Lặp tới pageSize items hợp lệ hoặc hết các nguồn.
8. Tạo cursor có đủ per-source positions và state cho các candidates chưa tiêu thụ.

Độ phức tạp CPU của k-way merge khi streams đã sort vào khoảng O(n log k) cho n phần tử được xét và k nguồn. Nhưng latency thực phụ thuộc network, batch sizes, errors, filtering, dedup và timeouts.

### 9.2. Lỗi quan trọng: fetch khác consume

Giả sử hệ thống fetch 3 items từ mỗi nguồn, tổng 9 items, nhưng chỉ xuất 4. Nếu nextCursor ghi vị trí **cuối batch đã fetch** ở A/B/C, các items chưa xuất A2, A3, C2, C3 có thể biến mất khỏi các trang sau.

Các cách đúng:

- Lưu **lastConsumedPosition** theo mỗi nguồn; request sau refetch từ vị trí đã thực sự tiêu thụ.
- Hoặc lưu buffer chứa candidates đã fetch nhưng chưa tiêu thụ trong server-side cursor state, kèm vị trí tiếp theo và TTL.
- Nếu một candidate bị loại vì filter hoặc dedup, cần cập nhật trạng thái xử lý có quy tắc rõ để không lặp vô hạn.

**Không được đánh dấu các ứng viên chưa được xem là đã tiêu thụ chỉ vì chúng nằm trong batch HTTP nhận về.**

### 9.3. Phải có comparator tương thích

Một nguồn sort theo createdAt, nguồn khác sort theo paidAt, nguồn thứ ba sort theo displayName không thể merge heads thành một global ordering có ý nghĩa mà không tính lại key. Mỗi stream phải sắp theo **cùng tổng thứ tự** hoặc được materialize rồi sort lại theo tiêu chí chung.

### 9.4. Khi cần chứng minh hasNext

Với nguồn đơn giản, fetch pageSize+1 có thể cho biết còn item tiếp. Nhưng với filter cross-service, phần tử thứ pageSize+1 thô có thể bị filter loại. Để trả hasNext=true/false chính xác, query phải tìm được ít nhất một **item hợp lệ kế tiếp** hoặc chứng minh mọi nguồn đã hết theo semantics.

Nếu quá deadline chưa thể biết, phải có error/partial/unknown contract; không tự trả false chỉ vì upstream chưa phản hồi.

## 10. Cursor đa nguồn

Cursor đơn nguồn có thể chỉ chứa last sort key. Cursor liên nguồn có thể cần:

~~~json
{
  "version": 2,
  "queryFingerprint": "hash-of-normalized-filters-and-sort",
  "subjectScope": "tenant-T5",
  "sort": ["createdAt:desc", "sourceId:asc", "entityId:asc"],
  "sourcePositions": {
    "region-a": {"lastConsumed": ["2026-11-11T10:00:00Z", "region-a", "A-10"]},
    "region-b": {"lastConsumed": ["2026-11-11T09:59:00Z", "region-b", "B-21"]}
  },
  "snapshotRef": "optional-snapshot-id",
  "expiresAt": "2026-11-11T10:30:00Z"
}
~~~

Đây chỉ là dữ liệu logic để giải thích. Cursor public nên là **opaque token**, có integrity protection (ví dụ server ký), không để client tự chỉnh query positions. Nếu chứa dữ liệu nhạy cảm, có thể mã hóa hoặc giữ state phía server, chỉ trả opaque ID.

### 10.1. Các ràng buộc quan trọng

- Cursor phải gắn với normalized filters, sort, tenant/identity scope và version.
- Nếu đổi filter/sort, phải bắt đầu trang đầu hoặc từ chối cursor cũ.
- Cursor có TTL; khi hết hạn trả lỗi contract rõ.
- Cursor ký không thay thế authentication/authorization hiện tại.
- Nếu có index generation hoặc snapshot ID, cần kiểm validity sau rollout/rebuild.
- Khi có nhiều nguồn, giữ chính xác vị trí đã tiêu thụ và những items còn buffer.
- Giới hạn kích thước cursor: không nhồi hàng nghìn documents vào HTTP header hoặc query string.

### 10.2. Stateful và stateless cursor

**Stateless:** Token chứa positions và metadata được ký/mã hóa nếu cần. Ít phụ thuộc store riêng nhưng token có thể lớn.

**Stateful:** Server lưu source positions, snapshot handles và pending buffers theo opaque session ID. Token nhỏ hơn nhưng cần cache/store bền phù hợp, TTL, cleanup, HA, xử lý session loss.

Nếu cursor state mất, không nên giả vờ tiếp tục chính xác. Trả CURSOR_EXPIRED hoặc lỗi phù hợp và yêu cầu client bắt đầu query mới.

### 10.3. Cursor không cấp quyền

Một token pagination hợp lệ chỉ thể hiện vị trí và điều kiện của truy vấn. Nếu nhân viên bị thu hồi quyền xem Customer hoặc đổi tenant giữa hai trang, truy vấn tiếp phải kiểm quyền lại. Không coi cursor cũ là capability vô thời hạn.

## 11. Concurrent writes và nhất quán giữa trang

Dữ liệu liên tục thay đổi:

- Một Order mới chèn lên đầu danh sách;
- Order bị hủy/xóa;
- Payment chuyển từ PENDING sang PAID;
- Customer đổi segment;
- Product đổi category;
- Một event đến projection muộn.

### 11.1. Live best-effort pagination

Mỗi page đọc dữ liệu tại thời điểm request. Keyset hạn chế vấn đề offset shift do insert phía trước, nhưng không đảm bảo mọi item xuất hiện đúng một lần khi **sort key hoặc membership thay đổi**.

Phù hợp với feeds/dashboard chấp nhận cập nhật động; UI có thể có nút refresh và thông báo dữ liệu đang thay đổi.

### 11.2. Snapshot pagination

Trang đầu thiết lập một point-in-time view; các trang sau tham chiếu cùng snapshot trong thời hạn hợp lệ. Điều này giúp giữ tập kết quả ổn định **trong phạm vi snapshot có hiệu lực**, nhưng có chi phí retention, session state hoặc transaction/index snapshot.

Không gọi một keyset cursor bình thường là “snapshot” nếu không có hạ tầng thực sự giữ snapshot.

### 11.3. Snapshot liên dịch vụ khó hơn

Một snapshot của Order không đóng băng Payment hoặc Customer. Đọc Order lúc 10:00:01 và Payment lúc 10:00:03 tạo một mixed-time view. Để có consistent snapshot liên miền cần cơ chế đồng bộ versions/checkpoints hoặc materialization tại một mốc hợp lệ.

Phần lớn dashboard không cần distributed strong snapshot; **eventual-consistent read model với metadata freshness** có thể phù hợp, nhưng phải ghi rõ bảo đảm thực tế.

### 11.4. Stable export

Nếu người dùng cần một danh sách phục vụ kiểm toán hoặc export nhiều triệu records, có thể tạo **async report job**:

~~~text
POST /reports/orders-export → 202 Accepted + jobId
Worker materializes query result at documented asOf
GET /reports/{id}/status
Download immutable export artifact when complete
~~~

Một export snapshot có thể dễ đảm bảo tính nhất quán nội bộ hơn so với deep interactive pagination liên tục trên các nguồn đang biến động. Tuy nhiên snapshot này vẫn có giới hạn freshness tùy dữ liệu nguồn.

### 11.5. Read-your-writes

Nếu user vừa tạo Order O-101 và list index chưa thấy vì projection lag, UI có thể hiển thị kết quả create command hoặc GET riêng O-101 từ Order owner. Không tự giả định index đã cập nhật; cũng không dùng list stale để ra quyết định Refund/Payment.

## 12. Materialized read model và CQRS

Một read model cho query có thể chứa:

~~~text
OrderSearchDocument:
    tenantId
    orderId
    customerId
    customerName
    customerSegment
    orderStatus
    createdAt
    paymentStatus
    paidAt
    productCategories[]
    totalAmount
    currency
    projectionVersion
    indexedAt
~~~

### 12.1. Luồng cập nhật

~~~mermaid
sequenceDiagram
    participant O as Order
    participant P as Payment
    participant C as Customer
    participant K as Catalog
    participant B as Event Bus
    participant X as Projection Builder
    participant R as Read Index
    O->>B: OrderCreated
    P->>B: PaymentAuthorized
    C->>B: CustomerSegmentChanged
    K->>B: ProductCategoryChanged
    B->>X: Deliver events
    X->>X: Dedup, order/version checks, join policy
    X->>R: Upsert document
~~~

Read model là bản sao phục vụ truy vấn; **không thay nguồn sự thật** của Order, Payment, Customer, Catalog.

### 12.2. Event đến sai thứ tự

PaymentAuthorized có thể đến trước OrderCreated do lag/retry. Projection cần chính sách:

- Tạo partial document rồi cập nhật sau?
- Giữ event pending đến khi có Order?
- Reconcile với source API?
- Dùng aggregate version để tránh áp event cũ?
- Đánh dấu missing data và theo dõi stuck projections?

**Event đã nhận không có nghĩa tất cả field đều đầy đủ để đưa vào kết quả tìm kiếm.** Nếu index thiếu Payment status, phải xác định filter PAID có coi là false, unknown hay pending. Đó là contract.

### 12.3. Historical hay current attributes?

Khách hàng đổi segment từ NEW sang LOYAL. Với danh sách orders lịch sử, filter segment có nghĩa:

- Segment **hiện tại** của khách hàng?
- Segment **tại thời điểm đặt hàng**?

Tương tự category của sản phẩm có thể thay đổi sau khi đơn đã đặt. Một search index phải định nghĩa cách cập nhật các Orders liên quan hoặc lưu snapshot của thuộc tính theo thời điểm, không chỉ sao chép field mà không có semantics.

### 12.4. CQRS không bắt buộc event sourcing

CQRS tách read model và write model khi nhu cầu khác nhau. Projection cập nhật qua events là một phương án. Event sourcing lưu chuỗi event như nguồn sự thật của aggregate, là lựa chọn storage sâu hơn và không bắt buộc để xây query index.

### 12.5. Backfill và rebuild

Khi schema search đổi, cần cách:

- Rebuild từ nguồn dữ liệu hợp lệ hoặc event history;
- Chạy idempotent upsert;
- Dùng version/generation;
- Theo dõi backlog và projection lag;
- Đảm bảo replay không làm trạng thái quay về phiên bản cũ;
- Đối chiếu count/checksum khi phù hợp;
- Chuyển alias/index generation có kế hoạch;
- Xử lý cursor đang tham chiếu index cũ;
- Tôn trọng dữ liệu xóa và privacy retention.

## 13. Full-text, facets và relevance sorting

Khi cần tìm tên khách hàng/sản phẩm, category, status và các facets, search engine hoặc RDBMS với index phù hợp có thể giúp thực hiện filter/sort/pagination trên một tập dữ liệu tổng hợp.

### 13.1. Relevance score

Sort theo search relevance khác sort theo createdAt. Điểm số có thể thay đổi khi index cập nhật, scoring statistics thay đổi, hoặc documents được thêm/xóa. Với deep pagination cần snapshot/PIT và unique tie-breaker nếu engine hỗ trợ. Không giả định relevance score là khóa bất biến.

### 13.2. Deep pagination

Một số search engines giới hạn deep OFFSET/from+size hoặc có chi phí cao. Có thể dùng search_after/cursor và point-in-time theo khả năng của nền tảng. Export số lượng lớn thường phù hợp async job hơn là UI kéo liên tiếp hàng trăm nghìn trang.

### 13.3. Facet counts

Count theo category/paymentStatus/region phải áp cùng tenant và ACL filter như items. Không tiết lộ số records của những tenants khác qua facets. Counts có thể là exact, approximate hoặc lower bound; API phải công bố rõ.

### 13.4. Normalization

Text search có thể khác nhau theo Unicode normalization, bỏ dấu tiếng Việt, case folding, stemming và tokenization. Filter theo tên An có thể match “An”, “Ân” hoặc chuỗi dài hơn tùy analyzer. Không gọi “contains” là cùng nghĩa trên mọi nguồn nếu analyzer khác nhau.

## 14. Total count và hasNext

Một API danh sách có thể trả:

~~~json
{
  "pageInfo": {
    "hasNextPage": true,
    "nextCursor": "opaque-cursor",
    "totalCount": 8731,
    "totalCountRelation": "EXACT"
  }
}
~~~

**Exact count** chỉ đúng theo tập kết quả, filter, ACL và thời điểm/snapshot đã định. Với kết quả phân tán, count có thể tốn kém; đếm toàn bộ records của Order và Payment rồi cộng lại là sai nếu có join hoặc duplicates.

Các lựa chọn:

- **EXACT:** Có bằng chứng tổng chính xác trong phạm vi snapshot/query.
- **APPROXIMATE:** Giá trị ước lượng, cần giải thích sai số/semantics nếu công khai.
- **GTE/lower-bound:** Tổng ít nhất N, không phải N chính xác.
- **UNKNOWN:** Không trả count; dùng hasNext và nextCursor.

### 14.1. hasNext không chỉ là raw buffer còn phần tử

Nếu filter liên nguồn loại phần lớn records, việc còn candidate ở một nguồn không chứng minh còn item **thỏa toàn bộ filter**. Để khẳng định hasNext, phải tìm được item hợp lệ tiếp theo hoặc có chứng cứ index đã xác định.

Nếu một nguồn bắt buộc lỗi, không được trả hasNext=false như thể toàn bộ tập kết quả đã duyệt xong.

### 14.2. Đừng làm API đắt chỉ để hiển thị “Page 1 of 10.000”

UI có thể dùng infinite scroll và không hiển thị totalCount nếu chính xác total count quá tốn kém. Với nhu cầu xuất báo cáo/count thật, có thể cung cấp endpoint/jobs riêng hoặc approximate count theo contract.

## 15. Hợp đồng API đề xuất

~~~http
GET /api/orders/search?limit=20&sort=-createdAt,orderId&status=CONFIRMED&paymentStatus=PAID
Authorization: Bearer <access-token>
Accept: application/json
~~~

Response minh họa:

~~~json
{
  "items": [
    {
      "orderId": "O-101",
      "createdAt": "2026-11-11T10:00:00Z",
      "orderStatus": "CONFIRMED",
      "paymentStatus": "PAID",
      "customer": {"id": "C-7", "displayName": "An Nguyen"}
    }
  ],
  "pageInfo": {
    "pageSize": 20,
    "hasNextPage": true,
    "nextCursor": "opaque-signed-cursor"
  },
  "sort": [
    {"field": "createdAt", "direction": "DESC"},
    {"field": "orderId", "direction": "ASC"}
  ],
  "consistency": {
    "mode": "EVENTUAL",
    "indexedAt": "2026-11-11T09:59:55Z"
  }
}
~~~

### 15.1. Field contract

| Thành phần | Quy tắc |
|---|---|
| limit/pageSize | Default, min/max, không cho caller kéo vô hạn |
| sort | Whitelist field và direction, luôn có tie-breaker |
| filters | Kiểu dữ liệu, operators, null, timezone, normalization rõ |
| cursor | Opaque, integrity-protected, versioned, expires, bound to query |
| hasNext | Được tính từ tập đã filter/authorized, không phải raw upstream page |
| totalCount | Exact/approx/unknown semantics |
| consistency | LIVE_BEST_EFFORT, SNAPSHOT hoặc EVENTUAL theo thiết kế |
| indexedAt/asOf | Thể hiện độ mới khi liên quan |
| errors | Invalid cursor, expired cursor, unsupported filter, timeout, partial source |
| tenant | Lấy từ identity đã xác thực và policy |
| correlationId | Truy vết mà không lộ secrets/PII |

### 15.2. Whitelist filter/sort

Không đưa input sort của user làm SQL fragment trực tiếp. Server cần mapping từ tên API field đã duyệt tới query builder có parameterization.

~~~json
{
  "allowedSortFields": ["createdAt", "orderId", "paidAt", "totalAmount"],
  "allowedFilters": {
    "status": ["EQ", "IN"],
    "createdAt": ["GTE", "LT"],
    "paymentStatus": ["EQ", "IN"],
    "customerName": ["CONTAINS"]
  }
}
~~~

Giới hạn số điều kiện, IN-list size, query length, date span, page size, number of sort fields và overall query timeout. Không cho caller nhúng SQL hoặc search DSL tùy ý vào public API.

### 15.3. Filter semantics khó cần ghi rõ

- NULL paymentStatus nghĩa là chưa có attempt, unknown hay not applicable?
- Một Order có nhiều payment attempts, status nào là final?
- Sắp xếp tên theo locale nào, có phân biệt dấu tiếng Việt không?
- Ngày 01/11 theo timezone user hay UTC?
- Category ở thời điểm bán hay category hiện tại?
- Currency có được so sánh lẫn nhau không?
- Khi một dòng xuất hiện trong nhiều nguồn, dùng global entity ID nào để dedup?
- Một order có 5 lines thì trả 1 row/order hay 5 rows/line?

**Entity grain phải được xác định** trước pagination, nếu không join one-to-many có thể nhân bản items và làm count sai.

## 16. Authorization là một filter bắt buộc

Mọi page phải được tính trong phạm vi records caller được phép đọc.

Nếu Query API lấy 20 Orders toàn công ty rồi lọc bỏ những Orders của tenant khác, client có thể nhận 2 items dù tenant mình còn nhiều Orders nằm sau. Thậm chí total count hoặc timing có thể lộ thông tin về tenants khác.

Một mô hình đúng:

~~~text
effectiveFilter =
    authenticatedTenantScope
    AND resourceAccessPolicy
    AND userRequestedFilters
~~~

Ràng buộc cần nằm ở query boundary trước pagination, và các owner vẫn kiểm business authorization nơi cần thiết.

### 16.1. Cursor không cấp quyền

Dù cursor được server ký, mỗi request phải xác thực danh tính, tenant và quyền **hiện tại**. Không cho user lấy cursor của tenant A rồi dùng với token của tenant B.

### 16.2. Cache theo người dùng/tenant

Cache key phải bao gồm hoặc phân biệt identity/permission scope, filter, sort, cursor/snapshot và index version theo semantics. Không cache shared kết quả nhạy cảm chỉ theo URL khi nhiều tenants có cùng query string.

### 16.3. Search index chứa PII

Một projection có thể sao chép tên, email, số điện thoại, địa chỉ. Phải có data minimization, masking, ACL, retention, delete propagation và audit. Index dễ query không có nghĩa mọi field đều được phép expose.

### 16.4. Thay đổi quyền giữa các lần lấy trang

Một user bị thu hồi quyền có thể đã có cursor và dữ liệu cũ trên UI. Server phải không tiếp tục tiết lộ dữ liệu sau khi quyền không còn hiệu lực. Nếu ACL đồng bộ qua event, cần xem độ trễ quyền có chấp nhận được không; với dữ liệu nhạy cảm có thể phải recheck owner/policy thay vì chỉ dùng projection stale.

## 17. Partial failure và semantics của API

Một Query API fan-out đến Order, Payment, Customer, Catalog có thể gặp timeout ở một dependency.

### 17.1. Required source

Nếu Payment.status là filter bắt buộc, không nhận dữ liệu Payment thì không chứng minh được các Orders trả ra có thỏa PAID hay không. Thường cần trả lỗi hoặc partial semantics được công bố rõ, **không trả complete success**.

### 17.2. Optional enrichment

Nếu Customer.displayName chỉ để hiển thị và không dùng filter/sort, có thể trả null/unavailable với cờ phù hợp khi Customer timeout, giữ nguyên danh sách Orders và cursor từ owner.

### 17.3. Partial response

Một hệ thống có thể trả:

~~~json
{
  "items": [],
  "partial": true,
  "unavailableSources": ["region-b"],
  "pageInfo": {
    "hasNextPage": null,
    "nextCursor": null
  }
}
~~~

Đây là contract ví dụ, không phải chuẩn bắt buộc. Nhiều sản phẩm nên fail fast với lỗi rõ hơn là trả một danh sách thiếu nhưng nhìn như đầy đủ. Nếu partial page được hỗ trợ, UI phải nhận biết và không tuyên bố “không còn kết quả”.

### 17.4. Overall deadline và retry

Khi SLO API là 800 ms, không cấp 800 ms riêng cho từng trong 5 lời gọi tuần tự. Cần overall deadline, parallelism có giới hạn, per-dependency timeout và request budgets.

GET có thể idempotent, nhưng nhiều tầng retry khi source chậm vẫn gây overload. Không để Gateway, aggregator và SDK đều retry ba lần ngoài kiểm soát.

## 18. N+1 calls, batching và bounded concurrency

Ví dụ một page có 20 orders:

~~~text
1 Order list call
20 Payment calls
20 Customer calls
40 Catalog calls
= 81 network calls
~~~

Nếu mỗi call có latency nhỏ nhưng tail latency lớn, 81 calls có thể gây p99 xấu và tăng tải đáng kể.

### 18.1. Batch APIs

Ví dụ:

~~~http
POST /internal/payments/by-order-ids
Content-Type: application/json

{"orderIds":["O-100","O-101","O-102"]}
~~~

Batch API cần quy định max IDs, thứ tự output, item missing, lỗi từng ID, auth/tenant scope, semantics khi một order có nhiều payment attempts và timeout.

### 18.2. Dedup trước batch

Nếu 20 orders chỉ có 4 distinct customerIds, Query API nên batch get 4 customers thay vì 20 calls. Cache cần tôn trọng TTL, permission và privacy.

### 18.3. Bounded concurrency

Có thể gọi Payment/Customer/Catalog song song, nhưng không tạo 1.000 in-flight requests không giới hạn. Dùng semaphore/bulkhead/connection pool limit và theo dõi resource saturation.

### 18.4. Batch endpoint không phải cửa hậu

Service sở hữu dữ liệu phải duy trì authorization. Không thiết kế batch get để caller nội bộ bất kỳ đọc toàn bộ Payment table mà không có kiểm soát.

## 19. Index và schema cho read model

Ví dụ schema quan hệ phục vụ tìm kiếm:

~~~sql
CREATE TABLE order_search (
  tenant_id VARCHAR(64) NOT NULL,
  order_id VARCHAR(64) NOT NULL,
  created_at TIMESTAMP NOT NULL,
  order_status VARCHAR(32) NOT NULL,
  payment_status VARCHAR(32),
  paid_at TIMESTAMP,
  customer_id VARCHAR(64) NOT NULL,
  customer_name VARCHAR(256),
  customer_segment VARCHAR(32),
  total_amount DECIMAL(18, 2),
  currency VARCHAR(3),
  indexed_at TIMESTAMP NOT NULL,
  PRIMARY KEY (tenant_id, order_id)
);
~~~

Index minh họa:

~~~sql
CREATE INDEX idx_order_search_created
ON order_search (tenant_id, order_status, created_at DESC, order_id DESC);

CREATE INDEX idx_order_search_paid
ON order_search (tenant_id, payment_status, paid_at DESC, order_id DESC);
~~~

Tên kiểu và syntax có thể khác theo DB. Index phù hợp createdAt không nhất thiết tối ưu paidAt, totalAmount hoặc full-text search. Khi mở thêm sort/filter fields, phải xét write amplification, storage, selectivity, query plans và SLO.

### 19.1. One-to-many join

Một order có nhiều products hoặc payment attempts. Nếu query một dòng trên mỗi order line, pagination 20 rows có thể chỉ gồm 5 orders duy nhất. Cần xác định **entity grain** và semantics aggregation, ví dụ một document/order có productCategories[] và latestSuccessfulPaidAt.

### 19.2. Projection là bản sao

Order, Payment, Customer, Catalog vẫn là owner. Read model chỉ giữ những field cần cho search. Không cho nhiều domain cùng ghi trực tiếp vào projection rồi coi nó là nguồn sự thật.

### 19.3. Projection reconciliation

Có thể đối chiếu số documents, version/watermarks, độ trễ và sample records với owners. Rebuild cần duy trì quyền dữ liệu, event schema evolution, duplicate handling và cursor behavior qua index generation.

## 20. Java ví dụ: API owner dùng keyset cursor

Một port minh họa:

~~~java
import java.time.Instant;
import java.util.List;

public record OrderSortKey(Instant createdAt, String orderId) {}

public record OrderFilter(
        String tenantId,
        Instant fromInclusive,
        Instant toExclusive,
        String orderStatus
) {}

public record OrderPageRequest(
        OrderFilter filter,
        OrderSortKey after,
        int limit
) {}

public record OrderSummary(
        String orderId,
        String customerId,
        Instant createdAt,
        String orderStatus
) {}

public record OrderPage(
        List<OrderSummary> items,
        OrderSortKey lastKey,
        boolean hasNextPage
) {}

public interface OrderQueryPort {
    OrderPage list(OrderPageRequest request);
}
~~~

Application service dùng port để yêu cầu Order filtering/sorting mà Order có trách nhiệm. Adapter HTTP/DB triển khai SQL keyset và tạo opaque cursor ở API layer.

Các yếu tố cần bổ sung khi triển khai thật: authenticated tenant context, validate limit, null handling, index, structured errors, logging không lộ thông tin nhạy cảm, snapshot semantics và token integrity.

### 20.1. Java pseudocode cho enrichment

~~~text
getOrdersPage(query, principal):
    safeFilter = normalizeAndAuthorize(query.filter, principal)
    orderPage = orderQuery.list(safeFilter, query.cursor, query.limit)

    customerIds = distinct(orderPage.items.customerId)
    orderIds = orderPage.items.orderId

    paymentData = paymentBatchGet(orderIds)
    customerData = customerBatchGet(customerIds)

    result = enrichWithoutChangingMembershipOrGlobalOrder(
        orderPage.items, paymentData, customerData
    )

    return result, orderPage.nextCursor
~~~

**Không áp dụng pseudocode này nếu Payment/Customer dùng để lọc hoặc sort**, trừ khi filter/sort đã được owner/index phản ánh đúng trước khi page selection.

## 21. Java pseudocode cho multi-source merge

~~~text
Input:
  size, normalizedQuery, cursor,
  sortedSources S1..Sk with the same comparator

state = validateAndLoadCursor(cursor, normalizedQuery)
for each source:
    open stream from state.lastConsumedPosition[source]
    load first candidate if available

priorityQueue = one head from each nonempty stream
result = []

while result.size < size:
    if priorityQueue empty:
        break

    candidate = pop globally smallest-or-largest head
    advance only the consumed position for candidate.source

    if candidate passes filters, authorization and dedup:
        result.add(candidate)

    load next candidate from that same source
    push it into priorityQueue when available

build continuation:
    preserve unconsumed fetched candidates
    or ensure next call resumes from consumed watermark
    include any required snapshot, filter, sort and identity bindings

return result and validated continuation metadata
~~~

Khi filter rất ít chọn lọc, thuật toán có thể cần xét nhiều hơn pageSize records để đủ một trang. Phải có query budget, không fetch vô hạn. Nếu budget hết trước khi xác định kết quả, trả failure/partial semantics rõ.

### 21.1. Cursor per-source đã tiêu thụ

Phân biệt:

- **Fetched:** Item đã được kéo về memory.
- **Considered:** Item đã được đưa qua comparator và filter.
- **Emitted:** Item được đưa vào response.
- **Consumed cursor:** Watermark mà từ đó lần sau có thể tiếp tục mà không bỏ items chưa xét.

Một item đã xét nhưng bị loại bởi filter có thể được coi là consumed theo logic query đã định. Một item mới chỉ fetch thì **không** được bỏ qua. Nếu dùng server-side buffer, positions và buffers phải cùng một phiên bản state.

## 22. Một use case end-to-end: Orders search

### 22.1. Yêu cầu

Support UI cần filter orderStatus, paymentStatus, customerSegment và productCategory; sort createdAt hoặc paidAt; pageSize=25; tenant isolation; search latency ổn định; Payment nghiệp vụ phải chính xác khi thao tác refund.

### 22.2. Thiết kế gợi ý

Chọn **Orders Query Service + materialized search index**, vì các filter/sort thuộc nhiều contexts:

~~~mermaid
flowchart TD
    UI["Support UI"] --> G["API Gateway"]
    G --> Q["Orders Query API"]
    Q --> IDX[("Orders Search Index")]
    O["Order"] --> EV["Domain Events / Outbox"]
    P["Payment"] --> EV
    C["Customer"] --> EV
    K["Catalog"] --> EV
    EV --> X["Projection Builder"]
    X --> IDX
    Q -->|Business decision recheck| O
    Q -->|Payment action recheck| P
~~~

### 22.3. Ownership

- Gateway: authentication, API quota và routing.
- Query API: validate query, auth scope, cursor, cost budget và response contract.
- Projection builder: event handling, idempotency, joins, versions, backfill.
- Search index: filter/sort/paginate theo một tập document.
- Order/Payment/Customer/Catalog: nguồn sự thật và business invariants.
- UI: hiển thị freshness, đổi filter thì restart pagination, xử lý cursor expiry.

### 22.4. API response

~~~http
GET /api/orders/search?limit=25&sort=-paidAt,orderId&paymentStatus=PAID
Authorization: Bearer <access-token>
~~~

~~~json
{
  "items": [
    {
      "orderId": "O-201",
      "paymentStatus": "PAID",
      "paidAt": "2026-11-11T10:12:00Z",
      "customerName": "An Tran"
    }
  ],
  "pageInfo": {
    "hasNextPage": true,
    "nextCursor": "opaque-cursor",
    "totalCountRelation": "UNKNOWN"
  },
  "dataFreshness": {
    "consistency": "EVENTUAL",
    "indexedAt": "2026-11-11T10:11:57Z"
  }
}
~~~

**Hợp đồng:** Search index có độ trễ. Khi nhân viên bấm Refund, Payment service phải xác minh trạng thái thực và authorization; không dùng paymentStatus trong một read model có thể stale để thực hiện giao dịch.

### 22.5. Thay đổi filter/sort

Khi user đổi từ sort=-paidAt sang sort=-createdAt, UI phải bỏ cursor cũ và bắt đầu truy vấn mới. Backend từ chối cursor gắn với query fingerprint cũ.

### 22.6. Khi Payment event bị chậm

Sau PaymentAuthorized, Order vẫn có thể xuất hiện với paymentStatus=PENDING trong index một lúc. API nêu indexedAt; nếu UX cần read-your-writes, có thể overlay trạng thái nhận từ command result hoặc GET theo orderId tại owner.

## 23. Metrics và observability

### 23.1. Query API

| Metric | Ý nghĩa |
|---|---|
| p50/p95/p99 latency theo route và loại query | Trải nghiệm và SLO |
| Requests/s và concurrency | Năng lực |
| Query plan/cost và scanned records | Tìm truy vấn đắt |
| PageSize thực tế, deep cursor usage | Đặc tính pagination |
| Fan-out calls/query và bytes transferred | Chi phí liên dịch vụ |
| Upstream timeouts/errors | Độ ổn định composition |
| Cache hit/miss | Lợi ích và nguy cơ cache |
| Cursor invalid/expired | Hạn chế UX và rollout |
| Partial-result rate | Tình huống source lỗi |
| Count query duration | Chi phí exact count |

### 23.2. Projection

- Consumer lag, oldest event age;
- Event delivery attempts/DLQ;
- Projection indexedAt delay;
- Failed joins hoặc partial documents;
- Duplicate/out-of-order events;
- Rebuild progress, index generation;
- Chênh lệch dữ liệu khi đối soát với owners;
- Document update throughput và index storage.

### 23.3. Logging/tracing

Trace query nên liên kết requestId, normalized query shape, route, source calls, index generation và consistency mode. Tránh log raw access token, dữ liệu PII hoặc query chứa email/số điện thoại ngoài chính sách. Không đưa orderId/customerId thành metric label cardinality lớn.

### 23.4. Business outcome

Gateway/API response nhanh không có nghĩa search đúng. Cần kiểm thêm tỷ lệ duplicates/missing trên các kiểm thử tham chiếu, freshness SLO và quyền dữ liệu. Những metric này có thể đòi synthetic tests, sampling/reconciliation và kiểm chứng contract định kỳ.

## 24. Performance và capacity

### 24.1. Latency budget minh họa

~~~text
Gateway overhead:                  20 ms
Order list query:                 110 ms
Payment batch enrichment:        120 ms
Customer batch enrichment:       100 ms
Serialization/response:           25 ms
Reserve/variance budget:          75 ms
Illustrative total sequential:   450 ms
~~~

Đây là ví dụ, không phải SLA mặc định. Payment và Customer có thể chạy song song nếu độc lập, nhưng tổng latency vẫn phụ thuộc nhánh chậm nhất cùng overhead. Phải đo p95/p99 với traffic thật.

### 24.2. Fan-out amplification

Một public search tạo 4 upstream calls: 1.000 searches/s tạo khoảng 4.000 calls/s, chưa tính retry. Nếu mỗi item lại gọi một API riêng, số calls tăng theo pageSize. Cần batch, cache đúng, bounded concurrency và policy tránh quá tải owner services.

### 24.3. Index chọn theo workload

Index cho (tenantId, orderStatus, createdAt) không mặc nhiên phục vụ sort paidAt hoặc filter full-text tốt. Thêm index tăng storage và write amplification. Dùng query explain, thống kê selectivity và benchmark dữ liệu thực để chọn.

### 24.4. Very large queries

Nếu user muốn export 2 triệu Orders với nhiều joins, nên dùng async job/snapshot và download artifact theo TTL/permission, không kéo qua hàng trăm nghìn HTTP pages có cursor lâu sống.

### 24.5. Query budget

Giới hạn:

- Page size và số filter clauses;
- Số sort fields và field whitelist;
- Độ dài full-text query và IN lists;
- Khoảng ngày tối đa nếu cần;
- Nguồn fan-out và số batch requests;
- Overall query deadline;
- Per-tenant concurrency;
- Deep pagination;
- Memory và CPU budget của aggregator;
- Count query hoặc expensive facets.

Khi quá giới hạn, trả lỗi contract rõ hoặc chuyển sang job, không lặng lẽ truncate kết quả rồi tuyên bố đầy đủ.

## 25. Anti-pattern thường gặp

**1. Mỗi service lấy page 2 rồi merge.** Local positions không biểu diễn global position.

**2. Lấy 20 Orders trước rồi filter Payment.** Loại records sau pagination làm trang thiếu.

**3. Sort chỉ 20 records đã fetch theo paidAt.** Không chứng minh là top 20 toàn cục.

**4. Chỉ ORDER BY createdAt.** Khi timestamp trùng, thứ tự có thể đổi; cần unique tie-breaker.

**5. Cursor dùng lastFetched thay lastConsumed.** Bỏ qua ứng viên chưa được xét/trả.

**6. OFFSET sâu cho mọi trường hợp.** Chi phí cao và nhạy concurrent insert/delete.

**7. Gọi keyset là snapshot.** Keyset không tự đóng băng source hoặc sort key.

**8. Tiếp tục cursor sau khi đổi filter/sort.** Positions thuộc query cũ.

**9. TotalCount bằng tổng count nhiều nguồn.** Có thể đếm trùng hoặc không áp global filters.

**10. Mixed-time joins nhưng mô tả “strongly consistent”.** Thiếu snapshot coordination.

**11. Coi projection là dữ liệu mới nhất tuyệt đối.** Eventual lag có thể làm filter kết quả chậm.

**12. Query index dùng làm source of truth để refund.** Business decision phải kiểm owner.

**13. N+1 synchronous HTTP calls không giới hạn.** Tail latency và downstream load tăng.

**14. Cache không gắn tenant/ACL.** Có nguy cơ lộ dữ liệu giữa tenants.

**15. Thực thi ACL sau page selection.** Trang thiếu và có thể tiết lộ thông tin qua count/timing.

**16. Sort tiền khác currency bằng numeric field.** Sai semantics nghiệp vụ.

**17. Một order nhiều lines bị trả thành nhiều items vô ý.** Entity grain/count sai.

**18. Search relevance sort mà không có snapshot/tie-breaker.** Kết quả thay đổi giữa pages.

**19. Cho user gửi raw SQL/sort expression.** Injection và query cost khó kiểm soát.

**20. Silent partial page khi một source bắt buộc timeout.** Client hiểu sai completeness.

**21. Dùng quá nhiều index cho mọi tổ hợp filter tùy ý.** Write amplification và vận hành tăng.

**22. Không có event dedup/ordering trong projection.** Data status có thể quay ngược.

**23. Không có cursor version/snapshot expiration.** Cursor cũ không tương thích sau rebuild.

**24. Tối ưu performance mà bỏ correctness.** Response nhanh nhưng thiếu hoặc lặp records không đáp ứng yêu cầu.

## 26. Kiểm thử tính đúng đắn

### 26.1. Tập dữ liệu tĩnh

Tạo bộ dữ liệu nhỏ từ A, B, C với sort keys xen kẽ, có khóa trùng timestamp và global tie-breaker. Tính expected global result độc lập.

Kiểm:

1. Page 1, 2, 3 nối lại đúng global order.
2. Không duplicates, không missing items.
3. Source rỗng vẫn hoạt động.
4. Một source có toàn bộ top-ranked items.
5. Filter loại 90% items vẫn xử lý đúng.
6. Dedup cùng entity ID từ hai nguồn.
7. Buffered records không bị mất khi chuyển cursor.
8. pageSize=1, pageSize=max và page cuối ít hơn limit.
9. hasNext phản ánh item hợp lệ tiếp theo.
10. Query filter thay đổi khiến cursor cũ bị từ chối.

### 26.2. Concurrent updates

1. Insert item mới trước cursor giữa hai trang.
2. Xóa item đã xem.
3. Update sort key của item sang phía trước cursor.
4. Payment.status chuyển PENDING → PAID.
5. CustomerSegmentChanged cập nhật projection chậm.
6. Event out-of-order và duplicate.
7. Snapshot/cursor hết hạn.
8. Index generation đổi khi rollout.

Đánh giá theo mức consistency đã cam kết. Một live feed không có snapshot có thể không hứa hoàn hảo khi records thay đổi; nhưng không được khẳng định bảo đảm mạnh mà kiến trúc không cung cấp.

### 26.3. Auth/security

1. Cursor tenant A dùng với identity tenant B.
2. Quyền user bị thu hồi giữa các trang.
3. API bị query với invalid field/operator.
4. Query có IN list quá lớn hoặc wildcard text quá rộng.
5. Cache trả nhầm kết quả user khác.
6. Index chứa field PII không được cấp quyền.
7. Count/facet tiết lộ dữ liệu ngoài tenant.
8. Source failure không được che thành complete success.

### 26.4. Reliability/performance

1. Payment timeout khi chỉ là display enrichment.
2. Payment timeout khi là required filter.
3. One source trả 429/503.
4. Overall deadline hết.
5. Burst 1.000 searches/s.
6. Một tenant có hàng triệu orders.
7. Deep pagination hoặc export nhiều records.
8. Projection lag dài và event replay.
9. Query index rebuild hoặc failover.
10. Connection pools và bounded fan-out bị saturation.

## 27. Bài thực hành: tìm kiếm Orders liên domain

**Bài toán:** Hệ thống có Order, Payment, Customer, Catalog. UI cần 25 đơn/trang, filter theo date, orderStatus, paymentStatus, customerSegment, productCategory; sort theo createdAt hoặc paidAt.

### Bước 1 — Xác định semantics

Viết một bảng gồm entity grain, mỗi field và owner, kiểu/filter operator, null semantics, global sort key, tenant/ACL, freshness expectation, page size, count semantics và response contract.

### Bước 2 — Chứng minh cách sai

Tạo 50 Orders, trong đó chỉ một phần nhỏ thỏa PAID. Lấy 20 Orders đầu rồi filter PAID. So sánh với kết quả lọc PAID trên toàn bộ tập trước rồi lấy 20. Chỉ ra items bị bỏ và hasNext sai.

### Bước 3 — Mô phỏng k-way merge

Tạo ba sorted lists A/B/C xen kẽ, pageSize=4. Viết pseudocode merge. Lưu per-source lastConsumedPosition sau page 1. Truy vấn page 2 và chứng minh không bỏ candidates đã fetch nhưng chưa xuất.

### Bước 4 — Thiết kế ba phương án

- Order owner pagination + enrichment;
- Live query với distributed join/merge;
- Materialized projection/index từ events.

So sánh correctness, latency, consistency, cost, observability, operation ownership và mức phức tạp.

### Bước 5 — Thiết kế API và cursor

Tạo request/response mẫu có filter, sort, nextCursor, hasNext, consistency/asOf và lỗi INVALID_CURSOR/EXPIRED. Mô tả cách ký cursor, gắn với tenant và query fingerprint.

### Bước 6 — Projection design

Xác định events và schema tài liệu. Thiết kế cách xử lý duplicate, out-of-order, missing Order khi PaymentAuthorized đến trước, customerSegment hiện tại hay lịch sử, rebuild và lag metrics.

### Bước 7 — Failure injection

Mô phỏng Payment timeout, index stale, cursor expiry, tenant switch, event duplicate, index generation change và một source không phản hồi. Với mỗi trường hợp, ghi expected response và lý do.

### Bước 8 — Load test và ADR

Đo p95/p99, query cost, fan-out amplification, index lag, error và deep pagination. Viết ADR chọn giải pháp hợp lý cho workload. Nêu rõ các guarantee thực sự có và các giới hạn chấp nhận.

**Đầu ra:** Bảng ownership/filter, global comparator, API/cursor contract, sơ đồ kiến trúc, test cases và ADR.

## 28. Mẫu ADR

~~~text
Title: Cross-Service Orders Search and Pagination

Context:
- Entity grain and owners:
- Consumers and use cases:
- Required filter fields:
- Required sort fields:
- Authorization and tenant scope:
- Consistency/freshness expectation:
- Latency and query volume SLO:

Alternatives:
A. Owner pagination + enrichment
B. Live fan-out/merge
C. Materialized read model
D. Snapshot/export job for heavy queries

Decision:
- Query API owner:
- Selected architecture:
- Filter pushdown:
- Global comparator and tie-breaker:
- Pagination type:
- Cursor state and expiry:
- Snapshot/freshness semantics:
- Total count and hasNext semantics:
- Security/ACL:
- Partial failure policy:
- Query budgets/timeouts:
- Projection replay/reconciliation:
- Observability and test strategy:

Consequences:
- Benefits:
- Correctness guarantees:
- Known limitations:
- Cost/operational burden:
- Risks and mitigation:
- Revisit conditions:
~~~

## 29. Câu hỏi ôn tập

1. Vì sao không được lấy page N của A và B rồi coi đó là page N của A∪B?
2. Tại sao thứ tự logic phải là lọc trước, sắp xếp sau, rồi chọn trang?
3. Khi nào có thể bổ sung CustomerName sau khi đã phân trang Orders?
4. Vì sao filter Payment.status sau khi lấy 20 Orders đầu có thể sai?
5. OFFSET có rủi ro gì khi dữ liệu được chèn/xóa giữa hai requests?
6. Keyset pagination giúp giảm vấn đề nào và không giải quyết vấn đề nào?
7. Vì sao createdAt cần tie-breaker orderId?
8. Nếu nhiều nguồn có local IDs trùng nhau, global key nên thêm thành phần gì?
9. K-way merge cần điều kiện gì về sort comparator của từng stream?
10. Vì sao lastFetchedPosition khác lastConsumedPosition?
11. Khi filter loại phần lớn candidates, hasNext có thể khó xác định ra sao?
12. Cursor phải gắn với filter/sort/tenant bằng cách nào?
13. Vì sao cursor ký hợp lệ không cấp quyền truy cập vô thời hạn?
14. Khi nào một database snapshot không tạo snapshot toàn hệ thống?
15. Projection lag ảnh hưởng kết quả tìm kiếm PAID như thế nào?
16. Khi PaymentAuthorized đến trước OrderCreated, projection xử lý ra sao?
17. CustomerSegment nên là hiện tại hay tại thời điểm đặt hàng?
18. Vì sao computed totalProfit cần materialization khi sort top N?
19. Exact total count khác approximate và unknown thế nào?
20. Facet counts có thể làm lộ dữ liệu cross-tenant ra sao?
21. Vì sao N+1 calls làm latency/availability xấu đi?
22. Batch APIs cần authorization và item-level error semantics gì?
23. Vì sao index cho createdAt không đủ cho mọi sort field?
24. Search relevance score có thể làm cursor đổi hành vi giữa trang ra sao?
25. Khi nào nên dùng async export thay deep pagination?
26. Những trường hợp nào nên trả partial response?
27. Nếu một required source timeout, vì sao không được trả complete success?
28. Một order có nhiều payment attempts làm entity grain phức tạp ra sao?
29. Tại sao không dùng stale projection trực tiếp để thực hiện Refund?
30. Bạn sẽ chọn architecture nào nếu yêu cầu chỉ sort Order.createdAt nhưng display CustomerName?
31. Bạn chọn gì nếu cần full-text filter CustomerName và sort Payment.paidAt trên hàng triệu Orders?
32. Làm sao kiểm thử pagination không lặp/bỏ trên tập dữ liệu tĩnh?
33. Với dữ liệu thay đổi, phải ghi rõ consistency contract nào?
34. Tại sao data freshness metadata có thể quan trọng đối với UX?
35. Những chỉ số nào chứng minh query layer không gây overload các domain owners?

## 30. Checklist trước khi triển khai

- [ ] Xác định rõ entity grain, owner và kiểu dữ liệu của từng field.
- [ ] Có một tập kết quả logic với filter và authorization áp trước page selection.
- [ ] Global sort là total order có unique tie-breaker.
- [ ] Không merge page N của từng nguồn như thể đó là page N toàn cục.
- [ ] Chỉ enrich sau pagination nếu enrichment không thay đổi membership/order.
- [ ] Đẩy filters tới owner/index khi có thể, không phá semantics.
- [ ] Sort theo field liên domain được thực hiện trên đủ ứng viên hoặc trong projection.
- [ ] Live merge dùng cùng comparator và đủ per-source cursor state.
- [ ] Không advance cursor qua những candidates chỉ mới fetch.
- [ ] Cursor có version, TTL, integrity, query fingerprint và tenant scope.
- [ ] Mỗi request tiếp theo vẫn kiểm tra quyền hiện tại.
- [ ] Consistency mode được công bố: LIVE, SNAPSHOT hoặc EVENTUAL.
- [ ] Không gọi keyset cursor là snapshot nếu không có snapshot thực.
- [ ] Projection có event dedup, versioning, rebuild, reconciliation và lag metrics.
- [ ] Search result hiển thị indexedAt/asOf nếu freshness có tác động.
- [ ] Facet/count semantics rõ: exact, approximate, lower-bound hoặc unknown.
- [ ] hasNext phản ánh các records hợp lệ sau global filter.
- [ ] Required source failure không bị che thành complete result.
- [ ] Query có page size, filter/sort whitelist, timeout và cost budget.
- [ ] Batch APIs, bounded concurrency và connection pools giảm N+1 calls.
- [ ] Không cache thiếu tenant/ACL hoặc cursor/snapshot context.
- [ ] Read model không thay thế source of truth của các domain.
- [ ] Business action quan trọng được xác minh lại tại owner.
- [ ] Đã thử static dataset, concurrent writes, duplicate event và cursor expiry.
- [ ] Đã đo p95/p99 latency, fan-out, deep pagination cost và projection lag.
- [ ] Có ADR mô tả lựa chọn, rủi ro, trade-off và điều kiện xem xét lại.

**Kết luận:** Phân trang, sắp xếp và lọc trên dữ liệu nhiều nguồn chỉ có ý nghĩa khi hệ thống xác định được **membership và global ordering**. Nếu filter/sort thuộc một domain, phân trang ở domain owner rồi enrich hiển thị là đủ và đơn giản. Với sorted streams tương thích, dùng k-way merge và cursor theo vị trí đã tiêu thụ. Với filter/sort liên miền, volume lớn và nhiều kiểu tìm kiếm, **materialized read model/search index** thường thực tế hơn, nhưng phải quản lý eventual consistency, ACL, replay và freshness. Dù chọn cách nào, correctness của cursor, authorization, count, partial failures và query cost là một phần bắt buộc của **hợp đồng API**, không phải chi tiết phụ có thể bỏ qua.