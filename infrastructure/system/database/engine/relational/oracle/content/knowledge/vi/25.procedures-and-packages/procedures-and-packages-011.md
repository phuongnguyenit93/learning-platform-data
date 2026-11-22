# Phụ thuộc đối tượng, thay đổi chữ ký và biên dịch lại trong Oracle

Một procedure có thể gọi package khác, package có thể truy vấn view, view lại phụ thuộc vào bảng. Khi một đối tượng thay đổi, các đối tượng sử dụng nó có thể phải được biên dịch lại. Nếu thay đổi đó làm chữ ký của procedure hoặc package không còn tương thích, caller có thể không biên dịch được hoặc phát sinh lỗi khi chạy. Vì vậy, thay đổi một object trong Oracle không chỉ là sửa một câu DDL; cần hiểu dependency graph, phạm vi ảnh hưởng và thứ tự triển khai.

Oracle lưu thông tin phụ thuộc giữa nhiều schema objects trong data dictionary. Các dependency giúp database biết object nào cần được kiểm tra hoặc đánh dấu INVALID khi object nền thay đổi. PL/SQL stored units có thể được tự động biên dịch lại khi được gọi sau khi invalid, hoặc DBA/developer có thể chủ động compile theo thứ tự phù hợp. Tuy nhiên, compile thành công chỉ xác nhận mã hiện tại có thể biên dịch với các dependency hiện tại; nó không tự chứng minh logic nghiệp vụ vẫn tương thích với mọi caller.

Bài học thuộc nhóm **Thủ tục và package** của Database Engine Relational Oracle. Nội dung tập trung vào dependency giữa procedure, function, package specification/body, view, table, type và synonym; tác động của thay đổi chữ ký; trạng thái VALID/INVALID; biên dịch lại; chẩn đoán lỗi; và quy trình triển khai thay đổi an toàn.

Sau bài này, bạn có thể:

- Giải thích dependency trực tiếp và dependency bắc cầu giữa các schema objects.
- Phân biệt package specification với package body về vai trò và phạm vi ảnh hưởng.
- Nhận diện thay đổi chữ ký procedure/function có thể phá vỡ caller.
- Hiểu vì sao thay đổi bảng, view, type hoặc quyền có thể làm stored object INVALID.
- Kiểm tra dependency bằng USER_DEPENDENCIES/ALL_DEPENDENCIES.
- Kiểm tra trạng thái object và lỗi compile bằng USER_OBJECTS/USER_ERRORS.
- Chủ động compile procedure, function, package, package body và view.
- Recompile schema theo cách phù hợp với quyền quản trị.
- Nhận biết giới hạn dependency tracking với dynamic SQL.
- Sắp xếp thứ tự migration và xử lý package state khi thay đổi code.
- Thiết kế API PL/SQL ổn định để giảm ảnh hưởng khi triển khai phiên bản mới.

> **Phạm vi ví dụ:** Cú pháp theo Oracle Database 19c. Các object có hậu tố _LAB dành cho schema thực hành. DDL trong Oracle có implicit commit theo quy tắc của database; hãy triển khai migration có kế hoạch và không chạy ví dụ trên schema nghiệp vụ thật.

## 1. Object dependency là gì?

Một object phụ thuộc vào object khác khi định nghĩa hoặc phần thân của nó tham chiếu đến object đó. Ví dụ:

~~~text
TABLE EMPLOYEE
    |
    v
VIEW V_EMPLOYEE_DIRECTORY
    |
    v
PACKAGE EMPLOYEE_API
    |
    v
PROCEDURE HR_SERVICE
~~~

Trong sơ đồ, view đọc bảng EMPLOYEE; package dùng view; procedure gọi package. Nếu bảng thay đổi theo cách ảnh hưởng view, tác động có thể lan qua các object phía trên.

### 1.1. Dependency trực tiếp

Procedure truy vấn bảng:

~~~sql
CREATE OR REPLACE PROCEDURE show_employee_lab (
    p_employee_id IN NUMBER
) AS
    l_name employee_data_lab.full_name%TYPE;
BEGIN
    SELECT full_name
    INTO l_name
    FROM employee_data_lab
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

SHOW_EMPLOYEE_LAB có dependency trực tiếp vào EMPLOYEE_DATA_LAB vì phần thân tham chiếu bảng và cột của bảng.

### 1.2. Dependency bắc cầu

Procedure gọi package, package đọc view, view đọc bảng:

~~~text
HR_SERVICE
   |
   v
EMPLOYEE_API
   |
   v
V_EMPLOYEE_DIRECTORY
   |
   v
EMPLOYEE_DATA
~~~

HR_SERVICE có dependency trực tiếp vào EMPLOYEE_API. Nó phụ thuộc gián tiếp vào view và bảng thông qua chuỗi object. Khi một dependency nền thay đổi, Oracle có thể đánh dấu một số object phụ thuộc cần compile lại theo quy tắc dependency và mức độ thay đổi.

### 1.3. Dependency là quan hệ giữa object, không phải lời gọi runtime duy nhất

Một stored procedure có thể phụ thuộc vào:

- Bảng, view, materialized view.
- Sequence.
- Synonym được phân giải đến object đích.
- Package specification, package, procedure hoặc function.
- SQL object type, collection type.
- Một số object khác được tham chiếu trong định nghĩa.

Dependency được ghi nhận khi compiler phân tích các tham chiếu tĩnh. Một tên object chỉ xuất hiện bên trong chuỗi dynamic SQL không được kiểm tra theo cùng cách tại thời điểm compile.

## 2. Dependency graph và phạm vi ảnh hưởng

### 2.1. Một thay đổi có thể ảnh hưởng nhiều object

Giả sử package spec được nhiều package khác sử dụng:

~~~text
                PACKAGE CUSTOMER_API SPEC
                    /       |       \
                   v        v        v
             ORDER_API   BILLING_API  REPORT_API
                 |          |           |
                 v          v           v
             ORDER_SVC   BILLING_SVC  REPORT_JOB
~~~

Thay đổi public declaration của CUSTOMER_API có thể làm các package phụ thuộc trực tiếp trở thành INVALID. Các object phụ thuộc tiếp theo có thể cũng cần compile lại. Vì vậy, trước khi sửa một API dùng chung, hãy xác định dependency graph và phạm vi consumer.

### 2.2. Thay đổi không phải lúc nào cũng invalidation toàn bộ schema

Oracle theo dõi dependency ở mức object và, với nhiều loại tham chiếu PL/SQL/SQL, có cơ chế dependency chi tiết. Một thay đổi không liên quan đến thành phần mà dependent object sử dụng có thể không làm mọi dependent invalid. Kết quả cụ thể phụ thuộc loại object, loại thay đổi, release và dependency metadata.

Không nên áp dụng hai giả định cực đoan:

- Mọi ALTER TABLE đều làm mọi procedure trong schema INVALID.
- Thay đổi bảng không bao giờ ảnh hưởng procedure.

Hãy kiểm tra trạng thái object thực tế sau migration.

### 2.3. Đồ thị phụ thuộc có thể có nhiều tầng và nhiều schema

