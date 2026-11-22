# Khóa ngoại thiếu chỉ mục và tranh chấp trên dữ liệu cha con

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Khóa và đồng thời  
> **Mục tiêu:** Hiểu vai trò của index trên các cột khóa ngoại ở bảng con trong Oracle; giải thích vì sao DELETE hoặc thay đổi khóa được tham chiếu ở bảng cha có thể gây table-level lock trên bảng con khi foreign key không được đánh index; phân biệt TM lock với TX row lock; thiết kế index cho khóa ngoại đơn và khóa ghép; nhận diện blocking, deadlock và chi phí duy trì index; kiểm tra bằng hai session và các view từ điển/hiệu năng.

## 1. Vấn đề: thao tác trên cha có thể ảnh hưởng đến bảng con

Xét hai bảng:

- PARENT: lưu đối tượng cha, mỗi hàng có một khóa duy nhất.
- CHILD: lưu các đối tượng con và tham chiếu đến cha bằng foreign key.

Ví dụ:

~~~sql
CREATE TABLE departments (
    department_id NUMBER CONSTRAINT pk_departments PRIMARY KEY,
    department_name VARCHAR2(100) NOT NULL
);

CREATE TABLE employees (
    employee_id NUMBER CONSTRAINT pk_employees PRIMARY KEY,
    employee_name VARCHAR2(100) NOT NULL,
    department_id NUMBER,
    CONSTRAINT fk_employees_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
);
~~~

PRIMARY KEY của DEPARTMENTS được bảo vệ bởi một unique index. Nhưng Oracle **không tự động tạo index trên cột foreign key ở bảng con** EMPLOYEES.DEPARTMENT_ID.

Điều này không làm foreign key mất hiệu lực. Oracle vẫn kiểm tra tính toàn vẹn tham chiếu khi INSERT/UPDATE hàng con và khi DELETE/thay đổi khóa cha. Tuy nhiên, nếu cột FK ở bảng con không có index phù hợp, một số thao tác trên bảng cha có thể cần kiểm tra bảng con theo cách tốn kém và lấy table-level lock rộng hơn.

Trong hệ thống OLTP, tình huống dễ thấy là:

1. Session A xóa một hàng cha hoặc thay đổi khóa được tham chiếu.
2. Oracle cần bảo đảm không có hàng con vi phạm foreign key.
3. Nếu FK ở bảng con không được đánh index, Oracle có thể lấy TM Share lock trên bảng con trong quá trình kiểm tra.
4. Session B muốn INSERT/UPDATE/DELETE một hàng khác trong bảng con có thể phải chờ, dù hàng đó không liên quan đến cha đang bị xóa.

Đây là lý do index khóa ngoại thường được cân nhắc vì **khả năng đồng thời**, ngoài lợi ích tăng tốc truy vấn JOIN hoặc tìm hàng con.

## 2. Foreign key và hai phía của quan hệ

Một foreign key được khai báo ở bảng con:

~~~sql
ALTER TABLE employees
ADD CONSTRAINT fk_employees_department
FOREIGN KEY (department_id)
REFERENCES departments(department_id);
~~~

Hai phía có vai trò khác nhau:

| Phía | Khóa | Vai trò |
|---|---|---|
| Bảng cha | PRIMARY KEY hoặc UNIQUE key | Xác định duy nhất hàng được tham chiếu |
| Bảng con | FOREIGN KEY | Xác nhận giá trị tham chiếu tồn tại ở cha |

Index ở bảng cha và index ở bảng con phục vụ hai mục tiêu khác nhau:

- Unique index trên khóa cha hỗ trợ tìm hàng cha và bảo vệ tính duy nhất.
- Index trên FK con hỗ trợ tìm nhanh các hàng con theo khóa cha, giảm chi phí kiểm tra tham chiếu và tránh một số table lock rộng.

Không nên nhầm việc đã có primary key index ở bảng cha với việc bảng con đã có index. Tạo PRIMARY KEY ở DEPARTMENTS không tự động tạo index cho EMPLOYEES.DEPARTMENT_ID.

## 3. Vì sao FK không có index có thể gây tranh chấp?

Khi xóa một hàng cha, Oracle phải xác định có hàng con nào đang tham chiếu tới khóa đó hay không. Nếu có hàng con và không khai báo hành động xóa dây chuyền phù hợp, thao tác bị từ chối để bảo vệ referential integrity.

Nếu FK ở bảng con không được index, việc kiểm tra có thể cần quét bảng con. Để bảo đảm không có session khác đồng thời chèn một hàng con tham chiếu đến cha trong lúc Oracle kiểm tra và xóa cha, Oracle có thể lấy TM Share lock trên bảng con.

TM Share lock xung đột với TM Row Exclusive lock mà một DML thông thường trên bảng con cần lấy. Vì vậy một thao tác INSERT/UPDATE/DELETE trên bảng con có thể bị chặn dù nó tác động đến hàng khác.

