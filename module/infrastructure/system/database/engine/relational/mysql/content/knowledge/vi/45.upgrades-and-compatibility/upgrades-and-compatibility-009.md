# So sánh SQL plan, độ trễ, lỗi và kết quả nghiệp vụ trước/sau

Nâng cấp MySQL có thể làm thay đổi cách optimizer chọn index, thứ tự join, ước lượng số hàng và cách thực thi truy vấn. Một câu SQL vẫn chạy thành công nhưng có thể chậm hơn, đọc nhiều hàng hơn hoặc trả về kết quả khác do thay đổi về SQL mode, collation, kiểu dữ liệu hay hành vi tương thích. Vì vậy, đánh giá nâng cấp phải so sánh đồng thời kế hoạch thực thi, độ trễ, lỗi và kết quả nghiệp vụ trên cùng một tập dữ liệu và workload có thể tái lập.

Bài học này thuộc chương **Nâng cấp và tương thích** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành, việc đo trước/sau giúp xác nhận nâng cấp giữ được tính đúng đắn và đáp ứng yêu cầu hiệu năng của hệ thống.

## 1. Bốn góc nhìn cần so sánh

Không nên kết luận một bản nâng cấp tốt chỉ vì ứng dụng khởi động được hoặc toàn bộ migration chạy xong. Hãy đánh giá ít nhất bốn nhóm chỉ số:

| Góc nhìn | Câu hỏi cần trả lời | Bằng chứng nên thu thập |
|---|---|---|
| SQL plan | Optimizer chọn đường truy cập và thứ tự join nào? Có thay đổi đáng kể không? | EXPLAIN FORMAT=JSON, EXPLAIN ANALYZE |
| Độ trễ và throughput | Truy vấn nhanh/chậm hơn bao nhiêu ở p50, p95, p99? Hệ thống xử lý được bao nhiêu request? | APM, application metrics, benchmark cùng workload |
| Lỗi và tài nguyên | Có tăng SQL error, warning, timeout, deadlock, lock wait, CPU hoặc I/O không? | Application log, Performance Schema, MySQL status, server log |
| Kết quả nghiệp vụ | Số hàng, tổng tiền, trạng thái, quan hệ và quy tắc nghiệp vụ có giữ nguyên không? | Đối chiếu result set, aggregate, constraint và test nghiệp vụ |

Một thay đổi kế hoạch không mặc nhiên là regression. Optimizer có thể chọn plan khác nhưng vẫn nhanh hơn. Ngược lại, plan trông gần như giống nhau vẫn có thể chậm do dữ liệu lớn hơn, cache lạnh, contention hoặc thay đổi tài nguyên. Cần kết hợp plan với số đo thực tế.

## 2. Xây dựng baseline trước nâng cấp

Baseline là bộ số liệu chuẩn để đối chiếu sau nâng cấp. Thu thập baseline trên phiên bản MySQL hiện tại trước khi thay đổi binary, cấu hình hoặc schema.

### Ghi nhận môi trường

Lưu lại phiên bản, cấu hình optimizer và các thiết lập ảnh hưởng ngữ nghĩa truy vấn:

~~~sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS version_comment;

SHOW VARIABLES
WHERE Variable_name IN (
  'sql_mode',
  'time_zone',
  'system_time_zone',
  'character_set_server',
  'collation_server',
  'optimizer_switch',
  'transaction_isolation',
  'innodb_stats_persistent',
  'binlog_format'
);
~~~

Một số biến hoặc tên biến có thể khác giữa các nhánh phiên bản. Nếu một biến không tồn tại, ghi nhận khác biệt thay vì tự giả định giá trị tương đương. Lưu thêm cấu hình MySQL, kích thước instance, CPU, RAM, storage, filesystem, connection pool, phiên bản driver và phiên bản ứng dụng.

Kiểm tra schema và đối tượng phụ thuộc:

