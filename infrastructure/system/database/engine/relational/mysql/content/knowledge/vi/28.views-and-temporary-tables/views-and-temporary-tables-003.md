# View có thể cập nhật và WITH CHECK OPTION

View thường được dùng như một bảng logic để đơn giản hóa truy vấn, giới hạn các cột được công bố hoặc tạo một góc nhìn nghiệp vụ trên bảng gốc. Trong MySQL, một số view còn cho phép INSERT, UPDATE và DELETE trực tiếp. Khi view có điều kiện lọc, việc thay đổi dữ liệu qua view có thể khiến hàng vừa ghi không còn xuất hiện trong chính view đó. WITH CHECK OPTION giúp ngăn tình huống này bằng cách yêu cầu hàng được chèn hoặc cập nhật phải tiếp tục thỏa điều kiện của view.

Trong module DATABASE_MYSQL, cần hiểu hai câu hỏi riêng: view có updatable hay không, và nếu updatable thì điều kiện nào phải được giữ sau khi ghi. Bài này giải thích tiêu chí updatable view, cách dùng LOCAL/CASCADED CHECK OPTION, hành vi khi ghi qua view lồng nhau và cách kiểm tra metadata cũng như quyền truy cập.

## 1. View là gì và khi nào có thể cập nhật?

View là một đối tượng database lưu định nghĩa SELECT. Khi truy vấn view, MySQL thực thi định nghĩa đó để lấy dữ liệu từ các bảng hoặc view bên dưới. View thông thường không lưu một bản sao dữ liệu riêng như materialized view; dữ liệu được đọc từ các đối tượng nguồn.

Ví dụ:

~~~sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(120) NOT NULL,
    department_id INT NOT NULL,
    employment_status VARCHAR(20) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employees_department (department_id)
) ENGINE=InnoDB;

INSERT INTO employees
    (employee_id, employee_name, department_id, employment_status, salary)
VALUES
    (101, 'An', 10, 'ACTIVE', 1200.00),
    (102, 'Binh', 10, 'ACTIVE', 1500.00),
    (103, 'Chi', 20, 'INACTIVE', 1300.00);
~~~

Tạo view chỉ hiển thị nhân viên đang làm việc:

~~~sql
CREATE VIEW v_active_employees AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
FROM employees
WHERE employment_status = 'ACTIVE';
~~~

Truy vấn view:

~~~sql
SELECT *
FROM v_active_employees;
~~~

Với view đơn giản này, mỗi hàng của view tương ứng trực tiếp với một hàng trong employees. MySQL có thể xác định hàng gốc cần thay đổi khi nhận UPDATE hoặc DELETE qua view. Đây là đặc điểm cốt lõi của updatable view: phải có ánh xạ đủ rõ giữa hàng trong view và hàng ở bảng nguồn.

Thử cập nhật:

~~~sql
UPDATE v_active_employees
SET salary = 1600.00
WHERE employee_id = 101;
~~~

Nếu view đủ điều kiện cập nhật và người dùng có quyền cần thiết, câu lệnh thay đổi hàng tương ứng trong bảng employees.

## 2. Những đặc điểm thường làm view không thể cập nhật

MySQL không thể cập nhật qua view khi không thể ánh xạ một hàng kết quả về một hàng nguồn duy nhất hoặc khi kết quả là dữ liệu tổng hợp. Các cấu trúc thường làm view không updatable gồm:

- Aggregate function như SUM, COUNT, AVG, MIN hoặc MAX.
- DISTINCT.
- GROUP BY hoặc HAVING.
- UNION hoặc UNION ALL.
- Một số cấu trúc JOIN không duy trì được ánh xạ hàng rõ ràng.
- Subquery trong select list.
- View bên dưới vốn không updatable.
- ALGORITHM=TEMPTABLE.

Ví dụ view tổng hợp:

~~~sql
CREATE VIEW v_department_salary AS
SELECT
    department_id,
    AVG(salary) AS average_salary,
    COUNT(*) AS employee_count
FROM employees
GROUP BY department_id;
~~~

