# Kiểm tra số truy vấn, số hàng và kích thước kết quả thay vì chỉ nhìn annotation trong Hibernate

Khi tối ưu Hibernate, việc đọc mapping và thấy `FetchType.LAZY`, `FetchType.EAGER`, `@BatchSize` hoặc `JOIN FETCH` chưa đủ để kết luận một use case chạy hiệu quả. Annotation mô tả một phần cách ORM quản lý và tải dữ liệu; hiệu năng thực tế còn phụ thuộc query được thực thi, số hàng database trả về, số entity/collection được materialize, lượng dữ liệu truyền qua JDBC và phần dữ liệu ứng dụng thật sự sử dụng.

Một endpoint có thể chỉ chạy **một câu SQL** nhưng trả hàng trăm nghìn hàng do join nhiều collection. Một endpoint khác chạy vài câu SQL nhưng mỗi câu chỉ trả một nhóm nhỏ, được phân trang và có tổng chi phí thấp hơn. Ngược lại, một danh sách 50 entity có thể phát 51 câu SELECT vì N+1, dù mỗi truy vấn riêng lẻ rất nhanh.

Vì vậy, khi đánh giá fetch plan, cần quan sát ít nhất ba nhóm chỉ số:

1. **Số truy vấn/statement**: ứng dụng gửi bao nhiêu câu SQL và chúng được thực thi bao nhiêu lần?
2. **Số hàng**: database trả bao nhiêu hàng, query đọc/quét bao nhiêu hàng, Hibernate materialize bao nhiêu entity hoặc collection element?
3. **Kích thước kết quả**: bao nhiêu dữ liệu được truyền, giữ trong bộ nhớ và trả ra API?

Các chỉ số này trả lời những câu hỏi khác nhau. Không thể dùng một con số thay thế cho tất cả. Bài học trình bày cách đo từ Hibernate, JDBC và database, cách đọc kết quả khi có N+1 hoặc join multiplication, cùng quy trình benchmark có thể lặp lại.

## 1. Vì sao annotation không đủ để dự đoán hiệu năng?

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;

@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
private List<PurchaseOrder> orders = new ArrayList<>();
```

Mapping cho biết các association có thể được tải trì hoãn. Nó không trả lời:

- Một request có truy cập `customer` hay `orders` không?
- Collection có được tải riêng cho từng customer hay được batch?
- Entity đã nằm trong first-level cache hoặc second-level cache chưa?
- Query có thêm fetch join hoặc entity graph không?
- Có auto-flush chạy trước query không?
- Mỗi customer có 2 order hay 20.000 order?
- Join có nhân hàng vì nhiều collection cùng tham gia không?
- Ứng dụng đọc toàn bộ kết quả hay chỉ đọc trang đầu?

Tương tự, `FetchType.EAGER` yêu cầu association sẵn sàng theo fetch plan, nhưng không cam kết một câu SQL duy nhất. Hibernate có thể dùng join hoặc select bổ sung tùy đường truy vấn. Một mapping EAGER có thể tạo N+1 nếu danh sách root được truy vấn mà association không được join phù hợp.

**Annotation là đầu vào của kế hoạch tải; SQL và dữ liệu thực tế mới cho thấy chi phí của kế hoạch đó.**

## 2. Ba nhóm số liệu và những gì chúng thực sự đo

Trước khi bật công cụ, hãy thống nhất định nghĩa. Nếu hai người cùng nói “query count” nhưng một người đếm JPQL và người kia đếm JDBC statement, số liệu sẽ không thể so sánh.

| Nhóm số liệu | Ví dụ | Trả lời câu hỏi |
|---|---|---|
| Query/statement count | 1 HQL execution, 8 JDBC SELECT, 2 UPDATE | Ứng dụng phát bao nhiêu lần truy vấn/ghi? |
| Database rows | 5.000 rows returned, 80.000 rows scanned | SQL trả bao nhiêu hàng hoặc database phải xử lý bao nhiêu hàng? |
| ORM object count | 100 entities loaded, 20 collections initialized | Hibernate materialize/quản lý bao nhiêu đối tượng? |
| Result size | 4 MB dữ liệu JDBC, 120 KB JSON response | Bao nhiêu dữ liệu được truyền hoặc giữ lại? |
| Latency | p50 40 ms, p95 300 ms | Người dùng phải chờ bao lâu? |
| Resource cost | CPU, heap, GC, connection wait | Query gây tải gì cho ứng dụng và database? |

Không phải mọi công cụ đều cung cấp tất cả các số liệu. Hibernate Statistics có thể giúp đếm entity/collection và statement preparation, nhưng không phải công cụ đo byte trên wire. SQL execution plan có thể cho biết rows scanned/returned theo DBMS, nhưng không tự cho biết JSON cuối cùng nặng bao nhiêu.

### 2.1. Phân biệt query logic và SQL statement

Một lần gọi repository hoặc JPQL query không nhất thiết tương ứng một SQL statement:

- Một HQL query có thể phát một câu SELECT chính và thêm nhiều SELECT cho EAGER association.
- Lazy loading có thể phát SQL sau khi repository method đã trả về.
- Flush có thể phát INSERT/UPDATE/DELETE trước một query.
- Một thao tác persist dùng generator IDENTITY có thể phát INSERT sớm.
- Native SQL và stored procedure có thể thực hiện nhiều thao tác bên trong database.
- Một query execution có thể được gọi nhiều lần trong vòng lặp.

Do đó, nên ghi riêng **số lần query ở tầng ORM** và **số statement JDBC thực thi**.

### 2.2. Phân biệt rows returned và rows scanned

Một câu:

```sql
SELECT id, full_name
FROM customer
WHERE id = 42;
```

có thể trả một hàng và chỉ đọc rất ít dữ liệu nhờ index.

Một câu aggregate:

```sql
SELECT COUNT(*)
FROM purchase_order
WHERE customer_id = 42;
```

cũng trả một hàng, nhưng database có thể phải đọc nhiều index entry hoặc row để tính count.

Vì vậy, “một hàng kết quả” không có nghĩa database chỉ xử lý một hàng. Hãy tách:

- **Rows returned**: số hàng trong result set.
- **Rows scanned/visited**: số hàng hoặc index entry database đọc trong quá trình thực thi.
- **Rows affected**: số hàng bị INSERT/UPDATE/DELETE hoặc bị ảnh hưởng bởi DML.
- **Entities loaded**: số entity instance Hibernate nạp vào persistence context.

Đây là các đại lượng khác nhau.

### 2.3. Kích thước kết quả cũng có nhiều lớp

Một query có thể trả 10.000 hàng, mỗi hàng 20 cột. Kích thước dữ liệu JDBC không giống:

- Dung lượng heap của các Java object sau khi materialize.
- Dung lượng collection và persistence context.
- Dung lượng DTO sau mapping.
- Dung lượng JSON nén hoặc chưa nén trả cho client.
- Dung lượng packet thực sự truyền qua mạng.

Không nên lấy số ký tự JSON để khẳng định JDBC result cũng có cùng kích thước. Các lớp có thể dùng kiểu dữ liệu, encoding và overhead khác nhau.

## 3. Ví dụ: một query nhưng hàng kết quả bị nhân lên

Giả sử một customer có:

- 10 order.
- 5 địa chỉ giao hàng.

Nếu query fetch join đồng thời hai collection:

```java
Customer customer = entityManager.createQuery(
    "select distinct c from Customer c " +
    "left join fetch c.orders " +
    "left join fetch c.addresses " +
    "where c.id = :id",
    Customer.class
)
.setParameter("id", 42L)
.getSingleResult();
```

SQL join có thể tạo:

```text
1 Customer × 10 Orders × 5 Addresses
= 50 rows trong result set
```

Hibernate có thể hợp nhất những hàng lặp thành một root entity và các collection tương ứng. Nhưng database và JDBC vẫn phải xử lý/di chuyển các hàng join đó.

Nếu số lượng tăng thành 500 order và 20 address:

```text
1 × 500 × 20 = 10.000 rows
```

Một statement duy nhất vẫn có thể rất đắt. Đó là lý do **đếm statement mà không đo rows và result size có thể dẫn đến tối ưu sai**.

### 3.1. Join multiplication khác với N+1

| Tình huống | Số statement | Rows/result |
|---|---:|---:|
| N+1 | Thường nhiều | Mỗi query có thể nhỏ, tổng rows tùy dữ liệu |
| Join nhiều collection | Có thể chỉ 1 | Có thể nhân lên rất lớn |
| Batch fetching | Ít hơn N+1 | Vẫn có thể tải toàn bộ child của nhiều owner |
| DTO aggregate | Thường ít | Có thể trả ít giá trị, dù DB vẫn xử lý nhiều rows |
| Pagination child | Nhiều trang nếu cần | Giới hạn rows mỗi lần tải |

N+1 là vấn đề số lượt truy vấn; join multiplication là vấn đề số hàng và dữ liệu lặp. Một ứng dụng có thể gặp cả hai ở các endpoint khác nhau.

## 4. Hibernate Statistics: điểm bắt đầu để quan sát ORM

Hibernate cung cấp API Statistics để quan sát hoạt động của `SessionFactory`. Có thể bật qua property:

```properties
hibernate.generate_statistics=true
```

Trong Spring Boot, có thể cấu hình:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Lấy statistics:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
```

