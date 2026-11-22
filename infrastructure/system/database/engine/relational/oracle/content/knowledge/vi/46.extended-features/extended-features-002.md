# So sánh phạm vi SQL/PLSQL giữa hệ thống 19c và các bản Oracle mới hơn

Oracle Database 19c vẫn là một nền tảng quan trọng cho các hệ thống production, nhưng phạm vi SQL và PL/SQL đã tiếp tục mở rộng qua các release 21c, 23ai và 26ai. Sự khác biệt không chỉ nằm ở số lượng câu lệnh mới. Các bản mới bổ sung kiểu dữ liệu, cú pháp DDL/DML, cách biểu diễn JSON, khả năng tích hợp SQL với PL/SQL, công cụ tối ưu hóa và những mô hình ứng dụng mới.

Khi so sánh, cần phân biệt **phiên bản cơ sở** với **Release Update (RU)**. Một số tính năng đã được đưa ngược về Oracle 19c ở các RU mới. Ví dụ, SQL table macro có từ 19c RU 19.7; cú pháp IF EXISTS/IF NOT EXISTS và schema annotations được hỗ trợ từ 19c RU 19.28. Vì vậy, câu nói “19c không có IF NOT EXISTS” chỉ đúng với các RU trước 19.28, không đúng với mọi hệ thống đang chạy 19c.

Bài học dùng tài liệu Oracle Database 19c, 21c, 23ai và Oracle AI Database 26ai làm mốc. Nội dung tập trung vào:
- Cách đọc đúng phiên bản, RU, COMPATIBLE và khả năng thực tế của hệ thống.
- Khác biệt giữa SQL engine, PL/SQL engine và các tính năng giao tiếp giữa hai engine.
- Tiến hóa của kiểu dữ liệu SQL, đặc biệt BOOLEAN, JSON và VECTOR.
- DDL/DML mới: IF EXISTS, multivalue INSERT, VALUES constructor, JOIN trong UPDATE/DELETE và RETURNING.
- SQL macros, SQL Transpiler, PL/SQL CASE mở rộng và JSON aggregate mapping.
- SQL Domains, annotations, JSON-Relational Duality và SQL Property Graph.
- Aggregation FILTER, GROUP BY ALL, GROUP BY alias/position và các cải tiến 26ai.
- Ảnh hưởng tới ứng dụng cũ, JDBC/client, migration, kiểm thử và chiến lược tương thích.

Các ví dụ mang tính minh họa cho Oracle Database 19c trở lên. Cú pháp chính xác, giới hạn, RU yêu cầu và khả năng triển khai còn phụ thuộc nền tảng, cấu hình, COMPATIBLE, driver/client, edition và các điều kiện cấp phép. Trước khi đưa cú pháp mới vào production, đối chiếu tài liệu đúng release và RU đang cài đặt.

## 1. Cách hiểu phạm vi phiên bản

### 1.1. 19c, 21c, 23ai và 26ai

| Dòng phát hành | Vai trò trong so sánh | Điểm đáng chú ý |
| --- | --- | --- |
| Oracle Database 19c | Bản nền phổ biến cho hệ thống hiện hữu | SQL/PLSQL ổn định; có nhiều tính năng được bổ sung qua RU |
| Oracle Database 21c | Bản innovation giữa 19c và 23ai | SQL macros scalar, kiểu JSON SQL dạng nhị phân và nhiều mở rộng cho developer |
| Oracle Database 23ai | Bản innovation tập trung vào developer và AI | SQL BOOLEAN, SQL Domains, multivalue INSERT, VALUES, JSON-Relational Duality, VECTOR và nhiều cú pháp SQL mới |
| Oracle AI Database 26ai | Bản Long Term Support kế tiếp theo tài liệu Oracle 2026 | Mở rộng SQL/PLSQL, JSON, vector, SQL Transpiler, aggregation và tích hợp ứng dụng |

Tên sản phẩm thay đổi theo thời gian. Tài liệu 23ai có thể vẫn xuất hiện dưới tên Oracle Database 23ai; tài liệu 26ai dùng tên Oracle AI Database 26ai. Khi đọc tài liệu, phải xác nhận release và ngày tài liệu, không chỉ nhìn tên marketing.

### 1.2. Phiên bản cơ sở không phải toàn bộ câu chuyện

Oracle phát hành RU theo chu kỳ. Một database có thể báo 19c nhưng đã có nhiều cú pháp được bổ sung ở RU sau này. Ngược lại, một hệ thống được gọi là 23ai hoặc 26ai có thể chưa cài RU cần thiết cho một tính năng cụ thể.

Các mốc quan trọng trong nhánh 19c:
- Từ 19c RU 19.7: hỗ trợ SQL table macros.
- Từ 19c RU 19.28: hỗ trợ IF [NOT] EXISTS cho các DDL được liệt kê trong tài liệu và schema annotations.
- RU 19.28 còn bổ sung package DBMS_DEVELOPER để lấy metadata object dưới dạng JSON CLOB.

Khi viết tài liệu kiến trúc hoặc migration plan, hãy ghi đủ dạng: Oracle Database 19c RU 19.xx, 21c release, 23ai release/RU hoặc 26ai RU cụ thể.

### 1.3. SQL và PL/SQL có phạm vi khác nhau

SQL là ngôn ngữ truy vấn và thao tác dữ liệu. PL/SQL là ngôn ngữ thủ tục của Oracle, hỗ trợ biến, điều kiện, vòng lặp, exception, package, procedure, function và trigger.

Một kiểu dữ liệu có thể tồn tại trong PL/SQL nhưng không được dùng làm kiểu cột SQL. Đây là ví dụ điển hình với BOOLEAN:
- Trong 19c, PL/SQL có BOOLEAN, nhưng SQL chưa có cột BOOLEAN native.
- Từ 23ai, SQL có kiểu BOOLEAN native.
- Trong 26ai, khả năng tương tác giữa SQL BOOLEAN và PL/SQL BOOLEAN được mở rộng thêm.

Do đó, khi đọc tài liệu tính năng, hãy hỏi: tính năng thuộc SQL, PL/SQL, cả hai hay chỉ là API của một client/driver?

## 2. Kiểm tra phiên bản và RU trên hệ thống

### 2.1. Kiểm tra version

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

Có thể xem thông tin component:

~~~sql
SELECT product, version, status
FROM product_component_version
ORDER BY product;
~~~

Một số hệ thống hiển thị banner khác nhau theo deployment. Không dùng riêng chuỗi banner để suy ra mọi tính năng đã được cài.

### 2.2. Kiểm tra RU/SQL patch

DBA có thể xem lịch sử SQL patch:

~~~sql
SELECT
    patch_id,
    patch_type,
    action,
    status,
    action_time,
    description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

Để xác định RU và binary patch đầy đủ, kết hợp thông tin SQL patch với inventory của Oracle Home, chẳng hạn kết quả OPatch lsinventory do DBA/OS administrator thu thập. Một số patch được áp dụng ở Oracle Home nhưng chưa hoàn tất datapatch; khi đó trạng thái binary và SQL registry có thể không đồng nhất.

### 2.3. Kiểm tra COMPATIBLE

~~~sql
SHOW PARAMETER compatible;
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

COMPATIBLE là một ràng buộc tương thích định dạng và khả năng database. Một số kiểu dữ liệu/tính năng yêu cầu giá trị COMPATIBLE tối thiểu. Ví dụ, kiểu JSON SQL native của 21c yêu cầu COMPATIBLE phù hợp theo tài liệu 21c. Không nâng COMPATIBLE chỉ để thử cú pháp nếu chưa đánh giá khả năng downgrade, backup và quy trình nâng cấp.

### 2.4. Kiểm tra capability thay vì đoán theo tên release

