# Địa chỉ lắng nghe, cổng kết nối và giới hạn phiên trong PostgreSQL

Sau khi cài PostgreSQL, ứng dụng thường kết nối bằng một URL như `jdbc:postgresql://db.internal:5432/shopdb`. Nhưng việc có đúng tên host và mật khẩu chưa đủ để bảo đảm kết nối thành công. Máy chủ phải **lắng nghe trên giao diện mạng phù hợp**, sử dụng **đúng cổng**, chấp nhận kết nối theo **quy tắc xác thực**, và còn **suất kết nối (*connection slot*)** cho client mới.

Ví dụ, PostgreSQL có thể chạy bình thường nhưng chỉ nghe `127.0.0.1`, khiến ứng dụng ở máy khác không kết nối được. Hoặc ứng dụng có thể truy cập thành công trong vài phút, sau đó báo `too many clients already` khi nhiều pool kết nối cùng mở phiên. Hai sự cố này có triệu chứng “không kết nối được” nhưng cách xử lý hoàn toàn khác nhau.

Bài học hướng dẫn cách cấu hình và chẩn đoán ba nhóm vấn đề gắn với nhau:

1. **Địa chỉ lắng nghe:** `listen_addresses`, giao diện mạng và Unix-domain socket.
2. **Cổng kết nối:** `port`, port của server, port phía client, Docker/Kubernetes và nhiều instance trên cùng máy.
3. **Giới hạn phiên:** `max_connections`, suất dự phòng, giới hạn theo role/database, `pg_stat_activity` và connection pooling.

Các ví dụ tập trung vào PostgreSQL hiện đại, đặc biệt PostgreSQL 14–18. Một số tham số như `reserved_connections` chỉ có ở các major mới hơn; khi sử dụng, cần đối chiếu tài liệu với major của server đang chạy. Lệnh chỉnh cấu hình hoặc restart chỉ nên thực hiện trên môi trường lab hoặc theo runbook được phê duyệt.

## 1. Một kết nối PostgreSQL đi qua những lớp nào?

Hãy hình dung ứng dụng Java ở máy khác gửi yêu cầu kết nối tới PostgreSQL:

```text
                  ỨNG DỤNG / JDBC CLIENT
                            |
                 host + port + database
                            |
                            v
                 DNS / route / firewall
                            |
                            v
                   PostgreSQL server
               listen_addresses + port
                            |
                            v
                  pg_hba.conf + TLS
                            |
                            v
                   Xác thực user
                            |
                            v
             connection slot / role / database
                            |
                            v
                  Phiên SQL được tạo
                            |
                     SELECT / INSERT ...
```

Các lớp khác nhau trả lời những câu hỏi khác nhau:

| Lớp | Câu hỏi | Điểm cấu hình hoặc công cụ |
| --- | --- | --- |
| Mạng | Client đi được tới máy chủ không? | DNS, route, firewall, security group, NetworkPolicy. |
| Listener | PostgreSQL có nghe đúng địa chỉ/cổng đó không? | `listen_addresses`, `port`, `ss`, `Get-NetTCPConnection`. |
| Xác thực | Host, database và role này được phép đăng nhập bằng phương thức nào? | `pg_hba.conf`, user/password, TLS. |
| Suất phiên | Máy chủ hoặc role/database có còn cho phép phiên mới không? | `max_connections`, reserved slots, connection limits. |
| Quyền SQL | Phiên đã đăng nhập có đọc/sửa được đối tượng không? | `GRANT`, `REVOKE`, quyền schema/bảng. |

**Có thể ping tới máy chủ** không có nghĩa cổng PostgreSQL mở. **Cổng mở** không có nghĩa PostgreSQL chấp nhận user. **Đăng nhập thành công** không đồng nghĩa user có quyền đọc bảng. Và **role có quyền hợp lệ** cũng chưa chắc tạo thêm phiên được khi hết connection slots.

## 2. Xác nhận đúng server trước khi sửa cấu hình

Trong một kết nối SQL đã hoạt động, trước hết kiểm tra:

```sql
SELECT
    current_database() AS database_name,
    current_user AS database_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version,
    pg_postmaster_start_time() AS server_started_at;
```

Tiếp tục:

```sql
SHOW config_file;
SHOW data_directory;
SHOW hba_file;
```

Điều này giúp nhận ra sai sót phổ biến: người quản trị sửa `postgresql.conf` của instance A nhưng ứng dụng thật đang dùng instance B. Một máy có thể chạy nhiều PostgreSQL clusters với những data directory và port khác nhau.

Lưu ý:

- `inet_server_addr()` cho biết địa chỉ local mà kết nối TCP hiện tại đang tới. Với Unix-domain socket, kết quả có thể là `NULL`.
- `inet_server_port()` là **port phía server** của kết nối TCP, không phải cổng ngẫu nhiên phía client.
- Nếu kết nối qua load balancer, proxy hoặc port forwarding, cần đối chiếu thêm endpoint ứng dụng đang dùng; một phần đường đi mạng có thể không hiển thị qua các hàm SQL.
- `SHOW config_file` và `SHOW data_directory` có thể yêu cầu quyền đọc thông số tương ứng. Không nâng account ứng dụng thành superuser chỉ để chẩn đoán.

Một bộ lệnh gọn:

```sql
SHOW server_version;
SHOW listen_addresses;
SHOW port;
SHOW max_connections;
SHOW unix_socket_directories;
```

Trong `psql` còn có lệnh:

```text
\conninfo
```

để xem chính client đã kết nối tới host/socket, port và database nào.

## 3. listen_addresses: PostgreSQL lắng nghe ở địa chỉ nào?

Thông số `listen_addresses` quyết định **những địa chỉ IP/interface mà tiến trình PostgreSQL cố gắng tạo TCP listening sockets** khi khởi động.

Ví dụ trong `postgresql.conf`:

```conf
listen_addresses = 'localhost'
port = 5432
```

Giá trị mặc định thường là `localhost`. Với cấu hình này, PostgreSQL thường chỉ chấp nhận các kết nối TCP từ chính máy chủ qua loopback, chẳng hạn `127.0.0.1` và `::1` theo khả năng phân giải tên/IPv6 của hệ thống. Một client ở máy khác không thể kết nối trực tiếp tới PostgreSQL thông qua địa chỉ mạng công khai/nội bộ của server chỉ nhờ biết mật khẩu.

### 3.1. Các giá trị thường dùng

| Giá trị cấu hình | Ý nghĩa | Khi cân nhắc sử dụng |
| --- | --- | --- |
| `'localhost'` | Nghe qua các địa chỉ loopback phù hợp trên máy. | Máy phát triển, kết nối nội bộ cùng host. |
| `'127.0.0.1'` | Nghe trên IPv4 loopback. | Khi chỉ muốn kết nối TCP IPv4 cục bộ. |
| `'::1'` | Nghe trên IPv6 loopback. | Khi chỉ muốn kết nối TCP IPv6 cục bộ. |
| `'10.20.30.11'` | Nghe trên IP cụ thể phải tồn tại và dùng được trên máy chủ. | Service ở mạng nội bộ có IP đã biết. |
| `'localhost,10.20.30.11'` | Danh sách nhiều địa chỉ lắng nghe. | Vừa phục vụ kết nối local, vừa phục vụ mạng nội bộ. |
| `'*'` | Cố gắng nghe trên mọi interface IP khả dụng. | Chỉ khi tầng mạng, firewall, xác thực và TLS được kiểm soát chặt. |
| `''` | Không mở TCP listening sockets. | Môi trường chỉ cần Unix-domain sockets, nếu nền tảng hỗ trợ. |

Ví dụ cấu hình cho một server nằm trong mạng riêng:

```conf
# Ví dụ: địa chỉ phải thực sự thuộc máy chủ PostgreSQL.
listen_addresses = 'localhost,10.20.30.11'
port = 5432
```

**Không đặt một dải CIDR như `'10.20.30.0/24'` trong `listen_addresses`.** Đây là danh sách địa chỉ/hostname hoặc ký hiệu `*` mà server sẽ bind, không phải danh sách các mạng client được cấp phép. Dải IP của client thuộc lớp firewall hoặc quy tắc `pg_hba.conf`.

### 3.2. Wildcard không đồng nghĩa được phép truy cập

`listen_addresses = '*'` cho phép PostgreSQL nghe ở nhiều interface hơn, nhưng **không tự cấp phép đăng nhập**. Client từ xa còn phải vượt qua đường mạng, firewall, `pg_hba.conf` và xác thực PostgreSQL.

Tuy nhiên, dùng wildcard vẫn tăng phạm vi có thể tiếp cận đến cổng PostgreSQL. Trên hệ thống thật:

- Chỉ mở interface thật sự cần phục vụ.
- Giới hạn nguồn truy cập bằng firewall/security group/NetworkPolicy.
- Dùng `pg_hba.conf` và xác thực mạnh cho từng nhóm kết nối.
- Sử dụng TLS khi luồng kết nối yêu cầu bảo vệ trên mạng.
- Không trực tiếp mở PostgreSQL ra Internet công cộng nếu không có thiết kế bảo mật phù hợp.

**Một cấu hình quá rộng không trở nên an toàn chỉ vì hiện tại mật khẩu đủ mạnh.** Đây là vấn đề giảm bề mặt tấn công theo nhiều lớp.

### 3.3. IPv4 và IPv6

