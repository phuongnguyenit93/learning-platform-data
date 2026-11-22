# Kết nối cục bộ qua Unix-domain socket hoặc TCP trong PostgreSQL

Sau khi cài đặt PostgreSQL, việc đầu tiên thường là kiểm tra **máy chủ đã khởi động chưa** và **ứng dụng hoặc người dùng có thể kết nối bằng cách nào**. Trên máy Linux/macOS, hai kiểu kết nối cục bộ thông dụng là:

- **Unix-domain socket:** tiến trình khách giao tiếp với PostgreSQL trên cùng hệ điều hành qua một tệp socket, không dùng kết nối TCP/IP.
- **TCP loopback:** tiến trình khách kết nối tới PostgreSQL qua địa chỉ `127.0.0.1` (IPv4) hoặc `::1` (IPv6), vẫn ở cùng máy nhưng sử dụng giao thức TCP.

Hai cách có thể tới **cùng một PostgreSQL instance**, **cùng database** và **cùng role**, nhưng cách chọn địa chỉ, quy tắc xác thực trong `pg_hba.conf` và lỗi thường gặp lại khác nhau. Hiểu sự khác biệt này giúp tránh lỗi “máy chủ đang chạy nhưng `psql` không kết nối được”, đặc biệt khi vừa cài PostgreSQL, cấu hình một dịch vụ Java hoặc chuyển từ tài khoản hệ điều hành sang role riêng của ứng dụng.

Bài hướng dẫn trên PostgreSQL hiện đại, tập trung môi trường Unix-like (Linux/macOS) cho Unix-domain socket. Trên Windows và trong container, chi tiết về socket và `localhost` khác nhau; sẽ được giải thích ở phần cuối.

## 1. Phân biệt máy chủ, client, database và role

Trong PostgreSQL, những đối tượng sau **không phải một**:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| PostgreSQL server | Tiến trình `postgres` | Tiếp nhận kết nối, quản lý dữ liệu và xử lý SQL |
| Client | `psql`, ứng dụng Java/JDBC, DBeaver | Gửi yêu cầu kết nối và câu lệnh SQL |
| Database | `postgres`, `app_db` | Tập đối tượng dữ liệu mà phiên kết nối tới |
| Role có quyền LOGIN | `postgres`, `app_user` | Danh tính và quyền trong PostgreSQL |
| Người dùng hệ điều hành | `postgres`, `alice` | Danh tính tiến trình client trên máy |
| Địa chỉ kết nối | Thư mục socket, `127.0.0.1`, `::1` | Cách client tìm đến server |
| Phương thức xác thực | `peer`, `scram-sha-256` | Cách server xác minh danh tính client |

Ví dụ `postgres` có thể đồng thời là tên role quản trị và tên database mặc định, nhưng hai khái niệm độc lập. Người dùng Linux `postgres` cũng là một danh tính khác, chỉ có thể được ánh xạ sang PostgreSQL role theo cấu hình.

Địa chỉ `localhost` chỉ là tên máy, không phải một phương thức xác thực; nó thường được phân giải thành địa chỉ loopback rồi đi qua TCP. Trái lại, một đường dẫn như `/var/run/postgresql` trong tham số host của libpq có ý nghĩa là **thư mục chứa Unix socket**.

## 2. Hình dung đường đi của hai kiểu kết nối

~~~mermaid
flowchart LR
    C["Client: psql / libpq"] --> Q{"Chọn kiểu kết nối"}
    Q -->|"Không đặt host trên Unix, hoặc host là thư mục"| U["Unix-domain socket"]
    Q -->|"host=127.0.0.1 hoặc host=localhost"| T["TCP loopback"]
    U --> H1["pg_hba.conf: dòng local"]
    T --> H2["pg_hba.conf: dòng host/hostssl"]
    H1 --> P[("PostgreSQL server")]
    H2 --> P
    P --> D[("Database app_db")]
~~~

Trong môi trường Unix-like, client dùng thư viện **libpq** (như `psql`) thường ưu tiên Unix socket **khi không chỉ định host**, còn khi chỉ định `-h localhost` hoặc `-h 127.0.0.1`, client sẽ kết nối qua TCP.

Lưu ý: đó là mô tả hành vi mặc định của `psql`/libpq trên Unix-like, **không phải quy luật bắt buộc đối với mọi driver**. Ví dụ URL JDBC PostgreSQL thông thường sử dụng TCP, kể cả khi ứng dụng và database chạy trên cùng máy.

## 3. Bắt đầu từ psql: những tham số quan trọng

Cú pháp tổng quát:

~~~bash
psql -h HOST -p PORT -U ROLE -d DATABASE
~~~

Trong đó:

- `-h` / `--host`: hostname/IP để dùng TCP, hoặc **đường dẫn thư mục socket** khi dùng Unix-domain socket.
- `-p` / `--port`: cổng PostgreSQL, mặc định thường là `5432`. Với Unix socket, số port vẫn dùng để xác định tên socket.
- `-U` / `--username`: PostgreSQL role để đăng nhập.
- `-d` / `--dbname`: database được kết nối tới.

Nếu bỏ `-U`, libpq thường lấy tên người dùng hệ điều hành hiện tại làm tên role mặc định. Nếu bỏ `-d`, tên database mặc định thường lấy từ tên role. Đó là lý do chạy `psql` không tham số có thể báo “role does not exist” hoặc “database does not exist”, ngay cả khi server đang chạy bình thường.

Ví dụ truy cập một database cụ thể:

~~~bash
psql -U app_user -d app_db
~~~

