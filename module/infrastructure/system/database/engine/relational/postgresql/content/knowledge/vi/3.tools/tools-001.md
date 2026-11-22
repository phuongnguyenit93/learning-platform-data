# Kết nối bằng psql và cấu trúc chuỗi kết nối trong PostgreSQL

Sau khi cài PostgreSQL, công việc đầu tiên thường là kết nối tới **đúng máy chủ, đúng cổng, đúng cơ sở dữ liệu và đúng vai trò đăng nhập**. PostgreSQL cung cấp công cụ dòng lệnh `psql` để thực hiện việc này. Ngoài các tùy chọn quen thuộc như `-h`, `-p`, `-U` và `-d`, `psql` còn chấp nhận **chuỗi kết nối** (*connection string*) theo định dạng của thư viện **libpq**: danh sách `key=value` hoặc URI `postgresql://...`.

Việc hiểu chuỗi kết nối giúp bạn:

- Đăng nhập vào PostgreSQL cục bộ hoặc một server trong mạng.
- Phân biệt kết nối Unix socket và kết nối TCP/IP.
- Chuyển cấu hình kết nối giữa terminal, script, container và môi trường phát triển.
- Thiết lập thời gian chờ, tên ứng dụng và yêu cầu TLS.
- Tránh để lộ mật khẩu trong lịch sử lệnh, file cấu hình hoặc log.
- Chẩn đoán lỗi do sai máy chủ, sai database, thiếu quyền hay phương thức xác thực không phù hợp.

Bài học dùng PostgreSQL hiện đại và các ví dụ có thể áp dụng trên Linux, Windows và macOS. Mọi địa chỉ, role và database minh họa đều cần thay theo môi trường của bạn. Các ví dụ không yêu cầu kết nối tới một server Internet công khai.

## 1. Phân biệt psql, libpq, PostgreSQL server và database

`psql` là chương trình **client**. Nó không tự vận hành storage engine hay lưu bảng dữ liệu; nó mở kết nối đến một tiến trình **PostgreSQL server** đang chạy. Thư viện **libpq** chịu trách nhiệm xử lý tham số kết nối, mở phiên, thương lượng xác thực và trao đổi theo giao thức PostgreSQL.

```mermaid
flowchart LR
    A["Người dùng / Terminal"] --> B["psql client"]
    B --> C["libpq: host, port, dbname, user, TLS..."]
    C --> D["PostgreSQL server"]
    D --> E["Database learning_pg"]
    E --> F["Schema và bảng"]
```

Một kết nối thường có những thông tin:

| Thông tin | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Host | `127.0.0.1` hoặc `db.internal.example` | Địa chỉ **server PostgreSQL**, không phải địa chỉ trình duyệt người dùng |
| Port | `5432` | Cổng TCP PostgreSQL lắng nghe |
| Database | `learning_pg` | Database sẽ mở phiên |
| User | `learning_app` | Role PostgreSQL dùng để xác thực |
| Password / auth | Mật khẩu, peer hoặc phương thức phù hợp | Chứng minh danh tính theo cấu hình xác thực |
| TLS mode | `verify-full` | Quy định yêu cầu bảo mật đường truyền |
| Application name | `psql_lab` | Nhận diện loại client trong công cụ giám sát |
| Connect timeout | `5` giây | Giới hạn thời gian thử thiết lập kết nối |

**Server, database và schema không phải cùng một khái niệm.** Một PostgreSQL instance có thể quản lý nhiều database; mỗi database lại có nhiều schema và bảng. Khi kết nối, libpq cần chọn một database ban đầu. Bạn không thể truy vấn trực tiếp bảng của database khác chỉ bằng cách viết `other_database.public.table` như cú pháp truy vấn bảng trong cùng database.

### 1.1. Điều kiện để một kết nối thành công

Một lần kết nối phải vượt qua nhiều bước độc lập:

```mermaid
flowchart TD
    A["psql nhận các tham số"] --> B{"Có thể tiếp cận host và port/socket?"}
    B -->|Không| C["Lỗi mạng, cổng hoặc server"]
    B -->|Có| D{"pg_hba.conf cho phép kiểu kết nối?"}
    D -->|Không| E["Lỗi quy tắc xác thực"]
    D -->|Có| F{"Xác thực user thành công?"}
    F -->|Không| G["Lỗi mật khẩu/peer/chứng thực"]
    F -->|Có| H{"Database tồn tại, được phép CONNECT?"}
    H -->|Không| I["Lỗi database hoặc quyền"]
    H -->|Có| J["Phiên sẵn sàng chạy SQL"]
```

Kết nối thành công **không có nghĩa** user được `SELECT` hoặc `INSERT` trên mọi bảng. PostgreSQL còn kiểm tra quyền ở cấp database, schema, bảng, sequence, function và đối tượng liên quan khi thực hiện SQL.

## 2. Kiểm tra công cụ và server trước khi kết nối

Trong terminal Linux/macOS:

```bash
psql --version
```

Trên Windows PowerShell, nếu `psql.exe` đã nằm trong `PATH`:

```powershell
psql --version
```

Nếu chưa có trong `PATH` và bạn cài PostgreSQL vào một thư mục điển hình, có thể gọi bằng đường dẫn đầy đủ (ví dụ phiên bản 18):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" --version
```

Số `18` là ví dụ về **major version**; đường dẫn thực tế phụ thuộc bản cài của bạn.

`psql --version` chỉ cho biết **phiên bản client**. Để biết server đang kết nối là phiên bản nào, sau khi đăng nhập hãy chạy:

```sql
SELECT version();
SHOW server_version;
```

Hai phiên bản có thể khác nhau; không nên suy luận server đã được nâng cấp chỉ từ phiên bản binary `psql`.

Nếu có `pg_isready`, có thể thử server tại một endpoint:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

`pg_isready` giúp kiểm tra server có phản hồi và có vẻ sẵn sàng nhận kết nối hay không; nó **không chứng minh** một cặp username/password cụ thể sẽ đăng nhập thành công hoặc có quyền SQL.

## 3. Cách kết nối cơ bản bằng các tùy chọn psql

Cú pháp thông dụng:

```text
psql -h <host> -p <port> -U <user> -d <database>
```

Đây là khuôn mẫu, không phải lệnh chạy nguyên văn. Các dấu `<...>` biểu thị giá trị bạn cần cung cấp.

### 3.1. Kết nối TCP tới server local

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg
```

| Tùy chọn | Tên dài tương ứng | Chức năng |
| --- | --- | --- |
| `-h 127.0.0.1` | `--host=127.0.0.1` | Chọn host đích hoặc đường dẫn Unix socket directory |
| `-p 5432` | `--port=5432` | Chọn cổng |
| `-U learning_app` | `--username=learning_app` | Chọn role đăng nhập |
| `-d learning_pg` | `--dbname=learning_pg` | Chọn database |
| `-W` | `--password` | Chủ động yêu cầu prompt nhập mật khẩu |
| `-w` | `--no-password` | Không hỏi mật khẩu tương tác; hữu ích cho automation có cơ chế secret khác |

