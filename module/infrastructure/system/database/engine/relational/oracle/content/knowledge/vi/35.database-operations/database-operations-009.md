# Theo dõi trạng thái listener, service, database và PDB

Để một ứng dụng kết nối được Oracle Database, nhiều thành phần phải cùng hoạt động đúng: listener phải lắng nghe trên endpoint mạng, database instance phải khởi động và ở trạng thái phù hợp, pluggable database (PDB) phải được mở, database service phải hoạt động và được listener nhận diện, cuối cùng client phải dùng đúng connect descriptor và có thông tin xác thực hợp lệ.

Vì vậy, kiểm tra một lệnh **lsnrctl status** thành công chưa đủ để kết luận ứng dụng có thể kết nối. Listener có thể đang chạy trong khi database đóng; database có thể OPEN nhưng PDB chứa schema ứng dụng đang MOUNTED; PDB có thể OPEN nhưng service ứng dụng chưa được khởi động hoặc chưa đăng ký với listener. Một quy trình vận hành tốt phải kiểm tra từng lớp và phân biệt rõ trạng thái của chúng.

## 1. Bốn lớp cần theo dõi

| Thành phần | Vai trò | Câu hỏi kiểm tra |
|---|---|---|
| Listener | Nhận yêu cầu kết nối Oracle Net và chuyển đến database service/handler phù hợp | Process có chạy, endpoint có lắng nghe và service có được đăng ký không? |
| Database instance/database | Quản lý bộ nhớ, process và dữ liệu; cung cấp trạng thái OPEN/MOUNTED | Instance đã khởi động và database có mở cho hoạt động mong muốn không? |
| PDB | Container chứa schema và dữ liệu của ứng dụng trong kiến trúc multitenant | PDB có OPEN ở chế độ READ WRITE hoặc chế độ phù hợp không? |
| Database service | Tên dịch vụ logic mà client dùng để định tuyến kết nối đến database/PDB | Service có hoạt động, được listener quảng bá và client gọi đúng tên không? |

Luồng kết nối có thể hình dung:

~~~text
Ứng dụng / SQL*Plus
        |
        | host, port, service_name
        v
Oracle Net Listener
        |
        | chọn service và handler
        v
Database instance
        |
        v
PDB chứa schema ứng dụng
        |
        v
Database user / session
~~~

Mỗi lớp có trạng thái và cách kiểm tra riêng. Hãy xác định lớp đầu tiên không đáp ứng trước khi restart hoặc thay đổi cấu hình.

## 2. Listener là gì và hoạt động độc lập ra sao?

Oracle Net Listener là tiến trình nhận kết nối đến từ client. Listener lắng nghe trên một hoặc nhiều protocol address, thường là TCP với host và port như 1521. Khi client yêu cầu một service, listener tìm service handler phù hợp rồi chuyển yêu cầu kết nối đến database instance.

Listener là thành phần độc lập với database instance:

- Listener có thể chạy khi database đang shutdown.
- Database có thể đã OPEN nhưng listener chưa chạy.
- Listener có thể chạy và hiển thị endpoint đúng nhưng chưa biết service của database.
- Một listener có thể phục vụ nhiều database service.
- Một database có thể đăng ký service với listener cục bộ hoặc listener ở máy khác.

Vì vậy, listener up chỉ xác nhận một phần của đường kết nối.

### Các tệp và thành phần liên quan

- listener.ora: cấu hình listener tĩnh, địa chỉ lắng nghe và một số thông tin đăng ký tĩnh nếu có.
- tnsnames.ora: connect identifier/alias phía client hoặc server.
- sqlnet.ora: một số cấu hình Oracle Net như naming methods và các tùy chọn kết nối.
- Listener log: ghi nhận hoạt động listener và yêu cầu kết nối theo cấu hình.
- ADR: Automatic Diagnostic Repository, nơi Oracle lưu log và trace của nhiều thành phần.

Không phải môi trường nào cũng cần khai báo service database thủ công trong listener.ora. Database thường tự đăng ký service động với listener.

## 3. Kiểm tra listener bằng lsnrctl

Trên máy cài Oracle Database hoặc Oracle Grid Infrastructure, dùng tiện ích lsnrctl:

~~~text
lsnrctl status
~~~

Nếu có nhiều listener hoặc listener không dùng tên mặc định, chỉ định tên:

~~~text
lsnrctl status LISTENER
~~~

Lệnh status thường cho biết:

- Listener alias/name.
- Phiên bản listener.
- Thời điểm khởi động.
- Các endpoint đang lắng nghe, ví dụ TCP host/port.
- Đường dẫn listener parameter file.
- Đường dẫn listener log.
- Danh sách service mà listener biết tại thời điểm kiểm tra.

Ví dụ minh họa phần output:

~~~text
Connecting to (DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=dbhost)(PORT=1521)))
STATUS of the LISTENER
------------------------
Alias                     LISTENER
Version                   ...
Start Date                ...
Uptime                    ...
Listening Endpoints Summary...
  (DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=dbhost)(PORT=1521)))
