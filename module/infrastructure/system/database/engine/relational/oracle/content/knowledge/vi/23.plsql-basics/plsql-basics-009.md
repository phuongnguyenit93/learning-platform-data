# RECORD và mô hình dữ liệu nhiều trường trong PL/SQL

Một nhân viên không chỉ có một giá trị. Một bản ghi nhân viên thường gồm mã nhân viên, họ tên, phòng ban, email, trạng thái và ngày tuyển dụng. Nếu một thủ tục PL/SQL phải xử lý các giá trị này như một đơn vị, việc khai báo hàng loạt biến rời rạc dễ làm code dài, khó truyền tham số và dễ nhầm thứ tự. PL/SQL cung cấp kiểu dữ liệu tổng hợp **RECORD** để gom nhiều trường có tên vào một cấu trúc có ý nghĩa.

Một RECORD có thể đại diện cho một hàng dữ liệu, một đối tượng nghiệp vụ ở mức ứng dụng hoặc một kết quả truy vấn gồm nhiều cột. Mỗi trường trong record có tên và datatype riêng. Ta có thể khai báo record tường minh, neo kiểu theo cột bằng %TYPE, lấy cấu trúc hàng bằng %ROWTYPE, dùng kiểu record của cursor, truyền record qua package API hoặc lưu nhiều record trong collection.

Bài học thuộc nhóm **PL/SQL cơ bản** của Database Engine Relational Oracle. Nội dung tập trung vào RECORD và cách mô hình hóa dữ liệu nhiều trường trong bộ nhớ PL/SQL. Bài cũng phân biệt record với collection, object type và hàng trong bảng SQL; hướng dẫn SELECT INTO, FETCH, DML RETURNING, package interfaces và BULK COLLECT.

Sau bài này, bạn có thể:

- Giải thích RECORD là kiểu dữ liệu tổng hợp gồm nhiều trường có tên.
- Khai báo TYPE ... IS RECORD và biến record.
- Neo datatype trường bằng %TYPE.
- Dùng table%ROWTYPE và cursor%ROWTYPE để bám sát cấu trúc kết quả.
- Đọc và ghi từng trường bằng dấu chấm.
- Khởi tạo, gán và truyền record giữa các thủ tục.
- Dùng SELECT INTO, FETCH và RETURNING INTO với record hoặc các trường record.
- Công bố record type trong package specification để làm API PL/SQL.
- Tạo collection chứa nhiều record và xử lý bằng BULK COLLECT.
- Hiểu giới hạn của PL/SQL RECORD khi làm việc với SQL engine.
- Chọn giữa RECORD, %ROWTYPE, collection và SQL object type theo yêu cầu.

> **Phạm vi ví dụ:** Cú pháp minh họa theo Oracle Database 19c. Các ví dụ dùng bảng có hậu tố _LAB trong schema thực hành. Một số cú pháp qualified expression để khởi tạo record có từ Oracle Database 18c; bài sẽ chỉ rõ khi nào cần phiên bản hỗ trợ và luôn có cách gán từng trường thay thế.

## 1. RECORD là gì?

RECORD là một kiểu dữ liệu PL/SQL gồm nhiều trường (fields). Mỗi trường có tên, datatype và có thể có giá trị mặc định. Các trường có thể có datatype khác nhau.

Ví dụ một nhân viên có:

| Trường | Datatype minh họa |
| --- | --- |
| employee_id | NUMBER |
| full_name | VARCHAR2 |
| department_id | NUMBER |
| work_email | VARCHAR2 |
| hire_date | DATE |
| active_flag | BOOLEAN |

Ta có thể mô hình hóa một nhân viên thành một record thay vì khai báo sáu biến riêng.

~~~text
EMPLOYEE_RECORD
+-----------------------------+
| employee_id   : NUMBER      |
| full_name     : VARCHAR2    |
| department_id : NUMBER      |
| work_email    : VARCHAR2    |
| hire_date     : DATE        |
| active_flag   : BOOLEAN     |
+-----------------------------+
~~~

### 1.1. RECORD đại diện cho một đơn vị dữ liệu nhiều trường

Một record thường đại diện cho một trong các khái niệm:

- Một hàng nhân viên.
- Một khách hàng cùng thông tin liên hệ.
- Một header đơn hàng.
- Một dòng kết quả của cursor.
- Một thông điệp nghiệp vụ đã được giải mã thành nhiều thuộc tính.
- Một cấu trúc input/output giữa các thủ tục trong cùng ứng dụng PL/SQL.

RECORD chỉ là dữ liệu trong bộ nhớ PL/SQL. Bản thân nó không tạo bảng, không lưu dữ liệu bền vững và không tự đảm bảo transaction hay constraint. Khi cần lưu, code phải INSERT/UPDATE vào bảng hoặc gọi cơ chế persistence phù hợp.

### 1.2. Khác với các biến rời rạc

Không dùng record:

~~~sql
DECLARE
    v_employee_id   NUMBER;
    v_full_name     VARCHAR2(80);
    v_department_id NUMBER;
    v_work_email    VARCHAR2(120);
BEGIN
    SELECT employee_id, full_name, department_id, work_email
    INTO v_employee_id, v_full_name, v_department_id, v_work_email
    FROM employee_data_lab
    WHERE employee_id = 101;
END;
/
~~~

Dùng record:

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id   NUMBER,
        full_name     VARCHAR2(80),
        department_id NUMBER,
        work_email    VARCHAR2(120)
    );

    l_employee employee_rec;
BEGIN
    SELECT employee_id, full_name, department_id, work_email
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

Record gom các giá trị liên quan vào một biến có cấu trúc. Khi truyền dữ liệu sang procedure khác, ta có thể truyền một record thay vì nhiều tham số rời rạc, miễn là API đã được thiết kế với record type tương thích.

## 2. Khai báo RECORD tường minh

### 2.1. Cú pháp TYPE ... IS RECORD

Mẫu cơ bản:

~~~sql
TYPE record_type_name IS RECORD (
    field_name_1 datatype [ [NOT NULL] { := | DEFAULT } expression ],
    field_name_2 datatype [ [NOT NULL] { := | DEFAULT } expression ],
    ...
);
~~~

Sau khi khai báo kiểu, khai báo một hoặc nhiều biến thuộc kiểu đó:

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        street       VARCHAR2(120),
        district     VARCHAR2(60),
        city         VARCHAR2(60),
        postal_code  VARCHAR2(20)
    );

    l_address address_rec;
BEGIN
    l_address.street := '12 Nguyen Hue';
    l_address.district := 'District 1';
    l_address.city := 'Ho Chi Minh City';
    l_address.postal_code := '700000';

    DBMS_OUTPUT.PUT_LINE(
        l_address.street || ', ' ||
        l_address.district || ', ' ||
        l_address.city
    );
END;
/
~~~

TYPE định nghĩa cấu trúc, còn l_address là biến chứa một giá trị record cụ thể. Có thể khai báo nhiều biến cùng một record type:

~~~sql
DECLARE
    TYPE point_rec IS RECORD (
        x NUMBER,
        y NUMBER
    );

    l_origin point_rec;
    l_target point_rec;