### 3.1. Tình huống minh họa

Giả sử bảng PARENT có hai hàng:

~~~text
PARENT_ID
---------
1
2
~~~

Bảng CHILD có một hàng tham chiếu parent 2:

~~~text
CHILD_ID | PARENT_ID
---------+----------
101      | 2
~~~

Không có index trên CHILD.PARENT_ID.

Session A chạy:

~~~sql
DELETE FROM parent
WHERE parent_id = 1;
~~~

Parent 1 không có hàng con. Oracle vẫn cần xác minh không có hàng con mới nào tham chiếu đến parent 1 trước khi hoàn tất việc xóa. Trong tình huống FK không được index, thao tác này có thể lấy TM Share lock trên CHILD để bảo vệ việc kiểm tra.

Session B chạy:

~~~sql
UPDATE child
SET child_note = 'checked'
WHERE child_id = 101;
~~~

Dù hàng CHILD_ID = 101 tham chiếu parent 2, UPDATE vẫn cần DML lock trên bảng CHILD. TM lock của A có thể làm B chờ. Đây là tranh chấp ở cấp bảng con, không phải vì A và B cùng sửa một hàng CHILD.

Nếu có index phù hợp trên CHILD.PARENT_ID, Oracle có thể tìm các hàng con bằng index và tránh kiểu table-level lock rộng này trong tình huống thông thường. Các row lock và xung đột thực sự trên cùng dữ liệu vẫn tồn tại.

### 3.2. Không phải mọi DELETE cha đều thành công

Nếu parent 1 có hàng con và FK không có ON DELETE CASCADE hoặc ON DELETE SET NULL, DELETE cha bị từ chối do ràng buộc tham chiếu, thường với:

~~~text
ORA-02292: integrity constraint violated - child record found
~~~

Index FK không thay đổi quy tắc này. Index chỉ hỗ trợ tìm hàng con và giảm một số tranh chấp; nó không cho phép xóa cha đang được tham chiếu.

## 4. TM lock và TX lock: phân biệt đúng loại chờ

Oracle dùng nhiều loại enqueue. Hai loại thường cần phân biệt khi điều tra FK contention:

- **TM enqueue:** khóa ở cấp đối tượng bảng, liên quan đến thao tác DML/DDL và bảo vệ cấu trúc bảng.
- **TX enqueue:** khóa liên quan transaction, thường xuất hiện khi session chờ transaction khác nhả row lock hoặc chờ một tài nguyên liên quan đến transaction.

DML thông thường thường lấy TM Row Exclusive lock trên bảng bị sửa. Ngoài ra, nó khóa các hàng thực sự được thay đổi bằng row-level lock.

### 4.1. Chế độ TM thường gặp

Các mode thường được hiển thị trong V$LOCK.LMODE và REQUEST:

| Mode | Tên thường gọi | Ý nghĩa khái quát |
|---:|---|---|
| 2 | Row Share (RS) | Khóa chia sẻ ở mức bảng |
| 3 | Row Exclusive (RX) | DML thông thường trên bảng |
| 4 | Share (S) | Khóa chia sẻ mạnh hơn, có thể xung đột với DML RX |
| 5 | Share Row Exclusive (SRX) | Kết hợp share và row exclusive |
| 6 | Exclusive (X) | Khóa độc quyền ở cấp bảng |

Trong tình huống FK không có index, TM Share lock trên bảng con có thể xung đột với TM Row Exclusive lock mà Session B cần để thực hiện DML. Cụ thể mode phụ thuộc thao tác và ngữ cảnh; khi điều tra, đọc cả TYPE, LMODE, REQUEST, object và blocker thay vì suy luận từ một cột.

### 4.2. Bảng so sánh

| Hiện tượng | Loại khóa thường liên quan | Phạm vi |
|---|---|---|
| Hai session UPDATE cùng một hàng | TX/row lock | Hàng bị tranh chấp |
| Parent DELETE với child FK không có index | TM lock trên bảng con có thể xuất hiện | Có thể ảnh hưởng DML không liên quan trên bảng con |
| DML thông thường trên bảng | TM Row Exclusive cùng row locks | Bảng ở mức DML và các hàng thực sự sửa |
| DDL xung đột DML | TM/table lock và DDL lock | Đối tượng bảng |
| Deadlock giữa hai transaction | Vòng chờ lock, thường có TX | Nhiều hàng/tài nguyên theo thứ tự khác nhau |

Không gọi mọi tình huống chờ là “row lock”. Nếu event là enq: TM - contention, hãy kiểm tra table enqueue và object. Nếu event là enq: TX - row lock contention, tìm transaction đang giữ hàng hoặc khóa liên quan.

## 5. Tạo index trên cột foreign key

