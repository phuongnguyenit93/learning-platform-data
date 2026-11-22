# DBMS_OUTPUT, biến bind và chạy block từ công cụ trong Oracle Database

Khi học và phát triển PL/SQL, bạn thường cần in thông tin để theo dõi luồng chạy, truyền giá trị từ công cụ SQL vào một anonymous block, nhận kết quả từ block và thực thi đúng cách trong SQL Developer, SQL*Plus hoặc SQLcl. Ba phần này liên quan nhưng có vai trò khác nhau:

- **DBMS_OUTPUT** cho phép PL/SQL ghi thông điệp vào một buffer để client đọc và hiển thị sau khi block kết thúc.
- **Bind variable** là placeholder nhận giá trị từ client/driver, được tham chiếu trong SQL hoặc PL/SQL bằng dấu hai chấm, ví dụ `:p_employee_id`.
- **Cách chạy block** phụ thuộc công cụ và chế độ thực thi. Một block có thể được gửi như một statement hoặc chạy như script có các lệnh điều khiển client như SET SERVEROUTPUT ON, VARIABLE, PRINT và dấu gạch chéo.

DBMS_OUTPUT hỗ trợ debug; bind variable truyền dữ liệu có kiểu; còn script runner quyết định cách các lệnh được gửi tới database. Hiểu đúng ba phần giúp tránh tình huống block chạy thành công nhưng không thấy output, hoặc nhầm biến bind với biến thay thế văn bản.

## 1. DBMS_OUTPUT là gì?

### 1.1. Package xuất thông điệp từ PL/SQL

DBMS_OUTPUT là package Oracle cung cấp. Chương trình PL/SQL gọi package để ghi văn bản vào output buffer:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from PL/SQL');
END;
/
```

PUT_LINE thêm một dòng vào buffer. Client có hỗ trợ DBMS_OUTPUT sẽ đọc buffer sau khi block hoàn tất và hiển thị nội dung.

DBMS_OUTPUT thường dùng để:
- Học cú pháp PL/SQL và quan sát giá trị biến.
- Debug anonymous block hoặc stored procedure.
- In thông tin kiểm tra trong script quản trị.
- Theo dõi số hàng, trạng thái hoặc nhánh logic trong một lần chạy thử.

### 1.2. Output được buffer, không phải console thời gian thực

DBMS_OUTPUT.PUT_LINE không gửi ngay từng dòng tới màn hình như hàm print trong ứng dụng. Nội dung được lưu vào buffer; client đọc buffer sau khi PL/SQL unit kết thúc.

Ví dụ:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Step 1');
    DBMS_OUTPUT.PUT_LINE('Step 2');

    DBMS_LOCK.SLEEP(5);

    DBMS_OUTPUT.PUT_LINE('Step 3');
END;
/
```

Trong khi block vẫn đang chạy, client thường chưa hiển thị các dòng đã ghi. Sau khi block hoàn tất, client mới lấy và hiển thị output. Vì vậy DBMS_OUTPUT không phù hợp để theo dõi tiến độ real-time của một tác vụ dài.

### 1.3. Không thay thế hệ thống logging

DBMS_OUTPUT phù hợp cho debug và script tương tác, không phải hệ thống log bền vững:
- Output buffer không phải bảng lưu lịch sử.
- Thông điệp không tự động được ghi vào file log ứng dụng.
- Nếu client không bật hoặc không đọc output, người dùng có thể không thấy nội dung.
- Không nên dùng output làm audit trail hoặc nơi lưu dữ liệu cần truy vết lâu dài.

Với log production, cân nhắc bảng log có kiểm soát, unified auditing, application logging hoặc công cụ giám sát phù hợp. Tránh in mật khẩu, token, connection string hoặc dữ liệu cá nhân không cần thiết.

## 2. Các thủ tục DBMS_OUTPUT thường dùng

### 2.1. PUT_LINE

PUT_LINE ghi một dòng và tự thêm ký tự xuống dòng:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Employee report');
    DBMS_OUTPUT.PUT_LINE('Total employees: 25');
END;
/
```

Đây là thủ tục được dùng nhiều nhất khi debug.

### 2.2. PUT và NEW_LINE

PUT ghi nội dung mà không kết thúc dòng. NEW_LINE kết thúc dòng hiện tại:

```sql
BEGIN
    DBMS_OUTPUT.PUT('Processing ');
    DBMS_OUTPUT.PUT('employees');
    DBMS_OUTPUT.NEW_LINE;
    DBMS_OUTPUT.PUT_LINE('Finished');
END;
/
```

Có thể dùng để ghép nhiều phần trên cùng một dòng. Trong thực tế PUT_LINE thường dễ đọc hơn.

### 2.3. In giá trị biến

Dùng phép nối chuỗi || để đưa giá trị vào thông điệp:

```sql
DECLARE
    v_employee_id NUMBER := 100;
    v_salary      NUMBER := 25000;
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Employee ID = ' || v_employee_id
    );

    DBMS_OUTPUT.PUT_LINE(
        'Salary = ' || TO_CHAR(v_salary)
    );
