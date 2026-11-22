# Quản lý thông tin kết nối bằng service file và .pgpass trong PostgreSQL

Khi làm việc với PostgreSQL, người dùng thường lặp lại nhiều tham số kết nối trong các lệnh `psql`, `pg_dump`, `pg_restore` hoặc các chương trình dùng thư viện `libpq`:

```bash
psql -h db.internal.example -p 5432 -U report_reader -d shopdb
pg_dump -h db.internal.example -p 5432 -U report_reader -d shopdb -Fc -f shopdb.dump
```

Việc sao chép thông tin này qua nhiều script dễ gây sai hostname, nhầm database staging với production, quên thiết lập TLS hoặc phải nhập mật khẩu nhiều lần. PostgreSQL có hai cơ chế phía client nhằm giải quyết những vấn đề này:

- **Connection service file**: đặt tên cho một nhóm tham số kết nối, ví dụ `[shop_staging_ro]`, để client chỉ cần gọi `service=shop_staging_ro`.
- **Password file**: chứa những dòng đối chiếu host/port/database/user với mật khẩu, giúp công cụ tự động xác thực mà không đưa mật khẩu lên dòng lệnh.

Trên Linux/macOS, file cá nhân thường tên **`~/.pg_service.conf`** và **`~/.pgpass`**. Trên Windows, đường dẫn mặc định thường là **`%APPDATA%\postgresql\.pg_service.conf`** và **`%APPDATA%\postgresql\pgpass.conf`**.

Hai file này làm hai việc **khác nhau nhưng bổ sung cho nhau**. Service file chọn đúng đích kết nối; password file hỗ trợ lấy secret cho kết nối đó. Chúng **không** tự tạo database, không cấp quyền SQL, không mở firewall và không thay thế xác thực/TLS của server.

Sau bài học, bạn có thể tạo service file, sử dụng `.pgpass` đúng định dạng và quyền truy cập, hiểu thứ tự ưu tiên tham số, gọi `psql`/`pg_dump` từ script và xử lý các lỗi thường gặp.

> **Phạm vi:** Những cơ chế này là tính năng của **libpq**, thư viện kết nối PostgreSQL. Các công cụ tiêu chuẩn như `psql` và `pg_dump` dùng libpq; nhưng không được tự suy ra mọi PostgreSQL driver của mọi ngôn ngữ, đặc biệt JDBC thuần trong Java, đều đọc service file và password file theo cách libpq làm.

## 1. Một tình huống thực tế

Giả sử nhóm phát triển quản lý ba môi trường:

| Tên dùng trong bài | Máy chủ | Port | Database | Role |
|---|---|---:|---|---|
| Dev | `127.0.0.1` | 5432 | `shopdb_dev` | `dev_user` |
| Staging | `stg-db.internal.example` | 5432 | `shopdb` | `report_reader` |
| Production | `prod-db.internal.example` | 5432 | `shopdb` | `report_reader` |

Nếu khai báo service file, bạn có thể dùng:

```bash
psql "service=shop_dev"
psql "service=shop_staging_ro"
pg_dump -d "service=shop_staging_ro" -Fc -f staging.dump
```

Thay vì lặp lại từng tham số, chỉ cần một tên service. Khi hostname của staging thay đổi, có thể chỉnh định nghĩa tương ứng mà không cần viết lại mọi script. Nếu server yêu cầu mật khẩu, libpq có thể tra `.pgpass` khớp với tham số hiệu lực.

Để thực hành, cần có PostgreSQL client tools đã cài, biết thông tin đích thật, và đã được cấp role có `LOGIN` cùng quyền cần thiết. Server phải đang hoạt động; `listen_addresses`, port, firewall và `pg_hba.conf` phía server phải cho phép kết nối.

## 2. Service file là gì và nằm ở đâu?

**Service file** là một tệp dạng INI chứa nhiều section. Tên section chính là service name; nội dung section là các tham số kết nối `key=value`.

Ví dụ:

```ini
# ~/.pg_service.conf

[shop_dev]
host=127.0.0.1
port=5432
dbname=shopdb_dev
user=dev_user
connect_timeout=5
application_name=shop_dev_cli

[shop_staging_ro]
host=stg-db.internal.example
port=5432
dbname=shopdb
user=report_reader
connect_timeout=10
application_name=shop_report_cli
sslmode=verify-full
sslrootcert=/home/linh/.postgresql/root.crt
```

Mỗi section là một **cấu hình có tên**. Ví dụ `shop_staging_ro` chỉ định host, database, user và yêu cầu xác minh chứng chỉ TLS. Tên `ro` chỉ là một quy ước đặt tên, **không tự giới hạn tài khoản ở quyền chỉ đọc**; quyền thật phải được cấu hình cho role PostgreSQL.

### 2.1. Vị trí file cá nhân

| OS | Đường dẫn mặc định |
|---|---|
| Linux | `~/.pg_service.conf` |
| macOS | `~/.pg_service.conf` |
| Windows | `%APPDATA%\postgresql\.pg_service.conf` |

Ví dụ Windows khi profile nằm tại `C:\Users\Linh`:

```text
C:\Users\Linh\AppData\Roaming\postgresql\.pg_service.conf
```

