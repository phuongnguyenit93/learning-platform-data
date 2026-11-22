# SQLCODE, SQLERRM, FORMAT_ERROR_STACK và FORMAT_ERROR_BACKTRACE

Khi một câu lệnh SQL hoặc đoạn PL/SQL phát sinh lỗi, Oracle cung cấp nhiều cách để lấy thông tin chẩn đoán. Bốn công cụ thường được dùng trong exception handler là:

- **SQLCODE**: trả về mã số của exception hiện tại.
- **SQLERRM**: trả về thông báo lỗi tương ứng với exception hiện tại hoặc một mã lỗi được chỉ định.
- **DBMS_UTILITY.FORMAT_ERROR_STACK**: trả về error stack, tức chuỗi thông báo của các lỗi đang có trong stack.
- **DBMS_UTILITY.FORMAT_ERROR_BACKTRACE**: trả về đường dẫn backtrace từ vị trí exception được phát sinh tới nơi đang xử lý exception.

Các công cụ này bổ sung cho nhau. SQLCODE giúp phân loại lỗi bằng mã; SQLERRM cung cấp thông điệp ngắn của lỗi hiện tại; FORMAT_ERROR_STACK cho biết chuỗi lỗi; FORMAT_ERROR_BACKTRACE giúp tìm dòng PL/SQL nơi lỗi được phát sinh, kể cả khi exception được bắt ở một procedure hoặc block bên ngoài.

Trong trigger, những thông tin này đặc biệt hữu ích vì lỗi có thể phát sinh từ trigger hoặc từ procedure mà trigger gọi, sau đó truyền ngược về câu INSERT/UPDATE/DELETE kích hoạt trigger. Một exception handler được thiết kế tốt cần ghi lại thông tin cần thiết, giữ nguyên lỗi khi cần và để caller nhận được kết quả thất bại chính xác.

## 1. Exception và exception handler

PL/SQL dùng exception để biểu diễn tình huống bất thường trong quá trình thực thi. Một exception có thể phát sinh từ:
- Oracle Database, ví dụ chia cho 0 hoặc vi phạm unique constraint.
- Một exception có tên được khai báo trong PL/SQL.
- Lệnh RAISE_APPLICATION_ERROR do ứng dụng chủ động phát sinh.
- Một exception được ném lại từ procedure/function bên dưới.

Cấu trúc cơ bản:

~~~sql
BEGIN
    -- Các câu lệnh có thể phát sinh lỗi.
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Khong the chia cho 0');
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Loi khac');
        RAISE;
END;
/
~~~

Phần EXCEPTION chỉ chạy khi một exception phát sinh trong phần BEGIN tương ứng và không được xử lý ở một block con trước đó.

### 1.1. Exception handler có phạm vi theo block

~~~sql
BEGIN
    BEGIN
        -- Block con.
        RAISE ZERO_DIVIDE;
    EXCEPTION
        WHEN ZERO_DIVIDE THEN
            DBMS_OUTPUT.PUT_LINE('Da xu ly trong block con');
    END;

    DBMS_OUTPUT.PUT_LINE('Block ngoai tiep tuc');
END;
/
~~~

Block con bắt exception và không ném lại, nên block ngoài tiếp tục bình thường.

Nếu block con ghi log rồi RAISE lại:

~~~sql
BEGIN
    BEGIN
        RAISE ZERO_DIVIDE;
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('Ghi nhan tai block con');
            RAISE;
    END;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Block ngoai nhan lai ZERO_DIVIDE');
END;
/
~~~

RAISE không có tên exception trong handler sẽ ném lại exception hiện tại. Đây là cách giữ lỗi gốc khi chỉ muốn bổ sung logging.

### 1.2. OTHERS là handler tổng quát

WHEN OTHERS nhận những exception chưa được xử lý bởi các nhánh cụ thể. Nó hữu ích cho logging tập trung, nhưng không nên dùng để che lỗi:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Ghi thông tin lỗi.
        RAISE;
~~~

Nếu handler chỉ in thông báo rồi kết thúc mà không RAISE, exception được xem là đã xử lý và caller có thể tiếp tục như thể subprogram hoàn thành bình thường. Chỉ làm vậy khi chương trình thật sự có phương án phục hồi và kết quả trả về thể hiện đúng trạng thái.

## 2. SQLCODE

SQLCODE là hàm PL/SQL trả về mã số của exception hiện tại. Thông thường gọi trong exception handler:

~~~sql
DECLARE
    l_result NUMBER;
BEGIN
    l_result := 10 / 0;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
END;
/
~~~

Kết quả điển hình:

~~~text
SQLCODE=-1476
~~~

Mã -1476 tương ứng với ORA-01476: divisor is equal to zero.

### 2.1. SQLCODE trong exception handler

Trong handler, SQLCODE phản ánh exception đang được xử lý. Ví dụ:

~~~sql
BEGIN
    INSERT INTO employees(employee_id, full_name)
    VALUES (101, 'An');

EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Duplicate key');
END;
/
~~~

Nếu lỗi thực tế là unique constraint violation, SQLCODE thường là -1 (ORA-00001).

Không nên chỉ dựa vào nội dung message để phân loại lỗi khi mã lỗi đã đủ rõ và ổn định hơn cho logic xử lý.

### 2.2. SQLCODE ngoài exception handler

Nếu không có exception đang được xử lý, SQLCODE trả về 0:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
END;
/
~~~

Kết quả:

~~~text
SQLCODE=0
~~~

Vì vậy, không dùng SQLCODE như một biến trạng thái cho biết câu SQL trước đó có thành công hay không ở bất kỳ vị trí nào. Nó được thiết kế để lấy mã của exception hiện hành.

### 2.3. Mã của exception do người dùng định nghĩa

Exception được khai báo trong PL/SQL:

~~~sql
DECLARE
    e_invalid_state EXCEPTION;
BEGIN
    RAISE e_invalid_state;
EXCEPTION
    WHEN e_invalid_state THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
END;
/
~~~

Một user-defined exception không được ánh xạ tới mã Oracle cụ thể thường có SQLCODE = +1 và SQLERRM là thông báo chung "User-Defined Exception".

