# Quyền EXECUTE, quyền trực tiếp và vai trò khi biên dịch PL/SQL

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Thủ tục và package  
> **Mục tiêu:** Hiểu mô hình quyền của procedure, function và package trong Oracle; phân biệt quyền tạo program unit, quyền truy cập object được tham chiếu và quyền EXECUTE dành cho caller; giải thích vì sao quyền qua role thường không đủ để biên dịch stored PL/SQL; phân biệt AUTHID DEFINER với AUTHID CURRENT_USER; nhận diện ảnh hưởng của static SQL, dynamic SQL, role, chuỗi gọi lồng nhau và INHERIT PRIVILEGES; biết cách chẩn đoán lỗi compile/runtime và triển khai theo nguyên tắc least privilege.

## 1. Một procedure chạy được cần những quyền nào?

Một stored procedure có thể được tạo bởi một schema, truy cập bảng của schema khác và được ứng dụng gọi từ một tài khoản riêng. Ba hành động này là ba lớp quyền khác nhau:

1. **Quyền tạo program unit:** cho phép schema tạo procedure, function hoặc package.
2. **Quyền của program unit trên object được tham chiếu:** cho phép mã PL/SQL đọc/ghi bảng, gọi package hoặc sử dụng sequence.
3. **Quyền EXECUTE của caller:** cho phép người dùng hoặc role gọi procedure/function/package.

Ví dụ, APP_CODE sở hữu package CUSTOMER_API, package đọc bảng DATA_OWNER.CUSTOMERS, còn ứng dụng kết nối bằng APP_RUNTIME:

~~~text
APP_RUNTIME (tài khoản ứng dụng)
       |
       | EXECUTE
       v
APP_CODE.CUSTOMER_API (package)
       |
       | SELECT theo security model của package
       v
DATA_OWNER.CUSTOMERS (bảng nguồn)
~~~

Cần cấp đúng quyền trên từng đường đi. Việc APP_RUNTIME có quyền SELECT bảng không tự động làm package của APP_CODE biên dịch được. Ngược lại, APP_CODE có quyền SELECT bảng cũng không có nghĩa APP_RUNTIME được phép gọi package.

Một lỗi thiết kế phổ biến là cấp một role có nhiều quyền cho schema sở hữu code rồi mong stored procedure tự sử dụng tất cả các quyền đó. Stored PL/SQL có quy tắc role riêng, đặc biệt với definer-rights unit.

## 2. Quyền tạo procedure, function và package

Để tạo program unit trong schema của chính mình, tài khoản thường cần system privilege phù hợp:

- CREATE PROCEDURE: tạo procedure, function và package trong schema của mình.
- CREATE ANY PROCEDURE: tạo hoặc thay đổi program unit trong schema khác; đây là quyền rộng và cần hạn chế.
- CREATE SESSION: cho phép kết nối database, không thay thế CREATE PROCEDURE.
- Các quyền bổ sung có thể cần tùy object và thao tác cụ thể.

Ví dụ DBA cấp quyền tạo code cho schema ứng dụng:

~~~sql
GRANT CREATE SESSION TO app_code;
GRANT CREATE PROCEDURE TO app_code;
~~~

APP_CODE sau đó có thể tạo procedure trong schema của mình:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.hello_api IS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from APP_CODE');
END;
/
~~~

Nếu đang kết nối bằng APP_CODE, có thể bỏ prefix schema:

~~~sql
CREATE OR REPLACE PROCEDURE hello_api IS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END;
/
~~~

Không cấp CREATE ANY PROCEDURE cho tài khoản ứng dụng chỉ để giải quyết một lỗi compile trong schema riêng. Hãy xác định đúng owner và cấp quyền tối thiểu cần thiết.

### 2.1. Quyền tạo code khác quyền gọi code

Một user có CREATE PROCEDURE không mặc nhiên có quyền EXECUTE mọi procedure trong database. Tương tự, user có EXECUTE trên một package không mặc nhiên được tạo package mới.

Đây là hai hành động độc lập:

~~~sql
GRANT CREATE PROCEDURE TO app_code;

GRANT EXECUTE ON app_code.customer_api TO app_runtime;
~~~

Lệnh đầu cấp quyền tạo program unit cho APP_CODE. Lệnh thứ hai cho APP_RUNTIME gọi package CUSTOMER_API.

## 3. Quyền truy cập object được tham chiếu trong PL/SQL

Giả sử DATA_OWNER sở hữu bảng CUSTOMERS:

~~~sql
CREATE TABLE data_owner.customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL,
    status VARCHAR2(20) NOT NULL
);
~~~

APP_CODE cần tạo procedure đọc bảng đó:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.list_customers IS
BEGIN
    FOR r IN (
        SELECT customer_id, customer_name
        FROM data_owner.customers
        ORDER BY customer_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.customer_id || ': ' || r.customer_name
        );
    END LOOP;
END;
/
~~~

Với procedure mặc định dùng AUTHID DEFINER, APP_CODE cần quyền truy cập trực tiếp thích hợp trên DATA_OWNER.CUSTOMERS để static SQL được biên dịch và để procedure thực thi theo quyền của owner.

DBA hoặc DATA_OWNER cấp trực tiếp:

~~~sql
GRANT SELECT ON data_owner.customers TO app_code;
~~~

