# Phân tích SQL, execution plans và truy vấn tiêu tốn tài nguyên

## 1. Mục tiêu và phạm vi

Trong chương **Quản lý và tối ưu cơ sở dữ liệu** của lộ trình Oracle Cloud Infrastructure (OCI), phân tích SQL giúp trả lời ba câu hỏi: truy vấn nào gây ảnh hưởng, phần việc nào thực sự tốn tài nguyên và thay đổi nào có thể giảm chi phí xử lý mà vẫn giữ đúng kết quả.

Sau bài này, bạn có thể:

- Xác định SQL theo mức tiêu thụ tổng, chi phí mỗi lần thực thi và tác động đến người dùng.
- Phân biệt plan ước lượng với plan của cursor đã thực thi.
- Đọc access path, join order, join method, predicate và thống kê từng bước.
- Dùng SQL ID, child cursor và khoảng đo để tránh kết luận từ dữ liệu không tương ứng.
- Liên hệ bằng chứng trong Oracle Database với giám sát, phân quyền, chi phí và tính sẵn sàng trên OCI.

Các ví dụ dùng cú pháp Oracle Database 19c và chạy trong một PDB hoặc database mà bạn có quyền truy cập. Nội dung phù hợp để học cách phân tích Oracle Database trên OCI Base Database Service, Exadata Database Service và Autonomous Database; quyền, công cụ và mức tự quản trị khác nhau giữa các dịch vụ. Các ví dụ không áp dụng nguyên xi cho MySQL HeatWave hay Oracle NoSQL Database.

Các đoạn DDL và truy vấn thực nghiệm dành cho schema lab tách biệt. Bài hướng dẫn cách thu thập và diễn giải bằng chứng, không yêu cầu thay đổi hàng loạt database đang phục vụ ứng dụng.

## 2. Truy vấn chậm và truy vấn tốn tài nguyên

Một API phản hồi chậm chưa đủ để kết luận SQL có plan kém. Độ trễ quan sát từ ứng dụng có thể bao gồm:

~~~text
Thời gian phản hồi ứng dụng
  = chờ lấy connection
  + truyền yêu cầu
  + xử lý trong database
  + truyền và fetch kết quả
  + xử lý tại ứng dụng
~~~

Đây là mô hình phân rã để điều tra, không phải cách cộng trực tiếp các counter trong Oracle. Với tác vụ đồng thời hoặc parallel execution, các phần việc có thể chồng lấp.

Cần phân biệt ba mục tiêu:

| Mục tiêu | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Giảm độ trễ | Người dùng phải đợi bao lâu? | Một giao dịch thanh toán mất 8 giây |
| Giảm tải tổng | SQL chiếm bao nhiêu tài nguyên trong khoảng đo? | Một truy vấn chạy 100.000 lần trong 10 phút |
| Tăng năng lực phục vụ | Database chịu được bao nhiêu yêu cầu đồng thời? | Tải tăng gấp đôi làm connection pool bão hòa |

Ví dụ giả định, chỉ xét phần xử lý nối tiếp và các lần chạy đã hoàn tất:

- SQL A dùng 4 giây mỗi lần, chạy 10 lần: tổng khoảng 40 giây.
- SQL B dùng 20 mili giây mỗi lần, chạy 100.000 lần: tổng khoảng 2.000 giây.

Nếu mục tiêu là giảm CPU toàn hệ thống, B có thể đáng ưu tiên hơn A. Nếu A nằm trên luồng thanh toán quan trọng, A vẫn cần xử lý sớm theo yêu cầu nghiệp vụ. Danh sách “top SQL” vì thế phải gắn với khoảng thời gian và mục tiêu cụ thể.

Không dùng `COST` của optimizer thay cho thời gian đo được. Cost phục vụ lựa chọn phương án trong mô hình optimizer; cost 100 không có nghĩa truy vấn mất 100 mili giây.

## 3. Chuẩn bị đúng phạm vi trên OCI

### 3.1. Hai lớp phân quyền độc lập

Quyền OCI IAM cho phép người vận hành truy cập tài nguyên hoặc thao tác dịch vụ theo tenancy, compartment và policy. Quyền Oracle Database quyết định tài khoản có thể đọc view, truy cập bảng hay thực thi package nào. Có quyền xem database trong OCI Console không tự động cấp quyền đọc `V$SQL` qua kết nối SQL.

Trước khi đo, ghi nhận:

- Region, compartment, database hoặc DB system và service kết nối.
- PDB, schema, phiên bản database và instance nếu dùng RAC.
- Múi giờ của log ứng dụng, khoảng sự cố và mã yêu cầu cần truy vết.
- Cách kết nối được phép qua VCN/private endpoint, VPN hoặc đường truy cập đã cấu hình.
- Tài khoản chẩn đoán và mức quyền được DBA cấp.

Với `DBMS_XPLAN.DISPLAY_CURSOR`, Oracle nêu các view cần quyền `SELECT` hoặc `READ`, gồm `V$SQL_PLAN`, `V$SESSION`, `V$SQL_PLAN_STATISTICS_ALL` và `V$SQL`. DBA cấp quyền trên các đối tượng nền tương ứng khi phù hợp; không mặc định cấp `DBA` chỉ để đọc plan. Xem [mô hình bảo mật của DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html).

### 3.2. Kiểm tra công cụ và quyền sử dụng