END;
/
```

Dùng TO_CHAR với format mask khi cần định dạng số/ngày nhất quán:

```sql
DECLARE
    v_amount NUMBER := 1234567.5;
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Amount = ' || TO_CHAR(v_amount, 'FM999G999G990D00')
    );
END;
/
```

Dấu phân cách phụ thuộc NLS settings. Nếu output được dùng để so sánh hoặc xử lý tự động, hãy quy định định dạng rõ ràng.

### 2.4. ENABLE và DISABLE

Package có thủ tục điều khiển buffer:

```sql
BEGIN
    DBMS_OUTPUT.ENABLE;
    DBMS_OUTPUT.PUT_LINE('Output is enabled');
END;
/
```

DBMS_OUTPUT.ENABLE bật output buffer ở phía database session. DBMS_OUTPUT.DISABLE tắt output:

```sql
BEGIN
    DBMS_OUTPUT.DISABLE;
END;
/
```

Trong SQL Developer, SQL*Plus hoặc SQLcl, thường nên dùng lệnh client SET SERVEROUTPUT ON để vừa bật output vừa yêu cầu client lấy nội dung. Chỉ gọi ENABLE trong PL/SQL không tự làm cửa sổ công cụ hiển thị buffer nếu client không đọc nó.

### 2.5. GET_LINE và GET_LINES

Các client có thể đọc output buffer qua API:
- GET_LINE lấy một dòng.
- GET_LINES lấy nhiều dòng trong một lần gọi.

Đây là cơ chế mà nhiều công cụ dùng để lấy output sau khi chạy PL/SQL. Khi viết ứng dụng JDBC thuần, driver không tự động hiển thị DBMS_OUTPUT chỉ vì block gọi PUT_LINE; ứng dụng cần bật và đọc buffer bằng các lời gọi package tương ứng hoặc dùng tiện ích của framework.

Không cần tự gọi GET_LINE/GET_LINES trong script SQL*Plus thông thường nếu đã dùng SET SERVEROUTPUT ON.

## 3. Bật và xem DBMS_OUTPUT trong công cụ

### 3.1. SQL*Plus và SQLcl

Trong SQL*Plus hoặc SQLcl, chạy:

```sql
SET SERVEROUTPUT ON
```

Có thể yêu cầu buffer lớn:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED
```

Sau đó chạy block:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from SQL*Plus or SQLcl');
END;
/
```

Client sẽ lấy output sau khi block hoàn tất. SET SERVEROUTPUT là lệnh của client, không phải câu SQL gửi trực tiếp tới database.

### 3.2. SQL Developer

SQL Developer có hai chế độ chạy worksheet thường dùng:

- **Run Statement** (thường Ctrl+Enter hoặc F9): thực thi statement/PLSQL block được chọn hoặc tại vị trí con trỏ.
- **Run Script** (F5): thực thi worksheet như script, hỗ trợ các lệnh SQL*Plus mà SQL Developer mô phỏng, ví dụ SET SERVEROUTPUT ON, VARIABLE, PRINT và dấu gạch chéo.

Để xem DBMS_OUTPUT:
1. Mở panel DBMS Output qua menu View nếu panel chưa hiển thị.
2. Nhấn dấu cộng trong panel và chọn đúng connection.
3. Bật output cho connection đó.
4. Chạy PL/SQL block.
5. Xem nội dung trong panel DBMS Output sau khi block hoàn tất.

Giao diện có thể khác đôi chút theo phiên bản SQL Developer. Trong script có thể viết:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

BEGIN
    DBMS_OUTPUT.PUT_LINE('Running from SQL Developer');
END;
/
```

Nếu chạy block bằng Run Statement, xác nhận panel DBMS Output đã bật cho đúng connection. Đừng nhầm việc block thực thi thành công với việc client đã cấu hình lấy output.

### 3.3. Run Statement và Run Script khác nhau

Ví dụ block:

```sql
DECLARE
    v_message VARCHAR2(100) := 'Statement mode';
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_message);
END;
```

Khi chạy như một PL/SQL statement, chọn toàn bộ block hoặc đặt con trỏ bên trong block rồi dùng Run Statement. Trong chế độ này, dấu gạch chéo là lệnh riêng của script runner và thường không cần đưa vào phần statement gửi đi.

Khi chạy bằng Run Script, dùng dấu gạch chéo trên dòng riêng để yêu cầu script runner thực thi block đã kết thúc bằng END;.

Nếu gặp lỗi kiểu invalid SQL statement hoặc block bị tách thành nhiều phần, hãy kiểm tra đang dùng Run Statement hay Run Script và cách đặt dấu gạch chéo.

### 3.4. DBeaver và công cụ khác

Các công cụ như DBeaver, DataGrip hoặc IDE database có thể có tab/output panel riêng và cách bật DBMS_OUTPUT khác nhau. Kiểm tra:
- Công cụ có hỗ trợ DBMS_OUTPUT không?
- Có nút Enable/Start DBMS Output cho connection không?
- Tool có tự đọc buffer sau khi block hoàn tất không?
- Script runner có hỗ trợ SET SERVEROUTPUT, VARIABLE, PRINT hoặc dấu gạch chéo không?
- Khi dùng JDBC, công cụ có gọi DBMS_OUTPUT.GET_LINES không?

