# System privilege, object privilege, role và quyền cấp lại

## 1. Mô hình quyền trong Oracle Database

Oracle Database sử dụng privilege để kiểm soát người dùng được phép thực hiện thao tác nào và trên phạm vi đối tượng nào. Một user có thể nhận quyền trực tiếp, nhận quyền thông qua role hoặc nhận quyền công khai qua `PUBLIC`.

Có hai nhóm privilege cơ bản:

- **System privilege** cho phép thực hiện một hành động ở cấp database hoặc trên một phạm vi đối tượng rộng, ví dụ kết nối database, tạo bảng trong schema của mình hoặc tạo user.
- **Object privilege** cho phép thực hiện một hành động cụ thể trên một đối tượng cụ thể, ví dụ đọc bảng `HR.EMPLOYEES`, cập nhật một số cột hoặc thực thi package.

**Role** là một tập hợp privilege và/hoặc role khác được đặt tên để quản lý, cấp và thu hồi quyền theo nhóm. Role không phải một loại privilege thứ ba; nó là cơ chế gom và phân phối privilege.

Oracle còn có hai khái niệm liên quan đến quyền cấp lại:

- `WITH ADMIN OPTION`: áp dụng khi cấp system privilege hoặc role, cho phép grantee cấp tiếp system privilege/role tương ứng cho grantee khác.
- `WITH GRANT OPTION`: áp dụng khi cấp object privilege cho một user, cho phép user đó cấp tiếp object privilege tương ứng trên cùng đối tượng.

Hiểu đúng các phạm vi này giúp tránh cấp quyền quá rộng, tránh phụ thuộc vào role khi chạy PL/SQL và biết trước tác động khi thu hồi quyền.

## 2. System privilege

### 2.1. Phạm vi của system privilege

System privilege cho phép user thực hiện một loại hành động trong database. Một số quyền chỉ cho phép thao tác trong schema của chính user; một số quyền có từ khóa `ANY` cho phép thao tác trên đối tượng thuộc nhiều schema khác.

Ví dụ:

| System privilege | Khả năng chính |
|---|---|
| `CREATE SESSION` | Đăng nhập database |
| `CREATE TABLE` | Tạo bảng trong schema của chính user |
| `CREATE VIEW` | Tạo view trong schema của chính user |
| `CREATE PROCEDURE` | Tạo procedure, function, package trong schema của chính user |
| `CREATE SEQUENCE` | Tạo sequence trong schema của chính user |
| `CREATE USER` | Tạo database user |
| `ALTER USER` | Thay đổi thuộc tính user theo phạm vi quyền được cấp |
| `CREATE ANY TABLE` | Tạo bảng trong schema của user khác |
| `ALTER ANY TABLE` | Thay đổi bảng thuộc schema khác |
| `DROP ANY TABLE` | Xóa bảng thuộc schema khác |
| `SELECT ANY TABLE` | Truy vấn bảng/view thuộc schema khác, theo phạm vi quyền của privilege |
| `GRANT ANY OBJECT PRIVILEGE` | Cấp object privilege trên đối tượng không thuộc schema của mình theo phạm vi quyền được cấp |
| `SELECT ANY DICTIONARY` | Đọc nhiều đối tượng data dictionary thuộc phạm vi privilege |

Các quyền `ANY` có phạm vi rộng và có thể vượt qua ranh giới sở hữu schema. Chỉ cấp khi có nhu cầu quản trị rõ ràng; không dùng chúng để thay thế các object privilege giới hạn trên một vài bảng.

### 2.2. CREATE TABLE và CREATE ANY TABLE

Hai quyền có tên gần giống nhưng phạm vi khác nhau:

```sql
GRANT CREATE TABLE TO app_user;
```

Cho phép `APP_USER` tạo bảng trong schema của chính mình. User còn cần quota trên tablespace hoặc quyền `UNLIMITED TABLESPACE` phù hợp để cấp phát segment.

```sql
GRANT CREATE ANY TABLE TO deployment_user;
```

Cho phép `DEPLOYMENT_USER` tạo bảng trong schema khác. Đây là quyền quản trị rộng hơn, không nên cấp cho tài khoản ứng dụng thông thường.

Tương tự, `CREATE VIEW` chỉ cho phép tạo view trong schema của mình; `CREATE ANY VIEW` mở rộng phạm vi sang schema khác. Khi thiết kế quyền, hãy phân biệt hành động trong schema sở hữu với hành động trên toàn database.

### 2.3. Cấp system privilege

Cú pháp cơ bản:

```sql
GRANT CREATE SESSION TO app_user;
GRANT CREATE TABLE, CREATE VIEW TO app_developer;
GRANT SELECT ANY TABLE TO reporting_admin;
```

Người cấp phải có quyền quản trị phù hợp, chẳng hạn đã được cấp system privilege tương ứng với `ADMIN OPTION` hoặc có quyền `GRANT ANY PRIVILEGE`. Các quyền quản trị này có phạm vi lớn; việc cấp chúng phải được kiểm soát riêng.

### 2.4. System privilege không tự động cấp quyền trên mọi loại thao tác

Một số tên quyền dễ bị hiểu rộng hơn phạm vi thực tế:

- `CREATE TABLE` không cho phép user tạo bảng trong schema người khác.
- `CREATE SESSION` chỉ cho phép mở session, không tự cấp quyền đọc bảng nghiệp vụ.
- `SELECT ANY TABLE` không đồng nghĩa user có quyền sửa hoặc xóa dữ liệu.
- `UNLIMITED TABLESPACE` liên quan quota tablespace, không phải object privilege trên bảng.
- `GRANT ANY OBJECT PRIVILEGE` là quyền cấp quyền trên đối tượng, không phải quyền sử dụng mọi đối tượng thay mặt chủ sở hữu trong mọi tình huống.

Không nên suy ra quyền từ tên gần giống. Hãy tra cứu privilege cụ thể trong tài liệu Oracle đúng phiên bản và kiểm tra view quyền hiện tại.

## 3. Object privilege

### 3.1. Phạm vi của object privilege

Object privilege cấp quyền thực hiện một hành động trên một đối tượng xác định. Đối tượng có thể là table, view, materialized view, sequence, procedure, function, package, directory và các loại object được Oracle hỗ trợ.

Ví dụ:

```sql
GRANT SELECT ON hr.employees TO reporting_user;
GRANT INSERT, UPDATE ON sales.orders TO order_app;
GRANT EXECUTE ON hr.payroll_api TO payroll_app;
GRANT SELECT ON sales.order_seq TO order_app;
```

Các quyền trên chỉ áp dụng cho đúng đối tượng được chỉ định. `SELECT ON HR.EMPLOYEES` không tự cấp quyền đọc các bảng khác trong schema `HR`.

### 3.2. Một số object privilege thường gặp

| Privilege | Đối tượng thường áp dụng | Khả năng |
|---|---|---|
| `SELECT` | Table, view, sequence và một số object phù hợp | Đọc dữ liệu/giá trị theo loại đối tượng |
| `READ` | Table, view, external table trong các phiên bản hỗ trợ | Đọc dữ liệu nhưng không cho phép `SELECT ... FOR UPDATE` |
| `INSERT` | Table, view | Thêm dòng |
| `UPDATE` | Table, view | Cập nhật dòng/cột được phép |
| `DELETE` | Table, view | Xóa dòng |
| `ALTER` | Table, sequence và một số object phù hợp | Thay đổi thuộc tính/định nghĩa theo loại object |
| `INDEX` | Table | Tạo index trên bảng |
| `REFERENCES` | Table | Tạo foreign key tham chiếu bảng/cột được cấp quyền |
| `EXECUTE` | Procedure, function, package, type | Gọi chương trình hoặc sử dụng type theo quyền được cấp |
| `READ`, `WRITE` | Directory | Đọc/ghi file trong directory object theo khả năng được cấp |

Tập privilege cụ thể phụ thuộc loại đối tượng và phiên bản Oracle. Ví dụ, không phải mọi object đều có `INSERT`, `UPDATE` hoặc `DELETE`.

### 3.3. Cấp object privilege

```sql
GRANT SELECT ON hr.employees TO analyst_user;

GRANT SELECT, INSERT, UPDATE, DELETE
ON sales.orders
TO order_app;

GRANT EXECUTE ON hr.employee_api TO hr_app;
```

Chủ sở hữu đối tượng có thể cấp object privilege trên đối tượng của mình. Người khác có thể cấp nếu họ nhận privilege đó với `GRANT OPTION` hoặc có system privilege quản trị phù hợp, chẳng hạn `GRANT ANY OBJECT PRIVILEGE` trong phạm vi Oracle cho phép.

### 3.4. Giới hạn quyền UPDATE theo cột

Oracle cho phép giới hạn `UPDATE` vào một số cột:

```sql
GRANT UPDATE (email, phone_number)
ON hr.employees
TO hr_support;
```

User `HR_SUPPORT` có thể cập nhật hai cột được chỉ định, nhưng không nhờ grant này mà cập nhật được `SALARY` hoặc các cột khác. Đây là cách cấp quyền theo nhu cầu nghiệp vụ hẹp hơn so với `UPDATE` toàn bảng.

Tương tự, `INSERT` có thể được giới hạn theo danh sách cột:

```sql
GRANT INSERT (customer_id, order_date, status)
ON sales.orders
TO order_app;
```

Khi cấp quyền theo cột, hãy kiểm tra câu SQL thực tế của ứng dụng có chỉ định các cột phù hợp hay không.

