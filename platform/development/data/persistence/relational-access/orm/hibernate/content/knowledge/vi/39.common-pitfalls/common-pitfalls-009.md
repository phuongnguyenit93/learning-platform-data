# Dùng fetch join nhiều tập hợp mà không đo số hàng tăng

Hibernate cho phép tải association cùng entity gốc bằng JPQL/HQL fetch join. Kỹ thuật này rất hữu ích để tránh N+1 queries: thay vì tải danh sách đơn hàng rồi chạy thêm một SELECT cho từng collection, ứng dụng có thể lấy đơn hàng và collection trong cùng một câu SQL.

Vấn đề xuất hiện khi một truy vấn fetch join **nhiều association dạng to-many cùng lúc**. Mỗi collection có thể có nhiều phần tử cho một entity gốc. Khi các collection được JOIN trong cùng result set, số hàng SQL có thể tăng theo tích số phần tử của chúng. Một màn hình cần 100 đơn hàng, 800 dòng hàng, 300 khoản thanh toán và 400 nhãn có thể khiến database trả về hàng nghìn hàng lặp lại thông tin đơn hàng và các phần tử liên quan.

Đây là lỗi hiệu năng khó nhận ra nếu chỉ nhìn số câu SQL. Một câu SQL duy nhất có thể tạo ra result set khổng lồ, truyền nhiều dữ liệu qua mạng và buộc Hibernate xử lý rất nhiều hàng để dựng lại một object graph nhỏ hơn nhiều.

Bài thuộc chương **Lỗi thường gặp** của Data Persistence Relational Access ORM Hibernate. Mục tiêu là biết khi nào fetch join nhiều collection làm tăng số hàng, cách đo cardinality thực tế, và cách chọn fetch plan giữ được lợi ích tránh N+1 mà không tạo Cartesian multiplication ngoài ý muốn.

---

## 1. Fetch join giải quyết vấn đề gì?

Giả sử có hai entity:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;
}
~~~

Nếu tải 100 đơn hàng rồi truy cập collection lines:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
    "select o from PurchaseOrder o order by o.id",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder order : orders) {
    int count = order.getLines().size();
}
~~~

Với lazy loading mặc định, ứng dụng có thể phát:

~~~text
1 SELECT purchase_orders
100 SELECT order_lines WHERE order_id = ?
------------------------------------------
101 SQL statements
~~~

Đây là dạng N+1. Fetch join một collection có thể giải quyết:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    order by o.id
    """, PurchaseOrder.class)
    .getResultList();
~~~

SQL khái quát:

~~~sql
SELECT o.id, ..., l.id, ...
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
ORDER BY o.id;
~~~

Thay vì một query cho orders và nhiều query cho lines, database thực thi một join và trả result set chứa orders cùng line data.

**Fetch join một collection thường là lựa chọn hợp lý khi số phần tử và lượng dữ liệu trả về được kiểm soát.** Điều đó không có nghĩa fetch join càng nhiều association thì càng tốt.

## 2. Vì sao nhiều collection làm số hàng tăng theo phép nhân?

Giả sử entity Order có ba collection độc lập:

~~~java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

@OneToMany(mappedBy = "order")
private List<Payment> payments;

@ManyToMany
@JoinTable(name = "order_tags")
private Set<Tag> tags;
~~~

Một query fetch đồng thời:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    left join fetch o.payments
    left join fetch o.tags
    where o.organizationId = :organizationId
    """, PurchaseOrder.class)
    .setParameter("organizationId", organizationId)
    .getResultList();
~~~

SQL join khái quát:

~~~sql
SELECT o.*, l.*, p.*, t.*
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
LEFT JOIN payments p ON p.order_id = o.id
LEFT JOIN order_tags ot ON ot.order_id = o.id
LEFT JOIN tags t ON t.id = ot.tag_id
WHERE o.organization_id = ?;
~~~

Đối với một order có 8 lines, 3 payments và 4 tags, SQL join có thể tạo:

\[
8 \times 3 \times 4 = 96
\]

hàng cho **một order**.

Mỗi hàng chứa thông tin order, một line, một payment và một tag. Hibernate phải đọc các hàng này và ghép chúng thành một object graph với 1 order, 8 lines, 3 payments và 4 tags.

### 2.1. Công thức ước lượng

Với entity gốc thứ \(i\), giả sử có \(k\) collection được LEFT JOIN FETCH. Gọi \(c_{ij}\) là số phần tử của collection thứ \(j\) trên root \(i\).

Số hàng join gần đúng:

\[
R_i \approx \prod_{j=1}^{k}\max(1,c_{ij})
\]

Tổng số hàng:

\[
R \approx \sum_{i=1}^{N}
\prod_{j=1}^{k}\max(1,c_{ij})
\]

Dùng max(1, c) vì LEFT JOIN vẫn tạo ít nhất một hàng cho root khi collection rỗng. Đây là mô hình ước lượng cho các join độc lập; predicates, association filters, duplicate link rows và quan hệ phụ thuộc có thể làm cardinality thực tế khác đi.

### 2.2. Ví dụ định lượng

Giả sử có 100 orders, trung bình mỗi order có:

| Collection | Số phần tử trung bình |
| --- | ---: |
| Lines | 8 |
| Payments | 3 |
| Tags | 4 |

Nếu các collection đều có phần tử, số hàng join ước lượng:

\[
100 \times 8 \times 3 \times 4 = 9.600
\]

Trong khi số object nghiệp vụ duy nhất gần đúng chỉ là:

- 100 orders.
- 800 lines.
- 300 payments.
- 400 tags.

Tổng cộng 1.600 entity instances khác nhau, nhưng result set có 9.600 rows. Các thông tin bị lặp lại theo từng tổ hợp line-payment-tag.

Nếu một order có 20 lines, 8 payments và 12 tags, riêng order đó có thể tạo:

\[
20 \times 8 \times 12 = 1.920
\]

rows.

**Average cardinality có thể che mất một vài parent rất lớn.** Khi điều tra, đo cả median, p95, p99 và maximum số phần tử mỗi collection trên từng root, không chỉ lấy trung bình toàn bảng.

### 2.3. Collection rỗng vẫn tạo hàng

Với LEFT JOIN, order không có payment vẫn xuất hiện. Trong phép ước lượng, collection rỗng được tính như một nhánh có một hàng null-extended:

~~~text
Order A: lines=8, payments=0, tags=4
Rows ≈ 8 × max(1,0) × 4 = 32
~~~

Nếu dùng INNER JOIN FETCH thay cho LEFT JOIN FETCH, các root không có association tương ứng có thể bị loại khỏi kết quả. Đây là khác biệt về semantics dữ liệu, không chỉ tối ưu hiệu năng.

## 3. Hình dung Cartesian multiplication

~~~mermaid
flowchart TD
    O["Order #42"] --> L["8 lines"]
    O --> P["3 payments"]
    O --> T["4 tags"]
    L --> X["SQL join tạo tổ hợp"]
    P --> X
    T --> X
    X --> R["8 × 3 × 4 = 96 rows"]
    R --> H["Hibernate ghép lại object graph"]
    H --> G["1 Order + 8 Lines + 3 Payments + 4 Tags"]
