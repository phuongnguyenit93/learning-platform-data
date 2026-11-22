# Lựa chọn cách khắc phục xóa nhầm, cập nhật nhầm hoặc triển khai lỗi bằng Oracle Flashback

Khi dữ liệu bị xóa nhầm, cập nhật sai hoặc một lần triển khai làm hỏng trạng thái database, câu hỏi đầu tiên không phải là “chạy lệnh Flashback nào?” mà là **cần quay lại phạm vi nào, đến thời điểm nào và có chấp nhận mất những thay đổi hợp lệ phát sinh sau đó hay không**.

Oracle cung cấp nhiều cơ chế phục hồi có phạm vi rất khác nhau:

- **ROLLBACK** hủy thay đổi của transaction chưa COMMIT.
- **Flashback Query và Flashback Versions Query** đọc lại dữ liệu ở thời điểm trước hoặc xem các phiên bản hàng đã thay đổi.
- **Flashback Table** đưa một hoặc nhiều bảng về trạng thái trước đó.
- **Flashback Drop** khôi phục bảng vừa DROP nếu object còn trong recycle bin.
- **Flashback Database** đưa toàn bộ database hoặc phạm vi được hỗ trợ về một SCN, timestamp hoặc restore point.
- **RMAN point-in-time recovery (PITR)** khôi phục database, tablespace, PDB hoặc table tới một thời điểm dựa trên backup và archived redo.

Mỗi phương án có điều kiện tiên quyết, giới hạn và blast radius khác nhau. Flashback Query thường phù hợp để đọc và tái dựng dữ liệu; Flashback Table thay đổi cả bảng; Flashback Database có thể làm mất toàn bộ giao dịch sau mốc phục hồi; RMAN PITR cần backup/recovery infrastructure và có thể tốn thời gian.

Bài học lấy Oracle Database 19c làm mốc. Trọng tâm là chọn đúng phương pháp cho accidental DELETE/UPDATE, DROP/TRUNCATE, triển khai DDL/DML lỗi và sự cố cần phục hồi rộng hơn; sau đó xác minh dữ liệu, kiểm soát giao dịch phát sinh và ghi lại bằng chứng phục hồi.

## 1. Bắt đầu bằng phân loại sự cố

### 1.1. Năm câu hỏi quyết định phương án

Trước khi chạy bất kỳ lệnh phục hồi nào, xác định:

1. **Thay đổi đã COMMIT chưa?** Nếu chưa, ROLLBACK hoặc ROLLBACK TO SAVEPOINT có thể giải quyết trực tiếp.
2. **Loại thay đổi là gì?** DELETE, UPDATE, INSERT sai, DROP, TRUNCATE, DDL, thay đổi cấu hình hay hỏng vật lý.
3. **Phạm vi cần phục hồi là gì?** Một vài hàng, một bảng, một tablespace/PDB hay toàn database.
4. **Mốc dữ liệu cần quay về là gì?** SCN, timestamp, transaction hoặc restore point nào?
5. **Các thay đổi hợp lệ sau mốc đó có cần giữ không?** Đây là yếu tố thường quyết định Flashback Table/compensating DML hay Flashback Database/PITR.

Nếu chưa biết chính xác thời điểm lỗi, hãy xác định từ application log, deployment log, audit trail, transaction ID và SCN trước khi thực hiện phục hồi.

### 1.2. Ma trận chọn phương án nhanh

| Tình huống | Phương án thường xem xét đầu tiên | Phạm vi ảnh hưởng | Điều kiện/giới hạn chính |
| --- | --- | --- | --- |
| DELETE/UPDATE chưa COMMIT | ROLLBACK hoặc ROLLBACK TO SAVEPOINT | Transaction hiện tại | Session/transaction còn tồn tại |
| DELETE/UPDATE đã COMMIT, chỉ cần xem dữ liệu cũ | Flashback Query | Đọc lịch sử hàng | Undo còn giữ phiên bản cần thiết |
| Chỉ một số hàng bị sửa sai, cần giữ thay đổi hợp lệ khác | Flashback Query/Versions Query rồi compensating DML | Hàng được chọn | Phải xác định chính xác hàng và thứ tự thay đổi |
| Cả bảng cần trở về thời điểm trước lỗi | Flashback Table | Toàn bộ bảng được chỉ định | Row movement, undo/history và giới hạn DDL |
| Bảng vừa DROP | Flashback Drop | Object trong recycle bin | Chưa PURGE, recycle bin có bản phù hợp |
| Bảng vừa TRUNCATE | RMAN RECOVER TABLE hoặc phục hồi rộng hơn | Bảng được khôi phục qua auxiliary database | Flashback Table không hoàn tác TRUNCATE |
| DDL/deployment lỗi, cần quay cả database | Flashback Database tới restore point/SCN | Toàn database | Flashback logs và chấp nhận bỏ thay đổi sau mốc |
| Cần khôi phục từ backup hoặc flashback logs không đủ | RMAN PITR | Database/tablespace/PDB/table tùy kỹ thuật | Backup, archived redo và quy trình recovery |
| Hỏng datafile/storage | RMAN restore/recover | File/tablespace/database | Flashback đơn thuần không thay thế media recovery |

Ma trận này là điểm bắt đầu. Trước khi chạy, xác nhận đúng loại sự cố, thời điểm và phạm vi. Không chọn Flashback Database chỉ vì lệnh có vẻ ngắn hơn nếu chỉ một bảng bị ảnh hưởng.

### 1.3. Xác định blast radius

Blast radius là phạm vi dữ liệu và workload bị tác động bởi thao tác phục hồi:

- ROLLBACK: các thay đổi trong transaction hiện tại.
- Compensating DML: các hàng/thuộc tính mà script phục hồi chủ động sửa.
- Flashback Table: các bảng được chỉ định; những thay đổi hợp lệ sau mốc trên các bảng đó có thể bị mất.
- Flashback Drop: object được khôi phục từ recycle bin; cần kiểm tra phụ thuộc.
- Flashback Database: toàn bộ database được đưa về mốc trước đó; giao dịch sau mốc bị loại khỏi trạng thái hiện tại.
- RMAN PITR: phạm vi phụ thuộc database, tablespace, PDB hoặc table được chọn.

Phạm vi phục hồi càng rộng, yêu cầu phối hợp ứng dụng, backup, validation và thời gian downtime càng cao.

## 2. Xác định thời điểm và SCN của sự cố

### 2.1. Timestamp và SCN

SCN (System Change Number) là số thứ tự logic Oracle dùng để xác định một điểm nhất quán trong database. Nhiều thao tác Flashback và RMAN có thể nhận SCN làm mốc.

Timestamp dễ liên hệ với application log hơn, nhưng SCN thường hữu ích cho việc xác định chính xác điểm phục hồi. Hãy ghi cả hai khi có thể.

### 2.2. Chuyển đổi SCN và timestamp

Oracle cung cấp các hàm chuyển đổi:

~~~sql
SELECT SCN_TO_TIMESTAMP(123456789) AS approximate_time
FROM   dual;
~~~

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP('2026-11-14 01:30:00',
                        'YYYY-MM-DD HH24:MI:SS')
       ) AS target_scn
FROM   dual;
~~~