Nếu muốn exception gắn với một mã ORA cụ thể, có thể dùng PRAGMA EXCEPTION_INIT hoặc RAISE_APPLICATION_ERROR.

### 2.4. Exception được ánh xạ bằng EXCEPTION_INIT

~~~sql
DECLARE
    e_business_error EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_business_error, -20041);
BEGIN
    RAISE_APPLICATION_ERROR(-20041, 'Trang thai don hang khong hop le');
EXCEPTION
    WHEN e_business_error THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
END;
/
~~~

PRAGMA EXCEPTION_INIT liên kết một exception có tên với mã lỗi Oracle. Khi handler bắt exception đó, SQLCODE trả mã đã ánh xạ.

### 2.5. Dùng SQLCODE để phân loại lỗi

Có thể ghi nhận mã rồi quyết định cách xử lý:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -1 THEN
            DBMS_OUTPUT.PUT_LINE('Trung khoa duy nhat');
        ELSIF SQLCODE = -2291 THEN
            DBMS_OUTPUT.PUT_LINE('Thieu khoa cha');
        ELSE
            RAISE;
        END IF;
~~~

Chỉ xử lý riêng những mã mà ứng dụng hiểu rõ. Các lỗi còn lại nên được truyền lên caller để không làm mất thông tin.

## 3. SQLERRM

SQLERRM trả về thông báo lỗi. Không có đối số, nó lấy thông báo cho exception hiện tại:

~~~sql
DECLARE
    l_result NUMBER;
BEGIN
    l_result := 10 / 0;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

Kết quả điển hình:

~~~text
ORA-01476: divisor is equal to zero
~~~

SQLERRM hữu ích khi cần thông điệp để ghi log hoặc hiển thị lỗi kỹ thuật. Tuy nhiên, message có thể được bản địa hóa theo ngôn ngữ NLS của session; không nên dùng toàn bộ chuỗi message làm khóa logic.

### 3.1. SQLERRM ngoài exception handler

Khi gọi SQLERRM mà không có exception đang được xử lý, hàm trả thông báo cho mã 0, thường là:

~~~text
ORA-0000: normal, successful completion
~~~

Điều này không có nghĩa SQLERRM có thể được dùng để kiểm tra thành công/thất bại của câu SQL trước đó. Hãy gọi trong exception handler để lấy thông tin exception cần xử lý.

### 3.2. SQLERRM với mã lỗi được chỉ định

SQLERRM có thể nhận một error number để lấy thông báo tương ứng:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(SQLERRM(-1));
    DBMS_OUTPUT.PUT_LINE(SQLERRM(-2291));
END;
/
~~~

Cách này hữu ích khi cần xem message cho một mã Oracle đã biết. Nó không tái tạo stack của một lần thực thi lỗi trước đó và không thay thế FORMAT_ERROR_STACK.

### 3.3. SQLERRM không phải toàn bộ error stack

Giả sử lỗi truyền qua nhiều tầng procedure. SQLERRM thường cho thông điệp của exception hiện tại, ví dụ ORA-01476. Nó không phải công cụ đầy đủ để xem tất cả dòng ORA-06512 hoặc toàn bộ chuỗi lỗi liên quan.

Để lấy chuỗi lỗi, dùng DBMS_UTILITY.FORMAT_ERROR_STACK.

### 3.4. Không dùng SQLERRM để quyết định nghiệp vụ bằng cách so chuỗi

Không nên viết:

~~~sql
IF SQLERRM = 'ORA-00001: unique constraint violated' THEN
    ...
END IF;
~~~

Thông báo có thể thay đổi theo ngôn ngữ, phiên bản hoặc ngữ cảnh. Dùng SQLCODE hoặc bắt exception có tên như DUP_VAL_ON_INDEX để phân loại. Dùng SQLERRM để cung cấp thông tin chẩn đoán cho con người.

### 3.5. Độ dài thông báo

SQLERRM trả về chuỗi thông báo có giới hạn độ dài của API. Nếu cần chẩn đoán đầy đủ hơn, đặc biệt khi có nhiều lỗi xếp chồng, hãy dùng FORMAT_ERROR_STACK và lưu kết quả vào biến VARCHAR2 đủ lớn trong PL/SQL.

## 4. DBMS_UTILITY.FORMAT_ERROR_STACK

DBMS_UTILITY.FORMAT_ERROR_STACK trả về error stack hiện tại dưới dạng chuỗi. Nó hữu ích khi exception stack chứa nhiều thông báo, ví dụ lỗi ứng dụng được thêm vào lỗi ban đầu.

Cú pháp:

~~~sql
DBMS_UTILITY.FORMAT_ERROR_STACK
~~~

Ví dụ:

~~~sql
DECLARE
    l_result NUMBER;
BEGIN
    l_result := 10 / 0;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
END;
/
~~~

Kết quả có thể chứa thông báo ORA-01476 cùng các dòng vị trí PL/SQL liên quan.

### 4.1. Khác biệt với SQLERRM

| Công cụ | Thông tin chính |
| --- | --- |
| SQLCODE | Mã số của exception hiện tại |
| SQLERRM | Thông báo của exception hiện tại hoặc mã được chỉ định |
| FORMAT_ERROR_STACK | Chuỗi error stack hiện tại |
| FORMAT_ERROR_BACKTRACE | Đường dẫn từ vị trí phát sinh lỗi tới handler |

SQLERRM phù hợp khi cần một message ngắn. FORMAT_ERROR_STACK phù hợp khi cần lưu chuỗi lỗi đầy đủ hơn cho chẩn đoán.

### 4.2. Error stack có thể chứa lỗi được thêm vào

Một procedure có thể bắt lỗi rồi gọi RAISE_APPLICATION_ERROR để thêm thông tin nghiệp vụ. Tham số thứ ba của RAISE_APPLICATION_ERROR quyết định có thêm lỗi mới vào error stack hiện tại hay thay thế stack hiện có.

~~~sql
BEGIN
    RAISE_APPLICATION_ERROR(
        -20041,
        'Khong the hoan tat thanh toan',
        TRUE
    );
