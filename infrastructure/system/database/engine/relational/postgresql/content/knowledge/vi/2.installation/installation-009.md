# Kiểm tra phiên bản, đường dẫn cấu hình và nhật ký khởi động PostgreSQL

Sau khi cài PostgreSQL, ba câu hỏi đầu tiên nên trả lời là: **máy chủ nào đang thực sự chạy**, **máy chủ đó đọc cấu hình ở đâu**, và **nhật ký nào cho biết quá trình khởi động thành công hay thất bại**. Chỉ nhìn thấy lệnh `psql` chạy được hoặc một dịch vụ có trạng thái `active` chưa đủ để kết luận ứng dụng đã kết nối đúng PostgreSQL instance mong muốn.

Trên máy phát triển, có thể cùng tồn tại PostgreSQL 15 và 16; client `psql` có thể là phiên bản 17; cấu hình có thể nằm ở thư mục khác với dữ liệu; còn nhật ký có thể ở một file, systemd journal, Docker logs hoặc dịch vụ quản lý tập trung. Việc dùng sai đường dẫn hoặc sai phiên bản khi xử lý lỗi đôi khi nguy hiểm hơn lỗi ban đầu.

Bài này hướng dẫn một quy trình kiểm tra **từ kết nối SQL đang hoạt động** và **khi server chưa khởi động được**, có ví dụ cho Linux, Windows và môi trường container. Các lệnh minh họa dành cho PostgreSQL hiện đại, chủ yếu PostgreSQL 14 trở lên; tên service, đường dẫn và giao diện công cụ phụ thuộc hệ điều hành, cách đóng gói và môi trường triển khai.

## 1. Phân biệt ba nhóm thông tin cần xác minh

| Nhóm kiểm tra | Câu hỏi chính | Cách xác minh |
| --- | --- | --- |
| **Phiên bản** | PostgreSQL Server thật sự chạy major/minor nào? Client và binary cài đặt có khác không? | `SHOW server_version`, `SELECT version()`, `SHOW server_version_num`; so với `psql --version`. |
| **Đường dẫn cấu hình** | Server hiện đọc `postgresql.conf`, `pg_hba.conf` và thư mục dữ liệu ở đâu? Thay đổi cấu hình nào có hiệu lực? | `SHOW config_file`, `SHOW hba_file`, `SHOW data_directory`, `pg_settings`. |
| **Nhật ký khởi động** | Server đã lắng nghe cổng nào, đã sẵn sàng nhận kết nối chưa, hoặc dừng vì lỗi gì? | `SHOW log_destination`, `pg_current_logfile()`, log file, `journalctl`, Docker/Kubernetes logs, Windows Event Viewer. |

Một chuỗi suy luận đáng tin cậy:

```text
Tìm đúng instance
       |
       v
Xác nhận Server version + địa chỉ/cổng/database
       |
       v
Xác nhận config_file + data_directory + hba_file
       |
       v
Xác nhận cấu hình đang có hiệu lực, có chờ restart không
       |
       v
Tìm đúng nguồn log cho instance đó
       |
       v
Đọc dòng khởi động và xử lý nguyên nhân nếu có lỗi
```

Điểm đặc biệt là **thông tin do server tự trả về** thường đáng tin hơn việc phỏng đoán từ thư mục cài đặt. Nếu server chạy được, hãy hỏi chính server trước khi mở file hệ thống.

## 2. Kiểm tra phiên bản PostgreSQL Server

Mở một kết nối SQL tới server cần kiểm tra, rồi chạy:

```sql
SHOW server_version;

SHOW server_version_num;

SELECT version();
```

Ví dụ kết quả:

```text
server_version
--------------
16.4

server_version_num
------------------
160004

version()
----------------------------------------------------------
PostgreSQL 16.4 on ..., compiled by ..., 64-bit
```

Ý nghĩa:

- `server_version`: phiên bản server dạng chuỗi; dùng để lựa chọn bộ tài liệu phù hợp.
- `server_version_num`: số nguyên thuận tiện cho so sánh trong script.
- `version()`: chuỗi thông tin server chi tiết hơn, có thể chứa hệ điều hành/kiến trúc và thông tin biên dịch.

Trong PostgreSQL từ major 10 trở đi, `16.4` nghĩa là **major 16, minor 4**. Đối với PostgreSQL trước 10, cách ghi phiên bản có ba phần: ví dụ `9.6.24` có **major 9.6**, minor 24. `server_version_num` ở ví dụ `16.4` là `160004`; không nên coi phiên bản như một số thập phân để so sánh.

Một truy vấn gọn để lưu lại thông tin:

```sql
SELECT
    current_setting('server_version') AS server_version,
    current_setting('server_version_num')::integer AS server_version_num,
    version() AS build_information;
```

### 2.1. Vì sao không chỉ dùng psql --version?

Ở terminal:

```bash
psql --version
```

Lệnh này trả **phiên bản chương trình client `psql` đang được gọi**, không phải phiên bản server mà ứng dụng đã kết nối. Có thể xảy ra:

```text
Laptop: psql (PostgreSQL) 17.2
Server: PostgreSQL 16.4
```

Đây không nhất thiết là lỗi. Client và server có vòng đời triển khai riêng. Nhưng để biết một cú pháp SQL có được server hỗ trợ hay không, **phiên bản server** mới là cơ sở.

Tương tự:

```bash
postgres --version
pg_config --version
pg_dump --version
```

Các lệnh này lần lượt phản ánh binary server được tìm thấy trên `PATH`, thông tin bộ cài/build mà `pg_config` tương ứng và phiên bản công cụ `pg_dump`. Chúng **không chứng minh** tiến trình PostgreSQL hiện đang phục vụ ứng dụng dùng đúng các binary đó.

Một máy có nhiều phiên bản cài song song có thể tìm thấy `postgres` và `psql` ở hai thư mục khác nhau. Với nhiều instance, việc kiểm tra binary trên `PATH` mà không đối chiếu kết nối thực tế có thể dẫn tới chẩn đoán sai.

### 2.2. Xác nhận server được truy vấn có đúng không

Nếu kết nối thành công, ghi nhận thêm:

```sql
SELECT
    current_database() AS database_name,
    current_user AS database_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version,
    pg_postmaster_start_time() AS server_start_time;
```

`pg_postmaster_start_time()` cho biết thời điểm tiến trình postmaster hiện tại khởi động. Kết quả có ích để xác nhận một lần restart vừa diễn ra và đối chiếu với timestamp trong nhật ký.

`inet_server_addr()` hoặc `inet_server_port()` có thể là `NULL` khi kết nối qua Unix-domain socket, hoặc không phản ánh địa chỉ công khai trước proxy/load balancer. Hãy ghi nhận cả endpoint từ cấu hình ứng dụng.

Trong `psql`, có thể dùng:

```text
\conninfo
```

để xem thông tin kết nối của phiên hiện tại.

## 3. Kết nối có chủ đích đến đúng instance

Nếu PostgreSQL có nhiều cluster hoặc cổng, đừng dựa hoàn toàn vào giá trị mặc định của `psql`. Chỉ định host, port, user và database:

