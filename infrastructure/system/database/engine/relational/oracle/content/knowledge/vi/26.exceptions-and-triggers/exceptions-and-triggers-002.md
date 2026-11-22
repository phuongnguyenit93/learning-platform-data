# RAISE, RAISE_APPLICATION_ERROR và bảo toàn thông tin nguyên nhân trong Oracle

## 1. Vì sao cần phát sinh và bảo toàn exception?

Trong PL/SQL, exception cho biết một thao tác không thể tiếp tục theo luồng bình thường. Lỗi có thể xuất phát từ Oracle Database, ví dụ vi phạm unique constraint, không tìm thấy hàng hoặc lỗi chuyển đổi; cũng có thể xuất phát từ quy tắc nghiệp vụ do ứng dụng định nghĩa, ví dụ số lượng đặt hàng vượt tồn kho hoặc tài khoản đã đóng.

Khi xử lý lỗi, chương trình cần trả lời ba câu hỏi:

1. **Lỗi gì đã xảy ra?** Mã lỗi và thông điệp nào mô tả vấn đề?
2. **Lỗi bắt đầu ở đâu?** Dòng PL/SQL hoặc lời gọi nào phát sinh lỗi gốc?
3. **Lỗi đi qua những lớp nào?** Procedure, package, trigger hoặc ứng dụng nào đã bắt, bổ sung ngữ cảnh hay truyền lỗi tiếp?

PL/SQL có hai cách phát sinh lỗi thường gặp:

- `RAISE`: phát sinh một exception đã khai báo hoặc phát sinh lại exception hiện tại trong handler.
- `RAISE_APPLICATION_ERROR`: phát ra mã lỗi và thông điệp do ứng dụng định nghĩa, thường dùng để báo lỗi nghiệp vụ cho caller.

Ví dụ:

```sql
CREATE OR REPLACE PROCEDURE validate_order_amount (
    p_amount IN NUMBER
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order amount cannot be negative'
        );
    END IF;
END validate_order_amount;
/
```

Khi caller truyền số tiền âm, procedure phát sinh lỗi ứng dụng `ORA-20001`. Caller có thể bắt lỗi này, hiển thị thông báo phù hợp hoặc ghi log.

Tuy nhiên, khi một exception đã xảy ra và chương trình chỉ muốn bổ sung ngữ cảnh, cách phát lại rất quan trọng. Dùng `RAISE;` trong handler sẽ phát lại exception hiện tại và giữ nguyên thông tin lỗi gốc. Dùng `RAISE_APPLICATION_ERROR(..., TRUE)` có thể thêm lỗi ứng dụng vào error stack hiện có. Nếu thay lỗi gốc bằng một thông báo chung mà không giữ stack hoặc backtrace, thông tin chẩn đoán có thể bị mất.

Bài học thuộc chương **Lỗi và trigger**, tập trung vào `RAISE`, `RAISE_APPLICATION_ERROR`, exception propagation, error stack, backtrace, cách ghi log, cách thêm ngữ cảnh mà vẫn giữ nguyên nguyên nhân và cách xử lý lỗi phát sinh từ trigger.

## 2. Exception trong PL/SQL

Exception là một điều kiện bất thường làm luồng thực thi bình thường bị gián đoạn. Khi exception phát sinh, PL/SQL tìm handler phù hợp trong block hiện tại. Nếu không có handler, exception truyền lên block bao ngoài hoặc caller.

Một block có cấu trúc:

```sql
DECLARE
    -- Variables and exception declarations
BEGIN
    -- Executable statements
EXCEPTION
    WHEN some_exception THEN
        -- Handle the exception
    WHEN OTHERS THEN
        -- Handle remaining exceptions
END;
/
```

Các nhóm exception:

- **Predefined exception:** Oracle đã định nghĩa tên, ví dụ `NO_DATA_FOUND`, `TOO_MANY_ROWS`, `DUP_VAL_ON_INDEX`, `ZERO_DIVIDE`.
- **User-defined exception:** lập trình viên khai báo bằng `EXCEPTION` trong PL/SQL.
- **Non-predefined Oracle error:** lỗi Oracle có mã nhưng không có predefined name tương ứng trong chương trình; có thể ánh xạ bằng `PRAGMA EXCEPTION_INIT`.

### 2.1. Exception được phát sinh như thế nào?

Exception có thể phát sinh tự động:

```sql
DECLARE
    v_result NUMBER;
BEGIN
    v_result := 10 / 0;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Cannot divide by zero');
END;
/
```

Hoặc do chương trình chủ động phát sinh:

```sql
DECLARE
    e_invalid_quantity EXCEPTION;
    v_quantity NUMBER := -1;
BEGIN
    IF v_quantity < 0 THEN
        RAISE e_invalid_quantity;
    END IF;
EXCEPTION
    WHEN e_invalid_quantity THEN
        DBMS_OUTPUT.PUT_LINE('Quantity must be non-negative');
END;
/
```

`RAISE` không tạo ra một mã ORA tùy ý. Nó phát sinh exception đã khai báo. Nếu cần một mã lỗi ứng dụng có thể nhận diện qua SQL/JDBC, dùng `RAISE_APPLICATION_ERROR`.

## 3. RAISE: phát sinh exception đã khai báo

### 3.1. Cú pháp

```sql
RAISE exception_name;
```

`exception_name` phải là exception đã được khai báo trong scope hiện tại hoặc được tham chiếu hợp lệ từ scope bên ngoài.

Ví dụ:

```sql
DECLARE
    e_insufficient_stock EXCEPTION;
    v_available NUMBER := 2;
    v_requested NUMBER := 5;
BEGIN
    IF v_requested > v_available THEN
        RAISE e_insufficient_stock;
    END IF;
EXCEPTION
    WHEN e_insufficient_stock THEN
        DBMS_OUTPUT.PUT_LINE('Not enough stock');
END;
/
```

### 3.2. Exception tự định nghĩa không có mã ORA nghiệp vụ riêng

Exception tự định nghĩa giúp đặt tên cho điều kiện nghiệp vụ bên trong PL/SQL:

```sql
DECLARE
    e_account_closed EXCEPTION;
    v_status VARCHAR2(20) := 'CLOSED';
BEGIN
    IF v_status = 'CLOSED' THEN
        RAISE e_account_closed;
    END IF;
EXCEPTION
    WHEN e_account_closed THEN
        DBMS_OUTPUT.PUT_LINE('Account is closed');
END;
/
```

Nếu exception không được xử lý trong PL/SQL, caller có thể nhận lỗi chung cho user-defined exception chưa được xử lý, thường là `ORA-06510`. Nếu cần một mã ứng dụng ổn định, hãy dùng `RAISE_APPLICATION_ERROR` hoặc ánh xạ exception với mã lỗi theo thiết kế.

### 3.3. RAISE trong handler để phát lại lỗi hiện tại

Đây là cách quan trọng nhất để bảo toàn lỗi gốc:

```sql
BEGIN
    -- Một thao tác có thể phát sinh exception.
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error=' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
```

Trong một exception handler, `RAISE;` không có tên exception nghĩa là phát lại exception đang được handler xử lý. Nó giữ nguyên exception hiện tại, thay vì tạo một exception mới theo tên.

Hãy dùng dạng không có tên khi mục tiêu là:

- Ghi log rồi để caller xử lý tiếp.
- Thực hiện cleanup rồi chuyển lỗi lên tầng trên.
- Bổ sung quan sát nhưng không đổi ý nghĩa lỗi.
- Bảo đảm transaction hoặc API bên ngoài biết thao tác đã thất bại.

