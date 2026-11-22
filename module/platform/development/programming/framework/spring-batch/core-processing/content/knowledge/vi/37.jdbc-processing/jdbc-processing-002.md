# Đọc theo page và sort ổn định

Khi đọc hàng triệu bản ghi từ database, truy vấn toàn bộ kết quả trong một lần có thể tiêu tốn nhiều bộ nhớ, giữ cursor hoặc connection quá lâu và khó khôi phục sau lỗi. Spring Batch cung cấp `JdbcPagingItemReader<T>` để đọc dữ liệu theo từng page. Reader thực hiện nhiều truy vấn có giới hạn, chuyển từng hàng thành item và lưu checkpoint để hỗ trợ restart.

Paging chỉ đáng tin cậy khi thứ tự dữ liệu được xác định. Nếu các page không dùng cùng một quy tắc sắp xếp ổn định, một bản ghi có thể bị lặp hoặc bỏ sót ở ranh giới page, đặc biệt khi sort column không duy nhất hoặc dữ liệu thay đổi trong lúc job chạy. Vì vậy, thiết kế sort key là phần cốt lõi khi dùng `JdbcPagingItemReader`.

## 1. Vì sao cần đọc theo page?

Giả sử bảng `orders` có vài triệu dòng. Một cách đọc đơn giản là chạy một câu `SELECT` trả về toàn bộ kết quả. Với dữ liệu lớn, cách này có thể:

- Tạo tập kết quả lớn và gây áp lực lên bộ nhớ ứng dụng hoặc driver.
- Giữ cursor, statement và connection trong thời gian dài.
- Làm transaction kéo dài nếu toàn bộ dữ liệu được xử lý trong một đơn vị lớn.
- Khó tiếp tục từ vị trí đã xử lý khi job bị lỗi.

Paging chia dữ liệu thành các nhóm nhỏ:

```text
Database table
      |
      v
Page 1: rows 1-500
      |
      v
Page 2: rows 501-1000
      |
      v
Page 3: rows 1001-1500
      |
     ...
      v
No more rows
```

`JdbcPagingItemReader` truy vấn từng page và trả item cho Spring Batch theo từng lần `read()`. Step vẫn gom item thành chunk để process/write và commit transaction. Page size và chunk size là hai cấu hình liên quan nhưng không đồng nghĩa.

## 2. Paging khác với cursor reading

Spring Batch có nhiều reader JDBC. Hai cách thường được so sánh là `JdbcCursorItemReader` và `JdbcPagingItemReader`.

| Tiêu chí | `JdbcCursorItemReader` | `JdbcPagingItemReader` |
|---|---|---|
| Cách đọc | Mở một cursor/result set và duyệt lần lượt. | Chạy nhiều truy vấn, mỗi truy vấn lấy một page. |
| Kết nối | Thường giữ cursor/connection trong thời gian đọc. | Thực hiện truy vấn theo page; mỗi lần lấy page cần truy vấn database. |
| Restart | Có thể cần mở lại và bỏ qua số item đã đọc tùy reader/state. | Lưu sort key cuối cùng để truy vấn tiếp từ vị trí phù hợp. |
| Yêu cầu sort | Cần thứ tự truy vấn phù hợp nếu nghiệp vụ phụ thuộc thứ tự. | Cần sort key ổn định, tốt nhất là duy nhất để không mất/lặp dữ liệu. |
| Phù hợp | Database/driver hỗ trợ cursor tốt và muốn đọc một result set liên tục. | Muốn lấy dữ liệu theo page và có cơ chế tiếp tục theo sort key. |

Paging không tự động nhanh hơn cursor trong mọi database. Nó đổi một truy vấn dài thành nhiều truy vấn nhỏ; hiệu năng phụ thuộc index, query plan, page size, latency và đặc tính database.

## 3. Các thành phần của JdbcPagingItemReader

`JdbcPagingItemReader<T>` sử dụng `PagingQueryProvider` để tạo câu SQL phù hợp với database. Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `DataSource` | Kết nối tới database. |
| `selectClause` | Các cột được lấy ra, bao gồm cả sort key cần thiết. |
| `fromClause` | Bảng và join tạo nguồn dữ liệu. |
| `whereClause` | Điều kiện lọc cố định cho tập dữ liệu của job. |
| `sortKeys` | Các cột và hướng sắp xếp dùng để tạo page và tiếp tục sau checkpoint. |
| `RowMapper<T>` | Chuyển mỗi `ResultSet` row thành Java item. |
| `pageSize` | Số dòng được lấy trong một truy vấn page. |
| `ExecutionContext` | Lưu state cần thiết để restart. |

Ví dụ cấu hình cơ bản:

```java
@Bean
@StepScope
JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['status']}") String status) {

    Map<String, Order> sortKeys = new LinkedHashMap<>();
    sortKeys.put("id", Order.ASCENDING);

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select id, customer_id, status, created_at, total_amount")
            .fromClause("from orders")
            .whereClause("where status = :status")
            .parameterValues(Map.of("status", status))
            .sortKeys(sortKeys)
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("id"),
                    rs.getLong("customer_id"),
                    rs.getString("status"),
                    rs.getTimestamp("created_at").toInstant(),
                    rs.getBigDecimal("total_amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Trong ví dụ, `id` là khóa duy nhất và được sắp xếp tăng dần. `whereClause` giới hạn dữ liệu theo status. `parameterValues` truyền giá trị vào placeholder, tránh ghép chuỗi tham số trực tiếp vào SQL.

`sortKeys` được dùng bởi query provider để tạo thứ tự và điều kiện lấy page tiếp theo. Không tự thêm `ORDER BY` vào `selectClause` hoặc `whereClause` nếu query provider đã chịu trách nhiệm tạo order clause.

## 4. PagingQueryProvider và SQL theo database

Các database có cú pháp paging khác nhau. Ví dụ, có hệ quản trị dùng `LIMIT`, hệ khác dùng `OFFSET/FETCH`, `ROWNUM` hoặc cấu trúc truy vấn khác. `PagingQueryProvider` trừu tượng hóa khác biệt đó.

`JdbcPagingItemReader` có thể lấy query provider phù hợp từ `DataSource` thông qua `SqlPagingQueryProviderFactoryBean`/factory được Spring Batch sử dụng. Khi dùng builder với `DataSource`, `selectClause`, `fromClause`, `whereClause` và `sortKeys`, framework có thể tạo provider theo database metadata.

Có thể cấu hình provider rõ ràng nếu cần kiểm soát:

```java
@Bean
SqlPagingQueryProviderFactoryBean orderQueryProvider(DataSource dataSource) {
    SqlPagingQueryProviderFactoryBean provider =
            new SqlPagingQueryProviderFactoryBean();
    provider.setDataSource(dataSource);
    provider.setSelectClause(
            "select id, customer_id, status, created_at, total_amount");
    provider.setFromClause("from orders");
    provider.setWhereClause("where status = :status");

    Map<String, Order> sortKeys = new LinkedHashMap<>();
    sortKeys.put("id", Order.ASCENDING);
    provider.setSortKeys(sortKeys);
    return provider;
}
```

Sau đó truyền `PagingQueryProvider` vào reader theo API của phiên bản Spring Batch đang sử dụng. Khi dùng factory bean trong cấu hình Spring, cần inject object `PagingQueryProvider` đã được tạo từ factory, không truyền trực tiếp factory bean thay cho provider.

Nếu query phức tạp, có CTE, join hoặc cú pháp đặc thù, hãy kiểm tra SQL mà provider tạo ra và execution plan trên database thật. Một query chạy được ở page đầu chưa chắc điều kiện lấy page tiếp theo cũng đúng nếu sort key hoặc alias không được khai báo phù hợp.

## 5. Sort ổn định nghĩa là gì?

Một thứ tự sắp xếp ổn định phải xác định được vị trí của từng hàng một cách nhất quán. `ORDER BY created_at` có thể chưa đủ nếu nhiều hàng có cùng timestamp.

Ví dụ:

| id | created_at | customer_id |
|---:|---|---|
| 101 | 2026-11-15 09:00:00 | 12 |
| 102 | 2026-11-15 09:00:00 | 15 |
| 103 | 2026-11-15 09:00:00 | 18 |
| 104 | 2026-11-15 09:01:00 | 20 |

Nếu chỉ sort theo `created_at`, ba hàng đầu có cùng sort value. Database không có nghĩa vụ trả các hàng cùng giá trị theo một thứ tự cố định nếu không có thêm khóa phân biệt.

Hãy thêm một khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at ASC, id ASC
```

Trong đó:

- `created_at` tạo thứ tự nghiệp vụ chính.
- `id` phân biệt các hàng có cùng timestamp.

Kết hợp hai cột tạo một thứ tự toàn phần nếu cặp `(created_at, id)` là duy nhất. Nếu `id` là primary key, điều kiện này được bảo đảm.

## 6. Vì sao sort key phải duy nhất?

`JdbcPagingItemReader` cần xác định hàng cuối cùng của page để tạo truy vấn cho page tiếp theo và lưu thông tin restart. Nếu sort key không duy nhất, nhiều hàng có thể có cùng giá trị ở ranh giới page.

Ví dụ page size là 2 và chỉ sort theo `created_at`:

```text
Page 1:
  id=101, created_at=09:00
  id=102, created_at=09:00

Page 2:
  id=103, created_at=09:00
  id=104, created_at=09:01
```

Nếu điều kiện lấy page tiếp theo chỉ dựa vào `created_at > 09:00`, hàng `id=103` có cùng timestamp với hàng cuối page trước và có thể bị bỏ qua. Với paging theo sort key, điều kiện continuation cần phân biệt thứ tự của từng hàng.

Thêm `id` làm tie-breaker:

```text
ORDER BY created_at ASC, id ASC

Page 1:
  (09:00, 101)
  (09:00, 102)

Page 2:
  (09:00, 103)
  (09:01, 104)
```

Khóa sắp xếp tổng hợp `(created_at, id)` tạo thứ tự rõ ràng giữa các page. Tài liệu Spring Batch yêu cầu sort key phải duy nhất để bảo đảm không mất dữ liệu giữa các lần thực thi/paging.

## 7. Dùng primary key làm sort key