Services Summary...
  Service "orders.example.com" has 1 instance(s).
    Instance "ORCL", status READY, has 1 handler(s) for this service...
The command completed successfully
~~~

Đây là ví dụ định dạng, không phải output cố định. Số endpoint, service, instance và handler phụ thuộc cấu hình thực tế.

### Kiểm tra service và handler

~~~text
lsnrctl services
~~~

Hoặc:

~~~text
lsnrctl services LISTENER
~~~

Lệnh này hiển thị chi tiết hơn về service, instance và handler mà listener đang quản lý. Cần chú ý:

- Service name có đúng với connect descriptor của ứng dụng không?
- Instance nào đang cung cấp service?
- Handler có trạng thái READY hay BLOCKED?
- Có handler nào đang ở trạng thái quá tải hoặc không nhận kết nối không?
- Listener có biết service của PDB ứng dụng hay chỉ biết service khác?

Một service có thể được hiển thị với trạng thái UNKNOWN khi được cấu hình tĩnh. Điều đó không tự động có nghĩa database hỏng; cần hiểu service được đăng ký tĩnh hay động. Với đăng ký động, listener thường nhận trạng thái instance/handler từ database.

### Các lệnh listener thường dùng

| Lệnh | Mục đích |
|---|---|
| lsnrctl status | Xem trạng thái, endpoint và service summary |
| lsnrctl services | Xem service, instance và handler chi tiết |
| lsnrctl start | Khởi động listener |
| lsnrctl stop | Dừng listener |
| lsnrctl reload | Nạp lại cấu hình listener mà không thực hiện stop/start thông thường |
| lsnrctl version | Xem phiên bản listener |
| lsnrctl help | Xem cú pháp và lệnh được hỗ trợ |

lsnrctl stop dừng listener process và ngăn các kết nối mới đi qua listener đó. Các database session đã thiết lập thường vẫn tiếp tục hoạt động, nhưng ứng dụng sẽ không thể dùng listener đó để reconnect hoặc failover cho đến khi listener hoạt động lại. Không chạy stop/start trên production chỉ để thử. Trước khi thay đổi, xác định listener nào đang phục vụ ứng dụng, có listener dự phòng hay không và cửa sổ bảo trì đã được phê duyệt chưa.

## 4. Listener endpoint và cấu hình listener.ora

Một cấu hình TCP listener tối giản có thể có dạng:

~~~ini
LISTENER =
  (DESCRIPTION_LIST =
    (DESCRIPTION =
      (ADDRESS =
        (PROTOCOL = TCP)
        (HOST = dbhost.example.com)
        (PORT = 1521)
      )
    )
  )
~~~

Tên listener và địa chỉ trong ví dụ cần được thay bằng cấu hình của môi trường. HOST có thể là hostname, địa chỉ IP hoặc địa chỉ phù hợp với network design. Trong môi trường nhiều network interface, cần bảo đảm listener bind đúng interface mà client được phép truy cập.

Sau khi thay đổi listener.ora, có thể kiểm tra và nạp cấu hình theo quy trình:

~~~text
lsnrctl status LISTENER
lsnrctl reload LISTENER
lsnrctl status LISTENER
~~~

Reload không thay thế việc xác nhận ứng dụng kết nối thành công. Hãy kiểm tra lại endpoint, service và thử kết nối từ máy client.

### Endpoint không đồng nghĩa firewall đã mở

Listener báo đang lắng nghe trên port 1521 ở máy database không chứng minh client ở mọi mạng đều truy cập được. Firewall, security list, route, DNS, NAT và network ACL có thể chặn đường đi.

Kiểm tra cần thực hiện từ đúng network zone mà ứng dụng sử dụng. Nếu chỉ thử từ localhost của database server, có thể bỏ sót lỗi firewall hoặc DNS giữa application server và database.

## 5. Dynamic service registration

Database thường tự đăng ký thông tin service và instance với listener thông qua tiến trình LREG. LREG gửi thông tin đăng ký để listener biết database service nào có thể nhận kết nối.

Dynamic registration giúp tránh phải khai báo tĩnh từng service trong listener. Thông tin đăng ký có thể chịu ảnh hưởng bởi:

- Listener endpoint được cấu hình.
- LOCAL_LISTENER cho listener cục bộ.
- REMOTE_LISTENER trong một số cấu hình, đặc biệt RAC/SCAN.
- Trạng thái instance và service.
- Trạng thái PDB gắn với service.
- Thời điểm LREG đăng ký hoặc đăng ký lại.

Xem tham số liên quan:

~~~sql
SHOW PARAMETER local_listener;
SHOW PARAMETER remote_listener;
~~~

Trong một số tình huống sau khi sửa cấu hình hoặc khởi động listener, DBA có thể yêu cầu database đăng ký lại:

~~~sql
ALTER SYSTEM REGISTER;
~~~

