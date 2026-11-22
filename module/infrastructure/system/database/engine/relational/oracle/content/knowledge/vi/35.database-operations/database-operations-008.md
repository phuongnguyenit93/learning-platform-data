# ADR, alert log, trace file và sử dụng ADRCI

Oracle Database lưu thông tin chẩn đoán trong **Automatic Diagnostic Repository (ADR)**. ADR là cấu trúc lưu trữ dựa trên thư mục, giúp tập trung alert log, trace file, incident, dump, health-check output và dữ liệu phục vụ phân tích sự cố. DBA có thể dùng SQL views để tra cứu một số thông tin, dùng hệ điều hành để đọc file khi phù hợp, hoặc dùng **ADRCI (ADR Command Interpreter)** để quản lý và đóng gói dữ liệu chẩn đoán.

Ba thành phần cần phân biệt:

- **Alert log:** nhật ký sự kiện quan trọng của database hoặc instance, như startup/shutdown, lỗi nghiêm trọng, checkpoint, archive log và các cảnh báo vận hành.
- **Trace file:** file chi tiết do Oracle process, session hoặc diagnostic component tạo ra; có thể chứa call stack, error stack, wait, SQL trace, bind và thông tin nội bộ tùy loại trace.
- **ADRCI:** công cụ dòng lệnh để khám phá ADR homes, xem alert, liệt kê problem/incident, tạo incident package và quản lý retention/purge.

Khi database gặp lỗi, quy trình thường bắt đầu bằng việc xác định đúng instance và thời điểm sự cố, đọc alert log để tìm dấu mốc, lấy trace tương ứng, sau đó dùng ADRCI/IPS để tạo gói chẩn đoán nếu cần gửi Oracle Support. Việc thu thập phải có kiểm soát vì trace và dump có thể chứa SQL text, bind values, tên người dùng, đường dẫn và dữ liệu nhạy cảm.

## 1. ADR là gì?

### 1.1. Mục đích

Automatic Diagnostic Repository là nơi Oracle lưu dữ liệu chẩn đoán theo cấu trúc thống nhất. ADR được giới thiệu để thay thế cách lưu rải rác trước đây và hỗ trợ:

- Ghi nhận sự kiện và lỗi quan trọng.
- Lưu trace file theo database, instance, listener và thành phần khác.
- Quản lý incident và problem.
- Chạy các quy trình Health Monitor/diagnostic.
- Đóng gói dữ liệu liên quan sự cố để phân tích.
- Áp dụng retention policy và dọn dữ liệu cũ.

ADR không phải kho backup database và không thay thế RMAN. Trace, alert log, dump và incident package hỗ trợ chẩn đoán; chúng không khôi phục datafile hoặc redo.

### 1.2. ADR base và ADR home

- **ADR base:** thư mục gốc chứa một hoặc nhiều ADR homes.
- **ADR home:** vùng chẩn đoán dành cho một database instance hoặc một thành phần Oracle cụ thể.

Ví dụ cấu trúc trên Linux:

§§§text
/u01/app/oracle/diag/
    rdbms/
        orcl/
            orcl/
                alert/
                trace/
                incident/
                cdump/
                hm/
                metadata/
    tnslsnr/
        dbhost01/
            listener/
                alert/
                trace/
                incident/
§§§

Đường dẫn thực tế phụ thuộc ADR base, DB_UNIQUE_NAME, instance name, Oracle Home và platform. Không giả định database home luôn nằm ở /u01/app/oracle hoặc mọi hệ thống dùng cùng tên thư mục.

### 1.3. Các thư mục thường gặp

| Thư mục | Nội dung |
|---|---|
| alert | Alert log, thường có định dạng XML và text tương ứng |
| trace | Trace file, process trace và một số file diagnostic |
| incident | Dump và metadata của incident |
| cdump | Core dump nếu có |
| hm | Health Monitor output |
| metadata | Metadata phục vụ ADR |
| sweep | Dữ liệu quản lý/diagnostic nội bộ tùy phiên bản |

Không nên tự xóa file trực tiếp trong các thư mục ADR để giải phóng dung lượng. Dùng ADRCI purge hoặc cơ chế quản lý được Oracle hỗ trợ để tránh xóa nhầm dữ liệu đang được tham chiếu.

### 1.4. ADR homes của nhiều thành phần

Một máy có thể có nhiều ADR homes:

- Database instance.
- Listener.
- ASM instance.
- Oracle Clusterware.
- Một số client hoặc thành phần Oracle khác tùy cấu hình.

Lỗi kết nối có thể nằm trong listener ADR home chứ không phải database ADR home. Khi điều tra, phải chọn đúng component và home.

## 2. Xác định ADR base, ADR home và đường dẫn chẩn đoán

### 2.1. V$DIAG_INFO

Trong database, view V$DIAG_INFO là điểm bắt đầu để biết các vị trí diagnostic:

§§§sql
SELECT name, value
FROM v$diag_info
ORDER BY name;
§§§

Các tên thường gặp:

| NAME | Ý nghĩa |
|---|---|
| Diag Enabled | ADR có được bật hay không |
| ADR Base | Thư mục gốc ADR |
| ADR Home | ADR home của instance hiện tại |
| Diag Trace | Thư mục trace |
| Diag Alert | Vị trí alert log |
| Diag Incident | Thư mục incident |
| Diag Cdump | Vị trí core dump |
| Health Monitor | Vị trí dữ liệu Health Monitor |
| Default Trace File | Trace file mặc định của session hiện tại |