Ví dụ buộc prompt mật khẩu:

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg -W
```

**`-W` không nhận mật khẩu làm đối số.** Khi có `-W`, `psql` yêu cầu bạn nhập mật khẩu vào prompt. Không có `-W`, libpq vẫn có thể yêu cầu mật khẩu khi server đòi hỏi và không có nguồn thông tin xác thực khác.

Không dùng `psql -W my_password` để truyền mật khẩu: `my_password` không phải đối số hợp lệ của `-W`. Tránh đưa mật khẩu vào command line hoặc URL vì shell history, công cụ giám sát process và log có thể làm lộ bí mật.

### 3.2. Kết nối tới server trong mạng

```bash
psql -h db.internal.example -p 5432 -U report_reader -d reporting
```

Ví dụ giả định tổ chức có hostname nội bộ `db.internal.example`. Để kết nối thành công, server cần lắng nghe ở địa chỉ mạng phù hợp, firewall cho phép nguồn client, `pg_hba.conf` có quy tắc xác thực thích hợp và role được cấp quyền `CONNECT` tới database.

**Không mở cổng PostgreSQL trực tiếp ra Internet công cộng** chỉ để làm thử nghiệm. Đối với server từ xa, ưu tiên private network/VPN hoặc đường truy cập có bảo vệ, kết hợp TLS và quyền tối thiểu.

### 3.3. Kết nối không ghi đủ tham số

Có thể gõ ngắn gọn:

```bash
psql
```

Tuy nhiên, cách này phụ thuộc vào các giá trị mặc định của libpq, biến môi trường và hệ điều hành:

- User mặc định thường là **tên user hệ điều hành đang chạy `psql`**, nếu không có cấu hình ghi đè.
- Database mặc định thường mang **cùng tên với user đăng nhập**.
- Trên hệ Unix, khi không chỉ định `host`, libpq thường thử **Unix-domain socket** trong thư mục được cấu hình khi build.
- Trên Windows, cách kết nối mặc định có thể khác; không giả định Windows hỗ trợ cùng đường socket với Linux.
- Port mặc định thường là **5432**, trừ khi cấu hình/build hoặc môi trường ghi đè.

Vì vậy, `psql` không tham số có thể báo `role "alice" does not exist` hoặc `database "alice" does not exist` dù PostgreSQL đã cài đúng. Trong bài học và script nên chỉ rõ `-h`, `-p`, `-U`, `-d` để tránh phụ thuộc môi trường ngầm.

## 4. Kết nối local bằng Unix socket so với TCP

Trên Linux/macOS, PostgreSQL có thể cho client local kết nối qua **Unix-domain socket**. Kết nối này không sử dụng cùng luồng TCP với `127.0.0.1:5432`.

Ví dụ trên một bản Linux có socket ở thư mục phù hợp:

```bash
# Có thể dùng Unix socket với thư mục socket cụ thể:
psql -h /var/run/postgresql -U postgres -d postgres

# Ép TCP loopback IPv4:
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

Thư mục `/var/run/postgresql` phổ biến trên một số bản Linux nhưng **không cố định trên mọi hệ điều hành**. Nếu bỏ `-h`, libpq dùng đường socket mặc định được cấu hình trong bản cài. Trên Ubuntu/Debian, có thể đăng nhập role quản trị qua peer bằng:

```bash
sudo -iu postgres psql -d postgres
```

So sánh:

| Kết nối | Đường truyền | Cấu hình xác thực thường được xét |
| --- | --- | --- |
| Không có `-h` trên Unix | Unix socket theo mặc định của libpq | Quy tắc `local` trong `pg_hba.conf` |
| `-h /path/to/socket_dir` | Unix socket ở thư mục chỉ định | Quy tắc `local` |
| `-h 127.0.0.1` | TCP IPv4 loopback | Quy tắc `host`/`hostssl` phù hợp |
| `-h ::1` | TCP IPv6 loopback | Quy tắc host cho IPv6 |
| `-h db.internal.example` | TCP tới máy server được DNS phân giải | Quy tắc host theo IP nguồn và chế độ TLS |

Một role có thể đăng nhập qua socket với `peer` nhưng không đăng nhập được qua TCP khi chưa đặt mật khẩu. **Không kết luận máy chủ “lúc được lúc không”** trước khi phân biệt giao thức và quy tắc `pg_hba.conf` tương ứng.

## 5. Chuỗi kết nối là gì?

Thay vì tách các tham số thành nhiều tùy chọn CLI, có thể gom chúng thành một **connection string**. `psql` sử dụng quy tắc chuỗi kết nối của **libpq**, khác với cú pháp JDBC URL của ứng dụng Java ở một số điểm.

Hai dạng phổ biến là:

1. **Keyword/value:** `host=... port=... dbname=... user=...`.
2. **URI:** `postgresql://user@host:port/database?parameter=value`.

Cả hai đều mô tả cùng một điểm kết nối nhưng có quy tắc escape khác nhau.

## 6. Dạng keyword/value của libpq

Một connection string có thể viết thành các cặp `tên_tham_số=giá_trị`, phân cách bởi khoảng trắng:

```bash
psql "host=127.0.0.1 port=5432 dbname=learning_pg user=learning_app"
```

Hoặc ghi rõ vào tùy chọn `-d`:

```bash
psql --dbname="host=127.0.0.1 port=5432 dbname=learning_pg user=learning_app connect_timeout=5 application_name=psql_lab"
```

Ở đây:

- `host` chọn server.
- `port` chọn cổng.
- `dbname` chọn database.
- `user` chọn role đăng nhập.
- `connect_timeout=5` giới hạn thời gian thiết lập kết nối (giây).
- `application_name=psql_lab` giúp nhận diện client trong `pg_stat_activity`.

Tên tham số libpq khác với một số tên option của CLI: ví dụ `dbname` trong connection string tương ứng với `-d` của `psql`.

### 6.1. Khi giá trị chứa khoảng trắng hoặc ký tự đặc biệt

Trong dạng keyword/value, giá trị có khoảng trắng có thể được bao trong **dấu nháy đơn** bên trong chuỗi:

```bash
psql "host=127.0.0.1 port=5432 dbname='training space' user=learning_app"
```

Ví dụ chỉ chạy được khi database thật có tên `training space`; tên có khoảng trắng thường không được khuyến khích trong môi trường học. Quy tắc libpq cho phép escape dấu nháy đơn và ký tự gạch chéo ngược bằng backslash khi cần.

Hãy phân biệt hai lớp quoting:

- **Shell quoting**: dấu `"..."` bên ngoài bảo đảm terminal truyền connection string thành một đối số.
- **Libpq quoting**: dấu `'...'` bên trong bảo đảm một giá trị có khoảng trắng được phân tích thành đúng một tham số.

