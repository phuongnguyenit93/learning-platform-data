# Truy vấn chậm đột ngột do thống kê, bind hoặc thay đổi kế hoạch

Một câu SQL chạy ổn định trong nhiều tuần có thể đột nhiên chậm sau một lần gather statistics, sau khi dữ liệu tăng mạnh, khi ứng dụng thay đổi bind value hoặc khi Oracle tạo child cursor với execution plan khác. Sự cố thường xuất hiện dưới dạng latency tăng, CPU/IO tăng, nhiều buffer gets hơn, thời gian chờ lớn hơn hoặc chỉ một nhóm người dùng bị ảnh hưởng.

Khi điều tra, cần phân biệt ba nhóm nguyên nhân có liên quan nhưng không giống nhau:

- **Statistics thay đổi hoặc không còn đại diện:** optimizer ước tính cardinality sai và chọn access path/join method khác.
- **Bind variable và dữ liệu lệch phân bố:** cùng SQL text nhưng các giá trị bind có selectivity rất khác nhau; bind peeking hoặc adaptive cursor sharing có thể tạo nhiều child cursor/plan.
- **Execution plan thay đổi:** cursor bị invalidation, optimizer environment đổi, object/index thay đổi hoặc plan mới có chi phí thực tế cao hơn.

Không nên bắt đầu bằng việc tạo index hoặc flush shared pool. Trước tiên phải xác định đúng SQL, child cursor, plan đã chạy, số liệu thực tế và thay đổi xảy ra gần thời điểm bắt đầu chậm. Sau đó mới chọn cách khôi phục hoặc điều chỉnh có phạm vi.

## 1. Nhận diện sự cố và bảo toàn bằng chứng

### 1.1. Xác định biểu hiện cụ thể

Ghi nhận:

- Thời điểm bắt đầu chậm và timezone.
- Endpoint, batch hoặc thao tác nghiệp vụ bị ảnh hưởng.
- Chỉ một SQL hay nhiều SQL cùng chậm.
- Mọi người dùng đều bị ảnh hưởng hay chỉ một nhóm bind value/tenant.
- Latency p50/p95/p99, throughput và error rate trước/sau sự cố.
- SQL_ID, module, action, service, instance và session nếu có.
- Có thay đổi gần thời điểm đó: gather stats, deploy code, DDL, tạo/drop index, partition maintenance, thay đổi parameter, patch hoặc tăng dữ liệu.

Một query chậm với một customer lớn nhưng vẫn nhanh với customer nhỏ có thể là vấn đề selectivity/bind. Nếu tất cả SQL đều chậm cùng lúc, hãy xem CPU, I/O, lock, network, connection pool và workload nền trước khi kết luận plan regression.

### 1.2. Không chỉ so sánh elapsed time tổng

Các bộ đếm trong `V$SQL` thường tích lũy theo cursor. Khi so sánh, cần tính trên mỗi execution và xem cursor đã chạy bao nhiêu lần. Một cursor có elapsed time tổng lớn có thể chỉ vì đã chạy nhiều hơn.

Các chỉ số hữu ích:

| Chỉ số | Câu hỏi |
|---|---|
| `EXECUTIONS` | Cursor đã chạy bao nhiêu lần? |
| `ELAPSED_TIME` | Tổng thời gian elapsed tích lũy là bao nhiêu? |
| `CPU_TIME` | Tổng CPU time là bao nhiêu? |
| `BUFFER_GETS` | Có bao nhiêu logical reads? |
| `DISK_READS` | Có bao nhiêu physical reads được ghi nhận? |
| `ROWS_PROCESSED` | Cursor xử lý bao nhiêu dòng? |
| `PLAN_HASH_VALUE` | Cursor dùng plan có hash nào? |
| `CHILD_NUMBER` | Đây là child cursor thứ mấy của SQL_ID? |
| `IS_BIND_SENSITIVE` / `IS_BIND_AWARE` | Oracle có nhận diện độ nhạy với bind không? |

`ELAPSED_TIME`, `CPU_TIME`, `BUFFER_GETS` và `DISK_READS` là tổng tích lũy trong vòng đời cursor. Chia cho `EXECUTIONS` cho số trung bình gần đúng; để đo percentile request, cần APM hoặc công cụ tracing ở tầng ứng dụng.

### 1.3. Lấy SQL_ID từ nguồn có ngữ cảnh

Tốt nhất lấy SQL_ID từ APM, trace ứng dụng, `V$SESSION`, SQL monitor được cấp phép hoặc log có correlation ID. Tránh tìm bằng `SQL_TEXT LIKE '%...%'` rồi chọn nhầm câu SQL tương tự.

Nếu có session đang chạy, có thể xem:

```sql
SELECT sid,
       serial#,
       username,
       service_name,
       module,
       action,
       sql_id,
       sql_child_number,
       event,
       wait_class,
       seconds_in_wait
FROM v$session
WHERE username IS NOT NULL
  AND sql_id IS NOT NULL
ORDER BY seconds_in_wait DESC;
```

View `V$SESSION` cho biết trạng thái tại thời điểm truy vấn. Một request có thể đã kết thúc trước khi DBA kiểm tra; vì vậy nên thu thập SQL_ID và timing từ ứng dụng trong lúc sự cố diễn ra.

## 2. Xác định cursor và execution plan đang dùng

