# Chiếu cột, lọc sớm và giảm dữ liệu phải quét

Truy vấn phân tích thường đọc hàng triệu hoặc hàng tỷ bản ghi để tạo báo cáo, tổng hợp và phân tích xu hướng. Chi phí lớn không chỉ đến từ phép tính cuối cùng mà còn từ lượng dữ liệu phải đọc, giải nén, chuyển qua mạng và đưa vào các toán tử xử lý. Một truy vấn chỉ cần ba cột nhưng đọc toàn bộ hàng rộng, hoặc chỉ cần dữ liệu một tháng nhưng quét nhiều năm, sẽ lãng phí I/O, CPU và bộ nhớ. Hai kỹ thuật nền tảng để giảm công việc là **chiếu đúng các cột cần thiết (projection pruning)** và **đẩy điều kiện lọc xuống gần nơi dữ liệu được đọc nhất có thể (predicate pushdown)**.

Bài học thuộc chương **Tải phân tích** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Trong tải phân tích, chiếu cột và lọc sớm giúp giảm số byte phải đọc và số hàng đi qua các toán tử; cần kiểm chứng bằng execution plan, số page/byte đọc, partition pruning, thời gian scan và kết quả nghiệp vụ.

## 1. Hai hướng giảm dữ liệu phải xử lý

Một truy vấn có thể giảm công việc theo hai chiều độc lập:

- **Giảm chiều rộng:** chỉ đọc những cột cần dùng. Đây là projection pruning/column pruning.
- **Giảm số hàng:** loại bỏ hàng không thỏa điều kiện càng sớm càng tốt. Đây là predicate pushdown/filter pushdown.

Ví dụ bảng `sales_fact` có 200 triệu hàng và 35 cột. Báo cáo chỉ cần `sale_date`, `region_id`, `net_amount`, trong đó chỉ lấy quý 4 năm 2026 và các giao dịch đã hoàn tất.

Truy vấn chưa tối ưu về mặt diễn đạt:

```sql
SELECT *
FROM sales_fact;
```

Ứng dụng tải toàn bộ hàng về rồi mới lọc có thể truyền một lượng dữ liệu rất lớn qua database connection, chiếm bộ nhớ JVM và làm tăng network I/O.

Truy vấn thể hiện rõ dữ liệu cần dùng:

```sql
SELECT sale_date, region_id, net_amount
FROM sales_fact
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2027-01-01'
  AND status = 'COMPLETED';
```

Bộ tối ưu có thể chỉ đọc các cột cần thiết và loại bỏ vùng dữ liệu ngoài quý 4 nếu storage layout, partitioning, index hoặc metadata cho phép. Kết quả vẫn phải đúng theo predicate và kiểu dữ liệu của cột.

## 2. Projection pruning: chỉ đọc cột thực sự cần

Projection là tập cột hoặc biểu thức mà truy vấn yêu cầu trả về hay sử dụng trong các toán tử. Projection pruning loại bỏ việc đọc các cột không cần thiết ở những tầng lưu trữ và xử lý có thể hỗ trợ.

### 2.1. Vì sao SELECT * tốn kém?

`SELECT *` yêu cầu tất cả cột của đối tượng được chọn. Nếu bảng có cột JSON lớn, văn bản dài, blob hoặc nhiều cột ít dùng, DBMS có thể phải đọc và giải mã thêm dữ liệu. Ở hệ thống lưu trữ dạng cột, engine có thể đọc nhiều column chunk hơn cần thiết. Ở hệ thống dạng hàng, các cột thường nằm cùng page nên lợi ích I/O của việc bỏ cột có thể nhỏ hơn, nhưng vẫn giảm dữ liệu truyền qua mạng, chuyển đổi kiểu và cấp phát object ở ứng dụng.

Ví dụ:

```sql
-- Không cần thiết nếu báo cáo chỉ dùng ba cột
SELECT *
FROM customer_events
WHERE event_date >= DATE '2026-11-01';

-- Projection tường minh
SELECT customer_id, event_type, event_date
FROM customer_events
WHERE event_date >= DATE '2026-11-01';
```

Projection tường minh còn giúp hợp đồng dữ liệu ổn định hơn khi schema thêm cột mới. Nó giảm nguy cơ vô tình tải trường nhạy cảm hoặc payload lớn mà ứng dụng không cần.

### 2.2. Cột cần cho truy vấn không chỉ là cột SELECT

Một cột có thể không xuất hiện trong output nhưng vẫn cần cho:

- `WHERE`, `JOIN`, `GROUP BY`, `HAVING` hoặc `ORDER BY`.
- Biểu thức tính toán và điều kiện trong window function.
- Khóa phân vùng, điều kiện bảo mật hoặc row-level filtering.
- Kiểm tra constraint hoặc logic của view.

Ví dụ:

```sql
SELECT region_id, SUM(net_amount) AS revenue
FROM sales_fact
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date < DATE '2027-01-01'
  AND status = 'COMPLETED'
GROUP BY region_id;
```

Truy vấn cần `sale_date` và `status` để lọc, `region_id` để nhóm và `net_amount` để tính tổng, dù output cuối chỉ có `region_id` và `revenue`. Optimizer có thể loại bỏ các cột khác khỏi scan nếu không cần cho bất kỳ bước nào.

### 2.3. Projection pruning trong columnar storage