Nếu một tham số bị ghi đè do kết hợp `-d` connection string với các option CLI khác, không nên dựa vào thứ tự mơ hồ; hãy chọn **một nguồn cấu hình rõ ràng** cho mỗi tham số trong script.

### 6.2. Các tham số libpq thường gặp

| Tham số | Ví dụ | Tác dụng |
| --- | --- | --- |
| `host` | `db.internal.example` | Hostname server hoặc thư mục Unix socket |
| `hostaddr` | `192.0.2.10` | Địa chỉ IP đích cụ thể, có thể tránh DNS lookup |
| `port` | `5432` | Cổng kết nối |
| `dbname` | `learning_pg` | Database đích |
| `user` | `learning_app` | Role đăng nhập |
| `connect_timeout` | `5` | Timeout kết nối tính bằng giây |
| `application_name` | `psql_lab` | Nhãn ứng dụng |
| `sslmode` | `verify-full` | Chính sách TLS |
| `sslrootcert` | `/path/to/ca.crt` | CA/trust material dùng xác thực chứng chỉ server |
| `passfile` | `/secure/path/pgpass` | Đường dẫn file mật khẩu libpq |
| `service` | `training` | Chọn cấu hình từ service file |
| `target_session_attrs` | `read-write` | Tiêu chí chọn server khi dùng nhiều host |
| `options` | Các tùy chọn khởi tạo session hợp lệ | Gửi thiết lập phiên được server hỗ trợ |

Không phải tham số nào cũng cần thiết cho kết nối local. Tốt nhất là bắt đầu bằng `host`, `port`, `dbname`, `user`, rồi chỉ thêm những tham số phục vụ yêu cầu cụ thể.

## 7. Dạng URI: postgresql://

Libpq hỗ trợ URI theo cấu trúc:

```text
postgresql://[user[:password]@][host][:port][/dbname][?param1=value1&param2=value2]
```

Đây là cấu trúc minh họa, các đoạn trong dấu `[...]` là tùy chọn. Trong câu lệnh chạy thực tế, **không gõ nguyên các dấu ngoặc vuông** này.

Ví dụ đơn giản:

```bash
psql "postgresql://learning_app@127.0.0.1:5432/learning_pg"
```

Tương đương về những trường thông tin cơ bản với:

```bash
psql "host=127.0.0.1 port=5432 dbname=learning_pg user=learning_app"
```

### 7.1. Thêm tham số ở query string

```bash
psql 'postgresql://learning_app@db.internal.example:5432/learning_pg?sslmode=verify-full&connect_timeout=5&application_name=psql_lab'
```

Giải thích:

| Thành phần của URI | Giá trị | Ý nghĩa |
| --- | --- | --- |
| Scheme | `postgresql://` | Sử dụng giao thức chuỗi kết nối PostgreSQL |
| Userinfo | `learning_app@` | Role PostgreSQL đăng nhập |
| Host | `db.internal.example` | Server đích |
| Port | `:5432` | Cổng TCP |
| Path | `/learning_pg` | Tên database |
| Query | `sslmode=verify-full` | Yêu cầu TLS và xác minh danh tính host |
| Query | `connect_timeout=5` | Timeout thiết lập kết nối |
| Query | `application_name=psql_lab` | Nhãn client |

Libpq cũng chấp nhận scheme `postgres://` ở những phiên bản phổ biến. Khi viết tài liệu nội bộ, nên dùng thống nhất `postgresql://` để dễ nhận biết.

**Lưu ý về dấu `&`:** trên nhiều shell, `&` có ý nghĩa điều khiển lệnh. Hãy bao **toàn bộ URI** trong dấu nháy thích hợp như ví dụ, thay vì dán URI có nhiều query parameter mà không quote.

### 7.2. Percent-encoding trong URI

Ký tự đặc biệt trong user, password, tên database hoặc tham số URL phải được **percent-encode** theo quy tắc URI. Một số ví dụ:

| Ký tự gốc | Dạng encoded |
| --- | --- |
| Khoảng trắng | `%20` |
| `@` | `%40` |
| `:` | `%3A` |
| `/` | `%2F` |
| `?` | `%3F` |
| `#` | `%23` |
| `%` | `%25` |

Ví dụ database thật có tên `training space` thì path của URI phải được encode:

```text
postgresql://learning_app@localhost:5432/training%20space
```

Nếu tên user có ký tự `@`, nó cũng phải encode trong phần userinfo. Không tự viết một URI có password chứa `@` hoặc `#` nguyên văn rồi giả định client phân tích đúng phần host.

Đặc biệt, **không khuyến khích đặt mật khẩu trực tiếp vào URI**:

```text
# CHỈ MINH HỌA CÚ PHÁP, KHÔNG ĐƯỢC DÙNG CÁCH NÀY ĐỂ LƯU MẬT KHẨU THẬT:
postgresql://learning_app:EXAMPLE_PASSWORD@localhost:5432/learning_pg
```

URI mang mật khẩu có thể rò rỉ qua shell history, biến cấu hình được in trong log, công cụ quan sát process, URL được sao chép hoặc hệ thống giám sát. Ưu tiên prompt, passfile hoặc một secret manager phù hợp.

### 7.3. URI khác JDBC URL của Java

Đừng dùng `jdbc:postgresql://...` nguyên văn cho `psql`:

```text
# Libpq / psql:
postgresql://learning_app@localhost:5432/learning_pg

# PostgreSQL JDBC (ứng dụng Java):
jdbc:postgresql://localhost:5432/learning_pg
```

Cả hai cùng mô tả kết nối PostgreSQL nhưng do **hai driver khác nhau** phân tích. Tên, giá trị và khả năng hỗ trợ một số connection parameter có thể khác nhau; hãy xem tài liệu libpq khi dùng `psql` và tài liệu PostgreSQL JDBC khi dùng Java.

## 8. Tạo môi trường thực hành để kiểm tra kết nối

Nếu bạn chưa có role/database mẫu, hãy tạo chúng trên **instance PostgreSQL đang học**, thông qua một phiên `psql` với role có quyền `CREATEROLE` và `CREATEDB` hoặc quyền quản trị tương ứng.

Ví dụ trên Linux với các gói distro thường tạo OS user `postgres`:

```bash
sudo -iu postgres psql -d postgres
```

Trên Windows, macOS hoặc máy có cấu hình riêng, dùng role quản trị đã được thiết lập; không phải hệ thống nào cũng có cách đăng nhập như trên. Trong phiên psql quản trị, chạy:

```sql
CREATE ROLE learning_app LOGIN;

CREATE DATABASE learning_pg OWNER learning_app;
```

Đặt mật khẩu cho role bằng meta-command của `psql`:

```text
\password learning_app
```