Danh sách tên và giá trị cụ thể có thể khác theo phiên bản hoặc loại instance.

### 2.2. Lấy đường dẫn trace file hiện tại

§§§sql
SELECT value
FROM v$diag_info
WHERE name = 'Default Trace File';
§§§

Đường dẫn này hữu ích khi muốn xác định trace file mặc định của session đang chạy câu SQL. Không phải mọi trace đều được ghi vào default trace file; process trace, incident dump và SQL trace có thể tạo file riêng.

### 2.3. Xem ADR home

§§§sql
SELECT value
FROM v$diag_info
WHERE name = 'ADR Home';
§§§

Đường dẫn này có thể dùng làm căn cứ khi chạy ADRCI và chọn đúng home. Với RAC, mỗi instance có ADR home riêng theo instance name.

### 2.4. Kiểm tra qua tham số

Một số cấu hình liên quan:

§§§sql
SHOW PARAMETER diagnostic_dest;
SHOW PARAMETER db_unique_name;
SHOW PARAMETER instance_name;
§§§

DIAGNOSTIC_DEST xác định vị trí gốc cho diagnostic data trong các cấu hình ADR tương ứng. Oracle có thể suy ra ADR base theo quy tắc platform nếu parameter không được đặt tường minh.

### 2.5. Database và listener có ADR home khác nhau

Nếu client không kết nối được, cần xem listener log. Database alert log chỉ ghi sự kiện khi request đã tới database hoặc database process có liên quan. Listener có ADR home riêng và có thể được truy cập qua ADRCI:

§§§text
diag/tnslsnr/<host_name>/<listener_name>
§§§

Thay host_name và listener_name bằng giá trị thực tế của máy.

## 3. Alert log

### 3.1. Vai trò

Alert log là nhật ký quan trọng nhất để theo dõi sự kiện cấp database/instance. Nó thường ghi:

- Startup, mount, open, shutdown.
- Thay đổi trạng thái database.
- Checkpoint và redo/archive activity.
- Datafile, control file và tablespace events.
- Lỗi ORA nghiêm trọng.
- Incident/problem được tạo.
- Một số cảnh báo về memory, process, recovery và background processes.

Alert log không phải SQL audit log. Nó không ghi mọi câu SQL mà người dùng thực thi.

### 3.2. XML và text alert log

Trong ADR, Oracle lưu alert log dạng XML; nhiều phiên bản cũng tạo text-formatted alert log để DBA đọc thuận tiện. Tên file và đường dẫn thường nằm trong ADR home dưới thư mục alert.

Định dạng XML có timestamp, component, message type/level và message text có cấu trúc. Text alert log dễ đọc nhanh bằng editor hoặc lệnh tail. Khi cần truy vấn hoặc lọc có cấu trúc, dùng view diagnostic hoặc ADRCI.

### 3.3. Xem alert log bằng ADRCI

Khởi động công cụ:

§§§text
adrci
§§§

Liệt kê ADR homes:

§§§text
adrci> show homes
§§§

Chọn database home:

§§§text
adrci> set home diag/rdbms/orcl/orcl
§§§

Xem alert:

§§§text
adrci> show alert
§§§

Tên home ở trên chỉ là ví dụ. Dùng đúng đường dẫn hiển thị bởi show homes.

### 3.4. Xem những dòng gần nhất

§§§text
adrci> show alert -tail 100
§§§

Theo dõi liên tục:

§§§text
adrci> show alert -tail -f
§§§

Tùy ADRCI release, cú pháp option có thể khác nhẹ; dùng help show alert để xem syntax mà phiên bản đang cài hỗ trợ.

### 3.5. Xem alert log dạng XML qua view

Một số release cung cấp V$DIAG_ALERT_EXT để truy vấn alert log:

§§§sql
SELECT originating_timestamp,
       message_type,
       message_level,
       message_text,
       problem_key
FROM v$diag_alert_ext
WHERE originating_timestamp >=
      SYSTIMESTAMP - INTERVAL '1' DAY
ORDER BY originating_timestamp DESC;
§§§

View này hữu ích để lọc theo thời gian, message type, problem key hoặc text. Các cột cụ thể có thể khác theo release; xem DESC V$DIAG_ALERT_EXT trong database đang dùng.

### 3.6. Tìm ORA error

Ví dụ tìm các message có mã ORA:

§§§sql
SELECT originating_timestamp,
       message_text
FROM v$diag_alert_ext
WHERE originating_timestamp >=
      SYSTIMESTAMP - INTERVAL '6' HOUR
  AND message_text LIKE '%ORA-%'
ORDER BY originating_timestamp;
§§§

Không chỉ tìm chuỗi ORA. Cần xem các message trước/sau để xác định nguyên nhân gốc, vì ORA ở cuối có thể chỉ là hậu quả.

### 3.7. Đọc theo trình tự thời gian

Khi có sự cố, xác định:

1. Thời điểm bắt đầu ảnh hưởng người dùng.
2. Sự kiện đầu tiên bất thường trong alert log.
3. Các warning/error tiếp theo.
4. Instance/database state thay đổi ra sao.
5. Có incident hoặc trace file nào được tạo cùng thời điểm không.

Đồng bộ timezone giữa alert log, application log, OS log và monitoring trước khi so sánh. Một số timestamp được hiển thị theo timezone khác nhau.

