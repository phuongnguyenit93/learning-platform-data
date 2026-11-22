# ORA-12154, ORA-12514, ORA-12541 và chẩn đoán Oracle Net

Khi ứng dụng kết nối Oracle Database, lỗi kết nối thường xuất hiện trước khi câu SQL đầu tiên được thực thi. Ba lỗi Oracle Net thường gặp là **ORA-12154**, **ORA-12541** và **ORA-12514**. Chúng có tên gần giống nhau nhưng xảy ra ở những tầng khác nhau:

- **ORA-12154 — Could not resolve the connect identifier specified:** client không phân giải được alias/connect identifier thành connect descriptor. Thường liên quan tnsnames.ora, sqlnet.ora, TNS_ADMIN, naming method hoặc connect string.
- **ORA-12541 — No listener:** client đã có địa chỉ đích nhưng không tiếp cận được listener tại host/port hoặc IPC key được chỉ định. Thường liên quan listener chưa chạy, sai host/port, DNS, firewall hoặc network path.
- **ORA-12514 — Listener does not currently know of service requested:** client đã tới listener, nhưng listener không biết service name được yêu cầu. Thường liên quan sai SERVICE_NAME, database/PDB/service chưa chạy hoặc dynamic service registration chưa hoàn tất.

Chẩn đoán hiệu quả phải đi theo thứ tự: **phân giải tên → phân giải host/port → kiểm tra listener → kiểm tra service registration → xác thực database session → kiểm tra ứng dụng**. Nếu bỏ qua thứ tự, DBA dễ sửa nhầm listener.ora, thay service name hoặc restart database dù lỗi nằm ở máy client hay network.

Bài học thuộc nhóm **Xử lý sự cố** của Database Engine Relational Oracle. Nội dung tập trung vào Oracle Net architecture, naming methods, connect descriptors, ba lỗi ORA-12154/12514/12541, listener/service registration, PDB/RAC, JDBC connection strings, listener logs, ADR, tracing và runbook chẩn đoán từ client đến database.

Sau bài này, bạn có thể:

- Phân biệt connect identifier, net service name, connect descriptor, SID và SERVICE_NAME.
- Hiểu vai trò của Oracle Net client, listener, LREG và database service.
- Tìm đúng tnsnames.ora và sqlnet.ora mà client thực sự sử dụng.
- Đọc và sửa lỗi cấu trúc trong tnsnames.ora.
- Dùng Easy Connect để tách lỗi alias khỏi lỗi listener/service.
- Phân biệt ORA-12154 với ORA-12541 và ORA-12514.
- Kiểm tra listener bằng lsnrctl status và lsnrctl services.
- Kiểm tra TCP port bằng công cụ của hệ điều hành.
- Kiểm tra service registration qua LREG, LOCAL_LISTENER và REMOTE_LISTENER.
- Đăng ký lại service bằng ALTER SYSTEM REGISTER khi phù hợp.
- Xử lý service của PDB và Oracle RAC.
- Chẩn đoán kết nối từ SQL*Plus, JDBC Thin Driver, connection pool và database link.
- Đọc listener log, SQL*Net log, ADR và trace files.
- Phân biệt tnsping với một lần đăng nhập database thật.
- Xây dựng runbook và thu thập bằng chứng trước khi thay đổi cấu hình.

> **Phạm vi ví dụ:** Nội dung chủ yếu theo Oracle Database 19c. Các host, service, port và đường dẫn trong ví dụ là giả định. Thay bằng giá trị của môi trường thực tế. Không công khai password, wallet, connect descriptor chứa thông tin nhạy cảm hoặc toàn bộ trace/log chưa được che dữ liệu.

## 1. Oracle Net trong một lần kết nối

Oracle Net Services cung cấp cơ chế naming, địa chỉ giao tiếp, listener và các chức năng kết nối giữa client với Oracle Database.

### 1.1. Các thành phần

| Thành phần | Vai trò |
| --- | --- |
| Oracle client | Ứng dụng hoặc công cụ gửi yêu cầu kết nối |
| Connect identifier | Tên hoặc chuỗi kết nối mà client đưa vào |
| Naming method | Cách phân giải connect identifier |
| tnsnames.ora | Repository local chứa net service names |
| sqlnet.ora | Cấu hình Oracle Net client/server, naming order, timeout, security và diagnostics |
| Connect descriptor | Thông tin protocol, host, port và connect data |
| Listener | Tiến trình nhận yêu cầu kết nối ban đầu trên database server |
| LREG | Background process đăng ký service/instance với listener |
| Database service | Tên logical endpoint mà client yêu cầu |
| Database instance | Instance thực thi database workload |
| PDB service | Service dùng để kết nối vào pluggable database phù hợp |

### 1.2. Luồng kết nối tổng quát

~~~text
Java / SQL*Plus / SQL Developer
             |
             v
       Connect identifier
             |
             v
        Naming method
    (TNSNAMES / EZCONNECT / LDAP)
             |
             v
       Connect descriptor
       HOST + PORT + SERVICE
             |
             v
      DNS / Network / TCP
             |
             v
       Oracle Net Listener
             |
             v
     Registered service handler
             |
             v
      Database instance / PDB
             |
             v
       Authentication / Session
~~~

Các lỗi thường gặp có thể được định vị theo luồng:

- ORA-12154: lỗi ở bước naming method, trước khi client có connect descriptor hợp lệ.
- ORA-12541: không tiếp cận được địa chỉ listener trong descriptor.
- ORA-12514: listener nhận được yêu cầu nhưng service name trong connect data chưa được listener biết.

### 1.3. Listener không phải database instance

Listener là tiến trình riêng chạy trên máy database server. Listener nhận yêu cầu và chuyển kết nối tới service handler phù hợp. Database instance có thể đang chạy nhưng listener dừng; khi đó client từ xa vẫn có thể gặp ORA-12541.

Ngược lại, listener có thể chạy bình thường nhưng database service chưa đăng ký; khi đó client có thể gặp ORA-12514.

### 1.4. Service không phải SID

Service name là định danh logical mà ứng dụng nên dùng để kết nối. SID thường nhận diện Oracle instance. Với database hiện đại, đặc biệt RAC và Multitenant, nên ưu tiên service name thay vì phụ thuộc SID.

Ví dụ:

~~~text
(CONNECT_DATA =
  (SERVICE_NAME = sales.example.com)
)
~~~

SERVICE_NAME phải là service mà listener đang biết. Không tự suy luận service name từ DB_NAME, SID, tên PDB hoặc tên host.

## 2. Connect identifier, connect descriptor và net service name

Ba khái niệm này thường bị gọi chung là TNS name nhưng chúng có vai trò khác nhau.

### 2.1. Connect identifier

Connect identifier là giá trị client cung cấp trong lệnh kết nối.

Ví dụ:

~~~text
sqlplus app_user@SALES_PROD
~~~

Trong ví dụ này, SALES_PROD là connect identifier. Nó có thể là alias trong tnsnames.ora, LDAP name hoặc Easy Connect string.

### 2.2. Net service name

Net service name là tên được đặt trong naming repository, ví dụ:

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = db-sales.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = sales.example.com)
    )
  )
~~~

SALES_PROD là alias; phần DESCRIPTION là connect descriptor.

### 2.3. Connect descriptor

Descriptor mô tả cách kết nối:

- Protocol: TCP, TCPS hoặc IPC.
- Host hoặc địa chỉ listener.
- Port hoặc IPC key.
- Service name hoặc thông tin connect data khác.
- Có thể có failover/load-balancing/address list và các tùy chọn bổ sung.

### 2.4. SID và SERVICE_NAME

Ví dụ descriptor dùng service:

~~~text
(CONNECT_DATA =
  (SERVICE_NAME = sales.example.com)
)
~~~

Ví dụ descriptor dùng SID:

~~~text
(CONNECT_DATA =
  (SID = SALES)
)
~~~

Không thay SERVICE_NAME bằng SID chỉ để thử ngẫu nhiên. Hãy xem listener services output và thông tin do DBA cung cấp.

## 3. Các naming methods

Oracle Net có nhiều phương thức phân giải connect identifier.

### 3.1. Local naming — TNSNAMES

Local naming tra alias trong file tnsnames.ora.

Ví dụ:

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db-sales.example.com)(PORT = 1521))
    (CONNECT_DATA = (SERVICE_NAME = sales.example.com))
  )
~~~

Kết nối:

~~~text
sqlplus app_user@SALES_PROD
~~~

### 3.2. Easy Connect

Easy Connect cho phép chỉ định host, port và service trực tiếp, không cần alias trong tnsnames.ora.

Cú pháp phổ biến:

~~~text
//host:port/service_name
~~~

Ví dụ:

~~~text
sqlplus app_user@//db-sales.example.com:1521/sales.example.com
~~~

Easy Connect giúp kiểm tra nhanh liệu lỗi có nằm ở alias TNS hay không. Nếu alias bị ORA-12154 nhưng Easy Connect hoạt động, hãy tập trung kiểm tra naming configuration.

### 3.3. Directory naming — LDAP

Connect identifier được phân giải qua directory server. Cần kiểm tra:

- ldap.ora.
- DIRECTORY_SERVERS.
- DEFAULT_ADMIN_CONTEXT.
- LDAP server host/port và DNS.
- Net service name có tồn tại trong Oracle Context hay không.

Nếu LDAP server không truy cập được hoặc default context sai, alias có thể không được phân giải dù tnsnames.ora không có lỗi.

### 3.4. External naming

Một số môi trường có naming adapter bên ngoài như NIS. Hãy xác định naming method thực sự được cấu hình thay vì giả định mọi client đều dùng TNSNAMES.

### 3.5. NAMES.DIRECTORY_PATH

Trong sqlnet.ora, tham số NAMES.DIRECTORY_PATH xác định thứ tự naming methods được thử.

Ví dụ:

~~~text
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT, LDAP)
~~~

Nếu ứng dụng dùng alias trong tnsnames.ora nhưng TNSNAMES không nằm trong danh sách, Oracle Net có thể không thử local naming.

Nếu ứng dụng dùng Easy Connect nhưng EZCONNECT không được cấu hình trong danh sách, chuỗi kết nối có thể không được phân giải như mong đợi.

Không thay toàn bộ naming path của production chỉ để sửa một client. Kiểm tra policy và các naming methods đang được dùng bởi ứng dụng khác.

## 4. ORA-12154 — Could not resolve the connect identifier specified

### 4.1. Ý nghĩa

ORA-12154 xuất hiện khi Oracle Net không thể chuyển connect identifier thành connect descriptor bằng naming methods được cấu hình.

Ví dụ:

~~~text
ORA-12154: TNS:could not resolve the connect identifier specified
~~~

Lỗi này thường xảy ra trước khi kết nối tới listener. Vì vậy, restart listener hoặc database thường không giải quyết được nguyên nhân.

### 4.2. Nguyên nhân thường gặp

- Alias bị gõ sai hoặc không tồn tại.
- tnsnames.ora không nằm trong thư mục Oracle client đang sử dụng.
- Biến môi trường TNS_ADMIN trỏ tới thư mục khác.
- Có nhiều Oracle Homes và client dùng nhầm home.
- NAMES.DIRECTORY_PATH thiếu TNSNAMES hoặc EZCONNECT.
- File tnsnames.ora có ngoặc không cân bằng hoặc ký tự thừa.
- Alias có domain suffix nhưng connect string không khớp.
- NAMES.DEFAULT_DOMAIN làm tên được nối thêm domain ngoài dự kiến.
- LDAP naming không truy cập được hoặc default context sai.
- JDBC Thin Driver không được cấu hình TNS_ADMIN tương ứng.
- Database link được thực hiện từ database server nhưng server-side Oracle Net config thiếu alias.

### 4.3. Bước 1 — Xác định client nào đang lỗi

Trước tiên xác định:

- Ứng dụng chạy trên máy developer, application server, container hay database server?
- Công cụ dùng Oracle Client, Instant Client hay JDBC Thin Driver?
- Lỗi xuất hiện khi chạy SQL*Plus, SQL Developer, Java application hay database link?
- Các ứng dụng khác trên cùng máy có kết nối được không?

Nếu SQL*Plus trên máy DBA kết nối được nhưng Java app trên server lỗi, không được giả định hai client đang dùng cùng Oracle Net configuration.

### 4.4. Bước 2 — Tìm Oracle client và TNS_ADMIN

Trên Windows PowerShell:

~~~powershell
Get-Command sqlplus -ErrorAction SilentlyContinue
Get-Command tnsping -ErrorAction SilentlyContinue
where.exe sqlplus
where.exe tnsping
$env:ORACLE_HOME
$env:TNS_ADMIN
~~~

Trên Linux/Unix:

~~~bash
which sqlplus
which tnsping
echo "$ORACLE_HOME"
echo "$TNS_ADMIN"
~~~

Kiểm tra đường dẫn:

- Nếu TNS_ADMIN được đặt, Oracle Net dùng thư mục cấu hình được chỉ định theo client/environment.
- Nếu không đặt, client thường tìm trong Oracle Home network admin directory.
- Instant Client cũng có thể dùng TNS_ADMIN để chỉ thư mục cấu hình riêng.

Không chỉnh biến môi trường ở một terminal rồi cho rằng service Windows, application server hoặc container cũng nhận giá trị đó. Mỗi process có environment riêng.

### 4.5. Bước 3 — Kiểm tra tnsnames.ora

Ví dụ:

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS =
      (PROTOCOL = TCP)
      (HOST = db-sales.example.com)
      (PORT = 1521)
    )
    (CONNECT_DATA =
      (SERVICE_NAME = sales.example.com)
    )
  )
~~~

Kiểm tra:

- Alias SALES_PROD có tồn tại chính xác không?
- Có dấu = sau alias không?
- Các ngoặc đơn có cân bằng không?
- ADDRESS có đủ PROTOCOL, HOST và PORT không?
- CONNECT_DATA có đúng SERVICE_NAME không?
- Có dấu ngoặc kép kiểu smart quotes được copy từ tài liệu không?
- Có ký tự lạ hoặc dòng cấu hình bị cắt không?
- Có nhiều alias cùng tên ở nhiều file TNSNAMES khác nhau không?

Oracle Net có thể coi toàn bộ file TNSNAMES không hợp lệ nếu một phần cấu trúc bị lỗi. Hãy kiểm tra cả các entry gần alias đang dùng.

### 4.6. Bước 4 — Kiểm tra sqlnet.ora

Ví dụ:

~~~text
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
~~~

Nếu dùng TNSNAMES, bảo đảm TNSNAMES nằm trong directory path. Nếu dùng Easy Connect, bảo đảm EZCONNECT được cấu hình phù hợp với client.

Kiểm tra thêm:

~~~text
NAMES.DEFAULT_DOMAIN = example.com
~~~

Khi tham số này được cấu hình, tên đơn giản có thể được nối domain. Ví dụ connect identifier SALES_PROD có thể được phân giải thành SALES_PROD.EXAMPLE.COM. Hãy kiểm tra alias trong file có đúng dạng fully-qualified name không.

Không thêm NAMES.DEFAULT_DOMAIN chỉ để làm một alias chạy nếu chưa hiểu ảnh hưởng đến các alias khác.

### 4.7. Bước 5 — Thử Easy Connect

Thay vì:

~~~text
sqlplus app_user@SALES_PROD
~~~

Thử:

~~~text
sqlplus app_user@//db-sales.example.com:1521/sales.example.com
~~~

Nhập password khi SQL*Plus yêu cầu.

Kết quả:

- Easy Connect hoạt động, alias thất bại: ưu tiên kiểm tra TNSNAMES, TNS_ADMIN, NAMES.DIRECTORY_PATH và alias/domain.
- Cả hai cùng lỗi ORA-12541: chuyển sang kiểm tra listener/network.
- Cả hai cùng lỗi ORA-12514: kiểm tra service registration/service name.

### 4.8. Bước 6 — Kiểm tra LDAP naming

Nếu môi trường dùng LDAP:

- Tìm đúng ldap.ora.
- Kiểm tra TNS_ADMIN và LDAP_ADMIN.
- Kiểm tra directory server host/port.
- Kiểm tra DNS.
- Kiểm tra Oracle Context và default context.
- Dùng công cụ directory phù hợp để xác nhận service entry tồn tại.

Không tạo một alias TNS local để né LDAP nếu chính sách tổ chức yêu cầu centralized naming.

### 4.9. Bước 7 — Trường hợp database link

Nếu lỗi xuất hiện khi chạy:

~~~sql
SELECT *
FROM remote_table@sales_link;
~~~

ORA-12154 có thể được phát sinh bởi Oracle Database server đang thực hiện database link, không phải laptop của DBA.

Kiểm tra:

- Database server có đúng Oracle Net naming configuration không?
- TNS_ADMIN của database process có trỏ đúng thư mục không?
- Alias mà database link dùng có tồn tại trên database server không?
- Remote connect descriptor có được cấu hình trong dictionary của database link không?
- Có khác biệt giữa client-side và server-side Oracle Home không?

Xem database link metadata bằng quyền phù hợp, tránh in password:

~~~sql
SELECT
    owner,
    db_link,
    username,
    host
FROM dba_db_links
WHERE db_link LIKE 'SALES_LINK%';
~~~

Không xuất hoặc chia sẻ thông tin secret nếu công cụ quản trị có cung cấp dữ liệu nhạy cảm.

### 4.10. Checklist ORA-12154

- [ ] Đã xác định đúng process/client phát sinh lỗi.
- [ ] Đã xác định Oracle Home hoặc JDBC Thin configuration.
- [ ] Đã kiểm tra TNS_ADMIN.
- [ ] Đã tìm đúng tnsnames.ora.
- [ ] Alias tồn tại và chính xác.
- [ ] Cấu trúc descriptor hợp lệ.
- [ ] NAMES.DIRECTORY_PATH chứa naming method cần dùng.
- [ ] NAMES.DEFAULT_DOMAIN đã được xem xét.
- [ ] Easy Connect đã được thử để tách lỗi naming.
- [ ] Nếu là database link, đã kiểm tra server-side Oracle Net.

## 5. ORA-12541 — TNS: no listener

### 5.1. Ý nghĩa

