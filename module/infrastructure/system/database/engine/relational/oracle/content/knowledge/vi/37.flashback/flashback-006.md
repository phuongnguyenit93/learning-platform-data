# Recycle bin, FLASHBACK DROP và hành vi PURGE trong Oracle

## 1. Recycle bin là gì?

Oracle Database có **recycle bin** để giữ lại một số table đã bị DROP, giúp người dùng có cơ hội khôi phục table bằng Flashback Drop mà không phải restore toàn bộ database từ backup.

Khi một table đủ điều kiện bị DROP và recycle bin đang bật, Oracle đổi tên object thành một tên hệ thống dạng BIN$..., đồng thời giữ lại metadata và các dependent object liên quan. Table không còn xuất hiện dưới tên cũ trong schema, nên người dùng có thể tạo một table mới trùng tên. Dữ liệu của table cũ vẫn chiếm dung lượng trong tablespace cho đến khi được purge hoặc bị Oracle tự động purge khi cần không gian.

Các khái niệm chính:

- **Recycle bin:** nơi lưu các table đã DROP đủ điều kiện và các dependent object của chúng.
- **Flashback Drop:** khả năng khôi phục table từ recycle bin bằng câu lệnh FLASHBACK TABLE ... TO BEFORE DROP.
- **PURGE:** xóa vĩnh viễn object khỏi recycle bin, không thể dùng Flashback Drop để khôi phục lại.

Recycle bin là một tiện ích phục hồi nhanh cho thao tác DROP nhầm. Nó không phải backup, không bảo vệ khỏi mất storage/database và không thay thế RMAN, Data Guard hoặc bản backup độc lập.

## 2. Vòng đời của một table sau DROP

Khi thực hiện DROP TABLE thông thường, Oracle kiểm tra recycle bin và các điều kiện áp dụng. Nếu table đủ điều kiện và recycle bin bật, object được chuyển vào recycle bin thay vì bị xóa vật lý ngay lập tức.

~~~text
Table đang hoạt động
        |
        | DROP TABLE table_name
        v
Oracle kiểm tra recycle bin và điều kiện hỗ trợ
        |
        +---- Recycle bin bật, object đủ điều kiện
        |                |
        |                v
        |        Đổi tên thành BIN$...
        |                |
        |                v
        |        Có thể FLASHBACK DROP
        |                |
        |        +-------+--------+
        |        |                |
        |        v                v
        |    Khôi phục          PURGE
        |        |                |
        |        v                v
        |    Table hoạt động   Xóa vĩnh viễn
        |
        +---- PURGE / recycle bin OFF / object không hỗ trợ
                         |
                         v
                   Xóa khỏi recycle bin
~~~

Có ba trạng thái cần phân biệt:

1. **Table đang hoạt động:** object có tên thông thường trong schema.
2. **Table trong recycle bin:** object đã DROP nhưng còn có thể khôi phục nếu chưa bị purge và vẫn đáp ứng điều kiện.
3. **Table đã purge:** object đã bị xóa khỏi recycle bin; Flashback Drop không thể khôi phục.

### 2.1. DROP không đồng nghĩa giải phóng ngay toàn bộ dung lượng

Khi table vào recycle bin, các segment vẫn tồn tại và tiếp tục chiếm dung lượng trong tablespace. Vì vậy, DROP một table lớn không nhất thiết làm dung lượng trống tăng ngay.

Đây là lý do một schema có thể báo hết quota sau khi đã DROP nhiều table. Cần kiểm tra recycle bin và purge những object không còn cần khôi phục.

### 2.2. Tên object trong recycle bin

Tên object trong recycle bin thường có dạng:

~~~text
BIN$xxxxxxxxxxxxxxxxxxxxxxxx==$0
~~~

Tên này là tên nội bộ do Oracle sinh ra. Nó không phải tên table nghiệp vụ ban đầu. Recycle bin lưu cả tên gốc để người dùng có thể tra cứu và khôi phục.

Một table đã DROP có thể được thay thế bằng table mới cùng tên. Vì thế, original name không nhất thiết còn duy nhất trong recycle bin: cùng một tên có thể có nhiều phiên bản đã DROP ở các thời điểm khác nhau.

## 3. Bật, tắt và kiểm tra recycle bin

### 3.1. Kiểm tra cấu hình

Trong SQL*Plus:

~~~sql
SHOW PARAMETER recyclebin;
~~~

Hoặc:

~~~sql
SELECT name,
       value,
       isses_modifiable,
       issys_modifiable
FROM v$parameter
WHERE name = 'recyclebin';
~~~

Recycle bin được bật mặc định trong các cấu hình Oracle Database thông dụng. Tuy nhiên, cần kiểm tra giá trị thực tế ở database/session đang chạy.

### 3.2. Tắt recycle bin cho session

~~~sql
ALTER SESSION SET recyclebin = OFF;
~~~

Khi recycle bin bị tắt trong session, table được DROP trong session đó sẽ không được giữ lại theo cơ chế recycle bin. Việc tắt ở session có phạm vi hẹp hơn thay đổi cấu hình toàn database.

### 3.3. Tắt recycle bin ở cấp hệ thống

DBA có thể thay đổi tham số hệ thống theo khả năng sửa đổi của phiên bản và môi trường:

