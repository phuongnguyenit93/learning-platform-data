# Kiểm tra kết nối theo từng lớp: DNS, TCP, listener và database service

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Công cụ và kết nối  
> **Mục tiêu:** Tự xác định vì sao ứng dụng hoặc công cụ SQL không kết nối được Oracle Database, bằng cách kiểm tra lần lượt **phân giải tên máy → đường truyền TCP → Oracle Net Listener → database service/PDB → xác thực và truy vấn**.

## 1. Vì sao phải kiểm tra theo từng lớp?

Một thông báo “không kết nối được database” có thể xuất phát từ nhiều nguyên nhân độc lập:

- Tên máy chủ không phân giải được hoặc phân giải ra sai IP.
- Máy client không đi được đến cổng TCP của máy chủ do định tuyến, VPN, firewall hoặc listener chưa lắng nghe.
- TCP đến được Oracle Net Listener, nhưng listener chưa nhận biết service được yêu cầu.
- Listener biết service, nhưng database/PDB chưa sẵn sàng hoặc không có handler để phục vụ kết nối.
- Đường truyền và service hoạt động, nhưng tài khoản, mật khẩu hoặc quyền đăng nhập sai.

Nếu kiểm tra ngay mật khẩu khi lỗi thực tế là DNS, ta sẽ mất thời gian mà không giải quyết được vấn đề. Ngược lại, việc mở cổng mạng sẽ không sửa được một service name bị gõ nhầm.

### Sơ đồ đường đi của một kết nối Oracle

```text
Ứng dụng Java / SQL Developer / SQLcl / SQL*Plus
        |
        | 1. "db.lab.example" -> địa chỉ IP
        v
       DNS / bộ phân giải tên của hệ điều hành
        |
        | 2. TCP đến <IP>:1521
        v
      Mạng / định tuyến / firewall / NAT
        |
        | 3. Oracle Net connect request
        v
      Oracle Net Listener (thường TCP 1521)
        |
        | 4. Yêu cầu service, ví dụ FREEPDB1
        v
      Database instance / đăng ký service / PDB
        |
        | 5. Xác thực LAB_ORACLE, tạo session
        v
      SQL thực thi trên PDB đã chọn
```

**Phân biệt hai khái niệm dễ nhầm:**

- **Listener** là tiến trình tiếp nhận và điều phối yêu cầu kết nối Oracle Net. Một listener có thể phục vụ nhiều service.
- **Database service** là tên logic để chọn đúng database/PDB hoặc nhóm instance cung cấp dịch vụ. Service không phải là cổng TCP hay tên máy chủ.

Một phép thử có kết quả tốt ở tầng trước **chưa chứng minh** tầng sau hoạt động. Ví dụ, kiểm tra cổng 1521 thành công chỉ chứng minh có kết nối TCP; nó chưa xác nhận service `FREEPDB1` tồn tại hoặc đăng nhập được.

## 2. Chuẩn bị một bộ thông số kết nối rõ ràng

Trước khi chạy lệnh, cần xác định các giá trị thực tế. Bài học sử dụng một môi trường giả định:

| Thông số | Giá trị ví dụ | Cần hiểu |
|---|---|---|
| Client | Laptop chạy SQL Developer hoặc ứng dụng Java | Máy phát sinh yêu cầu kết nối |
| Database host | `db.lab.example` | Tên DNS hoặc IP của **máy chủ Oracle** |
| Port | `1521` | Cổng listener truy cập từ client; có thể khác khi qua Docker/NAT |
| Protocol | `TCP` | Môi trường dùng TCPS cần cấu hình và kiểm tra riêng |
| Service name | `FREEPDB1` | PDB thực hành của Oracle Database Free |
| Username | `LAB_ORACLE` | Tài khoản **tồn tại trong PDB** |
| Password | Mật khẩu thực tế của tài khoản | Không ghi vào ảnh chụp màn hình, log hoặc ticket |
| Công cụ | SQL*Plus, SQLcl, SQL Developer hoặc JDBC | Có thể có cách đọc cấu hình khác nhau |

**Chuỗi kết nối EZConnect:**

```text
//db.lab.example:1521/FREEPDB1
```

Trong SQL*Plus:

```bash
sqlplus -L LAB_ORACLE@//db.lab.example:1521/FREEPDB1
```

Công cụ sẽ yêu cầu mật khẩu. Cờ `-L` giúp SQL*Plus chỉ thử đăng nhập một lần rồi trả lỗi, phù hợp để xác định kết quả của một phép thử.

Trong JDBC Thin, kết nối dùng service name có dạng:

```text
jdbc:oracle:thin:@//db.lab.example:1521/FREEPDB1
```

Để đối chiếu với môi trường khác:

| Oracle hoặc cách triển khai | Ví dụ service cho PDB |
|---|---|
| Oracle Database Free 23ai/26ai | `FREEPDB1` |
| Oracle Database XE 18c/21c | `XEPDB1` |
| Oracle 19c có CDB/PDB do DBCA tạo | Ví dụ `ORCLPDB1`, tùy người cài đặt |
| Oracle do tổ chức quản trị | Service name do DBA cung cấp; không tự đoán |