ORA-12541 có nghĩa client không thể tiếp cận listener tại địa chỉ được chỉ định.

Ví dụ:

~~~text
ORA-12541: TNS:no listener
~~~

Hoặc:

~~~text
ORA-12541: Cannot connect. No listener at host db-sales.example.com port 1521
~~~

Lỗi này cho biết vấn đề nằm ở listener address/reachability. Nó không nói rằng SERVICE_NAME sai; request chưa tới được listener để listener đánh giá service.

### 5.2. Nguyên nhân thường gặp

- Listener chưa được start.
- Listener chạy ở port khác.
- Client trỏ sai host hoặc port.
- DNS phân giải sai hostname.
- Firewall/security group chặn TCP.
- Listener chỉ bind vào địa chỉ khác.
- Listener đang chạy ở Oracle Home khác.
- Windows listener service chưa start.
- Network route/VPN/NAT không đúng.
- Client đi qua SCAN, proxy hoặc Connection Manager nhưng endpoint bị lỗi.
- Listener process dừng hoặc host bị mất kết nối.

### 5.3. Bước 1 — Kiểm tra hostname và port trong descriptor

Ví dụ:

~~~text
(ADDRESS =
  (PROTOCOL = TCP)
  (HOST = db-sales.example.com)
  (PORT = 1521)
)
~~~

Đối chiếu với thông tin listener thực tế trên database server. Không mặc định port luôn là 1521.

### 5.4. Bước 2 — Kiểm tra DNS/host resolution

Windows:

~~~powershell
Resolve-DnsName db-sales.example.com
nslookup db-sales.example.com
~~~

Linux:

~~~bash
getent hosts db-sales.example.com
nslookup db-sales.example.com
~~~

Kiểm tra IP trả về có đúng host/VIP/SCAN IP dự kiến không. Nếu hostname trả nhiều IP, cần xem client đang thử địa chỉ nào và từng địa chỉ có listener hay không.

### 5.5. Bước 3 — Kiểm tra TCP port

Windows:

~~~powershell
Test-NetConnection db-sales.example.com -Port 1521
~~~

Linux:

~~~bash
nc -vz db-sales.example.com 1521
~~~

TcpTestSucceeded = True chỉ chứng minh TCP connection tới port có thể được thiết lập. Nó không xác nhận Oracle service name, authentication hoặc database session hoạt động.

Nếu TCP thất bại:

- Kiểm tra firewall ở client/server/network.
- Kiểm tra security group hoặc network ACL.
- Kiểm tra VPN, route và NAT.
- Kiểm tra listener có đang listen port đó không.

### 5.6. Bước 4 — Kiểm tra listener trên database server

Đăng nhập host database bằng tài khoản quản trị phù hợp:

~~~text
lsnrctl status
~~~

Nếu listener có tên:

~~~text
lsnrctl status LISTENER_SALES
~~~

Kết quả thường cho biết:

- Listener alias.
- Listener version.
- Thời điểm start.
- Listening Endpoints Summary.
- Protocol/host/port.
- Services Summary.
- Listener log file path.

So sánh listening endpoint với host/port trong connect descriptor.

### 5.7. Bước 5 — Start listener khi thực sự dừng

Nếu xác nhận listener cần chạy và được phép start:

~~~text
lsnrctl start
~~~

Hoặc:

~~~text
lsnrctl start LISTENER_SALES
~~~

Sau đó:

~~~text
lsnrctl status LISTENER_SALES
lsnrctl services LISTENER_SALES
~~~

Không start một listener mới theo tên mặc định nếu hệ thống đang dùng listener do Grid Infrastructure quản lý. Trong RAC, dùng SRVCTL/Clusterware theo cấu hình thay vì quản lý listener bằng tay.

### 5.8. Bước 6 — Kiểm tra Windows service

Trên Windows database server:

~~~powershell
Get-Service *Oracle*Listener*
~~~

Hoặc mở Services và kiểm tra service có tên tương ứng với Oracle Home/listener. Tên dịch vụ có thể khác theo phiên bản và Oracle Home.

Nếu listener service dừng, chỉ start đúng service theo quy trình quản trị máy chủ.

### 5.9. Bước 7 — Kiểm tra listener đang bind địa chỉ nào

Listener có thể đang listen:

- Một hostname.
- Một IP cụ thể.
- Một VIP.
- Một port không phải 1521.
- TCPS thay vì TCP.

Dùng output lsnrctl status để xem endpoint thực tế. Nếu cần, kiểm tra socket trên OS:

Linux:

~~~bash
ss -ltnp
~~~

Windows:

~~~powershell
Get-NetTCPConnection -State Listen |
    Where-Object { $_.LocalPort -eq 1521 }
~~~

Không thay HOST trong listener.ora thành 0.0.0.0 hoặc IP tùy tiện khi chưa đánh giá security và topology.

### 5.10. Bước 8 — Kiểm tra firewall

Nếu listener đang listen đúng port nhưng client không tới được:

- Kiểm tra inbound firewall trên database host.
- Kiểm tra outbound policy trên client network.
- Kiểm tra firewall trung gian.
- Kiểm tra cloud security lists/security groups.
- Kiểm tra VPN hoặc subnet route.
- Xác định đúng destination IP nếu DNS có nhiều kết quả.

Mở port chỉ khi đúng endpoint và được phê duyệt. Không tắt firewall toàn máy để thử.

### 5.11. Bước 9 — Kiểm tra RAC/SCAN

Trong RAC, client thường kết nối SCAN listener, sau đó được redirect tới local listener của instance phù hợp.

Kiểm tra:

~~~text
srvctl status scan
srvctl status scan_listener
srvctl status listener
~~~

Tùy cấu hình và quyền quản trị, có thể kiểm tra:

~~~text
srvctl config scan
srvctl config scan_listener
~~~

Nếu client nhận ORA-12541 sau redirect, địa chỉ cuối cùng trong lỗi có thể là VIP/local listener chứ không phải SCAN listener ban đầu. Hãy kiểm tra endpoint được nêu trong error message và listener log.

### 5.12. Checklist ORA-12541

- [ ] Host và port trong descriptor đúng.
- [ ] DNS trả IP đúng.
- [ ] TCP port reachable từ đúng client.
- [ ] Listener đang chạy.
- [ ] Listener listen đúng endpoint.
- [ ] Windows service/Clusterware listener đang hoạt động.
- [ ] Firewall/route cho phép kết nối.
- [ ] SCAN/VIP/redirect endpoint hoạt động nếu dùng RAC.
- [ ] Đã đọc listener status và log.

## 6. ORA-12514 — Listener does not currently know of service requested

### 6.1. Ý nghĩa

ORA-12514 xuất hiện khi listener nhận được yêu cầu kết nối nhưng không biết service name được chỉ định trong connect descriptor.

Ví dụ:

~~~text
ORA-12514: TNS:listener does not currently know of service requested in connect descriptor
~~~

Đây là dấu hiệu listener đã nhận được request. Vì vậy, kiểm tra TCP port thường không phải bước sửa chính. Cần xác định service name có đúng và đã đăng ký với listener hay chưa.

### 6.2. Nguyên nhân thường gặp

- SERVICE_NAME trong tnsnames.ora bị sai.
- JDBC URL dùng nhầm service.
- PDB đang đóng.
- Database instance chưa mở hoặc đang startup.
- Listener mới start nhưng LREG chưa đăng ký service.
- LOCAL_LISTENER trỏ sai listener.
- REMOTE_LISTENER sai trong RAC.
- Service chưa được tạo hoặc chưa được start.
- Service bị stop sau maintenance/failover.
- Client kết nối nhầm listener/port khác với listener đang có service.
- Service registration bị chặn bởi listener configuration.

### 6.3. Bước 1 — Xem service mà listener biết

Trên database server:

~~~text
lsnrctl services
~~~

Hoặc:

~~~text
lsnrctl services LISTENER_SALES
~~~

Ví dụ output:

~~~text
Services Summary...
Service "sales.example.com" has 1 instance(s).
  Instance "sales", status READY, has 1 handler(s) for this service...
    Handler(s):
      "DEDICATED" established: 10 refused: 0 state: ready
~~~

Kiểm tra:

- Service name có xuất hiện không?
- Instance nào đang đăng ký service?
- Instance status có READY không?
- Handler có state READY không?
- Có service đúng nhưng chỉ đăng ký ở listener khác không?

### 6.4. Bước 2 — So sánh SERVICE_NAME trong client

Trong TNSNAMES:

~~~text
SALES_PROD =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)(HOST = db-sales.example.com)(PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = sales.example.com)
    )
  )
~~~

So sánh chính xác sales.example.com với output lsnrctl services.

Không dùng DB_NAME hoặc INSTANCE_NAME thay cho SERVICE_NAME trừ khi descriptor và listener được thiết kế rõ cho kiểu kết nối đó.

### 6.5. Bước 3 — Kiểm tra service từ database

Kết nối local tới database bằng phương thức quản trị phù hợp:

~~~sql
SELECT
    name,
    network_name,
    pdb,
    con_id
FROM v$services
ORDER BY name;
~~~

V$SERVICES cho biết services mà database instance nhận diện. So sánh với service mà listener báo đã đăng ký.

