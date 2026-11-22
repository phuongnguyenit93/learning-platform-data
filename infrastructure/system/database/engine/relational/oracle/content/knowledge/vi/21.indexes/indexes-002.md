# Unique/nonunique index và quan hệ với ràng buộc trong Oracle

Trong Oracle Database, **index** và **constraint** thường xuất hiện cùng nhau nhưng chúng giải quyết hai vấn đề khác nhau. Index là cấu trúc lưu trữ giúp tìm hàng nhanh hơn và có thể mang thuộc tính duy nhất. Constraint là quy tắc toàn vẹn dữ liệu mà Oracle phải duy trì. Một unique index có thể được dùng để thực thi unique constraint, nhưng bản thân unique index không tự tạo ra một constraint trong metadata.

Sự khác biệt này quan trọng khi thiết kế khóa chính, khóa tự nhiên, khóa ngoại, dữ liệu có NULL, hoặc khi cần cho phép cập nhật nhiều hàng theo một transaction rồi mới kiểm tra tính duy nhất ở thời điểm commit. Chọn sai loại index có thể khiến thao tác INSERT/UPDATE bị lỗi, truy vấn không dùng được access path mong muốn hoặc ứng dụng hiểu nhầm rằng dữ liệu đã được bảo vệ bởi một constraint.

Bài học thuộc chủ đề **Chỉ mục** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Unique index và nonunique index khác nhau ở mức lưu trữ và kiểm tra khóa.
- Quan hệ giữa index với PRIMARY KEY và UNIQUE constraint.
- NULL trong unique key, khóa ghép và các trường hợp biên.
- Cách Oracle tạo, tái sử dụng và quản lý index hỗ trợ constraint.
- DEFERRABLE constraint và kiểm tra uniqueness tại COMMIT.
- Index trên foreign key, function-based unique index và conditional uniqueness.
- Tra cứu metadata, đọc execution plan và bài thực hành SQL.

## 1. Index và constraint có vai trò khác nhau

### Index là cấu trúc truy cập

Index là một cấu trúc dữ liệu được lưu riêng với table, thường là B-tree trong các ví dụ OLTP. Index chứa khóa được tạo từ một hoặc nhiều cột/biểu thức và thông tin định vị hàng tương ứng. Oracle có thể dùng index để:

- Tìm hàng theo điều kiện equality hoặc range.
- Hỗ trợ JOIN và sắp xếp trong một số kế hoạch thực thi.
- Kiểm tra tính duy nhất nếu index là unique.
- Giảm số block table cần đọc khi điều kiện có tính chọn lọc phù hợp.

Index là đối tượng vật lý/logic của schema, có tên, trạng thái, loại và thuộc tính lưu trữ. Tạo index không đồng nghĩa với việc khai báo mọi quy tắc nghiệp vụ liên quan đến cột.

### Constraint là quy tắc toàn vẹn

Constraint định nghĩa điều kiện mà dữ liệu phải tuân theo. Các loại thường gặp:

| Constraint | Quy tắc |
| --- | --- |
| PRIMARY KEY | Xác định hàng duy nhất; các cột khóa không được NULL. |
| UNIQUE | Không cho phép trùng giá trị khóa theo quy tắc của constraint. |
| FOREIGN KEY | Giá trị khóa ngoại phải tham chiếu khóa hợp lệ ở bảng cha, trừ trường hợp NULL được phép. |
| NOT NULL | Cột phải có giá trị khác NULL. |
| CHECK | Giá trị phải thỏa biểu thức điều kiện. |

Constraint được lưu trong data dictionary, có tên, trạng thái ENABLE/DISABLE, VALIDATED/NOT VALIDATED và có thể có thuộc tính DEFERRABLE. Constraint diễn đạt quy tắc dữ liệu ở cấp schema để mọi ứng dụng ghi vào bảng đều phải tuân thủ.

### Unique index không tự tạo UNIQUE constraint

~~~sql
CREATE TABLE app_users (
    user_id NUMBER PRIMARY KEY,
    email   VARCHAR2(320)
);

CREATE UNIQUE INDEX ux_app_users_email
ON app_users(email);
~~~

Index trên email ngăn các giá trị khóa trùng theo semantics của unique index, nhưng trong data dictionary không có UNIQUE constraint tên tương ứng trên cột EMAIL. Nếu ứng dụng hoặc DBA chỉ nhìn index rồi kết luận schema đã khai báo UNIQUE constraint thì sẽ nhầm lẫn.

Ngược lại, khai báo constraint:

~~~sql
ALTER TABLE app_users
ADD CONSTRAINT uq_app_users_email UNIQUE (email);
~~~

Oracle bảo đảm quy tắc uniqueness ở mức constraint. Để thực thi hiệu quả, Oracle thường dùng một index phù hợp; nếu chưa có index phù hợp, nó có thể tạo index hỗ trợ constraint.

### Constraint có thể được thực thi bằng index

Đối với PRIMARY KEY và UNIQUE constraint, Oracle thường dùng unique index để kiểm tra uniqueness khi constraint được kiểm tra ngay lập tức. Nếu constraint là DEFERRABLE, Oracle cần cho phép trạng thái trùng tạm thời trong transaction nên index hỗ trợ constraint là nonunique; kiểm tra quy tắc được thực hiện tại thời điểm constraint phải được xác nhận.

Vì vậy:

- Index có thể là cơ chế thực thi constraint.
- Constraint vẫn là đối tượng mô tả quy tắc toàn vẹn.
- Không phải mọi unique index đều là constraint.
- Không phải mọi index dùng cho unique constraint đều nhất thiết là unique index.

## 2. Unique index và nonunique index

### Unique index

Unique index bảo đảm không có hai index entry mang cùng khóa theo quy tắc uniqueness của Oracle. Ví dụ:

~~~sql
CREATE UNIQUE INDEX ux_employees_badge
ON employees(badge_no);
~~~

Khi tạo thành công, Oracle từ chối INSERT/UPDATE tạo ra khóa trùng. Unique index có thể chứa một cột hoặc nhiều cột:

~~~sql
CREATE UNIQUE INDEX ux_employee_dept_email
ON employees(department_id, email);
~~~

Ở ví dụ này, uniqueness áp dụng cho tổ hợp hai giá trị, không yêu cầu từng cột riêng lẻ phải duy nhất.

### Nonunique index

Nonunique index cho phép nhiều hàng có cùng khóa index:

~~~sql
CREATE INDEX ix_orders_customer
ON orders(customer_id);
~~~

Nhiều đơn hàng có thể thuộc cùng một khách hàng. Nonunique index phù hợp cho các cột thường dùng lọc, JOIN hoặc sắp xếp nhưng không có quy tắc duy nhất.

### So sánh

| Đặc điểm | Unique index | Nonunique index |
| --- | --- | --- |
| Khóa trùng | Bị ngăn theo quy tắc unique index | Được phép |
| Mục tiêu | Truy cập và bảo đảm duy nhất ở cấp index | Truy cập dữ liệu |
| Có tự tạo constraint? | Không | Không |
| Có thể hỗ trợ PK/UNIQUE constraint? | Có, trong trường hợp phù hợp | Có thể được dùng trong một số trường hợp, đặc biệt constraint DEFERRABLE |
| Có thể lập trên nhiều cột? | Có | Có |
| Có thể là function-based? | Có | Có |

### Unique index không có nghĩa mỗi cột riêng lẻ đều duy nhất

~~~sql
CREATE UNIQUE INDEX ux_order_line
ON order_lines(order_id, line_no);
~~~

Index cho phép nhiều dòng có cùng ORDER_ID, miễn là LINE_NO khác nhau trong cùng ORDER_ID. Ví dụ (100, 1) và (100, 2) hợp lệ; hai hàng (100, 1) trùng nhau sẽ bị từ chối.

## 3. PRIMARY KEY, UNIQUE constraint và index hỗ trợ

### PRIMARY KEY

PRIMARY KEY vừa bảo đảm uniqueness, vừa cấm NULL trên các cột cấu thành khóa:

~~~sql
CREATE TABLE departments (
    department_id NUMBER
        CONSTRAINT pk_departments PRIMARY KEY,
    department_name VARCHAR2(100) NOT NULL
);
~~~

Oracle thường tạo unique index để thực thi primary key nếu không có index phù hợp được chỉ định/tái sử dụng. Primary key được lưu trong dictionary dưới constraint type P.

### UNIQUE constraint

UNIQUE constraint bảo đảm không có hai hàng vi phạm quy tắc duy nhất trên tập cột khai báo:

~~~sql
CREATE TABLE app_users (
    user_id NUMBER CONSTRAINT pk_app_users PRIMARY KEY,
    email   VARCHAR2(320),
    CONSTRAINT uq_app_users_email UNIQUE(email)
);
~~~

UNIQUE constraint khác PRIMARY KEY ở chỗ cột unique có thể cho phép NULL nếu không khai báo NOT NULL. Nếu nghiệp vụ yêu cầu mọi hàng phải có email và email không được trùng, khai báo cả hai:

~~~sql
email VARCHAR2(320) NOT NULL,
CONSTRAINT uq_app_users_email UNIQUE(email)
~~~

### Một bảng có thể có nhiều UNIQUE constraint

~~~sql
CREATE TABLE employees (
    employee_id NUMBER
        CONSTRAINT pk_employees PRIMARY KEY,
    national_code VARCHAR2(30),
    work_email    VARCHAR2(320),
    CONSTRAINT uq_employees_national_code UNIQUE(national_code),
    CONSTRAINT uq_employees_work_email UNIQUE(work_email)
);
~~~

Mỗi constraint biểu diễn một quy tắc độc lập. Oracle có thể tạo index riêng cho từng constraint, hoặc dùng index có sẵn phù hợp nếu được chỉ định và đáp ứng điều kiện.

### Dùng index có sẵn để hỗ trợ constraint

Có thể tạo index trước, sau đó thêm constraint và chỉ định index đó:

~~~sql
CREATE UNIQUE INDEX ux_app_users_email
ON app_users(email);

ALTER TABLE app_users
ADD CONSTRAINT uq_app_users_email UNIQUE(email)
USING INDEX ux_app_users_email;
~~~

Điều này giúp DBA chủ động tên và thuộc tính index. Index phải phù hợp với các cột/biểu thức và yêu cầu của constraint. Nếu index không phù hợp hoặc dữ liệu hiện tại vi phạm uniqueness, lệnh thêm constraint sẽ thất bại.

## 4. NULL trong unique key của Oracle

