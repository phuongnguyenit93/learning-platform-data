# Xử lý lỗi không kết nối được PostgreSQL do DNS, mạng, TLS, xác thực hoặc pg_hba.conf

Khi ứng dụng không kết nối được PostgreSQL, thông báo lỗi thường xuất hiện ở phía client nhưng nguyên nhân có thể nằm ở DNS, đường truyền, cấu hình lắng nghe của máy chủ, TLS, quy tắc truy cập hoặc thông tin xác thực. Cách xử lý hiệu quả là xác định kết nối dừng ở lớp nào, thu thập bằng chứng tại đúng máy chạy ứng dụng rồi sửa đúng cấu hình liên quan.

Một thông báo như `connection refused` khác hoàn toàn với `password authentication failed`: lỗi thứ nhất xảy ra trước khi PostgreSQL xác thực người dùng; lỗi thứ hai cho thấy client đã đến được máy chủ và tiến trình PostgreSQL đã xử lý yêu cầu đăng nhập. Phân biệt được điều này giúp tránh thay đổi mật khẩu hoặc mở firewall khi vấn đề thực tế nằm ở DNS hay TLS.

## 1. Hiểu đường đi của một kết nối PostgreSQL

Với kết nối TCP thông thường, client đi qua các bước chính:

1. Phân giải tên máy chủ thành địa chỉ IP.
2. Thiết lập đường mạng TCP đến IP và cổng PostgreSQL.
3. Kết nối đến tiến trình PostgreSQL đang lắng nghe.
4. Thương lượng TLS nếu client yêu cầu hoặc chế độ SSL cho phép.
5. Máy chủ đối chiếu kết nối với quy tắc trong `pg_hba.conf`.
6. PostgreSQL xác thực role bằng phương thức được quy định.
7. Máy chủ kiểm tra database đích và quyền kết nối, sau đó tạo session.

Kết nối qua Unix domain socket bỏ qua DNS và TCP, đồng thời thường khớp với các dòng `local` trong `pg_hba.conf`. Vì thế, kết nối local thành công không chứng minh ứng dụng từ máy khác có thể kết nối qua TCP.

Sơ đồ chẩn đoán:

~~~mermaid
flowchart TD
    A["Ứng dụng đọc host, port, database, user"] --> B["DNS phân giải host"]
    B -->|Thất bại| D["Kiểm tra DNS, resolver, hostname"]
    B -->|Thành công| C["Thiết lập TCP"]
    C -->|Timeout / refused| E["Kiểm tra route, firewall, listener, port"]
    C -->|Thành công| F["Thương lượng TLS"]
    F -->|Lỗi TLS| G["Kiểm tra sslmode, CA, certificate, hostname"]
    F -->|Thành công| H["Đối chiếu pg_hba.conf"]
    H -->|Không có rule phù hợp| I["Sửa rule, CIDR, thứ tự, SSL mode"]
    H -->|Có rule| J["Xác thực role"]
    J -->|Thất bại| K["Kiểm tra password, role, auth method"]
    J -->|Thành công| L["Kiểm tra database và quyền CONNECT"]
    L --> M["Kết nối thành công"]
~~~

Không phải mọi driver đều hiển thị riêng từng bước. Một số thư viện gói lỗi TLS, socket hoặc xác thực thành thông báo chung. Khi đó, hãy đối chiếu thông báo client với log máy chủ và các phép thử ở từng lớp.

## 2. Thu thập thông tin trước khi thay đổi cấu hình

Trước tiên, ghi lại:

- Thời điểm lỗi và thông báo đầy đủ, bao gồm phần nguyên nhân lồng bên trong nếu driver cung cấp.
- Máy hoặc container chạy ứng dụng, môi trường mạng và địa chỉ IP mà máy chủ nhìn thấy.
- Hostname, port, database, role và chế độ TLS đang dùng.
- Phiên bản PostgreSQL và phiên bản driver/client.
- Lỗi xảy ra với mọi client hay chỉ một ứng dụng, một máy hoặc một mạng.
- Thời điểm bắt đầu lỗi và các thay đổi gần đó: DNS, firewall, chứng chỉ, mật khẩu, cấu hình, triển khai ứng dụng hoặc failover.

Không đưa password, chuỗi kết nối có mật khẩu, private key hay token vào ticket, log chia sẻ hoặc lệnh chẩn đoán công khai. Có thể che giá trị nhạy cảm nhưng vẫn giữ hostname, port, database, username và chế độ TLS để đối chiếu.

Thử kết nối từ chính môi trường chạy ứng dụng. Kiểm tra từ laptop của quản trị viên có thể cho kết quả khác vì DNS, route, NAT, firewall và địa chỉ nguồn khác nhau.

## 3. Kiểm tra DNS và hostname

### 3.1. Nhận biết lỗi DNS

Các thông báo thường gặp:

- `could not translate host name ... to address`
- `Name or service not known`
- `Temporary failure in name resolution`
- `No such host is known`

Những lỗi này xảy ra trước khi client thiết lập kết nối TCP đến PostgreSQL. Kiểm tra hostname trong cấu hình ứng dụng, biến môi trường, secret hoặc connection string; đặc biệt chú ý tên môi trường staging/production và dấu chấm, dấu gạch ngang trong hostname.

### 3.2. Kiểm tra phân giải tên

Trên Linux:

~~~bash
getent ahosts db.example.internal
dig +short A db.example.internal
dig +short AAAA db.example.internal
~~~

Trên Windows PowerShell:

~~~powershell
Resolve-DnsName db.example.internal -Type A
Resolve-DnsName db.example.internal -Type AAAA
~~~

Kết quả cần đối chiếu với địa chỉ IP hiện tại của PostgreSQL hoặc endpoint do nhà cung cấp cấp. Nếu có cả bản ghi A và AAAA, client có thể thử IPv6 trong khi firewall hoặc route IPv6 chưa được cấu hình đúng. Nếu DNS trả nhiều địa chỉ, hãy kiểm tra từng địa chỉ vì một node cũ hoặc endpoint lỗi có thể làm kết quả chập chờn.

Nếu DNS nội bộ dùng split-horizon, hãy kiểm tra từ đúng VPC, subnet, VPN, cluster hoặc container nơi ứng dụng chạy. Một hostname có thể phân giải thành IP private ở mạng nội bộ và IP khác ở mạng bên ngoài.

### 3.3. Phân biệt lỗi DNS với lỗi mạng

Có thể dùng địa chỉ IP để kiểm tra tạm thời xem vấn đề có nằm ở phân giải tên hay không. Với libpq, `hostaddr` chỉ định địa chỉ mạng còn `host` giữ hostname logic:

~~~bash
psql "host=db.example.internal hostaddr=10.20.30.40 port=5432 dbname=appdb user=app_user connect_timeout=5"
~~~

Nếu kết nối bằng IP hoạt động nhưng dùng hostname thất bại, hãy kiểm tra DNS, cache resolver và cấu hình hostname. Khi bật `sslmode=verify-full`, vẫn cần giữ đúng hostname để xác minh tên trong chứng chỉ máy chủ; đừng thay hostname bằng IP chỉ để né lỗi chứng chỉ.

Chỉ xóa cache DNS khi đã xác định máy client đang giữ kết quả cũ. Trên Windows có thể dùng `ipconfig /flushdns`; trên Linux, cách xóa cache phụ thuộc resolver như systemd-resolved, dnsmasq hoặc dịch vụ mạng đang dùng. Xóa cache không sửa được bản ghi DNS sai ở máy chủ DNS.

## 4. Kiểm tra mạng TCP và PostgreSQL listener

### 4.1. Phân biệt timeout và connection refused

| Thông báo | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `connection timed out` | Gói tin không nhận được phản hồi trong thời gian chờ | Route, firewall, security group, ACL, VPN, NetworkPolicy |
| `connection refused` | Đích từ chối TCP, thường do không có listener ở IP/port đó hoặc firewall chủ động reject | PostgreSQL chưa chạy, sai port, sai địa chỉ bind, rule firewall |
| `No route to host` / `Network is unreachable` | Máy client không có đường đến mạng đích hoặc bị chặn ở tầng mạng | Route, subnet, gateway, VPN, địa chỉ IP |
| `server closed the connection unexpectedly` | Kết nối bị đóng bất ngờ sau khi đã bắt đầu | Log server, restart/crash, proxy, mạng, TLS hoặc lỗi phía client |

Đây là dấu hiệu định hướng, không phải kết luận tuyệt đối. Firewall có thể trả về lỗi từ chối hoặc âm thầm bỏ gói; proxy và load balancer cũng có thể tạo thông báo khác với kết nối trực tiếp.

### 4.2. Kiểm tra cổng từ client

Trên Linux có thể dùng netcat:

~~~bash
nc -vz db.example.internal 5432
~~~

Trên Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName db.example.internal -Port 5432
~~~

Nếu TCP không thiết lập được, chưa cần đổi password hay sửa quyền role. Hãy kiểm tra:

- Địa chỉ IP và port mà client đang dùng.
- Route giữa subnet của ứng dụng và subnet database.
- Firewall trên máy chủ và firewall mạng.
- Security group, network ACL hoặc firewall policy của cloud.
- VPN, peering, NAT gateway, proxy hoặc load balancer.
- Kubernetes Service, Endpoint/EndpointSlice và NetworkPolicy nếu ứng dụng chạy trong cluster.
- Cổng database có được publish/forward đúng nếu PostgreSQL chạy trong container hay không.

