# WHEN OTHERS, truyền tiếp lỗi và tránh che giấu giao dịch thất bại trong PL/SQL

PL/SQL dùng exception để báo hiệu một thao tác không thể tiếp tục theo luồng bình thường. Khi lỗi xuất hiện, Oracle tìm exception handler phù hợp trong block hiện tại rồi lan truyền lỗi lên các block gọi nếu không có handler xử lý. Cách viết handler quyết định lỗi có được ghi nhận, có đến được caller và ứng dụng có vô tình coi một giao dịch thất bại là thành công hay không.

Mệnh đề **WHEN OTHERS** bắt mọi exception chưa được xử lý bởi handler cụ thể trong block. Đây là công cụ hữu ích ở ranh giới xử lý cuối cùng, nhưng rất nguy hiểm nếu handler chỉ ghi log rồi tiếp tục như thể công việc đã thành công. Trong phần lớn trường hợp, sau khi ghi nhận thông tin cần thiết, hãy dùng **RAISE** để truyền lại exception hiện tại.

Bài học này trình bày phạm vi exception, thứ tự handler, RAISE và RAISE_APPLICATION_ERROR, thông tin lỗi và backtrace, khác biệt giữa statement rollback và transaction rollback, SAVEPOINT, logging, lỗi trong trigger và các mẫu code giúp tránh che giấu giao dịch thất bại.

## 1. Exception trong PL/SQL

Exception là sự kiện bất thường làm luồng thực thi rời khỏi câu lệnh hiện tại. Ví dụ:

- SELECT INTO không tìm thấy dòng.
- SELECT INTO trả về nhiều hơn một dòng.
- INSERT vi phạm PRIMARY KEY hoặc UNIQUE constraint.
- Chia cho 0.
- Chương trình chủ động gọi RAISE hoặc RAISE_APPLICATION_ERROR.
- Một trigger phát hiện dữ liệu không hợp lệ và từ chối DML.

PL/SQL có thể xử lý exception bằng phần EXCEPTION của block:

~~~sql
DECLARE
    v_salary NUMBER;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE(v_salary);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
END;
/
~~~

Nếu SELECT không trả dòng, Oracle chuyển điều khiển đến handler NO_DATA_FOUND. Câu lệnh sau SELECT trong phần BEGIN không được chạy.

### 1.1. Cấu trúc block có exception handler

~~~sql
DECLARE
    -- Khai báo biến, cursor, exception.
BEGIN
    -- Câu lệnh bình thường.
EXCEPTION
    WHEN exception_name THEN
        -- Xử lý lỗi cụ thể.
    WHEN OTHERS THEN
        -- Xử lý các lỗi còn lại.
END;
/
~~~

Phần EXCEPTION là tùy chọn. Một block có thể có nhiều handler, nhưng mỗi exception chỉ chuyển đến một handler phù hợp đầu tiên theo quy tắc khớp của PL/SQL.

### 1.2. Exception không phải giá trị trả về bình thường

Khi exception được bắt và handler kết thúc bình thường, chương trình tiếp tục sau END của block đã xử lý lỗi. Nếu exception không được xử lý trong block đó, nó lan truyền ra block bao ngoài hoặc caller.

Điều này quan trọng khi block con nằm trong procedure hoặc vòng lặp: bắt lỗi ở block con có thể cho phép chương trình tiếp tục; để lỗi lan ra ngoài có thể làm dừng toàn bộ lời gọi hiện tại.

## 2. Các loại exception

PL/SQL thường gặp ba nhóm:

1. Predefined exceptions: Oracle đã định nghĩa tên exception.
2. Non-predefined Oracle errors: lỗi Oracle có mã nhưng chưa có tên predefined tương ứng trong chương trình.
3. User-defined exceptions: lập trình viên tự khai báo và phát sinh theo quy tắc nghiệp vụ.

### 2.1. Predefined exceptions

| Exception | Tình huống thường gặp |
|---|---|
| NO_DATA_FOUND | SELECT INTO không trả dòng |
| TOO_MANY_ROWS | SELECT INTO trả nhiều dòng |
| ZERO_DIVIDE | Chia cho 0 |
| DUP_VAL_ON_INDEX | Vi phạm unique index/constraint |
| INVALID_CURSOR | Thao tác cursor không hợp lệ |
| CURSOR_ALREADY_OPEN | Mở cursor đang mở |
| VALUE_ERROR | Chuyển đổi hoặc kích thước giá trị không phù hợp |
| STORAGE_ERROR | Lỗi bộ nhớ PL/SQL |

Ví dụ:

~~~sql
DECLARE
    v_result NUMBER;
BEGIN
    v_result := 10 / 0;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Cannot divide by zero');
END;
/
~~~

### 2.2. User-defined exception

Khai báo exception trong phần DECLARE rồi phát sinh bằng RAISE:

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
    v_amount NUMBER := -10;
BEGIN
    IF v_amount < 0 THEN
        RAISE e_invalid_amount;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Amount accepted');
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE('Amount must not be negative');
END;
/
~~~

User-defined exception giúp biểu đạt điều kiện nghiệp vụ có tên rõ ràng. Nếu caller cần nhận mã lỗi Oracle cụ thể, có thể ánh xạ bằng PRAGMA EXCEPTION_INIT hoặc dùng RAISE_APPLICATION_ERROR.

### 2.3. Non-predefined Oracle error và EXCEPTION_INIT

PRAGMA EXCEPTION_INIT gắn tên exception do chương trình khai báo với mã Oracle:

~~~sql
DECLARE
    e_child_records_exist EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_child_records_exist, -2292);
BEGIN
    DELETE FROM departments
    WHERE department_id = 10;
EXCEPTION
    WHEN e_child_records_exist THEN
        DBMS_OUTPUT.PUT_LINE(
            'Department still has dependent rows'
        );
END;
/
~~~

Mã -2292 tương ứng lỗi integrity constraint khi xóa bản ghi cha còn bản ghi con tham chiếu. Việc bắt exception theo tên giúp code dễ đọc hơn so với so sánh SQLCODE ở nhiều nơi.

## 3. WHEN OTHERS là gì?

WHEN OTHERS là handler tổng quát bắt mọi exception chưa được một handler cụ thể trước đó xử lý trong cùng block:

~~~sql
BEGIN
    -- Các thao tác.
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Unexpected error: ' || SQLERRM
        );
END;
/
~~~

