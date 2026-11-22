# DBMS_SQL khi số cột hoặc số biến bind chưa biết trước trong Oracle PL/SQL

Dynamic SQL cho phép chương trình xây dựng và thực thi câu lệnh SQL khi chạy. Với Native Dynamic SQL (NDS), PL/SQL thường dùng EXECUTE IMMEDIATE hoặc OPEN FOR. Cách này ngắn gọn và phù hợp khi cấu trúc câu lệnh, số bind variable và kiểu dữ liệu kết quả đã biết tại thời điểm viết code.

Nhưng có những tình huống ứng dụng chỉ nhận được câu SQL lúc runtime:

- Một công cụ báo cáo cho phép người dùng chọn số cột tùy ý.
- Một bộ lọc tìm kiếm sinh ra số predicate thay đổi theo màn hình.
- Một tiện ích quản trị nhận câu SELECT từ cấu hình.
- Một framework cần đọc kết quả mà không biết trước tên và kiểu các cột.
- Một bộ thực thi câu SQL nhận danh sách bind variable từ metadata.

Trong các tình huống này, số lượng cột hoặc bind variable có thể chưa biết khi biên dịch PL/SQL. Package **DBMS_SQL** cung cấp API dạng thủ tục để mở cursor, parse SQL, mô tả cột kết quả, định nghĩa biến nhận dữ liệu, bind giá trị, execute và fetch từng dòng.

Một điểm cần phân biệt: DBMS_SQL có thể mô tả các cột của result set sau khi parse SELECT, nhưng không cung cấp một API tổng quát tương đương DESCRIBE_COLUMNS để tự khám phá toàn bộ bind placeholder trong một câu SQL tùy ý. Nếu số bind chưa biết, ứng dụng cần có metadata về tên và kiểu bind từ bộ sinh SQL hoặc một hợp đồng đầu vào rõ ràng. DBMS_SQL giúp bind động theo metadata đó.

## 1. Khi nào cần DBMS_SQL?

### 1.1 Native Dynamic SQL phù hợp khi cấu trúc đã biết

Nếu biết trước câu SQL và số biến nhận kết quả, EXECUTE IMMEDIATE thường là lựa chọn đơn giản:

~~~sql
DECLARE
    l_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE department_id = :dept'
        INTO l_count
        USING 10;

    DBMS_OUTPUT.PUT_LINE(l_count);
END;
/
~~~

Nếu số cột SELECT được biết trước:

~~~sql
DECLARE
    l_name employees.last_name%TYPE;
    l_salary employees.salary%TYPE;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT last_name, salary
           FROM employees
          WHERE employee_id = :id'
        INTO l_name, l_salary
        USING 100;
END;
/
~~~

PL/SQL cần danh sách biến INTO tương ứng với result columns. Nếu số cột thay đổi tùy câu SQL, không thể viết một INTO list cố định phù hợp cho mọi câu lệnh.

### 1.2 DBMS_SQL phù hợp khi số lượng hoặc kiểu cột chỉ biết lúc runtime

DBMS_SQL cho phép:

1. Mở cursor bằng OPEN_CURSOR.
2. Parse câu SQL bằng PARSE.
3. Mô tả số lượng và metadata cột bằng DESCRIBE_COLUMNS.
4. Gọi DEFINE_COLUMN cho từng cột và kiểu dữ liệu phù hợp.
5. Execute câu lệnh.
6. Fetch từng dòng và lấy giá trị bằng COLUMN_VALUE.
7. Đóng cursor bằng CLOSE_CURSOR.

~~~text
OPEN_CURSOR
    |
    v
PARSE SQL
    |
    v
DESCRIBE_COLUMNS
    |
    v
DEFINE_COLUMN cho từng cột
    |
    v
EXECUTE
    |
    v
FETCH_ROWS
    |
    v
COLUMN_VALUE cho từng cột
    |
    v
CLOSE_CURSOR
~~~

### 1.3 DBMS_SQL cũng hữu ích khi bind list được cung cấp lúc runtime

Nếu SQL builder tạo câu SQL cùng danh sách placeholder và kiểu dữ liệu tương ứng, chương trình có thể duyệt metadata rồi gọi BIND_VARIABLE nhiều lần. Điều này phù hợp với số lượng bind thay đổi.

DBMS_SQL không tự suy luận được giá trị nghiệp vụ, kiểu dữ liệu mong muốn hoặc ý nghĩa của từng placeholder. Những thông tin đó phải đến từ caller, cấu hình hoặc SQL builder.

## 2. DBMS_SQL và Native Dynamic SQL

| Tiêu chí | Native Dynamic SQL | DBMS_SQL |
|---|---|---|
| API chính | EXECUTE IMMEDIATE, OPEN FOR | OPEN_CURSOR, PARSE, BIND_VARIABLE, DEFINE_COLUMN, EXECUTE, FETCH_ROWS |
| Số cột kết quả | Thường phải biết trước trong PL/SQL | Có thể mô tả lúc runtime |
| Số biến bind | Danh sách USING được viết tường minh | Có thể bind theo vòng lặp từ metadata |
| Kiểu dữ liệu | Dễ dùng với kiểu PL/SQL đã biết | Cần dispatch đúng overload theo metadata |
| Độ dài code | Thường ngắn hơn | Nhiều bước và trạng thái cursor hơn |
| Trường hợp phù hợp | SQL động nhưng cấu trúc đã biết | SQL tổng quát, cấu trúc kết quả chưa biết |
| Chuyển đổi cursor | Có thể dùng SYS_REFCURSOR | Có thể chuyển qua TO_REFCURSOR và TO_CURSOR_NUMBER |

