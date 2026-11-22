# Can't connect, connection refused và lỗi phân giải địa chỉ/socket

Khi ứng dụng không kết nối được MySQL, thông báo như `Can't connect to MySQL server`, `Connection refused`, `Unknown MySQL server host` hoặc `Can't connect through socket` thường bị gom chung thành lỗi database. Tuy nhiên, mỗi thông báo chỉ ra một lớp khác nhau: tên máy không phân giải được, đường mạng không tới đích, không có tiến trình lắng nghe trên cổng, socket local sai đường dẫn, hoặc MySQL chưa khởi động thành công.

Hãy chẩn đoán theo đường đi của kết nối: **ứng dụng → DNS/địa chỉ → mạng và firewall → TCP port hoặc Unix socket → MySQL listener → xác thực và TLS**. Khi xác định được lớp đầu tiên thất bại, việc sửa lỗi sẽ nhanh và ít gây thay đổi không cần thiết hơn.

## 1. Phân biệt các nhóm lỗi kết nối

Một số mã lỗi thường gặp của MySQL client:

| Mã/thông báo | Ý nghĩa thường gặp | Lớp cần kiểm tra đầu tiên |
|---|---|---|
| `2005: Unknown MySQL server host` | Client không phân giải được hostname thành địa chỉ. | DNS, tên service, search domain, cấu hình hostname. |
| `2003: Can't connect to MySQL server` | Không thiết lập được kết nối TCP đến host/port. | Địa chỉ, route, firewall, listener, port và bind address. |
| `2002: Can't connect through socket` | Client local không mở được Unix socket hoặc socket không tồn tại/không truy cập được. | Socket path, quyền file, server process và protocol client đang chọn. |
| `Connection refused` | Đích hoặc thiết bị mạng trả lời từ chối kết nối; thường không có listener ở địa chỉ/cổng đó. | MySQL service, port, bind address, container port mapping và firewall reject. |
| `Connection timed out` | Không nhận được phản hồi kết nối trong thời gian chờ. | Firewall drop, route, security group, network policy hoặc máy đích không phản hồi. |
| `1045: Access denied` | Đã tới MySQL và server từ chối xác thực/quyền đăng nhập. | User, host pattern, password, authentication plugin và TLS policy. |
| `1040: Too many connections` | MySQL nhận kết nối nhưng hết slot connection cho phép. | `max_connections`, connection leak, pool và workload. |
| `1129: Host ... is blocked` | MySQL chặn host sau nhiều lỗi kết nối theo cơ chế host cache. | Nguồn gây lỗi lặp, host cache và chính sách mạng. |
| `2006: MySQL server has gone away` | Kết nối đã mất hoặc server không còn đáp ứng khi client thực hiện thao tác. | Server restart/crash, idle timeout, packet size và mạng. |
| `2013: Lost connection to MySQL server during query` | Kết nối bị mất trong lúc truy vấn đang chạy. | Server error log, query dài, network interruption, timeout và packet. |

Mã lỗi có thể được bọc bởi framework hoặc driver nên thông báo bên ngoài không luôn giữ nguyên mã MySQL. Ghi lại exception gốc, SQLState, vendor error code, hostname, port và thời điểm xảy ra. Không đưa password hoặc toàn bộ JDBC URL có secret vào log.

## 2. Bắt đầu từ cấu hình kết nối của ứng dụng

Trước khi kiểm tra server, xác nhận ứng dụng đang thực sự kết nối tới đâu. Những lỗi cấu hình thường gặp gồm:

- Hostname cũ sau khi đổi môi trường hoặc đổi endpoint.
- Port nhầm giữa MySQL Classic Protocol (`port`, thường là `3306`) và X Protocol (`mysqlx_port`, thường là `33060`).
- Container ứng dụng dùng `localhost` thay vì hostname/service name của container MySQL.
- JDBC URL có hostname, port, database hoặc TLS property khác với cấu hình được cho là đang dùng.
- Biến môi trường không được nạp, profile Spring Boot khác hoặc secret/config map chưa cập nhật.
- DNS cache hoặc connection pool vẫn giữ địa chỉ cũ sau khi endpoint thay đổi.