NULL không phải một giá trị số hay chuỗi thông thường; nó biểu thị giá trị chưa biết/không có. Do đó uniqueness có các trường hợp cần phân biệt.

### UNIQUE trên một cột

Với unique constraint trên một cột nullable, Oracle cho phép nhiều hàng có NULL trong cột đó. Các giá trị khác NULL vẫn phải duy nhất:

~~~sql
CREATE TABLE lab_unique_email (
    id    NUMBER PRIMARY KEY,
    email VARCHAR2(100),
    CONSTRAINT uq_lab_unique_email UNIQUE(email)
);

INSERT INTO lab_unique_email VALUES (1, 'a@example.com');
INSERT INTO lab_unique_email VALUES (2, NULL);
INSERT INTO lab_unique_email VALUES (3, NULL);
~~~

Hai hàng NULL hợp lệ; INSERT thêm một hàng có email a@example.com sẽ vi phạm unique constraint.

Nếu muốn cấm NULL, phải khai báo NOT NULL:

~~~sql
ALTER TABLE lab_unique_email
MODIFY email NOT NULL;
~~~

Lệnh này chỉ thành công nếu dữ liệu hiện có không còn NULL.

### UNIQUE trên nhiều cột

Với khóa ghép, uniqueness được xét trên tổ hợp các cột. Oracle có semantics riêng cho NULL trong compound key: một tổ hợp có NULL không được xử lý giống một giá trị thông thường trong phép so sánh SQL; các hàng có một hay nhiều thành phần NULL có thể được chấp nhận tùy tổ hợp, trong khi các tổ hợp hoàn toàn NULL có quy tắc riêng. Không suy luận rằng một UNIQUE constraint trên hai cột tương đương với hai unique constraint riêng.

Ví dụ cần thử trực tiếp trong schema lab để quan sát:

~~~sql
CREATE TABLE lab_unique_pair (
    id NUMBER PRIMARY KEY,
    a  NUMBER,
    b  NUMBER,
    CONSTRAINT uq_lab_unique_pair UNIQUE(a, b)
);

INSERT INTO lab_unique_pair VALUES (1, 10, NULL);
INSERT INTO lab_unique_pair VALUES (2, 10, NULL);
INSERT INTO lab_unique_pair VALUES (3, NULL, 20);
INSERT INTO lab_unique_pair VALUES (4, NULL, 20);
INSERT INTO lab_unique_pair VALUES (5, NULL, NULL);
~~~

Hãy quan sát từng INSERT trên phiên bản Oracle đang dùng và kiểm tra constraint metadata. Khi thiết kế nghiệp vụ, nếu yêu cầu uniqueness phải áp dụng cả khi một thành phần NULL, hãy biểu diễn rõ quy tắc bằng NOT NULL hoặc function-based unique index/biểu thức chuẩn hóa phù hợp, thay vì dựa vào trực giác về NULL.

### Unique B-tree index và khóa toàn NULL

Oracle B-tree index thông thường không lưu entry khi tất cả các cột khóa index đều NULL. Với composite index, một entry có thể tồn tại nếu ít nhất một thành phần có giá trị. Điều này ảnh hưởng đến việc dùng unique index để diễn đạt quy tắc cho các tổ hợp NULL.

Nếu cần bảo đảm một quy tắc đặc biệt liên quan tới NULL, hãy thiết kế biểu thức index tường minh và kiểm tra bằng dữ liệu mẫu. Đừng thay NULL bằng một sentinel tùy tiện nếu sentinel đó có thể xuất hiện trong dữ liệu thật.

## 5. DEFERRABLE constraint và nonunique index

Mặc định, PRIMARY KEY và UNIQUE constraint thường được kiểm tra ngay sau mỗi statement. Oracle cũng hỗ trợ constraint có thể trì hoãn việc kiểm tra đến cuối transaction:

- `NOT DEFERRABLE`: không cho trì hoãn.
- `DEFERRABLE INITIALLY IMMEDIATE`: có thể trì hoãn theo transaction, nhưng mặc định kiểm tra ngay.
- `DEFERRABLE INITIALLY DEFERRED`: mặc định kiểm tra khi transaction kết thúc.

Ví dụ:

~~~sql
CREATE TABLE lab_account_codes (
    id NUMBER PRIMARY KEY,
    code NUMBER,
    CONSTRAINT uq_lab_account_codes
        UNIQUE(code)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Với constraint deferred, transaction có thể tạm thời tạo trạng thái trùng trong lúc thực hiện nhiều bước, miễn là sửa về trạng thái hợp lệ trước khi commit:

~~~sql
SET CONSTRAINTS uq_lab_account_codes DEFERRED;

UPDATE lab_account_codes SET code = 20 WHERE id = 1;
UPDATE lab_account_codes SET code = 10 WHERE id = 2;

COMMIT;
~~~

Trường hợp đổi chỗ hai mã có thể tạo duplicate tạm thời nếu kiểm tra ngay từng statement. Constraint deferred cho phép trạng thái trung gian và xác nhận uniqueness khi transaction kết thúc.

### Vì sao index hỗ trợ DEFERRABLE constraint là nonunique?

Trong transaction deferred, có thể tồn tại tạm thời hai index entry cùng khóa trước khi transaction hoàn tất. Một unique index vật lý sẽ từ chối duplicate ngay khi DML xảy ra, trái với yêu cầu cho phép trì hoãn kiểm tra. Vì vậy Oracle dùng nonunique index để hỗ trợ constraint DEFERRABLE và kiểm tra uniqueness ở thời điểm constraint phải được xác nhận.

Có thể quan sát index liên kết với constraint qua USER_CONSTRAINTS và USER_INDEXES. Đừng suy luận rằng thấy index nonunique thì constraint không duy nhất; constraint có thể vẫn là UNIQUE và được kiểm tra deferred.

### SET CONSTRAINTS

Trong transaction, có thể thay đổi thời điểm kiểm tra các constraint có thuộc tính DEFERRABLE:

~~~sql
SET CONSTRAINTS uq_lab_account_codes DEFERRED;

-- DML có thể tạm tạo duplicate.

SET CONSTRAINTS uq_lab_account_codes IMMEDIATE;
~~~

Khi chuyển sang IMMEDIATE, Oracle kiểm tra các thay đổi hiện tại; nếu dữ liệu đang vi phạm, statement SET CONSTRAINTS có thể thất bại. Constraint `NOT DEFERRABLE` không thể chuyển sang DEFERRED.

## 6. Quan hệ với FOREIGN KEY và index ở bảng con

Foreign key tham chiếu PRIMARY KEY hoặc UNIQUE constraint ở bảng cha. Một unique index độc lập trên cột cha không thay thế đối tượng constraint mà foreign key cần tham chiếu.

Ví dụ:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER
        CONSTRAINT pk_customers PRIMARY KEY,
    email VARCHAR2(320)
);

CREATE TABLE orders (
    order_id NUMBER
        CONSTRAINT pk_orders PRIMARY KEY,
    customer_id NUMBER,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

Index hỗ trợ PRIMARY KEY của CUSTOMERS giúp Oracle tìm và kiểm tra khóa cha. Nhưng Oracle không tự động tạo index trên cột FOREIGN KEY của bảng con:

~~~sql
CREATE INDEX ix_orders_customer_id
ON orders(customer_id);
~~~

Đây thường là nonunique index vì một khách hàng có thể có nhiều đơn hàng.

### Vì sao index trên foreign key thường hữu ích?

- Tăng tốc JOIN từ orders sang customers theo CUSTOMER_ID.
- Hỗ trợ truy vấn lọc đơn hàng theo khách hàng.
- Giúp Oracle tìm các hàng con khi kiểm tra thao tác xóa hàng cha hoặc thay đổi khóa cha.
- Có thể tránh một số tình huống khóa rộng trên bảng con khi parent key bị DELETE/UPDATE trong khi FK không có index.

Index FK không bắt buộc cho mọi bảng. Nếu bảng con rất nhỏ, FK ít được truy vấn hoặc parent key không bị xóa/cập nhật, lợi ích có thể thấp hơn chi phí duy trì index. Mỗi INSERT/UPDATE/DELETE liên quan đến cột FK cũng phải duy trì index, làm tăng công việc DML và redo.

### FK không cần unique index ở bảng con

~~~sql
CREATE INDEX ix_order_lines_order
ON order_lines(order_id);
~~~

Nhiều dòng order_lines có cùng ORDER_ID, nên nonunique index là lựa chọn tự nhiên. Nếu tạo unique index trên ORDER_ID ở bảng con, vô tình bạn sẽ cấm một đơn hàng có nhiều dòng chi tiết.

### Khi nào cột FK có thể cần unique?

Nếu nghiệp vụ là quan hệ một-một, cột FK ở bảng con có thể có UNIQUE constraint:

~~~sql
CREATE TABLE employee_profiles (
    profile_id NUMBER PRIMARY KEY,
    employee_id NUMBER NOT NULL,
    CONSTRAINT uq_employee_profiles_employee UNIQUE(employee_id),
    CONSTRAINT fk_employee_profiles_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id)
);
~~~

UNIQUE constraint bảo đảm mỗi nhân viên có tối đa một profile. Đây là quy tắc dữ liệu; index hỗ trợ nó là một phần triển khai.

## 7. Function-based unique index

Unique index không chỉ áp dụng cho giá trị cột nguyên bản. Oracle hỗ trợ function-based index, trong đó khóa index được tính từ biểu thức. Điều này hữu ích khi uniqueness cần được xét sau chuẩn hóa.

### Không phân biệt chữ hoa/thường

Giả sử email được xem là không phân biệt chữ hoa/thường. Unique constraint thông thường trên EMAIL có thể coi hai chuỗi khác hoa/thường là hai giá trị khác nhau theo collation/semantics hiện tại. Có thể tạo unique function-based index:

~~~sql
CREATE UNIQUE INDEX ux_users_email_ci
ON app_users(LOWER(email));
~~~

Index bảo đảm không có hai giá trị LOWER(email) trùng nhau. Vì vậy Alice@example.com và ALICE@example.com sẽ xung đột nếu cả hai đều khác NULL.

Truy vấn tìm kiếm nên dùng biểu thức tương ứng:

~~~sql
SELECT user_id, email
FROM app_users
WHERE LOWER(email) = LOWER(:email);
~~~

Lưu ý:

- Đây là unique index, không tự tạo UNIQUE constraint trên cột EMAIL.
- Biểu thức chuẩn hóa phải đúng quy tắc nghiệp vụ và ngôn ngữ/collation cần hỗ trợ.
- Function-based index có chi phí duy trì khi cột đầu vào thay đổi.
- Nếu cần metadata constraint rõ ràng, có thể cân nhắc virtual column biểu diễn giá trị chuẩn hóa rồi khai báo UNIQUE constraint trên virtual column, tùy khả năng phiên bản và thiết kế schema.

### Conditional uniqueness: chỉ duy nhất trong một trạng thái

Một yêu cầu thường gặp: email phải duy nhất trong số người dùng ACTIVE, nhưng có thể lặp ở tài khoản INACTIVE hoặc đã lưu trữ. Có thể dùng CASE trong unique function-based index:

~~~sql
CREATE UNIQUE INDEX ux_active_users_email
ON app_users (
    CASE
        WHEN status = 'ACTIVE' THEN LOWER(email)
    END
);
~~~

Với hàng ACTIVE, biểu thức trả LOWER(email) nên các email chuẩn hóa trùng nhau bị từ chối. Với hàng không ACTIVE, biểu thức trả NULL; B-tree index không lưu entry khi toàn bộ khóa là NULL, vì vậy những hàng này không xung đột qua index đó.

Đây là cách diễn đạt conditional uniqueness bằng index. Nó không phải một UNIQUE constraint thông thường có điều kiện WHERE tương đương. Nếu trạng thái thay đổi từ INACTIVE sang ACTIVE, DML sẽ tạo index key và có thể thất bại nếu đã có một người dùng ACTIVE khác cùng email.

### Chuẩn hóa nhiều thành phần

~~~sql
CREATE UNIQUE INDEX ux_active_tenant_login
ON app_users (
    CASE WHEN status = 'ACTIVE' THEN tenant_id END,
    CASE WHEN status = 'ACTIVE' THEN LOWER(login_name) END
);
~~~

Mục tiêu là uniqueness của cặp tenant/login trong tập ACTIVE. Cần xác định rõ NULL và các hàng không ACTIVE, bởi unique index composite có semantics riêng với NULL. Nếu tenant_id hoặc login_name được phép NULL trong hàng ACTIVE, hãy bổ sung quy tắc NOT NULL/CHECK thích hợp nếu nghiệp vụ yêu cầu.

## 8. Tra cứu constraint và index trong data dictionary

Không nên đoán quan hệ giữa constraint và index từ tên object. Oracle cung cấp các dictionary views để kiểm tra.

### USER_CONSTRAINTS

Các cột hữu ích:

- CONSTRAINT_NAME: tên constraint.
- CONSTRAINT_TYPE: P (primary key), U (unique), R (foreign key), C (check/not null).
- TABLE_NAME: bảng chứa constraint.
- STATUS: ENABLED hoặc DISABLED.
- VALIDATED: VALIDATED hoặc NOT VALIDATED.
- DEFERRABLE và DEFERRED: khả năng và trạng thái trì hoãn.
- INDEX_NAME: index được liên kết để thực thi PK/UNIQUE nếu có.

### USER_INDEXES và USER_IND_COLUMNS

USER_INDEXES cho biết thuộc tính index:

- INDEX_NAME, TABLE_NAME.
- UNIQUENESS: UNIQUE hoặc NONUNIQUE.
- INDEX_TYPE, STATUS và các thuộc tính khác.

USER_IND_COLUMNS cho biết cột và thứ tự cột trong index. USER_CONS_COLUMNS cho biết các cột cấu thành constraint.

### Xem PK/UNIQUE và index liên kết

~~~sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status AS constraint_status,
       c.validated,
       c.deferrable,
       c.deferred,
       c.index_name,
       i.uniqueness AS index_uniqueness,
       i.status AS index_status
FROM user_constraints c
LEFT JOIN user_indexes i
  ON i.index_name = c.index_name
WHERE c.table_name = 'APP_USERS'
  AND c.constraint_type IN ('P', 'U')
ORDER BY c.constraint_type, c.constraint_name;
~~~

Nếu constraint là UNIQUE nhưng INDEX_UNIQUENESS là NONUNIQUE, hãy kiểm tra DEFERRABLE/DEFERRED và cách index được dùng. Đây có thể là thiết kế có chủ đích, không phải lỗi metadata.

### Xem cột của constraint

~~~sql
SELECT constraint_name,
       table_name,
       column_name,
       position
FROM user_cons_columns
WHERE table_name = 'APP_USERS'
ORDER BY constraint_name, position;
~~~

### Xem cột của index

~~~sql
SELECT index_name,
       table_name,
       column_name,
       column_position,
       descend
FROM user_ind_columns
WHERE table_name = 'APP_USERS'
ORDER BY index_name, column_position;
~~~

### Xem foreign key và bảng cha

~~~sql
SELECT fk.constraint_name,
       fk.table_name AS child_table,
       fkc.column_name AS child_column,
       pk.table_name AS parent_table,
       pk.constraint_name AS parent_constraint
FROM user_constraints fk
JOIN user_cons_columns fkc
  ON fkc.constraint_name = fk.constraint_name
JOIN user_constraints pk
  ON pk.constraint_name = fk.r_constraint_name
WHERE fk.constraint_type = 'R'
  AND fk.table_name = 'ORDERS'
ORDER BY fkc.position;
~~~

Các USER_ views chỉ hiển thị object thuộc schema hiện tại. Dùng ALL_ views để xem object mà user có quyền truy cập hoặc DBA_ views khi có quyền quản trị phù hợp. Tên object trong dictionary thường được lưu chữ hoa nếu được tạo không dùng quoted identifier.

