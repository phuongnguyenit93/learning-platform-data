# SIGNAL, RESIGNAL và bảo toàn thông tin lỗi

Stored program cần một hợp đồng lỗi rõ ràng để ứng dụng biết thao tác nào thất bại, vì sao thất bại và có thể xử lý tiếp hay phải dừng. MySQL cung cấp SIGNAL để chủ động phát sinh condition, RESIGNAL để chuyển tiếp condition đang được handler xử lý, và GET DIAGNOSTICS để đọc thông tin chẩn đoán như SQLSTATE, mã lỗi và thông điệp.

SIGNAL thường được dùng để từ chối dữ liệu không hợp lệ hoặc báo lỗi nghiệp vụ. RESIGNAL giúp handler thực hiện cleanup, thu thập thông tin hoặc bổ sung ngữ cảnh rồi vẫn trả lỗi gốc cho caller. GET STACKED DIAGNOSTICS đặc biệt quan trọng trong handler: nó đọc condition đã kích hoạt handler ngay cả khi các câu lệnh trong handler đã thay đổi diagnostics area hiện tại.

Một lỗi phổ biến là bắt SQLEXCEPTION rồi chỉ ghi log hoặc trả một thông điệp chung, khiến SQLSTATE và mã lỗi ban đầu bị mất. Một lỗi khác là dùng GET DIAGNOSTICS CONDITION 1 với giả định condition đầu tiên luôn là lỗi chính; MySQL không bảo đảm điều đó. Bài học này hướng dẫn cách thiết kế SQLSTATE, phát lỗi, chọn handler, lấy đúng diagnostics và bảo toàn lỗi qua nhiều tầng stored program.

Các ví dụ tập trung vào câu lệnh SQL phía server. Khi tạo routine bằng mysql command-line client, hãy dùng DELIMITER để client không kết thúc câu CREATE tại dấu chấm phẩy đầu tiên. DELIMITER là lệnh của client, không phải câu SQL gửi đến server.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt condition, warning, not found và exception.
- Giải thích cấu trúc SQLSTATE và lựa chọn SQLSTATE phù hợp.
- Phát lỗi có chủ đích bằng SIGNAL.
- Định nghĩa condition có tên bằng DECLARE ... CONDITION.
- Chọn handler CONTINUE hoặc EXIT theo luồng điều khiển.
- Hiểu thứ tự ưu tiên và phạm vi của condition handler.
- Dùng GET DIAGNOSTICS và GET STACKED DIAGNOSTICS.
- Lấy đúng condition chính khi diagnostics area chứa nhiều condition.
- Dùng RESIGNAL để chuyển tiếp lỗi gốc mà không làm mất SQLSTATE và MYSQL_ERRNO.
- Chỉ thay MESSAGE_TEXT hoặc chủ động chuyển lỗi sang mã nghiệp vụ mới.
- Phân biệt lỗi cursor NOT FOUND với lỗi SQL thông thường.
- Thiết kế handler có cleanup và transaction ownership rõ ràng.
- Kiểm thử lỗi bằng CALL, SHOW WARNINGS, SHOW ERRORS và ứng dụng.

## 1. Condition và error trong MySQL

Trong stored program, condition là thông tin được server tạo ra khi một statement phát sinh trạng thái cần chú ý. Condition có thể là:

- Thành công (success).
- Cảnh báo (warning).
- Không tìm thấy dữ liệu (not found).
- Lỗi/ngoại lệ (exception).

Một condition thường có các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| SQLSTATE | Mã trạng thái gồm 5 ký tự, theo chuẩn SQL/ODBC |
| MYSQL_ERRNO | Mã lỗi số riêng của MySQL |
| MESSAGE_TEXT | Thông điệp mô tả condition |
| Các diagnostics item khác | Thông tin constraint, schema, table, column hoặc cursor nếu có |

SQLSTATE có tính chuẩn hóa và thường phù hợp để ứng dụng phân loại lỗi ở mức tổng quát. MYSQL_ERRNO là mã riêng của MySQL, hữu ích khi cần nhận diện một lỗi cụ thể trong cùng hệ sinh thái MySQL. MESSAGE_TEXT dành cho chẩn đoán; ứng dụng không nên phân tích chuỗi thông điệp để quyết định logic nghiệp vụ vì nội dung có thể thay đổi theo phiên bản, ngôn ngữ hoặc ngữ cảnh.

### 1.1. Các lớp SQLSTATE thường gặp

SQLSTATE gồm 5 ký tự. Hai ký tự đầu xác định lớp condition:

| Lớp | Ý nghĩa | Cách MySQL xử lý tổng quát |
|---|---|---|
| 00 | Success | Không được dùng để SIGNAL lỗi |
| 01 | Warning | Phát warning; SQLWARNING handler có thể bắt |
| 02 | Not found | NOT FOUND handler có thể bắt |
| Khác 00, 01, 02 | Exception | SQLEXCEPTION handler có thể bắt |

Một số ví dụ:

- 02000: không tìm thấy dữ liệu.
- 23000: vi phạm integrity constraint, thường gặp với duplicate key hoặc foreign key.
- 22012: chia cho 0.
- 45000: exception do người dùng định nghĩa, thường dùng cho lỗi nghiệp vụ tổng quát.

Với lỗi nghiệp vụ do ứng dụng chủ động phát ra, SQLSTATE 45000 là lựa chọn tổng quát thường dùng. Không dùng lớp 00 để báo lỗi. Không dùng lớp 02 cho lỗi validation vì nó sẽ được xử lý như NOT FOUND, có thể vô tình kích hoạt handler kết thúc cursor loop.

### 1.2. SQLSTATE và MYSQL_ERRNO không thay thế nhau

Ví dụ một lỗi validation có thể dùng:

    SIGNAL SQLSTATE '45000'
        SET MYSQL_ERRNO = 30001,
            MESSAGE_TEXT = 'amount must be positive';

Ở đây:

- SQLSTATE 45000 xác định đây là exception do stored program phát ra.
- MYSQL_ERRNO 30001 là mã số ứng dụng chọn để nhận diện trường hợp cụ thể.
- MESSAGE_TEXT giúp người vận hành hiểu nguyên nhân.

Hãy quản lý dải mã tùy chỉnh trong tài liệu dự án để tránh trùng với quy ước nội bộ hoặc mã lỗi MySQL mà ứng dụng đang sử dụng. MYSQL_ERRNO là số nguyên không dấu 16-bit; MESSAGE_TEXT có giới hạn 128 ký tự.