`127.0.0.1` là loopback IPv4; `::1` là loopback IPv6. Kết nối tới `localhost` có thể thử IPv6 trước hoặc IPv4 trước tùy DNS/OS và thư viện client.

Vì vậy có thể xảy ra:

```text
psql -h 127.0.0.1 ...  -> thành công
psql -h ::1 ...        -> thất bại
psql -h localhost ...  -> kết quả phụ thuộc cách client phân giải/kết nối
```

Nếu ứng dụng bị lỗi chỉ ở một cách gọi host, hãy kiểm tra cả địa chỉ PostgreSQL thực sự lắng nghe, luật HBA tương ứng IPv4/IPv6 và kết quả DNS. Đừng mặc định `localhost` luôn tương đương hoàn toàn với `127.0.0.1`.

## 4. Kết nối TCP và Unix-domain socket

PostgreSQL có thể nhận kết nối qua:

1. **TCP/IP:** dùng host/IP và port; có thể đi qua mạng.
2. **Unix-domain socket:** một tệp socket trong hệ thống tệp trên cùng máy, chủ yếu trên hệ Unix/Linux.

Trong nhiều môi trường Linux, khi không chỉ định `-h` và không có biến môi trường ghi đè, `psql` ưu tiên kết nối qua Unix-domain socket:

```bash
# Không ghi -h: thường dùng Unix-domain socket trên Linux.
psql -U app_user -d appdb

# Chỉ định IPv4: dùng TCP.
psql -h 127.0.0.1 -p 5432 -U app_user -d appdb
```

Hai lệnh có thể gặp **quy tắc `pg_hba.conf` khác nhau**: một lệnh khớp mục `local` cho Unix socket, lệnh kia khớp mục `host`/`hostssl` cho TCP.

### 4.1. unix_socket_directories

Kiểm tra:

```sql
SHOW unix_socket_directories;
```

Trong hệ Unix, tham số này cho biết những thư mục PostgreSQL tạo Unix-domain sockets. Socket thường có tên gắn với số port, ví dụ:

```text
/var/run/postgresql/.s.PGSQL.5432
```

Đường dẫn trên chỉ là ví dụ. Tên thư mục phụ thuộc bản cài; trong một số môi trường là `/tmp` hoặc một thư mục riêng cho PostgreSQL.

Nếu `listen_addresses = ''`, máy chủ có thể vẫn phục vụ qua Unix-domain socket khi được cấu hình phù hợp. Vì vậy **“không lắng nghe TCP” không đồng nghĩa “server không nhận kết nối nào”**.

Khi client và server nằm trong hai container khác nhau, Unix socket của container server không tự xuất hiện trong container client. Muốn dùng socket giữa các container phải có cơ chế chia sẻ đường dẫn phù hợp; nếu không, kết nối TCP qua mạng container thường đơn giản hơn.

### 4.2. Unix socket có port không?

Các socket PostgreSQL thường có phần tên `.s.PGSQL.<port>`, nhưng đó không phải một cổng TCP đang mở ra mạng. Tham số `port` vẫn tham gia đặt tên socket, trong khi kết nối local sử dụng đường dẫn filesystem.

Sự phân biệt này hữu ích khi `pg_isready` báo server sẵn sàng qua socket nhưng ứng dụng truy cập địa chỉ TCP lại gặp `connection refused`.

## 5. port: cổng PostgreSQL dùng để lắng nghe

Thông số `port` là cổng TCP mà PostgreSQL sử dụng khi nhận kết nối. Giá trị thường gặp là `5432`.

```sql
SHOW port;
```

Ví dụ trong `postgresql.conf`:

```conf
port = 5432
```

Lưu ý:

- **Server port** là cổng PostgreSQL lắng nghe, ví dụ `5432`.
- **Client source port** thường là một cổng tạm do hệ điều hành client cấp phát; không cần trùng `5432`.
- **Port ở phía ngoài proxy/container** có thể khác port bên trong PostgreSQL.
- Cổng TCP phải được cho phép trong firewall hoặc security group trên đường kết nối.

Ví dụ:

```text
App client: 10.20.30.50:49152
                      |
                      | TCP
                      v
DB server:  10.20.30.11:5432
```

Đổi `port` không tự đổi URL JDBC hoặc cấu hình của tất cả client. Sau khi đổi cổng server, phải cập nhật endpoint ứng dụng, health checks, firewall, monitoring và những công cụ phụ thuộc.

### 5.1. Nhiều PostgreSQL instance trên một máy

Một host có thể chứa PostgreSQL 15 và PostgreSQL 16 đồng thời, nhưng hai tiến trình không thể cùng chiếm đúng cùng một địa chỉ và cổng TCP mà không có cách bố trí riêng.

Ví dụ:

```text
Instance A:
  data_directory = /srv/pg15/data
  listen_addresses = '127.0.0.1'
  port = 5432

Instance B:
  data_directory = /srv/pg16/data
  listen_addresses = '127.0.0.1'
  port = 5433
```

Ở đây, mỗi instance có data directory khác nhau và port khác nhau. Các giá trị chỉ mang tính minh họa. Cần bảo đảm **đúng binary/major cho data directory**, quyền tệp riêng và tránh trùng địa chỉ/socket khi khởi động.

### 5.2. Lỗi port đã được sử dụng

Khi cổng đã bị tiến trình khác chiếm, log có thể chứa:

```text
LOG:  could not bind IPv4 address "...": Address already in use
HINT: Is another postmaster already running on port 5432?
```

Trên Linux:

```bash
ss -lntp
```

Trên Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen
```

Hãy xác định tiến trình và instance sở hữu cổng trước khi quyết định đổi port hoặc dừng service. Không kết thúc một process chỉ vì nó dùng `5432` khi chưa biết đó có phải PostgreSQL production hay không.

## 6. listen_addresses và port cần restart, không chỉ reload

`listen_addresses` và `port` là các tham số được xác định khi tiến trình PostgreSQL khởi động. Thay đổi chúng trong cấu hình **không có hiệu lực chỉ bằng reload**.

Ví dụ:

```conf
listen_addresses = 'localhost,10.20.30.11'
port = 5433
```

Nếu chỉ thực hiện:

```sql
SELECT pg_reload_conf();
```

PostgreSQL có thể ghi nhận rằng những giá trị này cần **restart**, nhưng vẫn tiếp tục lắng nghe theo giá trị cũ trong tiến trình hiện tại.

### 6.1. Kiểm tra pending_restart

```sql
SELECT
    name,
    setting,
    context,
    source,
    sourcefile,
    pending_restart
FROM pg_settings
WHERE name IN ('listen_addresses', 'port', 'max_connections')
ORDER BY name;
```

Những tham số trên thường có `context = 'postmaster'`. Nếu sau một lần nạp lại file cấu hình `pending_restart = true`, server đã phát hiện thay đổi cần restart.

**`pg_reload_conf() = true` chỉ cho biết yêu cầu reload được gửi thành công**, không chứng minh listener đã đổi sang port/IP mới.

Trên server thực, việc restart cần thực hiện qua công cụ quản lý phù hợp (systemd, Windows Service, container orchestrator hoặc nhà cung cấp managed database), trong cửa sổ vận hành đã được phê duyệt. Restart ngắt kết nối hiện có, làm gián đoạn các transaction đang mở.

### 6.2. Cấu hình có nhiều nguồn

Giá trị hiện hành có thể đến từ `postgresql.conf`, `include`, `postgresql.auto.conf` do `ALTER SYSTEM` quản lý hoặc tham số dòng lệnh. Vì vậy không nên chỉ mở một file rồi kết luận đó là giá trị server đang dùng.

```sql
SHOW config_file;

SELECT
    name, setting, source, sourcefile,
    sourceline, pending_restart
FROM pg_settings
WHERE name IN ('listen_addresses', 'port', 'max_connections');
```

Thông tin `sourcefile`/`sourceline` có thể bị ẩn với tài khoản thiếu quyền phù hợp. Khi cần hỗ trợ quản trị, dùng role có quyền quan sát thiết lập theo chính sách thay vì cấp superuser cho ứng dụng.

## 7. Mở listener không đồng nghĩa cho phép đăng nhập: pg_hba.conf

Một cấu hình mạng đầy đủ cần phối hợp:

```text
listen_addresses = nghe ở đâu?
port             = nghe ở cổng nào?
firewall         = host nào đến được cổng?
pg_hba.conf      = kết nối nào được chấp nhận/xác thực ra sao?
user/password    = người dùng chứng minh danh tính bằng gì?
GRANT CONNECT    = role được vào database đích không?
```

Ví dụ PostgreSQL nghe trên IP nội bộ `10.20.30.11`, còn ứng dụng nằm trong mạng `10.20.30.0/24`:

```conf
# postgresql.conf
listen_addresses = 'localhost,10.20.30.11'
port = 5432
```

Một dòng xác thực tương ứng có thể là:

```conf
# pg_hba.conf
# TYPE  DATABASE  USER      ADDRESS          METHOD
host    appdb     app_user  10.20.30.0/24    scram-sha-256
```

Dòng này chỉ định PostgreSQL chấp nhận kiểu kết nối TCP phù hợp với database, user và mạng client được nêu **khi xác thực thành công**. Cần thêm cấu hình mạng và role/database thực tế; ví dụ không thay thế việc thiết kế TLS và firewall.

### 7.1. Quy tắc đầu tiên khớp quyết định cách xác thực

`pg_hba.conf` được xét **theo thứ tự dòng**; quy tắc khớp đầu tiên được dùng. PostgreSQL không tiếp tục thử các quy tắc sau chỉ vì xác thực theo dòng đầu tiên thất bại.

Ví dụ hai dòng:

```conf
host  appdb  app_user  10.20.30.0/24  scram-sha-256
host  all    all       0.0.0.0/0      reject
```

Client `app_user` từ mạng được phép khớp dòng đầu. Những kết nối không khớp một dòng cho phép trước đó có thể bị từ chối theo dòng sau. Tuy nhiên, quy tắc quá rộng như `0.0.0.0/0` nên được dùng cẩn trọng; các thiết lập IPv6 cũng cần xét riêng.

**Không dùng `trust` cho mạng rộng** để sửa nhanh lỗi mật khẩu. `trust` cho phép client đủ điều kiện khớp quy tắc đăng nhập mà không cần kiểm tra mật khẩu, gây rủi ro nếu áp dụng sai phạm vi.

### 7.2. local, host và hostssl

| Loại HBA | Áp dụng cho |
| --- | --- |
| `local` | Kết nối qua Unix-domain socket. |
| `host` | Kết nối TCP; có thể bao gồm kết nối có hoặc không có TLS tùy cấu hình. |
| `hostssl` | Kết nối TCP sử dụng SSL/TLS. |
| `hostnossl` | Kết nối TCP không sử dụng SSL/TLS. |

Ví dụ:

```conf
# Unix socket cho quản trị nội bộ, phương thức phải đúng mô hình OS user.
local    postgres    postgres                      peer

