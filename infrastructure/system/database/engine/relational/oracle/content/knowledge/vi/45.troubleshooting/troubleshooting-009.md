# ORA-01555, ORA-30036 và kiểm tra nhu cầu UNDO

## 1. Vai trò của UNDO trong Oracle Database

UNDO lưu lại thông tin cần thiết để Oracle đảo ngược thay đổi chưa commit, phục hồi transaction khi rollback hoặc instance recovery, và cung cấp dữ liệu cũ cho cơ chế đọc nhất quán (read consistency). UNDO cũng hỗ trợ một số tính năng Flashback như Flashback Query và Flashback Table trong giới hạn retention.

Khi một transaction thay đổi block dữ liệu, Oracle ghi undo record mô tả giá trị trước thay đổi. Redo bảo vệ các thay đổi cần phục hồi; undo cung cấp thông tin để rollback và tái tạo phiên bản dữ liệu mà một query cần nhìn thấy tại SCN của nó.

Ví dụ:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;
~~~

Trong khi transaction chưa commit, Oracle giữ undo để có thể rollback. Một query khác có thể cần đọc phiên bản trước UPDATE để bảo đảm không nhìn thấy thay đổi chưa commit. Sau COMMIT, undo vẫn có thể cần cho query bắt đầu trước đó hoặc cho Flashback trong thời gian retention.

UNDO vì vậy vừa phục vụ transaction đang chạy, vừa phục vụ các query cần đọc dữ liệu tại một thời điểm trước đó. Hai nhu cầu này cạnh tranh cùng dung lượng tablespace.

## 2. Automatic Undo Management và UNDO tablespace

Oracle Database hiện đại sử dụng Automatic Undo Management (AUM). DBA tạo một hoặc nhiều undo tablespace và cấu hình database/instance sử dụng tablespace thích hợp. Oracle tự quản lý undo segment và extent.

Kiểm tra cấu hình hiện tại:

~~~sql
SHOW PARAMETER undo;

SELECT name,
       value,
       isdefault,
       issys_modifiable
FROM v$parameter
WHERE name IN ('undo_management',
               'undo_tablespace',
               'undo_retention',
               'db_block_size')
ORDER BY name;
~~~

Kiểm tra undo tablespace:

~~~sql
SELECT tablespace_name,
       status,
       contents,
       retention,
       block_size
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

Kiểm tra datafile:

~~~sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 2) AS size_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 2) AS max_size_mb,
       increment_by
FROM dba_data_files
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
)
ORDER BY file_id;
~~~

Trong RAC, mỗi instance có thể dùng undo tablespace riêng. Hãy kiểm tra tham số trên từng instance bằng GV$PARAMETER và xem số liệu undo theo INST_ID. Không giả định một instance đang gặp lỗi có cùng mức sử dụng undo với instance còn lại.

Với multitenant, xác nhận đang kết nối vào CDB root hay PDB. Tùy chế độ shared undo/local undo và cấu hình của CDB, PDB có thể có undo tablespace riêng. Kiểm tra container hiện tại, database property và undo parameter trong đúng container trước khi thay đổi.

~~~sql
SHOW CON_NAME;

SELECT property_name,
       property_value
FROM database_properties
WHERE property_name = 'LOCAL_UNDO_ENABLED';
~~~

## 3. Phân biệt ORA-01555 và ORA-30036

Hai lỗi đều có thể xuất hiện khi workload cần nhiều undo hơn khả năng lưu giữ hiện tại, nhưng chúng mô tả hai tình huống khác nhau.

| Mã lỗi | Ý nghĩa | Điều Oracle không thể hoàn thành |
| --- | --- | --- |
| ORA-01555: snapshot too old | Undo cần để dựng lại phiên bản dữ liệu tại SCN của query đã bị ghi đè hoặc không còn sẵn có | Query không thể tiếp tục đọc nhất quán |
| ORA-30036: unable to extend segment by ... in undo tablespace | Oracle không cấp phát được extent tiếp theo cho undo segment trong undo tablespace | Transaction không thể lấy thêm undo space để tiếp tục thay đổi dữ liệu |

ORA-01555 thường làm query đọc dữ liệu thất bại. ORA-30036 thường làm transaction cần thêm undo thất bại. Áp lực dung lượng có thể liên quan đến cả hai: nếu Oracle phải tái sử dụng undo chưa hết thời gian cần thiết, query dài có thể gặp ORA-01555; nếu không còn extent có thể dùng hoặc mở rộng, transaction có thể gặp ORA-30036.

Không xử lý hai lỗi bằng cùng một hành động mặc định. Cần xác định workload, trạng thái extent, retention guarantee, autoextend và dung lượng storage trước khi thay đổi cấu hình.

## 4. ORA-01555: Snapshot Too Old

### 4.1. Cơ chế phát sinh

Một query cần nhìn dữ liệu tại read-consistent SCN được xác định khi query bắt đầu. Trong lúc query chạy, các transaction khác có thể cập nhật hoặc xóa những block mà query chưa đọc tới.

Nếu block đã bị thay đổi sau SCN của query, Oracle dùng undo để dựng lại phiên bản cũ. Nếu undo record cần thiết đã bị tái sử dụng hoặc không còn tồn tại, Oracle không thể tạo phiên bản dữ liệu đúng SCN và trả ORA-01555.

Ví dụ:

1. Báo cáo bắt đầu lúc 09:00 và cần đọc dữ liệu nhất quán tại SCN S.
2. Báo cáo chạy lâu do quét bảng lớn.
3. Ứng dụng OLTP liên tục UPDATE/DELETE cùng các block.
4. Undo chứa phiên bản trước các thay đổi được tái sử dụng để phục vụ transaction mới.
5. Đến 09:40, báo cáo cần một undo record đã không còn.
6. Query thất bại với ORA-01555.

Đây là vấn đề về thời gian tồn tại của undo cần cho consistent read, không nhất thiết là toàn bộ undo tablespace đã đầy.

