# Paging query và sort key

Trong Spring Batch, paging query là cách đọc dữ liệu từ database theo từng trang thay vì giữ một result set lớn mở trong suốt quá trình xử lý. `JdbcPagingItemReader` thực hiện việc này bằng cách tạo các câu SQL theo từng page thông qua `PagingQueryProvider`. Một **sort key** xác định thứ tự ổn định của các dòng và giúp reader biết cần tiếp tục từ vị trí nào ở page tiếp theo hoặc khi restart.

Sort key là phần cốt lõi của paging reader. Nếu thứ tự không duy nhất hoặc thay đổi trong lúc Job chạy, một dòng có thể bị đọc trùng hoặc bị bỏ sót giữa hai page. Vì vậy, cần chọn sort key có thứ tự xác định, thường là khóa chính hoặc tổ hợp cột kết thúc bằng một khóa duy nhất, đồng thời tạo index phù hợp để database truy vấn hiệu quả.

## 1. Paging query là gì?

Giả sử bảng `orders` có hàng triệu bản ghi. Một reader đọc toàn bộ dữ liệu trong một lần có thể tạo result set lớn, giữ cursor/connection lâu và gây áp lực bộ nhớ hoặc database. Paging chia truy vấn thành các nhóm nhỏ:

```text
Tập dữ liệu orders
       |
       v
Page 1: rows 1 - 500
       |
       v
Page 2: rows 501 - 1000
       |
       v
Page 3: rows 1001 - 1500
       |
       v
       ...
```

`JdbcPagingItemReader` truy vấn một page, trả từng item cho chunk pipeline, sau đó lấy page tiếp theo khi cần. Reader không cần giữ một JDBC cursor mở cho toàn bộ tập dữ liệu như cách đọc cursor truyền thống.

Paging thường phù hợp khi:

- Nguồn dữ liệu là database JDBC.
- Tập dữ liệu lớn và có thể truy vấn theo thứ tự xác định.
- Muốn giới hạn số dòng được lấy trong mỗi query.
- Cần reader có khả năng lưu checkpoint và restart.
- Database có index phù hợp với điều kiện lọc và sort key.

Paging không tự làm query nhanh nếu database phải scan và sort toàn bộ bảng ở mỗi page. Cấu trúc query, sort key và index quyết định phần lớn hiệu năng.

## 2. JdbcPagingItemReader và PagingQueryProvider

`JdbcPagingItemReader<T>` là reader chuẩn của Spring Batch để đọc dữ liệu JDBC theo page. Nó dùng một `PagingQueryProvider` để tạo câu query phù hợp với cú pháp paging của database.

Các thành phần quan trọng:

- `DataSource`: kết nối database.
- `selectClause`: các cột cần đọc.
- `fromClause`: bảng hoặc biểu thức nguồn.
- `whereClause`: điều kiện lọc dữ liệu.
- `sortKeys`: các cột xác định thứ tự và vị trí tiếp tục.
- `parameterValues`: giá trị bind cho các điều kiện query.
- `pageSize`: số dòng trong một page.
- `rowMapper`: chuyển mỗi dòng `ResultSet` thành object.

Spring Batch có thể tạo `PagingQueryProvider` từ các phần SQL và metadata của `DataSource`, hoặc ứng dụng có thể cung cấp một provider cụ thể nếu cần kiểm soát query theo database.

Database khác nhau có cú pháp paging khác nhau. Một provider có thể dùng `FETCH FIRST`, `LIMIT`, `ROWNUM` hoặc cơ chế riêng. Vì vậy, nên để provider tương ứng tạo query thay vì tự giả định một cú pháp SQL duy nhất chạy trên mọi database.

## 3. Ví dụ cấu hình JdbcPagingItemReader trong Spring Batch 5

Ví dụ đọc đơn hàng theo tenant và trạng thái, sắp xếp theo thời gian tạo rồi đến `order_id`:

```java
@Bean
@StepScope
JdbcPagingItemReader<OrderRecord> orderPagingReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        @Value("#{jobParameters['order.status']}") String status) {

    Map<String, Order> sortKeys = new LinkedHashMap<>();
    sortKeys.put("created_at", Order.ASCENDING);
    sortKeys.put("order_id", Order.ASCENDING);

    return new JdbcPagingItemReaderBuilder<OrderRecord>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .selectClause("select order_id, tenant_id, customer_id, amount, created_at")
            .fromClause("from orders")
            .whereClause("where tenant_id = :tenantId and status = :status")
            .parameterValues(Map.of(
                    "tenantId", tenantId,
                    "status", status))
            .sortKeys(sortKeys)
            .pageSize(500)
            .fetchSize(500)
            .rowMapper((rs, rowNum) -> new OrderRecord(
                    rs.getLong("order_id"),
                    rs.getLong("tenant_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount"),
                    rs.getTimestamp("created_at").toInstant()))
            .saveState(true)
            .build();
}
```

Trong ví dụ, `Order` trong map sort key là enum `org.springframework.batch.item.database.Order`; `OrderRecord` là kiểu domain của ứng dụng. Các key `created_at` và `order_id` xác định thứ tự kết quả. `order_id` đóng vai trò tie-breaker để hai đơn hàng có cùng thời điểm tạo vẫn có thứ tự xác định.

`sortKeys` nên được tạo bằng `LinkedHashMap` để giữ thứ tự các cột trong sort key tổng hợp. Các cột dùng để sắp xếp phải có mặt trong kết quả query theo yêu cầu của provider và phải được tham chiếu nhất quán trong cấu hình.

## 4. Sort key là gì?

Sort key là một hoặc nhiều cột dùng để xác định thứ tự dòng khi reader lấy dữ liệu. Ví dụ:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE status = 'READY'
ORDER BY order_id ASC
```

Ở đây `order_id` là sort key. Reader lấy page đầu tiên theo thứ tự tăng dần, sau đó sử dụng giá trị sort key cuối cùng để xác định phần dữ liệu tiếp theo.

Một sort key tốt nên:

- Có thứ tự so sánh ổn định trong database.
- Không thay đổi trong thời gian Job chạy.
- Phân biệt duy nhất từng dòng kết quả, hoặc kết hợp nhiều cột tạo thành một tuple duy nhất.
- Có index hỗ trợ điều kiện lọc và thứ tự truy vấn.
- Được trả về trong `SELECT` để reader có thể lưu giá trị cuối page.

Nếu sort key không duy nhất, nhiều dòng có thể có cùng giá trị tại ranh giới page. Khi reader tiếp tục bằng điều kiện sau giá trị cuối cùng, các dòng còn lại có cùng key có thể bị bỏ qua.

## 5. Vì sao sort key phải duy nhất?

Giả sử bảng có các dòng:

| order_id | created_at | customer_id |
|---:|---|---|
| 101 | 09:00:00 | C001 |
| 102 | 09:00:00 | C002 |
| 103 | 09:00:00 | C003 |
| 104 | 09:01:00 | C004 |

Nếu chỉ dùng `created_at` làm sort key và page kết thúc ở một dòng có `created_at = 09:00:00`, page tiếp theo có thể tìm các dòng có thời gian lớn hơn `09:00:00`. Những dòng khác có cùng thời gian nhưng chưa được đọc sẽ không được chọn.

Để tránh vấn đề này, thêm một khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at ASC, order_id ASC
```

Tuple `(created_at, order_id)` tạo thứ tự tổng thể xác định nếu `order_id` duy nhất. Khi page kết thúc ở `(09:00:00, 102)`, phần tiếp theo có thể bắt đầu sau tuple đó:

```sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND order_id > :lastOrderId)
ORDER BY created_at ASC, order_id ASC
```

Điều kiện trên minh họa cách so sánh key tổng hợp theo thứ tự từ trái sang phải. `PagingQueryProvider` tạo cú pháp cụ thể phù hợp với database và cấu hình sort key.

