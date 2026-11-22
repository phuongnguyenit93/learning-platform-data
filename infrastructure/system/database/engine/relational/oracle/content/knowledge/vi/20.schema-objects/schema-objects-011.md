# Đối tượng INVALID, biên dịch lại và theo dõi dependency

Trong Oracle Database, một đối tượng schema như view, procedure, function, package, trigger hoặc type có thể tồn tại trong data dictionary nhưng đang ở trạng thái **INVALID**. Điều này thường có nghĩa Oracle chưa có một phiên bản có thể sử dụng của đối tượng sau lần tạo/sửa gần nhất, hoặc một dependency mà đối tượng cần dùng đã thay đổi.

Khi ứng dụng gọi một đối tượng INVALID, Oracle có thể thử tự động biên dịch lại. Nếu lần biên dịch thành công, đối tượng trở lại VALID và câu lệnh có thể tiếp tục. Nếu còn lỗi, ứng dụng có thể nhận lỗi như ORA-04063, ORA-06508 hoặc ORA-04045 cùng lỗi biên dịch PL/SQL cụ thể. Vì vậy, điều tra không dừng ở thao tác COMPILE: phải tìm lỗi gốc, dependency bị thay đổi, quyền truy cập và các đối tượng phụ thuộc có thể bị ảnh hưởng.

Bài học hướng dẫn cách kiểm tra trạng thái object, đọc lỗi biên dịch, compile đúng loại đối tượng, lần theo dependency hai chiều, xử lý quyền trực tiếp trong stored PL/SQL và lập kế hoạch recompilation sau thay đổi schema.

## 1. VALID và INVALID có ý nghĩa gì?

Oracle lưu metadata của đối tượng schema trong data dictionary. Với các loại đối tượng có trạng thái biên dịch, cột STATUS trong USER_OBJECTS, ALL_OBJECTS hoặc DBA_OBJECTS thường cho biết:

| STATUS | Ý nghĩa |
| --- | --- |
| VALID | Đối tượng hiện có trạng thái hợp lệ theo metadata/biên dịch của Oracle |
| INVALID | Đối tượng cần được biên dịch hoặc xác thực lại trước khi có thể sử dụng bình thường |

Một object INVALID vẫn có thể xuất hiện trong USER_OBJECTS. INVALID không đồng nghĩa object đã bị DROP, và cũng không tự nói rõ nguyên nhân. Có thể object được tạo khi dependency chưa tồn tại, source có lỗi, quyền trực tiếp bị thiếu, signature của package thay đổi hoặc đối tượng được tham chiếu bị sửa.

### 1.1. Những loại object thường gặp

- **VIEW:** câu SELECT định nghĩa view không còn biên dịch được, ví dụ bảng/cột tham chiếu bị đổi hoặc quyền bị thu hồi.
- **PROCEDURE/FUNCTION:** source PL/SQL hoặc SQL tĩnh bên trong không biên dịch được.
- **PACKAGE:** specification hoặc body có lỗi; package body có thể INVALID dù specification còn VALID.
- **TRIGGER:** source trigger hoặc đối tượng mà trigger tham chiếu không còn hợp lệ.
- **TYPE/TYPE BODY:** định nghĩa type hoặc body cần biên dịch lại.
- **MATERIALIZED VIEW:** có thể cần refresh/compile tùy nguyên nhân và loại đối tượng; không nên áp dụng cú pháp compile PL/SQL cho mọi loại object.

Không phải mọi loại đối tượng trong *_OBJECTS đều có trạng thái biên dịch theo cùng cách. Khi viết script vận hành, hãy lọc các OBJECT_TYPE phù hợp thay vì giả định mọi object INVALID đều xử lý bằng một lệnh ALTER ... COMPILE.

### 1.2. INVALID có thể xuất hiện sau DDL

Ví dụ:

1. View V_ORDER_SUMMARY tham chiếu bảng ORDERS.
2. Procedure P_CLOSE_ORDER gọi package PKG_ORDER.
3. Package PKG_ORDER sử dụng view V_ORDER_SUMMARY.
4. Một thay đổi DDL trên đối tượng được tham chiếu làm dependent object cần được xác thực lại.

Oracle quản lý dependency để nhận biết quan hệ giữa các object. Khi thay đổi một đối tượng, Oracle có thể đánh dấu một số đối tượng phụ thuộc là INVALID. Khi object được dùng lại, Oracle có thể thử recompile tự động. Cơ chế fine-grained dependency tracking giúp tránh invalidation không cần thiết trong một số thay đổi SQL không ảnh hưởng phần được tham chiếu; tuy nhiên, thay đổi package specification hoặc interface vẫn có thể ảnh hưởng nhiều caller.

## 2. Liệt kê object INVALID trong schema

### 2.1. Schema hiện tại: USER_OBJECTS

~~~sql
SELECT
    object_type,
    object_name,
    status,
    last_ddl_time
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

USER_OBJECTS hiển thị các đối tượng thuộc schema đang đăng nhập. Đây thường là điểm bắt đầu khi developer điều tra object của chính mình.

### 2.2. Object có thể truy cập: ALL_OBJECTS

~~~sql
SELECT
    owner,
    object_type,
    object_name,
    status,
    last_ddl_time
FROM all_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

ALL_OBJECTS hiển thị các object mà session có thể truy cập theo metadata/privilege. Nó không nhất thiết là danh sách toàn bộ object trong database.

