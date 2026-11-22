# View có thể cập nhật, key-preserved table và WITH CHECK OPTION

Trong Oracle Database, **view** là một đối tượng schema lưu định nghĩa truy vấn và trình bày dữ liệu từ một hoặc nhiều bảng hoặc view khác. View thường được dùng để đơn giản hóa truy vấn, giới hạn cột/hàng được hiển thị và tạo một giao diện dữ liệu ổn định cho ứng dụng. Một số view cho phép thực hiện INSERT, UPDATE hoặc DELETE trực tiếp thông qua tên view; những view khác chỉ dùng để đọc.

Khả năng cập nhật phụ thuộc vào cấu trúc truy vấn định nghĩa view và quan hệ giữa các bảng nguồn. Với view đơn giản trên một bảng, Oracle thường có thể xác định hàng nguồn cần thay đổi. Với view JOIN, khái niệm **key-preserved table** quyết định bảng nguồn nào có thể được sửa an toàn qua view. Hai tùy chọn quan trọng bổ sung là:

- **WITH CHECK OPTION**: yêu cầu hàng được INSERT hoặc UPDATE thông qua view vẫn thỏa điều kiện của view sau khi thay đổi.
- **WITH READ ONLY**: cấm DML thông qua view.

Nếu một view phức tạp không tự cập nhật được, có thể dùng **INSTEAD OF trigger** để định nghĩa cách chuyển một thao tác trên view thành DML trên các bảng nền.

Bài học trình bày view updatable, key preservation, các giới hạn DML trên join view, lỗi Oracle thường gặp, WITH CHECK OPTION, WITH READ ONLY, metadata kiểm tra khả năng cập nhật và ví dụ thực hành.

## 1. View là giao diện logic trên dữ liệu

View thông thường được tạo bằng CREATE VIEW:

~~~sql
CREATE OR REPLACE VIEW v_employee_public AS
SELECT employee_id,
       full_name,
       department_id
FROM employees
WHERE status = 'ACTIVE';
~~~

View V_EMPLOYEE_PUBLIC không lưu một bản sao dữ liệu nhân viên theo cách của materialized view. Nó lưu định nghĩa truy vấn. Khi truy vấn view, Oracle phân tích định nghĩa và lấy dữ liệu từ các đối tượng nguồn theo snapshot của câu lệnh.

Có thể đọc view như bảng:

~~~sql
SELECT employee_id, full_name
FROM v_employee_public
ORDER BY employee_id;
~~~

Có thể dùng view làm nguồn cho JOIN, subquery, aggregate và nhiều thao tác SELECT khác.

### 1.1. View không nhất thiết là chỉ đọc

Với view đơn giản, các thao tác sau có thể hợp lệ:

~~~sql
UPDATE v_employee_public
SET full_name = 'An Nguyen'
WHERE employee_id = 101;
~~~

Nếu view updatable và cột FULL_NAME ánh xạ trực tiếp tới một cột của bảng nền, Oracle có thể cập nhật EMPLOYEES.

Tương tự, có thể INSERT hoặc DELETE qua view nếu các điều kiện về khả năng cập nhật, cột bắt buộc và constraint được đáp ứng.

### 1.2. View không phải bản sao dữ liệu

~~~sql
CREATE VIEW v_active_orders AS
SELECT order_id, customer_id, status
FROM orders
WHERE status = 'ACTIVE';
~~~

Khi bảng ORDERS thay đổi và transaction COMMIT, truy vấn view sau đó sẽ phản ánh dữ liệu nền theo read consistency của statement. Không cần refresh view như materialized view.

Điều này cũng có nghĩa DML qua view tác động tới bảng nền. Nếu UPDATE qua V_ACTIVE_ORDERS thành công, hàng ORDERS tương ứng thay đổi.

## 2. View đơn giản có thể cập nhật

Một view đơn giản thường chọn trực tiếp các cột từ một bảng nền, có thể kèm điều kiện WHERE:

~~~sql
CREATE OR REPLACE VIEW v_employee_edit AS
SELECT employee_id,
       full_name,
       department_id,
       salary,
       status
FROM employees
WHERE department_id = 10;
~~~

Đây là dạng view thường có thể cập nhật vì mỗi hàng view ánh xạ tới một hàng của EMPLOYEES và các cột hiển thị là cột trực tiếp.

Ví dụ:

~~~sql
UPDATE v_employee_edit
SET salary = salary + 1000000
WHERE employee_id = 101;
~~~

Oracle cập nhật hàng tương ứng trong EMPLOYEES. Nếu EMPLOYEE_ID không thuộc phòng 10, hàng đó không xuất hiện trong view và không được câu UPDATE tìm thấy.

### 2.1. Điều kiện phổ biến làm view không tự cập nhật được

Các cấu trúc truy vấn có thể khiến view hoặc một phần cột của view không updatable gồm:

- DISTINCT.
- Aggregate như SUM, AVG, COUNT, MIN, MAX trong select list.
- GROUP BY hoặc HAVING.
- Set operators như UNION, UNION ALL, INTERSECT, MINUS.
- Một số truy vấn phân cấp hoặc cấu trúc truy vấn phức tạp khác.
- Biểu thức tính toán trong select list đối với chính cột biểu thức đó.

Ví dụ view tổng hợp:

~~~sql
CREATE OR REPLACE VIEW v_department_salary AS
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS avg_salary
FROM employees
GROUP BY department_id;
~~~

View này biểu diễn một hàng cho mỗi phòng ban, không phải một hàng nhân viên cụ thể. Oracle không thể suy ra một UPDATE lên AVG_SALARY phải thay đổi SALARY của nhân viên nào. Vì vậy, DML trực tiếp trên view tổng hợp không tự động có ý nghĩa.

### 2.2. Cột biểu thức không phải cột nền có thể cập nhật

~~~sql
CREATE OR REPLACE VIEW v_employee_compensation AS
SELECT employee_id,
       salary,
       salary * 12 AS annual_salary
FROM employees;
~~~

Cột SALARY ánh xạ trực tiếp tới EMPLOYEES.SALARY. Cột ANNUAL_SALARY là biểu thức tính từ SALARY.

Có thể cập nhật cột nền nếu view và các điều kiện khác cho phép:

~~~sql
UPDATE v_employee_compensation
SET salary = 25000000
WHERE employee_id = 101;
~~~

Không thể gán trực tiếp một giá trị vào ANNUAL_SALARY như thể nó là cột lưu trữ độc lập. Oracle không tự suy ra phép biến đổi ngược từ annual salary về salary.

### 2.3. View có WHERE vẫn có thể cập nhật

WHERE tự nó không làm view trở thành read-only:

~~~sql
CREATE OR REPLACE VIEW v_high_salary_employee AS
SELECT employee_id, full_name, salary
FROM employees
WHERE salary >= 20000000;
~~~

Câu UPDATE trên view có thể sửa SALARY của hàng hiện có. Nếu không có WITH CHECK OPTION, thao tác có thể làm hàng không còn thỏa điều kiện WHERE và biến mất khỏi view sau khi cập nhật.

Đây là lý do WITH CHECK OPTION quan trọng khi view được dùng như một giao diện DML có điều kiện.

## 3. Key-preserved table là gì?

**Key-preserved table** là bảng có khóa vẫn duy nhất trong kết quả JOIN của view. Nói cách khác, mỗi hàng của bảng đó xuất hiện tối đa một lần trong kết quả join theo quan hệ đang xét.

Oracle cần xác định rằng một hàng view tương ứng với một hàng cụ thể của bảng nền để biết chính xác DML phải thay đổi hàng nào. Nếu một hàng bảng nền bị nhân thành nhiều hàng trong join result, việc cập nhật hoặc xóa qua view có thể mơ hồ.

Một bảng được xem là key-preserved khi khóa của nó vẫn là khóa của kết quả join. Oracle xác định điều này dựa trên metadata khóa/unique constraint phù hợp, không chỉ bằng cách quan sát dữ liệu hiện tại tình cờ không có duplicate.

### 3.1. Ví dụ quan hệ phòng ban và nhân viên

Giả sử:
- DEPARTMENTS có một hàng cho mỗi DEPARTMENT_ID.
- EMPLOYEES có nhiều nhân viên trong cùng một DEPARTMENT_ID.
- EMPLOYEES.DEPARTMENT_ID tham chiếu DEPARTMENTS.DEPARTMENT_ID.

Quan hệ:

~~~text
DEPARTMENTS
+---------------+-----------------+
| DEPARTMENT_ID | DEPARTMENT_NAME |
+---------------+-----------------+
| 10            | Sales           |
| 20            | Engineering     |
+---------------+-----------------+

EMPLOYEES
+-------------+---------------+-----------+
| EMPLOYEE_ID | DEPARTMENT_ID | FULL_NAME |
+-------------+---------------+-----------+
| 101         | 10            | An        |
| 102         | 10            | Binh      |
| 201         | 20            | Chi       |
+-------------+---------------+-----------+
~~~

JOIN:

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Kết quả:

| EMPLOYEE_ID | FULL_NAME | DEPARTMENT_ID | DEPARTMENT_NAME |
| ---: | --- | ---: | --- |
| 101 | An | 10 | Sales |
| 102 | Binh | 10 | Sales |
| 201 | Chi | 20 | Engineering |

Mỗi nhân viên chỉ xuất hiện một lần vì DEPARTMENTS.DEPARTMENT_ID là khóa duy nhất. EMPLOYEE_ID vẫn duy nhất trong kết quả JOIN, nên EMPLOYEES là key-preserved table.

Ngược lại, hàng DEPARTMENTS có DEPARTMENT_ID = 10 xuất hiện hai lần, một lần cho An và một lần cho Binh. Khóa của DEPARTMENTS không còn duy nhất trong kết quả JOIN. DEPARTMENTS không phải key-preserved table trong view này.

### 3.2. Key preservation phụ thuộc chiều JOIN và constraint

Với view:

~~~sql
SELECT e.employee_id,
       e.full_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

- EMPLOYEES có thể là key-preserved nhờ mỗi EMPLOYEE_ID chỉ xuất hiện một lần.
- DEPARTMENTS không key-preserved vì một phòng ban có thể ghép với nhiều nhân viên.

Nếu quan hệ thay đổi thành một-một và cả hai phía đều có khóa/unique constraint phù hợp, cả hai bảng có thể được key-preserved. Khi đó các quy tắc DML trên join view vẫn giới hạn mỗi câu DML chỉ sửa một bảng nền.

### 3.3. Dữ liệu hiện tại không thay thế constraint

Giả sử bảng DEPARTMENTS hiện tại không có hai hàng trùng DEPARTMENT_ID, nhưng không có PRIMARY KEY hoặc UNIQUE constraint bảo đảm điều đó. Oracle không thể chỉ dựa vào dữ liệu hiện thời để cam kết rằng JOIN sẽ không nhân bản hàng trong tương lai.

Để Oracle xác định key preservation, khai báo khóa phù hợp:

~~~sql
ALTER TABLE departments
ADD CONSTRAINT pk_departments
PRIMARY KEY (department_id);
~~~

Nếu nghiệp vụ yêu cầu mã phòng duy nhất nhưng không phải primary key, có thể dùng UNIQUE constraint phù hợp. Constraint phải phản ánh đúng quy tắc dữ liệu; không tạo constraint chỉ để ép một view cập nhật được nếu dữ liệu nghiệp vụ không bảo đảm điều đó.

## 4. Join view và các giới hạn DML

Một **join view** là view có định nghĩa truy vấn kết hợp nhiều bảng. Khả năng cập nhật của join view phụ thuộc key-preserved table và các quy tắc Oracle.

Các nguyên tắc quan trọng:

1. Một câu DML trên join view chỉ được sửa một bảng nền.
2. UPDATE chỉ có thể sửa các cột ánh xạ tới bảng key-preserved.
3. INSERT phải ánh xạ việc chèn vào một bảng nền và thỏa các cột bắt buộc/constraint của bảng đó.
4. DELETE trên join view có quy tắc riêng: Oracle cần xác định một bảng key-preserved duy nhất để xóa hàng. Nếu không xác định được đúng một bảng như yêu cầu, câu lệnh có thể báo ORA-01752.
5. Nếu view không đáp ứng điều kiện tự cập nhật, có thể cần INSTEAD OF trigger.

### 4.1. UPDATE cột của key-preserved table

Với join view EMPLOYEE_DEPARTMENT, EMPLOYEES là key-preserved. Câu UPDATE sau có thể hợp lệ:

~~~sql
UPDATE v_employee_department
SET full_name = 'An Nguyen'
WHERE employee_id = 101;
~~~

FULL_NAME thuộc EMPLOYEES và mỗi hàng nhân viên xuất hiện tối đa một lần trong view. Oracle có thể xác định chính xác hàng nhân viên cần cập nhật.

### 4.2. UPDATE cột của non-key-preserved table

Câu sau cố sửa tên phòng ban qua join view:

~~~sql
UPDATE v_employee_department
SET department_name = 'Sales North'
WHERE employee_id = 101;
~~~

Trong mô hình một phòng ban có nhiều nhân viên, DEPARTMENTS không key-preserved trong join view. Oracle không cho phép cập nhật cột của bảng không key-preserved theo cách này và có thể báo:

~~~text
ORA-01779: cannot modify a column which maps to a non key-preserved table
~~~

