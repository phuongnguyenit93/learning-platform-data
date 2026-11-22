# Fine-Grained Auditing và điều kiện áp dụng

Fine-Grained Auditing (FGA) là cơ chế kiểm toán chi tiết của Oracle Database, cho phép ghi nhận việc truy cập dữ liệu khi một câu lệnh thỏa mãn điều kiện được cấu hình. Thay vì ghi mọi lần truy cập vào một bảng, FGA có thể tập trung vào những cột, loại câu lệnh và dòng dữ liệu có ý nghĩa bảo mật.

Ví dụ, bộ phận bảo mật có thể cần biết khi ai đó đọc cột SALARY của nhân viên có mức lương từ một ngưỡng nhất định, hoặc khi một tài khoản truy cập hồ sơ khách hàng thuộc nhóm dữ liệu nhạy cảm. FGA cho phép định nghĩa policy gắn với bảng hoặc view, chỉ định loại câu lệnh, danh sách cột và điều kiện áp dụng.

FGA là cơ chế **ghi nhận và tạo bằng chứng kiểm toán**. Nó không tự ngăn người dùng đọc dữ liệu, không thay thế quyền truy cập, không che dữ liệu và không thay thế kiểm soát hàng. Muốn ngăn truy cập phải dùng privilege, view, Virtual Private Database (VPD), Oracle Label Security hoặc cơ chế kiểm soát phù hợp khác.

## 1. FGA giải quyết bài toán gì?

Kiểm toán truyền thống thường ghi nhận hoạt động theo loại câu lệnh hoặc object. Điều đó hữu ích để biết một tài khoản đã truy cập bảng nào, nhưng có thể tạo nhiều bản ghi không cần thiết nếu chỉ một phần dữ liệu trong bảng thực sự nhạy cảm.

FGA cho phép xác định một policy theo nhiều chiều:

- **Object:** bảng hoặc view cần theo dõi.
- **Statement type:** SELECT, INSERT, UPDATE hoặc DELETE theo policy.
- **Audit columns:** các cột mà câu lệnh phải tham chiếu để policy được kích hoạt.
- **Audit condition:** điều kiện dữ liệu phải thỏa mãn.
- **Handler:** thủ tục PL/SQL tùy chọn được gọi khi phát sinh audit event.
- **Enabled state:** policy đang được bật hay tắt.

Ví dụ, bảng HR.EMPLOYEES chứa cả dữ liệu thông thường như tên và dữ liệu nhạy cảm như SALARY. Tổ chức có thể chỉ cần kiểm toán các truy vấn tham chiếu SALARY và truy cập ít nhất một dòng có SALARY từ 15.000 trở lên.

FGA giúp biểu diễn chính sách đó ngay tại database, nơi dữ liệu được truy cập. Việc kiểm toán không phải phụ thuộc hoàn toàn vào việc từng ứng dụng tự ghi log đúng cách.

## 2. Phân biệt FGA với các cơ chế bảo mật khác

Các cơ chế bảo mật có mục tiêu khác nhau. Chọn sai cơ chế sẽ dẫn đến kỳ vọng sai về tác dụng của policy.

| Cơ chế | Mục tiêu chính | Ví dụ |
|---|---|---|
| Object privilege | Cho phép hoặc từ chối thao tác trên object | GRANT SELECT ON HR.EMPLOYEES |
| Fine-Grained Auditing | Ghi nhận truy cập thỏa điều kiện | Ghi audit khi truy cập SALARY của nhóm nhân viên nhạy cảm |
| Unified Auditing | Quản lý và lưu audit event tập trung theo policy | Ghi nhận đăng nhập, privilege use, object action |
| VPD | Giới hạn các dòng người dùng có thể nhìn thấy | Nhân viên chỉ xem hồ sơ thuộc phòng ban của mình |
| Oracle Label Security | Kiểm soát truy cập theo nhãn và cấp độ dữ liệu | Chỉ người có nhãn phù hợp mới đọc được hồ sơ |
| Data Redaction | Che hoặc biến đổi giá trị trả về | Ẩn một phần số định danh trong kết quả |

FGA không phải VPD. Nếu người dùng không được phép đọc một dòng, VPD hoặc quyền truy cập phải thực thi giới hạn đó. FGA có thể ghi nhận rằng một truy vấn đã truy cập dữ liệu thỏa điều kiện kiểm toán, nhưng không tự loại dòng khỏi kết quả.

FGA cũng không đồng nghĩa Unified Auditing. FGA là cơ chế policy kiểm toán chi tiết trên dữ liệu; Unified Auditing là kiến trúc audit trail và policy tập trung của Oracle. Trong môi trường bật Unified Auditing, bản ghi FGA được tích hợp vào unified audit trail. Với cấu hình audit truyền thống, cần kiểm tra các view FGA audit trail tương ứng.

## 3. Cách một FGA policy được kích hoạt

Một FGA policy được gắn với một bảng hoặc view. Khi câu lệnh thuộc loại được theo dõi tham chiếu object đó, Oracle kiểm tra các điều kiện policy.

Có thể hình dung logic kích hoạt như sau:

1. Câu SQL truy cập object có FGA policy.
2. Loại câu lệnh nằm trong statement_types của policy.
3. Câu lệnh tham chiếu cột phù hợp với audit_column và audit_column_opts, nếu policy giới hạn cột.
4. Audit condition được đánh giá trong ngữ cảnh truy cập dữ liệu.
5. Khi điều kiện policy được thỏa mãn, Oracle tạo audit event theo cơ chế audit trail của database.
6. Nếu policy có handler, thủ tục handler được gọi theo cơ chế của FGA.

Điều kiện cột và điều kiện dữ liệu có vai trò khác nhau:

- Audit column trả lời: câu SQL có tham chiếu cột cần kiểm toán không?
- Audit condition trả lời: dữ liệu được truy cập có thỏa điều kiện cần kiểm toán không?

Nếu audit_column là NULL, policy không giới hạn theo danh sách cột. Nếu audit_condition là NULL, policy không giới hạn theo predicate dữ liệu và có thể audit mọi truy cập phù hợp với các điều kiện còn lại.

