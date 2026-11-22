# ORA-00001, ORA-02291, ORA-02292 và vi phạm toàn vẹn dữ liệu

Oracle Database dùng các constraint để bảo vệ tính đúng đắn của dữ liệu. Primary key, unique key, foreign key, NOT NULL và CHECK constraint ngăn những trạng thái không hợp lệ đi vào bảng. Khi một câu INSERT, UPDATE hoặc DELETE vi phạm các quy tắc này, Oracle từ chối thao tác và trả lỗi.

Ba lỗi thường gặp khi xử lý quan hệ giữa các bảng:

- **ORA-00001: unique constraint violated.** Giá trị khóa chính hoặc khóa duy nhất bị trùng; lỗi cũng có thể đến từ unique index, kể cả function-based index.
- **ORA-02291: integrity constraint violated - parent key not found.** Hàng con đang INSERT/UPDATE tham chiếu tới khóa cha không tồn tại hoặc chưa nhìn thấy trong transaction.
- **ORA-02292: integrity constraint violated - child record found.** Hàng cha đang DELETE hoặc đổi khóa nhưng vẫn có hàng con tham chiếu.

Đây thường là lỗi dữ liệu/nghiệp vụ hoặc thứ tự transaction, không phải lỗi cần khắc phục bằng cách tắt constraint. Cách xử lý đúng là xác định constraint, tìm hàng liên quan, hiểu transaction và sửa thao tác hoặc dữ liệu theo quy tắc nghiệp vụ.

## 1. Toàn vẹn dữ liệu và constraint

Constraint là quy tắc do database thực thi để bảo đảm dữ liệu thỏa điều kiện. Việc đặt quy tắc tại database giúp mọi ứng dụng, batch job, script và người dùng đều phải tuân theo cùng một chuẩn.

Các loại constraint chính:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| PRIMARY KEY | Định danh duy nhất một hàng, không cho NULL | EMPLOYEE_ID |
| UNIQUE | Không cho phép trùng khóa duy nhất | EMAIL |
| FOREIGN KEY | Giá trị ở bảng con phải tham chiếu khóa hợp lệ ở bảng cha | DEPARTMENT_ID |
| NOT NULL | Cột bắt buộc có giá trị | EMPLOYEE_NAME |
| CHECK | Giá trị phải thỏa biểu thức | SALARY >= 0 |

Ví dụ:

~~~sql
CREATE TABLE departments (
    department_id NUMBER
        CONSTRAINT departments_pk PRIMARY KEY,
    department_name VARCHAR2(100)
        CONSTRAINT departments_name_nn NOT NULL
);

CREATE TABLE employees (
    employee_id NUMBER
        CONSTRAINT employees_pk PRIMARY KEY,
    email VARCHAR2(320)
        CONSTRAINT employees_email_uk UNIQUE,
    department_id NUMBER,
    salary NUMBER(12,2)
        CONSTRAINT employees_salary_ck CHECK (salary >= 0),
    CONSTRAINT employees_department_fk
        FOREIGN KEY (department_id)
        REFERENCES departments (department_id)
);
~~~

Trong ví dụ:

- EMPLOYEES_PK bảo đảm mỗi nhân viên có một employee_id duy nhất.
- EMPLOYEES_EMAIL_UK ngăn hai hàng có cùng email theo quy tắc UNIQUE của Oracle.
- EMPLOYEES_DEPARTMENT_FK bảo đảm department_id khác NULL phải tham chiếu một phòng ban hợp lệ.
- EMPLOYEES_SALARY_CK ngăn mức lương âm.

## 2. ORA-00001: unique constraint violated

ORA-00001 xuất hiện khi INSERT hoặc UPDATE tạo ra giá trị khóa trùng với một hàng đã có trong unique constraint hoặc unique index.

Ví dụ:

~~~sql
INSERT INTO employees (
    employee_id,
    email,
    department_id,
    salary
)
VALUES (
    101,
    'an@example.com',
    10,
    5000
);

INSERT INTO employees (
    employee_id,
    email,
    department_id,
    salary
)
VALUES (
    101,
    'binh@example.com',
    10,
    6000
);
~~~

Nếu EMPLOYEE_ID là primary key, INSERT thứ hai bị từ chối vì 101 đã tồn tại.

### 2.1 Nguyên nhân phổ biến

- INSERT một khóa chính đã tồn tại.
- INSERT một business key đã tồn tại, chẳng hạn email hoặc mã hợp đồng.
- UPDATE nhiều hàng thành cùng một giá trị unique.
- Sequence bị dùng sai, bị reset hoặc ứng dụng tự cung cấp ID trùng.
- Nhiều session cùng tạo một business key trong cùng thời điểm.
- Ứng dụng kiểm tra tồn tại trước rồi INSERT nhưng có transaction khác chèn trước.
- Unique index dùng biểu thức như UPPER(EMAIL), TRIM(CODE) hoặc CASE.
- Dữ liệu có khác biệt chữ hoa/thường hoặc khoảng trắng nhưng được chuẩn hóa về cùng một giá trị bởi index/collation.
- Một MERGE chạy đồng thời với transaction khác và gặp xung đột unique.

### 2.2 Constraint và unique index

Thông báo thường có dạng:

~~~text
ORA-00001: unique constraint (APP.EMPLOYEES_EMAIL_UK) violated
~~~

Trong một số trường hợp, thông báo nhắc đến unique index thay vì constraint. Không nên giả định mọi ORA-00001 đều đến từ primary key. Có thể có:

- Primary key constraint.
- Unique constraint.
- Unique index được tạo độc lập.
- Function-based unique index.

Hãy lấy đúng tên object trong thông báo lỗi rồi tra dictionary.

### 2.3 Tìm constraint gây lỗi

Nếu user đang kết nối đúng schema:

~~~sql
SELECT constraint_name,
       constraint_type,
       table_name,
       status,
       validated,
       deferrable,
       deferred,
       index_name
FROM user_constraints
WHERE constraint_name = UPPER(:constraint_name);
~~~

Nếu constraint thuộc schema khác và user có quyền xem:

~~~sql
SELECT owner,
       constraint_name,
       constraint_type,
       table_name,
       status,
       validated,
       deferrable,
       deferred,
       index_owner,
       index_name
FROM all_constraints
WHERE owner = UPPER(:owner)
  AND constraint_name = UPPER(:constraint_name);
~~~

Các giá trị CONSTRAINT_TYPE thường gặp:

- P: Primary key.
- U: Unique.
- R: Referential integrity/foreign key.
- C: Check constraint; NOT NULL cũng được biểu diễn trong nhóm này ở dictionary.

### 2.4 Tìm các cột thuộc unique constraint

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       column_name,
       position
FROM all_cons_columns
WHERE owner = UPPER(:owner)
  AND constraint_name = UPPER(:constraint_name)
ORDER BY position;
~~~

Nếu thông báo lỗi chỉ ra index độc lập, kiểm tra ALL_INDEXES và ALL_IND_COLUMNS:

~~~sql
SELECT owner,
       index_name,
       table_name,
       uniqueness,
       status
FROM all_indexes
WHERE owner = UPPER(:owner)
  AND index_name = UPPER(:index_name);

SELECT index_owner,
       index_name,
       table_name,
       column_name,
       column_position
FROM all_ind_columns
WHERE index_owner = UPPER(:owner)
  AND index_name = UPPER(:index_name)
ORDER BY column_position;
~~~

Với function-based index, xem biểu thức trong ALL_IND_EXPRESSIONS:

~~~sql
SELECT index_owner,
       index_name,
       column_position,
       column_expression