```bash
psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

Trong đó:

- `-X`: không đọc file khởi tạo `psqlrc`, hữu ích khi cần một phiên chẩn đoán ít bị tùy chỉnh.
- `-h 127.0.0.1`: kết nối qua TCP tới loopback thay vì mặc định chọn Unix socket trên một số hệ điều hành.
- `-p 5432`: cổng PostgreSQL mong muốn; `5432` là giá trị thường gặp, không bắt buộc cho mọi instance.
- `-U postgres`: database role dùng để đăng nhập; role này không đồng nghĩa với tài khoản hệ điều hành có cùng tên.
- `-d postgres`: database đích, cần tồn tại và tài khoản phải được phép kết nối.

Sau khi kết nối:

```sql
SHOW server_version;
SHOW port;
SHOW data_directory;
```

Một số thông số hoặc view quản trị có thể yêu cầu đặc quyền nhất định. Nếu nhận lỗi permission, dùng một tài khoản quản trị được cấp quyền theo quy trình thay vì tự nâng quyền ứng dụng bằng `SUPERUSER`.

### 3.1. Đọc thông tin trong một câu lệnh từ terminal

```bash
psql -X -h 127.0.0.1 -p 5432 -U postgres -d postgres \
  -c "SELECT current_database(), current_user, current_setting('server_version');"
```

Đoạn trên là ví dụ cú pháp dòng lệnh trên hệ shell chấp nhận dấu `\` nối dòng. Nếu dùng PowerShell hoặc Command Prompt, hãy viết lệnh trên một dòng hoặc dùng cú pháp nối dòng của shell đó.

### 3.2. Không kết nối được chưa chắc server chưa chạy

Thông báo như `connection refused` hoặc `no response` cho biết **đường kết nối được thử không thành công**, nhưng chưa xác định nguyên nhân:

- PostgreSQL có thể đang dừng.
- PostgreSQL đang nghe cổng khác.
- Server chỉ nghe trên Unix socket hoặc địa chỉ khác.
- Firewall, proxy hoặc cấu hình mạng đang chặn.
- Bạn đang thử hostname của máy khác.

Ngược lại, lỗi `password authentication failed` thường cho biết đã liên hệ được đến một PostgreSQL server nhưng thất bại ở bước xác thực. Cần phân biệt lỗi khởi động, lỗi kết nối và lỗi xác thực để tìm đúng log.

## 4. Hỏi server đường dẫn cấu hình đang được sử dụng

PostgreSQL có nhiều file cấu hình; tên file thường giống nhau trên các hệ điều hành, nhưng vị trí không cố định.

Chạy trong một kết nối có đủ quyền:

```sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW data_directory;
```

Có thể lấy trong một truy vấn:

```sql
SELECT
    current_setting('config_file') AS config_file,
    current_setting('hba_file') AS hba_file,
    current_setting('ident_file') AS ident_file,
    current_setting('data_directory') AS data_directory;
```

Ý nghĩa:

| Thông số | Đại diện cho |
| --- | --- |
| `config_file` | File cấu hình chính mà server thực sự nạp, thường tên `postgresql.conf`. |
| `hba_file` | File quy tắc xác thực kết nối, thường tên `pg_hba.conf`. |
| `ident_file` | File ánh xạ tên người dùng cho một số phương thức xác thực, thường tên `pg_ident.conf`. |
| `data_directory` | Thư mục dữ liệu của PostgreSQL cluster đang chạy; chứa tệp lưu trữ, metadata, WAL và nhiều cấu trúc nội bộ. |

Các đường dẫn do server trả về có giá trị lớn hơn việc đoán theo quy ước như `/etc/postgresql/...` hoặc `/var/lib/postgresql/...`.

### 4.1. Tại sao config_file có thể khác data_directory?

Hai cách bố trí đều có thể hợp lệ:

**Bố trí cùng một thư mục** – thường gặp khi tự khởi tạo một data directory bằng `initdb`:

```text
/srv/postgres/main/
    PG_VERSION
    postgresql.conf
    pg_hba.conf
    pg_ident.conf
    base/
    global/
    pg_wal/
    ...
```

**Bố trí tách cấu hình và dữ liệu** – thường gặp trong một số gói cài đặt Linux:

```text
/etc/postgresql/16/main/postgresql.conf
/etc/postgresql/16/main/pg_hba.conf
/var/lib/postgresql/16/main/           <- data_directory
```

Các đường dẫn chỉ để minh họa; **không** dùng chúng như mặc định chung trên mọi máy. Trong container hay máy chủ quản lý, cấu hình còn có thể được tạo từ biến môi trường, ConfigMap, volume hoặc hệ thống quản lý cấu hình.

### 4.2. File nào làm gì?

**`postgresql.conf`** cấu hình hành vi server: cổng, địa chỉ lắng nghe, bộ nhớ, logging, replication và nhiều thông số vận hành. Ví dụ:

```conf
listen_addresses = 'localhost'
port = 5432
log_min_duration_statement = '500ms'
```

**`pg_hba.conf`** quy định phương thức xác thực và các nguồn kết nối được phép. Ví dụ minh họa:

```conf
# TYPE  DATABASE   USER        ADDRESS         METHOD
host    appdb      app_user    127.0.0.1/32    scram-sha-256
```

Đây chỉ là một ví dụ về dòng HBA, **không phải khuyến nghị cho toàn bộ cấu hình**. Thứ tự các dòng trong `pg_hba.conf` quan trọng vì PostgreSQL chọn quy tắc khớp đầu tiên; chỉnh sai có thể khiến ứng dụng hoặc chính quản trị viên mất khả năng kết nối.

**`pg_ident.conf`** hỗ trợ ánh xạ danh tính hệ điều hành hoặc chứng chỉ tới database role khi một phương thức xác thực dùng map tương ứng.

### 4.3. Không nhầm PGDATA với config_file

Biến môi trường `PGDATA` hoặc tham số khởi động `-D` thường chỉ **data directory** hoặc thư mục cấu hình theo cách khởi chạy. Nhưng PostgreSQL cũng có thể được khởi động với `-c config_file=...` và một `data_directory` khai báo riêng.

Do đó:

```text
PGDATA được đặt trên shell        ≠  chắc chắn là config_file hiện hành
Thư mục cài PostgreSQL            ≠  chắc chắn là data_directory
Đường dẫn trong tài liệu gói       ≠  chắc chắn là đường dẫn server đang dùng
```

Khi server online, ưu tiên `SHOW config_file` và `SHOW data_directory` để xác nhận thực tế. Khi server offline, phải kiểm tra lệnh khởi chạy, service definition và các file cấu hình đã chuẩn bị.

## 5. Cấu hình nào thực sự có hiệu lực?

Tìm đúng `postgresql.conf` mới chỉ là bước đầu. Một giá trị còn có thể đến từ:

- Giá trị mặc định của PostgreSQL.
- File `postgresql.conf` chính.
- Những file được nhúng qua `include`, `include_if_exists` hoặc `include_dir`.
- File `postgresql.auto.conf` do `ALTER SYSTEM` quản lý, nằm trong data directory.
- Tham số dòng lệnh của tiến trình server.
- Thiết lập có hiệu lực trong session, database hoặc role cho những thông số được phép thay đổi ở phạm vi đó.

Vì vậy, việc nhìn thấy `log_min_duration_statement = 1000` trong một file không bảo đảm session đang dùng giá trị `1000`.

### 5.1. Đọc giá trị thực đang hoạt động

```sql
SHOW port;
SHOW listen_addresses;
SHOW max_connections;
SHOW shared_buffers;
SHOW log_destination;
SHOW logging_collector;
SHOW log_min_duration_statement;
```

Hoặc với `current_setting`:

```sql
SELECT
    current_setting('port') AS port,
    current_setting('max_connections') AS max_connections,
    current_setting('logging_collector') AS logging_collector;
