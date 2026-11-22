# SQL trace, DBMS_MONITOR và TKPROF

Khi một câu SQL chạy chậm, execution plan cho biết Oracle tổ chức các operation như thế nào, nhưng chưa giải thích đầy đủ thời gian được tiêu thụ ở đâu. SQL Trace bổ sung dấu vết ở cấp lời gọi database: parse, execute, fetch và các wait event liên quan. DBMS_MONITOR giúp bật hoặc tắt trace theo session, client identifier, service, module và action. TKPROF đọc raw trace file rồi trình bày số liệu theo từng câu SQL để người vận hành dễ phân tích.

Ba thành phần này giải quyết ba phần việc khác nhau:

- **SQL Trace:** ghi lại hoạt động thực thi và chờ của session/cursor.
- **DBMS_MONITOR:** xác định phạm vi và thời điểm bật/tắt trace.
- **TKPROF:** định dạng và tổng hợp raw trace thành báo cáo dễ đọc.

Trace rất hữu ích khi cần biết một SQL tiêu tốn CPU, I/O, parse hay thời gian chờ nào. Tuy nhiên, trace có overhead và có thể chứa SQL text, bind values cùng dữ liệu nhạy cảm. Cần giới hạn đúng đối tượng, thời gian và quyền truy cập file.

## 1. SQL Trace ghi lại những gì?

SQL Trace là cơ chế chẩn đoán của Oracle Database. Nó ghi lại các lời gọi SQL và một số hoạt động liên quan trong session được theo dõi.

Các loại lời gọi chính:

- **PARSE:** Oracle phân tích câu SQL, kiểm tra cú pháp, object, quyền và tìm hoặc tạo cursor.
- **EXEC:** ứng dụng yêu cầu thực thi cursor.
- **FETCH:** ứng dụng lấy các dòng kết quả từ cursor.
- **WAIT:** session chờ một sự kiện như đọc block, ghi redo, lock hoặc tài nguyên khác.
- **STAT:** thông tin thống kê theo operation/row source khi trace plan statistics được thu thập.
- **BINDS:** thông tin bind có thể xuất hiện khi bật tracing bind phù hợp.

Một câu SELECT có thể có một lần parse, một lần execute và nhiều lần fetch. Nếu ứng dụng fetch theo từng trang, trace sẽ cho thấy nhiều lời gọi fetch. Nếu ứng dụng chỉ lấy một phần kết quả, tổng số dòng fetch có thể thấp hơn số dòng mà truy vấn có khả năng trả về.

Trace cũng có thể ghi recursive SQL do database thực hiện thay cho câu lệnh ứng dụng, chẳng hạn thao tác dictionary, trigger, PL/SQL hoặc các bước nội bộ. Trường dep (depth) trong raw trace giúp phân biệt một số lời gọi lồng nhau.

### 1.1 SQL Trace và wait events

Khi bật waits, trace có thể ghi lại các lần session chờ. Mỗi wait thường có tên event, thời lượng và một số tham số mô tả đối tượng hoặc block liên quan.

Ví dụ các event có thể gặp:

- **db file sequential read:** thường liên quan single-block read, chẳng hạn đọc block qua index/table access.
- **db file scattered read:** thường liên quan multiblock read trong một số kiểu scan.
- **direct path read temp, direct path write temp:** truy cập TEMP, có thể liên quan sort/hash spill.
- **log file sync:** session chờ xác nhận commit từ redo.
- **enq: TX - row lock contention:** chờ khóa hàng trong một số tình huống transaction.
- **SQL*Net message from client:** session đang chờ client gửi yêu cầu tiếp theo; không tự động có nghĩa database bị nghẽn.

Tên wait event là manh mối, không phải kết luận. Cần xem số lần chờ, tổng thời gian, thời lượng từng lần, SQL/call tương ứng và ngữ cảnh ứng dụng.

### 1.2 Trace ghi theo lời gọi, không phải chỉ theo câu SQL

Một câu SQL có thể xuất hiện nhiều lần trong trace hoặc có nhiều cursor. Cần phân biệt:

- Một SQL statement.
- Một cursor được parse.
- Một lần execute.
- Nhiều lần fetch.
- Recursive SQL phát sinh từ statement.
- Wait xảy ra trong từng call.

Vì vậy, không nên cộng thời gian của các dòng một cách tùy tiện. Hãy dùng TKPROF để xem tổng hợp theo call, rồi quay lại raw trace khi cần dựng thứ tự sự kiện chi tiết.

## 2. Khi nào nên dùng SQL Trace?

SQL Trace phù hợp khi cần trả lời các câu hỏi cụ thể:

- SQL tiêu tốn CPU hay thời gian chờ?
- Thời gian nằm ở parse, execute hay fetch?
- Câu SQL có phát sinh nhiều lần parse hoặc library cache miss không?
- Có nhiều physical reads hoặc consistent gets không?
- Session chờ event nào và chờ trong bao lâu?
- Một request của ứng dụng gọi những SQL nào?
- Trigger, PL/SQL hoặc recursive SQL có đóng góp đáng kể không?
- Hai lần chạy cùng SQL khác nhau ở số call, wait hoặc số dòng như thế nào?

SQL Trace đặc biệt hữu ích khi một sự cố chỉ xảy ra với một session, một người dùng, một service hoặc một luồng nghiệp vụ cụ thể. Khi đã có SQL_ID và runtime statistics nhưng vẫn chưa biết thứ tự parse/execute/fetch hoặc wait chi tiết, trace có thể bổ sung bằng chứng.

Không nên bật trace toàn database chỉ vì một màn hình ứng dụng chậm. Hãy xác định một session, client identifier hoặc module/action đủ hẹp để thu thập dữ liệu trong thời gian ngắn.

## 3. DBMS_MONITOR quản lý trace như thế nào?

DBMS_MONITOR là package Oracle cung cấp các thủ tục bật và tắt SQL Trace theo phạm vi.

Các phạm vi thường dùng:

| Phạm vi | Cách nhận diện | Khi phù hợp |
|---|---|---|
| Session | SID và SERIAL# | Điều tra một session cụ thể |
| Client identifier | CLIENT_IDENTIFIER | Theo dõi một người dùng/request logic qua connection pool |
| Service/module/action | Service, module, action | Theo dõi một luồng nghiệp vụ của ứng dụng |
| Database | Toàn database/instance theo API tương ứng | Điều tra có kiểm soát khi cần phạm vi rộng |

Các thủ tục trace phổ biến:

- **DBMS_MONITOR.SESSION_TRACE_ENABLE** và **SESSION_TRACE_DISABLE**.
- **DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE** và **CLIENT_ID_TRACE_DISABLE**.
- **DBMS_MONITOR.SERV_MOD_ACT_TRACE_ENABLE** và **SERV_MOD_ACT_TRACE_DISABLE**.
- **DBMS_MONITOR.DATABASE_TRACE_ENABLE** và **DATABASE_TRACE_DISABLE**.

Tên tham số và khả năng hỗ trợ có thể thay đổi theo release. Hãy đối chiếu package specification của phiên bản đang chạy trước khi đưa lệnh vào runbook vận hành.

## 4. Bật trace cho session hiện tại

Cách đơn giản nhất là bật trace trong chính session đang tái hiện sự cố.

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    waits => TRUE,
    binds => FALSE
  );
END;
/
~~~

Sau đó thực hiện đúng thao tác hoặc câu SQL cần theo dõi. Khi hoàn tất, tắt trace:

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
~~~

Trong ví dụ:

- **waits => TRUE** yêu cầu ghi wait events.
- **binds => FALSE** không ghi bind values; đây là mặc định an toàn hơn cho nhiều tình huống.
- Có thể bật binds trong một lần thử có kiểm soát nếu thực sự cần phân tích bind behavior và đã xử lý quyền truy cập dữ liệu.

Nếu quên tắt trace, session tiếp tục tạo trace file cho các hoạt động sau đó. Điều này làm file lớn hơn và khiến việc xác định phạm vi sự cố khó hơn.

### 4.1 Bật trace cho một session khác

DBA có thể bật trace cho một session bằng SID và SERIAL#:

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    session_id => 123,
    serial_num => 456,
    waits      => TRUE,
    binds      => FALSE
  );
END;
/
~~~

Sau khi hoàn thành, tắt trace trên cùng session:

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_DISABLE(
    session_id => 123,
    serial_num => 456
  );
END;
/
~~~

SID có thể được tái sử dụng sau khi session kết thúc. Vì vậy, hãy kiểm tra cả SERIAL# và xác nhận đúng session ngay trước khi bật trace. Trong RAC, cần xác định instance chứa session và dùng tham số instance phù hợp nếu package procedure của release hỗ trợ.

Có thể tra cứu session bằng các view động khi có quyền:

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       service_name,
       module,
       action,
       client_identifier
FROM v$session
WHERE username = 'APP_USER';
~~~

Trong môi trường RAC, dùng GV$SESSION và thêm INST_ID để phân biệt session trên từng instance.

## 5. Theo dõi theo client identifier

Ứng dụng dùng connection pool thường tái sử dụng một database session cho nhiều request. Bật trace theo SID có thể theo dõi nhầm request tiếp theo nếu connection được trả về pool rồi dùng lại.