~~~

Join không tạo ra 96 orders nghiệp vụ. Nó tạo 96 **combinations of joined rows** để biểu diễn ba collection cùng lúc.

Đây là lý do số hàng trong SQL result set và số entity instances trong persistence context là hai đại lượng khác nhau.

## 4. Phân biệt to-one và to-many fetch join

Không phải mọi fetch join đều làm số hàng tăng theo phép nhân.

### 4.1. To-one association

Ví dụ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToOne(fetch = FetchType.LAZY)
private ShippingAddress shippingAddress;
~~~

Mỗi order tham chiếu tối đa một customer và một shipping address theo cardinality mapping. JOIN các association to-one này thường không nhân số hàng theo số phần tử con.

Fetch đồng thời một collection và vài to-one associations thường có row count gần bằng collection fetch đó, mặc dù số columns và payload mỗi row tăng.

### 4.2. To-many association

~~~java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

@ManyToMany
private Set<Tag> tags;
~~~

Mỗi root có thể có nhiều rows ở phía collection. Mỗi to-many join mới có thể nhân số rows đã có.

### 4.3. Bảng so sánh

| Fetch pattern | Tác động row count điển hình |
| --- | --- |
| Một root + nhiều to-one | Thường giữ một row trên mỗi root nếu joins không tạo duplicate ngoài mapping |
| Root + một to-many | Tăng theo số phần tử collection |
| Root + hai to-many | Tăng theo tích cardinality hai collection |
| Root + ba to-many | Tăng theo tích cardinality ba collection |
| Một to-many + nhiều to-one của root/child | Không nhất thiết nhân thêm rows, nhưng tăng payload/columns |
| Nhiều to-many có quan hệ phụ thuộc | Vẫn có thể tăng mạnh; cần đo SQL thực tế |

Lưu ý: dữ liệu sai constraint, join table có duplicate links hoặc custom join predicates có thể tạo nhiều rows hơn cardinality mà object model dự kiến.

## 5. Một query SQL có thể tệ hơn nhiều query nhỏ

Giả sử có 100 orders, 8 lines và 3 payments trung bình.

### Phương án A: một query fetch cả hai collection

~~~sql
SELECT o.*, l.*, p.*
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
LEFT JOIN payments p ON p.order_id = o.id
WHERE o.organization_id = ?;
~~~

Ước lượng 100 × 8 × 3 = 2.400 rows.

### Phương án B: ba query riêng

~~~sql
SELECT o.*
FROM purchase_orders o
WHERE o.organization_id = ?;

SELECT l.*
FROM order_lines l
JOIN purchase_orders o ON o.id = l.order_id
WHERE o.organization_id = ?;

SELECT p.*
FROM payments p
JOIN purchase_orders o ON o.id = p.order_id
WHERE o.organization_id = ?;
~~~

Số rows truyền về xấp xỉ:

~~~text
100 orders + 800 lines + 300 payments = 1.200 rows
~~~

Phương án B có ba round-trips thay vì một, nhưng chỉ truyền khoảng một nửa số rows trong ví dụ. Với RTT thấp và payload lớn, ba query có thể nhanh hơn một query join khổng lồ. Với RTT rất cao, cần cân nhắc batching hoặc fetch plan khác.

**Mục tiêu không phải giảm số SQL xuống mức thấp nhất bằng mọi giá. Mục tiêu là tối ưu tổng chi phí: round-trips + database work + bytes truyền + hydration + memory.**

## 6. Chi phí của row multiplication

### 6.1. Database execution

Database phải thực hiện joins, tạo combinations, xử lý sort/distinct nếu có, và đọc các columns cần thiết. Query planner có thể chọn hash join, nested loop hoặc merge join tùy statistics và indexes.

### 6.2. Network transfer

Mỗi joined row lặp lại columns của root và các association. Nếu root có nhiều text/JSON columns, payload tăng đáng kể dù ứng dụng chỉ cần một bản root object.

### 6.3. JDBC processing

Driver phải decode từng row, chuyển dữ liệu theo protocol và cung cấp ResultSet cho Hibernate. Một result set hàng trăm nghìn rows tạo overhead ngay cả khi database execution plan nhìn có vẻ nhanh.

### 6.4. Hibernate hydration và collection assembly

Hibernate phải đọc từng hàng, xác định entity identities, tái sử dụng entity instances trong persistence context, nhận diện collection elements đã thấy và dựng association state. Row duplication làm tăng công việc xử lý.

### 6.5. Memory và garbage collection

Persistence context có thể giữ entity/collection state; query result có thể giữ root references; driver có thể buffer rows tùy fetch mode. Payload lớn cũng tạo thêm allocation và GC pressure.

### 6.6. Một SQL statement không có nghĩa ít công việc

Số statement là một metric cần thiết để phát hiện N+1, nhưng không đủ để đánh giá fetch plan. Phải đo thêm số rows, bytes, unique roots, unique children và thời gian xử lý ở từng tầng.

## 7. Vì sao DISTINCT không xóa row explosion?

Một query thường được viết:

~~~jpql
select distinct o
from PurchaseOrder o
left join fetch o.lines
left join fetch o.payments
~~~

SQL rows có columns khác nhau:

~~~text
order_id | line_id | payment_id
---------+---------+-----------
42       | 1       | 10
42       | 1       | 11
42       | 2       | 10
42       | 2       | 11
~~~

Các hàng này khác nhau vì line_id/payment_id khác nhau. SQL DISTINCT không thể gộp chúng thành một row mà vẫn giữ đủ child data để Hibernate hydrate cả hai collections.

Hibernate có thể loại duplicate root entity references khi dựng kết quả entity query. Hành vi deduplication khác nhau theo Hibernate generation; Hibernate 6 đã tự loại duplicate root entity result do join fetch trong nhiều trường hợp, trong khi code legacy thường dùng JPQL DISTINCT. Tuy nhiên, việc deduplicate root objects **không xóa số rows database đã trả và Hibernate đã phải đọc**.

Vì vậy:

- DISTINCT có thể giúp danh sách root entity không lặp.
- DISTINCT không giải quyết Cartesian multiplication.
- DISTINCT có thể khiến database phải sort/hash thêm, tùy SQL và plan.
- Không nên dùng DISTINCT như một cách chữa fetch plan quá rộng.

Hãy xem SQL thực tế và Hibernate version thay vì giả định DISTINCT có cùng tác dụng ở mọi lớp.

## 8. MultipleBagFetchException

Hibernate có thể ném lỗi:

~~~text
org.hibernate.loader.MultipleBagFetchException:
cannot simultaneously fetch multiple bags
~~~

Lỗi thường xuất hiện khi một query cố fetch đồng thời nhiều association được Hibernate mapping với bag semantics.

### 8.1. Bag là gì?

Một List không có @OrderColumn thường được Hibernate xem là bag: collection có thể chứa phần tử lặp và không có vị trí persistent được lưu như index. Đây là semantics khác một indexed list.