## 2. SIGNAL: chủ động phát sinh condition

SIGNAL dùng để phát một condition mới. Cú pháp tổng quát:

    SIGNAL condition_value
        [SET signal_information_item = value [, ...]];

condition_value có thể là:

- SQLSTATE [VALUE] 'xxxxx'.
- Tên condition đã khai báo bằng DECLARE ... CONDITION và được định nghĩa bằng SQLSTATE.

Các signal information item thường dùng:

| Item | Mục đích |
|---|---|
| SQLSTATE | Được chỉ định trong condition_value |
| MYSQL_ERRNO | Mã lỗi số MySQL |
| MESSAGE_TEXT | Thông điệp lỗi |
| CONSTRAINT_SCHEMA / CONSTRAINT_NAME | Ngữ cảnh constraint |
| SCHEMA_NAME / TABLE_NAME / COLUMN_NAME | Ngữ cảnh đối tượng |
| CURSOR_NAME | Tên cursor liên quan nếu có |

Không thể gán NULL cho signal information item. Mỗi item chỉ được xuất hiện một lần trong SET. RETURNED_SQLSTATE được xác định bởi condition_value, không gán trực tiếp trong SET.

### 2.1. Phát lỗi validation

Ví dụ procedure từ chối số tiền không hợp lệ:

    CREATE PROCEDURE validate_payment(
        IN p_amount DECIMAL(12,2)
    )
    BEGIN
        IF p_amount IS NULL OR p_amount <= 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MYSQL_ERRNO = 30001,
                    MESSAGE_TEXT = 'amount must be greater than zero';
        END IF;

        SELECT 'payment amount accepted' AS result;
    END;

Nếu p_amount không hợp lệ, SIGNAL phát exception và statement CALL kết thúc tại lỗi nếu không có handler phù hợp. SELECT phía sau không được thực hiện.

SIGNAL không cần quyền đặc biệt. Nó có thể được dùng trong stored procedure, function, trigger và event. MySQL cũng cho phép SIGNAL ngoài stored program như một extension.

### 2.2. Phát warning có chủ đích

SQLSTATE lớp 01 biểu thị warning:

    SIGNAL SQLSTATE '01000'
        SET MESSAGE_TEXT = 'optional field was ignored',
            MYSQL_ERRNO = 30010;

Warning không tự động kết thúc stored program. SQLWARNING handler có thể bắt condition này. Ứng dụng có thể xem warning qua SHOW WARNINGS hoặc API diagnostics phù hợp.

Không dùng warning để thay cho exception khi thao tác bắt buộc phải dừng. Ngược lại, không phát exception cho tình huống chỉ cần cảnh báo và tiếp tục.

### 2.3. SIGNAL lớp 02 và NOT FOUND

SQLSTATE lớp 02 biểu thị NOT FOUND:

    SIGNAL SQLSTATE '02000'
        SET MESSAGE_TEXT = 'requested row was not found';

Condition này có thể kích hoạt handler NOT FOUND. Với cursor, NOT FOUND thường được dùng để báo FETCH đã hết hàng. SELECT ... INTO không trả hàng cũng có thể phát NOT FOUND.

Vì vậy, không dùng SQLSTATE 02000 cho validation hoặc lỗi nghiệp vụ thông thường. Nếu có handler NOT FOUND để kết thúc vòng lặp cursor, một SIGNAL 02000 ở vị trí khác có thể làm luồng điều khiển thoát loop hoặc block ngoài dự kiến.

Nếu NOT FOUND được phát trực tiếp bằng SIGNAL/RESIGNAL và không có handler phù hợp, MySQL xử lý nó như EXIT. Điều này khác với NOT FOUND phát sinh tự nhiên trong một số thao tác đọc, vốn có hành vi mặc định tiếp tục.

### 2.4. Những điều MySQL áp dụng cho SIGNAL

- SQLSTATE phải là chuỗi 5 ký tự hợp lệ.
- SQLSTATE bắt đầu bằng 00 là không hợp lệ cho SIGNAL.
- SQLSTATE 45000 là generic user-defined exception.
- SQLSTATE lớp 01 tạo warning.
- SQLSTATE lớp 02 tạo not found.
- Các lớp khác tạo exception; lớp 40 cũng được MySQL xử lý như exception thông thường.
- SIGNAL không bị bỏ qua bởi IGNORE và không phụ thuộc strict SQL mode.
- Các statement phía sau SIGNAL chỉ chạy nếu condition được xử lý bởi handler CONTINUE phù hợp.

## 3. DECLARE ... CONDITION: đặt tên cho condition

Tên condition giúp code dễ đọc và tránh lặp SQLSTATE literal.

Ví dụ:

    CREATE PROCEDURE create_invoice(
        IN p_total DECIMAL(12,2)
    )
    BEGIN
        DECLARE invalid_total CONDITION
            FOR SQLSTATE '45000';

        IF p_total IS NULL OR p_total <= 0 THEN
            SIGNAL invalid_total
                SET MYSQL_ERRNO = 30021,
                    MESSAGE_TEXT = 'invoice total is invalid';
        END IF;

        SELECT 'invoice accepted' AS result;
    END;

Condition được khai báo bằng SQLSTATE có thể dùng với SIGNAL và RESIGNAL.

### 3.1. Condition gắn với mã lỗi MySQL

DECLARE ... CONDITION cũng có thể đặt tên cho MySQL error number:

    DECLARE duplicate_key CONDITION FOR 1062;

Tên này có thể dùng trong DECLARE ... HANDLER:

    DECLARE EXIT HANDLER FOR duplicate_key
    BEGIN
        -- xử lý lỗi duplicate entry
    END;

Nhưng condition name gắn với MySQL error number không thể dùng trực tiếp trong SIGNAL hoặc RESIGNAL. SIGNAL/RESIGNAL chỉ chấp nhận condition name được định nghĩa bằng SQLSTATE.

Nếu muốn phát lỗi ứng dụng có tên, hãy định nghĩa condition bằng SQLSTATE, không dùng mã MySQL:

    DECLARE invalid_state CONDITION FOR SQLSTATE '45000';

### 3.2. Phạm vi condition name

