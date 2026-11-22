# Invisible index và thử nghiệm thay đổi kế hoạch thực thi trong Oracle Database

Một index có thể giúp một số truy vấn chạy nhanh hơn nhưng làm tăng chi phí INSERT, UPDATE và DELETE. Khi DBA muốn đánh giá việc bỏ một index, DROP ngay index có thể gây rủi ro vì các câu SQL đang phụ thuộc vào index có thể đổi execution plan và chậm đi. Oracle cung cấp **invisible index** để thử tác động của việc ẩn index khỏi optimizer mà vẫn giữ index trong database.

Invisible index vẫn tồn tại, chiếm dung lượng và được duy trì bởi DML. Theo mặc định, optimizer không xét index này khi chọn execution plan. Có thể bật tham số session `OPTIMIZER_USE_INVISIBLE_INDEXES` để optimizer cân nhắc các invisible index trong phiên thử nghiệm.

Câu hỏi mà kỹ thuật này giúp trả lời là: **nếu optimizer không còn dùng index này, các câu SQL sẽ chọn kế hoạch nào và hiệu năng thay đổi ra sao?** Nếu kết quả tốt và workload không bị ảnh hưởng, DBA có thể cân nhắc DROP index sau khi theo dõi đủ lâu. Nếu xuất hiện regression, có thể chuyển index về VISIBLE.

Bài học giải thích visibility của index, cách optimizer sử dụng invisible index, quy trình thử nghiệm có kiểm soát, cách xem execution plan và runtime statistics, giới hạn khi index hỗ trợ constraint, ảnh hưởng đến DML, các lỗi diễn giải thường gặp và bài thực hành trên bảng demo.

## 1. Visible index và invisible index

### 1.1. Visible index

Thông thường, index được tạo ở trạng thái visible. Optimizer có thể xem xét index khi lập kế hoạch thực thi nếu index phù hợp với predicate, join, order by hoặc yêu cầu truy cập dữ liệu.

Ví dụ:

```sql
CREATE INDEX ix_orders_customer
ON orders(customer_id);
```

Khi truy vấn lọc theo CUSTOMER_ID, optimizer có thể chọn INDEX RANGE SCAN nếu ước lượng chi phí phù hợp. Có index không đồng nghĩa Oracle luôn phải dùng index; optimizer vẫn có thể chọn full table scan hoặc một access path khác.

### 1.2. Invisible index

Invisible index là index có metadata visibility được đặt thành INVISIBLE. Index vẫn có trong schema, vẫn chiếm dung lượng và vẫn được duy trì khi dữ liệu thay đổi. Nhưng optimizer mặc định bỏ qua nó khi tạo execution plan.

Tạo index trực tiếp ở trạng thái invisible:

```sql
CREATE INDEX ix_orders_customer_test
ON orders(customer_id)
INVISIBLE;
```

Hoặc chuyển một index hiện có sang invisible:

```sql
ALTER INDEX ix_orders_customer INVISIBLE;
```

Để hiển thị lại:

```sql
ALTER INDEX ix_orders_customer VISIBLE;
```

Thay đổi visibility là DDL, vì vậy cần xem xét implicit commit và quy trình triển khai trước khi thực hiện trong môi trường có transaction nghiệp vụ đang mở.

### 1.3. Invisible không có nghĩa index bị vô hiệu hóa

Cần phân biệt:

| Trạng thái/khái niệm | Ý nghĩa |
| --- | --- |
| VISIBLE | Optimizer có thể xem xét index theo chi phí và cấu hình |
| INVISIBLE | Optimizer mặc định không xem xét index |
| UNUSABLE | Index không sẵn sàng cho các thao tác truy cập thông thường cho đến khi được rebuild hoặc xử lý |
| DROP | Index bị xóa khỏi schema |
| DISABLED constraint | Ràng buộc bị vô hiệu hóa; đây là trạng thái constraint, không phải visibility của index |

Invisible index không phải index bị drop, không phải index unusable và không phải constraint bị disable.

### 1.4. Vì sao không DROP ngay?

Giả sử một index được tạo từ lâu. DBA nghi ngờ nó không còn cần thiết. Nếu DROP, các truy vấn phụ thuộc index có thể đổi sang full table scan hoặc một access path khác. Khi đó phải tạo lại index và chờ kiểm tra kế hoạch.

Ẩn index giúp mô phỏng phần quan trọng của việc loại index khỏi lựa chọn của optimizer mà vẫn có thể khôi phục bằng ALTER INDEX VISIBLE.

Đây là công cụ thử nghiệm và triển khai có kiểm soát, không phải bằng chứng tự động rằng index có thể xóa an toàn.

## 2. Cách optimizer xử lý invisible index