**Tên service không nhất thiết trùng SID hoặc tên database.** Ví dụ, `FREE` có thể là tên CDB/SID còn `FREEPDB1` là service để vào PDB. Khi đang kiểm tra một cấu hình thực tế, dùng thông số từ chính môi trường đó thay cho giá trị ví dụ.

### Chọn nơi chạy lệnh

Cần phân biệt kết quả đo **trên client** với kết quả đo **trên server**:

- Lệnh DNS và TCP chạy từ chính **máy bị lỗi kết nối**; kết quả từ máy khác có thể không đại diện vì mạng, DNS và firewall khác.
- `lsnrctl` và các truy vấn quản trị database thường chạy trên **database server** hoặc thông qua quyền quản trị phù hợp.
- Kết nối SQL cuối cùng phải thử lại từ **client/ứng dụng đang gặp lỗi**.

Trong Docker, “server” có thể là một container: cổng bên trong container và cổng publish ra máy host là hai địa chỉ kiểm tra khác nhau.

## 3. Lớp 1 — Kiểm tra DNS và phân giải tên máy

### DNS trả lời câu hỏi gì?

Khi ứng dụng dùng hostname `db.lab.example`, hệ điều hành cần biến hostname thành IP. Nếu không phân giải được, client chưa thể biết nơi mở socket TCP.

Ngoài DNS, hệ điều hành có thể dùng file `hosts`, bộ nhớ đệm, bộ phân giải cục bộ hoặc cấu hình VPN. Vì vậy, nên phân biệt:

- **Tra cứu DNS:** máy chủ DNS trả bản ghi A/AAAA nào?
- **Phân giải theo hệ điều hành:** chương trình trên máy client thực sự có thể dùng địa chỉ nào?

### Windows PowerShell

```powershell
Resolve-DnsName db.lab.example

Resolve-DnsName db.lab.example -Type A
Resolve-DnsName db.lab.example -Type AAAA

nslookup db.lab.example
```

Cách đọc:

- Nếu có bản ghi `A`, đó là địa chỉ IPv4; bản ghi `AAAA` là IPv6.
- Nếu trả về `NXDOMAIN` hoặc báo không tìm thấy tên, trước hết kiểm tra **hostname, DNS, VPN và DNS zone**.
- Nếu có nhiều IP, client có thể thử một địa chỉ khác với IP bạn đang kiểm tra thủ công.
- `nslookup`/các công cụ tra cứu DNS không nhất thiết phản ánh chính xác toàn bộ đường phân giải của ứng dụng, đặc biệt khi máy dùng `hosts`, cache hoặc các cơ chế riêng.

Xem cấu hình DNS của máy:

```powershell
Get-DnsClientServerAddress

ipconfig /all
```

### Linux

```bash
getent ahosts db.lab.example

nslookup db.lab.example

dig +short db.lab.example A
dig +short db.lab.example AAAA
```

- `getent ahosts` dùng cơ chế phân giải tên do hệ điều hành cấu hình, nên hữu ích để đối chiếu với ứng dụng.
- `dig` và `nslookup` hỏi dịch vụ DNS, giúp xác định bản ghi DNS hiện tại.
- `dig` có thể chưa được cài; nếu thiếu, dùng `getent` hoặc cài công cụ DNS phù hợp với hệ điều hành.

Xem cấu hình liên quan khi cần:

```bash
cat /etc/resolv.conf
grep '^hosts:' /etc/nsswitch.conf
```

File `/etc/hosts` cũng có thể ảnh hưởng tới kết quả phân giải trên Linux; trên Windows, đường dẫn điển hình là `C:\Windows\System32\drivers\etc\hosts`.

### Diễn giải lỗi DNS

| Kết quả | Ý nghĩa thường gặp | Việc tiếp theo |
|---|---|---|
| Tên không phân giải được | Sai tên, chưa vào VPN, không truy cập DNS nội bộ hoặc record chưa tồn tại | Xác nhận hostname từ DBA và DNS/VPN |
| DNS trả IP khác dự kiến | Record cũ, split DNS giữa mạng nội bộ/VPN, sai môi trường | Đối chiếu IP máy chủ thật và record; không tự sửa DNS production |
| IP đúng nhưng vẫn lỗi | DNS đã qua được; vấn đề có thể nằm ở TCP trở về sau | Tiếp tục mục 4 |
| Có cả IPv4 và IPv6 | Client có thể chọn họ địa chỉ khác với phép thử | Kiểm tra khả năng kết nối của đường IPv4/IPv6 thực tế |

> **Không dùng `ping` làm bằng chứng duy nhất cho Oracle.** Ping sử dụng ICMP; firewall có thể chặn ICMP trong khi TCP 1521 vẫn hoạt động. Ping thành công cũng không chứng minh cổng Oracle mở.

**Thử bằng IP để cô lập lỗi:** nếu biết chắc IP của database server, có thể thử TCP trực tiếp đến IP đó. Nếu IP thông nhưng hostname không thông, nhánh điều tra hợp lý là DNS/hosts. Tuy nhiên, trong hệ thống có load balancer, SCAN, chứng chỉ TLS hoặc nhiều IP, truy cập bằng IP có thể không phản ánh đúng kết nối được thiết kế; chỉ dùng như phép đo tạm thời khi phù hợp.