BEGIN
    l_origin.x := 0;
    l_origin.y := 0;

    l_target.x := 10;
    l_target.y := 20;
END;
/
~~~

### 2.2. Truy cập trường bằng dấu chấm

Mỗi trường được truy cập theo cú pháp:

~~~sql
record_variable.field_name
~~~

Ví dụ:

~~~sql
l_employee.employee_id := 101;
l_employee.full_name := 'Nguyen An';
l_employee.department_id := 10;
~~~

Tên trường phải đúng với khai báo. Record không truy cập trường bằng chỉ số như array; nó dùng tên trường để thể hiện ý nghĩa dữ liệu.

### 2.3. Kiểu dữ liệu của từng trường

Trường record có thể dùng datatype PL/SQL phù hợp như NUMBER, VARCHAR2, DATE, TIMESTAMP, BOOLEAN, subtype, %TYPE hoặc một record/collection type khác trong phạm vi được hỗ trợ.

Ví dụ:

~~~sql
DECLARE
    TYPE contact_rec IS RECORD (
        contact_id NUMBER,
        display_name VARCHAR2(100),
        preferred_contact VARCHAR2(10),
        verified BOOLEAN,
        last_contact_at TIMESTAMP
    );

    l_contact contact_rec;
BEGIN
    l_contact.contact_id := 501;
    l_contact.display_name := 'Customer A';
    l_contact.preferred_contact := 'EMAIL';
    l_contact.verified := TRUE;
    l_contact.last_contact_at := SYSTIMESTAMP;
END;
/
~~~

BOOLEAN là datatype PL/SQL; không phải mọi datatype PL/SQL đều có thể dùng làm cột SQL. Đây là một khác biệt quan trọng giữa record PL/SQL và cấu trúc dữ liệu được khai báo ở SQL schema.

### 2.4. Giá trị mặc định cho trường

Có thể khai báo giá trị mặc định:

~~~sql
DECLARE
    TYPE order_rec IS RECORD (
        order_id NUMBER,
        status VARCHAR2(12) := 'NEW',
        priority NUMBER := 0,
        created_at TIMESTAMP := SYSTIMESTAMP
    );

    l_order order_rec;
BEGIN
    l_order.order_id := 9001;

    DBMS_OUTPUT.PUT_LINE(l_order.status);
END;
/
~~~

Khi biến record được tạo, các trường có default nhận giá trị tương ứng. Trường không có default thường có giá trị NULL ban đầu.

Nếu một trường được khai báo NOT NULL, phải cung cấp giá trị mặc định hợp lệ trong khai báo record. Ví dụ:

~~~sql
TYPE employee_key_rec IS RECORD (
    employee_id NUMBER NOT NULL := 0,
    full_name VARCHAR2(80)
);
~~~

Không nhầm NOT NULL của trường record với constraint NOT NULL của cột bảng. Nó là quy tắc ở datatype PL/SQL và chỉ bảo vệ việc gán trường trong phạm vi record đó.

## 3. Gán và khởi tạo RECORD

### 3.1. Gán từng trường

Đây là cách rõ ràng và hoạt động trên các phiên bản PL/SQL thông dụng:

~~~sql
DECLARE
    TYPE product_rec IS RECORD (
        product_id NUMBER,
        product_name VARCHAR2(80),
        unit_price NUMBER(12,2)
    );

    l_product product_rec;
BEGIN
    l_product.product_id := 1001;
    l_product.product_name := 'Keyboard';
    l_product.unit_price := 49.90;
END;
/
~~~

Gán từng trường hữu ích khi dữ liệu đến từ nhiều nguồn hoặc chỉ một số trường được thiết lập tại từng bước. Tuy nhiên, cần bảo đảm các trường bắt buộc được gán trước khi dùng.

### 3.2. Gán toàn bộ record

Có thể gán một record cho record khác khi hai biến có cùng kiểu record tương thích:

~~~sql
DECLARE
    TYPE point_rec IS RECORD (
        x NUMBER,
        y NUMBER
    );

    l_a point_rec;
    l_b point_rec;
BEGIN
    l_a.x := 10;
    l_a.y := 20;

    l_b := l_a;
END;
/
~~~

Phép gán toàn record sao chép các trường từ record nguồn sang record đích. Nếu record có trường chứa collection hoặc cấu trúc phức tạp, hãy hiểu semantics của kiểu thành phần và cách sao chép tương ứng.

Không giả định hai record type được khai báo độc lập sẽ luôn có thể gán cho nhau chỉ vì tên trường và datatype trông giống nhau. Thiết kế API nên dùng một type chung được khai báo ở package specification khi nhiều subprogram cần trao đổi cùng cấu trúc.

### 3.3. Qualified expressions trên Oracle 18c+

Oracle Database 18c trở lên hỗ trợ qualified expressions để tạo giá trị cho record type:

~~~sql
DECLARE
    TYPE point_rec IS RECORD (
        x NUMBER,
        y NUMBER
    );

    l_point point_rec;
BEGIN
    l_point := point_rec(10, 20);
END;
/
~~~

Có thể dùng named association để biểu đạt trường rõ hơn:

~~~sql
l_point := point_rec(y => 20, x => 10);
~~~

Qualified expression là cú pháp thuận tiện, nhưng nếu code cần chạy trên phiên bản cũ hơn, hãy gán từng trường hoặc dùng SELECT INTO.

### 3.4. Không có phép so sánh toàn record thông thường

Không nên viết:

~~~sql
IF l_old_record = l_new_record THEN
    ...
END IF;
~~~

PL/SQL không cung cấp phép so sánh equality tổng quát cho toàn bộ record như với scalar. Hãy so sánh các trường cần thiết:

~~~sql
IF l_old_record.employee_id = l_new_record.employee_id
   AND l_old_record.department_id = l_new_record.department_id
THEN
    ...
END IF;
~~~

Nếu cần so sánh nhiều trường, có thể viết hàm chuyên biệt hoặc so sánh theo business key và các thuộc tính có ý nghĩa. Cần xử lý NULL rõ ràng vì phép so sánh với NULL cho kết quả UNKNOWN.

### 3.5. Không kiểm tra NULL trên cả record như scalar

Không dùng:

~~~sql
IF l_employee IS NULL THEN
    ...
END IF;
~~~

Hãy dùng cờ trạng thái hoặc kiểm tra trường định danh:

~~~sql
IF l_employee.employee_id IS NULL THEN
    ...
END IF;
~~~

Nếu employee_id có thể NULL hợp lệ trong một trạng thái chưa hoàn chỉnh, dùng thêm BOOLEAN flag như l_loaded để phân biệt “chưa nạp record” với “record đã nạp nhưng trường này NULL”.

## 4. Neo datatype trường bằng %TYPE

Khi record đại diện cho dữ liệu bảng, hard-code độ dài và precision có thể khiến kiểu PL/SQL lệch khỏi schema. Attribute %TYPE cho phép trường dùng datatype của cột hoặc biến đã có.