## 4. Trace file

### 4.1. Trace file là gì?

Trace file chứa chi tiết chẩn đoán do Oracle process, session hoặc component tạo ra. Trace có thể bao gồm:

- Error stack và call stack.
- Process/session state.
- Wait event và thông tin timing.
- SQL text và execution details.
- Bind values nếu trace level thu thập chúng.
- Heap dump, system state dump hoặc process state dump.
- Thông tin về deadlock, latch, enqueue hoặc lỗi nội bộ.

Trace không có một format duy nhất cho mọi loại. Một số trace đọc được bằng text editor; một số dump lớn cần công cụ/Oracle Support để diễn giải.

### 4.2. Trace file của session

Đường dẫn default trace file của session:

§§§sql
SELECT value
FROM v$diag_info
WHERE name = 'Default Trace File';
§§§

Có thể đặt tracefile identifier để dễ nhận diện file được tạo sau đó:

§§§sql
ALTER SESSION SET tracefile_identifier = 'ORDER_API_DEBUG';
§§§

Identifier được nối vào tên trace file theo quy tắc Oracle. Đặt tên ngắn, không chứa dữ liệu nhạy cảm.

### 4.3. Trace file của background process

Background process như DBWn, LGWR, SMON, PMON hoặc process khác có thể ghi trace riêng khi phát sinh lỗi hoặc diagnostic event. Không phải mọi background process đều tạo trace liên tục.

Khi alert log chỉ ra process name và trace file path, hãy mở đúng file đó thay vì chỉ xem default trace của session DBA.

### 4.4. Trace file và incident dump

Incident thường có dump riêng trong ADR incident directory. Trace file có thể chứa phần tham chiếu đến incident hoặc dump. Không xóa file trong incident directory bằng thao tác filesystem vì có thể làm hỏng cấu trúc package hoặc mất bằng chứng.

### 4.5. Trace file quá lớn

SQL trace hoặc event trace có thể tăng rất nhanh khi workload nhiều. Trước khi bật trace:

- Giới hạn session/user/module và khoảng thời gian.
- Xác định nơi ghi file và dung lượng trống.
- Có thời điểm tắt trace rõ ràng.
- Tránh bật level cao trên toàn instance nếu không cần.
- Bảo vệ file vì có thể chứa SQL/bind data.

## 5. SQL trace cho session và workload

### 5.1. Mục đích SQL trace

SQL trace ghi các call parse, execute, fetch và wait liên quan. Khi định dạng bằng TKPROF, DBA có thể xem:

- Số lần parse/execute/fetch.
- CPU và elapsed time.
- Logical reads và physical reads.
- Rows processed.
- Wait event và thời gian chờ.
- Execution plan tùy cấu hình và dữ liệu trace.

SQL trace giúp phân biệt query tốn CPU, chờ I/O, chờ lock hoặc có nhiều lần parse/fetch.

### 5.2. Bật trace cho session hiện tại

Có thể dùng DBMS_SESSION:

§§§sql
BEGIN
    DBMS_SESSION.SESSION_TRACE_ENABLE(
        waits     => TRUE,
        binds     => FALSE,
        plan_stat => 'ALL_EXECUTIONS'
    );
END;
/
§§§

Signature hỗ trợ phụ thuộc Oracle release. Nếu overload không có plan_stat, dùng overload được package specification cung cấp. Bật binds chỉ khi cần và đã đánh giá rủi ro lộ dữ liệu.

Tắt trace:

§§§sql
BEGIN
    DBMS_SESSION.SESSION_TRACE_DISABLE;
END;
/
§§§

Luôn có bước tắt trace; đóng session không phải cách quản lý trace có chủ đích.

### 5.3. Dùng ALTER SESSION

Trong một số môi trường, có thể bật SQL trace bằng:

§§§sql
ALTER SESSION SET sql_trace = TRUE;
§§§

Tắt:

§§§sql
ALTER SESSION SET sql_trace = FALSE;
§§§

DBMS_SESSION hoặc DBMS_MONITOR thường linh hoạt hơn khi cần kiểm soát waits/binds và session khác.

### 5.4. Trace session khác bằng SID/SERIAL#

DBA có thể bật trace cho session khác bằng DBMS_MONITOR:

§§§sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        session_id => 123,
        serial_num => 456,
        waits      => TRUE,
        binds      => FALSE
    );
END;
/
§§§

SID và SERIAL# phải lấy từ V$SESSION tại thời điểm bật trace. Kết hợp cả hai để tránh nhầm session do SID có thể được tái sử dụng. Trong RAC, xác định instance/session tương ứng và dùng API/view phù hợp với cluster.

Tắt trace:

§§§sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE(
        session_id => 123,
        serial_num => 456
    );
END;
/
§§§

### 5.5. Trace theo client identifier

Ứng dụng có thể đặt CLIENT_IDENTIFIER bằng DBMS_SESSION.SET_IDENTIFIER. DBA có thể bật trace theo client ID:

§§§sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE(
        client_id => 'APP_USER_1001',
        waits     => TRUE,
        binds     => FALSE
    );
END;
/
§§§

Tắt:

§§§sql
BEGIN
    DBMS_MONITOR.CLIENT_ID_TRACE_DISABLE(
        client_id => 'APP_USER_1001'
    );
END;
/
§§§