Ví dụ:

~~~java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

@OneToMany(mappedBy = "order")
private List<Payment> payments;
~~~

Cả hai có thể là bag roles. Fetch join đồng thời có thể bị Hibernate từ chối vì Hibernate không thể xử lý an toàn việc ghép nhiều bag theo cách đó.

### 8.2. Chuyển List thành Set có giải quyết không?

Đổi List thành Set có thể tránh một số trường hợp MultipleBagFetchException vì collection không còn bag semantics. Nhưng SQL vẫn có thể tạo tích rows. Nếu một order có 8 lines và 3 payments, join hai collection vẫn có thể trả 24 rows.

Ngoài ra, Set thay đổi semantics:

- Không giữ duplicate elements theo equals/hashCode.
- Không bảo đảm thứ tự như List.
- Cần thiết kế equals/hashCode ổn định cho entity lifecycle.
- Có thể làm thay đổi API/domain behavior.

**Đừng đổi List thành Set chỉ để dập exception.** Trước tiên quyết định collection semantics đúng với nghiệp vụ; sau đó thiết kế fetch plan để kiểm soát cardinality.

### 8.3. Thêm @OrderColumn có giải quyết không?

`@OrderColumn` biến List thành indexed list theo mapping và có thể thay đổi bag-fetch restriction. Nhưng nó không loại Cartesian multiplication. Nhiều collection to-many được join cùng lúc vẫn có thể tạo số hàng tăng theo tích.

Dùng `@OrderColumn` khi vị trí phần tử là dữ liệu domain cần lưu, không phải như một mẹo performance.

## 9. Pagination kết hợp collection fetch join

Một lỗi phổ biến khác:

~~~java
List<PurchaseOrder> page = entityManager.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    order by o.createdAt desc
    """, PurchaseOrder.class)
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
~~~

Nếu database áp LIMIT 50 trực tiếp trên joined rows, nó có thể cắt giữa collection của một order và không trả đủ lines. Hibernate cần bảo đảm semantics pagination trên root entities, nên với collection fetch join nó thường phải áp dụng pagination trong memory hoặc phát cảnh báo.

### 9.1. Hệ quả

- Database có thể trả toàn bộ joined rows phù hợp.
- Hibernate hydrate nhiều dữ liệu rồi mới cắt page roots.
- P95/P99 tăng khi số root và collection lớn.
- Bộ nhớ ứng dụng tăng.
- Kết quả đúng về root pagination nhưng performance rất tệ.

### 9.2. Cấu hình fail-fast

Trong Hibernate có thể cấu hình:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Khi ứng dụng vô tình kết hợp pagination với collection fetch, cấu hình này giúp fail sớm thay vì âm thầm xử lý trong memory. Tên setting cần xác minh theo Hibernate version của dự án.

### 9.3. Không nhầm pagination root với pagination child

Nếu một page cần 50 orders, việc LIMIT 50 joined rows không tương đương 50 orders. Một order có 20 lines có thể chiếm 20 rows. Pagination phải được xác định trên root IDs trước.

## 10. Đo số rows trước khi chọn fetch plan

Không nên quyết định chỉ từ câu SQL hoặc số statement. Cần đo ít nhất:

- Số root rows.
- Số unique root IDs.
- Số unique elements của mỗi collection.
- Tổng joined result rows.
- Rows per root, đặc biệt p95/p99/max.
- Bytes trả về nếu có telemetry.
- Database execution time và buffers.
- JDBC/client-observed time.
- Hibernate entity/collection load counts.
- Peak heap/allocation nếu workload lớn.

### 10.1. Đếm rows của joined query

Với schema ví dụ:

~~~sql
SELECT COUNT(*) AS joined_rows
FROM purchase_orders o
LEFT JOIN order_lines l
    ON l.order_id = o.id
LEFT JOIN payments p
    ON p.order_id = o.id
LEFT JOIN order_tag_links ot
    ON ot.order_id = o.id
LEFT JOIN tags t
    ON t.id = ot.tag_id
WHERE o.organization_id = :organization_id;
~~~

Đếm root duy nhất:

~~~sql
SELECT COUNT(DISTINCT o.id) AS unique_orders
FROM purchase_orders o
WHERE o.organization_id = :organization_id;
~~~

Đếm unique children theo từng collection riêng:

~~~sql
SELECT COUNT(*)
FROM order_lines l
JOIN purchase_orders o ON o.id = l.order_id
WHERE o.organization_id = :organization_id;
~~~

Làm tương tự cho payments và tags. So sánh joined_rows với unique root/child counts để thấy hệ số nhân.

### 10.2. Ước lượng cardinality trước khi chạy query lớn

Ví dụ PostgreSQL:

~~~sql
SELECT
    percentile_cont(0.50) WITHIN GROUP (ORDER BY line_count) AS p50,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY line_count) AS p95,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY line_count) AS p99,
    MAX(line_count) AS max_lines
FROM (
    SELECT o.id, COUNT(l.id) AS line_count
    FROM purchase_orders o
    LEFT JOIN order_lines l ON l.order_id = o.id
    WHERE o.organization_id = :organization_id
    GROUP BY o.id
) x;
~~~

Với database khác, dùng percentile/analytic functions tương ứng hoặc export phân phối để tính. Đo mỗi collection riêng là bước đầu; sau đó đo joined query thật vì các cardinalities có thể tương quan.

### 10.3. Average không đủ

Giả sử 99 orders có 2 lines nhưng một order có 2.000 lines. Average có thể trông chấp nhận được nhưng request chứa order đặc biệt đó vẫn trả payload rất lớn.

Nếu cardinalities của nhiều collections tương quan (ví dụ order lớn thường có nhiều payments và tags), tích của averages có thể đánh giá thấp tail rows. Cần đo trên các root thực tế và xem phân phối rows per root.

## 11. Dùng EXPLAIN để hiểu database work

Với PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, l.id, p.id, t.id
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
LEFT JOIN payments p ON p.order_id = o.id
LEFT JOIN order_tag_links ot ON ot.order_id = o.id
LEFT JOIN tags t ON t.id = ot.tag_id
WHERE o.organization_id = 'org-42';
~~~

Quan sát actual rows tại các join nodes, loops và rows per loop, join algorithm, shared buffer hits/reads, sort/hash memory và spill, execution time, estimated rows so với actual rows.

### 11.1. Actual rows ở từng node có thể được nhân với loops

Trong EXPLAIN, một node có thể được thực thi nhiều loops. Khi đọc output, hiểu actual rows là số hàng trung bình mỗi loop trong một số format/version; tổng work cần xét cả loops. Đừng chỉ lấy một con số mà bỏ qua nested-loop repetition.

### 11.2. EXPLAIN ANALYZE thực thi query

Với SELECT lớn, nó vẫn tiêu tốn tài nguyên thật. Không chạy query tạo hàng triệu rows vào production giờ cao điểm chỉ để đo. Dùng staging/representative data hoặc giới hạn scope an toàn; EXPLAIN không có ANALYZE cho estimated plan ít tốn tài nguyên hơn nhưng không cho actual rows/time.

### 11.3. Plan không đo toàn bộ Java cost

Database execution time không gồm đầy đủ JDBC decode, network transfer, Hibernate hydration và serialization. Cần so server plan với client-observed query duration và request duration.

## 12. Đo ở JDBC/Hibernate layer

### 12.1. Hibernate Statistics hữu ích nhưng không thay row counter

Có thể bật:

~~~properties
hibernate.generate_statistics=true
~~~

Đọc các counters như:

~~~java
Statistics statistics = sessionFactory.getStatistics();

long queryExecutions = statistics.getQueryExecutionCount();
long entityLoads = statistics.getEntityLoadCount();
long entityFetches = statistics.getEntityFetchCount();
long collectionFetches = statistics.getCollectionFetchCount();
long collectionLoads = statistics.getCollectionLoadCount();
long preparedStatements = statistics.getPrepareStatementCount();
~~~

Các số này giúp hiểu query count và số entity/collection Hibernate load. Chúng **không trực tiếp cho biết số rows JDBC đã đọc**. Statistics thường có scope SessionFactory, nên counters có thể bị request khác làm nhiễu khi ứng dụng chạy đồng thời.

### 12.2. JDBC proxy hoặc instrumentation

Để đo ResultSet rows, có thể dùng JDBC instrumentation/DataSource proxy có khả năng theo dõi số lần `ResultSet.next()` trả true hoặc custom wrapper trong test. Đo cùng SQL fingerprint và request/trace context.

Một bộ đo nên ghi:

~~~text
request_id
sql_fingerprint
execute_elapsed_ms
result_rows_read
result_bytes (nếu driver/telemetry cung cấp)
database_server_time (nếu có)
~~~

Không ghi raw bind values nhạy cảm. Đảm bảo instrumentation không tạo overhead đáng kể hoặc log quá nhiều trong production.

### 12.3. SQL logs chỉ cho biết query shape

Hibernate SQL DEBUG có thể cho thấy join nào được tạo, nhưng một dòng SQL không nói result set có 200 rows hay 2 triệu rows. Kết hợp SQL logging với row counter, DB plan và trace.

### 12.4. Trace spans

Một trace có thể cho thấy một JDBC span rất dài nhưng không giải thích số rows. Nếu instrumentation có attributes rows fetched/returned, dùng chúng; nếu không, thêm metric an toàn ở JDBC boundary. Tránh đưa từng parent ID hoặc tenant ID có cardinality cao vào metrics labels.

## 13. Fetch join một collection, batch fetch các collection còn lại

Đây thường là phương án cân bằng tốt.

Ví dụ cần tải orders cùng lines, payments và tags. Fetch join lines (collection quan trọng nhất) và để hai collection còn lại lazy nhưng batch fetch:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @BatchSize(size = 32)
    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<Payment> payments = new ArrayList<>();

    @BatchSize(size = 32)
    @ManyToMany(fetch = FetchType.LAZY)
    private Set<Tag> tags = new HashSet<>();
}
~~~

Query:

~~~java
List<PurchaseOrder> orders = entityManager.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    where o.organizationId = :organizationId
    order by o.id
    """, PurchaseOrder.class)
    .setParameter("organizationId", organizationId)
    .getResultList();