### 4.1. Cú pháp column%TYPE

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE,
        work_email employee_data_lab.work_email%TYPE
    );

    l_employee employee_rec;
BEGIN
    ...
END;
/
~~~

Nếu datatype của cột thay đổi, record được biên dịch lại có thể bám theo kiểu mới mà không cần sửa từng khai báo độ dài/precision.

### 4.2. %TYPE không sao chép mọi constraint

%TYPE lấy datatype và một số thuộc tính kiểu liên quan từ cột/biến được tham chiếu, nhưng không biến trường record thành một cột bảng có đầy đủ constraint. Ví dụ, khai báo dựa trên cột NOT NULL không tự động có nghĩa trường record cũng được bảo vệ bằng constraint NOT NULL như cột nguồn.

Hãy kiểm tra dữ liệu bắt buộc trong logic PL/SQL hoặc khai báo NOT NULL/default ở record khi phù hợp.

### 4.3. Neo theo biến PL/SQL

%TYPE cũng có thể tham chiếu biến:

~~~sql
DECLARE
    v_default_amount NUMBER(12,2);

    TYPE payment_rec IS RECORD (
        payment_id NUMBER,
        amount v_default_amount%TYPE
    );

    l_payment payment_rec;
BEGIN
    ...
END;
/
~~~

Trong nhiều ứng dụng, neo theo cột bảng thường dễ hiểu hơn vì thể hiện record gắn với schema nào.

## 5. Dùng %ROWTYPE cho toàn bộ hàng

Nếu record cần có đúng cấu trúc của một hàng bảng hoặc view, %ROWTYPE giúp tránh khai báo lại mọi trường.

### 5.1. table%ROWTYPE

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
    DBMS_OUTPUT.PUT_LINE(l_employee.monthly_salary);
END;
/
~~~

EMPLOYEE_DATA_LAB%ROWTYPE tạo record có một trường tương ứng với mỗi cột của bảng. Tên trường tương ứng với tên cột, datatype bám theo cột.

### 5.2. view%ROWTYPE

Có thể neo theo view:

~~~sql
DECLARE
    l_directory_row v_employee_directory_lab%ROWTYPE;
BEGIN
    SELECT *
    INTO l_directory_row
    FROM v_employee_directory_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(l_directory_row.full_name);
END;
/
~~~

Record chỉ có các cột được view công bố. Điều này hữu ích khi procedure chỉ nên làm việc với một projection cụ thể, thay vì toàn bộ hàng bảng nền.

### 5.3. Ưu điểm và trade-off của %ROWTYPE

Ưu điểm:

- Khai báo ngắn.
- Bám theo cấu trúc bảng/view.
- Phù hợp khi xử lý một hàng gần như đầy đủ.
- Giảm nguy cơ datatype không đồng bộ.

Trade-off:

- Procedure phụ thuộc cấu trúc bảng/view.
- Nếu bảng có nhiều cột không cần thiết, record cũng có nhiều trường hơn.
- SELECT * làm code nhạy cảm với thay đổi schema.
- Không phải mọi trường đều phù hợp để công bố ra API.

Nếu chỉ cần 3 trong 30 cột, một explicit RECORD hoặc view projection thường thể hiện dependency rõ hơn.

### 5.4. %ROWTYPE không kế thừa constraint/default của bảng

%ROWTYPE cung cấp cấu trúc trường và datatype tương ứng, nhưng không sao chép đầy đủ NOT NULL, default, check hoặc foreign key constraint thành quy tắc tự động trên biến record.

Ví dụ, cột bảng NOT NULL có thể tương ứng với trường record mà code vẫn có thể chưa gán giá trị. Constraint sẽ được kiểm tra khi DML ghi vào bảng, không phải mỗi lần gán một trường PL/SQL.

### 5.5. SELECT * phù hợp khi dùng %ROWTYPE đúng đối tượng

~~~sql
SELECT *
INTO l_employee
FROM employee_data_lab
WHERE employee_id = 101;
~~~

Ở đây SELECT * khớp cấu trúc rowtype của cùng bảng. Nếu chỉ chọn một số cột, nên dùng record type có cấu trúc tương ứng hoặc INTO từng trường. Không chọn một tập cột tùy ý rồi INTO một %ROWTYPE có cấu trúc khác.

## 6. Cursor%ROWTYPE cho kết quả truy vấn

Kết quả SELECT không nhất thiết trùng với một bảng. Cursor%ROWTYPE cho record theo danh sách cột của cursor.

### 6.1. Khai báo explicit cursor

~~~sql
DECLARE
    CURSOR c_active_employee IS
        SELECT
            employee_id,
            full_name,
            department_id,
            work_email
        FROM employee_data_lab
        WHERE employment_status = 'ACTIVE';

    l_employee c_active_employee%ROWTYPE;
BEGIN
    OPEN c_active_employee;

    FETCH c_active_employee INTO l_employee;

    IF c_active_employee%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
    END IF;

    CLOSE c_active_employee;
END;
/
~~~

Cursor record chứa các cột/biểu thức được SELECT trong cursor, không phải toàn bộ cột bảng.

### 6.2. Cursor FOR LOOP tạo record ngầm

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, department_id
        FROM employee_data_lab
        WHERE employment_status = 'ACTIVE';
BEGIN
    FOR r_employee IN c_employee LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ': ' ||
            r_employee.full_name
        );
    END LOOP;
END;
/
~~~

Biến r_employee được khai báo ngầm bởi cursor FOR LOOP và có cấu trúc tương ứng với cursor select list. Oracle tự mở cursor, fetch từng dòng và đóng cursor khi vòng lặp kết thúc hoặc rời khỏi phạm vi.

### 6.3. Inline cursor FOR LOOP

~~~sql
BEGIN
    FOR r_order IN (
        SELECT order_id, customer_id, order_date
        FROM orders_lab
        WHERE order_date >= DATE '2026-01-01'
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_order.order_id || ' / ' ||
            r_order.customer_id
        );
    END LOOP;
END;
/
~~~

Đây là cách ngắn gọn cho xử lý tuần tự. Nếu cần truyền record ra ngoài hoặc dùng lại type ở nhiều subprogram, hãy khai báo cursor/type rõ ràng trong package.

## 7. SELECT INTO một RECORD

### 7.1. SELECT danh sách cột vào explicit record

~~~sql
DECLARE
    TYPE employee_summary_rec IS RECORD (
        employee_id NUMBER,
        full_name VARCHAR2(80),
        department_id NUMBER
    );

    l_employee employee_summary_rec;
BEGIN
    SELECT employee_id, full_name, department_id
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(
        l_employee.employee_id || ' - ' ||
        l_employee.full_name
    );
END;
/
~~~

Danh sách SELECT phải tương ứng với các trường record theo số lượng, thứ tự và datatype tương thích. Hãy viết danh sách cột rõ ràng thay vì dựa vào thứ tự ngầm.

### 7.2. SELECT INTO phải trả đúng một hàng

SELECT INTO là câu truy vấn một hàng:

- Không có hàng: phát sinh NO_DATA_FOUND.
- Nhiều hơn một hàng: phát sinh TOO_MANY_ROWS.
- Đúng một hàng: gán giá trị vào record.