Trong columnar storage, dữ liệu của từng cột hoặc nhóm cột được lưu riêng hoặc theo column chunk. Khi truy vấn chỉ cần ba cột, engine có thể đọc ba cột đó thay vì toàn bộ schema. Đây là một lợi thế quan trọng của định dạng cột trong workload phân tích.

Ví dụ một file Parquet có 40 cột nhưng báo cáo chỉ cần 4 cột. Reader có thể bỏ qua column chunks còn lại, giảm bytes đọc từ storage và lượng dữ liệu giải nén. Mức tiết kiệm phụ thuộc compression, row groups, metadata và cách truy vấn được thực thi.

Trong row store, các cột của một hàng thường được lưu gần nhau. Projection pruning vẫn giảm output và có thể hỗ trợ covering index, nhưng không phải lúc nào cũng giảm số page table phải đọc theo tỷ lệ số cột bị bỏ.

## 3. Predicate pushdown: đưa điều kiện lọc xuống gần nguồn dữ liệu

Predicate là biểu thức điều kiện dùng để xác định hàng cần giữ, thường nằm trong `WHERE` hoặc điều kiện join. Predicate pushdown là việc chuyển hoặc thực hiện điều kiện lọc ở tầng thấp hơn trong kế hoạch, trước khi dữ liệu được chuyển lên các toán tử phía trên.

Ví dụ một truy vấn đọc file dữ liệu:

```sql
SELECT customer_id, amount
FROM external_sales
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2026-11-01'
  AND country_code = 'VN';
```

Nếu engine hỗ trợ pushdown đến connector hoặc file reader, điều kiện ngày và quốc gia có thể được áp dụng ngay tại nguồn đọc. Khi đó ít hàng phải chuyển từ storage/remote source lên engine để tiếp tục xử lý.

### 3.1. Lợi ích của lọc sớm

- Ít page, block, row group hoặc file phải đọc hơn nếu metadata cho phép loại bỏ.
- Ít hàng đi qua join, sort, aggregate và window operators.
- Giảm memory grant và kích thước hash table/sort buffer.
- Giảm dữ liệu truyền giữa node, worker hoặc qua mạng.
- Giảm CPU giải mã, chuyển đổi và đánh giá biểu thức cho hàng bị loại.
- Giảm áp lực spill ra storage tạm.

Lọc sớm không phải lúc nào cũng giảm số byte đọc từ thiết bị. Nếu điều kiện không khớp index, partition bounds hoặc metadata, engine có thể vẫn phải đọc dữ liệu rồi mới lọc. Khi đó, predicate vẫn giảm hàng đi vào toán tử phía trên nhưng không giảm scan I/O ở nguồn.

### 3.2. Logical filter và physical pushdown

Trong SQL, `WHERE` mô tả điều kiện logic. Optimizer quyết định điều kiện được thực thi ở đâu trong physical plan. Việc viết điều kiện ở đầu câu lệnh không bảo đảm engine sẽ lọc ngay tại storage. Cần kiểm tra execution plan hoặc connector/file scan details để biết predicate đã được push xuống hay còn là filter ở tầng trên.

Ví dụ một kế hoạch có thể gồm:

```text
Scan sales_fact
  Filter: status = 'COMPLETED'
  -> Hash Aggregate
```

Nếu filter nằm ngay trong scan operator, engine có thể áp dụng điều kiện trong lúc đọc. Nếu kế hoạch có scan tất cả hàng rồi mới có filter operator riêng phía trên, dữ liệu có thể đã được đọc và giải mã trước khi bị loại. Một số engine vẫn hiển thị filter trong scan dù chỉ loại hàng sau khi đọc page; phải xem thêm scan bytes, rows read và storage metrics.

## 4. Partition pruning: loại bỏ partition trước khi scan

Partition pruning là trường hợp quan trọng của lọc sớm ở cấp phân vùng. Nếu bảng được partition theo `sale_date`, predicate thời gian có thể giúp engine loại bỏ partition ngoài khoảng cần đọc.

Ví dụ:

```sql
SELECT region_id, SUM(net_amount)
FROM sales_fact
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2027-01-01'
GROUP BY region_id;
```

Nếu bảng có partition theo tháng, truy vấn có thể chỉ cần các partition tháng 10, 11 và 12 năm 2026. Các partition khác không cần mở hoặc scan tùy cơ chế hệ quản trị.

### 4.1. Dùng khoảng nửa mở

Với cột timestamp, điều kiện nửa mở thường rõ ràng và tránh sai lệch ở phần cuối khoảng:

```sql
WHERE event_time >= TIMESTAMP '2026-10-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-11-01 00:00:00'
```

Không nên dùng `BETWEEN` với mốc cuối là `2026-10-31 23:59:59` nếu cột có độ chính xác phần giây nhỏ hơn một giây; các giá trị ở phần lẻ cuối ngày có thể bị bỏ sót. Nếu nghiệp vụ dùng timezone, phải xác định khoảng thời gian theo timezone nghiệp vụ rồi truyền hai mốc tương ứng.

### 4.2. Static và runtime pruning

Static pruning có thể xảy ra khi optimizer biết giá trị điều kiện trong lúc lập kế hoạch. Runtime pruning xảy ra khi giá trị chỉ được biết lúc thực thi, ví dụ tham số hoặc giá trị từ một toán tử khác. Khả năng và cách hiển thị phụ thuộc hệ quản trị.