Đối với firewall theo địa chỉ nguồn, cần xác định IP nguồn mà máy chủ thực sự nhìn thấy. NAT, egress gateway hoặc proxy có thể khiến IP đó khác địa chỉ private của container hay máy ứng dụng. Đừng thêm CIDR dựa trên địa chỉ đoán từ máy phát triển.

### 4.3. Kiểm tra PostgreSQL có lắng nghe đúng địa chỉ và port

Một máy chủ có PostgreSQL đang chạy vẫn có thể từ chối kết nối từ xa nếu tiến trình chỉ bind vào loopback.

Kết nối bằng socket local hoặc một phiên quản trị đang hoạt động, rồi kiểm tra:

~~~sql
SHOW listen_addresses;
SHOW port;
SHOW config_file;
SHOW hba_file;
~~~

- `listen_addresses` xác định địa chỉ IP mà PostgreSQL nhận kết nối TCP.
- `port` là cổng TCP của instance.
- `config_file` và `hba_file` cho biết file cấu hình thực tế, tránh sửa nhầm bản sao không được instance sử dụng.

Giá trị mặc định thường là `localhost`, chỉ nhận kết nối local. Nếu cần nhận kết nối từ mạng, hãy cấu hình địa chỉ private phù hợp hoặc `*` khi đã có kiểm soát mạng tương ứng. Không nên mở listener ra mọi giao diện công cộng nếu không có yêu cầu và lớp bảo vệ rõ ràng.

Trên Linux, có thể xem socket đang lắng nghe:

~~~bash
ss -lntp | grep 5432
~~~

Trên Windows:

~~~powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen
~~~

Nếu không thấy listener, kiểm tra trạng thái service, log khởi động, port cấu hình và tiến trình PostgreSQL. Nếu listener chỉ xuất hiện ở `127.0.0.1:5432` hoặc `[::1]:5432`, nó chưa nhận kết nối từ interface mạng khác.

Thay đổi `listen_addresses` hoặc `port` cần restart PostgreSQL vì đây là các tham số khởi động. Reload cấu hình không áp dụng được thay đổi yêu cầu restart. Trước khi restart, cần đánh giá tác động đến ứng dụng, replica, connection pool và lịch bảo trì.

### 4.4. Kiểm tra trạng thái server bằng pg_isready

~~~bash
pg_isready -h db.example.internal -p 5432 -d appdb -U app_user
~~~

`pg_isready` kiểm tra PostgreSQL có nhận kết nối hay không. Exit code thường là:

- `0`: server đang chấp nhận kết nối.
- `1`: server đang từ chối kết nối, ví dụ đang khởi động hoặc shutdown.
- `2`: không có phản hồi.
- `3`: tham số gọi không hợp lệ.

Lệnh này không chứng minh password đúng, role có quyền hoặc ứng dụng có thể hoàn tất đăng nhập. Hãy dùng `psql` để kiểm tra toàn bộ quá trình xác thực.

## 5. Kiểm tra TLS và chứng chỉ

PostgreSQL có thể mã hóa kết nối TCP bằng TLS. Lỗi TLS thường xảy ra sau khi TCP đã kết nối nhưng trước khi hoàn tất xác thực.

### 5.1. Các chế độ sslmode của libpq

Với client dùng libpq, tham số `sslmode` quyết định cách xử lý TLS:

| sslmode | Hành vi |
|---|---|
| `disable` | Không dùng TLS |
| `allow` | Thử không mã hóa trước, chỉ thử TLS nếu kết nối không mã hóa thất bại |
| `prefer` | Thử TLS trước, có thể quay về không mã hóa |
| `require` | Yêu cầu kết nối mã hóa TLS, không xác minh đầy đủ danh tính máy chủ theo cách của `verify-full` |
| `verify-ca` | Yêu cầu TLS và xác minh chuỗi chứng chỉ theo CA tin cậy |
| `verify-full` | Yêu cầu TLS, xác minh chuỗi CA và hostname của máy chủ |

Trong môi trường production, ưu tiên `verify-full` với CA tin cậy và hostname khớp chứng chỉ. `prefer` có thể cho phép client rơi về kết nối không mã hóa; `require` bảo đảm mã hóa nhưng không thay thế việc xác minh danh tính máy chủ.

Không nên dùng `sslmode=disable` như cách khắc phục lâu dài. Nếu chế độ này làm kết nối thành công, kết quả chỉ cho thấy đường kết nối không TLS đang hoạt động; cần xử lý cấu hình TLS và yêu cầu bảo mật của hệ thống.

### 5.2. Các lỗi chứng chỉ thường gặp