## 9. Vòng đời index gắn với constraint

Index hỗ trợ constraint có thể được tạo tự động hoặc được DBA tạo trước rồi gắn vào constraint. Cách tạo ảnh hưởng tới việc index tồn tại thế nào khi constraint bị disable hoặc drop.

### Oracle tự tạo index

~~~sql
CREATE TABLE lab_products (
    product_id NUMBER,
    sku        VARCHAR2(40),
    CONSTRAINT pk_lab_products PRIMARY KEY(product_id),
    CONSTRAINT uq_lab_products_sku UNIQUE(sku)
);
~~~

Nếu chưa có index phù hợp, Oracle tạo index để hỗ trợ PK và UNIQUE. Tên index do Oracle tạo có thể khác tên constraint. Kiểm tra qua USER_CONSTRAINTS.INDEX_NAME thay vì giả định hai tên giống nhau.

### Dùng index đã tạo trước

~~~sql
CREATE UNIQUE INDEX ux_lab_products_sku
ON lab_products(sku);

ALTER TABLE lab_products
ADD CONSTRAINT uq_lab_products_sku UNIQUE(sku)
USING INDEX ux_lab_products_sku;
~~~

Sau khi constraint được tạo, index trở thành index được liên kết với constraint. Không nên drop index khi constraint đang dựa vào nó; Oracle sẽ từ chối hoặc yêu cầu thay đổi constraint/index trước.

### Disable hoặc drop constraint

Khi disable PK/UNIQUE constraint, Oracle có thể drop index được tạo tự động để thực thi constraint. Nếu index được tạo độc lập và được dùng bởi constraint, DBA có thể chọn giữ index khi disable bằng tùy chọn KEEP INDEX:

~~~sql
ALTER TABLE lab_products
DISABLE CONSTRAINT uq_lab_products_sku KEEP INDEX;
~~~

Hành vi giữ/xóa index phụ thuộc nguồn gốc index và câu lệnh. Trước khi disable/drop constraint trong môi trường thật, kiểm tra USER_CONSTRAINTS.INDEX_NAME và USER_INDEXES, đồng thời xác nhận ứng dụng có đang dựa vào index cho truy vấn hay không.

### ENABLE VALIDATE và ENABLE NOVALIDATE

Khi bật lại constraint, có thể cần xác định cách kiểm tra dữ liệu hiện hữu:

- ENABLE VALIDATE: xác nhận dữ liệu hiện có tuân thủ constraint và áp dụng constraint cho DML tiếp theo.
- ENABLE NOVALIDATE: không kiểm tra lại toàn bộ dữ liệu cũ, nhưng constraint được áp dụng cho dữ liệu mới/được thay đổi theo quy tắc Oracle.

Ví dụ:

~~~sql
ALTER TABLE lab_products
ENABLE VALIDATE CONSTRAINT uq_lab_products_sku;
~~~

Nếu dữ liệu hiện tại có SKU trùng, việc ENABLE VALIDATE sẽ thất bại. Không dùng NOVALIDATE để che giấu vi phạm mà không có kế hoạch làm sạch; trạng thái VALIDATED là thông tin quan trọng đối với DBA và optimizer.

## 10. Tác động của unique/nonunique index lên DML và truy vấn

### Chi phí ghi

Mỗi index liên quan tới bảng đều cần được duy trì khi DML thay đổi các cột khóa hoặc rowid tương ứng:

- INSERT cần tạo index entry.
- DELETE cần loại index entry.
- UPDATE cột nằm trong khóa index có thể cần xóa entry cũ và thêm entry mới.
- UPDATE cột không thuộc khóa index có thể không cần thay đổi entry của index đó, tùy cấu trúc và thao tác.

Unique index còn cần kiểm tra xung đột khóa, bao gồm tương tác với transaction khác đang tạo cùng key. Vì vậy, thêm index giúp truy vấn không miễn phí; nó có thể làm INSERT/UPDATE/DELETE tốn thêm CPU, redo và I/O.

### Unique index có thể giúp optimizer

Optimizer biết thuộc tính uniqueness của unique index/constraint và có thể dùng thông tin đó để ước lượng cardinality hoặc chọn join method/access path phù hợp. Ví dụ, điều kiện equality trên unique key trả tối đa một hàng theo constraint/index đã được xác nhận.

Tuy nhiên, index không đảm bảo Oracle luôn dùng nó. Nếu bảng nhỏ, truy vấn trả tỷ lệ lớn số hàng, thống kê cũ hoặc full scan rẻ hơn, optimizer có thể chọn full table scan.

### Nonunique index phù hợp cho khóa ngoại và bộ lọc lặp

Các cột như CUSTOMER_ID, DEPARTMENT_ID, STATUS thường có nhiều hàng cùng giá trị. Nonunique index có thể hỗ trợ truy vấn:

~~~sql
SELECT order_id, order_date, amount
FROM orders
WHERE customer_id = :customer_id;
~~~

Nếu mỗi khách hàng có nhiều đơn, index nonunique là đúng semantics. Unique index sẽ biến một quan hệ một-nhiều thành ràng buộc duy nhất ngoài ý muốn.

### Không tạo unique index để thay thế kiểm tra nghiệp vụ phức tạp

