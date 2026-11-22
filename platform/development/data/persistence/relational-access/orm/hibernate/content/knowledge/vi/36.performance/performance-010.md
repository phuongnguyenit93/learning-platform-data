# Đối chiếu chỉ mục, kế hoạch thực thi và điều kiện lọc từ SQL thực trong Hibernate ORM

Một truy vấn JPQL/HQL nhìn ngắn gọn chưa nói lên database sẽ thực hiện nó nhanh hay chậm. Hibernate dịch mapping và query thành SQL cụ thể theo dialect, schema, fetch plan, pagination, inheritance và phiên bản ORM. Database sau đó chọn execution plan dựa trên SQL, bind values, indexes, statistics và cấu hình của chính nó.

Vì vậy, khi tối ưu hiệu năng Hibernate, cần đối chiếu ba thứ cùng lúc:

1. **SQL thực tế Hibernate gửi qua JDBC** — câu lệnh, joins, predicates, ordering, pagination và bind parameters.
2. **Indexes hiện có trong database** — cột, thứ tự cột, loại index, predicate của partial index, covering/include columns và trạng thái thống kê.
3. **Execution plan của database** — scan, seek, join algorithm, sort, filter, row estimates, actual rows, buffers/IO và chi phí thực tế.

Mục tiêu không phải tạo thật nhiều index hoặc ép database dùng một index cụ thể. Mục tiêu là hiểu **điều kiện lọc thực sự và thứ tự truy cập dữ liệu**, xác định chỗ database đọc quá nhiều rows hoặc sort/join tốn kém, rồi thay đổi query, mapping hoặc index có bằng chứng.

Bài học trình bày quy trình lấy SQL thực từ Hibernate, xem bind parameters an toàn, đọc `EXPLAIN`/`EXPLAIN ANALYZE`, thiết kế composite/partial/covering indexes, đánh giá sargability, xử lý tenant và soft-delete predicates, phân tích joins/pagination, kiểm tra parameter selectivity và query-plan caching, rồi kiểm chứng bằng benchmark và integration tests.

---

## 1. Vì sao không tối ưu chỉ từ JPQL/HQL?

