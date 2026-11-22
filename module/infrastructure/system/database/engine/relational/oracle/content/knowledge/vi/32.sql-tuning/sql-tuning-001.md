# Quy trình đo tải, chọn SQL trọng yếu, sửa và so sánh lại trong Oracle

## 1. Tối ưu SQL bắt đầu từ workload

Tối ưu SQL không phải là sửa một câu truy vấn chỉ vì nó có nhiều JOIN, nhiều dòng code hoặc execution plan trông phức tạp. Mục tiêu là cải thiện một workload cụ thể: người dùng cần hoàn tất thao tác nhanh hơn, batch cần kết thúc đúng cửa sổ, hệ thống cần phục vụ nhiều request hơn hoặc database cần dùng ít CPU và I/O hơn.

Một quy trình tối ưu có thể chia thành năm giai đoạn:

1. **Đo tải:** thu thập số liệu trong điều kiện đại diện cho workload thực tế.
2. **Chọn SQL trọng yếu:** tìm câu SQL có tác động lớn nhất đến thời gian đáp ứng, tài nguyên hoặc nghiệp vụ.
3. **Phân tích nguyên nhân:** đọc SQL, execution plan, thống kê runtime, bind values và môi trường thực thi.
4. **Thay đổi có kiểm soát:** sửa một nhóm nguyên nhân có giả thuyết rõ ràng.
5. **Đo và so sánh lại:** xác nhận kết quả, chi phí phụ và tính đúng đắn trước khi triển khai rộng.

Không nên bắt đầu bằng việc tạo index hoặc viết lại SQL theo cảm giác. Trước hết cần biết câu SQL nào đáng sửa, đang tốn tài nguyên gì và người dùng thực sự bị ảnh hưởng ra sao.

Bài học thuộc chương **Tối ưu SQL**, tập trung vào quy trình đo tải, chọn SQL trọng yếu, sửa câu SQL và so sánh trước/sau trên Oracle Database. Nội dung bao gồm workload metrics, SQL_ID, execution plan, SQL Trace/TKPROF, V$SQL, DBMS_XPLAN, cách ưu tiên công việc, kiểm thử và triển khai an toàn.

## 2. Xác định mục tiêu và phạm vi đo

Trước khi chạy benchmark, hãy xác định kết quả nào cần cải thiện. Một câu SQL có thể nhanh hơn về elapsed time nhưng tiêu thụ CPU nhiều hơn, hoặc giảm buffer gets nhưng làm tăng thời gian commit của workload ghi.

### 2.1. Chọn chỉ số phù hợp

| Mục tiêu | Chỉ số cần theo dõi |
|---|---|
| Request người dùng phản hồi nhanh | Elapsed time, p95/p99 latency |
| Giảm tải CPU | CPU time, DB CPU, CPU per execution |
| Giảm I/O logic | Buffer gets, gets per row |
| Giảm I/O vật lý | Physical reads, read latency |
| Tăng throughput | Executions/second, rows/second, transactions/second |
| Cải thiện batch | Tổng thời gian batch, thời điểm hoàn tất |
| Giảm chi phí ghi | Redo size, write I/O, DML elapsed time |
| Giảm tranh chấp | Wait events, lock waits, concurrency |
| Giảm tài nguyên theo request | CPU, buffers, reads trên mỗi execution |

Elapsed time là thời gian trôi qua mà người gọi quan sát được. CPU time là thời gian CPU thực sự chạy cho công việc đó. Hai giá trị có thể khác xa nhau nếu SQL chờ I/O, lock, network hoặc tài nguyên khác.

### 2.2. Phân biệt latency và throughput

- **Latency:** một request mất bao lâu để hoàn thành.
- **Throughput:** hệ thống hoàn thành được bao nhiêu request trong một đơn vị thời gian.

Tối ưu một truy vấn chạy tuần tự có thể giảm latency. Nhưng dưới tải đồng thời, cùng thay đổi đó có thể tăng contention hoặc giảm throughput. Vì vậy cần đo cả hai khi hệ thống phục vụ nhiều session.

### 2.3. Chọn percentile cho workload tương tác

Không chỉ xem average. Trung bình có thể che các request chậm bất thường. Với API hoặc ứng dụng tương tác, nên theo dõi:
- p50: mức điển hình.
- p95: 95% request hoàn thành không chậm hơn giá trị này.
- p99: thể hiện phần đuôi latency.
- Maximum: hữu ích để điều tra nhưng rất nhạy với outlier.

Không gộp các nhóm request khác nhau vào một percentile duy nhất. Ví dụ truy vấn tìm kiếm, báo cáo và cập nhật đơn hàng có SLA khác nhau nên cần phân nhóm.

## 3. Thiết kế một lần đo có thể so sánh

Một phép đo chỉ có giá trị khi biết nó được thực hiện trong điều kiện nào.

### 3.1. Ghi lại môi trường

Trước khi đo, lưu các thông tin:
- Oracle Database version và Release Update.
- Edition, cấu hình instance và số node nếu dùng RAC.
- CPU, RAM, storage và cấu hình I/O.
- Database parameters liên quan optimizer.
- Schema, indexes, partitions và statistics.
- Dữ liệu thử nghiệm và phân bố giá trị.
- Bind values hoặc nhóm bind đại diện.
- Số session đồng thời.
- Module, action và service name.
- Thời điểm đo và trạng thái hệ thống.

Một thay đổi SQL được đo trên máy ít tải không thể tự động chứng minh sẽ cải thiện production khi có nhiều session cùng truy cập.

### 3.2. Dùng cùng dữ liệu và cùng điều kiện

Khi so sánh phiên bản cũ và mới:
- Cùng tập dữ liệu hoặc snapshot tương đương.
- Cùng điều kiện lọc và bind values.
- Cùng transaction boundary.
- Cùng số session đồng thời.
- Cùng trạng thái cache hoặc ghi rõ trạng thái khác nhau.
- Cùng cấu hình database nếu mục tiêu là so sánh riêng câu SQL.
- Cùng cách đo và thời lượng workload.

Nếu dữ liệu thay đổi đáng kể giữa hai lần chạy, kết quả có thể phản ánh phân bố dữ liệu khác nhau thay vì chất lượng SQL.

### 3.3. Warm cache và cold cache

Lần chạy đầu có thể phải đọc block từ storage; các lần sau có thể đọc từ buffer cache. Vì vậy:
- Đo warm-cache khi workload thực tế thường lặp lại cùng dữ liệu.
- Đo cold-cache chỉ trong môi trường thử nghiệm có kiểm soát và khi mục tiêu cần đánh giá I/O lạnh.
- Không xóa buffer cache trên production để tạo benchmark.
- Ghi rõ số lần warm-up và cách chọn kết quả.

Không lấy lần chạy nhanh nhất trong nhiều lần đo làm kết luận. Hãy dùng median và percentile hoặc thống kê đủ số lần lặp.

### 3.4. Tránh benchmark chỉ một session khi production chạy đồng thời

Một index có thể làm một session nhanh hơn nhưng khiến nhiều session cùng cập nhật index bị tranh chấp. Một truy vấn đọc nhanh hơn có thể tăng CPU đủ nhiều để làm chậm workload khác.

