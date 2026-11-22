# Biến, hằng, phạm vi, khối lồng nhau và che khuất tên trong PL/SQL

PL/SQL cho phép khai báo biến và hằng để lưu giá trị trong khi xử lý nghiệp vụ. Một biến có thể được dùng trong biểu thức, điều kiện, vòng lặp, câu lệnh SQL và lời gọi thủ tục. Tuy nhiên, biến không tồn tại ở mọi nơi trong chương trình: nó chỉ có thể được truy cập trong **phạm vi (scope)** mà nó được khai báo và các khối con nằm bên trong phạm vi đó.

Khi một khối PL/SQL lồng nhau khai báo biến cùng tên với biến ở khối bên ngoài, tên ở khối trong sẽ **che khuất (shadow)** tên bên ngoài trong phạm vi khối con. Nếu không hiểu quy tắc này, chương trình có thể đọc hoặc cập nhật nhầm biến dù cú pháp hoàn toàn hợp lệ. Tình huống tương tự còn xuất hiện khi tên biến trùng với tên cột trong câu SQL nhúng.

Bài học thuộc chủ đề **PL/SQL cơ bản** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Cách khai báo, khởi tạo và sử dụng biến trong PL/SQL.
- Hằng số với từ khóa CONSTANT.
- Kiểu dữ liệu scalar, anchored type %TYPE và record %ROWTYPE.
- Scope, visibility và lifetime của biến.
- Khối lồng nhau, block label và cách truy cập biến ở khối cha.
- Name shadowing giữa biến, tham số, biến package và cột SQL.
- Quy ước đặt tên và bài thực hành có thể chạy trong SQL Developer/SQL*Plus.

## 1. Cấu trúc khối PL/SQL và vị trí khai báo

Một block PL/SQL có tối đa ba phần:

~~~sql
DECLARE
    -- Phần khai báo: biến, hằng, kiểu, cursor, exception...
BEGIN
    -- Phần thực thi: câu lệnh PL/SQL
EXCEPTION
    -- Phần xử lý lỗi (tùy chọn)
END;
/
~~~

- `DECLARE` là phần tùy chọn đối với anonymous block. Với stored procedure/function/package, phần khai báo nằm trong cú pháp tương ứng.
- `BEGIN` và `END` bao quanh phần thực thi; phần này là bắt buộc.
- `EXCEPTION` là phần tùy chọn để xử lý lỗi phát sinh trong block.
- Dấu `/` trên một dòng riêng là lệnh của SQL*Plus/SQL Developer script để gửi block đã nhập tới database; nó không phải câu lệnh PL/SQL.

Biến và hằng được khai báo trong phần khai báo, trước BEGIN. Không thể khai báo biến thông thường ở giữa các câu lệnh thực thi như trong một số ngôn ngữ lập trình khác.

Ví dụ anonymous block:

~~~sql
SET SERVEROUTPUT ON;

DECLARE
    l_customer_id NUMBER := 100;
    l_total       NUMBER(12,2) := 0;
BEGIN
    l_total := 1250.50;
    DBMS_OUTPUT.PUT_LINE(
        'Customer ' || l_customer_id ||
        ' total = ' || TO_CHAR(l_total)
    );
END;
/
~~~

`l_customer_id` và `l_total` được khai báo trong block nên chỉ dùng được trong block này và các block con của nó.

## 2. Khai báo biến

Cú pháp tổng quát:

~~~sql
variable_name [CONSTANT] datatype [NOT NULL]
    [ { := | DEFAULT } expression ];
~~~

Với biến thông thường, bỏ từ khóa CONSTANT:

~~~sql
DECLARE
    l_count       PLS_INTEGER;
    l_unit_price  NUMBER(10,2);
    l_description VARCHAR2(200);
    l_created_at  DATE := SYSDATE;
BEGIN
    l_count := 3;
    l_unit_price := 19.95;
    l_description := 'USB-C adapter';
END;
/
~~~

### Gán giá trị ban đầu

Có thể khởi tạo biến ngay khi khai báo bằng `:=` hoặc `DEFAULT`:

~~~sql
DECLARE
    l_attempts PLS_INTEGER := 0;
    l_status   VARCHAR2(20) DEFAULT 'NEW';
BEGIN
    NULL;
END;
/
~~~

Nếu không có biểu thức khởi tạo, biến scalar thông thường có giá trị ban đầu là NULL. Đừng nhầm giá trị mặc định NULL với số 0, chuỗi rỗng hoặc FALSE.

### Gán giá trị sau khi khai báo

Trong phần thực thi, dùng toán tử gán `:=`:

~~~sql
DECLARE
    l_quantity PLS_INTEGER;
BEGIN
    l_quantity := 5;
    l_quantity := l_quantity + 2;
    DBMS_OUTPUT.PUT_LINE(l_quantity); -- 7
END;
/
~~~

Dấu `=` thường dùng trong phép so sánh, còn `:=` dùng để gán giá trị cho biến PL/SQL.

### Biến NOT NULL

Có thể khai báo biến không cho phép nhận NULL bằng `NOT NULL`, nhưng phải khởi tạo giá trị khác NULL:

~~~sql
DECLARE
    l_customer_name VARCHAR2(100) NOT NULL := 'An';
BEGIN
    l_customer_name := 'Binh';
    -- l_customer_name := NULL; -- gây VALUE_ERROR
END;
/
~~~