~~~

Khi code truy cập payments/tags, Hibernate có thể gom nhiều collection owners vào các SELECT theo batch size thay vì một query cho mỗi order.

### 13.1. default_batch_fetch_size

Có thể cấu hình batch fetch mặc định:

~~~properties
hibernate.default_batch_fetch_size=32
~~~

Hoặc dùng annotation `@BatchSize` cho association/entity cụ thể. Batch size phù hợp phụ thuộc DB parameter limits, số owners, driver và workload.

### 13.2. Batch fetch không phải một collection fetch join khổng lồ

Batch fetching thường phát query dạng:

~~~sql
SELECT ...
FROM payments
WHERE order_id IN (?, ?, ?, ...);
~~~

Rows tăng theo tổng phần tử payments của một nhóm orders, không phải tích payments × lines trong cùng result set.

### 13.3. Đánh giá query count sau khi batch

Batch fetching có thể tạo vài query thay vì một query. Đo số batches, số placeholders trong IN, tổng rows, tổng bytes, latency, DB parameter limits và memory. Đừng chọn batch size quá lớn mà không đo.

## 14. Dùng SUBSELECT fetch cho một số collection

Hibernate có `FetchMode.SUBSELECT`:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines;
~~~

Khi một collection được khởi tạo cho một owner trong nhóm entity đã được load bằng query phù hợp, Hibernate có thể tải collection của nhóm owners bằng một secondary query dùng subselect thay vì một query cho mỗi owner.

### 14.1. Khi nào hữu ích?

- Một truy vấn tải một nhóm parent.
- Nhiều parent trong nhóm sẽ cần cùng collection.
- Muốn tránh N+1 mà không join tất cả collection trong một result set.
- Collection cardinality có thể quản lý được.

### 14.2. Hạn chế

- Đây là Hibernate-specific behavior.
- Secondary query có thể tải collection cho nhiều owners hơn code thực sự truy cập.
- Scope phụ thuộc query/Session state.
- Không phải lựa chọn tối ưu cho mọi pagination/query shape.
- Cần kiểm tra SQL thực tế và transaction/session lifetime.

SUBSELECT vẫn truyền các child rows, nhưng không nhân chúng với rows của các collection khác trong cùng joined result set.

## 15. Tách thành các query riêng trong cùng persistence context

Một chiến lược dễ hiểu là:

1. Query root entities.
2. Query fetch một collection.
3. Query fetch collection thứ hai.
4. Giữ các root entities trong cùng persistence context để Hibernate ghép associations vào đúng managed instances.

Ví dụ:

~~~java
@Transactional(readOnly = true)
public List<PurchaseOrder> loadOrderGraph(String organizationId) {
    List<PurchaseOrder> orders = entityManager.createQuery("""
        select o
        from PurchaseOrder o
        where o.organizationId = :organizationId
        order by o.createdAt desc, o.id desc
        """, PurchaseOrder.class)
        .setParameter("organizationId", organizationId)
        .getResultList();

    if (orders.isEmpty()) {
        return orders;
    }

    List<Long> ids = orders.stream()
        .map(PurchaseOrder::getId)
        .toList();

    entityManager.createQuery("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.lines
        where o.id in :ids
        """, PurchaseOrder.class)
        .setParameter("ids", ids)
        .getResultList();

    entityManager.createQuery("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.payments
        where o.id in :ids
        """, PurchaseOrder.class)
        .setParameter("ids", ids)
        .getResultList();

    return orders;
}
~~~

Ví dụ giả định mỗi fetch query chỉ join một collection. Root objects đã managed nên query tiếp theo có thể khởi tạo collection trên cùng persistence context.

### 15.1. Thứ tự root có thể thay đổi

Query IN (:ids) không đảm bảo giữ thứ tự IDs ban đầu. Giữ danh sách root đầu tiên làm danh sách trả về, hoặc sắp xếp lại rõ ràng theo sort key đã chọn.