Sau đó APP_CODE biên dịch procedure.

Nếu procedure cần INSERT:

~~~sql
GRANT INSERT ON data_owner.customers TO app_code;
~~~

Nếu cần UPDATE một số cột:

~~~sql
GRANT UPDATE (status) ON data_owner.customers TO app_code;
~~~

Nếu cần DELETE:

~~~sql
GRANT DELETE ON data_owner.customers TO app_code;
~~~

Cấp đúng object privilege theo thao tác thực tế. Không cấp SELECT/INSERT/UPDATE/DELETE toàn bộ chỉ vì muốn tránh lỗi compile.

### 3.1. Quyền trực tiếp và quyền qua role

Xét tình huống:

~~~sql
CREATE ROLE r_customer_reader;

GRANT SELECT ON data_owner.customers TO r_customer_reader;
GRANT r_customer_reader TO app_code;
~~~

APP_CODE có thể thấy role được cấp trong metadata/session theo cấu hình, nhưng role này không thay thế direct object grant cần cho việc biên dịch static SQL của stored definer-rights PL/SQL.

Đối với definer-rights unit, các role được cấp cho user bị vô hiệu hóa trong thời gian unit thực thi. Vì vậy procedure không thể dựa vào quyền SELECT chỉ đến từ role của APP_CODE.

Cách sửa đúng cho procedure cần SELECT bảng nguồn:

~~~sql
GRANT SELECT ON data_owner.customers TO app_code;
~~~

Đây là direct grant đến schema owner.

### 3.2. Vì sao SQL chạy trực tiếp nhưng procedure lại compile lỗi?

Một user có thể chạy câu SELECT trong worksheet thành công nhờ role:

~~~sql
SELECT customer_id, customer_name
FROM data_owner.customers;
~~~

Nhưng khi đưa cùng câu SQL vào stored procedure, compiler kiểm tra quyền trong ngữ cảnh biên dịch stored unit. Role không được dùng như một direct grant để đáp ứng yêu cầu biên dịch.

Do đó có thể gặp tình huống:

- SELECT trực tiếp thành công.
- CREATE PROCEDURE hoặc ALTER PROCEDURE báo lỗi.
- USER_ERRORS ghi nhận lỗi biên dịch, chẳng hạn ORA-00942 hoặc PLS-00201 tùy cách tham chiếu và ngữ cảnh.

Không kết luận rằng bảng không tồn tại chỉ từ ORA-00942. Kiểm tra owner, object name, synonym và quyền trực tiếp của schema biên dịch.

## 4. Static SQL và dynamic SQL: thời điểm kiểm tra quyền

Quyền truy cập object còn phụ thuộc câu SQL được viết trực tiếp trong PL/SQL hay được tạo thành chuỗi và thực thi lúc runtime.

### 4.1. Static SQL

Static SQL được viết trực tiếp trong source code:

~~~sql
SELECT customer_name
INTO l_customer_name
FROM data_owner.customers
WHERE customer_id = p_customer_id;
~~~

Oracle phân tích, resolve tên và kiểm tra quyền khi biên dịch. Static SQL cũng được kiểm tra quyền khi thực thi theo security domain đang có hiệu lực.

Với definer-rights unit, owner phải có quyền phù hợp trên object. Role không cung cấp quyền cho bước compile static SQL.

Với invoker-rights unit, cần chú ý quy tắc template object: static SQL phải resolve được object tương ứng trong schema owner lúc compile và trong schema invoker lúc runtime đối với external reference được resolve theo invoker. Hai object tương ứng phải có cấu trúc tương thích. Phần AUTHID CURRENT_USER giải thích chi tiết hơn.

### 4.2. Dynamic SQL

Dynamic SQL được tạo và thực thi lúc runtime, ví dụ:

~~~sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM data_owner.customers'
INTO l_customer_count;
~~~

Oracle thực hiện name resolution và privilege checking khi chạy câu lệnh động. Vì vậy quyền runtime và security domain của program unit quyết định câu SQL có thực hiện được không.

Trong definer-rights unit, dynamic SQL chạy theo quyền của owner; role của owner bị vô hiệu hóa theo quy tắc definer rights, trừ cơ chế role được cấp trực tiếp cho program unit theo khả năng Oracle hỗ trợ.

Trong invoker-rights unit, dynamic SQL sử dụng quyền của invoker và các role đang được bật trong ngữ cảnh hợp lệ.

Không dùng dynamic SQL chỉ để né lỗi direct grant của static SQL. Dynamic SQL làm tăng độ phức tạp, rủi ro SQL injection và khó kiểm tra dependency. Chỉ dùng khi tên bảng, cột hoặc cấu trúc câu lệnh thực sự phải thay đổi lúc runtime.

## 5. EXECUTE: quyền của người gọi procedure/package

Sau khi APP_CODE tạo package CUSTOMER_API, APP_RUNTIME cần quyền EXECUTE để gọi package.

~~~sql
GRANT EXECUTE ON app_code.customer_api TO app_runtime;
~~~

Có thể cấp cho role ứng dụng:

~~~sql
CREATE ROLE app_runtime_role;
GRANT EXECUTE ON app_code.customer_api TO app_runtime_role;
GRANT app_runtime_role TO app_runtime;
~~~

Khi role được bật trong session, APP_RUNTIME có thể gọi package:

~~~sql
BEGIN
    app_code.customer_api.list_customers;
END;
/
~~~

Caller không cần quyền CREATE PROCEDURE để gọi package. Caller cũng không nhất thiết cần SELECT trực tiếp bảng DATA_OWNER.CUSTOMERS nếu package là definer-rights và chỉ công bố thao tác được thiết kế.

### 5.1. EXECUTE trên package và quyền trên object bên trong

Cấp EXECUTE trên package không tự động cấp SELECT trên mọi bảng mà package sử dụng.

Ví dụ:

- APP_RUNTIME có EXECUTE trên APP_CODE.CUSTOMER_API.
- APP_CODE có SELECT trực tiếp trên DATA_OWNER.CUSTOMERS.
- CUSTOMER_API chạy với AUTHID DEFINER.

APP_RUNTIME có thể gọi API; package dùng quyền của APP_CODE để truy cập bảng theo logic đã viết.

Đây là cách xây dựng API database có kiểm soát: người dùng chỉ gọi các thao tác được công bố thay vì được truy cập trực tiếp mọi bảng.

Tuy nhiên, nếu procedure trả ra mọi dữ liệu nhạy cảm mà không lọc theo người dùng, việc chỉ cấp EXECUTE vẫn có thể mở ra quá nhiều dữ liệu. Phải thiết kế authorization nghiệp vụ bên trong API.

### 5.2. EXECUTE cho procedure được gọi từ stored procedure khác

Giả sử APP_CODE.PROC_A gọi APP_SERVICE.PROC_B. Nếu PROC_A là definer-rights, schema sở hữu PROC_A cần quyền EXECUTE phù hợp trên PROC_B theo security model của chuỗi gọi.

Không dựa vào role của người dùng cuối để làm cho một definer-rights stored procedure gọi được subprogram khác. Các privilege check trong chuỗi PL/SQL cần được đánh giá theo owner và AUTHID của từng unit.

### 5.3. Hạn chế GRANT EXECUTE TO PUBLIC

Có thể cấp quyền cho PUBLIC:

~~~sql
GRANT EXECUTE ON app_code.customer_api TO PUBLIC;
~~~

Nhưng PUBLIC đại diện cho mọi database user. Cách này mở rộng phạm vi gọi code rất lớn và không phù hợp với API nghiệp vụ nhạy cảm nếu không có lý do rõ ràng.

Ưu tiên cấp cho role ứng dụng chuyên biệt hoặc user cụ thể, sau đó quản lý membership của role.

## 6. AUTHID DEFINER: chạy với quyền của owner

Nếu không khai báo AUTHID, stored procedure/function/package mặc định dùng definer rights trong các trường hợp thông thường.