Client identifier giúp nhận diện người dùng hoặc request logic độc lập với session vật lý. Ứng dụng cần đặt identifier trên connection trước khi xử lý request.

Ví dụ trong session ứng dụng:

~~~sql
BEGIN
  DBMS_SESSION.SET_IDENTIFIER('ORDER_SUPPORT_501');
END;
/
~~~

DBA bật trace cho identifier đó:

~~~sql
BEGIN
  DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE(
    client_id => 'ORDER_SUPPORT_501',
    waits     => TRUE,
    binds     => FALSE
  );
END;
/
~~~

Khi hoàn tất:

~~~sql
BEGIN
  DBMS_MONITOR.CLIENT_ID_TRACE_DISABLE(
    client_id => 'ORDER_SUPPORT_501'
  );
END;
/
~~~

Client identifier có thể được dùng để nhóm hoạt động của cùng một logical client qua nhiều session, tùy cách ứng dụng quản lý và gán identifier.

Ứng dụng phải đặt identifier đúng lúc và xóa hoặc thay thế nó khi connection được trả về pool. Nếu identifier cũ còn sót lại, request sau có thể bị gắn nhầm danh tính và trace có thể bao gồm hoạt động không liên quan.

Lệnh SET_IDENTIFIER trong ví dụ phải chạy trên session ứng dụng cần nhận diện. Chạy nó trong session DBA không làm các session ứng dụng khác tự động mang identifier đó.

## 6. Theo dõi theo service, module và action

DBMS_APPLICATION_INFO cho phép ứng dụng gắn nhãn module và action vào session. Đây là cách hữu ích để phân biệt các luồng nghiệp vụ dùng chung một service.

Ví dụ, ứng dụng đặt module/action:

~~~sql
BEGIN
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => 'OrderService',
    action_name => 'CreateOrder'
  );
END;
/
~~~

Khi hoàn tất action, ứng dụng có thể cập nhật action mới hoặc xóa module/action theo quy ước instrumentation của hệ thống:

~~~sql
BEGIN
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => NULL,
    action_name => NULL
  );
END;
/
~~~

DBA có thể bật trace cho đúng service, module và action:

~~~sql
BEGIN
  DBMS_MONITOR.SERV_MOD_ACT_TRACE_ENABLE(
    service_name => 'APP_SERVICE',
    module_name  => 'OrderService',
    action_name  => 'CreateOrder',
    waits        => TRUE,
    binds        => FALSE
  );
END;
/
~~~

Tắt trace sau khi thu thập:

~~~sql
BEGIN
  DBMS_MONITOR.SERV_MOD_ACT_TRACE_DISABLE(
    service_name => 'APP_SERVICE',
    module_name  => 'OrderService',
    action_name  => 'CreateOrder'
  );
END;
/
~~~

Tên service phải là service database mà ứng dụng thực sự sử dụng. Module/action phải khớp với giá trị do ứng dụng gán; sai một ký tự có thể khiến không session nào khớp.

Đây thường là phạm vi phù hợp khi sự cố gắn với một endpoint hoặc tác vụ cụ thể. Ví dụ, có thể trace CreateOrder trong khi các action SearchOrders hoặc CancelOrder vẫn chạy bình thường.

### 6.1 Instrumentation trong ứng dụng

Để service/module/action có ích, ứng dụng cần gán chúng nhất quán:

- Service xác định nhóm kết nối hoặc workload.
- Module xác định thành phần ứng dụng.
- Action xác định thao tác đang xử lý.
- Client identifier xác định người dùng hoặc request logic khi cần.

Instrumentation nên được đặt ở ranh giới request hoặc nghiệp vụ và được reset khi kết thúc. Với connection pool, phải bảo đảm context của request trước không rò sang request sau.

Có thể xem các giá trị hiện tại trong V$SESSION:

~~~sql
SELECT sid,
       serial#,
       service_name,
       module,
       action,
       client_identifier
FROM v$session
WHERE username = 'APP_USER';
~~~

## 7. Lấy đường dẫn trace file

Oracle lưu diagnostic trace trong Automatic Diagnostic Repository (ADR). Trace file thường nằm dưới thư mục diagnostic của database hoặc instance.

Trong session đang được trace, có thể xem đường dẫn mặc định:

~~~sql
SELECT name, value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Default Trace File');
~~~

- **Diag Trace** cho biết thư mục trace của ADR.
- **Default Trace File** cho biết file trace mặc định của session hiện tại.

Nếu trace được bật cho một session khác, giá trị Default Trace File trong session DBA không phải file của session mục tiêu. Khi đó cần xác định process tương ứng qua thông tin session/instance và tìm trace file trong ADR. Công cụ ADRCI cũng hỗ trợ liệt kê và quản lý diagnostic files.

