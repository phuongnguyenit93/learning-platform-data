# Phân biệt Flashback Query, Table, Database và backup recovery

Oracle Database cung cấp nhiều cách đưa dữ liệu hoặc database trở lại trạng thái trước một thời điểm. Các cách này có tên gần giống nhau nhưng phạm vi tác động, dữ liệu cần có và mục đích sử dụng rất khác nhau. Chọn sai cơ chế có thể làm mất thêm dữ liệu, kéo dài downtime hoặc khiến việc phục hồi không thể thực hiện được.

Trong nhóm Flashback, ba tính năng thường gặp là **Flashback Query**, **Flashback Table** và **Flashback Database**. Flashback Query đọc phiên bản dữ liệu trong quá khứ; Flashback Table đưa một hoặc nhiều bảng về trạng thái trước đó; Flashback Database đưa toàn bộ database về một SCN hoặc thời điểm cũ. **RMAN backup recovery** lại là quy trình khôi phục các file vật lý từ backup rồi áp dụng redo để phục hồi database.

Điểm cần xác định đầu tiên là phạm vi sự cố: chỉ cần xem lại dữ liệu, cần hoàn tác một bảng, cần quay lui toàn bộ database hay phải phục hồi file bị mất/hỏng. Sau đó mới kiểm tra undo, flashback logs, restore point, backup và archived redo log có sẵn.

## 1. Bốn cơ chế giải quyết bốn nhu cầu khác nhau

| Cơ chế | Phạm vi | Dữ liệu nền tảng | Kết quả |
|---|---|---|---|
| Flashback Query | Một truy vấn trên bảng hoặc đối tượng được hỗ trợ | Undo data còn khả dụng | Đọc dữ liệu như ở SCN/thời điểm cũ; không sửa dữ liệu hiện tại |
| Flashback Table | Một hoặc nhiều bảng | Undo data còn khả dụng và điều kiện Flashback Table được đáp ứng | Thay đổi dữ liệu của bảng để trở về trạng thái cũ |
| Flashback Database | Toàn bộ database | Flashback logs được tạo từ trước sự cố; database được bật Flashback Database | Đưa database về SCN/thời điểm cũ, thường cần mở bằng `RESETLOGS` |
| RMAN backup recovery | Một hoặc nhiều datafile, tablespace hoặc toàn database | Backup phù hợp và redo/archived redo log cần thiết | Khôi phục file vật lý rồi áp dụng redo đến điểm phục hồi |

```text
Sự cố hoặc thao tác nhầm
          |
          v
Bạn cần làm gì?
          |
          +--> Chỉ đọc lại dữ liệu cũ ----------------> Flashback Query
          |
          +--> Hoàn tác dữ liệu của một vài bảng ----> Flashback Table
          |
          +--> Quay lui toàn bộ database ------------> Flashback Database
          |
          +--> Mất/hỏng file hoặc cần restore backup -> RMAN restore/recover
```

Flashback không phải một lệnh duy nhất dùng cho mọi tình huống. Flashback Query và Flashback Table chủ yếu dựa vào undo; Flashback Database dựa vào flashback logs; RMAN recovery dựa vào backup và redo. Một database có thể sử dụng đồng thời các cơ chế này để có nhiều lựa chọn phục hồi.

## 2. Flashback Query: đọc dữ liệu tại một thời điểm trong quá khứ

Flashback Query cho phép truy vấn phiên bản dữ liệu đã tồn tại tại một SCN hoặc timestamp trong quá khứ. Câu lệnh chỉ đọc trạng thái lịch sử; nó không ghi đè dữ liệu hiện tại và không tự động khôi phục bảng.

Ví dụ, người dùng báo rằng một bản ghi khách hàng vừa bị sửa nhầm. Trước khi quyết định cập nhật lại, DBA có thể đọc phiên bản trước khi sửa để xác định giá trị cũ.

### 2.1. Truy vấn theo timestamp

Mệnh đề `AS OF TIMESTAMP` yêu cầu Oracle đọc dữ liệu như ở thời điểm chỉ định:

```sql
SELECT
    employee_id,
    first_name,
    last_name,
    salary
FROM employees AS OF TIMESTAMP
     (SYSTIMESTAMP - INTERVAL '15' MINUTE)
WHERE employee_id = 100;
```

Truy vấn trên đọc phiên bản hàng của nhân viên có mã `100` tại thời điểm xấp xỉ 15 phút trước. Dữ liệu đang lưu trong bảng không bị thay đổi.

### 2.2. Truy vấn theo SCN

SCN (System Change Number) là số thứ tự thay đổi mà Oracle dùng để xác định điểm nhất quán trong database. Nếu đã ghi nhận SCN trước thao tác nhầm, truy vấn theo SCN giúp xác định điểm lịch sử chính xác hơn việc ước lượng timestamp.

```sql
SELECT employee_id, first_name, salary
FROM employees AS OF SCN 123456789
WHERE employee_id = 100;
```

`123456789` chỉ là SCN minh họa. Trong thực tế, cần dùng SCN hợp lệ được ghi nhận từ log, audit, ứng dụng hoặc công cụ vận hành.

### 2.3. So sánh dữ liệu hiện tại với dữ liệu cũ