# TCP có TLS cho ứng dụng từ mạng cụ thể.
hostssl  appdb       app_user   10.20.30.0/24      scram-sha-256
```

Đây là cấu hình minh họa trên hệ Unix; phương thức `peer` chỉ phù hợp trong những điều kiện kết nối Unix-domain socket được hỗ trợ. Để `hostssl` hoạt động, PostgreSQL phải được cấu hình TLS thích hợp và có chứng chỉ/khóa hợp lệ.

### 7.3. Kiểm tra HBA trước khi kết luận lỗi listener

```sql
SHOW hba_file;

SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
```

View `pg_hba_file_rules` giúp phát hiện một số lỗi khi phân tích file HBA và thấy quy tắc theo thứ tự. Quyền truy cập thông tin có thể bị giới hạn. Cần xem thêm log và thử kết nối từ **đúng địa chỉ nguồn** của ứng dụng.

Thay đổi `pg_hba.conf` thông thường có thể được nạp lại mà không cần restart toàn server, với lưu ý cơ chế áp dụng trên từng nền tảng có thể khác. Trái lại, thay đổi `listen_addresses`/`port` vẫn cần restart.

### 7.4. GRANT CONNECT trên database

Ngay cả sau khi xác thực thành công, quyền `CONNECT` ở database đích vẫn là một phần kiểm soát truy cập.

```sql
-- Chỉ minh họa cho môi trường được phép quản lý quyền.
GRANT CONNECT ON DATABASE appdb TO app_user;
```

PostgreSQL thường cấp quyền `CONNECT` mặc định cho `PUBLIC` trên database mới. Vì vậy `GRANT CONNECT` riêng có thể không thay đổi quyền hiệu lực nếu role đã nhận quyền qua `PUBLIC`.

Nếu cần giới hạn nghiêm ngặt một database cho các role xác định, quản trị viên có thể đánh giá việc thu hồi quyền mặc định:

```sql
-- CẢNH BÁO: ảnh hưởng nhiều tài khoản; chỉ dùng sau khi kiểm kê phụ thuộc.
REVOKE CONNECT ON DATABASE appdb FROM PUBLIC;
GRANT CONNECT ON DATABASE appdb TO app_user;
```

Không thực hiện tùy tiện trên production vì có thể làm mất quyền truy cập của các công cụ monitoring, migration, backup hoặc ứng dụng khác.

## 8. Thử kết nối chủ động từ client

Một câu lệnh `psql` với host và port ghi rõ:

```bash
psql -X -h 10.20.30.11 -p 5432 -U app_user -d appdb
```

Ý nghĩa:

- `-X`: tránh đọc file khởi tạo `psqlrc` trong phiên chẩn đoán.
- `-h`: địa chỉ kết nối; trong ví dụ là IP máy chủ PostgreSQL.
- `-p`: cổng server.
- `-U`: database role.
- `-d`: database đích.

Sau khi đăng nhập:

```sql
SELECT
    current_database(),
    current_user,
    inet_server_addr(),
    inet_server_port(),
    pg_backend_pid();
```

Nếu không muốn vào interactive shell:

```bash
psql -X -h 10.20.30.11 -p 5432 -U app_user -d appdb \
  -c "SELECT current_database(), current_user, pg_backend_pid();"
```

Dấu `\` nối dòng là cú pháp minh họa cho shell kiểu Unix; PowerShell và CMD có cú pháp xuống dòng khác. Không ghi mật khẩu trong command line hoặc URL được ghi vào log; dùng cơ chế quản lý secret phù hợp.

### 8.1. pg_isready chỉ xác nhận mức sẵn sàng của endpoint

```bash
pg_isready -h 10.20.30.11 -p 5432
```

Ví dụ kết quả:

```text
10.20.30.11:5432 - accepting connections
```

`pg_isready` giúp phân biệt endpoint đang phản hồi và nhận kết nối, đang từ chối tạm thời hay không trả lời. **Nó không chứng minh tài khoản/password/database của ứng dụng đúng.** Vì vậy, cần thử tiếp bằng chính account và database mà ứng dụng dùng.

Các mã thoát thường gặp là `0` (đang nhận kết nối), `1` (server trả lời nhưng từ chối), `2` (không có phản hồi) và `3` (tham số không hợp lệ/không thể thử).

## 9. max_connections: giới hạn số phiên client đồng thời

Trong mô hình PostgreSQL truyền thống, mỗi kết nối client thường có một backend process được server quản lý. Kết nối này chiếm tài nguyên: bộ nhớ, cấu trúc quản lý giao dịch, file descriptors và chi phí điều phối.

Thông số `max_connections` kiểm soát **số kết nối đồng thời tối đa theo cấu hình server**, trong khi một phần slot được dành riêng cho các loại tài khoản có đặc quyền.

```sql
SHOW max_connections;
```

Giá trị mặc định thường là `100`, nhưng giá trị thực có thể được thay đổi bởi nhà quản trị hoặc nhà cung cấp dịch vụ.

Ví dụ:

```conf
max_connections = 150
```

Con số 150 không có nghĩa server sẽ chạy nhanh với 150 truy vấn nặng đồng thời. Nó là một **giới hạn cho việc tạo phiên**, không phải giới hạn độ đồng thời tối ưu của CPU, số truy vấn chạy mỗi giây hay thông lượng transaction.

### 9.1. Vì sao không nên tăng thật lớn để tránh lỗi?

Mỗi kết nối có thể giữ state riêng; số kết nối nhiều làm tăng overhead của PostgreSQL và ứng dụng. Nếu hàng trăm kết nối đều thực thi truy vấn cùng lúc:

- CPU phải chuyển đổi giữa nhiều backend.
- Bộ nhớ dành cho thao tác sắp xếp/hash ở nhiều truy vấn có thể tăng mạnh.
- Tranh chấp khóa và hàng đợi I/O có thể tăng.
- Memory footprint, thời gian phản hồi và độ ổn định có thể tệ hơn.

Vì vậy, khi nhận lỗi hết slot, giải pháp có thể là **giảm số pool connections, phát hiện rò rỉ kết nối hoặc dùng pooler**, không chỉ sửa `max_connections = 2000`.

### 9.2. max_connections cần restart

`max_connections` thuộc nhóm tham số `postmaster`; cập nhật cấu hình rồi chỉ gọi `pg_reload_conf()` **không đủ để tăng số slot đang có hiệu lực**.

```sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name = 'max_connections';
```

Sau thay đổi và reload, `pending_restart` có thể là `true`. Phải khởi động lại instance theo quy trình để áp dụng cấu hình.

Trên một topology có standby, thay đổi `max_connections` còn có thể liên quan các yêu cầu tương thích tham số trên standby. Cần kiểm tra tài liệu đúng major và runbook replication/HA trước khi thay đổi.

## 10. Suất kết nối dự phòng cho quản trị và vận hành

Nếu mọi connection slot đều bị ứng dụng chiếm, quản trị viên có thể không còn đường đăng nhập để chẩn đoán. PostgreSQL có cơ chế dành một số slot cho kết nối đặc biệt.

### 10.1. superuser_reserved_connections

```sql
SHOW superuser_reserved_connections;
```

Trong nhiều bản PostgreSQL, giá trị mặc định là `3`. Khi số slot còn lại chạm ngưỡng dự phòng, các kết nối thông thường không được nhận thêm để bảo vệ khả năng đăng nhập của superuser.

Ví dụ minh họa:

```text
max_connections = 100
superuser_reserved_connections = 3

97 slot:  thường có thể dùng bởi kết nối không phải superuser
 3 slot:  giữ lại để hỗ trợ kết nối đặc quyền superuser