Với Connector/J, một URL Classic Protocol điển hình:

```properties
spring.datasource.url=jdbc:mysql://mysql-db.internal:3306/appdb
spring.datasource.username=app_runtime
spring.datasource.password=${DB_PASSWORD}
```

Địa chỉ `mysql-db.internal` và port `3306` chỉ là ví dụ. Hãy kiểm tra giá trị hiệu lực trong runtime, không chỉ đọc file cấu hình mặc định. Nếu dùng Spring profiles, biến môi trường hoặc secret manager, xác nhận profile và nguồn cấu hình đã được kích hoạt trong tiến trình đang lỗi.

Nếu lỗi chỉ xuất hiện trong một instance ứng dụng, so sánh cấu hình, DNS resolution và network route của instance đó với một instance đang hoạt động. Đừng thay đổi cấu hình database toàn cục khi vấn đề chỉ nằm ở một pod, container hoặc host ứng dụng.

## 3. Kiểm tra hostname và DNS

Nếu lỗi báo `Unknown host`, hãy kiểm tra hostname trước khi kiểm tra password hoặc grants. Một hostname không phân giải được thì client chưa thể mở kết nối đến MySQL.

Trên Linux:

```bash
getent ahosts mysql-db.internal
nslookup mysql-db.internal
```

Trên Windows PowerShell:

```powershell
Resolve-DnsName mysql-db.internal
```

Kiểm tra:

1. Hostname có đúng chính tả và đúng domain môi trường không?
2. DNS record có tồn tại và trả về địa chỉ dự kiến không?
3. Ứng dụng có dùng DNS resolver/search domain khác với máy quản trị không?
4. Có nhiều địa chỉ IPv4/IPv6 không, và tất cả địa chỉ trả về có thể truy cập được không?
5. Endpoint có vừa được thay đổi nhưng DNS cache hoặc connection pool chưa làm mới không?

Nếu hostname phân giải thành cả IPv4 và IPv6, kiểm tra đường kết nối đến từng địa chỉ. Có thể DNS trả về IPv6 nhưng MySQL chỉ lắng nghe IPv4, hoặc firewall chỉ mở một họ địa chỉ. Dùng địa chỉ IP để thử có thể giúp khoanh vùng DNS, nhưng đó chỉ là bước chẩn đoán; cấu hình production vẫn nên dùng tên dịch vụ ổn định nếu kiến trúc yêu cầu.

Trong Docker Compose, các service trên cùng network thường tìm nhau bằng service name. Ví dụ, từ container ứng dụng kết nối đến `db:3306`; `localhost` bên trong container ứng dụng là chính container ứng dụng đó, không phải container MySQL. Từ máy host, phải dùng port đã publish, chẳng hạn `127.0.0.1:3307` nếu Compose ánh xạ `3307:3306`.

## 4. Kiểm tra TCP port từ phía client

Sau khi hostname phân giải được, kiểm tra có thể mở TCP connection tới đúng port hay không.

Trên Linux/macOS có thể dùng:

```bash
nc -vz mysql-db.internal 3306
```

Hoặc:

```bash
telnet mysql-db.internal 3306
```

Trên Windows PowerShell:

```powershell
Test-NetConnection -ComputerName mysql-db.internal -Port 3306 -InformationLevel Detailed
```

Đọc kết quả theo hướng sau:

- `TcpTestSucceeded: True` hoặc `succeeded`: TCP handshake thành công; tiếp tục kiểm tra MySQL protocol, TLS và xác thực.
- `Connection refused`: địa chỉ đã trả lời nhưng port không có listener hoặc thiết bị mạng đang chủ động reject.
- `Timed out`: gói tin có thể bị drop hoặc route không tới được; kiểm tra firewall, security group, network ACL và route.
- `No route to host`/`Network is unreachable`: kiểm tra routing, subnet, gateway và interface mạng.

TCP test thành công chưa chứng minh user/password đúng hoặc MySQL query hoạt động. Nó chỉ xác nhận đường TCP đến endpoint đã mở được.