`\password` sẽ hỏi mật khẩu mới và xác nhận theo luồng của `psql`, giúp tránh đưa mật khẩu thật vào một lệnh `ALTER ROLE ... PASSWORD '...'` nằm trong lịch sử SQL. Trong môi trường thực tế, dùng mật khẩu mạnh, duy nhất và lưu bằng cơ chế quản lý bí mật.

**`CREATE DATABASE` phải chạy ngoài transaction block.** Trong chế độ mặc định của psql, lệnh này chạy riêng được; không bọc nó trong `BEGIN; ... COMMIT;`.

Sau đó thoát phiên quản trị:

```text
\q
```

Đăng nhập role mới bằng TCP:

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg -W
```

Nếu server chỉ cho phép xác thực local bằng phương thức khác hoặc port không phải 5432, cần điều chỉnh đúng cấu hình. Đừng đổi `pg_hba.conf` sang `trust` để bỏ qua lỗi mật khẩu.

### 8.1. Xác minh phiên thực tế sau khi đăng nhập

Trong `psql`:

```sql
SELECT
    current_user AS effective_role,
    session_user AS login_role,
    current_database() AS database_name,
    current_schema() AS schema_name;

SHOW server_version;
SHOW port;
```

Sau đó:

```text
\conninfo
```

`\conninfo` hiển thị thông tin kết nối hiện tại như database, user, host/socket và cổng; ở kết nối được bảo vệ TLS, công cụ cũng có thể cho biết thông tin SSL phù hợp với phiên bản client.

**Lưu ý:** `current_user` có thể thay đổi theo `SET ROLE` hoặc ngữ cảnh thực thi code sử dụng quyền khác; `session_user` gắn với user của phiên đăng nhập theo ngữ nghĩa PostgreSQL. Khi chẩn đoán quyền, nên xem cả hai nếu ứng dụng sử dụng role switching.

## 9. Các meta-command psql quan trọng

Khi phiên `psql` đã kết nối, các lệnh bắt đầu bằng `\` là **meta-command của client**, không phải câu SQL do server trực tiếp phân tích.

| Meta-command | Tác dụng |
| --- | --- |
| `\conninfo` | Hiển thị thông tin kết nối |
| `\l` | Liệt kê database mà user được phép xem |
| `\du` | Liệt kê role và thuộc tính |
| `\dn` | Liệt kê schema |
| `\dt` | Liệt kê bảng có thể thấy theo search path/pattern |
| `\d products` | Xem định nghĩa bảng `products` |
| `\c learning_pg` | Chuyển kết nối sang database `learning_pg` |
| `\c learning_pg learning_app 127.0.0.1 5432` | Kết nối lại với database/user/host/port chỉ định |
| `\timing on` | Hiển thị thời gian chạy câu lệnh |
| `\x auto` | Tự chọn chế độ hiển thị kết quả mở rộng khi phù hợp |
| `\pset pager off` | Tắt pager cho kết quả dài |
| `\?` | Trợ giúp meta-command |
| `\h SELECT` | Trợ giúp cú pháp SQL của `SELECT` |
| `\q` | Thoát psql |

Ví dụ:

```text
learning_pg=> \conninfo
learning_pg=> \dt
learning_pg=> \timing on
learning_pg=> \x auto
learning_pg=> \q
```

`learning_pg=>` là dấu nhắc minh họa, **không phải phần bạn cần gõ**.

### 9.1. Thay đổi database bằng \connect

```text
\connect postgres
```

Lệnh chuyển sang database `postgres` bằng thông tin kết nối được cung cấp hoặc tái sử dụng theo quy tắc của psql. Sau khi kết nối lại, cần kiểm tra `\conninfo`, đặc biệt nếu bạn đồng thời đổi host, user hoặc cổng.

Một transaction đang hoạt động không thể được “mang nguyên” sang database khác qua thao tác kết nối lại. Nên hoàn tất hoặc rollback transaction trước khi dùng `\connect`.

### 9.2. Thử một truy vấn đơn giản

```sql
SELECT
    current_database() AS db_name,
    current_user AS role_name,
    now() AS server_transaction_time;
```

Câu SQL kết thúc bằng dấu `;`. Trong psql, dòng nhập chưa kết thúc có thể được giữ trong bộ đệm cho đến khi bạn gửi một lệnh hoàn chỉnh. Khi lỡ nhập sai nội dung, meta-command `\r` có thể xóa bộ đệm câu lệnh hiện tại; `\q` thoát chương trình.

## 10. Biến môi trường kết nối của libpq

Để tránh gõ lại tham số thường xuyên, libpq có các **environment variables**. Chúng hữu ích trong môi trường phát triển, script và container, nhưng cần được sử dụng có kiểm soát.

| Biến | Tương ứng với | Ví dụ |
| --- | --- | --- |
| `PGHOST` | `host` | `127.0.0.1` |
| `PGPORT` | `port` | `5432` |
| `PGUSER` | `user` | `learning_app` |
| `PGDATABASE` | `dbname` | `learning_pg` |
| `PGCONNECT_TIMEOUT` | `connect_timeout` | `5` |
| `PGAPPNAME` | `application_name` | `psql_lab` |
| `PGSSLMODE` | `sslmode` | `verify-full` |
| `PGSSLROOTCERT` | `sslrootcert` | Đường dẫn CA certificate |
| `PGSERVICE` | `service` | `learning_local` |
| `PGPASSFILE` | `passfile` | Đường dẫn file mật khẩu |
| `PGPASSWORD` | `password` | Có hỗ trợ nhưng không nên dùng như cách mặc định lưu bí mật |

Trên Linux/macOS, thiết lập cho phiên terminal hiện tại:

```bash
export PGHOST=127.0.0.1
export PGPORT=5432
export PGUSER=learning_app
export PGDATABASE=learning_pg
export PGCONNECT_TIMEOUT=5

psql -W
```

Trên Windows PowerShell:

```powershell
$env:PGHOST = "127.0.0.1"
$env:PGPORT = "5432"
$env:PGUSER = "learning_app"
$env:PGDATABASE = "learning_pg"
$env:PGCONNECT_TIMEOUT = "5"