Đây là file **phía client**, không phải file cấu hình server PostgreSQL trong `PGDATA`. User OS chạy lệnh nào thì libpq tìm cấu hình của user đó, trừ khi có biến thay đổi đường dẫn. Một tác vụ chạy bằng account `backup` không mặc nhiên dùng file `~/.pg_service.conf` của người quản trị.

### 2.2. File cấp hệ thống và thứ tự ưu tiên giữa hai file

Ngoài file cá nhân, libpq có thể đọc service file dùng chung tên **`pg_service.conf`** nằm trong thư mục cấu hình của cài đặt PostgreSQL. Khi có công cụ tương ứng:

```bash
pg_config --sysconfdir
```

là cách xác định đường dẫn thư mục cấu hình hệ thống tương ứng với bản `pg_config` đang gọi. Nếu máy cài nhiều phiên bản PostgreSQL, cần biết công cụ trong `PATH` thuộc bản nào.

Khi cả file cá nhân và file cấp hệ thống có service **cùng tên**, định nghĩa trong **file cá nhân được ưu tiên**. Không giả định hai section trùng tên được hợp nhất theo ý người vận hành; nên đặt tên rõ và xác định chính xác file nào đang được client đọc.

### 2.3. Chọn file service khác

Biến môi trường `PGSERVICEFILE` trỏ đến một **file cụ thể**, thay thế vị trí file cá nhân mặc định:

```bash
export PGSERVICEFILE="$HOME/config/services_pg.conf"
psql "service=shop_staging_ro"
unset PGSERVICEFILE
```

Trên Windows PowerShell:

```powershell
$env:PGSERVICEFILE = 'C:\Config\PostgreSQL\services_pg.conf'
psql "service=shop_staging_ro"
Remove-Item Env:PGSERVICEFILE
```

`PGSYSCONFDIR` thì đặt **thư mục** tìm file cấp hệ thống tên `pg_service.conf`, không đặt đường dẫn file cá nhân:

```bash
export PGSYSCONFDIR=/etc/postgresql-client
psql "service=shop_staging_ro"
```

Hãy phân biệt: `PGSERVICE` chọn **tên service**; `PGSERVICEFILE` chọn **file cá nhân**; `PGSYSCONFDIR` chọn **thư mục cấu hình hệ thống**.

## 3. Các tham số nên đặt trong service file

| Tên libpq | Vai trò | Lưu ý |
|---|---|---|
| `host` | Hostname hoặc địa chỉ server | Với TLS verify-full, hostname phải phù hợp chứng chỉ |
| `hostaddr` | Địa chỉ IP TCP dùng để kết nối | Cần hiểu tương tác với `host`, TLS và password file |
| `port` | Cổng PostgreSQL | Mặc định thường 5432 nhưng có thể khác |
| `dbname` | Tên database | Không nhầm với tên service |
| `user` | Role dùng để đăng nhập | Không phải user OS chạy tiến trình |
| `connect_timeout` | Giới hạn chờ kết nối (giây) | Có lợi cho job không tương tác |
| `application_name` | Tên client hiển thị phục vụ quan sát | Có thể xem bằng `pg_stat_activity` |
| `sslmode` | Chính sách TLS | `verify-full` yêu cầu xác thực chứng chỉ và hostname |
| `sslrootcert` | Đường dẫn CA root tin cậy | File phải thực sự tồn tại và đúng nguồn tin cậy |
| `passfile` | Password file thay mặc định | Cần bảo vệ quyền file chứa secret |
| `target_session_attrs` | Yêu cầu tính chất server trong trường hợp có nhiều host | Dùng khi thực sự hiểu topology |

Không nhất thiết đặt mọi tham số. Những tham số vắng mặt có thể đến từ môi trường hoặc giá trị mặc định. Không nên đặt `password` trực tiếp trong service file dù libpq hỗ trợ tham số này: file thường được chia sẻ cho nhóm và dễ bị sao chép; hãy dùng password file hoặc hệ quản lý bí mật có kiểm soát.

### 3.1. Một service cho môi trường local

```ini
[inventory_local]
host=127.0.0.1
port=5432
dbname=inventory
user=inventory_dev
connect_timeout=5
```

### 3.2. Một service qua mạng riêng với TLS

```ini
[inventory_staging]
host=stg-db.internal.example
port=5432
dbname=inventory
user=inventory_reader
connect_timeout=8
sslmode=verify-full
sslrootcert=/home/linh/.postgresql/root.crt
application_name=staging_inventory_check
```

Hostname và đường dẫn CA là giá trị **minh họa**, không thể dùng nguyên xi nếu môi trường chưa có DNS/chứng chỉ tương ứng. Với `verify-full`, không nên sửa thành `sslmode=disable` chỉ để bỏ qua lỗi xác thực; cần kiểm tra đúng hostname, CA và chứng chỉ server.

## 4. Gọi kết nối bằng service name

Một cách dùng trực tiếp:

```bash
psql "service=inventory_local"
```

Libpq tìm section `[inventory_local]`, đọc host/port/dbname/user rồi mở kết nối theo điều kiện server cho phép.

### 4.1. Kiểm tra đích thực tế sau khi kết nối

Trong `psql`, chạy:

```sql
SELECT
    current_database() AS ten_database,
    current_user AS role_hien_tai,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    current_setting('application_name') AS ten_ung_dung;
```

Hoặc nhập meta-command:

```text
\conninfo
```