Ví dụ ứng dụng viết:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.customer.id = :customerId
      and o.status = :status
    order by o.createdAt desc
    """, PurchaseOrder.class)
    .setParameter("customerId", customerId)
    .setParameter("status", OrderStatus.OPEN)
    .getResultList();
```

Trong đầu người viết, truy vấn có hai điều kiện và một sắp xếp. Nhưng SQL thật có thể là:

```sql
select
    o.id,
    o.customer_id,
    o.status,
    o.created_at,
    o.total_amount,
    o.version
from purchase_orders o
where o.customer_id = ?
  and o.status = ?
order by o.created_at desc
```

Nếu entity mapping có inheritance, soft delete, tenant restriction, filter hoặc fetch graph, SQL có thể thêm joins và predicates:

```sql
select ...
from purchase_orders o
join customers c on c.id = o.customer_id
where o.customer_id = ?
  and o.status = ?
  and o.organization_id = ?
  and o.deleted = false
order by o.created_at desc
```

Database tối ưu **SQL sau khi Hibernate sinh**, không tối ưu câu JPQL mà developer nhìn thấy.

### 1.1. Mapping ảnh hưởng SQL shape

Các yếu tố có thể làm SQL khác dự kiến:

- `FetchType.EAGER`, EntityGraph và fetch joins.
- Lazy loading và batch fetching.
- `@Filter`, `@SQLRestriction`, `@SoftDelete` hoặc tenant mapping.
- Inheritance strategy như SINGLE_TABLE/JOINED.
- Embedded values và secondary tables.
- Formula, custom types, converters và quoted identifiers.
- Pagination, locking, DISTINCT và collection fetch.
- Hibernate version và SQL dialect.

Do đó, index được thiết kế theo một JPQL giả định có thể không hỗ trợ SQL thực.

### 1.2. Một query không đồng nghĩa một SQL

Một method repository có thể gây thêm SQL khi:

- Lazy association được truy cập lúc map DTO.
- Serializer gọi getter của entity.
- Một vòng lặp truy cập collection của từng root entity.
- Flush tự động phát sinh INSERT/UPDATE trước query.
- Identifier generator cần sequence query.
- Một query count chạy thêm cho Spring Data `Page<T>`.

Hãy lấy SQL của **toàn bộ use case**, không chỉ câu SELECT đầu tiên.

## 2. Quy trình tối ưu có bằng chứng

```text
1. Tái hiện use case với dữ liệu đại diện
            |
            v
2. Thu SQL thực + bind values có kiểm soát
            |
            v
3. Xác định query shape và predicate
            |
            v
4. Xem index hiện có + database statistics
            |
            v
5. Chạy EXPLAIN / actual execution plan
            |
            v
6. Xác định scan, join, sort, row-estimate mismatch
            |
            v
7. Chọn sửa query, mapping hoặc index
            |
            v
8. Đo lại latency, IO, rows, memory
            |
            v
9. Khóa regression bằng integration/performance test
```

Không bỏ qua bước thu SQL thật. Nếu plan được tạo cho một câu SQL khác với câu Hibernate thực thi, toàn bộ phân tích index có thể sai.

## 3. Lấy SQL thực tế từ Hibernate

Có nhiều cách, mỗi cách quan sát một phần khác nhau.

### 3.1. Hibernate SQL logger

Với Hibernate 6, cấu hình thường gặp:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

Để quan sát bind values, logger thường gặp trong Hibernate 6 là:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Ở Hibernate 5, bind logger thường gặp là `org.hibernate.type.descriptor.sql.BasicBinder`. Tên logger có thể thay đổi theo major version; kiểm tra version đang chạy trước khi áp dụng.

SQL log giúp thấy query shape, còn bind log giúp hiểu các placeholder được gắn giá trị gì. **Bind values có thể chứa PII, tokens, email, account IDs hoặc dữ liệu tài chính**, nên chỉ bật trong môi trường có kiểm soát, giới hạn thời gian, quyền truy cập và retention.

### 3.2. Không dùng show_sql như giải pháp logging duy nhất

```properties
hibernate.show_sql=true
hibernate.format_sql=true
```

`show_sql` thường in SQL theo cơ chế riêng của Hibernate, có thể gây log noise và khó tích hợp với structured logging. Với ứng dụng Spring, logger category thường linh hoạt hơn cho filtering, correlation và redaction.

### 3.3. StatementInspector

`StatementInspector` nhận SQL text trước khi Hibernate chuẩn bị JDBC statement:

```java
public final class SqlShapeInspector
        implements StatementInspector {

    @Override
    public String inspect(String sql) {
        // Quan sát metadata/SQL shape đã được giới hạn.
        return null;
    }
}
```

Nó hữu ích để quan sát hoặc thêm marker SQL cố định có kiểm soát. Nhưng inspector **không tự nhận bind values, execution duration, rows affected hay commit outcome**. Không dùng nó để tự nối parameter values vào SQL hoặc viết lại WHERE predicates theo user input.

### 3.4. JDBC/DataSource instrumentation

Nếu cần thấy thời gian prepare/execute, parameter binding, connection acquisition hoặc mọi JDBC statement kể cả `JdbcTemplate`, dùng JDBC proxy/DataSource instrumentation, APM hoặc tracing phù hợp.

Hibernate SQL logger có thể không thấy SQL chạy trực tiếp qua DataSource ngoài Hibernate.

## 4. Bind parameters quan trọng ngang SQL text

SQL:

```sql
select *
from purchase_orders
where status = ?
```

có thể rất nhanh với `status = 'CANCELLED'` nhưng chậm với `status = 'OPEN'` nếu 95% rows có status OPEN. Predicate text giống nhau, selectivity khác nhau.

### 4.1. Xác định parameter types và values

Cần biết:

- Giá trị thực tế ở mỗi placeholder.
- Kiểu JDBC/SQL được bind.
- Thứ tự bind.
- Có cast implicit hay không.
- Có truyền null không.
- Parameter có cardinality khác nhau giữa requests không.

Không suy đoán giá trị chỉ từ SQL text có dấu `?`.

### 4.2. Không ghép values vào SQL thủ công

Không làm:

```java
String sql = loggedSql.replace("?", "'" + value + "'");
```

Cách này sai khi nhiều parameters, dấu hỏi nằm trong literal/operator, type/date/time/escaping, và có nguy cơ SQL injection. Dùng bind logging hoặc JDBC tracing đã có cơ chế ghi nhận parameter an toàn.

### 4.3. Redaction

Khi điều tra production:

- Redact secrets, access tokens, email/PII theo policy.
- Dùng representative values trong staging khi có thể.
- Giữ lại type, nullability và selectivity cần thiết nếu dữ liệu thật bị che.
- Không copy bind values vào ticket/log công khai nếu không cần.
- Giới hạn retention của traces.

## 5. Xác định predicate thật trong SQL

Trước khi xem index, phân loại từng predicate.

Ví dụ:

```sql
select o.id, o.status, o.created_at
from purchase_orders o
where o.organization_id = ?
  and o.deleted_at is null
  and o.customer_id = ?
  and o.status in (?, ?)
  and o.created_at >= ?
order by o.created_at desc
limit ?
```

Các điều kiện:

| Predicate | Vai trò | Kiểu lọc |
|---|---|---|
| `organization_id = ?` | Tenant scope | Equality |
| `deleted_at is null` | Soft-delete visibility | IS NULL |
| `customer_id = ?` | Customer scope | Equality |
| `status IN (?, ?)` | Tập trạng thái | Multi-value equality-like |
| `created_at >= ?` | Time window | Range |
| `ORDER BY created_at DESC` | Sắp xếp | Ordering |
| `LIMIT ?` | Giới hạn kết quả | Pagination |

Đây là thông tin đầu vào để cân nhắc composite/partial indexes.

### 5.1. Predicate ở ON khác predicate ở WHERE

```sql
select d.id, c.id
from documents d
left join comments c
  on c.document_id = d.id
 and c.deleted_at is null
where d.organization_id = ?
```

Điều kiện comment nằm trong `ON` giúp giữ documents ngay cả khi không có comment active. Nếu chuyển thành:

```sql
where d.organization_id = ?
  and c.deleted_at is null
```

thì với NULL từ outer join, semantics có thể thay đổi và loại documents không có comments. Khi tối ưu predicate, phải bảo toàn semantics, không chỉ làm index đẹp hơn.

### 5.2. Predicate được ORM thêm tự động

Tenant filters, soft-delete restrictions, discriminator columns, association conditions và filters động có thể không xuất hiện trong JPQL source. SQL log cho thấy chúng có thực sự được thêm hay không.

## 6. Đọc execution plan với EXPLAIN

Database cung cấp công cụ xem plan. Cú pháp phụ thuộc DB engine.

PostgreSQL:

```sql
EXPLAIN
SELECT id, status
FROM purchase_orders
WHERE organization_id = '...'
  AND customer_id = 42;
```

MySQL:

```sql
EXPLAIN
SELECT id, status
FROM purchase_orders
WHERE organization_id = '...'
  AND customer_id = 42;
```

SQL Server:

```sql
SET SHOWPLAN_XML ON;
-- Chạy query để lấy estimated plan.
SET SHOWPLAN_XML OFF;
```

Oracle có các công cụ như `EXPLAIN PLAN` và `DBMS_XPLAN` để đọc plan. Không copy cú pháp của một database sang engine khác.

### 6.1. Estimated plan và actual plan

- **Estimated plan**: database dự đoán đường thực thi dựa trên statistics/metadata.
- **Actual execution plan**: query được chạy và plan kèm actual rows/timing/loops/buffers theo khả năng DB.

Actual plan hữu ích hơn để phát hiện estimate sai, nhưng có chi phí vì nó thực thi query thật.

### 6.2. PostgreSQL EXPLAIN ANALYZE

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT id, status, created_at
FROM purchase_orders
WHERE organization_id = '...'
  AND customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

`ANALYZE` chạy câu query thật. Chỉ chạy với workload/dữ liệu phù hợp, tránh thử UPDATE/DELETE nguy hiểm trên production. Có thể dùng transaction rollback cho một số thử nghiệm, nhưng không coi rollback là vô hại với mọi side effects, sequences, locks hoặc external effects.

### 6.3. MySQL actual analysis

MySQL 8 có `EXPLAIN ANALYZE` trong những phiên bản hỗ trợ, thực thi query và báo actual timing/rows theo iterator. Kiểm tra minor version và môi trường trước khi dùng.

### 6.4. SQL Server và Oracle

SQL Server có actual execution plans/Query Store; Oracle có runtime plan statistics và `DBMS_XPLAN.DISPLAY_CURSOR` với options phù hợp. Tìm công cụ đúng engine/version thay vì dùng chung một cú pháp.

## 7. Các node thường gặp trong plan

Tên hiển thị khác nhau giữa engines, nhưng các khái niệm phổ biến:

| Node/operation | Ý nghĩa | Câu hỏi cần hỏi |
|---|---|---|
| Table/Seq Scan | Đọc nhiều hoặc toàn bộ rows của table | Có phù hợp với tỷ lệ rows cần lấy? |
| Index Seek/Scan | Duyệt index để tìm rows | Predicate có dùng đúng leading columns? |
| Bitmap Index/Heap Scan | Kết hợp index candidates rồi truy cập heap | Có nhiều rows cần lọc/heap fetch? |
| Index Only Scan | Có thể lấy dữ liệu từ index mà không đọc heap nhiều | Visibility/covering có thật sự đủ? |
| Nested Loop | Lặp inner lookup cho từng outer row | Inner side có index và outer cardinality nhỏ? |
| Hash Join | Dựng hash table rồi ghép | Build side có lớn, spill memory không? |
| Merge Join | Ghép hai input đã sắp xếp | Sort có cần thiết không? |
| Sort | Sắp xếp rows | Có index hỗ trợ order? Có sort spill? |
| Filter | Lọc rows sau một bước | Bao nhiêu rows bị loại sau khi đã đọc? |
| Aggregate | Tính count/sum/group | Có group lớn hoặc sort/hash spill? |

### 7.1. Seq Scan không tự động là lỗi

Nếu query cần 70% bảng, sequential scan có thể nhanh hơn index lookup + random heap reads. Với bảng nhỏ, table scan thường là hợp lý.

Đừng yêu cầu database luôn dùng index. Hãy xem tỷ lệ rows được đọc, cardinality và chi phí thực tế.

### 7.2. Index Scan không tự động là tốt

Một index scan có thể đọc hàng trăm nghìn index entries rồi truy cập heap từng row. Một plan có chữ Index chưa chứng minh query hiệu quả.

### 7.3. Filter sau scan có thể là dấu hiệu thiếu index

Ví dụ plan đọc 1 triệu rows rồi filter còn 100 rows. Nếu predicate ổn định và có selectivity tốt, index phù hợp có thể giảm lượng rows đọc. Nhưng cần xét write cost, table size và workload.

## 8. So sánh estimated rows với actual rows

Một trong những tín hiệu quan trọng:

```text
Estimated rows: 20
Actual rows:    80,000
```

Database ước lượng sai rất lớn. Điều này có thể khiến nó chọn join algorithm hoặc index không phù hợp.

### 8.1. Nguyên nhân thường gặp

- Statistics stale sau bulk load/delete.
- Phân phối dữ liệu skewed.
- Correlation giữa nhiều columns không được mô tả đủ.
- Predicate trên expression/function.
- Parameter selectivity khác nhau.
- Thiếu extended/multicolumn statistics (tùy DB).
- Data type/cast làm estimate kém.

### 8.2. PostgreSQL ANALYZE

```sql
ANALYZE purchase_orders;
```

Cập nhật planner statistics lấy mẫu. Sau thay đổi dữ liệu lớn, cần cân nhắc analyze/autovacuum settings và statistics targets phù hợp.

### 8.3. MySQL statistics

MySQL có persistent InnoDB statistics và histogram support trong các phiên bản phù hợp. Cần xem engine, histogram, cardinality và optimizer behavior thực tế.

### 8.4. Không tạo index để chữa statistics stale

Nếu planner ước lượng sai vì statistics cũ, thêm một index mới có thể không giải quyết nguyên nhân và làm writes nặng hơn. Cập nhật/đánh giá statistics trước khi kết luận.

## 9. Composite index và thứ tự cột

Một truy vấn:

```sql
SELECT id, status, created_at
FROM purchase_orders
WHERE organization_id = ?
  AND customer_id = ?
  AND status = ?
ORDER BY created_at DESC;
```

Một index có thể cân nhắc:

```sql
CREATE INDEX ix_orders_org_customer_status_created
ON purchase_orders (
    organization_id,
    customer_id,
    status,
    created_at DESC
);
```

Index này đặt các equality predicates trước, rồi cột phục vụ ordering. Nhưng đây không phải quy tắc tuyệt đối; thứ tự tốt phụ thuộc workload, selectivity, query variants và DB engine.

### 9.1. Leftmost prefix trong B-tree

Với B-tree composite index:

```sql
(organization_id, customer_id, status, created_at)
```

nhiều engines có thể tận dụng leading prefix như:

- `organization_id`.
- `organization_id, customer_id`.
- `organization_id, customer_id, status`.

Query chỉ lọc `status` có thể không tận dụng index hiệu quả như query bắt đầu bằng `organization_id`, tùy engine/optimizer.

### 9.2. Equality trước range thường là điểm khởi đầu

Với:

```sql
WHERE organization_id = ?
  AND customer_id = ?
  AND created_at >= ?
ORDER BY created_at DESC
```

Một index candidate:

```sql
(organization_id, customer_id, created_at DESC)
```

Equality trên prefix rồi range/order trên created_at thường phù hợp.

Nhưng khi có nhiều equality columns, hãy cân nhắc selectivity, các query khác, join order và workload. Không có một quy tắc “cột có selectivity cao nhất luôn đứng đầu” áp dụng mọi trường hợp.

### 9.3. IN list và ordering phức tạp

`status IN ('OPEN', 'PENDING')` có thể được xử lý như nhiều ranges hoặc một số plan khác. Dù index có `status`, database vẫn có thể cần sort để tạo đúng global order theo created_at.

Đọc actual plan, không đoán chỉ từ thứ tự cột.

### 9.4. Không tạo một composite index cho mọi tổ hợp

Nếu entity có 8 filterable fields, tạo index cho mọi permutation sẽ tăng storage và write amplification rất nhanh. Thu thập top query shapes từ production/staging, ưu tiên query có latency/volume cao và index reuse tốt.

## 10. Thiết kế index cho ORDER BY và LIMIT

Query:

```sql
SELECT id, status, created_at
FROM purchase_orders
WHERE organization_id = ?
  AND status = ?
ORDER BY created_at DESC
LIMIT 50;
```

Candidate:

```sql
CREATE INDEX ix_orders_org_status_created
ON purchase_orders (
    organization_id,
    status,
    created_at DESC
);
```

Nếu index order tương thích predicate/order, database có thể đọc các entries đầu tiên và dừng sau 50 rows mà không sort toàn bộ candidate set.

### 10.1. Sort node không phải lúc nào cũng có thể loại bỏ

- Ordering khác hướng/collation.
- Có nhiều status values.
- Query order theo expression.
- Join làm thay đổi order.
- Planner chọn plan khác vì selectivity.
- DB không tận dụng được index order cho query shape.

### 10.2. LIMIT không làm query tự rẻ

Nếu DB phải scan 2 triệu rows mới tìm được 50 rows phù hợp, LIMIT 50 vẫn có thể chậm. Index cần hỗ trợ **đường tìm candidate rows**, không chỉ giới hạn kết quả.

### 10.3. Keyset pagination

Offset lớn:

```sql
ORDER BY created_at DESC, id DESC
OFFSET 500000
LIMIT 50;
```

có thể tốn vì database phải đi qua/loại bỏ nhiều rows trước offset.

Keyset:

```sql
WHERE organization_id = ?
  AND (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Cần index phù hợp, ví dụ `(organization_id, created_at DESC, id DESC)`. Cú pháp tuple comparison phụ thuộc database. Với nulls, tie-breakers và sort direction phải được thiết kế rõ.

## 11. Sargability: predicate có giúp index tìm kiếm không?

Một predicate thường được gọi là sargable khi database có thể dùng nó hiệu quả làm search condition cho index.

### 11.1. Hàm trên cột

Có thể kém hiệu quả:

```sql
WHERE LOWER(email) = LOWER(?)
```

Index B-tree thông thường trên `email` có thể không phục vụ expression này như mong đợi. Các lựa chọn:

- Lưu normalized email riêng và index cột đó.
- Tạo expression/function-based index nếu DB hỗ trợ.
- Dùng collation/case-insensitive type phù hợp.
- Chuẩn hóa input trước khi bind nếu semantics cho phép.

PostgreSQL expression index:

```sql
CREATE INDEX ix_users_lower_email
ON users (lower(email));
```

Query phải tương thích expression để planner sử dụng.

### 11.2. CAST trên indexed column

```sql
WHERE CAST(created_at AS DATE) = ?
```

có thể làm index trên `created_at` khó dùng như range scan thông thường. Viết thành khoảng:

```sql
WHERE created_at >= ?
  AND created_at < ?
```

với đầu mốc ngày và đầu mốc ngày tiếp theo theo timezone nghiệp vụ. Cách này thường thân thiện với B-tree trên timestamp hơn.

### 11.3. Leading wildcard

```sql
WHERE title LIKE '%hibernate%'
```

B-tree thông thường thường không thể seek theo prefix vì wildcard đầu chuỗi. Có thể cần full-text, trigram hoặc search engine tùy database và yêu cầu.

`LIKE 'hibernate%'` có khả năng dùng index trong điều kiện collation/operator phù hợp.

### 11.4. Implicit conversion

Nếu cột là UUID nhưng bind thành VARCHAR hoặc cột numeric bị so sánh với string, database có thể cast một phía và giảm khả năng dùng index, đồng thời có nguy cơ semantics khác.

Dùng đúng Java type/JDBC type, mapping và parameter binding. Đọc SQL/plan để thấy cast thực tế.

### 11.5. OR predicates

```sql
WHERE customer_id = ?
   OR assigned_user_id = ?
```

Optimizer có thể dùng bitmap/index union hoặc chọn scan. Hai index riêng đôi khi hữu ích; một composite index không tự giải quyết mọi OR. Hãy đo plan với dữ liệu đại diện.

## 12. Index cho tenant scope và soft delete

Một ứng dụng shared-table có SQL:

```sql
SELECT id, title, created_at
FROM documents
WHERE organization_id = ?
  AND deleted_at IS NULL
  AND status = ?
ORDER BY created_at DESC
LIMIT 50;
```

Các predicates quan trọng gồm tenant, soft-delete và status.

### 12.1. Composite index đầy đủ

Candidate:

```sql
CREATE INDEX ix_documents_org_deleted_status_created
ON documents (
    organization_id,
    deleted_at,
    status,
    created_at DESC
);
```

Index này có thể hỗ trợ một số query shapes nhưng `deleted_at IS NULL` có cardinality/semantics riêng. Cần xem tỷ lệ deleted rows và các query khác.

### 12.2. Partial index

PostgreSQL hỗ trợ partial index:

```sql
CREATE INDEX ix_documents_active_org_status_created
ON documents (
    organization_id,
    status,
    created_at DESC
)
WHERE deleted_at IS NULL;
```

Index chỉ chứa rows thỏa predicate. Nó có thể nhỏ hơn và hiệu quả cho truy vấn active documents.

**Không phải mọi database hỗ trợ partial indexes theo cùng cú pháp/khả năng.** MySQL có các lựa chọn khác; SQL Server có filtered indexes; Oracle có các kỹ thuật function-based/index strategies tương ứng.

### 12.3. Query predicate phải chứng minh được partial condition

Planner chỉ dùng partial/filtered index khi có thể xác định query predicate tương thích với điều kiện index. Nếu ORM sinh predicate khác expression, cast hoặc parameterization làm optimizer không chứng minh được, index có thể không được chọn.

Hãy lấy SQL thật và plan thật để xác nhận.

### 12.4. Tenant filter không phải permission

Index giúp query theo organization nhanh hơn; nó không xác minh user có membership hoặc quyền READ. Hiệu năng và authorization là hai vấn đề riêng.

## 13. Index cho JOIN predicates

Ví dụ:

```sql
SELECT o.id, c.name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.organization_id = ?
  AND c.active = true;
```

Các cột cần xem:

- `purchase_orders.organization_id`.
- `purchase_orders.customer_id`.
- `customers.id` (thường đã là PK/index).
- `customers.active` nếu query/workload khiến cột này có giá trị lọc đáng kể và join order phù hợp.

### 13.1. Index foreign key không luôn tự được tạo

Một số DB tự tạo index cho primary key/unique constraints, nhưng **không phải mọi foreign key đều tự có index**. Kiểm tra schema thật.

Index trên child FK thường hữu ích cho joins, parent deletes/updates và association loads:

```sql
CREATE INDEX ix_orders_customer
ON purchase_orders(customer_id);
```

Nếu mọi query còn scope tenant:

```sql
CREATE INDEX ix_orders_org_customer
ON purchase_orders(organization_id, customer_id);
```

có thể phù hợp hơn tùy workload.

### 13.2. Join algorithm quyết định giá trị index

Nested loop join thường cần lookup hiệu quả ở inner side. Hash join có thể scan và hash một side. Merge join cần ordered inputs. Không phải cứ có index trên cả hai FK thì planner sẽ dùng nested loop.

### 13.3. FK và tenant integrity

Trong shared-table multi-tenancy, FK chỉ theo global ID có thể chưa đủ ngăn cross-tenant association. Composite tenant-aware FK có thể bảo vệ integrity, còn index cần phù hợp thứ tự cột của constraint và query workload.

## 14. Covering index và index-only scan

Nếu query thường xuyên:

```sql
SELECT id, status, created_at
FROM purchase_orders
WHERE organization_id = ?
  AND customer_id = ?
ORDER BY created_at DESC
LIMIT 50;
```

Index có thể chứa các cột tìm kiếm/sắp xếp và cột cần trả về.

PostgreSQL hỗ trợ `INCLUDE`:

```sql
CREATE INDEX ix_orders_org_customer_created
ON purchase_orders (
    organization_id,
    customer_id,
    created_at DESC
)
INCLUDE (status);
```

DB có thể phục vụ projection từ index trong điều kiện thích hợp, giảm heap access. Nhưng PostgreSQL index-only scan còn phụ thuộc visibility map; không phải mọi query đều tránh heap hoàn toàn.

### 14.1. Covering index không có nghĩa đưa mọi cột vào index

Index quá rộng:

- Tốn disk và cache memory.
- Làm INSERT/UPDATE/DELETE đắt hơn.
- Tăng write amplification.
- Có thể vượt giới hạn kích thước index entry.
- Làm vacuum/maintenance nặng hơn.

Chỉ include những columns có lợi rõ cho query workload.

### 14.2. Projection DTO có thể giúp index-only

Nếu entity query hydrate 30 columns nhưng endpoint chỉ cần 3, covering index cho 3 columns khó tận dụng khi SQL vẫn SELECT tất cả 30 cột.

DTO projection:

```java
List<OrderSummary> summaries = em.createQuery("""
    select new com.example.OrderSummary(
        o.id,
        o.status,
        o.createdAt
    )
    from PurchaseOrder o
    where o.organizationId = :orgId
      and o.customer.id = :customerId
    order by o.createdAt desc
    """, OrderSummary.class)
    .setParameter("orgId", orgId)
    .setParameter("customerId", customerId)
    .getResultList();
```

có thể tạo SELECT hẹp hơn, giúp index covering có cơ hội phát huy. Kiểm tra SQL thực tế để xác nhận.

## 15. Index selectivity và phân bố dữ liệu

Index trên một cột có cardinality thấp như `active` (true/false) có thể ít hữu ích nếu một giá trị chiếm hầu hết bảng.

Ví dụ:

```text
active = true: 98% rows
active = false: 2% rows
```

Một index riêng trên `active` có thể không giúp query lấy 98% rows; database có thể chọn table scan.

### 15.1. Selectivity không chỉ là distinct count

Cần hiểu phân bố values. Cột có 100 distinct values vẫn có thể skew nặng nếu một value chiếm 90%.

### 15.2. Composite index thay đổi selectivity

`organization_id` có thể có ít distinct values, nhưng kết hợp `customer_id` tạo tập rất hẹp. Một index `(organization_id, customer_id)` có thể hữu ích dù index riêng từng cột không hấp dẫn.

### 15.3. Workload nhiều tenants

Tenant lớn nhất có thể chứa 60% rows, tenant nhỏ chỉ 0.01%. Một query cùng SQL shape nhưng parameter org khác nhau có selectivity rất khác. Cần test cả tenant lớn và tenant nhỏ.

## 16. Parameter sniffing và generic/custom plans

Database có thể lập plan dựa trên bind values hoặc dùng prepared/generic plan được tái sử dụng, tùy engine/driver/configuration.

Một query:

```sql
WHERE organization_id = ?
  AND status = ?
```

có thể rất khác giữa tenant có 100 rows và tenant có 10 triệu rows.

### 16.1. PostgreSQL prepared statements

PostgreSQL có thể dùng custom plans hoặc generic plans cho prepared statements tùy execution history/configuration. Một generic plan có thể không tối ưu cho các parameter distributions skewed.

### 16.2. SQL Server parameter sniffing

SQL Server có thể compile plan dựa trên parameter values khi compile/recompile, và reuse plan cho những values khác. Một plan tốt cho tenant nhỏ có thể kém cho tenant lớn.

### 16.3. MySQL và driver behavior

Prepared statement/optimizer behavior phụ thuộc MySQL version, driver mode và execution strategy. Không áp dụng thuật ngữ/giải pháp của PostgreSQL hoặc SQL Server máy móc.

### 16.4. Cách điều tra

- So sánh plan với parameter values đại diện.
- Xem estimated vs actual rows.
- Xác định query có parameter skew.
- Xem plan cache/recompile/generic-plan behavior của DB.
- Cân nhắc query rewrite, statistics, index hoặc chiến lược DB-specific sau khi đo.

Không vội thêm hint/force index trước khi hiểu parameter distribution.

## 17. Index và Hibernate pagination

Spring Data:

```java
Page<PurchaseOrder> page =
    repository.findByOrganizationIdAndStatus(
        orgId,
        status,
        PageRequest.of(
            0,
            50,
            Sort.by(Sort.Direction.DESC, "createdAt")
        )
    );
```

SQL có thể gồm SELECT page và COUNT query. Cần tối ưu cả hai query shapes.

### 17.1. Index cho page query

Candidate có thể là:

```sql
(organization_id, status, created_at DESC, id DESC)
```

Cột `id` là tie-breaker giúp ordering ổn định khi nhiều rows có cùng created_at.

### 17.2. Count query có thể cần index khác

```sql
SELECT count(*)
FROM purchase_orders
WHERE organization_id = ?
  AND status = ?;
```

Index `(organization_id, status)` có thể đủ cho count. Nếu một index rộng đã có prefix tương thích, có thể reuse; nhưng plan/visibility/engine behavior vẫn phải xác nhận.

### 17.3. OFFSET lớn

Index có thể giúp tìm thứ tự, nhưng database vẫn phải đi qua các rows bị offset. Keyset pagination thường ổn định hơn cho trang sâu.

### 17.4. Sort order và nulls

`ORDER BY created_at DESC NULLS LAST` hoặc semantics tương tự phụ thuộc database. Index direction/collation/null ordering cần tương thích; không suy từ DESC đơn thuần.

## 18. Function, collation và case-insensitive search

Ví dụ:

```sql
WHERE email = ?
```

có thể dùng B-tree nếu collation/type/operator phù hợp.

Nhưng:

```sql
WHERE LOWER(email) = LOWER(?)
```

có thể cần expression index hoặc normalized column.

### 18.1. Unicode và collation

So sánh case-insensitive, accent-insensitive và Unicode normalization có semantics khác nhau theo collation/DB. Không tự lowercase trong Java rồi cho rằng tương đương DB collation.

### 18.2. LIKE và full-text

Prefix search `LIKE 'abc%'` khác substring `LIKE '%abc%'`. Với search semantics phức tạp, dùng full-text/trigram/search engine phù hợp hơn là thêm B-tree index vô ích.

### 18.3. Criteria builder có thể tạo casts/functions

Một Criteria expression hoặc converter có thể khiến SQL bao cột trong function/cast. Kiểm tra SQL thật trước khi kết luận index không được dùng vì “JPQL chỉ so sánh field”.

## 19. OR, IN và predicate động

Hibernate query builder có thể tạo:

```sql
WHERE organization_id = ?
  AND (
       status = ?
       OR assigned_user_id = ?
  )
```

hoặc:

```sql
WHERE id IN (?, ?, ?, ...)
```

### 19.1. OR có thể cần nhiều index

Database có thể dùng index merge/bitmap OR nếu có index riêng phù hợp, hoặc chọn scan. Một composite index không phải lúc nào tối ưu cho cả hai nhánh.

### 19.2. IN list lớn

Một danh sách hàng chục nghìn IDs có thể tạo SQL lớn, nhiều bind parameters, plan overhead và giới hạn DB. Cân nhắc:

- Chunk IDs.
- Temporary/staging table.
- Join với table-valued parameter/array mechanism theo DB.
- Bulk query với scoped predicates.
- Batch processing thay vì một câu query khổng lồ.

### 19.3. Query shape biến đổi

Nếu một query builder thêm/bỏ predicates theo filter người dùng, mỗi shape có thể có plan khác. Không thiết kế một index theo một trường hợp duy nhất rồi mong mọi combinations đều nhanh.

## 20. Index có chi phí ghi

Mỗi index thêm vào table có thể làm:

- INSERT phải cập nhật index.
- UPDATE indexed columns phải cập nhật index.
- DELETE phải loại entries.
- Disk/storage và backup tăng.
- Cache memory bị phân tán.
- Vacuum/maintenance và replication write volume tăng.

### 20.1. Đánh giá workload đọc/ghi

Một bảng orders có hàng triệu inserts mỗi ngày nhưng một report query chạy 2 lần/ngày có thể không đáng thêm 5 indexes rộng. Ngược lại một endpoint đọc cực thường xuyên có thể xứng đáng index chuyên biệt.

### 20.2. Index trùng lặp

Index `(organization_id, customer_id)` và `(organization_id, customer_id, status)` có prefix overlap. Không nhất thiết cả hai đều cần; nhưng index ngắn có thể nhỏ và hữu ích hơn cho một workload khác. Xem usage stats và query plan trước khi drop.

### 20.3. Index unused

DB usage statistics có thể giúp nhận diện indexes ít được scan, nhưng uptime, reset counters, replica role và seasonal workloads ảnh hưởng kết quả. Không drop index chỉ vì usage thấp trong một cửa sổ ngắn.

## 21. Hibernate mapping và index DDL

JPA có annotation:

```java
@Table(
    name = "purchase_orders",
    indexes = {
        @Index(
            name = "ix_orders_customer_status",
            columnList = "customer_id, status"
        )
    }
)
@Entity
public class PurchaseOrder {
    // ...
}
```

Đây có thể là metadata cho schema generation khi dùng DDL auto/create. Nhưng trong production, schema thường được quản lý bằng Flyway/Liquibase hoặc migrations tương đương.

### 21.1. Annotation không chứng minh index tồn tại

Nếu dùng `ddl-auto=validate`, Hibernate không tự tạo index. Nếu schema được provision bên ngoài, phải kiểm tra migration và DB catalog.

### 21.2. Mapping column names

`columnList` dùng physical column names theo annotation/JPA schema metadata, không phải lúc nào cũng là Java property names. Kiểm tra naming strategy, quoting và tên vật lý thật.

### 21.3. Index expression/partial/include

JPA `@Index` portable chủ yếu cho column indexes. Partial indexes, expression indexes, INCLUDE columns, operator classes và filtered indexes thường cần DB-specific migrations.

Không cố nhồi database-specific design vào annotation portable nếu schema tooling không hỗ trợ.

## 22. Kiểm tra indexes hiện có

Trước khi tạo index, đọc schema catalog.

### 22.1. PostgreSQL

Ví dụ:

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'purchase_orders';
```

Có thể dùng `pg_stat_user_indexes` để xem scans/tuples, đồng thời kiểm tra reset time và workload window.

### 22.2. MySQL

Dùng:

```sql
SHOW INDEX FROM purchase_orders;
```

Kết hợp `EXPLAIN`, optimizer trace và performance schema phù hợp.

### 22.3. SQL Server

Dùng catalog views như `sys.indexes`, `sys.index_columns`, `sys.columns` và execution plans/Query Store.

### 22.4. Oracle

Dùng data dictionary views như `USER_INDEXES`, `USER_IND_COLUMNS`, `USER_IND_EXPRESSIONS` và plan tools.

Câu SQL catalog cụ thể phụ thuộc privileges/schema và database version.

## 23. Cập nhật database statistics sau thay đổi lớn

Index có thể tồn tại nhưng planner chưa có thống kê tốt về distribution/cardinality.

### 23.1. PostgreSQL

```sql
ANALYZE purchase_orders;
```

PostgreSQL cũng có autovacuum/analyze. Nếu cột có skew hoặc correlation, có thể cần statistics target/extended statistics sau khi đo.

### 23.2. MySQL

InnoDB persistent statistics và histogram có thể cần được cập nhật/quản lý theo phiên bản, storage engine và optimizer settings.

### 23.3. SQL Server

Auto statistics, update statistics và cardinality estimator ảnh hưởng plan. Xem Query Store/actual plan trước khi chạy update hàng loạt.

### 23.4. Statistics không thay index

ANALYZE có thể giúp optimizer chọn plan tốt hơn cho indexes hiện có; nó không tự tạo access path mới nếu query cần một index không tồn tại.

## 24. Dùng EXPLAIN ANALYZE cẩn thận

`EXPLAIN ANALYZE` thực thi query thật. Với SELECT nặng, nó vẫn tiêu thụ CPU, IO, locks và memory. Với DML, nó có thể thay đổi dữ liệu.

### 24.1. Môi trường phù hợp

- Staging có data distribution gần production.
- Production read-only query được đánh giá an toàn và chạy trong cửa sổ kiểm soát.
- Replica có cấu hình tương đương, nhưng cần hiểu replication lag và plan differences.
- Dataset anonymized/representative.

### 24.2. DML thử nghiệm

Trong PostgreSQL có thể dùng transaction:

```sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
UPDATE purchase_orders
SET status = 'ARCHIVED'
WHERE created_at < TIMESTAMP '2024-01-01';
ROLLBACK;
```

Nhưng rollback không hoàn tác mọi thứ bên ngoài transactional semantics, chẳng hạn sequence advancement, external triggers/integrations hoặc side effects tùy hệ thống. Không chạy thử DML tùy tiện trên production.

### 24.3. Đo nhiều lần

Cold cache và warm cache có thể cho latency rất khác. So sánh cùng conditions, nhiều lần, ghi median/percentiles và xem variance. Không lấy một execution duy nhất làm kết luận.

## 25. Index hints và force index

Một số database cho phép hints/force index. Đây là công cụ cuối cùng sau khi hiểu plan.

### 25.1. Vì sao ép index có thể làm tệ hơn?

- Data distribution thay đổi.
- Tenant sizes thay đổi.
- Statistics được cập nhật.
- Query parameters có selectivity khác.
- Index bị bloated/fragmented.
- Một scan tốt hơn index random IO.

### 25.2. Hibernate không tự chọn index

Hibernate sinh SQL; database optimizer chọn index. ORM mapping không thể bảo đảm DB dùng một index cụ thể.

### 25.3. Hints là database-specific

Nếu dùng hint trong SQL comment/query API/StatementInspector, phải xác nhận dialect, vị trí syntax, plan và behavior khi upgrade. Không thêm hint bằng regex chung cho mọi query.

## 26. N+1: index không chữa được số lượng round trips

Giả sử query:

```sql
select o.id, o.customer_id
from purchase_orders o
where o.organization_id = ?;
```

sau đó mỗi Order phát sinh:

```sql
select l.*
from order_lines l
where l.order_id = ?;
```

Index `order_lines(order_id)` có thể làm mỗi lookup nhanh, nhưng vẫn có 100 SELECTs cho 100 orders.

### 26.1. Hai vấn đề khác nhau

- **Access path**: một câu query có dùng index hiệu quả không?
- **Query count**: ứng dụng có phát sinh quá nhiều queries không?

Index giải quyết access path; fetch plan/batch fetching/DTO projection giải quyết N+1.

### 26.2. Kết hợp tối ưu

Có thể cần cả:

```sql
CREATE INDEX ix_order_lines_order
ON order_lines(order_id);
```

và mapping/query:

```java
@BatchSize(size = 32)
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Hoặc query DTO/join fetch phù hợp. Đo statement count và plan từng query.

## 27. Bulk predicates và index khi update/delete

Một background job:

```sql
UPDATE purchase_orders
SET status = 'ARCHIVED'
WHERE organization_id = ?
  AND status = 'CLOSED'
  AND created_at < ?;
```

Index candidate:

```sql
(organization_id, status, created_at)
```

Equality predicates trước, range sau là điểm bắt đầu hợp lý để thử. Nhưng nếu tỷ lệ rows cần update rất lớn, sequential scan có thể nhanh hơn index; index cũng làm mỗi updated row tốn thêm maintenance.

### 27.1. Update index columns

Nếu query update `status` và index chứa `status`, DB cần duy trì index entries. Với PostgreSQL, HOT updates chỉ có thể áp dụng trong những điều kiện cụ thể; indexed columns thường ảnh hưởng khả năng HOT update.

### 27.2. Batch/chunk processing

Một câu UPDATE hàng triệu rows có thể giữ locks lâu và tạo transaction lớn. Chunking theo key/time range có thể giảm lock duration, nhưng cần đảm bảo progress, idempotency và consistency.

### 27.3. Hibernate bulk DML

Bulk HQL/JPQL SQL thực tế có thể khác query entity SELECT. Lấy đúng UPDATE/DELETE SQL, xem plan của mutation và đừng suy từ plan SELECT cùng bảng.

## 28. Index cho soft-delete rows

Nếu phần lớn truy vấn luôn chỉ lấy active records:

```sql
WHERE deleted_at IS NULL
```

PostgreSQL partial index có thể nhỏ và hiệu quả:

```sql
CREATE INDEX ix_active_orders_org_created
ON purchase_orders (organization_id, created_at DESC)
WHERE deleted_at IS NULL;
```

### 28.1. Query restore/admin

Một query cần xem deleted rows:

```sql
WHERE organization_id = ?
  AND deleted_at IS NOT NULL
```

không dùng partial index active. Có thể cần index khác cho admin/retention workload, nhưng không tạo chỉ vì một đường hiếm nếu table nhỏ hoặc scan chấp nhận được.

### 28.2. Soft delete và unique constraints

Nếu chỉ active records cần unique, một partial unique index có thể phù hợp (DB hỗ trợ):

```sql
CREATE UNIQUE INDEX ux_active_order_external_ref
ON purchase_orders(organization_id, external_ref)
WHERE deleted_at IS NULL;
```

Phải xem restore conflicts và concurrency. ORM filter không thay unique constraint.

## 29. SQL do Hibernate sinh có thể chứa casts và aliases

Hibernate có thể render:

```sql
select p1_0.id, p1_0.created_at
from purchase_orders p1_0
where p1_0.organization_id = cast(? as uuid)
```

hoặc casts/functions khác do type mapping, dialect và parameter binding.

### 29.1. Xem data types

Cột UUID, enum, timestamp, numeric, JSON và custom types cần bind đúng SQL type. Nếu DB phải cast cột thay vì parameter, index usage có thể bị ảnh hưởng.

### 29.2. Alias không quan trọng cho index

Tên alias `p1_0` thường không ảnh hưởng lựa chọn index, nhưng expressions và join predicates phía sau thì có.

### 29.3. Quoted identifiers

Nếu mapping dùng quoted/case-sensitive names, migration/index DDL phải khớp tên vật lý. SQL log cho thấy tên thực tế.

## 30. Đọc plan cho join + filter + pagination

Query:

```sql
SELECT o.id, o.created_at, c.name
FROM purchase_orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.organization_id = ?
  AND o.status = ?
  AND c.active = true
ORDER BY o.created_at DESC
LIMIT 50;
```

Cần phân tích:

1. Database bắt đầu từ Orders hay Customers?
2. Có dùng index cho `organization_id`/`status`?
3. Customer join dùng PK/unique index hay scan?
4. `c.active` được áp trước/sau join?
5. Có sort node lớn không?
6. Limit có dừng sớm được không?
7. Estimated vs actual rows có lệch?
8. Có lookup lặp trong nested loop?
9. Projection có đọc nhiều cột không cần thiết?

Một index đơn lẻ trên mỗi predicate không bảo đảm plan tối ưu. Join order và cardinality quyết định cách kết hợp.

## 31. Query shape từ ORM: SELECT entity hay DTO projection?

Nếu repository trả entity:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o from PurchaseOrder o
    where o.organizationId = :orgId
    """, PurchaseOrder.class)
    .setParameter("orgId", orgId)
    .getResultList();