Trong RAC, mỗi instance có ADR home riêng. Trace của session chạy trên instance nào sẽ được ghi tại ADR tương ứng của instance đó. Không nên tìm file chỉ trong thư mục của instance đang kết nối nếu session mục tiêu ở instance khác.

Với parallel execution hoặc một số hoạt động dùng nhiều process, có thể có nhiều trace file liên quan. Cần xác định các process và session liên quan trước khi kết luận một file đơn lẻ chứa toàn bộ dấu vết.

## 8. Raw trace file có cấu trúc như thế nào?

Raw trace là dữ liệu chi tiết, không được thiết kế để đọc như báo cáo cuối cùng. Một file có thể chứa các record như:

- PARSING IN CURSOR: thông tin cursor và SQL text.
- PARSE: số liệu của lời gọi parse.
- EXEC: số liệu của lời gọi execute.
- FETCH: số liệu của lời gọi fetch.
- WAIT: wait event và thời gian chờ.
- STAT: thống kê operation khi có plan statistics.
- BINDS: thông tin bind nếu tracing bind được bật.

Một dòng WAIT minh họa có thể có dạng:

~~~text
WAIT #140012345 nam='db file sequential read' ela=1250 p1=7 p2=12345 p3=1
~~~

Đây chỉ là ví dụ rút gọn để nhận diện cấu trúc. Giá trị ela trong raw trace thường được ghi theo microsecond ở các record wait tương ứng; cần xem định dạng trace của release và loại record cụ thể.

Một record PARSE/EXEC/FETCH thường có các trường thể hiện CPU, elapsed, số lần đọc vật lý, consistent gets, current gets, số dòng và timestamp. Các mã số cursor trong trace giúp liên kết call với câu SQL đã parse.

### 8.1 Đọc thứ tự sự kiện

Raw trace giữ thông tin thời điểm và thứ tự tương đối của các call/wait. Khi cần biết session chờ gì giữa execute và fetch, raw trace là bằng chứng chi tiết hơn báo cáo tổng hợp.

Ví dụ, một request có thể:

1. Parse cursor.
2. Execute SQL.
3. Chờ đọc block.
4. Fetch một nhóm dòng.
5. Chờ client.
6. Fetch nhóm tiếp theo.
7. Đóng cursor.

TKPROF có thể tổng hợp các call thành một phần báo cáo theo SQL. Nếu cần dựng timeline chi tiết hoặc phân biệt từng lần chờ, hãy quay lại raw trace.

### 8.2 Recursive SQL

Trace có thể chứa SQL do database thực hiện bên trong một call. Những câu lệnh này có thể đến từ trigger, PL/SQL, dictionary access hoặc hoạt động nội bộ. Trường depth trong trace giúp nhận diện quan hệ lồng nhau.

Khi dùng TKPROF với sys=no, các câu lệnh do SYS phát hành có thể bị loại khỏi báo cáo. Điều này không đồng nghĩa mọi recursive SQL của ứng dụng đều biến mất. Khi cần phân tích hoạt động nội bộ, hãy giữ raw trace và cân nhắc cách lọc.

## 9. TKPROF làm gì?

TKPROF là tiện ích đi kèm Oracle Database/Oracle Client tools để chuyển raw SQL Trace file thành báo cáo dạng văn bản.

Nó giúp:

- Gom các call parse, execute và fetch theo SQL.
- Hiển thị số lần gọi và số liệu CPU/elapsed.
- Hiển thị physical reads, consistent gets và current gets.
- Hiển thị số dòng xử lý.
- Sắp xếp SQL theo tiêu chí như elapsed hoặc CPU.
- Hiển thị một số wait event nếu chọn tùy chọn phù hợp.
- Có thể tạo thêm execution plan bằng tùy chọn EXPLAIN, nhưng plan này không phải bằng chứng chắc chắn về plan gốc đã chạy.

TKPROF không bật trace. Nó chỉ xử lý file trace đã được tạo bởi SQL Trace.

## 10. Chạy TKPROF

Cú pháp tổng quát:

~~~text
tkprof input_trace_file output_report_file [options]
~~~

Ví dụ trên Windows:

~~~text
tkprof "D:\oracle\trace\orders_app.trc" "D:\oracle\trace\orders_app.prf" sort=exeela,fchela sys=no waits=yes
~~~

Ví dụ trên Linux:

~~~bash
tkprof /u01/app/oracle/diag/rdbms/db/DB/trace/orders_app.trc \
       /tmp/orders_app.prf \
       sort=exeela,fchela sys=no waits=yes
