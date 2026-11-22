# GRANT, REVOKE, WITH ADMIN OPTION và WITH GRANT OPTION trong Oracle

## 1. Quản lý quyền truy cập trong Oracle Database

Oracle Database dùng cơ chế privilege và role để kiểm soát ai được kết nối, tạo đối tượng, đọc dữ liệu, thay đổi dữ liệu hoặc thực thi chương trình trong database.

Ba khái niệm cần phân biệt:

- **System privilege:** quyền thực hiện một loại thao tác trong database, ví dụ CREATE SESSION, CREATE TABLE hoặc CREATE PROCEDURE.
- **Object privilege:** quyền thực hiện một thao tác trên một đối tượng cụ thể, ví dụ SELECT trên HR.EMPLOYEES hoặc EXECUTE trên một package.
- **Role:** một nhóm quyền và role khác được gom lại để cấp cho user hoặc role khác.

Hai tùy chọn ủy quyền có tên gần giống nhau nhưng áp dụng cho hai loại quyền khác nhau:

- **WITH ADMIN OPTION:** dùng khi cấp system privilege hoặc role. Grantee được phép quản trị và cấp tiếp privilege/role đó cho user hoặc role khác.
- **WITH GRANT OPTION:** dùng khi cấp object privilege. Grantee được phép cấp tiếp object privilege đó cho user hoặc role khác.

Không được xem hai option này là một. Chọn nhầm option có thể tạo ra quyền quản trị rộng hơn ý định ban đầu hoặc khiến câu GRANT không hợp lệ.

~~~text
                    ORACLE DATABASE
                           |
              +------------+------------+
              |            |            |
              v            v            v
        SYSTEM PRIVILEGE  OBJECT PRIVILEGE   ROLE
              |            |                 |
              |            |                 |
       WITH ADMIN OPTION   WITH GRANT OPTION  WITH ADMIN OPTION
              |            |                 |
              v            v                 v
       Cấp/quản trị tiếp  Cấp tiếp quyền    Cấp/quản trị
       system privilege  trên object       role cho user/role
       hoặc role
~~~

> Bài học dùng Oracle Database 19c. Quyền thực tế còn phụ thuộc schema owner, quyền được cấp trực tiếp hay qua role, trạng thái role trong session, quyền quản trị và cấu hình multitenant. Ví dụ cần chạy trong schema lab có quyền phù hợp.

## 2. System privilege, object privilege và role

### 2.1. System privilege

System privilege cho phép user thực hiện một hành động hoặc một nhóm hành động ở phạm vi database/schema.

Ví dụ:

| System privilege | Ý nghĩa khái quát |
| --- | --- |
| CREATE SESSION | Kết nối database |
| CREATE TABLE | Tạo table trong schema của user |
| CREATE VIEW | Tạo view trong schema của user |
| CREATE PROCEDURE | Tạo procedure, function và package trong schema của user |
| CREATE SEQUENCE | Tạo sequence trong schema của user |
| CREATE ANY TABLE | Tạo table trong schema khác theo phạm vi privilege |
| SELECT ANY TABLE | Query phần lớn table/view trong các schema theo quy tắc Oracle |
| GRANT ANY PRIVILEGE | Cấp hoặc thu hồi system privilege thay mặt cơ chế quản trị |
| GRANT ANY ROLE | Cấp hoặc thu hồi role theo phạm vi privilege |
| GRANT ANY OBJECT PRIVILEGE | Cấp hoặc thu hồi object privilege theo phạm vi privilege |

System privilege có thể có phạm vi rất rộng. Đặc biệt, các privilege chứa ANY như SELECT ANY TABLE, UPDATE ANY TABLE hoặc CREATE ANY PROCEDURE cần được cấp rất thận trọng. Chúng không tương đương với quyền trên một table cụ thể.

Một số system privilege ANY không áp dụng cho object trong SYS hoặc các dictionary object được bảo vệ bằng privilege riêng. Không nên suy ra rằng ANY đồng nghĩa với mọi object không có ngoại lệ.

### 2.2. Object privilege

Object privilege cho phép thực hiện thao tác trên một object cụ thể.

Ví dụ:

~~~sql
GRANT SELECT ON hr.employees TO analyst;
GRANT INSERT, UPDATE ON hr.orders TO order_app;
GRANT EXECUTE ON hr.order_api TO order_app;
~~~

Một số object privilege thường gặp:

| Object privilege | Đối tượng/thao tác |
| --- | --- |
| SELECT | Đọc dữ liệu từ table, view hoặc materialized view |
| READ | Đọc dữ liệu nhưng không bao gồm một số khả năng khóa row như SELECT FOR UPDATE |
| INSERT | Thêm row |
| UPDATE | Sửa row; có thể giới hạn theo column |
| DELETE | Xóa row |
| REFERENCES | Tham chiếu cột bằng foreign key |
| EXECUTE | Thực thi procedure, function hoặc package |
| ALTER | Thay đổi cấu trúc object trong phạm vi được hỗ trợ |
| INDEX | Tạo index trên table của schema khác |

Danh sách privilege hợp lệ phụ thuộc loại object. Không phải object nào cũng có đầy đủ SELECT, INSERT, UPDATE hoặc DELETE.

### 2.3. Role

Role là một nhóm privilege và có thể chứa role khác. Thay vì cấp nhiều object privilege riêng lẻ cho từng user, DBA có thể cấp privilege vào role rồi cấp role cho user.

Ví dụ:

~~~sql
CREATE ROLE reporting_role;

GRANT CREATE SESSION TO reporting_role;
GRANT SELECT ON hr.employees TO reporting_role;
GRANT SELECT ON hr.departments TO reporting_role;

GRANT reporting_role TO analyst;
~~~

Khi role được enable trong session, user có thể sử dụng các quyền nằm trong role. Role giúp quản lý quyền theo chức năng, ví dụ REPORTING_ROLE, ORDER_READ_ROLE hoặc ORDER_WRITE_ROLE.

Role cũng có thể được cấp cho role khác. Oracle không cho phép cấp role cho chính nó hoặc tạo chuỗi role grant vòng tròn.

### 2.4. Quyền trực tiếp và quyền qua role

Privilege có thể được cấp trực tiếp cho user hoặc thông qua role:

~~~sql
-- Direct object privilege
GRANT SELECT ON hr.employees TO analyst;

-- Object privilege cấp cho role
GRANT SELECT ON hr.employees TO reporting_role;
GRANT reporting_role TO analyst;
~~~

Hai cách có thể cho phép query cùng một object trong session, nhưng chúng không hoàn toàn tương đương ở mọi ngữ cảnh. Một số thao tác compile stored PL/SQL definer-rights yêu cầu privilege được cấp trực tiếp cho owner, không chỉ thông qua role.

## 3. Câu lệnh GRANT

GRANT được dùng để:

1. Cấp system privilege cho user hoặc role.
2. Cấp role cho user, role hoặc program unit theo cú pháp Oracle hỗ trợ.
3. Cấp object privilege trên một object cụ thể cho user hoặc role.

### 3.1. Cấp system privilege

Cú pháp cơ bản:

~~~sql
GRANT system_privilege [, system_privilege ...]
TO user_or_role [, user_or_role ...];
~~~

Ví dụ:

~~~sql
GRANT CREATE SESSION TO app_user;
GRANT CREATE TABLE, CREATE SEQUENCE TO app_owner;
GRANT CREATE VIEW TO reporting_owner;
~~~

User nhận system privilege có thể thực hiện hành động tương ứng ngay khi privilege có hiệu lực.

### 3.2. Cấp object privilege

Cú pháp cơ bản:

~~~sql
GRANT object_privilege [, object_privilege ...]
ON schema.object
TO user_or_role [, user_or_role ...];
~~~

Ví dụ:

~~~sql
GRANT SELECT ON hr.employees TO analyst;
GRANT SELECT, INSERT ON hr.orders TO order_app;
GRANT EXECUTE ON hr.order_api TO order_app;
~~~

Object privilege luôn gắn với object cụ thể. SELECT trên HR.EMPLOYEES không tự động cho phép SELECT trên HR.DEPARTMENTS.

### 3.3. Cấp quyền theo column

Oracle cho phép giới hạn một số object privilege theo column, đặc biệt UPDATE, INSERT và REFERENCES:

~~~sql
GRANT UPDATE (salary)
ON hr.employees
TO payroll_operator;
~~~

Payroll operator chỉ được UPDATE cột SALARY theo grant này. Quyền không tự mở rộng sang các cột khác.

Ví dụ cấp INSERT theo một nhóm cột:

~~~sql
GRANT INSERT (employee_id, first_name, last_name)
ON hr.employees
TO hr_importer;
~~~

Việc giới hạn column giúp giảm phạm vi dữ liệu có thể thay đổi.

### 3.4. Cấp READ hoặc SELECT

Oracle 19c có cả READ và SELECT object privilege cho table/view:

~~~sql
GRANT READ ON hr.employees TO report_viewer;
GRANT SELECT ON hr.employees TO report_operator;
~~~

Cả hai cho phép query dữ liệu bằng SELECT. SELECT còn cho phép các thao tác như SELECT ... FOR UPDATE hoặc LOCK TABLE trong phạm vi được hỗ trợ; READ không cấp các khả năng khóa đó.

Nếu user chỉ cần đọc dữ liệu, READ có thể là lựa chọn hẹp hơn. Hãy kiểm tra ứng dụng có sử dụng SELECT FOR UPDATE hay không trước khi thay SELECT bằng READ.

### 3.5. Cấp quyền trên view

Ví dụ:

~~~sql
GRANT SELECT ON hr.employee_directory_v TO reporting_role;
~~~

Nếu view tham chiếu object ở schema khác, owner của view cần có quyền thích hợp trên các object nền. Để cấp SELECT trên view cho user khác, Oracle yêu cầu view owner sở hữu các object nền hoặc có SELECT WITH GRANT OPTION trên tất cả object nền liên quan. Việc người nhận đã có quyền trực tiếp trên các bảng nền không thay thế điều kiện grant của view owner.

Đây là nguyên nhân phổ biến của lỗi ORA-01720 khi cấp quyền trên view.

### 3.6. Cấp role

Cú pháp:

~~~sql
GRANT role_name TO user_or_role;
~~~

Ví dụ:

~~~sql
CREATE ROLE app_read_role;
GRANT SELECT ON hr.products TO app_read_role;
GRANT SELECT ON hr.categories TO app_read_role;

GRANT app_read_role TO app_user;
~~~

User có role có thể enable role và sử dụng privilege chứa trong role.

### 3.7. Ai được phép GRANT?

Điều kiện phụ thuộc loại quyền:

| Loại quyền được cấp | Ai có thể cấp? |
| --- | --- |
| System privilege | User có system privilege đó WITH ADMIN OPTION hoặc có GRANT ANY PRIVILEGE |
| Role | Role creator, user được cấp role trực tiếp WITH ADMIN OPTION, hoặc user có GRANT ANY ROLE |
| Object privilege | Object owner, user nhận object privilege WITH GRANT OPTION, hoặc user có GRANT ANY OBJECT PRIVILEGE theo giới hạn Oracle |

GRANT ANY PRIVILEGE, GRANT ANY ROLE và GRANT ANY OBJECT PRIVILEGE là các system privilege có sức mạnh quản trị cao. Không cấp chúng chỉ để tiện vận hành.

## 4. WITH ADMIN OPTION

### 4.1. Ý nghĩa

WITH ADMIN OPTION áp dụng cho system privilege và role. Nó trao cho grantee quyền quản trị privilege/role đó, bao gồm khả năng cấp hoặc thu hồi privilege/role cho user hoặc role khác.

Ví dụ cấp system privilege:

~~~sql
GRANT CREATE TABLE
TO schema_manager
WITH ADMIN OPTION;
~~~

Schema manager có CREATE TABLE và có thể cấp CREATE TABLE cho user hoặc role khác.

Ví dụ cấp role:

~~~sql
GRANT reporting_role
TO reporting_manager
WITH ADMIN OPTION;
~~~

Reporting manager có thể cấp hoặc thu hồi REPORTING_ROLE cho user/role khác theo quyền được ủy quyền.

### 4.2. ADMIN OPTION không phải object privilege

Không dùng WITH ADMIN OPTION cho SELECT ON table:

~~~sql
-- Không hợp lệ: SELECT ON table là object privilege
GRANT SELECT ON hr.employees
TO analyst
WITH ADMIN OPTION;
~~~

Đối với object privilege, option đúng là WITH GRANT OPTION.

### 4.3. WITH ADMIN OPTION cho system privilege

~~~sql
GRANT CREATE SESSION
TO user_admin
WITH ADMIN OPTION;
~~~

User admin có thể cấp CREATE SESSION cho user/role khác và thu hồi privilege đó từ các grantee khác.

Điều này không đồng nghĩa user admin có quyền cấp mọi system privilege. ADMIN OPTION gắn với privilege cụ thể. Muốn cấp system privilege khác, user phải có ADMIN OPTION trên privilege đó hoặc GRANT ANY PRIVILEGE.

### 4.4. WITH ADMIN OPTION cho role

~~~sql
GRANT app_read_role
TO team_lead
WITH ADMIN OPTION;
~~~

Team lead có thể cấp role cho user hoặc role khác và thu hồi role đó theo quyền quản trị. Đây là cách phân quyền quản trị role theo từng nhóm thay vì cấp GRANT ANY ROLE cho nhiều người.

### 4.5. ADMIN OPTION cho phép quản trị rộng hơn việc cấp tiếp

Oracle mô tả ADMIN OPTION cho system privilege/role cho phép grantee:

- Grant privilege hoặc role cho user/role khác, trừ giới hạn đối với global role.
- Revoke privilege hoặc role từ user/role khác.
- Alter hoặc drop privilege/role trong phạm vi Oracle cho phép.
- Với role, grant/revoke role cho program unit trong schema của grantee theo quy tắc hỗ trợ.

Vì vậy, ADMIN OPTION là quyền ủy quyền quản trị, không chỉ là một cờ thông báo.

### 4.6. System privilege được cấp cho role và ADMIN OPTION

Oracle 19c có một chi tiết cần lưu ý khi cấp system privilege cho role:

- Nếu grantor có system privilege với ADMIN OPTION, user được cấp role chứa privilege đó có thể có privilege ngay cả khi role chưa được enable.
- Nếu grantor cấp system privilege nhờ GRANT ANY PRIVILEGE, user cần enable role để sử dụng privilege qua role.

Đây là khác biệt trong privilege domain và cách Oracle xử lý nguồn cấp. Khi thiết kế quyền qua role, cần kiểm tra cách privilege được cấp vào role và trạng thái role của session.

### 4.7. Không thể chỉ thu hồi ADMIN OPTION

Oracle không hỗ trợ một thao tác riêng để giữ privilege/role nhưng chỉ bỏ ADMIN OPTION. Cần thu hồi toàn bộ privilege/role khỏi user, sau đó cấp lại mà không có ADMIN OPTION:

~~~sql
REVOKE CREATE TABLE FROM schema_manager;

GRANT CREATE TABLE TO schema_manager;
~~~

Sau bước này, schema_manager vẫn có CREATE TABLE nhưng không còn ADMIN OPTION từ grant vừa thực hiện.

Với role:

~~~sql
REVOKE reporting_role FROM reporting_manager;
GRANT reporting_role TO reporting_manager;
~~~

Hãy kiểm tra các quyền độc lập khác mà user có thể nhận được qua role khác hoặc direct grant. REVOKE một grant không tự loại bỏ mọi đường cấp quyền khác.

## 5. WITH GRANT OPTION

### 5.1. Ý nghĩa

WITH GRANT OPTION áp dụng cho object privilege. Nó cho phép người nhận cấp tiếp object privilege đó cho user hoặc role khác.

Ví dụ:

~~~sql
GRANT SELECT ON hr.employees
TO data_steward
WITH GRANT OPTION;
~~~

Data steward có SELECT trên HR.EMPLOYEES và có thể cấp tiếp SELECT trên object đó.

### 5.2. Phạm vi ủy quyền gắn với object cụ thể

Nếu data steward được cấp SELECT WITH GRANT OPTION trên HR.EMPLOYEES, điều đó không cho phép họ cấp SELECT trên HR.DEPARTMENTS hoặc UPDATE trên HR.EMPLOYEES.

Muốn cấp tiếp quyền khác, họ phải có đúng privilege và grant option tương ứng, hoặc có system privilege quản trị rộng hơn.

### 5.3. Grantee tiếp tục cấp cho user hoặc role

Ví dụ chuỗi cấp:

~~~sql
-- HR là owner
GRANT SELECT ON hr.employees
TO data_steward
WITH GRANT OPTION;

-- Data steward cấp tiếp
GRANT SELECT ON hr.employees
TO report_reader;

-- Data steward cũng có thể cấp cho role
GRANT SELECT ON hr.employees
TO report_role;
~~~

REPORT_READER và REPORT_ROLE nhận SELECT. Họ không tự có GRANT OPTION trừ khi grant tương ứng có WITH GRANT OPTION và đáp ứng giới hạn Oracle.

### 5.4. WITH GRANT OPTION không dùng để cấp system privilege

Không viết:

~~~sql
-- Không hợp lệ cho system privilege
GRANT CREATE TABLE TO schema_manager
WITH GRANT OPTION;
~~~

System privilege dùng WITH ADMIN OPTION.

### 5.5. Không cấp WITH GRANT OPTION cho role

Oracle 19c không cho chỉ định WITH GRANT OPTION khi object privilege được cấp cho role:

~~~sql
-- Không hợp lệ: grantee là role
GRANT SELECT ON hr.employees
TO reporting_role
WITH GRANT OPTION;
~~~

Nếu cần một cá nhân được phép cấp tiếp object privilege, cấp object privilege trực tiếp cho user đó với WITH GRANT OPTION. Có thể cấp privilege thông thường cho role để các thành viên khác sử dụng.

Oracle SQL Language Reference 19c nêu grantee của WITH GRANT OPTION có thể là user hoặc PUBLIC, không phải role. Cấp cho PUBLIC làm quyền lan tới mọi user, vì vậy không dùng cách này như một mẫu phân quyền ứng dụng thông thường.

### 5.6. Không thể chỉ thu hồi GRANT OPTION

Oracle không cho thu hồi riêng option mà giữ nguyên object privilege. Cần revoke privilege rồi grant lại không có WITH GRANT OPTION:

~~~sql
REVOKE SELECT ON hr.employees FROM data_steward;

GRANT SELECT ON hr.employees TO data_steward;
~~~

Lưu ý: việc revoke object privilege khỏi một grantor có thể làm các grant downstream dựa trên WITH GRANT OPTION bị thu hồi dây chuyền. Phải kiểm tra grant chain trước khi thực hiện.

## 6. So sánh WITH ADMIN OPTION và WITH GRANT OPTION

| Tiêu chí | WITH ADMIN OPTION | WITH GRANT OPTION |
| --- | --- | --- |
| Áp dụng cho | System privilege và role | Object privilege |
| Phạm vi | Một loại thao tác/role trong database | Một privilege trên object cụ thể |
| Cho phép cấp tiếp | System privilege hoặc role | Object privilege |
| Cho phép thu hồi tiếp | Có, với privilege/role được ủy quyền | Grantee có thể cấp tiếp; quyền revoke theo grantor/owner và quy tắc Oracle |
| Có thể cấp cho role? | Role có thể nhận system privilege/role với ADMIN OPTION theo cú pháp hỗ trợ | Không thể cấp object privilege WITH GRANT OPTION cho role |
| Thu hồi riêng option? | Không; revoke privilege/role rồi grant lại không option | Không; revoke object privilege rồi grant lại không option |
| Hệ quả revoke | Không có cascade grant chain giống object grant option; quyền phụ thuộc role/system privilege có thể ảnh hưởng object/code sử dụng nó | Revoke object privilege của grantor có thể cascade các grant được truyền qua GRANT OPTION |

Một cách ghi nhớ:

- ADMIN = quyền quản trị việc cấp/revoke system privilege hoặc role.
- GRANT = quyền cấp tiếp một object privilege cụ thể.

Không suy luận option dựa trên tên gần giống. Hãy xác định privilege thuộc loại nào trước.

## 7. REVOKE: thu hồi quyền

### 7.1. Thu hồi system privilege

