# DELETE theo điều kiện và xóa dữ liệu quan hệ cha con trong Oracle

Lệnh **DELETE** dùng để xóa các dòng khỏi một bảng. Trong hệ thống có nhiều bảng liên kết bằng khóa ngoại, việc xóa một dòng cha còn phụ thuộc vào những dòng con đang tham chiếu đến nó. Vì vậy, một thao tác xóa an toàn cần trả lời được ba câu hỏi: **dòng nào cần xóa, các dòng liên quan nằm ở đâu, và quan hệ khóa ngoại quy định điều gì khi xóa cha?**

Bài học này trình bày cách viết **DELETE ... WHERE**, kiểm tra phạm vi trước khi xóa, xóa dữ liệu theo quan hệ cha-con nhiều cấp, và lựa chọn giữa xóa con trước, **ON DELETE CASCADE** hoặc **ON DELETE SET NULL**. Các ví dụ dùng Oracle Database, có thể chạy trong schema thực hành riêng.

## 1. DELETE là lệnh DML

Cú pháp cơ bản:

~~~sql
DELETE FROM table_name
WHERE condition;
~~~

- **DELETE FROM** chỉ ra bảng đích.
- **WHERE** xác định những dòng thỏa điều kiện sẽ bị xóa.
- Nếu bỏ **WHERE**, Oracle xóa **tất cả các dòng** trong bảng.
- Bảng, cột, index và constraint vẫn tồn tại sau lệnh DELETE.

Ví dụ:

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'DONE';
~~~

Lệnh trên xóa các dòng công việc có trạng thái DONE. Những dòng có trạng thái khác vẫn còn.

**DELETE** là DML (Data Manipulation Language). Các thay đổi thuộc transaction hiện tại và có thể được **COMMIT** hoặc **ROLLBACK** theo quy tắc transaction của Oracle. Điều này khác với các lệnh DDL như **TRUNCATE TABLE** hoặc **DROP TABLE**, vốn có hành vi commit ngầm theo quy tắc DDL của Oracle.

### 1.1. DELETE không có WHERE

~~~sql
DELETE FROM lab_del_task;
~~~

Lệnh này xóa mọi dòng trong **LAB_DEL_TASK**. Nó không xóa bảng và có thể rollback nếu transaction chưa commit. Tuy nhiên, phạm vi ảnh hưởng rất lớn; hãy xác nhận đúng schema, đúng bảng và đúng mục tiêu trước khi chạy.

### 1.2. DELETE khác TRUNCATE và DROP

| Lệnh | Tác động | Có WHERE? | Có thể ROLLBACK như DML chưa commit? | Đối tượng sau lệnh |
|---|---|:---:|---|---|
| **DELETE** | Xóa các dòng được chọn | Có | Có | Bảng còn nguyên |
| **DELETE** không WHERE | Xóa mọi dòng | Không | Có | Bảng còn nguyên |
| **TRUNCATE TABLE** | Xóa toàn bộ dữ liệu bằng DDL | Không | Không | Bảng còn nguyên |
| **DROP TABLE** | Xóa đối tượng bảng | Không | Không theo cách rollback DML | Bảng bị loại khỏi schema/recycle bin tùy điều kiện |

Không chọn TRUNCATE chỉ vì muốn xóa nhanh nếu yêu cầu là xóa theo điều kiện hoặc cần rollback trong transaction.

## 2. Chuẩn bị schema thực hành có quan hệ cha-con

Ta tạo ba cấp dữ liệu:

- **LAB_DEL_DEPARTMENT**: phòng ban, là bảng cha cấp cao.
- **LAB_DEL_EMPLOYEE**: nhân viên, tham chiếu phòng ban.
- **LAB_DEL_TASK**: công việc, tham chiếu nhân viên.

Quan hệ:

~~~text
LAB_DEL_DEPARTMENT
        |
        | 1 phòng ban có nhiều nhân viên
        v
LAB_DEL_EMPLOYEE
        |
        | 1 nhân viên có nhiều công việc
        v
LAB_DEL_TASK
~~~

Trong bộ bảng đầu tiên, các khóa ngoại **không khai báo ON DELETE CASCADE**. Đây là cách mặc định thường gặp: Oracle ngăn xóa dòng cha khi vẫn còn dòng con tham chiếu.

### 2.1. Tạo bảng cha

~~~sql
CREATE TABLE lab_del_department (
    department_id   NUMBER(4) PRIMARY KEY,
    department_name VARCHAR2(60 CHAR) NOT NULL
);
~~~

### 2.2. Tạo bảng con cấp một

~~~sql
CREATE TABLE lab_del_employee (
    employee_id   NUMBER(6) PRIMARY KEY,
    department_id NUMBER(4) NOT NULL,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    employee_status VARCHAR2(20 CHAR) NOT NULL,
    hire_date     DATE NOT NULL,
    CONSTRAINT fk_lab_del_emp_dept
      FOREIGN KEY (department_id)
      REFERENCES lab_del_department (department_id),
    CONSTRAINT ck_lab_del_emp_status
      CHECK (employee_status IN ('ACTIVE', 'INACTIVE'))
);
~~~

**DEPARTMENT_ID** là khóa ngoại tham chiếu phòng ban. Cột được khai báo **NOT NULL**, vì mỗi nhân viên trong ví dụ phải thuộc một phòng ban.

### 2.3. Tạo bảng con cấp hai

~~~sql
CREATE TABLE lab_del_task (
    task_id     NUMBER(7) PRIMARY KEY,
    employee_id NUMBER(6) NOT NULL,
    task_name   VARCHAR2(100 CHAR) NOT NULL,
    task_status VARCHAR2(20 CHAR) NOT NULL,
    created_at  DATE NOT NULL,
    CONSTRAINT fk_lab_del_task_emp
      FOREIGN KEY (employee_id)
      REFERENCES lab_del_employee (employee_id),
    CONSTRAINT ck_lab_del_task_status
      CHECK (task_status IN ('OPEN', 'DONE', 'CANCELLED'))
);
~~~

Một nhân viên có thể có nhiều công việc. Khóa ngoại **FK_LAB_DEL_TASK_EMP** bảo đảm công việc chỉ tham chiếu nhân viên tồn tại.

### 2.4. Chèn dữ liệu mẫu

~~~sql
INSERT INTO lab_del_department VALUES (10, 'Sales');
INSERT INTO lab_del_department VALUES (20, 'Support');
INSERT INTO lab_del_department VALUES (30, 'Legal');

INSERT INTO lab_del_employee VALUES
  (101, 10, 'An',   'ACTIVE',   DATE '2022-01-10');