Nếu client kết nối bằng Unix-domain socket, hai hàm `inet_server_addr()`/`inet_server_port()` có thể trả `NULL`. Điều đó tự nó không có nghĩa kết nối đã thất bại.

**Luôn xác minh database, role và host trước khi thực hiện thao tác thay đổi nguy hiểm**, đặc biệt khi một máy có nhiều instance hoặc nhiều service dùng cùng tên.

### 4.2. Chọn service bằng biến môi trường

Bash:

```bash
export PGSERVICE=inventory_local
psql
unset PGSERVICE
```

PowerShell:

```powershell
$env:PGSERVICE = 'inventory_local'
psql
Remove-Item Env:PGSERVICE
```

Biến môi trường giúp chọn service cho một nhóm lệnh trong cùng process/shell. Nếu script đã truyền `service=...` trực tiếp hoặc có cấu hình cao ưu tiên hơn, cần xác định nguồn hiệu lực thay vì suy đoán từ `PGSERVICE`.

### 4.3. Sử dụng trong pg_dump, pg_restore và pg_isready

```bash
# Kiểm tra server có chấp nhận kết nối không.
pg_isready -d "service=inventory_staging"

# Xuất dump logic định dạng custom.
pg_dump -d "service=inventory_staging" \
    -Fc -f inventory_staging.dump

# Minh họa cú pháp restore, CHỈ chạy ở môi trường thử nghiệm được phép.
pg_restore -d "service=inventory_local" \
    inventory_staging.dump
```

`pg_isready` không phải công cụ chứng minh role đã xác thực và có đủ quyền trên mọi bảng. `pg_dump` cần quyền đọc những đối tượng cần backup. `pg_restore` có thể thay đổi dữ liệu/schema và phải có kế hoạch riêng; không dùng nó chỉ để thử kết nối.

## 5. Thứ tự ưu tiên của tham số kết nối

Khi cùng một tham số được khai báo ở nhiều nơi, libpq kết hợp chúng theo **ưu tiên từng tham số**, đại ý:

```text
Ưu tiên cao
    1. Tham số kết nối được chỉ định trực tiếp
       (ví dụ trong connection string)
    2. Giá trị đọc từ service file được chọn
    3. Biến môi trường tương ứng (PGHOST, PGPORT, ...)
    4. Giá trị mặc định của libpq
Ưu tiên thấp
```

Ví dụ service:

```ini
[shop_report]
host=stg-db.internal.example
port=5432
dbname=shopdb
user=report_reader
```

Giả sử trong shell có `PGPORT=5444`, nhưng gọi:

```bash
psql "service=shop_report port=5433"
```

Kết nối dùng **port 5433**, vì tham số trực tiếp được ưu tiên. Nếu bỏ `port=5433`, dùng port **5432** từ service, không phải `PGPORT=5444`. Host, dbname và user vẫn lấy từ service nếu không bị ghi đè.

### 5.1. Các biến môi trường thường gặp

| Biến | Tham số tương ứng |
|---|---|
| `PGHOST` | `host` |
| `PGPORT` | `port` |
| `PGDATABASE` | `dbname` |
| `PGUSER` | `user` |
| `PGCONNECT_TIMEOUT` | `connect_timeout` |
| `PGSSLMODE` | `sslmode` |
| `PGSSLROOTCERT` | `sslrootcert` |
| `PGAPPNAME` | `application_name` |
| `PGSERVICE` | `service` |
| `PGPASSFILE` | `passfile` |

`PGPASSWORD` có thể cung cấp mật khẩu, nhưng không được khuyến nghị vì biến môi trường có nguy cơ bị quan sát qua một số công cụ tiến trình, debug/log. Một secret bị thiết lập trong `PGPASSWORD` cũng có thể khiến libpq **không dùng** password file đúng như bạn mong đợi.

### 5.2. Tránh nhầm lẫn ưu tiên của service và password file

Service file không tự thực hiện xác thực. Sau khi xác định host/port/dbname/user cuối cùng, libpq kết nối và, khi cần mật khẩu mà chưa có password được chỉ định theo cách khác, có thể tra password file.

Nếu người dùng ghi đè `user` hoặc `host` ở connection string, password file phải có dòng khớp **giá trị cuối cùng**, không phải giá trị ban đầu trong service. Đó là nguyên nhân phổ biến của việc “service đúng nhưng vẫn bị hỏi mật khẩu”.

## 6. Password file .pgpass nằm ở đâu?

**Password file** là tệp phía client chứa credential theo từng tổ hợp kết nối.

| Nền tảng | Vị trí mặc định |
|---|---|
| Linux/macOS/Unix-like | `~/.pgpass` |
| Windows | `%APPDATA%\postgresql\pgpass.conf` |

Điểm dễ nhầm trên Windows:

```text
Service file:  %APPDATA%\postgresql\.pg_service.conf
Password file: %APPDATA%\postgresql\pgpass.conf
```

Tên password file **không** có dấu chấm đầu như `.pgpass` trên Unix. Một password file khác có thể được chỉ định bằng:

```bash
export PGPASSFILE="$HOME/secrets/pg_passwords"
psql "service=inventory_local"
```

Hoặc dùng tham số kết nối `passfile` nếu client hỗ trợ các tham số libpq phù hợp.

### 6.1. Định dạng năm trường

Mỗi dòng:

```text
hostname:port:database:username:password
```