Nếu query join làm một `order_id` xuất hiện nhiều lần, khóa chính của bảng `orders` không còn duy nhất cho kết quả query. Khi đó cần bổ sung key của bảng join hoặc điều chỉnh query để mỗi item có tuple sort key duy nhất.

## 6. Sort key tổng hợp (composite sort key)

Khi một cột không đủ duy nhất, có thể dùng nhiều cột theo thứ tự ưu tiên:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("business_date", Order.ASCENDING);
sortKeys.put("tenant_id", Order.ASCENDING);
sortKeys.put("order_id", Order.ASCENDING);
```

Thứ tự logic là:

1. Sắp xếp theo `business_date`.
2. Nếu cùng ngày, sắp xếp theo `tenant_id`.
3. Nếu cùng ngày và tenant, sắp xếp theo `order_id`.

Tuple này cần duy nhất trên toàn bộ tập kết quả. Nếu `order_id` chỉ duy nhất trong một tenant, việc thêm `tenant_id` vào tuple sẽ giúp phân biệt các dòng giữa tenant.

Khi dùng composite sort key:

- Dùng `LinkedHashMap` để thứ tự key rõ ràng.
- Chọn chiều ASC/DESC nhất quán với cách muốn duyệt dữ liệu.
- Bảo đảm mọi cột đều có trong query và được database hiểu đúng.
- Bảo đảm tuple cuối cùng thực sự duy nhất.
- Kiểm thử ranh giới khi các cột đầu tiên có giá trị trùng.

Không nên chọn nhiều cột tùy ý chỉ để query có vẻ được sắp xếp. Mỗi cột bổ sung làm điều kiện tiếp tục phức tạp hơn; hãy chọn tập key nhỏ nhất đủ tạo thứ tự duy nhất và ổn định.

## 7. ASC và DESC

Sort key có thể dùng thứ tự tăng dần hoặc giảm dần:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("created_at", Order.DESCENDING);
sortKeys.put("order_id", Order.DESCENDING);
```

Ví dụ này đọc đơn hàng mới nhất trước. Nếu dùng nhiều cột với hướng khác nhau, cần hiểu chính xác thứ tự tuple và query provider có hỗ trợ tổ hợp hướng đó theo database hay không.

Điều quan trọng không chỉ là chiều sắp xếp mà còn là tính ổn định. Nếu dùng `created_at DESC` và `order_id DESC`, giá trị checkpoint phải được tiếp tục theo đúng thứ tự giảm dần. Không thay đổi hướng sort giữa lần chạy đầu và restart của cùng JobInstance.

## 8. Paging query và keyset continuation

Để lấy page tiếp theo, reader cần biết vị trí cuối cùng của page trước. Với sort key duy nhất tăng dần, ý tưởng truy vấn là:

```sql
-- Page đầu tiên
SELECT order_id, customer_id, amount
FROM orders
WHERE status = :status
ORDER BY order_id ASC
FETCH FIRST :pageSize ROWS ONLY;

-- Các page tiếp theo, minh họa keyset predicate
SELECT order_id, customer_id, amount
FROM orders
WHERE status = :status
  AND order_id > :lastOrderId
ORDER BY order_id ASC
FETCH FIRST :pageSize ROWS ONLY;
```

Cú pháp giới hạn page trong ví dụ phụ thuộc database. `JdbcPagingItemReader` không yêu cầu ứng dụng tự viết hai query như trên khi dùng builder; `PagingQueryProvider` tạo query theo database và sort keys.

Với composite key `(created_at, order_id)`, predicate tiếp tục có dạng:

```sql
WHERE status = :status
  AND (
       created_at > :lastCreatedAt
       OR (created_at = :lastCreatedAt AND order_id > :lastOrderId)
  )
ORDER BY created_at ASC, order_id ASC
```

Đây là keyset pagination: dùng giá trị sort key cuối cùng để tìm các dòng sau đó. Nó khác với offset pagination, nơi database phải bỏ qua một số lượng dòng đã đọc trước đó, ví dụ `OFFSET 500000`. Với tập dữ liệu lớn, keyset thường tránh chi phí tăng dần của offset và có semantics restart rõ hơn khi key ổn định.