### 6.6. Bước 4 — Kiểm tra instance và PDB

~~~sql
SELECT
    instance_name,
    status,
    database_status
FROM v$instance;

SELECT
    name,
    open_mode
FROM v$pdbs
ORDER BY name;
~~~

Nếu service thuộc PDB đang MOUNTED/CLOSED, ứng dụng có thể không kết nối được service đó.

Mở PDB theo quy trình:

~~~sql
ALTER PLUGGABLE DATABASE salespdb OPEN;
~~~

Đảm bảo trạng thái mở được lưu qua restart nếu yêu cầu:

~~~sql
ALTER PLUGGABLE DATABASE salespdb SAVE STATE;
~~~

Chỉ chạy lệnh mở PDB khi đã xác nhận đúng PDB, đúng CDB và có quyền/phê duyệt.

### 6.7. Bước 5 — Kiểm tra dynamic service registration

Oracle Database dùng background process LREG để đăng ký services và instance information với listener.

Sau khi listener start, việc đăng ký có thể chưa diễn ra ngay. LREG chạy discovery theo chu kỳ; có thể buộc đăng ký ngay:

~~~sql
ALTER SYSTEM REGISTER;
~~~

Sau đó kiểm tra lại:

~~~text
lsnrctl services LISTENER_SALES
~~~

ALTER SYSTEM REGISTER chỉ hữu ích khi instance/service đã sẵn sàng và listener có thể tiếp cận. Nó không sửa service name sai, listener sai port hoặc network không thông.

### 6.8. Bước 6 — Kiểm tra LOCAL_LISTENER

~~~sql
SHOW PARAMETER local_listener;
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN ('local_listener', 'remote_listener');
~~~

LOCAL_LISTENER chỉ ra listener local mà LREG cần đăng ký. Nếu listener chạy port khác 1521 nhưng LOCAL_LISTENER vẫn dùng default hoặc alias không phân giải được, service có thể không đăng ký tại listener mà client đang gọi.

Ví dụ listener custom chạy trên port 1522:

~~~sql
ALTER SYSTEM SET LOCAL_LISTENER =
  '(ADDRESS=(PROTOCOL=TCP)(HOST=db-sales.example.com)(PORT=1522))'
  SCOPE=BOTH;

ALTER SYSTEM REGISTER;
~~~

Ví dụ chỉ minh họa. Trong production, xác nhận SPFILE/PFILE, RAC, listener alias và cấu hình hiện tại trước khi thay đổi.

### 6.9. Bước 7 — Kiểm tra REMOTE_LISTENER trong RAC

Trong RAC, service registration thường liên quan SCAN listeners qua REMOTE_LISTENER.

~~~sql
SHOW PARAMETER remote_listener;
~~~

Kiểm tra:

- SCAN hostname resolve đúng.
- SCAN listeners đang hoạt động.
- REMOTE_LISTENER trỏ đúng SCAN address.
- Local listeners/VIP hoạt động.
- Service được cấu hình cho đúng database/instances.

Không đặt REMOTE_LISTENER thành địa chỉ local listener chỉ để thử. Dùng cấu hình SCAN do Grid Infrastructure quản lý.

### 6.10. Bước 8 — Quản lý service trong Oracle 19c

Từ Oracle Database 19c, việc khách hàng tự quản lý tham số SERVICE_NAMES đã deprecated. Oracle khuyến nghị dùng SRVCTL, GDSCTL hoặc DBMS_SERVICE để quản lý services.

Trong môi trường RAC/Clusterware, kiểm tra service:

~~~text
srvctl config service -db SALESDB
srvctl status service -db SALESDB
~~~

Nếu service được quản lý bởi Clusterware, dùng SRVCTL để start/stop theo cấu hình và chính sách HA:

~~~text
srvctl start service -db SALESDB -service sales_app
~~~

Không tự thêm SERVICE_NAMES vào SPFILE như cách sửa mặc định cho Oracle 19c. Trước khi tạo hoặc start service, xác định service có được quản lý bởi SRVCTL, DBMS_SERVICE, GDS hoặc cloud control plane hay không.

### 6.11. Bước 9 — Kiểm tra service ở đúng listener

Có thể database service xuất hiện ở một listener nhưng client kết nối listener khác:

- Client dùng port 1521 nhưng listener service chỉ đăng ký ở port 1522.
- Local listener khác SCAN listener.
- Có nhiều Oracle Homes/listeners trên cùng host.
- Service registration gửi tới listener không trùng endpoint client đang gọi.

So sánh lsnrctl status và lsnrctl services của đúng listener name, host và port.

### 6.12. Checklist ORA-12514

- [ ] SERVICE_NAME trong connect descriptor đúng.
- [ ] Listener đúng host/port đã nhận request.
- [ ] lsnrctl services có service được yêu cầu.
- [ ] Service handler có trạng thái READY.
- [ ] Instance đang chạy và phù hợp.
- [ ] PDB đã OPEN nếu service thuộc PDB.
- [ ] LREG đã đăng ký service.
- [ ] LOCAL_LISTENER đúng.
- [ ] REMOTE_LISTENER/SCAN đúng nếu RAC.
- [ ] Service được quản lý đúng bằng SRVCTL/DBMS_SERVICE/GDS.
- [ ] Listener log không có lỗi registration liên quan.

## 7. So sánh nhanh ba lỗi

| Tiêu chí | ORA-12154 | ORA-12541 | ORA-12514 |
| --- | --- | --- | --- |
| Giai đoạn | Naming resolution | Listener address/connectivity | Service selection |
| Đã có descriptor hợp lệ? | Chưa phân giải được | Có địa chỉ được thử | Có |
| Đã tới listener? | Không nhất thiết; thường chưa | Không | Có |
| Host/port cần kiểm tra? | Sau khi phân giải được | Có, trọng tâm | Có, nhưng listener đã nhận request |
| Service name cần kiểm tra? | Descriptor chưa phân giải nên chưa phải bước đầu | Chưa tới bước service selection | Có, trọng tâm |
| File/cấu hình thường liên quan | tnsnames.ora, sqlnet.ora, TNS_ADMIN, LDAP | listener.ora, OS/network/firewall | LOCAL_LISTENER, REMOTE_LISTENER, service/PDB, listener registration |
| Lệnh trọng tâm | Kiểm tra file, Easy Connect, naming path | lsnrctl status, TCP test | lsnrctl services, V$SERVICES, ALTER SYSTEM REGISTER |

## 8. TNSPING: dùng đúng mục đích

tnsping là tiện ích kiểm tra Oracle Net connect identifier và thông tin kết nối ở mức chẩn đoán.

Ví dụ:

~~~text
tnsping SALES_PROD
~~~

Output thường hiển thị:

- Alias được dùng.
- Connect descriptor được phân giải.
- Thời gian thử.
- Kết quả TNS-125xx nếu thất bại.

### 8.1. TNSPING không phải đăng nhập database

TNSPING không xác thực username/password và không chứng minh:

- Database service có thể tạo session.
- Database instance đã mở.
- PDB đã mở.
- Handler sẵn sàng nhận connection.
- User/password hợp lệ.
- Ứng dụng có quyền truy cập object.
- Một câu SQL có thể chạy thành công.

Tài liệu Troubleshooting Oracle Net Services 19c khuyến nghị thử kết nối thực tế bằng SQL*Plus thay vì dùng TNSPING làm bằng chứng Oracle Net foundation layer hoạt động đầy đủ.

### 8.2. Kiểm tra end-to-end bằng SQL*Plus

~~~text
sqlplus -L app_user@SALES_PROD
~~~

Nhập password tại prompt. Nếu login thành công:

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME') AS db_name,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Truy vấn này xác nhận session đang kết nối database/service/container nào.

### 8.3. Test TCP không thay thế SQL*Plus

Test-NetConnection hoặc nc -vz chỉ xác nhận TCP port có thể tiếp cận. Một TCP connection thành công chưa chứng minh Oracle listener/service/authentication hoạt động.

Nên dùng ba phép kiểm tra theo mục đích:

| Công cụ | Điều được kiểm tra |
| --- | --- |
| DNS lookup | Hostname phân giải thành địa chỉ nào |
| TCP port test | Có thể mở TCP tới host/port không |
| SQL*Plus login | Có thể thực sự thiết lập Oracle database session không |

## 9. Kiểm tra cấu hình client theo từng môi trường

### 9.1. SQL*Plus trên Windows

~~~powershell
where.exe sqlplus
where.exe tnsping
$env:ORACLE_HOME
$env:TNS_ADMIN

Get-ChildItem Env: |
    Where-Object { $_.Name -match 'ORACLE|TNS' }
~~~

Nếu có nhiều Oracle Homes, xác định executable thực tế được gọi. Mỗi Oracle Home có thể có thư mục network/admin riêng.

### 9.2. SQL*Plus trên Linux

~~~bash
which sqlplus
which tnsping
echo "$ORACLE_HOME"
echo "$TNS_ADMIN"
env | grep -E 'ORACLE|TNS'
~~~

Kiểm tra quyền đọc file:

~~~bash
ls -l "$TNS_ADMIN/tnsnames.ora"
ls -l "$TNS_ADMIN/sqlnet.ora"
~~~