~~~sql
SHOW CREATE TABLE orders;
SHOW CREATE TABLE customers;
SHOW INDEX FROM orders;
SHOW INDEX FROM customers;
~~~

Với stored program, trigger và event quan trọng, lưu định nghĩa tương ứng bằng SHOW CREATE. Ghi lại charset/collation, kiểu cột, default, generated column, index, constraint, partition và histogram nếu có. Đây là những yếu tố có thể ảnh hưởng cả kết quả lẫn plan.

### Chọn workload đại diện

Chọn các truy vấn quan trọng dựa trên lưu lượng và rủi ro nghiệp vụ:

- Truy vấn đọc thường xuyên, chiếm phần lớn request.
- Truy vấn có p95/p99 cao hoặc thời gian chạy không ổn định.
- Truy vấn join nhiều bảng, lọc theo ngày, phân trang hoặc tổng hợp.
- Truy vấn ghi vào bảng có nhiều index hoặc khóa ngoại.
- Truy vấn chạy theo batch, báo cáo hoặc tác vụ nền.
- Truy vấn có tham số phân bố lệch, ví dụ một trạng thái phổ biến hơn nhiều trạng thái khác.

Không chỉ lấy một giá trị tham số thuận lợi. Cùng một câu SQL có thể có plan hoặc thời gian khác nhau đáng kể tùy độ chọn lọc của tham số và phân bố dữ liệu. Lưu lại bộ tham số đại diện, kể cả trường hợp biên.

### Dùng cùng một trạng thái dữ liệu

Cách so sánh đáng tin cậy là restore cùng một snapshot dữ liệu vào hai môi trường thử nghiệm, một môi trường chạy phiên bản cũ và một môi trường chạy phiên bản đích. Giữ nguyên schema ứng dụng, index, dữ liệu, cấu hình phần cứng và workload trong lần đo đầu tiên để cô lập ảnh hưởng của phiên bản server.

Nếu nâng cấp đồng thời schema hoặc cấu hình, tách thành các lượt thử riêng để biết yếu tố nào tạo ra khác biệt. Với workload ghi, chạy trên clone hoặc dữ liệu thử nghiệm có thể khôi phục; không phát lại DML có tác dụng phụ lên production chỉ để benchmark.

## 3. Đọc kế hoạch thực thi bằng EXPLAIN

EXPLAIN cho biết optimizer dự định truy cập dữ liệu như thế nào. Bắt đầu với dạng JSON để có cấu trúc dễ so sánh:

~~~sql
EXPLAIN FORMAT=JSON
SELECT
  o.id,
  o.created_at,
  o.total_amount,
  c.email
FROM orders AS o
JOIN customers AS c
  ON c.id = o.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
ORDER BY o.created_at DESC, o.id DESC
LIMIT 100;
~~~

Khi so sánh trước/sau, chú ý:

- **access_type:** kiểu truy cập như const, eq_ref, ref, range, index hoặc ALL. ALL thường cho biết full table scan, nhưng có thể vẫn là lựa chọn hợp lý với bảng nhỏ hoặc truy vấn đọc phần lớn dữ liệu.
- **key và possible_keys:** index optimizer cân nhắc và index được chọn. Plan có thể đổi index do thống kê hoặc chi phí ước lượng.
- **rows và filtered:** số hàng ước lượng cần đọc và tỷ lệ hàng còn lại sau điều kiện lọc. Đây là ước lượng, không phải số hàng thực tế.
- **join order:** thứ tự bảng được truy cập. Đổi thứ tự có thể cải thiện hoặc làm tăng số hàng trung gian.
- **temporary table và filesort:** việc tạo bảng tạm hoặc sắp xếp bổ sung. Không phải lúc nào cũng xấu, nhưng cần theo dõi nếu xuất hiện mới hoặc chi phí tăng.
- **materialization và derived table:** optimizer có thể materialize subquery/CTE hoặc biến đổi cách thực thi.
- **partition pruning:** truy vấn có loại bỏ được partition không cần thiết hay phải đọc nhiều partition.