Không nên tự giả định mọi database provider đều tạo cùng một SQL. Hãy kiểm tra query được sinh ra hoặc log SQL trong môi trường test nếu cần tối ưu theo dialect.

## 9. Paging khác offset pagination như thế nào?

Hai chiến lược thường được nhắc đến:

| Đặc điểm | Offset pagination | Keyset/paging theo sort key |
|---|---|---|
| Vị trí page tiếp theo | Số dòng cần bỏ qua (`OFFSET`) | Giá trị sort key cuối page trước |
| Chi phí ở page sâu | Có thể tăng do database phải đi qua nhiều dòng | Thường ổn định hơn nếu có index phù hợp |
| Restart | Cần offset/page index chính xác; dữ liệu chèn/xóa có thể làm lệch | Dựa vào key đã lưu; ổn định hơn nếu key bất biến |
| Điều kiện | Cần ORDER BY xác định | Cần sort key duy nhất và thứ tự xác định |
| Dữ liệu thay đổi | Insert/delete phía trước offset có thể làm trùng hoặc bỏ sót | Insert/update liên quan key cũng có thể làm thay đổi tập còn lại; cần snapshot/high-watermark khi cần nhất quán |

`JdbcPagingItemReader` dùng `PagingQueryProvider` và sort keys để tạo query theo database. Chi tiết query không phải lúc nào cũng giống cú pháp offset. Điểm quan trọng ở cấp ứng dụng là phải cung cấp sort key duy nhất, ổn định để provider có thể xác định page tiếp theo và reader có thể restart.

## 10. Page size, fetch size và chunk size

Ba khái niệm này có vai trò khác nhau:

- **Page size:** số dòng reader yêu cầu trong một page từ database.
- **Fetch size:** gợi ý cho JDBC driver về số dòng nên lấy mỗi lần từ database; cách áp dụng phụ thuộc driver.
- **Chunk size:** số item được xử lý trong một chunk transaction trước khi commit theo cấu hình Step.