```

Các câu trên cho biết **giá trị có hiệu lực đối với session hoặc server hiện tại** theo đặc tính của từng thông số, không nhất thiết là giá trị trong một dòng cụ thể của file.

### 5.2. Xem nguồn cấu hình qua pg_settings

`pg_catalog.pg_settings` cung cấp metadata về từng tham số. Ví dụ:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN (
    'port',
    'listen_addresses',
    'shared_buffers',
    'logging_collector',
    'log_destination',
    'log_directory',
    'log_filename',
    'log_min_duration_statement'
)
ORDER BY name;
```

Ý nghĩa của các cột:

| Cột | Cách diễn giải |
| --- | --- |
| `name`, `setting`, `unit` | Tên, giá trị và đơn vị cấu hình hiện hành. |
| `context` | Loại ngữ cảnh có thể thay đổi thông số; giúp biết nó cần restart, reload hay có thể đặt ở session. |
| `source` | Nguồn cung cấp giá trị, chẳng hạn mặc định, file cấu hình, dòng lệnh hoặc session. |
| `sourcefile`, `sourceline` | Vị trí file/dòng cấu hình, khi server và quyền truy cập cho phép hiển thị. |
| `pending_restart` | `true` khi có thay đổi trong cấu hình đang chờ restart server để áp dụng. |

Các trường `sourcefile` và `sourceline` thường bị hạn chế đối với user thường; chúng có thể là `NULL` nếu tài khoản không đủ đặc quyền hoặc thông số không lấy từ file. Vai trò quản trị hoặc quyền `pg_read_all_settings` có thể cần thiết theo phiên bản và thiết lập cụ thể.

### 5.3. Kiểm tra lỗi trong các file cấu hình

Đối với quản trị viên có quyền thích hợp:

```sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE error IS NOT NULL
ORDER BY sourcefile, sourceline;
```

`pg_file_settings` giúp tìm những lỗi liên quan đến các dòng được PostgreSQL phân tích từ file cấu hình. Nếu không có dòng lỗi, điều đó **không đủ chứng minh mọi lựa chọn cấu hình đều phù hợp nghiệp vụ**; nó chỉ hỗ trợ kiểm tra trạng thái phân tích/nạp cấu hình.

Đối với thông số nhiều nguồn hoặc bị ghi đè, có thể xem đầy đủ:

```sql
SELECT sourcefile, sourceline, name, setting, applied, error
FROM pg_file_settings
WHERE name IN ('port', 'shared_buffers', 'log_destination')
ORDER BY sourcefile, sourceline;
```

Không tự chỉnh sửa file trong `data_directory` chỉ vì thấy nó trong metadata. Cần phân biệt file cấu hình do hệ thống sinh, file của package manager và file do công cụ quản lý cấu hình điều khiển.

## 6. Reload khác gì restart?

Một số tham số PostgreSQL có thể áp dụng bằng **reload**, còn những tham số khác chỉ có hiệu lực sau **restart**.

### 6.1. Reload cấu hình

Nếu server đang hoạt động và tài khoản đủ quyền:

```sql
SELECT pg_reload_conf();
```

Hàm gửi tín hiệu yêu cầu PostgreSQL nạp lại các file cấu hình. Kết quả `true` về cơ bản cho biết tín hiệu reload đã được gửi thành công, **không phải lời bảo đảm mọi dòng mới đều được áp dụng mà không lỗi**.

Sau reload, nên:

```sql
SELECT name, setting, source, pending_restart
FROM pg_settings
WHERE name IN (
    'log_min_duration_statement',
    'shared_buffers',
    'logging_collector'
)
ORDER BY name;
```

và đọc log để tìm lỗi nạp cấu hình hoặc thông báo về yêu cầu restart.

Trên môi trường có `pg_ctl` và quyền hệ điều hành phù hợp, có thể dùng:

```bash
pg_ctl -D /path/to/data_directory reload
```

Đường dẫn trong ví dụ phải được thay bằng data directory thực tế. Nếu PostgreSQL do systemd, Windows Service, Docker hoặc Kubernetes quản lý, nên dùng cơ chế vận hành tương ứng và tuân thủ quy trình của môi trường đó.

### 6.2. Restart server

Những thông số như `shared_buffers`, `port`, `listen_addresses` hoặc `logging_collector` thường chỉ áp dụng sau khi khởi động lại server. Trong `pg_settings`, những thông số có `context = 'postmaster'` thuộc nhóm cần restart để đổi giá trị.

Ví dụ, nếu sửa:

```conf
shared_buffers = '1GB'
```

rồi chỉ gọi `pg_reload_conf()`, thay đổi có thể vẫn chờ restart. `pending_restart = true` là một tín hiệu cần xem xét.

**Restart có thể ngắt tất cả kết nối hiện tại**, làm các transaction chưa hoàn tất bị rollback và ảnh hưởng SLA. Trên hệ thống có replication/HA, restart cần được lập kế hoạch cùng vai trò primary/standby và công cụ điều phối, không thực hiện tùy tiện vì muốn một tham số áp dụng ngay.

### 6.3. ALTER SYSTEM và postgresql.auto.conf

Quản trị viên có thể thay đổi một số cấu hình qua SQL:

```sql
-- Chỉ minh họa trên môi trường lab có quyền quản trị.
ALTER SYSTEM SET log_min_duration_statement = '500ms';

SELECT pg_reload_conf();

SHOW log_min_duration_statement;
```

`ALTER SYSTEM` ghi cấu hình vào `postgresql.auto.conf` trong data directory. Đây là cách thay đổi cấu hình **lưu qua các lần khởi động**, không giống `SET` chỉ tác động tới session trong nhiều trường hợp. Những tham số cần restart vẫn phải restart dù được ghi qua `ALTER SYSTEM`.

Để thu hồi một thiết lập cụ thể do `ALTER SYSTEM` quản lý:

```sql
-- Chỉ thực hiện khi biết chính xác thay đổi cần thu hồi.
ALTER SYSTEM RESET log_min_duration_statement;
SELECT pg_reload_conf();
```

Không sửa `postgresql.auto.conf` trực tiếp bằng tay khi không có quy trình phù hợp. Nếu hệ thống đang dùng Ansible, Helm, managed-service parameter group hoặc một nguồn cấu hình tập trung, `ALTER SYSTEM` có thể gây xung đột với nguồn cấu hình chuẩn.

## 7. Nhật ký khởi động PostgreSQL nằm ở đâu?

Không có một vị trí log bắt buộc chung cho mọi bản PostgreSQL. Đường đi phụ thuộc **cấu hình PostgreSQL** và **cách tiến trình được khởi động/đóng gói**.

Các nguồn thường gặp:

| Môi trường | Nơi thường kiểm tra |
| --- | --- |
| PostgreSQL tự chạy bằng `pg_ctl` | File được chỉ định bởi `pg_ctl -l` hoặc stderr của tiến trình; file log theo cấu hình collector nếu bật. |
| systemd trên Linux | `journalctl` của đúng service/unit; có thể có file log riêng theo package. |
| Linux package với logging collector | File trong `log_directory` và tên do `log_filename` quyết định. |
| Docker | `docker logs` nếu PostgreSQL ghi ra stdout/stderr; hoặc volume/file log nếu cấu hình khác. |
| Kubernetes | `kubectl logs` của container PostgreSQL; nếu dùng file log, kiểm tra volume hoặc logging agent tương ứng. |
| Windows | File log do `logging_collector` cấu hình, stdout/stderr của service wrapper hoặc Windows Event Viewer khi được cấu hình. |
| Dịch vụ PostgreSQL được quản lý | Console/log service của nhà cung cấp; có thể không có quyền đọc file hệ điều hành. |