Không giả định mọi SQL editor đều tự hiển thị DBMS_OUTPUT như SQL*Plus.

## 4. Buffer và giới hạn output

### 4.1. Buffer size

DBMS_OUTPUT ghi nội dung vào buffer. Nếu chương trình tạo nhiều output, buffer có giới hạn theo cấu hình và phiên bản Oracle/client. Có thể yêu cầu buffer lớn bằng:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED
```

Hoặc gọi ENABLE với buffer size theo tài liệu phiên bản. Khi buffer vượt giới hạn, chương trình có thể gặp lỗi buffer overflow, ví dụ ORU-10027. Không nên in hàng trăm nghìn dòng chỉ để debug.

### 4.2. Độ dài một dòng

Một dòng output có giới hạn độ dài, thông thường tối đa 32.767 byte trong các phiên bản hiện đại. Chuỗi Unicode có thể chiếm nhiều byte hơn số ký tự hiển thị. Nếu thông điệp quá dài, chia thành nhiều dòng hoặc chỉ in phần cần điều tra.

```sql
DECLARE
    v_text VARCHAR2(1000) := RPAD('A', 1000, 'A');
BEGIN
    FOR i IN 0 .. 4 LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Chunk ' || i || ': ' || SUBSTR(v_text, i * 200 + 1, 200)
        );
    END LOOP;
END;
/
```

### 4.3. Output nhiều dòng ảnh hưởng hiệu năng

Mỗi lần PUT_LINE tạo thêm dữ liệu cần buffer và client phải lấy về. In quá nhiều nội dung có thể:
- Tăng thời gian chạy block.
- Tăng lượng dữ liệu chuyển từ database tới client.
- Làm cửa sổ output khó sử dụng.
- Che mất thông điệp quan trọng.

Nên in checkpoint có ý nghĩa, số lượng hàng và giá trị cần điều tra. Với batch lớn, in theo lô thay vì từng hàng.

### 4.4. Không flush giữa block

DBMS_OUTPUT không cung cấp cơ chế flush công khai để đẩy từng dòng ngay lập tức tới client giữa lúc block đang chạy. PUT_LINE chỉ thêm vào buffer; client đọc sau khi unit kết thúc. Nếu cần tiến độ real-time, dùng logging/monitoring khác hoặc thiết kế job có trạng thái quan sát được.

## 5. Bind variable là gì?

### 5.1. Placeholder do client cung cấp

Bind variable là placeholder có giá trị được truyền riêng với câu SQL/PLSQL. Trong Oracle SQL, bind thường viết bằng dấu hai chấm:

```sql
SELECT employee_id,
       first_name,
       salary
FROM   employees
WHERE  department_id = :p_department_id;
```

P_DEPARTMENT_ID là bind variable. Câu SQL được parse với placeholder, còn giá trị được gửi riêng khi thực thi.

Trong PL/SQL anonymous block:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Department = ' || :p_department_id
    );
END;
/
```

Ở đây :p_department_id là bind do client cung cấp, không phải biến được khai báo trong phần DECLARE của block.

### 5.2. Khác với biến PL/SQL cục bộ

Biến PL/SQL được khai báo trong DECLARE:

```sql
DECLARE
    v_department_id NUMBER := 10;
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_department_id);
END;
/
```

Biến v_department_id chỉ thuộc phạm vi block. Nó không cần dấu hai chấm khi dùng bên trong PL/SQL.

Bind variable do host/client cung cấp được tham chiếu bằng dấu hai chấm:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(:p_department_id);
END;
/
```

Không khai báo bind variable trong phần DECLARE. Hãy khai báo bằng lệnh của client/driver hoặc truyền qua API thực thi.

### 5.3. Lợi ích của bind variable

Bind variable thường mang lại:
- Tái sử dụng SQL cursor khi câu SQL giống nhau nhưng giá trị thay đổi.
- Giảm chi phí hard parse trong workload lặp lại.
- Tách dữ liệu khỏi cấu trúc câu SQL.
- Giảm nguy cơ SQL injection khi bind giá trị đúng cách.
- Truyền kiểu dữ liệu rõ ràng qua driver.

Bind variable không bảo đảm mọi truy vấn luôn có cùng execution plan tối ưu. Bind peeking và adaptive cursor sharing có thể ảnh hưởng plan theo phân bố dữ liệu và bind values.

### 5.4. Bind giá trị, không bind tên cột hoặc tên bảng

Bind dùng cho giá trị biểu thức:
- WHERE employee_id = :p_id
- SET salary = :p_salary
- WHERE created_at >= :p_from_date

Không thể dùng bind thay cho tên bảng, tên cột hoặc từ khóa SQL:

```sql
-- Không hoạt động như một cách bind tên bảng:
SELECT * FROM :p_table_name;
```

Nếu cần chọn tên bảng/cột động, hãy xây dựng dynamic SQL có kiểm soát, dùng whitelist tên được phép và biện pháp xác thực phù hợp như DBMS_ASSERT. Không nối trực tiếp chuỗi người dùng vào SQL.

## 6. Bind variable trong SQL*Plus và SQLcl

### 6.1. Khai báo bằng VARIABLE

Trong SQL*Plus/SQLcl, dùng lệnh client VARIABLE (viết tắt VAR) để khai báo bind:

```sql
VARIABLE b_department_id NUMBER
```

Gán giá trị bằng EXECUTE:

```sql
EXEC :b_department_id := 10;
```

Dùng trong câu SELECT:

```sql
SELECT department_id,
       department_name