Trước một kịch bản kiểm thử, có thể reset counters:

```java
statistics.clear();

// Chạy đúng một use case cần đo.

long preparedStatements =
    statistics.getPrepareStatementCount();

long queryExecutions =
    statistics.getQueryExecutionCount();

long entityLoads =
    statistics.getEntityLoadCount();

long entityFetches =
    statistics.getEntityFetchCount();

long collectionLoads =
    statistics.getCollectionLoadCount();

long collectionFetches =
    statistics.getCollectionFetchCount();

System.out.println("Prepared statements: " + preparedStatements);
System.out.println("Query executions: " + queryExecutions);
System.out.println("Entity loads: " + entityLoads);
System.out.println("Entity fetches: " + entityFetches);
System.out.println("Collection loads: " + collectionLoads);
System.out.println("Collection fetches: " + collectionFetches);
```

Tên metric/API có thể thay đổi theo Hibernate major version; hãy đối chiếu dependency của dự án.

### 4.1. Ý nghĩa một số counter quan trọng

| Statistics API | Ý nghĩa thực hành | Không nên diễn giải thành |
|---|---|---|
| `getPrepareStatementCount()` | Số prepared statement Hibernate đã chuẩn bị theo thống kê | Số rows hoặc bytes trả về |
| `getQueryExecutionCount()` | Số lần thực thi query được Hibernate theo dõi | Tổng số SQL statement trong mọi trường hợp |
| `getEntityLoadCount()` | Số entity được load từ datasource theo thống kê Hibernate | Số root trong response |
| `getEntityFetchCount()` | Số entity được fetch qua association theo thống kê | Tổng số entity đang nằm trong context |
| `getCollectionLoadCount()` | Số collection được load | Tổng số phần tử collection |
| `getCollectionFetchCount()` | Số collection được fetch theo cơ chế fetch association | Số rows trong collection |
| `getSecondLevelCacheHitCount()` | Số lần đọc cache cấp hai thành công | Database không có tải nào khác |
| `getSecondLevelCacheMissCount()` | Số lần lookup cache không có entry phù hợp | Chắc chắn có đúng một SQL tiếp theo |

Statistics hữu ích để phát hiện một endpoint bỗng tải nhiều entity hoặc collection, nhưng **không trực tiếp báo chính xác số hàng result set hoặc dung lượng bytes**.

### 4.2. Prepared statement count không đồng nghĩa query execution count

Một prepared statement có thể được chuẩn bị và thực thi theo cách phụ thuộc driver, pooling và Hibernate. Một query logic có thể tạo nhiều statement SQL phụ; một số statement có thể được tái sử dụng hoặc chuẩn bị lại.

Nếu cần số lần JDBC execute chính xác theo request, dùng công cụ quan sát ở tầng DataSource/JDBC. Hãy xem Hibernate Statistics là tín hiệu ORM tổng quan, không phải packet-level trace.

### 4.3. Statistics là cấp SessionFactory, không mặc nhiên theo request

`SessionFactory` thường được chia sẻ cho nhiều request. Nếu một request gọi `statistics.clear()` trong khi request khác đang chạy, counters có thể bị reset giữa chừng và làm sai kết quả của cả hai.

Không dùng reset global trong production để đo riêng từng request có traffic đồng thời. Các lựa chọn phù hợp hơn:

- Chạy integration test cô lập.
- Đo trên một instance/test profile không có request khác.
- Dùng JDBC/DataSource instrumentation có correlation ID hoặc thread/request context.
- Dùng tracing/APM gắn span SQL với HTTP request.
- Thu thập counter theo khoảng thời gian và phân tích theo workload thay vì reset mỗi request.

### 4.4. Bật Statistics có chi phí

Statistics có overhead nhất định và có thể thay đổi kết quả benchmark. Dùng chúng để quan sát trong môi trường phù hợp; nếu cần đo latency production, kết hợp APM/metrics với sampling và cấu hình logging có kiểm soát.