Quy trình xác định tính năng nên là:
1. Xác nhận database release.
2. Xác nhận RU/patch.
3. Xác nhận COMPATIBLE.
4. Kiểm tra tài liệu tính năng ghi rõ release/RU hỗ trợ.
5. Kiểm tra quyền và điều kiện cấu hình.
6. Chạy thử câu lệnh trong schema lab.
7. Kiểm tra client, driver và framework có nhận kiểu dữ liệu/cú pháp mới hay không.

Không nên dựa vào một câu như “chạy Oracle 19c” để kết luận mọi cú pháp 19c giống nhau.

## 3. Bảng so sánh tổng quan SQL/PLSQL

| Khả năng | 19c cơ sở | 19c RU mới | 21c | 23ai | 26ai |
| --- | --- | --- | --- | --- | --- |
| PL/SQL BOOLEAN | Có | Có | Có | Có | Có, tương tác SQL rộng hơn |
| SQL BOOLEAN column | Không | Không | Không | Có | Có, thêm khả năng tương tác PL/SQL |
| SQL table macro | Từ RU 19.7 | Có | Có | Có | Có |
| SQL scalar macro | Không phải khả năng của 19c cơ sở | Kiểm tra RU/tài liệu | Có | Có | Có |
| IF [NOT] EXISTS DDL | Không ở RU cũ | Từ RU 19.28 cho DDL được hỗ trợ | Có theo release | Có | Có |
| Schema annotations | Không ở RU cũ | Từ RU 19.28 | Tùy release | Có | Có, thêm tích hợp |
| Native SQL JSON data type | Không | Không | Có | Có | Có, thêm JSON features |
| SQL Domains | Không | Không | Không | Có | Có, thêm data use case domains |
| Multivalue INSERT | Không | Không | Không | Có | Có |
| VALUES table constructor | Không theo cú pháp mới | Không | Không | Có | Có |
| SELECT bỏ FROM | Không | Không | Không | Có | Có |
| Alias trong GROUP BY | Không | Không | Không theo cú pháp 23ai | Có | Có thêm vị trí, HAVING và GROUP BY ALL |
| RETURNING trong UPDATE/MERGE tĩnh | Giới hạn theo cú pháp cũ | Giới hạn theo cú pháp cũ | Kiểm tra release | Có | Có thêm khả năng OLD/NEW trên DML |
| JOIN trực tiếp trong UPDATE/DELETE | Không | Không | Không theo cú pháp 23ai | Có | Có |
| SQL VECTOR | Không | Không | Không | Có | Có; PL/SQL vector mở rộng |
| JSON-Relational Duality View | Không | Không | Không | Có | Có thêm nhiều tính năng |
| SQL Transpiler PL/SQL-to-SQL | Không | Không | Không | Không phải tính năng nền | Có |
| Aggregate FILTER | Không | Không | Không | Không theo tài liệu 26ai | Có |
| GROUP BY ALL | Không | Không | Không | Không | Có |
| SUM/AVG cho INTERVAL | Không theo phạm vi 19c | Không | Không | Tài liệu SQL ghi hỗ trợ từ release 23 | Có |

Bảng này là bản đồ định hướng, không thay thế tài liệu SQL Language Reference. Một số khả năng được backport theo RU hoặc có điều kiện deployment. Các dòng có ghi “kiểm tra release” phải được xác minh theo patch cụ thể.

## 4. BOOLEAN: từ PL/SQL sang SQL

### 4.1. Oracle 19c

PL/SQL 19c có kiểu BOOLEAN với ba trạng thái logic: TRUE, FALSE và NULL (unknown).

Ví dụ PL/SQL hợp lệ:

~~~sql
DECLARE
    l_enabled BOOLEAN := TRUE;
BEGIN
    IF l_enabled THEN
        DBMS_OUTPUT.PUT_LINE('Enabled');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Disabled or unknown');
    END IF;
END;
/
~~~

Tuy nhiên SQL 19c không có kiểu BOOLEAN native cho table column. Không thể tạo cột BOOLEAN hoặc dùng BOOLEAN expression tùy ý trong SQL. Ứng dụng thường mô phỏng bằng NUMBER(1), CHAR(1) hoặc VARCHAR2 với CHECK constraint.

~~~sql
CREATE TABLE feature_flags (
    flag_id NUMBER PRIMARY KEY,
    enabled NUMBER(1) NOT NULL,
    CONSTRAINT feature_flags_enabled_ck
        CHECK (enabled IN (0, 1))
);
~~~

### 4.2. Oracle 23ai

SQL có BOOLEAN native:

~~~sql
CREATE TABLE feature_flags (
    flag_id NUMBER PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE NOT NULL
);

INSERT INTO feature_flags (flag_id, enabled)
VALUES (1, TRUE);

SELECT flag_id
FROM feature_flags
WHERE enabled = TRUE;
~~~

Điều này giúp schema thể hiện rõ ý nghĩa logic, thay vì phải thống nhất quy ước 0/1 hoặc Y/N ở nhiều ứng dụng.

BOOLEAN vẫn có ba giá trị logic. NULL không phải FALSE; điều kiện có thể có kết quả UNKNOWN. Vì vậy cần thiết kế NOT NULL/default và kiểm thử predicate trong WHERE, CASE, JOIN và constraint.

### 4.3. Oracle 26ai và tương tác PL/SQL

26ai mở rộng cách sử dụng BOOLEAN giữa SQL và PL/SQL:
- Stored PL/SQL function có tham số BOOLEAN có thể được gọi trực tiếp từ SQL với BOOLEAN expression/literal theo khả năng được tài liệu hóa.
- BOOLEAN hỗ trợ trong các trường hợp SELECT INTO và BULK COLLECT INTO trong PL/SQL.
- Có chuyển đổi BOOLEAN với number/character và các hàm chuyển đổi liên quan.
- BOOLEAN được hỗ trợ trong bind, trigger và một số interface như OCI, dynamic SQL, DBMS_SQL.
- PL/SQL có thể dùng BOOLEAN như kiểu scalar độc lập trong ngữ cảnh được hỗ trợ.

Ví dụ 26ai:

~~~sql
CREATE OR REPLACE FUNCTION is_large_order(
    p_amount NUMBER
) RETURN BOOLEAN
IS
BEGIN
    RETURN p_amount >= 10000;
END;
/

SELECT is_large_order(15000) AS large_order
FROM dual;
~~~

Trong môi trường 23ai/26ai, kiểm tra SQL BOOLEAN và BOOLEAN PL/SQL interoperability theo release. Một function có kiểu trả về/đối số BOOLEAN có thể không chạy trên 19c theo cách viết trên.

### 4.4. Chiến lược tương thích 19c

Nếu cùng một ứng dụng phải chạy trên 19c và 23ai:
- Dùng NUMBER(1) hoặc CHAR(1) làm contract dữ liệu chung nếu cần schema dùng chung.
- Hoặc tách migration schema theo version và chuyển đổi ở tầng repository.
- Không đưa BOOLEAN column vào DDL chung nếu target 19c cũ phải parse DDL đó.
- Dùng API mapping thống nhất trong Java/.NET để tránh rải quy tắc 0/1/Y/N.
- Kiểm tra driver version và metadata mapping khi chuyển sang BOOLEAN native.

## 5. JSON: từ văn bản sang kiểu dữ liệu và mô hình quan hệ-tài liệu

### 5.1. 19c

Oracle 19c có thể lưu JSON trong VARCHAR2, CLOB hoặc BLOB, kèm constraint IS JSON và các hàm SQL/JSON như JSON_VALUE, JSON_QUERY, JSON_EXISTS, JSON_TABLE.

Ví dụ:

~~~sql
CREATE TABLE api_events (
    event_id NUMBER PRIMARY KEY,
    payload CLOB CHECK (payload IS JSON)
);