~~~sql
ALTER SYSTEM SET recyclebin = OFF SCOPE = BOTH;
~~~

Nếu môi trường không cho thay đổi với SCOPE đã chọn, kiểm tra tính modifiable của parameter và cấu hình SPFILE/PFILE theo quy trình quản trị. Không dùng thay đổi hệ thống chỉ để giải quyết một lần DROP nhầm.

### 3.4. Bật lại recycle bin

~~~sql
ALTER SESSION SET recyclebin = ON;
~~~

Hoặc DBA bật lại ở cấp hệ thống theo cấu hình phù hợp. Việc bật lại không khôi phục các object đã bị purge trong thời gian recycle bin tắt.

### 3.5. Tắt recycle bin không phải là PURGE

Tắt recycle bin ảnh hưởng cách xử lý các object bị DROP sau khi thay đổi. Nó không tự động purge toàn bộ object đã nằm trong recycle bin từ trước.

Muốn xóa object đang có trong recycle bin, sử dụng lệnh PURGE với phạm vi phù hợp.

## 4. Xem các object trong recycle bin

### 4.1. SHOW RECYCLEBIN

Trong SQL*Plus:

~~~sql
SHOW RECYCLEBIN;
~~~

Lệnh này hiển thị các object trong recycle bin của user hiện tại, thường gồm tên hệ thống, tên gốc, loại object và thời điểm DROP.

### 4.2. USER_RECYCLEBIN

Để truy vấn bằng SQL:

~~~sql
SELECT object_name,
       original_name,
       operation,
       type,
       ts_name,
       droptime,
       can_undrop,
       can_purge
FROM user_recyclebin
ORDER BY droptime DESC;
~~~

Các cột thường được dùng:

| Cột | Ý nghĩa |
| --- | --- |
| OBJECT_NAME | Tên hệ thống trong recycle bin, thường bắt đầu BIN$ |
| ORIGINAL_NAME | Tên object trước khi DROP |
| OPERATION | Thao tác đưa object vào recycle bin |
| TYPE | Loại object |
| TS_NAME | Tablespace chứa object |
| DROPTIME | Thời điểm DROP |
| CAN_UNDROP | Object có thể được khôi phục hay không |
| CAN_PURGE | Object có thể được purge hay không |
| BASE_OBJECT | Mã nhận diện object gốc liên quan |
| RELATED | Liên hệ với object phụ thuộc |

Tên và tập cột có thể thay đổi theo view/phiên bản. Dùng mô tả data dictionary của đúng release khi cần kiểm tra đầy đủ.

### 4.3. RECYCLEBIN synonym

RECYCLEBIN là synonym thuận tiện để xem recycle bin của user hiện tại trong các công cụ SQL hỗ trợ:

~~~sql
SELECT object_name,
       original_name,
       type,
       droptime
FROM recyclebin
ORDER BY droptime DESC;
~~~

### 4.4. DBA_RECYCLEBIN

DBA có thể xem recycle bin của nhiều schema bằng DBA_RECYCLEBIN nếu có quyền dictionary phù hợp:

~~~sql
SELECT owner,
       object_name,
       original_name,
       type,
       ts_name,
       droptime,
       can_undrop,
       can_purge
FROM dba_recyclebin
ORDER BY owner, droptime DESC;
~~~

View này hữu ích khi điều tra dung lượng toàn database hoặc xác định object nào đang giữ segment trong tablespace.

### 4.5. Phân biệt object chính và dependent object

Khi DROP table, Oracle có thể đưa cả các dependent object liên quan vào recycle bin, ví dụ index và một số object gắn với table. Vì thế một table có thể tạo nhiều dòng trong USER_RECYCLEBIN.

Không coi mỗi dòng trong recycle bin là một table nghiệp vụ riêng. Dùng TYPE, ORIGINAL_NAME, RELATED và BASE_OBJECT để nhận diện object chính và object phụ thuộc.

## 5. FLASHBACK DROP: khôi phục table đã DROP

### 5.1. Cú pháp cơ bản

~~~sql
FLASHBACK TABLE table_name
TO BEFORE DROP;
~~~

Ví dụ:

~~~sql
FLASHBACK TABLE employees
TO BEFORE DROP;
~~~

Oracle tìm phiên bản table phù hợp trong recycle bin và khôi phục về schema với tên gốc nếu tên đó còn khả dụng.

### 5.2. Khôi phục với tên mới

Nếu table mới đã được tạo cùng tên, hoặc muốn giữ cả phiên bản mới và phiên bản cũ, dùng RENAME TO:

~~~sql
FLASHBACK TABLE employees
TO BEFORE DROP
RENAME TO employees_recovered;
~~~

Table cũ được khôi phục với tên EMPLOYEES_RECOVERED. Tên mới phải hợp lệ và không xung đột với object đang tồn tại trong schema.

### 5.3. Khôi phục phiên bản cụ thể bằng recycle bin name

Nếu một table cùng tên đã bị DROP nhiều lần, recycle bin có thể chứa nhiều phiên bản. Có thể chỉ rõ tên hệ thống của object cần khôi phục:

~~~sql
SELECT object_name,
       original_name,
       droptime
FROM user_recyclebin
WHERE original_name = 'EMPLOYEES'
ORDER BY droptime DESC;
~~~