### 4.2. Nguyên nhân thường gặp

- Query chạy lâu hơn khoảng thời gian undo thực tế được giữ.
- Tốc độ phát sinh undo cao do DML đồng thời.
- Undo tablespace quá nhỏ so với workload và retention mục tiêu.
- Datafile không thể autoextend hoặc đã chạm MAXSIZE.
- Có transaction lớn hoặc batch DML làm thay đổi nhiều block.
- PL/SQL mở cursor rồi COMMIT trong khi vẫn tiếp tục FETCH cursor đó.
- Query chạy trên bảng có thay đổi rất mạnh trong lúc đọc.
- Một workload Flashback Query yêu cầu dữ liệu cũ hơn mức undo còn giữ.

Không kết luận ORA-01555 chỉ từ tham số UNDO_RETENTION. Phải xem TUNED_UNDORETENTION, MAXQUERYLEN, SSOLDERRCNT và mức tiêu thụ undo trong đúng khoảng thời gian lỗi.

### 4.3. Lỗi do COMMIT trong lúc FETCH cursor

Một anti-pattern kinh điển:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM orders
        WHERE status = 'NEW';
BEGIN
    FOR r IN c_orders LOOP
        UPDATE orders
        SET status = 'PROCESSED'
        WHERE order_id = r.order_id;

        COMMIT;
    END LOOP;
END;
/
~~~

Cursor đang đọc một tập dữ liệu theo read-consistent SCN, trong khi transaction liên tục commit và tạo thêm undo pressure. Với một số cách xử lý cursor/fetch, điều này có thể dẫn đến ORA-01555 hoặc hành vi khó dự đoán. Việc commit từng row cũng tạo overhead lớn và làm transaction không còn atomic.

Thiết kế tốt hơn:

- Nếu có thể, dùng một câu UPDATE set-based.
- Nếu cần xử lý theo lô, xác định batch key rõ ràng và đóng cursor trước khi commit batch.
- Dùng keyset pagination hoặc bảng staging để phân đoạn công việc.
- Chỉ commit tại ranh giới batch đã được thiết kế, không commit bên trong fetch loop của cùng cursor.
- Lưu tiến độ batch bền vững để có thể resume an toàn.

Ví dụ set-based:

~~~sql
UPDATE orders
SET status = 'PROCESSED'
WHERE status = 'NEW';

COMMIT;
~~~

Nếu số row quá lớn để chạy trong một transaction, chia thành các batch độc lập dựa trên khóa ổn định. Mỗi batch phải có điều kiện lọc không làm thay đổi tập kết quả của cursor đang mở.

### 4.4. ORA-01555 không đồng nghĩa undo tablespace đầy

Undo tablespace có thể còn free space nhưng undo cũ đã được tái sử dụng trước khi query dài cần tới. Ngược lại, tablespace có thể đầy nhưng query ngắn vẫn chạy bình thường nếu không cần phiên bản undo đã mất.

Phân biệt:

- **Free space:** extent chưa được cấp phát hoặc dung lượng có thể cấp phát.
- **Expired undo:** undo đã qua thời gian retention cần thiết và có thể tái sử dụng.
- **Unexpired undo:** undo vẫn nằm trong retention window mục tiêu.
- **Active undo:** undo thuộc transaction đang hoạt động; không thể bị tái sử dụng tùy tiện.

Số liệu của các nhóm extent giúp hiểu vì sao Oracle tái sử dụng undo hoặc không thể cấp phát thêm.

## 5. ORA-30036: Unable to Extend Segment in Undo Tablespace

### 5.1. Cơ chế phát sinh

Transaction đang thực hiện INSERT, UPDATE, DELETE hoặc thao tác khác cần undo. Oracle cần cấp phát thêm extent cho undo segment nhưng không thể lấy đủ dung lượng từ tablespace.

Các khả năng:

- Undo tablespace không còn free extent đủ dùng.
- Datafile không bật AUTOEXTEND.
- Datafile đã đạt MAXSIZE.
- Filesystem/ASM disk group hết dung lượng.
- Tablespace bị giới hạn bởi storage quota hoặc policy.
- Active transaction đang giữ lượng undo lớn.
- Retention Guarantee bảo vệ unexpired undo nên Oracle không thể tái sử dụng phần undo đó để cấp phát cho transaction mới.

Thông báo thường có dạng:

~~~text
ORA-30036: unable to extend segment by 8 in undo tablespace 'UNDOTBS1'
~~~

Số block trong thông báo phụ thuộc extent allocation. Không được suy ra tổng dung lượng cần thêm chỉ từ con số extent trong lỗi.

### 5.2. Tác động của RETENTION GUARANTEE

Undo tablespace có thuộc tính retention:

- **NOGUARANTEE:** Oracle có thể tái sử dụng unexpired undo khi cần không gian cho transaction mới. Điều này ưu tiên khả năng DML tiếp tục nhưng query dài có thể mất undo cần thiết và gặp ORA-01555.
- **GUARANTEE:** Oracle không tái sử dụng unexpired undo trước khi hết retention. Điều này bảo vệ undo cho query/Flashback trong retention mục tiêu, nhưng nếu không có đủ chỗ và không thể mở rộng, DML có thể thất bại với ORA-30036.

Kiểm tra:

~~~sql
SELECT tablespace_name,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

Thay đổi guarantee:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
~~~

Hoặc:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION NOGUARANTEE;
~~~

Đây là thay đổi ảnh hưởng trực tiếp tới cân bằng giữa bảo vệ query cũ và khả năng ghi transaction mới. Không bật GUarantee chỉ để cố chữa ORA-01555 nếu chưa sizing đủ dung lượng. Cũng không chuyển sang NOGUARANTEE một cách vội vàng khi ứng dụng phụ thuộc Flashback Query/long-running report.

### 5.3. UNDO_RETENTION không phải cam kết tuyệt đối trong mọi cấu hình