Một audit event của FGA là bằng chứng cho câu lệnh thỏa policy. Không nên xem audit trail như bảng sao chép từng dòng dữ liệu được đọc. FGA không phải cơ chế xuất toàn bộ từng row đã được truy cập để tái dựng kết quả truy vấn.

## 4. Thành phần của DBMS_FGA.ADD_POLICY

Package DBMS_FGA cung cấp API tạo và quản lý policy. Thủ tục thường dùng nhất là ADD_POLICY.

Cấu trúc minh họa:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema       => 'HR',
    object_name         => 'EMPLOYEES',
    policy_name         => 'AUDIT_HIGH_SALARY',
    audit_condition     => 'SALARY >= 15000',
    audit_column        => 'SALARY',
    statement_types     => 'SELECT',
    audit_column_opts   => DBMS_FGA.ANY_COLUMNS,
    enable              => TRUE
  );
END;
/
~~~

Các tham số quan trọng:

| Tham số | Ý nghĩa |
|---|---|
| object_schema | Schema sở hữu bảng hoặc view |
| object_name | Tên bảng hoặc view được kiểm toán |
| policy_name | Tên policy, cần duy nhất trong phạm vi object theo quy tắc Oracle |
| audit_condition | Điều kiện dữ liệu; NULL nghĩa là không giới hạn theo điều kiện này |
| audit_column | Danh sách cột cần tham chiếu để policy được kích hoạt; NULL nghĩa là không giới hạn cột |
| statement_types | Các loại câu lệnh được kiểm toán |
| audit_column_opts | Cách kết hợp các cột trong audit_column |
| handler_schema | Schema chứa handler PL/SQL nếu có |
| handler_module | Tên thủ tục handler nếu có |
| enable | Bật hoặc tắt policy khi tạo |
| audit_trail | Tham số lịch sử liên quan loại audit trail; cách sử dụng phụ thuộc phiên bản và chế độ auditing |

Các loại statement thường được chỉ định là SELECT, INSERT, UPDATE và DELETE. Hãy kiểm tra tài liệu đúng release trước khi dựa vào cách xử lý các câu lệnh kết hợp hoặc cú pháp mới như MERGE.

Trong các phiên bản Oracle hiện đại, audit_trail trong DBMS_FGA.ADD_POLICY là tham số lịch sử và cách ghi nhận phụ thuộc chế độ auditing. Không nên sao chép giá trị audit_trail từ một ví dụ cũ mà chưa xác định database đang dùng traditional auditing hay Unified Auditing.

## 5. Audit condition: điều kiện theo dữ liệu

audit_condition là biểu thức điều kiện SQL dùng để quyết định dữ liệu truy cập có thuộc phạm vi cần kiểm toán hay không.

Ví dụ:

~~~sql
audit_condition => 'SALARY >= 15000'
~~~

Policy chỉ cần ghi nhận các truy cập mà điều kiện lương được thỏa mãn. Một policy khác có thể theo dõi dữ liệu của một phòng ban:

~~~sql
audit_condition => 'DEPARTMENT_ID = 90'
~~~

Hoặc theo một trạng thái nhạy cảm:

~~~sql
audit_condition => 'ACCOUNT_STATUS = ''SUSPENDED'''
~~~

Lưu ý dấu nháy đơn lồng nhau trong chuỗi PL/SQL: literal SQL SUSPENDED được viết thành hai dấu nháy đơn ở mỗi phía bên trong chuỗi audit_condition.

### 5.1 Điều kiện NULL và điều kiện có giá trị

Nếu audit_condition là NULL, FGA không lọc theo giá trị dòng. Policy vẫn có thể được giới hạn bằng statement_types và audit_column.

Nếu audit_condition có biểu thức, policy đánh giá điều kiện đó trong quá trình truy cập dữ liệu. Khi có dữ liệu phù hợp với điều kiện, audit event được tạo theo ngữ nghĩa FGA.

Không nên nhầm audit_condition với WHERE clause của câu SQL do ứng dụng gửi. WHERE clause của ứng dụng quyết định tập kết quả; audit_condition của policy quyết định truy cập đó có thuộc diện phải ghi audit hay không.

Ví dụ policy có điều kiện SALARY >= 15000. Ứng dụng có thể truy vấn theo department_id, không cần đưa điều kiện salary vào SQL. FGA vẫn áp dụng điều kiện của policy khi đánh giá dữ liệu được truy cập.

### 5.2 Điều kiện phải phù hợp với object

Tên cột trong audit_condition phải thuộc object được kiểm toán và cần được viết theo cú pháp SQL hợp lệ cho policy. Hãy dùng tên cột rõ ràng, kiểu dữ liệu tương thích và biểu thức đơn giản.

Có thể dùng biểu thức SQL và context phù hợp để phân biệt session hoặc ứng dụng, ví dụ SYS_CONTEXT với USERENV hoặc application context đã được thiết lập có kiểm soát. Điều này hữu ích khi policy cần quan tâm đến client identifier hoặc một thuộc tính session.

Ví dụ minh họa:

~~~sql
audit_condition =>
  'DEPARTMENT_ID = 90 AND SYS_CONTEXT(''USERENV'', ''SESSION_USER'') <> ''SEC_AUDITOR'''
~~~

Biểu thức trong ví dụ chỉ minh họa cách tham chiếu session context. Cần kiểm tra cú pháp và hành vi của điều kiện trên phiên bản Oracle mục tiêu, đồng thời bảo đảm context do ứng dụng thiết lập không thể bị người dùng giả mạo ngoài ý muốn.

Tránh đưa logic phức tạp, phụ thuộc trạng thái thay đổi hoặc gọi hàm có side effect vào audit_condition. Policy được đánh giá trong quá trình thực thi SQL; biểu thức phức tạp có thể làm tăng chi phí và khiến hành vi khó dự đoán.

### 5.3 NULL, ba giá trị logic và dữ liệu thiếu