SELECT
    JSON_VALUE(payload, '$.eventType') AS event_type
FROM api_events;
~~~

JSON được lưu dưới dạng dữ liệu văn bản/serialized trong các kiểu cột này. 19c có nhiều khả năng xử lý JSON, nhưng chưa có native SQL JSON data type như 21c.

### 5.2. 21c

21c giới thiệu kiểu dữ liệu SQL JSON chuyên dụng, lưu dữ liệu theo binary JSON format. Kiểu này giúp xử lý nested JSON hiệu quả hơn và giảm việc parse văn bản lặp lại.

Ví dụ minh họa:

~~~sql
CREATE TABLE event_documents (
    event_id NUMBER PRIMARY KEY,
    payload JSON
);
~~~

Khả năng sử dụng kiểu JSON phụ thuộc COMPATIBLE theo yêu cầu release. Khi nâng từ 19c, phải kiểm tra ứng dụng, driver và công cụ export/import có hỗ trợ kiểu JSON native hay không.

### 5.3. 23ai và JSON-Relational Duality

JSON-Relational Duality Views cho phép ứng dụng đọc/cập nhật dữ liệu quan hệ dưới dạng JSON document. Dữ liệu vẫn được lưu trong relational table đã chuẩn hóa; duality view cung cấp document view có thể cập nhật.

Lợi ích:
- Ứng dụng document-oriented có thể làm việc với JSON.
- Ứng dụng SQL vẫn truy cập dữ liệu relational.
- Cả hai cách nhìn dùng chung dữ liệu nguồn.
- Giảm nhu cầu tự viết nhiều tầng chuyển đổi JSON và relational.

Duality view không có nghĩa database biến toàn bộ table thành document store. Phải thiết kế mapping, key, relationship, update semantics và quyền truy cập theo tài liệu.

### 5.4. 26ai và mở rộng JSON/PLSQL

26ai mở rộng JSON constructor và JSON_VALUE để làm việc với PL/SQL aggregate types như record và collection. JSON constructor có thể tạo JSON object/array từ aggregate; JSON_VALUE có thể ánh xạ JSON trở lại kiểu aggregate theo RETURNING.

Điều này giúp trao đổi dữ liệu giữa PL/SQL và ứng dụng dùng JSON mà không phải tự tuần tự hóa từng trường bằng nhiều đoạn code.

Ví dụ khái niệm:

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id NUMBER,
        employee_name VARCHAR2(100)
    );

    l_employee employee_rec;
    l_json JSON;
BEGIN
    l_employee.employee_id := 10;
    l_employee.employee_name := 'Lan';

    l_json := JSON(l_employee);
END;
/
~~~

Đây là minh họa về hướng hỗ trợ aggregate-to-JSON; cú pháp overload và kiểu JSON cụ thể cần kiểm tra trong PL/SQL Language Reference của 26ai.

## 6. VECTOR và AI Vector Search

### 6.1. Phạm vi 19c/21c

Oracle 19c và 21c không có SQL VECTOR data type theo mô hình AI Vector Search của các release mới. Nếu cần lưu embedding ở 19c, ứng dụng thường phải dùng BLOB, RAW hoặc một biểu diễn số/JSON và tự quản lý index/search logic.

Các cách thay thế này không tương đương native vector indexing và similarity search.

### 6.2. 23ai

23ai giới thiệu VECTOR data type và khả năng AI Vector Search. Vector lưu biểu diễn số nhiều chiều, thường là embedding của văn bản, hình ảnh hoặc dữ liệu khác. SQL có thể dùng vector distance/similarity và vector index theo khả năng release.

Ví dụ khái niệm:

~~~sql
CREATE TABLE document_embeddings (
    document_id NUMBER PRIMARY KEY,
    embedding VECTOR(3, FLOAT32)
);
~~~

Kích thước và format trong ví dụ chỉ minh họa. Chọn dimension, format và index theo model embedding thực tế.

### 6.3. 26ai và PL/SQL VECTOR

26ai bổ sung hỗ trợ VECTOR trong PL/SQL như một họ kiểu scalar riêng. Các RU 26ai tiếp tục mở rộng:
- Hỗ trợ BINARY vector và Jaccard distance trong RU tương ứng.
- Arithmetic theo từng dimension trong PL/SQL.
- SPARSE vector trong RU tương ứng.
- Các phép toán vector và khả năng liên quan AI Vector Search.

Với RAC hoặc môi trường có patch riêng, cần đọc ghi chú RU và điều kiện patch. Ví dụ tài liệu 26ai nêu yêu cầu patch bổ sung cho một số trường hợp SPARSE vector trong RAC.

## 7. DDL: IF [NOT] EXISTS và annotations

### 7.1. IF NOT EXISTS trong 19c RU 19.28

19c bản RU cũ không có cú pháp này cho các DDL thông dụng. Từ RU 19.28, Oracle hỗ trợ IF NOT EXISTS trên các CREATE statement được liệt kê trong tài liệu, và IF EXISTS trên các ALTER/DROP statement được hỗ trợ.

Ví dụ:

~~~sql
CREATE TABLE IF NOT EXISTS migration_log (
    log_id NUMBER PRIMARY KEY,
    message VARCHAR2(200)
);
~~~

Ví dụ drop:

~~~sql
DROP TABLE IF EXISTS migration_log;
~~~

Không được suy luận rằng mọi câu lệnh CREATE/ALTER/DROP đều hỗ trợ. Đọc danh sách object type và restriction trong SQL Language Reference đúng RU. IF NOT EXISTS cũng không kết hợp tùy tiện với OR REPLACE trong cùng CREATE statement.

### 7.2. 23ai

23ai mở rộng trải nghiệm DDL với IF [NOT] EXISTS như một tính năng developer productivity. Script có thể viết idempotent hơn và tránh một số nhánh kiểm tra object tồn tại trước khi tạo/xóa.

Tuy nhiên, IF NOT EXISTS không kiểm tra xem object đã tồn tại có đúng cấu trúc mong muốn hay không. Nếu table đã tồn tại nhưng sai cột/constraint, lệnh có thể không thay đổi nó. Migration vẫn cần kiểm tra metadata và schema drift.

### 7.3. Schema annotations

Annotations là metadata tự do gắn vào object hoặc column. Có thể dùng để lưu display label, mô tả, owner nghiệp vụ hoặc metadata cho công cụ phát triển.

Annotations có trong 23ai, nhưng cũng đã được backport về 19c RU 19.28. Vì vậy phải kiểm tra RU khi dùng ở hệ thống 19c.

Ví dụ:

~~~sql
CREATE TABLE employee_notes (
    employee_id NUMBER,
    employee_name VARCHAR2(100)
)
ANNOTATIONS (purpose 'Employee master data');
~~~

Ví dụ gắn annotation cho column:

~~~sql
ALTER TABLE employee_notes
MODIFY (employee_name ANNOTATIONS (display 'Employee name'));
~~~

Metadata có thể đọc qua các view như USER_ANNOTATIONS hoặc USER_ANNOTATIONS_USAGE theo object và quyền. Annotation là metadata; nó không tự thực thi validation hoặc bảo mật dữ liệu.

### 7.4. SQL Domains

SQL Domains là object trong data dictionary để định nghĩa domain tái sử dụng với kiểu dữ liệu và các thuộc tính/constraint. Từ 23ai, domain giúp mô tả một loại giá trị nghiệp vụ dùng chung, ví dụ email, mã bưu chính hoặc năm sinh.

Ví dụ:

~~~sql
CREATE DOMAIN email_address AS VARCHAR2(254)
    CONSTRAINT email_address_ck
    CHECK (REGEXP_LIKE(VALUE, '^[^@]+@[^@]+[.][^@]+$'));