SCN_TO_TIMESTAMP chỉ ánh xạ được trong phạm vi thông tin ánh xạ còn được lưu; đây không phải dịch vụ lưu lịch sử SCN vô hạn. Timestamp-to-SCN cũng cần mốc nằm trong phạm vi hỗ trợ của database. Với recovery quan trọng, không suy ra SCN bằng phép tính thời gian thủ công.

### 2.3. Tìm SCN từ transaction hoặc audit

Nếu ứng dụng ghi transaction ID/request ID, hãy đối chiếu:
- Application log và deployment log.
- Unified audit trail.
- Flashback Versions Query.
- FLASHBACK_TRANSACTION_QUERY khi có dữ liệu cần thiết.
- Restore point và alert log.
- Backup/archivelog metadata.

Một audit record có timestamp không nhất thiết là SCN chính xác của mọi thay đổi trong transaction. Hãy dùng nhiều nguồn để khoanh vùng.

### 2.4. Xác định database mode và khả năng Flashback

~~~sql
SELECT name,
       open_mode,
       log_mode,
       flashback_on,
       database_role
FROM   v$database;
~~~

Các trường quan trọng:
- LOG_MODE: database có ở ARCHIVELOG hay không.
- FLASHBACK_ON: trạng thái Flashback Database.
- DATABASE_ROLE: primary, physical standby hoặc role khác.
- OPEN_MODE: trạng thái hiện tại.

Flashback Query/Table dựa trên undo và có điều kiện khác với Flashback Database. FLASHBACK_ON = NO không đồng nghĩa mọi tính năng Flashback đều không dùng được.

### 2.5. Kiểm tra flashback log window

~~~sql
SELECT oldest_flashback_scn,
       oldest_flashback_time,
       retention_target,
       flashback_size,
       estimated_flashback_size
FROM   v$flashback_database_log;
~~~

View này hữu ích khi Flashback Database được cấu hình và có thông tin flashback log. Nó cho biết phạm vi flashback ước lượng còn có thể đáp ứng. Không dùng một cột riêng lẻ để cam kết phục hồi chắc chắn; kiểm tra FRA, log, restore point và trạng thái database.

## 3. Transaction chưa COMMIT: ROLLBACK trước tiên

### 3.1. DELETE chưa COMMIT

~~~sql
DELETE FROM orders
WHERE  order_id = 9001;

-- Phát hiện xóa nhầm trước COMMIT:
ROLLBACK;
~~~

ROLLBACK hủy các thay đổi chưa commit trong transaction hiện tại. Nếu transaction có nhiều thao tác hợp lệ và sai lẫn nhau, có thể cần ROLLBACK TO SAVEPOINT thay vì rollback toàn bộ.

### 3.2. Dùng SAVEPOINT

~~~sql
SAVEPOINT before_risky_update;

UPDATE accounts
SET    balance = balance - 500
WHERE  account_id = 1001;

-- Phát hiện sai:
ROLLBACK TO SAVEPOINT before_risky_update;
~~~

SAVEPOINT cho phép quay transaction về điểm đánh dấu mà không hủy các thao tác trước savepoint.

### 3.3. Transaction đã COMMIT

Sau COMMIT, ROLLBACK thông thường không thể hoàn tác transaction đó. Lúc này cần xác định dữ liệu cũ có còn trong undo hay không, table/object có còn trong recycle bin hay cần phục hồi từ backup/Flashback Database.

Không chạy ROLLBACK trong một session khác với kỳ vọng nó hủy transaction đã commit của session trước.

### 3.4. DDL và implicit commit

Oracle thực hiện implicit commit quanh nhiều câu lệnh DDL. Vì vậy, không thể dựa vào ROLLBACK để hoàn tác một deployment đã chạy CREATE, ALTER, DROP hoặc TRUNCATE rồi thất bại ở bước tiếp theo.

Một script deployment có thể:
- Commit DML trước khi chạy DDL.
- Thực hiện DDL và commit ngầm.
- Thất bại ở giữa migration.
- Để lại schema ở trạng thái nửa cũ nửa mới.

Cần chọn phương án phục hồi theo từng thay đổi đã thực sự xảy ra, không giả định toàn bộ script là một transaction nguyên tử.

## 4. Flashback Query — đọc dữ liệu tại thời điểm trước

### 4.1. Đọc bảng AS OF SCN

Flashback Query cho phép truy vấn dữ liệu ở một SCN trước đó:

~~~sql
SELECT order_id,
       status,
       total_amount
FROM   orders AS OF SCN 123456789
WHERE  order_id = 9001;
~~~

Kết quả phản ánh phiên bản dữ liệu nhất quán tại SCN chỉ định, nếu Oracle còn đủ undo để tái dựng phiên bản đó.

### 4.2. Đọc bảng AS OF TIMESTAMP

~~~sql
SELECT order_id,
       status,
       total_amount
FROM   orders AS OF TIMESTAMP
       TO_TIMESTAMP('2026-11-14 01:30:00',
                    'YYYY-MM-DD HH24:MI:SS')
WHERE  order_id = 9001;
~~~

Timestamp hữu ích khi thời điểm lỗi được biết từ deployment log hoặc ứng dụng. Nếu cần độ chính xác cao, xác định SCN và kiểm tra kết quả tại điểm đó.

### 4.3. So sánh hiện tại với lịch sử

~~~sql
SELECT current_row.order_id,
       current_row.status AS current_status,
       old_row.status AS old_status,
       current_row.total_amount AS current_amount,
       old_row.total_amount AS old_amount
FROM   orders current_row
JOIN   orders AS OF SCN 123456789 old_row
       ON old_row.order_id = current_row.order_id
WHERE  current_row.order_id = 9001;
~~~

Câu truy vấn này giúp xem giá trị hiện tại khác giá trị ở mốc SCN ra sao. Nếu hàng hiện tại đã bị xóa, cần dùng truy vấn lịch sử phù hợp hoặc outer join từ tập khóa đã biết.

### 4.4. Dựng lại các hàng đã bị xóa

Nếu biết khóa của hàng bị xóa, có thể truy vấn phiên bản trước và dùng kết quả làm nguồn cho INSERT phục hồi:

~~~sql
SELECT order_id,
       customer_id,
       status,
       total_amount,
       created_at
FROM   orders AS OF SCN 123456789
WHERE  order_id IN (9001, 9002, 9003);
~~~

Sau khi kiểm tra dữ liệu, có thể tạo bảng staging hoặc INSERT có chọn lọc. Không chèn ngay vào bảng thật nếu chưa kiểm tra:
- Primary/unique key có đang tồn tại không.
- Foreign key có còn hợp lệ không.
- Trigger có phát sinh side effect không.
- Các cột identity/default/generated có quy tắc gì.
- Hàng có được tạo lại hợp lệ bởi nghiệp vụ sau thời điểm đó không.

### 4.5. Undo retention và ORA-01555

Flashback Query dựa trên thông tin phiên bản cũ. Nếu undo cần thiết đã bị tái sử dụng, truy vấn có thể thất bại, thường với ORA-01555: snapshot too old.

Khả năng truy vấn lịch sử phụ thuộc:
- UNDO_RETENTION.
- Kích thước undo tablespace và tốc độ sinh undo.
- Concurrent DML.
- Thời gian từ lúc thay đổi đến lúc truy vấn.
- Cấu hình retention guarantee và workload.