Không thể cập nhật average_salary để MySQL tự suy ra phải thay đổi salary của nhân viên nào. Giá trị này được tính từ nhiều hàng nguồn nên không có ánh xạ một-một để thực hiện DML.

View có JOIN cần được đánh giá theo từng định nghĩa. Một số join view vẫn updatable nếu MySQL xác định được bảng đích và quan hệ hàng phù hợp; tuy nhiên, các thao tác có giới hạn. Với view nhiều bảng, một UPDATE chỉ có thể cập nhật các cột thuộc một bảng nguồn trong một câu lệnh. INSERT qua join view bị giới hạn hơn và thường không phù hợp khi cần tạo hàng đồng thời ở nhiều bảng. Khi cần DML ổn định, view đơn bảng thường dễ hiểu và dễ kiểm soát nhất.

Ngay cả khi toàn bộ view được đánh giá là updatable, một cột được tính bằng biểu thức như salary * 1.1 AS salary_with_bonus không phải cột nguồn trực tiếp để gán giá trị. Hãy cập nhật cột gốc trong bảng nguồn hoặc qua cột trực tiếp được view công bố.

## 3. ALGORITHM ảnh hưởng đến khả năng cập nhật

MySQL hỗ trợ các thuật toán xử lý view:

| ALGORITHM | Cách xử lý | Khả năng cập nhật |
|---|---|---|
| MERGE | Gộp định nghĩa view vào câu truy vấn tham chiếu view | Có thể updatable nếu định nghĩa view đáp ứng các điều kiện |
| TEMPTABLE | Tạo bảng tạm nội bộ để chứa kết quả view | Không updatable |
| UNDEFINED | Để MySQL chọn thuật toán phù hợp | Phụ thuộc thuật toán được chọn và định nghĩa view |

Có thể khai báo rõ MERGE:

~~~sql
CREATE OR REPLACE ALGORITHM = MERGE VIEW v_active_employees AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
FROM employees
WHERE employment_status = 'ACTIVE';
~~~

MERGE không làm một view vốn không updatable trở thành updatable. Nó chỉ cho phép MySQL xử lý view theo cách gộp định nghĩa; các điều kiện về ánh xạ hàng và cấu trúc SELECT vẫn phải được đáp ứng.

Nếu khai báo TEMPTABLE, view không thể được dùng làm đích INSERT, UPDATE hoặc DELETE. Khi cần DML qua view, không chọn TEMPTABLE. Với view thông thường, có thể để MySQL quyết định bằng UNDEFINED và kiểm tra metadata.

## 4. Vấn đề khi cập nhật qua view có WHERE

View v_active_employees chỉ hiển thị hàng có employment_status = 'ACTIVE'. Nếu không dùng CHECK OPTION, người dùng có thể thay đổi một hàng sao cho nó không còn thỏa WHERE của view:

~~~sql
UPDATE v_active_employees
SET employment_status = 'INACTIVE'
WHERE employee_id = 102;
~~~

Nếu view không có CHECK OPTION, câu lệnh có thể thành công vì hàng nguồn vẫn tồn tại và có thể cập nhật. Sau UPDATE, hàng đó không còn thỏa điều kiện employment_status = 'ACTIVE', nên nó biến mất khỏi kết quả của v_active_employees.

Tương tự, INSERT qua view có thể tạo hàng không thỏa điều kiện lọc nếu các cột cần thiết được cung cấp và các constraint của bảng nguồn cho phép:

~~~sql
INSERT INTO v_active_employees (
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
)
VALUES (104, 'Dung', 10, 'INACTIVE', 1400.00);
~~~

Sau khi insert, hàng có thể không xuất hiện trong view. Điều này thường gây bất ngờ cho ứng dụng vì lệnh ghi thành công nhưng SELECT lại từ view không thấy dữ liệu vừa ghi.

## 5. WITH CHECK OPTION giải quyết vấn đề gì?

WITH CHECK OPTION yêu cầu mỗi hàng được INSERT hoặc UPDATE thông qua view phải thỏa điều kiện của view sau thao tác. Nếu hàng không thỏa điều kiện, MySQL từ chối thay đổi.