INSERT INTO lab_del_employee VALUES
  (102, 10, 'Binh', 'INACTIVE', DATE '2020-03-15');
INSERT INTO lab_del_employee VALUES
  (201, 20, 'Chi',  'ACTIVE',   DATE '2021-07-01');
INSERT INTO lab_del_employee VALUES
  (301, 30, 'Dung', 'ACTIVE',   DATE '2023-05-01');

INSERT INTO lab_del_task VALUES
  (1001, 101, 'Prepare sales report', 'DONE', DATE '2024-01-05');
INSERT INTO lab_del_task VALUES
  (1002, 101, 'Call customer',        'OPEN', DATE '2026-01-10');
INSERT INTO lab_del_task VALUES
  (1003, 102, 'Archive old contract', 'DONE', DATE '2023-12-20');
INSERT INTO lab_del_task VALUES
  (2001, 201, 'Resolve support case', 'OPEN', DATE '2026-02-02');

COMMIT;
~~~

### 2.5. Kiểm tra dữ liệu và quan hệ

~~~sql
SELECT * FROM lab_del_department ORDER BY department_id;
SELECT * FROM lab_del_employee ORDER BY employee_id;
SELECT * FROM lab_del_task ORDER BY task_id;
~~~

Tóm tắt:

| Phòng ban | Nhân viên | Công việc |
|---|---|---|
| Sales (10) | An (101), Binh (102) | 1001, 1002 của An; 1003 của Binh |
| Support (20) | Chi (201) | 2001 |
| Legal (30) | Dung (301) | Chưa có công việc |

Dataset có nhân viên inactive, task đã hoàn thành, task đang mở, và phòng ban chưa có nhân viên. Các trường hợp này giúp kiểm tra điều kiện xóa và tác động của khóa ngoại.

## 3. Xóa dữ liệu theo điều kiện WHERE

Điều kiện WHERE có thể dựa trên một cột, nhiều cột, khoảng ngày, danh sách giá trị hoặc truy vấn con.

### 3.1. Xóa theo khóa chính

~~~sql
DELETE FROM lab_del_task
WHERE task_id = 1001;
~~~

**TASK_ID** là primary key, nên điều kiện xác định tối đa một dòng. Đây là dạng xóa chính xác khi đã biết định danh bản ghi.

### 3.2. Xóa theo nhiều điều kiện

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'DONE'
  AND created_at < DATE '2025-01-01';
~~~

Chỉ các task vừa có trạng thái DONE vừa được tạo trước ngày 1/1/2025 được chọn. Điều kiện **AND** yêu cầu cả hai vế đúng.

Nếu dùng **OR**:

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'CANCELLED'
   OR created_at < DATE '2024-01-01';
~~~

Một dòng thỏa một trong hai điều kiện cũng bị xóa. Cần phân biệt rõ AND và OR vì chúng có thể làm thay đổi mạnh số dòng bị tác động.

### 3.3. Xóa theo danh sách

~~~sql
DELETE FROM lab_del_employee
WHERE employee_id IN (102, 301);
~~~

Điều kiện IN phù hợp với danh sách khóa đã xác định. Tuy nhiên, ví dụ này có thể bị khóa ngoại ngăn lại nếu nhân viên 102 vẫn có task 1003. Phải xử lý dòng con trước hoặc dùng chính sách xóa được thiết kế ở constraint.

### 3.4. Xóa theo khoảng ngày

Với cột Oracle DATE có cả ngày và thời gian, nên dùng khoảng nửa mở khi xóa theo một ngày/tháng:

~~~sql
DELETE FROM lab_del_task
WHERE created_at >= DATE '2024-01-01'
  AND created_at <  DATE '2025-01-01';
~~~

Điều kiện này bao gồm mọi thời điểm trong năm 2024 và không phụ thuộc vào việc tự đặt mốc cuối ngày 31/12. Literal DATE giúp tránh diễn giải chuỗi theo thiết lập NLS của session.

### 3.5. Xóa các dòng có cột NULL

Không dùng **= NULL**:

~~~sql
-- Không đúng ý định:
DELETE FROM lab_del_task
WHERE task_status = NULL;

-- Kiểm tra NULL đúng cách:
DELETE FROM lab_del_task
WHERE task_status IS NULL;
~~~

Trong bảng lab, **TASK_STATUS** là NOT NULL nên lệnh thứ hai không xóa dòng nào. Khi cột thực tế nullable, **IS NULL** mới là phép kiểm tra phù hợp.

Trong SQL, điều kiện có kết quả UNKNOWN (ví dụ so sánh với NULL) không được WHERE giữ lại. Hãy xem lại logic ba giá trị TRUE/FALSE/UNKNOWN khi viết điều kiện xóa.

## 4. Kiểm tra phạm vi trước khi DELETE

Một quy trình thực tế nên bắt đầu bằng SELECT có cùng điều kiện với DELETE.

Giả sử cần xóa các task DONE đã tạo trước năm 2025:

**Bước 1 — xem các dòng sẽ bị ảnh hưởng:**

~~~sql
SELECT task_id, employee_id, task_name, task_status, created_at
FROM lab_del_task
WHERE task_status = 'DONE'
  AND created_at < DATE '2025-01-01'
ORDER BY task_id;
~~~

**Bước 2 — đếm số dòng:**

~~~sql
SELECT COUNT(*) AS rows_to_delete
FROM lab_del_task
WHERE task_status = 'DONE'
  AND created_at < DATE '2025-01-01';
~~~

**Bước 3 — thực hiện DELETE với cùng điều kiện:**

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'DONE'
  AND created_at < DATE '2025-01-01';
~~~

**Bước 4 — kiểm tra số dòng và kết quả sau xóa:**

SQL client thường hiển thị số dòng bị xóa. Trong PL/SQL, có thể đọc **SQL%ROWCOUNT** ngay sau câu DELETE:

~~~sql
DECLARE
    v_deleted PLS_INTEGER;
BEGIN
    DELETE FROM lab_del_task
    WHERE task_status = 'DONE'
      AND created_at < DATE '2025-01-01';

    v_deleted := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('Deleted rows: ' || v_deleted);

    ROLLBACK;
END;
/
~~~

Ví dụ PL/SQL trên rollback để minh họa cách kiểm tra số dòng mà không giữ thay đổi. Khi thực hiện xóa thật, hãy chọn COMMIT hoặc ROLLBACK theo kết quả kiểm tra và quy trình transaction của ứng dụng.

### 4.1. Lưu ý về SQL%ROWCOUNT