### 15.2. Giới hạn kích thước IN

Nếu page có hàng nghìn IDs, một IN quá dài có thể vượt giới hạn database/driver hoặc làm plan xấu. Chia thành chunks hoặc dùng batch fetch. Database khác nhau có parameter limits khác nhau.

### 15.3. Consistency giữa các query

Nhiều query trong cùng transaction không tự động có cùng snapshot ở mọi isolation level. Ở READ COMMITTED, mỗi statement có thể nhìn thấy snapshot khác nhau tùy database. Nếu graph cần consistent snapshot, chọn isolation/transaction semantics phù hợp và hiểu chi phí.

### 15.4. Chú ý filters và tenant predicates

Fetch query thứ hai phải giữ mọi điều kiện security/data-scope cần thiết. Không được nghĩ rằng có danh sách IDs từ query đầu thì mọi query sau có thể bỏ tenant/business constraints tùy tiện. IDs và persistence context phải thuộc đúng transaction/tenant.

## 16. Pagination hai pha: root IDs trước, collections sau

Khi endpoint trả một page orders và cần một hoặc nhiều collections, không áp pagination trực tiếp lên collection fetch join.

### Pha 1: lấy root IDs theo page

~~~java
List<Long> ids = entityManager.createQuery("""
    select o.id
    from PurchaseOrder o
    where o.organizationId = :organizationId
      and o.status = :status
    order by o.createdAt desc, o.id desc
    """, Long.class)
    .setParameter("organizationId", organizationId)
    .setParameter("status", OrderStatus.OPEN)
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

### Pha 2: tải root và một collection

~~~java
List<PurchaseOrder> fetched = entityManager.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    where o.id in :ids
    """, PurchaseOrder.class)
    .setParameter("ids", ids)
    .getResultList();
~~~

### Pha 3: tải các collection khác bằng query riêng hoặc batch

~~~java
entityManager.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.payments
    where o.id in :ids
    """, PurchaseOrder.class)
    .setParameter("ids", ids)
    .getResultList();
~~~

Giữ thứ tự IDs:

~~~java
Map<Long, PurchaseOrder> byId = fetched.stream()
    .collect(Collectors.toMap(
        PurchaseOrder::getId,
        Function.identity()
    ));

List<PurchaseOrder> ordered = ids.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
~~~

### 16.1. Cẩn thận khi root bị xóa giữa hai pha

Nếu transaction isolation không giữ snapshot ổn định, root có thể bị xóa hoặc đổi trạng thái giữa query ID và query fetch. Quyết định semantics: bỏ qua root biến mất, retry, hoặc dùng isolation phù hợp.

### 16.2. Page total và sort stability

Nếu API cần total count, chạy count query riêng. Sort phải có tie-breaker ổn định như createdAt, id; nếu chỉ sort theo timestamp trùng nhau, page boundaries có thể không ổn định.

## 17. DTO projection cho read API

Nếu màn hình chỉ cần hiển thị summary, không nhất thiết phải load toàn bộ entity graph.

~~~java
public record OrderSummary(
    Long id,
    String orderNumber,
    OrderStatus status,
    BigDecimal total,
    long lineCount,
    BigDecimal paidAmount
) {}
~~~

Query:

~~~java
List<OrderSummary> rows = entityManager.createQuery("""
    select new com.example.api.OrderSummary(
        o.id,
        o.orderNumber,
        o.status,
        o.totalAmount,
        count(distinct l.id),
        sum(p.amount)
    )
    from PurchaseOrder o
    left join o.lines l
    left join o.payments p
    where o.organizationId = :organizationId
    group by o.id, o.orderNumber, o.status, o.totalAmount
    """, OrderSummary.class)
    .setParameter("organizationId", organizationId)
    .getResultList();
~~~

**Cảnh báo:** Query aggregate ở trên vẫn join hai to-many collections và có thể nhân rows trước khi aggregate. count(distinct l.id) có thể tránh đếm trùng lines, nhưng sum(p.amount) vẫn có thể bị nhân theo số lines. Với báo cáo chính xác, dùng correlated subqueries, aggregate subqueries/CTEs hoặc query riêng cho từng collection rồi ghép kết quả.

Ví dụ dùng subquery aggregate theo root:

~~~sql
SELECT
    o.id,
    o.order_number,
    o.status,
    o.total_amount,
    (
        SELECT COUNT(*)
        FROM order_lines l
        WHERE l.order_id = o.id
    ) AS line_count,
    (
        SELECT COALESCE(SUM(p.amount), 0)
        FROM payments p
        WHERE p.order_id = o.id
    ) AS paid_amount
FROM purchase_orders o
WHERE o.organization_id = :organization_id;
~~~

Optimizer có thể decorrelate subqueries hoặc chọn plan khác tùy DB. Cần EXPLAIN và index phù hợp.

### 17.1. Projection tránh hydrate graph không cần thiết

DTO projection giúp chỉ lấy fields/aggregates cần cho màn hình. Nếu UI cần chi tiết lines, có thể gọi endpoint/query riêng cho lines khi người dùng mở rộng order.

### 17.2. Không dùng entity graph chỉ vì tiện

JPA EntityGraph mô tả fetch graph, nhưng provider có thể triển khai bằng joins hoặc secondary selects. EntityGraph không bảo đảm tránh Cartesian multiplication. Kiểm tra SQL sinh ra và rows thực tế.

## 18. EntityGraph và fetch profiles

Ví dụ:

~~~java
EntityGraph<PurchaseOrder> graph =
    entityManager.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");
graph.addSubgraph("lines");
~~~

Sau đó áp dụng graph cho query/find theo JPA hints hoặc repository annotation.

EntityGraph hữu ích để khai báo dữ liệu cần tải theo use case mà không thay đổi mapping fetch mặc định. Nhưng nếu graph chứa nhiều to-many associations, provider có thể sinh nhiều joins hoặc nhiều queries tùy implementation.

Hãy xem EntityGraph như một **fetch plan request**, không phải lời hứa rằng SQL sẽ có cardinality thấp. Đo SQL, result rows và query count như với fetch join viết trực tiếp.

Hibernate Fetch Profiles cũng cần được đánh giá theo SQL thực tế; đổi cách khai báo fetch không tự loại row multiplication.

## 19. Mapping collection: List, Set, bag và ordering

Lựa chọn Java collection type phải phản ánh domain semantics.

| Collection | Ý nghĩa thường gặp | Điều cần chú ý |
| --- | --- | --- |
| List + không có OrderColumn | Bag semantics trong nhiều Hibernate mappings | Có thể gặp MultipleBagFetchException khi fetch nhiều bag |
| List + OrderColumn | Indexed list, vị trí được lưu | Có thêm cột index và chi phí duy trì thứ tự |
| Set | Không cho duplicate theo equals/hashCode | Không tự bảo đảm thứ tự; vẫn có Cartesian multiplication |
| SortedSet | Set có ordering | Comparator và entity lifecycle cần ổn định |
| Map | Association keyed theo key | Key semantics và fetch behavior cần kiểm tra |