USER_DEPENDENCIES chỉ cho biết dependency mà user hiện tại sở hữu. Khi ứng dụng dùng nhiều schema, hãy dùng ALL_DEPENDENCIES hoặc DBA_DEPENDENCIES với quyền phù hợp để xem phạm vi rộng hơn. Cần xét cả owner của object nền, synonym, package và view.

### 2.4. Object INVALID không đồng nghĩa dữ liệu bị hỏng

INVALID là trạng thái của object cần được biên dịch hoặc xử lý lại. Nó không có nghĩa bảng dữ liệu bị mất hay dữ liệu bị thay đổi. Tuy nhiên, nếu ứng dụng gọi object INVALID mà compile lại thất bại, chức năng phụ thuộc object đó có thể không chạy được.

## 3. Package specification và package body

Package có hai phần có vai trò khác nhau:

- **Specification (spec):** public contract, khai báo type, constant, variable, cursor, exception, procedure và function mà caller được phép dùng.
- **Body:** implementation của subprogram, cursor body, private declarations và logic nội bộ.

### 3.1. Package specification

~~~sql
CREATE OR REPLACE PACKAGE employee_api_lab AS
    PROCEDURE get_employee_name (
        p_employee_id IN NUMBER,
        p_full_name OUT VARCHAR2
    );

    FUNCTION employee_count
        RETURN NUMBER;
END employee_api_lab;
/
~~~

Caller compile dựa trên public declarations trong spec. Đây là contract mà package cung cấp cho các stored objects khác và code gọi package.

### 3.2. Package body

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api_lab AS
    PROCEDURE get_employee_name (
        p_employee_id IN NUMBER,
        p_full_name OUT VARCHAR2
    ) IS
    BEGIN
        SELECT full_name
        INTO p_full_name
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END get_employee_name;

    FUNCTION employee_count
        RETURN NUMBER
    IS
        l_count NUMBER;
    BEGIN
        SELECT COUNT(*)
        INTO l_count
        FROM employee_data_lab;

        RETURN l_count;
    END employee_count;
END employee_api_lab;
/
~~~

Body chứa implementation. Nếu chỉ thay đổi cách tính bên trong mà public spec không đổi, caller thường không cần compile lại chỉ vì implementation thay đổi. Tuy nhiên, body phải compile thành công và các session đang giữ package state có thể chịu tác động khi package được thay thế.

### 3.3. Sửa spec có phạm vi ảnh hưởng lớn hơn sửa body

| Thay đổi | Tác động thường gặp |
| --- | --- |
| Chỉ sửa câu SQL hoặc logic trong body | Package body cần compile; public contract không đổi |
| Thêm private helper trong body | Body thay đổi; caller không cần biết helper |
| Đổi tham số public procedure trong spec | Caller phụ thuộc chữ ký có thể INVALID hoặc không compile |
| Đổi public type trong spec | Các object dùng type có thể cần compile lại |
| Xóa procedure/function khỏi spec | Caller tham chiếu API đã xóa sẽ lỗi compile |
| Đổi constant/public declaration | Consumer phụ thuộc declaration có thể bị ảnh hưởng |

Đây là nguyên tắc thiết kế quan trọng: giữ spec ổn định và thay đổi implementation trong body khi có thể. Khi phải thay public API, lập kế hoạch migration cho tất cả caller.

### 3.4. Package body vẫn phụ thuộc spec

Body phải tuân thủ declarations trong spec. Nếu body thiếu implementation cho public subprogram hoặc chữ ký không khớp, body không compile được. Khi sửa spec, body có thể trở thành INVALID và cần được cập nhật tương ứng.

## 4. Chữ ký procedure và function

Chữ ký mô tả cách caller tương tác với subprogram. Với procedure/function PL/SQL, các yếu tố quan trọng gồm:

- Tên subprogram.
- Số lượng và thứ tự tham số.
- Tên tham số khi caller dùng named notation.
- Datatype và subtype của tham số.
- Parameter mode: IN, OUT, IN OUT.
- Default value của tham số.
- Kiểu trả về của function.
- Các quy tắc overload resolution.

### 4.1. Chữ ký ban đầu

~~~sql
CREATE OR REPLACE PROCEDURE create_order_lab (
    p_customer_id IN NUMBER,
    p_amount IN NUMBER
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Customer=' || p_customer_id ||
        ', amount=' || p_amount
    );
END;
/
~~~

Caller theo positional notation:

~~~sql
BEGIN
    create_order_lab(501, 250);
END;
/
~~~

Caller theo named notation:

~~~sql
BEGIN
    create_order_lab(
        p_customer_id => 501,
        p_amount => 250
    );
END;
/
~~~

### 4.2. Thêm tham số bắt buộc

Giả sử API mới thêm p_currency nhưng không có default:

~~~sql
CREATE OR REPLACE PROCEDURE create_order_lab (
    p_customer_id IN NUMBER,
    p_amount IN NUMBER,
    p_currency IN VARCHAR2
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        p_customer_id || ' ' || p_amount || ' ' || p_currency
    );
END;
/
~~~

Caller cũ chỉ truyền hai tham số sẽ không còn khớp chữ ký. Stored caller có thể trở thành INVALID và khi compile lại sẽ báo lỗi về số lượng/kiểu tham số. Caller bên ngoài database cũng cần được cập nhật.

### 4.3. Thêm tham số có default ở cuối

Một cách giảm ảnh hưởng là thêm tham số tùy chọn ở cuối với default:

~~~sql
CREATE OR REPLACE PROCEDURE create_order_lab (
    p_customer_id IN NUMBER,
    p_amount IN NUMBER,
    p_currency IN VARCHAR2 DEFAULT 'VND'
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        p_customer_id || ' ' || p_amount || ' ' || p_currency
    );
END;
/
~~~

Caller cũ truyền hai đối số vẫn có thể gọi procedure và dùng default cho p_currency. Tuy nhiên:

- Cần kiểm tra mọi caller dùng positional/named notation.
- Default phải phù hợp với semantics nghiệp vụ.
- Thay đổi public spec vẫn có thể làm dependent objects cần revalidation/recompile.
- Client ngoài database, generated bindings và integration contract vẫn cần kiểm tra.

Default parameter là công cụ tương thích có điều kiện, không phải bảo đảm rằng mọi API consumer không cần thay đổi.

### 4.4. Chèn tham số vào giữa làm positional calls nguy hiểm

Nếu thêm một tham số giữa danh sách, positional callers có thể gán giá trị cũ vào vị trí mới hoặc không còn compile. Ngay cả khi có default, việc thay đổi thứ tự tham số có thể phá vỡ lời gọi.

Đối với API dùng rộng, hãy ưu tiên:

- Thêm tham số tùy chọn ở cuối nếu semantics phù hợp.
- Dùng named notation trong PL/SQL callers.
- Tạo overload hoặc API version mới khi thay đổi không tương thích.
- Giữ wrapper procedure cũ trong giai đoạn chuyển đổi.

### 4.5. Đổi parameter mode

IN, OUT và IN OUT không thể xem là thay đổi hình thức:

- IN: caller cung cấp giá trị để subprogram đọc.
- OUT: subprogram trả giá trị cho caller.
- IN OUT: subprogram nhận giá trị và có thể thay đổi rồi trả lại.