### 2.1. Liệt kê child cursor của một SQL_ID

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       optimizer_env_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS elapsed_seconds,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1e3, 3)
           AS avg_elapsed_ms,
       ROUND(cpu_time / NULLIF(executions, 0) / 1e3, 3)
           AS avg_cpu_ms,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS buffers_per_exec,
       ROUND(disk_reads / NULLIF(executions, 0), 1)
           AS reads_per_exec,
       rows_processed,
       is_bind_sensitive,
       is_bind_aware,
       last_active_time
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Một SQL_ID có thể có nhiều child cursor. Nếu các child có `PLAN_HASH_VALUE` khác nhau, cùng SQL text có thể đang chạy bằng nhiều plan. So sánh average elapsed, buffers/execution, reads/execution và số executions của từng child.

Không kết luận child có average lớn nhất chắc chắn là plan xấu nếu nó xử lý bind value hoặc số dòng khác hẳn. Cần so sánh các lần chạy với bind value, row count và workload tương đương.

### 2.2. Xem SQL text và plan hash

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       sql_fulltext
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Giữ nguyên SQL text và SQL_ID khi so sánh. Nếu ứng dụng nối literal vào SQL thay vì bind, mỗi giá trị có thể tạo SQL text/SQL_ID khác nhau, làm tăng parse và khiến việc so sánh khó hơn.

### 2.3. Xem execution plan thực tế

Nếu biết SQL_ID và child number:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +ALIAS +OUTLINE'
    )
);
```

`DISPLAY_CURSOR` đọc plan của cursor trong shared pool. `ALLSTATS LAST` hiển thị runtime row-source statistics của lần thực thi cuối cùng có thu thập số liệu. Nếu ứng dụng không bật thống kê thực thi cho cursor, cột `A-Rows`, `Buffers` hoặc thời gian theo operation có thể không đầy đủ.

Để thu thập runtime statistics trong lần chạy kiểm soát, có thể dùng hint:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, order_date, total_amount
FROM app.orders
WHERE customer_id = :customer_id
  AND status = :status;
```

Sau khi chạy xong trong cùng session, gọi `DISPLAY_CURSOR` cho SQL_ID/child phù hợp. Hint có overhead nhỏ và cần được dùng có mục tiêu. Không thêm hint vào mọi SQL production chỉ để quan sát.

### 2.4. Vì sao EXPLAIN PLAN chưa đủ?

`EXPLAIN PLAN` tạo plan ước tính chứ không chứng minh plan mà cursor thực tế đã chạy. Kết quả có thể khác do:

- Bind value và bind peeking.
- Child cursor/adaptive cursor sharing.
- Optimizer environment của session.
- Statistics hoặc histogram tại thời điểm parse.
- Adaptive plan và runtime decision.
- Cursor đã được load trước đó với môi trường khác.

Khi truy vấn thực sự chậm, ưu tiên `DBMS_XPLAN.DISPLAY_CURSOR` với đúng SQL_ID và child number. Dùng `EXPLAIN PLAN` để khảo sát plan dự kiến, không dùng nó làm bằng chứng duy nhất cho một regression đang xảy ra.

## 3. Đọc plan để tìm điểm regression

### 3.1. So sánh operation và access path

Các thay đổi thường thấy:

| Plan cũ | Plan mới | Câu hỏi cần kiểm tra |
|---|---|---|
| `INDEX RANGE SCAN` | `TABLE ACCESS FULL` | Query cần bao nhiêu phần trăm bảng? Selectivity/statistics có đổi không? |
| `NESTED LOOPS` | `HASH JOIN` | Outer rows và cardinality ước tính thay đổi ra sao? |
| `HASH JOIN` | `NESTED LOOPS` | Có quá nhiều lookup lặp lại hoặc index access đắt không? |
| Partition pruning ít partition | Đọc nhiều partition | Predicate có còn dùng partition key đúng cách không? |
| Index access có filter sớm | Filter sau khi đọc nhiều row | Predicate có bị implicit conversion hoặc function làm giảm khả năng access không? |
| Ít sort/temp | Sort/hash spill ra TEMP | Số dòng, memory grant/workarea hoặc concurrency có đổi không? |

Full table scan không mặc định là xấu. Nếu query trả phần lớn bảng, full scan có thể rẻ hơn index lookup. Hãy đánh giá số dòng thực tế, buffers, reads, CPU và elapsed time, không chỉ nhìn tên operation.

### 3.2. So E-Rows và A-Rows

Trong `DBMS_XPLAN`, `E-Rows` là số dòng optimizer ước tính; `A-Rows` là số dòng thực tế được ghi nhận. Chênh lệch lớn thường là manh mối quan trọng.

Ví dụ:

| Operation | E-Rows | A-Rows | Diễn giải |
|---|---:|---:|---|
| Filter status | 100 | 80.000 | Optimizer ước tính thấp hơn thực tế rất nhiều. |
| Join customers/orders | 5.000 | 4.800 | Ước tính tương đối sát. |
| Inner index lookup | 1 | 80.000, Starts=80.000 | Lookup lặp rất nhiều lần; cần xem tổng buffers và join method. |

Số liệu trên chỉ minh họa. Với nested loops, `Starts` cho biết operation được chạy bao nhiêu lần; phải đọc `A-Rows` cùng `Starts` để hiểu tổng công việc. Sai lệch cardinality ở node sớm có thể dẫn tới join order hoặc join method kém hiệu quả ở các node phía trên.

### 3.3. Predicate Information

Kiểm tra predicate được dùng làm `access` hay chỉ làm `filter`. Một số nguyên nhân làm predicate kém hiệu quả:

- Hàm trên cột, ví dụ `TRUNC(order_date) = :day`, trong khi index thường đặt trên `order_date`.
- Implicit conversion do bind datatype khác datatype cột.
- So sánh chuỗi và số không nhất quán.
- Leading wildcard như `LIKE '%abc'` không phù hợp với B-tree index thông thường.
- Điều kiện OR phức tạp hoặc biểu thức không có function-based index phù hợp.
- Predicate không khớp partition key nên pruning không hiệu quả.