**SQL%ROWCOUNT** là thuộc tính cursor ngầm trong PL/SQL, cho biết số dòng bị tác động bởi câu DML gần nhất. Hãy đọc nó ngay sau câu DELETE cần đo; một câu SQL khác có thể làm thay đổi giá trị liên quan đến cursor ngầm.

Không dùng số dòng bị xóa làm bằng chứng duy nhất rằng thao tác đúng. Hãy kiểm tra cả khóa của các dòng được chọn, các bảng con và trạng thái nghiệp vụ.

## 5. Transaction: COMMIT, ROLLBACK và SAVEPOINT

DELETE là DML, nên thay đổi thuộc transaction hiện tại:

~~~sql
DELETE FROM lab_del_task
WHERE task_id = 1001;

-- Nếu phát hiện chọn nhầm:
ROLLBACK;
~~~

Sau ROLLBACK, dòng task 1001 được khôi phục nếu chưa có COMMIT hoặc ranh giới transaction khác.

Nếu xóa nhiều nhóm dữ liệu trong một transaction, có thể đặt SAVEPOINT:

~~~sql
SAVEPOINT before_cleanup;

DELETE FROM lab_del_task
WHERE task_status = 'DONE';

-- Kiểm tra kết quả, nếu chưa đúng:
ROLLBACK TO before_cleanup;
~~~

**ROLLBACK TO** hoàn tác các thay đổi sau savepoint, giữ transaction mở. **COMMIT** kết thúc transaction và làm thay đổi trở nên bền vững; sau đó không thể dùng ROLLBACK để khôi phục các dòng đã xóa.

### 5.1. COMMIT ngầm và công cụ client

Oracle tự động commit trước và sau một số lệnh DDL. **DELETE** không phải DDL và bản thân nó không tự commit. Tuy nhiên, SQL Developer, SQL*Plus, JDBC client hoặc công cụ khác có thể có tùy chọn autocommit. Hãy biết chế độ transaction của công cụ trước khi thử thao tác xóa.

## 6. Quan hệ khóa ngoại mặc định: không xóa được cha khi còn con

Trong schema lab, khóa ngoại **FK_LAB_DEL_EMP_DEPT** không khai báo hành động ON DELETE. Khi có nhân viên tham chiếu phòng ban 10, câu lệnh:

~~~sql
DELETE FROM lab_del_department
WHERE department_id = 10;
~~~

sẽ bị Oracle từ chối với lỗi thường gặp:

~~~text
ORA-02292: integrity constraint (SCHEMA.FK_LAB_DEL_EMP_DEPT) violated - child record found
~~~

Thông báo có nghĩa là vẫn còn dòng con tham chiếu khóa chính phòng ban đang bị xóa. Oracle bảo vệ tính toàn vẹn tham chiếu: không cho phép tạo ra nhân viên có **DEPARTMENT_ID** trỏ tới phòng ban không còn tồn tại.

Tương tự, xóa nhân viên 101 khi task 1001 hoặc 1002 vẫn tham chiếu nhân viên đó sẽ bị chặn bởi **FK_LAB_DEL_TASK_EMP**.

### 6.1. Xóa theo thứ tự từ con lên cha

Nếu thiết kế không dùng ON DELETE CASCADE, phải xóa các dòng con trước:

~~~sql
-- Cấp sâu nhất: công việc của nhân viên thuộc phòng 10.
DELETE FROM lab_del_task t
WHERE EXISTS (
    SELECT 1
    FROM lab_del_employee e
    WHERE e.employee_id = t.employee_id
      AND e.department_id = 10
);

-- Sau khi task đã được xóa, xóa nhân viên của phòng 10.
DELETE FROM lab_del_employee
WHERE department_id = 10;

-- Cuối cùng mới xóa phòng ban.
DELETE FROM lab_del_department
WHERE department_id = 10;
~~~

Thứ tự là:

1. Xóa task (con của employee).
2. Xóa employee (con của department).
3. Xóa department (cha).

Nếu một nhân viên có nhiều loại dữ liệu con ở các bảng khác nhau, phải xử lý **tất cả các bảng con** trước khi xóa nhân viên. Nếu một phòng ban có thêm bảng con như lịch sử, ngân sách hoặc tài sản, phải xem xét các khóa ngoại đó trước khi xóa phòng ban.

### 6.2. Kiểm tra từng cấp trước khi xóa

Trước khi xóa task thuộc phòng 10:

~~~sql
SELECT t.*
FROM lab_del_task t
JOIN lab_del_employee e
  ON e.employee_id = t.employee_id
WHERE e.department_id = 10
ORDER BY t.task_id;
~~~

Kiểm tra nhân viên:

~~~sql
SELECT *
FROM lab_del_employee
WHERE department_id = 10
ORDER BY employee_id;
~~~

Kiểm tra phòng ban:

~~~sql
SELECT *
FROM lab_del_department
WHERE department_id = 10;
~~~

Các SELECT này giúp xác nhận tập dữ liệu liên quan trước khi chạy chuỗi DELETE. Chúng không khóa hoặc giữ nguyên tập dòng nếu dữ liệu khác có thể được thay đổi đồng thời; với thao tác cần tính nhất quán cao, hãy thiết kế transaction, khóa và mức cô lập phù hợp.

## 7. Dùng EXISTS để xóa dòng con theo điều kiện của cha

Một yêu cầu phổ biến là xóa các task thuộc nhân viên inactive hoặc có trạng thái cụ thể.

Ví dụ: xóa task của nhân viên inactive:

~~~sql
DELETE FROM lab_del_task t
WHERE EXISTS (
    SELECT 1
    FROM lab_del_employee e
    WHERE e.employee_id = t.employee_id
      AND e.employee_status = 'INACTIVE'
);
~~~

**EXISTS** kiểm tra có ít nhất một dòng employee thỏa điều kiện cho task hiện tại. Subquery tương quan tham chiếu **t.employee_id** của dòng đang xét.

Một cách khác dùng IN:

~~~sql
DELETE FROM lab_del_task
WHERE employee_id IN (
    SELECT employee_id
    FROM lab_del_employee
    WHERE employee_status = 'INACTIVE'
);
~~~

Hai dạng này phù hợp khi subquery trả danh sách khóa. EXISTS thường diễn đạt rõ quan hệ tương quan; IN cũng dễ đọc cho tập khóa. Khi dùng NOT IN, cần đặc biệt chú ý NULL trong tập con vì NULL có thể khiến điều kiện không trả TRUE. **NOT EXISTS** thường dễ kiểm soát hơn cho bài toán xóa dòng không có dòng liên quan.

### 7.1. Xóa nhân viên khi không còn dòng con

Ví dụ xóa nhân viên inactive không có task:

~~~sql
DELETE FROM lab_del_employee e
WHERE e.employee_status = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM lab_del_task t
      WHERE t.employee_id = e.employee_id
  );
~~~

NOT EXISTS bảo đảm chỉ chọn nhân viên không có task liên quan. Đây là điều kiện nghiệp vụ; khóa ngoại vẫn là lớp bảo vệ cuối cùng nếu dữ liệu thay đổi đồng thời.

### 7.2. Xóa dòng cha dựa trên điều kiện của bảng con

Ví dụ xóa nhân viên chỉ khi tất cả công việc đã hoàn thành. Cần xác định cả trường hợp không có công việc. Một cách diễn đạt “có ít nhất một task và không có task chưa hoàn thành”:

~~~sql
DELETE FROM lab_del_employee e
WHERE EXISTS (
    SELECT 1
    FROM lab_del_task t
    WHERE t.employee_id = e.employee_id
)
AND NOT EXISTS (
    SELECT 1
    FROM lab_del_task t
    WHERE t.employee_id = e.employee_id
      AND t.task_status <> 'DONE'
);
~~~

Trước khi dùng, cần nhớ rằng khóa ngoại không cascade: các task vẫn còn nên DELETE employee vẫn bị ORA-02292. Điều kiện chỉ xác định nhân viên đủ tiêu chí nghiệp vụ; ta vẫn phải xóa task trước hoặc dùng một thiết kế cascade phù hợp.

## 8. Xóa dữ liệu quan hệ nhiều cấp

Với cây dữ liệu:

~~~text
DEPARTMENT
  ├── EMPLOYEE
  │     ├── TASK
  │     └── EMPLOYEE_NOTE
  └── DEPARTMENT_DOCUMENT
~~~

Muốn xóa một phòng ban theo cách không cascade, phải xóa mọi nhánh con ở cấp sâu nhất trước, rồi mới đi ngược lên:

1. Xóa TASK và EMPLOYEE_NOTE thuộc nhân viên của phòng.
2. Xóa EMPLOYEE thuộc phòng.
3. Xóa DEPARTMENT_DOCUMENT thuộc phòng.
4. Xóa DEPARTMENT.

Không chỉ nhìn quan hệ trực tiếp. Một dòng cha có thể được tham chiếu bởi nhiều bảng con độc lập; chỉ cần một dòng con còn tồn tại là khóa ngoại tương ứng có thể chặn thao tác xóa.

### 8.1. Xóa một nhánh bằng EXISTS

Mẫu cho bảng con:

~~~sql
DELETE FROM child_table c
WHERE EXISTS (
    SELECT 1
    FROM parent_table p
    WHERE p.parent_id = c.parent_id
      AND p.parent_id = :target_parent_id
);
~~~

Mẫu này xóa các dòng con thuộc một parent ID. Với bảng cháu, nối qua bảng con để xác định tổ tiên:

~~~sql
DELETE FROM grandchild_table g
WHERE EXISTS (
    SELECT 1
    FROM child_table c
    WHERE c.child_id = g.child_id
      AND c.parent_id = :target_parent_id
);
~~~

Thay tên bảng, khóa và điều kiện theo schema thật. Chạy SELECT với cùng điều kiện để xem chính xác nhánh sẽ bị xóa.

## 9. ON DELETE CASCADE: tự động xóa con khi xóa cha

Nếu quy tắc nghiệp vụ quy định rằng dòng con không có ý nghĩa độc lập khi dòng cha bị xóa, có thể khai báo khóa ngoại với **ON DELETE CASCADE**.

Hành động này được khai báo trên **foreign key ở bảng con**:

~~~sql
CREATE TABLE lab_c_department (
    department_id   NUMBER(4) PRIMARY KEY,
    department_name VARCHAR2(60 CHAR) NOT NULL
);

CREATE TABLE lab_c_employee (
    employee_id   NUMBER(6) PRIMARY KEY,
    department_id NUMBER(4) NOT NULL,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    CONSTRAINT fk_lab_c_emp_dept
      FOREIGN KEY (department_id)
      REFERENCES lab_c_department (department_id)
      ON DELETE CASCADE
);

CREATE TABLE lab_c_task (
    task_id     NUMBER(7) PRIMARY KEY,
    employee_id NUMBER(6) NOT NULL,
    task_name   VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT fk_lab_c_task_emp
      FOREIGN KEY (employee_id)
      REFERENCES lab_c_employee (employee_id)
      ON DELETE CASCADE
);
~~~

Chèn dữ liệu:

~~~sql
INSERT INTO lab_c_department VALUES (10, 'Sales');
INSERT INTO lab_c_department VALUES (20, 'Support');

INSERT INTO lab_c_employee VALUES (101, 10, 'An');
INSERT INTO lab_c_employee VALUES (102, 10, 'Binh');
INSERT INTO lab_c_employee VALUES (201, 20, 'Chi');

INSERT INTO lab_c_task VALUES (1001, 101, 'Prepare report');
INSERT INTO lab_c_task VALUES (1002, 101, 'Call customer');
INSERT INTO lab_c_task VALUES (1003, 102, 'Archive contract');
INSERT INTO lab_c_task VALUES (2001, 201, 'Resolve case');

COMMIT;
~~~

Khi xóa phòng ban 10:

~~~sql
DELETE FROM lab_c_department
WHERE department_id = 10;
~~~

Oracle tự động xóa các employee thuộc phòng 10 theo **FK_LAB_C_EMP_DEPT**; sau đó các task tham chiếu những employee đó cũng bị xóa theo **FK_LAB_C_TASK_EMP**.

Kiểm tra:

~~~sql
SELECT * FROM lab_c_department ORDER BY department_id;
SELECT * FROM lab_c_employee ORDER BY employee_id;
SELECT * FROM lab_c_task ORDER BY task_id;
~~~

Sau DELETE:

- Phòng ban 10 không còn.
- Nhân viên 101 và 102 không còn.
- Task 1001, 1002 và 1003 không còn.
- Phòng ban 20, nhân viên 201 và task 2001 vẫn còn.

Đây là xóa cascade nhiều cấp do mỗi quan hệ cha-con đều khai báo hành động cascade tương ứng.

### 9.1. ON DELETE CASCADE không phải cú pháp của DELETE

~~~sql
-- Không phải cú pháp Oracle:
DELETE FROM lab_c_department
WHERE department_id = 10
CASCADE;
~~~

Oracle không có mệnh đề DELETE ... CASCADE như vậy. Hành động cascade là thuộc tính của constraint foreign key, được định nghĩa khi tạo hoặc sửa constraint.