UNDO_RETENTION là thời gian mục tiêu tính bằng giây mà Oracle cố giữ undo đã commit. Giá trị này không tự động bảo đảm rằng mọi undo sẽ luôn tồn tại trong khoảng thời gian đó.

Trong NOGUARANTEE, khi thiếu chỗ, Oracle có thể tái sử dụng unexpired undo để phục vụ transaction mới. Retention Guarantee mới buộc Oracle không ghi đè unexpired undo, đổi lại DML có thể thiếu chỗ.

Oracle có thể tự điều chỉnh retention trong Automatic Undo Management. TUNED_UNDORETENTION trong V$UNDOSTAT cho biết retention được điều chỉnh thực tế theo workload và dung lượng. Do đó, không chỉ nhìn UNDO_RETENTION parameter rồi kết luận query dài sẽ được bảo vệ.

## 6. Chẩn đoán theo thứ tự

Khi nhận ORA-01555 hoặc ORA-30036, trước tiên xác định database, instance, PDB, undo tablespace và thời điểm lỗi. Giữ lại alert log, application log, SQL_ID và transaction/request ID nếu có.

### 6.1. Xác định đúng undo tablespace

~~~sql
SHOW CON_NAME;
SHOW PARAMETER undo_tablespace;
SHOW PARAMETER undo_retention;

SELECT name,
       value
FROM v$parameter
WHERE name IN ('undo_tablespace', 'undo_retention');
~~~

Với RAC:

~~~sql
SELECT inst_id,
       name,
       value
FROM gv$parameter
WHERE name IN ('undo_tablespace', 'undo_retention')
ORDER BY inst_id, name;
~~~

Nếu chạy trong CDB/PDB, kiểm tra đúng container sở hữu workload. Đừng lấy số liệu từ CDB root rồi áp dụng cho PDB mà không hiểu chế độ undo của CDB.

### 6.2. Kiểm tra dung lượng datafile và khả năng autoextend

~~~sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 2) AS size_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 2) AS max_size_mb,
       increment_by
FROM dba_data_files
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
)
ORDER BY file_id;
~~~

Kiểm tra tổng allocated:

Để lọc theo loại tablespace, nối DBA_DATA_FILES với DBA_TABLESPACES:

~~~sql
SELECT d.tablespace_name,
       ROUND(SUM(d.bytes) / 1024 / 1024, 2) AS allocated_mb
FROM dba_data_files d
JOIN dba_tablespaces t
  ON t.tablespace_name = d.tablespace_name
WHERE t.contents = 'UNDO'
GROUP BY d.tablespace_name
ORDER BY d.tablespace_name;
~~~

Kiểm tra free extent:

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS free_mb,
       COUNT(*) AS free_extent_count,
       ROUND(MAX(bytes) / 1024 / 1024, 2) AS largest_free_extent_mb
FROM dba_free_space
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
)
GROUP BY tablespace_name;
~~~

Đối với bigfile tablespace, autoextend và ASM, kiểm tra cả giới hạn datafile lẫn dung lượng storage phía dưới. Một datafile còn maxbytes không có nghĩa disk group còn chỗ để tăng file.

### 6.3. Xem trạng thái extent trong undo

~~~sql
SELECT tablespace_name,
       status,
       COUNT(*) AS extent_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_undo_extents
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
)
GROUP BY tablespace_name, status
ORDER BY status;
~~~

Ý nghĩa:

| STATUS | Ý nghĩa |
| --- | --- |
| ACTIVE | Undo đang được transaction sử dụng |
| UNEXPIRED | Undo đã commit nhưng vẫn nằm trong retention period |
| EXPIRED | Undo đã hết retention và có thể tái sử dụng |

Nếu ACTIVE chiếm phần lớn, kiểm tra transaction dài hoặc transaction DML lớn. Nếu UNEXPIRED chiếm nhiều và tablespace dùng RETENTION GUARANTEE, kiểm tra retention mục tiêu và khả năng mở rộng. Nếu EXPIRED còn nhiều nhưng ORA-30036 vẫn xảy ra, xem extent allocation, segment state, file limit và alert log thay vì chỉ dựa vào tổng MB.

### 6.4. Đọc V$UNDOSTAT

V$UNDOSTAT là nguồn quan trọng nhất để phân tích undo workload theo các khoảng thời gian. View lưu thống kê theo các interval, thông thường 10 phút, cho một cửa sổ lịch sử gần đây.

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       maxqueryid,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt,
       expstealcnt,
       activeblks,
       unexpiredblks,
       expiredblks
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 36 ROWS ONLY;
~~~

Các cột cần chú ý:

| Cột | Ý nghĩa |
| --- | --- |
| BEGIN_TIME, END_TIME | Khoảng thời gian thống kê |
| UNDOBLKS | Số undo block được tạo trong interval |
| TXNCOUNT | Số transaction trong interval |
| MAXQUERYLEN | Thời lượng query dài nhất, giây |
| MAXQUERYID | SQL ID của query dài nhất nếu có |
| TUNED_UNDORETENTION | Undo retention được Oracle điều chỉnh, giây |
| SSOLDERRCNT | Số lỗi snapshot too old trong interval |
| NOSPACEERRCNT | Số lần không có chỗ cho undo trong interval |
| UNXPSTEALCNT | Số lần Oracle lấy/reuse unexpired undo extent |
| EXPSTEALCNT | Số lần lấy expired extent |
| ACTIVEBLKS | Số undo block active |
| UNEXPIREDBLKS | Số undo block unexpired |
| EXPIREDBLKS | Số undo block expired |

Diễn giải:

- SSOLDERRCNT tăng tại thời điểm lỗi là dấu hiệu cần điều tra ORA-01555.
- NOSPACEERRCNT tăng cho thấy có lần thiếu không gian undo, cần đối chiếu ORA-30036 và storage.
- UNXPSTEALCNT tăng cho thấy Oracle đã phải tái sử dụng undo chưa hết retention; query dài có thể bị ảnh hưởng.
- MAXQUERYLEN lớn hơn TUNED_UNDORETENTION là tín hiệu nguy cơ, không phải bằng chứng duy nhất rằng một query cụ thể chắc chắn lỗi.
- UNDOBLKS tăng nhanh cho thấy tốc độ phát sinh undo lớn; phải so với dung lượng và retention mục tiêu.

