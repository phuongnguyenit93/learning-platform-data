# ALTER SYSTEM, ALTER SESSION và yêu cầu khởi động lại trong Oracle

Oracle Database cho phép thay đổi cấu hình ở nhiều phạm vi. Câu lệnh **ALTER SESSION** thay đổi thiết lập cho session hiện tại. Câu lệnh **ALTER SYSTEM** thay đổi tham số hoặc trạng thái ở phạm vi instance/database theo quyền và loại thao tác. Một số tham số có thể thay đổi khi database đang chạy; một số chỉ được ghi vào SPFILE và có hiệu lực sau khi khởi động lại.

Khi thay đổi một initialization parameter, cần xác định bốn điều:

1. Thay đổi áp dụng cho session hiện tại, session mới, instance hiện tại hay toàn bộ các instance?
2. Tham số là dynamic hay static?
3. Giá trị chỉ cần có hiệu lực trong bộ nhớ, cần lưu vào SPFILE, hay cần cả hai?
4. Có cần restart instance/database hoặc thay đổi service/cluster resource không?

Không phải mọi thay đổi đều cần restart. Ngược lại, cố gắng thay đổi một tham số static bằng ALTER SYSTEM khi instance đang chạy sẽ bị từ chối. Việc dùng sai SCOPE cũng có thể khiến thay đổi chỉ có hiệu lực tạm thời hoặc không được lưu qua lần restart tiếp theo.

Bài học thuộc chủ đề **Vận hành** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Khác biệt giữa ALTER SYSTEM và ALTER SESSION.
- Phạm vi session, instance, database, RAC và CDB/PDB.
- Dynamic/static parameters và ISSYS_MODIFIABLE.
- SCOPE=MEMORY, SCOPE=SPFILE, SCOPE=BOTH.
- SID, DEFERRED, RESET và cấu hình PFILE/SPFILE.
- Xác định tham số có cần restart hay không.
- Kiểm tra cấu hình qua V$PARAMETER và V$SPPARAMETER.
- Quy trình thay đổi, xác nhận, rollback và bảo trì an toàn.
- Bài thực hành SQL trong schema/database lab.

## 1. Hai lớp cấu hình: session và system

Oracle duy trì các giá trị cấu hình ở nhiều phạm vi. Có thể hình dung:

~~~text
Initialization parameter in SPFILE/PFILE
                 |
                 v
         Instance runtime value
                 |
                 v
       Session-level override
                 |
                 v
       Current SQL operation
~~~

SPFILE/PFILE cung cấp giá trị cấu hình khi instance khởi động. Instance nạp các giá trị đó vào bộ nhớ. Một số tham số cho phép từng session ghi đè bằng ALTER SESSION. Thay đổi session không tự ghi ngược vào instance hoặc SPFILE.

### ALTER SESSION

ALTER SESSION thay đổi thuộc tính hoặc tham số cho session đang kết nối. Ví dụ:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
ALTER SESSION SET CURRENT_SCHEMA = SALES;
ALTER SESSION SET optimizer_mode = ALL_ROWS;
~~~

Thay đổi này không tác động session khác, không cập nhật giá trị hệ thống và không tự tồn tại sau khi session kết thúc.

### ALTER SYSTEM

ALTER SYSTEM thay đổi tham số ở phạm vi system/instance hoặc thực hiện thao tác quản trị hệ thống. Ví dụ:

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = BOTH;
~~~

Lệnh trên yêu cầu thay đổi OPEN_CURSORS ở bộ nhớ và ghi vào SPFILE, nếu tham số cho phép thay đổi động và instance sử dụng SPFILE. Phạm vi thực tế còn phụ thuộc SID/container và loại tham số.

### Không phải mọi thứ trong ALTER SYSTEM đều là initialization parameter

ALTER SYSTEM còn có các lệnh vận hành khác, chẳng hạn:

~~~sql
ALTER SYSTEM CHECKPOINT;
ALTER SYSTEM SWITCH LOGFILE;
ALTER SYSTEM ENABLE RESTRICTED SESSION;
~~~

Các lệnh này thực hiện hành động quản trị, không phải thay đổi giá trị initialization parameter. Vì vậy, khái niệm SCOPE=MEMORY/SPFILE/BOTH chỉ áp dụng cho cú pháp ALTER SYSTEM SET parameter, không áp dụng cho mọi câu ALTER SYSTEM.

## 2. ALTER SESSION: thay đổi cho session hiện tại

ALTER SESSION thường dùng để điều chỉnh cách session diễn giải dữ liệu, tối ưu SQL, định dạng, thời gian hoặc hành vi thực thi trong một kết nối.

### Cú pháp cơ bản

~~~sql
ALTER SESSION SET parameter_name = value;
~~~

Không phải mọi initialization parameter đều có thể đặt ở session. Cần kiểm tra thuộc tính ISSES_MODIFIABLE hoặc tài liệu parameter.

### Ví dụ NLS

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
~~~

Các tham số NLS ảnh hưởng việc chuyển đổi/hiển thị dữ liệu trong session. Ứng dụng nên truyền datatype đúng và dùng format model tường minh thay vì phụ thuộc vào NLS_DATE_FORMAT mặc định.

### Ví dụ optimizer

~~~sql
ALTER SESSION SET optimizer_mode = ALL_ROWS;
ALTER SESSION SET optimizer_index_cost_adj = 50;
~~~

Ví dụ thứ hai chỉ dùng nếu tham số có thể đặt trong session ở phiên bản đang chạy. Không thay đổi optimizer parameters toàn cục chỉ để ép một query; ưu tiên kiểm tra plan, statistics và SQL-specific controls trước.

### Ví dụ CURRENT_SCHEMA

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES;
~~~

CURRENT_SCHEMA thay đổi schema mặc định khi phân giải tên object không có owner. Nó không cấp thêm quyền trên schema SALES. User vẫn phải có privilege cần thiết để truy cập object.

### Ví dụ time zone

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';
~~~

Session time zone ảnh hưởng một số thao tác với TIMESTAMP WITH LOCAL TIME ZONE và hàm liên quan. Nó không thay đổi DBTIMEZONE hoặc time zone của OS.

### Ví dụ bật thống kê thực thi

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

STATISTICS_LEVEL có thể làm Oracle thu thập thêm runtime statistics/advisory data tùy mức. Dùng có mục tiêu trong phiên kiểm tra; cân nhắc overhead và khôi phục giá trị ban đầu sau thử nghiệm.

### Xem giá trị session

~~~sql
SELECT name, value
FROM v$ses_optimizer_env
WHERE sid = SYS_CONTEXT('USERENV', 'SID')
ORDER BY name;
~~~

