# FLASHBACK TABLE, row movement và giới hạn phụ thuộc trong Oracle Database

FLASHBACK TABLE cho phép đưa một hoặc nhiều bảng về trạng thái dữ liệu tại một thời điểm hoặc SCN trong quá khứ mà không cần restore toàn bộ database. Đây là công cụ hữu ích khi người dùng vô tình xóa/cập nhật nhầm dữ liệu, một batch ghi sai hàng hoặc ứng dụng phát sinh thay đổi ngoài dự kiến.

Để thực hiện được, Oracle cần các phiên bản dữ liệu cũ còn khả dụng trong undo. Bảng cũng phải cho phép row movement. Khi flashback, Oracle có thể thay đổi vị trí vật lý của hàng, vì vậy ROWID có thể đổi. Các bảng có quan hệ khóa ngoại, trigger, index và materialized view phụ thuộc cần được xem xét trước khi khôi phục.

FLASHBACK TABLE là thao tác phục hồi dữ liệu ở phạm vi bảng. Nó không khôi phục toàn bộ database, không đảo ngược mọi thay đổi DDL và không thay thế backup. Đặc biệt, việc flashback một bảng riêng lẻ có thể gây mất nhất quán với bảng cha/con hoặc hệ thống bên ngoài nếu các phụ thuộc không được xử lý cùng thời điểm.

Bài học lấy Oracle Database 19c làm mốc, giải thích cơ chế, điều kiện tiên quyết, row movement, cách dùng TO SCN/TO TIMESTAMP, phục hồi nhiều bảng, ảnh hưởng tới trigger/index/constraint, giới hạn, lỗi thường gặp và quy trình phục hồi có kiểm soát.

## 1. FLASHBACK TABLE dùng để làm gì?

### 1.1. Khôi phục dữ liệu bảng về một thời điểm trước đó

Giả sử ứng dụng chạy nhầm câu lệnh:

~~~sql
UPDATE hr.employees
SET    salary = salary * 10;
~~~

Nếu chưa có transaction khác làm thay đổi dữ liệu theo cách không thể đảo ngược bằng rollback, người quản trị có thể dùng Flashback Table để đưa bảng về thời điểm trước câu lệnh sai, miễn là undo cần thiết vẫn còn.

Một ví dụ khác là người dùng xóa nhầm một nhóm hàng:

~~~sql
DELETE FROM orders
WHERE  order_date < DATE '2024-01-01';
COMMIT;
~~~

Sau COMMIT, ROLLBACK không thể hoàn tác transaction đó. FLASHBACK TABLE có thể khôi phục trạng thái bảng về trước thời điểm DELETE nếu đáp ứng các điều kiện và giới hạn.

### 1.2. Flashback Table không phải backup/restore

| Cơ chế | Phạm vi | Mục tiêu |
| --- | --- | --- |
| ROLLBACK | Transaction hiện tại chưa commit | Hủy thay đổi của transaction |
| Flashback Query | Truy vấn dữ liệu trong quá khứ | Xem lại phiên bản hàng |
| Flashback Versions Query | Xem lịch sử phiên bản hàng trong một khoảng | Điều tra thay đổi |
| Flashback Transaction Query | Xem thông tin transaction đã thay đổi dữ liệu | Tìm SQL/transaction gây thay đổi |
| FLASHBACK TABLE | Đưa dữ liệu một hoặc nhiều bảng về thời điểm trước | Khôi phục bảng |
| Flashback Drop | Khôi phục table đã DROP còn trong recycle bin | Lấy lại object bị drop |
| Flashback Database | Đưa database về một SCN/thời điểm trước | Phục hồi ở phạm vi database |
| RMAN restore/recover | Khôi phục datafile/database từ backup và redo | Phục hồi khi cần bản sao lưu |

FLASHBACK TABLE phù hợp khi phạm vi sự cố nằm ở một hoặc một nhóm bảng và undo còn đủ. Nếu database bị hỏng rộng, cần khôi phục DDL, datafile hoặc thay đổi đã vượt thời gian undo, hãy đánh giá Flashback Database hoặc RMAN.

### 1.3. Dữ liệu được khôi phục, cấu trúc bảng không quay về quá khứ

FLASHBACK TABLE chủ yếu khôi phục nội dung hàng. Nó không phải cơ chế khôi phục định nghĩa bảng về phiên bản DDL cũ.

Ví dụ:
- UPDATE/DELETE/INSERT nhầm: có thể phù hợp.
- Thay đổi cấu trúc cột, truncate hoặc các DDL làm thay đổi object: có thể khiến flashback về thời điểm trước đó không khả thi.
- DROP TABLE: dùng Flashback Drop nếu object còn trong recycle bin, hoặc phương án backup/recovery phù hợp.

Luôn xác định thời điểm và loại thao tác gây lỗi trước khi chọn cơ chế.

## 2. Cơ chế và nguồn dữ liệu phục hồi

### 2.1. Undo cung cấp phiên bản dữ liệu cũ

Oracle lưu undo record để hỗ trợ rollback và read consistency. FLASHBACK TABLE dùng thông tin undo để dựng lại trạng thái hàng tại target SCN hoặc timestamp.

Điều đó có nghĩa:
- Undo cần thiết phải còn khả dụng.
- Query hoặc thao tác flashback quá cũ có thể gặp lỗi snapshot/không tìm thấy snapshot.
- Undo retention và dung lượng undo ảnh hưởng khả năng phục hồi.
- Workload DML lớn có thể ghi đè undo cũ nhanh hơn dự kiến nếu không đủ không gian.

Không nên coi UNDO_RETENTION là lời bảo đảm tuyệt đối trong mọi cấu hình. Cần xem trạng thái tablespace, retention policy và workload thực tế.

### 2.2. Flashback Table tạo thay đổi mới

Khi đưa bảng về quá khứ, Oracle thực hiện các thay đổi cần thiết để khôi phục trạng thái hàng. Hoạt động phục hồi này cũng là công việc database, có thể tạo redo/undo và tiêu thụ CPU/I/O.