Một số chức năng chẩn đoán liên quan đến Oracle Diagnostics Pack hoặc Oracle Tuning Pack. AWR/ASH thuộc nhóm chức năng Diagnostics Pack; SQL Tuning Advisor và Real-Time SQL Monitoring thuộc Tuning Pack. Quyền sử dụng phụ thuộc edition, dịch vụ và hợp đồng; tham số bật tính năng không thay thế quyền sử dụng hợp lệ. Đối chiếu [Licensing Information của Oracle Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html) trước khi chọn công cụ.

Trong OCI Database Management, kiểm tra thêm loại database, phiên bản, management option và credential. Không mặc định mọi màn hình hay thao tác đều có trên mọi dịch vụ. Oracle công bố riêng [ma trận hỗ trợ tính năng](https://docs.oracle.com/en-us/iaas/database-management/doc/database-management-feature-support-matrix.html).

Các ví dụ `V$SQL`, `V$SESSION` và plan cursor tạo một luồng học bằng kết nối SQL khi quyền cho phép. Bài không yêu cầu bật AWR/ASH hoặc SQL Monitoring để hoàn thành lab.

## 4. Nhận diện đúng SQL trước khi xem plan

Một câu SQL có thể có nhiều child cursor. Khác biệt về kiểu bind, môi trường optimizer hoặc khả năng chia sẻ cursor có thể dẫn đến các child khác nhau. Khi điều tra, lưu định danh đủ để lần đo có ý nghĩa:

| Thông tin | Dùng để làm gì? |
| --- | --- |
| SQL ID | Nhận diện parent cursor của SQL |
| Child number | Chọn child cursor đang phân tích |
| Plan hash value | Sàng lọc thay đổi cấu trúc plan |
| Schema, PDB | Xác định đúng đối tượng và ngữ cảnh |
| Instance | Chọn đúng nơi thực thi trong RAC |
| Thời điểm và bind đại diện | Phân biệt các lần chạy và nhóm dữ liệu |

SQL ID không phải mã định danh riêng của một lần thực thi. Hai lần chạy cùng SQL có thể dùng bind khác nhau và tốn tài nguyên rất khác nhau.

Plan hash value hữu ích khi phát hiện plan thay đổi, nhưng không mô tả đầy đủ mọi khác biệt về predicate, bind, môi trường và dữ liệu. Khi nghi ngờ regression, xem toàn văn plan cùng runtime statistics và bối cảnh, thay vì chỉ so hai con số hash.

~~~text
Ví dụ cùng SQL ID:
  child 0 → phục vụ nhóm khách hàng ít dữ liệu
  child 1 → phục vụ nhóm khách hàng có lịch sử rất lớn

Câu hỏi cần đặt:
  sự cố thuộc child nào, ở instance nào, vào thời điểm nào?
~~~

Trong RAC, `V$` cho góc nhìn instance hiện tại; khi có quyền và cần nhìn toàn cluster, sử dụng view `GV$` tương ứng và giữ `INST_ID` trong định danh. Trong môi trường multitenant, giữ đúng container/PDB; không gộp số liệu giữa các phạm vi rồi coi đó là một workload duy nhất.

## 5. Tìm SQL tiêu tốn tài nguyên

### 5.1. Các chỉ số cần biết

`V$SQL` cung cấp thống kê theo child cursor. Một số cột thường dùng:

| Cột | Ý nghĩa chính |
| --- | --- |
| `EXECUTIONS` | Số lần thực thi |
| `END_OF_FETCH_COUNT` | Số lần hoàn tất lấy kết quả |
| `ELAPSED_TIME` | Thời gian tích lũy, microsecond |
| `CPU_TIME` | CPU time tích lũy, microsecond |
| `BUFFER_GETS` | Logical buffer gets |
| `DISK_READS` | Số lần đọc đĩa được ghi nhận |
| `ROWS_PROCESSED` | Số dòng đã xử lý |
| `PARSE_CALLS` | Số lần parse |
| `LAST_ACTIVE_TIME` | Thời điểm hoạt động gần nhất |

Đây là counter tích lũy của cursor trong cache. Với parallel execution, `ELAPSED_TIME` cộng thời gian query coordinator và worker, nên không phải wall-clock latency của ứng dụng. Xem định nghĩa tại [V$SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html).

`BUFFER_GETS` cao cho thấy nhiều công việc truy cập block logic, kể cả khi cache giúp giảm đọc vật lý. `DISK_READS` không chuyển trực tiếp thành số thao tác I/O hay chi phí lưu trữ mà biểu đồ OCI đang hiển thị; trước tiên phải đối chiếu đơn vị, tầng đo và khoảng lấy mẫu.

### 5.2. Truy vấn sàng lọc trong cursor cache

Ví dụ SQL*Plus/SQLcl dùng một bind chứa schema ứng dụng. Thay `APP_SCHEMA` bằng tên schema thực tế, đúng kiểu chữ lưu trong dictionary.

~~~sql
VARIABLE p_schema VARCHAR2(128);
EXEC :p_schema := 'APP_SCHEMA';

SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       end_of_fetch_count,
       ROUND(elapsed_time / 1e6, 3) AS elapsed_s_total,
       ROUND(cpu_time / 1e6, 3) AS cpu_s_total,
       buffer_gets,
       disk_reads,
       ROUND(elapsed_time / NULLIF(executions, 0) / 1e3, 3)
         AS elapsed_ms_per_exec,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
         AS gets_per_exec,
       rows_processed,
       parse_calls,
       last_active_time,
       SUBSTR(sql_text, 1, 160) AS sql_sample
FROM   v$sql
WHERE  parsing_schema_name = :p_schema
AND    executions > 0
AND    last_active_time >= SYSDATE - 15 / 1440
ORDER BY elapsed_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Điều kiện 15 phút chỉ chọn cursor còn hoạt động gần đây. Các counter vẫn có thể chứa hoạt động từ nhiều giờ trước; đây **không phải báo cáo tổng tiêu thụ của 15 phút vừa qua**.

Dùng danh sách để chọn ứng viên, rồi đo theo khoảng ở mục tiếp theo. Có thể đổi thứ tự sắp xếp sang CPU hoặc buffer gets tùy câu hỏi. Một dòng SQL bị cắt ngắn chưa đủ để sửa truy vấn; lấy `SQL_FULLTEXT` cho đúng SQL ID và child đã chọn.

Tỷ lệ chia cho `EXECUTIONS` là chỉ dấu tổng hợp. Khi có thực thi đang chạy, bị hủy hoặc chỉ fetch một phần, tỷ lệ có thể không đại diện cho một lần hoàn tất. `END_OF_FETCH_COUNT` giúp phát hiện tình huống này; cũng không nên tùy tiện thay mẫu số bằng số lần hoàn tất vì tử số vẫn có thể gồm công việc của các lần chưa hoàn tất.

### 5.3. Đo delta trong một cửa sổ thời gian

Để biết SQL nào gây tải trong 5 phút xảy ra sự cố, lấy hai snapshot của cùng counter ở đầu và cuối khoảng đo.

~~~text
delta_executions = executions_t1 - executions_t0
delta_elapsed_s = (elapsed_time_t1 - elapsed_time_t0) / 1.000.000
delta_cpu_s = (cpu_time_t1 - cpu_time_t0) / 1.000.000
delta_gets = buffer_gets_t1 - buffer_gets_t0

Nếu delta_executions > 0:
  elapsed_ms_per_exec_trong_khoang
    = 1.000 × delta_elapsed_s / delta_executions
~~~

Ví dụ giả định cho một child cursor ổn định trong khoảng đo:

| Chỉ số | t0 | t1 | Delta |
| --- | ---: | ---: | ---: |
| Executions | 1.000 | 1.500 | 500 |
| Elapsed time, microsecond | 10.000.000 | 25.000.000 | 15.000.000 |
| CPU time, microsecond | 6.000.000 | 14.000.000 | 8.000.000 |
| Buffer gets | 2.000.000 | 3.500.000 | 1.500.000 |

Trong khoảng này, SQL dùng 15 giây elapsed tích lũy, 8 giây CPU và 3.000 buffer gets mỗi execution theo tỷ lệ tổng hợp. Giá trị trung bình elapsed là 30 mili giây, chưa nói được p95/p99.

Khi ghép snapshot, ngoài SQL ID/child, giữ instance, container và dấu hiệu vòng đời cursor như địa chỉ, thời điểm load. Cursor có thể bị aging, reload hoặc invalidation; không lấy hai bản ghi có bộ đếm khác vòng đời để trừ nhau. Delta âm hoặc cursor không xuất hiện ở một đầu khoảng đo phải được đánh dấu không đủ dữ liệu, không ép về 0 để “làm sạch” kết quả.

Thực thi dài bắc qua ranh giới snapshot cũng làm tỷ lệ theo execution khó diễn giải. Với một lần chạy cụ thể, cần bằng chứng theo execution hoặc phép đo ở ứng dụng, thay vì suy ra toàn bộ từ trung bình cursor.

## 6. Phân biệt đang dùng CPU, chờ I/O và bị khóa

Trước khi đổi index hoặc tăng tài nguyên OCI, xem các session đang hoạt động:

~~~sql
SELECT sid,
       serial#,
       username,
       service_name,
       module,
       action,
       sql_id,
       sql_child_number,
       sql_exec_start,
       state,
       wait_class,
       event,
       blocking_session_status,
       blocking_instance,
       blocking_session
FROM   v$session
WHERE  type = 'USER'
AND    status = 'ACTIVE'
ORDER BY sql_exec_start NULLS LAST;
~~~

Diễn giải `EVENT` cùng `STATE`: khi session không ở trạng thái `WAITING`, event có thể mô tả lần chờ trước đó. Một ảnh chụp không chứng minh session đang chạy CPU liên tục. Định nghĩa các trường nằm trong [V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html).

Các hướng điều tra sau là giả thuyết cần kiểm chứng:

| Bằng chứng quan sát | Hướng điều tra tiếp |
| --- | --- |
| CPU tăng cùng delta buffer gets lớn | Quét nhiều dữ liệu, biểu thức, join lặp hoặc quá nhiều lần gọi |
| User I/O wait nổi bật | Lượng đọc, access path, cache và độ trễ lưu trữ |
| Chờ khóa, có blocker hợp lệ | Giao dịch giữ khóa, thứ tự cập nhật, thời điểm commit |
| TEMP tăng khi sort/hash | Dữ liệu trung gian lớn, ước lượng sai, workarea |
| Connection pool chờ nhưng DB ít tải | Giữ connection lâu, giới hạn pool, luồng ứng dụng |
| Cluster wait trên RAC | Truy cập block giữa instance và phân bố workload |

Ví dụ, một `UPDATE` có index đúng vẫn có thể chờ vì giao dịch khác chưa commit. Xóa session chặn có thể kéo theo rollback dài và tác động nghiệp vụ; bằng chứng về blocker cần dẫn đến phân tích transaction, không phải quyết định tự động ngắt session.

Nếu có quyền sử dụng Real-Time SQL Monitoring, chọn đúng lần thực thi bằng tổ hợp SQL ID, SQL execution start và SQL execution ID, cùng bối cảnh database/instance. Báo cáo giúp xem một execution đang tiêu thời gian ở đâu; không phải mọi SQL đều được monitor. Xem [Monitoring Database Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/monitoring-database-operations.html).

## 7. Plan ước lượng và plan của cursor thực thi

### 7.1. EXPLAIN PLAN trả lời điều gì?

`EXPLAIN PLAN` cho biết optimizer dự kiến thực hiện SQL như thế nào trong môi trường explain. Lệnh không chạy truy vấn để đo runtime.

Ví dụ sau giả định bảng lab ở mục 12 đã được tạo:

~~~sql
EXPLAIN PLAN SET STATEMENT_ID = 'OCI_SQL_RANGE_EST' FOR
SELECT COUNT(*) AS order_count,
       SUM(amount) AS order_total
FROM   perf_orders
WHERE  order_date >= DATE '2026-06-15'
AND    order_date <  DATE '2026-06-16'
AND    status = 'PAID';

SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY(
    table_name   => 'PLAN_TABLE',
    statement_id => 'OCI_SQL_RANGE_EST',
    format       => 'TYPICAL +PREDICATE'
  )
);
~~~