Không nên dùng DBMS_SQL cho mọi câu SQL động. Nếu số cột và bind đã biết, NDS thường dễ đọc, dễ bảo trì và ít code hơn. Chọn DBMS_SQL khi tính tổng quát của cấu trúc runtime thực sự cần thiết.

## 3. Vòng đời cursor của DBMS_SQL

### 3.1 OPEN_CURSOR

OPEN_CURSOR cấp một cursor number:

~~~sql
l_cursor := DBMS_SQL.OPEN_CURSOR;
~~~

Cursor number là handle nội bộ của DBMS_SQL, không phải SQL cursor name hay SYS_REFCURSOR.

### 3.2 PARSE

PARSE phân tích câu SQL:

~~~sql
DBMS_SQL.PARSE(
    c             => l_cursor,
    statement     => l_sql,
    language_flag => DBMS_SQL.NATIVE
);
~~~

DBMS_SQL.NATIVE chỉ định cú pháp SQL/PLSQL native của Oracle. Parse kiểm tra cú pháp và chuẩn bị statement; với SELECT, result metadata có thể được mô tả sau bước này.

### 3.3 DESCRIBE_COLUMNS

Sau khi parse SELECT, có thể gọi DESCRIBE_COLUMNS hoặc phiên bản mở rộng:

~~~sql
DBMS_SQL.DESCRIBE_COLUMNS2(
    c       => l_cursor,
    col_cnt => l_col_count,
    desc_t  => l_desc
);
~~~

DESCRIBE_COLUMNS2 trả số cột và mô tả từng cột qua DESC_TAB2. Metadata thường bao gồm:

- COL_NAME: tên cột hoặc alias.
- COL_TYPE: mã kiểu dữ liệu Oracle.
- COL_MAX_LEN: độ dài tối đa được mô tả.
- COL_PRECISION và COL_SCALE: precision/scale khi áp dụng.
- COL_NULL_OK: thông tin nullability được mô tả.
- Các thông tin charset hoặc type metadata tùy record/version.

DESCRIBE_COLUMNS3 và DESC_TAB3 có thể được dùng khi cần metadata mở rộng, chẳng hạn thông tin tên kiểu/schema cho các kiểu dữ liệu phù hợp. Hãy kiểm tra package specification của phiên bản Oracle đang triển khai.

### 3.4 DEFINE_COLUMN

Với SELECT, phải định nghĩa biến nhận dữ liệu cho từng cột trước khi fetch:

~~~sql
DBMS_SQL.DEFINE_COLUMN(l_cursor, 1, l_varchar_value, 32767);
DBMS_SQL.DEFINE_COLUMN(l_cursor, 2, l_number_value);
DBMS_SQL.DEFINE_COLUMN(l_cursor, 3, l_date_value);
~~~

Overload được chọn phải phù hợp với kiểu dữ liệu trả về. Không thể dùng một biến VARCHAR2 cho mọi kiểu cột rồi giả định Oracle tự chuyển đổi an toàn mọi kiểu.

### 3.5 EXECUTE

~~~sql
l_result := DBMS_SQL.EXECUTE(l_cursor);
~~~

Với DML, giá trị trả về cho biết số dòng được xử lý theo semantics của DBMS_SQL. Với SELECT, cần gọi FETCH_ROWS để lấy các dòng kết quả; không dùng giá trị trả về của EXECUTE như số dòng SELECT.

### 3.6 FETCH_ROWS và COLUMN_VALUE

FETCH_ROWS lấy dòng tiếp theo:

~~~sql
WHILE DBMS_SQL.FETCH_ROWS(l_cursor) > 0 LOOP
    DBMS_SQL.COLUMN_VALUE(l_cursor, 1, l_varchar_value);
END LOOP;
~~~

COLUMN_VALUE sao chép giá trị cột đã define vào biến PL/SQL tương ứng. Vị trí cột bắt đầu từ 1.

### 3.7 CLOSE_CURSOR

Khi hoàn tất, luôn đóng cursor:

~~~sql
DBMS_SQL.CLOSE_CURSOR(l_cursor);
~~~

Cursor mở mà không đóng có thể giữ tài nguyên session và dẫn đến lỗi quá nhiều cursor mở. Phải đóng cả trong nhánh exception.

## 4. Ví dụ: đọc SELECT có số cột chưa biết trước

Ví dụ dưới đây nhận câu SELECT lúc runtime. Nó hỗ trợ ba loại scalar phổ biến trong minh họa: VARCHAR2, NUMBER và DATE. Các kiểu khác được báo rõ là chưa được xử lý; trong ứng dụng thực tế cần bổ sung overload tương ứng cho TIMESTAMP, RAW, CLOB, BLOB, BINARY_FLOAT, object type hoặc các kiểu khác theo nhu cầu.