### 2.3. Toàn database: DBA_OBJECTS

DBA hoặc tài khoản được cấp quyền phù hợp có thể dùng:

~~~sql
SELECT
    owner,
    object_type,
    object_name,
    status,
    last_ddl_time
FROM dba_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Đây là truy vấn phù hợp cho báo cáo toàn database. Không cấp quyền đọc DBA_OBJECTS hoặc catalog rộng chỉ để một ứng dụng thông thường liệt kê object của schema mình.

### 2.4. Đếm object theo owner và loại

~~~sql
SELECT
    owner,
    object_type,
    COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, invalid_count DESC, object_type;
~~~

Truy vấn này giúp nhận ra một schema vừa có một package body lỗi hay đang có hàng trăm object INVALID sau một đợt deploy. Số lượng lớn không tự cho biết nguyên nhân; cần drill down theo object và dependency.

### 2.5. Ghi nhận thời điểm và edition

Khi điều tra môi trường có edition-based redefinition, cần lưu ý object có thể được phân biệt theo edition. Nếu view metadata của release hỗ trợ cột EDITION_NAME, có thể thêm cột đó vào báo cáo để không nhầm object ở edition khác. Cũng nên ghi timestamp của snapshot và database/service/instance trong biên bản sự cố.

## 3. Đọc lỗi biên dịch

Trạng thái INVALID chỉ cho biết object cần xử lý; chi tiết thường nằm trong *_ERRORS.

### 3.1. USER_ERRORS

Với object thuộc schema hiện tại:

~~~sql
SELECT
    name,
    type,
    sequence,
    line,
    position,
    text,
    attribute
FROM user_errors
WHERE name = UPPER(:object_name)
ORDER BY sequence;
~~~

Các cột quan trọng:

| Cột | Ý nghĩa |
| --- | --- |
| NAME | Tên object |
| TYPE | Loại object, ví dụ PROCEDURE, FUNCTION, PACKAGE BODY, TRIGGER |
| SEQUENCE | Thứ tự thông báo lỗi |
| LINE | Dòng source liên quan |
| POSITION | Vị trí trong dòng |
| TEXT | Thông báo lỗi |
| ATTRIBUTE | Loại thông báo, thường là ERROR hoặc WARNING |

Tên trong USER_ERRORS được lưu theo quy tắc định danh của object. Với object thông thường không dùng quoted identifier, UPPER(:object_name) là cách truyền tên phổ biến. Nếu object dùng tên quoted có phân biệt hoa/thường, hãy truyền đúng tên.

### 3.2. ALL_ERRORS và DBA_ERRORS

Để xem lỗi ở schema khác:

~~~sql
SELECT
    owner,
    name,
    type,
    sequence,
    line,
    position,
    text,
    attribute
FROM dba_errors
WHERE owner = UPPER(:owner)
  AND name = UPPER(:object_name)
ORDER BY sequence;
~~~

ALL_ERRORS dùng khi chỉ cần lỗi của object mà session có thể truy cập; DBA_ERRORS dành cho tài khoản có quyền xem toàn bộ thông tin.

### 3.3. SHOW ERRORS trong SQL*Plus/SQLcl

Trong SQL*Plus hoặc SQLcl:

~~~sql
SHOW ERRORS PROCEDURE p_rebuild_summary;
SHOW ERRORS PACKAGE BODY pkg_order;
SHOW ERRORS VIEW v_order_summary;
~~~

SHOW ERRORS là lệnh của client, không phải câu SQL gửi trực tiếp đến database. Trong ứng dụng JDBC hoặc công cụ không hỗ trợ lệnh này, hãy truy vấn USER_ERRORS/ALL_ERRORS/DBA_ERRORS.

### 3.4. Lấy source để đối chiếu

Với source PL/SQL:

~~~sql
SELECT
    line,
    text
FROM user_source
WHERE name = UPPER(:object_name)
  AND type = UPPER(:object_type)
ORDER BY line;
~~~

Ở schema khác, có thể dùng ALL_SOURCE hoặc DBA_SOURCE theo quyền. Source giúp đối chiếu dòng lỗi với câu lệnh cụ thể. Với view, lấy DDL bằng DBMS_METADATA.GET_DDL hoặc xem định nghĩa trong các view metadata thích hợp.

Không sửa source chỉ để làm biến mất một thông báo lỗi nếu chưa xác định yêu cầu nghiệp vụ và dependency của object.

## 4. Các nguyên nhân INVALID thường gặp

### 4.1. Source có lỗi cú pháp hoặc kiểu dữ liệu

~~~sql
CREATE OR REPLACE PROCEDURE p_test_invalid AS
BEGIN
    SELECT missing_column
    INTO   l_value
    FROM   employees
    WHERE  employee_id = 100;
END;
/
~~~

Ví dụ trên còn thiếu khai báo biến l_value và cột missing_column có thể không tồn tại. Oracle tạo/ghi nhận object nhưng biên dịch thất bại; USER_ERRORS sẽ chỉ ra lỗi. Sửa source theo schema thực tế rồi compile lại.

### 4.2. Dependency bị DROP, RENAME hoặc thay đổi interface

Procedure có thể tham chiếu view hoặc package. Nếu dependency bị DROP hoặc signature của package thay đổi, dependent có thể INVALID hoặc khi compile báo object không tồn tại/không tương thích.