SQL sử dụng logic ba giá trị: TRUE, FALSE và UNKNOWN. Khi điều kiện liên quan một cột NULL, kết quả so sánh có thể là UNKNOWN chứ không phải FALSE.

Ví dụ:

~~~sql
SALARY >= 15000
~~~

Nếu SALARY là NULL, điều kiện không đánh giá TRUE. Nếu yêu cầu kiểm toán cả các dòng chưa có salary, cần diễn đạt rõ:

~~~sql
SALARY >= 15000 OR SALARY IS NULL
~~~

Điều kiện phải phản ánh chính sách thực tế. Không giả định NULL tự động thuộc hoặc không thuộc nhóm dữ liệu nhạy cảm.

## 6. Audit column và audit_column_opts

audit_column giới hạn policy vào các cột được câu lệnh tham chiếu. Đây là cách giảm số sự kiện không liên quan khi bảng có nhiều cột nhưng chỉ một vài cột nhạy cảm.

Ví dụ:

~~~sql
audit_column => 'SALARY, COMMISSION_PCT'
~~~

Nếu audit_column_opts là DBMS_FGA.ANY_COLUMNS, việc tham chiếu ít nhất một cột trong danh sách có thể kích hoạt phần điều kiện cột.

Nếu audit_column_opts là DBMS_FGA.ALL_COLUMNS, câu lệnh phải tham chiếu tất cả các cột trong danh sách theo quy tắc policy.

| Tùy chọn | Cách kết hợp |
|---|---|
| DBMS_FGA.ANY_COLUMNS | Chỉ cần một cột trong danh sách được tham chiếu |
| DBMS_FGA.ALL_COLUMNS | Tất cả cột trong danh sách phải được tham chiếu |

Ví dụ policy theo dõi salary và commission:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema     => 'HR',
    object_name       => 'EMPLOYEES',
    policy_name       => 'AUDIT_PAY_FIELDS',
    audit_condition   => 'SALARY >= 15000',
    audit_column      => 'SALARY, COMMISSION_PCT',
    statement_types   => 'SELECT',
    audit_column_opts => DBMS_FGA.ANY_COLUMNS
  );
END;
/
~~~

Với ANY_COLUMNS, truy vấn tham chiếu SALARY hoặc COMMISSION_PCT có thể đáp ứng điều kiện cột. Với ALL_COLUMNS, policy đòi hỏi câu lệnh tham chiếu cả hai cột.

### 6.1 Cột trong SELECT list và cột trong predicate

Một cột có thể được tham chiếu trong SELECT list, WHERE, JOIN, ORDER BY hoặc biểu thức khác. Khi xem policy có kích hoạt hay không, cần xem toàn bộ SQL statement và cách Oracle xác định cột được truy cập.

Ví dụ:

~~~sql
-- Tham chiếu SALARY trong SELECT list
SELECT employee_id, salary
FROM hr.employees
WHERE department_id = 90;
~~~

~~~sql
-- Tham chiếu SALARY trong predicate
SELECT employee_id
FROM hr.employees
WHERE salary >= 15000;
~~~

Cả hai câu lệnh đều tham chiếu SALARY. Với policy theo dõi cột SALARY, không nên chỉ kiểm tra danh sách cột trả về.

Ngược lại:

~~~sql
SELECT employee_id, first_name
FROM hr.employees
WHERE department_id = 90;
~~~

Nếu SALARY không được tham chiếu và policy chỉ theo dõi SALARY, câu truy vấn này có thể không thỏa điều kiện cột. Điều đó không có nghĩa dữ liệu salary không tồn tại trong bảng; nó chỉ không được truy cập qua cột được policy chỉ định.

### 6.2 Chọn ANY hay ALL

Chọn ANY_COLUMNS khi chỉ cần phát hiện việc truy cập bất kỳ trường nhạy cảm nào trong nhóm.

Chọn ALL_COLUMNS khi sự kiện chỉ có ý nghĩa nếu câu lệnh sử dụng đồng thời toàn bộ các trường trong nhóm. Đây là trường hợp hẹp hơn và cần được kiểm thử bằng SQL thực tế.

Không nên chọn ALL_COLUMNS chỉ để giảm số bản ghi mà không hiểu rằng một câu SQL truy cập riêng từng cột có thể không được ghi nhận.

## 7. Statement types: kiểm toán loại thao tác nào?

statement_types chỉ định loại câu lệnh được policy theo dõi.

Ví dụ chỉ kiểm toán SELECT:

~~~sql
statement_types => 'SELECT'
~~~

Kiểm toán SELECT và UPDATE:

~~~sql
statement_types => 'SELECT,UPDATE'
~~~

Các loại thông dụng:

- **SELECT:** đọc dữ liệu.
- **INSERT:** thêm dữ liệu.
- **UPDATE:** thay đổi dữ liệu.
- **DELETE:** xóa dữ liệu.

Cần phân biệt FGA với audit DDL. Tạo bảng, thay đổi cấu trúc, cấp quyền hoặc đăng nhập không phải là mục tiêu của các statement type FGA thông thường. Những sự kiện này nên được quản lý bằng Unified Auditing hoặc cơ chế audit phù hợp.

Nếu hệ thống dùng MERGE hoặc câu lệnh phức hợp, hãy kiểm tra hành vi cụ thể trên phiên bản Oracle đang chạy. Không nên tự suy luận rằng policy có INSERT và UPDATE chắc chắn ghi đúng mọi nhánh của MERGE mà chưa thử nghiệm.

### 7.1 Policy chỉ theo dõi SELECT

Một yêu cầu phổ biến là ghi nhận việc đọc dữ liệu nhạy cảm. Ví dụ:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema   => 'HR',
    object_name     => 'EMPLOYEES',
    policy_name     => 'AUDIT_SENSITIVE_READ',
    audit_condition => 'DEPARTMENT_ID = 90',
    audit_column    => 'SALARY',
    statement_types => 'SELECT'
  );
END;
/
~~~

Policy này tập trung vào việc đọc cột SALARY của các dòng thuộc department 90.

### 7.2 Policy theo dõi thay đổi dữ liệu