## 5. Đếm SQL statement ở tầng JDBC/DataSource

Để biết chính xác endpoint đã gửi bao nhiêu statement JDBC, hãy quan sát nơi Hibernate gọi JDBC. Các công cụ phổ biến gồm:

- DataSource proxy hoặc JDBC instrumentation.
- P6Spy.
- datasource-proxy.
- APM agent có theo dõi JDBC.
- Instrumentation tự viết qua wrapper của DataSource/Connection/PreparedStatement.

Công cụ ở tầng này có thể ghi nhận:

- SQL text sau khi Hibernate sinh.
- Loại thao tác SELECT/INSERT/UPDATE/DELETE.
- Số lần execute.
- Thời gian thực thi.
- Batch size và số lần executeBatch.
- Parameters nếu được cấu hình.
- Kết quả update count.
- ResultSet được mở/đọc/đóng nếu công cụ hỗ trợ.

Không phải công cụ nào cũng đo được rows hoặc bytes; cần kiểm tra khả năng cụ thể.

### 5.1. Ví dụ log một endpoint

Một log minh họa có thể như sau:

```text
requestId=abc-123
endpoint=GET /customers
jdbc.statements=4
  1. SELECT customer ...                 1.8 ms
  2. SELECT purchase_order WHERE ...     2.1 ms
  3. SELECT purchase_order WHERE ...     1.4 ms
  4. SELECT purchase_order WHERE ...     1.6 ms
response.rows=20
response.bytes=8450
```

Chỉ từ log này đã có thể đặt câu hỏi:

- Vì sao có ba query lấy order riêng?
- Đây có phải N+1 hay các query có mục đích khác nhau?
- Tổng số rows được trả từ database là bao nhiêu?
- Response 8.450 bytes có nhỏ nhưng JDBC result có thể lớn hơn không?
- Có thể dùng batch hoặc projection không?

### 5.2. Cẩn thận với log parameter

Parameter có thể chứa email, token, thông tin cá nhân hoặc dữ liệu nhạy cảm. Trên production, tránh ghi toàn bộ bind values nếu không có chính sách bảo vệ, masking, retention và quyền truy cập phù hợp.

SQL text và số lượng statement thường đã đủ để tìm nhiều lỗi N+1. Chỉ bật bind logging khi cần và trong môi trường được kiểm soát.

## 6. Đếm số hàng ResultSet: cần đo đúng lớp

Số rows trả về từ database không phải lúc nào cũng có sẵn trong một counter Hibernate đơn giản.

Một cách đo ở JDBC là instrument thao tác `ResultSet.next()` và đếm mỗi lần trả về `true`. Khi cursor được đọc hết, số lần thành công là số hàng đã tiêu thụ.

Tuy nhiên cần phân biệt:

- **Rows returned/available**: database tạo ra cho result set.
- **Rows consumed**: ứng dụng/ORM thực sự đọc qua cursor.
- **Rows materialized**: số object/tuple được tạo.
- **Rows affected**: số hàng DML cập nhật/xóa.

Nếu ứng dụng dùng streaming và dừng sớm, số rows consumed thấp hơn tổng số hàng query có thể trả. Một proxy chỉ đếm `ResultSet.next()` sẽ đo số hàng đã đọc qua cursor, không nhất thiết biết tổng số kết quả còn lại.

### 6.1. Không dựa vào `ResultSet.getRow()` cho mọi driver

`ResultSet.getRow()` không phải cách portable để đếm toàn bộ hàng của mọi result set, đặc biệt với cursor forward-only. Nó trả vị trí hàng hiện tại trong những trường hợp driver hỗ trợ, không phải tổng số hàng của query.

Muốn đếm rows consumed, instrument `next()`. Muốn biết rows thực tế database xử lý hoặc trả về, dùng execution plan/DBMS telemetry hoặc công cụ tracing phù hợp.

### 6.2. Hibernate Statistics entity count không phải JDBC row count

Một join query có thể trả 100 hàng SQL nhưng Hibernate chỉ tạo một root entity và một số child entity duy nhất. Ngược lại, một projection trả 100 tuple không làm 100 entity được load.

Do đó:

```text
JDBC rows != Hibernate entity loads != collection elements != API response rows
```

Khi phân tích join multiplication, phải kết hợp SQL/resultset observation với ORM entity/collection counters.

## 7. Đo số hàng database phải quét bằng execution plan

Để hiểu database phải làm bao nhiêu việc, xem execution plan của SQL.

Ví dụ:

```sql
SELECT id, order_code, status
FROM purchase_order
WHERE customer_id = 42
ORDER BY id DESC;
```

Execution plan có thể cho thấy:

- Table scan hay index scan.
- Index nào được dùng.
- Estimated rows và actual rows.
- Số loop ở nested loop join.
- Filter loại bỏ bao nhiêu hàng.
- Sort hoặc hash aggregate có tốn bộ nhớ không.
- Có spill ra disk hay không.

Các lệnh cụ thể phụ thuộc DBMS:

| DBMS | Công cụ thường dùng |
|---|---|
| PostgreSQL | `EXPLAIN`, `EXPLAIN (ANALYZE, BUFFERS)` |
| MySQL | `EXPLAIN`, `EXPLAIN ANALYZE` tùy phiên bản |
| SQL Server | Actual Execution Plan, Query Store, logical reads |
| Oracle | Explain Plan, SQL Monitor, execution statistics |

`EXPLAIN ANALYZE` trên một số DBMS **thực thi câu query thật**. Với SELECT thường ít rủi ro dữ liệu hơn DML, nhưng vẫn tiêu tốn tài nguyên và có thể giữ lock/tạo tải. Với UPDATE/DELETE, cần hiểu rõ semantics và dùng môi trường an toàn hoặc transaction rollback theo khả năng DBMS.

### 7.1. Estimated rows và actual rows

Optimizer dự đoán số hàng để chọn plan. Nếu estimate khác xa actual rows, có thể có vấn đề thống kê, skew dữ liệu hoặc predicate khó ước lượng.

Ví dụ:

```text
Plan estimate: 10 rows
Actual rows:   50,000 rows
```

Query có thể rất chậm vì optimizer chọn join order hoặc access path dựa trên estimate sai. Tăng fetch batch size ở Hibernate không giải quyết được lỗi cardinality estimate của database.

### 7.2. Rows scanned không nhất thiết bằng rows returned

Một index scan có thể đọc nhiều index entry rồi filter còn vài hàng. Một aggregate có thể quét hàng triệu bản ghi nhưng trả một hàng count. Đo rows returned giúp hiểu kích thước result set; execution plan giúp hiểu chi phí xử lý ở DBMS.