Nếu mục tiêu là đổi tên phòng ban, hãy UPDATE trực tiếp bảng DEPARTMENTS theo khóa:

~~~sql
UPDATE departments
SET department_name = 'Sales North'
WHERE department_id = 10;
~~~

Không dùng join view để sửa một bảng mà khóa của nó bị nhân bản trong kết quả JOIN.

### 4.3. Một câu UPDATE không sửa hai bảng nền

Không thể dùng một UPDATE qua join view để đồng thời thay đổi cột của EMPLOYEES và DEPARTMENTS:

~~~sql
-- Không hợp lệ: hai cột thuộc hai bảng nền khác nhau.
UPDATE v_employee_department
SET full_name = 'An Nguyen',
    department_name = 'Sales North'
WHERE employee_id = 101;
~~~

Oracle có thể báo ORA-01776:

~~~text
ORA-01776: cannot modify more than one base table through a join view
~~~

Hãy thực hiện hai câu UPDATE riêng trên hai bảng nền trong cùng transaction nếu nghiệp vụ cần cả hai thay đổi cùng thành công hoặc thất bại:

~~~sql
UPDATE employees
SET full_name = 'An Nguyen'
WHERE employee_id = 101;

UPDATE departments
SET department_name = 'Sales North'
WHERE department_id = 10;

COMMIT;
~~~

Cả hai câu DML vẫn có thể thuộc cùng một transaction. Giới hạn một bảng nền áp dụng cho từng câu DML qua join view, không có nghĩa một transaction chỉ được sửa một bảng.

### 4.4. INSERT qua join view

INSERT qua join view có thể hợp lệ khi Oracle xác định được bảng nền đích và các cột được cung cấp thuộc bảng key-preserved phù hợp. Một câu INSERT không được cố chèn vào nhiều bảng nền cùng lúc.

Ví dụ nếu view chứa các cột EMPLOYEE_ID, FULL_NAME và DEPARTMENT_ID từ EMPLOYEES cùng DEPARTMENT_NAME từ DEPARTMENTS, INSERT chỉ cung cấp các cột nhân viên có thể chèn vào EMPLOYEES nếu:
- EMPLOYEES là bảng key-preserved.
- DEPARTMENT_ID tham chiếu một phòng ban có thật.
- Mọi cột NOT NULL không có default của EMPLOYEES đều được cung cấp.
- Không có giới hạn view/constraint khác ngăn DML.

Ví dụ:

~~~sql
INSERT INTO v_employee_department (
    employee_id,
    full_name,
    department_id
)
VALUES (301, 'Dung', 10);
~~~

Oracle chèn một hàng EMPLOYEES. Câu INSERT không đồng thời tạo phòng ban mới; DEPARTMENT_ID=10 phải tồn tại.

Nếu cố cung cấp cả cột nhân viên và cột tên phòng ban để tạo hai hàng ở hai bảng qua một INSERT, Oracle có thể báo ORA-01776. Hãy INSERT vào từng bảng theo thứ tự và trong cùng transaction.

### 4.5. DELETE qua join view

Oracle chỉ cho phép DELETE từ join view khi có thể xác định một key-preserved table duy nhất làm mục tiêu xóa. Nếu view có nhiều bảng key-preserved hoặc không có đúng một bảng phù hợp, có thể gặp:

~~~text
ORA-01752: cannot delete from view without exactly one key-preserved table
~~~

Trong ví dụ quan hệ nhiều nhân viên - một phòng ban, EMPLOYEES là bảng key-preserved duy nhất. DELETE qua view có thể xóa hàng nhân viên tương ứng:

~~~sql
DELETE FROM v_employee_department
WHERE employee_id = 101;
~~~

Thao tác này xóa hàng EMPLOYEES của nhân viên 101, không xóa phòng ban 10. Đừng suy luận rằng DELETE một hàng hiển thị trong join view sẽ xóa cả hai hàng nguồn.

Nếu mục tiêu là xóa phòng ban, hãy dùng DML trực tiếp trên DEPARTMENTS và xử lý foreign key/cascade theo quy tắc nghiệp vụ.

## 5. WITH CHECK OPTION: buộc hàng vẫn thỏa điều kiện view

Một view có thể giới hạn hàng bằng WHERE. Nếu DML qua view làm hàng không còn thỏa WHERE, hàng sẽ biến mất khỏi view. Đôi khi đây là hành vi không mong muốn vì ứng dụng dùng view như một vùng dữ liệu có chính sách cố định.

**WITH CHECK OPTION** yêu cầu mọi hàng được INSERT hoặc UPDATE qua view phải tiếp tục thỏa điều kiện của view sau thao tác.

Cú pháp:

~~~sql
CREATE OR REPLACE VIEW view_name AS
SELECT column_list
FROM table_name
WHERE condition
WITH CHECK OPTION [CONSTRAINT constraint_name];
~~~

Tên constraint là tùy chọn. Đặt tên giúp thông báo lỗi và metadata dễ nhận diện hơn.

### 5.1. View không có CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_active_employee AS
SELECT employee_id,
       full_name,
       department_id,
       status
FROM employees
WHERE status = 'ACTIVE';
~~~

Giả sử hàng nhân viên 101 có STATUS='ACTIVE'. Câu lệnh:

~~~sql
UPDATE v_active_employee
SET status = 'INACTIVE'
WHERE employee_id = 101;
~~~

có thể thành công nếu các điều kiện updatable khác được đáp ứng. Sau UPDATE, hàng 101 không còn thỏa WHERE STATUS='ACTIVE', nên không xuất hiện trong view nữa.

Đây là hành vi hợp lệ nếu ứng dụng chấp nhận việc cập nhật một hàng khiến nó rời khỏi view.

### 5.2. View có WITH CHECK OPTION

Tạo view:

~~~sql
CREATE OR REPLACE VIEW v_active_employee_checked AS
SELECT employee_id,
       full_name,
       department_id,
       status
FROM employees
WHERE status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT v_active_employee_ck;
~~~

Thử:

~~~sql
UPDATE v_active_employee_checked
SET status = 'INACTIVE'
WHERE employee_id = 101;
~~~

Oracle từ chối thao tác vì hàng sau UPDATE không còn thỏa STATUS='ACTIVE'. Lỗi thường gặp:

~~~text
ORA-01402: view WITH CHECK OPTION where-clause violation
~~~

Hàng vẫn giữ trạng thái trước UPDATE vì câu lệnh bị từ chối.

### 5.3. INSERT cũng phải thỏa điều kiện view

~~~sql
INSERT INTO v_active_employee_checked (
    employee_id,
    full_name,
    department_id,
    status
)
VALUES (501, 'Mai', 10, 'ACTIVE');
~~~

