# Chống SQL injection trong SQL động và sử dụng DBMS_ASSERT trong Oracle Database

SQL injection xảy ra khi dữ liệu đầu vào bị ghép vào câu SQL hoặc PL/SQL theo cách làm thay đổi cấu trúc hay ý nghĩa của lệnh. Kẻ tấn công có thể khiến ứng dụng thực thi điều kiện ngoài dự kiến, đọc dữ liệu không được phép, thay đổi dữ liệu hoặc gọi thao tác với quyền của schema đang chạy chương trình.

Trong Oracle, rủi ro thường xuất hiện khi dùng `EXECUTE IMMEDIATE`, `OPEN ... FOR` hoặc `DBMS_SQL` để tạo câu lệnh động bằng phép nối chuỗi. Cách phòng vệ quan trọng nhất là **bind variable cho mọi giá trị dữ liệu**. Khi cần tạo tên bảng, tên cột hoặc từ khóa động, hãy dùng lựa chọn cố định từ allowlist và xác thực tên bằng các hàm phù hợp của `DBMS_ASSERT`.

`DBMS_ASSERT` hỗ trợ kiểm tra và quote một số dạng tên SQL hoặc literal. Package này là lớp phòng vệ bổ sung; nó không thay thế bind variable, allowlist, kiểm tra quyền truy cập hay thiết kế least privilege.

Bài học trình bày cách SQL injection hình thành, các dạng lỗi trong dynamic SQL và dynamic PL/SQL, cách bind giá trị, xử lý identifier động, sử dụng `DBMS_ASSERT`, phòng tránh NLS và second-order injection, kiểm soát quyền trong stored procedure, cách kiểm thử và các mẫu triển khai an toàn.

## 1. SQL injection là gì?

### 1.1. Dữ liệu đầu vào làm thay đổi cấu trúc SQL

Ứng dụng thường nhận dữ liệu từ form web/mobile, REST API, file import, message queue, job chạy theo lịch, bảng staging hoặc dữ liệu do ứng dụng khác ghi trước đó.

Nếu ứng dụng nối trực tiếp dữ liệu vào SQL, đầu vào có thể biến thành một phần cú pháp SQL thay vì chỉ là giá trị cần tìm kiếm.

Ví dụ không an toàn:

```sql
DECLARE
    v_sql VARCHAR2(4000);
BEGIN
    v_sql :=
        'SELECT COUNT(*) FROM employees ' ||
        'WHERE last_name = ''' || :p_last_name || '''';

    EXECUTE IMMEDIATE v_sql;
END;
/
```

Đoạn code này tạo SQL bằng cách nối `p_last_name` vào giữa hai dấu nháy đơn. Nếu dữ liệu chứa dấu nháy hoặc biểu thức SQL, cấu trúc điều kiện có thể bị thay đổi.

Không nên cố sửa ví dụ bằng cách chỉ xóa một vài ký tự đặc biệt. SQL có nhiều kiểu literal, biểu thức, comment, chuyển đổi kiểu và ngữ cảnh cú pháp khác nhau. Quy tắc lọc ký tự thủ công rất dễ thiếu trường hợp.

### 1.2. Tác động có thể xảy ra

Tùy quyền của schema và cấu trúc ứng dụng, SQL injection có thể dẫn tới:
- Bỏ qua điều kiện xác thực hoặc lọc dữ liệu.
- Đọc hàng hoặc cột ngoài phạm vi được phép.
- Thay đổi hoặc xóa dữ liệu.
- Gọi procedure/package ngoài ý định.
- Truy cập đối tượng khác trong cùng database.
- Tạo lỗi để dò cấu trúc SQL hoặc metadata.

SQL injection không tự động vượt qua mọi quyền bảo mật của Oracle. Câu lệnh vẫn chạy với quyền của session hoặc chương trình PL/SQL thực thi nó. Tuy nhiên, nếu ứng dụng kết nối bằng schema có quyền quá rộng, tác động có thể lớn.

### 1.3. SQL injection khác lỗi nhập liệu thông thường

Đầu vào sai định dạng có thể gây lỗi chuyển đổi dữ liệu hoặc vi phạm constraint mà không phải SQL injection. SQL injection xảy ra khi dữ liệu đầu vào được diễn giải như cú pháp hoặc làm thay đổi cấu trúc câu lệnh.

Ví dụ:
- Nhập chữ vào trường NUMBER có thể gây lỗi chuyển đổi.
- Nhập dấu nháy vào chuỗi được bind vẫn chỉ là dữ liệu.
- Nối dấu nháy vào dynamic SQL mà không xử lý đúng có thể thay đổi biểu thức SQL.

Phòng vệ nên dựa trên cách xây dựng câu lệnh, không dựa trên giả định rằng người dùng chỉ gửi các ký tự bình thường.

## 2. Những vị trí dynamic SQL dễ có SQL injection

### 2.1. EXECUTE IMMEDIATE

`EXECUTE IMMEDIATE` thực thi SQL statement hoặc PL/SQL block được tạo lúc chạy. Nếu chuỗi SQL chứa dữ liệu không tin cậy qua phép nối, rủi ro injection xuất hiện.

Không an toàn:

```sql
v_sql :=
    'DELETE FROM orders WHERE customer_id = ' ||
    p_customer_id;

EXECUTE IMMEDIATE v_sql;
```

Ngay cả khi `p_customer_id` có kiểu NUMBER, việc chuyển nó thành text rồi ghép vào câu lệnh là không cần thiết. Dùng bind:

```sql
v_sql :=
    'DELETE FROM orders WHERE customer_id = :1';

EXECUTE IMMEDIATE v_sql
    USING p_customer_id;
```

### 2.2. OPEN FOR với REF CURSOR

Dynamic query dùng `OPEN ... FOR` cũng có nguy cơ nếu ghép dữ liệu.

Không an toàn:

```sql
v_sql :=
    'SELECT order_id, total_amount ' ||
    'FROM orders WHERE customer_id = ' ||
    p_customer_id;

OPEN p_result FOR v_sql;
```

An toàn hơn:

```sql
v_sql :=
    'SELECT order_id, total_amount ' ||
    'FROM orders WHERE customer_id = :customer_id';

OPEN p_result FOR v_sql
    USING p_customer_id;
```