Cú pháp:

~~~sql
REVOKE system_privilege
FROM user_or_role;
~~~

Ví dụ:

~~~sql
REVOKE CREATE TABLE FROM app_user;
REVOKE CREATE SESSION FROM temporary_user;
~~~

Để revoke system privilege, người thực hiện cần ADMIN OPTION trên privilege tương ứng hoặc GRANT ANY PRIVILEGE.

### 7.2. Thu hồi object privilege

Cú pháp:

~~~sql
REVOKE object_privilege
ON schema.object
FROM user_or_role;
~~~

Ví dụ:

~~~sql
REVOKE SELECT ON hr.employees FROM analyst;
REVOKE INSERT, UPDATE ON hr.orders FROM order_app;
REVOKE EXECUTE ON hr.order_api FROM old_app_role;
~~~

Thông thường object owner có thể revoke grant do mình cấp. Người có GRANT ANY OBJECT PRIVILEGE cũng có thể revoke theo phạm vi Oracle quy định.

### 7.3. Thu hồi role

~~~sql
REVOKE reporting_role FROM analyst;
~~~

User không còn nhận privilege thông qua role đó. Nếu user có cùng privilege qua direct grant hoặc role khác, quyền hiệu lực có thể vẫn còn.

Để revoke role, người thực hiện cần trực tiếp được cấp role với ADMIN OPTION hoặc đã tạo role, hoặc có GRANT ANY ROLE theo phạm vi hỗ trợ.

### 7.4. Thu hồi nhiều privilege

~~~sql
REVOKE SELECT, INSERT
ON hr.orders
FROM order_reader, order_importer;
~~~

Có thể dùng ALL để thu hồi các object privilege đã cấp trên object:

~~~sql
REVOKE ALL ON hr.orders FROM legacy_role;
~~~

ALL là cách viết gọn cho các privilege được cấp; không phải một privilege độc lập.

### 7.5. Thu hồi REFERENCES và CASCADE CONSTRAINTS

Nếu grantee đã dùng REFERENCES privilege để tạo foreign key constraint đang tồn tại, Oracle yêu cầu CASCADE CONSTRAINTS khi revoke:

~~~sql
REVOKE REFERENCES ON hr.departments
FROM app_schema
CASCADE CONSTRAINTS;
~~~

CASCADE CONSTRAINTS làm các foreign key constraint đang phụ thuộc vào REFERENCES grant bị xóa. Đây là thay đổi cấu trúc dữ liệu, không chỉ là thay đổi quyền. Cần đánh giá các constraint bị ảnh hưởng trước khi chạy.

## 8. Cascade khi thu hồi quyền

Đây là khác biệt quan trọng giữa object privilege grant option và system privilege/role admin option.

### 8.1. Object privilege có grant chain

Giả sử:

1. HR là owner của HR.EMPLOYEES.
2. HR cấp SELECT WITH GRANT OPTION cho DATA_STEWARD.
3. DATA_STEWARD cấp SELECT cho REPORT_READER.
4. REPORT_READER có thể sử dụng quyền theo grant đó.

~~~text
HR (object owner)
  |
  | SELECT WITH GRANT OPTION
  v
DATA_STEWARD
  |
  | SELECT
  v
REPORT_READER
~~~

Nếu HR revoke SELECT từ DATA_STEWARD:

~~~sql
REVOKE SELECT ON hr.employees
FROM data_steward;
~~~

Oracle cascade revoke SELECT trên HR.EMPLOYEES khỏi REPORT_READER nếu grant của REPORT_READER được truyền qua DATA_STEWARD. Các grant downstream phụ thuộc grant chain đó bị thu hồi.

### 8.2. Grant độc lập vẫn có thể tồn tại

Nếu HR cũng cấp SELECT trực tiếp cho REPORT_READER:

~~~sql
GRANT SELECT ON hr.employees TO report_reader;
~~~

Khi grant từ DATA_STEWARD bị cascade revoke, grant độc lập trực tiếp từ HR vẫn còn. Oracle lưu grant theo grantor/grantee và không nên giả định một đường thu hồi sẽ xóa mọi đường cấp quyền khác.

### 8.3. Revoke system privilege khác object grant cascade

Oracle không áp dụng cùng cơ chế cascade grant chain của WITH GRANT OPTION cho system privilege được cấp bằng ADMIN OPTION.

Ví dụ với system privilege DDL:

~~~sql
GRANT CREATE TABLE TO schema_manager WITH ADMIN OPTION;
GRANT CREATE TABLE TO app_owner;

REVOKE CREATE TABLE FROM schema_manager;
~~~

Việc thu hồi CREATE TABLE từ SCHEMA_MANAGER không tự động cascade revoke CREATE TABLE đã được SCHEMA_MANAGER cấp cho APP_OWNER. Các object đã được tạo cũng không tự động bị xóa.

Tuy vậy, revoke system privilege DML có thể làm stored procedure/function/package phụ thuộc privilege đó không còn thực thi thành công. Cần phân biệt việc thu hồi grant chain với tác động lên object/code đang sử dụng quyền.

### 8.4. Revoke role

Revoke role khỏi user làm user mất quyền nhận từ role đó. Nếu role chứa role khác hoặc nhiều object/system privilege, tất cả các quyền đến từ role không còn trong privilege domain của user khi role bị thu hồi/không được enable.

ADMIN OPTION của role không thể được thu hồi riêng. Muốn bỏ ADMIN OPTION, revoke role khỏi user rồi grant lại role không có option.

### 8.5. Thu hồi object privilege có thể ảnh hưởng stored object

Nếu procedure hoặc package definer-rights phụ thuộc object privilege bị thu hồi từ owner của stored object, procedure/package có thể không thực thi được. View phụ thuộc object cũng có thể bị invalidated.

Vì vậy, revoke không chỉ ảnh hưởng user đăng nhập trực tiếp. Nó có thể tác động đến ứng dụng và stored code.

## 9. Column privilege và giới hạn khi REVOKE

Oracle cho phép grant một số quyền theo column:

~~~sql
GRANT UPDATE (salary, commission_pct)
ON hr.employees
TO payroll_operator;
~~~

Nhưng không thể dùng REVOKE để chỉ thu hồi riêng một column privilege theo cách tương ứng. Ví dụ, không có cú pháp thông thường để chỉ revoke UPDATE trên SALARY và giữ UPDATE trên COMMISSION_PCT trong cùng grant.

Muốn thay đổi phạm vi column:

~~~sql
REVOKE UPDATE ON hr.employees
FROM payroll_operator;

GRANT UPDATE (commission_pct)
ON hr.employees
TO payroll_operator;
~~~

Thao tác đầu thu hồi UPDATE trên object khỏi grantee; thao tác sau cấp lại đúng column cần giữ.

## 10. Quyền trực tiếp, role và stored PL/SQL

### 10.1. Role tiện cho session nhưng không thay thế mọi direct grant