Condition name có phạm vi trong block BEGIN ... END nơi nó được khai báo và các block con nằm trong phạm vi đó. Nếu một condition name trùng tên được khai báo ở block lồng nhau, khai báo gần nhất với statement được áp dụng.

Đặt tên theo ý nghĩa nghiệp vụ:

- invalid_amount
- customer_not_found
- duplicate_order
- insufficient_balance

Tránh các tên quá chung như error1 hoặc condition_a vì khó hiểu khi đọc handler và SIGNAL.

## 4. DECLARE ... HANDLER: xử lý condition

Handler quy định hành động khi một condition xảy ra trong phạm vi block.

Cú pháp tổng quát:

    DECLARE handler_action HANDLER
    FOR condition_value [, condition_value] ...
    statement;

handler_action có thể là:

- CONTINUE: chạy handler xong thì tiếp tục sau statement phát condition.
- EXIT: chạy handler xong thì thoát block BEGIN ... END nơi handler được khai báo.

MySQL không hỗ trợ handler action UNDO.

Các condition value phổ biến:

- MySQL error code, ví dụ 1062.
- SQLSTATE 'xxxxx'.
- Tên condition đã khai báo.
- SQLWARNING.
- NOT FOUND.
- SQLEXCEPTION.

### 4.1. CONTINUE handler

CONTINUE handler xử lý condition rồi tiếp tục thực thi statement kế tiếp sau statement gây condition.

Ví dụ:

    CREATE PROCEDURE demo_continue_handler()
    BEGIN
        DECLARE v_warning_seen BOOLEAN DEFAULT FALSE;

        DECLARE CONTINUE HANDLER FOR SQLWARNING
            SET v_warning_seen = TRUE;

        SIGNAL SQLSTATE '01000'
            SET MESSAGE_TEXT = 'non-fatal warning';

        SELECT
            v_warning_seen AS warning_was_handled,
            'procedure continued' AS execution_state;
    END;

Sau khi handler chạy, SELECT tiếp tục được thực hiện. CONTINUE phù hợp với tình huống có thể phục hồi hoặc bỏ qua có chủ đích, chẳng hạn đánh dấu cursor đã hết hàng.

Không dùng CONTINUE cho mọi SQLEXCEPTION rồi tiếp tục chạy như không có gì xảy ra. Nếu statement trước đó thất bại, biến hoặc dữ liệu trung gian có thể không ở trạng thái mà các statement sau mong đợi.

### 4.2. EXIT handler

EXIT handler xử lý condition rồi thoát block mà handler được khai báo.

Ví dụ:

    CREATE PROCEDURE demo_exit_handler()
    BEGIN
        DECLARE EXIT HANDLER FOR SQLEXCEPTION
        BEGIN
            SELECT 'error handled; leaving this block' AS state;
        END;

        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'operation rejected';

        SELECT 'this statement is not reached' AS state;
    END;

Handler EXIT khai báo ở block ngoài cùng sẽ kết thúc block procedure sau khi xử lý. Nếu handler được khai báo trong một block con, EXIT thoát block con đó; code ở block cha có thể tiếp tục tùy luồng điều khiển.

### 4.3. Vị trí khai báo trong block

Trong MySQL, khai báo local variables và named conditions phải nằm trước cursor declarations; cursor declarations phải nằm trước handler declarations. Tất cả khai báo phải đứng đầu block trước các executable statements.

Thứ tự thường dùng:

    BEGIN
        DECLARE v_done BOOLEAN DEFAULT FALSE;
        DECLARE v_order_id BIGINT;
        DECLARE c_no_order CONDITION FOR SQLSTATE '02000';
        DECLARE cur_orders CURSOR FOR
            SELECT order_id FROM orders;
        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_done = TRUE;

        -- executable statements bắt đầu từ đây
    END;

Nếu khai báo handler trước cursor, MySQL có thể báo lỗi cú pháp hoặc thứ tự khai báo không hợp lệ.

## 5. Thứ tự ưu tiên khi MySQL chọn handler

Khi condition xảy ra, MySQL tìm handler trong block hiện tại. Nếu không có handler phù hợp, server tìm tiếp ở các block bao ngoài. Khi có nhiều handler phù hợp trong cùng scope, MySQL áp dụng thứ tự ưu tiên:

1. Handler cho MySQL error code cụ thể có ưu tiên cao nhất.
2. Handler cho SQLSTATE cụ thể có ưu tiên tiếp theo.
3. Handler lớp tổng quát như SQLWARNING, NOT FOUND hoặc SQLEXCEPTION có ưu tiên thấp hơn.

Trong nhóm handler tổng quát, SQLEXCEPTION có ưu tiên cao hơn SQLWARNING. Không dựa vào thứ tự khai báo để phân xử các handler cùng mức ưu tiên.

Ví dụ:

    DECLARE EXIT HANDLER FOR 1062
        SET v_duplicate = TRUE;

    DECLARE EXIT HANDLER FOR SQLSTATE '23000'
        SET v_integrity_error = TRUE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
        SET v_general_error = TRUE;

Nếu INSERT tạo lỗi 1062, handler cho mã lỗi 1062 được chọn trước handler SQLSTATE 23000 hoặc SQLEXCEPTION.

### 5.1. Scope cục bộ có ưu tiên hơn scope ngoài

Nếu một block con và block cha đều có handler phù hợp, handler ở block gần statement phát condition hơn được chọn trước. Quy tắc scope cục bộ được xét trước mức độ cụ thể giữa các handler ở scope khác nhau.

Ví dụ:

    BEGIN
        DECLARE EXIT HANDLER FOR 1062
            SET v_outer_duplicate = TRUE;

        BEGIN
            DECLARE EXIT HANDLER FOR SQLEXCEPTION
                SET v_inner_error = TRUE;

            -- lỗi 1062 xảy ra tại đây
        END;
    END;

Handler SQLEXCEPTION ở block con có thể được chọn vì nó nằm trong scope gần nhất, dù handler ở block cha chỉ rõ mã 1062.

### 5.2. Tránh nhiều handler cùng độ ưu tiên

Nếu một statement phát nhiều condition và có nhiều handler cùng mức ưu tiên phù hợp, việc chọn handler có thể không xác định. Kết quả có thể thay đổi theo circumstances của condition.

Thiết kế tốt:

- Tránh khai báo nhiều handler cùng mức ưu tiên có thể cùng khớp một statement.
- Ưu tiên một handler tổng quát và xử lý theo diagnostics khi cần.
- Tách statement vào block con nếu cần một chính sách xử lý riêng.
- Không dựa vào thứ tự viết DECLARE HANDLER để mong MySQL chọn một handler cụ thể.