Không đọc một dòng V$UNDOSTAT đơn lẻ rồi kết luận. Đối chiếu nhiều interval trước, trong và sau thời điểm sự cố.

### 6.5. Tính tốc độ phát sinh undo

UNDOBLKS là số block tạo ra trong interval. Có thể ước lượng tốc độ undo block mỗi giây:

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       ROUND(
           undoblks /
           NULLIF((end_time - begin_time) * 86400, 0),
           2
       ) AS undo_blocks_per_sec,
       maxquerylen,
       tuned_undoretention
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 36 ROWS ONLY;
~~~

Nhân undo_blocks_per_sec với DB_BLOCK_SIZE để ước lượng bytes/second. Dùng peak interval đại diện cho workload bận, không chỉ dùng average cả ngày vì peak DML có thể cao hơn nhiều.

### 6.6. Xem transaction đang giữ undo

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       s.sql_id,
       t.start_time,
       t.used_ublk,
       t.used_urec
FROM v$transaction t
JOIN v$session s
  ON s.taddr = t.addr
ORDER BY t.used_ublk DESC;
~~~

USED_UBLK và USED_UREC cho biết transaction đang sử dụng bao nhiêu undo block/record. Transaction có USED_UBLK rất lớn hoặc tồn tại lâu có thể giữ nhiều undo active và làm giảm không gian có thể tái sử dụng.

Xác định SQL_ID, MODULE, username và thời điểm bắt đầu trước khi cân nhắc can thiệp. Không kill transaction chỉ vì nó lớn; có thể gây rollback rất lâu và tạo thêm tải undo/redo trong quá trình recovery.

### 6.7. Tìm query đang chạy lâu

~~~sql
SELECT sid,
       serial#,
       username,
       module,
       sql_id,
       sql_exec_start,
       ROUND((SYSDATE - sql_exec_start) * 86400) AS elapsed_seconds
FROM v$session
WHERE status = 'ACTIVE'
  AND sql_exec_start IS NOT NULL
ORDER BY sql_exec_start;
~~~

Đối chiếu SQL_ID với MAXQUERYID trong V$UNDOSTAT, execution plan, SQL Monitor nếu được cấp phép và application request log. Không phải mọi session ACTIVE đều đang tiêu thụ nhiều undo; query SELECT dài thường tạo ít undo hơn DML nhưng cần undo cũ để consistent read.

### 6.8. AWR và Diagnostics Pack

DBA_HIST_UNDOSTAT và AWR có thể hỗ trợ điều tra lịch sử dài hơn V$UNDOSTAT. Tuy nhiên, việc sử dụng AWR/ASH và một số báo cáo/feature có thể yêu cầu Oracle Diagnostics Pack hoặc license tương ứng.

Nếu môi trường không có license, ưu tiên dynamic performance views như V$UNDOSTAT, V$SESSION, V$TRANSACTION và log đã được thu thập hợp lệ. Không bật hoặc truy vấn tính năng có license hạn chế mà chưa xác nhận quyền sử dụng.

## 7. Đánh giá nhu cầu UNDO và sizing

### 7.1. Những yếu tố quyết định dung lượng

Dung lượng undo cần phụ thuộc:

- Tốc độ phát sinh undo của workload, đặc biệt peak DML.
- Thời gian query dài nhất cần đọc nhất quán.
- Retention mục tiêu cho Flashback Query/Flashback Table.
- Số transaction đồng thời và transaction lớn nhất.
- Thời gian batch, ETL và maintenance.
- RETENTION GUARANTEE hay NOGUARANTEE.
- Khả năng autoextend và giới hạn storage.
- Dung lượng headroom cho spike và rollback.

Không sizing chỉ theo số GB database hoặc số row trong bảng. Hai database có cùng kích thước có thể có undo generation rate rất khác nhau.

### 7.2. Công thức ước lượng ban đầu

Một cách ước lượng đơn giản:

~~~text
Undo bytes per second
    = peak undo blocks per second × DB_BLOCK_SIZE

Undo for retention
    = undo bytes per second × target retention seconds

Initial tablespace estimate
    = undo for retention
      + headroom for concurrent active transactions
      + safety margin
~~~

Ví dụ giả định:

- Peak undo generation: 1.500 block/giây.
- DB_BLOCK_SIZE: 8.192 bytes.
- Target retention: 1.800 giây (30 phút).
- Active transaction/headroom: 4 GB.
- Safety margin: 25% trên phần tính toán trước margin.

Tính:

~~~text
Undo rate = 1.500 × 8.192 = 12.288.000 bytes/giây
Retention volume = 12.288.000 × 1.800
                 = 22.118.400.000 bytes
                 ≈ 20,6 GiB
Base = 20,6 + 4 = 24,6 GiB
Estimate with 25% margin ≈ 30,8 GiB
~~~

Đây chỉ là sizing sơ bộ. Dùng peak interval đại diện, đo active transaction thực tế, kiểm tra concurrent workload và chạy Undo Advisor/Enterprise Manager khi phù hợp. Không dùng ví dụ này như giá trị mặc định cho production.

### 7.3. Chọn retention mục tiêu

UNDO_RETENTION phải đáp ứng query dài nhất và yêu cầu Flashback đã xác định. Ví dụ:

- OLTP query thông thường chạy vài giây.
- Báo cáo chạy 20 phút.
- Batch reconciliation chạy 45 phút.
- Flashback Query cần đọc lại dữ liệu trong 2 giờ.