REF CURSOR không tự làm câu SQL an toàn. Điều quyết định là cách tạo chuỗi và truyền giá trị.

### 2.3. Dynamic PL/SQL block

Không chỉ SELECT/INSERT/UPDATE/DELETE mới có rủi ro. Ghép dữ liệu vào một block PL/SQL động cũng có thể cho phép đầu vào thay đổi lệnh được thực thi.

Ví dụ nguy hiểm:

```sql
v_block :=
    'BEGIN process_order(''' ||
    p_order_code ||
    '''); END;';

EXECUTE IMMEDIATE v_block;
```

Nếu chỉ cần truyền tham số cho procedure, hãy bind:

```sql
v_block := 'BEGIN process_order(:order_code); END;';

EXECUTE IMMEDIATE v_block
    USING p_order_code;
```

Không đưa dữ liệu đầu vào vào phần thân block nếu có thể truyền nó qua tham số.

### 2.4. DBMS_SQL

`DBMS_SQL` cho phép parse, bind và execute câu lệnh động theo từng bước. Package này không tự bảo vệ ứng dụng khỏi SQL injection. Nếu chuỗi được tạo bằng cách nối dữ liệu không tin cậy, rủi ro vẫn còn.

Hãy dùng API bind của DBMS_SQL để truyền giá trị. Chỉ dùng DBMS_SQL khi cần khả năng dynamic SQL mà native dynamic SQL không đáp ứng thuận tiện, chẳng hạn xử lý số lượng cột hoặc kiểu kết quả chưa biết tại thời điểm compile.

## 3. Bind variable là biện pháp chính cho giá trị dữ liệu

### 3.1. Tách giá trị khỏi cú pháp

Bind variable là placeholder trong SQL. Giá trị được truyền riêng khi thực thi, không được nối vào chuỗi SQL.

```sql
DECLARE
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE department_id = :dept'
        INTO v_count
        USING 10;

    DBMS_OUTPUT.PUT_LINE('Count = ' || v_count);
END;
/
```

Giá trị 10 được bind vào placeholder. Nếu người dùng truyền chuỗi có dấu nháy hoặc từ khóa SQL vào bind VARCHAR2, Oracle xử lý nó như dữ liệu của predicate, không diễn giải thành cú pháp SQL.

### 3.2. Bind cho INSERT, UPDATE và DELETE

INSERT:

```sql
EXECUTE IMMEDIATE
    'INSERT INTO audit_events(event_type, actor_id) ' ||
    'VALUES (:event_type, :actor_id)'
USING p_event_type, p_actor_id;
```

UPDATE:

```sql
EXECUTE IMMEDIATE
    'UPDATE employees SET salary = :salary ' ||
    'WHERE employee_id = :employee_id'
USING p_salary, p_employee_id;
```

DELETE:

```sql
EXECUTE IMMEDIATE
    'DELETE FROM orders WHERE order_id = :order_id'
USING p_order_id;
```

Trong mỗi trường hợp, câu SQL giữ cấu trúc cố định và giá trị được truyền riêng.

### 3.3. Bind ngày, số và chuỗi

Không chuyển giá trị thành text rồi ghép vào SQL. Bind theo kiểu dữ liệu giúp tránh lỗi định dạng và NLS.

Bind DATE:

```sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM orders WHERE order_date >= :from_date'
    INTO v_count
    USING p_from_date;
```

Bind NUMBER:

```sql
EXECUTE IMMEDIATE
    'UPDATE accounts SET balance = balance - :amount ' ||
    'WHERE account_id = :account_id'
USING p_amount, p_account_id;
```

Bind chuỗi:

```sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM employees WHERE last_name = :last_name'
    INTO v_count
    USING p_last_name;
```

Không dùng TO_CHAR để biến ngày hoặc số thành một đoạn SQL literal nếu bind trực tiếp được.

### 3.4. Thứ tự bind trong native dynamic SQL

Với dynamic SQL statement, các placeholder positional được ghép với biểu thức trong USING theo thứ tự xuất hiện.

```sql
EXECUTE IMMEDIATE
    'UPDATE employees ' ||
    'SET salary = :x ' ||
    'WHERE employee_id = :y'
USING p_salary, p_employee_id;
```

Ở đây bind đầu tiên là salary, bind thứ hai là employee_id.

Với dynamic anonymous PL/SQL block hoặc CALL statement, quy tắc xử lý placeholder có khác biệt khi cùng tên placeholder xuất hiện nhiều lần. Để tránh nhầm lẫn, hãy đặt placeholder rõ ràng và đối chiếu quy tắc Native Dynamic SQL trong tài liệu Oracle của phiên bản đang dùng. Không mặc định mọi trường hợp đều có thể ghép theo tên.

### 3.5. Bind không thay thế được tên bảng hoặc tên cột

Bind chỉ thay thế giá trị biểu thức. Không thể dùng bind cho identifier hoặc từ khóa:

```sql
-- Không hợp lệ để bind tên bảng:
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM :table_name'
    INTO v_count
    USING p_table_name;
```

Oracle cần biết tên đối tượng khi parse câu SQL. Vì vậy tên bảng/cột phải nằm trong chuỗi SQL trước khi parse. Đây là trường hợp cần allowlist và DBMS_ASSERT, trình bày ở các phần sau.

### 3.6. Bind danh sách IN

Không thể coi một bind VARCHAR2 chứa `10,20,30` là danh sách ba giá trị trong predicate `IN (:ids)`. Oracle xem đó là một giá trị đơn.

Nếu cần lọc nhiều ID, có thể:
- Dùng collection SQL type và TABLE() khi kiểu collection được khai báo phù hợp.
- Dùng JSON_TABLE với JSON được bind.
- Tạo số lượng placeholder theo số phần tử, nhưng bind từng giá trị riêng.
- Nạp ID vào bảng staging hoặc global temporary table rồi join.

Ví dụ tạo collection type ở schema:

```sql
CREATE TYPE number_list_t AS TABLE OF NUMBER;
/
```

Dùng collection:

```sql
SELECT e.employee_id, e.last_name
FROM   employees e
WHERE  e.department_id IN (
    SELECT column_value
    FROM   TABLE(:department_ids)
);
```