Trên Linux/macOS, nếu không có cấu hình host khác can thiệp, câu này thường tìm Unix-domain socket mặc định. Nhưng nếu đã thiết lập biến môi trường `PGHOST` hoặc service configuration, kết nối thực tế có thể khác.

### Một số lệnh kiểm tra bên trong psql

Sau khi vào phiên tương tác:

~~~sql
SELECT current_user, current_database(), version();
~~~

Trong CLI `psql`, có thể dùng các meta-command:

~~~text
\conninfo
\du
\l
\q
~~~

`\conninfo` cho biết phiên kết nối hiện tại đang sử dụng loại địa chỉ nào, người dùng và database nào. `\du` liệt kê roles, `\l` liệt kê databases, `\q` thoát. Đây là **lệnh của psql**, không phải SQL chuẩn để gửi trực tiếp qua JDBC.

## 4. Kết nối cục bộ qua Unix-domain socket

### 4.1. Unix-domain socket là gì?

Trên Unix-like, PostgreSQL có thể tạo socket với tên thường có dạng:

~~~text
/var/run/postgresql/.s.PGSQL.5432
~~~

Tên phần cuối có `5432` tương ứng với port mà instance đang dùng. Tệp socket là **đầu mối IPC (inter-process communication)** giữa các tiến trình trên cùng máy; nó không phải một file văn bản chứa database và không cần kết nối TCP đến cổng 5432.

Thư mục chứa socket phụ thuộc hệ điều hành, cách cài đặt và cấu hình. Ví dụ:

- Nhiều bản cài Debian/Ubuntu dùng `/var/run/postgresql` (thường là đường dẫn tới `/run/postgresql`).
- Một số bản dựng hoặc cách cài đặt khác dùng `/tmp`.
- Hệ thống có nhiều instance có thể cấu hình những thư mục và port khác nhau.

**Không nên đoán cứng đường dẫn socket** từ một hệ thống khác. Hãy kiểm tra cấu hình PostgreSQL hoặc tài liệu của gói cài đặt đang sử dụng.

### 4.2. Dùng Unix socket mặc định

Trên máy Unix-like, thử:

~~~bash
psql -U postgres -d postgres
~~~

Nếu role PostgreSQL `postgres` đang yêu cầu xác thực `peer`, lệnh trên có thể **thất bại** khi bạn đang chạy bằng người dùng hệ điều hành khác tên `postgres`. Đây không chứng minh socket bị hỏng; có thể đơn giản là bạn không thỏa quy tắc xác thực.

Trong các bản cài Linux có tài khoản hệ điều hành `postgres`, một thao tác quản trị thường gặp là:

~~~bash
sudo -u postgres psql -d postgres
~~~

Lệnh dùng tài khoản OS `postgres` để kết nối vào PostgreSQL. Nó hoạt động khi dịch vụ, socket, quyền Unix và quy tắc `pg_hba.conf` tương ứng cho phép. Không dùng tài khoản quản trị này làm tài khoản ứng dụng thông thường.

### 4.3. Chỉ định thư mục socket một cách tường minh

~~~bash
psql \
  -h /var/run/postgresql \
  -p 5432 \
  -U postgres \
  -d postgres
~~~

Lưu ý: `-h /var/run/postgresql` là **đường dẫn thư mục**, không phải đường dẫn tới riêng file `.s.PGSQL.5432`. Libpq ghép tên socket phù hợp từ thư mục và số port.

Nếu server dùng thư mục `/tmp`:

~~~bash
psql -h /tmp -p 5432 -U app_user -d app_db
~~~

Không có quy tắc nào bắt buộc `/var/run/postgresql` phải tồn tại trên mọi máy. Nếu lệnh báo không tìm thấy socket, kiểm tra đúng thư mục đang được server sử dụng.

### 4.4. Xác nhận phiên thực sự đi qua Unix socket

Trong `psql`:

~~~text
\conninfo
~~~

Trên hệ thống Unix, thông báo có thể cho biết kết nối `via socket in "/var/run/postgresql"`.

Có thể dùng SQL:

~~~sql
SELECT
    current_user,
    current_database(),
    inet_client_addr() AS client_ip,
    inet_server_addr() AS server_ip;
~~~

Với một **kết nối Unix-domain socket**, cả `inet_client_addr()` và `inet_server_addr()` trả SQL `NULL` vì kết nối không dùng địa chỉ IP. Kết quả này nên được đối chiếu với `\conninfo`; không phải mọi ngữ cảnh `NULL` trong các view hệ thống đều chứng minh cùng một loại kết nối.

## 5. Kết nối cục bộ qua TCP loopback

### 5.1. Chỉ định IPv4 127.0.0.1

~~~bash
psql \
  -h 127.0.0.1 \
  -p 5432 \
  -U app_user \
  -d app_db
~~~

`127.0.0.1` là địa chỉ loopback IPv4 của **chính môi trường mạng đang chạy client**. Client yêu cầu kết nối TCP đến PostgreSQL ở cổng `5432` trên loopback.

### 5.2. Chỉ định localhost hoặc IPv6

~~~bash
psql -h localhost -p 5432 -U app_user -d app_db
~~~

Tên `localhost` thường phân giải thành `::1` (IPv6), `127.0.0.1` (IPv4), hoặc cả hai tùy cấu hình resolver. Vì vậy, kết nối dùng `localhost` có thể đi tới một địa chỉ khác với việc chỉ định `127.0.0.1` trực tiếp.

Muốn kiểm tra IPv6 riêng:

~~~bash
psql -h ::1 -p 5432 -U app_user -d app_db
~~~

Để xác định địa chỉ TCP được sử dụng trong phiên thành công:

~~~sql
SELECT
    inet_client_addr() AS client_ip,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port;
~~~