Nếu khai báo NOT NULL mà không có giá trị khởi tạo, PL/SQL báo lỗi khi biên dịch. Nếu trong lúc chạy cố gán NULL, phát sinh VALUE_ERROR.

## 3. Kiểu dữ liệu của biến

PL/SQL hỗ trợ kiểu dữ liệu SQL và các kiểu dành riêng cho PL/SQL. Chọn kiểu theo miền giá trị và cách dữ liệu được sử dụng.

### Kiểu scalar thường dùng

| Kiểu | Công dụng | Ví dụ |
| --- | --- | --- |
| NUMBER(p,s) | Số nguyên hoặc thập phân | NUMBER(12,2) |
| PLS_INTEGER | Số nguyên có dấu, phù hợp phép tính số nguyên trong PL/SQL | PLS_INTEGER |
| BINARY_INTEGER | Kiểu số nguyên PL/SQL tương thích | BINARY_INTEGER |
| VARCHAR2(n) | Chuỗi ký tự có độ dài biến đổi | VARCHAR2(100) |
| CHAR(n) | Chuỗi ký tự có độ dài cố định | CHAR(2) |
| DATE | Ngày và thời gian tới giây | DATE |
| TIMESTAMP | Ngày giờ có phần giây lẻ | TIMESTAMP |
| BOOLEAN | TRUE, FALSE hoặc NULL trong PL/SQL | BOOLEAN |
| CLOB / BLOB | Dữ liệu ký tự lớn / nhị phân lớn | CLOB |

BOOLEAN là kiểu PL/SQL, không thể dùng trực tiếp như một cột SQL BOOLEAN trên nhiều phiên bản Oracle truyền thống. Oracle Database 23ai bổ sung kiểu SQL BOOLEAN; khả năng dùng trong SQL phụ thuộc phiên bản. Trong bài học PL/SQL cơ bản, hãy coi BOOLEAN là kiểu biểu thức/biến PL/SQL trừ khi đã xác nhận phiên bản và kiểu SQL đang dùng.

Ví dụ:

~~~sql
DECLARE
    l_amount    NUMBER(12,2) := 150.75;
    l_count     PLS_INTEGER := 4;
    l_name      VARCHAR2(80) := 'Oracle';
    l_is_active BOOLEAN := TRUE;
    l_started   TIMESTAMP := SYSTIMESTAMP;
BEGIN
    IF l_is_active THEN
        DBMS_OUTPUT.PUT_LINE(l_name || ': ' || l_count);
    END IF;
END;
/
~~~

### NUMBER và PLS_INTEGER

- Dùng NUMBER khi cần số thập phân, tiền tệ hoặc độ chính xác số theo kiểu SQL.
- Dùng PLS_INTEGER cho bộ đếm và phép tính số nguyên trong PL/SQL khi miền giá trị phù hợp.
- PLS_INTEGER có giới hạn số nguyên 32-bit; tràn miền có thể gây lỗi.
- Không dùng NUMBER cho mọi biến chỉ vì nó phổ biến; chọn kiểu có ý nghĩa và phù hợp dữ liệu.

### BOOLEAN có ba trạng thái logic

BOOLEAN có thể nhận TRUE, FALSE hoặc NULL. Vì vậy điều kiện IF chỉ chạy nhánh THEN khi biểu thức là TRUE:

~~~sql
DECLARE
    l_is_valid BOOLEAN;
BEGIN
    IF l_is_valid THEN
        DBMS_OUTPUT.PUT_LINE('Valid');
    ELSIF l_is_valid = FALSE THEN
        DBMS_OUTPUT.PUT_LINE('Invalid');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Unknown');
    END IF;
END;
/
~~~

Khi l_is_valid là NULL, hai phép so sánh với TRUE/FALSE không cho kết quả TRUE; chương trình đi vào ELSE. Đây là logic ba giá trị, không nên xem NULL như FALSE trong mọi biểu thức.

## 4. Anchored types: %TYPE và %ROWTYPE

Khi biến lưu dữ liệu lấy từ bảng, khai báo kiểu độc lập có thể bị lệch khi cấu trúc cột thay đổi. PL/SQL cung cấp anchored declaration để biến bám theo kiểu dữ liệu của cột hoặc cấu trúc hàng.

### %TYPE: lấy kiểu từ một cột hoặc biến khác

Cú pháp:

~~~sql
variable_name table_name.column_name%TYPE;
~~~

Ví dụ:

~~~sql
DECLARE
    l_employee_id employees.employee_id%TYPE;
    l_salary      employees.salary%TYPE;
    l_new_salary  l_salary%TYPE;
BEGIN
    l_employee_id := 100;
    l_salary := 5000;
    l_new_salary := l_salary * 1.10;
END;
/
~~~

Nếu kiểu hoặc độ chính xác của cột EMPLOYEES.SALARY thay đổi, biến khai báo theo %TYPE tự bám theo định nghĩa cột khi chương trình được biên dịch lại.

%TYPE cũng có thể tham chiếu biến đã khai báo:

~~~sql
DECLARE
    l_base_amount NUMBER(12,2) := 100;
    l_tax_amount  l_base_amount%TYPE;
BEGIN
    l_tax_amount := l_base_amount * 0.08;
END;
/
~~~

Lưu ý: %TYPE lấy kiểu dữ liệu và thuộc tính độ dài/precision liên quan, nhưng không tự kế thừa ràng buộc NOT NULL của cột bảng. Một biến khai báo employees.employee_name%TYPE vẫn có thể nhận NULL nếu bản thân biến không khai báo NOT NULL.