Không tạo function-based index ngay khi thấy hàm trong predicate. Trước tiên xác nhận semantics, selectivity, SQL thực tế và khả năng sửa câu lệnh để giữ cột ở dạng có thể dùng access path phù hợp.

### 3.4. Buffers, reads, CPU và TEMP

- `Buffers` cao cho thấy nhiều logical block được xử lý, có thể do đọc quá nhiều row, lookup lặp hoặc join intermediate lớn.
- `Reads` cao cho thấy physical I/O được ghi nhận; cache state và storage latency ảnh hưởng kết quả.
- CPU cao với reads thấp có thể liên quan tới xử lý nhiều row, function, sort, hash hoặc parse.
- TEMP cao có thể do sort/hash spill hoặc dữ liệu trung gian lớn.
- Elapsed time cao nhưng CPU thấp có thể do wait, blocking, I/O hoặc network.

Đọc runtime plan cùng wait event và số liệu ứng dụng. Một plan hash không đổi nhưng latency tăng vẫn có thể do storage chậm, cache lạnh, lock hoặc concurrency tăng.

## 4. Statistics và cách chúng ảnh hưởng optimizer

### 4.1. Optimizer statistics gồm những gì?

Oracle optimizer dùng statistics để ước tính chi phí và cardinality. Các thông tin quan trọng gồm:

- Table statistics: số dòng, số block, kích thước bảng.
- Column statistics: số giá trị distinct, số `NULL`, density và histogram.
- Index statistics: leaf blocks, clustering factor, blevel và số distinct key.
- Partition/global statistics: thống kê ở cấp partition và toàn bảng.
- System statistics: đặc tính CPU/I/O được optimizer dùng trong một số phép tính chi phí.

Statistics không phải dữ liệu nghiệp vụ. Chúng là mô tả/ước tính về dữ liệu để optimizer chọn plan. Khi dữ liệu thay đổi, statistics cũ có thể làm cardinality sai; khi gather stats, plan có thể đổi dù SQL không đổi.

### 4.2. Kiểm tra thời điểm gather statistics

```sql
SELECT owner,
       table_name,
       num_rows,
       blocks,
       sample_size,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND table_name = 'ORDERS';
```

Với partitioned table, view có thể có nhiều dòng cho table/partition/subpartition. Hãy xem cả global và partition statistics. `NUM_ROWS` là giá trị thống kê, không nhất thiết là số dòng chính xác ngay tại thời điểm truy vấn.

Có thể kiểm tra cột quan trọng:

```sql
SELECT column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM dba_tab_col_statistics
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY column_name;
```

Kiểm tra index:

```sql
SELECT index_name,
       status,
       visibility,
       blevel,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       last_analyzed
FROM dba_indexes
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY index_name;
```

Nếu không có quyền DBA view, dùng `ALL_TAB_STATISTICS`, `ALL_TAB_COL_STATISTICS` và `ALL_INDEXES` trong phạm vi user được phép xem.

### 4.3. Statistics stale hoặc không đại diện

Statistics có thể stale sau khi lượng dữ liệu thay đổi đáng kể. Nhưng stale không đồng nghĩa chắc chắn plan sai; ngược lại, statistics chưa stale cũng có thể không đại diện nếu phân bố giá trị thay đổi mạnh.

Kiểm tra:

- Bảng tăng/giảm mạnh số dòng sau bulk load hoặc purge.
- Một vài giá trị mới chiếm tỷ lệ lớn.
- Dữ liệu chuyển từ phân bố đều sang skew.
- Partition mới có dữ liệu khác hẳn partition cũ.
- Index được rebuild hoặc cấu trúc bảng thay đổi.
- Statistics được gather với sample/estimate khác trước.
- Histogram được tạo, xóa hoặc thay đổi bucket.

Không gather stats toàn schema ngay khi thấy query chậm. Thu hẹp đối tượng liên quan, so sánh timestamp và kiểm tra plan trước/sau.

### 4.4. Histogram và dữ liệu skew

Histogram giúp optimizer hiểu phân bố giá trị của cột. Không có histogram, optimizer có thể giả định phân bố tương đối đều dựa trên NDV/density. Nếu một trạng thái chiếm 99% và trạng thái khác chỉ chiếm 0,1%, giả định đều có thể sai lớn.

Các loại histogram và cách tạo phụ thuộc phiên bản Oracle, số bucket, `METHOD_OPT` và workload. `SIZE AUTO` cho phép Oracle cân nhắc histogram dựa trên workload/usage và statistics policy; không có nghĩa mọi cột đều nên có histogram.

Kiểm tra histogram:

```sql
SELECT column_name,
       histogram,
       num_distinct,
       density,
       num_buckets,
       last_analyzed
FROM dba_tab_col_statistics
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
  AND column_name IN ('STATUS', 'CUSTOMER_ID');
```

Nếu cần xem endpoint:

```sql
SELECT endpoint_number,
       endpoint_value,
       endpoint_actual_value
FROM dba_tab_histograms
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
  AND column_name = 'STATUS'
ORDER BY endpoint_number;
```

`ENDPOINT_ACTUAL_VALUE` và một số cột có thể phụ thuộc kiểu dữ liệu/phiên bản. Với histogram dạng frequency/top-frequency/hybrid, cách diễn giải endpoint khác nhau; không đọc endpoint như danh sách đơn giản của mọi giá trị nếu không biết loại histogram.

### 4.5. Extended statistics cho cột tương quan