### 9.3. Oracle Instant Client

Instant Client có thể sử dụng TNS_ADMIN để tìm cấu hình Oracle Net. Không giả định cấu hình trong một Oracle Database Home tự động được Instant Client dùng.

### 9.4. SQL Developer

SQL Developer có thể sử dụng:

- Basic connection: hostname, port, service name/SID được nhập trực tiếp.
- TNS connection: alias được đọc từ thư mục TNS admin đã cấu hình trong Preferences.

Nếu SQL*Plus dùng được nhưng SQL Developer lỗi ORA-12154, kiểm tra TNS admin directory trong SQL Developer và cấu hình JDK/runtime của công cụ.

### 9.5. JDBC Thin Driver

JDBC Thin Driver có thể kết nối bằng Easy Connect:

~~~java
String url =
    "jdbc:oracle:thin:@//db-sales.example.com:1521/sales.example.com";
~~~

Hoặc dùng TNS alias khi driver được cấu hình để tìm Oracle Net config:

~~~java
String url = "jdbc:oracle:thin:@SALES_PROD";
~~~

Với TNS alias, cấu hình oracle.net.tns_admin hoặc cơ chế TNS admin phù hợp với Oracle JDBC driver/version.

Ví dụ JVM property:

~~~text
-Doracle.net.tns_admin=/opt/app/oracle/network/admin
~~~

Trên Windows, dùng đường dẫn thư mục tương ứng.

### 9.6. Spring Boot application

Ví dụ cấu hình JDBC URL:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//db-sales.example.com:1521/sales.example.com
    username: app_user
    password: INJECT_FROM_SECRET_STORE
    driver-class-name: oracle.jdbc.OracleDriver
~~~

Nếu dùng alias:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@SALES_PROD
~~~

Phải bảo đảm JVM/app process nhìn thấy TNS_ADMIN đúng. Không dùng password thật trong source control hoặc log.

### 9.7. Container/Kubernetes

Nếu app chạy trong container:

- File TNSNAMES trên host không tự xuất hiện trong container.
- TNS_ADMIN phải trỏ đến path bên trong container.
- ConfigMap/secret volume phải mount đúng.
- Container DNS và network policy có thể khác host.
- Egress policy phải cho phép port Oracle.
- Restart rollout khi cần nạp lại environment/config theo quy trình.

Không kiểm tra tnsnames.ora trên laptop rồi kết luận pod có cùng cấu hình.

## 10. Listener và service registration

### 10.1. Listener configuration

Listener configuration thường nằm trong listener.ora, chứa:

- Listener name.
- Protocol addresses.
- Host/IP.
- Port.
- Các tham số runtime.

Listener mặc định thường có tên LISTENER và TCP port 1521, nhưng môi trường có thể dùng tên/port khác.

### 10.2. Dynamic service registration

Database đăng ký services với listener thông qua LREG. Dynamic registration không yêu cầu khai báo từng service trong listener.ora.

LREG gửi thông tin service, instance và workload tới listener. Listener dùng dữ liệu này để chọn service handler cho connection request.

### 10.3. Listener start trước database

Nếu listener start trước instance, LREG có thể chưa đăng ký service ngay. Sau khi instance sẵn sàng, registration sẽ diễn ra theo discovery cycle. Có thể buộc đăng ký:

~~~sql
ALTER SYSTEM REGISTER;
~~~

### 10.4. LOCAL_LISTENER

LOCAL_LISTENER chỉ listener local mà LREG đăng ký service. Giá trị có thể là alias hoặc address.

~~~sql
SHOW PARAMETER local_listener;
~~~

Ví dụ address trực tiếp:

~~~sql
ALTER SYSTEM SET LOCAL_LISTENER =
  '(ADDRESS=(PROTOCOL=TCP)(HOST=db-sales.example.com)(PORT=1522))'
  SCOPE=BOTH;
~~~

Sau khi thay đổi, kiểm tra parameter và listener registration. Trong RAC, Clusterware và cấu hình network phải được xem xét cùng nhau.

### 10.5. REMOTE_LISTENER

REMOTE_LISTENER thường được dùng để đăng ký service với listener từ xa/SCAN listener trong RAC.

~~~sql
SHOW PARAMETER remote_listener;
~~~

Nếu REMOTE_LISTENER trỏ sai, service có thể không xuất hiện trên SCAN listener mà client đang gọi.

### 10.6. SERVICE_NAMES trong 19c

Trong Oracle Database 19c, việc customer tự sử dụng SERVICE_NAMES parameter đã deprecated. Oracle khuyến nghị quản lý services bằng SRVCTL, GDSCTL hoặc DBMS_SERVICE.

Vì vậy, không dùng lệnh kiểu:

~~~sql
ALTER SYSTEM SET SERVICE_NAMES = 'sales.example.com';
~~~

như cách sửa mặc định cho mọi ORA-12514 trên 19c. Trước tiên xác định service được tạo và quản lý bởi công cụ nào.

### 10.7. Kiểm tra listener services

~~~text
lsnrctl services LISTENER
~~~

Đọc:

- Service name.
- Instance name.
- Instance status.
- Handler type.
- Established/refused/current/max.
- Handler state.

Trạng thái READY nghĩa là handler có thể nhận kết nối. BLOCKED nghĩa là handler không nhận connection mới. UNKNOWN thường liên quan static registration.

## 11. PDB service và ORA-12514

Trong Multitenant, service thường là cách client kết nối vào PDB.

### 11.1. Xem PDB

~~~sql
SHOW PDBS;
~~~

Hoặc:

~~~sql
SELECT name, open_mode
FROM v$pdbs;
~~~

### 11.2. Xem service

~~~sql
SELECT
    name,
    network_name,
    pdb,
    con_id
FROM v$services
ORDER BY name;
~~~

### 11.3. Service của PDB chưa sẵn sàng

Nếu PDB đang đóng hoặc service chưa start, listener có thể không biết service được client yêu cầu.

Kiểm tra:

1. CDB instance có đang chạy không?
2. PDB có OPEN không?
3. Service có tồn tại không?
4. Service có được start không?
5. Service có đăng ký với listener không?
6. Client có dùng đúng service name không?

### 11.4. Không dùng SID để kết nối PDB

Với ứng dụng cần kết nối PDB, dùng service name của PDB. SID thường chỉ xác định instance, không phải cách định tuyến logical tới PDB.

### 11.5. Lưu trạng thái PDB

Nếu chính sách yêu cầu PDB tự mở sau database restart:

~~~sql
ALTER PLUGGABLE DATABASE salespdb SAVE STATE;
~~~

Kiểm tra lại sau restart và xác nhận service registration.

## 12. Oracle RAC, SCAN và local listener

RAC thêm nhiều endpoint vào quá trình kết nối.

### 12.1. Luồng kết nối RAC

~~~text
Client
  |
  v
SCAN name / SCAN IP
  |
  v
SCAN Listener
  |
  v
Redirect to Node VIP / Local Listener
  |
  v
Database Instance / Service Handler
~~~

### 12.2. SCAN listener và local listener khác nhau

- SCAN listener nhận kết nối qua SCAN address và phân phối tới node phù hợp.
- Local listener trên node quản lý service handler của instance tại node đó.
- Service có thể chạy trên một hoặc nhiều instances theo preferred/available configuration.

### 12.3. Kiểm tra SCAN và listener

~~~text
srvctl status scan
srvctl status scan_listener
srvctl status listener
srvctl status service -db SALESDB
~~~

Kiểm tra cấu hình:

~~~text
srvctl config scan
srvctl config scan_listener
srvctl config service -db SALESDB
~~~

### 12.4. ORA-12541 sau redirect

Client có thể tới được SCAN listener nhưng không kết nối được local listener/VIP sau redirect. Error có thể chứa endpoint cuối cùng. Đọc CONNECTION_ID, listener logs và hostname/IP cuối cùng thay vì chỉ test SCAN hostname.

### 12.5. ORA-12514 trong RAC

Service có thể chưa chạy trên instance mà listener đang xử lý hoặc client gọi nhầm service. Kiểm tra service configuration, preferred/available instances, service status và output của srvctl status service.

### 12.6. Không restart listener tùy tiện

Trong RAC, listener do Grid Infrastructure quản lý. Dùng SRVCTL và quy trình Clusterware. Restart listener thủ công có thể làm mất trạng thái hoặc gây gián đoạn kết nối của các workload khác.

## 13. JDBC và connection pool

Một lỗi Oracle Net có thể xuất hiện trong ứng dụng Java ngay cả khi DBA kết nối được từ terminal.

### 13.1. Phân biệt Thin và OCI

JDBC Thin Driver dùng Java implementation của Oracle Net và không yêu cầu Oracle Client native library theo cách OCI cần.

JDBC OCI phụ thuộc Oracle Client/OCI installation và Oracle Net config trên host.

Khi so sánh kết quả, phải dùng cùng driver type và cùng runtime config.

### 13.2. JDBC URL Easy Connect

~~~java
String url =
    "jdbc:oracle:thin:@//db-sales.example.com:1521/sales.example.com";

try (Connection connection =
         DriverManager.getConnection(url, username, password)) {
    // session đã được tạo nếu không có exception
}
~~~