Handler này không phân biệt lỗi do dữ liệu, quyền, cấu hình, lỗi lập trình hay lỗi hệ thống. Vì vậy, dùng WHEN OTHERS để ghi nhận hoặc bổ sung ngữ cảnh có thể hợp lý; dùng nó để biến mọi lỗi thành kết quả thành công là một lỗi thiết kế nghiêm trọng.

### 3.1. WHEN OTHERS phải đặt sau các handler cụ thể

Ví dụ:

~~~sql
BEGIN
    -- Work.
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        -- Xử lý trường hợp không tìm thấy.
    WHEN DUP_VAL_ON_INDEX THEN
        -- Xử lý trùng khóa.
    WHEN OTHERS THEN
        -- Xử lý các lỗi còn lại.
        RAISE;
END;
/
~~~

WHEN OTHERS là nhánh tổng quát, nên phải đứng cuối danh sách handler. Không đặt handler cụ thể sau nó.

### 3.2. Không cần WHEN OTHERS nếu không có xử lý phù hợp

Nếu block không cần bổ sung thông tin hoặc khôi phục trạng thái, để exception tự lan truyền thường tốt hơn:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;
END;
/
~~~

Nếu UPDATE thất bại, caller nhận lỗi gốc. Không cần bắt rồi RAISE lại chỉ để tạo thêm code.

## 4. Vì sao WHEN OTHERS rồi bỏ qua lỗi nguy hiểm?

Xem ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE transfer_money_bad (
    p_from_account IN NUMBER,
    p_to_account   IN NUMBER,
    p_amount       IN NUMBER
)
AS
BEGIN
    UPDATE accounts
    SET balance = balance - p_amount
    WHERE account_id = p_from_account;

    UPDATE accounts
    SET balance = balance + p_amount
    WHERE account_id = p_to_account;

EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Transfer failed: ' || SQLERRM);
        -- Không RAISE, lỗi bị nuốt.
END;
/
~~~

Nếu câu UPDATE thứ hai thất bại, procedure bắt lỗi rồi kết thúc bình thường. Caller có thể không biết giao dịch chuyển tiền đã thất bại. Nếu caller chỉ dựa vào việc procedure trả về bình thường, hệ thống có thể báo thành công sai.

Đặc biệt, câu UPDATE thứ nhất có thể đã thành công và thay đổi của nó vẫn còn trong transaction. Việc handler bỏ qua exception không tự hoàn tác câu UPDATE đầu tiên.

### 4.1. Các hậu quả của việc nuốt exception

- Caller không nhận được lỗi để quyết định retry, rollback hoặc báo thất bại.
- Ứng dụng có thể trả trạng thái SUCCESS dù dữ liệu chưa hoàn tất.
- Một phần thao tác có thể vẫn nằm trong transaction.
- Job batch có thể đánh dấu bản ghi đã xử lý dù bước quan trọng thất bại.
- Trigger có thể che giấu việc từ chối dữ liệu và cho DML tiếp tục.
- Log chỉ có thông báo chung, không có mã lỗi hoặc backtrace để điều tra.

Nguyên tắc: nếu thao tác nghiệp vụ không hoàn thành, lỗi phải đến được tầng có trách nhiệm quyết định transaction và trạng thái nghiệp vụ.

## 5. RAISE để truyền tiếp exception hiện tại

Trong exception handler, câu lệnh RAISE không có tên exception sẽ phát lại exception đang được xử lý:

~~~sql
BEGIN
    -- Work.
EXCEPTION
    WHEN OTHERS THEN
        -- Ghi nhận hoặc bổ sung ngữ cảnh.
        RAISE;
END;
/
~~~

RAISE không có tham số trong handler giữ nguyên exception hiện tại và cho phép nó lan lên caller. Đây là mẫu thông dụng khi cần ghi log nhưng không muốn thay đổi kết quả lỗi.

### 5.1. Mẫu ghi log rồi RAISE

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 20;

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

Trong ứng dụng thật, thay DBMS_OUTPUT bằng cơ chế logging được thiết kế phù hợp. RAISE bảo đảm caller vẫn nhận được lỗi gốc.

### 5.2. Khác biệt giữa RAISE và RAISE exception_name

~~~sql
RAISE;
~~~

Phát lại exception đang được xử lý; thường dùng trong exception handler.

~~~sql
RAISE e_invalid_amount;
~~~

Chủ động phát sinh một user-defined exception có tên. Dùng trong phần thực thi bình thường hoặc handler khi muốn phát sinh exception đã khai báo.

Không nhầm hai cách này. Nếu đang xử lý lỗi gốc và muốn giữ nguyên lỗi đó, dùng RAISE không tham số.

### 5.3. Không dùng RAISE SQLERRM

SQLERRM trả về thông điệp lỗi dạng ký tự; nó không phải tên exception để truyền cho RAISE. Cách đúng để truyền lại exception hiện tại là:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Log SQLERRM nếu cần.
        RAISE;
~~~

Nếu thay lỗi bằng một lỗi nghiệp vụ mới, hãy dùng RAISE_APPLICATION_ERROR có chủ đích và ghi rõ quan hệ với lỗi gốc.

## 6. RAISE_APPLICATION_ERROR

RAISE_APPLICATION_ERROR phát sinh lỗi ứng dụng với mã nằm trong khoảng -20000 đến -20999:

~~~sql
RAISE_APPLICATION_ERROR(
    -20001,
    'Amount must be greater than zero'
);
~~~

Đây là cách phổ biến để trả lỗi nghiệp vụ có mã rõ ràng cho caller.

### 6.1. Ví dụ kiểm tra tham số

~~~sql
CREATE OR REPLACE PROCEDURE create_order (
    p_order_id IN NUMBER,
    p_amount   IN NUMBER
)
AS
BEGIN
    IF p_order_id IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order ID is required'
        );
    END IF;

    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Amount must be greater than zero'
        );
    END IF;

    INSERT INTO orders (order_id, amount)
    VALUES (p_order_id, p_amount);
END;
/
~~~

Caller có thể nhận mã lỗi -20001 hoặc -20002 và hiển thị thông báo phù hợp theo hợp đồng API.

### 6.2. Tham số thứ ba TRUE/FALSE

RAISE_APPLICATION_ERROR có tham số thứ ba tùy chọn:

- FALSE hoặc bỏ qua: thay thế error stack hiện tại bằng lỗi ứng dụng mới.
- TRUE: thêm lỗi ứng dụng vào error stack hiện tại.