Có thể truy vấn cùng một bảng ở hai phiên bản bằng cách dùng alias:

```sql
SELECT
    current_row.employee_id,
    current_row.salary AS current_salary,
    old_row.salary AS salary_15_minutes_ago
FROM employees current_row
JOIN employees AS OF TIMESTAMP
     (SYSTIMESTAMP - INTERVAL '15' MINUTE) old_row
  ON old_row.employee_id = current_row.employee_id
WHERE current_row.employee_id = 100;
```

Truy vấn này hữu ích khi cần xác định cột nào đã thay đổi. Với nhiều bảng liên quan, có thể áp dụng cùng điểm SCN hoặc timestamp cho các bảng để so sánh một trạng thái dữ liệu nhất quán, miễn các đối tượng hỗ trợ Flashback Query và undo còn đủ.

### 2.4. Xem các phiên bản hàng bằng Flashback Versions Query

Flashback Versions Query cho phép xem các phiên bản hàng xuất hiện trong một khoảng SCN hoặc timestamp. Nó phù hợp khi cần điều tra một bản ghi đã được insert, update hoặc delete như thế nào.

```sql
SELECT
    versions_startscn,
    versions_endscn,
    versions_operation,
    versions_xid,
    employee_id,
    salary
FROM employees
     VERSIONS BETWEEN SCN 123450000 AND 123456789
WHERE employee_id = 100
ORDER BY versions_startscn;
```

Các pseudo-column thường dùng:

- `VERSIONS_STARTSCN`: SCN bắt đầu phiên bản hàng.
- `VERSIONS_ENDSCN`: SCN kết thúc phiên bản hàng; giá trị `NULL` thường thể hiện phiên bản hiện tại trong khoảng được xét.
- `VERSIONS_OPERATION`: thao tác tạo phiên bản, thường biểu diễn insert, update hoặc delete bằng ký hiệu tương ứng.
- `VERSIONS_XID`: transaction ID đã tạo ra phiên bản.

Phiên bản hàng và khoảng SCN mà Oracle có thể trả về phụ thuộc undo còn tồn tại. Một thao tác DDL thay đổi cấu trúc bảng có thể làm truy vấn phiên bản lịch sử không còn thực hiện được qua ranh giới thay đổi đó.

### 2.5. Điều tra transaction

Khi cần tìm transaction đã thay đổi dữ liệu, có thể kết hợp `VERSIONS_XID` với `FLASHBACK_TRANSACTION_QUERY`:

```sql
SELECT
    xid,
    start_scn,
    commit_scn,
    operation,
    table_name,
    undo_sql,
    logon_user
FROM flashback_transaction_query
WHERE xid = HEXTORAW('00000A0000120000');
```

XID trong ví dụ là giá trị minh họa, lấy từ `VERSIONS_XID` hoặc công cụ điều tra. Khả năng lấy đầy đủ SQL redo/undo phụ thuộc supplemental logging và metadata undo còn khả dụng. Quyền truy cập view này thường cần DBA cấp riêng.

### 2.6. Điều kiện và giới hạn của Flashback Query

Flashback Query cần undo data đủ để tái dựng phiên bản cũ. `UNDO_RETENTION` là mục tiêu thời gian lưu undo, nhưng trong điều kiện thiếu dung lượng, Oracle có thể phải tái sử dụng undo chưa hết thời gian mục tiêu nếu undo tablespace không được cấu hình retention guarantee.

Kiểm tra cấu hình undo:

```sql
SHOW PARAMETER undo_retention;
SHOW PARAMETER undo_tablespace;

SELECT
    begin_time,
    end_time,
    tuned_undoretention,
    ssolderrcnt,
    nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC;
```

`TUNED_UNDORETENTION` cho biết thời gian giữ undo được Oracle điều chỉnh theo hoạt động thực tế. `SSOLDERRCNT` và `NOSPACEERRCNT` giúp theo dõi một số vấn đề liên quan đến snapshot và không gian undo. Cần xem nhiều khoảng thời gian và dung lượng tablespace trước khi kết luận một mốc lịch sử còn truy vấn được.

Các lỗi thường gặp:

- `ORA-01555: snapshot too old`: undo cần thiết đã không còn khả dụng để tái dựng phiên bản nhất quán.
- `ORA-08180: no snapshot found based on specified time`: Oracle không tìm được SCN tương ứng hoặc thông tin cần thiết cho thời điểm yêu cầu.
- `ORA-01466: unable to read data - table definition has changed`: cấu trúc đối tượng đã thay đổi theo cách khiến truy vấn lịch sử không thể thực hiện qua mốc đó.

Flashback Query thích hợp để xem, so sánh và điều tra dữ liệu. Nếu muốn thay đổi dữ liệu hiện tại để quay lại trạng thái cũ, cần đánh giá Flashback Table hoặc một phương án phục hồi khác.

## 3. Flashback Table: đưa một hoặc nhiều bảng về trạng thái cũ

Flashback Table dùng undo để đưa dữ liệu của bảng về một SCN hoặc timestamp trước đó. Khác với Flashback Query, thao tác này thay đổi dữ liệu hiện tại của bảng. Nó phù hợp khi một bảng bị cập nhật hoặc xóa nhầm nhưng các phần còn lại của database vẫn đúng.