Khi kết nối bằng IPv4 loopback, thường thấy `127.0.0.1`; bằng IPv6 loopback, thường thấy `::1`. Giá trị port tương ứng cổng phía server.

### 5.3. TCP loopback không đồng nghĩa với TCP từ máy khác

Nếu `listen_addresses = 'localhost'`, PostgreSQL chỉ lắng nghe trên các địa chỉ loopback phù hợp. Một máy khác trong mạng không thể dùng IP LAN của server để kết nối chỉ vì bạn đã cấu hình TCP loopback.

Để cho phép truy cập từ máy khác, cần thay đổi cấu hình mạng, firewall, `pg_hba.conf` và chính sách bảo mật riêng. Bài này chủ yếu nói về **kết nối trên chính máy chủ**, không hướng dẫn mở PostgreSQL ra Internet.

## 6. So sánh Unix socket và TCP loopback

| Tiêu chí | Unix-domain socket | TCP loopback |
| --- | --- | --- |
| Cơ chế truyền | IPC tại hệ điều hành | TCP/IP qua loopback |
| Ví dụ `psql` | `psql -h /var/run/postgresql ...` | `psql -h 127.0.0.1 ...` |
| Địa chỉ | Thư mục socket và tên socket | IP/hostname + port |
| Phạm vi thông thường | Các tiến trình trong cùng hệ điều hành | Các tiến trình trong cùng network namespace/host theo địa chỉ loopback |
| Loại rule `pg_hba.conf` | `local` | `host`, `hostssl`, `hostnossl` tương ứng |
| Xác thực thường gặp | `peer` hoặc mật khẩu | `scram-sha-256`, TLS/mật khẩu theo cấu hình |
| Phụ thuộc `listen_addresses` | Không; chịu tác động bởi `unix_socket_directories` | Có |
| Có thể dùng `peer`? | Có, khi hệ thống/phương thức cho phép | Không theo cách xác thực peer qua Unix socket |
| Xác nhận bằng `inet_client_addr()` | SQL `NULL` | Thường là `127.0.0.1` hoặc `::1` |
| Phù hợp khi | Công cụ quản trị cục bộ, dịch vụ cùng OS có socket | Ứng dụng thông thường, JDBC, công cụ kết nối qua port |

Không có lựa chọn luôn nhanh hoặc an toàn tuyệt đối hơn trong mọi triển khai. Unix socket tránh phần TCP/IP và thuận tiện cho xác thực dựa trên người dùng OS, còn TCP được hỗ trợ rộng rãi bởi nhiều driver và công cụ. Trên một máy, chênh lệch hiệu năng thường phải **đo theo workload thực tế** thay vì dùng làm tiêu chí lựa chọn duy nhất.

## 7. Điều khiển kiểu kết nối bằng postgresql.conf

PostgreSQL có hai nhóm thiết lập khác nhau: lắng nghe TCP và vị trí Unix socket.

~~~conf
# Ví dụ minh họa trong postgresql.conf
listen_addresses = 'localhost'
port = 5432
unix_socket_directories = '/var/run/postgresql'
~~~

Trong đó:

- `listen_addresses`: địa chỉ IP mà PostgreSQL lắng nghe cho **kết nối TCP**. `localhost` giới hạn ở loopback; `'*'` có thể mở listener trên mọi interface theo cấu hình và không phù hợp làm thay đổi tùy tiện.
- `port`: cổng TCP và là một phần tên socket Unix.
- `unix_socket_directories`: thư mục/tập thư mục tạo Unix-domain socket. Giá trị rỗng có thể vô hiệu hóa socket Unix trong cấu hình hỗ trợ.

Các thiết lập này thường có hiệu lực ở thời điểm **khởi động PostgreSQL**, nên chỉnh chúng thường yêu cầu restart server. Ngược lại, thay đổi các quy tắc xác thực trong `pg_hba.conf` thường được áp dụng khi reload cấu hình, không cần restart toàn bộ instance trong môi trường Unix-like.

Để xem giá trị thực của server đang chạy:

~~~sql
SHOW listen_addresses;
SHOW port;
SHOW unix_socket_directories;
SHOW config_file;
SHOW hba_file;
~~~

Đường dẫn `config_file` và `hba_file` là nơi server dùng cho cấu hình, không nhất thiết cùng một thư mục với PostgreSQL data directory. Một số thông tin có thể bị hạn chế hiển thị cho role thiếu quyền.

### Kiểm tra PostgreSQL đã tạo socket chưa

Trên Linux, sau khi biết đúng thư mục:

~~~bash
ls -la /var/run/postgresql/
~~~

Có thể thấy tệp dạng `.s.PGSQL.5432` cùng lock file hỗ trợ. Tuy nhiên, **tệp socket tồn tại không bảo đảm role của bạn sẽ đăng nhập được**, và một tệp cũ không chứng minh PostgreSQL đang sẵn sàng. Dùng lệnh kết nối thực tế hoặc `pg_isready` để xác nhận trạng thái.

Trên Linux, có thể quan sát listener TCP với:

~~~bash
ss -ltn
~~~

Danh sách listener giúp biết có cổng TCP tương ứng hay không. Nó không cho biết một PostgreSQL role cụ thể có qua được `pg_hba.conf` hay không.

## 8. pg_hba.conf: vì sao cùng một user nhưng hai kết nối cho kết quả khác?

`pg_hba.conf` (host-based authentication configuration) xác định **loại kết nối nào được phép xác thực bằng phương thức nào**. PostgreSQL xét các bản ghi theo thứ tự từ trên xuống; **bản ghi đầu tiên khớp** loại kết nối, database, role và địa chỉ sẽ được chọn.