### 13.3. JDBC URL TNS alias

~~~java
String url = "jdbc:oracle:thin:@SALES_PROD";
~~~

Alias phải được phân giải trong runtime của JVM. Nếu TNS_ADMIN chỉ được đặt trong shell của DBA nhưng không được truyền vào service/application process, Java app có thể gặp ORA-12154.

### 13.4. Connection pool giữ connection cũ

Nếu listener/service vừa được sửa, pool có thể còn các connection cũ hoặc retry theo timeout riêng. Kiểm tra:

- Pool initialization failure.
- Connection validation query.
- Maximum lifetime.
- Connection timeout.
- Retry/backoff.
- DNS cache.
- Pod/application restart và environment variables.

Không restart toàn bộ application chỉ để che lỗi cấu hình. Trước tiên xác định lỗi có tái hiện với một connection mới từ đúng runtime không.

### 13.5. Spring Boot datasource

Kiểm tra effective configuration:

- JDBC URL cuối cùng.
- Driver class/version.
- TNS_ADMIN hoặc JVM properties.
- Secret/environment injection.
- Host/port/service trong config profile đang active.
- HikariCP hoặc pool khác có dùng đúng DataSource.

Không log password hoặc toàn bộ connection properties nếu có secret.

### 13.6. Kiểm tra session sau kết nối

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME') AS db_name,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'INSTANCE_NAME') AS instance_name,
    sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

Điều này xác nhận app không chỉ kết nối được mà còn vào đúng database/service/PDB.

## 14. Listener logs, SQL*Net logs và ADR

Khi lỗi vẫn còn sau các bước cơ bản, logs giúp xác định request đã đi tới tầng nào.

### 14.1. Listener log

Listener log ghi nhận connection requests, service registration events, direct hand-off và các sự kiện liên quan.

Dùng:

~~~text
lsnrctl status LISTENER
~~~

Output có mục Listener Log File để xác định đường dẫn thực tế.

Trong ADR, listener home thường có dạng:

~~~text
<ADR_BASE>/diag/tnslsnr/<host>/<listener_name>/
~~~

Các thư mục thường gặp:

- alert: XML alert log.
- trace: listener trace và text log.
- incident: incident dumps nếu có.

Không hard-code một đường dẫn duy nhất cho mọi host. Lấy ADR home từ output lsnrctl status hoặc ADRCI.

### 14.2. SQL*Net client/server logs

Oracle Net có thể ghi sqlnet.log và trace file ở client/server ADR homes.

Đối với ORA-12154, client-side diagnostics thường quan trọng vì naming resolution xảy ra tại client.

Đối với ORA-12541/12514, listener log thường cho biết listener có nhận request hay service registration có xuất hiện.

### 14.3. ADRCI

Khởi động:

~~~text
adrci
~~~

Liệt kê homes:

~~~text
ADRCI> SHOW HOMES
~~~

Chọn listener home đúng:

~~~text
ADRCI> SET HOME diag/tnslsnr/db-sales/listener
~~~

Xem alert log:

~~~text
ADRCI> SHOW ALERT -TAIL 100
~~~

Đường dẫn SET HOME phải khớp home thực tế được liệt kê bởi SHOW HOMES.

### 14.4. Đọc error stack

Oracle Net log có thể chứa nhiều lớp error:

- NI: Network Interface.
- NS: Network Session.
- NA: Network Authentication.
- NT: Network Transport/OS.

Thông báo cuối cùng mà ứng dụng hiển thị có thể chỉ là lớp ngoài. Trong log, bắt đầu từ cuối error stack và tìm lỗi non-zero đầu tiên có ý nghĩa để xác định nguyên nhân gốc.

### 14.5. Listener log và CONNECTION_ID

Các lỗi Oracle mới có thể cung cấp CONNECTION_ID. Dùng giá trị này để đối chiếu request trong listener/client/server trace. Ghi lại:

- Timestamp chính xác và timezone.
- Host/client source.
- Destination host/port.
- Service name.
- CONNECTION_ID.
- Error code đầy đủ.

Không chỉ copy một dòng ORA-12514 mà bỏ qua descriptor và timestamp.

## 15. Bật Oracle Net tracing có kiểm soát

Tracing ghi chi tiết các bước giao tiếp nội bộ và có thể tạo nhiều dữ liệu.

### 15.1. Khi nào cần trace?

- Lỗi chỉ xảy ra ở một số client.
- Lỗi không ổn định hoặc chỉ xảy ra sau redirect.
- DNS/network behavior khó tái hiện.
- Listener nhận request nhưng không rõ vì sao handler không được chọn.
- Cần xem naming resolution hoặc network protocol negotiation.

### 15.2. Client tracing

Ví dụ cấu hình tạm trong sqlnet.ora:

~~~text
TRACE_LEVEL_CLIENT = ADMIN
TRACE_UNIQUE_CLIENT = ON
~~~

Tên và vị trí trace phụ thuộc ADR configuration và Oracle Net version. Sau khi bật, tái hiện một lần lỗi, lưu trace và tắt tracing.

### 15.3. Listener tracing

Listener tracing được cấu hình trong listener.ora theo listener name. Ví dụ:

~~~text
TRACE_LEVEL_LISTENER = ADMIN
TRACE_TIMESTAMP_LISTENER = ON
~~~

Tên tham số chính xác phụ thuộc listener alias và release. Tham khảo Oracle Net Services Reference trước khi thay đổi.

### 15.4. Trace level

Các mức thường gặp:

- OFF: tắt.
- USER: thông tin cơ bản phục vụ người dùng.
- ADMIN: chi tiết hơn cho quản trị.
- SUPPORT: rất chi tiết, phục vụ Oracle Support.

Không bật SUPPORT tracing lâu trên production. Tracing có thể tăng disk usage và ảnh hưởng hiệu năng.

### 15.5. Tắt tracing sau khi thu thập

Khôi phục cấu hình ban đầu, xác nhận trace không còn tăng liên tục và bảo đảm log/trace được lưu đúng nơi theo chính sách retention.

### 15.6. Che dữ liệu nhạy cảm

Trace có thể chứa:

- Hostnames/IPs.
- Username.
- Connect descriptors.
- Service names.
- Authentication/network metadata.
- SQL text hoặc dữ liệu ứng dụng tùy loại trace.

Trước khi gửi ra ngoài tổ chức, cần review và redact thông tin nhạy cảm.

## 16. Quy trình chẩn đoán theo tầng

Một runbook tốt không bắt đầu bằng restart database. Hãy đi theo các bước có thể chứng minh.

### Bước 1 — Ghi nhận lỗi chính xác

Thu thập:

- Error code đầy đủ, gồm TNS-xxxxx nếu có.
- Timestamp và timezone.
- Client host/application.
- Connect identifier hoặc JDBC URL đã redact.
- Protocol, host, port và service.
- Có chỉ một client lỗi hay toàn bộ client?
- Lỗi bắt đầu từ thời điểm nào?
- Có thay đổi DNS, firewall, listener, service, PDB hoặc deploy không?

### Bước 2 — Xác định client configuration

- Tìm Oracle Home/driver.
- Xác định TNS_ADMIN.
- Xác định naming method.
- Kiểm tra TNSNAMES hoặc LDAP.
- Với JDBC, kiểm tra URL và JVM property.

### Bước 3 — Phân giải tên

Nếu dùng alias:

- Kiểm tra TNSNAMES.
- Kiểm tra NAMES.DIRECTORY_PATH.
- Kiểm tra NAMES.DEFAULT_DOMAIN.

Thử Easy Connect để tách naming error.

### Bước 4 — Kiểm tra host/port

- Resolve DNS.
- Kiểm tra IP.
- Test TCP port.
- Xác định firewall/network path.

### Bước 5 — Kiểm tra listener

~~~text
lsnrctl status LISTENER
~~~

So sánh endpoint thực tế với descriptor.

### Bước 6 — Kiểm tra service registration

~~~text
lsnrctl services LISTENER
~~~

Nếu thiếu service, kiểm tra:

- V$SERVICES.
- V$INSTANCE.
- V$PDBS.
- LOCAL_LISTENER.
- REMOTE_LISTENER.
- Service status qua SRVCTL/DBMS_SERVICE.

### Bước 7 — Thử login thật

~~~text
sqlplus -L app_user@SALES_PROD
~~~

Nếu login thành công, chạy query xác nhận DB/service/PDB.

### Bước 8 — Kiểm tra runtime ứng dụng

- Từ đúng application server/container.
- Dùng đúng JDBC driver.
- Dùng đúng effective URL.
- Dùng đúng TNS_ADMIN.
- Kiểm tra connection pool và DNS cache.

### Bước 9 — Đọc logs/traces

Đối chiếu client, listener và database timestamps/connection ID.

### Bước 10 — Chỉ thay đổi đúng tầng

Mỗi lần chỉ thay một biến có căn cứ, ghi lại giá trị trước/sau và kiểm thử lại từ cùng client.

## 17. Ma trận lỗi và hướng xử lý