Với quan hệ đơn:

~~~sql
CREATE INDEX ix_employees_department_id
ON employees(department_id);
~~~

Index này cho phép Oracle tìm các hàng EMPLOYEES có DEPARTMENT_ID bằng một khóa cha cụ thể mà không phải quét toàn bộ bảng con trong những đường truy cập phù hợp.

Index FK cũng hữu ích cho các truy vấn:

~~~sql
SELECT e.employee_id,
       e.employee_name
FROM employees e
WHERE e.department_id = :p_department_id;
~~~

và JOIN:

~~~sql
SELECT d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id
WHERE d.department_id = :p_department_id;
~~~

Tuy nhiên, lý do quan trọng trong bài học này là index giúp Oracle kiểm tra quan hệ cha-con và tránh một số table lock rộng khi thao tác trên khóa cha.

### 5.1. Index không bắt buộc để khai báo FK

Oracle cho phép tạo foreign key mà không có index ở bảng con. Constraint vẫn được kiểm tra và dữ liệu không hợp lệ vẫn bị từ chối.

Vì thế:

- FK constraint bảo vệ tính toàn vẹn.
- FK index cải thiện access path và hành vi concurrency trong một số thao tác.
- Hai đối tượng có mục đích khác nhau; một cái không thay thế cái kia.

Không có index FK không có nghĩa dữ liệu sai. Đó là quyết định thiết kế cần đánh giá theo workload, đặc biệt tần suất parent DELETE/key update và mức độ DML đồng thời trên bảng con.

## 6. Khóa ngoại ghép và thứ tự cột index

Giả sử bảng cha có khóa duy nhất ghép TENANT_ID và PARENT_CODE:

~~~sql
CREATE TABLE tenant_parent (
    tenant_id NUMBER NOT NULL,
    parent_code VARCHAR2(30 CHAR) NOT NULL,
    parent_name VARCHAR2(100),
    CONSTRAINT pk_tenant_parent
        PRIMARY KEY (tenant_id, parent_code)
);
~~~

Bảng con:

~~~sql
CREATE TABLE tenant_child (
    child_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    parent_code VARCHAR2(30 CHAR) NOT NULL,
    child_name VARCHAR2(100),
    CONSTRAINT fk_tenant_child_parent
        FOREIGN KEY (tenant_id, parent_code)
        REFERENCES tenant_parent(tenant_id, parent_code)
);
~~~

Một index phù hợp trên FK:

~~~sql
CREATE INDEX ix_tenant_child_parent
ON tenant_child(tenant_id, parent_code);
~~~

Với index ghép, các cột FK nên nằm ở phần đầu (leading columns) của index để database có thể tìm theo toàn bộ khóa cha. Có thể thêm cột khác phía sau nếu workload truy vấn cần:

~~~sql
CREATE INDEX ix_tenant_child_parent_status
ON tenant_child(tenant_id, parent_code, status);
~~~

Một index như:

~~~sql
CREATE INDEX ix_tenant_child_status_parent
ON tenant_child(status, tenant_id, parent_code);
~~~

không có FK columns ở đầu. Nếu truy vấn chỉ lọc theo TENANT_ID và PARENT_CODE, index này thường không có access path thuận lợi như index bắt đầu bằng các cột FK.

Khi thiết kế, cần xét:

- Tất cả cột trong foreign key có được bao phủ không.
- Các cột FK có nằm ở leading prefix không.
- Thứ tự cột có phù hợp predicate và workload không.
- Có index hiện có đã bao phủ cùng prefix chưa.
- Index có trùng lặp với index khác không.

### 6.1. FK là một phần của index lớn hiện có

Không nhất thiết tạo index mới nếu bảng con đã có index mà các cột FK tạo thành leading prefix.

Ví dụ FK là (DEPARTMENT_ID) và đã có:

~~~sql
CREATE INDEX ix_emp_department_status
ON employees(department_id, status);
~~~

Index này đã bắt đầu bằng DEPARTMENT_ID nên có thể phục vụ tìm hàng con theo FK. Trước khi tạo thêm index đơn trên DEPARTMENT_ID, hãy kiểm tra index hiện có và execution plan.

Nếu FK gồm (TENANT_ID, PARENT_CODE), index (TENANT_ID, PARENT_CODE, CREATED_AT) có thể hỗ trợ lookup theo FK. Index (CREATED_AT, TENANT_ID, PARENT_CODE) không có FK ở leading prefix.

## 7. Tác động của từng thao tác cha-con