Một khác biệt quan trọng: thông báo rất sớm trong quá trình khởi động (trước khi cơ chế ghi log file sẵn sàng) **có thể xuất hiện trong journal, console hoặc log của service wrapper**, dù sau khi server chạy ổn định log đã được chuyển sang file khác.

## 8. Hỏi PostgreSQL cấu hình ghi log hiện hành

Khi server online, chạy:

```sql
SHOW log_destination;
SHOW logging_collector;
SHOW log_directory;
SHOW log_filename;
SHOW log_rotation_age;
SHOW log_rotation_size;
SHOW log_line_prefix;
SHOW log_min_messages;
```

Diễn giải:

- `log_destination` quyết định loại đích của thông điệp: có thể là `stderr`, `csvlog`, `syslog` hoặc những đích khác được phiên bản hỗ trợ. Ví dụ `jsonlog` được hỗ trợ từ PostgreSQL 15.
- `logging_collector` quyết định việc collector của PostgreSQL gom và ghi log ra file khi dùng các đích thích hợp như `stderr`/`csvlog`/`jsonlog`.
- `log_directory` là thư mục log khi collector ghi file. Nếu là đường dẫn tương đối, nó được hiểu tương đối với **data directory**.
- `log_filename` là mẫu tên file, có thể chứa thành phần thời gian.
- `log_rotation_age` và `log_rotation_size` liên quan thời điểm xoay file log.
- `log_line_prefix` giúp gắn timestamp, PID, database, user hoặc các thông tin cần thiết vào mỗi dòng log.

### 8.1. Kiểm tra file log hiện tại

Trong những cấu hình dùng logging collector, có thể gọi:

```sql
SELECT pg_current_logfile();
```

Để lấy theo định dạng cụ thể được hỗ trợ:

```sql
SELECT pg_current_logfile('stderr');
```

Hàm trả đường dẫn của file log hiện tại khi PostgreSQL có thể xác định được file thông qua logging collector. Nó có thể trả **NULL** nếu collector tắt, định dạng yêu cầu không được ghi ra file, hoặc thông tin file không khả dụng.

Một ví dụ cấu hình:

```text
data_directory       = /srv/postgres/main
logging_collector    = on
log_directory        = log
log_filename         = postgresql-%Y-%m-%d_%H%M%S.log
```

Với cách đặt này, file log do collector tạo thường nằm bên dưới thư mục `/srv/postgres/main/log/`, **không phải** tại một thư mục `log` tự nhiên theo working directory của terminal. Nếu `log_directory` là đường dẫn tuyệt đối, nó được sử dụng trực tiếp.

### 8.2. Khi logging_collector = off

Nếu `logging_collector = off` và `log_destination` có `stderr`, PostgreSQL ghi thông báo tới stderr. Hệ thống khởi chạy tiến trình có thể thu chúng qua:

- systemd journal;
- Docker/container runtime;
- file đích của `pg_ctl -l`;
- terminal/console hoặc service wrapper.

Trong trường hợp này, `pg_current_logfile()` có thể trả `NULL`; đó không nhất thiết là dấu hiệu PostgreSQL không ghi log. Cần tìm **đích stderr thực tế** của tiến trình.

Nếu log gửi qua `syslog`, hãy kiểm tra cấu hình syslog/journald của hệ điều hành. Đừng mặc định `logging_collector` là đường duy nhất để có nhật ký.

## 9. Nhận biết một lần khởi động thành công trong log

Ví dụ minh họa các thông báo `LOG` trong lúc server khởi động:

```text
LOG:  starting PostgreSQL 16.4 on x86_64-...
LOG:  listening on IPv4 address "127.0.0.1", port 5432
LOG:  listening on Unix socket "/var/run/postgresql/.s.PGSQL.5432"
LOG:  database system was shut down at 2026-01-10 09:14:00 UTC
LOG:  database system is ready to accept connections
```

Đây là **mẫu thông điệp minh họa**, không phải một đoạn log chắc chắn xuất hiện nguyên văn trên mọi máy. Tùy cấu hình, PostgreSQL có thể nghe IPv6, nhiều địa chỉ hoặc socket ở vị trí khác; sau một lần tắt không sạch còn có thể xuất hiện thông tin recovery/WAL replay.

Cách đọc:

1. `starting PostgreSQL ...` xác nhận tiến trình đang khởi động và cho biết phiên bản binary được chạy.
2. `listening on ...` cho biết địa chỉ và cổng/socket thực sự đang lắng nghe.
3. Các dòng recovery, checkpoint hoặc trạng thái dữ liệu giúp đánh giá giai đoạn phục hồi.
4. `database system is ready to accept connections` là dấu hiệu server đã hoàn tất giai đoạn khởi động đủ để nhận kết nối theo trạng thái hiện tại.

Nhưng **ready to accept connections không đồng nghĩa mọi ứng dụng chắc chắn đăng nhập được**. `pg_hba.conf`, TLS, user, password, database, firewall và quyền đối tượng vẫn phải phù hợp.

### 9.1. Mức độ log cần chú ý

| Mức/thông báo | Ý nghĩa thường gặp |
| --- | --- |
| `LOG` | Thông tin vận hành, khởi động, dừng, recovery, checkpoint hoặc cấu hình. |
| `WARNING` | Dấu hiệu vấn đề cần chú ý nhưng không nhất thiết dừng server. |
| `ERROR` | Một câu lệnh hoặc thao tác thất bại. |
| `FATAL` | Kết nối hoặc tiến trình gặp lỗi nghiêm trọng khiến thao tác hiện tại kết thúc; có thể xuất hiện ở lỗi xác thực client hoặc lỗi khởi động. |
| `PANIC` | Tình trạng rất nghiêm trọng khiến quá trình server phải dừng hoặc phục hồi; cần điều tra khẩn cấp. |
| `DETAIL` / `HINT` | Dữ liệu bổ sung và gợi ý cho thông báo lỗi ngay trước đó. |

Không chỉ tìm dòng `FATAL` rồi bỏ qua các dòng trước. Nguyên nhân thường nằm ở một hoặc vài dòng lân cận, ví dụ lỗi đọc file config, không thể bind port hoặc không thể truy cập data directory.

### 9.2. Timestamp, PID và dữ liệu nhạy cảm

Một cấu hình `log_line_prefix` đủ thông tin có thể giúp gắn sự kiện theo thời điểm và process. Ví dụ:

```conf
log_line_prefix = '%m [%p] %u@%d '
```

Trong đó `%m` biểu diễn timestamp, `%p` PID, `%u` tên user và `%d` database khi có thông tin tương ứng. Một số log khởi động chưa gắn với user/database nên những trường này có thể trống.

**Bảo vệ file log:** một số mức logging có thể ghi câu SQL, hostname, lỗi chứa giá trị tham số hoặc thông tin ứng dụng. Tránh vô tình đưa mật khẩu, token và dữ liệu nhạy cảm vào log. Không bật `log_statement = 'all'` lâu dài trên production chỉ để xem một lỗi khởi động nếu không đánh giá rủi ro và chi phí.

## 10. Tìm nhật ký trên Linux với systemd

Nhiều gói cài PostgreSQL trên Linux được quản lý bằng `systemd`. Đầu tiên phải biết **tên unit thực tế**.

Ví dụ trên Debian/Ubuntu, có thể gặp:

```bash
sudo systemctl status postgresql
sudo systemctl status postgresql@16-main
```

Trong một số gói Red Hat/Rocky/AlmaLinux, tên unit có thể là:

```bash
sudo systemctl status postgresql-16
```