FROM   departments
WHERE  department_id = :b_department_id;
```

VARIABLE và EXEC ở đây là lệnh client. Chúng không phải cú pháp khai báo biến trong anonymous block.

### 6.2. Bind variable với anonymous block

```sql
VARIABLE b_department_id NUMBER
VARIABLE b_employee_count NUMBER

EXEC :b_department_id := 10;

BEGIN
    SELECT COUNT(*)
    INTO   :b_employee_count
    FROM   employees
    WHERE  department_id = :b_department_id;

    DBMS_OUTPUT.PUT_LINE(
        'Employees in department ' ||
        :b_department_id ||
        ': ' ||
        :b_employee_count
    );
END;
/

PRINT b_employee_count
```

Trong block, dấu hai chấm cho biết biến thuộc client. PRINT hiển thị giá trị bind sau khi block hoàn tất.

### 6.3. OUT bind variable

Bind có thể nhận giá trị từ PL/SQL:

```sql
VARIABLE b_message VARCHAR2(200)

BEGIN
    :b_message := 'Completed successfully';
END;
/

PRINT b_message
```

Đây là cách trả dữ liệu từ anonymous block về SQL*Plus/SQLcl. Với ứng dụng, driver đăng ký và đọc OUT parameter theo API tương ứng.

### 6.4. IN, OUT và IN OUT trong procedure

Một procedure có thể nhận tham số:

```sql
CREATE OR REPLACE PROCEDURE get_employee_salary (
    p_employee_id IN  employees.employee_id%TYPE,
    p_salary      OUT employees.salary%TYPE
)
AS
BEGIN
    SELECT salary
    INTO   p_salary
    FROM   employees
    WHERE  employee_id = p_employee_id;
END;
/
```

Gọi procedure từ SQL*Plus/SQLcl:

```sql
VARIABLE b_salary NUMBER

EXEC get_employee_salary(100, :b_salary);

PRINT b_salary
```

- IN: dữ liệu truyền vào procedure.
- OUT: procedure gán giá trị trả về.
- IN OUT: giá trị được truyền vào và có thể thay đổi để trả về.

Bind variable là phía client; formal parameter là phần khai báo của procedure. Hai khái niệm liên kết khi client truyền bind vào tham số procedure.

## 7. Bind variable và substitution variable không giống nhau

### 7.1. Substitution variable thay văn bản trước khi gửi SQL

Trong SQL*Plus/SQLcl, substitution variable dùng dấu & hoặc &&:

```sql
DEFINE department_id = 10

SELECT department_id,
       department_name
FROM   departments
WHERE  department_id = &department_id;
```

Client thay &department_id bằng văn bản 10 trước khi gửi câu SQL tới database. Đây là text substitution, không phải bind.

### 7.2. So sánh

| Đặc điểm | Bind variable :name | Substitution variable &name |
| --- | --- | --- |
| Cách xử lý | Giá trị truyền riêng khi execute | Thay văn bản trước khi gửi SQL |
| Kiểu dữ liệu | Có kiểu theo bind/driver | Là đoạn văn bản được thay vào |
| Tái sử dụng cursor | Hỗ trợ chia sẻ cursor khi SQL giống nhau | Giá trị thay đổi có thể làm SQL text khác |
| An toàn | Tách giá trị khỏi SQL structure | Có thể nguy hiểm nếu chèn text không tin cậy |
| Dùng cho tên object | Không | Có thể thay văn bản nhưng phải kiểm soát chặt |

### 7.3. Ví dụ

Bind:

```sql
VARIABLE b_dept NUMBER
EXEC :b_dept := 20;

SELECT *
FROM employees
WHERE department_id = :b_dept;
```

Substitution:

```sql
DEFINE dept = 20

SELECT *
FROM employees
WHERE department_id = &dept;
```

Trong ví dụ bind, SQL gửi tới Oracle vẫn chứa placeholder. Trong ví dụ substitution, client thay &dept thành 20 rồi gửi câu SQL đã được mở rộng.

### 7.4. Khi nào dùng substitution?

Substitution hữu ích trong script để:
- Chọn schema/table theo môi trường từ giá trị đã được kiểm soát.
- Thay một đoạn SQL hoặc tùy chọn script.
- Nhận tham số văn bản khi chạy script.

Vì substitution thay đổi câu SQL trước parse, không dùng nó thay bind cho dữ liệu người dùng không tin cậy. Với giá trị lọc thông thường, ưu tiên bind variable.

## 8. Bind variable trong SQL Developer

### 8.1. Khai báo bind trong Run Script

Trong worksheet SQL Developer:

```sql
VARIABLE b_emp_id NUMBER
VARIABLE b_salary NUMBER