~~~sql
SET SERVEROUTPUT ON

DECLARE
    l_sql       VARCHAR2(32767) :=
        'SELECT table_name, num_rows, last_analyzed
           FROM user_tables
          WHERE table_name LIKE ''EMP%''';

    l_cursor    INTEGER;
    l_col_count PLS_INTEGER;
    l_desc      DBMS_SQL.DESC_TAB2;
    l_exec      INTEGER;
    l_fetch     INTEGER;

    l_varchar   VARCHAR2(32767);
    l_number    NUMBER;
    l_date      DATE;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        l_sql,
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.DESCRIBE_COLUMNS2(
        l_cursor,
        l_col_count,
        l_desc
    );

    DBMS_OUTPUT.PUT_LINE('Column count = ' || l_col_count);

    -- Define buffer cho từng cột dựa trên kiểu được mô tả.
    FOR i IN 1 .. l_col_count LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Column ' || i ||
            ': ' || l_desc(i).col_name ||
            ', type code=' || l_desc(i).col_type ||
            ', max length=' || l_desc(i).col_max_len
        );

        CASE l_desc(i).col_type
            WHEN 1 THEN
                DBMS_SQL.DEFINE_COLUMN(
                    l_cursor, i, l_varchar, 32767
                );
            WHEN 2 THEN
                DBMS_SQL.DEFINE_COLUMN(
                    l_cursor, i, l_number
                );
            WHEN 12 THEN
                DBMS_SQL.DEFINE_COLUMN(
                    l_cursor, i, l_date
                );
            ELSE
                RAISE_APPLICATION_ERROR(
                    -20001,
                    'Unsupported column type code: ' ||
                    l_desc(i).col_type ||
                    ' for column ' || l_desc(i).col_name
                );
        END CASE;
    END LOOP;

    l_exec := DBMS_SQL.EXECUTE(l_cursor);

    WHILE DBMS_SQL.FETCH_ROWS(l_cursor) > 0 LOOP
        FOR i IN 1 .. l_col_count LOOP
            CASE l_desc(i).col_type
                WHEN 1 THEN
                    DBMS_SQL.COLUMN_VALUE(l_cursor, i, l_varchar);
                    DBMS_OUTPUT.PUT_LINE(
                        l_desc(i).col_name || '=' || NVL(l_varchar, '<NULL>')
                    );
                WHEN 2 THEN
                    DBMS_SQL.COLUMN_VALUE(l_cursor, i, l_number);
                    DBMS_OUTPUT.PUT_LINE(
                        l_desc(i).col_name || '=' ||
                        NVL(TO_CHAR(l_number), '<NULL>')
                    );
                WHEN 12 THEN
                    DBMS_SQL.COLUMN_VALUE(l_cursor, i, l_date);
                    DBMS_OUTPUT.PUT_LINE(
                        l_desc(i).col_name || '=' ||
                        NVL(TO_CHAR(l_date, 'YYYY-MM-DD HH24:MI:SS'), '<NULL>')
                    );
            END CASE;
        END LOOP;

        DBMS_OUTPUT.PUT_LINE('---');
    END LOOP;

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(l_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        RAISE;
END;
/
~~~

### 4.1 Vì sao cần hai vòng lặp?

Vòng lặp đầu tiên duyệt metadata để DEFINE_COLUMN cho toàn bộ result columns. Oracle cần biết biến đích và kiểu dữ liệu trước khi FETCH_ROWS.

Vòng lặp thứ hai chạy sau mỗi FETCH_ROWS, đọc giá trị của từng cột bằng COLUMN_VALUE. Cả hai vòng lặp đều dùng số cột được trả về từ DESCRIBE_COLUMNS2, nên không cần biết trước số lượng cột.

### 4.2 Vì sao ví dụ chỉ hỗ trợ ba kiểu?

DBMS_SQL dùng các overload có kiểu cụ thể. Ví dụ trên cố ý chỉ hỗ trợ VARCHAR2 (type code 1), NUMBER (2) và DATE (12) để thể hiện cơ chế dispatch. Một result set tổng quát có thể chứa nhiều kiểu hơn:

- CHAR, NCHAR, NVARCHAR2.
- TIMESTAMP và TIMESTAMP WITH TIME ZONE.
- INTERVAL.
- RAW.
- CLOB, NCLOB, BLOB.
- BINARY_FLOAT, BINARY_DOUBLE.
- Object type hoặc các kiểu đặc biệt khác.

Với mỗi loại cần chọn biến PL/SQL, DEFINE_COLUMN và COLUMN_VALUE tương ứng. Một số kiểu dài hoặc đặc biệt cần API chuyên dụng như DEFINE_COLUMN_LONG/COLUMN_VALUE_LONG. Không chuyển mọi giá trị thành chuỗi mà không xem xét độ dài, charset, định dạng ngày và độ chính xác số.

### 4.3 Xử lý cột alias và tên trùng

Result set có thể có hai cột cùng tên nếu SQL không đặt alias riêng. Khi xây dựng metadata cho client, nên giữ vị trí cột làm định danh ổn định và đặt alias duy nhất nếu cần. COL_NAME là metadata hiển thị; không dùng nó làm chỉ số thay cho vị trí cột.

## 5. Các kiểu dữ liệu và DEFINE_COLUMN

DBMS_SQL có nhiều overload DEFINE_COLUMN. Quy tắc là kiểu biến nhận phải tương thích với kiểu SQL được mô tả.

| SQL result type | Biến PL/SQL minh họa | Ghi chú |
|---|---|---|
| VARCHAR2 | VARCHAR2 | Cần chỉ định kích thước buffer trong overload phù hợp |
| CHAR | CHAR hoặc VARCHAR2 phù hợp | Xem độ dài và semantics padding |
| NUMBER | NUMBER | Giữ precision/scale |
| DATE | DATE | Định dạng chỉ áp dụng khi hiển thị |
| TIMESTAMP | TIMESTAMP | Cần overload đúng kiểu timestamp |
| RAW | RAW | Buffer phải đủ lớn |
| CLOB | CLOB | Xử lý LOB locator và đọc nội dung phù hợp |
| BLOB | BLOB | Xử lý binary LOB, không chuyển tùy tiện sang VARCHAR2 |
| LONG | API LONG chuyên dụng | Dùng DEFINE_COLUMN_LONG/COLUMN_VALUE_LONG theo giới hạn API |

Ví dụ với timestamp:

~~~sql
DECLARE
    l_ts TIMESTAMP;
BEGIN
    -- Sau khi PARSE và DESCRIBE:
    -- DBMS_SQL.DEFINE_COLUMN(l_cursor, l_position, l_ts);
    NULL;
END;
/
~~~

Đoạn này chỉ minh họa kiểu biến. Trong code thực tế, đặt DEFINE_COLUMN ở giai đoạn define trước EXECUTE/FETCH và gọi COLUMN_VALUE với cùng kiểu.

### 5.1 COL_MAX_LEN không phải lúc nào cũng là kích thước buffer hoàn chỉnh

COL_MAX_LEN là metadata mô tả độ dài cột theo result descriptor. Với character data, cần xét byte/character semantics, charset và giới hạn biến PL/SQL. Với LOB hoặc kiểu đặc biệt, không thể chỉ cấp VARCHAR2(COL_MAX_LEN) rồi coi là xử lý đầy đủ.

### 5.2 NULL vẫn là một giá trị hợp lệ

Nếu cột trả NULL, COLUMN_VALUE đặt biến đích thành NULL. Điều đó khác với cột không tồn tại: cột luôn được xác định theo vị trí trong metadata; NULL là giá trị của dòng tại vị trí cột đó.

## 6. Bind variable với DBMS_SQL

### 6.1 Bind theo tên

DBMS_SQL cho phép bind theo placeholder name:

~~~sql
DECLARE
    l_cursor INTEGER;
    l_rows   INTEGER;
    l_salary NUMBER := 8000;
    l_emp_id NUMBER := 100;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        'UPDATE employees
            SET salary = :new_salary
          WHERE employee_id = :emp_id',
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor, ':new_salary', l_salary
    );
    DBMS_SQL.BIND_VARIABLE(
        l_cursor, ':emp_id', l_emp_id
    );

    l_rows := DBMS_SQL.EXECUTE(l_cursor);

    DBMS_OUTPUT.PUT_LINE('Rows processed=' || l_rows);

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(l_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

Trong ví dụ, câu UPDATE có hai bind placeholder. DBMS_SQL.BIND_VARIABLE được gọi riêng cho từng tên. Giá trị dữ liệu được truyền bằng bind thay vì nối vào chuỗi SQL.

### 6.2 Số bind thay đổi theo metadata

Giả sử một bộ sinh SQL trả về:

- SQL text.
- Danh sách bind name.
- Kiểu dữ liệu của từng bind.
- Giá trị tương ứng.

PL/SQL có thể duyệt danh sách rồi gọi overload phù hợp:

~~~sql
FOR i IN 1 .. l_bind_count LOOP
    CASE l_binds(i).data_type
        WHEN 'NUMBER' THEN
            DBMS_SQL.BIND_VARIABLE(
                l_cursor,
                l_binds(i).bind_name,
                l_binds(i).number_value
            );
        WHEN 'VARCHAR2' THEN
            DBMS_SQL.BIND_VARIABLE(
                l_cursor,
                l_binds(i).bind_name,
                l_binds(i).varchar_value
            );
        WHEN 'DATE' THEN
            DBMS_SQL.BIND_VARIABLE(
                l_cursor,
                l_binds(i).bind_name,
                l_binds(i).date_value
            );
        ELSE
            RAISE_APPLICATION_ERROR(
                -20002,
                'Unsupported bind type: ' || l_binds(i).data_type
            );
    END CASE;
END LOOP;
~~~

Đây là phần lõi của mô hình metadata-driven binding. L_BINDS và các field trong ví dụ là cấu trúc dữ liệu do ứng dụng tự định nghĩa; chúng không phải kiểu có sẵn của DBMS_SQL. Một implementation thật cần khai báo record/collection phù hợp hoặc dùng các collection riêng cho từng kiểu dữ liệu.

### 6.3 DBMS_SQL không tự mô tả bind placeholders

DESCRIBE_COLUMNS mô tả các cột của kết quả SELECT, không phải danh sách bind variables của câu SQL. DBMS_SQL không cung cấp một thao tác tổng quát để hỏi: “Câu SQL tùy ý này có những placeholder nào, kiểu mong đợi của mỗi placeholder là gì?”

Do đó, nếu số bind chưa biết trước:

1. SQL builder nên sinh SQL và bind metadata cùng lúc.
2. Metadata phải có tên placeholder, kiểu và giá trị.
3. Code duyệt metadata để bind từng biến.
4. Parse/execute sẽ phát hiện lỗi bind thiếu hoặc kiểu không tương thích.

Không nên cố tìm placeholder bằng một regex đơn giản trên SQL text. Dấu hai chấm có thể xuất hiện trong string literal, comment, quoted identifier hoặc cú pháp khác; một bộ phân tích SQL tổng quát cần hiểu cú pháp thực sự.

### 6.4 Placeholder lặp lại

Nếu cùng placeholder name xuất hiện nhiều lần trong SQL, hãy bind theo tên một cách nhất quán. Không tự tạo bind metadata trùng tên với các giá trị khác nhau. Một placeholder đại diện cho một giá trị bind; nếu cần hai giá trị độc lập, dùng hai tên riêng.

### 6.5 Bind NULL có kiểu

Khi bind NULL, cần dùng biến PL/SQL có kiểu mong muốn:

~~~sql
DECLARE
    l_number_value NUMBER := NULL;
BEGIN
    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':p_amount',
        l_number_value
    );
END;
/
~~~

Biến có kiểu NUMBER giúp chọn overload bind NUMBER. Tránh biểu thức NULL không có kiểu rõ ràng khi overload bị mơ hồ.

## 7. Phân biệt bind value và SQL identifier

Bind variable thay thế giá trị dữ liệu, không thay thế tên bảng, tên cột, từ khóa hoặc hướng sắp xếp.

Hợp lệ:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE department_id = :dept_id;
~~~

Không thể dùng bind placeholder để thay tên bảng:

~~~sql
SELECT *
FROM :table_name;
~~~

Nếu tên bảng/cột phải thay đổi theo runtime, cần xây dựng identifier từ danh sách cho phép và kiểm tra/quote đúng cách. Có thể dùng DBMS_ASSERT như SIMPLE_SQL_NAME hoặc SQL_OBJECT_NAME theo ngữ cảnh, nhưng DBMS_ASSERT không thay thế whitelist và kiểm tra quyền nghiệp vụ.

Ví dụ:

~~~sql
DECLARE
    l_table_name VARCHAR2(128) := 'EMPLOYEES';
    l_sql        VARCHAR2(1000);
    l_cursor     INTEGER;
BEGIN
    l_table_name := DBMS_ASSERT.SIMPLE_SQL_NAME(l_table_name);

    l_sql := 'SELECT COUNT(*) FROM ' || l_table_name ||
             ' WHERE department_id = :dept';

    l_cursor := DBMS_SQL.OPEN_CURSOR;
    DBMS_SQL.PARSE(l_cursor, l_sql, DBMS_SQL.NATIVE);
    DBMS_SQL.BIND_VARIABLE(l_cursor, ':dept', 10);
    -- Define/fetch hoặc execute theo loại statement.
    DBMS_SQL.CLOSE_CURSOR(l_cursor);
END;
/
~~~

Ví dụ chỉ minh họa kiểm tra identifier và bind value; trong ứng dụng thật, bảng cần nằm trong allowlist nghiệp vụ và phải được xử lý theo quyền của user/session.

Không nối trực tiếp input người dùng vào SQL text. Bind values giúp tránh SQL injection ở vị trí giá trị; identifier động cần một chính sách kiểm soát riêng.

## 8. DBMS_SQL cho DML có số bind động

Với DML, không cần DESCRIBE_COLUMNS hoặc DEFINE_COLUMN nếu câu lệnh không trả result set. Quy trình là OPEN_CURSOR, PARSE, bind từng placeholder, EXECUTE, rồi CLOSE_CURSOR.

~~~sql
DECLARE
    l_cursor INTEGER;
    l_rows   INTEGER;
    l_dept   NUMBER := 20;
    l_raise  NUMBER := 500;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        'UPDATE employees
            SET salary = salary + :raise_amount
          WHERE department_id = :department_id',
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(l_cursor, ':raise_amount', l_raise);
    DBMS_SQL.BIND_VARIABLE(l_cursor, ':department_id', l_dept);

    l_rows := DBMS_SQL.EXECUTE(l_cursor);
    DBMS_OUTPUT.PUT_LINE('Updated rows=' || l_rows);

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(l_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

Nếu số bind thay đổi, phần bind có thể nằm trong vòng lặp metadata. Việc DML thành công không có nghĩa tự động COMMIT; transaction vẫn thuộc quyền kiểm soát của caller hoặc procedure theo hợp đồng đã thiết kế.

## 9. DML có RETURNING và output bind

DBMS_SQL có thể bind biến nhận output cho một số dạng statement có bind OUT/IN OUT. Sau khi execute, dùng VARIABLE_VALUE để lấy giá trị output theo placeholder đã bind. Với chuỗi output, cần chọn overload và kích thước phù hợp.

Ví dụ khái niệm:

~~~sql
DECLARE
    l_cursor INTEGER;
    l_id     NUMBER;
    l_rows   INTEGER;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        'BEGIN :out_id := 100; END;',
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':out_id',
        l_id
    );

    l_rows := DBMS_SQL.EXECUTE(l_cursor);

    DBMS_SQL.VARIABLE_VALUE(
        l_cursor,
        ':out_id',
        l_id
    );

    DBMS_OUTPUT.PUT_LINE('Output id=' || l_id);
    DBMS_SQL.CLOSE_CURSOR(l_cursor);
END;
/
~~~

Đây là ví dụ minh họa bind OUT cho anonymous PL/SQL block. Với DML RETURNING INTO, cú pháp dynamic SQL và cách khai báo bind cần theo dạng statement cụ thể; không giả định mọi placeholder đều là IN. Đọc package documentation cho overload và giới hạn OUT/IN OUT của kiểu dữ liệu cần dùng.

## 10. Chuyển đổi giữa DBMS_SQL và SYS_REFCURSOR

Đôi khi một tầng cần mô tả cột động bằng DBMS_SQL, nhưng tầng khác muốn nhận SYS_REFCURSOR để fetch theo API NDS. Oracle cung cấp:

- DBMS_SQL.TO_REFCURSOR: chuyển cursor number đang mở thành SYS_REFCURSOR.
- DBMS_SQL.TO_CURSOR_NUMBER: chuyển SYS_REFCURSOR sang cursor number DBMS_SQL.

Ví dụ chuyển cursor sau khi parse/prepare:

~~~sql
DECLARE
    l_cursor INTEGER;
    l_refcur SYS_REFCURSOR;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;
    DBMS_SQL.PARSE(
        l_cursor,
        'SELECT employee_id, last_name FROM employees',
        DBMS_SQL.NATIVE
    );

    l_refcur := DBMS_SQL.TO_REFCURSOR(l_cursor);
    -- Quyền sở hữu cursor đã chuyển sang l_refcur.
    -- Fetch qua SYS_REFCURSOR ở tầng nhận.
    CLOSE l_refcur;
END;
/
~~~

Sau TO_REFCURSOR, không tiếp tục dùng cursor number cũ như thể DBMS_SQL còn sở hữu cursor. Cursor cần được đóng qua ref cursor. Chuyển đổi hữu ích khi cần kết nối API, nhưng không làm biến mất yêu cầu phải biết cách tiêu thụ result metadata.

## 11. Xử lý cursor và exception an toàn

DBMS_SQL là API cấp thấp hơn NDS nên cần quản lý vòng đời cursor cẩn thận.

### 11.1 Luôn đóng cursor trong cả đường thành công và lỗi

Mẫu cơ bản:

~~~sql
DECLARE
    l_cursor INTEGER;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    -- PARSE, BIND, DEFINE, EXECUTE, FETCH...

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(l_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        RAISE;
END;
/
~~~

IS_OPEN cho phép kiểm tra cursor còn mở trước khi đóng trong exception handler. Không nuốt lỗi gốc chỉ vì việc đóng cursor gặp lỗi phụ; với hệ thống production, có thể ghi nhận lỗi cleanup nhưng vẫn phải giữ nguyên exception chính.

### 11.2 Không dùng lại cursor number sau khi đóng

Sau CLOSE_CURSOR, handle không còn hợp lệ. Mở cursor mới bằng OPEN_CURSOR nếu cần thực hiện statement tiếp theo.

### 11.3 Đừng giữ cursor lâu hơn cần thiết

Fetch xong phải đóng. Nếu cần trả kết quả cho tầng gọi, cân nhắc trả SYS_REFCURSOR hoặc chuyển đổi bằng TO_REFCURSOR với quyền sở hữu được quy định rõ.

### 11.4 Kiểm soát lỗi parse và bind

Các lỗi có thể xảy ra:

- SQL syntax invalid.
- Object hoặc column không tồn tại.
- Thiếu bind variable.
- Bind name không khớp.
- Kiểu bind không tương thích.
- Kiểu result không được code dispatch hỗ trợ.
- Quyền truy cập đối tượng không đủ.

Nên báo rõ SQL code, vị trí cột/bind và bước lỗi, nhưng không ghi toàn bộ SQL hoặc bind values nhạy cảm vào log.

## 12. DBMS_SQL và bảo mật

Dynamic SQL có rủi ro SQL injection nếu ứng dụng nối dữ liệu không tin cậy vào SQL text.

Quy tắc:

1. Bind tất cả giá trị dữ liệu.
2. Chỉ cho phép identifier từ allowlist đã kiểm soát.
3. Dùng DBMS_ASSERT phù hợp để kiểm tra identifier khi cần.
4. Không để người dùng tự cung cấp câu SQL tùy ý nếu chức năng không được thiết kế như một SQL console.
5. Giới hạn quyền schema thực thi; không chạy dynamic SQL bằng quyền quá rộng.
6. Ghi log request ID và câu lệnh đã chuẩn hóa theo chính sách, tránh lộ dữ liệu.
7. Kiểm soát số dòng, thời gian chạy và tài nguyên cho truy vấn do người dùng cấu hình.

DBMS_SQL là công cụ thực thi SQL động, không tự động làm SQL an toàn. BIND_VARIABLE bảo vệ giá trị ở vị trí bind; nó không bảo vệ identifier được nối vào câu SQL.

## 13. Giới hạn của DBMS_SQL và các trường hợp không nên dùng

### 13.1 Không tự khám phá bind metadata tổng quát

DBMS_SQL mô tả output columns, không cung cấp một API công khai tổng quát để mô tả mọi bind placeholder của arbitrary SQL. Hãy thiết kế SQL builder sinh bind metadata cùng SQL.

### 13.2 Không dùng DBMS_SQL chỉ để tránh khai báo biến

Nếu câu SQL cố định và số cột biết trước, EXECUTE IMMEDIATE thường đơn giản hơn. DBMS_SQL thêm nhiều code quản lý cursor, define và fetch.

### 13.3 Kiểu dữ liệu đặc biệt cần xử lý riêng

LOB, LONG, object type, collection, REF, timestamp có timezone và các kiểu mở rộng cần đúng overload/API. Không giả định ví dụ VARCHAR2/NUMBER/DATE là parser tổng quát.

### 13.4 Giới hạn kích thước SQL text

Độ dài statement phụ thuộc overload và phiên bản Oracle. Nếu câu SQL lớn hơn giới hạn VARCHAR2 của interface đang dùng, kiểm tra overload CLOB/kiểu hỗ trợ trong DBMS_SQL của phiên bản đó. Không cắt chuỗi SQL thành nhiều mảnh tùy tiện rồi parse từng mảnh như các statement độc lập.

### 13.5 Parse không có nghĩa statement chắc chắn chạy thành công

Parse kiểm tra cú pháp và chuẩn bị statement, nhưng lỗi quyền, lỗi bind, constraint, dữ liệu và lỗi runtime vẫn có thể xuất hiện khi execute/fetch.

## 14. Metadata-driven SQL builder

Với ứng dụng cần số bind biến đổi, nên có một tầng tạo SQL và metadata cùng lúc thay vì cố phân tích SQL text sau khi đã sinh.

Ví dụ hợp đồng khái niệm:

| Trường metadata | Ví dụ | Mục đích |
|---|---|---|
| SQL text | SELECT ... WHERE status = :p1 AND created_at >= :p2 | Statement cần thực thi |
| Bind name | :p1 | Placeholder trong SQL |
| Data type | VARCHAR2 | Chọn overload bind |
| Value | OPEN | Giá trị dữ liệu |
| Direction | IN | IN, OUT hoặc IN OUT nếu API hỗ trợ |
| Size | 30 | Kích thước với kiểu cần độ dài |

Luồng:

~~~text
UI / API request
       |
       v
SQL builder
       |
       +----> SQL text
       |
       +----> bind metadata collection
                     |
                     v
                DBMS_SQL
                     |
                     v
             Parse / bind / execute
                     |
                     v
             Describe result columns
                     |
                     v
             Define / fetch / map result
~~~

Metadata phải được sinh từ cấu trúc truy vấn được kiểm soát. Không nhận một chuỗi SQL không tin cậy cùng một danh sách bind tùy ý rồi coi đó là an toàn.

## 15. Bài lab: SELECT có số cột thay đổi

Lab chạy trong schema thực hành. Ví dụ dùng USER_TABLES để có ba kiểu dữ liệu phổ biến và minh họa metadata runtime.

### 15.1 Chuẩn bị

~~~sql
SET SERVEROUTPUT ON
~~~

Chạy block ở phần 4. Thử thay SELECT thành:

~~~sql
SELECT table_name
FROM user_tables;
~~~

và:

~~~sql
SELECT table_name,
       num_rows,
       last_analyzed
FROM user_tables;
~~~

Số cột thay đổi từ một lên ba nhưng code DBMS_SQL vẫn lấy số cột qua DESCRIBE_COLUMNS2.

### 15.2 Thử kiểu không được hỗ trợ

Thêm một cột có kiểu không thuộc CASE trong ví dụ, chẳng hạn một biểu thức timestamp:

~~~sql
SELECT table_name,
       CAST(last_analyzed AS TIMESTAMP) AS analyzed_ts
FROM user_tables;
~~~

Code minh họa sẽ báo unsupported type code cho cột TIMESTAMP. Đây là hành vi có chủ đích: thêm nhánh DEFINE_COLUMN và COLUMN_VALUE cho TIMESTAMP trước khi hỗ trợ kiểu này.

### 15.3 Thử DML với bind

Dùng bảng lab do bạn tự tạo hoặc một bảng thử nghiệm riêng. Parse UPDATE có hai placeholder, bind hai giá trị và xem số dòng DBMS_SQL.EXECUTE trả về. Không dùng bảng nghiệp vụ hoặc câu lệnh thay đổi dữ liệu thật trong lab.

### 15.4 Kiểm tra đóng cursor khi lỗi

Cố ý truyền câu SQL sai cú pháp hoặc bind thiếu để kích hoạt exception. Xác nhận exception handler đóng cursor trước khi RAISE lại. Không bỏ handler để thử lặp nhiều lần trong session vì có thể để lại cursor mở.

## 16. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng EXECUTE IMMEDIATE cho số cột không cố định | INTO list phải phù hợp cấu trúc result | Dùng DBMS_SQL để describe/define/fetch |
| Gọi DESCRIBE_COLUMNS trước PARSE | Cursor chưa có statement được parse | PARSE SELECT trước |
| Bỏ qua DEFINE_COLUMN | Chưa khai báo biến nhận cột trước fetch | Define từng cột theo metadata |
| Dùng sai overload DEFINE_COLUMN | Kiểu biến không tương thích với SQL type | Dispatch theo COL_TYPE |
| Gọi COLUMN_VALUE trước FETCH_ROWS | Chưa có dòng hiện hành | FETCH_ROWS trước, rồi COLUMN_VALUE |
| Coi EXECUTE return là số dòng SELECT | SELECT rows được lấy bằng FETCH_ROWS | Dùng FETCH_ROWS để fetch |
| Thiếu bind variable | Chưa bind đủ placeholder | Sinh bind metadata và bind toàn bộ |
| Cố mô tả bind bằng DESCRIBE_COLUMNS | API này chỉ mô tả output columns | Caller cung cấp bind metadata |
| Nối value vào SQL | SQL injection và hard parse | Dùng BIND_VARIABLE |
| Dùng bind cho tên bảng/cột | Bind chỉ thay giá trị | Allowlist và kiểm tra identifier |
| Không đóng cursor | Rò rỉ tài nguyên session | CLOSE_CURSOR trong cả success/error |
| Chuyển mọi kiểu thành VARCHAR2 | Mất precision/format hoặc không hỗ trợ LOB | Dùng đúng kiểu và overload |
| Dùng COL_MAX_LEN làm kích thước mọi biến | Không phù hợp mọi kiểu/charset/LOB | Xử lý theo datatype |
| Tự parse bind bằng regex đơn giản | Có thể nhầm string/comment/identifier | SQL builder phát metadata cùng SQL |

## 17. Checklist triển khai

Trước khi dùng DBMS_SQL trong ứng dụng, xác định:

1. Vì sao NDS không đáp ứng được cấu trúc runtime?
2. Câu SQL có phải SELECT hay DML/PLSQL block?
3. Nếu là SELECT, code có DESCRIBE_COLUMNS sau PARSE không?
4. Có dispatch DEFINE_COLUMN theo COL_TYPE không?
5. Các kiểu dữ liệu được hỗ trợ đã được giới hạn và tài liệu hóa chưa?
6. Có xử lý NULL, LOB, LONG và kiểu đặc biệt phù hợp không?
7. Số bind, tên, kiểu và giá trị có đến từ metadata đáng tin cậy không?
8. Có bind tất cả giá trị thay vì nối chuỗi không?
9. Identifier động có allowlist/DBMS_ASSERT phù hợp không?
10. Có phân biệt EXECUTE với FETCH_ROWS cho SELECT không?
11. Có đóng cursor trong cả success và exception path không?
12. Có giới hạn SQL text, số dòng, thời gian chạy và quyền thực thi không?
13. Có log lỗi đủ để điều tra nhưng không lộ bind value nhạy cảm không?
14. Nếu trả cursor cho tầng khác, quyền sở hữu và cách đóng cursor có rõ không?
15. Có kiểm thử nhiều kiểu cột, số cột, số bind và lỗi runtime không?

## 18. Tổng kết

DBMS_SQL là API PL/SQL dành cho những tình huống dynamic SQL cần thao tác ở mức cursor khi cấu trúc câu lệnh chỉ được biết lúc runtime.

- OPEN_CURSOR mở cursor number; PARSE phân tích câu lệnh.
- DESCRIBE_COLUMNS/DESCRIBE_COLUMNS2 mô tả số lượng và metadata của result columns.
- DEFINE_COLUMN khai báo biến nhận cho từng cột theo datatype.
- EXECUTE chạy statement; SELECT cần FETCH_ROWS để lấy từng dòng.
- COLUMN_VALUE lấy giá trị cột theo vị trí và kiểu biến đã define.
- BIND_VARIABLE bind giá trị theo placeholder; có thể lặp trong vòng lặp khi caller cung cấp bind metadata.
- DBMS_SQL không có API tổng quát để tự mô tả mọi bind placeholder và kiểu mong đợi trong SQL tùy ý.
- Bind values không thay thế identifier; tên bảng/cột động phải được kiểm soát riêng.
- Cursor phải được đóng trên mọi đường thực thi, kể cả exception.

Nếu số cột và bind đã biết, ưu tiên Native Dynamic SQL vì code gọn hơn. Khi ứng dụng cần xử lý result metadata hoặc bind list thực sự biến đổi theo runtime, DBMS_SQL cung cấp các bước tường minh để parse, describe, define, bind, execute và fetch một cách có kiểm soát.