Sau khi xác định đúng BIN$ name:

~~~sql
FLASHBACK TABLE "BIN$xxxxxxxxxxxxxxxx==$0"
TO BEFORE DROP
RENAME TO employees_older;
~~~

Tên BIN$ cần được đặt trong dấu nháy kép vì có ký tự đặc biệt và cách viết do Oracle tạo ra. Không tự đoán tên hệ thống; lấy chính xác từ USER_RECYCLEBIN hoặc DBA_RECYCLEBIN.

### 5.4. Khi có nhiều phiên bản cùng original name

Nếu không chỉ rõ recycle bin name, Oracle chọn object phù hợp theo quy tắc mặc định, thường là phiên bản mới nhất có thể khôi phục. Để tránh khôi phục nhầm bản cũ/mới:

1. Query USER_RECYCLEBIN.
2. So sánh ORIGINAL_NAME và DROPTIME.
3. Kiểm tra TYPE và các object liên quan.
4. Dùng OBJECT_NAME cụ thể trong FLASHBACK TABLE.
5. Đặt RENAME TO nếu tên gốc đã được sử dụng hoặc cần giữ hai phiên bản.

### 5.5. Khôi phục dependent objects

Khi table được khôi phục, Oracle cũng khôi phục các dependent object được giữ trong recycle bin cùng table, chẳng hạn index và trigger liên quan. Tuy nhiên, tên của dependent object có thể cần kiểm tra nếu tên cũ đã được dùng bởi object mới hoặc có xung đột.

Sau khi Flashback Drop, kiểm tra:

~~~sql
SELECT index_name,
       index_type,
       status
FROM user_indexes
WHERE table_name = 'EMPLOYEES_RECOVERED';

SELECT trigger_name,
       status
FROM user_triggers
WHERE table_name = 'EMPLOYEES_RECOVERED';

SELECT constraint_name,
       constraint_type,
       status
FROM user_constraints
WHERE table_name = 'EMPLOYEES_RECOVERED';
~~~

Tên table trong các query phải khớp với tên đã khôi phục. Nếu table được phục hồi dưới tên gốc, thay EMPLOYEES_RECOVERED bằng EMPLOYEES.

### 5.6. Quyền trên table được khôi phục

Các grant gắn với table được recycle bin lưu cùng object và có thể được khôi phục theo cơ chế Flashback Drop. Sau khi restore, kiểm tra object privilege bằng USER_TAB_PRIVS hoặc DBA_TAB_PRIVS để xác nhận trạng thái thực tế.

Không giả định mọi dependency bên ngoài table đều tự động được dựng lại. Đặc biệt, nếu DROP dùng CASCADE CONSTRAINTS làm mất foreign key constraint ở các table khác, cần kiểm tra và xử lý các constraint liên quan theo kế hoạch riêng.

## 6. Điều kiện và giới hạn của FLASHBACK DROP

Flashback Drop chỉ làm việc khi object còn tồn tại trong recycle bin và Oracle vẫn có thể khôi phục object đó.

Các trường hợp không thể dựa vào Flashback Drop:

- Table đã bị purge.
- Table được DROP với PURGE.
- Recycle bin bị tắt tại thời điểm DROP.
- Object không thuộc nhóm được recycle bin hỗ trợ.
- Object trong recycle bin đã bị Oracle tự động purge để lấy chỗ.
- Tablespace chứa object đã bị drop hoặc không còn khả dụng.
- Object thuộc trường hợp đặc biệt không được đưa vào recycle bin theo quy tắc Oracle, chẳng hạn object của SYS hoặc table trong SYSTEM tablespace.

Recycle bin chủ yếu hỗ trợ table và các dependent object. Không phải mọi loại schema object như package, procedure, sequence hoặc user đều có thể khôi phục bằng FLASHBACK TABLE ... TO BEFORE DROP.

### 6.1. Object thuộc SYS và SYSTEM tablespace

Không dùng recycle bin như cơ chế khôi phục object hệ thống của SYS. Các table trong SYSTEM tablespace và các object thuộc trường hợp Oracle loại trừ không được bảo vệ theo cách thông thường.

Đặt application table trong tablespace ứng dụng phù hợp thay vì SYSTEM.

### 6.2. Table thuộc cluster

Table là thành viên của cluster có các giới hạn riêng đối với recycle bin/Flashback Drop. Không giả định table trong cluster có thể được khôi phục giống heap table thông thường.

### 6.3. Object đã bị purge hoặc tự động purge

Khi object đã bị purge, metadata recycle bin không còn là cơ sở để Flashback Drop. Cần chuyển sang phương án recovery phù hợp như RMAN restore/recover, auxiliary database hoặc backup khác.

### 6.4. Tên object bị chiếm dụng

Nếu đã tạo object mới cùng tên gốc, Flashback Drop không thể đơn giản ghi đè object mới. Dùng RENAME TO để khôi phục object cũ dưới tên khác, sau đó so sánh dữ liệu và quyết định hợp nhất/đổi tên.

### 6.5. Quota và tablespace

Table được khôi phục cần có tablespace và dung lượng phù hợp. Kiểm tra quota của owner và tình trạng tablespace trước khi restore, đặc biệt khi object đã nằm trong recycle bin lâu hoặc storage đã thay đổi.