Ví dụ, procedure gọi:

~~~sql
pkg_customer.get_status(p_customer_id, p_status);
~~~

Nếu package specification đổi tên procedure hoặc kiểu tham số, caller cần được cập nhật theo interface mới rồi compile lại.

### 4.3. Thiếu quyền trực tiếp trong stored PL/SQL

Với stored PL/SQL chạy theo quyền người định nghĩa (definer rights, mặc định nếu không khai báo AUTHID CURRENT_USER), quyền cần cho SQL tĩnh bên trong unit phải được cấp trực tiếp cho owner của unit. Quyền chỉ đến từ role thường không đủ cho compile/execute theo definer-rights semantics.

Ví dụ:

~~~sql
GRANT SELECT ON data_owner.orders TO app_owner;
~~~

Nếu APP_OWNER.P_ORDER_REPORT truy vấn DATA_OWNER.ORDERS, cần quyền trực tiếp phù hợp cho APP_OWNER. Tạo synonym không thay thế quyền object. Synonym chỉ là tên thay thế để phân giải object.

Với invoker-rights unit (AUTHID CURRENT_USER), quyền truy cập khi chạy được xét theo invoker; nhưng dependency, quyền tạo object và ngữ cảnh biên dịch vẫn cần được thiết kế đúng. Khi compile báo thiếu quyền, xác định owner, kiểu AUTHID và privilege thực tế trước khi cấp thêm quyền.

### 4.4. Synonym trỏ sai hoặc dependency ở schema khác

Một procedure có thể tham chiếu synonym thay vì ghi rõ owner.object. Nếu synonym bị thay đổi hoặc target không còn tồn tại, object phụ thuộc có thể không compile được. Hãy truy vấn ALL_SYNONYMS/DBA_SYNONYMS để xác định synonym đang trỏ tới đâu.

### 4.5. Thay đổi package specification

Package specification là interface công khai. Thay đổi tên, kiểu tham số, constant, type hoặc declaration công khai có thể làm caller phụ thuộc cần biên dịch lại. Thay đổi chỉ trong package body thường ít ảnh hưởng đến caller hơn vì interface không đổi, nhưng package body vẫn phải tự compile được.

### 4.6. Dependency remote qua database link

Đối tượng tham chiếu object qua database link có thêm yếu tố remote dependency. Oracle có các chế độ quản lý remote dependency dựa trên timestamp/signature; kết nối, quyền hoặc DDL ở database remote có thể khiến việc compile/execute thất bại. Khi điều tra, ghi lại REFERENCED_LINK_NAME trong dependency view và kiểm tra trạng thái database link/remote object theo quy trình được cấp quyền.

## 5. Biên dịch lại một object cụ thể

Sửa nguyên nhân trước, sau đó compile lại object đúng loại. Compile không tự sửa source hoặc tự cấp quyền.

### 5.1. View

~~~sql
ALTER VIEW v_order_summary COMPILE;
~~~

Sau đó xem lỗi:

~~~sql
SELECT line, position, text
FROM user_errors
WHERE name = 'V_ORDER_SUMMARY'
  AND type = 'VIEW'
ORDER BY sequence;
~~~

### 5.2. Procedure và function

~~~sql
ALTER PROCEDURE p_close_order COMPILE;
ALTER FUNCTION f_order_total COMPILE;
~~~

Nếu compile vẫn lỗi, đọc USER_ERRORS theo tên và type tương ứng.

### 5.3. Package specification và body

~~~sql
ALTER PACKAGE pkg_order COMPILE SPECIFICATION;
ALTER PACKAGE pkg_order COMPILE BODY;
~~~

Specification và body là hai phần khác nhau. Nếu spec INVALID, hãy xử lý spec trước rồi body. Nếu spec VALID nhưng body INVALID, compile body và kiểm tra lỗi loại PACKAGE BODY.

### 5.4. Trigger

~~~sql
ALTER TRIGGER trg_orders_audit COMPILE;
~~~

Trigger có thể INVALID do source hoặc object mà trigger tham chiếu. Không bật/disable trigger như cách thay thế cho việc sửa compile error; trạng thái enable/disable và trạng thái validity là hai vấn đề riêng.

### 5.5. Type và các object khác

Type có cú pháp compile riêng theo loại và trạng thái specification/body. Một số object như materialized view có quy trình xử lý riêng. Hãy dùng SQL Language Reference đúng release cho loại object cụ thể, thay vì chạy một câu ALTER ... COMPILE chung cho tất cả OBJECT_TYPE.

### 5.6. REUSE SETTINGS

Với PL/SQL object, cú pháp compile có thể hỗ trợ REUSE SETTINGS để giữ compiler settings đã lưu trước đó:

~~~sql
ALTER PROCEDURE p_close_order COMPILE REUSE SETTINGS;
ALTER PACKAGE pkg_order COMPILE BODY REUSE SETTINGS;
~~~

Điều này hữu ích khi muốn compile lại mà không vô tình thay đổi các thiết lập compiler của object. Nếu mục tiêu là đổi PL/SQL optimization/debug settings, phải chủ động đặt cấu hình phù hợp và kiểm tra tác động trước.

## 6. Xác nhận object đã VALID sau compile

