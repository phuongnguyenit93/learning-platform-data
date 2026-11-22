# SQL injection, bind parameter và kiểm soát tên đối tượng động trong Oracle Database

SQL injection xảy ra khi dữ liệu đầu vào không đáng tin cậy bị ghép trực tiếp vào câu SQL hoặc PL/SQL dưới dạng mã lệnh. Khi đó, một giá trị người dùng dự định gửi như dữ liệu có thể làm thay đổi cấu trúc câu lệnh, thêm điều kiện, đọc dữ liệu ngoài phạm vi, sửa/xóa dữ liệu hoặc thực thi một câu lệnh khác trong phạm vi quyền của database account.

Biện pháp quan trọng nhất để ngăn SQL injection là **dùng bind variables cho mọi giá trị dữ liệu**. Bind variable gửi giá trị tách khỏi SQL text, nên dấu nháy, dấu chấm phẩy hoặc chuỗi giống cú pháp SQL không thể biến thành mã lệnh.

Tên bảng, tên schema, tên cột, từ khóa và hướng sắp xếp là thành phần cấu trúc SQL; chúng không thể được thay bằng bind variable như một giá trị thông thường. Khi thật sự cần chọn đối tượng động, phải dùng **allowlist** xác định những lựa chọn được phép, sau đó kiểm tra/quote tên bằng các hàm phù hợp như DBMS_ASSERT. DBMS_ASSERT hỗ trợ xác thực cú pháp và tên đối tượng; nó không thay thế allowlist, kiểm soát quyền hay thiết kế an toàn.

Nội dung bài tập trung vào Oracle Database, SQL tĩnh, Native Dynamic SQL, DBMS_SQL, DBMS_ASSERT và quyền thực thi PL/SQL. Các ví dụ minh họa cách biến dữ liệu đầu vào thành bind, cách kiểm soát identifier động và các lỗi bảo mật thường gặp.

## 1. SQL injection là gì?

Một ứng dụng thường tạo truy vấn bằng cách kết hợp SQL text với dữ liệu người dùng. Nếu ứng dụng nối chuỗi không an toàn, dữ liệu có thể làm thay đổi cú pháp SQL.

Ví dụ giả sử ứng dụng muốn tìm user theo tên đăng nhập:

~~~sql
SELECT user_id, username
FROM app_users
WHERE username = '<input>';
~~~

Nếu input được nối thẳng vào câu SQL, người dùng có thể nhập một chuỗi chứa dấu nháy và toán tử SQL để thay đổi điều kiện. Khi dữ liệu trở thành một phần của SQL text, database phân tích nó như cú pháp.

### 1.1 Ví dụ nối chuỗi không an toàn

~~~sql
CREATE OR REPLACE PROCEDURE find_user_unsafe (
    p_username IN  VARCHAR2,
    p_user_id  OUT NUMBER
)
AS
    l_sql VARCHAR2(4000);