psql -W
```

Các biến môi trường này chỉ áp dụng cho **môi trường tiến trình** tương ứng; đổi chúng không tự đổi cấu hình server hay role. Tham số được truyền tường minh trong chuỗi kết nối/option có thể ghi đè các mặc định môi trường theo quy tắc libpq.

### 10.1. Không dùng PGPASSWORD làm nơi lưu mật khẩu dài hạn

`PGPASSWORD` là một cơ chế được libpq nhận biết nhưng có nhược điểm: biến môi trường có thể xuất hiện trong công cụ quan sát tiến trình, crash report, hệ thống debug hoặc log cấu hình tùy nền tảng và quyền. Nếu có thể, ưu tiên:

1. Prompt `-W` khi thao tác thủ công.
2. Password file do libpq hỗ trợ, có quyền file chặt chẽ.
3. Secret manager/credential store của hệ thống triển khai.
4. Các cơ chế xác thực khác được tổ chức cho phép và quản lý.

Không lưu password thật vào file shell profile hoặc commit cấu hình bí mật lên Git.

## 11. Dùng .pgpass/pgpass.conf để không nhập mật khẩu lặp lại

Libpq hỗ trợ **password file** để lưu thông tin xác thực cho các kết nối phù hợp. Đây là cách thuận tiện cho script, nhưng file phải được bảo vệ cẩn thận.

Vị trí mặc định thường là:

| Nền tảng | Vị trí password file |
| --- | --- |
| Linux/macOS | `~/.pgpass` |
| Windows | `%APPDATA%\postgresql\pgpass.conf` |

Mỗi dòng có cấu trúc:

```text
hostname:port:database:username:password
```

Ví dụ giả định (không dùng mật khẩu minh họa trong thực tế):

```text
127.0.0.1:5432:learning_pg:learning_app:REPLACE_WITH_REAL_SECRET
db.internal.example:5432:reporting:report_reader:REPLACE_WITH_ANOTHER_SECRET
```

Libpq chọn dòng **phù hợp đầu tiên**. Dấu `*` có thể đại diện cho nhiều giá trị nhưng làm phạm vi khớp rộng hơn; chỉ dùng khi thực sự cần. Trong password file, dấu hai chấm và backslash thuộc một giá trị cần escape bằng backslash theo quy tắc file.

Trên Unix, file cần có quyền truy cập đủ chặt, thường:

```bash
chmod 600 ~/.pgpass
```

Libpq có thể **bỏ qua** password file trên Unix nếu quyền của file quá rộng. Trên Windows, cơ chế kiểm soát quyền file dựa vào Windows ACL; phải giới hạn quyền truy cập vào file chứa secret.

Sau khi có file hợp lệ, lệnh:

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg
```

có thể sử dụng mật khẩu được tìm thấy mà không cần prompt. Nếu file không khớp, hết hiệu lực hoặc quyền file không phù hợp, kết nối có thể vẫn yêu cầu nhập mật khẩu hoặc thất bại, tùy tùy chọn tương tác.

### 11.1. Dùng đường dẫn passfile riêng

Có thể chọn password file khác thông qua `PGPASSFILE` hoặc tham số `passfile` trong libpq connection string:

```bash
psql "host=db.internal.example port=5432 dbname=reporting user=report_reader passfile=/secure/path/to/pgpass"
```

Đường dẫn trong ví dụ cần thay bằng file thực tế; trên Windows dùng đường dẫn Windows phù hợp. Việc có passfile **không tự mã hóa file ở trạng thái lưu trữ**. Phải bảo vệ cả file, bản sao lưu và tài khoản hệ điều hành có thể đọc nó.

## 12. Dùng service file để tái sử dụng nhiều cấu hình

Khi cần kết nối thường xuyên tới nhiều môi trường như development, staging, reporting, bạn có thể định nghĩa các kết nối trong **libpq service file**.

Một số vị trí thường gặp:

- Linux/macOS: `~/.pg_service.conf`.
- Windows: file dịch vụ trong thư mục cấu hình PostgreSQL thuộc `%APPDATA%`, thường là `%APPDATA%\postgresql\.pg_service.conf`.
- Có thể chỉ rõ đường dẫn bằng biến môi trường `PGSERVICEFILE`.

Ví dụ nội dung service file:

```ini
[learning_local]
host=127.0.0.1
port=5432
dbname=learning_pg
user=learning_app
connect_timeout=5
application_name=learning_psql

[reporting_internal]
host=db.internal.example
port=5432
dbname=reporting
user=report_reader
connect_timeout=5
sslmode=verify-full
sslrootcert=/secure/path/company-ca.crt
```

Đường dẫn CA certificate cần thay bằng đường dẫn thực trên hệ điều hành dùng service file. Không đặt mật khẩu thật trực tiếp trong file này nếu không có cơ chế bảo vệ phù hợp; có thể ghép với passfile hoặc secret manager.

Kết nối qua tên service:

```bash
psql "service=learning_local"
```

Hoặc:

```bash
psql "service=reporting_internal"
```

Service file giúp script ít phụ thuộc tên host/port cụ thể hơn và làm cấu hình rõ ràng hơn. Tuy nhiên, khi thay đổi service file hoặc `PGSERVICEFILE`, cần xác nhận script đang đọc đúng cấu hình; không chỉ dựa vào tên service giống nhau ở các máy.

## 13. Kết nối an toàn với TLS

Kết nối TCP PostgreSQL có thể được bảo vệ bằng **TLS**. Với server trong mạng không hoàn toàn đáng tin cậy, cần vừa bảo vệ dữ liệu truyền đi vừa xác minh danh tính server.

Libpq có các chế độ `sslmode` phổ biến:

| `sslmode` | Ý nghĩa khái quát | Lưu ý |
| --- | --- | --- |
| `disable` | Không yêu cầu TLS | Chỉ cân nhắc ở môi trường được kiểm soát rõ |
| `allow` | Cho phép thử không TLS trước rồi thử TLS khi cần | Không thích hợp khi chính sách yêu cầu TLS |
| `prefer` | Ưu tiên TLS nhưng có thể chấp nhận không TLS | Thường là mặc định libpq; không bảo đảm TLS bắt buộc |
| `require` | Yêu cầu kết nối được mã hóa bằng TLS | Không đủ để khẳng định đã xác minh đúng hostname server |
| `verify-ca` | TLS và xác minh chứng chỉ bằng CA tin cậy | Chưa kiểm tra tên hostname như `verify-full` |
| `verify-full` | TLS, xác minh CA và tên server | Nên ưu tiên khi kết nối tới máy chủ từ xa có certificate phù hợp |

Ví dụ URI yêu cầu xác thực danh tính server:

```bash
psql 'postgresql://report_reader@db.internal.example:5432/reporting?sslmode=verify-full&connect_timeout=5'
```

Ví dụ này chỉ thành công khi server hỗ trợ TLS, certificate hợp lệ với hostname `db.internal.example`, và client có trust material phù hợp, chẳng hạn CA certificate được cấu hình bằng `sslrootcert` hoặc `PGSSLROOTCERT` theo chính sách.

**Không mặc định `sslmode=require` tương đương xác thực đầy đủ danh tính server.** Trong một số cấu hình/tính tương thích, sự có mặt của root CA file có thể ảnh hưởng hành vi xác minh; để diễn đạt yêu cầu rõ ràng, hãy dùng `verify-full` và cấu hình CA phù hợp.

### 13.1. Kiểm tra kết nối có SSL hay không

Khi đang ở `psql`, chạy:

```text
\conninfo
```

Bạn cũng có thể dùng view hệ thống nếu có quyền:

```sql
SELECT
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_ssl AS s
WHERE s.pid = pg_backend_pid();
```

Kết quả cho biết **phiên hiện tại** đang dùng SSL/TLS và, nếu có, phiên bản/cipher được báo. Nếu kết nối qua Unix socket, TLS TCP không phải lúc nào cũng áp dụng theo cách giống kết nối mạng.

### 13.2. Hostname và hostaddr

Tham số `host` thường mang hostname cần truy cập; `hostaddr` có thể chỉ địa chỉ IP đích trực tiếp. Khi dùng xác minh tên chứng chỉ ở `sslmode=verify-full`, hãy giữ một **hostname phù hợp với chứng chỉ** trong cấu hình `host`, thay vì chỉ cung cấp IP rồi bỏ qua bước xác minh tên.

Ví dụ ở môi trường có DNS hoặc tuyến IP đặc biệt, cấu hình có thể cần cả `host` và `hostaddr`, nhưng phải xác minh chúng cùng đại diện đúng server; không tự đi vòng xác minh hostname chỉ để kết nối thành công.

## 14. Timeout, tên ứng dụng và nhiều địa chỉ server

### 14.1. Giới hạn thời gian chờ kết nối

Một ứng dụng hoặc script không nên treo vô hạn khi hostname không phân giải được hoặc server không trả lời.

```bash
psql "host=db.internal.example port=5432 dbname=learning_pg user=learning_app connect_timeout=5 application_name=maintenance_check"
```

`connect_timeout=5` áp dụng cho thời gian thiết lập kết nối theo quy tắc libpq, **không phải** giới hạn thời gian chạy mọi câu SQL sau khi đã đăng nhập. Để giới hạn thời gian thực thi truy vấn, PostgreSQL có các thiết lập phiên riêng, chẳng hạn `statement_timeout`, và cần áp dụng theo hợp đồng nghiệp vụ.

### 14.2. application_name giúp quan sát kết nối

Đặt tên ứng dụng trong connection string:

```bash
psql "host=127.0.0.1 port=5432 dbname=learning_pg user=learning_app application_name=lesson43_psql"
```

Trong phiên:

```sql
SHOW application_name;
```

Với role quản trị/giám sát có quyền phù hợp, có thể quan sát các phiên qua:

```sql
SELECT pid, usename, datname, application_name, state
FROM pg_stat_activity
WHERE application_name = 'lesson43_psql';
```

`application_name` là một nhãn hỗ trợ giám sát, **không phải** thông tin nhận dạng bảo mật đáng tin tuyệt đối: client có thể tự đặt nó. Không dùng nhãn này làm căn cứ cấp quyền.

### 14.3. Nhiều host và lựa chọn read-write

Libpq hỗ trợ khai báo nhiều host/port trong một connection string để thử kết nối theo chính sách phù hợp. Ví dụ trên hạ tầng PostgreSQL đã có nhiều endpoint:

```bash
psql "host=pg1.internal.example,pg2.internal.example port=5432,5432 dbname=learning_pg user=learning_app target_session_attrs=read-write connect_timeout=5"
```

`target_session_attrs=read-write` yêu cầu libpq lựa chọn một kết nối có thuộc tính phù hợp với phiên có thể ghi, thay vì chỉ kết nối tới bất kỳ standby nào. Đây là cơ chế chọn mục tiêu kết nối, **không tự tạo high availability, tự bầu primary hay giải quyết việc routing của toàn ứng dụng**.

Trong môi trường có failover, cần kết hợp với hệ thống quản lý cluster, DNS/load balancer hoặc cơ chế điều phối được vận hành đúng. Không thử nhiều host trên các server độc lập rồi giả định chúng có cùng dữ liệu.

## 15. Chạy SQL từ command line mà không vào phiên tương tác

`psql` không chỉ dùng để mở một dấu nhắc SQL; nó còn chạy được một câu lệnh hoặc một file script.

### 15.1. Thực thi một câu SQL với -c

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg \
  -c "SELECT current_database(), current_user, now();"
```

Đoạn này dùng dấu `\` nối dòng theo shell kiểu Linux/macOS. Trong PowerShell, có thể viết lệnh trên một dòng:

```powershell
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg -c "SELECT current_database(), current_user, now();"
```

Với automation, nên xử lý exit code và output cẩn thận. Đừng dựa vào việc một lần chạy có kết quả SQL in ra màn hình để kết luận script đầy đủ đã thành công.

### 15.2. Chạy file .sql

Giả sử có file `init_lab.sql` trong thư mục làm việc:

```sql
CREATE TABLE IF NOT EXISTS demo_notes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message TEXT NOT NULL
);

INSERT INTO demo_notes (message)
VALUES ('Hello PostgreSQL');

SELECT id, message
FROM demo_notes
ORDER BY id;
```

Chạy bằng:

```bash
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg \
  -X -v ON_ERROR_STOP=1 -f init_lab.sql
```

Giải thích:

- `-f init_lab.sql`: đọc và thực thi các lệnh trong file.
- `-X`: không đọc file khởi tạo `psqlrc` của người dùng, giảm ảnh hưởng cấu hình tùy biến khi chạy script.
- `-v ON_ERROR_STOP=1`: yêu cầu `psql` dừng khi gặp lỗi thay vì tiếp tục chạy các bước sau.
- File được thực thi theo quyền của role đã đăng nhập; cần quyền `CREATE` trên schema nếu script tạo bảng.

Trên PowerShell có thể viết trên một dòng:

```powershell
psql -h 127.0.0.1 -p 5432 -U learning_app -d learning_pg -X -v ON_ERROR_STOP=1 -f init_lab.sql
```

**Lưu ý về transaction:** nhiều câu SQL trong file không mặc nhiên tạo thành một transaction duy nhất. Nếu yêu cầu tất cả cùng thành công hoặc cùng rollback, có thể dùng `BEGIN ... COMMIT` trong file phù hợp hoặc tùy chọn `--single-transaction` của `psql` khi các lệnh cho phép. Một số lệnh như `CREATE DATABASE` không thể chạy trong transaction block, nên không dùng tùy chọn này máy móc cho mọi script.

### 15.3. Trích xuất kết quả cho shell script

Khi cần lấy một giá trị đơn giản mà không kèm header bảng:

```bash
psql -h 127.0.0.1 -U learning_app -d learning_pg \
  -X -A -t -c "SELECT current_database();"
```

`-A` chọn output không căn chỉnh; `-t` ẩn phần header/footer bảng. Cách xuất này hữu ích cho shell script nhưng chỉ phù hợp khi bạn đã biết rõ cấu trúc dữ liệu được trả; với dữ liệu nhiều dòng, dấu xuống dòng/tab và giá trị đặc biệt cần được xử lý cẩn thận.

## 16. Thứ tự ưu tiên cấu hình và cách tránh “kết nối nhầm”

Một môi trường có thể cung cấp thông tin kết nối từ nhiều nơi:

```text
Tham số đưa trực tiếp vào psql / connection string
          |
          v