Tên nêu trên chỉ là ví dụ theo cách đóng gói. **Không kết luận server đang chạy chỉ vì umbrella service `postgresql` hiển thị `active (exited)`**: với một số bản phân phối, unit chung quản lý các instance/unit con.

### 10.1. Xem log của đúng unit

Ví dụ với một cluster tên `16-main`:

```bash
sudo journalctl -u postgresql@16-main -b -n 200 --no-pager
```

Ý nghĩa:

- `-u`: chọn unit.
- `-b`: chỉ lấy log từ lần boot hệ điều hành hiện tại.
- `-n 200`: lấy các dòng cuối.
- `--no-pager`: in trực tiếp ra terminal.

Nếu unit thật là `postgresql-16`, thay tham số `-u` cho đúng. Có thể thêm `-f` để theo dõi log mới trong lúc khởi động một instance thử nghiệm, nhưng cần tránh làm phân tán sự chú ý khỏi những dòng báo lỗi đầu tiên.

### 10.2. Xem các cluster được gói Debian/Ubuntu quản lý

Một số hệ Debian/Ubuntu có tiện ích:

```bash
pg_lsclusters
```

Nó giúp thấy version, tên cluster, cổng, trạng thái, owner và một số đường dẫn. Đây là công cụ của hệ thống đóng gói tương ứng, **không phải tiện ích PostgreSQL phổ quát** xuất hiện trên mọi bản cài.

Với cách đóng gói Debian thường gặp, nhật ký có thể nằm ở vị trí dạng:

```text
/var/log/postgresql/postgresql-16-main.log
```

Nhưng nếu server cấu hình logging collector, chạy trong container hoặc được đóng gói khác, đường dẫn thực tế có thể khác. Hãy xác nhận qua `SHOW log_*`, service configuration hoặc công cụ hệ điều hành trước khi kết luận không có log.

### 10.3. Tìm lệnh khởi động do systemd sử dụng

```bash
sudo systemctl cat postgresql@16-main
sudo systemctl show -p ExecStart postgresql@16-main
```

Thông tin unit giúp xác định binary, cổng, data/config directory hoặc script quản lý được gọi. Nếu thấy một script wrapper, cần xem cách wrapper xác định instance chứ không suy ra mọi tham số từ tên unit.

## 11. PostgreSQL chạy độc lập bằng pg_ctl

Với một server được khởi tạo thủ công bằng `initdb` hoặc một môi trường lab, quản trị viên có thể dùng:

```bash
pg_ctl -D /srv/postgres/main status
```

Lệnh kiểm tra trạng thái của PostgreSQL instance được quản lý ở data directory chỉ định.

Khi cần minh họa cách ghi stderr ra file lúc khởi động trong **môi trường thử nghiệm**:

```bash
pg_ctl -D /srv/postgres/main \
  -l /srv/postgres/startup.log start
```

`-l` chỉ định file nhận log của tiến trình theo cách `pg_ctl` khởi chạy. Nếu PostgreSQL có logging collector, một phần log về sau có thể được chuyển sang file theo cấu hình `log_directory`/`log_filename`; còn log khởi động sớm vẫn có thể hữu ích trong file chỉ định bằng `-l`.

**Không chạy lệnh start lại trên data directory của một instance đang hoạt động**. Trước hết phải xác định service owner, trạng thái tiến trình và port; với môi trường production, các thao tác start/stop nên thực hiện qua cơ chế quản lý chính thức của instance.

### Khi server đã dừng hoàn toàn

Không thể chạy `SHOW config_file` vì không có server trả lời. Có thể:

1. Xem file cấu hình được lệnh `postgres`/`pg_ctl` hoặc service trỏ đến.
2. Kiểm tra data directory dự kiến và file `PG_VERSION`.
3. Xem binary cụ thể mà service dùng bằng `postgres --version` với **đường dẫn binary đúng**.
4. Đọc log của service, log chỉ định khi start hoặc stderr.

`PG_VERSION` là file trong data directory cho biết **major version của cluster dữ liệu**, không phải số minor của binary hiện đang chạy. Đừng dùng mỗi `PG_VERSION` để khẳng định server đã được cập nhật từ `16.4` lên `16.5`.

Nếu cần thông tin cluster offline ở mức quản trị, PostgreSQL còn có `pg_controldata`, nhưng phải dùng phiên bản công cụ và đường dẫn phù hợp; **không phải** công cụ thay thế cho việc đọc log khởi động, và không nên thử các tiện ích sửa dữ liệu khi chỉ cần chẩn đoán.

## 12. Nhật ký trên Windows

PostgreSQL có thể được cài như một Windows Service. Trong PowerShell:

```powershell
Get-Service -Name '*postgres*'
```

Để xem tên và lệnh chạy của service theo môi trường được phép:

```powershell
Get-CimInstance Win32_Service |
    Where-Object { $_.Name -like '*postgres*' } |
    Select-Object Name, State, PathName
```

Tên service thường chứa version hoặc cluster name do bộ cài đặt đặt ra; không được giả định mọi máy đều gọi là `postgresql-x64-16`.

Nếu PostgreSQL được cấu hình ghi file:

```powershell
Get-Content -Path 'C:\Path\To\PostgreSQL\data\log\postgresql.log' -Tail 100
```

Đường dẫn trên là placeholder cần thay bằng file log thực tế. Nếu cấu hình ghi vào Windows Event Log hoặc wrapper chuyển thông báo sang Event Viewer, dùng Event Viewer và lọc sự kiện theo ứng dụng/nguồn thích hợp. Khi server không chạy được, việc xem service status và Event Viewer có thể là đường chẩn đoán khả dụng nhất.

Trên Windows, quyền tài khoản chạy service đối với data directory, thư mục log, khóa riêng TLS và các file cấu hình có thể khác quyền của tài khoản người dùng đang mở PowerShell.

## 13. Nhật ký PostgreSQL trong Docker và Kubernetes

### 13.1. Docker

Trong một container cấu hình PostgreSQL ghi ra stdout/stderr, dùng:

```bash
docker logs --tail 200 pg-demo
```

Nếu container đã được đặt tên `pg-demo` và đang chạy, có thể truy vấn server bên trong:

```bash
docker exec -it pg-demo \
  psql -U postgres -d postgres \
  -c "SHOW server_version;"
```

Trong thực tế, database role và database mặc định phải đúng với image/secret đã cấu hình. Lệnh Docker không tự vượt qua PostgreSQL authentication và không chứng minh rằng port đã được publish ra host.

**Điều cần nhớ:** log của PostgreSQL trong container có thể:

- Được ghi ra stdout/stderr và hiện trong `docker logs`.
- Được collector ghi vào file trong volume.
- Được một logging agent chuyển sang hệ thống tập trung.

Nếu `docker logs` không có thông tin chi tiết, đừng vội kết luận PostgreSQL không phát log; kiểm tra cấu hình logging, volume và entrypoint script của image đang dùng.

### 13.2. Kubernetes

Với một pod PostgreSQL:

```bash
kubectl logs -n database pod/postgres-0 -c postgres --tail=200
```

Khi container vừa crash/restart, có thể xem phiên bản container trước:

```bash
kubectl logs -n database pod/postgres-0 -c postgres --previous
```

Nếu pod không tạo được container hoặc có lỗi mount/secret, dùng:

```bash
kubectl describe pod -n database postgres-0
```

Những tên namespace, pod và container ở đây chỉ là ví dụ. Với một operator quản lý PostgreSQL, hãy kiểm tra thêm custom resources và log operator để hiểu vì sao nó đã đổi cấu hình hoặc khởi động lại pod.