Nếu một bản ghi đã khớp nhưng xác thực thất bại, server **không tự thử các bản ghi bên dưới** để tìm cách khác. Đây là lý do thứ tự dòng trong file cực kỳ quan trọng.

Ví dụ minh họa một tập quy tắc nhỏ:

~~~conf
# TYPE   DATABASE   USER       ADDRESS          METHOD

# Unix socket: role quản trị dùng xác thực OS.
local    all        postgres                     peer

# Unix socket: ứng dụng dùng mật khẩu SCRAM.
local    app_db     app_user                     scram-sha-256

# TCP loopback IPv4:
host     app_db     app_user   127.0.0.1/32      scram-sha-256

# TCP loopback IPv6:
host     app_db     app_user   ::1/128           scram-sha-256
~~~

Phần địa chỉ để trống đối với bản ghi `local`. Đối với `host` cần địa chỉ/mạng cho phép. Ví dụ trên không chứa một quy tắc tổng quát cho mọi role/database; những kết nối khác chỉ được cho phép nếu có bản ghi phù hợp khác trong file.

### Phân biệt các loại bản ghi

| TYPE trong pg_hba.conf | Áp dụng |
| --- | --- |
| `local` | Chỉ kết nối Unix-domain socket |
| `host` | Kết nối TCP với cơ chế mã hóa phù hợp hoặc không mã hóa, theo quy tắc chung |
| `hostssl` | Kết nối TCP sử dụng SSL/TLS, cần server hỗ trợ/bật SSL |
| `hostnossl` | Kết nối TCP không sử dụng SSL/TLS |

Vì `local` và `host` là hai loại riêng, việc cho phép một Unix socket connection **không tự động** cho phép cùng role đó qua `127.0.0.1`.

Ngoài ra, kết nối `-h localhost` có thể đi qua IPv6 `::1`. Nếu file chỉ có `127.0.0.1/32` mà thiếu `::1/128`, kết nối IPv6 có thể không tìm được rule tương ứng hoặc hoạt động khác dự kiến. Đối chiếu địa chỉ cụ thể từ lỗi/log và phiên kết nối.

## 9. Xác thực peer trên Unix socket

**`peer`** là phương thức PostgreSQL có thể sử dụng trên Unix-domain socket. Nó yêu cầu hệ điều hành cung cấp danh tính OS của tiến trình client, sau đó PostgreSQL so khớp danh tính này với role đăng nhập hoặc ánh xạ qua `pg_ident.conf`.

Giả sử có dòng:

~~~conf
local   all   postgres   peer
~~~

Nếu bạn chạy lệnh dưới đây từ user OS `postgres`:

~~~bash
sudo -u postgres psql -U postgres -d postgres
~~~

thì PostgreSQL thường có thể xác minh OS user là `postgres` và cho phép vào role `postgres`.

Ngược lại, nếu đang là OS user `alice` nhưng chạy:

~~~bash
psql -U postgres -d postgres
~~~

thì bạn có thể nhận:

~~~text
FATAL:  Peer authentication failed for user "postgres"
~~~

Đây là **lỗi xác thực**, không nhất thiết là lỗi password hay server chết. Khi peer được cấu hình, việc nhập mật khẩu không tự làm cho danh tính OS `alice` biến thành `postgres`.

### Khi nào peer phù hợp?

- Quản trị PostgreSQL trực tiếp trên máy chủ với tài khoản OS được kiểm soát.
- Dịch vụ chạy bằng một OS user riêng và có PostgreSQL role tương ứng.
- Các môi trường cần dựa vào quyền và danh tính OS thay vì phân phối mật khẩu cho tiến trình cục bộ.

Nếu muốn ánh xạ tên OS user và database role khác nhau, có thể dùng `pg_ident.conf` cùng tham số `map=...` trong quy tắc `pg_hba.conf`. Đây là cấu hình quản trị có chủ đích, không phải cách bỏ qua phân quyền.

`peer` không áp dụng cho kết nối TCP `127.0.0.1` chỉ vì hai tiến trình chạy trên cùng máy. Với TCP, cần cấu hình một phương thức xác thực phù hợp với loại `host`.

## 10. Xác thực mật khẩu bằng SCRAM-SHA-256

Đối với tài khoản ứng dụng, lựa chọn phổ biến là **`scram-sha-256`**. Đây là cơ chế xác thực mật khẩu challenge–response được PostgreSQL hỗ trợ, thay cho các cấu hình mật khẩu cũ kém phù hợp hơn.

Ví dụ cho TCP loopback:

~~~conf
host   app_db   app_user   127.0.0.1/32   scram-sha-256
host   app_db   app_user   ::1/128        scram-sha-256
~~~

Và cho Unix socket khi muốn dùng cùng cơ chế mật khẩu:

~~~conf
local  app_db   app_user                  scram-sha-256
~~~

Khi dùng SCRAM, role cần có bí mật mật khẩu được lưu theo định dạng tương thích. Đăng nhập qua TCP:

~~~bash
psql -h 127.0.0.1 -p 5432 -U app_user -d app_db -W
~~~

`-W` buộc `psql` yêu cầu người dùng nhập mật khẩu tương tác. Không nên gõ mật khẩu thật trực tiếp trong URL, terminal command có thể lưu lịch sử hoặc tài liệu nhóm.

### Tạo một role và database dành cho lab

Trong phiên quản trị PostgreSQL hợp lệ:

~~~sql
CREATE ROLE app_user LOGIN;
CREATE DATABASE app_db OWNER app_user;
~~~

`CREATE DATABASE` phải được thực thi ở ngữ cảnh hợp lệ, không ở trong một transaction block do người dùng bao ngoài. Nếu role/database đã tồn tại, không chạy lại mà không xác định trạng thái hệ thống.