CHECK OPTION chỉ áp dụng cho view có thể cập nhật; nó không biến view chứa GROUP BY, DISTINCT hoặc cấu trúc không updatable khác thành view có thể ghi.

Tạo lại view với CHECK OPTION:

~~~sql
CREATE OR REPLACE ALGORITHM = MERGE VIEW v_active_employees AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
FROM employees
WHERE employment_status = 'ACTIVE'
WITH CASCADED CHECK OPTION;
~~~

Giờ thử cập nhật hàng đang ACTIVE thành INACTIVE:

~~~sql
UPDATE v_active_employees
SET employment_status = 'INACTIVE'
WHERE employee_id = 101;
~~~

MySQL từ chối vì hàng sau cập nhật không còn thỏa điều kiện của view. Lỗi thường gặp là 1369 (CHECK OPTION failed).

Thử INSERT hàng INACTIVE qua view cũng bị từ chối:

~~~sql
INSERT INTO v_active_employees (
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
)
VALUES (105, 'Ha', 10, 'INACTIVE', 1450.00);
~~~

Trong khi đó, INSERT hàng ACTIVE thỏa điều kiện có thể thành công:

~~~sql
INSERT INTO v_active_employees (
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
)
VALUES (106, 'Khanh', 10, 'ACTIVE', 1550.00);
~~~

CHECK OPTION không thay thế PRIMARY KEY, UNIQUE, NOT NULL, CHECK constraint hay quyền truy cập. Nó chỉ kiểm tra điều kiện lọc của view trong phạm vi được chỉ định.

## 6. CHECK OPTION kiểm tra INSERT và UPDATE, không phải DELETE

CHECK OPTION bảo đảm hàng được tạo hoặc thay đổi qua view vẫn thỏa điều kiện view. DELETE không tạo ra một hàng mới hoặc làm thay đổi giá trị để hàng rời khỏi điều kiện lọc, nên CHECK OPTION không ngăn DELETE.

Ví dụ:

~~~sql
DELETE FROM v_active_employees
WHERE employee_id = 106;
~~~

Nếu view updatable và người dùng có quyền DELETE, câu lệnh xóa hàng nguồn tương ứng. CHECK OPTION không biến view thành một vùng dữ liệu chỉ đọc và cũng không giới hạn quyền xóa.

Nếu người dùng chỉ được phép xem hoặc sửa một phần dữ liệu, cần kết hợp quyền GRANT phù hợp, view được thiết kế đúng và quy tắc nghiệp vụ ở tầng ứng dụng/database. Không coi CHECK OPTION là cơ chế phân quyền hoàn chỉnh.

## 7. LOCAL và CASCADED CHECK OPTION

Sự khác biệt giữa LOCAL và CASCADED chỉ rõ khi một view được định nghĩa dựa trên một view khác.

- LOCAL chỉ kiểm tra điều kiện của view đang được định nghĩa.
- CASCADED kiểm tra điều kiện của view hiện tại và các view bên dưới trong chuỗi định nghĩa.
- Nếu không ghi LOCAL hoặc CASCADED, MySQL mặc định dùng CASCADED.

### Tạo view nền không có CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_staff_active AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status
FROM employees
WHERE employment_status = 'ACTIVE';
~~~

View nền chỉ hiển thị nhân viên ACTIVE nhưng chưa yêu cầu hàng ghi qua nó phải giữ điều kiện này.

### View lồng với LOCAL CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_department_10_local AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status
FROM v_staff_active
WHERE department_id = 10
WITH LOCAL CHECK OPTION;
~~~

LOCAL chỉ kiểm tra điều kiện department_id = 10 của view hiện tại. Vì view nền v_staff_active không có CHECK OPTION và LOCAL không kiểm tra điều kiện của view nền, một hàng có department_id = 10 nhưng employment_status = 'INACTIVE' có thể được ghi qua view lồng nếu các điều kiện cập nhật khác cho phép. Sau khi ghi, hàng đó không còn xuất hiện trong v_staff_active.

Thử trong môi trường kiểm thử:

~~~sql
INSERT INTO v_department_10_local (
    employee_id,
    employee_name,
    department_id,
    employment_status
)
VALUES (107, 'Lan', 10, 'INACTIVE');
~~~

### View lồng với CASCADED CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_department_10_cascaded AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status
FROM v_staff_active
WHERE department_id = 10
WITH CASCADED CHECK OPTION;
~~~

CASCADED kiểm tra cả điều kiện department_id = 10 của view hiện tại và employment_status = 'ACTIVE' của view nền. Vì vậy, INSERT hoặc UPDATE tạo ra hàng INACTIVE bị từ chối.

~~~sql
INSERT INTO v_department_10_cascaded (
    employee_id,
    employee_name,
    department_id,
    employment_status
)
VALUES (108, 'Minh', 10, 'INACTIVE');
~~~

Câu lệnh này bị từ chối bởi CHECK OPTION của view lồng.

| Hành động qua view lồng | LOCAL | CASCADED |
|---|---|---|
| Ghi department_id khác 10 | Bị từ chối | Bị từ chối |
| Ghi department_id = 10, status = INACTIVE | Có thể được chấp nhận nếu view nền không có CHECK OPTION | Bị từ chối |
| Ghi department_id = 10, status = ACTIVE | Được chấp nhận nếu các constraint khác thỏa | Được chấp nhận nếu các constraint khác thỏa |

Nếu cần bảo đảm mọi điều kiện lọc trong chuỗi view đều được kiểm tra khi ghi, hãy dùng CASCADED. Không dựa vào LOCAL để bảo vệ điều kiện WHERE của view nền; LOCAL chỉ yêu cầu kiểm tra điều kiện của view hiện tại.

## 8. Giá trị NULL và CHECK OPTION

Điều kiện WHERE trong SQL chỉ chọn hàng khi biểu thức là TRUE. FALSE và UNKNOWN đều không được chọn. UNKNOWN thường xuất hiện khi một phép so sánh liên quan đến NULL.

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW v_high_salary AS
SELECT employee_id, employee_name, salary
FROM employees
WHERE salary >= 1000
WITH CHECK OPTION;
~~~

Nếu salary là NULL, biểu thức salary >= 1000 có giá trị UNKNOWN. Một hàng có salary NULL không thỏa điều kiện của view và không thể được INSERT/UPDATE qua view với CHECK OPTION. Trong schema ví dụ, salary là NOT NULL nên tình huống này không xảy ra; nếu cột cho phép NULL, cần chủ động xác định quy tắc nghiệp vụ.

Đừng dùng COALESCE hoặc giá trị mặc định trong view chỉ để làm CHECK OPTION dễ vượt qua. Hãy quyết định rõ NULL có được phép hay không và điều kiện lọc phải phản ánh quy tắc dữ liệu nào.

## 9. Cột bị ẩn khỏi view và yêu cầu khi INSERT

CHECK OPTION không tự điền các cột bắt buộc của bảng nguồn. Nếu view không công bố một cột NOT NULL không có DEFAULT, INSERT qua view có thể thất bại vì bảng gốc không nhận được giá trị cho cột đó.

Ví dụ, nếu employees có thêm:

~~~sql
hire_date DATE NOT NULL
~~~

nhưng view không chọn hire_date, INSERT qua view có thể không cung cấp được giá trị bắt buộc. Cần:

- Đưa cột vào view nếu người dùng được phép cung cấp giá trị.
- Khai báo DEFAULT hợp lệ ở bảng nguồn nếu nghiệp vụ cho phép.
- Dùng stored procedure hoặc API ghi dữ liệu nếu cần áp dụng logic tạo giá trị.

Đừng nhầm lỗi thiếu cột bắt buộc với lỗi CHECK OPTION. Một lỗi đến từ constraint của bảng nguồn; lỗi còn lại đến từ điều kiện view.

## 10. Kiểm tra view có updatable hay không

MySQL cung cấp metadata trong INFORMATION_SCHEMA.VIEWS:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    IS_UPDATABLE,
    CHECK_OPTION,
    SECURITY_TYPE,
    DEFINER
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
      'v_active_employees',
      'v_active_employees_secure',
      'v_staff_active',
      'v_department_10_local',
      'v_department_10_cascaded'
  );