Lệnh này yêu cầu instance đăng ký service với listener đã cấu hình. Nó không khởi động database, không mở PDB và không tạo service mới. Nếu service chưa hoạt động hoặc listener endpoint sai, REGISTER không tự sửa nguyên nhân gốc.

### LOCAL_LISTENER

LOCAL_LISTENER xác định địa chỉ listener cục bộ mà instance sử dụng để đăng ký động. Giá trị có thể là connect descriptor hoặc tên alias được phân giải theo Oracle Net.

Nếu LOCAL_LISTENER trỏ đến host/port sai, listener có thể đang chạy nhưng database không đăng ký service vào listener mà client đang dùng.

### REMOTE_LISTENER

REMOTE_LISTENER thường xuất hiện trong môi trường RAC, nơi instance đăng ký service với SCAN listener hoặc listener ở vị trí khác theo cấu hình Grid Infrastructure. Không nên tự sửa tham số này nếu database được quản lý bởi Clusterware; dùng công cụ quản trị cluster và theo tài liệu release.

### SERVICE_NAMES và cách quản lý service

Tham số SERVICE_NAMES từng được dùng để chỉ định service name cho database. Từ Oracle Database 19c, Oracle đã deprecate việc khách hàng dùng tham số này để quản lý service; với môi trường cần HA hoặc cluster, hãy quản lý service bằng SRVCTL/DBMS_SERVICE theo mô hình được hỗ trợ, không dựa vào việc sửa SERVICE_NAMES như một cách quản trị service hiện đại.

Trong RAC hoặc môi trường do Grid Infrastructure quản lý, dùng SRVCTL để tạo, cấu hình, start/stop và kiểm tra service. Với database standalone, DBA có thể dùng DBMS_SERVICE theo tài liệu đúng phiên bản khi cần quản lý application service.

## 6. Kiểm tra trạng thái database instance

Sau khi xác nhận listener, đăng nhập vào database bằng một tài khoản có quyền xem trạng thái. Trên máy database, DBA có thể dùng OS authentication nếu đã được cấu hình:

~~~text
sqlplus / as sysdba
~~~

Không dùng SYSDBA credential trong ứng dụng. Đây là quyền quản trị đặc biệt, chỉ dành cho hoạt động DBA có kiểm soát.

### Kiểm tra instance

~~~sql
SELECT instance_name,
       host_name,
       status,
       startup_time
  FROM v$instance;
~~~

Các trạng thái instance thường gặp:

| STATUS | Ý nghĩa khái quát |
|---|---|
| STARTED | Instance đã được khởi động nhưng database chưa mount |
| MOUNTED | Control file đã được mount; database chưa OPEN |
| OPEN | Instance đang mở database |

Một số trạng thái hoặc chi tiết có thể khác theo hoạt động recovery, shutdown hoặc phiên bản. Nếu instance không trả về hàng hoặc không thể kết nối, cần xem process, alert log và trạng thái startup.

### Kiểm tra database

~~~sql
SELECT name,
       db_unique_name,
       open_mode,
       database_role
  FROM v$database;
~~~

OPEN_MODE cho biết database đang ở chế độ mở nào, ví dụ READ WRITE, READ ONLY hoặc MOUNTED. DATABASE_ROLE cho biết vai trò như PRIMARY hoặc PHYSICAL STANDBY. Không thể chỉ nhìn STATUS của instance rồi kết luận database sẵn sàng cho ghi dữ liệu.

Ví dụ:

| Instance status | Database open_mode | Diễn giải |
|---|---|---|
| OPEN | READ WRITE | Database mở cho hoạt động đọc/ghi theo quyền và cấu hình |
| OPEN | READ ONLY | Database mở chỉ đọc |
| MOUNTED | MOUNTED | Database chưa OPEN |
| STARTED | Không có kết quả database phù hợp | Instance đã start nhưng database chưa mount |

Nếu database là standby hoặc đang trong quy trình switchover/failover, READ ONLY/READ WRITE phải được hiểu theo database role và trạng thái Data Guard. Không tự mở database theo chế độ khác với vai trò vận hành.

## 7. Kiểm tra PDB trong CDB

Trong Oracle Multitenant, CDB có thể chứa nhiều PDB. Một PDB có thể đóng trong khi CDB root vẫn OPEN. Vì vậy, database OPEN không đồng nghĩa mọi ứng dụng trong các PDB đều kết nối được.

Từ SQL*Plus kết nối vào CDB root:

~~~sql
SHOW CON_NAME;
SHOW PDBS;
~~~

Hoặc truy vấn:

~~~sql
SELECT name,
       open_mode,
       restricted
  FROM v$pdbs
 ORDER BY name;
~~~

Các trạng thái thường gặp:

| OPEN_MODE | Ý nghĩa |
|---|---|
| MOUNTED | PDB chưa mở |
| READ WRITE | PDB mở cho đọc/ghi |
| READ ONLY | PDB chỉ đọc |