Nếu không cần thứ tự nghiệp vụ khác, primary key tăng dần thường là sort key đơn giản và đáng tin cậy:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("id", Order.ASCENDING);
```

Ưu điểm:

- Primary key thường duy nhất và không null.
- Có index sẵn, giúp database tìm page tiếp theo hiệu quả.
- Không thay đổi trong vòng đời bản ghi nếu schema được thiết kế đúng.
- Checkpoint dễ biểu diễn bằng một giá trị.

Nhược điểm là thứ tự có thể không phản ánh thứ tự nghiệp vụ. Nếu cần xử lý theo ngày tạo, sequence hoặc priority, hãy dùng khóa nghiệp vụ đó cùng primary key làm tie-breaker.

Không dùng một cột tăng dần làm sort key nếu giá trị của nó có thể bị cập nhật trong khi job chạy. Một sort key mutable có thể khiến hàng di chuyển từ phía sau checkpoint lên phía trước hoặc ngược lại.

## 8. Dùng nhiều sort key

`sortKeys` có thể chứa nhiều cột. Thứ tự khai báo trong map phải phản ánh thứ tự sắp xếp mong muốn.

Ví dụ cần đọc theo ngày nghiệp vụ, sau đó theo customer ID và order ID:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("business_date", Order.ASCENDING);
sortKeys.put("customer_id", Order.ASCENDING);
sortKeys.put("id", Order.ASCENDING);
```

Tương đương về mặt ý nghĩa:

```sql
ORDER BY business_date ASC, customer_id ASC, id ASC
```

Nếu `id` duy nhất, toàn bộ thứ tự là duy nhất ngay cả khi nhiều hàng có cùng `business_date` và `customer_id`.

Nên dùng `LinkedHashMap` để giữ thứ tự khai báo sort key. Không dựa vào thứ tự iteration của một map không cam kết ordering khi nhiều sort key có quan hệ ưu tiên.

## 9. Kết hợp ASC và DESC

Các sort key có thể dùng hướng khác nhau:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("priority", Order.DESCENDING);
sortKeys.put("created_at", Order.ASCENDING);
sortKeys.put("id", Order.ASCENDING);
```

Ý nghĩa:

1. Priority cao được đọc trước.
2. Trong cùng priority, đọc theo thời gian tạo tăng dần.
3. Nếu timestamp trùng, dùng ID để phân biệt.

Khi dùng sort key hỗn hợp ASC/DESC, query provider phải tạo predicate continuation phù hợp cho từng chiều. Hãy kiểm thử trên database thực tế và phiên bản Spring Batch đang dùng, đặc biệt khi có nhiều cột và page boundary rơi vào nhóm giá trị trùng.

Không tự viết điều kiện `WHERE` tiếp trang dựa trên một phép so sánh đơn giản nếu có nhiều hướng sắp xếp. Với `(priority DESC, created_at ASC, id ASC)`, điều kiện tiếp tục phải tôn trọng thứ tự từ điển và hướng của từng cột.

## 10. Sort key cần xuất hiện trong select clause

Reader cần các giá trị sort key để tạo điều kiện page tiếp theo và lưu checkpoint. Vì vậy, các cột sort key cần có trong dữ liệu được select.

Ví dụ:

```java
.selectClause("select id, created_at, customer_id, total_amount")
.fromClause("from orders")
```

Nếu sort theo `created_at` và `id`, cả hai cột phải có trong select list. Không nên chỉ select field hiển thị cho processor rồi bỏ cột dùng để paging.

Với join, hãy xác định rõ sort key thuộc bảng nào và dùng tên cột/alias phù hợp với query provider. Tránh tên cột mơ hồ khi nhiều bảng cùng có `id`, `created_at` hoặc `status`.

## 11. Sort key và index database

Sort ổn định bảo đảm tính đúng; index phù hợp giúp paging chạy hiệu quả.

Ví dụ query:

```sql
SELECT id, customer_id, status, created_at, total_amount
FROM orders
WHERE status = ?
ORDER BY created_at ASC, id ASC
```

Một index có thể cân nhắc:

```sql
CREATE INDEX idx_orders_status_created_id
    ON orders(status, created_at, id);
```

Thứ tự cột index cần dựa trên selectivity, predicate và query plan của database. Index ví dụ trên đặt cột lọc `status` trước các cột sort. Với database hỗ trợ index direction hoặc covering index, có thể tối ưu thêm theo workload.

Không tạo index chỉ dựa vào hình thức SQL. Hãy kiểm tra `EXPLAIN`/execution plan, số dòng được scan, sort operation, logical reads và thời gian mỗi page. Index bổ sung cũng làm tăng chi phí insert/update và dung lượng lưu trữ.

## 12. Page size và chunk size khác nhau

`pageSize` là số dòng reader yêu cầu trong một lần truy vấn database. `chunkSize` là số item Spring Batch gom trước khi gọi writer và commit transaction.

Ví dụ:

```java
new JdbcPagingItemReaderBuilder<Order>()
        .name("orderReader")
        .dataSource(dataSource)
        .selectClause("select id, status, total_amount")
        .fromClause("from orders")
        .sortKeys(Map.of("id", Order.ASCENDING))
        .rowMapper(orderRowMapper)
        .pageSize(1000)
        .build();
```

Step:

```java
new StepBuilder("processOrdersStep", jobRepository)
        .<Order, Order>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

Reader có thể tải page 1.000 dòng nhưng step commit sau mỗi 200 item. Trong trường hợp này, một page có thể phục vụ nhiều chunk. Ranh giới page không bắt buộc trùng với ranh giới transaction.

