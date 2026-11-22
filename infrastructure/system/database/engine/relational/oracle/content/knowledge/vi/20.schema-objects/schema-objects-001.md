# Tạo view và sử dụng view làm ranh giới truy cập dữ liệu trong Oracle

Một ứng dụng thường không cần biết toàn bộ cấu trúc bảng bên trong database. Màn hình danh bạ nhân viên chỉ cần mã, tên, phòng ban và email công việc; nó không cần lương, thông tin ngân hàng hay trạng thái xử lý nội bộ. Nếu ứng dụng được cấp quyền SELECT trực tiếp trên bảng nhân viên, mọi câu truy vấn của ứng dụng đều có thể đọc các cột mà nó không cần. Khi tạo một **view** chỉ công bố những cột và hàng được phép dùng, rồi cấp quyền trên view thay vì bảng gốc, database có thể cung cấp một hợp đồng truy cập rõ ràng hơn.

Trong Oracle, view thông thường là một đối tượng schema lưu định nghĩa truy vấn. Khi người dùng truy vấn view, Oracle thực thi truy vấn định nghĩa view cùng với điều kiện của câu truy vấn bên ngoài. View không lưu bản sao kết quả như một bảng vật lý hay materialized view. Vì vậy, view vừa là lớp trừu tượng hóa cấu trúc dữ liệu, vừa có thể là một ranh giới cấp quyền nếu quyền trên bảng nền được quản lý đúng.

Bài học thuộc nhóm **Đối tượng schema** của Database Engine Relational Oracle. Nội dung trình bày cách tạo và thay đổi view, công bố hợp đồng cột/hàng, cấp quyền tối thiểu, giới hạn DML bằng WITH CHECK OPTION hoặc WITH READ ONLY, xử lý view phức tạp bằng INSTEAD OF trigger, quản lý dependency và hiểu tác động của view đến optimizer.

Sau bài này, bạn có thể:

- Tạo view bằng CREATE VIEW và thay đổi định nghĩa bằng CREATE OR REPLACE VIEW.
- Thiết kế view với danh sách cột tường minh, tên cột ổn định và predicate nghiệp vụ rõ ràng.
- Dùng view làm lớp truy cập cho ứng dụng mà không cấp quyền trực tiếp trên bảng nền.
- Hiểu quyền cần có của view owner và quyền cần cấp cho người dùng ứng dụng.
- Phân biệt view có thể cập nhật với view chỉ đọc.
- Dùng WITH CHECK OPTION, WITH READ ONLY và INSTEAD OF trigger đúng mục đích.
- Kiểm tra dependency, trạng thái INVALID và lỗi biên dịch view.
- Phân biệt view thường, inline view, CTE, synonym và materialized view.
- Đánh giá view trong execution plan và nhận biết giới hạn bảo mật của view.

> **Phạm vi ví dụ:** Các câu lệnh dùng cú pháp Oracle Database 19c. Bảng thực hành có hậu tố _LAB. Hãy chạy trong schema lab riêng. Quyền CREATE VIEW, quyền truy cập object ở schema khác và quyền cấp cho user/role phụ thuộc cấu hình quản trị database.

## 1. View là gì?

View là một đối tượng schema chứa định nghĩa của một truy vấn. Người dùng truy vấn view như truy vấn một bảng:

~~~sql
SELECT employee_id, full_name, department_id
FROM v_employee_directory
WHERE department_id = 20;
~~~

Định nghĩa view có thể đọc từ một hoặc nhiều bảng, view khác hoặc một số đối tượng dữ liệu được phép. View có thể:

- Chỉ chọn một số cột.
- Chỉ hiển thị những hàng đáp ứng điều kiện.
- Đổi tên cột hoặc biểu thức để tạo giao diện dễ dùng.
- Kết hợp nhiều bảng.
- Tổng hợp dữ liệu bằng GROUP BY.
- Che giấu một phần cấu trúc vật lý và logic truy vấn phía sau.

### 1.1. View thường không lưu kết quả

~~~text
APPLICATION USER
       |
       | SELECT
       v
   VIEW OBJECT
       |
       | stored query definition
       v
  BASE TABLE(S)
       |
       v
  CURRENT COMMITTED DATA
~~~

View thường lưu câu truy vấn trong data dictionary. Khi được truy vấn, Oracle tối ưu và thực thi câu SQL dựa trên view cùng các đối tượng nền. Nếu dữ liệu bảng thay đổi và transaction được commit, lần truy vấn view sau có thể thấy dữ liệu mới theo read consistency.

Điều này có nghĩa view không tự động tăng tốc truy vấn. Nó cũng không phải một snapshot cố định của dữ liệu. Nếu cần lưu kết quả đã tính trước, hãy tìm hiểu materialized view.

### 1.2. Vì sao dùng view?

| Mục tiêu | View giúp gì? |
| --- | --- |
| Đơn giản hóa truy vấn | Đóng gói JOIN, biểu thức hoặc điều kiện lặp lại |
| Ổn định giao diện dữ liệu | Ứng dụng phụ thuộc vào tên/cột của view thay vì cấu trúc bảng nội bộ |
| Giới hạn cột | Chỉ công bố cột cần thiết |
| Giới hạn hàng | Công bố một tập hàng theo predicate |
| Cấp quyền tối thiểu | Cấp SELECT/DML trên view thay vì bảng gốc |
| Báo cáo | Cung cấp một mô hình đọc thống nhất cho nhiều báo cáo |

View là một phần của thiết kế schema. Nó không thay thế primary key, foreign key, check constraint, row-level security hoặc kiểm soát quyền ở các tầng khác.

## 2. Cú pháp CREATE VIEW

Mẫu cơ bản:

~~~sql
CREATE [OR REPLACE] [FORCE | NOFORCE] VIEW view_name
    [(column_alias_1, column_alias_2, ...)]
AS
    subquery
[WITH CHECK OPTION [CONSTRAINT constraint_name]
 | WITH READ ONLY];
~~~

Các thành phần chính:

- CREATE VIEW: tạo view mới.
- OR REPLACE: thay định nghĩa view đã tồn tại.
- FORCE/NOFORCE: điều khiển việc tạo view khi đối tượng nền hoặc quyền chưa sẵn sàng; NOFORCE là mặc định.
- Danh sách alias: đặt tên cột của view, hữu ích với biểu thức hoặc tên cột cần chuẩn hóa.
- AS subquery: truy vấn định nghĩa view.
- WITH CHECK OPTION: kiểm soát DML đi qua view để hàng vẫn đáp ứng điều kiện của view.
- WITH READ ONLY: không cho phép DML thông qua view.

### 2.1. Dùng danh sách cột tường minh

Ví dụ:

~~~sql
CREATE VIEW v_department_employee AS
SELECT
    department_id,
    employee_id,
    full_name,
    work_email
FROM employee_data_lab;
~~~

Nên liệt kê cột cần công bố thay vì SELECT *. Khi bảng nền được thêm cột mới, định nghĩa view đã tạo không tự động trở thành hợp đồng công bố mọi cột mới. Danh sách tường minh cũng giúp người đọc biết view đang cho phép truy cập thông tin nào.

### 2.2. Đặt alias cho biểu thức

~~~sql
CREATE VIEW v_department_payroll (
    department_id,
    employee_count,
    total_salary
) AS
SELECT
    department_id,
    COUNT(*),
    SUM(monthly_salary)
FROM employee_data_lab
GROUP BY department_id;
~~~

Tên cột view là một phần giao diện mà ứng dụng sử dụng. Hãy chọn tên ổn định, có ý nghĩa nghiệp vụ và không phụ thuộc cách đặt tên nội bộ của một bảng cụ thể.

### 2.3. CREATE OR REPLACE VIEW

~~~sql
CREATE OR REPLACE VIEW v_department_employee AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email,
    employment_status
FROM employee_data_lab;
~~~

OR REPLACE cập nhật định nghĩa của view đang tồn tại mà không cần DROP trước. Đây là cách triển khai thay đổi thông thường. Tuy vậy, thay đổi tên cột, datatype, thứ tự hoặc semantics của view có thể làm hỏng ứng dụng và các object phụ thuộc. Trước khi thay đổi hợp đồng, hãy xem các consumer đang dùng view.

### 2.4. FORCE và NOFORCE

NOFORCE là mặc định: Oracle yêu cầu các đối tượng nền và quyền cần thiết phải hợp lệ để tạo view.

FORCE cho phép tạo view ngay cả khi một số đối tượng nền chưa tồn tại hoặc một số điều kiện kiểm tra chưa được đáp ứng; view có thể ở trạng thái INVALID cho đến khi các dependency sẵn sàng và view được biên dịch lại. FORCE hữu ích trong một số kịch bản triển khai theo thứ tự, nhưng không làm cho view hợp lệ về mặt truy vấn và không cấp thêm quyền.

~~~sql
CREATE FORCE VIEW v_future_source AS
SELECT id, description
FROM future_source_table;
~~~

Không dùng FORCE để che lỗi thiếu dependency trong triển khai thông thường. Nếu view không hợp lệ, hãy kiểm tra USER_ERRORS/ALL_ERRORS và sửa nguyên nhân.

## 3. Chuẩn bị schema lab

### 3.1. Tạo bảng nhân viên

~~~sql
CREATE TABLE employee_data_lab (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    work_email VARCHAR2(120 CHAR),
    monthly_salary NUMBER(12,2) NOT NULL,
    employment_status VARCHAR2(12 CHAR) NOT NULL,
    bank_account_ref VARCHAR2(40 CHAR),
    CONSTRAINT ck_employee_salary_lab
        CHECK (monthly_salary >= 0),
    CONSTRAINT ck_employee_status_lab
        CHECK (employment_status IN ('ACTIVE', 'INACTIVE', 'LEAVE'))
);
~~~

Bảng có các cột công khai cho danh bạ, cột lương dùng cho báo cáo nhân sự được cấp quyền riêng và mã tài khoản ngân hàng không nên xuất hiện trong view danh bạ thông thường.

### 3.2. Nạp dữ liệu minh họa

~~~sql
INSERT INTO employee_data_lab VALUES
    (101, 'Nguyen An', 10, 'an@example.test', 2500, 'ACTIVE', 'BANK-REF-A');

INSERT INTO employee_data_lab VALUES
    (102, 'Tran Binh', 10, 'binh@example.test', 3200, 'ACTIVE', 'BANK-REF-B');

INSERT INTO employee_data_lab VALUES
    (103, 'Le Chi', 20, 'chi@example.test', 2800, 'ACTIVE', 'BANK-REF-C');

INSERT INTO employee_data_lab VALUES
    (104, 'Pham Dung', 20, 'dung@example.test', 3000, 'INACTIVE', 'BANK-REF-D');

COMMIT;
~~~

## 4. Tạo view làm hợp đồng truy cập

### 4.1. View danh bạ chỉ công bố cột cần thiết

~~~sql
CREATE OR REPLACE VIEW v_employee_directory_lab AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

View này:

- Chỉ công bố employee_id, full_name, department_id và work_email.
- Không công bố monthly_salary hoặc bank_account_ref.
- Chỉ hiển thị nhân viên có employment_status là ACTIVE.
- Không cho DML qua view vì có WITH READ ONLY.

Ứng dụng danh bạ có thể truy vấn:

~~~sql
SELECT employee_id, full_name, work_email
FROM v_employee_directory_lab
WHERE department_id = 10
ORDER BY full_name;
~~~

Ứng dụng không cần biết cột bank_account_ref tồn tại. Khi schema nội bộ thay đổi, view có thể giữ nguyên hợp đồng cho consumer nếu định nghĩa view được điều chỉnh tương ứng.

### 4.2. View tổng hợp cho báo cáo

~~~sql
CREATE OR REPLACE VIEW v_department_payroll_lab AS
SELECT
    department_id,
    COUNT(*) AS employee_count,
    SUM(monthly_salary) AS total_monthly_salary,
    AVG(monthly_salary) AS average_monthly_salary
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
GROUP BY department_id;
~~~

Báo cáo chỉ cần tổng số nhân viên và tổng lương theo phòng ban có thể đọc view thay vì tự viết lại điều kiện ACTIVE và GROUP BY. Đây là view tổng hợp, thông thường không thể cập nhật trực tiếp các giá trị tổng hợp qua view.

### 4.3. View kết hợp nhiều bảng

Một view có thể đóng gói JOIN:

~~~sql
CREATE TABLE department_data_lab (
    department_id NUMBER PRIMARY KEY,
    department_name VARCHAR2(60 CHAR) NOT NULL
);

INSERT INTO department_data_lab VALUES (10, 'Engineering');
INSERT INTO department_data_lab VALUES (20, 'Finance');
COMMIT;

CREATE OR REPLACE VIEW v_employee_department_lab AS
SELECT
    e.employee_id,
    e.full_name,
    e.work_email,
    d.department_name
FROM employee_data_lab e
JOIN department_data_lab d
  ON d.department_id = e.department_id
WHERE e.employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

Consumer dùng một giao diện duy nhất dù dữ liệu được lưu ở hai bảng. View cũng giúp giữ logic JOIN và predicate ở một nơi thay vì sao chép trong nhiều ứng dụng.