~~~

TKPROF thường nằm trong thư mục bin của Oracle Home. Cần chạy từ Oracle Home có tiện ích phù hợp hoặc cấu hình PATH trỏ đúng thư mục.

Một số tùy chọn thường gặp:

| Tùy chọn | Ý nghĩa |
|---|---|
| sort=... | Sắp xếp SQL theo một hoặc nhiều chỉ số |
| sys=yes/no | Có đưa SQL do SYS phát hành vào báo cáo hay không |
| waits=yes/no | Có đưa phần thống kê wait vào báo cáo hay không |
| aggregate=yes/no | Có gộp các cursor/call tương ứng theo quy tắc TKPROF hay không |
| print=n | Giới hạn số statement được in sau khi sắp xếp |
| explain=user/password | Yêu cầu TKPROF giải thích SQL bằng schema được cung cấp |
| table=... | Chỉ định plan table khi dùng EXPLAIN, tùy môi trường |

Tên sort key và tùy chọn cụ thể cần đối chiếu tài liệu TKPROF của Oracle Home đang dùng. Ví dụ exeela thường sắp xếp theo elapsed của execute, còn fchela theo elapsed của fetch.

### 10.1 Vì sao nên sort theo execute và fetch?

Một truy vấn có thể mất phần lớn thời gian ở execute hoặc fetch:

- Execute tốn nhiều CPU hoặc chờ xử lý trước khi trả dòng đầu.
- Fetch tốn thời gian vì phải đọc và truyền nhiều dòng.
- Parse tốn thời gian do hard parse hoặc cursor sharing kém.

Sắp xếp theo exeela và fchela giúp tìm statement có elapsed lớn ở hai giai đoạn chính. Có thể sắp xếp theo CPU, physical reads hoặc consistent gets khi câu hỏi điều tra tập trung vào một tài nguyên cụ thể.

Không có một sort order tốt nhất cho mọi sự cố. Hãy chọn metric theo giả thuyết đang kiểm tra.

### 10.2 Cẩn trọng với tùy chọn EXPLAIN

Tùy chọn explain=user/password yêu cầu TKPROF thực hiện EXPLAIN PLAN cho SQL bằng schema được cung cấp tại thời điểm tạo báo cáo. Kế hoạch đó có thể khác kế hoạch thực tế đã chạy vì statistics, bind, schema, optimizer environment và thời điểm parse khác nhau.

Không dùng plan được tạo bởi tùy chọn EXPLAIN của TKPROF để khẳng định đó là execution plan gốc của lần trace. Muốn xác minh plan đã chạy, lấy cursor plan từ DBMS_XPLAN hoặc các nguồn runtime plan phù hợp.

Ngoài ra, không nên đưa mật khẩu rõ vào command line trên hệ thống nhiều người dùng nếu shell history hoặc process list có thể lưu/hiển thị tham số. Có thể bỏ tùy chọn EXPLAIN khi chỉ cần phân tích call statistics và lấy plan bằng công cụ riêng.

## 11. Hiểu các cột trong báo cáo TKPROF

Báo cáo TKPROF thường trình bày các dòng call như Parse, Execute và Fetch, với các cột phổ biến:

| Cột | Ý nghĩa |
|---|---|
| Count | Số lần call thuộc loại đó |
| CPU | Tổng CPU time của các call |
| Elapsed | Tổng elapsed time của các call |
| Disk | Số physical reads được ghi nhận |
| Query | Consistent gets |
| Current | Current-mode gets |
| Rows | Số dòng được xử lý/trả về ở call tương ứng |

Cần đọc từng loại call trong ngữ cảnh:

- **Parse:** số lần parse, CPU/elapsed và library cache misses nếu được báo cáo.
- **Execute:** số lần thực thi, CPU, elapsed và số liệu I/O/gets phát sinh trong execute.
- **Fetch:** số lần lấy dữ liệu, số dòng trả về và tài nguyên tiêu thụ trong fetch.

Một SELECT thường có nhiều fetch calls. Count của Fetch có thể lớn vì client lấy dữ liệu theo từng batch. Count cao tự nó không chứng minh có lỗi; cần xem số dòng, thời gian và cách client fetch.

### 11.1 CPU và elapsed

CPU là thời gian CPU được dùng cho các call. Elapsed là thời gian trôi qua của các call. Elapsed thường bao gồm cả thời gian chờ trong call.

Nếu elapsed lớn hơn CPU nhiều, phần chênh lệch có thể liên quan wait events hoặc thời gian không chạy CPU. Hãy xem phần wait statistics và raw trace để xác định event cụ thể.