### 3.5. READ và SELECT

`READ` được bổ sung để cho phép đọc dữ liệu mà không cấp khả năng khóa dòng thông qua `SELECT ... FOR UPDATE`. Nếu ứng dụng chỉ cần truy vấn dữ liệu và không cần khóa dòng, `READ` có thể là quyền hẹp hơn `SELECT` trong các phiên bản hỗ trợ.

Ví dụ:

```sql
GRANT READ ON hr.employees TO report_reader;
```

Nếu ứng dụng cần `SELECT ... FOR UPDATE`, cần privilege phù hợp là `SELECT` cùng các điều kiện khác của câu lệnh. Hãy kiểm tra phiên bản database và tài liệu privilege trước khi dùng `READ`.

## 4. Role: gom privilege thành nhóm

### 4.1. Vì sao cần role?

Nếu quản trị viên cấp từng object privilege trực tiếp cho hàng trăm user, việc onboarding, thay đổi chức năng và thu hồi quyền sẽ phức tạp. Role cho phép mô hình hóa quyền theo trách nhiệm:

```text
report_reader_role
  ├── CREATE SESSION
  ├── SELECT ON HR.EMPLOYEES
  └── SELECT ON SALES.ORDERS

report_writer_role
  ├── CREATE SESSION
  ├── SELECT ON SALES.ORDERS
  └── INSERT, UPDATE ON SALES.ORDERS

Users
  ├── analyst_01  -> report_reader_role
  ├── analyst_02  -> report_reader_role
  └── order_app   -> report_writer_role
```

Khi một user đổi công việc, DBA có thể thay đổi role được cấp thay vì sửa từng privilege trực tiếp. Role cũng giúp tách quyền của ứng dụng, người dùng nghiệp vụ và quản trị viên.

### 4.2. Tạo role và cấp privilege cho role

```sql
CREATE ROLE report_reader_role;

GRANT CREATE SESSION TO report_reader_role;
GRANT SELECT ON hr.employees TO report_reader_role;
GRANT SELECT ON sales.orders TO report_reader_role;
```

Sau đó cấp role cho user:

```sql
GRANT report_reader_role TO analyst_01;
GRANT report_reader_role TO analyst_02;
```

Các user nhận được privilege trong role khi role đang được enable trong session. Một user có thể nhận nhiều role.

### 4.3. Role có thể chứa role khác

Oracle cho phép grant một role cho role khác, tạo cấu trúc role lồng nhau:

```sql
CREATE ROLE order_read_role;
CREATE ROLE order_write_role;
CREATE ROLE order_app_role;

GRANT SELECT ON sales.orders TO order_read_role;
GRANT INSERT, UPDATE ON sales.orders TO order_write_role;

GRANT order_read_role TO order_app_role;
GRANT order_write_role TO order_app_role;

GRANT order_app_role TO order_app;
```

`ORDER_APP` nhận tập quyền từ `ORDER_APP_ROLE` và các role lồng bên trong. Role lồng nhau giúp tái sử dụng nhóm quyền nhưng cũng khiến việc truy vết phức tạp hơn. Nên giữ cây role đơn giản, có tên phản ánh chức năng và tránh tạo chuỗi phụ thuộc quá sâu.

### 4.4. Role mặc định và role không mặc định

Khi đăng nhập, Oracle enable các default role của user. Role không mặc định có thể được enable bằng `SET ROLE` nếu user được phép sử dụng:

```sql
ALTER USER analyst_01
  DEFAULT ROLE report_reader_role;
```

Trong session:

```sql
SET ROLE report_reader_role;
```

Có thể kiểm tra role đang enable:

```sql
SELECT role
FROM session_roles
ORDER BY role;
```

`DBA_ROLE_PRIVS` cho biết role nào được cấp cho user/role và trạng thái default; `SESSION_ROLES` cho biết các role hiện được enable trong session. Hai view trả lời hai câu hỏi khác nhau.

### 4.5. Role có password hoặc secure application role

Oracle hỗ trợ role yêu cầu password khi enable và secure application role chỉ được enable qua một PL/SQL package được cấu hình. Secure application role giúp ứng dụng quyết định thời điểm và điều kiện kích hoạt role, chẳng hạn chỉ cho phép quyền nhạy cảm sau khi người dùng đã qua bước xác thực bổ sung.

Ví dụ khái quát:

```sql
CREATE ROLE payroll_sensitive_role
  IDENTIFIED USING security_admin.role_guard;
```

Package `SECURITY_ADMIN.ROLE_GUARD` được cấu hình làm cơ chế kiểm tra khi role được enable. Cần triển khai package bảo mật, quyền execute và logic xác thực phù hợp; chỉ tạo role với mệnh đề `IDENTIFIED USING` chưa đủ để xây dựng một chính sách an toàn hoàn chỉnh.

## 5. WITH ADMIN OPTION và WITH GRANT OPTION

Hai option đều cho phép cấp lại quyền, nhưng áp dụng cho hai loại grant khác nhau và có quy tắc thu hồi khác nhau.

### 5.1. WITH ADMIN OPTION cho system privilege

Ví dụ:

```sql
GRANT CREATE SESSION TO security_admin
WITH ADMIN OPTION;
```

`SECURITY_ADMIN` được phép sử dụng `CREATE SESSION` và cấp tiếp system privilege này cho user/role khác:

```sql
CONNECT security_admin/...

GRANT CREATE SESSION TO app_user;
```

`ADMIN OPTION` là quyền quản trị grant. Người nhận có thể cấp system privilege cho người khác và quản lý các grant tương ứng theo quy tắc Oracle. Chỉ cấp option này cho tài khoản có trách nhiệm quản trị quyền.

### 5.2. WITH GRANT OPTION cho object privilege

Ví dụ:

```sql
GRANT SELECT ON hr.employees TO hr_reporting_admin
WITH GRANT OPTION;
```

`HR_REPORTING_ADMIN` có thể đọc bảng và cấp tiếp quyền `SELECT` trên chính đối tượng đó:

```sql
CONNECT hr_reporting_admin/...

GRANT SELECT ON hr.employees TO report_user;
```

Quyền cấp lại gắn với object privilege cụ thể. Có `SELECT ... WITH GRANT OPTION` trên `HR.EMPLOYEES` không có nghĩa user được cấp quyền trên `HR.DEPARTMENTS` hoặc quyền `UPDATE` trên `HR.EMPLOYEES`.

Oracle không cho phép cấp object privilege với `WITH GRANT OPTION` cho role hoặc `PUBLIC`. Nếu cần phân phối object privilege qua role, hãy cấp privilege cho role mà không có grant option, rồi grant role cho user.

### 5.3. ADMIN OPTION khi grant role

Role cũng có thể được cấp với `ADMIN OPTION`:

```sql
GRANT report_reader_role TO department_admin
WITH ADMIN OPTION;
```

`DEPARTMENT_ADMIN` có thể cấp role đó cho user hoặc role khác theo quy tắc Oracle. Đây là quyền quản lý việc phân phối role, không phải quyền cấp lại từng object privilege bên trong role dưới dạng grant trực tiếp.

### 5.4. So sánh hai option

| Thuộc tính | `WITH ADMIN OPTION` | `WITH GRANT OPTION` |
|---|---|---|
| Dùng cho | System privilege và role | Object privilege |
| Cho phép cấp lại | System privilege/role tương ứng | Object privilege tương ứng trên cùng object |
| Có thể cấp cho role? | Có thể dùng trong grant system privilege/role theo cú pháp và quy tắc Oracle | Không được cấp object privilege với grant option cho role |
| Rủi ro chính | Mở rộng quyền quản trị và phân phối quyền | Tạo chuỗi grant object privilege cần theo dõi khi revoke |
| Câu lệnh ví dụ | `GRANT CREATE SESSION TO admin WITH ADMIN OPTION` | `GRANT SELECT ON hr.employees TO admin WITH GRANT OPTION` |

Không nhầm `ADMIN OPTION` với `GRANT OPTION`. Dùng sai option có thể khiến user có khả năng cấp lại quyền rộng hơn dự kiến.

## 6. Ai có thể cấp quyền?

### 6.1. Cấp system privilege

System privilege có thể được cấp bởi user có quyền quản trị thích hợp, ví dụ:

- User đã nhận chính system privilege đó với `ADMIN OPTION`.
- User có `GRANT ANY PRIVILEGE`.
- Tài khoản quản trị như `SYS` thực hiện theo chính sách quản trị database.

### 6.2. Cấp object privilege

Object privilege có thể được cấp bởi:

- Chủ sở hữu object.
- User đã nhận object privilege tương ứng với `GRANT OPTION`.
- User có system privilege `GRANT ANY OBJECT PRIVILEGE` trong phạm vi quyền được Oracle cho phép.

Một user chỉ nhận `SELECT` thông qua role không thể tự động cấp `SELECT ON object` đó cho user khác. Muốn cấp lại trực tiếp, user cần có quyền cấp phù hợp theo quy tắc Oracle; việc chỉ có thể sử dụng privilege trong session không đồng nghĩa có quyền quản trị grant.

### 6.3. Cấp role

Role được cấp bởi user có quyền quản lý role đó, chẳng hạn creator/owner hoặc user đã nhận role với `ADMIN OPTION`, tùy trường hợp. `GRANT ANY ROLE` là system privilege có phạm vi rộng để grant/revoke role; không cấp quyền này cho application account.