Prepared statement không nhất thiết làm pruning thất bại; một số engine có thể prune khi khởi tạo hoặc trong quá trình chạy. Hãy kiểm tra actual plan với các giá trị tham số đại diện.

### 4.3. Không có predicate trên partition key

Nếu truy vấn chỉ lọc `status = 'COMPLETED'` mà không có điều kiện trên `sale_date`, engine có thể phải xem xét mọi partition. Index trên `status` hoặc metadata khác có thể hỗ trợ, nhưng partition pruning theo ngày không thể được suy ra nếu điều kiện không giới hạn ngày.

## 5. Row group, zone map và metadata pruning

Trong các hệ thống phân tích lưu trữ dữ liệu theo file hoặc block, engine có thể dùng metadata để bỏ qua vùng dữ liệu mà chắc chắn không chứa giá trị cần tìm.

### 5.1. Min/max statistics và zone maps

Một row group hoặc block có thể lưu giá trị nhỏ nhất/lớn nhất của một cột. Với predicate:

```sql
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2026-11-01'
```

nếu metadata của một row group cho biết toàn bộ ngày trong nhóm nằm ở tháng 8, engine có thể bỏ qua row group đó mà không đọc toàn bộ nội dung. Kỹ thuật này thường được gọi là min/max pruning hoặc zone-map pruning tùy hệ thống.

Hiệu quả phụ thuộc thứ tự dữ liệu. Nếu file được sắp xếp hoặc clustering theo `sale_date`, min/max của từng row group có thể hẹp và hữu ích. Nếu dữ liệu trộn ngẫu nhiên mọi ngày trong mỗi row group, khoảng min/max có thể bao phủ gần như toàn bộ thời gian và ít row group bị loại.

### 5.2. Bloom filter

Bloom filter là cấu trúc xác suất giúp kiểm tra nhanh một giá trị có thể tồn tại trong một vùng dữ liệu hay chắc chắn không tồn tại. Bloom filter có thể có false positive (báo có thể tồn tại dù thực tế không có), nhưng không được có false negative nếu triển khai đúng. Khi filter cho biết giá trị chắc chắn không có trong row group/partition, engine có thể bỏ qua vùng đó.

Bloom filter thường hữu ích cho điều kiện equality hoặc join key có tính chọn lọc. Nó không thay thế index B-tree và không trả về vị trí hàng cụ thể. Mức hỗ trợ và cách tạo bloom filter phụ thuộc định dạng file, storage engine và query engine.

### 5.3. Dictionary filtering

Một số columnar formats mã hóa giá trị bằng dictionary trong row group. Nếu dictionary không chứa giá trị predicate, engine có thể bỏ qua phần dữ liệu tương ứng. Ví dụ, nếu một row group chỉ chứa `country_code` là `JP` và `SG`, predicate `country_code = 'VN'` có thể loại cả nhóm dựa trên dictionary metadata.

Dictionary encoding cũng giúp nén dữ liệu có cardinality thấp, nhưng không bảo đảm pruning nếu dictionary của từng row group chứa nhiều giá trị khác nhau.

## 6. Columnar storage và row-oriented storage

Lựa chọn storage layout ảnh hưởng trực tiếp đến hiệu quả chiếu cột và lọc sớm.

| Đặc điểm | Row-oriented | Column-oriented |
|---|---|---|
| Cách lưu | Các cột của một hàng được lưu gần nhau | Giá trị của cùng cột được lưu theo nhóm/column chunk |
| Phù hợp | OLTP, đọc/ghi một số hàng với nhiều cột | Scan nhiều hàng nhưng chỉ cần một số cột |
| Projection | Bỏ cột giảm dữ liệu output; scan page có thể vẫn đọc nhiều cột vật lý | Có thể chỉ đọc column chunks cần thiết |
| Filter | Index/partition có thể giảm số hàng phải đọc | Predicate pushdown, min/max, dictionary và zone map có thể bỏ row group |
| Compression | Tùy engine và page/row format | Thường khai thác locality cùng cột để nén tốt |
| Chi phí cập nhật | Thường thuận lợi cho cập nhật từng hàng | Có thể cần xử lý phức tạp hơn cho cập nhật nhỏ; tùy kiến trúc |

Một hệ thống có thể dùng row store cho transaction và columnar replica/data warehouse cho phân tích. Không phải mọi bảng phân tích cần chuyển sang columnar; cần xem tỷ lệ scan, projection, cập nhật và freshness.

### 6.1. Ví dụ Parquet

Parquet tổ chức file theo row group; mỗi row group có column chunks và metadata. Reader có thể:

1. Đọc footer/metadata để biết schema và thống kê.
2. Chọn các cột được truy vấn yêu cầu.
3. Dùng partition metadata, min/max hoặc bloom filter nếu có để bỏ file/row group.
4. Đọc và giải nén các column chunks còn lại.
5. Áp dụng predicate ở reader hoặc query engine.

Mức pruning thực tế phụ thuộc writer đã ghi statistics/bloom filters chưa, dữ liệu có được sắp xếp/clustering không, connector có hỗ trợ pushdown và predicate có tương thích với metadata không.

## 7. Viết predicate để engine có thể tận dụng access path

Predicate dễ được tối ưu thường so sánh trực tiếp cột với hằng số hoặc tham số có kiểu phù hợp. Cách viết biểu thức có thể ảnh hưởng khả năng dùng index, partition bounds hoặc pushdown.