FROM all_ind_expressions
WHERE index_owner = UPPER(:owner)
  AND index_name = UPPER(:index_name)
ORDER BY column_position;
~~~

### 2.5 Tìm dữ liệu trùng

Giả sử unique constraint trên EMAIL:

~~~sql
SELECT email,
       COUNT(*) AS duplicate_count
FROM employees
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Với khóa ghép:

~~~sql
SELECT company_id,
       external_code,
       COUNT(*) AS duplicate_count
FROM customer_accounts
GROUP BY company_id, external_code
HAVING COUNT(*) > 1;
~~~

Với unique index không phân biệt chữ hoa/thường:

~~~sql
SELECT UPPER(email) AS normalized_email,
       COUNT(*) AS duplicate_count
FROM employees
WHERE email IS NOT NULL
GROUP BY UPPER(email)
HAVING COUNT(*) > 1;
~~~

Điều kiện tìm trùng phải phản ánh đúng định nghĩa index/constraint. Nếu index dùng TRIM, LOWER, NLSSORT hoặc CASE, hãy nhóm theo đúng biểu thức đó.

### 2.6 NULL trong UNIQUE

UNIQUE không giống PRIMARY KEY. Một unique key có thể chứa NULL; primary key thì không cho NULL.

Với unique constraint một cột, Oracle cho phép nhiều hàng có giá trị NULL trong cột đó. Với unique key nhiều cột, cần hiểu cách Oracle xử lý tổ hợp NULL và giá trị không NULL; không dựa vào NULL để biểu diễn một business key tùy ý.

Oracle xem chuỗi rỗng VARCHAR2 là NULL. Vì vậy, dữ liệu ứng dụng gửi chuỗi rỗng có thể có hành vi khác với database khác. Nếu business key bắt buộc, hãy dùng NOT NULL và chuẩn hóa dữ liệu trước khi ghi.

## 3. ORA-02291: parent key not found

ORA-02291 xảy ra khi một hàng con tham chiếu tới khóa cha không tồn tại theo foreign key constraint.

Ví dụ:

~~~sql
INSERT INTO employees (
    employee_id,
    email,
    department_id,
    salary
)
VALUES (
    102,
    'mai@example.com',
    99,
    5500
);
~~~

Nếu DEPARTMENTS không có DEPARTMENT_ID = 99, Oracle từ chối INSERT và trả ORA-02291.

### 3.1 Foreign key hoạt động thế nào?

~~~text
DEPARTMENTS (parent)
--------------------
DEPARTMENT_ID  PK
10
20
30
       |
       | referenced by
       v
EMPLOYEES (child)
-----------------
EMPLOYEE_ID    PK
DEPARTMENT_ID  FK
101             10
102             20
103             99  <-- invalid: parent 99 does not exist
~~~

Foreign key bảo đảm giá trị khóa ngoại ở bảng con khớp với một khóa được tham chiếu ở bảng cha, trừ trường hợp NULL được phép theo quy tắc của foreign key.

### 3.2 Các nguyên nhân phổ biến

- INSERT hàng con trước khi tạo hàng cha trong transaction có constraint kiểm tra ngay.
- UPDATE khóa ngoại sang giá trị không có ở bảng cha.
- Parent row đã bị xóa hoặc chưa được tạo.
- Parent insert ở session khác chưa COMMIT nên session hiện tại chưa nhìn thấy.
- Ứng dụng kết nối nhầm schema, PDB, service hoặc database.
- Dùng nhầm mã hiển thị với khóa nội bộ.
- Composite foreign key được bind sai thứ tự cột.
- Parent key và child key có khác biệt về giá trị sau khi chuẩn hóa.
- Migration import dữ liệu không đúng thứ tự parent-child.

### 3.3 Tìm foreign key gây lỗi

Thông báo thường có dạng:

~~~text
ORA-02291: integrity constraint (APP.EMPLOYEES_DEPARTMENT_FK) violated - parent key not found
~~~

Tra constraint:

~~~sql
SELECT owner,
       constraint_name,
       table_name AS child_table,
       constraint_type,
       r_owner AS parent_owner,
       r_constraint_name AS parent_constraint,
       status,
       validated,
       deferrable,
       deferred
FROM all_constraints
WHERE owner = UPPER(:owner)
  AND constraint_name = UPPER(:constraint_name)
  AND constraint_type = 'R';
~~~

### 3.4 Tìm bảng cha và các cột tham chiếu

Foreign key lưu tên constraint được tham chiếu trong R_OWNER và R_CONSTRAINT_NAME. Join với constraint cha:

~~~sql
SELECT child.owner AS child_owner,
       child.table_name AS child_table,
       child.constraint_name AS foreign_key,
       child_col.column_name AS child_column,
       parent.owner AS parent_owner,
       parent.table_name AS parent_table,
       parent.constraint_name AS parent_key,
       parent_col.column_name AS parent_column,
       child_col.position
FROM all_constraints child
JOIN all_constraints parent
  ON parent.owner = child.r_owner
 AND parent.constraint_name = child.r_constraint_name
JOIN all_cons_columns child_col
  ON child_col.owner = child.owner
 AND child_col.constraint_name = child.constraint_name
JOIN all_cons_columns parent_col
  ON parent_col.owner = parent.owner
 AND parent_col.constraint_name = parent.constraint_name
 AND parent_col.position = child_col.position
WHERE child.owner = UPPER(:child_owner)
  AND child.constraint_name = UPPER(:constraint_name)
  AND child.constraint_type = 'R'
ORDER BY child_col.position;
~~~

Kết quả cho biết cột nào của bảng con tham chiếu cột nào của bảng cha, theo đúng thứ tự của khóa ghép.

### 3.5 Kiểm tra parent row

Với foreign key đơn DEPARTMENT_ID:

~~~sql
SELECT department_id,
       department_name
FROM departments
WHERE department_id = :department_id;
~~~

Nếu không có hàng, cần xác định:

- Mã phòng ban có đúng không?
- Parent row đã được tạo chưa?
- Parent row có bị xóa trong transaction khác không?
- Đang kết nối đúng PDB/service không?
- Có đang kiểm tra đúng schema/table không?

Không tự tạo parent row giả chỉ để làm cho INSERT hàng con chạy qua. Parent phải tồn tại theo nghiệp vụ.

### 3.6 Thứ tự INSERT parent và child

Trong transaction thông thường, tạo parent trước rồi child:

~~~sql
INSERT INTO departments (department_id, department_name)
VALUES (40, 'Research');

INSERT INTO employees (
    employee_id, email, department_id, salary
)
VALUES (
    104, 'lan@example.com', 40, 7000
);

COMMIT;
~~~

Cùng transaction có thể nhìn thấy thay đổi chưa commit của chính transaction đó. Không cần COMMIT parent trước child nếu cả hai được tạo trong cùng transaction và constraint immediate; commit chung giúp tính nguyên tử.

Nếu parent được tạo bởi transaction khác, transaction đó phải commit trước khi transaction con có thể dựa vào parent đã tồn tại.

## 4. ORA-02292: child record found

ORA-02292 xảy ra khi thao tác trên hàng cha bị chặn vì còn hàng con tham chiếu tới hàng đó.

Ví dụ:

~~~sql
DELETE FROM departments
WHERE department_id = 10;
~~~

Nếu còn nhân viên trong EMPLOYEES có DEPARTMENT_ID = 10, Oracle từ chối DELETE và trả ORA-02292.

### 4.1 Vì sao Oracle chặn?

Nếu xóa phòng ban trong khi nhân viên vẫn tham chiếu phòng ban đó, foreign key sẽ trỏ tới một parent key không tồn tại. Database chặn thao tác để giữ tính toàn vẹn tham chiếu.