Đổi IN thành OUT/IN OUT có thể làm caller cũ không còn hợp lệ, đặc biệt khi caller truyền literal, expression hoặc biến không phù hợp với OUT semantics. Phải kiểm tra mọi call site và binding của client.

### 4.6. Đổi datatype

Đổi NUMBER thành VARCHAR2 hoặc đổi subtype/precision có thể làm:

- Caller không còn khớp datatype.
- Overload resolution chọn subprogram khác.
- Phát sinh implicit conversion hoặc lỗi runtime.
- Client binding phải thay đổi.

Không coi implicit conversion là hợp đồng API. Hãy dùng datatype rõ ràng và migration có kiểm thử.

### 4.7. Đổi function return type

Function trả NUMBER:

~~~sql
CREATE OR REPLACE FUNCTION get_credit_limit_lab (
    p_customer_id IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN 1000;
END;
/
~~~

Nếu đổi return type sang VARCHAR2 hoặc SQL object type, các caller dùng function trong SQL, PL/SQL expression hoặc client binding có thể bị ảnh hưởng. Return type là một phần của contract.

## 5. Overloading và thay đổi API

Package có thể overload procedure/function bằng nhiều chữ ký khác nhau:

~~~sql
CREATE OR REPLACE PACKAGE payment_api_lab AS
    PROCEDURE pay (
        p_account_id IN NUMBER,
        p_amount IN NUMBER
    );

    PROCEDURE pay (
        p_account_id IN NUMBER,
        p_amount IN NUMBER,
        p_currency IN VARCHAR2
    );
END payment_api_lab;
/
~~~

Overloading hữu ích khi các biến thể có semantics rõ. Nhưng overload có thể tạo mơ hồ khi các kiểu tham số gần nhau hoặc literal có thể chuyển đổi sang nhiều kiểu.

### 5.1. Overload resolution

~~~sql
BEGIN
    payment_api_lab.pay(10, 250);
    payment_api_lab.pay(10, 250, 'VND');
END;
/
~~~

Khi thêm overload, hãy kiểm tra các lời gọi hiện tại có thể trở nên ambiguous hoặc chọn overload khác không. Các lời gọi dùng NULL literal, số không có suffix hoặc string có thể cần kiểu rõ ràng.

### 5.2. Dùng named notation

~~~sql
BEGIN
    payment_api_lab.pay(
        p_account_id => 10,
        p_amount => 250,
        p_currency => 'VND'
    );
END;
/
~~~

Named notation làm rõ ý nghĩa tham số và giảm nhầm thứ tự. Nó không loại bỏ mọi vấn đề khi đổi tên tham số public, vì tên tham số là một phần của named-call contract.

### 5.3. Không overload chỉ để né versioning

Nếu hai biến thể có semantics khác nhau đáng kể, tên API riêng có thể rõ hơn:

- CREATE_ORDER_V1 và CREATE_ORDER_V2 trong giai đoạn chuyển tiếp.
- CREATE_ORDER với request record versioned.
- Package API riêng theo domain hoặc version.

Overloading nên được dùng khi các biến thể thực sự là cùng một thao tác với tập tham số khác nhau.

## 6. Thay đổi bảng, view và type có thể ảnh hưởng PL/SQL

### 6.1. Procedure phụ thuộc cột bảng

~~~sql
CREATE OR REPLACE PROCEDURE read_salary_lab (
    p_employee_id IN NUMBER,
    p_salary OUT NUMBER
) AS
BEGIN
    SELECT monthly_salary
    INTO p_salary
    FROM employee_data_lab
    WHERE employee_id = p_employee_id;
END;
/
~~~

Procedure phụ thuộc vào bảng và cột MONTHLY_SALARY. Nếu cột bị DROP hoặc đổi tên, procedure không thể compile với câu SQL cũ.

### 6.2. %TYPE tạo dependency với datatype nguồn

~~~sql
CREATE OR REPLACE PROCEDURE update_employee_email_lab (
    p_employee_id IN employee_data_lab.employee_id%TYPE,
    p_email IN employee_data_lab.work_email%TYPE
) AS
BEGIN
    UPDATE employee_data_lab
    SET work_email = p_email
    WHERE employee_id = p_employee_id;
END;
/
~~~

%TYPE giúp datatype PL/SQL bám theo cột. Nếu datatype nguồn thay đổi, stored unit có thể cần revalidation/recompile và caller cần kiểm tra tương thích.

### 6.3. %ROWTYPE phụ thuộc cấu trúc hàng

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;
END;
/
~~~

%ROWTYPE gắn với row shape của bảng/view. Thêm, xóa hoặc thay đổi cột có thể ảnh hưởng các đơn vị sử dụng rowtype và câu SELECT tương ứng. Dùng %ROWTYPE khi cần toàn hàng; dùng explicit record khi muốn contract chỉ gồm một số trường ổn định.

### 6.4. View thay đổi

Procedure truy vấn view phụ thuộc vào cột view công bố. Nếu CREATE OR REPLACE VIEW đổi tên cột, bỏ cột hoặc đổi datatype, procedure dùng view có thể INVALID hoặc compile lỗi. Nếu chỉ thay predicate mà giữ schema, code có thể vẫn compile nhưng semantics dữ liệu thay đổi; cần kiểm thử nghiệp vụ.

### 6.5. SQL object type thay đổi

Package/procedure có thể dùng SQL object type hoặc collection type trong tham số. Thay đổi type specification có thể ảnh hưởng các object phụ thuộc. Với object type có thuộc tính/method, thay đổi type cần được quản lý như thay đổi contract, đặc biệt khi type được dùng trong bảng hoặc interface giữa schema.

### 6.6. Thêm cột không luôn làm mọi dependent invalid

Oracle có cơ chế dependency chi tiết để tránh invalidation không cần thiết trong một số thay đổi. Ví dụ, một procedure chỉ dùng hai cột cụ thể không nhất thiết bị invalid chỉ vì thêm một cột không liên quan vào bảng. Nhưng object dùng %ROWTYPE hoặc SELECT * có dependency rộng hơn về cấu trúc hàng.

Đừng đoán phạm vi invalidation. Hãy kiểm tra USER_OBJECTS sau DDL và compile/test các object có liên quan.

## 7. Static SQL và dynamic SQL trong dependency tracking

### 7.1. Static SQL

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_static_lab (
    p_id IN NUMBER
) AS
    l_name VARCHAR2(80);
BEGIN
    SELECT full_name
    INTO l_name
    FROM employee_data_lab
    WHERE employee_id = p_id;
END;
/
~~~

Compiler phân tích tên bảng/cột trong static SQL và ghi dependency phù hợp. Nếu object nền thay đổi theo cách phá vỡ câu SQL, stored unit có thể bị invalid hoặc compile lại thất bại.

### 7.2. Dynamic SQL

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_dynamic_lab (
    p_table_name IN VARCHAR2,
    p_id IN NUMBER,
    p_name OUT VARCHAR2
) AS
BEGIN
    EXECUTE IMMEDIATE
        'SELECT full_name FROM ' || p_table_name ||
        ' WHERE employee_id = :x'
        INTO p_name
        USING p_id;
END;
/
~~~

Tên bảng nằm trong chuỗi tại runtime. Compiler không thể xác nhận đầy đủ object name trong chuỗi như static SQL. Vì vậy, dependency dictionary có thể không thể hiện tất cả object mà dynamic SQL sẽ truy cập.

Điều này có nghĩa:

- Compile procedure thành công không chứng minh mọi dynamic SQL path đều hợp lệ.
- Đổi tên/drop bảng được nhắc trong chuỗi có thể chỉ lộ lỗi khi nhánh runtime được gọi.
- Test phải bao phủ các object name và nhánh dynamic SQL thực tế.
- Input dùng làm identifier cần được kiểm soát chặt; bind variable chỉ bind value, không bind tên bảng/cột.

### 7.3. Không nối input tùy ý vào dynamic SQL

Không dùng user input trực tiếp làm tên object hoặc mảnh SQL:

~~~sql
-- Khong an toan neu p_table_name den tu input khong tin cay.
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM ' || p_table_name;
~~~

Nếu cần chọn bảng theo nghiệp vụ, dùng allowlist tên hợp lệ, schema qualification và DBMS_ASSERT cho identifier phù hợp. Bind values thay vì nối giá trị vào chuỗi:

~~~sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM employee_data_lab WHERE department_id = :d'
INTO l_count
USING p_department_id;
~~~

DBMS_ASSERT giúp kiểm tra một số dạng identifier/literal; nó không thay thế authorization hoặc allowlist nghiệp vụ.

### 7.4. Synonym và tên không qualification

Nếu code tham chiếu tên không có schema prefix, Oracle có thể phân giải qua object trong schema hiện tại hoặc synonym. Khi synonym đổi target, ý nghĩa truy vấn có thể đổi. Để migration dễ dự đoán, cân nhắc schema-qualify dependency quan trọng và kiểm soát synonym grants/target.

## 8. Trạng thái VALID và INVALID

Oracle lưu trạng thái object trong data dictionary. Với stored PL/SQL units, view và một số schema objects, trạng thái thường là VALID hoặc INVALID.

### 8.1. Xem object trong schema hiện tại

~~~sql
SELECT
    object_name,
    object_type,
    status,
    last_ddl_time
FROM user_objects
WHERE object_type IN (
    'PROCEDURE',
    'FUNCTION',
    'PACKAGE',
    'PACKAGE BODY',
    'VIEW',
    'TRIGGER'
)
ORDER BY object_type, object_name;
~~~

VALID nghĩa object đã được compile/validate thành công theo trạng thái hiện tại. INVALID nghĩa object cần được compile lại hoặc có lỗi dependency/definition.

### 8.2. Xem invalid objects trong schema

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

Ở phạm vi nhiều schema, DBA có thể dùng DBA_OBJECTS hoặc ALL_OBJECTS tùy quyền.

### 8.3. Xem lỗi compile

~~~sql
SELECT
    name,
    type,
    sequence,
    line,
    position,
    text
FROM user_errors
ORDER BY name, type, sequence;
~~~

USER_ERRORS chứa lỗi biên dịch của object thuộc schema hiện tại. ALL_ERRORS/DBA_ERRORS cho phạm vi rộng hơn khi có quyền. Lỗi compile thường chỉ ra line/position; mở đúng source line để sửa nguyên nhân.

### 8.4. SHOW ERRORS

Trong SQL*Plus hoặc công cụ hỗ trợ lệnh tương đương:

~~~sql
SHOW ERRORS PROCEDURE show_employee_lab
SHOW ERRORS PACKAGE employee_api_lab
SHOW ERRORS PACKAGE BODY employee_api_lab
~~~

SHOW ERRORS tiện cho tương tác. USER_ERRORS phù hợp khi cần truy vấn lỗi bằng SQL hoặc tích hợp vào deployment report.

## 9. Xem dependency bằng data dictionary

### 9.1. USER_DEPENDENCIES

Xem các object trong schema hiện tại phụ thuộc vào object nào:

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type,
    dependency_type
FROM user_dependencies
ORDER BY name, referenced_owner, referenced_name;
~~~

Các cột quan trọng:

- NAME/TYPE: object phụ thuộc.
- REFERENCED_OWNER: schema của object được tham chiếu.
- REFERENCED_NAME/TYPE: tên và loại object được tham chiếu.
- DEPENDENCY_TYPE: loại dependency theo dictionary.

### 9.2. Tìm object phụ thuộc vào một package

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM all_dependencies
WHERE referenced_name = 'EMPLOYEE_API_LAB'
  AND referenced_type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY owner, name, type;
~~~

ALL_DEPENDENCIES có OWNER; nếu truy vấn trong schema hiện tại, USER_DEPENDENCIES có thể đơn giản hơn. Thay tên package bằng chữ hoa theo dictionary nếu object được tạo không dùng quoted identifier.

### 9.3. Tìm dependency theo object nền

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE referenced_name = 'EMPLOYEE_DATA_LAB'
ORDER BY type, name;
~~~

Kết quả giúp tìm stored objects/view phụ thuộc trực tiếp vào bảng.

### 9.4. Dependency không phải toàn bộ runtime call graph

Dictionary dependency không phải profiler. Nó không cho biết:

- Object nào được gọi thường xuyên nhất.
- Nhánh dynamic SQL nào thực sự chạy.
- Caller ngoài database nào gọi procedure.
- Code client nào đang dùng positional parameter binding.
- Object nào chỉ được gọi qua reflection/framework.

Muốn lập bản đồ đầy đủ, cần kết hợp dependency metadata, source search, application repository, SQL monitoring và log runtime.

### 9.5. Xem source stored object

~~~sql
SELECT line, text
FROM user_source
WHERE name = 'EMPLOYEE_API_LAB'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY type, line;
~~~

USER_SOURCE giúp xem source PL/SQL hiện được lưu. Với package spec/body, hãy lọc đúng TYPE. ALL_SOURCE/DBA_SOURCE dùng cho phạm vi rộng hơn theo quyền.

## 10. Biên dịch lại object

Khi object INVALID, có thể compile thủ công sau khi dependency đã hợp lệ.

### 10.1. Compile procedure

~~~sql
ALTER PROCEDURE show_employee_lab COMPILE;
~~~

### 10.2. Compile function

~~~sql
ALTER FUNCTION get_credit_limit_lab COMPILE;
~~~

### 10.3. Compile package specification

~~~sql
ALTER PACKAGE employee_api_lab COMPILE SPECIFICATION;
~~~

Có thể dùng ALTER PACKAGE ... COMPILE để compile package theo cú pháp hỗ trợ. Khi cần chỉ rõ phần body:

~~~sql
ALTER PACKAGE employee_api_lab COMPILE BODY;
~~~

### 10.4. Compile view

~~~sql
ALTER VIEW v_employee_directory_lab COMPILE;
~~~

Nếu view vẫn INVALID do cột/bảng không tồn tại hoặc quyền không hợp lệ, compile lại sẽ không tự sửa định nghĩa. Cần sửa dependency hoặc view query trước.

### 10.5. Compile trigger

~~~sql
ALTER TRIGGER trg_employee_audit_lab COMPILE;
~~~

Trigger có thể phụ thuộc vào table columns, package, sequence và các object khác. Kiểm tra USER_ERRORS sau compile.

### 10.6. Compile xong vẫn phải kiểm tra

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'SHOW_EMPLOYEE_LAB',
    'EMPLOYEE_API_LAB',
    'V_EMPLOYEE_DIRECTORY_LAB'
)
ORDER BY object_type, object_name;