```

Đây là **mô hình phân bổ khái niệm**. Các điều kiện cấp slot thực tế còn tùy phiên bản, nhóm kết nối và trạng thái server; không coi tổng số 100 là “100 suất dành toàn bộ cho pool của ứng dụng”.

### 10.2. reserved_connections từ PostgreSQL 16

PostgreSQL 16 bổ sung cấu hình `reserved_connections` cùng vai trò hệ thống `pg_use_reserved_connections` để quản lý một nhóm slot dự phòng cho các role được cấp đặc quyền phù hợp, bên cạnh phần dành riêng cho superuser.

Trên server hỗ trợ:

```sql
SHOW reserved_connections;
SHOW superuser_reserved_connections;
SHOW max_connections;
```

Với PostgreSQL 14 hoặc 15, `SHOW reserved_connections` sẽ không hoạt động vì tham số này chưa có; không nên sao chép lệnh từ manual major mới rồi kết luận máy chủ cũ bị cấu hình sai.

Ví dụ phân bổ giả định trên PostgreSQL hỗ trợ:

```text
max_connections               = 100
reserved_connections          =   5
superuser_reserved_connections=   3
---------------------------------------
Slot phổ thông tối đa theo mô hình       92
Slot dự phòng cho role được phép          5
Slot cuối cho superuser                   3
```

Khi số slot tự do xuống thấp, những role thuộc nhóm có thể dùng slot dự phòng có thể vẫn đăng nhập theo chính sách, trong khi kết nối thường bị từ chối. Khi xuống thấp hơn nữa, phần slot cuối dành cho superuser.

Nếu cần cấp khả năng dùng nhóm slot dự phòng trên server hỗ trợ:

```sql
-- Chỉ ví dụ với role vận hành đã tồn tại và được phê duyệt.
GRANT pg_use_reserved_connections TO ops_operator;
```

Đây là **quyền đặc biệt**, không phải quyền cần cấp cho mọi worker ứng dụng. Nếu để application pool chiếm luôn slot dự phòng, mục đích khôi phục khi quá tải sẽ bị phá vỡ.

### 10.3. Connection slots và bảo mật

Các slot dự phòng chỉ bảo vệ một phần năng lực kết nối cho công tác điều hành. Chúng không giải quyết:

- Query bị khóa hàng giờ.
- Tất cả CPU và RAM đã kiệt.
- Disk đã đầy, WAL không ghi được.
- Hệ thống mạng hoặc proxy gặp lỗi.

Khi các tài nguyên khác đã quá tải, quản trị viên có thể đăng nhập được nhưng vẫn gặp thao tác rất chậm. Vì vậy, dự phòng kết nối là một lớp trong chiến lược vận hành, không phải bảo đảm tuyệt đối cho mọi sự cố.

## 11. Giới hạn kết nối theo role và theo database

`max_connections` là mức cấu hình toàn server. Có trường hợp cần giới hạn một tài khoản hoặc một database để một service không chiếm hết slot.

### 11.1. Giới hạn cho một role

Giả sử role đăng nhập `app_service` đã được tạo:

```sql
ALTER ROLE app_service CONNECTION LIMIT 20;
```

Khi đó PostgreSQL kiểm tra giới hạn số phiên thông thường của role theo cơ chế áp dụng; mở kết nối mới vượt giới hạn có thể bị từ chối. Không phải mọi loại connection, đặc biệt các phiên đặc quyền superuser, đều bị áp dụng như kết nối thường.

Để bỏ giới hạn riêng:

```sql
ALTER ROLE app_service CONNECTION LIMIT -1;
```

Giá trị `-1` nghĩa là **không đặt một giới hạn riêng ở cấp role**, không phải vô hiệu hóa `max_connections` toàn máy chủ.

### 11.2. Giới hạn cho một database

```sql
ALTER DATABASE appdb CONNECTION LIMIT 60;
```

Giới hạn này liên quan đến tổng số kết nối vào database `appdb` theo những điều kiện áp dụng của PostgreSQL, bất kể có nhiều application roles cùng kết nối.

Để bỏ giới hạn riêng:

```sql
ALTER DATABASE appdb CONNECTION LIMIT -1;
```

Đây là hai loại giới hạn riêng biệt:

| Mức giới hạn | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Server | `max_connections = 100` | Tổng ngân sách kết nối do server quản lý. |
| Role | `app_service CONNECTION LIMIT 20` | Hạn mức phiên cho một role đăng nhập theo quy tắc áp dụng. |
| Database | `appdb CONNECTION LIMIT 60` | Hạn mức phiên đến một database theo quy tắc áp dụng. |

Ví dụ: server còn slot nhưng `app_service` đã chạm hạn mức 20 thì ứng dụng vẫn có thể nhận lỗi kết nối. Tăng `max_connections` không tự giải quyết giới hạn role nếu đó mới là nguồn lỗi.

### 11.3. Đọc giới hạn hiện hành

Quản trị viên có thể truy vấn catalog:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolconnlimit
FROM pg_roles
WHERE rolname IN ('app_service', 'report_reader', 'ops_operator')
ORDER BY rolname;

SELECT
    datname,
    datconnlimit
FROM pg_database
WHERE datname IN ('appdb', 'postgres')
ORDER BY datname;
```

Giá trị `-1` là không giới hạn riêng. Các giới hạn role/database có đặc tính kiểm tra khi tạo kết nối và có ngoại lệ nhất định; không xem chúng như một **bộ phân xử cứng chính xác từng mili-giây** trong mọi đợt login đồng thời.

Thay đổi giới hạn không tự động chấm dứt các session đã tồn tại. Nếu một database hiện có nhiều phiên hơn hạn mức mới, cần quản lý các kết nối hiện tại và quan sát tác động với những lần kết nối tiếp theo.

## 12. Xem số phiên đang tồn tại bằng pg_stat_activity

`pg_stat_activity` là view quan trọng khi điều tra PostgreSQL hết connection slots, quá nhiều session idle hoặc truy vấn đang chạy.

### 12.1. Đếm các client backend

```sql
SELECT count(*) AS client_sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend';
```

Các hàng khác trong `pg_stat_activity` có thể đại diện tiến trình nền hoặc worker khác, không nhất thiết là một phiên JDBC của người dùng. Vì vậy, đếm tất cả hàng rồi so trực tiếp với `max_connections` có thể gây nhầm lẫn.

Nhóm theo database, user và trạng thái:

```sql
SELECT
    datname,
    usename,
    state,
    count(*) AS session_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, state
ORDER BY session_count DESC, datname, usename, state;
```

Ví dụ dạng kết quả:

| datname | usename | state | session_count |
| --- | --- | --- | ---: |
| appdb | app_service | idle | 42 |
| appdb | app_service | active | 8 |
| appdb | report_reader | idle | 3 |
| postgres | ops_operator | active | 1 |

Từ ví dụ trên, `app_service` có 50 session client, nhưng chỉ 8 đang `active` ở thời điểm lấy mẫu. Điều này có thể phản ánh một connection pool giữ nhiều session chờ tái sử dụng, không nhất thiết là 50 truy vấn đang chạy đồng thời.

### 12.2. Phân biệt idle và idle in transaction

Một số trạng thái thường gặp:

| `state` | Ý nghĩa |
| --- | --- |
| `active` | Backend đang thực thi một query. |
| `idle` | Session đang kết nối nhưng không thực thi query ở thời điểm lấy mẫu. |
| `idle in transaction` | Transaction đang mở nhưng client không gửi query mới tại thời điểm quan sát. |
| `idle in transaction (aborted)` | Transaction đã rơi vào trạng thái lỗi nhưng chưa được rollback/kết thúc. |

`idle` không nhất thiết là lỗi: pool cần giữ một số kết nối rảnh để giảm chi phí thiết lập kết nối. Ngược lại, `idle in transaction` kéo dài có thể giữ khóa, giữ snapshot cũ, cản trở VACUUM dọn tuple cũ hoặc làm tài nguyên bị giữ lâu hơn cần thiết.

Tìm các session có transaction mở:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

View có thể che một số nội dung chi tiết của session khác nếu role thiếu quyền giám sát. Đối với monitoring được phê duyệt, PostgreSQL có các role như `pg_monitor` hoặc `pg_read_all_stats` để hỗ trợ quan sát mà không phải cấp superuser một cách tùy tiện.

### 12.3. Số phiên theo database

```sql
SELECT
    datname,
    numbackends
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY numbackends DESC;
```

`numbackends` cho biết số backend hiện kết nối với database tương ứng theo view thống kê. Nó hữu ích để nhanh chóng nhận biết database nào đang chiếm nhiều kết nối, nhưng vẫn cần xem `pg_stat_activity` để hiểu role, ứng dụng và trạng thái.

### 12.4. Xem nguồn kết nối

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    client_port,
    backend_start,
    state
FROM pg_stat_activity
WHERE backend_type = 'client backend'
ORDER BY backend_start DESC;
```

`client_addr` và `client_port` giúp truy nguồn kết nối TCP. Với Unix socket, một số trường có thể là `NULL`; địa chỉ phía client sau proxy hoặc pooler cũng có thể phản ánh **proxy/pooler** thay vì máy ứng dụng cuối cùng.

Việc đặt `application_name` có ý nghĩa lớn cho vận hành: thay vì tất cả session đều hiện tên mặc định, có thể phân biệt `checkout-api`, `inventory-worker`, `migration-job` và `reporting`.

## 13. Ước tính ngân sách kết nối cho nhiều ứng dụng

Một nguyên nhân phổ biến của `too many clients` là cộng số kết nối của **toàn bộ replicas** không khớp ngân sách server.

Giả sử:

```text
PostgreSQL:
  max_connections = 100