V$SES_OPTIMIZER_ENV tập trung vào optimizer environment của session, không phải danh sách mọi tham số session. Với initialization parameters, V$PARAMETER phản ánh giá trị instance hiện tại; một số session-modifiable values có thể được quan sát qua session-specific views hoặc truy vấn phù hợp của release.

### Session pool và reset cấu hình

Ứng dụng dùng connection pool thường tái sử dụng session. Nếu request A đặt CURRENT_SCHEMA, NLS_DATE_FORMAT, TIME_ZONE hoặc optimizer setting rồi trả connection về pool mà không reset, request B có thể nhận session với trạng thái còn sót lại.

Thiết kế pool cần:

- Đặt session state rõ ràng khi lấy connection.
- Reset state khi trả connection về pool hoặc dùng callback/init SQL.
- Không giả định session mới cho mỗi request.
- Không đặt session-specific setting bằng ALTER SYSTEM để sửa lỗi của một request.

## 3. ALTER SYSTEM SET: thay đổi initialization parameter

ALTER SYSTEM SET dùng để thay đổi giá trị một initialization parameter ở phạm vi instance/system.

### Cú pháp tổng quát

~~~sql
ALTER SYSTEM SET parameter_name = value
    [COMMENT = 'text']
    [DEFERRED]
    [SCOPE = MEMORY | SPFILE | BOTH]
    [SID = '*' | 'instance_name']
    [CONTAINER = CURRENT | ALL];
~~~

Không phải mọi clause đều có trên mọi Oracle release hoặc áp dụng cho mọi loại parameter. Dùng cú pháp theo tài liệu phiên bản thực tế.

### Ví dụ thay đổi tham số động

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = BOTH;
~~~

Nếu OPEN_CURSORS được phép thay đổi động, giá trị mới có thể có hiệu lực trong instance hiện tại và được ghi vào SPFILE để tồn tại sau restart. Session đã mở cursor có thể không bị đóng chỉ vì giới hạn mới thay đổi; tham số điều khiển giới hạn cursor mỗi session.

### COMMENT

~~~sql
ALTER SYSTEM SET open_cursors = 500
    SCOPE = SPFILE
    COMMENT = 'Change ticket CHG-1042';
~~~

COMMENT có thể lưu mô tả cùng entry trong SPFILE để giúp DBA nhận diện lý do thay đổi. Ghi mã change ticket và mục đích, không ghi password hoặc secret.

### Thay đổi nhiều tham số

Có thể thực hiện nhiều ALTER SYSTEM SET riêng biệt. Mỗi câu có thể thành công/thất bại độc lập; không coi một loạt lệnh là transaction có thể rollback bằng ROLLBACK. SPFILE là file cấu hình, không phải bảng transactional.

Trước khi thay đổi nhiều tham số, lưu snapshot cấu hình và xác định thứ tự/điều kiện restart. Nếu một lệnh thất bại giữa chừng, so sánh giá trị runtime và SPFILE để biết phần nào đã được áp dụng.

## 4. SCOPE=MEMORY, SPFILE và BOTH

SCOPE quyết định thay đổi được áp dụng ở đâu.

| SCOPE | Tác động | Sau restart |
| --- | --- | --- |
| MEMORY | Thay đổi giá trị runtime trong bộ nhớ instance hiện tại, nếu parameter cho phép | Mất; instance nạp lại giá trị từ file cấu hình |
| SPFILE | Ghi giá trị vào SPFILE, không thay đổi runtime hiện tại | Có hiệu lực khi instance khởi động lại |
| BOTH | Thay đổi runtime và ghi vào SPFILE | Tiếp tục có hiệu lực sau restart |

### SCOPE=MEMORY

~~~sql
ALTER SYSTEM SET open_cursors = 600 SCOPE = MEMORY;
~~~

Thay đổi chỉ áp dụng trong bộ nhớ instance. Nó hữu ích để thử một giá trị động mà không muốn lưu bền vững. Khi restart, giá trị từ SPFILE/PFILE được nạp lại.

### SCOPE=SPFILE

~~~sql
ALTER SYSTEM SET open_cursors = 600 SCOPE = SPFILE;
~~~

Lệnh chỉ ghi vào SPFILE. V$PARAMETER có thể tiếp tục hiển thị giá trị runtime cũ cho tới lần restart phù hợp. V$SPPARAMETER cho biết giá trị được lưu trong SPFILE.

### SCOPE=BOTH

~~~sql
ALTER SYSTEM SET open_cursors = 600 SCOPE = BOTH;
~~~

Lệnh áp dụng thay đổi runtime và lưu trong SPFILE. Đây là cách thường dùng cho parameter động khi muốn thay đổi có hiệu lực ngay và giữ sau restart.

### Parameter static chỉ có thể đặt trong SPFILE

Tham số không thể thay đổi động khi instance đang chạy thường cần:

~~~sql
ALTER SYSTEM SET parameter_name = value SCOPE = SPFILE;
~~~

Sau đó restart instance để giá trị mới có hiệu lực. Không dùng SCOPE=BOTH cho tham số static.

### Khi khởi động bằng PFILE

Nếu instance được khởi động bằng PFILE thay vì SPFILE, thao tác yêu cầu ghi SPFILE có thể thất bại với lỗi như ORA-32001. Trong cấu hình này, SCOPE=MEMORY có thể áp dụng thay đổi runtime động; muốn giữ qua restart, DBA phải chỉnh PFILE được dùng khi startup hoặc chuyển sang SPFILE theo quy trình.

### Không dựa vào default SCOPE

Default SCOPE có thể phụ thuộc việc instance dùng SPFILE/PFILE và loại parameter. Trong script production, ghi SCOPE tường minh để người đọc biết thay đổi chỉ runtime, chỉ persistent hay cả hai.

## 5. Dynamic và static initialization parameters

Không phải mọi initialization parameter đều có thể thay đổi khi instance đang chạy. Oracle mô tả khả năng thay đổi bằng thuộc tính ISSYS_MODIFIABLE trong V$PARAMETER:

| ISSYS_MODIFIABLE | Ý nghĩa |
| --- | --- |
| IMMEDIATE | Có thể thay đổi bằng ALTER SYSTEM khi instance đang chạy; thay đổi có hiệu lực ngay theo semantics của parameter. |
| DEFERRED | Có thể thay đổi khi instance đang chạy nhưng chỉ áp dụng cho session bắt đầu sau thời điểm thay đổi. |
| FALSE | Không thể thay đổi động; phải ghi giá trị vào SPFILE/PFILE và restart để có hiệu lực. |

Một số parameter còn có ISSES_MODIFIABLE cho biết có thể dùng ALTER SESSION hay không. Đây là thuộc tính khác với ISSYS_MODIFIABLE.

### Kiểm tra parameter cụ thể

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isses_modifiable,
       isinstance_modifiable,
       ispdb_modifiable,
       isdefault,
       ismodified,
       isadjusted