Ví dụ toàn bộ mật khẩu bên dưới là **placeholder**, không phải secret:

```text
127.0.0.1:5432:inventory:inventory_dev:EXAMPLE_LOCAL_PASSWORD
stg-db.internal.example:5432:inventory:inventory_reader:EXAMPLE_STAGING_PASSWORD
```

Không đặt dấu ngoặc kép quanh từng trường. Dấu `:` có ý nghĩa tách trường; nếu một giá trị thực chứa dấu đặc biệt, cần escape đúng.

### 6.2. Cách khớp dòng

Libpq tìm từ trên xuống và dùng **dòng đầu tiên** khớp các trường kết nối.

Ví dụ:

```text
stg-db.internal.example:5432:inventory:inventory_reader:SECRET_A
127.0.0.1:5432:inventory:inventory_dev:SECRET_B
```

Service `inventory_staging` ở mục trước khai báo host `stg-db.internal.example`, port `5432`, dbname `inventory` và user `inventory_reader`, nên dòng đầu là ứng viên để cấp mật khẩu.

Nếu gọi `psql "service=inventory_staging user=other_user"` thì dòng đó không còn khớp vì username hiệu lực đã thay đổi.

### 6.3. Wildcard và thứ tự cụ thể trước tổng quát

Bốn trường đầu có thể dùng `*` để khớp bất kỳ giá trị:

```text
stg-db.internal.example:5432:inventory:inventory_reader:SPECIFIC_PASSWORD
stg-db.internal.example:5432:*:inventory_reader:STAGING_PASSWORD
*:5432:*:inventory_dev:GENERIC_DEV_PASSWORD
```

Vì **dòng đầu tiên khớp được chọn**, luôn đặt các dòng cụ thể ở trước dòng wildcard. Nếu viết:

```text
*:*:*:*:GENERIC_PASSWORD
stg-db.internal.example:5432:inventory:inventory_reader:SPECIFIC_PASSWORD
```

thì dòng tổng quát đầu có thể chặn mọi dòng sau. Tránh `*:*:*:*` ở hệ thống có nhiều server: dễ gửi thử mật khẩu không phù hợp đến một host không dự kiến và làm khó kiểm tra lỗi.

### 6.4. Escape dấu hai chấm và backslash

Vì dấu `:` ngăn các trường, ký tự `:` và `\` bên trong giá trị phải escape bằng backslash:

```text
# Mật khẩu minh họa thực tế: pass:word\example
db.internal.example:5432:shopdb:app_user:pass\:word\\example
```

`\:` biểu diễn dấu hai chấm thuộc giá trị; `\\` biểu diễn một dấu backslash. Không thêm escape tùy tiện cho các ký tự khác nếu không có yêu cầu.

### 6.5. Hostname khác IP, và kết nối Unix socket

Khớp mật khẩu có liên quan đến tham số `host`; nếu không có `host` mà có `hostaddr`, libpq xét `hostaddr`; nếu không có cả hai thì tra theo `localhost`. Có quy tắc đặc biệt với Unix-domain socket tại thư mục socket mặc định.

Vì thế:

- `host=localhost` và `host=127.0.0.1` là **hai chuỗi khác nhau**.
- Password file chỉ có `localhost:5432:...` không tự bảo đảm khớp service đặt `host=127.0.0.1`.
- Với socket tùy chỉnh, cần xác nhận đúng cách libpq lựa chọn trường hostname cho matching.
- Khi thay đổi `host`, `port`, `dbname` hoặc `user`, cần đánh giá lại các dòng `.pgpass` tương ứng.

## 7. Quyền .pgpass trên Unix: yêu cầu bảo mật bắt buộc

Password file chứa mật khẩu dạng **plaintext**. Trên Linux/macOS/Unix, libpq **bỏ qua file** nếu quyền tệp cho phép group hoặc other truy cập. Cách thiết lập thông dụng:

```bash
# Tạo file với umask hạn chế nếu chưa có.
umask 077
touch "$HOME/.pgpass"

# Chỉ owner đọc/ghi.
chmod 600 "$HOME/.pgpass"

# Xem owner và mode.
ls -l "$HOME/.pgpass"
```

Ví dụ mode:

```text
-rw------- 1 linh linh ... /home/linh/.pgpass
```

`0600` có nghĩa:

- Owner: đọc và ghi.
- Group: không có quyền.
- Other: không có quyền.

File `-rw-r--r--` tương ứng `0644` sẽ bị libpq trên Unix **bỏ qua** cho mục đích tra mật khẩu. Một script không tương tác khi đó có thể thất bại với lỗi thiếu mật khẩu.

Đừng chữa bằng cách đổi `pg_hba.conf` thành `trust` hoặc cấp quyền đọc file mật khẩu cho mọi user. Hãy đặt đúng quyền, owner, vị trí file và account chạy client.

### 7.1. Quyền service file có giống .pgpass không?

Nên bảo vệ `~/.pg_service.conf`, ví dụ:

```bash
chmod 600 "$HOME/.pg_service.conf"
```

Nhưng cần phân biệt: yêu cầu **bỏ qua file khi quyền group/other quá rộng** được PostgreSQL quy định trực tiếp cho **password file**. Service file không nên chứa secret, và file cấp hệ thống có thể được chia sẻ có kiểm soát. Không đồng nhất hai loại file.

### 7.2. Windows: dùng NTFS ACL

Trên Windows, libpq không áp dụng kiểm tra mode Unix `0600` tương tự; nó giả định profile đã được bảo vệ. Tuy nhiên mật khẩu vẫn là plaintext, nên cần kiểm soát **NTFS ACL**.

Lệnh PowerShell để xác định file và xem ACL:

```powershell
$file = Join-Path $env:APPDATA 'postgresql\pgpass.conf'
Write-Output $file

