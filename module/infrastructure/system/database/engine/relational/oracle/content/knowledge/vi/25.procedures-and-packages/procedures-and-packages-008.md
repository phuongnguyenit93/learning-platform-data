# AUTHID DEFINER, AUTHID CURRENT_USER và kiểm tra quyền thực thi

Một stored procedure hoặc package có thể truy cập dữ liệu bằng quyền của schema sở hữu code hoặc bằng quyền của người đang gọi nó. Oracle điều khiển hành vi này bằng thuộc tính AUTHID:

- **AUTHID DEFINER**: code chạy theo quyền của owner (người định nghĩa). Đây là mặc định nếu không khai báo AUTHID.
- **AUTHID CURRENT_USER**: code chạy theo quyền của invoker (người gọi trong ngữ cảnh hiện tại).

Lựa chọn này ảnh hưởng trực tiếp đến bảo mật, cách Oracle kiểm tra privilege, cách phân giải tên object, vai trò của role và khả năng tái sử dụng PL/SQL giữa nhiều schema. Một API definer-rights được thiết kế đúng có thể cho ứng dụng dùng dữ liệu qua một giao diện hẹp mà không cần cấp quyền trực tiếp lên bảng. Một utility invoker-rights có thể dùng quyền và schema của caller để thao tác trên dữ liệu mà caller được phép truy cập.

Bài học tập trung vào cách chọn AUTHID, hiểu sự khác nhau giữa SESSION_USER và CURRENT_USER, cấp direct grant, xử lý INHERIT PRIVILEGES, kiểm tra quyền thực thi, bảo vệ dynamic SQL và kiểm chứng bằng lab nhiều schema.

## 1. AUTHID điều khiển điều gì?

AUTHID là thuộc tính bảo mật của named PL/SQL unit như standalone procedure/function, package hoặc type method. Nó quyết định ngữ cảnh quyền được dùng khi unit chạy.

~~~text
APP_USER
   |
   | EXECUTE
   v
API_OWNER.GET_REPORT
   |
   +-- AUTHID DEFINER
   |      |
   |      +-- SQL chạy theo quyền API_OWNER
   |      +-- role thông thường của APP_USER không được dùng
   |
   +-- AUTHID CURRENT_USER
          |
          +-- SQL chạy theo quyền invoker hiện tại
          +-- role đang bật của invoker có thể được dùng
~~~

AUTHID không tự cấp quyền cho ai. Người gọi vẫn cần quyền EXECUTE trên procedure/package. AUTHID chỉ quyết định ngữ cảnh privilege và name resolution khi code được thực thi.

### 1.1. AUTHID DEFINER là mặc định

Nếu không khai báo AUTHID, named PL/SQL unit mặc định dùng definer rights. Hai khai báo sau có cùng ý nghĩa về AUTHID:

~~~sql
CREATE OR REPLACE PROCEDURE p_report (
    p_id IN NUMBER
) AS
BEGIN
    NULL;
END;
/
~~~

~~~sql
CREATE OR REPLACE PROCEDURE p_report (
    p_id IN NUMBER
)
AUTHID DEFINER
AS
BEGIN
    NULL;
END;
/
~~~

Viết tường minh AUTHID DEFINER có thể giúp người đọc nhận ra chủ ý bảo mật của API, dù không bắt buộc.

### 1.2. AUTHID CURRENT_USER

Để chạy theo quyền của invoker:

~~~sql
CREATE OR REPLACE PROCEDURE p_report (
    p_id IN NUMBER
)
AUTHID CURRENT_USER
AS
BEGIN
    NULL;
END;
/
~~~

Caller phải có EXECUTE trên procedure. Khi procedure thực hiện thao tác dữ liệu, Oracle kiểm tra quyền theo invoker hiện tại, cùng các role đang bật trong ngữ cảnh đó.

### 1.3. Package dùng một AUTHID cho các subprogram

AUTHID của package được khai báo ở package specification và áp dụng cho các subprogram trong package:

~~~sql
CREATE OR REPLACE PACKAGE report_api
AUTHID CURRENT_USER
AS
    PROCEDURE open_report (
        p_result OUT SYS_REFCURSOR
    );
END report_api;
/
~~~

Không khai báo một AUTHID khác riêng cho từng procedure bên trong cùng package. Nếu hai API cần hai mô hình quyền khác nhau, có thể tách chúng thành các package hoặc standalone unit có ranh giới bảo mật rõ ràng.

## 2. Phân biệt SESSION_USER, CURRENT_USER và CURRENT_SCHEMA

Ba khái niệm này thường bị nhầm lẫn nhưng có ý nghĩa khác nhau.

| Giá trị | Ý nghĩa |
| --- | --- |
| SESSION_USER | Database user đã xác thực phiên đăng nhập |
| CURRENT_USER | User mà Oracle đang dùng làm ngữ cảnh quyền hiện tại |
| CURRENT_SCHEMA | Schema mặc định dùng để phân giải tên object chưa ghi owner |

Trong definer-rights unit, CURRENT_USER và CURRENT_SCHEMA được chuyển sang owner của unit trong thời gian unit chạy. SESSION_USER vẫn phản ánh user đã đăng nhập ban đầu.

Trong invoker-rights unit, CURRENT_USER và CURRENT_SCHEMA phản ánh ngữ cảnh của invoker hiện tại. CURRENT_SCHEMA có thể khác SESSION_USER nếu session đã chủ động thay đổi schema bằng ALTER SESSION SET CURRENT_SCHEMA.

### 2.1. Xem ngữ cảnh thực thi