SELECT name, type, line, position, text
FROM user_errors
ORDER BY name, type, sequence;
~~~

Không coi việc ALTER ... COMPILE trả về không lỗi là bằng chứng duy nhất. Hãy kiểm tra status và compile errors.

## 11. Automatic recompilation và lần gọi đầu tiên

Khi một stored object INVALID được tham chiếu, Oracle có thể tự động thử compile lại object đó. Nếu tất cả dependency cần thiết hợp lệ và quyền phù hợp, object có thể trở lại VALID và lần gọi tiếp tục.

### 11.1. Automatic revalidation không bảo đảm thành công

Nếu:

- Cột đã bị DROP/rename.
- Procedure được gọi đã đổi chữ ký.
- Type không còn tương thích.
- View không compile được.
- Quyền trực tiếp trên object nền đã bị thu hồi.
- Package spec/body không khớp.

thì automatic compilation có thể thất bại và caller nhận lỗi.

### 11.2. Có thể phát sinh latency ở lần gọi đầu

Nếu hệ thống chờ đến khi ứng dụng gọi object INVALID mới compile, request đầu tiên sau deployment có thể chịu thêm thời gian compile hoặc thất bại. Với hệ thống quan trọng, chủ động compile và kiểm tra toàn bộ object trong deployment window giúp phát hiện lỗi trước khi traffic thật đi vào.