### 7.1. Tránh bọc cột bằng hàm khi không cần

Ví dụ:

```sql
-- Có thể làm khó index/partition pruning trên created_at
WHERE DATE(created_at) = DATE '2026-10-15'
```

Viết thành khoảng:

```sql
WHERE created_at >= TIMESTAMP '2026-10-15 00:00:00'
  AND created_at <  TIMESTAMP '2026-10-16 00:00:00'
```

Biểu thức thứ hai thường dễ tận dụng B-tree range scan và range partition bounds hơn. Tuy nhiên, optimizer có thể hỗ trợ functional index hoặc expression pruning trong một số trường hợp; hãy xem execution plan thay vì áp dụng quy tắc máy móc.

### 7.2. Tránh implicit conversion trên cột

Nếu cột là `INTEGER` nhưng ứng dụng bind chuỗi, DBMS có thể phải chuyển kiểu. Tùy quy tắc type precedence, phép chuyển đổi có thể được áp lên cột và làm giảm khả năng seek/pushdown.

```sql
-- Bind :customer_id bằng kiểu số phù hợp với cột
WHERE customer_id = :customer_id
```

Hãy bind tham số đúng kiểu của cột, kiểm tra execution plan và cảnh báo conversion. Không chỉ đổi kiểu bằng cast tùy tiện vì cast sai có thể thay đổi semantics hoặc làm mất khả năng dùng index.

### 7.3. LIKE và pattern matching

Điều kiện `LIKE 'ABC%'` có thể dùng index hoặc prefix pruning trong một số hệ quản trị và collation. Điều kiện `LIKE '%ABC'` thường không thể dùng B-tree theo cách prefix thông thường vì không biết điểm bắt đầu. Full-text index, trigram index hoặc search index có thể phù hợp hơn tùy yêu cầu.

### 7.4. OR và biểu thức phức tạp

Điều kiện `OR` có thể làm optimizer chọn scan hoặc nhiều access path. Một số engine hỗ trợ index union/bitmap OR; một số có thể tận dụng partition pruning theo từng nhánh. Không nên tự tách OR thành `UNION ALL` nếu hai nhánh có thể giao nhau, vì có thể tạo hàng trùng. Nếu tách, phải giữ đúng bag semantics hoặc loại trùng theo đúng khóa nghiệp vụ.

### 7.5. Sargability

Predicate có tính sargable (search-argument-able) khi cấu trúc điều kiện cho phép engine dùng access path như index seek/range scan hoặc partition bounds hiệu quả. Sargability phụ thuộc DBMS, index, kiểu dữ liệu và biểu thức. Một predicate không sargable vẫn có thể được push xuống scan để lọc trong storage reader; hai khái niệm liên quan nhưng không đồng nhất.

## 8. Selectivity và thứ tự lọc

Selectivity mô tả mức độ một predicate giữ lại bao nhiêu phần dữ liệu. Nếu predicate giữ 1% hàng, nó có tính chọn lọc cao; nếu giữ 90%, tính chọn lọc thấp.

Ví dụ bảng có 100 triệu hàng:

| Predicate | Tỷ lệ giữ lại giả định | Số hàng còn lại |
|---|---:|---:|
| `sale_date` trong một ngày | 0,3% | 300.000 |
| `region_id = 7` | 8% | 8.000.000 |
| `status = 'COMPLETED'` | 75% | 75.000.000 |

Nếu các điều kiện độc lập, kết hợp có thể giữ tỷ lệ nhỏ hơn nhiều; trong thực tế các cột thường tương quan. Optimizer dùng statistics/histogram để ước lượng cardinality và chọn access path.

### 8.1. Không cần viết WHERE theo thứ tự chọn lọc để ép thực thi

SQL là ngôn ngữ khai báo. Việc đặt predicate chọn lọc cao lên trước trong văn bản `WHERE` không bảo đảm DBMS đánh giá nó trước. Optimizer có thể sắp xếp lại điều kiện, push predicate xuống scan hoặc dùng index/partition theo chi phí.

Ví dụ hai cách viết dưới đây thường có cùng semantics và optimizer có thể chuẩn hóa:

```sql
WHERE status = 'COMPLETED'
  AND region_id = 7
```

```sql
WHERE region_id = 7
  AND status = 'COMPLETED'
```

Hãy cải thiện statistics, index và predicate shape nếu estimate sai; không dựa vào thứ tự văn bản để điều khiển execution order.

### 8.2. Correlation giữa các predicate

Nếu `status` và `sale_date` có tương quan, nhân selectivity độc lập có thể ước lượng sai. Ví dụ đơn hàng mới thường ở trạng thái `PENDING`, trong khi dữ liệu cũ chủ yếu `COMPLETED`. Thống kê đa cột, extended statistics hoặc histogram phù hợp có thể giúp optimizer ước lượng tốt hơn tùy hệ quản trị.

## 9. Filter pushdown qua JOIN

Đẩy filter xuống trước join có thể giảm kích thước đầu vào và chi phí join. Tuy nhiên, việc biến đổi phải giữ nguyên semantics, đặc biệt với outer join, NULL và bản ghi trùng.

### 9.1. Inner join

Ví dụ:

```sql
SELECT c.region_id, SUM(o.total_amount)
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region_id = 7
  AND o.created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-11-01 00:00:00'
GROUP BY c.region_id;
```