Nếu yêu cầu phục hồi là 2 giờ, chỉ đặt retention 20 phút vì báo cáo hiện tại chạy 20 phút sẽ không đáp ứng mục tiêu. Ngược lại, đặt retention rất dài mà không sizing tablespace có thể gây ORA-30036 nếu dùng RETENTION GUARANTEE hoặc gây tái sử dụng undo khi NOGUARANTEE.

### 7.4. Đặt UNDO_RETENTION

Ví dụ:

~~~sql
ALTER SYSTEM SET undo_retention = 1800 SCOPE = BOTH;
~~~

1800 giây tương đương 30 phút. Giá trị thực tế phải dựa trên query duration, workload, storage và mục tiêu Flashback. Trong RAC, xác định scope và cấu hình cho từng instance theo chính sách.

Thay đổi tham số không tự tạo thêm dung lượng và không bảo đảm retention nếu tablespace không có chỗ. Theo dõi TUNED_UNDORETENTION sau thay đổi.

### 7.5. Undo Advisor

Enterprise Manager Undo Advisor có thể dùng lịch sử workload và retention mục tiêu để đề xuất dung lượng. Khi sử dụng, chọn khoảng thời gian đại diện cho tải cao, bao gồm batch/reporting peak.

Undo Advisor là công cụ hỗ trợ quyết định; DBA vẫn phải xem:

- Peak undo generation.
- Query dài nhất.
- Concurrent active transaction.
- Retention Guarantee.
- Datafile autoextend/MAXSIZE.
- Storage capacity.
- Mục tiêu Flashback.

Không coi một giá trị đề xuất tự động là sizing cố định cho mọi mùa tải.

## 8. Khắc phục ORA-01555

### 8.1. Xác nhận thời điểm và SQL gây lỗi

Thu thập:

- Thời điểm lỗi và database/PDB/instance.
- SQL_ID, module, action và request ID.
- Query duration và MAXQUERYLEN.
- SSOLDERRCNT và TUNED_UNDORETENTION.
- UNXPSTEALCNT và trạng thái extent.
- Peak DML/undo generation trong cùng interval.

Nếu lỗi chỉ xảy ra trong báo cáo cuối ngày, so sánh tải DML cùng thời điểm với các giờ ít tải.

### 8.2. Giảm thời gian query

Query cần undo càng lâu thì cửa sổ consistent read càng dài. Có thể:

- Tối ưu execution plan và index.
- Thu hẹp khoảng thời gian lọc dữ liệu.
- Chỉ lấy cột cần thiết.
- Chia báo cáo thành partition/date range.
- Dùng summary table hoặc materialized view khi phù hợp.
- Chạy báo cáo vào thời gian ít DML.
- Giảm network/client fetch delay nếu ứng dụng fetch chậm.

Một query có execution plan kém có thể giữ snapshot lâu hơn cần thiết, làm tăng nguy cơ ORA-01555 dù SQL không thay đổi.

### 8.3. Tăng undo tablespace

Nếu số liệu cho thấy undo space không đủ so với query duration và workload, tăng dung lượng bằng cách thêm datafile hoặc tăng kích thước datafile có kiểm soát. Kiểm tra filesystem/ASM trước.

Ví dụ thêm datafile:

~~~sql
ALTER TABLESPACE undotbs1
ADD DATAFILE '/u02/oradata/DB/undotbs1_02.dbf'
SIZE 8G
AUTOEXTEND ON
NEXT 512M
MAXSIZE 32G;
~~~

Đường dẫn, kích thước và MAXSIZE chỉ minh họa. Với OMF/ASM, dùng cấu hình storage thực tế. Không thêm file nếu disk group không còn capacity hoặc datafile sẽ vượt giới hạn đã phê duyệt.

### 8.4. Tăng retention có dung lượng hỗ trợ

Sau khi xác nhận tablespace đủ lớn, có thể tăng UNDO_RETENTION để đáp ứng query dài hoặc Flashback. Theo dõi TUNED_UNDORETENTION và SSOLDERRCNT qua nhiều interval.

Chỉ tăng tham số mà không tăng dung lượng có thể không giải quyết được lỗi, đặc biệt ở NOGUARANTEE khi Oracle phải tái sử dụng unexpired undo để phục vụ DML.

### 8.5. Xem xét RETENTION GUARANTEE

Chỉ bật guarantee khi nghiệp vụ thật sự cần bảo đảm retention và đã tính đủ dung lượng cho peak undo generation, active transaction và headroom. Khi guarantee, transaction mới có thể thất bại nếu không thể cấp phát thêm undo.

### 8.6. Sửa commit pattern

Nếu ứng dụng commit bên trong cursor fetch loop, thiết kế lại batch boundary. Tránh commit từng row và tránh tiếp tục fetch từ cursor phụ thuộc snapshot cũ sau khi commit nhiều lần.

## 9. Khắc phục ORA-30036

### 9.1. Xác định nguyên nhân thiếu chỗ

Kiểm tra đồng thời:

1. UNDO tablespace nào đang được instance/PDB sử dụng.
2. Allocated/free extent và ACTIVE/UNEXPIRED/EXPIRED blocks.
3. Datafile AUTOEXTEND và MAXSIZE.
4. Filesystem/ASM disk group còn chỗ hay không.
5. RETENTION là GUARANTEE hay NOGUARANTEE.
6. Transaction lớn đang giữ undo.
7. NOSPACEERRCNT và UNDOBLKS trong V$UNDOSTAT.

### 9.2. Thêm hoặc mở rộng datafile

Nếu storage còn capacity và sizing cho thấy cần thêm dung lượng, DBA có thể thêm datafile hoặc resize file hiện tại:

~~~sql
ALTER DATABASE DATAFILE
  '/u02/oradata/DB/undotbs1_01.dbf'
RESIZE 16G;
~~~

Hoặc bật autoextend với mức trần:

~~~sql
ALTER DATABASE DATAFILE
  '/u02/oradata/DB/undotbs1_01.dbf'
AUTOEXTEND ON
NEXT 512M
MAXSIZE 32G;
~~~