### 6.6. Flashback Drop không phục hồi dữ liệu đã bị TRUNCATE

TRUNCATE TABLE không chuyển table vào recycle bin. Nó giữ object nhưng loại bỏ dữ liệu theo semantics của DDL. FLASHBACK TABLE ... TO BEFORE DROP không phải công cụ phục hồi row đã bị truncate.

Nếu truncate nhầm, cần xem xét backup/recovery, Flashback Database hoặc giải pháp khôi phục khác phù hợp với trạng thái database.

## 7. PURGE: xóa vĩnh viễn object trong recycle bin

PURGE loại bỏ object khỏi recycle bin và giải phóng các segment tương ứng khi Oracle hoàn tất xử lý. Sau purge, Flashback Drop không thể khôi phục object đó.

### 7.1. Purge một table

~~~sql
PURGE TABLE employees;
~~~

Lệnh này purge object trong recycle bin có original name phù hợp của schema hiện tại. Nếu có nhiều phiên bản cùng tên, hãy kiểm tra recycle bin và chỉ rõ tên hệ thống khi cần xác định chính xác object.

### 7.2. Purge bằng tên hệ thống

~~~sql
PURGE TABLE "BIN$xxxxxxxxxxxxxxxx==$0";
~~~

Dùng cách này khi có nhiều bản DROP cùng original name hoặc muốn purge chính xác một object.

### 7.3. Purge index

~~~sql
PURGE INDEX old_employee_idx;
~~~

Lệnh này áp dụng cho index đang nằm trong recycle bin. Nếu index là dependent object của table trong recycle bin, việc purge table có thể purge cả các dependent object của table.

### 7.4. Purge recycle bin của user hiện tại

~~~sql
PURGE RECYCLEBIN;
~~~

Lệnh này purge các object trong recycle bin của user hiện tại. Chỉ sử dụng khi user xác nhận không cần Flashback Drop bất kỳ object nào đang giữ.

### 7.5. Purge theo tablespace

~~~sql
PURGE TABLESPACE users;
~~~

Có thể chỉ định user để giới hạn phạm vi trong tablespace:

~~~sql
PURGE TABLESPACE users USER app_owner;
~~~

Đây là thao tác theo phạm vi tablespace, có thể xóa nhiều object hơn một table cụ thể. Kiểm tra DBA_RECYCLEBIN trước khi chạy.

### 7.6. Purge recycle bin toàn database

~~~sql
PURGE DBA_RECYCLEBIN;
~~~

Đây là thao tác quản trị phạm vi toàn database, yêu cầu quyền quản trị đặc biệt theo quy tắc Oracle. Nó có thể xóa object trong recycle bin của nhiều schema. Không dùng thay cho PURGE RECYCLEBIN của một user.

### 7.7. DROP TABLE ... PURGE

Nếu đã chắc chắn không cần Flashback Drop:

~~~sql
DROP TABLE employees PURGE;
~~~

Table được drop và purge trực tiếp thay vì chuyển vào recycle bin. Đây là quyết định không thể đảo ngược bằng Flashback Drop.

## 8. So sánh DROP, FLASHBACK DROP, PURGE và TRUNCATE

| Thao tác | Table còn tồn tại dưới tên cũ? | Dữ liệu có còn trong table? | Recycle bin | Khôi phục bằng Flashback Drop? |
| --- | --- | --- | --- | --- |
| DROP TABLE | Không | Table được giữ nếu đủ điều kiện | Có thể có | Có, nếu object còn trong recycle bin |
| DROP TABLE ... PURGE | Không | Không | Không | Không |
| FLASHBACK TABLE ... TO BEFORE DROP | Có, theo tên gốc hoặc tên mới | Dữ liệu table được khôi phục | Object được lấy ra | Không còn là object trong recycle bin |
| PURGE TABLE | Không | Không | Object bị xóa khỏi recycle bin | Không |
| TRUNCATE TABLE | Có | Các row bị loại bỏ | Không đưa table vào recycle bin | Không thể dùng Flashback Drop |
| DELETE FROM table | Có | Row bị xóa theo transaction | Không | Có thể ROLLBACK trước COMMIT; có thể có phương án Flashback Query tùy retention |

### 8.1. DROP TABLE

~~~sql
DROP TABLE employees;
~~~

Nếu table đủ điều kiện và recycle bin bật, Oracle giữ object trong recycle bin.

### 8.2. DROP TABLE PURGE

~~~sql
DROP TABLE employees PURGE;
~~~

Bỏ qua recycle bin cho table bị drop. Không thể khôi phục bằng FLASHBACK TABLE ... TO BEFORE DROP.

### 8.3. TRUNCATE TABLE

~~~sql
TRUNCATE TABLE employees;
~~~

TRUNCATE là DDL, không đưa table vào recycle bin và không thể rollback như DELETE. Table vẫn tồn tại nhưng dữ liệu đã bị loại bỏ. Không nhầm TRUNCATE với DROP.

### 8.4. DELETE FROM

~~~sql
DELETE FROM employees
WHERE department_id = 50;

ROLLBACK;
~~~