### 2.1. Hành vi mặc định

Trong cấu hình thông thường, optimizer không xét invisible index khi tạo execution plan. Vì vậy, sau lệnh:

```sql
ALTER INDEX ix_orders_customer INVISIBLE;
```

các SQL parse mới sẽ lập kế hoạch như thể index đó không có sẵn cho optimizer. Những index visible khác vẫn có thể được chọn.

Một câu SQL đang chạy hoặc cursor đã được parse trước đó không nhất thiết đổi kế hoạch ngay tại thời điểm ALTER INDEX. Khi thử nghiệm, cần chạy statement được parse trong điều kiện mới và xem cursor plan tương ứng.

### 2.2. OPTIMIZER_USE_INVISIBLE_INDEXES

Tham số `OPTIMIZER_USE_INVISIBLE_INDEXES` điều khiển việc optimizer có được xem xét invisible index hay không.

Kiểm tra giá trị session:

```sql
SHOW PARAMETER optimizer_use_invisible_indexes;
```

Hoặc:

```sql
SELECT name, value
FROM   v$parameter
WHERE  name = 'optimizer_use_invisible_indexes';
```

Mặc định thường là FALSE. Có thể bật ở phạm vi session để thử nghiệm:

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
```

Sau đó optimizer có thể cân nhắc invisible index trong session đó. Tham số này không bắt optimizer phải dùng một index cụ thể; cost-based optimizer vẫn lựa chọn dựa trên thống kê, predicate, cardinality, system statistics và các yếu tố khác.

### 2.3. Tắt lại sau thử nghiệm

Khi kết thúc:

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

Thiết lập session chỉ tác động đến session hiện tại. Nó phù hợp để thử nghiệm kế hoạch mà không thay đổi hành vi optimizer của các session ứng dụng khác.

Không bật tham số ở SYSTEM chỉ để thử một câu SQL nếu không có lý do triển khai rõ ràng. Thay đổi phạm vi rộng có thể khiến nhiều invisible index khác cũng được optimizer cân nhắc.

### 2.4. Tham số TRUE không làm index visible

Hai khái niệm độc lập:

- `ALTER INDEX ... VISIBLE` thay đổi metadata visibility của index.
- `OPTIMIZER_USE_INVISIBLE_INDEXES = TRUE` cho phép optimizer trong phạm vi tham số cân nhắc invisible index.

Index vẫn được đánh dấu INVISIBLE trong dictionary khi session bật tham số TRUE. Session khác với tham số FALSE tiếp tục bỏ qua nó theo mặc định.

### 2.5. Hint và invisible index

Optimizer hint như `INDEX` hoặc `NO_INDEX` có thể tác động lựa chọn access path, nhưng không nên dùng hint để thay thế thử nghiệm visibility thông thường. Nếu mục tiêu là quan sát quyết định tự nhiên của optimizer, hãy giữ SQL, bind, thống kê và môi trường giống nhau, rồi thay đổi đúng một điều kiện: visibility hoặc tham số session.

Hint có thể hữu ích trong một thí nghiệm riêng để kiểm tra một access path có khả thi hay không. Kết quả đó không chứng minh optimizer sẽ tự chọn index trong workload thật.

## 3. Metadata và kiểm tra trạng thái index

### 3.1. Xem visibility trong USER_INDEXES

Trong schema hiện tại:

```sql
SELECT index_name,
       table_name,
       uniqueness,
       status,
       visibility,
       index_type
FROM   user_indexes
ORDER  BY table_name, index_name;
```

Cột VISIBILITY thường hiển thị VISIBLE hoặc INVISIBLE. Cột STATUS cho biết trạng thái index, ví dụ VALID hoặc UNUSABLE; không nhầm STATUS với VISIBILITY.

### 3.2. Xem index của bảng cụ thể

```sql
SELECT index_name,
       uniqueness,
       status,
       visibility
FROM   user_indexes
WHERE  table_name = 'ORDERS'
ORDER  BY index_name;
```

Tên object trong dictionary thường được lưu uppercase nếu không tạo bằng quoted identifier.

### 3.3. Xem các cột trong index

```sql
SELECT index_name,
       column_position,
       column_name,
       descend
FROM   user_ind_columns
WHERE  table_name = 'ORDERS'
ORDER  BY index_name, column_position;
```

Cần biết index được tạo trên cột nào và theo thứ tự nào trước khi đánh giá ảnh hưởng. Composite index có thể phục vụ nhiều câu SQL dựa trên leading columns; chỉ nhìn tên index không đủ để kết luận nó thừa.

### 3.4. Xem constraint liên quan

```sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status,
       c.validated,
       c.index_name