Ví dụ, một job lỗi đã cập nhật sai cột trạng thái của bảng `ORDERS`. Nếu undo còn đủ và bảng không có thay đổi cấu trúc cản trở việc flashback, DBA có thể đưa bảng về trước thời điểm job chạy.

### 3.1. Bật row movement

Trước khi flashback table, cần bật row movement cho bảng:

```sql
ALTER TABLE orders ENABLE ROW MOVEMENT;
```

Oracle có thể cần thay đổi ROWID khi đưa hàng về trạng thái cũ. Row movement cho phép hàng được di chuyển trong quá trình này. Cấu hình row movement là thuộc tính của bảng; hãy kiểm tra chính sách và tác động ứng dụng trước khi thay đổi.

### 3.2. Flashback theo timestamp hoặc SCN

```sql
FLASHBACK TABLE orders TO TIMESTAMP
    (SYSTIMESTAMP - INTERVAL '20' MINUTE);
```

Hoặc dùng SCN:

```sql
FLASHBACK TABLE orders TO SCN 123456789;
```

Sau thao tác, dữ liệu của bảng `ORDERS` được đưa về trạng thái ở thời điểm đã chọn. Các thay đổi sau thời điểm đó trên bảng có thể bị loại bỏ khỏi trạng thái hiện tại. Vì vậy, cần xác định đúng thời điểm và cân nhắc xuất dữ liệu hiện tại ra một bảng staging hoặc backup trước khi thực hiện nếu cần giữ lại các thay đổi hợp lệ phát sinh sau mốc đó.

### 3.3. Flashback nhiều bảng cùng một điểm

Nếu các bảng có quan hệ khóa ngoại hoặc cần giữ tính nhất quán nghiệp vụ, nên flashback chúng cùng một câu lệnh và cùng SCN/timestamp:

```sql
ALTER TABLE orders ENABLE ROW MOVEMENT;
ALTER TABLE order_items ENABLE ROW MOVEMENT;

FLASHBACK TABLE orders, order_items
    TO SCN 123456789;
```

Ví dụ trên giả định cả hai bảng đủ điều kiện flashback và SCN vẫn nằm trong phạm vi undo có thể sử dụng. Nếu chỉ flashback bảng cha mà không xử lý bảng con, có thể gặp vấn đề toàn vẹn tham chiếu hoặc dữ liệu không nhất quán theo nghiệp vụ. Cần đánh giá các quan hệ liên quan và thực hiện trong cửa sổ bảo trì phù hợp.

### 3.4. Trigger trong Flashback Table

Trong quá trình Flashback Table, trigger có thể được bật hoặc không theo tùy chọn của lệnh. Nếu cần trigger chạy cho các thay đổi được thực hiện trong quá trình flashback, có thể chỉ định `ENABLE TRIGGERS`:

```sql
FLASHBACK TABLE orders
    TO SCN 123456789
    ENABLE TRIGGERS;
```

Nếu không chỉ định, trigger trên bảng bị vô hiệu hóa trong quá trình thao tác flashback theo hành vi mặc định của tính năng. Hãy cân nhắc kỹ vì trigger có thể tạo side effect như ghi audit, cập nhật bảng khác hoặc phát sinh tác vụ phụ. Không nên bật trigger mà chưa đánh giá ảnh hưởng của các thay đổi được tái tạo.

### 3.5. Điều kiện và giới hạn

Flashback Table có một số yêu cầu cần kiểm tra trước:

- Undo cần thiết cho thời điểm đích vẫn còn khả dụng.
- Người thực hiện có quyền phù hợp trên bảng.
- Row movement đã được bật.
- Bảng và các đối tượng liên quan thuộc loại được hỗ trợ.
- Không có thay đổi cấu trúc như `TRUNCATE` hoặc một số DDL làm mất khả năng flashback về mốc yêu cầu.
- Quan hệ khóa ngoại, trigger, index, materialized view và logic nghiệp vụ được đánh giá trước khi thực hiện.

Flashback Table khôi phục dữ liệu hàng trong bảng, không phải công cụ khôi phục mọi thay đổi cấu trúc database. Nếu bảng đã bị `DROP`, tình huống đó thường cần xem xét Flashback Drop (`FLASHBACK TABLE ... TO BEFORE DROP`) và recycle bin; đây là tính năng khác với Flashback Table về timestamp/SCN. Nếu file dữ liệu bị mất hoặc hỏng, Flashback Table cũng không thay thế RMAN media recovery.

### 3.6. Kiểm tra sau khi flashback

Sau thao tác, cần xác nhận số lượng và nội dung hàng, ràng buộc và trạng thái ứng dụng:

```sql
SELECT COUNT(*) FROM orders;

SELECT order_status, COUNT(*)
FROM orders
GROUP BY order_status
ORDER BY order_status;
```

Đây chỉ là truy vấn minh họa. Hãy kiểm tra bằng khóa nghiệp vụ, đối chiếu bảng con, audit trail và các chỉ số mà ứng dụng sử dụng. Nếu cần phục hồi lại các thay đổi hợp lệ bị loại bỏ, phải có nguồn dữ liệu riêng để đối chiếu và áp dụng lại có kiểm soát.