Không nên lấy elapsed trừ CPU rồi gán toàn bộ kết quả cho một wait event mà chưa kiểm tra. Cần xét các wait được ghi nhận, thời gian scheduling, các call lồng nhau và cách thống kê được tổng hợp.

### 11.2 Disk, Query và Current

- **Disk:** physical reads.
- **Query:** consistent gets, thường phản ánh logical reads theo consistent mode.
- **Current:** current-mode gets, thường liên quan block được truy cập ở current mode để đọc/ghi dữ liệu hiện hành.

Một SQL có Disk thấp nhưng Query cao vẫn có thể tiêu tốn nhiều CPU và buffer activity. Một SQL có Current cao có thể liên quan thao tác DML hoặc hoạt động cần current block access.

Đừng chỉ xem Disk rồi kết luận câu SQL không gây tải I/O nội bộ. Buffer gets cũng là tài nguyên quan trọng.

### 11.3 Rows

Rows cho biết số dòng được xử lý hoặc trả về trong các call theo cách TKPROF báo cáo. Với SELECT, tổng số dòng fetch có thể phụ thuộc client có lấy hết kết quả hay không. Với DML, số dòng bị tác động cần được đọc cùng execute count và transaction behavior.

## 12. Đọc phần wait statistics

Khi bật waits và chạy TKPROF với waits=yes, báo cáo có thể hiển thị tổng hợp wait event gắn với các SQL/call.

Ví dụ các nhóm cần chú ý:

- User I/O: chờ đọc/ghi block.
- Concurrency: chờ tranh chấp tài nguyên đồng thời.
- Application: chờ do ứng dụng hoặc lock.
- Commit: chờ liên quan commit/redo.
- Network: chờ trao đổi với client hoặc database link.
- Configuration/Administrative: một số chờ liên quan cấu hình hoặc quản trị.

Không nên chỉ nhìn tên event. Hãy xem số lần wait và tổng thời gian. Một event xuất hiện rất nhiều lần nhưng mỗi lần rất ngắn có thể ít quan trọng hơn một event có vài lần chờ dài.

Ví dụ:

- Nhiều db file sequential read có thể cho thấy nhiều single-block reads, nhưng cần xem tổng thời gian và access path.
- log file sync cao có thể liên quan commit quá thường xuyên hoặc redo latency; cần phân tích transaction pattern và redo subsystem.
- enq: TX - row lock contention cần xác định session giữ lock và transaction liên quan.
- SQL*Net message from client thường biểu thị database đang đợi client gửi thêm công việc; cần phân biệt idle wait với thời gian xử lý SQL.

Raw trace hữu ích để xem một wait xảy ra trước hay sau call nào. TKPROF giúp tổng hợp nhưng có thể làm mất chi tiết timeline.

## 13. Ví dụ quy trình end-to-end cho một session

Giả sử một nhân viên hỗ trợ tái hiện được thao tác tạo đơn hàng trong một session riêng.

### Bước 1: Xác định session

~~~sql
SELECT sid, serial#, username, service_name, module, action
FROM v$session
WHERE username = 'APP_USER';
~~~

Ghi lại SID, SERIAL#, service và instance nếu là RAC.

### Bước 2: Bật trace có waits

Trong session DBA:

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    session_id => 123,
    serial_num => 456,
    waits      => TRUE,
    binds      => FALSE
  );
END;
/
~~~

### Bước 3: Tái hiện một lần thao tác

Yêu cầu ứng dụng chạy đúng thao tác cần điều tra. Ghi timestamp bắt đầu/kết thúc và request identifier để đối chiếu với trace.

### Bước 4: Tắt trace ngay sau khi tái hiện

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_DISABLE(
    session_id => 123,
    serial_num => 456
  );
END;
/
~~~

### Bước 5: Xác định file trace

Dùng ADR để tìm file của process/session được trace. Nếu đang ở chính session được trace, có thể xem V$DIAG_INFO để lấy Default Trace File.

### Bước 6: Tạo báo cáo TKPROF

~~~text
tkprof "D:\oracle\trace\session_123.trc" "D:\oracle\trace\session_123.prf" sort=exeela,fchela sys=no waits=yes
~~~

### Bước 7: Đọc báo cáo và quay lại raw trace

Tìm statement có elapsed, CPU, gets hoặc waits lớn. Với statement quan trọng, lấy SQL_ID/plan phù hợp, kiểm tra runtime plan bằng DBMS_XPLAN và đọc raw trace để hiểu thứ tự call/wait.

Quy trình này giữ trace trong phạm vi một session và một lần tái hiện, giúp báo cáo dễ gắn với sự kiện thực tế.

## 14. Ví dụ theo dõi một request qua connection pool