Ví dụ xử lý:

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    BEGIN
        SELECT *
        INTO l_employee
        FROM employee_data_lab
        WHERE employee_id = 999999;

        DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('Employee not found');
        WHEN TOO_MANY_ROWS THEN
            DBMS_OUTPUT.PUT_LINE('Query returned more than one row');
    END;
END;
/
~~~

Nếu điều kiện dự kiến duy nhất, hãy có primary key/unique constraint để bảo vệ giả định đó. Không dùng ROWNUM = 1 để che dữ liệu trùng nếu nghiệp vụ yêu cầu duy nhất.

### 7.3. Dùng aggregate SELECT INTO record

~~~sql
DECLARE
    TYPE department_stats_rec IS RECORD (
        department_id NUMBER,
        employee_count NUMBER,
        average_salary NUMBER
    );

    l_stats department_stats_rec;
BEGIN
    SELECT
        10,
        COUNT(*),
        AVG(monthly_salary)
    INTO l_stats
    FROM employee_data_lab
    WHERE department_id = 10
      AND employment_status = 'ACTIVE';

    DBMS_OUTPUT.PUT_LINE(l_stats.employee_count);
END;
/
~~~

Aggregate không có GROUP BY thường trả một hàng, ngay cả khi không có hàng nguồn; COUNT(*) trả 0, các aggregate khác như AVG trả NULL khi không có giá trị. Hãy thiết kế record và xử lý NULL theo semantics đó.

## 8. DML RETURNING INTO và trường record

Một câu INSERT/UPDATE/DELETE có thể trả giá trị cột bị tác động vào biến PL/SQL bằng RETURNING INTO. Có thể trả vào từng trường của record:

~~~sql
DECLARE
    TYPE created_order_rec IS RECORD (
        order_id NUMBER,
        status VARCHAR2(12)
    );

    l_created created_order_rec;
BEGIN
    INSERT INTO orders_lab (
        order_id,
        customer_id,
        order_date,
        status,
        total_amount
    )
    VALUES (
        9001,
        501,
        DATE '2026-04-10',
        'NEW',
        125
    )
    RETURNING order_id, status
    INTO l_created.order_id, l_created.status;

    DBMS_OUTPUT.PUT_LINE(
        'Created order ' || l_created.order_id ||
        ' status=' || l_created.status
    );

    ROLLBACK;
END;
/
~~~

RETURNING INTO nhận danh sách biến đích. Dùng từng trường record giúp thể hiện dữ liệu được trả về. Câu lệnh vẫn tuân theo transaction; ROLLBACK trong ví dụ hủy INSERT.

## 9. RECORD lồng nhau để mô hình hóa dữ liệu nhiều tầng

Một thực thể nghiệp vụ có thể chứa nhóm thuộc tính con. Ví dụ khách hàng có thông tin định danh và địa chỉ; địa chỉ lại gồm đường, quận, thành phố và mã bưu chính.

### 9.1. Khai báo nested record

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        street VARCHAR2(120),
        district VARCHAR2(60),
        city VARCHAR2(60),
        postal_code VARCHAR2(20)
    );

    TYPE customer_rec IS RECORD (
        customer_id NUMBER,
        full_name VARCHAR2(100),
        email VARCHAR2(120),
        address address_rec
    );

    l_customer customer_rec;
BEGIN
    l_customer.customer_id := 501;
    l_customer.full_name := 'Tran Minh';
    l_customer.email := 'minh@example.test';
    l_customer.address.street := '25 Le Loi';
    l_customer.address.district := 'District 1';
    l_customer.address.city := 'Ho Chi Minh City';
    l_customer.address.postal_code := '700000';

    DBMS_OUTPUT.PUT_LINE(
        l_customer.full_name || ' lives in ' ||
        l_customer.address.city
    );
END;
/
~~~

Nested record giúp nhóm thuộc tính theo ý nghĩa. Nó tránh một record phẳng có hàng chục trường với tên lặp như BILLING_CITY, SHIPPING_CITY, BILLING_POSTAL_CODE, SHIPPING_POSTAL_CODE.

### 9.2. Hai địa chỉ cùng dùng một type

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        street VARCHAR2(120),
        city VARCHAR2(60),
        postal_code VARCHAR2(20)
    );

    TYPE customer_rec IS RECORD (
        customer_id NUMBER,
        billing_address address_rec,
        shipping_address address_rec
    );

    l_customer customer_rec;
BEGIN
    l_customer.customer_id := 501;
    l_customer.billing_address.city := 'Ho Chi Minh City';
    l_customer.shipping_address.city := 'Da Nang';
END;
/
~~~

Hai trường address dùng cùng một type, nhưng là hai giá trị độc lập. Thay đổi billing_address không tự thay đổi shipping_address.

### 9.3. Chọn độ sâu hợp lý

Nested records hữu ích khi các nhóm thuộc tính có ý nghĩa riêng và được xử lý cùng nhau. Không nên lồng quá sâu chỉ để phản ánh mọi quan hệ trong database. Cấu trúc trong bộ nhớ phục vụ code; mô hình quan hệ trong database phục vụ lưu trữ, constraint, truy vấn và tính toàn vẹn.

## 10. RECORD trong package specification: tạo API PL/SQL

Nếu nhiều procedure/function cần trao đổi cùng một cấu trúc, hãy công bố record type trong package specification. Consumer có thể khai báo biến theo type công khai đó.

### 10.1. Khai báo public record type

~~~sql
CREATE OR REPLACE PACKAGE employee_api_lab AS
    TYPE employee_info_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE,
        work_email employee_data_lab.work_email%TYPE
    );

    PROCEDURE get_employee (
        p_employee_id IN employee_data_lab.employee_id%TYPE,
        p_employee OUT employee_info_rec
    );
END employee_api_lab;
/
~~~

Package specification công bố type và chữ ký procedure. Người gọi có thể tham chiếu:

~~~sql
DECLARE
    l_employee employee_api_lab.employee_info_rec;
BEGIN
    employee_api_lab.get_employee(
        p_employee_id => 101,
        p_employee => l_employee
    );

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

### 10.2. Cài đặt package body

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api_lab AS
    PROCEDURE get_employee (
        p_employee_id IN employee_data_lab.employee_id%TYPE,
        p_employee OUT employee_info_rec
    ) IS
    BEGIN
        SELECT
            employee_id,
            full_name,
            department_id,
            work_email
        INTO p_employee
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END get_employee;
END employee_api_lab;
/
~~~

Package type tạo một contract chung cho producer và consumer. Khi cần thay đổi record public, hãy xem đây là thay đổi API có thể ảnh hưởng mọi caller và dependent PL/SQL units.

### 10.3. IN, OUT và IN OUT

Record có thể được truyền như parameter:

- IN: procedure đọc giá trị record do caller truyền.
- OUT: procedure tạo kết quả và trả record về caller.
- IN OUT: procedure đọc rồi thay đổi record.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE employee_rules_lab AS
    TYPE employee_rec IS RECORD (
        employee_id NUMBER,
        full_name VARCHAR2(80),
        department_id NUMBER
    );

    PROCEDURE normalize_employee (
        p_employee IN OUT employee_rec
    );