Khả năng bind collection trực tiếp phụ thuộc ngữ cảnh và driver. Với ứng dụng, dùng API collection binding của Oracle JDBC/driver phù hợp; nếu không, dùng bảng staging hoặc tạo placeholder riêng cho từng phần tử.

## 4. SQL động có identifier thay đổi

### 4.1. Vì sao identifier cần xử lý riêng?

Một báo cáo có thể cho phép người dùng chọn cột sắp xếp:

```sql
SELECT order_id, order_date, total_amount
FROM orders
ORDER BY <selected_column>;
```

`selected_column` là tên cột, không phải giá trị dữ liệu. Oracle không cho bind tên cột vào vị trí đó. Ứng dụng cần tạo một đoạn SQL từ tập lựa chọn được cho phép.

Không nối thẳng chuỗi do client gửi:

```sql
-- Không an toàn:
v_sql := 'SELECT * FROM orders ORDER BY ' || p_sort_column;
```

Đầu vào có thể chứa thêm cú pháp ngoài ý định.

### 4.2. Allowlist là lựa chọn ưu tiên

Thay vì chấp nhận bất kỳ tên cột nào, ánh xạ mã lựa chọn sang một đoạn SQL cố định:

```sql
CASE UPPER(p_sort_key)
    WHEN 'DATE' THEN
        v_sort_column := 'ORDER_DATE';
    WHEN 'AMOUNT' THEN
        v_sort_column := 'TOTAL_AMOUNT';
    WHEN 'ID' THEN
        v_sort_column := 'ORDER_ID';
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Unsupported sort option');
END CASE;
```

Giá trị nối vào câu lệnh chỉ có thể là một trong ba tên cột do lập trình viên định nghĩa. Đầu vào bên ngoài chỉ chọn một nhánh hợp lệ.

### 4.3. Allowlist cho hướng sắp xếp

Không nối trực tiếp ASC hoặc DESC từ người dùng. Ánh xạ lựa chọn:

```sql
CASE UPPER(p_sort_direction)
    WHEN 'ASC' THEN
        v_direction := 'ASC';
    WHEN 'DESC' THEN
        v_direction := 'DESC';
    ELSE
        RAISE_APPLICATION_ERROR(-20002, 'Unsupported sort direction');
END CASE;
```

Sau đó nối v_direction, vốn chỉ có hai giá trị cố định. Áp dụng cùng nguyên tắc cho toán tử, tên schema, tên bảng, join fragment và mọi phần cấu trúc SQL động.

### 4.4. Identifier lấy từ metadata

Một số công cụ quản trị hoặc báo cáo cần chọn bảng/cột dựa trên metadata. Dù tên lấy từ dictionary, vẫn nên kiểm tra:
- Object có thuộc schema được phép không?
- Object có đúng loại không?
- Tên có nằm trong danh sách được ứng dụng cho phép không?
- Người gọi có quyền thực hiện thao tác đó không?

Tên hợp lệ về cú pháp không đồng nghĩa tên được phép dùng trong chức năng đang xây dựng.

## 5. DBMS_ASSERT là gì?

### 5.1. Package kiểm tra đầu vào cho dynamic SQL

DBMS_ASSERT là package Oracle cung cấp các hàm kiểm tra một số dạng SQL identifier hoặc literal. Nó giúp xác nhận chuỗi có hình thức phù hợp với ngữ cảnh tên SQL được hỗ trợ.

Các hàm thường gặp:
- SIMPLE_SQL_NAME
- QUALIFIED_SQL_NAME
- SCHEMA_NAME
- SQL_OBJECT_NAME
- ENQUOTE_NAME
- ENQUOTE_LITERAL
- NOOP

Các hàm này không làm cho mọi chuỗi trở nên an toàn trong mọi vị trí SQL. Phải chọn hàm theo đúng ngữ cảnh và vẫn giới hạn quyền, object và thao tác được phép.

### 5.2. SIMPLE_SQL_NAME

DBMS_ASSERT.SIMPLE_SQL_NAME kiểm tra chuỗi có phải simple SQL name hợp lệ hay không. Hàm trả về chuỗi nếu hợp lệ; nếu không, nó phát sinh exception.

```sql
DECLARE
    v_name VARCHAR2(128);
BEGIN
    v_name := DBMS_ASSERT.SIMPLE_SQL_NAME('EMPLOYEES');
    DBMS_OUTPUT.PUT_LINE(v_name);
END;
/
```

Hàm kiểm tra hình thức identifier đơn. Nó không xác nhận cột hoặc bảng tồn tại, cũng không xác nhận người gọi được phép truy cập.

### 5.3. ENQUOTE_NAME

DBMS_ASSERT.ENQUOTE_NAME kiểm tra simple SQL name và đặt tên trong dấu ngoặc kép theo quy tắc Oracle identifier:

```sql
DECLARE
    v_quoted_name VARCHAR2(300);
BEGIN
    v_quoted_name := DBMS_ASSERT.ENQUOTE_NAME(
        'EMPLOYEES',
        capitalize => TRUE
    );

    DBMS_OUTPUT.PUT_LINE(v_quoted_name);
END;
/
```

Tham số capitalize mặc định TRUE. Nếu cần giữ nguyên chữ hoa/thường của tên được quote, có thể truyền FALSE. Identifier đã quote trong Oracle phân biệt chữ hoa/thường, vì vậy hãy dùng thống nhất với cách object được tạo.

ENQUOTE_NAME không kiểm tra object có tồn tại hoặc caller có quyền truy cập. Nó chỉ hỗ trợ kiểm tra/quote tên theo ngữ pháp simple SQL name.

### 5.4. QUALIFIED_SQL_NAME

DBMS_ASSERT.QUALIFIED_SQL_NAME kiểm tra qualified SQL name theo cú pháp Oracle, ví dụ tên có thành phần schema và object:

```sql
DECLARE
    v_name VARCHAR2(300);
BEGIN
    v_name := DBMS_ASSERT.QUALIFIED_SQL_NAME('APP.EMPLOYEES');
    DBMS_OUTPUT.PUT_LINE(v_name);
END;
/
```