CREATE TABLE application_users (
    user_id NUMBER PRIMARY KEY,
    email email_address
);
~~~

Domain giúp giảm lặp lại constraint giữa các table. Tuy nhiên cần kiểm tra domain behavior, metadata, Data Pump và khả năng tương thích target khi migrate về 19c. Domain object không tồn tại trong 19c bản thông thường.

## 8. SELECT không cần FROM và VALUES constructor

### 8.1. SELECT trong 19c

Trong 19c, truy vấn chỉ trả biểu thức thường dùng DUAL:

~~~sql
SELECT SYSDATE FROM dual;
SELECT 10 * 20 AS result FROM dual;
SELECT SYS_CONTEXT('USERENV', 'CURRENT_USER') FROM dual;
~~~

### 8.2. SELECT trong 23ai

23ai cho phép bỏ FROM khi không cần đọc table:

~~~sql
SELECT SYSDATE;
SELECT 10 * 20 AS result;
SELECT SYS_CONTEXT('USERENV', 'CURRENT_USER');
~~~

Đây là thay đổi cú pháp nhỏ nhưng ảnh hưởng parser và SQL generator của ORM, query builder, report tool và ứng dụng sinh SQL.

### 8.3. VALUES constructor

23ai cho phép dùng table value constructor để tạo tập row nhỏ ngay trong SQL:

~~~sql
SELECT *
FROM (VALUES
    (10, 'HR'),
    (20, 'IT'),
    (30, 'FINANCE')
) departments(department_id, department_name);
~~~

Điều này hữu ích cho lookup tạm thời, ad-hoc query hoặc dữ liệu nhỏ được nhúng trong câu lệnh. Không nên dùng VALUES constructor thay staging table hoặc bulk load cho tập dữ liệu lớn.

### 8.4. Multivalue INSERT

Trước 23ai, có thể cần nhiều INSERT hoặc INSERT ALL. 23ai cho phép nhiều tuple trong một INSERT:

~~~sql
INSERT INTO departments (department_id, department_name)
VALUES
    (10, 'HR'),
    (20, 'IT'),
    (30, 'FINANCE');
~~~

Lợi ích là một statement và một transaction boundary rõ ràng hơn cho một nhóm tuple. Với tải lớn, vẫn nên đánh giá array binding, direct path, external table hoặc bulk load thay vì tạo một statement cực lớn.

## 9. GROUP BY alias, position và GROUP BY ALL

### 9.1. 19c

Trong 19c, thường phải lặp lại expression:

~~~sql
SELECT
    TO_CHAR(order_date, 'YYYY') AS order_year,
    COUNT(*) AS order_count
FROM orders
GROUP BY TO_CHAR(order_date, 'YYYY');
~~~

### 9.2. 23ai

23ai cho phép tham chiếu alias trong GROUP BY:

~~~sql
SELECT
    TO_CHAR(order_date, 'YYYY') AS order_year,
    COUNT(*) AS order_count
FROM orders
GROUP BY order_year;
~~~

Điều này giảm lặp expression và giúp query dễ đọc hơn. Cần chú ý tên alias trùng với tên column và phạm vi alias trong query block.

### 9.3. 26ai

26ai mở rộng GROUP BY để hỗ trợ alias hoặc vị trí SELECT item trong GROUP BY, GROUP BY CUBE, ROLLUP, GROUPING SETS và hỗ trợ alias trong HAVING. Ngoài ra có GROUP BY ALL để tự nhóm theo các biểu thức không aggregate trong select list.

Ví dụ GROUP BY ALL:

~~~sql
SELECT
    department_id,
    job_id,
    COUNT(*) AS employee_count,
    AVG(salary) AS average_salary
FROM employees
GROUP BY ALL;
~~~

GROUP BY ALL tiện cho query ad-hoc và prototype. Với query production phức tạp, vẫn nên ghi rõ grouping key khi muốn hợp đồng SQL ổn định, dễ review và ít bị ảnh hưởng khi select list thay đổi.

## 10. DML: UPDATE/DELETE có JOIN

### 10.1. 19c

Trong 19c, muốn cập nhật theo điều kiện từ table khác thường dùng subquery hoặc MERGE:

~~~sql
UPDATE employees e
SET e.salary = e.salary * 1.05
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments d
    WHERE d.department_name = 'RESEARCH'
);
~~~

### 10.2. 23ai trở lên

23ai hỗ trợ JOIN trực tiếp trong UPDATE/DELETE với FROM clause:

~~~sql
UPDATE employees e
SET e.salary = e.salary * 1.05
FROM departments d
WHERE e.department_id = d.department_id
  AND d.department_name = 'RESEARCH';
~~~

Điều này làm câu lệnh gần với cách viết của nhiều hệ quản trị khác và có thể giúp query dễ đọc hơn. Cần kiểm tra cú pháp JOIN được hỗ trợ, alias, cardinality và khả năng một row đích khớp nhiều row nguồn. Không chuyển đổi máy móc từ MERGE sang JOIN UPDATE nếu logic match/insert khác nhau.

### 10.3. Tương thích ngược

Nếu ứng dụng phải chạy cả 19c và 23ai:
- Giữ subquery hoặc MERGE cho SQL chung.
- Dùng phiên bản SQL riêng theo capability khi lợi ích đáng kể.
- Đừng gửi cú pháp JOIN UPDATE mới đến server 19c cũ.
- Kiểm thử row count, duplicate source match và execution plan trước khi thay đổi.

## 11. RETURNING: từ DML cũ đến OLD/NEW

### 11.1. 19c

Oracle 19c đã hỗ trợ RETURNING INTO cho INSERT, UPDATE và DELETE trong những phạm vi được tài liệu hóa. PL/SQL có thể dùng biến hoặc BULK COLLECT cho trường hợp nhiều row. Dynamic SQL cũng có dạng RETURNING INTO riêng.

Ví dụ UPDATE một row:

~~~sql
DECLARE
    l_new_salary NUMBER;
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE employee_id = 100
    RETURNING salary INTO l_new_salary;

    DBMS_OUTPUT.PUT_LINE(l_new_salary);
END;
/
~~~

### 11.2. 23ai

23ai bổ sung RETURNING cho UPDATE và MERGE trong DML tĩnh, bao gồm cách lấy giá trị OLD và NEW trong các trường hợp hỗ trợ.

~~~sql
DECLARE
    l_old_salary NUMBER;
    l_new_salary NUMBER;
BEGIN
    UPDATE employees
    SET salary = salary + 1000
    WHERE employee_id = 100
    RETURNING OLD salary, NEW salary
    INTO l_old_salary, l_new_salary;
END;
/
~~~

MERGE cũng có thể dùng RETURNING theo cú pháp và điều kiện được hỗ trợ trong release.

### 11.3. 26ai

26ai tiếp tục mở rộng RETURNING để lấy OLD/NEW values thống nhất hơn trên INSERT, UPDATE, DELETE và MERGE:
- UPDATE có thể trả giá trị trước và sau.
- INSERT có giá trị NEW; không có OLD row.
- DELETE có giá trị OLD; không có NEW row.
- MERGE có thể trả giá trị theo nhánh và semantics được hỗ trợ.

Ví dụ tổng quát phải được viết theo đúng DML statement và release. Không dùng cú pháp 26ai OLD/NEW trong source SQL cần compile trên 19c.

### 11.4. RETURNING và nhiều row

Nếu statement tác động nhiều row, cần xem xét BULK COLLECT INTO hoặc cơ chế tương ứng. Không giả định biến scalar luôn nhận đủ kết quả của nhiều row. Kiểm tra số row affected, collection cardinality và hành vi khi không có row.

## 12. SQL Macros: 19c table macro và 21c scalar macro

### 12.1. 19c RU 19.7