## 8. Đo kích thước kết quả thay vì chỉ đếm hàng

Hai result set cùng 1.000 hàng có thể có kích thước rất khác:

| Result | Hàng | Cột | Ví dụ nội dung |
|---|---:|---:|---|
| A | 1.000 | 3 | ID, status, timestamp |
| B | 1.000 | 25 | nhiều text, JSON, metadata |
| C | 1.000 | 5 | có cột LOB lớn |
| D | 1.000 | 4 | chuỗi Unicode dài |

Chỉ đếm rows không phản ánh đầy đủ network, heap hoặc serialization cost.

### 8.1. Kích thước ở tầng JDBC

JDBC API chuẩn không cung cấp một hàm portable trả về tổng số bytes đã truyền cho ResultSet. Các lựa chọn:

- Driver/database metrics về network bytes nếu DBMS hỗ trợ.
- APM hoặc network instrumentation ở tầng connection.
- Ước lượng dựa trên kiểu cột, độ dài dữ liệu và số hàng.
- Đo thời gian fetch và số hàng consumed để so sánh tương đối.
- Tránh SELECT các cột lớn không cần thiết.

Nếu dùng LOB streaming, không nên materialize toàn bộ nội dung chỉ để đo. Có thể đo số bytes đọc từ stream tại điểm ứng dụng tiêu thụ, nhưng đây là bytes mà ứng dụng đã đọc, không nhất thiết toàn bộ bytes database đã gửi.

### 8.2. Kích thước object trong heap

Một entity Java có overhead object header, field references, collection wrapper, snapshot và các object liên quan. Vì vậy, 1 MB dữ liệu SQL có thể trở thành nhiều MB heap sau materialization.

Để quan sát:

- Heap profiling và allocation profiling.
- Java Flight Recorder (JFR).
- GC logs và heap usage.
- APM runtime metrics.
- Kích thước collection/object graph trong một test được cô lập.

Không nhân số cột với độ dài trung bình rồi coi đó là heap size chính xác. Object layout và JVM phụ thuộc phiên bản, compressed references, alignment và kiểu dữ liệu.

### 8.3. Kích thước HTTP response là một chỉ số khác

Nếu endpoint trả DTO/JSON, đo payload tại ranh giới HTTP:

- Bytes trước compression.
- Bytes sau compression nếu muốn đo network payload.
- Số phần tử trong response.
- Số field trên mỗi phần tử.
- Latency và throughput.

Một endpoint có JDBC result lớn nhưng DTO lọc còn nhỏ vẫn có thể tạo response nhỏ; tuy nhiên nó đã trả chi phí truy vấn/materialization trước khi lọc. Hãy đo cả tầng DB/JDBC và tầng HTTP.

## 9. Ví dụ so sánh ba cách lấy danh sách customer

Giả sử có 50 customer, mỗi người trung bình 10 order. Endpoint chỉ hiển thị tên customer và mã các order.

### Cách A — Lazy collection trong vòng lặp

```java
List<Customer> customers = entityManager.createQuery(
    "select c from Customer c order by c.id",
    Customer.class
)
.setMaxResults(50)
.getResultList();

for (Customer customer : customers) {
    for (PurchaseOrder order : customer.getOrders()) {
        render(customer.getFullName(), order.getOrderCode());
    }
}
```

Nếu không có batch/cache, kết quả có thể:

- 1 SELECT lấy customer.
- 50 SELECT lấy orders.
- Tổng 51 statement.
- Khoảng 500 order rows được tải.

### Cách B — Join fetch collection

```java
List<Customer> customers = entityManager.createQuery(
    "select distinct c from Customer c " +
    "left join fetch c.orders " +
    "order by c.id",
    Customer.class
)
.setMaxResults(50)
.getResultList();
```

Trong trường hợp đơn giản không pagination và một collection:

- Có thể chỉ 1 statement.
- Khoảng 500 hàng join.
- Cột customer được lặp lại trên các hàng order.
- Hibernate hợp nhất entity/collection theo identity.
- Nếu có pagination collection fetch, cần xem lại tính đúng đắn và cách Hibernate xử lý.

### Cách C — DTO projection

```java
public record CustomerOrderRow(
    Long customerId,
    String customerName,
    Long orderId,
    String orderCode
) {}
```

JPQL:

```java
List<CustomerOrderRow> rows = entityManager.createQuery(
    "select new com.example.CustomerOrderRow(" +
    " c.id, c.fullName, o.id, o.orderCode) " +
    "from Customer c " +
    "left join c.orders o " +
    "order by c.id, o.id",
    CustomerOrderRow.class
)
.setMaxResults(500)
.getResultList();
```

Cách này có thể chạy một SQL và chỉ chọn các cột cần hiển thị. Nó không materialize entity graph đầy đủ. Tuy nhiên, kết quả vẫn có một hàng cho mỗi customer/order pair và cần thiết kế pagination cẩn thận để không cắt giữa nhóm nếu UI yêu cầu trang theo customer.

### 9.1. So sánh không thể chỉ dựa vào số statement

| Chỉ số | A: Lazy N+1 | B: Join fetch | C: DTO projection |
|---|---|---|---|
| Statement | Có thể 51 | Có thể 1 | Có thể 1 |
| SQL rows | Root + child queries | Join rows | Root-child rows |
| Cột lặp | Ít hơn trên mỗi query | Root columns lặp | Chỉ cột được chọn nhưng root values lặp theo child |
| Entity materialization | Customer + Order | Customer + Order | DTO rows |
| Collection initialized | Có | Có | Không cần persistent collection |
| Dữ liệu trả về | Entity graph | Entity graph | Projection |
| Rủi ro | Round-trip N+1 | Join multiplication/pagination | DTO mapping và pagination theo đúng đơn vị |

Trong nhiều endpoint danh sách, DTO projection có thể là lựa chọn hợp lý vì chỉ lấy dữ liệu cần thiết. Nhưng không có cách nào luôn thắng: đo với dữ liệu và yêu cầu thật.

## 10. Một query nhanh không có nghĩa endpoint nhanh

Endpoint còn có chi phí ngoài SQL:

- Thời gian chờ connection pool.
- Transaction begin/commit và flush.
- Hydration entity và dirty-check snapshot.
- Lazy loading trong mapper/serializer.
- Business logic xử lý collection.
- JSON serialization.
- GC do object graph lớn.
- Network trả response.
- Lock wait và contention.

Ví dụ SQL chạy 5 ms nhưng tải 20.000 entity, mapping DTO mất 80 ms và serialize mất 100 ms. Chỉ xem query latency sẽ bỏ lỡ phần lớn chi phí.