Nếu chỉ có lỗi ở một mạng, so sánh thử từ host cùng subnet với MySQL và từ host ứng dụng. Nếu kết nối từ máy quản trị thành công nhưng từ application subnet thất bại, kiểm tra rule firewall/security group theo nguồn đích cụ thể.

## 5. Xác nhận MySQL service đang chạy

Trên máy chủ MySQL, kiểm tra service trước:

```bash
sudo systemctl status mysqld
```

Trên một số distribution, tên service là `mysql`:

```bash
sudo systemctl status mysql
```

Nếu service không chạy, đọc trạng thái và log trước khi restart liên tục:

```bash
sudo journalctl -u mysqld -n 100 --no-pager
```

Nếu service dùng tên `mysql`, thay unit tương ứng. Có thể xem error log MySQL theo vị trí được cấu hình bởi `log_error`:

```sql
SHOW VARIABLES LIKE 'log_error';
```

Các nguyên nhân service không khởi động được gồm cấu hình sai, port bị chiếm, quyền data directory sai, thiếu dung lượng đĩa, file InnoDB/redo không hợp lệ, plugin không tải được hoặc lỗi sau nâng cấp. Error log thường cho biết nguyên nhân cụ thể hơn thông báo từ ứng dụng.

Không xóa file trong data directory, socket hoặc PID file một cách tùy tiện để ép service chạy. Trước khi thay đổi file, xác nhận tiến trình MySQL đã dừng và hiểu file đó do service quản lý như thế nào.

## 6. Kiểm tra MySQL có lắng nghe đúng địa chỉ và port

Khi service đang chạy, kiểm tra listener ở cấp hệ điều hành.

Linux:

```bash
sudo ss -lntp | grep 3306
```

Hoặc:

```bash
sudo netstat -lntp | grep 3306
```

Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 3306 -State Listen
```

Nếu không có listener, kiểm tra cấu hình MySQL:

```sql
SHOW VARIABLES LIKE 'port';
SHOW VARIABLES LIKE 'bind_address';
SHOW VARIABLES LIKE 'skip_networking';
SHOW VARIABLES LIKE 'socket';
```

Các biến SQL trên cần chạy được khi đã có kết nối local hoặc một phiên quản trị khác. Nếu không kết nối được, đọc file cấu hình server và error log để xác định giá trị hiệu lực.

Ý nghĩa chính:

- `port`: cổng Classic Protocol mà server dùng để nhận TCP connection.
- `bind_address`: địa chỉ interface mà MySQL bind listener. Nếu chỉ bind loopback, client từ máy khác không thể kết nối qua interface private/public.
- `skip_networking`: khi bật, MySQL không nhận kết nối TCP/IP; kết nối local qua Unix socket vẫn có thể hoạt động.
- `socket`: đường dẫn Unix socket trên hệ điều hành Unix-like.

Không đặt `bind_address=0.0.0.0` hoặc mở port ra mọi interface chỉ để thử nếu chưa kiểm soát firewall và nguồn truy cập. Chọn private interface hoặc địa chỉ cần thiết, rồi giới hạn firewall theo subnet ứng dụng.

Nếu port `3306` đang được một tiến trình khác sử dụng, MySQL có thể không bind được và ghi lỗi `Address already in use` trong error log. Xác định process đang giữ port trước khi quyết định đổi port hoặc dừng dịch vụ khác.

## 7. Phân biệt TCP với Unix socket

Trên Linux/macOS, client MySQL có thể kết nối local qua Unix domain socket hoặc TCP. Khi dùng `localhost`, một số client command line chọn Unix socket; khi dùng `127.0.0.1`, client dùng TCP. Điều này giải thích tình huống lệnh `mysql -h localhost` thành công nhưng `mysql -h 127.0.0.1` thất bại, hoặc ngược lại.

Ép client dùng TCP:

```bash
mysql --protocol=TCP -h 127.0.0.1 -P 3306 -u app_runtime -p
```

Ép client dùng Unix socket:

```bash
mysql --protocol=SOCKET \
  --socket=/var/run/mysqld/mysqld.sock \
  -u app_runtime -p