Có thể kiểm tra bằng SYS_CONTEXT:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_USER')   AS current_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Đặt đoạn truy vấn này trong procedure hoặc function để quan sát ngữ cảnh khi code chạy.

### 2.2. Ví dụ procedure in ngữ cảnh

~~~sql
CREATE OR REPLACE PROCEDURE show_execution_context
AUTHID DEFINER
AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'SESSION_USER=' || SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_USER=' || SYS_CONTEXT('USERENV', 'CURRENT_USER')
    );
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_SCHEMA=' || SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
    );
END;
/
~~~

Nếu APP_USER gọi procedure thuộc API_OWNER, kết quả điển hình là SESSION_USER vẫn là APP_USER trong khi CURRENT_USER và CURRENT_SCHEMA trong phần code definer-rights là API_OWNER.

Nếu procedure được đổi thành AUTHID CURRENT_USER, CURRENT_USER chuyển theo invoker hiện tại. Đây là cách trực tiếp để kiểm chứng sự khác nhau giữa hai mô hình.

### 2.3. CURRENT_SCHEMA không phải quyền truy cập

ALTER SESSION SET CURRENT_SCHEMA = OTHER_SCHEMA chỉ thay schema mặc định khi phân giải tên object chưa ghi owner. Nó không cấp SELECT, INSERT, UPDATE, DELETE hoặc EXECUTE trên object của schema đó.

Ví dụ, đặt CURRENT_SCHEMA thành DATA_OWNER không có nghĩa user được phép đọc DATA_OWNER.PAYROLL. Vẫn phải có object privilege phù hợp trực tiếp hoặc qua role đang bật theo ngữ cảnh thực thi.

## 3. AUTHID DEFINER: chạy theo quyền owner

Definer-rights thường được dùng để xây dựng API dữ liệu. Owner của procedure được cấp quyền trên các bảng cần thiết, còn ứng dụng chỉ được EXECUTE API.

### 3.1. Mô hình ba schema

Ví dụ có ba user:

- DATA_OWNER sở hữu bảng nghiệp vụ.
- API_OWNER sở hữu procedure cung cấp API.
- APP_USER là tài khoản ứng dụng.

~~~text
DATA_OWNER
  |
  +-- PAYROLL
        ^
        | SELECT được cấp trực tiếp
        |
API_OWNER
  |
  +-- GET_EMPLOYEE_SALARY  (AUTHID DEFINER)
        ^
        | EXECUTE
        |
APP_USER
~~~

APP_USER không cần được cấp SELECT trên PAYROLL nếu chỉ cần lấy dữ liệu qua procedure và procedure được thiết kế an toàn.

### 3.2. Cấp quyền cho owner của API

DBA hoặc DATA_OWNER tạo bảng và cấp quyền trực tiếp cho API_OWNER:

~~~sql
CREATE TABLE payroll (
    employee_id NUMBER PRIMARY KEY,
    salary      NUMBER(12, 2)
);

GRANT SELECT ON payroll TO api_owner;
~~~

Nếu API_OWNER chỉ nhận quyền SELECT qua một role, quyền đó không đủ cho việc biên dịch static SQL trong stored PL/SQL. Hãy cấp trực tiếp object privilege cần thiết cho owner.

### 3.3. Tạo definer-rights procedure

Đăng nhập API_OWNER:

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_salary (
    p_employee_id IN NUMBER,
    p_salary      OUT NUMBER
)
AUTHID DEFINER
AS
BEGIN
    SELECT salary
    INTO p_salary
    FROM data_owner.payroll
    WHERE employee_id = p_employee_id;
END;
/
~~~

Procedure chạy câu SELECT bằng quyền của API_OWNER. Vì API_OWNER có direct SELECT trên DATA_OWNER.PAYROLL, unit có thể biên dịch và thực hiện truy vấn đó.

### 3.4. Chỉ cấp EXECUTE cho ứng dụng

DBA hoặc API_OWNER cấp:

~~~sql
GRANT EXECUTE ON get_employee_salary TO app_user;
~~~

APP_USER gọi procedure:

~~~sql
VARIABLE v_salary NUMBER
EXEC api_owner.get_employee_salary(101, :v_salary)
PRINT v_salary
~~~

Đây là cú pháp SQL*Plus/SQLcl. Ứng dụng JDBC hoặc .NET sẽ bind tham số OUT bằng API của driver.

APP_USER có thể gọi procedure mà không có SELECT trên PAYROLL. Procedure là ranh giới truy cập; do đó phải giới hạn tham số, hàng và cột mà API cho phép đọc.

### 3.5. Lợi ích và rủi ro

Lợi ích:

- Không phải cấp quyền bảng trực tiếp cho mọi ứng dụng.
- Có thể tập trung kiểm tra tenant, trạng thái nghiệp vụ và audit trong API.
- Có thể thay đổi bảng nội bộ mà không buộc client truy vấn trực tiếp.
- Có thể cung cấp thao tác có kiểm soát như tạo đơn, duyệt giao dịch hoặc đọc báo cáo.

Rủi ro:

- Procedure có thể trở thành đường nâng quyền nếu nhận tham số quá tự do.
- Dynamic SQL ghép chuỗi có thể cho phép SQL injection chạy bằng quyền owner.
- Một lỗi kiểm tra tenant hoặc quyền ở tầng API có thể làm lộ dữ liệu của nhiều người dùng.
- Owner có quyền quá rộng khiến mọi lỗi trong code có hậu quả lớn.

Definer-rights là một cơ chế xây dựng API có đặc quyền, không phải lý do để cấp DBA hoặc ANY privileges cho schema ứng dụng.