FROM   user_constraints c
WHERE  c.table_name = 'ORDERS'
ORDER  BY c.constraint_name;
```

Một index có thể liên quan đến PRIMARY KEY hoặc UNIQUE constraint. Oracle có các giới hạn đối với việc làm invisible index được dùng để thực thi các constraint này. Trước khi thay đổi visibility, xác định index có đang hỗ trợ constraint hay không; không dùng invisible index như cách vô hiệu hóa PK/UK. Nếu index được constraint dùng để bảo đảm uniqueness, xử lý constraint và index theo quy trình được hỗ trợ của phiên bản Oracle, không cố ép visibility bằng workaround.

### 3.5. Xem DDL của index

```sql
SELECT DBMS_METADATA.GET_DDL('INDEX', 'IX_ORDERS_CUSTOMER')
FROM   dual;
```

DBMS_METADATA giúp xem định nghĩa index gồm cột, tablespace, storage và thuộc tính liên quan. Cần quyền phù hợp nếu đọc metadata của schema khác.

## 4. Invisible index và thử nghiệm thay đổi execution plan

### 4.1. Mục tiêu thí nghiệm

Một thử nghiệm tốt cần trả lời được:

1. Khi index visible, optimizer chọn plan nào?
2. Khi index invisible và optimizer dùng mặc định, plan thay đổi ra sao?
3. Nếu cho phép dùng invisible index trong một session, optimizer có cân nhắc index đó không?
4. Runtime thực tế thay đổi thế nào với cùng dữ liệu, bind và điều kiện tải?
5. Index có đang được dùng bởi các SQL quan trọng khác không?

Không chỉ so sánh một dòng INDEX RANGE SCAN với TABLE ACCESS FULL. Cần xem thời gian, buffer gets, physical reads, số hàng thực tế, cardinality estimate và tác động của workload.

### 4.2. Thiết lập baseline

Trước khi thử:
- Ghi lại tên index và trạng thái ban đầu.
- Thu thập SQL_ID, plan hash value và execution plan của SQL quan trọng.
- Ghi nhận bind values hoặc phân bố bind đại diện.
- Ghi lại thống kê bảng/index và thời điểm gather stats.
- Đo elapsed time, CPU, logical reads và physical reads.
- Thực hiện trong môi trường test/staging nếu có thể.

Không thay đổi visibility của index production mà không có kế hoạch theo dõi và phương án khôi phục.

### 4.3. Thử nghiệm bằng EXPLAIN PLAN

```sql
EXPLAIN PLAN FOR
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM   orders
WHERE  customer_id = 100;

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
```

EXPLAIN PLAN hiển thị kế hoạch ước lượng cho câu SQL. Nó hữu ích để quan sát cách optimizer lập kế hoạch trong session hiện tại, nhưng không thay thế runtime plan của cursor thực thi.

Để thử invisible index, chạy EXPLAIN PLAN trong session có OPTIMIZER_USE_INVISIBLE_INDEXES FALSE và TRUE, giữ các điều kiện khác giống nhau.

### 4.4. Xem runtime plan bằng DBMS_XPLAN

Có thể thu thập thống kê thực thi cho một câu SQL:

```sql
SELECT /*+ gather_plan_statistics */
       order_id,
       customer_id,
       order_date,
       total_amount
FROM   orders
WHERE  customer_id = :customer_id;
```

Sau khi chạy và fetch kết quả, xem cursor plan:

```sql
SELECT *
FROM   TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
```

ALLSTATS LAST hiển thị thống kê của lần thực thi gần nhất nếu Oracle đã thu thập được. Có thể xem các thông tin như:
- E-Rows: số hàng ước lượng.
- A-Rows: số hàng thực tế.
- Buffers: logical reads.
- Reads: physical reads theo thống kê hiển thị.
- Predicate Information: điều kiện truy cập/lọc.
- Operation: các bước trong execution plan.

Cần quyền đọc các view hiệu năng liên quan. Nếu ALLSTATS LAST không có số liệu, xác nhận statement đã thực thi và có hint gather_plan_statistics hoặc cơ chế statistics phù hợp.

### 4.5. Vì sao EXPLAIN PLAN và runtime plan có thể khác?

Execution plan thực tế có thể khác EXPLAIN PLAN do:
- Bind peeking và bind values.
- Adaptive cursor sharing.
- Statistics hoặc histogram.
- Session parameters.
- SQL profile, baseline hoặc patch.
- Adaptive plans.
- Các yếu tố môi trường và optimizer settings.

Vì vậy, khi đánh giá tác động của invisible index, cần thu thập cursor thực tế dưới workload gần production và không chỉ dựa vào một EXPLAIN PLAN.

## 5. Thực hành: tạo bảng demo và index

### 5.1. Tạo dữ liệu thử nghiệm

Thực hiện trong schema học tập hoặc môi trường test:

```sql
CREATE TABLE demo_invisible_orders AS
SELECT LEVEL AS order_id,
       MOD(LEVEL, 1000) AS customer_id,
       CASE
           WHEN MOD(LEVEL, 20) = 0 THEN 'OPEN'
           ELSE 'CLOSED'
       END AS status,
       TRUNC(SYSDATE) - MOD(LEVEL, 365) AS order_date,
       MOD(LEVEL, 50000) / 100 AS total_amount