INSERT có thể thành công nếu các constraint bảng nền được đáp ứng.

Ngược lại:

~~~sql
INSERT INTO v_active_employee_checked (
    employee_id,
    full_name,
    department_id,
    status
)
VALUES (502, 'Nam', 10, 'INACTIVE');
~~~

bị từ chối vì hàng mới không thỏa điều kiện view.

Nếu STATUS bị bỏ khỏi danh sách INSERT và cột nền có default là ACTIVE, hàng có thể thỏa điều kiện; nếu không có default và cột NOT NULL, thao tác có thể thất bại do constraint của bảng nền trước hoặc trong quá trình kiểm tra.

### 5.4. CHECK OPTION chỉ áp dụng cho DML qua view

Nếu cập nhật trực tiếp bảng nền:

~~~sql
UPDATE employees
SET status = 'INACTIVE'
WHERE employee_id = 101;
~~~

điều kiện WITH CHECK OPTION của V_ACTIVE_EMPLOYEE_CHECKED không được dùng như một constraint toàn bảng để chặn thao tác này. WITH CHECK OPTION kiểm soát thao tác DML đi qua view đó.

Nếu cần bảo đảm STATUS chỉ nhận một tập giá trị, dùng CHECK constraint trên bảng nền. Nếu cần người dùng chỉ sửa được một tập hàng/cột, xem xét quyền, view, VPD hoặc các cơ chế bảo mật phù hợp.

### 5.5. CHECK OPTION không thay thế constraint bảng

Giả sử view lọc DEPARTMENT_ID=10. WITH CHECK OPTION ngăn DML qua view đưa hàng ra khỏi phòng 10. Nhưng nó không thay thế:
- PRIMARY KEY.
- UNIQUE.
- NOT NULL.
- CHECK constraint.
- FOREIGN KEY.

Các constraint bảng nền vẫn được áp dụng. WITH CHECK OPTION chỉ bổ sung điều kiện của truy vấn định nghĩa view.

### 5.6. DELETE không cần hàng tiếp tục thỏa điều kiện

DELETE loại bỏ hàng khỏi bảng nền; hàng không còn để kiểm tra có thỏa WHERE hay không. WITH CHECK OPTION chủ yếu kiểm soát INSERT và UPDATE làm thay đổi trạng thái hàng. Nó không ngăn xóa một hàng chỉ vì sau khi xóa hàng không còn trong view.

Quyền DELETE, foreign key và các constraint liên quan vẫn được áp dụng.

## 6. WITH CHECK OPTION trong view lồng nhau

Một view có thể được xây trên một view khác. Ví dụ:

~~~sql
CREATE OR REPLACE VIEW v_department_10 AS
SELECT employee_id, full_name, department_id, status
FROM employees
WHERE department_id = 10
WITH CHECK OPTION CONSTRAINT v_dept10_ck;
~~~

Tạo view con:

~~~sql
CREATE OR REPLACE VIEW v_active_dept_10 AS
SELECT employee_id, full_name, department_id, status
FROM v_department_10
WHERE status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT v_active_dept10_ck;
~~~

DML qua view ngoài phải tuân thủ điều kiện của view ngoài và các điều kiện check option được kế thừa từ view nền theo quy tắc Oracle. Trong ví dụ:
- DEPARTMENT_ID phải là 10.
- STATUS phải là ACTIVE.

UPDATE làm hàng chuyển sang phòng 20 hoặc trạng thái INACTIVE sẽ vi phạm một trong các điều kiện được kiểm tra.

Khi thiết kế view lồng nhau, hãy kiểm tra rõ các điều kiện WHERE ở từng tầng. Đừng coi view ngoài là một bộ lọc độc lập nếu view nền đã có check option.

## 7. WITH READ ONLY: cấm DML qua view

Nếu view chỉ được phép đọc, có thể khai báo:

~~~sql
CREATE OR REPLACE VIEW v_employee_report AS
SELECT employee_id,
       full_name,
       department_id,
       salary
FROM employees
WITH READ ONLY;
~~~

SELECT vẫn hợp lệ:

~~~sql
SELECT *
FROM v_employee_report;
~~~

Nhưng DML qua view bị từ chối:

~~~sql
UPDATE v_employee_report
SET salary = salary + 100000
WHERE employee_id = 101;
~~~

Oracle báo lỗi vì view được khai báo read-only, thường là ORA-42399:

~~~text
ORA-42399: cannot perform a DML operation on a read-only view
~~~

### 7.1. READ ONLY trên view không làm bảng nền read-only

View V_EMPLOYEE_REPORT chỉ cấm DML thông qua chính view. Nếu user có quyền UPDATE trực tiếp EMPLOYEES, họ vẫn có thể cập nhật bảng nền theo quyền được cấp.

~~~sql
UPDATE employees
SET salary = salary + 100000
WHERE employee_id = 101;
~~~

Lệnh này không đi qua V_EMPLOYEE_REPORT. Muốn cấm người dùng thay đổi dữ liệu nền, phải quản lý privilege trên bảng nền và cấp quyền phù hợp trên view.

### 7.2. READ ONLY và CHECK OPTION là hai mục tiêu khác nhau

| Thuộc tính | WITH CHECK OPTION | WITH READ ONLY |
| --- | --- | --- |
| SELECT | Cho phép | Cho phép |
| INSERT qua view | Cho phép nếu hàng thỏa điều kiện và view insertable | Cấm |
| UPDATE qua view | Cho phép nếu hàng sau thay đổi vẫn thỏa điều kiện và view updatable | Cấm |
| DELETE qua view | Có thể cho phép nếu view updatable | Cấm |
| Mục tiêu | Giữ hàng trong phạm vi điều kiện view | Chỉ cho đọc qua view |

Hai tùy chọn biểu đạt hai chính sách khác nhau; không đặt cả hai như thể chúng bổ sung cùng một hành vi. Khi cần chỉ đọc, dùng WITH READ ONLY. Khi cho phép DML nhưng muốn giữ predicate, dùng WITH CHECK OPTION.

## 8. Kiểm tra metadata khả năng cập nhật

Oracle cung cấp các data dictionary views để xem cột nào của view có thể INSERT, UPDATE hoặc DELETE theo khả năng cập nhật mà database xác định.

Ví dụ:

~~~sql
SELECT table_name,
       column_name,
       updatable,
       insertable,
       deletable
FROM user_updatable_columns
WHERE table_name = 'V_EMPLOYEE_EDIT'
ORDER BY column_name;
~~~

Các cột:
- UPDATABLE: cột có thể được cập nhật qua view.
- INSERTABLE: cột có thể được đưa vào thao tác INSERT qua view.
- DELETABLE: metadata cho biết khả năng xóa qua view theo quy tắc của view.