### %ROWTYPE: khai báo record theo một hàng

%ROWTYPE tạo một record có các field tương ứng với các cột của bảng, view hoặc cursor:

~~~sql
DECLARE
    l_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(
        l_employee.employee_id || ': ' ||
        l_employee.first_name || ' ' ||
        l_employee.last_name
    );
END;
/
~~~

Record có field truy cập bằng dấu chấm: `l_employee.employee_id`, `l_employee.salary`. Tên và kiểu field theo cấu trúc nguồn được tham chiếu.

SELECT * INTO record%ROWTYPE thuận tiện khi lấy toàn bộ hàng. Nếu chỉ chọn một số cột, cần INTO các biến/record có cấu trúc phù hợp với danh sách select item; không thể tùy ý SELECT hai cột rồi INTO record toàn hàng của bảng.

### %TYPE và %ROWTYPE khác nhau

| Đặc điểm | %TYPE | %ROWTYPE |
| --- | --- | --- |
| Mục tiêu | Khai báo một biến theo kiểu của cột/biến | Khai báo record gồm các field theo hàng |
| Truy cập | Dùng trực tiếp tên biến | Dùng record.field |
| Nguồn tham chiếu | Cột hoặc biến PL/SQL | Bảng, view hoặc cursor |
| Phù hợp | ID, số tiền, ngày, tên đơn lẻ | Lấy/xử lý nhiều cột của một hàng |

## 5. Hằng số với CONSTANT

Hằng số là tên đại diện cho giá trị không được gán lại sau khi khai báo. Dùng CONSTANT để thể hiện các giá trị cấu hình, ngưỡng, tỷ lệ hoặc mã cố định trong phạm vi block.

Cú pháp:

~~~sql
constant_name CONSTANT datatype [NOT NULL] := expression;
~~~

Giá trị khởi tạo là bắt buộc:

~~~sql
DECLARE
    c_tax_rate   CONSTANT NUMBER(5,4) := 0.0800;
    c_max_retries CONSTANT PLS_INTEGER := 3;
    c_app_name  CONSTANT VARCHAR2(30) := 'OrderService';
BEGIN
    DBMS_OUTPUT.PUT_LINE(c_app_name);
    DBMS_OUTPUT.PUT_LINE(c_tax_rate);
END;
/
~~~

Không thể gán lại hằng số:

~~~sql
DECLARE
    c_limit CONSTANT PLS_INTEGER := 10;
BEGIN
    -- c_limit := 20; -- lỗi: constant cannot be modified
    NULL;
END;
/
~~~

### Khởi tạo hằng bằng biểu thức

Giá trị khởi tạo có thể là literal hoặc biểu thức hợp lệ:

~~~sql
DECLARE
    c_started_at CONSTANT TIMESTAMP := SYSTIMESTAMP;
    c_today      CONSTANT DATE := TRUNC(SYSDATE);
BEGIN
    DBMS_OUTPUT.PUT_LINE(TO_CHAR(c_today, 'YYYY-MM-DD'));
END;
/
~~~

Biểu thức được đánh giá khi block được thực thi/khởi tạo. Với hằng dùng SYSDATE, giá trị là thời điểm khởi tạo block đó, không phải một giá trị bất biến xuyên suốt mọi lần gọi chương trình.

### CONSTANT và NOT NULL

Hằng số phải có giá trị khởi tạo; có thể kết hợp NOT NULL để thể hiện rõ ý định:

~~~sql
DECLARE
    c_region CONSTANT VARCHAR2(10) NOT NULL := 'APAC';
BEGIN
    NULL;
END;
/
~~~

Hằng số giảm lỗi do sửa nhầm giá trị và giúp người đọc phân biệt cấu hình cố định với trạng thái thay đổi. Tuy nhiên, không nên khai báo hằng cục bộ cho mọi literal nhỏ; hãy dùng tên khi giá trị có ý nghĩa nghiệp vụ hoặc được dùng lặp lại.

## 6. Phạm vi (scope), khả năng nhìn thấy (visibility) và thời gian sống (lifetime)

Ba khái niệm liên quan nhưng không giống nhau:

- **Scope:** vùng mã nguồn mà tên được định nghĩa và có thể được tham chiếu theo quy tắc ngôn ngữ.
- **Visibility:** tên có đang nhìn thấy được tại vị trí hiện tại hay bị một khai báo gần hơn che khuất.
- **Lifetime:** khoảng thời gian giá trị của biến tồn tại trong bộ nhớ/phiên làm việc.

Trong PL/SQL, biến khai báo trong block có lexical scope: block đó và các block con bên trong có thể tham chiếu biến; block bên ngoài không thể truy cập biến chỉ được khai báo trong block con.

Ví dụ:

~~~sql
DECLARE
    l_outer_value NUMBER := 10;
BEGIN
    DECLARE
        l_inner_value NUMBER := 20;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(l_outer_value); -- nhìn thấy biến ngoài
        DBMS_OUTPUT.PUT_LINE(l_inner_value); -- biến của block trong
    END;

    DBMS_OUTPUT.PUT_LINE(l_outer_value); -- vẫn nhìn thấy
    -- l_inner_value không còn trong scope tại đây.
END;
/
~~~

Biến l_inner_value chỉ có scope trong block lồng. Sau END của block đó, mã ở block ngoài không thể tham chiếu tên này.