Phương pháp này hữu ích với connection pool vì một end user có thể được phục vụ bởi nhiều database session. CLIENT_IDENTIFIER phải được ứng dụng đặt đúng và reset khi connection được tái sử dụng.

### 5.6. Trace theo service/module/action

DBMS_MONITOR có thể bật trace theo service, module và action:

§§§sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_ENABLE(
        service_name => 'ORDER_SERVICE',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER',
        waits        => TRUE,
        binds        => FALSE
    );
END;
/
§§§

Tắt:

§§§sql
BEGIN
    DBMS_MONITOR.SERV_MOD_ACT_TRACE_DISABLE(
        service_name => 'ORDER_SERVICE',
        module_name  => 'ORDER_API',
        action_name  => 'CREATE_ORDER'
    );
END;
/
§§§

Module/action thường được ứng dụng thiết lập bằng DBMS_APPLICATION_INFO.SET_MODULE. Xác nhận tên service/module/action đúng với giá trị runtime trước khi bật trace.

### 5.7. Trace theo database client

Trace theo service/module/action hoặc client ID có thể tác động nhiều session. Ước lượng số session match và dung lượng trace trước khi bật trên production.

## 6. TKPROF và phân tích SQL trace

### 6.1. TKPROF là gì?

TKPROF là công cụ Oracle cung cấp để định dạng raw SQL trace thành báo cáo dễ đọc. Nó tổng hợp parse/execute/fetch, CPU, elapsed time, logical/physical I/O, rows và wait statistics theo cursor.

### 6.2. Ví dụ chạy TKPROF

Trên máy có Oracle client/database tools:

§§§text
tkprof input.trc output.prf sys=no sort=exeela,fchela
§§§

Đường dẫn file trace và output cần thay bằng file thực tế. Tùy phiên bản, các tùy chọn sort và report có thể khác.

### 6.3. Đọc các phần trong report

- Parse: chi phí parse và số lần parse.
- Execute: thời gian/CPU/I/O trong lúc thực thi.
- Fetch: chi phí lấy dữ liệu trả về client.
- Rows: số hàng xử lý ở từng phase.
- Misses/library cache: dấu hiệu parse hoặc cursor reuse.
- Waits: thời gian chờ theo event nếu trace waits được bật.

Một câu SELECT có thể có execute nhanh nhưng fetch rất lâu vì client lấy nhiều hàng hoặc xử lý chậm. Đừng chỉ nhìn execute time.

### 6.4. EXPLAIN trong TKPROF

TKPROF có thể nhận tùy chọn EXPLAIN để phân tích plan bằng tài khoản/schema. Plan được tạo lại trong môi trường explain và có thể không giống cursor plan lúc trace. Khi cần plan thực tế, đối chiếu SQL_ID/child cursor với DBMS_XPLAN.DISPLAY_CURSOR.

### 6.5. Trace có bind values

Trace binds có thể chứa giá trị người dùng, token, email, số tài khoản hoặc dữ liệu nghiệp vụ. Bật binds chỉ khi thực sự cần, giới hạn thời gian và bảo vệ file/report. Trước khi chia sẻ trace, kiểm tra chính sách bảo mật và quy trình redaction.

## 7. Incident và problem trong ADR

### 7.1. Problem

Problem là một loại lỗi hoặc sự cố được Oracle nhận diện theo problem key/signature. Nhiều lần xảy ra cùng loại lỗi có thể được liên kết với cùng problem.

### 7.2. Incident

Incident là một lần xảy ra cụ thể của problem. Một problem có thể có nhiều incident, mỗi incident có timestamp và dump/trace liên quan.

Ví dụ, một lỗi ORA nội bộ lặp lại nhiều lần có thể tạo một problem key và nhiều incident. Việc gom nhóm giúp DBA không phải xem từng dump như một sự cố hoàn toàn độc lập.

### 7.3. Incident flood control

Oracle có thể giới hạn số incident dump được tạo cho một problem trong một khoảng thời gian để tránh làm đầy disk khi lỗi lặp liên tục. Vì vậy không phải mỗi lần lỗi đều tạo một incident dump mới.

### 7.4. ADRCI show problem

§§§text
adrci> show problem
§§§

Lệnh liệt kê problem trong ADR home hiện tại. Chọn đúng home trước khi chạy.

### 7.5. ADRCI show incident

§§§text
adrci> show incident
§§§

Có thể giới hạn output theo problem hoặc khoảng thời gian bằng các tùy chọn được ADRCI release hỗ trợ. Dùng help show incident để xem cú pháp.

### 7.6. Incident details

Thông tin incident có thể gồm:

- Incident ID.
- Problem ID/key.
- Create time.
- Incident status.
- File path của dump/trace.
- Component và process liên quan.

Dùng incident ID để tạo package và liên kết dữ liệu với Oracle Support.

## 8. ADRCI cơ bản

### 8.1. Khởi động

Từ operating system shell:

§§§text
adrci
§§§

ADRCI là command-line interpreter. Nó không phải SQL*Plus và không nhận cú pháp SQL trực tiếp. Các lệnh có prefix show, set, ips, purge hoặc help.

### 8.2. Liệt kê homes

§§§text
adrci> show homes
§§§

Output có thể chứa nhiều home cho database, listener, ASM hoặc component khác.

### 8.3. Chọn home

§§§text
adrci> set home diag/rdbms/orcl/orcl
§§§