## 4. Lớp 2 — Kiểm tra đường truyền TCP đến host và port

DNS đúng không đồng nghĩa đường TCP thông. Lớp TCP trả lời: **client có thiết lập được kết nối tới host:port không?**

### Windows PowerShell

Từ máy chạy SQL Developer/JDBC:

```powershell
Test-NetConnection -ComputerName db.lab.example -Port 1521
```

Có thể yêu cầu thông tin chi tiết:

```powershell
Test-NetConnection db.lab.example -Port 1521 -InformationLevel Detailed
```

Chú ý dòng `TcpTestSucceeded`:

- `True`: TCP handshake tới địa chỉ/cổng đã chọn thành công. Một tiến trình đang nhận kết nối, nhưng **chưa chứng minh là Oracle listener đúng service**.
- `False`: chưa thiết lập được kết nối. Kiểm tra cổng, IP, firewall, VPN, tuyến mạng, NAT và trạng thái dịch vụ trên server.

Dòng `PingSucceeded` có thể `False` trong khi `TcpTestSucceeded` vẫn `True`; trường hợp này không phải lỗi TCP.

### Linux hoặc macOS

Từ client có Netcat:

```bash
nc -vz -w 3 db.lab.example 1521
```

- Nếu xuất hiện thông báo `succeeded` / `open`, kết nối TCP tới host:port thành công.
- Nếu `Connection refused`, máy đích hoặc thiết bị trung gian chủ động từ chối kết nối. Một nguyên nhân phổ biến là không có listener trên cổng đó; cũng cần xem chính sách firewall.
- Nếu `timed out`, gói tin hoặc phản hồi có thể bị chặn, định tuyến sai, host không phản hồi hoặc mạng bị gián đoạn.
- Nếu `Name or service not known`, quay lại bước phân giải tên.

Các bản Netcat có thể khác cú pháp; nếu `-w` không được hỗ trợ, xem `nc -h` và dùng tùy chọn tương ứng.

### Kiểm tra ngay trên database server

Trên Linux, xác định tiến trình lắng nghe cổng:

```bash
sudo ss -ltnp '( sport = :1521 )'
```

Ví dụ dòng chứa `LISTEN` cùng địa chỉ `0.0.0.0:1521` hoặc một IP giao diện máy chủ. Nếu chỉ lắng nghe `127.0.0.1:1521`, các client từ máy khác không thể đến trực tiếp listener qua địa chỉ mạng ngoài.

Trên Windows server:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 1521
```

Hoặc:

```powershell
netstat -ano | findstr :1521
```

Kiểm tra cổng trên server giúp biết listener có mở socket tại đó hay không, nhưng **không thay thế phép thử từ client** vì firewall giữa hai máy có thể ngăn kết nối.

### Khi có Docker, NAT hoặc chuyển tiếp cổng

Giả sử container Oracle lắng nghe **1521**, nhưng máy host publish thành **1522**:

```bash
docker run ... -p 127.0.0.1:1522:1521 ...
```

Khi đó:

- **Từ chính máy host:** kết nối `localhost:1522/FREEPDB1`.
- **Từ bên trong container:** listener thường vẫn ở cổng `1521`.
- **Từ máy khác:** không thể dùng ánh xạ `127.0.0.1:1522` nêu trên vì host chỉ cho truy cập loopback. Muốn truy cập từ mạng phải có cấu hình publish/network phù hợp và tuân theo chính sách bảo mật.

Kiểm tra ánh xạ cổng bằng:

```bash
docker ps
docker port oracle-free
```

Trong Docker Desktop, `localhost` từ laptop là máy host đang chạy Docker; trong một container khác, `localhost` là chính container đó. Đây là nguồn gây lỗi kết nối rất thường gặp.

### Khi môi trường yêu cầu TCPS

Nếu cấu hình Oracle Net dùng **TCPS** (Oracle Net trên TLS), kiểm tra bằng cổng TCPS được quản trị viên cung cấp và bằng một client đã cấu hình wallet/chứng chỉ phù hợp. TCP handshake thành công vẫn không chứng minh TLS handshake hoặc xác minh chứng chỉ thành công. Không suy đoán cổng TCPS luôn là 1522; cổng phụ thuộc cấu hình thực tế.

## 5. Lớp 3 — Kiểm tra Oracle Net Listener

Sau khi TCP thành công, bước tiếp theo là xác nhận endpoint đó thực sự là Oracle Listener và listener biết những service nào.

### Listener nhận yêu cầu kết nối như thế nào?

Một client gửi yêu cầu Oracle Net có chứa **service name**. Listener nhận yêu cầu trên cổng đang lắng nghe, tra thông tin service/handler và chuyển kết nối tới database instance thích hợp. Trong đa số hệ thống hiện đại, instance tự đăng ký service với listener (dynamic service registration); cơ chế này được tiến trình nền **LREG** thực hiện.

Có thể xảy ra hai trường hợp khác nhau:

1. Listener **không chạy** hoặc client đến **sai listener/cổng** → lỗi tầng TCP/listener.
2. Listener **đang chạy**, nhưng **không biết service được yêu cầu** → lỗi đăng ký service hoặc tên service; TCP vẫn có thể thành công.

### Lệnh trên database server

Đăng nhập máy chủ dưới tài khoản hệ điều hành có môi trường Oracle phù hợp, chạy:

```bash
lsnrctl status
```

Với listener có tên khác `LISTENER`, chỉ định tên thực tế:

```bash
lsnrctl status LISTENER
```

Các thông tin cần đọc trong output:

- `Alias` / tên listener.
- `Listening Endpoints Summary`: địa chỉ/protocol/port listener đang nghe.
- `Services Summary`: các service đã được đăng ký hoặc cấu hình.
- Thông điệp listener đã chạy, uptime và vị trí file log khi hiển thị.

Để xem chi tiết service và handler:

```bash
lsnrctl services
```

Ví dụ minh họa ý nghĩa output:

```text
Service "FREEPDB1" has 1 instance(s).
  Instance "FREE", status READY, has 1 handler(s) for this service...
    Handler(s):
      "DEDICATED" established:0 refused:0 state:ready