FROM   dual
CONNECT BY LEVEL <= 100000;
```

Tạo PK và index phục vụ truy vấn demo:

```sql
ALTER TABLE demo_invisible_orders
ADD CONSTRAINT pk_demo_invisible_orders
PRIMARY KEY (order_id);

CREATE INDEX ix_demo_orders_customer
ON demo_invisible_orders(customer_id);

CREATE INDEX ix_demo_orders_status_date
ON demo_invisible_orders(status, order_date);
```

Dữ liệu được tạo theo công thức để có thể lặp lại. Phân bố này chỉ phục vụ học tập, không đại diện mọi workload thực tế.

### 5.2. Thu thập thống kê

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'DEMO_INVISIBLE_ORDERS',
        cascade => TRUE
    );
END;
/
```

Optimizer cần thống kê phù hợp để ước lượng cardinality và chi phí. Nếu dữ liệu hoặc index thay đổi đáng kể, cần cân nhắc thu thập thống kê lại trước khi so sánh.

### 5.3. Chạy truy vấn baseline khi index visible

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;

SELECT /*+ gather_plan_statistics */
       order_id,
       customer_id,
       order_date,
       total_amount
FROM   demo_invisible_orders
WHERE  customer_id = 100;
```

Sau khi fetch hết kết quả, xem:

```sql
SELECT *
FROM   TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Ghi lại access path, buffers, reads, A-Rows, E-Rows và elapsed time. Kết quả plan phụ thuộc thống kê và môi trường, vì vậy không giả định index chắc chắn được chọn.

### 5.4. Ẩn index và chạy lại

```sql
ALTER INDEX ix_demo_orders_customer INVISIBLE;
```

Kiểm tra:

```sql
SELECT index_name, visibility, status
FROM   user_indexes
WHERE  index_name = 'IX_DEMO_ORDERS_CUSTOMER';
```

Trong session có OPTIMIZER_USE_INVISIBLE_INDEXES = FALSE, chạy lại cùng truy vấn với comment phân biệt để tạo/capture một lần parse riêng:

```sql
SELECT /*+ gather_plan_statistics */ /* INVISIBLE_TEST_OFF */
       order_id,
       customer_id,
       order_date,
       total_amount
FROM   demo_invisible_orders
WHERE  customer_id = 100;
```

Xem runtime plan bằng DBMS_XPLAN. Optimizer mặc định bỏ qua index vừa ẩn; nó có thể chọn index khác hoặc full table scan tùy chi phí.

### 5.5. Cho optimizer cân nhắc invisible index trong session thử nghiệm

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
```

Chạy truy vấn cùng điều kiện, với tag SQL khác:

```sql
SELECT /*+ gather_plan_statistics */ /* INVISIBLE_TEST_ON */
       order_id,
       customer_id,
       order_date,
       total_amount
FROM   demo_invisible_orders
WHERE  customer_id = 100;
```

Xem runtime plan. Optimizer được phép cân nhắc invisible index, nhưng không bắt buộc chọn nó. Nếu cost của một access path khác thấp hơn, optimizer có thể tiếp tục dùng plan khác.

### 5.6. Khôi phục trạng thái

Kết thúc thí nghiệm, trả index về visible và reset tham số session:

```sql
ALTER INDEX ix_demo_orders_customer VISIBLE;

ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

Xác nhận:

```sql
SELECT index_name, visibility, status
FROM   user_indexes
WHERE  index_name = 'IX_DEMO_ORDERS_CUSTOMER';
```

Luôn ghi nhận trạng thái ban đầu. Nếu index ban đầu đã invisible, không tự ý chuyển thành visible sau thử nghiệm; hãy khôi phục đúng trạng thái đã ghi.

## 6. Đọc và so sánh execution plan

### 6.1. So sánh access path

Các operation có thể gặp:
- TABLE ACCESS FULL: đọc bảng theo full scan.
- INDEX RANGE SCAN: truy cập một dải key phù hợp với predicate.
- INDEX UNIQUE SCAN: tìm một key duy nhất.
- TABLE ACCESS BY INDEX ROWID: lấy hàng từ bảng theo ROWID do index trả về.
- INDEX FAST FULL SCAN: đọc index như một cấu trúc dữ liệu riêng, không bảo đảm thứ tự key.