Nếu yêu cầu là kiểm toán thay đổi salary, có thể cấu hình UPDATE:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema   => 'HR',
    object_name     => 'EMPLOYEES',
    policy_name     => 'AUDIT_SALARY_UPDATE',
    audit_condition => 'DEPARTMENT_ID = 90',
    audit_column    => 'SALARY',
    statement_types => 'UPDATE'
  );
END;
/
~~~

Policy FGA ghi nhận sự kiện truy cập/thao tác thỏa điều kiện, nhưng không nên xem nó là cơ chế lưu đầy đủ giá trị trước và sau của mọi cột đã thay đổi. Nếu cần lịch sử thay đổi chi tiết theo từng dòng, hãy đánh giá Flashback Data Archive, trigger audit được thiết kế cẩn thận, application event log hoặc giải pháp CDC phù hợp.

## 8. Tạo policy FGA hoàn chỉnh

Giả sử yêu cầu:

- Theo dõi bảng HR.EMPLOYEES.
- Chỉ quan tâm các truy vấn SELECT.
- Chỉ ghi nhận khi câu lệnh tham chiếu SALARY.
- Chỉ ghi nhận khi có dòng thỏa SALARY >= 15000.
- Không ghi bind values trừ khi có nhu cầu và kiểm soát riêng.

Có thể tạo policy:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema       => 'HR',
    object_name         => 'EMPLOYEES',
    policy_name         => 'AUDIT_HIGH_SALARY_READ',
    audit_condition     => 'SALARY >= 15000',
    audit_column        => 'SALARY',
    statement_types     => 'SELECT',
    audit_column_opts   => DBMS_FGA.ANY_COLUMNS,
    enable              => TRUE
  );
END;
/
~~~

Sau khi tạo, kiểm tra policy trong data dictionary:

~~~sql
SELECT object_schema,
       object_name,
       policy_name,
       policy_text,
       policy_column,
       policy_column_options,
       enabled,
       sel,
       ins,
       upd,
       del
FROM dba_audit_policies
WHERE object_schema = 'HR'
  AND object_name = 'EMPLOYEES';
~~~

Tên cột và khả năng hiển thị của dictionary view có thể khác theo release và quyền truy cập. Nếu không có quyền DBA, dùng view phù hợp như ALL_AUDIT_POLICIES nếu phiên bản hỗ trợ hoặc nhờ audit administrator kiểm tra.

### 8.1 Kiểm thử policy bằng các truy vấn khác nhau

Giả sử dữ liệu có một số nhân viên thuộc department 90 và có mức salary khác nhau.

Truy vấn tham chiếu SALARY và có thể đọc các dòng nhạy cảm:

~~~sql
SELECT employee_id, salary
FROM hr.employees
WHERE department_id = 90;
~~~

Truy vấn tham chiếu SALARY trong predicate:

~~~sql
SELECT employee_id
FROM hr.employees
WHERE salary >= 15000;
~~~

Truy vấn không tham chiếu SALARY:

~~~sql
SELECT employee_id, first_name
FROM hr.employees
WHERE department_id = 90;
~~~

Khi kiểm thử, không chỉ chạy một câu SQL. Cần kiểm tra các tình huống:

- Câu lệnh tham chiếu cột được audit.
- Câu lệnh không tham chiếu cột được audit.
- Dữ liệu có dòng thỏa điều kiện.
- Dữ liệu không có dòng thỏa điều kiện.
- Điều kiện trả về UNKNOWN do NULL.
- Các statement type khác SELECT nếu policy hỗ trợ.
- Câu lệnh truy cập qua view hoặc application layer nếu hệ thống sử dụng.

FGA đánh giá policy theo dữ liệu được truy cập và điều kiện cấu hình. Hãy xác minh audit event thực tế trong audit trail thay vì chỉ dựa vào việc câu SQL chạy thành công.

## 9. Quản lý vòng đời policy

Sau khi tạo policy, có thể bật, tắt hoặc xóa bằng DBMS_FGA.

### 9.1 Tắt policy tạm thời

~~~sql
BEGIN
  DBMS_FGA.DISABLE_POLICY(
    object_schema => 'HR',
    object_name   => 'EMPLOYEES',
    policy_name   => 'AUDIT_HIGH_SALARY_READ'
  );
END;
/
~~~

Policy vẫn tồn tại nhưng không được áp dụng trong thời gian bị disable.

### 9.2 Bật lại policy

~~~sql
BEGIN
  DBMS_FGA.ENABLE_POLICY(
    object_schema => 'HR',
    object_name   => 'EMPLOYEES',
    policy_name   => 'AUDIT_HIGH_SALARY_READ',
    enable        => TRUE
  );
END;
/
~~~

### 9.3 Xóa policy

~~~sql
BEGIN
  DBMS_FGA.DROP_POLICY(
    object_schema => 'HR',
    object_name   => 'EMPLOYEES',
    policy_name   => 'AUDIT_HIGH_SALARY_READ'
  );
END;
/
~~~

Xóa policy dừng việc tạo audit event theo policy đó trong tương lai. Việc xóa policy không phải thao tác xóa các audit record đã được tạo trước đó.

### 9.4 Thay đổi định nghĩa policy

Khi yêu cầu thay đổi, có thể drop rồi add lại policy hoặc dùng API phù hợp của release để sửa thuộc tính. Hãy lưu định nghĩa policy hiện tại trước khi thay đổi, ghi nhận người thực hiện, thời điểm và lý do.

Không nên chỉnh policy trực tiếp bằng UPDATE vào bảng hệ thống hoặc bảng audit nội bộ. Luôn dùng API được Oracle hỗ trợ.

## 10. Handler module: phản ứng khi phát sinh audit event

FGA cho phép chỉ định handler_schema và handler_module. Handler là thủ tục PL/SQL tùy chọn được gọi khi có audit event phù hợp.

Ví dụ tham số:

~~~sql
handler_schema => 'SEC_ADMIN',
handler_module => 'FGA_EVENT_HANDLER'
~~~

Thủ tục handler có thể được định nghĩa trong schema quản trị:

~~~sql
CREATE OR REPLACE PROCEDURE sec_admin.fga_event_handler AS
BEGIN
  -- Thực hiện xử lý phụ trợ tối thiểu theo thiết kế đã kiểm thử.
  NULL;
END;
/
~~~

Tên thủ tục trong handler_module phải khớp với thủ tục thực tế và cần quyền thực thi phù hợp. Cách phân giải tên, quyền và hành vi lỗi cần được xác minh trên release cụ thể.

Handler có thể dùng để kích hoạt quy trình cảnh báo hoặc ghi nhận phụ trợ. Tuy nhiên:

- Audit trail của Oracle vẫn là nguồn bằng chứng kiểm toán chính.
- Handler không nên thay thế audit trail bằng một bảng log tự tạo.
- Tránh gọi dịch vụ mạng đồng bộ hoặc thực hiện công việc nặng trong handler.
- Tránh làm phát sinh truy vấn đệ quy vào chính object đang được audit.
- Thiết kế handler sao cho lỗi phụ trợ không làm sai lệch luồng nghiệp vụ.
- Kiểm thử overhead, quyền thực thi, exception và transaction behavior.

Nếu mục tiêu chỉ là lưu bằng chứng truy cập, thường không cần handler. Chỉ thêm handler khi có nhu cầu phản ứng rõ ràng và đã đánh giá ảnh hưởng đến SQL đang chạy.

## 11. Xem audit record được tạo bởi FGA

Vị trí đọc audit record phụ thuộc chế độ auditing của Oracle Database.

### 11.1 Traditional audit trail

Trong cấu hình traditional auditing, có thể kiểm tra view DBA_FGA_AUDIT_TRAIL:

~~~sql
SELECT timestamp,
       db_user,
       os_user,
       userhost,
       client_id,
       object_schema,
       object_name,
       policy_name,
       statement_type,
       sql_text,
       sql_bind
FROM dba_fga_audit_trail
WHERE object_schema = 'HR'
  AND object_name = 'EMPLOYEES'
ORDER BY timestamp DESC;
~~~

View USER_FGA_AUDIT_TRAIL có thể dùng để xem các bản ghi thuộc phạm vi người dùng hiện tại theo quyền và phiên bản. DBA_COMMON_AUDIT_TRAIL có thể hợp nhất một số loại audit trail truyền thống.

### 11.2 Unified Auditing

Khi Unified Auditing được bật, audit records được xem trong UNIFIED_AUDIT_TRAIL. Có thể truy vấn các trường chung như:

~~~sql
SELECT event_timestamp,
       dbusername,
       os_username,
       userhost,
       client_identifier,
       action_name,
       object_schema,
       object_name,
       sql_text,
       sql_binds,
       unified_audit_policies
FROM unified_audit_trail
WHERE object_schema = 'HR'
  AND object_name = 'EMPLOYEES'
ORDER BY event_timestamp DESC;
~~~

Các cột có sẵn và cách liên kết policy FGA với unified audit record phụ thuộc release và cấu hình. Có thể dùng điều kiện bổ sung trên tên policy hoặc thông tin audit phù hợp trong view để thu hẹp kết quả.

Nếu truy vấn không thấy record, không nên kết luận ngay rằng FGA không hoạt động. Hãy xác định database đang dùng traditional hay unified auditing, policy có enabled không, session có truy cập đúng object không, statement có tham chiếu audit column không và dữ liệu có thỏa audit_condition không.

### 11.3 Kiểm tra định danh người dùng và ứng dụng

Một audit record có thể cung cấp thông tin về database user, OS user, host, client identifier, object, policy, statement type, SQL text và bind data tùy chế độ/configuration.

Các trường này giúp trả lời:

- Ai đã thực hiện thao tác?
- Kết nối đến từ host hoặc client nào?
- Object nào bị truy cập?
- Policy nào đã kích hoạt?
- Câu lệnh thuộc loại nào?
- SQL text/bind có được lưu theo cấu hình không?

Audit record không nhất thiết chứng minh danh tính con người nếu tài khoản database được chia sẻ. Muốn truy vết đến người dùng cuối, ứng dụng cần thiết lập client identifier và module/action một cách đáng tin cậy, đồng thời bảo vệ việc giả mạo context.

## 12. Điều kiện áp dụng FGA trong thiết kế bảo mật

Không phải mọi bảng đều cần FGA. Nên áp dụng khi có yêu cầu kiểm toán dữ liệu cụ thể, có thể mô tả bằng object, statement, column và condition.

Các trường hợp phù hợp:

- Dữ liệu cá nhân hoặc tài chính có quy định truy cập.
- Cột lương, số tài khoản, thông tin định danh hoặc hồ sơ nhạy cảm.
- Truy vấn dữ liệu ngoài phạm vi nghiệp vụ thông thường.
- Theo dõi truy cập các dòng thuộc nhóm đặc biệt.
- Cần audit SELECT có điều kiện mà object auditing thông thường quá rộng.
- Cần ghi nhận một số thao tác DML trên cột hoặc dữ liệu nhạy cảm.

Các trường hợp cần cân nhắc cơ chế khác:

- Muốn ngăn user đọc một số dòng: dùng VPD hoặc quyền/view phù hợp.
- Muốn che giá trị trả về: dùng Data Redaction hoặc tầng trình bày có kiểm soát.
- Muốn lưu đầy đủ old/new values cho từng dòng: đánh giá Flashback Data Archive, CDC hoặc audit trigger phù hợp.
- Muốn kiểm toán đăng nhập, cấp quyền, DDL, role use hoặc hành động quản trị: dùng Unified Auditing.
- Muốn giám sát mọi câu SQL trong workload: dùng công cụ performance monitoring hoặc trace có phạm vi phù hợp.

### 12.1 Có yêu cầu chính sách rõ ràng

Trước khi tạo FGA policy, cần trả lời:

1. Dữ liệu hoặc object nào được xem là nhạy cảm?
2. Hành động nào cần ghi nhận?
3. Ai hoặc nhóm nào cần được theo dõi?
4. Cột nào phải được tham chiếu?
5. Điều kiện dòng nào kích hoạt audit?
6. Có cần phân biệt service/module/action hoặc client identifier không?
7. Audit trail cần lưu bao lâu?
8. Ai được phép đọc, xuất và xóa audit record?
9. Có cần cảnh báo gần thời gian thực không?
10. Cách kiểm thử để chứng minh policy không bỏ sót và không tạo quá nhiều record?

Không nên bắt đầu bằng việc tạo policy cho tất cả bảng rồi mới tìm lý do. Hãy chuyển yêu cầu bảo mật thành điều kiện có thể kiểm chứng.

### 12.2 Chọn phạm vi object

FGA policy gắn với object cụ thể. Nếu dữ liệu được truy cập qua nhiều view, synonym, package hoặc schema, cần kiểm tra đường truy cập thực tế.

Một ứng dụng có thể truy cập bảng trực tiếp, qua view hoặc qua PL/SQL definer-rights package. Hãy kiểm thử đúng đường đi mà ứng dụng sử dụng. Không giả định policy trên một object sẽ tự động thay thế policy trên mọi object khác có dữ liệu tương tự.

### 12.3 Điều kiện phải có tính ổn định và dễ giải thích

Một policy tốt có thể giải thích được vì sao một truy cập được ghi nhận. Điều kiện nên ngắn, rõ và gắn với quy tắc nghiệp vụ ổn định.

Nếu điều kiện dựa trên application context, hãy xác định ai có quyền đặt context và thời điểm context được reset. Nếu context có thể bị người dùng giả mạo, audit trail có thể phân loại sai hoạt động.

Nếu điều kiện dựa trên giá trị dữ liệu, cần kiểm tra NULL, kiểu dữ liệu, collation, timezone và các trường hợp biên.

## 13. FGA có phải audit từng dòng không?

FGA thường được hiểu nhầm là một cơ chế ghi một record cho từng row được đọc. Mục tiêu chính của nó là ghi nhận câu lệnh truy cập thỏa policy, dựa trên điều kiện dữ liệu và cột được cấu hình.

Nếu một SELECT trả về hàng nghìn dòng phù hợp với audit_condition, không nên mặc định audit trail sẽ chứa một bản ghi riêng cho từng dòng với toàn bộ giá trị của từng dòng. Audit event cho biết statement/policy/object và thông tin liên quan, không phải bản sao của result set.

Nếu yêu cầu pháp lý cần biết chính xác dòng nào đã được đọc hoặc giá trị nào đã được trả về, cần thiết kế thêm cơ chế có thể chứng minh được mức chi tiết đó. Cần đánh giá cả hiệu năng, tính toàn vẹn, khả năng bị bypass và chi phí lưu trữ.

## 14. FGA và VPD có thể phối hợp

FGA và VPD có thể cùng áp dụng trên một object vì chúng giải quyết hai mục tiêu khác nhau.

Ví dụ:

- VPD giới hạn nhân viên phòng ban 10 chỉ nhìn thấy dữ liệu phòng ban 10.
- FGA ghi nhận khi một tài khoản có quyền đặc biệt truy cập cột SALARY của nhân viên thuộc phòng ban 90.

VPD thay đổi predicate được áp dụng để giới hạn dòng mà người dùng nhìn thấy. FGA tạo audit event khi truy cập thỏa policy. Hai cơ chế cần được thiết kế và kiểm thử cùng nhau để xác nhận policy FGA đánh giá dữ liệu theo đúng ngữ nghĩa truy cập trong môi trường có VPD.

Không dùng FGA thay cho VPD. Nếu người dùng không được phép nhìn thấy dòng, cần một cơ chế thực thi quyền đó.

## 15. Hiệu năng và vận hành audit trail

FGA thêm công việc vào quá trình thực thi SQL. Chi phí phụ thuộc số policy, độ phức tạp audit_condition, số cột kiểm toán, số lần truy cập, cách ghi audit trail và handler nếu có.

Các yếu tố cần đo:

- Số policy gắn với object.
- Độ phức tạp của audit_condition.
- Số dòng mà statement truy cập.
- Số lần statement được chạy.
- Audit trail destination và tải I/O.
- Handler có thực hiện công việc phụ trợ hay không.
- Mức concurrency và thời gian lưu trữ.

Một điều kiện đơn giản thường dễ kiểm soát hơn một biểu thức phức tạp. Tránh thêm policy trùng lặp với cùng mục tiêu vì có thể làm khó việc giải thích audit event và tăng chi phí.

### 15.1 Dung lượng và retention

Audit trail có thể tăng nhanh nếu policy quá rộng hoặc ứng dụng chạy nhiều truy vấn. Cần xác định:

- Retention theo yêu cầu pháp lý và chính sách tổ chức.
- Dung lượng dự kiến và cảnh báo khi gần ngưỡng.
- Quy trình archive/export.
- Quyền truy cập audit record.
- Quy trình purge sau khi hết thời hạn.
- Khả năng truy xuất lại khi có điều tra.

Dùng DBMS_AUDIT_MGMT và quy trình quản lý audit được Oracle hỗ trợ để quản lý vòng đời dữ liệu. Không xóa trực tiếp dữ liệu khỏi các bảng SYS nội bộ hoặc sửa audit trail bằng DML thông thường.

### 15.2 Bảo vệ audit trail

Audit trail là bằng chứng bảo mật nên cần kiểm soát nghiêm:

- Tách quyền tạo policy, đọc audit và quản trị database khi phù hợp.
- Hạn chế quyền truy cập DBA_FGA_AUDIT_TRAIL hoặc UNIFIED_AUDIT_TRAIL.
- Ghi nhận thao tác thay đổi policy.
- Bảo vệ file export và bản sao lưu.
- Hạn chế SQL_TEXT và SQL_BINDS khi chứa dữ liệu nhạy cảm.
- Theo dõi việc tắt policy hoặc thay đổi retention.
- Đảm bảo đồng bộ thời gian giữa database, ứng dụng và hệ thống giám sát.

