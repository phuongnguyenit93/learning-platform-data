# Đánh giá hồi quy kế hoạch sau nạp dữ liệu hoặc nâng cấp

Một câu truy vấn từng chạy nhanh có thể chậm đi sau khi nạp thêm dữ liệu, thay đổi phân bố giá trị hoặc nâng cấp MySQL. Nguyên nhân có thể là optimizer chọn access path khác, thống kê không còn phản ánh dữ liệu, histogram thiếu hoặc đã lỗi thời, chỉ mục thay đổi, hay chi phí thực thi thực tế tăng dù kế hoạch không đổi.

Đánh giá hồi quy kế hoạch (execution plan regression) là quy trình so sánh kế hoạch và hiệu năng của cùng một workload trước và sau một thay đổi. Mục tiêu là xác định phần nào đã đổi, tìm nguyên nhân có bằng chứng, rồi chọn biện pháp sửa phù hợp. Không nên kết luận chỉ từ việc câu SQL chậm hơn hoặc từ một dòng `key` trong `EXPLAIN`.

## 1. Phân biệt hồi quy kế hoạch và hồi quy hiệu năng

Hai hiện tượng có liên quan nhưng không giống nhau:

- **Hồi quy kế hoạch:** optimizer chọn đường truy cập hoặc thứ tự join khác, ví dụ chuyển từ index range scan sang full table scan, đổi thứ tự join hoặc thêm bước sort.
- **Hồi quy hiệu năng:** thời gian thực thi, số hàng đọc, CPU hoặc I/O xấu đi. Điều này có thể xảy ra dù kế hoạch không đổi, chẳng hạn dữ liệu tăng, cache lạnh, ổ đĩa bận hoặc mức đồng thời cao hơn.

Khi điều tra, cần so sánh cả kế hoạch ước lượng, số hàng thực tế và thời gian thực thi. Một kế hoạch khác không nhất thiết xấu hơn; optimizer có thể chọn kế hoạch mới nhanh hơn trên dữ liệu hiện tại. Ngược lại, kế hoạch giống nhau vẫn có thể chậm vì khối lượng công việc đã tăng.

## 2. Tạo baseline trước khi nạp dữ liệu hoặc nâng cấp

Baseline là tập thông tin dùng để so sánh sau thay đổi. Với mỗi truy vấn quan trọng, ghi nhận:

1. SQL hoặc digest của truy vấn, cùng các giá trị tham số đại diện.
2. Phiên bản MySQL, storage engine, schema, index và cấu hình optimizer liên quan.
3. Kế hoạch `EXPLAIN` (tốt nhất lưu cả JSON hoặc TREE nếu phiên bản hỗ trợ).
4. Số hàng ước lượng, số hàng thực tế, số vòng lặp và thời gian thực thi.
5. Độ trễ trung bình và percentile như p95/p99, số lần chạy, rows examined, rows sent.
6. Điều kiện đo: lượng dữ liệu, thời điểm, tải đồng thời và trạng thái cache.

Ví dụ kiểm tra môi trường:

```sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS version_comment,
       @@SESSION.optimizer_switch AS optimizer_switch;

SHOW CREATE TABLE orders;
SHOW INDEX FROM orders;
```

Giữ lại kết quả baseline bên ngoài phiên đo hoặc trong hệ thống quản lý thay đổi của nhóm. Khi so sánh, dùng cùng câu SQL, kiểu tham số, dữ liệu đại diện và điều kiện tải càng giống nhau càng tốt. Nếu vừa nâng cấp MySQL, vừa thay index và đổi cấu hình optimizer cùng lúc, sẽ khó xác định yếu tố nào gây ra khác biệt.

## 3. Thu thập truy vấn cần đánh giá

Không nên chỉ kiểm tra câu truy vấn vừa được báo chậm. Hãy tìm những câu có tổng thời gian lớn, chạy thường xuyên, đọc nhiều hàng hoặc có độ trễ cao.