### Scope là lexical, không phải theo thứ tự gọi

Một block con nhìn thấy khai báo của block cha vì block con được viết bên trong phạm vi đó. Một thủ tục được khai báo ở nơi khác không tự động nhìn thấy biến local của block gọi nó chỉ vì thủ tục được gọi từ block đó. Muốn truyền dữ liệu, dùng tham số; muốn chia sẻ trạng thái lâu dài hơn, có thể dùng package variable hoặc cơ chế lưu trữ phù hợp.

### Lifetime của local variable

Biến local được tạo khi block/subprogram tương ứng bắt đầu hoạt động và không còn được dùng sau khi lần thực thi đó kết thúc. Mỗi lần gọi subprogram thông thường có trạng thái local riêng cho lần gọi đó.

Biến local không phải vùng lưu trữ bền vững. Muốn giữ dữ liệu qua nhiều lần gọi hoặc qua session, cần chọn cơ chế khác như package state (trong session), bảng, collection được quản lý phù hợp hoặc lưu trữ ngoài.

## 7. Khối lồng nhau và khả năng truy cập biến

Một block có thể chứa block khác trong phần thực thi. Block con nhìn thấy biến và hằng được khai báo trong block cha, miễn là tên đó không bị khai báo khác che khuất. Block cha không nhìn thấy biến chỉ được khai báo trong block con.

~~~sql
SET SERVEROUTPUT ON;

DECLARE
    l_outer_value NUMBER := 10;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer before: ' || l_outer_value);

    DECLARE
        l_inner_value NUMBER := 20;
    BEGIN
        DBMS_OUTPUT.PUT_LINE('Outer from inner: ' || l_outer_value);
        DBMS_OUTPUT.PUT_LINE('Inner value: ' || l_inner_value);
    END;

    DBMS_OUTPUT.PUT_LINE('Outer after: ' || l_outer_value);
    -- l_inner_value không thể được tham chiếu ở đây.
END;
/
~~~

Block con có thể đọc biến ngoài. Nó cũng có thể gán lại biến ngoài nếu biến đó không bị che khuất:

~~~sql
DECLARE
    l_total NUMBER := 100;
BEGIN
    DECLARE
        l_tax NUMBER := 8;
    BEGIN
        l_total := l_total + l_tax;
    END;

    DBMS_OUTPUT.PUT_LINE(l_total); -- 108
END;
/
~~~

Block con không tạo một bản sao tự động của biến ngoài. Khi tham chiếu đúng tên biến ngoài, chương trình đang đọc hoặc thay đổi cùng biến đã được khai báo ở block cha.

### Nhiều cấp block lồng nhau

Một block lồng sâu có thể truy cập các khai báo còn nhìn thấy ở mọi cấp cha:

~~~sql
DECLARE
    l_company VARCHAR2(30) := 'Northwind';
BEGIN
    DECLARE
        l_department VARCHAR2(30) := 'Sales';
    BEGIN
        DECLARE
            l_employee VARCHAR2(30) := 'Mai';
        BEGIN
            DBMS_OUTPUT.PUT_LINE(
                l_company || '/' || l_department || '/' || l_employee
            );
        END;
    END;
END;
/
~~~

Khi block con kết thúc, biến cục bộ của block đó ra khỏi scope. Các biến ở block cha tiếp tục tồn tại cho tới khi block cha kết thúc.

## 8. Che khuất tên (name shadowing)

**Shadowing** xảy ra khi một khai báo ở phạm vi trong có cùng tên với một khai báo ở phạm vi ngoài. Trong block con, tên không định danh sẽ trỏ tới khai báo gần nhất trong phạm vi hiện tại; khai báo ngoài bị che khuất tại vị trí đó.

Ví dụ:

~~~sql
SET SERVEROUTPUT ON;

DECLARE
    l_status VARCHAR2(20) := 'OUTER';
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_status); -- OUTER

    DECLARE
        l_status VARCHAR2(20) := 'INNER';
    BEGIN
        DBMS_OUTPUT.PUT_LINE(l_status); -- INNER
    END;

    DBMS_OUTPUT.PUT_LINE(l_status); -- OUTER
END;
/
~~~

Khai báo l_status bên trong không ghi đè giá trị của l_status bên ngoài. Nó tạo một biến khác, có scope riêng, và che khuất tên ngoài chỉ trong block con.

### Shadowing biến và hằng

Quy tắc tên gần nhất cũng áp dụng nếu tên ngoài là hằng:

~~~sql
DECLARE
    c_limit CONSTANT PLS_INTEGER := 10;
BEGIN
    DECLARE
        c_limit CONSTANT PLS_INTEGER := 3;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(c_limit); -- 3
    END;

    DBMS_OUTPUT.PUT_LINE(c_limit); -- 10
END;
/
~~~

Không nên lạm dụng cùng tên ở nhiều cấp. Dù hợp lệ, shadowing khiến người đọc khó biết biểu thức đang dùng giá trị nào, đặc biệt khi block dài hoặc có nhiều câu SQL.

### Tên ở block trong có thể che khuất tên ở nhiều cấp ngoài

~~~sql
DECLARE
    l_code NUMBER := 1;
BEGIN
    DECLARE
        l_code NUMBER := 2;
    BEGIN
        DECLARE
            l_code NUMBER := 3;
        BEGIN
            DBMS_OUTPUT.PUT_LINE(l_code); -- 3
        END;
    END;