Tên view trong data dictionary thường được lưu chữ hoa nếu được tạo không quote identifier. Nếu view thuộc schema khác, xem ALL_UPDATABLE_COLUMNS hoặc DBA_UPDATABLE_COLUMNS theo quyền.

### 8.1. Metadata không thay thế thử nghiệm DML

Một cột có UPDATABLE='YES' không đảm bảo mọi câu UPDATE đều thành công. Câu lệnh vẫn có thể thất bại vì:
- WHERE không tìm thấy hàng.
- Constraint bảng nền bị vi phạm.
- Trigger bảng nền từ chối thay đổi.
- Check option bị vi phạm.
- Thiếu quyền.
- Khóa hoặc xung đột transaction.
- Giá trị bind không hợp lệ.

Metadata giúp xác định khả năng ở mức cấu trúc view; điều kiện thực thi cụ thể vẫn cần được xét.

### 8.2. Xem định nghĩa view

~~~sql
SELECT view_name,
       text
FROM user_views
WHERE view_name = 'V_EMPLOYEE_EDIT';
~~~

USER_VIEWS cho biết định nghĩa view trong schema hiện tại. ALL_VIEWS và DBA_VIEWS cung cấp phạm vi rộng hơn theo quyền.

Định nghĩa view giúp kiểm tra:
- Cột nào ánh xạ trực tiếp tới bảng nền.
- Có JOIN hay không.
- Predicate WHERE nào đang được áp dụng.
- Có aggregate, DISTINCT hoặc cấu trúc làm hạn chế DML không.
- Có check option hoặc read-only clause trong metadata tương ứng hay không.

## 9. INSTEAD OF trigger cho view không tự cập nhật được

Một số view có mục đích trình bày dữ liệu tổng hợp hoặc kết hợp nhiều bảng. Không thể ánh xạ DML tự động một cách rõ ràng, nhưng ứng dụng vẫn muốn thao tác trên giao diện view.

Oracle hỗ trợ **INSTEAD OF trigger** trên view. Trigger chạy thay cho thao tác DML được gửi tới view và tự viết các câu INSERT/UPDATE/DELETE trên bảng nền.

Ví dụ view ghép EMPLOYEE và DEPARTMENT:

~~~sql
CREATE OR REPLACE VIEW v_employee_department_report AS
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Nếu muốn một thao tác INSERT trên view tạo hàng nhân viên, có thể viết INSTEAD OF trigger để ánh xạ cột:

~~~sql
CREATE OR REPLACE TRIGGER trg_v_emp_dept_insert
INSTEAD OF INSERT ON v_employee_department_report
FOR EACH ROW
BEGIN
    INSERT INTO employees (
        employee_id,
        full_name,
        department_id
    )
    VALUES (
        :NEW.employee_id,
        :NEW.full_name,
        :NEW.department_id
    );
END;
/
~~~

Trigger chỉ INSERT vào EMPLOYEES. DEPARTMENT_NAME được cung cấp trong view nhưng không dùng để tạo DEPARTMENTS. DEPARTMENT_ID phải tham chiếu phòng ban có sẵn; foreign key sẽ kiểm tra.

### 9.1. INSTEAD OF trigger phải tự định nghĩa quy tắc

Nếu view chứa nhiều bảng, trigger cần quyết định:
- Cột nào được ghi vào bảng nào.
- Khi INSERT, có tạo nhiều hàng ở các bảng nền hay không.
- Khi UPDATE, xác định khóa của từng bảng.
- Khi DELETE, xóa bảng nào và theo thứ tự nào.
- Xử lý constraint, duplicate, NULL và lỗi ra sao.
- Có cần bảo đảm các thay đổi cùng transaction không.

Trigger không tự làm cho một thao tác mơ hồ trở nên đúng nghiệp vụ. Nó chỉ cung cấp nơi để lập trình quy tắc ánh xạ.

### 9.2. INSTEAD OF trigger và transaction

DML trong trigger thông thường tham gia transaction của câu lệnh gọi. Nếu trigger phát sinh lỗi và câu lệnh thất bại, thay đổi của câu lệnh bị rollback theo quy tắc statement-level. COMMIT/ROLLBACK transaction nên do caller quản lý, không đặt COMMIT tùy tiện bên trong trigger.

Không dùng autonomous transaction cho DML chính của INSTEAD OF trigger nếu muốn các thay đổi bảng nền rollback cùng câu lệnh view.

### 9.3. INSTEAD OF trigger không phải cách mặc định cho mọi view

Nếu view đơn giản và tự updatable, không cần trigger chỉ để chuyển một UPDATE trực tiếp tới bảng nền. Trigger làm tăng độ phức tạp:
- Khó theo dõi DML thực tế.
- Có thể tạo logic cập nhật hai chiều không nhất quán.
- Cần kiểm thử nhiều trường hợp NULL/duplicate.
- Có thể ảnh hưởng hiệu năng.
- Dễ tạo side effect khó đoán.

Chỉ dùng khi view thực sự cần một giao diện DML tùy biến.

## 10. Ví dụ đầy đủ: key preservation và DML

Phần này tạo hai bảng sandbox, view JOIN và view có check option để quan sát các quy tắc.

### 10.1. Tạo bảng phòng ban

~~~sql
CREATE TABLE dept_view_demo (
    department_id   NUMBER(4)
        CONSTRAINT pk_dept_view_demo PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);
~~~

### 10.2. Tạo bảng nhân viên

~~~sql
CREATE TABLE emp_view_demo (
    employee_id   NUMBER(6)
        CONSTRAINT pk_emp_view_demo PRIMARY KEY,
    full_name     VARCHAR2(100 CHAR) NOT NULL,
    department_id NUMBER(4) NOT NULL,
    salary        NUMBER(12,2),
    status        VARCHAR2(10 CHAR) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT fk_emp_dept_view_demo
        FOREIGN KEY (department_id)
        REFERENCES dept_view_demo(department_id),
    CONSTRAINT ck_emp_status_view_demo
        CHECK (status IN ('ACTIVE', 'INACTIVE'))
);
~~~

### 10.3. Nạp dữ liệu

~~~sql
INSERT INTO dept_view_demo VALUES (10, 'Sales');
INSERT INTO dept_view_demo VALUES (20, 'Engineering');

INSERT INTO emp_view_demo
VALUES (101, 'An', 10, 20000000, 'ACTIVE');

INSERT INTO emp_view_demo
VALUES (102, 'Binh', 10, 18000000, 'ACTIVE');

INSERT INTO emp_view_demo
VALUES (201, 'Chi', 20, 30000000, 'ACTIVE');

COMMIT;
~~~

Phòng 10 có hai nhân viên; phòng 20 có một nhân viên.

### 10.4. Tạo join view