END;
/
~~~

Khi tham số thứ ba là TRUE, lỗi ứng dụng được thêm vào stack. Khi là FALSE hoặc bỏ qua tham số này, lỗi mới thay thế stack hiện có theo hành vi của RAISE_APPLICATION_ERROR.

Khi cần giữ nguyên lỗi gốc, RAISE trong exception handler thường là cách đơn giản nhất. Nếu cần chuyển lỗi thành mã ứng dụng mới, hãy lưu thông tin gốc trước khi gọi RAISE_APPLICATION_ERROR.

### 4.3. Không gọi FORMAT_ERROR_STACK ngoài ngữ cảnh lỗi để kiểm tra câu lệnh trước

FORMAT_ERROR_STACK được thiết kế để lấy error stack hiện tại. Gọi nó ngoài exception context không cung cấp một bản ghi lịch sử các lỗi của session. Muốn lưu lịch sử, ứng dụng cần tự ghi log tại thời điểm bắt lỗi.

## 5. DBMS_UTILITY.FORMAT_ERROR_BACKTRACE

FORMAT_ERROR_BACKTRACE trả về thông tin backtrace từ nơi exception được phát sinh tới vị trí hiện đang xử lý exception.

Cú pháp:

~~~sql
DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
~~~

Điểm quan trọng: exception có thể được bắt ở một procedure bên ngoài, nhưng backtrace vẫn giúp xác định dòng PL/SQL bên trong nơi lỗi bắt đầu.

### 5.1. Ví dụ lỗi phát sinh ở procedure con

Tạo procedure con:

~~~sql
CREATE OR REPLACE PROCEDURE divide_demo (
    p_numerator IN NUMBER,
    p_denominator IN NUMBER
) AS
    l_result NUMBER;
BEGIN
    l_result := p_numerator / p_denominator;

    DBMS_OUTPUT.PUT_LINE('Result=' || l_result);
END divide_demo;
/
~~~

Tạo procedure gọi:

~~~sql
CREATE OR REPLACE PROCEDURE run_divide_demo AS
BEGIN
    divide_demo(10, 0);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END run_divide_demo;
/
~~~

Gọi:

~~~sql
BEGIN
    run_divide_demo;
END;
/
~~~

SQLCODE và SQLERRM mô tả lỗi chia cho 0. FORMAT_ERROR_BACKTRACE chỉ ra dòng trong DIVIDE_DEMO nơi phép chia phát sinh lỗi và các vị trí gọi liên quan. Số dòng cụ thể phụ thuộc nội dung source thực tế sau khi tạo procedure.

### 5.2. Backtrace khác call stack

Không nhầm ba khái niệm:

- **Error stack**: các thông báo lỗi đang được giữ.
- **Error backtrace**: vị trí exception được phát sinh và đường truyền tới handler.
- **Call stack**: các subprogram đang hoạt động tại thời điểm gọi hàm lấy call stack.

DBMS_UTILITY còn có FORMAT_CALL_STACK để xem call stack hiện tại. FORMAT_CALL_STACK trả lời “hiện đang gọi qua những tầng nào”; FORMAT_ERROR_BACKTRACE trả lời “exception được phát sinh ở đâu”. Hai kết quả có thể khác nhau nếu exception đã được truyền qua nhiều tầng hoặc handler đang chạy ở một vị trí khác.

### 5.3. Backtrace cần được lấy khi đang xử lý exception

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        -- Ghi log hoặc truyền thông tin đi tiếp.
        RAISE;
~~~

Nếu bắt exception rồi không giữ lại thông tin, sau khi rời exception handler không nên kỳ vọng gọi FORMAT_ERROR_BACKTRACE ở một vị trí khác sẽ khôi phục lại backtrace của lỗi cũ.

### 5.4. Backtrace giúp tìm lỗi trong package và trigger

Một DML có thể đi qua:
1. Câu UPDATE từ ứng dụng.
2. BEFORE UPDATE trigger.
3. Procedure được trigger gọi.
4. Function kiểm tra nghiệp vụ.
5. Một câu SQL phát sinh lỗi.

Nếu exception được bắt ở tầng gọi bên ngoài, backtrace có thể chỉ ra các dòng PL/SQL liên quan, giúp tìm đúng trigger/procedure thay vì chỉ thấy câu UPDATE thất bại.

## 6. So sánh bốn công cụ

| Công cụ | Trả về | Câu hỏi được trả lời |
| --- | --- | --- |
| SQLCODE | NUMBER | Mã lỗi là gì? |
| SQLERRM | VARCHAR2 | Thông điệp lỗi hiện tại là gì? |
| FORMAT_ERROR_STACK | VARCHAR2 | Stack thông báo lỗi đang gồm những gì? |
| FORMAT_ERROR_BACKTRACE | VARCHAR2 | Exception được phát sinh ở dòng nào và truyền tới handler ra sao? |

Một handler logging tốt thường lấy cả bốn loại thông tin:

~~~sql
DECLARE
    l_code      NUMBER;
    l_message   VARCHAR2(4000);
    l_stack     VARCHAR2(32767);
    l_backtrace VARCHAR2(32767);
BEGIN
    -- Công việc có thể phát sinh lỗi.
    RAISE_APPLICATION_ERROR(-20041, 'Invalid order state');

EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        DBMS_OUTPUT.PUT_LINE('Code: ' || l_code);
        DBMS_OUTPUT.PUT_LINE('Message: ' || l_message);
        DBMS_OUTPUT.PUT_LINE('Error stack: ' || l_stack);
        DBMS_OUTPUT.PUT_LINE('Backtrace: ' || l_backtrace);

        RAISE;
END;
/
~~~

Biến cục bộ giúp giữ lại dữ liệu chẩn đoán trước khi thực hiện thêm thao tác. Trong ứng dụng thật, ghi log vào logger được quản lý bởi hệ thống; DBMS_OUTPUT chỉ phù hợp cho minh họa hoặc debug trong công cụ hỗ trợ.

## 7. Thứ tự lấy thông tin trong WHEN OTHERS