| Thao tác | Kiểm tra/ảnh hưởng FK | Vai trò của index con |
|---|---|---|
| INSERT hàng con | Xác nhận khóa cha tồn tại | Không thay thế việc kiểm tra cha; index con được duy trì khi insert |
| UPDATE cột FK ở con | Kiểm tra khóa cha mới | Giúp lookup theo FK; index entry cần cập nhật |
| DELETE hàng con | Xóa tham chiếu khỏi tập con | Index entry cần duy trì; hỗ trợ tìm/xóa theo FK |
| DELETE hàng cha | Xác nhận không còn con hoặc áp dụng hành động ON DELETE | Tìm hàng con nhanh và giảm nguy cơ table lock rộng khi FK không index |
| UPDATE khóa được tham chiếu ở cha | Bảo vệ tham chiếu; thường bị từ chối nếu còn con | Hỗ trợ kiểm tra hàng con và giảm tranh chấp |
| DELETE cha với ON DELETE CASCADE | Xóa các hàng con liên quan | Tìm hàng con nhanh; các hàng con vẫn phải bị khóa và xóa |

Oracle không hỗ trợ ON UPDATE CASCADE theo cú pháp foreign key thông thường. Nếu cập nhật khóa cha đang được tham chiếu, thao tác có thể bị từ chối do hàng con còn tồn tại; cần thiết kế thay đổi khóa theo quy trình riêng.

### 7.1. INSERT hàng con

Khi INSERT CHILD với FK value, Oracle phải xác nhận hàng cha tồn tại. Nếu không có cha phù hợp, DML bị từ chối, thường là ORA-02291.

~~~sql
INSERT INTO employees (
    employee_id, employee_name, department_id
)
VALUES (1001, 'An', 9999);
~~~

Nếu department 9999 không tồn tại, constraint FK ngăn INSERT. Index FK ở bảng con không loại bỏ việc kiểm tra cha; nó chủ yếu hỗ trợ tra cứu theo chiều cha sang con và duy trì cấu trúc index.

### 7.2. UPDATE FK ở bảng con

~~~sql
UPDATE employees
SET department_id = 20
WHERE employee_id = 1001;
~~~

Oracle kiểm tra department 20 tồn tại. Vì DEPARTMENT_ID nằm trong index FK, thay đổi giá trị cũng cần duy trì index entry. Index giúp lookup nhưng có thêm chi phí ghi.

### 7.3. DELETE hàng cha không có ON DELETE CASCADE

~~~sql
DELETE FROM departments
WHERE department_id = 10;
~~~

Nếu còn employee tham chiếu department 10, Oracle từ chối xóa để giữ tính toàn vẹn. Index FK giúp tìm hàng con nhanh và giảm table-level lock rộng trong các tình huống thích hợp.

### 7.4. ON DELETE CASCADE

~~~sql
ALTER TABLE employees
DROP CONSTRAINT fk_employees_department;

ALTER TABLE employees
ADD CONSTRAINT fk_employees_department
FOREIGN KEY (department_id)
REFERENCES departments(department_id)
ON DELETE CASCADE;
~~~

Khi xóa department, các employee tham chiếu có thể bị xóa theo. Đây là nhiều thay đổi DML trên bảng con, do đó cần tính đến undo, redo, index maintenance và row lock của các hàng con.

Index FK giúp Oracle tìm các hàng cần cascade hiệu quả hơn. Nó không loại bỏ row locks trên các hàng bị xóa và cũng không bảo đảm không có blocking với transaction đang sửa những hàng đó.

### 7.5. ON DELETE SET NULL

~~~sql
ALTER TABLE employees
DROP CONSTRAINT fk_employees_department;

ALTER TABLE employees
ADD CONSTRAINT fk_employees_department
FOREIGN KEY (department_id)
REFERENCES departments(department_id)
ON DELETE SET NULL;
~~~

Khi xóa department, DEPARTMENT_ID của hàng con được đặt NULL nếu cột cho phép. Các hàng con bị UPDATE nên vẫn có chi phí undo/redo, index maintenance và lock. FK index hỗ trợ xác định tập hàng cần cập nhật.

## 8. Khi nào index FK có giá trị concurrency cao?

Index thường đặc biệt đáng cân nhắc khi:

- Bảng cha thường xuyên có DELETE.
- Khóa được tham chiếu ở cha có thể bị UPDATE theo quy trình nghiệp vụ.
- Bảng con nhận INSERT/UPDATE/DELETE liên tục từ nhiều session.
- Một thao tác parent DML không liên quan đến phần lớn hàng con nhưng có thể gây blocking rộng.
- Bảng con lớn và việc quét toàn bảng để kiểm tra quan hệ tốn kém.
- Có ON DELETE CASCADE/SET NULL trên số lượng hàng con đáng kể.
- Các truy vấn thường lọc/JOIN theo FK.

Index có thể ít giá trị hơn nếu bảng con rất nhỏ, dữ liệu gần như chỉ đọc, parent key không bao giờ bị xóa/thay đổi và workload không có tranh chấp. Tuy nhiên, quyết định phải xét cả khả năng thay đổi yêu cầu nghiệp vụ trong tương lai.