END;
/
~~~

Ở vị trí sâu nhất, tên l_code không định danh tham chiếu biến gần nhất (giá trị 3). Hai khai báo ngoài vẫn tồn tại nhưng bị che khuất tại vị trí đó.

## 9. Block label: truy cập biến bị che khuất

Có thể đặt nhãn cho block bằng cú pháp `<<label_name>>`. Nhãn cho phép định danh block và dùng làm qualifier để tham chiếu biến ở block ngoài ngay cả khi block trong khai báo biến cùng tên.

~~~sql
SET SERVEROUTPUT ON;

<<outer_block>>
DECLARE
    l_count PLS_INTEGER := 100;
BEGIN
    <<inner_block>>
    DECLARE
        l_count PLS_INTEGER := 5;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(l_count);              -- 5
        DBMS_OUTPUT.PUT_LINE(outer_block.l_count);  -- 100

        outer_block.l_count := outer_block.l_count + l_count;
    END inner_block;

    DBMS_OUTPUT.PUT_LINE(l_count); -- 105
END outer_block;
/
~~~

Trong block inner_block:

- `l_count` tham chiếu biến được khai báo trong block trong.
- `outer_block.l_count` tham chiếu biến ở block có nhãn outer_block.
- Phép gán cuối cập nhật biến ngoài, cộng với giá trị biến trong.

Block label cũng có thể giúp phân biệt tên trong nhiều cấp lồng nhau. Tên label phải được khai báo ở đầu block và có thể ghi lại sau END để làm rõ block kết thúc.

### Label không tạo biến mới

Nhãn chỉ định danh block; nó không tạo một namespace độc lập cho tất cả tên và cũng không kéo dài lifetime của biến. Biến vẫn thuộc block khai báo nó và không thể truy cập sau khi block đó kết thúc.

### Khi nào nên dùng label qualifier?

- Khi cố ý dùng cùng tên ở block trong và cần truy cập biến ngoài.
- Khi nhiều block lồng nhau có biến cùng tên và cần làm rõ nguồn.
- Khi cần đọc/ghi biến của block cha trong một biểu thức phức tạp.

Nếu phải dùng qualifier liên tục, cân nhắc đổi tên biến để giảm shadowing thay vì dựa vào nhiều label.

## 10. Tên biến trùng với tên cột trong SQL nhúng

PL/SQL cho phép dùng biến trong SQL statement. Tuy nhiên, tên trong câu SQL còn được phân giải theo quy tắc của SQL. Nếu một tên không định danh có thể là cả tên cột lẫn tên biến PL/SQL, câu lệnh trở nên mơ hồ với người đọc và có thể được hiểu theo hướng không mong muốn. Trong SQL scope, tên cột có thể được phân giải như cột của bảng thay vì biến mà lập trình viên định dùng.

Ví dụ dễ gây nhầm:

~~~sql
DECLARE
    employee_id NUMBER := 100;
    l_count     PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM employees
    WHERE employee_id = employee_id;
END;
/
~~~

Điều kiện hai vế có thể được hiểu là so sánh cột EMPLOYEE_ID với chính cột EMPLOYEE_ID, thay vì so sánh cột với biến có giá trị 100. Đây là lỗi logic nguy hiểm vì chương trình có thể chạy mà không báo lỗi cú pháp.

### Đặt tên biến khác tên cột

Giải pháp dễ đọc nhất là dùng prefix nhất quán cho biến PL/SQL và alias cho bảng:

~~~sql
DECLARE
    l_employee_id employees.employee_id%TYPE := 100;
    l_raise_pct   NUMBER := 0.05;
BEGIN
    UPDATE employees e
    SET salary = salary * (1 + l_raise_pct)
    WHERE e.employee_id = l_employee_id;
END;
/
~~~

Ở đây:

- `e.employee_id` là cột của bảng EMPLOYEES.
- `l_employee_id` là biến PL/SQL.
- `l_raise_pct` là biến PL/SQL dùng trong biểu thức SET.

Không đặt tên biến trùng tên cột nếu không có lý do rõ ràng.

### Dùng block label để định danh biến trong SQL

Khi cần giữ tên biến trùng cột, block label có thể làm rõ tham chiếu tới biến:

~~~sql
<<main_block>>
DECLARE
    employee_id employees.employee_id%TYPE := 100;
BEGIN
    UPDATE employees e
    SET salary = salary + 100
    WHERE e.employee_id = main_block.employee_id;
END main_block;
/
~~~

`main_block.employee_id` chỉ rõ biến PL/SQL ở block có nhãn main_block; `e.employee_id` chỉ rõ cột trong bảng. Cách này hợp lệ nhưng prefix biến vẫn dễ đọc và ít gây nhầm hơn.

### Luôn qualify cột trong câu SQL nhiều bảng

~~~sql
SELECT e.employee_id,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = l_employee_id;
~~~

Alias giúp tránh cột cùng tên giữa nhiều bảng và làm rõ nguồn dữ liệu. Khi có biến PL/SQL, dùng tên biến riêng biệt để không tạo xung đột.

## 11. Scope của tham số và biến package

### Tham số của procedure/function

Tham số hình thức (formal parameter) được khai báo trong phần header của procedure/function và có scope trong chương trình con đó:

~~~sql
CREATE OR REPLACE PROCEDURE print_employee (
    p_employee_id IN employees.employee_id%TYPE
) AS
    l_employee_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO l_employee_name
    FROM employees
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(l_employee_name);
END;
/
~~~

`p_employee_id` có thể được dùng trong phần khai báo/thực thi theo quy tắc PL/SQL và chỉ có ý nghĩa trong invocation của PRINT_EMPLOYEE. Biến local `l_employee_name` chỉ tồn tại trong lần gọi procedure đó.

Tham số có mode:

- IN: caller truyền giá trị vào; chương trình con không được gán lại tham số IN.
- OUT: chương trình con trả giá trị cho caller.
- IN OUT: nhận giá trị ban đầu và có thể trả giá trị đã thay đổi.

Tham số và biến local có scope theo chương trình con. Nếu block con khai báo tên giống tham số, khai báo trong có thể che khuất tham số trong phạm vi block con; tránh tình huống này bằng quy ước tên.

### Biến package

Package có thể khai báo biến ở package specification hoặc package body:

~~~sql
CREATE OR REPLACE PACKAGE app_context AS
    g_region VARCHAR2(10) := 'APAC';
    PROCEDURE set_region(p_region IN VARCHAR2);
END app_context;
/

CREATE OR REPLACE PACKAGE BODY app_context AS
    PROCEDURE set_region(p_region IN VARCHAR2) IS
    BEGIN
        g_region := p_region;
    END set_region;
END app_context;
/
~~~

Biến khai báo trong package specification là public và có thể được truy cập bằng `app_context.g_region` từ chương trình được cấp quyền. Biến chỉ khai báo trong package body là private, chỉ dùng bên trong package body.

Package variable không phải biến global dùng chung cho mọi session. Package state thông thường tồn tại trong trạng thái package của từng database session:

- Các lần gọi package trong cùng session có thể nhìn thấy giá trị đã thay đổi.
- Session khác có bản package state riêng.
- Session kết thúc thì package state của session đó không còn.
- Connection pool tái sử dụng session có thể giữ package state giữa các request nếu ứng dụng không reset/quản lý rõ.

Ví dụ:

~~~sql
BEGIN
    app_context.set_region('EMEA');
    DBMS_OUTPUT.PUT_LINE(app_context.g_region);
END;
/
~~~

Kết quả trong session hiện tại là EMEA. Một session khác chưa gọi SET_REGION vẫn có giá trị package state riêng theo khởi tạo ban đầu.

### Biến package và constant package

Có thể khai báo constant trong package specification để chia sẻ giá trị chỉ đọc:

~~~sql
CREATE OR REPLACE PACKAGE app_constants AS
    c_max_attempts CONSTANT PLS_INTEGER := 5;
    c_default_region CONSTANT VARCHAR2(10) := 'APAC';
END app_constants;
/
~~~

Chương trình khác có thể tham chiếu `app_constants.c_max_attempts` nếu có quyền EXECUTE package. Hằng package thể hiện cấu hình chung ở mức package, còn biến package có thể thay đổi và giữ state theo session.

## 12. Biến trong phần EXCEPTION và lỗi scope

Biến khai báo trong phần DECLARE của một block có thể được sử dụng cả trong phần BEGIN và EXCEPTION của chính block đó:

~~~sql
DECLARE
    l_employee_id NUMBER := 999999;
    l_name        VARCHAR2(100);
BEGIN
    SELECT last_name
    INTO l_name
    FROM employees
    WHERE employee_id = l_employee_id;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            'No employee: ' || l_employee_id
        );
END;
/
~~~

Nếu exception phát sinh trong block con và được xử lý ở block cha, biến chỉ khai báo trong block con không còn nằm trong scope của handler ở block cha:

~~~sql
DECLARE
    l_outer_id NUMBER := 100;
BEGIN
    DECLARE
        l_inner_message VARCHAR2(100) := 'inner work';
    BEGIN
        RAISE_APPLICATION_ERROR(-20001, 'Failure');
    END;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(l_outer_id);
        -- l_inner_message không thuộc scope của block ngoài.
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

Handler của block ngoài có thể truy cập biến của block ngoài, nhưng không thể tham chiếu biến local đã khai báo trong block con.

### Lỗi khai báo trùng trong cùng một scope

Không thể khai báo hai biến cùng tên trong cùng một declarative region:

~~~sql
DECLARE
    l_value NUMBER := 1;
    -- l_value VARCHAR2(10) := 'A'; -- khai báo trùng tên
BEGIN
    NULL;
END;
/
~~~

Shadowing chỉ xảy ra khi khai báo nằm ở phạm vi lồng bên trong; hai khai báo ngang cấp trong cùng phần khai báo sẽ gây lỗi định danh trùng.

## 13. Quy ước đặt tên để giảm shadowing

Oracle không bắt buộc prefix cho biến, tham số hoặc hằng. Tuy nhiên, quy ước nhất quán giúp phân biệt tên PL/SQL với cột SQL và giúp đọc code nhanh hơn.

Một quy ước thường dùng:

| Prefix | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `p_` | Parameter của procedure/function | `p_employee_id` |
| `l_` | Local variable | `l_total_amount` |
| `c_` | Constant | `c_tax_rate` |
| `g_` | Package variable/state | `g_current_region` |
| `r_` | Record variable | `r_employee` |
| `t_` | User-defined type/subtype | `t_currency` |

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE apply_bonus (
    p_employee_id IN employees.employee_id%TYPE,
    p_bonus       IN NUMBER
) AS
    l_current_salary employees.salary%TYPE;
    l_new_salary     employees.salary%TYPE;
    c_max_bonus      CONSTANT NUMBER := 5000;