### 9.2. Khi nào nên dùng cascade?

Phù hợp khi:

- Dòng con phụ thuộc hoàn toàn vào dòng cha.
- Dữ liệu con không cần tồn tại nếu cha bị xóa.
- Quy tắc xóa nhất quán ở mọi ứng dụng và mọi đường truy cập database.
- Phạm vi cascade đã được hiểu và kiểm soát.

Không phù hợp hoặc cần cân nhắc kỹ khi:

- Dòng con là lịch sử, chứng từ, nhật ký hoặc dữ liệu cần lưu theo chính sách retention.
- Dữ liệu con được tham chiếu bởi nhiều nghiệp vụ độc lập.
- Người dùng cần lưu audit hoặc lý do xóa ở từng cấp.
- Một thao tác xóa cha có thể xóa lượng dữ liệu rất lớn ngoài dự kiến.

Cascade làm đơn giản hóa chuỗi DELETE, nhưng cũng làm tăng phạm vi tác động của một lệnh xóa cha. Trước khi dùng, hãy liệt kê tất cả quan hệ cascade trên đường đi.

## 10. ON DELETE SET NULL: giữ con, bỏ liên kết tới cha

Một số nghiệp vụ muốn giữ dòng con nhưng cho phép nó không còn thuộc dòng cha. Khi đó có thể dùng **ON DELETE SET NULL**:

~~~sql
CREATE TABLE lab_s_department (
    department_id   NUMBER(4) PRIMARY KEY,
    department_name VARCHAR2(60 CHAR) NOT NULL
);

CREATE TABLE lab_s_employee (
    employee_id   NUMBER(6) PRIMARY KEY,
    department_id NUMBER(4) NULL,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    CONSTRAINT fk_lab_s_emp_dept
      FOREIGN KEY (department_id)
      REFERENCES lab_s_department (department_id)
      ON DELETE SET NULL
);
~~~

Chèn dữ liệu:

~~~sql
INSERT INTO lab_s_department VALUES (10, 'Sales');
INSERT INTO lab_s_employee VALUES (101, 10, 'An');
INSERT INTO lab_s_employee VALUES (102, 10, 'Binh');
COMMIT;
~~~

Xóa phòng ban:

~~~sql
DELETE FROM lab_s_department
WHERE department_id = 10;
~~~

Kết quả:

| EMPLOYEE_ID | DEPARTMENT_ID | EMPLOYEE_NAME |
|---:|---:|---|
| 101 | NULL | An |
| 102 | NULL | Binh |

Các dòng nhân viên còn tồn tại, nhưng **DEPARTMENT_ID** được đặt thành NULL. Vì vậy cột khóa ngoại phải cho phép NULL. Nếu cột được khai báo NOT NULL, hành động SET NULL không thể hoàn tất do xung đột constraint.

### 10.1. Chọn RESTRICT, CASCADE hay SET NULL

Oracle không dùng từ khóa RESTRICT riêng trong cú pháp foreign key như một số hệ quản trị khác. Khi không khai báo **ON DELETE CASCADE** hoặc **ON DELETE SET NULL**, hành vi mặc định là ngăn xóa cha khi có dòng con tham chiếu.

| Cấu hình foreign key | Khi xóa dòng cha |
|---|---|
| Không khai báo hành động ON DELETE | Bị chặn nếu còn dòng con tham chiếu |
| **ON DELETE CASCADE** | Dòng con tham chiếu bị xóa |
| **ON DELETE SET NULL** | Cột khóa ngoại ở dòng con được đặt NULL |

Hãy chọn theo quy tắc dữ liệu, không chỉ theo sự tiện lợi của câu lệnh.

## 11. Xóa nhiều dòng cha bằng cascade và phạm vi tác động

Với cascade, một DELETE có thể làm thay đổi nhiều bảng. Ví dụ:

~~~sql
DELETE FROM lab_c_department
WHERE department_id IN (10, 20);
~~~

Lệnh này có thể xóa mọi nhân viên và task thuộc cả hai phòng ban. Số dòng bị tác động trong bảng đích không phản ánh đầy đủ tổng số dòng cascade ở các bảng con.

Trước khi chạy, kiểm tra từng cấp:

~~~sql
SELECT COUNT(*) AS departments_to_delete
FROM lab_c_department
WHERE department_id IN (10, 20);

SELECT COUNT(*) AS employees_affected
FROM lab_c_employee
WHERE department_id IN (10, 20);

SELECT COUNT(*) AS tasks_affected
FROM lab_c_task t
WHERE EXISTS (
    SELECT 1
    FROM lab_c_employee e
    WHERE e.employee_id = t.employee_id
      AND e.department_id IN (10, 20)
);
~~~

Các câu đếm cho biết quy mô dự kiến theo từng bảng. Sau khi xóa, cần kiểm tra lại cả bảng cha và các bảng con để xác nhận tác động.

## 12. Xóa bằng subquery và quan hệ giữa các bảng

Oracle cho phép dùng subquery trong điều kiện DELETE. Một số mẫu thường gặp:

### 12.1. Xóa task thuộc phòng ban

~~~sql
DELETE FROM lab_del_task t
WHERE EXISTS (
    SELECT 1
    FROM lab_del_employee e
    WHERE e.employee_id = t.employee_id
      AND e.department_id = 20
);
~~~

### 12.2. Xóa employee không có task

~~~sql
DELETE FROM lab_del_employee e
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_del_task t
    WHERE t.employee_id = e.employee_id
);
~~~

### 12.3. Xóa đơn hàng không có dòng chi tiết

~~~sql
DELETE FROM lab_order_header h
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_order_line l
    WHERE l.order_id = h.order_id
);
~~~

Đây là mẫu minh họa; các tên bảng trên không thuộc schema lab đã tạo ở phần 2. Nếu bảng chi tiết có khóa ngoại tham chiếu đơn hàng, những đơn không có dòng chi tiết có thể xóa mà không vi phạm quan hệ đó.

### 12.4. DELETE với điều kiện EXISTS không xóa bảng con tự động

**EXISTS** chỉ chọn các dòng của **bảng đích DELETE**. Nó không tự xóa những dòng của bảng khác. Muốn xóa nhiều bảng, cần nhiều lệnh DELETE theo thứ tự phù hợp hoặc dùng ON DELETE CASCADE đã được định nghĩa.

## 13. Một DELETE chỉ có một bảng đích

Oracle DELETE thông thường xóa dòng từ một bảng hoặc view đích. Không dùng cú pháp kiểu một số dialect:

~~~sql
-- Đây không phải cú pháp DELETE JOIN thông dụng của Oracle:
DELETE e, t
FROM employee e
JOIN task t ON t.employee_id = e.employee_id;
~~~

Để xóa từ một bảng dựa trên bảng khác, dùng correlated subquery/EXISTS:

~~~sql
DELETE FROM employee e
WHERE EXISTS (
    SELECT 1
    FROM department d
    WHERE d.department_id = e.department_id
      AND d.department_status = 'CLOSED'
);
~~~

Nếu cần xóa cả employee và task, thực hiện xóa task trước rồi employee, hoặc cấu hình cascade ở khóa ngoại phù hợp. Đừng giả định một câu DELETE có thể xóa đồng thời nhiều bảng như một thao tác JOIN.

## 14. Xóa trong quan hệ tự tham chiếu

Một bảng có thể chứa khóa ngoại tham chiếu chính nó, ví dụ nhân viên có quản lý:

~~~sql
CREATE TABLE lab_del_org_employee (
    employee_id NUMBER(6) PRIMARY KEY,
    manager_id  NUMBER(6),
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    CONSTRAINT fk_lab_del_manager
      FOREIGN KEY (manager_id)
      REFERENCES lab_del_org_employee (employee_id)
);
~~~

Nếu quản lý còn nhân viên cấp dưới tham chiếu, xóa quản lý sẽ bị khóa ngoại chặn theo hành vi mặc định. Có hai hướng thiết kế:

- Xóa các cấp dưới trước, đi từ lá lên gốc, nếu toàn bộ nhánh phải bị xóa.
- Khai báo **ON DELETE SET NULL** nếu khi quản lý rời hệ thống, nhân viên cấp dưới vẫn tồn tại và cần được gỡ liên kết.

Với cây tổ chức sâu, cần xác định toàn bộ descendants trước khi xóa. Oracle hỗ trợ truy vấn phân cấp bằng **CONNECT BY**:

~~~sql
SELECT employee_id, manager_id, LEVEL AS hierarchy_level
FROM lab_del_org_employee
START WITH employee_id = :root_employee_id
CONNECT BY PRIOR employee_id = manager_id;
~~~

Truy vấn trên liệt kê nhân viên gốc và các cấp dưới. Để xóa một cây trong quan hệ tự tham chiếu không cascade, phải xóa các nút lá trước khi xóa nút cha; thứ tự này có thể được xây dựng bằng LEVEL giảm dần trong một bước chọn khóa, nhưng cần xử lý trường hợp nhiều nhánh, chu trình dữ liệu và khóa ngoại cụ thể. Không chạy DELETE gốc trước khi xử lý các descendants.

## 15. DEFERRABLE constraint và thời điểm kiểm tra khóa ngoại

Thông thường, Oracle kiểm tra foreign key ngay tại thời điểm câu DML cần kiểm tra tính toàn vẹn. Constraint được khai báo **DEFERRABLE** có thể được trì hoãn kiểm tra đến cuối transaction hoặc thời điểm được chỉ định.

Ví dụ khai báo:

~~~sql
CONSTRAINT fk_child_parent
  FOREIGN KEY (parent_id)
  REFERENCES parent_table(parent_id)
  DEFERRABLE INITIALLY IMMEDIATE
~~~

Trong transaction, có thể yêu cầu trì hoãn:

~~~sql
SET CONSTRAINTS fk_child_parent DEFERRED;
~~~

Điều này có thể cho phép một chuỗi thao tác tạm thời vi phạm quan hệ trong transaction nhưng phải hợp lệ khi constraint được kiểm tra. Tuy nhiên, nó không tự xóa dữ liệu con và không thay thế chính sách cascade. Chỉ dùng khi mô hình nghiệp vụ thực sự cần trì hoãn kiểm tra; mặc định, xóa con trước rồi xóa cha thường dễ hiểu hơn.

## 16. Trigger và tác động phụ của DELETE

Một bảng có thể có trigger **BEFORE DELETE** hoặc **AFTER DELETE** ở mức dòng hoặc mức câu lệnh. Trigger có thể ghi audit, cập nhật bảng khác hoặc thực hiện quy tắc nghiệp vụ bổ sung.

Trước khi xóa trên hệ thống thực, hãy kiểm tra:

- Có trigger DELETE trên bảng đích không?
- Trigger có ghi log hoặc cập nhật bảng liên quan không?
- Có khóa ngoại cascade dẫn tới nhiều bảng không?
- Các thao tác cascade có tác động đến trigger trên bảng con theo hành vi Oracle của constraint/trigger đó không?
- Có audit policy hoặc cơ chế CDC/replication theo dõi thao tác xóa không?

Không nên giả định số dòng hiển thị từ DELETE phản ánh toàn bộ tác động của trigger và cascade. Nếu có trigger nghiệp vụ, hãy xem mã trigger và thử trong môi trường kiểm thử phù hợp.

## 17. DELETE nhiều dòng: undo, redo, khóa và hiệu năng

DELETE tạo thay đổi dữ liệu có thể rollback, vì vậy Oracle cần lưu thông tin undo và tạo redo theo cơ chế database. Với tập dữ liệu lớn, thao tác có thể:

- Chiếm thời gian do tìm dòng, kiểm tra constraint và thực thi trigger.
- Tạo lượng undo/redo đáng kể.
- Giữ row lock đến khi transaction kết thúc.
- Làm các session khác chờ nếu cùng truy cập dòng hoặc tài nguyên liên quan.
- Tăng chi phí cascade nếu một dòng cha có nhiều dòng con ở nhiều cấp.

### 17.1. Xóa theo lô

Nếu cần xóa lượng lớn theo batch, có thể chọn một số ROWID rồi xóa:

~~~sql
DELETE FROM lab_del_task
WHERE ROWID IN (
    SELECT rid
    FROM (
        SELECT ROWID AS rid
        FROM lab_del_task
        WHERE task_status = 'DONE'
          AND created_at < DATE '2025-01-01'
        ORDER BY created_at, task_id
    )
    WHERE ROWNUM <= 1000
);
~~~

Đây là mẫu minh họa batch tối đa 1000 dòng mỗi lần. Query con sắp xếp ứng viên rồi dùng ROWNUM để giới hạn số ROWID. Cần chạy lặp lại có kiểm soát cho đến khi không còn dòng phù hợp; mỗi batch có thể được commit theo chính sách transaction của ứng dụng.

Batching làm thay đổi đặc tính transaction: nếu commit sau mỗi batch, các batch trước không thể rollback cùng batch sau. Với dữ liệu cha-con, phải bảo đảm thứ tự xóa đúng ở mỗi batch và không để parent bị xóa khi còn child.