## 7. REVOKE và tác động của việc thu hồi

### 7.1. Thu hồi system privilege

```sql
REVOKE CREATE SESSION FROM app_user;
REVOKE SELECT ANY TABLE FROM reporting_admin;
```

Thu hồi system privilege từ một grantee loại bỏ grant tương ứng khỏi grantee đó. Với system privilege được cấp qua `ADMIN OPTION`, việc thu hồi không tự động cascade thu hồi privilege khỏi những user/role khác mà grantee trước đó đã cấp. Các grant tiếp theo cần được kiểm tra và quản trị riêng.

Điều này khác với object privilege có `GRANT OPTION`. Không giả định mọi chuỗi cấp quyền đều có cùng hành vi cascade khi revoke.

### 7.2. Thu hồi object privilege có grant option

Giả sử:

```sql
-- HR là owner
GRANT SELECT ON hr.employees TO user_a WITH GRANT OPTION;

-- USER_A cấp tiếp
GRANT SELECT ON hr.employees TO user_b WITH GRANT OPTION;

-- USER_B cấp tiếp
GRANT SELECT ON hr.employees TO user_c;
```

Nếu owner `HR` thu hồi quyền từ `USER_A`:

```sql
REVOKE SELECT ON hr.employees FROM user_a;
```

Oracle cascade revoke các object privilege phụ thuộc được cấp tiếp từ chuỗi grant đó, bao gồm grant của `USER_B` và `USER_C` trong ví dụ. Đây là lý do cần theo dõi chuỗi grant khi sử dụng `WITH GRANT OPTION`.

Nếu một user có quyền trực tiếp và đồng thời nhận quyền tương tự qua role, revoke một nguồn không nhất thiết loại bỏ nguồn còn lại. Hãy kiểm tra tất cả đường cấp quyền trước khi kết luận user đã mất khả năng truy cập.

### 7.3. Thu hồi privilege khỏi role

```sql
REVOKE SELECT ON hr.employees FROM report_reader_role;
```

Các user nhận privilege thông qua `REPORT_READER_ROLE` sẽ không còn quyền đó từ role sau khi thay đổi có hiệu lực trong session phù hợp. Tuy nhiên, nếu user còn được cấp `SELECT` trực tiếp hoặc qua role khác, quyền truy cập vẫn có thể tồn tại.

### 7.4. Thu hồi role khỏi user

```sql
REVOKE report_reader_role FROM analyst_01;
```

User mất các privilege đến từ role này khi role không còn được cấp/enable. Các quyền được cấp trực tiếp hoặc qua role khác không tự mất theo.

### 7.5. REFERENCES và CASCADE CONSTRAINTS

Khi cấp `REFERENCES` trên bảng, grantee có thể tạo foreign key tham chiếu các cột được cấp quyền. Nếu thu hồi `REFERENCES` trong khi có foreign key constraint phụ thuộc, Oracle có thể yêu cầu `CASCADE CONSTRAINTS`:

```sql
REVOKE REFERENCES ON hr.departments
FROM hr_app
CASCADE CONSTRAINTS;
```

Mệnh đề này cho phép thu hồi các constraint phụ thuộc theo quy tắc Oracle. Đây là thao tác có ảnh hưởng đến cấu trúc dữ liệu; cần xác định foreign key bị ảnh hưởng trước khi chạy.

## 8. Role và quyền trong PL/SQL

### 8.1. Definer's rights: role bị vô hiệu hóa

Stored PL/SQL unit mặc định chạy với quyền của chủ sở hữu (definer's rights, `AUTHID DEFINER`). Trong ngữ cảnh thực thi này, các role của user không được dùng để xác định quyền truy cập của unit; quyền cần thiết cho SQL tĩnh phải được cấp trực tiếp cho owner của PL/SQL unit (hoặc qua `PUBLIC` nếu phù hợp).

Ví dụ, package thuộc schema `APP_OWNER` đọc `HR.EMPLOYEES`:

```sql
GRANT SELECT ON hr.employees TO app_owner;
```

Chỉ grant `SELECT ON HR.EMPLOYEES` cho một role rồi grant role đó cho `APP_OWNER` có thể đủ để user tương tác trực tiếp trong session, nhưng không đủ cho definer-rights PL/SQL unit sử dụng quyền đó. Cần direct grant cho owner.

### 8.2. Invoker's rights: quyền theo người gọi

PL/SQL unit khai báo `AUTHID CURRENT_USER` chạy theo quyền của invoker. Trong ngữ cảnh invoker's rights, các role được enable của người gọi có thể được xét theo quy tắc Oracle. Điều này hữu ích khi cùng một unit cần thực thi với quyền của nhiều người gọi khác nhau.

```sql
CREATE OR REPLACE PROCEDURE read_employee_data
AUTHID CURRENT_USER
AS
BEGIN
  -- SQL executes using invoker's privilege context.
  NULL;
END;
/
```

Việc chọn `AUTHID DEFINER` hay `AUTHID CURRENT_USER` là quyết định thiết kế bảo mật. Invoker's rights không phải cách bật role tùy ý; cần phân tích schema resolution, quyền của invoker và quyền truy cập các object mà unit tham chiếu.

### 8.3. Kiểm tra role trong session không thay thế kiểm tra PL/SQL

`SESSION_ROLES` hiển thị role đang enable trong session tương tác. Khi vào definer-rights unit, tập role có hiệu lực thay đổi theo ngữ cảnh PL/SQL. Vì vậy, không dùng kết quả `SESSION_ROLES` bên ngoài unit để kết luận package chắc chắn có quyền thực thi câu SQL bên trong.

## 9. Các data dictionary view để kiểm tra quyền

### 9.1. System privilege được cấp trực tiếp cho user

```sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee IN ('APP_USER', 'REPORT_READER_ROLE')
ORDER BY grantee, privilege;
```

`DBA_SYS_PRIVS` hiển thị system privilege được cấp cho user/role. `USER_SYS_PRIVS` và `SESSION_PRIVS` phục vụ các góc nhìn hẹp hơn về user hiện tại và quyền đang có trong session.

### 9.2. Object privilege

```sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM dba_tab_privs
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY grantee, privilege;
```

`GRANTABLE='YES'` cho biết object privilege được cấp với grant option. Có thể dùng `USER_TAB_PRIVS`, `ALL_TAB_PRIVS` tùy phạm vi quyền và đối tượng cần quan sát.

### 9.3. Role được cấp cho user/role

```sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
FROM dba_role_privs
WHERE grantee IN ('APP_USER', 'APP_ROLE')
ORDER BY grantee, granted_role;
```

`ADMIN_OPTION='YES'` cho biết role được cấp với quyền cấp lại; `DEFAULT_ROLE` cho biết role có được enable mặc định khi user đăng nhập hay không. Role lồng nhau có thể cần truy vết thêm qua các dòng mà grantee là role.

### 9.4. Privilege bên trong role

```sql
SELECT role, privilege, admin_option
FROM role_sys_privs
WHERE role = 'REPORT_READER_ROLE'
ORDER BY privilege;

SELECT role, owner, table_name, privilege
FROM role_tab_privs
WHERE role = 'REPORT_READER_ROLE'
ORDER BY owner, table_name, privilege;
```

Các view `ROLE_SYS_PRIVS`, `ROLE_TAB_PRIVS` và `ROLE_ROLE_PRIVS` giúp xem system privilege, object privilege và role lồng bên trong một role.

### 9.5. Quyền đang có trong session

```sql
SELECT * FROM session_privs ORDER BY privilege;
SELECT * FROM session_roles ORDER BY role;
```

`SESSION_PRIVS` phản ánh system privilege có hiệu lực trong session; `SESSION_ROLES` liệt kê role đang enable. Để điều tra một quyền truy cập cụ thể, cần kết hợp các view này với direct grants, object grants và role hierarchy.

Các `DBA_*` view cần quyền đọc data dictionary phù hợp. Trong môi trường production, nên cấp quyền truy vấn thông tin quản trị qua role DBA/audit chuyên biệt thay vì cấp `SELECT ANY DICTIONARY` chỉ để xem một vài view.

## 10. Mẫu thiết kế quyền theo nguyên tắc least privilege

### 10.1. Tách owner schema và application schema

Một mô hình thường dùng là schema owner sở hữu bảng/package, còn application user chỉ nhận quyền cần thiết:

```text
HR_OWNER
  ├── owns EMPLOYEES, DEPARTMENTS
  └── owns EMPLOYEE_API package

HR_APP_ROLE
  ├── EXECUTE ON HR_OWNER.EMPLOYEE_API
  └── CREATE SESSION

HR_APP_USER
  └── receives HR_APP_ROLE
```

Ứng dụng gọi API/package thay vì có quyền cập nhật trực tiếp mọi bảng. Cách này tạo ranh giới kiểm soát nghiệp vụ và giảm phạm vi quyền dữ liệu.

### 10.2. Không cấp DBA hoặc ANY privilege cho tài khoản ứng dụng

Role `DBA` chứa nhiều system privilege mạnh. `SELECT ANY TABLE`, `UPDATE ANY TABLE`, `DROP ANY TABLE`, `GRANT ANY OBJECT PRIVILEGE` và các quyền tương tự có thể mở rộng phạm vi tác động trên nhiều schema.

Ứng dụng thông thường nên nhận:

- `CREATE SESSION` để kết nối.
- Object privilege tối thiểu trên bảng/view/package cần sử dụng.
- Quyền sequence hoặc directory riêng nếu chức năng cần.
- Role chuyên biệt theo chức năng, có owner và người quản lý rõ ràng.

Không cấp `CREATE TABLE`, `CREATE PROCEDURE` hoặc quyền DDL cho runtime account nếu ứng dụng không cần tạo đối tượng khi vận hành. Tách tài khoản deployment/migration khỏi tài khoản runtime giúp giảm rủi ro.

### 10.3. Role theo nhiệm vụ, không theo từng người dùng

Tên role nên thể hiện chức năng, ví dụ `ORDER_READ_ROLE`, `ORDER_WRITE_ROLE`, `PAYROLL_APPROVER_ROLE`. User nhận một hoặc nhiều role tương ứng với công việc. Tránh tạo role riêng cho từng user hoặc role tổng hợp quá rộng mà không có chủ sở hữu.

### 10.4. Rà soát định kỳ

Định kỳ kiểm tra:

- User không còn sử dụng nhưng vẫn có role/privilege.
- Role có quyền mạnh hoặc role lồng nhau không còn cần thiết.
- `ADMIN_OPTION` và `GRANTABLE` đang được bật ở đâu.
- User ứng dụng có system privilege `ANY`, DDL hoặc quyền quản trị ngoài nhu cầu.
- Object privilege được cấp trực tiếp ngoài mô hình role.
- Các chuỗi grant option tạo phụ thuộc khi revoke.
- Quyền truy cập được dùng bởi definer-rights PL/SQL có direct grant đầy đủ.

## 11. Ví dụ hoàn chỉnh: tạo role đọc báo cáo và cấp lại có kiểm soát

Giả sử schema `HR` sở hữu bảng `EMPLOYEES`; nhóm báo cáo cần đọc bảng, còn một quản trị viên bộ phận được phép cấp role cho nhân viên của nhóm.

```sql
-- 1. DBA tạo role chức năng
CREATE ROLE hr_report_reader;

-- 2. Owner cấp quyền kết nối và đọc dữ liệu cần thiết
GRANT CREATE SESSION TO hr_report_reader;
GRANT SELECT ON hr.employees TO hr_report_reader;

-- 3. DBA cấp role cho người dùng cuối
GRANT hr_report_reader TO analyst_01;

-- 4. DBA cấp role cho quản trị viên bộ phận với ADMIN OPTION
GRANT hr_report_reader TO department_admin
WITH ADMIN OPTION;

-- 5. Department admin có thể phân phối role cho nhân viên khác
-- (thực hiện trong session của department_admin)
GRANT hr_report_reader TO analyst_02;

-- 6. Kiểm tra role grant
SELECT grantee, granted_role, admin_option, default_role
FROM dba_role_privs
WHERE granted_role = 'HR_REPORT_READER';

-- 7. Khi analyst_01 chuyển nhóm, DBA thu hồi role
REVOKE hr_report_reader FROM analyst_01;
```

Trong ví dụ, `DEPARTMENT_ADMIN` có quyền cấp lại role vì được cấp `ADMIN OPTION`. Người dùng cuối nhận privilege qua role và không tự có quyền cấp object privilege `SELECT ON HR.EMPLOYEES` cho người khác. Nếu cần thu hồi một object privilege khỏi tất cả người dùng role, owner có thể revoke privilege khỏi role; nếu chỉ một user rời nhóm, revoke role khỏi user đó.

## 12. Nguyên tắc cần ghi nhớ

1. System privilege cho phép thực hiện hành động ở phạm vi database/schema; object privilege cho phép thao tác trên object cụ thể.
2. `CREATE TABLE` khác `CREATE ANY TABLE`; quyền có `ANY` thường mở rộng đáng kể phạm vi tác động.
3. Role gom system privilege, object privilege và role khác để quản lý theo chức năng.
4. Privilege được nhận qua role có thể phụ thuộc role đang enable; direct grant và role grant cần được phân biệt.
5. `WITH ADMIN OPTION` dùng cho system privilege/role; `WITH GRANT OPTION` dùng cho object privilege.
6. Object privilege không thể cấp cho role với `WITH GRANT OPTION`.
7. Revoke object privilege có grant option có thể cascade đến các grant phụ thuộc; revoke system privilege không tự cascade theo cùng cách.
8. Definer-rights PL/SQL không dùng các role của owner để thực thi; cấp direct grant cần thiết cho owner.
9. Kiểm tra `DBA_SYS_PRIVS`, `DBA_TAB_PRIVS`, `DBA_ROLE_PRIVS`, các view `ROLE_*` và `SESSION_*` để truy vết quyền.
10. Thiết kế theo least privilege, giới hạn quyền `ANY`/quản trị và rà soát chuỗi cấp lại định kỳ.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Language Reference — GRANT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GRANT.html)
- [Oracle Database 19c SQL Language Reference — REVOKE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/REVOKE.html)
- [Oracle Database 19c Security Guide — Configuring Privilege and Role Authorization](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-privilege-and-role-authorization.html)
- [Oracle Database 19c Database Reference — DBA_SYS_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SYS_PRIVS.html)
- [Oracle Database 19c Database Reference — DBA_TAB_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TAB_PRIVS.html)
- [Oracle Database 19c Database Reference — DBA_ROLE_PRIVS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_ROLE_PRIVS.html)
# System privilege, object privilege, role và quyền cấp lại