Ví dụ:

~~~sql
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Order already exists',
            TRUE
        );
END;
~~~

TRUE có thể giữ lại thông tin lỗi trước đó trong stack khi bổ sung thông điệp nghiệp vụ. Dù vậy, nếu mục tiêu là truyền nguyên exception hiện tại không thay đổi, RAISE vẫn là lựa chọn rõ ràng nhất.

### 6.3. Không biến mọi lỗi thành cùng một mã nghiệp vụ

Không nên bắt mọi exception rồi phát lại cùng một mã -20000 chung chung. Điều đó làm mất khả năng phân biệt:

- Dữ liệu đầu vào không hợp lệ.
- Không tìm thấy đối tượng.
- Trùng khóa.
- Hết dung lượng.
- Thiếu quyền.
- Lỗi kết nối hoặc lỗi hệ thống.

Chỉ ánh xạ lỗi khi tầng ứng dụng thực sự cần một hợp đồng lỗi mới. Nếu không, truyền exception gốc để caller có đủ thông tin.

## 7. SQLCODE và SQLERRM

Trong exception handler, PL/SQL cung cấp hai hàm thường dùng:

- SQLCODE: mã số của exception hiện tại.
- SQLERRM: thông điệp lỗi tương ứng.

Ví dụ:

~~~sql
BEGIN
    INSERT INTO departments (department_id, department_name)
    VALUES (10, 'Duplicate');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Code: ' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message: ' || SQLERRM);
        RAISE;
END;
/
~~~

SQLCODE/SQLERRM hữu ích cho log và phân loại lỗi, nhưng không đủ để định vị chính xác dòng PL/SQL đã phát sinh lỗi.

### 7.1. Không gọi SQLCODE/SQLERRM sau khi đã rời handler

Thông tin exception hiện tại có ý nghĩa trong exception handler. Nếu cần sử dụng sau đó, hãy lưu mã và thông điệp vào biến cục bộ ngay khi bắt lỗi.

~~~sql
DECLARE
    v_error_code NUMBER;
    v_error_text VARCHAR2(4000);
BEGIN
    -- Work.
EXCEPTION
    WHEN OTHERS THEN
        v_error_code := SQLCODE;
        v_error_text := SQLERRM;
        -- Dùng hai biến để ghi nhận trước khi truyền lỗi.
        RAISE;
END;
/
~~~

## 8. Error stack, backtrace và call stack

Một thông điệp SQLERRM có thể cho biết lỗi loại gì, nhưng không phải lúc nào cũng đủ để tìm vị trí phát sinh. Oracle cung cấp thêm các hàm chẩn đoán.

| Hàm | Mục đích |
|---|---|
| SQLCODE | Mã lỗi hiện tại |
| SQLERRM | Thông điệp lỗi hiện tại |
| DBMS_UTILITY.FORMAT_ERROR_STACK | Chuỗi error stack |
| DBMS_UTILITY.FORMAT_ERROR_BACKTRACE | Vị trí trong PL/SQL nơi exception được phát sinh |
| DBMS_UTILITY.FORMAT_CALL_STACK | Call stack tại thời điểm gọi hàm |

Ví dụ:

~~~sql
BEGIN
    -- Câu lệnh có thể lỗi.
    DELETE FROM departments
    WHERE department_id = -999;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_CALL_STACK
        );
        RAISE;
END;
/
~~~

### 8.1. Error stack và backtrace khác nhau

- Error stack cho biết chuỗi lỗi hiện có, có thể gồm nhiều thông điệp.
- Backtrace chỉ ra vị trí PL/SQL nơi exception được phát sinh, kể cả khi nó đã lan qua nhiều block.
- Call stack mô tả chuỗi lời gọi tại thời điểm lấy thông tin; nó giúp hiểu đường gọi nhưng không thay thế backtrace.

Khi ghi log lỗi, nên lưu cả mã lỗi, error stack và backtrace nếu chính sách log cho phép. Không chỉ lưu SQLERRM rồi bỏ mất vị trí phát sinh.

### 8.2. Lưu backtrace trước khi gọi logger

Nếu logger gọi thêm nhiều thủ tục hoặc xử lý exception riêng, hãy lấy thông tin lỗi trước khi gọi logger:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        v_code      := SQLCODE;
        v_message   := SQLERRM;
        v_err_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        log_error(
            p_code      => v_code,
            p_message   => v_message,
            p_stack     => v_err_stack,
            p_backtrace => v_backtrace
        );

        RAISE;
~~~

Ví dụ là cấu trúc minh họa; khai báo biến và chữ ký LOG_ERROR phải phù hợp với ứng dụng. RAISE vẫn phải nằm trong handler đang xử lý exception gốc.

## 9. Phạm vi exception và lan truyền qua các block

PL/SQL tìm handler trong block hiện tại trước. Nếu không có handler phù hợp, exception lan truyền ra block bao ngoài. Quá trình này tiếp tục cho đến khi tìm thấy handler hoặc exception thoát khỏi lời gọi đến caller.

Ví dụ:

~~~sql
DECLARE
    e_problem EXCEPTION;
BEGIN
    BEGIN
        RAISE e_problem;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('Inner: no data');
    END;

    DBMS_OUTPUT.PUT_LINE('After inner block');
EXCEPTION
    WHEN e_problem THEN
        DBMS_OUTPUT.PUT_LINE('Outer: handled problem');
END;
/
~~~

Handler trong block con không khớp E_PROBLEM, nên exception lan ra block ngoài. Block ngoài bắt nó; dòng After inner block không chạy vì luồng điều khiển rời block con do exception.

### 9.1. Handler kết thúc bình thường thì block tiếp tục sau block đó

~~~sql
BEGIN
    BEGIN
        RAISE NO_DATA_FOUND;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('Handled inside');
    END;

    DBMS_OUTPUT.PUT_LINE('Continue outer block');
END;
/
~~~

Vì handler xử lý NO_DATA_FOUND và không phát lại lỗi, block ngoài tiếp tục chạy.

### 9.2. RAISE làm lỗi tiếp tục lan truyền

~~~sql
BEGIN
    BEGIN
        RAISE NO_DATA_FOUND;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('Logging inner error');
            RAISE;
    END;

    DBMS_OUTPUT.PUT_LINE('This line is skipped');
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Handled by outer block');
END;
/
~~~