Không so sánh nguyên văn toàn bộ JSON bằng diff rồi kết luận. Phiên bản mới có thể đổi cách trình bày plan. Hãy trích các thuộc tính quan trọng và giải thích tác động lên workload.

### Xem plan dạng cây

~~~sql
EXPLAIN FORMAT=TREE
SELECT
  customer_id,
  COUNT(*) AS order_count
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY customer_id;
~~~

Dạng TREE cho thấy luồng iterator và quan hệ giữa các bước. Đây là dạng hiển thị được dùng cùng EXPLAIN ANALYZE trong MySQL 8.0.18 trở lên.

### Đo thực thi bằng EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT
  o.id,
  o.created_at,
  o.total_amount
FROM orders AS o
WHERE o.customer_id = 1001
  AND o.status = 'PAID'
ORDER BY o.created_at DESC
LIMIT 50;
~~~

EXPLAIN ANALYZE thực sự chạy câu SELECT và báo thời gian, số hàng thực tế cùng số vòng lặp ở từng iterator. Chỉ dùng với truy vấn đọc an toàn, tham số và phạm vi dữ liệu đã được đánh giá. Một truy vấn SELECT vẫn có thể tiêu tốn CPU, I/O và giữ tài nguyên đáng kể; không chạy tùy tiện trên production trong giờ cao điểm.

Đối chiếu số hàng thực tế với ước lượng. Nếu optimizer ước lượng vài chục hàng nhưng thực tế đọc hàng triệu, thống kê có thể không phản ánh phân bố dữ liệu. Kiểm tra index, histogram và thời điểm ANALYZE TABLE. Đừng vội ép index trước khi hiểu vì sao ước lượng sai.

EXPLAIN ANALYZE có overhead đo đạc và thường chạy một lần cho truy vấn được chỉ định. Không dùng thời gian của một lần EXPLAIN ANALYZE làm kết luận duy nhất về latency production. Kết hợp nó với benchmark lặp lại và số đo ở tầng ứng dụng.

## 4. Phân tích digest bằng Performance Schema

Performance Schema tổng hợp thống kê câu lệnh theo digest, giúp tìm truy vấn tiêu tốn tổng thời gian, đọc nhiều hàng hoặc phát sinh lỗi. Ví dụ:

~~~sql
SELECT
  SCHEMA_NAME,
  DIGEST,
  LEFT(DIGEST_TEXT, 180) AS query_sample,
  COUNT_STAR,
  ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
  ROUND(MAX_TIMER_WAIT / 1000000000000, 6) AS max_seconds,
  SUM_ROWS_EXAMINED,
  SUM_ROWS_SENT,
  SUM_ERRORS,
  SUM_WARNINGS,
  SUM_CREATED_TMP_DISK_TABLES,
  SUM_SORT_ROWS
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 30;
~~~

Timer của Performance Schema được biểu diễn bằng picosecond; chia cho 10^12 để đổi sang giây. Bảng digest là số liệu tích lũy trong khoảng thống kê, không phải latency của từng request. Hãy chụp snapshot tại đầu và cuối cùng một khoảng workload rồi tính delta cho các bộ đếm như COUNT_STAR, SUM_TIMER_WAIT, SUM_ROWS_EXAMINED và SUM_ERRORS.

Không nên xóa/reset summary toàn cục trên production chỉ để tạo baseline nếu việc đó ảnh hưởng quan sát của đội vận hành. Có thể xuất snapshot ra file hoặc hệ thống monitoring rồi so sánh delta theo cửa sổ thời gian.

Performance Schema phải có instrument và consumer phù hợp được bật. Nếu bảng không có số liệu, kiểm tra cấu hình instrumentation và quyền truy cập trước khi kết luận rằng workload không phát sinh câu lệnh.