~~~

Các cột hữu ích:

- IS_UPDATABLE cho biết MySQL đánh giá view có thể cập nhật hay không.
- CHECK_OPTION cho biết NONE, LOCAL hoặc CASCADED.
- SECURITY_TYPE cho biết view chạy theo quyền DEFINER hay INVOKER.
- DEFINER cho biết tài khoản định nghĩa view.

Metadata giúp xác nhận trạng thái mà MySQL nhận diện, nhưng vẫn nên thử DML trên dữ liệu kiểm thử để hiểu hành vi cụ thể của định nghĩa view.

Có thể xem định nghĩa view:

~~~sql
SHOW CREATE VIEW v_active_employees;
~~~

Lệnh này giúp kiểm tra SELECT, ALGORITHM, DEFINER, SQL SECURITY và CHECK OPTION đã được lưu như mong đợi chưa.

## 11. Quyền truy cập khi ghi qua view

View có thể dùng SQL SECURITY DEFINER hoặc SQL SECURITY INVOKER:

- DEFINER: câu lệnh truy cập các đối tượng bên dưới theo quyền của tài khoản định nghĩa view.
- INVOKER: câu lệnh truy cập các đối tượng bên dưới theo quyền của người gọi.

Ví dụ:

~~~sql
CREATE OR REPLACE ALGORITHM = MERGE
SQL SECURITY DEFINER
VIEW v_active_employees_secure AS
SELECT employee_id, employee_name, department_id, employment_status, salary
FROM employees
WHERE employment_status = 'ACTIVE'
WITH CASCADED CHECK OPTION;
~~~

Người dùng vẫn cần quyền thích hợp trên view cho thao tác SELECT, INSERT, UPDATE hoặc DELETE. Với DEFINER, quyền trên bảng nguồn được kiểm tra theo cơ chế bảo mật của view; với INVOKER, người gọi phải có quyền cần thiết trên các đối tượng được truy cập.

CHECK OPTION không cấp quyền và cũng không giới hạn một người dùng chỉ được sửa một số cột. Nếu cần giới hạn cột, hãy chỉ công bố các cột phù hợp trong view và cấp quyền theo cột/view đúng cách; kiểm tra thêm quyền trên bảng nguồn và các routine liên quan.

## 12. Khi nào nên dùng updatable view?

Updatable view phù hợp khi:

- Ứng dụng cần một giao diện ghi đơn giản trên một bảng nguồn.
- Muốn chỉ công bố một tập cột cho một nhóm người dùng.
- Muốn giới hạn các hàng được phép ghi bằng điều kiện cố định.
- Muốn gom điều kiện lọc lặp lại thành một đối tượng database có tên rõ nghĩa.

Ví dụ, view active employees giúp ứng dụng chỉ thao tác trên nhân viên đang làm việc. CHECK OPTION bảo đảm cập nhật qua view không vô tình chuyển hàng ra khỏi tập dữ liệu được phép.

Không nên dùng view như ranh giới bảo mật duy nhất nếu có nhiều quy tắc phức tạp. Các constraint của bảng, quyền GRANT, stored procedure và kiểm tra ở tầng ứng dụng có thể cần phối hợp để bảo đảm tính toàn vẹn.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ mọi view đều cập nhật được | DML thất bại với view tổng hợp hoặc không có ánh xạ hàng | Kiểm tra IS_UPDATABLE và định nghĩa SELECT |
| Dùng GROUP BY/DISTINCT rồi cố UPDATE | Không xác định được hàng nguồn cần sửa | Cập nhật bảng nguồn theo khóa cụ thể hoặc dùng routine |
| Quên CHECK OPTION | UPDATE có thể làm hàng biến mất khỏi view | Thêm LOCAL/CASCADED theo phạm vi cần bảo vệ |
| Dùng LOCAL khi cần bảo vệ điều kiện view nền | Hàng có thể vi phạm điều kiện của view bên dưới nếu view nền không có CHECK OPTION | Dùng CASCADED |
| Nghĩ CHECK OPTION chặn DELETE | DELETE vẫn có thể xóa hàng nếu có quyền | Cấp quyền DELETE đúng mức |
| Nghĩ CHECK OPTION thay thế constraint | Vẫn có thể gặp duplicate key, NULL hoặc lỗi FK/NOT NULL | Giữ constraint ở bảng nguồn |
| Dùng ALGORITHM=TEMPTABLE cho view cần DML | View không updatable | Dùng MERGE hoặc UNDEFINED phù hợp |
| Không kiểm tra cột bắt buộc bị ẩn | INSERT qua view thất bại | Công bố cột, dùng DEFAULT hoặc routine |