Tham số lấy từ service file (nếu có service)
          |
          v
Biến môi trường PGHOST / PGPORT / PGUSER / PGDATABASE ...
          |
          v
Giá trị mặc định của libpq / hệ điều hành
```

Đây là sơ đồ khái quát để **giải thích nguồn cấu hình**, không phải bảng thứ tự thay thế đầy đủ cho mọi trường hợp trùng tham số. Các quy tắc kết hợp option `-d`, service file và tham số tường minh có chi tiết riêng; để giảm nhập nhằng hãy cấu hình một tham số tại một nơi có chủ đích.

Ví dụ, terminal đã có:

```bash
export PGDATABASE=reporting
export PGHOST=db.internal.example
```

Nếu sau đó chỉ gõ:

```bash
psql -U learning_app
```

thì có thể kết nối tới **reporting trên server từ xa**, chứ không phải `learning_pg` local mà người dùng tưởng. Với các thao tác quan trọng, nên:

1. Ghi rõ endpoint và database trong command hoặc service được kiểm soát.
2. Dùng role có quyền tối thiểu.
3. Chạy `\conninfo` và `SELECT current_database(), current_user;` để xác minh phiên.
4. Với môi trường production, dùng biện pháp bảo vệ bổ sung trước các câu lệnh thay đổi dữ liệu.

## 17. Chẩn đoán các lỗi kết nối phổ biến

### 17.1. Không tìm thấy chương trình psql

Thông báo như `psql: command not found` hoặc `psql is not recognized` nghĩa là shell không tìm được binary trong `PATH`, hoặc client chưa cài.

Giải pháp: xác định vị trí binary được cài, dùng đường dẫn đầy đủ hoặc thêm đúng thư mục `bin` vào `PATH`, sau đó thử lại `psql --version`. Nếu máy có nhiều phiên bản PostgreSQL, cần xem binary nào đang được chọn.

### 17.2. Connection refused hoặc timeout

Ví dụ:

```text
connection to server at "127.0.0.1", port 5432 failed:
Connection refused
```

Các nguyên nhân thường gặp:

- PostgreSQL server chưa chạy.
- Sai hostname hoặc port.
- Server không lắng nghe trên địa chỉ đã chỉ định.
- Firewall, route hoặc proxy chặn kết nối.
- Server đang khởi động, quá tải hoặc cổng bị dịch vụ khác sử dụng.

Thử:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Nếu server không phản hồi, kiểm tra service manager và log trên **đúng máy server**. `Connection refused` khác với lỗi sai mật khẩu: thường đây là thất bại trước bước xác thực người dùng.

### 17.3. FATAL: password authentication failed

Server nhận kết nối nhưng thông tin xác thực của role không được chấp nhận theo quy tắc áp dụng.

Kiểm tra:

- Đã chọn đúng `host`/`port`/`dbname`/`user` chưa?
- Password file hoặc secret manager có đang cung cấp mật khẩu cũ không?
- `pg_hba.conf` đang chọn phương thức xác thực nào?
- Client/driver có hỗ trợ cơ chế như SCRAM hay không?
- Server có nhiều instance cùng tên database nhưng dùng tài khoản khác nhau không?

Không sửa lỗi bằng cách mở `trust` trên mạng công cộng. Đặt lại credential của **đúng role và đúng instance** qua quản trị viên nếu cần.

### 17.4. FATAL: role does not exist

Ví dụ:

```text
FATAL: role "learning_app" does not exist
```

Kiểm tra user được gửi qua `-U`, biến `PGUSER` và các role đang tồn tại. Trên hệ có quyền, dùng `\du` hoặc truy vấn metadata phù hợp.

Nếu role vừa được tạo nhưng vẫn báo không tồn tại, rất có thể bạn đang kết nối tới **instance khác** (sai host, port, container hoặc service).

### 17.5. FATAL: database does not exist

Nếu bỏ `-d`, database mặc định có thể trùng tên role. Chỉ rõ `-d learning_pg` để tránh đoán sai. Nếu database không tồn tại trên instance hiện tại, quản trị viên có thể tạo mới khi đúng yêu cầu; không tạo bừa một database cùng tên trên server production.

### 17.6. Peer authentication failed

Trên Linux/Unix, xác thực local `peer` có thể so sánh OS user với PostgreSQL role. Vì vậy:

```bash
psql -U postgres
```

có thể thất bại nếu bạn đang chạy dưới OS user khác, dù:

```bash
sudo -iu postgres psql
```

có thể thành công. Đường TCP với `-h 127.0.0.1` có thể dùng quy tắc xác thực khác; hãy kiểm tra cấu hình trước khi đổi password hoặc các dòng trong `pg_hba.conf`.

### 17.7. No pg_hba.conf entry

Kết nối đã tới server nhưng không có quy tắc xác thực phù hợp với loại kết nối, địa chỉ **client**, role, database và trạng thái SSL.

Ví dụ thông báo:

```text
FATAL: no pg_hba.conf entry for host "...", user "...",
database "...", ...
```

Để sửa đúng:

1. Xác định địa chỉ client mà PostgreSQL nhìn thấy.
2. Xem đường dẫn `pg_hba.conf` qua `SHOW hba_file;` nếu có quyền.
3. Xác định dòng `host`/`hostssl`, CIDR, role và database phù hợp.
4. Bổ sung quy tắc **giới hạn phạm vi** và phương thức xác thực an toàn.
5. Reload cấu hình theo quy trình đã được phê duyệt.

Không thêm `host all all 0.0.0.0/0 trust` chỉ để làm cho một lệnh kết nối hoạt động.

### 17.8. Lỗi certificate hoặc hostname khi dùng verify-full

Nếu `sslmode=verify-full` báo certificate không hợp lệ, có thể do:

- Client thiếu hoặc dùng sai CA certificate.
- Certificate server đã hết hạn hoặc không được CA phù hợp ký.
- Hostname trong URI không khớp tên được chứng chỉ xác nhận.
- Bạn kết nối bằng IP trong khi chứng chỉ được cấp theo hostname khác.
- Đang kết nối nhầm endpoint/server.

Không chuyển ngay sang `sslmode=disable` để bỏ qua lỗi. Hãy xác định chứng chỉ của đúng server, cấu hình trust material và hostname chuẩn theo quy trình bảo mật.

## 18. Chẩn đoán trực tiếp trong một phiên psql đã kết nối

Khi đã đăng nhập, chạy:

```sql
SELECT
    current_database() AS db,
    current_user AS effective_user,
    session_user AS login_user,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    inet_client_addr() AS client_ip;