Nếu quy tắc duy nhất phụ thuộc nhiều bảng, thời gian hiệu lực, trạng thái hoặc điều kiện liên quan tới các hàng khác, một unique index đơn giản có thể không diễn đạt đủ. Cần mô hình hóa quy tắc bằng constraint phù hợp, function-based index, trigger hoặc quy trình giao dịch có kiểm soát. Trigger kiểm tra uniqueness bằng SELECT trước INSERT/UPDATE có thể bị race condition nếu không dùng cơ chế khóa/constraint phù hợp; ưu tiên declarative constraint/index khi có thể.

## 11. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Unique index tạo thất bại | Dữ liệu hiện tại có khóa trùng | Tìm và xử lý duplicate trước khi tạo index. |
| Thêm UNIQUE constraint thất bại | Dữ liệu hiện tại vi phạm uniqueness hoặc index hỗ trợ không phù hợp | Kiểm tra duplicate, kiểu index và trạng thái constraint. |
| ORA-00001 | INSERT/UPDATE tạo khóa trùng với unique index/constraint | Xác định tên object, kiểm tra logic sinh key và xử lý retry/idempotency. |
| ORA-01452 khi CREATE UNIQUE INDEX | Có duplicate key trong dữ liệu | GROUP BY các cột khóa và HAVING COUNT(*) > 1 để tìm nhóm trùng. |
| ORA-02299 khi ENABLE/VALIDATE UNIQUE constraint | Dữ liệu hiện hữu có duplicate | Làm sạch dữ liệu rồi ENABLE VALIDATE. |
| Foreign key không thể tham chiếu unique index độc lập | Oracle cần PRIMARY KEY hoặc UNIQUE constraint ở bảng cha | Tạo UNIQUE constraint trên cột cha rồi tham chiếu constraint đó. |
| Một khách hàng chỉ có thể có một đơn hàng | Vô tình tạo UNIQUE index/constraint trên CUSTOMER_ID | Dùng nonunique index nếu quan hệ là một-nhiều. |
| UNIQUE constraint có nhiều NULL | Cột nullable và NULL được phép theo semantics Oracle | Thêm NOT NULL nếu mọi hàng bắt buộc có giá trị. |
| Constraint UNIQUE nhưng index là NONUNIQUE | Có thể là DEFERRABLE constraint | Kiểm tra DEFERRABLE/DEFERRED và INDEX_NAME trong dictionary. |
| Drop constraint làm mất index | Index được tạo tự động để thực thi constraint | Tạo/giữ index độc lập hoặc dùng KEEP INDEX khi phù hợp. |
| Truy vấn không dùng index | Cost, selectivity, thống kê hoặc biểu thức không phù hợp | Xem actual plan và stats; không ép index chỉ dựa trên sự tồn tại của nó. |
| INSERT chậm sau khi thêm nhiều index | Chi phí duy trì index tăng | Đánh giá từng index theo workload đọc/ghi và loại bỏ index dư thừa theo quy trình. |

### Tìm duplicate trước khi tạo unique index

~~~sql
SELECT email,
       COUNT(*) AS duplicate_count
FROM app_users
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
~~~

Với khóa ghép:

~~~sql
SELECT department_id,
       email,
       COUNT(*) AS duplicate_count
FROM employees
GROUP BY department_id, email
HAVING COUNT(*) > 1;
~~~

Kết quả GROUP BY cũng gom NULL thành một nhóm để thống kê. Hãy đối chiếu với semantics unique constraint và dữ liệu thực tế trước khi kết luận một nhóm có chắc chắn bị constraint từ chối hay không.

## 12. Bài thực hành tổng hợp

Các ví dụ sử dụng schema học tập có quyền CREATE TABLE và quota phù hợp. DDL có implicit commit trong Oracle; không chạy trên bảng nghiệp vụ thật.

### Bước 1: tạo bảng khách hàng

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER,
    email       VARCHAR2(100),
    status      VARCHAR2(20),
    CONSTRAINT pk_lab_customers PRIMARY KEY(customer_id),
    CONSTRAINT uq_lab_customers_email UNIQUE(email)
);
~~~

### Bước 2: thử UNIQUE constraint và NULL

~~~sql
INSERT INTO lab_customers VALUES (1, 'a@example.com', 'ACTIVE');
INSERT INTO lab_customers VALUES (2, NULL, 'ACTIVE');
INSERT INTO lab_customers VALUES (3, NULL, 'INACTIVE');
~~~

Thử thêm một hàng với email a@example.com và quan sát lỗi. Sau đó truy vấn:

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       deferrable,
       index_name
FROM user_constraints
WHERE table_name = 'LAB_CUSTOMERS';
~~~

### Bước 3: tạo nonunique index trên trạng thái

~~~sql
CREATE INDEX ix_lab_customers_status
ON lab_customers(status);
~~~

Thêm nhiều khách hàng có cùng STATUS và quan sát rằng index nonunique không ngăn duplicate.

### Bước 4: thử function-based unique index

~~~sql
CREATE UNIQUE INDEX ux_lab_customers_email_ci
ON lab_customers(LOWER(email));
~~~

Thử thêm Alice@example.com rồi ALICE@example.com ở hai customer khác nhau. Quan sát xung đột do biểu thức LOWER(email) tạo cùng key.

### Bước 5: thử conditional uniqueness