### Diễn giải số liệu

- COUNT_STAR tăng nhanh cho biết digest được thực thi thường xuyên.
- AVG_TIMER_WAIT thể hiện thời gian trung bình của digest trong khoảng thống kê; nó không cho biết phân vị p95 hoặc p99.
- SUM_ROWS_EXAMINED cao so với SUM_ROWS_SENT có thể cho thấy truy vấn đọc nhiều hàng để trả ít kết quả. Với truy vấn aggregate, tỷ lệ này có thể là bản chất của nghiệp vụ.
- SUM_CREATED_TMP_DISK_TABLES tăng có thể chỉ ra truy vấn cần bảng tạm trên đĩa.
- SUM_ERRORS và SUM_WARNINGS giúp phát hiện thay đổi về lỗi hoặc cảnh báo sau nâng cấp.

Ví dụ, một digest có tổng thời gian lớn có thể do mỗi lần chạy chậm hoặc do được gọi rất nhiều lần. Phân biệt hai trường hợp bằng cách xem cả COUNT_STAR và AVG_TIMER_WAIT. Tối ưu một truy vấn rất nhanh nhưng được gọi hàng triệu lần đôi khi đem lại lợi ích lớn hơn tối ưu truy vấn hiếm khi chạy.

## 5. Đo latency, throughput và tài nguyên đúng cách

Latency phải được đo ở nơi người dùng cảm nhận. Application Performance Monitoring (APM) hoặc telemetry của ứng dụng nên ghi lại p50, p95, p99, timeout và thời gian chờ connection pool. Performance Schema bổ sung góc nhìn ở phía server.

| Chỉ số | Ý nghĩa | Cách so sánh |
|---|---|---|
| p50 latency | Thời gian của request điển hình | Phát hiện thay đổi ở phần lớn request |
| p95 latency | 95% request hoàn tất trong ngưỡng này | Đánh giá trải nghiệm phần lớn người dùng |
| p99 latency | Đuôi phân bố chậm | Phát hiện query chậm, lock hoặc tranh chấp hiếm gặp |
| Throughput | Request hoặc transaction mỗi giây | Xác định năng lực xử lý dưới tải |
| Error rate | Tỷ lệ request/transaction lỗi | Phát hiện lỗi tương thích và timeout |
| CPU và I/O | Tài nguyên tiêu thụ | Xác định regression do chi phí thực thi |
| Lock wait/deadlock | Tranh chấp đồng thời | Phát hiện thay đổi về thứ tự hoặc thời gian giữ khóa |

Performance Schema digest cung cấp trung bình và cực đại, không phải percentile chính xác cho từng request. Dùng APM hoặc histogram ở tầng ứng dụng để lấy p50/p95/p99. Nếu không có APM, triển khai histogram latency trước khi nâng cấp để có baseline tương đương.

### Điều kiện benchmark

Giữ các điều kiện sau giống nhau giữa hai phiên bản:

1. Cùng snapshot dữ liệu, schema và index.
2. Cùng câu SQL, bộ tham số và tỷ lệ đọc/ghi.
3. Cùng phần cứng, giới hạn tài nguyên và cấu hình kết nối.
4. Cùng mức concurrency và thời lượng workload.
5. Cùng trạng thái cache hoặc tách riêng phép đo cold-cache và warm-cache.
6. Có giai đoạn warm-up trước khi ghi số liệu.
7. Lặp lại nhiều lần và so sánh median cùng các percentile, không chọn lần chạy tốt nhất.

Đo cả tải thấp và tải gần mức production. Một plan có latency tốt khi chạy đơn lẻ có thể gây lock wait hoặc tăng p99 khi nhiều transaction chạy đồng thời.

## 6. So sánh lỗi SQL, warning và lock