Nếu hai cột có tương quan mạnh, ví dụ `COUNTRY_CODE` và `POSTAL_REGION`, optimizer có thể ước tính sai khi giả định selectivity độc lập. Extended statistics có thể mô tả column group:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => 'APP',
           tabname   => 'CUSTOMERS',
           extension => '(COUNTRY_CODE, POSTAL_REGION)'
       ) AS extension_name
FROM dual;
```

Sau đó gather statistics phù hợp và kiểm tra cardinality. Extended statistics không phải giải pháp chung cho mọi query; chỉ tạo khi có bằng chứng cột tương quan và sai lệch estimate đáng kể.

### 4.6. Statistics lock và pending statistics

Statistics có thể bị lock ở table/schema level. Nếu stats không cập nhật như mong đợi, kiểm tra `STATTYPE_LOCKED` và preferences. Không unlock chỉ để ép gather stats nếu chưa hiểu lý do khóa.

Pending statistics cho phép gather stats để thử trước khi publish. Ví dụ:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
```

Trong session thử nghiệm, bật dùng pending statistics:

```sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
```

Sau khi kiểm tra plan và hiệu năng, có thể publish:

```sql
EXEC DBMS_STATS.PUBLISH_PENDING_STATS('APP', 'ORDERS');
```

Hoặc xóa pending stats nếu không dùng:

```sql
EXEC DBMS_STATS.DELETE_PENDING_STATS('APP', 'ORDERS');
```

Pending statistics giúp thử trong phạm vi session trước khi publish toàn hệ thống. Cú pháp và quyền cần xác nhận theo phiên bản. Sau thử nghiệm, khôi phục session setting và table preference theo chính sách để không vô tình giữ cấu hình thử nghiệm.

## 5. Bind variable, bind peeking và adaptive cursor sharing

### 5.1. Vì sao cùng SQL nhưng bind value khác nhau?

Giả sử câu SQL:

```sql
SELECT order_id, order_date, total_amount
FROM app.orders
WHERE status = :status;
```

Trong dữ liệu production, `CLOSED` có thể chiếm 95% số dòng, còn `ESCALATED` chỉ chiếm 0,2%. Truy vấn `CLOSED` có thể phù hợp full scan, trong khi `ESCALATED` có thể phù hợp index range scan.

Nếu mọi lần chạy dùng cùng SQL text và bind, Oracle có thể tái sử dụng cursor. Đây thường là lợi ích của bind variable, nhưng khi dữ liệu skew mạnh, một plan duy nhất có thể không tối ưu cho mọi bind value.

### 5.2. Bind peeking

Khi hard parse, Oracle có thể peek giá trị bind đầu tiên để ước tính selectivity và chọn plan. Plan ban đầu có thể phù hợp với bind đó nhưng không phù hợp với các giá trị sau có phân bố khác.

Ví dụ:

1. Request đầu tiên bind `ESCALATED`, optimizer chọn index range scan.
2. Cursor được chia sẻ.
3. Request sau bind `CLOSED`, nhưng plan index có thể phải đọc quá nhiều row.
4. Latency của nhóm `CLOSED` tăng dù SQL text không đổi.

Chi tiết phụ thuộc histogram, phiên bản và optimizer behavior. Bind peeking không phải lúc nào cũng xấu; nó giúp optimizer chọn plan dựa trên dữ liệu thực tế khi parse.

### 5.3. Adaptive Cursor Sharing

Oracle có Adaptive Cursor Sharing (ACS) để nhận diện câu SQL bind-sensitive và trong điều kiện phù hợp tạo các child cursor/plan cho các vùng bind value khác nhau. Một SQL có thể chuyển từ bind-sensitive sang bind-aware sau khi Oracle thu thập đủ thông tin.

Kiểm tra:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       is_bind_sensitive,
       is_bind_aware,
       executions,
       last_active_time
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Nếu nhiều child cursor có plan khác nhau, so sánh bind distribution và hiệu năng từng child. Nhiều child không tự động là lỗi; có thể là hành vi cần thiết để xử lý skew. Nhưng số child tăng bất thường cũng có thể làm tăng memory/parse overhead hoặc chỉ ra mismatch môi trường/bind metadata.

### 5.4. Xem bind được capture và peeked binds

`V$SQL_BIND_CAPTURE` có thể cung cấp bind metadata và giá trị capture gần nhất:

```sql
SELECT sql_id,
       child_number,
       name,
       position,
       datatype_string,
       value_string,
       last_captured
FROM v$sql_bind_capture
WHERE sql_id = :sql_id
ORDER BY child_number, position;
```

Bind capture có tính lấy mẫu; không ghi lại mọi execution và không phải lúc nào cũng có giá trị mới nhất. Một số kiểu dữ liệu không được capture đầy đủ. `PEEKED_BINDS` trong `DBMS_XPLAN.DISPLAY_CURSOR` thường phản ánh giá trị được peek lúc hard parse, không nhất thiết là bind của lần execution chậm gần nhất.

Bind value có thể chứa email, account ID, token hoặc dữ liệu cá nhân. Chỉ truy cập và chia sẻ trong phạm vi quyền được phê duyệt; che giá trị nhạy cảm trong báo cáo.

### 5.5. Kiểm tra datatype của bind

Ứng dụng nên bind đúng kiểu tương ứng với cột. Nếu cột là `NUMBER` nhưng JDBC bind chuỗi, Oracle có thể phải implicit conversion. Nếu hàm chuyển đổi áp dụng lên cột, index access có thể bị ảnh hưởng hoặc phát sinh lỗi dữ liệu.

Ví dụ Java:

```java
String sql = "SELECT order_id FROM app.orders WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId); // CUSTOMER_ID là NUMBER nguyên phù hợp.
    try (ResultSet rs = ps.executeQuery()) {
        // Đọc kết quả.
    }
}
```