### 3.4. Phân biệt RAISE; và RAISE exception_name;

Hai câu lệnh có mục đích khác nhau:

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
```

Phát lại exception hiện tại trong handler. Đây là lựa chọn phù hợp khi muốn giữ nguyên lỗi đang xử lý.

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE e_another_error;
```

Phát sinh exception có tên `e_another_error`. Đây là một exception được nêu đích danh, có thể thay đổi ý nghĩa lỗi và vị trí backtrace. Không dùng cách thứ hai như một bản sao tương đương của `RAISE;`.

Nếu cần chuyển đổi loại lỗi, hãy làm có chủ đích và giữ lại nguyên nhân bằng error stack hoặc cơ chế log.

### 3.5. RAISE exception ở bất kỳ nhánh logic phù hợp

```sql
CREATE OR REPLACE PROCEDURE validate_transfer (
    p_amount IN NUMBER,
    p_balance IN NUMBER
) AS
    e_invalid_amount EXCEPTION;
    e_insufficient_balance EXCEPTION;
BEGIN
    IF p_amount <= 0 THEN
        RAISE e_invalid_amount;
    END IF;

    IF p_amount > p_balance THEN
        RAISE e_insufficient_balance;
    END IF;
END validate_transfer;
/
```

Exception handler có thể đặt trong procedure hoặc ở caller. Nếu procedure không bắt exception, nó truyền ra caller.

## 4. RAISE_APPLICATION_ERROR: phát lỗi ứng dụng có mã riêng

### 4.1. Cú pháp

```sql
RAISE_APPLICATION_ERROR(
    error_code,
    message
    [, keep_errors]
);
```

Trong đó:

- `error_code`: số nguyên âm trong khoảng `-20000` đến `-20999`.
- `message`: thông điệp lỗi ứng dụng, tối đa 2048 byte.
- `keep_errors`: tùy chọn Boolean. `TRUE` thêm lỗi ứng dụng vào error stack hiện tại; `FALSE` thay thế error stack hiện tại. Mặc định là `FALSE`.

Ví dụ:

```sql
BEGIN
    RAISE_APPLICATION_ERROR(
        -20001,
        'Customer is not eligible for this operation'
    );
END;
/
```

Caller nhận lỗi Oracle có mã `ORA-20001` cùng thông điệp.

### 4.2. Dải mã lỗi ứng dụng

| Dải | Ý nghĩa |
|---|---|
| `-20000` đến `-20999` | Dải mã được dành cho lỗi do ứng dụng định nghĩa bằng `RAISE_APPLICATION_ERROR` |
| Mã ORA khác | Lỗi Oracle hoặc lỗi từ thành phần khác, không tự chọn làm mã ứng dụng tùy ý |

Không dùng mã ngoài dải được cho phép khi gọi `RAISE_APPLICATION_ERROR`; Oracle sẽ báo lỗi tham số không hợp lệ.

### 4.3. Ví dụ kiểm tra nghiệp vụ

```sql
CREATE OR REPLACE PROCEDURE create_payment (
    p_amount IN NUMBER
) AS
BEGIN
    IF p_amount IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Payment amount is required'
        );
    END IF;

    IF p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20011,
            'Payment amount must be greater than zero'
        );
    END IF;

    -- Thực hiện các bước tạo thanh toán ở đây.
END create_payment;
/
```

Hai điều kiện nghiệp vụ có hai mã khác nhau, vì vậy caller có thể phân biệt trường hợp thiếu dữ liệu với trường hợp giá trị không hợp lệ.

### 4.4. Chọn mã lỗi ổn định

Mã lỗi ứng dụng nên có quy ước tập trung, ví dụ:

| Mã ví dụ | Ý nghĩa |
|---:|---|
| `-20010` | Thiếu dữ liệu bắt buộc |
| `-20011` | Giá trị đầu vào không hợp lệ |
| `-20020` | Không tìm thấy đối tượng nghiệp vụ |
| `-20021` | Trạng thái hiện tại không cho phép thao tác |
| `-20030` | Vi phạm giới hạn nghiệp vụ |

Đây chỉ là quy ước minh họa. Trong hệ thống thực tế, nên quản lý mã trong tài liệu API hoặc package constants để tránh hai module dùng cùng mã cho hai ý nghĩa khác nhau.

### 4.5. Không đưa dữ liệu nhạy cảm vào message

Thông điệp có thể xuất hiện trong SQL client, log database, ứng dụng hoặc API response. Không đưa mật khẩu, token, dữ liệu thẻ, thông tin định danh nhạy cảm hoặc toàn bộ payload vào error message. Dùng mã lỗi và một thông điệp ngắn, đủ để người gọi hiểu cách xử lý.

## 5. Tham số keep_errors: thay thế hay thêm vào error stack

Tham số thứ ba quyết định `RAISE_APPLICATION_ERROR` xử lý error stack hiện có như thế nào.

### 5.1. Mặc định FALSE: thay error stack hiện tại

```sql
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Customer record is missing'
        );
```

Vì tham số thứ ba mặc định là `FALSE`, lỗi ứng dụng mới thay thế stack lỗi đang có. Caller chủ yếu thấy lỗi `ORA-20020`. Điều này có thể phù hợp khi chủ đích là ánh xạ lỗi kỹ thuật sang một lỗi API đã được định nghĩa và hệ thống không cần hiển thị lỗi gốc ở error stack.

Nhưng nếu mục tiêu là bảo toàn nguyên nhân kỹ thuật, không nên dùng mặc định này một cách vô ý.

### 5.2. TRUE: thêm lỗi ứng dụng vào error stack

```sql
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Customer record is missing',
            TRUE
        );
```

`TRUE` yêu cầu Oracle giữ các lỗi đã có trong stack và thêm lỗi ứng dụng. Nhờ vậy caller có thể thấy thông tin nghiệp vụ ở lớp ngoài mà vẫn còn lỗi gốc trong error stack.

Đây là cách hữu ích khi:

- Một tầng PL/SQL muốn thêm mã nghiệp vụ nhưng vẫn giữ ORA gốc.
- Một trigger muốn thêm ngữ cảnh cho lỗi xảy ra khi DML.
- Một API muốn diễn đạt lỗi theo ngôn ngữ nghiệp vụ nhưng vẫn giữ chi tiết kỹ thuật cho đội vận hành.

### 5.3. Minh họa hai cách

Giả sử một truy vấn không tìm thấy hàng:

```sql
CREATE OR REPLACE PROCEDURE find_customer (
    p_customer_id IN NUMBER
) AS
    v_name VARCHAR2(100);
BEGIN
    SELECT customer_name
    INTO v_name
    FROM customers
    WHERE customer_id = p_customer_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Customer ' || p_customer_id || ' was not found',
            TRUE
        );
END find_customer;
/
```

Với `TRUE`, lỗi ứng dụng được thêm vào stack đang có thay vì xóa hoàn toàn thông tin lỗi gốc. Caller vẫn cần đọc toàn bộ error stack/backtrace thay vì chỉ lấy một dòng message.

### 5.4. TRUE không tự tạo một bản ghi log đầy đủ

`keep_errors => TRUE` chỉ điều khiển error stack của exception. Nó không:

- Ghi lỗi vào bảng log.
- Lưu payload hoặc bind values.
- Lưu request ID của ứng dụng.
- Lưu toàn bộ lịch sử các lời gọi đã thành công.
- Bảo đảm log tồn tại sau khi session kết thúc.

Muốn có dữ liệu điều tra bền vững, cần một cơ chế logging riêng.