Không coi việc câu lệnh ALTER ... COMPILE trả về thành công là bằng chứng duy nhất. Kiểm tra trạng thái:

~~~sql
SELECT
    object_name,
    object_type,
    status,
    last_ddl_time
FROM user_objects
WHERE object_name IN (
    'V_ORDER_SUMMARY',
    'P_CLOSE_ORDER',
    'F_ORDER_TOTAL',
    'PKG_ORDER',
    'TRG_ORDERS_AUDIT'
)
ORDER BY object_type, object_name;
~~~

Với package, có thể thấy hai object type riêng là PACKAGE và PACKAGE BODY. Cần kiểm tra cả hai:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'PKG_ORDER'
ORDER BY object_type;
~~~

Kiểm tra lỗi còn lại:

~~~sql
SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'PKG_ORDER'
ORDER BY type, sequence;
~~~

Nếu object đã VALID nhưng runtime vẫn lỗi, cần kiểm tra quyền runtime, dữ liệu, SQL động, database link và các lỗi không phát hiện ở compile time. VALID không có nghĩa mọi đường thực thi nghiệp vụ đều chắc chắn thành công.

## 7. Dependency là gì?

Dependency mô tả object A cần object B để được biên dịch hoặc thực thi. Trong Oracle dependency view:

- OWNER, NAME, TYPE: object **phụ thuộc** (dependent object).
- REFERENCED_OWNER, REFERENCED_NAME, REFERENCED_TYPE: object **được tham chiếu** (referenced object).
- REFERENCED_LINK_NAME: database link nếu dependency là remote.
- DEPENDENCY_TYPE: loại dependency, ví dụ HARD hoặc REF tùy trường hợp.

Ví dụ:

~~~text
APP_OWNER.P_ORDER_REPORT
        |
        | depends on
        v
DATA_OWNER.V_ORDER_SUMMARY
        |
        | depends on
        v
DATA_OWNER.ORDERS
~~~

Nếu ORDERS thay đổi, cần xác định các object trực tiếp và gián tiếp phụ thuộc vào nó. Khi một package spec đổi, cần tìm các caller và object khác phụ thuộc vào interface đó.

## 8. Xem dependency trực tiếp

### 8.1. Object trong schema hiện tại

~~~sql
SELECT
    name AS dependent_name,
    type AS dependent_type,
    referenced_owner,
    referenced_name,
    referenced_type,
    referenced_link_name,
    dependency_type
FROM user_dependencies
WHERE name = UPPER(:dependent_object)
ORDER BY referenced_owner, referenced_type, referenced_name;
~~~

Truy vấn trên trả lời: “Object này đang phụ thuộc vào những object nào?”

### 8.2. Tìm object nào phụ thuộc vào object hiện tại

~~~sql
SELECT
    name AS dependent_name,
    type AS dependent_type,
    referenced_owner,
    referenced_name,
    referenced_type,
    dependency_type
FROM user_dependencies
WHERE referenced_owner = USER
  AND referenced_name = UPPER(:referenced_object)
ORDER BY type, name;
~~~

Truy vấn này chỉ xem các dependent object thuộc schema hiện tại và tham chiếu object được chỉ định. Nếu object được tham chiếu nằm ở schema khác, điều kiện REFERENCED_OWNER phải dùng owner đó.

### 8.3. Toàn database với DBA_DEPENDENCIES

~~~sql
SELECT
    owner,
    name AS dependent_name,
    type AS dependent_type,
    referenced_owner,
    referenced_name,
    referenced_type,
    referenced_link_name,
    dependency_type
FROM dba_dependencies
WHERE referenced_owner = UPPER(:referenced_owner)
  AND referenced_name = UPPER(:referenced_name)
ORDER BY owner, type, name;
~~~

Đây là truy vấn quan trọng khi thay đổi bảng hoặc package dùng chung. Một object trong schema khác có thể phụ thuộc vào object của bạn, vì vậy chỉ xem USER_DEPENDENCIES có thể bỏ sót caller bên ngoài schema.

## 9. Lần theo dependency nhiều cấp

### 9.1. Từ một object tìm các dependent object nhiều cấp

Mỗi hàng trong DBA_DEPENDENCIES biểu diễn dependent object tham chiếu tới referenced object. Có thể dùng CONNECT BY NOCYCLE để lần từ object gốc tới các object phụ thuộc trực tiếp và gián tiếp:

~~~sql
SELECT
    LEVEL AS dependency_level,
    owner,
    name AS dependent_name,
    type AS dependent_type,
    referenced_owner,
    referenced_name,
    referenced_type,
    SYS_CONNECT_BY_PATH(
        owner || '.' || name || ' [' || type || ']',
        ' <- '
    ) AS dependent_path
FROM dba_dependencies
START WITH referenced_owner = UPPER(:root_owner)
   AND referenced_name = UPPER(:root_name)
   AND referenced_type = UPPER(:root_type)
CONNECT BY NOCYCLE
       PRIOR owner = referenced_owner
   AND PRIOR name = referenced_name
   AND PRIOR type = referenced_type
ORDER SIBLINGS BY owner, type, name;
~~~

Đọc hướng cây cẩn thận:

- START WITH chọn những object trực tiếp tham chiếu object gốc.
- Mỗi hàng kết quả là một dependent object.
- CONNECT BY dùng dependent object của cấp trước làm referenced object ở cấp sau.
- NOCYCLE tránh truy vấn lặp vô hạn nếu metadata có quan hệ vòng.