UNDO_RETENTION là mục tiêu, không phải bảo đảm tuyệt đối trong mọi cấu hình. Nếu dữ liệu lịch sử cần giữ lâu dài, hãy thiết kế Flashback Data Archive hoặc backup/archival phù hợp thay vì dựa vào undo thông thường.

### 4.6. Quyền truy vấn Flashback

Người dùng cần quyền phù hợp trên object và khả năng dùng Flashback Query. Tùy trường hợp có thể cần SELECT, FLASHBACK object privilege hoặc quyền quản trị rộng hơn. Cấp quyền tối thiểu cần thiết; không cấp SELECT ANY TABLE chỉ để khôi phục một bảng.

## 5. Flashback Versions Query — xem các phiên bản hàng

### 5.1. Mục đích

Flashback Versions Query cho biết các phiên bản hàng trong một khoảng SCN hoặc timestamp. Nó hữu ích khi:
- Cần biết hàng đã thay đổi bao nhiêu lần.
- Cần xác định thao tác INSERT/UPDATE/DELETE.
- Cần tìm transaction ID liên quan.
- Cần chọn đúng phiên bản trước khi chạy compensating DML.

### 5.2. Truy vấn phiên bản theo SCN

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid,
       order_id,
       status,
       total_amount
FROM   orders
       VERSIONS BETWEEN SCN 123456000 AND 123456900
WHERE  order_id = 9001
ORDER  BY versions_startscn;
~~~

Các pseudo-column:
- VERSIONS_STARTSCN: SCN bắt đầu phiên bản.
- VERSIONS_ENDSCN: SCN kết thúc phiên bản, có thể NULL với phiên bản hiện hành.
- VERSIONS_OPERATION: thao tác tạo phiên bản, thường là I, U hoặc D.
- VERSIONS_XID: transaction ID liên quan.

Một số giá trị có thể NULL tùy loại phiên bản và khả năng truy xuất. Đọc cùng dữ liệu ứng dụng và transaction context.

### 5.3. Truy vấn phiên bản theo thời gian

~~~sql
SELECT versions_starttime,
       versions_endtime,
       versions_operation,
       versions_xid,
       order_id,
       status
FROM   orders
       VERSIONS BETWEEN TIMESTAMP
           TO_TIMESTAMP('2026-11-14 01:00:00',
                        'YYYY-MM-DD HH24:MI:SS')
       AND TO_TIMESTAMP('2026-11-14 02:00:00',
                        'YYYY-MM-DD HH24:MI:SS')
WHERE  order_id = 9001
ORDER  BY versions_starttime;
~~~

Tên pseudo-column STARTTIME/ENDTIME cung cấp thông tin thời gian phiên bản. Nếu cần điểm phục hồi chính xác, sử dụng SCN sau khi xác minh.

### 5.4. Hạn chế

Versions Query không phải audit log dài hạn:
- Phụ thuộc undo còn sẵn.
- Không nhất thiết hiển thị toàn bộ lịch sử của mọi object.
- Một số thao tác DDL hoặc loại object không được hỗ trợ như DML row history.
- Phiên bản đã bị purge/reuse không thể tái dựng bằng query.
- Không thay thế backup hoặc audit trail.

## 6. Truy vấn thông tin transaction và UNDO_SQL

### 6.1. FLASHBACK_TRANSACTION_QUERY

View FLASHBACK_TRANSACTION_QUERY có thể cung cấp thông tin transaction và SQL dùng để đảo ngược một số thay đổi:

~~~sql
SELECT xid,
       start_scn,
       commit_scn,
       logon_user,
       operation,
       table_name,
       undo_sql
FROM   flashback_transaction_query
WHERE  table_name = 'ORDERS'
ORDER  BY commit_scn DESC;
~~~

Để tìm đúng transaction, có thể lọc theo XID lấy từ VERSIONS_XID và theo khoảng SCN/thời gian.

### 6.2. Supplemental logging

Khả năng truy vấn transaction và dựng thông tin cần thiết có thể phụ thuộc supplemental logging và dữ liệu redo/undo còn sẵn. Nếu cần điều tra sâu, DBA phải kiểm tra cấu hình logging đã có tại thời điểm sự kiện; bật supplemental logging sau sự cố không tái tạo thông tin đã mất.

### 6.3. UNDO_SQL là gợi ý, không phải script khôi phục an toàn

UNDO_SQL có thể hữu ích để hiểu cách đảo ngược một DML. Tuy nhiên, không nên copy toàn bộ nội dung rồi chạy trực tiếp trên production:
- Dữ liệu có thể đã thay đổi thêm sau transaction gốc.
- Ràng buộc và thứ tự transaction có thể tạo dependency.
- Trigger có thể tạo side effect.
- SQL có thể cần giá trị khóa hoặc context chính xác.
- Nhiều transaction có thể phụ thuộc nhau.

Hãy kiểm tra từng câu, dựng dữ liệu mục tiêu và chạy trong transaction có thể kiểm soát.

### 6.4. DBMS_FLASHBACK.TRANSACTION_BACKOUT

Oracle có cơ chế Transaction Backout để đảo ngược một hoặc nhiều transaction theo dependency analysis. Đây là phương án chuyên biệt, không phải lựa chọn mặc định cho mọi UPDATE/DELETE nhầm. Cần hiểu dependency, cascade option, quyền, giới hạn và kiểm thử trước khi sử dụng.

Với một vài hàng sai, Flashback Query/Versions Query rồi compensating DML thường dễ kiểm soát hơn. Với transaction phức tạp, hãy tham khảo package reference và DBA có kinh nghiệm.

## 7. Flashback Table — đưa cả bảng về trạng thái cũ

### 7.1. Khi nào phù hợp?

Flashback Table phù hợp khi:
- Một bảng bị cập nhật hoặc xóa nhầm trên diện rộng.
- Cần khôi phục toàn bộ bảng về trước sự kiện.
- Có đủ undo để dựng lại trạng thái.
- Chấp nhận rằng thay đổi hợp lệ trên bảng sau mốc đó cũng sẽ bị quay lại.

Nếu chỉ một vài hàng sai trong khi phần lớn bảng có thay đổi hợp lệ sau mốc, Flashback Table có thể gây mất dữ liệu mới. Hãy cân nhắc Flashback Query và compensating DML.

### 7.2. Bật row movement

Flashback Table yêu cầu row movement được bật:

~~~sql
ALTER TABLE orders ENABLE ROW MOVEMENT;
~~~

Kiểm tra:

~~~sql
SELECT table_name,
       row_movement
FROM   user_tables
WHERE  table_name = 'ORDERS';
~~~

Row movement cho phép ROWID của hàng thay đổi trong một số thao tác. Ứng dụng không nên xem ROWID là khóa nghiệp vụ ổn định.

### 7.3. Flashback Table về SCN

~~~sql
FLASHBACK TABLE orders
TO SCN 123456789;
~~~

Lệnh này đưa bảng về trạng thái tại SCN được chỉ định. Nó ảnh hưởng toàn bộ bảng được nêu, không chỉ một hàng. Có thể cần xử lý các bảng liên quan, khóa và ràng buộc trước khi thực hiện.

### 7.4. Flashback Table về timestamp

~~~sql
FLASHBACK TABLE orders
TO TIMESTAMP TO_TIMESTAMP(
    '2026-11-14 01:30:00',
    'YYYY-MM-DD HH24:MI:SS'
);
~~~

