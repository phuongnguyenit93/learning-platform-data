# DBMS_APPLICATION_INFO để gắn module/action cho phiên ứng dụng

Trong một database có nhiều ứng dụng, service và connection pool, chỉ nhìn SQL text hoặc database username thường chưa đủ để biết một session đang phục vụ chức năng nghiệp vụ nào. Một user có thể được dùng chung cho nhiều module của cùng ứng dụng; một connection vật lý cũng có thể lần lượt xử lý nhiều request của các end users khác nhau. Khi cần tìm nguyên nhân một chức năng chậm, DBA cần biết SQL đang được chạy từ module nào và đang thực hiện action nào.

Oracle cung cấp package **DBMS_APPLICATION_INFO** để ứng dụng gắn nhãn cho session. Hai thuộc tính chính là **MODULE** và **ACTION**. MODULE mô tả vùng chức năng hoặc thành phần ứng dụng, còn ACTION mô tả công việc hiện tại bên trong module. Oracle ghi nhận các thuộc tính này trong các dynamic performance views như V$SESSION và V$SQLAREA, đồng thời dùng chúng làm tiêu chí cho thống kê và SQL trace qua DBMS_MONITOR.

Ví dụ, một hệ thống bán hàng có thể đặt MODULE = ORDER_API và ACTION lần lượt là VALIDATE_ORDER, RESERVE_STOCK, CREATE_INVOICE. Khi session chạy chậm, DBA có thể tìm các session hoặc SQL thuộc đúng module/action thay vì phải suy luận từ username, hostname hoặc SQL text.

Bài học thuộc nhóm **Vận hành** của Database Engine Relational Oracle. Nội dung tập trung vào DBMS_APPLICATION_INFO, cách đặt và xóa MODULE/ACTION, phân biệt CLIENT_INFO với CLIENT_IDENTIFIER, đọc metadata trong dynamic performance views, tích hợp với connection pool, thống kê và trace theo service/module/action bằng DBMS_MONITOR, theo dõi long operations, bảo mật và quy trình vận hành.

Sau bài này, bạn có thể:

- Giải thích MODULE và ACTION đại diện cho điều gì trong một session.
- Dùng SET_MODULE, SET_ACTION, READ_MODULE và READ_CLIENT_INFO.
- Xóa nhãn cũ để không gán nhầm workload cho request tiếp theo.
- Hiểu giới hạn độ dài module/action và tham số LONG_MODULE_ACTION.
- Phân biệt MODULE/ACTION, CLIENT_INFO và CLIENT_IDENTIFIER.
- Truy vấn V$SESSION, V$SQLAREA, V$SQL và V$ACTIVE_SESSION_HISTORY để quan sát ứng dụng.
- Tích hợp module/action vào PL/SQL procedure và ứng dụng Java/JDBC.
- Reset session state đúng cách khi dùng connection pool.
- Bật thống kê theo service/module/action bằng DBMS_MONITOR.
- Bật SQL trace có phạm vi hẹp và tắt trace sau khi điều tra.
- Dùng SET_SESSION_LONGOPS để hiển thị tiến độ công việc dài.
- Tránh dùng application metadata như một cơ chế xác thực hoặc phân quyền.

> **Phạm vi ví dụ:** Các ví dụ chủ yếu theo Oracle Database 19c. Một số view yêu cầu quyền đọc dynamic performance views; các API DBMS_MONITOR cần quyền quản trị phù hợp. Kiểm tra release/RU, cấu hình RAC/PDB và quyền thực tế trước khi áp dụng.

## 1. Vì sao cần gắn module/action cho session?

Một ứng dụng thường có nhiều luồng nghiệp vụ cùng kết nối database:

- API tạo đơn hàng.
- API tra cứu đơn hàng.
- Quy trình thanh toán.
- Batch đồng bộ kho.
- Báo cáo doanh thu.
- Job gửi thông báo.

Nếu tất cả kết nối dùng cùng một database user, DBA nhìn V$SESSION có thể thấy nhiều session cùng USERNAME. Nếu chỉ nhìn SQL text, rất khó phân biệt request nào đang chạy ở bước nghiệp vụ nào.

### 1.1. Không chỉ database username

Ví dụ:

| Database user | Ứng dụng | Module | Action |
| --- | --- | --- | --- |
| APP_RUNTIME | Sales API | ORDER_API | CREATE_ORDER |
| APP_RUNTIME | Sales API | ORDER_API | GET_ORDER |
| APP_RUNTIME | Sales API | PAYMENT_API | AUTHORIZE_PAYMENT |
| APP_RUNTIME | Inventory batch | INVENTORY_JOB | SYNC_STOCK |
| APP_RUNTIME | Reporting | REPORT_API | MONTHLY_REVENUE |

Tất cả có thể kết nối bằng APP_RUNTIME, nhưng module/action cho phép phân loại workload rõ ràng.

### 1.2. Lợi ích vận hành

- Tìm session đang thực hiện một chức năng cụ thể.
- Phân tích SQL tiêu tốn tài nguyên theo module.
- Thu thập thống kê theo service/module/action.
- Bật SQL trace cho một action gặp lỗi hiệu năng.
- Đối chiếu request ở application log với hoạt động trong database.
- Phân biệt workload OLTP, batch và reporting khi chúng dùng chung schema.

### 1.3. End-to-end application tracing

Oracle gọi cách theo dõi xuyên các tầng ứng dụng là end-to-end application tracing. Các tiêu chí có thể dùng gồm:

- Client identifier: nhận diện end user hoặc client logic.
- Service: nhóm workload được kết nối qua database service.
- Module: vùng chức năng trong ứng dụng.
- Action: thao tác đang thực hiện trong module.
- Session: session database cụ thể.
- Instance: database instance cụ thể.
- Container: PDB/container trong môi trường multitenant.

MODULE/ACTION là metadata do ứng dụng đặt. Chúng giúp DBA hiểu session đang làm gì, nhưng không tự động chứng minh danh tính người dùng hoặc quyền truy cập dữ liệu.

## 2. DBMS_APPLICATION_INFO là gì?

DBMS_APPLICATION_INFO là package PL/SQL do Oracle cung cấp để ghi nhận tên module, action và thông tin bổ sung của ứng dụng vào session.

### 2.1. Các procedure chính

| Procedure | Mục đích |
| --- | --- |
| SET_MODULE | Đặt MODULE và ACTION cùng lúc |
| SET_ACTION | Thay ACTION trong MODULE hiện tại |
| READ_MODULE | Đọc MODULE và ACTION hiện tại |
| SET_CLIENT_INFO | Ghi thông tin bổ sung vào CLIENT_INFO |
| READ_CLIENT_INFO | Đọc CLIENT_INFO hiện tại |
| SET_SESSION_LONGOPS | Ghi tiến độ operation dài vào V$SESSION_LONGOPS |

### 2.2. Quyền thực thi

Trong cài đặt Oracle chuẩn, DBMS_APPLICATION_INFO đã được cài đặt và public synonym được cung cấp. Tài liệu Oracle 19c nêu rằng ứng dụng không cần privilege bổ sung để gọi package này.

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CREATE_ORDER'
    );
END;
/
~~~

Không cần cấp DBA role cho ứng dụng chỉ để đặt module/action.

### 2.3. Không phải một bảng log nghiệp vụ

DBMS_APPLICATION_INFO ghi metadata của session/cursor để phục vụ quan sát và tracing. Nó không tự ghi từng bước nghiệp vụ vào bảng audit của ứng dụng, không lưu request body và không thay thế application logging.