EXEC :b_emp_id := 100;

BEGIN
    SELECT salary
    INTO   :b_salary
    FROM   employees
    WHERE  employee_id = :b_emp_id;

    DBMS_OUTPUT.PUT_LINE('Salary = ' || :b_salary);
END;
/

PRINT b_salary
```

Chạy bằng Run Script (F5) để các lệnh SQL*Plus như VARIABLE, EXEC, PRINT và dấu gạch chéo được xử lý theo script runner.

### 8.2. Chạy một block riêng

Nếu chỉ cần chạy:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Test block');
END;
```

Chọn block hoặc đặt con trỏ trong block rồi dùng Run Statement. Cần bật DBMS Output panel cho đúng connection nếu muốn xem output.

Nếu block dùng bind variable, bảo đảm bind đã được tạo/gán trong cùng connection/session mà block thực thi. Các lệnh VARIABLE/PRINT nên chạy theo chế độ script nếu worksheet cần xử lý chúng như lệnh client.

### 8.3. Bind Variables panel

Một số phiên bản SQL Developer cung cấp panel hoặc cửa sổ để nhập giá trị bind khi chạy statement. Khi công cụ yêu cầu bind:
1. Xác nhận tên bind trong SQL/block.
2. Nhập giá trị đúng kiểu.
3. Thực thi statement.
4. Kiểm tra kết quả hoặc OUT bind theo giao diện công cụ.

Giao diện có thể khác giữa phiên bản. Với ví dụ nhiều bước, VARIABLE + EXEC + block + PRINT chạy bằng F5 thường dễ lặp lại và lưu thành script hơn.

### 8.4. Connection/session rất quan trọng

Bind variable trong SQL*Plus/SQLcl hoặc SQL Developer gắn với session/connection cụ thể. Nếu đổi worksheet connection hoặc mở session khác, không giả định bind cũ vẫn có sẵn.

Khi gặp lỗi bind variable not declared, kiểm tra:
- Đã khai báo VARIABLE chưa?
- Đã chạy lệnh khai báo trong đúng connection chưa?
- Đang dùng Run Script hay Run Statement?
- Tên bind có khớp không?
- Có dấu hai chấm ở vị trí cần thiết không?

## 9. Chạy anonymous block từ các công cụ

### 9.1. Cấu trúc anonymous block

```sql
DECLARE
    -- Khai báo biến, cursor, kiểu và exception cục bộ
BEGIN
    -- Các câu lệnh thực thi
EXCEPTION
    -- Xử lý exception
END;
/
```

DECLARE là tùy chọn. BEGIN và END là bắt buộc. Các câu lệnh bên trong kết thúc bằng dấu chấm phẩy.

### 9.2. Dấu chấm phẩy và dấu gạch chéo

Trong script SQL*Plus/SQLcl:
- Dấu chấm phẩy kết thúc câu lệnh PL/SQL bên trong block.
- Dấu gạch chéo trên một dòng riêng yêu cầu client thực thi nội dung block đang nằm trong SQL buffer.

Ví dụ:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END;
/
```

Dấu gạch chéo không phải một phần cú pháp PL/SQL block gửi trực tiếp tới database. Nó là lệnh client script runner. Vì vậy, cách dùng dấu gạch chéo phụ thuộc chế độ chạy.

### 9.3. EXECUTE/EXEC

SQL*Plus/SQLcl hỗ trợ lệnh tắt:

```sql
EXEC DBMS_OUTPUT.PUT_LINE('One PL/SQL statement');
```

EXEC/EXECUTE là lệnh client dùng để thực thi một PL/SQL statement. Với logic nhiều câu, biến cục bộ hoặc exception handling, dùng anonymous block đầy đủ sẽ rõ ràng hơn.

### 9.4. Chạy stored procedure

Nếu procedure đã được tạo:

```sql
BEGIN
    get_employee_salary(
        p_employee_id => 100,
        p_salary      => :b_salary
    );
END;
/
```

Khi procedure có OUT parameter, dùng bind để nhận kết quả từ client.

### 9.5. Hiển thị lỗi biên dịch

Nếu anonymous block bị lỗi, client thường hiển thị ORA-06550 và dòng/vị trí lỗi PL/SQL. Đọc lỗi đầu tiên và vị trí được chỉ ra trước khi sửa.

Với stored procedure/function/package đã tạo, có thể dùng:

```sql
SHOW ERRORS PROCEDURE get_employee_salary;
```

Hoặc xem lỗi trong dictionary:

```sql
SELECT line,
       position,
       text
FROM   user_errors
WHERE  name = 'GET_EMPLOYEE_SALARY'
ORDER  BY sequence;
```

SHOW ERRORS là lệnh client của SQL*Plus/SQLcl và được một số script runner mô phỏng. Nó không phải câu SQL thông thường.

## 10. Nhận dữ liệu trả về từ block

### 10.1. DBMS_OUTPUT là kênh hiển thị

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Result = 42');
END;
/
```