Một điểm bắt đầu thường được thử là page size bằng chunk size hoặc một bội số phù hợp của chunk size, nhưng cần benchmark. Page lớn có thể giảm số truy vấn nhưng tăng lượng dữ liệu giữ trong buffer; chunk lớn tăng transaction duration và lượng item sống đồng thời.

## 13. Chọn page size theo workload

Không có page size tối ưu cho mọi database và item. Cần cân bằng:

- Số lần round trip tới database.
- Kích thước row và object sau mapping.
- Heap của batch worker.
- Tốc độ processor và writer.
- Thời gian commit và lock duration.
- Latency mạng giữa ứng dụng và database.
- Khả năng của driver và database buffer.

Ví dụ tham khảo về số page cho một triệu hàng:

| Page size | Số page xấp xỉ |
|---:|---:|
| 100 | 10.000 |
| 500 | 2.000 |
| 1.000 | 1.000 |
| 5.000 | 200 |

Đây chỉ là phép tính số page, không phải dự đoán thời gian chạy. Page size lớn có thể giảm round trip nhưng query nặng hơn và tăng memory. Page size nhỏ giảm lượng dữ liệu mỗi lần nhưng tăng số truy vấn.

Đo ít nhất throughput, thời gian query mỗi page, heap, GC, transaction duration và database load. Chọn giá trị phù hợp với dữ liệu thực tế thay vì chỉ tăng page size để giảm số query.

## 14. Phân biệt pageSize và fetchSize

`pageSize` là kích thước page mà `JdbcPagingItemReader` yêu cầu query provider lấy từ database. `fetchSize` là JDBC hint cho driver về số hàng nên fetch từ result set trong một lần trao đổi/đọc.

Hai thuộc tính này không có cùng ý nghĩa:

| Thuộc tính | Điều khiển |
|---|---|
| `pageSize` | Số item trong một page logic của Spring Batch paging query. |
| `fetchSize` | Hint cho JDBC driver về cách fetch row từ ResultSet. |
| `chunkSize` | Số item xử lý trong một transaction chunk. |

Ví dụ:

```java
new JdbcPagingItemReaderBuilder<Order>()
        .name("orderReader")
        .dataSource(dataSource)
        .selectClause("select id, total_amount")
        .fromClause("from orders")
        .sortKeys(Map.of("id", Order.ASCENDING))
        .rowMapper(orderRowMapper)
        .pageSize(1000)
        .fetchSize(500)
        .build();
```

`fetchSize` chỉ là hint; driver có thể bỏ qua hoặc diễn giải khác nhau. Paging query đã giới hạn số row ở mức SQL, còn fetch size điều khiển việc driver lấy các row của result set như thế nào.

## 15. Paging theo điều kiện cố định

Một job thường chỉ xử lý một tập con dữ liệu. Có thể dùng `whereClause` và `parameterValues` để giới hạn:

```java
.whereClause("where status = :status and business_date = :businessDate")
.parameterValues(Map.of(
        "status", "READY",
        "businessDate", Date.valueOf(businessDate)))
```

Điều kiện nên xác định tập dữ liệu của JobInstance. Nếu cùng một job được restart, các tham số lọc cần giữ nguyên. Thay `businessDate` hoặc `status` trong lần restart có thể khiến reader đọc một tập dữ liệu khác nhưng vẫn dùng checkpoint cũ.

Với job xử lý cửa sổ thời gian, nên chốt `fromTime` và `toTime` trong JobParameters trước khi launch. Tránh dùng biểu thức `CURRENT_TIMESTAMP` thay đổi theo từng page nếu mục tiêu là một snapshot logic nhất quán.

## 16. Offset paging và keyset paging

Paging có thể được triển khai theo các chiến lược SQL khác nhau.

**Offset paging** dùng số dòng cần bỏ qua:

```sql
SELECT id, created_at
FROM orders
ORDER BY created_at, id
OFFSET 10000 ROWS FETCH NEXT 500 ROWS ONLY
```

Ở offset lớn, database có thể phải duyệt/bỏ qua nhiều hàng trước khi trả page. Nếu dữ liệu thay đổi giữa các truy vấn, vị trí offset cũng có thể dịch chuyển.

**Keyset/seek paging** dùng giá trị sort key cuối page trước để lấy các hàng tiếp theo:

```sql
SELECT id, created_at
FROM orders
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at, id
FETCH FIRST 500 ROWS ONLY
```

Điều kiện keyset bám theo khóa sắp xếp thay vì số hàng đã bỏ qua. `JdbcPagingItemReader` dùng `PagingQueryProvider` để tạo các truy vấn paging phù hợp, bao gồm điều kiện dựa trên sort key cho page tiếp theo và restart.

Không nên đồng nhất mọi database paging với cú pháp `OFFSET`. Query provider cụ thể có thể dùng chiến lược khác. Hãy kiểm tra SQL được tạo ra cho database đang dùng.

## 17. Dữ liệu thay đổi trong lúc paging

Sort key duy nhất giải quyết tính xác định của thứ tự, nhưng không tự tạo một snapshot bất biến của bảng.

Giả sử job đọc theo `id` tăng dần và đã checkpoint đến `id=5000`:

- Một row mới có `id=6000` được insert trước khi job kết thúc có thể được đọc ở page sau.
- Một row mới có `id=4500` được insert sau checkpoint có thể không được đọc trong lần chạy này.
- Một row chưa đọc bị xóa sẽ không xuất hiện.
- Một row chưa đọc được cập nhật sort key từ 7000 xuống 4000 có thể di chuyển về trước checkpoint và bị bỏ qua.
- Một row đã đọc được cập nhật sort key từ 3000 lên 8000 có thể xuất hiện lại ở phía sau tùy truy vấn và state.

Hành vi chính xác phụ thuộc isolation level, query provider, database và cách transaction được mở. Nếu job cần xử lý đúng một tập dữ liệu xác định tại thời điểm bắt đầu, cần thiết kế snapshot/window thay vì chỉ dựa vào sort key.

Các lựa chọn:

- Chọn một khoảng thời gian hoặc batch ID bất biến trong `whereClause`.
- Dùng snapshot isolation hoặc transaction isolation phù hợp nếu database hỗ trợ và thời gian transaction chấp nhận được.
- Materialize danh sách khóa cần xử lý vào bảng staging/manifest trước khi đọc.
- Dùng cột trạng thái và claim/locking theo thiết kế để xác định record thuộc batch.
- Đóng băng input set bằng quy trình upstream trước khi launch.

Không mặc định dùng transaction `READ COMMITTED` là có snapshot nhất quán xuyên suốt tất cả page. Mỗi query có thể nhìn thấy dữ liệu commit mới tùy database/isolation.

## 18. Sort key nên bất biến trong thời gian xử lý

Một sort key có thể duy nhất nhưng vẫn không ổn định nếu giá trị thay đổi trong lúc job chạy. Primary key thường phù hợp vì không đổi. Các cột như `status`, `priority`, `updated_at` có thể thay đổi bởi ứng dụng khác.

Ví dụ không nên chỉ sort theo status:

```sql
ORDER BY status, id
```

Nếu status thay đổi từ `READY` sang `DONE` khi job hoặc một process khác cập nhật dữ liệu, hàng có thể chuyển vị trí. Nếu `whereClause` cũng lọc status, row có thể biến mất khỏi tập kết quả hoặc chuyển ra/vào tập dữ liệu.

Nếu status là điều kiện claim, hãy xác định rõ thời điểm claim và cách checkpoint. Có thể dùng cột `batch_id` bất biến cho batch đang xử lý hoặc bảng staging chứa các ID đã được chọn.

## 19. Sort key có null

Sort key có thể cho phép `NULL` trong schema, nhưng thứ tự null (đầu hay cuối) khác nhau giữa database và query. Điều kiện keyset cũng phức tạp hơn khi so sánh với null vì SQL dùng logic ba giá trị.

Ví dụ:

```sql
ORDER BY processed_at ASC, id ASC
```

Nếu `processed_at` có thể null, cần xác định rõ quy tắc:

- Loại bỏ null trong `whereClause` nếu nghiệp vụ không xử lý chúng.
- Chuẩn hóa null thành một giá trị sort riêng bằng expression được hỗ trợ và select đúng expression.
- Dùng cột không null làm sort key chính, hoặc bổ sung discriminator để đặt nhóm null rõ ràng.

Đơn giản nhất là dùng sort key không null và duy nhất, thường là primary key. Nếu bắt buộc sort theo nullable column, cần test page boundary qua nhóm null trên database thật.

## 20. Sort key trong query có JOIN hoặc GROUP BY

Query phức tạp cần một sort key đại diện cho mỗi item đầu ra. Nếu join một order với nhiều order line, kết quả có thể có nhiều row cho cùng `order.id`.

Ví dụ:

```sql
SELECT o.id, o.created_at, l.id AS line_id, l.sku
FROM orders o
JOIN order_lines l ON l.order_id = o.id
ORDER BY o.created_at, o.id
```

Nếu reader trả mỗi joined row như một item, `(o.created_at, o.id)` không duy nhất vì một order có nhiều line. Cần thêm `l.id` làm tie-breaker:

```sql
ORDER BY o.created_at, o.id, l.id
```

Nếu item logic là một order với collection lines, có thể cần query/grouping khác để mỗi hàng output là một order duy nhất. `GROUP BY` và aggregate cũng cần sort key duy nhất cho mỗi group.

Hãy xác định item boundary trước khi chọn sort key. Sort key phải duy nhất trên tập hàng mà reader thực sự trả về, không chỉ duy nhất trên một bảng nguồn.

## 21. Sort key và alias

Với query join, tên cột có thể mơ hồ. Có thể cần alias trong select list, nhưng query provider cũng cần biết đúng tên sort column để tạo order/continuation predicate.

Ví dụ:

```sql
SELECT o.id AS order_id,
       o.created_at AS order_created_at,
       l.id AS line_id
FROM orders o
JOIN order_lines l ON l.order_id = o.id
```

Khi cấu hình sort keys, hãy dùng tên/alias được query provider hỗ trợ trong SQL được tạo ra. Một số provider yêu cầu sort key column xuất hiện trong select list và có thể cần tên cột không qualify theo alias bảng. Kiểm tra query thực tế để tránh SQL không hợp lệ hoặc continuation predicate tham chiếu sai tên.