**Đặc biệt:** container mới có thể dùng image tag khác với PostgreSQL data directory đang mount. Một image major mới không thể mặc nhiên khởi động dữ liệu của major cũ. Hãy đối chiếu version của binary với major ghi trong data directory và quy trình upgrade của operator.

## 14. Dịch vụ PostgreSQL được quản lý trên cloud

Với một dịch vụ quản lý như Amazon RDS for PostgreSQL, Google Cloud SQL for PostgreSQL hoặc Azure Database for PostgreSQL, người dùng thường **không có shell truy cập toàn bộ hệ điều hành host**.

Bạn vẫn có thể dùng:

```sql
SHOW server_version;
SELECT version();
SHOW log_destination;
```

nhưng khả năng đọc `config_file`, `data_directory` hoặc log file có thể bị hạn chế; hệ thống quản lý thường dùng parameter group, console, API hoặc dịch vụ log trung tâm.

Trong trường hợp này:

- Xác định server instance/cluster qua console nhà cung cấp.
- Dùng tính năng xuất log chính thức của dịch vụ.
- Tra cơ chế thay đổi tham số và restart riêng của dịch vụ.
- Không giả định rằng quyền database admin trên dịch vụ tương đương superuser của PostgreSQL tự quản lý.

Với managed PostgreSQL, một phần cấu hình có thể bị khóa bởi nhà cung cấp. Nếu `SHOW` phản ánh một giá trị khác với cấu hình dự kiến, kiểm tra cả nhóm tham số hoặc policy cấp dịch vụ, không cố chỉnh file vật lý mà bạn không sở hữu.

## 15. Một công cụ kiểm tra sớm: pg_isready

`pg_isready` có thể kiểm tra trạng thái sẵn sàng của endpoint mà **không nhất thiết cần một kết nối SQL hoàn chỉnh**:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Các mã thoát phổ biến:

| Exit code | Ý nghĩa |
| ---: | --- |
| `0` | Server đang nhận kết nối. |
| `1` | Server có phản hồi nhưng hiện từ chối kết nối, ví dụ đang trong một giai đoạn khởi động. |
| `2` | Không nhận được phản hồi từ server mục tiêu. |
| `3` | Chưa thực hiện được phép thử do tham số không hợp lệ hoặc vấn đề tương tự. |

Ví dụ các kết quả dạng thông báo có thể là:

```text
127.0.0.1:5432 - accepting connections
127.0.0.1:5432 - rejecting connections
127.0.0.1:5432 - no response
```

**Giới hạn:** “accepting connections” không đồng nghĩa user/password/database của ứng dụng chắc chắn đúng hoặc câu SQL nghiệp vụ có thể chạy. Sau `pg_isready`, nên thử kết nối bằng `psql` với đúng endpoint và thông tin xác thực, rồi đọc `SHOW server_version`.

## 16. Những lỗi khởi động thường gặp và cách xác định

Đừng bắt đầu bằng sửa nhiều file đồng thời. Hãy tìm **thông điệp lỗi đầu tiên có ý nghĩa** của đúng lần khởi động và đúng instance, rồi đối chiếu version, cấu hình, data directory và quyền hệ điều hành.

### 16.1. Cổng đã được dùng

Thông điệp minh họa:

```text
LOG:  could not bind IPv4 address "127.0.0.1": Address already in use
HINT: Is another postmaster already running on port 5432?
FATAL: could not create any TCP/IP sockets
```

Khả năng:

- Một PostgreSQL instance khác đang dùng `5432`.
- Service cũ chưa dừng hẳn.
- Một tiến trình khác đang giữ cổng.

Trên Linux có thể kiểm tra, khi đủ quyền:

```bash
ss -ltnp
```

Trên Windows:

```powershell
Get-NetTCPConnection -LocalPort 5432 -ErrorAction SilentlyContinue
```

Sau đó đối chiếu process thực sự trước khi quyết định đổi port hoặc dừng dịch vụ. **Không kill một process theo PID chỉ vì nó nghe ở `5432` mà chưa xác định thuộc instance nào.**

### 16.2. Sai đường dẫn hoặc lỗi quyền đọc data directory

Thông điệp có thể chứa:

```text
could not access directory ...
Permission denied
data directory ... has invalid permissions
```

Nguyên nhân có thể gồm:

- Service chạy bằng OS user khác với người tạo dữ liệu.
- Thư mục cha hoặc volume không cho phép đọc/ghi.
- ACL/ownership của data directory sai sau sao chép hoặc restore.
- File mount dưới Docker/Kubernetes không có quyền phù hợp.

Hãy kiểm tra **tài khoản hệ điều hành chạy PostgreSQL**, quyền trên từng thư mục cha và data directory, quyền ghi thư mục log và mount options. Đừng sửa quyền thành “ai cũng đọc/ghi được” để khắc phục nhanh: database chứa dữ liệu và bí mật vận hành cần được bảo vệ.

### 16.3. Sai cấu hình trong postgresql.conf

Thông điệp có thể là:

```text
LOG:    syntax error in file ".../postgresql.conf" line ...
FATAL:  configuration file ".../postgresql.conf" contains errors
```

Hoặc tên tham số không hợp lệ, giá trị vượt giới hạn, cổng ngoài dải được phép, dấu nháy không khớp.

Cách xử lý:

1. Tìm chính xác `config_file` mà service đang đọc.
2. Đọc dòng và các file `include` liên quan.
3. So sánh với bản cấu hình đã chạy được trước đó.
4. Sửa đúng lỗi trong môi trường được quản lý.
5. Khởi động theo cơ chế service thích hợp và kiểm tra lại log.

Nếu server vẫn chạy và lỗi chỉ xuất hiện khi reload, `pg_file_settings` và `pg_settings.pending_restart` có thể hỗ trợ xác định lỗi; nếu không khởi động được thì phải đọc log/stderr và file ngoài hệ thống.

### 16.4. Data directory thuộc major khác với binary

Một thông báo thường gặp ở lỗi này:

```text
FATAL: database files are incompatible with server
DETAIL: The data directory was initialized by PostgreSQL version ...
```

Ví dụ: data directory được khởi tạo bằng major 16 nhưng process chạy binary PostgreSQL 17.

**Không sửa tay file `PG_VERSION` để đánh lừa server.** Định dạng dữ liệu và cơ chế WAL có thể không tương thích giữa các major. Hãy chọn binary đúng major để khởi động dữ liệu hiện tại hoặc thực hiện quy trình major upgrade được PostgreSQL hỗ trợ, ví dụ `pg_upgrade` hay dump/restore tùy kế hoạch.

### 16.5. Không đủ dung lượng lưu trữ

Thông điệp có thể chứa:

```text
No space left on device
could not write file ...
could not create file ...
```

Kiểm tra data volume, WAL volume, vị trí file log và filesystem chứa temporary files. Khi disk đầy, PostgreSQL có thể không tạo được file, ghi WAL hoặc mở rộng dữ liệu. Đừng xóa tùy tiện file trong `pg_wal` hoặc thư mục dữ liệu để lấy chỗ trống; việc đó có thể phá vỡ tính toàn vẹn database và khả năng phục hồi.

Phương án xử lý phải xuất phát từ nguyên nhân cụ thể: giải phóng dung lượng ở nơi an toàn, mở rộng volume, xử lý retention log/backup theo quy trình hoặc khôi phục phù hợp.

### 16.6. postmaster.pid và instance đang chạy

Lỗi minh họa:

```text
FATAL: lock file "postmaster.pid" already exists
HINT: Is another postmaster (PID ...) running in data directory ...?
```