Optimizer có thể lọc khách hàng theo region và đơn hàng theo thời gian trước khi join. Điều này giảm số hàng đầu vào nếu predicate có selectivity tốt và access path hỗ trợ.

### 9.2. Outer join

Với `LEFT JOIN`, chuyển điều kiện từ `ON` sang `WHERE` có thể loại các hàng không khớp và làm thay đổi kết quả.

Giữ mọi khách hàng, chỉ nối đơn hàng tháng 10:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.created_at >= TIMESTAMP '2026-10-01 00:00:00'
 AND o.created_at <  TIMESTAMP '2026-11-01 00:00:00';
```

Nếu đưa điều kiện thời gian của `o` xuống `WHERE`, các khách hàng không có đơn hàng sẽ có `o.created_at IS NULL` và bị loại. Đây là thay đổi semantics, không phải phép tối ưu tương đương.

### 9.3. Dynamic filtering trong query engine phân tán

Một số query engine phân tán có thể tạo filter từ tập khóa của một phía join rồi truyền filter đó xuống scan phía còn lại. Kỹ thuật này thường được gọi là dynamic filtering hoặc runtime filtering. Ví dụ dimension table lọc còn một số customer ID; engine có thể dùng tập ID đó để giảm lượng fact rows cần đọc.

Hiệu quả phụ thuộc kích thước tập khóa, thời điểm filter sẵn sàng, connector và khả năng áp dụng filter tại nguồn. Nếu tập khóa quá lớn hoặc đến muộn, filter có thể không tiết kiệm nhiều. Cần kiểm tra plan và scan metrics.

## 10. Filter pushdown qua GROUP BY, HAVING và window function

Điều kiện lọc trước và sau aggregate không thể thay thế tùy ý.

- `WHERE` lọc hàng đầu vào trước aggregate.
- `HAVING` lọc nhóm sau khi aggregate.
- Điều kiện trên kết quả window function thường cần tầng truy vấn ngoài hoặc `QUALIFY` nếu hệ quản trị hỗ trợ.

Ví dụ:

```sql
SELECT region_id, SUM(net_amount) AS revenue
FROM sales_fact
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2027-01-01'
GROUP BY region_id
HAVING SUM(net_amount) > 1000000;
```

Điều kiện thời gian có thể lọc hàng trước aggregate. Điều kiện tổng doanh thu phải được đánh giá sau khi tính tổng theo nhóm. Không thể chuyển `HAVING SUM(net_amount) > 1000000` thành một predicate trên từng hàng mà vẫn giữ kết quả.

Với window function, ví dụ lấy giao dịch mới nhất mỗi khách hàng:

```sql
SELECT customer_id, order_id, created_at
FROM (
    SELECT
        customer_id,
        order_id,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM orders
    WHERE created_at >= TIMESTAMP '2026-10-01 00:00:00'
      AND created_at <  TIMESTAMP '2026-11-01 00:00:00'
) AS ranked
WHERE rn = 1;
```

Predicate thời gian có thể được đẩy xuống trước window vì nó định nghĩa tập hàng đầu vào theo yêu cầu. Điều kiện `rn = 1` phải được áp dụng sau khi tính ranking. Đẩy hoặc bỏ điều kiện sai vị trí có thể làm thay đổi hàng được xếp hạng.

## 11. CTE, subquery và optimizer barriers

Viết truy vấn thành CTE hoặc subquery không tự động làm nó chạy riêng rồi lưu toàn bộ kết quả. Nhiều optimizer có thể inline/merge CTE để push predicate từ truy vấn ngoài vào bên trong. Một số hệ quản trị hoặc cú pháp materialization có thể tạo ranh giới tối ưu hóa khiến pushdown bị hạn chế.

Ví dụ:

```sql
WITH recent_sales AS (
    SELECT sale_date, region_id, net_amount
    FROM sales_fact
)
SELECT region_id, SUM(net_amount)
FROM recent_sales
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2026-11-01'
GROUP BY region_id;
```

Optimizer có thể inline CTE và áp dụng điều kiện thời gian ở scan. Nhưng nếu CTE được materialize hoặc là optimization fence trong engine cụ thể, nó có thể xử lý nhiều hàng trước khi filter. Hãy xem execution plan, không kết luận chỉ từ việc có hay không có CTE.

Materialization có thể hữu ích nếu kết quả trung gian được dùng nhiều lần hoặc cần tránh tính toán lặp. Nhưng materialize một tập dữ liệu lớn trước khi lọc có thể tăng memory/temp I/O. Chọn theo số lần dùng, kích thước trung gian và plan thực tế.

## 12. Giới hạn của predicate pushdown

Không phải mọi biểu thức đều có thể push xuống storage hoặc remote source.

Các nguyên nhân phổ biến:

- Hàm không được connector hỗ trợ hoặc không tương đương giữa hai engine.
- Ép kiểu, collation hoặc timezone có semantics khác nhau.
- Hàm không xác định hoặc phụ thuộc session/environment.
- Điều kiện phụ thuộc kết quả aggregate/window ở tầng cao hơn.
- Outer join hoặc NULL semantics khiến chuyển vị trí predicate thay đổi kết quả.
- UDF cần chạy trong engine chính, không thể thực thi tại nguồn.
- Remote source không hỗ trợ toán tử, kiểu dữ liệu hoặc predicate tương ứng.
- Chính sách bảo mật/row-level security yêu cầu áp dụng điều kiện ở tầng có thẩm quyền.

Nếu connector chỉ push được một phần predicate, engine có thể áp dụng phần còn lại ở phía trên. Execution plan thường cho biết pushed filters và residual filters; tên hiển thị tùy sản phẩm.

### 12.1. Pushed predicate và residual predicate

Pushed predicate được chuyển xuống tầng scan/source để loại dữ liệu sớm. Residual predicate vẫn phải được đánh giá ở tầng engine sau khi đọc dữ liệu. Một truy vấn có thể push được điều kiện ngày nhưng phải lọc `LOWER(email)` ở tầng trên vì connector không hỗ trợ biểu thức đó.

Hãy xem cả hai nhóm điều kiện. Một filter hiển thị gần scan không đồng nghĩa toàn bộ predicate đã được thực thi ở storage.

### 12.2. NULL và ba giá trị logic

Predicate pushdown phải giữ semantics của SQL với `TRUE`, `FALSE` và `UNKNOWN`. Khi chuyển điều kiện qua outer join, `NOT IN`, `CASE` hoặc phép so sánh nullable, kết quả có thể thay đổi nếu engine áp dụng logic khác hoặc connector không hỗ trợ chính xác. Cần kiểm thử dữ liệu NULL và đối chiếu kết quả trước/sau.

## 13. Giảm dữ liệu phải quét ở tầng lưu trữ

Chiếu cột và lọc sớm có thể phối hợp với partitioning, index, clustering và file layout.

### 13.1. Index trong row store

Trong row-oriented DBMS, index có thể đưa engine trực tiếp đến các hàng thỏa predicate mà không scan toàn bảng. Covering index có thể chứa cả cột lọc và cột output để giảm lookup về bảng chính.

Ví dụ truy vấn:

```sql
SELECT sale_date, net_amount
FROM sales_fact
WHERE region_id = :region_id
  AND sale_date >= :from_date
  AND sale_date < :to_date;