Nếu có nhiều homes, chọn chính xác database/instance hoặc listener cần điều tra. Các lệnh show sau đó hoạt động trong home đang chọn.

### 8.4. Xem alert

§§§text
adrci> show alert
adrci> show alert -tail 100
adrci> show alert -tail -f
§§§

show alert -tail -f hữu ích khi theo dõi startup hoặc tái hiện lỗi. Dừng chế độ theo dõi bằng thao tác ngắt phù hợp của terminal.

### 8.5. Xem trace file

§§§text
adrci> show tracefile
§§§

Lệnh liệt kê trace files trong ADR home. Dùng các tùy chọn lọc/sắp xếp nếu release hỗ trợ hoặc dùng help show tracefile.

### 8.6. Xem problem và incident

§§§text
adrci> show problem
adrci> show incident
§§§

Sau khi tìm được incident, lấy ID và thời điểm để liên hệ với alert log, trace file và monitoring.

### 8.7. Help

§§§text
adrci> help
adrci> help show alert
adrci> help ips
adrci> help purge
§§§

ADRCI có thể có khác biệt cú pháp giữa các Oracle homes/version. Help tại chính máy đang điều tra là nguồn kiểm tra syntax gần nhất.

## 9. Incident Packaging Service (IPS)

### 9.1. Vì sao cần package?

Khi mở service request với Oracle Support, thường cần cung cấp trace, dump, alert log và metadata liên quan. IPS giúp gom các file cần thiết thành incident package có cấu trúc, giảm việc tự tìm và copy từng file.

### 9.2. Tạo package theo problem

Ví dụ trong ADRCI:

§§§text
adrci> ips create package problem 1
§§§

Số 1 là problem ID minh họa. Thay bằng problem ID lấy từ show problem.

### 9.3. Tạo package theo incident

§§§text
adrci> ips create package incident 12345
§§§

Thay 12345 bằng incident ID thực tế. Package theo incident tập trung vào một lần xảy ra cụ thể; package theo problem có thể gom nhiều incident cùng loại theo yêu cầu.

### 9.4. Xem package

§§§text
adrci> ips show package
§§§

Ghi nhận package ID được trả về. Có thể cập nhật package, thêm incident hoặc file bổ sung bằng IPS commands theo nhu cầu và syntax release.

### 9.5. Generate package

§§§text
adrci> ips generate package 7 in /u01/support
§§§

Số 7 là package ID ví dụ. Thư mục đích phải tồn tại và có quyền ghi. ADRCI tạo file package/archive để chuyển cho nhóm hỗ trợ.

### 9.6. Package theo thời gian

Khi không có incident ID rõ ràng, có thể tạo package theo khoảng thời gian hoặc theo file/problem tùy lệnh IPS được hỗ trợ. Xem help ips create package và help ips add trong phiên bản đang chạy.

### 9.7. Kiểm tra nội dung trước khi gửi

Package có thể chứa SQL text, bind values, schema/object names, hostnames, path, username hoặc dữ liệu nhạy cảm. Trước khi chuyển ra ngoài:

- Xác định chính xác phạm vi file được đóng gói.
- Kiểm tra quy định dữ liệu và security policy của tổ chức.
- Dùng kênh upload Oracle Support được phê duyệt.
- Không gửi package qua email/chat công cộng nếu chưa được phép.
- Giữ lại package ID, thời điểm tạo và service request reference.

## 10. ADRCI purge và retention policy

### 10.1. Vì sao cần retention?

Trace, incident dump và alert log có thể tăng dung lượng theo thời gian. ADR có retention policy để xác định dữ liệu diagnostic được giữ bao lâu trước khi có thể purge.

Purge quá sớm có thể làm mất bằng chứng điều tra; giữ vô hạn có thể làm đầy filesystem và ảnh hưởng database/Oracle Home.

### 10.2. Xem retention policy

Trong ADRCI:

§§§text
adrci> show control
§§§

Output chứa một số thuộc tính ADR control và retention. Tên trường, đơn vị và nội dung có thể khác theo release.

### 10.3. Purge theo tuổi dữ liệu

ADRCI purge thường nhận age theo phút và loại dữ liệu:

§§§text
adrci> purge -age 10080 -type TRACE
§§§

Ví dụ 10080 phút tương đương 7 ngày. Chỉ thực hiện sau khi xác nhận loại dữ liệu, home và retention policy. Không dùng ví dụ này như lệnh mặc định cho production.

### 10.4. Purge các loại dữ liệu

Tùy phiên bản, ADRCI hỗ trợ purge theo loại như TRACE, ALERT, INCIDENT, CDUMP hoặc HM. Xem help purge để xác nhận các type hợp lệ trên home hiện tại.

### 10.5. Không purge bằng wildcard filesystem

Không dùng lệnh xóa đệ quy để xóa trực tiếp toàn bộ thư mục trace/incident nhằm dọn ADR. Việc xóa thủ công có thể làm mất metadata, phá vỡ liên kết incident/package hoặc xóa file đang được process sử dụng.

### 10.6. Retention và incident

Incident có thể cần giữ lâu hơn trace thông thường nếu đang điều tra hoặc chờ Oracle Support. Trước khi purge, xác nhận service request đã nhận package và dữ liệu không còn cần thiết. Có thể export/package trước khi dọn.

### 10.7. Theo dõi dung lượng