```

Hibernate có thể SELECT nhiều columns cần hydrate entity.

Nếu endpoint chỉ cần:

```java
public record OrderListItem(
    Long id,
    String status,
    Instant createdAt
) {}
```

projection:

```java
List<OrderListItem> rows = em.createQuery("""
    select new com.example.OrderListItem(
        o.id, o.status, o.createdAt
    )
    from PurchaseOrder o
    where o.organizationId = :orgId
    order by o.createdAt desc
    """, OrderListItem.class)
    .setParameter("orgId", orgId)
    .getResultList();
```

SQL có thể hẹp hơn, giảm row width và tăng cơ hội covering index. Nhưng phải lấy SQL thực tế xác nhận Hibernate không thêm columns/joins ngoài dự kiến.

## 32. Thứ tự index columns: một ví dụ phân tích

Query A:

```sql
WHERE organization_id = ?
  AND customer_id = ?
ORDER BY created_at DESC
LIMIT 50;
```

Query B:

```sql
WHERE organization_id = ?
  AND status = ?
ORDER BY created_at DESC
LIMIT 50;
```

Query C:

```sql
WHERE organization_id = ?
  AND created_at >= ?
ORDER BY created_at DESC
LIMIT 50;
```

Một index `(organization_id, customer_id, created_at)` phù hợp Query A hơn; không thay thế đầy đủ index cho Query B. Index `(organization_id, status, created_at)` phù hợp B; index `(organization_id, created_at)` có thể phù hợp C.

Không nhất thiết tạo cả ba. Xếp hạng theo frequency, latency, criticality, write rate, storage và mức overlap. Có thể một query ít quan trọng chấp nhận scan.

## 33. Database plan và Hibernate query-plan cache là hai thứ khác nhau

Hibernate có thể cache query interpretation/plan cho HQL/Criteria. Database có thể cache execution plans/prepared statements riêng.

```text
JPQL/HQL
   |
   v