Trong `psql`, người quản trị có thể đặt mật khẩu tương tác:

~~~text
\password app_user
~~~

`\password` yêu cầu nhập mật khẩu và giúp tránh đưa plaintext password vào câu `ALTER ROLE ... PASSWORD '...'` có thể bị ghi vào lịch sử hoặc log client. PostgreSQL cần lưu SCRAM verifier tương thích theo cấu hình. Người quản trị nên kiểm tra `password_encryption` và chính sách cấp quyền trước khi thử nghiệm.

Ví dụ:

~~~sql
SHOW password_encryption;
~~~

Nếu giá trị hoặc quy trình lưu mật khẩu chưa tương thích với `scram-sha-256`, cần cập nhật verifier/mật khẩu bằng cơ chế hợp lệ trước khi kết nối. Không khuyến khích thay toàn bộ `pg_hba.conf` sang `trust` để xử lý nhanh một lỗi mật khẩu.

## 11. Thực hành song song: cùng role, hai đường kết nối

Giả sử server dùng port `5432`, socket directory `/var/run/postgresql` và đã tạo `app_user`/`app_db` với quy tắc SCRAM như trên.

### 11.1. Cửa sổ A: qua Unix socket

~~~bash
psql -h /var/run/postgresql \
     -p 5432 \
     -U app_user \
     -d app_db \
     -W
~~~

Khi vào `psql`:

~~~sql
SELECT
    current_user AS db_role,
    current_database() AS db_name,
    inet_client_addr() AS client_ip,
    inet_server_addr() AS server_ip,
    pg_backend_pid() AS backend_pid;
~~~

Kỳ vọng `client_ip` và `server_ip` là SQL `NULL`, còn `db_role` là `app_user`.

Trong `psql`:

~~~text
\conninfo
~~~

Nó sẽ mô tả kết nối qua socket directory.

### 11.2. Cửa sổ B: qua TCP IPv4 loopback

~~~bash
psql -h 127.0.0.1 \
     -p 5432 \
     -U app_user \
     -d app_db \
     -W
~~~

Chạy lại câu `SELECT` như ở A. Giá trị `client_ip` và `server_ip` thường là `127.0.0.1`. `pg_backend_pid()` ở A và B thường khác nhau vì đây là hai phiên backend riêng.

### 11.3. Đối chiếu kết quả

| Thuộc tính | Cửa sổ A | Cửa sổ B |
| --- | --- | --- |
| Role | app_user | app_user |
| Database | app_db | app_db |
| Transport | Unix socket | TCP IPv4 loopback |
| Client IP | SQL `NULL` | `127.0.0.1` |
| Quy tắc pg_hba | `local` | `host ... 127.0.0.1/32` |
| Phương thức xác thực ví dụ | scram-sha-256 | scram-sha-256 |

Cả hai có thể cùng thấy bảng dữ liệu trong `app_db`, vì **transport không quyết định quyền dữ liệu**. Quyền thực tế đến từ role, membership, grants, object ownership, row-level security và các thiết lập bảo mật liên quan.

### 11.4. Đóng kết nối

Trong từng cửa sổ:

~~~text
\q
~~~

Việc đóng phiên giải phóng backend session cùng các tài nguyên gắn với nó theo cơ chế PostgreSQL.

## 12. Tại sao hai kết nối có thể yêu cầu mật khẩu khác nhau?

Giả sử `pg_hba.conf` gồm:

~~~conf
local   all     postgres                     peer
host    all     postgres    127.0.0.1/32     scram-sha-256
~~~

Thì:

~~~bash
sudo -u postgres psql -U postgres -d postgres
~~~

có thể vào qua Unix socket **không cần nhập mật khẩu** nhờ xác thực OS bằng peer.

Nhưng:

~~~bash
psql -h 127.0.0.1 -U postgres -d postgres -W
~~~

dùng TCP và phải đáp ứng phương thức `scram-sha-256`, yêu cầu role có mật khẩu/verifier phù hợp.

Do đó thông điệp “chạy bằng `sudo -u postgres` thì vào được, còn `-h 127.0.0.1` lại thất bại” **không phải mâu thuẫn**. Đó là hai bản ghi `pg_hba.conf` khác nhau được áp dụng.

## 13. Kiểm tra và áp dụng pg_hba.conf

PostgreSQL không tự sửa quy tắc xác thực theo lệnh `psql` mà client gửi. Nếu không thể đăng nhập vì thiếu rule, người quản trị phải chỉnh đúng file `pg_hba.conf` theo chính sách bảo mật.

Trên một phiên quản trị đủ quyền:

~~~sql
SHOW hba_file;
~~~

Để xem các bản ghi parse được và lỗi cấu hình hiện tại trên đĩa:

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
ORDER BY line_number;
~~~

View `pg_hba_file_rules` có ích để nhận diện những dòng bị lỗi cú pháp hoặc thứ tự quy tắc. Tuy nhiên, nó mô tả **nội dung file hiện có trên đĩa**, không nhất thiết chứng minh server đã nạp bản thay đổi mới nhất trong mọi tình huống. Sau khi chỉnh file, phải reload phù hợp.

Một cách yêu cầu reload qua SQL khi có quyền:

~~~sql
SELECT pg_reload_conf();
~~~

`pg_reload_conf()` gửi tín hiệu yêu cầu nạp lại cấu hình; giá trị trả về không thay thế việc xác minh log server hoặc thử kết nối mới. Những tham số thuộc loại yêu cầu restart, như `listen_addresses`, không bắt đầu có hiệu lực chỉ bằng reload.