Plan này chưa chứa bằng chứng đã xử lý bao nhiêu dòng hay tiêu bao nhiêu buffer gets. Môi trường thực thi có thể khác về bind, schema, statistics hoặc tham số. Oracle giải thích sự khác biệt trong [Explaining and Displaying Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html).

### 7.2. DISPLAY_CURSOR trả lời điều gì?

`DBMS_XPLAN.DISPLAY_CURSOR` đọc plan của cursor trong cache. Muốn có thống kê từng row source, phải thu thập chúng khi chạy câu lệnh; chỉ thêm tùy chọn hiển thị sau đó không tạo ra số liệu quá khứ.

Trong một lần thử có kiểm soát, dùng hint ở SQL cần đo:

~~~sql
SELECT /*+ gather_plan_statistics */ /* OCI_SQL_DEMO */
       COUNT(*)
FROM   perf_orders
WHERE  order_date >= DATE '2026-06-15'
AND    order_date <  DATE '2026-06-16';
~~~

Sau đó xem đúng cursor:

~~~sql
VARIABLE p_sql_id VARCHAR2(13);
VARIABLE p_child NUMBER;

-- Thay bằng SQL ID và child thực tế đã thu thập.
EXEC :p_sql_id := 'THAY_SQL_ID';
EXEC :p_child := 0;

SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id          => :p_sql_id,
    cursor_child_no => :p_child,
    format          => 'ALLSTATS LAST +PREDICATE +ALIAS'
  )
);
~~~

`ALLSTATS` hiển thị I/O và memory statistics khi có dữ liệu; `LAST` chọn thống kê lần thực thi gần nhất của cursor. Trong workload chạy đồng thời, “gần nhất” có thể không phải lần của người điều tra. Kết hợp cửa sổ đo, bind và định danh execution khi công cụ hỗ trợ, hoặc tái hiện trong session lab riêng.

Không bật `STATISTICS_LEVEL=ALL` trên toàn database chỉ để đo một SQL. Hint thu thập thống kê cũng có overhead và làm thay đổi SQL text, nên SQL ID của bản có hint có thể khác bản ứng dụng.

## 8. Đọc execution plan theo cây

Plan là cây các row source: bước cha yêu cầu dữ liệu từ bước con, rồi lọc, ghép, sắp xếp hoặc tổng hợp. Độ thụt lề thể hiện quan hệ cha–con; số `Id` không phải thứ tự hoàn thành.

Với nhánh một con như table access qua index, nhìn xuống để thấy nơi dữ liệu được tìm rồi đi lên để thấy cách xử lý. Với join hoặc nhiều nhánh, xét cơ chế vận hành của operator. Quy tắc “đọc từ dòng cuối lên đầu” không mô tả đầy đủ thứ tự thực thi mọi plan.

### 8.1. Những operator thường gặp

| Operator | Ý nghĩa khi đọc plan | Câu hỏi cần đặt |
| --- | --- | --- |
| `TABLE ACCESS FULL` | Quét bảng | Có thực sự cần phần lớn dữ liệu không? |
| `INDEX RANGE SCAN` | Tìm dải entry trong index | Access predicate giới hạn được bao nhiêu? |
| `INDEX UNIQUE SCAN` | Tra cứu khóa duy nhất | Có phải mỗi lần chỉ tìm rất ít dòng? |
| `TABLE ACCESS BY INDEX ROWID` | Đọc dòng bảng từ ROWID | Có nhiều lượt đọc rải rác không? |
| `INDEX FAST FULL SCAN` | Đọc rộng trên index | Index có đủ cột cần dùng không? |
| `SORT ORDER BY`, `HASH GROUP BY` | Sắp xếp, tổng hợp | Bao nhiêu dữ liệu đi vào, có dùng TEMP không? |
| `PARTITION RANGE ...` | Truy cập các partition | Phạm vi partition có được thu hẹp không? |
| `PX ...` | Phối hợp parallel execution | Công việc phân phối giữa worker ra sao? |

Full scan có thể hiệu quả với bảng nhỏ, báo cáo đọc phần lớn bảng hoặc nền tảng có cơ chế quét phù hợp. Index scan trả hàng triệu ROWID có thể đắt hơn một lần quét liên tục. Xem các lựa chọn nền tảng tại [Optimizer Access Paths](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html).

### 8.2. Join method đi cùng lượng dữ liệu