```

Index ghép `(region_id, sale_date)` có thể hỗ trợ equality trên `region_id` rồi range trên `sale_date`; include/covering columns có thể giúp tránh đọc thêm cột nếu DBMS hỗ trợ. Cấu trúc index cần cân bằng với chi phí ghi, dung lượng và các truy vấn khác.

### 13.2. Clustering và data ordering

Nếu dữ liệu được sắp xếp hoặc clustering theo cột lọc thường dùng, các page hoặc row group có thể chứa khoảng giá trị hẹp hơn. Điều này cải thiện min/max pruning và locality. Dữ liệu được ghi liên tục theo thời gian thường tự nhiên có locality theo ngày, nhưng late-arriving data hoặc merge job có thể làm giảm hiệu quả.

### 13.3. Partitioning và file pruning

Partitioning theo thời gian hoặc tenant có thể loại toàn bộ partition. Trong data lake, partition directory/file layout cũng có thể giúp connector bỏ file. Tuy nhiên, partition quá nhỏ tạo nhiều file nhỏ, metadata và scheduling overhead; partition quá lớn làm scan đọc nhiều dữ liệu hơn. Chọn granularity theo workload và đo số file/partition thực sự được mở.

### 13.4. File compaction và small files

Hàng nghìn file nhỏ có thể làm tăng thời gian liệt kê metadata, mở file, lập task và quản lý object storage request. Compaction gộp file có thể giảm overhead, nhưng file quá lớn hoặc row group không phù hợp có thể giảm song song hoặc pruning. Hãy đo file count, average file size, row-group size, bytes scanned và parallelism.

## 14. Ví dụ tổng hợp: báo cáo doanh thu quý

Giả sử fact table có 1,2 tỷ hàng, 48 cột và dữ liệu giữ 5 năm. Báo cáo cần doanh thu theo khu vực cho quý 4 năm 2026, chỉ tính đơn hàng hoàn tất.

Truy vấn:

```sql
SELECT region_id, SUM(net_amount) AS revenue
FROM sales_fact
WHERE sale_date >= DATE '2026-10-01'
  AND sale_date <  DATE '2027-01-01'
  AND order_status = 'COMPLETED'