END employee_rules_lab;
/

CREATE OR REPLACE PACKAGE BODY employee_rules_lab AS
    PROCEDURE normalize_employee (
        p_employee IN OUT employee_rec
    ) IS
    BEGIN
        p_employee.full_name := TRIM(p_employee.full_name);
    END normalize_employee;
END employee_rules_lab;
/
~~~

OUT/IN OUT record là dữ liệu truyền trong PL/SQL call. Không nhầm nó với việc trả record trực tiếp từ một câu SQL cho client ngoài database.

### 10.4. Đặt type ở đúng phạm vi

| Nơi khai báo | Phạm vi sử dụng |
| --- | --- |
| Khối DECLARE | Khối đó và các khối con |
| Phần khai báo của procedure/function | Subprogram đó và phần thân |
| Package specification | Public API cho consumer có quyền execute package |
| Package body | Nội bộ package body |

Nếu type chỉ phục vụ một procedure, khai báo local. Nếu nhiều subprogram cùng dùng và caller cần tạo biến kiểu đó, khai báo trong package specification.

## 11. Collection chứa nhiều RECORD

RECORD đại diện một cấu trúc nhiều trường. Nếu cần nhiều hàng, có thể dùng collection chứa record.

### 11.1. Khai báo associative array of records

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE
    );

    TYPE employee_tab IS TABLE OF employee_rec
        INDEX BY PLS_INTEGER;

    l_employees employee_tab;
BEGIN
    l_employees(1).employee_id := 101;
    l_employees(1).full_name := 'Nguyen An';
    l_employees(1).department_id := 10;

    l_employees(2).employee_id := 102;
    l_employees(2).full_name := 'Tran Binh';
    l_employees(2).department_id := 10;

    DBMS_OUTPUT.PUT_LINE(l_employees(2).full_name);
END;
/
~~~

Associative array dùng key để truy cập phần tử. Ở ví dụ này, mỗi phần tử là một employee_rec. Collection và record là hai cấp cấu trúc khác nhau: collection chứa nhiều phần tử, mỗi phần tử có nhiều trường.

### 11.2. BULK COLLECT vào collection of records

~~~sql
DECLARE
    TYPE employee_tab IS TABLE OF employee_data_lab%ROWTYPE
        INDEX BY PLS_INTEGER;

    l_employees employee_tab;
BEGIN
    SELECT *
    BULK COLLECT INTO l_employees
    FROM employee_data_lab
    WHERE department_id = 10
    ORDER BY employee_id;

    FOR i IN 1 .. l_employees.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_employees(i).employee_id || ' - ' ||
            l_employees(i).full_name
        );
    END LOOP;
END;
/
~~~

BULK COLLECT lấy nhiều hàng vào collection trong một thao tác PL/SQL/SQL boundary. Nó có thể giảm context switching so với fetch từng hàng trong loop, nhưng giữ toàn bộ kết quả trong bộ nhớ có thể tốn PGA nếu tập dữ liệu lớn.

### 11.3. BULK COLLECT với LIMIT

Với dữ liệu lớn, dùng cursor và FETCH BULK COLLECT LIMIT để xử lý theo batch:

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT *
        FROM employee_data_lab
        ORDER BY employee_id;

    TYPE employee_tab IS TABLE OF c_employee%ROWTYPE
        INDEX BY PLS_INTEGER;

    l_batch employee_tab;
BEGIN
    OPEN c_employee;

    LOOP
        FETCH c_employee
        BULK COLLECT INTO l_batch
        LIMIT 500;

        EXIT WHEN l_batch.COUNT = 0;

        FOR i IN 1 .. l_batch.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(l_batch(i).full_name);
        END LOOP;
    END LOOP;

    CLOSE c_employee;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employee%ISOPEN THEN
            CLOSE c_employee;
        END IF;
        RAISE;
END;
/
~~~

LIMIT giới hạn số hàng được fetch mỗi batch, giúp kiểm soát bộ nhớ. Trong ứng dụng thật, xử lý trong loop cần có mục tiêu rõ và không nên dùng DBMS_OUTPUT cho khối lượng dữ liệu lớn.

### 11.4. Collection rỗng và COUNT

Với associative array chưa có phần tử, COUNT trả 0. Vì vậy:

~~~sql
IF l_employees.COUNT = 0 THEN
    DBMS_OUTPUT.PUT_LINE('No employees');
END IF;
~~~

Không truy cập phần tử chưa được gán. Với associative array có key không liên tục, không giả định các chỉ số luôn từ 1 đến COUNT; dùng FIRST/NEXT hoặc collection method phù hợp.

### 11.5. FORALL và record collections

FORALL dùng để thực hiện DML bulk với collection, giảm context switching. Có thể thiết kế collection of records để giữ dữ liệu theo nhóm; khi dùng các trường collection trong DML, hãy tuân thủ cú pháp bulk binding được hỗ trợ và thử trên đúng release.

Ví dụ đơn giản dùng các collection scalar:

~~~sql
DECLARE
    TYPE id_tab IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE salary_tab IS TABLE OF NUMBER INDEX BY PLS_INTEGER;

    l_ids id_tab;
    l_salaries salary_tab;
BEGIN
    l_ids(1) := 101;
    l_ids(2) := 102;
    l_salaries(1) := 2600;
    l_salaries(2) := 3300;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employee_data_lab
        SET monthly_salary = l_salaries(i)
        WHERE employee_id = l_ids(i);
END;
/
~~~

Đây là ví dụ dùng hai collection scalar có cùng chỉ số. Nếu dùng collection of records trong FORALL, cần xác nhận cú pháp record-field reference trong DML và tính liên tục của index set; không ép dữ liệu vào record collection chỉ để làm code ngắn hơn.

## 12. RECORD và SQL engine: ranh giới cần nhớ

PL/SQL và SQL là hai engine có datatype và phạm vi sử dụng khác nhau. RECORD là datatype PL/SQL; không thể coi nó như một kiểu cột SQL thông thường.

### 12.1. RECORD PL/SQL không phải SQL object type

| Đặc điểm | PL/SQL RECORD | SQL object type |
| --- | --- | --- |
| Khai báo | TYPE ... IS RECORD trong PL/SQL | CREATE TYPE ... AS OBJECT ở schema |
| Phạm vi | PL/SQL block/subprogram/package | SQL schema object |
| Có thể dùng làm cột bảng | Không trực tiếp | Có thể, theo điều kiện SQL type |
| Có thể có method | Không như object type | Có thể định nghĩa method |
| Dùng trong PL/SQL | Có | Có |
| Dùng trực tiếp trong SQL | Bị giới hạn; không phải SQL datatype | Được SQL engine hỗ trợ |

Nếu cần lưu một cấu trúc nhiều thuộc tính như một cột object, truyền qua SQL/client hoặc dùng trong SQL expressions, hãy tìm hiểu SQL object type và nested table/varray types. Nếu chỉ cần gom dữ liệu trong PL/SQL, RECORD thường đơn giản hơn.