Trong môi trường dùng `systemd` hoặc công cụ quản lý PostgreSQL riêng, có thể có lệnh service reload tương ứng. Không đoán tên service từ hệ thống khác vì tên instance và version có thể khác.

**Quy tắc quan trọng:** `pg_hba.conf` duyệt từ trên xuống. Khi sửa, hãy xác định có một dòng rộng hơn ở phía trước (ví dụ `host all all ...`) khiến dòng cụ thể bên dưới không bao giờ được chọn hay không.

## 14. Kiểm tra server đã sẵn sàng chưa bằng pg_isready

`pg_isready` là tiện ích kiểm tra PostgreSQL có đang nhận kết nối hay không; nó không thay thế xác thực và quyền truy cập vào một database cụ thể.

Kiểm tra Unix socket:

~~~bash
pg_isready -h /var/run/postgresql -p 5432
~~~

Kiểm tra TCP loopback:

~~~bash
pg_isready -h 127.0.0.1 -p 5432
~~~

Kết quả có thể cho biết server đang `accepting connections`, `rejecting connections` hoặc không phản hồi. Ví dụ server đang khởi động hoặc ở một pha khôi phục có thể chưa nhận kết nối bình thường.

**Điểm cần nhớ:** `pg_isready` báo nhận kết nối **không có nghĩa** mật khẩu của `app_user` đúng, role có `LOGIN`, database `app_db` tồn tại hay người dùng có quyền cần thiết. Sau khi kiểm tra readiness, vẫn phải thử một phiên `psql` với **đúng host, port, role và database**.

## 15. Những lỗi thường gặp với Unix socket

### 15.1. Không tìm thấy socket

Thông báo thường gặp:

~~~text
connection to server on socket
"/var/run/postgresql/.s.PGSQL.5432" failed:
No such file or directory
~~~

Các nguyên nhân có thể là:

- PostgreSQL chưa chạy.
- Server tạo Unix socket ở thư mục khác.
- Client dùng sai port nên tìm tên socket không tồn tại.
- `unix_socket_directories` bị cấu hình khác hoặc không bật socket.
- Client và server không chia sẻ cùng filesystem/socket namespace, đặc biệt trong container.

Cách kiểm tra:

~~~bash
pg_isready -h /var/run/postgresql -p 5432
~~~

Nếu còn một kết nối quản trị hợp lệ qua TCP, kiểm tra:

~~~sql
SHOW unix_socket_directories;
SHOW port;
~~~

Không kết luận ngay rằng PostgreSQL hỏng chỉ vì path mặc định của client không trùng với nơi server tạo socket.

### 15.2. Permission denied khi truy cập socket

Có thể tiến trình không có quyền đi qua thư mục cha hoặc truy cập socket theo quyền filesystem. Kiểm tra permissions của thư mục và socket, tài khoản OS của dịch vụ và ứng dụng.

PostgreSQL cung cấp các cấu hình liên quan như `unix_socket_permissions` và `unix_socket_group` trên nền tảng hỗ trợ. Không nên tùy tiện `chmod 777` toàn bộ thư mục hệ thống để “sửa nhanh”; cần cấp đúng quyền tối thiểu phù hợp với mô hình xác thực.

### 15.3. Peer authentication failed

Thông báo:

~~~text
FATAL:  Peer authentication failed for user "postgres"
~~~

Nghĩa là kết nối đã tới PostgreSQL nhưng danh tính OS không đáp ứng quy tắc `peer` cho role đó. Hãy kiểm tra `whoami`/`id` ở client, role đang yêu cầu, dòng `local` tương ứng và mapping `pg_ident.conf` nếu được cấu hình.

Không nên chuyển toàn bộ `local all all` sang `trust`, vì `trust` cho phép những client phù hợp kết nối mà không cần xác thực mật khẩu.

## 16. Những lỗi thường gặp với TCP loopback

### 16.1. Connection refused

Thông báo dạng:

~~~text
connection to server at "127.0.0.1", port 5432 failed:
Connection refused
~~~

Các khả năng:

- PostgreSQL chưa chạy hoặc không lắng nghe TCP.
- `listen_addresses` không bao gồm địa chỉ loopback đang truy cập.
- Server đang nghe cổng khác.
- Bạn đang ở network namespace khác (ví dụ container) nên `127.0.0.1` trỏ tới nơi khác.
- Chính sách mạng hoặc firewall cản trở kết nối.

Kiểm tra:

~~~bash
pg_isready -h 127.0.0.1 -p 5432
~~~

Trong phiên quản trị đang dùng được:

~~~sql
SHOW listen_addresses;
SHOW port;
~~~

Trên Linux có thể kiểm tra listener bằng `ss -ltn`. Nếu đổi `listen_addresses`, thường cần **restart** PostgreSQL để listener mới có hiệu lực.

### 16.2. No pg_hba.conf entry

Thông báo dạng:

~~~text
FATAL: no pg_hba.conf entry for host "127.0.0.1",
user "app_user", database "app_db", ...
~~~

Server đã nhận yêu cầu kết nối nhưng không tìm được rule cho loại kết nối, role, database, địa chỉ và điều kiện mã hóa phù hợp. Kiểm tra:

- Bạn đang dùng `127.0.0.1` hay `::1`.
- Rule có `host`/`hostssl` đúng địa chỉ và database không.
- Server đã reload `pg_hba.conf` sau khi chỉnh chưa.
- Có yêu cầu SSL/TLS hoặc không SSL/TLS đặc biệt hay không.
- Có dòng `reject`/rule đứng trước hoặc cấu hình rộng hơn được chọn trước không.