FROM v$parameter
WHERE name IN (
    'open_cursors',
    'processes',
    'sessions',
    'sga_target',
    'memory_target',
    'db_block_size',
    'optimizer_mode'
)
ORDER BY name;
~~~

Không đoán static/dynamic theo tên hoặc kinh nghiệm từ một phiên bản khác. Kiểm tra đúng database release, platform và parameter.

### Ví dụ parameter dynamic

OPEN_CURSORS thường là parameter có thể thay đổi động:

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = BOTH;
~~~

Sau đó kiểm tra V$PARAMETER và V$SPPARAMETER để xác nhận runtime/persistent values.

### Ví dụ parameter static

PROCESSES là ví dụ parameter thường cần restart để thay đổi:

~~~sql
ALTER SYSTEM SET processes = 800 SCOPE = SPFILE;
~~~

Giá trị mới chỉ được nạp khi instance restart. Thay đổi PROCESSES có thể ảnh hưởng cấu hình SESSIONS, process limit, memory và ứng dụng; phải tính toán capacity trước khi sửa.

### ORA-02095

Khi cố thay đổi parameter không thể sửa động bằng ALTER SYSTEM SET với SCOPE=MEMORY hoặc BOTH, Oracle có thể trả ORA-02095: specified initialization parameter cannot be modified. Kiểm tra ISSYS_MODIFIABLE; nếu FALSE, ghi vào SPFILE và lên kế hoạch restart.

### Parameter có thể điều chỉnh nhưng không có nghĩa nên điều chỉnh

Một parameter có ISSYS_MODIFIABLE=IMMEDIATE vẫn có thể ảnh hưởng toàn instance, shared pool, memory, optimizer hoặc các session đang chạy. Khả năng thay đổi không đồng nghĩa thay đổi không rủi ro. Đọc tài liệu parameter và đo tác động trước khi chỉnh.

## 6. DEFERRED: thay đổi chỉ áp dụng cho session mới

Một parameter có ISSYS_MODIFIABLE=DEFERRED có thể được thay đổi trong lúc instance đang chạy, nhưng giá trị mới được áp dụng cho các session bắt đầu sau khi thay đổi. Các session đã tồn tại tiếp tục dùng giá trị cũ.

Ví dụ minh họa với parameter có hỗ trợ deferred modification:

~~~sql
ALTER SYSTEM SET parameter_name = value DEFERRED SCOPE = BOTH;
~~~

Không chạy nguyên văn ví dụ này vì parameter_name/value chỉ là placeholder. Kiểm tra ISSYS_MODIFIABLE và tài liệu tham số cụ thể trước khi dùng DEFERRED.

### Vì sao có deferred parameters?

Một số thiết lập được đọc hoặc cố định khi session khởi tạo. Thay đổi chúng giữa vòng đời session có thể gây hành vi không nhất quán. Oracle vì vậy cho phép thay đổi mặc định cho session tương lai mà không ép các session đang hoạt động đổi trạng thái giữa chừng.

### Cách xác nhận

1. Mở session A.
2. DBA thay đổi một parameter hỗ trợ DEFERRED.
3. Session A tiếp tục dùng giá trị đã nhận khi nó khởi tạo.
4. Mở session B sau thay đổi.
5. Session B nhận giá trị mới theo parameter.

Để xác minh, dùng view/session instrumentation phù hợp với parameter đó; không giả định V$PARAMETER luôn hiển thị mọi session-level effective value.

### DEFERRED không phải restart

DEFERRED có nghĩa là session mới, không phải instance mới. Nếu parameter có ISSYS_MODIFIABLE=DEFERRED, thay đổi có thể có hiệu lực cho session mới mà không restart instance. Nếu ISSYS_MODIFIABLE=FALSE, cần restart; thêm từ khóa DEFERRED không làm parameter static trở thành dynamic.

## 7. Khi nào phải restart?

Một parameter cần restart khi Oracle đánh dấu ISSYS_MODIFIABLE=FALSE hoặc tài liệu parameter quy định thay đổi chỉ có hiệu lực lúc startup. Trong trường hợp đó:

1. Ghi giá trị mới vào SPFILE bằng SCOPE=SPFILE.
2. Kiểm tra giá trị đã lưu trong V$SPPARAMETER.
3. Chọn maintenance window và xác định tác động downtime.
4. Shutdown/startup instance theo quy trình vận hành.
5. Xác nhận giá trị runtime sau startup.
6. Kiểm tra alert log, service, PDB, application connection và workload.

### Ví dụ chuẩn bị thay đổi static parameter

~~~sql
ALTER SYSTEM SET processes = 800 SCOPE = SPFILE;

SELECT name, value, isspecified
FROM v$spparameter
WHERE name = 'processes';
~~~

V$SPPARAMETER phản ánh giá trị lưu trong SPFILE. Nếu instance đang dùng PFILE, lệnh ghi SPFILE có thể không thành công; cần xác định file khởi động thực tế.

### Restart instance

Trong môi trường single-instance được quản lý trực tiếp:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP;
~~~

Đây là thao tác gây gián đoạn kết nối. SHUTDOWN IMMEDIATE chờ các hoạt động cần thiết theo semantics Oracle, rollback transaction chưa commit và đóng database. Trước khi chạy phải có phê duyệt, xác nhận backup/recovery readiness và thông báo tới owner ứng dụng.

### Oracle RAC / Grid Infrastructure

Với RAC hoặc database được Clusterware/Oracle Restart quản lý, dùng SRVCTL theo quy trình của môi trường để stop/start database hoặc instance. Không tự ý dùng SQL*Plus STARTUP/SHUTDOWN trên một instance do Clusterware quản lý nếu điều đó đi ngược quy trình vận hành.

Ví dụ cú pháp SRVCTL thay đổi theo release:

~~~text
srvctl stop instance -db <db_unique_name> -instance <instance_name>
srvctl start instance -db <db_unique_name> -instance <instance_name>
~~~

Xác nhận đúng syntax bằng srvctl help trên Oracle Home đang dùng. Với rolling changes, cần xem parameter có thể khác giữa các instance và tác động đến service placement.

### Restart database hay chỉ restart PDB?

Trong multitenant, một số parameter có thể được đặt ở PDB scope; một số khác chỉ có hiệu lực ở CDB/instance scope. Không giả định parameter static ở PDB luôn yêu cầu restart toàn CDB hoặc có thể được áp dụng bằng cách đóng/mở PDB. Kiểm tra ISPDB_MODIFIABLE, container scope và tài liệu parameter.

## 8. SID và cấu hình nhiều instance (RAC)

Trong Oracle RAC, nhiều instance cùng mở một database. SPFILE có thể chứa giá trị mặc định áp dụng cho tất cả instance và giá trị riêng cho từng SID.