Truy vấn này cho biết phạm vi dependency metadata, không đảm bảo mọi object trong danh sách đều INVALID. Hãy đối chiếu DBA_OBJECTS để xem status và xác định object nào cần xử lý.

### 9.2. Lấy trạng thái của dependent objects

~~~sql
SELECT
    d.owner,
    d.name,
    d.type,
    o.status,
    o.last_ddl_time,
    d.referenced_owner,
    d.referenced_name,
    d.referenced_type
FROM dba_dependencies d
JOIN dba_objects o
  ON o.owner = d.owner
 AND o.object_name = d.name
 AND o.object_type = d.type
WHERE d.referenced_owner = UPPER(:referenced_owner)
  AND d.referenced_name = UPPER(:referenced_name)
ORDER BY d.owner, d.type, d.name;
~~~

Đây là danh sách direct dependents và status hiện tại. Một object có thể xuất hiện nhiều dòng nếu nó tham chiếu nhiều object; vì vậy số dòng không nhất thiết bằng số object duy nhất. Khi cần đếm object, tạo tập distinct theo owner/name/type trước.

### 9.3. Dependency là metadata, không phải toàn bộ quan hệ nghiệp vụ

Dependency view theo dõi các tham chiếu mà Oracle nhận diện được khi tạo object. Những quan hệ được tạo qua dynamic SQL, tên bảng ghép từ chuỗi, job gọi procedure theo tên, application code gọi SQL trực tiếp hoặc cấu hình ngoài database có thể không xuất hiện trong *_DEPENDENCIES.

Ví dụ:

~~~sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM ' || p_table_name
    INTO l_count;
~~~

Oracle không thể luôn biết trước object cụ thể được chọn từ giá trị runtime của P_TABLE_NAME. Vì vậy dependency metadata phải được bổ sung bằng tìm kiếm source, application repository, job metadata và log triển khai.

## 10. Phân biệt dependency trực tiếp và dependency ngược

Khi object INVALID, có hai câu hỏi khác nhau:

1. **Object này cần gì?** Tìm referenced objects mà nó phụ thuộc.
2. **Ai cần object này?** Tìm dependent objects tham chiếu nó.

Ví dụ, nếu PKG_ORDER INVALID vì view V_ORDER_SUMMARY không compile:

- Đi theo dependency của PKG_ORDER để tìm view/package/table mà nó cần.
- Đi ngược dependency từ PKG_ORDER để tìm procedure, trigger hoặc view gọi package.

Đừng compile toàn schema ngay khi chỉ một object lỗi. Tìm dependency gốc trước, sửa prerequisite rồi compile dependent theo thứ tự phù hợp.

## 11. Tác động của thay đổi dependency và invalidation

### 11.1. DDL trên object được tham chiếu

Khi một bảng, view, package specification hoặc object khác thay đổi, Oracle kiểm tra dependency và có thể invalidate dependent object. Sau đó, khi dependent được sử dụng, Oracle có thể tự recompile. Nếu interface vẫn tương thích và quyền đầy đủ, object có thể trở lại VALID mà không cần DBA chạy compile thủ công.

### 11.2. Fine-grained dependency tracking

Oracle theo dõi dependency ở mức chi tiết hơn trong nhiều trường hợp SQL, giúp giảm invalidation khi thay đổi không ảnh hưởng cột/thuộc tính được tham chiếu. Tuy nhiên, không nên dựa vào giả định rằng mọi DDL đều không làm dependent INVALID. Hãy kiểm tra trạng thái thực tế sau deploy và đọc tài liệu dependency management của release đang dùng.

### 11.3. Package specification và body

- Thay đổi **package specification** có thể ảnh hưởng caller vì interface công khai đã thay đổi.
- Thay đổi **package body** mà không thay interface thường không yêu cầu caller recompile chỉ vì body đổi; tuy vậy body vẫn phải compile thành công.
- Thay đổi type hoặc signature dùng trong package interface có thể kéo theo invalidation nhiều cấp.

Đây là lý do nên giữ interface ổn định và tách thay đổi implementation khỏi thay đổi public API khi có thể.

### 11.4. Synonym không phải dependency bảo mật

Synonym giúp phân giải tên object nhưng không cấp quyền truy cập. Nếu synonym tồn tại nhưng user không có privilege trên target, compile/execute vẫn có thể thất bại. Khi điều tra, kiểm tra cả synonym target lẫn quyền object thực tế.

## 12. Quyền cần thiết để compile và chạy

### 12.1. Direct grants cho definer-rights PL/SQL

Mặc định stored PL/SQL chạy theo definer rights. Các quyền object cần cho SQL tĩnh bên trong unit phải được cấp trực tiếp cho schema owner. Quyền nhận qua role không được sử dụng như direct object privilege trong quá trình compile/execute definer-rights unit theo quy tắc tương ứng.

Ví dụ:

~~~sql
-- Chạy bởi DATA_OWNER hoặc DBA có quyền cấp grant.
GRANT SELECT ON data_owner.orders TO app_owner;
GRANT EXECUTE ON common_owner.pkg_currency TO app_owner;
~~~

Sau đó, owner compile lại object:

~~~sql
ALTER PROCEDURE p_order_report COMPILE;
~~~