## 6. GET DIAGNOSTICS: đọc thông tin lỗi

GET DIAGNOSTICS đọc diagnostics area mà MySQL tạo ra sau khi thực thi statement.

Cú pháp khái quát:

    GET [CURRENT | STACKED] DIAGNOSTICS
        statement_information_item [, ...]

    GET [CURRENT | STACKED] DIAGNOSTICS
        CONDITION condition_number
        condition_information_item [, ...];

Hai statement information item thường dùng:

- NUMBER: số condition hiện có trong diagnostics area.
- ROW_COUNT: số hàng bị ảnh hưởng theo diagnostics của statement.

Các condition information item thường dùng:

- RETURNED_SQLSTATE
- MYSQL_ERRNO
- MESSAGE_TEXT
- TABLE_NAME
- COLUMN_NAME
- SCHEMA_NAME
- CONSTRAINT_NAME
- CURSOR_NAME
- CLASS_ORIGIN
- SUBCLASS_ORIGIN

Một số item có thể rỗng hoặc không được server cung cấp cho condition cụ thể. Không xây dựng logic nghiệp vụ phụ thuộc vào TABLE_NAME hoặc COLUMN_NAME luôn có giá trị.

### 6.1. CURRENT diagnostics area

GET CURRENT DIAGNOSTICS đọc diagnostics area hiện tại. Nếu bỏ qua từ khóa CURRENT, đây là mặc định.

Ví dụ sau khi một statement lỗi trong mysql client:

    GET DIAGNOSTICS CONDITION 1
        @sqlstate = RETURNED_SQLSTATE,
        @errno = MYSQL_ERRNO,
        @message = MESSAGE_TEXT;

    SELECT @sqlstate, @errno, @message;

Trong stored program, có thể gán vào local variables:

    GET CURRENT DIAGNOSTICS
        v_condition_count = NUMBER;

### 6.2. STACKED diagnostics area

Khi handler được kích hoạt, MySQL đẩy diagnostics area trước khi vào handler sang stacked diagnostics area và tạo current diagnostics area cho handler.

Ban đầu hai vùng có nội dung giống nhau. Nhưng câu lệnh chạy trong handler có thể thay đổi current diagnostics area. Stacked diagnostics area giữ condition đã kích hoạt handler và không bị các statement thông thường trong handler ghi đè; RESIGNAL là ngoại lệ có thể tác động đến nó.

Vì vậy, khi cần bảo toàn lỗi gốc, hãy dùng:

    GET STACKED DIAGNOSTICS ...

Đừng thực hiện SET, INSERT, ROLLBACK hoặc câu SQL khác trước rồi mới cố lấy lỗi gốc từ CURRENT diagnostics area. Khi đó current area có thể đã bị thay đổi.

### 6.3. Không mặc định CONDITION 1 là lỗi chính

MySQL có thể ghi nhiều condition trong diagnostics area và không bảo đảm condition số 1 luôn là condition chính của statement trước đó.

Để lấy condition chính, trước hết đọc NUMBER rồi dùng số condition đó:

    GET STACKED DIAGNOSTICS
        v_condition_count = NUMBER;

    IF v_condition_count > 0 THEN
        GET STACKED DIAGNOSTICS CONDITION v_condition_count
            v_sqlstate = RETURNED_SQLSTATE,
            v_mysql_errno = MYSQL_ERRNO,
            v_message_text = MESSAGE_TEXT;
    END IF;

Trong ví dụ này, condition cuối cùng được chọn theo hướng dẫn của MySQL để lấy condition chính trong trường hợp có nhiều condition. Cách này đáng tin cậy hơn giả định CONDITION 1 luôn là lỗi cần báo.

### 6.4. Ví dụ đầy đủ trong EXIT handler

    CREATE PROCEDURE capture_error_context()
    BEGIN
        DECLARE v_condition_count INT DEFAULT 0;
        DECLARE v_sqlstate CHAR(5) DEFAULT '00000';
        DECLARE v_mysql_errno INT DEFAULT 0;
        DECLARE v_message_text VARCHAR(128) DEFAULT '';

        DECLARE EXIT HANDLER FOR SQLEXCEPTION
        BEGIN
            GET STACKED DIAGNOSTICS
                v_condition_count = NUMBER;

            IF v_condition_count > 0 THEN
                GET STACKED DIAGNOSTICS CONDITION v_condition_count
                    v_sqlstate = RETURNED_SQLSTATE,
                    v_mysql_errno = MYSQL_ERRNO,
                    v_message_text = MESSAGE_TEXT;
            END IF;

            SELECT
                v_sqlstate AS original_sqlstate,
                v_mysql_errno AS original_errno,
                v_message_text AS original_message;

            RESIGNAL;
        END;

        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 30031,
                MESSAGE_TEXT = 'demo failure for diagnostics';
    END;

Handler lấy thông tin từ stacked area trước khi chạy các statement có thể thay đổi current area. SELECT chỉ minh họa việc quan sát; trong ứng dụng thực tế, không nên trả nội dung nhạy cảm hoặc biến kết quả handler thành một result set ngoài hợp đồng API. RESIGNAL chuyển tiếp condition gốc cho caller.

## 7. RESIGNAL: chuyển tiếp condition đang xử lý

RESIGNAL chỉ hợp lệ khi execution context hiện tại là condition handler. Gọi RESIGNAL ngoài handler sẽ gây lỗi RESIGNAL when handler not active.

Cú pháp tổng quát:

    RESIGNAL;

    RESIGNAL SET signal_information_item = value [, ...];

    RESIGNAL condition_value
        [SET signal_information_item = value [, ...]];

RESIGNAL khác SIGNAL:

| SIGNAL | RESIGNAL |
|---|---|
| Tạo condition mới | Chuyển tiếp condition hiện có trong handler |
| Có thể dùng trong stored program và ngoài handler | Chỉ dùng khi đang chạy handler |
| Dùng để validation hoặc phát lỗi nghiệp vụ | Dùng để cleanup, bổ sung ngữ cảnh hoặc chuyển lỗi lên caller |
| Không cần condition trước đó | Dựa trên condition đã kích hoạt handler |

### 7.1. RESIGNAL không tham số: giữ nguyên lỗi gốc