## 3. MODULE và ACTION

### 3.1. MODULE là vùng chức năng

MODULE nên mô tả thành phần tương đối ổn định của ứng dụng:

- ORDER_API
- PAYMENT_API
- INVENTORY_JOB
- CUSTOMER_PORTAL
- REPORTING_SERVICE

Không nên đặt module thành một giá trị duy nhất cho từng request nếu mục tiêu là thống kê tổng hợp. Module có quá nhiều giá trị riêng lẻ sẽ làm việc phân tích theo nhóm kém hiệu quả.

### 3.2. ACTION là công việc hiện tại

ACTION mô tả bước hoặc transaction đang thực hiện:

- CREATE_ORDER
- VALIDATE_ADDRESS
- RESERVE_STOCK
- AUTHORIZE_PAYMENT
- LOAD_MONTHLY_REPORT
- SEND_NOTIFICATION

Một module có thể lần lượt chạy nhiều action. Ví dụ:

~~~text
MODULE = ORDER_API
    ACTION = VALIDATE_ORDER
    ACTION = RESERVE_STOCK
    ACTION = WRITE_ORDER
    ACTION = PUBLISH_EVENT
~~~

### 3.3. MODULE và ACTION không phải SQL operation

MODULE/ACTION do ứng dụng định nghĩa. Oracle không bắt buộc ACTION phải là SELECT, INSERT hoặc UPDATE. Có thể đặt tên theo nghiệp vụ để người vận hành dễ hiểu.

Ví dụ ORDER_API / AUTHORIZE_CARD hữu ích hơn MODULE1 / STEP3.

### 3.4. Chọn tên có quy ước

Nên thống nhất:

- Dùng chữ hoa và dấu gạch dưới để dễ lọc.
- Giữ module ổn định qua các phiên bản ứng dụng.
- Dùng action mô tả một bước nghiệp vụ rõ ràng.
- Tránh đưa timestamp, UUID hoặc request ID vào module/action.
- Không dùng dữ liệu nhạy cảm như email, số tài khoản, token hoặc access key.
- Dùng client identifier hoặc application log correlation ID cho định danh request/người dùng.

### 3.5. Giới hạn độ dài

Đây là điểm cần chú ý vì tài liệu package và cấu hình database có thể thể hiện các giới hạn khác nhau.

| Cấu hình/version | MODULE | ACTION |
| --- | ---: | ---: |
| Trước Oracle 12.2 | 48 bytes | 32 bytes |
| Oracle 12.2 trở lên, LONG_MODULE_ACTION = FALSE | 48 bytes | 32 bytes |
| Oracle 12.2 trở lên, LONG_MODULE_ACTION = TRUE | 64 bytes | 64 bytes |

Trong Oracle 19c, LONG_MODULE_ACTION có giá trị mặc định TRUE. V$SESSION.MODULE và V$SESSION.ACTION đều có kiểu VARCHAR2(64).

Kiểm tra:

~~~sql
SHOW PARAMETER long_module_action
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'long_module_action';
~~~

LONG_MODULE_ACTION có thể thay đổi bằng ALTER SYSTEM và có thể điều chỉnh trong PDB. Trong Oracle RAC, cùng một giá trị phải được sử dụng trên tất cả instance.

Ví dụ:

~~~sql
ALTER SYSTEM SET long_module_action = TRUE;
~~~

Chỉ thay đổi tham số này khi có kế hoạch cấu hình thống nhất cho môi trường. Không dựa vào việc chuỗi dài được truncate mà không kiểm tra; hai module/action khác nhau có thể bị cắt thành cùng một prefix.

### 3.6. Độ dài tính theo byte

Oracle mô tả giới hạn module/action theo bytes. Với chuỗi UTF-8, một ký tự có thể chiếm nhiều byte. Vì vậy, một tên tiếng Việt có thể đạt giới hạn byte trước khi đạt số ký tự dự kiến.

Để tránh truncate khó phát hiện và giảm khác biệt giữa client/database character sets, nên dùng nhãn ngắn, ổn định, thường là ASCII.

## 4. SET_MODULE

SET_MODULE đặt module hiện tại và action hiện tại trong một lần gọi.

### 4.1. Cú pháp

~~~sql
DBMS_APPLICATION_INFO.SET_MODULE(
    module_name IN VARCHAR2,
    action_name IN VARCHAR2
);
~~~

### 4.2. Đặt module và action

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CREATE_ORDER'
    );
END;
/
~~~

Sau đó, V$SESSION có thể hiển thị MODULE = ORDER_API và ACTION = CREATE_ORDER.

### 4.3. Đổi sang module khác

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'PAYMENT_API',
        action_name => 'AUTHORIZE_PAYMENT'
    );
END;
/
~~~

SET_MODULE thay cả hai thuộc tính. Nếu muốn giữ module và chỉ đổi action, dùng SET_ACTION.

### 4.4. Xóa module/action

Khi module hiện tại kết thúc:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
~~~

Oracle khuyến nghị đặt module/action mới khi ứng dụng bước vào module mới, và đặt NULL khi module kết thúc nếu không còn module tiếp theo.

### 4.5. SET_MODULE không commit transaction

SET_MODULE chỉ thay metadata session. Nó không COMMIT, ROLLBACK hoặc thay đổi transaction data. Có thể gọi trước transaction, trong transaction hoặc khi chuẩn bị thực hiện một bước nghiệp vụ.

## 5. SET_ACTION

SET_ACTION chỉ thay ACTION của module hiện tại.

### 5.1. Cú pháp

~~~sql
DBMS_APPLICATION_INFO.SET_ACTION(
    action_name IN VARCHAR2
);
~~~

### 5.2. Chuyển action trong cùng module

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        'ORDER_API',
        'VALIDATE_ORDER'
    );

    -- Validate dữ liệu đầu vào.

    DBMS_APPLICATION_INFO.SET_ACTION('RESERVE_STOCK');

    -- Gọi logic giữ hàng.

    DBMS_APPLICATION_INFO.SET_ACTION('WRITE_ORDER');

    -- Ghi đơn hàng.

    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
END;
/
~~~

MODULE vẫn là ORDER_API trong khi ACTION thay đổi qua từng bước.

### 5.3. Xóa action

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
END;
/
~~~

Nên xóa action khi bước nghiệp vụ kết thúc. Nếu không, session có thể tiếp tục hiển thị action cũ khi thực hiện call tiếp theo.

### 5.4. Đặt action trước transaction

Oracle khuyến nghị ứng dụng đặt action trước khi bắt đầu transaction. Điều này giúp thống kê theo service/module/action gắn với đúng bước công việc.

### 5.5. Action mới có thể chỉ được phản ánh ở call kế tiếp trong thống kê tổng hợp

Khi DBMS_MONITOR thu thập thống kê theo module/action, thay đổi module/action trong một user call được áp dụng cho call kế tiếp. Vì vậy, call đang thực hiện SET_ACTION có thể vẫn được tính vào action cũ; các call sau mới được tính vào action mới.

Đây là chi tiết quan trọng khi so sánh số liệu chính xác theo từng bước.

## 6. READ_MODULE và READ_CLIENT_INFO

Có thể đọc lại metadata hiện tại trong chính session.

### 6.1. READ_MODULE

~~~sql
DECLARE
    l_module VARCHAR2(64);
    l_action VARCHAR2(64);