## 4. Quyền của role trong definer-rights unit

Khi một definer-rights unit chạy, các role thông thường được cấp cho user owner bị vô hiệu hóa trong ngữ cảnh unit. Các privilege cần cho static SQL phải được cấp trực tiếp cho owner.

Ví dụ:

~~~sql
CREATE ROLE payroll_reader;
GRANT SELECT ON data_owner.payroll TO payroll_reader;
GRANT payroll_reader TO api_owner;
~~~

Nếu API_OWNER chỉ có SELECT thông qua PAYROLL_READER, procedure tham chiếu PAYROLL có thể không biên dịch được. Cách xử lý là cấp direct grant:

~~~sql
GRANT SELECT ON data_owner.payroll TO api_owner;
~~~

Không nhầm lẫn:

- USER_ROLE_PRIVS cho biết role được cấp cho user.
- SESSION_ROLES cho biết role đang bật trong session hiện tại.
- Role được cấp cho user không đồng nghĩa role đó được sử dụng trong definer-rights unit.

### 4.1. Role được cấp trực tiếp cho PL/SQL unit (CBAC)

Oracle hỗ trợ Code Based Access Control (CBAC) trên các release có tính năng này. DBA có thể cấp role cho procedure, function hoặc package để privilege của role được dùng trong lúc unit chạy, thay vì cấp role đó cho toàn bộ user owner.

Ví dụ minh họa:

~~~sql
CREATE ROLE report_runtime_role;
GRANT SELECT ON data_owner.payroll TO report_runtime_role;

GRANT report_runtime_role
TO PROCEDURE api_owner.get_employee_salary;
~~~

Role gắn với unit tạo một ranh giới quyền hẹp hơn role gắn với cả schema. Tuy nhiên, privilege cần để biên dịch static SQL vẫn phải được cấp trực tiếp cho owner theo quy tắc compile-time. CBAC không thay thế việc đọc kỹ quyền biên dịch và quyền runtime.

Kiểm tra role được cấp cho code bằng các view dictionary phù hợp như DBA_CODE_ROLE_PRIVS hoặc USER_CODE_ROLE_PRIVS nếu phiên bản cung cấp.

## 5. AUTHID CURRENT_USER: chạy theo quyền invoker

Invoker-rights phù hợp khi một unit dùng chung cần thực hiện công việc trong phạm vi quyền của người gọi. Nó không làm caller tự động có thêm quyền; caller phải có quyền cần thiết cho câu lệnh được thực thi.

### 5.1. Ví dụ kiểm tra ngữ cảnh

~~~sql
CREATE OR REPLACE PROCEDURE show_invoker_context
AUTHID CURRENT_USER
AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'SESSION_USER=' || SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_USER=' || SYS_CONTEXT('USERENV', 'CURRENT_USER')
    );
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_SCHEMA=' || SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
    );
END;
/
~~~

Khi APP_USER gọi procedure, CURRENT_USER phản ánh invoker hiện tại. Trong một lời gọi trực tiếp thông thường, đó là APP_USER. Nếu lời gọi đi qua nhiều unit, invoker hiện tại có thể là owner của unit definer-rights gần nhất trong call chain; xem mục 8.

### 5.2. Quyền runtime thuộc về invoker

Giả sử procedure invoker-rights chạy SELECT trên DATA_OWNER.PAYROLL:

- APP_USER phải có SELECT trực tiếp hoặc thông qua role đang bật tại thời điểm gọi.
- API_OWNER cũng cần các quyền cần thiết để compile static SQL trong unit.
- APP_USER vẫn cần EXECUTE trên procedure.

Nếu APP_USER không có quyền truy cập PAYROLL, việc API_OWNER có SELECT không có nghĩa APP_USER được phép đọc qua AUTHID CURRENT_USER.

### 5.3. Khi nào nên dùng invoker-rights?

- Utility package dùng chung cho nhiều schema và cần tôn trọng quyền của caller.
- Framework chạy câu lệnh trên object thuộc schema hiện tại của caller.
- API cần sử dụng quyền của người dùng cuối thay vì quyền rộng của owner.
- Một số thư viện PL/SQL dùng dynamic SQL để thao tác object được caller cung cấp trong phạm vi quyền của caller.

Không chọn CURRENT_USER chỉ vì muốn code “linh hoạt”. Nếu mục tiêu là cung cấp một thao tác dữ liệu có kiểm soát qua API, definer-rights có thể phù hợp hơn.

## 6. INHERIT PRIVILEGES và ORA-06598

Từ Oracle Database 12c, cơ chế INHERIT PRIVILEGES kiểm soát việc owner của invoker-rights unit có được phép kế thừa quyền của invoker hay không.

Khi một invoker-rights unit chạy, Oracle cần xác định rằng owner của unit được phép thực thi code trong ngữ cảnh privilege của invoker. Nếu thiếu quyền này, lời gọi có thể thất bại với:

~~~text
ORA-06598: insufficient INHERIT PRIVILEGES privilege
~~~

### 6.1. Cấp quyền cho owner của invoker-rights unit

Ví dụ APP_USER gọi unit thuộc API_OWNER:

~~~sql
GRANT INHERIT PRIVILEGES ON USER app_user TO api_owner;
~~~

Lệnh này cấp cho API_OWNER quyền inherit privilege của APP_USER trong ngữ cảnh invoker-rights. Nó không cấp cho APP_USER quyền SELECT trên bảng và cũng không cấp EXECUTE trên procedure.

### 6.2. Giới hạn PUBLIC grant