Timestamp phải nằm trong phạm vi undo/history có thể sử dụng. Nếu có thể, chuyển và ghi lại SCN để làm mốc phục hồi rõ ràng.

### 7.5. Flashback nhiều bảng

~~~sql
FLASHBACK TABLE orders, order_items
TO SCN 123456789;
~~~

Các bảng liên quan có thể cần quay về cùng một mốc để giữ tính nhất quán nghiệp vụ. Kiểm tra foreign key, trigger, materialized view, index và dữ liệu liên quan trước khi phục hồi.

### 7.6. Những điều cần kiểm tra trước Flashback Table

- Undo còn đủ để phục hồi tới mốc.
- Table có row movement enabled.
- Không có DDL không tương thích sau mốc.
- Không có transaction đang giữ lock gây cản trở.
- Các bảng phụ thuộc có cần flashback cùng thời điểm không.
- Có thể chấp nhận mất thay đổi hợp lệ sau mốc trên bảng không.
- Có staging/backup để bảo toàn dữ liệu hiện tại nếu cần đối chiếu.

Flashback Table có các giới hạn với một số loại object và thao tác DDL. Đọc SQL Language Reference của đúng release trước khi thực hiện trên bảng đặc biệt, partitioned table, object có dependency hoặc bảng thuộc cấu trúc phức tạp.

### 7.7. Xác minh sau Flashback Table

Sau khi lệnh hoàn tất:
1. Đếm hàng và kiểm tra các khóa nghiệp vụ.
2. So sánh mẫu dữ liệu với trạng thái mong muốn.
3. Kiểm tra constraint và index.
4. Kiểm tra trigger và trạng thái row movement.
5. Chạy truy vấn nghiệp vụ quan trọng.
6. Xác nhận application service hoạt động.
7. Ghi nhận các thay đổi hợp lệ sau mốc đã bị quay lại và xử lý bù nếu cần.

Không chỉ dựa vào việc câu lệnh FLASHBACK TABLE trả về thành công.

## 8. Flashback Drop — khôi phục bảng bị DROP

### 8.1. Recycle bin

Khi recycle bin được bật và object đủ điều kiện, DROP TABLE có thể chuyển object vào recycle bin thay vì xóa segment ngay lập tức.

Kiểm tra recycle bin:

~~~sql
SHOW PARAMETER recyclebin;
~~~

Xem object:

~~~sql
SELECT object_name,
       original_name,
       type,
       droptime,
       dropscn,
       can_undrop,
       can_purge
FROM   user_recyclebin
ORDER  BY droptime DESC;
~~~

Recycle bin không phải backup. Object có thể bị purge do user/DBA purge hoặc do space pressure.

### 8.2. Khôi phục bảng theo tên gốc

~~~sql
FLASHBACK TABLE orders
TO BEFORE DROP;
~~~

Nếu có nhiều object cùng original name trong recycle bin, có thể cần chỉ định tên recycle bin phù hợp thay vì tên gốc.

### 8.3. Khôi phục với tên mới

~~~sql
FLASHBACK TABLE orders
TO BEFORE DROP
RENAME TO orders_recovered;
~~~

Dùng tên mới khi bảng gốc đã được tạo lại hoặc cần kiểm tra dữ liệu trước khi thay thế object hiện hành.

### 8.4. Khôi phục theo recycle bin object name

~~~sql
SELECT object_name,
       original_name,
       type,
       droptime
FROM   user_recyclebin
WHERE  original_name = 'ORDERS'
ORDER  BY droptime DESC;
~~~

Có thể dùng object_name dạng BIN$... trong câu FLASHBACK TABLE TO BEFORE DROP khi cần chọn đúng phiên bản object đã bị drop.

### 8.5. Giới hạn của Flashback Drop

Flashback Drop không khôi phục được object đã bị PURGE hoặc không còn trong recycle bin. Các trường hợp sau cần phương án khác:
- DROP TABLE PURGE.
- Recycle bin bị tắt.
- Object đã bị purge do space pressure.
- Object thuộc loại không được hỗ trợ.
- Đối tượng phụ thuộc hoặc tên object đã được tái sử dụng.

Flashback Drop không phải cách hoàn tác TRUNCATE. Nếu bảng chỉ bị truncate, xem RMAN RECOVER TABLE hoặc phương án phục hồi rộng hơn.

### 8.6. Sau khi khôi phục

Kiểm tra:
- Bảng và dữ liệu.
- Index, constraint, trigger.
- Grant và synonym.
- Dependent object.
- Tên object và các object cùng tên đã được tạo lại.
- Application reference.

Một số object phụ thuộc có thể cần kiểm tra/recompile hoặc khôi phục riêng theo trạng thái trước DROP.

## 9. Flashback Database — quay toàn database về mốc trước

### 9.1. Khi nào nên dùng?

Flashback Database phù hợp khi lỗi ảnh hưởng rộng:
- Deployment làm thay đổi nhiều schema/object.
- DML/DDL sai trên diện rộng.
- Database cần quay về trước một release hoặc thao tác quản trị.
- Có restore point hoặc SCN rõ ràng.
- Có flashback logs bao phủ mốc cần quay về.

Đây là phương án có blast radius lớn. Database được đưa về trạng thái tại mốc đó; các giao dịch sau mốc không còn trong trạng thái hiện tại. Nếu các giao dịch sau mốc là hợp lệ và cần giữ, phải trích xuất/đối chiếu và áp dụng lại theo kế hoạch.

### 9.2. Điều kiện chính

Flashback Database cần cấu hình và tài nguyên phù hợp, bao gồm:
- Database ở ARCHIVELOG mode cho quy trình Flashback Database thông thường.
- Flashback Database được bật hoặc có guaranteed restore point đáp ứng điều kiện sử dụng.
- Flash Recovery Area (FRA) có đủ dung lượng cho flashback logs và các file liên quan.
- Flashback logs còn bao phủ mốc mục tiêu.
- Database và file cần thiết còn khả dụng.

Kiểm tra:

~~~sql
SELECT log_mode,
       flashback_on
FROM   v$database;
~~~

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
SHOW PARAMETER db_flashback_retention_target;
~~~

Flashback retention target là mục tiêu, không phải cam kết rằng mọi mốc đều còn sẵn. Kiểm tra oldest flashback SCN/time và FRA usage trước khi quyết định.

### 9.3. Restore point thường

Tạo restore point:

~~~sql
CREATE RESTORE POINT before_release_2026_11_14;
~~~

Restore point thường lưu tên và SCN để tham chiếu thuận tiện. Nó không tự bảo đảm flashback logs được giữ lại đến restore point nếu không có cơ chế bảo đảm tương ứng.

### 9.4. Guaranteed restore point

~~~sql
CREATE RESTORE POINT before_release_2026_11_14
GUARANTEE FLASHBACK DATABASE;
~~~

Guaranteed restore point yêu cầu Oracle giữ flashback logs cần thiết để có thể flashback về mốc đó, nhưng các log này tiêu thụ FRA. Nếu không gian FRA cạn, database có thể gặp vấn đề nghiêm trọng do không thể xóa log được bảo vệ bởi restore point.

Chỉ tạo guaranteed restore point khi:
- Có kế hoạch thời gian giữ rõ ràng.
- Đã tính dung lượng FRA và tốc độ thay đổi dữ liệu.
- Có monitoring cảnh báo FRA.
- Có người chịu trách nhiệm xóa restore point sau khi release được chấp nhận.

