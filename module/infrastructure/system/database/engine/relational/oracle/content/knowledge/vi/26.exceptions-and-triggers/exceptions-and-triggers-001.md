# Exception định sẵn, exception tự định nghĩa và PRAGMA EXCEPTION_INIT trong PL/SQL

PL/SQL dùng exception để báo hiệu và xử lý tình huống bất thường trong khi thực thi. Một câu SELECT INTO không tìm thấy dòng, phép chia cho 0, vi phạm unique constraint hoặc một quy tắc nghiệp vụ không hợp lệ đều có thể làm luồng xử lý chuyển sang exception handler.

Oracle cung cấp các **exception định sẵn (predefined exceptions)** cho những lỗi thường gặp. Khi cần mô tả một tình huống riêng của ứng dụng, lập trình viên có thể khai báo **exception tự định nghĩa (user-defined exception)** và chủ động raise nó. Khi một lỗi Oracle có mã ORA cụ thể nhưng chưa có tên exception phù hợp trong PL/SQL, **PRAGMA EXCEPTION_INIT** cho phép gắn mã lỗi đó với một tên exception để xử lý bằng WHEN.

Ba cơ chế này giải quyết ba nhu cầu khác nhau:

- Predefined exception: dùng tên Oracle đã định nghĩa sẵn cho lỗi phổ biến.
- User-defined exception: đặt tên cho điều kiện bất thường do logic ứng dụng phát hiện.
- PRAGMA EXCEPTION_INIT: liên kết một exception đã khai báo với mã lỗi Oracle để bắt lỗi đó bằng tên có ý nghĩa.

Ngoài ra, RAISE_APPLICATION_ERROR cho phép trả mã lỗi và thông điệp ứng dụng trong khoảng mã dành riêng. Cần phân biệt nó với RAISE và PRAGMA EXCEPTION_INIT để thiết kế hợp đồng lỗi nhất quán giữa procedure, trigger và ứng dụng gọi.

## 1. Exception là gì?

Exception là một sự kiện bất thường làm PL/SQL rời luồng xử lý tuần tự tại vị trí phát sinh lỗi và tìm handler tương ứng. Nếu block hiện tại không có handler phù hợp, exception truyền ra block gọi hoặc môi trường gọi.

Một block PL/SQL có ba phần:

~~~sql
DECLARE
    -- Khai báo biến, cursor, exception, kiểu dữ liệu...
BEGIN
    -- Các câu lệnh thực thi bình thường.
EXCEPTION
    -- Các handler xử lý exception.
END;
/
~~~

Phần DECLARE là tùy chọn. Phần EXCEPTION cũng là tùy chọn nếu block không cần xử lý lỗi tại chỗ.

### 1.1 Luồng xử lý khi có exception

~~~text
Bắt đầu block
     |
     v
Chạy câu lệnh bình thường
     |
     v
Có exception?
   /     \
 Không    Có
  |       |
  v       v
Tiếp tục  Tìm handler phù hợp
          trong block hiện tại
               |
          +----+----+
          |         |
        Có handler  Không có
          |         |
          v         v
      Chạy handler  Truyền exception
          |         ra block gọi
          v
      Kết thúc block
~~~

Sau khi một handler chạy xong, PL/SQL không quay lại câu lệnh đã gây lỗi để tiếp tục câu lệnh tiếp theo trong phần executable section. Luồng tiếp tục sau block đã xử lý exception, hoặc exception được truyền tiếp nếu handler dùng RAISE.

### 1.2 Exception khác với giá trị trả về

Một procedure có thể trả trạng thái nghiệp vụ như NOT_FOUND qua OUT parameter, hoặc raise exception. Hai cách có hợp đồng khác nhau:

- Giá trị trả về phù hợp khi tình huống là kết quả bình thường mà caller cần phân nhánh.
- Exception phù hợp khi luồng hiện tại không thể tiếp tục theo điều kiện đã định hoặc cần truyền lỗi qua nhiều tầng.

Không nên dùng exception như cơ chế điều khiển cho mọi nhánh thông thường, ví dụ dùng NO_DATA_FOUND chỉ để kiểm tra sự tồn tại khi một câu SELECT COUNT hoặc EXISTS phù hợp hơn.

## 2. Exception định sẵn (predefined exceptions)

Predefined exceptions là các exception Oracle đã khai báo trong package STANDARD. Chúng có thể được dùng trực tiếp trong PL/SQL mà không cần khai báo lại.

Ví dụ:

~~~sql
BEGIN
    -- Các câu lệnh có thể phát sinh lỗi.
    NULL;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Không tìm thấy dữ liệu');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Truy vấn trả về nhiều hơn một dòng');
END;
/
~~~

### 2.1 Một số predefined exception thường gặp

| Tên exception | Mã Oracle thường gặp | Tình huống |
|---|---:|---|
| NO_DATA_FOUND | +100 trong PL/SQL | SELECT INTO không trả dòng |
| TOO_MANY_ROWS | -1422 | SELECT INTO trả nhiều hơn một dòng |
| ZERO_DIVIDE | -1476 | Chia một số cho 0 |
| DUP_VAL_ON_INDEX | -1 | INSERT/UPDATE vi phạm unique constraint hoặc unique index |
| INVALID_NUMBER | -1722 | Chuyển chuỗi sang NUMBER không hợp lệ trong ngữ cảnh SQL |
| VALUE_ERROR | -6502 | Lỗi chuyển đổi, gán hoặc giới hạn giá trị trong PL/SQL |
| INVALID_CURSOR | -1001 | Thao tác cursor không hợp lệ |
| CURSOR_ALREADY_OPEN | -6511 | Mở một explicit cursor vốn đang mở |
| LOGIN_DENIED | -1017 | Đăng nhập bị từ chối |
| NOT_LOGGED_ON | -1012 | Thao tác yêu cầu session đã đăng nhập |
| TIMEOUT_ON_RESOURCE | -51 | Hết thời gian chờ tài nguyên trong một số thao tác |