SHOW search_path;
SHOW application_name;
```

Và:

```text
\conninfo
```

Cần hiểu:

- `inet_server_addr()` và `inet_server_port()` có thể trả `NULL` với kết nối Unix socket.
- `search_path` ảnh hưởng việc tên bảng không kèm schema được ánh xạ vào đối tượng nào.
- `application_name` là nhãn do client đặt, không phải credential.
- `current_user` thể hiện role hiệu lực hiện tại, còn `session_user` thường phản ánh role đăng nhập của phiên.

Nếu truy vấn bảng không có schema trả `relation does not exist` nhưng bảng thực sự tồn tại, có thể bạn ở **database khác** hoặc `search_path` không chứa schema của bảng. Đó là lỗi phạm vi tên đối tượng, không nhất thiết là lỗi đường truyền hay xác thực.

## 19. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ gõ `psql` và mặc định luôn vào database `postgres` | Libpq có thể chọn database trùng tên OS user hoặc môi trường | Chỉ rõ `-h`, `-U`, `-d` và xem `\conninfo` |
| Nhầm `psql --version` với phiên bản server | Chẩn đoán sai major version | Kết nối rồi chạy `SHOW server_version;` |
| Nhầm `-h localhost` với Unix socket trong mọi trường hợp | Xác thực và đường kết nối khác nhau | Xác minh host, socket directory và TCP tường minh |
| Đặt mật khẩu vào command line/URI | Dễ rò rỉ qua history/log/process | Dùng prompt, passfile hoặc secret manager |
| Gõ `-W password` | `-W` không nhận password như giá trị | Dùng `-W` rồi nhập ở prompt |
| Dùng URI có `&` nhưng không quote | Shell có thể tách lệnh | Quote toàn bộ URI |
| Không percent-encode ký tự đặc biệt trong URI | Phân tích sai user, host, database hoặc query | Encode theo ngữ nghĩa URI |
| Dùng `jdbc:postgresql://...` với psql | Driver URI không cùng cú pháp libpq | Dùng `postgresql://...` hoặc `key=value` |
| Dùng `sslmode=prefer` rồi cho rằng TLS bắt buộc | Client có thể fallback không TLS | Cấu hình `verify-full` khi cần xác minh server |
| Dùng `sslmode=require` rồi coi như đã kiểm tra hostname | Có thể thiếu bước xác minh danh tính đầy đủ | Cấu hình `verify-full` và CA phù hợp |
| Đọc secret từ `.pgpass` nhưng để file quyền quá rộng trên Unix | Libpq có thể bỏ qua file | Hạn chế quyền truy cập, thường `chmod 600` |
| Script không bật `ON_ERROR_STOP` | Có thể tiếp tục sau câu SQL lỗi | Dùng `-X -v ON_ERROR_STOP=1` khi phù hợp |
| Tin tên service mà không kiểm tra điểm kết nối thực tế | Có thể kết nối nhầm staging/production | Kiểm tra endpoint, role, database và quyền |
| Mở `trust` hoặc cổng public để khắc phục lỗi auth | Làm yếu hệ thống | Sửa đúng `pg_hba.conf`, TLS và firewall |

## 20. Bài tập thực hành

Sử dụng một PostgreSQL instance thực hành, không dùng database production:

1. Chạy `psql --version`, sau đó kết nối và chạy `SHOW server_version;`. Giải thích vì sao hai giá trị có thể khác nhau.
2. Kết nối tới `learning_pg` bằng bốn tùy chọn `-h`, `-p`, `-U`, `-d`. Chạy `\conninfo` và ghi lại database, role, host và port.
3. Viết lại kết nối ở câu 2 thành **libpq keyword/value connection string**. Thêm `connect_timeout=5` và `application_name=lesson43_psql`.
4. Viết lại cùng kết nối thành URI `postgresql://...`. Thêm hai query parameter và giải thích vì sao cần quote toàn bộ URI khi có `&`.
5. Nếu database có khoảng trắng trong tên, giải thích cách quote giá trị ở dạng `key=value` và cách percent-encode khoảng trắng ở URI.
6. Trên Linux/macOS, so sánh kết nối không có `-h` với `-h 127.0.0.1`. Dùng `\conninfo` để nhận diện giao thức/host và nêu sự khác nhau giữa quy tắc `local` và `host` trong `pg_hba.conf`.
7. Thiết lập `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE` trong terminal rồi kết nối bằng `psql -W`. Giải thích những tham số nào do môi trường cung cấp.
8. Tạo password file chỉ trong môi trường thử nghiệm, bảo vệ quyền file phù hợp, kết nối mà không nhập mật khẩu và giải thích vì sao không nên đưa file này vào Git.
9. Tạo service file có hai cấu hình: local training và reporting internal. Dùng `psql "service=..."` rồi xác nhận không kết nối nhầm instance.
10. Thiết lập một kết nối được yêu cầu `sslmode=verify-full` trong một môi trường đã cấp chứng chỉ phù hợp; dùng `\conninfo` hoặc `pg_stat_ssl` để xác nhận TLS. Giải thích sự khác nhau giữa `require` và `verify-full`.
11. Chạy một truy vấn với `psql -c`, sau đó tạo file SQL và chạy qua `psql -X -v ON_ERROR_STOP=1 -f ...`. Nêu cách nhận biết lỗi thực thi từ script.
12. Chẩn đoán năm tình huống: client không có trong `PATH`, `Connection refused`, `Peer authentication failed`, `Role does not exist` và `No pg_hba.conf entry`. Với mỗi lỗi, chỉ rõ phải kiểm tra ở client, server, xác thực hay cấu hình quyền.
13. Một terminal đã có `PGHOST=db.internal.example` và `PGDATABASE=reporting`. Nếu bạn chạy `psql -U learning_app`, khả năng kết nối tới đâu? Thiết kế cách ngăn thao tác nhầm môi trường.
14. So sánh chuỗi kết nối libpq `postgresql://...` với URL JDBC `jdbc:postgresql://...`; chỉ ra phần nào tương tự và vì sao không thể dùng thay thế nguyên văn.

## 21. Tổng kết

Để kết nối PostgreSQL thành công bằng `psql`, phải xác định rõ **endpoint, port, database, role và phương thức xác thực**. Bạn có thể cung cấp các thông tin đó bằng từng option CLI, bằng connection string `key=value` hoặc bằng URI `postgresql://...`. Libpq còn hỗ trợ biến môi trường, password file và service file để tái sử dụng cấu hình.

Khi triển khai thực tế, ưu tiên **xác minh server đang kết nối**, **giữ mật khẩu ngoài command line và mã nguồn**, **dùng TLS có xác thực danh tính cho kết nối từ xa**, và **đặt timeout phù hợp**. Sau khi mở phiên, `\conninfo`, `current_database()`, `current_user` cùng các lệnh chẩn đoán sẽ giúp bạn phân biệt lỗi kết nối với lỗi quyền hoặc sai database. Nắm chắc những công cụ này là nền tảng cho việc sử dụng PostgreSQL an toàn trong terminal, script và ứng dụng.