### 11.3. Không cần compile mù toàn bộ schema sau mọi thay đổi

Compile tất cả object sau mỗi DDL có thể tạo tải không cần thiết và làm khó xác định lỗi gốc. Hãy:

1. Xác định dependency bị ảnh hưởng.
2. Sửa object nền trước.
3. Compile theo thứ tự dependency.
4. Kiểm tra invalid objects còn lại.
5. Chạy smoke tests cho API bị ảnh hưởng.

Với schema lớn hoặc migration nhiều object, DBA có thể dùng công cụ recompile schema theo kế hoạch.

## 12. Recompile schema và nhiều object

### 12.1. DBMS_UTILITY.COMPILE_SCHEMA

DBMS_UTILITY cung cấp COMPILE_SCHEMA để compile stored objects trong một schema:

~~~sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema => 'APP_OWNER',
        compile_all => FALSE
    );
END;
/
~~~

COMPILE_ALL = FALSE thường chỉ compile các object INVALID; TRUE yêu cầu compile tất cả object phù hợp. Quyền thực thi package và phạm vi schema phụ thuộc user. Chạy trong maintenance/deployment window khi schema có nhiều object.

### 12.2. UTL_RECOMP

UTL_RECOMP hỗ trợ recompile invalid objects theo cách serial hoặc parallel trong phạm vi quản trị:

~~~sql
BEGIN
    UTL_RECOMP.RECOMP_SERIAL('APP_OWNER');
END;
/
~~~

Hoặc DBA có thể cân nhắc RECOMP_PARALLEL theo tài liệu package của release và tài nguyên hệ thống. UTL_RECOMP thường cần quyền quản trị thích hợp và không nên được gọi tùy tiện từ application runtime.

### 12.3. Compile song song không phải lúc nào cũng tốt hơn

Parallel recompilation có thể giảm thời gian trên schema lớn nhưng tiêu thụ CPU, memory và I/O. Nếu dependency còn thiếu hoặc lỗi source chưa được sửa, parallel compile chỉ làm nhiều object cùng thất bại. Hãy sửa root cause trước.

### 12.4. Kiểm tra trước và sau

Trước:

~~~sql
SELECT owner, object_type, COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, object_type;
~~~

Sau:

~~~sql
SELECT owner, object_name, object_type, status
FROM dba_objects
WHERE owner = 'APP_OWNER'
  AND status = 'INVALID'
ORDER BY object_type, object_name;
~~~

DBA_OBJECTS cần quyền xem dictionary phù hợp. Nếu không có DBA privilege, dùng USER_OBJECTS hoặc ALL_OBJECTS trong phạm vi được phép.

## 13. Quyền trực tiếp và dependency khi compile

Stored PL/SQL chạy với quyền theo AUTHID và cơ chế privilege tương ứng. Đặc biệt với definer-rights stored units (mặc định), role grants không thay thế direct object grants khi compile/resolve static SQL trong stored code.

### 13.1. Ví dụ cross-schema

DATA_OWNER sở hữu bảng:

~~~sql
CREATE TABLE employee_data_lab (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(80)
);
~~~

APP_OWNER cần truy cập bảng:

~~~sql
GRANT SELECT ON employee_data_lab TO app_owner;
~~~

Sau đó APP_OWNER tạo procedure:

~~~sql
CREATE OR REPLACE PROCEDURE app_read_employee_lab (
    p_id IN NUMBER,
    p_name OUT VARCHAR2
) AS
BEGIN
    SELECT full_name
    INTO p_name
    FROM data_owner.employee_data_lab
    WHERE employee_id = p_id;
END;
/
~~~

Nếu chỉ cấp SELECT qua role cho APP_OWNER, compile stored procedure definer-rights có thể thất bại. Hãy cấp quyền trực tiếp trên object nền cho owner của stored unit theo nguyên tắc least privilege.

### 13.2. Thu hồi quyền có thể làm object không còn compile được

Nếu DATA_OWNER thu hồi SELECT:

~~~sql
REVOKE SELECT ON employee_data_lab FROM app_owner;
~~~

Procedure phụ thuộc bảng có thể bị invalid hoặc không thể revalidate/compile. Khi xử lý lỗi, kiểm tra cả object dependency lẫn grants; không chỉ sửa source code.

### 13.3. AUTHID CURRENT_USER

Procedure/package có AUTHID CURRENT_USER dùng invoker-rights model. Quyền truy cập được kiểm tra theo invoker theo quy tắc Oracle, khác với definer-rights mặc định. Thiết kế invoker-rights có thể hữu ích cho API cần dùng quyền caller, nhưng không phải cách chữa thiếu direct grants một cách tự động. Hãy xác định rõ security model và test bằng user thực tế.

## 14. Synonym và dependency resolution

Synonym là tên thay thế cho object khác. Stored code có thể tham chiếu object qua synonym:

~~~sql
CREATE SYNONYM employee_source_lab
FOR data_owner.employee_data_lab;
~~~

Procedure:

~~~sql
CREATE OR REPLACE PROCEDURE read_employee_syn_lab (
    p_id IN NUMBER,
    p_name OUT VARCHAR2
) AS
BEGIN
    SELECT full_name
    INTO p_name
    FROM employee_source_lab
    WHERE employee_id = p_id;
END;
/
~~~

### 14.1. Synonym không cấp quyền