### 19.1. Không đổi semantics chỉ để tối ưu SQL

Nếu nghiệp vụ cho phép cùng một tag xuất hiện nhiều lần ở collection, chuyển List/Bag sang Set có thể làm mất dữ liệu/ý nghĩa. Nếu thứ tự line là nghiệp vụ, phải lưu order column hoặc sort key thực sự.

### 19.2. equals/hashCode ảnh hưởng Set

Entity thường có generated ID được gán sau persist. equals/hashCode không ổn định có thể làm Set hoạt động sai khi ID thay đổi hoặc entity chuyển từ transient sang persistent. Thiết kế identity semantics trước khi chọn Set.

### 19.3. OrderBy không giống OrderColumn

- OrderBy yêu cầu sắp xếp theo property khi load; không lưu index vị trí.
- OrderColumn lưu vị trí của từng phần tử trong collection.

Cả hai không loại Cartesian multiplication khi join nhiều collection.

## 20. Những trường hợp làm cardinality thực tế lớn hơn dự kiến

- Many-to-many join table có duplicate rows do thiếu unique constraint.
- Association join dùng predicate chưa đủ khóa.
- Soft-delete/filter predicate được áp dụng khác nhau giữa các joins.
- Tenant predicate bị thiếu ở một join path.
- Child relation có dữ liệu legacy không tuân thủ invariant.
- Một root có collection rất lớn bất thường.
- Fetch join thêm collection gián tiếp qua nested association.
- Mapping inheritance tạo thêm joins/columns.
- Secondary joins hoặc formula mappings làm plan phức tạp.

### 20.1. Kiểm tra database constraints

Many-to-many link table thường nên có unique constraint phù hợp trên cặp foreign keys nếu domain không cho phép duplicate association:

~~~sql
ALTER TABLE order_tag_links
ADD CONSTRAINT uk_order_tag UNIQUE (order_id, tag_id);
~~~

Chỉ thêm constraint sau khi kiểm tra duplicate data và domain semantics. Constraint giúp ngăn duplicate links trong tương lai, nhưng không giải quyết phép nhân giữa lines, payments và tags.

### 20.2. Tenant scoping

Trong multi-tenant model, mỗi query phải giữ tenant boundary. Một join sai predicate có thể không chỉ làm rows tăng mà còn trộn dữ liệu ngoài scope. Fetch optimization không được làm yếu tenant isolation.

## 21. Chiến lược chọn fetch plan theo use case

| Use case | Fetch plan nên cân nhắc |
| --- | --- |
| Order detail, một order, một collection nhỏ | Join fetch collection đó |
| Order detail, nhiều collection nhỏ | So sánh split queries và join một collection + batch |
| Order list có pagination | Page root IDs trước; tải collections theo batch/separate queries |
| Report chỉ cần totals/counts | DTO/scalar aggregate queries |
| Nhiều roots cùng truy cập một lazy collection | Batch fetch hoặc SUBSELECT |
| Collection cực lớn | Query riêng, pagination/streaming cho child rows |
| Nhiều to-one associations | Fetch join thường ít nguy cơ nhân rows |
| Graph nhiều to-many cardinality cao | Tránh join đồng thời; chia fetch plan |

Không có một fetch strategy tối ưu cho mọi entity. Chọn theo số root, cardinality distribution, dữ liệu cần hiển thị, RTT, database capacity và transaction consistency.

## 22. Benchmark so sánh các fetch strategies

Tạo dataset representative:

~~~text
Orders: 1,000
Lines/order: median 5, p95 20, max 300
Payments/order: median 1, p95 4, max 20
Tags/order: median 3, p95 8, max 30
~~~

So sánh:

1. Fetch join một collection.
2. Fetch join hai collections.
3. Fetch join một collection + batch fetch các collection còn lại.
4. Root query + split fetch queries.
5. DTO projection/aggregate.
6. EntityGraph tương đương nếu ứng dụng sử dụng.

### 22.1. Metrics cần ghi

| Metric | Vì sao cần |
| --- | --- |
| SQL statement count | Phát hiện N+1/round-trips |
| Joined rows read | Đo row multiplication trực tiếp |
| Unique root IDs | Biết kích thước kết quả nghiệp vụ |
| Unique child IDs theo collection | Biết số entity thực tế |
| Bytes transferred | Đo payload lặp |
| DB execution time | Chi phí ở database |
| JDBC elapsed time | Chi phí client/driver/transfer |
| Hibernate hydration time | Chi phí ORM dựng graph |
| Heap allocation/peak heap | Memory pressure |
| GC pauses | Ảnh hưởng runtime |
| HTTP p95/p99 | Trải nghiệm thực tế |
| Connection usage | Tác động lên pool |

### 22.2. Kiểm soát biến số

Giữ cố định database version, indexes, data distribution, JVM, driver, pool, concurrency, transaction isolation và cache state. Chạy warm-up, nhiều lần và đo percentiles.

Không benchmark với 10 orders nhỏ rồi kết luận query an toàn cho production có hàng triệu orders và vài tenant rất lớn.

### 22.3. Kiểm tra cả tail cardinality

Thêm fixtures cực trị: một root có hàng trăm/hàng nghìn children, collections rỗng, một association rất skewed và nhiều associations cùng có cardinality cao. Đây thường là những trường hợp làm p99 xấu đi.

## 23. Ví dụ test đếm joined rows

Có thể viết integration test chạy trên database thật để so sánh số rows:

~~~java
long joinedRows = ((Number) entityManager.createNativeQuery("""
    select count(*)
    from purchase_orders o
    left join order_lines l on l.order_id = o.id
    left join payments p on p.order_id = o.id
    where o.organization_id = :org
    """)
    .setParameter("org", organizationId)
    .getSingleResult())
    .longValue();

long rootCount = entityManager.createQuery("""
    select count(o)
    from PurchaseOrder o
    where o.organizationId = :org
    """, Long.class)
    .setParameter("org", organizationId)
    .getSingleResult();

assertThat(joinedRows).isGreaterThanOrEqualTo(rootCount);
~~~

Test này không phải benchmark đầy đủ. Nó chỉ chứng minh join cardinality trên fixture. Để xác nhận từng collection, thêm counts riêng và kiểm tra số unique child IDs.

### 23.1. Đừng hard-code một tỷ lệ chung cho mọi dataset

Một assertion kiểu joinedRows nhỏ hơn rootCount nhân 10 chỉ hợp lệ nếu đó là business/performance budget có căn cứ. Nếu collection cardinality hợp lệ có thể lớn hơn, test sẽ flaky hoặc khuyến khích thay đổi semantics dữ liệu.

Đặt budget dựa trên SLO và giới hạn nghiệp vụ thực tế.

## 24. Cấu hình và log hữu ích khi điều tra

Có thể bật SQL logging trong local/test:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
~~~

Trong một số Hibernate versions, bind logging category khác nhau. Chỉ bật bind logging khi cần và dùng dữ liệu test; bind values có thể chứa PII/secrets.

Các nguồn quan sát nên kết hợp:

- Hibernate SQL logs: xem join shape.
- Hibernate Statistics: query/entity/collection counts.
- JDBC instrumentation: rows fetched và elapsed time.
- Database EXPLAIN: actual join cardinality, loops, buffers.
- Application trace: request duration và query spans.
- JVM profiler/JFR: allocation, hydration và GC.
- Dataset SQL: cardinality distribution per parent.

Không bật SQL TRACE vô thời hạn trong production; logging volume và dữ liệu bind có thể gây overhead hoặc lộ thông tin.

## 25. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Fetch join tất cả collections để chỉ có một SQL | Cartesian row multiplication | Fetch một collection rồi batch/split phần còn lại |
| Chỉ nhìn SQL count | Bỏ qua rows và bytes | Đo joined rows/result size |
| Dùng DISTINCT để chữa row explosion | SQL vẫn phải trả các child combinations | Thay fetch plan |
| Đổi List thành Set để hết MultipleBagFetchException | Đổi domain semantics nhưng row multiplication vẫn còn | Giữ collection semantics đúng, split queries |
| Thêm OrderColumn chỉ để tránh bag exception | Tăng write/index maintenance, không xóa row multiplication | Chỉ dùng khi cần persistent ordering |
| Pagination trực tiếp với collection fetch | Hibernate có thể phân trang trong memory | Page root IDs trước |
| Dùng EntityGraph rồi nghĩ không có Cartesian join | Provider vẫn có thể join nhiều to-many | Đo SQL thực tế |
| Dùng average cardinality | Bỏ sót hot roots/tail | Đo p95/p99/max |
| Chỉ đo database execution | Bỏ qua network/JDBC/hydration | Đo client-observed rows và latency |
| Một query aggregate với hai to-many joins | COUNT/SUM có thể bị nhân sai | Subquery/aggregate riêng |
| Split queries nhưng bỏ tenant predicate | Có thể đọc ngoài scope | Giữ security/data predicates |
| Chia query nhưng không nghĩ isolation | Graph có thể thấy dữ liệu ở các snapshot khác nhau | Chọn transaction semantics |
| Batch size quá lớn | IN list/parameter/memory tăng | Benchmark và chunk |
| SUBSELECT cho mọi collection | Có thể tải quá nhiều owners | Chọn theo access pattern |
| Test chỉ với collections rỗng | Không phát hiện multiplication | Seed cardinality đại diện và cực trị |

## 26. Quy trình xử lý một fetch join chậm

### Bước 1 — Xác định graph cần dùng

Liệt kê root và associations thực sự cần cho response/use case. Phân loại to-one và to-many.

### Bước 2 — Đọc SQL Hibernate sinh ra

Đếm số joins, xác định mỗi join tới collection nào và điều kiện join có đầy đủ khóa/tenant/filter không.

### Bước 3 — Đo root và collection cardinalities

Lấy số root, unique children từng collection, p50/p95/p99/max elements per root.

### Bước 4 — Đo joined rows

Chạy count query tương đương hoặc JDBC row instrumentation trong môi trường an toàn. So sánh rows với unique entity counts.

### Bước 5 — Đọc database plan

Dùng EXPLAIN/ANALYZE phù hợp để hiểu actual rows, loops, join algorithms, buffers và estimates.

### Bước 6 — Chọn một thay đổi có thể kiểm chứng

Ví dụ bỏ một collection fetch join và thay bằng batch fetch hoặc query riêng.

### Bước 7 — So sánh cùng workload

Đo statement count, rows, bytes, DB time, hydration, heap và p95/p99. Xác nhận dữ liệu/ordering/tenant semantics không đổi.

### Bước 8 — Thêm regression test

Tạo fixture có nhiều collection và một root cardinality lớn. Kiểm tra query count/row budget nếu budget đã được xác định.

## 27. Checklist trước khi merge fetch plan

- [ ] Xác định root entity và associations cần cho use case.
- [ ] Phân biệt to-one và to-many.
- [ ] Đếm số to-many collection được join cùng statement.
- [ ] Ước lượng tích cardinality cho mỗi root.
- [ ] Đo p50/p95/p99/max collection size.
- [ ] Đo actual joined rows và unique root/child counts.
- [ ] Đo payload/bytes hoặc client-observed result processing.
- [ ] Kiểm tra Hibernate version và MultipleBagFetchException.
- [ ] Không dùng DISTINCT như giải pháp row multiplication.
- [ ] Không thay List/Set semantics chỉ để dập exception.
- [ ] Kiểm tra pagination-over-collection-fetch.
- [ ] Xem xét batch fetching, SUBSELECT hoặc split queries.
- [ ] Kiểm tra EntityGraph SQL thực tế.
- [ ] Giữ tenant/security predicates ở mọi query.
- [ ] Xác định isolation/consistency khi chia nhiều queries.
- [ ] Test với cardinality cực trị và collection rỗng.
- [ ] Đo p95/p99 và memory dưới concurrency đại diện.
- [ ] Ghi rõ fetch plan và giới hạn cardinality trong code review.

## 28. Bài tập thực hành

### Bài 1 — Tính row multiplication

Một query tải 80 orders. Mỗi order trung bình có 6 lines, 2 payments và 5 tags. Ước lượng joined rows nếu fetch cả ba collections cùng lúc.

### Bài 2 — Collection rỗng

Một order có 10 lines, 0 payments và 3 tags. Với LEFT JOIN FETCH, ước lượng số joined rows. Vì sao collection rỗng vẫn không làm root biến mất?

### Bài 3 — To-one và to-many

Giải thích tại sao fetch join customer (ManyToOne) cùng lines (OneToMany) thường ít nguy cơ nhân rows hơn fetch lines cùng payments.

### Bài 4 — DISTINCT

Với một order có hai lines và hai payments, liệt kê bốn tổ hợp rows. Vì sao SQL DISTINCT không thể gộp thành một row mà vẫn hydrate đủ collections?

### Bài 5 — MultipleBagFetchException

Một entity có hai List associations không khai báo OrderColumn. Hibernate ném MultipleBagFetchException. Nêu nguyên nhân và hai chiến lược giải quyết không làm thay đổi semantics collection.

### Bài 6 — Đổi List thành Set

Đổi hai Lists thành Sets khiến query không còn ném MultipleBagFetchException. Vì sao vẫn phải đo số rows? Nêu rủi ro equals/hashCode.

### Bài 7 — OrderColumn

Giải thích khác biệt giữa OrderColumn và OrderBy. Vì sao thêm OrderColumn không tự giải quyết Cartesian multiplication?

### Bài 8 — Pagination

Một query dùng setMaxResults(20) cùng collection fetch join. Vì sao database LIMIT 20 rows không tương đương 20 root entities? Mô tả pagination hai pha.

### Bài 9 — Batch fetching

Viết mapping/configuration để batch fetch payments cho nhóm orders. Giải thích dạng SQL có thể được phát khi collection được truy cập.

### Bài 10 — SUBSELECT

Khi nào FetchMode.SUBSELECT phù hợp? Nêu hai hạn chế cần đo.

### Bài 11 — Split queries