## 4. Flashback Database: quay lui toàn bộ database

Flashback Database đưa toàn bộ database về một SCN, timestamp hoặc restore point trước đó. Nó hoạt động ở mức block: Oracle sử dụng flashback logs để tái dựng phiên bản block cũ, kết hợp redo cần thiết để đưa database về điểm đích.

Đây là lựa chọn hữu ích khi một thao tác nhầm ảnh hưởng rộng, ví dụ job cập nhật sai nhiều schema hoặc triển khai ứng dụng gây thay đổi dữ liệu trên nhiều bảng. Thay vì flashback từng bảng, DBA có thể đưa cả database về trạng thái trước sự kiện.

Flashback Database phải được bật trước khi sự cố xảy ra và cần có flashback logs phù hợp. Không thể bật tính năng sau sự cố rồi yêu cầu Oracle tái dựng các block trong quá khứ nếu log tương ứng chưa được tạo.

### 4.1. Điều kiện cần có

Các điều kiện vận hành quan trọng gồm:

1. Database chạy ở chế độ `ARCHIVELOG`.
2. Flashback Database được bật trước thời điểm cần quay lui.
3. Fast Recovery Area (FRA) được cấu hình và còn đủ dung lượng cho flashback logs cùng các file recovery liên quan.
4. Flashback logs bao phủ SCN/thời điểm đích.
5. Datafile và các thành phần cần thiết vẫn có thể truy cập; Flashback Database không phải phương án thay thế cho việc restore file vật lý bị mất hoặc hỏng.

Kiểm tra trạng thái:

```sql
SELECT
    name,
    log_mode,
    flashback_on,
    open_mode
FROM v$database;

SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
SHOW PARAMETER db_flashback_retention_target;
```

`FLASHBACK_ON` cho biết Flashback Database có đang bật hay không. `DB_FLASHBACK_RETENTION_TARGET` là mục tiêu thời gian giữ flashback logs; nó không bảo đảm Oracle luôn giữ đủ log trong mọi điều kiện dung lượng. FRA có thể phải tái sử dụng hoặc xóa file theo chính sách quản lý khi không gian bị áp lực, trừ các log được giữ bởi cơ chế bảo đảm phù hợp.

### 4.2. Bật Flashback Database

Ví dụ quy trình khi database đã ở `ARCHIVELOG` và FRA đã được cấu hình:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE FLASHBACK ON;
ALTER DATABASE OPEN;
```

Nếu database chưa ở `ARCHIVELOG`, DBA cần thực hiện quy trình chuyển chế độ log trong trạng thái mount theo kế hoạch bảo trì và kiểm tra backup phù hợp. Cấu hình FRA và dung lượng phải được hoàn thành trước khi bật Flashback Database trong production.

Có thể kiểm tra thông tin flashback log:

```sql
SELECT
    oldest_flashback_scn,
    oldest_flashback_time,
    retention_target,
    flashback_size,
    estimated_flashback_size
FROM v$flashback_database_log;
```

`OLDEST_FLASHBACK_SCN` và `OLDEST_FLASHBACK_TIME` cho biết mốc cũ nhất mà thông tin flashback hiện có thể hỗ trợ theo trạng thái log. Đây là dữ liệu quan trọng để biết một sự cố cách đây bao lâu còn có thể xử lý bằng Flashback Database.

### 4.3. Flashback theo SCN hoặc timestamp

Khi đã xác định điểm đích, đưa database về trạng thái mount rồi thực hiện flashback:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;

FLASHBACK DATABASE TO SCN 123456789;

ALTER DATABASE OPEN RESETLOGS;
```

Hoặc dùng timestamp:

```sql
FLASHBACK DATABASE TO TIMESTAMP
    (TO_TIMESTAMP('2026-11-14 09:30:00', 'YYYY-MM-DD HH24:MI:SS'));
```

Các mốc SCN và thời gian trong ví dụ chỉ để minh họa. Trước khi chạy, cần xác định chính xác thời điểm sự cố bắt đầu, thời điểm dữ liệu bị tác động và điểm gần nhất mà database còn nhất quán. Chọn mốc quá muộn có thể giữ lại thay đổi sai; chọn mốc quá sớm có thể loại bỏ thêm giao dịch hợp lệ.

Sau Flashback Database, database thường được mở bằng `RESETLOGS`, tạo một database incarnation mới. Điều này ảnh hưởng chuỗi backup và quy trình RMAN tiếp theo. Cần thực hiện backup mới và kiểm tra trạng thái RMAN theo quy trình vận hành sau khi mở database.

### 4.4. Restore point và guaranteed restore point

Restore point là tên định danh cho một SCN để dễ quay lại một mốc cụ thể, ví dụ trước khi triển khai phiên bản mới:

```sql
CREATE RESTORE POINT before_release_2026_11;
```

Restore point thông thường chỉ đánh dấu SCN. Nó không tự bảo đảm flashback logs cần thiết sẽ luôn được giữ.

Guaranteed restore point yêu cầu Oracle giữ flashback logs cần thiết để có thể flashback về mốc đó, miễn là database và FRA có thể tiếp tục vận hành. Tạo bằng:

```sql
CREATE RESTORE POINT before_release_2026_11
    GUARANTEE FLASHBACK DATABASE;
```

Flashback về restore point:

```sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
FLASHBACK DATABASE TO RESTORE POINT before_release_2026_11;
ALTER DATABASE OPEN RESETLOGS;
```

Kiểm tra restore point:

```sql
SELECT
    name,
    scn,
    time,
    guarantee_flashback_database,
    storage_size
FROM v$restore_point
ORDER BY time DESC;
```

Guaranteed restore point có thể giữ lại nhiều flashback logs và làm FRA tăng nhanh. Nếu FRA hết chỗ, database có thể không tiếp tục tạo các file recovery cần thiết và hoạt động có thể bị ảnh hưởng. Vì vậy cần theo dõi dung lượng, thời gian tồn tại của restore point và xóa restore point sau khi không còn cần:

```sql
DROP RESTORE POINT before_release_2026_11;
```

Không tạo guaranteed restore point rồi quên dọn. Đây là công cụ hữu ích trước thay đổi lớn, nhưng phải đi kèm kế hoạch dung lượng và thời điểm giải phóng.

### 4.5. Flashback Database không phải RMAN restore

Flashback Database sử dụng flashback logs để tái dựng các block cũ trong database hiện có. Nó không lấy datafile từ backup piece và không thể tự sửa một datafile đã mất hoàn toàn hoặc thiết bị lưu trữ bị hỏng. Nếu media failure làm file không còn truy cập được, cần RMAN restore/recover hoặc một phương án khôi phục file tương đương.

Flashback Database cũng không phải bản sao lưu độc lập. Nếu cùng một storage chứa datafile và flashback logs bị mất, cả hai có thể cùng mất. Vì vậy vẫn cần backup RMAN được lưu ở miền lỗi độc lập.

## 5. RMAN backup recovery: restore file và áp dụng redo

RMAN backup recovery là phương án khôi phục dựa trên backup vật lý. RMAN có thể restore datafile, control file, SPFILE hoặc các thành phần backup khác từ backup piece/image copy, sau đó áp dụng incremental backup và redo/archived redo log để đưa file đến trạng thái nhất quán.

Đây là phương án cần thiết khi:

- Datafile hoặc tablespace bị mất, hỏng hoặc storage không còn truy cập được.
- Control file hoặc SPFILE bị mất và cần khôi phục từ backup.
- Flashback Database chưa được bật hoặc flashback logs không bao phủ điểm cần quay lui.
- Cần khôi phục về một điểm lịch sử dài hơn thời gian undo hoặc flashback logs còn giữ.
- Cần khôi phục database sang máy chủ hoặc môi trường khác.

### 5.1. Phân biệt RESTORE và RECOVER

- `RESTORE` lấy file vật lý từ backup và ghi chúng về vị trí đích. File được restore thường phản ánh trạng thái tại thời điểm backup.
- `RECOVER` áp dụng incremental backup và/hoặc redo cần thiết lên các file đã restore để đưa chúng tiến đến điểm phục hồi.

Ví dụ, một datafile được backup lúc 02:00. Nếu database có archived redo log liên tục từ sau 02:00 đến thời điểm cần phục hồi, RMAN có thể restore datafile từ backup 02:00 rồi apply redo để đưa file tiến tới thời điểm mới hơn.

```text
Backup datafile (02:00)
        |
        v
RESTORE datafile
        |
        v
RECOVER: incremental backup + archived redo + redo cần thiết
        |
        v
Datafile được phục hồi tới điểm đích
```

### 5.2. Complete recovery và incomplete recovery

**Complete recovery** áp dụng toàn bộ redo cần thiết để đưa database hoặc file tới trạng thái mới nhất có thể phục hồi, thường là thời điểm hiện tại hoặc thời điểm sự cố được khắc phục. Với complete media recovery, database có thể được mở theo quy trình phù hợp mà không nhất thiết phải `RESETLOGS`.

**Incomplete recovery** dừng ở một SCN, timestamp hoặc log sequence trước hiện tại. Đây là cách point-in-time recovery (PITR) khi cần loại bỏ các giao dịch sau điểm đích. Sau incomplete recovery toàn database, thường phải mở bằng `RESETLOGS`, tạo incarnation mới.

### 5.3. Ví dụ point-in-time recovery toàn database

Ví dụ dưới đây minh họa database cần quay về một SCN trước khi một batch job làm sai dữ liệu. Database đã có RMAN backup phù hợp và archived redo log cần thiết.

```rman
STARTUP MOUNT;

RUN {
    SET UNTIL SCN 123456789;
    RESTORE DATABASE;
    RECOVER DATABASE;
}

ALTER DATABASE OPEN RESETLOGS;
```

SCN chỉ là ví dụ. DBA phải xác minh backup, archived redo log, DBID, incarnation, control file và điểm đích trước khi thực hiện. Với database đang mở hoặc trạng thái khác, cần tuân theo quy trình shutdown/mount và khôi phục đúng với tình huống thực tế.

RMAN cũng hỗ trợ đặt điểm đích theo thời gian:

```rman
RUN {
    SET UNTIL TIME "TO_DATE('2026-11-14 09:30:00', 'YYYY-MM-DD HH24:MI:SS')";
    RESTORE DATABASE;
    RECOVER DATABASE;
}
```