Nên có hai cấp đo:
1. **Microbenchmark:** cô lập câu SQL để hiểu access path và chi phí mỗi lần thực thi.
2. **Workload test:** chạy cùng các request đại diện với concurrency gần thực tế để xác nhận tác động toàn hệ thống.

## 4. Thu thập dữ liệu tải ở cấp database

Oracle cung cấp nhiều nguồn số liệu. Chọn công cụ theo quyền, phiên bản, chính sách license và mức độ cần thiết.

### 4.1. V$SQL: thống kê câu SQL trong shared pool

`V$SQL` hiển thị các cursor SQL đang được lưu trong shared SQL area, cùng thống kê thực thi tích lũy. Một số cột hữu ích:

| Cột | Ý nghĩa |
|---|---|
| `SQL_ID` | Định danh SQL statement |
| `CHILD_NUMBER` | Child cursor |
| `PLAN_HASH_VALUE` | Giá trị nhận diện plan hash |
| `EXECUTIONS` | Số lần thực thi |
| `ELAPSED_TIME` | Tổng elapsed time, đơn vị microsecond |
| `CPU_TIME` | Tổng CPU time, đơn vị microsecond |
| `BUFFER_GETS` | Logical reads |
| `DISK_READS` | Physical reads được ghi nhận |
| `ROWS_PROCESSED` | Số hàng xử lý |
| `PARSE_CALLS` | Số lần parse call |
| `MODULE`, `ACTION` | Ngữ cảnh ứng dụng nếu được thiết lập |
| `LAST_ACTIVE_TIME` | Thời điểm hoạt động gần nhất |

Ví dụ tìm SQL tiêu thụ tổng elapsed time cao:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 2) AS cpu_seconds,
       buffer_gets,
       disk_reads,
       rows_processed,
       module,
       action,
       last_active_time
FROM v$sql
WHERE executions > 0
ORDER BY elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
```

Đây là thống kê tích lũy trong vòng đời cursor hiện diện ở shared pool, không phải báo cáo riêng cho một khoảng thời gian cố định. Cursor có thể bị aged out hoặc load lại; số liệu có thể reset khi instance restart hoặc cursor được nạp lại.

### 4.2. Đừng xếp hạng chỉ theo elapsed time tổng

Một SQL có tổng elapsed cao có thể chỉ chạy một lần trong báo cáo. Một SQL khác có elapsed mỗi lần nhỏ nhưng chạy hàng trăm nghìn lần và làm tổng tải lớn.

Tính các chỉ số trung bình:

```sql
SELECT sql_id,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS total_elapsed_s,
       ROUND(elapsed_time / GREATEST(executions, 1) / 1e6, 6)
           AS elapsed_s_per_exec,
       ROUND(cpu_time / GREATEST(executions, 1) / 1e6, 6)
           AS cpu_s_per_exec,
       ROUND(buffer_gets / GREATEST(executions, 1), 1)
           AS gets_per_exec,
       ROUND(rows_processed / GREATEST(executions, 1), 1)
           AS rows_per_exec
FROM v$sql
WHERE executions > 0
ORDER BY elapsed_time DESC;
```

Các số trung bình giúp hiểu chi phí mỗi lần gọi, nhưng có thể che biến động do bind values hoặc child cursor. Nếu workload có nhiều nhóm tham số, cần phân tích riêng.

### 4.3. Lấy delta thay vì chỉ đọc số tích lũy

Nếu muốn đo một khoảng thử nghiệm:
1. Lấy snapshot thống kê trước.
2. Chạy workload trong khoảng đã định.
3. Lấy snapshot sau.
4. Tính delta giữa hai lần.

Có thể lưu số liệu từ `V$SQL` vào bảng lab hoặc file bên ngoài. Khi so sánh, dùng `SQL_ID` và `CHILD_NUMBER`/`PLAN_HASH_VALUE` phù hợp; nếu cursor biến mất giữa hai snapshot, cần ghi nhận thay vì giả định delta hợp lệ.

### 4.4. Xem SQL theo module/action

Ứng dụng nên thiết lập module và action để DBA biết câu SQL thuộc chức năng nào:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'SEARCH_ORDERS'
    );
END;
/
```

Sau khi hoàn tất tác vụ, ứng dụng có thể đổi action hoặc reset module theo quy ước kết nối. Với connection pool, cần thiết lập ngữ cảnh đúng cho mỗi request để không gắn nhầm SQL của request trước.

Có thể xem trong `V$SQL.MODULE` và `V$SQL.ACTION`, hoặc các view session/workload liên quan.

### 4.5. V$SQL không phải lịch sử đầy đủ

`V$SQL` chỉ phản ánh cursor còn trong shared pool và thống kê gắn với cursor đó. Nó không thay thế hệ thống lịch sử workload. Với khoảng thời gian dài, cần nguồn lưu lịch sử như AWR hoặc Statspack, theo quyền và license phù hợp.

## 5. AWR, ASH và Statspack

### 5.1. AWR

Automatic Workload Repository (AWR) lưu snapshot thống kê workload để phân tích xu hướng và so sánh các khoảng thời gian. Báo cáo AWR có thể giúp xác định:
- DB time và DB CPU.
- Top SQL theo elapsed, CPU, buffer gets hoặc reads.
- Wait events nổi bật.
- Load profile.
- SQL execution và plan statistics.
- Thay đổi workload giữa hai snapshot.

AWR là công cụ hữu ích cho hệ thống có tải dài hạn, nhưng việc sử dụng AWR và các tính năng liên quan có điều kiện license theo Oracle. Hãy kiểm tra Oracle Licensing Information User Manual và hợp đồng hiện hành trước khi sử dụng.

### 5.2. ASH

Active Session History (ASH) lấy mẫu trạng thái session đang hoạt động, giúp thấy session đang chạy SQL nào và đang chờ sự kiện gì. Nó hỗ trợ điều tra:
- SQL_ID gây tải trong thời điểm cụ thể.
- Session chờ I/O, lock hoặc CPU.
- Module/action.
- Blocking session và chuỗi chờ trong phạm vi dữ liệu được ghi nhận.

ASH/AWR và các báo cáo dựa trên chúng thuộc nhóm tính năng cần xác nhận license phù hợp. Không dùng view hoặc report chỉ vì tài khoản có quyền truy cập.

### 5.3. Statspack

Statspack là lựa chọn thu thập và so sánh thống kê hiệu năng theo snapshot, thường được dùng khi không có quyền sử dụng AWR hoặc theo chính sách hệ thống. Cần cài đặt, cấu hình snapshot và quản lý dữ liệu Statspack theo hướng dẫn Oracle cho phiên bản.

Statspack không có toàn bộ khả năng và chi tiết như AWR/ASH, nhưng có thể hỗ trợ xác định workload và xu hướng tải.

### 5.4. Chọn công cụ

| Nhu cầu | Công cụ gợi ý |
|---|---|
| Xem cursor hiện tại và thống kê tích lũy | `V$SQL`, `V$SQLAREA` |
| Đo một câu SQL cụ thể | SQL Trace + TKPROF |
| Xem runtime plan của cursor | `DBMS_XPLAN.DISPLAY_CURSOR` |
| Phân tích lịch sử workload | AWR nếu có license; Statspack theo chính sách |
| Phân tích session đang hoạt động | ASH nếu có license; session/wait views phù hợp |
| Phân tích thời gian PL/SQL | `DBMS_HPROF` hoặc profiler phù hợp |
| Theo dõi SQL dài đang chạy | SQL Monitor nếu được cấp phép và hỗ trợ |