Checkout API:
  3 replicas * maximumPoolSize 20 = 60 kết nối tiềm năng

Inventory Worker:
  2 replicas * maximumPoolSize 10 = 20 kết nối tiềm năng

Reporting / maintenance:
  có thể dùng thêm 5 kết nối

Tổng đỉnh lý thuyết phần client kể trên = 60 + 20 + 5 = 85
```

Con số 85 chưa tính các công cụ khác kết nối cùng server, những đợt rollout có **hai phiên bản pod chạy chồng nhau**, connection pool mở đột biến, quản trị viên, monitoring, hoặc các điều kiện dự phòng. Nếu tất cả replica cùng tăng pool size từ 20 lên 30, chỉ riêng Checkout API đã có thể mở `3 * 30 = 90` kết nối.

Vì vậy:

\[
\text{Kết nối đỉnh dự kiến} =
\sum_i (\text{số replica}_i \times \text{pool tối đa}_i)
+ \text{các phiên trực tiếp khác}
\]

Để chọn cấu hình an toàn, kết nối đỉnh dự kiến cần **nằm dưới ngân sách client thực sự khả dụng**, sau khi xét slot dự phòng và biến động vận hành.

### 13.1. Pool size không bằng số request đồng thời

Ví dụ 200 HTTP requests đang xử lý không nhất thiết cần 200 PostgreSQL connections:

- Một request có thể đang xác thực, chờ mạng, đọc cache hoặc xử lý logic Java.
- Mỗi request chỉ giữ connection trong phần thời gian cần truy vấn database.
- Pool giới hạn số kết nối DB và cho các request còn lại chờ mượn connection.

Pool quá nhỏ có thể khiến ứng dụng chờ lâu; pool quá lớn có thể làm database quá tải. Phải đo **thời gian sử dụng connection**, SQL latency, số query đồng thời, chờ lock và tài nguyên máy chủ, không chọn pool size chỉ theo số luồng HTTP.

### 13.2. Ví dụ cấu hình HikariCP trong ứng dụng Java

```properties
# Ví dụ Spring Boot / HikariCP, không phải giá trị tối ưu cho mọi workload.
spring.datasource.url=jdbc:postgresql://db.internal.example.test:5432/appdb
spring.datasource.username=app_service
spring.datasource.hikari.maximum-pool-size=15
spring.datasource.hikari.minimum-idle=3
spring.datasource.hikari.connection-timeout=30000
```

`maximum-pool-size` giới hạn số connection mà **một pool instance** có thể giữ; nếu ứng dụng chạy sáu pod, ngân sách không phải 15 mà có thể tới `6 * 15 = 90` cho riêng service ấy.

`connection-timeout` ở HikariCP là thời gian client chờ mượn connection từ pool trước khi báo lỗi (đơn vị mili giây trong ví dụ); nó **không phải** `statement_timeout` của PostgreSQL hay timeout TCP kết nối tới host.

Thông tin xác thực nên lấy từ secret manager hoặc hệ thống quản lý bí mật, không ghi password thật vào file cấu hình được commit vào repository.

## 14. Connection pooling và PgBouncer

Trong mô hình PostgreSQL truyền thống, tạo quá nhiều kết nối trực tiếp có thể gây overhead cao. **Connection pooling** cho phép tái sử dụng connection thay vì mở/đóng mỗi HTTP request.

Có hai loại thường gặp:

1. **Pool trong ứng dụng:** HikariCP của Java giữ một số kết nối tới database.
2. **Pooler bên ngoài:** PgBouncer nhận nhiều client connections và ánh xạ chúng tới số lượng server connections được kiểm soát.

```text
                  4 Application replicas
                    /      |      \
                   v       v       v
                 JDBC / Hikari pools
                         |
                         v
                      PgBouncer
                  (pool server connections)
                         |
                         v
                 PostgreSQL primary
              max_connections hữu hạn
```

### 14.1. Session pooling và transaction pooling

| Kiểu | Ý tưởng | Điểm cần lưu ý |
| --- | --- | --- |
| Session pooling | Một server connection được giữ cho client trong suốt session. | Giảm chi phí tạo kết nối, nhưng khả năng chia sẻ thấp hơn khi có nhiều client rảnh. |
| Transaction pooling | Chỉ giữ server connection cho client trong phạm vi một transaction rồi có thể trả về pool. | Tối ưu số backend cho workload phù hợp, nhưng những tính năng phụ thuộc trạng thái session có thể cần thay đổi thiết kế. |

Với transaction pooling, ứng dụng phải chú ý tới session state như temporary tables, `SET` các tham số session, session-level advisory locks, `LISTEN/NOTIFY`, cursor hoặc prepared statements; mức hỗ trợ thực tế tùy tính năng và phiên bản PgBouncer. Không mặc định rằng chuyển từ kết nối trực tiếp sang transaction pooling sẽ giữ nguyên mọi hành vi session.

### 14.2. Pooler không tạo thêm năng lực CPU/I/O

PgBouncer giúp kiểm soát số server connections và giảm overhead, nhưng không khiến một máy PostgreSQL tự xử lý được vô hạn SQL đồng thời. Khi có quá nhiều transaction nặng, pooler sẽ **xếp hàng** những yêu cầu chờ backend. Cần theo dõi độ trễ chờ, timeout, CPU, lock và I/O.

Nếu mục tiêu là tăng throughput, hãy kết hợp phân tích SQL/index, transaction time, read replicas hoặc thay đổi kiến trúc phù hợp. Pooling chỉ là một phần của bài toán năng lực.

## 15. Timeout và vòng đời phiên

Không phải mọi connection tồn tại đều đang làm công việc hữu ích. PostgreSQL cung cấp một số timeout giúp giới hạn những tình huống nguy hiểm.

| Tham số | Ý nghĩa khái quát |
| --- | --- |
| `idle_in_transaction_session_timeout` | Có thể chấm dứt session bỏ không quá lâu khi transaction vẫn mở. |
| `idle_session_timeout` | Có thể chấm dứt session idle không ở trong transaction; cần cẩn trọng với connection pools. |
| `statement_timeout` | Giới hạn thời gian thực thi câu lệnh theo phạm vi áp dụng. |
| `lock_timeout` | Giới hạn thời gian chờ khóa. |
| `authentication_timeout` | Giới hạn thời gian hoàn thành quá trình xác thực kết nối. |
| `tcp_keepalives_idle` và các thiết lập keepalive liên quan | Ảnh hưởng việc phát hiện kết nối TCP bị mất theo hệ điều hành và cấu hình. |

Kiểm tra:

```sql
SHOW idle_in_transaction_session_timeout;
SHOW idle_session_timeout;
SHOW statement_timeout;
SHOW lock_timeout;
```

Không nên đặt các timeout cùng một giá trị mà không hiểu mục đích:

- `statement_timeout` không giải quyết trực tiếp việc pool có quá nhiều kết nối `idle`.
- `idle_in_transaction_session_timeout` giúp giảm rủi ro transaction treo nhưng có thể làm ứng dụng nhận lỗi khi đang giữ transaction quá lâu.
- `idle_session_timeout` có thể cắt những kết nối idle mà pool đang có ý định tái sử dụng; nếu cấu hình pool không phát hiện và loại kết nối chết, ứng dụng có thể gặp lỗi ngắt quãng.

Khi áp dụng timeout, cần phối hợp cấu hình phía JDBC/pooler và kiểm thử hành vi retry của ứng dụng.

## 16. Chẩn đoán những lỗi kết nối thường gặp

Những lỗi sau nhìn giống nhau ở tầng ứng dụng nhưng xuất phát từ các lớp khác nhau.

| Triệu chứng | Khả năng chính | Cần kiểm tra |
| --- | --- | --- |
| `Connection refused` | Không có listener ở địa chỉ/cổng đích hoặc hệ thống chủ động từ chối. | Server running, `listen_addresses`, `port`, firewall và port mapping. |
| Timeout khi mở TCP | Đường mạng bị chặn, không định tuyến được hoặc endpoint không phản hồi. | DNS, route, firewall, security group, proxy/load balancer. |
| `no pg_hba.conf entry` | Chưa có luật HBA phù hợp host/user/database/TLS. | `hba_file`, luật IPv4/IPv6, thứ tự rule, SSL mode. |
| `password authentication failed` | Xác thực không thành công. | Password/secret, user, HBA method, account provisioning. |
| `remaining connection slots are reserved` | Suất kết nối thông thường đã hết, còn slot đặc quyền. | `max_connections`, reserved slots, pool sizes, `pg_stat_activity`. |
| `too many clients already` | Giới hạn kết nối đã chạm. | Session count, pool leak, cấu hình server và nhu cầu concurrency. |
| `too many connections for role` | Hạn mức `CONNECTION LIMIT` của role. | `pg_roles.rolconnlimit`, session của role. |
| `too many connections for database` | Hạn mức kết nối database. | `pg_database.datconnlimit`, `pg_stat_database.numbackends`. |
| JDBC pool timeout | Không mượn được connection từ pool trong thời hạn. | Hikari active/idle/pending, SQL chậm, connection leak, server saturation. |

Thông điệp chính xác có thể khác theo PostgreSQL/JDBC/PgBouncer và cách thư viện bọc lỗi. Cần giữ **SQLSTATE, thông điệp gốc và timestamp** để khoanh vùng nguyên nhân.

### 16.1. “Connection refused” không nhất thiết là lỗi pg_hba.conf

`pg_hba.conf` được xét sau khi client đã tới được PostgreSQL ở bước kết nối thích hợp. Nếu không có process nghe ở địa chỉ/cổng, việc thêm một dòng HBA sẽ không tạo listener mới.

Trình tự:

1. Kiểm tra PostgreSQL process đã chạy chưa.
2. Kiểm tra `listen_addresses` và `port` đang có hiệu lực.
3. Xem listener trong OS hoặc container.
4. Kiểm tra route và firewall.
5. Khi TCP thông, mới xét HBA và xác thực nếu vẫn bị từ chối.

### 16.2. Lỗi reserved slots

Nếu server báo chỉ còn kết nối dành cho superuser hoặc role có đặc quyền sử dụng slot dự phòng, dấu hiệu cho thấy **kết nối thường đã chạm ngưỡng phục vụ**. Không nên đăng nhập bằng superuser từ ứng dụng để vượt ngưỡng.

Thay vào đó, quản trị viên nên:

- Quan sát `pg_stat_activity` để tìm role/database/service đang dùng nhiều sessions.
- Kiểm tra lượng kết nối sau rollout/autoscaling.
- Xem connection pool có bị rò rỉ hay giữ nhiều session quá lâu không.
- Giảm đỉnh mở kết nối hoặc tạm điều tiết request theo runbook.
- Chỉ cân nhắc tăng `max_connections` sau khi đánh giá tài nguyên và kế hoạch restart.

### 16.3. Khi timeout là lỗi từ client pool

Thông báo như “Connection is not available, request timed out” từ HikariCP thường có nghĩa không lấy được connection từ pool trong thời gian cho phép. Nó **không tự chứng minh PostgreSQL từ chối kết nối**: tất cả server connections của pool có thể đang bận vì truy vấn chậm hoặc transaction giữ quá lâu.

Cần đối chiếu metric pool `active`, `idle`, `pending` và thời gian mượn connection với trạng thái server. Tăng max pool size có thể làm lỗi tạm biến mất nhưng chuyển áp lực về PostgreSQL.

## 17. Dùng pg_stat_ssl để quan sát kết nối TLS

Khi PostgreSQL phục vụ qua mạng, TLS giúp bảo vệ dữ liệu trên đường truyền và có thể là một phần chính sách xác thực.

Kiểm tra cấu hình server:

```sql
SHOW ssl;
```

Nếu có quyền quan sát phù hợp, có thể xem trạng thái TLS của session:

```sql
SELECT
    a.pid,
    a.usename,
    a.client_addr,
    a.application_name,
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s
  ON s.pid = a.pid