Không cấp SELECT ANY TABLE hoặc EXECUTE ANY PROCEDURE chỉ để làm object compile được. Cấp đúng privilege trên đúng object theo least privilege.

### 12.2. AUTHID CURRENT_USER

Unit khai báo AUTHID CURRENT_USER chạy theo quyền invoker đối với các thao tác runtime được áp dụng invoker rights. Đây là mô hình bảo mật khác với mặc định definer rights. Hãy kiểm tra declaration của package/procedure và tài liệu PL/SQL Security trước khi thay đổi AUTHID; việc đổi AUTHID có thể thay đổi hành vi bảo mật và không phải cách sửa lỗi compile chung.

### 12.3. Synonym và quyền

Nếu APP_OWNER dùng synonym ORDERS trỏ tới DATA_OWNER.ORDERS, cần có quyền phù hợp trên DATA_OWNER.ORDERS. Tạo synonym không thay thế GRANT.

## 13. Compile nhiều object trong một schema

Sau deploy lớn, có thể cần compile lại các object INVALID của schema. Chỉ thực hiện sau khi đã sửa nguyên nhân gốc; nếu compile hàng loạt khi dependency còn lỗi, nhiều object vẫn sẽ INVALID và tạo thêm log nhiễu.

### 13.1. DBMS_UTILITY.COMPILE_SCHEMA

~~~sql
BEGIN
    DBMS_UTILITY.COMPILE_SCHEMA(
        schema         => 'APP_OWNER',
        compile_all    => FALSE,
        reuse_settings => TRUE
    );
END;
/
~~~

COMPILE_ALL => FALSE chỉ yêu cầu xử lý các object INVALID; TRUE yêu cầu compile cả các object phù hợp trong schema. REUSE_SETTINGS => TRUE yêu cầu giữ compiler settings đã lưu. Tài khoản gọi cần quyền thực hiện phù hợp; khi vận hành schema khác, DBA phải tuân theo quyền và quy trình của môi trường.

### 13.2. UTL_RECOMP

Oracle cung cấp UTL_RECOMP cho việc recompilation hàng loạt, đặc biệt hữu ích sau nâng cấp database hoặc thao tác có nhiều invalid object. Ví dụ chạy serial cho một schema:

~~~sql
BEGIN
    UTL_RECOMP.RECOMP_SERIAL('APP_OWNER');
END;
/
~~~

UTL_RECOMP thường được chạy bởi DBA trong cửa sổ bảo trì và có yêu cầu quyền/điều kiện riêng. Chạy song song có thể giảm thời gian nhưng tăng tải CPU/I/O và contention; hãy đối chiếu signature package của release cụ thể và chọn mức parallel phù hợp. Không chạy đồng thời nhiều công cụ recompilation trên cùng schema nếu chưa có kế hoạch.

### 13.3. Không dùng recompilation hàng loạt để che nguyên nhân

Nếu object INVALID vì bảng/cột đã bị DROP, package spec không còn tương thích hoặc quyền trực tiếp bị thu hồi, chạy COMPILE_SCHEMA lặp lại sẽ không sửa được nguyên nhân. Trước tiên sửa dependency, interface, quyền và source; sau đó compile.

## 14. Theo dõi trạng thái trước và sau deploy

Một đợt deploy schema nên có baseline và post-check.

### 14.1. Lưu snapshot invalid objects

~~~sql
SELECT
    owner,
    object_type,
    object_name,
    status,
    last_ddl_time
FROM dba_objects
WHERE owner IN ('APP_OWNER', 'DATA_OWNER')
  AND status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

Ghi lại kết quả trước deploy để phân biệt object INVALID có sẵn với object bị ảnh hưởng bởi release mới.

### 14.2. Kiểm tra object INVALID sau deploy

~~~sql
SELECT
    owner,
    object_type,
    object_name,
    status,
    last_ddl_time
FROM dba_objects
WHERE owner IN ('APP_OWNER', 'DATA_OWNER')
  AND status = 'INVALID'
ORDER BY owner, object_type, object_name;
~~~

So sánh với baseline, rồi truy vấn DBA_ERRORS và dependency của từng object mới INVALID. Không chỉ so sánh tổng số vì một object có thể được sửa trong khi object khác mới lỗi.

### 14.3. Kiểm tra dependency của các object thay đổi

Trước deploy package specification hoặc table dùng chung, chạy truy vấn dependent object ở mục 8.3 và lưu danh sách. Xác định schema ứng dụng nào có caller phụ thuộc, kế hoạch compile/test và người chịu trách nhiệm.

### 14.4. Ghi nhận trạng thái và lỗi trong bảng vận hành

Với hệ thống triển khai tự động, có thể lưu:

- Release/build ID.
- Object owner/name/type.
- Status trước và sau deploy.
- Error line/position/message.
- Dependency root.
- Thời điểm compile.
- Người/job thực hiện.

Không cần tự tạo một bảng mới nếu công cụ deployment hoặc repository hiện tại đã lưu đầy đủ lịch sử. Mục tiêu là có thể truy nguyên object nào bị INVALID sau thay đổi nào.

## 15. Ví dụ lab: tạo lỗi, đọc lỗi, sửa và compile lại

Thực hành trong schema lab riêng.

### 15.1. Tạo bảng và view hợp lệ

~~~sql
CREATE TABLE lab_departments (
    department_id NUMBER PRIMARY KEY,
    department_name VARCHAR2(80) NOT NULL
);