Handler con ghi nhận rồi RAISE. Block ngoài bắt exception và tiếp tục sau handler ngoài. Dòng This line is skipped không được thực hiện.

## 10. Statement rollback và transaction rollback

Đây là điểm quan trọng khi xử lý lỗi giao dịch. Cần phân biệt:

- **Statement-level rollback**: Oracle hoàn tác tác động của câu lệnh SQL thất bại.
- **Transaction rollback**: hoàn tác các thay đổi chưa COMMIT trong toàn bộ transaction, hoặc đến một SAVEPOINT.

Một câu DML thất bại không đồng nghĩa toàn bộ transaction tự động rollback.

### 10.1. Một câu INSERT thất bại

Giả sử:

~~~sql
INSERT INTO accounts (account_id, balance)
VALUES (1, 1000);

INSERT INTO accounts (account_id, balance)
VALUES (1, 2000);
~~~

Nếu câu INSERT thứ hai vi phạm khóa chính, Oracle hoàn tác tác động của chính câu INSERT thứ hai. Dòng account_id = 1 được chèn thành công bởi câu đầu vẫn thuộc transaction hiện tại, chưa tự biến mất.

Caller có thể quyết định:

- COMMIT thay đổi hợp lệ trước đó.
- ROLLBACK toàn transaction.
- ROLLBACK TO SAVEPOINT để chỉ hoàn tác phần sau một mốc.

### 10.2. Exception trong stored procedure

Nếu procedure thực hiện nhiều DML và một DML sau đó lỗi, các DML trước đó đã thành công không mặc nhiên bị rollback chỉ vì exception thoát khỏi procedure. Caller cần quyết định transaction.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE lab_two_steps
AS
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = -1;
END;
/
~~~

Nếu câu lệnh thứ hai không cập nhật dòng nào thì không có exception tự động; nếu nó phát sinh lỗi, câu DML lỗi bị rollback ở mức statement, nhưng câu UPDATE đầu có thể vẫn còn trong transaction. Procedure không nên nuốt lỗi và để caller tưởng hai bước đã hoàn tất.

### 10.3. Trigger exception và statement rollback

Nếu trigger phát sinh exception trong lúc một câu INSERT/UPDATE/DELETE chạy, câu lệnh kích hoạt trigger thất bại. Oracle hoàn tác tác động của câu lệnh đó, bao gồm thay đổi do trigger thực hiện trong cùng statement. Các thay đổi thuộc transaction đã thực hiện trước statement vẫn có thể còn.

Điều này khác với việc một procedure chạy nhiều câu DML riêng biệt rồi gặp lỗi ở câu cuối. Hãy xác định ranh giới statement và transaction trước khi quyết định rollback.

## 11. SAVEPOINT để kiểm soát một phần transaction

SAVEPOINT đánh dấu vị trí trong transaction. ROLLBACK TO SAVEPOINT hoàn tác các thay đổi sau mốc đó mà không rollback toàn transaction.

Ví dụ:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    SAVEPOINT after_debit;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 2;

    -- Giả lập cần hủy phần sau mốc.
    ROLLBACK TO after_debit;

    -- Tiếp tục công việc khác hoặc để caller quyết định.
END;
/
~~~

Ở ví dụ này, UPDATE đầu xảy ra trước SAVEPOINT nên vẫn còn trong transaction sau ROLLBACK TO. UPDATE thứ hai bị hoàn tác.

### 11.1. SAVEPOINT trong exception handler

~~~sql
DECLARE
    v_amount NUMBER := 100;
BEGIN
    SAVEPOINT before_transfer;

    UPDATE accounts
    SET balance = balance - v_amount
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + v_amount
    WHERE account_id = -1;

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_transfer;
        RAISE;
END;
/
~~~

Handler hoàn tác phần công việc sau SAVEPOINT rồi truyền lỗi cho caller. Caller vẫn nhận exception và có thể quyết định rollback toàn transaction hoặc xử lý theo hợp đồng nghiệp vụ.

### 11.2. Không tự động rollback toàn transaction trong mọi handler

Procedure có thể được gọi bên trong một transaction lớn do caller quản lý. Nếu procedure tự ROLLBACK toàn transaction khi gặp một lỗi nhỏ, nó có thể xóa cả những thay đổi hợp lệ mà caller đã thực hiện trước đó.

Chỉ gọi ROLLBACK toàn transaction khi procedure thực sự sở hữu transaction theo hợp đồng rõ ràng. Với reusable procedure, thường nên để transaction control ở tầng gọi; nếu cần, dùng SAVEPOINT có quy ước để hoàn tác phần việc của procedure.

## 12. WHEN OTHERS trong trigger

Trigger là PL/SQL được Oracle tự động gọi khi sự kiện tương ứng xảy ra, chẳng hạn INSERT, UPDATE hoặc DELETE trên bảng. Exception trong trigger có ảnh hưởng trực tiếp đến câu lệnh kích hoạt trigger.

### 12.1. Trigger từ chối dữ liệu

~~~sql
CREATE OR REPLACE TRIGGER trg_check_order_amount
BEFORE INSERT OR UPDATE OF amount
ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount IS NULL OR :NEW.amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Order amount must be greater than zero'
        );
    END IF;
END;
/
~~~

Nếu amount không hợp lệ, trigger phát sinh lỗi. INSERT hoặc UPDATE kích hoạt trigger thất bại; caller nhận mã lỗi ứng dụng. Không nên bắt lỗi này trong trigger rồi bỏ qua, vì như vậy DML có thể tiếp tục với dữ liệu không hợp lệ.

### 12.2. WHEN OTHERS rồi RAISE trong trigger

Nếu cần ghi log hoặc bổ sung thông tin:

~~~sql
CREATE OR REPLACE TRIGGER trg_check_order_amount
BEFORE INSERT OR UPDATE OF amount
ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount IS NULL OR :NEW.amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Order amount must be greater than zero'
        );
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        -- Chỉ bổ sung chẩn đoán ở đây nếu cần.
        RAISE;
END;
/
~~~

RAISE truyền lại lỗi để câu lệnh DML bị từ chối. Nếu trigger không có thao tác cần xử lý tổng quát, không cần thêm WHEN OTHERS chỉ để viết RAISE.

### 12.3. Không COMMIT hoặc ROLLBACK trong trigger thông thường