Khi exception phát sinh, nên lấy thông tin ngay đầu handler:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        -- Sau đó mới gọi logger hoặc thực hiện xử lý bổ sung.
        RAISE;
~~~

Lý do:
- Đây là thời điểm exception context còn rõ ràng.
- Logger hoặc thủ tục phụ có thể phát sinh lỗi khác.
- Nếu lỗi mới thay thế lỗi cũ, thông tin gốc đã được lưu trong biến.
- Có thể truyền dữ liệu chẩn đoán sang logger mà không phải gọi lại SQLCODE/SQLERRM ở một context khác.

### 7.1. Không để logger che lỗi gốc

Giả sử exception handler gọi một procedure ghi log nhưng procedure đó cũng phát sinh lỗi. Nếu lỗi logging thoát ra ngoài, caller có thể chỉ nhìn thấy lỗi logger thay vì lỗi nghiệp vụ ban đầu.

Có thể cô lập lỗi logger:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        BEGIN
            error_log_api.write_error(
                p_code      => l_code,
                p_message   => l_message,
                p_stack     => l_stack,
                p_backtrace => l_backtrace
            );
        EXCEPTION
            WHEN OTHERS THEN
                NULL; -- Logger thất bại; không thay thế lỗi gốc.
        END;

        RAISE;
~~~

Đây là mẫu minh họa. Trong production, việc bỏ qua lỗi logger phải là quyết định có chủ đích: cần có kênh giám sát khác để không âm thầm mất toàn bộ log. Sau khi ghi log hoặc xử lý logger thất bại, RAISE không tham số giữ exception gốc của handler bên ngoài.

### 7.2. Không ghi log rồi nuốt lỗi

Mẫu nguy hiểm:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        -- Không RAISE, không trả trạng thái thất bại.
END;
~~~

Caller có thể tưởng thao tác thành công dù dữ liệu chỉ được cập nhật một phần hoặc không được cập nhật. Nếu muốn xử lý lỗi và tiếp tục, hãy định nghĩa rõ kết quả, trạng thái và ranh giới transaction.

## 8. RAISE và RAISE_APPLICATION_ERROR

Hai lệnh này có vai trò khác nhau.

### 8.1. RAISE không tham số

Trong exception handler:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Ghi thông tin.
        RAISE;
~~~

RAISE không tham số ném lại exception hiện tại. Đây là lựa chọn phù hợp khi chỉ muốn ghi log hoặc cleanup rồi để caller xử lý lỗi gốc.

### 8.2. RAISE exception có tên

Có thể chủ động phát sinh exception đã khai báo:

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
BEGIN
    RAISE e_invalid_amount;
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

Exception do người dùng khai báo có thể không có mã Oracle riêng. Nếu cần mã ứng dụng cụ thể, dùng RAISE_APPLICATION_ERROR hoặc EXCEPTION_INIT.

### 8.3. RAISE_APPLICATION_ERROR

Cú pháp:

~~~sql
RAISE_APPLICATION_ERROR(
    error_code,
    message,
    keep_errors
);
~~~

- error_code phải nằm trong khoảng -20000 đến -20999.
- message là thông điệp ứng dụng.
- keep_errors tùy chọn, mặc định FALSE. TRUE thêm lỗi mới vào error stack hiện có; FALSE thay thế stack hiện có theo hành vi của lệnh.

Ví dụ:

~~~sql
IF p_amount <= 0 THEN
    RAISE_APPLICATION_ERROR(
        -20041,
        'Amount must be greater than zero'
    );
END IF;
~~~

Dùng mã lỗi riêng giúp caller phân biệt lỗi nghiệp vụ với lỗi Oracle hệ thống.

### 8.4. Bọc lỗi gốc bằng mã nghiệp vụ

~~~sql
BEGIN
    perform_payment;
EXCEPTION
    WHEN OTHERS THEN
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        -- Có thể log l_stack và l_backtrace trước khi bọc lỗi.
        RAISE_APPLICATION_ERROR(
            -20050,
            'Payment processing failed',
            TRUE
        );
END;
~~~

Khi dùng TRUE, lỗi ứng dụng được thêm vào stack thay vì bỏ mất các lỗi trước đó. Caller có thể nhận thông báo nghiệp vụ, trong khi error stack vẫn giữ thông tin lỗi được thêm trước đó. Hãy kiểm tra stack thực tế trong phiên bản Oracle và client đang dùng.

Nếu chỉ cần truyền nguyên exception gốc lên trên, dùng RAISE không tham số thay vì tạo một lỗi mới.

## 9. Exception trong trigger

Trigger là PL/SQL subprogram được Oracle tự động gọi khi sự kiện tương ứng xảy ra. Trigger có thể phát sinh exception trong các tình huống:
- Kiểm tra điều kiện nghiệp vụ không hợp lệ.
- Vi phạm constraint hoặc lỗi DML bên trong trigger.
- Procedure/function mà trigger gọi phát sinh lỗi.
- Lỗi chuyển đổi dữ liệu hoặc lỗi runtime khác.

Ví dụ BEFORE INSERT trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_validate_amount
BEFORE INSERT OR UPDATE OF amount ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20041,
            'Order amount cannot be negative'
        );
    END IF;
END;
/
~~~

Nếu ứng dụng INSERT một đơn có AMOUNT âm, trigger phát sinh lỗi và câu lệnh DML thất bại.

### 9.1. Bắt lỗi ở tầng gọi DML

~~~sql
BEGIN
    INSERT INTO orders(order_id, amount)
    VALUES (9001, -100);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
/
~~~

Backtrace có thể chỉ ra dòng RAISE_APPLICATION_ERROR trong trigger và các vị trí PL/SQL liên quan. Lỗi trả về client vẫn là lỗi của câu INSERT đã kích hoạt trigger.

### 9.2. Exception phát sinh từ procedure mà trigger gọi

Ví dụ trigger gọi procedure:

~~~sql
CREATE OR REPLACE PROCEDURE validate_order_amount (
    p_amount IN NUMBER
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20042,
            'Invalid amount from validation procedure'
        );
    END IF;