Resize chỉ thành công nếu storage và giới hạn file cho phép. Không cấu hình MAXSIZE UNLIMITED theo thói quen; phải có quota/capacity guard ở tầng storage.

### 9.3. Giải phóng áp lực từ transaction

Xác định transaction lớn qua V$TRANSACTION và V$SESSION. Liên hệ application owner để xác định batch đang chạy, thời gian dự kiến và khả năng cancel an toàn.

Không kill session chỉ để làm giảm undo mà không xem xét rollback. Khi kill một transaction lớn, Oracle phải rollback thay đổi; rollback cũng cần tài nguyên và có thể kéo dài.

### 9.4. Xem xét retention guarantee

Nếu tablespace đang GUARANTEE, Oracle giữ unexpired undo theo cam kết. Nếu dung lượng không đủ, DML mới có thể lỗi ORA-30036. Chuyển NOGUARANTEE có thể cho phép tái sử dụng unexpired undo và giúp DML tiếp tục, nhưng query dài/Flashback có thể mất khả năng đọc phiên bản cũ.

Chỉ thay đổi khi owner nghiệp vụ chấp nhận trade-off và có kế hoạch giám sát sau đó.

### 9.5. Kiểm tra storage bên dưới

Đối với filesystem:

- Dung lượng volume còn đủ không?
- Có quota ở filesystem hoặc user không?
- File system read-only hoặc có lỗi I/O không?

Đối với ASM:

- Disk group còn usable free space không?
- Có rebalance hoặc disk failure không?
- File growth có bị giới hạn bởi redundancy/reserved space không?

Database datafile autoextend không thể vượt qua giới hạn storage phía dưới.

## 10. Giám sát UNDO định kỳ

### 10.1. Dashboard cần có

Một dashboard vận hành nên hiển thị:

- Undo tablespace allocated MB và max possible MB.
- Free space/extent.
- ACTIVE, UNEXPIRED và EXPIRED undo MB.
- Undo blocks per second.
- TUNED_UNDORETENTION.
- MAXQUERYLEN.
- SSOLDERRCNT.
- NOSPACEERRCNT.
- UNXPSTEALCNT.
- Số transaction lớn và thời gian chạy.
- Datafile autoextend, MAXSIZE và storage free.

### 10.2. Query tóm tắt V$UNDOSTAT

~~~sql
SELECT begin_time,
       ROUND(undoblks * 8192 / 1024 / 1024, 2) AS undo_mb,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt,
       expstealcnt
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 24 ROWS ONLY;
~~~

Query trên giả định DB_BLOCK_SIZE là 8192 bytes. Nếu database dùng block size khác, lấy giá trị từ V$PARAMETER thay vì hardcode 8192.

### 10.3. Query theo RAC instance

~~~sql
SELECT inst_id,
       begin_time,
       end_time,
       undoblks,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt
FROM gv$undostat
ORDER BY begin_time DESC, inst_id
FETCH FIRST 72 ROWS ONLY;
~~~

Số liệu RAC cần được đọc theo INST_ID. Undo pressure trên một instance không nhất thiết được bù bằng free space ở undo tablespace của instance khác.

### 10.4. Cảnh báo vận hành

Có thể tạo cảnh báo khi:

- SSOLDERRCNT tăng.
- NOSPACEERRCNT lớn hơn 0.
- TUNED_UNDORETENTION thấp hơn yêu cầu query.
- UNXPSTEALCNT tăng liên tục.
- Datafile gần MAXSIZE.
- Storage/ASM disk group gần ngưỡng cảnh báo.
- Transaction dùng undo vượt ngưỡng hoặc tồn tại quá lâu.

Ngưỡng phải dựa trên baseline workload và SLA, không dùng một ngưỡng MB chung cho mọi database.

## 11. Ví dụ tình huống điều tra

### Tình huống A: Báo cáo 40 phút gặp ORA-01555

Quan sát:

- MAXQUERYLEN khoảng 2.400 giây.
- TUNED_UNDORETENTION khoảng 1.200 giây.
- SSOLDERRCNT tăng trong interval.
- UNXPSTEALCNT tăng khi batch OLTP chạy.
- Tablespace có free space thấp và NOGUARANTEE.

Nhận định:

- Query cần snapshot lâu hơn retention thực tế.
- Oracle tái sử dụng unexpired undo để phục vụ DML mới.
- Free space thấp làm áp lực tái sử dụng tăng.

Hướng xử lý:

1. Tối ưu báo cáo để giảm runtime.
2. Đo peak undo generation trong batch window.
3. Tính lại dung lượng cho retention cần thiết.
4. Tăng undo tablespace và giới hạn autoextend phù hợp.
5. Đặt UNDO_RETENTION theo mục tiêu sau khi storage sẵn sàng.
6. Theo dõi TUNED_UNDORETENTION và SSOLDERRCNT sau thay đổi.

### Tình huống B: Batch UPDATE gặp ORA-30036

Quan sát:

- NOSPACEERRCNT tăng.
- ACTIVE undo chiếm phần lớn tablespace.
- Một transaction dùng USED_UBLK rất lớn.
- Datafile đã đạt MAXSIZE.
- Filesystem/ASM vẫn còn capacity.

Nhận định:

- Transaction cần thêm undo nhưng file không thể mở rộng.
- Active transaction đang giữ nhiều undo.

Hướng xử lý:

1. Xác minh batch có đúng phạm vi và dự kiến hoàn tất không.
2. Tăng MAXSIZE hoặc thêm datafile theo capacity đã duyệt.
3. Theo dõi tiến độ transaction và undo generation.
4. Tối ưu batch size/transaction boundary cho lần chạy sau.
5. Không kill transaction nếu chưa đánh giá chi phí rollback.

### Tình huống C: ORA-30036 khi RETENTION GUARANTEE

Quan sát:

- Tablespace ở GUARANTEE.
- UNEXPIREDBLKS cao.
- Datafile đạt MAXSIZE.
- DML mới lỗi ORA-30036.