Trigger chạy trong ngữ cảnh của câu lệnh kích hoạt nó. Trigger thông thường không được COMMIT hoặc ROLLBACK transaction của caller; cố thực hiện sẽ dẫn đến lỗi như ORA-04092. Không dùng trigger để tự commit một phần thao tác nghiệp vụ.

Nếu cần ghi audit, thường ghi trong cùng transaction để audit và DML cùng thành công hoặc cùng rollback. Nếu yêu cầu ghi nhận cả lần thất bại dù transaction rollback, cần cân nhắc logging độc lập với transaction, hiểu rõ hệ quả và giới hạn của autonomous transaction.

## 13. Logging lỗi: transaction thường và autonomous transaction

Có hai cách tổ chức logging phổ biến:

### 13.1. Log trong cùng transaction

Logger chèn bản ghi vào bảng log bằng transaction hiện tại. Ưu điểm là log nhất quán với transaction nghiệp vụ:

- Nếu nghiệp vụ COMMIT, log cũng COMMIT.
- Nếu nghiệp vụ ROLLBACK, log cũng ROLLBACK.

Nhược điểm: nếu muốn lưu dấu vết lỗi sau khi caller rollback, bản ghi log cũng bị rollback và không còn.

### 13.2. Log bằng autonomous transaction

Một procedure được khai báo PRAGMA AUTONOMOUS_TRANSACTION có transaction độc lập với caller. Nó có thể ghi log và COMMIT riêng, kể cả khi transaction nghiệp vụ sau đó rollback.

Ví dụ bảng log:

~~~sql
CREATE TABLE app_error_log (
    log_id       NUMBER GENERATED BY DEFAULT AS IDENTITY,
    logged_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    error_code   NUMBER,
    error_message VARCHAR2(4000),
    error_stack  CLOB,
    backtrace    CLOB,
    module_name  VARCHAR2(128)
);
~~~

Logger autonomous:

~~~sql
CREATE OR REPLACE PROCEDURE log_application_error (
    p_error_code    IN NUMBER,
    p_error_message IN VARCHAR2,
    p_error_stack   IN CLOB,
    p_backtrace     IN CLOB,
    p_module        IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO app_error_log (
        error_code,
        error_message,
        error_stack,
        backtrace,
        module_name
    )
    VALUES (
        p_error_code,
        p_error_message,
        p_error_stack,
        p_backtrace,
        p_module
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        -- Không để lỗi của logger che lỗi gốc.
        -- Hệ thống giám sát cần có cách phát hiện logger thất bại.
END;
/
~~~

Đây là ví dụ minh họa. Trong hệ thống thật, cần quyết định cách xử lý lỗi logging, giới hạn kích thước stack/backtrace, quyền ghi bảng log và cơ chế giám sát khi logger không ghi được.

### 13.3. Gọi logger rồi truyền lỗi gốc

~~~sql
CREATE OR REPLACE PROCEDURE process_order (
    p_order_id IN NUMBER
)
AS
    v_code      NUMBER;
    v_message   VARCHAR2(4000);
    v_stack     CLOB;
    v_backtrace CLOB;
BEGIN
    UPDATE orders
    SET status = 'PROCESSING'
    WHERE order_id = p_order_id;

    -- Các bước nghiệp vụ khác.

EXCEPTION
    WHEN OTHERS THEN
        v_code      := SQLCODE;
        v_message   := SQLERRM;
        v_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        log_application_error(
            p_error_code    => v_code,
            p_error_message => v_message,
            p_error_stack   => v_stack,
            p_backtrace     => v_backtrace,
            p_module        => 'PROCESS_ORDER'
        );

        RAISE;
END;
/
~~~

Logger tự COMMIT trong transaction autonomous. Sau khi logger kết thúc, RAISE truyền lại exception nghiệp vụ cho caller. Caller vẫn phải quyết định rollback transaction chính theo hợp đồng của ứng dụng.

### 13.4. Cảnh báo khi dùng autonomous logger trong trigger

Autonomous transaction có thể nhìn thấy trạng thái dữ liệu khác với transaction caller vì các thay đổi chưa commit của caller không hiển thị như dữ liệu đã commit cho autonomous transaction. Nếu logger truy vấn hoặc khóa dòng đang được transaction chính giữ, có thể phát sinh blocking hoặc deadlock.

Logger autonomous nên chỉ ghi thông tin chẩn đoán được truyền vào, tránh đọc hoặc cập nhật lại các dòng nghiệp vụ đang được transaction chính xử lý. Dùng nó có chủ đích để ghi dấu vết độc lập, không dùng như cách né quy tắc transaction.

## 14. Giữ nguyên lỗi gốc khi logger gặp lỗi

Một lỗi tinh vi xảy ra khi handler gọi logger, nhưng logger cũng phát sinh exception. Nếu exception của logger thoát ra, caller có thể chỉ nhìn thấy lỗi logging thay vì lỗi nghiệp vụ ban đầu.

Mẫu logger ở phần trước bắt lỗi nội bộ, rollback transaction autonomous và không phát lại lỗi logging. Điều này giữ đường truyền exception gốc ở handler gọi logger.

Một cách tổ chức khác là bọc lời gọi logger trong block con:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        v_code := SQLCODE;
        v_message := SQLERRM;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        BEGIN
            log_application_error(
                v_code,
                v_message,
                DBMS_UTILITY.FORMAT_ERROR_STACK,
                v_backtrace,
                'PROCESS_ORDER'
            );
        EXCEPTION
            WHEN OTHERS THEN
                -- Ghi nhận rằng logging thất bại bằng kênh giám sát phù hợp.
                NULL;
        END;

        RAISE;
~~~

Handler con chỉ ngăn lỗi phụ từ logger thay thế lỗi gốc; RAISE cuối vẫn nằm trong handler ngoài đang xử lý exception gốc. Không áp dụng WHEN OTHERS THEN NULL cho logic nghiệp vụ thông thường.

Nếu việc ghi log là bắt buộc để tuân thủ kiểm toán, không được âm thầm bỏ qua lỗi logger. Cần thiết kế cơ chế giám sát/đảm bảo log phù hợp và quyết định rõ liệu nghiệp vụ có được tiếp tục khi logging không khả dụng hay không.

## 15. Không nhầm lỗi với kết quả DML bằng 0 dòng

Một UPDATE không tìm thấy dòng không tự phát sinh exception:

~~~sql
UPDATE orders
SET status = 'SHIPPED'
WHERE order_id = -1;
~~~

Nếu không có order_id = -1, câu lệnh thành công nhưng SQL%ROWCOUNT bằng 0. Đây không phải exception.

Nếu nghiệp vụ yêu cầu đúng một dòng phải được cập nhật:

~~~sql
UPDATE orders
SET status = 'SHIPPED'
WHERE order_id = p_order_id;

IF SQL%ROWCOUNT = 0 THEN
    RAISE_APPLICATION_ERROR(
        -20030,
        'Order does not exist'
    );
END IF;
~~~

Nếu cần đúng một dòng và muốn phát hiện nhiều hơn một dòng, cần thiết kế constraint phù hợp hoặc kiểm tra số dòng theo yêu cầu. Đừng dựa vào WHEN OTHERS để phát hiện tình huống DML không tác động dòng nào.

## 16. Transaction thất bại và trạng thái nghiệp vụ

Một API hoặc batch job cần phân biệt ít nhất:

- Thành công và đã COMMIT.
- Thành công trong transaction nhưng chưa COMMIT.
- Thất bại và đã rollback phần việc liên quan.
- Thất bại nhưng một phần thay đổi trước đó còn trong transaction.
- Thất bại ở một bản ghi nhưng batch tiếp tục theo chính sách.

Không đặt trạng thái SUCCESS chỉ vì procedure đã kết thúc mà không có exception nếu code có thể nuốt exception.

### 16.1. Ví dụ hợp đồng transaction rõ ràng

Procedure chỉ thực hiện DML và truyền lỗi:

~~~sql
CREATE OR REPLACE PROCEDURE reserve_inventory (
    p_product_id IN NUMBER,
    p_quantity   IN NUMBER
)
AS
BEGIN
    IF p_quantity <= 0 THEN
        RAISE_APPLICATION_ERROR(-20040, 'Invalid quantity');
    END IF;

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id
      AND available_qty >= p_quantity;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20041,
            'Insufficient inventory or product not found'
        );
    END IF;
END;
/
~~~

Procedure không COMMIT. Caller kiểm soát transaction:

~~~sql
BEGIN
    reserve_inventory(100, 2);
    -- Thực hiện các bước nghiệp vụ liên quan khác.
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Trong mẫu này, caller sở hữu transaction và rollback toàn bộ nếu bất kỳ bước nào thất bại. Nếu caller muốn giữ các thay đổi trước procedure, hãy dùng SAVEPOINT và ROLLBACK TO thay vì rollback toàn transaction.

### 16.2. Không COMMIT trong procedure dùng chung nếu caller cần kiểm soát

Procedure tự COMMIT có thể làm caller mất khả năng rollback nhiều bước như một đơn vị nghiệp vụ. Trừ khi hợp đồng của procedure nói rõ nó sở hữu transaction, hãy để transaction control ở tầng điều phối.

## 17. Xử lý lỗi theo từng dòng trong batch

Một batch có thể cần tiếp tục xử lý bản ghi sau khi một bản ghi lỗi. Đây là yêu cầu nghiệp vụ khác với việc nuốt mọi lỗi.

Ví dụ khái niệm:

~~~sql
BEGIN
    FOR rec IN (
        SELECT order_id
        FROM staging_orders
        ORDER BY order_id
    ) LOOP
        SAVEPOINT before_one_order;

        BEGIN
            process_one_order(rec.order_id);
        EXCEPTION
            WHEN DUP_VAL_ON_INDEX THEN
                ROLLBACK TO before_one_order;
                -- Ghi nhận bản ghi trùng theo chính sách batch.
            WHEN OTHERS THEN
                ROLLBACK TO before_one_order;
                -- Nếu lỗi không được phép bỏ qua, truyền lên caller.
                RAISE;
        END;
    END LOOP;
END;
/
~~~

Ví dụ này chỉ bỏ qua lỗi trùng khóa theo chính sách đã định; lỗi khác vẫn được truyền lên. Nếu nghiệp vụ cho phép tiếp tục cả với lỗi khác, phải ghi trạng thái FAILED cho từng order và bảo đảm batch tổng thể không báo thành công toàn phần.

Với xử lý số lượng lớn, cân nhắc FORALL SAVE EXCEPTIONS hoặc DML error logging phù hợp. Dù dùng công cụ nào, cần phân biệt thành công từng dòng với trạng thái tổng thể của batch.

## 18. DML error logging và xử lý lỗi hàng loạt

Oracle hỗ trợ cơ chế DML error logging qua DBMS_ERRLOG và mệnh đề LOG ERRORS trong một số câu DML. Cơ chế này có thể cho phép DML tiếp tục xử lý các dòng không lỗi trong khi ghi các dòng lỗi vào bảng lỗi.

Ví dụ tạo bảng lỗi:

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'ORDERS',
        err_log_table_name => 'ERR$_ORDERS'
    );
END;
/
~~~

Sau đó, trong một trường hợp phù hợp:

~~~sql
INSERT INTO orders (order_id, amount)
SELECT order_id, amount
FROM staging_orders
LOG ERRORS INTO err$_orders ('IMPORT_2026')
REJECT LIMIT UNLIMITED;
~~~

Đây là kỹ thuật riêng cho DML theo tập hợp; không thay thế việc thiết kế exception handler cho mọi lỗi. Cần xem loại lỗi nào được ghi nhận, giới hạn reject, transaction và yêu cầu atomicity của nghiệp vụ.

Nếu yêu cầu toàn bộ batch phải thành công hoặc thất bại cùng nhau, cơ chế tiếp tục bỏ qua dòng lỗi có thể không phù hợp. Khi dùng LOG ERRORS, caller phải đọc bảng lỗi và xác định trạng thái batch trước khi báo thành công.

## 19. Trigger và lỗi nghiệp vụ

Trigger thường được dùng cho audit, kiểm tra hoặc duy trì logic phụ thuộc sự kiện DML. Khi trigger phát sinh exception:

- Câu lệnh kích hoạt trigger nhận lỗi.
- DML statement bị thất bại.
- Tác động của statement và trigger trong statement đó được hoàn tác.
- Caller có thể bắt exception hoặc để nó lan tiếp.

### 19.1. Trigger không nên che lỗi constraint nghiệp vụ

Ví dụ không tốt:

~~~sql
CREATE OR REPLACE TRIGGER trg_validate_order_bad
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20050, 'Invalid amount');
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
/
~~~