Ngược lại, SQL chạy 50 ms nhưng trả một DTO aggregate nhỏ có thể rẻ hơn việc chạy 100 query 2 ms rồi materialize hàng nghìn object.

Hãy đo latency theo request và chia span:

```text
HTTP request
  ├── connection acquisition
  ├── transaction / service
  │    ├── SQL statement 1
  │    ├── SQL statement 2
  │    └── entity hydration / mapping
  ├── DTO transformation
  └── JSON serialization / response
```

## 11. Phân biệt thời gian SQL với thời gian fetch ResultSet

Một JDBC statement có thể có hai khoảng thời gian đáng quan sát:

1. Thời gian gọi execute và database bắt đầu trả kết quả.
2. Thời gian ứng dụng tiếp tục đọc ResultSet và chuyển dữ liệu.

Driver có thể fetch dữ liệu theo batch/cursor. Một query trả hàng lớn có thể execute nhanh nhưng đọc hết kết quả chậm.

Nếu instrumentation chỉ đo thời gian từ `executeQuery()` đến lúc method trả ResultSet, nó có thể bỏ sót thời gian ứng dụng tiêu thụ toàn bộ cursor. Cần xem công cụ có đo ResultSet iteration/fetch hay không.

Với Hibernate stream/scroll, nhớ đóng stream và resource đúng cách:

```java
try (var stream = entityManager.createQuery(
        "select o from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    ).getResultStream()) {

    stream.forEach(order -> process(order));
}
```

Tên API và behavior streaming phụ thuộc provider/version; streaming không tự đảm bảo cursor server-side hoặc giới hạn heap nếu driver/provider materialize theo cách khác.

## 12. Pagination là cách kiểm soát rows và result size

Nếu UI chỉ hiển thị 25 order mỗi trang, hãy để database giới hạn rows thay vì tải tất cả rồi cắt trong Java.

```java
List<PurchaseOrder> page = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status " +
    "order by o.createdAt desc, o.id desc",
    PurchaseOrder.class
)
.setParameter("status", "PAID")
.setFirstResult(0)
.setMaxResults(25)
.getResultList();
```

Điều này giới hạn số root result cho query đơn giản. Nếu query fetch collection to-many, pagination có thể không áp dụng trực tiếp lên root như mong đợi; Hibernate có thể phải phân trang trong memory hoặc cảnh báo/lỗi tùy cấu hình.

### 12.1. Đo cả rows của từng trang và tổng số trang

Một page query có thể trả 25 rows, nhưng nếu UI cần tổng số bản ghi, framework có thể chạy thêm count query. Vì vậy một request phân trang thường có:

- Query lấy page.
- Query count tổng số kết quả.
- Các query phụ do fetch association nếu mapping/query gây ra.

Count query có thể tốn kém dù chỉ trả một row. Đo execution plan của count riêng; không đánh giá nó bằng result row count.

### 12.2. Keyset pagination cho dữ liệu lớn

Offset lớn có thể khiến DBMS phải bỏ qua nhiều hàng trước khi trả trang. Keyset pagination dựa trên cursor:

```java
List<PurchaseOrder> nextPage = entityManager.createQuery(
    "select o from PurchaseOrder o " +
    "where o.status = :status " +
    "and (o.createdAt < :lastTime " +
    "  or (o.createdAt = :lastTime and o.id < :lastId)) " +
    "order by o.createdAt desc, o.id desc",
    PurchaseOrder.class
)
.setParameter("status", "PAID")
.setParameter("lastTime", lastCreatedAt)
.setParameter("lastId", lastId)
.setMaxResults(25)
.getResultList();
```

Keyset pagination giúp truy vấn tiếp từ vị trí cuối, thường phù hợp feed hoặc bảng lớn có thứ tự ổn định. Nó vẫn cần index phù hợp và chính sách cho hàng mới/xóa giữa các lần lấy trang.

## 13. Batch fetching: đo số statement và tổng rows cùng lúc

Hibernate có thể batch các lazy association:

```java
import org.hibernate.annotations.BatchSize;

@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
@BatchSize(size = 16)
private List<PurchaseOrder> orders = new ArrayList<>();
```

Hoặc:

```properties
hibernate.default_batch_fetch_size=16
```

Khi một collection được truy cập, Hibernate có thể tải collection cho một nhóm customer ID bằng SQL `IN`. Điều này giảm số statement so với N+1.

Nhưng batch size 16 không có nghĩa chỉ tải 16 order. Nếu 16 customer có tổng 5.000 order, query vẫn có thể trả 5.000 hàng. Hãy ghi cả:

- Số statement trước/sau.
- Số rows returned.
- Số collection initialized.
- Tổng entity load count.
- Thời gian và heap.

Một tối ưu giảm statement nhưng tăng rows quá mạnh có thể không cải thiện endpoint.

## 14. EntityGraph và fetch join cần được đo ở query thực tế

`@EntityGraph` mô tả association cần fetch:

```java
@EntityGraph(attributePaths = {"customer"})
Optional<PurchaseOrder> findWithCustomerById(Long id);
```

`JOIN FETCH` diễn đạt rõ trong JPQL:

```java
select o
from PurchaseOrder o
join fetch o.customer
where o.id = :id
```

Cả hai có thể làm query count giảm hoặc entity fetch thay đổi, nhưng không đảm bảo SQL giống nhau. Provider có thể dùng join, select hoặc chiến lược khác.

Khi thử fetch plan mới, so sánh:

- Statement count.
- ResultSet rows.
- Số entity/collection load.
- Dung lượng cột được chọn.
- Query latency và fetch time.
- Heap và response size.
- Tính đúng của pagination và thứ tự kết quả.

Không đánh giá một EntityGraph chỉ bằng việc code có ít annotation hơn hay query log có một dòng SQL.

## 15. SQL logging: hữu ích nhưng không thay thế metrics

Hibernate có thể hiển thị SQL:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
```

Trong ứng dụng Spring Boot, thường dùng logging category của Hibernate thay vì chỉ dựa vào stdout. Cấu hình chi tiết phụ thuộc Hibernate major version và logging framework.

SQL log giúp nhận diện:

- Query lặp theo từng ID.
- Join thừa.
- Cột không cần thiết.
- Query count phụ.
- Flush DML phát sinh trước SELECT.
- Batch `IN` hoặc truy vấn phụ.

Nhưng log text không tự cho biết:

- Số hàng ResultSet đã đọc.
- Số bytes truyền qua mạng.
- Số rows database quét.
- Thời gian fetch đầy đủ.
- Số entity đã materialize chính xác.

Kết hợp log với JDBC instrumentation, Hibernate Statistics và execution plan.

### 15.1. `StatementInspector` quan sát SQL trước khi thực thi

Hibernate có interface:

```java
import org.hibernate.resource.jdbc.spi.StatementInspector;