Hàm kiểm tra hình thức qualified name theo quy tắc Oracle. Không coi kết quả là xác nhận object tồn tại, thuộc allowlist hoặc được phép truy cập trong nghiệp vụ. Nếu cần xác nhận object tồn tại, xem SQL_OBJECT_NAME và kiểm tra thêm schema/object được phép.

### 5.5. SCHEMA_NAME

DBMS_ASSERT.SCHEMA_NAME kiểm tra schema name và xác nhận schema tương ứng tồn tại trong database:

```sql
DECLARE
    v_schema VARCHAR2(128);
BEGIN
    v_schema := DBMS_ASSERT.SCHEMA_NAME('HR');
    DBMS_OUTPUT.PUT_LINE(v_schema);
END;
/
```

Schema tồn tại không có nghĩa ứng dụng được phép cho người dùng truy cập mọi object trong schema đó. Vẫn cần allowlist và kiểm tra quyền.

### 5.6. SQL_OBJECT_NAME

DBMS_ASSERT.SQL_OBJECT_NAME kiểm tra tên SQL object đủ điều kiện và xác nhận object tương ứng tồn tại theo quy tắc của package:

```sql
DECLARE
    v_object_name VARCHAR2(300);
BEGIN
    v_object_name := DBMS_ASSERT.SQL_OBJECT_NAME('HR.EMPLOYEES');
    DBMS_OUTPUT.PUT_LINE(v_object_name);
END;
/
```

Hàm hữu ích khi dynamic SQL cần tham chiếu object đã tồn tại. Nhưng object có thật vẫn có thể nằm ngoài phạm vi mà người dùng được phép thao tác. Không dùng SQL_OBJECT_NAME thay cho authorization policy.

### 5.7. ENQUOTE_LITERAL

DBMS_ASSERT.ENQUOTE_LITERAL hỗ trợ quote chuỗi theo dạng SQL character literal:

```sql
DECLARE
    v_literal VARCHAR2(4000);
BEGIN
    v_literal := DBMS_ASSERT.ENQUOTE_LITERAL('O''Brien');
    DBMS_OUTPUT.PUT_LINE(v_literal);
END;
/
```

Hàm này có thể hữu ích khi phải tạo literal trong một số tình huống đặc biệt. Tuy nhiên, với giá trị dữ liệu thông thường, **bind variable vẫn là lựa chọn ưu tiên**. Quoting literal thủ công dễ dẫn tới sai ngữ cảnh, chuyển đổi kiểu hoặc lỗi khi câu SQL phức tạp.

Không dùng ENQUOTE_LITERAL để quote tên bảng/cột; identifier và string literal là hai ngữ cảnh khác nhau.

### 5.8. NOOP

DBMS_ASSERT.NOOP trả lại chuỗi đầu vào mà không thực hiện kiểm tra bảo mật có ý nghĩa. Không dùng NOOP như biện pháp xác thực identifier hoặc chống SQL injection.

### 5.9. Bảng chọn hàm

| Hàm | Mục đích | Không bảo đảm |
| --- | --- | --- |
| SIMPLE_SQL_NAME | Kiểm tra simple identifier | Object tồn tại hoặc caller có quyền |
| ENQUOTE_NAME | Kiểm tra và quote simple identifier | Object tồn tại hoặc nằm trong allowlist |
| QUALIFIED_SQL_NAME | Kiểm tra qualified SQL name | Object được phép dùng trong nghiệp vụ |
| SCHEMA_NAME | Kiểm tra schema tồn tại | Caller được quyền truy cập schema |
| SQL_OBJECT_NAME | Kiểm tra tên SQL object tồn tại | Object thuộc allowlist hoặc an toàn cho mọi thao tác |
| ENQUOTE_LITERAL | Quote character literal | Thay thế bind cho giá trị thông thường |
| NOOP | Trả nguyên chuỗi | Không xác thực; không dùng để bảo vệ |

Tên hàm và chi tiết hành vi cần được đối chiếu tài liệu DBMS_ASSERT của đúng phiên bản Oracle.

## 6. Kết hợp allowlist và DBMS_ASSERT

### 6.1. Kiểm tra hai lớp

Với identifier động:
1. Kiểm tra lựa chọn nghiệp vụ bằng allowlist.
2. Dùng DBMS_ASSERT để xác nhận/quote tên ở đúng ngữ cảnh.
3. Ghép identifier đã kiểm soát vào SQL.
4. Bind tất cả giá trị dữ liệu còn lại.
5. Chạy dưới quyền tối thiểu cần thiết.

Allowlist trả lời “ứng dụng có cho phép lựa chọn này không?”. DBMS_ASSERT hỗ trợ trả lời “chuỗi có đúng hình thức identifier không?”.

### 6.2. Ví dụ sort column an toàn

```sql
DECLARE
    v_column_name VARCHAR2(30);
    v_quoted_name VARCHAR2(300);
    v_direction   VARCHAR2(4);
    v_sql         VARCHAR2(4000);
    v_cursor      SYS_REFCURSOR;
BEGIN
    CASE UPPER(p_sort_key)
        WHEN 'DATE' THEN
            v_column_name := 'ORDER_DATE';
        WHEN 'AMOUNT' THEN
            v_column_name := 'TOTAL_AMOUNT';
        WHEN 'ID' THEN
            v_column_name := 'ORDER_ID';
        ELSE
            RAISE_APPLICATION_ERROR(-20001, 'Invalid sort key');
    END CASE;

    CASE UPPER(p_direction)
        WHEN 'ASC' THEN
            v_direction := 'ASC';
        WHEN 'DESC' THEN
            v_direction := 'DESC';
        ELSE
            RAISE_APPLICATION_ERROR(-20002, 'Invalid direction');
    END CASE;

    v_quoted_name :=
        DBMS_ASSERT.ENQUOTE_NAME(v_column_name);

    v_sql :=
        'SELECT order_id, order_date, total_amount ' ||
        'FROM orders ' ||
        'WHERE customer_id = :customer_id ' ||
        'ORDER BY ' || v_quoted_name || ' ' || v_direction;

    OPEN v_cursor FOR v_sql
        USING p_customer_id;
END;
/
```

Chỉ tên cột và hướng sort được nối vào SQL, và cả hai đều lấy từ tập giá trị cố định. Customer ID được bind. Trong procedure thật, cần trả REF CURSOR cho caller hoặc fetch và đóng cursor theo đúng thiết kế.