## 6. Chọn SQL trọng yếu: ưu tiên theo tác động

Sau khi thu thập số liệu, không nhất thiết sửa SQL đứng đầu một bảng xếp hạng. Cần kết hợp chi phí kỹ thuật với mức độ ảnh hưởng đến nghiệp vụ.

### 6.1. Các tiêu chí ưu tiên

- Tổng DB time/elapsed time tiêu thụ.
- Tổng CPU time.
- Buffer gets và physical reads.
- Số lần thực thi.
- Chi phí trung bình mỗi execution.
- p95/p99 latency nếu có số liệu.
- Thời điểm chạy và mức độ ảnh hưởng đến batch.
- Số người dùng hoặc dịch vụ bị ảnh hưởng.
- Tầm quan trọng của chức năng.
- Mức độ rủi ro và công sức sửa.

### 6.2. Ví dụ bảng xếp hạng

| SQL | Executions | Total elapsed | Elapsed/exec | Gets/exec | Ảnh hưởng |
|---|---:|---:|---:|---:|---|
| SQL A | 2.000 | 900 s | 0,45 s | 80.000 | Báo cáo chạy theo lịch |
| SQL B | 500.000 | 600 s | 0,0012 s | 35 | API gọi liên tục |
| SQL C | 10 | 300 s | 30 s | 2.000.000 | Báo cáo chậm |
| SQL D | 100.000 | 120 s | 0,0012 s | 20 | Ít ảnh hưởng |

Số liệu chỉ minh họa. SQL A có tổng elapsed cao nhất; SQL B có thể đáng ưu tiên vì mỗi lần gọi rất thường xuyên. SQL C có thể ảnh hưởng lớn đến một nhóm người dùng hoặc cửa sổ batch. Quyết định phụ thuộc SLA và mức độ quan trọng nghiệp vụ.

### 6.3. Ma trận ưu tiên

Có thể chấm điểm theo các chiều:
- **Impact:** ảnh hưởng người dùng/batch.
- **Cost:** tổng tài nguyên SQL tiêu thụ.
- **Frequency:** tần suất chạy.
- **Confidence:** mức chắc chắn về nguyên nhân và giải pháp.
- **Risk:** nguy cơ thay đổi làm sai kết quả hoặc ảnh hưởng workload khác.

Không nên cộng điểm một cách máy móc. Hãy dùng ma trận để giải thích vì sao chọn một SQL, và ghi lại lý do để nhóm có thể xem xét lại.

### 6.4. Chọn SQL theo nghiệp vụ, không chỉ theo SQL_ID

SQL_ID giúp nhận diện câu SQL trong Oracle, nhưng người dùng hiểu chức năng như “tìm đơn hàng”, “tính tồn kho” hoặc “đóng kỳ”. Kết hợp module/action, service, schema và log ứng dụng để liên kết SQL với nghiệp vụ.

Nếu một chức năng phát sinh nhiều SQL_ID khác nhau do literal values, xem xét bind variables và cách ứng dụng sinh SQL.

## 7. Phân tích SQL_ID và child cursor

Một SQL statement có thể có nhiều child cursor do khác biệt môi trường, bind metadata, optimizer environment, object resolution hoặc adaptive cursor sharing.

### 7.1. Xem các child cursor

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       loads,
       invalidations,
       is_bind_sensitive,
       is_bind_aware
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Nếu cùng SQL_ID có nhiều child cursor với plan hash khác nhau, cần xác định lý do. Không kết luận nhiều child cursor luôn là lỗi; Oracle có thể cần nhiều plan cho các nhóm bind values khác nhau.

### 7.2. Xem SQL text

```sql
SELECT sql_id,
       child_number,
       sql_fulltext
FROM v$sql
WHERE sql_id = :sql_id;
```

SQL text có thể dài; dùng `SQL_FULLTEXT` hoặc `V$SQL.SQL_TEXT` theo nhu cầu. Không đưa literal chứa thông tin nhạy cảm vào tài liệu hoặc log không kiểm soát.

### 7.3. Bind values

Bind variable giúp tái sử dụng cursor và giảm hard parse, nhưng phân bố dữ liệu có thể khiến một plan không tốt cho mọi giá trị. `V$SQL_BIND_CAPTURE` chỉ thu thập bind theo cơ chế lấy mẫu, không bảo đảm lưu mọi lần chạy hoặc mọi giá trị. Không dùng nó như bản ghi đầy đủ của tất cả bind values.

Đối với benchmark, ghi rõ nhóm bind đại diện ở tầng ứng dụng hoặc harness thử nghiệm, đồng thời bảo vệ dữ liệu nhạy cảm.

### 7.4. SQL_ID và PLAN_HASH_VALUE

- `SQL_ID` nhận diện statement.
- `PLAN_HASH_VALUE` giúp so sánh hình dạng execution plan.
- Cùng SQL_ID có thể có plan khác nhau theo child cursor.
- Cùng plan hash không bảo đảm runtime giống nhau vì dữ liệu, cache, bind, concurrency và hệ thống khác nhau.

## 8. Đọc execution plan đúng cách

Execution plan cho biết Oracle dự định hoặc đã thực hiện truy vấn qua các operation nào. Đừng chỉ nhìn xem có dùng index hay không.

### 8.1. EXPLAIN PLAN

```sql
EXPLAIN PLAN FOR
SELECT order_id, customer_id, order_date
FROM orders
WHERE customer_id = 1001
  AND order_date >= DATE '2026-01-01';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` tạo plan ước lượng cho câu SQL trong ngữ cảnh explain. Nó không nhất thiết phản ánh child cursor và runtime thực tế đã chạy.

### 8.2. DISPLAY_CURSOR

Trong session thử nghiệm, bật thu thập runtime statistics:

```sql
ALTER SESSION SET statistics_level = ALL;
```

Chạy câu SQL:

```sql
SELECT order_id, customer_id, order_date
FROM orders
WHERE customer_id = 1001
  AND order_date >= DATE '2026-01-01';
```