- **Nested loops:** lặp trên đầu vào ngoài, dùng mỗi dòng để tìm ở đầu vào trong. Xem số lần khởi động nhánh trong và chi phí mỗi lần tra cứu.
- **Hash join:** tạo cấu trúc hash từ một đầu vào rồi đối chiếu đầu vào còn lại. Xem kích thước dữ liệu và workarea, nhất là khi có spill.
- **Sort merge join:** xử lý hai đầu vào theo thứ tự khóa join. Xem dữ liệu đã có thứ tự hay phải sort lớn.

Không có join method luôn nhanh nhất. Chọn lựa phụ thuộc số dòng, điều kiện join, access path và tài nguyên. Oracle mô tả các cơ chế tại [Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/joins.html).

### 8.3. Access predicate và filter predicate

~~~text
access("ORDER_DATE">=:FROM_DATE AND "ORDER_DATE"<:TO_DATE)
filter("STATUS"='PAID')
~~~

Access predicate tham gia cách tìm hoặc giới hạn vùng dữ liệu tại operator đó. Filter predicate loại các dòng không đạt điều kiện tại nơi được hiển thị. Điều kiện xuất hiện trong filter không tự nó chứng minh có lỗi: vấn đề là bao nhiêu dòng/block đã phải đọc trước khi loại bỏ.

Đọc cả `Predicate Information`, `Note`, alias và thông tin partition. Chúng có thể giải thích implicit conversion, dynamic statistics, statistics feedback hoặc nhánh adaptive; chỉ nhìn tên operator dễ bỏ sót nguyên nhân.

## 9. So sánh ước lượng với số liệu thực thi

### 9.1. Các cột runtime quan trọng

| Cột | Cách dùng |
| --- | --- |
| `Starts` | Số lần operator được khởi động |
| `E-Rows` | Số dòng optimizer ước lượng |
| `A-Rows` | Số dòng operator thực sự xuất ra |
| `A-Time` | Thời gian đo ở row source |
| `Buffers` | Công việc buffer tại bước |
| `Reads` | Đọc vật lý được báo cáo |
| Memory/TEMP | Nhu cầu workarea và dấu hiệu spill, nếu có |

Không cộng `A-Time` của mọi dòng để tính thời gian SQL: thời gian các nhánh có thể bao hàm nhau, còn parallel execution có chồng lấp. Cũng không cộng toàn bộ `Buffers` dọc cây để có tổng mới vì dễ đếm lặp công việc ở cấp cha và con.

Với row source được khởi động nhiều lần, xét cùng cơ sở:

~~~text
Số dòng thực tế trung bình mỗi start = A-Rows / Starts
~~~

Đối chiếu giá trị này với `E-Rows` của row source phù hợp, thay vì so trực tiếp `A-Rows` tích lũy với ước lượng mỗi lần. Khi `Starts = 0`, operator chưa được chạy trong số liệu đang xem; không chia cho 0 hoặc coi đây là nhánh đã đọc nhưng không tìm thấy dữ liệu.

### 9.2. Ví dụ plan rút gọn

Bảng dưới là **số liệu giả lập để luyện đọc**, không phải kết quả đã chạy trên OCI:

~~~text
Id  Operation                         Starts  E-Rows  A-Rows   Buffers
 0  SELECT STATEMENT                       1          500000   1500400
 1    NESTED LOOPS                          1      40  500000   1500400
 2      TABLE ACCESS FULL CUSTOMERS        1      20  100000       400
 3      TABLE ACCESS BY INDEX ROWID    100000       2  500000   1500000
 4        INDEX RANGE SCAN ORDERS_CUST_IX
                                      100000       2  500000    400000
~~~

Cách lập luận:

1. Nhánh ngoài ở Id 2 được ước lượng 20 dòng nhưng xuất ra 100.000 dòng.
2. Nhánh trong bị khởi động 100.000 lần. Mỗi lần không nhất thiết đắt, nhưng tổng công việc lớn.
3. Tại Id 4, trung bình thực tế là 500.000 / 100.000 = 5 dòng mỗi start, so với ước lượng 2. Sai lệch này khác về mức độ so với sai lệch 20 thành 100.000 ở Id 2.
4. Điểm cần điều tra sớm là predicate và ước lượng của nhánh ngoài: dữ liệu lệch, statistics chưa phù hợp hay điều kiện có tương quan?
5. Thử lại phương án trên dữ liệu đại diện. Chưa đủ bằng chứng để chỉ thêm hint ép hash join.

Đây là cách lần ngược từ lượng công việc đến nơi bắt đầu phình dữ liệu. Operator có nhiều buffer nhất có thể đang chịu hậu quả của một ước lượng sai ở phía trước.

## 10. Các nguyên nhân thường gặp và cách kiểm chứng

### 10.1. Statistics thiếu, cũ hoặc không diễn tả đúng dữ liệu

Optimizer cần thông tin về quy mô bảng, phân bố giá trị và index. Sau một đợt nạp dữ liệu lớn, ước lượng có thể không còn phản ánh thực tế. Histogram có thể mô tả dữ liệu lệch; extended statistics có thể hỗ trợ các cột có tương quan. Xem [Optimizer Statistics Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html).

Ví dụ tự xây dựng: 95% đơn hàng có trạng thái `PAID`, còn 0,1% là `FAILED`. Đường truy cập tốt cho `FAILED` chưa chắc hiệu quả cho `PAID`.

Một ví dụ khác: `country_code` và `province_code` có tương quan. Ước lượng hai điều kiện như hai sự kiện độc lập có thể đánh giá sai lượng dữ liệu kết hợp.