Không áp dụng máy móc “mọi FK đều phải có index”. Hãy đánh giá rủi ro concurrency, chi phí duy trì và workload thật.

## 9. Chi phí của index FK

Index FK không miễn phí. Khi INSERT hàng con, Oracle phải thêm entry. Khi UPDATE FK, phải duy trì entry cũ/mới. Khi DELETE hàng con, phải duy trì việc xóa entry.

| Thao tác bảng con | Chi phí index FK |
|---|---|
| INSERT CHILD | Thêm entry vào index |
| UPDATE cột FK | Thay đổi entry tương ứng |
| UPDATE cột không liên quan FK | Thường không thay entry FK index |
| DELETE CHILD | Duy trì xóa entry |
| Bulk load | Nhiều entry được xây/duy trì; có thể thành chi phí đáng kể |

Index cũng tiêu thụ storage, buffer cache, redo và công việc bảo trì. Với bảng con ghi cực lớn, thêm nhiều index có thể làm throughput INSERT giảm.

### 9.1. Chọn B-tree hay bitmap?

Với bảng OLTP có DML đồng thời, B-tree index là lựa chọn thông dụng cho FK. Bitmap index trên cột FK có thể tạo phạm vi khóa/cạnh tranh rộng khi cập nhật nhiều hàng, đặc biệt khi nhiều session cùng thao tác. Bitmap thường phù hợp hơn với workload phân tích ít DML đồng thời và cần đánh giá kỹ trước khi dùng trên bảng giao dịch.

### 9.2. Tránh index trùng lặp

Nếu đã có index ghép bắt đầu bằng các cột FK, index đơn bổ sung có thể không cần thiết. Nhiều index tương tự làm tăng chi phí ghi và lưu trữ mà không đem lại lợi ích tương xứng.

## 10. Kiểm tra FK nào chưa có index phù hợp

Trước hết, liệt kê foreign key và các cột theo thứ tự:

~~~sql
SELECT c.table_name,
       c.constraint_name,
       cc.position,
       cc.column_name
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.constraint_type = 'R'
ORDER BY c.table_name, c.constraint_name, cc.position;
~~~

Tiếp theo, liệt kê các index và thứ tự cột:

~~~sql
SELECT table_name,
       index_name,
       column_position,
       column_name
FROM user_ind_columns
ORDER BY table_name, index_name, column_position;
~~~

Đối chiếu từng FK với các index trên cùng bảng con. Một index ứng viên nên có toàn bộ cột FK ở leading prefix. Không chỉ nhìn thấy tên cột ở đâu đó trong index; vị trí cột rất quan trọng.

Ví dụ, nếu FK là DEPARTMENT_ID:

- Index (DEPARTMENT_ID) phù hợp.
- Index (DEPARTMENT_ID, STATUS) cũng có leading prefix phù hợp.
- Index (STATUS, DEPARTMENT_ID) không có DEPARTMENT_ID ở leading position.

Nếu cần xem schema khác, DBA có thể dùng DBA_CONSTRAINTS, DBA_CONS_COLUMNS, DBA_INDEXES và DBA_IND_COLUMNS thay cho USER views. Cần chú ý owner, index status, visibility và partitioning khi đánh giá.

### 10.1. Xem index hiện có trên một bảng

~~~sql
SELECT i.index_name,
       i.uniqueness,
       i.status,
       c.column_position,
       c.column_name
FROM user_indexes i
JOIN user_ind_columns c
  ON c.index_name = i.index_name
 AND c.table_name = i.table_name
WHERE i.table_name = 'EMPLOYEES'
ORDER BY i.index_name, c.column_position;
~~~

Tên object trong USER views thường được lưu uppercase nếu tạo không đặt quoted identifier.

### 10.2. Kiểm tra constraint

~~~sql
SELECT constraint_name,
       constraint_type,
       table_name,
       status,
       validated,
       r_constraint_name,
       delete_rule
FROM user_constraints
WHERE table_name IN ('DEPARTMENTS', 'EMPLOYEES')
ORDER BY table_name, constraint_type, constraint_name;
~~~

DELETE_RULE cho biết hành vi xóa theo constraint, ví dụ NO ACTION hoặc CASCADE/SET NULL theo metadata tương ứng. Kiểm tra trạng thái ENABLED/VALIDATED trước khi kết luận mọi dữ liệu hiện có đã được xác thực.

## 11. Theo dõi TM contention và blocker

Khi một DML trên bảng con bị chờ, xem session và event:

~~~sql
SELECT sid,
       serial#,
       username,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       sql_id
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

Nếu event là enq: TM - contention, điều tra table enqueue và object liên quan. Nếu event là enq: TX - row lock contention, tìm transaction đang giữ row lock hoặc tài nguyên TX liên quan.

### 11.1. Xem TM/TX lock