Theo dõi dung lượng ADR base và từng ADR home, tốc độ tăng trace, incident flood và dung lượng filesystem còn trống. Cảnh báo sớm trước khi filesystem đầy; không chờ đến khi database không thể ghi trace hoặc alert log.

## 11. Health Monitor và diagnostic data

### 11.1. Health Monitor

Oracle Health Monitor có thể chạy các check phục vụ chẩn đoán database/file/component. Kết quả có thể được lưu trong ADR và được xem qua các view/package phù hợp.

### 11.2. Khi nào dùng?

Health Monitor hữu ích khi điều tra corruption, block/datafile issues hoặc một số vấn đề cấu trúc database. Chọn check phù hợp với triệu chứng và tài liệu Oracle; không chạy mọi check trên production mà không hiểu tác động.

### 11.3. ADRCI và HM

ADRCI có thể hiển thị thông tin Health Monitor trong các release hỗ trợ. Dùng help show hm_run hoặc lệnh tương ứng để xem các lần chạy và kết quả.

### 11.4. Health Monitor không thay backup validation

Health check hỗ trợ phát hiện vấn đề nhưng không thay thế RMAN backup validation, restore test hoặc quy trình disaster recovery. Diagnostic output không tự sửa corruption.

## 12. Điều tra sự cố theo quy trình

### Bước 1 — Xác định phạm vi

Ghi nhận database, DB_UNIQUE_NAME, instance, host, container/PDB, service và thời điểm sự cố. Nếu kết nối không tới database, kiểm tra listener ADR home.

### Bước 2 — Xác định ADR home

Trong database, truy vấn V$DIAG_INFO. Nếu database không mở được, xác định ADR base/home từ Oracle Home, cấu hình và ADRCI show homes.

### Bước 3 — Đọc alert log

Xem quanh thời điểm bắt đầu sự cố. Tìm ORA error, process name, incident ID, file path, startup/shutdown và các message trước/sau.

### Bước 4 — Lấy trace đúng

Nếu alert log chỉ ra trace path, mở đúng file đó. Nếu cần trace session, lấy SID/SERIAL# hoặc client/module/action rồi bật trace có phạm vi.

### Bước 5 — Liên kết incident/problem

Dùng ADRCI show problem và show incident. Đối chiếu problem key, incident ID và timestamp với alert log.

### Bước 6 — Phân tích SQL trace nếu cần

Dùng TKPROF cho raw SQL trace để xem parse/execute/fetch, CPU, I/O và waits. Đối chiếu với DBMS_XPLAN hoặc SQL Monitor nếu cần plan/runtime details.

### Bước 7 — Tạo incident package

Dùng IPS tạo package theo incident/problem hoặc khoảng thời gian phù hợp. Generate package vào thư mục được bảo vệ.

### Bước 8 — Bảo vệ và chia sẻ

Kiểm tra package có dữ liệu nhạy cảm, lưu hash/metadata nếu quy trình yêu cầu và chuyển qua kênh hỗ trợ được phê duyệt.

### Bước 9 — Khôi phục và theo dõi

Sau khi xử lý sự cố, kiểm tra database status, alert log mới, application health và resource metrics. Không xóa diagnostic data trước khi xác nhận điều tra hoàn tất.

## 13. Ví dụ truy vấn chẩn đoán

### 13.1. Liệt kê vị trí ADR

§§§sql
SELECT name, value
FROM v$diag_info
ORDER BY name;
§§§

### 13.2. Alert log trong 30 phút gần nhất

§§§sql
SELECT originating_timestamp,
       message_type,
       message_level,
       message_text
FROM v$diag_alert_ext
WHERE originating_timestamp >=
      SYSTIMESTAMP - INTERVAL '30' MINUTE
ORDER BY originating_timestamp;
§§§

### 13.3. Lọc lỗi ORA

§§§sql
SELECT originating_timestamp,
       message_text,
       problem_key
FROM v$diag_alert_ext
WHERE message_text LIKE '%ORA-%'
  AND originating_timestamp >=
      SYSTIMESTAMP - INTERVAL '1' DAY
ORDER BY originating_timestamp DESC;
§§§

### 13.4. Session và process

§§§sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.module,
       s.action,
       s.client_identifier,
       p.spid,
       p.tracefile
FROM v$session s
JOIN v$process p
  ON p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY s.sid;
§§§

Các cột V$PROCESS có thể khác theo release. Nếu TRACEFILE không có trong view của phiên bản, dùng V$DIAG_INFO hoặc ADRCI để xác định trace path.

### 13.5. Session đang bật SQL trace

§§§sql
SELECT sid,
       serial#,
       username,
       sql_trace,
       sql_trace_waits,
       sql_trace_binds,
       module,
       action
FROM v$session
WHERE sql_trace = 'ENABLED';
§§§

Tên/giá trị cột có thể khác theo release. Có thể cần xem V$SESSION hoặc các view monitor khác để xác định session trace state.

### 13.6. Incident metadata

Thông tin incident có thể xem qua ADRCI hoặc các view diagnostic phù hợp như V$DIAG_INCIDENT. Cột và quyền truy cập phụ thuộc release; dùng DESC trên view có sẵn và đối chiếu incident ID với ADRCI.

## 14. Listener alert log và lỗi kết nối

### 14.1. Khi nào cần xem listener ADR?

Nếu client báo ORA-12514, ORA-12541, ORA-12505 hoặc ORA-12170, hãy xem listener log cùng với client connect descriptor, service registration và trạng thái network.