Oracle Database quản lý quyền truy cập theo nhiều lớp. Một user có thể được phép đăng nhập database nhưng không được tạo bảng; được phép gọi một package nhưng không được đọc trực tiếp bảng mà package sử dụng; hoặc nhận quyền thông qua một role được bật trong session. Khi quản trị quyền, cần phân biệt rõ **system privilege**, **object privilege**, **role** và quyền cấp lại như `WITH ADMIN OPTION` hoặc `WITH GRANT OPTION`.

Những khái niệm này quyết định ai được thực hiện thao tác nào, trên phạm vi nào và ai được phép chuyển tiếp quyền đó cho người khác. Nếu gộp chúng thành một khái niệm chung là “quyền user”, rất dễ cấp quyền rộng hơn yêu cầu, khó truy vết quyền hiệu lực và tạo ra các lỗi khó giải thích khi chạy PL/SQL.

## 1. Mô hình quyền trong Oracle

Có thể nhìn mô hình quyền theo ba thành phần:

- **Privilege:** quyền thực hiện một thao tác. Privilege có thể là system privilege hoặc object privilege.
- **Role:** một nhóm chứa system privilege, object privilege và các role khác. Role giúp cấp quyền theo chức năng hoặc trách nhiệm.
- **Grantee:** user, role hoặc `PUBLIC` nhận privilege/role.

Ví dụ một ứng dụng bán hàng có thể tổ chức như sau:

| Thành phần | Vai trò |
|---|---|
| `DATA_OWNER` | Sở hữu bảng nghiệp vụ |
| `APP_OWNER` | Sở hữu package và các object của ứng dụng |
| `APP_RUNTIME` | User mà ứng dụng dùng để kết nối |
| `ORDER_ENTRY_ROLE` | Role cho phép tạo và cập nhật đơn hàng |
| `ORDER_REPORT_ROLE` | Role chỉ đọc dữ liệu báo cáo |

Các quyền có thể được tổ chức thành chuỗi:

```text
System privileges ───────┐
                         ├──> Role ───> User
Object privileges ───────┘       │
                                 └──> Role khác (role lồng nhau)

System/Object privilege ─────────────> User trực tiếp
System/Object privilege ─────────────> PUBLIC
```

Quyền cấp trực tiếp cho user và quyền nhận thông qua role có thể cùng tồn tại. Quyền hiệu lực trong một session còn phụ thuộc role nào đang được bật và ngữ cảnh thực thi (SQL trực tiếp, definer-rights PL/SQL hay invoker-rights PL/SQL).

## 2. System privilege: quyền thực hiện thao tác ở cấp database

System privilege cho phép user thực hiện một loại thao tác trên database hoặc trong phạm vi schema được chỉ định bởi privilege. Nó không gắn với một bảng hay package duy nhất.

Một số system privilege phổ biến:

| System privilege | Ý nghĩa khái quát |
|---|---|
| `CREATE SESSION` | Kết nối vào database |
| `CREATE TABLE` | Tạo bảng trong schema của chính user |
| `CREATE VIEW` | Tạo view trong schema của chính user |
| `CREATE SEQUENCE` | Tạo sequence trong schema của chính user |
| `CREATE PROCEDURE` | Tạo procedure, function và package trong schema của chính user |
| `CREATE TRIGGER` | Tạo trigger trong schema của chính user |
| `CREATE SYNONYM` | Tạo synonym trong schema của chính user |
| `CREATE ANY TABLE` | Tạo bảng trong schema khác theo phạm vi system privilege `ANY` |
| `ALTER ANY TABLE` | Thay đổi cấu trúc bảng trong các schema theo phạm vi privilege |
| `SELECT ANY TABLE` | Đọc các bảng/view thuộc phạm vi privilege trên nhiều schema |
| `CREATE ANY PROCEDURE` | Tạo program unit trong schema khác theo phạm vi privilege |
| `GRANT ANY PRIVILEGE` | Cấp system privilege mà người cấp có quyền quản trị theo privilege này |
| `GRANT ANY ROLE` | Cấp role theo phạm vi quyền quản trị role |
| `ALTER SYSTEM` | Thực hiện các thao tác hệ thống được privilege này cho phép |