## 6. Bảo toàn nguyên nhân khi bắt rồi ném lại lỗi

### 6.1. Pattern đúng: log rồi RAISE

```sql
CREATE OR REPLACE PROCEDURE process_invoice (
    p_invoice_id IN NUMBER
) AS
BEGIN
    -- Các bước xử lý hóa đơn.
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Invoice=' || p_invoice_id ||
            ', error=' || SQLCODE ||
            ', message=' || SQLERRM
        );
        RAISE;
END process_invoice;
/
```

`RAISE;` giữ exception hiện tại và truyền nó ra caller. Caller vẫn có thể phân loại lỗi theo mã Oracle gốc.

### 6.2. Pattern nguy hiểm: thay lỗi bằng lỗi chung

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20099,
            'Processing failed'
        );
```

Nếu không có `keep_errors => TRUE`, lỗi gốc bị thay thế trong error stack. Caller chỉ thấy thông báo chung và khó xác định lỗi ban đầu là `NO_DATA_FOUND`, `DUP_VAL_ON_INDEX`, lỗi chuyển đổi hay một lỗi khác.

Nếu API thực sự cần chuyển mọi lỗi thành một mã tổng quát, hãy ghi lại stack/backtrace gốc trước khi chuyển đổi, và cân nhắc giữ stack:

```sql
EXCEPTION
    WHEN OTHERS THEN
        -- Ghi log SQLCODE, SQLERRM, error stack và backtrace ở đây.
        RAISE_APPLICATION_ERROR(
            -20099,
            'Processing failed; contact support with the request ID',
            TRUE
        );
```

### 6.3. Không dùng RAISE tên exception để thay cho RAISE trống

Ví dụ:

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
```

phát lại lỗi hiện tại.

Trong khi:

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE e_processing_failed;
```

phát sinh exception được nêu tên. Đây là một thay đổi về loại lỗi. Nếu muốn chuyển loại lỗi, cần giữ nguyên nguyên nhân bằng logging hoặc `RAISE_APPLICATION_ERROR(..., TRUE)` theo hợp đồng API.

### 6.4. Cleanup nhưng vẫn giữ lỗi gốc

Nếu cần đóng cursor hoặc giải phóng tài nguyên:

```sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM orders
        WHERE status = 'NEW';
BEGIN
    OPEN c_orders;

    -- Thao tác có thể lỗi.
    FETCH c_orders INTO v_order_id;

    CLOSE c_orders;
EXCEPTION
    WHEN OTHERS THEN
        IF c_orders%ISOPEN THEN
            CLOSE c_orders;
        END IF;
        RAISE;
END;
/
```

Cleanup nằm trong handler, sau đó `RAISE;` truyền tiếp exception ban đầu. Nếu chính cleanup có thể phát sinh lỗi, cần bảo vệ cleanup bằng block con để lỗi phụ không che lỗi gốc.

## 7. SQLCODE và SQLERRM

Trong exception handler, hai hàm này cung cấp thông tin cơ bản:

- `SQLCODE`: mã số của exception hiện tại.
- `SQLERRM`: thông điệp của exception hiện tại.

Ví dụ:

```sql
BEGIN
    RAISE_APPLICATION_ERROR(-20010, 'Invalid payment amount');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        RAISE;
END;
/
```

`SQLCODE` của lỗi ứng dụng thường là `-20010`. `SQLERRM` trả thông điệp tương ứng.

### 7.1. Giới hạn của SQLERRM

`SQLERRM` hữu ích để đọc thông điệp lỗi hiện tại, nhưng không phải API lưu toàn bộ chuỗi nguyên nhân. Khi một lỗi được bọc qua nhiều tầng, `SQLERRM` thường chỉ thể hiện lỗi hiện tại/đầu stack theo ngữ cảnh; không nên dùng nó thay cho error stack và backtrace.

Không parse message để quyết định logic vì:

- Thông điệp có thể phụ thuộc ngôn ngữ.
- Nội dung có thể thay đổi theo phiên bản.
- Message có thể chứa giá trị dữ liệu.
- Một error stack có thể chứa nhiều lỗi.

Hãy phân nhánh theo exception name hoặc SQLCODE đã được định nghĩa.

### 7.2. SQLCODE ngoài exception handler

`SQLCODE` và `SQLERRM` có ý nghĩa chẩn đoán rõ nhất trong exception handler. Đừng đọc chúng ở phần chạy bình thường rồi coi kết quả là lỗi của câu SQL trước đó. Nếu cần biết DML có tác động hàng hay không, dùng `SQL%ROWCOUNT`, không dùng SQLCODE.

## 8. FORMAT_ERROR_STACK, FORMAT_ERROR_BACKTRACE và FORMAT_CALL_STACK

Oracle cung cấp các hàm trong `DBMS_UTILITY` để lấy thông tin chi tiết hơn.

### 8.1. FORMAT_ERROR_STACK

```sql
DBMS_UTILITY.FORMAT_ERROR_STACK
```

Trả về error stack hiện tại dưới dạng chuỗi. Đây là thông tin hữu ích khi một exception đã đi qua nhiều lớp và stack chứa nhiều mã lỗi.

### 8.2. FORMAT_ERROR_BACKTRACE

```sql
DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
```

Trả về vị trí trong PL/SQL call stack nơi exception được phát sinh. Hãy gọi trong exception handler để giữ thông tin backtrace của lỗi đang xử lý, đặc biệt trước khi phát sinh một exception mới.

Backtrace giúp trả lời câu hỏi: lỗi bắt đầu ở dòng nào? Đây là thông tin rất quan trọng khi exception được bắt ở một procedure phía trên.

### 8.3. FORMAT_CALL_STACK

```sql
DBMS_UTILITY.FORMAT_CALL_STACK
```

Trả về call stack hiện tại, cho biết các chương trình đang nằm trên đường gọi tại thời điểm lấy thông tin. Call stack khác error backtrace:

- Error backtrace tập trung vào nơi exception được phát sinh.
- Call stack tập trung vào chuỗi lời gọi tại thời điểm hàm được gọi.

### 8.4. Ví dụ ghi thông tin chẩn đoán

```sql
DECLARE
    v_code NUMBER;
    v_message VARCHAR2(4000);
    v_stack VARCHAR2(4000);
    v_backtrace VARCHAR2(4000);
    v_call_stack VARCHAR2(4000);
BEGIN
    RAISE_APPLICATION_ERROR(-20030, 'Order validation failed');
EXCEPTION
    WHEN OTHERS THEN
        v_code := SQLCODE;
        v_message := SQLERRM;
        v_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        v_call_stack := DBMS_UTILITY.FORMAT_CALL_STACK;

        DBMS_OUTPUT.PUT_LINE('Code=' || v_code);
        DBMS_OUTPUT.PUT_LINE('Message=' || v_message);
        DBMS_OUTPUT.PUT_LINE('Error stack=' || v_stack);
        DBMS_OUTPUT.PUT_LINE('Backtrace=' || v_backtrace);
        DBMS_OUTPUT.PUT_LINE('Call stack=' || v_call_stack);
        RAISE;
END;
/
```

Trong hệ thống thực tế, nên lưu các trường này vào log có cấu trúc thay vì chỉ in ra DBMS_OUTPUT.

## 9. Bảo toàn backtrace khi truyền exception qua nhiều tầng

Giả sử chuỗi gọi:

```text
Application
    |
    v
ORDER_API.PROCESS_ORDER
    |
    v
INVENTORY_API.RESERVE_STOCK
    |
    v