Không nên cho chính tài khoản nghiệp vụ có quyền sửa hoặc xóa audit record mà nó có thể bị ghi nhận.

## 16. Quyền quản trị FGA

Việc tạo và quản lý policy cần quyền phù hợp. Tùy phiên bản và cấu hình, việc quản trị auditing có thể dựa trên quyền như AUDIT_ADMIN, quyền thực thi package DBMS_FGA và quyền trên object liên quan.

Người xem audit trail có thể cần quyền như AUDIT_VIEWER hoặc quyền đọc view tương ứng theo cấu hình. Không cấp DBA chỉ để một nhóm bảo mật đọc audit record.

Một mô hình trách nhiệm thường gồm:

- Chủ sở hữu dữ liệu xác định cột và điều kiện nghiệp vụ nhạy cảm.
- Security/audit administrator quản lý policy.
- DBA hỗ trợ cấu hình, dung lượng, ADR và vận hành.
- Auditor có quyền đọc audit trail theo phạm vi.
- Application team cung cấp module/action/client identifier và kịch bản kiểm thử.

Tên role, quyền package và quyền truy cập view phải được xác minh theo phiên bản Oracle đang chạy. Dùng nguyên tắc least privilege và thử trên môi trường kiểm thử trước khi áp dụng production.

## 17. Troubleshooting khi không thấy audit record

Nếu câu SQL chạy nhưng không có audit record, hãy kiểm tra theo thứ tự:

### Policy có tồn tại và đang enabled?

~~~sql
SELECT object_schema,
       object_name,
       policy_name,
       enabled,
       policy_text,
       policy_column,
       sel,
       ins,
       upd,
       del
FROM dba_audit_policies
WHERE object_schema = 'HR'
  AND object_name = 'EMPLOYEES';
~~~

Xác nhận đúng schema/object và policy không bị disable.

### Statement type có nằm trong policy?

Nếu policy chỉ có SELECT, một UPDATE sẽ không kích hoạt policy theo statement type đó.

### Câu SQL có tham chiếu audit column?

Kiểm tra toàn bộ biểu thức SQL, bao gồm SELECT list, WHERE, JOIN và ORDER BY. Xem lại ANY_COLUMNS hay ALL_COLUMNS.

### Có dòng nào thỏa audit_condition?

Nếu điều kiện là SALARY >= 15000 nhưng không có dòng phù hợp trong tập được truy cập, không nên mong đợi event theo điều kiện đó.

### Đang đọc đúng audit trail không?

Xác định Unified Auditing hay traditional audit trail. Đọc đúng view và kiểm tra quyền. Với unified mode, xem UNIFIED_AUDIT_TRAIL; với traditional FGA trail, xem DBA_FGA_AUDIT_TRAIL.

### Có đang truy vấn sai database, PDB hoặc instance?

Trong CDB/PDB và RAC, cần xác nhận kết nối đang ở đúng container và instance. Không tìm audit event ở một PDB khác với nơi statement được thực thi.

### Handler có lỗi không?

Nếu policy dùng handler, kiểm tra compile status, quyền execute và lỗi handler. Tuy nhiên, hãy phân biệt lỗi handler với việc policy có tạo audit event hay không; audit trail mới là nơi cần xác minh bản ghi.

## 18. Ví dụ chính sách theo nhiều điều kiện

Giả sử tổ chức muốn kiểm toán khi:

- Người dùng truy cập bảng HR.EMPLOYEES.
- Câu lệnh tham chiếu SALARY hoặc COMMISSION_PCT.
- Có ít nhất một dòng thuộc department 90.
- Chỉ quan tâm SELECT.

Policy:

~~~sql
BEGIN
  DBMS_FGA.ADD_POLICY(
    object_schema       => 'HR',
    object_name         => 'EMPLOYEES',
    policy_name         => 'AUDIT_EXEC_PAY_READ',
    audit_condition     => 'DEPARTMENT_ID = 90',
    audit_column        => 'SALARY, COMMISSION_PCT',
    statement_types     => 'SELECT',
    audit_column_opts   => DBMS_FGA.ANY_COLUMNS,
    enable              => TRUE
  );
END;
/
~~~

Bảng tình huống minh họa:

| SQL/request | Tham chiếu cột audit? | Dữ liệu phù hợp? | Kỳ vọng |
|---|---|---|---|
| SELECT SALARY, dòng department 90 | Có | Có | Audit event |
| SELECT COMMISSION_PCT, dòng department 90 | Có | Có | Audit event |
| SELECT SALARY, chỉ department 10 | Có | Không | Không có event theo điều kiện |
| SELECT FIRST_NAME, department 90 | Không | Có | Không thỏa điều kiện cột |
| SELECT SALARY, không có dòng phù hợp | Có | Không | Không có event theo điều kiện |

Bảng này mô tả logic policy ở mức khái niệm. Khi kiểm thử thực tế, hãy xác nhận cách Oracle xử lý tập dòng truy cập, view, predicate pushdown, bind values và phiên bản database.

Nếu thay ANY_COLUMNS bằng ALL_COLUMNS, các truy vấn chỉ tham chiếu một trong hai cột sẽ không đáp ứng điều kiện cột; policy yêu cầu cả SALARY và COMMISSION_PCT được tham chiếu.

## 19. Các giới hạn và điều cần xác minh theo phiên bản

FGA có lịch sử phát triển qua nhiều phiên bản Oracle. Một số ví dụ cũ có thể sử dụng tham số audit_trail hoặc giả định về nơi lưu audit record không còn phù hợp với cấu hình Unified Auditing hiện tại.

Trước khi triển khai, cần xác minh:

- Release và Release Update của Oracle Database.
- Database đang dùng Unified Auditing hay traditional auditing.
- Cú pháp DBMS_FGA.ADD_POLICY và các statement type được hỗ trợ.
- Cách policy áp dụng với view, synonym, VPD và PL/SQL access path.
- Quyền cần thiết để tạo, bật/tắt và đọc policy.
- Audit trail view thực tế và các cột có sẵn.
- Hành vi của handler và lỗi handler.
- Cách quản lý retention và purge.
- Tác động hiệu năng trên workload đại diện.