BEGIN
    DBMS_APPLICATION_INFO.READ_MODULE(
        module_name => l_module,
        action_name => l_action
    );

    DBMS_OUTPUT.PUT_LINE('MODULE=' || NVL(l_module, '<NULL>'));
    DBMS_OUTPUT.PUT_LINE('ACTION=' || NVL(l_action, '<NULL>'));
END;
/
~~~

READ_MODULE trả giá trị gần nhất được đặt bằng SET_MODULE/SET_ACTION trong session hiện tại.

### 6.2. READ_CLIENT_INFO

~~~sql
DECLARE
    l_client_info VARCHAR2(64);
BEGIN
    DBMS_APPLICATION_INFO.READ_CLIENT_INFO(
        client_info => l_client_info
    );

    DBMS_OUTPUT.PUT_LINE(
        'CLIENT_INFO=' || NVL(l_client_info, '<NULL>')
    );
END;
/
~~~

### 6.3. Kiểm tra metadata bằng SYS_CONTEXT

Có thể đọc một số session attributes qua SYS_CONTEXT:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'MODULE') AS module_name,
    SYS_CONTEXT('USERENV', 'ACTION') AS action_name,
    SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER') AS client_identifier
FROM dual;
~~~

SYS_CONTEXT thuận tiện khi PL/SQL cần đọc metadata session trong SQL expression.

## 7. CLIENT_INFO khác CLIENT_IDENTIFIER

Hai thuộc tính này có tên gần nhau nhưng mục tiêu khác nhau.

### 7.1. CLIENT_INFO

SET_CLIENT_INFO ghi thông tin bổ sung của client:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_CLIENT_INFO(
        'web-node-03;release-2026.11'
    );
END;
/
~~~

Giá trị được lưu trong V$SESSION.CLIENT_INFO. Oracle 19c giới hạn CLIENT_INFO ở 64 bytes; dữ liệu dài hơn bị truncate.

Đọc lại:

~~~sql
DECLARE
    l_info VARCHAR2(64);
BEGIN
    DBMS_APPLICATION_INFO.READ_CLIENT_INFO(l_info);
    DBMS_OUTPUT.PUT_LINE(l_info);
END;
/
~~~

CLIENT_INFO có thể được đọc và ghi bởi bất kỳ user nào. Không dùng nó để lưu thông tin bí mật hoặc làm bằng chứng xác thực.

### 7.2. CLIENT_IDENTIFIER

CLIENT_IDENTIFIER nhận diện end user/client logic trong môi trường nhiều tầng. Ví dụ:

- USER-10027
- CUSTOMER-501
- API-REQUEST-8F3A

Đặt bằng DBMS_SESSION:

~~~sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('CUSTOMER-501');
END;
/
~~~

Giá trị có thể đọc trong V$SESSION.CLIENT_IDENTIFIER hoặc:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER')
FROM dual;
~~~

DBMS_SESSION.SET_IDENTIFIER hỗ trợ tối đa 64 bytes. Client identifier phân biệt chữ hoa/chữ thường.

### 7.3. Xóa client identifier

~~~sql
BEGIN
    DBMS_SESSION.CLEAR_IDENTIFIER;
END;
/
~~~

### 7.4. So sánh

| Thuộc tính | Mục đích | API | View phổ biến |
| --- | --- | --- | --- |
| MODULE | Thành phần ứng dụng | DBMS_APPLICATION_INFO.SET_MODULE | V$SESSION.MODULE |
| ACTION | Bước nghiệp vụ hiện tại | DBMS_APPLICATION_INFO.SET_ACTION | V$SESSION.ACTION |
| CLIENT_INFO | Thông tin bổ sung về client | DBMS_APPLICATION_INFO.SET_CLIENT_INFO | V$SESSION.CLIENT_INFO |
| CLIENT_IDENTIFIER | Nhận diện end user/client logic | DBMS_SESSION.SET_IDENTIFIER | V$SESSION.CLIENT_IDENTIFIER |
| SERVICE_NAME | Database service mà session kết nối | Client/service configuration | V$SESSION.SERVICE_NAME |

### 7.5. Không dùng CLIENT_INFO để thay CLIENT_IDENTIFIER

CLIENT_IDENTIFIER được Oracle dùng trực tiếp trong end-to-end tracing, client statistics và một số cơ chế security/auditing. CLIENT_INFO là trường bổ sung tự do.

Nếu cần gắn user logic từ middle tier, dùng SET_IDENTIFIER và quy trình tin cậy ở tầng ứng dụng. Nếu cần bảo vệ thuộc tính dùng cho authorization, dùng secure application context được thiết lập bởi trusted package; không tin giá trị do client tùy ý truyền.

### 7.6. Không nhầm metadata với danh tính đã xác thực

Các API này được thiết kế để ứng dụng gắn nhãn session. Một database user có thể gọi các API và tự đặt giá trị. Do đó:

- Không cấp quyền truy cập dữ liệu chỉ dựa vào MODULE/ACTION.
- Không coi CLIENT_IDENTIFIER là bằng chứng mật khẩu/MFA đã được xác thực.
- Không đưa secret, token, password hoặc dữ liệu nhạy cảm vào metadata.
- Dùng application context, VPD/RLS, database privileges và authentication thực sự cho security enforcement.

## 8. Quan sát MODULE/ACTION trong V$SESSION

V$SESSION hiển thị session hiện tại, bao gồm module, action, client info và client identifier.

### 8.1. Tìm session theo module

~~~sql
SELECT
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier,
    client_info,
    status,
    sql_id,
    sql_exec_start,
    last_call_et
FROM v$session
WHERE module = 'ORDER_API'
ORDER BY logon_time;
~~~

### 8.2. Tìm một action cụ thể

~~~sql
SELECT
    sid,
    serial#,
    username,
    module,
    action,
    status,
    event,
    wait_class,
    sql_id
FROM v$session
WHERE module = 'ORDER_API'
  AND action = 'RESERVE_STOCK';
~~~

### 8.3. Tìm session của một client identifier

~~~sql
SELECT
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier,
    status,
    machine,
    program
FROM v$session
WHERE client_identifier = 'CUSTOMER-501';
~~~

### 8.4. V$SESSION là trạng thái hiện tại

V$SESSION cho biết metadata của session hiện tại. Nếu ứng dụng đã reset module/action, giá trị cũ không còn nằm ở session đó. Muốn phân tích lịch sử, cần dùng SQL trace, thống kê tổng hợp hoặc repository lịch sử được cấu hình phù hợp.

### 8.5. Trạng thái ACTIVE và INACTIVE

- ACTIVE: session hiện đang thực thi database call.
- INACTIVE: session không có call đang chạy.

MODULE/ACTION có thể vẫn giữ giá trị cuối cùng dù session đang INACTIVE. Vì vậy, thấy ACTION = CREATE_ORDER không có nghĩa query CREATE_ORDER đang chạy ngay thời điểm đọc view; hãy xem STATUS, SQL_ID và SQL_EXEC_START.

## 9. Quan sát SQL theo module/action

Oracle ghi module/action cùng thông tin SQL vào các view cursor như V$SQLAREA và V$SQL.

### 9.1. V$SQLAREA

~~~sql
SELECT
    sql_id,
    module,
    action,
    executions,
    elapsed_time,
    cpu_time,
    buffer_gets,
    disk_reads,
    rows_processed,
    sql_text
FROM v$sqlarea
WHERE module = 'ORDER_API'
ORDER BY elapsed_time DESC;
~~~

### 9.2. V$SQL

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    module,
    action,
    executions,
    elapsed_time,
    cpu_time,
    buffer_gets,
    disk_reads