WHERE a.backend_type = 'client backend'
ORDER BY a.pid;
```

`s.ssl = true` cho biết PostgreSQL session tương ứng sử dụng SSL/TLS. Nếu có proxy kết thúc TLS trước PostgreSQL, trạng thái bảo vệ giữa từng chặng phải được đánh giá riêng: TLS từ client tới proxy **không tự chứng minh** kết nối từ proxy tới PostgreSQL cũng có TLS.

### verify-full trong ứng dụng

Với PostgreSQL client/libpq, `sslmode=verify-full` yêu cầu xác thực chứng chỉ và tên host theo quy tắc TLS hỗ trợ. Một ứng dụng có thể cần CA certificate và hostname đúng để kết nối thành công.

Ví dụ dạng URL:

```text
jdbc:postgresql://db.internal.example.test:5432/appdb?sslmode=verify-full
```

URL ở đây chỉ minh họa lựa chọn; cần cấu hình trust material và chứng chỉ server phù hợp với PostgreSQL JDBC Driver đang dùng. Không chọn `sslmode=disable` để tránh lỗi chứng chỉ trên môi trường bắt buộc mã hóa đường truyền.

## 18. Container, Docker và Kubernetes: phân biệt cổng trong/ngoài

### 18.1. Docker port mapping

Giả sử PostgreSQL trong container nghe `0.0.0.0:5432`, nhưng bạn chỉ muốn cho máy host truy cập qua loopback:

```text
Docker host 127.0.0.1:15432
              |
       port forwarding
              |
              v
Container 0.0.0.0:5432
```

Cú pháp Docker minh họa:

```bash
docker run --name pg-lab \
  -e POSTGRES_PASSWORD=REPLACE_WITH_LAB_SECRET \
  -p 127.0.0.1:15432:5432 \
  postgres:16
```

Lệnh này chỉ mang tính thử nghiệm: biến môi trường ở ví dụ chứa placeholder và có thể bị lộ qua lịch sử/metadata container. Không dùng secret thật theo cách này trong production. Hãy tuân theo cơ chế secret và volume bền vững của nền tảng.

Trong container, PostgreSQL vẫn nghe port `5432`; từ host, client có thể kết nối qua `127.0.0.1:15432`. Đổi port mapping **không bắt buộc thay `port` trong PostgreSQL**.

`listen_addresses = 'localhost'` trong container chỉ nghe loopback **bên trong container**, nên port forwarding từ host qua interface mạng container có thể không truy cập được. Cần cấu hình listener phù hợp cùng chính sách mạng, không chỉ thêm `-p`.

### 18.2. Kubernetes Service

Một PostgreSQL Pod có thể nghe `5432`, còn Kubernetes Service cung cấp tên DNS và port cho client:

```text
App Pod
   |
   v
postgres.database.svc.cluster.local:5432
   |
   v
Kubernetes Service -> PostgreSQL Pod:5432
```

Ở đây:

- Service `port` có thể khác `targetPort` của Pod.
- NetworkPolicy có thể giới hạn nguồn được kết nối.
- PostgreSQL vẫn cần listener và luật HBA phù hợp với địa chỉ mà nó thực tế nhìn thấy, có thể là IP Pod hoặc một địa chỉ đã bị NAT/proxy.
- Nếu dùng PostgreSQL Operator, tham số `listen_addresses` và `max_connections` có thể được quản lý thông qua custom resource, không phải bằng cách chỉnh trực tiếp file bên trong Pod.

**Không lấy kết quả `SHOW port` rồi kết luận client bên ngoài cluster phải dùng đúng port đó.** Client phải dùng port của endpoint phù hợp, sau khi đi qua các tầng chuyển tiếp được cấu hình.

## 19. Managed PostgreSQL và giới hạn của tài khoản quản trị

Trên các dịch vụ PostgreSQL được quản lý, nhà cung cấp có thể kiểm soát `listen_addresses`, cơ chế mở cổng, certificate, số kết nối hoặc quyền thay đổi thông số.

Bạn vẫn có thể thử:

```sql
SHOW listen_addresses;
SHOW port;
SHOW max_connections;
```

nhưng giá trị hiển thị và khả năng thay đổi có thể phụ thuộc parameter group, server configuration của dịch vụ hoặc quyền tài khoản quản trị được cấp.

Ví dụ khi kết nối bị từ chối từ một VM khác:

1. Kiểm tra endpoint và port do nhà cung cấp công bố.
2. Kiểm tra network access rules/security group/private network.
3. Kiểm tra TLS và thông tin đăng nhập.
4. Kiểm tra giới hạn kết nối riêng của dịch vụ.
5. Sử dụng console/API của nhà cung cấp để điều chỉnh những tham số được hỗ trợ.

Không giả định có thể chạy `ALTER SYSTEM` hoặc chỉnh `postgresql.conf` vật lý trên managed database giống như PostgreSQL tự cài đặt.

## 20. Các tham số và lệnh thường được kiểm tra cùng nhau

Một script **chỉ đọc** có thể hỗ trợ chẩn đoán cơ bản:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'listen_addresses',
    'port',
    'unix_socket_directories',
    'max_connections',
    'superuser_reserved_connections',
    'reserved_connections',
    'ssl',
    'authentication_timeout',
    'idle_in_transaction_session_timeout',
    'idle_session_timeout'
)
ORDER BY name;
```

Điểm mạnh của truy vấn `pg_settings` so với loạt `SHOW` là **nếu major cũ không có tham số `reserved_connections`, truy vấn vẫn có thể trả các dòng tham số đang tồn tại** mà không bắt buộc phải `SHOW` tham số không được hỗ trợ.

Xem kết nối hiện tại:

```sql
SELECT
    datname,
    usename,
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, state
ORDER BY sessions DESC;
```

Xem giới hạn theo role:

```sql
SELECT rolname, rolconnlimit
FROM pg_roles
WHERE rolcanlogin
ORDER BY rolname;
```

Xem giới hạn database:

```sql
SELECT datname, datconnlimit
FROM pg_database
WHERE datallowconn
ORDER BY datname;
```

Một báo cáo kết nối tốt ghi rõ **thời điểm đo**, **instance và port**, **cấu hình tối đa**, **số phiên thực tế**, **phân bổ theo ứng dụng/role** và **số slot cần giữ lại cho vận hành**.

## 21. Thay đổi cấu hình có kiểm soát

Khi cần mở kết nối từ máy ứng dụng mới hoặc tăng số phiên, đừng chỉnh nhiều thông số cùng lúc mà không có mục tiêu rõ.

### 21.1. Quy trình thay đổi listener