END;
/
~~~

Trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_validate_amount
BEFORE INSERT OR UPDATE OF amount ON orders
FOR EACH ROW
BEGIN
    validate_order_amount(:NEW.amount);
END;
/
~~~

Khi procedure phát sinh lỗi, exception truyền qua trigger về câu DML. FORMAT_ERROR_BACKTRACE giúp lần theo vị trí trong procedure và trigger.

### 9.3. Trigger có thể xử lý exception nội bộ

Trigger có thể bắt một exception cụ thể nếu có phương án xử lý hợp lệ. Tuy nhiên, nếu lỗi vi phạm quy tắc nghiệp vụ mà câu DML không được phép tiếp tục, trigger cần ném lỗi lên caller.

Không viết WHEN OTHERS rồi bỏ qua exception trong trigger chỉ để câu INSERT/UPDATE thành công. Điều đó có thể khiến dữ liệu không thỏa quy tắc được ghi vào bảng.

### 9.4. Không COMMIT hoặc ROLLBACK trong trigger thông thường

Trigger thông thường chạy trong transaction của câu DML kích hoạt nó. Không COMMIT hoặc ROLLBACK transaction bên trong trigger thông thường; Oracle không cho phép kết thúc transaction của caller từ trigger theo cách đó.

Nếu cần ghi audit độc lập ngay cả khi DML thất bại, có thể cân nhắc autonomous transaction cho logger riêng. Đây là quyết định đặc biệt cần thiết kế cẩn thận vì log độc lập sẽ tồn tại ngay cả khi câu DML cha rollback. Không dùng autonomous transaction để ghi thay đổi nghiệp vụ chính.

### 9.5. Statement rollback và transaction rollback

Nếu trigger phát sinh lỗi, câu DML kích hoạt trigger thất bại và các thay đổi thuộc câu lệnh đó được rollback theo statement atomicity. Điều này không tự động có nghĩa toàn bộ transaction trước đó bị rollback.

Ví dụ:
1. UPDATE A thành công nhưng chưa COMMIT.
2. INSERT B kích hoạt trigger và thất bại.
3. INSERT B cùng các thay đổi thuộc statement đó bị rollback.
4. UPDATE A trước đó vẫn có thể còn trong transaction.
5. Caller quyết định tiếp tục hay ROLLBACK toàn transaction.

Ứng dụng phải xử lý lỗi và transaction boundary rõ ràng; không giả định lỗi trigger tự động hủy mọi DML trước đó.

## 10. Ghi log lỗi có cấu trúc

Một logger hữu ích nên lưu ít nhất:
- Thời điểm ghi log.
- Mã lỗi.
- Message.
- Error stack.
- Backtrace.
- Tên module/procedure hoặc correlation ID nếu có.
- Context nghiệp vụ không nhạy cảm, ví dụ order ID.
- Session/application identifier phù hợp.

Ví dụ một bảng log:

~~~sql
CREATE TABLE application_error_log (
    log_id       NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    logged_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    error_code   NUMBER,
    error_message VARCHAR2(4000),
    error_stack  CLOB,
    error_backtrace CLOB,
    module_name  VARCHAR2(128),
    reference_id VARCHAR2(100)
);
~~~

Thủ tục ghi log có thể nhận dữ liệu đã được capture:

~~~sql
CREATE OR REPLACE PROCEDURE write_application_error (
    p_error_code      IN NUMBER,
    p_error_message   IN VARCHAR2,
    p_error_stack     IN VARCHAR2,
    p_error_backtrace IN VARCHAR2,
    p_reference_id    IN VARCHAR2
) AS
BEGIN
    INSERT INTO application_error_log (
        error_code,
        error_message,
        error_stack,
        error_backtrace,
        reference_id
    )
    VALUES (
        p_error_code,
        p_error_message,
        p_error_stack,
        p_error_backtrace,
        p_reference_id
    );
END;
/
~~~

Ví dụ gọi trong handler:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        write_application_error(
            l_code,
            l_message,
            l_stack,
            l_backtrace,
            p_order_id
        );

        RAISE;
~~~

Đoạn code minh họa luồng capture. Vì INSERT log thuộc transaction hiện tại, nếu caller ROLLBACK thì log cũng có thể rollback. Nếu yêu cầu log phải tồn tại độc lập với transaction nghiệp vụ, cần thiết kế logger autonomous transaction hoặc gửi log tới hệ thống logging bên ngoài.

### 10.1. Logging trong cùng transaction

Ưu điểm:
- Log và dữ liệu nghiệp vụ cùng COMMIT/ROLLBACK.
- Không có log "thành công" nếu transaction cha rollback.
- Không cần autonomous transaction.

Giới hạn:
- Khi transaction rollback, log trong cùng transaction cũng biến mất.
- Không phù hợp nếu mục tiêu là lưu lại mọi thất bại dù caller rollback.

### 10.2. Logging bằng autonomous transaction

Một logger độc lập có thể khai báo:

~~~sql
CREATE OR REPLACE PROCEDURE write_error_independent (
    p_error_code IN NUMBER,
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_error_log (
        error_code,
        error_message
    )
    VALUES (
        p_error_code,
        p_message
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Autonomous transaction có transaction boundary riêng. COMMIT trong logger không commit transaction cha.

Cần lưu ý:
- Logger độc lập có thể ghi lại lỗi dù transaction cha rollback.
- Không truy cập hoặc chờ tài nguyên đang bị transaction cha khóa theo cách gây deadlock.
- Logger phải ngắn và đáng tin cậy.
- Nếu logger lỗi, cần quyết định có để lỗi logging thay thế lỗi gốc hay không.
- Không dùng autonomous transaction cho DML nghiệp vụ cần rollback cùng câu lệnh cha.

## 11. Nested exception và giữ nguyên thông tin lỗi

Một exception có thể được bắt ở nhiều tầng. Nếu mỗi tầng đều xử lý và ném một exception mới, error stack/backtrace có thể thay đổi.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE step_three AS
BEGIN
    RAISE_APPLICATION_ERROR(-20061, 'Failure in step three');
END;
/

CREATE OR REPLACE PROCEDURE step_two AS
BEGIN
    step_three;
EXCEPTION
    WHEN OTHERS THEN
        -- Ghi log tại tầng trung gian.
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
/

CREATE OR REPLACE PROCEDURE step_one AS
BEGIN
    step_two;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
/
~~~

STEP_THREE phát sinh lỗi. STEP_TWO bắt và RAISE lại. STEP_ONE bắt tiếp, lấy thông tin và RAISE lại. Caller cuối cùng vẫn nhận exception.

### 11.1. RAISE giữ exception hiện tại

Trong handler:

~~~sql
RAISE;
~~~

nên dùng khi muốn chuyển exception hiện tại lên tầng trên mà không thay đổi loại lỗi.

### 11.2. RAISE một exception khác thay đổi lỗi đang truyền

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE e_application_failure;
~~~

Câu lệnh này phát sinh exception E_APPLICATION_FAILURE tại vị trí RAISE. Nếu mục tiêu là giữ nguyên lỗi gốc, không thay bằng một exception khác. Hãy lưu diagnostics trước khi chuyển đổi và dùng RAISE_APPLICATION_ERROR có keep_errors phù hợp khi cần thêm ngữ cảnh.

### 11.3. Backtrace cần được capture trước khi bọc lỗi

Nếu handler gọi RAISE_APPLICATION_ERROR để tạo mã mới, backtrace về sau có thể phản ánh vị trí raise mới. Vì vậy, nếu cần vị trí lỗi gốc, capture FORMAT_ERROR_BACKTRACE trước khi bọc.

## 12. FORMAT_ERROR_STACK và FORMAT_ERROR_BACKTRACE trong package

Một package có thể cung cấp helper dùng chung để lấy diagnostics:

~~~sql
CREATE OR REPLACE PACKAGE error_diagnostics AS
    PROCEDURE print_current_error;
END error_diagnostics;
/
~~~

Body:

~~~sql
CREATE OR REPLACE PACKAGE BODY error_diagnostics AS
    PROCEDURE print_current_error IS
        l_code      NUMBER;
        l_message   VARCHAR2(4000);
        l_stack     VARCHAR2(32767);
        l_backtrace VARCHAR2(32767);
    BEGIN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        DBMS_OUTPUT.PUT_LINE('Code=' || l_code);
        DBMS_OUTPUT.PUT_LINE('Message=' || l_message);
        DBMS_OUTPUT.PUT_LINE('Stack=' || l_stack);
        DBMS_OUTPUT.PUT_LINE('Backtrace=' || l_backtrace);
    END print_current_error;
END error_diagnostics;
/
~~~

Gọi helper bên trong exception handler:

~~~sql
BEGIN
    -- Công việc.
    RAISE ZERO_DIVIDE;
EXCEPTION
    WHEN OTHERS THEN
        error_diagnostics.print_current_error;
        RAISE;
END;
/
~~~

Helper được gọi trong khi exception đang được xử lý. Trong ứng dụng production, nên truyền các giá trị đã capture vào logger để tránh phụ thuộc vào trạng thái exception context trong các tầng gọi lồng nhau.

## 13. SQLCODE/SQLERRM và exception mapping

Oracle định nghĩa một số predefined exceptions, ví dụ:
- NO_DATA_FOUND.
- TOO_MANY_ROWS.
- ZERO_DIVIDE.
- DUP_VAL_ON_INDEX.
- INVALID_NUMBER.
- VALUE_ERROR.
- OTHERS là handler tổng quát, không phải exception cụ thể.

Có thể bắt exception theo tên:

~~~sql
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        ...
    WHEN DUP_VAL_ON_INDEX THEN
        ...
    WHEN OTHERS THEN
        ...
~~~

Đối với mã lỗi Oracle chưa có predefined exception phù hợp, khai báo exception và ánh xạ bằng PRAGMA EXCEPTION_INIT:

~~~sql
DECLARE
    e_parent_missing EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_parent_missing, -2291);
BEGIN
    -- DML có thể vi phạm foreign key.
    NULL;
EXCEPTION
    WHEN e_parent_missing THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

Không ánh xạ một exception tùy ý vào mã không phù hợp. Mã phải phản ánh lỗi Oracle mà handler muốn bắt.

### 13.1. SQLCODE và SQLERRM trong OTHERS

Trong WHEN OTHERS, hai hàm lấy thông tin exception hiện tại:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_code := SQLCODE;
        l_message := SQLERRM;
        RAISE;
~~~

Không cần kiểm tra SQLCODE trước khi gọi SQLERRM. Capture cả hai ngay đầu handler thường là cách rõ ràng.

### 13.2. SQLERRM với lỗi user-defined

Với exception do RAISE e_name và không được ánh xạ mã, SQLERRM thường chỉ trả "User-Defined Exception". Nếu cần message cụ thể, hãy dùng RAISE_APPLICATION_ERROR hoặc tự lưu mã/message nghiệp vụ trong biến/context.

## 14. Error stack, backtrace và call stack: ví dụ phân biệt

Giả sử luồng gọi:

~~~text
CLIENT
  |
  v
PROCEDURE PROCESS_ORDER
  |
  v
PACKAGE VALIDATION_PKG.CHECK_ORDER
  |
  v
TRIGGER TRG_ORDER_VALIDATE
  |
  v
FUNCTION CHECK_LIMIT
  |
  v
ORA-20071 được phát sinh
~~~

Nếu lỗi truyền ngược lên PROCESS_ORDER:

- SQLCODE: mã số của exception đang được bắt, ví dụ -20071.
- SQLERRM: thông điệp của exception hiện tại.
- FORMAT_ERROR_STACK: các thông báo lỗi đang có trong stack.
- FORMAT_ERROR_BACKTRACE: các vị trí PL/SQL từ nơi exception được phát sinh tới handler.
- FORMAT_CALL_STACK: các subprogram đang hoạt động tại thời điểm hàm được gọi; có thể không giống backtrace.

### 14.1. Không nhầm error stack với backtrace

Error stack trả lời: **Oracle đang báo những lỗi nào?**

Backtrace trả lời: **Lỗi bắt đầu ở dòng nào?**

Call stack trả lời: **Code hiện đang được gọi qua những tầng nào?**

Khi điều tra lỗi phức tạp, ghi cả error stack và backtrace. Nếu cần hiểu context thực thi hiện tại, có thể ghi thêm FORMAT_CALL_STACK.

## 15. Những lưu ý khi ghi log trong trigger

Trigger chạy trong ngữ cảnh câu DML của caller. Logging trong trigger cần được thiết kế cẩn thận.

### 15.1. DBMS_OUTPUT không phải hệ thống logging production

DBMS_OUTPUT:
- Không tự ghi vào bảng log.
- Có thể không được client bật hoặc đọc.
- Không phải kênh giám sát tin cậy cho ứng dụng chạy nền.
- Không nên là cách duy nhất lưu lỗi production.

Dùng logging API hoặc cơ chế giám sát phù hợp với hệ thống.

### 15.2. Trigger không nên che lỗi

Nếu trigger phát hiện dữ liệu không hợp lệ, có thể phát sinh mã ứng dụng:

~~~sql
RAISE_APPLICATION_ERROR(
    -20071,
    'Order state transition is not allowed'
);
~~~

Không bắt OTHERS rồi tiếp tục ghi dữ liệu nếu điều kiện đó phải được bảo đảm.

### 15.3. Tránh side effect không thể rollback

Nếu trigger gửi email hoặc gọi HTTP rồi sau đó câu DML thất bại, side effect bên ngoài không được Oracle rollback. Một thiết kế an toàn hơn là ghi sự kiện vào outbox trong cùng transaction; worker chỉ gửi sau khi transaction COMMIT.

### 15.4. Autonomous logging có thể tồn tại sau rollback

Logger autonomous có thể lưu lỗi dù DML cha thất bại. Tuy nhiên, log cần ghi rõ rằng transaction nghiệp vụ không thành công hoặc chưa commit. Đừng ghi một bản ghi log như thể thay đổi dữ liệu đã được xác nhận.

## 16. Ví dụ thực hành tổng hợp: lỗi từ trigger và backtrace

Tạo bảng sandbox:

~~~sql
CREATE TABLE error_demo_orders (
    order_id NUMBER PRIMARY KEY,
    amount   NUMBER NOT NULL
);
~~~

Tạo procedure kiểm tra:

~~~sql
CREATE OR REPLACE PROCEDURE validate_demo_amount (
    p_amount IN NUMBER
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20081,
            'Amount must not be negative'
        );
    END IF;
END;
/
~~~

Tạo trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_error_demo_orders
BEFORE INSERT OR UPDATE OF amount
ON error_demo_orders
FOR EACH ROW
BEGIN
    validate_demo_amount(:NEW.amount);
END;
/
~~~

Thử một DML hợp lệ:

~~~sql
INSERT INTO error_demo_orders(order_id, amount)
VALUES (1, 100);

COMMIT;
~~~

Thử DML không hợp lệ:

~~~sql
DECLARE
    l_code      NUMBER;
    l_message   VARCHAR2(4000);
    l_stack     VARCHAR2(32767);
    l_backtrace VARCHAR2(32767);
BEGIN
    INSERT INTO error_demo_orders(order_id, amount)
    VALUES (2, -50);

EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || l_code);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || l_message);
        DBMS_OUTPUT.PUT_LINE('STACK=' || l_stack);
        DBMS_OUTPUT.PUT_LINE('BACKTRACE=' || l_backtrace);

        RAISE;