Sau đó:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
    )
);
```

`ALLSTATS LAST` hiển thị runtime statistics của lần thực thi gần nhất nếu đã được thu thập. Có thể bật `STATISTICS_LEVEL=ALL` trong session thử nghiệm thay vì dùng hint, theo quyền và chính sách môi trường.

### 8.3. So sánh E-Rows và A-Rows

- `E-Rows`: số hàng optimizer ước lượng.
- `A-Rows`: số hàng thực tế trong runtime plan.

Chênh lệch lớn có thể chỉ ra:
- Statistics lỗi thời hoặc không đại diện.
- Skew dữ liệu chưa được mô hình hóa.
- Predicate tương quan nhiều cột.
- Bind values có phân bố khác nhau.
- Function hoặc biểu thức làm optimizer khó ước lượng.
- Cardinality của JOIN không đúng dự đoán.

Ước lượng sai có thể dẫn đến join order hoặc join method không phù hợp.

### 8.4. Xem các operation quan trọng

| Operation | Câu hỏi cần đặt ra |
|---|---|
| TABLE ACCESS FULL | Bảng lớn hay nhỏ? Truy vấn trả bao nhiêu phần trăm hàng? |
| INDEX RANGE SCAN | Predicate có chọn lọc? Có phải truy cập table nhiều lần không? |
| INDEX UNIQUE SCAN | Điều kiện có dùng đầy đủ unique key không? |
| TABLE ACCESS BY INDEX ROWID | Số lần truy cập table và clustering factor ra sao? |
| NESTED LOOPS | Outer row count có nhỏ như optimizer dự đoán không? |
| HASH JOIN | Có đủ PGA? Có spill ra TEMP không? |
| SORT ORDER BY | Có thể tận dụng index/order hoặc giảm dữ liệu trước sort không? |
| HASH GROUP BY | Có spill TEMP hoặc xử lý tập quá lớn không? |
| PARTITION RANGE | Có partition pruning đúng không? |
| FILTER | Predicate nào đang được đánh giá lặp? |

Không mặc định full scan xấu hoặc index scan tốt. Nếu cần đọc phần lớn bảng, full scan có thể rẻ hơn nhiều lần random access qua index.

## 9. Chẩn đoán theo loại tài nguyên

### 9.1. CPU cao

Dấu hiệu:
- CPU time lớn.
- DB CPU chiếm tỷ trọng cao.
- Buffer gets hoặc số lần gọi function lớn.
- SQL chạy lâu dù physical reads không cao.

Hướng điều tra:
- Lặp biểu thức hoặc function.
- Join tạo quá nhiều hàng trung gian.
- Sort/hash lớn.
- Predicate không sargable.
- SQL bị gọi quá nhiều lần.
- PL/SQL/SQL context switch.
- Parse CPU do hard parse.

### 9.2. Buffer gets cao

Buffer gets là số lần truy cập block trong buffer cache. Một truy vấn có thể không đọc nhiều từ storage nhưng vẫn tiêu tốn CPU vì quét quá nhiều block.

Hướng điều tra:
- Full scan không cần thiết.
- Index range scan trả quá nhiều rowid.
- Nested loops lặp trên tập outer lớn.
- Thiếu composite index phù hợp.
- JOIN hoặc predicate làm phình tập dữ liệu.
- Function-based predicate khiến index không được dùng.

### 9.3. Physical reads cao

Hướng điều tra:
- Working set lớn hơn cache.
- Access path đọc nhiều block.
- Table/index scan trên segment lớn.
- Storage latency hoặc throughput.
- Cache behavior và concurrency.
- LOB hoặc table data được truy cập không cần thiết.

Physical reads không tự chứng minh SQL kém; workload có thể cần đọc lượng dữ liệu lớn theo yêu cầu.

### 9.4. Waits và blocking

Nếu elapsed time cao nhưng CPU thấp, xem wait events:
- User I/O.
- Concurrency/latch/mutex.
- Lock waits.
- Network hoặc client waits.
- Commit/log file sync.
- TEMP I/O.

Tối ưu câu SQL không giải quyết mọi wait. Ví dụ một câu UPDATE chậm vì chờ row lock cần điều tra transaction đang giữ khóa; thêm index có thể không xử lý nguyên nhân.

## 10. Các hướng sửa SQL thường gặp

Mỗi thay đổi cần gắn với một nguyên nhân đã quan sát trong plan hoặc số liệu.

### 10.1. Lọc dữ liệu sớm và tránh xử lý hàng không cần thiết

Nếu chỉ cần một nhóm dữ liệu, đưa predicate vào query phù hợp để giảm số hàng đi qua JOIN, sort và aggregate. Tránh lấy toàn bộ bảng về ứng dụng rồi lọc ở client.

### 10.2. Dùng EXISTS cho kiểm tra tồn tại

Nếu chỉ cần biết có hàng liên quan hay không, `EXISTS` thường diễn đạt trực tiếp ý định:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'OPEN'
);
```

Không JOIN toàn bộ orders rồi DISTINCT nếu chỉ cần kiểm tra sự tồn tại, trừ khi có lý do về plan hoặc kết quả.

### 10.3. Tránh function trên cột lọc nếu làm mất khả năng dùng index

Ví dụ:

```sql
SELECT order_id
FROM orders
WHERE TRUNC(order_date) = DATE '2026-03-01';
```

Một cách viết thường thân thiện với index trên `ORDER_DATE` hơn:

```sql
SELECT order_id
FROM orders
WHERE order_date >= DATE '2026-03-01'
  AND order_date <  DATE '2026-03-02';
```

Cách này giữ predicate dạng range trên cột gốc và tránh áp dụng TRUNC cho từng giá trị cột. Nếu semantics có timezone hoặc kiểu timestamp, phải xây dựng ranh giới thời gian đúng với nghiệp vụ.

### 10.4. Tránh implicit conversion

Nếu cột là NUMBER, bind giá trị NUMBER. Nếu cột là DATE, bind DATE. Không so sánh NUMBER với chuỗi hoặc DATE với chuỗi định dạng tùy môi trường.

Ví dụ tránh:

```sql
WHERE customer_id = '1001'
```

Ưu tiên:

```sql
WHERE customer_id = :customer_id
```

với bind variable có kiểu NUMBER.

Implicit conversion có thể làm thay đổi semantics, gây lỗi theo NLS settings hoặc khiến biểu thức index không được sử dụng như dự kiến.

### 10.5. Dùng bind variables

```sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id;
```

Bind variables giúp giảm hard parse khi cùng cấu trúc SQL được chạy với nhiều giá trị. Tuy nhiên, bind peeking và data skew có thể khiến một plan không phù hợp cho mọi giá trị. Hãy kiểm tra child cursor, bind sensitivity và adaptive cursor sharing trước khi thay đổi cấu hình.

### 10.6. Chọn composite index theo predicate

Nếu query thường lọc:

```sql
WHERE tenant_id = :tenant_id
  AND status = :status
  AND created_at >= :from_time
```

Có thể đánh giá index như `(tenant_id, status, created_at)`. Thứ tự cột phụ thuộc các predicate, selectivity, truy vấn khác, sort và workload DML. Không tạo index chỉ dựa vào một câu SQL mà bỏ qua các truy vấn dùng chung bảng.

### 10.7. Giảm cột và hàng đọc

Tránh `SELECT *` nếu chỉ cần một vài cột. Giảm payload có thể giảm I/O, memory, network và công việc ở client. Tuy nhiên, không thêm covering index quá rộng nếu chi phí storage/DML lớn hơn lợi ích.

### 10.8. Partition pruning

Nếu bảng partition theo ngày và query có điều kiện trên partition key, viết predicate rõ ràng để Oracle có thể loại partition không cần đọc. Kiểm tra plan có operation partition range phù hợp hay không.

### 10.9. Kiểm tra JOIN cardinality

Trước khi đổi join method, xác định:
- Mối quan hệ một-một, một-nhiều hay nhiều-nhiều.
- Có duplicate ngoài dự kiến không.
- Predicate JOIN có đầy đủ không.
- Statistics và cardinality estimate.
- Có thể lọc dữ liệu trước JOIN không.