Thông điệp được hiển thị nếu client đã bật và đọc DBMS_OUTPUT. Đây là kênh văn bản hỗ trợ debug, không phải cách tốt nhất để ứng dụng lấy giá trị có kiểu dữ liệu.

### 10.2. Dùng OUT bind cho giá trị có cấu trúc

Nếu ứng dụng cần nhận số, chuỗi, ngày hoặc ref cursor, nên dùng tham số OUT/IN OUT hoặc bind output phù hợp thay vì parse văn bản DBMS_OUTPUT.

```sql
VARIABLE b_total NUMBER

BEGIN
    SELECT COUNT(*)
    INTO   :b_total
    FROM   employees;
END;
/

PRINT b_total
```

Giá trị b_total được trả về dưới dạng bind NUMBER, không phải chuỗi phải phân tích từ output.

### 10.3. RETURNING INTO cho DML

Với INSERT/UPDATE/DELETE cần lấy giá trị vừa tác động, cân nhắc RETURNING INTO:

```sql
VARIABLE b_new_id NUMBER

BEGIN
    INSERT INTO departments (department_name)
    VALUES ('Research')
    RETURNING department_id INTO :b_new_id;
END;
/

PRINT b_new_id
```

Nếu DEPARTMENT_ID là identity, Oracle sinh ID và RETURNING lấy đúng giá trị của hàng vừa insert. Không dùng SELECT MAX(id) để tìm ID mới vì session khác có thể insert đồng thời.

### 10.4. REF CURSOR và kết quả nhiều hàng

Nếu ứng dụng cần nhận tập hàng, procedure có thể trả SYS_REFCURSOR qua OUT parameter. Cách đọc phụ thuộc driver/tool. Không in toàn bộ tập kết quả thành DBMS_OUTPUT chỉ để truyền dữ liệu cho ứng dụng.

## 11. JDBC và ứng dụng gọi PL/SQL

### 11.1. Bind trong PreparedStatement

Ứng dụng Java có thể dùng PreparedStatement:

```java
String sql =
    "SELECT salary FROM employees WHERE employee_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 100L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getBigDecimal(1));
        }
    }
}
```

Dấu ? là placeholder của JDBC. Driver truyền giá trị riêng, giúp tái sử dụng SQL và tránh nối dữ liệu người dùng vào câu lệnh.

### 11.2. Gọi PL/SQL block với CallableStatement

```java
String plsql =
    "BEGIN " +
    "  get_employee_salary(?, ?); " +
    "END;";

try (CallableStatement cs = connection.prepareCall(plsql)) {
    cs.setLong(1, 100L);
    cs.registerOutParameter(2, Types.NUMERIC);
    cs.execute();

    BigDecimal salary = cs.getBigDecimal(2);
}
```

Ví dụ dùng tham số thứ nhất IN và thứ hai OUT. Kiểu JDBC phải phù hợp với kiểu Oracle và driver. Với kiểu phức tạp như REF CURSOR, dùng API tương ứng của Oracle JDBC.

### 11.3. DBMS_OUTPUT trong JDBC không tự hiện ra

Khi Java gọi block có DBMS_OUTPUT.PUT_LINE, nội dung vẫn nằm trong buffer của DBMS_OUTPUT. JDBC không tự chuyển nội dung đó thành System.out.

Muốn lấy output, ứng dụng phải:
1. Gọi DBMS_OUTPUT.ENABLE trên connection/session.
2. Thực thi PL/SQL block.
3. Gọi DBMS_OUTPUT.GET_LINES hoặc GET_LINE để lấy nội dung.
4. Hiển thị hoặc ghi log ở tầng ứng dụng.
5. Tắt/giải phóng cấu hình nếu ứng dụng có quy ước riêng.

Trong hệ thống thật, không nên bật DBMS_OUTPUT cho mọi request nếu không cần debug; output nhiều có thể tăng chi phí và tạo dữ liệu không cần thiết.

### 11.4. Giữ đúng connection

OUT bind và DBMS_OUTPUT buffer thuộc session/connection đang thực thi. Nếu ứng dụng dùng connection pool, phải lấy output trên đúng connection đã chạy block trước khi trả connection về pool. Không chạy block ở connection A rồi gọi GET_LINES ở connection B.

## 12. Debug PL/SQL có phương pháp

### 12.1. In checkpoint

```sql
DECLARE
    v_count NUMBER;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Step 1: start');

    SELECT COUNT(*)
    INTO   v_count
    FROM   employees;

    DBMS_OUTPUT.PUT_LINE('Step 2: count=' || v_count);

    IF v_count = 0 THEN
        DBMS_OUTPUT.PUT_LINE('No employees found');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Employees exist');
    END IF;

    DBMS_OUTPUT.PUT_LINE('Step 3: finish');
END;
/
```

Output giúp xác định block đã đi tới đâu và giá trị biến tại một thời điểm.

### 12.2. In exception