Trong các môi trường Oracle có mặc định cấp INHERIT PRIVILEGES cho PUBLIC trên user, DBA có thể thu hẹp phạm vi rồi cấp riêng cho code owner cần thiết:

~~~sql
REVOKE INHERIT PRIVILEGES ON USER app_user FROM PUBLIC;
GRANT INHERIT PRIVILEGES ON USER app_user TO api_owner;
~~~

Hãy xác nhận grant thực tế của database và chính sách bảo mật trước khi thay đổi. Nếu nhiều invoker gọi cùng unit, mỗi user cần được xem xét theo chính sách tương ứng.

### 6.3. INHERIT ANY PRIVILEGES

INHERIT ANY PRIVILEGES cho phép user kế thừa quyền của nhiều user khác và có phạm vi rộng. Không cấp privilege này như một cách sửa nhanh ORA-06598. Ưu tiên grant INHERIT PRIVILEGES trên đúng user cho đúng owner.

### 6.4. Kiểm tra quyền INHERIT

DBA có thể kiểm tra object grants liên quan:

~~~sql
SELECT
    grantee,
    owner,
    table_name,
    privilege,
    grantor
FROM dba_tab_privs
WHERE privilege = 'INHERIT PRIVILEGES'
  AND table_name = UPPER('APP_USER')
ORDER BY grantee;
~~~

Tên hiển thị và metadata có thể khác theo release/kiểu grant; đối chiếu DBA_TAB_PRIVS và tài liệu Reference đúng phiên bản nếu truy vấn không trả kết quả như dự kiến.

## 7. Compile-time và runtime privilege checks

Đây là điểm quan trọng khi debug lỗi quyền: Oracle kiểm tra quyền ở các giai đoạn khác nhau.

### 7.1. Khi compile static SQL

Stored PL/SQL cần phân giải tên object và kiểm tra privilege để biên dịch câu SQL tĩnh. Các object privilege cần cho việc compile phải được cấp trực tiếp cho owner của unit; quyền chỉ đến từ role của owner không đủ.

Ví dụ API_OWNER biên dịch procedure có câu:

~~~sql
SELECT salary
INTO p_salary
FROM data_owner.payroll
WHERE employee_id = p_employee_id;
~~~

API_OWNER cần direct SELECT trên DATA_OWNER.PAYROLL để compile unit. Việc API_OWNER có role PAYROLL_READER không thay thế direct grant này.

### 7.2. Khi chạy AUTHID DEFINER

Oracle kiểm tra quyền runtime theo owner của unit. Role thông thường của user owner bị vô hiệu hóa trong definer-rights context; privilege trực tiếp của owner được dùng. Các role được cấp trực tiếp cho PL/SQL unit theo CBAC là cơ chế riêng nếu được cấu hình.

Caller cần EXECUTE trên unit, nhưng không nhất thiết cần quyền trên từng bảng mà definer unit truy cập.

### 7.3. Khi chạy AUTHID CURRENT_USER

Oracle kiểm tra quyền runtime theo invoker hiện tại. Các role đang bật trong ngữ cảnh invoker có thể tham gia kiểm tra quyền. Invoker cần privilege trên object được truy cập và cần được phép gọi unit.

Owner của unit vẫn phải đáp ứng yêu cầu compile-time đối với static SQL. Do đó, “runtime chạy theo invoker” không có nghĩa owner có thể compile một static query tham chiếu object hoàn toàn không tồn tại hoặc không có privilege cần thiết.

### 7.4. Dynamic SQL được kiểm tra khi chạy

Dynamic SQL được parse/execute tại runtime. Vì vậy quyền truy cập cho câu SQL động được kiểm tra theo ngữ cảnh AUTHID đang hoạt động:

- Definer-rights: quyền của owner, role thông thường của owner bị tắt.
- Invoker-rights: quyền của invoker, gồm role đang bật trong ngữ cảnh đó.

Đây là khác biệt quan trọng khi một unit dùng EXECUTE IMMEDIATE hoặc OPEN FOR với chuỗi SQL.

### 7.5. Bảng tổng hợp

| Giai đoạn | AUTHID DEFINER | AUTHID CURRENT_USER |
| --- | --- | --- |
| Người gọi cần EXECUTE unit | Có | Có |
| Compile static SQL | Owner cần quyền trực tiếp phù hợp | Owner cần quyền trực tiếp phù hợp |
| Runtime privilege check | Owner của unit | Invoker hiện tại |
| Role thông thường của owner | Bị tắt trong unit | Không phải nguồn quyền runtime của invoker |
| Role đang bật của invoker | Không dùng cho SQL trong unit | Có thể dùng |
| Dynamic SQL | Kiểm tra theo owner context | Kiểm tra theo invoker context |
| INHERIT PRIVILEGES | Không phải yêu cầu riêng của definer unit | Cần quyền inherit phù hợp trên invoker |

## 8. Quyền trong chuỗi gọi PL/SQL

Khi một unit gọi unit khác, ngữ cảnh AUTHID được áp dụng theo từng bước. CURRENT_USER của unit invoker-rights là invoker hiện tại tại thời điểm unit đó được gọi, không nhất thiết luôn là SESSION_USER ban đầu.

~~~text
APP_USER (SESSION_USER)
   |
   v
APP_OWNER.CLIENT_ENTRY
   AUTHID DEFINER
   CURRENT_USER = APP_OWNER
   |
   v
SHARED_OWNER.UTILITY
   AUTHID CURRENT_USER
   CURRENT_USER = APP_OWNER
   |
   v