if (Test-Path -LiteralPath $file) {
    Get-Acl -LiteralPath $file | Format-List
}
```

File chỉ nên đọc được bởi account cần sử dụng và quản trị viên được ủy quyền. Không đặt file trong thư mục public, share rộng, repository, email hoặc ticket.

**Chú ý:** Windows Task Scheduler có thể chạy bằng account khác tài khoản đang mở PowerShell. Account đó có `APPDATA` và ACL khác; phải kiểm tra ngữ cảnh thực thi thật.

## 8. Ví dụ kết hợp hai file từ đầu đến cuối

Giả sử PostgreSQL dev chạy ở `127.0.0.1:5432`, database `inventory` và role `inventory_dev` đã tồn tại.

### Bước 1 — Tạo service file

Nội dung `~/.pg_service.conf`:

```ini
[inventory_local]
host=127.0.0.1
port=5432
dbname=inventory
user=inventory_dev
connect_timeout=5
application_name=inventory_tutorial
```

### Bước 2 — Tạo password file

Nội dung `~/.pgpass`:

```text
127.0.0.1:5432:inventory:inventory_dev:EXAMPLE_PASSWORD_REPLACE_ME
```

Thay placeholder bằng mật khẩu hợp lệ qua phương thức quản lý bí mật được chấp nhận. Đừng sao chép mật khẩu thật vào bài học hoặc Git.

### Bước 3 — Đặt quyền

```bash
chmod 600 "$HOME/.pgpass"
chmod 600 "$HOME/.pg_service.conf"
```

### Bước 4 — Test kết nối không tương tác

```bash
psql -w "service=inventory_local" \
    -c "SELECT current_database(), current_user;"
```

Tùy chọn `-w`/`--no-password` yêu cầu `psql` **không hỏi mật khẩu tương tác**. Nếu file credential chưa đúng, lệnh báo lỗi thay vì chờ người dùng gõ mật khẩu. Nó không bỏ qua kiểm tra auth của server.

### Bước 5 — Xác minh service đang được sử dụng

```bash
psql "service=inventory_local" -c "SELECT current_database();"

psql "service=inventory_local application_name=one_off_check" \
    -c "SELECT current_setting('application_name');"
```

Lệnh thứ hai ghi đè `application_name` ở phạm vi lời gọi để minh họa ưu tiên tham số trực tiếp. Đừng thêm `-h`, `-p` và `-U` tùy tiện trong lúc đang muốn kiểm chứng chính xác giá trị lấy từ service.

## 9. Sử dụng trong cron, CI và công việc sao lưu

Một tác vụ chạy được trong terminal nhưng lỗi khi chạy tự động thường do môi trường chạy khác, không phải do PostgreSQL “tự quên” service.

### 9.1. Script Bash mẫu

```bash
#!/usr/bin/env bash
set -euo pipefail

export PGSERVICEFILE=/etc/myapp/pg_services.conf
export PGPASSFILE=/etc/myapp/pg_passwords.secret

mkdir -p /var/backups/myapp

pg_dump -w -d "service=inventory_staging" \
    -Fc -f /var/backups/myapp/inventory_staging.dump
```

Trong hệ thống thật, account chạy job phải đọc được hai file và có quyền ghi thư mục backup. Password file trên Unix vẫn cần mode không cho group/other truy cập. Đường dẫn dưới `/etc` chỉ là minh họa; dùng secret store, volume/quyền và chính sách tổ chức phù hợp.

Lệnh `pg_dump` tạo bản dump logic. Nó không tự bao gồm mọi thành phần cấp cluster như global roles/tablespaces và cũng không thay thế chiến lược backup vật lý/WAL nếu yêu cầu khôi phục theo thời điểm. Kiểm tra bản sao bằng quy trình restore thực tế.

### 9.2. Vì sao cron không tìm thấy service?

Những nguyên nhân điển hình:

- Job chạy dưới account khác, nên `HOME` và file cá nhân khác.
- `PGSERVICEFILE` hoặc `PGPASSFILE` chưa được set trong job.
- Path tương đối được giải từ working directory khác.
- File password thiếu quyền đọc với account đang chạy.
- Trên Unix, password file có mode quá rộng và bị libpq bỏ qua.
- Có biến `PG*` kế thừa ngoài ý muốn, ghi đè một số thông tin.
- Client `psql`/`pg_dump` trong cron đến từ phiên bản PostgreSQL khác trong `PATH`.

Nên đặt đường dẫn tuyệt đối, xác định account, kiểm tra môi trường một cách an toàn và không ghi toàn bộ biến môi trường vào log nếu có thể chứa `PGPASSWORD` hay secret khác.

### 9.3. Windows Task Scheduler

Ví dụ PowerShell cho account chạy task:

```powershell
$env:PGSERVICEFILE = 'C:\Config\PostgreSQL\services.conf'
$env:PGPASSFILE = 'C:\Secrets\PostgreSQL\pgpass.conf'