Không thêm DISTINCT để che lỗi JOIN tạo duplicate nếu chưa hiểu nguyên nhân.

### 10.10. Tránh tối ưu sai semantics

Viết lại SQL phải giữ:
- NULL semantics.
- Duplicate rows.
- Outer join behavior.
- Timezone và date boundaries.
- Collation/NLS.
- Ordering nếu ứng dụng phụ thuộc thứ tự.
- Transaction isolation và concurrency.
- Error behavior khi dữ liệu bất thường.

SQL nhanh hơn nhưng trả kết quả khác là lỗi, không phải tối ưu.

## 11. Cách tạo và kiểm tra giả thuyết sửa đổi

Một thay đổi tốt bắt đầu bằng giả thuyết có thể kiểm chứng.

| Quan sát | Giả thuyết | Thay đổi thử |
|---|---|---|
| `TRUNC(order_date)` trong predicate | Index trên cột ngày khó được dùng trực tiếp | Chuyển thành range predicate |
| E-Rows thấp hơn A-Rows rất nhiều | Cardinality estimate sai | Kiểm tra stats/histogram và predicate correlation |
| 500.000 executions, gets/exec nhỏ | SQL bị gọi quá thường xuyên | Xem lại N+1 ở ứng dụng hoặc batch |
| Nested loops lặp hàng triệu lần | Outer row count lớn hơn dự đoán | Kiểm tra join order, filter và join method |
| Full scan nhưng chỉ cần vài hàng | Predicate không chọn lọc đúng hoặc thiếu index | Xem index phù hợp và stats |
| SQL có nhiều child plan | Bind/data distribution hoặc environment khác nhau | Phân tích child cursor và bind groups |
| Query chờ row lock | Transaction khác giữ khóa | Tìm blocker và transaction duration |

Mỗi lần chỉ thay một yếu tố quan trọng nếu có thể. Nếu cùng lúc thay index, statistics, SQL text và optimizer parameter, rất khó biết yếu tố nào tạo ra cải thiện hoặc regression.

## 12. Quy trình thử nghiệm trước/sau

### 12.1. Lưu baseline

Trước khi sửa, lưu:
- SQL text.
- SQL_ID và child number.
- Plan hash value.
- Execution plan có runtime statistics.
- Bind values đại diện (đã xử lý dữ liệu nhạy cảm).
- Executions.
- Elapsed, CPU, buffer gets, disk reads.
- Rows processed.
- Wait profile.
- Thời điểm và điều kiện đo.

### 12.2. Tạo bản thử nghiệm

Tùy thay đổi:
- Dùng schema hoặc database staging.
- Tạo index thử nghiệm.
- Dùng SQL text riêng hoặc SQL patch/test harness.
- Giữ lại phiên bản query cũ để rollback.
- Ghi rõ DDL, statistics và tham số đã thay đổi.

Không tạo index hoặc thay optimizer parameter trên production chỉ để benchmark mà chưa có phê duyệt vận hành phù hợp.

### 12.3. Chạy cùng workload

Chạy cùng bind values và concurrency. Nếu workload có nhiều nhóm giá trị, lấy mẫu đại diện:
- Giá trị phổ biến.
- Giá trị hiếm.
- Tập trả về nhỏ.
- Tập trả về lớn.
- Giá trị biên.
- Trường hợp NULL hoặc không có dữ liệu nếu nghiệp vụ cho phép.

### 12.4. So sánh plan và runtime

So sánh:
- Plan hash và operation.
- E-Rows/A-Rows.
- Starts và số vòng lặp operation.
- Buffer gets.
- Physical reads.
- CPU và elapsed.
- Waits.
- Rows returned/affected.
- DML redo và index maintenance.

Plan hash khác không có nghĩa tốt hơn. Plan hash giống cũng không bảo đảm runtime giống. Kết luận phải dựa trên kết quả thực tế.

### 12.5. Bảng benchmark

| Chỉ số | Trước sửa | Sau sửa | Chênh lệch |
|---|---:|---:|---:|
| Median elapsed | Đo | Đo | Tính |
| p95 elapsed | Đo | Đo | Tính |
| CPU per execution | Đo | Đo | Tính |
| Buffer gets per execution | Đo | Đo | Tính |
| Physical reads | Đo | Đo | Tính |
| Rows returned | Đo | Đo | Phải tương đương |
| Executions/second | Đo | Đo | Tính |
| Redo per transaction | Đo | Đo | Tính |
| Error count | Đo | Đo | Không tăng bất thường |

Phần trăm cải thiện elapsed:

\[
\text{Improvement} =
\frac{\text{Before} - \text{After}}{\text{Before}} \times 100\%
\]

Nếu giá trị âm, phiên bản sau chậm hơn. Ghi rõ mẫu số và đơn vị; không chỉ báo “nhanh hơn 30%” mà thiếu điều kiện benchmark.

## 13. SQL Trace và TKPROF cho một câu SQL cụ thể

Khi cần biết một câu SQL parse/execute/fetch bao nhiêu lần và tốn thời gian ở đâu, SQL Trace rất hữu ích.

### 13.1. Bật trace trong session thử nghiệm

```sql
ALTER SESSION SET SQL_TRACE = TRUE;

-- Chạy procedure hoặc workload cần phân tích.

ALTER SESSION SET SQL_TRACE = FALSE;
```

Hoặc dùng `DBMS_SESSION`/`DBMS_MONITOR` để trace session hoặc service theo chính sách DBA.

Trace file được ghi vào vị trí diagnostic của database server. Tên file và đường dẫn do Oracle quản lý; DBA có thể xác định bằng các view diagnostic phù hợp.

### 13.2. TKPROF

TKPROF định dạng trace file thành báo cáo dễ đọc, có thông tin:
- Parse, execute, fetch count.
- CPU và elapsed time.
- Disk reads và query/current buffer gets.
- Rows processed.
- SQL text.

Ví dụ lệnh chạy trên máy có Oracle client:

```text
tkprof input_trace.trc output_report.txt sys=no sort=exeela,fchela
```

Đường dẫn file là ví dụ. Thực thi TKPROF ở máy có công cụ Oracle phù hợp và tuân thủ chính sách bảo vệ trace/bind data.

### 13.3. Khi nào dùng trace?

- Một request cụ thể bị chậm.
- Cần tìm SQL lặp bên trong procedure.
- Muốn tách parse, execute và fetch.
- Cần xem câu SQL thực tế được phát ra.
- Muốn so sánh số lần gọi trước/sau.

Không bật trace diện rộng quá lâu vì có overhead và có thể thu thập thông tin nhạy cảm.

## 14. SQL Monitor và SQL Tuning Advisor

Một số công cụ Oracle giúp phân tích SQL sâu hơn nhưng có điều kiện phiên bản, quyền và license.

### 14.1. Real-Time SQL Monitoring

SQL Monitor có thể hiển thị tiến độ và runtime của SQL dài hoặc parallel execution, gồm các operation, thời gian, I/O và phân bố hoạt động. Khả năng tự động monitor phụ thuộc ngưỡng và cấu hình.

Real-Time SQL Monitoring thuộc tính năng cần xác nhận Oracle Tuning Pack license trong mô hình cấp phép phổ biến. Hãy kiểm tra điều khoản hiện hành trước khi sử dụng.