Nâng cấp có thể làm lộ ra truy vấn vốn đã dựa vào hành vi không rõ ràng hoặc phụ thuộc cấu hình cũ. Theo dõi lỗi theo SQLSTATE và error code, không chỉ tìm chuỗi ERROR trong log.

Các nhóm cần chú ý:

- **Syntax/compatibility error:** tên từ khóa, cú pháp hoặc tính năng đã deprecated/removed.
- **Data conversion error:** chuyển chuỗi sang số/ngày, giá trị ngoài miền hoặc strict SQL mode.
- **Constraint violation:** duplicate key, foreign key, NOT NULL hoặc CHECK constraint.
- **Authentication/privilege error:** plugin xác thực, tài khoản, role hoặc quyền routine.
- **Timeout:** query timeout, lock wait timeout, connection timeout.
- **Deadlock:** transaction xung đột và bị InnoDB rollback để phá vòng chờ.
- **Warning:** ép kiểu, giá trị bị cắt hoặc cú pháp deprecated.

So sánh tổng lỗi theo cùng cửa sổ thời gian và cùng số lượng request. Tỷ lệ lỗi có ý nghĩa hơn số lượng tuyệt đối nếu throughput giữa hai lần đo khác nhau.

Dùng Performance Schema digest để xem SUM_ERRORS và SUM_WARNINGS; đối chiếu với application log để biết request, endpoint và tham số gây lỗi. Khi gặp deadlock, lấy thông tin từ log ứng dụng và SHOW ENGINE INNODB STATUS. Không chỉ đếm lỗi: cần phân loại theo mã, mức độ, endpoint và tác động nghiệp vụ.

Kiểm tra lock wait trong Performance Schema trên MySQL 8.0:

~~~sql
SELECT
  w.REQUESTING_ENGINE_TRANSACTION_ID,
  w.BLOCKING_ENGINE_TRANSACTION_ID,
  r.OBJECT_SCHEMA,
  r.OBJECT_NAME,
  r.INDEX_NAME,
  r.LOCK_TYPE,
  r.LOCK_MODE AS requesting_lock_mode,
  b.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS r
  ON r.ENGINE = w.ENGINE
 AND r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS b
  ON b.ENGINE = w.ENGINE
 AND b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
~~~

Bảng này cho thấy quan hệ giữa transaction đang chờ và transaction chặn nó. Nếu truy vấn không trả dữ liệu, có thể tại thời điểm lấy mẫu không có lock wait. Để tìm blocker, kết hợp với data_locks, events_statements_current và process list. Không kill session chỉ dựa vào một hàng lock wait mà chưa xác định giao dịch và hậu quả.

## 7. Xác minh kết quả nghiệp vụ trước và sau

Plan và latency không chứng minh kết quả đúng. Cần so sánh kết quả nghiệp vụ trên cùng snapshot và cùng tham số.

### So sánh result set

Với truy vấn trả danh sách, xuất kết quả ở cả hai môi trường với thứ tự xác định bằng khóa duy nhất:

~~~sql
SELECT
  id,
  customer_id,
  status,
  total_amount,
  created_at
FROM orders
WHERE created_at >= '2026-01-01'
ORDER BY id;
~~~

So sánh theo khóa chính và từng cột sau khi chuẩn hóa định dạng. Nếu truy vấn không có ORDER BY, thứ tự hàng không được bảo đảm; không so sánh hai file kết quả theo vị trí dòng. Khi có phân trang, dùng thứ tự ổn định có khóa phụ duy nhất để tránh bản ghi đổi vị trí giữa các lần chạy.

Với DECIMAL, so sánh giá trị chính xác theo scale. Với FLOAT/DOUBLE, chọn tolerance theo yêu cầu nghiệp vụ và sai số tính toán cho phép. Với JSON, xác định có cần so sánh cấu trúc sau chuẩn hóa hay chuỗi biểu diễn. Với thời gian, thống nhất timezone và độ chính xác fractional seconds.

### So sánh aggregate