Sau khi flashback:
- Các thay đổi được thực hiện sau target time bị loại khỏi trạng thái bảng được khôi phục.
- Dữ liệu trở lại trạng thái tại target.
- Các thay đổi flashback là một hoạt động mới trong lịch sử database.
- Những transaction khác hoặc hệ thống ngoài database không tự được đảo ngược.

Hãy kiểm tra tác động tới redo generation, standby/replication, audit trail và ứng dụng.

### 2.3. SCN và timestamp

SCN (System Change Number) là mốc logic mà Oracle dùng để định vị thứ tự thay đổi database. Timestamp dễ hiểu với con người nhưng có thể cần ánh xạ sang SCN.

Khi cần đưa nhiều bảng về cùng một điểm nhất quán, SCN thường là mốc rõ ràng hơn. Ghi lại SCN trước khi bắt đầu một batch hoặc tại thời điểm điều tra nếu có thể.

### 2.4. Vì sao không thể flashback vô hạn về quá khứ?

Undo được tái sử dụng theo chính sách retention và áp lực không gian. Khi phiên bản hàng cần thiết không còn tồn tại, Oracle không thể dựng lại trạng thái đó chỉ từ FLASHBACK TABLE.

Nếu yêu cầu phục hồi vượt quá cửa sổ undo:
- Dùng backup/redo hoặc Flashback Database nếu được cấu hình.
- Dùng bản sao dữ liệu, export hoặc audit trail để tái tạo phần cần thiết.
- Xem xét point-in-time recovery ở phạm vi phù hợp.
- Không thử lặp đi lặp lại với timestamp cũ nếu đã có bằng chứng undo không còn.

## 3. Điều kiện tiên quyết và quyền cần có

### 3.1. Bật row movement cho bảng

Trước khi flashback, bảng phải được bật row movement:

~~~sql
ALTER TABLE hr.employees ENABLE ROW MOVEMENT;
~~~

Nếu chưa bật, câu lệnh FLASHBACK TABLE thường thất bại với ORA-08189.

Có thể kiểm tra trạng thái:

~~~sql
SELECT table_name,
       row_movement
FROM   user_tables
WHERE  table_name = 'EMPLOYEES';
~~~

Với schema khác, dùng DBA_TABLES hoặc ALL_TABLES tùy quyền:

~~~sql
SELECT owner,
       table_name,
       row_movement
FROM   dba_tables
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES';
~~~

ROW_MOVEMENT thường hiển thị ENABLED hoặc DISABLED.

### 3.2. Quyền FLASHBACK

Người thực hiện cần quyền phù hợp:
- FLASHBACK object privilege trên bảng, hoặc
- FLASHBACK ANY TABLE system privilege để flashback các bảng trong phạm vi được phép.

Ngoài quyền FLASHBACK, Oracle yêu cầu các quyền object cần thiết để truy cập và thay đổi bảng, chẳng hạn SELECT, INSERT, DELETE và ALTER theo quy tắc privilege của Flashback Table. Chủ sở hữu bảng thường có các quyền cần thiết trên object của mình.

Ví dụ DBA cấp quyền object cho một user phục hồi:

~~~sql
GRANT FLASHBACK ON hr.employees TO recovery_operator;
GRANT SELECT, INSERT, DELETE, ALTER
ON hr.employees TO recovery_operator;
~~~

Cấp quyền tối thiểu cho đúng object. Không cấp FLASHBACK ANY TABLE hoặc DBA chỉ để tiện chạy một lần nếu quyền object đủ dùng.

### 3.3. Undo phải còn đủ

Trước khi thực hiện, xác định:
- Target time/SCN.
- Undo tablespace và trạng thái datafile.
- UNDO_RETENTION hiện tại.
- Tốc độ sinh undo trong giờ cao điểm.
- Transaction/query dài đang hoạt động.
- Có retention guarantee hay không.
- Có đủ free space để phục hồi và tiếp tục workload không.

Xem cấu hình:

~~~sql
SHOW PARAMETER undo;
~~~

Hoặc:

~~~sql
SELECT name,
       value
FROM   v$parameter
WHERE  name IN ('undo_management', 'undo_tablespace', 'undo_retention');
~~~

### 3.4. Không có DDL không tương thích trong khoảng cần phục hồi

FLASHBACK TABLE không thể tự tái tạo cấu trúc bảng đã thay đổi sau target time. Các thao tác như TRUNCATE hoặc thay đổi định nghĩa bảng có thể ngăn việc flashback về trước thao tác đó.

Nếu nghi ngờ có DDL:
- Xem audit trail hoặc application deployment log.
- Xác định thời điểm DDL.
- Kiểm tra object metadata và lỗi khi thử trong bản sao/test.
- Chọn Flashback Drop, Flashback Database hoặc RMAN nếu phù hợp.

Không chạy flashback thử trên production khi chưa xác định giới hạn DDL.

### 3.5. Bảng phải thuộc loại được hỗ trợ

Oracle có các giới hạn theo loại object, cấu trúc và quan hệ phụ thuộc. Ví dụ, một số bảng đặc biệt như bảng thuộc cluster hoặc cấu trúc không được hỗ trợ có thể không flashback theo cách thông thường.

Trước khi chạy trên bảng phức tạp, kiểm tra phần Restrictions của SQL Language Reference đúng release. Không giả định mọi object xuất hiện trong DBA_TABLES đều có thể flashback.

## 4. ROW MOVEMENT — ý nghĩa và tác động

### 4.1. Row movement là gì?

Trong Oracle, một hàng có ROWID xác định vị trí vật lý của nó. Một số thao tác có thể khiến hàng phải chuyển sang vị trí vật lý khác. Row movement cho phép Oracle thay đổi ROWID của hàng khi cần.

Flashback Table cần khả năng di chuyển hàng để dựng lại trạng thái cũ, vì vậy yêu cầu ENABLE ROW MOVEMENT.

### 4.2. Enable row movement không tự di chuyển toàn bộ hàng

~~~sql
ALTER TABLE hr.employees ENABLE ROW MOVEMENT;
~~~