Nhận định:

- Oracle không được phép tái sử dụng unexpired undo.
- Không còn khả năng mở rộng để cấp phát extent cho transaction.

Hướng xử lý:

1. Xác nhận retention guarantee có phải yêu cầu nghiệp vụ bắt buộc.
2. Tính dung lượng cần cho retention và peak DML.
3. Tăng datafile/tablespace nếu storage cho phép.
4. Nếu business chấp thuận giảm guarantee, thay đổi sang NOGUARANTEE theo change process.
5. Theo dõi ORA-01555 và Flashback requirements sau khi thay đổi.

## 12. Những thao tác không nên làm khi gặp lỗi UNDO

- Không xóa datafile undo bằng lệnh hệ điều hành.
- Không drop undo tablespace đang được instance sử dụng.
- Không kill transaction lớn mà chưa hiểu rollback impact.
- Không chuyển RETENTION GUARANTEE sang NOGUARANTEE chỉ để xóa lỗi tức thời mà không thông báo owner.
- Không đặt UNDO_RETENTION rất lớn khi chưa có dung lượng.
- Không đặt AUTOEXTEND UNLIMITED mà không có storage limit/monitoring.
- Không chạy purge hoặc DDL không liên quan để cố giải phóng undo.
- Không kết luận ORA-01555 chỉ do tablespace nhỏ mà chưa xem V$UNDOSTAT.
- Không kết luận ORA-30036 chỉ do retention guarantee mà chưa xem datafile/storage.
- Không commit từng row trong cursor fetch loop.
- Không dùng DBA_HIST_UNDOSTAT/AWR nếu chưa xác nhận license.

## 13. Lab thực hành

Lab nên chạy trong schema/database thử nghiệm. Không cố tình gây hết undo trên production.

### 13.1. Tạo bảng test

~~~sql
CREATE TABLE undo_lab_data (
    id NUMBER PRIMARY KEY,
    payload VARCHAR2(200),
    updated_at TIMESTAMP
);

INSERT INTO undo_lab_data(id, payload, updated_at)
SELECT level,
       RPAD('A', 100, 'A'),
       SYSTIMESTAMP
FROM dual
CONNECT BY level <= 100000;

COMMIT;
~~~

### 13.2. Mở query đọc dài

Session A:

~~~sql
SELECT COUNT(*)
FROM undo_lab_data a
CROSS JOIN undo_lab_data b;
~~~

Trong workload thật, query có thể chạy lâu và cần consistent read trong lúc session khác cập nhật dữ liệu. Với lab, chọn một query và data volume đủ để quan sát; không cần cố tình tạo lỗi nếu môi trường nhỏ.

### 13.3. Tạo DML đồng thời

Session B:

~~~sql
BEGIN
    FOR i IN 1..10000 LOOP
        UPDATE undo_lab_data
        SET payload = RPAD(TO_CHAR(i), 100, 'X'),
            updated_at = SYSTIMESTAMP
        WHERE id = i;
        COMMIT;
    END LOOP;
END;
/
~~~

Quan sát V$UNDOSTAT, DBA_UNDO_EXTENTS và query session. Thử tăng datafile/retention trong môi trường lab để thấy tác động tới query duration và undo reuse.

### 13.4. Quan sát extent

~~~sql
SELECT status,
       COUNT(*) AS extent_count,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS size_mb
FROM dba_undo_extents
GROUP BY status
ORDER BY status;
~~~

### 13.5. Quan sát undo history

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt,
       unxpstealcnt
FROM v$undostat
ORDER BY begin_time DESC
FETCH FIRST 12 ROWS ONLY;
~~~

### 13.6. Thử retention guarantee

Chỉ thực hiện trong tablespace lab:

~~~sql
ALTER TABLESPACE undotbs_lab RETENTION GUARANTEE;
~~~

Quan sát thay đổi extent và khả năng cấp phát khi workload tạo nhiều undo. Sau lab, trả về chính sách ban đầu đã ghi nhận:

~~~sql
ALTER TABLESPACE undotbs_lab RETENTION NOGUARANTEE;
~~~

Không thực hiện trên undo tablespace production nếu chưa có phê duyệt và sizing.

## 14. Checklist xử lý sự cố

1. **Xác định đúng lỗi:** ORA-01555 hay ORA-30036, thời điểm và SQL_ID.
2. **Xác định đúng container/instance:** CDB/PDB và RAC INST_ID.
3. **Xác định undo tablespace:** UNDO_TABLESPACE parameter.
4. **Kiểm tra datafile:** size, autoextend, MAXSIZE và path.
5. **Kiểm tra storage:** filesystem/ASM free capacity.
6. **Kiểm tra retention mode:** GUARANTEE hay NOGUARANTEE.
7. **Đọc V$UNDOSTAT:** MAXQUERYLEN, TUNED_UNDORETENTION, SSOLDERRCNT, NOSPACEERRCNT.
8. **Kiểm tra extent:** ACTIVE, UNEXPIRED, EXPIRED.
9. **Kiểm tra transaction:** USED_UBLK, USED_UREC, START_TIME.
10. **Kiểm tra query dài:** SQL_ID, execution time, execution plan.
11. **Đối chiếu tải DML:** peak undo generation và thời điểm batch.
12. **Tính lại sizing:** peak undo rate × retention + active transaction headroom + margin.
13. **Chọn hành động:** tối ưu query, sửa commit pattern, tăng dung lượng hoặc điều chỉnh retention.
14. **Đánh giá trade-off:** Guarantee bảo vệ query nhưng có thể làm DML thiếu chỗ.
15. **Thực hiện change có kiểm soát:** ghi lại giá trị trước/sau và storage limit.
16. **Theo dõi sau thay đổi:** lỗi, retention thực tế, extent và pool of undo.
17. **Xác nhận nghiệp vụ:** query/batch chạy hoàn tất và dữ liệu đúng.
18. **Lưu bằng chứng:** log, SQL_ID, interval và số liệu để cập nhật baseline.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** UNDO phục vụ những mục đích chính nào?