~~~sql
CREATE OR REPLACE VIEW v_emp_dept_demo AS
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       e.salary,
       d.department_name
FROM emp_view_demo e
JOIN dept_view_demo d
  ON d.department_id = e.department_id;
~~~

EMP_VIEW_DEMO là key-preserved vì EMPLOYEE_ID vẫn duy nhất trong kết quả. DEPT_VIEW_DEMO không key-preserved vì hàng phòng ban 10 xuất hiện hai lần.

### 10.5. UPDATE cột nhân viên qua view

~~~sql
UPDATE v_emp_dept_demo
SET salary = 21000000
WHERE employee_id = 101;

COMMIT;
~~~

Câu lệnh cập nhật EMP_VIEW_DEMO.SALARY. Kiểm tra:

~~~sql
SELECT employee_id, salary
FROM emp_view_demo
WHERE employee_id = 101;
~~~

Kết quả SALARY là 21.000.000.

### 10.6. Thử UPDATE cột phòng ban qua view

~~~sql
-- Có thể nhận ORA-01779 vì DEPT_VIEW_DEMO không key-preserved.
UPDATE v_emp_dept_demo
SET department_name = 'Sales North'
WHERE employee_id = 101;
~~~

Câu lệnh cố sửa cột của bảng không key-preserved trong join view. Thực hiện thay đổi tên phòng ban trực tiếp:

~~~sql
UPDATE dept_view_demo
SET department_name = 'Sales North'
WHERE department_id = 10;

COMMIT;
~~~

Cả hai nhân viên phòng 10 sẽ thấy tên phòng mới khi truy vấn view.

### 10.7. Tạo view có WITH CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_emp_active_demo AS
SELECT employee_id,
       full_name,
       department_id,
       salary,
       status
FROM emp_view_demo
WHERE status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT v_emp_active_ck_demo;
~~~

Thử cập nhật trạng thái:

~~~sql
UPDATE v_emp_active_demo
SET status = 'INACTIVE'
WHERE employee_id = 101;
~~~

Oracle từ chối vì hàng sau cập nhật không còn thỏa STATUS='ACTIVE'. Hãy thử thay đổi SALARY, thao tác đó vẫn thỏa predicate và có thể thành công:

~~~sql
UPDATE v_emp_active_demo
SET salary = salary + 500000
WHERE employee_id = 101;

COMMIT;
~~~

### 10.8. Tạo view READ ONLY

~~~sql
CREATE OR REPLACE VIEW v_emp_report_ro_demo AS
SELECT employee_id,
       full_name,
       department_id,
       salary
FROM emp_view_demo
WITH READ ONLY;
~~~

SELECT qua view hợp lệ. UPDATE qua view bị từ chối:

~~~sql
UPDATE v_emp_report_ro_demo
SET salary = salary + 100000
WHERE employee_id = 101;
~~~

Nhưng nếu user có quyền trên bảng nền, UPDATE trực tiếp EMP_VIEW_DEMO vẫn là một thao tác khác, không đi qua view READ ONLY.

### 10.9. Kiểm tra metadata

~~~sql
SELECT table_name,
       column_name,
       updatable,
       insertable,
       deletable
FROM user_updatable_columns
WHERE table_name IN (
    'V_EMP_DEPT_DEMO',
    'V_EMP_ACTIVE_DEMO',
    'V_EMP_REPORT_RO_DEMO'
)
ORDER BY table_name, column_name;
~~~

Kết quả cho biết Oracle nhận diện khả năng cập nhật của từng cột trong các view. Không suy luận rằng tất cả cột trong join view đều có cùng trạng thái.

### 10.10. Dọn bảng sandbox

~~~sql
DROP VIEW v_emp_report_ro_demo;
DROP VIEW v_emp_active_demo;
DROP VIEW v_emp_dept_demo;

DROP TABLE emp_view_demo PURGE;
DROP TABLE dept_view_demo PURGE;
~~~

Chỉ xóa các đối tượng sandbox do bài học tạo khi chắc chắn không cần dữ liệu. DROP là DDL và có implicit commit; thực hiện cleanup riêng, không trộn với transaction DML cần rollback.

## 11. Các lỗi Oracle thường gặp

| Mã lỗi | Ý nghĩa thường gặp trong ngữ cảnh view | Hướng xử lý |
| --- | --- | --- |
| ORA-01779 | Cập nhật cột ánh xạ tới bảng không key-preserved trong join view | Sửa trực tiếp bảng nền hoặc thiết kế lại view/constraint |
| ORA-01776 | Một DML qua join view cố sửa nhiều bảng nền | Tách thành nhiều DML trong cùng transaction hoặc dùng INSTEAD OF trigger có quy tắc rõ |
| ORA-01752 | DELETE qua join view không xác định được đúng một key-preserved table | DELETE trực tiếp bảng nền hoặc thiết kế view phù hợp |
| ORA-01732 | DML không hợp lệ trên view | Kiểm tra aggregate, DISTINCT, GROUP BY, set operator và cấu trúc view |
| ORA-01402 | DML vi phạm WHERE của view có WITH CHECK OPTION | Giữ hàng thỏa predicate hoặc thay đổi yêu cầu nghiệp vụ |
| ORA-42399 | DML trên view được khai báo WITH READ ONLY | Chỉ đọc qua view hoặc dùng giao diện ghi được cấp quyền riêng |
| ORA-01400 | INSERT tạo NULL cho cột NOT NULL của bảng nền | Cung cấp giá trị hoặc dùng default hợp lệ |
| ORA-02291 | Giá trị foreign key không có hàng cha tương ứng | Tạo/chọn khóa cha hợp lệ trước khi INSERT/UPDATE |

Thông báo lỗi cụ thể có thể phụ thuộc cấu trúc view và câu DML. Khi chẩn đoán, đọc cả định nghĩa view, constraint, trigger và cột đang được cập nhật.

## 12. Quyền truy cập và bảo mật khi dùng view

View có thể tạo giao diện chỉ hiển thị một phần dữ liệu:

~~~sql
CREATE OR REPLACE VIEW v_employee_directory AS
SELECT employee_id,
       full_name,
       department_id
FROM employees;
~~~

DBA có thể cấp quyền SELECT trên view cho một user thay vì cấp quyền SELECT toàn bộ bảng nền, tùy mô hình quyền và ownership.

~~~sql
GRANT SELECT ON v_employee_directory TO reporting_user;
~~~

Nếu user chỉ có quyền qua view, họ có thể đọc các cột được view cung cấp theo privilege chain phù hợp. Nếu muốn cho phép DML qua view, cần xem quyền cần thiết trên view/bảng nền, quyền sở hữu đối tượng và cơ chế privilege của Oracle.