## 5. View làm ranh giới truy cập dữ liệu

Một cách tổ chức phổ biến là tách schema sở hữu dữ liệu, schema sở hữu view và user ứng dụng:

~~~text
DATA_OWNER
  owns EMPLOYEE_DATA
  grants SELECT directly to REPORT_OWNER
           |
           v
REPORT_OWNER
  owns V_EMPLOYEE_DIRECTORY
  grants SELECT on the view to APP_READER_ROLE
           |
           v
APPLICATION USER
  receives APP_READER_ROLE
  queries the view
~~~

Tách schema giúp kiểm soát ai được thay đổi bảng, ai được định nghĩa hợp đồng view và ai chỉ được đọc dữ liệu công bố.

### 5.1. Quyền cần có để tạo view

User tạo view cần system privilege CREATE VIEW trong schema của chính mình. Nếu tạo view trong schema khác, cần quyền CREATE ANY VIEW phù hợp và phải tuân theo chính sách quản trị.

Đối với các bảng/view nền thuộc schema khác, view owner phải có object privileges cần thiết được cấp trực tiếp. Quyền nhận thông qua role không đủ để định nghĩa một stored view. Ví dụ:

~~~sql
-- Chay boi DATA_OWNER:
GRANT SELECT ON employee_data_lab TO report_owner;
~~~

Sau đó REPORT_OWNER có thể tạo view tham chiếu bảng mà nó được cấp quyền trực tiếp:

~~~sql
-- Chay trong schema REPORT_OWNER:
CREATE OR REPLACE VIEW v_employee_directory AS
SELECT employee_id, full_name, department_id, work_email
FROM data_owner.employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

Nếu REPORT_OWNER chỉ có quyền SELECT thông qua một role, việc tạo view có thể thất bại vì stored object cần quyền trực tiếp trên dependency.

### 5.2. Cấp quyền trên view cho ứng dụng

~~~sql
-- Tao role neu chua co:
CREATE ROLE app_employee_reader;

-- View owner cap quyen tren view:
GRANT SELECT ON v_employee_directory TO app_employee_reader;

-- DBA hoac user co quyen grant role cap role cho app user:
GRANT app_employee_reader TO app_reader;
~~~

APP_READER có thể SELECT view nhờ role. User ứng dụng không cần được cấp SELECT trực tiếp trên DATA_OWNER.EMPLOYEE_DATA nếu mục tiêu là chỉ đọc qua view.

### 5.3. Vì sao view có thể hoạt động khi user không có quyền bảng nền?

Khi user truy vấn view, Oracle kiểm tra quyền trên view và quyền của view owner đối với các object nền theo cơ chế view. Vì vậy, user có thể được cấp quyền SELECT trên view mà không được cấp SELECT trực tiếp trên bảng nền.

Đây là nền tảng để dùng view làm access boundary. Hãy xác nhận view owner có quyền trực tiếp và ứng dụng chỉ nhận những object privileges cần thiết.

### 5.4. View không bảo vệ bảng nếu user vẫn có quyền trực tiếp

Nếu APP_READER đồng thời có:

~~~sql
GRANT SELECT ON data_owner.employee_data_lab TO app_reader;
~~~

thì user có thể bỏ qua view và truy vấn bảng gốc. View không thể ngăn một quyền rộng hơn đã được cấp ở nơi khác.

Để view thực sự đóng vai trò ranh giới:

- Không cấp quyền trực tiếp trên bảng nền cho application user/role.
- Không cấp quyền rộng như SELECT ANY TABLE nếu không cần.
- Cấp đúng SELECT hoặc DML trên các view đã được thiết kế.
- Kiểm tra quyền được kế thừa qua role và các grant khác.
- Tách tài khoản owner/schema khỏi tài khoản runtime của ứng dụng.

### 5.5. View giới hạn cột và hàng

View danh bạ ở trên vừa giới hạn cột vừa giới hạn hàng. Đây là cách đơn giản để tách consumer theo mục đích:

| Consumer | View được cấp | Dữ liệu công bố |
| --- | --- | --- |
| Danh bạ nội bộ | V_EMPLOYEE_DIRECTORY | Mã, tên, phòng ban, email |
| Báo cáo lương | V_DEPARTMENT_PAYROLL | Tổng hợp lương theo phòng ban |
| Quản trị nhân sự | View chuyên biệt có quyền rộng hơn | Dữ liệu nhân sự theo nhiệm vụ |

Không nên tạo một view “all purpose” chứa mọi cột rồi cấp cho tất cả ứng dụng. Nhiều view nhỏ theo hợp đồng nghiệp vụ giúp quyền dễ kiểm tra và giảm rủi ro lộ dữ liệu.

### 5.6. View có phải cơ chế bảo mật hoàn chỉnh không?

Không. View là một lớp cấp quyền và trừu tượng hóa hữu ích, nhưng cần được đặt trong mô hình bảo mật tổng thể:

- Nếu user có quyền bảng nền, họ có thể bỏ qua view.
- Nếu user có quyền rộng ở cấp system, view không thu hẹp quyền đó.
- Predicate tĩnh trong view chỉ lọc theo logic được định nghĩa; nó không tự hiểu danh tính tenant/người dùng.
- Nếu cần chính sách hàng động theo user/tenant trên nhiều đường truy cập, hãy đánh giá Oracle Virtual Private Database (VPD/FGAC), application context đáng tin cậy hoặc cơ chế row-level security phù hợp.
- Không để client tự đặt một context có thể giả mạo để vượt qua predicate bảo mật.

Một view lọc tenant theo SYS_CONTEXT chỉ an toàn khi context được thiết lập và bảo vệ bằng cơ chế tin cậy; đừng xem một chuỗi điều kiện WHERE trong view là thay thế đầy đủ cho VPD.

## 6. DML qua view: view nào có thể cập nhật?

Không phải view nào cũng chỉ đọc. Một số view đơn giản cho phép INSERT, UPDATE và DELETE đi qua view xuống bảng nền.

### 6.1. View đơn giản

~~~sql
CREATE OR REPLACE VIEW v_employee_edit_lab AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email,
    employment_status
FROM employee_data_lab;
~~~

Ví dụ cập nhật qua view:

~~~sql
UPDATE v_employee_edit_lab
SET work_email = 'new-address@example.test'
WHERE employee_id = 101;

COMMIT;
~~~

Oracle áp dụng thay đổi lên bảng nền. View là giao diện truy cập, không phải một bản sao dữ liệu độc lập.

### 6.2. Các đặc điểm thường làm view không thể cập nhật trực tiếp

View có thể không updatable khi truy vấn chứa các cấu trúc như:

- Aggregate function hoặc GROUP BY.
- DISTINCT.
- Set operator như UNION/UNION ALL, INTERSECT hoặc MINUS.
- Một số biểu thức tính toán hoặc cột suy ra không ánh xạ trực tiếp đến một cột bảng.
- Join view mà bảng cần sửa không được xác định là key-preserved.
- Các cấu trúc khác bị hạn chế theo quy tắc DML-through-view của Oracle.

Ví dụ view tổng hợp:

~~~sql
CREATE OR REPLACE VIEW v_department_payroll_readonly_lab AS
SELECT
    department_id,
    COUNT(*) AS employee_count,
    SUM(monthly_salary) AS total_salary
FROM employee_data_lab
GROUP BY department_id;
~~~

Không thể cập nhật total_salary như thể đó là một cột vật lý của một nhân viên. Giá trị này được tính từ nhiều hàng.

### 6.3. Key-preserved table trong join view

Với view JOIN nhiều bảng, Oracle cần xác định bảng nào được bảo toàn khóa trong kết quả JOIN. Một bảng là key-preserved khi mỗi hàng của bảng đó xuất hiện tối đa một lần trong kết quả join theo quan hệ khóa được chứng minh.

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW v_employee_dept_edit_lab AS
SELECT
    e.employee_id,
    e.full_name,
    e.department_id,
    d.department_name
FROM employee_data_lab e
JOIN department_data_lab d
  ON d.department_id = e.department_id;
~~~

DEPARTMENT_DATA_LAB có primary key department_id. Mỗi nhân viên ghép với tối đa một phòng ban; vì vậy hàng employee không bị nhân bản bởi join này. Bảng employee có thể là key-preserved và một số thao tác cập nhật cột employee có thể được cho phép, tùy đầy đủ quy tắc updatable join view của Oracle.

Nếu một bảng không key-preserved, Oracle có thể báo ORA-01779 khi cố cập nhật cột của bảng đó qua join view. Không thể kết luận chỉ từ việc JOIN có primary key ở một phía; hãy xem constraint, join condition và quy tắc DML cụ thể.

### 6.4. Cột tính toán không tự động ghi ngược được

~~~sql
CREATE OR REPLACE VIEW v_employee_compensation_lab AS
SELECT
    employee_id,
    monthly_salary,
    monthly_salary * 12 AS annual_salary
FROM employee_data_lab;
~~~

annual_salary là biểu thức tính toán. Nó không tương ứng với một cột độc lập trong bảng nền. UPDATE annual_salary qua view không có phép ánh xạ ngược tự nhiên về monthly_salary nếu không có logic bổ sung.

## 7. WITH CHECK OPTION: giữ hàng nằm trong phạm vi view

### 7.1. Vấn đề nếu không có CHECK OPTION

View:

~~~sql
CREATE OR REPLACE VIEW v_active_employee_edit_lab AS
SELECT employee_id, full_name, employment_status
FROM employee_data_lab
WHERE employment_status = 'ACTIVE';
~~~

Một user có quyền UPDATE trên view có thể cập nhật trạng thái của một hàng đang hiển thị:

~~~sql
UPDATE v_active_employee_edit_lab
SET employment_status = 'INACTIVE'
WHERE employee_id = 101;
~~~

Nếu view không có CHECK OPTION, thao tác có thể thành công; sau update, hàng không còn đáp ứng predicate ACTIVE và biến mất khỏi view.

### 7.2. Thêm WITH CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_active_employee_checked_lab AS
SELECT employee_id, full_name, employment_status
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT ck_active_employee_view_lab;
~~~

Với CHECK OPTION, DML thực hiện qua view phải để hàng tiếp tục đáp ứng điều kiện của view. Câu UPDATE đổi ACTIVE thành INACTIVE qua view sẽ bị từ chối vì hàng sau thay đổi không còn được view chọn.

### 7.3. CHECK OPTION không phải bộ lọc quyền tổng quát

CHECK OPTION điều khiển khả năng DML qua view để giữ predicate của view. Nó không:

- Ngăn user có quyền trực tiếp trên bảng nền cập nhật hàng.
- Thay thế constraint ở bảng.
- Thay thế kiểm soát row-level security cho các truy cập khác.
- Bảo đảm mọi quy tắc nghiệp vụ liên quan nhiều bảng.

Nếu yêu cầu là “ứng dụng chỉ được sửa nhân viên đang hoạt động và không thể chuyển hàng ra ngoài tập view”, CHECK OPTION là một phần phù hợp của thiết kế, cùng với việc không cấp quyền bảng nền.

## 8. WITH READ ONLY: công bố view chỉ đọc

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW v_employee_directory_readonly_lab AS
SELECT employee_id, full_name, department_id, work_email
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

WITH READ ONLY cấm INSERT, UPDATE và DELETE qua view. Đây là cách rõ ràng để công bố một view chỉ dùng cho truy vấn.

Lưu ý:

- READ ONLY chỉ áp dụng cho DML qua view.
- Nó không thu hồi quyền DML trực tiếp trên bảng nền nếu user đã được cấp.
- Một view read-only vẫn có thể phản ánh dữ liệu mới sau khi transaction trên bảng nền commit.
- Nếu cần giới hạn cột/hàng, vẫn phải thiết kế SELECT list và predicate đúng.

Đối với view báo cáo hoặc danh bạ, WITH READ ONLY thường giúp hợp đồng truy cập dễ hiểu hơn.

## 9. INSTEAD OF trigger cho view phức tạp

Một view phức tạp có thể không updatable theo quy tắc mặc định. Nếu nghiệp vụ cần cho phép DML qua view, có thể dùng INSTEAD OF trigger để định nghĩa hành động thực tế trên các bảng nền.

### 9.1. Ví dụ view kết hợp phòng ban và nhân viên

~~~sql
CREATE OR REPLACE VIEW v_employee_department_api_lab AS
SELECT
    e.employee_id,
    e.full_name,
    e.department_id,
    d.department_name
FROM employee_data_lab e
JOIN department_data_lab d
  ON d.department_id = e.department_id;
~~~

Giả sử cần INSERT một nhân viên qua view. Một trigger có thể ghi vào bảng employee:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_dept_insert_lab
INSTEAD OF INSERT ON v_employee_department_api_lab
FOR EACH ROW
BEGIN
    INSERT INTO employee_data_lab (
        employee_id,
        full_name,
        department_id,
        work_email,
        monthly_salary,
        employment_status,
        bank_account_ref
    )
    VALUES (
        :NEW.employee_id,
        :NEW.full_name,
        :NEW.department_id,
        NULL,
        0,
        'ACTIVE',
        NULL
    );
END;
/
~~~

