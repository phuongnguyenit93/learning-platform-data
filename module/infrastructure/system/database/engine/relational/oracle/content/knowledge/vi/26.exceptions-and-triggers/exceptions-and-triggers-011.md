# PRAGMA AUTONOMOUS_TRANSACTION cho nhật ký và rủi ro mất nhất quán

Trong Oracle PL/SQL, một transaction thường bao gồm nhiều câu lệnh cùng commit hoặc rollback như một đơn vị. Khi cần ghi nhật ký lỗi hoặc ghi nhận một sự kiện phải tồn tại ngay cả khi transaction nghiệp vụ bị rollback, có thể dùng **autonomous transaction** (giao dịch tự trị).

Một routine được đánh dấu bằng PRAGMA AUTONOMOUS_TRANSACTION chạy trong một transaction độc lập với transaction đã gọi nó. Routine tự trị có thể commit hoặc rollback phần việc của chính nó; thao tác đó không commit hay rollback transaction của caller. Khi routine kết thúc, transaction của caller tiếp tục.

Cơ chế này hữu ích cho error logging, nhưng cũng tạo ra một ranh giới nhất quán dữ liệu cần được thiết kế cẩn thận. Một dòng log có thể đã commit trong khi thay đổi nghiệp vụ mà nó mô tả bị rollback. Nếu dùng autonomous transaction để ghi audit “giao dịch đã thành công”, log có thể nói một điều mà dữ liệu chính không xác nhận.

Bài học trình bày:

- Cách khai báo và vòng đời của autonomous transaction.
- Sự độc lập giữa transaction tự trị và transaction gọi nó.
- Ghi log lỗi bền vững khi transaction nghiệp vụ rollback.
- Dùng autonomous transaction trong trigger và những giới hạn cần biết.
- Rủi ro dữ liệu mất nhất quán, deadlock, khóa và foreign key.
- Phân biệt log lần thử với audit giao dịch đã commit.
- Kiểm thử hành vi commit/rollback bằng lab và chọn mô hình phù hợp.

Các ví dụ dùng Oracle Database 19c. Chỉ dùng autonomous transaction khi cần tính độc lập về transaction là một yêu cầu có chủ đích.

## 1. Transaction thông thường và autonomous transaction

Một transaction thông thường bắt đầu khi session thực hiện DML và kết thúc bằng COMMIT hoặc ROLLBACK. Nếu procedure được gọi trong transaction đó chạy câu INSERT, UPDATE hoặc DELETE, DML thường tham gia cùng transaction của caller.

Ví dụ:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    INSERT INTO transaction_audit (
        account_id,
        event_name
    )
    VALUES (10, 'DEBIT');

    ROLLBACK;
END;
/
~~~

Nếu không có autonomous transaction, cả UPDATE và INSERT đều bị rollback. Đây thường là hành vi mong muốn của audit nghiệp vụ: audit chỉ tồn tại nếu thay đổi nghiệp vụ commit.

Autonomous transaction tạo một transaction độc lập:

~~~text
MAIN TRANSACTION
  UPDATE business row
       |
       | gọi routine tự trị
       v
  SUSPENDED
       |
       +-------------------------------+
                                       |
AUTONOMOUS TRANSACTION                 |
  INSERT error/event log               |
  COMMIT                               |
       |                               |
       +-------------------------------+
                                       |
MAIN TRANSACTION                      |
  RESUMES <----------------------------+
  COMMIT hoặc ROLLBACK
~~~

Khi routine tự trị commit, dòng log được lưu độc lập. Nếu transaction chính sau đó rollback, dòng log vẫn còn.

### 1.1. Autonomous transaction không phải session mới

Routine tự trị vẫn chạy trong cùng database session và cùng call stack. Oracle tạo một transaction context riêng cho routine. Nó không tạo một connection mới và không tự thay đổi SESSION_USER.

Điều này có nghĩa:

- Context transaction độc lập.
- Session identity và session settings vẫn liên quan đến session gọi.
- Routine tự trị vẫn có thể gặp lock contention với transaction chính.
- Cursor, package state và các tài nguyên session không trở thành một session hoàn toàn khác.

### 1.2. Khi nào cần độc lập transaction?

Một số tình huống phù hợp:

- Ghi lại lỗi trước khi exception được ném trở lại caller.
- Ghi nhận một lần thử thao tác bị từ chối hoặc thất bại.
- Ghi lại thông tin chẩn đoán khi transaction chính có thể rollback.
- Ghi nhận một sự kiện vận hành mà nghiệp vụ yêu cầu giữ lại bất kể kết quả transaction chính.
- Một số trigger cần ghi lại lần thay đổi được thử, kể cả khi DML bên ngoài sau đó rollback.

Không dùng autonomous transaction chỉ để “cho phép COMMIT trong procedure”. Nếu procedure cần tham gia transaction nghiệp vụ của caller, hãy để nó dùng transaction của caller và để tầng gọi quyết định commit/rollback.

## 2. Khai báo PRAGMA AUTONOMOUS_TRANSACTION

PRAGMA AUTONOMOUS_TRANSACTION khai báo routine hoặc trigger là autonomous. Pragma được đặt trong phần khai báo của routine, trước BEGIN.

### 2.1. Procedure độc lập