Có thể ghi rõ:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.list_customers
AUTHID DEFINER
IS
BEGIN
    FOR r IN (
        SELECT customer_id, customer_name
        FROM data_owner.customers
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(r.customer_name);
    END LOOP;
END;
/
~~~

Khi APP_RUNTIME gọi procedure:

- CURRENT_USER trong ngữ cảnh definer-rights là owner của unit.
- Quyền truy cập SQL được đánh giá theo security domain của owner.
- Các role của owner bị vô hiệu hóa trong unit.
- Caller cần EXECUTE trên unit, không cần trực tiếp có mọi quyền bảng mà unit sử dụng.
- Các thay đổi dữ liệu vẫn tuân theo transaction của session gọi; definer rights không tự COMMIT.

### 6.1. Definer rights là một ranh giới bảo mật

Một API definer-rights có thể cho phép user thực hiện một thao tác cụ thể mà không cấp trực tiếp quyền trên bảng nguồn.

Ví dụ, caller chỉ được gọi procedure tạo yêu cầu hỗ trợ:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.create_support_request (
    p_customer_id IN NUMBER,
    p_message     IN VARCHAR2
)
AUTHID DEFINER
IS
BEGIN
    INSERT INTO data_owner.support_requests (
        customer_id,
        request_message,
        created_at
    )
    VALUES (
        p_customer_id,
        p_message,
        SYSTIMESTAMP
    );
END;
/
~~~

APP_CODE cần quyền INSERT trực tiếp trên bảng SUPPORT_REQUESTS. APP_RUNTIME chỉ cần EXECUTE trên procedure.

Procedure cần validate customer, độ dài message, trạng thái tài khoản và các quy tắc nghiệp vụ trước khi ghi. Nếu không, một API được cấp EXECUTE rộng có thể trở thành đường ghi dữ liệu không được kiểm soát.

### 6.2. Role bị tắt trong definer-rights unit

Trong một definer-rights unit, các role đang bật của caller không trở thành quyền thực thi cho code. Việc này ngăn procedure vô tình kế thừa toàn bộ quyền role của người gọi.

Điều đó cũng có nghĩa câu lệnh SET ROLE không phải cách bật role bên trong definer-rights unit. Hãy cấp direct grant phù hợp cho owner hoặc thiết kế AUTHID khác khi yêu cầu thực sự là dùng quyền của caller.

## 7. AUTHID CURRENT_USER: chạy theo quyền của invoker

Invoker-rights unit được khai báo bằng AUTHID CURRENT_USER.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE app_code.count_my_customers
AUTHID CURRENT_USER
IS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM customers;

    DBMS_OUTPUT.PUT_LINE('Rows = ' || l_count);
END;
/
~~~

Khi được gọi, unit sử dụng security context của invoker cho các external references được resolve trong schema của invoker. Các role đang bật của invoker có thể tham gia privilege checking, trừ trường hợp unit được gọi trực tiếp hoặc gián tiếp từ một definer-rights unit khiến role bị vô hiệu hóa trong chuỗi gọi.

### 7.1. Template objects cho static SQL

Với invoker-rights unit có static SQL, Oracle cần resolve object khi compile. Các object được tham chiếu phải tồn tại trong schema owner tại thời điểm compile và trong schema invoker tại runtime nếu tên được resolve theo invoker.

Ví dụ:

- APP_CODE tạo COUNT_MY_CUSTOMERS.
- APP_CODE có bảng CUSTOMERS làm template để compiler phân tích SELECT.
- APP_RUNTIME có bảng CUSTOMERS riêng với cấu trúc tương thích.
- Khi APP_RUNTIME gọi procedure, static SQL được resolve theo schema invoker và chạy trên CUSTOMERS của APP_RUNTIME.

Các object tương ứng cần có tên/cột tương thích. Bảng template của APP_CODE không nhất thiết phải có dữ liệu; nó phục vụ việc biên dịch và resolve metadata.

Đây là mô hình hữu ích khi viết utility có thể chạy trên object cùng tên trong nhiều schema. Nếu không cần tính tổng quát này, definer-rights với object được qualify rõ ràng thường dễ quản lý hơn.

### 7.2. Quyền của invoker

Đối với DML và dynamic SQL tham chiếu object được resolve trong schema invoker, invoker phải có quyền runtime cần thiết. Quyền có thể đến từ direct grant hoặc role đang bật trong ngữ cảnh được phép.

Ví dụ, APP_RUNTIME truy cập bảng DATA_OWNER.CUSTOMERS qua dynamic SQL hoặc reference được resolve theo schema đó thì APP_RUNTIME cần quyền phù hợp trên bảng nguồn, trực tiếp hoặc qua role theo semantics invoker-rights.

Cấp quyền cho owner APP_CODE không thay thế quyền runtime mà invoker cần trong invoker-rights path.

### 7.3. Không phải mọi external reference đều được kiểm tra giống nhau

Oracle phân biệt external reference trong DML/dynamic SQL với các reference PL/SQL khác. Với một số reference PL/SQL được resolve lúc compile, quyền của owner được kiểm tra khi biên dịch và không được kiểm tra lại như object access runtime của invoker.

Vì vậy không nên mô tả AUTHID CURRENT_USER đơn giản là “mọi câu lệnh đều dùng quyền caller”. Cần xác định loại reference, thời điểm name resolution và unit được gọi trực tiếp hay gián tiếp từ definer-rights code.

### 7.4. INHERIT PRIVILEGES trong các phiên bản hỗ trợ

Từ Oracle Database 12c, invoker-rights unit còn chịu kiểm tra quyền kế thừa security context của invoker. Nếu owner không có INHERIT PRIVILEGES trên invoker và cũng không có INHERIT ANY PRIVILEGES, runtime có thể báo:

~~~text
ORA-06598: insufficient INHERIT PRIVILEGES privilege
~~~

DBA có thể cấp quyền cần thiết theo chính sách:

~~~sql
GRANT INHERIT PRIVILEGES ON USER app_runtime TO app_code;
~~~

Hoặc trong trường hợp đặc biệt, cấp INHERIT ANY PRIVILEGES cho owner. Quyền ANY này rất rộng, nên ưu tiên cấp INHERIT PRIVILEGES trên đúng user cần thiết.

Không cấp INHERIT PRIVILEGES hàng loạt nếu chưa hiểu unit nào thực sự cần chạy dưới quyền invoker.

## 8. So sánh AUTHID DEFINER và AUTHID CURRENT_USER

| Tiêu chí | AUTHID DEFINER | AUTHID CURRENT_USER |
|---|---|---|
| Security context runtime | Owner của program unit | Invoker hiện tại |
| Role của user | Bị vô hiệu hóa trong definer-rights unit | Có thể được bật, tùy call stack |
| Quyền trên bảng nguồn | Owner cần quyền thích hợp | Invoker cần quyền runtime cho external reference được resolve trong schema invoker |
| Mục tiêu thường gặp | API nghiệp vụ có quyền được kiểm soát | Utility tổng quát chạy theo quyền caller |
| Rủi ro chính | Code có thể sử dụng quyền mạnh của owner thay caller | Kết quả/phạm vi truy cập thay đổi theo invoker và role |
| Khai báo | Mặc định hoặc ghi AUTHID DEFINER | AUTHID CURRENT_USER |
| INHERIT PRIVILEGES | Không phải kiểm tra chuyển sang invoker như IR | Có thể cần trên Oracle 12c+ |

Chọn AUTHID dựa trên hợp đồng bảo mật:

- Dùng DEFINER khi muốn công bố một tập thao tác được kiểm soát bằng quyền của schema owner.
- Dùng CURRENT_USER khi logic phải tôn trọng quyền và schema của người gọi.
- Không đổi sang CURRENT_USER chỉ để sửa lỗi thiếu direct grant.
- Không dùng DEFINER chỉ vì muốn caller khỏi cần quyền bảng mà chưa thiết kế authorization bên trong procedure.

## 9. Vai trò trong stored PL/SQL

Role gom nhiều privilege thành một đơn vị để cấp cho user. Role rất hữu ích cho session ứng dụng và quản trị quyền, nhưng hiệu lực trong PL/SQL phụ thuộc AUTHID và call stack.

### 9.1. Role trong SQL session

Ví dụ:

~~~sql
CREATE ROLE r_reporting;

GRANT SELECT ON data_owner.customers TO r_reporting;
GRANT r_reporting TO app_runtime;
~~~

Sau khi đăng nhập, nếu role được bật:

~~~sql
SELECT role
FROM session_roles
WHERE role = 'R_REPORTING';
~~~

APP_RUNTIME có thể chạy SELECT trực tiếp nhờ role.

### 9.2. Role trong definer-rights unit

Khi một definer-rights procedure chạy, role của caller và owner bị vô hiệu hóa trong security domain của unit. Vì vậy không dựa vào R_REPORTING để cấp SELECT cho APP_CODE khi biên dịch và chạy static SQL của definer-rights procedure.

Thay vào đó, cấp direct object privilege cho APP_CODE:

~~~sql
GRANT SELECT ON data_owner.customers TO app_code;
~~~

### 9.3. Role trong invoker-rights unit

Invoker-rights unit có thể dùng các role đang bật của invoker cho privilege checking runtime đối với external references được resolve trong schema invoker, trừ trường hợp call stack từ definer-rights unit làm role bị vô hiệu hóa.

Điều này hữu ích cho một utility được nhiều schema gọi với quyền khác nhau. Cùng một procedure có thể truy cập tập object mà từng invoker được phép truy cập.

### 9.4. Chuỗi gọi lồng nhau

Xét:

~~~text
APP_RUNTIME
    |
    v
APP_CODE.PROC_A  (AUTHID DEFINER)
    |
    v
UTIL.PKG_B       (AUTHID CURRENT_USER)
    |
    v
DML / dynamic SQL
~~~

Khi invoker-rights unit được gọi trực tiếp hoặc gián tiếp bởi definer-rights unit, role của invoker không tự động được bật lại như khi gọi trực tiếp từ session. Cần phân tích toàn bộ call stack, không chỉ nhìn AUTHID của procedure cuối cùng.

## 10. Ví dụ đầy đủ: direct grant, role và EXECUTE

Phần này minh họa mô hình phổ biến với ba schema:

- DATA_OWNER sở hữu dữ liệu.
- APP_CODE sở hữu package API.
- APP_RUNTIME là tài khoản ứng dụng.

### 10.1. DATA_OWNER tạo bảng

Kết nối bằng DATA_OWNER:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);