BEGIN
    SELECT e.salary
    INTO l_current_salary
    FROM employees e
    WHERE e.employee_id = p_employee_id;

    l_new_salary := l_current_salary + LEAST(p_bonus, c_max_bonus);

    UPDATE employees e
    SET e.salary = l_new_salary
    WHERE e.employee_id = p_employee_id;
END;
/
~~~

Tên biến khác tên cột, tên tham số có prefix riêng và tên cột được qualify bằng alias. Điều này giảm rủi ro name resolution nhầm.

### Các nguyên tắc nên giữ

- Không dùng cùng một tên cho biến ngoài và biến trong nếu không có lý do rõ ràng.
- Đặt tên biến theo ý nghĩa dữ liệu, không chỉ theo kiểu như `number1` hoặc `text2`.
- Dùng prefix nhất quán cho parameter, local variable, constant và package state.
- Qualify cột bằng table alias trong SQL nhiều bảng.
- Không dùng tên biến trùng tên cột được truy vấn.
- Khi buộc phải shadow, dùng block label để truy cập biến ngoài và ghi chú mục đích.
- Không giữ trạng thái nghiệp vụ trong package variable nếu request khác có thể tái sử dụng cùng session mà không reset state.

### Tránh dùng tên dễ đụng từ khóa hoặc tên built-in

Không nên đặt biến tên như `date`, `rownum`, `level`, `user`, `count` hoặc tên hàm phổ biến. Dù một số tên có thể được dùng trong ngữ cảnh nhất định, chúng làm câu SQL/PLSQL khó đọc và dễ gây nhầm với pseudocolumn, function hoặc keyword. Dùng tên có nghĩa như `l_run_date`, `l_row_count`, `l_current_user`.

## 14. Bài thực hành tổng hợp

Thực hiện trong schema học tập có quyền CREATE TABLE và quota phù hợp. DDL có implicit commit trong Oracle; không chạy lệnh tạo/xóa bảng trên schema nghiệp vụ thật.

### Bước 1: tạo bảng mẫu

~~~sql
CREATE TABLE lab_employee (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80) NOT NULL,
    salary NUMBER(12,2) NOT NULL,
    department_id NUMBER
);

INSERT INTO lab_employee VALUES (1, 'Mai', 12000, 10);
INSERT INTO lab_employee VALUES (2, 'An', 15000, 10);
INSERT INTO lab_employee VALUES (3, 'Binh', 11000, 20);
COMMIT;
~~~

### Bước 2: khai báo biến bằng %TYPE và hằng số

~~~sql
SET SERVEROUTPUT ON;

DECLARE
    l_employee_id lab_employee.employee_id%TYPE := 1;
    l_salary      lab_employee.salary%TYPE;
    c_bonus       CONSTANT NUMBER(8,2) := 500;
BEGIN
    SELECT salary
    INTO l_salary
    FROM lab_employee
    WHERE employee_id = l_employee_id;

    DBMS_OUTPUT.PUT_LINE('Old salary: ' || l_salary);
    DBMS_OUTPUT.PUT_LINE('New salary: ' || (l_salary + c_bonus));
END;
/
~~~

Thử đổi kiểu/precision cột SALARY trong một bảng lab riêng và quan sát vì sao anchored declaration giảm nguy cơ lệch kiểu. Không sửa schema dùng chung.

### Bước 3: dùng %ROWTYPE

~~~sql
DECLARE
    r_employee lab_employee%ROWTYPE;
BEGIN
    SELECT *
    INTO r_employee
    FROM lab_employee
    WHERE employee_id = 2;

    DBMS_OUTPUT.PUT_LINE(
        r_employee.employee_name || ': ' || r_employee.salary
    );
END;
/
~~~

### Bước 4: quan sát shadowing

~~~sql
DECLARE
    l_value NUMBER := 100;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer = ' || l_value);

    DECLARE
        l_value NUMBER := 5;
    BEGIN
        DBMS_OUTPUT.PUT_LINE('Inner = ' || l_value);
    END;

    DBMS_OUTPUT.PUT_LINE('Outer again = ' || l_value);
END;
/
~~~

Giải thích vì sao giá trị bên ngoài vẫn là 100 sau khi block con kết thúc.

### Bước 5: dùng block label

~~~sql
<<main_block>>
DECLARE
    l_total NUMBER := 100;
BEGIN
    DECLARE
        l_total NUMBER := 5;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(l_total);
        DBMS_OUTPUT.PUT_LINE(main_block.l_total);
        main_block.l_total := main_block.l_total + l_total;
    END;

    DBMS_OUTPUT.PUT_LINE(l_total);
END main_block;
/
~~~

Kết quả lần lượt thể hiện biến trong (5), biến ngoài (100), rồi biến ngoài sau khi được cập nhật (105).

### Bước 6: dùng block label để tránh trùng tên cột

~~~sql
<<update_block>>
DECLARE
    employee_id lab_employee.employee_id%TYPE := 3;
BEGIN
    UPDATE lab_employee e
    SET e.salary = e.salary + 100
    WHERE e.employee_id = update_block.employee_id;
END update_block;
/

ROLLBACK;
~~~

Block label phân biệt biến PL/SQL với cột EMPLOYEE_ID. ROLLBACK hủy thay đổi lab sau khi quan sát.