| Triệu chứng | Tầng ưu tiên | Kiểm tra đầu tiên |
| --- | --- | --- |
| ORA-12154 | Naming | TNS_ADMIN, TNSNAMES, NAMES.DIRECTORY_PATH |
| ORA-12541 | Listener/network | Host, port, TCP test, lsnrctl status |
| ORA-12514 | Service registration | SERVICE_NAME, lsnrctl services, V$SERVICES |
| ORA-12505 | Instance/SID | SID trong descriptor và listener |
| ORA-12521 | Instance registration | INSTANCE_NAME và service registration |
| ORA-12520 | Handler availability/type | Handler status, server=, instance state |
| ORA-12516 | Handler capacity/protocol | Service handler, dispatcher/dedicated capacity |
| ORA-12170 | Timeout | Network delay, timeout parameters, listener/client trace |
| ORA-12525 | Listener inbound timeout | Client completion time, listener log, network |
| ORA-12500 | Server process startup | PROCESSES, OS limits, permissions, listener log |
| ORA-12560 | Protocol adapter | OS/client protocol configuration |
| ORA-03113 | Session/communication loss | Database alert log, server process, network |

Không giải quyết các lỗi trong bảng bằng một công thức chung. Xác định error stack và tầng phát sinh trước.

## 18. Một số lỗi Oracle Net liên quan

### 18.1. ORA-12505 — Listener không biết SID

ORA-12505 khác ORA-12514:

- ORA-12505: descriptor chỉ định SID mà listener không nhận diện.
- ORA-12514: descriptor chỉ định service name mà listener không nhận diện.

Nếu ứng dụng nên kết nối bằng service, hãy dùng SERVICE_NAME đúng thay vì đổi SID ngẫu nhiên.

### 18.2. ORA-12521 — Listener không biết instance

Instance name được yêu cầu không đúng hoặc chưa đăng ký với listener. Kiểm tra INSTANCE_NAME, database instance và listener services.

### 18.3. ORA-12520 — Không tìm được handler phù hợp

Listener có thể biết service nhưng không có handler phù hợp cho loại server requested, hoặc instance chưa đăng ký đúng. Kiểm tra lsnrctl services, handler state, server mode và instance status.

### 18.4. ORA-12516 — Không có handler khả dụng

Listener không tìm được service handler có protocol stack phù hợp. Kiểm tra handler capacity, dispatcher/shared server, process/session limits và listener log.

### 18.5. ORA-12170 — Connect timeout

Timeout có thể do:

- DNS/network chậm.
- Firewall silently drop packets.
- Server quá tải.
- Client không hoàn tất connect/authentication trong thời gian cấu hình.
- Network path bị mất gói hoặc retransmit.

Đừng tăng timeout ngay khi chưa biết điểm chờ. Trace giúp xác định client/server đang chờ giai đoạn nào.

### 18.6. ORA-03113 — End-of-file on communication channel

Lỗi này thường xuất hiện sau khi session đã được thiết lập hoặc trong quá trình giao tiếp, và có thể liên quan database process, instance failure, network hoặc server-side error. Kiểm tra database alert log và trace thay vì chỉ kiểm tra TNSNAMES.

## 19. Các tình huống thực tế

### 19.1. SQL Developer kết nối được nhưng Java app lỗi ORA-12154

Khả năng:

- SQL Developer dùng TNS admin directory riêng.
- JVM không có TNS_ADMIN.
- App dùng JDBC Thin alias nhưng Oracle Net config không được mount.
- App đang dùng profile khác.

Hướng xử lý:

1. Lấy JDBC URL thực tế.
2. Kiểm tra JVM system properties.
3. Kiểm tra TNS_ADMIN trong process.
4. Thử Easy Connect.
5. Xác nhận driver version và runtime.

### 19.2. SQL*Plus chạy trên laptop được nhưng server app lỗi ORA-12541

Khả năng:

- Server không resolve cùng IP.
- Firewall giữa application subnet và DB subnet.
- App đang dùng port khác.
- DNS cache hoặc proxy/redirect endpoint khác.

Thử TCP test từ đúng application host/container.

### 19.3. Listener chạy nhưng ORA-12514

Khả năng:

- Service name sai.
- Service chưa start.
- PDB đóng.
- LREG chưa đăng ký.
- Client gọi listener không có service.

Dùng lsnrctl services, V$SERVICES, V$PDBS và kiểm tra LREG registration.

### 19.4. Sau reboot, ORA-12514 xuất hiện vài phút rồi tự hết

Có thể listener start trước database hoặc LREG chưa đăng ký service. Xem listener services theo thời gian và database startup logs. Nếu đúng là registration delay, có thể dùng ALTER SYSTEM REGISTER sau khi instance/service sẵn sàng hoặc điều chỉnh startup dependency theo quản trị hệ thống.

### 19.5. PDB mới tạo nhưng app không kết nối được

Kiểm tra:

1. PDB tồn tại.
2. PDB OPEN.
3. Service được tạo và start.
4. Service xuất hiện trong V$SERVICES.
5. Listener nhận service.
6. JDBC URL dùng đúng service name.

### 19.6. Chỉ một node RAC lỗi ORA-12541

Kiểm tra VIP, local listener, SCAN redirect và firewall giữa các node. Client có thể được redirect tới node không hoạt động dù SCAN listener khỏe.

### 19.7. Database link lỗi ORA-12154

Kiểm tra alias/connect descriptor từ Oracle database server thực hiện database link. File TNSNAMES trên máy người chạy SQL*Plus không quyết định cấu hình naming của database server process.

## 20. Runbook mẫu cho DBA

### 20.1. Thu thập thông tin

~~~text
ERROR_CODE:
TIMESTAMP:
CLIENT_HOST:
APPLICATION:
ORACLE_CLIENT_OR_DRIVER:
CONNECT_IDENTIFIER:
HOST:
PORT:
SERVICE_NAME:
DATABASE_NAME:
PDB:
RAC_OR_SINGLE_INSTANCE:
RECENT_CHANGE:
~~~

### 20.2. Kiểm tra client

~~~text
where.exe sqlplus
where.exe tnsping
echo %TNS_ADMIN%
~~~

Nếu dùng PowerShell:

~~~powershell
Get-Command sqlplus -ErrorAction SilentlyContinue
$env:TNS_ADMIN
~~~

### 20.3. Kiểm tra naming

- Xác nhận alias.
- Đọc TNSNAMES.
- Đọc SQLNET.
- Kiểm tra naming order.
- Thử Easy Connect.

### 20.4. Kiểm tra network

~~~powershell
Resolve-DnsName db-sales.example.com
Test-NetConnection db-sales.example.com -Port 1521
~~~

### 20.5. Kiểm tra listener

~~~text
lsnrctl status LISTENER
lsnrctl services LISTENER
~~~

### 20.6. Kiểm tra database/service

~~~sql
SELECT
    instance_name,
    status,
    database_status
FROM v$instance;

SELECT
    name,
    network_name,
    pdb
FROM v$services
ORDER BY name;

SELECT
    name,
    open_mode
FROM v$pdbs
ORDER BY name;

SHOW PARAMETER local_listener;
SHOW PARAMETER remote_listener;
~~~

### 20.7. Đăng ký lại service nếu phù hợp

~~~sql
ALTER SYSTEM REGISTER;
~~~

Sau đó:

~~~text
lsnrctl services LISTENER
~~~

### 20.8. Xác minh end-to-end

~~~text
sqlplus -L app_user@SALES_PROD
~~~

Sau khi login:

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME') AS db_name,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'INSTANCE_NAME') AS instance_name,
    sys_context('USERENV', 'CON_NAME') AS con_name
FROM dual;
~~~

### 20.9. Ghi nhận sau sửa lỗi

Ghi:

- Nguyên nhân gốc.
- Cấu hình đã thay đổi.
- Giá trị trước/sau.
- Lệnh đã chạy.
- Listener/service state.
- Client đã test.
- Thời gian phục hồi.
- Có cần theo dõi sau change không.

## 21. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| ORA-12154 là listener down | Đây là lỗi phân giải connect identifier |
| ORA-12541 là service name sai | Đây là lỗi không tiếp cận được listener address |
| ORA-12514 là port bị firewall | Listener đã nhận request nhưng không biết service |
| Listener chạy nghĩa là database service sẵn sàng | Listener có thể chưa đăng ký service |
| PING thành công nghĩa Oracle kết nối được | Ping chỉ kiểm tra IP reachability ở mức ICMP |
| TCP port mở nghĩa database login được | TCP test không kiểm tra Oracle service/authentication |
| TNSPING thành công nghĩa database session hoạt động | Cần SQL*Plus/JDBC login thực tế |
| TNSNAMES trên laptop cũng là TNSNAMES của Java app | Mỗi runtime có thể dùng Oracle Home/TNS_ADMIN riêng |
| Restart database luôn sửa ORA-12514 | Cần kiểm tra service registration và PDB/service state |
| SERVICE_NAME luôn bằng DB_NAME | Không nhất thiết; service là logical connect endpoint |
| SID và SERVICE_NAME có thể thay nhau tùy ý | Chúng có semantics khác nhau |
| Chỉ cần thêm SERVICE_NAMES vào SPFILE cho 19c | SERVICE_NAMES customer management đã deprecated; dùng SRVCTL/GDSCTL/DBMS_SERVICE |
| ALTER SYSTEM REGISTER sửa mọi ORA-12514 | Nó chỉ yêu cầu LREG đăng ký lại; không sửa sai service hoặc listener |
| ORA-12154 trong database link phải sửa trên laptop | Naming resolution có thể xảy ra ở database server |
| Listener log không có request nghĩa listener chắc chắn lỗi | Client có thể chưa tới listener hoặc đang gọi endpoint khác |
| Tăng timeout sẽ sửa mọi lỗi kết nối | Timeout không sửa naming, listener hoặc service registration |
| Mở firewall toàn mạng là cách kiểm tra nhanh | Chỉ kiểm tra và mở đúng source/destination/port theo chính sách |