### 12.2. Không thể khai báo cột bảng bằng local RECORD type

Không dùng một type khai báo trong DECLARE để tạo cột SQL:

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        city VARCHAR2(60),
        postal_code VARCHAR2(20)
    );
BEGIN
    -- address_rec khong phai SQL datatype de khai bao cot bang.
    NULL;
END;
/
~~~

Để lưu dữ liệu, tạo các cột scalar riêng hoặc định nghĩa SQL object type:

~~~sql
CREATE TYPE address_obj_lab AS OBJECT (
    city VARCHAR2(60),
    postal_code VARCHAR2(20)
);
/

CREATE TABLE customer_object_lab (
    customer_id NUMBER PRIMARY KEY,
    address_info address_obj_lab
);
~~~

SQL object type có vòng đời schema và semantics khác với record type local.

### 12.3. Không trả PL/SQL RECORD như một cột SQL tùy ý

Một procedure PL/SQL có thể nhận/trả record parameter cho caller PL/SQL phù hợp. Nhưng không thể giả định một câu SELECT thuần SQL có thể gọi function trả về một local PL/SQL RECORD như một scalar SQL value. SQL engine cần datatype mà SQL hiểu được.

Nếu API phải được gọi từ SQL hoặc client qua SQL interface, cân nhắc:

- SQL object type.
- Scalar columns.
- REF CURSOR cho result set.
- JSON/XML theo contract và phiên bản.
- Một package procedure trả các OUT scalar hoặc cursor.

### 12.4. RECORD không thay thế mô hình quan hệ

Một customer record trong bộ nhớ có thể chứa nested address record, nhưng database quan hệ vẫn có thể lưu CUSTOMER và ADDRESS ở các bảng riêng để hỗ trợ:

- Ràng buộc toàn vẹn.
- Truy vấn và join.
- Tái sử dụng địa chỉ.
- Lịch sử thay đổi.
- Transaction và concurrency.

Record là cách tổ chức dữ liệu trong PL/SQL, không phải chỉ dẫn rằng phải gộp các bảng thành một cấu trúc lưu trữ.

## 13. Thiết kế mô hình nhiều trường theo nghiệp vụ

### 13.1. Mô hình đơn hàng

Một đơn hàng thường có header và nhiều line:

~~~text
ORDER
  order_id
  customer_id
  order_date
  status
  shipping_address
      street
      city
      postal_code
  lines[]
      line_id
      product_id
      quantity
      unit_price
~~~

Trong PL/SQL có thể mô hình hóa:

~~~sql
DECLARE
    TYPE address_rec IS RECORD (
        street VARCHAR2(120),
        city VARCHAR2(60),
        postal_code VARCHAR2(20)
    );

    TYPE order_header_rec IS RECORD (
        order_id NUMBER,
        customer_id NUMBER,
        order_date DATE,
        status VARCHAR2(12),
        shipping_address address_rec
    );

    TYPE order_line_rec IS RECORD (
        line_id NUMBER,
        product_id NUMBER,
        quantity NUMBER(10,2),
        unit_price NUMBER(12,2)
    );

    TYPE order_line_tab IS TABLE OF order_line_rec
        INDEX BY PLS_INTEGER;

    l_order order_header_rec;
    l_lines order_line_tab;
BEGIN
    l_order.order_id := 9001;
    l_order.customer_id := 501;
    l_order.order_date := SYSDATE;
    l_order.status := 'NEW';
    l_order.shipping_address.city := 'Ho Chi Minh City';

    l_lines(1).line_id := 1;
    l_lines(1).product_id := 100;
    l_lines(1).quantity := 2;
    l_lines(1).unit_price := 25;

    l_lines(2).line_id := 2;
    l_lines(2).product_id := 200;
    l_lines(2).quantity := 1;
    l_lines(2).unit_price := 80;
END;
/
~~~

Ở đây order header là một record, địa chỉ là nested record, còn các dòng hàng là collection of records. Mô hình này thể hiện quan hệ một đơn hàng có nhiều dòng hàng trong bộ nhớ.

### 13.2. Tách dữ liệu bắt buộc và tùy chọn

Khi thiết kế record, hãy phân biệt:

- Trường định danh: thường phải có để xác định entity.
- Trường nghiệp vụ bắt buộc: cần validate trước khi persistence.
- Trường tùy chọn: có thể NULL.
- Trường tính toán: có thể suy ra từ trường khác.
- Trường trạng thái: phản ánh lifecycle.

Đừng để một record có trạng thái nửa khởi tạo mà code sau không biết trường nào đã được gán. Có thể dùng factory procedure, validation function hoặc cờ initialized để kiểm soát.

### 13.3. Tạo procedure validate record

~~~sql
DECLARE
    TYPE payment_rec IS RECORD (
        payment_id NUMBER,
        customer_id NUMBER,
        amount NUMBER(12,2),
        currency_code VARCHAR2(3)
    );

    l_payment payment_rec;

    PROCEDURE validate_payment(p_payment IN payment_rec) IS
    BEGIN
        IF p_payment.payment_id IS NULL THEN
            RAISE_APPLICATION_ERROR(-20001, 'Payment ID is required');
        END IF;

        IF p_payment.customer_id IS NULL THEN
            RAISE_APPLICATION_ERROR(-20002, 'Customer ID is required');
        END IF;

        IF p_payment.amount IS NULL OR p_payment.amount <= 0 THEN
            RAISE_APPLICATION_ERROR(-20003, 'Amount must be positive');
        END IF;

        IF p_payment.currency_code IS NULL
           OR LENGTH(p_payment.currency_code) <> 3
        THEN
            RAISE_APPLICATION_ERROR(-20004, 'Invalid currency code');
        END IF;
    END validate_payment;
BEGIN
    l_payment.payment_id := 7001;
    l_payment.customer_id := 501;
    l_payment.amount := 125.50;
    l_payment.currency_code := 'VND';

    validate_payment(l_payment);
END;
/
~~~

Validation ở PL/SQL giúp trả lỗi nghiệp vụ dễ hiểu. Constraint ở bảng vẫn cần thiết để bảo vệ dữ liệu khi có đường ghi khác như batch, SQL client hoặc service khác.

## 14. Xử lý lỗi khi làm việc với RECORD

### 14.1. NO_DATA_FOUND

SELECT INTO không tìm thấy hàng sẽ phát sinh NO_DATA_FOUND. Nếu “không tồn tại” là trạng thái hợp lệ, hãy xử lý rõ ràng:

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    BEGIN
        SELECT *
        INTO l_employee
        FROM employee_data_lab
        WHERE employee_id = 999;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('No matching employee');
            RETURN;
    END;

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

### 14.2. TOO_MANY_ROWS

Nếu query có thể trả nhiều hàng, dùng cursor hoặc collection thay vì SELECT INTO một record. Không bắt TOO_MANY_ROWS rồi lấy một kết quả tùy ý nếu nghiệp vụ không định nghĩa cách chọn.