FROM v$sql
WHERE module = 'ORDER_API'
  AND action = 'CREATE_ORDER'
ORDER BY elapsed_time DESC;
~~~

### 9.3. Cumulative statistics

Các số liệu trong V$SQL/V$SQLAREA thường là số liệu tích lũy của cursor trong shared pool. Không so sánh tổng elapsed_time giữa hai module nếu số executions và tuổi đời cursor khác nhau.

Có thể tính trung bình tham khảo:

~~~sql
SELECT
    module,
    action,
    SUM(executions) AS executions,
    ROUND(
        SUM(elapsed_time) /
        NULLIF(SUM(executions), 0) / 1e6,
        4
    ) AS avg_elapsed_seconds,
    ROUND(
        SUM(cpu_time) /
        NULLIF(SUM(executions), 0) / 1e6,
        4
    ) AS avg_cpu_seconds,
    ROUND(
        SUM(buffer_gets) /
        NULLIF(SUM(executions), 0),
        2
    ) AS avg_buffer_gets
FROM v$sql
WHERE module = 'ORDER_API'
GROUP BY module, action
ORDER BY avg_elapsed_seconds DESC;
~~~

Average không thể hiện percentile hoặc phân phối latency. Dùng application metrics hoặc tracing khi cần p95/p99.

### 9.4. SQL text có thể bị cắt ngắn

V$SQLAREA.SQL_TEXT có giới hạn hiển thị. Với câu SQL dài, dùng SQL_FULLTEXT hoặc SQL_ID để lấy nội dung chi tiết theo quyền và release.

## 10. Gắn module/action trong PL/SQL

Một stored procedure có thể tự đặt module/action khi bắt đầu xử lý.

### 10.1. Ví dụ procedure đơn giản

~~~sql
CREATE OR REPLACE PROCEDURE create_order_lab (
    p_customer_id IN NUMBER
)
IS
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CREATE_ORDER'
    );

    DBMS_APPLICATION_INFO.SET_ACTION('VALIDATE_CUSTOMER');
    -- Kiểm tra customer.

    DBMS_APPLICATION_INFO.SET_ACTION('WRITE_ORDER');
    -- Ghi đơn hàng.

    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
        RAISE;
END;
/
~~~

Ví dụ minh họa cách đặt metadata. Trong code thật, cần bảo đảm cleanup được thực hiện cả khi validation hoặc DML phát sinh exception.

### 10.2. Tách phần xử lý và cleanup

Có thể đặt logic nghiệp vụ trong nested block để cleanup ở cả đường thành công và lỗi:

~~~sql
CREATE OR REPLACE PROCEDURE process_order_lab (
    p_order_id IN NUMBER
)
IS
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        'ORDER_API',
        'PROCESS_ORDER'
    );

    BEGIN
        DBMS_APPLICATION_INFO.SET_ACTION('LOAD_ORDER');
        -- SELECT thông tin đơn hàng.

        DBMS_APPLICATION_INFO.SET_ACTION('RESERVE_STOCK');
        -- Gọi logic giữ hàng.

        DBMS_APPLICATION_INFO.SET_ACTION('UPDATE_STATUS');
        -- Cập nhật trạng thái.

    EXCEPTION
        WHEN OTHERS THEN
            DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
            RAISE;
    END;

    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
~~~

Trong hệ thống lớn, có thể xây dựng helper/wrapper để giảm việc lặp cleanup. Không nuốt exception chỉ để reset metadata.

### 10.3. Không để action cũ tồn tại

Nếu một procedure chỉ gọi SET_ACTION ở nhánh thành công, action có thể bị giữ lại khi exception. Dùng cleanup trong exception handler hoặc một cơ chế finally ở application layer.

### 10.4. Nested procedures

Nếu procedure A gọi B, cần quy ước ai sở hữu module/action:

- Module cấp cao có thể đại diện toàn API.
- Action được cập nhật theo bước hiện tại.
- Procedure con không nên tùy tiện reset module của caller.
- Nếu procedure con thay module, phải khôi phục giá trị caller sau khi kết thúc.

Một convention rõ ràng giúp metadata không bị ghi đè khó dự đoán.

## 11. Tích hợp trong ứng dụng Java/JDBC

Ứng dụng Java có thể gọi DBMS_APPLICATION_INFO qua PL/SQL anonymous block hoặc stored procedure.

### 11.1. Đặt module/action và client identifier

Ví dụ dùng JDBC CallableStatement:

~~~java
String sql = """
    BEGIN
      DBMS_APPLICATION_INFO.SET_MODULE(?, ?);
      DBMS_SESSION.SET_IDENTIFIER(?);
    END;
    """;

try (CallableStatement call = connection.prepareCall(sql)) {
    call.setString(1, "ORDER_API");
    call.setString(2, "CREATE_ORDER");
    call.setString(3, "CUSTOMER-501");
    call.execute();
}
~~~

Đây là ví dụ khái niệm. Dùng cùng connection vật lý sẽ thực hiện nghiệp vụ tiếp theo; không mở một connection khác chỉ để đặt metadata.

### 11.2. Đổi action giữa các bước

~~~java
try (CallableStatement call =
         connection.prepareCall(
             "BEGIN DBMS_APPLICATION_INFO.SET_ACTION(?); END;")) {
    call.setString(1, "RESERVE_STOCK");
    call.execute();
}
~~~

### 11.3. Reset trước khi trả connection về pool

~~~java
String resetSql = """
    BEGIN
      DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
      DBMS_APPLICATION_INFO.SET_CLIENT_INFO(NULL);
      DBMS_SESSION.CLEAR_IDENTIFIER;
    END;
    """;

try (CallableStatement reset = connection.prepareCall(resetSql)) {
    reset.execute();
}
~~~

Đặt đoạn reset trong finally hoặc connection cleanup hook của pool. Nếu reset thất bại, cần loại connection khỏi pool thay vì trả về pool với metadata của request cũ.

### 11.4. Không tạo một connection chỉ để đặt tag

Module/action là state của database session. Phải đặt trên chính session chạy SQL nghiệp vụ. Nếu gọi SET_MODULE qua connection A nhưng query chạy trên connection B, query không nhận tag của A.

## 12. Connection pool và session state

Đây là nơi dễ phát sinh lỗi gắn nhãn nhất.

### 12.1. Session vật lý được tái sử dụng

Một connection pool có thể giữ 20 session database mở. Request đầu tiên mượn session số 1, đặt MODULE = ORDER_API và ACTION = CREATE_ORDER. Sau khi request trả connection về pool, session database vẫn tồn tại.

Nếu request tiếp theo mượn lại session đó mà không reset metadata, nó có thể tiếp tục hiển thị ORDER_API/CREATE_ORDER dù đang phục vụ báo cáo hoặc chức năng khác.

### 12.2. Vòng đời khuyến nghị

~~~text
Application request
        |
        v
Borrow connection from pool
        |
        v
Set CLIENT_IDENTIFIER
Set MODULE and ACTION
        |
        v
Execute business SQL
Update ACTION as work changes
        |
        v
Clear MODULE/ACTION and CLIENT_IDENTIFIER
        |
        v
Return clean connection to pool
~~~

### 12.3. Đặt metadata ở mỗi lần checkout

Không chỉ đặt module/action lúc connection được tạo lần đầu. Một physical session có thể phục vụ nhiều request và nhiều end users. Đặt lại metadata mỗi lần checkout hoặc ở request boundary phù hợp.

### 12.4. Reset ở cả success và exception