### 17.2. Không có DELETE ... LIMIT trực tiếp như một số dialect

~~~sql
-- Đây không phải cú pháp Oracle DELETE thông dụng:
DELETE FROM lab_del_task
WHERE task_status = 'DONE'
LIMIT 1000;
~~~

Hãy dùng subquery chọn ROWID/khóa với ROWNUM hoặc cú pháp phù hợp phiên bản Oracle.

### 17.3. Chỉ số trên khóa ngoại

Oracle không tự động tạo index cho mọi foreign key. Index trên cột khóa ngoại có thể hữu ích cho việc tìm dòng con, JOIN và một số thao tác bảo trì/xóa cha. Khi xóa cha, việc Oracle cần kiểm tra dòng con tham chiếu có thể tốn kém nếu bảng con lớn và cột FK không có index phù hợp.

Không tạo index một cách máy móc: xem workload đọc/ghi, cardinality, tính chọn lọc và execution plan. Index làm tăng chi phí INSERT/UPDATE/DELETE trên bảng con.

## 18. Khóa và thay đổi đồng thời

Giữa lúc SELECT xem trước và lúc DELETE chạy, session khác có thể chèn hoặc thay đổi dòng liên quan. Vì thế kết quả SELECT trước đó không tự bảo đảm tập dòng sẽ giống hệt lúc DELETE thực thi.

Một số điểm cần hiểu:

- DELETE khóa các dòng bị tác động theo cơ chế row locking của Oracle.
- Khóa được giữ đến COMMIT hoặc ROLLBACK.
- Kiểm tra khóa ngoại và cascade có thể làm thao tác ảnh hưởng đến nhiều dòng liên quan.
- Nếu cần kiểm soát tập cha trước khi xóa trong transaction, có thể cân nhắc **SELECT ... FOR UPDATE** trên các dòng cha phù hợp; điều này không tự khóa mọi dòng con chưa được chọn và cần thiết kế đồng bộ giữa các đường ghi.
- Mức cô lập, thứ tự khóa và retry khi deadlock phải phù hợp với ứng dụng.

Không giữ transaction xóa lớn mở lâu hơn cần thiết. Ngược lại, cũng không chia transaction tùy tiện nếu nghiệp vụ yêu cầu tất cả thao tác cha-con thành công hoặc thất bại cùng nhau.

## 19. Xem khóa ngoại và hành động ON DELETE trong data dictionary

Có thể xem constraint của schema hiện tại qua **USER_CONSTRAINTS**:

~~~sql
SELECT
    constraint_name,
    table_name,
    constraint_type,
    status,
    delete_rule,
    deferrable,
    deferred
FROM user_constraints
WHERE constraint_type = 'R'
  AND table_name IN (
      'LAB_DEL_EMPLOYEE',
      'LAB_DEL_TASK',
      'LAB_C_EMPLOYEE',
      'LAB_C_TASK'
  )
ORDER BY table_name, constraint_name;
~~~

Các cột đáng chú ý:

- **CONSTRAINT_TYPE = 'R'**: foreign key.
- **STATUS**: constraint đang ENABLED hay DISABLED.
- **DELETE_RULE**: hành động xóa tham chiếu, ví dụ NO ACTION, CASCADE hoặc SET NULL theo metadata Oracle.
- **DEFERRABLE** và **DEFERRED**: khả năng/trạng thái trì hoãn kiểm tra.

Muốn biết cột nào tham gia khóa ngoại, nối **USER_CONS_COLUMNS**:

~~~sql
SELECT
    c.constraint_name,
    c.table_name,
    cc.column_name,
    c.r_constraint_name,
    c.delete_rule
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
WHERE c.constraint_type = 'R'
ORDER BY c.table_name, c.constraint_name, cc.position;
~~~

Nếu xem object thuộc schema khác và có quyền phù hợp, dùng các view **ALL_CONSTRAINTS/ALL_CONS_COLUMNS** hoặc **DBA_CONSTRAINTS/DBA_CONS_COLUMNS** theo quyền được cấp. Không cần cấp quyền DBA chỉ để thực hành trong schema của chính mình.

## 20. Vì sao không nên tắt khóa ngoại để xóa cha?

Một cách xử lý nguy hiểm là disable foreign key, xóa dòng cha, rồi quên kiểm tra hoặc bật lại constraint. Khi đó bảng con có thể chứa khóa ngoại không còn dòng cha tương ứng (orphan).

Nếu thật sự cần thao tác bảo trì đặc biệt, phải có kế hoạch:

1. Xác định toàn bộ quan hệ và dữ liệu bị ảnh hưởng.
2. Có bản sao/khả năng phục hồi phù hợp với quy trình vận hành.
3. Thực hiện trong cửa sổ bảo trì được kiểm soát.
4. Kiểm tra orphan trước khi enable lại constraint.
5. Bật lại constraint và xác nhận trạng thái ENABLED/VALIDATED.

Trong thao tác ứng dụng bình thường, hãy giữ khóa ngoại hoạt động và xóa con trước, hoặc dùng hành động ON DELETE đã được thiết kế.

## 21. DELETE và TRUNCATE khi bảng đang được tham chiếu

**DELETE** theo điều kiện có thể xóa một phần dữ liệu và tôn trọng khóa ngoại. **TRUNCATE** là DDL xóa toàn bộ dữ liệu của bảng; Oracle có giới hạn khi bảng cha được tham chiếu bởi khóa ngoại đang bật. Trong trường hợp đó, TRUNCATE bảng cha có thể bị từ chối (ví dụ lỗi **ORA-02266**) ngay cả khi bảng con không có dòng tham chiếu, tùy cấu hình constraint.

Không chuyển từ DELETE sang TRUNCATE chỉ để tránh xử lý quan hệ cha-con. Hãy chọn lệnh theo yêu cầu transaction, điều kiện lọc và quan hệ dữ liệu.

## 22. Lỗi thường gặp và cách xử lý