```

Đường dẫn socket ở ví dụ phải thay bằng giá trị thực của server/client. Kiểm tra biến `socket` trong cấu hình server và option socket của client; hai bên phải trỏ đến cùng file socket. Ngoài ra, user hệ điều hành chạy ứng dụng phải có quyền truy cập thư mục cha và socket file.

Một số nguyên nhân socket error:

- MySQL chưa khởi động nên socket chưa được tạo.
- Server tạo socket ở `/var/lib/mysql/mysql.sock` nhưng client tìm ở `/var/run/mysqld/mysqld.sock`.
- File socket cũ còn lại sau crash nhưng không có server đang lắng nghe.
- Quyền thư mục/socket không cho user ứng dụng truy cập.
- Client đang ép `SOCKET` trong khi server chỉ được truy cập qua TCP hoặc socket path khác.

Trên Windows, các protocol local có thể gồm TCP, named pipe hoặc shared memory tùy cấu hình. Không áp dụng đường dẫn Unix socket cho Windows; dùng protocol và pipe name được cấu hình trên cả client lẫn server.

Lưu ý: Connector/J kết nối MySQL qua TCP/IP, không dùng Unix socket theo cách `mysql` command line có thể dùng. Vì vậy, kiểm tra `localhost` qua socket bằng CLI không chứng minh JDBC URL TCP sẽ hoạt động.

## 8. Kiểm tra firewall, security group và network policy

Nếu MySQL đang lắng nghe đúng interface/port nhưng client không kết nối được, kiểm tra lớp mạng ở cả hai đầu:

- Firewall trên máy chủ: `firewalld`, `ufw`, Windows Defender Firewall hoặc `iptables`/`nftables`.
- Cloud security group/network security group: inbound rule cho port MySQL từ đúng subnet hoặc security identity của ứng dụng.
- Network ACL, route table, VPN, peering và gateway giữa các subnet.
- Kubernetes NetworkPolicy, service selector, endpoint và service port nếu ứng dụng chạy trong cluster.
- Firewall phía client hoặc proxy trung gian có chặn outbound không.

Mở đúng port cho đúng nguồn. Ví dụ, nếu ứng dụng ở subnet `10.20.0.0/16`, rule inbound nên giới hạn nguồn vào subnet hoặc security group đó thay vì `0.0.0.0/0`. Port `3306` không nên được mở trực tiếp ra Internet.

Nếu có thể, kiểm tra packet ở cả client và server bằng công cụ network được phê duyệt. Nếu SYN đến server nhưng không có SYN-ACK, kiểm tra listener và firewall host. Nếu SYN không đến server, điều tra route hoặc firewall ở giữa. Nếu server gửi RST, thường không có listener ở địa chỉ/port đích hoặc có thiết bị chủ động từ chối.

## 9. Kiểm tra Docker và Kubernetes

### Docker Compose

Một cấu hình thường gặp:

```yaml
services:
  app:
    build: .
    environment:
      DB_HOST: db
      DB_PORT: 3306
    depends_on:
      db:
        condition: service_healthy

  db:
    image: mysql:8.4.4
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: appdb
    ports:
      - "3307:3306"
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "-p${MYSQL_ROOT_PASSWORD}"]
      interval: 5s
      timeout: 3s
      retries: 20