DATA_OWNER.DATA_API
   AUTHID DEFINER
   CURRENT_USER = DATA_OWNER
~~~

Sơ đồ minh họa nguyên tắc chuyển ngữ cảnh: khi code definer-rights chạy, quyền chuyển sang owner; khi gọi invoker-rights unit từ trong ngữ cảnh đó, invoker của unit mới là current user đang có tại thời điểm gọi. Khi unit kết thúc, Oracle khôi phục ngữ cảnh của caller.

### 8.1. Vì sao call chain quan trọng?

Giả sử APP_USER gọi một procedure definer-rights của APP_OWNER, procedure này lại gọi utility invoker-rights của SHARED_OWNER. Utility không nhất thiết chạy theo APP_USER ban đầu; nó có thể chạy theo APP_OWNER vì APP_OWNER là current user tại thời điểm gọi.

Khi điều tra quyền, hãy vẽ call chain và xác định:

1. Unit nào đang chạy?
2. AUTHID của unit đó là gì?
3. Ai là CURRENT_USER ngay trước khi gọi unit?
4. Owner unit có INHERIT PRIVILEGES trên invoker đó không?
5. Quyền object nào cần ở compile-time và runtime?

Đừng chỉ nhìn SESSION_USER rồi kết luận đó là user dùng để kiểm tra mọi câu SQL trong call chain.

## 9. Name resolution và dynamic SQL

AUTHID cũng ảnh hưởng schema context dùng để phân giải tên object chưa ghi owner. Với definer-rights unit, CURRENT_SCHEMA trong unit là schema owner. Với invoker-rights unit, CURRENT_SCHEMA theo ngữ cảnh invoker.

### 9.1. Static SQL và dynamic SQL

Static SQL được phân tích khi compile unit và tạo dependency metadata. Dynamic SQL được parse khi chạy, nên có thể sử dụng tên object được xác định theo runtime context.

Ví dụ invoker-rights utility truy cập bảng có cùng tên trong schema caller:

~~~sql
CREATE OR REPLACE PROCEDURE open_my_items (
    p_status IN VARCHAR2,
    p_result OUT SYS_REFCURSOR
)
AUTHID CURRENT_USER
AS
BEGIN
    OPEN p_result FOR
        'SELECT item_id, item_name ' ||
        'FROM caller_items ' ||
        'WHERE status = :status ' ||
        'ORDER BY item_id'
    USING p_status;
END;
/
~~~

Nếu APP_USER gọi procedure và CURRENT_SCHEMA trong ngữ cảnh là APP_USER, tên chưa qualify CALLER_ITEMS được phân giải trong schema hiện tại của invoker. APP_USER phải có quyền cần thiết trên bảng đó. Vì câu query là dynamic SQL, object không bị hard-code thành một dependency static của procedure.

Đây là một mẫu nâng cao. Hãy thử nghiệm với schema thực tế, synonym và CURRENT_SCHEMA trước khi sử dụng. Nếu caller đã thay CURRENT_SCHEMA bằng ALTER SESSION, tên unqualified có thể được phân giải ở schema đó.

### 9.2. Bind variable cho dữ liệu

Luôn bind giá trị thay vì ghép chuỗi:

~~~sql
OPEN p_result FOR
    'SELECT item_id, item_name FROM caller_items WHERE status = :s'
USING p_status;
~~~

Bind variables giúp tránh SQL injection cho giá trị và cho phép Oracle tái sử dụng cursor hiệu quả hơn.

### 9.3. Identifier không thể bind

Bind variable không thể thay tên bảng, tên cột hoặc từ khóa SQL. Nếu API cần lựa chọn sort column, dùng whitelist:

~~~sql
IF p_sort = 'NAME' THEN
    l_order_by := 'item_name';
ELSIF p_sort = 'DATE' THEN
    l_order_by := 'created_at';
ELSE
    RAISE_APPLICATION_ERROR(-20001, 'Unsupported sort column');
END IF;

l_sql := 'SELECT item_id, item_name FROM caller_items ORDER BY '
         || l_order_by;

OPEN p_result FOR l_sql;
~~~

Chỉ ghép identifier lấy từ danh sách cố định do code kiểm soát. DBMS_ASSERT có thể hỗ trợ xác thực cú pháp identifier trong một số trường hợp nhưng không thay thế whitelist, kiểm tra quyền và xác thực nghiệp vụ.

### 9.4. Rủi ro SQL injection trong definer-rights

Nếu definer-rights procedure nhận chuỗi SQL tùy ý và thực thi bằng quyền owner, caller có thể khiến code thao tác trên object mà caller không được phép truy cập trực tiếp.

Không xây dựng API như:

~~~sql
EXECUTE IMMEDIATE p_sql_text;
~~~

trừ khi đây là công cụ quản trị có kiểm soát đặc biệt và caller được xác thực, phân quyền chặt chẽ. Trong API ứng dụng, hãy cố định cấu trúc SQL, bind giá trị và whitelist mọi lựa chọn identifier.

## 10. Kiểm tra AUTHID trong data dictionary

Không nên suy luận AUTHID chỉ từ tên procedure hoặc schema owner. Có thể xem metadata của các stored subprogram.

### 10.1. ALL_PROCEDURES

~~~sql
SELECT
    owner,
    object_name,
    procedure_name,
    authid
FROM all_procedures
WHERE owner = UPPER(:owner)
  AND object_name = UPPER(:object_name)
ORDER BY procedure_name;
~~~

Các giá trị AUTHID thường biểu diễn DEFINER hoặc CURRENT_USER. Với package, kiểm tra các subprogram thuộc package và đối chiếu package specification. Quyền xem metadata phụ thuộc quyền truy cập của session.