### Bước 7: xử lý exception trong block

~~~sql
DECLARE
    l_employee_id NUMBER := -1;
    l_name lab_employee.employee_name%TYPE;
BEGIN
    SELECT employee_name
    INTO l_name
    FROM lab_employee
    WHERE employee_id = l_employee_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            'No employee for id ' || l_employee_id
        );
END;
/
~~~

Biến khai báo ở block ngoài vẫn có thể được sử dụng trong exception handler của chính block đó.

### Bước 8: dọn dữ liệu

~~~sql
DROP TABLE lab_employee PURGE;
~~~

Chỉ chạy khi đã hoàn thành bài và không cần giữ dữ liệu. DROP TABLE là DDL có implicit commit; PURGE bỏ qua Recycle Bin.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Biến chưa khởi tạo trả NULL | Biến scalar không có giá trị khởi tạo | Khởi tạo rõ ràng hoặc xử lý NULL trước khi dùng. |
| Gán NULL gây VALUE_ERROR | Biến khai báo NOT NULL | Bảo đảm giá trị khác NULL hoặc bỏ NOT NULL nếu nghiệp vụ cho phép. |
| Không thể gán lại hằng | Khai báo CONSTANT | Dùng biến nếu giá trị cần thay đổi. |
| Block ngoài không thấy biến trong | Biến chỉ thuộc scope của block con | Đưa khai báo lên block cha hoặc trả giá trị qua OUT/record phù hợp. |
| Biến ngoài dường như không đổi | Biến cùng tên trong block con đang che khuất | Dùng tên khác hoặc block label qualifier. |
| SQL lọc sai số hàng | Tên biến trùng tên cột và bị phân giải nhầm | Dùng prefix biến, qualify cột và block label khi cần. |
| %TYPE vẫn nhận NULL dù cột NOT NULL | %TYPE không kế thừa ràng buộc NOT NULL | Khai báo biến NOT NULL và khởi tạo rõ ràng nếu cần. |
| %ROWTYPE không nhận được SELECT danh sách cột rút gọn | Số/thứ tự select item không khớp record | Dùng SELECT * cho rowtype tương ứng hoặc khai báo record phù hợp. |
| Package variable giữ giá trị từ request trước | Package state tồn tại trong session | Reset state theo request hoặc tránh dùng package global cho dữ liệu request. |
| Biến block con không dùng được trong outer exception | Biến đã ra khỏi lexical scope | Lưu thông tin cần thiết ở biến block cha hoặc xử lý exception tại block con. |

## 16. Câu hỏi tự kiểm tra

1. **Khai báo biến ở đâu trong block PL/SQL?** Trong phần DECLARE, trước BEGIN.
2. **Biến scalar không khởi tạo có giá trị gì?** NULL.
3. **Toán tử gán trong PL/SQL là gì?** Dấu hai chấm bằng, tức :=.
4. **CONSTANT có yêu cầu gì?** Phải có biểu thức khởi tạo và không được gán lại.
5. **NOT NULL variable cần điều gì?** Phải được khởi tạo bằng giá trị khác NULL.
6. **%TYPE dùng để làm gì?** Khai báo biến theo kiểu dữ liệu của cột hoặc biến khác.
7. **%TYPE có kế thừa NOT NULL của cột không?** Không; nếu muốn biến không nhận NULL, khai báo NOT NULL riêng.
8. **%ROWTYPE tạo kiểu gì?** Record có field tương ứng với cấu trúc hàng của bảng, view hoặc cursor.
9. **Scope khác lifetime thế nào?** Scope là nơi tên có thể được tham chiếu; lifetime là thời gian giá trị tồn tại.
10. **Block con có nhìn thấy biến ngoài không?** Có, nếu tên không bị che khuất.
11. **Block ngoài có nhìn thấy biến trong không?** Không.
12. **Shadowing là gì?** Khai báo trong phạm vi lồng bên trong có cùng tên và che khuất khai báo ngoài.
13. **Làm sao truy cập biến ngoài khi bị shadow?** Dùng block label qualifier, ví dụ main_block.l_total.
14. **Block label có kéo dài lifetime của biến không?** Không; nó chỉ định danh block.
15. **Biến package có dùng chung giữa mọi session không?** Không; package state thông thường riêng theo session.
16. **Vì sao nên prefix biến PL/SQL?** Để phân biệt biến với cột SQL và giảm lỗi name resolution.
17. **Biến trong block con có dùng được ở exception handler của block cha không?** Không, vì nó không còn trong scope của block cha.
18. **Cách tốt nhất để tránh SQL name collision là gì?** Dùng tên biến khác tên cột, prefix rõ ràng và qualify cột bằng alias.

Biến và hằng trong PL/SQL được quản lý theo phạm vi lexical của block hoặc chương trình con nơi chúng được khai báo. Block con có thể truy cập biến ngoài, nhưng khai báo cùng tên ở block trong sẽ che khuất tên ngoài; block label giúp tham chiếu rõ biến bị che khuất. Dùng %TYPE/%ROWTYPE để bám theo cấu trúc dữ liệu, CONSTANT để bảo vệ giá trị không đổi, prefix nhất quán để tránh xung đột với cột SQL và nhớ rằng package variable giữ state theo session. Những quy tắc này giúp chương trình dễ đọc, ít lỗi name resolution và dễ bảo trì hơn.