GROUP BY region_id
ORDER BY revenue DESC;
```

Một thiết kế storage có thể gồm:

- Partition theo tháng dựa trên `sale_date`.
- Columnar file format cho workload scan phân tích.
- Row groups có min/max statistics trên `sale_date`.
- Data clustering theo ngày hoặc khu vực nếu workload chứng minh có lợi.
- Chỉ giữ các cột `sale_date`, `order_status`, `region_id`, `net_amount` trong scan.
- Predicate thời gian và trạng thái được push xuống reader khi connector hỗ trợ.

Giả sử tổng dữ liệu lưu trữ là 8 TB, quý cần phân tích tương ứng 400 GB dữ liệu thô theo partition. Projection chỉ đọc 4 trong 48 cột, nhưng lượng byte không nhất thiết giảm đúng còn 1/12 vì các cột có kích thước, compression và encoding khác nhau. Row-group pruning có thể tiếp tục bỏ một phần dữ liệu theo min/max; predicate trạng thái có thể lọc trong reader nhưng không chắc loại bỏ row group nếu metadata không đủ chọn lọc.

Không nên tính trước tỷ lệ giảm I/O bằng số cột đơn thuần. Hãy đo bytes scanned, compressed bytes, rows read, rows output, partitions/files skipped, CPU decode và thời gian aggregate.

## 15. Đọc execution plan để xác nhận pruning và pushdown

Khi tối ưu tải phân tích, cần kiểm tra ít nhất các thông tin sau:

| Thành phần | Điều cần xem |
|---|---|
| Scan operator | Table/file/partition scan nào được dùng? |
| Projection | Các cột nào thực sự được đọc? Có `SELECT *` hoặc cột thừa không? |
| Pushed filters | Predicate nào được áp dụng tại storage/connector? |
| Residual filters | Điều kiện nào còn phải lọc ở engine phía trên? |
| Partition pruning | Tổng partition, partition được giữ lại và partition bị bỏ |
| Row-group/file pruning | Số row group/file bị skip và lý do nếu có |
| Rows read/output | Số hàng đọc từ nguồn so với số hàng sau filter |
| Bytes read/scanned | Lượng dữ liệu thực sự đọc, không chỉ kích thước kết quả |
| CPU/decode | Chi phí giải nén, chuyển kiểu và đánh giá biểu thức |
| Intermediate rows | Số hàng đi vào join, sort, aggregate và window |
| Spill/network | Temp bytes và dữ liệu trao đổi giữa worker/node |

Tên trường và cách hiển thị phụ thuộc DBMS/query engine. Có engine hiển thị `PushedFilters`, `PartitionFilters`, `ReadSchema`, `Input`, `Output`, `Files read` hoặc `Bytes scanned`; engine khác dùng tên khác.

### 15.1. Estimated rows và actual rows

Nếu optimizer ước lượng filter giữ 1% nhưng thực tế giữ 80%, nó có thể chọn sai join method hoặc memory grant. Kiểm tra estimated/actual rows tại scan và các toán tử tiếp theo. Nếu sai lệch lớn, xem statistics, histogram, data skew và correlation giữa cột.

### 15.2. Không chỉ nhìn thời gian tổng

Một truy vấn có thể nhanh hơn do cache nóng dù bytes scanned không đổi. Ngược lại, bytes scanned giảm nhưng CPU tăng do decode hoặc biểu thức phức tạp. Hãy đo cùng workload nhiều lần, phân biệt cold/warm cache và so sánh cả resource consumption.

## 16. Quy trình tối ưu từng bước

1. **Xác định đầu ra:** liệt kê chính xác cột và hàng nghiệp vụ cần trả về.
2. **Đo baseline:** ghi query latency, bytes/pages read, rows read/output, CPU, memory, network và spill.
3. **Thu gọn projection:** bỏ `SELECT *`, bỏ cột không dùng trong filter/join/group/order/output.
4. **Viết predicate rõ ràng:** dùng kiểu dữ liệu phù hợp, khoảng nửa mở và tránh biến đổi không cần thiết trên cột.
5. **Kiểm tra pruning:** partition, index, row group, zone map, bloom filter hoặc file metadata.
6. **Kiểm tra pushdown:** xem predicate nào đã push, predicate nào còn residual và connector có giới hạn gì.
7. **Kiểm tra cardinality:** so estimated/actual rows, selectivity và correlation giữa các điều kiện.
8. **Đánh giá join/aggregate:** xác nhận số hàng đầu vào đã giảm trước toán tử tốn kém.
9. **Thử một thay đổi:** không đồng thời thay partition, index, file layout và query nếu muốn biết nguyên nhân.
10. **Đo lại:** giữ cùng dữ liệu, tham số, concurrency, trạng thái cache và cửa sổ đo.
11. **Kiểm chứng semantics:** đối chiếu kết quả, NULL, duplicate, boundary time và outer join.
12. **Ghi nhận trade-off:** chi phí ghi, compaction, metadata, freshness và workload khác.

## 17. Những sai lầm thường gặp

- **Dùng `SELECT *` cho báo cáo:** đọc và truyền cột không cần thiết.
- **Nghĩ predicate trong WHERE luôn được push xuống storage:** phải xác nhận bằng plan và scan metrics.
- **Cho rằng filter hiển thị gần scan đã giảm physical I/O:** có thể engine vẫn đọc page rồi mới lọc.
- **Dùng hàm trên partition/index key:** có thể cản range pruning hoặc index seek.
- **Bind sai kiểu dữ liệu:** implicit conversion có thể làm giảm khả năng dùng access path.
- **Chỉ lọc sau khi join:** có thể tạo intermediate rows rất lớn nếu điều kiện có thể áp dụng sớm hơn một cách an toàn.
- **Đẩy điều kiện outer join từ ON sang WHERE:** có thể loại hàng không khớp và thay đổi kết quả.
- **Đẩy HAVING xuống WHERE:** có thể làm thay đổi ngữ nghĩa aggregate.
- **Cho rằng CTE luôn materialize hoặc luôn inline:** hành vi phụ thuộc engine, phiên bản và cấu trúc query.
- **Tách OR bằng UNION ALL mà không xử lý giao nhau:** tạo duplicate rows.
- **Chia partition quá nhỏ:** tăng metadata, file count và scheduling overhead.
- **Chỉ nhìn tỷ lệ cột được chọn:** không phản ánh chính xác bytes đọc vì kích thước và compression khác nhau.
- **Không kiểm tra residual predicate:** một phần điều kiện có thể vẫn chạy ở tầng trên.
- **Chỉ nhìn cache hit hoặc thời gian một lần chạy:** bỏ qua bytes scanned, rows read và trạng thái cache.

## 18. Bài tập tự kiểm tra

### Bài tập 1: Projection pruning

Một bảng sự kiện có 30 cột, trong đó `payload_json` chiếm phần lớn dung lượng. Báo cáo chỉ cần `event_date`, `event_type` và `tenant_id` nhưng đang dùng `SELECT *`.

**Câu hỏi:** cần sửa gì và lợi ích có thể xuất hiện ở tầng nào?

**Gợi ý trả lời:** chọn ba cột cần thiết cùng các cột cần cho filter/join/group. Columnar reader có thể bỏ các column chunks không dùng; ở row store, lợi ích có thể rõ hơn ở network, decode và object allocation, còn page I/O phụ thuộc layout/index.

### Bài tập 2: Predicate không sargable

Bảng partition theo `created_at`; truy vấn dùng `WHERE DATE(created_at) = :day` và execution plan đọc nhiều partition.

**Câu hỏi:** viết lại predicate thế nào?

**Gợi ý trả lời:** dùng `created_at >= :day_start AND created_at < :next_day_start`, với hai mốc cùng kiểu và timezone đúng. Sau đó xác nhận partition pruning trong actual plan.

### Bài tập 3: Outer join và filter pushdown

Báo cáo cần giữ mọi khách hàng kể cả khách hàng chưa có đơn hàng trong tháng. Nhóm chuyển điều kiện tháng từ `ON` sang `WHERE` để lọc sớm.

**Câu hỏi:** điều gì thay đổi?

**Gợi ý trả lời:** hàng khách hàng không có đơn hàng nhận NULL ở phía orders và bị WHERE loại, làm kết quả gần với inner join. Giữ điều kiện lọc phía orders trong `ON` hoặc dùng cấu trúc tương đương bảo toàn outer join semantics.

### Bài tập 4: Row-group pruning

File Parquet có row group A với ngày từ tháng 1 đến tháng 2, row group B từ tháng 10 đến tháng 10. Truy vấn chỉ lấy tháng 10.

**Câu hỏi:** engine có thể bỏ row group nào dựa trên min/max?

**Gợi ý trả lời:** có thể bỏ A vì khoảng min/max không giao với tháng 10; B cần đọc. Kết quả còn phụ thuộc statistics có sẵn, predicate tương thích và reader hỗ trợ pruning.

### Bài tập 5: Predicate đã push nhưng bytes không giảm

Execution plan cho thấy filter được push vào scan, nhưng bytes đọc gần như không đổi.

**Câu hỏi:** vì sao?

**Gợi ý trả lời:** filter có thể được áp dụng khi decode từng hàng sau khi file/page đã đọc; metadata không đủ để skip vùng dữ liệu; hoặc predicate có selectivity thấp. Cần xem files/row groups skipped, bytes scanned, rows read/output và loại pushdown mà connector hỗ trợ.

### Bài tập 6: Chọn thứ tự điều kiện WHERE

Nhóm đặt predicate giữ 1% hàng lên trước trong câu SQL và kỳ vọng DB luôn đánh giá nó trước predicate giữ 80% hàng.

**Câu hỏi:** giả định này có đúng không?

**Gợi ý trả lời:** không. SQL khai báo; optimizer có thể sắp xếp lại và chọn access path dựa trên cost/statistics. Cần cải thiện predicate, index và statistics, sau đó kiểm tra plan.

### Checklist giảm dữ liệu phải quét

- [ ] Đã xác định cột đầu ra và các cột cần cho filter/join/group/order.
- [ ] Đã bỏ `SELECT *` khi không cần toàn bộ cột.
- [ ] Đã kiểm tra row store hay columnar storage và lợi ích projection tương ứng.
- [ ] Đã viết predicate tương thích kiểu dữ liệu và partition bounds.
- [ ] Đã dùng khoảng thời gian nửa mở khi lọc timestamp.
- [ ] Đã xác nhận partition pruning và số partition thực sự được đọc.
- [ ] Đã kiểm tra row-group/file pruning, min/max, bloom filter hoặc dictionary metadata nếu có.
- [ ] Đã phân biệt pushed predicate với residual predicate.
- [ ] Đã xem tác động của JOIN, outer join, HAVING và window function lên semantics.
- [ ] Đã kiểm tra CTE/materialization behavior của đúng engine.
- [ ] Đã so estimated rows với actual rows và xem selectivity/correlation.
- [ ] Đã đo bytes/pages read, rows read/output, CPU, memory, network và spill.
- [ ] Đã đối chiếu kết quả để bảo đảm không mất hàng, nhân bản hoặc đổi cách xử lý NULL.
- [ ] Đã đo lại trên workload đại diện và ghi nhận trade-off vận hành.

Chiếu cột và lọc sớm giúp giảm cả chiều rộng lẫn số lượng dữ liệu đi qua pipeline phân tích. Projection pruning tránh đọc cột thừa khi storage layout hỗ trợ; predicate pushdown, partition pruning và metadata pruning giúp bỏ hàng, partition, file hoặc row group không liên quan. Câu SQL chỉ mô tả ý định, còn execution plan mới cho biết engine thực sự đọc gì và lọc ở đâu. Hãy dùng predicate có kiểu phù hợp, bảo toàn semantics của JOIN/NULL/aggregate, đo bytes và rows thực tế, rồi kiểm chứng hiệu năng cùng tính đúng đắn trước khi triển khai.