Nếu query provider không xử lý được cấu trúc query đặc thù, cân nhắc tạo view, bảng staging hoặc custom `PagingQueryProvider` phù hợp thay vì ép builder tạo SQL không đúng.

## 22. Sort key và collation của String

Nếu sort key là String, thứ tự phụ thuộc collation/charset của database. Ví dụ chữ hoa/chữ thường, dấu tiếng Việt và ký tự Unicode có thể được sắp xếp khác nhau giữa môi trường.

Các yếu tố cần xác định:

- Collation của cột và database.
- So sánh có phân biệt hoa/thường hay không.
- Quy tắc dấu và chuẩn hóa Unicode.
- Có giá trị trùng sau khi collation chuẩn hóa hay không.
- Có khóa số/ID làm tie-breaker hay không.

Nếu thứ tự nghiệp vụ cần không phụ thuộc collation môi trường, có thể dùng cột normalized/sort key được chuẩn hóa trước và có index. Không tự chuẩn hóa trong `RowMapper` vì paging được quyết định ở SQL; giá trị dùng để sắp xếp phải được xác định nhất quán trong database query.

## 23. Checkpoint và restart của JdbcPagingItemReader

`JdbcPagingItemReader` triển khai `ItemStreamReader`. Khi `saveState(true)`, reader lưu state cần thiết trong `ExecutionContext`, bao gồm thông tin sort key của item cuối cùng đã được xác nhận theo lifecycle của chunk.

Khi restart, reader sử dụng state này cùng query provider để lấy dữ liệu tiếp theo theo thứ tự sort key. Vì vậy, sort key cần:

- Duy nhất trên kết quả truy vấn.
- Được select để reader có thể lưu giá trị.
- Ổn định giữa lần chạy đầu và restart.
- Có kiểu dữ liệu và semantics so sánh nhất quán trong database.
- Được khai báo với cùng thứ tự và ASC/DESC direction.

Tên reader cũng phải ổn định:

```java
.name("orderReader")
.saveState(true)
```

Không đổi tên reader, sort key, direction, query filter hoặc resource/JobParameters trong khi JobInstance cũ còn có thể restart. Những thay đổi đó có thể làm checkpoint cũ không còn tương thích với query mới.

## 24. Page boundary và chunk boundary

Page boundary là ranh giới của một lần truy vấn database. Chunk boundary là ranh giới commit của Spring Batch. Hai ranh giới có thể khác nhau.

Ví dụ page size 1.000, chunk size 250:

```text
Page 1: item 1-1000
  Chunk 1: 1-250     -> commit
  Chunk 2: 251-500   -> commit
  Chunk 3: 501-750   -> commit
  Chunk 4: 751-1000  -> commit

Page 2: item 1001-2000
  Chunk 5: 1001-1250 -> commit
  ...
```

Nếu page size 500 và chunk size 800, một chunk có thể cần item từ nhiều page. Điều đó không làm thay đổi semantics của transaction chunk.

Reader có thể giữ page đã fetch trong bộ nhớ trong khi chunk được xử lý. Vì vậy page size quá lớn vẫn có thể tạo memory pressure dù chunk nhỏ.

## 25. Lưu ý về transaction và isolation

`JdbcPagingItemReader` thường mở các truy vấn page trong quá trình step. Transaction và isolation level ảnh hưởng việc các page nhìn thấy thay đổi từ transaction khác.

Một số điểm cần xác định:

- Reader dùng cùng hay khác transaction manager với writer.
- Mỗi page query có nhìn thấy dữ liệu commit mới hay không.
- Có cần snapshot nhất quán cho toàn job không.
- Writer cập nhật chính các hàng đang được reader lọc/sort hay không.
- Locking có làm giảm throughput hoặc gây deadlock không.

Nếu reader lọc `status = 'READY'` và writer đổi status sang `DONE`, cần hiểu rõ tập kết quả của các page tiếp theo và cách restart. Nếu page query chỉ tiếp tục sau sort key, thay đổi status có thể làm row ra khỏi tập kết quả. Điều này có thể là chủ đích, nhưng cần được thiết kế.

Một chiến lược phổ biến là chọn trước danh sách khóa của batch vào staging table với batch ID, rồi reader paging theo batch ID và primary key. Nhờ vậy, tập dữ liệu cần xử lý ít bị ảnh hưởng bởi thay đổi nghiệp vụ bên ngoài.

## 26. Dùng query provider tùy chỉnh

`PagingQueryProvider` xác định các câu truy vấn cho page đầu và các page tiếp theo. Nếu database hoặc query đặc thù không được factory hỗ trợ, có thể triển khai provider tùy chỉnh theo contract của Spring Batch.

Trước khi tự viết provider, hãy cân nhắc:

- Dùng database-specific provider có sẵn.
- Tạo view đơn giản hóa query.
- Đưa dữ liệu vào staging table.
- Thay query phức tạp bằng một select trên khóa đã materialize.

Provider tùy chỉnh phải tạo đúng SQL cho:

- Truy vấn page đầu.
- Truy vấn các page tiếp theo dựa trên sort key cuối cùng.
- Sort direction ASC/DESC.
- Nhiều sort key với tie-breaker.
- Parameter binding và tên cột.
- Database syntax và giới hạn số row.

Lỗi trong predicate page tiếp theo có thể không xuất hiện ở page đầu. Hãy test ít nhất ba page, page có giá trị sort trùng, page cuối và restart giữa page.