### 4.2 Nguyên nhân phổ biến

- DELETE parent row khi child rows còn tồn tại.
- UPDATE parent primary/unique key làm child foreign key mất tham chiếu.
- Xóa dữ liệu theo thứ tự parent trước child trong script.
- Import/cleanup chạy sai thứ tự.
- Có bảng con khác mà người thực hiện không biết.
- Child rows nằm trong schema khác.
- Ứng dụng xóa parent nhưng không xử lý quan hệ phụ thuộc.

### 4.3 Tìm child table từ tên constraint

Thông báo thường có dạng:

~~~text
ORA-02292: integrity constraint (APP.EMPLOYEES_DEPARTMENT_FK) violated - child record found
~~~

Tra metadata của foreign key:

~~~sql
SELECT owner,
       table_name AS child_table,
       constraint_name,
       r_owner AS parent_owner,
       r_constraint_name AS parent_constraint,
       delete_rule
FROM all_constraints
WHERE owner = UPPER(:owner)
  AND constraint_name = UPPER(:constraint_name)
  AND constraint_type = 'R';
~~~

Sau đó tìm parent table và cột qua join ALL_CONSTRAINTS/ALL_CONS_COLUMNS ở phần ORA-02291.

### 4.4 Tìm các hàng con đang tham chiếu

~~~sql
SELECT employee_id,
       email,
       department_id
FROM employees
WHERE department_id = :department_id;
~~~

Nếu có hàng trả về, đây là các hàng đang ngăn thao tác xóa parent. Với một parent có nhiều bảng con, phải kiểm tra tất cả foreign key tham chiếu tới parent key đó.

### 4.5 Không xóa child một cách mù quáng

Trước khi xóa child:

- Xác định child có phải dữ liệu lịch sử cần giữ không.
- Kiểm tra quan hệ cháu/chắt ở các bảng sâu hơn.
- Xác định chính sách cascade.
- Kiểm tra trigger và side effect.
- Xác nhận nghiệp vụ cho phép xóa.
- Ghi nhận số hàng dự kiến bị ảnh hưởng.

Nếu child là dữ liệu nghiệp vụ cần giữ, có thể phải archive, soft-delete hoặc chuyển quan hệ theo quy tắc thay vì DELETE.

## 5. So sánh ba lỗi

| Error | Thao tác thường gặp | Vi phạm | Câu hỏi đầu tiên |
|---|---|---|---|
| ORA-00001 | INSERT/UPDATE | Trùng unique/primary key | Khóa nào đang bị trùng? |
| ORA-02291 | INSERT/UPDATE child | Không có parent key | Parent row ở đâu? |
| ORA-02292 | DELETE/UPDATE parent | Còn child row tham chiếu | Bảng con nào đang giữ parent? |

Ví dụ nhanh:

- ORA-00001: hai nhân viên có cùng employee_id.
- ORA-02291: nhân viên tham chiếu department_id không tồn tại.
- ORA-02292: xóa phòng ban vẫn còn nhân viên thuộc phòng ban đó.

## 6. Quy trình chẩn đoán chung

Khi gặp constraint error, đi theo trình tự:

1. Ghi lại toàn bộ error stack, SQL operation và thời điểm.
2. Xác định database, PDB, schema và session/application.
3. Lấy chính xác owner và constraint/index name trong lỗi.
4. Tra ALL_CONSTRAINTS/ALL_CONS_COLUMNS hoặc ALL_INDEXES.
5. Xác định bảng, cột và quan hệ parent-child.
6. Đọc dữ liệu liên quan bằng SELECT.
7. Kiểm tra transaction, commit order và concurrent sessions.
8. Xác định business rule cần giữ.
9. Chọn cách sửa dữ liệu hoặc thay đổi thứ tự DML.
10. Chạy lại trong transaction có thể rollback và kiểm tra kết quả.
11. Commit chỉ sau khi mọi điều kiện nghiệp vụ được thỏa.

Không disable constraint trước khi hiểu lỗi. Tắt constraint có thể cho phép dữ liệu sai đi vào database và tạo lỗi khó sửa hơn về sau.

## 7. Constraint metadata cần biết

Các dictionary views thường dùng:

| View | Phạm vi | Dùng để |
|---|---|---|
| USER_CONSTRAINTS | Schema hiện tại | Constraint do user sở hữu |
| ALL_CONSTRAINTS | Object user được phép thấy | Constraint trong phạm vi truy cập |
| DBA_CONSTRAINTS | Toàn database | DBA inventory và điều tra |
| USER_CONS_COLUMNS | Schema hiện tại | Cột của constraint |
| ALL_CONS_COLUMNS | Object user được phép thấy | Cột constraint |
| DBA_CONS_COLUMNS | Toàn database | Cột constraint toàn database |
| ALL_INDEXES | Index user được phép thấy | Unique index và trạng thái |
| ALL_IND_COLUMNS | Cột index | Thứ tự cột index |
| ALL_IND_EXPRESSIONS | Biểu thức index | Function-based index |

### 7.1 Xem constraint của một bảng

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       delete_rule
FROM all_constraints
WHERE owner = UPPER(:owner)
  AND table_name = UPPER(:table_name)
ORDER BY constraint_type, constraint_name;
~~~

### 7.2 Xem cột của mọi constraint trên bảng

~~~sql
SELECT constraint_name,
       column_name,
       position
FROM all_cons_columns
WHERE owner = UPPER(:owner)
  AND table_name = UPPER(:table_name)
ORDER BY constraint_name, position;
~~~

### 7.3 Xem foreign key trỏ tới bảng cha nào

~~~sql
SELECT fk.owner AS child_owner,
       fk.table_name AS child_table,
       fk.constraint_name AS fk_name,
       pk.owner AS parent_owner,
       pk.table_name AS parent_table,
       pk.constraint_name AS parent_key,
       fk.delete_rule,
       fk.status,
       fk.validated
FROM all_constraints fk
JOIN all_constraints pk
  ON pk.owner = fk.r_owner
 AND pk.constraint_name = fk.r_constraint_name
WHERE fk.constraint_type = 'R'
  AND fk.owner = UPPER(:owner)
  AND fk.table_name = UPPER(:table_name)
ORDER BY fk.constraint_name;
~~~

### 7.4 Tìm tất cả foreign key tham chiếu tới một parent table

~~~sql
SELECT fk.owner AS child_owner,
       fk.table_name AS child_table,
       fk.constraint_name AS foreign_key,
       pk.owner AS parent_owner,
       pk.table_name AS parent_table,
       pk.constraint_name AS parent_key,
       fk.delete_rule
FROM all_constraints fk
JOIN all_constraints pk
  ON pk.owner = fk.r_owner
 AND pk.constraint_name = fk.r_constraint_name
WHERE fk.constraint_type = 'R'
  AND pk.owner = UPPER(:parent_owner)
  AND pk.table_name = UPPER(:parent_table)
ORDER BY fk.owner, fk.table_name, fk.constraint_name;
~~~

Truy vấn này hữu ích trước khi xóa parent hoặc thay đổi khóa cha. Quyền xem ALL_* chỉ bao gồm object user có thể thấy; DBA có thể dùng DBA_CONSTRAINTS để có inventory đầy đủ hơn.

## 8. Phân biệt constraint status và validation

Oracle quản lý trạng thái constraint bằng các thuộc tính như ENABLE/DISABLE và VALIDATE/NOVALIDATE.