Nếu Performance Schema đang thu thập statement digest, có thể xem các truy vấn tốn thời gian trong schema hiện tại:

```sql
SELECT DIGEST_TEXT,
       COUNT_STAR,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS total_seconds,
       ROUND(AVG_TIMER_WAIT / 1000000000, 2) AS avg_ms,
       SUM_ROWS_EXAMINED,
       SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Các timer trong Performance Schema được biểu diễn theo picosecond; phép chia trong ví dụ chuyển tổng thời gian sang giây và thời gian trung bình sang mili giây. Bảng summary là số liệu tích lũy từ lúc thống kê được khởi tạo hoặc reset, không phải lịch sử từng lần chạy. Hãy lưu snapshot ở hai thời điểm hoặc dùng công cụ giám sát để tính chênh lệch trong một khoảng đo.

Có thể xem thêm view `sys.statement_analysis` nếu schema `sys` được cài đặt và người dùng có quyền đọc. View này giúp sắp xếp digest theo tổng độ trễ, độ trễ trung bình và số hàng đọc. Slow query log cũng hữu ích để thu thập các lần chạy vượt ngưỡng, nhưng cần cấu hình và quản lý dung lượng log phù hợp.

## 4. So sánh kế hoạch bằng EXPLAIN

`EXPLAIN` cho biết optimizer dự kiến thực thi câu lệnh như thế nào. Ví dụ:

```sql
EXPLAIN
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
```

Với định dạng bảng truyền thống, hãy chú ý:

- `possible_keys`: các index optimizer có thể cân nhắc.
- `key`: index thực sự được chọn.
- `key_len`: độ dài phần khóa được sử dụng; cần diễn giải theo kiểu dữ liệu, khả năng NULL và cấu trúc index.
- `type`: access type như `const`, `eq_ref`, `ref`, `range` hoặc `ALL`.
- `rows` và `filtered`: số hàng ước lượng cần đọc và tỷ lệ hàng dự kiến còn lại sau lọc.
- `Extra`: thông tin như `Using filesort`, `Using temporary`, `Using index` hoặc `Using index condition`.

Có thể dùng JSON để đọc chi tiết điều kiện và chi phí ước lượng:

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
```

Hoặc dùng TREE để xem cây iterator trên các phiên bản hỗ trợ:

```sql
EXPLAIN FORMAT=TREE
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
```

So sánh baseline và kết quả mới theo từng bước: access method của mỗi bảng, index được chọn, thứ tự join, bộ lọc, sort, temporary table và ước lượng số hàng. Đừng chỉ so sánh toàn bộ văn bản EXPLAIN vì một số thông tin phụ có thể đổi mà không làm thay đổi đường truy cập quan trọng.

## 5. Đối chiếu ước lượng với thực tế bằng EXPLAIN ANALYZE

MySQL 8.0.18 trở lên hỗ trợ `EXPLAIN ANALYZE` cho câu `SELECT`. Lệnh này thực sự chạy truy vấn và báo số hàng, số vòng lặp cùng thời gian của các iterator:

```sql
EXPLAIN ANALYZE
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
```

Hãy tập trung vào:

- `rows`: số hàng thực tế iterator trả về.
- `loops`: số lần iterator được gọi; cần xét cùng số hàng để hiểu tổng lượng công việc.
- `actual time`: thời gian thực tế của iterator, thường thể hiện thời gian đến hàng đầu tiên và thời gian hoàn tất.
- Sự chênh lệch giữa ước lượng và thực tế: sai lệch lớn có thể khiến optimizer chọn join order hoặc index không phù hợp.

Ví dụ, optimizer ước lượng một điều kiện trả về vài chục hàng nhưng thực tế trả về hàng trăm nghìn hàng. Khi đó, join theo nested loop hoặc tra cứu từng hàng có thể đắt hơn nhiều so với dự tính. Cần kiểm tra thống kê và phân bố dữ liệu của cột lọc.