Mã trong bảng là các mã lỗi Oracle thường liên quan; SQLCODE của một số predefined exception có quy ước đặc biệt, đáng chú ý nhất là NO_DATA_FOUND trả +100. Khi cần xử lý một ORA code cụ thể, hãy đối chiếu đúng lỗi phát sinh và phiên bản Oracle.

Một số predefined exceptions khác gồm ACCESS_INTO_NULL, CASE_NOT_FOUND, COLLECTION_IS_NULL, PROGRAM_ERROR, ROWTYPE_MISMATCH, SELF_IS_NULL, STORAGE_ERROR, SUBSCRIPT_BEYOND_COUNT, SUBSCRIPT_OUTSIDE_LIMIT và SYS_INVALID_ROWID.

### 2.2 NO_DATA_FOUND

NO_DATA_FOUND phát sinh khi câu SELECT INTO không trả dòng:

~~~sql
DECLARE
    l_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO l_name
    FROM employees
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Không có nhân viên phù hợp');
END;
/
~~~

SELECT INTO được thiết kế để lấy đúng một dòng. Nếu không có dòng, PL/SQL raise NO_DATA_FOUND. Nếu có nhiều hơn một dòng, lỗi là TOO_MANY_ROWS.

Nếu tình huống không tìm thấy là kết quả bình thường, có thể cân nhắc trả trạng thái qua OUT parameter hoặc dùng cursor/logic khác để caller xử lý rõ ràng.

### 2.3 TOO_MANY_ROWS

~~~sql
DECLARE
    l_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO l_name
    FROM employees
    WHERE department_id = 10;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Điều kiện truy vấn không xác định duy nhất một nhân viên'
        );
END;
/
~~~

Nếu nghiệp vụ yêu cầu một dòng duy nhất, nên bảo đảm điều kiện có khóa duy nhất hoặc có quy tắc chọn dòng rõ ràng. Không dùng ROWNUM = 1 tùy tiện để che việc dữ liệu không duy nhất.

### 2.4 ZERO_DIVIDE

~~~sql
DECLARE
    l_total NUMBER := 100;
    l_count NUMBER := 0;
    l_average NUMBER;
BEGIN
    l_average := l_total / l_count;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Không thể chia cho 0');
END;
/
~~~

Nếu mẫu số có thể bằng 0 theo nghiệp vụ, có thể kiểm tra trước khi chia và trả kết quả phù hợp. Exception vẫn hữu ích để bảo vệ trường hợp không dự kiến.

### 2.5 DUP_VAL_ON_INDEX

~~~sql
BEGIN
    INSERT INTO departments (
        department_id,
        department_name
    )
    VALUES (
        10,
        'New department'
    );
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE(
            'Mã phòng ban đã tồn tại'
        );
END;
/
~~~

Không nên mặc định mọi lỗi duplicate đều là request lặp hợp lệ. Cần xác định constraint nào vi phạm, kiểm tra dữ liệu hiện có và áp dụng chính sách nghiệp vụ.

### 2.6 VALUE_ERROR và INVALID_NUMBER

VALUE_ERROR thường liên quan đến chuyển đổi hoặc giới hạn kiểu dữ liệu trong PL/SQL:

~~~sql
DECLARE
    l_small VARCHAR2(3);
BEGIN
    l_small := 'ORACLE';
EXCEPTION
    WHEN VALUE_ERROR THEN
        DBMS_OUTPUT.PUT_LINE('Giá trị vượt giới hạn biến');
END;
/
~~~

INVALID_NUMBER thường xuất hiện khi một biểu thức SQL cố chuyển chuỗi không hợp lệ sang NUMBER:

~~~sql
DECLARE
    l_value NUMBER;
BEGIN
    SELECT TO_NUMBER('ABC')
    INTO l_value
    FROM dual;
EXCEPTION
    WHEN INVALID_NUMBER THEN
        DBMS_OUTPUT.PUT_LINE('Chuỗi không phải số hợp lệ');
END;
/
~~~

Ranh giới giữa lỗi chuyển đổi ở SQL và PL/SQL có thể ảnh hưởng exception cụ thể. Khi cần phân loại chính xác, dùng mã lỗi và thông điệp thực tế từ môi trường chạy.

## 3. Khai báo và sử dụng exception tự định nghĩa

User-defined exception là exception do lập trình viên khai báo để mô tả điều kiện nghiệp vụ hoặc tình huống riêng.

### 3.1 Khai báo exception

Khai báo trong phần DECLARE:

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
BEGIN
    NULL;
END;
/
~~~

Exception có phạm vi theo block khai báo. Block con có thể nhìn thấy exception được khai báo ở block cha, nhưng block bên ngoài không nhìn thấy exception chỉ được khai báo cục bộ trong block con.

### 3.2 Raise exception bằng RAISE

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
    l_amount NUMBER := -50;