SQL table macro được hỗ trợ từ 19c RU 19.7. Table macro là PL/SQL function được dùng như một biểu thức tạo query trong FROM. Nó giúp tái sử dụng SQL logic mà không cần lặp lại query text.

Ví dụ khái niệm:

~~~sql
CREATE OR REPLACE FUNCTION employees_by_department(
    p_department_id NUMBER
) RETURN VARCHAR2 SQL_MACRO(TABLE)
IS
BEGIN
    RETURN q'[
        SELECT employee_id, employee_name, department_id
        FROM employees
        WHERE department_id = p_department_id
    ]';
END;
/
~~~

Sử dụng:

~~~sql
SELECT *
FROM employees_by_department(10);
~~~

Cú pháp chính xác của macro phụ thuộc phiên bản và loại macro. Ví dụ này minh họa mô hình table macro; kiểm tra SQL_MACRO clause và các restriction của 19c RU.

### 12.2. 21c và scalar macro

21c bổ sung SQL scalar macro, dùng để tái sử dụng expression trong SELECT list, WHERE, GROUP BY hoặc HAVING. Nó giúp đóng gói logic biểu thức mà vẫn để SQL optimizer nhìn thấy phần SQL được mở rộng.

Ví dụ khái niệm:

~~~sql
CREATE OR REPLACE FUNCTION normalized_email(
    p_email VARCHAR2
) RETURN VARCHAR2 SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[LOWER(TRIM(p_email))]';
END;
/
~~~

Sử dụng:

~~~sql
SELECT employee_id
FROM employees
WHERE normalized_email(email) = 'user@example.com';
~~~

Kiểm tra cú pháp và khả năng macro theo release cụ thể. Không coi macro là procedure được gọi row-by-row giống một function thông thường; SQL macro trả về SQL text để database mở rộng khi parse.

### 12.3. Macro và function PL/SQL truyền thống

| Tiêu chí | Function PL/SQL truyền thống | SQL macro |
| --- | --- | --- |
| Kết quả | Giá trị runtime | SQL expression/query được mở rộng |
| SQL engine gọi PL/SQL runtime | Có thể có context switch | Macro mở rộng thành SQL |
| Tái sử dụng | Có | Có |
| Tối ưu SQL | Phụ thuộc khả năng optimizer và function | Optimizer thấy SQL được mở rộng |
| Khả năng tương thích | Rộng hơn | Phụ thuộc RU/release và macro type |

SQL macro không phải giải pháp thay thế mọi PL/SQL function. Dùng khi logic có thể biểu diễn thành SQL và cần tái sử dụng query expression/table logic.

## 13. SQL Transpiler trong 26ai

SQL Transpiler tự động chuyển đổi PL/SQL function được gọi bên trong SQL thành SQL expression khi có thể. Mục tiêu là giảm chi phí chuyển đổi giữa SQL runtime và PL/SQL runtime.

Ví dụ ý tưởng:

~~~sql
CREATE OR REPLACE FUNCTION tax_amount(
    p_net NUMBER
) RETURN NUMBER
IS
BEGIN
    RETURN p_net * 0.10;
END;
/
~~~

Query:

~~~sql
SELECT order_id, tax_amount(net_amount)
FROM orders;
~~~

Trong 26ai, SQL Transpiler có thể chuyển đổi function đơn giản thành SQL expression khi function đáp ứng điều kiện transpile. Không phải mọi function đều transpile được; function có side effect, trạng thái package, thao tác không thuần SQL hoặc construct không hỗ trợ có thể không đủ điều kiện.

Không giả định chỉ vì database là 26ai mà mọi function PL/SQL trong SQL sẽ tự động có performance như biểu thức inline. Kiểm tra execution plan, trace và SQL Tuning Guide. Nếu performance quan trọng, đo trước/sau với dữ liệu và bind thực tế.

## 14. PL/SQL CASE mở rộng trong 26ai

PL/SQL CASE simple statement được mở rộng với:
- Choice list: nhiều lựa chọn trong một WHEN.
- Dangling predicate: so sánh dựa trên selector với phần predicate được rút gọn.

Ví dụ choice list:

~~~sql
DECLARE
    l_status VARCHAR2(20) := 'PENDING';
    l_message VARCHAR2(100);
BEGIN
    CASE l_status
        WHEN 'NEW', 'PENDING' THEN
            l_message := 'Waiting';
        WHEN 'DONE', 'CLOSED' THEN
            l_message := 'Completed';
        ELSE
            l_message := 'Unknown';
    END CASE;

    DBMS_OUTPUT.PUT_LINE(l_message);
END;
/
~~~

Ví dụ dangling predicate theo cú pháp được hỗ trợ:

~~~sql
DECLARE
    l_score NUMBER := 82;
    l_grade VARCHAR2(2);
BEGIN
    CASE l_score
        WHEN >= 90 THEN l_grade := 'A';
        WHEN >= 80 THEN l_grade := 'B';
        WHEN >= 70 THEN l_grade := 'C';
        ELSE l_grade := 'F';
    END CASE;
END;
/
~~~

Cú pháp minh họa cần được xác nhận trên đúng 26ai RU; tài liệu ghi rõ một số dangling predicate như IS JSON và IS OF chưa được hỗ trợ. Với code phải chạy 19c, dùng searched CASE truyền thống để bảo đảm tương thích.

## 15. Aggregation FILTER và INTERVAL

### 15.1. Conditional aggregate trong 19c

Trước FILTER clause, thường dùng CASE bên trong aggregate:

~~~sql
SELECT
    department_id,
    COUNT(CASE WHEN status = 'ACTIVE' THEN 1 END) AS active_count,
    SUM(CASE WHEN status = 'ACTIVE' THEN salary ELSE 0 END) AS active_salary
FROM employees
GROUP BY department_id;
~~~

### 15.2. FILTER trong 26ai

26ai hỗ trợ FILTER clause trên aggregate function:

~~~sql
SELECT
    department_id,
    COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active_count,
    SUM(salary) FILTER (WHERE status = 'ACTIVE') AS active_salary,
    SUM(salary) FILTER (WHERE status = 'INACTIVE') AS inactive_salary
FROM employees
GROUP BY department_id;
~~~

FILTER chỉ tác động đến aggregate đứng trước nó. Nó không thay thế WHERE toàn query. Có thể dùng nhiều aggregate với các filter khác nhau trong cùng một SELECT.

### 15.3. SUM/AVG với INTERVAL

Tài liệu SQL hiện hành ghi nhận hỗ trợ aggregate SUM và AVG với INTERVAL từ release 23. Điều này giúp tính tổng/thời lượng trung bình mà không cần chuyển thành số giây hoặc số ngày thủ công.

~~~sql
SELECT
    project_id,
    SUM(duration_interval) AS total_duration,
    AVG(duration_interval) AS average_duration
FROM task_durations
GROUP BY project_id;
~~~

Kiểu INTERVAL kết quả giữ đơn vị phù hợp với input. Kiểm tra quy tắc precision, conversion và format khi hiển thị.

## 16. GROUP BY ALL và mở rộng GROUP BY trong 26ai

26ai có GROUP BY ALL để tự nhóm theo các biểu thức không aggregate trong select list.

~~~sql
SELECT
    department_id,
    job_id,
    COUNT(*) AS employee_count,
    AVG(salary) AS average_salary
FROM employees
GROUP BY ALL;
~~~

Cú pháp này giảm việc phải lặp các cột grouping trong GROUP BY. Nó thuận tiện cho exploratory query, nhưng cần xem xét khi query thay đổi select list: thêm một cột non-aggregate có thể làm thay đổi grouping semantics.

26ai cũng mở rộng hỗ trợ alias/position trong GROUP BY, ROLLUP, CUBE, GROUPING SETS và HAVING theo tài liệu. Nếu query phải chạy cả 19c, nên dùng biểu thức/cột grouping tường minh hoặc tạo view trung gian.