public class SqlInspector implements StatementInspector {

    @Override
    public String inspect(String sql) {
        // Ghi nhận hoặc phân loại SQL.
        // Trả lại SQL nguyên trạng nếu không cần sửa.
        return sql;
    }
}
```

Có thể cấu hình inspector qua Hibernate properties hoặc bootstrap. `StatementInspector` nhìn thấy câu SQL trước khi thực thi; nó không nhận ResultSet và không tự đếm rows/bytes.

Nếu cần gắn SQL với request, cần correlation context phù hợp. Inspector thường được cấu hình dùng chung; tránh dùng một mutable field toàn cục để lưu “request hiện tại” vì nhiều request có thể chạy đồng thời.

### 15.2. P6Spy và datasource-proxy

Các thư viện JDBC proxy có thể log statement, execution time và đôi khi hỗ trợ listener cho ResultSet. Chúng tiện khi cần quan sát ở tầng JDBC mà không sửa từng repository.

Trước khi chọn, xác định rõ công cụ có hỗ trợ phiên bản driver/JDK/framework không, cách masking parameters, overhead và cách xuất metrics. Không coi mọi thư viện có chức năng “query logging” đều đếm được rows hoặc bytes.

## 16. Đo query theo request thay vì toàn ứng dụng

Một counter global hữu ích cho xu hướng nhưng không trả lời endpoint cụ thể nào gây N+1.

Một mô hình quan sát tốt:

```text
requestId=R-2026
route=GET /customers?page=0
duration_ms=148
jdbc_statement_count=3
jdbc_select_count=3
jdbc_write_count=0
resultset_rows_consumed=75
hibernate_entity_loads=50
hibernate_collection_fetches=0
response_items=25
response_bytes=6200
```

Các field ở trên là ví dụ schema metric, không phải tên metric tiêu chuẩn Hibernate. Có thể gắn chúng vào tracing span hoặc log event.

### 16.1. Correlation ID

Mỗi request có một correlation ID. SQL span được gắn vào request trace để xem:

- Query nào chạy trong request.
- Query nào chiếm nhiều thời gian.
- Có nhiều query cùng SQL pattern nhưng bind ID khác nhau không.
- SQL xảy ra trong repository, service hay serializer.
- Có lazy query sau khi service method đã hoàn tất không.

Nếu dùng async processing, thread context không tự truyền qua mọi executor; cần instrumentation context propagation của framework.

### 16.2. Đừng dùng query text đầy đủ làm metric label

SQL chứa literal hoặc parameter khác nhau có thể tạo cardinality rất cao trong metrics system. Nên chuẩn hóa query fingerprint/statement shape và dùng trace/log có sampling để lưu chi tiết. Metrics label chỉ nên có số chiều được kiểm soát.

## 17. Thiết kế benchmark có thể lặp lại

Một benchmark hữu ích cần kiểm soát dữ liệu và trạng thái runtime. Quy trình gợi ý:

### Bước 1 — Chọn use case cụ thể

Ví dụ endpoint danh sách customer, chi tiết order hoặc báo cáo tổng hợp. Định nghĩa rõ response phải có trường nào và giới hạn bao nhiêu phần tử.

### Bước 2 — Tạo dữ liệu đại diện

Không chỉ tạo 10 hàng nhỏ. Dữ liệu cần phản ánh phân bố thực tế:

- Customer có số order trung bình và trường hợp lớn nhất.
- Order có số line khác nhau.
- Một số customer không có association.
- Dữ liệu text/LOB có độ dài thực tế.
- Skew dữ liệu, ví dụ một tenant lớn hơn nhiều tenant khác.

### Bước 3 — Cố định môi trường đo

Ghi lại:

- Hibernate/JPA version.
- DBMS/version/dialect.
- JDBC driver.
- Isolation level.
- Connection pool.
- Cache settings.
- Batch sizes.
- Heap/JVM options.
- Số thread và concurrency.
- Dataset size.

### Bước 4 — Đo cold và warm separately

Cold run và warm run có thể khác do:

- First-level cache vừa được tạo hay đã có entity.
- Second-level cache hit/miss.
- Query cache.
- OS/database buffer cache.
- JVM JIT warm-up.
- Connection pool và prepared statement cache.

Không gộp hai trạng thái thành một con số mà không ghi chú.

### Bước 5 — Lặp nhiều lần và xem phân vị

Đo nhiều lượt, loại bỏ warm-up phù hợp, báo cáo p50/p95/p99 thay vì chỉ một lần trung bình. Giữ cùng workload và concurrency khi so sánh.

### Bước 6 — Ghi cả số liệu DB, ORM và response

Một bảng benchmark tối thiểu:

| Kịch bản | Statements | Rows consumed | Entity loads | Result/response size | p95 |
|---|---:|---:|---:|---:|---:|
| Lazy N+1 | 51 | 550 | 550 | 180 KB | 420 ms |
| Batch fetch | 5 | 550 | 550 | 180 KB | 170 ms |
| DTO projection | 1 | 500 | 0 entity graph | 70 KB | 95 ms |

Các con số chỉ minh họa cách trình bày. Không dùng chúng làm kỳ vọng hiệu năng chung; kết quả thật phụ thuộc DBMS, dữ liệu, index, driver và code.

## 18. Kiểm tra dữ liệu nhỏ và dữ liệu lớn

Một fetch plan có thể chạy tốt trên fixture 5 customer nhưng thất bại khi có 50.000 customer. Vì thế benchmark nên có ít nhất ba quy mô:

- **Small**: nhanh để chạy test chức năng và xem SQL shape.
- **Typical**: gần phân bố production.
- **Worst-case**: root/collection lớn nhất hợp lệ, để phát hiện graph bùng nổ.

Đặc biệt kiểm tra các outlier. Một customer có 200.000 order có thể làm endpoint chậm dù 99% customer chỉ có 2 order.

Không chỉ dùng cardinality trung bình; cần percentile hoặc maximum theo nghiệp vụ.

## 19. Index và execution plan: query count thấp vẫn có thể chậm

Ví dụ endpoint lọc order theo customer và trạng thái:

```sql
SELECT id, order_code, status, created_at
FROM purchase_order
WHERE customer_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT 25;
```

Nếu không có index phù hợp, database có thể quét rất nhiều hàng rồi sort mới lấy 25. Một câu SQL duy nhất vẫn chậm.

Index ứng viên có thể là:

```sql
CREATE INDEX idx_order_customer_status_created
ON purchase_order(customer_id, status, created_at, id);
```

Thứ tự cột tối ưu phụ thuộc DBMS, predicate, sort direction, selectivity và workload. Hãy xem execution plan và logical reads trước khi quyết định.

Đo thêm:

- Index scan/seek hay table scan.
- Actual rows và loops.
- Buffer/cache reads.
- Sort/hash memory và spill.
- Lock wait.
- Plan changes theo parameter values.

## 20. Những trường hợp số query bị hiểu sai

### 20.1. Một lần repository call nhưng có lazy query sau đó

Repository trả entity. Mapper/serializer gọi getter association và phát SQL sau khi repository method đã kết thúc. Nếu chỉ đếm SQL trong repository span, sẽ bỏ sót query.

Đo toàn bộ request hoặc transaction boundary.

### 20.2. Một lần JPQL query nhưng Hibernate phát SELECT EAGER phụ

Query root không fetch join association EAGER. Hibernate phát thêm select để đáp ứng fetch requirement. Đọc JPQL string không đủ; xem JDBC statement thực tế.

### 20.3. Auto-flush thêm UPDATE trước SELECT

Nếu entity đang dirty và query có thể bị ảnh hưởng, Hibernate có thể auto-flush theo flush mode. Query log có thể có UPDATE trước SELECT dù code repository không gọi save rõ ràng tại dòng đó.

Đừng phân loại mọi statement trước query thành lazy loading.

### 20.4. IDENTITY phát INSERT sớm

Một số generator cần database cấp identifier, nên persist có thể phát SQL trước flush tổng quát. Khi đo query count, phân loại DML và SELECT riêng.

### 20.5. Cache làm SQL count giảm nhưng dữ liệu vẫn được xử lý

Cache hit có thể giảm DB round-trip, nhưng Hibernate vẫn cần materialize hoặc trả object, mapper vẫn cần chạy và response vẫn cần serialize. Đo cả latency/heap, không chỉ SQL.

### 20.6. Batch statement không giống một câu SQL đơn

JDBC batch có thể gửi nhiều lệnh trong một batch execution. Cần phân biệt số lần executeBatch, số statement trong batch và số rows affected. Một metric đếm method call có thể không bằng số lệnh DML logic.

## 21. Chọn chỉ số theo câu hỏi điều tra

| Câu hỏi | Chỉ số/công cụ nên xem |
|---|---|
| Có N+1 không? | JDBC SELECT count, SQL fingerprint lặp, query trace |
| Một join có nhân hàng không? | ResultSet row count, execution plan actual rows, entity load counters |
| Database quét quá nhiều hàng? | EXPLAIN ANALYZE/actual plan, logical reads, buffers |
| Entity graph quá lớn? | Hibernate entity/collection load counters, heap profiling |
| ResultSet nặng? | Rows consumed, cột được chọn, driver/network metrics |
| API response quá lớn? | Response item count và bytes ở HTTP boundary |
| Query nhanh nhưng endpoint chậm? | Distributed trace, mapping/serialization time, GC/heap |
| Query count tăng sau deploy? | Per-request SQL metrics và fingerprint comparison |
| Cache có giúp không? | Cache hit/miss, cold/warm benchmark, DB load |
| Pagination không hiệu quả? | Actual plan, offset cost, rows read vs rows returned |

Không có một dashboard duy nhất trả lời mọi câu hỏi. Chọn đúng công cụ cho lớp đang có vấn đề.

## 22. Ví dụ: điều tra endpoint có N+1

Giả sử log cho thấy:

```text
GET /customers
  SELECT customer ...                  1 time
  SELECT purchase_order ...            30 times
  response items                       30