### 14.2. SQL Tuning Advisor

SQL Tuning Advisor có thể đưa ra khuyến nghị như statistics, SQL profile hoặc cấu trúc truy cập tùy tình huống. Đây là công cụ hỗ trợ; DBA vẫn cần đánh giá tính đúng đắn, chi phí và license.

SQL Tuning Advisor thuộc nhóm tính năng Oracle Tuning Pack theo mô hình cấp phép phổ biến. Không chạy hoặc bật tính năng chỉ vì package có sẵn mà chưa xác nhận quyền sử dụng.

### 14.3. Công cụ không thay thế hiểu workload

Advisor có thể đề xuất một index nhưng không biết đầy đủ tác động đến tất cả DML và truy vấn khác trong hệ thống. Khuyến nghị cần được benchmark trên workload tổng thể.

## 15. Kiểm tra statistics trước khi sửa SQL

Optimizer dùng statistics để ước lượng cardinality và chọn plan.

### 15.1. Table và index statistics

```sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
```

Xem index:

```sql
SELECT index_name,
       num_rows,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       last_analyzed
FROM user_ind_statistics
WHERE table_name = 'ORDERS';
```

Tên cột và view có thể khác theo quyền/phiên bản. Các số liệu này giúp hiểu optimizer đang dựa trên statistics nào.

### 15.2. Thu thập statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
```

Không chạy gather statistics tùy tiện trên production. Việc thay đổi statistics có thể làm nhiều SQL đổi plan cùng lúc. Hãy dùng chính sách statistics, kiểm tra stale stats, incremental stats và cửa sổ vận hành của hệ thống.

### 15.3. Histograms và data skew

Nếu một cột có phân bố lệch mạnh, histogram có thể giúp optimizer ước lượng tốt hơn cho các giá trị khác nhau. Tuy nhiên:
- Histogram không cần thiết cho mọi cột.
- Bind variables và bind peeking ảnh hưởng cách chọn plan.
- Adaptive cursor sharing có thể tạo child cursor theo nhóm bind.
- Statistics thay đổi có thể làm plan đổi ngoài câu SQL đang tối ưu.

Đừng tạo histogram hoặc thay `OPTIMIZER_FEATURES_ENABLE` chỉ để ép một truy vấn nhanh hơn mà chưa phân tích ảnh hưởng toàn workload.

## 16. Chọn index dựa trên workload tổng thể

Index giúp đọc nhưng làm ghi tốn hơn. Trước khi thêm index, đánh giá:
- Query nào sẽ dùng index?
- Predicate có selectivity đủ tốt?
- Index có trùng hoặc gần trùng index hiện tại?
- Cột nào đứng đầu composite index?
- Tác động INSERT/UPDATE/DELETE?
- Dung lượng và backup?
- Index có thể phục vụ nhiều query không?
- Có partition local/global và yêu cầu pruning?
- Clustering factor có phù hợp?

Một index chỉ giúp một SQL nhưng làm mọi DML trên bảng chậm hơn có thể không phải lựa chọn tốt cho workload.

### 16.1. Kiểm tra index hiện có

```sql
SELECT index_name,
       column_name,
       column_position,
       descend
FROM user_ind_columns
WHERE table_name = 'ORDERS'
ORDER BY index_name, column_position;
```

Kiểm tra thêm uniqueness, status, visibility và partition metadata trước khi tạo index mới.

### 16.2. Invisible index để thử nghiệm

Oracle hỗ trợ invisible index trong các phiên bản tương ứng. Có thể tạo index invisible để kiểm tra một số kịch bản optimizer với `OPTIMIZER_USE_INVISIBLE_INDEXES` ở session thử nghiệm. Invisible index vẫn được duy trì bởi DML và vẫn tốn storage; nó không miễn phí.

Không dùng invisible index như cách né đánh giá chi phí ghi hoặc license. Xác nhận cú pháp và hành vi theo release trước khi triển khai.

## 17. Kiểm soát thay đổi và khả năng quay lui

Một thay đổi SQL có thể tác động đến nhiều chức năng cùng dùng bảng hoặc view. Vì vậy cần quản lý như một thay đổi kỹ thuật có thể kiểm chứng.

### 17.1. Ghi change record

Mỗi thay đổi nên có:
- SQL_ID/SQL text hoặc chức năng liên quan.
- Vấn đề và số liệu baseline.
- Giả thuyết nguyên nhân.
- Nội dung sửa.
- Index/statistics/parameter thay đổi.
- Kết quả trước/sau.
- Các bind groups đã thử.
- Rủi ro và phạm vi ảnh hưởng.
- Kế hoạch rollback.
- Người phê duyệt và thời điểm triển khai theo quy trình nhóm.

### 17.2. Chỉ thay một nhóm yếu tố có thể giải thích

Nếu cùng lúc thay SQL text, index, statistics và optimizer parameter, rất khó quy kết nguyên nhân cải thiện. Tách thay đổi giúp:
- Hiểu yếu tố nào tạo ra hiệu quả.
- Phát hiện regression.
- Quay lui chính xác.
- Duy trì tri thức kỹ thuật.

### 17.3. Kiểm tra tính đúng đắn

So sánh kết quả trước/sau:
- Số hàng trả về.
- Nội dung và kiểu dữ liệu.
- Duplicate.
- NULL.
- Thứ tự nếu có `ORDER BY` và ứng dụng phụ thuộc.
- Kết quả với bind values khác nhau.
- Transaction và locking.
- Error behavior.

Có thể dùng `MINUS` hai chiều trên tập kết quả phù hợp để so sánh, nhưng cần lưu ý kiểu dữ liệu LOB, thứ tự và semantics của phép so sánh. Với dữ liệu lớn, xây dựng checksum hoặc kiểm thử theo khóa nghiệp vụ.

### 17.4. Kế hoạch rollback

- Giữ lại SQL cũ.
- Biết cách drop/disable index thử nghiệm nếu cần.
- Lưu trạng thái statistics hoặc dùng cơ chế restore statistics theo chính sách.
- Không xóa index cũ ngay sau deploy nếu chưa qua thời gian quan sát.
- Xác định ngưỡng rollback như p95 tăng, CPU tăng hoặc lỗi tăng.
- Có người chịu trách nhiệm theo dõi sau triển khai.

## 18. Đo lại dưới tải thật và quan sát regression

Một truy vấn nhanh hơn trong staging chưa đủ. Sau triển khai cần quan sát:
- p50/p95/p99 latency.
- Throughput.
- DB CPU và host CPU.
- Buffer gets và physical reads.
- Wait events.
- Parse rate và child cursor.
- DML latency trên bảng có index mới.
- TEMP và PGA nếu thay join/sort.
- Error rate và kết quả nghiệp vụ.
- Các SQL khác cùng bảng hoặc cùng service.

Một thay đổi có thể cải thiện SQL mục tiêu nhưng làm chậm một nhóm truy vấn khác. Hãy theo dõi cả workload liên quan.

### 18.1. Đặt ngưỡng chấp nhận

Ví dụ quy ước dự án:
- p95 giảm ít nhất 20%.
- CPU mỗi execution không tăng quá ngưỡng đã thống nhất.
- Rows returned phải giống.
- Không tăng lỗi.
- DML throughput không giảm quá giới hạn.
- Không làm batch khác trễ SLA.

Các ngưỡng này là ví dụ; đội dự án phải định nghĩa theo SLA và năng lực hệ thống.

### 18.2. Đừng giữ tối ưu chỉ vì một chỉ số đẹp

Nếu elapsed giảm nhưng CPU tăng gấp đôi và throughput tổng giảm, thay đổi có thể không tốt. Nếu buffer gets giảm nhưng latency người dùng không thay đổi vì chờ lock, cần xử lý đúng nguyên nhân. Chọn theo mục tiêu hệ thống chứ không theo một con số đơn lẻ.

## 19. Quy trình thực hành từ đầu đến cuối

Giả sử API tìm đơn hàng bị chậm trong giờ cao điểm.

### Bước 1. Gắn module/action

Ứng dụng hoặc session thử nghiệm thiết lập:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'SEARCH_ORDERS'
    );
END;
/
```