Không dựa vào một đoạn SQL từ tài liệu của phiên bản khác mà không chạy kiểm thử. Đặc biệt, không giả định audit trail, bind capture và hành vi câu lệnh phức hợp giống nhau giữa mọi cấu hình.

## 20. Quy trình triển khai FGA trong môi trường thật

Một quy trình triển khai có kiểm soát có thể gồm:

1. **Xác định dữ liệu nhạy cảm:** làm rõ object, cột, dòng và nghiệp vụ cần kiểm toán.
2. **Viết điều kiện policy:** xác định statement type, audit_column và audit_condition.
3. **Xác định nguồn audit trail:** traditional hay unified; quyền đọc và retention.
4. **Đánh giá hiệu năng:** ước lượng tần suất truy cập, số policy và độ phức tạp điều kiện.
5. **Tạo policy ở môi trường thử:** dùng DBMS_FGA.ADD_POLICY.
6. **Kiểm thử dương tính:** câu lệnh đúng phạm vi phải tạo audit event.
7. **Kiểm thử âm tính:** câu lệnh ngoài phạm vi không tạo event ngoài ý muốn.
8. **Kiểm thử các đường truy cập:** table, view, application package, connection pool và các session context.
9. **Kiểm tra audit trail:** xác nhận user, object, policy, statement và timestamp.
10. **Triển khai production:** ghi nhận người thay đổi, thời điểm, policy definition và kế hoạch rollback.
11. **Theo dõi:** kiểm tra số lượng record, dung lượng, overhead và các cảnh báo.
12. **Rà soát định kỳ:** loại bỏ policy không còn cần, điều chỉnh điều kiện và kiểm tra quyền.

Một policy chỉ nên được xem là triển khai thành công khi đã chứng minh cả trường hợp cần audit được ghi nhận và trường hợp không thuộc phạm vi không tạo sự kiện ngoài ý muốn.

## 21. Những hiểu lầm thường gặp

| Nhận định | Cách hiểu chính xác |
|---|---|
| FGA chặn người dùng đọc dòng nhạy cảm | FGA ghi nhận; VPD/privilege mới thực thi giới hạn truy cập |
| FGA ghi một bản ghi cho mỗi row được đọc | Audit event không phải bản sao từng dòng kết quả |
| audit_condition giống WHERE của ứng dụng | Đây là điều kiện policy độc lập với predicate của câu SQL |
| audit_column chỉ xét cột trong SELECT list | Cần xét các cột được câu lệnh tham chiếu trong toàn bộ biểu thức |
| NULL audit_condition nghĩa là không audit | NULL nghĩa là không giới hạn theo điều kiện dữ liệu |
| ALL_COLUMNS dễ thay thế ANY_COLUMNS | ALL yêu cầu tất cả cột trong danh sách được tham chiếu |
| FGA thay thế Unified Auditing | FGA là policy chi tiết; Unified Auditing là kiến trúc audit trail/policy rộng hơn |
| FGA lưu đầy đủ giá trị trước và sau UPDATE | Không nên xem FGA là cơ chế lưu row image; dùng giải pháp phù hợp nếu cần lịch sử giá trị |
| Tạo policy xong là đủ | Cần kiểm tra enabled state, audit trail, retention và workload |
| Không thấy record nghĩa là policy không chạy | Có thể sai object, statement type, column, condition, container hoặc audit trail view |

## 22. Checklist thiết kế và vận hành

Trước khi tạo policy:

- [ ] Đã xác định object và schema chính xác.
- [ ] Đã xác định loại câu lệnh cần audit.
- [ ] Đã xác định cột nhạy cảm và cách kết hợp ANY/ALL.
- [ ] Đã định nghĩa audit_condition rõ ràng, có xử lý NULL.
- [ ] Đã xác định context/session attributes có thể tin cậy.
- [ ] Đã chọn audit trail theo chế độ auditing.
- [ ] Đã xác định retention, quyền đọc và quyền quản trị.
- [ ] Đã đánh giá handler có thật sự cần thiết hay không.

Khi kiểm thử:

- [ ] Policy được tạo và enabled.
- [ ] Truy vấn trong phạm vi tạo audit event.
- [ ] Truy vấn ngoài phạm vi không tạo event ngoài ý muốn.
- [ ] Kiểm thử cả trường hợp dữ liệu phù hợp và không phù hợp.
- [ ] Kiểm thử ANY_COLUMNS và ALL_COLUMNS theo SQL thực tế.
- [ ] Kiểm thử SELECT và các DML statement type được cấu hình.
- [ ] Kiểm tra view, VPD, PL/SQL và connection pool nếu có.
- [ ] Đọc đúng audit trail và xác nhận các trường định danh.

Sau khi triển khai:

- [ ] Theo dõi dung lượng và tốc độ tăng audit trail.
- [ ] Theo dõi overhead trên workload.
- [ ] Hạn chế quyền đọc và sửa đổi policy.
- [ ] Kiểm tra handler và lỗi phụ trợ nếu có.
- [ ] Dùng API được hỗ trợ để quản lý retention/purge.
- [ ] Rà soát policy định kỳ và lưu lại thay đổi.

## 23. Kết luận

Fine-Grained Auditing cho phép Oracle ghi nhận các thao tác truy cập dữ liệu thỏa điều kiện cụ thể. DBMS_FGA.ADD_POLICY xác định object, statement type, audit columns, audit condition và handler tùy chọn. ANY_COLUMNS và ALL_COLUMNS kiểm soát cách các cột trong danh sách được kết hợp; audit_condition xác định dữ liệu thuộc diện cần ghi nhận.

FGA phù hợp khi tổ chức cần bằng chứng truy cập có chọn lọc đối với dữ liệu nhạy cảm. Nó không chặn truy cập, không che dữ liệu và không thay thế cơ chế lưu lịch sử từng dòng. Thiết kế tốt cần policy rõ ràng, kiểm thử cả trường hợp dương tính và âm tính, đọc đúng audit trail, kiểm soát quyền, retention và overhead.