RESTRICTED cho biết PDB có đang ở restricted mode hay không. Một PDB READ WRITE nhưng RESTRICTED = YES có thể chỉ cho phép các session có quyền phù hợp kết nối. Ứng dụng thông thường có thể không đăng nhập được.

### Mở PDB

Nếu PDB phải mở và DBA đã xác nhận thao tác phù hợp:

~~~sql
ALTER PLUGGABLE DATABASE salespdb OPEN;
~~~

Mở tất cả PDB:

~~~sql
ALTER PLUGGABLE DATABASE ALL OPEN;
~~~

Không chạy lệnh OPEN ALL một cách máy móc trên mọi môi trường. Có PDB được thiết kế để đóng, chỉ đọc, phục vụ standby hoặc chỉ mở trong cửa sổ batch.

### Lưu trạng thái mở sau khi restart

Nếu muốn Oracle tự khôi phục trạng thái PDB sau khi CDB restart:

~~~sql
ALTER PLUGGABLE DATABASE salespdb SAVE STATE;
~~~

Hoặc:

~~~sql
ALTER PLUGGABLE DATABASE ALL SAVE STATE;
~~~

Lệnh SAVE STATE lưu trạng thái mở hiện tại của PDB để được khôi phục trong lần startup CDB sau theo cơ chế Oracle. Cần xác định PDB nào thực sự phải tự mở khi khởi động; không lưu trạng thái cho PDB chỉ dùng tạm thời hoặc cần kiểm soát thủ công.

### Đóng PDB

~~~sql
ALTER PLUGGABLE DATABASE salespdb CLOSE IMMEDIATE;
~~~

Đóng PDB sẽ ảnh hưởng session ứng dụng trong PDB đó. Chỉ thực hiện khi có kế hoạch bảo trì, kiểm tra service, xử lý session và xác nhận tác động nghiệp vụ.

## 8. Database service là gì?

Database service là tên logic mô tả workload hoặc điểm kết nối mà client yêu cầu. Service giúp tách cách ứng dụng kết nối khỏi tên instance hoặc SID cụ thể.

Ví dụ một database có thể cung cấp:

- orders_rw.example.com: service cho ứng dụng ghi/đọc đơn hàng.
- reports_ro.example.com: service cho báo cáo chỉ đọc.
- batch.example.com: service cho batch job.

Tên trên chỉ là ví dụ. Service có thể được gắn với database/PDB, thuộc tính workload, role hoặc cấu hình HA theo thiết kế.

### Service name khác SID

SID nhận diện một instance. Service name nhận diện dịch vụ logic mà client muốn truy cập. Trong môi trường nhiều instance hoặc RAC, client nên kết nối bằng service name phù hợp thay vì phụ thuộc vào một SID cố định.

Ví dụ connect descriptor:

~~~text
ORDERS =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = dbhost.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = orders_rw.example.com)
    )
  )
~~~

Client có thể kết nối bằng alias ORDERS trong tnsnames.ora hoặc dùng EZCONNECT:

~~~text
sqlplus app_user@//dbhost.example.com:1521/orders_rw.example.com
~~~

Connect string phải dùng service name đã được DBA cấu hình và listener đăng ký. Không đoán service name từ DB_NAME hoặc SID.

### Service gắn với PDB

Trong Multitenant, application service thường được gắn với một PDB. Khi client kết nối đúng service, session được đưa vào PDB tương ứng. Nếu service không gắn đúng PDB hoặc PDB đang đóng, ứng dụng có thể không kết nối hoặc không truy cập được schema mong muốn.

Oracle tự tạo default service cho PDB. Với ứng dụng production, nên dùng application-defined service được quản lý theo chính sách vận hành/HA, thay vì phụ thuộc vào default PDB service cho mọi workload.

## 9. Kiểm tra service trong database

### Xem service được database biết đến

~~~sql
SELECT name,
       network_name,
       con_id
  FROM v$services
 ORDER BY con_id, name;
~~~

V$SERVICES hiển thị thông tin service trong database. CON_ID giúp xác định container liên quan trong môi trường Multitenant. Các cột cụ thể có thể thay đổi theo release; nếu một phiên bản không có cột được dùng, đối chiếu data dictionary của release đó.

### Xem service đang hoạt động

~~~sql
SELECT name,
       network_name,
       con_id
  FROM v$active_services
 ORDER BY con_id, name;
~~~

V$ACTIVE_SERVICES phản ánh các service đang active trong instance hiện tại. Trong RAC, xem GV$ACTIVE_SERVICES hoặc GV$SERVICES để tổng hợp theo instance; chú ý INST_ID và CON_ID.

### Xem session đang dùng service nào

~~~sql
SELECT username,
       service_name,
       module,
       machine,
       status,
       COUNT(*) AS session_count
  FROM v$session
 WHERE username IS NOT NULL
 GROUP BY username,
          service_name,
          module,
          machine,
          status
 ORDER BY service_name, session_count DESC;
~~~