| Lỗi | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Certificate verify failed | CA chưa được tin cậy, thiếu intermediate certificate hoặc chuỗi chứng chỉ không hợp lệ | Cài đúng CA và cấu hình `sslrootcert` |
| Hostname mismatch | Hostname client dùng không khớp SAN/CN hợp lệ của chứng chỉ | Dùng endpoint đúng hoặc cấp lại chứng chỉ có SAN phù hợp |
| Certificate has expired | Chứng chỉ hết hạn | Gia hạn, triển khai chứng chỉ mới và reload theo quy trình |
| Server does not support SSL | SSL phía server chưa bật, client đang kết nối nhầm endpoint hoặc proxy không hỗ trợ TLS PostgreSQL | Kiểm tra `ssl`, endpoint và cấu hình proxy |
| No certificate provided / certificate required | Server yêu cầu chứng chỉ client nhưng client chưa gửi hoặc gửi sai | Cấu hình client certificate và private key phù hợp |
| Private key permission denied | Tiến trình client không đọc được private key hoặc quyền file quá rộng | Sửa owner và quyền truy cập key |

Với `verify-full`, hostname phải khớp tên trong chứng chỉ máy chủ. Nếu client kết nối bằng alias DNS, alias đó cũng cần xuất hiện trong Subject Alternative Name (SAN) của chứng chỉ.

### 5.3. Cấu hình TLS phía client

Ví dụ kết nối bằng libpq với CA của tổ chức:

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/certs/root-ca.crt connect_timeout=5"
~~~

Nếu server yêu cầu chứng chỉ client:

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user sslmode=verify-full sslrootcert=/etc/postgresql/certs/root-ca.crt sslcert=/etc/postgresql/certs/client.crt sslkey=/etc/postgresql/private/client.key"
~~~

Đường dẫn chỉ là ví dụ; phải dùng chứng chỉ do hệ thống cấp. Private key cần được bảo vệ và chỉ cấp quyền đọc cho user chạy ứng dụng. Trên Unix, libpq thường yêu cầu private key không cho nhóm hoặc người dùng khác đọc; quyền `0600` là lựa chọn phổ biến.

Một số thư viện Java, .NET, Node.js và driver PostgreSQL có tên tham số hoặc cách cấu hình trust store riêng. Hãy kiểm tra tài liệu đúng phiên bản driver. Không giả định `sslmode`, `sslrootcert` hoặc đường dẫn chứng chỉ của libpq có thể dùng nguyên trạng trong mọi driver.

### 5.4. Kiểm tra TLS phía server và phiên kết nối

Khi đã có quyền kết nối quản trị:

~~~sql
SHOW ssl;
SHOW ssl_cert_file;
SHOW ssl_key_file;
SHOW ssl_ca_file;
~~~

`ssl` phải được bật nếu server cần phục vụ kết nối TLS. Kiểm tra chứng chỉ, private key, chuỗi CA và quyền đọc file theo user chạy PostgreSQL. Tham số nào cần restart hay chỉ cần reload phụ thuộc context của tham số và phiên bản; xem `pg_settings` thay vì mặc định rằng mọi thay đổi TLS đều áp dụng giống nhau.

Để xác nhận session hiện tại đang mã hóa:

~~~sql
SELECT
    ssl,
    version,
    cipher,
    bits
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
~~~

Nếu `ssl` là `true`, session hiện tại dùng TLS. View này chỉ cho biết trạng thái của kết nối đã được tạo; nó không chẩn đoán được một client đang thất bại trước khi đăng nhập.

## 6. Kiểm tra pg_hba.conf

`pg_hba.conf` (Host-Based Authentication) là nơi PostgreSQL quy định client nào được kết nối đến database nào, bằng role nào, từ địa chỉ nào và qua phương thức xác thực nào.

Đây là cấu hình phía server. Sửa file trên máy client không thay đổi chính sách truy cập của PostgreSQL.

### 6.1. Cấu trúc một dòng HBA

Các dạng phổ biến:

~~~text
# TYPE     DATABASE   USER       ADDRESS          METHOD
local      appdb      app_user                    scram-sha-256
host       appdb      app_user   10.20.30.0/24    scram-sha-256
hostssl    appdb      app_user   10.20.30.0/24    scram-sha-256
hostnossl  appdb      app_user   10.20.30.0/24    reject
~~~

Các loại kết nối quan trọng:

- `local`: Unix domain socket, không có cột địa chỉ IP.
- `host`: TCP, có thể dùng TLS hoặc không TLS.
- `hostssl`: TCP qua TLS.
- `hostnossl`: TCP không dùng TLS.

Một kết nối TCP không khớp với dòng `local`. Nếu ứng dụng chuyển từ socket local sang hostname hoặc IP, nó cần một rule `host`, `hostssl` hoặc `hostnossl` phù hợp.

### 6.2. Quy tắc khớp và thứ tự dòng

PostgreSQL đọc các dòng HBA từ trên xuống. **Rule đầu tiên khớp đầy đủ loại kết nối, database, user và địa chỉ sẽ được áp dụng.** Nếu xác thực bằng rule đó thất bại, PostgreSQL không tiếp tục thử các dòng sau.