### 10.2. USER_SOURCE

Nếu cần xác nhận source:

~~~sql
SELECT line, text
FROM user_source
WHERE name = UPPER(:object_name)
  AND type IN ('PROCEDURE', 'FUNCTION', 'PACKAGE')
ORDER BY type, line;
~~~

Với package, AUTHID thường được khai báo ở specification. Đừng tìm một AUTHID riêng trong package body rồi kết luận body có quyền khác specification.

## 11. Kiểm tra quyền đang có hiệu lực

Quyền được cấp, quyền đang bật và quyền cần cho một thao tác là ba khái niệm khác nhau.

### 11.1. Role được cấp và role đang bật

~~~sql
SELECT role
FROM user_role_privs
ORDER BY role;

SELECT role
FROM session_roles
ORDER BY role;
~~~

USER_ROLE_PRIVS cho biết role được cấp cho user. SESSION_ROLES cho biết role đang bật trong session hiện tại. Khi kiểm tra quyền của invoker-rights unit, cần xét các role đang bật tại thời điểm unit chạy.

### 11.2. System privileges đang có hiệu lực

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

SESSION_PRIVS cho biết system privilege có hiệu lực trong session. Không dùng nó để kết luận toàn bộ object privilege trên một bảng cụ thể.

### 11.3. Object privilege

Với quyền trên bảng/view:

~~~sql
SELECT
    owner,
    table_name,
    privilege,
    grantor,
    grantee
FROM all_tab_privs
WHERE table_name = UPPER(:table_name)
ORDER BY owner, grantee, privilege;
~~~

DBA có thể dùng DBA_TAB_PRIVS để xem phạm vi rộng hơn. Cần phân biệt grantee là user hay role; nếu quyền được cấp cho role, kiểm tra tiếp role đó có đang bật trong session hay không.

### 11.4. Quyền EXECUTE trên API

Kiểm tra ai được cấp quyền trên procedure/package:

~~~sql
SELECT
    owner,
    table_name,
    grantee,
    privilege,
    grantable
FROM all_tab_privs
WHERE owner = UPPER(:api_owner)
  AND table_name = UPPER(:api_name)
  AND privilege = 'EXECUTE'
ORDER BY grantee;
~~~

Một user có quyền trên bảng không đồng nghĩa user có quyền gọi procedure; ngược lại, có EXECUTE trên procedure cũng không tự tạo quyền trực tiếp trên mọi bảng mà procedure dùng.

## 12. So sánh lựa chọn AUTHID trong thiết kế

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| API đọc dữ liệu qua một interface đã kiểm soát | DEFINER | Caller chỉ cần EXECUTE, API dùng quyền owner |
| API cập nhật nghiệp vụ có validation và audit tập trung | DEFINER | Owner thực hiện DML trong phạm vi code được kiểm soát |
| Utility truy cập object của schema caller | CURRENT_USER | Tôn trọng quyền và schema của invoker |
| Framework thực thi thao tác theo quyền từng user | CURRENT_USER | Không dùng quyền rộng của owner thay cho caller |
| Package tiện ích dùng chung nhưng cần privilege riêng của unit | Đánh giá CURRENT_USER hoặc CBAC | Phụ thuộc ai nên sở hữu quyền runtime |
| Công cụ chạy SQL tùy ý | Không mở API rộng; thiết kế lại | Nguy cơ SQL injection và nâng quyền rất cao |

Không có một AUTHID tốt cho mọi package. Quyết định dựa trên ranh giới tin cậy: ai được phép gọi, dữ liệu nào được phép truy cập và ai chịu trách nhiệm cho privilege runtime.

## 13. Lab: kiểm chứng definer và invoker rights

Lab cần ba schema: DATA_OWNER, API_OWNER và APP_USER. DBA tạo user, tablespace/quota và quyền CREATE SESSION/CREATE TABLE/CREATE PROCEDURE phù hợp. Dùng mật khẩu theo chính sách lab; không dùng mật khẩu mẫu trong production.

### 13.1. Tạo dữ liệu

Đăng nhập DATA_OWNER:

~~~sql
CREATE TABLE lab_payroll (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80),
    salary NUMBER(12, 2)
);

INSERT INTO lab_payroll VALUES (101, 'An', 2500);
INSERT INTO lab_payroll VALUES (102, 'Binh', 3200);
COMMIT;

GRANT SELECT ON lab_payroll TO api_owner;
~~~

### 13.2. Tạo definer-rights API

Đăng nhập API_OWNER:

~~~sql
CREATE OR REPLACE PROCEDURE lab_get_salary (
    p_employee_id IN NUMBER,
    p_salary OUT NUMBER
)
AUTHID DEFINER
AS
BEGIN
    SELECT salary
    INTO p_salary
    FROM data_owner.lab_payroll
    WHERE employee_id = p_employee_id;
END;
/

GRANT EXECUTE ON lab_get_salary TO app_user;
~~~

Đăng nhập APP_USER và gọi:

~~~sql
VARIABLE v_salary NUMBER
EXEC api_owner.lab_get_salary(101, :v_salary)
PRINT v_salary
~~~

APP_USER nhận được salary dù không có SELECT trên DATA_OWNER.LAB_PAYROLL. Hãy thử SELECT trực tiếp bảng để quan sát sự khác nhau về quyền.

### 13.3. Tạo invoker-rights API

Đăng nhập API_OWNER:

~~~sql
CREATE OR REPLACE PROCEDURE lab_check_payroll_access (
    p_result OUT SYS_REFCURSOR
)
AUTHID CURRENT_USER
AS
BEGIN
    OPEN p_result FOR
        SELECT employee_id, employee_name, salary
        FROM data_owner.lab_payroll
        ORDER BY employee_id;
END;
/

GRANT EXECUTE ON lab_check_payroll_access TO app_user;
~~~

Nếu APP_USER chưa có SELECT trên DATA_OWNER.LAB_PAYROLL, gọi procedure sẽ thất bại ở runtime do thiếu quyền invoker. DBA hoặc DATA_OWNER có thể cấp:

~~~sql
GRANT SELECT ON lab_payroll TO app_user;
~~~

Sau đó gọi lại procedure bằng client hỗ trợ SYS_REFCURSOR. APP_USER có thể đọc dữ liệu vì chính invoker có quyền SELECT.

### 13.4. Kiểm tra INHERIT PRIVILEGES

Nếu môi trường đã thu hồi grant từ PUBLIC hoặc policy yêu cầu grant tường minh, cấp:

~~~sql
GRANT INHERIT PRIVILEGES ON USER app_user TO api_owner;
~~~

Thử thu hồi grant phù hợp trong môi trường lab để quan sát lỗi ORA-06598, sau đó cấp lại. Không thử thay đổi privilege trên user production.

### 13.5. Quan sát CURRENT_USER

Tạo procedure hiển thị context với cả AUTHID DEFINER và AUTHID CURRENT_USER. Gọi từ APP_USER và so sánh SESSION_USER, CURRENT_USER, CURRENT_SCHEMA.

### 13.6. Kiểm tra role không thay direct grant khi compile

Tạo role có SELECT trên LAB_PAYROLL, cấp role cho API_OWNER, rồi thử compile một procedure static SQL khi API_OWNER không có direct SELECT. Quan sát lỗi compile. Cấp direct SELECT cho API_OWNER và compile lại.

Lab này cho thấy compile-time privilege check và runtime privilege check là hai bước khác nhau.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Procedure không ghi AUTHID nhưng chạy bằng quyền owner | DEFINER là mặc định | Ghi rõ AUTHID khi muốn thể hiện chủ ý |
| APP_USER không SELECT được bảng nhưng procedure vẫn đọc được | Procedure là definer-rights và owner có quyền | Kiểm tra API có giới hạn dữ liệu đúng không |
| Procedure compile lỗi dù role có SELECT | Role của owner không thay direct grant khi compile static SQL | GRANT object privilege trực tiếp cho owner |
| Invoker-rights procedure báo thiếu quyền | Invoker không có privilege runtime trên object | Cấp quyền tối thiểu cho invoker hoặc thiết kế lại API |
| ORA-06598 | Owner của invoker-rights unit không được phép inherit privilege của invoker | Cấp INHERIT PRIVILEGES đúng user cho đúng owner |
| Đã GRANT EXECUTE nhưng vẫn lỗi SELECT | EXECUTE trên unit không đồng nghĩa quyền truy cập object runtime | Xác định AUTHID và kiểm tra privilege đúng ngữ cảnh |
| CURRENT_SCHEMA đổi nhưng vẫn bị từ chối truy cập | CURRENT_SCHEMA chỉ ảnh hưởng name resolution | Cấp object privilege phù hợp |
| Session role có quyền nhưng definer unit không dùng được | Role thông thường bị tắt trong definer-rights context | Direct grant hoặc đánh giá CBAC |
| Procedure qua call chain dùng sai quyền dự kiến | CURRENT_USER đổi theo unit đang chạy | Vẽ call chain và kiểm tra AUTHID từng unit |
| Dynamic SQL có thể truy cập bảng ngoài ý định | Ghép identifier hoặc SQL text không kiểm soát | Bind value, whitelist identifier và giới hạn quyền |
| Caller thấy kết quả của tenant khác | Definer API thiếu filter/authorization theo tenant | Xác thực tenant/user trong API và audit |
| AUTHID package không đúng mong đợi | AUTHID thuộc package specification, áp dụng cho các subprogram | Kiểm tra package spec và metadata |
| Tăng INHERIT ANY PRIVILEGES để sửa nhanh | Cấp quyền inherit quá rộng | Dùng INHERIT PRIVILEGES trên đúng user |

## 15. Checklist kiểm tra quyền khi procedure lỗi

Khi một procedure/package gặp ORA-01031, ORA-00942, ORA-06598 hoặc lỗi compile liên quan privilege, đi theo thứ tự:

1. Xác định owner, object type và AUTHID thực tế.
2. Xác định SESSION_USER, CURRENT_USER và CURRENT_SCHEMA tại điểm lỗi.
3. Xác nhận caller có EXECUTE trên procedure/package.
4. Xác định câu SQL gây lỗi là static SQL hay dynamic SQL.
5. Nếu lỗi compile static SQL, kiểm tra direct grant cho owner.
6. Nếu runtime definer-rights, kiểm tra privilege của owner và role gắn trực tiếp với code nếu có CBAC.
7. Nếu runtime invoker-rights, kiểm tra direct/object privilege và role đang bật của invoker.
8. Kiểm tra INHERIT PRIVILEGES trên invoker.
9. Kiểm tra synonym, CURRENT_SCHEMA và owner thực của object.
10. Kiểm tra call chain nếu procedure được gọi gián tiếp.
11. Kiểm tra SQL injection hoặc tham số identifier nếu có dynamic SQL.
12. Cấp quyền tối thiểu và thử lại bằng đúng user/role của ứng dụng.