Truy vấn này giúp thấy service nào đang được session sử dụng. Nó không cho biết service nào được cấu hình nhưng chưa có session.

### Kiểm tra service trong PDB hiện tại

Khi đã kết nối vào PDB:

~~~sql
SHOW CON_NAME;

SELECT name,
       network_name
  FROM v$services
 ORDER BY name;
~~~

So sánh service mà ứng dụng dùng với service của PDB hiện tại. Nếu kết nối nhầm service, có thể ứng dụng đăng nhập thành công nhưng thao tác trên schema/database khác dự kiến.

## 10. Quản lý service bằng SRVCTL trong RAC/Grid Infrastructure

Trong Oracle RAC hoặc môi trường service được Clusterware quản lý, dùng SRVCTL để kiểm tra và vận hành service. Không tự quản lý service cluster bằng cách sửa tham số hoặc dùng DBMS_SERVICE nếu service thuộc quyền quản lý của Grid Infrastructure.

Ví dụ:

~~~text
srvctl status database -db ORCL
srvctl config database -db ORCL
srvctl status service -db ORCL
srvctl config service -db ORCL
~~~

Kiểm tra một service cụ thể:

~~~text
srvctl status service -db ORCL -service orders_rw
srvctl config service -db ORCL -service orders_rw
~~~

Khởi động hoặc dừng service:

~~~text
srvctl start service -db ORCL -service orders_rw
srvctl stop service -db ORCL -service orders_rw
~~~

Tên database và service phải lấy từ cấu hình thật. Cú pháp option có thể khác giữa các phiên bản Grid Infrastructure; dùng srvctl -help hoặc tài liệu đúng release trước khi thực hiện.

### Vì sao nên dùng SRVCTL?

SRVCTL hiểu cấu hình cluster, instance ưu tiên/khả dụng, database role và thuộc tính service. Khi một service được Clusterware quản lý, SRVCTL giữ cấu hình nhất quán và cho phép Clusterware giám sát, khởi động lại hoặc chuyển service theo policy.

Không dùng lsnrctl stop để thay thế việc dừng một database service. Listener có thể phục vụ nhiều service và database khác; dừng listener có phạm vi ảnh hưởng rộng hơn.

## 11. Quản lý service trong database standalone

Trong môi trường standalone không được Clusterware quản lý service, Oracle cung cấp DBMS_SERVICE để quản lý application service theo khả năng của phiên bản.

Ví dụ minh họa tạo và start service trong môi trường phù hợp:

~~~sql
BEGIN
  DBMS_SERVICE.CREATE_SERVICE(
    service_name => 'orders_rw',
    network_name => 'orders_rw.example.com'
  );

  DBMS_SERVICE.START_SERVICE(
    service_name => 'orders_rw'
  );
END;
/
~~~

Đây là ví dụ về API, không phải script dùng chung cho RAC hoặc mọi release. Cần kiểm tra quyền, trạng thái database, PDB và hướng dẫn quản lý service của phiên bản cụ thể. Với service thuộc Grid Infrastructure, dùng SRVCTL.

Service cần được gắn với PDB và thuộc tính phù hợp nếu ứng dụng sử dụng Multitenant. Không chỉ kiểm tra service có tồn tại trong DBA_SERVICES; cần kiểm tra service có active và listener có nhận được đăng ký hay không.

## 12. Kiểm tra từ client: tnsping và kết nối SQL thực tế

### tnsping

~~~text
tnsping ORDERS
~~~

tnsping kiểm tra việc phân giải connect identifier và khả năng tiếp cận listener theo connect descriptor. Nó không thực hiện database authentication, không xác nhận user/password đúng và không chứng minh PDB hoặc service đã sẵn sàng để chạy SQL.

Do đó:

- tnsping thành công nhưng SQL*Plus thất bại: có thể listener reachable nhưng service, database, PDB hoặc authentication có vấn đề.
- tnsping thất bại: kiểm tra alias, naming method, DNS, route, firewall, host và port.

### Thử kết nối thực tế

~~~text
sqlplus -L app_user@//dbhost.example.com:1521/orders_rw.example.com
~~~

Sau khi kết nối, chạy truy vấn nhẹ:

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
  SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Kết quả giúp xác nhận client đã vào đúng database, PDB/container, service và user. Đây là kiểm tra quan trọng hơn chỉ nhìn listener status.

### Kiểm tra từ đúng máy và network zone

Một kết nối thành công từ database server không chứng minh application server kết nối được. Hãy chạy thử từ host hoặc network zone gần với ứng dụng nhất, sử dụng cùng DNS, port, service name và cơ chế xác thực. Nếu có load balancer, SCAN hoặc VIP, hãy kiểm tra đúng endpoint mà ứng dụng dùng.

## 13. Bảng lỗi kết nối thường gặp