Tên có từ `ANY` thường cho phép thao tác vượt khỏi schema của chính user và có phạm vi rộng. Không nên cấp `CREATE ANY TABLE`, `SELECT ANY TABLE`, `ALTER ANY TABLE` hoặc các quyền `ANY` khác chỉ để làm cho một ứng dụng chạy được. Hãy xác định object cụ thể và cấp object privilege nếu nhu cầu chỉ giới hạn ở một số object.

### 2.1. Phân biệt quyền trong schema riêng và quyền ANY

Ví dụ:

```sql
-- APP_DEVELOPER chỉ tạo bảng trong schema của chính mình.
GRANT CREATE TABLE TO app_developer;

-- Quyền rộng hơn: có thể tạo bảng trong schema khác theo phạm vi ANY.
GRANT CREATE ANY TABLE TO app_admin;
```

`CREATE TABLE` không có nghĩa user được tạo bảng trong mọi schema. Tương tự, `CREATE PROCEDURE` cho phép tạo program unit trong schema của user; `CREATE ANY PROCEDURE` có phạm vi rộng hơn.

Quyền tạo object còn liên quan đến quota tablespace và các điều kiện khác. Có `CREATE TABLE` không tự động bảo đảm user có đủ quota để cấp phát segment trong tablespace. Quản trị viên cần kiểm tra cả quyền tạo object và giới hạn lưu trữ.

### 2.2. Cấp system privilege

Cú pháp cơ bản:

```sql
GRANT CREATE SESSION TO app_runtime;
GRANT CREATE TABLE TO app_developer;
```

Có thể cấp system privilege cho role để quản lý theo nhóm:

```sql
CREATE ROLE schema_developer_role;

GRANT CREATE TABLE,
      CREATE VIEW,
      CREATE SEQUENCE,
      CREATE PROCEDURE
TO schema_developer_role;

GRANT schema_developer_role TO app_developer;
```

Trong ví dụ, user `APP_DEVELOPER` nhận các quyền thông qua role. Nếu role được bật trong session, user có thể sử dụng những system privilege đó trong ngữ cảnh SQL thông thường mà role có hiệu lực.

### 2.3. Ai có thể cấp system privilege?

Thông thường, system privilege có thể được cấp bởi user có quyền quản trị thích hợp, chẳng hạn user có `GRANT ANY PRIVILEGE`, hoặc user đã nhận chính system privilege đó với `ADMIN OPTION`. Các quyền quản trị mạnh như vậy nên được giữ ở tài khoản quản trị có kiểm soát.

Có thể cấp system privilege kèm `WITH ADMIN OPTION`:

```sql
GRANT CREATE TABLE
TO team_lead
WITH ADMIN OPTION;
```

`TEAM_LEAD` có thể sử dụng `CREATE TABLE` và có thể cấp lại system privilege này cho user hoặc role khác. Đây là quyền quản trị, không chỉ là quyền sử dụng. Chỉ cấp khi người nhận thực sự chịu trách nhiệm quản lý quyền cho nhóm khác.

## 3. Object privilege: quyền trên một object cụ thể

Object privilege cho phép thực hiện thao tác trên một object được chỉ định, ví dụ một bảng, view, sequence, procedure, function, package hoặc directory.

Ví dụ, user báo cáo chỉ cần đọc bảng `APP.ORDERS`:

```sql
GRANT SELECT
ON app.orders
TO report_user;
```

Quyền này chỉ áp dụng trên object `APP.ORDERS`. Nó không tự cho phép đọc mọi bảng khác trong schema `APP` hoặc trong database.

### 3.1. Object privilege thường gặp theo loại object

| Loại object | Một số object privilege thường dùng |
|---|---|
| Table/view/materialized view | `SELECT`, `READ`, `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `INDEX`, `REFERENCES`, `FLASHBACK`, `DEBUG` (tùy object/phiên bản) |
| Sequence | `SELECT`, `ALTER` |
| Procedure/function/package | `EXECUTE`, `DEBUG` |
| Type | `EXECUTE`, `UNDER` trong các trường hợp hỗ trợ |
| Directory | `READ`, `WRITE`, `EXECUTE` theo nhu cầu sử dụng |

Không phải mọi privilege trong bảng đều áp dụng cho mọi loại object. Cần kiểm tra loại object và phiên bản Oracle trước khi cấp quyền.

### 3.2. Các quyền trên table và view

| Privilege | Tác dụng |
|---|---|
| `SELECT` | Truy vấn dữ liệu từ table/view |
| `READ` | Đọc dữ liệu với phạm vi hạn chế hơn `SELECT`, chẳng hạn không cho `SELECT FOR UPDATE` |
| `INSERT` | Thêm dòng |
| `UPDATE` | Cập nhật dòng hoặc cột được cấp quyền |
| `DELETE` | Xóa dòng |
| `ALTER` | Thay đổi định nghĩa object theo phạm vi được phép |
| `INDEX` | Tạo index trên table trong phạm vi privilege |
| `REFERENCES` | Tạo foreign key tham chiếu đến cột được cấp quyền |
| `FLASHBACK` | Thực hiện các truy vấn flashback được privilege cho phép |

Ví dụ cấp quyền đọc và thêm đơn hàng:

```sql
GRANT SELECT, INSERT
ON app.orders
TO order_entry_user;
```

Ví dụ cấp quyền cập nhật một số cột:

```sql
GRANT UPDATE (order_status, total_amount)
ON app.orders
TO order_entry_user;
```

Quyền theo cột giúp giới hạn phạm vi thay đổi. `ORDER_ENTRY_USER` có thể cập nhật trạng thái và tổng tiền nhưng không tự động được cập nhật mọi cột khác của bảng.

Oracle hỗ trợ cấp một số object privilege ở mức cột như `INSERT`, `UPDATE` và `REFERENCES`. Ví dụ:

```sql
GRANT INSERT (customer_id, order_date, total_amount)
ON app.orders
TO order_entry_user;
```

Không phải mọi privilege đều có dạng cấp theo cột. Hãy dùng đúng cú pháp được hỗ trợ cho loại privilege tương ứng.

### 3.3. Quyền trên sequence

Sequence thường được dùng để sinh mã. User cần quyền `SELECT` để gọi `NEXTVAL` hoặc `CURRVAL` của sequence mà user không sở hữu; quyền `ALTER` cho phép thay đổi thuộc tính sequence theo phạm vi được cấp.

```sql
GRANT SELECT
ON app.order_id_seq
TO app_runtime;
```

Sau đó user có thể tham chiếu sequence:

```sql
SELECT app.order_id_seq.NEXTVAL
FROM dual;
```

Quyền đọc sequence không đồng nghĩa với quyền `INSERT` vào bảng sử dụng sequence. Hai quyền này kiểm soát hai object khác nhau.

### 3.4. Quyền EXECUTE trên package, procedure và function

Để user gọi package do schema khác sở hữu, owner có thể cấp `EXECUTE`:

```sql
GRANT EXECUTE
ON app_owner.order_api
TO app_runtime;
```

`EXECUTE` cho phép gọi các subprogram công khai trong package specification. Nó không làm lộ các procedure/function private chỉ khai báo trong package body.

Quyền gọi package cũng không đồng nghĩa caller được đọc trực tiếp các bảng mà package sử dụng. Điều này đặc biệt quan trọng với package `AUTHID DEFINER`: package có thể thao tác trên object bằng quyền của owner, trong khi caller chỉ có `EXECUTE`. Tuy nhiên, package phải kiểm tra đầu vào và không được biến quyền của owner thành đường thực thi SQL tùy ý.

## 4. Owner, grantee và quyền mặc định trên object

User tạo object là owner. Owner có quyền quản lý object và có thể cấp các object privilege phù hợp cho user, role hoặc `PUBLIC`.

Ví dụ `APP` tạo bảng `ORDERS`. `APP` có thể truy vấn và thay đổi bảng theo quyền sở hữu, không cần tự grant `SELECT`, `INSERT` hoặc `UPDATE` cho chính mình.

Khi user khác cần truy cập, owner cấp quyền cụ thể:

```sql
GRANT SELECT
ON app.orders
TO reporting_role;

GRANT INSERT, UPDATE (order_status)
ON app.orders
TO order_entry_role;
```

Nếu người nhận cần truy cập object bằng tên không kèm schema, có thể tạo private hoặc public synonym. Synonym chỉ là tên thay thế; nó không cấp privilege. User vẫn cần quyền trên object đích.

```sql
CREATE SYNONYM orders FOR app.orders;
```

Việc tạo synonym không làm cho user có quyền đọc `APP.ORDERS` nếu chưa được cấp `SELECT` hoặc quyền thích hợp.

## 5. Role: nhóm privilege theo chức năng

Role là một đối tượng bảo mật dùng để gom system privilege, object privilege và role khác. Thay vì cấp từng privilege cho nhiều user, quản trị viên có thể cấp quyền vào role rồi cấp role cho user.

Ví dụ tạo role đọc báo cáo:

```sql
CREATE ROLE order_report_role;

GRANT SELECT
ON app.orders
TO order_report_role;

GRANT SELECT
ON app.customers
TO order_report_role;

GRANT order_report_role
TO report_user;
```

Khi `ORDER_REPORT_ROLE` được bật, `REPORT_USER` có thể đọc hai object đã được cấp. Khi user chuyển sang công việc khác, quản trị viên có thể thu hồi role mà không phải thu hồi từng privilege riêng lẻ.

### 5.1. Role lồng nhau

Một role có thể được cấp cho role khác. Điều này cho phép xây dựng nhóm quyền theo tầng:

```sql
CREATE ROLE order_read_role;
CREATE ROLE customer_read_role;
CREATE ROLE sales_report_role;