Điểm thời gian cần được xác định theo time zone và đồng hồ của hệ thống. Nếu có thể, dùng SCN đã được ghi nhận rõ ràng để tránh nhầm lẫn về múi giờ hoặc độ chính xác timestamp.

### 5.4. Phục hồi một datafile bị mất

Nếu chỉ một datafile bị mất nhưng database còn hoạt động và có backup cùng redo cần thiết, có thể restore/recover riêng datafile thay vì đưa toàn database về quá khứ:

```rman
RESTORE DATAFILE 7;
RECOVER DATAFILE 7;
```

Ví dụ sử dụng file number `7`; cần thay bằng file number thật. Tùy trạng thái database, tablespace và chế độ hoạt động, DBA có thể cần đưa datafile/tablespace offline trước khi restore và online sau khi recover. Phải xác minh kiến trúc và trạng thái file trước khi chạy lệnh.

### 5.5. Điều kiện và giới hạn của backup recovery

Khả năng recovery phụ thuộc vào:

- Backup datafile/control file/SPFILE còn tồn tại, đọc được và thuộc đúng database/incarnation.
- Archived redo log và redo cần thiết còn đủ, không bị thiếu đoạn trong chuỗi.
- Backup piece có thể truy cập từ host hoặc thiết bị lưu trữ dùng trong quá trình phục hồi.
- Có thông tin DBID, cấu trúc database, đường dẫn file và cấu hình cần thiết.
- Có đủ dung lượng đích và quyền truy cập để restore file.

Nếu thiếu archived redo log ở giữa chuỗi, RMAN có thể không recover được tới điểm mong muốn. Khi đó phải chọn một điểm phục hồi sớm hơn mà backup và redo còn đủ, hoặc tìm bản sao log từ nguồn khác.

RMAN recovery có thể mất nhiều thời gian vì phải restore dữ liệu từ thiết bị backup rồi apply redo. RTO phụ thuộc dung lượng database, tốc độ storage/network, parallelism, số lượng log và tài nguyên máy chủ. Cần diễn tập để có số liệu thực tế.

## 6. So sánh sâu hơn: chọn công cụ theo tình huống

| Tình huống | Cơ chế thường phù hợp | Lý do |
|---|---|---|
| Cần xem giá trị một hàng trước khi bị sửa | Flashback Query | Chỉ đọc phiên bản cũ, không làm thay đổi bảng hiện tại |
| Cần điều tra các phiên bản của một hàng | Flashback Versions Query | Hiển thị lịch sử phiên bản trong khoảng SCN/time còn undo |
| Một bảng bị update/delete nhầm, cấu trúc không đổi | Flashback Table | Khôi phục dữ liệu của bảng bằng undo |
| Nhiều bảng trong một giao dịch bị tác động và cần quay lại cùng điểm | Flashback Table cho nhóm bảng, hoặc Flashback Database tùy phạm vi | Cần bảo toàn quan hệ giữa các bảng; đánh giá ảnh hưởng toàn hệ thống |
| Nhiều schema hoặc toàn database bị thao tác nhầm | Flashback Database nếu đã bật và còn log | Quay lui toàn bộ database đến một điểm trước sự cố |
| Datafile bị xóa hoặc storage hỏng | RMAN restore/recover | Cần khôi phục file vật lý từ backup |
| Flashback Database chưa bật, nhưng có backup và archived redo | RMAN point-in-time recovery | Dùng backup và redo để dựng lại database tới điểm đích |
| Cần phục hồi database trên host mới | RMAN restore/recover | Khôi phục file vào môi trường đích và áp dụng redo |

Không phải lúc nào Flashback Database cũng là lựa chọn nhanh nhất. Nếu chỉ một bảng bị ảnh hưởng và undo còn đủ, Flashback Table có phạm vi tác động nhỏ hơn. Ngược lại, nếu hàng trăm bảng bị tác động và cần trạng thái nhất quán toàn database, flashback từng bảng có thể phức tạp và dễ bỏ sót quan hệ; Flashback Database hoặc RMAN PITR có thể phù hợp hơn.

## 7. Kết hợp Flashback với RMAN trong chiến lược phục hồi

Flashback và RMAN bổ sung cho nhau. RMAN cung cấp nền tảng backup để phục hồi khi file bị mất hoặc khi cần quay về thời điểm nằm ngoài khoảng flashback. Flashback Query và Flashback Table giúp điều tra hoặc xử lý nhanh lỗi logic nhỏ. Flashback Database có thể giảm thời gian quay lui toàn database nếu flashback logs còn sẵn.

Một chiến lược có thể gồm:

1. Chạy RMAN backup database và archived redo log theo RPO/RTO.
2. Bảo vệ control file và SPFILE bằng autobackup.
3. Bật Flashback Database nếu workload và dung lượng FRA cho phép.
4. Tăng cường giám sát undo để Flashback Query/Table có cơ hội đáp ứng thời gian cần thiết.
5. Tạo guaranteed restore point trước thay đổi lớn khi có đủ FRA và kế hoạch dọn restore point.
6. Kiểm tra backup bằng `CROSSCHECK`, `RESTORE ... VALIDATE` hoặc các bài kiểm thử restore phù hợp.
7. Diễn tập cả logical recovery và media recovery, ghi nhận thời gian và điểm dữ liệu phục hồi.