Khi index invisible, optimizer có thể đổi từ index range scan sang full scan. Điều đó không tự động là regression; nếu query trả về phần lớn bảng, full scan có thể rẻ hơn.

### 6.2. Ước lượng cardinality và thực tế

So sánh E-Rows với A-Rows:
- E-Rows cao hơn nhiều A-Rows: optimizer có thể ước lượng quá nhiều hàng.
- E-Rows thấp hơn nhiều A-Rows: optimizer có thể đánh giá thấp số hàng và chọn plan không phù hợp.
- Chênh lệch lớn có thể liên quan thống kê, histogram, correlation giữa các cột hoặc bind values.

Nếu plan thay đổi sau khi ẩn index, cần xác định đó là do access path mất đi hay do các điều kiện khác trong session thay đổi.

### 6.3. Logical reads và physical reads

- **Buffers/logical reads:** số lần đọc block qua buffer cache; hữu ích để so sánh lượng công việc đọc logic.
- **Physical reads:** block cần đọc từ storage theo thống kê runtime; có thể phụ thuộc cache state.
- **Elapsed time:** thời gian thực tế chịu ảnh hưởng tải hệ thống, I/O, CPU và concurrency.
- **CPU time:** thời gian CPU dùng cho statement.

Một lần chạy nhanh hơn có thể chỉ vì dữ liệu đã nằm trong cache. Nên chạy nhiều lần với điều kiện tương đương, quan sát cả logical reads và runtime, và không cố xóa buffer cache trên hệ thống dùng chung chỉ để làm benchmark.

### 6.4. Plan hash value

Plan hash value là dấu hiệu nhận diện cấu trúc plan, hữu ích khi so sánh. Tuy nhiên:
- Plan hash khác không nhất thiết có nghĩa hiệu năng xấu hơn.
- Plan hash giống nhau không bảo đảm runtime giống nhau.
- Cần xem operation, predicates, cardinality và thống kê thực tế.

### 6.5. Bind values và cursor sharing

Nếu SQL dùng bind variable, plan có thể chịu ảnh hưởng bind peeking hoặc adaptive cursor sharing. Khi so sánh:
- Dùng cùng bind values đại diện.
- Dùng cùng kiểu dữ liệu bind.
- Ghi nhận child cursor và SQL_ID.
- Không trộn kết quả của các lần parse khác điều kiện.
- Xem xét nhiều nhóm bind nếu độ chọn lọc khác nhau.

Một index có thể tốt cho customer có ít đơn hàng nhưng không tốt cho customer có rất nhiều đơn hàng. Không kết luận từ một bind value duy nhất.

## 7. Invisible index trong môi trường production

### 7.1. Quy trình đánh giá index có thể bỏ hay không

Một quy trình thường dùng:

1. Xác định index và lý do nghi ngờ không còn cần.
2. Kiểm tra index có hỗ trợ PK/UK constraint hoặc tính năng khác không.
3. Thu thập SQL workload sử dụng bảng và index.
4. Ghi baseline execution plan và runtime.
5. Thực hiện thay đổi INVISIBLE trong cửa sổ được kiểm soát.
6. Theo dõi workload đủ lâu để bao phủ chu kỳ nghiệp vụ.
7. Nếu xuất hiện regression, chuyển index về VISIBLE.
8. Nếu không có regression và có đủ bằng chứng, lập kế hoạch DROP riêng.
9. Sau DROP, tiếp tục theo dõi vì chi phí DML và dung lượng mới thực sự được giải phóng.

Không bỏ index chỉ vì không thấy nó xuất hiện trong một vài plan hoặc vì một báo cáo index usage ngắn hạn không ghi nhận hoạt động.

### 7.2. Invisible index vẫn có chi phí DML

Khi index INVISIBLE:
- INSERT vẫn phải cập nhật index.
- DELETE vẫn phải cập nhật index.
- UPDATE cột được index hóa vẫn có thể phải thay đổi index entry.
- Index vẫn chiếm dung lượng segment và có thể có chi phí bảo trì.

Do đó, invisible index chủ yếu kiểm tra ảnh hưởng tới lựa chọn execution plan. Nó không mô phỏng đầy đủ lợi ích hiệu năng DML và dung lượng mà DROP index mang lại.

### 7.3. Index usage monitoring không giống invisible index

Oracle có cơ chế monitoring usage:

```sql
ALTER INDEX ix_demo_orders_customer MONITORING USAGE;
```

Sau thời gian theo dõi:

```sql
SELECT index_name,
       monitoring,
       used,
       start_monitoring,
       end_monitoring
FROM   v$object_usage;
```

Khả năng và phạm vi view có thể phụ thuộc phiên bản/quyền. Monitoring usage trả lời index có được ghi nhận là sử dụng trong khoảng theo dõi hay không; nó không thay đổi visibility và không đo toàn bộ lợi ích tiềm năng của index. Một khoảng theo dõi ngắn hoặc workload không đầy đủ có thể bỏ sót SQL hiếm chạy theo tháng/quý.

### 7.4. Chú ý workload theo mùa hoặc theo kỳ

Một index có thể ít được dùng trong ngày thường nhưng quan trọng cho:
- Cuối tháng.
- Đóng sổ cuối quý.
- Báo cáo năm.
- Batch reconciliation.
- Quy trình audit.
- Sự kiện cao điểm.

Trước khi DROP, hãy theo dõi qua chu kỳ đủ đại diện hoặc phân tích SQL workload lịch sử. Không coi một ngày không có regression là đủ cho mọi hệ thống.

### 7.5. Kế hoạch rollback

Nếu sau khi ẩn index có regression:

```sql
ALTER INDEX ix_demo_orders_customer VISIBLE;
```

Đây là hành động khôi phục visibility tương đối nhanh. Tuy nhiên, plan của cursor đã parse có thể cần parse lại để optimizer xét index trong điều kiện mới. Theo dõi SQL_ID/child cursor và xác nhận runtime plan đã trở lại phù hợp.

Đừng đợi tới khi SLA bị vi phạm nghiêm trọng mới khôi phục. Đặt trước ngưỡng dừng thử nghiệm, ví dụ thời gian phản hồi hoặc buffer gets tăng quá mức đã thống nhất.

## 8. Ràng buộc và giới hạn cần lưu ý

### 8.1. Index hỗ trợ PRIMARY KEY hoặc UNIQUE

Một index được Oracle dùng để thực thi PRIMARY KEY hoặc UNIQUE constraint có giới hạn riêng đối với visibility. Không được xem invisible index như một cách tắt index enforcement trong khi vẫn giữ constraint.

Trước khi thử:

```sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status,
       c.index_name
FROM   user_constraints c
WHERE  c.table_name = 'DEMO_INVISIBLE_ORDERS';
```

Nếu index thuộc constraint, hãy kiểm tra tài liệu release và quy trình được hỗ trợ. Không disable constraint chỉ để có thể ẩn index nếu mục tiêu ban đầu chỉ là đánh giá plan.

### 8.2. Invisible index không phải index riêng cho một session

Visibility là thuộc tính của index trong metadata database. Tham số OPTIMIZER_USE_INVISIBLE_INDEXES mới là thiết lập theo session cho phép optimizer cân nhắc các invisible index.

Vì vậy, một session thử nghiệm bật TRUE có thể cân nhắc nhiều invisible index trong schema/database phù hợp, không chỉ index đang khảo sát. Kiểm kê các invisible index khác trước khi diễn giải plan.

### 8.3. Không đảm bảo index sẽ được dùng khi bật TRUE

Optimizer vẫn dựa trên cost. Nếu index có selectivity thấp, truy vấn cần phần lớn bảng hoặc clustering factor không thuận lợi, full scan có thể rẻ hơn. OPTIMIZER_USE_INVISIBLE_INDEXES = TRUE chỉ làm index đủ điều kiện được cân nhắc.

### 8.4. DDL và implicit commit

Các lệnh ALTER INDEX là DDL và có implicit commit theo quy tắc Oracle. Không đặt chúng giữa các bước DML mà ứng dụng kỳ vọng có thể ROLLBACK toàn bộ transaction.

Lập kế hoạch thay đổi riêng, ghi lại trạng thái ban đầu và phối hợp cửa sổ triển khai.

### 8.5. Version và loại index

Khả năng và giới hạn chi tiết có thể khác theo release, loại index, partitioning, constraint và tính năng đang dùng. Trước khi áp dụng trên hệ thống thực, đối chiếu SQL Language Reference và Administrator's Guide của đúng phiên bản Oracle. Không giả định mọi loại index có cùng hành vi hoặc mọi index đều có thể đổi visibility tự do.

## 9. Phân biệt Invisible Index với các tính năng liên quan