Nếu application code chỉ reset sau khi query thành công, lỗi timeout hoặc exception có thể để metadata cũ trong session. Dùng finally, interceptor hoặc pool callback để cleanup.

### 12.5. Pool reset và transaction state

Reset metadata không thay thế việc quản lý transaction:

- Commit/rollback theo transaction boundary.
- Trả connection về pool khi transaction đã kết thúc.
- Không để transaction mở khi connection idle trong pool.
- Reset session attributes theo chính sách của pool.

### 12.6. Module/action có thể tồn tại khi session idle

V$SESSION hiển thị module/action gần nhất được đặt cho session. Một session INACTIVE có thể vẫn giữ module/action của request trước đó. Đây là lý do cần reset trước khi trả connection về pool.

## 13. DBMS_MONITOR: thống kê theo service/module/action

DBMS_APPLICATION_INFO gắn nhãn. DBMS_MONITOR dùng nhãn đó để bật thu thập thống kê hoặc SQL trace theo workload cụ thể.

### 13.1. SERV_MOD_ACT_STAT_ENABLE

Cú pháp:

~~~sql
DBMS_MONITOR.SERV_MOD_ACT_STAT_ENABLE(
    service_name IN VARCHAR2,
    module_name  IN VARCHAR2,
    action_name  IN VARCHAR2 DEFAULT ALL_ACTIONS
);
~~~

Ví dụ bật thống kê cho action tạo đơn hàng:

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_STAT_ENABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER'
    );
END;
/
~~~

Nếu bỏ action_name hoặc dùng DBMS_MONITOR.ALL_ACTIONS, Oracle thu thập thống kê cho tất cả action trong module.

### 13.2. ALL_ACTIONS khác NULL

Oracle dùng một hằng đặc biệt DBMS_MONITOR.ALL_ACTIONS để chỉ tất cả actions trong module. NULL/chuỗi rỗng được dùng để chỉ action rỗng. Không thay ALL_ACTIONS bằng NULL nếu mục tiêu là gom mọi action.

### 13.3. Xem thống kê

V$SERV_MOD_ACT_STATS hiển thị thống kê cho service/module/action đã bật aggregation:

~~~sql
SELECT
    service_name,
    module,
    action,
    stat_name,
    value
FROM v$serv_mod_act_stats
WHERE service_name = 'SALES_APP'
  AND module = 'ORDER_API'
ORDER BY action, stat_name;
~~~

View này cung cấp các số liệu về thời gian và công việc đã thực hiện cho business transaction. VALUE là số liệu tích lũy theo statistic; nhiều statistic thời gian được biểu diễn bằng microseconds.

### 13.4. Xem aggregation đã bật

~~~sql
SELECT
    aggregation_type,
    primary_id AS service_name,
    qualifier_id1 AS module_name,
    qualifier_id2 AS action_name
FROM dba_enabled_aggregations
WHERE aggregation_type LIKE 'SERVICE_MODULE%';
~~~

DBA_ENABLED_AGGREGATIONS cho biết các aggregation rules đang được bật.

### 13.5. Tắt thống kê

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_STAT_DISABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER'
    );
END;
/
~~~

Theo tài liệu Oracle, thao tác disable loại bỏ dữ liệu tích lũy tương ứng khỏi V$SERV_MOD_ACT_STATS. Nếu cần giữ kết quả phân tích, hãy xuất/lưu số liệu trước khi disable.

### 13.6. Tính chất persistent

Statistics aggregation theo service/module/action được cấu hình ở phạm vi database và tồn tại qua instance restart. Trong RAC, cấu hình áp dụng cho các instance của cùng database.

### 13.7. Thay đổi action có hiệu lực ở call kế tiếp

Khi ứng dụng đổi module/action trong một user call, thống kê của call hiện tại vẫn có thể được tính theo giá trị cũ. Giá trị mới được dùng từ user call kế tiếp. Hãy lưu ý khi đối chiếu chính xác số liệu transaction.

## 14. DBMS_MONITOR: SQL trace theo module/action

Khi một module/action có vấn đề, có thể bật SQL trace đúng phạm vi thay vì trace toàn database.

### 14.1. Bật trace

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_ENABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER',
        waits        => TRUE,
        binds        => FALSE
    );
END;
/
~~~

Tham số:

- service_name: database service.
- module_name: module cần trace.
- action_name: action cần trace; có thể dùng hằng wildcard theo API.
- waits: có đưa wait information vào trace hay không.
- binds: có đưa bind values vào trace hay không.
- instance_name: có thể giới hạn trace vào một instance.
- plan_stat: tần suất ghi row source statistics theo lựa chọn được hỗ trợ.

### 14.2. Vì sao mặc định nên cẩn thận với binds?

Bind values có thể chứa thông tin nhạy cảm như customer ID, account number hoặc dữ liệu nghiệp vụ. Bật binds có thể làm dữ liệu đó xuất hiện trong trace files. Chỉ bật khi thật sự cần, có kiểm soát quyền truy cập và thời hạn lưu.

### 14.3. Trace có phạm vi database

SERV_MOD_ACT_TRACE_ENABLE bật trace cho tổ hợp service/module/action trên database, trừ khi giới hạn instance_name. Trong RAC, trace có thể phát sinh trên nhiều instance và nhiều trace files.

### 14.4. Tắt trace

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_DISABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER'
    );
END;
/
~~~

Luôn ghi nhận thao tác bật và tắt trace. Không để tracing rộng tồn tại sau khi hoàn tất điều tra.

### 14.5. Tổng hợp trace files

Trace của cùng một module/action có thể nằm trong nhiều trace files, nhất là khi nhiều shadow processes phục vụ workload. Dùng TRCSESS để gom trace theo tiêu chí phù hợp, sau đó dùng TKPROF để định dạng và phân tích.

### 14.6. SQL trace có overhead

Trace tạo dữ liệu trên filesystem và có thể ảnh hưởng hiệu năng. Chọn module/action cụ thể, thời gian ngắn và tắt sau khi thu đủ dữ liệu. Tránh bật trace toàn database chỉ vì chưa gắn nhãn workload.

## 15. CLIENT_IDENTIFIER và DBMS_MONITOR

Nếu cần theo dõi end user qua nhiều database sessions, client identifier có thể phù hợp hơn module/action.

### 15.1. Thống kê theo client

~~~sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_STAT_ENABLE(
        client_id => 'CUSTOMER-501'
    );
END;
/
~~~

Thống kê có thể xem trong V$CLIENT_STATS.

### 15.2. Trace theo client identifier

~~~sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE(
        client_id => 'CUSTOMER-501',
        waits     => TRUE,
        binds     => FALSE
    );
END;
/
~~~

Tắt:

~~~sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_TRACE_DISABLE(
        client_id => 'CUSTOMER-501'
    );
END;
/
~~~

### 15.3. Khi nào dùng tiêu chí nào?

| Mục tiêu | Tiêu chí phù hợp |
| --- | --- |
| Tìm mọi request thuộc chức năng tạo đơn hàng | Service + MODULE + ACTION |
| Tìm mọi hoạt động của một end user | CLIENT_IDENTIFIER |
| Tìm một database connection cụ thể | SID + SERIAL# |
| Tìm workload thuộc ứng dụng/service | SERVICE_NAME |
| Tìm SQL của một bước nghiệp vụ | MODULE + ACTION |

Có thể kết hợp nhiều tiêu chí trong cùng một chiến lược tracing.