```

Ví dụ này cho biết listener nhận biết service `FREEPDB1` và có handler ở trạng thái sẵn sàng. Số handler, tên instance và trạng thái thực tế phụ thuộc hệ thống.

**`lsnrctl status`/`services` phải được chạy trong đúng môi trường Oracle Home hoặc chỉ định đúng listener.** Trên máy có nhiều Oracle Home hay nhiều listener, một lệnh thành công chưa chắc đang kiểm tra listener mà client đi tới.

### Kiểm tra nhanh từ client bằng tnsping

Nếu có Oracle Net client, có thể chạy:

```bash
tnsping DBLAB
```

Ở đây `DBLAB` là alias được cấu hình trong `tnsnames.ora` hoặc cơ chế đặt tên tương ứng. `tnsping` thường cho biết Oracle Net đã phân giải alias theo phương thức nào và có liên lạc được với listener tại địa chỉ mô tả hay không.

**Giới hạn của `tnsping`:** thông báo `OK` **không xác nhận** PDB được mở, service đăng nhập được, mật khẩu đúng hay truy vấn SQL chạy được. Đây là phép thử Oracle Net/địa chỉ listener, không phải kiểm thử đầy đủ database session.

### Listener không hiển thị service mong đợi

Nếu TCP thông nhưng `lsnrctl services` không có `FREEPDB1`, kiểm tra theo thứ tự:

1. Có đang hỏi **đúng listener và cổng** mà client dùng không?
2. Database instance đã chạy chưa?
3. PDB tương ứng đã mở chưa?
4. Database có đăng ký service với **đúng listener** không (`LOCAL_LISTENER`; môi trường RAC có thể liên quan `REMOTE_LISTENER`/SCAN)?
5. Có đang yêu cầu tên dịch vụ khác với tên mà database thực sự cung cấp không?

Trên server, tài khoản có quyền `SYSDBA` có thể yêu cầu đăng ký lại service sau khi xác định cấu hình đã đúng:

```sql
ALTER SYSTEM REGISTER;
```

Lệnh này yêu cầu instance thực hiện đăng ký lại với listener được cấu hình; nó **không tự mở PDB**, không tạo service mới và không sửa được địa chỉ `LOCAL_LISTENER` sai. Không thay đổi các tham số listener của môi trường dùng chung khi chưa xác định cấu hình mạng của hệ thống.

### Đọc kết quả ở lớp listener

| Dấu hiệu | Cách hiểu |
|---|---|
| `TNS-12541: no listener` / `ORA-12541` | Chưa gặp listener tại endpoint, hoặc địa chỉ/cổng/đường mạng có vấn đề |
| `ORA-12514: listener does not currently know of service requested` | Đã tiếp cận listener, nhưng service name chưa được listener biết tới |
| `ORA-12505: listener does not currently know of SID given` | Mẫu kết nối yêu cầu **SID**, nhưng listener không biết SID đó; cân nhắc dùng service name của PDB |
| `ORA-12516` | Listener biết service nhưng chưa tìm được handler phù hợp, thường cần xem tải/giới hạn kết nối/handler |
| `lsnrctl services` có service `READY` | Listener đã đăng ký handler; tiếp tục thử đăng nhập SQL để chứng minh tầng database |

## 6. Lớp 4 — Kiểm tra database service và trạng thái PDB

Listener có thể chạy bình thường dù database instance chưa mở hoặc PDB đang đóng. Với Oracle multitenant, điều quan trọng là kết nối vào **đúng service trỏ đến PDB cần dùng**.

### CDB, PDB, SID và service name

```text
Oracle database server
├── Instance: FREE               (ví dụ SID)
├── CDB: FREE
│   ├── CDB$ROOT                 (quản trị chung)
│   ├── PDB$SEED                 (PDB mẫu)
│   └── FREEPDB1                 (PDB dùng cho bài lab)
└── Listener: TCP 1521
    ├── Service: FREE            (thường hướng vào CDB/root)
    └── Service: FREEPDB1        (hướng vào PDB thực hành)