BEGIN
    IF l_amount <= 0 THEN
        RAISE e_invalid_amount;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Amount is valid');
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE('Số tiền phải lớn hơn 0');
END;
/
~~~

RAISE e_invalid_amount chủ động phát sinh exception đã khai báo. Nó không tự tạo một ORA code ứng dụng riêng. Nếu user-defined exception không được ánh xạ bằng PRAGMA EXCEPTION_INIT, SQLCODE thường là +1 và SQLERRM trả thông điệp User-Defined Exception.

### 3.3 Tình huống nghiệp vụ riêng

Ví dụ một đơn hàng không được xác nhận nếu số lượng bằng 0:

~~~sql
DECLARE
    e_empty_order EXCEPTION;
    l_quantity NUMBER := 0;
BEGIN
    IF l_quantity = 0 THEN
        RAISE e_empty_order;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Confirm order');
EXCEPTION
    WHEN e_empty_order THEN
        DBMS_OUTPUT.PUT_LINE(
            'Không thể xác nhận đơn hàng không có sản phẩm'
        );
END;
/
~~~

Tên exception nên mô tả điều kiện rõ ràng, chẳng hạn e_invalid_order_state, e_credit_limit_exceeded hoặc e_missing_approval, thay vì tên chung như e_error.

### 3.4 Exception tự định nghĩa không tự có thông điệp riêng

Khai báo e_invalid_amount EXCEPTION không gắn message nghiệp vụ tùy ý. Có thể:

- Ghi message trong handler.
- Dùng RAISE_APPLICATION_ERROR để trả mã và message có cấu trúc cho caller.
- Ghi log có request ID và ngữ cảnh, sau đó raise lại.

Không nên phụ thuộc vào SQLERRM của user-defined exception thuần để hiển thị thông điệp nghiệp vụ.

## 4. Phạm vi (scope) của exception

Exception được khai báo trong declarative section của block, procedure, function hoặc package. Tên exception có hiệu lực trong phạm vi từ nơi khai báo đến hết block và trong các block con lồng bên trong.

### 4.1 Exception khai báo ở block cha

~~~sql
DECLARE
    e_invalid_state EXCEPTION;
BEGIN
    BEGIN
        RAISE e_invalid_state;
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('Inner block nhận lỗi');
            RAISE;
    END;
EXCEPTION
    WHEN e_invalid_state THEN
        DBMS_OUTPUT.PUT_LINE('Outer block xử lý lỗi');
END;
/
~~~

Block con có thể dùng exception khai báo ở block cha. Handler bên trong bắt lỗi bằng WHEN OTHERS, sau đó bare RAISE; truyền lại exception hiện tại để block cha bắt bằng tên cụ thể.

### 4.2 Exception khai báo trong block con

~~~sql
BEGIN
    DECLARE
        e_local_error EXCEPTION;
    BEGIN
        RAISE e_local_error;
    END;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Lỗi từ block con đã truyền ra');
END;
/
~~~

Block cha có thể bắt bằng OTHERS, hoặc dùng một exception có phạm vi rộng hơn nếu cần hợp đồng lỗi có tên.

### 4.3 Exception dùng chung giữa package và caller

Nếu nhiều procedure cần trả cùng một loại lỗi nghiệp vụ, có thể khai báo exception trong package specification:

~~~sql
CREATE OR REPLACE PACKAGE order_errors AS
    e_invalid_order_state EXCEPTION;
    e_credit_limit_exceeded EXCEPTION;
END order_errors;
/
~~~

Caller có thể xử lý:

~~~sql
BEGIN
    order_service.confirm_order(1001);
EXCEPTION
    WHEN order_errors.e_invalid_order_state THEN
        DBMS_OUTPUT.PUT_LINE('Đơn hàng không ở trạng thái cho phép');
    WHEN order_errors.e_credit_limit_exceeded THEN
        DBMS_OUTPUT.PUT_LINE('Vượt hạn mức tín dụng');
END;
/
~~~

Ví dụ giả định package order_service raise các exception tương ứng đã được công bố. Package specification đóng vai trò hợp đồng lỗi giữa các module; không cần để mọi exception nội bộ lộ ra ngoài.

## 5. Exception propagation: truyền lỗi qua các block

Nếu một block không có handler phù hợp, exception được truyền ra block bao ngoài hoặc caller. Đây gọi là exception propagation.

### 5.1 Không xử lý ở tầng thấp nếu không biết cách phục hồi

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE update_order (
    p_order_id IN NUMBER
)
AS
BEGIN
    UPDATE orders
    SET status = 'CONFIRMED'
    WHERE order_id = p_order_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20011,
            'Order does not exist'
        );
    END IF;
END;
/
~~~

Procedure không tự COMMIT và không nuốt lỗi. Caller có thể quyết định transaction boundary và thông báo cho ứng dụng.

### 5.2 Bắt rồi raise lại

~~~sql
BEGIN
    update_order(999999);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Order update failed');
        RAISE;
END;
/
~~~

Bare RAISE trong exception handler phát lại exception đang được xử lý, giữ nguyên lỗi gốc để tầng trên có thể phân loại.

### 5.3 Raise một exception khác

Một tầng có thể chuyển lỗi kỹ thuật thành lỗi nghiệp vụ khác, nhưng cần cân nhắc việc giữ nguyên nguyên nhân. Nếu thay exception gốc bằng exception khác, caller có thể mất thông tin nguyên nhân. Khi cần giữ nguyên stack, xem RAISE_APPLICATION_ERROR với tham số thứ ba TRUE hoặc ghi lại error stack/backtrace trước khi chuyển đổi.