## 16. SET_SESSION_LONGOPS: hiển thị tiến độ công việc dài

DBMS_APPLICATION_INFO còn có SET_SESSION_LONGOPS để ứng dụng báo tiến độ của operation dài vào V$SESSION_LONGOPS.

### 16.1. Mục đích

Ví dụ:

- Import hàng triệu bản ghi.
- Đồng bộ dữ liệu nhiều bảng.
- Xử lý file lớn theo batch.
- Tính toán lại dữ liệu theo từng partition.
- Chạy quy trình nghiệp vụ dài có số lượng đơn vị công việc ước lượng được.

Ứng dụng cập nhật SOFAR và TOTALWORK để DBA biết công việc đã hoàn thành bao nhiêu.

### 16.2. Cú pháp chính

~~~sql
DBMS_APPLICATION_INFO.SET_SESSION_LONGOPS(
    rindex      IN OUT BINARY_INTEGER,
    slno        IN OUT BINARY_INTEGER,
    op_name     IN VARCHAR2 DEFAULT NULL,
    target      IN BINARY_INTEGER DEFAULT 0,
    context     IN BINARY_INTEGER DEFAULT 0,
    sofar       IN NUMBER DEFAULT 0,
    totalwork   IN NUMBER DEFAULT 0,
    target_desc IN VARCHAR2 DEFAULT 'unknown target',
    units       IN VARCHAR2 DEFAULT NULL
);
~~~

### 16.3. Ví dụ cập nhật tiến độ

~~~sql
DECLARE
    l_rindex   BINARY_INTEGER;
    l_slno     BINARY_INTEGER;
    l_total    PLS_INTEGER := 100;
BEGIN
    l_rindex := DBMS_APPLICATION_INFO.SET_SESSION_LONGOPS_NOHINT;

    DBMS_APPLICATION_INFO.SET_MODULE(
        'INVENTORY_JOB',
        'SYNC_STOCK'
    );

    FOR i IN 1 .. l_total LOOP
        -- Xử lý một batch hoặc một nhóm bản ghi.

        DBMS_APPLICATION_INFO.SET_SESSION_LONGOPS(
            rindex      => l_rindex,
            slno        => l_slno,
            op_name     => 'SYNC_STOCK',
            sofar       => i,
            totalwork   => l_total,
            target_desc => 'inventory batches',
            units       => 'batches'
        );
    END LOOP;

    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
~~~

Trong code thực tế, chỉ cập nhật progress theo batch hoặc theo khoảng thời gian hợp lý. Không gọi SET_SESSION_LONGOPS quá dày trong một vòng lặp hàng triệu phần tử nếu không cần thiết.

### 16.4. Các trường quan trọng

| Trường | Ý nghĩa |
| --- | --- |
| OPNAME | Tên operation |
| TARGET_DESC | Mô tả đối tượng đang xử lý |
| SOFAR | Công việc đã hoàn thành |
| TOTALWORK | Tổng công việc ước tính |
| UNITS | Đơn vị của sofar/totalwork |
| ELAPSED_SECONDS | Thời gian đã chạy |
| TIME_REMAINING | Thời gian còn lại ước tính |

### 16.5. Truy vấn V$SESSION_LONGOPS

~~~sql
SELECT
    sid,
    serial#,
    opname,
    target_desc,
    sofar,
    totalwork,
    units,
    elapsed_seconds,
    time_remaining,
    message
FROM v$session_longops
WHERE sofar < totalwork
ORDER BY start_time DESC;
~~~

Một số operation do Oracle tự quản lý cũng xuất hiện trong view này, không chỉ operation do ứng dụng tạo.

## 17. MODULE/ACTION trong RAC và multitenant

### 17.1. Oracle RAC

Mỗi session tồn tại trên một instance tại một thời điểm. Để tìm session trên toàn RAC, dùng GV$SESSION:

~~~sql
SELECT
    inst_id,
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier,
    status,
    sql_id
FROM gv$session
WHERE module = 'ORDER_API'
ORDER BY inst_id, sid;
~~~

DBMS_MONITOR service/module/action tracing có thể áp dụng trên mọi instance của database; có thể giới hạn bằng instance_name nếu cần.

### 17.2. LONG_MODULE_ACTION trong RAC

Nếu dùng LONG_MODULE_ACTION, Oracle yêu cầu cùng giá trị trên mọi instance. Không để một node dùng TRUE và node khác dùng FALSE, vì module/action có thể bị truncate khác nhau.

### 17.3. CDB/PDB

Trong multitenant database, session có container context. Khi phân tích workload, nên lấy CON_ID hoặc container name nếu view hỗ trợ:

~~~sql
SELECT
    con_id,
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier
FROM v$session
WHERE module = 'ORDER_API';
~~~

Module/action là session metadata, còn service và container giúp xác định database service/PDB mà session đang dùng.

### 17.4. Service name không phải module

Service định tuyến và nhóm workload ở cấp database service. Module/action mô tả chức năng và thao tác bên trong ứng dụng. Một service có thể phục vụ nhiều module; một module có thể có nhiều action.

## 18. Quan sát lịch sử qua ASH/AWR

V$ACTIVE_SESSION_HISTORY lưu mẫu session active và bao gồm module, action, client identifier. Điều này giúp xem workload theo thời gian thay vì chỉ trạng thái hiện tại.

### 18.1. Xem mẫu ASH trong memory

~~~sql
SELECT
    sample_time,
    session_id,
    session_serial#,
    sql_id,
    module,
    action,
    client_id,
    event,
    wait_class
FROM v$active_session_history
WHERE module = 'ORDER_API'
  AND sample_time >= SYSTIMESTAMP - INTERVAL '30' MINUTE
ORDER BY sample_time DESC;
~~~

### 18.2. ASH chỉ lấy mẫu session active

ASH không ghi mọi trạng thái idle và không phải audit log đầy đủ cho mọi request. Một thao tác rất ngắn có thể không xuất hiện trong mẫu. Dùng application log và transaction metrics để bổ sung.

### 18.3. AWR historical ASH

DBA_HIST_ACTIVE_SESS_HISTORY cung cấp lịch sử ASH đã được lưu theo cơ chế AWR:

~~~sql
SELECT
    sample_time,
    sql_id,
    module,
    action,
    client_id,
    event,
    wait_class
FROM dba_hist_active_sess_history
WHERE module = 'ORDER_API'
ORDER BY sample_time DESC;
~~~

AWR/ASH historical data và các công cụ liên quan có thể yêu cầu Oracle Diagnostics Pack. Xác nhận license của tổ chức trước khi dùng các view/feature yêu cầu pack. Nếu không có license, dùng V$SESSION, V$SQL, SQL Trace/TKPROF và application telemetry theo quyền được phép.

## 19. Thiết kế naming convention và correlation

Một quy ước metadata tốt giúp truy vấn và thống kê có giá trị lâu dài.

### 19.1. Gợi ý cấu trúc

| Thuộc tính | Ví dụ | Đặc điểm |
| --- | --- | --- |
| SERVICE_NAME | SALES_APP | Nhóm workload/điểm kết nối |
| MODULE | ORDER_API | Thành phần chức năng ổn định |
| ACTION | CREATE_ORDER | Bước nghiệp vụ hiện tại |
| CLIENT_IDENTIFIER | USER-10027 | End user/client logic |
| CLIENT_INFO | node-03;release-2026.11 | Metadata phụ, không nhạy cảm |

### 19.2. Tránh high cardinality ở module/action