Ví dụ:

~~~text
host    all     all         10.20.30.0/24    reject
hostssl appdb   app_user    10.20.30.0/24    scram-sha-256
~~~

Với client thuộc subnet trên, dòng `reject` đầu tiên đã khớp nên dòng `hostssl` phía sau không bao giờ được xét. Cần sắp xếp rule cụ thể và rule tổng quát theo thứ tự phù hợp.

Các trường database và user cũng phải khớp. Một rule cho `appdb` không cho phép tự động kết nối database `reporting`; một rule cho `app_user` không áp dụng cho role khác.

### 6.3. Xác định địa chỉ nguồn và CIDR

Trường `ADDRESS` là địa chỉ nguồn mà PostgreSQL nhìn thấy. Nếu client đi qua NAT, egress gateway, proxy hoặc load balancer, địa chỉ đó có thể khác IP gốc của máy ứng dụng.

Ví dụ:

~~~text
hostssl appdb app_user 10.20.30.0/24 scram-sha-256
~~~

Rule trên cho phép các địa chỉ IPv4 thuộc subnet `10.20.30.0/24` truy cập database `appdb` bằng role `app_user` qua TLS và xác thực SCRAM.

Với IPv6, dùng CIDR IPv6 tương ứng. Hãy xác minh địa chỉ nguồn thật và chỉ cấp dải nhỏ nhất cần thiết. Không dùng `0.0.0.0/0` hoặc `::/0` để chữa nhanh lỗi kết nối; cách đó có thể mở quyền truy cập cho toàn bộ Internet nếu firewall cũng cho phép.

### 6.4. Kiểm tra file HBA thực tế và lỗi cú pháp

Dùng phiên quản trị đang hoạt động:

~~~sql
SHOW hba_file;
~~~

Đọc đúng file được trả về, kiểm tra rule liên quan và xác minh file có thể phân tích:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
WHERE error IS NOT NULL
ORDER BY line_number;
~~~

Nếu truy vấn trả về dòng lỗi, sửa cú pháp hoặc giá trị ở các dòng được chỉ ra. View `pg_hba_file_rules` giúp kiểm tra nội dung và lỗi phân tích của file; việc không có lỗi cú pháp không chứng minh client cụ thể đã khớp rule mong muốn. Vẫn phải đối chiếu database, user, loại kết nối, SSL và địa chỉ nguồn.

### 6.5. Nạp lại cấu hình sau khi sửa

Sau khi chỉnh `pg_hba.conf`, có thể reload cấu hình:

~~~sql
SELECT pg_reload_conf();
~~~

Kết quả `true` cho biết yêu cầu reload đã được gửi thành công; hãy kiểm tra log server để xác nhận không có lỗi khi đọc cấu hình. Có thể dùng `pg_ctl reload` hoặc lệnh reload của service tùy cách cài đặt.

HBA thường không cần restart toàn bộ PostgreSQL. Tuy nhiên, phải đọc log sau reload và thử lại từ đúng client. Nếu sửa `listen_addresses` hoặc tham số cần restart khác cùng lúc, reload riêng HBA không áp dụng các thay đổi đó.

### 6.6. Chọn phương thức xác thực phù hợp

Một số phương thức thường gặp:

| Method | Cách hoạt động và phạm vi |
|---|---|
| `scram-sha-256` | Xác thực password bằng SCRAM; lựa chọn hiện đại được khuyến nghị cho password authentication |
| `md5` | Phương thức password cũ; nên có kế hoạch chuyển sang SCRAM khi client tương thích |
| `password` | Gửi password theo giao thức PostgreSQL; chỉ nên dùng qua TLS |
| `peer` | Dùng danh tính user hệ điều hành cho kết nối local trên Unix |
| `cert` | Xác thực bằng chứng chỉ client theo cấu hình chứng chỉ và mapping |
| `trust` | Cho phép kết nối không cần xác thực password; chỉ phù hợp phạm vi local cô lập và có kiểm soát chặt |

Với ứng dụng từ xa, thường nên dùng `hostssl` kết hợp `scram-sha-256`. Không đổi sang `trust` để né lỗi password, vì mọi client khớp rule đó có thể đăng nhập mà không cần chứng minh danh tính bằng password.

Nếu chuyển từ MD5 sang SCRAM, cần bảo đảm driver và thư viện client hỗ trợ SCRAM, đặt `password_encryption` phù hợp rồi đặt lại password cho các role cần chuyển. Thay đổi `password_encryption` không tự chuyển đổi password hash đã lưu trước đó.

## 7. Kiểm tra role, password và quyền database

Khi log báo `password authentication failed for user ...`, client đã đến được PostgreSQL và server đã đi đến bước xác thực. Nguyên nhân có thể là password sai, role không đúng, secret cũ, phương thức xác thực không tương thích hoặc ứng dụng đang dùng nhầm endpoint.