| Trạng thái | Ý nghĩa khái quát |
|---|---|
| ENABLE VALIDATE | Dữ liệu hiện có đã được kiểm tra và DML mới phải tuân thủ |
| ENABLE NOVALIDATE | DML mới phải tuân thủ; dữ liệu cũ chưa được xác nhận đầy đủ |
| DISABLE VALIDATE | Constraint không được dùng để kiểm tra DML mới; có các điều kiện riêng về dữ liệu/segment |
| DISABLE NOVALIDATE | Constraint bị tắt và dữ liệu hiện có không được xác nhận |

Đừng suy luận chỉ từ cột STATUS rằng mọi hàng hiện có đều hợp lệ. Xem cả VALIDATED, trạng thái index và cách constraint được tạo/enable.

### 8.1 ENABLE NOVALIDATE

Ví dụ:

~~~sql
ALTER TABLE employees
ENABLE NOVALIDATE CONSTRAINT employees_department_fk;
~~~

Trạng thái này có thể dùng trong một số kế hoạch chuyển đổi dữ liệu: Oracle bắt đầu thực thi constraint cho DML mới nhưng chưa quét xác nhận toàn bộ dữ liệu cũ. Điều đó không làm dữ liệu cũ tự nhiên trở nên hợp lệ.

Sau khi xử lý dữ liệu lịch sử, có thể validate:

~~~sql
ALTER TABLE employees
ENABLE VALIDATE CONSTRAINT employees_department_fk;
~~~

Nếu còn hàng vi phạm, thao tác validate sẽ thất bại. Hãy tìm và sửa các hàng đó trước.

### 8.2 DISABLE constraint

~~~sql
ALTER TABLE employees
DISABLE CONSTRAINT employees_department_fk;
~~~

Tắt constraint có thể cho phép dữ liệu không hợp lệ. Chỉ dùng trong quy trình load/migration được kiểm soát, có bước kiểm tra và enable validate lại. Không tắt constraint để che lỗi ứng dụng.

## 9. Deferrable constraints và thời điểm kiểm tra

Constraint mặc định thường được kiểm tra ngay tại statement. Một số constraint có thể khai báo DEFERRABLE để trì hoãn kiểm tra tới cuối transaction.

Ví dụ:

~~~sql
CREATE TABLE task_items (
    item_id NUMBER,
    parent_item_id NUMBER,
    CONSTRAINT task_items_pk
        PRIMARY KEY (item_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT task_items_parent_fk
        FOREIGN KEY (parent_item_id)
        REFERENCES task_items(item_id)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Với constraint DEFERRABLE, có thể điều khiển thời điểm kiểm tra:

~~~sql
SET CONSTRAINTS task_items_parent_fk DEFERRED;
~~~

Hoặc kiểm tra ngay:

~~~sql
SET CONSTRAINTS task_items_parent_fk IMMEDIATE;
~~~

### 9.1 INITIALLY IMMEDIATE và INITIALLY DEFERRED

- INITIALLY IMMEDIATE: mặc định kiểm tra sau mỗi statement; transaction có thể đổi sang deferred nếu constraint deferrable.
- INITIALLY DEFERRED: mặc định trì hoãn kiểm tra tới cuối transaction.

Chỉ constraint được khai báo DEFERRABLE mới có thể defer. Constraint NOT DEFERRABLE không thể chuyển sang deferred bằng SET CONSTRAINTS.

### 9.2 Vì sao cần deferred?

Ví dụ một bộ dữ liệu có quan hệ tham chiếu vòng hoặc cần tạo nhiều hàng theo thứ tự mà constraint immediate không cho phép. Deferred constraint cho phép các bước trung gian tạm thời chưa thỏa điều kiện, miễn là toàn bộ trạng thái hợp lệ khi kiểm tra cuối transaction.

### 9.3 Lỗi xuất hiện tại COMMIT

Với deferred constraint, INSERT/UPDATE có thể chạy thành công nhưng COMMIT thất bại vì trạng thái cuối transaction vẫn vi phạm constraint.

Do đó, không kết luận thao tác thành công chỉ vì executeUpdate trả số hàng. Cần kiểm tra kết quả COMMIT và xử lý rollback nếu commit bị từ chối.

### 9.4 Kiểm tra thuộc tính

~~~sql
SELECT constraint_name,
       deferrable,
       deferred,
       status,
       validated
FROM user_constraints
WHERE table_name = UPPER(:table_name)
ORDER BY constraint_name;
~~~

Không chuyển mọi constraint sang deferred như một cách tránh lỗi. Điều này thay đổi thời điểm phát hiện vi phạm và có thể khiến lỗi xuất hiện muộn ở cuối transaction.

## 10. ON DELETE CASCADE và ON DELETE SET NULL

Foreign key mặc định ngăn xóa parent nếu còn child tham chiếu. Oracle hỗ trợ các hành vi xóa được khai báo rõ:

- NO ACTION/default: không cho xóa parent nếu còn child tham chiếu.
- ON DELETE CASCADE: xóa child rows liên quan khi xóa parent.
- ON DELETE SET NULL: đặt child foreign key thành NULL khi xóa parent, nếu cột cho phép.

### 10.1 ON DELETE CASCADE

~~~sql
CREATE TABLE order_items (
    order_item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    CONSTRAINT order_items_order_fk
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
        ON DELETE CASCADE
);
~~~

Khi xóa một hàng ORDERS, các ORDER_ITEMS tham chiếu bị xóa tự động trong cùng transaction.

Chỉ dùng CASCADE khi child thực sự không có ý nghĩa độc lập ngoài parent, ví dụ các dòng chi tiết của một đơn hàng trong mô hình phù hợp. Không dùng cascade nếu child là chứng từ, lịch sử hoặc dữ liệu cần giữ theo yêu cầu kiểm toán.

### 10.2 ON DELETE SET NULL

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER,
    CONSTRAINT employees_department_fk
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        ON DELETE SET NULL
);
~~~

Khi xóa department, department_id của employee liên quan được đặt NULL. Cột foreign key phải cho phép NULL và nghiệp vụ phải chấp nhận nhân viên không còn phòng ban.

### 10.3 Oracle không hỗ trợ ON UPDATE CASCADE

Oracle không cung cấp ON UPDATE CASCADE như một hành vi foreign key tiêu chuẩn. Thiết kế tốt thường dùng khóa cha ổn định, chẳng hạn surrogate primary key, và không thay đổi giá trị primary key trong vận hành bình thường.

Nếu bắt buộc đổi khóa cha, phải lập kế hoạch cập nhật dữ liệu con có kiểm soát hoặc dùng mô hình khóa ổn định và business key riêng.

## 11. Index trên foreign key

Oracle tự tạo index cho primary key/unique constraint theo cách triển khai thông thường nếu cần, nhưng không tự động tạo index cho mọi foreign key.

Index foreign key thường hữu ích khi:

- Xóa hoặc cập nhật parent key.
- Join parent-child thường xuyên.
- Tìm child rows theo parent key.
- Tránh full table scan trên bảng con lớn.
- Giảm một số tình huống locking/contention liên quan tới thao tác parent.

Ví dụ:

~~~sql
CREATE INDEX employees_department_ix
ON employees(department_id);
~~~

Index không thay thế foreign key constraint. Nó cải thiện truy cập và có thể giảm chi phí kiểm tra/xóa parent, nhưng tính toàn vẹn vẫn do constraint bảo vệ.

Với composite foreign key, cân nhắc index có thứ tự cột phù hợp với truy vấn và thao tác parent. Đo execution plan và DML overhead trước khi tạo index.

## 12. Khắc phục ORA-00001 an toàn

Một quy trình:

1. Lấy tên constraint/index từ error stack.
2. Tra cột hoặc biểu thức unique key.
3. Query hàng hiện có đang sở hữu giá trị.
4. Xác định giá trị mới có hợp lệ về nghiệp vụ không.
5. Kiểm tra session đồng thời và logic tạo ID.
6. Chọn insert/update/upsert hoặc trả lỗi nghiệp vụ phù hợp.
7. Không xóa hàng cũ chỉ để giải phóng unique key nếu chưa có phê duyệt.

### 12.1 Kiểm tra trước khi INSERT không đủ để chống race condition

Mẫu dễ gặp:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE email = :email;

-- Nếu count = 0 thì INSERT.
~~~

Hai session có thể cùng SELECT thấy count = 0 rồi cùng INSERT. Một session thành công, session còn lại nhận ORA-00001.

Unique constraint vẫn là hàng rào cuối cùng. Ứng dụng cần bắt lỗi duplicate và chuyển thành phản hồi nghiệp vụ, ví dụ “email đã được sử dụng”.

### 12.2 Dùng MERGE không loại bỏ mọi race condition

MERGE tiện cho upsert, nhưng hai session đồng thời xử lý cùng business key vẫn có thể xung đột unique. Ứng dụng cần xử lý tình huống cạnh tranh và retry có điều kiện khi phù hợp.

### 12.3 Sequence và primary key

Sequence thường dùng để cấp ID:

~~~sql
CREATE SEQUENCE employees_seq
START WITH 1
INCREMENT BY 1
CACHE 100;
~~~

~~~sql
INSERT INTO employees (
    employee_id, email, department_id, salary
)
VALUES (
    employees_seq.NEXTVAL, :email, :department_id, :salary
);
~~~

Sequence không đảm bảo số liên tục. Giá trị có thể bị bỏ trống do rollback, cache, instance restart hoặc concurrency. Không dùng việc có gap làm dấu hiệu duplicate.

Nếu vẫn có ORA-00001 khi dùng sequence, kiểm tra:

- Có session/ứng dụng tự gán ID thủ công không?
- Sequence có bị reset thấp hơn dữ liệu hiện tại?
- Có nhiều hệ thống cùng ghi một bảng?
- Có trigger cấp ID khác với ứng dụng?
- Có sequence khác được dùng nhầm?
- Có unique constraint khác ngoài primary key?

### 12.4 Chuẩn hóa business key

Nếu email không phân biệt chữ hoa/thường, thiết kế unique key trên biểu thức chuẩn hóa hoặc dùng collation phù hợp. Ví dụ function-based index:

~~~sql
CREATE UNIQUE INDEX customers_email_uix
ON customers(UPPER(TRIM(email)));
~~~

Trước khi tạo index, tìm dữ liệu trùng theo cùng biểu thức:

~~~sql
SELECT UPPER(TRIM(email)) AS normalized_email,
       COUNT(*) AS duplicate_count
FROM customers
WHERE email IS NOT NULL
GROUP BY UPPER(TRIM(email))
HAVING COUNT(*) > 1;
~~~

## 13. Khắc phục ORA-02291 an toàn

Một quy trình:

1. Xác định foreign key name.
2. Tìm child table, parent table và cột tương ứng.
3. Kiểm tra giá trị foreign key của hàng đang ghi.
4. Xác minh parent row tồn tại trong đúng PDB/schema.
5. Kiểm tra parent transaction đã COMMIT chưa.
6. Kiểm tra thứ tự load dữ liệu.
7. Sửa source data hoặc thứ tự DML.
8. Chạy lại trong transaction và kiểm tra commit.

### 13.1 Load dữ liệu parent trước child

Khi import từ file:

~~~text
1. Load DEPARTMENTS
2. Load EMPLOYEES
3. Validate foreign keys
~~~

Với hệ thống có nhiều tầng quan hệ, xây dựng thứ tự topological dựa trên dependency graph. Bảng cha phải được nạp trước bảng con khi constraint immediate được bật.

### 13.2 Composite foreign key

Giả sử:

~~~sql
CREATE TABLE product_versions (
    product_id NUMBER,
    version_no NUMBER,
    CONSTRAINT product_versions_pk
        PRIMARY KEY (product_id, version_no)
);

CREATE TABLE order_lines (
    order_line_id NUMBER PRIMARY KEY,
    product_id NUMBER,
    version_no NUMBER,
    CONSTRAINT order_lines_product_version_fk
        FOREIGN KEY (product_id, version_no)
        REFERENCES product_versions(product_id, version_no)
);
~~~

Parent phải tồn tại với đúng cả product_id và version_no. Một phần khớp không đủ.

### 13.3 NULL trong foreign key

Với foreign key đơn, NULL không tham chiếu một parent row. Với composite foreign key, Oracle cho phép trường hợp có cột NULL theo quy tắc foreign key của Oracle; nếu nghiệp vụ yêu cầu tất cả cột phải cùng NULL hoặc cùng có giá trị, bổ sung CHECK constraint để thể hiện quy tắc đó.

Ví dụ all-or-none:

~~~sql
ALTER TABLE order_lines ADD CONSTRAINT order_lines_product_pair_ck
CHECK (
    (product_id IS NULL AND version_no IS NULL)
    OR
    (product_id IS NOT NULL AND version_no IS NOT NULL)
);
~~~

## 14. Khắc phục ORA-02292 an toàn

Một quy trình:

1. Xác định foreign key trong thông báo lỗi.
2. Tra child table và parent key.
3. Tìm mọi hàng con đang tham chiếu parent.
4. Xác định child có phải dữ liệu cần lưu không.
5. Kiểm tra các tầng quan hệ phía dưới child.
6. Chọn delete child, cascade, set null, soft delete hoặc giữ parent.
7. Thực hiện theo transaction có thể rollback.
8. Đếm số hàng bị ảnh hưởng và kiểm tra kết quả.

### 14.1 Xóa child trước parent

Nếu nghiệp vụ cho phép xóa toàn bộ chi tiết:

~~~sql
DELETE FROM order_items
WHERE order_id = :order_id;

DELETE FROM orders
WHERE order_id = :order_id;

COMMIT;
~~~

Hai lệnh nằm trong cùng transaction. Nếu lệnh thứ hai thất bại, có thể rollback để khôi phục child rows đã xóa.

### 14.2 Giữ parent, xóa logical

Với dữ liệu tài chính, nhân sự hoặc kiểm toán, thay vì DELETE có thể dùng cột status:

~~~sql
UPDATE departments
SET status = 'INACTIVE',
    closed_at = SYSTIMESTAMP
WHERE department_id = :department_id;
~~~

Đây là soft delete. Cần thiết kế unique key, truy vấn ứng dụng và retention phù hợp để hàng inactive không gây xung đột logic.

### 14.3 Cascade có chủ đích

Chỉ khai báo ON DELETE CASCADE nếu vòng đời child phụ thuộc hoàn toàn vào parent và việc xóa child tự động là yêu cầu nghiệp vụ. Việc xóa cascade có thể tác động nhiều hàng/bảng hơn câu DELETE ban đầu.

## 15. Transaction và concurrency

Constraint được kiểm tra trong bối cảnh transaction. Hai session có thể tương tác khiến một câu lệnh nhìn thấy trạng thái khác với trạng thái mà ứng dụng vừa đọc.

### 15.1 Race condition khi tạo business key

~~~text
Session A                  Session B
---------                  ---------
SELECT email -> none
                           SELECT email -> none
INSERT email
                           INSERT same email
COMMIT
                           ORA-00001
~~~

Đây là hành vi đúng: unique constraint đảm bảo chỉ một hàng sở hữu business key đó.

### 15.2 Parent insert chưa commit

~~~text
Session A                  Session B
---------                  ---------
INSERT parent
                           INSERT child referencing parent
                           (parent chưa commit)
COMMIT
~~~

Session B không thể dựa vào một parent row chưa commit của Session A như một hàng đã tồn tại độc lập. Tùy khóa và thời điểm, thao tác có thể chờ hoặc thất bại khi kiểm tra. Thiết kế transaction cần bảo đảm parent commit trước khi transaction khác phụ thuộc vào nó.

Nếu parent và child cùng thuộc một nghiệp vụ, tốt nhất tạo chúng trong một transaction khi có thể.

### 15.3 Không retry vô hạn constraint errors

ORA-00001, ORA-02291 và ORA-02292 thường là lỗi logic/dữ liệu. Retry ngay cùng câu SQL với cùng dữ liệu sẽ tiếp tục thất bại.

Retry chỉ phù hợp khi ứng dụng đã thay đổi đầu vào hoặc xác định lỗi do race condition tạm thời và có chiến lược đọc lại trạng thái. Mọi retry phải có giới hạn và tính idempotent.

## 16. Xử lý lỗi trong PL/SQL

PL/SQL có predefined exception DUP_VAL_ON_INDEX cho duplicate key.

~~~sql
BEGIN
    INSERT INTO employees (
        employee_id, email, department_id, salary
    )
    VALUES (
        employees_seq.NEXTVAL,
        'an@example.com',
        10,
        5000
    );
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE(
            'Employee key or unique value already exists'
        );
END;
/
~~~

Đối với lỗi foreign key, có thể kiểm tra SQLCODE:

~~~sql
BEGIN
    -- DML statement
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -2291 THEN
            DBMS_OUTPUT.PUT_LINE('Referenced parent key not found');
        ELSIF SQLCODE = -2292 THEN
            DBMS_OUTPUT.PUT_LINE('Child rows still reference parent');
        ELSE
            RAISE;
        END IF;
END;
/
~~~

Ví dụ trên chỉ minh họa phân nhánh. Trong ứng dụng thật, không nuốt lỗi sau khi in DBMS_OUTPUT. Hãy ghi log có correlation ID, trả lỗi nghiệp vụ rõ ràng và rollback khi transaction không thể tiếp tục.

### 16.1 SQLCODE và SQLERRM

- SQLCODE trả mã lỗi số trong exception handler.
- SQLERRM trả thông điệp lỗi.
- DBMS_UTILITY.FORMAT_ERROR_STACK có thể giúp ghi error stack.
- DBMS_UTILITY.FORMAT_ERROR_BACKTRACE giúp xác định dòng PL/SQL phát sinh lỗi.

Ví dụ:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_ERROR_BACKTRACE);
        RAISE;