INSERT INTO customers VALUES (1, 'An');
INSERT INTO customers VALUES (2, 'Binh');
COMMIT;
~~~

### 10.2. Cấp quyền trực tiếp cho APP_CODE

Kết nối bằng DATA_OWNER hoặc DBA:

~~~sql
GRANT SELECT ON customers TO app_code;
~~~

Đây là direct object grant. Không chỉ cấp SELECT qua role.

### 10.3. APP_CODE tạo package definer-rights

Kết nối bằng APP_CODE:

~~~sql
CREATE OR REPLACE PACKAGE customer_api
AUTHID DEFINER
AS
    PROCEDURE print_customer_names;
END customer_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    PROCEDURE print_customer_names IS
    BEGIN
        FOR r IN (
            SELECT customer_name
            FROM data_owner.customers
            ORDER BY customer_id
        ) LOOP
            DBMS_OUTPUT.PUT_LINE(r.customer_name);
        END LOOP;
    END print_customer_names;
END customer_api;
/
~~~

Nếu package body biên dịch thành công, kiểm tra object status:

~~~sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_name = 'CUSTOMER_API';
~~~

### 10.4. Cấp EXECUTE cho role ứng dụng

Kết nối bằng APP_CODE hoặc DBA:

~~~sql
CREATE ROLE app_runtime_role;

GRANT EXECUTE ON customer_api TO app_runtime_role;
GRANT app_runtime_role TO app_runtime;
~~~

APP_RUNTIME có thể gọi package:

~~~sql
BEGIN
    app_code.customer_api.print_customer_names;
END;
/
~~~

APP_RUNTIME không cần quyền SELECT trực tiếp trên DATA_OWNER.CUSTOMERS cho thao tác được package definer-rights thực hiện. Nhưng APP_RUNTIME vẫn phải có quyền EXECUTE trên package theo cách cấp quyền đã chọn.

### 10.5. Thu hồi direct grant để thấy ảnh hưởng compile/runtime

Trong môi trường lab, DATA_OWNER có thể thu hồi SELECT trực tiếp:

~~~sql
REVOKE SELECT ON customers FROM app_code;
~~~

Stored unit có thể chuyển sang INVALID hoặc lần biên dịch/thực thi tiếp theo gặp lỗi quyền, tùy dependency và trạng thái. Kiểm tra USER_OBJECTS/USER_ERRORS trong APP_CODE và không thực hiện trên production để thử.

Cấp lại:

~~~sql
GRANT SELECT ON customers TO app_code;
~~~

Sau đó compile lại nếu cần:

~~~sql
ALTER PACKAGE customer_api COMPILE BODY;
~~~