Đây là cách bảo toàn lỗi đơn giản nhất:

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        -- Có thể thu thập diagnostics hoặc cleanup.
        RESIGNAL;
    END;

RESIGNAL không tham số chuyển tiếp condition đang được handler xử lý mà không thay đổi SQLSTATE, MYSQL_ERRNO và MESSAGE_TEXT gốc.

Đây là lựa chọn nên dùng khi handler chỉ cần cleanup hoặc thực hiện một thao tác phụ rồi để caller quyết định xử lý.

### 7.2. RESIGNAL SET: chỉ thay đổi thông tin cần thiết

Nếu cần thêm ngữ cảnh cho thông điệp nhưng muốn giữ SQLSTATE và mã lỗi:

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL
            SET MESSAGE_TEXT = 'order operation failed';
    END;

Trong dạng này, MESSAGE_TEXT được thay đổi. Các signal information item khác không được chỉ định vẫn giữ thông tin condition gốc.

MESSAGE_TEXT giới hạn 128 ký tự. Hãy dùng thông điệp ngắn, không chứa mật khẩu, token, dữ liệu cá nhân hoặc câu SQL đầy đủ.

### 7.3. RESIGNAL với SQLSTATE mới: chủ động chuyển đổi lỗi

Có lúc muốn ánh xạ lỗi hạ tầng thành lỗi nghiệp vụ mà API hiểu:

    DECLARE EXIT HANDLER FOR 1062
    BEGIN
        RESIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 30042,
                MESSAGE_TEXT = 'order number already exists';
    END;

Ở đây handler biến lỗi duplicate key thành mã lỗi nghiệp vụ 30042. Caller nhìn thấy condition mới làm lỗi được phát ra; diagnostics area có thể chứa thêm condition liên quan đến lỗi ban đầu. Việc chuyển đổi này là quyết định API có chủ ý, không còn là bảo toàn nguyên trạng lỗi gốc.

Nếu cần giữ đầy đủ thông tin lỗi gốc để điều tra, hãy lấy diagnostics từ STACKED trước khi RESIGNAL, sau đó ghi vào kênh log phù hợp. Đừng chuyển đổi SQLSTATE hoặc MYSQL_ERRNO nếu ứng dụng cần phân biệt chính xác lỗi MySQL ban đầu.

### 7.4. RESIGNAL không thay thế SIGNAL

Không dùng RESIGNAL để phát một lỗi validation mới trước khi có handler:

    -- Sai ngữ cảnh nếu statement này chạy ngoài handler:
    -- RESIGNAL SQLSTATE '45000';

Dùng SIGNAL cho condition mới:

    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'customer is inactive';

Chỉ dùng RESIGNAL bên trong handler đang hoạt động để chuyển tiếp condition mà handler nhận được.

## 8. Mẫu handler bảo toàn lỗi gốc

Một handler tổng quát thường có ba bước:

1. Đọc thông tin condition từ STACKED diagnostics.
2. Thực hiện cleanup cần thiết theo transaction contract.
3. RESIGNAL để caller nhận lỗi gốc.

Mẫu:

    DECLARE v_condition_count INT DEFAULT 0;
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_mysql_errno INT;
    DECLARE v_message_text VARCHAR(128);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET STACKED DIAGNOSTICS
            v_condition_count = NUMBER;

        IF v_condition_count > 0 THEN
            GET STACKED DIAGNOSTICS CONDITION v_condition_count
                v_sqlstate = RETURNED_SQLSTATE,
                v_mysql_errno = MYSQL_ERRNO,
                v_message_text = MESSAGE_TEXT;
        END IF;

        -- Thực hiện cleanup phù hợp với quyền sở hữu transaction.
        RESIGNAL;
    END;

Không bắt SQLEXCEPTION rồi kết thúc handler mà không RESIGNAL nếu ý định là báo lỗi cho caller. Nếu handler EXIT kết thúc procedure bình thường, caller có thể hiểu nhầm thao tác đã thành công dù một statement bên trong thất bại.

## 9. Kết hợp RESIGNAL với transaction

Handler có thể cần rollback khi stored procedure tự sở hữu transaction. Tuy nhiên, MySQL không có nested transaction thực sự. START TRANSACTION trong khi transaction khác đang hoạt động có thể commit transaction hiện tại trước khi bắt đầu transaction mới.

Vì vậy, mỗi procedure phải xác định rõ transaction contract:

- **Procedure-owned transaction**: procedure tự START TRANSACTION, COMMIT và ROLLBACK. Caller phải gọi theo hợp đồng yêu cầu, thường là không có transaction đang hoạt động.
- **Caller-owned transaction**: caller mở transaction và quyết định COMMIT/ROLLBACK. Procedure không tự START TRANSACTION, COMMIT hoặc ROLLBACK.

### 9.1. Procedure-owned transaction

Ví dụ khung xử lý:

    CREATE PROCEDURE create_order_atomic(
        IN p_customer_id BIGINT UNSIGNED,
        IN p_amount DECIMAL(12,2)
    )
    BEGIN
        DECLARE v_transaction_started BOOLEAN DEFAULT FALSE;
        DECLARE v_condition_count INT DEFAULT 0;
        DECLARE v_sqlstate CHAR(5);
        DECLARE v_mysql_errno INT;
        DECLARE v_message_text VARCHAR(128);

        DECLARE EXIT HANDLER FOR SQLEXCEPTION
        BEGIN
            GET STACKED DIAGNOSTICS
                v_condition_count = NUMBER;

            IF v_condition_count > 0 THEN
                GET STACKED DIAGNOSTICS CONDITION v_condition_count
                    v_sqlstate = RETURNED_SQLSTATE,
                    v_mysql_errno = MYSQL_ERRNO,
                    v_message_text = MESSAGE_TEXT;
            END IF;

            IF v_transaction_started THEN
                ROLLBACK;
            END IF;

            RESIGNAL;
        END;

        IF p_amount IS NULL OR p_amount <= 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MYSQL_ERRNO = 30051,
                    MESSAGE_TEXT = 'order amount must be positive';
        END IF;

        START TRANSACTION;
        SET v_transaction_started = TRUE;

        INSERT INTO orders(customer_id, total_amount)
        VALUES (p_customer_id, p_amount);

        COMMIT;
        SET v_transaction_started = FALSE;
    END;