~~~

Giữ RAISE để lỗi tiếp tục được báo cho caller nếu không có xử lý phục hồi rõ ràng.

## 17. Xử lý lỗi trong Java/JDBC

JDBC biểu diễn lỗi SQL bằng SQLException và các lớp con. Constraint violation thường thuộc nhóm SQLState class 23; Oracle JDBC có vendor error code tương ứng.

Ví dụ:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customers(customer_id, email) VALUES (?, ?)")) {
    ps.setLong(1, customerId);
    ps.setString(2, email);
    ps.executeUpdate();
} catch (SQLIntegrityConstraintViolationException e) {
    connection.rollback();
    int oracleCode = e.getErrorCode();

    if (oracleCode == 1) {
        throw new DuplicateCustomerException(
            "Customer key or email already exists", e);
    }
    throw e;
}
~~~

Tùy driver và cách framework bọc exception, lỗi có thể được trả dưới dạng SQLException hoặc DataAccessException. Có thể cần duyệt chuỗi getNextException/getCause để tìm vendor code gốc.

Không chỉ parse chuỗi thông báo lỗi vì message có thể thay đổi theo ngôn ngữ hoặc driver version. Dùng vendor error code/SQLState và context của operation.

### 17.1 Phân biệt duplicate nào bị trùng

ORA-00001 chỉ cho biết một unique rule bị vi phạm. Ứng dụng cần biết constraint/index tương ứng để trả thông báo đúng:

- Customer ID đã tồn tại.
- Email đã được đăng ký.
- Mã đơn hàng bị trùng.
- Idempotency key đã được xử lý.

Không trả một thông báo chung “database error” nếu có thể ánh xạ sang lỗi nghiệp vụ an toàn.

### 17.2 BatchUpdateException

Khi chạy JDBC batch, constraint error có thể làm batch dừng hoặc trả update counts tùy driver/batch mode. Kiểm tra:

- getUpdateCounts().
- getNextException().
- Transaction state.
- Những hàng nào đã được xử lý trước lỗi.

Không giả định batch luôn atomic ở cấp toàn bộ batch. Dùng transaction và rollback khi cần tất cả-hoặc-không-gì.

## 18. Bulk DML và SAVE EXCEPTIONS

Trong PL/SQL FORALL, SAVE EXCEPTIONS cho phép tiếp tục xử lý các phần tử khác và lưu lỗi theo từng iteration.

~~~sql
DECLARE
    TYPE id_array_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_array_t := id_array_t(101, 102, 103, 104);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        DELETE FROM employees
        WHERE employee_id = l_ids(i);
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -24381 THEN
            FOR i IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
                DBMS_OUTPUT.PUT_LINE(
                    'Index=' ||
                    SQL%BULK_EXCEPTIONS(i).ERROR_INDEX ||
                    ', Code=' ||
                    SQL%BULK_EXCEPTIONS(i).ERROR_CODE
                );
            END LOOP;
        ELSE
            RAISE;
        END IF;
END;
/
~~~

SAVE EXCEPTIONS hữu ích khi xử lý batch lớn và cần ghi nhận lỗi từng hàng. Cần thiết kế commit/rollback rõ ràng: các DML thành công trước exception vẫn thuộc transaction hiện tại và có thể cần rollback nếu yêu cầu toàn bộ batch atomic.

## 19. DML error logging

Oracle hỗ trợ DML error logging qua DBMS_ERRLOG và mệnh đề LOG ERRORS cho một số tình huống DML. Cơ chế này có thể ghi một số lỗi row-level vào error table để xử lý phần dữ liệu lỗi riêng.

Tạo error logging table:

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'EMPLOYEES',
        err_log_table_name => 'ERR$_EMPLOYEES'
    );
END;
/
~~~

Ví dụ:

~~~sql
INSERT INTO employees (
    employee_id, email, department_id, salary
)
SELECT employee_id, email, department_id, salary
FROM employees_stage
LOG ERRORS INTO err$_employees ('IMPORT_BATCH_01')
REJECT LIMIT UNLIMITED;
~~~

Khả năng log từng loại constraint error phụ thuộc statement, loại constraint, chế độ DML và giới hạn của Oracle release. Không giả định mọi lỗi ORA-00001/02291/02292 đều được ghi vào error table. Thử nghiệm với đúng câu SQL và database version trước khi dùng trong quy trình nạp dữ liệu.

Error logging không thay thế kiểm tra dữ liệu nguồn. Sau khi load, cần thống kê lỗi, sửa source rows và chạy lại phần bị từ chối.

## 20. Thiết kế constraint có chủ đích

### 20.1 Đặt tên rõ ràng

Tên constraint nên cho biết bảng và vai trò:

~~~text
EMPLOYEES_PK
EMPLOYEES_EMAIL_UK
EMPLOYEES_DEPARTMENT_FK
EMPLOYEES_SALARY_CK
EMPLOYEES_NAME_NN
~~~

Tên dễ đọc giúp xác định lỗi nhanh hơn so với SYS_C00... do Oracle tự sinh.

### 20.2 Primary key ổn định