Một user có thể query table nhờ role được enable:

~~~sql
GRANT SELECT ON hr.employees TO reporting_role;
GRANT reporting_role TO analyst;
~~~

Trong session, ANALYST có thể enable REPORTING_ROLE để query.

### 10.2. Definer-rights PL/SQL

Stored procedure/function/package mặc định chạy theo definer-rights nếu không khai báo AUTHID CURRENT_USER. Khi compile và thực thi definer-rights program unit, các role thông thường của owner bị disable.

Nếu procedure trong schema APP_OWNER cần SELECT HR.EMPLOYEES, cấp trực tiếp:

~~~sql
GRANT SELECT ON hr.employees TO app_owner;
~~~

Không chỉ cấp SELECT cho một role rồi cấp role đó cho APP_OWNER nếu quyền được dùng để compile definer-rights stored code.

Tương tự, system privilege cần để tạo stored program unit phải được cấp trực tiếp cho owner theo quy tắc Oracle, không dựa vào role thông thường.

### 10.3. Invoker-rights và code-based access control

Program unit khai báo AUTHID CURRENT_USER chạy với quyền của invoker theo mô hình invoker-rights. Oracle còn hỗ trợ cấp role cho program unit (code-based access control), cho phép role được enable khi program unit chạy theo quy tắc tương ứng.

Ví dụ cú pháp cấp role cho procedure:

~~~sql
GRANT app_read_role
TO PROCEDURE app_owner.read_dashboard;
~~~

Đây là cơ chế riêng. Không nhầm việc cấp role cho program unit với việc cấp role cho user.

### 10.4. WITH DELEGATE OPTION là gì?

Oracle 19c còn có WITH DELEGATE OPTION khi cấp role trực tiếp cho user. Option này cho phép user grant/revoke role đó cho program unit trong schema của họ, không trao toàn bộ quyền grant/revoke role cho user hoặc role khác như ADMIN OPTION.

Ví dụ:

~~~sql
GRANT app_read_role
TO app_owner
WITH DELEGATE OPTION;
~~~

WITH DELEGATE OPTION không phải chủ đề chính của bài, nhưng cần phân biệt với ADMIN OPTION. Cả hai đều liên quan tới role, nhưng phạm vi ủy quyền khác nhau.

## 11. GRANT ANY PRIVILEGE, GRANT ANY ROLE và GRANT ANY OBJECT PRIVILEGE

Đây là các system privilege phục vụ quản trị grant/revoke:

| System privilege | Phạm vi |
| --- | --- |
| GRANT ANY PRIVILEGE | Cấp hoặc thu hồi system privilege theo phạm vi Oracle |
| GRANT ANY ROLE | Cấp hoặc thu hồi role theo phạm vi Oracle |
| GRANT ANY OBJECT PRIVILEGE | Cấp hoặc thu hồi object privilege theo phạm vi Oracle |

Chúng có phạm vi rất rộng và cần được bảo vệ.

### 11.1. GRANT ANY PRIVILEGE

User có GRANT ANY PRIVILEGE có thể cấp system privilege cho user/role mà không cần có ADMIN OPTION trên từng privilege riêng.

### 11.2. GRANT ANY ROLE

User có GRANT ANY ROLE có thể cấp hoặc revoke role cho user/role khác, ngoại trừ các giới hạn đối với global role.

### 11.3. GRANT ANY OBJECT PRIVILEGE

User có GRANT ANY OBJECT PRIVILEGE có thể cấp object privilege thay mặt object owner trong phạm vi owner có quyền cấp. Khi sử dụng quyền này, Oracle vẫn áp dụng các giới hạn về loại object privilege và object.

### 11.4. Không dùng ANY privilege thay cho thiết kế role

Ví dụ, nếu ứng dụng chỉ cần SELECT trên HR.EMPLOYEES, cấp:

~~~sql
GRANT SELECT ON hr.employees TO app_reader;
~~~

thay vì:

~~~sql
GRANT SELECT ANY TABLE TO app_reader;
~~~

Quyền ANY mở rộng phạm vi sang nhiều object ngoài yêu cầu ứng dụng. Least privilege giúp giảm tác động khi account hoặc ứng dụng bị lạm dụng.

## 12. Kiểm tra quyền bằng Data Dictionary

Oracle cung cấp các view USER_, ALL_, DBA_ và ROLE_ để kiểm tra grant.

### 12.1. DBA_SYS_PRIVS

Xem system privilege được cấp cho user/role:

~~~sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee IN ('APP_OWNER', 'SCHEMA_MANAGER')
ORDER BY grantee, privilege;
~~~

ADMIN_OPTION = YES cho biết grant có ADMIN OPTION.

### 12.2. DBA_TAB_PRIVS

Xem object privilege:

~~~sql
SELECT grantee,
       owner,
       table_name,
       grantor,
       privilege,
       grantable,
       hierarchy
FROM dba_tab_privs
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY grantee, privilege;
~~~

GRANTABLE = YES cho biết object privilege được cấp với GRANT OPTION. HIERARCHY cho biết trạng thái WITH HIERARCHY OPTION khi áp dụng.

### 12.3. DBA_ROLE_PRIVS

Xem role được cấp cho user/role:

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role,
       delegate_option
FROM dba_role_privs
WHERE grantee IN ('ANALYST', 'REPORTING_MANAGER')
ORDER BY grantee, granted_role;
~~~

ADMIN_OPTION = YES cho biết role grant có ADMIN OPTION. DEFAULT_ROLE cho biết role có được enable mặc định khi user đăng nhập theo cấu hình hay không.

### 12.4. DBA_COL_PRIVS

Xem grant theo column:

~~~sql
SELECT grantee,
       owner,
       table_name,
       column_name,
       privilege,
       grantor
FROM dba_col_privs
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY grantee, column_name;
~~~

### 12.5. ROLE_SYS_PRIVS và ROLE_TAB_PRIVS

Các view ROLE_SYS_PRIVS và ROLE_TAB_PRIVS giúp xem system/object privilege được cấp cho role. Có thể lần theo:

1. Role được cấp cho user nào.
2. Role chứa những role con nào.
3. Role chứa system privilege nào.
4. Role chứa object privilege nào.

Khi điều tra effective privilege, phải xem cả role hierarchy và role enabled trong session.

### 12.6. SESSION_PRIVS và SESSION_ROLES

~~~sql
SELECT *
FROM session_privs
ORDER BY privilege;

SELECT *
FROM session_roles
ORDER BY role;
~~~

SESSION_PRIVS cho biết system privilege đang có hiệu lực trong session. SESSION_ROLES cho biết role đang enable. Đây là cách hữu ích để phân biệt quyền được cấp nhưng chưa enable với quyền đang thực sự khả dụng.

### 12.7. USER_ và ALL_ views

Nếu không có quyền DBA dictionary:

- USER_SYS_PRIVS: system privilege liên quan tới user hiện tại.
- USER_TAB_PRIVS: object privilege trong phạm vi user hiện tại có thể xem theo view.
- USER_ROLE_PRIVS: role được cấp cho user hiện tại.
- USER_COL_PRIVS: column privilege liên quan.
- ALL_TAB_PRIVS và ALL_TAB_PRIVS_RECD: các object grant có thể xem theo phạm vi tương ứng.

Không giả định một view USER_ luôn hiển thị đầy đủ toàn bộ privilege gián tiếp từ mọi role lồng nhau.

## 13. Thiết kế phân quyền theo role

Một cách tổ chức phổ biến:

~~~text
                  USERS
                    |
        +-----------+-----------+
        |                       |
        v                       v
   APP_READ_ROLE           APP_WRITE_ROLE
        |                       |
        v                       v
  SELECT trên view       INSERT/UPDATE trên API
  EXECUTE read API       EXECUTE write API
~~~

### 13.1. Tạo role theo chức năng

~~~sql
CREATE ROLE app_read_role;
CREATE ROLE app_write_role;
CREATE ROLE app_support_role;
~~~

### 13.2. Cấp object privilege cho role

~~~sql
GRANT SELECT ON hr.employee_directory_v
TO app_read_role;

GRANT EXECUTE ON hr.employee_api
TO app_write_role;

GRANT SELECT ON hr.application_audit_v
TO app_support_role;
~~~

### 13.3. Cấp role cho user

~~~sql
GRANT app_read_role TO app_reader_01;
GRANT app_write_role TO app_writer_01;
GRANT app_support_role TO app_support_01;
~~~

### 13.4. Tách người quản trị role

Nếu một team lead cần quản lý thành viên của role:

~~~sql
GRANT app_read_role
TO app_role_manager
WITH ADMIN OPTION;
~~~

Chỉ cấp ADMIN OPTION cho role cụ thể mà người đó chịu trách nhiệm. Không cấp GRANT ANY ROLE nếu chỉ cần quản trị một role.

### 13.5. Không cấp quyền DBA cho ứng dụng

Ứng dụng runtime thường chỉ cần CREATE SESSION và object privilege/role phục vụ nghiệp vụ. Không cấp DBA, SELECT ANY TABLE, UPDATE ANY TABLE, GRANT ANY PRIVILEGE hoặc GRANT ANY OBJECT PRIVILEGE chỉ để xử lý lỗi quyền.

Nếu ứng dụng cần tạo object, tách schema owner/deployment khỏi application runtime account. Runtime account thường không cần quyền DDL.

## 14. Quy trình kiểm tra và rà soát quyền

Khi rà soát một user:

1. Xác định direct system privilege.
2. Xác định direct object privilege.
3. Xác định role được cấp và role có ADMIN OPTION hay không.
4. Lần theo role lồng nhau.
5. Kiểm tra role nào đang default/enabled.
6. Kiểm tra quyền đến từ PUBLIC.
7. Kiểm tra GRANTABLE và ADMIN_OPTION.
8. Kiểm tra stored procedure/package/view phụ thuộc grant.
9. Xác định quyền ANY và quyền quản trị grant/revoke.
10. Đối chiếu quyền với chức năng ứng dụng thực tế.

Không chỉ nhìn DBA_TAB_PRIVS rồi kết luận user có toàn bộ quyền hiệu lực. Quyền có thể đến từ role, PUBLIC, system privilege hoặc các cơ chế khác.

### 14.1. Tìm object privilege có grant option

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantor
FROM dba_tab_privs
WHERE grantable = 'YES'
ORDER BY owner, table_name, grantee;
~~~

### 14.2. Tìm system privilege có admin option

~~~sql
SELECT grantee,
       privilege
FROM dba_sys_privs
WHERE admin_option = 'YES'
ORDER BY grantee, privilege;
~~~

### 14.3. Tìm role có admin option

~~~sql
SELECT grantee,
       granted_role
FROM dba_role_privs
WHERE admin_option = 'YES'
ORDER BY grantee, granted_role;
~~~

### 14.4. Kiểm tra grant của PUBLIC

~~~sql
SELECT owner,
       table_name,
       privilege,
       grantor
FROM dba_tab_privs
WHERE grantee = 'PUBLIC'
ORDER BY owner, table_name, privilege;
~~~

Các grant cho PUBLIC có thể mở quyền tới toàn bộ user. Cần rà soát đặc biệt kỹ các quyền ghi, thực thi và quyền có thể ủy quyền.

## 15. Lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| ORA-01031: insufficient privileges | User thiếu privilege cần cho GRANT/REVOKE hoặc thao tác object | Xác định loại quyền và cấp đúng privilege cần thiết |
| ORA-01932: ADMIN option not granted for role | Người chạy GRANT/REVOKE role không có ADMIN OPTION | Kiểm tra DBA_ROLE_PRIVS hoặc nhờ role owner/DBA |
| ORA-01924: role does not exist or is not granted | Role không tồn tại hoặc quyền quản trị role không có | Kiểm tra tên role, schema và grant trực tiếp |
| ORA-01720: grant option does not exist | View owner thiếu grant option trên object nền khi cấp quyền trên view | Cấp grant option thích hợp cho view owner hoặc thiết kế lại quyền |
| ORA-01919: role does not exist | Tên role trong GRANT/REVOKE không tồn tại | Kiểm tra role đã được tạo và chính tả |
| ORA-01933: cannot create a stored object using privileges from a role | Stored object cần privilege được cấp qua role | Cấp privilege trực tiếp cho schema owner |
| User vẫn truy cập sau REVOKE | Có grant khác qua role, direct grant hoặc PUBLIC | Kiểm tra toàn bộ grant path và session roles |
| User mất quyền ngoài dự kiến sau REVOKE | Object grant downstream bị cascade hoặc role chứa quyền bị thu hồi | Kiểm tra grant chain và các object phụ thuộc |
| Không thể revoke riêng ADMIN OPTION | Oracle yêu cầu revoke toàn bộ privilege/role rồi grant lại | Revoke và cấp lại không option |
| Không thể revoke riêng GRANT OPTION | Oracle yêu cầu revoke object privilege rồi grant lại không option | Đánh giá cascade trước khi thực hiện |
| FK constraint bị xóa khi revoke REFERENCES | REVOKE dùng CASCADE CONSTRAINTS | Kiểm tra constraint phụ thuộc trước khi revoke |
| Procedure compile lỗi dù user query được table | User có quyền qua role, nhưng definer-rights code cần direct grant | Cấp object privilege trực tiếp cho procedure owner |

## 16. Anti-pattern và nguyên tắc bảo mật

### 16.1. Cấp ADMIN OPTION cho quá nhiều user

Mỗi user có ADMIN OPTION có thể mở rộng phạm vi cấp quyền. Chỉ cấp cho người thực sự chịu trách nhiệm quản trị privilege hoặc role đó.