INVENTORY_API.CHECK_AVAILABLE
```

Lỗi thực sự xảy ra trong `CHECK_AVAILABLE`, nhưng được bắt ở `PROCESS_ORDER`. Nếu tầng giữa chỉ ghi thông điệp chung và phát sinh exception mới, vị trí ban đầu có thể khó truy tìm.

### 9.1. Không bắt lỗi nếu không cần xử lý

Nếu một tầng không cần bổ sung hành động nào, để exception tự truyền lên. Không cần viết `WHEN OTHERS THEN RAISE;` ở mọi procedure vì điều đó chỉ thêm code mà không bổ sung giá trị.

### 9.2. Bắt để cleanup hoặc ghi log rồi RAISE

```sql
CREATE OR REPLACE PROCEDURE process_order (
    p_order_id IN NUMBER
) AS
BEGIN
    inventory_api.reserve_stock(p_order_id);
    payment_api.authorize_payment(p_order_id);
EXCEPTION
    WHEN OTHERS THEN
        -- Capture diagnostic information before doing other work.
        DBMS_OUTPUT.PUT_LINE(
            'Order=' || p_order_id ||
            ', stack=' || DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END process_order;
/
```

Tầng điều phối thêm order ID vào thông tin log nhưng giữ exception gốc bằng `RAISE;`.

### 9.3. Thêm ngữ cảnh nghiệp vụ nhưng giữ error stack

```sql
CREATE OR REPLACE PROCEDURE process_order (
    p_order_id IN NUMBER
) AS
BEGIN
    inventory_api.reserve_stock(p_order_id);
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20040,
            'Unable to process order ' || p_order_id,
            TRUE
        );
END process_order;
/
```

`TRUE` thêm thông điệp nghiệp vụ vào stack đang có. Lỗi gốc vẫn có thể được nhìn thấy trong stack. Nếu cần backtrace đầy đủ để điều tra, hãy lưu `FORMAT_ERROR_BACKTRACE` trước khi gọi `RAISE_APPLICATION_ERROR`.

### 9.4. Lưu nguyên nhân trước khi chuyển đổi lỗi

```sql
EXCEPTION
    WHEN OTHERS THEN
        v_original_code := SQLCODE;
        v_original_message := SQLERRM;
        v_original_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_original_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        -- Persist diagnostic data or attach a request identifier.
        RAISE_APPLICATION_ERROR(
            -20099,
            'Order processing failed; reference=' || v_request_id,
            TRUE
        );
```

Biến `v_original_*` có thể được dùng để ghi log. Không cần hiển thị toàn bộ stack kỹ thuật cho end user; caller có thể nhận mã ứng dụng và request ID, còn đội vận hành tra cứu stack trong log.

## 10. Exception mapping với PRAGMA EXCEPTION_INIT

Một số lỗi Oracle không có predefined exception name thuận tiện. `PRAGMA EXCEPTION_INIT` ánh xạ một mã lỗi Oracle vào exception do chương trình khai báo.

### 10.1. Cú pháp

```sql
DECLARE
    e_resource_busy EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_resource_busy, -54);
BEGIN
    -- Operation that may raise ORA-00054.
    NULL;
EXCEPTION
    WHEN e_resource_busy THEN
        DBMS_OUTPUT.PUT_LINE('Resource is busy');
END;
/
```

Mã được truyền vào pragma là số âm tương ứng mã ORA, ví dụ ORA-00054 dùng `-54`.

### 10.2. Phân biệt mapping và phát sinh

`PRAGMA EXCEPTION_INIT` chỉ ánh xạ exception name với mã lỗi; nó không tự phát sinh lỗi. Muốn phát sinh exception đã khai báo, dùng `RAISE e_resource_busy;`.

### 10.3. Khi nào dùng mapping?

- Cần bắt lỗi Oracle cụ thể không có tên predefined phù hợp.
- Muốn code dễ đọc hơn so với `WHEN OTHERS` rồi so sánh SQLCODE.
- Muốn gom xử lý lỗi theo loại lỗi có ý nghĩa.

Không tạo mapping trùng lặp hoặc dùng mã không đúng với lỗi dự kiến. Tên exception nên mô tả nguyên nhân kỹ thuật hoặc nghiệp vụ rõ ràng.

## 11. Error stack và backtrace khác nhau như thế nào?

| Thông tin | Trả lời câu hỏi | Cách lấy |
|---|---|---|
| SQLCODE | Mã lỗi hiện tại là gì? | `SQLCODE` |
| SQLERRM | Thông điệp hiện tại là gì? | `SQLERRM` |
| Error stack | Những lỗi nào đang có trong stack? | `DBMS_UTILITY.FORMAT_ERROR_STACK` |
| Error backtrace | Exception phát sinh ở đâu? | `DBMS_UTILITY.FORMAT_ERROR_BACKTRACE` |
| Call stack | Chương trình nào đang gọi chương trình nào tại thời điểm này? | `DBMS_UTILITY.FORMAT_CALL_STACK` |

Không dùng một trường để thay thế tất cả trường còn lại. Một log tốt nên giữ mã, message, stack, backtrace, call stack và context nghiệp vụ có chọn lọc.

### 11.1. Ví dụ nhiều lớp

```sql
CREATE OR REPLACE PROCEDURE inner_step AS
BEGIN
    RAISE_APPLICATION_ERROR(-20051, 'Inner operation failed');
END inner_step;
/

CREATE OR REPLACE PROCEDURE middle_step AS
BEGIN
    inner_step;
END middle_step;
/

CREATE OR REPLACE PROCEDURE outer_step AS
BEGIN
    middle_step;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Stack: ' || DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            'Backtrace: ' || DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END outer_step;
/
```

Gọi:

```sql
BEGIN
    outer_step;