Giả sử ứng dụng mới nằm trong mạng `10.20.30.0/24` và PostgreSQL hiện chỉ nghe localhost.

1. Xác nhận server đang chạy và `SHOW config_file`/`SHOW listen_addresses`.
2. Xác nhận IP `10.20.30.11` thực sự thuộc interface của server.
3. Dự kiến cấu hình `listen_addresses` hẹp nhất đủ dùng, ví dụ `'localhost,10.20.30.11'`.
4. Tạo quy tắc firewall/security group chỉ cho phép nguồn ứng dụng cần thiết tới port PostgreSQL.
5. Bổ sung HBA/TLS xác thực phù hợp cho database và role.
6. Lập kế hoạch restart vì `listen_addresses` thuộc nhóm `postmaster`.
7. Sau restart, xác nhận `SHOW listen_addresses`, listener thực tế và kết nối từ chính máy ứng dụng.
8. Kiểm tra ứng dụng và log, chuẩn bị phương án khôi phục cấu hình nếu đường kết nối bị mất.

Ví dụ cấu hình:

```conf
listen_addresses = 'localhost,10.20.30.11'
port = 5432
```

HBA phù hợp vẫn là bước riêng:

```conf
hostssl  appdb  app_user  10.20.30.0/24  scram-sha-256
```

Không phải mọi môi trường đều có thể trực tiếp thay `postgresql.conf`; managed service hoặc operator cần dùng cơ chế khai báo cấu hình của chính nền tảng.

### 21.2. Quy trình thay đổi max_connections

1. Đo số client sessions và đỉnh theo thời gian, không chỉ số tức thời.
2. Xác định mỗi pool/replica và tốc độ mở kết nối sau rollout.
3. Đánh giá thiếu slot do pool quá rộng, rò rỉ connection hay thực sự tăng tải.
4. Cân nhắc tuning pool/PgBouncer trước khi nâng hard limit.
5. Nếu vẫn cần tăng, tính RAM và các tài nguyên liên quan, xét các thành viên standby/HA.
6. Thay tham số và lên kế hoạch restart.
7. Sau restart, xác nhận giá trị, theo dõi memory, latency và trạng thái phiên.

Ví dụ chỉ để minh họa:

```conf
max_connections = 150
superuser_reserved_connections = 3
```

Trên PostgreSQL 16+ có thể xem xét thêm `reserved_connections` cho role vận hành khi yêu cầu phù hợp. Các tham số dự phòng thường cũng cần được điều chỉnh theo quy trình cấu hình/restart tương ứng.

Không tăng `max_connections` tới một con số lớn bất kỳ chỉ để tránh lỗi pool timeout; việc này có thể dẫn tới tiêu thụ bộ nhớ và độ đồng thời kém hiệu quả.

## 22. Một số tình huống vận hành và cách suy luận

### Tình huống A: local kết nối được, remote không kết nối được

**Hiện trạng:** Trên database server, `psql -h 127.0.0.1` thành công; từ máy ứng dụng, `psql -h 10.20.30.11` báo `connection refused`.

**Phân tích:** Có thể PostgreSQL chỉ nghe loopback, hoặc IP/port mong đợi không được bind, hoặc lớp mạng từ chối. Kiểm tra `SHOW listen_addresses`, `SHOW port` và listener OS; tiếp theo mới kiểm tra firewall và HBA. Thêm HBA mà không mở listener đúng IP sẽ không xử lý được vấn đề này.

### Tình huống B: log báo FATAL: no pg_hba.conf entry

**Hiện trạng:** PostgreSQL có listener, nhưng client từ mạng mới bị từ chối.

**Phân tích:** Client đã tới được lớp xử lý kết nối PostgreSQL. Kiểm tra database, role, client source IP, SSL mode và quy tắc HBA theo thứ tự. Không cần tăng `max_connections` để giải quyết thiếu HBA.

### Tình huống C: sau autoscaling, ứng dụng báo too many clients

**Hiện trạng:** Trước đây có hai application replicas, mỗi replica pool 20; sau autoscaling tăng lên sáu replicas và giữ nguyên pool.

**Phân tích:** Ngân sách đỉnh tăng từ `2 * 20 = 40` lên `6 * 20 = 120` kết nối tiềm năng, chưa tính monitoring/jobs và reserved slots. Nếu `max_connections = 100`, hệ thống không đủ slot. Cần giảm pool size/giới hạn replicas, đánh giá PgBouncer hoặc thay đổi capacity có kiểm soát.

### Tình huống D: max_connections còn dư nhưng một service vẫn không đăng nhập được

**Hiện trạng:** Server có `max_connections = 150` và chỉ khoảng 70 client sessions, nhưng một account báo vượt giới hạn phiên.

**Phân tích:** Xem `rolconnlimit` hoặc `datconnlimit`. Nếu role bị giới hạn 10 sessions hoặc database bị giới hạn 60, chúng có thể là nguyên nhân. Giới hạn toàn server không phải giới hạn duy nhất.

### Tình huống E: sửa port rồi reload, ứng dụng vẫn phải dùng port cũ

**Hiện trạng:** Sửa `port = 5433` rồi chạy `SELECT pg_reload_conf()`, nhưng server vẫn nghe `5432`.

**Phân tích:** `port` cần restart. Đọc `pg_settings.context` và `pending_restart`, lập kế hoạch restart rồi kiểm tra lại. Reload HBA và restart listener là hai thao tác có phạm vi khác nhau.

### Tình huống F: pool chứa nhiều phiên idle

**Hiện trạng:** `pg_stat_activity` cho thấy hàng chục phiên `idle` của cùng một user, query DB không nặng.

**Phân tích:** Nhiều phiên idle có thể là hoạt động bình thường của pool, nhưng nếu pool size lớn hơn nhu cầu, chúng vẫn chiếm slot. Hãy so active/idle/pending metrics, số replica và thời gian giữ connection; không kết luận mọi session idle là rò rỉ trước khi xem chính sách pool.

### Tình huống G: idle in transaction tăng

**Hiện trạng:** Nhiều phiên có `state='idle in transaction'` và `xact_start` cũ.

**Phân tích:** Khả năng ứng dụng mở transaction nhưng xử lý chậm hoặc quên commit/rollback. Các session có thể giữ lock/snapshot, gây chậm VACUUM và cạnh tranh truy vấn. Cần sửa transaction boundary trong ứng dụng; `idle_in_transaction_session_timeout` chỉ là một biện pháp hỗ trợ, không thay thế sửa nguyên nhân.

### Tình huống H: kiểm tra TCP được nhưng ứng dụng vẫn lỗi TLS

**Hiện trạng:** `pg_isready` báo accepting, còn JDBC với `sslmode=verify-full` báo lỗi chứng chỉ.

**Phân tích:** Cổng và PostgreSQL endpoint có thể đã sẵn sàng, nhưng chứng chỉ không khớp hostname, CA chưa được trust hoặc TLS termination chưa đúng thiết kế. Cần kiểm tra chứng chỉ và đường đi TLS; không tắt xác minh chứng chỉ để làm lỗi biến mất mà không đánh giá rủi ro.

## 23. Bài tập thực hành

Những bài dưới đây chủ yếu dùng truy vấn đọc. Với các lệnh `ALTER ROLE`, `ALTER DATABASE` hoặc thay đổi `postgresql.conf`, chỉ chạy trong lab có quyền quản trị và có khả năng khôi phục cấu hình.

### Bài 1. Kiểm tra listener của server

```sql
SHOW listen_addresses;
SHOW port;
SHOW unix_socket_directories;
```

**Câu hỏi:** Nếu `listen_addresses = 'localhost'` và `port = 5432`, ứng dụng ở máy khác có thể tự kết nối tới IP nội bộ của database server không?

**Đáp án:** Không chỉ bằng cấu hình này. PostgreSQL thường chỉ nghe loopback. Phải cấu hình listener trên IP phù hợp, kiểm soát firewall, HBA và xác thực, rồi restart khi thay đổi `listen_addresses`.

### Bài 2. Phân biệt TCP và Unix socket

Chạy lần lượt trên máy Linux có PostgreSQL lab:

```bash
psql -U app_user -d appdb
psql -h 127.0.0.1 -p 5432 -U app_user -d appdb
```

**Yêu cầu:** quan sát kết quả xác thực và `\conninfo`. Nếu khác nhau, giải thích vì sao.

**Gợi ý:** kết nối không có `-h` thường dùng Unix socket và luật HBA `local`; kết nối với `127.0.0.1` dùng TCP và luật `host`/`hostssl`.

### Bài 3. Xác định ngân sách kết nối

Server `max_connections = 100`, có `superuser_reserved_connections = 3` và trên PostgreSQL hỗ trợ `reserved_connections = 5`. Ứng dụng có ba replicas, mỗi replica pool tối đa 30; thêm một job có pool tối đa 10.

**Câu hỏi:** Cấu hình pool có nguy cơ làm cạn connection slots không?

**Phân tích:** `3 * 30 + 10 = 100` kết nối tiềm năng. Trong khi slot thông thường còn phải nhường phần dự phòng và các kết nối khác. Đây là thiết kế dễ bị từ chối khi cùng lên đỉnh; cần giảm budget pool, tính thêm monitoring/migration và cân nhắc pooler.

### Bài 4. Nhận diện trạng thái connection

```sql
SELECT
    state,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state
ORDER BY sessions DESC;
```