```

Tùy phiên bản/cấu hình, service có thể mang tên khác, thậm chí thuộc về cluster hoặc được tạo riêng cho ứng dụng. **Không dùng tên SID thay cho service name nếu client đang yêu cầu PDB service.**

### Xem trạng thái instance/database trên server

Trên **database server**, dùng tài khoản hệ điều hành được cấp quyền quản trị Oracle và môi trường `ORACLE_SID` phù hợp:

```bash
sqlplus / as sysdba
```

Sau đó kiểm tra:

```sql
SELECT instance_name, status
FROM v$instance;

SELECT name, open_mode
FROM v$database;

SELECT name, open_mode
FROM v$pdbs
ORDER BY name;

SHOW CON_NAME;
```

Diễn giải:

- `v$instance` cho biết instance đang ở trạng thái nào.
- `v$database.open_mode` thường là `READ WRITE` khi database đã được mở cho hoạt động thông thường.
- `v$pdbs` cho biết từng PDB. PDB mà ứng dụng cần truy cập thường phải ở `READ WRITE`; `PDB$SEED` thường chỉ đọc.
- `SHOW CON_NAME` hiển thị container của **session hiện tại**, tránh nhầm giữa `CDB$ROOT` và PDB.

Từ root container, truy vấn các service đang hoạt động:

```sql
SELECT name, network_name, pdb
FROM v$active_services
ORDER BY name;
```

Để kiểm tra cấu hình service, DBA có thể đối chiếu thêm `DBA_SERVICES` (hoặc `CDB_SERVICES` theo phạm vi quyền/phiên bản). **Service được định nghĩa** và **service đang hoạt động/đăng ký với listener** không phải lúc nào cũng giống nhau.

### PDB đang đóng thì xử lý ra sao?

Ví dụ thấy `FREEPDB1` ở trạng thái `MOUNTED`. Nếu được giao quyền quản trị database và việc mở PDB phù hợp với môi trường, tại `CDB$ROOT`:

```sql
ALTER PLUGGABLE DATABASE FREEPDB1 OPEN;

ALTER PLUGGABLE DATABASE FREEPDB1 SAVE STATE;
```

- `OPEN` mở PDB để người dùng có thể sử dụng. Chạy khi PDB thực sự đang đóng; không cần mở lại PDB đã mở.
- `SAVE STATE` lưu trạng thái mở để Oracle tự khôi phục trạng thái phù hợp sau khi CDB khởi động lại, trong phiên bản/cấu hình hỗ trợ.

Sau đó kiểm tra lại `v$pdbs` và `lsnrctl services`. Nếu listener chưa nhận ra service dù PDB đã mở, quay lại mục đăng ký service.

Trong hệ thống production hoặc môi trường có nhiều người dùng, **quản trị viên** chịu trách nhiệm mở/đóng PDB, quản lý resource và đăng ký service. Người học chỉ cần thu thập bằng chứng, không tự thay đổi trạng thái cơ sở dữ liệu dùng chung.

### Thử tạo session SQL từ đúng client

Trên máy đang gặp lỗi kết nối:

```bash
sqlplus -L LAB_ORACLE@//db.lab.example:1521/FREEPDB1
```

Nhập mật khẩu khi được hỏi. Nếu đăng nhập thành công, chạy:

```sql
SELECT USER AS connected_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS connected_service
FROM dual;

SELECT 1 AS connection_ok
FROM dual;