Kiểm tra thời điểm thống kê, quy mô hiện tại, phân bố dữ liệu và nơi E-Rows lệch A-Rows. Không thu thập lại toàn bộ schema như phản xạ đầu tiên: cập nhật statistics có thể làm SQL khác đổi plan. Thực hiện thay đổi có phạm vi, số liệu trước–sau và phương án khôi phục statistics do DBA quản lý.

### 10.2. Bind và các nhóm dữ liệu rất khác nhau

Bind giúp ứng dụng tái sử dụng SQL, nhưng không làm mọi giá trị có cùng chi phí. Bind peeking và adaptive cursor sharing là các cơ chế cần hiểu khi phân tích nhiều child cursor. Xem [Improving Real-World Performance Through Cursor Sharing](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/improving-rwp-cursor-sharing.html).

Ví dụ, cùng truy vấn theo `customer_id`, một khách có 5 đơn hàng còn khách khác có 500.000 đơn. Chỉ thử với khách ít dữ liệu có thể bỏ sót vấn đề ở nhóm lớn.

Lưu kiểu bind và nhóm phân bố, đồng thời che dữ liệu nhạy cảm. Trong ứng dụng Java, kiểm tra `PreparedStatement` và kiểu setter tương ứng với kiểu cột. Đừng chuyển tất cả bind sang literal để xử lý một regression vì có thể tăng số SQL và áp lực parse.

### 10.3. Hàm trên cột và implicit conversion

Điều kiện sau có thể làm khó việc dùng B-tree index thông thường trên cột ngày:

~~~sql
WHERE TRUNC(order_date) = DATE '2026-06-15'
~~~

Nếu yêu cầu là lấy toàn bộ ngày với cột Oracle `DATE`, dạng khoảng nửa mở giữ ý nghĩa rõ ràng:

~~~sql
WHERE order_date >= DATE '2026-06-15'
AND   order_date <  DATE '2026-06-16'
~~~

Đây là ứng viên để kiểm chứng bằng plan, không phải cam kết optimizer luôn chọn index. Function-based index hoặc phép biến đổi optimizer có thể làm tình huống khác đi. Với `TIMESTAMP WITH TIME ZONE` hoặc yêu cầu “ngày theo múi giờ người dùng”, xác định ranh giới thời gian đúng trước khi viết lại.

Với implicit conversion, đọc predicate để biết hàm chuyển đổi nằm trên cột hay bind. Bind có kiểu không phù hợp có thể làm đổi access path, selectivity hoặc phát sinh lỗi dữ liệu. Sửa kiểu ở chỗ truyền tham số và kiểm tra lại tính đúng của kết quả.

### 10.4. Đọc quá nhiều dữ liệu hoặc gọi SQL quá nhiều lần

Những vấn đề sau không luôn cần index mới:

- `SELECT *` khi chỉ cần vài cột làm tăng dữ liệu đọc và truyền.
- Vòng lặp ứng dụng thực hiện một SQL cho mỗi bản ghi làm số execution tăng mạnh.
- Join sai điều kiện có thể nhân bản số dòng.
- Báo cáo đọc toàn lịch sử dù nghiệp vụ chỉ cần một kỳ.
- Phân trang sâu có thể phải bỏ qua lượng kết quả lớn trước khi trả trang cần xem.

Đối chiếu số dòng nghiệp vụ cần với số dòng và số block đã xử lý. Một SQL nhanh hơn 10% chưa chắc có lợi bằng giảm 90% số lần gọi thừa; thay đổi ứng dụng vẫn phải giữ nguyên quyền truy cập dữ liệu và ý nghĩa nghiệp vụ.

### 10.5. Sort, hash và parallel execution

Khi một bước sort/hash xử lý tập dữ liệu lớn, kiểm tra lượng dòng đi vào trước khi bàn tăng PGA. Nếu join sai đã tạo dữ liệu trung gian lớn gấp 100 lần dự kiến, tăng bộ nhớ chỉ xử lý phần ngọn.

Parallel execution có thể giảm thời gian một báo cáo nhưng tăng lượng CPU, I/O hoặc TEMP cùng lúc, làm giao dịch khác chậm đi. Trên OCI, đo cả mức tiêu thụ và tác động tới workload chung; không đồng nhất thời gian chạy ngắn hơn với chi phí thấp hơn.

## 11. Kết hợp phân tích SQL với công cụ OCI

Một quy trình điều tra thực tế:

~~~mermaid
flowchart TD
    A["Chọn khoảng sự cố và yêu cầu nghiệp vụ"] --> B["Đối chiếu chỉ số ứng dụng và database"]
    B --> C["Khoanh vùng SQL, session và loại chờ"]
    C --> D["Chọn đúng cursor hoặc execution"]
    D --> E["Đọc plan, predicate và runtime statistics"]
    E --> F["Lập giả thuyết có thể kiểm chứng"]
    F --> G["Thử một thay đổi trong môi trường phù hợp"]
    G --> H["So kết quả, độ trễ, tài nguyên và ảnh hưởng chung"]
~~~

Trong Database Management hoặc Performance Hub khi được hỗ trợ và có quyền sử dụng:

1. Chọn đúng region, compartment, database/PDB và khoảng thời gian.
2. Xem hoạt động theo SQL và loại chờ để tìm ứng viên.
3. Mở SQL details, đối chiếu plan và các lần thực thi nếu có dữ liệu.
4. Liên hệ thời điểm triển khai ứng dụng, thay đổi statistics hoặc thay đổi hạ tầng.
5. Ghi lại bằng chứng đủ để người khác tái hiện việc lựa chọn SQL.