```

Các bước:

1. Xác nhận 30 query order có cùng SQL shape và khác bind parameter customer ID.
2. Xác nhận collection `orders` được khởi tạo trong mapper/controller.
3. Đo rows mỗi query và tổng rows.
4. Kiểm tra endpoint thật sự cần order detail hay chỉ count.
5. Nếu cần toàn bộ order của trang customer và cardinality vừa phải, cân nhắc batch fetching hoặc fetch theo tập ID.
6. Nếu chỉ cần count, dùng projection/COUNT.
7. Nếu cần một vài order gần nhất, query child có sort và limit.
8. Chạy lại benchmark cold/warm với cùng dataset và so sánh statements, rows, bytes, p95.

Không chỉ đổi `LAZY` thành `EAGER`. Điều đó có thể chuyển N+1 thành select EAGER phụ hoặc join lớn mà không giải quyết đúng nhu cầu dữ liệu.

## 23. Ví dụ: điều tra một câu JOIN rất lớn

Log cho thấy:

```text
GET /customer/42
  SELECT customer
    LEFT JOIN purchase_order
    LEFT JOIN address
    LEFT JOIN customer_tag
  statement count = 1
  result rows = 24,000
  response items = 1 customer
```

Đây không phải endpoint tối ưu chỉ vì statement count bằng 1.

Các bước điều tra:

- Tính cardinality mỗi collection.
- Xác định tích số hàng do join.
- Xem cột nào bị lặp qua mỗi row.
- Kiểm tra Hibernate materialize bao nhiêu entity/collection element.
- Xác định màn hình có thực sự cần mọi collection cùng lúc không.
- Tách query từng nhánh hoặc dùng DTO/projection.
- Phân trang collection lớn riêng.
- So sánh tổng bytes và heap trước/sau.

Một fetch plan có 3 query nhỏ, mỗi query chỉ lấy đúng nhánh cần thiết, có thể nhanh và ổn định hơn một join duy nhất trả 24.000 rows.

## 24. Tránh các phép đo gây nhiễu

Khi đo, đừng để công cụ debug tự thay đổi hành vi đang quan sát:

- `toString()` của entity có thể chạm association lazy.
- IDE debugger có thể đánh giá getter.
- Logging bind parameter có thể tạo overhead và lộ dữ liệu.
- Test chạy song song có thể làm nhiễu Hibernate Statistics global.
- Transaction chưa đóng có thể giữ connection/lock và persistence context.
- Second-level cache warm giữa các lượt có thể làm query count giảm.
- JIT warm-up khiến lượt đầu chậm hơn.
- Dataset quá nhỏ không tạo ra N+1 hoặc join multiplication đáng kể.
- Connection pool có thể che latency mở connection nhưng gây wait khi tải cao.

Định nghĩa trước điều kiện benchmark và ghi lại các cấu hình quan trọng.

## 25. Checklist đo lường cho một thay đổi fetch plan

Với mỗi endpoint cần tối ưu, ghi một baseline trước khi thay đổi:

| Hạng mục | Cần ghi nhận |
|---|---|
| Use case | Route/service và dữ liệu đầu ra cần có |
| Dataset | Số root, cardinality trung bình và outlier của collection |
| Mapping | LAZY/EAGER, association type, batch/entity graph |
| Query plan | JPQL/HQL/native SQL và SQL thực tế |
| Statement count | SELECT, INSERT, UPDATE, DELETE tách riêng |
| Rows | ResultSet rows, rows consumed, rows scanned nếu có |
| ORM loads | Entity load/fetch, collection load/fetch |
| Payload | JDBC/result bytes nếu có, DTO/HTTP response bytes |
| Time | SQL execute/fetch, service, serialization, p50/p95/p99 |
| Runtime | Heap, GC, CPU, connection pool wait |
| Cache | First-level, second-level, query cache; cold/warm |
| Correctness | Pagination, ordering, duplicate roots, transaction semantics |

Sau khi đổi fetch plan, chạy lại cùng kịch bản và so sánh. Một cải thiện tốt nên giảm chi phí mục tiêu mà vẫn giữ đúng dữ liệu, pagination và semantics nghiệp vụ.

## 26. Bài thực hành A — So sánh N+1, batch fetch và projection

Giả sử có 40 customer, mỗi customer có 8 order. Endpoint hiển thị mã khách hàng và số order.

### Cách làm 1

```java
List<Customer> customers = entityManager.createQuery(
    "select c from Customer c order by c.id",
    Customer.class
).getResultList();