## 27. Dùng partitioning với paging reader

Paging reader có thể được dùng trong worker step của partitioning, ví dụ mỗi worker xử lý một khoảng ID hoặc một tenant. Mỗi partition cần query scope riêng và `ExecutionContext` riêng.

Ví dụ:

```java
.whereClause("where id >= :minId and id <= :maxId")
.parameterValues(Map.of(
        "minId", minId,
        "maxId", maxId))
.sortKeys(Map.of("id", Order.ASCENDING))
```

Partitioner tạo các range không chồng lấn. Mỗi worker đọc page trong range của mình.

Điều cần bảo đảm:

- Các range bao phủ tập dữ liệu mong muốn và không chồng lấn ngoài ý muốn.
- Mỗi reader instance có state/name phù hợp với partition.
- Sort key duy nhất trong phạm vi truy vấn của worker.
- Không chia cùng một range cho hai worker nếu không có cơ chế claim/lock.
- Writer/output không bị xung đột giữa partition.

Nếu dùng cùng một bean reader mutable cho nhiều partition mà không có scope/prototype phù hợp, state của các worker có thể bị chia sẻ. Hãy tạo reader instance theo step scope/partition context theo cấu hình Spring Batch.

## 28. Kiểm thử sort key và page boundary

Test phải có dữ liệu cố tình trùng giá trị sort chính để chứng minh tie-breaker hoạt động.

Ví dụ fixture:

| id | created_at | amount |
|---:|---|---:|
| 10 | 09:00 | 10.00 |
| 11 | 09:00 | 11.00 |
| 12 | 09:00 | 12.00 |
| 13 | 09:01 | 13.00 |
| 14 | 09:01 | 14.00 |

Sort keys:

```java
Map<String, Order> sortKeys = new LinkedHashMap<>();
sortKeys.put("created_at", Order.ASCENDING);
sortKeys.put("id", Order.ASCENDING);
```

Đặt page size là 2 để nhóm `created_at` trùng bị cắt qua page boundary. Đọc toàn bộ và xác nhận thứ tự:

```text
10, 11 | 12, 13 | 14
```

Test này có thể phát hiện việc chỉ sort theo timestamp khiến page tiếp theo bỏ sót record cùng timestamp.

## 29. Kiểm thử không mất hoặc lặp item

Không chỉ kiểm tra số item tổng. Hãy kiểm tra business key:

```java
List<Long> ids = new ArrayList<>();
Order item;
while ((item = reader.read()) != null) {
    ids.add(item.id());
}

assertThat(ids).containsExactly(10L, 11L, 12L, 13L, 14L);
assertThat(ids).doesNotHaveDuplicates();
```

Với integration test, xác nhận cả:

- Không có ID nào bị thiếu.
- Không có ID nào xuất hiện hai lần.
- Thứ tự đúng theo toàn bộ sort key.
- Page cuối có ít hơn page size vẫn được đọc đầy đủ.
- Tập dữ liệu rỗng kết thúc đúng.
- Điều kiện `whereClause` được áp dụng trên mọi page.

## 30. Kiểm thử restart giữa các page

Một bài test restart có thể làm theo trình tự:

1. Tạo bảng fixture với nhiều page và nhiều hàng có cùng sort value.
2. Khởi chạy job với identifying parameters cố định.
3. Đọc và commit một số chunk qua ít nhất một page boundary.
4. Làm step thất bại có kiểm soát.
5. Kiểm tra `ExecutionContext` có state reader cần thiết.
6. Restart cùng JobInstance với query, sort keys, direction và parameters như cũ.
7. Xác nhận reader tiếp tục sau sort key đã commit.
8. So sánh output với tập ID kỳ vọng, bảo đảm không thiếu/lặp.

Nếu page size khác chunk size, hãy đặt lỗi ở vị trí thể hiện rõ cả page boundary và chunk boundary. Test chỉ thất bại trong page đầu có thể không phát hiện lỗi continuation query.

Không thay sort key hoặc resource/query filter giữa lần chạy đầu và restart. Nếu muốn thay cách sắp xếp, hãy tạo một JobInstance mới với quy tắc mới.

## 31. Kiểm thử khi dữ liệu thay đổi đồng thời

Nếu hệ thống có transaction khác insert/update/delete trong khi batch đang chạy, cần test theo isolation level và database production.

Một số tình huống cần mô phỏng:

- Insert một row có sort key lớn hơn checkpoint.
- Insert một row có sort key nhỏ hơn checkpoint.
- Delete row chưa đọc.
- Update sort key của row chưa đọc.
- Update filter column khiến row đi vào/ra tập kết quả.
- Restart sau khi một số thay đổi đã commit.

Kết quả mong đợi phải được định nghĩa trước: job xử lý snapshot lúc bắt đầu, mọi row thỏa điều kiện tại thời điểm từng page query, hay một batch manifest cố định. Không có một semantics đúng cho mọi nghiệp vụ.