### 9.5. Xem restore point

~~~sql
SELECT name,
       scn,
       time,
       guarantee_flashback_database,
       storage_size,
       preserved
FROM   v$restore_point
ORDER  BY time DESC;
~~~

Tên cột có thể phụ thuộc trạng thái/release; dùng DESC V$RESTORE_POINT nếu cần. Kiểm tra SCN, timestamp, guarantee flag và dung lượng được giữ.

### 9.6. Flashback Database tới restore point

Quy trình khái quát trong môi trường single-instance:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO RESTORE POINT before_release_2026_11_14;

ALTER DATABASE OPEN RESETLOGS;
~~~

Đây là thao tác phục hồi database-wide, cần DBA điều phối và dừng ứng dụng. Trong RAC, Data Guard hoặc CDB/PDB, quy trình có thêm yêu cầu riêng; không áp dụng nguyên mẫu này mà chưa kiểm tra kiến trúc.

### 9.7. Flashback Database tới SCN hoặc timestamp

~~~sql
FLASHBACK DATABASE TO SCN 123456789;
~~~

Hoặc:

~~~sql
FLASHBACK DATABASE TO TIMESTAMP
TO_TIMESTAMP('2026-11-14 01:30:00',
             'YYYY-MM-DD HH24:MI:SS');
~~~

Sau flashback database, thường cần OPEN RESETLOGS để mở database ở incarnation mới theo quy trình. Kiểm tra hướng dẫn recovery và trạng thái database trước khi mở.

### 9.8. Flashback Database không phải rollback một bảng

Flashback Database quay database về một mốc nhất quán. Nó không chọn một bảng để quay lại trong khi giữ mọi object khác ở hiện tại.

Nếu chỉ một bảng bị ảnh hưởng, xem:
- Flashback Query/Versions Query để tái dựng hàng.
- Flashback Table nếu toàn bảng có thể quay lại.
- Flashback Drop nếu object bị DROP.
- RMAN RECOVER TABLE nếu cần phục hồi riêng table từ backup.

### 9.9. Sau OPEN RESETLOGS

Sau khi database mở:
- Xác nhận database open mode và incarnation.
- Kiểm tra PDB/service.
- Xác minh dữ liệu và schema.
- Chạy smoke test ứng dụng.
- Đánh giá transaction sau mốc bị loại bỏ.
- Kiểm tra backup strategy và tạo backup mới theo chính sách sau khi mở incarnation mới.
- Kiểm tra Data Guard, replication và downstream consumer theo runbook.

Không để ứng dụng ghi dữ liệu mới trước khi DBA xác nhận trạng thái phục hồi.

### 9.10. Xóa restore point sau khi release ổn định

~~~sql
DROP RESTORE POINT before_release_2026_11_14;
~~~

Chỉ xóa sau khi thời hạn rollback đã kết thúc và owner chấp thuận. Với guaranteed restore point, việc xóa giúp Oracle có thể tái sử dụng flashback logs được giữ riêng cho mốc đó.

## 10. RMAN Point-in-Time Recovery

### 10.1. Khi nào cần RMAN PITR?

RMAN PITR là lựa chọn khi:
- Flashback logs không bao phủ thời điểm cần phục hồi.
- Flashback Database chưa được bật hoặc không đủ điều kiện.
- Cần khôi phục từ backup.
- Cần phục hồi phạm vi database/tablespace/PDB/table theo kỹ thuật RMAN hỗ trợ.
- Có hỏng vật lý hoặc datafile cần restore/recover.

RMAN PITR cần backup phù hợp và archived redo liên tục tới mốc mục tiêu. Nếu thiếu backup hoặc log cần thiết, recovery có thể không đạt tới SCN mong muốn.

### 10.2. Database point-in-time recovery

Mẫu khái quát:

~~~text
RMAN> SHUTDOWN IMMEDIATE;
RMAN> STARTUP MOUNT;
RMAN> RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
RMAN> SQL 'ALTER DATABASE OPEN RESETLOGS';
~~~

Cú pháp và bước chuẩn bị thực tế phụ thuộc control file, catalog, backup location, incarnation, encryption và kiến trúc. Cần kiểm tra backup/archivelog trước, đảm bảo mốc SCN nằm trong phạm vi phục hồi và có kế hoạch cho Data Guard/standby.

### 10.3. Tablespace point-in-time recovery

Nếu chỉ một tablespace cần quay lại, RMAN TSPITR có thể phục hồi tablespace tới một thời điểm mà không đưa toàn bộ database về mốc đó. Oracle sử dụng auxiliary instance để phục hồi và tích hợp tablespace trở lại.

TSPITR có giới hạn về dependency:
- Các object có quan hệ tham chiếu giữa tablespace.
- Index/LOB/partition và object phụ thuộc.
- Undo/system tablespace và các tablespace không thể phục hồi theo cách thông thường.
- Referential integrity và consistency giữa tablespace được phục hồi với phần database còn lại.

Không chọn TSPITR chỉ vì phạm vi nhỏ hơn database PITR; phải xác định dependency và kiểm tra tính nhất quán.

### 10.4. RMAN RECOVER TABLE

Oracle 19c hỗ trợ RMAN table recovery để phục hồi table hoặc partition tới một thời điểm, dùng auxiliary database/instance trong quá trình xử lý rồi đưa object phục hồi về database đích.

Ví dụ minh họa:

~~~text
RMAN> RECOVER TABLE HR.EMPLOYEES
      UNTIL SCN 123456789
      AUXILIARY DESTINATION '/u01/rman_aux'
      REMAP TABLE 'HR'.'EMPLOYEES':'EMPLOYEES_RECOVERED';
~~~

Đường dẫn auxiliary phải tồn tại và có đủ dung lượng/quyền. Cú pháp chính xác có thể cần bổ sung OF PLUGGABLE DATABASE nếu table nằm trong PDB. Xác nhận cú pháp trong RMAN Reference của release đang chạy.

Phục hồi ra tên mới thường an toàn để kiểm tra dữ liệu trước khi thay thế bảng đang hoạt động. Sau đó cần xử lý grant, synonym, constraint, index, trigger và phụ thuộc ứng dụng.

### 10.5. RMAN PITR và Flashback Database

| Tiêu chí | Flashback Database | RMAN database PITR |
| --- | --- | --- |
| Nguồn phục hồi chính | Flashback logs và redo cần thiết | Backup và archived redo |
| Chuẩn bị trước sự cố | Flashback Database/restore point | Backup và archive log policy |
| Thời gian phục hồi | Thường nhanh hơn khi flashback logs còn sẵn | Phụ thuộc restore size và redo apply |
| Phạm vi | Database-wide (hoặc phạm vi hỗ trợ riêng như PDB) | Database/tablespace/PDB/table tùy kỹ thuật |
| Tác động sau phục hồi | Mở theo quy trình RESETLOGS khi cần | PITR thường cần OPEN RESETLOGS |
| Hạn chế | Không có log cần thiết, FRA pressure, blast radius rộng | Thiếu backup/archivelog, auxiliary storage, recovery time |
| Phù hợp | Quay nhanh về mốc gần có flashback logs | Khôi phục từ backup hoặc phạm vi chi tiết hơn |