### 7.1. Kiểm tra role tồn tại và có quyền LOGIN

Từ một phiên quản trị:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolvaliduntil
FROM pg_roles
WHERE rolname = 'app_user';
~~~

- Không có dòng kết quả: role không tồn tại trong cluster đang kết nối.
- `rolcanlogin = false`: role không được phép đăng nhập trực tiếp.
- `rolvaliduntil` đã qua thời điểm hiện tại: password của role đã hết hạn theo cấu hình đó.

Có thể xem thuộc tính role bằng `\du` trong psql. Nếu role cần đăng nhập và chính sách cho phép:

~~~sql
ALTER ROLE app_user LOGIN;
~~~

Chỉ cấp `LOGIN` cho role ứng dụng được thiết kế để đăng nhập. Role nhóm hoặc role chỉ chứa quyền có thể được giữ ở trạng thái không đăng nhập.

### 7.2. Đặt lại password an toàn

Nếu đã xác minh đúng cluster, role và quy trình phê duyệt thay đổi, quản trị viên có thể dùng lệnh `\password` trong psql:

~~~text
\password app_user
~~~

Lệnh này yêu cầu nhập password tương tác và tránh đặt password trực tiếp trong câu SQL dễ lưu vào history hoặc log. Không gửi password qua chat hoặc ghi password vào shell script, file cấu hình được commit hay dòng lệnh có thể bị liệt kê bởi process monitor.

Sau khi đổi secret, cập nhật secret store và khởi động lại hoặc làm mới connection pool theo cách ứng dụng sử dụng. Một số pool giữ kết nối cũ hoặc tiếp tục dùng password cũ trong các lần mở kết nối mới.

### 7.3. Kiểm tra database và quyền CONNECT

Database phải tồn tại trên đúng cluster:

~~~sql
SELECT datname
FROM pg_database
WHERE datname = 'appdb';
~~~

Nếu role xác thực thành công nhưng không được kết nối database, kiểm tra quyền:

~~~sql
SELECT
    has_database_privilege('app_user', 'appdb', 'CONNECT') AS can_connect;
~~~

Nếu chính sách cho phép cấp quyền:

~~~sql
GRANT CONNECT ON DATABASE appdb TO app_user;
~~~

Thông báo `database "appdb" does not exist` thường là sai tên database hoặc kết nối nhầm cluster. Thông báo `permission denied for database` cần xử lý quyền CONNECT. Hai trường hợp này khác với lỗi password.

### 7.4. Kiểm tra connection string và secret của ứng dụng

Đối chiếu các trường:

- Host và port có trỏ đến đúng môi trường không.
- Database và username có bị nhầm giữa staging và production không.
- Password có được cập nhật trong secret manager, biến môi trường và connection pool không.
- Ký tự đặc biệt trong password có được mã hóa đúng nếu dùng URI không.
- Driver có đọc đúng biến môi trường hoặc file cấu hình không.

Trong URI, các ký tự dành riêng như `@`, `:`, `/`, `?`, `#` và `%` cần được percent-encode khi xuất hiện trong thành phần username/password. Nếu có thể, ưu tiên cơ chế nhập secret riêng hoặc secret manager thay vì ghép password vào URL.

Không nên dùng biến môi trường `PGPASSWORD` trong môi trường nhiều người dùng vì môi trường tiến trình có thể bị lộ qua công cụ hệ thống. Với libpq, có thể dùng password file `.pgpass` hoặc `PGPASSFILE` và bảo vệ quyền truy cập. Trên Unix, file thường cần quyền `0600`; trên Windows, libpq dùng file `%APPDATA%\postgresql\pgpass.conf`.

## 8. Đọc log PostgreSQL để tìm nguyên nhân phía server

Log phía server thường cung cấp thông tin mà client không hiển thị, nhất là khi có proxy hoặc driver gói nhiều lỗi thành một thông báo.

Tùy cách triển khai, xem log bằng:

- `journalctl` hoặc log service trên Linux.
- Event Viewer và log PostgreSQL trên Windows.
- `docker logs` nếu PostgreSQL chạy trong container.
- Log database, audit hoặc connection của nhà cung cấp cloud.
- Log của Kubernetes pod và hệ thống logging tập trung.

Nếu được phép, có thể bật `log_connections` trong thời gian chẩn đoán để ghi nhận các lần kết nối và kết quả xác thực. Cần cân nhắc dung lượng log, tải và chính sách bảo mật; tắt hoặc trả lại cấu hình sau khi hoàn tất nếu đây chỉ là thay đổi tạm thời.

Đối chiếu log theo timestamp, địa chỉ client, database và role. Các dòng như sau thường giúp phân loại:

- `no pg_hba.conf entry for host ...`: kiểm tra rule HBA, IP nguồn, database, role và trạng thái SSL.
- `password authentication failed for user ...`: kiểm tra password, role, secret và auth method.
- `role ... does not exist`: kiểm tra username và cluster đích.
- `database ... does not exist`: kiểm tra tên database và endpoint.
- `too many connections`: kiểm tra số session, connection pool và giới hạn kết nối.
- Lỗi đọc chứng chỉ hoặc private key: kiểm tra đường dẫn, owner, quyền file và chuỗi chứng chỉ.
- Server restart hoặc crash đúng thời điểm lỗi: kiểm tra log hệ điều hành, container và sự kiện failover.

Không bật log password. PostgreSQL không cần ghi password rõ để chẩn đoán lỗi đăng nhập.

## 9. Chạy quy trình kiểm tra từ client đến server

Dùng cùng hostname, port, database và user như ứng dụng. Thực hiện theo thứ tự để biết chính xác lớp nào thất bại.

### Bước 1: Xác nhận cấu hình ứng dụng

Kiểm tra host, port, database, user, sslmode và nguồn secret. Đừng in password ra terminal hoặc log. Xác nhận ứng dụng đang trỏ đến đúng endpoint và môi trường.

### Bước 2: Kiểm tra DNS

Dùng `getent`, `dig` hoặc `Resolve-DnsName`. Ghi lại tất cả IP được trả về và kiểm tra hostname từ đúng container hoặc máy ứng dụng.

### Bước 3: Kiểm tra TCP

Dùng `nc -vz` hoặc `Test-NetConnection`. Nếu TCP thất bại, tập trung vào route, firewall, security group, port và listener.

### Bước 4: Kiểm tra PostgreSQL có nhận kết nối

~~~bash
pg_isready -h db.example.internal -p 5432 -d appdb -U app_user
~~~

Nếu server đang từ chối hoặc không phản hồi, đối chiếu trạng thái service và log. Nếu server nhận kết nối, tiếp tục kiểm tra TLS và xác thực.

### Bước 5: Thử đăng nhập bằng psql

~~~bash
psql "host=db.example.internal port=5432 dbname=appdb user=app_user connect_timeout=5 sslmode=verify-full sslrootcert=/etc/postgresql/certs/root-ca.crt"
~~~

Lệnh sẽ hỏi password nếu phương thức xác thực yêu cầu. Nếu client không dùng libpq hoặc không có CA ở đường dẫn trên, điều chỉnh theo driver và trust store thực tế.

### Bước 6: Đối chiếu HBA và log server

Nếu thấy `no pg_hba.conf entry`, kiểm tra địa chỉ nguồn máy chủ nhìn thấy, database, role, host/hostssl và thứ tự rule. Xác minh file bằng `pg_hba_file_rules`, reload rồi thử lại.

### Bước 7: Kiểm tra role và quyền

Nếu thấy lỗi password, xác minh role, secret, auth method và thời hạn password. Nếu xác thực thành công nhưng không vào được database, kiểm tra database tồn tại và quyền CONNECT.

### Bước 8: Kiểm tra lại ứng dụng và pool

Sau khi kết nối bằng psql thành công từ đúng môi trường, kiểm tra driver, cấu hình TLS, biến môi trường, secret cache, connection pool và thời điểm tạo kết nối của ứng dụng. Một ứng dụng có thể tiếp tục lỗi nếu process hoặc pool chưa nạp cấu hình mới.

## 10. Một số tình huống thường gặp

### Tình huống A: Kết nối local được nhưng ứng dụng từ máy khác bị timeout

Kết nối local dùng Unix socket hoặc loopback nên không đi qua firewall mạng. Kiểm tra `listen_addresses`, listener trên private IP, route, security group và firewall. Sau đó xác minh IP nguồn thực tế và rule HBA.

### Tình huống B: TCP hoạt động nhưng báo no pg_hba.conf entry

Đường TCP đã đến PostgreSQL. Xác minh IP nguồn server nhìn thấy, database, user, SSL mode và thứ tự dòng. Thêm một rule hẹp phù hợp vào file HBA thực tế, kiểm tra cú pháp, reload và đọc log.

### Tình huống C: Chỉ ứng dụng production lỗi sau khi xoay password

Có thể secret store đã đổi nhưng instance hoặc connection pool vẫn giữ password cũ. Đối chiếu version secret, username, host và thời điểm triển khai; cập nhật cấu hình rồi refresh pool theo quy trình. Không cần mở rộng HBA nếu thông báo lỗi là password authentication failed.

### Tình huống D: Kết nối bằng IP được nhưng bằng hostname báo lỗi chứng chỉ

Kiểm tra hostname trong connection string và SAN của chứng chỉ. Dùng endpoint DNS được cấp cho database hoặc cấp lại chứng chỉ với SAN phù hợp. Nếu cần kiểm tra DNS độc lập, dùng `hostaddr` trong khi giữ `host` là hostname hợp lệ để xác minh TLS.