### 14.2. Chọn listener home

Trong ADRCI:

§§§text
adrci> show homes
adrci> set home diag/tnslsnr/dbhost01/listener
adrci> show alert -tail 100
§§§

Tên host/listener chỉ minh họa. Một máy có thể có nhiều listener và mỗi listener có ADR home riêng.

### 14.3. Database alert log vẫn cần kiểm tra

Listener có thể nhận connection rồi chuyển tới database. Nếu lỗi phát sinh sau khi request đã tới instance, database alert log hoặc session trace có thể có thêm thông tin. Đọc cả hai theo timeline.

### 14.4. Listener log và database alert log khác nhau

Listener log ghi connection requests, service registration và network-level events. Database alert log ghi sự kiện trong database/instance. Không dùng một log thay cho log còn lại.

## 15. Các lỗi và lưu ý thường gặp

| Triệu chứng | Nguồn cần kiểm tra | Gợi ý |
|---|---|---|
| Không tìm thấy alert log | V$DIAG_INFO/ADRCI home | Kiểm tra đúng instance và ADR home |
| Alert log không có lỗi kết nối | Listener ADR home | Kiểm tra listener/service/network |
| Trace file không rõ vị trí | Default Trace File, V$PROCESS, ADRCI | Xác định đúng session/process |
| Trace file quá lớn | SQL trace scope và thời gian | Tắt trace, giới hạn module/session |
| ORA error xuất hiện nhiều lần | Alert log/problem/incident | Tìm sự kiện đầu tiên và problem key |
| Incident không tạo mỗi lần lỗi | Flood control/incident policy | Kiểm tra problem và incident history |
| ADR base đầy | ADR retention/dữ liệu trace | Dùng ADRCI purge theo age/type |
| IPS package thiếu file | Chọn sai home/incident/problem | Kiểm tra package content và incident ID |
| Không xem được ADRCI home | ADR base/home discovery | Kiểm tra Oracle Home, ADR base và quyền OS |
| TKPROF report không có plan đúng | Explain trong môi trường khác | Dùng cursor plan thực tế để đối chiếu |
| Trace binds chứa dữ liệu nhạy cảm | Bật binds quá rộng | Tắt trace và kiểm soát package/report |
| Không tìm được session trace | SID/SERIAL# đã thay đổi | Xác định session hiện tại và instance |

## 16. Bảo mật và quyền truy cập diagnostic data

### 16.1. Trace có thể chứa dữ liệu nhạy cảm

Trace có thể chứa SQL text, bind values, schema names, user identifiers, file paths, hostnames và dữ liệu ứng dụng. Một số dump có thể chứa thông tin bộ nhớ. Xem trace như dữ liệu vận hành nhạy cảm.

### 16.2. Hạn chế quyền đọc

Chỉ DBA, nhóm hỗ trợ hoặc người được phê duyệt mới nên có quyền đọc toàn bộ ADR. Phân quyền OS ở thư mục ADR phải phù hợp với owner/group Oracle và policy của tổ chức.

### 16.3. Bật trace có phạm vi

Ưu tiên trace theo SID/SERIAL#, client ID, service/module/action hoặc session cụ thể. Tránh bật binds hoặc event trace toàn instance nếu chưa đánh giá dung lượng và dữ liệu.

### 16.4. Bảo vệ incident package

Package có thể gom nhiều file hơn dự kiến. Trước khi upload:

- Kiểm tra nội dung và phạm vi package.
- Dùng kênh được tổ chức phê duyệt.
- Không đặt package ở thư mục public.
- Không đưa vào source control.
- Xóa bản tạm sau khi hết thời hạn retention nội bộ.

### 16.5. Audit thao tác

Ghi lại ai bật trace, phạm vi, thời điểm bật/tắt, ADRCI purge và package ID. Điều này giúp kiểm soát diagnostic collection và giải thích thay đổi dung lượng.

## 17. Bài thực hành ADRCI

Thực hiện trong môi trường lab hoặc staging. Không bật trace binds, purge hoặc tạo dump nặng trên production nếu chưa có phê duyệt vận hành.

### Bước 1 — Xem vị trí ADR

§§§sql
SELECT name, value
FROM v$diag_info
ORDER BY name;
§§§

Ghi lại ADR base, ADR home, Diag Trace, Diag Alert và Default Trace File.

### Bước 2 — Khởi chạy ADRCI

§§§text
adrci
show homes
§§§

Xác định database home của instance lab.

### Bước 3 — Xem alert log

§§§text
set home <database_adr_home>
show alert -tail 50
§§§

Đối chiếu timestamp với V$DIAG_ALERT_EXT.

### Bước 4 — Đặt tracefile identifier

§§§sql
ALTER SESSION SET tracefile_identifier = 'ADR_LAB';
§§§

Lấy default trace file từ V$DIAG_INFO.

### Bước 5 — Bật session trace

§§§sql
BEGIN
    DBMS_SESSION.SESSION_TRACE_ENABLE(
        waits => TRUE,
        binds => FALSE
    );
END;
/
§§§

Chạy một câu SQL lab có phạm vi nhỏ, sau đó tắt trace.

### Bước 6 — Tắt trace

§§§sql
BEGIN
    DBMS_SESSION.SESSION_TRACE_DISABLE;
END;
/
§§§

Xác nhận trace file mới được tạo trong thư mục ADR trace.

### Bước 7 — Định dạng trace