~~~sql
SELECT sid,
       type,
       id1,
       id2,
       lmode,
       request,
       block
FROM v$lock
WHERE type IN ('TM', 'TX')
ORDER BY type, sid;
~~~

Ý nghĩa:

- TYPE: loại enqueue, ví dụ TM hoặc TX.
- ID1/ID2: định danh tài nguyên theo loại lock.
- LMODE: mode session đang giữ.
- REQUEST: mode session đang yêu cầu.
- BLOCK: thông tin session có đang chặn session khác theo cột này.

Với TM lock, ID1 thường liên hệ đến object ID. Có thể đối chiếu với DBA_OBJECTS:

~~~sql
SELECT object_id,
       owner,
       object_name,
       object_type
FROM dba_objects
WHERE object_id = :p_object_id;
~~~

### 11.2. Xem object đang bị khóa

~~~sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
~~~

V$LOCKED_OBJECT hữu ích để xem object-level DML lock; nó không liệt kê từng row lock như một danh sách hàng. Kết hợp V$SESSION, V$LOCK, SQL_ID và blocker chain để tìm nguyên nhân.

Các view V$ và DBA có thể cần quyền SELECT_CATALOG_ROLE hoặc quyền được cấp riêng. Không yêu cầu ứng dụng thường ngày có quyền DBA chỉ để chạy DML.

## 12. Ví dụ hai session: tái hiện tranh chấp

Thực hiện trên schema lab riêng. Mở hai session database độc lập, tắt auto-commit trong công cụ SQL nếu cần để giữ transaction.

### 12.1. Chuẩn bị dữ liệu

~~~sql
CREATE TABLE lab_parent (
    parent_id NUMBER CONSTRAINT pk_lab_parent PRIMARY KEY,
    parent_name VARCHAR2(50)
);

CREATE TABLE lab_child (
    child_id NUMBER CONSTRAINT pk_lab_child PRIMARY KEY,
    parent_id NUMBER NOT NULL,
    child_note VARCHAR2(100),
    CONSTRAINT fk_lab_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES lab_parent(parent_id)
);

INSERT INTO lab_parent VALUES (1, 'Parent 1');
INSERT INTO lab_parent VALUES (2, 'Parent 2');
INSERT INTO lab_child VALUES (101, 2, 'Existing child');
COMMIT;
~~~

Chưa tạo index trên LAB_CHILD.PARENT_ID.

### 12.2. Session A: thao tác trên cha

Chạy trong Session A và chưa commit:

~~~sql
DELETE FROM lab_parent
WHERE parent_id = 1;
~~~

Parent 1 không có hàng con. Oracle vẫn cần bảo vệ việc kiểm tra FK trước khi xóa.

### 12.3. Session B: DML vào hàng con không liên quan

Chạy trong Session B:

~~~sql
UPDATE lab_child
SET child_note = 'Updated by session B'
WHERE child_id = 101;
~~~

Hàng 101 tham chiếu parent 2, không phải parent 1. Khi FK không có index, Session B có thể chờ TM lock trên bảng LAB_CHILD mà Session A giữ trong lúc xử lý parent DELETE.

Trong Session B, kiểm tra V$SESSION để xem event, thời gian chờ và BLOCKING_SESSION. Trong Session A, xem SQL_ID và transaction đang mở.

### 12.4. Kết thúc transaction

Trong Session A:

~~~sql
ROLLBACK;
~~~

Sau khi A rollback, Session B có thể tiếp tục. Kiểm tra kết quả và trạng thái dữ liệu.

### 12.5. Tạo index FK và thử lại

Tạo index:

~~~sql
CREATE INDEX ix_lab_child_parent_id
ON lab_child(parent_id);
~~~

Lặp lại thao tác ở Session A:

~~~sql
DELETE FROM lab_parent
WHERE parent_id = 1;
~~~

Trong Session B, chạy UPDATE trên child 101 như trên. Với index FK phù hợp, kiểu table-level lock rộng do FK không index thường được tránh; DML không liên quan có thể tiếp tục. Vẫn có thể có chờ nếu hai session đụng cùng hàng, cùng parent key, constraint hoặc tài nguyên khác.

Rollback Session A sau thử nghiệm:

~~~sql
ROLLBACK;
~~~

### 12.6. Dọn dữ liệu lab

~~~sql
DROP TABLE lab_child PURGE;
DROP TABLE lab_parent PURGE;
~~~

Chỉ xóa bảng lab do bạn tạo. Không chạy thử nghiệm giữ transaction hoặc DROP trên schema production.

## 13. Deadlock và thứ tự thao tác cha-con

Index FK giảm một kiểu tranh chấp rộng, nhưng không loại bỏ deadlock hoặc mọi lock wait.

Ví dụ hai transaction thao tác khác thứ tự:

- Session A khóa parent rồi cập nhật child.
- Session B khóa child rồi thực hiện thao tác cần parent.