Ở đây department_name chỉ là cột mô tả lấy từ bảng department; trigger dùng department_id để tạo hàng employee. Bảng department không bị thay đổi.

### 9.2. Trách nhiệm của INSTEAD OF trigger

Trigger phải định nghĩa rõ:

- Cột nào được phép INSERT/UPDATE.
- Dữ liệu nào được ghi vào bảng nào.
- Hành vi khi người dùng thay đổi cột suy ra hoặc cột chỉ đọc.
- Cách xử lý bản ghi không tồn tại hoặc vi phạm quan hệ.
- Bảo đảm transaction và lỗi được truyền về caller.

Không COMMIT trong trigger để chia nhỏ đơn vị công việc. DML do trigger thực hiện tham gia transaction của câu lệnh gọi trigger; nếu câu lệnh bị rollback, thay đổi do trigger tạo cũng được rollback theo.

### 9.3. INSTEAD OF trigger không phải cách mặc định cho mọi view

Trigger làm logic ghi khó nhìn thấy từ câu SQL bên ngoài và có thể tăng độ phức tạp khi debug. Chỉ dùng khi view là một API dữ liệu có chủ đích và việc ánh xạ DML được định nghĩa rõ. Nếu một bảng đơn giản có thể được cập nhật trực tiếp qua view, không cần trigger chỉ để thêm một lớp gián tiếp.

## 10. View như một hợp đồng ổn định cho ứng dụng

### 10.1. Tách tên vật lý khỏi tên nghiệp vụ

Ứng dụng có thể truy vấn:

~~~sql
SELECT employee_id, display_name, department_code
FROM api_employee_directory;
~~~

Trong khi view ánh xạ các tên này từ một hoặc nhiều bảng nội bộ:

~~~sql
CREATE OR REPLACE VIEW api_employee_directory (
    employee_id,
    display_name,
    department_code
) AS
SELECT
    e.employee_id,
    e.full_name,
    d.department_name
FROM employee_data_lab e
JOIN department_data_lab d
  ON d.department_id = e.department_id
WHERE e.employment_status = 'ACTIVE';
~~~

Ứng dụng phụ thuộc vào API view. Bên trong database, nhóm phát triển có thể đổi tên bảng hoặc tách bảng nếu vẫn giữ được hợp đồng cột/semantics của view.

### 10.2. Hợp đồng view cần ổn định cả ý nghĩa

Không chỉ tên cột cần ổn định. Hãy ghi rõ:

- Mỗi hàng đại diện cho nhân viên, phòng ban hay một bản ghi tổng hợp.
- Hàng nào bị loại bởi predicate.
- NULL có ý nghĩa gì.
- Đơn vị tiền tệ, thời gian và timezone.
- Có thể có nhiều hàng cho cùng một business key hay không.
- DML có được hỗ trợ không.
- Quyền nào được cấp cho consumer.

Nếu đổi view từ “nhân viên đang hoạt động” sang “mọi nhân viên”, đây là thay đổi semantics có thể ảnh hưởng bảo mật và báo cáo ngay cả khi schema cột không đổi.

### 10.3. Tránh SELECT * trong view API

SELECT * làm hợp đồng khó nhìn và có thể gây nhầm lẫn khi bảng nền thay đổi. Hãy liệt kê rõ cột và alias. Nếu cần thêm cột mới, thực hiện như một thay đổi schema có chủ đích, kiểm tra consumer và cập nhật quyền phù hợp.

### 10.4. Version hóa view khi thay đổi không tương thích

Nếu một thay đổi phá hợp đồng cũ, có thể tạo view phiên bản mới:

~~~sql
CREATE VIEW api_employee_directory_v2 AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email,
    employment_status
FROM employee_data_lab;
~~~

Consumer cũ tiếp tục dùng view v1 trong thời gian chuyển đổi; consumer mới dùng v2. Khi không còn consumer cũ, có thể ngừng cấp quyền và loại bỏ v1 theo kế hoạch.

## 11. View, inline view, CTE, synonym và materialized view

Các khái niệm này có mục đích khác nhau:

| Đối tượng/cấu trúc | Phạm vi | Lưu kết quả? | Dùng làm ranh giới quyền? |
| --- | --- | --- | --- |
| View thường | Đối tượng schema dùng lại được | Không lưu result set | Có, qua object privileges |
| Inline view | Query block trong FROM của một câu SQL | Không | Không phải object cấp quyền độc lập |
| CTE (WITH clause) | Tên query block trong một statement | Không mặc định | Không phải object cấp quyền độc lập |
| Synonym | Bí danh cho object khác | Không | Không; không cấp quyền thay object |
| Materialized view | Đối tượng schema lưu kết quả truy vấn | Có | Có thể cấp quyền trên object, nhưng cần quản lý refresh/data freshness |

### 11.1. Inline view

~~~sql
SELECT department_id, employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employee_data_lab
    GROUP BY department_id
)
WHERE employee_count >= 2;
~~~

Inline view chỉ tồn tại trong câu SQL này. Nếu nhiều ứng dụng cần cùng logic, một view schema có thể dễ tái sử dụng và cấp quyền hơn.

### 11.2. CTE

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id
    FROM employee_data_lab
    WHERE employment_status = 'ACTIVE'
)
SELECT department_id, COUNT(*)
FROM active_employees
GROUP BY department_id;
~~~

CTE làm câu SQL nhiều bước dễ đọc. Nó không tạo object schema và không phải API quyền độc lập.

### 11.3. Synonym

~~~sql
CREATE SYNONYM employee_directory
FOR report_owner.v_employee_directory;
~~~

Synonym giúp gọi object bằng tên khác. Nó không tự cấp SELECT trên view và không làm bảng nền an toàn hơn. Người dùng vẫn cần quyền phù hợp trên object đích.

### 11.4. Materialized view

Materialized view lưu kết quả truy vấn dưới dạng dữ liệu vật lý và có cơ chế refresh. Nó phù hợp khi cần giảm chi phí tính toán lặp lại hoặc hỗ trợ báo cáo phân tích, nhưng phải quản lý độ mới của dữ liệu và refresh strategy.

~~~sql
CREATE MATERIALIZED VIEW mv_department_payroll_lab
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT
    department_id,
    COUNT(*) AS employee_count,
    SUM(monthly_salary) AS total_salary
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
GROUP BY department_id;
~~~

Đây chỉ là ví dụ cấu trúc cơ bản. Khả năng FAST REFRESH và query rewrite phụ thuộc định nghĩa, materialized view logs, constraints, query shape và cấu hình. Materialized view không tự động luôn nhanh hơn hoặc luôn mới nhất.

## 12. View và hiệu năng: optimizer nhìn thấy gì?