Dùng surrogate key như numeric ID hoặc UUID theo chuẩn hệ thống. Tránh thay đổi primary key thường xuyên vì các foreign key phụ thuộc vào nó.

Business key như email, mã khách hàng hoặc số hợp đồng có thể có UNIQUE constraint riêng.

### 20.3 Xác định delete policy

Mỗi quan hệ cần trả lời:

- Có được xóa parent không?
- Child có tồn tại độc lập không?
- Khi xóa parent, child phải cascade, set null, archive hay chặn?
- Có cần soft delete?
- Dữ liệu lịch sử phải giữ bao lâu?

Không chọn CASCADE chỉ vì muốn tránh ORA-02292.

### 20.4 Index foreign key có chọn lọc

Tạo index khi workload cần tìm child theo parent, join hoặc delete/update parent. Đo chi phí ghi thêm và dung lượng index.

## 21. Làm sạch dữ liệu trước khi bật constraint

Khi migration một bảng đã có dữ liệu, việc thêm UNIQUE/PK/FK có thể thất bại nếu dữ liệu hiện tại vi phạm.

### 21.1 Tìm duplicate trước khi thêm UNIQUE

~~~sql
SELECT email,
       COUNT(*) AS row_count
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Với khóa ghép:

~~~sql
SELECT tenant_id,
       external_id,
       COUNT(*) AS row_count
FROM external_customers
GROUP BY tenant_id, external_id
HAVING COUNT(*) > 1;
~~~

### 21.2 Tìm child orphan trước khi thêm FK

~~~sql
SELECT e.employee_id,
       e.department_id
FROM employees e
WHERE e.department_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM departments d
      WHERE d.department_id = e.department_id
  );
~~~

### 21.3 Sửa dữ liệu có kiểm soát

Các lựa chọn:

- Map mã cũ sang parent key đúng.
- Tạo parent row nếu thực sự thiếu theo nghiệp vụ.
- Chuyển child sang trạng thái chờ xử lý.
- Đưa hàng lỗi vào quarantine table.
- Sửa duplicate bằng quy tắc hợp nhất được phê duyệt.
- Loại bỏ hàng test/rác nếu đã xác nhận.

Không tự chọn MIN/MAX hoặc xóa các hàng trùng một cách máy móc. Dữ liệu trùng có thể đại diện hai khách hàng hoặc hai giao dịch khác nhau cần phân biệt.

## 22. Constraint trong import và migration

Khi nạp dữ liệu nhiều bảng:

1. Tạo schema và parent tables.
2. Nạp parent/reference data.
3. Nạp child tables.
4. Xử lý duplicate theo business rule.
5. Validate foreign key và unique constraints.
6. Tạo/rebuild index theo chiến lược đã chọn.
7. Chạy đối soát row count và business totals.

Với Data Pump, có thể dùng metadata/data filters và thứ tự import phù hợp, nhưng không nên dựa vào việc disable mọi constraint nếu không có kế hoạch validate lại.

### 22.1 Tạm hoãn constraint trong migration

Nếu cần disable/defer:

- Ghi rõ constraint nào và lý do.
- Có thời gian bắt đầu/kết thúc.
- Giới hạn quyền thực hiện.
- Giữ log số hàng nạp.
- Chạy truy vấn phát hiện duplicate/orphan.
- Enable VALIDATE trước khi mở ứng dụng ghi.

### 22.2 Constraint chưa validate

ENABLE NOVALIDATE có thể giúp triển khai enforcement cho DML mới trong khi xử lý dữ liệu cũ. Nhưng trạng thái này phải được ghi nhận và có kế hoạch validate. Không coi migration hoàn tất nếu dữ liệu lịch sử còn vi phạm yêu cầu.

## 23. Kiểm tra transaction trước khi commit

Với nghiệp vụ nhiều bảng, gom thao tác liên quan trong một transaction:

~~~sql
SAVEPOINT before_order;

INSERT INTO orders (order_id, customer_id, status)
VALUES (9001, 100, 'NEW');

INSERT INTO order_items (order_item_id, order_id, product_id)
VALUES (1, 9001, 200);

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 200;

-- Kiểm tra số hàng và điều kiện nghiệp vụ.
COMMIT;
~~~

Nếu có lỗi:

~~~sql
ROLLBACK TO before_order;
~~~

hoặc rollback toàn transaction theo thiết kế. Không commit một phần nếu nghiệp vụ yêu cầu tất cả các bảng phải thay đổi cùng nhau.

## 24. Constraint và trigger

Trigger có thể tạo thêm DML hoặc thay đổi giá trị trước/sau thao tác. Một lỗi unique/foreign key có thể xuất phát từ câu lệnh bên trong trigger chứ không phải câu lệnh ngoài mà ứng dụng gửi.

Khi error stack có trigger:

- Kiểm tra trigger trên bảng.
- Xem trigger gọi procedure/package nào.
- Xem DML phụ được thực hiện.
- Kiểm tra autonomous transaction nếu có.
- Xem stack/backtrace đầy đủ.

Không disable trigger ngay khi gặp constraint error. Trước hết xác định trigger có thực hiện đúng business rule không.

## 25. Constraint và partitioning

Trong bảng partitioned, unique constraint có thể chịu giới hạn về cột partition key và kiểu index global/local. Một unique key phải phù hợp với quy tắc partitioning của Oracle.

Khi tạo hoặc thay đổi unique constraint trên bảng partitioned:

- Xác định local/global index.
- Kiểm tra partition key có nằm trong unique key theo yêu cầu.
- Kiểm tra index usability.
- Xem ảnh hưởng partition maintenance.
- Kiểm thử DDL trên đúng release.

Không cố xử lý ORA-00001 bằng cách tạo thêm index trùng lặp khi chưa hiểu index/constraint hiện có.

## 26. Bảo vệ dữ liệu và ghi log lỗi

Log điều tra nên có:

- Error code và constraint name.
- Operation (INSERT/UPDATE/DELETE).
- Table/schema.
- Business correlation ID.
- Transaction/request ID.
- Thời điểm và service.
- Key đã được mask hoặc token hóa theo policy.

Không ghi toàn bộ row payload, password, token, email/số định danh hoặc dữ liệu cá nhân vào log nếu không cần. Dùng correlation ID để tra dữ liệu trong hệ thống có quyền truy cập.

## 27. Ví dụ điều tra end-to-end

Giả sử API tạo nhân viên trả ORA-02291 với constraint APP.EMPLOYEES_DEPARTMENT_FK.

### Bước 1: Xác định quan hệ

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       r_owner,
       r_constraint_name
FROM all_constraints
WHERE owner = 'APP'
  AND constraint_name = 'EMPLOYEES_DEPARTMENT_FK';
~~~

### Bước 2: Xác định parent key

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type
FROM all_constraints
WHERE owner = 'APP'
  AND constraint_name = :parent_constraint;
~~~

### Bước 3: Kiểm tra parent row

~~~sql
SELECT department_id,
       department_name
FROM app.departments
WHERE department_id = :department_id;
~~~

### Bước 4: Kiểm tra request

Đối chiếu department_id trong request với master data. Kiểm tra ứng dụng có dùng mã phòng ban từ tenant hoặc PDB khác hay không.

### Bước 5: Sửa logic

Nếu phòng ban hợp lệ nhưng chưa được tạo, tạo parent qua quy trình nghiệp vụ. Nếu request gửi sai ID, trả validation error cho client. Không disable foreign key.

### Bước 6: Kiểm thử concurrency

Chạy test khi parent được tạo đồng thời bởi transaction khác. Xác nhận transaction boundary và commit order.