```sql
DECLARE
    v_salary NUMBER;
BEGIN
    SELECT salary
    INTO   v_salary
    FROM   employees
    WHERE  employee_id = -1;

    DBMS_OUTPUT.PUT_LINE('Salary=' || v_salary);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No employee found');

    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('More than one employee found');

    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Unexpected error: ' || SQLERRM
        );
        RAISE;
END;
/
```

SQLERRM trả thông điệp lỗi hiện tại trong handler. Khi bắt WHEN OTHERS, cân nhắc re-raise bằng RAISE để không che giấu lỗi ngoài ý muốn. Không chỉ in lỗi rồi tiếp tục như thể block thành công.

### 12.3. Không in mọi hàng khi dữ liệu lớn

Với bảng lớn, vòng lặp PUT_LINE cho từng hàng có thể tạo lượng output rất lớn. Thay vào đó, in tổng số hàng, một vài mẫu hoặc checkpoint theo lô:

```sql
DBMS_OUTPUT.PUT_LINE('Processed batch: ' || v_batch_no);
```

Nếu cần theo dõi tiến độ tác vụ dài, lưu trạng thái batch trong bảng job hoặc dùng công cụ monitoring thay vì chờ DBMS_OUTPUT.

### 12.4. Không ghi thông tin bí mật

Không in mật khẩu, access token, connection string chứa credential hoặc dữ liệu cá nhân không cần thiết. Output có thể được lưu trong lịch sử script, ảnh chụp màn hình hoặc log của client.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Block chạy thành công nhưng không thấy output | DBMS_OUTPUT chưa bật hoặc client chưa đọc buffer | Bật DBMS Output panel/SET SERVEROUTPUT ON |
| Output chỉ xuất hiện khi block kết thúc | DBMS_OUTPUT được buffer, không flush real-time | Đây là hành vi bình thường |
| SP2 error khi chạy SET/VARIABLE/PRINT | Đang gửi lệnh client như SQL statement hoặc tool không hỗ trợ | Chạy bằng script mode hoặc dùng API driver |
| Bind variable not declared | Chưa khai báo bind, sai connection hoặc sai tên | VARIABLE/Bind panel và kiểm tra dấu hai chấm |
| ORA-06550 | Lỗi cú pháp hoặc lỗi PL/SQL trong block | Đọc dòng/vị trí và lỗi PL/SQL tiếp theo |
| ORA-01403 | SELECT INTO không tìm thấy hàng | Xử lý NO_DATA_FOUND |
| ORA-01422 | SELECT INTO trả nhiều hàng | Sửa predicate hoặc dùng cursor/collection |
| Output buffer overflow | In quá nhiều nội dung hoặc buffer nhỏ | Giảm output hoặc cấu hình buffer phù hợp |
| Một dòng output quá dài | Vượt giới hạn độ dài dòng | Chia thành nhiều dòng |
| CURRVAL chưa được định nghĩa | Session chưa gọi NEXTVAL | Gọi NEXTVAL trước trong cùng session |

### 13.1. Block chạy nhưng panel rỗng

Kiểm tra theo thứ tự:
1. Block có thực sự được thực thi thành công không?
2. PUT_LINE có nằm trên nhánh logic đã chạy không?
3. Client có bật DBMS_OUTPUT không?
4. Panel đã gắn đúng connection chưa?
5. Client có lấy output sau khi block hoàn tất không?
6. Có lỗi buffer hoặc lỗi khác trước PUT_LINE không?

Đừng thêm hàng loạt PUT_LINE trước khi xác định vấn đề là block không chạy hay client không đọc output.

### 13.2. Bind variable không nhận giá trị

Kiểm tra:
- Tên bind trong block có đúng với tên khai báo không.
- Đã dùng dấu hai chấm trước bind chưa.
- Kiểu bind có tương thích với cột/tham số không.
- Đã gán giá trị trước khi execute chưa.
- Bind có được khai báo trong cùng session không.
- Tool có đang chạy VARIABLE như lệnh client trong script mode không.

### 13.3. Bind trong SQL động

Trong dynamic SQL, bind value nên được truyền qua USING:

```sql
DECLARE
    v_count NUMBER;
    v_dept_id NUMBER := 10;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE department_id = :x'
        INTO v_count
        USING v_dept_id;

    DBMS_OUTPUT.PUT_LINE('Count=' || v_count);
END;
/
```

Giá trị v_dept_id được bind qua USING, không cần nối vào chuỗi SQL. Thứ tự USING phải phù hợp với placeholder theo quy tắc native dynamic SQL.

## 14. Bài thực hành tổng hợp

### Bài 1 — Bật DBMS_OUTPUT

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello Oracle');
END;
/
```

Quan sát output sau khi block kết thúc.

### Bài 2 — In biến cục bộ

```sql
DECLARE
    v_name VARCHAR2(50) := 'An';
    v_age  NUMBER := 25;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Name=' || v_name);
    DBMS_OUTPUT.PUT_LINE('Age=' || v_age);
END;
/
```

Phân biệt biến cục bộ với bind variable.

### Bài 3 — Dùng PUT và NEW_LINE

```sql
BEGIN
    DBMS_OUTPUT.PUT('Oracle ');
    DBMS_OUTPUT.PUT('PL/SQL');
    DBMS_OUTPUT.NEW_LINE;