EXIT;
```

Đây là phép thử xác nhận đồng thời:

1. Client đã đi qua đường mạng Oracle Net.
2. Listener đã điều phối đến service phù hợp.
3. Database chấp nhận tài khoản và tạo session.
4. Session chạy được SQL.
5. `current_container` trỏ đến **PDB mong muốn**.

Nếu đang dùng Oracle 21c XE, sửa service `FREEPDB1` thành `XEPDB1`; với môi trường 19c riêng, dùng service PDB thực tế do DBA cung cấp.

## 7. Bảng tra nhanh lỗi theo lớp

Thông báo lỗi Oracle Net có thể thay đổi theo driver, phiên bản và chỗ phát sinh. Bảng dưới đây nêu **hướng điều tra ưu tiên**, không coi một mã lỗi là bằng chứng tuyệt đối cho một nguyên nhân duy nhất.

| Triệu chứng / mã lỗi | Lớp ưu tiên | Hướng kiểm tra |
|---|---|---|
| `UnknownHostException`, hostname không tìm thấy | DNS/hostname | `Resolve-DnsName`, `getent ahosts`, DNS nội bộ, VPN, chính tả |
| `ORA-12154: TNS:could not resolve the connect identifier specified` | Oracle Net naming phía client | Alias `tnsnames.ora`, `TNS_ADMIN`, `sqlnet.ora`, `NAMES.DIRECTORY_PATH`, cú pháp EZConnect |
| `ORA-12545: Connect failed because target host or object does not exist` | Host/address hoặc Oracle Net | Địa chỉ listener, tên máy, IP trả về, cấu hình kết nối |
| `ORA-12541: No listener` | TCP/listener | Đúng host/port chưa, listener chạy/chờ kết nối chưa, NAT/firewall |
| `ORA-12170` / `ORA-12535` hoặc TCP timeout | Đường truyền và thời gian chờ | Kết nối TCP từ client, firewall, định tuyến, listener/DB bị quá tải |
| `ORA-12514` | Listener → service | Service name đúng chưa, PDB mở chưa, `lsnrctl services`, đăng ký service |
| `ORA-12505` | Listener → SID | Có đang dùng SID thay cho service name không, cấu hình connect descriptor |
| `ORA-12516` | Listener → handler | Trạng thái handler, giới hạn process/session, tải máy chủ |
| `ORA-01033` / `ORA-01034` | Instance/database | Trạng thái khởi động, database open mode, thông báo từ DBA |
| `ORA-01017` | Xác thực | Sai username/password, phân biệt hoa-thường, đúng PDB/service chưa |
| `ORA-28000` / `ORA-28001` | Trạng thái tài khoản | Account bị khóa hoặc mật khẩu hết hạn; cần người có quyền xử lý |
| JDBC `IO Error: The Network Adapter could not establish the connection` | Chưa thể kết luận | Kiểm tra DNS/TCP/listener và lỗi gốc (`cause`) theo trình tự |
| Kết nối thành công nhưng thấy `CDB$ROOT` | Chọn database service | Đổi sang **service của PDB**; kiểm tra `SYS_CONTEXT('USERENV', 'CON_NAME')` |
| Kết nối được nhưng truy vấn bị `ORA-01031` | Quyền SQL sau khi tạo session | Đã qua lớp kết nối; kiểm tra quyền của schema, không sửa firewall |

**Chú ý về `ORA-12154`:** Đây thường là lỗi **phân giải định danh kết nối của Oracle Net**, chẳng hạn không tìm được alias `DBLAB`. Nó không nhất thiết có nghĩa máy chủ DNS không phân giải được hostname. Muốn phân biệt, hãy thử EZConnect đầy đủ và kiểm tra cấu hình alias ở mục tiếp theo.

## 8. Khi lỗi nằm ở Oracle Net naming: tnsnames.ora và EZConnect

Ứng dụng có thể chỉ biết một alias như `DBLAB` thay vì biết hostname/port/service. Alias này được ánh xạ qua Oracle Net naming, thường là `tnsnames.ora`.

Ví dụ nội dung `tnsnames.ora`:

```ini
DBLAB =
  (DESCRIPTION =
    (ADDRESS = (PROTOCOL = TCP)
               (HOST = db.lab.example)
               (PORT = 1521))
    (CONNECT_DATA =
      (SERVICE_NAME = FREEPDB1)
    )
  )
```

Kết nối tương ứng:

```bash
sqlplus -L LAB_ORACLE@DBLAB
```

Nếu lệnh này lỗi nhưng EZConnect `LAB_ORACLE@//db.lab.example:1521/FREEPDB1` thành công, khả năng cao vấn đề nằm ở **tên alias, file cấu hình hoặc đường dẫn tìm cấu hình của client**.

### Xác định nơi client đọc Oracle Net configuration

Trong hệ thống có Oracle Client/Oracle Home, thư mục mặc định thường nằm dưới:

```text
$ORACLE_HOME/network/admin
```

Biến môi trường `TNS_ADMIN` có thể trỏ sang thư mục khác chứa `tnsnames.ora` và `sqlnet.ora`.

Trên Windows PowerShell:

```powershell
$env:TNS_ADMIN
$env:ORACLE_HOME
```

Trên Linux:

```bash
printf 'TNS_ADMIN=%s\n' "$TNS_ADMIN"
printf 'ORACLE_HOME=%s\n' "$ORACLE_HOME"
```

Tùy công cụ, client có thể được đóng gói thư viện Oracle Net riêng hoặc dùng JDBC Thin với cấu hình không hoàn toàn giống SQL*Plus. Vì thế, cần kiểm tra chính **runtime của ứng dụng bị lỗi**, không chỉ môi trường shell của quản trị viên.

Trong `sqlnet.ora`, thông số `NAMES.DIRECTORY_PATH` có thể quy định các phương pháp phân giải định danh như `TNSNAMES` và `EZCONNECT`. Nếu tổ chức cố ý chỉ cho phép một phương thức, việc dùng alias/EZConnect cần phù hợp cấu hình đó.

### Service name và SID không thay thế cho nhau

Connect descriptor sử dụng service name:

```ini
(CONNECT_DATA = (SERVICE_NAME = FREEPDB1))
```

Connect descriptor theo SID đời cũ sử dụng:

```ini
(CONNECT_DATA = (SID = FREE))
```

Với môi trường multitenant, thông thường client ứng dụng phải dùng **service name của PDB**. Nếu Java dùng URL kiểu SID đời cũ trong khi SQL Developer dùng service name, hai công cụ có thể nhận lỗi khác nhau dù kết nối cùng một máy.

## 9. Quy trình chẩn đoán thực tế

Giả sử SQL Developer báo không kết nối được `LAB_ORACLE@db.lab.example:1521/FREEPDB1`.

### Bước 1: xác nhận thông số