Lệnh này bật khả năng row movement cho bảng. Nó không tự động scan và di chuyển tất cả hàng sang vị trí mới.

Row movement có thể được sử dụng trong các thao tác như Flashback Table, shrink hoặc một số thao tác liên quan partition key. Hành vi cụ thể phụ thuộc loại bảng và operation.

### 4.3. ROWID có thể thay đổi

Khi flashback hoặc thao tác khác di chuyển hàng, ROWID của hàng có thể khác trước đó. Vì vậy:
- Không lưu ROWID lâu dài như business key.
- Không dùng ROWID làm khóa ngoại giữa các bảng.
- Không giả định ROWID của một hàng giữ nguyên sau flashback.
- Nếu ứng dụng cache ROWID, cần refresh cache sau phục hồi.

ROWID hữu ích để định vị vật lý một hàng tại thời điểm truy vấn, nhưng không phải định danh nghiệp vụ ổn định.

### 4.4. Kiểm tra và thay đổi trạng thái row movement

Xem trạng thái:

~~~sql
SELECT owner,
       table_name,
       row_movement
FROM   dba_tables
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES';
~~~

Bật:

~~~sql
ALTER TABLE hr.employees ENABLE ROW MOVEMENT;
~~~

Tắt lại nếu chính sách thiết kế yêu cầu:

~~~sql
ALTER TABLE hr.employees DISABLE ROW MOVEMENT;
~~~

Không cần tắt ngay sau flashback trong mọi trường hợp. Nếu ứng dụng hoặc quy trình khác cần row movement, giữ ENABLED. Nếu muốn giới hạn khả năng di chuyển hàng, hãy xác nhận không có operation phụ thuộc trước khi disable.

### 4.5. Row movement và partitioned table

Với bảng partition, row movement có thể cần thiết khi UPDATE partition key khiến hàng chuyển partition. Trạng thái row movement vì vậy ảnh hưởng cả operation phân vùng và flashback.

Trước khi thay đổi, xem partition key, partitioning strategy, local/global indexes và ứng dụng. Không tắt row movement theo thói quen nếu bảng cần di chuyển hàng giữa partition.

## 5. Flashback Table theo TIMESTAMP

### 5.1. Cú pháp cơ bản

~~~sql
FLASHBACK TABLE hr.employees
TO TIMESTAMP (SYSTIMESTAMP - INTERVAL '10' MINUTE);
~~~

Câu lệnh đưa HR.EMPLOYEES về trạng thái dữ liệu cách thời điểm hiện tại 10 phút. Bảng phải đáp ứng các điều kiện quyền, row movement, undo và giới hạn object.

### 5.2. Dùng timestamp cố định