### SID='*'

~~~sql
ALTER SYSTEM SET open_cursors = 600
    SCOPE = SPFILE
    SID = '*';
~~~

SID='*' chỉ định giá trị dùng chung cho các instance, trừ khi có cấu hình riêng theo instance được ưu tiên theo quy tắc Oracle.

### SID theo instance

~~~sql
ALTER SYSTEM SET open_cursors = 700
    SCOPE = SPFILE
    SID = 'orcl2';
~~~

Ví dụ đặt giá trị riêng cho instance ORCL2. Tên SID phải khớp instance name thực tế; không dùng service name hoặc DB_UNIQUE_NAME thay thế nếu chúng không phải SID.

### Xem các entry SPFILE theo SID

~~~sql
SELECT sid,
       name,
       value,
       isspecified
FROM v$spparameter
WHERE name = 'open_cursors'
ORDER BY sid;
~~~

### Xem instance hiện tại

~~~sql
SELECT instance_name,
       host_name,
       version,
       status
FROM v$instance;
~~~

### RAC và runtime propagation

Thay đổi parameter ở một instance không có nghĩa mọi instance đã nhận cùng giá trị runtime. Phải kiểm tra từng instance, xác định parameter có modifiable ở instance scope hay không và dùng SID/Clusterware đúng cách. Với parameter static, giá trị SPFILE có thể được ghi trước rồi áp dụng khi từng instance restart.

### Rolling restart

Một số thay đổi có thể triển khai theo từng instance trong RAC để giảm downtime; một số thay đổi yêu cầu tất cả instance dừng hoặc có thứ tự đặc biệt. Không giả định mọi static parameter đều rolling-compatible. Kiểm tra Oracle documentation, RAC rolling patch/upgrade guidance và application service behavior.

## 9. PFILE và SPFILE

Oracle có hai dạng file khởi tạo phổ biến:

- **PFILE:** file text có thể chỉnh sửa bằng editor ở hệ điều hành, thường có tên init.ora.
- **SPFILE:** server parameter file dạng nhị phân do Oracle quản lý; dùng ALTER SYSTEM SET để cập nhật entry.

Khi khởi động, Oracle đọc PFILE hoặc SPFILE để tạo instance. SPFILE thường được ưu tiên nếu có ở vị trí mặc định và môi trường được cấu hình dùng nó.

### Xác định instance dùng SPFILE nào

~~~sql
SHOW PARAMETER spfile;

SELECT value
FROM v$parameter
WHERE name = 'spfile';
~~~

Nếu VALUE không rỗng, instance được khởi động từ SPFILE. Nếu rỗng, instance thường được khởi động từ PFILE hoặc nguồn cấu hình khác theo cơ chế của platform.

### Tạo PFILE từ SPFILE

~~~sql
CREATE PFILE = '/tmp/initORCL.ora' FROM SPFILE;
~~~

PFILE được tạo ở filesystem phía database server. Đường dẫn không phải máy client. Đây là bản text hữu ích để kiểm tra/lưu snapshot cấu hình; bảo vệ file nếu chứa thông tin nhạy cảm.

### Tạo SPFILE từ PFILE

~~~sql
CREATE SPFILE FROM PFILE = '/tmp/initORCL.ora';
~~~

Lệnh tạo SPFILE từ PFILE theo vị trí mặc định nếu không chỉ định đường dẫn. Cần quyền SYSDBA và tuân theo trạng thái instance/cách triển khai. Trong RAC, SPFILE dùng chung thường được đặt ở ASM/shared location theo cấu hình Clusterware.

### Khởi động với PFILE tường minh

~~~sql
STARTUP PFILE = '/tmp/initORCL.ora';
~~~

Đường dẫn PFILE là server-side. Nếu cần khởi động từ một file cấu hình cụ thể, xác nhận file tồn tại, quyền đọc và tham số hợp lệ trước khi dừng instance.

### Vì sao SCOPE=SPFILE thất bại?

Nếu instance không được khởi động bằng SPFILE, ALTER SYSTEM SET ... SCOPE=SPFILE có thể trả ORA-32001. Khi đó:

1. Xác nhận nguồn startup bằng SHOW PARAMETER SPFILE.
2. Nếu quy trình yêu cầu SPFILE, tạo SPFILE từ PFILE theo kế hoạch.
3. Nếu vẫn dùng PFILE, sửa PFILE được dùng khi startup bằng quy trình OS có kiểm soát.
4. Không giả định sửa một file init.ora bất kỳ sẽ ảnh hưởng instance nếu instance đang đọc file khác.

### Quản lý version của cấu hình

Trước thay đổi quan trọng, export PFILE snapshot hoặc lưu bản SPFILE backup theo quy trình DBA. Lưu timestamp, database/instance, change ticket và người thực hiện. Không đưa password hoặc secret vào kho source code.

## 10. Kiểm tra runtime value và SPFILE value

V$PARAMETER phản ánh giá trị parameter hiện tại trong instance. V$SPPARAMETER phản ánh các entry được lưu trong SPFILE. Hai giá trị có thể khác nhau nếu vừa thay đổi SCOPE=SPFILE hoặc SCOPE=MEMORY.

### So sánh hai nguồn

~~~sql
SELECT p.name,
       p.value AS runtime_value,
       s.value AS spfile_value,
       p.issys_modifiable,
       p.isses_modifiable,
       p.isdefault,
       p.ismodified
FROM v$parameter p
LEFT JOIN v$spparameter s
  ON s.name = p.name
 AND s.sid IN ('*', (SELECT instance_name FROM v$instance))
WHERE p.name IN (
    'open_cursors',
    'processes',
    'sessions',
    'sga_target',
    'memory_target'
)
ORDER BY p.name;
~~~

Trong RAC, có thể có nhiều entry cho cùng parameter theo SID. Query trên chỉ minh họa việc đối chiếu; cần xử lý trường hợp nhiều SID/default override rõ ràng.

### Xem toàn bộ parameter

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isses_modifiable,
       isinstance_modifiable,
       ispdb_modifiable,
       isdefault,
       ismodified,
       isadjusted
FROM v$parameter
ORDER BY name;
~~~

### Tìm parameter static

~~~sql
SELECT name, value, issys_modifiable
FROM v$parameter
WHERE issys_modifiable = 'FALSE'
ORDER BY name;
~~~

Danh sách thay đổi theo release và platform. Dùng truy vấn này để khám phá, không coi đây là danh sách đầy đủ mọi parameter có restart requirement trong mọi tình huống.

### Tìm parameter có thể thay đổi trong session

~~~sql
SELECT name, value, isses_modifiable
FROM v$parameter
WHERE isses_modifiable = 'TRUE'
ORDER BY name;
~~~