### 16.2. Cấp GRANT OPTION cho account ứng dụng

Application runtime thường chỉ cần sử dụng object privilege. Không cấp quyền cấp tiếp trừ khi ứng dụng thực sự là một tầng quản trị quyền được thiết kế và kiểm soát.

### 16.3. Dùng ANY privilege thay cho object privilege cụ thể

Nếu chỉ cần một table, cấp quyền trên table. Không cấp SELECT ANY TABLE hoặc UPDATE ANY TABLE để tránh phải quản lý nhiều object grants.

### 16.4. Dùng DBA role cho ứng dụng

DBA role chứa phạm vi quản trị rất rộng. Ứng dụng nghiệp vụ không nên chạy bằng account có DBA chỉ để giải quyết lỗi thiếu quyền.

### 16.5. Cấp quyền cho PUBLIC

PUBLIC bao phủ tất cả user. Tránh grant dữ liệu nhạy cảm, DML hoặc EXECUTE nhạy cảm cho PUBLIC. Kiểm tra các grant PUBLIC hiện có trong hệ thống.

### 16.6. Không kiểm tra cascade trước khi revoke

Revoke object privilege có GRANT OPTION có thể làm mất quyền của nhiều user downstream và ảnh hưởng stored object. Trước khi revoke, truy vấn DBA_TAB_PRIVS để dựng grant chain, kiểm tra dependent views/procedures và chuẩn bị kế hoạch cấp lại nếu cần.

### 16.7. Không dùng role để thay direct grant cho definer-rights code

Stored PL/SQL definer-rights không dùng role thông thường của owner khi thực thi. Cấp trực tiếp privilege cần thiết cho owner của program unit.

### 16.8. Không dùng GRANT ALL một cách máy móc

ALL có ý nghĩa khác nhau tùy system privilege và object privilege. Hãy cấp danh sách quyền cần thiết, đặc biệt với account runtime và object chứa dữ liệu nhạy cảm.

## 17. Lab: GRANT, REVOKE và hai loại option

Lab dùng schema riêng. Các user GRANT_LAB_USER, GRANT_LAB_USER_2, GRANT_LAB_MANAGER và GRANT_LAB_STEWARD phải được DBA chuẩn bị trước và có quyền CREATE SESSION. Người chạy cần quyền tạo role, table và cấp object privilege phù hợp. Thay tên schema nếu môi trường khác. Chỉ chạy trong database thử nghiệm.

### 17.1. Tạo bảng thử

Trong schema owner:

~~~sql
CREATE TABLE grant_lab_employees (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(100) NOT NULL,
    salary NUMBER(10,2)
);

INSERT INTO grant_lab_employees
VALUES (1, 'Nguyen An', 1500);

INSERT INTO grant_lab_employees
VALUES (2, 'Tran Binh', 2000);

COMMIT;
~~~

### 17.2. Tạo role và cấp object privilege

~~~sql
CREATE ROLE grant_lab_reader;
CREATE ROLE grant_lab_reader_2;

GRANT SELECT ON grant_lab_employees
TO grant_lab_reader;
~~~

Sau đó DBA hoặc schema owner cấp role cho user thử:

~~~sql
GRANT grant_lab_reader TO grant_lab_user;
~~~

Đăng nhập bằng GRANT_LAB_USER, kiểm tra role:

~~~sql
SELECT *
FROM session_roles;
~~~

Query object bằng tên schema:

~~~sql
SELECT *
FROM grant_lab_owner.grant_lab_employees;
~~~

### 17.3. Thử WITH ADMIN OPTION trên role

Trong schema owner:

~~~sql
GRANT grant_lab_reader
TO grant_lab_manager
WITH ADMIN OPTION;
~~~

Đăng nhập bằng GRANT_LAB_MANAGER và cấp role cho user khác:

~~~sql
GRANT grant_lab_reader TO grant_lab_user_2;
~~~

Kiểm tra:

~~~sql
SELECT username,
       granted_role,
       admin_option
FROM user_role_privs
ORDER BY username, granted_role;
~~~

### 17.4. Thử WITH GRANT OPTION trên object privilege

Trong schema owner:

~~~sql
GRANT SELECT ON grant_lab_employees
TO grant_lab_steward
WITH GRANT OPTION;
~~~

Đăng nhập bằng GRANT_LAB_STEWARD:

~~~sql
GRANT SELECT ON grant_lab_owner.grant_lab_employees
TO grant_lab_reader_2;
~~~

Kiểm tra trong schema owner hoặc user có quyền dictionary:

~~~sql
SELECT grantee,
       grantor,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'GRANT_LAB_OWNER'
  AND table_name = 'GRANT_LAB_EMPLOYEES'
ORDER BY grantee;
~~~

GRANTABLE = YES trên grant của GRANT_LAB_STEWARD cho biết steward có GRANT OPTION.

### 17.5. Thử cascade revoke

Trong schema owner:

~~~sql
REVOKE SELECT ON grant_lab_employees
FROM grant_lab_steward;
~~~

Kiểm tra lại DBA_TAB_PRIVS. Grant downstream của GRANT_LAB_STEWARD cho GRANT_LAB_READER_2 sẽ bị cascade revoke nếu không có một grant độc lập khác.

### 17.6. Thu hồi ADMIN OPTION bằng revoke và grant lại

Trong schema owner:

~~~sql
REVOKE grant_lab_reader
FROM grant_lab_manager;

GRANT grant_lab_reader
TO grant_lab_manager;
~~~

Kiểm tra ADMIN_OPTION trong DBA_ROLE_PRIVS hoặc USER_ROLE_PRIVS. Role vẫn được cấp nhưng grant mới không có ADMIN OPTION.

### 17.7. Dọn lab

Sau khi kiểm tra xong, thu hồi các grant còn lại và xóa object do lab tạo:

~~~sql
REVOKE grant_lab_reader FROM grant_lab_user;
REVOKE grant_lab_reader FROM grant_lab_user_2;
REVOKE grant_lab_reader FROM grant_lab_manager;

DROP ROLE grant_lab_reader;
DROP ROLE grant_lab_reader_2;
DROP TABLE grant_lab_employees PURGE;
~~~

Nếu role vẫn đang được cấp cho user/role khác, cần revoke các grant liên quan trước khi drop. Không chạy lệnh cleanup trên role hoặc table dùng chung của ứng dụng.

## 18. Checklist trước khi GRANT hoặc REVOKE