### 6.3. Tên schema và object động

Nếu ứng dụng có chức năng quản trị cần chọn object, đừng chỉ gọi SQL_OBJECT_NAME trên mọi chuỗi do người dùng gửi rồi cho phép truy vấn tùy ý.

Hãy ánh xạ mã lựa chọn sang object được phép:

```sql
CASE UPPER(p_report_code)
    WHEN 'CURRENT_ORDERS' THEN
        v_object_name := 'APP.ORDERS';
    WHEN 'ARCHIVE_ORDERS' THEN
        v_object_name := 'APP.ORDERS_ARCHIVE';
    ELSE
        RAISE_APPLICATION_ERROR(-20010, 'Unknown report');
END CASE;

v_object_name :=
    DBMS_ASSERT.SQL_OBJECT_NAME(v_object_name);

v_sql :=
    'SELECT COUNT(*) FROM ' || v_object_name;

EXECUTE IMMEDIATE v_sql INTO v_count;
```

Allowlist bảo đảm chỉ hai object được chức năng này sử dụng. SQL_OBJECT_NAME bổ sung kiểm tra object hợp lệ/tồn tại. Quyền của schema thực thi vẫn phải được giới hạn.

### 6.4. Không cho phép người dùng gửi nguyên WHERE clause

Một thiết kế rủi ro là nhận tham số p_where_clause rồi nối vào:

```sql
v_sql := 'SELECT * FROM orders WHERE ' || p_where_clause;
```

DBMS_ASSERT không phải bộ phân tích SQL tổng quát để chứng minh một WHERE clause tùy ý chỉ chứa điều kiện an toàn. Thay vào đó, nhận các trường dữ liệu riêng như customer ID, trạng thái, ngày bắt đầu/kết thúc và dựng predicate từ các nhánh cố định với bind variable.

## 7. Các dạng SQL injection nâng cao

### 7.1. Second-order SQL injection

Second-order injection xảy ra khi dữ liệu nguy hiểm được lưu trước, rồi một chương trình khác đọc dữ liệu đó và ghép vào dynamic SQL sau này.

Ví dụ:
1. Một màn hình cho phép lưu tên báo cáo hoặc giá trị cấu hình.
2. Dữ liệu được lưu vào bảng.
3. Job quản trị đọc dữ liệu đã lưu.
4. Job ghép chuỗi đó vào dynamic SQL.
5. SQL bị thay đổi cấu trúc khi job chạy.

Dữ liệu từ database không mặc nhiên đáng tin. Nguồn dữ liệu có thể là người dùng, hệ thống tích hợp, import hoặc ứng dụng khác. Bind variable và allowlist vẫn cần được áp dụng ở thời điểm tạo SQL, không chỉ ở màn hình nhập liệu.

### 7.2. NLS injection

Oracle có thể chuyển đổi NUMBER hoặc DATE sang text theo NLS settings nếu code nối giá trị vào SQL.

Ví dụ thiết kế rủi ro:

```sql
v_sql :=
    'SELECT * FROM orders WHERE order_date = ''' ||
    p_date ||
    '''';
```

Việc chuyển DATE thành text có thể phụ thuộc NLS_DATE_FORMAT hoặc thiết lập session. Trong tình huống không an toàn, NLS format do session kiểm soát có thể làm thay đổi chuỗi SQL được tạo.

Cách tốt nhất là bind DATE:

```sql
v_sql := 'SELECT * FROM orders WHERE order_date = :d';

OPEN p_cursor FOR v_sql USING p_date;
```

Nếu cần tạo text để hiển thị hoặc ghi log, dùng TO_CHAR với format mask cố định; không dùng chuỗi đã định dạng để thay thế bind trong predicate.

Tương tự với NUMBER, bind trực tiếp để tránh phụ thuộc NLS_NUMERIC_CHARACTERS.

### 7.3. Injection qua LIKE

Dùng bind variable ngăn giá trị trở thành cú pháp SQL, nhưng ký tự % và _ vẫn có ý nghĩa wildcard trong LIKE. Đây thường là vấn đề ngữ nghĩa tìm kiếm chứ không phải SQL injection.

Nếu nghiệp vụ muốn tìm chính xác chuỗi chứa ký tự % hoặc _, cần escape wildcard:

```sql
SELECT employee_id, last_name
FROM employees
WHERE last_name LIKE :p_pattern ESCAPE '\';
```

Ứng dụng phải escape ký tự escape, % và _ theo đúng thứ tự trước khi bind. Phân biệt:
- SQL injection: đầu vào thay đổi cú pháp SQL.
- Wildcard injection: đầu vào mở rộng phạm vi kết quả LIKE ngoài ý định.

### 7.4. Injection trong tên object và database link

Tên schema, bảng, cột, sequence, database link hoặc partition name có thể xuất hiện trong SQL động. Không thể bind các identifier này. Hãy:
- Dùng allowlist object cụ thể.
- Xác định schema được phép.
- Kiểm tra loại object nếu nghiệp vụ yêu cầu.
- Dùng DBMS_ASSERT đúng hàm cho identifier.
- Không cho phép người dùng tự chọn database link tùy ý.

Database link có thể mở đường truy cập hệ thống khác bằng credential đã cấu hình. Không cho người dùng điều khiển database link chỉ vì tên của nó hợp lệ về cú pháp.

### 7.5. Injection trong ORDER BY và biểu thức

ORDER BY thường cần lựa chọn cột hoặc hướng sắp xếp. Không nối biểu thức tùy ý do client gửi. Dùng mã lựa chọn đã ánh xạ sang các đoạn SQL cố định. Cùng nguyên tắc áp dụng cho:
- Tên cột trong SELECT list.
- Join condition.
- Toán tử so sánh.
- Tên bảng hoặc view.
- Tên partition.
- Hướng ASC/DESC.
- Tên function hoặc expression.

## 8. Quy trình viết dynamic SQL an toàn

### 8.1. Phân loại từng thành phần