GRANT SELECT ON app.orders TO order_read_role;
GRANT SELECT ON app.customers TO customer_read_role;

GRANT order_read_role TO sales_report_role;
GRANT customer_read_role TO sales_report_role;

GRANT sales_report_role TO report_user;
```

`REPORT_USER` nhận quyền đọc cả hai bảng thông qua role tổng hợp `SALES_REPORT_ROLE`. Cách tổ chức này giúp tái sử dụng nhóm quyền, nhưng role lồng nhau quá sâu có thể khiến việc truy vết quyền hiệu lực khó hơn. Nên đặt tên role theo chức năng và giữ cấu trúc đơn giản.

### 5.2. Role mặc định và role đang bật

Role được grant cho user có thể được cấu hình là default role. Các default role được bật khi user đăng nhập, trừ khi cấu hình hoặc thao tác session thay đổi trạng thái.

Có thể chỉ định default role:

```sql
ALTER USER report_user
DEFAULT ROLE order_report_role;
```

Hoặc tắt tất cả role mặc định:

```sql
ALTER USER report_user DEFAULT ROLE NONE;
```

Trong session, user có thể bật hoặc tắt role được phép sử dụng:

```sql
SET ROLE order_report_role;
```

```sql
SET ROLE NONE;
```

Có thể bật nhiều role:

```sql
SET ROLE order_report_role, customer_read_role;
```

Việc role đã được grant không có nghĩa nó luôn đang được bật. Khi một câu SQL báo thiếu quyền, hãy kiểm tra role hiện tại và quyền hiệu lực trong session.

### 5.3. Role có mật khẩu và secure application role

Oracle hỗ trợ các cơ chế kiểm soát việc bật role, bao gồm role được bảo vệ bằng password và secure application role được bật thông qua một package xác thực. Secure application role thường phù hợp khi ứng dụng chỉ được bật quyền sau khi đáp ứng điều kiện nghiệp vụ hoặc bảo mật.

Ví dụ khái niệm:

```sql
CREATE ROLE order_approval_role
IDENTIFIED USING app_owner.role_guard;
```

Package `ROLE_GUARD` chịu trách nhiệm xác thực ngữ cảnh trước khi gọi `DBMS_SESSION.SET_ROLE` cho role được bảo vệ. Cú pháp và thiết kế chi tiết cần tuân theo yêu cầu của Oracle Database phiên bản triển khai. Không nên xem secure application role là thay thế cho xác thực người dùng ở tầng ứng dụng hoặc cho việc cấp quyền tối thiểu.

### 5.4. PUBLIC là role đặc biệt

`PUBLIC` là một grantee đặc biệt đại diện cho tất cả database user. Khi privilege hoặc role được cấp cho `PUBLIC`, mọi user có thể nhận quyền đó theo cơ chế tương ứng.

Ví dụ:

```sql
GRANT SELECT ON app.reference_codes TO PUBLIC;
```

Quyền này có thể phù hợp với một số dữ liệu tham chiếu công khai trong phạm vi database, nhưng không nên dùng để đơn giản hóa cấu hình ứng dụng. Với dữ liệu nghiệp vụ hoặc package nhạy cảm, hãy cấp cho role/user cụ thể.

## 6. WITH GRANT OPTION và WITH ADMIN OPTION

Hai tùy chọn này đều liên quan đến việc chuyển tiếp quyền, nhưng áp dụng cho các loại quyền khác nhau.

| Tiêu chí | `WITH GRANT OPTION` | `WITH ADMIN OPTION` |
|---|---|---|
| Áp dụng cho | Object privilege | System privilege và role |
| Người nhận có thể làm gì? | Cấp lại object privilege tương ứng cho user khác theo quy tắc Oracle | Cấp privilege/role tương ứng cho user hoặc role khác; quản trị việc grant/revoke theo phạm vi được phép |
| Thường dùng trong | Ủy quyền trên một object cụ thể | Ủy quyền quản trị system privilege hoặc role |
| Có cấp cho role/PUBLIC được không? | Không dùng `WITH GRANT OPTION` khi grantee là role hoặc `PUBLIC` | Có thể cấp `ADMIN OPTION` khi grantee là user hoặc role theo cú pháp hỗ trợ |

### 6.1. WITH GRANT OPTION cho object privilege

Ví dụ owner cấp quyền đọc bảng cho một user và cho phép user đó cấp lại:

```sql
GRANT SELECT
ON app.orders
TO team_lead
WITH GRANT OPTION;
```

`TEAM_LEAD` có thể cấp tiếp quyền `SELECT` trên chính object đó:

```sql
GRANT SELECT
ON app.orders
TO analyst_01;
```

Quyền cấp lại bị giới hạn bởi object privilege mà `TEAM_LEAD` đã nhận. Nó không tự tạo ra quyền `INSERT`, `UPDATE` hay quyền trên object khác.

`WITH GRANT OPTION` không được dùng khi grant object privilege cho role hoặc `PUBLIC`. Nếu cần nhiều user có cùng quyền, cách rõ ràng hơn thường là grant object privilege cho role rồi grant role cho các user.

### 6.2. WITH ADMIN OPTION cho system privilege

Ví dụ:

```sql
GRANT CREATE TABLE
TO team_lead
WITH ADMIN OPTION;
```

`TEAM_LEAD` có thể cấp `CREATE TABLE` cho user khác:

```sql
GRANT CREATE TABLE TO developer_01;
```

`ADMIN OPTION` không có nghĩa user nhận được quyền quản trị mọi system privilege. Người nhận chỉ có thể cấp lại privilege được cấp với option này, trừ khi họ có thêm quyền quản trị khác.

### 6.3. WITH ADMIN OPTION cho role

Role cũng có thể được cấp kèm `ADMIN OPTION`:

```sql
GRANT order_report_role
TO team_lead
WITH ADMIN OPTION;
```

`TEAM_LEAD` có thể grant role `ORDER_REPORT_ROLE` cho user hoặc role khác. Vì vậy, quyền quản trị role cần được quản lý chặt: một role chứa nhiều privilege có thể được lan truyền rộng hơn dự kiến nếu người nhận có `ADMIN OPTION`.

### 6.4. Không nhầm option với quyền sử dụng

Một user có `SELECT ON APP.ORDERS` chỉ có quyền đọc object. Nếu có `WITH GRANT OPTION`, user có thêm khả năng cấp lại quyền đọc đó. Tương tự, một user có `CREATE TABLE` chỉ có quyền tạo bảng trong schema của mình; nếu có `WITH ADMIN OPTION`, user còn có khả năng cấp lại system privilege đó.

Vì quyền cấp lại mở rộng phạm vi quản trị, chỉ cấp option khi có nhu cầu ủy quyền rõ ràng. Với ứng dụng runtime, thông thường chỉ cần quyền sử dụng, không cần quyền grant.

## 7. Thu hồi privilege và ảnh hưởng dây chuyền

Quản trị quyền không chỉ là cấp. Khi user đổi vai trò, nghỉ việc hoặc ứng dụng không còn cần object, quyền phải được thu hồi đúng phạm vi.

### 7.1. Thu hồi system privilege

```sql
REVOKE CREATE TABLE
FROM app_developer;
```

Nếu system privilege được cấp cho role, có thể thu hồi khỏi role:

```sql
REVOKE CREATE TABLE
FROM schema_developer_role;
```

Thu hồi quyền trực tiếp khỏi user không tự động xóa privilege mà user còn nhận thông qua role khác. Cần kiểm tra tất cả đường cấp quyền trước khi kết luận user đã mất quyền.

Việc thu hồi system privilege đã được cấp với `ADMIN OPTION` không có cùng cơ chế cascading như thu hồi object privilege có `GRANT OPTION`. Người đã nhận system privilege từ grantee có admin option có thể vẫn giữ quyền được grant riêng của họ. Vì vậy, khi thu hồi quyền quản trị, cần rà soát các grant phát sinh và thu hồi riêng khi chính sách yêu cầu.

### 7.2. Thu hồi object privilege

```sql
REVOKE UPDATE
ON app.orders
FROM order_entry_user;
```

Nếu một object privilege được cấp kèm `WITH GRANT OPTION` và người nhận đã grant lại cho người khác, việc owner thu hồi grant trong chuỗi có thể làm các grant phụ thuộc bị thu hồi dây chuyền (*cascading revoke*).

Ví dụ:

```text
APP (owner)
  │ GRANT SELECT WITH GRANT OPTION
  ▼
TEAM_LEAD
  │ GRANT SELECT
  ▼