### 12.1. View thường không phải một lớp thực thi vật lý bắt buộc

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW v_active_employee_lab AS
SELECT employee_id, department_id, full_name
FROM employee_data_lab
WHERE employment_status = 'ACTIVE';
~~~

Truy vấn:

~~~sql
SELECT employee_id, full_name
FROM v_active_employee_lab
WHERE department_id = 10;
~~~

Oracle optimizer có thể hợp nhất view vào query block bên ngoài (view merging) hoặc đẩy predicate xuống gần bảng nền (predicate pushing) khi transformation hợp lệ. Plan có thể truy cập trực tiếp bảng nền và không nhất thiết có một operation “VIEW” riêng.

### 12.2. Không giả định view làm truy vấn nhanh hơn

View thường giúp tái sử dụng và quản lý logic. Nó không tự lưu cache kết quả. Hiệu năng phụ thuộc:

- Số dòng bảng nền và selectivity predicate.
- Index và thống kê.
- Join order, join method và access path.
- Các phép aggregate, DISTINCT, analytic hoặc set operator.
- Khả năng optimizer merge view/push predicate.
- Số tầng view lồng nhau và độ phức tạp truy vấn.

Một view phức tạp dùng ở nhiều nơi có thể làm query khó hiểu nếu các consumer tiếp tục lồng nhiều view khác. Hãy giữ từng view có grain và trách nhiệm rõ.

### 12.3. View merging và predicate pushing

Optimizer có thể biến đổi:

~~~sql
SELECT *
FROM v_active_employee_lab
WHERE department_id = 10;
~~~

thành một truy vấn tương đương trên bảng nền với cả hai predicate. Điều này cho phép chọn index/access path tốt hơn. Một số cấu trúc hoặc semantics có thể hạn chế transformation; không nên dựa vào việc mọi view luôn được merge.

### 12.4. Đọc execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id, full_name
FROM v_active_employee_lab
WHERE department_id = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Để xem actual statistics cho một lần chạy:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id, full_name
FROM v_active_employee_lab
WHERE department_id = 10;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Xem operation trên bảng nền, predicate được áp dụng ở đâu, E-Rows/A-Rows, Starts, Buffers và A-Time. Đừng kết luận view chậm chỉ vì SQL bên ngoài ngắn hơn hoặc dài hơn.

### 12.5. Khi cần lưu kết quả, xem materialized view

Nếu một báo cáo aggregate lớn chạy liên tục và dữ liệu không cần cập nhật tức thời ở mỗi lần truy vấn, materialized view có thể là lựa chọn. Nhưng phải đánh giá:

- Refresh COMPLETE hay FAST.
- ON DEMAND hay ON COMMIT.
- Độ trễ dữ liệu chấp nhận được.
- Chi phí refresh và lưu trữ.
- Materialized view log và khả năng query rewrite.

Đừng thay view thường bằng materialized view chỉ để “tăng tốc” khi chưa đo và chưa xác định freshness requirement.

## 13. Dependency và vòng đời view

### 13.1. View phụ thuộc vào object nền

Nếu view tham chiếu bảng hoặc view khác, Oracle ghi dependency trong data dictionary. Khi object nền bị DROP, thay đổi không tương thích hoặc không còn quyền cần thiết, view có thể trở thành INVALID hoặc lỗi khi truy vấn.

Không nên DROP/CREATE bảng nền một cách tùy tiện khi nhiều view và package đang phụ thuộc. Hãy triển khai migration theo thứ tự và kiểm tra object phụ thuộc.

### 13.2. Xem danh sách view trong schema

~~~sql
SELECT view_name, text_length
FROM user_views
ORDER BY view_name;
~~~

### 13.3. Xem trạng thái object

~~~sql
SELECT object_name, status, last_ddl_time
FROM user_objects
WHERE object_type = 'VIEW'
ORDER BY object_name;
~~~

VALID cho biết object hiện hợp lệ theo trạng thái dictionary; INVALID cho biết cần biên dịch lại hoặc xử lý lỗi dependency.

### 13.4. Xem dependency

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE type = 'VIEW'
ORDER BY name, referenced_owner, referenced_name;
~~~

ALL_DEPENDENCIES/DBA_DEPENDENCIES cho phạm vi rộng hơn nếu user có quyền xem.

### 13.5. Xem lỗi biên dịch

~~~sql
SELECT
    name,
    type,
    line,
    position,
    text
FROM user_errors
WHERE type = 'VIEW'
ORDER BY name, sequence;
~~~

Trong SQL*Plus hoặc công cụ tương thích, có thể dùng SHOW ERRORS VIEW view_name. USER_ERRORS hữu ích khi cần truy vấn lỗi bằng SQL hoặc đưa vào script triển khai.

### 13.6. Biên dịch lại view

~~~sql
ALTER VIEW v_employee_directory_lab COMPILE;
~~~

Sau đó kiểm tra USER_OBJECTS và USER_ERRORS. COMPILE không tự sửa một tên cột đã bị xóa hoặc quyền đã mất; phải sửa dependency hoặc định nghĩa trước.

### 13.7. Lấy DDL của view

~~~sql
SELECT DBMS_METADATA.GET_DDL(
           'VIEW',
           'V_EMPLOYEE_DIRECTORY_LAB',
           USER
       )
FROM dual;
~~~

DBMS_METADATA hữu ích cho migration, review định nghĩa và sao lưu DDL. Quyền truy cập metadata có thể phụ thuộc user và cấu hình.

## 14. Thay đổi và xóa view

### 14.1. CREATE OR REPLACE là cách cập nhật thường dùng

~~~sql
CREATE OR REPLACE VIEW v_employee_directory_lab AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email,
    employment_status
FROM employee_data_lab
WHERE employment_status IN ('ACTIVE', 'LEAVE')
WITH READ ONLY;
~~~

Khi sửa view:

- Kiểm tra tên và datatype cột đầu ra.
- Kiểm tra consumer phụ thuộc.
- Kiểm tra quyền trên view sau triển khai.
- Kiểm tra trạng thái VALID/INVALID và lỗi.
- Chạy các truy vấn đại diện và xem plan nếu thay đổi đáng kể.

Việc thay đổi định nghĩa view có thể ảnh hưởng các view/package phụ thuộc. Hãy triển khai theo dependency order và có phương án rollback DDL rõ ràng.

### 14.2. DROP VIEW

~~~sql
DROP VIEW v_employee_directory_lab;
~~~

DROP VIEW xóa view object, không xóa các bảng nền. Tuy nhiên, các object phụ thuộc có thể bị invalid hoặc không còn sử dụng được. DROP VIEW là DDL và có implicit commit theo quy tắc Oracle.

Không nhầm DROP VIEW với DROP TABLE. Xóa view không xóa dữ liệu nguồn.