### 14.3. Trường NULL

Một trường record có thể NULL. So sánh:

~~~sql
IF l_employee.work_email IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('No work email');
END IF;
~~~

Không dùng phép so sánh bằng với NULL. Nếu cần so sánh hai giá trị nullable, phải định nghĩa semantics rõ:

~~~sql
IF l_old_email = l_new_email
   OR (l_old_email IS NULL AND l_new_email IS NULL)
THEN
    -- Gia tri duoc xem la giong nhau theo quy uoc nay.
    NULL;
END IF;
~~~

### 14.4. Record OUT khi exception

Nếu procedure có OUT record và phát sinh exception trước khi gán đầy đủ, caller không nên giả định record đã có kết quả hoàn chỉnh. Hãy:

- Gán kết quả chỉ khi đã đọc/validate đủ dữ liệu.
- Dùng status code hoặc exception để biểu đạt lỗi.
- Không nuốt exception rồi trả record nửa hoàn chỉnh.
- Tài liệu hóa khi nào OUT record được bảo đảm có giá trị.

## 15. Hiệu năng và thực hành tốt

### 15.1. Record không tự làm SQL nhanh hơn

RECORD chủ yếu cải thiện cách tổ chức dữ liệu trong PL/SQL. Nó không thay thế index, không giảm số block đọc và không tự biến row-by-row SQL thành bulk SQL.

Hiệu năng phụ thuộc cách lấy dữ liệu:

- SELECT INTO một record: một hàng.
- Cursor FOR LOOP: fetch từng hàng qua cơ chế cursor loop.
- BULK COLLECT: fetch nhiều hàng theo batch.
- FORALL: thực hiện DML bulk với collection.

### 15.2. Dùng %ROWTYPE khi thực sự cần toàn hàng

Nếu chỉ cần vài trường, explicit record hoặc cursor record với select list tối thiểu giúp:

- Giảm dữ liệu không cần thiết.
- Thể hiện dependency.
- Hạn chế coupling với schema rộng.
- Tránh đọc cột nhạy cảm không cần thiết.

### 15.3. Dùng %TYPE để tránh hard-code datatype

Datatype neo theo cột giúp code theo kịp precision/length của schema khi compile lại. Tuy nhiên, thay đổi cột vẫn có thể ảnh hưởng API và cần regression testing.

### 15.4. Dùng package type cho contract dùng chung

Nếu record đi qua nhiều procedure hoặc được caller tạo trực tiếp, đặt type ở package specification. Tránh khai báo các record type riêng lẻ giống nhau ở nhiều nơi vì khó bảo trì và dễ lệch cấu trúc.

### 15.5. Không fetch toàn bộ bảng vào collection nếu không cần

BULK COLLECT toàn bộ hàng có thể tiêu thụ nhiều PGA. Dùng LIMIT, predicate phù hợp hoặc xử lý theo key range khi dữ liệu lớn.

### 15.6. Giữ record có trách nhiệm rõ ràng

Một record nên đại diện một khái niệm có ý nghĩa. Tránh gom mọi dữ liệu từ nhiều bảng vào một record khổng lồ chỉ để tiện truyền. Có thể dùng nested record hoặc nhiều record type tách biệt cho header, detail, address và payment.

### 15.7. Không dùng record để né constraint

Kiểm tra dữ liệu trong PL/SQL là cần thiết nhưng không thay thế constraint database. Nếu hai session hoặc hai ứng dụng cùng ghi dữ liệu, constraint là lớp bảo vệ chung ở database.

## 16. Bài thực hành tổng hợp

Bài lab dùng bảng nhân viên trong schema lab. Nếu bảng chưa có, tạo:

~~~sql
CREATE TABLE employee_data_lab (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    work_email VARCHAR2(120 CHAR),
    monthly_salary NUMBER(12,2) NOT NULL,
    employment_status VARCHAR2(12 CHAR) NOT NULL
);

INSERT INTO employee_data_lab VALUES
    (101, 'Nguyen An', 10, 'an@example.test', 2500, 'ACTIVE');
INSERT INTO employee_data_lab VALUES
    (102, 'Tran Binh', 10, 'binh@example.test', 3200, 'ACTIVE');
INSERT INTO employee_data_lab VALUES
    (103, 'Le Chi', 20, 'chi@example.test', 2800, 'ACTIVE');
COMMIT;
~~~

### Bước 1 — Khai báo record theo %TYPE

~~~sql
DECLARE
    TYPE employee_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE,
        work_email employee_data_lab.work_email%TYPE
    );

    l_employee employee_rec;
BEGIN
    SELECT employee_id, full_name, department_id, work_email
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

### Bước 2 — Dùng %ROWTYPE

~~~sql
DECLARE
    l_employee employee_data_lab%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employee_data_lab
    WHERE employee_id = 102;

    DBMS_OUTPUT.PUT_LINE(
        l_employee.employee_id || ' ' ||
        l_employee.full_name || ' ' ||
        l_employee.monthly_salary
    );
END;
/
~~~

### Bước 3 — Cursor record

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, full_name, department_id
        FROM employee_data_lab
        WHERE employment_status = 'ACTIVE';
BEGIN
    FOR r IN c_employee LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ': ' || r.full_name
        );
    END LOOP;
END;
/
~~~

### Bước 4 — Package API trả record

~~~sql
CREATE OR REPLACE PACKAGE employee_record_api_lab AS
    TYPE employee_rec IS RECORD (
        employee_id employee_data_lab.employee_id%TYPE,
        full_name employee_data_lab.full_name%TYPE,
        department_id employee_data_lab.department_id%TYPE
    );

    PROCEDURE find_employee (
        p_employee_id IN employee_data_lab.employee_id%TYPE,
        p_employee OUT employee_rec
    );
END employee_record_api_lab;
/

CREATE OR REPLACE PACKAGE BODY employee_record_api_lab AS
    PROCEDURE find_employee (
        p_employee_id IN employee_data_lab.employee_id%TYPE,
        p_employee OUT employee_rec
    ) IS
    BEGIN
        SELECT employee_id, full_name, department_id
        INTO p_employee
        FROM employee_data_lab
        WHERE employee_id = p_employee_id;
    END find_employee;
END employee_record_api_lab;
/
~~~

Gọi API:

~~~sql
DECLARE
    l_employee employee_record_api_lab.employee_rec;
BEGIN
    employee_record_api_lab.find_employee(103, l_employee);
    DBMS_OUTPUT.PUT_LINE(l_employee.full_name);
END;
/
~~~

### Bước 5 — BULK COLLECT nhiều record

~~~sql
DECLARE
    TYPE employee_tab IS TABLE OF employee_data_lab%ROWTYPE
        INDEX BY PLS_INTEGER;

    l_employees employee_tab;
BEGIN
    SELECT *
    BULK COLLECT INTO l_employees
    FROM employee_data_lab
    WHERE department_id = 10
    ORDER BY employee_id;

    FOR i IN 1 .. l_employees.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_employees(i).employee_id || ': ' ||
            l_employees(i).full_name
        );
    END LOOP;