ANALYST_01
```

Nếu `APP` thu hồi `SELECT` khỏi `TEAM_LEAD`, grant mà `TEAM_LEAD` đã cấp cho `ANALYST_01` cũng bị thu hồi do phụ thuộc vào grant option ban đầu. Đây là điểm quan trọng khi quản trị chuỗi cấp lại object privilege.

### 7.3. Thu hồi role

```sql
REVOKE order_report_role
FROM report_user;
```

Sau khi role bị thu hồi khỏi user, các privilege mà user chỉ nhận thông qua role đó không còn hiệu lực qua đường grant này. Tuy nhiên, nếu user còn nhận cùng privilege trực tiếp hoặc qua role khác, user vẫn có thể sử dụng privilege đó.

Khi rà soát sau revoke, cần phân biệt:

- Quyền trực tiếp được grant cho user.
- Quyền được grant qua role trực tiếp.
- Quyền được kế thừa qua role lồng nhau.
- Quyền được cấp cho `PUBLIC`.
- Quyền phát sinh từ system privilege có phạm vi rộng.

Một lệnh `REVOKE` thành công không tự chứng minh rằng user đã mất mọi con đường truy cập object.

## 8. Quyền trực tiếp và quyền qua role trong PL/SQL

Đây là một trong những điểm quan trọng nhất khi xử lý lỗi privilege trong package, procedure, function, trigger và view.

Trong SQL chạy trực tiếp ở session, role đang bật có thể cung cấp privilege. Nhưng trong named PL/SQL unit chạy theo quyền definer (`AUTHID DEFINER`, là mặc định), các role của session bị vô hiệu hóa khi thực thi unit. Vì vậy, code cần quyền trên object phải nhận quyền trực tiếp cho schema sở hữu unit, hoặc dùng cơ chế role gắn với program unit được hỗ trợ như Code Based Access Control.

Ví dụ:

```sql
-- DATA_OWNER sở hữu bảng.
GRANT SELECT ON data_owner.orders TO app_owner;
```

Sau đó package của `APP_OWNER` có thể truy vấn bảng bằng quyền definer:

```sql
CREATE OR REPLACE PACKAGE app_owner.order_query_api
AUTHID DEFINER
AS
    PROCEDURE show_orders;
END order_query_api;
/

CREATE OR REPLACE PACKAGE BODY app_owner.order_query_api
AS
    PROCEDURE show_orders
    IS
        l_count NUMBER;
    BEGIN
        SELECT COUNT(*)
        INTO l_count
        FROM data_owner.orders;
    END show_orders;
END order_query_api;
/
```

Nếu chỉ grant `SELECT ON DATA_OWNER.ORDERS` cho một role mà `APP_OWNER` nhận, static SQL trong definer-rights unit không thể dựa vào role session đó. Hãy cấp trực tiếp cho `APP_OWNER` nếu package cần quyền này.

### 8.1. Invoker-rights unit

Với `AUTHID CURRENT_USER`, quyền được kiểm tra theo ngữ cảnh invoker. Các role đang bật của invoker có thể tham gia kiểm tra quyền khi unit thực thi. Điều này hữu ích khi package được thiết kế để sử dụng quyền riêng của từng caller.

```sql
CREATE OR REPLACE PACKAGE app_owner.report_api
AUTHID CURRENT_USER
AS
    PROCEDURE show_report;
END report_api;
/
```

Khi caller `REPORT_USER` gọi package, các object mà package truy cập cần có quyền phù hợp đối với invoker theo quy tắc Oracle. Không nên giả định rằng chỉ cần cấp `EXECUTE` là đủ cho mọi invoker-rights unit.

`CURRENT_USER` và `CURRENT_SCHEMA` là hai khái niệm khác nhau. `CURRENT_USER` liên quan đến ngữ cảnh kiểm tra quyền; `CURRENT_SCHEMA` ảnh hưởng đến việc phân giải tên object không ghi rõ schema. Đổi `CURRENT_SCHEMA` không tự cấp privilege.

### 8.2. Code Based Access Control (CBAC)

Oracle hỗ trợ cấp role cho một program unit trong các phiên bản có Code Based Access Control. Role được bật trong phạm vi thực thi của unit, cho phép gắn một tập quyền cụ thể với package/procedure thay vì cấp toàn bộ quyền đó cho schema owner.

Ví dụ minh họa:

```sql
GRANT order_data_reader TO PACKAGE app_owner.order_query_api;
```

CBAC cần được cấu hình và kiểm thử theo phiên bản Oracle đang sử dụng. Không nên dùng CBAC để che giấu một ma trận quyền không rõ ràng. Hãy xác định chính xác package cần privilege nào và role đó chỉ chứa những quyền tối thiểu nào.

### 8.3. Quyền khi tạo view và biên dịch stored code

Khi tạo view dựa trên object của schema khác, chủ sở hữu view cần các object privilege cần thiết được grant trực tiếp theo quy tắc Oracle; quyền chỉ nhận qua role không đủ cho một số bước xác thực quyền của view.

Tương tự, khi biên dịch stored PL/SQL có static SQL tham chiếu object khác schema, owner cần quyền trực tiếp phù hợp. Nếu compile lỗi `PLS-00201` hoặc `ORA-00942`, đừng vội cấp `SELECT ANY TABLE`; hãy kiểm tra object tồn tại, schema qualification và direct grant.

## 9. Phân biệt quyền trên object với quyền tạo object

Một lỗi thiết kế thường gặp là cấp system privilege rộng khi ứng dụng chỉ cần thao tác trên một object cụ thể.

Ví dụ, ứng dụng chỉ cần đọc bảng `APP.ORDERS`:

```sql
-- Phạm vi hẹp.
GRANT SELECT ON app.orders TO app_runtime;
```

Không nên thay bằng:

```sql
-- Phạm vi rộng trên nhiều object.
GRANT SELECT ANY TABLE TO app_runtime;
```

Tương tự, nếu user cần cập nhật một bảng cụ thể, hãy grant `UPDATE ON schema.table` hoặc quyền theo cột phù hợp. Không cấp system privilege như `UPDATE ANY TABLE` chỉ để xử lý một bảng.

Một system privilege như `CREATE TABLE` cũng không tương đương object privilege trên một bảng đã tồn tại. `CREATE TABLE` cho phép tạo object trong schema của user; `SELECT ON APP.ORDERS` cho phép đọc object được chỉ định. Hai quyền giải quyết hai mục tiêu khác nhau.

## 10. Tra cứu quyền đã cấp và quyền hiệu lực

Oracle cung cấp data dictionary views để kiểm tra grant. Cần chọn view đúng phạm vi: quyền của user hiện tại, quyền trên object, quyền của role hay quyền toàn database.

### 10.1. Kiểm tra system privilege

Một số view thường dùng:

| View | Phạm vi |
|---|---|
| `USER_SYS_PRIVS` | System privilege được grant trực tiếp cho user hiện tại |
| `ROLE_SYS_PRIVS` | System privilege được grant cho role mà user có thể xem |
| `DBA_SYS_PRIVS` | System privilege được grant trong database; cần quyền xem DBA view |
| `SESSION_PRIVS` | System privilege hiện có hiệu lực trong session |

Ví dụ:

```sql
SELECT privilege,
       admin_option
FROM user_sys_privs
ORDER BY privilege;
```

Xem system privilege được cấp trong database:

```sql
SELECT grantee,
       privilege,
       admin_option
FROM dba_sys_privs
WHERE grantee IN ('APP_RUNTIME', 'SCHEMA_DEVELOPER_ROLE')
ORDER BY grantee, privilege;
```

### 10.2. Kiểm tra object privilege

| View | Phạm vi |
|---|---|
| `USER_TAB_PRIVS_MADE` | Object privilege được user hiện tại cấp cho người khác |
| `USER_TAB_PRIVS_RECD` | Object privilege user hiện tại nhận được |
| `USER_TAB_PRIVS` | Object privilege liên quan đến object trong phạm vi user hiện tại theo định nghĩa view |
| `USER_COL_PRIVS` | Object privilege cấp theo cột trong phạm vi user hiện tại |
| `ALL_TAB_PRIVS` | Object privilege trên các object user có thể truy cập metadata |
| `DBA_TAB_PRIVS` | Object privilege được grant trong database |
| `DBA_COL_PRIVS` | Object privilege cấp theo cột trong database |

Ví dụ xem quyền trên một bảng:

```sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
FROM all_tab_privs
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY grantee, privilege;
```

`GRANTABLE = 'YES'` cho biết object privilege được cấp với grant option. Điều này khác với `ADMIN_OPTION` của system privilege hoặc role.

### 10.3. Kiểm tra role được grant

| View | Phạm vi |
|---|---|
| `USER_ROLE_PRIVS` | Role được grant cho user hiện tại |
| `ROLE_ROLE_PRIVS` | Role được grant cho role |
| `DBA_ROLE_PRIVS` | Role được grant cho user và role trong database |
| `SESSION_ROLES` | Role hiện đang bật trong session |

Ví dụ:

```sql
SELECT granted_role,
       admin_option,
       default_role
FROM user_role_privs
ORDER BY granted_role;
```

Kiểm tra role đang bật:

```sql
SELECT role
FROM session_roles
ORDER BY role;
```

### 10.4. Xem privilege trong role

Để hiểu role mang theo quyền nào, cần xem cả system privilege và object privilege của role:

```sql
SELECT role,
       privilege,
       admin_option
FROM role_sys_privs
ORDER BY role, privilege;
```

```sql
SELECT role,
       owner,
       table_name,
       privilege