Trigger bắt lỗi và bỏ qua. INSERT có thể tiếp tục dù trigger đã phát hiện amount không hợp lệ. Đây là cách làm mất tác dụng kiểm tra dữ liệu.

Phiên bản đúng:

~~~sql
CREATE OR REPLACE TRIGGER trg_validate_order
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount IS NULL OR :NEW.amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20050, 'Invalid amount');
    END IF;
END;
/
~~~

Không cần WHEN OTHERS nếu không có xử lý bổ sung. Nếu thêm logger, ghi thông tin rồi RAISE để từ chối DML.

### 19.2. Trigger audit và transaction

Audit row được chèn bởi trigger thông thường thuộc cùng transaction với DML:

- DML COMMIT thì audit COMMIT.
- DML ROLLBACK thì audit ROLLBACK.
- Trigger phát sinh lỗi khiến DML statement thất bại thì audit row của statement đó cũng bị hoàn tác.

Đây thường là hành vi mong muốn khi audit ghi nhận thay đổi dữ liệu đã thành công.

Nếu cần lưu cả lần thử thất bại, hãy thiết kế log lỗi độc lập và hiểu rõ rằng bản ghi autonomous log không chứng minh thay đổi nghiệp vụ đã commit.

## 20. Những anti-pattern cần tránh

| Anti-pattern | Vấn đề | Cách xử lý |
|---|---|---|
| WHEN OTHERS THEN NULL | Nuốt mọi lỗi | RAISE hoặc xử lý rõ theo nghiệp vụ |
| WHEN OTHERS chỉ DBMS_OUTPUT | Log không bền vững và caller không biết lỗi | Logger phù hợp rồi RAISE |
| Bắt lỗi rồi trả về SUCCESS | Trạng thái ứng dụng sai | Trả lỗi hoặc trạng thái FAILED rõ ràng |
| RAISE_APPLICATION_ERROR cho mọi lỗi | Làm mất phân biệt lỗi gốc | Chỉ ánh xạ khi cần hợp đồng lỗi mới |
| ROLLBACK toàn transaction trong procedure dùng chung | Xóa thay đổi của caller | Để caller sở hữu transaction hoặc dùng SAVEPOINT |
| COMMIT trong trigger | Trigger không được điều khiển transaction caller | Bỏ COMMIT/ROLLBACK khỏi trigger thường |
| Logger autonomous truy vấn dòng caller đang khóa | Có thể blocking/deadlock | Chỉ ghi diagnostics đã truyền vào |
| Logger lỗi làm che lỗi gốc | Caller nhận lỗi phụ | Bảo vệ lời gọi logger, sau đó RAISE lỗi gốc |
| Chỉ ghi SQLERRM | Thiếu vị trí phát sinh | Ghi thêm error stack và backtrace |
| Nuốt lỗi từng dòng mà không đánh dấu batch | Batch báo thành công sai | Theo dõi trạng thái từng dòng và tổng thể |

## 21. Mẫu xử lý exception nên dùng

### 21.1. Không cần xử lý: để lỗi lan truyền

~~~sql
BEGIN
    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = p_order_id;
END;
/
~~~

Đây là cách đơn giản khi caller có thể xử lý exception.

### 21.2. Xử lý một lỗi dự kiến, giữ lỗi khác

~~~sql
BEGIN
    INSERT INTO orders (order_id, amount)
    VALUES (p_order_id, p_amount);
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        RAISE_APPLICATION_ERROR(
            -20060,
            'Order ID already exists'
        );
END;
/
~~~

Chỉ lỗi trùng khóa được ánh xạ sang thông báo nghiệp vụ. Các lỗi khác tự lan truyền.

### 21.3. Ghi log mọi lỗi rồi truyền tiếp

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        v_code := SQLCODE;
        v_message := SQLERRM;
        v_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        BEGIN
            log_application_error(
                v_code,
                v_message,
                v_stack,
                v_backtrace,
                'MODULE_NAME'
            );
        EXCEPTION
            WHEN OTHERS THEN
                -- Lỗi logging được xử lý riêng; không thay lỗi gốc.
                NULL;
        END;

        RAISE;
~~~

Đây là mẫu cho tầng có trách nhiệm ghi nhận lỗi tổng quát. Việc không truyền lỗi logging ra ngoài chỉ áp dụng cho lỗi phụ của logger; exception nghiệp vụ gốc vẫn được RAISE.

### 21.4. Hoàn tác phần việc của procedure rồi truyền lỗi

~~~sql
BEGIN
    SAVEPOINT before_procedure_work;

    -- Nhiều bước DML thuộc procedure.

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_procedure_work;
        RAISE;
END;
/
~~~

Dùng khi hợp đồng của procedure là hoàn tác phần thay đổi do chính procedure thực hiện nhưng giữ các thay đổi trước savepoint của caller.

## 22. Kiểm tra kết quả giao dịch ở tầng ứng dụng

Caller không nên chỉ kiểm tra procedure có ném exception hay không nếu procedure được thiết kế có thể trả trạng thái. Hãy quy định rõ:

- Procedure trả kết quả bình thường chỉ khi bước nào đã hoàn thành?
- Transaction đã COMMIT chưa?
- Caller còn phải COMMIT không?
- Lỗi nào được chuyển thành kết quả nghiệp vụ?
- Lỗi nào phải làm batch thất bại?
- Nếu logger không ghi được thì hành vi ra sao?

Ví dụ một API có thể trả status code, nhưng chỉ trả SUCCESS sau khi transaction đã hoàn tất theo hợp đồng. Nếu procedure không COMMIT, status nên diễn đạt là “đã thực hiện DML trong transaction” chứ không khẳng định dữ liệu đã bền vững.

## 23. Bài tập thực hành

### Bài 1 — WHEN OTHERS

Viết block chia 10 cho 0. Bắt WHEN OTHERS, in SQLCODE và SQLERRM rồi RAISE.

**Yêu cầu:** quan sát caller nhận lỗi như thế nào.

### Bài 2 — Nuốt lỗi

Viết hai phiên bản procedure: một phiên bản WHEN OTHERS THEN NULL, một phiên bản ghi log rồi RAISE.

**Câu hỏi:** caller phân biệt thành công và thất bại ra sao?

### Bài 3 — RAISE và RAISE_APPLICATION_ERROR

Tạo user-defined exception cho số tiền âm. Thử RAISE exception đã khai báo và RAISE_APPLICATION_ERROR với mã trong khoảng -20000 đến -20999.