RMAN có thể là phương án khôi phục table cụ thể mà không phải đưa toàn bộ database về quá khứ. Flashback Database thường thuận tiện khi có restore point và chấp nhận quay cả database.

## 11. Truncate, Drop, DDL và các giới hạn quan trọng

### 11.1. DELETE khác TRUNCATE

DELETE là DML và tạo undo cho các hàng bị xóa. Nếu undo còn đủ, có thể dùng Flashback Query/Table để đọc hoặc phục hồi dữ liệu.

TRUNCATE là DDL:
- Có implicit commit.
- Không tạo undo row-level để khôi phục nội dung đã truncate theo cách Flashback Table.
- Không thể ROLLBACK.
- Không thể dùng Flashback Table để quay lại trạng thái trước TRUNCATE.

Nếu TRUNCATE nhầm:
1. Ngừng các thay đổi tiếp theo trên bảng.
2. Xác định thời điểm và SCN.
3. Kiểm tra backup/archivelog.
4. Dùng RMAN RECOVER TABLE nếu phù hợp.
5. Nếu không thể phục hồi riêng table, đánh giá Flashback Database hoặc PITR với blast radius rõ ràng.

### 11.2. DROP TABLE khác DROP TABLE PURGE

DROP TABLE có thể đưa object vào recycle bin nếu đủ điều kiện. DROP TABLE PURGE bỏ qua recycle bin hoặc xóa object khỏi recycle bin ngay.

- DROP thông thường: thử Flashback Drop.
- DROP PURGE: cần RMAN table recovery, PITR hoặc backup/export.
- Recycle bin đã purge: Flashback Drop không còn dữ liệu để khôi phục.

### 11.3. DDL thay đổi cấu trúc

Flashback Table có giới hạn khi cấu trúc bảng thay đổi sau mốc mục tiêu. Các thao tác như TRUNCATE, MOVE, DROP COLUMN hoặc một số thay đổi partition có thể làm phương án Flashback Table không dùng được theo cách mong muốn.

Khi deployment gồm nhiều DDL:
- Lưu trạng thái schema trước release.
- Tạo restore point hoặc backup phù hợp.
- Ghi rõ từng bước DDL đã chạy thành công.
- Xác định DDL nào đã commit.
- Chọn reverse migration, Flashback Database hoặc RMAN table recovery tùy phạm vi.

Không giả định Flashback Table có thể đảo mọi DDL.

### 11.4. DML và DDL xen kẽ trong deployment

Ví dụ migration:
1. UPDATE dữ liệu chuẩn hóa.
2. ALTER TABLE thêm cột.
3. INSERT dữ liệu mapping.
4. CREATE INDEX.
5. Script lỗi ở bước tiếp theo.

Rollback transaction không thể đưa database về trước toàn bộ migration vì DDL đã commit ngầm. Hãy xác định:
- DML nào đã commit.
- DDL nào đã hoàn tất.
- Object nào đã tạo/đổi.
- Application version nào đang chạy.
- Dữ liệu mới có phát sinh sau migration không.

Có thể cần reverse migration cho schema, compensating DML cho dữ liệu, hoặc Flashback Database nếu muốn quay toàn database về trước deployment.

## 12. Tình huống mẫu: DELETE nhầm một số đơn hàng đã commit

### 12.1. Ngừng tác động và xác định mốc

Giả sử ứng dụng xóa nhầm order_id 9001 và 9002, transaction đã COMMIT lúc khoảng 01:30. Ngừng job liên quan có thể tiếp tục cập nhật các hàng đó. Lấy SCN gần thời điểm lỗi và xác nhận bằng log.

### 12.2. Kiểm tra dữ liệu trước DELETE

~~~sql
SELECT order_id,
       customer_id,
       status,
       total_amount
FROM   orders AS OF TIMESTAMP
       TO_TIMESTAMP('2026-11-14 01:29:00',
                    'YYYY-MM-DD HH24:MI:SS')
WHERE  order_id IN (9001, 9002);
~~~

Kiểm tra kết quả và các khóa liên quan. Nếu undo không còn đủ, truy vấn có thể lỗi; chuyển sang RMAN recovery.

### 12.3. Kiểm tra dữ liệu hiện tại

~~~sql
SELECT order_id,
       customer_id,
       status,
       total_amount
FROM   orders
WHERE  order_id IN (9001, 9002);
~~~

Nếu không còn hàng, đó là kết quả mong đợi sau DELETE. Nếu một hàng đã được tạo lại hoặc có dữ liệu mới, cần điều tra trước khi INSERT.

### 12.4. Phục hồi có kiểm soát

Có thể INSERT các hàng đã xác minh từ Flashback Query:

~~~sql
INSERT INTO orders (
    order_id,
    customer_id,
    status,
    total_amount
)
SELECT old_row.order_id,
       old_row.customer_id,
       old_row.status,
       old_row.total_amount
FROM   orders AS OF SCN 123456789 old_row
WHERE  old_row.order_id IN (9001, 9002)
AND    NOT EXISTS (
           SELECT 1
           FROM orders current_row
           WHERE current_row.order_id = old_row.order_id
       );
~~~

Đây chỉ là ví dụ minh họa. Bảng thật có thể có thêm cột NOT NULL, identity, audit columns, trigger hoặc bảng con. Cần xác minh tất cả dependency và xử lý child rows theo thứ tự foreign key.

### 12.5. Xác minh

- Kiểm tra số hàng được INSERT.
- So sánh cột nghiệp vụ với phiên bản lịch sử.
- Kiểm tra foreign key và bảng con.
- Xác nhận không tạo duplicate hoặc side effect.
- Chạy truy vấn nghiệp vụ và smoke test.
- Ghi lại transaction phục hồi và người phê duyệt.

## 13. Tình huống mẫu: UPDATE nhầm một cột trên toàn bảng

### 13.1. Xác định phạm vi

Giả sử script chạy:

~~~sql
UPDATE customers
SET    credit_limit = 0;
COMMIT;
~~~

thay vì chỉ cập nhật một nhóm khách hàng. Nếu bảng có hàng triệu khách và có các thay đổi hợp lệ khác sau đó, Flashback Table có thể đưa toàn bộ bảng về quá khứ và làm mất các thay đổi đó.

### 13.2. Tìm phiên bản trước

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid,
       customer_id,
       credit_limit
FROM   customers
       VERSIONS BETWEEN SCN 123456000 AND 123456900
WHERE  credit_limit = 0
ORDER  BY customer_id, versions_startscn;
~~~

Truy vấn thực tế cần chọn predicate xác định hàng bị cập nhật sai. Không chỉ dựa vào credit_limit = 0 nếu giá trị 0 vốn hợp lệ.

### 13.3. Tạo tập staging trước khi sửa

~~~sql
CREATE TABLE customers_repair_stage AS
SELECT customer_id,
       credit_limit AS old_credit_limit
FROM   customers AS OF SCN 123456789
WHERE  customer_id IN (
    SELECT customer_id
    FROM customers
    WHERE credit_limit = 0
);
~~~

Ví dụ này cần được điều chỉnh để xác định chính xác tập hàng bị lỗi. Không tạo staging bằng predicate rộng có thể gom cả hàng hợp lệ.

### 13.4. Compensating UPDATE

Sau khi kiểm tra staging và xác nhận từng khóa:

~~~sql
UPDATE customers c
SET    credit_limit = (
           SELECT s.old_credit_limit
           FROM customers_repair_stage s
           WHERE s.customer_id = c.customer_id
       )
WHERE  EXISTS (
           SELECT 1
           FROM customers_repair_stage s
           WHERE s.customer_id = c.customer_id
       );
~~~

Trước COMMIT, kiểm tra số hàng bị tác động và giá trị mới. Nếu không đúng, ROLLBACK. Lưu ý nếu bảng có update hợp lệ sau mốc, hãy xác định chính sách merge thay vì ghi đè toàn bộ hàng.

## 14. Tình huống mẫu: deployment lỗi sau DDL

### 14.1. Trước deployment

Nếu release có rủi ro cao:
- Xác nhận backup gần nhất và khả năng restore.
- Tạo restore point (guaranteed nếu đã tính FRA và có yêu cầu quay nhanh).
- Ghi SCN và timestamp.
- Lưu schema metadata, grants và dependency.
- Chuẩn bị migration/reverse migration.
- Định nghĩa tiêu chí rollback và thời gian quyết định.

Ví dụ:

~~~sql
CREATE RESTORE POINT before_app_release
GUARANTEE FLASHBACK DATABASE;
~~~

Đảm bảo FRA còn đủ chỗ và có monitoring trước khi tạo guaranteed restore point.

### 14.2. Deployment thất bại giữa chừng

Không chạy lại toàn bộ script ngay lập tức. Ghi lại:
- Bước nào thành công.
- Bước nào thất bại.
- DDL đã commit.
- DML đã commit.
- Ứng dụng đã bắt đầu ghi dữ liệu theo schema mới chưa.
- Có request/transaction mới sau mốc release không.

### 14.3. Chọn rollback strategy

- Nếu chỉ một bảng bị DML sai và schema không đổi: Flashback Query/compensating DML hoặc Flashback Table.
- Nếu một bảng bị DROP và recycle bin còn object: Flashback Drop.
- Nếu TRUNCATE hoặc DDL không thể đảo cục bộ: RMAN RECOVER TABLE hoặc phục hồi rộng hơn.
- Nếu toàn bộ database phải quay lại trước release và chấp nhận mất giao dịch sau mốc: Flashback Database to restore point.
- Nếu không có flashback logs đủ: RMAN PITR từ backup/archivelog.

### 14.4. Tránh mất giao dịch hợp lệ sau release

Nếu ứng dụng đã tiếp tục nhận request sau khi deployment lỗi, Flashback Database sẽ loại bỏ các thay đổi database sau restore point. Trước khi quay:
- Dừng hoặc drain ứng dụng.
- Xác định giao dịch phát sinh sau mốc.
- Export/stage dữ liệu cần giữ nếu có thể.
- Xác định cách replay/compensate sau khi database được flashback.
- Thông báo downtime và kiểm tra downstream systems.

Không flashback toàn database khi chưa xác định tác động tới giao dịch mới.

### 14.5. Sau khi phục hồi

- Kiểm tra schema version.
- Kiểm tra object validity và invalid objects.
- Kiểm tra dữ liệu nghiệp vụ.
- Kiểm tra grants, synonyms, jobs, triggers.
- Kiểm tra application compatibility.
- Chạy smoke test và reconciliation.
- Tạo backup theo chính sách sau thay đổi incarnation nếu có RESETLOGS.
- Chỉ mở traffic sau khi owner chấp thuận.

## 15. Restore point như một phần của quy trình release

### 15.1. Restore point thường và guaranteed

| Đặc điểm | Restore point thường | Guaranteed restore point |
| --- | --- | --- |
| Lưu tên và SCN | Có | Có |
| Bảo đảm giữ flashback logs tới mốc | Không | Có, trong khi restore point còn tồn tại |
| Tiêu thụ FRA | Không giữ riêng log như guaranteed point | Có thể tăng đáng kể |
| Phù hợp | Đánh dấu mốc tiện tham chiếu | Cửa sổ rollback ngắn có yêu cầu chắc chắn |
| Quản lý sau release | Có thể drop khi không cần | Cần drop đúng hạn để giải phóng log được giữ |

### 15.2. Quy trình release có restore point

1. Xác nhận database ở chế độ hỗ trợ.
2. Kiểm tra FRA usage và free space.
3. Xác định retention period.
4. Tạo restore point có tên gắn với release.
5. Ghi SCN/time vào change record.
6. Thực hiện deployment.
7. Chạy smoke test, validation và monitoring.
8. Nếu release lỗi, quyết định Flashback Database dựa trên giao dịch sau mốc.
9. Nếu release thành công, giữ restore point hết thời hạn rollback rồi drop.
10. Kiểm tra FRA sau khi drop.

### 15.3. Không giữ guaranteed restore point vô thời hạn

Guaranteed restore point có thể khiến flashback logs tiếp tục chiếm FRA. Nếu FRA đầy, archive/backup/flashback hoạt động có thể bị ảnh hưởng. Gắn owner, expiry time và cảnh báo cho mỗi restore point.

## 16. Data Guard, RAC và multitenant

### 16.1. Data Guard

Trong môi trường Data Guard, Flashback Database và PITR có thể ảnh hưởng standby hoặc yêu cầu đồng bộ lại. Sau OPEN RESETLOGS, database incarnation thay đổi và standby cần được xử lý theo quy trình Data Guard phù hợp.

Không áp dụng quy trình single-instance độc lập trên primary mà không đánh giá:
- Standby role và apply lag.
- Flashback Database trên primary/standby.
- Broker configuration.
- Reinstate/failover strategy.
- Redo transport và incarnation.

### 16.2. RAC

Với RAC, phục hồi database-wide là thao tác ở cấp database, không chỉ một instance. Phối hợp shutdown/mount và mở lại theo quy trình cluster/database. Kiểm tra mọi instance và service sau recovery.

### 16.3. CDB/PDB

Oracle 19c hỗ trợ một số phương án Flashback/PITR ở phạm vi PDB tùy điều kiện và cấu hình. Cần xác định:
- CDB root hay PDB.
- Restore point ở phạm vi nào.
- PDB có local undo hay shared undo theo cấu hình.
- RMAN syntax và auxiliary destination.
- Ảnh hưởng tới các PDB khác và common objects.

Không dùng lệnh database-wide trong CDB khi mục tiêu chỉ là một PDB nếu có phương án PDB recovery phù hợp. Tra đúng Oracle Multitenant/Backup and Recovery Guide.

## 17. Những trường hợp Flashback không thay thế backup

Flashback rất hữu ích cho logical error gần đây, nhưng không thay thế backup:
- Datafile bị mất hoặc storage hỏng.
- Flashback logs/undo đã không còn.
- Table bị DROP PURGE và recycle bin không còn.
- TRUNCATE hoặc DDL không thể phục hồi bằng Flashback Table.
- Cần phục hồi tới thời điểm xa hơn dữ liệu Flashback còn giữ.
- Database bị mất control file hoặc cấu trúc vật lý.
- Cần bản sao độc lập để kiểm tra dữ liệu lịch sử.
- Cần khôi phục sau thảm họa tại site khác.

Backup RMAN, archived redo, control file autobackup, recovery catalog và kiểm thử restore vẫn là nền tảng của khả năng phục hồi.