```

Trong network Compose, app kết nối `db:3306`. Từ host máy developer, kết nối `127.0.0.1:3307`. Cổng host `3307` được ánh xạ vào cổng container `3306`; dùng `localhost:3306` từ app container sẽ trỏ về chính app container.

`depends_on` với `condition: service_healthy` chờ healthcheck khi Compose hỗ trợ điều kiện này, nhưng không thay thế retry ở ứng dụng. Database có thể restart sau khi app đã khởi động, hoặc healthcheck chỉ xác nhận server trả lời cục bộ chứ chưa chứng minh user/schema ứng dụng có thể sử dụng.

Kiểm tra:

```bash
docker compose ps
docker compose logs db
docker compose exec db mysqladmin ping -h 127.0.0.1 -uroot -p
```

Không đặt password thật trong lệnh hoặc shell history; ví dụ cuối dùng prompt để nhập mật khẩu. Xác nhận container đang healthy và port mapping đúng bằng `docker compose ps`.

### Kubernetes

Nếu ứng dụng chạy trong Kubernetes, thường nên kết nối qua DNS của Service, ví dụ `mysql.database.svc.cluster.local`, thay vì IP Pod. Kiểm tra:

1. Service có selector khớp label Pod MySQL không?
2. Service port và targetPort có trỏ đúng cổng listener không?
3. EndpointSlice có endpoint Pod Ready không?
4. NetworkPolicy có cho phép traffic từ namespace/pod ứng dụng đến database không?
5. Readiness probe có phản ánh trạng thái MySQL đủ để nhận kết nối không?

Một Service không có endpoint Ready có thể dẫn tới timeout hoặc connection failure dù Pod MySQL vẫn tồn tại. Kiểm tra DNS từ chính Pod ứng dụng vì resolver và search domain bên trong Pod có thể khác máy local.

## 10. Sau khi TCP kết nối được: phân biệt lỗi mạng với lỗi xác thực

Khi TCP handshake thành công, client mới trao đổi MySQL protocol, thương lượng TLS (nếu bật) và xác thực. Nếu nhận `1045 Access denied`, kết nối đã tới MySQL; lúc này tập trung vào user, host, password, plugin và grants thay vì tiếp tục thay firewall.

MySQL phân biệt account theo cặp `user` và `host`. Ví dụ:

```sql
CREATE USER 'app_runtime'@'10.20.%' IDENTIFIED BY 'managed-secret';
GRANT SELECT, INSERT, UPDATE, DELETE ON appdb.*
TO 'app_runtime'@'10.20.%';

SHOW GRANTS FOR 'app_runtime'@'10.20.%';
```

Ví dụ chỉ minh họa cách account host pattern hoạt động; hãy tạo đúng account theo nguồn kết nối thực tế và cấp quyền tối thiểu. Nếu ứng dụng đi qua NAT, proxy hoặc Kubernetes egress gateway, MySQL có thể nhìn thấy IP nguồn khác với IP của Pod.

Kiểm tra plugin xác thực và TLS nếu lỗi xuất hiện sau nâng cấp driver/server. Connector/J và MySQL phải có phương thức xác thực tương thích. Với TLS, xác nhận CA, certificate hostname, trust store và chính sách verify; không tắt kiểm tra certificate trong production chỉ để vượt qua handshake error.

Nếu lỗi là `1040 Too many connections`, kiểm tra:

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
SHOW VARIABLES LIKE 'max_connections';
SHOW FULL PROCESSLIST;
```

Tìm connection leak, pool tạo quá nhiều connection trên nhiều instance, transaction giữ connection lâu hoặc workload tăng đột biến. Tăng `max_connections` mà không xem RAM và giới hạn hệ thống có thể làm server quá tải hơn.

## 11. Kiểm tra MySQL host cache và host bị block

MySQL theo dõi lỗi kết nối từ host. Nếu số lần lỗi vượt ngưỡng `max_connect_errors`, server có thể chặn host và trả lỗi 1129. Điều tra nguồn lỗi lặp trước khi xóa trạng thái block:

```sql
SHOW VARIABLES LIKE 'max_connect_errors';

SELECT
    IP,
    HOST,
    HOST_VALIDATED,
    SUM_CONNECT_ERRORS,
    COUNT_HOST_BLOCKED_ERRORS
FROM performance_schema.host_cache;
```

Tên cột trong `performance_schema.host_cache` phụ thuộc phiên bản. Kiểm tra cấu trúc bảng trên server hiện tại nếu truy vấn không chạy. Sửa nguyên nhân như lỗi mạng, DNS ngược hoặc client retry sai trước khi mở block.

Sau khi xác nhận an toàn, trên các phiên bản còn hỗ trợ, tài khoản có quyền quản trị có thể dùng:

```sql
FLUSH HOSTS;
```

`FLUSH HOSTS` đã deprecated trong MySQL 8.0.23. Trên các phiên bản hỗ trợ thao tác trực tiếp với Performance Schema host cache, cách thay thế là:

```sql
TRUNCATE TABLE performance_schema.host_cache;
```

Kiểm tra tài liệu và quyền cần thiết của đúng phiên bản trước khi dùng. Việc xóa host cache chỉ gỡ trạng thái hiện tại; nó không sửa lỗi mạng, DNS hoặc client đang retry sai. Không dùng các lệnh này như cách xử lý định kỳ nếu host tiếp tục phát sinh lỗi kết nối.

## 12. Connection pool và thời điểm khởi động ứng dụng

Một ứng dụng có thể khởi động trước MySQL hoặc trong lúc MySQL đang restart. Nếu pool chỉ thử kết nối một lần, ứng dụng có thể ở trạng thái lỗi dù database đã sẵn sàng sau đó.

Thiết kế kết nối nên có:

- Connection timeout hữu hạn để request không treo vô thời hạn.
- Retry có backoff và jitter khi khởi động hoặc sau sự cố tạm thời.
- Validation query/connection test phù hợp với pool và driver.
- Loại bỏ connection đã hỏng sau failover hoặc server restart.
- Giới hạn pool theo tổng số instance và `max_connections` của MySQL.
- Readiness check của ứng dụng phản ánh khả năng phục vụ, nhưng không tạo vòng lặp restart liên tục khi database đang bảo trì.

Với HikariCP, cấu hình minh họa:

```yaml
spring:
  datasource:
    hikari:
      connection-timeout: 30000
      validation-timeout: 5000
      maximum-pool-size: 10
      minimum-idle: 2
```

Các giá trị phải dựa trên tải và ngân sách connection toàn hệ thống. Nếu có 20 instance ứng dụng với pool tối đa 10, database có thể phải phục vụ đến 200 connection từ ứng dụng, chưa tính job, admin và replication. Pool lớn không đồng nghĩa truy vấn nhanh hơn; quá nhiều connection đồng thời có thể làm CPU, memory và lock contention tăng.

## 13. Quy trình chẩn đoán theo thứ tự

Thực hiện tuần tự và ghi lại kết quả để biết lỗi nằm ở lớp nào:

1. **Xác nhận endpoint**: đọc cấu hình hiệu lực của ứng dụng, hostname, port, protocol và database.
2. **Phân giải DNS**: xác nhận hostname trả về địa chỉ đúng từ chính môi trường ứng dụng.
3. **Kiểm tra TCP**: dùng `nc` hoặc `Test-NetConnection` đến đúng IP/port.
4. **Kiểm tra server process**: xác nhận MySQL service đang chạy và đọc error log.
5. **Kiểm tra listener**: xác nhận `port`, `bind_address`, `skip_networking` và địa chỉ socket.
6. **Kiểm tra network policy**: firewall host, security group, route, container mapping hoặc Kubernetes Service/NetworkPolicy.
7. **Thử MySQL client**: dùng cùng host/port/protocol từ môi trường ứng dụng, với tài khoản được phép.
8. **Phân loại lỗi protocol/authentication**: `1045`, TLS handshake, authentication plugin, `1040` hoặc host blocked.
9. **Kiểm tra pool và retry**: xem connection lifetime, stale connection, startup order và số lượng connection.
10. **Xác minh bằng log và thời gian**: đối chiếu application log, MySQL error log, firewall log và sự kiện deploy/restart.

Một bảng ghi nhận đơn giản:

| Bước | Kết quả | Diễn giải |
|---|---|---|
| DNS | Hostname trả về IP đúng | Có thể tiếp tục kiểm tra network. |
| TCP | Port mở từ app host | Đường TCP tới listener đã hoạt động. |
| Service | MySQL active | Tiến trình đang chạy; vẫn cần xác nhận listener. |
| Listener | Đúng IP/port | MySQL đang bind đúng endpoint dự kiến. |
| MySQL protocol | Server trả handshake | Client đã tới MySQL protocol layer. |
| Authentication | Đăng nhập thành công | User/host/password/plugin/TLS đã hợp lệ. |
| Query | Query kiểm tra thành công | Kết nối đủ khả năng thực hiện SQL trong phạm vi quyền. |