DELETE là DML và có thể rollback trước COMMIT. Sau COMMIT, Flashback Query/Flashback Table hoặc media recovery có thể là phương án tùy cấu hình và thời gian retention; recycle bin không liên quan.

## 9. Tự động purge khi thiếu dung lượng

Recycle bin không bảo đảm giữ object vô thời hạn. Khi tablespace cần không gian cho allocation mới, Oracle có thể tự động purge object trong recycle bin của tablespace đó để giải phóng extent.

Điều này có nghĩa:

- Table đã DROP hôm qua có thể không còn trong recycle bin hôm nay nếu tablespace cần dung lượng.
- Một table lớn trong recycle bin có thể bị tự động purge trước khi người dùng kịp khôi phục.
- Không thể coi recycle bin là nơi lưu trữ dài hạn.
- Muốn giữ khả năng phục hồi trong thời gian dài, phải có backup/recovery strategy phù hợp.

### 9.1. Áp lực dung lượng và quota

Object trong recycle bin vẫn chiếm dung lượng tablespace. Khi schema gần hết quota, việc DROP table không nhất thiết giúp schema có đủ quota để tạo object mới. Purge object phù hợp có thể giải phóng extent.

### 9.2. Theo dõi dung lượng tablespace

Ví dụ kiểm tra datafile:

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS allocated_mb
FROM dba_data_files
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

Kiểm tra free extent:

~~~sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS free_mb
FROM dba_free_space
GROUP BY tablespace_name
ORDER BY tablespace_name;
~~~

Hai query này cần quyền dictionary phù hợp. Với bigfile tablespace, autoextend, ASM và quota, cần đọc thêm datafile/storage metrics thay vì chỉ nhìn tổng allocated/free.

### 9.3. Tìm object recycle bin chiếm dung lượng

Recycle bin view cung cấp metadata về object; để điều tra dung lượng chi tiết, có thể kết hợp DBA_RECYCLEBIN với segment metadata theo tên object nếu quyền và view hỗ trợ:

~~~sql
SELECT r.owner,
       r.object_name,
       r.original_name,
       r.type,
       r.ts_name,
       r.droptime,
       s.bytes
FROM dba_recyclebin r
LEFT JOIN dba_segments s
  ON s.owner = r.owner
 AND s.segment_name = r.object_name
ORDER BY s.bytes DESC NULLS LAST;
~~~

Tên segment và cách lưu dependent object có thể khiến phép nối đơn giản này không bao phủ toàn bộ dung lượng của một table. Hãy xem các related objects và tổng hợp theo base object khi cần báo cáo chính xác.

### 9.4. Không dựa vào thời gian lưu cố định

Recycle bin không phải retention window có số ngày cố định. Thời gian object tồn tại phụ thuộc dung lượng, hoạt động cấp phát và purge của DBA. Nếu nghiệp vụ yêu cầu giữ bản table đã drop trong 30 ngày, cần một quy trình backup/export riêng thay vì dựa vào recycle bin.

## 10. Quy trình phục hồi table bị DROP nhầm

Khi phát hiện table bị DROP nhầm, tránh tạo thêm object hoặc purge trước khi xác định tình trạng.

### Bước 1. Xác định schema và tên table

~~~sql
SHOW USER;

SELECT object_name,
       original_name,
       type,
       droptime,
       can_undrop,
       can_purge
FROM user_recyclebin
WHERE original_name = 'EMPLOYEES'
ORDER BY droptime DESC;
~~~

Nếu table thuộc schema khác, DBA kiểm tra DBA_RECYCLEBIN.

### Bước 2. Xác định đúng phiên bản

So sánh DROPTIME, OBJECT_NAME và các dependent object. Nếu có nhiều phiên bản cùng tên, chọn đúng BIN$ name thay vì dùng tên gốc một cách mơ hồ.

### Bước 3. Kiểm tra tên đích

~~~sql
SELECT object_name,
       object_type
FROM user_objects
WHERE object_name IN ('EMPLOYEES', 'EMPLOYEES_RECOVERED');
~~~

Nếu tên gốc đang được sử dụng, chọn tên phục hồi khác.

### Bước 4. Kiểm tra tablespace và quota

Xác nhận owner vẫn có quyền/quota và tablespace còn khả dụng. Nếu object cần khôi phục nằm trong tablespace không còn dùng được, xử lý theo quy trình storage/DBA.

### Bước 5. Thực hiện Flashback Drop

~~~sql
FLASHBACK TABLE employees
TO BEFORE DROP
RENAME TO employees_recovered;
~~~

Nếu không có xung đột tên và muốn khôi phục tên gốc, có thể bỏ RENAME TO.

### Bước 6. Kiểm tra dữ liệu

~~~sql
SELECT COUNT(*)
FROM employees_recovered;

SELECT *
FROM employees_recovered
FETCH FIRST 10 ROWS ONLY;
~~~

Đối chiếu row count, khóa, dữ liệu mẫu và yêu cầu nghiệp vụ. Nếu table được khôi phục dưới tên khác, kiểm tra các view/procedure/application reference đang mong đợi tên gốc.

### Bước 7. Kiểm tra dependent objects và grants

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE table_name = 'EMPLOYEES_RECOVERED';

SELECT constraint_name, constraint_type, status
FROM user_constraints
WHERE table_name = 'EMPLOYEES_RECOVERED';