Dùng TKPROF trên máy có Oracle tools:

§§§text
tkprof input.trc adr_lab.prf sys=no
§§§

Đọc parse/execute/fetch, CPU, elapsed, logical reads và waits.

### Bước 8 — Xem problem và incident

§§§text
adrci> show problem
adrci> show incident
§§§

Trong lab bình thường có thể không có incident. Không cố tình tạo lỗi nghiêm trọng chỉ để có dữ liệu thử nghiệm.

### Bước 9 — Tạo package khi có incident được chỉ định

Nếu môi trường lab có incident được tạo hợp lệ:

§§§text
adrci> ips create package incident <incident_id>
adrci> ips show package
adrci> ips generate package <package_id> in <output_directory>
§§§

Thay placeholder bằng ID và thư mục thực tế. Không generate package ra thư mục chia sẻ công khai.

### Bước 10 — Xem retention

§§§text
adrci> show control
adrci> help purge
§§§

Đọc retention policy và các loại purge hỗ trợ; không cần purge trong lab nếu không có dữ liệu cần dọn.

### Bước 11 — Ghi kết quả

| Nội dung | Giá trị |
|---|---|
| ADR Base | |
| ADR Home | |
| Alert log path | |
| Default trace file | |
| SQL trace file | |
| Problem ID | |
| Incident ID | |
| IPS package ID | |
| Retention policy | |

Điền dữ liệu thực tế từ môi trường lab.

## 18. Checklist điều tra sự cố

- [ ] Xác định database, DB_UNIQUE_NAME, instance và host.
- [ ] Xác định thời điểm bắt đầu sự cố và timezone.
- [ ] Lấy ADR Base và ADR Home từ V$DIAG_INFO hoặc ADRCI.
- [ ] Chọn đúng database/listener/ASM ADR home.
- [ ] Đọc alert log trước, trong và sau thời điểm lỗi.
- [ ] Tìm ORA error đầu tiên, process name và incident/problem key.
- [ ] Xác định trace file đúng từ alert log, V$PROCESS hoặc ADRCI.
- [ ] Nếu cần SQL trace, giới hạn session/client/module và thời gian.
- [ ] Tắt trace sau khi thu thập.
- [ ] Dùng TKPROF khi cần phân tích parse/execute/fetch/waits.
- [ ] Liên kết problem ID và incident ID.
- [ ] Tạo IPS package đúng incident/problem nếu cần hỗ trợ.
- [ ] Kiểm tra package và dữ liệu nhạy cảm trước khi chia sẻ.
- [ ] Kiểm tra ADR retention và dung lượng filesystem.
- [ ] Chỉ purge bằng ADRCI theo age/type đã xác nhận.
- [ ] Lưu timeline, package ID và kết quả xử lý.

## 19. Câu hỏi tự kiểm tra

1. ADR là gì và được dùng để lưu những loại dữ liệu nào?
2. ADR base khác ADR home ở điểm nào?
3. Vì sao một máy có nhiều ADR homes?
4. V$DIAG_INFO cung cấp những đường dẫn nào?
5. Alert log khác SQL audit log như thế nào?
6. Vì sao alert log có cả định dạng XML và text?
7. V$DIAG_ALERT_EXT dùng để làm gì?
8. Trace file có thể chứa những thông tin nào?
9. Default Trace File có luôn là file chứa mọi trace của session không?
10. Tracefile identifier có tác dụng gì?
11. SQL trace ghi nhận parse, execute và fetch ra sao?
12. DBMS_SESSION.SESSION_TRACE_ENABLE dùng để làm gì?
13. DBMS_MONITOR có thể bật trace theo session, client ID hoặc module/action thế nào?
14. Vì sao phải dùng SID kết hợp SERIAL#?
15. TKPROF giúp phân tích trace ở những khía cạnh nào?
16. Bind tracing có rủi ro bảo mật gì?
17. Problem khác incident như thế nào?
18. Incident flood control có mục đích gì?
19. ADRCI show homes và set home được dùng ra sao?
20. Làm thế nào theo dõi alert log liên tục bằng ADRCI?
21. IPS dùng để làm gì?
22. Khi nào tạo package theo problem và khi nào theo incident?
23. Vì sao phải kiểm tra nội dung package trước khi gửi?
24. ADRCI purge -age và -type có ý nghĩa gì?
25. Vì sao không nên xóa file ADR trực tiếp bằng lệnh filesystem?
26. Listener ADR home hỗ trợ điều tra lỗi kết nối nào?
27. Health Monitor cung cấp loại diagnostic nào?
28. Vì sao SQL trace toàn instance có thể nguy hiểm?
29. Những dữ liệu nào cần ghi lại trong timeline sự cố?
30. Quy trình từ alert log đến trace và IPS package nên thực hiện theo thứ tự nào?

**Nguyên tắc cần nhớ:** ADR tập trung dữ liệu chẩn đoán; alert log cho biết sự kiện và timeline, trace file cung cấp chi tiết process/session, còn ADRCI giúp khám phá home, xem alert/problem/incident, tạo IPS package và purge theo retention. Luôn xác định đúng ADR home và đúng session/process trước khi thu thập. Giới hạn trace theo phạm vi/thời gian, tắt sau khi dùng, bảo vệ bind và dump data, và chỉ dọn ADR bằng công cụ được hỗ trợ sau khi xác nhận dữ liệu không còn cần cho điều tra.