Ghi lại hostname, cổng, service name, protocol, client/driver, thời gian lỗi và mạng đang dùng (LAN/VPN). Không gửi mật khẩu vào log, ảnh chụp hoặc email hỗ trợ.

### Bước 2: hỏi DNS từ máy bị lỗi

Windows:

```powershell
Resolve-DnsName db.lab.example
```

Linux:

```bash
getent ahosts db.lab.example
```

Nếu tên không ra IP phù hợp, xử lý tên/VPN/DNS trước khi tiếp tục.

### Bước 3: thử TCP tới đúng cổng

Windows:

```powershell
Test-NetConnection db.lab.example -Port 1521
```

Linux:

```bash
nc -vz -w 3 db.lab.example 1521
```

Nếu TCP thất bại, đối chiếu tình trạng listener trên server, firewall, NAT và route. Nếu TCP thành công, tiếp tục.

### Bước 4: kiểm tra listener và service trên server

```bash
lsnrctl status
lsnrctl services
```

Xác định listener có lắng nghe đúng endpoint và service `FREEPDB1` có xuất hiện không. Nếu service chưa có, kiểm tra database/PDB và cấu hình đăng ký.

### Bước 5: kiểm tra PDB và active services

Với tài khoản quản trị phù hợp trên server:

```sql
SELECT name, open_mode FROM v$pdbs;
SELECT name, network_name, pdb FROM v$active_services;
```

Nếu PDB chưa mở, báo DBA hoặc thực hiện thao tác quản trị đã được cho phép. Nếu PDB và service đều phù hợp, tiếp tục.

### Bước 6: thử SQL bằng service name cụ thể

```bash
sqlplus -L LAB_ORACLE@//db.lab.example:1521/FREEPDB1
```

Sau khi vào SQL*Plus:

```sql
SELECT USER,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service
FROM dual;
```

Nếu thành công, kết nối mạng–listener–service–xác thực–SQL đã được chứng minh với công cụ này. Nếu ứng dụng Java vẫn lỗi, kiểm tra tiếp cấu hình của **chính ứng dụng**: JDBC URL, biến môi trường, connection pool, proxy, wallet/TCPS, driver, mạng container, thông tin đăng nhập và lỗi gốc trong stack trace.

### Bước 7: lưu lại kết quả theo từng lớp

Dùng bảng kết quả nhỏ gọn:

| Lớp | Câu hỏi | Bằng chứng cần ghi |
|---|---|---|
| DNS | Hostname đã ra đúng IP? | Lệnh, thời điểm, IP được trả về |
| TCP | Client mở được socket đến port? | `TcpTestSucceeded` hoặc kết quả `nc` |
| Listener | Có listener đúng endpoint? | Listener name, listening address, port |
| Database service | Listener biết service và PDB đang mở? | Service name, handler, `open_mode` |
| SQL session | Đúng user, đúng PDB, chạy truy vấn? | `USER`, `CON_NAME`, truy vấn `SELECT 1 FROM dual` |

Bảng này giúp người hỗ trợ nhanh chóng biết đang mắc ở lớp nào, tránh yêu cầu thực hiện lại các bước đã có bằng chứng.

## 10. Tình huống minh họa

### Tình huống A — DNS sai nhưng listener vẫn hoạt động

- `Resolve-DnsName db.lab.example` trả về `10.40.1.25`.
- DBA xác nhận database thực tế được truy cập qua `10.40.2.25`.
- Kiểm tra TCP bằng hostname thất bại; qua IP được DBA xác nhận lại thông.

**Kết luận điều tra:** tên DNS có thể đang trỏ sai hoặc client dùng sai mạng/VPN. Hướng xử lý là sửa dữ liệu phân giải/cấu hình mạng bằng quy trình của môi trường, không cần thay mật khẩu Oracle.

### Tình huống B — TCP thành công nhưng ORA-12514

- `Test-NetConnection ... -Port 1521` báo `TcpTestSucceeded: True`.
- SQL*Plus báo `ORA-12514`.
- `lsnrctl services` có service `FREE`, không có `FREEPDB1`.
- Kiểm tra `v$pdbs` cho thấy `FREEPDB1` đang `MOUNTED`.

**Kết luận điều tra:** listener đang chạy, nhưng service PDB chưa khả dụng. Nếu được cấp quyền, quản trị viên mở PDB và xác minh đăng ký lại service. Mở cổng firewall không giúp giải quyết trường hợp này.

### Tình huống C — TCP, listener, service tốt nhưng ORA-01017

- DNS phân giải đúng và TCP thông.
- Listener thấy service `FREEPDB1` với handler `READY`.
- Khi dùng `LAB_ORACLE`, SQL*Plus báo `ORA-01017`.

**Kết luận điều tra:** đã vượt qua phần lớn đường truyền. Cần kiểm tra tài khoản, mật khẩu, đúng PDB và cấu hình authentication của client. Không thay đổi mạng nếu không có thêm bằng chứng.

### Tình huống D — Kết nối trên host thành công nhưng từ container Java thất bại

- Oracle Database và Java app chạy ở **hai container**.
- JDBC URL của app dùng `localhost:1521/FREEPDB1`.
- Trên host, kết nối `localhost:1521` thành công; trong app, kết nối thất bại.