| Thành phần | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Giá trị dữ liệu | ID, tên, số tiền, ngày | Bind variable |
| Tên bảng/cột | ORDERS, ORDER_DATE | Allowlist + DBMS_ASSERT phù hợp |
| Từ khóa/đoạn cú pháp | ASC, DESC, JOIN type | Allowlist cố định |
| Predicate động | Bộ lọc tùy chọn | Ghép fragment do code kiểm soát; bind giá trị |
| Câu SQL hoàn chỉnh do user gửi | SQL text tùy ý | Không thực thi như input thông thường |

### 8.2. Xây dựng fragment cố định

Ví dụ bộ lọc tùy chọn:

```sql
v_sql := 'SELECT order_id, customer_id, status FROM orders WHERE 1=1';

IF p_customer_id IS NOT NULL THEN
    v_sql := v_sql || ' AND customer_id = :customer_id';
END IF;

IF p_status IS NOT NULL THEN
    v_sql := v_sql || ' AND status = :status';
END IF;
```

Các fragment AND customer_id = :customer_id và AND status = :status do chương trình định nghĩa. Không có phần cú pháp nào lấy trực tiếp từ người dùng.

Khi có nhiều tổ hợp điều kiện, việc quản lý thứ tự bind có thể phức tạp. Hãy viết rõ từng nhánh và danh sách USING tương ứng, hoặc dùng DBMS_SQL khi số bind thay đổi linh hoạt.

### 8.3. Ví dụ các nhánh bind rõ ràng

```sql
IF p_customer_id IS NOT NULL
   AND p_status IS NOT NULL
THEN
    v_sql :=
        'SELECT order_id, total_amount FROM orders ' ||
        'WHERE customer_id = :1 AND status = :2';

    OPEN p_result FOR v_sql
        USING p_customer_id, p_status;

ELSIF p_customer_id IS NOT NULL THEN
    v_sql :=
        'SELECT order_id, total_amount FROM orders ' ||
        'WHERE customer_id = :1';

    OPEN p_result FOR v_sql
        USING p_customer_id;

ELSIF p_status IS NOT NULL THEN
    v_sql :=
        'SELECT order_id, total_amount FROM orders ' ||
        'WHERE status = :1';

    OPEN p_result FOR v_sql
        USING p_status;

ELSE
    v_sql :=
        'SELECT order_id, total_amount FROM orders';

    OPEN p_result FOR v_sql;
END IF;
```

Cách này dài hơn nhưng thể hiện rõ từng cấu trúc và thứ tự bind. Với bộ lọc lớn hơn, có thể dùng DBMS_SQL hoặc query builder có quy tắc bind được kiểm soát.

### 8.4. Dynamic DDL

Nhiều câu DDL không hỗ trợ bind ở vị trí tên object hoặc một số thuộc tính cú pháp. Khi tạo bảng/index/partition động:
- Chỉ cho phép object name từ allowlist hoặc quy tắc đặt tên nội bộ.
- Dùng DBMS_ASSERT để xác thực/quote identifier.
- Kiểm tra kiểu dữ liệu, tablespace, partition option từ enum/allowlist.
- Không nối trực tiếp DDL fragment do người dùng gửi.
- Chạy bằng tài khoản quản trị có quyền tối thiểu cần thiết và tách khỏi schema ứng dụng thông thường.

Không dùng DBMS_ASSERT để hợp thức hóa một chuỗi DDL đầy đủ do người dùng gửi.

## 9. DBMS_ASSERT không thay thế authorization

### 9.1. Identifier hợp lệ chưa chắc được phép

Ví dụ HR.EMPLOYEES có thể là tên object hợp lệ và tồn tại. Nhưng một chức năng chỉ cho phép báo cáo trên APP.ORDERS không nên chấp nhận HR.EMPLOYEES chỉ vì SQL_OBJECT_NAME xác nhận nó tồn tại.

Allowlist là lớp kiểm soát nghiệp vụ; DBMS_ASSERT là lớp xác thực hình thức tên.

### 9.2. Quyền của definer-rights procedure

Stored procedure mặc định thường chạy theo definer rights (AUTHID DEFINER). Điều này có thể khiến procedure sử dụng quyền của owner. Nếu procedure nhận tên object tùy ý rồi chạy dynamic SQL, nó có thể vô tình phơi bày quyền rộng của owner cho caller.

Thiết kế an toàn:
- Chỉ expose thao tác nghiệp vụ cụ thể, không expose một SQL console tổng quát.
- Giới hạn object và thao tác bằng allowlist.
- Cấp quyền tối thiểu cho owner.
- Không dùng schema ứng dụng có quyền DBA.
- Kiểm tra authorization của caller trước thao tác nhạy cảm.

### 9.3. AUTHID CURRENT_USER

Procedure có thể khai báo AUTHID CURRENT_USER để dùng invoker rights theo ngữ nghĩa Oracle:

```sql
CREATE OR REPLACE PROCEDURE read_allowed_data (
    p_id IN NUMBER
)
AUTHID CURRENT_USER
AS
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM allowed_table WHERE id = :1'
    INTO v_count
    USING p_id;
END;
/
```

Invoker rights làm thay đổi mô hình phân giải tên và quyền thực thi của chương trình. Nó không tự loại bỏ SQL injection. Vẫn cần bind variable, allowlist và kiểm tra quyền. Chọn DEFINER hoặc CURRENT_USER dựa trên thiết kế bảo mật, không dùng như cách chữa injection đơn lẻ.

### 9.4. Least privilege

Tài khoản kết nối ứng dụng chỉ nên có:
- Quyền cần thiết trên các bảng/view/procedure được dùng.
- Không có quyền tạo/drop object nếu nghiệp vụ không cần.
- Không có quyền quản trị database.
- Không có quyền truy cập schema khác ngoài phạm vi.
- Quyền EXECUTE package/procedure đúng nhu cầu.

Nếu injection xảy ra, least privilege giới hạn những gì câu lệnh bị lợi dụng có thể làm.

## 10. Mẫu procedure tìm kiếm an toàn

### 10.1. Procedure với giá trị bind