END;
/
~~~

Kết quả dự kiến:
- SQLCODE là -20081.
- SQLERRM chứa thông báo Amount must not be negative.
- Error stack chứa lỗi ứng dụng và thông tin Oracle liên quan.
- Backtrace giúp tìm dòng phát sinh trong procedure hoặc trigger.

Câu INSERT thứ hai thất bại. Hàng ORDER_ID=2 không được thêm. Hàng ORDER_ID=1 đã COMMIT trước đó vẫn tồn tại.

### 16.1. Kiểm tra dữ liệu

~~~sql
SELECT *
FROM error_demo_orders
ORDER BY order_id;
~~~

Chỉ hàng 1 được trả về.

### 16.2. Dọn sandbox

~~~sql
DROP TRIGGER trg_error_demo_orders;
DROP PROCEDURE validate_demo_amount;
DROP TABLE error_demo_orders PURGE;
~~~

Chỉ xóa các đối tượng sandbox do bài học tạo khi chắc chắn không cần dữ liệu. DROP là DDL và có quy tắc implicit commit; thực hiện cleanup riêng.

## 17. Quy trình xử lý exception trong procedure/package/trigger

Một quy trình thực tế có thể gồm:

1. Bắt exception cụ thể nếu có cách xử lý rõ ràng.
2. Với lỗi không dự kiến, dùng WHEN OTHERS ở ranh giới phù hợp.
3. Ngay đầu handler, capture SQLCODE và SQLERRM.
4. Capture FORMAT_ERROR_STACK để giữ chuỗi lỗi.
5. Capture FORMAT_ERROR_BACKTRACE để giữ vị trí phát sinh.
6. Ghi log cùng correlation ID và ngữ cảnh nghiệp vụ cần thiết.
7. Nếu logger có thể lỗi, bảo vệ lỗi gốc theo chính sách logging.
8. Dùng RAISE để truyền lại exception gốc nếu không xử lý được.
9. Chỉ dùng RAISE_APPLICATION_ERROR khi cần chuyển sang mã lỗi ứng dụng hoặc bổ sung thông điệp nghiệp vụ.
10. Không COMMIT/ROLLBACK trong trigger thông thường.
11. Xác định rõ statement rollback và transaction rollback.
12. Để caller hoặc transaction manager quyết định COMMIT/ROLLBACK theo đơn vị nghiệp vụ.

## 18. Những nhầm lẫn thường gặp

**SQLCODE luôn trả mã lỗi gần nhất của session.** Không đúng. Ngoài exception context, SQLCODE trả 0; trong handler, nó mô tả exception đang được xử lý.