## 17. SQL Domains và Data Use Case Domains

### 17.1. SQL Domains trong 23ai

Domain là object reusable mô tả kiểu và constraint cho nhóm giá trị. Ví dụ email, mã quốc gia, số tài khoản hoặc ngày sinh. Một domain có thể được dùng trên nhiều column để thống nhất định nghĩa.

~~~sql
CREATE DOMAIN country_code AS VARCHAR2(2)
    CONSTRAINT country_code_ck
    CHECK (LENGTH(VALUE) = 2);

CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    country country_code
);
~~~

Domain không thay thế mọi constraint table-level, foreign key hoặc validation nghiệp vụ phức tạp. Nó giúp tái sử dụng quy tắc cho giá trị cùng bản chất.

### 17.2. Data Use Case Domains trong 26ai

26ai bổ sung Data Use Case Domain metadata cho các trường hợp sử dụng như email hoặc credit card number. Domain có thể đóng gói thuộc tính/constraint tùy mục đích và gắn với column.

Khi dùng domain trong migration:
- Kiểm tra domain object có được export/import ở workflow cụ thể hay không.
- Kiểm tra target release có hỗ trợ domain.
- Xác minh constraint được giữ nguyên.
- Kiểm tra metadata của driver/tool.
- Không giả định domain object được chuyển thành CHECK constraint đơn giản.

## 18. JSON-Relational Duality và SQL Property Graph

### 18.1. JSON-Relational Duality

23ai giới thiệu JSON-Relational Duality Views. Ứng dụng có thể đọc và cập nhật dữ liệu relational qua JSON document view. Dữ liệu vẫn nằm trong các table quan hệ, nhưng có giao diện document cho application.

Ví dụ sử dụng:
- REST API trả một JSON order chứa header và line items.
- Ứng dụng document-centric cập nhật một phần JSON.
- Hệ thống SQL/BI vẫn truy vấn các bảng quan hệ.
- Nhiều ứng dụng chia sẻ một model dữ liệu nguồn.

26ai tiếp tục mở rộng duality view, ví dụ validation directive, field ẩn/generated, giới hạn array, key tùy chỉnh và khả năng tích hợp/replication. Những tính năng này cần kiểm tra đúng RU và tài liệu JSON Developer's Guide.

### 18.2. SQL Property Graph Queries

Các release mới hỗ trợ SQL/PGQ để truy vấn graph trực tiếp trên dữ liệu quan hệ. Điều này cho phép biểu diễn vertex/edge và truy vấn quan hệ nhiều bước mà không cần chuyển toàn bộ dữ liệu sang graph store riêng.

Ứng dụng có thể dùng graph query cho:
- Phát hiện đường đi giữa các entity.
- Quan hệ khách hàng/tài khoản/giao dịch.
- Dependency và network topology.
- Phân tích chuỗi liên kết.

Không nhầm SQL/PGQ với việc tạo một table graph riêng cho mỗi query. Kiểm tra graph view, syntax, quyền và hỗ trợ theo release.

## 19. PL/SQL packages và API mở rộng

Phạm vi PL/SQL không chỉ là cú pháp block. Oracle tiếp tục bổ sung package và API để developer quản lý JSON, vector, metadata, performance và application integration.

Ví dụ trong 26ai:
- DBMS_VECTOR hỗ trợ các thao tác AI Vector Search như chunking, embedding và vector index.
- DBMS_DEVELOPER cung cấp API lấy metadata object; package này đã được bổ sung trong 19c RU 19.28.
- DBMS_SPM có API quản lý SQL plan management.
- Các package In-Memory và vector được mở rộng theo release.

Khi gọi package mới:
1. Kiểm tra package có tồn tại trên target.
2. Kiểm tra EXECUTE privilege.
3. Kiểm tra package status và dependency.
4. Xác nhận license/option nếu package gắn với tính năng có điều kiện.
5. Kiểm tra input/output type có được client hỗ trợ.
6. Test trong PDB đúng nơi triển khai.

Không dựa vào tên package trong tài liệu 26ai để giả định nó tồn tại trong 19c.

## 20. Tính năng mới không chỉ là cú pháp SQL

Một số khả năng 26ai ảnh hưởng cách ứng dụng tương tác với SQL/PLSQL nhưng không phải chỉ là một câu lệnh mới:
- JDBC có hỗ trợ native BOOLEAN data type và metadata.
- Driver có property điều khiển cách gửi boolean để tương thích ứng dụng cũ.
- Client/driver có thể cần nâng cấp để bind/fetch kiểu mới.
- SQL Firewall kiểm soát câu lệnh SQL được phép thực thi.
- API driver có thể mở rộng cho annotations, pipelining hoặc application security context.

Do đó, khi nâng database, phải nâng cấp và kiểm thử cả tầng client. Server chấp nhận một kiểu dữ liệu không có nghĩa mọi driver, ORM, ETL hoặc GUI tool đều có thể đọc/ghi nó.

## 21. Những khác biệt cần lưu ý khi port SQL từ 19c lên bản mới

| Hạng mục | Rủi ro khi port | Cách xử lý |
| --- | --- | --- |
| BOOLEAN column | 19c cũ không parse/không có SQL BOOLEAN | Dùng representation chung hoặc migration schema |
| JSON native | 19c không có kiểu JSON SQL của 21c | Dùng CLOB/BLOB + IS JSON hoặc giữ adapter |
| VECTOR | 19c không có native VECTOR | Giữ embedding ở external/alternate representation hoặc tách code path |
| IF NOT EXISTS | 19c RU trước 19.28 lỗi cú pháp | Kiểm tra RU; dùng dynamic DDL hoặc PL/SQL dictionary check |
| Annotations | 19c RU cũ không hỗ trợ | Chỉ dùng từ RU được hỗ trợ; giữ metadata ngoài nếu cần |
| SQL Domains | Target 19c không có domain | Materialize constraint ở table/column cho target cũ |
| SELECT bỏ FROM | 19c cần DUAL | Giữ FROM DUAL trong SQL chung |
| Multivalue INSERT | 19c không parse tuple list mới | Dùng INSERT ALL, array binding hoặc nhiều INSERT |
| VALUES constructor | 19c không hỗ trợ dạng mới | Dùng SELECT FROM DUAL/CTE/temporary table |
| GROUP BY alias | 19c cần expression/cột lặp lại | Dùng inline view hoặc lặp expression |
| JOIN UPDATE/DELETE | 19c không parse cú pháp mới | Dùng subquery hoặc MERGE |
| UPDATE/MERGE RETURNING mới | Khác biệt syntax/semantics theo release | Dùng PL/SQL wrapper hoặc code path riêng |
| SQL Transpiler | 19c không có tính năng tự transpile 26ai | Tối ưu function và SQL theo cách tương thích |
| FILTER aggregate | 19c không có cú pháp mới | Dùng CASE bên trong aggregate |
| GROUP BY ALL | 19c không có cú pháp mới | Liệt kê grouping columns tường minh |
| VECTOR trong PL/SQL | Cần 26ai và RU phù hợp | Dùng package/SQL path riêng cho bản mới |

## 22. Ví dụ cùng một nghiệp vụ trên 19c và 23ai+

Giả sử cần đếm số đơn hàng theo trạng thái, đồng thời tính tổng giá trị đơn hàng đã thanh toán.

### 22.1. SQL dùng được trên 19c

~~~sql
SELECT
    customer_id,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    SUM(CASE WHEN status = 'PAID' THEN total_amount ELSE 0 END)
        AS paid_amount
FROM orders
GROUP BY customer_id;
~~~

### 22.2. SQL dùng FILTER ở bản hỗ trợ