Synonym chỉ cung cấp tên thay thế. Caller/owner vẫn cần quyền trên object đích theo mô hình security. Tạo synonym không tự cấp SELECT/EXECUTE.

### 14.2. Thay target synonym

Nếu synonym được thay để trỏ sang bảng/view khác, semantics của stored code có thể thay đổi. Object phụ thuộc có thể cần revalidation; ngay cả khi compile thành công, schema mới có thể có dữ liệu/constraint khác.

### 14.3. Dùng schema qualification cho dependency quan trọng

Trong stored code của ứng dụng, tham chiếu rõ OWNER.OBJECT giúp:

- Giảm sự mơ hồ khi có private/public synonym trùng tên.
- Dễ review dependency.
- Giảm rủi ro đổi target do search path/synonym.
- Làm migration giữa schema rõ ràng hơn.

Tuy vậy, schema qualification không thay thế quyền và không loại bỏ dependency.

## 15. Package state và lỗi sau khi thay package

Package có thể giữ trạng thái trong session nếu chứa public/private package variables, constants được khởi tạo, cursors hoặc state khác. Khi package bị recompile/replaced trong lúc session đã khởi tạo package state, session đó có thể nhận lỗi liên quan package state ở lần gọi tiếp theo.

### 15.1. Các lỗi có thể gặp

- ORA-04061: existing state of package has been invalidated.
- ORA-04065: not executed, altered or dropped stored procedure/package.
- ORA-04068: existing state of packages has been discarded.
- ORA-04063: package/body hoặc object có errors.

Thông báo cụ thể phụ thuộc tình huống và release.

### 15.2. Vì sao package body thay đổi vẫn có thể ảnh hưởng session?

Ngay cả khi spec không đổi và caller không cần compile lại, package body được thay thế có thể làm trạng thái package đã khởi tạo trong session cũ không còn hợp lệ. Oracle có thể bỏ package state để session dùng implementation mới. Ứng dụng cần xử lý lỗi và có thể phải khởi tạo lại trạng thái package.

### 15.3. Package state không phải nơi lưu trạng thái bền vững

Không dùng package variables làm nguồn dữ liệu bền vững giữa các session. Package state:

- Thuộc session.
- Có thể bị reset khi package invalidated/recompiled.
- Không được chia sẻ như bảng giữa mọi session.
- Có thể gây hành vi khó dự đoán trong connection pool nếu state không được quản lý.

Nếu trạng thái nghiệp vụ cần tồn tại qua session/restart, lưu trong bảng hoặc storage phù hợp.

### 15.4. Connection pool và package state

Connection pool tái sử dụng database sessions. Một session có thể giữ package state từ request trước. Nếu API dựa vào package variables, cần reset/initialize state có chủ đích và không giả định mỗi request nhận session sạch. Sau package deployment, kiểm thử các session cũ đang được pool giữ.

## 16. Thứ tự triển khai khi thay đổi dependency

Khi một API hoặc object nền thay đổi, triển khai theo thứ tự dependency để giảm invalidation kéo dài.

### 16.1. Thứ tự tổng quát

~~~text
1. TABLES / SEQUENCES / SQL TYPES
          |
          v
2. GRANTS / SYNONYMS
          |
          v
3. VIEWS
          |
          v
4. PACKAGE SPECIFICATIONS
          |
          v
5. PACKAGE BODIES
          |
          v
6. PROCEDURES / FUNCTIONS / TRIGGERS
          |
          v
7. RECOMPILE DEPENDENTS
          |
          v
8. SMOKE TESTS / APPLICATION CHECK
~~~

Đây là thứ tự khái quát. Schema thực tế có thể có package spec tham chiếu type/package khác, view phụ thuộc view, hoặc dependency vòng được thiết kế bằng forward declarations. Hãy dùng dependency graph thực tế để xác định thứ tự.

### 16.2. Thay đổi additive

Thay đổi additive là bổ sung mà vẫn giữ contract cũ, ví dụ thêm tham số cuối có default hoặc thêm procedure mới vào package spec. Đây thường ít phá vỡ hơn nhưng vẫn cần kiểm tra:

- Dependent objects có bị INVALID không?
- Overload resolution có đổi không?
- Caller cũ có tiếp tục compile/run?
- Public package state có bị reset?
- Client ngoài database có cần update binding?

### 16.3. Thay đổi breaking

Thay đổi breaking gồm:

- Xóa procedure/function.
- Đổi tên public subprogram.
- Đổi datatype hoặc parameter mode.
- Đổi thứ tự tham số positional.
- Đổi return type.
- Đổi public record/object type.
- Đổi semantics của tham số hoặc kết quả.

Với thay đổi breaking, cân nhắc tạo API version mới, wrapper tương thích hoặc rollout theo nhiều bước.

### 16.4. Wrapper tương thích

Giữ API cũ nhưng chuyển implementation sang API mới:

~~~sql
CREATE OR REPLACE PACKAGE employee_api_v2_lab AS
    PROCEDURE get_employee (
        p_employee_id IN NUMBER,
        p_include_status IN BOOLEAN,
        p_full_name OUT VARCHAR2,
        p_status OUT VARCHAR2
    );
END employee_api_v2_lab;
/
~~~

Package cũ giữ chữ ký cũ và gọi API mới với default phù hợp:

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api_lab AS
    PROCEDURE get_employee_name (
        p_employee_id IN NUMBER,
        p_full_name OUT VARCHAR2
    ) IS
        l_status VARCHAR2(12);
    BEGIN
        employee_api_v2_lab.get_employee(
            p_employee_id => p_employee_id,
            p_include_status => FALSE,
            p_full_name => p_full_name,
            p_status => l_status
        );
    END get_employee_name;
END employee_api_lab;
/
~~~

Wrapper cho phép consumer cũ tiếp tục hoạt động trong thời gian chuyển đổi. Khi đã migrate hết caller, có thể deprecate và loại bỏ API cũ theo một release riêng.

## 17. Quy trình deployment thực tế

### 17.1. Trước deployment

1. Lấy danh sách object phụ thuộc.
2. Tìm caller trong source repository và application configuration.
3. Xác định thay đổi additive hay breaking.
4. Kiểm tra quyền trực tiếp và synonym target.
5. Lập thứ tự DDL/compile.
6. Chuẩn bị rollback/forward-fix script.
7. Kiểm tra package state và connection pool.
8. Chạy migration trên môi trường cùng release/schema shape.

### 17.2. Trong deployment

- Dừng hoặc điều phối traffic nếu thay đổi không tương thích.
- Triển khai object nền trước.
- Cập nhật grants/synonyms.
- Tạo view và package spec/body theo dependency order.
- Compile các dependent stored objects.
- Kiểm tra USER_OBJECTS/USER_ERRORS.
- Chạy smoke tests từ schema owner và application user.
- Kiểm tra session cũ nếu package state có ý nghĩa.

### 17.3. Sau deployment

- Xác nhận không còn INVALID object ngoài danh sách được chấp nhận.
- Chạy truy vấn/transaction đại diện.
- Kiểm tra application logs và lỗi ORA-/PLS-.
- Xác nhận caller cũ/new client binding.
- Kiểm tra dependency mới và grants.
- Ghi nhận version API và migration result.