## 28. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Tắt unique constraint khi gặp ORA-00001 | Cho phép duplicate | Xác định khóa và sửa dữ liệu/logic |
| Chỉ SELECT trước INSERT | Race condition vẫn tạo duplicate | Giữ UNIQUE constraint và xử lý lỗi |
| Nghĩ ORA-00001 luôn là primary key | Bỏ sót unique index khác | Tra constraint/index name |
| Không kiểm tra function-based index | Không hiểu vì sao hai chuỗi khác nhau bị trùng | Xem ALL_IND_EXPRESSIONS |
| Dùng sequence và giả định không bao giờ trùng | Reset/manual ID có thể gây collision | Kiểm tra sequence và các nguồn ID |
| Tạo child trước parent ở transaction khác | ORA-02291 | Bảo đảm parent commit trước |
| Tạo parent giả để vượt FK | Dữ liệu nghiệp vụ sai | Xác minh master data |
| Xóa parent trước child | ORA-02292 | Xác định delete policy và dependency |
| Bật ON DELETE CASCADE để né lỗi | Xóa lan dữ liệu ngoài dự kiến | Chỉ dùng khi nghiệp vụ yêu cầu |
| Disable FK khi import rồi quên enable | Dữ liệu orphan tồn tại | Validate trước khi hoàn tất |
| ENABLE NOVALIDATE bị coi là VALIDATE | Dữ liệu cũ có thể vẫn sai | Theo dõi VALIDATED và validate |
| Nuốt exception trong PL/SQL | Ứng dụng tưởng thao tác thành công | Log, rollback và RAISE phù hợp |
| Retry constraint error vô hạn | Tăng tải, không sửa nguyên nhân | Retry chỉ khi có điều kiện rõ |
| Không index foreign key trên bảng lớn | Delete parent/join có thể tốn kém | Đánh giá và index khi phù hợp |
| Log toàn bộ row data | Rò rỉ dữ liệu nhạy cảm | Log key đã mask và correlation ID |

## 29. Bài thực hành tự kiểm tra

Thực hiện trong schema lab với dữ liệu giả.

### Bài 1 — ORA-00001 từ primary key

Tạo bảng có primary key, INSERT cùng ID hai lần và ghi nhận constraint name.

### Bài 2 — ORA-00001 từ unique key

Tạo unique constraint trên EMAIL, thử INSERT email trùng và tra USER_CONSTRAINTS.

### Bài 3 — Function-based unique index

Tạo unique index trên UPPER(TRIM(email)). Thử hai email khác chữ hoa/thường hoặc khoảng trắng và giải thích kết quả.

### Bài 4 — Tìm duplicate

Viết GROUP BY/HAVING để tìm dữ liệu trùng trước khi thêm unique constraint.

### Bài 5 — ORA-02291

Tạo child row tham chiếu parent ID không tồn tại. Tra ALL_CONSTRAINTS và ALL_CONS_COLUMNS.

### Bài 6 — Composite foreign key

Tạo parent key ghép và foreign key ghép. Thử đúng/sai thứ tự cột và các trường hợp NULL.

### Bài 7 — ORA-02292

Tạo parent và child, thử DELETE parent. Tìm child rows và xóa theo đúng thứ tự.

### Bài 8 — ON DELETE CASCADE

Tạo bảng lab có cascade. Xóa parent và đếm child trước/sau trong transaction.

### Bài 9 — DEFERRABLE

Tạo constraint DEFERRABLE INITIALLY DEFERRED. Tạo trạng thái trung gian chưa hợp lệ rồi sửa trước COMMIT; thử commit khi vẫn vi phạm.

### Bài 10 — Concurrency

Dùng hai session cùng INSERT một business key. Quan sát một session nhận duplicate và xử lý thành phản hồi nghiệp vụ.

### Bài 11 — JDBC exception

Bắt SQLIntegrityConstraintViolationException/SQLException, đọc SQLState, vendor code và next exception; ánh xạ sang lỗi ứng dụng.

### Bài 12 — Migration validation

Nạp dữ liệu có duplicate/orphan vào staging, sửa dữ liệu và ENABLE VALIDATE constraint.

## 30. Checklist xử lý sự cố

**Thu thập lỗi**

- Có toàn bộ error stack?
- Có owner và constraint/index name?
- Biết SQL operation và bind key?
- Biết database/PDB/service và transaction ID?

**Tra metadata**

- Đã xác định constraint type?
- Đã tìm đúng bảng và cột?
- Với FK đã tìm parent/child table?
- Với unique index đã kiểm tra biểu thức?

**Dữ liệu và transaction**

- Đã kiểm tra duplicate/orphan rows?
- Parent row đã tồn tại và commit?
- Có session concurrent?
- Constraint immediate hay deferred?
- Có trigger tạo DML phụ?

**Khắc phục**

- Cách sửa đúng business rule?
- Có cần xóa/đổi child hay giữ parent?
- Cascade có thực sự được yêu cầu?
- Có thể rollback nếu kiểm tra thất bại?
- Không tắt constraint để che lỗi?

**Sau xử lý**

- Constraint ENABLE và VALIDATED đúng?
- Dữ liệu hiện có hợp lệ?
- Có test concurrency?
- Log có đủ context nhưng không lộ dữ liệu nhạy cảm?
- Có metric để phát hiện lỗi lặp lại?

## 31. Ghi nhớ

| Mã lỗi/khái niệm | Điều cần nhớ |
|---|---|
| ORA-00001 | Vi phạm unique constraint/index |
| ORA-02291 | Child tham chiếu parent key không tồn tại |
| ORA-02292 | Parent bị chặn vì còn child tham chiếu |
| PRIMARY KEY | Duy nhất và NOT NULL |
| UNIQUE | Duy nhất theo key/index, có quy tắc NULL riêng |
| FOREIGN KEY | Bảo vệ quan hệ parent-child |
| USER_CONSTRAINTS | Constraint của schema hiện tại |
| ALL_CONSTRAINTS | Constraint user được phép xem |
| ALL_CONS_COLUMNS | Cột của constraint |
| ALL_IND_EXPRESSIONS | Biểu thức function-based index |
| ENABLE VALIDATE | Constraint được bật và dữ liệu đã validate |
| ENABLE NOVALIDATE | DML mới được kiểm tra, dữ liệu cũ chưa được xác nhận |
| DEFERRABLE | Cho phép trì hoãn kiểm tra constraint |
| SET CONSTRAINTS | Đổi thời điểm kiểm tra constraint deferrable |
| ON DELETE CASCADE | Xóa child tự động khi xóa parent |
| ON DELETE SET NULL | Đặt FK của child thành NULL khi xóa parent |
| SAVE EXCEPTIONS | Thu thập lỗi từng iteration của FORALL |
| DBMS_ERRLOG | Ghi một số lỗi DML row-level vào error table |
| SQLIntegrityConstraintViolationException | Nhóm exception JDBC cho vi phạm integrity |

ORA-00001 cho biết một giá trị unique bị trùng; hãy tra đúng constraint/index và các cột hoặc biểu thức tạo khóa. ORA-02291 cho biết hàng con không tìm thấy parent hợp lệ; kiểm tra foreign key, dữ liệu cha và thứ tự commit. ORA-02292 cho biết vẫn còn hàng con tham chiếu khi xóa hoặc đổi khóa cha; tìm child table và áp dụng delete policy của nghiệp vụ. Dùng dictionary views để xác định quan hệ thật, giữ constraint làm hàng rào toàn vẹn và xử lý transaction/concurrency đúng cách. Chỉ dùng cascade, deferred constraint hoặc disable/enable trong kế hoạch có kiểm soát, có validate và đối soát dữ liệu sau cùng.