SELECT trigger_name, status
FROM user_triggers
WHERE table_name = 'EMPLOYEES_RECOVERED';
~~~

Kiểm tra object privilege, synonym, view, procedure và foreign key từ table khác. Rebuild/recreate những dependency không được tự khôi phục hoặc đã bị thay đổi bởi thao tác DROP.

### Bước 8. Chỉ purge phiên bản không cần sau khi xác nhận

Sau khi xác nhận table đã khôi phục đúng và các dependency hoạt động, mới purge các bản DROP còn lại nếu không cần nữa. Tránh PURGE RECYCLEBIN ngay đầu quy trình.

## 11. Ví dụ thực hành đầy đủ

Lab dưới đây tạo table, DROP, xem recycle bin, khôi phục, thử tên xung đột và PURGE. Chạy trong schema thử nghiệm.

### 11.1. Tạo table

~~~sql
CREATE TABLE recycle_lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL,
    amount NUMBER(12,2)
);

INSERT INTO recycle_lab_orders
VALUES (1, 'Customer A', 120);

INSERT INTO recycle_lab_orders
VALUES (2, 'Customer B', 250);

COMMIT;
~~~

### 11.2. DROP table

~~~sql
DROP TABLE recycle_lab_orders;
~~~

Nếu recycle bin bật và table đủ điều kiện, table sẽ xuất hiện trong recycle bin.

### 11.3. Xem recycle bin

~~~sql
SELECT object_name,
       original_name,
       type,
       droptime,
       can_undrop
FROM user_recyclebin
WHERE original_name = 'RECYCLE_LAB_ORDERS'
ORDER BY droptime DESC;
~~~

Ghi lại OBJECT_NAME do Oracle sinh ra.

### 11.4. Khôi phục bằng tên gốc

~~~sql
FLASHBACK TABLE recycle_lab_orders
TO BEFORE DROP;
~~~

Kiểm tra:

~~~sql
SELECT *
FROM recycle_lab_orders
ORDER BY order_id;
~~~

### 11.5. DROP lần nữa và tạo table mới cùng tên

~~~sql
DROP TABLE recycle_lab_orders;

CREATE TABLE recycle_lab_orders (
    order_id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);
~~~

Table mới đang sử dụng tên gốc. Phiên bản cũ vẫn có thể còn trong recycle bin.

### 11.6. Khôi phục phiên bản cũ dưới tên khác

~~~sql
FLASHBACK TABLE recycle_lab_orders
TO BEFORE DROP
RENAME TO recycle_lab_orders_old;
~~~

Kiểm tra hai table:

~~~sql
SELECT * FROM recycle_lab_orders;
SELECT * FROM recycle_lab_orders_old ORDER BY order_id;
~~~

Table mới và table được khôi phục cùng tồn tại dưới hai tên khác nhau.

### 11.7. Purge object cũ

~~~sql
PURGE TABLE recycle_lab_orders_old;
~~~

Nếu object cần purge vẫn ở recycle bin dưới tên hệ thống, query USER_RECYCLEBIN rồi dùng chính xác tên BIN$.

### 11.8. Dọn lab

~~~sql
DROP TABLE recycle_lab_orders PURGE;
DROP TABLE recycle_lab_orders_old PURGE;
~~~

Nếu table đã được purge ở bước trước, lệnh DROP tương ứng có thể không còn cần thiết. Chỉ chạy cleanup cho object lab đã xác định, không dùng trên object nghiệp vụ.

## 12. Quyền và phạm vi quản trị

### 12.1. User khôi phục table của chính mình

Thông thường owner có thể xem recycle bin của mình, khôi phục table thuộc schema của mình và purge object của mình theo quyền sở hữu.

### 12.2. DBA khôi phục object của schema khác

Để thao tác trên object của schema khác, cần privilege quản trị phù hợp, ví dụ FLASHBACK ANY TABLE và quyền dictionary để xem recycle bin toàn database. Không cấp quyền rộng này cho user ứng dụng chỉ để phục hồi một table.

### 12.3. DBA_RECYCLEBIN và PURGE DBA_RECYCLEBIN

DBA_RECYCLEBIN cho phép quản trị viên quan sát object trong recycle bin của các owner. PURGE DBA_RECYCLEBIN là thao tác phạm vi toàn database và cần quyền quản trị đặc biệt. Phải kiểm tra tác động tới mọi schema trước khi thực hiện.

### 12.4. Quyền trên object được khôi phục

Sau khi khôi phục, kiểm tra lại:

- Object owner và tên table.
- Index, trigger, constraint.
- Object privilege grants.
- Synonym và dependency.
- View/procedure/package tham chiếu table.
- Application account và role liên quan.

Không chỉ xác nhận câu FLASHBACK TABLE chạy thành công rồi kết luận ứng dụng đã hoạt động bình thường.

## 13. Bảo mật và quản trị vòng đời dữ liệu

Recycle bin có thể giữ dữ liệu sau khi người dùng nghĩ rằng table đã bị xóa. Điều này có ý nghĩa với dữ liệu nhạy cảm và yêu cầu retention:

- DROP table không đồng nghĩa dữ liệu đã được xóa vĩnh viễn khỏi database storage.
- Người có quyền phù hợp có thể khôi phục table từ recycle bin.
- Object trong recycle bin tiếp tục chiếm storage.
- Oracle có thể tự động purge khi cần chỗ, nên không bảo đảm giữ lâu dài.
- PURGE làm mất khả năng Flashback Drop và cần được kiểm soát theo chính sách.

Với dữ liệu nhạy cảm, phải áp dụng data retention, encryption, access control và quy trình purge theo yêu cầu pháp lý/nghiệp vụ. Không coi DROP thường là phương pháp secure erase.

### 13.1. Phân biệt purge với backup retention

PURGE xóa object khỏi recycle bin trong database hiện tại. Nó không tự động xóa bản backup RMAN hoặc bản export đã được lưu ở nơi khác. Nếu yêu cầu xóa dữ liệu trên mọi bản sao, cần quy trình riêng bao phủ backup, replica, standby, export và storage lifecycle.

### 13.2. Kiểm soát PURGE

Trong production:

1. Chỉ người chịu trách nhiệm dữ liệu mới phê duyệt purge.
2. Xác định owner, original name, object name và tablespace.
3. Kiểm tra object có đang được giữ để phục hồi không.
4. Kiểm tra dependent object và ứng dụng.
5. Xem phạm vi lệnh: một table, một tablespace, user hay toàn database.
6. Ghi nhận thay đổi theo audit/change management.
7. Xác minh dung lượng sau purge.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng/lỗi | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| FLASHBACK TABLE không tìm thấy object | Table không ở recycle bin, recycle bin OFF khi DROP hoặc object đã purge | Kiểm tra USER_RECYCLEBIN/DBA_RECYCLEBIN và alert/history |
| ORA-38305: object not in RECYCLE BIN | Object không còn trong recycle bin hoặc tên không đúng | Query lại recycle bin và xác định đúng object |
| ORA-38312: original name is used by an existing object | Tên gốc đã được table/object khác sử dụng | Dùng RENAME TO với tên đích chưa tồn tại |
| ORA-38301: can not perform DDL/DML over objects in Recycle Bin | Đang thao tác trực tiếp trên object recycle bin theo cách không hỗ trợ | Dùng FLASHBACK TABLE để khôi phục trước |
| FLASHBACK DROP không khôi phục được table | Object không được hỗ trợ, đã purge hoặc tablespace không khả dụng | Kiểm tra giới hạn recycle bin và phương án RMAN |
| DROP table nhưng dung lượng không giảm | Segment vẫn nằm trong recycle bin | Kiểm tra recycle bin và purge object không cần |
| Không tạo được table mới do quota | Object đã drop vẫn chiếm quota/tablespace | Xem quota và purge có kiểm soát |
| Table khôi phục được nhưng ứng dụng lỗi | Dependency, grants, synonym hoặc tên object thay đổi | Kiểm tra index/constraint/trigger/grant và compile dependency |
| Không thấy object trong SHOW RECYCLEBIN | Đang đăng nhập sai owner hoặc object không được recycle | Kiểm tra SHOW USER và DBA_RECYCLEBIN |
| Object biến mất khỏi recycle bin | Có thể đã bị auto purge do tablespace pressure hoặc bị purge thủ công | Chuyển sang backup/recovery nếu cần |

Thông báo lỗi và khả năng xử lý phụ thuộc phiên bản, loại object và trạng thái recycle bin. Đọc đầy đủ lỗi Oracle thay vì chỉ dựa vào tên lỗi trong bảng.

## 15. Checklist trước khi FLASHBACK DROP hoặc PURGE

1. **Đúng database/PDB/schema chưa?** Xác nhận môi trường và owner.
2. **Recycle bin có bật khi DROP không?** Kiểm tra parameter và lịch sử thao tác.
3. **Object còn trong recycle bin không?** Query USER_RECYCLEBIN hoặc DBA_RECYCLEBIN.
4. **Đã chọn đúng phiên bản chưa?** So sánh ORIGINAL_NAME, OBJECT_NAME và DROPTIME.
5. **Tên đích có bị chiếm không?** Dùng RENAME TO nếu cần.
6. **Tablespace và quota còn khả dụng không?** Xác nhận khả năng restore.
7. **Dependent object nào cần kiểm tra?** Index, trigger, constraint và grant.
8. **Có foreign key ở table khác không?** Đặc biệt khi DROP dùng CASCADE CONSTRAINTS.
9. **Có thể tự động purge không?** Recycle bin không phải retention dài hạn.
10. **PURGE có đúng phạm vi không?** Một object, recycle bin user, tablespace hay toàn database.
11. **Có cần giữ backup không?** Recycle bin không thay thế RMAN.
12. **Đã xác nhận dữ liệu sau restore chưa?** Kiểm tra row count và dữ liệu nghiệp vụ.
13. **Đã kiểm tra application dependency chưa?** View, synonym, stored code và grants.
14. **Đã phê duyệt purge chưa?** Purge không thể Flashback Drop trở lại.
15. **Đã ghi nhận thao tác chưa?** Lưu người thực hiện, thời điểm, object và lý do.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Recycle bin của Oracle dùng để làm gì?

**Câu 2.** DROP TABLE thông thường khác DROP TABLE PURGE như thế nào?