## 22. Checklist trước khi thay đổi cấu hình

**Naming**

- Đã xác định đúng client process chưa?
- TNS_ADMIN có đúng không?
- Có nhiều Oracle Homes không?
- TNSNAMES có alias đúng không?
- NAMES.DIRECTORY_PATH đúng không?
- Easy Connect có hoạt động không?

**Network**

- Hostname resolve đúng IP không?
- Port listener có mở từ đúng subnet không?
- Có NAT, firewall, VPN hoặc SCAN redirect không?
- Đã xác định endpoint cuối trong lỗi chưa?

**Listener**

- Listener có chạy không?
- Listener có listen đúng port không?
- Listener name có đúng không?
- Listener có nhận request không?
- Listener log có entry tương ứng không?

**Service**

- SERVICE_NAME có chính xác không?
- lsnrctl services có service đó không?
- Handler có READY không?
- Instance và PDB có sẵn sàng không?
- LOCAL_LISTENER/REMOTE_LISTENER đúng không?
- Service có được quản lý bằng SRVCTL/DBMS_SERVICE/GDS không?

**Ứng dụng**

- JDBC URL có đúng không?
- Driver/runtime có dùng TNS_ADMIN đúng không?
- Connection pool có connection cũ không?
- App có chạy trong container/network namespace khác không?
- Đã test từ đúng app host bằng SQL*Plus hoặc một client tương đương chưa?

## 23. Câu hỏi tự kiểm tra

1. Oracle Net giải quyết nhiệm vụ gì?
2. Connect identifier khác connect descriptor thế nào?
3. Net service name là gì?
4. SID và SERVICE_NAME khác nhau thế nào?
5. ORA-12154 xuất hiện ở tầng nào?
6. ORA-12541 cho biết điều gì?
7. ORA-12514 cho biết điều gì?
8. Vì sao restart listener thường không sửa ORA-12154?
9. TNS_ADMIN dùng để làm gì?
10. NAMES.DIRECTORY_PATH điều khiển điều gì?
11. NAMES.DEFAULT_DOMAIN ảnh hưởng alias ra sao?
12. Easy Connect có lợi gì khi troubleshooting?
13. Vì sao ORA-12154 trong database link có thể do server-side config?
14. lsnrctl status cho biết điều gì?
15. lsnrctl services khác status ở điểm nào?
16. LREG làm nhiệm vụ gì?
17. ALTER SYSTEM REGISTER dùng khi nào?
18. LOCAL_LISTENER dùng để làm gì?
19. REMOTE_LISTENER thường có vai trò gì trong RAC?
20. Vì sao không nên tự thay SERVICE_NAMES trong Oracle 19c?
21. Vì sao PDB đóng có thể gây ORA-12514?
22. srvctl status service dùng để kiểm tra gì?
23. TNSPING có chứng minh database login thành công không?
24. Test-NetConnection chứng minh được điều gì?
25. Vì sao cần test từ đúng application server?
26. Listener log và client trace giúp phân biệt tầng lỗi thế nào?
27. ADR là gì?
28. Vì sao tracing không nên bật lâu?
29. ORA-12505 khác ORA-12514 thế nào?
30. Khi nào cần kiểm tra SCAN/local listener trong RAC?
31. JDBC Thin Driver dùng TNS alias cần cấu hình gì?
32. Vì sao SQL Developer hoạt động nhưng Java app lỗi ORA-12154?
33. Những thông tin nào cần ghi lại khi incident Oracle Net?
34. Vì sao không nên tăng timeout hoặc mở firewall trước khi xác định tầng lỗi?
35. Một runbook end-to-end nên kết thúc bằng phép thử nào?

**Gợi ý trả lời:**

1. Cung cấp naming, addressing, listener và giao tiếp client/server.
2. Identifier là tên/chuỗi client cung cấp; descriptor là protocol/host/port/connect data sau phân giải.
3. Tên alias trong naming repository.
4. SID nhận diện instance; SERVICE_NAME định tuyến logical tới service.
5. Naming resolution.
6. Không tiếp cận được listener ở địa chỉ được chỉ định.
7. Listener nhận request nhưng không biết service name.
8. Vì lỗi xảy ra trước khi client có descriptor hợp lệ.
9. Chỉ thư mục Oracle Net config mà client/process sử dụng.
10. Thứ tự naming methods.
11. Có thể nối domain vào connect identifier đơn giản.
12. Tách lỗi alias/TNSNAMES khỏi lỗi host/port/service.
13. Database server process có Oracle Net configuration riêng.
14. Listener endpoint, trạng thái, services summary và log path.
15. SERVICES cung cấp chi tiết service, instance và handlers.
16. Đăng ký service/instance information với listener.
17. Khi instance/service đã sẵn sàng nhưng cần yêu cầu đăng ký ngay.
18. Chỉ local listener mà LREG dùng để đăng ký.
19. Đăng ký với remote/SCAN listeners.
20. Vì customer use đã deprecated; quản lý bằng SRVCTL/GDSCTL/DBMS_SERVICE.
21. Service của PDB không thể nhận kết nối nếu PDB/service chưa sẵn sàng.
22. Trạng thái service được Clusterware quản lý.
23. Không; cần SQL*Plus/JDBC login thực tế.
24. Khả năng mở TCP tới host/port.
25. Vì DNS, firewall, TNS_ADMIN, JVM và network namespace có thể khác.
26. Listener log cho biết request/service registration; client trace cho biết naming và kết nối phía client.
27. Automatic Diagnostic Repository, nơi lưu logs/traces/incident data.
28. Trace có thể tạo dữ liệu lớn và ảnh hưởng hiệu năng.
29. ORA-12505 là SID không biết; ORA-12514 là service name không biết.
30. Khi dùng RAC/SCAN, redirect hoặc lỗi chỉ xảy ra trên một node.
31. TNS_ADMIN hoặc oracle.net.tns_admin tương ứng.
32. Hai runtime có thể dùng TNS admin directory hoặc Oracle Net config khác nhau.
33. Error code, timestamp, client, descriptor đã redact, host/port/service, CONNECTION_ID và thay đổi gần đây.
34. Vì chúng không sửa naming/service/listener root cause và có thể tạo rủi ro bảo mật.
35. Đăng nhập thực tế và truy vấn xác nhận database/service/PDB.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Net Services Administrator's Guide — Troubleshooting Oracle Net Services](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/troubleshooting-oracle-net-services.html): quy trình chẩn đoán, ORA-12154, ORA-12514, ORA-12541, logging và tracing.
- [Oracle Database 19c Net Services Administrator's Guide — Configuring and Administering Oracle Net Listener](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/configuring-and-administering-oracle-net-listener.html): listener, LREG, dynamic registration, LOCAL_LISTENER, REMOTE_LISTENER và SERVICES.
- [Oracle Database Error Help — ORA-12154](https://docs.oracle.com/en/error-help/db/ora-12154/): nguyên nhân và hướng xử lý naming resolution.
- [Oracle Database Error Help — ORA-12514](https://docs.oracle.com/en/error-help/db/ora-12514/): service chưa đăng ký hoặc không được listener nhận diện.
- [Oracle Database Error Help — ORA-12541](https://docs.oracle.com/en/error-help/db/ora-12541/): listener không chạy hoặc không tiếp cận được host/port.
- [Oracle Database 19c Quick Start to Oracle Net Services](https://docs.oracle.com/en/database/oracle/oracle-database/19/netag/quick-start-oracle-net-services.html): kiểm tra kết nối và service registration.
- [Oracle Database 19c Real Application Clusters Administration and Deployment Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/racad/index.html): SCAN, local listeners và quản lý service bằng SRVCTL.

**Nguyên tắc cần nhớ:** ORA-12154 là lỗi phân giải tên; ORA-12541 là lỗi tiếp cận listener; ORA-12514 là listener không biết service. Xác định đúng client và connect descriptor trước, sau đó kiểm tra DNS/TCP, listener và service registration theo từng tầng. tnsping và TCP test chỉ là phép kiểm tra hỗ trợ; hãy đăng nhập thật bằng SQL*Plus hoặc JDBC từ đúng runtime để xác nhận end-to-end. Với Oracle 19c, kiểm tra LREG, LOCAL_LISTENER, REMOTE_LISTENER và quản lý service bằng SRVCTL/GDSCTL/DBMS_SERVICE thay vì tự thay SERVICE_NAMES. Thu thập listener logs/ADR/trace có kiểm soát, chỉ thay đổi cấu hình khi đã có bằng chứng về nguyên nhân gốc.