| Tính năng | Mục tiêu | Có xóa/không duy trì index không? |
| --- | --- | --- |
| Invisible index | Thử tác động khi optimizer không xét index | Không; DML vẫn duy trì index |
| Unusable index | Đánh dấu index không sẵn sàng sử dụng | Index không phục vụ truy cập bình thường; DML maintenance tùy thuộc thuộc tính và thao tác |
| Index monitoring | Ghi nhận thông tin sử dụng index | Không thay đổi plan hoặc maintenance |
| DROP INDEX | Xóa index khỏi schema | Có; không còn chi phí duy trì index đó |
| SQL Plan Baseline | Quản lý/kiểm soát plan được chấp nhận | Không trực tiếp thay đổi visibility index |
| SQL Profile | Cung cấp thông tin điều chỉnh optimizer | Không trực tiếp thay đổi visibility index |

Invisible index là phép thử về khả năng optimizer sử dụng index. Index monitoring là phép quan sát việc sử dụng. SQL Plan Management là cơ chế quản lý kế hoạch. Không dùng lẫn mục đích của các tính năng này.

## 10. Quy trình thí nghiệm có kiểm soát

### 10.1. Chuẩn bị

Trước khi chạy:
- Chọn một index không thuộc PK/UK constraint cần bảo vệ.
- Ghi lại visibility và DDL ban đầu.
- Xác định các SQL quan trọng liên quan đến bảng.
- Chuẩn bị bind values đại diện.
- Thu thập thống kê và runtime baseline.
- Chọn môi trường test/staging hoặc cửa sổ thay đổi được phê duyệt.
- Chuẩn bị câu lệnh khôi phục visibility.

### 10.2. Thực hiện

1. Chạy SQL baseline khi index visible.
2. Lưu SQL_ID, plan hash, operation, buffers, reads và elapsed time.
3. Chuyển index sang invisible.
4. Giữ OPTIMIZER_USE_INVISIBLE_INDEXES = FALSE và chạy SQL parse mới.
5. Ghi nhận plan khi optimizer bỏ qua index.
6. Bật TRUE ở session thử nghiệm và chạy lại.
7. Ghi nhận plan khi optimizer được phép cân nhắc index.
8. Chạy nhiều bind values và nhiều lần thực thi.
9. Khôi phục trạng thái index ban đầu.

### 10.3. Đánh giá

Không chỉ nhìn plan text. So sánh:
- Kết quả truy vấn có giống nhau không?
- A-Rows có phù hợp với kỳ vọng không?
- Buffers và physical reads thay đổi bao nhiêu?
- Elapsed/CPU time có ổn định qua nhiều lần chạy không?
- Các SQL khác trên cùng bảng có bị ảnh hưởng không?
- Batch DML có còn chi phí duy trì index trong giai đoạn invisible không?
- Workload theo tháng/quý có được bao phủ không?

### 10.4. Quyết định

- **Giữ visible:** index vẫn cần hoặc việc ẩn gây regression.
- **Giữ invisible trong giai đoạn theo dõi:** cần thêm bằng chứng từ workload đầy đủ.
- **DROP sau phê duyệt:** chỉ khi đã chứng minh không có regression đáng kể và chấp nhận ảnh hưởng đến DML/index storage.
- **Khôi phục visible:** nếu xuất hiện regression hoặc phát hiện dependency chưa được đánh giá.

Invisible index là một bước thử nghiệm có thể đảo ngược, nhưng DROP vẫn là thay đổi riêng cần kế hoạch và kiểm soát.

## 11. Những hiểu nhầm thường gặp

**“Invisible index đã bị xóa.”** Không. Index vẫn tồn tại và được duy trì bởi DML.

**“Optimizer luôn bỏ qua invisible index trong mọi tình huống.”** Mặc định là bỏ qua; session có OPTIMIZER_USE_INVISIBLE_INDEXES = TRUE có thể cho optimizer cân nhắc.

**“Bật tham số TRUE sẽ bắt Oracle dùng index.”** Không. Optimizer vẫn chọn theo cost và thống kê.

**“Ẩn index giúp giảm chi phí INSERT/UPDATE/DELETE.”** Không. Index vẫn được duy trì. Chỉ DROP mới loại bỏ chi phí duy trì index đó.

**“Một query không dùng index nghĩa là có thể DROP.”** Chưa đủ. Các SQL hiếm chạy hoặc workload theo kỳ có thể phụ thuộc index.

**“EXPLAIN PLAN là hiệu năng thực tế.”** Không. Cần xem runtime plan và thống kê thực thi.

**“Plan hash khác nghĩa là plan mới chậm hơn.”** Không. Phải so sánh operation và runtime metrics.

**“Invisible index vô hiệu hóa UNIQUE constraint.”** Không. Không dùng visibility để né constraint enforcement; index hỗ trợ constraint có giới hạn riêng.

**“V$OBJECT_USAGE cho biết toàn bộ mọi khả năng sử dụng.”** Không. Nó chỉ phản ánh monitoring trong phạm vi/thời gian đã bật và có thể bỏ sót workload hiếm.