~~~sql
SELECT
    customer_id,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    SUM(total_amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM orders
GROUP BY customer_id;
~~~

Hai câu lệnh biểu đạt cùng ý định nhưng câu thứ hai cần release hỗ trợ FILTER. Nếu ứng dụng phải chạy trên 19c, giữ câu lệnh đầu hoặc tạo view/package tương thích.

## 23. Viết SQL đa phiên bản an toàn

### 23.1. Ưu tiên SQL giao nhau

Nếu cùng một codebase phải chạy nhiều release:
- Dùng cú pháp chung nhỏ nhất.
- Đóng gói khác biệt trong repository/view/package.
- Tránh rải kiểm tra version trong mọi query.
- Tách script migration theo release.
- Không gửi cú pháp mới tới parser của server cũ.

### 23.2. Dynamic SQL cho cú pháp có điều kiện

Một PL/SQL block có thể chứa SQL mới dưới dạng chuỗi và chỉ execute khi capability đã được xác nhận. Server cũ có thể compile block vì cú pháp mới không nằm trong static SQL; nhưng chuỗi chỉ được parse khi chạy.

Ví dụ khái niệm:

~~~sql
DECLARE
    l_supports_new_ddl BOOLEAN := FALSE;
BEGIN
    -- Capability phải được xác định từ release/RU đã kiểm chứng.
    IF l_supports_new_ddl THEN
        EXECUTE IMMEDIATE
            'CREATE TABLE IF NOT EXISTS app_log (id NUMBER)';
    ELSE
        BEGIN
            EXECUTE IMMEDIATE
                'CREATE TABLE app_log (id NUMBER)';
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE != -955 THEN
                    RAISE;
                END IF;
        END;
    END IF;
END;
/
~~~

Ví dụ trên chỉ minh họa cách cô lập cú pháp; production phải có capability check thật và chỉ bỏ qua đúng lỗi object already exists. Không dùng WHEN OTHERS để nuốt mọi lỗi DDL.

### 23.3. Không kiểm tra version bằng chuỗi tùy tiện

Một số tính năng được backport qua RU nên chỉ so VERSION là không đủ. Cần xác định:
- Release.
- RU/patch.
- COMPATIBLE.
- Feature option.
- Client/driver capability.

Nếu cần runtime capability detection, tạo một module kiểm tra tập trung, có log và test cho từng môi trường.

### 23.4. Tách DDL migration theo target

Schema migration có thể có:
- Script baseline 19c.
- Script mở rộng cho 19c RU mới.
- Script nâng cấp 21c.
- Script dành cho 23ai/26ai.
- Script backfill và validation.
- Script rollback hoặc forward-fix.

Không đặt mọi cú pháp vào một file SQL duy nhất rồi hy vọng database cũ bỏ qua phần không hiểu. SQL parser phải phân tích câu lệnh trước khi điều kiện runtime có thể quyết định bỏ qua nó.

## 24. Kiểm thử khi nâng cấp 19c lên 23ai/26ai

### 24.1. Kiểm thử cú pháp và object

- Compile lại package, procedure, function và trigger.
- Kiểm tra invalid object và dependency.
- Chạy migration DDL theo đúng thứ tự.
- Xác minh domain, annotation, identity và JSON metadata.
- Kiểm tra synonym, view và materialized view.

### 24.2. Kiểm thử dữ liệu

- Đối chiếu row count.
- Kiểm tra NULL và default.
- Kiểm tra JSON validity và JSON type conversion.
- Kiểm tra BOOLEAN mapping.
- Kiểm tra VECTOR dimension/format và null handling.
- Kiểm tra constraint và index.

### 24.3. Kiểm thử execution plan

SQL mới có thể làm query ngắn hơn nhưng không mặc định nhanh hơn. So sánh:
- Execution plan.
- Estimated/actual rows.
- Buffer gets và physical reads.
- CPU và elapsed time.
- Wait events.
- Bind peeking/adaptive behavior.
- SQL plan baseline nếu đang dùng SPM.

SQL Transpiler, FILTER, GROUP BY mới và JOIN DML đều cần benchmark bằng workload thật.

### 24.4. Kiểm thử client và framework

- JDBC/ODP.NET/OCI version.
- ORM dialect và schema generator.
- BI/reporting tool.
- ETL và Data Pump.
- SQL Developer/SQLcl/SQL*Plus.
- Monitoring/observability.
- Application server connection pool.

Đặc biệt với BOOLEAN, JSON và VECTOR, test cả metadata discovery, bind, fetch, serialization và null handling.

## 25. Ma trận quyết định áp dụng tính năng mới

| Câu hỏi | Nếu có | Hướng xử lý |
| --- | --- | --- |
| Ứng dụng chỉ chạy 19c RU cũ? | Có | Không dùng cú pháp mới; chọn fallback |
| Ứng dụng chạy 19c RU 19.28+? | Có | Xác nhận IF EXISTS/annotations theo object support |
| Có cần chia sẻ code trên 19c và 23ai? | Có | Dùng SQL giao nhau hoặc adapter |
| Có cần boolean column native? | Có | Chỉ dùng khi mọi target/driver hỗ trợ |
| Có cần document API trên relational data? | Có | Đánh giá JSON-Relational Duality |
| Có workload embedding/vector? | Có | Đánh giá VECTOR, index, model và RU |
| Có function PL/SQL nặng được gọi trong SQL? | Có | Xem SQL Transpiler hoặc SQL macro, đo hiệu năng |
| Có query aggregate nhiều điều kiện? | Có | Đánh giá FILTER trên release hỗ trợ |
| Có script DDL idempotent? | Có | Xác nhận RU 19.28 hoặc release mới |
| Có migration đa nền tảng? | Có | Test dump, driver, data type và client compatibility |

## 26. Lab so sánh cú pháp

Thực hiện trên hai môi trường riêng hoặc hai database container có release khác nhau. Không chạy DDL thử nghiệm trên schema production.

### 26.1. Lab BOOLEAN

Trên 19c:

~~~sql
CREATE TABLE lab_flag_19c (
    id NUMBER PRIMARY KEY,
    enabled NUMBER(1) NOT NULL CHECK (enabled IN (0, 1))
);
~~~

Trên 23ai/26ai:

~~~sql
CREATE TABLE lab_flag_new (
    id NUMBER PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE NOT NULL
);

INSERT INTO lab_flag_new VALUES (1, TRUE);
SELECT * FROM lab_flag_new WHERE enabled = TRUE;
~~~

So sánh schema metadata, driver fetch và cách ứng dụng biểu diễn giá trị.

### 26.2. Lab DDL IF EXISTS

Trên 19c RU trước 19.28, thử lệnh mới trong schema lab để quan sát lỗi parse. Trên RU 19.28+ hoặc 23ai/26ai, kiểm tra object type được hỗ trợ:

~~~sql
CREATE TABLE IF NOT EXISTS lab_idempotent (
    id NUMBER PRIMARY KEY
);

DROP TABLE IF EXISTS lab_idempotent;
~~~

Không kết luận từ một câu lệnh CREATE TABLE rằng tất cả DDL đều hỗ trợ IF EXISTS.

### 26.3. Lab VALUES và multivalue INSERT

~~~sql
SELECT *
FROM (VALUES
    (1, 'A'),
    (2, 'B'),
    (3, 'C')
) sample_rows(id, label);
~~~

~~~sql
INSERT INTO lab_items (item_id, item_name)
VALUES
    (1, 'A'),
    (2, 'B'),
    (3, 'C');
~~~

Chạy trên 23ai/26ai. Trên 19c dùng INSERT ALL hoặc nhiều INSERT tương ứng.

### 26.4. Lab GROUP BY alias

~~~sql
SELECT
    TO_CHAR(created_at, 'YYYY-MM') AS month_key,
    COUNT(*) AS item_count
FROM lab_items
GROUP BY month_key;
~~~

So sánh với cách lặp lại TO_CHAR expression trên 19c.

### 26.5. Lab RETURNING

Tạo table lab và thử UPDATE RETURNING OLD/NEW trên 23ai/26ai theo syntax được hỗ trợ. Trên 19c, thử RETURNING truyền thống và so sánh dữ liệu trả về.

### 26.6. Lab SQL macro

Tạo table macro trên 19c RU 19.7+ hoặc release mới. Tạo scalar macro trên release hỗ trợ. Xem execution plan để hiểu macro được mở rộng thành SQL như thế nào.

### 26.7. Lab SQL Transpiler

Trên 26ai:
- Tạo function PL/SQL đơn giản, không side effect.
- Gọi function trong SQL.
- Kiểm tra điều kiện transpile theo tài liệu.
- Xem execution plan và đo CPU/elapsed.
- Thay đổi function để thêm construct không hỗ trợ và so sánh.

Không dùng kết quả của một lab nhỏ để khẳng định mọi function sẽ transpile.

## 27. Lỗi thường gặp khi dùng tính năng mới

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| ORA-00902 invalid datatype với BOOLEAN | Server chưa hỗ trợ SQL BOOLEAN hoặc client metadata sai | Xác nhận 23ai+ và driver |
| ORA-00933/ORA-00905 khi dùng cú pháp mới | Release/RU chưa hỗ trợ câu lệnh | Kiểm tra SQL Reference và RU |
| IF NOT EXISTS không hoạt động trên 19c | RU thấp hơn 19.28 hoặc object type không nằm trong danh sách | Xác nhận patch và supported statement |
| Annotations không được nhận diện | RU/release chưa hỗ trợ hoặc syntax sai | Kiểm tra 19.28+ và CREATE/ALTER grammar |
| JSON type không dùng được trên 21c | COMPATIBLE hoặc điều kiện release chưa đúng | Kiểm tra parameter và migration guide |
| VECTOR không bind từ application | Driver/client chưa hỗ trợ kiểu mới | Nâng driver và kiểm tra API mapping |
| PL/SQL BOOLEAN gọi từ SQL lỗi | Release/argument expression chưa hỗ trợ | Kiểm tra khả năng BOOLEAN interop của 26ai |
| SQL macro không compile | RU/release hoặc loại macro không hỗ trợ | Phân biệt table macro và scalar macro |
| SQL Transpiler không áp dụng | Function chứa construct không đủ điều kiện | Kiểm tra tài liệu và execution plan |
| UPDATE JOIN trả nhiều row không mong muốn | Source join không duy nhất | Kiểm tra cardinality và khóa nguồn |
| GROUP BY alias ambiguous | Alias trùng tên column hoặc scope khác | Đổi alias và qualify column |
| FILTER aggregate khác kết quả CASE | Điều kiện NULL/ELSE khác nhau | So sánh semantics và dữ liệu NULL |
| Import schema mất domain/annotation | Target cũ hoặc export/import path không hỗ trợ | Kiểm tra Data Pump compatibility và metadata |
| Tool hiển thị sai kiểu | Client cũ chưa hiểu type metadata | Nâng SQL Developer/driver/ORM |

## 28. Nguyên tắc thiết kế cho hệ thống nhiều release

1. Chọn baseline SQL chung nếu cùng source phải chạy trên nhiều phiên bản.
2. Ghi rõ database version, RU và COMPATIBLE trong deployment manifest.
3. Dùng adapter cho khác biệt BOOLEAN, JSON và VECTOR.
4. Tách migration script theo release và capability.
5. Không gửi cú pháp mới trong static SQL đến database cũ.
6. Kiểm tra client/driver/ORM song song với server.
7. Dùng dynamic SQL có kiểm soát khi cần hỗ trợ nhiều parser.
8. Test rollback và data conversion trước khi đổi kiểu cột.
9. Benchmark SQL mới thay vì giả định cú pháp ngắn hơn sẽ nhanh hơn.
10. Giữ fallback path cho các hệ thống còn 19c RU cũ.
11. Xác minh license, deployment restriction và patch requirement.
12. Đọc tài liệu RU trước khi nâng patch production.

## Tổng kết

Phạm vi SQL/PLSQL của Oracle đã mở rộng đáng kể từ 19c qua 21c, 23ai và 26ai. 19c vẫn có nhiều khả năng hiện đại, đặc biệt khi đã cài RU mới: table SQL macro có từ 19.7, IF [NOT] EXISTS và annotations có từ 19.28. 21c bổ sung native JSON SQL data type và scalar SQL macros. 23ai mở rộng SQL với BOOLEAN, Domains, multivalue INSERT, VALUES constructor, optional FROM, GROUP BY alias, UPDATE/MERGE RETURNING, JOIN DML, VECTOR và JSON-Relational Duality. 26ai tiếp tục mở rộng PL/SQL BOOLEAN/VECTOR, JSON aggregate mapping, SQL Transpiler, CASE controls, aggregation FILTER, GROUP BY ALL và nhiều khả năng SQL khác.

Không nên xem khác biệt phiên bản như một danh sách cú pháp mới đơn thuần. Điều quan trọng là xác định tính năng nằm ở SQL hay PL/SQL, release/RU nào hỗ trợ, COMPATIBLE và client driver có đáp ứng hay không, và cách ứng dụng fallback khi phải chạy nhiều release. Một migration tốt ghi rõ capability, kiểm thử schema/data/client, đo hiệu năng và triển khai từng bước để tránh đưa cú pháp mới vào hệ thống chưa hỗ trợ.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Language Reference — Changes in This Release](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Changes-in-This-Release-for-Oracle-Database-SQL-Language-Reference.html) — SQL macros, RU 19.28 IF [NOT] EXISTS và schema annotations.
- [Oracle Database 19c PL/SQL Language Reference — Changes in This Release](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/release-changes.html) — SQL table macros từ 19c RU 19.7 và IF [NOT] EXISTS từ RU 19.28.
- [Oracle Database 19c Release Update 19.28](https://docs.oracle.com/en/database/oracle/oracle-database/19/newft/ru-19-28.html) — DBMS_DEVELOPER, annotations và các thay đổi RU.
- [Oracle Database 21c SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/Data-Types.html) — native JSON data type.
- [Oracle Database 21c SQL Language Reference — Changes in This Release](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/Changes-in-This-Release-for-Oracle-Database-SQL-Language-Reference.html) — SQL macros scalar/table và các thay đổi SQL 21c.
- [Explore SQL Features in Oracle Database 23ai](https://docs.oracle.com/en/learn/db23ai-sql-features/index.html) — BOOLEAN, IF EXISTS, multivalue INSERT, VALUES, GROUP BY alias, RETURNING, JOIN DML, annotations và domains.
- [Oracle AI Database 26ai New Features](https://docs.oracle.com/en/database/oracle/oracle-database/26/nfcoa/all-nfg.html) — tổng hợp tính năng SQL/PLSQL, JSON, vector và developer productivity của 26ai.
- [Oracle AI Database 26ai PL/SQL Language Reference — Changes in This Release](https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/release-changes.html) — SQL BOOLEAN, VECTOR, IF [NOT] EXISTS, CASE mở rộng, JSON aggregate mapping và SQL Transpiler.
- [Oracle AI Database 26ai SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/) — cú pháp SQL hiện hành.
- [Oracle AI Database 26ai PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/) — cú pháp PL/SQL hiện hành.

Khi áp dụng, hãy đọc cả SQL Language Reference, PL/SQL Language Reference, New Features và RU notes của đúng release. Đặc biệt xác nhận RU 19c, COMPATIBLE, driver/client, feature option và restriction trước khi đưa cú pháp mới vào source dùng chung.