FROM role_tab_privs
ORDER BY role, owner, table_name, privilege;
```

Nếu role được lồng qua nhiều tầng, hãy truy vết các role được grant cho role khác. Một user có thể có privilege thông qua nhiều đường khác nhau; chỉ xem `USER_SYS_PRIVS` hoặc `USER_TAB_PRIVS_RECD` chưa chắc giải thích được toàn bộ quyền hiệu lực.

### 10.5. Truy vấn quyền quản trị và quyền cấp lại

Các cột quan trọng thường gồm:

- `ADMIN_OPTION` trong `DBA_SYS_PRIVS` hoặc `DBA_ROLE_PRIVS` cho biết người nhận có quyền cấp lại system privilege/role hay không.
- `GRANTABLE` trong `DBA_TAB_PRIVS` cho biết object privilege có được cấp kèm grant option hay không.
- `DEFAULT_ROLE` trong `DBA_ROLE_PRIVS` cho biết role có được bật mặc định khi đăng nhập hay không.

Khi kiểm tra một user, nên đối chiếu direct grants, roles được grant, role đang bật, quyền `PUBLIC` và các system privilege có phạm vi rộng. Đừng chỉ nhìn một view rồi kết luận user có hoặc không có quyền.

## 11. Thiết kế ma trận quyền theo vai trò

Một hệ thống nên có ma trận quyền thể hiện user/role nào được phép thực hiện thao tác nào trên object nào.

Ví dụ:

| Role | ORDERS | CUSTOMERS | ORDER_API |
|---|---|---|---|
| `ORDER_ENTRY_ROLE` | `SELECT`, `INSERT`, `UPDATE(status)` | `SELECT` | `EXECUTE` |
| `ORDER_REPORT_ROLE` | `SELECT` | `SELECT` | Không cần |
| `ORDER_SUPPORT_ROLE` | `SELECT`, `UPDATE(status)` | `SELECT` | `EXECUTE` |

Tài khoản runtime chỉ nhận các role cần cho luồng nghiệp vụ. Không nên dùng một role chung chứa quyền đọc, ghi, DDL và quản trị database cho mọi tài khoản.

Một số nguyên tắc hữu ích:

1. Tách user sở hữu object khỏi user runtime của ứng dụng.
2. Cấp `CREATE SESSION` và quyền cần thiết để kết nối.
3. Cấp object privilege theo từng object hoặc API cụ thể.
4. Dùng role theo chức năng để gom quyền có cùng mục đích.
5. Không cấp quyền `ANY` nếu object privilege hẹp đã đáp ứng yêu cầu.
6. Chỉ cấp `ADMIN OPTION` hoặc `GRANT OPTION` khi người nhận cần ủy quyền lại.
7. Tránh grant cho `PUBLIC` nếu không có lý do nghiệp vụ và bảo mật rõ ràng.
8. Rà soát role mặc định và role được bật trong connection pool.
9. Ghi nhận chủ sở hữu, lý do và thời hạn của quyền đặc biệt.
10. Kiểm thử bằng đúng user và role của ứng dụng, không chỉ bằng tài khoản DBA.

## 12. Ví dụ triển khai từ đầu đến cuối

Giả sử có schema dữ liệu `DATA_OWNER`, schema package `APP_OWNER` và user kết nối ứng dụng `APP_RUNTIME`.

### 12.1. Cấp quyền cho owner của package

`APP_OWNER` cần quyền trực tiếp trên bảng mà package thao tác:

```sql
GRANT SELECT, INSERT, UPDATE
ON data_owner.orders
TO app_owner;
```

### 12.2. Cấp quyền gọi package cho runtime role

```sql
CREATE ROLE order_api_executor;

GRANT EXECUTE
ON app_owner.order_api
TO order_api_executor;

GRANT order_api_executor
TO app_runtime;
```

### 12.3. Cấp quyền kết nối

```sql
GRANT CREATE SESSION TO app_runtime;
```

Trong mô hình này, `APP_RUNTIME` có thể gọi package thông qua role `ORDER_API_EXECUTOR`. `APP_OWNER` có quyền trực tiếp trên bảng `DATA_OWNER.ORDERS`. Nếu package là definer-rights, code sử dụng quyền của `APP_OWNER` theo hợp đồng API.

### 12.4. Kiểm tra từ tài khoản runtime

Đăng nhập bằng `APP_RUNTIME` và kiểm tra role:

```sql
SELECT role
FROM session_roles;
```

Gọi API:

```sql
BEGIN
    app_owner.order_api.create_order(
        p_customer_id => 1001,
        p_product_id  => 501,
        p_quantity    => 2
    );
END;
/
```

Sau đó thử truy vấn trực tiếp bảng `DATA_OWNER.ORDERS`. Nếu thiết kế không cấp `SELECT` cho runtime, truy vấn trực tiếp phải bị từ chối. Điều này xác nhận ranh giới API đang hoạt động như dự kiến.

## 13. Các lỗi thường gặp khi cấp quyền

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `ORA-01031: insufficient privileges` | Thiếu system/object privilege hoặc role không được bật trong ngữ cảnh hiện tại | Xác định user thực thi, `AUTHID`, role và grant trực tiếp |
| `ORA-00942: table or view does not exist` | Sai schema/object name hoặc thiếu quyền nhìn thấy object | Kiểm tra object và direct grant; không vội cấp `SELECT ANY TABLE` |
| `PLS-00201: identifier must be declared` | Object/package không nhìn thấy khi compile hoặc thiếu quyền cần thiết | Kiểm tra owner, synonym, direct grant và lỗi compile |
| User gọi được SQL trực tiếp nhưng package lỗi | Package chạy theo definer rights nên role session bị vô hiệu hóa | Cấp quyền trực tiếp cho owner hoặc dùng CBAC có kiểm soát |
| User đã bị revoke nhưng vẫn truy cập được | Quyền còn qua role khác, grant trực tiếp, `PUBLIC` hoặc system privilege rộng | Truy vết mọi đường cấp quyền |
| User có role nhưng không dùng được privilege | Role không phải default hoặc đang bị tắt trong session | Kiểm tra `SESSION_ROLES`, `SET ROLE` và connection pool |
| Không grant lại được object privilege | Người cấp không phải owner, không có grant option hoặc thiếu quyền quản trị thích hợp | Kiểm tra `GRANTABLE`, grantor và quyền quản trị |

Không nên xử lý lỗi quyền bằng cách grant hàng loạt system privilege. Hãy xác định chính xác thao tác thất bại, object liên quan, user thực thi, ngữ cảnh PL/SQL và đường nhận privilege.

## 14. Quy trình rà soát quyền định kỳ

Một quy trình rà soát quyền có thể thực hiện theo các bước:

1. **Liệt kê user và account:** xác định user ứng dụng, owner, user vận hành và user quản trị.
2. **Liệt kê system privilege:** tìm các quyền `ANY`, quyền DDL và quyền quản trị nhạy cảm.
3. **Liệt kê object privilege:** xác định object nào được chia sẻ và cho grantee nào.
4. **Kiểm tra role:** xem role trực tiếp, role lồng nhau, default role và role đang bật.
5. **Kiểm tra quyền cấp lại:** tìm `ADMIN_OPTION = 'YES'` và `GRANTABLE = 'YES'`.
6. **Kiểm tra PUBLIC:** rà soát privilege/role được cấp cho `PUBLIC`.
7. **Đối chiếu với chức năng:** xác nhận từng quyền còn phục vụ nghiệp vụ đang tồn tại.
8. **Thu hồi quyền dư thừa:** thực hiện theo quy trình change control và kiểm tra ứng dụng sau revoke.
9. **Kiểm thử ngữ cảnh thực thi:** chạy bằng user runtime và đúng role, đặc biệt với stored PL/SQL.
10. **Lưu bằng chứng:** ghi lại người cấp, lý do, thời điểm, phạm vi và người phê duyệt quyền đặc biệt.

## 15. Những nhầm lẫn cần tránh

| Nhầm lẫn | Thực tế |
|---|---|
| `CREATE TABLE` cho phép tạo bảng trong mọi schema | Chỉ tạo trong schema của user; `CREATE ANY TABLE` có phạm vi rộng hơn |
| `SELECT ON APP.ORDERS` cho phép đọc mọi bảng của APP | Chỉ áp dụng object được chỉ định |
| Synonym tự cấp quyền truy cập | Synonym chỉ đổi tên tham chiếu, privilege vẫn cần riêng |
| Role là một system privilege | Role là container chứa privilege và role khác |
| Role được grant luôn đang bật | Role có thể không phải default hoặc bị tắt trong session |
| `WITH GRANT OPTION` và `WITH ADMIN OPTION` giống nhau | Grant option dành cho object privilege; admin option dành cho system privilege và role |
| Có `EXECUTE` trên package nghĩa là được đọc bảng bên trong | Quyền truy cập nội bộ phụ thuộc `AUTHID` và quyền của owner/invoker |
| DBA chạy được thì runtime user cũng chạy được | DBA có thể có quyền vượt xa ứng dụng; phải test bằng đúng runtime account |
| Revoke một role là chắc chắn mất mọi quyền | Quyền có thể còn qua grant trực tiếp, role khác, PUBLIC hoặc system privilege |
| Cấp quyền `ANY` là cách nhanh nhất để sửa lỗi | `ANY` mở rộng phạm vi lớn; nên cấp object privilege hẹp khi có thể |

System privilege, object privilege và role giải quyết những phạm vi quyền khác nhau. `WITH ADMIN OPTION` và `WITH GRANT OPTION` bổ sung khả năng ủy quyền, nên cần được xem là quyền quản trị có rủi ro cao hơn quyền sử dụng thông thường. Khi thiết kế theo nguyên tắc tối thiểu, tách quyền theo chức năng, truy vết đầy đủ các đường grant và kiểm thử trong đúng ngữ cảnh session/PLSQL, hệ thống sẽ dễ quản trị và hạn chế được việc cấp quyền quá rộng.