Ví dụ chỉ minh họa cấu trúc. Trong code thực tế, nên đặt cờ transaction sao cho phản ánh đúng trạng thái sau khi START TRANSACTION và COMMIT thành công; cần xác định rõ hành vi khi START hoặc COMMIT tự phát sinh lỗi. Quan trọng nhất, caller không được có transaction đang hoạt động nếu procedure được thiết kế để tự sở hữu transaction.

Handler lấy diagnostics trước ROLLBACK. RESIGNAL sau ROLLBACK vẫn chuyển tiếp condition ban đầu từ stacked diagnostics area.

### 9.2. Caller-owned transaction

Nếu ứng dụng quản lý transaction, procedure nên để quyền quyết định cho caller:

    CREATE PROCEDURE reserve_inventory(
        IN p_product_id BIGINT UNSIGNED,
        IN p_quantity INT
    )
    BEGIN
        DECLARE EXIT HANDLER FOR SQLEXCEPTION
        BEGIN
            RESIGNAL;
        END;

        IF p_quantity <= 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MYSQL_ERRNO = 30052,
                    MESSAGE_TEXT = 'quantity must be positive';
        END IF;

        UPDATE inventory
        SET available_quantity = available_quantity - p_quantity
        WHERE product_id = p_product_id
          AND available_quantity >= p_quantity;

        IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000'
                SET MYSQL_ERRNO = 30053,
                    MESSAGE_TEXT = 'insufficient inventory';
        END IF;
    END;

Caller có thể thực hiện:

    START TRANSACTION;

    CALL reserve_inventory(1001, 2);

    -- Các thao tác nghiệp vụ liên quan khác.

    COMMIT;

Nếu CALL lỗi, ứng dụng nhận exception và quyết định ROLLBACK theo transaction contract. Procedure không tự rollback transaction của caller.

### 9.3. Logging lỗi và rollback

Nếu handler INSERT một bản ghi vào error_log rồi ROLLBACK transaction, bản ghi log nằm trong cùng transaction có thể bị rollback theo. MySQL không cung cấp autonomous transaction như một số hệ quản trị khác.

Để bảo toàn log lỗi:

- Ghi log ở application layer sau khi nhận lỗi.
- Dùng một connection/transaction độc lập cho audit nếu kiến trúc cho phép.
- Gửi event đến hệ thống logging bên ngoài.
- Nếu ghi log trong cùng transaction, hiểu rằng rollback có thể xóa bản ghi đó.

Không tuyên bố đã ghi audit bền vững nếu INSERT log có thể bị rollback cùng nghiệp vụ.

## 10. Cursor và NOT FOUND: tách EOF khỏi exception

Trong cursor loop, NOT FOUND thường báo FETCH không còn hàng. Handler phổ biến:

    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE cur_orders CURSOR FOR
        SELECT order_id
        FROM orders
        ORDER BY order_id;
    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    OPEN cur_orders;

    read_loop: LOOP
        FETCH cur_orders INTO v_order_id;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        -- Xử lý hàng hiện tại.
    END LOOP;

    CLOSE cur_orders;

Handler NOT FOUND này có thể bắt cả condition từ SELECT ... INTO không trả hàng nếu SELECT đó chạy trong cùng scope. Điều này dễ làm cursor loop kết thúc sớm ngoài ý muốn.

### 10.1. Cô lập SELECT ... INTO bằng block con

Nếu trong loop có truy vấn phụ có thể không tìm thấy hàng, đặt nó trong block riêng với handler riêng:

    read_loop: LOOP
        FETCH cur_orders INTO v_order_id;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        BEGIN
            DECLARE v_related_found BOOLEAN DEFAULT TRUE;
            DECLARE v_related_value VARCHAR(100);

            DECLARE CONTINUE HANDLER FOR NOT FOUND
                SET v_related_found = FALSE;

            SELECT related_value
            INTO v_related_value
            FROM order_metadata
            WHERE order_id = v_order_id;

            IF NOT v_related_found THEN
                SET v_related_value = 'no metadata';
            END IF;
        END;

        -- Cursor handler bên ngoài không bị dùng cho SELECT phụ.
    END LOOP;

Block con giới hạn scope của handler NOT FOUND cho SELECT ... INTO. FETCH vẫn dùng handler NOT FOUND ở block chứa cursor loop.

### 10.2. Không dùng SQLSTATE 02000 cho lỗi nghiệp vụ

Nếu routine SIGNAL SQLSTATE 02000 để báo customer không hợp lệ, handler NOT FOUND của cursor có thể coi đó như EOF. Dùng SQLSTATE 45000 cho lỗi nghiệp vụ và giữ SQLSTATE 02000 cho tình huống không tìm thấy dữ liệu theo đúng ngữ nghĩa.

## 11. Bắt lỗi cụ thể và chuyển thành lỗi nghiệp vụ

Một số lỗi MySQL có thể được chuyển thành mã lỗi mà ứng dụng hiểu rõ hơn. Ví dụ duplicate key 1062:

    CREATE PROCEDURE register_external_order(
        IN p_external_ref VARCHAR(100)
    )
    BEGIN
        DECLARE duplicate_key CONDITION FOR 1062;

        DECLARE EXIT HANDLER FOR duplicate_key
        BEGIN
            RESIGNAL SQLSTATE '45000'
                SET MYSQL_ERRNO = 30061,
                    MESSAGE_TEXT = 'external reference already exists';
        END;

        INSERT INTO external_order(external_ref)
        VALUES (p_external_ref);
    END;

Caller nhận lỗi nghiệp vụ 30061 thay vì phải phụ thuộc trực tiếp vào mã 1062. Đây là một lựa chọn thiết kế API; nếu vận hành cần biết lỗi gốc, hãy ghi nhận diagnostics trước khi chuyển đổi.

Nếu muốn bảo toàn lỗi nguyên trạng, dùng RESIGNAL không tham số:

    DECLARE EXIT HANDLER FOR 1062
    BEGIN
        RESIGNAL;
    END;

Không chuyển tất cả SQLEXCEPTION thành cùng một SQLSTATE nếu ứng dụng hoặc người vận hành cần phân biệt deadlock, timeout, duplicate key, foreign key và lỗi cấu hình.

## 12. Truyền lỗi qua nhiều tầng stored program

Procedure A có thể gọi procedure B. Nếu B gặp lỗi:

- B có thể không khai báo handler; condition truyền ra caller theo quy tắc handler scope.
- B có handler EXIT và RESIGNAL; condition gốc được chuyển tiếp cho A.
- A có thể có handler cụ thể để chuyển đổi lỗi hoặc cleanup.
- Nếu A cũng RESIGNAL, condition tiếp tục truyền lên ứng dụng.

Sơ đồ luồng:

    Application
        |
        | CALL procedure_A()
        v
    procedure_A
        |
        | CALL procedure_B()
        v
    procedure_B
        |
        | statement raises SQLSTATE / MySQL error
        v
    handler in procedure_B
        |
        | GET STACKED DIAGNOSTICS
        | optional cleanup
        | RESIGNAL
        v
    handler in procedure_A (if applicable)
        |
        | RESIGNAL or deliberate translation
        v
    Application receives condition

Mỗi tầng chỉ nên chuyển đổi lỗi khi có lý do nghiệp vụ rõ ràng. Nếu mọi tầng đều thay MESSAGE_TEXT hoặc SQLSTATE, việc tìm nguyên nhân gốc sẽ khó hơn.

## 13. Diagnostics area có thể chứa nhiều condition

Một statement có thể tạo nhiều warning hoặc condition. Diagnostics area gồm:

- Statement information: NUMBER, ROW_COUNT.
- Condition information: SQLSTATE, MYSQL_ERRNO, MESSAGE_TEXT và các item liên quan.

Khi handler được kích hoạt, MySQL tạo stacked diagnostics area chứa thông tin trước khi handler bắt đầu. CURRENT diagnostics area dành cho statement trong handler. Dùng GET STACKED DIAGNOSTICS để đọc condition ban đầu sau khi handler chạy các statement khác.

Ví dụ lấy toàn bộ số condition:

    GET STACKED DIAGNOSTICS
        v_condition_count = NUMBER;

Nếu cần điều tra nhiều condition, có thể lặp từ 1 đến NUMBER và đọc từng condition. Tuy nhiên, để lấy lỗi chính của statement trong MySQL, không mặc định condition 1 là lỗi chính; lấy condition number bằng NUMBER rồi đọc condition ở vị trí đó.

GET DIAGNOSTICS là statement chẩn đoán và được phép trong stored program. SIGNAL, RESIGNAL và GET DIAGNOSTICS không được dùng như câu lệnh SQL được PREPARE/EXECUTE động.

## 14. Xây dựng hợp đồng lỗi cho ứng dụng

Stored program nên phát lỗi có cấu trúc để ứng dụng không phải phân tích chuỗi message.

Một hợp đồng lỗi có thể gồm:

| Thành phần | Quy ước đề xuất |
|---|---|
| SQLSTATE | Nhóm lỗi tổng quát, ví dụ 45000 cho lỗi nghiệp vụ tùy chỉnh |
| MYSQL_ERRNO | Mã cụ thể do dự án quản lý |
| MESSAGE_TEXT | Thông điệp ngắn, an toàn, tối đa 128 ký tự |
| Logging context | Request ID, tenant ID, procedure name và thông tin chẩn đoán được phép lưu |
| Retry policy | Chỉ retry các lỗi tạm thời đã xác định như deadlock/lock timeout theo chính sách |

Ví dụ quy ước:

| MYSQL_ERRNO | Ý nghĩa |
|---:|---|
| 30001 | Giá trị amount không hợp lệ |
| 30021 | Tổng hóa đơn không hợp lệ |
| 30042 | Mã đơn bên ngoài đã tồn tại |
| 30053 | Không đủ tồn kho |

Các số trên chỉ là ví dụ. Dự án cần duy trì registry mã lỗi để các service không gán trùng ý nghĩa.

### 14.1. Không parse MESSAGE_TEXT để điều khiển nghiệp vụ

Không nên viết logic như:

    IF error_message LIKE '%duplicate%' THEN
        -- xử lý duplicate
    END IF;

Thông điệp có thể thay đổi. Hãy dùng SQLSTATE và MYSQL_ERRNO:

- SQLSTATE cho phân loại tổng quát.
- MYSQL_ERRNO cho mã lỗi cụ thể.
- MESSAGE_TEXT cho người vận hành hoặc log.

### 14.2. Không làm lộ thông tin nhạy cảm

Thông điệp lỗi trả về client không nên chứa:

- Password, token hoặc secret.
- Nội dung SQL có literal nhạy cảm.
- Dữ liệu cá nhân không cần thiết.
- Đường dẫn nội bộ hoặc thông tin hạ tầng không cần cho caller.
- Toàn bộ nội dung diagnostics nếu nó chứa dữ liệu nhạy cảm.

Giữ thông điệp client ngắn và an toàn; lưu thông tin chi tiết ở kênh log được kiểm soát.

## 15. Kiểm thử SIGNAL và RESIGNAL

Kiểm thử không chỉ xác nhận routine có báo lỗi. Cần xác nhận SQLSTATE, MYSQL_ERRNO, MESSAGE_TEXT và hành vi luồng điều khiển.

### 15.1. Kiểm thử SIGNAL

    CALL validate_payment(0);

Kỳ vọng:

- CALL trả lỗi.
- SQLSTATE là 45000.
- MYSQL_ERRNO là 30001.
- Message chỉ ra amount phải lớn hơn 0.
- Statement sau SIGNAL không chạy nếu không có CONTINUE handler.

### 15.2. Kiểm thử RESIGNAL giữ nguyên lỗi

Tạo procedure cố ý gây lỗi trong một handler tổng quát:

    CREATE PROCEDURE test_preserve_original_error()
    BEGIN
        DECLARE v_condition_count INT DEFAULT 0;
        DECLARE v_sqlstate CHAR(5);
        DECLARE v_errno INT;
        DECLARE v_message VARCHAR(128);

        DECLARE EXIT HANDLER FOR SQLEXCEPTION
        BEGIN
            GET STACKED DIAGNOSTICS
                v_condition_count = NUMBER;

            IF v_condition_count > 0 THEN
                GET STACKED DIAGNOSTICS CONDITION v_condition_count
                    v_sqlstate = RETURNED_SQLSTATE,
                    v_errno = MYSQL_ERRNO,
                    v_message = MESSAGE_TEXT;
            END IF;

            RESIGNAL;
        END;

        SIGNAL SQLSTATE '45000'
            SET MYSQL_ERRNO = 30071,
                MESSAGE_TEXT = 'original test condition';
    END;

    CALL test_preserve_original_error();