```sql
CREATE OR REPLACE PROCEDURE find_orders (
    p_customer_id IN  orders.customer_id%TYPE,
    p_from_date   IN  DATE,
    p_result      OUT SYS_REFCURSOR
)
AUTHID DEFINER
AS
    v_sql VARCHAR2(4000);
BEGIN
    v_sql :=
        'SELECT order_id, order_date, total_amount ' ||
        'FROM orders ' ||
        'WHERE customer_id = :customer_id ' ||
        'AND order_date >= :from_date ' ||
        'ORDER BY order_date DESC';

    OPEN p_result FOR v_sql
        USING p_customer_id, p_from_date;
END;
/
```

Procedure chỉ tạo SQL cấu trúc cố định. Customer và date được bind. Caller vẫn cần được xác thực để gọi procedure theo quy tắc ứng dụng.

### 10.2. Procedure cho phép chọn cột sort

```sql
CREATE OR REPLACE PROCEDURE find_orders_sorted (
    p_customer_id IN orders.customer_id%TYPE,
    p_sort_key    IN VARCHAR2,
    p_result      OUT SYS_REFCURSOR
)
AUTHID DEFINER
AS
    v_sort_column VARCHAR2(30);
    v_sql         VARCHAR2(4000);
BEGIN
    CASE UPPER(p_sort_key)
        WHEN 'DATE' THEN
            v_sort_column := 'ORDER_DATE';
        WHEN 'AMOUNT' THEN
            v_sort_column := 'TOTAL_AMOUNT';
        WHEN 'ID' THEN
            v_sort_column := 'ORDER_ID';
        ELSE
            RAISE_APPLICATION_ERROR(-20020, 'Invalid sort key');
    END CASE;

    v_sort_column :=
        DBMS_ASSERT.ENQUOTE_NAME(v_sort_column);

    v_sql :=
        'SELECT order_id, order_date, total_amount ' ||
        'FROM orders ' ||
        'WHERE customer_id = :1 ' ||
        'ORDER BY ' || v_sort_column;

    OPEN p_result FOR v_sql
        USING p_customer_id;
END;
/
```

Tên cột được ánh xạ từ allowlist và quote bằng ENQUOTE_NAME. Customer ID được bind. Nếu muốn hỗ trợ ASC/DESC, hãy ánh xạ hướng sort qua CASE riêng, không nối input thô.

### 10.3. Kiểm soát lỗi

Không trả toàn bộ SQL động, stack trace hoặc metadata nội bộ cho client cuối. Có thể ghi mã lỗi và correlation ID vào log có kiểm soát, còn client nhận thông báo phù hợp.

Trong quá trình phát triển, DBA/dev có thể ghi SQL_ID hoặc câu SQL có placeholder để điều tra. Không ghi giá trị bind nhạy cảm vào log nếu không cần.

## 11. Kiểm thử và rà soát SQL injection

### 11.1. Kiểm tra source code

Tìm các vị trí:
- EXECUTE IMMEDIATE
- OPEN ... FOR
- DBMS_SQL.PARSE
- Chuỗi ghép với tham số procedure hoặc input bên ngoài.
- Dynamic DDL.
- Stored procedure nhận tên bảng/cột/WHERE clause.
- Job đọc dữ liệu từ bảng cấu hình rồi ghép vào SQL.

Mỗi vị trí cần xác định nguồn dữ liệu, ngữ cảnh sử dụng và cách bind/validate.

### 11.2. Kiểm thử bằng input bất thường vô hại

Trong môi trường test, thử:
- Chuỗi có dấu nháy đơn.
- Chuỗi có comment marker.
- Chuỗi dài bất thường.
- Tên object không tồn tại.
- Tên object hợp lệ nhưng ngoài allowlist.
- Giá trị chứa wildcard % và _ khi dùng LIKE.
- Ngày/số trong các NLS setting khác nhau.
- Dữ liệu đã lưu từ trước rồi được dùng lại trong dynamic SQL.

Mục tiêu là xác nhận input luôn được xử lý như dữ liệu hoặc bị từ chối theo allowlist, không làm thay đổi cấu trúc câu SQL.

### 11.3. Kiểm tra quyền

Thử procedure bằng:
- User hợp lệ có quyền nghiệp vụ.
- User không có quyền.
- User cố chọn object ngoài allowlist.
- User gọi chức năng với schema khác.
- User truyền tên object hợp lệ nhưng không thuộc phạm vi.

Kiểm tra kết quả thực thi theo quyền thiết kế, không chỉ kiểm tra chuỗi có hợp lệ hay không.

### 11.4. Regression test

Sau khi sửa:
- Xác nhận kết quả truy vấn đúng với input hợp lệ.
- Xác nhận input bất thường không làm thay đổi SQL structure.
- Xác nhận lỗi được xử lý nhất quán.
- Kiểm tra execution plan nếu thay đổi cách bind hoặc query structure.
- Kiểm tra transaction và side effect.
- Kiểm tra log không làm lộ dữ liệu nhạy cảm.

## 12. Các lỗi và hiểu nhầm thường gặp

| Hiểu nhầm hoặc lỗi | Giải thích |
| --- | --- |
| Dùng DBMS_ASSERT cho mọi input là đủ | Không; phải bind giá trị và allowlist identifier |
| Bind được tên bảng | Không; bind chỉ dành cho giá trị biểu thức |
| Quote chuỗi bằng cách thay dấu nháy thủ công là đủ | Dễ thiếu trường hợp và sai ngữ cảnh |
| SQL_OBJECT_NAME chứng minh caller có quyền | Không; nó không thay authorization |
| SIMPLE_SQL_NAME xác nhận object tồn tại | Không; nó kiểm tra hình thức simple name |
| ENQUOTE_NAME dùng cho string literal | Không; dùng cho identifier |
| ENQUOTE_LITERAL thay thế bind | Không; bind vẫn ưu tiên cho giá trị |
| Dữ liệu đọc từ database luôn đáng tin | Sai; có thể là dữ liệu user nhập trước đó |
| NUMBER/DATE nối thành text luôn an toàn | Không; có thể chịu ảnh hưởng NLS conversion |
| LIKE wildcard là SQL injection | Không nhất thiết; đây là ngữ nghĩa wildcard cần xử lý riêng |
| Procedure definer rights không có rủi ro | Sai; quyền owner có thể làm tăng tác động |
| Bắt OTHERS rồi bỏ qua lỗi là an toàn | Sai; có thể che giấu lỗi và để transaction ở trạng thái không mong muốn |