## 6. PRAGMA EXCEPTION_INIT là gì?

PRAGMA EXCEPTION_INIT liên kết một exception đã khai báo với một mã lỗi Oracle cụ thể. Nhờ vậy, code có thể bắt một lỗi Oracle bằng tên có ý nghĩa thay vì chỉ kiểm tra SQLCODE trong WHEN OTHERS.

Cú pháp:

~~~sql
exception_name EXCEPTION;
PRAGMA EXCEPTION_INIT(exception_name, error_code);
~~~

Trong đó:

- exception_name là user-defined exception đã được khai báo trước đó trong cùng phạm vi.
- error_code là mã lỗi Oracle dạng số nguyên âm, ví dụ -2292 cho ORA-02292.

PRAGMA là chỉ thị cho compiler, không phải câu lệnh runtime và không tự phát sinh exception.

### 6.1 Ví dụ: bắt ORA-02292 bằng tên riêng

ORA-02292 xảy ra khi xóa dòng cha đang được tham chiếu bởi dòng con trong quan hệ foreign key.

~~~sql
DECLARE
    e_child_records_exist EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_child_records_exist, -2292);
BEGIN
    DELETE FROM departments
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Department deleted');
EXCEPTION
    WHEN e_child_records_exist THEN
        DBMS_OUTPUT.PUT_LINE(
            'Không thể xóa phòng ban vì vẫn còn bản ghi con'
        );
    WHEN OTHERS THEN
        RAISE;
END;
/
~~~

Nếu DELETE vi phạm foreign key do còn bản ghi con, Oracle phát sinh ORA-02292. PL/SQL nhận diện mã -2292 và chuyển nó vào handler có tên e_child_records_exist.

Tên exception diễn tả ý nghĩa nghiệp vụ của lỗi tốt hơn việc để caller phải biết mã ORA.

### 6.2 PRAGMA không thay đổi lỗi gốc

PRAGMA EXCEPTION_INIT không đổi mã lỗi Oracle và không thay đổi nguyên nhân. Nó chỉ gắn tên PL/SQL vào mã lỗi để có thể viết:

~~~sql
WHEN e_child_records_exist THEN
~~~

thay vì:

~~~sql
WHEN OTHERS THEN
    IF SQLCODE = -2292 THEN
        ...
    ELSE
        RAISE;
    END IF;
~~~

Cách dùng tên exception giúp code rõ hơn, tránh nhầm mã lỗi và tách logic xử lý khỏi việc so sánh số trong handler tổng quát.

### 6.3 Chọn mã lỗi chưa có predefined exception phù hợp

Nên dùng PRAGMA EXCEPTION_INIT cho một ORA error cụ thể mà PL/SQL chưa có tên predefined phù hợp, ví dụ một lỗi constraint hoặc lỗi khóa cần được xử lý riêng.

Không cần khai báo lại các exception đã có tên predefined như DUP_VAL_ON_INDEX hoặc NO_DATA_FOUND. Dùng tên chuẩn sẵn có giúp người đọc nhận ra ý nghĩa và giữ tính nhất quán.

### 6.4 PRAGMA không phải RAISE_APPLICATION_ERROR

| Cơ chế | Mục đích |
|---|---|
| PRAGMA EXCEPTION_INIT | Gắn tên exception với mã lỗi đã có |
| RAISE e_name | Chủ động raise exception đã khai báo |
| RAISE; | Raise lại exception hiện tại trong handler |
| RAISE_APPLICATION_ERROR | Phát sinh mã lỗi và thông điệp ứng dụng |

PRAGMA không tạo mã lỗi mới. RAISE_APPLICATION_ERROR mới là API để phát ra lỗi ứng dụng trong dải mã dành riêng.

## 7. RAISE_APPLICATION_ERROR và mã lỗi ứng dụng

RAISE_APPLICATION_ERROR thuộc package DBMS_STANDARD, được dùng trong PL/SQL để trả mã lỗi do ứng dụng định nghĩa.

Cú pháp:

~~~sql
RAISE_APPLICATION_ERROR(
    error_code,
    message
    [, {TRUE | FALSE}]
);
~~~

Quy tắc:

- error_code phải nằm trong khoảng -20000 đến -20999.
- message là thông điệp giải thích lỗi.
- Tham số thứ ba tùy chọn: TRUE thêm lỗi mới lên error stack; FALSE thay thế error stack hiện tại. Mặc định là FALSE.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE validate_transfer (
    p_amount IN NUMBER
)
AS
BEGIN
    IF p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Transfer amount must be greater than zero'
        );
    END IF;
END;
/
~~~

Caller nhận được ORA-20020 cùng message. Mã lỗi có thể được dùng trong API contract, log hoặc mapping sang mã lỗi HTTP ở tầng ứng dụng.

### 7.1 Kết hợp PRAGMA với mã lỗi ứng dụng

Có thể đặt tên cho một mã ứng dụng để caller bắt bằng exception:

~~~sql
DECLARE
    e_invalid_transfer_amount EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_invalid_transfer_amount, -20020);
BEGIN
    validate_transfer(-50);
EXCEPTION
    WHEN e_invalid_transfer_amount THEN
        DBMS_OUTPUT.PUT_LINE(
            'Số tiền chuyển không hợp lệ'
        );