**WITH READ ONLY không phải cơ chế phân quyền đầy đủ.** Nó ngăn DML qua view nhưng không tự thu hồi quyền DML trực tiếp trên bảng nền. Bảo mật phải được thiết kế bằng GRANT/REVOKE, schema ownership, VPD hoặc các cơ chế thích hợp.

### 12.1. View lọc hàng không tự động là ranh giới bảo mật tuyệt đối

Một view có WHERE STATUS='ACTIVE' giúp cung cấp tập dữ liệu giới hạn. Nhưng nếu user có quyền trực tiếp trên bảng nền, họ có thể truy vấn những hàng ngoài view. Nếu cần bảo đảm row-level security bất kể câu truy vấn đi qua đối tượng nào, cân nhắc Oracle Virtual Private Database (VPD) hoặc chính sách bảo mật ở tầng database.

WITH CHECK OPTION chỉ kiểm soát DML qua view; nó không phải row-level security policy.

### 12.2. Cấp quyền DML trên view có chủ đích

Nếu ứng dụng chỉ cần cập nhật SALARY qua view, hãy giới hạn quyền và cột theo nhu cầu. Không cấp quyền rộng hơn cần thiết. Quyền thực tế để DML thành công còn phụ thuộc bảng nền, view owner, invoker/definer rights và các quy tắc privilege của Oracle.

## 13. Thiết kế view updatable dễ bảo trì

Khi tạo view dùng làm giao diện ghi dữ liệu:

- Chỉ đưa các cột cần thiết vào view.
- Giữ ánh xạ cột trực tiếp, tránh expression không cần thiết trên cột cần UPDATE.
- Đặt WHERE thể hiện phạm vi dữ liệu rõ ràng.
- Dùng WITH CHECK OPTION nếu hàng phải tiếp tục nằm trong phạm vi view sau INSERT/UPDATE.
- Dùng WITH READ ONLY nếu mục tiêu chỉ đọc.
- Với join view, xác định key-preserved table bằng PK/UNIQUE constraint và quan hệ JOIN.
- Không cố sửa hai bảng nền qua một câu DML trên join view.
- Dùng INSTEAD OF trigger khi cần một giao diện DML tùy biến cho view phức tạp.
- Kiểm tra USER_UPDATABLE_COLUMNS và thử DML trong schema sandbox.
- Kiểm tra trigger, foreign key, NOT NULL, CHECK và quyền truy cập.
- Ghi rõ hành vi khi một UPDATE làm hàng rời khỏi view.
- Không dùng view làm cơ chế bảo mật duy nhất nếu user còn quyền trực tiếp trên bảng nền.

### 13.1. View có thể cập nhật không có nghĩa mọi câu DML đều thành công

Một view được đánh dấu updatable vẫn chịu các quy tắc:
- Câu WHERE có thể không tìm thấy hàng.
- UPDATE có thể vi phạm CHECK constraint.
- INSERT có thể thiếu cột NOT NULL.
- FK có thể không tìm thấy hàng cha.
- Trigger bảng nền có thể từ chối thao tác.
- Transaction khác có thể giữ khóa.
- WITH CHECK OPTION có thể từ chối hàng sau thay đổi.

Khả năng cập nhật là thuộc tính cấu trúc của view; thành công của một câu DML cụ thể còn phụ thuộc dữ liệu, constraint, trigger, privilege và concurrency.

## 14. So sánh các cách kiểm soát DML qua view

| Cơ chế | Mục tiêu | Có cho DML qua view? | Phạm vi |
| --- | --- | --- | --- |
| View đơn giản updatable | Ánh xạ DML tới bảng nền | Có, theo cột và cấu trúc hợp lệ | Một bảng nền |
| Key-preserved join view | Cho phép sửa bảng có khóa còn duy nhất trong join | Có giới hạn | Bảng key-preserved |
| WITH CHECK OPTION | Giữ hàng trong predicate của view | Có, nếu view updatable và hàng thỏa điều kiện | DML qua view |
| WITH READ ONLY | Chặn mọi DML qua view | Không | DML qua view đó |
| INSTEAD OF trigger | Tự định nghĩa ánh xạ DML trên view | Có, theo logic trigger | Các bảng do trigger xử lý |
| Table constraints | Bảo vệ tính hợp lệ của dữ liệu | Có thể chặn DML | Bảng nền |
| GRANT/REVOKE | Kiểm soát ai được truy cập/thay đổi | Theo privilege được cấp | User/role và object |

Không có cơ chế nào thay thế hoàn toàn các cơ chế còn lại. Một thiết kế tốt có thể kết hợp view, constraint, privilege và trigger theo mục tiêu cụ thể.

## 15. Quy trình xác định view có thể cập nhật

Khi gặp một view cần DML, hãy kiểm tra theo thứ tự:

1. Đọc định nghĩa view trong USER_VIEWS/ALL_VIEWS.
2. Xác định view dựa trên một bảng hay nhiều bảng.
3. Kiểm tra có DISTINCT, GROUP BY, HAVING, aggregate hoặc set operator không.
4. Xác định cột nào ánh xạ trực tiếp tới cột bảng nền, cột nào là expression.
5. Nếu là join view, liệt kê PK/UNIQUE của từng bảng.
6. Kiểm tra bảng nào là key-preserved trong kết quả JOIN.
7. Xác định câu DML đang muốn sửa đúng một bảng nền hay nhiều bảng.
8. Kiểm tra INSERT có đủ cột NOT NULL và giá trị FK hợp lệ không.
9. Nếu có predicate WHERE, quyết định có cần WITH CHECK OPTION không.
10. Nếu chỉ đọc, cân nhắc WITH READ ONLY và quyền bảng nền.
11. Nếu view không tự updatable nhưng cần DML, thiết kế INSTEAD OF trigger.
12. Xem USER_UPDATABLE_COLUMNS.
13. Thử INSERT/UPDATE/DELETE trên dữ liệu sandbox.
14. Kiểm tra lỗi, constraint, trigger, quyền và transaction boundary.
15. Xác nhận ứng dụng không có quyền trực tiếp vượt qua chính sách view nếu view được dùng cho bảo mật.

## 16. Những nhầm lẫn thường gặp

**Mọi view đều chỉ đọc.** Không đúng. View đơn giản có thể cho phép DML nếu cấu trúc và cột đáp ứng quy tắc Oracle.

**Mọi view JOIN đều không cập nhật được.** Không đúng. Join view có thể cho phép sửa cột của bảng key-preserved.

**Một bảng có primary key thì luôn key-preserved trong mọi join view.** Không đúng. Key preservation phụ thuộc khóa có còn duy nhất trong kết quả JOIN hay không.