`postmaster.pid` là một phần cơ chế xác định instance đang sử dụng data directory. **Không xóa file này theo phản xạ.** Trước tiên xác minh:

- PostgreSQL có đang chạy thật và đang dùng đúng data directory đó không?
- PID ghi trong file có thuộc process đang sống không?
- Service/cluster manager nào đang sở hữu instance?
- Có tình huống recovery hoặc restart chưa hoàn tất không?

Chỉ sau khi đã xác minh chắc chắn không còn tiến trình sử dụng dữ liệu mới cân nhắc quy trình xử lý stale PID theo tài liệu và runbook của hệ thống. Xóa nhầm trong lúc server khác đang sử dụng data directory có thể dẫn đến hư hỏng dữ liệu nghiêm trọng.

### 16.7. Lỗi pg_hba.conf hoặc xác thực

Ví dụ:

```text
FATAL: no pg_hba.conf entry for host ..., user ..., database ...
FATAL: password authentication failed for user ...
```

Những thông báo này thường xuất hiện khi server **đã có khả năng xử lý yêu cầu kết nối**, nhưng account, source host, SSL mode hoặc phương thức xác thực không phù hợp.

Kiểm tra:

```sql
SHOW hba_file;
```

Nếu có quyền quản trị trên server đang chạy, có thể xem:

```sql
SELECT line_number, type, database, user_name,
       address, auth_method, error
FROM pg_hba_file_rules
ORDER BY line_number;
```

`pg_hba_file_rules` giúp quan sát các quy tắc HBA đã được phân tích từ file. Kiểm tra lỗi, thứ tự dòng và phạm vi host. Sau khi sửa HBA trên hệ thống cần reload theo quy trình thích hợp; việc reload/áp dụng HBA có khác biệt nền tảng trong một số trường hợp. Không mở mọi nguồn kết nối hoặc dùng `trust` rộng chỉ để tránh lỗi password.

### 16.8. Hạn chế tài nguyên hoặc lỗi phục hồi

Nhật ký có thể cho biết không cấp phát được shared memory, không có đủ tài nguyên, không đọc được WAL, cần recovery hoặc cấu hình checkpoint không phù hợp.

Những lỗi này đòi hỏi đọc **nguyên thông điệp, DETAIL/HINT, trạng thái storage và cấu hình**. Với dữ liệu sản xuất, đừng dùng các tiện ích sửa chữa cấp thấp hoặc xóa WAL theo mẹo trên Internet khi chưa có backup và quy trình phục hồi được phê duyệt.

## 17. Phân biệt lỗi khởi động server và lỗi của ứng dụng

Không phải lỗi kết nối PostgreSQL nào cũng có nguyên nhân ở startup. Ví dụ:

| Biểu hiện | Phân loại ban đầu | Bước xác minh |
| --- | --- | --- |
| `pg_isready`: no response | Server/đường kết nối chưa phản hồi | Kiểm tra service, port, network và log khởi động. |
| `FATAL: database files are incompatible with server` | Binary/cluster major không khớp | Đối chiếu phiên bản binary và data directory. |
| `database system is ready to accept connections`, nhưng client không vào được | Có thể là authentication/network/database | Kiểm tra endpoint, HBA, user, password và firewall. |
| `password authentication failed` | Xác thực bị từ chối | Kiểm tra role, secret, HBA, SSL và nguồn kết nối. |
| `database "appdb" does not exist` | Database đích chưa có hoặc sai tên | Kết nối database đúng, xem danh sách database qua account đủ quyền. |
| `relation "orders" does not exist` | Lỗi schema/search_path/truy vấn | Kiểm tra database, schema, migration, `search_path`. |
| Server vừa khởi động lại, ứng dụng lỗi connection reset | Kết nối cũ bị ngắt | Kiểm tra pool, retry và log thời điểm restart. |

Một log startup cho biết server sẵn sàng không bảo đảm migration đã chạy, quyền ứng dụng đúng hoặc endpoint phía trước proxy luôn khỏe. Cần chẩn đoán theo **tầng gây lỗi**.

## 18. Một quy trình kiểm tra không làm thay đổi dữ liệu

Phần lớn thông tin trong bài có thể kiểm tra **read-only**. Một quy trình an toàn trên instance đang hoạt động:

### Bước 1: định danh endpoint

```sql
SELECT
    current_database() AS db,
    current_user AS db_user,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    pg_postmaster_start_time() AS started_at;
```

Ghi nhận tên môi trường và endpoint ứng dụng dùng. Nếu có proxy hoặc load balancer, đối chiếu thêm thành viên thực tế.

### Bước 2: xác nhận version

```sql
SHOW server_version;
SHOW server_version_num;
SELECT version();
```

Không lấy version từ thông tin package hoặc image tag thay cho version server đang chạy.

### Bước 3: xác định file cấu hình và data directory

```sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW data_directory;
```

Nếu thiếu quyền, nhờ quản trị viên xác minh thay vì dùng account ứng dụng để chỉnh cấu hình.

### Bước 4: đọc giá trị hoạt động và trạng thái pending restart

```sql
SELECT
    name, setting, unit, context, source, pending_restart
FROM pg_settings
WHERE name IN (
    'port', 'listen_addresses', 'max_connections',
    'shared_buffers', 'logging_collector',
    'log_destination', 'log_directory', 'log_filename'
)
ORDER BY name;
```

Nếu đã đổi cấu hình nhưng giá trị hoạt động chưa đúng, kiểm tra `source`, `pending_restart` và log reload/restart.

### Bước 5: xác định đích log

```sql
SHOW logging_collector;
SHOW log_destination;
SHOW log_directory;
SHOW log_filename;

SELECT pg_current_logfile();
```

Nếu `pg_current_logfile()` trả `NULL`, xem stderr/journal/container logging hoặc đích log khác tương ứng.

### Bước 6: đối chiếu log và thời gian khởi động

Tìm những dòng quanh `pg_postmaster_start_time()`:

```text
starting PostgreSQL ...
listening on ...
database system is ready to accept connections
```

Nếu không có dòng “ready”, xem thông điệp lỗi trước đó và kiểm tra service state. Nếu server đang chạy từ lâu, log của lần khởi động có thể đã được rotate/đưa vào hệ thống lưu trữ, nên cần tìm theo timestamp và chính sách retention.

### Bước 7: thử khả năng kết nối như ứng dụng

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Sau đó, dùng đúng account và database của ứng dụng để thực hiện một truy vấn đọc đơn giản, nếu được cho phép. Chỉ xác nhận port mở chưa đủ; còn cần kiểm tra xác thực và quyền trên database đích.

## 19. Bài thực hành trên một PostgreSQL lab

Các bài sau yêu cầu một instance PostgreSQL thử nghiệm. Các câu đọc thông tin không sửa dữ liệu; những thao tác khởi động và chỉnh cấu hình nên làm trên môi trường học tập được phép.

### Bài 1. Phân biệt version server và client

Trên terminal:

```bash
psql --version
```

Trong `psql` đã kết nối:

```sql
SHOW server_version;
SHOW server_version_num;
```

**Yêu cầu:** ghi ba giá trị. Nếu `psql --version` không giống `server_version`, giải thích tại sao điều đó không nhất thiết là lỗi.

**Gợi ý:** client có phiên bản riêng; server mới là nơi phân tích cú pháp và xử lý câu SQL.

### Bài 2. Phân biệt config và data directory

```sql
SELECT
    current_setting('config_file') AS config_file,
    current_setting('data_directory') AS data_directory;
```