END;
/
~~~

Ở đây:

1. Procedure raise ORA-20020 bằng RAISE_APPLICATION_ERROR.
2. PRAGMA liên kết mã -20020 với tên e_invalid_transfer_amount.
3. Caller bắt lỗi bằng tên exception.

Đây là cách tạo hợp đồng lỗi có tên và mã ổn định. Cần quản lý dải mã -20000..-20999 để tránh hai module dùng cùng một mã cho ý nghĩa khác nhau.

### 7.2 Khi nào dùng tham số TRUE?

Nếu đang xử lý một exception và cần bổ sung lỗi ứng dụng nhưng giữ thông tin lỗi trước đó trên stack, có thể dùng:

~~~sql
RAISE_APPLICATION_ERROR(
    -20030,
    'Order processing failed',
    TRUE
);
~~~

TRUE thêm lỗi mới lên trên stack hiện có. FALSE (mặc định) thay stack hiện tại bằng lỗi mới. Hãy chọn theo nhu cầu chẩn đoán; không dùng TRUE như một cách tự động bảo toàn mọi ngữ cảnh nếu code đã bắt và thay đổi luồng trước đó.

## 8. SQLCODE và SQLERRM

Hai hàm này giúp đọc mã lỗi và thông điệp trong exception handler.

### 8.1 SQLCODE

SQLCODE trả mã của exception đang được xử lý:

- Lỗi Oracle thường trả mã âm.
- NO_DATA_FOUND có mã PL/SQL +100.
- User-defined exception thuần thường trả +1.
- Exception được ánh xạ bằng PRAGMA EXCEPTION_INIT trả mã đã liên kết.

### 8.2 SQLERRM

SQLERRM trả thông điệp của exception hiện tại trong handler. Có thể gọi:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
        RAISE;
~~~

Không nên chỉ log message mà bỏ mã lỗi, vì message có thể phụ thuộc ngôn ngữ hoặc phiên bản; mã lỗi giúp phân loại ổn định hơn.

### 8.3 Log exception và giữ lỗi gốc

~~~sql
BEGIN
    perform_business_operation;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'SQLCODE=' || SQLCODE ||
            ', SQLERRM=' || SQLERRM
        );
        RAISE;
END;
/
~~~

Trong ứng dụng thực tế, thay DBMS_OUTPUT bằng logger phù hợp. Sau khi ghi log, RAISE; truyền lại lỗi gốc để caller vẫn biết thao tác thất bại.

### 8.4 Error stack và backtrace

SQLERRM thường cho thông điệp của exception hiện tại. Khi cần chẩn đoán sâu hơn, có thể dùng:

~~~sql
DBMS_UTILITY.FORMAT_ERROR_STACK
DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
DBMS_UTILITY.FORMAT_CALL_STACK
~~~

- FORMAT_ERROR_STACK: trả error stack hiện tại.
- FORMAT_ERROR_BACKTRACE: cho biết đường đi đến vị trí exception phát sinh.
- FORMAT_CALL_STACK: mô tả call stack tại thời điểm gọi.

Ví dụ:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
~~~

Backtrace đặc biệt hữu ích khi exception được raise ở procedure sâu bên dưới nhưng chỉ được xử lý ở tầng cao.

## 9. Thứ tự và phạm vi của exception handler

### 9.1 Mỗi handler xử lý một nhóm exception

~~~sql
BEGIN
    -- Các câu lệnh nghiệp vụ.
    NULL;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        -- Xử lý không có dòng.
        NULL;
    WHEN DUP_VAL_ON_INDEX THEN
        -- Xử lý duplicate.
        NULL;
    WHEN OTHERS THEN
        -- Xử lý lỗi chưa phân loại.
        RAISE;
END;
/
~~~

WHEN OTHERS phải đặt cuối danh sách handler. Nó là nhánh bắt các exception còn lại không được xử lý bởi handler cụ thể phía trên.

### 9.2 Không đặt WHEN OTHERS trước handler cụ thể

Một handler tổng quát ở cuối giúp bảo vệ lỗi chưa dự kiến. Đặt nó ở giữa sẽ làm các handler sau không thể được dùng đúng cấu trúc PL/SQL.

### 9.3 Handler không tự bắt lỗi phát sinh bên trong chính handler

Nếu code trong handler tiếp tục gây lỗi, lỗi mới không được xử lý bởi các handler khác trong cùng exception section. Nó sẽ truyền ra block bao ngoài. Vì vậy logger, cleanup và thao tác phục hồi trong handler cũng cần có thiết kế lỗi riêng.

### 9.4 Không nuốt exception bằng NULL

Đoạn sau thường nguy hiểm:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

Nó làm caller tưởng procedure thành công dù thao tác có thể thất bại. Chỉ bỏ qua exception khi tình huống được xác định rõ là không ảnh hưởng nghiệp vụ, và cần ghi nhận lý do cùng trạng thái.

## 10. Transaction và exception

Exception handling không đồng nghĩa với transaction handling. Khi một câu SQL lỗi, Oracle thường rollback các thay đổi của chính câu lệnh đó; các thay đổi trước đó trong transaction vẫn có thể còn pending.

Ví dụ:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    -- INSERT sau đây có thể vi phạm constraint.
    INSERT INTO transfer_log (
        transfer_id,
        account_id,
        amount
    )
    VALUES (
        -1,
        10,
        100
    );
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE('Duplicate transfer id');
        -- UPDATE trước đó không tự động rollback ở đây.