INSERT INTO lab_departments VALUES (10, 'Engineering');
COMMIT;

CREATE OR REPLACE VIEW lab_department_v AS
SELECT department_id, department_name
FROM lab_departments;
~~~

Kiểm tra:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_DEPARTMENT_V';
~~~

### 15.2. Tạo procedure phụ thuộc vào view

~~~sql
CREATE OR REPLACE PROCEDURE lab_show_department (
    p_department_id IN NUMBER
) AS
    l_name lab_department_v.department_name%TYPE;
BEGIN
    SELECT department_name
    INTO l_name
    FROM lab_department_v
    WHERE department_id = p_department_id;

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

Kiểm tra dependency:

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE name = 'LAB_SHOW_DEPARTMENT'
ORDER BY referenced_owner, referenced_type, referenced_name;
~~~

Procedure có thể tham chiếu view; view lại tham chiếu bảng. Dependency graph giúp nhìn thấy quan hệ nhiều cấp.

### 15.3. Làm view INVALID bằng thay đổi dependency

Đổi tên cột mà view đang tham chiếu:

~~~sql
ALTER TABLE lab_departments
RENAME COLUMN department_name TO department_label;
~~~

Kiểm tra:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'LAB_DEPARTMENT_V',
    'LAB_SHOW_DEPARTMENT'
)
ORDER BY object_type, object_name;
~~~

Trạng thái cụ thể của dependent object có thể được Oracle cập nhật theo dependency/revalidation behavior của release. Hãy dùng kết quả thực tế thay vì giả định mọi object chắc chắn chuyển INVALID ngay tại cùng thời điểm.

### 15.4. Đọc lỗi

~~~sql
SELECT name, type, sequence, line, position, text
FROM user_errors
WHERE name IN ('LAB_DEPARTMENT_V', 'LAB_SHOW_DEPARTMENT')
ORDER BY name, type, sequence;
~~~

Lỗi có thể chỉ ra view không còn tìm thấy DEPARTMENT_NAME; procedure phụ thuộc view cũng có thể cần xác thực lại.

### 15.5. Sửa view và compile dependent

~~~sql
CREATE OR REPLACE VIEW lab_department_v AS
SELECT department_id, department_label AS department_name
FROM lab_departments;

ALTER PROCEDURE lab_show_department COMPILE;
~~~

Kiểm tra lại:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'LAB_DEPARTMENT_V',
    'LAB_SHOW_DEPARTMENT'
)
ORDER BY object_type, object_name;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('LAB_DEPARTMENT_V', 'LAB_SHOW_DEPARTMENT')
ORDER BY name, type, sequence;
~~~

Khi cả view và procedure VALID, chạy thử:

~~~sql
SET SERVEROUTPUT ON;
EXEC lab_show_department(10);
~~~

SET SERVEROUTPUT ON là lệnh client trong SQL*Plus/SQLcl. Nếu công cụ không hỗ trợ, hãy gọi procedure qua cách phù hợp của công cụ và kiểm tra kết quả.

## 16. Thay đổi schema có kiểm soát

Khi một bảng dùng chung sắp đổi cột hoặc package spec sắp đổi signature, nên triển khai theo trình tự:

1. Liệt kê object phụ thuộc trực tiếp và gián tiếp.
2. Tìm caller ngoài schema bằng DBA_DEPENDENCIES, application source và job metadata.
3. Xác định thay đổi có tương thích ngược hay không.
4. Chuẩn bị DDL và source cập nhật cho các dependent object.
5. Deploy prerequisite/interface theo thứ tự phù hợp.
6. Compile và đọc lỗi.
7. Chạy smoke test/integration test cho caller quan trọng.
8. So sánh danh sách INVALID trước và sau deploy.
9. Chỉ đóng release khi object trọng yếu VALID và kiểm thử nghiệp vụ đạt.

DDL trong Oracle có hành vi commit ngầm trước/sau một số lệnh DDL. Không coi chuỗi ALTER/CREATE OR REPLACE là một transaction có thể rollback toàn bộ như DML. Cần có backup/source control và kế hoạch rollback bằng DDL bù trừ.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Object INVALID nhưng không biết lỗi | Chỉ xem OBJECTS, chưa đọc ERRORS | Truy vấn USER_ERRORS/ALL_ERRORS/DBA_ERRORS |
| Package hiển thị hai trạng thái | PACKAGE và PACKAGE BODY là hai object type | Kiểm tra cả spec và body |
| Compile lại nhưng vẫn INVALID | Source/dependency/privilege chưa được sửa | Đọc lỗi mới nhất, sửa nguyên nhân trước |
| Stored procedure không thấy bảng qua role | Definer-rights unit cần direct object grant cho owner | GRANT trực tiếp trên object, compile lại |
| Synonym tồn tại nhưng compile thất bại | Synonym không cấp quyền và có thể trỏ sai target | Kiểm tra ALL_SYNONYMS và privilege trên target |
| Chỉ xem USER_DEPENDENCIES bỏ sót caller | Caller thuộc schema khác | Dùng DBA_DEPENDENCIES nếu có quyền |
| Thay đổi bảng làm nhiều object INVALID | Dependency bị ảnh hưởng bởi DDL | Lập dependency impact list, compile theo prerequisite |
| Compile schema lặp lại không sửa được lỗi | Nguyên nhân gốc vẫn tồn tại | Sửa interface, source, quyền hoặc referenced object |
| Dynamic SQL không có trong dependency view | Object name được quyết định lúc runtime | Tìm source, job metadata và application code |
| VALID nhưng chạy vẫn lỗi | Compile không kiểm tra mọi dữ liệu/runtime path | Kiểm tra quyền runtime, SQL động, database link và dữ liệu |
| Dùng compile syntax sai loại object | Mỗi object type có DDL riêng | Tra SQL Language Reference đúng release |
| Recompile song song gây tải hệ thống | Nhiều compile đồng thời dùng CPU/I/O | Chạy trong maintenance window và giới hạn parallelism |