& 'C:\Program Files\PostgreSQL\bin\psql.exe' -w "service=inventory_local" -c "SELECT 1;"
```

Đường dẫn binary chỉ là minh họa; cần thay bằng nơi cài `psql.exe` thực tế. Với Task Scheduler, cấp NTFS ACL của secret file cho đúng service account; không mặc định profile của người quản trị sẽ được dùng.

## 10. Tương tác với TLS và phân quyền server

Service có thể nêu yêu cầu bảo mật kết nối:

```ini
[prod_readonly]
host=prod-db.internal.example
port=5432
dbname=shopdb
user=report_reader
sslmode=verify-full
sslrootcert=/home/linh/.postgresql/root.crt
connect_timeout=8
```

`sslmode=verify-full` kiểm tra CA/chứng chỉ máy chủ và hostname. Nếu chứng chỉ chỉ hợp lệ cho `prod-db.internal.example` mà service đổi sang IP không được chứng nhận, việc xác minh có thể thất bại. Không bỏ xác minh TLS để chạy được nếu chính sách yêu cầu chống kết nối nhầm/máy chủ giả mạo.

**Một service không tự bảo đảm quyền chỉ đọc.** Nếu `report_reader` có quyền `INSERT`/`DELETE` do cấu hình `GRANT` sai thì tên `prod_readonly` không ngăn được thao tác. Cần tạo role quyền tối thiểu và giới hạn truy cập qua `pg_hba.conf`, firewall và xác thực thích hợp.

### 10.1. Những file không được nhầm

| File | Phía sử dụng | Mục đích |
|---|---|---|
| `.pg_service.conf` | libpq client | Nhóm tham số kết nối dưới service name |
| `.pgpass` / `pgpass.conf` | libpq client | Tra mật khẩu theo host/port/database/user |
| `postgresql.conf` | PostgreSQL server | Cấu hình listener, bộ nhớ và tham số server |
| `pg_hba.conf` | PostgreSQL server | Chính sách xác thực kết nối |
| `pg_ident.conf` | PostgreSQL server | Ánh xạ danh tính trong một số cơ chế auth |

Sửa file client **không tự thay đổi** listener hoặc quyền server. Đổi port server từ 5432 sang 5433 đòi hỏi cập nhật service file, `.pgpass`, firewall và client/monitoring có liên quan.

## 11. Client nào thực sự hỗ trợ?

| Client | Có thể dùng service/.pgpass như libpq? | Ghi chú |
|---|---|---|
| `psql` | Có | Công cụ PostgreSQL dùng libpq |
| `pg_dump` | Có | Dùng thông tin kết nối, nhưng cần quyền backup |
| `pg_restore` | Có khi kết nối trực tiếp DB | Cẩn thận vì restore thay đổi dữ liệu/schema |
| `pg_isready` | Dùng tham số libpq | Chỉ kiểm tra khả năng tiếp nhận kết nối, không thay thế test quyền |
| Ứng dụng C dùng libpq | Có | Khi truyền đúng tham số, file và môi trường |
| Driver Python dựa trên libpq | Thường có | Tùy driver/version và cách truyền DSN |
| Java PostgreSQL JDBC thuần | Không mặc định | Có cách cấu hình riêng, không suy ra từ libpq |
| GUI/ORM/driver khác | Tùy sản phẩm | Có thể dùng credential store hoặc định dạng riêng |

Vì vậy, một file được `psql` đọc thành công không phải chứng cứ rằng ứng dụng Java đang tự đọc cùng file. Phải kiểm tra tài liệu và cấu hình của thư viện kết nối thực tế.

## 12. Chẩn đoán khi service hoặc .pgpass không hoạt động

### 12.1. Không tìm thấy service

Lỗi dạng:

```text
definition of service "inventory_local" not found
```

Cần kiểm tra tên section, account OS, đường dẫn file cá nhân, `PGSERVICEFILE`, `PGSYSCONFDIR` và các service trùng tên. Nếu dùng Windows, kiểm tra tên file cá nhân **`.pg_service.conf`**, không nhầm với `pgpass.conf`.

### 12.2. Có .pgpass nhưng vẫn bị hỏi mật khẩu

Hỏi lần lượt:

1. File nằm đúng profile người chạy client?
2. Trên Unix, file có mode `0600` hoặc quyền đủ nghiêm ngặt?
3. Dòng có đúng host/port/dbname/user **sau khi áp dụng override**?
4. Dòng cụ thể có đứng trước wildcard?
5. Dấu `:` và `\` có escape đúng?
6. Có `PGPASSWORD` hoặc tham số `password` khác được ưu tiên?
7. Server thực sự yêu cầu password auth hay cơ chế khác?

Thử:

```bash
psql -w "service=inventory_local" -c "SELECT 1;"
```

`-w` giúp tác vụ nhận lỗi rõ mà không chờ prompt. Không in nội dung `.pgpass` ra log để debug.

### 12.3. Tham số đúng nhưng server từ chối

| Hiện tượng | Nơi cần kiểm tra |
|---|---|
| `Connection refused` | PostgreSQL chưa chạy, port hoặc `listen_addresses` sai |
| Timeout TCP | Route, DNS, firewall, cloud security group |
| `no pg_hba.conf entry` | Rule server cho host/user/database/SSL chưa phù hợp |
| `password authentication failed` | Mật khẩu, role hoặc cơ chế auth không đúng |
| `database does not exist` | `dbname` sai hoặc đang kết nối nhầm cluster |
| `role does not exist` | `user` sai hoặc role chưa được tạo |
| Lỗi kiểm tra certificate | CA, hostname, cert server hoặc chính sách TLS |
| `permission denied for schema/table` | Thiếu quyền SQL sau khi đăng nhập |

Đừng sửa `pg_hba.conf` thành `trust` hoặc mở toàn bộ firewall chỉ để chữa lỗi service file. Những vấn đề này thuộc các lớp kết nối khác nhau.

### 12.4. Một service trỏ nhầm môi trường

Trong hệ thống có production, lỗi nguy hiểm nhất là **kết nối thành công nhưng đến sai database**. Có thể do service tên giống trong file cá nhân và hệ thống, `PGSERVICEFILE` trỏ file khác, tham số trực tiếp ghi đè `host` hoặc DNS thay đổi.

Trước `DROP`, migration, restore hoặc thao tác chỉnh dữ liệu, luôn xác minh:

```sql
SELECT current_database(), current_user, inet_server_addr(), inet_server_port();
```

Cũng nên phân tách quyền giữa môi trường thật và môi trường test, để kết nối nhầm không lập tức có quyền phá hủy dữ liệu.

## 13. Bảo mật mật khẩu và vận hành dài hạn

`.pgpass` là giải pháp tiện lợi nhưng **lưu plaintext**. Vì vậy phải:

- Giữ quyền file/ACL chặt chẽ.
- Tránh đưa secret lên command line, Git, email, tài liệu hoặc ticket.
- Dùng role chuyên biệt, chỉ cấp quyền cần thiết.
- Kết hợp TLS khi truyền qua mạng có yêu cầu bảo mật.
- Luân chuyển password và cập nhật file cho mọi job liên quan.
- Phân biệt **trace/request ID** trong log với secret; không ghi mật khẩu khi debug.
- Kiểm tra quyền backup và nơi lưu dump vì tệp backup cũng có thể chứa dữ liệu nhạy cảm.

### 13.1. Luân chuyển mật khẩu

Khi đổi password của `report_reader` trên server, mọi client dùng dòng `.pgpass` cũ có thể xác thực thất bại. Quy trình nên gồm:

1. Lập danh sách account/job dùng credential.
2. Chuẩn bị secret mới qua phương pháp phân phối an toàn.
3. Cập nhật secret ở đúng profile/file/secret store của từng tác vụ.
4. Kiểm tra kết nối mới thành công bằng `psql -w` hoặc công cụ thực tế.
5. Thu hồi secret cũ theo quy trình; tránh để bản cũ trong file backup không bảo vệ.

Không nhầm luân chuyển mật khẩu ở server với sửa `.pgpass`: file client không có quyền tự thay đổi password của role.

### 13.2. Khi nào không nên dùng .pgpass?

Trong một số hạ tầng, tổ chức yêu cầu secret manager, mật khẩu ngắn hạn, workload identity hoặc client certificate thay vì password file cố định. Khi đó, hãy dùng cơ chế được hỗ trợ của tổ chức. Không ép mọi loại xác thực vào `.pgpass` chỉ vì ví dụ đơn giản.

Nếu cần password file riêng cho CI, ưu tiên cấp file tạm bằng secret store, phân quyền phù hợp, và dọn khi job hoàn tất. Không chèn secret trực tiếp vào workflow YAML trong repository.

## 14. Bảng kiểm trước khi đưa vào dùng chung

### 14.1. Service file

- [ ] Tên service phân biệt dev/staging/production rõ ràng.
- [ ] Biết file cá nhân hay cấp hệ thống nào đang được sử dụng.
- [ ] `host`, `port`, `dbname`, `user` đã được kiểm chứng.
- [ ] Đã thiết lập `sslmode`/CA phù hợp nếu cần TLS.
- [ ] Không lưu mật khẩu thật trong file chia sẻ hoặc Git.
- [ ] Đã hiểu tham số trực tiếp ưu tiên hơn service file và môi trường.

### 14.2. Password file

- [ ] Đúng đường dẫn của account OS chạy client.
- [ ] Mỗi dòng đủ năm trường, không nhầm thứ tự.
- [ ] Dòng cụ thể đứng trước wildcard.
- [ ] Escape đúng dấu `:` và backslash.
- [ ] Trên Unix, quyền không cho group/other truy cập; thường `0600`.
- [ ] Trên Windows, NTFS ACL chặn account không cần quyền.
- [ ] Mật khẩu không xuất hiện trong log, Git, ticket hoặc dump cấu hình.

### 14.3. Kiểm tra kết nối

- [ ] Thử `psql -w "service=..." -c "SELECT 1;"`.
- [ ] Xác minh database/role/host/port hoặc `\conninfo`.
- [ ] Chạy thử công cụ mục tiêu, ví dụ `pg_dump` dưới chính account job.
- [ ] Có kế hoạch khi đổi host, port, role hoặc mật khẩu.

## 15. Bài tập thực hành có lời giải

### Bài 1 — Tạo hai service khác nhau

**Yêu cầu:** tạo `inventory_dev` trỏ `127.0.0.1:5432`, database `inventory`, user `dev_user`; và `inventory_staging` trỏ `stg-db.internal.example:5432`, database `inventory`, user `read_user`, dùng TLS xác minh đầy đủ.

**Đáp án mẫu:**

```ini
[inventory_dev]
host=127.0.0.1
port=5432
dbname=inventory
user=dev_user