## 32. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Thiếu row ở ranh giới page | Sort key không duy nhất hoặc continuation predicate không phân biệt hàng trùng. | Thêm primary key làm tie-breaker. |
| Row xuất hiện hai lần | Sort key mutable, thứ tự không ổn định hoặc dữ liệu thay đổi khi paging. | Dùng khóa bất biến và tập dữ liệu/snapshot cố định. |
| Restart đọc sai vị trí | Đổi reader name, sort key, direction, query filter hoặc input parameters. | Giữ cấu hình và identifying parameters ổn định cho JobInstance. |
| Page query chậm dần | Offset lớn, index không phù hợp hoặc query plan kém. | Kiểm tra provider, index và execution plan; dùng keyset strategy phù hợp. |
| SQL lỗi ở page tiếp theo | Sort key không có trong select list hoặc provider không hỗ trợ query shape. | Kiểm tra SQL được tạo cho từng page và tên cột/alias. |
| Thứ tự không giống giữa môi trường | Collation, null ordering hoặc map key ordering khác nhau. | Xác định collation/null rule và dùng ordered sort key map. |
| Sort theo timestamp nhưng thứ tự trùng không ổn định | Timestamp không duy nhất. | Thêm unique ID làm tie-breaker. |
| Tốn bộ nhớ dù paging | Page/chunk quá lớn hoặc RowMapper tạo object nặng. | Giảm page/chunk, chỉ select field cần thiết và đo heap. |
| Thiếu dữ liệu mới insert | Row có sort key nhỏ hơn checkpoint hoặc tập dữ liệu đã được chốt. | Xác định snapshot/window semantics và batch manifest. |
| Partition xử lý trùng | Range chồng lấn hoặc worker chia sẻ reader/state. | Tạo range không chồng lấn và reader instance riêng. |
| Page đầu đúng nhưng page sau sai | Predicate continuation hoặc mixed ASC/DESC được tạo sai. | Test nhiều page và sort values trùng trên database thật. |

## 33. Quy trình thiết kế paging có sort ổn định

Khi triển khai `JdbcPagingItemReader`, hãy đi theo các bước:

1. **Xác định item boundary:** một row, một group hay một entity tổng hợp?
2. **Xác định tập dữ liệu:** chốt `whereClause`, batch window và identifying JobParameters.
3. **Chọn thứ tự nghiệp vụ:** ngày, sequence, priority hoặc primary key.
4. **Thêm tie-breaker duy nhất:** thường là primary key hoặc khóa tổng hợp duy nhất.
5. **Chọn sort direction:** khai báo ASC/DESC rõ ràng cho từng key.
6. **Đưa sort key vào select list:** bảo đảm reader có giá trị để tiếp tục paging/restart.
7. **Cấu hình provider:** dùng provider tương thích database và xác nhận query page đầu/page sau.
8. **Thiết kế index:** đối chiếu predicate, sort order và execution plan.
9. **Chọn page/chunk size:** benchmark theo row width, heap và transaction duration.
10. **Giữ state ổn định:** reader name, sort keys, direction, parameters và input set không đổi khi restart.
11. **Xác định concurrency semantics:** snapshot, dữ liệu động hay batch manifest.
12. **Kiểm thử page boundary:** cố tình tạo nhiều row có cùng sort value chính.
13. **Kiểm thử restart:** thất bại qua page/chunk boundary rồi xác nhận không thiếu/lặp.
14. **Đo production behavior:** query time, throughput, heap, GC và database load.

## 34. Những điểm cần ghi nhớ

- `JdbcPagingItemReader` đọc database theo page, trả item cho chunk processing và hỗ trợ checkpoint/restart.
- `PagingQueryProvider` tạo câu SQL paging phù hợp với database và sort keys.
- `pageSize`, `chunkSize` và `fetchSize` có ý nghĩa khác nhau: page query, transaction chunk và JDBC fetch hint.
- Sort phải xác định duy nhất thứ tự của từng hàng; sort theo timestamp hoặc status đơn lẻ thường chưa đủ.
- Thêm primary key làm tie-breaker, ví dụ `ORDER BY created_at, id`.
- Với nhiều sort key, dùng `LinkedHashMap` để giữ thứ tự ưu tiên; khai báo ASC/DESC rõ ràng.
- Sort key phải có trong select list, ổn định, không null nếu có thể và không thay đổi trong khi job xử lý.
- Query join cần sort key duy nhất trên kết quả thực tế, không chỉ trên bảng gốc.
- Index nên phù hợp với filter và sort; xác nhận bằng execution plan trên database thật.
- Paging không tự tạo snapshot nhất quán; insert/update/delete giữa các page có thể thay đổi tập dữ liệu.
- Giữ reader name, sort keys, direction, query filter và JobParameters ổn định cho restart.
- Kiểm thử ít nhất nhiều page, sort value trùng, page cuối, restart và thay đổi dữ liệu đồng thời theo semantics đã chọn.
- Partitioning cần reader/state riêng và range không chồng lấn nếu xử lý song song.

Đọc theo page giúp Spring Batch xử lý tập dữ liệu JDBC lớn mà không phải materialize toàn bộ kết quả trong bộ nhớ. Tuy nhiên, paging chỉ đáng tin cậy khi thứ tự được xác định duy nhất và giữ ổn định qua mọi page cũng như lần restart. Hãy chọn sort key bất biến có tie-breaker duy nhất, kiểm tra query provider và index trên database thực tế, chốt tập dữ liệu cần xử lý, rồi kiểm thử kỹ ranh giới page/chunk và restart để tránh mất hoặc lặp bản ghi.