### 14.3. View grants và thay đổi định nghĩa

Khi quản lý migration, hãy kiểm tra các quyền đã cấp trên view và tái xác nhận quyền sau khi thay đổi. CREATE OR REPLACE thường được dùng để sửa view mà không cần DROP object trước; tránh DROP/CREATE không cần thiết vì có thể tạo khoảng thời gian consumer không truy cập được và làm mất các metadata/grant cần thiết tùy thao tác.

## 15. Các lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| ORA-01031 insufficient privileges khi CREATE VIEW | Thiếu CREATE VIEW hoặc quyền trực tiếp trên bảng nền | Kiểm tra system privilege và direct object grants |
| View INVALID | Bảng/cột nền thay đổi, dependency không hợp lệ hoặc FORCE tạo view chưa sẵn sàng | Xem USER_ERRORS, USER_DEPENDENCIES và compile lại sau khi sửa |
| ORA-00904 invalid identifier | Tên cột sai hoặc cột nền đã đổi | Kiểm tra định nghĩa bảng và SQL view |
| ORA-01779 cannot modify a column which maps to a non key-preserved table | DML qua join view nhắm vào bảng không key-preserved | Thiết kế DML rõ ràng hoặc dùng INSTEAD OF trigger |
| ORA-01402 view WITH CHECK OPTION where-clause violation | DML làm hàng không còn thỏa predicate view | Sửa giá trị hoặc thiết kế lại view/policy |
| Ứng dụng vẫn đọc được cột nhạy cảm | User còn quyền trực tiếp trên bảng hoặc quyền hệ thống rộng | Rà soát grants, roles và quyền kế thừa |
| View không thấy hàng vừa đổi trạng thái | Predicate view loại hàng đó | Kiểm tra WHERE và transaction commit |
| View lồng nhiều tầng khó tối ưu | Nhiều lớp truy vấn phức tạp hoặc transformation bị hạn chế | Đơn giản hóa contract, xem execution plan |
| Tưởng view lưu kết quả | Nhầm view thường với materialized view | Xác định yêu cầu freshness và loại object |

## 16. Bài thực hành tổng hợp: công bố API đọc nhân viên

Lab này minh họa cách schema owner cung cấp view và ứng dụng chỉ được cấp quyền trên view.

### Bước 1 — Tạo bảng và dữ liệu

Chạy Mục 3 trong schema lab. Nếu đã có bảng, không tạo lại; dùng tên lab khác hoặc làm sạch đúng bảng do bạn tạo.

### Bước 2 — Tạo view danh bạ

~~~sql
CREATE OR REPLACE VIEW v_employee_directory_lab AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

### Bước 3 — Kiểm tra dữ liệu được công bố

~~~sql
SELECT *
FROM v_employee_directory_lab
ORDER BY employee_id;
~~~

Kết quả chỉ có nhân viên ACTIVE và không có monthly_salary/bank_account_ref.

### Bước 4 — Tạo role và cấp quyền trên view

~~~sql
CREATE ROLE employee_directory_reader_lab;
GRANT SELECT ON v_employee_directory_lab
TO employee_directory_reader_lab;
~~~

Nếu role đã tồn tại, bỏ qua CREATE ROLE. DBA hoặc user có quyền phù hợp cấp role cho application user:

~~~sql
GRANT employee_directory_reader_lab TO app_reader_lab;
~~~

Thay app_reader_lab bằng user thử nghiệm thực tế. Không cấp quyền trên bảng nền cho user này nếu mục tiêu là chỉ truy cập qua view.

### Bước 5 — Thử quyền từ application user

Đăng nhập bằng app_reader_lab:

~~~sql
SELECT employee_id, full_name, department_id, work_email
FROM owner_schema.v_employee_directory_lab;
~~~

Nếu view nằm cùng schema với user, có thể bỏ owner prefix. Tên schema cần thay bằng owner thực tế.

Thử truy vấn bảng nền:

~~~sql
SELECT bank_account_ref
FROM owner_schema.employee_data_lab;
~~~

Truy vấn này phải bị từ chối nếu application user không được cấp quyền trực tiếp hoặc quyền rộng khác trên bảng nền.

Thử DML qua view:

~~~sql
UPDATE owner_schema.v_employee_directory_lab
SET full_name = 'Changed Name'
WHERE employee_id = 101;
~~~

DML bị từ chối vì view được khai báo WITH READ ONLY.

### Bước 6 — Thử CHECK OPTION

Tạo view có thể cập nhật:

~~~sql
CREATE OR REPLACE VIEW v_active_employee_check_lab AS
SELECT employee_id, full_name, employment_status
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT ck_active_employee_check_lab;
~~~

Thử thay trạng thái:

~~~sql
UPDATE v_active_employee_check_lab
SET employment_status = 'INACTIVE'
WHERE employee_id = 101;
~~~

Oracle từ chối vì hàng sau UPDATE không còn thỏa predicate ACTIVE. Rollback nếu đang thử nghiệm trong transaction:

~~~sql
ROLLBACK;
~~~

### Bước 7 — Kiểm tra metadata

~~~sql
SELECT view_name, text_length
FROM user_views
WHERE view_name LIKE 'V_%_LAB'
ORDER BY view_name;

SELECT object_name, status
FROM user_objects
WHERE object_type = 'VIEW'
  AND object_name LIKE 'V_%_LAB'
ORDER BY object_name;
~~~

### Bước 8 — Dọn object lab (tùy chọn)

Chỉ chạy khi chắc chắn object thuộc lab và không cần dữ liệu:

~~~sql
DROP VIEW v_employee_directory_lab;
DROP VIEW v_department_payroll_lab;
DROP VIEW v_employee_department_lab;
DROP VIEW v_employee_edit_lab;
DROP VIEW v_active_employee_edit_lab;
DROP VIEW v_active_employee_checked_lab;
DROP VIEW v_employee_directory_readonly_lab;
DROP VIEW v_employee_dept_edit_lab;
DROP VIEW v_employee_compensation_lab;
DROP VIEW v_employee_department_api_lab;
DROP VIEW v_department_payroll_readonly_lab;
DROP VIEW api_employee_directory;
~~~

Sau khi các view đã được xử lý, có thể xóa trigger và bảng lab do bạn tạo theo thứ tự dependency. Không chạy DROP trên object không rõ ownership. DDL có implicit commit, nên chỉ dọn sau khi transaction thực hành đã kết thúc.

## 17. Nguyên tắc thiết kế view cho ứng dụng

Khi tạo view dùng làm data access boundary, hãy xác định rõ:

1. **Owner:** schema nào sở hữu bảng, schema nào sở hữu view?
2. **Consumer:** ứng dụng, báo cáo hay người dùng nào cần truy cập?
3. **Contract:** grain, tên cột, datatype, ý nghĩa NULL và semantics của từng hàng.
4. **Projection:** chỉ công bố những cột consumer cần.
5. **Row filter:** điều kiện hàng nào được hiển thị và ai có quyền thay đổi điều kiện đó?
6. **Privileges:** view owner có direct grants cần thiết chưa; application role có đúng quyền trên view chưa?
7. **DML policy:** view read-only hay updatable; có CHECK OPTION hoặc INSTEAD OF trigger không?
8. **Security boundary:** consumer có còn quyền trực tiếp trên bảng nền hoặc quyền system rộng không?
9. **Dependency:** object nền và các view/package phụ thuộc có được quản lý trong migration không?
10. **Performance:** execution plan có access path phù hợp; predicate có được push xuống; actual rows có đúng kỳ vọng không?

### 17.1. Một mẫu phân tầng thực tế

~~~text
DATA SCHEMA
  normalized tables
  constraints and indexes
       |
       | direct grants to view owner
       v
ACCESS/API SCHEMA
  public read views
  reporting views
  controlled DML views
       |
       | object grants to application roles
       v
APPLICATION SCHEMA / SERVICE
  SELECT or permitted DML through views
~~~

Schema phân tầng giúp tách trách nhiệm, nhưng chỉ hiệu quả khi grants được quản lý đúng. Nếu ứng dụng vẫn dùng tài khoản owner có quyền toàn bộ bảng, view chỉ là quy ước trong code, chưa phải ranh giới quyền thực sự.

## 18. Câu hỏi tự kiểm tra

1. View thường lưu định nghĩa hay lưu kết quả truy vấn?
2. Vì sao view không tự động làm truy vấn nhanh hơn?
3. Khi nào dùng CREATE OR REPLACE VIEW?
4. FORCE khác NOFORCE thế nào?
5. Vì sao nên liệt kê cột thay vì SELECT * trong view?
6. View owner cần loại quyền nào trên bảng nền ở schema khác?
7. Vì sao quyền lấy qua role không đủ để định nghĩa stored view?
8. User ứng dụng cần quyền gì để SELECT view?
9. Vì sao user có quyền SELECT trực tiếp trên bảng nền có thể bỏ qua view?
10. WITH READ ONLY giới hạn điều gì?
11. WITH CHECK OPTION bảo vệ điều kiện nào?
12. CHECK OPTION có ngăn user cập nhật bảng nền trực tiếp không?
13. Key-preserved table nghĩa là gì trong join view?
14. Khi nào Oracle có thể báo ORA-01779?
15. INSTEAD OF trigger dùng để giải quyết trường hợp nào?
16. Vì sao không nên COMMIT bên trong INSTEAD OF trigger?
17. Synonym có tự cấp quyền truy cập object đích không?
18. Materialized view khác view thường ở đâu?
19. USER_VIEWS, USER_OBJECTS và USER_ERRORS giúp kiểm tra điều gì?
20. Vì sao phải kiểm tra grants sau khi thay đổi view?
21. View predicate theo tenant có tự tạo row-level security hoàn chỉnh không?
22. View merging và predicate pushing có vai trò gì?
23. Khi nào cần xem actual plan thay vì chỉ EXPLAIN PLAN?
24. Vì sao view API cần ổn định cả semantics chứ không chỉ tên cột?

**Gợi ý trả lời:**

1. View thường lưu query definition; không lưu result set.
2. Optimizer vẫn thực thi truy vấn nền; view không tự cache kết quả.
3. Khi cần thay định nghĩa view hiện có mà không DROP trước.
4. NOFORCE yêu cầu dependency hợp lệ; FORCE có thể tạo view chưa hợp lệ để xử lý sau.
5. Để hợp đồng cột rõ ràng và tránh vô tình công bố cột mới.
6. Object privileges được cấp trực tiếp trên object nền.
7. Stored view cần quyền trực tiếp, không dựa vào role của owner.
8. SELECT trên view hoặc role chứa SELECT trên view.
9. Vì quyền rộng hơn cho phép truy vấn trực tiếp bảng gốc.
10. INSERT/UPDATE/DELETE qua view.
11. Yêu cầu hàng sau DML vẫn đáp ứng predicate của view.
12. Không.
13. Mỗi hàng của bảng đó xuất hiện tối đa một lần trong kết quả join theo quan hệ khóa được chứng minh.
14. Khi cố DML lên bảng không key-preserved qua join view.
15. Khi view phức tạp không updatable theo quy tắc mặc định nhưng cần định nghĩa DML mapping.
16. Vì DML của trigger phải cùng transaction với statement gọi trigger.
17. Không; synonym chỉ là bí danh.
18. Materialized view lưu kết quả và cần refresh; view thường lưu định nghĩa truy vấn.
19. Danh sách view, trạng thái object và lỗi biên dịch.
20. Để bảo đảm consumer còn đúng quyền và không bị mất quyền ngoài ý muốn.
21. Không; cần context đáng tin cậy/VPD hoặc cơ chế row-level security phù hợp.
22. Cho optimizer hợp nhất query block và đẩy điều kiện xuống gần bảng nền khi hợp lệ.
23. Khi cần biết runtime rows, buffers, starts và thời gian thực tế.
24. Thay đổi predicate có thể đổi tập dữ liệu hoặc chính sách truy cập dù schema cột không đổi.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — CREATE VIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-VIEW.html): cú pháp tạo view, FORCE, CHECK OPTION và READ ONLY.
- [Oracle Database SQL Language Reference — Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Views.html): khái niệm và cách sử dụng view.
- [Oracle Database Administrator's Guide — Managing Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-views.html): tạo, thay đổi và quản lý view.
- [Oracle Database SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html): INSTEAD OF trigger và trigger semantics.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): object privileges, least privilege và kiểm soát truy cập.
- [Oracle Database SQL Tuning Guide — Query Transformations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html): view merging và các query transformations.
- [Oracle Database SQL Language Reference — CREATE MATERIALIZED VIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-MATERIALIZED-VIEW.html): materialized view và refresh options.

**Nguyên tắc cần nhớ:** view tạo một hợp đồng truy cập ở cấp schema. Hãy công bố đúng cột và hàng, cấp quyền trên view cho consumer, giữ quyền bảng nền ở mức tối thiểu, và xác định rõ view có chỉ đọc hay cho phép DML. View giúp tổ chức quyền và trừu tượng hóa dữ liệu, nhưng chỉ trở thành ranh giới bảo mật hiệu quả khi các quyền rộng hơn trên bảng nền và hệ thống được kiểm soát.