END;
/
~~~

Nếu hai thay đổi thuộc cùng một nghiệp vụ và phải cùng thành công hoặc cùng thất bại, caller cần ROLLBACK transaction khi xử lý lỗi:

~~~sql
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        ROLLBACK;
        RAISE;
~~~

Không tự COMMIT hoặc ROLLBACK trong procedure dùng chung nếu caller đang sở hữu transaction lớn hơn, trừ khi hợp đồng của procedure quy định rõ nó sở hữu transaction. Transaction ownership cần nhất quán giữa các tầng.

## 11. Kết hợp predefined, user-defined và EXCEPTION_INIT trong một module

Một procedure nghiệp vụ có thể xử lý ba nhóm lỗi:

1. Lỗi Oracle đã có predefined name.
2. Lỗi Oracle có ORA code nhưng chưa có tên phù hợp.
3. Điều kiện nghiệp vụ do ứng dụng tự phát hiện.

Ví dụ một procedure kiểm tra tồn kho:

~~~sql
CREATE OR REPLACE PROCEDURE reserve_inventory (
    p_product_id IN NUMBER,
    p_quantity   IN NUMBER
)
AS
    e_invalid_quantity EXCEPTION;
    l_available inventory.available_qty%TYPE;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE e_invalid_quantity;
    END IF;

    SELECT available_qty
    INTO l_available
    FROM inventory
    WHERE product_id = p_product_id
    FOR UPDATE;

    IF l_available < p_quantity THEN
        RAISE_APPLICATION_ERROR(
            -20041,
            'Insufficient inventory'
        );
    END IF;

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id;

EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20042,
            'Product does not exist'
        );
    WHEN e_invalid_quantity THEN
        RAISE_APPLICATION_ERROR(
            -20043,
            'Quantity must be greater than zero'
        );
    WHEN OTHERS THEN
        RAISE;
END;
/
~~~

Procedure trên dùng NO_DATA_FOUND cho tình huống không tìm thấy sản phẩm, exception tự định nghĩa cho số lượng không hợp lệ và RAISE_APPLICATION_ERROR cho các lỗi nghiệp vụ có mã riêng. Nó không tự COMMIT; caller sở hữu transaction.

Một lỗi ORA cụ thể chưa có predefined exception phù hợp có thể được bổ sung bằng exception declaration và PRAGMA EXCEPTION_INIT trong cùng phần khai báo. Không thêm handler cho lỗi mà procedure không thể thực sự phát sinh.

## 12. Thiết kế exception contract cho package

Một package có thể công bố exception nghiệp vụ để nhiều caller xử lý thống nhất.

### 12.1 Khai báo public exception và mã liên kết

~~~sql
CREATE OR REPLACE PACKAGE inventory_errors AS
    e_invalid_quantity EXCEPTION;
    e_insufficient_stock EXCEPTION;
    e_product_not_found EXCEPTION;

    PRAGMA EXCEPTION_INIT(e_invalid_quantity, -20051);
    PRAGMA EXCEPTION_INIT(e_insufficient_stock, -20052);
    PRAGMA EXCEPTION_INIT(e_product_not_found, -20053);
END inventory_errors;
/
~~~

### 12.2 Package service phát mã lỗi tương ứng

~~~sql
CREATE OR REPLACE PACKAGE inventory_service AS
    PROCEDURE reserve (
        p_product_id IN NUMBER,
        p_quantity   IN NUMBER
    );
END inventory_service;
/

CREATE OR REPLACE PACKAGE BODY inventory_service AS
    PROCEDURE reserve (
        p_product_id IN NUMBER,
        p_quantity   IN NUMBER
    )
    AS
        l_available NUMBER;
    BEGIN
        IF p_quantity <= 0 THEN
            RAISE_APPLICATION_ERROR(
                -20051,
                'Quantity must be greater than zero'
            );
        END IF;

        SELECT available_qty
        INTO l_available
        FROM inventory
        WHERE product_id = p_product_id
        FOR UPDATE;

        IF l_available < p_quantity THEN
            RAISE_APPLICATION_ERROR(
                -20052,
                'Insufficient stock'
            );
        END IF;

        UPDATE inventory
        SET available_qty = available_qty - p_quantity
        WHERE product_id = p_product_id;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
                -20053,
                'Product not found'
            );
    END reserve;
END inventory_service;
/
~~~

### 12.3 Caller xử lý theo exception name

~~~sql
BEGIN
    inventory_service.reserve(100, -5);
EXCEPTION
    WHEN inventory_errors.e_invalid_quantity THEN
        DBMS_OUTPUT.PUT_LINE('Số lượng không hợp lệ');
    WHEN inventory_errors.e_insufficient_stock THEN
        DBMS_OUTPUT.PUT_LINE('Không đủ hàng');
    WHEN inventory_errors.e_product_not_found THEN
        DBMS_OUTPUT.PUT_LINE('Không tìm thấy sản phẩm');
END;
/
~~~

Caller không cần hard-code mã -20051, -20052 hoặc -20053 trong từng module. Package specification công bố tên lỗi và PRAGMA liên kết tên đó với mã ứng dụng.

## 13. Exception trong procedure, function và trigger

### 13.1 Procedure và function

Procedure/function có thể khai báo exception cục bộ hoặc dùng exception package. Nếu không xử lý, lỗi truyền về caller. Với function được gọi trong SQL statement, exception có thể làm câu SQL gọi function thất bại.