### Tình huống E: Kết nối hoạt động khi tắt SSL

Điều này gợi ý vấn đề ở thương lượng TLS, CA, chứng chỉ hoặc cấu hình SSL. Kiểm tra `ssl` phía server, CA phía client, hạn chứng chỉ, hostname và yêu cầu `hostssl` trong HBA. Không giữ `sslmode=disable` làm giải pháp production.

### Tình huống F: Lỗi chỉ xuất hiện theo từng thời điểm

Nếu DNS trả nhiều IP, kiểm tra từng node. Nếu dùng load balancer hoặc proxy, kiểm tra health check và endpoint backend. Đối chiếu lỗi với failover, restart, cập nhật chứng chỉ, giới hạn connection, backup hoặc thay đổi firewall. Có thể một địa chỉ trong pool DNS hoặc một backend đang cấu hình khác các node còn lại.

### Tình huống G: Server báo too many connections

Đây là vấn đề giới hạn tài nguyên, khác với DNS hoặc password. Kiểm tra session:

~~~sql
SELECT
    usename,
    datname,
    state,
    count(*) AS connections
FROM pg_stat_activity
GROUP BY usename, datname, state
ORDER BY connections DESC;
~~~

Xem số kết nối của ứng dụng, số pool instance và cấu hình max pool size. Có thể dùng PgBouncer hoặc giới hạn pool để kiểm soát số backend. Không tăng `max_connections` ngay khi chưa đánh giá RAM và chi phí của mỗi backend.

## 11. Những cách xử lý dễ gây rủi ro

- Không đặt HBA thành `trust` để bỏ qua xác thực.
- Không mở `0.0.0.0/0` hoặc `::/0` chỉ để thử kết nối.
- Không tắt TLS vĩnh viễn khi gặp lỗi chứng chỉ.
- Không xóa file WAL, file dữ liệu hoặc replication slot để xử lý lỗi kết nối.
- Không restart database nhiều lần khi chưa đọc log và chưa xác định tham số nào cần restart.
- Không đổi password liên tục khi lỗi thực tế là timeout hoặc DNS.
- Không sửa một file `pg_hba.conf` phỏng đoán khi chưa kiểm tra `SHOW hba_file`.
- Không coi `pg_isready` trả về sẵn sàng là bằng chứng xác thực và quyền database đều đúng.
- Không ghi password, private key hoặc toàn bộ connection URI chứa secret vào log.

Mỗi thay đổi cần có phạm vi nhỏ, lý do rõ ràng và cách xác minh sau thay đổi. Với hệ thống production, ghi lại cấu hình trước/sau và dùng quy trình thay đổi của đội vận hành.

## 12. Checklist xử lý sự cố kết nối

- [ ] Đã lưu thông báo lỗi đầy đủ, timestamp và môi trường phát sinh.
- [ ] Đã xác nhận host, port, database, user và sslmode của ứng dụng.
- [ ] Đã kiểm tra DNS từ chính máy hoặc container chạy ứng dụng.
- [ ] Đã kiểm tra TCP đến đúng IP và port.
- [ ] Đã xác nhận PostgreSQL lắng nghe trên interface và port cần thiết.
- [ ] Đã kiểm tra route, firewall, security group, NAT và NetworkPolicy.
- [ ] Đã kiểm tra TLS, CA, SAN, thời hạn chứng chỉ và private key nếu dùng.
- [ ] Đã xác minh file HBA thực tế, địa chỉ nguồn, database, role và thứ tự rule.
- [ ] Đã kiểm tra lỗi cú pháp bằng `pg_hba_file_rules` và reload cấu hình khi cần.
- [ ] Đã kiểm tra role LOGIN, password, auth method và thời hạn password.
- [ ] Đã kiểm tra database tồn tại và quyền CONNECT.
- [ ] Đã đối chiếu log PostgreSQL với log ứng dụng.
- [ ] Đã kiểm tra connection pool và secret cache sau khi thay đổi.
- [ ] Đã xác nhận kết nối lại bằng chính môi trường và driver của ứng dụng.

## Kết luận

Lỗi kết nối PostgreSQL cần được phân loại theo lớp. DNS quyết định client tìm đến IP nào; mạng TCP và listener quyết định client có đến được tiến trình PostgreSQL hay không; TLS bảo vệ và xác minh kết nối; `pg_hba.conf` quyết định kết nối nào được phép thử xác thực; role, password và quyền database quyết định người dùng có thể mở session hay không.

Hãy kiểm tra tuần tự từ client đến server, dùng log và phép thử tại đúng môi trường ứng dụng. Khi biết lỗi nằm ở lớp nào, thay đổi nhỏ và có kiểm chứng sẽ giúp khôi phục kết nối nhanh hơn mà vẫn giữ được chính sách bảo mật của database.