END;
/
```

Exception được phát sinh trong `INNER_STEP`, truyền qua `MIDDLE_STEP`, rồi được bắt ở `OUTER_STEP`. `RAISE;` phát lại exception đang xử lý. Backtrace giúp tìm vị trí phát sinh thay vì chỉ biết handler cuối cùng.

## 12. Ghi log lỗi mà không làm mất lỗi gốc

Trong hệ thống production, DBMS_OUTPUT không phải cơ chế logging bền vững. Có thể ghi thông tin vào một bảng log riêng, đồng thời giữ exception gốc.

### 12.1. Tạo bảng log

```sql
CREATE TABLE app_error_log (
    log_id RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    error_code NUMBER,
    error_message VARCHAR2(4000),
    error_stack CLOB,
    error_backtrace CLOB,
    call_stack CLOB,
    module_name VARCHAR2(64),
    action_name VARCHAR2(64)
);
```

Các trường:

- `LOG_ID`: định danh log.
- `CREATED_AT`: thời điểm ghi nhận.
- `ERROR_CODE`, `ERROR_MESSAGE`: thông tin ngắn.
- `ERROR_STACK`: chuỗi lỗi đầy đủ.
- `ERROR_BACKTRACE`: vị trí phát sinh.
- `CALL_STACK`: chuỗi lời gọi.
- `MODULE_NAME`, `ACTION_NAME`: thông tin module/action nếu ứng dụng đã thiết lập bằng `DBMS_APPLICATION_INFO`.

Không nên lưu toàn bộ dữ liệu đầu vào, mật khẩu, access token hoặc dữ liệu cá nhân không cần thiết vào log.

### 12.2. Procedure ghi log bằng autonomous transaction

```sql
CREATE OR REPLACE PROCEDURE write_app_error_log (
    p_error_code      IN NUMBER,
    p_error_message   IN VARCHAR2,
    p_error_stack     IN CLOB,
    p_error_backtrace IN CLOB,
    p_call_stack      IN CLOB
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO app_error_log (
        error_code,
        error_message,
        error_stack,
        error_backtrace,
        call_stack,
        module_name,
        action_name
    )
    VALUES (
        p_error_code,
        p_error_message,
        p_error_stack,
        p_error_backtrace,
        p_call_stack,
        SYS_CONTEXT('USERENV', 'MODULE'),
        SYS_CONTEXT('USERENV', 'ACTION')
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END write_app_error_log;
/
```

`PRAGMA AUTONOMOUS_TRANSACTION` khiến thao tác ghi log có transaction độc lập với transaction nghiệp vụ của caller. COMMIT trong logger xác nhận log ngay cả khi transaction nghiệp vụ sau đó ROLLBACK.

### 12.3. Gọi logger trong exception handler

```sql
CREATE OR REPLACE PROCEDURE process_demo_order (
    p_order_id IN NUMBER
) AS
    v_error_code NUMBER;
    v_error_message VARCHAR2(4000);
    v_error_stack VARCHAR2(4000);
    v_error_backtrace VARCHAR2(4000);
    v_call_stack VARCHAR2(4000);
BEGIN
    -- Thay bằng logic nghiệp vụ thực tế.
    RAISE_APPLICATION_ERROR(-20061, 'Demo processing failure');
EXCEPTION
    WHEN OTHERS THEN
        v_error_code := SQLCODE;
        v_error_message := SQLERRM;
        v_error_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_error_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        v_call_stack := DBMS_UTILITY.FORMAT_CALL_STACK;

        write_app_error_log(
            p_error_code      => v_error_code,
            p_error_message   => v_error_message,
            p_error_stack     => v_error_stack,
            p_error_backtrace => v_error_backtrace,
            p_call_stack      => v_call_stack
        );

        RAISE;
END process_demo_order;
/
```

Thông tin được chụp trước khi gọi logger. Sau khi ghi log, `RAISE;` truyền lại exception gốc cho caller.

### 12.4. Logger lỗi không được che lỗi nghiệp vụ gốc

Nếu logger có thể lỗi, lỗi từ logger có nguy cơ thay thế lỗi ban đầu. Khi chính sách logging là best effort, có thể bảo vệ lời gọi logger bằng block con:

```sql
EXCEPTION
    WHEN OTHERS THEN
        v_error_code := SQLCODE;
        v_error_message := SQLERRM;
        v_error_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_error_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        v_call_stack := DBMS_UTILITY.FORMAT_CALL_STACK;

        BEGIN
            write_app_error_log(
                v_error_code,
                v_error_message,
                v_error_stack,
                v_error_backtrace,
                v_call_stack
            );
        EXCEPTION
            WHEN OTHERS THEN
                -- Best-effort logging: do not replace the original exception.
                NULL;
        END;

        RAISE;
```

Ở đây chỉ lỗi phụ của thao tác ghi log bị bỏ qua; lỗi nghiệp vụ/kỹ thuật ban đầu vẫn được phát lại bằng `RAISE;`. Nếu hệ thống yêu cầu logging bắt buộc, không nên âm thầm bỏ qua lỗi logger; cần thiết kế kênh cảnh báo hoặc chính sách fail-closed phù hợp.

### 12.5. Lưu ý về autonomous transaction

Autonomous logger có các đặc điểm cần hiểu:

- Log có thể COMMIT dù transaction nghiệp vụ ROLLBACK.
- Logger không nhìn thấy các thay đổi chưa commit của transaction cha.
- Không nên tạo foreign key từ bảng log đến hàng nghiệp vụ chưa commit; autonomous transaction không thể dựa vào dữ liệu chưa commit của caller.
- Logger nên ghi dữ liệu chẩn đoán độc lập, không cập nhật hàng đang bị transaction cha khóa.
- Autonomous transaction tiêu thụ tài nguyên và có thể gặp lỗi riêng; cần thiết kế dung lượng, retention và quyền.

Không dùng autonomous transaction như một cách tùy tiện để COMMIT một phần nghiệp vụ.

## 13. RAISE_APPLICATION_ERROR trong trigger

Trigger thường dùng để bảo vệ một quy tắc dữ liệu ở thời điểm INSERT, UPDATE hoặc DELETE. Khi dữ liệu vi phạm quy tắc, trigger có thể phát sinh lỗi ứng dụng để từ chối statement.

### 13.1. Trigger kiểm tra số tiền

```sql
CREATE OR REPLACE TRIGGER trg_demo_order_amount
BEFORE INSERT OR UPDATE OF amount
ON demo_orders
FOR EACH ROW
BEGIN
    IF :NEW.amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20070,
            'Order amount must not be negative'
        );
    END IF;
END trg_demo_order_amount;
/
```

Trigger chạy trước khi ghi hàng. Nếu `:NEW.amount` âm, trigger phát sinh lỗi `ORA-20070` và DML bị từ chối.

### 13.2. Thêm ngữ cảnh từ trigger nhưng giữ lỗi gốc

Nếu trigger gọi procedure khác và procedure phát sinh lỗi, trigger có thể thêm ngữ cảnh:

```sql
CREATE OR REPLACE TRIGGER trg_demo_order_check
BEFORE INSERT
ON demo_orders
FOR EACH ROW
BEGIN
    validate_order_amount(:NEW.amount);
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20071,
            'Order validation failed for customer ' ||
            :NEW.customer_id,
            TRUE
        );
END trg_demo_order_check;
/
```

`TRUE` giữ error stack hiện tại và thêm lỗi ứng dụng của trigger. Nếu cần điều tra sâu, logger nên lưu `FORMAT_ERROR_STACK` và `FORMAT_ERROR_BACKTRACE` tại nơi bắt exception.

### 13.3. Trigger không nên che nguyên nhân bằng message chung

Tránh:

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20099,
            'Database operation failed'
        );
```

Nếu không giữ stack, lỗi chi tiết bên trong procedure có thể bị thay thế. Hãy quyết định rõ: phát lại nguyên lỗi bằng `RAISE;`, hay thêm ngữ cảnh bằng `RAISE_APPLICATION_ERROR(..., TRUE)`.

### 13.4. Lỗi trigger được trả về caller như thế nào?

Khi trigger phát sinh lỗi trong lúc một DML statement chạy:

- Statement DML bị thất bại.
- Oracle hoàn tác các thay đổi của statement đó theo tính nguyên tử statement.
- Exception truyền về session/client gọi DML.
- Client có thể nhận mã lỗi ứng dụng và thông tin trigger execution liên quan.

Thông báo thực tế có thể chứa `ORA-04088: error during execution of trigger ...` cùng lỗi gốc hoặc lỗi ứng dụng. Hãy giữ toàn bộ stack khi điều tra, không chỉ copy dòng ORA-04088.

### 13.5. Trigger không được COMMIT hoặc ROLLBACK transaction cha

Trigger thông thường không thể COMMIT hoặc ROLLBACK transaction đang thực hiện DML. Nếu cần ghi log độc lập, có thể có thiết kế autonomous transaction riêng, nhưng phải hiểu rõ dữ liệu chưa commit và tính độc lập của log.

Không biến trigger thành nơi điều phối nhiều transaction nghiệp vụ. Trigger nên giữ trách nhiệm hẹp, rõ và tránh side effect khó dự đoán.

## 14. Bảo toàn thông tin nguyên nhân qua nhiều lớp

Một thiết kế lỗi tốt giữ được ba lớp thông tin:

1. **Mã nguyên nhân:** mã Oracle gốc hoặc mã ứng dụng cụ thể.
2. **Ngữ cảnh nghiệp vụ:** order ID, customer ID, operation hoặc request ID.
3. **Vị trí kỹ thuật:** error stack, backtrace và call stack.

### 14.1. Ví dụ tầng dữ liệu

```sql
CREATE OR REPLACE PROCEDURE reserve_stock (
    p_product_id IN NUMBER,
    p_quantity IN NUMBER
) AS
    v_available NUMBER;
BEGIN
    SELECT available_quantity
    INTO v_available
    FROM inventory
    WHERE product_id = p_product_id;

    IF p_quantity > v_available THEN
        RAISE_APPLICATION_ERROR(
            -20080,
            'Insufficient stock for product ' || p_product_id
        );
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20081,
            'Inventory record not found for product ' || p_product_id,
            TRUE
        );
END reserve_stock;
/
```

Tầng này hiểu dữ liệu inventory và có thể phân biệt không có record với không đủ hàng.

### 14.2. Ví dụ tầng điều phối

```sql
CREATE OR REPLACE PROCEDURE process_order_stock (
    p_order_id IN NUMBER,
    p_product_id IN NUMBER,
    p_quantity IN NUMBER
) AS
BEGIN
    reserve_stock(p_product_id, p_quantity);
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20082,
            'Stock reservation failed for order ' || p_order_id,
            TRUE
        );
END process_order_stock;
/
```

Tầng điều phối thêm order ID nhưng giữ lỗi stack đã có. Khi caller nhận lỗi, có thể thấy ngữ cảnh order và nguyên nhân inventory.

### 14.3. Ở tầng ứng dụng

Ứng dụng nên:

- Ghi request/correlation ID.
- Lấy mã Oracle và toàn bộ chuỗi lỗi do driver cung cấp khi được phép.
- Phân biệt lỗi nghiệp vụ dự kiến với lỗi hệ thống.
- Trả thông điệp thân thiện cho người dùng, không phơi bày stack nội bộ.
- Giữ stack kỹ thuật trong log có kiểm soát quyền truy cập.

Không trả nguyên SQLERRM, tên schema, câu SQL nội bộ hoặc stack database cho mọi end user. Bảo toàn nguyên nhân trong hệ thống log không đồng nghĩa công khai mọi chi tiết cho client.

## 15. UTL_CALL_STACK và thông tin chẩn đoán chi tiết

Trong các phiên bản Oracle hỗ trợ `UTL_CALL_STACK` (từ Oracle Database 12c), package này cung cấp API có cấu trúc để đọc call stack, error stack và backtrace.

Các hàm có thể dùng gồm:

- `UTL_CALL_STACK.ERROR_DEPTH`: số lỗi trong error stack.
- `UTL_CALL_STACK.ERROR_NUMBER(n)`: mã lỗi ở vị trí n.
- `UTL_CALL_STACK.ERROR_MSG(n)`: thông điệp lỗi ở vị trí n.
- `UTL_CALL_STACK.BACKTRACE_DEPTH`: số frame trong backtrace.
- `UTL_CALL_STACK.BACKTRACE_UNIT(n)`: unit ở frame backtrace.
- `UTL_CALL_STACK.BACKTRACE_LINE(n)`: dòng tương ứng trong backtrace.
- `UTL_CALL_STACK.DYNAMIC_DEPTH`: độ sâu dynamic call stack.
- `UTL_CALL_STACK.CONCATENATE_SUBPROGRAM(n)`: tên subprogram ở frame tương ứng.

Ví dụ minh họa:

```sql
BEGIN
    RAISE_APPLICATION_ERROR(-20090, 'Diagnostic example');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error depth=' || UTL_CALL_STACK.ERROR_DEPTH
        );

        FOR i IN 1 .. UTL_CALL_STACK.ERROR_DEPTH LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Error ' || i ||
                ': ' || UTL_CALL_STACK.ERROR_NUMBER(i) ||
                ' - ' || UTL_CALL_STACK.ERROR_MSG(i)
            );
        END LOOP;

        FOR i IN 1 .. UTL_CALL_STACK.BACKTRACE_DEPTH LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Backtrace ' || i ||
                ': ' || UTL_CALL_STACK.BACKTRACE_UNIT(i) ||
                ' line ' || UTL_CALL_STACK.BACKTRACE_LINE(i)
            );
        END LOOP;

        RAISE;
END;
/
```

Chỉ gọi index trong khoảng depth được trả về. Quyền thực thi và API cụ thể cần được kiểm tra theo phiên bản Oracle. `DBMS_UTILITY.FORMAT_ERROR_STACK` và `FORMAT_ERROR_BACKTRACE` vẫn là cách đơn giản, phổ biến để ghi chuỗi chẩn đoán.

## 16. Error handling trong trigger: các nguyên tắc quan trọng

### 16.1. Chỉ dùng trigger khi quy tắc cần được áp dụng ở database

Trigger phù hợp với quy tắc phải bảo vệ ở mọi đường DML, kể cả khi dữ liệu được ghi bởi SQL client, batch hoặc ứng dụng khác. Tuy nhiên, nếu một quy tắc có thể biểu diễn bằng CHECK constraint, NOT NULL, UNIQUE hoặc FOREIGN KEY, constraint thường đơn giản và rõ hơn trigger.

Ví dụ số tiền không âm nên ưu tiên:

```sql
ALTER TABLE demo_orders
ADD CONSTRAINT ck_demo_order_amount_nonnegative
CHECK (amount >= 0);
```

Trigger có thể bổ sung kiểm tra phức tạp hơn nhưng không nên thay constraint đơn giản.

### 16.2. Tránh bắt rồi bỏ qua lỗi trong trigger

Nếu trigger bắt lỗi và không re-raise, statement DML có thể tiếp tục hoặc kết thúc theo hành vi đã được code quyết định, làm dữ liệu không phản ánh đúng quy tắc. Không viết:

```sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
```

trong trigger để “không làm gián đoạn” DML, trừ khi nghiệp vụ có thiết kế rõ ràng cho việc bỏ qua lỗi đó.

### 16.3. Không tự ý thay đổi loại lỗi

Nếu trigger gọi procedure và nhận lỗi ORA cụ thể, hãy dùng `RAISE;` để truyền nguyên lỗi hoặc `RAISE_APPLICATION_ERROR(..., TRUE)` để thêm context. Dùng `FALSE` chỉ khi có chủ đích thay error stack bằng mã API khác và đã lưu nguyên nhân ở nơi khác.

### 16.4. Trigger và lỗi mutating table là vấn đề riêng

Một số row-level trigger không được truy vấn hoặc sửa trực tiếp chính bảng đang bị statement thay đổi, có thể dẫn đến `ORA-04091: table is mutating`. Đây là hạn chế về tính nhất quán/trigger timing, không phải lỗi được giải quyết bằng `RAISE` hay `RAISE_APPLICATION_ERROR`. Cần thiết kế lại logic, dùng compound trigger hoặc cơ chế phù hợp với phiên bản và nghiệp vụ.