**SQLERRM là toàn bộ error stack.** Không đúng. Nó trả message của exception hiện tại hoặc mã được chỉ định; dùng FORMAT_ERROR_STACK để lấy stack.

**FORMAT_ERROR_STACK cho biết chính xác dòng code gây lỗi.** Không phải mục tiêu chính. Dùng FORMAT_ERROR_BACKTRACE để lấy vị trí exception được phát sinh.

**FORMAT_ERROR_BACKTRACE giống FORMAT_CALL_STACK.** Không đúng. Backtrace mô tả đường truyền của exception; call stack mô tả các lời gọi đang hoạt động tại thời điểm gọi.

**Bắt OTHERS là đã xử lý lỗi.** Chỉ đúng nếu handler thực sự phục hồi và biểu diễn kết quả thất bại/thành công chính xác. Nếu không, RAISE lại.

**RAISE; và RAISE e_name; có cùng tác dụng.** Không đúng. RAISE không tham số ném lại exception hiện tại; RAISE tên exception phát sinh exception được chỉ định.

**SQLERRM nên được so chuỗi để phân loại lỗi.** Không nên. Dùng SQLCODE hoặc named exception; message có thể phụ thuộc NLS.

**NULL luôn chọn một overload cụ thể.** Không đúng. Untyped NULL có thể làm lời gọi overload mơ hồ; dùng CAST hoặc biến typed.

**RAISE_APPLICATION_ERROR luôn giữ lỗi cũ.** Không đúng. Tham số thứ ba quyết định cách stack hiện có được xử lý; TRUE thêm lỗi vào stack, FALSE thay thế stack hiện có.

**Ghi DBMS_OUTPUT là đủ cho production.** Không đúng. DBMS_OUTPUT phụ thuộc client và không phải hệ thống logging bền vững.

**Trigger bắt OTHERS rồi bỏ qua lỗi là an toàn.** Không đúng nếu lỗi thể hiện vi phạm nghiệp vụ; dữ liệu có thể được ghi trong trạng thái sai.

**Trigger có thể COMMIT để giữ log.** Không đúng với trigger thông thường. Nếu cần log độc lập, dùng một thiết kế autonomous logger có chủ đích.

**Trigger thất bại luôn rollback toàn bộ transaction.** Không đúng. Câu DML gây lỗi được rollback theo statement atomicity; các statement trước trong transaction có thể vẫn còn.

**ROLLBACK của caller luôn xóa log autonomous.** Không đúng. Autonomous transaction đã COMMIT độc lập nên log vẫn tồn tại.

**Backtrace gọi sau khi rời handler vẫn khôi phục lỗi cũ.** Không nên giả định điều đó. Capture backtrace ngay trong handler.

## 19. Bài tập tự luyện

1. Tạo anonymous block chia 10 cho 0 và in SQLCODE.
2. In SQLERRM trong WHEN OTHERS và giải thích message.
3. Gọi SQLCODE ngoài exception handler. Kết quả là gì?
4. Gọi SQLERRM ngoài exception handler. Vì sao message không mô tả lỗi trước đó?
5. Tạo một user-defined exception và quan sát SQLCODE/SQLERRM.
6. Dùng PRAGMA EXCEPTION_INIT ánh xạ exception tới -20041.
7. Tạo lỗi ORA-00001 và bắt bằng DUP_VAL_ON_INDEX.
8. So sánh SQLERRM với DBMS_UTILITY.FORMAT_ERROR_STACK.
9. Tạo procedure con phát sinh lỗi và procedure cha bắt lỗi.
10. In FORMAT_ERROR_BACKTRACE tại procedure cha. Nó chỉ ra vị trí nào?
11. So sánh FORMAT_ERROR_BACKTRACE và FORMAT_CALL_STACK.
12. Tạo hai tầng procedure và dùng RAISE để truyền nguyên exception.
13. Thay RAISE bằng RAISE e_name. Quan sát khác biệt.
14. Dùng RAISE_APPLICATION_ERROR với mã -20050.
15. Thử tham số thứ ba TRUE và FALSE khi stack đã có lỗi.
16. Vì sao nên capture backtrace trước khi bọc exception?
17. Tạo bảng log chứa error code, message, stack và backtrace.
18. Viết procedure logger nhận diagnostics qua named parameters.
19. Gọi logger trong WHEN OTHERS rồi RAISE lại.
20. Tạo lỗi bên trong logger và xem cách bảo vệ exception gốc.
21. Tạo trigger BEFORE INSERT từ chối amount âm bằng RAISE_APPLICATION_ERROR.
22. Bắt lỗi DML từ trigger ở anonymous block và in bốn thông tin chẩn đoán.
23. Tạo trigger gọi procedure kiểm tra rồi phát sinh lỗi ở procedure. Backtrace hiển thị những tầng nào?
24. Giải thích vì sao không COMMIT/ROLLBACK trong trigger thông thường.
25. Một INSERT thất bại trong trigger. Các DML thành công trước đó trong transaction có bị rollback không?
26. So sánh logging cùng transaction với autonomous transaction.
27. Vì sao autonomous logger có thể ghi log dù DML cha rollback?
28. Thiết kế cách ghi correlation ID để liên kết lỗi giữa application, package và trigger.
29. Khi nào nên bắt exception cụ thể thay vì chỉ dùng OTHERS?
30. Thiết kế một handler production vừa giữ lỗi gốc, vừa lưu error stack/backtrace và trả mã lỗi nghiệp vụ phù hợp.

**SQLCODE cho biết mã exception, SQLERRM cho biết thông điệp, FORMAT_ERROR_STACK giữ chuỗi lỗi và FORMAT_ERROR_BACKTRACE chỉ ra nơi exception được phát sinh.** Hãy capture các giá trị này ngay trong handler, ghi log theo một cấu trúc nhất quán và dùng RAISE khi cần truyền nguyên lỗi lên caller. Với trigger, cần nhớ lỗi làm thất bại câu DML kích hoạt trigger; transaction tổng thể vẫn do caller quản lý.