[inventory_staging]
host=stg-db.internal.example
port=5432
dbname=inventory
user=read_user
sslmode=verify-full
sslrootcert=/home/linh/.postgresql/root.crt
```

Không đặt mật khẩu trong service file. Đường dẫn CA là ví dụ, phải thay đúng file thực tế.

### Bài 2 — Tạo password file khớp service

**Đáp án mẫu:**

```text
127.0.0.1:5432:inventory:dev_user:DEV_EXAMPLE_SECRET
stg-db.internal.example:5432:inventory:read_user:STAGING_EXAMPLE_SECRET
```

Trên Unix đặt file tại `~/.pgpass` và `chmod 600`; trên Windows dùng `%APPDATA%\postgresql\pgpass.conf` với ACL thích hợp.

### Bài 3 — Ai thắng khi port khác nhau?

File service có `port=5432`, môi trường có `PGPORT=5444`, lệnh dùng:

```bash
psql "service=inventory_dev port=5433"
```

**Đáp án:** Port **5433** do tham số trực tiếp ưu tiên. Nếu bỏ `port=5433` thì dùng **5432** từ service, không phải `PGPORT=5444`.

### Bài 4 — Wildcard đứng đầu

```text
*:*:*:*:GENERIC
stg-db.internal.example:5432:inventory:read_user:SPECIFIC
```

**Đáp án:** Dòng đầu có thể khớp mọi kết nối, vì vậy `SPECIFIC` không được chọn. Phải đặt dòng cụ thể trước và hạn chế wildcard rộng.

### Bài 5 — Đã có mật khẩu mà psql vẫn hỏi

`~/.pgpass` trên Linux có mode `0644`.

**Đáp án:** File có quyền đọc cho group/other, nên libpq bỏ qua. Dùng:

```bash
chmod 600 "$HOME/.pgpass"
psql -w "service=inventory_dev" -c "SELECT 1;"
```

Nếu vẫn lỗi, kiểm tra owner, host/port/database/user cuối cùng và các nguồn `password` khác.

### Bài 6 — Hostname localhost và 127.0.0.1

Service dùng `host=127.0.0.1`; password file chỉ có:

```text
localhost:5432:inventory:dev_user:EXAMPLE
```

**Đáp án:** Không chắc khớp. `localhost` và `127.0.0.1` không cùng chuỗi khi tra host thông thường. Dùng dòng có `127.0.0.1` hoặc thiết kế quy tắc khớp rõ ràng.

### Bài 7 — Cron không thấy service

Terminal chạy `psql "service=inventory_dev"` được, nhưng cron chạy dưới user `backup` báo không tìm thấy service.

**Đáp án:** File cá nhân của user đăng nhập không tự xuất hiện trong home của user `backup`. Cần cấu hình `PGSERVICEFILE`/`PGPASSFILE` bằng đường dẫn tuyệt đối, cấp quyền đúng và kiểm tra môi trường của cron.

### Bài 8 — Đổi .pgpass có cần restart PostgreSQL không?

**Đáp án:** Không. `.pgpass` là file phía client được đọc khi mở kết nối mới. Đổi mật khẩu của role trên server là thao tác riêng; các kết nối mới cần credential tương ứng. Nếu đổi cấu hình server như `pg_hba.conf`, quy trình reload/restart lại là câu chuyện khác.

## 16. Tổng kết và tài liệu tra cứu

Ghi nhớ những nguyên tắc chính:

1. **`.pg_service.conf`** ánh xạ tên dịch vụ với host, port, database, role và các tham số kết nối khác.
2. **`.pgpass`** (Windows: `pgpass.conf`) lưu mật khẩu theo `hostname:port:database:username:password`, chọn **dòng khớp đầu tiên**.
3. **Tham số trực tiếp → service file → môi trường → mặc định** là thứ tự ưu tiên cơ bản khi dùng service.
4. **Trên Unix, password file có quyền quá rộng sẽ bị bỏ qua**; trên Windows cần ACL phù hợp.
5. **Tên service không thay thế quyền SQL, TLS hay firewall**; password file không tạo user/password ở server.
6. **Không phải mọi driver đều dùng libpq**; chỉ dùng cơ chế này khi client thực sự hỗ trợ.

Tài liệu PostgreSQL chính thức:

- [Connection Service File](https://www.postgresql.org/docs/current/libpq-pgservice.html).
- [The Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html).
- [Environment Variables](https://www.postgresql.org/docs/current/libpq-envars.html).
- [libpq Connection Strings](https://www.postgresql.org/docs/current/libpq-connect.html).

**Kết luận:** Service file giúp gọi **đúng cấu hình kết nối bằng một tên ổn định**, còn `.pgpass` cung cấp **credential đúng đích theo cách có thể tự động hóa**. Kết hợp chúng với phân quyền file, role ít đặc quyền và TLS phù hợp giúp việc vận hành `psql`, `pg_dump` và các chương trình dùng libpq đơn giản hơn mà vẫn kiểm soát được rủi ro lộ thông tin.