Hibernate query interpretation/plan cache
   |
   v
SQL + bind parameters
   |
   v
JDBC driver / prepared statement
   |
   v
Database optimizer / execution plan cache
   |
   v
Index scan, joins, sort, execution
```

Một Hibernate plan cache hit không chứng minh database dùng index tốt. Một DB plan cache hit cũng không chứng minh plan phù hợp với mọi parameter distribution.

## 34. Benchmark trước và sau khi thêm index

Một bảng so sánh nên có:

| Chỉ số | Trước | Sau |
|---|---:|---:|
| SQL shape | Ghi nhận | Ghi nhận |
| Actual rows scanned/read | ... | ... |
| Rows returned | ... | ... |
| Execution time p50/p95 | ... | ... |
| Buffers/IO | ... | ... |
| Sort spill/temp usage | ... | ... |
| Index used | ... | ... |
| Hibernate prepared statements | ... | ... |
| Entity/collection loads | ... | ... |
| Insert/update latency | ... | ... |
| Index size | ... | ... |

### 34.1. Cùng dữ liệu và cùng parameters

Benchmark phải giữ:

- Cùng database engine/version.
- Dataset có phân bố tương tự production.
- Cùng query text và bind types.
- Parameter values đại diện cho tenant nhỏ/lớn, status phổ biến/hiếm.
- Cache state được xác định.
- Concurrent load tương tự nếu mục tiêu là production latency.

### 34.2. Đo write regression

Index mới có thể tăng read performance nhưng làm writes chậm hơn. Benchmark insert/update/delete và bulk jobs trước khi chấp nhận.

### 34.3. Không chỉ so cost estimate

Optimizer cost là estimate nội bộ, không phải milliseconds. So actual timings, buffers/IO và workload-level p95/p99.

## 35. Index maintenance và vận hành

Một index mới cần:

- Migration tạo index an toàn.
- Lock impact được đánh giá.
- Build concurrently/online nếu DB hỗ trợ và phù hợp.
- Storage budget.
- Backup/replication impact.
- Monitoring index bloat/fragmentation theo engine.
- Kế hoạch rollback/drop nếu không cải thiện.

Ví dụ PostgreSQL:

```sql
CREATE INDEX CONCURRENTLY ix_orders_org_status_created
ON purchase_orders (
    organization_id,
    status,
    created_at DESC
);
```

`CONCURRENTLY` có transaction/operational restrictions riêng; migration tool có thể cần cấu hình không chạy trong transaction. Không copy cú pháp này sang DB khác.

## 36. Một quy trình thực tế: query chậm trong Hibernate

Giả sử endpoint list orders p95 tăng từ 100 ms lên 900 ms.

### Bước 1: xác nhận query

Thu SQL thật sau Hibernate, gồm:

- SELECT columns.
- Joins.
- WHERE predicates.
- ORDER BY/LIMIT/OFFSET.
- Soft-delete/tenant restrictions.
- Bind values/types đã redacted phù hợp.

### Bước 2: kiểm tra số SQL

Dùng Hibernate Statistics/JDBC tracing để xác định:

- Có N+1 không?
- Có count query phụ không?
- Có flush trước SELECT không?
- Có lazy association loads sau query chính không?

### Bước 3: xem indexes

Kiểm tra catalog: index nào tồn tại, cột thứ tự nào, partial condition/include columns, index usage, statistics freshness.

### Bước 4: lấy plan

Chạy EXPLAIN/actual plan trên data/parameters đại diện. Tìm:

- Seq/table scan.
- Index scan/seek.
- Rows estimate mismatch.
- Join order/algorithm.
- Sort/hash spill.
- Filter loại nhiều rows sau scan.
- Buffers/IO.

### Bước 5: đưa ra giả thuyết cụ thể

Ví dụ: query filter theo `organization_id` và `status`, sort theo `created_at`, nhưng plan scan 2 triệu rows rồi sort. Candidate index `(organization_id, status, created_at DESC)` có thể giảm rows cần đọc.

### Bước 6: kiểm chứng

Tạo migration trên staging, chạy cùng query và workload, so plan/timing/IO, sau đó đo write regression.

### Bước 7: khóa bằng test

Integration/performance test đảm bảo SQL/query budget và kết quả đúng. Không test rằng optimizer **bắt buộc** dùng một node exact nếu plan có thể thay đổi hợp lệ theo stats/version.

## 37. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Tạo index chỉ từ JPQL | Index không khớp SQL thực | Thu SQL sau Hibernate |
| Bỏ qua bind values | Plan khác giữa parameter distributions | Xem types/representative values an toàn |
| Coi Seq Scan luôn xấu | Ép index gây chậm | Đọc actual rows/selectivity |
| Coi Index Scan luôn tốt | Đọc nhiều heap pages | Xem buffers/actual rows |
| Chỉ xem estimated plan | Bỏ qua estimate sai | Dùng actual plan khi an toàn |
| Dùng EXPLAIN ANALYZE tùy tiện trên DML production | Thay đổi dữ liệu/locks | Staging hoặc quy trình an toàn |
| Index mỗi cột một cái | Tốn storage/write và plan kém | Thiết kế composite theo query shapes |
| Đặt columns tùy tiện trong composite index | Không tận dụng leading prefix/order | Phân tích equality/range/order |
| Quên soft-delete predicate | Query active vẫn scan rộng | Xem partial/filtered index nếu DB hỗ trợ |
| Quên tenant predicate | Index/query thiếu scope và có thể sai security | Scope rõ; index theo workload tenant |
| Thêm index cho mọi tenant query | Index proliferation | Ưu tiên query frequency/latency |
| Hàm/cast trên indexed column | Predicate khó sargable | Expression index hoặc range rewrite |
| LIKE '%term%' dùng B-tree thường | Index không seek prefix | Full-text/trigram phù hợp |
| Ép FORCE INDEX quá sớm | Plan tệ với data khác | Cập nhật stats, đo parameters |
| Chỉ tối ưu SELECT | INSERT/UPDATE chậm hơn | Đo write amplification |
| Fetch join nhiều collections | Cartesian product/heap tăng | Bounded fetch plan/DTO |
| Nghĩ index chữa N+1 | N queries vẫn là N round trips | Batch fetching/fetch plan |
| Chỉ nhìn query count | Bỏ qua rows/bytes/sort | Actual plan và latency |
| Dùng Hibernate plan cache làm DB plan | Kết luận sai | Phân biệt hai tầng cache |
| Test chỉ với tenant nhỏ | Không thấy parameter skew | Test phân bố đại diện |
| Test warm cache duy nhất | Cold path chậm | Đo cold và warm |
| Tạo index annotation rồi tưởng production có | Migration chưa chạy | Kiểm tra schema/catalog |
| Drop index vì usage thấp một ngày | Mất access path theo mùa | Quan sát đủ workload window |
| Gắn raw SQL vào metric labels | High cardinality/PII | Labels hữu hạn, traces/logs có bảo vệ |

## 38. Bài tập 1: chọn index cho equality + range

SQL:

```sql
SELECT id, amount
FROM invoices
WHERE organization_id = ?
  AND status = ?
  AND issued_at >= ?