~~~sql
CREATE OR REPLACE PROCEDURE write_log (
    p_message IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_log (
        log_time,
        message
    )
    VALUES (
        SYSTIMESTAMP,
        p_message
    );

    COMMIT;
END;
/
~~~

Lệnh COMMIT trong procedure này commit transaction tự trị. Nó không commit các DML chưa commit của caller.

### 2.2. Function độc lập

Function cũng có thể được khai báo autonomous:

~~~sql
CREATE OR REPLACE FUNCTION record_attempt (
    p_event IN VARCHAR2
) RETURN NUMBER
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
    v_log_id NUMBER;
BEGIN
    INSERT INTO application_log (
        log_time,
        message
    )
    VALUES (
        SYSTIMESTAMP,
        p_event
    )
    RETURNING log_id INTO v_log_id;

    COMMIT;
    RETURN v_log_id;
END;
/
~~~

Function có side effect và transaction control cần được gọi trong ngữ cảnh phù hợp. Không nên gọi function ghi log như một phần của biểu thức SELECT chỉ vì có thể làm vậy; side effect trong truy vấn làm hành vi khó dự đoán, khó tối ưu và khó kiểm soát.

### 2.3. Autonomous transaction trong package

Pragma được khai báo trong phần khai báo của từng subprogram cần tự trị trong package body:

~~~sql
CREATE OR REPLACE PACKAGE app_logger AS
    PROCEDURE write_event (
        p_event_name IN VARCHAR2,
        p_detail     IN VARCHAR2
    );
END app_logger;
/
~~~

~~~sql
CREATE OR REPLACE PACKAGE BODY app_logger AS
    PROCEDURE write_event (
        p_event_name IN VARCHAR2,
        p_detail     IN VARCHAR2
    )
    AS
        PRAGMA AUTONOMOUS_TRANSACTION;
    BEGIN
        INSERT INTO application_log (
            log_time,
            event_name,
            detail
        )
        VALUES (
            SYSTIMESTAMP,
            p_event_name,
            p_detail
        );

        COMMIT;
    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK;
            RAISE;
    END write_event;
END app_logger;
/
~~~

Pragma gắn với subprogram được khai báo, không tự biến mọi procedure khác trong package thành autonomous. Nếu một package có nhiều routine, chỉ đánh dấu routine thật sự cần transaction độc lập.

### 2.4. Autonomous trigger

Trigger cũng có thể được khai báo autonomous:

~~~sql
CREATE OR REPLACE TRIGGER trg_log_salary_attempt
AFTER UPDATE OF salary ON employees
FOR EACH ROW
DECLARE
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO salary_change_attempts (
        employee_id,
        old_salary,
        new_salary,
        attempted_at
    )
    VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYSTIMESTAMP
    );

    COMMIT;
END;
/
~~~

Đây là log **lần thử thay đổi**. Trigger tự trị commit log độc lập với transaction đang cập nhật EMPLOYEES. Nếu transaction chính rollback, dòng trong SALARY_CHANGE_ATTEMPTS vẫn tồn tại.

Không đặt tên hoặc diễn giải dòng này là “salary change committed” vì trigger không thể khẳng định transaction bên ngoài sẽ commit sau đó.

## 3. Vòng đời transaction tự trị

Một routine tự trị cần quản lý transaction của chính nó bằng COMMIT hoặc ROLLBACK.

### 3.1. Các bước thực thi

1. Transaction chính đang chạy.
2. Caller gọi routine có PRAGMA AUTONOMOUS_TRANSACTION.
3. Oracle tạm dừng transaction chính.
4. Routine tự trị bắt đầu thực hiện DML trong transaction riêng.
5. Routine commit hoặc rollback transaction riêng.
6. Routine kết thúc.
7. Transaction chính tiếp tục từ vị trí đã tạm dừng.

Transaction chính không bị commit hoặc rollback khi routine tự trị kết thúc.

### 3.2. COMMIT trong routine tự trị