## 14. Ví dụ xử lý ba tình huống điển hình

### Tình huống A: ứng dụng báo Connection refused

Ứng dụng dùng `mysql-db.internal:3306` và nhận `Connection refused`.

1. `Resolve-DnsName`/`getent ahosts` cho thấy hostname phân giải đúng.
2. `Test-NetConnection`/`nc` báo từ chối ở port `3306`.
3. Trên MySQL host, `systemctl status mysqld` cho thấy service failed.
4. Error log báo port đã được tiến trình khác sử dụng.
5. Xác định tiến trình giữ port, xác nhận có phải MySQL instance cũ hay dịch vụ khác, sau đó xử lý xung đột và khởi động MySQL theo runbook.
6. Kiểm tra listener và thử lại từ app host.

Không giải quyết bằng cách mở firewall rộng hơn vì nguyên nhân là server không bind được port.

### Tình huống B: localhost chạy được nhưng container app không kết nối

MySQL hoạt động trên máy host; lệnh `mysql -h localhost` thành công, nhưng app container báo timeout.

1. Xác nhận CLI có thể đang dùng Unix socket vì hostname là `localhost`.
2. Dùng `mysql --protocol=TCP -h 127.0.0.1 -P 3306` trên host để thử TCP.
3. Trong container app, `localhost` là chính container app.
4. Dùng service name `db` và port nội bộ `3306` nếu hai container cùng network Compose.
5. Kiểm tra `docker compose ps`, healthcheck, log và network membership.

Kết quả: thay endpoint app thành `db:3306` thay vì `localhost:3306` hoặc port publish của host.

### Tình huống C: TCP mở nhưng ứng dụng nhận Access denied

`nc -vz mysql-db.internal 3306` thành công nhưng JDBC báo `1045`.

1. Đường DNS/TCP/listener đã hoạt động.
2. Xác nhận username và secret thực tế mà app đang dùng.
3. Kiểm tra MySQL account có đúng host pattern cho IP nguồn mà server nhìn thấy không.
4. Kiểm tra authentication plugin, TLS requirement và grants.
5. Cấp đúng quyền cho account ứng dụng và xác minh bằng chính kết nối từ app host.

Không cần thay port hoặc bind address nếu server đã nhận được handshake và trả lỗi xác thực.

## 15. Checklist trước khi kết luận lỗi kết nối đã hết

- [ ] Ứng dụng đang dùng đúng hostname, port, protocol và profile cấu hình.
- [ ] Hostname phân giải được từ chính máy/container/pod ứng dụng.
- [ ] TCP connection mở được đến đúng IP và port.
- [ ] MySQL service đang chạy và error log không có lỗi khởi động/listener.
- [ ] `bind_address`, `port`, `skip_networking` và socket path phù hợp.
- [ ] Firewall, security group, route và network policy chỉ mở đúng nguồn cần thiết.
- [ ] Docker/Kubernetes service name, port mapping và endpoint được xác nhận.
- [ ] Client protocol phù hợp: TCP, Unix socket hoặc named pipe.
- [ ] Nếu nhận `1045`, user/host/password/plugin/TLS đã được kiểm tra.
- [ ] Nếu nhận `1040`, connection pool và tổng ngân sách connection đã được xem xét.
- [ ] Pool có timeout, validation và retry phù hợp; stale connection được loại bỏ.
- [ ] Đã xác nhận kết nối bằng query thực tế với tài khoản ứng dụng.

Lỗi kết nối MySQL cần được xử lý theo đúng lớp thất bại. `Unknown host` dẫn đến DNS; `Connection refused` dẫn đến listener/port hoặc reject ở mạng; socket error dẫn đến protocol và đường dẫn socket; timeout dẫn đến route/firewall; `1045` là lỗi xác thực sau khi đã tới server. Khi ghi lại endpoint, kết quả từng bước và log tương ứng, đội vận hành có thể khoanh vùng nguyên nhân nhanh, sửa đúng thành phần và tránh thay đổi cấu hình bảo mật hoặc mạng quá rộng.