Mô tả cách query root entities rồi query lines và payments riêng trong cùng persistence context. Vì sao danh sách root ban đầu nên được dùng để giữ ordering?

### Bài 12 — Consistency

Ba query được chạy trong một READ COMMITTED transaction. Vì sao dữ liệu graph có thể đến từ các statement snapshots khác nhau trên một số database? Khi nào cần isolation mạnh hơn?

### Bài 13 — Aggregate double counting

Một order có 3 lines và 2 payments. Query join cả hai rồi SUM(payment.amount). Vì sao tổng có thể bị nhân ba lần? Nêu cách sửa.

### Bài 14 — EXPLAIN

Một join node có actual rows rất cao và nested loop nhiều iterations. Cần xem thêm metrics nào để xác định row multiplication và plan cost?

### Bài 15 — Hibernate Statistics

getEntityLoadCount() là 100 nhưng JDBC result set có 9.000 rows. Hai con số có mâu thuẫn không? Giải thích.

### Bài 16 — Hot parent

99 orders có 2 lines nhưng một order có 2.000 lines, 10 payments và 8 tags. Vì sao average cardinality có thể đánh giá thấp p99? Thiết kế test fixture.

### Bài 17 — EntityGraph

Một EntityGraph yêu cầu lines và payments. Vì sao không thể mặc định rằng provider sẽ chạy hai SELECT riêng? Làm sao xác minh?

### Bài 18 — Tenant predicate

Một fetch query pha hai tải collection chỉ lọc theo root IDs. Những điều kiện tenant/security nào cần bảo đảm? Vì sao ID list không thay thế authorization?

### Bài 19 — Đo rows

Đề xuất ba cách đo joined rows: SQL count, EXPLAIN actual rows và JDBC ResultSet instrumentation. Mỗi cách có giới hạn gì?

### Bài 20 — Benchmark

Thiết kế benchmark so một query fetch hai collections, fetch một + batch một, và split queries. Ghi ít nhất tám metrics.

### Bài 21 — Nhiều collection trong detail page

Một detail page cần lines, payments, shipment events và tags. Chọn fetch plan và giải thích collection nào nên join, collection nào nên query riêng/batch.

### Bài 22 — Code review

Một PR thêm left join fetch cho ba collections để giảm 3 SQL thành 1. Viết các câu hỏi reviewer phải yêu cầu tác giả trả lời trước khi chấp nhận.

### Gợi ý đáp án

- **Bài 1:** 80 × 6 × 2 × 5 = 4.800 rows, nếu cardinalities gần như nhau và collections không rỗng.
- **Bài 2:** 10 × max(1,0) × 3 = 30 rows; LEFT JOIN giữ root bằng null-extended payment columns.
- **Bài 3:** To-one chỉ thêm tối đa một related row cho mỗi root; to-many tạo nhiều rows và các to-many joins nhân nhau.
- **Bài 4:** Hai lines × hai payments tạo bốn cặp; mỗi row khác line/payment IDs nên SQL DISTINCT vẫn giữ chúng.
- **Bài 5:** Hai bag roles được fetch đồng thời; fetch một collection rồi batch/split collection còn lại, hoặc DTO projection.
- **Bài 6:** Sets vẫn join theo tích cardinality; Set thay duplicate/order semantics và cần equals/hashCode ổn định.
- **Bài 7:** OrderColumn lưu index; OrderBy sort theo property khi load. Cả hai không loại phép nhân giữa các collection.
- **Bài 8:** LIMIT cắt joined rows chứ không phải root; query page IDs trước rồi tải collection theo IDs.
- **Bài 9:** Dùng @BatchSize(size=...) hoặc hibernate.default_batch_fetch_size; SQL thường dùng WHERE order_id IN (...).
- **Bài 10:** Hữu ích khi một query tải nhóm owners và nhiều owners cần collection; kiểm tra scope owners và số rows tải thừa.
- **Bài 11:** Giữ root entities managed; query fetch collection riêng sẽ khởi tạo collection trên cùng instances. IN không bảo đảm order.
- **Bài 12:** READ COMMITTED có thể tạo snapshot theo statement; cần repeatable snapshot nếu graph phải nhất quán theo một thời điểm.
- **Bài 13:** Mỗi payment lặp theo số lines; aggregate bằng subquery/CTE hoặc query riêng.
- **Bài 14:** Loops, buffers, estimated vs actual rows, execution time, bytes và JDBC/hydration metrics.
- **Bài 15:** Không. Nhiều SQL rows có thể đại diện cùng root/child entity; entityLoadCount đếm entity loads, không đếm JDBC rows.
- **Bài 16:** Tail root tạo 2.000 × 10 × 8 = 160.000 rows riêng nó; test root cực trị và p95/p99.
- **Bài 17:** EntityGraph là fetch plan request; provider có thể join hoặc secondary select. Đọc SQL logs/traces và đo result rows.
- **Bài 18:** Giữ tenant predicate/authorization ở mọi query; IDs không phải proof of permission.
- **Bài 19:** COUNT(*) query đo cardinality nhưng tự chạy join; EXPLAIN cho actual plan rows nhưng phải hiểu loops; JDBC wrapper đếm rows client đọc nhưng có instrumentation overhead.
- **Bài 20:** SQL count, joined rows, unique IDs, bytes, DB time, JDBC time, hydration, heap, GC, p95/p99 và connection usage.
- **Bài 21:** Có thể join một collection nhỏ/quan trọng như lines; batch hoặc query riêng payments/events/tags theo access pattern và cardinality; DTO cho summary.
- **Bài 22:** Yêu cầu cardinality distributions, estimated/actual rows, payload, MultipleBag behavior, pagination, tenant predicates, consistency, alternatives và benchmark evidence.

---

## Tổng kết

**Fetch join nhiều collection có thể giảm số SQL statements nhưng làm số rows tăng theo tích cardinality.** Một câu SQL duy nhất không tự động là một fetch plan hiệu quả.

1. Fetch join to-one thường ít tạo row multiplication; nhiều to-many joins mới là rủi ro lớn.
2. Ước lượng rows bằng tích số phần tử của từng collection trên mỗi root; đo cả p95/p99/max vì average che mất hot parents.
3. DISTINCT có thể loại duplicate root references trong kết quả entity nhưng không xóa các joined rows khác nhau ở database/JDBC.
4. MultipleBagFetchException là dấu hiệu mapping/query có nhiều bag fetch; đổi List thành Set có thể đổi domain semantics và vẫn không giải quyết Cartesian multiplication.
5. Không phân trang trực tiếp trên collection fetch join; lấy root IDs theo page trước rồi fetch collections theo query riêng/batch.
6. Đo SQL rows, unique entity counts, bytes, database plan, JDBC time, Hibernate hydration và memory.
7. Cân nhắc fetch một collection, batch fetching, SUBSELECT, split queries hoặc DTO projection tùy use case và consistency requirements.

**Trước khi thêm một fetch join to-many, hãy biết mỗi root có bao nhiêu phần tử ở từng collection và tổng joined rows sẽ là bao nhiêu.**