Không thay bằng `host all all 0.0.0.0/0 trust` để “cho thử nhanh”; điều đó có thể mở rộng bề mặt truy cập nghiêm trọng.

### 16.3. Password authentication failed

~~~text
FATAL: password authentication failed for user "app_user"
~~~

Hãy xác minh role, mật khẩu nhập, verifier tương thích với `scram-sha-256`, phương thức trên dòng `pg_hba.conf` thực sự được chọn và các quy định về credential.

Đừng dùng mật khẩu của tài khoản hệ điều hành để suy rằng mật khẩu PostgreSQL role phải giống nhau. Chúng là hai hệ thống xác thực riêng, trừ khi môi trường đã cấu hình tích hợp xác thực cụ thể.

### 16.4. Role hoặc database không tồn tại

~~~text
FATAL: role "alice" does not exist
FATAL: database "alice" does not exist
~~~

Điều này thường xảy ra khi chạy `psql` không `-U` hoặc `-d` và client lấy tên OS user làm giá trị mặc định.

Thử chỉ định rõ:

~~~bash
psql -h 127.0.0.1 -U app_user -d app_db
~~~

Nếu role/database thật sự chưa được tạo, quản trị viên phải tạo chúng và cấp quyền cần thiết theo chính sách. Chỉnh transport từ socket sang TCP không tự tạo ra role hoặc database.

## 17. Unix socket, Docker và môi trường phát triển

### 17.1. localhost bên trong container là localhost của container

Giả sử ứng dụng chạy ở **container A**, PostgreSQL chạy ở **container B**. Lệnh trong A:

~~~bash
psql -h 127.0.0.1 -p 5432 -U app_user -d app_db
~~~

sẽ tìm PostgreSQL trên **network namespace của A**, chứ không tự trỏ sang B. Trong một mạng Docker Compose, ứng dụng thường kết nối theo tên service, chẳng hạn:

~~~bash
psql -h db -p 5432 -U app_user -d app_db
~~~

Ở đây `db` là tên service giả định do Compose/network cung cấp. Đây là TCP **giữa hai container**, không còn là TCP loopback nội bộ của chính tiến trình client.

### 17.2. Muốn dùng Unix socket giữa container thì sao?

Hai container chỉ có thể dùng chung Unix-domain socket khi hệ thống thiết lập được một **đường dẫn socket có thể truy cập chung**, ví dụ qua volume/mount phù hợp, đồng thời giải quyết quyền OS, vòng đời socket và chính sách PostgreSQL. Cách này cần quản trị và không phải mặc định của Docker Compose.

Vì vậy, với ứng dụng container hóa, TCP qua service name thường đơn giản và ít phụ thuộc filesystem hơn.

### 17.3. Windows và WSL

Trên Windows, nhiều client PostgreSQL mặc định dùng TCP `localhost` thay vì Unix socket như trên Linux. Nếu ứng dụng chạy trong WSL còn PostgreSQL chạy trên Windows (hoặc ngược lại), hai môi trường có ranh giới mạng và filesystem cần xét riêng. Không được tự giả định `/var/run/postgresql` hoặc `127.0.0.1` ở một môi trường luôn trỏ tới server ở môi trường còn lại.

Hãy xác nhận nơi chạy **client**, nơi chạy **server** và cơ chế chuyển tiếp mạng thực tế trước khi sửa `pg_hba.conf`.

## 18. Kết nối từ Java/JDBC thường sử dụng TCP

Trong bối cảnh phát triển ứng dụng Java, URL PostgreSQL JDBC phổ biến có dạng:

~~~text
jdbc:postgresql://127.0.0.1:5432/app_db
~~~

Ví dụ tạo kết nối:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

String url = "jdbc:postgresql://127.0.0.1:5432/app_db";
String username = "app_user";
String password = System.getenv("DB_PASSWORD");

try (Connection connection =
         DriverManager.getConnection(url, username, password);
     PreparedStatement ps =
         connection.prepareStatement(
             "SELECT current_user, current_database(), inet_client_addr()"
         );
     ResultSet rs = ps.executeQuery()) {

    if (rs.next()) {
        System.out.println(rs.getString(1));
        System.out.println(rs.getString(2));
        System.out.println(rs.getString(3));
    }
}
~~~

Đoạn mã giả định dự án đã khai báo dependency PostgreSQL JDBC driver và có biến môi trường `DB_PASSWORD`. Trong ứng dụng production, nên quản lý credential bằng secret manager, dùng connection pool và thiết lập SSL/TLS phù hợp với mô hình triển khai.

**Điểm khác với psql trên Unix:** URL trên chỉ định `127.0.0.1` nên là **TCP**, và sẽ dùng dòng `host` trong `pg_hba.conf`. Đừng suy rằng vì bạn đăng nhập được bằng `sudo -u postgres psql` (peer qua socket) nên ứng dụng JDBC với username/password nhất định cũng đăng nhập được.

Các phương thức dùng Unix socket với pgJDBC có thể yêu cầu thêm socket factory/điều chỉnh riêng; không phải hành vi mặc định của URL TCP thông thường.

## 19. Quy tắc chọn giải pháp

Có thể ra quyết định theo câu hỏi đơn giản:

~~~mermaid
flowchart TD
    A["Client ở đâu?"] --> B{"Cùng môi trường OS với PostgreSQL?"}
    B -->|"Không"| T["TCP tới hostname/service thích hợp"]
    B -->|"Có"| C{"Có cần dùng danh tính người dùng OS?"}
    C -->|"Có, có chính sách peer"| U["Unix-domain socket + pg_hba local/peer"]
    C -->|"Không"| D{"Driver/client hỗ trợ socket rõ ràng?"}
    D -->|"Có"| E["Unix socket hoặc TCP loopback"]
    D -->|"Không / JDBC URL thông thường"| F["TCP loopback + pg_hba host"]
    T --> G["Kiểm tra listen_addresses, network, pg_hba"]
    U --> H["Kiểm tra unix_socket_directories, quyền OS, pg_hba local"]
    E --> I["Kiểm tra đường kết nối thực và xác thực"]
    F --> I