| Mã lỗi | Ý nghĩa thường gặp | Hướng kiểm tra đầu tiên |
|---|---|---|
| ORA-12154 | Không phân giải được connect identifier | tnsnames.ora, naming method, alias và TNS_ADMIN |
| ORA-12541 | Không có listener tại endpoint được yêu cầu | Listener process, host, port, firewall và endpoint |
| ORA-12514 | Listener chưa biết service name được yêu cầu | SERVICE_NAME, đăng ký động, trạng thái service/PDB |
| ORA-12505 | Listener không biết SID được yêu cầu | Connect descriptor đang dùng SID hay SERVICE_NAME; kiểm tra SID nếu thật sự cần |
| ORA-12516 / ORA-12519 | Listener không tìm được handler phù hợp hoặc không có handler khả dụng | Handler status, số process/session, tải database và đăng ký service |
| ORA-12545 | Không kết nối được host/object đích | DNS, hostname, route và network |
| ORA-01034 | Oracle instance không khả dụng | Instance status, startup/shutdown và alert log |
| ORA-01033 | Oracle đang khởi tạo hoặc shutdown | Startup/shutdown progress, alert log |
| ORA-01109 | Database chưa mở | V$INSTANCE, V$DATABASE và trạng thái startup |
| ORA-65019 | PDB chưa mở | V$PDBS, OPEN_MODE và trạng thái PDB |
| ORA-01017 | Username/password không hợp lệ | Credential, case, authentication và secret rotation |
| ORA-28000 | Account bị khóa | DBA_USERS, profile và chính sách account |

Thông báo lỗi có thể xuất hiện cùng lỗi gốc khác ở server/client. Không thay đổi listener hoặc mở database chỉ dựa trên mã lỗi; đối chiếu connect descriptor và trạng thái từng lớp.

## 14. Quy trình health check theo lớp

Một runbook kiểm tra kết nối có thể đi theo thứ tự sau:

### Bước 1: xác định endpoint client đang dùng

Thu thập hostname, port, service name, alias, protocol, PDB dự kiến và service name thực tế từ cấu hình ứng dụng. Không lấy SID thay cho service name nếu kiến trúc yêu cầu service.

### Bước 2: kiểm tra listener process và endpoint

~~~text
lsnrctl status LISTENER
lsnrctl services LISTENER
~~~

Xác nhận listener đúng tên, endpoint đúng host/port và không có lỗi rõ ràng.

### Bước 3: kiểm tra instance và database

~~~sql
SELECT instance_name, status, startup_time
  FROM v$instance;

SELECT name, db_unique_name, open_mode, database_role
  FROM v$database;
~~~

Xác định database đã OPEN ở chế độ phù hợp hay đang MOUNTED/READ ONLY.

### Bước 4: kiểm tra PDB

~~~sql
SELECT name, open_mode, restricted
  FROM v$pdbs
 ORDER BY name;
~~~

Xác nhận PDB chứa ứng dụng đang mở và không bị restricted ngoài dự kiến.

### Bước 5: kiểm tra service

~~~sql
SELECT name, network_name, con_id
  FROM v$services
 ORDER BY con_id, name;

SELECT name, network_name, con_id
  FROM v$active_services
 ORDER BY con_id, name;
~~~

Đối chiếu service cấu hình và service active. Với RAC, kiểm tra bằng SRVCTL và các GV$ view khi cần.

### Bước 6: kiểm tra client

~~~text
tnsping ORDERS
sqlplus -L app_user@//dbhost.example.com:1521/orders_rw.example.com
~~~

Thực hiện kết nối từ application host và chạy truy vấn xác nhận DB/PDB/service/user.

### Bước 7: kiểm tra log

Nếu một lớp không đạt, xem listener log, database alert log, Grid Infrastructure log và log ứng dụng quanh cùng thời điểm. Ghi lại timestamp, timezone, host, service, SQL_ID hoặc session khi có.

## 15. Listener log và database alert log

### Listener log

lsnrctl status thường hiển thị đường dẫn listener log. Trong ADR, listener log thường nằm dưới cây:

~~~text
diag/tnslsnr/<host>/<listener_name>/trace/listener.log
~~~

Listener log giúp điều tra:

- Kết nối đến từ client nào.
- Service name được yêu cầu.
- Thời điểm kết nối và lỗi Oracle Net.
- Một số thông tin endpoint và trạng thái listener.

Log có thể chứa hostname, IP, service và metadata kết nối. Hạn chế quyền đọc và xử lý theo chính sách bảo vệ log.

### Database alert log

Alert log ghi lại sự kiện quan trọng như startup/shutdown, lỗi nội bộ, thay đổi trạng thái, recovery và một số cảnh báo. Có thể xem vị trí qua ADR hoặc dùng ADRCI:

~~~text
adrci
show homes
set home diag/rdbms/<db_unique_name>/<instance_name>
show alert -tail 100
~~~

Đường dẫn home phụ thuộc DB name, instance và ADR configuration. Trước khi dùng ADRCI, chọn đúng home từ kết quả show homes.

Nếu database không OPEN, alert log thường là một trong những nguồn đầu tiên cần xem để tìm lỗi startup, mount hoặc recovery.