~~~sql
CREATE OR REPLACE PROCEDURE log_message (
    p_message IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_log (log_time, message)
    VALUES (SYSTIMESTAMP, p_message);

    COMMIT;
END;
/
~~~

COMMIT bảo đảm log được lưu ngay cả khi caller rollback sau đó.

### 3.3. ROLLBACK trong routine tự trị

~~~sql
CREATE OR REPLACE PROCEDURE try_log (
    p_message IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_log (log_time, message)
    VALUES (SYSTIMESTAMP, p_message);

    ROLLBACK;
END;
/
~~~

Trong ví dụ này, dòng log bị rollback. ROLLBACK chỉ tác động transaction tự trị, không rollback transaction chính.

### 3.4. Routine phải kết thúc với transaction đã đóng

Nếu routine tự trị kết thúc trong khi transaction riêng vẫn còn active, Oracle phát sinh:

~~~text
ORA-06519: active autonomous transaction detected and rolled back
~~~

Oracle rollback transaction tự trị chưa kết thúc và báo lỗi. Vì vậy, mọi đường thực thi bình thường và đường exception phải có COMMIT hoặc ROLLBACK phù hợp.

Mẫu xử lý:

~~~sql
CREATE OR REPLACE PROCEDURE write_event (
    p_message IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_log (log_time, message)
    VALUES (SYSTIMESTAMP, p_message);

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Không để một nhánh IF hoặc exception handler thoát khỏi routine mà transaction tự trị vẫn mở.

### 3.5. Savepoint của hai transaction tách biệt

Autonomous transaction có phạm vi savepoint riêng. Nó không thể rollback về savepoint được tạo bởi transaction chính; transaction chính cũng không thể dùng savepoint bên trong autonomous routine.

Không dùng savepoint như một cách chia sẻ trạng thái giữa hai transaction. Hãy xem mỗi transaction là một đơn vị commit/rollback riêng.

## 4. Dữ liệu nào nhìn thấy được giữa hai transaction?

Độc lập transaction không có nghĩa hai bên tự động nhìn thấy dữ liệu chưa commit của nhau.

### 4.1. Autonomous transaction không thấy DML chưa commit của caller

Giả sử transaction chính thực hiện:

~~~sql
UPDATE orders
SET order_status = 'PROCESSING'
WHERE order_id = 500;
~~~

Sau đó gọi routine tự trị để ghi log. Routine tự trị không nhìn thấy thay đổi ORDER_STATUS chưa commit của transaction chính như một dữ liệu đã commit. Nó cũng không thể đọc một phiên bản dữ liệu chưa commit của caller.

Vì vậy, nếu logger cần biết thông tin về thao tác đang diễn ra, hãy truyền các giá trị cần ghi qua tham số:

~~~sql
write_event(
    p_event_name => 'ORDER_STATUS_ATTEMPT',
    p_detail     => 'order_id=500; new_status=PROCESSING'
);
~~~

Không yêu cầu logger tự query lại hàng chưa commit để lấy dữ liệu.

### 4.2. Transaction chính có thấy dữ liệu autonomous đã commit không?

Trong isolation level mặc định READ COMMITTED, sau khi autonomous routine commit và trả quyền điều khiển, các câu SQL tiếp theo của transaction chính có thể nhìn thấy dữ liệu đã commit đó.

Với SERIALIZABLE, transaction chính tiếp tục dùng snapshot của chính nó; thay đổi được autonomous transaction commit sau khi snapshot của transaction chính bắt đầu không trở nên nhìn thấy trong snapshot đó.

Điểm quan trọng: khả năng nhìn thấy phụ thuộc isolation level và thời điểm statement bắt đầu. Không thiết kế logic nghiệp vụ dựa trên giả định rằng mọi transaction chính đều lập tức nhìn thấy dòng log vừa commit.

### 4.3. Ma trận visibility

| Dữ liệu | Autonomous transaction nhìn thấy? | Transaction chính nhìn thấy? |
| --- | --- | --- |
| Dữ liệu đã commit trước khi autonomous query bắt đầu | Có, theo snapshot của nó | Có nếu thuộc snapshot của transaction chính |
| DML chưa commit của transaction chính | Không | Có trong chính transaction chính |
| DML autonomous đã commit | Có trong transaction tự trị | READ COMMITTED: câu SQL tiếp theo có thể thấy; SERIALIZABLE: snapshot hiện tại không thấy |
| DML autonomous chưa commit | Chỉ trong transaction tự trị | Không |
| DML transaction chính bị rollback | Không còn là dữ liệu đã commit | Không còn trong transaction chính sau rollback |

Dùng log như dữ liệu chẩn đoán, không dùng nó làm nguồn trạng thái chuẩn cho nghiệp vụ nếu hai transaction có thể mô tả các kết quả khác nhau.

## 5. Ghi log lỗi bằng autonomous transaction

Đây là use case phổ biến và hợp lý: khi một thao tác nghiệp vụ thất bại, hệ thống rollback dữ liệu chính nhưng vẫn giữ lại thông tin lỗi để điều tra.

### 5.1. Tạo bảng nhật ký

~~~sql
CREATE TABLE app_error_log (
    log_id             NUMBER PRIMARY KEY,
    logged_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    session_user_name  VARCHAR2(128),
    current_user_name  VARCHAR2(128),
    module_name        VARCHAR2(64),
    action_name        VARCHAR2(64),
    client_identifier  VARCHAR2(64),
    error_code         NUMBER,
    error_message      VARCHAR2(4000),
    error_stack        CLOB,
    error_backtrace    CLOB,
    context_text       CLOB
);

CREATE SEQUENCE app_error_log_seq;
~~~

Bảng log nên lưu các thông tin cần cho điều tra:

- Thời điểm xảy ra lỗi.
- User và ngữ cảnh ứng dụng.
- Module/action/client identifier nếu được thiết lập.
- SQLCODE và SQLERRM.
- Error stack và backtrace.
- Khóa nghiệp vụ hoặc correlation ID được truyền từ caller.

Không lưu quá nhiều dữ liệu nhạy cảm hoặc toàn bộ payload người dùng nếu không có yêu cầu và chính sách bảo vệ phù hợp.

### 5.2. Tạo routine logger

~~~sql
CREATE OR REPLACE PROCEDURE write_error_log (
    p_error_code      IN NUMBER,
    p_error_message   IN VARCHAR2,
    p_error_stack     IN VARCHAR2,
    p_error_backtrace IN VARCHAR2,
    p_context         IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO app_error_log (
        log_id,
        logged_at,
        session_user_name,
        current_user_name,
        module_name,
        action_name,
        client_identifier,
        error_code,
        error_message,
        error_stack,
        error_backtrace,
        context_text
    )
    VALUES (
        app_error_log_seq.NEXTVAL,
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER'),
        SYS_CONTEXT('USERENV', 'CURRENT_USER'),
        SYS_CONTEXT('USERENV', 'MODULE'),
        SYS_CONTEXT('USERENV', 'ACTION'),
        SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER'),
        p_error_code,
        SUBSTR(p_error_message, 1, 4000),
        p_error_stack,
        p_error_backtrace,
        p_context
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Logger commit ngay sau khi insert. Nếu insert log thất bại, nó rollback transaction riêng và báo lỗi cho caller. Caller cần quyết định cách xử lý lỗi logger mà không làm mất exception nghiệp vụ ban đầu.

Nếu logger thuộc schema khác, owner của logger cần quyền trực tiếp phù hợp trên bảng và sequence để compile static SQL. Ứng dụng chỉ nên được cấp EXECUTE trên API cần thiết.

### 5.3. Gọi logger trong exception handler

~~~sql
CREATE OR REPLACE PROCEDURE process_order (
    p_order_id IN NUMBER
)
AS
    l_error_code      NUMBER;
    l_error_message   VARCHAR2(4000);
    l_error_stack     VARCHAR2(4000);
    l_error_backtrace VARCHAR2(4000);
BEGIN
    UPDATE orders
    SET order_status = 'PROCESSING'
    WHERE order_id = p_order_id;

    -- Các bước xử lý nghiệp vụ khác.
    -- Nếu có lỗi, transaction caller có thể rollback.
EXCEPTION
    WHEN OTHERS THEN
        l_error_code := SQLCODE;
        l_error_message := SQLERRM;
        l_error_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_error_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        BEGIN
            write_error_log(
                p_error_code      => l_error_code,
                p_error_message   => l_error_message,
                p_error_stack     => l_error_stack,
                p_error_backtrace => l_error_backtrace,
                p_context         => 'order_id=' || p_order_id
            );
        EXCEPTION
            WHEN OTHERS THEN
                -- Không để lỗi ghi log che exception nghiệp vụ ban đầu.
                NULL;
        END;

        RAISE;
END;
/
~~~

Caller có thể bắt exception và rollback transaction nghiệp vụ theo chính sách của ứng dụng. Dòng log đã commit độc lập nên vẫn tồn tại.

### 5.4. Vì sao phải chụp SQLCODE và SQLERRM trước?

SQLCODE, SQLERRM, FORMAT_ERROR_STACK và FORMAT_ERROR_BACKTRACE cần được lấy ngay trong exception handler đang xử lý lỗi. Hãy lưu vào biến trước khi gọi logger hoặc routine khác để giữ đúng thông tin của exception gốc.

Lệnh RAISE không tham số trong exception handler cuối cùng ném lại exception đang được xử lý. Cách này giữ nguyên lỗi gốc thay vì thay bằng một lỗi mới do logging gây ra.

### 5.5. Logger có nên nuốt lỗi không?

Có hai chính sách thường gặp:

- **Best-effort logging:** nếu log thất bại, vẫn ưu tiên trả exception nghiệp vụ gốc. Caller bắt lỗi logger như ví dụ trên.
- **Logging bắt buộc:** nếu không ghi được log, ứng dụng không cho phép tiếp tục hoặc cần báo một lỗi vận hành riêng.

Chọn chính sách theo yêu cầu kiểm toán và vận hành. Với error logger thông thường, không nên để lỗi ghi log che mất lỗi gốc; đồng thời cần một kênh giám sát riêng để phát hiện logger không hoạt động.

## 6. Autonomous transaction trong trigger

Trigger thường chạy trong transaction kích hoạt DML. Nếu trigger ghi audit bằng DML thông thường, dòng audit thuộc cùng transaction với thay đổi bảng chính.

### 6.1. Audit cùng transaction

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_audit
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    INSERT INTO employee_audit (
        employee_id,
        old_salary,
        new_salary,
        changed_at
    )
    VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYSTIMESTAMP
    );
END;
/
~~~

Nếu UPDATE EMPLOYEES rollback, dòng EMPLOYEE_AUDIT cũng rollback. Khi transaction chính commit, cả thay đổi lương và audit cùng commit. Đây là lựa chọn phù hợp khi audit có nghĩa là “thay đổi đã được commit cùng transaction”.

### 6.2. Autonomous trigger ghi lần thử

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_attempt_log
AFTER UPDATE OF salary ON employees
FOR EACH ROW
DECLARE
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO employee_change_attempts (
        employee_id,
        old_salary,
        requested_salary,
        attempted_at
    )
    VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYSTIMESTAMP
    );

    COMMIT;
END;
/
~~~

Nếu transaction bên ngoài rollback, dòng EMPLOYEE_CHANGE_ATTEMPTS vẫn tồn tại. Đây là thông tin về lần thử thay đổi, không phải bằng chứng thay đổi đã thành công.

### 6.3. Chọn đúng ý nghĩa của log

| Yêu cầu | Cách ghi phù hợp |
| --- | --- |
| Ghi audit chỉ khi thay đổi nghiệp vụ commit | Trigger/DML thông thường trong transaction chính |
| Ghi lại lần thử, kể cả khi caller rollback | Autonomous transaction |
| Ghi exception để điều tra sau rollback | Autonomous logger |
| Ghi trạng thái nghiệp vụ chính thức | Transaction nghiệp vụ hoặc outbox được commit cùng nghiệp vụ |
| Ghi telemetry không ảnh hưởng giao dịch chính | Autonomous logger hoặc hệ thống telemetry riêng, theo chính sách mất dữ liệu |

Không dùng autonomous trigger để tạo một audit “đã thay đổi” nếu business DML có thể rollback sau khi trigger commit.

## 7. Rủi ro mất nhất quán

Autonomous transaction tạo ra hai lịch sử commit độc lập. Nếu không đặt tên sự kiện và mô hình dữ liệu đúng, người vận hành có thể hiểu nhầm log là trạng thái nghiệp vụ đã được xác nhận.

### 7.1. Log tồn tại nhưng nghiệp vụ rollback

Ví dụ:

1. Transaction chính trừ 100 khỏi tài khoản.
2. Logger autonomous ghi “đã trừ tiền” và commit.
3. Transaction chính gặp lỗi và rollback.
4. Số dư tài khoản không đổi nhưng log vẫn ghi đã trừ tiền.

Đây là sai lệch ngữ nghĩa. Có thể khắc phục bằng cách ghi DEBIT_ATTEMPT hoặc DEBIT_PROCESSING, thay vì DEBIT_COMMITTED.

### 7.2. Transaction chính commit nhưng log không ghi được

Chiều ngược lại cũng có thể xảy ra:

1. Transaction chính thực hiện nghiệp vụ.
2. Logger gặp lỗi như tablespace đầy, privilege thiếu hoặc lỗi constraint.
3. Ứng dụng chọn bỏ qua lỗi logger để bảo toàn exception/luồng nghiệp vụ.
4. Nghiệp vụ vẫn commit nhưng không có log.

Autonomous transaction không bảo đảm log luôn ghi thành công. Nó chỉ tách transaction. Cần giám sát lỗi logger, quyền, dung lượng và trạng thái bảng log.

Nếu audit là yêu cầu bắt buộc phải đồng bộ với commit nghiệp vụ, ghi audit trong cùng transaction hoặc dùng transactional outbox. Không dựa vào một autonomous logger best-effort để thay thế cơ chế audit bắt buộc.

### 7.3. Log không phải nguồn dữ liệu chuẩn

Không dùng bảng autonomous log để quyết định rằng một đơn hàng đã thanh toán, một tài khoản đã bị trừ tiền hoặc một hồ sơ đã được phê duyệt. Nguồn trạng thái chuẩn phải là dữ liệu nghiệp vụ đã commit hoặc event/outbox được commit cùng thay đổi đó.

### 7.4. Không tạo foreign key tới hàng chưa commit

Một lỗi phổ biến là logger insert vào bảng log có foreign key tới hàng mà transaction chính vừa tạo nhưng chưa commit. Autonomous transaction không nhìn thấy hàng chưa commit đó; việc kiểm tra foreign key có thể chờ khóa của transaction chính hoặc tạo deadlock.

Với error log/attempt log:

- Lưu business key như ORDER_ID hoặc ACCOUNT_ID dưới dạng giá trị tham chiếu, không nhất thiết tạo foreign key.
- Nếu cần foreign key thật, chỉ ghi tham chiếu tới hàng đã commit và tồn tại độc lập.
- Không yêu cầu logger đọc lại dữ liệu chưa commit của caller.

### 7.5. Deadlock giữa autonomous và transaction chính

Transaction chính bị tạm dừng khi gọi routine tự trị nhưng vẫn giữ các lock đã lấy. Nếu autonomous transaction cố truy cập hàng hoặc tài nguyên đang bị transaction chính khóa, nó có thể chờ chính transaction đang tạm dừng. Kết quả có thể là deadlock.

Ví dụ rủi ro:

~~~sql
-- Transaction chính đã khóa hàng này.
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Routine autonomous lại UPDATE cùng hàng.
write_account_log_and_update(10);
~~~

Không để routine tự trị cập nhật cùng hàng nghiệp vụ mà caller đang giữ lock. Logger nên ghi vào bảng log độc lập và tránh đọc/ghi các tài nguyên mà transaction chính đang giữ.

### 7.6. Trigger autonomous truy vấn bảng đang thay đổi

Một trigger tự trị vẫn có thể gặp deadlock nếu cố truy cập tài nguyên đang bị câu lệnh kích hoạt trigger khóa. Đặc biệt, không thiết kế trigger tự trị để query lại bảng đang được thay đổi hoặc chờ các row lock của chính transaction gọi trigger.

Nếu trigger chỉ cần ghi thông tin từ hàng, truyền giá trị qua :OLD và :NEW vào bảng log độc lập; không query lại hàng chưa commit.

## 8. Autonomous transaction và lock

Transaction tự trị có thể truy cập bảng khác, nhưng không được coi là có thể dùng mọi tài nguyên của transaction chính.

Các nguyên tắc:

- Transaction chính bị suspend nhưng lock của nó vẫn được giữ.
- Autonomous transaction không thừa hưởng lock của transaction chính.
- Autonomous transaction có thể bị block khi truy cập hàng đang bị parent lock.
- Parent không thể tiếp tục để giải phóng lock cho đến khi autonomous routine trả quyền điều khiển.
- Tình huống này có thể tạo deadlock.

Thiết kế logger chỉ INSERT vào bảng log độc lập, dùng sequence riêng và tránh foreign key tới hàng chưa commit. Tránh cập nhật bảng nghiệp vụ, bảng cha/con đang bị khóa hoặc bảng cấu hình mà transaction chính đang giữ lock.

## 9. Transaction isolation và khả năng đọc log

Oracle mặc định dùng READ COMMITTED. Trong mức này, mỗi statement nhìn thấy dữ liệu đã commit trước thời điểm statement bắt đầu. Sau khi routine autonomous commit, statement tiếp theo của parent có thể nhìn thấy log mới.

Trong SERIALIZABLE, transaction chính giữ snapshot nhất quán của transaction. Dữ liệu autonomous commit sau thời điểm snapshot được thiết lập không nhất thiết xuất hiện trong snapshot đó.

Điều này quan trọng nếu code chính định đọc lại log ngay sau khi gọi logger để ra quyết định nghiệp vụ. Đừng giả định mọi isolation level có cùng visibility.

Nếu cần truyền kết quả logger về caller, hãy trả log ID hoặc giá trị cần thiết qua OUT parameter. Đừng buộc caller query lại một bảng log để lấy giá trị mà logger vừa tạo.

## 10. Lỗi và lưu ý vận hành

### 10.1. ORA-06519

Nguyên nhân: routine autonomous kết thúc khi transaction tự trị vẫn active.

Cách xử lý:

- COMMIT khi ghi log thành công.
- ROLLBACK khi xử lý thất bại.
- Kiểm tra mọi nhánh IF và exception.
- Không để một helper được gọi bên trong routine tự trị mở transaction rồi bỏ quên.

### 10.2. ORA-00060 hoặc chờ khóa

Nguyên nhân có thể là autonomous transaction truy cập tài nguyên bị parent transaction khóa.

Cách xử lý:

- Tách bảng log khỏi bảng nghiệp vụ.
- Không update cùng hàng mà caller đang khóa.
- Không tạo foreign key tới dữ liệu chưa commit.
- Rà soát call stack và lock graph nếu có deadlock.

### 10.3. Logger lỗi làm che lỗi gốc

Nguyên nhân: exception khi INSERT log thay thế exception nghiệp vụ đang xử lý.

Cách xử lý:

- Lưu SQLCODE, SQLERRM và backtrace trước khi gọi logger.
- Bắt riêng exception của logger.
- Giữ lại và RAISE exception nghiệp vụ gốc.
- Theo dõi lỗi logger qua metric hoặc kênh vận hành khác.

### 10.4. Log tăng không giới hạn

Error logging có thể tạo lượng DML lớn. Cần:

- Partition/retention bảng log khi khối lượng phù hợp.
- Index vừa đủ cho truy vấn điều tra.
- Archive hoặc purge theo chính sách.
- Giới hạn kích thước context và payload.
- Tránh ghi toàn bộ dữ liệu nhạy cảm.
- Theo dõi tablespace, redo, undo và tốc độ tăng dữ liệu.

### 10.5. Commit quá thường xuyên

Autonomous logger thường commit từng lần gọi. Với tần suất rất cao, commit và redo có thể tạo chi phí đáng kể. Nếu logging volume lớn, cân nhắc batch/queue/telemetry chuyên dụng. Tuy nhiên, batch có thể làm thay đổi cam kết “log phải tồn tại ngay lập tức sau mỗi lần gọi”; phải cân bằng yêu cầu độ bền với throughput.

## 11. Ví dụ so sánh: audit cùng transaction và autonomous log

### 11.1. Tạo bảng lab

~~~sql
CREATE TABLE lab_accounts (
    account_id NUMBER PRIMARY KEY,
    balance NUMBER(12, 2) NOT NULL
);

INSERT INTO lab_accounts VALUES (10, 1000);
COMMIT;

CREATE TABLE lab_event_log (
    log_id NUMBER PRIMARY KEY,
    event_name VARCHAR2(40) NOT NULL,
    account_id NUMBER NOT NULL,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL,
    detail VARCHAR2(200)
);

CREATE SEQUENCE lab_event_log_seq;

CREATE TABLE lab_business_audit (
    account_id NUMBER NOT NULL,
    event_name VARCHAR2(40) NOT NULL,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Trong LAB_EVENT_LOG cố ý không khai báo foreign key tới LAB_ACCOUNTS. Điều này giúp log attempt có thể lưu ngay cả khi transaction chính đang tạo hoặc cập nhật hàng chưa commit.

### 11.2. Tạo autonomous logger

~~~sql
CREATE OR REPLACE PROCEDURE lab_log_event (
    p_event_name IN VARCHAR2,
    p_account_id IN NUMBER,
    p_detail IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO lab_event_log (
        log_id,
        event_name,
        account_id,
        event_time,
        detail
    )
    VALUES (
        lab_event_log_seq.NEXTVAL,
        p_event_name,
        p_account_id,
        SYSTIMESTAMP,
        p_detail
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

### 11.3. Thử rollback transaction chính

~~~sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    lab_log_event(
        p_event_name => 'DEBIT_ATTEMPT',
        p_account_id => 10,
        p_detail => 'Requested debit amount=100'
    );

    ROLLBACK;
END;
/
~~~

Kiểm tra:

~~~sql
SELECT account_id, balance
FROM lab_accounts
WHERE account_id = 10;

SELECT log_id, event_name, account_id, detail
FROM lab_event_log
ORDER BY log_id;
~~~

Kết quả mong đợi:

- BALANCE vẫn là 1000 vì transaction chính rollback.
- LAB_EVENT_LOG có dòng DEBIT_ATTEMPT vì routine tự trị đã commit.

Đây là hành vi đúng nếu yêu cầu là ghi lại lần thử debit. Nếu gọi dòng log là DEBIT_SUCCESS, dữ liệu sẽ gây hiểu nhầm.

### 11.4. So sánh audit cùng transaction

~~~sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    INSERT INTO lab_business_audit (
        account_id,
        event_name,
        event_time
    )
    VALUES (
        10,
        'DEBIT',
        SYSTIMESTAMP
    );

    ROLLBACK;
END;
/
~~~

Kiểm tra:

~~~sql
SELECT COUNT(*) AS audit_rows
FROM lab_business_audit
WHERE account_id = 10;
~~~

Kết quả là 0 vì audit thuộc transaction chính và cùng rollback với UPDATE.

### 11.5. Thử commit transaction chính

~~~sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    INSERT INTO lab_business_audit (
        account_id,
        event_name,
        event_time
    )
    VALUES (
        10,
        'DEBIT',
        SYSTIMESTAMP
    );

    lab_log_event(
        p_event_name => 'DEBIT_ATTEMPT',
        p_account_id => 10,
        p_detail => 'Debit request processed'
    );

    COMMIT;
END;
/
~~~

Sau COMMIT:

- Balance giảm còn 900.
- Audit nghiệp vụ và thay đổi balance cùng commit.
- Autonomous event log cũng đã commit riêng.

Lab này minh họa rằng hai bảng log có thể mang hai ngữ nghĩa khác nhau: audit giao dịch đã commit và log lần thử. Hãy đặt tên event/table để người đọc không nhầm lẫn.

## 12. Thiết kế bảng log và chính sách dữ liệu

Một bảng log tốt cần phục vụ điều tra mà không trở thành bản sao không kiểm soát của dữ liệu nghiệp vụ.

### 12.1. Các trường thường hữu ích

| Trường | Mục đích |
| --- | --- |
| LOG_ID | Khóa duy nhất của log |
| LOGGED_AT | Thời điểm ghi log |
| SESSION_USER_NAME | User đăng nhập |
| CURRENT_USER_NAME | User hiện tại trong privilege context |
| MODULE_NAME/ACTION_NAME | Nhận diện luồng ứng dụng |
| CLIENT_IDENTIFIER | Nhận diện người dùng hoặc request |
| ERROR_CODE | Mã lỗi Oracle/ứng dụng |
| ERROR_MESSAGE | Nội dung lỗi rút gọn |
| ERROR_STACK | Chuỗi lỗi |
| ERROR_BACKTRACE | Vị trí phát sinh lỗi |
| CONTEXT_TEXT | Correlation ID hoặc khóa nghiệp vụ |

Có thể dùng DBMS_APPLICATION_INFO để thiết lập MODULE/ACTION và DBMS_SESSION.SET_IDENTIFIER để gán CLIENT_IDENTIFIER trước khi thực hiện nghiệp vụ. Logger đọc các giá trị này bằng SYS_CONTEXT.

### 12.2. Correlation ID

Một request có thể đi qua nhiều procedure, trigger và service. Truyền correlation ID xuyên suốt call chain giúp gom log mà không phải dựa vào timestamp gần nhau.

Correlation ID là dữ liệu định danh của request, không phải khóa ngoại bắt buộc. Với autonomous logger, có thể lưu nó như một chuỗi ngay cả khi hàng nghiệp vụ liên quan chưa commit.

### 12.3. Retention và phân quyền

- Chỉ cấp quyền INSERT/EXECUTE cần thiết cho logger.
- Giới hạn SELECT trên bảng log cho nhóm vận hành phù hợp.
- Không để user ứng dụng sửa/xóa log đã ghi nếu yêu cầu audit cần tính toàn vẹn.
- Định nghĩa retention và archive.
- Giám sát lỗi insert, dung lượng tablespace và tốc độ tăng.
- Tuân thủ chính sách dữ liệu cá nhân và thông tin nhạy cảm.

## 13. Khi nào không nên dùng autonomous transaction?

Không dùng nó trong các trường hợp sau nếu không có yêu cầu độc lập rõ ràng:

- Ghi audit thành công phải rollback cùng thay đổi nghiệp vụ.
- Cập nhật lại hàng mà transaction chính đang giữ lock.
- Dựa vào dữ liệu chưa commit của caller.
- Dùng làm cách né lỗi mutating table mà không hiểu lock và consistency.
- Thay thế transaction boundary của tầng service.
- Commit từng bước trong một quy trình nghiệp vụ vốn cần atomicity.
- Ghi trạng thái “đã hoàn tất” trước khi transaction chính thực sự commit.

Nếu cần gửi sự kiện chỉ sau khi giao dịch commit, cân nhắc transactional outbox: ghi business data và outbox row trong cùng transaction, rồi worker riêng phát event sau commit. Cách này giữ quan hệ nhất quán giữa nghiệp vụ và event cần phát.

## 14. Quy trình điều tra khi log và dữ liệu chính lệch nhau

Khi phát hiện log ghi một hành động nhưng bảng nghiệp vụ không có thay đổi tương ứng, hãy xác định ngữ nghĩa của log trước.

1. Xác định routine/trigger nào có PRAGMA AUTONOMOUS_TRANSACTION.
2. Xác định log được ghi trước hay sau bước nghiệp vụ nào.
3. Kiểm tra routine có COMMIT trước khi caller kết thúc không.
4. Kiểm tra transaction chính có ROLLBACK, exception hoặc timeout không.
5. Xác định log biểu thị ATTEMPT, ERROR, PROCESSING hay COMMITTED.
6. Kiểm tra autonomous routine có đọc dữ liệu chưa commit hoặc foreign key tới hàng chưa commit không.
7. Kiểm tra lock/deadlock và call stack.
8. Đối chiếu isolation level nếu parent query không nhìn thấy log mới.
9. Xác định logger có thể thất bại độc lập và cách ứng dụng xử lý lỗi logger.
10. Sửa tên event, contract và transaction design để phản ánh đúng ý nghĩa.

Đừng xóa dòng log chỉ vì nó không có business row tương ứng. Nếu đó là log attempt hoặc error, việc không có business commit chính là thông tin cần giữ.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ORA-06519 khi routine kết thúc | Autonomous transaction chưa COMMIT/ROLLBACK | Đóng transaction trên mọi nhánh |
| Log vẫn tồn tại sau caller ROLLBACK | Logger đã COMMIT transaction riêng | Đây là hành vi dự kiến; đặt tên log là attempt/error nếu phù hợp |
| Audit ghi thành công nhưng business row không đổi | Autonomous audit commit trước transaction chính | Dùng audit cùng transaction hoặc transactional outbox |
| Autonomous routine bị treo hoặc deadlock | Đụng resource parent đang khóa | Tách log table và tránh truy cập hàng bị khóa |
| Logger không thấy row vừa INSERT | Row của parent chưa commit | Truyền dữ liệu qua tham số; không query row chưa commit |
| Insert log bị chờ ở foreign key | FK tham chiếu hàng chưa commit của parent | Tránh FK tới dữ liệu chưa commit trong attempt/error log |
| Logger lỗi làm che lỗi gốc | Exception logger thay thế exception nghiệp vụ | Bắt riêng lỗi logger rồi RAISE lại lỗi gốc |
| Parent không thấy log mới ngay | SERIALIZABLE snapshot hoặc statement đã mở trước đó | Hiểu isolation/statement snapshot; không dùng query lại log làm API trả kết quả |
| Trigger log thay đổi đã rollback | Trigger autonomous commit độc lập | Phân biệt ATTEMPT với COMMITTED |
| Log tăng quá nhanh | Mỗi lỗi/trigger tạo transaction và redo riêng | Giới hạn dữ liệu, retention, partition và giám sát |
| Tưởng pragma làm procedure có session mới | Nhầm transaction context với session | Nhớ rằng session vẫn là session caller |
| Dùng autonomous để né commit boundary | Transaction ownership không rõ | Để tầng service sở hữu commit/rollback nghiệp vụ |

## 16. Bài tập thực hành

Sử dụng các bảng LAB_ACCOUNTS, LAB_EVENT_LOG và LAB_BUSINESS_AUDIT trong mục 11.

### Bài 1 — Transaction độc lập

Tạo procedure có PRAGMA AUTONOMOUS_TRANSACTION, insert một dòng log và commit. Gọi nó giữa một UPDATE và ROLLBACK của caller. Quan sát hai bảng.

### Bài 2 — Bỏ quên COMMIT

Tạo một autonomous procedure chỉ INSERT mà không commit/rollback. Gọi procedure và quan sát ORA-06519. Giải thích transaction tự trị đã được xử lý như thế nào khi routine kết thúc.

### Bài 3 — Logger có exception handler

Tạo logger rollback khi insert thất bại và re-raise lỗi. Trong caller, bắt riêng lỗi logger để giữ exception nghiệp vụ gốc. Kiểm tra lỗi nào được trả về client.

### Bài 4 — Audit cùng transaction

Viết trigger audit thông thường và autonomous trigger trên hai bảng lab riêng. Thực hiện DML rồi rollback. So sánh số dòng audit.

### Bài 5 — Rủi ro foreign key

Trong lab, thử thiết kế log table có foreign key tới hàng được transaction chính tạo nhưng chưa commit. Quan sát chờ khóa hoặc deadlock. Sau đó thay foreign key bằng business key lưu dạng scalar.

### Bài 6 — Rủi ro lock

Trong session chính, khóa một hàng. Gọi autonomous routine cố cập nhật cùng hàng đó. Quan sát tình huống chờ/deadlock và giải thích vì sao parent không thể tiếp tục để nhả lock trong khi routine tự trị chưa kết thúc.

### Bài 7 — READ COMMITTED và SERIALIZABLE

Thiết lập hai tình huống isolation phù hợp trong môi trường lab. Gọi autonomous logger rồi truy vấn log từ parent. So sánh khả năng nhìn thấy dòng vừa commit theo snapshot.

### Bài 8 — Phân loại event

Thiết kế tên event và cột trạng thái cho ba trường hợp: thao tác được thử, thao tác thất bại, và thao tác đã commit. Xác định trường hợp nào dùng autonomous transaction và trường hợp nào ghi cùng transaction chính.

## 17. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
DROP PROCEDURE lab_log_event;
DROP TABLE lab_business_audit PURGE;
DROP TABLE lab_event_log PURGE;
DROP SEQUENCE lab_event_log_seq;
DROP TABLE lab_accounts PURGE;
~~~

Nếu tạo thêm trigger hoặc routine trong các bài tập, drop đúng các object lab đó trước khi xóa bảng. Không chạy lệnh dọn dẹp trên dữ liệu nghiệp vụ.

## Tổng kết

PRAGMA AUTONOMOUS_TRANSACTION tạo một transaction độc lập trong cùng session. Transaction chính bị tạm dừng khi routine tự trị chạy; COMMIT/ROLLBACK bên trong routine chỉ tác động transaction riêng. Routine phải kết thúc với transaction tự trị đã được commit hoặc rollback, nếu không có thể phát sinh ORA-06519.

Cơ chế này phù hợp để ghi error log hoặc attempt log cần tồn tại dù transaction nghiệp vụ rollback. Nó không phù hợp để ghi audit “đã commit” nếu audit phải nhất quán với thay đổi chính. Transaction tự trị không thấy DML chưa commit của caller và có thể deadlock khi truy cập resource mà caller đang khóa. Hãy truyền context qua tham số, dùng bảng log độc lập, tránh foreign key tới hàng chưa commit, giữ exception gốc và đặt tên event đúng ngữ nghĩa. Nếu cần event chỉ phát ra sau khi business commit, dùng audit cùng transaction hoặc transactional outbox.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — Autonomous Transactions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/autonomous-transactions.html) — pragma, transaction context, commit và rollback.
- [Oracle Database PL/SQL Language Reference — AUTONOMOUS_TRANSACTION Pragma (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/AUTONOMOUS_TRANSACTION-pragma.html) — vị trí khai báo và hành vi pragma.
- [Oracle Database PL/SQL Language Reference — Exception Handlers (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/exception-handling.html) — xử lý exception và RAISE.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_UTILITY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_UTILITY.html) — FORMAT_ERROR_STACK và FORMAT_ERROR_BACKTRACE.
- [Oracle Database Concepts — Data Concurrency and Consistency (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html) — read consistency, isolation và locking.
- [Oracle Database PL/SQL Language Reference — Triggers (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/triggers.html) — trigger và transaction behavior.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu PL/SQL Language Reference và Database Concepts đúng phiên bản, đặc biệt visibility theo isolation level, hành vi trigger, lock/deadlock và lỗi khi autonomous transaction chưa kết thúc.