**Kết luận điều tra:** `localhost` bên trong container Java chỉ tới **container Java**, không tự tới container Oracle. Dùng tên service/container Oracle trên cùng Docker network và cổng container phù hợp (ví dụ `oracle-free:1521`), sau đó thử DNS/TCP từ **bên trong container app**.

### Tình huống E — Alias sai, EZConnect đúng

- `sqlplus LAB_ORACLE@DBLAB` báo `ORA-12154`.
- `sqlplus LAB_ORACLE@//db.lab.example:1521/FREEPDB1` thành công.

**Kết luận điều tra:** đường mạng và service hoạt động theo EZConnect. Kiểm tra `tnsnames.ora`, `TNS_ADMIN`, `sqlnet.ora` và phương thức naming của SQL*Plus.

## 11. Sơ đồ quyết định ngắn gọn

```text
Không kết nối được Oracle
    |
    v
Hostname phân giải đúng IP?
    |-- Không --> DNS / hosts / VPN / tên máy
    |
    v
TCP tới host:port thành công?
    |-- Không --> route / firewall / NAT / listener chưa lắng nghe
    |
    v
Listener nhận yêu cầu và biết service?
    |-- Không --> kiểm tra endpoint, service name, đăng ký service
    |
    v
Database/PDB mở, handler sẵn sàng?
    |-- Không --> trạng thái DB/PDB, tải, đăng ký, cấu hình dịch vụ
    |
    v
SQL*Plus/SQLcl đăng nhập được?
    |-- Không --> tài khoản / mật khẩu / authentication / PDB
    |
    v
SELECT 1 FROM dual chạy được?
    |-- Không --> quyền / trạng thái session / database / ứng dụng
    |
    v
Kết nối đầu-cuối đã được xác nhận
```

Sơ đồ này là cách sắp xếp việc **thu thập bằng chứng**. Trong thực tế, sự cố có thể nằm ở nhiều lớp cùng lúc; sau khi sửa một lỗi, hãy thử lại từ client để tìm lỗi tiếp theo.

## 12. Nguyên tắc vận hành và bảo mật khi kiểm tra

1. **Chạy từ đúng vị trí phát sinh lỗi.** Kết nối thành công từ server không bảo đảm truy cập từ laptop hoặc container ứng dụng sẽ thành công.
2. **Không suy luận từ một phép thử duy nhất.** `ping`, `nc`, `tnsping`, `lsnrctl` và `sqlplus` trả lời những câu hỏi khác nhau.
3. **Không tiết lộ mật khẩu.** Để SQL*Plus yêu cầu mật khẩu tương tác; loại bỏ secret trước khi chia sẻ lệnh, log và ảnh chụp.
4. **Không tự mở cổng database ra Internet.** Kiểm tra theo đường mạng được phê duyệt; tuân thủ VPN, firewall, TLS/wallet và chính sách truy cập của môi trường.
5. **Không tùy tiện restart listener hay database production.** Kiểm tra trạng thái và log trước; restart có thể ảnh hưởng các ứng dụng khác, trong khi lỗi gốc có thể chỉ là service name.
6. **Ghi nhận thông số thực tế.** Oracle Free, XE, CDB/PDB tạo bằng DBCA, RAC/SCAN và Autonomous Database có cách đặt tên và kết nối khác nhau; ví dụ `FREEPDB1` chỉ áp dụng khi đó đúng là service của hệ thống.
7. **Kiểm chứng cuối cùng bằng SQL.** Dấu hiệu hoàn tất đáng tin cậy là chính client mục tiêu đăng nhập được vào **đúng PDB** và thực hiện được một truy vấn đơn giản.

## 13. Bài thực hành tự kiểm tra

**Yêu cầu:** Với database Oracle đã được cấp quyền truy cập, thực hiện một đợt xác minh không thay đổi cấu hình hệ thống:

1. Ghi lại hostname, TCP port, service name và username (không lưu mật khẩu).
2. Thử phân giải DNS từ máy client và ghi IP nhận được.
3. Thử kết nối TCP từ client đến host:port.
4. Nếu có quyền trên server, ghi lại listener endpoint và danh sách service từ `lsnrctl services`; nếu không, xin thông tin từ DBA.
5. Kết nối bằng service name với SQL*Plus/SQLcl/SQL Developer và chạy `SELECT USER, SYS_CONTEXT('USERENV','CON_NAME') FROM dual;`.
6. Trình bày kết quả theo bảng ở mục 9, nêu rõ lớp đầu tiên thất bại và bằng chứng tương ứng.

**Kết quả mong đợi:** Bạn có thể nói chính xác “DNS chưa phân giải đúng”, “TCP chưa tới listener”, “listener chưa nhận service”, “PDB chưa mở”, hoặc “đã tới database nhưng xác thực thất bại” dựa trên kết quả thực tế — thay vì chỉ báo “Oracle không kết nối được”.

Đây là kỹ năng nền tảng khi làm việc với Oracle SQL Developer, SQLcl, SQL*Plus, ứng dụng Java JDBC, container và môi trường Oracle Database đa PDB.