BEGIN
    l_sql :=
        'SELECT user_id FROM app_users WHERE username = '''
        || p_username
        || '''';

    EXECUTE IMMEDIATE l_sql INTO p_user_id;
END;
/
~~~

Đoạn code trên có hai vấn đề:

- Dữ liệu đầu vào được nối vào SQL text.
- Dấu nháy đơn trong dữ liệu có thể kết thúc string literal và đưa phần tiếp theo vào cú pháp SQL.

Khi input làm thay đổi cấu trúc câu lệnh, đây là SQL injection. Không cần người tấn công có quyền kết nối trực tiếp tới database; chỉ cần một ứng dụng hoặc stored procedure nhận input rồi tạo SQL không an toàn.

### 1.2 Ví dụ an toàn bằng bind variable

~~~sql
CREATE OR REPLACE PROCEDURE find_user_safe (
    p_username IN  VARCHAR2,
    p_user_id  OUT NUMBER
)
AS
BEGIN
    EXECUTE IMMEDIATE
        'SELECT user_id
           FROM app_users
          WHERE username = :username'
        INTO p_user_id
        USING p_username;
END;
/
~~~

SQL text chứa placeholder :username. Giá trị p_username được gửi riêng trong USING, nên dù input chứa dấu nháy hoặc chuỗi giống SQL, Oracle vẫn xử lý nó như dữ liệu của predicate.

### 1.3 Điều gì có thể xảy ra khi bị SQL injection?

Tùy quyền của schema và cách ứng dụng thực thi, SQL injection có thể dẫn đến:

- Bỏ qua xác thực hoặc điều kiện lọc.
- Đọc dữ liệu của người dùng/tenant khác.
- Sửa, thêm hoặc xóa dữ liệu.
- Gọi package/procedure có quyền cao hơn người dùng ứng dụng.
- Thực thi DDL hoặc câu lệnh khác nếu code cho phép nhiều statement hoặc dynamic PL/SQL block không an toàn.
- Truy cập object ngoài phạm vi dự kiến thông qua tên schema/đối tượng được điều khiển.
- Làm lộ thông tin qua lỗi SQL, timing hoặc các kênh phụ.

Mức độ ảnh hưởng phụ thuộc vào quyền của database account, quyền của stored procedure, dữ liệu được phép truy cập và các lớp kiểm soát khác.

## 2. Quy tắc cốt lõi: tách dữ liệu khỏi mã SQL

SQL statement có hai loại thành phần:

| Thành phần | Ví dụ | Cách xử lý an toàn |
|---|---|---|
| Giá trị dữ liệu | username, ngày, số tiền, trạng thái, ID | Bind variable |
| Tên đối tượng | schema, table, view, column | Allowlist, validate và quote identifier |
| Từ khóa/cấu trúc | ASC/DESC, toán tử, tên hàm, join type | Chọn từ tập hằng số được phép |
| Fragment SQL | WHERE clause, ORDER BY expression | Thiết kế cố định hoặc sinh từ cấu trúc đã kiểm soát |

Không dùng một quy tắc cho tất cả đầu vào. Bind variable là lựa chọn chuẩn cho giá trị dữ liệu; identifier và SQL syntax cần được chọn từ các giá trị đã được chương trình kiểm soát.

### 2.1 Bind variable không phải là cơ chế escape chuỗi

Bind không sửa chuỗi bằng cách thêm dấu nháy. Nó giữ SQL text và dữ liệu ở hai kênh riêng biệt:

~~~text
SQL text:  SELECT ... WHERE username = :b1
Bind b1:   chuỗi đầu vào của người dùng
~~~

Oracle parse SQL text như câu lệnh có placeholder, sau đó nhận giá trị bind riêng. Giá trị bind không được parse lại thành cú pháp SQL.

### 2.2 Bind variables còn giúp giảm hard parse

Khi ứng dụng nối literal vào SQL text, mỗi giá trị khác nhau có thể tạo SQL text khác nhau:

~~~sql
SELECT * FROM orders WHERE customer_id = 100;
SELECT * FROM orders WHERE customer_id = 101;
SELECT * FROM orders WHERE customer_id = 102;
~~~

Khi dùng bind:

~~~sql
SELECT * FROM orders WHERE customer_id = :customer_id;
~~~

SQL text có thể được chia sẻ giữa nhiều lần thực thi với giá trị bind khác nhau, giúp giảm parse overhead và tăng khả năng cursor sharing. Optimizer vẫn có thể tạo nhiều child cursor trong một số trường hợp, ví dụ adaptive cursor sharing hoặc bind metadata khác nhau.

Hiệu năng là lợi ích bổ sung. Lý do bảo mật chính vẫn là dữ liệu không thể thay đổi cú pháp câu SQL.

## 3. Bind variables trong SQL tĩnh

Với SQL tĩnh trong PL/SQL, dùng biến PL/SQL trực tiếp trong SQL statement. Oracle tự bind các biến PL/SQL đó:

~~~sql
CREATE OR REPLACE PROCEDURE find_order (
    p_order_id IN orders.order_id%TYPE
) AUTHID DEFINER
AS
    l_status orders.status%TYPE;
BEGIN
    SELECT status
    INTO l_status
    FROM orders
    WHERE order_id = p_order_id;

    DBMS_OUTPUT.PUT_LINE('Status=' || l_status);
END;
/
~~~

Đây là SQL tĩnh. Giá trị p_order_id được truyền như bind; không cần nối chuỗi hay dùng EXECUTE IMMEDIATE.

### 3.1 Không tạo SQL động nếu SQL tĩnh đã đủ

Nếu table, column và cấu trúc truy vấn đã biết lúc compile, SQL tĩnh thường tốt hơn:

- Compiler kiểm tra cú pháp và object reference.
- Dependency được database theo dõi.
- Dễ đọc, bảo trì và review.
- Không phải tự xây dựng SQL text.
- Giá trị đầu vào vẫn được bind.

Chỉ dùng dynamic SQL khi cấu trúc câu lệnh hoặc đối tượng thực sự cần thay đổi lúc runtime, chẳng hạn chọn một trong nhiều bảng hợp lệ hoặc tạo DDL.

## 4. Bind variables với Native Dynamic SQL

Native Dynamic SQL (NDS) là cách dùng EXECUTE IMMEDIATE hoặc OPEN FOR để chạy SQL/PLSQL được tạo lúc runtime.

### 4.1 Bind giá trị trong SELECT một dòng

~~~sql
DECLARE
    l_sql       VARCHAR2(1000);
    l_order_id  NUMBER;
    l_status    VARCHAR2(30);
BEGIN
    l_sql :=
        'SELECT order_id, status
           FROM orders
          WHERE customer_id = :customer_id
            AND order_date >= :from_date';

    EXECUTE IMMEDIATE l_sql
        INTO l_order_id, l_status
        USING p_customer_id, p_from_date;
END;
/
~~~

Các placeholder :customer_id và :from_date đại diện cho giá trị. Các bind trong USING được truyền theo vị trí đối với dynamic SQL statement thông thường.

### 4.2 Bind trong INSERT, UPDATE và DELETE

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'INSERT INTO order_audit
             (order_id, action_name, created_at)
         VALUES
             (:order_id, :action_name, :created_at)'
    USING p_order_id, p_action_name, SYSTIMESTAMP;

    EXECUTE IMMEDIATE
        'UPDATE orders
            SET status = :new_status
          WHERE order_id = :order_id'
    USING p_new_status, p_order_id;

    EXECUTE IMMEDIATE
        'DELETE FROM order_staging
          WHERE batch_id = :batch_id'
    USING p_batch_id;
END;
/
~~~

Mọi giá trị đầu vào đều nằm trong USING. Không nối giá trị vào SQL text, kể cả số hoặc ngày tháng.

### 4.3 Bind OUT parameter với RETURNING INTO

EXECUTE IMMEDIATE hỗ trợ bind input và output. Với DML RETURNING:

~~~sql
DECLARE
    l_new_status VARCHAR2(30);
BEGIN
    EXECUTE IMMEDIATE
        'UPDATE orders
            SET status = :new_status
          WHERE order_id = :order_id
        RETURNING status INTO :returned_status'
    USING p_new_status, p_order_id
    RETURNING INTO l_new_status;

    DBMS_OUTPUT.PUT_LINE(l_new_status);
END;
/
~~~

RETURNING INTO là phần nhận giá trị do DML trả về. Nó không thay cho USING của các input binds.

### 4.4 Bind với nhiều dòng bằng OPEN FOR

Khi truy vấn trả nhiều dòng, dùng REF CURSOR:

~~~sql
DECLARE
    l_cursor SYS_REFCURSOR;
    l_sql    VARCHAR2(1000);
    l_id     NUMBER;
    l_status VARCHAR2(30);
BEGIN
    l_sql :=
        'SELECT order_id, status
           FROM orders
          WHERE customer_id = :customer_id
          ORDER BY order_date DESC';

    OPEN l_cursor FOR l_sql USING p_customer_id;

    LOOP
        FETCH l_cursor INTO l_id, l_status;
        EXIT WHEN l_cursor%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(l_id || ':' || l_status);
    END LOOP;

    CLOSE l_cursor;
END;
/
~~~

Giá trị p_customer_id được bind an toàn. ORDER BY là cấu trúc cố định trong SQL text.

### 4.5 Thứ tự bind và tên placeholder

Với dynamic SQL statement trong Native Dynamic SQL, placeholder được gắn với bind argument theo **vị trí**, không theo tên placeholder. Vì vậy cần giữ thứ tự USING trùng với thứ tự xuất hiện của placeholder.

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql :=
        'UPDATE orders
            SET status = :x
          WHERE customer_id = :x
            AND order_id = :y';

    EXECUTE IMMEDIATE l_sql
        USING p_status, p_customer_id, p_order_id;
END;
/
~~~

Trong một dynamic SQL statement, hai placeholder cùng tên :x vẫn được bind theo từng vị trí. Không nên dựa vào việc tên giống nhau để truyền một bind duy nhất cho nhiều vị trí.

Đối với anonymous PL/SQL block hoặc CALL statement được chạy động, Oracle xử lý placeholder theo tên; nếu placeholder cùng tên xuất hiện nhiều lần, một bind argument có thể được dùng cho các lần xuất hiện đó. Do quy tắc khác nhau, hãy viết ví dụ và USING rõ ràng, kiểm tra đúng loại dynamic statement trước khi tái sử dụng code.

## 5. Những gì không thể bind

Bind variables thay thế giá trị biểu thức, không thay thế cấu trúc SQL.

Các trường hợp không thể dùng bind như một identifier/keyword:

~~~sql
SELECT * FROM :table_name;
ORDER BY :column_name;
SELECT :column_name FROM orders;
CREATE TABLE :new_table (...);
~~~

Trong các ví dụ trên, placeholder không biến thành tên bảng, tên cột hoặc tên đối tượng. Trong biểu thức SELECT :column_name, Oracle trả về giá trị bind như một scalar expression; nó không đọc cột có tên được chứa trong bind.

### 5.1 Phân loại đầu vào

| Đầu vào | Bind được không? | Giải pháp |
|---|---|---|
| Customer ID | Có | Bind NUMBER |
| Username | Có | Bind VARCHAR2 |
| DATE/TIMESTAMP | Có | Bind đúng kiểu ngày giờ |
| Giá trị status | Có | Bind VARCHAR2 |
| Tên bảng | Không | Allowlist + identifier validation/quoting |
| Tên schema | Không | Allowlist schema + validate/quote |
| Tên cột ORDER BY | Không | Map lựa chọn sang identifier cố định |
| ASC/DESC | Không | Chọn từ hai literal cố định |
| Tên hàm/toán tử | Không | Chỉ dùng cấu trúc do chương trình định nghĩa |
| Một fragment WHERE tùy ý | Không an toàn | Thiết kế filter có cấu trúc và bind từng value |

### 5.2 ORDER BY động

Không nối trực tiếp giá trị p_sort_column:

~~~sql
-- Không an toàn
l_sql := 'SELECT ... FROM orders ORDER BY ' || p_sort_column;
~~~

Thay vào đó, map input sang một tập lựa chọn cố định:

~~~sql
DECLARE
    l_sort_column VARCHAR2(30);
    l_direction  VARCHAR2(4);
    l_sql         VARCHAR2(2000);
BEGIN
    CASE UPPER(p_sort_key)
        WHEN 'DATE' THEN
            l_sort_column := 'ORDER_DATE';
        WHEN 'AMOUNT' THEN
            l_sort_column := 'TOTAL_AMOUNT';
        WHEN 'STATUS' THEN
            l_sort_column := 'STATUS';
        ELSE
            RAISE_APPLICATION_ERROR(-20001, 'Unsupported sort key');
    END CASE;

    CASE UPPER(p_sort_direction)
        WHEN 'ASC' THEN
            l_direction := 'ASC';
        WHEN 'DESC' THEN
            l_direction := 'DESC';
        ELSE
            RAISE_APPLICATION_ERROR(-20002, 'Unsupported sort direction');
    END CASE;

    l_sql :=
        'SELECT order_id, order_date, total_amount, status
           FROM orders
          WHERE customer_id = :customer_id
          ORDER BY ' || l_sort_column || ' ' || l_direction;

    OPEN p_result FOR l_sql USING p_customer_id;
END;
/
~~~

Chỉ các identifier và keyword do chương trình chọn mới được đưa vào SQL text. Giá trị customer ID vẫn được bind.

### 5.3 Tên cột trong projection động

Nếu người dùng được chọn cột hiển thị, dùng allowlist:

~~~sql
CASE UPPER(p_field_key)
    WHEN 'ORDER_ID' THEN l_column := 'ORDER_ID';
    WHEN 'ORDER_DATE' THEN l_column := 'ORDER_DATE';
    WHEN 'STATUS' THEN l_column := 'STATUS';
    ELSE
        RAISE_APPLICATION_ERROR(-20003, 'Unsupported field');
END CASE;
~~~

Không nhận một chuỗi bất kỳ làm danh sách SELECT columns. Một lựa chọn giao diện như ORDER_DATE phải được ánh xạ sang identifier hằng số do ứng dụng kiểm soát.

## 6. Allowlist: kiểm soát tên đối tượng động

Allowlist là danh sách những đối tượng hoặc cấu trúc được phép sử dụng. Với dynamic object name, đây là lớp kiểm soát nghiệp vụ quan trọng nhất.

Ví dụ ứng dụng chỉ cho phép đọc hai bảng:

| Mã lựa chọn từ ứng dụng | Schema | Table |
|---|---|---|
| ORDERS | APP | ORDERS |
| ARCHIVE | APP | ORDERS_ARCHIVE |

Người dùng gửi key ORDERS hoặc ARCHIVE. Ứng dụng tra key trong danh sách cố định và lấy schema/table tương ứng. Không dùng chuỗi người dùng gửi làm tên object trực tiếp.

### 6.1 Allowlist bằng CASE

~~~sql
DECLARE
    l_owner VARCHAR2(128);
    l_table VARCHAR2(128);
BEGIN
    CASE UPPER(p_source_key)
        WHEN 'ORDERS' THEN
            l_owner := 'APP';
            l_table := 'ORDERS';
        WHEN 'ARCHIVE' THEN
            l_owner := 'APP';
            l_table := 'ORDERS_ARCHIVE';
        ELSE
            RAISE_APPLICATION_ERROR(-20010, 'Source is not allowed');
    END CASE;
END;
/
~~~

Danh sách được kiểm soát trong code hoặc trong bảng cấu hình chỉ DBA/owner có quyền quản lý. Nếu dùng bảng allowlist, không cho user thông thường tự thêm object tùy ý.

### 6.2 Allowlist không giống denylist

Denylist cố gắng loại bỏ những chuỗi nguy hiểm như dấu chấm phẩy, dấu nháy hoặc từ khóa. Cách này dễ bỏ sót cú pháp hợp lệ khác và không hiểu ngữ cảnh SQL.

Allowlist chỉ chấp nhận các lựa chọn cụ thể. Với tên object, đây là phương pháp dễ kiểm soát và dễ audit hơn.

### 6.3 Phân quyền theo đối tượng

Ngay cả khi object name nằm trong allowlist, schema chạy SQL vẫn phải có đúng quyền cần thiết. Allowlist kiểm soát lựa chọn của ứng dụng; privilege kiểm soát database account có thể làm gì. Cần cả hai.

## 7. DBMS_ASSERT: xác thực và quote tên SQL

DBMS_ASSERT là package Oracle cung cấp các hàm kiểm tra input dùng trong dynamic SQL. Các hàm này giúp xác nhận một chuỗi phù hợp với một loại SQL name hoặc quote identifier/literal theo quy tắc Oracle.

DBMS_ASSERT là lớp phòng vệ hữu ích, nhưng không thay thế allowlist:

- Một tên object hợp lệ về cú pháp vẫn có thể là object mà ứng dụng không được phép truy cập.
- Một schema hoặc object tồn tại không có nghĩa caller nên được phép chọn nó.
- DBMS_ASSERT không thay thế privilege checks của Oracle.
- Với giá trị dữ liệu, bind variable vẫn là lựa chọn đúng; không cần DBMS_ASSERT để thay cho bind.

### 7.1 Các hàm thường dùng

| Hàm | Mục đích |
|---|---|
| ENQUOTE_NAME | Kiểm tra simple SQL name và đặt tên trong double quotes |
| SIMPLE_SQL_NAME | Kiểm tra một simple SQL name |
| QUALIFIED_SQL_NAME | Kiểm tra một qualified SQL name theo grammar Oracle |
| SCHEMA_NAME | Kiểm tra tên schema tồn tại |
| SQL_OBJECT_NAME | Kiểm tra tên SQL object tồn tại |
| ENQUOTE_LITERAL | Quote một SQL string literal; chỉ dùng khi thật sự cần tạo literal, bind vẫn được ưu tiên |
| NOOP | Trả nguyên input; không xác thực và không làm sạch input |

### 7.2 ENQUOTE_NAME

ENQUOTE_NAME kiểm tra tên đầu vào là một simple SQL name rồi trả về identifier được bao bằng dấu nháy kép:

~~~sql
SELECT DBMS_ASSERT.ENQUOTE_NAME('ORDERS')
FROM dual;
~~~

Kết quả là identifier được quote, thường có dạng "ORDERS".

Tham số capitalize mặc định là TRUE. Với identifier không quote thông thường, Oracle chuyển tên về uppercase. Nếu cần giữ chữ hoa/thường của một quoted identifier đã được allowlist, dùng capitalize => FALSE và lưu chính xác tên đã tạo:

~~~sql
SELECT DBMS_ASSERT.ENQUOTE_NAME('MixedCaseTable', FALSE)
FROM dual;
~~~

Identifier được quote phải khớp chính xác với cách tạo object. Không tự động uppercase tên quoted object.

### 7.3 SIMPLE_SQL_NAME

SIMPLE_SQL_NAME kiểm tra input là một simple SQL name hợp lệ. Hàm này không kiểm tra object có tồn tại hay caller có quyền truy cập hay không.

~~~sql
DECLARE
    l_column_name VARCHAR2(128);
BEGIN
    l_column_name := DBMS_ASSERT.SIMPLE_SQL_NAME(p_column_name);
END;
/
~~~

Chỉ gọi hàm này không làm cho một cột tùy ý trở thành lựa chọn nghiệp vụ được phép. Sau validation cú pháp vẫn phải kiểm tra cột thuộc allowlist.

### 7.4 QUALIFIED_SQL_NAME

QUALIFIED_SQL_NAME kiểm tra một qualified SQL name theo grammar Oracle. Nó phù hợp để kiểm tra cú pháp tên được phân cấp, nhưng không nên nhận một chuỗi tùy ý từ client rồi nối trực tiếp vào câu lệnh chỉ vì hàm validation trả về thành công.

Nếu ứng dụng chỉ cho phép một schema và vài table cụ thể, allowlist owner/table riêng vẫn rõ ràng hơn.

### 7.5 SCHEMA_NAME và SQL_OBJECT_NAME

SCHEMA_NAME kiểm tra tên schema tồn tại. SQL_OBJECT_NAME kiểm tra tên SQL object tồn tại. Chúng hữu ích sau khi ứng dụng đã xác định lựa chọn được phép:

~~~sql
DECLARE
    l_owner VARCHAR2(128);
    l_table VARCHAR2(128);
BEGIN
    l_owner := DBMS_ASSERT.SCHEMA_NAME('APP');
    l_table := DBMS_ASSERT.SIMPLE_SQL_NAME('ORDERS');
END;
/
~~~

Đây chỉ là kiểm tra tên. Để quyết định caller được chọn object nào, vẫn cần allowlist. Quyền SELECT/INSERT/UPDATE/DELETE thực tế được database kiểm tra khi dynamic SQL chạy.

### 7.6 Ví dụ ghép identifier động an toàn

~~~sql
DECLARE
    l_owner VARCHAR2(128);
    l_table VARCHAR2(128);
    l_sql   VARCHAR2(4000);
    l_count NUMBER;
BEGIN
    -- Allowlist: input chỉ chọn key, không cung cấp tên object trực tiếp.
    CASE UPPER(p_source_key)
        WHEN 'ORDERS' THEN
            l_owner := 'APP';
            l_table := 'ORDERS';
        WHEN 'ARCHIVE' THEN
            l_owner := 'APP';
            l_table := 'ORDERS_ARCHIVE';
        ELSE
            RAISE_APPLICATION_ERROR(-20020, 'Source is not allowed');
    END CASE;

    -- Kiểm tra tên schema và table đã được chọn từ allowlist.
    l_owner := DBMS_ASSERT.SCHEMA_NAME(l_owner);
    l_table := DBMS_ASSERT.SIMPLE_SQL_NAME(l_table);

    l_sql :=
        'SELECT COUNT(*) FROM '
        || DBMS_ASSERT.ENQUOTE_NAME(l_owner)
        || '.'
        || DBMS_ASSERT.ENQUOTE_NAME(l_table)
        || ' WHERE status = :status';

    EXECUTE IMMEDIATE l_sql
        INTO l_count
        USING p_status;
END;
/
~~~

Ở đây chỉ owner/table đã được chọn từ allowlist mới đi vào SQL text. Status là dữ liệu nên được bind.

### 7.7 ENQUOTE_LITERAL không thay thế bind

DBMS_ASSERT.ENQUOTE_LITERAL có thể quote một chuỗi thành SQL literal hợp lệ. Tuy nhiên, nếu giá trị có thể bind được, hãy bind:

~~~sql
-- Ưu tiên
EXECUTE IMMEDIATE
    'SELECT user_id FROM app_users WHERE username = :username'
INTO l_user_id
USING p_username;
~~~

Quote literal thủ công tạo thêm trách nhiệm xử lý encoding, kiểu dữ liệu, kích thước và cú pháp. Bind variable vừa an toàn hơn vừa thường có lợi cho cursor sharing.

## 8. NLS injection: nguy cơ khi nối DATE và NUMBER

SQL injection không chỉ đến từ chuỗi người dùng có dấu nháy. Trong Oracle, việc chuyển đổi ngầm DATE, TIMESTAMP hoặc NUMBER thành VARCHAR2 khi nối chuỗi có thể phụ thuộc NLS session settings. Kẻ tấn công có thể tác động một số NLS settings trong session để làm thay đổi SQL text được tạo.

### 8.1 Ví dụ DATE bị chuyển thành chuỗi ngầm

Code không an toàn:

~~~sql
l_sql :=
    'SELECT * FROM orders WHERE order_date = '''
    || p_order_date
    || '''';
~~~

P_ORDER_DATE là DATE, nhưng khi nối với VARCHAR2 Oracle phải chuyển DATE thành chuỗi. Format có thể phụ thuộc NLS_DATE_FORMAT. Nếu session có NLS_DATE_FORMAT bị thay đổi thành format chứa nội dung SQL, phần text sinh ra có thể làm thay đổi câu lệnh.

### 8.2 Cách an toàn: bind DATE

~~~sql
l_sql :=
    'SELECT * FROM orders WHERE order_date = :order_date';

OPEN p_result FOR l_sql USING p_order_date;
~~~

Giá trị vẫn là DATE khi truyền vào SQL; không cần chuyển thành chuỗi.

### 8.3 NUMBER và NLS_NUMERIC_CHARACTERS

Việc nối NUMBER thành SQL text có thể phụ thuộc NLS_NUMERIC_CHARACTERS, ảnh hưởng cách biểu diễn dấu thập phân và dấu phân nhóm. Không nối số vào SQL:

~~~sql
-- Không an toàn và phụ thuộc chuyển đổi
l_sql := 'SELECT * FROM invoices WHERE amount > ' || p_amount;
~~~

Dùng bind:

~~~sql
l_sql := 'SELECT * FROM invoices WHERE amount > :amount';
OPEN p_result FOR l_sql USING p_amount;
~~~

### 8.4 Nếu bắt buộc phải tạo literal

Một số ngữ cảnh DDL hoặc cấu trúc không hỗ trợ bind có thể cần sinh literal. Hãy ưu tiên dùng API Oracle hỗ trợ bind/metadata nếu có; nếu không, phải chuyển đổi tường minh với format model cố định, kiểm soát NLS và quote đúng kiểu. Không dùng implicit conversion.

Tuy nhiên, đừng lấy cách format literal làm giải pháp chung cho DML/SELECT. Hãy bind các giá trị có thể bind được.

## 9. Second-order SQL injection

Second-order injection xảy ra khi dữ liệu đầu vào ban đầu được lưu trong bảng như dữ liệu bình thường, nhưng một chức năng khác sau đó đọc giá trị đó và nối nó vào SQL text. Điểm injection xuất hiện ở lần sử dụng sau, không nhất thiết ở lần ghi đầu tiên.

Ví dụ:

1. Ứng dụng lưu một chuỗi cấu hình vào bảng REPORT_CONFIG.
2. Một procedure chạy báo cáo đọc chuỗi đó.
3. Procedure nối chuỗi vào WHERE clause hoặc ORDER BY.
4. Nội dung đã lưu làm thay đổi SQL khi report chạy.

Dữ liệu đến từ database không mặc nhiên đáng tin cậy. Nó có thể được nhập bởi người dùng, tích hợp bên ngoài, batch hoặc một ứng dụng có lỗ hổng khác.

### 9.1 Ví dụ không an toàn

~~~sql
SELECT filter_expression
INTO l_filter
FROM report_config
WHERE report_id = p_report_id;

l_sql := 'SELECT * FROM orders WHERE ' || l_filter;
OPEN l_result FOR l_sql;
~~~

Nếu người dùng có thể thay đổi FILTER_EXPRESSION, đây là SQL fragment không đáng tin cậy dù giá trị được đọc từ một bảng nội bộ.

### 9.2 Thiết kế an toàn hơn

Thay vì lưu một đoạn SQL tùy ý, lưu các tham số có cấu trúc:

| Cột cấu hình | Ví dụ |
|---|---|
| FILTER_STATUS | SHIPPED |
| MIN_AMOUNT | 1000 |
| CREATED_FROM | 2026-01-01 |
| SORT_KEY | ORDER_DATE |
| SORT_DIRECTION | DESC |

Khi chạy report:

- Validate SORT_KEY qua allowlist.
- Validate SORT_DIRECTION qua ASC/DESC.
- Bind FILTER_STATUS, MIN_AMOUNT và CREATED_FROM.
- Tạo SQL text từ template cố định.

Không lưu SQL fragment do người dùng tự soạn rồi thực thi trực tiếp.

## 10. Dynamic IN list

Một lỗi phổ biến là nối các giá trị vào danh sách IN:

~~~sql
-- Không an toàn
l_sql := 'SELECT * FROM orders WHERE order_id IN (' || p_id_list || ')';
~~~

Không nên biến chuỗi "10,20,30" thành một phần SQL text. Có hai cách an toàn phổ biến.

### 10.1 Sinh placeholder, bind từng giá trị

Nếu số phần tử được giới hạn và biết trước, tạo chuỗi placeholder:

~~~sql
SELECT *
FROM orders
WHERE order_id IN (:id1, :id2, :id3)
~~~

Sau đó bind từng ID bằng USING hoặc DBMS_SQL. Phần được sinh động chỉ là số lượng dấu placeholder do chương trình kiểm soát; giá trị thực tế vẫn được bind.

Với số lượng placeholder thay đổi và không biết trước, DBMS_SQL có thể phù hợp hơn Native Dynamic SQL vì có thể bind theo vòng lặp.

### 10.2 Dùng SQL collection

Nếu có SQL collection type phù hợp, có thể truyền cả collection làm một bind:

~~~sql
DECLARE
    l_ids SYS.ODCINUMBERLIST :=
        SYS.ODCINUMBERLIST(10, 20, 30);
    l_cursor SYS_REFCURSOR;
BEGIN
    OPEN l_cursor FOR
        'SELECT order_id, status
           FROM orders
          WHERE order_id IN (
              SELECT column_value
              FROM TABLE(:ids)
          )'
        USING l_ids;
END;
/
~~~

Giá trị của collection được bind. Kiểm tra kiểu collection, khả năng bind và cú pháp SQL type trong release đang chạy; với collection tự định nghĩa, SQL type cần được khai báo ở phạm vi schema để SQL engine sử dụng.

## 11. LIKE và bind variable

Bind variable ngăn input thay đổi SQL syntax, nhưng không loại bỏ semantics wildcard của LIKE.

Ví dụ:

~~~sql
SELECT customer_id, last_name
FROM customers
WHERE last_name LIKE :pattern;
~~~

Nếu pattern là "SMI%", đây là prefix search. Nếu pattern là "%SMI%", đây là contains search. Dấu % và _ trong input vẫn có ý nghĩa wildcard dù đã bind.

Nếu nghiệp vụ muốn tìm chuỗi literal do người dùng nhập, phải escape wildcard:

~~~sql
SELECT customer_id, last_name
FROM customers
WHERE last_name LIKE :pattern ESCAPE '\';
~~~

Ứng dụng cần thay ký tự escape, % và _ trong dữ liệu người dùng bằng dạng escaped trước khi thêm wildcard do chương trình chủ động. Ví dụ về logic:

~~~text
input:       A_10% 
escaped:     A\_10\%
prefix:      A\_10\%%
~~~

Bind vẫn là lớp bảo vệ SQL injection. Escape wildcard chỉ kiểm soát ý nghĩa tìm kiếm, không phải thay thế bind.

## 12. Native Dynamic SQL và DBMS_SQL

Oracle có hai cơ chế chính để chạy dynamic SQL từ PL/SQL.

### 12.1 Native Dynamic SQL

Dùng EXECUTE IMMEDIATE hoặc OPEN FOR. Phù hợp khi số lượng và kiểu bind/column đã biết lúc compile:

~~~sql
EXECUTE IMMEDIATE
    'UPDATE orders SET status = :status WHERE order_id = :id'
USING p_status, p_order_id;
~~~

Ưu điểm:

- Cú pháp ngắn, dễ đọc.
- Tích hợp trực tiếp với biến PL/SQL.
- Hỗ trợ SELECT INTO, RETURNING INTO, OPEN FOR và bulk operations.
- Phù hợp với phần lớn dynamic SQL trong ứng dụng.

### 12.2 DBMS_SQL

DBMS_SQL phù hợp khi cấu trúc SQL chỉ biết lúc runtime, ví dụ:

- Số lượng bind variables không biết trước.
- Số lượng cột trong SELECT list không biết trước.
- Cần DESCRIBE columns và xử lý kết quả tổng quát.
- Cần thao tác cursor theo API parse/bind/define/execute/fetch.

Quy trình khái quát:

1. OPEN_CURSOR.
2. PARSE SQL text.
3. BIND_VARIABLE cho từng bind.
4. DEFINE_COLUMN nếu cần fetch result set.
5. EXECUTE.
6. FETCH_ROWS và COLUMN_VALUE.
7. CLOSE_CURSOR trong mọi nhánh xử lý.

### 12.3 Ví dụ DBMS_SQL bind giá trị

~~~sql
DECLARE
    l_cursor INTEGER;
    l_rows   INTEGER;
    l_sql    VARCHAR2(1000);
BEGIN
    l_sql :=
        'UPDATE orders
            SET status = :status
          WHERE customer_id = :customer_id';

    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        l_sql,
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':status',
        p_status
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':customer_id',
        p_customer_id
    );

    l_rows := DBMS_SQL.EXECUTE(l_cursor);
    DBMS_SQL.CLOSE_CURSOR(l_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_SQL.IS_OPEN(l_cursor) THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        RAISE;
END;
/
~~~

Bind variable vẫn là dữ liệu tách khỏi SQL text. DBMS_SQL không làm dynamic SQL tự an toàn; nếu nối input vào l_sql trước khi PARSE, vẫn có SQL injection.

### 12.4 Chuyển đổi giữa DBMS_SQL và REF CURSOR

Oracle cung cấp TO_REFCURSOR và TO_CURSOR_NUMBER để chuyển giữa cursor DBMS_SQL và REF CURSOR trong những trường hợp phù hợp. Điều này hữu ích khi cần parse/describe động nhưng muốn trả kết quả qua interface REF CURSOR.

## 13. Dynamic PL/SQL block nguy hiểm hơn dynamic SQL statement

Nếu chỉ cần chạy SELECT/INSERT/UPDATE/DELETE, hãy tạo đúng loại SQL statement. Không bọc nó vào anonymous PL/SQL block nếu không cần thiết.

Ví dụ không an toàn:

~~~sql
l_block :=
    'BEGIN process_order(''' || p_order_id || '''); END;';

EXECUTE IMMEDIATE l_block;
~~~

Chuỗi input được chèn vào PL/SQL source. Nếu input làm thay đổi block, người dùng có thể thêm lời gọi hoặc statement khác trong phạm vi quyền thực thi.

Ví dụ an toàn:

~~~sql
EXECUTE IMMEDIATE
    'BEGIN process_order(:order_id); END;'
USING p_order_id;
~~~

Placeholder bind được truyền vào procedure như argument. Không nối giá trị vào source block.

Nếu procedure có thể gọi tĩnh:

~~~sql
BEGIN
    process_order(p_order_id);
END;
/
~~~

thì gọi trực tiếp còn đơn giản hơn và không cần dynamic PL/SQL.

## 14. Kiểm soát quyền khi thực thi dynamic SQL

Một lỗ hổng SQL injection có thể nghiêm trọng hơn nhiều nếu code chạy với quyền rộng.

### 14.1 Definer rights và invoker rights

Stored procedure/function trong PL/SQL mặc định chạy theo quyền của owner (definer rights), trừ khi khai báo AUTHID CURRENT_USER.

| Chế độ | Ý nghĩa khái quát |
|---|---|
| AUTHID DEFINER | Unit chạy với quyền của schema sở hữu unit |
| AUTHID CURRENT_USER | Unit chạy theo quyền của invoker và current schema/context của invoker theo quy tắc Oracle |

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE app_read_orders (
    p_customer_id IN NUMBER
)
AUTHID DEFINER
AS
BEGIN
    -- SQL trong unit chạy theo definer-rights model.
    NULL;
END;
/
~~~

AUTHID DEFINER là mặc định nếu không chỉ định AUTHID. Một procedure definer-rights có thể truy cập object bằng quyền của owner; nếu nó ghép SQL text từ input không tin cậy, lỗ hổng có thể cho phép caller khai thác quyền của owner.

### 14.2 Least privilege

Schema owner của stored procedure chỉ nên có quyền cần thiết:

- Chỉ cấp SELECT trên các bảng cần đọc.
- Chỉ cấp INSERT/UPDATE/DELETE trên các bảng nghiệp vụ cần ghi.
- Không cấp DBA, CREATE ANY TABLE hoặc quyền hệ thống rộng nếu không cần.
- Không cho procedure động truy cập object tùy ý ngoài allowlist.
- Tách schema owner code khỏi schema chứa dữ liệu nếu mô hình triển khai yêu cầu.

Không dùng dynamic SQL để vượt qua kiểm soát quyền của ứng dụng.

### 14.3 AUTHID CURRENT_USER không thay thế bind

Invoker rights có thể giúp unit dùng quyền của caller, nhưng không ngăn SQL injection. Nếu SQL text được ghép từ input không tin cậy, attacker vẫn có thể thay đổi câu lệnh trong phạm vi quyền của invoker.

Ngược lại, definer rights không tự động là lỗi. Nó phù hợp cho API được thiết kế để cung cấp một tập thao tác giới hạn. Điều quan trọng là bind values, allowlist identifiers, privilege tối thiểu và interface được kiểm soát.

### 14.4 Quyền trực tiếp và role

Stored PL/SQL definer-rights thường thực thi với role bị vô hiệu hóa, nên quyền trên object cần được cấp trực tiếp cho owner theo yêu cầu của Oracle. Khi thiết kế package, hãy kiểm tra quyền compile và runtime riêng biệt; đừng cấp role rộng chỉ để làm cho dynamic SQL chạy.

## 15. Các biện pháp không đủ để chống SQL injection

### 15.1 Chỉ xóa dấu nháy

Không đủ. SQL có nhiều cú pháp, comment, toán tử, encoding và ngữ cảnh. Blacklist ký tự dễ bị bypass và có thể làm hỏng dữ liệu hợp lệ.

### 15.2 Tự thay dấu nháy đơn

Ví dụ:

~~~sql
REPLACE(p_input, '''', '''''')
~~~

Đây không phải giải pháp chung. Cách quote có thể phụ thuộc vào ngữ cảnh SQL, kiểu dữ liệu và encoding. Với giá trị, hãy bind.

### 15.3 Chỉ dùng DBMS_ASSERT

DBMS_ASSERT kiểm tra một số dạng SQL name/literal, không quyết định đối tượng đó có được phép truy cập theo nghiệp vụ không. Một tên hợp lệ và tồn tại vẫn có thể là tên object mà user không được chọn.

### 15.4 Chỉ dùng quyền thấp

Least privilege giảm tác động nhưng không sửa lỗi injection. Attacker vẫn có thể đọc/sửa/xóa những dữ liệu mà account bị khai thác có quyền.

### 15.5 Dùng một bind cho identifier

Bind không thể thay thế table/column name. Phải chọn identifier từ allowlist, validate/quote và ghép vào SQL text.

## 16. Quy trình xây dựng dynamic SQL an toàn

Một quy trình có thể áp dụng cho procedure cần chọn bảng, cột hoặc sort order động:

~~~text
Nhận input từ ứng dụng
        |
        v
Phân loại input
        |
        +-----------------------+
        |                       |
        v                       v
Giá trị dữ liệu            Identifier/SQL structure
        |                       |
        v                       v
Bind variable              Allowlist mapping
                                |
                                v
                         DBMS_ASSERT validation
                         và quote identifier
                                |
                                v
                         Ghép vào SQL template
        |                       |
        +-----------+-----------+
                    |
                    v
            Execute dynamic SQL
                    |
                    v
        Oracle kiểm tra privilege
                    |
                    v
          Ghi log/audit phù hợp
~~~

Các bước thực hành:

1. Ưu tiên SQL tĩnh nếu cấu trúc truy vấn đã biết.
2. Tách mọi input thành value, identifier hoặc SQL syntax.
3. Bind tất cả giá trị có thể bind.
4. Với identifier, map một key nghiệp vụ sang object/cột cố định.
5. Dùng DBMS_ASSERT để validate/quote tên sau khi allowlist đã quyết định.
6. Chỉ sinh SQL từ template và fragment do chương trình kiểm soát.
7. Giữ quyền của schema ở mức tối thiểu.
8. Ghi log SQL_ID, module/action và lựa chọn nghiệp vụ cần thiết, không ghi bí mật hoặc bind nhạy cảm vào log.
9. Kiểm thử input có dấu nháy, comment, dấu phân cách, Unicode, wildcard và giá trị NLS bất thường.

## 17. Ví dụ hoàn chỉnh: API báo cáo với table và sort động

Ví dụ này cho phép ứng dụng chọn nguồn ORDERS hoặc ARCHIVE, chọn một trong ba sort keys và truyền status/customer ID.

~~~sql
CREATE OR REPLACE PROCEDURE open_order_report (
    p_source_key     IN VARCHAR2,
    p_sort_key       IN VARCHAR2,
    p_sort_direction IN VARCHAR2,
    p_customer_id    IN NUMBER,
    p_status         IN VARCHAR2,
    p_result         OUT SYS_REFCURSOR
)
AUTHID DEFINER
AS
    l_owner       VARCHAR2(128);
    l_table       VARCHAR2(128);
    l_sort_column VARCHAR2(128);
    l_direction   VARCHAR2(4);
    l_sql         VARCHAR2(4000);
BEGIN
    -- Chọn object từ allowlist.
    CASE UPPER(p_source_key)
        WHEN 'ORDERS' THEN
            l_owner := 'APP';
            l_table := 'ORDERS';
        WHEN 'ARCHIVE' THEN
            l_owner := 'APP';
            l_table := 'ORDERS_ARCHIVE';
        ELSE
            RAISE_APPLICATION_ERROR(-20031, 'Invalid report source');
    END CASE;

    -- Chọn sort column từ allowlist.
    CASE UPPER(p_sort_key)
        WHEN 'DATE' THEN
            l_sort_column := 'ORDER_DATE';
        WHEN 'AMOUNT' THEN
            l_sort_column := 'TOTAL_AMOUNT';
        WHEN 'STATUS' THEN
            l_sort_column := 'STATUS';
        ELSE
            RAISE_APPLICATION_ERROR(-20032, 'Invalid sort key');
    END CASE;

    -- Chỉ cho phép hai hướng sắp xếp.
    CASE UPPER(p_sort_direction)
        WHEN 'ASC' THEN
            l_direction := 'ASC';
        WHEN 'DESC' THEN
            l_direction := 'DESC';
        ELSE
            RAISE_APPLICATION_ERROR(-20033, 'Invalid sort direction');
    END CASE;

    -- Validate và quote các identifier đã được allowlist chọn.
    l_owner := DBMS_ASSERT.SCHEMA_NAME(l_owner);
    l_table := DBMS_ASSERT.SIMPLE_SQL_NAME(l_table);
    l_sort_column := DBMS_ASSERT.SIMPLE_SQL_NAME(l_sort_column);

    l_sql :=
        'SELECT order_id, customer_id, order_date, total_amount, status '
        || 'FROM '
        || DBMS_ASSERT.ENQUOTE_NAME(l_owner)
        || '.'
        || DBMS_ASSERT.ENQUOTE_NAME(l_table)
        || ' WHERE customer_id = :customer_id'
        || ' AND status = :status'
        || ' ORDER BY '
        || DBMS_ASSERT.ENQUOTE_NAME(l_sort_column)
        || ' '
        || l_direction;

    OPEN p_result FOR l_sql
        USING p_customer_id, p_status;
END;
/
~~~

Các thành phần an toàn trong ví dụ:

- p_source_key không được ghép trực tiếp; nó chỉ chọn một cặp owner/table trong allowlist.
- p_sort_key chỉ chọn một column name đã định nghĩa trước.
- p_sort_direction chỉ có ASC hoặc DESC.
- Owner, table và column được xác thực/quote trước khi đưa vào SQL text.
- Customer ID và status là giá trị dữ liệu nên được bind.
- Stored procedure chỉ có thể thực thi object mà definer có quyền và code cho phép chọn.

Trong hệ thống thực tế, cần bảo đảm hai bảng có cùng cấu trúc cột được SELECT. Nếu object có quoted identifier phân biệt hoa/thường, lưu chính xác tên và dùng chế độ quote phù hợp. Cũng cần quyết định rõ caller có được xem cả dữ liệu archive hay không; allowlist kỹ thuật không thay thế authorization nghiệp vụ.

## 18. Kiểm thử SQL injection và kiểm soát động

Kiểm thử nên chứng minh dữ liệu đầu vào không thể thay đổi SQL syntax, và identifier ngoài allowlist bị từ chối.

### 18.1 Test input có dấu nháy

Với truy vấn:

~~~sql
WHERE username = :username
~~~

thử username chứa dấu nháy đơn, dấu gạch ngang kép, dấu chấm phẩy và chuỗi trông giống điều kiện SQL. Giá trị phải được so sánh như dữ liệu; nó không được thay đổi số hàng hoặc cấu trúc câu lệnh ngoài semantics so sánh.

### 18.2 Test NLS settings

Trong môi trường lab, thử thay đổi NLS_DATE_FORMAT và NLS_NUMERIC_CHARACTERS của session rồi gọi procedure:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
~~~

Procedure dùng bind DATE/NUMBER phải tiếp tục hoạt động với đúng giá trị. SQL text không được phụ thuộc vào cách chuyển DATE/NUMBER thành chuỗi.

### 18.3 Test identifier ngoài allowlist

Gửi các key không hợp lệ như:

- Tên schema không được cho phép.
- Tên table khác danh sách.
- Tên có dấu chấm, dấu nháy hoặc ký tự không thuộc identifier grammar.
- Sort key không được hỗ trợ.
- Direction khác ASC/DESC.

API phải từ chối bằng lỗi nghiệp vụ rõ ràng trước khi chạy SQL.

### 18.4 Test second-order injection

Nếu hệ thống lưu report configuration, kiểm tra mọi đường ghi và mọi nơi đọc lại cấu hình. Không chỉ test input ở màn hình đầu tiên; kiểm tra dữ liệu đã lưu được dùng trong dynamic SQL ở batch, scheduler hoặc report worker.

## 19. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nối input vào WHERE | Dữ liệu trở thành SQL syntax | Bind variable |
| Bind table/column name | Bind chỉ thay giá trị expression | Allowlist identifier và quote |
| Chỉ xóa dấu nháy hoặc comment | Blacklist không bao phủ grammar SQL | Tách data khỏi code bằng bind |
| Dùng DBMS_ASSERT như allowlist | Tên hợp lệ vẫn có thể không được phép | Allowlist trước, DBMS_ASSERT sau |
| Nối DATE/NUMBER vào SQL | Implicit conversion phụ thuộc NLS | Bind đúng kiểu |
| Lưu SQL fragment trong bảng cấu hình | Second-order injection khi fragment được chạy | Lưu cấu hình có cấu trúc, không lưu SQL tùy ý |
| Nối ORDER BY từ input | Column/direction thay đổi cấu trúc | Map sort key/direction sang hằng số |
| Nối IN-list từ chuỗi | Giá trị trong list có thể thay đổi cú pháp | Bind từng giá trị hoặc bind collection |
| Dùng dynamic PL/SQL block không cần thiết | Tạo bề mặt injection lớn hơn | Dùng SQL statement hoặc gọi procedure tĩnh |
| Dùng definer-rights quá rộng | Injection khai thác quyền owner | Least privilege, allowlist và bind |
| Cho rằng invoker-rights tự chống injection | Dynamic SQL vẫn có thể bị thay đổi | Vẫn bind, validate và phân quyền |
| Không xử lý cursor trong DBMS_SQL | Rò rỉ cursor khi exception | Đóng cursor trong exception handler |
| Không escape wildcard của LIKE | Input có thể thay đổi semantics tìm kiếm | Dùng bind và escape %/_ nếu cần literal search |

## 20. Checklist bảo mật cho dynamic SQL

Trước khi đưa dynamic SQL vào production, hãy xác nhận:

1. Có thể thay dynamic SQL bằng SQL tĩnh không?
2. Mọi giá trị dữ liệu đã được bind chưa?
3. Có DATE/NUMBER nào bị nối vào SQL text qua implicit conversion không?
4. Tên schema/table/column có được map từ allowlist không?
5. Sort direction và operator có được chọn từ tập literal cố định không?
6. DBMS_ASSERT có được dùng đúng mục đích sau allowlist không?
7. Có hiểu rõ identifier được quote và case-sensitive không?
8. Không có SQL fragment không tin cậy được đọc từ bảng rồi thực thi?
9. Dynamic PL/SQL block có thật sự cần thiết không?
10. IN-list động có bind từng value hoặc collection không?
11. LIKE có cần escape wildcard để giữ semantics literal không?
12. Stored procedure chạy AUTHID DEFINER hay CURRENT_USER, và lý do là gì?
13. Schema owner có đúng quyền tối thiểu không?
14. Các object trong allowlist có được caller phép truy cập theo nghiệp vụ không?
15. Exception có được xử lý mà không làm lộ SQL text hoặc dữ liệu nhạy cảm không?
16. DBMS_SQL cursor có được đóng trong mọi nhánh không?
17. Đã test NLS_DATE_FORMAT và NLS_NUMERIC_CHARACTERS chưa?
18. Đã test dấu nháy, comment, dấu phân cách, Unicode và input bất thường chưa?
19. Đã kiểm tra second-order injection trong job/report/configuration chưa?
20. Log có ghi đủ SQL_ID/module/action để điều tra mà không ghi bí mật hoặc bind nhạy cảm không?

## 21. Tổng kết

SQL injection xảy ra khi dữ liệu đầu vào được diễn giải thành một phần của SQL/PLSQL code. Cách bảo vệ quan trọng nhất là giữ SQL text cố định và truyền giá trị bằng bind variables.

- SQL tĩnh nên được ưu tiên khi cấu trúc truy vấn đã biết.
- Native Dynamic SQL dùng EXECUTE IMMEDIATE hoặc OPEN FOR với USING để bind giá trị.
- DBMS_SQL phù hợp khi số lượng bind hoặc cột kết quả chỉ biết lúc runtime; nó vẫn cần bind và kiểm soát SQL text.
- Bind variables không thể thay thế tên bảng, tên cột, schema, keyword hoặc SQL fragment.
- Identifier động phải được chọn từ allowlist; DBMS_ASSERT giúp kiểm tra/quote identifier nhưng không cấp quyền và không quyết định lựa chọn có được phép hay không.
- Không nối DATE/NUMBER vào SQL text vì implicit conversion có thể phụ thuộc NLS và tạo NLS injection.
- Dữ liệu đọc từ database vẫn có thể không đáng tin cậy; second-order injection xảy ra khi dữ liệu đã lưu được nối vào SQL ở một bước sau.
- AUTHID DEFINER và quyền rộng làm tăng tác động của lỗ hổng; dùng least privilege và thiết kế API có phạm vi rõ ràng.
- Bind variable vừa ngăn injection vừa hỗ trợ cursor sharing, nhưng không thay thế authorization hoặc validation nghiệp vụ.

Hãy phân loại mọi input trước khi tạo SQL: giá trị thì bind, identifier thì allowlist và validate/quote, cấu trúc SQL thì chỉ chọn từ các lựa chọn do chương trình định nghĩa. Đây là nền tảng để dynamic SQL an toàn, dễ kiểm soát và dễ bảo trì.

## 22. Tài liệu Oracle tham khảo

- Oracle Database 19c PL/SQL Language Reference, “Native Dynamic SQL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/native-dynamic-sql.html
- Oracle Database 19c PL/SQL Packages and Types Reference, “DBMS_ASSERT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html
- Oracle Database 19c PL/SQL Language Reference, “SQL Injection”: https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/sql-injection.html
- Oracle Database 19c PL/SQL Language Reference, “Invokers Rights and Definers Rights”: https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights.html
- Oracle Database 19c PL/SQL Packages and Types Reference, “DBMS_SQL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SQL.html
- Oracle Database 19c SQL Language Reference, “Placeholders”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Placeholders.html
- Oracle Database Security Guide, “SQL Injection”: https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/sql-injection.html