**Yêu cầu:** kiểm tra hai đường dẫn có nằm trong cùng một thư mục không. Nếu khác, xác định cách cài đặt quản lý file cấu hình.

**Gợi ý:** nhiều bản cài Linux tách thư mục cấu hình và dữ liệu; không nên suy ra một vị trí mặc định chung.

### Bài 3. Tìm nguồn cấu hình

```sql
SELECT name, setting, context, source, pending_restart
FROM pg_settings
WHERE name IN ('shared_buffers', 'port', 'log_min_duration_statement')
ORDER BY name;
```

**Yêu cầu:** cho biết thông số nào cần restart và thông số nào có thể áp dụng bằng reload/session theo `context`.

**Gợi ý:** `shared_buffers` và `port` thường cần restart vì thuộc ngữ cảnh `postmaster`. `log_min_duration_statement` có thể được áp dụng theo các cơ chế cấu hình hỗ trợ mà không bắt buộc restart server.

### Bài 4. Xác định nguồn nhật ký

```sql
SHOW logging_collector;
SHOW log_destination;
SHOW log_directory;
SELECT pg_current_logfile();
```

**Yêu cầu:** xác định log ở file PostgreSQL hay ở nguồn stderr/journal/container.

**Gợi ý:** nếu collector tắt và hàm current logfile trả `NULL`, hãy kiểm tra cách service/container thu stderr thay vì tìm một file mặc định tưởng tượng.

### Bài 5. Kiểm tra đường kết nối

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Nếu lệnh báo “no response”, hãy liệt kê ít nhất ba giả thuyết trước khi sửa cấu hình.

**Gợi ý:** server dừng, cổng sai, không lắng nghe TCP trên địa chỉ đó, firewall hoặc địa chỉ đích sai.

### Bài 6. Lỗi sau khi đổi port

Một quản trị viên sửa `postgresql.conf`:

```conf
port = 5433
```

sau đó chỉ chạy `SELECT pg_reload_conf();` và thấy server vẫn nghe cổng `5432`.

**Giải thích:** `port` là thông số cần restart, không được áp dụng chỉ bằng reload. Kiểm tra `pg_settings.pending_restart`, lập kế hoạch restart rồi xác nhận `SHOW port` và log `listening on ...`.

### Bài 7. Nghi vấn “server đang chạy binary sai”

Terminal báo:

```text
postgres --version    -> PostgreSQL 17.x
SHOW server_version   -> PostgreSQL 16.x
```

**Giải thích:** lệnh `postgres --version` có thể tìm thấy binary khác trên `PATH` so với instance đang chạy. Trước khi làm gì với data directory, hãy xác định lệnh khởi động của service và binary gắn với process. Không tự đổi binary của server đang chạy chỉ để hai lệnh in ra cùng số version.

### Bài 8. Phân loại lỗi theo log

Các tình huống:

1. `Address already in use`.
2. `database files are incompatible with server`.
3. `no pg_hba.conf entry`.
4. `No space left on device`.
5. `database system is ready to accept connections`.

**Đáp án:**

1. Cần xem port/process hoặc địa chỉ lắng nghe.
2. Cần xem major version của binary và data directory.
3. Chủ yếu là lớp xác thực/kết nối, không chứng minh khởi động thất bại.
4. Cần kiểm tra filesystem/volume/WAL/log và quy trình giải phóng an toàn.
5. Là dấu hiệu server đã đạt trạng thái nhận kết nối, nhưng chưa bảo đảm mọi client/ứng dụng truy cập được.

## 20. Những nhầm lẫn cần tránh

**Nhầm lẫn 1: “`psql --version` là phiên bản của database đang chạy.”** Không. Đó là phiên bản client; kiểm tra server qua `SHOW server_version`.

**Nhầm lẫn 2: “File `postgresql.conf` luôn ở data directory.”** Không. Nhiều gói cài tách thư mục cấu hình và dữ liệu, và server có thể được cấp `config_file` rõ ràng.

**Nhầm lẫn 3: “Tôi đã sửa đúng file nên cấu hình chắc chắn áp dụng.”** Chưa chắc. File có thể bị override, có include khác hoặc giá trị đang chờ restart. Dùng `pg_settings` và log.

**Nhầm lẫn 4: “`pg_reload_conf() = true` tức mọi cấu hình đã thành công.”** Không. Nó xác nhận yêu cầu reload được gửi; còn phải kiểm tra giá trị hoạt động, `pending_restart` và lỗi log.

**Nhầm lẫn 5: “`logging_collector = off` nghĩa là PostgreSQL không có log.”** Không. Log có thể được gửi qua stderr, systemd journal hoặc container runtime.

**Nhầm lẫn 6: “`pg_current_logfile() = NULL` nghĩa là startup không có lỗi.”** Không. Hàm có thể không trả file vì cơ chế thu log khác, ngay cả khi service có lỗi trong journal.

**Nhầm lẫn 7: “systemctl báo active là ứng dụng chắc chắn hoạt động.”** Không. Cần xem đúng instance/unit, port, tính sẵn sàng và khả năng xác thực từ ứng dụng.

**Nhầm lẫn 8: “`PG_VERSION` cho biết bản vá minor của server.”** Không. Nó phục vụ định dạng cluster dữ liệu ở mức major, không thay thế `SHOW server_version` hoặc binary version.

**Nhầm lẫn 9: “Xóa postmaster.pid sẽ chữa mọi lỗi lock file.”** Rất nguy hiểm. Phải xác minh chắc chắn không còn tiến trình sử dụng data directory trước khi xử lý file PID tồn dư.

**Nhầm lẫn 10: “Xóa file WAL là cách dọn dung lượng an toàn.”** Không. WAL gắn với phục hồi và tính toàn vẹn; xóa tùy tiện có thể làm hỏng database.

**Nhầm lẫn 11: “Nhật ký startup luôn nằm ở file PostgreSQL.”** Có thể nằm ở journal, Windows Event Viewer, container logs hoặc log dịch vụ quản lý.

**Nhầm lẫn 12: “Server ready thì mọi SQL đều đúng.”** Ready chỉ xác nhận khả năng chấp nhận kết nối ở một mức nào đó; authentication, migration, quyền, schema và logic ứng dụng vẫn cần kiểm tra riêng.

## 21. Kết luận

Để kiểm tra một bản cài PostgreSQL, hãy luôn phân biệt **binary cài trên máy**, **client đang chạy** và **server thực sự được ứng dụng kết nối**. Khi server hoạt động, các lệnh `SHOW server_version`, `SHOW config_file`, `SHOW data_directory`, `SHOW hba_file` và truy vấn `pg_settings` là điểm bắt đầu đáng tin cậy. Để xác định log, kiểm tra `log_destination`, `logging_collector`, `log_directory`, `pg_current_logfile()` và nguồn logging của hệ điều hành/container.

Khi PostgreSQL không thể khởi động, SQL không khả dụng; lúc đó chuyển sang **service definition, đúng binary, đúng data directory và log của lần startup thất bại**. Đọc thông điệp đầu tiên giải thích nguyên nhân trước khi thay đổi cấu hình, tránh xóa `postmaster.pid` hay dữ liệu/WAL theo phỏng đoán. Cuối cùng, kiểm tra từ góc nhìn ứng dụng qua đúng host, port, user và database để khẳng định instance đã sẵn sàng phục vụ.

Một chẩn đoán PostgreSQL tốt không bắt đầu bằng “thử sửa vài tham số”, mà bắt đầu bằng **xác nhận đúng máy chủ, đúng phiên bản, đúng file cấu hình và đúng dòng nhật ký**.