SQL Tuning Advisor có thể đề xuất statistics, index, viết lại SQL, SQL profile hoặc plan baseline. Xem đề xuất như đầu vào đánh giá; lợi ích ước tính không thay thế đo workload và kiểm tra kết quả. Tài liệu [Analyze SQL with SQL Tuning Advisor](https://docs.oracle.com/en-us/iaas/database-management/doc/analyze-sql-sql-tuning-advisor.html) mô tả luồng chọn SQL, chạy tác vụ và xem khuyến nghị trong OCI.

Việc liên hệ với Compute, lưu trữ và chi phí có ý nghĩa ở bước này:

- CPU database tăng cùng SQL đọc nhiều block là bằng chứng khác với CPU máy ứng dụng tăng.
- I/O latency cần xem cùng lượng I/O, throughput và tầng lưu trữ cụ thể.
- Với Exadata, đặc điểm xử lý tại storage có thể đổi cách đánh giá scan.
- Với Autonomous Database, ưu tiên thao tác được dịch vụ cung cấp; không giả định có quyền sửa hệ điều hành hoặc mọi tham số database.
- Khi theo dõi chi phí, so workload đã hoàn thành trên cùng đơn vị tính phí và cấu hình; không suy chi phí tiền từ buffer gets.

Nếu tự động thu thập số liệu, giữ đồng nhất schema, cửa sổ đo và định danh; giới hạn tần suất, thời gian lưu và lượng SQL text. Dùng tài khoản chẩn đoán được quản lý, không ghi mật khẩu hoặc bind nhạy cảm vào script và báo cáo. Các job giám sát cũng cần được theo dõi overhead.

## 12. Thực hành: đối chiếu predicate với số liệu thực thi

### 12.1. Chuẩn bị schema lab

Lab tạo 200.000 dòng giả lập trong schema hiện tại, một index và statistics của chính bảng đó. Cần quyền tạo bảng/index, quota lưu trữ và quyền dùng các view chẩn đoán. DDL có thể tự commit; thực hiện trong schema lab không có giao dịch nghiệp vụ.

Nếu tên `PERF_ORDERS` đã tồn tại, chọn schema lab khác hoặc dừng để xác định chủ sở hữu, không xóa đối tượng sẵn có.

~~~sql
CREATE TABLE perf_orders (
  order_id    NUMBER         NOT NULL,
  customer_id NUMBER         NOT NULL,
  order_date  DATE           NOT NULL,
  status      VARCHAR2(12)   NOT NULL,
  amount      NUMBER(12, 2)  NOT NULL,
  CONSTRAINT perf_orders_pk PRIMARY KEY (order_id)
);

INSERT INTO perf_orders (
  order_id, customer_id, order_date, status, amount
)
SELECT LEVEL,
       MOD(LEVEL - 1, 10000) + 1,
       DATE '2026-01-01'
         + MOD(LEVEL - 1, 365)
         + MOD(LEVEL - 1, 86400) / 86400,
       CASE WHEN MOD(LEVEL, 20) = 0
            THEN 'PENDING'
            ELSE 'PAID'
       END,
       100 + MOD(LEVEL, 1000)
FROM dual
CONNECT BY LEVEL <= 200000;

COMMIT;

CREATE INDEX perf_orders_date_ix
    ON perf_orders(order_date);

BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'PERF_ORDERS',
    cascade => TRUE
  );
END;
/
~~~

Đây là dữ liệu tổng hợp để quan sát đường truy cập, không đại diện kích thước, độ lệch hay concurrency của production. Script được trình bày để người học thực hành; bài không khẳng định đã chạy trên một database OCI thực.

### 12.2. Đo truy vấn dùng TRUNC

Chạy câu sau và lấy hết kết quả. Truy vấn tổng hợp trả một dòng, giúp tránh việc công cụ chỉ fetch trang đầu của một tập lớn.

~~~sql
SELECT /*+ gather_plan_statistics */ /* OCI_SQL_LAB_TRUNC */
       COUNT(*) AS order_count,
       SUM(amount) AS order_total
FROM   perf_orders
WHERE  TRUNC(order_date) = DATE '2026-06-15'
AND    status = 'PAID';
~~~

Trong session lab riêng, chạy ngay lệnh sau, không chủ động chạy SQL khác xen giữa:

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST +PREDICATE'
  )
);
~~~

Kiểm tra phần đầu output có đúng SQL mang nhãn `OCI_SQL_LAB_TRUNC`. Một số công cụ có thể chạy SQL nền, khiến mặc định “cursor gần nhất” không trỏ đến câu vừa đo.

Khi cần tìm rõ định danh, dùng:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       last_active_time
FROM   v$sql
WHERE  parsing_schema_name = USER
AND    sql_text LIKE
         'SELECT /*+ gather_plan_statistics */ /* OCI_SQL_LAB_TRUNC */%'
ORDER BY last_active_time DESC;
~~~

Sau đó gọi `DISPLAY_CURSOR` với SQL ID và child thực tế như mục 7. Nếu đã thử nhiều lần hoặc có session khác chạy cùng câu, xác nhận đúng lần đo; nhãn không tự tạo sự cô lập.

Lưu `order_count`, `order_total`, plan, predicate, `Starts`, `E-Rows`, `A-Rows` và `Buffers`. Quan sát operator đọc bảng, không chỉ dòng tổng hợp ở trên cùng: trả một dòng không có nghĩa database chỉ đọc một dòng.

### 12.3. Đo truy vấn dùng khoảng ngày