### 13.2 Trigger

Trigger có thể dùng predefined exception, user-defined exception và PRAGMA EXCEPTION_INIT như block PL/SQL khác.

Ví dụ kiểm tra quy tắc:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_validate
BEFORE INSERT OR UPDATE ON orders
FOR EACH ROW
DECLARE
    e_invalid_amount EXCEPTION;
BEGIN
    IF :NEW.total_amount < 0 THEN
        RAISE e_invalid_amount;
    END IF;
EXCEPTION
    WHEN e_invalid_amount THEN
        RAISE_APPLICATION_ERROR(
            -20061,
            'Order amount cannot be negative'
        );
END;
/
~~~

Trigger raise exception sẽ làm câu DML kích hoạt trigger thất bại. Câu DML đó bị rollback theo tính nguyên tử của statement. Không dùng trigger để nuốt lỗi constraint hoặc che trạng thái dữ liệu không hợp lệ.

### 13.3 Không commit trong trigger thông thường

Trigger chạy trong ngữ cảnh transaction của câu lệnh kích hoạt nó. Không thực hiện COMMIT/ROLLBACK thông thường trong trigger; các thao tác transaction control có giới hạn và có thể gây lỗi. Hãy để caller quản lý transaction và dùng exception để báo lỗi.

## 14. Ghi log lỗi đúng cách

Một handler ghi log nên giữ các thông tin đủ để điều tra:

- SQLCODE và SQLERRM.
- FORMAT_ERROR_STACK.
- FORMAT_ERROR_BACKTRACE.
- Tên module/procedure và bước nghiệp vụ.
- Request ID hoặc business key không nhạy cảm.
- Thời điểm phát sinh và correlation ID.

Ví dụ:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        error_logger.write_error(
            p_error_code => SQLCODE,
            p_error_text => SQLERRM,
            p_error_stack =>
                DBMS_UTILITY.FORMAT_ERROR_STACK,
            p_backtrace =>
                DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
~~~

ERROR_LOGGER.WRITE_ERROR là procedure giả định của ứng dụng. Nếu logger ghi trong cùng transaction, bản ghi log có thể bị rollback cùng nghiệp vụ. Nếu cần lưu log độc lập, phải thiết kế cơ chế riêng và hiểu rõ transaction boundary; không tự ý commit thay đổi nghiệp vụ từ exception handler.

Không ghi password, access token, dữ liệu thanh toán hoặc thông tin cá nhân nhạy cảm vào log. SQLERRM đôi khi chứa giá trị hoặc tên đối tượng hữu ích cho chẩn đoán; áp dụng chính sách mask phù hợp.

## 15. Lỗi thường gặp và cách xử lý

| Lỗi thiết kế | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng WHEN OTHERS cho mọi trường hợp | Mất khả năng phân loại lỗi | Bắt predefined/user-defined cụ thể trước |
| Không có handler cho lỗi dự kiến | Lỗi truyền thẳng ra caller ngoài ý muốn | Xác định exception contract |
| Khai báo exception nhưng không RAISE | Handler không bao giờ chạy | Raise khi điều kiện thực sự xảy ra |
| Dùng RAISE e_name để mong có message tùy ý | SQLERRM chỉ là User-Defined Exception nếu không có mapping | Dùng RAISE_APPLICATION_ERROR hoặc logger |
| So sánh SQLCODE trong nhiều nhánh OTHERS | Code khó đọc và dễ bỏ sót | Dùng PRAGMA EXCEPTION_INIT để đặt tên lỗi |
| Dùng PRAGMA cho lỗi đã có predefined name | Trùng lặp và gây nhầm lẫn | Dùng tên exception chuẩn |
| Nhầm PRAGMA với RAISE_APPLICATION_ERROR | PRAGMA không tự phát sinh lỗi | Dùng đúng API theo mục đích |
| Bắt lỗi rồi không raise lại | Caller có thể tưởng thành công | RAISE nếu tầng hiện tại không phục hồi hoàn chỉnh |
| Dùng RAISE e_other để chuyển lỗi nhưng mất gốc | Mất mã và backtrace ban đầu | Ghi stack/backtrace hoặc dùng chiến lược giữ stack |
| Đặt WHEN OTHERS trước handler cụ thể | Handler không hợp lệ về cấu trúc/ý định | Đặt OTHERS cuối |
| Nuốt lỗi bằng NULL | Che giấu thất bại | Chỉ bỏ qua khi có chính sách rõ và log |
| Nghĩ exception tự rollback toàn transaction | DML trước đó có thể vẫn pending | Caller rollback đúng phạm vi |
| Dùng ROLLBACK trong procedure dùng chung | Có thể hủy thay đổi của caller | Quy định transaction owner |
| Chuyển mọi lỗi thành ORA-20000 chung | Caller mất khả năng phân loại | Duy trì mã lỗi ổn định, riêng biệt |
| Ghi log rồi commit trong handler | Có thể commit nghiệp vụ ngoài ý muốn | Tách logging transaction theo thiết kế |

## 16. Bài lab: ba cách xử lý lỗi

Các block sau dùng PL/SQL và có thể chạy trong schema thực hành với SET SERVEROUTPUT ON. Những ví dụ DML trên bảng mẫu chỉ chạy nếu bảng/constraint tương ứng tồn tại và dữ liệu được phép thay đổi.

### 16.1 Bắt predefined exception

~~~sql
SET SERVEROUTPUT ON

DECLARE
    l_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO l_name
    FROM employees
    WHERE employee_id = -999;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('NO_DATA_FOUND was handled');
END;
/
~~~

Quan sát SELECT INTO không có dòng và handler NO_DATA_FOUND được chạy.

### 16.2 Raise user-defined exception

~~~sql
DECLARE
    e_invalid_quantity EXCEPTION;
    l_quantity NUMBER := -3;
BEGIN
    IF l_quantity <= 0 THEN
        RAISE e_invalid_quantity;
    END IF;
EXCEPTION
    WHEN e_invalid_quantity THEN
        DBMS_OUTPUT.PUT_LINE('Quantity must be positive');
END;
/
~~~

Thay l_quantity bằng 3 để thấy luồng không phát sinh exception.

### 16.3 Ánh xạ ORA-02292

~~~sql
DECLARE
    e_child_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_child_exists, -2292);