### 17.4. DDL và rollback

DDL trong Oracle có implicit commit. Nếu script gồm 10 câu CREATE/ALTER và câu thứ 8 thất bại, các DDL trước đó có thể đã được commit. Không thể bọc toàn bộ migration DDL trong một transaction rồi ROLLBACK như DML.

Hãy chuẩn bị:

- Script forward-fix hoặc reverse DDL tương ứng.
- Backup/source control của DDL trước thay đổi.
- Kế hoạch tương thích ứng dụng trong thời gian rollout.
- Bước xác minh trạng thái sau mỗi giai đoạn.

Không dùng DROP/CREATE tùy tiện nếu CREATE OR REPLACE hoặc ALTER phù hợp hơn; DROP có thể làm mất grants, synonym references hoặc tạo khoảng thời gian object không tồn tại.

## 18. Ví dụ lab: thay chữ ký và recompile dependent objects

Lab này minh họa dependency giữa package và procedure gọi nó. Chạy trong schema riêng.

### 18.1. Tạo package phiên bản đầu

~~~sql
CREATE OR REPLACE PACKAGE employee_api_sig_lab AS
    PROCEDURE get_name (
        p_employee_id IN NUMBER,
        p_name OUT VARCHAR2
    );
END employee_api_sig_lab;
/

CREATE OR REPLACE PACKAGE BODY employee_api_sig_lab AS
    PROCEDURE get_name (
        p_employee_id IN NUMBER,
        p_name OUT VARCHAR2
    ) IS
    BEGIN
        SELECT full_name
        INTO p_name
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END get_name;
END employee_api_sig_lab;
/
~~~

### 18.2. Tạo caller phụ thuộc

~~~sql
CREATE OR REPLACE PROCEDURE caller_sig_lab (
    p_employee_id IN NUMBER
) AS
    l_name VARCHAR2(80);
BEGIN
    employee_api_sig_lab.get_name(
        p_employee_id => p_employee_id,
        p_name => l_name
    );

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

Caller phụ thuộc vào public signature của EMPLOYEE_API_SIG_LAB.

### 18.3. Kiểm tra dependency

~~~sql
SELECT
    name,
    type,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE referenced_name = 'EMPLOYEE_API_SIG_LAB'
ORDER BY name, type;
~~~

### 18.4. Thay đổi chữ ký theo cách breaking

Thêm tham số bắt buộc:

~~~sql
CREATE OR REPLACE PACKAGE employee_api_sig_lab AS
    PROCEDURE get_name (
        p_employee_id IN NUMBER,
        p_language IN VARCHAR2,
        p_name OUT VARCHAR2
    );
END employee_api_sig_lab;
/
~~~

Body cần được cập nhật để khớp spec. Caller cũ vẫn gọi với hai đối số và có thể không compile được.

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api_sig_lab AS
    PROCEDURE get_name (
        p_employee_id IN NUMBER,
        p_language IN VARCHAR2,
        p_name OUT VARCHAR2
    ) IS
    BEGIN
        SELECT full_name
        INTO p_name
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END get_name;
END employee_api_sig_lab;
/
~~~

### 18.5. Xem trạng thái caller và lỗi

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'EMPLOYEE_API_SIG_LAB',
    'CALLER_SIG_LAB'
)
ORDER BY object_type;

SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'CALLER_SIG_LAB'
ORDER BY sequence;
~~~

### 18.6. Sửa caller

~~~sql
CREATE OR REPLACE PROCEDURE caller_sig_lab (
    p_employee_id IN NUMBER
) AS
    l_name VARCHAR2(80);
BEGIN
    employee_api_sig_lab.get_name(
        p_employee_id => p_employee_id,
        p_language => 'VI',
        p_name => l_name
    );

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

Sau khi sửa caller, kiểm tra lại status và errors rồi gọi procedure với một employee_id hợp lệ.

### 18.7. So sánh với tham số default

Trong một bản thiết kế khác, thêm p_language ở cuối với DEFAULT 'VI' có thể giữ caller hai tham số. Đây là thay đổi API ít phá vỡ hơn, nhưng vẫn phải compile/test dependency và xác nhận semantics default.

### 18.8. Dọn lab (tùy chọn)

Chỉ chạy nếu chắc chắn đây là các object lab do bạn tạo:

~~~sql
DROP PROCEDURE caller_sig_lab;
DROP PACKAGE employee_api_sig_lab;
~~~

DROP là DDL và có implicit commit. Không chạy trên object nghiệp vụ thật.

## 19. Những lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| PLS-00306 wrong number or types of arguments | Caller không khớp chữ ký mới | Sửa call site, thêm overload hoặc wrapper tương thích |
| PLS-00302 component must be declared | Public member bị xóa/đổi tên hoặc không có trong spec | Cập nhật caller hoặc khôi phục API |
| PLS-00905 object is invalid | Object được tham chiếu đang INVALID | Xem USER_ERRORS và compile dependency trước |
| ORA-04063 has errors | Package/view/procedure có lỗi compile | Truy vấn USER_ERRORS/ALL_ERRORS và sửa source |
| ORA-04061 package state invalidated | Package đã thay đổi khi session giữ state | Xử lý session/package state, khởi tạo lại theo thiết kế |
| ORA-04068 package state discarded | Oracle bỏ state package đã khởi tạo | Ứng dụng xử lý lỗi, khởi tạo lại request/session state |
| ORA-00942 table or view does not exist | Object không tồn tại, synonym sai hoặc thiếu quyền | Kiểm tra owner, object name và direct grants |
| PLS-00201 identifier must be declared | Tên object/type/procedure không phân giải được hoặc thiếu quyền | Kiểm tra spec, schema qualification, synonym và grants |
| Object vẫn INVALID sau COMPILE | Dependency nền vẫn sai hoặc compile error còn tồn tại | Sửa root cause trước, rồi compile lại |
| Dynamic SQL lỗi dù procedure VALID | Tên object trong chuỗi không được kiểm tra đầy đủ lúc compile | Test runtime paths và kiểm soát identifier |
| Caller ngoài DB lỗi sau deployment | Binding/client contract không được cập nhật | Kiểm tra JDBC/OCI/ORM/generated API và versioning |

## 20. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Package body và spec là một object có cùng tác động | Spec là public contract; body là implementation |
| Sửa body luôn invalid mọi caller | Body-only change thường không đổi caller contract, nhưng session package state có thể bị discard |
| Thêm tham số luôn phá mọi caller | Tham số cuối có default có thể giữ một số call sites, nhưng vẫn cần kiểm tra |
| Compile thành công chứng minh API tương thích | Chỉ chứng minh object compile; client ngoài DB và semantics vẫn cần test |
| INVALID nghĩa dữ liệu bảng hỏng | INVALID là trạng thái schema object, không phải trạng thái dữ liệu |
| Oracle luôn tự compile thành công | Auto revalidation có thể thất bại do dependency/signature/privilege |
| USER_DEPENDENCIES hiển thị mọi runtime call | Dynamic SQL và external callers có thể không được thể hiện đầy đủ |
| Synonym cấp quyền truy cập | Synonym chỉ là alias; quyền vẫn cần trên object đích |
| Role grant luôn đủ cho stored definer-rights code | Static SQL compile cần direct object grants phù hợp |
| ALTER ... COMPILE sửa được mọi lỗi | Compile chỉ thử lại; source/dependency sai vẫn cần sửa |
| Có thể rollback toàn bộ DDL migration | DDL có implicit commit; cần forward-fix/reverse DDL |
| Package variables tồn tại vĩnh viễn | Package state thuộc session và có thể bị reset/invalidate |