## 16. Theo dõi trong môi trường RAC

Trong RAC, mỗi instance có thể chạy trên node khác nhau, còn service có thể được phân bố hoặc chuyển giữa các instance theo cấu hình. Cần phân biệt:

- Local listener trên node.
- SCAN listener.
- VIP và địa chỉ mạng public/private.
- Instance đang cung cấp service.
- Service preferred/available instances.
- Database role và service role khi Data Guard được tích hợp.

Các lệnh thường dùng:

~~~text
srvctl status listener
srvctl status scan_listener
srvctl status database -db ORCL
srvctl status service -db ORCL
~~~

Kiểm tra service:

~~~text
srvctl config service -db ORCL -service orders_rw
~~~

Trong database:

~~~sql
SELECT inst_id,
       name,
       network_name,
       con_id
  FROM gv$active_services
 ORDER BY name, inst_id;
~~~

INST_ID giúp biết service active trên instance nào. Một service có thể chạy trên một hoặc nhiều instance tùy policy.

Không dùng lsnrctl stop trên một node như cách dừng service của ứng dụng. Với service được Clusterware quản lý, thao tác qua SRVCTL và quy trình vận hành cluster.

## 17. Theo dõi service trong môi trường Data Guard

Nếu database là primary/standby, service ứng dụng có thể được cấu hình chỉ chạy trên database role phù hợp. Khi switchover hoặc failover, service cần khởi động trên database mới trở thành primary theo thiết kế.

Khi kiểm tra:

- Xem DATABASE_ROLE trong V$DATABASE.
- Xem service có được cấu hình theo role không.
- Xác nhận service active trên database hiện là primary.
- Xác nhận client connect descriptor, DNS, SCAN hoặc endpoint đã chuyển đúng.
- Kiểm tra PDB mở và service gắn với PDB.
- Thử kết nối từ application network.

Không start service ghi dữ liệu trên standby chỉ vì listener hiển thị endpoint. Service phải phù hợp với database role và chính sách Data Guard.

## 18. Theo dõi liên tục và thiết kế cảnh báo

Một hệ thống monitoring nên phân biệt nhiều loại health check:

| Check | Tần suất gợi ý | Cảnh báo khi |
|---|---|---|
| Listener process/endpoint | Theo chu kỳ ngắn phù hợp SLA | Listener không lắng nghe endpoint cần thiết |
| Service registration | Theo chu kỳ | Service ứng dụng không được listener nhận diện |
| Database state | Theo chu kỳ | Instance/database không ở trạng thái mong đợi |
| PDB state | Theo chu kỳ | PDB ứng dụng đóng hoặc restricted ngoài dự kiến |
| Synthetic client login | Theo SLA ứng dụng | Kết nối thật từ application network thất bại |
| Application query | Theo SLA | Truy vấn xác nhận hoặc API health endpoint lỗi |
| Listener/database log | Theo event | Xuất hiện lỗi lặp lại hoặc lỗi nghiêm trọng |

Tần suất cần dựa trên SLA, chi phí truy vấn và khả năng hệ thống giám sát. Không polling các view nặng với tần suất quá cao.

### Health check nên kiểm tra điều gì?

Một check kết nối tốt nên:

1. Dùng đúng endpoint và service name mà ứng dụng dùng.
2. Dùng tài khoản giám sát có quyền tối thiểu.
3. Thực hiện login thật thay vì chỉ tnsping.
4. Chạy một truy vấn nhẹ xác nhận database, PDB và service.
5. Đặt timeout rõ ràng.
6. Không in mật khẩu hoặc token vào log.
7. Trả trạng thái rõ ràng để monitoring phân biệt listener, service, database, PDB và authentication.

Ví dụ truy vấn kiểm tra sau khi đăng nhập:

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_UNIQUE_NAME') AS db_unique_name,
  SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name,
  SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Nếu tài khoản monitoring không có quyền xem V$ view, có thể dùng SYS_CONTEXT để xác nhận ngữ cảnh kết nối mà không cần cấp quyền quản trị rộng.

### Tránh false positive

Một listener không có service ứng dụng có thể là tình trạng bình thường nếu database đang shutdown theo lịch. Một PDB READ ONLY có thể là đúng nếu nó phục vụ báo cáo. Một service không active trên một node có thể bình thường nếu policy chỉ chạy trên node khác.

Monitoring phải so sánh trạng thái thực tế với trạng thái mong đợi của từng môi trường, database role, thời gian bảo trì và service policy. Không dùng một ngưỡng chung cho mọi PDB.

## 19. Các tình huống vận hành thường gặp

### Listener chạy nhưng service không xuất hiện

Kiểm tra:

1. Database instance có OPEN không?
2. PDB chứa service có OPEN không?
3. Service có tồn tại và active không?
4. LOCAL_LISTENER/REMOTE_LISTENER có trỏ đúng endpoint không?
5. Listener đang kiểm tra có đúng listener mà database đăng ký không?
6. LREG đã đăng ký lại chưa?