Đối với truy vấn báo cáo, đối chiếu số hàng, tổng và phân nhóm:

~~~sql
SELECT
  status,
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_amount
FROM orders
WHERE created_at >= '2026-01-01'
GROUP BY status
ORDER BY status;
~~~

Có thể so sánh thêm MIN/MAX thời gian, số khách hàng duy nhất, số hàng theo tenant hoặc tổng theo ngày. Aggregate giúp phát hiện sai lệch lớn nhanh chóng, nhưng không thay thế đối chiếu từng khóa nếu cần xác định chính xác bản ghi khác nhau.

### Kiểm tra quan hệ và constraint

~~~sql
SELECT COUNT(*) AS orphan_orders
FROM orders AS o
LEFT JOIN customers AS c
  ON c.id = o.customer_id
WHERE c.id IS NULL;
~~~

Kết quả phải phù hợp quy tắc nghiệp vụ và constraint. Kiểm tra duplicate trên các khóa nghiệp vụ, hàng NULL ở cột bắt buộc và các trạng thái không hợp lệ. Đối chiếu số hàng trước/sau migration theo từng partition, tenant hoặc batch.

### Không so sánh trên dữ liệu đang thay đổi

Nếu source tiếp tục nhận ghi trong lúc thu thập kết quả, hai lần truy vấn có thể nhìn thấy hai snapshot khác nhau. Hãy restore cùng snapshot, hoặc sử dụng transaction snapshot và điểm chụp dữ liệu có thể đối chiếu. Với dữ liệu thay đổi liên tục, ghi lại watermark như GTID/binlog position hoặc batch cutover để xác định phạm vi so sánh.

Đối với truy vấn ghi, chạy test trên clone có thể reset. So sánh trạng thái trước/sau transaction, số hàng bị tác động, audit event và tác dụng phụ như trigger hoặc event. Không chạy lại một giao dịch thanh toán, gửi thông báo hoặc thao tác ngoài database trên production chỉ để đo.

## 8. Những thay đổi tương thích có thể làm kết quả khác

Khi nâng cấp giữa các phiên bản MySQL, kiểm tra các yếu tố có thể đổi ngữ nghĩa:

- **SQL mode:** strict mode, ONLY_FULL_GROUP_BY và các quy tắc xử lý ngày/giá trị không hợp lệ có thể làm truy vấn cũ phát sinh lỗi hoặc warning.
- **Character set và collation:** quy tắc so sánh, sắp xếp, phân biệt hoa/thường và dấu có thể thay đổi; điều này ảnh hưởng equality, unique key và ORDER BY.
- **Time zone:** session time_zone và system_time_zone có thể làm thay đổi cách hiển thị hoặc chuyển đổi giá trị TIMESTAMP.
- **Kiểu dữ liệu và chuyển đổi ngầm:** biểu thức so sánh chuỗi với số, độ chính xác DECIMAL/FLOAT và giá trị ngày giờ cần được kiểm tra.
- **Optimizer và thống kê:** phiên bản mới có thể chọn index, join order hoặc chiến lược materialization khác.
- **Reserved words và cú pháp:** identifier từng hợp lệ có thể trở thành từ khóa; kiểm tra tên cột, bảng và routine.
- **Authentication và privilege:** plugin xác thực, role và quyền có thể thay đổi cách client kết nối hoặc gọi routine.
- **Stored program:** kiểm tra routine, trigger, event, DEFINER, SQL SECURITY và quyền EXECUTE.

Không thay đổi SQL mode, collation hoặc optimizer_switch trong lúc benchmark chỉ để làm hai phiên bản có kết quả giống nhau. Trước hết đo với cấu hình mục tiêu của từng phiên bản; sau đó mới thử thay đổi từng biến riêng biệt để xác định nguyên nhân.

## 9. Phân tích khi plan hoặc latency regression