Với connection pool, SID có thể được dùng lại. Nếu muốn theo dõi request logic, ứng dụng nên đặt client identifier trước khi xử lý.

Trong ứng dụng:

~~~sql
BEGIN
  DBMS_SESSION.SET_IDENTIFIER('SUPPORT_REQ_20261114_001');
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => 'OrderApi',
    action_name => 'CreateOrder'
  );
END;
/
~~~

DBA bật trace theo client identifier:

~~~sql
BEGIN
  DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE(
    client_id => 'SUPPORT_REQ_20261114_001',
    waits     => TRUE,
    binds     => FALSE
  );
END;
/
~~~

Sau khi request hoàn tất, DBA tắt trace:

~~~sql
BEGIN
  DBMS_MONITOR.CLIENT_ID_TRACE_DISABLE(
    client_id => 'SUPPORT_REQ_20261114_001'
  );
END;
/
~~~

Ứng dụng cần xóa identifier/module/action trước khi trả connection về pool, hoặc cập nhật chúng cho request tiếp theo theo một quy ước nhất quán. Nếu không, trace có thể gộp nhầm các request hoặc gắn hoạt động vào sai client.

Đây là ví dụ instrumentation ở mức khái niệm. Trong thực tế, thời điểm bật trace phải được phối hợp để không bỏ lỡ phần request cần đo; nếu bật sau khi request đã chạy xong, trace không thể tái tạo các call đã xảy ra.

## 15. Trcsess khi có nhiều trace file

Một số tình huống, đặc biệt RAC, parallel execution hoặc theo dõi một client qua nhiều session, có thể tạo nhiều trace file. Tiện ích trcsess có thể lọc/gộp các trace file theo session, client identifier, service, module hoặc action tùy tùy chọn được hỗ trợ.

Cú pháp tổng quát:

~~~text
trcsess [output=output_file] [session=...] [clientid=...] [service=...] [module=...] [action=...] trace_files
~~~

Sau khi tạo file trace đã lọc/gộp, có thể chạy TKPROF trên file đó:

~~~text
tkprof "D:\oracle\trace\request.trc" "D:\oracle\trace\request.prf" sort=exeela,fchela waits=yes sys=no
~~~

Hãy xem trợ giúp của trcsess trong Oracle Home cụ thể để xác nhận cách viết bộ lọc và wildcard. Không nên gộp tất cả trace file của database nếu chỉ cần một request, vì báo cáo sẽ có nhiều hoạt động không liên quan.

## 16. Những sai lầm thường gặp khi dùng SQL Trace và TKPROF

| Sai lầm | Hệ quả |
|---|---|
| Bật trace toàn database cho một SQL | Tạo lượng trace lớn và tăng overhead không cần thiết |
| Quên tắt trace | Session tiếp tục ghi file và làm nhiễu dữ liệu |
| Chỉ bật trace cho SID trong connection pool | Có thể theo dõi nhầm request khi session được tái sử dụng |
| Không ghi SID và SERIAL# | Có nguy cơ trace nhầm session nếu SID được tái sử dụng |
| Bật binds mặc định cho mọi phiên | Tăng dữ liệu trace và có thể lộ thông tin nhạy cảm |
| Chỉ đọc TKPROF, không giữ raw trace | Mất chi tiết timeline và một số ngữ cảnh wait |
| Dùng EXPLAIN trong TKPROF làm plan gốc | Plan được giải thích lúc tạo báo cáo có thể khác plan đã chạy |
| Chỉ sort theo elapsed | Có thể bỏ qua SQL tiêu tốn CPU hoặc logical reads lớn |
| Coi mọi wait là lỗi database | Một số wait là trạng thái bình thường hoặc do client |
| Gộp nhiều request vào một trace | Khó xác định statement nào thuộc request cần điều tra |
| Không ghi thời điểm tái hiện | Khó liên kết trace với log ứng dụng |
| Chia sẻ raw trace công khai | Có thể làm lộ SQL text, bind và metadata nhạy cảm |

## 17. Overhead, quyền truy cập và bảo vệ dữ liệu

SQL Trace là công cụ chẩn đoán, không nên bật vô thời hạn trên mọi session. Mức overhead phụ thuộc số lượng call, lượng wait/bind được ghi, workload và môi trường. Bind tracing thường tạo thêm dữ liệu và có thể ghi giá trị nhạy cảm.

Một quy trình an toàn về vận hành:

1. Xác định câu hỏi cần trả lời trước khi bật trace.
2. Chọn phạm vi nhỏ nhất: session, client identifier hoặc service/module/action.
3. Ghi timestamp và định danh request.
4. Bắt đầu trace ngay trước khi tái hiện.
5. Dừng trace ngay sau khi đủ dữ liệu.
6. Kiểm tra dung lượng file và tạo báo cáo.
7. Giữ file theo chính sách retention của tổ chức.
8. Hạn chế người có thể đọc raw trace và báo cáo.
9. Ẩn hoặc loại bỏ bind values và dữ liệu nhạy cảm trước khi chia sẻ.
10. Xóa dữ liệu chẩn đoán khi hết thời hạn lưu giữ được phê duyệt.

Để trace session khác hoặc service/module/action, người vận hành cần quyền phù hợp. Không nên cấp quyền DBA rộng chỉ để một ứng dụng có thể tự bật trace cho session bất kỳ. Hãy dùng tài khoản vận hành và quyền tối thiểu theo chính sách hệ thống.

## 18. SQL Trace so với các công cụ quan sát khác

Các công cụ khác nhau cung cấp góc nhìn khác nhau:

| Công cụ | Góc nhìn chính | Khi hữu ích |
|---|---|---|
| DBMS_XPLAN | Cấu trúc execution plan và runtime row-source stats nếu có | Phân tích access path, cardinality và operation |
| SQL Trace | Parse/execute/fetch và wait theo session/call | Điều tra một lần thực thi hoặc một nhóm session cụ thể |
| TKPROF | Báo cáo tổng hợp từ raw trace | Xếp hạng SQL và so sánh call statistics |
| V$SQL | Thống kê cursor đang có trong shared pool | Tìm SQL tiêu tốn tài nguyên tích lũy |
| SQL Monitor | Tiến trình thực thi chi tiết của SQL đủ điều kiện monitor | Theo dõi SQL dài, parallel hoặc operation phức tạp |
| AWR/ASH | Lịch sử và mẫu hoạt động theo thời gian | Điều tra regression hoặc workload lịch sử khi có quyền sử dụng phù hợp |

Không có công cụ nào thay thế tất cả công cụ còn lại. DBMS_XPLAN trả lời câu hỏi về kế hoạch; trace cho biết call và wait; TKPROF tổng hợp trace; AWR/ASH hỗ trợ nhìn lại workload ở quy mô thời gian rộng hơn.

Khi điều tra một request cụ thể, SQL Trace thường đem lại chi tiết hữu ích. Khi cần tìm SQL gây tải trong cả hệ thống, bắt đầu từ thống kê cursor hoặc công cụ workload-level có thể hiệu quả hơn rồi mới trace một trường hợp đại diện.

## 19. Checklist vận hành

Trước khi bật trace:

- [ ] Đã xác định câu hỏi điều tra và phạm vi cần trace.
- [ ] Đã nhận diện đúng session hoặc client identifier.
- [ ] Nếu dùng SID, đã xác nhận cả SERIAL# và instance.
- [ ] Nếu dùng service/module/action, đã xác minh instrumentation khớp.
- [ ] Đã quyết định có thực sự cần ghi bind values hay không.
- [ ] Đã xác định người có quyền đọc trace file.

Trong khi thu thập:

- [ ] Ghi timestamp bắt đầu và kết thúc.
- [ ] Tái hiện đúng một request hoặc nhóm thao tác cần đo.
- [ ] Theo dõi dung lượng trace.
- [ ] Tắt trace ngay sau khi đủ dữ liệu.

Sau khi thu thập:

- [ ] Xác định đúng file trace trong ADR.
- [ ] Dùng TKPROF với sort key phù hợp.
- [ ] Kiểm tra parse, execute, fetch và wait statistics.
- [ ] Quay lại raw trace khi cần timeline.
- [ ] Xác minh execution plan bằng DBMS_XPLAN.
- [ ] Đối chiếu với log ứng dụng và request identifier.
- [ ] Bảo vệ bind values và dữ liệu nhạy cảm.
- [ ] Lưu hoặc xóa file theo retention policy.

## 20. Kết luận

SQL Trace ghi lại hoạt động parse, execute, fetch và wait của session được theo dõi. DBMS_MONITOR giúp giới hạn trace theo session, client identifier hoặc service/module/action. TKPROF chuyển raw trace thành báo cáo để xem số lần call, CPU, elapsed, physical reads, consistent gets, current gets, rows và wait events.

Khi điều tra hiệu năng, hãy bắt đầu từ một request hoặc session xác định, bật trace trong thời gian ngắn, tắt ngay sau khi tái hiện, rồi đọc TKPROF và raw trace cùng execution plan thực tế. Kết hợp các nguồn này giúp phân biệt công việc SQL, thời gian chờ và hành vi ứng dụng, từ đó đề xuất thay đổi dựa trên bằng chứng có thể kiểm chứng.