`EXPLAIN ANALYZE` có tác động vì nó thực thi câu truy vấn. Chỉ chạy với câu đọc có thể thực thi an toàn, giới hạn tải và cân nhắc giờ đo trên production. Thời gian của một lần chạy chịu ảnh hưởng bởi cache, I/O, cạnh tranh tài nguyên và tải đồng thời; nên đo nhiều lần trong điều kiện kiểm soát và so sánh percentile thay vì kết luận từ một mẫu đơn lẻ.

## 6. Làm mới thống kê InnoDB sau bulk load

Optimizer dựa vào thống kê index để ước lượng cardinality và số hàng phù hợp với điều kiện. Sau khi nạp một lượng dữ liệu lớn, phân bố giá trị có thể khác trước, trong khi thống kê cũ chưa phản ánh đầy đủ dữ liệu mới.

Với InnoDB, thống kê index có thể được lưu bền vững. Một số biến liên quan:

```sql
SHOW VARIABLES LIKE 'innodb_stats_persistent';
SHOW VARIABLES LIKE 'innodb_stats_auto_recalc';
SHOW VARIABLES LIKE 'innodb_stats_persistent_sample_pages';
```

- `innodb_stats_persistent` điều khiển việc lưu thống kê InnoDB bền vững.
- `innodb_stats_auto_recalc` điều khiển việc tự động tính lại thống kê khi dữ liệu thay đổi đủ lớn.
- `innodb_stats_persistent_sample_pages` điều khiển số trang lấy mẫu khi tính thống kê persistent.

Với cấu hình mặc định, InnoDB có thể lên lịch tính lại thống kê persistent ở chế độ nền khi khoảng 10% số hàng của bảng thay đổi. Đây là hoạt động tự động, không bảo đảm thống kê được làm mới ngay tại thời điểm bulk load kết thúc. Khi cần đánh giá kế hoạch ngay sau nạp dữ liệu, hãy chủ động chạy `ANALYZE TABLE` và kiểm tra kết quả.

Khi nạp dữ liệu lớn hoặc phân bố dữ liệu thay đổi đáng kể, có thể yêu cầu cập nhật thống kê tường minh:

```sql
ANALYZE TABLE orders;
```

Sau đó chạy lại `EXPLAIN` và `EXPLAIN ANALYZE` với cùng truy vấn. So sánh số hàng ước lượng trước và sau `ANALYZE TABLE`; nếu ước lượng gần thực tế hơn và kế hoạch tốt hơn, thống kê cũ có thể là một phần nguyên nhân.

Có thể xem thống kê InnoDB persistent trong các bảng hệ thống:

```sql
SELECT *
FROM mysql.innodb_table_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders';

SELECT index_name, stat_name, stat_value, sample_size, stat_description
FROM mysql.innodb_index_stats
WHERE database_name = DATABASE()
  AND table_name = 'orders'
ORDER BY index_name, stat_name;
```

Các giá trị như `n_rows`, `n_diff_pfxNN` và `stat_value` là ước lượng thống kê, không phải số đếm chính xác cho mọi truy vấn. Việc lấy mẫu cũng có thể tạo ra sai số, nhất là khi dữ liệu lệch mạnh hoặc có phân bố không đồng đều.

`ANALYZE TABLE` có thể cần metadata lock và tiêu thụ tài nguyên khi lấy mẫu. Hãy lên lịch phù hợp, kiểm tra transaction dài và theo dõi tải trên bảng lớn. Không chạy lặp lại liên tục chỉ để ép optimizer chọn một index mong muốn.

## 7. Histogram cho cột có phân bố lệch

Thống kê index thường mô tả cardinality của các tiền tố index. Với một cột có phân bố lệch mạnh, ví dụ một số trạng thái xuất hiện rất nhiều còn một số trạng thái hiếm, histogram có thể giúp optimizer ước lượng selectivity tốt hơn.