~~~sql
SELECT /*+ gather_plan_statistics */ /* OCI_SQL_LAB_RANGE */
       COUNT(*) AS order_count,
       SUM(amount) AS order_total
FROM   perf_orders
WHERE  order_date >= DATE '2026-06-15'
AND    order_date <  DATE '2026-06-16'
AND    status = 'PAID';
~~~

Lấy kết quả rồi hiển thị plan ngay trong session lab:

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST +PREDICATE'
  )
);
~~~

Xác nhận nhãn `OCI_SQL_LAB_RANGE`. Khi tra lại định danh, dùng truy vấn tìm cursor ở trên và đổi nhãn cho phù hợp.

Kết quả cần kiểm chứng:

- Hai phiên bản có cùng `order_count` và `order_total`.
- Predicate của bản khoảng ngày có cho phép giới hạn vùng trên `ORDER_DATE` hay không.
- Optimizer chọn full scan hay index, và lượng `Buffers` đổi thế nào.
- Sai lệch giữa số dòng ước lượng và thực tế có đáng chú ý không.
- Chênh lệch thời gian có lặp lại hay chủ yếu do cache và nhiễu đo.

Không đặt trước điều kiện “bản RANGE bắt buộc dùng index”. Tùy bố trí dữ liệu, thống kê, cache và môi trường, full scan vẫn có thể được chọn. Lab đạt mục tiêu khi bạn giải thích được bằng chứng quan sát, kể cả khi hai bản cùng access path.

Nếu A-Rows không hiển thị, kiểm tra hint có nằm trong câu đã chạy, cursor có đúng không và quyền có đủ không. Ô trống không có nghĩa số dòng bằng 0.

### 12.4. So sánh công bằng

Chạy một lượt làm quen, rồi đo vài lượt mỗi phiên bản, luân phiên thứ tự. Giữ nguyên dữ liệu, session, service và mức concurrency. Không flush buffer cache hay shared pool của database dùng chung để tạo “cold run”.

Dùng bảng sau; các ô để trống vì phải lấy số thật từ môi trường của bạn:

| Phiên bản | Lượt | Count/Sum | Plan hash | Buffers ở cấp SQL | Reads | Thời gian client |
| --- | --- | --- | --- | --- | --- | --- |
| TRUNC | 1 | | | | | |
| RANGE | 1 | | | | | |
| TRUNC | 2 | | | | | |
| RANGE | 2 | | | | | |

Nếu thời gian client rất nhỏ, buffer gets và tính ổn định qua nhiều lượt có thể dễ diễn giải hơn vài mili giây dao động. Nếu dùng `SET TIMING ON` trong SQL*Plus/SQLcl, phân biệt thời gian SELECT cần đo với thời gian SELECT hiển thị plan.

Không tự gọi vài lượt lab là p95 production. Đánh giá percentile cần đủ mẫu và tải đại diện ở tầng đo đã xác định.

### 12.5. Thu dọn có chủ đích

Chỉ khi bảng được tạo bởi chính lab này trong schema hiện tại và bạn đã lưu bằng chứng cần thiết:

~~~sql
DROP TABLE perf_orders;
~~~

Lệnh xóa bảng cùng các index của bảng. Không chạy nếu chưa chắc đối tượng thuộc lab. Nếu recycle bin được bật, dữ liệu có thể còn ở đó; giải phóng dung lượng theo chính sách môi trường học, không dùng purge hàng loạt.

## 13. Từ phát hiện đến thay đổi có thể kiểm chứng

Một báo cáo phân tích hữu ích liên hệ được vấn đề, bằng chứng và phương án thử:

~~~text
Triệu chứng:
  API tra cứu đơn hàng chậm trong giờ cao điểm.

Phạm vi:
  Database/PDB/service, thời gian và nhóm yêu cầu cụ thể.

Bằng chứng:
  SQL ID/child/instance, bind đại diện, delta counter,
  plan, row source statistics và loại chờ.

Giả thuyết:
  Predicate khiến lượng đọc lớn hơn nhu cầu nghiệp vụ.

Thử nghiệm:
  Đổi một yếu tố, kiểm tra kết quả và đo lại dưới tải phù hợp.

Điều kiện chấp nhận:
  Kết quả đúng; độ trễ và tài nguyên đạt mục tiêu;
  không gây regression đáng kể cho workload liên quan.

Phương án khôi phục:
  Cách quay lại SQL/cấu hình/statistics trước thay đổi,
  cùng người chịu trách nhiệm theo dõi.
~~~

Khi đánh giá index mới, tính thêm dung lượng, thời gian tạo, overhead của INSERT/UPDATE/DELETE và tác động đến các SQL khác. Khi đánh giá statistics, theo dõi các plan có thể đổi. Khi đánh giá parallelism hoặc nâng cấu hình OCI, kiểm tra cả concurrency, hàng đợi và chi phí.

Tính sẵn sàng cũng là tiêu chí: báo cáo chạy nhanh hơn nhưng chiếm hết tài nguyên trong giờ giao dịch có thể làm dịch vụ kém ổn định. Chọn khung triển khai, giám sát và tiêu chí quay lui phù hợp với loại database đang dùng.

Một kết luận có thể kiểm chứng có dạng: “Trong khoảng đo đã xác định, với nhóm bind đại diện, thay đổi X giữ nguyên kết quả, giảm công việc Y và cải thiện chỉ tiêu Z dưới tải đã thử.” Bằng chứng như vậy giúp việc tối ưu SQL liên hệ rõ với hiệu năng, năng lực phục vụ và kiểm soát chi phí trên OCI.