Parameter có thể session-modifiable không nhất thiết có thể ALTER SYSTEM hoặc ngược lại. Chọn câu lệnh theo đúng phạm vi cần thay đổi.

### Xem giá trị hợp lệ

Một số parameter có danh sách giá trị hợp lệ trong V$PARAMETER_VALID_VALUES:

~~~sql
SELECT name, value, isdefault
FROM v$parameter_valid_values
WHERE name = 'optimizer_mode'
ORDER BY value;
~~~

Không phải parameter nào cũng có tập giá trị enum; một số nhận số, chuỗi, path hoặc biểu thức. Tài liệu parameter là nguồn xác nhận cuối cùng.

## 11. ALTER SYSTEM RESET và khôi phục giá trị mặc định

ALTER SYSTEM RESET xóa entry của parameter khỏi SPFILE để Oracle dùng giá trị mặc định hoặc giá trị được kế thừa theo cấu hình ở lần startup tiếp theo. Nó không phải lệnh rollback dữ liệu và thường không làm thay đổi runtime value ngay.

### Reset entry trong SPFILE

~~~sql
ALTER SYSTEM RESET open_cursors
    SCOPE = SPFILE
    SID = '*';
~~~

Trong RAC, SID xác định entry cần xóa; SID='*' xóa entry mặc định dùng chung, còn SID instance cụ thể có thể dùng cho override riêng. Cần xem V$SPPARAMETER trước để tránh xóa nhầm cấu hình.

### Reset không có nghĩa đặt về một con số cố định

Sau reset, Oracle dùng default hoặc giá trị được xác định bởi parameter precedence/configuration của release và instance. Giá trị mặc định có thể khác theo memory sizing, platform, CDB/PDB và phiên bản. Kiểm tra V$PARAMETER sau restart.

### Khôi phục từ snapshot

Nếu đã lưu PFILE hoặc snapshot SPFILE, có thể phục hồi entry cũ theo kế hoạch. Không thay thế toàn bộ SPFILE bằng snapshot cũ nếu các thay đổi khác đã được thực hiện sau thời điểm snapshot mà chưa được ghi nhận.

## 12. CDB/PDB: parameter ở phạm vi container

Trong multitenant architecture, một số initialization parameters có thể được đặt riêng cho PDB, một số chỉ có ý nghĩa ở CDB/instance scope. V$PARAMETER có cột ISPDB_MODIFIABLE để chỉ ra khả năng thay đổi theo PDB.

### Kiểm tra PDB modifiability

~~~sql
SELECT name,
       value,
       ispdb_modifiable,
       issys_modifiable
FROM v$parameter
WHERE name IN (
    'open_cursors',
    'sessions',
    'optimizer_mode',
    'nls_date_format'
)
ORDER BY name;
~~~

### Thay đổi parameter ở container hiện tại

Với parameter hỗ trợ PDB scope, cú pháp có thể dùng CONTAINER=CURRENT khi thực hiện từ container phù hợp:

~~~sql
ALTER SYSTEM SET parameter_name = value
    CONTAINER = CURRENT;
~~~

Ví dụ này là cú pháp khái quát; không chạy placeholder. Quy tắc SCOPE, CONTAINER và parameter availability thay đổi theo release. Xác nhận ISPDB_MODIFIABLE, quyền common/local và tài liệu trước khi thay đổi.

### Thay đổi cho tất cả container

Từ CDB root, một số parameter có thể đặt CONTAINER=ALL để áp dụng phạm vi common theo quy tắc multitenant:

~~~sql
ALTER SYSTEM SET parameter_name = value
    CONTAINER = ALL;
~~~

Không phải mọi parameter hỗ trợ CONTAINER=ALL. Không dùng ALL nếu chỉ muốn một PDB. Kiểm tra V$PARAMETER/parameter documentation và current container trước khi thực thi.

### Session-level trong PDB

ALTER SESSION chỉ thay đổi session đang kết nối. Nếu session ở PDB, thay đổi session chỉ tồn tại trong session đó; không làm thay đổi giá trị parameter cho các session khác trong PDB hoặc CDB.

### Lưu trạng thái PDB

Một số thay đổi PDB parameter được lưu theo cơ chế multitenant và có thể tồn tại sau khi PDB đóng/mở; không suy ra mọi parameter đều cần restart CDB. Xác định scope và restart requirement theo chính parameter, PDB state và phiên bản.

## 13. Các thao tác ALTER SYSTEM khác

ALTER SYSTEM còn cung cấp các lệnh vận hành không thay đổi initialization parameter. Những lệnh này có semantics và rủi ro riêng; SCOPE=MEMORY/SPFILE/BOTH không áp dụng cho chúng.

### CHECKPOINT

~~~sql
ALTER SYSTEM CHECKPOINT;
~~~

Yêu cầu Oracle thực hiện checkpoint. Checkpoint ghi dirty buffers theo cơ chế DBWR và cập nhật checkpoint information. Không dùng lệnh này như cách chữa mọi vấn đề I/O hoặc thay thế tuning checkpoint/redo.

### SWITCH LOGFILE

~~~sql
ALTER SYSTEM SWITCH LOGFILE;
~~~

Yêu cầu instance chuyển sang online redo log group tiếp theo. Đây là thao tác thường dùng trong lab hoặc một số quy trình quản trị; không chạy lặp liên tục trong production vì có thể gây log switch quá dày và tăng áp lực archive/checkpoint.

### ARCHIVE LOG CURRENT

~~~sql
ALTER SYSTEM ARCHIVE LOG CURRENT;
~~~

Trong ARCHIVELOG mode, lệnh yêu cầu archive current redo log theo semantics của database. Cần phân biệt với SWITCH LOGFILE và xem trạng thái archive destination. Không dùng để thay thế backup archived redo hoặc kiểm tra khả năng restore.

### Restricted session

~~~sql
ALTER SYSTEM ENABLE RESTRICTED SESSION;
ALTER SYSTEM DISABLE RESTRICTED SESSION;
~~~

Restricted session giới hạn các user thông thường đăng nhập mới theo privilege. Đây có thể là bước bảo trì nhưng không tự động dừng session đã kết nối. Xác định rõ session hiện hữu và application service trước khi bật.

### Kill hoặc disconnect session

~~~sql
ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE;
~~~

Trong RAC, cú pháp có thể thêm instance ID theo release:

~~~sql
ALTER SYSTEM KILL SESSION 'sid,serial#,@inst_id' IMMEDIATE;
~~~

KILL SESSION yêu cầu quyền và thông tin SID/SERIAL# đúng. Session có thể cần thời gian cleanup/rollback; trạng thái KILLED không có nghĩa mọi tài nguyên đã được giải phóng ngay.