Không đặt request UUID, timestamp hoặc customer ID vào module/action. Nếu mỗi request tạo một action riêng, thống kê tổng hợp theo action sẽ phân mảnh và khó phân tích.

Dùng CLIENT_IDENTIFIER cho user/client, và correlation ID trong application logs hoặc tracing system nếu cần định danh từng request.

### 19.3. Đồng bộ với application logs

Application log có thể ghi:

- Request/correlation ID.
- Module và action.
- Client identifier.
- Database service.
- Thời điểm mượn/trả connection.
- SQL_ID nếu được thu thập.

Khi điều tra, DBA có thể nối metadata database với log của application theo module/action/client identifier và thời gian.

### 19.4. Tránh đưa dữ liệu nhạy cảm vào metadata

MODULE/ACTION/CLIENT_INFO/CLIENT_IDENTIFIER có thể hiển thị cho người có quyền đọc các view liên quan và có thể xuất hiện trong trace/monitoring. Chỉ lưu nhãn vận hành cần thiết, không lưu:

- Password hoặc token.
- Số thẻ thanh toán.
- Email/địa chỉ đầy đủ nếu không cần.
- Nội dung request/response.
- Secret của ứng dụng.

## 20. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| MODULE/ACTION là NULL | Ứng dụng chưa gọi SET_MODULE/SET_ACTION hoặc đã reset | Kiểm tra request lifecycle và điểm đặt tag |
| Module/action bị truncate | Vượt giới hạn byte hoặc LONG_MODULE_ACTION khác nhau | Kiểm tra parameter và độ dài byte |
| Query hiển thị module của request trước | Connection pool tái sử dụng session nhưng không reset | Đặt metadata mỗi checkout và clear trước khi trả pool |
| Action không đổi trong thống kê call hiện tại | DBMS_MONITOR áp dụng giá trị mới từ user call kế tiếp | Tính đến boundary của call khi đối chiếu |
| V$SESSION có module nhưng V$SQLAREA không như mong đợi | SQL cursor được parse dưới context khác hoặc dữ liệu cursor thay đổi | Kiểm tra V$SQL, SQL_ID, child và thời điểm parse |
| SERV_MOD_ACT_STATS không có dữ liệu | Chưa bật aggregation hoặc module/action/service không khớp | Kiểm tra DBA_ENABLED_AGGREGATIONS và nhãn thực tế |
| Không trace được action | Sai service/module/action hoặc trace đã bị disable | Xác nhận V$SESSION, API parameters và instance |
| Trace files nằm nhiều nơi | Nhiều shadow processes/instances | Dùng TRCSESS để gom |
| Client identifier không đúng | Chưa gọi SET_IDENTIFIER hoặc pool không clear | Đặt/clear ở request boundary |
| CLIENT_INFO bị xem như thông tin bảo mật | Trường này có thể đọc/ghi bởi user | Dùng secure application context cho security attributes |
| Longops không có tiến độ | Không gọi SET_SESSION_LONGOPS hoặc progress update không đúng | Kiểm tra rindex/slno/sofar/totalwork và view |
| GV$SESSION thiếu session | Quyền/view/container filter chưa phù hợp | Kiểm tra quyền và instance/container |

## 21. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| MODULE là database username | MODULE là nhãn do ứng dụng đặt |
| ACTION chỉ nhận SELECT/INSERT/UPDATE | ACTION là tên nghiệp vụ tùy ứng dụng |
| SET_ACTION thay đổi MODULE | SET_ACTION chỉ đổi ACTION |
| SET_MODULE chỉ đổi MODULE | SET_MODULE đặt cả MODULE và ACTION |
| MODULE/ACTION tự reset sau COMMIT | Chúng là session metadata và có thể còn tồn tại |
| CLIENT_INFO và CLIENT_IDENTIFIER giống nhau | Mục tiêu và API khác nhau |
| CLIENT_INFO an toàn để lưu token | CLIENT_INFO đọc/ghi được bởi user; không lưu secret |
| CLIENT_IDENTIFIER là danh tính đã được database xác thực | Nó là nhãn client do ứng dụng đặt |
| Mọi phiên bản đều giới hạn module 48/action 32 | 12.2+ có LONG_MODULE_ACTION, mặc định TRUE cho phép 64/64 |
| V$SESSION chỉ có module khi session ACTIVE | Session INACTIVE có thể vẫn giữ module/action cuối |
| DBMS_APPLICATION_INFO tự bật SQL trace | Nó gắn nhãn; DBMS_MONITOR bật statistics/trace |
| DBMS_MONITOR trace chỉ một session | Service/module/action trace có thể áp dụng toàn database hoặc instance |
| ASH là log đầy đủ mọi request | ASH lấy mẫu session active |
| SET_SESSION_LONGOPS tự chạy công việc | Nó chỉ công bố tiến độ do ứng dụng cập nhật |
| Reset metadata thay thế rollback transaction | Hai việc độc lập |

## 22. Checklist triển khai DBMS_APPLICATION_INFO

**Thiết kế nhãn**

- Module có đại diện cho thành phần chức năng ổn định không?
- Action có mô tả bước nghiệp vụ hiện tại không?
- Có tránh UUID, timestamp và high cardinality không?
- Tên có nằm trong giới hạn byte của database không?
- LONG_MODULE_ACTION có thống nhất trên RAC không?

**Tích hợp ứng dụng**

- Đặt module/action trên đúng physical database connection?
- Đổi action khi bước nghiệp vụ thay đổi?
- Reset metadata trong cả success và exception?
- Connection pool có cleanup trước khi trả session không?
- Client identifier có được set/clear ở request boundary không?

**Quan sát**

- V$SESSION hiển thị module/action đúng?
- V$SQL/V$SQLAREA có thể phân tích SQL theo module/action?
- DBMS_MONITOR aggregation có bật đúng service/module/action?
- Có biết cách disable aggregation/trace không?
- Có giữ trace files theo retention và access policy không?

**Bảo mật và vận hành**

- Không lưu secret hoặc dữ liệu nhạy cảm trong metadata?
- Không dùng module/action làm authorization?
- Bind tracing chỉ bật khi cần và được kiểm soát?
- Có kiểm tra quyền trên dynamic performance views?
- Có tính đến RAC, PDB và service routing?

## 23. Bài thực hành tổng hợp

Lab tạo một session có module/action, kiểm tra V$SESSION và bật thống kê theo service/module/action. Chạy trong schema lab có quyền phù hợp.

### Bước 1 — Đặt module/action

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'CREATE_ORDER'
    );

    DBMS_SESSION.SET_IDENTIFIER('LAB-USER-01');
    DBMS_APPLICATION_INFO.SET_CLIENT_INFO('lab-node-01');
END;
/
~~~

### Bước 2 — Kiểm tra session metadata

~~~sql
SELECT
    sid,
    serial#,
    username,
    service_name,
    module,
    action,
    client_identifier,
    client_info,
    status
FROM v$session
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

### Bước 3 — Đổi action

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION('RESERVE_STOCK');
END;
/
~~~

Kiểm tra lại V$SESSION và quan sát ACTION.

### Bước 4 — Đọc bằng READ_MODULE

~~~sql
DECLARE
    l_module VARCHAR2(64);
    l_action VARCHAR2(64);
BEGIN
    DBMS_APPLICATION_INFO.READ_MODULE(l_module, l_action);
    DBMS_OUTPUT.PUT_LINE('MODULE=' || l_module);
    DBMS_OUTPUT.PUT_LINE('ACTION=' || l_action);
END;
/
~~~