Không bind `customerId` bằng `setString()` chỉ vì giá trị ban đầu đến từ JSON. Hãy parse/validate ở tầng ứng dụng rồi bind đúng kiểu SQL. Với `DATE`, `TIMESTAMP`, `VARCHAR2` và `NUMBER`, datatype/precision/length cũng cần tương thích.

### 5.6. Kiểm tra child cursor không share được

`V$SQL_SHARED_CURSOR` có các cột giải thích vì sao child cursor không thể share với cursor khác. Ví dụ:

```sql
SELECT child_number,
       bind_mismatch,
       bind_equiv_failure,
       optimizer_mismatch,
       stats_row_mismatch,
       user_bind_peek_mismatch,
       language_mismatch
FROM v$sql_shared_cursor
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Các cột có sẵn và tên cột có thể khác theo phiên bản. Nếu một cột không tồn tại, kiểm tra cấu trúc view của phiên bản đang chạy thay vì suy diễn. Các cờ cho biết một số lý do share failure; cần đọc cùng `V$SQL`, optimizer environment và bind metadata.

Nguyên nhân có thể gồm bind datatype/length mismatch, optimizer environment khác nhau, object/statistics mismatch, authorization hoặc các điều kiện cursor sharing khác. Không xóa child cursor chỉ để giảm số lượng mà chưa xử lý nguyên nhân.

## 6. Tìm lịch sử thay đổi plan và statistics

### 6.1. So sánh thời điểm chậm với stats update

```sql
SELECT owner,
       table_name,
       stats_update_time
FROM dba_tab_stats_history
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY stats_update_time DESC;
```

`DBA_TAB_STATS_HISTORY` lưu lịch sử statistics theo retention policy. Nếu thời điểm stats update trùng với thời điểm query bắt đầu chậm, đó là manh mối, không phải bằng chứng duy nhất. Cần so sánh plan, histogram, cardinality và dữ liệu thực tế.

Kiểm tra thời gian lịch sử còn khả dụng:

```sql
SELECT DBMS_STATS.GET_STATS_HISTORY_AVAILABILITY AS oldest_available_time
FROM dual;
```

Nếu cần xem stats history cho table khác, điều chỉnh owner/table. Lịch sử có thể không còn nếu đã hết retention hoặc bị purge.

### 6.2. So sánh AWR nếu được cấp phép

Trong môi trường có quyền và license Oracle Diagnostics Pack phù hợp, AWR có thể giúp xem SQL statistics theo snapshot và plan history. Ví dụ truy vấn tổng hợp SQL theo snapshot:

```sql
SELECT ss.snap_id,
       sn.begin_interval_time,
       ss.plan_hash_value,
       ss.executions_delta,
       ROUND(ss.elapsed_time_delta / 1e6, 2) AS elapsed_seconds,
       ROUND(ss.cpu_time_delta / 1e6, 2) AS cpu_seconds,
       ss.buffer_gets_delta,
       ss.disk_reads_delta
FROM dba_hist_sqlstat ss
JOIN dba_hist_snapshot sn
  ON sn.snap_id = ss.snap_id
 AND sn.dbid = ss.dbid
 AND sn.instance_number = ss.instance_number
WHERE ss.sql_id = :sql_id
ORDER BY ss.snap_id;
```

Các delta giúp so sánh theo khoảng thời gian. `DBA_HIST_SQLSTAT`, AWR reports và một số dữ liệu lịch sử liên quan thuộc phạm vi Diagnostics Pack theo chính sách Oracle; chỉ sử dụng khi tổ chức có quyền/license phù hợp. Nếu không có license, dựa trên cursor cache, SQL trace được phép, APM và các view miễn phí phù hợp.

### 6.3. SQL plan history

Có thể xem lịch sử plan từ `DBA_HIST_SQL_PLAN` trong môi trường có quyền/license phù hợp. Không dựa vào một plan hash đơn lẻ nếu có adaptive plan hoặc child cursor khác nhau. Cần so sánh operation, predicate, outline, optimizer environment và runtime stats.

### 6.4. Kiểm tra thay đổi object và optimizer environment

Kiểm tra thời điểm thay đổi:

- Index được tạo, drop, unusable hoặc invisible.
- Partition được exchange, split, truncate hoặc move.
- Column datatype/constraint thay đổi.
- Statistics được gather, restore, lock hoặc publish.
- Optimizer parameter/session setting đổi.
- Ứng dụng thay JDBC driver, bind datatype, SQL text hoặc session initialization.
- Database được patch/upgrade hoặc `OPTIMIZER_FEATURES_ENABLE` thay đổi.

Trong `V$SQL`, `OPTIMIZER_ENV_HASH_VALUE` giúp nhận diện cursor được parse với optimizer environment khác nhau. So sánh session parameter và module/service khi cùng SQL chạy qua nhiều connection pool.

## 7. Khôi phục statistics khi gather stats gây regression

### 7.1. Kiểm tra history trước

Oracle có thể giữ lịch sử statistics và hỗ trợ restore về thời điểm trước. Trước khi restore:

1. Xác định chính xác table/partition/index liên quan.
2. Ghi nhận `LAST_ANALYZED`, histogram, NDV, num_rows và plan hiện tại.
3. Tìm thời điểm trước thay đổi được cho là gây regression.
4. Xác nhận stats history còn sẵn và chọn đúng timestamp.
5. Thử trên môi trường test hoặc pending statistics nếu có thể.
6. Đánh giá tác động lên các SQL khác dùng cùng object.

Restore table stats có thể ảnh hưởng nhiều SQL khác cùng truy cập bảng. Không nên rollback statistics chỉ vì một query chậm nếu stats mới phản ánh dữ liệu thật tốt hơn và query cần sửa ở chỗ khác.

### 7.2. Restore table statistics

Ví dụ khôi phục stats của một bảng về thời điểm trước:

```sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname       => 'APP',
        tabname       => 'ORDERS',
        as_of_timestamp => TO_TIMESTAMP_TZ(
            '2026-11-14 09:00:00 +07:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        ),
        force         => TRUE,
        no_invalidate => FALSE
    );