## 14. Quy trình thiết kế view có thể cập nhật

1. Xác định bảng nguồn và hàng nghiệp vụ mà view đại diện.
2. Chọn các cột cần công bố; giữ khóa định danh để MySQL ánh xạ hàng.
3. Viết SELECT đơn giản, tránh aggregate, DISTINCT, GROUP BY, HAVING và UNION nếu cần DML.
4. Kiểm tra các cột bắt buộc của bảng nguồn và giá trị DEFAULT.
5. Chọn ALGORITHM phù hợp; không dùng TEMPTABLE nếu cần cập nhật.
6. Xác định điều kiện WHERE mà mọi hàng ghi qua view phải thỏa.
7. Chọn WITH LOCAL CHECK OPTION hoặc WITH CASCADED CHECK OPTION theo chuỗi view.
8. Kiểm tra IS_UPDATABLE và CHECK_OPTION trong INFORMATION_SCHEMA.VIEWS.
9. Thử INSERT/UPDATE làm hàng vẫn thỏa điều kiện và thử thao tác vi phạm để xác nhận bị từ chối.
10. Thử trường hợp NULL, duplicate key và cột nguồn không xuất hiện trong view.
11. Kiểm tra quyền SELECT/INSERT/UPDATE/DELETE và SQL SECURITY.
12. Ghi lại quy tắc ghi qua view để ứng dụng không giả định sai về các hàng vừa cập nhật.

## 15. Bài tập thực hành

1. Tạo bảng employees theo ví dụ và tạo view chỉ hiển thị nhân viên ACTIVE.
2. UPDATE status của một nhân viên thành INACTIVE qua view không có CHECK OPTION; xác nhận hàng biến mất khỏi view nhưng vẫn còn ở bảng nguồn.
3. Tạo lại view với WITH CASCADED CHECK OPTION; thử UPDATE cùng thao tác và đọc lỗi.
4. INSERT một nhân viên ACTIVE và một nhân viên INACTIVE qua view; so sánh kết quả.
5. Tạo view v_staff_active không có CHECK OPTION và view lồng theo department_id = 10 với LOCAL CHECK OPTION; thử ghi hàng INACTIVE thuộc department 10.
6. Tạo lại view lồng với CASCADED CHECK OPTION; xác nhận điều kiện employment_status của view nền cũng được kiểm tra.
7. Thử tạo view tổng hợp theo department_id và kiểm tra IS_UPDATABLE.
8. So sánh SHOW CREATE VIEW và INFORMATION_SCHEMA.VIEWS cho các view đã tạo.
9. Thử một cột nguồn NOT NULL không có DEFAULT nhưng không được công bố trong view; phân biệt lỗi constraint với lỗi CHECK OPTION.
10. Tạo hai view với SQL SECURITY DEFINER và INVOKER trong môi trường thử nghiệm; cấp quyền tối thiểu và quan sát thao tác DML.

Bạn hoàn thành bài khi xác định được view nào updatable, giải thích được vì sao một số cấu trúc SELECT không thể cập nhật, chọn đúng LOCAL hoặc CASCADED CHECK OPTION và chứng minh được các hàng vi phạm điều kiện bị từ chối. Hãy xem view là một giao diện dữ liệu có quy tắc rõ ràng; constraint và quyền trên bảng nguồn vẫn là lớp bảo vệ cần thiết.