### Bước 5 — Bật statistics aggregation

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_STAT_ENABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'RESERVE_STOCK'
    );
END;
/
~~~

Thay SALES_APP bằng service name thực tế của lab.

### Bước 6 — Chạy SQL dưới action đã gắn

~~~sql
SELECT COUNT(*)
FROM user_objects;
~~~

Chạy một vài lần để tạo hoạt động cho session.

### Bước 7 — Xem thống kê module/action

~~~sql
SELECT
    service_name,
    module,
    action,
    stat_name,
    value
FROM v$serv_mod_act_stats
WHERE service_name = 'SALES_APP'
  AND module = 'ORDER_API'
ORDER BY stat_name;
~~~

### Bước 8 — Tắt aggregation

~~~sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_STAT_DISABLE(
        service_name => 'SALES_APP',
        module_name  => 'ORDER_API',
        action_name  => 'RESERVE_STOCK'
    );
END;
/
~~~

### Bước 9 — Reset session metadata

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
    DBMS_APPLICATION_INFO.SET_CLIENT_INFO(NULL);
    DBMS_SESSION.CLEAR_IDENTIFIER;
END;
/
~~~

### Bước 10 — Xác nhận đã reset

~~~sql
SELECT
    module,
    action,
    client_info,
    client_identifier
FROM v$session
WHERE sid = SYS_CONTEXT('USERENV', 'SID');
~~~

Các giá trị phải trở về NULL sau khi cleanup.

## 24. Câu hỏi tự kiểm tra

1. DBMS_APPLICATION_INFO dùng để làm gì?
2. MODULE và ACTION khác nhau thế nào?
3. SET_MODULE đặt những thuộc tính nào?
4. SET_ACTION có thay module không?
5. READ_MODULE trả về những gì?
6. Khi nào nên đặt ACTION?
7. Vì sao cần reset module/action?
8. Giới hạn module/action mặc định của Oracle 19c là bao nhiêu?
9. LONG_MODULE_ACTION = FALSE thay đổi giới hạn thế nào?
10. Độ dài module/action tính theo ký tự hay byte?
11. CLIENT_INFO khác CLIENT_IDENTIFIER thế nào?
12. API nào đặt CLIENT_IDENTIFIER?
13. Vì sao không dùng CLIENT_INFO để lưu token?
14. V$SESSION cung cấp thông tin gì?
15. V$SQLAREA giúp phân tích workload theo module/action thế nào?
16. Vì sao session INACTIVE vẫn có thể hiển thị ACTION?
17. Connection pool có thể làm sai module/action ra sao?
18. Vì sao cần cleanup trong finally?
19. DBMS_MONITOR.SERV_MOD_ACT_STAT_ENABLE dùng để làm gì?
20. Thống kê theo service/module/action xem ở view nào?
21. ALL_ACTIONS khác NULL thế nào?
22. Khi đổi action, thống kê call hiện tại có đổi ngay không?
23. SERV_MOD_ACT_STAT_DISABLE có tác động gì đến số liệu tích lũy?
24. SERV_MOD_ACT_TRACE_ENABLE dùng để làm gì?
25. Vì sao nên thận trọng với binds trong trace?
26. TRCSESS và TKPROF có vai trò gì?
27. SET_SESSION_LONGOPS công bố tiến độ ở view nào?
28. SOFAR và TOTALWORK biểu diễn điều gì?
29. ASH có phải log đầy đủ mọi request không?
30. MODULE/ACTION có thể dùng để phân quyền không?

**Gợi ý trả lời:**

1. Gắn nhãn ứng dụng/session để quan sát, thống kê và tracing.
2. MODULE là vùng chức năng; ACTION là công việc hiện tại trong module.
3. Cả MODULE và ACTION.
4. Không, chỉ thay ACTION.
5. Module và action hiện tại.
6. Trước mỗi transaction hoặc bước nghiệp vụ cần quan sát.
7. Tránh request sau kế thừa nhãn của request trước.
8. LONG_MODULE_ACTION mặc định TRUE: 64 bytes cho mỗi trường.
9. Module 48 bytes, action 32 bytes.
10. Byte.
11. CLIENT_INFO là metadata bổ sung; CLIENT_IDENTIFIER nhận diện end user/client logic.
12. DBMS_SESSION.SET_IDENTIFIER.
13. CLIENT_INFO có thể đọc/ghi bởi user và không phải secure storage.
14. Session hiện tại, status, service, module/action, client, SQL_ID và nhiều thuộc tính khác.
15. Xem cursor SQL được gắn module/action và các thống kê thực thi.
16. Metadata vẫn giữ giá trị cuối cho đến khi được đổi hoặc reset.
17. Session vật lý được tái sử dụng và có thể mang tag của request trước.
18. Bảo đảm cleanup cả khi có exception.
19. Bật thống kê tổng hợp theo service/module/action.
20. V$SERV_MOD_ACT_STATS.
21. ALL_ACTIONS là wildcard cho mọi action; NULL đại diện action rỗng.
22. Có thể từ user call kế tiếp.
23. Tắt aggregation và xóa số liệu tích lũy tương ứng khỏi view.
24. Bật SQL trace theo service/module/action.
25. Bind values có thể chứa dữ liệu nhạy cảm và được ghi vào trace.
26. TRCSESS gom trace files; TKPROF định dạng/phân tích.
27. V$SESSION_LONGOPS.
28. Công việc đã hoàn thành và tổng công việc ước tính.
29. Không, ASH lấy mẫu session active.
30. Không; chúng là metadata do ứng dụng đặt, không phải cơ chế authorization.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html): SET_MODULE, SET_ACTION, READ_MODULE, CLIENT_INFO và SESSION_LONGOPS.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_MONITOR](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_MONITOR.html): thống kê và SQL trace theo client/service/module/action.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SESSION.html): SET_IDENTIFIER và CLEAR_IDENTIFIER.
- [Oracle Database 19c Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): MODULE, ACTION, CLIENT_INFO và CLIENT_IDENTIFIER.
- [Oracle Database 19c Database Reference — V$SERV_MOD_ACT_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SERV_MOD_ACT_STATS.html): thống kê theo service/module/action.
- [Oracle Database 19c Database Reference — LONG_MODULE_ACTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/LONG_MODULE_ACTION.html): giới hạn độ dài module/action từ 12.2.
- [Oracle Database 19c SQL Tuning Guide — Performing Application Tracing](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/performing-application-tracing.html): end-to-end tracing, DBMS_MONITOR, trace files và TKPROF.
- [Oracle Database 19c Security Guide — Preserving User Identity in Multitiered Environments](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/preserving-user-identity-multitiered-environments.html): client identifier trong kiến trúc nhiều tầng.

**Nguyên tắc cần nhớ:** DBMS_APPLICATION_INFO cho phép ứng dụng gắn MODULE để mô tả thành phần chức năng và ACTION để mô tả bước nghiệp vụ hiện tại. Đặt nhãn trên đúng physical session, đổi action khi công việc thay đổi và reset metadata khi request kết thúc. CLIENT_IDENTIFIER dùng để nhận diện end user/client logic; CLIENT_INFO chỉ là trường bổ sung, không phải nơi lưu dữ liệu bảo mật. Kết hợp MODULE/ACTION với V$SESSION, V$SQLAREA, DBMS_MONITOR và V$SERV_MOD_ACT_STATS để tìm workload và bật tracing có phạm vi. Với connection pool, luôn cleanup session state trước khi trả connection để request tiếp theo không bị gắn nhầm nhãn.