END;
/
```

Timestamp chỉ là ví dụ; dùng thời điểm thực tế nằm trong stats history và timezone đúng. `NO_INVALIDATE => FALSE` yêu cầu invalidation cursor theo hành vi của API, giúp cursor được parse lại với statistics được restore. Việc invalidation có thể ảnh hưởng tải parse; hãy chọn thời điểm và phạm vi phù hợp.

Tên tham số, quyền và cách restore partition/global stats cần xác nhận theo phiên bản Oracle. `FORCE => TRUE` có thể cần thiết nếu stats bị lock; không bật tùy tiện để vượt qua chính sách khóa. Restore statistics không hoàn tác dữ liệu bảng, index hoặc DDL; nó chỉ khôi phục metadata optimizer statistics.

### 7.3. Sau khi restore

- Xác nhận `LAST_ANALYZED` và statistics đã về đúng thời điểm.
- Xem plan mới trong cursor sau khi invalidation/reparse.
- Chạy với nhiều bind value đại diện.
- Đo elapsed, CPU, buffers, reads và application latency.
- Theo dõi các SQL khác dùng cùng bảng để phát hiện regression mới.
- Ghi nhận quyết định và kế hoạch gather stats lại sau khi xử lý nguyên nhân.

Không dùng `ALTER SYSTEM FLUSH SHARED_POOL` như bước mặc định. Flush toàn shared pool có thể gây hard parse hàng loạt và ảnh hưởng toàn database. Nếu cần làm mới cursor, ưu tiên cơ chế invalidation có phạm vi hoặc thao tác được DBA phê duyệt.

## 8. SQL Plan Management và kiểm soát plan

### 8.1. SQL Plan Baseline là gì?

SQL Plan Management (SPM) cho phép ghi nhận và quản lý các execution plan được chấp nhận cho SQL. Khi optimizer tạo plan mới, baseline có thể giúp kiểm soát việc sử dụng plan đã được xác nhận thay vì tự động chuyển sang một plan chưa được đánh giá.

SPM hữu ích khi:

- Một plan trước đây đã được chứng minh tốt.
- Regression xuất hiện sau statistics refresh hoặc thay đổi môi trường.
- Cần triển khai thay đổi có kiểm soát và quan sát plan mới trước khi chấp nhận.
- Muốn giảm rủi ro plan thay đổi ngoài dự kiến trong workload quan trọng.

Baseline không làm cho SQL luôn nhanh. Một plan cũ có thể trở nên kém khi dữ liệu tăng hoặc phân bố thay đổi; plan baseline cũng cần được theo dõi và tiến hóa theo workload.

### 8.2. Nạp plan tốt từ cursor cache

Nếu đã xác định cursor/plan tốt còn trong shared pool, có thể nạp vào SQL Management Base bằng `DBMS_SPM`:

```sql
DECLARE
    l_loaded_plans PLS_INTEGER;
BEGIN
    l_loaded_plans := DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(
        sql_id          => '4abc123def456',
        plan_hash_value => 1234567890
    );
    DBMS_OUTPUT.PUT_LINE('Plans loaded: ' || l_loaded_plans);
END;
/
```

Thay SQL_ID và plan hash bằng giá trị thực tế. Cần xác nhận plan là plan đã được đo và phù hợp với bind distribution cần bảo vệ. Chỉ nạp baseline không có nghĩa mọi execution lập tức dùng nó; kiểm tra `DBA_SQL_PLAN_BASELINES`, trạng thái enabled/accepted/fixed và plan thực tế sau đó.

### 8.3. Kiểm tra SQL Plan Baseline

```sql
SELECT sql_handle,
       plan_name,
       enabled,
       accepted,
       fixed,
       reproduced,
       created,
       last_executed