**Yêu cầu:** phân biệt `active`, `idle` và `idle in transaction`. Vì sao không thể kết luận mọi connection idle đều nguy hiểm?

**Gợi ý:** pool chủ động giữ idle connections để tái sử dụng; điều cần xem là quy mô và thời gian giữ connection, đồng thời phát hiện những transaction mở kéo dài.

### Bài 5. Giới hạn role so với giới hạn server

Trên môi trường lab với role đã tồn tại:

```sql
ALTER ROLE app_service CONNECTION LIMIT 5;
```

**Câu hỏi:** Nếu PostgreSQL còn hàng chục slot trống, tại sao kết nối thứ sáu của role này vẫn có thể bị từ chối?

**Đáp án:** Vì giới hạn riêng `CONNECTION LIMIT 5` của role có thể bị chạm dù `max_connections` chưa hết. Đây là các lớp giới hạn riêng; cần kiểm tra `pg_roles.rolconnlimit` và số session của role.

Sau thực hành, chỉ khi được phép và cần bỏ hạn mức:

```sql
ALTER ROLE app_service CONNECTION LIMIT -1;
```

### Bài 6. Cấu hình đổi nhưng chưa có hiệu lực

```sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name IN ('listen_addresses', 'port', 'max_connections');
```

**Câu hỏi:** `context = 'postmaster'` và `pending_restart = true` cho biết điều gì?

**Đáp án:** Thay đổi cần khởi động lại server để áp dụng. Reload đơn thuần không thể thay listening sockets hoặc số connection slots đã cấp lúc khởi động.

### Bài 7. Phân tích lỗi từ môi trường container

PostgreSQL trong container nghe `5432`. Host publish `15432:5432`, và client chạy trên host dùng `-p 5432` nhưng báo `connection refused`.

**Gợi ý:** cần kết nối tới **port publish phía host**, tức `15432` trong ví dụ, đồng thời xác nhận Docker mapping/bind address. `SHOW port` trong container vẫn có thể là `5432`.

### Bài 8. Thiết kế kết nối cho Java API

Ứng dụng có 4 replicas, mỗi replica Hikari `maximum-pool-size = 25`; PostgreSQL `max_connections = 120`. Ngoài ứng dụng còn các job và admin connections.

**Câu hỏi:** Tại sao vẫn có nguy cơ hết connection slots dù `4 * 25 = 100 < 120`?

**Đáp án:** 20 slot còn lại không hoàn toàn là ngân sách an toàn cho ứng dụng: có reserved slots, jobs, monitoring, rollout chồng replicas và các client khác. Cần tính **đỉnh toàn hệ thống** thay vì chỉ một service, đồng thời xem chi phí RAM/CPU và nguy cơ quá nhiều truy vấn đồng thời.

### Bài 9. Kiểm tra kết nối TLS

```sql
SELECT
    a.usename,
    a.client_addr,
    s.ssl,
    s.version
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'client backend';
```

**Yêu cầu:** nếu một session TCP có `ssl = false` nhưng chính sách đòi TLS, cần điều tra gì?

**Gợi ý:** đường kết nối, HBA `hostssl`, cấu hình TLS của server và client, cùng khả năng TLS kết thúc ở proxy. Không suy ra mọi hop được bảo vệ từ một trạng thái TLS duy nhất.

## 24. Các nhầm lẫn thường gặp

**1. “listen_addresses='*' nghĩa là ai cũng đăng nhập được.”** Không. Nó mở rộng nơi server lắng nghe; HBA, xác thực, quyền database và firewall vẫn kiểm soát truy cập.

**2. “Cần cho phép mạng 10.20.30.0/24 thì ghi CIDR vào listen_addresses.”** Không. `listen_addresses` dùng IP/interface hoặc hostname của **server**; dải nguồn client thuộc HBA/firewall.

**3. “localhost và 127.0.0.1 luôn giống nhau.”** Không hoàn toàn. `localhost` có thể phân giải IPv4/IPv6; không chỉ định host trên Linux còn có thể dùng Unix socket.

**4. “Đổi port chỉ cần pg_reload_conf().”** Không. `port` thuộc cấu hình cần restart.

**5. “pg_isready báo accepting nên tài khoản ứng dụng chắc chắn đăng nhập được.”** Không. Nó không thay thế kiểm tra user/password/database/TLS và quyền.

**6. “max_connections=100 thì 100 connection đều dành cho pool.”** Không. Cần giữ slot quản trị và tính các client khác, cũng như các điều kiện cấu hình riêng theo phiên bản.

**7. “Connection limit là giới hạn số truy vấn đang chạy đồng thời.”** Không. Một session `idle` vẫn chiếm connection slot dù không thực thi query ở thời điểm đó.

**8. “Tăng max_connections luôn làm ứng dụng nhanh hơn.”** Không. Rất nhiều backend có thể tạo tranh chấp CPU/RAM/I/O và giảm throughput.

**9. “Tăng max_connections sẽ sửa lỗi role đạt CONNECTION LIMIT.”** Không. Role/database limits là những giới hạn riêng.

**10. “Mọi PostgreSQL đều hỗ trợ reserved_connections.”** Không. Tham số này được bổ sung ở PostgreSQL 16; phải xem major trước khi dùng.

**11. “Session idle in transaction cũng vô hại như idle.”** Không. Transaction mở dài có thể giữ lock và làm chậm việc dọn dẹp MVCC.

**12. “Kết nối qua Docker/Kubernetes phải dùng đúng SHOW port.”** Không nhất thiết. Port phía client có thể do host publish hoặc Service mapping quyết định.

**13. “Có PgBouncer thì không cần quan tâm transaction hoặc session state.”** Sai. Transaction pooling có yêu cầu tương thích với cách ứng dụng sử dụng trạng thái session.

**14. “Một timeout có thể xử lý mọi lỗi connection.”** Không. Connection timeout của pool, `statement_timeout`, `lock_timeout` và các idle session timeouts giải quyết những vấn đề khác nhau.

**15. “Listener đã mở thì không cần TLS.”** Sai. Khi kết nối qua mạng cần bảo vệ, TLS và xác thực phù hợp là một phần của thiết kế.

## 25. Quy trình chẩn đoán nhanh

Khi ứng dụng không kết nối được hoặc kết nối chập chờn, có thể đi theo thứ tự:

```text
1. Xác định endpoint mà ứng dụng thật sự dùng:
   hostname/IP, port, database, user, TLS/proxy
                         |
                         v
2. Thử pg_isready hoặc kiểm tra TCP từ đúng client host
                         |
              +----------+-----------+
              |                      |
         Không tới được         Tới được server
              |                      |
              v                      v
3A. Process/listener/port/      3B. HBA/TLS/authentication
    DNS/firewall/route               /CONNECT privilege
              |                      |
              +----------+-----------+
                         |
                         v
4. Nếu lỗi giới hạn kết nối:
   max_connections / reserved slots
   rolconnlimit / datconnlimit
                         |
                         v
5. Xem pg_stat_activity:
   role, database, active, idle, idle in transaction
                         |
                         v
6. Đối chiếu pool sizes, replicas, rollout và tải thực
                         |
                         v
7. Sửa đúng lớp gây lỗi; xác minh lại từ ứng dụng
```

Một bộ lệnh SQL đọc nhanh trên server đang hoạt động:

```sql
SHOW server_version;
SHOW listen_addresses;
SHOW port;
SHOW max_connections;

SELECT count(*) AS client_sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend';

SELECT datname, usename, state, count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, usename, state
ORDER BY sessions DESC;
```

Với sự cố kết nối, kết quả từ **đúng client host** và log server quanh timestamp lỗi vẫn rất quan trọng. Một phép thử thành công trên chính máy database không đủ đại diện cho đường mạng mà ứng dụng Java sử dụng.

## 26. Tổng kết

Cấu hình kết nối PostgreSQL có ba trụ cột:

- **`listen_addresses`** xác định PostgreSQL nghe trên những địa chỉ mạng nào; **`port`** xác định cổng TCP của server. Hai tham số thuộc nhóm cần restart khi đổi giá trị.
- **`pg_hba.conf`, TLS, firewall và quyền `CONNECT`** quyết định một client đã tới được server có thể xác thực và truy cập database hay không. Mở listener **không** đồng nghĩa mở quyền cho mọi client.
- **`max_connections` và các giới hạn role/database** kiểm soát số phiên có thể tồn tại, còn các slot dự phòng bảo vệ một phần khả năng truy cập quản trị khi hệ thống gần đầy. Tăng giới hạn kết nối không tự động tăng năng lực xử lý query.

Khi vận hành nhiều ứng dụng Java hoặc container replicas, hãy tính ngân sách theo **số replica nhân với pool size tối đa**, thêm các client khác và khoảng dự phòng. Dùng `pg_stat_activity` để phân biệt session `active`, `idle` và `idle in transaction`; dùng connection pooling hoặc PgBouncer khi phù hợp thay vì mở vô hạn backend.

Cuối cùng, đừng sửa cấu hình theo phỏng đoán. **Xác nhận đúng instance, đúng listener, đúng đường mạng và đúng loại giới hạn**, thay đổi có kiểm soát rồi kiểm chứng lại từ cùng đường kết nối mà ứng dụng thực sự sử dụng. Đó là nền tảng để PostgreSQL vừa truy cập được, vừa an toàn, ổn định khi tải tăng.