END;
/
~~~

### Bước 6 — Dọn lab (tùy chọn)

Chỉ chạy nếu chắc chắn đây là bảng/package lab do bạn tạo và không cần dữ liệu nữa:

~~~sql
DROP PACKAGE employee_record_api_lab;
DROP TABLE employee_data_lab PURGE;
~~~

DROP PACKAGE và DROP TABLE là DDL, có implicit commit theo quy tắc Oracle. Không chạy trên object nghiệp vụ thật.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| RECORD là một bảng tạm | RECORD là datatype PL/SQL trong bộ nhớ |
| RECORD và collection giống nhau | RECORD gom nhiều trường; collection chứa nhiều phần tử |
| %ROWTYPE kế thừa mọi constraint/default của bảng | Nó bám cấu trúc và datatype, không biến biến PL/SQL thành hàng có mọi constraint |
| %TYPE tạo kiểu dữ liệu hoàn toàn độc lập | Nó neo datatype theo cột/biến được tham chiếu |
| Hai record cùng trường luôn gán được cho nhau | Cần cùng kiểu/compatibility; nên dùng type chung trong package API |
| SELECT INTO record có thể trả nhiều hàng | SELECT INTO yêu cầu đúng một hàng |
| Cursor%ROWTYPE luôn chứa toàn bộ cột bảng | Nó chứa select list của cursor |
| Có thể so sánh toàn record bằng = | So sánh các trường hoặc viết logic riêng |
| Có thể kiểm tra cả record IS NULL | Kiểm tra trường định danh hoặc cờ initialized |
| PL/SQL RECORD dùng trực tiếp làm cột SQL | Cần SQL datatype/object type phù hợp |
| BULK COLLECT luôn tốt hơn cursor loop | Nó có thể tiêu thụ nhiều PGA; dùng LIMIT khi cần |
| RECORD tự bảo đảm dữ liệu hợp lệ | Constraint/validation vẫn cần ở tầng phù hợp |

## 18. Câu hỏi tự kiểm tra

1. RECORD là gì và một record thường đại diện cho điều gì?
2. TYPE ... IS RECORD khác biến record như thế nào?
3. Truy cập trường record bằng cú pháp nào?
4. Trường record có thể khai báo default không?
5. Nếu một trường record khai báo NOT NULL thì cần lưu ý gì?
6. %TYPE dùng để làm gì?
7. %TYPE có tự kế thừa mọi constraint của cột không?
8. %ROWTYPE khác explicit RECORD ở điểm nào?
9. Vì sao %ROWTYPE không thay thế được mọi explicit record?
10. Cursor%ROWTYPE chứa các trường nào?
11. SELECT INTO một record yêu cầu bao nhiêu hàng?
12. NO_DATA_FOUND và TOO_MANY_ROWS xảy ra khi nào?
13. Có thể gán toàn record trong trường hợp nào?
14. Qualified expressions có từ phiên bản nào?
15. Vì sao không nên so sánh hai record bằng toán tử =?
16. Nested record giúp mô hình hóa dữ liệu nào?
17. Vì sao nên khai báo record type trong package specification?
18. IN, OUT và IN OUT áp dụng cho record parameter thế nào?
19. RECORD và collection khác nhau ra sao?
20. BULK COLLECT LIMIT giúp kiểm soát điều gì?
21. Vì sao PL/SQL RECORD không thể dùng trực tiếp làm cột bảng SQL?
22. Khi nào nên dùng SQL object type?
23. RECORD có thay thế transaction hoặc constraint không?
24. Vì sao không nên BULK COLLECT toàn bộ một bảng rất lớn vào PGA?
25. Sau khi thay đổi public record type trong package, cần xem xét điều gì?

**Gợi ý trả lời:**

1. Kiểu PL/SQL gồm nhiều trường có tên; thường đại diện một hàng hoặc một cấu trúc nghiệp vụ.
2. TYPE định nghĩa cấu trúc; biến record chứa giá trị theo cấu trúc đó.
3. record_variable.field_name.
4. Có.
5. Phải có default hợp lệ và không gán NULL cho trường đó.
6. Neo datatype theo cột hoặc biến có sẵn.
7. Không.
8. %ROWTYPE lấy cấu trúc từ bảng/view/cursor; explicit RECORD cho phép chọn và đặt tên trường theo contract.
9. Nó có thể quá rộng hoặc tạo coupling với toàn bảng.
10. Các cột/biểu thức trong select list của cursor.
11. Đúng một hàng.
12. Không có hàng hoặc nhiều hơn một hàng.
13. Khi hai biến có cùng kiểu record tương thích.
14. Oracle Database 18c trở lên.
15. PL/SQL không cung cấp equality tổng quát cho toàn record.
16. Nhóm thuộc tính con như địa chỉ trong khách hàng hoặc địa chỉ giao hàng trong đơn.
17. Để nhiều subprogram và caller dùng cùng một type contract.
18. IN đọc, OUT trả kết quả, IN OUT đọc rồi thay đổi record.
19. RECORD chứa nhiều trường trong một phần tử; collection chứa nhiều phần tử.
20. Số hàng giữ trong bộ nhớ mỗi batch.
21. RECORD là datatype PL/SQL, không phải SQL schema datatype.
22. Khi cần kiểu dữ liệu được SQL engine hiểu, lưu trong cột hoặc dùng trong SQL expressions.
23. Không; record chỉ tổ chức dữ liệu trong bộ nhớ.
24. Có thể tiêu thụ nhiều PGA và gây áp lực bộ nhớ.
25. Caller, dependency, datatype, semantics và khả năng tương thích API.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — Record Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/record-types.html): khai báo, sử dụng và thao tác với record.
- [Oracle Database PL/SQL Language Reference — %ROWTYPE Attribute](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/ROWTYPE-attribute.html): record dựa trên hàng bảng/view/cursor.
- [Oracle Database PL/SQL Language Reference — %TYPE Attribute](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/TYPE-attribute.html): neo datatype theo cột hoặc biến.
- [Oracle Database PL/SQL Language Reference — Assigning Values to Records](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/assigning-values-records.html): gán giá trị cho record.
- [Oracle Database PL/SQL Language Reference — Cursor Variables and Explicit Cursors](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursors-overview.html): cursor, fetch và cursor row types.
- [Oracle Database PL/SQL Language Reference — BULK COLLECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html): bulk SQL, collection và giới hạn fetch.
- [Oracle Database SQL Language Reference — Object Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/adobj/): SQL object types và khả năng dùng trong SQL.

**Nguyên tắc cần nhớ:** RECORD gom nhiều trường có liên quan thành một giá trị PL/SQL có cấu trúc. Dùng explicit RECORD khi muốn định nghĩa contract vừa đủ; dùng %TYPE để neo datatype; dùng %ROWTYPE khi cần toàn bộ cấu trúc hàng; dùng cursor%ROWTYPE cho kết quả truy vấn; và dùng collection of records khi cần nhiều hàng. Hãy nhớ RECORD là kiểu PL/SQL trong bộ nhớ, không phải SQL object type hay bảng lưu trữ.