Sau khi xác nhận cấu hình đúng, có thể yêu cầu đăng ký lại:

~~~sql
ALTER SYSTEM REGISTER;
~~~

Nếu vẫn không xuất hiện, xem alert log, listener log và cấu hình service thay vì lặp lại REGISTER.

### Listener biết service nhưng client nhận ORA-12514

Có thể client đang kết nối đến listener khác, dùng sai service name hoặc service chỉ được đăng ký ở một listener/endpoint khác. So sánh chính xác host, port, service name trong connect descriptor với lsnrctl services tại endpoint client đang truy cập.

### Database OPEN nhưng ứng dụng không kết nối

Kiểm tra PDB, service, handler, account status, password, firewall, service name và giới hạn process/session. Đừng restart database nếu lỗi thực chất là account bị khóa hoặc service chưa được start.

### PDB đóng sau khi CDB restart

Kiểm tra PDB open mode và saved state. Nếu PDB phải tự mở sau restart, xác nhận đã lưu trạng thái bằng SAVE STATE theo thiết kế và alert log không có lỗi mở PDB.

### Service chạy trên node khác

Trong RAC, đây có thể là hành vi mong đợi do service placement hoặc failover. Dùng SRVCTL và GV$ACTIVE_SERVICES để xác định vị trí hiện tại, không suy luận từ một local listener đơn lẻ.

## 20. Thứ tự xử lý sự cố và nguyên tắc thay đổi

Khi kết nối lỗi, nên đi theo thứ tự từ ngoài vào trong:

1. Connect descriptor và DNS/hostname.
2. Network route, firewall và TCP endpoint.
3. Listener process và listening endpoint.
4. Service registration và handler.
5. Database instance và database open mode.
6. PDB open mode và restricted status.
7. Service active và gắn đúng PDB.
8. Authentication, account status và privilege.
9. Ứng dụng, connection pool và transaction.

Không restart toàn bộ database hoặc listener như bước đầu tiên. Restart có thể làm gián đoạn các service khác và che mất bằng chứng nguyên nhân gốc. Hãy thu thập timestamp, lỗi đầy đủ, listener log, alert log, trạng thái instance/PDB/service và kết nối thử nghiệm trước khi thay đổi.

Các lệnh ALTER PLUGGABLE DATABASE, SRVCTL start/stop service, lsnrctl stop/start hoặc thao tác shutdown/startup có thể ảnh hưởng người dùng. Chỉ thực hiện khi có quyền, xác nhận phạm vi và quy trình thay đổi phù hợp.

## 21. Mẫu checklist vận hành

- [ ] Xác định hostname, port, service name và PDB mà ứng dụng cần.
- [ ] Xác nhận đúng listener name và endpoint.
- [ ] Chạy lsnrctl status và lsnrctl services.
- [ ] Kiểm tra listener log nếu có lỗi Oracle Net.
- [ ] Kiểm tra V$INSTANCE và V$DATABASE.
- [ ] Kiểm tra V$PDBS và restricted status.
- [ ] Kiểm tra V$SERVICES và V$ACTIVE_SERVICES.
- [ ] Với RAC, kiểm tra SRVCTL và GV$ACTIVE_SERVICES.
- [ ] Xác nhận LREG registration và LOCAL_LISTENER/REMOTE_LISTENER khi service không xuất hiện.
- [ ] Chạy tnsping từ client để kiểm tra alias/endpoint.
- [ ] Thử login SQL thực tế từ application network.
- [ ] Dùng SYS_CONTEXT xác nhận database, PDB, service và user.
- [ ] Kiểm tra account status, handler và process/session limit nếu login thất bại.
- [ ] Đối chiếu listener log, database alert log và application log.
- [ ] Ghi nhận kết quả, thời điểm, người thực hiện và thay đổi đã áp dụng.

## 22. Kết luận

Theo dõi Oracle listener, service, database và PDB cần được thực hiện như một quy trình nhiều lớp. lsnrctl status xác nhận listener và endpoint; lsnrctl services cho biết service/handler mà listener nhận diện; V$INSTANCE và V$DATABASE phản ánh trạng thái instance/database; V$PDBS cho biết PDB đã mở hay chưa; V$SERVICES, V$ACTIVE_SERVICES và SRVCTL giúp kiểm tra service đang hoạt động và vị trí cung cấp.

Cuối cùng, hãy thử kết nối thật từ application network bằng đúng service name và xác nhận ngữ cảnh bằng SYS_CONTEXT. tnsping chỉ kiểm tra phân giải và tiếp cận listener, không chứng minh database login thành công. Khi sự cố xảy ra, xác định lớp đầu tiên không đạt, đọc listener/database log và chỉ thay đổi service, PDB, listener hoặc instance sau khi đã xác nhận phạm vi ảnh hưởng. Cách tiếp cận này giúp phát hiện đúng nguyên nhân và tránh restart không cần thiết.