**Câu 3.** Vì sao table đã DROP vẫn có thể chiếm dung lượng?

**Câu 4.** Tên BIN$... trong recycle bin có ý nghĩa gì?

**Câu 5.** USER_RECYCLEBIN và DBA_RECYCLEBIN khác nhau thế nào?

**Câu 6.** FLASHBACK TABLE ... TO BEFORE DROP làm gì?

**Câu 7.** RENAME TO được dùng trong trường hợp nào?

**Câu 8.** Làm sao chọn đúng một phiên bản table khi cùng tên đã DROP nhiều lần?

**Câu 9.** Dependent object nào cần kiểm tra sau Flashback Drop?

**Câu 10.** PURGE TABLE khác PURGE RECYCLEBIN như thế nào?

**Câu 11.** PURGE DBA_RECYCLEBIN có phạm vi gì?

**Câu 12.** Vì sao không nên xóa file recycle bin bằng lệnh hệ điều hành?

**Câu 13.** Oracle có thể tự động purge object trong trường hợp nào?

**Câu 14.** Recycle bin có bảo đảm giữ table trong một số ngày cố định không?

**Câu 15.** TRUNCATE TABLE có đưa table vào recycle bin không?

**Câu 16.** Có thể Flashback Drop table đã được purge không?

**Câu 17.** Vì sao cần kiểm tra quota và tablespace trước khi restore?

**Câu 18.** Vì sao DROP TABLE không phải secure erase?

**Câu 19.** Flashback Drop có thay thế RMAN backup không?

**Câu 20.** Khi nào nên dùng DROP TABLE PURGE?

<details>
<summary>Gợi ý đáp án</summary>

1. Giữ lại table đã DROP đủ điều kiện để có thể khôi phục bằng Flashback Drop.
2. DROP thường có thể đưa table vào recycle bin; DROP PURGE xóa vĩnh viễn, bỏ qua recycle bin.
3. Segment vẫn được giữ trong tablespace cho đến khi purge hoặc tự động purge.
4. Tên nội bộ do Oracle sinh ra để nhận diện object trong recycle bin.
5. USER_RECYCLEBIN hiển thị object của user hiện tại; DBA_RECYCLEBIN cho phép DBA xem nhiều owner.
6. Khôi phục table từ recycle bin về schema.
7. Khi tên gốc đã được dùng hoặc muốn khôi phục object dưới tên khác.
8. Query OBJECT_NAME, ORIGINAL_NAME, DROPTIME rồi dùng tên BIN$ cụ thể.
9. Index, trigger, constraint, grants và dependency ngoài table.
10. PURGE TABLE xử lý một object; PURGE RECYCLEBIN xóa recycle bin của user hiện tại.
11. Purge object trong recycle bin toàn database, cần quyền quản trị đặc biệt.
12. Có thể làm metadata/repository không đồng bộ và ảnh hưởng recovery.
13. Khi tablespace cần dung lượng để cấp phát extent mới.
14. Không. Thời gian tồn tại phụ thuộc áp lực dung lượng và thao tác purge.
15. Không. TRUNCATE giữ table nhưng loại bỏ dữ liệu, không đưa table vào recycle bin.
16. Không. Cần backup hoặc phương án recovery khác.
17. Table cần tablespace và khả năng cấp phát phù hợp khi khôi phục.
18. DROP thường giữ object trong recycle bin và dữ liệu vẫn còn trên storage.
19. Không. Recycle bin không bảo vệ khỏi mất database/storage và có thể tự động purge.
20. Khi đã xác nhận không cần Flashback Drop và chính sách yêu cầu xóa object khỏi recycle bin ngay.

</details>

## 17. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — FLASHBACK TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FLASHBACK-TABLE.html): cú pháp Flashback Table và Flashback Drop.
2. [Oracle Database 19c Administrator's Guide — Managing the Recycle Bin](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html): recycle bin, xem, khôi phục và purge object.
3. [Oracle Database 19c SQL Language Reference — PURGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/PURGE.html): cú pháp PURGE theo object, tablespace và recycle bin.
4. [Oracle Database 19c SQL Language Reference — DROP TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DROP-TABLE.html): DROP TABLE và tùy chọn PURGE.
5. [Oracle Database 19c Reference — USER_RECYCLEBIN](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_RECYCLEBIN.html): metadata recycle bin của user hiện tại.
6. [Oracle Database 19c Reference — DBA_RECYCLEBIN](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_RECYCLEBIN.html): metadata recycle bin ở phạm vi database.
7. [Oracle Database 19c Administrator's Guide — Managing Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html): quản lý table, quota và dung lượng.
8. [Oracle Database 19c Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/): các phương án backup và recovery khi Flashback Drop không còn khả dụng.

**Nguyên tắc cần nhớ:** DROP TABLE có thể đưa table vào recycle bin; FLASHBACK TABLE ... TO BEFORE DROP khôi phục object còn được giữ; PURGE xóa vĩnh viễn và không thể Flashback Drop trở lại. Recycle bin có thể bị Oracle tự động purge khi tablespace cần chỗ, vì vậy không phải nơi lưu backup dài hạn. Trước khi restore, xác định đúng phiên bản và kiểm tra dependency; trước khi purge, xác nhận phạm vi và yêu cầu recovery.