## 21. Checklist thay đổi procedure/package an toàn

Trước khi sửa:

1. Xác định object nền và các dependent objects.
2. Xem package spec/body và chữ ký hiện tại.
3. Tìm caller trong PL/SQL source và application repository.
4. Xác định thay đổi additive hay breaking.
5. Kiểm tra positional/named notation, overload và parameter modes.
6. Kiểm tra direct grants, role, AUTHID và synonym resolution.
7. Xem dynamic SQL có tham chiếu object bị thay đổi không.
8. Chuẩn bị migration theo dependency order.

Sau khi sửa:

1. Compile package spec trước body khi spec thay đổi.
2. Compile dependent procedures/functions/triggers/views theo dependency.
3. Xem USER_OBJECTS/ALL_OBJECTS.
4. Xem USER_ERRORS/ALL_ERRORS.
5. Xác nhận không còn invalid object ngoài dự kiến.
6. Chạy smoke tests từ caller thực tế.
7. Kiểm tra package state của session/connection pool.
8. Kiểm tra client binding và API compatibility.
9. Ghi nhận version và kết quả deployment.

## 22. Câu hỏi tự kiểm tra

1. Object dependency là gì?
2. Dependency trực tiếp khác dependency bắc cầu thế nào?
3. Vì sao thay đổi package spec có thể ảnh hưởng nhiều caller?
4. Package body khác package spec ở vai trò nào?
5. Thay đổi body-only thường có tác động gì đến dependent callers?
6. Vì sao package body replacement vẫn có thể ảnh hưởng session giữ package state?
7. Chữ ký procedure/function gồm những thành phần quan trọng nào?
8. Thêm tham số bắt buộc ảnh hưởng caller cũ ra sao?
9. Thêm tham số cuối có default giúp gì?
10. Vì sao thay đổi thứ tự tham số positional có thể nguy hiểm?
11. IN, OUT và IN OUT ảnh hưởng call contract thế nào?
12. Overloading có thể tạo lỗi/mơ hồ gì?
13. %TYPE và %ROWTYPE tạo dependency với schema ra sao?
14. Vì sao thêm cột vào bảng không nhất thiết invalid mọi procedure?
15. Dynamic SQL có hạn chế gì trong dependency tracking?
16. USER_DEPENDENCIES dùng để xem điều gì?
17. USER_OBJECTS và USER_ERRORS khác nhau thế nào?
18. Khi nào dùng ALTER PACKAGE COMPILE BODY?
19. Automatic recompilation hoạt động khi nào và có giới hạn gì?
20. DBMS_UTILITY.COMPILE_SCHEMA dùng để làm gì?
21. Vì sao definer-rights stored code cần direct grants?
22. Synonym có thay thế quyền object không?
23. ORA-04068 liên quan đến điều gì?
24. Vì sao DDL migration không thể rollback như một transaction DML?
25. Khi nào nên tạo API version mới hoặc wrapper?

**Gợi ý trả lời:**

1. Quan hệ giữa một schema object và object mà nó tham chiếu.
2. Trực tiếp là tham chiếu ngay; bắc cầu đi qua một hoặc nhiều object trung gian.
3. Caller compile dựa trên public declarations của spec.
4. Spec khai báo public contract; body chứa implementation.
5. Thường body cần compile; caller contract không đổi nếu spec giữ nguyên.
6. Package state đã khởi tạo có thể bị invalidated/discarded.
7. Tên, tham số, thứ tự, datatype, mode, default, return type và overload behavior.
8. Call cũ thiếu đối số có thể không compile.
9. Có thể giữ một số caller cũ khi semantics default phù hợp.
10. Giá trị có thể bị gán sang tham số khác hoặc call không còn hợp lệ.
11. Chúng xác định dữ liệu đi vào/đi ra và loại actual argument được phép.
12. Ambiguous resolution hoặc chọn overload khác ngoài dự kiến.
13. Chúng gắn datatype/row shape với cột hoặc bảng/view.
14. Oracle có dependency tracking chi tiết; object chỉ dùng cột không đổi có thể không cần invalidation.
15. Tên object nằm trong string thường chỉ được phân giải lúc runtime, không được compiler kiểm tra đầy đủ.
16. Object phụ thuộc và object được tham chiếu.
17. USER_OBJECTS cho trạng thái; USER_ERRORS cho lỗi compile.
18. Khi cần compile implementation body của package.
19. Oracle thử compile khi object INVALID được tham chiếu; thất bại nếu dependency/quyền/source còn lỗi.
20. Compile stored objects trong một schema, thường để xử lý object INVALID.
21. Role grants không thay direct object grants trong compile static SQL của definer-rights stored units.
22. Không; synonym chỉ là alias.
23. Package state của session đã bị discard do package invalidation.
24. DDL có implicit commit.
25. Khi thay đổi breaking cần rollout dần và giữ consumer cũ hoạt động trong giai đoạn chuyển tiếp.

## Tài liệu Oracle tham khảo

- [Oracle Database Concepts — Schema Objects and Dependencies](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/schema-objects.html): schema objects và quan hệ phụ thuộc.
- [Oracle Database PL/SQL Language Reference — PL/SQL Units and Compilation](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-units-and-compilation.html): stored PL/SQL units và biên dịch.
- [Oracle Database PL/SQL Language Reference — Packages](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-packages.html): package specification, body và package state.
- [Oracle Database SQL Language Reference — ALTER PROCEDURE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-PROCEDURE.html): biên dịch lại procedure.
- [Oracle Database SQL Language Reference — ALTER PACKAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-PACKAGE.html): biên dịch package specification/body.
- [Oracle Database Reference — USER_DEPENDENCIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_DEPENDENCIES.html): dependency metadata trong schema.
- [Oracle Database Reference — USER_OBJECTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_OBJECTS.html): trạng thái và metadata object.
- [Oracle Database Reference — USER_ERRORS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_ERRORS.html): lỗi biên dịch stored objects.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_UTILITY](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_UTILITY.html): COMPILE_SCHEMA và các tiện ích quản trị.
- [Oracle Database PL/SQL Packages and Types Reference — UTL_RECOMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_RECOMP.html): recompile invalid objects.

**Nguyên tắc cần nhớ:** Package specification là hợp đồng công khai; package body là phần triển khai. Thay đổi public signature có thể làm caller không còn tương thích, trong khi thay body thường giữ nguyên contract nhưng vẫn có thể làm mất package state của session đang hoạt động. Hãy xem dependency graph, grants và caller trước migration; triển khai object nền trước object phụ thuộc; compile và kiểm tra trạng thái/error sau đó; cuối cùng chạy smoke test với caller và connection pool thực tế.