## 18. Bài tập thực hành

Sử dụng schema lab ở mục 15.

### Bài 1 — Liệt kê object INVALID

Tạo một procedure có lỗi compile. Dùng USER_OBJECTS để tìm object INVALID và giải thích vì sao object vẫn tồn tại trong data dictionary.

### Bài 2 — Đọc compile errors

Dùng USER_ERRORS để lấy line, position, text và sequence. So sánh với SHOW ERRORS trong SQL*Plus/SQLcl.

### Bài 3 — Sửa dependency

Tạo view tham chiếu bảng, rồi procedure tham chiếu view. Đổi tên một cột trong bảng và quan sát object nào cần revalidation. Sửa view và compile procedure.

### Bài 4 — Dependency hai chiều

Dùng USER_DEPENDENCIES để trả lời: procedure phụ thuộc object nào? Sau đó tìm object nào phụ thuộc vào view. Vẽ graph theo hướng dependent → referenced.

### Bài 5 — Dependency nhiều schema

Giả lập owner dữ liệu và owner ứng dụng khác nhau. Cấp quyền trực tiếp cho app owner, tạo procedure definer-rights tham chiếu bảng dữ liệu, sau đó thu hồi grant và quan sát compile/execute error. Cấp lại đúng quyền rồi compile.

### Bài 6 — Package specification và body

Tạo package có một procedure public, một caller. Thay đổi signature trong specification và xem các caller phụ thuộc. Sau đó chỉ sửa body nhưng giữ interface, so sánh ảnh hưởng.

### Bài 7 — Compile schema

Tạo một vài object INVALID trong schema lab, chạy DBMS_UTILITY.COMPILE_SCHEMA với COMPILE_ALL => FALSE, rồi kiểm tra status và errors. Không chạy recompilation hàng loạt trên schema production để thử nghiệm.

### Bài 8 — Lập impact analysis

Chọn một bảng hoặc package dùng chung. Truy vấn direct dependents, lần dependency nhiều cấp và liệt kê object thuộc schema khác. Đề xuất thứ tự deploy, compile và test.

## 19. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi đã hoàn thành bài tập:

~~~sql
DROP PROCEDURE lab_show_department;
DROP VIEW lab_department_v;
DROP TABLE lab_departments PURGE;
~~~

Xóa dependent object trước prerequisite để tránh để lại object tham chiếu tới object đã xóa. PURGE bỏ qua recycle bin; không dùng với object nghiệp vụ hoặc dữ liệu cần khôi phục.

## Tổng kết

INVALID là trạng thái cần điều tra, không phải nguyên nhân. Bắt đầu bằng USER_OBJECTS/ALL_OBJECTS/DBA_OBJECTS, sau đó đọc USER_ERRORS/ALL_ERRORS/DBA_ERRORS để biết dòng lỗi và loại thông báo. Sửa source, referenced object hoặc direct privilege trước khi compile lại đúng loại object; với package, kiểm tra cả specification lẫn body.

Dependency view cho biết object nào phụ thuộc vào object nào: NAME/TYPE là dependent, REFERENCED_OWNER/NAME/TYPE là prerequisite. Dùng dependency hai chiều và nhiều cấp để đánh giá tác động trước deploy, nhưng bổ sung tìm kiếm dynamic SQL, job và application code vì metadata không ghi nhận mọi quan hệ runtime. Sau compile, xác nhận status, errors và kiểm thử đường chạy nghiệp vụ. Recompilation hàng loạt chỉ nên thực hiện sau khi dependency root đã được sửa và trong cửa sổ vận hành phù hợp.

## Tài liệu Oracle tham khảo

- [Oracle Database Reference — USER_OBJECTS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_OBJECTS.html) — trạng thái object trong schema hiện tại.
- [Oracle Database Reference — DBA_OBJECTS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_OBJECTS.html) — metadata object toàn database.
- [Oracle Database Reference — USER_ERRORS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_ERRORS.html) — compile diagnostics.
- [Oracle Database Reference — DBA_DEPENDENCIES (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DEPENDENCIES.html) — dependency giữa schema objects.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_UTILITY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_UTILITY.html) — COMPILE_SCHEMA.
- [Oracle Database PL/SQL Packages and Types Reference — UTL_RECOMP (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_RECOMP.html) — recompilation utilities.
- [Oracle Database PL/SQL Language Reference — Invoker's Rights and Definer's Rights (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html) — quyền thực thi PL/SQL.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu SQL Language Reference, PL/SQL Language Reference và Reference đúng phiên bản, đặc biệt cú pháp compile theo object type, dependency invalidation và quyền của công cụ recompilation.