## 17. Những lỗi thường gặp khi phát sinh hoặc truyền exception

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-06510` | User-defined exception không được xử lý | Bắt exception hoặc ánh xạ sang mã ứng dụng phù hợp |
| `ORA-20000` đến `ORA-20999` | Lỗi ứng dụng được phát sinh | Tra mã lỗi trong hợp đồng API |
| `ORA-21000` / invalid error number | Mã truyền vào `RAISE_APPLICATION_ERROR` ngoài dải hợp lệ | Dùng số âm trong khoảng -20000 đến -20999 |
| Lỗi gốc biến mất | Dùng `RAISE_APPLICATION_ERROR` mặc định `FALSE` trong handler | Dùng `RAISE;` hoặc `keep_errors => TRUE` |
| Backtrace chỉ tới handler | Tạo exception mới hoặc lấy thông tin quá muộn | Chụp `FORMAT_ERROR_BACKTRACE` trước khi chuyển lỗi |
| Lỗi log che lỗi chính | Logger phát sinh exception mới | Bảo vệ logger bằng block con hoặc chính sách logging rõ ràng |
| Không có log sau rollback | Log dùng transaction nghiệp vụ rồi bị rollback | Cân nhắc autonomous logger nếu yêu cầu log tồn tại độc lập |
| Trigger trả ORA-04088 | Trigger phát sinh lỗi khi DML chạy | Đọc toàn bộ stack, tìm mã lỗi gốc và backtrace |
| Caller chỉ thấy message chung | Handler thay lỗi gốc mà không lưu stack | Giữ stack và ghi log có context |
| Message bị cắt | Thông điệp vượt giới hạn 2048 byte | Rút gọn message, lưu chi tiết vào log |
| Log chứa dữ liệu nhạy cảm | Ghi toàn bộ payload/SQLERRM không lọc | Chỉ lưu context cần thiết, phân quyền và retention |
| Dùng SQLERRM để phân loại | Phụ thuộc chuỗi message/ngôn ngữ | Dùng exception name hoặc SQLCODE |

### 17.1. Mã lỗi ngoài dải

`RAISE_APPLICATION_ERROR` yêu cầu mã từ `-20000` đến `-20999`. Nếu truyền mã ngoài khoảng, Oracle phát sinh lỗi về tham số error number không hợp lệ. Đừng dùng `-1`, `-54` hoặc mã ORA bất kỳ như mã tùy chỉnh của ứng dụng; các mã đó thuộc không gian lỗi Oracle.

### 17.2. Message quá dài

Thông điệp của `RAISE_APPLICATION_ERROR` có giới hạn 2048 byte. Chuỗi Unicode có thể dùng nhiều byte cho một ký tự, nên không nên chỉ đếm số ký tự. Giữ message ngắn và ghi phần chi tiết vào bảng log.

### 17.3. Bắt OTHERS nhưng không RAISE

```sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        NULL;
```

Block có thể kết thúc như thể lỗi đã được xử lý, trong khi caller không nhận được dấu hiệu thất bại. Nếu không thực sự khôi phục được trạng thái hợp lệ, hãy phát lại exception.

## 18. Quy trình thiết kế error handling

Một quy trình thực tế:

1. **Xác định lỗi dự kiến:** lỗi dữ liệu, lỗi nghiệp vụ hay lỗi hệ thống.
2. **Chọn cách biểu đạt:** predefined exception, user-defined exception hoặc mã `RAISE_APPLICATION_ERROR`.
3. **Xác định API contract:** caller cần phân biệt những mã lỗi nào.
4. **Bắt ở đúng tầng:** chỉ bắt khi tầng đó có thể xử lý, cleanup hoặc bổ sung context.
5. **Chụp thông tin gốc:** SQLCODE, SQLERRM, error stack và backtrace trước khi tạo lỗi mới.
6. **Ghi log an toàn:** giữ request ID và context nghiệp vụ cần thiết, tránh dữ liệu nhạy cảm.
7. **Truyền lỗi tiếp:** dùng `RAISE;` hoặc thêm lỗi ứng dụng với `keep_errors => TRUE`.
8. **Kiểm soát transaction:** quyết định rõ statement/transaction có rollback hay caller chịu trách nhiệm.
9. **Kiểm thử từ client:** kiểm tra mã lỗi và stack thực tế qua SQL Developer, SQLcl hoặc JDBC.

### 18.1. Khi nào nên chuyển lỗi thành mã nghiệp vụ?

Chuyển lỗi khi caller cần một API ổn định, ví dụ thay `NO_DATA_FOUND` thành `ORA-20020 CUSTOMER_NOT_FOUND`. Nhưng nếu có ích cho điều tra, hãy giữ stack gốc bằng `TRUE` và lưu backtrace.

### 18.2. Khi nào nên phát lại nguyên lỗi?

Nếu tầng hiện tại không có cách xử lý lỗi và chỉ muốn caller biết thao tác thất bại, dùng `RAISE;`. Đừng thêm handler chỉ để in SQLERRM rồi thay bằng thông điệp chung.

### 18.3. Khi nào nên log?

Log tại một hoặc một vài ranh giới có ý nghĩa, nơi có đủ context và trách nhiệm vận hành. Nếu mọi tầng đều log cùng exception rồi re-raise, một lỗi có thể tạo nhiều bản ghi trùng. Hãy chọn tầng log chính và truyền request ID qua các tầng.

## 19. Bài thực hành tổng hợp

Các ví dụ dưới đây tạo đối tượng riêng trong schema lab. Chỉ chạy khi có quyền tạo bảng/procedure/trigger và không dùng tên trùng đối tượng nghiệp vụ.

### Bước 1. Tạo bảng đơn hàng lab

```sql
CREATE TABLE lab_error_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12, 2) NOT NULL,
    status VARCHAR2(20) DEFAULT 'NEW' NOT NULL
);
```

### Bước 2. Thử RAISE exception tự định nghĩa

```sql
DECLARE
    e_invalid_amount EXCEPTION;
    v_amount NUMBER := -10;
BEGIN
    IF v_amount < 0 THEN
        RAISE e_invalid_amount;
    END IF;
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE('Invalid amount');
END;
/
```

### Bước 3. Thử RAISE_APPLICATION_ERROR

```sql
BEGIN
    RAISE_APPLICATION_ERROR(
        -20010,
        'Lab validation failed'
    );
END;
/
```

Quan sát mã ORA và thông điệp phía client.

### Bước 4. Thử RAISE; giữ lỗi gốc

```sql
BEGIN
    DECLARE
        v_amount NUMBER;
    BEGIN
        v_amount := 1 / 0;
    END;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE || ': ' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
/
```

Quan sát exception cuối cùng vẫn là lỗi chia cho 0.

### Bước 5. Thử thêm context mà giữ stack

```sql
BEGIN
    BEGIN
        RAISE_APPLICATION_ERROR(-20021, 'Original inventory error');
    EXCEPTION
        WHEN OTHERS THEN
            RAISE_APPLICATION_ERROR(
                -20022,
                'Order 1001 could not reserve inventory',
                TRUE
            );
    END;
END;
/
```

So sánh với cùng ví dụ nhưng dùng tham số thứ ba `FALSE` hoặc bỏ tham số thứ ba. Quan sát sự khác nhau của error stack trong client và `FORMAT_ERROR_STACK`.

### Bước 6. Tạo trigger từ chối số tiền âm

```sql
CREATE OR REPLACE TRIGGER trg_lab_error_orders
BEFORE INSERT OR UPDATE OF amount
ON lab_error_orders
FOR EACH ROW
BEGIN
    IF :NEW.amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20030,
            'Amount must be non-negative'
        );
    END IF;
END trg_lab_error_orders;
/
```

### Bước 7. Thử DML hợp lệ

```sql
INSERT INTO lab_error_orders (
    order_id,
    customer_id,
    amount
)
VALUES (1, 501, 1000);