Thử nghiệm cho thấy quyền của owner trên object nguồn là một phần của hợp đồng vận hành package.

## 11. Chẩn đoán lỗi biên dịch và runtime

Không nên chỉ nhìn một mã lỗi rồi cấp thêm quyền rộng. Xác định lỗi xuất hiện ở giai đoạn nào.

### 11.1. Xem object status

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_type IN ('PROCEDURE', 'FUNCTION', 'PACKAGE', 'PACKAGE BODY')
ORDER BY object_name, object_type;
~~~

INVALID cho biết program unit cần được xử lý/compile lại hoặc dependency có vấn đề.

### 11.2. Xem lỗi compile

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
ORDER BY name, sequence;
~~~

USER_ERRORS hiển thị lỗi của object trong schema hiện tại. Với schema khác, DBA có thể dùng DBA_ERRORS nếu được cấp quyền.

### 11.3. Xem direct object grants

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM all_tab_privs
WHERE grantee IN ('APP_CODE', 'APP_RUNTIME')
ORDER BY owner, table_name, grantee, privilege;
~~~

DBA có thể dùng DBA_TAB_PRIVS để xem toàn database. USER_TAB_PRIVS/ALL_TAB_PRIVS/DBA_TAB_PRIVS có phạm vi hiển thị khác nhau; hãy chọn view đúng quyền của tài khoản đang điều tra.

### 11.4. Xem role và system privilege

Role đang bật trong session:

~~~sql
SELECT role
FROM session_roles
ORDER BY role;
~~~

System privilege trong session:

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

Role được cấp cho user:

~~~sql
SELECT granted_role,
       default_role
FROM user_role_privs
ORDER BY granted_role;
~~~

Những view này giúp phân biệt quyền trực tiếp trong session và role đang bật. Tuy nhiên, role đang bật trong session không chứng minh role đó được sử dụng bên trong definer-rights unit.

### 11.5. Kiểm tra quyền EXECUTE

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege
FROM all_tab_privs
WHERE privilege = 'EXECUTE'
  AND table_name = 'CUSTOMER_API'
ORDER BY owner, grantee;
~~~

Nếu package nằm ở schema khác, kiểm tra owner và grantee chính xác. Cũng kiểm tra role chứa EXECUTE có được cấp cho user và đang bật theo cách kết nối thực tế hay không.

### 11.6. Các lỗi thường gặp

| Lỗi/tình huống | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| ORA-00942 khi compile | Object không tồn tại, sai owner/name hoặc thiếu direct privilege | Kiểm tra object, synonym, direct grant và USER_ERRORS |
| PLS-00201 | Identifier không resolve được hoặc thiếu quyền nhìn thấy object | Kiểm tra schema qualification, grant và compile errors |
| ORA-01031 | Insufficient privileges cho DDL/DML hoặc thao tác runtime | Xác định user thực thi và security domain |
| ORA-06598 | Thiếu INHERIT PRIVILEGES cho invoker-rights unit | Kiểm tra grant INHERIT trên invoker |
| Procedure chạy trực tiếp được nhưng gọi từ package khác thất bại | Quyền trong call stack/definer-rights khác session role | Kiểm tra AUTHID của từng unit và direct grants |
| Package INVALID sau REVOKE | Dependency hoặc quyền compile/runtime thay đổi | USER_OBJECTS, USER_ERRORS và grants |
| Caller không gọi được package | Thiếu EXECUTE hoặc role chưa bật | Kiểm tra ALL_TAB_PRIVS và SESSION_ROLES |

Các mã lỗi có thể có nhiều nguyên nhân. Đọc toàn bộ error stack, dòng compile và object đang được tham chiếu trước khi thay đổi quyền.

## 12. Quy trình cấp quyền theo least privilege

Một quy trình triển khai nên tách owner, data schema và runtime user:

~~~text
DATA_OWNER
   |
   | GRANT đúng SELECT/INSERT/UPDATE/DELETE
   | trực tiếp cho APP_CODE nếu unit cần
   v
APP_CODE
   |
   | CREATE PROCEDURE / package
   | compile và kiểm tra USER_ERRORS
   |
   | GRANT EXECUTE trên API
   v
APP_RUNTIME_ROLE
   |
   | GRANT role cho APP_RUNTIME
   v
APP_RUNTIME
   |
   | gọi API đã được công bố
   v
APP_CODE.CUSTOMER_API
~~~

Các bước thực hiện:

1. Xác định object nguồn và thao tác tối thiểu cần thiết.
2. Cấp object privilege trực tiếp cho code owner khi definer-rights/static SQL cần.
3. Compile procedure/package và kiểm tra USER_ERRORS.
4. Xác định AUTHID phù hợp với security contract.
5. Cấp EXECUTE trên đúng procedure/package cho role ứng dụng.
6. Cấp role cho user ứng dụng theo chính sách.
7. Kiểm thử bằng tài khoản runtime thật, không chỉ bằng owner.
8. Kiểm tra truy cập ngoài phạm vi được phép có bị từ chối.
9. Kiểm tra dynamic SQL và SQL injection nếu có.
10. Ghi nhận grant/revoke trong migration script và quản lý bằng version control.

### 12.1. Không cấp quyền quá rộng để chữa lỗi

Tránh các cách sửa thiếu kiểm soát:

~~~sql
GRANT DBA TO app_code;
GRANT SELECT ANY TABLE TO app_code;
GRANT EXECUTE ANY PROCEDURE TO app_runtime;
GRANT EXECUTE ON app_code.customer_api TO PUBLIC;
~~~

Các quyền này có phạm vi rộng hơn nhu cầu của một API cụ thể. Hãy cấp direct object privilege hoặc EXECUTE trên object cần thiết.

### 12.2. Thu hồi quyền khi API không còn cần

Nếu package không còn dùng một bảng, thu hồi grant tương ứng sau khi xác nhận dependency:

~~~sql
REVOKE SELECT ON data_owner.old_customers FROM app_code;
~~~

Nếu ứng dụng không còn được phép gọi package:

~~~sql
REVOKE EXECUTE ON app_code.customer_api FROM app_runtime_role;
~~~

Sau REVOKE, kiểm tra object status, compile dependencies và hành vi caller. Không thu hồi grant trên production khi chưa xác định các unit khác cũng dùng quyền đó.

## 13. Dynamic SQL và an toàn bảo mật

Dynamic SQL có thể làm quyền được kiểm tra ở runtime và tên object thay đổi theo người gọi. Đây là tính năng hữu ích nhưng dễ tạo lỗ hổng nếu nối chuỗi trực tiếp từ input.

Không an toàn:

~~~sql
l_sql := 'SELECT * FROM ' || p_table_name;
EXECUTE IMMEDIATE l_sql;
~~~

Nếu P_TABLE_NAME chứa dữ liệu không đáng tin cậy, người dùng có thể thay đổi cấu trúc câu lệnh. Bind variable chỉ thay được giá trị, không thay được tên bảng/cột.

Với identifier động:

- Whitelist tên schema/table được phép.
- Dùng DBMS_ASSERT cho identifier phù hợp.
- Không ghép giá trị đầu vào vào literal; dùng bind variable.
- Qualify schema khi cần để tránh name resolution ngoài ý muốn.
- Kiểm tra quyền runtime theo AUTHID và call stack.
- Chỉ công bố EXECUTE cho đối tượng thực sự cần dùng.

Ví dụ bind giá trị:

~~~sql
l_sql :=
    'SELECT COUNT(*) FROM data_owner.customers ' ||
    'WHERE status = :1';

EXECUTE IMMEDIATE l_sql
INTO l_count
USING p_status;
~~~

P_STATUS được bind như dữ liệu. Tên bảng vẫn được cố định trong code; nếu tên bảng phải động, hãy xác thực bằng whitelist/DBMS_ASSERT.

## 14. Package và quyền ở mức package

Package gom procedure/function thành API chung. Caller thường được cấp EXECUTE trên package thay vì cấp riêng cho từng subprogram public.

Ví dụ:

~~~sql
GRANT EXECUTE ON app_code.customer_api TO app_runtime_role;
~~~

Quyền EXECUTE package cho phép caller gọi các subprogram public trong package specification. Private subprogram chỉ được gọi từ bên trong package và không thể gọi trực tiếp từ schema khác.

### 14.1. Package AUTHID

AUTHID được khai báo ở package specification và áp dụng cho package unit:

~~~sql
CREATE OR REPLACE PACKAGE app_code.report_api
AUTHID CURRENT_USER
AS
    PROCEDURE run_report;
END report_api;
/
~~~

Package body triển khai các subprogram theo security property của package. Không khai báo một AUTHID riêng cho từng procedure bên trong cùng package theo cách thay đổi property chung đó.

Nếu package cần các entry point có security behavior khác nhau, có thể thiết kế nhiều package hoặc tách các standalone unit theo boundary rõ ràng.

### 14.2. Private subprogram và controlled entry point

Một package có thể công bố một procedure public làm entry point, còn helper procedure giữ private trong body. Caller chỉ có thể gọi entry point có EXECUTE permission; helper được gọi nội bộ theo call chain.

Cách này giúp giảm bề mặt API và tập trung validation ở một nơi. Đừng công bố mọi helper trong package specification nếu ứng dụng không cần gọi trực tiếp.

## 15. Lab: chứng minh role không thay direct grant cho definer-rights code

Chỉ thực hiện trong schema lab có quyền tạo user/role hoặc nhờ DBA chuẩn bị. Không thu hồi grant trên object production.

### 15.1. Chuẩn bị

Tạo role và grant quyền SELECT qua role:

~~~sql
CREATE ROLE r_lab_reader;
GRANT SELECT ON data_owner.customers TO r_lab_reader;
GRANT r_lab_reader TO app_code;
~~~

Đăng nhập APP_CODE và thử SELECT trực tiếp:

~~~sql
SELECT COUNT(*)
FROM data_owner.customers;
~~~

Nếu role đang bật, câu SQL trực tiếp có thể thành công.

### 15.2. Tạo definer-rights procedure

~~~sql
CREATE OR REPLACE PROCEDURE test_role_privilege IS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM data_owner.customers;

    DBMS_OUTPUT.PUT_LINE(l_count);
END;
/
~~~

Với chỉ role grant, compile static SQL có thể thất bại. Xem:

~~~sql
SELECT line, position, text
FROM user_errors
WHERE name = 'TEST_ROLE_PRIVILEGE'
ORDER BY sequence;
~~~