### 12.1. Phân biệt ba lớp kiểm soát

- **Bind variable:** tách giá trị dữ liệu khỏi cú pháp SQL.
- **DBMS_ASSERT:** xác thực/quote một số identifier hoặc literal theo ngữ cảnh cụ thể.
- **Authorization/allowlist:** quyết định người gọi được phép thao tác trên object/chức năng nào.

Ba lớp này bổ sung cho nhau. Không lớp nào thay thế hoàn toàn hai lớp còn lại.

## 13. Checklist trước khi đưa dynamic SQL vào production

1. Mọi giá trị dữ liệu đã được bind chưa?
2. Có chỗ nào nối input trực tiếp vào SQL/PLSQL string không?
3. Identifier động có allowlist cụ thể không?
4. DBMS_ASSERT có được dùng đúng ngữ cảnh tên/literal không?
5. Có cho phép client gửi nguyên WHERE clause hoặc SQL fragment không?
6. Có xử lý dữ liệu đọc từ bảng cấu hình (second-order) như input không tin cậy không?
7. Có chuyển DATE/NUMBER sang text theo NLS rồi ghép SQL không?
8. Có phân biệt wildcard LIKE với SQL injection không?
9. Procedure chạy theo definer rights hay invoker rights, và quyền có tối thiểu không?
10. Caller có được kiểm tra authorization theo nghiệp vụ không?
11. Error/log có làm lộ SQL, dữ liệu bind hoặc thông tin nhạy cảm không?
12. Đã kiểm thử input bất thường và regression trên môi trường test chưa?

## 14. Bài thực hành

### Bài 1 — Nhận diện SQL injection

Đọc đoạn code nối p_last_name vào câu SELECT ở mục 1. Giải thích vì sao dấu nháy đơn trong dữ liệu có thể làm thay đổi cú pháp.

### Bài 2 — Chuyển sang bind variable

Viết lại ví dụ tìm nhân viên bằng EXECUTE IMMEDIATE ... USING. Kiểm tra với họ tên có dấu nháy đơn như O'Brien.

### Bài 3 — Bind UPDATE và DELETE

Viết hai block cập nhật salary và xóa order theo ID. Đảm bảo mọi giá trị đều được bind.

### Bài 4 — Dynamic query với REF CURSOR

Viết procedure mở REF CURSOR theo customer ID và ngày bắt đầu. Dùng OPEN FOR ... USING.

### Bài 5 — Sort key allowlist

Cho phép sort theo DATE, AMOUNT hoặc ID. Từ chối mọi lựa chọn khác bằng RAISE_APPLICATION_ERROR. Không nối p_sort_key trực tiếp.

### Bài 6 — Dùng SIMPLE_SQL_NAME

Thử SIMPLE_SQL_NAME với tên cột hợp lệ và chuỗi có khoảng trắng/ký tự cú pháp. Quan sát exception và giải thích giới hạn của hàm.

### Bài 7 — Dùng ENQUOTE_NAME

Quote tên cột từ allowlist bằng ENQUOTE_NAME. Thử khác biệt capitalize TRUE/FALSE và giải thích tác động của quoted identifier.

### Bài 8 — Phân biệt QUALIFIED_SQL_NAME và SQL_OBJECT_NAME

Thử tên APP.ORDERS, tên object không tồn tại và chuỗi sai cú pháp. Ghi nhận hàm nào kiểm tra cú pháp, hàm nào kiểm tra object tồn tại theo tài liệu phiên bản.

### Bài 9 — NLS conversion

Viết ví dụ không an toàn nối DATE vào SQL text. Sau đó thay bằng bind DATE và giải thích vì sao không phụ thuộc NLS_DATE_FORMAT.

### Bài 10 — Second-order injection

Thiết kế bảng lưu tên báo cáo. Viết job đọc tên từ bảng và dùng nó trong dynamic SQL. Sửa để tên báo cáo chỉ được ánh xạ qua allowlist.

### Bài 11 — LIKE wildcard

Viết truy vấn tìm chuỗi literal có chứa % hoặc _. Bind pattern và escape wildcard theo đúng cú pháp ESCAPE.

### Bài 12 — Authorization

Tạo procedure definer rights chỉ cho phép truy vấn hai bảng báo cáo trong allowlist. Kiểm tra user gọi không thể chọn object khác dù object đó tồn tại.

### Bài 13 — Dynamic DDL

Viết script tạo bảng demo với tên được tạo theo quy tắc nội bộ. Dùng allowlist/DBMS_ASSERT cho identifier và cố định kiểu dữ liệu, tablespace, constraint; không nhận nguyên DDL từ người dùng.

### Bài 14 — Rà soát source

Tìm tất cả EXECUTE IMMEDIATE, OPEN FOR và DBMS_SQL.PARSE trong một project PL/SQL. Phân loại thành:
- Cấu trúc cố định, giá trị bind.
- Identifier allowlist + DBMS_ASSERT.
- Cần refactor vì nối input không tin cậy.

## 15. Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html): các hàm kiểm tra và quote SQL name/literal.
- [Oracle Database PL/SQL Language Reference — Native Dynamic SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dynamic-sql.html): EXECUTE IMMEDIATE, OPEN FOR và bind arguments.
- [Oracle Database PL/SQL Language Reference — DBMS_SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/DBMS_SQL.html): dynamic SQL với DBMS_SQL.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): nguyên tắc bảo mật database và quyền.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): cú pháp SQL, identifier và literal.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/): package và API PL/SQL.

Khi viết SQL động, hãy giữ cấu trúc SQL do chương trình kiểm soát và truyền mọi giá trị qua bind variable. Nếu phải thay đổi tên bảng, tên cột hoặc từ khóa, chọn từ allowlist rồi dùng DBMS_ASSERT phù hợp để kiểm tra/quote identifier. Hãy coi dữ liệu lưu trong database cũng có thể không đáng tin, tránh chuyển DATE/NUMBER sang text theo NLS, giới hạn quyền của procedure và kiểm thử các đường đi của dynamic SQL. **Bind variable là lớp phòng vệ chính cho giá trị; DBMS_ASSERT và allowlist bổ sung kiểm soát cho identifier; authorization giới hạn những gì caller được phép làm.**