Ví dụ:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRecord, OrderOutput>chunk(200, transactionManager)
        .reader(orderPagingReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

Trong khi reader được cấu hình `pageSize(500)`, Step có `chunk(200)`. Reader có thể nạp một page 500 dòng và cung cấp item cho nhiều chunk. Page size không tự quyết định transaction commit interval.

| Cấu hình | Ví dụ | Ảnh hưởng chính |
|---|---:|---|
| `pageSize` | 500 | Số dòng mỗi paging query/page buffer. |
| `fetchSize` | 500 | Hint cho JDBC driver khi fetch rows. |
| `chunk` | 200 | Số item trong một chunk transaction. |

### Chọn page size

Page size lớn có thể giảm số query nhưng tăng bộ nhớ cho page và thời gian một lần đọc. Page size nhỏ giảm lượng dữ liệu mỗi query nhưng tăng số lần round trip.

Hãy cân nhắc:

- Kích thước object sau mapping, không chỉ kích thước dòng database.
- Độ trễ giữa ứng dụng và database.
- Chi phí query và execution plan.
- Connection pool và số worker đồng thời.
- Chunk size và tần suất commit.
- Thời gian restart và lượng dữ liệu cần nạp lại.

Không có một page size tối ưu cho mọi Job. Hãy đo throughput, heap usage, query latency và database load với dữ liệu gần production.

## 11. Điều kiện lọc và sort key cần phối hợp

Query thường lọc theo một hoặc nhiều điều kiện rồi sắp xếp kết quả:

```sql
SELECT order_id, tenant_id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at ASC, order_id ASC
```

Một index phù hợp có thể bắt đầu bằng các cột equality filter rồi đến sort key, ví dụ:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (tenant_id, status, created_at, order_id);
```

Index này chỉ là ví dụ thiết kế. Cấu trúc tốt nhất phụ thuộc database, selectivity, cardinality, điều kiện query và các truy vấn khác. Hãy xem execution plan thực tế; không tạo index theo công thức máy móc.

Nếu sort key không được index, database có thể phải sort một tập dữ liệu lớn ở mỗi page. Nếu điều kiện filter không được index, page query có thể scan nhiều dòng trước khi trả kết quả.

### Cột sort key phải được chọn

Reader cần giá trị sort key để theo dõi vị trí tiếp tục. Hãy bảo đảm các cột sort key nằm trong `selectClause` và tên được khai báo khớp với query provider. Khi dùng alias hoặc join, cần xác nhận provider có thể tham chiếu key trong điều kiện paging và `ORDER BY` đúng với database.

## 12. Sort key có NULL hoặc collation đặc biệt

Sort key nên tránh NULL nếu có thể. Thứ tự NULL có thể khác nhau giữa database hoặc phụ thuộc `NULLS FIRST`/`NULLS LAST`. Nếu một page kết thúc tại giá trị NULL, predicate tiếp tục có thể khó biểu diễn đúng và không nhất quán giữa dialect.

Các khuyến nghị:

- Ưu tiên cột `NOT NULL` làm sort key.
- Nếu bắt buộc dùng cột có NULL, chuẩn hóa bằng một biểu thức/cột generated có semantics rõ và kiểm tra provider hỗ trợ.
- Với chuỗi, hiểu collation/case sensitivity và cách so sánh của database.
- Không thay đổi collation hoặc kiểu dữ liệu giữa lần chạy đầu và restart.
- Bổ sung khóa duy nhất không NULL làm tie-breaker.

Ví dụ, nếu cần sắp xếp theo tên khách hàng nhưng tên có thể NULL hoặc trùng, có thể sắp xếp theo một giá trị chuẩn hóa cộng với `customer_id` duy nhất. Tuy nhiên, biểu thức sort cần được hỗ trợ bởi query provider và index phù hợp.

## 13. Dữ liệu thay đổi trong khi reader paging

Sort key ổn định giúp xác định thứ tự, nhưng không tự bảo đảm tập dữ liệu bất biến. Trong khi Job đọc nhiều page, ứng dụng khác có thể thêm, xóa hoặc cập nhật dòng.

Ví dụ với `order_id` tăng dần:

- Một dòng mới có ID lớn hơn key hiện tại có thể xuất hiện ở page sau.
- Một dòng mới có ID nhỏ hơn hoặc bằng key đã đọc có thể không được nhìn thấy trong lần chạy hiện tại.
- Một dòng bị xóa trước khi reader tới page tương ứng sẽ không còn được trả về.
- Nếu sort key có thể thay đổi, một dòng có thể di chuyển qua vị trí checkpoint, dẫn đến bỏ sót hoặc đọc lại.
- Nếu thuộc tính filter thay đổi, dòng có thể đi vào hoặc ra khỏi tập kết quả giữa các page.

Khi cần một tập dữ liệu nhất quán, hãy xác định snapshot semantics:

- Dùng transaction isolation/snapshot phù hợp với database nếu thời gian chạy và tải cho phép.
- Chụp high-watermark khi bắt đầu, ví dụ `order_id <= :maxOrderIdAtStart`.
- Dùng business date hoặc batch membership table để cố định tập item thuộc Job.
- Chọn sort key bất biến và điều kiện filter ổn định.
- Ghi identifying JobParameters hoặc ExecutionContext cho snapshot/version cần thiết khi restart.

Ví dụ high-watermark:

```sql
WHERE tenant_id = :tenantId
  AND order_id <= :maxOrderIdAtStart
ORDER BY order_id ASC
```

Giá trị `maxOrderIdAtStart` phải được chụp một lần và giữ nguyên qua restart của cùng JobInstance. Nếu tính lại ở mỗi lần mở reader, tập dữ liệu có thể thay đổi ngoài ý muốn.

## 14. Restart và sort key

`JdbcPagingItemReader` hỗ trợ restart khi state được bật và reader có tên ổn định. Reader lưu thông tin vị trí dựa trên sort key trong `ExecutionContext`, sau đó dùng thông tin này để tiếp tục đọc sau điểm đã commit.

Ví dụ:

```java
new JdbcPagingItemReaderBuilder<OrderRecord>()
        .name("orderPagingReader")
        .dataSource(dataSource)
        .selectClause("select order_id, amount")
        .fromClause("from orders")
        .whereClause("where status = :status")
        .parameterValues(Map.of("status", "READY"))
        .sortKeys(Map.of("order_id", Order.ASCENDING))
        .pageSize(500)
        .saveState(true)
        .rowMapper(orderRowMapper)
        .build();
```

Các điều kiện để restart đáng tin cậy:

- Reader có tên ổn định và duy nhất trong phạm vi Step.
- `saveState(true)` được bật nếu cần checkpoint.
- Sort key duy nhất trên kết quả query.
- Hướng sort và query filter giữ ổn định.
- JobParameters và snapshot/high-watermark giữ nguyên cho cùng JobInstance.
- Dữ liệu nguồn không thay đổi theo cách làm mất tính ổn định của checkpoint.
- Writer xử lý lại item an toàn nếu có tình huống commit không rõ ràng hoặc side effect ngoài transaction.

Không thay đổi sort key giữa hai lần chạy của cùng JobInstance. Nếu query mới dùng thứ tự khác, checkpoint cũ có thể không còn chỉ đúng vị trí tương ứng.

## 15. Sort key và phân vùng dữ liệu

Paging query thường đọc một tập dữ liệu theo một thứ tự. Nếu kết hợp với partitioning, mỗi worker cần phạm vi riêng và sort key riêng phù hợp với tập kết quả của partition.

Ví dụ manager chia theo `tenant_id`, worker đọc từng tenant và sort theo `(created_at, order_id)`. Khi đó:

- Partition key xác định worker xử lý tenant nào.
- Sort key xác định thứ tự item trong partition.
- Mỗi worker có `ExecutionContext` và checkpoint riêng.
- Sort tuple cần duy nhất trong tập kết quả của từng worker.

Không nhầm partition key với sort key. Chúng có thể trùng một phần nhưng phục vụ hai mục đích khác nhau.

Nếu nhiều worker đọc cùng một bảng, hãy bảo đảm predicate partition không chồng lấn và sort key không thay đổi. Cần giới hạn concurrency theo database connection pool và kiểm tra index cho cả partition predicate lẫn paging order.

## 16. Dùng queryProvider tùy chỉnh

Builder có thể tạo query provider từ các clause phổ biến. Với query phức tạp hoặc database cần cú pháp đặc biệt, có thể tạo `PagingQueryProvider` phù hợp rồi truyền vào reader.

Các trường hợp có thể cần provider tùy chỉnh:

- Query có join, alias hoặc expression phức tạp.
- Database có cú pháp paging riêng không được factory nhận diện đúng.
- Cần tối ưu predicate page tiếp theo theo index đặc thù.
- Cần điều khiển query đầu tiên và query các page sau.
- Query dùng composite sort key với biểu thức đặc biệt.

Khi tự cấu hình provider, vẫn phải bảo đảm hợp đồng sort key: thứ tự xác định, giá trị key có trong kết quả, predicate page tiếp theo không bỏ sót/trùng dòng và restart dùng đúng checkpoint.

Không tự viết paging SQL chỉ để né một lỗi query mà chưa kiểm tra database dialect. Một query chạy đúng page đầu có thể sai ở page thứ hai hoặc restart vì điều kiện tiếp tục không tương đương thứ tự `ORDER BY`.

## 17. Kiểm thử paging query và sort key

Kiểm thử nên tập trung vào ranh giới page, sort key trùng, composite key, restart và dữ liệu thay đổi.

### Kiểm thử không trùng và không thiếu

Tạo fixture có số dòng lớn hơn hai page và có nhiều dòng cùng giá trị ở cột sort đầu tiên. Đọc hết và so sánh tập ID:

```java
Set<Long> actualIds = new LinkedHashSet<>();
OrderRecord item;
while ((item = reader.read()) != null) {
    assertThat(actualIds.add(item.orderId()))
            .as("order_id must not be read twice")
            .isTrue();
}

assertThat(actualIds).containsExactlyElementsOf(expectedIds);
```

Test này giả định `expectedIds` đã được sắp xếp theo cùng thứ tự query. Ngoài kiểm tra số lượng, nên so sánh chính xác sequence để phát hiện dòng bị bỏ sót hoặc thứ tự không ổn định.

### Kiểm thử composite sort key

Tạo nhiều record có cùng `created_at` nhưng `order_id` khác nhau. Đặt page size nhỏ hơn số record có cùng timestamp để buộc page boundary rơi giữa nhóm trùng. Xác nhận mọi ID xuất hiện đúng một lần theo thứ tự `(created_at, order_id)`.

### Kiểm thử restart

1. Mở reader với `ExecutionContext` mới.
2. Đọc một số item và cập nhật context tại điểm checkpoint.
3. Tạo reader mới với cùng tên, query, sort keys và parameters.
4. Mở reader bằng context đã lưu.
5. Xác nhận reader tiếp tục sau item cuối đã commit, không đọc trùng hoặc bỏ sót.

Trong integration test Spring Batch, nên kiểm thử restart qua Job/Step và transaction thật để xác nhận checkpoint được commit cùng chunk như cấu hình.

### Kiểm thử dữ liệu thay đổi

- Insert dòng có sort key nhỏ hơn checkpoint.
- Insert dòng có sort key lớn hơn checkpoint.
- Xóa dòng chưa đọc.
- Thay đổi sort key hoặc filter column.
- Restart với cùng high-watermark và xác nhận tập dữ liệu không đổi theo yêu cầu.

Không phải mọi ứng dụng cần cùng snapshot isolation, nhưng test phải làm rõ semantics dữ liệu mới có được xử lý trong lần chạy hiện tại hay lần sau.

## 18. Theo dõi và tối ưu hiệu năng

Khi paging reader chậm, nên đo các chỉ số:

- Thời gian thực thi mỗi page query.
- Số page/query cho một Step.
- Số dòng đọc và tốc độ item/giây.
- Heap usage và kích thước page buffer.
- Connection wait và database CPU/I/O.
- Sort spill hoặc full table scan trong execution plan.
- Thời gian transaction chunk và commit.
- Thời gian chờ do nhiều worker cùng truy vấn.

Các hướng tối ưu thường gặp:

- Tạo index phù hợp với filter và sort key.
- Chỉ select các cột thực sự cần.
- Dùng sort key ngắn, ổn định và có index.
- Chọn page size theo đo đạc thay vì phỏng đoán.
- Đặt fetch size hợp lý theo JDBC driver.
- Tránh biểu thức trên sort key nếu khiến database không dùng index.
- Giữ query filter sargable khi có thể.
- Tránh concurrency quá cao gây contention.
- Xem execution plan của cả page đầu và page tiếp theo.

Một query có thể chạy nhanh ở page đầu nhưng chậm ở các page sâu nếu provider hoặc index không hỗ trợ predicate tiếp tục. Hãy kiểm tra query được sinh cho page tiếp theo, không chỉ query đầu tiên.

## 19. Những lỗi thường gặp

### Dùng sort key không duy nhất

Nhiều dòng cùng key ở ranh giới page có thể bị bỏ sót khi reader tiếp tục sau giá trị cuối. Bổ sung tie-breaker duy nhất, thường là primary key.

### ORDER BY khác với sortKeys

Nếu thứ tự trong query tùy chỉnh không khớp với cấu hình provider, predicate page tiếp theo có thể không phản ánh cùng thứ tự. Giữ sort definition nhất quán.

### Không select cột sort key

Reader/provider cần giá trị sort key để xây dựng vị trí tiếp tục và checkpoint. Đưa đầy đủ các sort key vào select result theo yêu cầu của provider.

### Dùng sort key có thể thay đổi

Một dòng có thể di chuyển qua checkpoint trong khi Job đang chạy. Ưu tiên khóa bất biến và snapshot rõ ràng.

### Dùng page size như chunk size

Page size điều khiển lượng dữ liệu một query; chunk size điều khiển transaction commit interval. Chọn hai giá trị độc lập theo bộ nhớ và transaction.

### Không có index hỗ trợ

Database có thể scan/sort lớn cho từng page. Kiểm tra execution plan và index cho filter/sort.

### Thay đổi parameters hoặc sort keys khi restart

Checkpoint cũ có thể không còn đúng với query mới. Giữ nguyên input, filter, high-watermark và thứ tự sort cho cùng JobInstance.

### Dữ liệu nguồn thay đổi nhưng mong snapshot tự động

Paging không tự tạo snapshot nghiệp vụ cho mọi database. Xác định isolation, high-watermark hoặc batch membership table.

### Chỉ kiểm tra page đầu

Lỗi predicate thường xuất hiện từ page thứ hai hoặc khi restart. Test nhiều page và ranh giới key trùng.

### Quá nhiều worker cùng paging một bảng

Concurrency cao có thể tăng contention và làm database chậm hơn. Đo throughput và giới hạn theo connection pool/năng lực database.

## 20. Quy trình thiết kế paging query và sort key

Khi tạo một paging reader, có thể thực hiện theo trình tự:

1. Xác định tập dữ liệu cần đọc và điều kiện filter.
2. Chọn sort key bất biến, có thứ tự xác định.
3. Bảo đảm một key hoặc composite tuple duy nhất trên kết quả query.
4. Bổ sung tie-breaker nếu cột sort chính có giá trị trùng.
5. Đưa toàn bộ sort key vào select clause và khai báo đúng thứ tự trong `sortKeys`.
6. Cấu hình `JdbcPagingItemReader` và `PagingQueryProvider` phù hợp database.
7. Chọn `pageSize`, `fetchSize` và chunk size độc lập.
8. Tạo index theo filter/sort và kiểm tra execution plan của các page.
9. Bật `saveState` và giữ tên reader ổn định để hỗ trợ restart.
10. Chốt snapshot/high-watermark nếu nguồn có thể thay đổi trong lúc đọc.
11. Kiểm thử page boundary, duplicate key, composite key và restart.
12. Đo query latency, heap, throughput và database load trước khi tăng concurrency.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Đọc database theo từng nhóm dòng | `JdbcPagingItemReader` |
| Tạo query paging theo dialect database | `PagingQueryProvider` |
| Sắp xếp theo khóa chính duy nhất | Một sort key ASC hoặc DESC |
| Cột sort chính bị trùng | Composite sort key có tie-breaker duy nhất |
| Restart sau chunk đã commit | `saveState(true)`, reader name ổn định và sort key ổn định |
| Tập dữ liệu thay đổi trong lúc Job chạy | Snapshot, high-watermark hoặc batch membership table |
| Tối ưu page sâu | Keyset predicate và index phù hợp; kiểm tra query provider thực tế |

## Kết luận

`JdbcPagingItemReader` đọc database theo page bằng query do `PagingQueryProvider` tạo. `sortKeys` xác định thứ tự dòng, page tiếp theo và vị trí restart; vì vậy, sort key phải ổn định và duy nhất trên từng dòng kết quả. Nếu một cột có thể trùng, hãy dùng composite sort key với khóa duy nhất làm tie-breaker. Phân biệt `pageSize`, JDBC `fetchSize` và chunk size; tạo index phù hợp với filter/sort; bật state khi cần restart; và xác định snapshot hoặc high-watermark khi dữ liệu có thể thay đổi trong lúc Job chạy. Kiểm thử nhiều page, ranh giới key trùng và restart để bảo đảm không đọc thiếu hoặc trùng dữ liệu.