Nếu mỗi session chờ tài nguyên mà session kia giữ, có thể tạo vòng chờ. Oracle phát hiện deadlock và báo ORA-00060.

Giảm rủi ro:

- Chuẩn hóa thứ tự truy cập bảng và hàng trong transaction.
- Giữ transaction ngắn.
- Tránh gọi dịch vụ ngoài hoặc chờ người dùng trong khi giữ lock.
- Thiết kế batch phân vùng theo khóa cha nếu có thể.
- Dùng FK index để tránh table-level lock không cần thiết trong các tình huống phù hợp.
- Điều tra trace deadlock, blocker và SQL thực tế trước khi thay đổi schema.

Không coi việc tạo index FK là giải pháp cho mọi ORA-00060; deadlock còn phụ thuộc thứ tự khóa trên nhiều tài nguyên.

## 14. FK index và hiệu năng truy vấn

Ngoài concurrency, index FK hỗ trợ các truy vấn phổ biến:

### 14.1. Tìm toàn bộ con của một cha

~~~sql
SELECT *
FROM employees
WHERE department_id = :p_department_id;
~~~

### 14.2. JOIN cha-con

~~~sql
SELECT d.department_name,
       COUNT(e.employee_id) AS employee_count
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name;
~~~

### 14.3. DELETE CASCADE

Nếu quan hệ dùng ON DELETE CASCADE, Oracle cần tìm hàng con để xóa. Index FK có thể giảm chi phí tìm tập hàng con, đặc biệt khi bảng con lớn và mỗi cha chỉ có ít con.

Optimizer vẫn có thể chọn full table scan nếu tỷ lệ hàng phù hợp cao hoặc statistics cho thấy đó là phương án rẻ hơn. Index không bảo đảm mọi query đều dùng index.

## 15. Các trường hợp cần cân nhắc đặc biệt

### 15.1. Bảng con nhỏ

Nếu bảng con chỉ có vài chục hàng và ít DML đồng thời, full scan có thể rẻ và tranh chấp không đáng kể. Index mới tạo thêm chi phí duy trì. Hãy đo trước.

### 15.2. Bảng con ghi liên tục

Với bảng con có nhiều INSERT/UPDATE đồng thời, parent DELETE hiếm nhưng FK index có thể tăng chi phí mỗi lần ghi. Cần cân bằng chi phí duy trì index với rủi ro blocking trên bảng con. Trong nhiều hệ thống OLTP, giảm table-wide contention quan trọng hơn chi phí thêm một B-tree index nhỏ, nhưng cần xác nhận bằng workload.

### 15.3. Khóa ngoại ghép

Tạo index chứa tất cả FK columns ở leading prefix. Nếu index hiện có bao phủ đúng prefix, không cần tạo bản sao chỉ vì tên index khác.

### 15.4. Constraint DISABLED hoặc NOVALIDATE

Nếu FK không ENABLED/VALIDATED, semantics kiểm tra dữ liệu có thể khác với constraint đã được xác thực đầy đủ. Không suy luận lock behavior của FK đã disable giống FK enabled. Kiểm tra metadata trước khi điều tra.

### 15.5. Deferred constraint

Constraint DEFERRABLE có thể trì hoãn kiểm tra đến thời điểm phù hợp trong transaction. Điều đó thay đổi thời điểm lỗi xuất hiện nhưng không xóa yêu cầu về toàn vẹn dữ liệu hoặc tự động loại bỏ lock contention. Kiểm tra trạng thái DEFERRABLE/DEFERRED và thiết kế transaction.

### 15.6. Partitioning

Bảng con partitioned có thể dùng local hoặc global index. Index strategy phải phù hợp partition key, FK lookup và thao tác bảo trì partition. Không giả định một local index luôn thay thế được mọi global access path; xem execution plan và yêu cầu integrity của release Oracle đang dùng.

## 16. Quy trình quyết định có tạo index FK không

~~~text
Bảng con có FOREIGN KEY?
          |
          v
Kiểm tra index hiện có
          |
          +-- Có index với toàn bộ FK columns
          |   ở leading prefix?
          |          |
          |          +-- Có --> Đánh giá workload; tránh tạo trùng
          |          |
          |          +-- Không
          v
Bảng cha có DELETE / key update?
Bảng con có DML đồng thời?
Bảng con lớn hoặc có cascade?
          |
          +-- Có --> Ưu tiên đánh giá B-tree index FK
          |
          +-- Không --> Đo lợi ích truy vấn và concurrency
                         so với chi phí duy trì
          |
          v
Tạo index trong cửa sổ phù hợp
          |
          v
Kiểm tra metadata + execution plan
          |
          v
Theo dõi TM/TX waits và DML throughput
~~~

Đây là quy trình đánh giá, không phải quy tắc tạo index tự động cho mọi foreign key.