FROM dba_sql_plan_baselines
WHERE sql_text LIKE '%FROM app.orders%'
ORDER BY created DESC;
```

SQL text filter chỉ là ví dụ và có thể khớp nhiều câu lệnh. Trong vận hành, dùng SQL handle/SQL text đã xác định và bảo vệ nội dung SQL. `REPRODUCED`/các cột khác có thể phản ánh trạng thái plan theo version; xem data dictionary đúng phiên bản.

### 8.4. Chấp nhận hoặc evolve plan mới

Một plan mới có thể tốt hơn với dữ liệu mới. Đừng cố định plan cũ mãi mãi. Dùng quy trình thử nghiệm/evolve phù hợp để so sánh hiệu năng, bind value và workload trước khi chấp nhận plan mới. Theo dõi sau khi evolve để có thể quay về baseline đã biết nếu regression.

### 8.5. SQL Profile, SQL Patch và hint

SQL Profile có thể cung cấp thông tin hỗ trợ optimizer ước tính cardinality; SQL Patch có thể áp dụng hint ở cấp SQL trong một số trường hợp. Đây là công cụ DBA nâng cao, cần hiểu nguyên nhân và phiên bản. SQL Tuning Advisor/SQL Tuning Set và một số tính năng quản trị liên quan có yêu cầu license Oracle Tuning Pack/Diagnostics Pack; kiểm tra quyền sử dụng trước khi dùng.

Không tạo SQL Profile/Patch chỉ để ép một plan hash mà không xác nhận bind distribution và tác động lên các execution khác. Nếu SQL sai do bind datatype hoặc predicate, sửa ứng dụng/SQL thường bền vững hơn việc thêm hint.

## 9. Quy trình xử lý sự cố từng bước

### Bước 1: Xác nhận phạm vi

Xác định query, người dùng, service, module, thời điểm, p95/p99 và mức độ ảnh hưởng. Kiểm tra có phải toàn database chậm hay chỉ một SQL/bind group.

### Bước 2: Thu SQL_ID và child cursor

Ghi SQL text, SQL_ID, child number, plan hash, optimizer environment hash, executions, elapsed/CPU, buffers, reads và bind-sensitive/aware state. Lưu bằng chứng trước khi cursor bị aging out.

### Bước 3: Xem runtime plan

Dùng `DBMS_XPLAN.DISPLAY_CURSOR` cho child chậm. Thu runtime stats nếu có thể; đọc E-Rows/A-Rows, Starts, buffers, reads, predicates, partition pruning, sort/hash/TEMP và outline.

### Bước 4: So sánh plan tốt và plan chậm

Tìm plan hash trước/sau, so operation, join order, access path và cardinality. Nếu plan hash không đổi, tìm nguyên nhân khác như cache, I/O, lock, CPU, concurrency hoặc data volume.

### Bước 5: Kiểm tra statistics

Đối chiếu `LAST_ANALYZED`, stale stats, histogram, NDV, index stats và partition stats. Xem stats history và thời điểm gather. Kiểm tra stats lock, pending stats và automatic stats task.

### Bước 6: Kiểm tra bind và child cursor

So sánh bind datatype/length, peeked binds, captured binds và `IS_BIND_SENSITIVE`/`IS_BIND_AWARE`. Kiểm tra `V$SQL_SHARED_CURSOR` để hiểu child cursor không share được. Chạy thử với bind value phổ biến và hiếm.

### Bước 7: Kiểm tra thay đổi môi trường

Xem DDL, index, partition maintenance, optimizer parameters, session NLS, JDBC/ORM version, deploy và patch. So sánh `OPTIMIZER_ENV_HASH_VALUE` và session setting.

### Bước 8: Chọn biện pháp có phạm vi

Tùy nguyên nhân, có thể:

- Sửa bind datatype hoặc SQL predicate.
- Thu thập/điều chỉnh statistics có mục tiêu.
- Dùng pending stats để thử trước khi publish.
- Restore statistics nếu có bằng chứng rõ và stats history phù hợp.
- Dùng SQL Plan Baseline để tạm bảo vệ plan đã xác nhận.
- Sửa index/partition/SQL sau khi đo và thử trên môi trường tương đương.

### Bước 9: Đo lại và theo dõi

Chạy cùng workload, bind distribution và cache condition. So p50/p95/p99, throughput, error rate, CPU, buffers, reads, TEMP và tác động lên DML. Theo dõi qua ít nhất một chu kỳ tải đại diện.

## 10. Các nguyên nhân khác dễ bị nhầm với plan regression

### 10.1. Blocking và lock contention

Query có thể chờ transaction khác dù plan không đổi. Kiểm tra `V$SESSION`, `BLOCKING_SESSION`, wait event và transaction dài. Nếu elapsed tăng nhưng CPU time thấp, wait có thể là nguyên nhân.

### 10.2. Cache lạnh hoặc storage latency

Sau restart, failover hoặc workload thay đổi, buffer cache có thể chưa nóng. Physical reads tăng và query chậm dù plan hash không đổi. So sánh reads, I/O latency và trạng thái cache; đo cold và warm riêng.

### 10.3. Data growth và clustering factor

Bảng tăng số dòng hoặc dữ liệu được chèn theo thứ tự khác có thể làm index clustering factor xấu đi. Plan trước đây phù hợp có thể trở nên đắt khi phải truy cập nhiều block rải rác.

### 10.4. Index unusable/invisible hoặc partition issue

Index có thể bị unusable, invisible hoặc partition index không hợp lệ sau maintenance. Kiểm tra `DBA_INDEXES`, `DBA_IND_PARTITIONS`, `DBA_IND_SUBPARTITIONS` và partition pruning.

### 10.5. Connection pool và network

API latency có thể tăng vì pool cạn, connection creation chậm, network round trip hoặc fetch nhiều dòng. Đo riêng thời gian lấy connection, execute, fetch và xử lý ứng dụng.

### 10.6. Parse storm và SQL text thay đổi

Nếu ứng dụng nối literal, SQL text khác nhau theo từng request có thể làm tăng hard parse và shared pool pressure. Dùng bind variable đúng kiểu và kiểm tra `VERSION_COUNT`, child cursor, parse calls và số lượng SQL text tương tự.

## 11. Những thao tác không nên làm theo phản xạ

- Không gather stats toàn schema chỉ vì một query chậm.
- Không flush shared pool hoặc buffer cache trên production để “làm mới plan”.
- Không tạo index trước khi xem actual plan, cardinality và workload DML.
- Không ép `FULL` hoặc `INDEX` hint khi chưa thử nhiều bind value.
- Không restore stats cũ mà chưa đánh giá ảnh hưởng tới các SQL khác dùng cùng bảng.
- Không xóa child cursor hoặc kill session chỉ để làm sạch triệu chứng.
- Không giả định mọi child cursor khác nhau đều là lỗi; ACS có thể chủ động tạo plan khác nhau cho bind group.
- Không xem `PEEKED_BINDS` là giá trị của execution chậm gần nhất.
- Không dùng AWR/ASH/SQL Tuning Advisor nếu tổ chức không có quyền/license phù hợp.
- Không ghi bind value nhạy cảm vào ticket, log hoặc báo cáo chia sẻ rộng.

## 12. Runbook mẫu cho một query regression

### Thu thập ban đầu

1. Ghi thời điểm, service, module/action, endpoint và ảnh hưởng người dùng.
2. Lấy SQL_ID, child number, plan hash và bind group.
3. Lưu SQL text và output `DBMS_XPLAN.DISPLAY_CURSOR`.
4. Ghi executions, elapsed/exec, CPU/exec, buffers/exec, reads/exec và rows processed.
5. Xác nhận query có đang chờ lock, I/O hoặc network không.

### Kiểm tra thay đổi gần nhất

1. Xem `LAST_ANALYZED`, stale stats, histogram và stats history của table/index liên quan.
2. Xem child cursor, bind mismatch và optimizer environment.
3. Kiểm tra DDL, index status, partition maintenance và application deploy.
4. Nếu có AWR/ASH license phù hợp, so sánh SQL plan/performance giữa snapshot trước và sau.

### Khắc phục và xác nhận

1. Chọn thay đổi nhỏ nhất khớp nguyên nhân đã chứng minh.
2. Thử trên môi trường test hoặc dùng pending stats khi phù hợp.
3. Nếu cần, restore stats có phạm vi hoặc bảo vệ plan tốt bằng SPM.
4. Đo lại với bind distribution và concurrency đại diện.
5. Theo dõi SQL, workload liên quan và các query khác dùng cùng object.
6. Lưu plan, số liệu trước/sau, quyết định và thời điểm hoàn tất.

## 13. Mẫu báo cáo nguyên nhân gốc

Một báo cáo điều tra nên ghi:

| Trường | Nội dung |
|---|---|
| Incident | Thời điểm bắt đầu, service, module, mức ảnh hưởng. |
| SQL | SQL_ID, SQL text đã làm sạch, child number, bind type/group. |
| Plan trước | Plan hash, operation, E-Rows/A-Rows, buffers, reads, elapsed. |
| Plan sau | Plan hash, operation, E-Rows/A-Rows, buffers, reads, elapsed. |
| Statistics | Table/column/index stats, histogram, last analyzed, history timestamp. |
| Bind | Bind-sensitive/aware, peeked bind, child cursor reasons, datatype. |
| Environment | Optimizer env hash, parameter/session setting, version/patch. |
| Root cause | Bằng chứng cụ thể và mối liên hệ với thời điểm regression. |
| Remediation | Thay đổi đã thực hiện, phạm vi và rollback method. |
| Validation | Workload, bind distribution, p95/p99, CPU, buffers, reads, error rate. |
| Follow-up | Monitoring, owner, thời gian theo dõi và điều kiện đóng incident. |

Không đưa password, token, dữ liệu khách hàng hoặc bind value nhạy cảm vào báo cáo. Dùng định danh đã mask và lưu tài liệu ở vị trí có quyền truy cập phù hợp.

## 14. Nguyên tắc cần nhớ

- Xác định đúng SQL_ID, child cursor và plan thực tế trước khi thay đổi database.
- So sánh metric trên mỗi execution; bộ đếm trong cursor thường là số tích lũy.
- Dùng `DBMS_XPLAN.DISPLAY_CURSOR` để xem plan cursor, không chỉ dựa vào `EXPLAIN PLAN`.
- So `E-Rows` với `A-Rows`, đồng thời xem `Starts`, buffers, reads, predicates và TEMP.
- Kiểm tra statistics, histogram, skew, partition/global stats và thời điểm gather.
- Bind peeking có thể khiến plan ban đầu phụ thuộc giá trị bind lúc hard parse.
- Adaptive Cursor Sharing có thể tạo nhiều child cursor/plan cho các bind group khác nhau.
- Bind đúng datatype và kiểm tra implicit conversion.
- Dùng stats history/pending stats để thử hoặc restore có mục tiêu khi có bằng chứng.
- SQL Plan Baseline có thể bảo vệ plan đã được xác nhận nhưng cần theo dõi theo workload mới.
- Plan hash không đổi không loại trừ vấn đề cache, I/O, lock, CPU hoặc concurrency.
- Không flush shared pool, gather toàn schema hoặc ép hint theo phản xạ.
- Kiểm tra license trước khi dùng AWR/ASH, SQL Monitor hoặc SQL Tuning Advisor.
- Đo lại với dữ liệu, bind distribution, concurrency và warm-up đại diện.

## Kết luận

Truy vấn chậm đột ngột cần được điều tra bằng bằng chứng của cursor và workload thực tế. Statistics có thể làm optimizer ước tính cardinality khác và chọn plan mới; bind peeking cùng dữ liệu skew có thể khiến một SQL cần nhiều child cursor/plan; còn thay đổi object hoặc optimizer environment có thể làm cursor bị invalidation hay không share được. DBA nên bắt đầu bằng SQL_ID, child number, plan hash và runtime statistics, sau đó đối chiếu E-Rows/A-Rows, bind, histogram, stats history và thay đổi gần thời điểm sự cố. Khi nguyên nhân đã rõ, có thể thử pending stats, restore statistics có mục tiêu hoặc dùng SQL Plan Management để bảo vệ plan đã được xác nhận. Cuối cùng, chỉ coi sự cố đã được xử lý khi đo lại bằng bind distribution và tải đại diện, xác nhận p95/p99 cùng tài nguyên database, đồng thời theo dõi các SQL khác bị ảnh hưởng bởi thay đổi.