## 18. Checklist trước khi thực hiện phục hồi

### Bằng chứng và mốc thời gian

- [ ] Có incident/change ID và owner chịu trách nhiệm.
- [ ] Đã xác định loại thao tác gây lỗi.
- [ ] Đã xác định thời điểm hoặc SCN mục tiêu.
- [ ] Đã đối chiếu application/audit/deployment log.
- [ ] Đã xác định các transaction hợp lệ sau mốc.

### Điều kiện kỹ thuật

- [ ] Đã kiểm tra ARCHIVELOG, FLASHBACK_ON và FRA.
- [ ] Đã kiểm tra undo retention nếu dùng Flashback Query/Table.
- [ ] Đã kiểm tra recycle bin nếu dùng Flashback Drop.
- [ ] Đã kiểm tra backup và archived redo nếu dùng RMAN.
- [ ] Đã xác định CDB/PDB, RAC, Data Guard.
- [ ] Đã kiểm tra quyền và cú pháp cho đúng release.

### Phạm vi và kế hoạch

- [ ] Đã xác định blast radius.
- [ ] Đã chọn phương án có phạm vi nhỏ nhất đáp ứng mục tiêu.
- [ ] Đã lưu dữ liệu hiện tại nếu cần đối chiếu/replay.
- [ ] Đã dừng hoặc drain ứng dụng khi cần.
- [ ] Đã chuẩn bị validation và rollback/forward-fix.
- [ ] Đã thông báo người chịu trách nhiệm và downtime.

### Sau phục hồi

- [ ] Dữ liệu và schema đã được xác minh.
- [ ] Constraint/index/trigger/grant/dependency đã kiểm tra.
- [ ] Ứng dụng smoke test đạt.
- [ ] Downstream systems/standby đã được kiểm tra.
- [ ] Backup mới được tạo khi quy trình yêu cầu.
- [ ] Incident record lưu SCN, command, thời gian và kết quả.

## 19. Bài thực hành

Dùng schema test riêng, dữ liệu không nhạy cảm và backup có thể phục hồi. Không thử DROP/TRUNCATE hoặc Flashback Database trên production.

### Bài 1 — Rollback transaction

DELETE một hàng, kiểm tra trước COMMIT rồi ROLLBACK. Xác nhận hàng vẫn còn.

### Bài 2 — Flashback Query

UPDATE một hàng và COMMIT. Truy vấn AS OF SCN/TIMESTAMP để đọc giá trị trước thay đổi.

### Bài 3 — Versions Query

Cập nhật cùng một hàng nhiều lần. Dùng VERSIONS BETWEEN SCN để liệt kê operation, SCN và XID.

### Bài 4 — Transaction Query

Tìm XID từ versions query và truy vấn FLASHBACK_TRANSACTION_QUERY. Đọc UNDO_SQL nhưng không thực thi tự động.

### Bài 5 — Compensating DML

Dùng Flashback Query để lấy giá trị cũ của một hàng. Tạo staging, kiểm tra và UPDATE bù trong transaction có thể rollback.

### Bài 6 — Flashback Table

Bật row movement, cập nhật nhiều hàng, xác định SCN rồi FLASHBACK TABLE. So sánh dữ liệu trước/sau và ghi nhận thay đổi hợp lệ bị quay lại.

### Bài 7 — Flashback Drop

Tạo bảng test, DROP không PURGE, xem USER_RECYCLEBIN rồi FLASHBACK TABLE TO BEFORE DROP.

### Bài 8 — Drop và purge

Tạo bảng test thứ hai, DROP TABLE PURGE. Xác nhận Flashback Drop không còn khả dụng và lập phương án RMAN recovery.

### Bài 9 — Truncate

TRUNCATE bảng test có backup phù hợp. Thử Flashback Table để quan sát giới hạn, sau đó phục hồi bằng RMAN RECOVER TABLE trong môi trường test.

### Bài 10 — Restore point thường

Tạo restore point thường, truy vấn V$RESTORE_POINT, rồi drop restore point sau khi hoàn thành.

### Bài 11 — Guaranteed restore point

Trong database test có FRA đủ lớn, tạo guaranteed restore point. Theo dõi V$FLASHBACK_DATABASE_LOG và FRA usage; drop point sau bài tập.

### Bài 12 — Flashback Database

Tạo restore point trước thay đổi test, tạo thay đổi có thể nhận diện, flashback database theo runbook và kiểm tra trạng thái sau OPEN RESETLOGS.

### Bài 13 — RMAN table recovery

Dùng backup/archived redo của schema test để RECOVER TABLE tới SCN trước một thao tác xóa hoặc truncate. Phục hồi ra tên mới và kiểm tra dependency.

### Bài 14 — Lựa chọn phương án

Mô phỏng ba sự cố: DELETE nhầm một số hàng, TRUNCATE nhầm bảng và deployment DDL lỗi. Với mỗi sự cố, nêu mốc, phạm vi, phương án, điều kiện, blast radius và cách xác minh.

## 20. Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Language Reference — SELECT / Flashback Query](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): AS OF SCN/TIMESTAMP và Versions Query.
- [Oracle Database 19c SQL Language Reference — FLASHBACK TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FLASHBACK-TABLE.html): phục hồi bảng về SCN, timestamp hoặc trước DROP.
- [Oracle Database 19c SQL Language Reference — FLASHBACK DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FLASHBACK-DATABASE.html): cú pháp Flashback Database.
- [Oracle Database Backup and Recovery User's Guide 19c — Flashback Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/using-flasback-database.html): cấu hình và vận hành Flashback Database.
- [Oracle Database Backup and Recovery User's Guide 19c — Performing Flashback and Database Point-in-Time Recovery](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/performing-flashback-dbpitr.html): lựa chọn và thực hiện Flashback/PITR.
- [Oracle Database Backup and Recovery User's Guide 19c — Recovering Tables and Table Partitions](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/rman-recovering-tables-partitions.html): RMAN table recovery.
- [Oracle Database Administrator's Guide 19c — Managing Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html): recycle bin và quản lý table.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_FLASHBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK.html): API Flashback và transaction-related operations.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_FLASHBACK_ARCHIVE](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK_ARCHIVE.html): quản lý Flashback Data Archive.
- [Oracle Database Reference — V$RESTORE_POINT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-RESTORE_POINT.html): metadata restore point.
- [Oracle Database Reference — V$FLASHBACK_DATABASE_LOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-FLASHBACK_DATABASE_LOG.html): phạm vi và dung lượng flashback logs.

Cách khắc phục xóa nhầm, cập nhật nhầm hoặc triển khai lỗi phụ thuộc trạng thái COMMIT, loại thao tác, thời điểm và phạm vi dữ liệu cần quay lại. Dùng ROLLBACK cho transaction chưa commit; dùng Flashback Query/Versions để đọc và tái dựng dữ liệu cũ; dùng Flashback Table khi có thể quay cả bảng; dùng Flashback Drop cho object còn trong recycle bin; dùng Flashback Database khi chấp nhận quay toàn database; và dùng RMAN PITR khi cần phục hồi từ backup hoặc phạm vi table/tablespace/database phù hợp. **Chọn phương án có blast radius nhỏ nhất đáp ứng yêu cầu, bảo toàn các thay đổi hợp lệ và xác minh dữ liệu trước khi mở lại ứng dụng.**