## 17. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
|---|---|---|
| Chỉ tạo PK index ở bảng cha và nghĩ FK con đã được index | Parent DELETE có thể gây TM contention trên bảng con | Kiểm tra index riêng ở bảng con |
| FK con không có index trong OLTP nhiều session | Parent DML có thể chặn DML không liên quan trên child | Đánh giá B-tree index FK |
| Index FK nằm sau cột không liên quan | Không có leading prefix phù hợp cho lookup FK | Đặt FK columns ở đầu index |
| Tạo thêm index dù đã có composite prefix | Tăng chi phí ghi/storage | Kiểm kê index trước |
| Tưởng FK index cho phép xóa cha có con | Vẫn vi phạm referential integrity | Dùng ON DELETE action nếu đúng nghiệp vụ |
| Tưởng index loại bỏ mọi lock | Row lock và transaction wait vẫn tồn tại | Phân biệt TM với TX và kiểm tra blocker |
| Dùng bitmap FK index cho OLTP ghi đồng thời | Có thể tăng lock contention | Đánh giá B-tree |
| Không index FK có cascade trên bảng con lớn | Tìm và xóa hàng con tốn kém | Index FK và đo cascade |
| Tạo index mà không xét DML overhead | INSERT/UPDATE/DELETE chậm hơn | Đo read/write trade-off |
| Kill session đang chờ mà không tìm blocker | Không xử lý nguyên nhân gốc | Xem blocker chain và transaction owner |

## 18. Checklist triển khai

- [ ] Xác định bảng cha, bảng con và toàn bộ cột foreign key.
- [ ] Kiểm tra FK đang ENABLED/VALIDATED và delete rule.
- [ ] Kiểm tra index hiện có trên bảng con.
- [ ] Xác nhận toàn bộ FK columns nằm trong leading prefix của ít nhất một index phù hợp.
- [ ] Kiểm tra index ghép có phục vụ thêm workload nào và có trùng lặp không.
- [ ] Đánh giá parent DELETE/key update và ON DELETE CASCADE/SET NULL.
- [ ] Đánh giá số lượng DML đồng thời trên bảng con.
- [ ] Đo TM contention và blocker trước/sau nếu có thể.
- [ ] Xác nhận index mới không gây chi phí ghi/storage không chấp nhận được.
- [ ] Kiểm tra execution plan của truy vấn tìm hàng con và cascade.
- [ ] Thử hai session trong schema lab, bao gồm parent DML và child DML không liên quan.
- [ ] Có quy trình tạo/rebuild index phù hợp với môi trường production và phân vùng.

## 19. Ghi nhớ cốt lõi

- Foreign key constraint nằm ở bảng con; primary/unique index ở bảng cha không tự tạo index cho FK con.
- FK constraint bảo vệ tính toàn vẹn; FK index hỗ trợ tìm hàng con và giảm một số table-level lock rộng.
- Khi FK không có index, DELETE hoặc thay đổi khóa được tham chiếu ở bảng cha có thể khiến Oracle lấy TM Share lock trên bảng con trong lúc kiểm tra tham chiếu.
- TM Share lock có thể xung đột với TM Row Exclusive lock của DML khác trên bảng con, kể cả DML vào hàng không liên quan.
- Index phù hợp trên FK thường giúp Oracle tìm hàng con qua B-tree và tránh kiểu tranh chấp rộng đó; nó không loại bỏ row lock, TX wait hoặc mọi blocking.
- Nếu hàng con thực sự tồn tại, DELETE cha vẫn bị từ chối trừ khi hành động ON DELETE cho phép; index không thay đổi quy tắc nghiệp vụ.
- Với FK ghép, đặt toàn bộ FK columns ở leading prefix của index; kiểm tra index hiện có trước khi tạo thêm.
- Index FK có chi phí INSERT/UPDATE/DELETE, redo, storage và bảo trì; chọn dựa trên workload.
- Theo dõi enq: TM - contention và enq: TX - row lock contention riêng biệt để xác định đúng phạm vi tranh chấp.
- Thử nghiệm hai session và đo trước/sau là cách thực tế để xác nhận index có giải quyết bottleneck của hệ thống hay không.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Data concurrency and consistency, locks, transactions và integrity constraints.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing indexes, tables và database objects.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — CREATE INDEX, foreign key constraints, DELETE và referential actions.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Enqueue waits, blocking sessions và execution plans.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — V$LOCK, V$SESSION, V$LOCKED_OBJECT và các view hiệu năng.

Lock mode cụ thể và cách optimizer truy cập dữ liệu phụ thuộc loại DML, constraint, phiên bản Oracle và cấu hình. Đối chiếu tài liệu đúng release, kiểm tra index theo leading columns và tái hiện bằng hai session trên schema lab trước khi thay đổi schema production.