**Câu 2.** Vì sao query cần undo ngay cả khi transaction tạo undo đã COMMIT?

**Câu 3.** ORA-01555 có nghĩa gì?

**Câu 4.** ORA-30036 có nghĩa gì?

**Câu 5.** Vì sao hai lỗi này không thể xử lý bằng một hành động mặc định?

**Câu 6.** ACTIVE, UNEXPIRED và EXPIRED undo khác nhau thế nào?

**Câu 7.** UNDO_RETENTION có phải cam kết tuyệt đối không?

**Câu 8.** RETENTION GUARANTEE thay đổi hành vi tái sử dụng undo ra sao?

**Câu 9.** Vì sao RETENTION GUARANTEE có thể dẫn đến ORA-30036?

**Câu 10.** V$UNDOSTAT cung cấp những thông tin quan trọng nào?

**Câu 11.** SSOLDERRCNT và NOSPACEERRCNT phản ánh điều gì?

**Câu 12.** UNXPSTEALCNT tăng gợi ý điều gì?

**Câu 13.** MAXQUERYLEN và TUNED_UNDORETENTION được dùng để đánh giá điều gì?

**Câu 14.** USED_UBLK trong V$TRANSACTION có ý nghĩa gì?

**Câu 15.** Vì sao không nên COMMIT từng row bên trong cursor fetch loop?

**Câu 16.** Cách ước lượng ban đầu dung lượng undo cần thiết là gì?

**Câu 17.** Vì sao tăng UNDO_RETENTION mà không tăng tablespace có thể không giải quyết ORA-01555?

**Câu 18.** Khi gặp ORA-30036, vì sao phải kiểm tra cả ASM/filesystem?

**Câu 19.** Vì sao không nên kill transaction lớn chỉ để giải phóng undo?

**Câu 20.** AWR/DBA_HIST_UNDOSTAT có lưu ý license nào?

<details>
<summary>Gợi ý đáp án</summary>

1. Rollback, read consistency, instance recovery và một số Flashback features.
2. Query khác có thể cần phiên bản dữ liệu tại SCN cũ hơn để đọc nhất quán.
3. Undo cần để dựng snapshot tại SCN của query đã không còn sẵn có.
4. Oracle không cấp phát được extent tiếp theo cho undo segment trong undo tablespace.
5. Một lỗi là mất undo cần cho consistent read; lỗi kia là không có chỗ cấp phát undo mới.
6. ACTIVE đang được transaction sử dụng; UNEXPIRED còn trong retention; EXPIRED đã hết retention và có thể tái sử dụng.
7. Không trong mọi cấu hình; NOGUARANTEE có thể tái sử dụng unexpired undo khi thiếu chỗ.
8. Không cho phép tái sử dụng unexpired undo trước khi hết retention.
9. Nếu tablespace không thể mở rộng và không được tái sử dụng unexpired undo, transaction mới có thể không cấp phát được extent.
10. Undo generation, query dài nhất, tuned retention, lỗi snapshot-too-old, lỗi no-space và extent steal counts.
11. Lần lượt là lỗi snapshot too old và lần thiếu không gian undo.
12. Oracle đã phải lấy/reuse unexpired undo extent, có nguy cơ ảnh hưởng query dài.
13. So sánh thời gian query dài với retention thực tế.
14. Số undo block transaction hiện đang dùng.
15. Làm tăng overhead, phá vỡ transaction boundary và có thể tạo vấn đề snapshot cho cursor đang mở.
16. Peak undo blocks/second × block size × retention seconds, cộng active transaction headroom và safety margin.
17. Oracle vẫn có thể tái sử dụng undo khi thiếu chỗ nếu NOGUARANTEE.
18. Autoextend phụ thuộc dung lượng storage bên dưới; datafile không thể tăng nếu disk đầy.
19. Rollback có thể kéo dài và tiếp tục tiêu thụ tài nguyên.
20. AWR/ASH và một số historical views/reports yêu cầu Diagnostics Pack license; cần xác nhận entitlement.

</details>

## 16. Tài liệu Oracle chính thức

1. [Oracle Database 19c Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): Automatic Undo Management, undo retention, undo tablespace và sizing.
2. [Oracle Database 19c Administrator's Guide — Managing Undo Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): retention guarantee, undo advisor và vận hành undo.
3. [Oracle Database 19c Reference — V$UNDOSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-UNDOSTAT.html): undo workload, retention và error counters.
4. [Oracle Database 19c Reference — DBA_UNDO_EXTENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_UNDO_EXTENTS.html): trạng thái ACTIVE, UNEXPIRED và EXPIRED.
5. [Oracle Database 19c Reference — V$TRANSACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-TRANSACTION.html): transaction và undo usage.
6. [Oracle Database Error Messages — ORA-01555](https://docs.oracle.com/en/error-help/db/ora-01555/): snapshot too old.
7. [Oracle Database Error Messages — ORA-30036](https://docs.oracle.com/en/error-help/db/ora-30036/): unable to extend segment in undo tablespace.
8. [Oracle Database 19c SQL Language Reference — ALTER TABLESPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLESPACE.html): thay đổi retention guarantee.
9. [Oracle Database 19c Reference — UNDO_RETENTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/UNDO_RETENTION.html): tham số retention.

**Nguyên tắc cần nhớ:** ORA-01555 là query không còn đủ undo để dựng snapshot nhất quán; ORA-30036 là transaction không cấp phát được undo extent. Chẩn đoán bằng V$UNDOSTAT, DBA_UNDO_EXTENTS, V$TRANSACTION, datafile và storage. Sizing phải dựa trên peak undo generation, query/Flashback retention, active transaction và headroom. RETENTION GUARANTEE bảo vệ unexpired undo nhưng có thể làm DML thất bại khi hết chỗ; NOGUARANTEE ưu tiên transaction mới nhưng query dài có thể gặp snapshot too old.