Khi phát hiện truy vấn chậm hơn, xử lý theo thứ tự để tránh thay đổi nhiều yếu tố cùng lúc:

1. Xác nhận workload, tham số, concurrency và trạng thái cache giữa hai lần đo tương đương.
2. So sánh EXPLAIN JSON/TREE để xác định access path, join order, estimated rows, temporary table và filesort.
3. Dùng EXPLAIN ANALYZE trên môi trường thử nghiệm để so sánh estimated rows với actual rows.
4. Kiểm tra thống kê index, histogram và thời điểm ANALYZE TABLE.
5. Xem số hàng đọc, số hàng trả về, temporary disk table, sort và lock wait trong Performance Schema.
6. Kiểm tra thay đổi schema, collation, SQL mode, optimizer_switch và cấu hình server.
7. Thử một điều chỉnh tại một thời điểm trên clone, rồi chạy lại đúng workload.
8. Ghi lại plan, số đo và kết quả trước/sau điều chỉnh để có thể review.

ANALYZE TABLE cập nhật thống kê và có thể làm optimizer chọn plan khác. Thử trên môi trường kiểm thử trước, ghi lại thời điểm chạy và so sánh thống kê trước/sau. Không chạy hàng loạt lệnh ANALYZE trên production trong lúc điều tra nếu chưa đánh giá tác động.

Index hint hoặc optimizer hint có thể hữu ích trong một trường hợp đã được chứng minh, nhưng làm tăng sự phụ thuộc vào dữ liệu và phiên bản. Ưu tiên hiểu nguyên nhân ước lượng sai, thiết kế index phù hợp và xác minh query shape trước khi cố định plan bằng hint.

## 10. Ma trận đánh giá nâng cấp

Đặt tiêu chí chấp nhận trước khi bắt đầu thử nghiệm. Ví dụ:

| Hạng mục | Điều kiện chấp nhận | Khi không đạt |
|---|---|---|
| Kết quả nghiệp vụ | Không có sai lệch ngoài khác biệt đã được phê duyệt | Dừng rollout, tìm query hoặc quy tắc bị đổi |
| SQL errors | Không có lỗi mới ở luồng quan trọng | Phân loại SQLSTATE/error code và sửa tương thích |
| Warnings | Không tăng warning nghiêm trọng hoặc bị bỏ qua | Xác định ép kiểu, truncation hoặc deprecated syntax |
| p95/p99 latency | Nằm trong SLO hoặc ngưỡng regression đã thống nhất | Phân tích digest và plan của query chậm |
| Throughput | Đạt tải mục tiêu với headroom cần thiết | Kiểm tra CPU, I/O, lock và connection pool |
| Resource usage | CPU, memory, I/O và disk không vượt ngưỡng vận hành | Điều chỉnh workload/cấu hình sau khi xác định nút thắt |
| Lock/deadlock | Không tăng vượt mức ứng dụng có thể retry an toàn | Phân tích transaction và thứ tự truy cập |
| Recovery/replication | Replica và backup vẫn đáp ứng RPO/RTO | Dừng thay đổi hoặc khắc phục đường phục hồi |

Các con số ngưỡng phải dựa trên SLO và đặc tính hệ thống. Ví dụ, một nhóm có thể đặt p95 không tăng quá 10% cho truy vấn quan trọng; đó chỉ là ngưỡng minh họa, không phải chuẩn chung. Quy định rõ số lần đo, thời lượng, tải và cách tính delta trước khi benchmark để tránh chọn số liệu có lợi sau khi đã thấy kết quả.

## 11. Quy trình kiểm thử và rollout

Một quy trình so sánh có thể triển khai như sau:

1. **Chụp baseline:** lưu version, biến cấu hình, schema, index, thống kê, digest, latency percentile, error rate và aggregate nghiệp vụ.
2. **Tạo môi trường đối chiếu:** restore cùng snapshot vào phiên bản hiện tại và phiên bản mục tiêu.
3. **Chạy kiểm tra tương thích:** migration, stored program, authentication, SQL mode, charset/collation và driver.
4. **Chạy workload:** dùng cùng tham số, concurrency, thời lượng và warm-up.
5. **Thu thập plan:** lưu EXPLAIN JSON/TREE và EXPLAIN ANALYZE cho truy vấn đại diện.
6. **Đối chiếu hiệu năng:** so sánh p50/p95/p99, throughput, rows examined, errors, warnings, CPU, I/O và lock waits.
7. **Đối chiếu kết quả:** so sánh result set, aggregate, constraint và trạng thái nghiệp vụ.
8. **Xử lý regression:** thay đổi từng yếu tố, chạy lại cùng bộ kiểm thử và ghi bằng chứng.
9. **Canary:** triển khai trên một nhóm nhỏ hoặc replica/cụm thử nghiệm, theo dõi chỉ số thực tế.
10. **Mở rộng hoặc dừng:** chỉ tiếp tục khi các tiêu chí chấp nhận đạt; giữ backup và phương án rollback/forward fix.

Với hệ thống có replication, kiểm tra cả thời gian apply, lag và trạng thái replica sau nâng cấp. Với Group Replication hoặc InnoDB Cluster, tuân theo quy trình nâng cấp topology tương ứng; không tự ý nâng cấp một thành viên theo thứ tự tùy ý mà chưa xác nhận khả năng tương thích phiên bản và quy tắc rolling upgrade.

## 12. Ghi nhớ

- So sánh trước/sau trên cùng snapshot, schema, tham số và workload.
- Dùng EXPLAIN FORMAT=JSON/TREE để xem plan; dùng EXPLAIN ANALYZE để đo iterator thực tế trên truy vấn đọc an toàn.
- Plan thay đổi không đồng nghĩa regression; cần kiểm tra actual rows, latency và throughput.
- Performance Schema digest giúp tìm truy vấn tốn thời gian, đọc nhiều hàng, lỗi và warning; nó không thay thế p95/p99 ở tầng ứng dụng.
- Đo latency dưới tải và tách cold-cache khỏi warm-cache.
- So sánh lỗi theo SQLSTATE/error code và tỷ lệ trên tổng request.
- Xác minh result set, aggregate, constraint và quan hệ nghiệp vụ trên cùng snapshot.
- Kiểm tra SQL mode, collation, timezone, kiểu dữ liệu, authentication và stored program.
- Điều tra một yếu tố mỗi lần; không ép index hoặc reset thống kê khi chưa hiểu nguyên nhân.
- Đặt ngưỡng chấp nhận trước rollout và giữ bằng chứng để review.

Một bản nâng cấp chỉ nên được chấp nhận khi dữ liệu vẫn đúng, lỗi nằm trong ngưỡng, hiệu năng đáp ứng SLO và quy trình phục hồi đã được kiểm tra. Việc lưu baseline cùng plan, metric và kết quả nghiệp vụ tạo ra bằng chứng rõ ràng để quyết định nâng cấp, điều chỉnh hoặc dừng rollout.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual: EXPLAIN](https://dev.mysql.com/doc/refman/8.0/en/explain.html)
- [MySQL 8.0 Reference Manual: EXPLAIN ANALYZE](https://dev.mysql.com/doc/refman/8.0/en/explain.html#explain-analyze)
- [MySQL 8.0 Reference Manual: Performance Schema Statement Summary Tables](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-statement-summary-tables.html)
- [MySQL 8.0 Reference Manual: Performance Schema Data Lock Waits](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-data-lock-waits-table.html)
- [MySQL 8.0 Reference Manual: Optimizer Statistics](https://dev.mysql.com/doc/refman/8.0/en/optimizer-statistics.html)
- [MySQL 8.0 Reference Manual: Server SQL Modes](https://dev.mysql.com/doc/refman/8.0/en/sql-mode.html)