Ví dụ, trước một đợt triển khai schema lớn, nhóm vận hành có thể tạo guaranteed restore point. Nếu triển khai gây thay đổi dữ liệu sai trên nhiều bảng, DBA đánh giá Flashback Database để quay về trước triển khai. Nếu sự cố làm hỏng storage hoặc mất datafile, RMAN restore/recover vẫn là cơ chế chính. Sau một sự cố nhỏ ở một bảng, Flashback Query giúp xác định dữ liệu đúng và Flashback Table có thể khôi phục bảng nếu các điều kiện undo được đáp ứng.

## 8. Các lỗi và hiểu nhầm thường gặp

### 8.1. Nghĩ rằng UNDO_RETENTION bảo đảm truy vấn được mọi dữ liệu trong khoảng đó

`UNDO_RETENTION` là mục tiêu giữ undo. Nếu undo tablespace thiếu chỗ và không bật retention guarantee, Oracle có thể ghi đè undo chưa hết thời gian mục tiêu. Hãy theo dõi `V$UNDOSTAT`, kích thước undo tablespace, workload và lỗi `ORA-01555`.

### 8.2. Nghĩ rằng có thể bật Flashback Database sau khi sự cố xảy ra

Flashback Database chỉ có thể quay về khoảng thời gian mà flashback logs đã được tạo và còn tồn tại. Bật tính năng sau sự cố không tạo lại các block image trong quá khứ. Khi không có flashback logs phù hợp, phải đánh giá RMAN backup recovery.

### 8.3. Nhầm Flashback Table với Flashback Drop

`FLASHBACK TABLE table_name TO TIMESTAMP ...` đưa dữ liệu bảng về trạng thái cũ bằng undo. `FLASHBACK TABLE table_name TO BEFORE DROP` khôi phục bảng đã drop từ recycle bin nếu đối tượng còn ở đó và tính năng áp dụng. Đây là hai đường xử lý khác nhau.

### 8.4. Nhầm Flashback Database với restore database

Flashback Database tái dựng block từ flashback logs trong database đã có. RMAN restore lấy file từ backup. Flashback Database không sửa được file vật lý đã mất; RMAN restore không cần flashback logs nhưng cần backup và redo.

### 8.5. Chọn sai điểm đích

Chọn timestamp chỉ dựa trên giờ người dùng báo có thể không chính xác do time zone, độ trễ ghi nhận và giao dịch kéo dài. Hãy xác định SCN hoặc timestamp bằng audit, log ứng dụng, transaction history và kiểm tra dữ liệu. Trước khi quay lui toàn database, cần tính rõ những giao dịch hợp lệ sẽ bị loại bỏ.

### 8.6. Không tạo backup sau OPEN RESETLOGS

Sau incomplete recovery hoặc Flashback Database, `OPEN RESETLOGS` tạo incarnation mới. Cần kiểm tra incarnation bằng RMAN, đánh giá backup cũ có còn phù hợp với chiến lược mới hay không và tạo backup mới sau khi database đã ổn định.

## 9. Quy trình ra quyết định khi có sự cố dữ liệu

Khi phát hiện thao tác nhầm, nên làm theo thứ tự có kiểm soát:

1. **Dừng tác nhân gây lỗi**: tạm dừng job, batch hoặc ứng dụng đang tiếp tục ghi dữ liệu sai.
2. **Ghi nhận thời điểm và phạm vi**: xác định bảng/schema/database bị ảnh hưởng, transaction, SCN/timestamp và các giao dịch hợp lệ sau đó.
3. **Bảo toàn bằng chứng**: lưu log ứng dụng, audit, transaction ID và bản chụp dữ liệu hiện tại nếu cần điều tra.
4. **Đánh giá undo**: kiểm tra Flashback Query/Versions Query có đọc được dữ liệu trước sự cố không.
5. **Chọn phạm vi khôi phục**: truy vấn lịch sử, flashback một vài bảng, flashback toàn database hay RMAN restore/recover.
6. **Kiểm tra điều kiện kỹ thuật**: row movement, flashback logging, restore point, FRA, backup và archived redo log.
7. **Thử trong môi trường phù hợp**: nếu tác động lớn, diễn tập trên clone/standby hoặc môi trường khôi phục trước khi thay đổi production.
8. **Thực hiện và xác minh**: kiểm tra tính toàn vẹn dữ liệu, ràng buộc, số liệu nghiệp vụ và khả năng hoạt động của ứng dụng.
9. **Tạo điểm bảo vệ mới**: backup sau phục hồi và cập nhật tài liệu vận hành.

Không nên chạy lệnh flashback hoặc RMAN PITR chỉ dựa trên một timestamp ước lượng. Quay lui toàn database có thể loại bỏ các giao dịch hợp lệ của mọi ứng dụng dùng chung database.

## 10. Ví dụ tổng hợp

Giả sử hệ thống quản lý đơn hàng gặp ba sự cố khác nhau:

**Tình huống A — Một bản ghi bị sửa nhầm:** người vận hành cập nhật sai địa chỉ của một khách hàng. Có thể dùng Flashback Query để xem địa chỉ cũ:

```sql
SELECT customer_id, address
FROM customers AS OF TIMESTAMP
     (SYSTIMESTAMP - INTERVAL '10' MINUTE)
WHERE customer_id = 5001;
```

Sau khi xác nhận dữ liệu đúng, nhóm ứng dụng có thể tạo một lệnh `UPDATE` có kiểm soát để sửa lại đúng hàng. Truy vấn lịch sử không tự thay đổi bảng.

**Tình huống B — Một job cập nhật sai toàn bộ bảng trạng thái:** nếu chỉ bảng `ORDERS` bị ảnh hưởng, cấu trúc bảng không đổi và undo còn đủ, DBA có thể bật row movement rồi flashback bảng về SCN trước job. Cần đánh giá bảng con, giao dịch hợp lệ sau mốc đó và trigger trước khi thực hiện.

**Tình huống C — Một đợt triển khai làm sai dữ liệu trên nhiều schema:** nếu Flashback Database đã được bật và flashback logs bao phủ thời điểm trước triển khai, DBA có thể đưa toàn database về restore point trước release. Nếu không có flashback logs nhưng RMAN backup và archived redo log đầy đủ, DBA có thể thực hiện point-in-time recovery. Cả hai cách đều ảnh hưởng toàn database và cần xác định giao dịch nào sẽ bị mất.

Nếu storage bị lỗi làm mất datafile, Flashback Query/Table/Database không thể thay thế việc restore file. RMAN phải khôi phục datafile từ backup và apply redo theo khả năng còn lại.

## 11. Kiểm tra và diễn tập định kỳ

Một chiến lược phục hồi chỉ đáng tin cậy khi có số liệu và kết quả diễn tập. Các kiểm tra nên được đưa vào lịch vận hành:

| Thành phần | Kiểm tra | Mục tiêu |
|---|---|---|
| Undo | `UNDO_RETENTION`, `V$UNDOSTAT`, dung lượng tablespace | Biết khả năng truy vấn/flashback dữ liệu lịch sử |
| Flashback Database | `V$DATABASE.FLASHBACK_ON`, `V$FLASHBACK_DATABASE_LOG` | Biết tính năng có bật và khoảng SCN/time còn khả dụng |
| FRA | Dung lượng sử dụng, file recovery, guaranteed restore point | Tránh hết chỗ và mất khả năng duy trì flashback logs |
| Restore point | `V$RESTORE_POINT`, tuổi và storage size | Quản lý mốc rollback trước thay đổi lớn |
| RMAN | `LIST BACKUP`, `CROSSCHECK`, `RESTORE ... VALIDATE` | Xác minh metadata và khả năng đọc backup |
| Archived redo | Log sequence và tính liên tục của chuỗi log | Xác định khả năng recover tới điểm mong muốn |
| Diễn tập | Flashback Query/Table, Flashback Database và RMAN restore/recover trên môi trường phù hợp | Đo RTO, RPO và phát hiện thiếu sót quy trình |

Các câu lệnh `CROSSCHECK` và `RESTORE ... VALIDATE` giúp phát hiện một số vấn đề về khả năng truy cập backup, nhưng không thay thế một bài diễn tập mở database và xác nhận dữ liệu nghiệp vụ. Nên kiểm thử nhiều tình huống: mất một datafile, mất control file, thao tác DML nhầm, triển khai lỗi và mất catalog/flashback logs.

## 12. Những điểm cần nhớ

- **Flashback Query** đọc dữ liệu ở SCN/timestamp cũ bằng undo; không thay đổi dữ liệu hiện tại.
- **Flashback Versions Query** giúp xem lịch sử phiên bản hàng trong khoảng undo còn khả dụng.
- **Flashback Table** thay đổi dữ liệu của một hoặc nhiều bảng để đưa chúng về trạng thái cũ; cần row movement và undo phù hợp.
- **Flashback Database** quay lui toàn database bằng flashback logs; phải bật trước sự cố và cần đủ FRA/logs.
- **RMAN restore/recover** khôi phục file vật lý từ backup rồi áp dụng incremental/redo; cần backup và chuỗi redo phù hợp.
- `UNDO_RETENTION` là mục tiêu, không mặc nhiên là cam kết giữ undo trong mọi điều kiện.
- `DB_FLASHBACK_RETENTION_TARGET` cũng là mục tiêu; guaranteed restore point giữ log cần thiết nhưng có thể tiêu thụ nhiều FRA.
- Flashback không thay thế backup; RMAN backup vẫn cần thiết cho media failure và disaster recovery.
- Sau point-in-time recovery hoặc Flashback Database, cần xử lý incarnation và backup mới theo quy trình.
- Luôn xác định đúng phạm vi, điểm đích và giao dịch hợp lệ sẽ bị ảnh hưởng trước khi thực hiện phục hồi.

Flashback và RMAN là các lớp bảo vệ bổ sung cho nhau. Hiểu đúng dữ liệu nền tảng của từng cơ chế — undo, flashback logs hay backup cùng redo — giúp chọn phạm vi phục hồi phù hợp, giảm downtime và tránh làm mất thêm dữ liệu hợp lệ.