Không sửa lỗi bằng cách cấp SELECT ANY TABLE, EXECUTE ANY PROCEDURE hoặc INHERIT ANY PRIVILEGES nếu chưa có phân tích quyền cần thiết. Những quyền rộng này có thể làm tăng đáng kể phạm vi truy cập của code.

## 16. Bài tập thực hành

Sử dụng lab ba schema ở mục 13.

### Bài 1 — So sánh context

Tạo hai procedure giống nhau, một AUTHID DEFINER và một AUTHID CURRENT_USER. Gọi từ APP_USER, ghi SESSION_USER, CURRENT_USER và CURRENT_SCHEMA. Giải thích kết quả.

### Bài 2 — Direct grant và role

Cấp SELECT trên LAB_PAYROLL cho một role rồi cấp role cho API_OWNER. Thử compile static SQL. Sau đó cấp SELECT trực tiếp cho API_OWNER và compile lại. Giải thích tại sao hai trường hợp khác nhau.

### Bài 3 — Runtime invoker privilege

Tạo procedure AUTHID CURRENT_USER truy cập DATA_OWNER.LAB_PAYROLL. Gọi khi APP_USER chưa có SELECT rồi cấp SELECT cho APP_USER và gọi lại. Phân biệt lỗi compile với lỗi runtime.

### Bài 4 — INHERIT PRIVILEGES

Trong môi trường lab, kiểm tra grant INHERIT PRIVILEGES. Thu hồi grant từ PUBLIC nếu policy lab cho phép, cấp riêng cho API_OWNER và quan sát kết quả. Ghi lại tình huống tạo ORA-06598.

### Bài 5 — Call chain

Tạo một definer-rights procedure gọi invoker-rights utility. Gọi từ APP_USER và quan sát CURRENT_USER trong utility. Thay đổi thứ tự AUTHID và so sánh.

### Bài 6 — Dynamic SQL

Viết invoker-rights procedure mở cursor trên bảng CALLER_ITEMS trong schema caller. Dùng bind variable cho status. Kiểm tra tên object được phân giải theo CURRENT_SCHEMA.

### Bài 7 — SQL injection

Thử một input có dấu nháy trong giá trị tìm kiếm. So sánh query dùng bind variable với query ghép chuỗi. Không chạy payload phá hoại; mục tiêu là hiểu vì sao bind giữ input ở dạng dữ liệu.

### Bài 8 — Kiểm tra metadata

Dùng ALL_PROCEDURES, SESSION_ROLES, SESSION_PRIVS và ALL_TAB_PRIVS để lập bảng quyền của API_OWNER và APP_USER. Phân biệt quyền được cấp, quyền đang bật, quyền compile và quyền runtime.

## 17. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập và xác nhận không còn phụ thuộc:

~~~sql
DROP PROCEDURE lab_check_payroll_access;
DROP PROCEDURE lab_get_salary;
DROP TABLE lab_payroll PURGE;
~~~

Thu hồi các grant, role và INHERIT PRIVILEGES đã cấp trong lab theo đúng user/owner trước khi xóa schema lab. Không chạy các lệnh dọn dẹp trên object nghiệp vụ.

## Tổng kết

AUTHID DEFINER chạy theo quyền của owner và là mặc định của named PL/SQL unit. Nó phù hợp để tạo API có đặc quyền nhưng đòi hỏi direct grants cho compile-time static SQL, kiểm soát chặt EXECUTE và bảo vệ mọi dynamic SQL. AUTHID CURRENT_USER chạy theo quyền của invoker hiện tại, có thể sử dụng role đang bật của invoker và cần INHERIT PRIVILEGES phù hợp trên invoker.

SESSION_USER là user đăng nhập; CURRENT_USER là user dùng cho privilege check tại thời điểm code chạy; CURRENT_SCHEMA điều khiển name resolution cho tên chưa qualify. Ba giá trị có thể khác nhau trong call chain. Khi debug, phải tách compile-time khỏi runtime, static SQL khỏi dynamic SQL, và quyền EXECUTE khỏi quyền trên object dữ liệu. Thiết kế an toàn bắt đầu từ quyền tối thiểu, API có contract rõ, bind variables, whitelist identifier và kiểm thử bằng đúng user/role mà ứng dụng sử dụng.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — Invoker's Rights and Definer's Rights (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html) — AUTHID, runtime identity và privilege model.
- [Oracle Database Security Guide — Using Invoker's Rights and Definer's Rights (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-security-for-definers-rights-and-invokers-rights.html) — bảo mật stored PL/SQL.
- [Oracle Database Security Guide — Inherit Privileges (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-security-for-definers-rights-and-invokers-rights.html) — INHERIT PRIVILEGES và kiểm soát invoker rights.
- [Oracle Database Security Guide — Code Based Access Control (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-privilege-and-role-authorization.html) — role được cấp cho PL/SQL program unit.
- [Oracle Database Reference — ALL_PROCEDURES (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_PROCEDURES.html) — metadata procedure và AUTHID.
- [Oracle Database Reference — SESSION_ROLES (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/SESSION_ROLES.html) — role đang bật trong session.
- [Oracle Database Reference — SESSION_PRIVS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/SESSION_PRIVS.html) — system privilege đang có hiệu lực.
- [Oracle Database SQL Language Reference — GRANT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/GRANT.html) — cấp object privilege, role và INHERIT PRIVILEGES.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu PL/SQL Language Reference, Security Guide và Reference đúng phiên bản, đặc biệt quy tắc INHERIT PRIVILEGES, CBAC, role trong definer-rights unit và metadata AUTHID.