~~~

Một quy trình cấu hình thường theo thứ tự:

1. Xác định **client thực sự chạy ở đâu** và server PostgreSQL nào cần tới.
2. Xác định **transport**: Unix socket, TCP loopback hay TCP qua mạng.
3. Xác định **role, database, port** và thông tin đăng nhập.
4. Kiểm tra server có đang lắng nghe đúng socket/địa chỉ hay không.
5. Kiểm tra dòng `pg_hba.conf` đầu tiên khớp kết nối và cơ chế xác thực tương ứng.
6. Dùng `pg_isready` để kiểm tra khả năng nhận kết nối.
7. Dùng `psql` hoặc ứng dụng thật để thử xác thực, rồi dùng `\conninfo`/`inet_client_addr()` xác nhận transport.
8. Áp dụng **nguyên tắc quyền tối thiểu**, không mở listener rộng hay dùng `trust` chỉ để tránh lỗi cấu hình.

## 20. Bài tập thực hành

### Bài tập 1: Nhận diện transport

Chạy hai lệnh trên máy Linux có PostgreSQL:

~~~bash
psql -U app_user -d app_db
psql -h 127.0.0.1 -U app_user -d app_db
~~~

Hãy xác định lệnh nào dùng Unix socket theo mặc định, lệnh nào dùng TCP. Lưu ý lệnh đầu có thể bị biến môi trường `PGHOST` làm thay đổi hành vi; nếu cần kết quả không mơ hồ, đặt rõ `-h /đường/dẫn/socket`.

### Bài tập 2: Vì sao peer và SCRAM cho kết quả khác?

Giả sử `pg_hba.conf` có:

~~~conf
local   all   postgres                  peer
host    all   postgres   127.0.0.1/32   scram-sha-256
~~~

Người dùng OS `alice` thử `psql -U postgres -d postgres` và nhận lỗi peer. Khi thêm `-h 127.0.0.1`, client được hỏi mật khẩu. Giải thích: **đổi transport làm thay đổi loại dòng `pg_hba.conf` được chọn**, chứ không đổi role PostgreSQL.

### Bài tập 3: localhost chọn địa chỉ nào?

Thử:

~~~bash
psql -h localhost -U app_user -d app_db
psql -h 127.0.0.1 -U app_user -d app_db
psql -h ::1 -U app_user -d app_db
~~~

Khi kết nối được, chạy:

~~~sql
SELECT inet_client_addr(), inet_server_addr();
~~~

Đối chiếu địa chỉ với các rule `127.0.0.1/32` và `::1/128`. Không mặc định môi trường nào cũng bật IPv6.

### Bài tập 4: Phân biệt lỗi server với lỗi xác thực

Nếu `pg_isready -h 127.0.0.1 -p 5432` báo `accepting connections`, nhưng `psql -h 127.0.0.1 -U app_user -d app_db` báo “password authentication failed”, nên kiểm tra điều gì?

**Đáp án:** server đã nhận kết nối ở mức giao thức; cần kiểm tra credential của `app_user`, phương thức `scram-sha-256`, rule thực sự khớp, mật khẩu role và cấu hình có liên quan. Không nên khởi động lại server như bước đầu tiên khi lỗi thực sự là mật khẩu.

### Bài tập 5: Sửa lỗi socket path

Lệnh `psql -h /tmp -p 5432 ...` báo “No such file or directory”, nhưng kết nối TCP `-h 127.0.0.1` thành công. Hãy chạy `SHOW unix_socket_directories;` từ phiên TCP và tìm đường dẫn socket thật. Nếu socket đặt ở `/var/run/postgresql`, thử lại với `-h /var/run/postgresql`.

### Bài tập 6: Nhận diện lỗi container

Ứng dụng ở container `web`, PostgreSQL ở container `db`. Tại sao `-h 127.0.0.1` trong container `web` không kết nối được `db`?

**Đáp án:** `127.0.0.1` là loopback của container `web`; phải dùng địa chỉ/tên service mà network của hệ thống cung cấp, ví dụ `-h db` khi Docker Compose network được cấu hình phù hợp.

## 21. Tổng kết

**Unix-domain socket** và **TCP loopback** đều có thể giúp một client truy cập PostgreSQL trên cùng máy, nhưng chúng là **hai đường truyền khác nhau**:

- Unix socket dùng đường dẫn thư mục và quy tắc `local` trong `pg_hba.conf`, có thể dùng xác thực `peer` dựa vào người dùng hệ điều hành.
- TCP loopback dùng `127.0.0.1` hoặc `::1`, phụ thuộc `listen_addresses` và quy tắc `host` trong `pg_hba.conf`; thường dùng SCRAM password cho tài khoản ứng dụng.
- Cùng một PostgreSQL role có thể vào được bằng một cách mà thất bại bằng cách kia vì **đường truyền, quy tắc xác thực và danh tính client** khác nhau.

Khi gặp lỗi kết nối, hãy kiểm tra theo thứ tự **đúng server → đúng transport → đúng địa chỉ/socket và port → đúng rule pg_hba → đúng role/database/password**. Cách tiếp cận này giúp xử lý sự cố có hệ thống, không cần nới lỏng bảo mật PostgreSQL một cách tùy tiện.