DISCONNECT SESSION có thể dùng khi muốn ngắt session theo tùy chọn POST_TRANSACTION hoặc IMMEDIATE:

~~~sql
ALTER SYSTEM DISCONNECT SESSION 'sid,serial#' POST_TRANSACTION;
~~~

Trước khi kill/disconnect, xác định user, module, SQL_ID, transaction, blocker/waiter và tác động nghiệp vụ. Không dùng để xử lý một session chậm mà chưa biết nó đang làm gì.

### FLUSH SHARED_POOL

~~~sql
ALTER SYSTEM FLUSH SHARED_POOL;
~~~

Lệnh flush shared pool có thể loại bỏ nhiều cursor/object khỏi cache, dẫn đến hard parse và tải CPU tăng sau đó. Không chạy tùy tiện trên production để “làm mới plan”. Nếu cần xử lý một SQL cụ thể, dùng phương pháp quản lý cursor/plan phù hợp và có kế hoạch rollback.

### ALTER SYSTEM SET EVENTS

Một số thao tác event/trace có thể dùng ALTER SYSTEM SET EVENTS hoặc DBMS_MONITOR, nhưng cú pháp và phạm vi rất chuyên biệt. Không copy event string từ diễn đàn vào production. Ưu tiên công cụ tracing được hỗ trợ, giới hạn session và thời gian, đồng thời tắt event sau khi thu thập.

## 14. ALTER SESSION cho chẩn đoán và kiểm soát thực thi

ALTER SESSION hữu ích để thử nghiệm có giới hạn trong một session mà không thay đổi cấu hình toàn instance.

### Bật SQL trace cho session

~~~sql
ALTER SESSION SET sql_trace = TRUE;

-- Chạy câu SQL cần điều tra.

ALTER SESSION SET sql_trace = FALSE;
~~~

Trong production, DBMS_MONITOR có thể cung cấp cách bật trace theo session/client/module; kiểm soát bind capture và nơi lưu trace vì có thể chứa dữ liệu nhạy cảm.

### Gắn trace file identifier

~~~sql
ALTER SESSION SET tracefile_identifier = 'ROW473_DIAG';
~~~

Giá trị này giúp nhận diện trace file của session trong ADR trace directory. Nó không đổi vị trí trace destination.

### Bật parallel query/DML cho session

~~~sql
ALTER SESSION ENABLE PARALLEL QUERY;
ALTER SESSION ENABLE PARALLEL DML;
~~~

Các lệnh này cho phép session dùng một số hình thức parallel execution khi plan/hint/resource policy cho phép. Parallel DML còn có điều kiện về transaction và object. Không bật chỉ để tăng tốc một query mà chưa xem CPU, PX server availability, I/O và contention.

### Tắt parallel query/DML trong session

~~~sql
ALTER SESSION DISABLE PARALLEL QUERY;
ALTER SESSION DISABLE PARALLEL DML;
~~~

### Thay đổi optimizer environment tạm thời

~~~sql
ALTER SESSION SET optimizer_mode = ALL_ROWS;
ALTER SESSION SET optimizer_dynamic_sampling = 4;
~~~

Các thay đổi optimizer ở session hữu ích để chẩn đoán plan trong lab hoặc session thử nghiệm. Không biến một thử nghiệm session thành thay đổi toàn hệ thống khi chưa đo workload.

### Đặt schema hiện tại

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = REPORTING;
~~~

CURRENT_SCHEMA chỉ ảnh hưởng cách phân giải tên không qualified. Nó không cấp quyền và không đổi SESSION_USER.

## 15. Quy trình thay đổi parameter an toàn

Một thay đổi cấu hình nên được xử lý như change có kiểm soát:

1. Xác định vấn đề và parameter liên quan; không thay đổi chỉ dựa trên phỏng đoán.
2. Đọc tài liệu parameter đúng Oracle release, platform và architecture.
3. Kiểm tra ISSYS_MODIFIABLE, ISSES_MODIFIABLE, ISINSTANCE_MODIFIABLE và ISPDB_MODIFIABLE.
4. Ghi lại runtime value, SPFILE value, default, instance, container và session.
5. Kiểm tra dependency, giới hạn OS, memory/process capacity, application pool và RAC/Data Guard.
6. Lưu snapshot PFILE/SPFILE hoặc ghi lại giá trị cũ và change ticket.
7. Chọn SCOPE, SID, CONTAINER và DEFERRED phù hợp.
8. Nếu static, ghi SCOPE=SPFILE rồi lên lịch restart theo quy trình.
9. Xác nhận runtime/SPFILE values và alert log sau thay đổi.
10. Đo workload, error rate và tài nguyên; kiểm tra service/PDB/instance.
11. Nếu có regression, khôi phục giá trị cũ bằng đúng scope và restart nếu cần.
12. Ghi kết quả, người thực hiện, thời gian và audit reference.

### Trước khi chạy ALTER SYSTEM SET

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isses_modifiable,
       isinstance_modifiable,
       ispdb_modifiable,
       isdefault,
       ismodified
FROM v$parameter
WHERE name = 'open_cursors';

SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE name = 'open_cursors';

SELECT instance_name, host_name, status
FROM v$instance;

SHOW PARAMETER spfile;
SHOW CON_NAME;
~~~

Các câu truy vấn này cung cấp điểm bắt đầu. Trong RAC, truy vấn từ từng instance hoặc dùng GV$ views để xem toàn cluster; trong CDB, xác nhận container.

### Chọn scope theo mục tiêu

| Mục tiêu | Cách tiếp cận |
| --- | --- |
| Thử trong một session | ALTER SESSION nếu parameter session-modifiable. |
| Thay đổi runtime tạm thời trên instance | ALTER SYSTEM SET ... SCOPE=MEMORY. |
| Lưu cho lần startup sau | ALTER SYSTEM SET ... SCOPE=SPFILE. |
| Thay đổi động ngay và lưu bền vững | ALTER SYSTEM SET ... SCOPE=BOTH. |
| Tham số áp dụng cho session mới | Dùng DEFERRED nếu parameter hỗ trợ. |
| Tham số static | SCOPE=SPFILE và restart. |
| Một instance trong RAC | SID cụ thể theo instance name. |
| Giá trị chung trong RAC | SID='*' theo cấu hình SPFILE. |
| Một PDB | CONTAINER=CURRENT nếu parameter cho phép. |
| Các PDB trong CDB | CONTAINER=ALL nếu parameter cho phép và scope phù hợp. |

## 16. Rollback thay đổi cấu hình

Rollback cấu hình cần biết thay đổi ban đầu đã tác động ở đâu.

### Nếu chỉ đổi MEMORY

Nếu dùng SCOPE=MEMORY, có thể đặt lại giá trị runtime cũ:

~~~sql
ALTER SYSTEM SET open_cursors = 300 SCOPE = MEMORY;
~~~