for (Customer c : customers) {
    System.out.println(c.getOrders().size());
}
```

Nếu collection lazy được khởi tạo riêng và không có tối ưu, có thể phát 1 query root + 40 query collection. Tổng số order rows được đọc có thể là 320.

### Cách làm 2

Đặt batch fetch size phù hợp cho `orders`. Số statement collection có thể giảm thành vài batch, nhưng tổng order rows vẫn có thể là 320 nếu mọi collection được tải.

### Cách làm 3

```java
public record CustomerOrderCount(
    Long id,
    String code,
    long orderCount
) {}
```

Query:

```java
List<CustomerOrderCount> rows = entityManager.createQuery(
    "select new com.example.CustomerOrderCount(" +
    " c.id, c.customerCode, count(o.id)) " +
    "from Customer c left join c.orders o " +
    "group by c.id, c.customerCode",
    CustomerOrderCount.class
).getResultList();
```

Query aggregate có thể trả 40 DTO rows và không khởi tạo collection entity. Database vẫn phải tính aggregate trên các order phù hợp.

### Câu hỏi

1. Vì sao cách 2 giảm statement nhưng không nhất thiết giảm rows?
2. Vì sao cách 3 có thể giảm entity materialization và response size?
3. Nếu chỉ nhìn query count, có thể kết luận cách 3 luôn nhanh hơn không?
4. Cần đo thêm chỉ số nào để hiểu database cost của COUNT/GROUP BY?

**Gợi ý trả lời:** Đo actual rows/plan, index reads, thời gian aggregate, statement count, entity loads, heap và payload. Projection giảm dữ liệu ORM cần materialize nhưng database vẫn phải xử lý dữ liệu nguồn.

## 27. Bài thực hành B — Một statement nhưng result set rất lớn

Một query fetch join:

```java
select distinct c
from Customer c
left join fetch c.orders
left join fetch c.addresses
where c.id = :id
```

Giả sử customer có 120 order và 15 address.

**Câu hỏi:**

1. Ước tính số hàng join có thể xuất hiện.
2. Hibernate có thể trả bao nhiêu root Customer?
3. Vì sao số root entity không phản ánh số rows JDBC?
4. Có thể tách query như thế nào?

**Gợi ý trả lời:** Join có thể tạo đến 1.800 tổ hợp hàng trước khi xét dữ liệu null/đặc thù; Hibernate có thể hợp nhất thành một root Customer. Có thể query customer trước, query orders và addresses riêng hoặc phân trang từng collection theo nhu cầu.

## 28. Bài thực hành C — Đọc execution plan

Query:

```sql
SELECT id, order_code, status
FROM purchase_order
WHERE customer_id = ?
  AND status = ?
ORDER BY id DESC
LIMIT 25;
```

Plan cho thấy estimate 20 rows nhưng actual 80.000 rows được xét trước khi limit.

**Câu hỏi:**

1. Vì sao query chỉ trả 25 rows nhưng vẫn chậm?
2. Cần xem index nào?
3. Hibernate fetch mode có giải quyết sai lệch estimate của optimizer không?
4. Sau khi thêm index, cần benchmark những gì?

**Gợi ý trả lời:** Database có thể scan/filter/sort nhiều rows trước limit. Xem index theo predicate và ordering, statistics, actual plan. Fetch annotation không sửa optimizer estimate. Đo logical reads, actual rows, latency, statement count, result bytes và p95.

## 29. Nguyên tắc áp dụng vào dự án

- **Đừng kết luận hiệu năng từ annotation.** Xem SQL thực thi trong đúng use case.
- **Đếm riêng query logic và JDBC statement.** Một JPQL query có thể kéo theo nhiều SQL phụ.
- **Đo rows returned, rows scanned và rows consumed riêng biệt.** Chúng không đồng nghĩa.
- **Đếm entity/collection được materialize.** Một join có thể trả nhiều hàng nhưng tạo ít root entity.
- **Đo kích thước dữ liệu ở đúng lớp.** JDBC bytes, heap size và HTTP payload là các số liệu khác nhau.
- **Dùng Hibernate Statistics để quan sát ORM**, JDBC/DataSource instrumentation để đếm statement, execution plan để hiểu database.
- **Gắn metrics với request/trace**, tránh dùng global reset khi có traffic đồng thời.
- **Cố định dataset, cache, transaction và concurrency khi benchmark.**
- **Kiểm tra cả outlier cardinality**, không chỉ dữ liệu trung bình.
- **So sánh N+1 với join multiplication.** Giảm statement có thể làm rows và bytes tăng.
- **Dùng projection, COUNT, EXISTS và pagination** khi use case không cần toàn bộ entity graph.
- **Xem cả latency, heap, GC và response size**, vì SQL không phải toàn bộ thời gian request.
- **Chạy lại cùng benchmark sau thay đổi**, xác nhận hiệu năng cải thiện mà không phá correctness.

Khi đánh giá một fetch plan, hãy đặt ba câu hỏi trước: **có bao nhiêu statement được gửi, database và JDBC phải xử lý bao nhiêu hàng, và ứng dụng thực sự nhận/giữ bao nhiêu dữ liệu?** Annotation chỉ gợi ý cách Hibernate có thể tải; số đo từ ORM, JDBC và database mới cho thấy chi phí thực tế của use case.