1. **Loại quyền là gì?** System privilege, object privilege hay role?
2. **Grantee là ai?** User, role hay PUBLIC?
3. **Phạm vi quyền có đúng không?** Một object hay toàn database?
4. **Có cần option không?** ADMIN OPTION cho system/role; GRANT OPTION cho object.
5. **Ai được phép cấp?** Owner, grantor có option hay user có GRANT ANY privilege tương ứng?
6. **Có thể cấp qua role không?** Cấp role để quản lý nhóm quyền nếu không cần delegation cá nhân.
7. **Có cần direct grant cho PL/SQL owner không?** Đặc biệt với definer-rights stored code.
8. **Có grant chain không?** Xem DBA_TAB_PRIVS và GRANTABLE trước khi revoke.
9. **Có downstream user hoặc stored object phụ thuộc không?** Đánh giá tác động.
10. **Có REFERENCES constraint không?** Kiểm tra trước khi dùng CASCADE CONSTRAINTS.
11. **Có quyền ANY hoặc GRANT ANY không?** Xác nhận đây là nhu cầu quản trị thật.
12. **Có quyền PUBLIC không?** Tránh mở rộng quyền cho mọi user.
13. **Có cần audit không?** Theo dõi thay đổi quyền theo chính sách bảo mật.
14. **Đã kiểm tra effective privilege chưa?** Xem direct grants, roles enabled, nested roles và PUBLIC.
15. **Đã xác nhận sau thay đổi chưa?** Query lại dictionary và thử bằng account thực tế.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** System privilege khác object privilege như thế nào?

**Câu 2.** Role dùng để giải quyết vấn đề gì?

**Câu 3.** WITH ADMIN OPTION áp dụng cho loại quyền nào?

**Câu 4.** WITH GRANT OPTION áp dụng cho loại quyền nào?

**Câu 5.** Vì sao không thể dùng WITH ADMIN OPTION cho SELECT ON table?

**Câu 6.** User có CREATE TABLE WITH ADMIN OPTION có thể cấp privilege nào?

**Câu 7.** User có SELECT ON HR.EMPLOYEES WITH GRANT OPTION có thể cấp tiếp quyền nào?

**Câu 8.** Có thể cấp object privilege WITH GRANT OPTION cho role không?

**Câu 9.** Oracle 19c SQL Reference cho phép grantee của WITH GRANT OPTION là những loại nào?

**Câu 10.** Vì sao revoke SELECT khỏi một user có GRANT OPTION có thể ảnh hưởng user khác?

**Câu 11.** ADMIN OPTION có thể bị revoke riêng mà giữ role/system privilege không?

**Câu 12.** GRANT OPTION có thể bị revoke riêng mà giữ object privilege không?

**Câu 13.** GRANT ANY ROLE khác ADMIN OPTION của một role cụ thể thế nào?

**Câu 14.** Vì sao object privilege cấp qua role có thể không đủ cho definer-rights PL/SQL?

**Câu 15.** DBA_SYS_PRIVS dùng để kiểm tra điều gì?

**Câu 16.** DBA_TAB_PRIVS có cột nào cho biết grant có GRANT OPTION?

**Câu 17.** DBA_ROLE_PRIVS có cột nào cho biết role grant có ADMIN OPTION?

**Câu 18.** Khi nào cần CASCADE CONSTRAINTS khi revoke REFERENCES?

**Câu 19.** Vì sao không nên cấp SELECT ANY TABLE nếu ứng dụng chỉ cần đọc một table?

**Câu 20.** Vì sao cần kiểm tra direct grant, role và PUBLIC khi điều tra user vẫn truy cập được object sau REVOKE?

<details>
<summary>Gợi ý đáp án</summary>

1. System privilege cho phép thực hiện loại thao tác ở phạm vi database/schema; object privilege cho phép thao tác trên object cụ thể.
2. Gom privilege thành nhóm để cấp và quản lý theo chức năng.
3. System privilege và role.
4. Object privilege.
5. SELECT ON table là object privilege; option phù hợp là WITH GRANT OPTION.
6. CREATE TABLE đó cho user hoặc role khác, theo phạm vi được ủy quyền.
7. SELECT trên HR.EMPLOYEES cho user hoặc role khác.
8. Không. Oracle không cho WITH GRANT OPTION khi grantee là role.
9. User hoặc PUBLIC; không phải role.
10. Các object privilege grants được truyền tiếp qua grant option có thể bị cascade revoke.
11. Không. Phải revoke privilege/role rồi grant lại không có ADMIN OPTION.
12. Không. Phải revoke object privilege rồi grant lại không có GRANT OPTION.
13. ADMIN OPTION gắn với privilege/role cụ thể; GRANT ANY ROLE là system privilege quản trị phạm vi rộng hơn.
14. Role thông thường bị disable trong compile/execute definer-rights context; owner cần direct grant.
15. System privilege được cấp cho user/role và ADMIN_OPTION.
16. GRANTABLE.
17. ADMIN_OPTION.
18. Khi grantee đã dùng REFERENCES privilege để tạo foreign key constraint đang tồn tại.
19. SELECT ANY TABLE mở quyền đọc nhiều object ngoài yêu cầu.
20. Vì quyền có thể còn hiệu lực qua một đường cấp độc lập khác.

</details>

## 20. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — GRANT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GRANT.html): cú pháp GRANT, WITH ADMIN OPTION, WITH GRANT OPTION, grantee restrictions và prerequisites.
2. [Oracle Database 19c SQL Language Reference — REVOKE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REVOKE.html): cú pháp REVOKE, quyền cần có và CASCADE CONSTRAINTS.
3. [Oracle Database 19c Security Guide — Managing System Privileges](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-system-privileges.html): system privilege, ANY privilege và quản lý grant/revoke.
4. [Oracle Database 19c Security Guide — Managing Object Privileges](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-object-privileges.html): object privilege, grant option và READ/SELECT.
5. [Oracle Database 19c Security Guide — Granting and Revoking Roles](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/granting-and-revoking-roles1.html): role hierarchy, ADMIN OPTION và role cho program unit.
6. [Oracle Database 19c Security Guide — Revokes of Privileges and Roles from a User](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/revokes-privileges-and-roles-user.html): revoke requirements, cascading effects và REFERENCES constraints.
7. [Oracle Database 19c Reference — DBA_SYS_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SYS_PRIVS.html): system privilege grants.
8. [Oracle Database 19c Reference — DBA_TAB_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TAB_PRIVS.html): object privilege grants.
9. [Oracle Database 19c Reference — DBA_ROLE_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_ROLE_PRIVS.html): role grants và option.

**Nguyên tắc cần nhớ:** GRANT cấp quyền, REVOKE thu hồi quyền. System privilege và role dùng WITH ADMIN OPTION; object privilege dùng WITH GRANT OPTION. ADMIN OPTION trao quyền quản trị privilege/role; GRANT OPTION trao quyền cấp tiếp một object privilege cụ thể. Oracle không cho thu hồi riêng option mà vẫn giữ privilege. Đặc biệt, revoke object privilege từ grantor có GRANT OPTION có thể cascade tới các grantee phía sau. Hãy thiết kế role theo chức năng, cấp quyền tối thiểu, tránh ANY privilege và PUBLIC, đồng thời kiểm tra direct grant, role hierarchy và grant chain trước khi thay đổi quyền.