BEGIN
    -- Chỉ chạy nếu schema có quan hệ parent-child phù hợp.
    DELETE FROM departments
    WHERE department_id = 10;
EXCEPTION
    WHEN e_child_exists THEN
        DBMS_OUTPUT.PUT_LINE(
            'ORA-02292 được bắt bằng e_child_exists'
        );
    WHEN OTHERS THEN
        RAISE;
END;
/
~~~

Để kiểm tra, cần chọn parent row đang có child row. Không xóa dữ liệu thật chỉ để thử exception.

### 16.4 Tạo và bắt mã lỗi ứng dụng

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_invalid_amount, -20071);
BEGIN
    RAISE_APPLICATION_ERROR(
        -20071,
        'Amount must be greater than zero'
    );
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE(
            'Application error handled by named exception'
        );
END;
/
~~~

Ví dụ cho thấy mã lỗi do RAISE_APPLICATION_ERROR phát ra có thể được liên kết với tên exception bằng PRAGMA.

### 16.5 Quan sát SQLCODE và SQLERRM

~~~sql
DECLARE
    e_invalid_state EXCEPTION;
BEGIN
    RAISE e_invalid_state;
EXCEPTION
    WHEN e_invalid_state THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
END;
/
~~~

Quan sát mã của user-defined exception thuần và backtrace tại vị trí raise.

## 17. Checklist thiết kế exception

Trước khi hoàn thiện procedure, function hoặc trigger, hãy xác định:

1. Những lỗi Oracle nào có predefined exception tương ứng?
2. Điều kiện nghiệp vụ nào cần user-defined exception?
3. ORA code nào chưa có predefined name nhưng cần xử lý riêng?
4. Có nên ánh xạ mã đó bằng PRAGMA EXCEPTION_INIT không?
5. Mã lỗi ứng dụng nào cần phát ra bằng RAISE_APPLICATION_ERROR?
6. Tên exception có ý nghĩa và có phạm vi phù hợp không?
7. Exception nào là public contract của package, exception nào chỉ nội bộ?
8. Handler có bắt lỗi cụ thể trước WHEN OTHERS không?
9. Handler có phục hồi hoàn chỉnh hay cần RAISE lại?
10. SQLCODE, SQLERRM và backtrace có được ghi log đủ không?
11. Logger có vô tình che lỗi gốc hoặc commit transaction không?
12. Caller hay procedure sở hữu COMMIT/ROLLBACK?
13. Khi một statement lỗi, các DML trước đó có cần rollback không?
14. Mã -20000..-20999 có được quản lý tránh trùng ý nghĩa không?
15. Các exception contract có được kiểm thử từ cả PL/SQL caller và ứng dụng ngoài không?

## 18. Tổng kết

PL/SQL có ba cách quan trọng để định danh và xử lý lỗi:

- **Predefined exceptions** là các tên Oracle có sẵn như NO_DATA_FOUND, TOO_MANY_ROWS, ZERO_DIVIDE và DUP_VAL_ON_INDEX. Dùng chúng khi lỗi phát sinh thuộc nhóm đã được định nghĩa.
- **User-defined exceptions** được khai báo trong PL/SQL bằng exception_name EXCEPTION; và chủ động phát sinh bằng RAISE exception_name;. Chúng phù hợp với điều kiện nghiệp vụ do ứng dụng xác định.
- **PRAGMA EXCEPTION_INIT** gắn một user-defined exception với mã lỗi Oracle âm, giúp bắt ORA error bằng tên có ý nghĩa. PRAGMA không tự raise lỗi và không thay đổi mã lỗi gốc.
- **RAISE_APPLICATION_ERROR** phát sinh mã và message ứng dụng trong khoảng -20000 đến -20999; có thể kết hợp PRAGMA để caller bắt mã đó bằng tên exception.
- **SQLCODE, SQLERRM và FORMAT_ERROR_BACKTRACE** giúp phân loại và điều tra lỗi.
- **RAISE** trong handler truyền lại exception hiện tại. Không nuốt lỗi nếu tầng hiện tại chưa phục hồi hoàn chỉnh.
- Exception handling không tự quyết định transaction. Caller cần quản lý COMMIT/ROLLBACK đúng ranh giới nghiệp vụ.

Một thiết kế lỗi tốt đặt tên rõ cho từng tình huống, giữ được nguyên nhân gốc, công bố hợp đồng nhất quán giữa các module và để transaction được quản lý bởi đúng tầng sở hữu nó.