**“Đổi index về VISIBLE bảo đảm mọi cursor lập tức dùng lại index.”** Không nhất thiết. Cần xem cursor parse, child cursor và runtime plan sau khi thay đổi.

## 12. Bài thực hành

Các bài tập dùng bảng DEMO_INVISIBLE_ORDERS ở mục 5. Chỉ chạy DDL trên schema học tập.

### Bài 1 — Xem trạng thái index

```sql
SELECT index_name,
       table_name,
       status,
       visibility,
       uniqueness
FROM   user_indexes
WHERE  table_name = 'DEMO_INVISIBLE_ORDERS';
```

Xác định index nào visible và index nào đang invisible.

### Bài 2 — Chuyển index sang invisible

```sql
ALTER INDEX ix_demo_orders_customer INVISIBLE;
```

Kiểm tra USER_INDEXES.VISIBILITY. Giải thích vì sao index vẫn tồn tại.

### Bài 3 — So sánh EXPLAIN PLAN

Chạy cùng một truy vấn với OPTIMIZER_USE_INVISIBLE_INDEXES FALSE và TRUE. Lưu hai kết quả DBMS_XPLAN.DISPLAY và giải thích khác biệt.

### Bài 4 — So sánh runtime plan

Chạy truy vấn có gather_plan_statistics, fetch hết kết quả và xem DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST. So sánh E-Rows, A-Rows, Buffers và Reads.

### Bài 5 — Thử bind values khác nhau

Chọn hai CUSTOMER_ID có số đơn khác nhau. Chạy truy vấn với cả hai bind và quan sát liệu optimizer có chọn cùng access path hay không.

### Bài 6 — Bật và tắt tham số session

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
SHOW PARAMETER optimizer_use_invisible_indexes;

ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

Giải thích vì sao tham số session không làm thay đổi metadata visibility của index.

### Bài 7 — Kiểm tra index có hỗ trợ constraint không

```sql
SELECT constraint_name,
       constraint_type,
       status,
       index_name
FROM   user_constraints
WHERE  table_name = 'DEMO_INVISIBLE_ORDERS';
```

Phân biệt PK index với index phụ dùng cho truy vấn.

### Bài 8 — Quan sát DML khi index invisible

Trong khi index invisible, INSERT một hàng demo rồi kiểm tra index vẫn tồn tại và vẫn được duy trì. Giải thích vì sao invisible không mô phỏng đầy đủ việc DROP.

### Bài 9 — Index usage monitoring

Bật monitoring usage, chạy một số SQL đại diện, rồi xem V$OBJECT_USAGE nếu phiên bản và quyền cho phép. So sánh mục đích monitoring với invisible index.

### Bài 10 — Khôi phục trạng thái

```sql
ALTER INDEX ix_demo_orders_customer VISIBLE;
ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

Xác nhận visibility đúng như trạng thái ban đầu.

### Bài 11 — Đánh giá một index ứng viên DROP

Chọn một index phụ trong schema demo. Viết kế hoạch theo dõi workload đủ chu kỳ, liệt kê SQL quan trọng và các chỉ số runtime cần so sánh trước khi đề xuất DROP.

### Bài 12 — Đọc plan và ra quyết định

Giả sử khi invisible:
- Một truy vấn tăng buffers gấp 8 lần.
- Một truy vấn khác giảm elapsed time 10%.
- Batch INSERT không thay đổi đáng kể vì index vẫn được duy trì.

Đề xuất bước tiếp theo. Giải thích vì sao không thể kết luận index nên DROP chỉ từ một truy vấn.

## 13. Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): tạo index và thuộc tính visibility.
- [Oracle Database SQL Language Reference — ALTER INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-INDEX.html): thay đổi visibility và thuộc tính index.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer, execution plan và phân tích hiệu năng SQL.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): hiển thị execution plan và runtime statistics.
- [Oracle Database Reference — USER_INDEXES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_INDEXES.html): metadata index và visibility.
- [Oracle Database Reference — V$OBJECT_USAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-OBJECT_USAGE.html): thông tin index usage monitoring.

Invisible index giúp thử tác động của việc loại một index khỏi lựa chọn của optimizer mà vẫn giữ index và khả năng khôi phục visibility. Hãy ghi baseline, thay đổi một điều kiện mỗi lần, so sánh runtime plan với cùng bind và workload, theo dõi đủ chu kỳ nghiệp vụ, rồi mới quyết định giữ, khôi phục hay DROP. **Invisible index vẫn được duy trì bởi DML; thử nghiệm visibility đánh giá ảnh hưởng đến execution plan, không đo toàn bộ lợi ích DML và dung lượng của việc xóa index.**