Điều này giúp phân biệt SQL của chức năng tìm đơn hàng với workload khác.

### Bước 2. Thu thập SQL trọng yếu

Trong khoảng đo được xác định:

```sql
SELECT sql_id,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 2) AS elapsed_s,
       ROUND(cpu_time / 1e6, 2) AS cpu_s,
       buffer_gets,
       disk_reads,
       module,
       action
FROM v$sql
WHERE module = 'ORDER_API'
  AND action = 'SEARCH_ORDERS'
  AND executions > 0
ORDER BY elapsed_time DESC;
```

Đây là số liệu tích lũy trong shared pool. Nếu cần khoảng thời gian chính xác, chụp snapshot trước/sau hoặc dùng công cụ lịch sử phù hợp.

### Bước 3. Xem SQL text và child cursor

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       sql_fulltext
FROM v$sql
WHERE sql_id = :sql_id;
```

Kiểm tra nhiều child cursor và plan hash nếu có.

### Bước 4. Lấy runtime plan

Chạy SQL trong session thử nghiệm với runtime statistics rồi:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Xem E-Rows/A-Rows, buffer gets và operation có chi phí cao.

### Bước 5. Đặt giả thuyết

Ví dụ plan cho thấy `TRUNC(created_at)` trong predicate và full scan trên bảng lớn. Giả thuyết: áp dụng function trên cột ngày khiến index hiện có không được dùng trực tiếp.

### Bước 6. Sửa query trong môi trường thử nghiệm

Query cũ:

```sql
SELECT order_id, created_at
FROM orders
WHERE TRUNC(created_at) = :order_day;
```

Query thử:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= :order_day
  AND created_at <  :order_day + 1;
```

`:order_day` cần được bind dưới kiểu DATE và được chuẩn hóa về đầu ngày theo timezone/nghiệp vụ.

### Bước 7. Chạy lại cùng workload

Dùng cùng dữ liệu, bind values, concurrency và số lần lặp. Ghi lại plan, elapsed, CPU, buffers, reads và số hàng.

### Bước 8. So sánh kết quả

Xác nhận hai query trả cùng tập hàng và thời điểm. So sánh runtime plan và chỉ số.

### Bước 9. Thử dưới concurrency

Chạy nhiều request tìm kiếm đồng thời. Kiểm tra p95/p99, throughput và tác động đến các thao tác ghi.

### Bước 10. Triển khai và theo dõi

Triển khai theo quy trình release. Giữ SQL cũ và kế hoạch rollback. Theo dõi metric và rollback nếu vượt ngưỡng đã thống nhất.

## 20. Mẫu báo cáo trước và sau

Một báo cáo tối ưu ngắn nên đủ để người khác hiểu vì sao thay đổi có giá trị.

### 20.1. Thông tin chung

| Trường | Giá trị |
|---|---|
| Chức năng | Ví dụ: tìm đơn hàng |
| SQL_ID | Ghi SQL_ID |
| Child cursor | Ghi child number |
| Plan hash trước/sau | Ghi hai giá trị |
| Khoảng đo | Thời điểm và thời lượng |
| Môi trường | Version, service, concurrency |
| Bind group | Nhóm tham số đại diện |

### 20.2. Kết quả

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Executions | Đo | Đo | — |
| Median elapsed | Đo | Đo | % |
| p95 elapsed | Đo | Đo | % |
| CPU per execution | Đo | Đo | % |
| Buffer gets per execution | Đo | Đo | % |
| Physical reads | Đo | Đo | % |
| Rows returned | Đo | Đo | Phải tương đương |
| Throughput | Đo | Đo | % |
| DML impact | Đo | Đo | % |

### 20.3. Kết luận có bằng chứng

Ghi rõ:
- Vấn đề ban đầu là gì.
- Bằng chứng trong plan/metrics.
- Thay đổi cụ thể.
- Metric nào cải thiện và bao nhiêu.
- Metric nào xấu đi.
- Kết quả có giữ đúng semantics không.
- Phạm vi bind/concurrency đã thử.
- Điều kiện cần theo dõi sau deploy.

Không ghi “SQL đã tối ưu” nếu chỉ có một lần chạy nhanh hơn mà không có baseline hoặc không kiểm tra kết quả.

## 21. Những sai lầm thường gặp

| Sai lầm | Vì sao không ổn | Cách làm tốt hơn |
|---|---|---|
| Sửa SQL chậm nhất theo cảm giác | Có thể không ảnh hưởng nghiệp vụ hoặc chỉ chạy một lần | Kết hợp tài nguyên, tần suất và SLA |
| Chỉ đo elapsed time một lần | Nhiễu cache, scheduling và tải | Chạy lặp, dùng median/percentile |
| Chỉ test một bind value | Có thể bỏ qua data skew | Dùng nhiều nhóm bind đại diện |
| Chỉ nhìn EXPLAIN PLAN | Không phản ánh đầy đủ runtime | Dùng DISPLAY_CURSOR với actual stats |
| Cho rằng full scan luôn xấu | Full scan có thể rẻ khi đọc phần lớn bảng | So sánh cost và runtime |
| Thêm index ngay khi thấy full scan | Có thể làm DML và storage tốn hơn | Xem selectivity và workload tổng |
| Tạo index cho mọi predicate | Nhiều index tăng chi phí ghi | Chọn index theo query trọng yếu |
| Bỏ qua child cursor | Có thể có plan khác nhau theo bind | Phân tích SQL_ID/child/plan hash |
| Gather stats trên production tùy tiện | Có thể làm nhiều SQL đổi plan | Theo chính sách stats và có kế hoạch |
| So sánh hai lần đo với dữ liệu khác nhau | Kết quả không công bằng | Dùng snapshot và bind tương đương |
| Chỉ test một session | Không thấy contention | Test concurrency gần thực tế |
| Dùng hint để ép plan ngay | Có thể che nguyên nhân và gây regression | Hiểu optimizer estimate trước |
| Không kiểm tra kết quả | Query nhanh nhưng sai semantics | So sánh dữ liệu và edge cases |
| Không có rollback | Khó phục hồi khi regression | Lưu bản cũ và ngưỡng rollback |
| Dùng AWR/ASH/SQL Monitor mà không kiểm tra license | Có thể vi phạm điều khoản | Xác nhận quyền sử dụng theo release/hợp đồng |