### 15.3. Cấp direct grant và compile lại

DATA_OWNER hoặc DBA:

~~~sql
GRANT SELECT ON data_owner.customers TO app_code;
~~~

APP_CODE:

~~~sql
ALTER PROCEDURE test_role_privilege COMPILE;
~~~

Kiểm tra:

~~~sql
SELECT object_name, status
FROM user_objects
WHERE object_name = 'TEST_ROLE_PRIVILEGE';
~~~

### 15.4. Cấp EXECUTE cho caller

~~~sql
GRANT EXECUTE ON app_code.test_role_privilege TO app_runtime;
~~~

Đăng nhập APP_RUNTIME và gọi:

~~~sql
BEGIN
    app_code.test_role_privilege;
END;
/
~~~

Caller được phép chạy procedure thông qua EXECUTE. Quyền SELECT của procedure đến từ APP_CODE theo definer-rights; không cần cấp SELECT trên bảng cho APP_RUNTIME chỉ để chạy ví dụ này.

## 16. Checklist kiểm tra trước khi triển khai PL/SQL

- [ ] Xác định owner của procedure/function/package.
- [ ] Xác định schema sở hữu từng bảng, view, sequence và package được tham chiếu.
- [ ] Xác nhận CREATE PROCEDURE hoặc quyền tạo phù hợp.
- [ ] Phân biệt direct grant với quyền chỉ có qua role.
- [ ] Với definer-rights static SQL, cấp direct object privilege cho owner.
- [ ] Với invoker-rights static SQL, chuẩn bị template object và object tương ứng trong schema invoker.
- [ ] Xác định SQL nào là static, SQL nào là dynamic.
- [ ] Chọn AUTHID DEFINER hoặc CURRENT_USER theo security contract.
- [ ] Kiểm tra role và call stack, nhất là IR unit được gọi từ DR unit.
- [ ] Kiểm tra INHERIT PRIVILEGES trên Oracle release có áp dụng.
- [ ] Cấp EXECUTE trên đúng package/procedure cho role hoặc user cần thiết.
- [ ] Tránh GRANT EXECUTE TO PUBLIC nếu không có lý do rõ ràng.
- [ ] Kiểm tra USER_OBJECTS và USER_ERRORS sau compile.
- [ ] Kiểm thử bằng tài khoản runtime thật.
- [ ] Thử cả thao tác được phép và thao tác phải bị từ chối.
- [ ] Rà soát dynamic SQL, bind variables và identifier validation.
- [ ] Ghi lại GRANT/REVOKE trong migration và quy trình quản trị quyền.

## 17. Ghi nhớ cốt lõi

- CREATE PROCEDURE cho phép tạo program unit trong schema của mình; CREATE ANY PROCEDURE là quyền rộng để tạo trong schema khác.
- Quyền tạo code, quyền truy cập object của code và quyền EXECUTE của caller là ba lớp độc lập.
- Static SQL được kiểm tra khi compile và runtime; AUTHID không thay đổi cách kiểm tra ở compile time.
- Quyền chỉ được cấp qua role không thay thế direct grant cần cho compile static SQL của stored PL/SQL.
- Definer-rights unit là mặc định: runtime dùng quyền owner và role của user bị vô hiệu hóa trong unit.
- Invoker-rights unit dùng security context của invoker cho các external references được resolve trong schema invoker; role có thể tham gia runtime checking theo call stack.
- Invoker-rights static SQL cần template object trong schema owner lúc compile và object tương ứng trong schema invoker lúc runtime.
- Dynamic SQL được resolve và kiểm tra quyền lúc runtime; không dùng dynamic SQL chỉ để né lỗi quyền.
- EXECUTE trên package không tự cấp SELECT/INSERT/UPDATE/DELETE trên mọi bảng package sử dụng.
- Một definer-rights procedure gọi unit khác cần được đánh giá theo quyền owner và AUTHID của từng mắt xích, không dựa vào role của user cuối.
- Oracle 12c+ có thể yêu cầu INHERIT PRIVILEGES khi chạy invoker-rights unit; thiếu quyền có thể gây ORA-06598.
- Least privilege, package entry point rõ ràng, direct grants chính xác và test bằng tài khoản runtime giúp PL/SQL an toàn hơn.
- Khi có lỗi, kiểm tra compile errors, object status, direct grants, roles, AUTHID và call stack trước khi cấp quyền rộng.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database PL/SQL Language Reference — Invoker's Rights and Definer's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html) — AUTHID, static/dynamic SQL, template objects, role và INHERIT PRIVILEGES.
- [Oracle Database Security Guide — Managing Security for Definer's Rights and Invoker's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-security-for-definers-rights-and-invokers-rights.html) — quyền runtime, call chain và quyền của invoker.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — GRANT, REVOKE, CREATE PROCEDURE và quyền EXECUTE.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — package specification/body và program unit.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — USER_OBJECTS, USER_ERRORS, ALL_TAB_PRIVS, SESSION_ROLES và các dictionary view.

Quy tắc AUTHID, template object, role trong call stack và INHERIT PRIVILEGES cần được đối chiếu với Oracle release đang chạy. Hãy thử compile và execute bằng các schema lab riêng, kiểm tra cả direct grant lẫn role grant, rồi mới áp dụng migration quyền vào production.