### Bài 4 — Backtrace

Tạo ba procedure gọi lồng nhau. Phát sinh lỗi ở procedure sâu nhất; dùng FORMAT_ERROR_STACK, FORMAT_ERROR_BACKTRACE và FORMAT_CALL_STACK để quan sát khác biệt.

### Bài 5 — Statement rollback

Trong cùng transaction, INSERT một dòng hợp lệ rồi INSERT dòng trùng khóa. Bắt lỗi ở caller và kiểm tra dòng đầu còn tồn tại trước khi rollback hay không.

### Bài 6 — SAVEPOINT

Tạo hai bước DML, đặt SAVEPOINT giữa hai bước, gây lỗi ở bước hai và ROLLBACK TO. Xác định thay đổi nào còn trong transaction.

### Bài 7 — Trigger

Tạo BEFORE INSERT trigger từ chối amount âm bằng RAISE_APPLICATION_ERROR. Thử INSERT hợp lệ và không hợp lệ.

**Yêu cầu:** kiểm tra DML statement và dữ liệu trigger có bị hoàn tác khi trigger lỗi.

### Bài 8 — Logger autonomous

Tạo bảng APP_ERROR_LOG và procedure logger có PRAGMA AUTONOMOUS_TRANSACTION. Gọi logger từ exception handler rồi RAISE lỗi gốc.

**Câu hỏi:** bản ghi log còn tồn tại sau khi caller ROLLBACK transaction chính không?

### Bài 9 — Logger thất bại

Tạm thời làm logger phát sinh lỗi. Bọc lời gọi logger trong block con, sau đó RAISE exception gốc. Quan sát mã lỗi caller nhận được.

### Bài 10 — Batch theo từng dòng

Xử lý danh sách staging. Cho phép bỏ qua DUP_VAL_ON_INDEX nhưng phải dừng với lỗi khác. Ghi trạng thái FAILED/SKIPPED/SUCCEEDED cho từng bản ghi và trạng thái tổng thể batch.

## 24. Quy trình xử lý lỗi an toàn

Khi viết exception handler, hãy đi theo trình tự:

1. Xác định lỗi nào là tình huống nghiệp vụ dự kiến.
2. Bắt riêng các exception có thể xử lý rõ ràng.
3. Với lỗi không dự kiến, dùng WHEN OTHERS ở ranh giới phù hợp.
4. Chụp SQLCODE, SQLERRM, error stack và backtrace trước khi gọi logger.
5. Ghi log bằng cơ chế phù hợp với yêu cầu transaction.
6. Nếu logger thất bại, tránh để lỗi phụ che lỗi gốc; đồng thời có cơ chế giám sát logging.
7. Dùng RAISE để truyền exception gốc khi thao tác nghiệp vụ chưa hoàn thành.
8. Chỉ dùng RAISE_APPLICATION_ERROR khi cần trả mã lỗi nghiệp vụ mới.
9. Xác định rõ rollback statement, rollback savepoint hay rollback toàn transaction.
10. Để tầng sở hữu transaction quyết định COMMIT/ROLLBACK theo hợp đồng.
11. Với trigger, để lỗi kiểm tra dữ liệu lan ra câu lệnh DML; không nuốt lỗi.
12. Chỉ đánh dấu batch/API thành công khi mọi điều kiện thành công theo hợp đồng đã được đáp ứng.

Sơ đồ:

~~~text
Exception phát sinh
        |
        v
Có lỗi nghiệp vụ đã biết?
       /          \
     Có            Không
      |              |
      v              v
Bắt lỗi cụ thể   WHEN OTHERS tại ranh giới
      |              |
      v              v
Xử lý theo       Chụp SQLCODE/SQLERRM/
hợp đồng         stack/backtrace
      |              |
      |              v
      |          Ghi log an toàn
      |              |
      |              v
      |          Logger có lỗi?
      |              |
      |              v
      |          Bảo vệ lỗi gốc
      |              |
      +-------+------+
              |
              v
       Nghiệp vụ đã hoàn tất?
          /          \
        Có            Không
        |               |
        v               v
 Trả kết quả theo    RAISE hoặc ánh xạ
 transaction contract lỗi có chủ đích
                        |
                        v
              Caller quyết định rollback
~~~

## 25. Những điểm cần nhớ

- WHEN OTHERS bắt lỗi chưa được handler cụ thể xử lý; nó không có nghĩa lỗi đã được khắc phục.
- Nếu chỉ ghi log rồi kết thúc handler, exception bị nuốt và caller có thể hiểu nhầm nghiệp vụ thành công.
- RAISE không tham số trong exception handler truyền tiếp exception hiện tại.
- RAISE_APPLICATION_ERROR dùng để phát sinh mã lỗi ứng dụng trong khoảng -20000 đến -20999.
- SQLCODE và SQLERRM cung cấp mã và thông điệp; FORMAT_ERROR_STACK và FORMAT_ERROR_BACKTRACE giúp truy vết sâu hơn.
- Một DML statement thất bại thường chỉ rollback tác động của statement đó; các thay đổi trước đó trong transaction có thể còn.
- Exception thoát khỏi procedure không tự động có nghĩa toàn bộ transaction đã rollback.
- Trigger phát sinh exception làm câu lệnh kích hoạt trigger thất bại; không nuốt lỗi kiểm tra dữ liệu.
- Logger cùng transaction sẽ rollback cùng nghiệp vụ; autonomous logger có thể tồn tại độc lập nhưng cần thiết kế thận trọng.
- Tầng sở hữu transaction phải quyết định COMMIT/ROLLBACK và trạng thái thành công cuối cùng.

WHEN OTHERS có ích khi được dùng như điểm xử lý cuối cùng để ghi nhận và truyền tiếp lỗi. Handler tốt giúp caller biết thao tác đã thất bại, có đủ thông tin để điều tra và có thể quyết định transaction một cách nhất quán. Đừng để một thông báo log thay thế exception, đừng coi procedure kết thúc bình thường là bằng chứng dữ liệu đã commit, và đừng để trigger bỏ qua lỗi kiểm tra dữ liệu. Khi lỗi được truyền đúng, rollback được đặt ở đúng ranh giới và trạng thái nghiệp vụ phản ánh kết quả thực tế, hệ thống sẽ tránh được những giao dịch thất bại bị báo nhầm là thành công.