Khi restart, giá trị SPFILE/PFILE vẫn là nguồn cấu hình persistent.

### Nếu đổi BOTH

Phải khôi phục cả runtime và SPFILE:

~~~sql
ALTER SYSTEM SET open_cursors = 300 SCOPE = BOTH;
~~~

Chỉ đặt lại MEMORY sẽ khiến giá trị mới quay lại ở lần startup sau.

### Nếu đổi SPFILE cho parameter dynamic

Giá trị runtime chưa đổi; có thể ghi lại giá trị cũ vào SPFILE:

~~~sql
ALTER SYSTEM SET open_cursors = 300 SCOPE = SPFILE;
~~~

Hoặc reset entry nếu muốn quay về default:

~~~sql
ALTER SYSTEM RESET open_cursors SCOPE = SPFILE SID = '*';
~~~

### Nếu parameter static

Ghi giá trị cũ vào SPFILE rồi restart theo maintenance plan. Không thể khôi phục hiệu lực runtime của static parameter chỉ bằng ALTER SESSION hoặc SCOPE=MEMORY.

### Không có transaction rollback cho ALTER SYSTEM

ROLLBACK không hoàn tác ALTER SYSTEM SET. Hãy lưu giá trị trước thay đổi và dùng ALTER SYSTEM SET/RESET để khôi phục có chủ đích.

## 17. Lỗi thường gặp và cách xử lý

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| ORA-02095: specified initialization parameter cannot be modified | Parameter không hỗ trợ thay đổi động hoặc cách sửa không hợp lệ | Kiểm tra ISSYS_MODIFIABLE; nếu FALSE, ghi SCOPE=SPFILE và lên lịch restart. |
| ORA-02096: parameter cannot be modified with this option | SCOPE/DEFERRED hoặc clause không phù hợp với parameter | Đọc tài liệu parameter và dùng đúng option được hỗ trợ. |
| ORA-32001: write to SPFILE requested but no SPFILE is in use | Instance khởi động bằng PFILE hoặc không dùng SPFILE | Xác nhận SHOW PARAMETER SPFILE; chỉnh đúng PFILE hoặc chuyển sang SPFILE. |
| ORA-32017: failure in updating SPFILE | Không ghi được SPFILE hoặc cấu hình/đường dẫn gặp vấn đề | Kiểm tra quyền, trạng thái SPFILE, ASM/filesystem và alert log. |
| ORA-00093: specified value must be between ... | Giá trị ngoài range hoặc format không hợp lệ | Kiểm tra V$PARAMETER_VALID_VALUES và tài liệu parameter. |
| ORA-01031: insufficient privileges | User thiếu ALTER SYSTEM hoặc administrative privilege cần thiết | Dùng account vận hành được cấp quyền tối thiểu phù hợp. |
| ORA-01078 khi startup | Oracle không xử lý được một hoặc nhiều initialization parameters | Xem alert log và PFILE/SPFILE; sửa giá trị sai trước khi startup lại. |
| ORA-32004 khi startup | Có parameter obsolete/deprecated trong file cấu hình | Xác định parameter được cảnh báo, kiểm tra tài liệu release và loại bỏ/thay thế theo kế hoạch. |
| Runtime value khác SPFILE value | Đã dùng SCOPE=SPFILE hoặc MEMORY, hoặc có override theo SID | So sánh V$PARAMETER và V$SPPARAMETER, kiểm tra SID/container. |
| Giá trị thay đổi nhưng session cũ không thấy | Parameter dùng DEFERRED hoặc session có override riêng | Kiểm tra ISSYS_MODIFIABLE/ISSES_MODIFIABLE và mở session mới để thử. |
| Thay đổi biến mất sau restart | Chỉ dùng SCOPE=MEMORY hoặc chỉnh nhầm file PFILE | Ghi persistent value bằng SPFILE hoặc cập nhật đúng PFILE startup. |
| Thay đổi SPFILE nhưng chưa có hiệu lực | Dùng SCOPE=SPFILE cho parameter dynamic/static mà chưa restart hoặc session chưa nhận | Kiểm tra ISSYS_MODIFIABLE và yêu cầu restart/session mới. |
| Một RAC instance có giá trị khác | Entry theo SID hoặc runtime chưa đồng bộ | Kiểm tra GV$PARAMETER, V$SPPARAMETER và từng instance. |
| PDB nhận giá trị khác CDB root | Parameter có scope PDB hoặc container override | Kiểm tra ISPDB_MODIFIABLE, CONTAINER clause và current container. |
| Session pool có NLS/schema sai | Session state cũ chưa được reset | Đặt/reset session state khi checkout/checkin connection. |

### Quy trình chẩn đoán ngắn

1. Xác định parameter và giá trị mong muốn.
2. Kiểm tra V$PARAMETER để biết runtime value và ISSYS_MODIFIABLE.
3. Kiểm tra ISSES_MODIFIABLE, ISINSTANCE_MODIFIABLE và ISPDB_MODIFIABLE.
4. Kiểm tra V$SPPARAMETER để biết persistent value và SID entry.
5. Kiểm tra SPFILE/PFILE thực tế, container, instance và quyền.
6. Đọc alert log nếu startup hoặc parameter processing thất bại.
7. Xác định thay đổi cần session mới hay restart.
8. Xác nhận sau thay đổi bằng cả dictionary và workload.

## 18. Bài thực hành: ALTER SESSION và ALTER SYSTEM

Thực hiện trong database lab có quyền phù hợp. Không dùng các bước restart hoặc thay đổi static parameter trên production hay database dùng chung.

### Bước 1: xác định session và instance

~~~sql
SHOW USER;
SHOW CON_NAME;
SHOW PARAMETER spfile;

SELECT instance_name, host_name, status
FROM v$instance;

SELECT sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema,
       sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Ghi lại user, schema, container, instance và nguồn startup.

### Bước 2: thử ALTER SESSION

~~~sql
SELECT SYSDATE FROM dual;

ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

SELECT SYSDATE FROM dual;
~~~

Chỉ định dạng ngày trong session hiện tại thay đổi. Mở session thứ hai và chạy SELECT SYSDATE để thấy session khác không bị thay đổi.

### Bước 3: thử CURRENT_SCHEMA

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = SALES;

SELECT sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Thử truy cập một object SALES mà user hiện tại có quyền. Nếu thiếu quyền, CURRENT_SCHEMA không cấp quyền thay thế GRANT.

Trả về schema ban đầu bằng cách đặt lại giá trị đã ghi nhận trước thử nghiệm.

### Bước 4: kiểm tra một parameter động

~~~sql
SELECT name,
       value,
       issys_modifiable,
       isses_modifiable,
       isinstance_modifiable,
       ispdb_modifiable