END;
/
```

Quan sát việc ghép nội dung trên một dòng.

### Bài 4 — Bind IN

```sql
VARIABLE b_dept NUMBER
EXEC :b_dept := 10;

BEGIN
    DBMS_OUTPUT.PUT_LINE('Department=' || :b_dept);
END;
/

PRINT b_dept
```

Thay giá trị bind và chạy lại.

### Bài 5 — Bind OUT

```sql
VARIABLE b_count NUMBER

BEGIN
    SELECT COUNT(*)
    INTO :b_count
    FROM employees;
END;
/

PRINT b_count
```

Giải thích vì sao OUT bind có kiểu NUMBER trong khi DBMS_OUTPUT chỉ là văn bản.

### Bài 6 — Bind và SELECT INTO

Dùng bind employee ID để truy vấn salary vào một bind output. Thử ID không tồn tại và xử lý NO_DATA_FOUND.

### Bài 7 — Substitution variable

Dùng DEFINE và dấu & để thay một giá trị trong script. So sánh SQL text sau substitution với câu SQL có bind :name.

### Bài 8 — Chạy trong SQL Developer

Chạy một block bằng Run Statement, sau đó chạy script có SET SERVEROUTPUT ON và dấu gạch chéo bằng Run Script. Ghi nhận khác biệt.

### Bài 9 — Stored procedure có OUT

Tạo procedure nhận employee ID IN và salary OUT. Gọi bằng bind và PRINT kết quả.

### Bài 10 — Dynamic SQL với USING

Dùng EXECUTE IMMEDIATE và USING để truyền giá trị lọc. Giải thích vì sao không nối trực tiếp giá trị người dùng vào SQL string.

### Bài 11 — Xử lý exception

Tạo SELECT INTO không có hàng, in thông báo trong NO_DATA_FOUND. Thêm WHEN OTHERS có RAISE và quan sát lỗi được trả về.

### Bài 12 — Debug batch

Viết block xử lý theo lô, chỉ in số batch, số hàng xử lý và trạng thái cuối. Không in từng hàng nếu dữ liệu lớn.

## 15. Quy trình chạy block an toàn và dễ lặp lại

Trước khi chạy script PL/SQL:
1. Xác nhận đúng database, service, schema và connection.
2. Xác định công cụ đang dùng SQL*Plus, SQLcl, SQL Developer hay JDBC.
3. Nếu cần DBMS_OUTPUT, bật output ở đúng session/connection.
4. Khai báo bind variables và gán giá trị trước khi gọi block.
5. Dùng đúng chế độ Run Statement hoặc Run Script.
6. Dùng dấu gạch chéo trên dòng riêng khi script runner yêu cầu.
7. Đọc output, lỗi và OUT bind sau khi block hoàn tất.
8. Kiểm tra transaction: COMMIT/ROLLBACK có đúng yêu cầu nghiệp vụ không.
9. Không để output chứa credential hoặc dữ liệu nhạy cảm.
10. Ghi lại script có thể chạy lại và tránh DDL/DML phá dữ liệu ngoài ý muốn.

Với script nhiều bước, có thể tổ chức:

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

VARIABLE b_result NUMBER

DECLARE
    v_local_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO   v_local_count
    FROM   employees;

    :b_result := v_local_count;

    DBMS_OUTPUT.PUT_LINE(
        'Employee count = ' || v_local_count
    );
END;
/

PRINT b_result
```

Script thể hiện ba phạm vi:
- v_local_count: biến cục bộ trong PL/SQL block.
- :b_result: bind variable của client nhận kết quả.
- DBMS_OUTPUT: thông điệp debug hiển thị qua client sau khi block kết thúc.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Packages and Types Reference — DBMS_OUTPUT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_OUTPUT.html): PUT_LINE, PUT, NEW_LINE, ENABLE, DISABLE, GET_LINE và GET_LINES.
- [Oracle Database SQL*Plus User's Guide and Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqpug/): SET SERVEROUTPUT, VARIABLE, PRINT, EXECUTE và cách chạy script.
- [Oracle SQL Developer User's Guide](https://docs.oracle.com/en/database/oracle/sql-developer/): worksheet, Run Statement, Run Script và DBMS Output panel.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/): anonymous block, biến PL/SQL, procedure và parameter modes.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): cú pháp SQL và cách sử dụng bind trong câu lệnh.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): SQL injection và thực hành bảo mật khi xây dựng dynamic SQL.

DBMS_OUTPUT giúp PL/SQL gửi thông điệp debug qua buffer để client đọc sau khi block kết thúc. Bind variable truyền giá trị có kiểu từ client vào SQL/PLSQL hoặc nhận kết quả qua OUT bind; nó khác substitution variable vốn thay văn bản trước khi parse. Khi chạy block, hãy xác định đúng công cụ và chế độ Run Statement/Run Script, bật DBMS_OUTPUT cho đúng connection, khai báo bind trong đúng session và dùng dấu gạch chéo khi script runner yêu cầu.