## 22. Quy trình chọn công cụ

| Câu hỏi | Công cụ |
|---|---|
| SQL nào đang chiếm nhiều tài nguyên trong shared pool? | V$SQL |
| SQL thuộc chức năng nào? | MODULE/ACTION, service và application logs |
| Một request gọi những SQL nào? | SQL Trace/TKPROF |
| Plan thực thi thực tế là gì? | DBMS_XPLAN.DISPLAY_CURSOR |
| Vì sao ước lượng hàng sai? | E-Rows/A-Rows, statistics, histograms |
| Workload thay đổi theo thời gian thế nào? | AWR nếu licensed hoặc Statspack |
| Session đang chờ ở đâu? | ASH nếu licensed hoặc session/wait views phù hợp |
| SQL dài/parallel đang chạy ra sao? | SQL Monitor nếu licensed |
| PL/SQL subprogram nào chiếm thời gian? | DBMS_HPROF hoặc profiler phù hợp |
| Thay đổi có thực sự tốt hơn? | Benchmark trước/sau cùng workload |

## 23. Checklist vận hành tối ưu SQL

Trước khi sửa:
- Đã xác định chức năng và SLA bị ảnh hưởng.
- Có baseline và khoảng đo.
- Có SQL_ID, child cursor và plan hash.
- Có bind values đại diện.
- Đã xem elapsed, CPU, gets, reads, executions và waits.
- Đã hiểu dữ liệu, statistics và index hiện tại.

Trong khi sửa:
- Có giả thuyết dựa trên bằng chứng.
- Thay đổi có phạm vi nhỏ.
- Không đổi semantics.
- Đã kiểm tra tác động đến DML và SQL liên quan.
- Có cách rollback.

Sau khi sửa:
- Đã chạy cùng workload.
- Đã so sánh plan và runtime statistics.
- Đã kiểm tra nhiều bind groups.
- Đã đo concurrency và percentile.
- Đã so sánh kết quả dữ liệu.
- Đã theo dõi regression sau triển khai.
- Đã lưu báo cáo trước/sau.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao tối ưu SQL phải bắt đầu từ workload?

**Trả lời:** Vì cần biết câu SQL nào thực sự ảnh hưởng hệ thống, tốn tài nguyên gì và tác động đến nghiệp vụ ra sao trước khi chọn cách sửa.

**Câu 2.** Elapsed time khác CPU time thế nào?

**Trả lời:** Elapsed là thời gian trôi qua mà caller chờ; CPU time là thời gian CPU thực sự thực thi. Chênh lệch có thể đến từ I/O, lock hoặc các wait khác.

**Câu 3.** Vì sao không chỉ xếp hạng theo total elapsed time?

**Trả lời:** Một SQL chạy ít lần có thể có tổng elapsed cao; SQL chạy rất thường xuyên nhưng mỗi lần rẻ cũng có thể tạo tải lớn.

**Câu 4.** V$SQL lưu loại số liệu nào?

**Trả lời:** Thống kê thực thi tích lũy của cursor trong shared pool như executions, elapsed, CPU, buffer gets, reads và plan hash.

**Câu 5.** Vì sao V$SQL không phải lịch sử workload đầy đủ?

**Trả lời:** Cursor có thể bị aged out hoặc load lại; thống kê gắn với cursor hiện diện và có thể reset.

**Câu 6.** SQL_ID và PLAN_HASH_VALUE khác nhau thế nào?

**Trả lời:** SQL_ID nhận diện statement; PLAN_HASH_VALUE giúp nhận diện hình dạng execution plan.

**Câu 7.** E-Rows và A-Rows dùng để làm gì?

**Trả lời:** So sánh số hàng optimizer ước lượng với số hàng thực tế để tìm sai lệch cardinality.

**Câu 8.** Full table scan có luôn xấu không?

**Trả lời:** Không. Nếu truy vấn cần phần lớn dữ liệu hoặc bảng nhỏ, full scan có thể rẻ hơn index lookup.

**Câu 9.** Vì sao cần nhiều nhóm bind values?

**Trả lời:** Phân bố dữ liệu có thể lệch; một plan tốt cho giá trị phổ biến có thể kém với giá trị hiếm.

**Câu 10.** SQL Trace/TKPROF giúp gì?

**Trả lời:** Cho thấy số lần parse/execute/fetch, thời gian, I/O và SQL được thực thi trong workload được trace.

**Câu 11.** AWR và ASH có cần kiểm tra license không?

**Trả lời:** Có. Việc sử dụng cần đối chiếu điều khoản Oracle và hợp đồng của hệ thống.

**Câu 12.** Vì sao thêm index có thể làm hệ thống chậm hơn?

**Trả lời:** Index tăng storage và chi phí duy trì khi INSERT/UPDATE/DELETE, đồng thời có thể tạo contention.

**Câu 13.** Vì sao cần đo concurrency?

**Trả lời:** Một SQL nhanh hơn khi chạy riêng có thể tranh chấp CPU, I/O hoặc index khi nhiều session cùng chạy.

**Câu 14.** Plan hash giống nhau có bảo đảm runtime giống nhau không?

**Trả lời:** Không. Dữ liệu, bind values, cache, concurrency và hệ thống có thể khác.

**Câu 15.** Sau khi sửa SQL cần so sánh những gì?

**Trả lời:** Plan, elapsed, CPU, buffer gets, physical reads, rows, throughput, waits và tác động DML; đồng thời xác nhận kết quả nghiệp vụ tương đương.

**Câu 16.** Vì sao phải có kế hoạch rollback?

**Trả lời:** Vì thay đổi có thể gây regression trên workload khác hoặc dưới tải thật; rollback giúp phục hồi nhanh và có kiểm soát.

## 25. Kết luận

Tối ưu SQL hiệu quả là một vòng lặp có đo lường: xác định mục tiêu workload, thu thập baseline, chọn câu SQL có tác động lớn, phân tích SQL_ID và execution plan, hình thành giả thuyết, sửa trong môi trường kiểm soát rồi chạy lại cùng workload để so sánh. V$SQL hữu ích cho thống kê cursor hiện tại; SQL Trace/TKPROF phân tích một request; DBMS_XPLAN cho biết plan và runtime statistics. AWR, ASH, SQL Monitor và SQL Tuning Advisor có thể bổ sung góc nhìn nhưng phải xác nhận quyền sử dụng theo license Oracle.

Khi chọn SQL trọng yếu, kết hợp tổng tài nguyên, chi phí mỗi lần thực thi, tần suất, p95/p99 và ảnh hưởng nghiệp vụ. Khi sửa, bắt đầu từ nguyên nhân được chứng minh: predicate, join cardinality, statistics, index, bind values, partition pruning hoặc số lần gọi SQL. Không mặc định full scan là xấu, không thêm index theo cảm giác và không ép plan trước khi hiểu optimizer.

Một thay đổi chỉ được coi là thành công khi cải thiện chỉ số mục tiêu trong workload đại diện, giữ nguyên kết quả và không gây regression không chấp nhận được cho các SQL hoặc DML liên quan. Lưu baseline, ghi change record, đặt ngưỡng rollback và theo dõi sau triển khai để mỗi lần tối ưu đều có thể giải thích, lặp lại và kiểm chứng.