Tạo histogram cho cột `status`:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 64 BUCKETS;
```

Kiểm tra histogram trong data dictionary:

```sql
SELECT SCHEMA_NAME, TABLE_NAME, COLUMN_NAME, HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders';
```

Histogram là thống kê theo từng cột, có thể hỗ trợ optimizer ngay cả khi cột không phải phần đầu của một index. Histogram không thay thế index: nó giúp ước lượng số hàng, còn access path vẫn cần cấu trúc lưu trữ phù hợp. Histogram không được tự làm mới chỉ vì các hàng trong bảng thay đổi; cần chủ động chạy `UPDATE HISTOGRAM` khi phân bố dữ liệu thay đổi đáng kể.

Nếu dữ liệu thay đổi đáng kể, histogram có thể cần được cập nhật lại:

```sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status WITH 64 BUCKETS;
```

Nếu muốn bỏ histogram của cột:

```sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status;
```

Không nên chọn số bucket theo cảm tính. Nhiều bucket hơn không tự động làm kế hoạch tốt hơn; hãy so sánh ước lượng, kế hoạch và thời gian với workload đại diện. Histogram có thể đặc biệt hữu ích khi giá trị phổ biến và hiếm có độ chọn lọc khác xa nhau.

## 8. Điều tra hồi quy sau nâng cấp MySQL

Nâng cấp có thể làm thay đổi optimizer, cost model, mặc định cấu hình, cách xử lý biểu thức hoặc thống kê. Vì vậy, một truy vấn có thể nhận kế hoạch khác dù câu SQL và schema không đổi.

Quy trình so sánh trước/sau nâng cấp:

1. Lưu phiên bản MySQL cũ và mới, cấu hình liên quan, schema và danh sách index.
2. Lưu digest của truy vấn quan trọng cùng giá trị tham số đại diện.
3. Chụp `EXPLAIN FORMAT=JSON` hoặc `TREE` trên môi trường cũ và mới.
4. Chạy benchmark có kiểm soát trên dữ liệu tương đương; đo actual rows, loops, thời gian, rows examined và độ trễ.
5. Kiểm tra thống kê InnoDB và histogram trên môi trường mới; không mặc định chúng đã phản ánh đúng phân bố sau nạp dữ liệu.
6. Xem xét thay đổi `optimizer_switch`, cost model, index visibility, collation và kiểu dữ liệu nếu chúng ảnh hưởng truy vấn.
7. Chỉ thay đổi một yếu tố mỗi lần, rồi đo lại để xác định nguyên nhân.

Ví dụ ghi nhận các biến quan trọng:

```sql
SELECT VERSION(), @@optimizer_switch;
SHOW VARIABLES LIKE 'innodb_stats%';
```

Không nên sao chép nguyên cấu hình optimizer từ phiên bản cũ sang phiên bản mới mà không đánh giá. Giá trị mặc định và hành vi optimizer có thể thay đổi; cấu hình cũ có thể vô hiệu hóa cải tiến hoặc tạo vấn đề khác.

## 9. Chẩn đoán theo dấu hiệu

| Dấu hiệu quan sát | Nguyên nhân cần kiểm tra | Hướng xử lý đầu tiên |
|---|---|---|
| `rows` ước lượng nhỏ nhưng actual rows rất lớn | Thống kê cũ, histogram thiếu hoặc phân bố lệch | `ANALYZE TABLE`, kiểm tra histogram và so sánh ước lượng |
| Optimizer chuyển từ `range`/`ref` sang `ALL` | Index không còn phù hợp, selectivity thay đổi hoặc cost estimate khác | Kiểm tra `possible_keys`, `key`, index và số hàng thực tế |
| Join order thay đổi và nested loop chạy nhiều vòng | Cardinality ước lượng sai hoặc bảng đầu vào lớn hơn dự kiến | Đối chiếu rows/loops từng iterator và thống kê các bảng |
| Có `Using filesort` hoặc temporary table mới xuất hiện | Thứ tự index không đáp ứng truy vấn hoặc tập kết quả tăng | Kiểm tra composite index, ORDER BY/GROUP BY và lượng hàng cần sort |
| Kế hoạch gần như giống nhau nhưng latency tăng | I/O, buffer pool, CPU, lock wait hoặc concurrency | Đo tài nguyên, waits, rows examined và trạng thái cache |
| Chỉ một nhóm giá trị tham số bị chậm | Phân bố giá trị lệch, histogram hoặc tính chọn lọc khác nhau | Đo với tham số phổ biến và hiếm, xem histogram và actual rows |

## 10. Khắc phục và xác minh sau điều chỉnh

Ưu tiên sửa nguyên nhân đã xác nhận:

- Làm mới thống kê index sau bulk load hoặc thay đổi dữ liệu đáng kể.
- Cập nhật histogram cho cột có phân bố lệch khi ước lượng selectivity là vấn đề.
- Điều chỉnh hoặc bổ sung index nếu truy vấn và access path cho thấy thiếu tiền tố phù hợp.
- Viết lại truy vấn nếu biểu thức, chuyển kiểu hoặc điều kiện khiến index không được sử dụng như mong đợi.
- Kiểm tra cấu hình và khác biệt phiên bản nếu hồi quy bắt đầu sau upgrade.
- Đo lại cả workload liên quan để chắc rằng cải thiện một truy vấn không làm truy vấn khác suy giảm đáng kể.

`FORCE INDEX` hoặc optimizer hint có thể dùng làm phép thử đối chứng: so sánh kế hoạch với index được đề xuất và kế hoạch optimizer tự chọn. Không nên dùng hint như phản xạ đầu tiên hoặc gắn cố định vào ứng dụng khi chưa hiểu vì sao optimizer chọn kế hoạch cũ. Dữ liệu tiếp tục thay đổi và hint có thể trở thành lựa chọn tệ trong tương lai.

Trước khi đưa thay đổi vào production, cần có phương án quay lại: khôi phục index, bỏ histogram mới nếu gây tác động xấu, hoàn nguyên cấu hình hoặc phát hành lại câu SQL. Sau triển khai, tiếp tục theo dõi digest, latency, rows examined và lỗi truy vấn trong một khoảng đủ đại diện.

## 11. Checklist đánh giá hồi quy

| Bước | Việc cần xác nhận |
|---|---|
| Baseline | Có SQL/digest, tham số, version, schema, index, config và kế hoạch trước thay đổi |
| Workload | Đã chọn truy vấn quan trọng, truy vấn định kỳ và tham số đại diện |
| Kế hoạch | Đã so sánh access path, join order, key, rows, sort và temporary table |
| Thực thi | Đã so sánh actual rows, loops, thời gian và độ trễ dưới tải tương đương |
| Thống kê | Đã kiểm tra persistent stats, `ANALYZE TABLE` và histogram khi phù hợp |
| Khắc phục | Đã thay đổi từng yếu tố và đo lại toàn bộ truy vấn liên quan |
| Triển khai | Có phương án rollback và giám sát sau thay đổi |

## 12. Tự kiểm tra

1. Hồi quy kế hoạch khác hồi quy hiệu năng ở điểm nào?
2. Vì sao cần lưu baseline trước bulk load hoặc nâng cấp?
3. `EXPLAIN` và `EXPLAIN ANALYZE` cung cấp những loại bằng chứng khác nhau nào?
4. Khi nào cần chạy `ANALYZE TABLE` sau nạp dữ liệu lớn?
5. Histogram giúp optimizer cải thiện ước lượng trong trường hợp nào?
6. Vì sao kế hoạch không đổi vẫn có thể có latency tăng?
7. Khi điều tra hồi quy sau upgrade, vì sao cần thay đổi từng yếu tố một?
8. Vì sao không nên dùng `FORCE INDEX` trước khi hiểu nguyên nhân optimizer chọn kế hoạch?