ORDER BY issued_at DESC;
```

**Câu hỏi:** Index candidate nào đáng thử?

**Gợi ý:**

```sql
(organization_id, status, issued_at DESC)
```

Hai equality predicates đứng trước range/order column là điểm bắt đầu hợp lý. Xác nhận bằng plan và workload; không coi đây là câu trả lời tuyệt đối cho mọi database.

## 39. Bài tập 2: predicate không sargable

SQL:

```sql
WHERE DATE(created_at) = ?
```

**Câu hỏi:** Vì sao index B-tree thông thường trên created_at có thể không được dùng hiệu quả?

**Giải thích:** Hàm DATE được áp lên cột; database phải đánh giá expression. Có thể rewrite thành khoảng `created_at >= start` và `created_at < nextDay`, hoặc dùng expression index phù hợp.

## 40. Bài tập 3: soft delete và partial index

Query active records:

```sql
WHERE organization_id = ?
  AND deleted_at IS NULL
  AND status = ?
```

**Câu hỏi:** PostgreSQL có thể dùng index nào?

**Gợi ý:**

```sql
CREATE INDEX ix_active_org_status
ON documents (organization_id, status)
WHERE deleted_at IS NULL;
```

Cần xác minh planner chứng minh được predicate và index có lợi cho data distribution.

## 41. Bài tập 4: một SQL nhưng entity load cao

Một JOIN FETCH trả 1.000 Orders và 50.000 OrderLines trong một SQL.

**Câu hỏi:** Vì sao endpoint vẫn có thể chậm?

**Giải thích:** SQL row volume, hydration, object allocation, memory, serialization và GC có thể lớn. Giảm query count không đồng nghĩa giảm lượng dữ liệu.

## 42. Bài tập 5: index không chữa N+1

Một request tạo 51 SELECTs; mỗi SELECT order_lines dùng index PK/FK rất nhanh.

**Câu hỏi:** Chỉ tạo index tốt hơn trên order_id có loại bỏ N+1 không?

**Giải thích:** Không. Nó làm từng lookup nhanh hơn nhưng số round trips vẫn cao. Cần fetch join/batch fetching/DTO hoặc two-phase query phù hợp.

## 43. Bài tập 6: parameter skew

Cùng SQL filter `organization_id`:

- Tenant A có 100 documents.
- Tenant B có 8 triệu documents.

**Câu hỏi:** Một plan reused có luôn tối ưu cho cả hai không?

**Giải thích:** Không chắc. Parameter selectivity và plan caching/sniffing khác nhau theo DB. Xem actual plans/rows với cả hai distributions.

## 44. Bài tập 7: index hiện có nhưng plan vẫn scan

Table nhỏ có 2.000 rows, query trả 1.700 rows, B-tree index tồn tại.

**Câu hỏi:** Seq Scan có phải bug không?

**Giải thích:** Không. Đọc phần lớn bảng bằng sequential scan có thể rẻ hơn index lookup rồi heap access. Plan phải được đánh giá bằng actual performance.

## 45. Bài tập 8: count query của Page

Một endpoint dùng `Page<PurchaseOrder>` và SQL count query chậm.

**Câu hỏi:** Index tối ưu SELECT page có chắc tối ưu count không?

**Giải thích:** Không. Count query có SQL shape/projection riêng. Lấy cả hai SQL, xem plan và cân nhắc index prefix tương thích.

## 46. Checklist đối chiếu SQL, index và execution plan

1. **SQL thực:** đã lấy SQL do Hibernate thật sự sinh chưa?
2. **Use case:** đã chạy hết service và DTO mapping, không chỉ repository call?
3. **Query count:** có N+1, count query hoặc lazy loads bổ sung?
4. **Bind values:** có parameter values/types đại diện và được redacted?
5. **Predicates:** đã liệt kê equality, IN, range, null, OR và soft-delete/tenant filters?
6. **Joins:** ON/WHERE predicates và outer join semantics có đúng?
7. **Ordering:** ORDER BY direction, null ordering, tie-breaker và pagination?
8. **Projection:** có đang SELECT nhiều entity columns không cần?
9. **Schema:** physical column names/types/collations đúng?
10. **Indexes:** catalog xác nhận index thực sự tồn tại?
11. **Composite order:** leading columns hỗ trợ query shape?
12. **Partial/filtered:** predicate của index có tương thích SQL?
13. **Covering:** có giảm heap access đáng kể mà không làm index quá rộng?
14. **Selectivity:** data distribution có skew theo tenant/status/time?
15. **Sargability:** functions/casts/leading wildcard/implicit conversions?
16. **Plan:** scan, seek, joins, sorts, filters và aggregates?
17. **Estimates:** estimated rows lệch actual rows bao nhiêu?
18. **Statistics:** DB statistics có mới sau bulk data changes?
19. **IO:** buffers, physical/logical reads, temp spills?
20. **Parameters:** generic/custom plan hoặc parameter sniffing?
21. **Writes:** index mới làm INSERT/UPDATE/DELETE chậm bao nhiêu?
22. **ORM cache:** cold/warm L1/L2/query cache đã được tách?
23. **JDBC:** prepare count và batch execution đã được phân biệt?
24. **Pagination:** OFFSET sâu hay keyset phù hợp?
25. **N+1:** đã tách query count khỏi index access path?
26. **Version:** SQL/dialect/plan có khác sau Hibernate/DB upgrade?
27. **Migration:** index được tạo bằng schema migration và rollback plan?
28. **Production safety:** EXPLAIN ANALYZE có thực thi query/DML và gây tải?
29. **Benchmark:** cùng data, parameters, concurrency và cache conditions?
30. **Kết quả:** latency, IO, memory và write performance có cải thiện?

## 47. Ghi nhớ

- **Database tối ưu SQL thực tế Hibernate sinh**, không tối ưu trực tiếp JPQL/HQL source.
- Lấy SQL logs/JDBC trace để thấy joins, predicates, order, pagination và SQL bổ sung do lazy loading/flush.
- Bind values và JDBC types ảnh hưởng selectivity/plan; phải quan sát an toàn, không tự nối placeholders thành SQL.
- `EXPLAIN` cho estimated plan; `EXPLAIN ANALYZE` (hoặc actual plan tương ứng DB) thực thi query và cung cấp actual rows/timing theo engine.
- **Seq Scan không mặc định xấu và Index Scan không mặc định tốt**; đánh giá actual rows, IO, cardinality và workload.
- Composite B-tree indexes cần được thiết kế theo query shapes: equality, range, ordering và leading-prefix behavior; không có thứ tự cột thần kỳ cho mọi workload.
- Partial/filtered indexes cho active/tenant subsets có thể hữu ích khi database hỗ trợ và planner chứng minh predicate tương thích.
- Functions, casts, implicit conversions và leading wildcard có thể làm predicate kém sargable; xem expression index, normalized columns hoặc range rewrite.
- Covering indexes có thể giảm heap access nhưng tăng storage và write amplification.
- Index trên FK/join columns hữu ích khi plan cần lookup, nhưng join algorithm và cardinality quyết định optimizer sử dụng ra sao.
- **Index không loại bỏ N+1**; nó chỉ cải thiện từng access path. Fetch plan, batching và DTO projection giải quyết số lần truy vấn.
- Hibernate query-plan cache khác query-result cache, L2 cache và database execution-plan cache.
- Parameter skew theo tenant/status có thể làm một plan không phù hợp mọi values; thử parameters đại diện và đọc actual plan.
- Dùng schema migration để quản lý index production; annotation JPA không chứng minh index đã tồn tại.
- Đo cả read và write workload; index mới có thể cải thiện SELECT nhưng làm INSERT/UPDATE/DELETE đắt hơn.
- Kết luận tối ưu dựa trên latency, IO, rows, memory và correctness, không chỉ một node hoặc cost estimate.

**Kết luận:** Đối chiếu index và execution plan trong Hibernate phải bắt đầu từ **SQL thực và predicates thực** mà ORM gửi đến database. Sau khi hiểu bind values, join order, filter selectivity, ordering và pagination, hãy đọc plan để biết database đang scan/seek/sort/join như thế nào và estimate có sát actual rows không. Chọn index theo workload đã đo, đồng thời cân nhắc fetch plan, DTO projection và batching khi vấn đề là N+1 hoặc over-fetching. Cuối cùng, chạy lại cùng dữ liệu và parameter distributions, kiểm tra read/write latency cùng IO, rồi khóa hành vi bằng migration và integration/performance tests.