FROM v$parameter
WHERE name = 'open_cursors';

SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE name = 'open_cursors';
~~~

Ghi lại giá trị runtime và SPFILE trước khi thay đổi.

### Bước 5: thay đổi runtime trong lab

Nếu OPEN_CURSORS cho phép thay đổi động và tài khoản có quyền:

~~~sql
ALTER SYSTEM SET open_cursors = 500 SCOPE = MEMORY;
~~~

Kiểm tra:

~~~sql
SELECT name, value, issys_modifiable
FROM v$parameter
WHERE name = 'open_cursors';
~~~

SCOPE=MEMORY chỉ áp dụng runtime. Không để lại thay đổi thử nghiệm; khôi phục giá trị cũ đã ghi nhận:

~~~sql
ALTER SYSTEM SET open_cursors = <previous_value> SCOPE = MEMORY;
~~~

Thay placeholder bằng giá trị cũ thật. Không chạy nguyên văn dấu ngoặc nhọn.

### Bước 6: quan sát SPFILE scope

Trong database lab dùng SPFILE, ghi một giá trị thử nghiệm khác:

~~~sql
ALTER SYSTEM SET open_cursors = 550 SCOPE = SPFILE;
~~~

So sánh:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'open_cursors';

SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE name = 'open_cursors';
~~~

Runtime value có thể vẫn là giá trị cũ, trong khi SPFILE value đã là 550. Trước khi restart, khôi phục SPFILE về giá trị cũ:

~~~sql
ALTER SYSTEM SET open_cursors = <previous_value> SCOPE = SPFILE;
~~~

Nếu không khôi phục, giá trị thử nghiệm sẽ được nạp ở lần restart sau. Không thực hiện bước này nếu không chắc giá trị cũ hoặc SPFILE đang được chia sẻ với instance khác.

### Bước 7: xem parameter cần restart

~~~sql
SELECT name,
       value,
       issys_modifiable
FROM v$parameter
WHERE name = 'processes';
~~~

Trong lab có thể lập kế hoạch thay đổi PROCESSES bằng SCOPE=SPFILE. Không restart database chỉ để hoàn thành bài tập nếu không có cửa sổ bảo trì; mục tiêu là nhận biết parameter static và quy trình áp dụng.

~~~sql
ALTER SYSTEM SET processes = 600 SCOPE = SPFILE;
~~~

Sau đó kiểm tra V$SPPARAMETER và khôi phục giá trị cũ trước lần startup tiếp theo nếu không định áp dụng:

~~~sql
ALTER SYSTEM SET processes = <previous_value> SCOPE = SPFILE;
~~~

### Bước 8: dọn trạng thái session

Đóng session lab hoặc đặt lại NLS_DATE_FORMAT/CURRENT_SCHEMA theo giá trị đã ghi nhận. Trong ứng dụng pool, kiểm tra callback reset session state.

## 19. Câu hỏi tự kiểm tra

1. **ALTER SESSION thay đổi phạm vi nào?** Chỉ session hiện tại.
2. **ALTER SYSTEM SET thay đổi phạm vi nào?** Runtime instance/system và/hoặc SPFILE tùy SCOPE, SID và container.
3. **SCOPE=MEMORY có tồn tại sau restart không?** Không.
4. **SCOPE=SPFILE có đổi runtime ngay không?** Không; giá trị có hiệu lực ở lần startup phù hợp.
5. **SCOPE=BOTH làm gì?** Đổi runtime và ghi persistent value vào SPFILE nếu parameter hỗ trợ.
6. **Dynamic parameter có nghĩa gì?** Có thể thay đổi khi instance đang chạy theo mức IMMEDIATE hoặc DEFERRED.
7. **Static parameter có thể thay đổi thế nào?** Ghi vào SPFILE/PFILE và restart để áp dụng.
8. **ISSYS_MODIFIABLE=IMMEDIATE có nghĩa gì?** Thay đổi system parameter có hiệu lực ngay theo semantics của parameter.
9. **ISSYS_MODIFIABLE=DEFERRED có nghĩa gì?** Giá trị mới áp dụng cho session bắt đầu sau thay đổi.
10. **ISSES_MODIFIABLE dùng để làm gì?** Cho biết parameter có thể được thay đổi bằng ALTER SESSION hay không.
11. **V$PARAMETER phản ánh gì?** Giá trị runtime trong instance.
12. **V$SPPARAMETER phản ánh gì?** Entry được lưu trong SPFILE.
13. **PFILE khác SPFILE thế nào?** PFILE là text file; SPFILE là server parameter file do Oracle quản lý.
14. **ORA-32001 thường có nghĩa gì?** Yêu cầu ghi SPFILE nhưng instance không dùng SPFILE.
15. **ORA-02095 thường có nghĩa gì?** Parameter không thể thay đổi động theo cách đã yêu cầu.
16. **SID='*' dùng khi nào?** Đặt giá trị chung cho các instance trong SPFILE/RAC theo cấu hình.
17. **SID='instance_name' dùng khi nào?** Đặt override riêng cho một instance trong RAC.
18. **CONTAINER=CURRENT/ALL có tác dụng gì?** Xác định phạm vi PDB/container cho parameter hỗ trợ multitenant.
19. **ALTER SYSTEM RESET có làm runtime đổi ngay không?** Thông thường nó xóa entry SPFILE; runtime không tự đổi chỉ vì reset.
20. **ALTER SYSTEM có thể ROLLBACK bằng SQL ROLLBACK không?** Không; phải đặt lại giá trị hoặc reset cấu hình.
21. **Tại sao connection pool cần reset ALTER SESSION state?** Session được tái sử dụng và có thể giữ NLS/schema/optimizer settings của request trước.
22. **Mọi static parameter có rolling restart được không?** Không; phải kiểm tra tài liệu và yêu cầu kiến trúc cụ thể.
23. **Tại sao cần so sánh V$PARAMETER và V$SPPARAMETER?** Để phát hiện runtime và persistent values khác nhau.

ALTER SESSION dùng cho thay đổi cục bộ của một kết nối; ALTER SYSTEM SET quản lý giá trị ở phạm vi instance/database và có thể ghi cấu hình persistent. ISSYS_MODIFIABLE, ISSES_MODIFIABLE, ISINSTANCE_MODIFIABLE và ISPDB_MODIFIABLE giúp xác định parameter thay đổi ở phạm vi nào. SCOPE=MEMORY chỉ đổi runtime, SPFILE chỉ lưu cho startup sau, BOTH làm cả hai. Parameter static cần ghi cấu hình và restart; parameter deferred áp dụng cho session mới. Luôn kiểm tra runtime/SPFILE values, SID/container, alert log và workload sau thay đổi, đồng thời chuẩn bị giá trị rollback trước khi sửa production.