| Lỗi/dấu hiệu | Nguyên nhân | Hướng xử lý |
|---|---|---|
| **ORA-02292: child record found** | Xóa cha khi còn dòng con tham chiếu | Xóa con trước hoặc dùng ON DELETE CASCADE/SET NULL đã được thiết kế |
| **ORA-02291: parent key not found** | Chèn/cập nhật khóa ngoại trỏ tới cha không tồn tại | Tạo cha trước hoặc sửa khóa ngoại |
| **ORA-01400: cannot insert NULL** | Hành động SET NULL xung đột với cột NOT NULL | Thiết kế cột nullable hoặc chọn chính sách xóa khác |
| Xóa nhiều dòng hơn dự kiến | WHERE quá rộng, AND/OR sai hoặc subquery chọn nhầm | Chạy SELECT cùng predicate, COUNT và kiểm tra khóa trước |
| Không xóa được dù SELECT thấy dữ liệu | Quyền, view, trigger, constraint hoặc session khác | Đọc lỗi Oracle cụ thể và kiểm tra đối tượng liên quan |
| Session bị chờ khóa | Transaction khác đang giữ lock | Xác định blocker, timeout/retry theo quy trình ứng dụng |
| Xóa cha nhưng dữ liệu con còn | FK không cascade hoặc SET NULL, hoặc chỉ xóa một nhánh | Kiểm tra DELETE_RULE và toàn bộ FK liên quan |
| Orphan sau bảo trì | Constraint bị disable hoặc dữ liệu được nạp sai | Kiểm tra dữ liệu tham chiếu và enable/validate constraint |

## 23. Bài tập thực hành

### Bài 1 — Xóa theo điều kiện đơn giản

Xóa các task có trạng thái CANCELLED trong bảng **LAB_DEL_TASK**.

**Gợi ý:**

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'CANCELLED';
~~~

Trước khi chạy, dùng SELECT với cùng điều kiện để xem các task được chọn.

### Bài 2 — Xóa theo khoảng ngày

Xóa các task DONE được tạo trong năm 2024.

**Gợi ý:** dùng khoảng **created_at >= DATE '2024-01-01' AND created_at < DATE '2025-01-01'**.

### Bài 3 — Xóa task của nhân viên inactive

Viết DELETE dùng EXISTS để xóa task thuộc nhân viên có **EMPLOYEE_STATUS = 'INACTIVE'**.

**Câu hỏi:** Vì sao EXISTS phù hợp hơn việc JOIN trực tiếp trong cú pháp DELETE của một số hệ quản trị khác?

**Định hướng:** Oracle DELETE có một bảng đích; EXISTS chọn các dòng của bảng đích dựa trên bảng liên quan.

### Bài 4 — Xóa phòng ban theo cách không cascade

Xóa phòng ban 10 trong schema **LAB_DEL_***. Hãy liệt kê thứ tự DELETE cần thực hiện để không vi phạm khóa ngoại.

**Đáp án định hướng:** xóa task của employee thuộc phòng 10; xóa employee thuộc phòng 10; cuối cùng xóa department 10.

### Bài 5 — Quan sát ORA-02292

Trên dữ liệu lab chưa bị xóa, thử xóa phòng ban có nhân viên mà không xóa con trước.

**Câu hỏi:** Constraint nào chặn thao tác và tại sao?

**Định hướng:** **FK_LAB_DEL_EMP_DEPT** tham chiếu phòng ban từ employee.

### Bài 6 — Kiểm tra ON DELETE CASCADE

Tạo lại bộ bảng **LAB_C_***, xóa department 10 rồi kiểm tra employee/task.

**Câu hỏi:** Vì sao chỉ một DELETE ở bảng department có thể làm mất nhiều dòng ở hai bảng con?

**Định hướng:** các foreign key tương ứng được khai báo ON DELETE CASCADE ở từng cấp.

### Bài 7 — Kiểm tra ON DELETE SET NULL

Tạo bảng **LAB_S_***, xóa department 10 và kiểm tra employee.

**Câu hỏi:** Vì sao employee còn tồn tại nhưng department_id trở thành NULL?

**Định hướng:** foreign key khai báo ON DELETE SET NULL và cột department_id cho phép NULL.

### Bài 8 — Đếm phạm vi xóa

Viết ba SELECT COUNT để đếm số department, employee và task bị ảnh hưởng nếu xóa một department theo cascade.

**Định hướng:** đếm cha bằng điều kiện khóa; đếm con theo FK; đếm cháu bằng EXISTS nối qua bảng con.

### Bài 9 — Xóa theo lô

Viết câu DELETE dùng ROWID và ROWNUM để xóa tối đa 100 task DONE cũ mỗi lượt.

**Câu hỏi:** Nếu commit sau mỗi batch, có thể rollback toàn bộ các batch đã commit không?

**Đáp án:** Không. Mỗi COMMIT kết thúc transaction của batch đó; rollback chỉ hoàn tác thay đổi chưa commit trong transaction hiện tại.

## 24. Quy trình xóa dữ liệu cha-con an toàn

Trước một thao tác xóa có liên quan nhiều bảng, đi theo quy trình:

1. **Xác định bảng đích và khóa:** dòng cha nào cần xóa, điều kiện nào xác định chính xác?
2. **Tra cứu foreign key:** những bảng nào tham chiếu bảng đích, trực tiếp và gián tiếp?
3. **Xác định delete rule:** mặc định chặn, CASCADE hay SET NULL?
4. **Xem dữ liệu bị ảnh hưởng:** SELECT và COUNT ở từng cấp, kiểm tra cả nhánh con sâu nhất.
5. **Chọn chiến lược:** xóa con trước, cascade đã được thiết kế, hay set null theo nghiệp vụ.
6. **Thực hiện trong transaction phù hợp:** dùng SAVEPOINT khi cần, không commit trước khi kiểm tra.
7. **Kiểm tra kết quả:** xác nhận cha, con, cháu và dữ liệu audit/trạng thái liên quan.
8. **Kết thúc transaction:** COMMIT khi kết quả đúng; ROLLBACK nếu có sai lệch.

Sơ đồ quyết định:

~~~text
Cần xóa dòng cha?
        |
        v
Có dòng con tham chiếu không?
       / \
     Không Có
      |    |
      |    v
      |  Kiểm tra ON DELETE rule
      |       |
      |   +---+---+
      |   |       |
      |   v       v
      | CASCADE  SET NULL
      |   |       |
      |   v       v
      | Xóa con  Giữ con, gỡ FK
      | tự động  (cột phải nullable)
      |   |       |
      |   +---+---+
      |       |
      |       v
      |    Kiểm tra tác động
      |
      +------> DELETE cha
                 |
                 v
          Kiểm tra kết quả
                 |
            +----+----+
            |         |
           Đúng      Sai
            |         |
            v         v
          COMMIT    ROLLBACK
~~~

**DELETE ... WHERE** quyết định **dòng nào bị xóa**; khóa ngoại quyết định **có được xóa dòng cha khi còn con hay không và dữ liệu con sẽ được xử lý thế nào**. Khi nắm rõ hai phần này, ta có thể xóa dữ liệu theo điều kiện chính xác, giữ toàn vẹn tham chiếu và kiểm soát được tác động trên toàn bộ cây quan hệ cha-con.