**Dữ liệu hiện tại không có duplicate là đủ để Oracle xem bảng key-preserved.** Không đúng. Oracle dựa vào metadata constraint/unique phù hợp, không chỉ kiểm tra dữ liệu tình cờ.

**Có thể UPDATE cột của bất kỳ bảng nào trong join view.** Không đúng. Cột phải ánh xạ tới bảng key-preserved và tuân theo giới hạn một bảng nền mỗi câu DML.

**Một UPDATE qua join view có thể sửa hai bảng nền cùng lúc.** Không đúng. Tách thành nhiều câu DML trong cùng transaction hoặc dùng trigger được thiết kế rõ.

**DELETE qua join view xóa tất cả bảng tham gia JOIN.** Không đúng. Oracle xác định một key-preserved table làm mục tiêu xóa theo quy tắc join view.

**WITH CHECK OPTION ngăn mọi UPDATE làm dữ liệu thay đổi.** Không đúng. Nó chỉ ngăn hàng sau INSERT/UPDATE qua view vi phạm điều kiện view; thay đổi các cột khác vẫn có thể được phép.

**WITH CHECK OPTION là constraint toàn bảng.** Không đúng. DML trực tiếp trên bảng nền không bị predicate view kiểm tra bởi check option đó.

**WITH READ ONLY khóa bảng nền.** Không đúng. Nó chặn DML qua view, không tự chặn DML trực tiếp trên bảng nền.

**View có WHERE tự động không updatable.** Không đúng. WHERE vẫn có thể xuất hiện trong view updatable; check option quyết định việc hàng có được phép rời khỏi phạm vi view hay không.

**Cột tính toán có thể UPDATE ngược về cột nguồn.** Không đúng. Oracle không tự suy ra phép biến đổi ngược cho expression column.

**INSTEAD OF trigger làm mọi DML tự động an toàn.** Không đúng. Trigger phải tự định nghĩa mapping, khóa, constraint và transaction behavior.

**USER_UPDATABLE_COLUMNS='YES' bảo đảm câu UPDATE luôn thành công.** Không đúng. Constraint, trigger, quyền, dữ liệu và khóa vẫn có thể làm DML thất bại.

## 17. Bài tập tự luyện

1. Tạo view chọn EMPLOYEE_ID, FULL_NAME, SALARY từ EMPLOYEES. Thử UPDATE qua view và kiểm tra bảng nền.
2. Tạo view có WHERE STATUS='ACTIVE'. Nếu UPDATE STATUS thành INACTIVE mà không có CHECK OPTION, hàng sẽ xuất hiện thế nào trong view?
3. Tạo lại view với WITH CHECK OPTION và thử cùng UPDATE. Giải thích lỗi.
4. INSERT một hàng ACTIVE qua view có CHECK OPTION. Sau đó thử INSERT INACTIVE.
5. Giải thích vì sao WITH CHECK OPTION không ngăn UPDATE trực tiếp bảng nền.
6. Tạo view có WITH READ ONLY. Thử SELECT, INSERT, UPDATE và DELETE.
7. Nếu view READ ONLY nhưng user có quyền UPDATE bảng nền, thao tác trực tiếp trên bảng nền có bị chặn không?
8. Tạo view EMPLOYEES JOIN DEPARTMENTS. Xác định bảng nào key-preserved trong quan hệ một phòng ban - nhiều nhân viên.
9. Vì sao DEPARTMENTS không key-preserved trong join view nếu mỗi phòng có nhiều nhân viên?
10. Thử UPDATE FULL_NAME qua join view. Giải thích vì sao có thể thành công.
11. Thử UPDATE DEPARTMENT_NAME qua join view. Giải thích ORA-01779.
12. Vì sao không thể sửa FULL_NAME và DEPARTMENT_NAME trong cùng một UPDATE qua join view?
13. Viết hai câu UPDATE trực tiếp trên hai bảng trong cùng transaction rồi COMMIT.
14. Thử INSERT nhân viên qua join view bằng các cột thuộc EMPLOYEES. Điều kiện FK nào phải thỏa?
15. Vì sao INSERT một hàng vừa vào EMPLOYEES vừa vào DEPARTMENTS không thể được thực hiện bằng một INSERT qua join view thông thường?
16. Giải thích ORA-01752 khi DELETE từ join view có nhiều bảng key-preserved hoặc không có đúng một bảng phù hợp.
17. Tạo view tổng hợp COUNT(*) theo DEPARTMENT_ID. Vì sao view không tự xác định được hàng nhân viên cần UPDATE?
18. Xem USER_UPDATABLE_COLUMNS và giải thích UPDATABLE, INSERTABLE, DELETABLE.
19. Tạo INSTEAD OF trigger cho một view join để INSERT vào bảng EMPLOYEES. Cột DEPARTMENT_NAME có được dùng không?
20. Nếu INSTEAD OF trigger phát sinh lỗi, thay đổi của câu DML view có thể được rollback theo phạm vi nào?
21. Vì sao không nên COMMIT bên trong trigger thông thường?
22. So sánh WITH CHECK OPTION và WITH READ ONLY.
23. Một view lọc STATUS='ACTIVE' được dùng làm giao diện bảo mật. Vì sao cần kiểm tra privilege trực tiếp trên bảng nền?
24. Khi nào nên dùng VPD thay vì chỉ dựa vào WHERE trong view?
25. Một view có cột SALARY*12 AS ANNUAL_SALARY. Cột nào có thể được cập nhật và vì sao?
26. Tạo view lồng nhau với hai điều kiện WHERE và CHECK OPTION. Xác định các predicate cần được giữ.
27. Giải thích vì sao constraint UNIQUE/PRIMARY KEY quan trọng để Oracle xác định key preservation.
28. Một view có WHERE nhưng không có CHECK OPTION. INSERT qua view với giá trị không thỏa WHERE có thể gây ra kết quả gì?
29. Khi DML qua view thất bại với ORA-01732, cần kiểm tra những thành phần nào trong định nghĩa view?
30. Thiết kế một view updatable cho ứng dụng chỉ được sửa nhân viên ACTIVE thuộc phòng 10, đồng thời bảo đảm UPDATE không thể chuyển hàng sang phòng khác hoặc trạng thái INACTIVE.

**View updatable cho phép DML khi Oracle xác định được hàng bảng nền cần thay đổi. Với join view, key-preserved table là yếu tố quyết định bảng nào có thể được sửa an toàn; WITH CHECK OPTION giữ hàng trong điều kiện của view, còn WITH READ ONLY chặn DML qua view.** Khi view phức tạp cần một quy tắc ghi tùy biến, INSTEAD OF trigger có thể ánh xạ thao tác tới các bảng nền. Kết hợp đúng view, constraint và privilege giúp giao diện dữ liệu rõ ràng mà vẫn bảo vệ được tính hợp lệ của dữ liệu.