Để kiểm tra conditional uniqueness độc lập, bỏ constraint UNIQUE toàn cột và index function-based không điều kiện đã tạo ở các bước trước:

~~~sql
ALTER TABLE lab_customers
DROP CONSTRAINT uq_lab_customers_email;

DROP INDEX ux_lab_customers_email_ci;
~~~

Sau đó tạo conditional index:

~~~sql
CREATE UNIQUE INDEX ux_lab_customers_active_email
ON lab_customers (
    CASE WHEN status = 'ACTIVE' THEN LOWER(email) END
);
~~~

Thử hai hàng INACTIVE cùng email và quan sát cả hai có thể tồn tại. Thử hai hàng ACTIVE cùng email đã chuẩn hóa và quan sát hàng thứ hai bị từ chối. Giải thích vì sao index chỉ áp dụng uniqueness cho key được tạo từ biểu thức CASE.

### Bước 6: thử index hỗ trợ foreign key

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER,
    CONSTRAINT fk_lab_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers(customer_id)
);

CREATE INDEX ix_lab_orders_customer
ON lab_orders(customer_id);
~~~

Thêm nhiều đơn cho cùng một customer. Quan sát index bảng con là nonunique và FK vẫn bảo đảm customer_id tham chiếu khách hàng hợp lệ.

### Bước 7: xem metadata index và constraint

~~~sql
SELECT i.index_name,
       i.uniqueness,
       c.constraint_name,
       c.constraint_type,
       c.deferrable,
       c.index_name AS constraint_index
FROM user_indexes i
LEFT JOIN user_constraints c
  ON c.index_name = i.index_name
WHERE i.table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY i.table_name, i.index_name;
~~~

Giải thích vì sao có index không có constraint tương ứng và vì sao index hỗ trợ constraint có thể không cùng tên với constraint.

### Bước 8: dọn dữ liệu

~~~sql
DROP TABLE lab_orders PURGE;
DROP TABLE lab_customers PURGE;
~~~

Chỉ chạy khi đã hoàn thành bài và không cần giữ dữ liệu. DROP TABLE là DDL có implicit commit; PURGE bỏ qua Recycle Bin.

## 13. Câu hỏi tự kiểm tra

1. **Unique index là gì?** Index bảo đảm các key entry không trùng theo quy tắc unique index của Oracle.
2. **Nonunique index là gì?** Index cho phép nhiều hàng có cùng key.
3. **Tạo unique index có tự tạo UNIQUE constraint không?** Không; index và constraint là hai object khác nhau.
4. **UNIQUE constraint có thể được thực thi bằng index không?** Có; Oracle thường dùng index phù hợp để kiểm tra uniqueness.
5. **PRIMARY KEY khác UNIQUE constraint thế nào?** Primary key không cho NULL và chỉ có một primary key trên một bảng; bảng có thể có nhiều unique constraint.
6. **Unique constraint trên một cột nullable có cho nhiều NULL không?** Có; nếu nghiệp vụ cấm NULL, thêm NOT NULL.
7. **Unique index ghép bảo đảm điều gì?** Tổ hợp các giá trị trong toàn bộ danh sách cột là duy nhất theo semantics của Oracle.
8. **Vì sao constraint DEFERRABLE có thể dùng nonunique index?** Để cho phép key trùng tạm thời trong transaction và kiểm tra khi constraint được yêu cầu xác nhận.
9. **SET CONSTRAINTS dùng để làm gì?** Thay đổi thời điểm kiểm tra constraint có thuộc tính DEFERRABLE trong transaction.
10. **Foreign key có thể tham chiếu một unique index độc lập không?** Không; cần PRIMARY KEY hoặc UNIQUE constraint ở bảng cha.
11. **Oracle có tự tạo index cho foreign key ở bảng con không?** Không; DBA/ứng dụng cân nhắc tạo nonunique index theo workload.
12. **Khi nào function-based unique index hữu ích?** Khi uniqueness cần xét trên giá trị chuẩn hóa hoặc biểu thức như LOWER(email).
13. **Conditional uniqueness có thể biểu diễn thế nào?** Dùng unique function-based index với CASE để chỉ tạo key cho các hàng thuộc trạng thái cần kiểm soát.
14. **Xem index nào hỗ trợ constraint ở đâu?** USER_CONSTRAINTS.INDEX_NAME, kết hợp USER_INDEXES.UNIQUENESS.
15. **Vì sao phải xử lý duplicate trước khi tạo unique index?** Unique index không thể được tạo nếu dữ liệu hiện tại chứa key trùng.
16. **Tăng số index có tác động gì?** Có thể tăng tốc truy vấn nhưng làm DML tốn thêm công việc duy trì, redo, I/O và không gian.

Unique/nonunique mô tả thuộc tính của **index**, còn PRIMARY KEY và UNIQUE mô tả **quy tắc toàn vẹn**. Trong Oracle, một constraint duy nhất thường dựa vào index để thực thi; constraint DEFERRABLE có thể cần nonunique index để cho phép trạng thái trùng tạm thời. Hãy kiểm tra dictionary thay vì suy luận từ tên index, chọn nonunique index cho các quan hệ một-nhiều như foreign key khi workload cần, và chỉ dùng function-based/conditional unique index khi quy tắc chuẩn hóa hoặc uniqueness có điều kiện đã được xác định rõ.