COMMIT;
```

### Bước 8. Thử DML không hợp lệ

```sql
INSERT INTO lab_error_orders (
    order_id,
    customer_id,
    amount
)
VALUES (2, 501, -100);
```

Quan sát lỗi ORA-20030 và lỗi trigger execution liên quan. Kiểm tra hàng không hợp lệ không được chèn.

### Bước 9. Kiểm tra metadata trigger

```sql
SELECT trigger_name,
       status,
       triggering_event,
       trigger_type
FROM user_triggers
WHERE trigger_name = 'TRG_LAB_ERROR_ORDERS';
```

### Bước 10. Dọn đối tượng lab

Chỉ khi chắc chắn đây là đối tượng do bạn tạo và không cần giữ dữ liệu:

```sql
DROP TRIGGER trg_lab_error_orders;
DROP TABLE lab_error_orders PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin theo hành vi lệnh; DDL có commit ngầm. Không chạy trên bảng nghiệp vụ hoặc đối tượng dùng chung.

## 20. Quy tắc ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Phát sinh exception đã khai báo | `RAISE exception_name;` |
| Phát lại exception hiện tại trong handler | `RAISE;` |
| Trả mã lỗi nghiệp vụ | `RAISE_APPLICATION_ERROR(-20000..-20999, message)` |
| Thêm lỗi ứng dụng nhưng giữ stack hiện tại | `RAISE_APPLICATION_ERROR(code, message, TRUE)` |
| Thay error stack hiện tại | `RAISE_APPLICATION_ERROR(code, message, FALSE)` hoặc bỏ tham số thứ ba |
| Lấy mã/thông điệp hiện tại | `SQLCODE`, `SQLERRM` |
| Lấy toàn bộ error stack | `DBMS_UTILITY.FORMAT_ERROR_STACK` |
| Tìm dòng phát sinh exception | `DBMS_UTILITY.FORMAT_ERROR_BACKTRACE` |
| Xem call stack tại thời điểm hiện tại | `DBMS_UTILITY.FORMAT_CALL_STACK` |
| Ánh xạ mã ORA sang exception name | `PRAGMA EXCEPTION_INIT` |
| Ghi log độc lập transaction nghiệp vụ | Cân nhắc autonomous logger với thiết kế rõ ràng |
| Xử lý lỗi trigger | Đọc toàn bộ stack; phát lại hoặc thêm context có giữ stack |
| Bảo vệ lỗi gốc khi logger lỗi | Bọc logger trong block con, sau đó `RAISE;` |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `RAISE exception_name;` dùng để làm gì?

**Trả lời:** Chủ động phát sinh một exception đã được khai báo trong scope.

**Câu 2.** `RAISE;` không có tên dùng trong trường hợp nào?

**Trả lời:** Trong exception handler để phát lại exception hiện tại, giữ nguyên lỗi đang được xử lý.

**Câu 3.** `RAISE_APPLICATION_ERROR` dùng mã trong khoảng nào?

**Trả lời:** Mã số âm từ `-20000` đến `-20999`.

**Câu 4.** Thông điệp của RAISE_APPLICATION_ERROR tối đa bao nhiêu byte?

**Trả lời:** 2048 byte.

**Câu 5.** Tham số thứ ba của RAISE_APPLICATION_ERROR có ý nghĩa gì?

**Trả lời:** `TRUE` thêm lỗi ứng dụng vào error stack hiện tại; `FALSE` thay thế stack hiện tại. Mặc định là FALSE.

**Câu 6.** Vì sao dùng `RAISE_APPLICATION_ERROR` mặc định trong handler có thể làm mất nguyên nhân?

**Trả lời:** Vì mặc định FALSE thay error stack hiện tại bằng lỗi ứng dụng mới.

**Câu 7.** Khi chỉ cần log rồi chuyển lỗi lên caller, nên dùng gì?

**Trả lời:** Chụp thông tin cần thiết, ghi log và dùng `RAISE;` trong handler.

**Câu 8.** SQLCODE và SQLERRM khác FORMAT_ERROR_STACK như thế nào?

**Trả lời:** SQLCODE/SQLERRM cung cấp mã và thông điệp hiện tại; FORMAT_ERROR_STACK trả chuỗi error stack có thể chứa nhiều lỗi.

**Câu 9.** FORMAT_ERROR_BACKTRACE cho biết điều gì?

**Trả lời:** Vị trí trong PL/SQL nơi exception được phát sinh, hữu ích khi lỗi được bắt ở tầng trên.

**Câu 10.** FORMAT_CALL_STACK khác error backtrace ở đâu?

**Trả lời:** Call stack thể hiện chuỗi lời gọi tại thời điểm lấy; error backtrace chỉ vị trí phát sinh exception.

**Câu 11.** PRAGMA EXCEPTION_INIT có tự phát sinh exception không?

**Trả lời:** Không. Nó ánh xạ mã lỗi Oracle với tên exception; muốn phát sinh exception đã khai báo thì dùng RAISE.

**Câu 12.** Vì sao logger có thể dùng autonomous transaction?

**Trả lời:** Để log có thể COMMIT độc lập và tồn tại ngay cả khi transaction nghiệp vụ rollback; cần chấp nhận các giới hạn về dữ liệu chưa commit và tài nguyên.

**Câu 13.** Nếu logger lỗi trong handler, làm sao tránh che lỗi gốc?

**Trả lời:** Bọc logger trong block con và xử lý lỗi logger riêng, sau đó `RAISE;` ở handler ngoài.

**Câu 14.** Khi trigger phát sinh RAISE_APPLICATION_ERROR, DML statement sẽ thế nào?

**Trả lời:** Statement thất bại và các thay đổi của statement được rollback theo tính nguyên tử statement; lỗi được truyền về caller.

**Câu 15.** Có nên dùng WHEN OTHERS THEN NULL trong trigger?

**Trả lời:** Không, trừ khi có chính sách bỏ qua lỗi rất cụ thể; thông thường phải xử lý hoặc phát lại để tránh DML thành công trong trạng thái sai.

## 22. Kết luận

`RAISE` và `RAISE_APPLICATION_ERROR` phục vụ hai nhu cầu khác nhau. `RAISE exception_name;` chủ động phát sinh exception đã khai báo; `RAISE;` trong handler phát lại exception hiện tại và là cách phù hợp khi chỉ cần log, cleanup hoặc truyền lỗi lên caller. `RAISE_APPLICATION_ERROR` tạo mã lỗi nghiệp vụ trong dải `-20000` đến `-20999`, giúp API database trả thông điệp có ý nghĩa cho ứng dụng.

Điểm quyết định khi bảo toàn nguyên nhân là tham số `keep_errors`: `TRUE` thêm lỗi ứng dụng vào error stack hiện tại; `FALSE` hoặc mặc định thay thế stack. Khi cần chẩn đoán, hãy chụp `SQLCODE`, `SQLERRM`, `DBMS_UTILITY.FORMAT_ERROR_STACK` và `FORMAT_ERROR_BACKTRACE` trước khi tạo exception mới. Call stack bổ sung thông tin về đường gọi hiện tại; logger có cấu trúc giúp lưu dữ liệu để điều tra sau khi session kết thúc.

Trong trigger, lỗi phát sinh sẽ làm DML statement thất bại và được trả về caller. Hãy dùng constraint cho các quy tắc đơn giản, giữ trigger gọn, không nuốt lỗi và đọc toàn bộ stack thay vì chỉ nhìn ORA-04088. Một chiến lược exception tốt giữ được cả mã lỗi ổn định, ngữ cảnh nghiệp vụ và vị trí kỹ thuật, đồng thời không để lỗi phụ như logging che mất nguyên nhân ban đầu.