Kỳ vọng caller nhận lại SQLSTATE 45000, MYSQL_ERRNO 30071 và thông điệp gốc. Handler có thể đọc thông tin trước khi chuyển tiếp.

### 15.3. Kiểm thử RESIGNAL thay thông điệp

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        RESIGNAL SET
            MESSAGE_TEXT = 'order service could not complete request';
    END;

Kỳ vọng SQLSTATE và MYSQL_ERRNO của condition gốc được giữ, còn MESSAGE_TEXT được thay bằng thông điệp mới.

### 15.4. Kiểm thử chuyển đổi lỗi

Tạo duplicate key và kiểm tra handler có chuyển mã lỗi thành mã nghiệp vụ đã định nghĩa hay không. Đồng thời xác nhận log nội bộ vẫn có thông tin lỗi gốc nếu yêu cầu vận hành cần.

### 15.5. Kiểm thử handler scope

Tạo block con có handler NOT FOUND và block cha có handler NOT FOUND khác. Kiểm tra SELECT ... INTO không có hàng không làm cursor loop bên ngoài kết thúc sớm.

## 16. Những lỗi thường gặp

- Dùng SIGNAL SQLSTATE '00000' dù đây là success class.
- Dùng SQLSTATE 02000 cho lỗi validation rồi vô tình kích hoạt NOT FOUND handler.
- Dùng warning khi cần dừng transaction hoặc thao tác.
- Dùng RESIGNAL ngoài handler.
- Dùng condition name gắn với MySQL error number trong SIGNAL.
- Nghĩ RESIGNAL và SIGNAL có cùng mục đích.
- Bắt SQLEXCEPTION rồi nuốt lỗi mà không trả trạng thái thất bại cho caller.
- Dùng GET DIAGNOSTICS CURRENT sau khi handler đã chạy SET/ROLLBACK và làm mất thông tin condition gốc.
- Giả định CONDITION 1 luôn là lỗi chính.
- Quên đọc NUMBER trước khi chọn condition cần lấy.
- Chỉ lưu MESSAGE_TEXT mà bỏ SQLSTATE và MYSQL_ERRNO.
- Thay SQLSTATE hoặc MYSQL_ERRNO khi không có lý do chuyển đổi API.
- Khai báo handler trước cursor.
- Không hiểu handler EXIT thoát block nơi nó được khai báo.
- Dùng NOT FOUND handler chung cho cursor và SELECT ... INTO trong cùng scope.
- Ghi error_log trong transaction rồi ROLLBACK và kỳ vọng log vẫn tồn tại.
- Procedure tự ROLLBACK transaction do caller sở hữu.
- Dùng message text để ứng dụng phân nhánh nghiệp vụ.
- Trả diagnostics có chứa thông tin nhạy cảm cho client.
- Không kiểm thử SQLSTATE, MYSQL_ERRNO và luồng điều khiển cùng nhau.

## 17. Checklist thiết kế error handling

- Đã phân biệt warning, not found và exception.
- Đã chọn SQLSTATE theo ngữ nghĩa condition.
- Đã dùng 45000 cho lỗi nghiệp vụ tùy chỉnh phù hợp.
- Đã đặt MYSQL_ERRNO theo registry mã lỗi của dự án.
- Đã giữ MESSAGE_TEXT ngắn, không nhạy cảm và trong giới hạn 128 ký tự.
- Đã khai báo condition name đúng loại SQLSTATE hoặc MySQL error number.
- Đã đặt biến, condition, cursor và handler theo đúng thứ tự khai báo.
- Đã chọn CONTINUE hoặc EXIT theo luồng điều khiển mong muốn.
- Đã hiểu precedence và scope của handler.
- Đã dùng GET STACKED DIAGNOSTICS trong handler khi cần giữ lỗi gốc.
- Đã lấy NUMBER trước khi chọn condition chính.
- Đã dùng RESIGNAL không tham số khi muốn bảo toàn lỗi nguyên trạng.
- Chỉ thay MESSAGE_TEXT hoặc SQLSTATE khi có chủ đích API rõ ràng.
- Đã tách NOT FOUND của cursor khỏi SELECT ... INTO không có hàng.
- Đã xác định procedure-owned hay caller-owned transaction.
- Đã kiểm tra logging có bị rollback cùng transaction không.
- Đã kiểm thử bằng account và client thực tế của ứng dụng.
- Đã xác nhận caller nhận đúng SQLSTATE, MYSQL_ERRNO và thông điệp.

## 18. Tài liệu tham khảo

- MySQL 8.4 Reference Manual — SIGNAL Statement: https://dev.mysql.com/doc/refman/8.4/en/signal.html
- MySQL 8.4 Reference Manual — RESIGNAL Statement: https://dev.mysql.com/doc/refman/8.4/en/resignal.html
- MySQL 8.4 Reference Manual — GET DIAGNOSTICS Statement: https://dev.mysql.com/doc/refman/8.4/en/get-diagnostics.html
- MySQL 8.4 Reference Manual — Scope Rules for Handlers: https://dev.mysql.com/doc/refman/8.4/en/handler-scope.html
- MySQL 8.4 Reference Manual — The MySQL Diagnostics Area: https://dev.mysql.com/doc/refman/8.4/en/diagnostics-area.html
- MySQL 8.4 Reference Manual — Restrictions on Condition Handling: https://dev.mysql.com/doc/refman/8.4/en/condition-handling-restrictions.html

SIGNAL tạo condition mới; RESIGNAL chuyển tiếp condition trong handler; GET DIAGNOSTICS đọc thông tin chẩn đoán. Muốn bảo toàn lỗi gốc, hãy lấy dữ liệu từ STACKED diagnostics trước khi cleanup, chọn condition chính bằng NUMBER thay vì giả định CONDITION 1, rồi dùng RESIGNAL không tham số. Chỉ thay SQLSTATE, MYSQL_ERRNO hoặc MESSAGE_TEXT khi có chủ đích chuyển đổi hợp đồng lỗi. Handler phải có scope và action rõ ràng; đặc biệt cần tách NOT FOUND của cursor khỏi truy vấn phụ và xác định ai sở hữu transaction. Khi làm đúng, stored program có thể xử lý lỗi nội bộ mà vẫn cung cấp cho caller thông tin ổn định để log, retry hoặc trả lỗi nghiệp vụ phù hợp.