~~~sql
FLASHBACK TABLE hr.employees
TO TIMESTAMP (
    TO_TIMESTAMP_TZ(
        '2026-11-14 19:30:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    )
);
~~~

Ví dụ sử dụng timestamp có timezone rõ ràng. Hãy thay thời điểm bằng mốc đã xác nhận từ incident log và kiểm tra timezone của ứng dụng/database trước khi thực hiện.

Không dùng timestamp ước lượng kiểu “khoảng trước đó 10 phút” cho một phục hồi production nếu đã có SCN chính xác từ trace hoặc quy trình điều tra.

### 5.3. Dùng timestamp tương đối

Một số tình huống test có thể dùng:

~~~sql
FLASHBACK TABLE hr.orders
TO TIMESTAMP (SYSTIMESTAMP - INTERVAL '30' MINUTE);
~~~

Thời điểm tương đối phụ thuộc lúc câu lệnh được thực thi. Nếu chuẩn bị nhiều bước hoặc cần flashback nhiều bảng, nên xác định một mốc chung và lưu nó trước.

### 5.4. Kiểm tra trước khi chạy

Trước khi thực hiện, xác nhận:
- Timestamp đúng timezone.
- Target time nằm trong cửa sổ undo khả dụng.
- Bảng chưa bị DDL không tương thích.
- Row movement đang ENABLED.
- Các bảng liên quan đã được xác định.
- Không có transaction/ứng dụng đang thay đổi cùng dữ liệu.
- Có phương án backup/restore nếu flashback không đáp ứng.

## 6. Flashback Table theo SCN

### 6.1. Cú pháp

~~~sql
FLASHBACK TABLE hr.employees
TO SCN 123456789;
~~~

SCN là mốc logic cụ thể. Ví dụ số trên chỉ minh họa; phải dùng SCN thật từ database hoặc incident record.

### 6.2. Lấy current SCN

~~~sql
SELECT current_scn
FROM   v$database;
~~~

Hoặc dùng PL/SQL:

~~~sql
DECLARE
    l_scn NUMBER;
BEGIN
    l_scn := DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER;
    DBMS_OUTPUT.PUT_LINE('Current SCN = ' || l_scn);
END;
/
~~~

Ghi lại SCN trước sự cố nếu hệ thống có quy trình snapshot/incident marker. Current SCN lấy sau sự cố không đại diện cho thời điểm cần phục hồi.

### 6.3. Chuyển timestamp sang SCN

Oracle có hàm ánh xạ timestamp sang SCN:

~~~sql
SELECT TIMESTAMP_TO_SCN(
           SYSTIMESTAMP - INTERVAL '10' MINUTE
       ) AS target_scn
FROM dual;
~~~

SCN_TO_TIMESTAMP thực hiện chiều ngược lại trong phạm vi ánh xạ còn được lưu. Ánh xạ timestamp/SCN có độ phân giải và thời gian lưu hữu hạn; không coi nó là phép đổi chính xác tuyệt đối cho mọi timestamp cũ.

~~~sql
SELECT SCN_TO_TIMESTAMP(123456789)
FROM dual;
~~~

### 6.4. Khi nào nên chọn SCN?

SCN phù hợp khi:
- Cần flashback nhiều bảng về cùng một điểm.
- Cần đối chiếu với transaction/redo/incident record.
- Muốn ghi lại mốc phục hồi rõ ràng.
- Muốn tránh nhầm timezone hoặc độ chính xác timestamp.

Timestamp tiện đọc nhưng SCN thường thuận tiện hơn cho consistency giữa các object.

## 7. Flashback nhiều bảng và quan hệ phụ thuộc

### 7.1. Vì sao không nên flashback từng bảng tùy ý?

Giả sử có hai bảng:
- DEPARTMENTS là bảng cha.
- EMPLOYEES chứa DEPARTMENT_ID tham chiếu DEPARTMENTS.

Một sự cố xóa phòng ban và nhân viên có thể tác động cả hai bảng. Nếu chỉ flashback EMPLOYEES hoặc chỉ flashback DEPARTMENTS, trạng thái hiện tại của bảng còn lại có thể không phù hợp với trạng thái được khôi phục.

Ví dụ:
- EMPLOYEES được đưa về thời điểm có DEPARTMENT_ID = 50.
- DEPARTMENTS hiện tại không còn department_id = 50.
- Khóa ngoại có thể bị vi phạm hoặc trạng thái nghiệp vụ không nhất quán.

Cần xác định toàn bộ tập bảng phụ thuộc và đưa chúng về cùng SCN khi cần.

### 7.2. Flashback nhiều bảng cùng SCN

Oracle hỗ trợ flashback nhiều bảng trong một câu lệnh khi các điều kiện và giới hạn tương ứng được đáp ứng:

~~~sql
FLASHBACK TABLE hr.departments,
                hr.employees
TO SCN 123456789;
~~~

Ví dụ này đưa cả hai bảng về cùng một SCN. Thay danh sách bảng và SCN theo hệ thống thực tế. Xác nhận tất cả bảng có row movement enabled và đủ quyền.

### 7.3. Foreign key và referential integrity

Trước khi flashback bảng có quan hệ khóa ngoại:
1. Liệt kê bảng cha và bảng con.
2. Xác định foreign key enabled/validated hay không.
3. Xác định các thay đổi sau target SCN.
4. Chọn tập bảng cần flashback đồng thời.
5. Dùng cùng SCN cho các bảng liên quan.
6. Kiểm tra constraint sau thao tác.

Không disable constraint chỉ để câu lệnh chạy qua rồi bỏ quên việc validate lại. Nếu cần disable tạm thời theo phương án được phê duyệt, phải có kế hoạch kiểm tra dữ liệu và enable/validate lại.

### 7.4. Xem foreign key dependency

~~~sql
SELECT c.owner,
       c.table_name,
       c.constraint_name,
       c.r_owner,
       p.table_name AS parent_table,
       c.status,
       c.validated
FROM   dba_constraints c
JOIN   dba_constraints p
       ON p.owner = c.r_owner
      AND p.constraint_name = c.r_constraint_name
WHERE  c.constraint_type = 'R'
AND    (c.owner = 'HR' OR c.r_owner = 'HR')
ORDER  BY c.owner, c.table_name, c.constraint_name;
~~~

Truy vấn này tìm foreign key của các bảng trong HR và các bảng tham chiếu tới HR. Với hệ thống nhiều schema, mở rộng phạm vi theo object dependency thực tế.

### 7.5. Xem constraint của một bảng

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       r_owner,
       r_constraint_name
FROM   dba_constraints
WHERE  owner = 'HR'
AND    table_name IN ('DEPARTMENTS', 'EMPLOYEES')
ORDER  BY table_name, constraint_type, constraint_name;
~~~

Trước và sau flashback, lưu metadata constraint để đối chiếu. Constraint không phải dữ liệu hàng và không tự quay về định nghĩa cũ bằng Flashback Table.

### 7.6. Self-referencing foreign key

Một bảng có thể tham chiếu chính nó, ví dụ EMPLOYEES.MANAGER_ID tham chiếu EMPLOYEE_ID. Khi khôi phục các hàng, quan hệ cha-con nội bộ trong cùng bảng cần nhất quán tại target SCN.

Với self-reference, flashback toàn bộ bảng về cùng SCN thường là phạm vi đúng hơn so với cố khôi phục một nhóm hàng riêng. Kiểm tra constraint sau khi hoàn tất.

### 7.7. Quan hệ ngoài database

Flashback Table không đảo ngược:
- Message đã gửi sang queue hoặc hệ thống khác.
- Email/notification đã gửi.
- API call sang service bên ngoài.
- File đã ghi ra filesystem.
- Cache hoặc search index ở hệ thống khác.
- Bản sao dữ liệu đã xuất sang data warehouse.

Sau flashback, cần reconciliation hoặc replay/compensation ở tầng ứng dụng. Database state có thể quay lại nhưng side effect ngoài database vẫn tồn tại.

## 8. Trigger, index và các object phụ thuộc

### 8.1. Trigger trong quá trình flashback

Trigger có thể tạo thêm thay đổi khi DML diễn ra. Nếu trigger chạy trong lúc flashback, nó có thể tạo side effect ngoài ý muốn hoặc làm thay đổi dữ liệu khác.

Cú pháp Flashback Table có tùy chọn ENABLE TRIGGERS. Theo mặc định, trigger không được kích hoạt trong quá trình Flashback Table; chỉ dùng ENABLE TRIGGERS khi đã xác định trigger cần chạy và hiểu đầy đủ side effect.

Ví dụ:

~~~sql
FLASHBACK TABLE hr.employees
TO SCN 123456789
ENABLE TRIGGERS;
~~~

Nếu không có lý do nghiệp vụ cụ thể, không bật trigger trong thao tác phục hồi. Sau khi flashback, kiểm tra trạng thái trigger và hành vi ứng dụng.

### 8.2. Kiểm tra trigger

~~~sql
SELECT owner,
       trigger_name,
       table_owner,
       table_name,
       status,
       triggering_event,
       trigger_type
FROM   dba_triggers
WHERE  table_owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY trigger_name;
~~~

Kiểm tra trigger có ghi audit nghiệp vụ, cập nhật bảng khác, enqueue message hoặc gọi package ngoài hay không. Đọc mã trigger và các dependency liên quan trước khi chọn ENABLE TRIGGERS.

### 8.3. Index được duy trì

Oracle duy trì các index liên quan trong quá trình Flashback Table để index phản ánh trạng thái hàng sau phục hồi. Thông thường không cần rebuild toàn bộ index chỉ vì đã flashback.

Tuy vậy, cần xác nhận:
- Index có ở trạng thái VALID không.
- Index partition có trạng thái hợp lệ không.
- Có index unusable từ trước sự cố không.
- Có function-based/domain index hoặc cấu trúc đặc biệt cần kiểm tra riêng không.

### 8.4. Kiểm tra index

~~~sql
SELECT owner,
       index_name,
       table_owner,
       table_name,
       status,
       visibility,
       uniqueness
FROM   dba_indexes
WHERE  table_owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY index_name;
~~~

Với partitioned index, kiểm tra thêm DBA_IND_PARTITIONS và DBA_IND_SUBPARTITIONS. Không chạy rebuild nếu chưa có bằng chứng index invalid hoặc kế hoạch bảo trì cần thiết.

### 8.5. Grants, synonym và view

Flashback Table khôi phục hàng, không phải cơ chế khôi phục toàn bộ metadata object. Các grants, synonym, view và định nghĩa trigger/index không được đưa về phiên bản cũ chỉ bởi thao tác flashback dữ liệu.

Nếu một DDL đã thay đổi object definition sau target time, Flashback Table có thể không thực hiện được. Nếu chỉ có thay đổi dữ liệu, các metadata object hiện tại thường vẫn được giữ; vẫn cần xác nhận object dependencies trước khi mở lại ứng dụng.

### 8.6. Materialized view

Materialized view phụ thuộc vào bảng nguồn có thể trở thành stale sau khi Flashback Table thay đổi dữ liệu. Kiểm tra trạng thái refresh và refresh theo chiến lược phù hợp trước khi consumer sử dụng lại.

~~~sql
SELECT owner,
       mview_name,
       staleness,
       last_refresh_type,
       last_refresh_date
FROM   dba_mviews
WHERE  owner = 'REPORTING'
ORDER  BY mview_name;
~~~

Các cột và quyền xem tùy phiên bản. Không giả định materialized view tự được đồng bộ về cùng trạng thái chỉ vì bảng base đã flashback.

### 8.7. Constraint và trigger không phải side effect duy nhất

Một bảng có thể liên quan:
- Foreign key và check constraint.
- Trigger.
- Materialized view/log.
- CDC/replication/GoldenGate.
- Change data capture hoặc downstream ETL.
- Application cache và search index.
- Audit policy và application log.

Lập dependency inventory trước khi flashback, sau đó xác nhận từng hệ thống đã đồng bộ.

## 9. Giới hạn của FLASHBACK TABLE

### 9.1. DDL và thay đổi cấu trúc

Flashback Table không phải DDL time travel. Nếu cấu trúc bảng thay đổi kể từ target time, Oracle có thể không thể diễn giải undo cũ theo định nghĩa hiện tại.

Ví dụ các thao tác cần đặc biệt lưu ý:
- TRUNCATE TABLE.
- DROP TABLE.
- Thay đổi định nghĩa cột.
- Một số thao tác MOVE/REDEFINITION hoặc thay đổi cấu trúc segment.
- Thay đổi partition/object làm ảnh hưởng metadata cần thiết.

Lỗi ORA-01466 thường liên quan định nghĩa bảng đã thay đổi trong khoảng cần đọc. Kiểm tra DDL history/audit/deployment log và chọn phương án phục hồi đúng.

### 9.2. Truncate không giống DELETE

DELETE tạo undo cho các hàng bị xóa, vì vậy có thể flashback nếu undo còn đủ.

TRUNCATE là DDL, không tạo undo row-by-row theo cách DELETE. Không thể coi FLASHBACK TABLE là cách hoàn tác TRUNCATE. Cần dùng Flashback Drop nếu object bị drop, Flashback Database hoặc backup/recovery theo tình huống.

### 9.3. Table đã bị DROP

FLASHBACK TABLE ... TO TIMESTAMP/SCN không phải cú pháp phục hồi object đã drop. Nếu table còn trong recycle bin, xem Flashback Drop:

~~~sql
FLASHBACK TABLE hr.orders
TO BEFORE DROP;
~~~

Flashback Drop có điều kiện riêng, phụ thuộc recycle bin, tên object và dung lượng. Nếu object đã bị purge hoặc recycle bin không lưu, dùng backup/recovery.

### 9.4. Undo không còn

Nếu target time vượt quá undo còn khả dụng, có thể gặp lỗi như ORA-01555 hoặc ORA-08180. Tăng UNDO_RETENTION sau khi sự cố đã xảy ra không thể tạo lại undo record đã bị tái sử dụng.

Đối với nhu cầu phục hồi dài hơn, cần thiết kế backup, Flashback Database, guaranteed restore point hoặc archive/replication theo yêu cầu RPO.

### 9.5. Bảng thuộc cluster hoặc loại object đặc biệt

Một số loại bảng/object có giới hạn Flashback Table. Kiểm tra Restrictions trong Oracle Database 19c SQL Language Reference cho chính loại object đang xử lý, đặc biệt với clustered table, cấu trúc nested/object đặc biệt, remote object hoặc bảng có quan hệ phức tạp.

Không suy rộng khả năng từ một bảng heap đơn giản sang mọi loại bảng trong database.

### 9.6. Lock và transaction đang hoạt động

Flashback Table cần khóa các bảng được khôi phục để bảo đảm thao tác nhất quán. Session đang giữ DML lock hoặc workload liên tục cập nhật có thể làm thao tác chờ hoặc thất bại.

Trước khi chạy:
- Quiesce hoặc tạm dừng writer của ứng dụng nếu có thể.
- Xác định transaction đang mở.
- Thông báo consumer và batch job.
- Chọn maintenance window.
- Theo dõi lock/wait.
- Không kill session tùy tiện.

### 9.7. Phạm vi nhất quán

Flashback Table khôi phục bảng trong database. Nó không tự đưa:
- Sequence về giá trị cũ.
- Audit trail về quá khứ.
- Scheduler job hoặc external job về trạng thái cũ.
- File và object storage về thời điểm cũ.
- Cache/queue/service khác về cùng SCN.

Các thành phần này cần được xử lý theo quy trình reconciliation riêng.

## 10. Ví dụ thực hành đầy đủ

### 10.1. Tạo bảng demo

~~~sql
CREATE TABLE flash_demo_accounts (
    account_id NUMBER PRIMARY KEY,
    owner_name VARCHAR2(100) NOT NULL,
    balance    NUMBER(12,2) NOT NULL
);
~~~

### 10.2. Nạp dữ liệu ban đầu

~~~sql
INSERT INTO flash_demo_accounts VALUES (1, 'An', 1000);
INSERT INTO flash_demo_accounts VALUES (2, 'Binh', 2000);
INSERT INTO flash_demo_accounts VALUES (3, 'Chi', 3000);
COMMIT;
~~~

### 10.3. Ghi lại SCN trước thay đổi

~~~sql
SELECT current_scn
FROM   v$database;
~~~

Ghi kết quả SCN ra incident/test note. Giả sử SCN thu được là 123456789; đây chỉ là giá trị minh họa.

### 10.4. Bật row movement

~~~sql
ALTER TABLE flash_demo_accounts ENABLE ROW MOVEMENT;
~~~

### 10.5. Thực hiện thay đổi sai

~~~sql
UPDATE flash_demo_accounts
SET    balance = balance + 50000;

COMMIT;
~~~

Kiểm tra:

~~~sql
SELECT *
FROM   flash_demo_accounts
ORDER  BY account_id;
~~~

### 10.6. Flashback về SCN đã ghi

~~~sql
FLASHBACK TABLE flash_demo_accounts
TO SCN 123456789;
~~~

Thay SCN minh họa bằng giá trị thực đã ghi trước thay đổi. Bảng phải đáp ứng điều kiện quyền, undo và không có DDL không tương thích.

### 10.7. Xác nhận dữ liệu

~~~sql
SELECT *
FROM   flash_demo_accounts
ORDER  BY account_id;
~~~

Đối chiếu balance với snapshot/test baseline. Kiểm tra số hàng, constraint và ứng dụng trước khi mở lại traffic.

### 10.8. Dọn bảng demo

~~~sql
DROP TABLE flash_demo_accounts PURGE;
~~~

Chỉ chạy trong schema test sau khi không còn cần dữ liệu. PURGE loại object khỏi recycle bin nên không dùng tùy tiện trên bảng thật.

## 11. Quy trình phục hồi một bảng trong production

### Bước 1 — Khoanh vùng sự cố

Xác định:
- Bảng và schema bị ảnh hưởng.
- Thời điểm bắt đầu thay đổi sai.
- SQL/transaction gây thay đổi.
- Các bảng liên quan.
- Có DDL, TRUNCATE hoặc DROP trong khoảng này không.
- Ứng dụng nào đang ghi dữ liệu.

Không chọn target time chỉ từ thời điểm người dùng báo lỗi. Cần xác định trạng thái cuối cùng còn đúng.

### Bước 2 — Bảo toàn bằng chứng và dữ liệu hiện tại

Trước khi phục hồi:
- Ghi SQL_ID, transaction, audit record và thời điểm.
- Export/snapshot dữ liệu hiện tại nếu cần đối chiếu.
- Ghi current SCN.
- Lưu constraint/index/trigger metadata.
- Xác nhận backup/recovery point.
- Ghi lại số hàng và các khóa nghiệp vụ quan trọng.

Snapshot trước khi flashback giúp so sánh và tái tạo những thay đổi hợp lệ phát sinh sau target time nếu cần.

### Bước 3 — Xác định target SCN/time

Dùng audit trail, application log, transaction log hoặc snapshot để xác định mốc. Nếu có thể, dùng SCN cụ thể. Kiểm tra timezone nếu dùng timestamp.

### Bước 4 — Kiểm tra undo và khả năng flashback

Xem UNDO_RETENTION, V$UNDOSTAT, undo tablespace và workload. Nếu target vượt undo availability, dừng phương án Flashback Table và đánh giá backup/Flashback Database.

### Bước 5 — Kiểm tra row movement và quyền

Xác nhận ROW_MOVEMENT = ENABLED, quyền FLASHBACK và object privileges. Ghi nhận trạng thái ban đầu để khôi phục nếu cần.

### Bước 6 — Kiểm tra dependency

Lập danh sách:
- Parent/child FK.
- Self-referencing FK.
- Trigger.
- Index.
- Materialized view.
- Replication/CDC.
- Application cache/queue.
- Các hệ thống downstream.

Chọn tất cả bảng cần flashback về cùng SCN nếu cần giữ referential integrity.

### Bước 7 — Dừng hoặc kiểm soát writer

Quiesce writer, batch và service có thể thay đổi bảng trong khi phục hồi. Xác nhận transaction đã hoàn tất hoặc được xử lý theo runbook.

### Bước 8 — Thực hiện flashback

Chạy một câu lệnh cho tập bảng được phê duyệt, dùng cùng SCN. Theo dõi thời gian, lock, redo, undo và alert log.

### Bước 9 — Validation

Kiểm tra:
- Số hàng và các aggregate quan trọng.
- Khóa chính và foreign key.
- Check constraint.
- Index status.
- Trigger status và side effect.
- Materialized view staleness.
- Audit trail.
- Replication/CDC.
- Application smoke test.

### Bước 10 — Reconcile thay đổi hợp lệ

Những thay đổi hợp lệ sau target time cũng bị loại khỏi trạng thái bảng được khôi phục. Dùng snapshot/audit/application log để xác định phần cần replay hoặc nhập lại. Không copy dữ liệu trở lại một cách mù quáng vì có thể tái tạo chính lỗi ban đầu.

### Bước 11 — Mở lại ứng dụng

Chỉ mở writer sau khi:
- Validation đạt.
- Referential integrity hợp lệ.
- Consumer/downstream đã đồng bộ.
- Application owner chấp nhận kết quả.
- Monitoring và alert được theo dõi.

### Bước 12 — Ghi nhận incident

Lưu target SCN, thời điểm, lệnh đã chạy, người phê duyệt, kết quả validation, dữ liệu phải reconcile và các thay đổi cấu hình như row movement.

## 12. Lỗi thường gặp và cách xử lý

| Lỗi/tình huống | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| ORA-08189 | Row movement chưa bật | Kiểm tra DBA_TABLES.ROW_MOVEMENT và ENABLE ROW MOVEMENT |
| ORA-08180 | Không tìm thấy snapshot/SCN phù hợp | Kiểm tra target time/SCN và undo availability |
| ORA-01555 | Undo cần thiết đã không còn | Xem V$UNDOSTAT, query duration, DML rate và retention |
| ORA-01466 | Định nghĩa bảng đã thay đổi trong khoảng cần đọc | Kiểm tra DDL history, truncate/move/alter và chọn recovery khác |
| ORA-02292 hoặc lỗi constraint | Trạng thái phục hồi vi phạm quan hệ dữ liệu | Flashback các bảng liên quan cùng SCN và xác minh FK |
| ORA-00054 hoặc thao tác chờ lock | Object đang bị session khác khóa | Xem V$LOCK/V$SESSION, quiesce writer theo runbook |
| Insufficient privileges | Thiếu quyền FLASHBACK/object privilege hoặc quyền thao tác bảng | Cấp đúng quyền tối thiểu |
| Flashback không có record mong muốn | Target time sai hoặc undo không còn | Xác minh timestamp/timezone/SCN và các nguồn log khác |
| Materialized view stale | Bảng nguồn thay đổi sau flashback | Kiểm tra DBA_MVIEWS và refresh phù hợp |

Mã lỗi và thông báo cụ thể phụ thuộc thao tác, object và phiên bản. Khi gặp lỗi, lưu toàn bộ stack và SQL, kiểm tra Oracle Database Error Messages thay vì chỉ xử lý theo tên lỗi.

### 12.1. ORA-08189 — row movement chưa bật

Kiểm tra:

~~~sql
SELECT owner,
       table_name,
       row_movement
FROM   dba_tables
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES';
~~~

Nếu được phê duyệt, bật:

~~~sql
ALTER TABLE hr.employees ENABLE ROW MOVEMENT;
~~~

Sau đó xác nhận quyền, target time và undo trước khi chạy lại.

### 12.2. ORA-01555/ORA-08180 — không còn phiên bản cần thiết

Không lặp lại cùng câu lệnh với timestamp cũ hơn. Xác định undo còn khả dụng và cân nhắc backup/Flashback Database. Tăng UNDO_RETENTION sau khi undo đã bị ghi đè không thể khôi phục phiên bản đã mất.

### 12.3. Constraint violation

Nếu bảng có FK:
- Xác định hướng quan hệ parent/child.
- Xem trạng thái constraint.
- Kiểm tra dữ liệu ở target SCN.
- Flashback tập bảng cần thiết về cùng SCN.
- Validate constraint trước khi mở lại ứng dụng.

Không bỏ constraint rồi quên enable lại. Nếu buộc phải disable tạm thời, ghi rõ owner, trạng thái ban đầu và lệnh phục hồi.

## 13. Kiểm tra sau Flashback Table

### 13.1. Kiểm tra số hàng

~~~sql
SELECT COUNT(*) AS row_count
FROM   hr.employees;
~~~

So sánh với baseline, không chỉ dựa trên số hàng vì có thể cùng số lượng nhưng nội dung khác.

### 13.2. Kiểm tra khóa và constraint

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated
FROM   dba_constraints
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY constraint_type, constraint_name;
~~~

Nếu có bảng liên quan, kiểm tra toàn bộ FK chain.

### 13.3. Kiểm tra index

~~~sql
SELECT index_name,
       status,
       visibility,
       uniqueness
FROM   dba_indexes
WHERE  table_owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY index_name;
~~~

Với partitioned index, kiểm tra trạng thái từng partition/subpartition.

### 13.4. Kiểm tra trigger

~~~sql
SELECT trigger_name,
       status,
       triggering_event
FROM   dba_triggers
WHERE  table_owner = 'HR'
AND    table_name = 'EMPLOYEES'
ORDER  BY trigger_name;
~~~

Đảm bảo trigger trở về trạng thái mong muốn và side effect được kiểm soát.

### 13.5. Kiểm tra row movement

~~~sql
SELECT row_movement
FROM   dba_tables
WHERE  owner = 'HR'
AND    table_name = 'EMPLOYEES';
~~~

Quyết định giữ ENABLED hay DISABLED theo thiết kế bảng và các operation sau này. Không thay đổi chỉ để “trả về trạng thái cũ” nếu trạng thái đó không còn phù hợp với workload.

### 13.6. Kiểm tra materialized view và downstream

Kiểm tra staleness/refresh, replication lag, CDC checkpoint, cache invalidation và dữ liệu đã export. Tổ chức reconciliation trước khi khẳng định toàn hệ thống đã nhất quán.

## 14. So sánh Flashback Table với các cơ chế Flashback khác

| Cơ chế | Dữ liệu/đối tượng | Dùng khi | Giới hạn chính |
| --- | --- | --- | --- |
| Flashback Query | Truy vấn phiên bản hàng | Xem dữ liệu quá khứ | Phụ thuộc undo |
| Flashback Versions Query | Lịch sử phiên bản hàng | Điều tra ai/thay đổi gì theo phiên bản có sẵn | Phụ thuộc undo và giới hạn query |
| Flashback Transaction Query | Transaction và SQL thay đổi | Tìm transaction gây lỗi | Cần dữ liệu transaction/undo và quyền phù hợp |
| FLASHBACK TABLE | Một hoặc nhiều bảng | Khôi phục dữ liệu bảng | Row movement, undo, DDL/dependency restrictions |
| Flashback Drop | Table đã DROP | Lấy lại object từ recycle bin | Object còn trong recycle bin |
| Flashback Database | Toàn database | Lùi database về SCN/time | Cần cấu hình flashback logging và storage |
| RMAN | Datafile/database | Recovery từ backup và redo | Cần backup, archive log và quy trình restore |

### 14.1. Flashback Query để xem trước

Trước khi phục hồi, có thể xem dữ liệu quá khứ bằng AS OF TIMESTAMP:

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM   hr.employees
AS OF TIMESTAMP (SYSTIMESTAMP - INTERVAL '10' MINUTE)
WHERE  employee_id = 100;
~~~

Đây là truy vấn chỉ đọc, hữu ích để xác nhận dữ liệu mục tiêu trước khi thực hiện DDL flashback.

### 14.2. Flashback Versions Query để xem lịch sử hàng

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid,
       employee_id,
       salary
FROM   hr.employees
VERSIONS BETWEEN SCN 123456000 AND 123456789
WHERE  employee_id = 100;
~~~

Các pseudo-column VERSIONS_* giúp xem phiên bản hàng trong khoảng SCN còn khả dụng. Có thể dùng để xác định transaction cần điều tra.

### 14.3. Flashback Drop cho object bị xóa

~~~sql
FLASHBACK TABLE hr.employees
TO BEFORE DROP;
~~~

Cú pháp này khác với TO SCN/TIMESTAMP. Nó khôi phục table đã drop còn trong recycle bin, không phải đưa dữ liệu của table đang tồn tại về thời điểm trước.

## 15. Bài thực hành

Các bài thực hành nên chạy trên schema test, có backup/snapshot và dữ liệu không nhạy cảm. Không chạy lệnh phục hồi trên production để thử nghiệm.

### Bài 1 — Bật row movement

Tạo bảng demo, kiểm tra USER_TABLES.ROW_MOVEMENT, bật ENABLE ROW MOVEMENT và kiểm tra lại.

### Bài 2 — So sánh ROWID

Lấy ROWID của các hàng trước và sau một thao tác flashback trong môi trường test. Quan sát vì sao ROWID không nên dùng làm khóa nghiệp vụ.

### Bài 3 — Flashback theo TIMESTAMP

Ghi lại trạng thái bảng, thực hiện UPDATE và COMMIT, sau đó flashback về timestamp trước UPDATE. So sánh dữ liệu.

### Bài 4 — Flashback theo SCN

Lấy SCN từ V$DATABASE hoặc DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER trước khi thay đổi. Thực hiện DML, COMMIT và flashback về SCN đã ghi.

### Bài 5 — Flashback Query trước khi phục hồi

Dùng AS OF TIMESTAMP/SCN để xem trước dữ liệu mục tiêu. Xác nhận các hàng và giá trị cần khôi phục.

### Bài 6 — Kiểm tra giới hạn undo

Chạy DML đủ lớn và giữ một query lâu trong test. Quan sát V$UNDOSTAT, thử đọc phiên bản cũ và ghi lại ảnh hưởng của retention.

### Bài 7 — ORA-08189

Tạo bảng với row movement disabled, thử flashback trong môi trường test và ghi nhận lỗi. Bật row movement rồi thực hiện lại.

### Bài 8 — Quan hệ parent/child

Tạo hai bảng có foreign key. Thay đổi/xóa dữ liệu ở cả hai, sau đó flashback cùng SCN. Kiểm tra referential integrity.

### Bài 9 — Self-referencing FK

Tạo bảng nhân viên có MANAGER_ID tham chiếu EMPLOYEE_ID. Flashback bảng về cùng SCN và xác minh quan hệ.

### Bài 10 — Trigger

Tạo trigger ghi audit nghiệp vụ cho bảng demo. Thực hiện flashback mặc định và thử ENABLE TRIGGERS trong môi trường test. Quan sát side effect và trạng thái trigger.

### Bài 11 — Index và constraint

Tạo primary key, unique index và check constraint. Flashback bảng, sau đó kiểm tra index status và constraint validation.

### Bài 12 — DDL và TRUNCATE

Trong schema test, thử DML rồi flashback; sau đó thử TRUNCATE và đánh giá vì sao Flashback Table không thể được dùng như undo cho DDL.

### Bài 13 — Materialized view

Tạo materialized view phụ thuộc bảng demo, flashback bảng nguồn và kiểm tra trạng thái staleness/refresh.

### Bài 14 — Runbook phục hồi

Lập kế hoạch flashback cho một sự cố UPDATE sai: target SCN, bảng phụ thuộc, undo, row movement, quyền, trigger, validation, reconciliation và rollback/fallback.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Language Reference — FLASHBACK TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FLASHBACK-TABLE.html): cú pháp, điều kiện và restrictions của Flashback Table.
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): ENABLE/DISABLE ROW MOVEMENT.
- [Oracle Database 19c Backup and Recovery User's Guide — Using Flashback Table and Flashback Drop](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/using-flasback-database-and-other-flashback-features.html): tổng quan các tính năng Flashback.
- [Oracle Database 19c Administrator's Guide — Managing Undo](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-undo.html): undo tablespace và retention.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_FLASHBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FLASHBACK.html): SCN và các thao tác flashback hỗ trợ.
- [Oracle Database Reference — DBA_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TABLES.html): ROW_MOVEMENT và metadata bảng.
- [Oracle Database Reference — DBA_CONSTRAINTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_CONSTRAINTS.html): metadata và trạng thái constraint.
- [Oracle Database Reference — DBA_TRIGGERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TRIGGERS.html): trigger status và event.
- [Oracle Database Reference — DBA_MVIEWS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_MVIEWS.html): trạng thái materialized view.

FLASHBACK TABLE có thể khôi phục dữ liệu bảng về một SCN hoặc timestamp khi undo cần thiết còn sẵn và object đáp ứng các điều kiện. Row movement phải được bật, ROWID có thể thay đổi, bảng cha/con cần được xử lý cùng một mốc để giữ quan hệ dữ liệu, còn trigger và các object phụ thuộc phải được kiểm tra trước/sau thao tác. **Hãy xác định đúng target SCN, kiểm kê dependency, kiểm soát writer, flashback trong phạm vi được phê duyệt và xác nhận toàn bộ dữ liệu liên quan trước khi mở lại ứng dụng.**
