# Vai trò của postgresql.conf, pg_hba.conf và pg_ident.conf trong PostgreSQL

Khi một ứng dụng không kết nối được PostgreSQL, nguyên nhân có thể rất khác nhau: server chưa lắng nghe ở địa chỉ mạng cần thiết, quy tắc xác thực không cho phép nguồn kết nối, mật khẩu không khớp, hoặc người dùng hệ điều hành không được ánh xạ tới vai trò PostgreSQL mà ứng dụng yêu cầu. Mỗi trường hợp liên quan tới một lớp cấu hình khác nhau.

Ba tệp quan trọng trong cấu hình một PostgreSQL instance là:

- `postgresql.conf`: cấu hình **cách server hoạt động**, ví dụ địa chỉ lắng nghe, cổng, bộ nhớ, ghi log và nhiều tham số vận hành.
- `pg_hba.conf`: xác định **kết nối nào được phép thử xác thực và phải dùng phương thức xác thực gì**, dựa trên kiểu kết nối, database, role và địa chỉ phía client.
- `pg_ident.conf`: định nghĩa **cách ánh xạ danh tính bên ngoài** (chẳng hạn người dùng hệ điều hành) sang một PostgreSQL role khi phương thức xác thực hỗ trợ user mapping.

Ba tệp **bổ sung nhưng không thay thế nhau**. Mở cổng bằng `listen_addresses` không tự cấp quyền kết nối; có dòng `pg_hba.conf` phù hợp không tự cấp quyền `SELECT`; và khai báo `pg_ident.conf` không tạo ra PostgreSQL role.

Bài học hướng dẫn vai trò từng tệp, vị trí thực tế, nguyên tắc ưu tiên, reload/restart, những ví dụ dễ gặp và phương pháp chẩn đoán an toàn trên PostgreSQL.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Mô tả đúng luồng kết nối từ ứng dụng tới PostgreSQL, chỉ ra vai trò từng tệp cấu hình.
2. Tìm đường dẫn hiệu lực của `postgresql.conf`, `pg_hba.conf`, `pg_ident.conf` bằng SQL, thay vì đoán theo bản phân phối hệ điều hành.
3. Phân biệt các thiết lập cần **reload**, cần **restart**, hoặc có thể thay đổi trong một session.
4. Đọc các dòng `local`, `host`, `hostssl`, `hostnossl` và quy tắc **dòng khớp đầu tiên** trong `pg_hba.conf`.
5. Thiết lập tài khoản đăng nhập có mật khẩu SCRAM cho kết nối TCP và hiểu yêu cầu TLS.
6. Giải thích `peer` và `ident`, đồng thời xây dựng một ví dụ `pg_ident.conf` ánh xạ người dùng hệ điều hành sang database role.
7. Kiểm tra cấu hình bằng `SHOW`, `pg_settings`, `pg_file_settings`, `pg_hba_file_rules`, `pg_ident_file_mappings`.
8. Nhận diện lỗi mạng, xác thực và phân quyền SQL khác nhau; sửa đúng lớp cấu hình.
9. Thực hiện thay đổi an toàn, có phương án giữ đường quản trị và hoàn tác.

Các ví dụ dùng PostgreSQL hiện đại trên Linux/Unix để minh họa xác thực socket. Trên Windows, container hoặc dịch vụ PostgreSQL được quản lý, vị trí tệp và các cách xác thực khả dụng có thể khác.

---

## 2. Bức tranh tổng thể: điều gì xảy ra khi một client kết nối?

Giả sử ứng dụng muốn đăng nhập PostgreSQL role `app_login` vào database `appdb` trên máy `db.internal` qua cổng 5432.

Một luồng đơn giản:

```text
Ứng dụng / psql
    |
    | TCP đến db.internal:5432 hoặc Unix-domain socket
    v
[PostgreSQL server đang lắng nghe?]
    |
    | Tác động từ postgresql.conf:
    | listen_addresses, port, ssl, ...
    v
[Kết nối đi vào server]
    |
    | pg_hba.conf:
    | kiểu local/host/hostssl
    | database, role, IP client
    | => chọn một quy tắc xác thực
    v
[Thực thi phương thức xác thực]
    |
    | password / scram-sha-256 / peer /
    | cert / ident / phương thức khác
    |
    | pg_ident.conf (nếu dùng user mapping)
    v
[Đã xác thực danh tính PostgreSQL role]
    |
    | Role phải tồn tại, được LOGIN,
    | quyền CONNECT và quyền trên đối tượng
    v
[Session được thiết lập; ứng dụng gửi SQL]
    |
    | GRANT, REVOKE, RLS, schema/table privileges...
    v
[Đọc/ghi dữ liệu theo quyền thực tế]
```

Ở đây có ít nhất **bốn câu hỏi độc lập**:

| Câu hỏi | Nguồn kiểm soát chính |
| --- | --- |
| Server có nhận kết nối tới địa chỉ/cổng đó không? | `postgresql.conf`, trạng thái service, mạng/firewall |
| Client này phải xác thực theo cách nào? | `pg_hba.conf` |
| Danh tính bên ngoài có được dùng để đăng nhập role PostgreSQL khác tên không? | `pg_ident.conf` khi phương thức hỗ trợ mapping |
| Sau đăng nhập được phép truy cập database/bảng nào? | Role, `LOGIN`, `CONNECT`, `GRANT`, `REVOKE`, RLS và chính sách SQL khác |

**Không dùng `pg_hba.conf` thay cho quyền truy cập bảng**. Nó nằm ở giai đoạn kết nối/xác thực, trước khi ứng dụng bắt đầu chạy truy vấn nghiệp vụ.

## 3. Ba tệp có cùng chức năng không?

Không. Hãy xem bảng đối chiếu:

| Tệp | Mục đích | Ví dụ nội dung | Đọc khi nào? |
| --- | --- | --- | --- |
| `postgresql.conf` | Tham số hoạt động của instance | `listen_addresses`, `port`, `shared_buffers`, `log_min_duration_statement` | Khởi động và/hoặc khi reload, tùy từng tham số |
| `pg_hba.conf` | Quy tắc xác thực kết nối client | `hostssl appdb app_login 10.20.1.0/24 scram-sha-256` | Khi kết nối mới được kiểm tra; cấu hình được nạp khi startup/reload theo nền tảng |
| `pg_ident.conf` | Ánh xạ username bên ngoài sang PostgreSQL role | `appmap appsvc app_login` | Khi cần user mapping cho phương thức xác thực; cấu hình được nạp khi startup/reload |

Các tệp này được quản lý theo **instance/cluster PostgreSQL**, không phải tự động tạo một tệp riêng cho mỗi database ứng dụng.

Có thể thay đổi hành vi một session bằng lệnh SQL `SET` đối với các tham số cho phép; điều đó không biến `pg_hba.conf` hay `pg_ident.conf` thành SQL object của database.

---

## 4. Tìm đúng vị trí của các tệp đang được sử dụng

Không nên đoán rằng PostgreSQL luôn đặt các tệp trong `/var/lib/postgresql/data/`. Cách cài đặt qua package Linux, source, Docker, Kubernetes hay dịch vụ quản lý có thể thay đổi đường dẫn.

Kết nối bằng role có quyền xem thông tin cấu hình phù hợp:

```sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW data_directory;
```

Hoặc:

```sql
SELECT
    current_setting('config_file') AS config_path,
    current_setting('hba_file') AS hba_path,
    current_setting('ident_file') AS ident_path;
```

Một số setting nhạy cảm hoặc thông tin đường dẫn có thể bị hạn chế với người dùng thường; cần dùng tài khoản quản trị/giám sát được ủy quyền phù hợp.

### 4.1. Phân biệt data directory và config directory

`data_directory` là thư mục dữ liệu của instance. Nó có thể **khác thư mục chứa `postgresql.conf`**. Ví dụ trong một số bản phân phối Linux, cấu hình nằm dưới `/etc/postgresql/...` còn dữ liệu nằm dưới `/var/lib/postgresql/...`.

Vì vậy, thao tác đúng là:

1. Xác định PostgreSQL instance bạn đang kết nối.
2. Chạy `SHOW config_file`, `SHOW hba_file`, `SHOW ident_file`.
3. Dùng đường dẫn thật do instance trả về.
4. Kiểm tra bạn có quyền chỉnh tệp ở đúng host/container không.
5. Dự phòng cấu hình hiện tại trước khi sửa.

Một máy có thể chạy **nhiều PostgreSQL cluster hoặc container**. Sửa nhầm tệp của cluster khác có thể không thay đổi hệ thống bạn đang chẩn đoán.

### 4.2. Nếu dùng PostgreSQL managed service

Với dịch vụ PostgreSQL được quản lý, bạn có thể không được sửa trực tiếp các tệp trên filesystem. Nhà cung cấp có thể dùng parameter group, cấu hình instance hoặc giao diện riêng để thay đổi tham số/hạn chế mạng.

Dù cú pháp SQL và khái niệm tương tự, **khả năng chỉnh tệp, reload, restart và chính sách TLS phụ thuộc nhà cung cấp**. Không cố tìm cách can thiệp filesystem của dịch vụ mà bạn không được cấp quyền quản trị.

---

## 5. `postgresql.conf`: tham số vận hành của server

Tệp `postgresql.conf` chứa nhiều tham số được biểu diễn dưới dạng `ten_tham_so = gia_tri`. Dòng bắt đầu bằng `#` thường là chú thích.

Ví dụ **minh họa**, không phải cấu hình cần chép nguyên vào production:

```conf
# PostgreSQL server settings (example only)

listen_addresses = 'localhost'
port = 5432

max_connections = 100
shared_buffers = '256MB'

password_encryption = 'scram-sha-256'
log_min_duration_statement = '500ms'
```

### 5.1. Nhóm tham số kết nối

| Tham số | Ý nghĩa |
| --- | --- |
| `listen_addresses` | Danh sách địa chỉ mạng trên máy **server** mà PostgreSQL lắng nghe qua TCP |
| `port` | Cổng TCP PostgreSQL phục vụ, thường là 5432 |
| `max_connections` | Giới hạn kết nối đồng thời theo cấu hình |
| `unix_socket_directories` | Vị trí Unix-domain socket khi nền tảng hỗ trợ |
| `ssl` | Điều khiển hỗ trợ kết nối TLS theo cấu hình và khả năng cài đặt |

Một điểm quan trọng: `listen_addresses` nói về **địa chỉ IP gắn với server**, không phải danh sách IP client được phép kết nối.

Ví dụ:

```conf
# Server chỉ lắng nghe ở loopback trên máy server:
listen_addresses = 'localhost'
```

Khi đó một client ở máy khác có thể không thể kết nối qua TCP, dù `pg_hba.conf` có dòng `host all all 10.20.1.0/24 ...`.

Nếu server có địa chỉ nội bộ `10.20.0.10`, một cấu hình minh họa để nhận kết nối qua giao diện đó là:

```conf
listen_addresses = 'localhost,10.20.0.10'
```

Địa chỉ phải thực sự có trên máy server; cần cấu hình tường lửa, route và `pg_hba.conf` tương ứng. Đây không phải lời khuyên mở PostgreSQL trên mọi interface trong production.

`listen_addresses = '*'` là cách yêu cầu lắng nghe trên mọi giao diện khả dụng, **không** có nghĩa tất cả client đều xác thực thành công; nó làm tăng bề mặt kết nối nên cần được đánh giá cẩn thận.

### 5.2. Nhóm bộ nhớ và tài nguyên

Ví dụ:

```conf
shared_buffers = '256MB'
work_mem = '4MB'
maintenance_work_mem = '64MB'
max_connections = 100
```

- `shared_buffers`: vùng đệm chung của PostgreSQL cho những trang dữ liệu thường được truy cập; đây không phải toàn bộ RAM mà PostgreSQL có thể dùng.
- `work_mem`: giới hạn bộ nhớ cơ bản cho những thao tác như sort/hash theo ngữ cảnh; một truy vấn hoặc nhiều phiên có thể dùng **nhiều** vùng làm việc, không phải chỉ một lần `work_mem` cho toàn server.
- `maintenance_work_mem`: ngân sách bộ nhớ cho một số thao tác bảo trì.
- `max_connections`: số kết nối tối đa được cấu hình, có ảnh hưởng tới tài nguyên server.

Không có bộ tham số “chuẩn” cho mọi hệ thống. Việc tăng `work_mem` bừa bãi trên một server nhiều kết nối có thể gây áp lực RAM đáng kể; tăng `max_connections` không nhất thiết làm hệ thống chịu tải tốt hơn.

### 5.3. Nhóm ghi log và khả năng quan sát

Ví dụ:

```conf
log_min_duration_statement = '500ms'
log_lock_waits = on
```

- `log_min_duration_statement` có thể ghi lại những statement vượt ngưỡng thời gian cấu hình, hữu ích khi điều tra truy vấn chậm.
- `log_lock_waits` giúp ghi một số tình huống chờ khóa lâu theo cơ chế log liên quan.

Ghi log quá chi tiết có chi phí I/O, dung lượng và có thể chứa dữ liệu nhạy cảm trong SQL. Chỉ bật mức cần thiết và thiết kế chính sách lưu log phù hợp.

### 5.4. PostgreSQL lấy giá trị hiệu lực từ đâu?

Giá trị một tham số **không nhất thiết chỉ đến từ một dòng trong `postgresql.conf`**. Nguồn có thể gồm:

- Giá trị mặc định của PostgreSQL.
- Tệp cấu hình chính và các tệp được include.
- Tệp `postgresql.auto.conf` do `ALTER SYSTEM` quản lý.
- Tham số khởi động server, chẳng hạn lựa chọn `-c` từ tiến trình khởi chạy.
- Thiết lập cho database/role như `ALTER DATABASE ... SET` hoặc `ALTER ROLE ... SET` khi tham số cho phép.
- Thiết lập session bằng `SET` cho những tham số được phép thay đổi ở session.

**Vì vậy, việc sửa `postgresql.conf` mà không thấy giá trị thay đổi không tự chứng minh reload hỏng.** Có thể một nguồn có ưu tiên cao hơn đang đặt giá trị khác.

---

## 6. Xem tham số hiệu lực bằng SQL

Trước khi thay đổi file, hãy xem server thực sự đang dùng giá trị nào:

```sql
SHOW listen_addresses;
SHOW port;
SHOW max_connections;
SHOW shared_buffers;
SHOW work_mem;
SHOW password_encryption;
```

View `pg_settings` giúp xem chi tiết hơn:

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
    'listen_addresses',
    'port',
    'max_connections',
    'shared_buffers',
    'work_mem',
    'password_encryption',
    'log_min_duration_statement'
)
ORDER BY name;
```

Những cột cần chú ý:

| Cột | Ý nghĩa |
| --- | --- |
| `name` | Tên tham số |
| `setting` | Giá trị có hiệu lực theo cách thể hiện của view |
| `unit` | Đơn vị nội bộ hoặc đơn vị hiển thị cần xét khi đọc giá trị |
| `context` | Phạm vi/thời điểm có thể thay đổi tham số |
| `source` | Nguồn của giá trị hiệu lực |
| `sourcefile`, `sourceline` | Vị trí tệp/dòng cấu hình nếu thông tin được phép hiển thị |
| `pending_restart` | Cho biết có thay đổi cấu hình cần restart để có hiệu lực hay không |

Cột `sourcefile` và `sourceline` có thể bị ẩn nếu tài khoản không có quyền xem thông tin cấu hình tương ứng.

### 6.1. Ba kiểu thay đổi thường gặp

| Nhóm | Ví dụ thường gặp | Cách có hiệu lực |
| --- | --- | --- |
| Tham số chỉ đổi khi start server (`context = postmaster`) | `listen_addresses`, `port`, `shared_buffers`, `max_connections` | **Restart PostgreSQL** |
| Tham số server có thể nạp lại (`context = sighup`) | Nhiều tham số logging, giới hạn vận hành theo cấu hình | **Reload cấu hình** |
| Tham số có thể thay đổi ở session (`user`/`superuser` hoặc ngữ cảnh phù hợp) | `work_mem`, `statement_timeout` theo quyền | Dùng `SET` hoặc cấu hình session/role/database phù hợp |

Bảng mang tính khái quát. Khi không chắc, **xem trực tiếp `pg_settings.context` trên phiên bản đang chạy** thay vì suy luận chỉ từ tên tham số.

### 6.2. `ALTER SYSTEM` và `postgresql.auto.conf`

PostgreSQL hỗ trợ:

```sql
-- Ví dụ trong instance thử nghiệm, do quản trị viên đủ quyền thực hiện.
ALTER SYSTEM SET log_min_duration_statement = '500ms';
```

Lệnh này ghi cấu hình vào `postgresql.auto.conf`, không trực tiếp sửa các dòng `postgresql.conf`. File tự động có vị trí và cơ chế ưu tiên riêng, thường được xét sau cấu hình chính. Không nên chỉnh tay `postgresql.auto.conf` nếu không có quy trình kiểm soát rõ ràng.

Sau `ALTER SYSTEM`, thay đổi còn cần **reload hoặc restart** tùy tham số. `ALTER SYSTEM` không chạy trong một transaction block thông thường. Khi cần hoàn tác một thiết lập được đưa vào auto conf:

```sql
ALTER SYSTEM RESET log_min_duration_statement;
```

Sau đó nạp lại cấu hình phù hợp. Các câu này **chỉ là minh họa cú pháp**; không chạy trên instance production nếu chưa được phân quyền/quy trình thay đổi phê duyệt.

---

## 7. Cách ưu tiên khi có nhiều tệp hoặc nhiều dòng cấu hình

Trong `postgresql.conf`, có thể sử dụng các chỉ thị include:

```conf
include = 'memory.conf'
include_if_exists = 'local-overrides.conf'
include_dir = 'conf.d'
```

Tùy cách triển khai, những tệp này có thể chứa tham số theo nhóm. Việc sắp xếp nguồn cấu hình phải được hiểu theo quy tắc đọc và ưu tiên của PostgreSQL; **cấu hình cuối cùng có hiệu lực có thể đến từ tệp khác dòng bạn vừa sửa**.

Ví dụ đơn giản:

```conf
# postgresql.conf
work_mem = '4MB'
include = 'performance.conf'
```

Tệp `performance.conf` chứa:

```conf
work_mem = '16MB'
```

Với thứ tự áp dụng phù hợp và không có nguồn ưu tiên cao hơn, giá trị sau có thể ghi đè giá trị trước. Trường hợp dùng `postgresql.auto.conf` hoặc tham số khởi động `-c` còn cần xem thứ tự ưu tiên tương ứng.

Không nên dựa vào việc nhìn duy nhất một tệp. Khi điều tra, dùng `pg_settings` cùng view `pg_file_settings`:

```sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE name = 'work_mem'
ORDER BY sourcefile, sourceline;
```

View này giúp thấy các dòng được parse từ tệp và những giá trị có được áp dụng hay không. `applied = false` không phải lúc nào cũng là lỗi cú pháp: dòng có thể bị ghi đè bởi dòng có hiệu lực sau. Xem thêm cột `error` và giá trị hiệu lực từ `pg_settings`.

---

## 8. `pg_hba.conf`: quy tắc xác thực client

Tên HBA bắt nguồn từ **Host-Based Authentication**, nhưng tệp còn quy định kết nối thông qua Unix-domain socket. Nó trả lời:

> “Với kiểu kết nối, database, PostgreSQL username và địa chỉ nguồn này, phải dùng phương thức xác thực nào?”

Một dòng HBA cho kết nối TCP thường có dạng:

```text
TYPE  DATABASE  USER  ADDRESS  METHOD  [OPTIONS]
```

Ví dụ:

```conf
# TYPE     DATABASE USER        ADDRESS         METHOD
host       appdb    app_login   10.20.1.0/24    scram-sha-256
```

Ý nghĩa:

- `host`: dòng áp dụng cho kết nối TCP/IP.
- `appdb`: database đích.
- `app_login`: role PostgreSQL client muốn đăng nhập.
- `10.20.1.0/24`: các client thuộc dải IPv4 tương ứng.
- `scram-sha-256`: phương thức xác thực bằng mật khẩu SCRAM.
- Các tùy chọn bổ sung có thể xuất hiện sau phương thức, tùy kiểu xác thực.

Khi xác thực thành công, PostgreSQL còn kiểm tra role, quyền kết nối và các điều kiện liên quan; dòng HBA **không phải lệnh cấp SQL privilege**.

### 8.1. Các loại dòng HBA thường gặp

| `TYPE` | Kết nối được áp dụng | Lưu ý |
| --- | --- | --- |
| `local` | Unix-domain socket trên cùng host | Không có cột ADDRESS dạng IP; có thể dùng `peer` |
| `host` | TCP/IP, không giới hạn theo trạng thái TLS của dòng | Có thể khớp cả kết nối có/không TLS |
| `hostssl` | TCP/IP dùng TLS | Cần PostgreSQL được cấu hình hỗ trợ SSL/TLS |
| `hostnossl` | TCP/IP không dùng TLS | Thường không nên cho phép đường này với dữ liệu nhạy cảm |
| Các biến thể khác | Phụ thuộc phiên bản và cơ chế xác thực/SSL/GSS | Chỉ dùng khi hiểu rõ tính năng |

**`local` không có nghĩa địa chỉ TCP `127.0.0.1`.** Hai kết nối khác nhau:

```bash
# Trên Unix/Linux: không cung cấp -h thường chọn Unix-domain socket.
psql -U app_login -d appdb

# Có -h 127.0.0.1: dùng TCP/IP loopback.
psql -h 127.0.0.1 -U app_login -d appdb
```

Dòng `local` có thể dùng `peer`, còn dòng `host` cho loopback có thể dùng `scram-sha-256`. Vì vậy cùng database/role nhưng một cách đăng nhập thành công, cách kia thất bại là điều có thể xảy ra.

### 8.2. Các trường DATABASE, USER và ADDRESS

`DATABASE` có thể nêu tên database cụ thể hoặc những từ khóa đặc biệt như `all`, `sameuser`, `samerole`. `USER` có thể là tên role hoặc nhóm tương ứng theo cú pháp HBA; một số trường hợp cho phép biểu thức tên role hoặc danh sách được include.

`ADDRESS` có thể là địa chỉ IPv4/IPv6 kèm CIDR, ví dụ:

```conf
host  appdb  app_login  127.0.0.1/32     scram-sha-256
host  appdb  app_login  10.20.1.0/24     scram-sha-256
host  appdb  app_login  ::1/128          scram-sha-256
```

Phân biệt:

- `127.0.0.1/32`: một địa chỉ IPv4 loopback.
- `10.20.1.0/24`: một dải địa chỉ IPv4 ví dụ.
- `::1/128`: loopback IPv6.

Dùng dải địa chỉ rộng hơn nhu cầu thực tế làm tăng phạm vi client được **thử xác thực**. Nó không tự cấp mật khẩu hay quyền SQL cho họ, nhưng tăng bề mặt tấn công.

### 8.3. Các phương thức xác thực

| `METHOD` | Vai trò | Khi nào cân nhắc |
| --- | --- | --- |
| `scram-sha-256` | Xác thực mật khẩu bằng SCRAM | Phù hợp cho nhiều client PostgreSQL hiện đại |
| `peer` | Xác thực dựa trên user OS của kết nối Unix socket | Dịch vụ local được quản lý trên Linux/Unix |
| `ident` | Lấy danh tính phía client thông qua dịch vụ ident, thường dùng cho TCP trong bối cảnh đặc thù | Ít phổ biến; cần hiểu độ tin cậy của hạ tầng |
| `cert` | Xác thực bằng chứng chỉ client TLS | Hệ thống có PKI và quản lý certificate phù hợp |
| `trust` | Chấp nhận kết nối khớp quy tắc mà không yêu cầu kiểm tra mật khẩu | Chỉ dùng với tình huống được kiểm soát đặc biệt, tránh trong production |
| `reject` | Từ chối kết nối phù hợp | Dùng khi cần chặn một phạm vi cụ thể |
| `md5` | Phương thức mật khẩu cũ/giá trị cấu hình tương thích | Tránh thiết kế mới phụ thuộc MD5; ưu tiên SCRAM |
| PAM/LDAP/GSS/SSPI... | Xác thực tích hợp hạ tầng bên ngoài | Cần cấu hình riêng theo môi trường |

Không nên dùng `trust` cho dải mạng mở chỉ để “dễ kết nối”. Trong cấu hình production, ưu tiên phương thức hiện đại, mạng được hạn chế và TLS có xác minh danh tính đầu xa khi cần.

---

## 9. Quy tắc quan trọng nhất của pg_hba.conf: dòng khớp đầu tiên

PostgreSQL xét các dòng HBA **theo thứ tự**, và chọn **dòng đầu tiên khớp** kiểu kết nối, database, user và địa chỉ nguồn. Nếu phương thức xác thực của dòng đó thất bại, server **không tiếp tục thử những dòng sau như cơ chế dự phòng**.

Ví dụ:

```conf
# Dòng 1 khớp mọi kết nối TCP IPv4 từ dải 10.20.1.0/24 tới appdb:
host  appdb  app_login  10.20.1.0/24    reject

# Dòng 2 định cho cùng kết nối nhưng sẽ không được thử:
host  appdb  app_login  10.20.1.15/32   scram-sha-256
```

Một kết nối từ `10.20.1.15` tới `appdb` bằng `app_login` bị từ chối ở **dòng 1**. Dòng 2 là dòng cụ thể hơn nhưng đứng sau nên không được dùng.

Nếu muốn cho phép địa chỉ `10.20.1.15` nhưng chặn phần còn lại của dải, thứ tự phải là:

```conf
host  appdb  app_login  10.20.1.15/32   scram-sha-256
host  appdb  app_login  10.20.1.0/24    reject
```

**PostgreSQL không chọn dòng “cụ thể nhất” theo một thuật toán xếp hạng độ ưu tiên IP.** Nó chọn dòng khớp đầu tiên theo thứ tự trong cấu hình hiệu lực.

### 9.1. Sai lầm với quy tắc rộng đặt trước

Ví dụ:

```conf
local  all    all                 peer
local  appdb  app_login           peer map=local_app_map
```

Dòng `local all all peer` đã khớp mọi kết nối Unix socket. Dòng mapping phía sau không được xét. Vì vậy, để dùng mapping cụ thể, đặt quy tắc cụ thể **trước** dòng rộng:

```conf
local  appdb  app_login           peer map=local_app_map
local  all    all                 peer
```

Đây là một trong những nguyên nhân phổ biến khi đã chỉnh `pg_ident.conf` đúng mà đăng nhập bằng mapped user vẫn không hoạt động.

### 9.2. Không có dòng khớp thì sao?

Nếu không có dòng HBA nào khớp yêu cầu, kết nối bị từ chối. Thông báo có thể chứa dạng:

```text
FATAL: no pg_hba.conf entry for host "...",
user "...", database "...", ...
```

Không cần giải quyết bằng cách thêm ngay:

```conf
# CẤU HÌNH NGUY HIỂM nếu đưa vào mạng thật:
host  all  all  0.0.0.0/0  trust
```

Quy tắc này cho phép các kết nối IPv4 từ mọi nơi khớp dòng đó mà **không cần mật khẩu**, rất rủi ro. Cách xử lý đúng là xác định host, database, role, loại kết nối và phương thức bảo mật cần thiết, rồi cấp **quy tắc hẹp nhất có thể**.

---

## 10. Ví dụ HBA cho ứng dụng kết nối TCP qua TLS

Giả sử:

- PostgreSQL server có địa chỉ mạng nội bộ `10.20.0.10`.
- Ứng dụng kết nối từ `10.20.1.15`.
- Database cần truy cập là `appdb`.
- Role PostgreSQL đăng nhập là `app_login`.
- Tổ chức yêu cầu TLS và SCRAM.

Trong `postgresql.conf` (chỉ là ví dụ sau khi đã chuẩn bị hạ tầng TLS):

```conf
listen_addresses = 'localhost,10.20.0.10'
port = 5432

# Bật TLS chỉ khi cert/key/server configuration đã được chuẩn bị đúng.
ssl = on
```

Trong `pg_hba.conf`:

```conf
# TYPE    DATABASE USER       ADDRESS         METHOD
hostssl   appdb    app_login  10.20.1.15/32   scram-sha-256
```

Trong PostgreSQL (bằng tài khoản có quyền quản lý role):

```sql
-- Ví dụ chỉ để học; dùng secret mạnh, không lưu password thật vào Git.
CREATE ROLE app_login LOGIN
PASSWORD 'THAY_BANG_SECRET_DU_DAI_VA_DU_NGAU_NHIEN';

-- Giả sử database appdb đã tồn tại.
GRANT CONNECT ON DATABASE appdb TO app_login;
```

Lưu ý:

1. `pg_hba.conf` chỉ cho phép ứng dụng **thử** xác thực theo SCRAM ở kết nối có TLS đến từ IP chỉ định.
2. Role `app_login` phải tồn tại và có thuộc tính `LOGIN`.
3. Server phải có password verifier phù hợp với phương thức SCRAM. Tham số `password_encryption = 'scram-sha-256'` quy định cách password **mới được đặt**; đổi cấu hình không tự chuyển đổi mọi mật khẩu đã lưu trước đó.
4. Client cần cấu hình xác minh máy chủ TLS (ví dụ `sslmode=verify-full`, CA và hostname phù hợp), không chỉ bật mã hóa mà không xác minh danh tính.
5. `GRANT CONNECT` không cấp quyền `SELECT` hay `INSERT` trong database. Cần cấp quyền schema/table/sequence phù hợp.
6. Network/firewall phải cho phép traffic từ ứng dụng tới server; HBA không thay thế quy tắc mạng.
7. `listen_addresses` là tham số **cần restart** để thay đổi có hiệu lực; thay HBA thông thường cần reload.

Ví dụ lệnh client (chỉ minh họa, cần CA và DNS chính xác trong môi trường thật):

```bash
psql "host=db.internal port=5432 dbname=appdb user=app_login sslmode=verify-full sslrootcert=/path/to/ca.pem"
```

Nếu server certificate không khớp hostname hoặc CA không tin cậy, `verify-full` sẽ từ chối kết nối. Đây là bảo vệ cần thiết, không phải lý do để tắt xác minh ngay lập tức.

---

## 11. `pg_ident.conf`: ánh xạ username bên ngoài

Thông thường, phương thức `peer` trên Unix socket kiểm tra tên user hệ điều hành của tiến trình client. Nếu bạn chạy `psql` bằng OS user `appsvc` và muốn đăng nhập PostgreSQL role `app_login`, hai tên khác nhau nên xác thực `peer` mặc định không tự coi chúng là một.

`pg_ident.conf` giải quyết vấn đề **mapping danh tính** trong các phương thức có hỗ trợ.

Dạng một dòng thông dụng:

```text
MAPNAME  SYSTEM-USERNAME  PG-USERNAME
```

Ví dụ trong `pg_ident.conf`:

```conf
# MAPNAME      SYSTEM-USERNAME  PG-USERNAME
local_app_map  appsvc           app_login
```

Ý nghĩa: khi một quy tắc xác thực sử dụng map tên `local_app_map`, user bên ngoài `appsvc` được phép xác thực vào PostgreSQL role `app_login` theo quan hệ mapping đó.

**Đây không phải phép đổi tên tài khoản trong PostgreSQL.** Role `app_login` vẫn cần được tạo bằng SQL, và role đó vẫn cần quyền phù hợp trên database.

### 11.1. Kết hợp pg_ident.conf với pg_hba.conf

Trong `pg_hba.conf`:

```conf
# Quy tắc cụ thể PHẢI ở trước quy tắc local rộng hơn.
local  appdb  app_login  peer map=local_app_map
local  all    all        peer
```

Trong `pg_ident.conf`:

```conf
local_app_map  appsvc  app_login
```

Trong SQL, role cần tồn tại:

```sql
CREATE ROLE app_login LOGIN;
GRANT CONNECT ON DATABASE appdb TO app_login;
```

Trên một máy Unix/Linux có user OS `appsvc` được quản lý thích hợp, khi chạy `psql` bằng user đó và kết nối qua Unix socket:

```bash
psql -U app_login -d appdb
```

PostgreSQL xử lý ý tưởng:

```text
Client kết nối qua Unix-domain socket
         |
         v
HBA: local appdb app_login peer map=local_app_map
         |
         v
Lấy danh tính OS user thực: appsvc
         |
         v
pg_ident map local_app_map:
    appsvc -> app_login
         |
         v
Xác thực cho PostgreSQL role app_login
         |
         v
Kiểm tra quyền CONNECT và quyền SQL tiếp theo
```

Việc tạo mapping **không tạo OS user `appsvc`** và không thay đổi ai được phép chạy tiến trình dưới OS account đó. Quản trị OS/containers và quyền file/socket vẫn phải được cấu hình phù hợp.

### 11.2. `peer` khác `ident` như thế nào?

| Phương thức | Thông tin danh tính đến từ đâu? | Ngữ cảnh |
| --- | --- | --- |
| `peer` | Hệ điều hành phía **server** lấy danh tính của tiến trình đang kết nối qua Unix-domain socket | Kết nối `local` trên hệ hỗ trợ |
| `ident` | Server hỏi dịch vụ Ident ở phía client để nhận tên user của kết nối TCP theo giao thức ident | Kết nối host/TCP khi hạ tầng được kiểm soát |
| `cert` | Danh tính từ chứng chỉ client TLS theo chính sách xác thực certificate | Kết nối TLS và hệ thống PKI |

`peer` thường là lựa chọn tự nhiên hơn khi một service local chạy dưới OS user chuyên dụng và không muốn lưu mật khẩu PostgreSQL cho kết nối socket.

`ident` cần phụ thuộc vào phản hồi của ident service phía client, nên phải đánh giá mức độ tin cậy của máy client/hạ tầng. Nó không phải lựa chọn thay thế mật khẩu/TLS mặc định cho các ứng dụng kết nối qua mạng không tin cậy.

`pg_ident.conf` cũng có thể tham gia vào những cơ chế mapping khác như chứng chỉ client khi cấu hình phù hợp. Nó **không phải file chứa mật khẩu**.

### 11.3. Một mapping có thể ánh xạ nhiều danh tính

Ví dụ:

```conf
# Hai OS users khác nhau vào cùng một database role.
local_app_map  appsvc   app_login
local_app_map  jobsync  app_login
```

Điều này cho phép hai danh tính hệ điều hành được map sang cùng role PostgreSQL nếu HBA cho phép. Tuy nhiên, dùng chung database role sẽ làm giảm khả năng phân biệt truy cập ở phía PostgreSQL. Trong nhiều hệ thống, nên cấp **role riêng theo service** để ghi log/audit rõ ràng hơn.

Một map còn có thể sử dụng biểu thức khớp tên theo khả năng của PostgreSQL, nhưng phần bài này ưu tiên mapping tường minh để dễ kiểm soát. Không mở rộng regex quá rộng nếu không hiểu tác động lên quyền đăng nhập.

### 11.4. Mapping không thay đổi quyền trên bảng

Khi `appsvc` được map vào `app_login`, mọi SQL sau đăng nhập chạy dưới quyền hiệu lực của `app_login` và các vai trò/cấu hình liên quan. Nó **không tự có quyền root OS**, không tự nhận quyền superuser PostgreSQL và không tự được truy cập mọi bảng.

Phân biệt hai quá trình:

```text
OS user appsvc  --pg_ident mapping-->  PostgreSQL role app_login
                                               |
                                               v
                                        Kiểm tra GRANT/REVOKE,
                                        schema/table/RLS...
```

---

## 12. Một quy trình thay đổi cấu hình an toàn

Việc sửa cấu hình PostgreSQL trên server thật có thể làm ứng dụng mất kết nối hoặc server không khởi động được. Quy trình nên phân biệt **thay tham số** và **thay xác thực**.

### Bước 1 — Xác định đúng instance và giá trị hiện tại

```sql
SELECT current_database(), current_user;
SHOW config_file;
SHOW hba_file;
SHOW ident_file;

SELECT name, setting, context, source, pending_restart
FROM pg_settings
WHERE name IN ('listen_addresses', 'port', 'work_mem', 'shared_buffers')
ORDER BY name;
```

Ghi nhận cách đăng nhập quản trị hiện đang hoạt động. Nếu bạn sửa HBA sai và không còn kết nối mới được, có thể phải cần đường truy cập console hoặc một session quản trị đã mở để khôi phục.

### Bước 2 — Sao lưu cấu hình và chuẩn bị cách hoàn tác

Trước khi sửa các tệp thật:

- Lưu bản sao tệp cấu hình hiện tại bằng công cụ quản trị OS được phép.
- Ghi lại những dòng được thay đổi và người phê duyệt.
- Giữ một đường quản trị tin cậy, nhưng **không** duy trì dòng `trust` rộng như “cửa hậu” trong production.
- Lên kế hoạch reload hoặc restart tùy tham số.
- Chọn môi trường thử nghiệm trước khi áp dụng production.

### Bước 3 — Sửa phạm vi nhỏ nhất

Ví dụ bạn cần thêm một IP ứng dụng trong HBA; hãy thêm một dòng `hostssl` cho database, role và IP cụ thể, rồi đặt ở vị trí phù hợp với quy tắc first-match.

Nếu bạn cần đổi `listen_addresses`, xác nhận địa chỉ thực sự có trên host server và nhớ rằng thay đổi thường cần restart.

Nếu bạn cần ánh xạ OS user, sửa `pg_ident.conf` và bảo đảm `pg_hba.conf` có dòng `peer map=...` phù hợp.

### Bước 4 — Xem lỗi cấu hình trên file trước khi áp dụng

PostgreSQL có các view hỗ trợ quan sát những dòng được parse:

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

Với HBA:

```sql
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

Với mapping:

```sql
SELECT
    line_number,
    map_name,
    sys_name,
    pg_username,
    error
FROM pg_ident_file_mappings
ORDER BY line_number;
```

Những view này có trên các phiên bản PostgreSQL phù hợp và có thể cần quyền quản trị/quan sát nhất định. Cấu trúc cột cụ thể có thể thay đổi theo phiên bản; nếu không truy vấn được, hãy kiểm tra `\d+ pg_hba_file_rules` hoặc tài liệu của instance đang dùng.

**Quan trọng:** một view đọc/parse nội dung file hiện tại **không tự chứng minh đó là bộ quy tắc đang được áp dụng trong bộ nhớ**. Sau khi sửa file cần nạp lại cấu hình phù hợp, kiểm tra log và thử kết nối mới.

### Bước 5 — Reload hoặc restart đúng loại

Để yêu cầu PostgreSQL đọc lại những phần cấu hình hỗ trợ reload:

```sql
SELECT pg_reload_conf();
```

Giá trị `true` cho biết PostgreSQL đã gửi tín hiệu yêu cầu reload thành công theo cơ chế của hàm. **Nó không phải lời xác nhận mọi dòng trong các file đều hợp lệ và đã được áp dụng**. Hãy kiểm tra log server, `pg_file_settings`/các view HBA và giá trị hiệu lực.

Ở hệ điều hành, quản trị viên cũng có thể dùng công cụ service hoặc `pg_ctl reload` theo cách quản lý instance cụ thể.

Với tham số cần restart (ví dụ `listen_addresses`, `shared_buffers`), reload **không đủ**. Khi cần restart:

- Lập kế hoạch tác động kết nối.
- Bảo đảm đã có phương án rollback cấu hình nếu server không khởi động.
- Kiểm tra `pg_settings.pending_restart` và log.
- Không chạy restart bừa trên production chỉ để thử một bài học.

### Bước 6 — Thử một kết nối mới

Thử kết nối đúng loại mà cấu hình mới nhắm tới:

- Unix socket (đối với `local`/`peer`).
- TCP có hoặc không có TLS theo chính sách.
- Đúng database, username và host nguồn.
- Đúng role đã tạo và quyền `CONNECT`.

Sau khi đăng nhập:

```sql
SELECT
    current_user,
    session_user,
    current_database(),
    inet_client_addr() AS client_ip;
```

Với kết nối Unix socket, `inet_client_addr()` thường là `NULL`. Với TCP, nó cho biết địa chỉ client mà server nhận thấy.

Sau đó thử **một truy vấn SELECT được phép**, không tự thử `DROP TABLE` trên môi trường thật.

---

## 13. Reload khác restart như thế nào?

| Hành động | Khi dùng | Tác động cơ bản |
| --- | --- | --- |
| `SELECT pg_reload_conf();` | Thay đổi tham số có thể reload, HBA/ident trên môi trường phù hợp | Yêu cầu nạp lại cấu hình; không dừng toàn instance |
| `pg_ctl reload` / gửi SIGHUP | Cách quản trị hệ thống để reload | Tác dụng tương tự yêu cầu reload |
| Restart service PostgreSQL | Thay tham số cần postmaster restart hoặc bảo trì theo kế hoạch | Kết nối có thể bị ngắt; server dừng và chạy lại |
| `SET work_mem = '...'` | Chỉ thay đổi một session được phép | Không sửa file cấu hình toàn instance |
| `ALTER ROLE ... SET ...` / `ALTER DATABASE ... SET ...` | Đặt giá trị mặc định theo user/database nếu tham số hỗ trợ | Thường ảnh hưởng các session mới theo quy tắc áp dụng |
| `ALTER SYSTEM SET ...` | Ghi thay đổi tham số server vào auto config | Vẫn cần reload/restart tùy context |

Thông thường, thay `pg_hba.conf` và `pg_ident.conf` trên Unix/Linux cần **reload** để áp dụng cho kết nối mới. Trên Windows, PostgreSQL có thể áp dụng thay đổi HBA cho kết nối mới theo hành vi nền tảng mà không cần tín hiệu SIGHUP như Unix; dù vậy vẫn nên kiểm tra phiên bản và quy trình quản trị cụ thể.

Một **kết nối đang hoạt động** không bị xác thực lại ngay chỉ vì HBA đổi. Khi đánh giá thay đổi, hãy tạo **kết nối mới**. Để chặn quyền SQL của phiên hiện tại, có thể còn phải xử lý role, quyền và session hiện có; không coi chỉ sửa HBA là biện pháp kết thúc mọi kết nối đã đăng nhập.

---

## 14. Kiểm tra HBA bằng pg_hba_file_rules

View `pg_hba_file_rules` hữu ích để biết PostgreSQL đang parse những dòng HBA thế nào.

```sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules;
```

Nếu muốn lọc lỗi:

```sql
SELECT line_number, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
```

Kết quả rỗng của câu truy vấn lỗi cho thấy không có lỗi được view ghi nhận ở các dòng nó parse, **không chứng minh chính sách đúng nghiệp vụ hoặc bảo mật**. Một dòng `trust` khớp quá rộng hoàn toàn có thể đúng cú pháp nhưng nguy hiểm.

Các bước kiểm tra logic:

1. Xác định kết nối đang dùng `local` hay `host/hostssl`.
2. Xác định database yêu cầu, PostgreSQL role và IP nguồn thật.
3. Đọc các dòng theo **thứ tự hiệu lực**, xem dòng nào khớp đầu tiên.
4. Kiểm tra phương thức xác thực và tùy chọn như `map=...`.
5. Kiểm tra danh tính/secret/certificate phía client.
6. Nếu sửa file, xác nhận reload đã thành công và thử phiên kết nối mới.

Một tệp HBA có thể sử dụng include trên các phiên bản PostgreSQL hỗ trợ. Khi đó, nội dung file hiệu lực có thể đến từ nhiều tệp; đừng chỉ nhìn một tệp và bỏ qua các quy tắc được include.

---

## 15. Kiểm tra mapping bằng pg_ident_file_mappings

Một cấu hình mapping sai có thể khiến `peer` hoặc phương thức khác từ chối kết nối dù OS user và PostgreSQL role đều tồn tại.

Ví dụ muốn map `appsvc → app_login` qua map `local_app_map`:

```conf
# pg_ident.conf
local_app_map  appsvc  app_login
```

Kiểm tra:

```sql
SELECT
    line_number,
    map_name,
    sys_name,
    pg_username,
    error
FROM pg_ident_file_mappings;
```

Nếu thấy:

- `map_name` khác `map=...` trong HBA → không dùng đúng mapping.
- `sys_name` khác OS username thực tế → ánh xạ không khớp.
- `pg_username` khác role được yêu cầu bởi client → không khớp.
- `error` khác `NULL` → có vấn đề parse cần sửa.

Sau khi sửa cần reload theo môi trường và tạo **kết nối mới** để thử.

Không nên mở rộng một mapping cho quá nhiều PostgreSQL role nếu không có yêu cầu và kiểm soát rõ ràng. Mapping chỉ là cầu nối xác thực danh tính; chính sách phân quyền vẫn phải được giới hạn ở các role.

---

## 16. HBA xác thực thành công nhưng truy vấn vẫn bị từ chối

Giả sử ứng dụng đã đăng nhập `appdb` bằng `app_login` nhưng chạy:

```sql
SELECT * FROM public.orders;
```

và nhận:

```text
ERROR: permission denied for table orders
```

Đây **không còn là lỗi chọn phương thức xác thực trong pg_hba.conf**. Kết nối đã được thiết lập; PostgreSQL đang kiểm tra quyền truy cập đối tượng.

Các điều cần xem:

- Role đã có `LOGIN` chưa (nếu đang xử lý giai đoạn đăng nhập).
- Database có cấp `CONNECT` theo yêu cầu không.
- Schema có quyền `USAGE` không.
- Bảng có `SELECT`/`INSERT`/`UPDATE` tương ứng không.
- Sequence có quyền cần thiết nếu thao tác dùng sequence không.
- Có Row-Level Security hoặc chính sách khác giới hạn dữ liệu không.

Ví dụ (chỉ cấp đúng quyền khi nghiệp vụ cần):

```sql
-- Được thực hiện bởi quản trị viên/owner có quyền cấp phát.
GRANT CONNECT ON DATABASE appdb TO app_login;
GRANT USAGE ON SCHEMA public TO app_login;
GRANT SELECT ON TABLE public.orders TO app_login;
```

Những câu trên chỉ là minh họa; `public.orders` phải tồn tại và thực sự thuộc database appdb khi thực thi. Không mở rộng thành `GRANT ALL PRIVILEGES ON ALL TABLES` chỉ để xử lý một truy vấn `SELECT`.

---

## 17. Chẩn đoán sự cố theo thông báo lỗi

Các triệu chứng sau đại diện những **lớp vấn đề khác nhau**:

| Triệu chứng | Lớp cần kiểm tra trước | Câu hỏi chẩn đoán |
| --- | --- | --- |
| `connection refused` | Mạng/service/`postgresql.conf` | PostgreSQL đang chạy, lắng nghe IP/cổng nào? |
| Timeout kết nối TCP | Mạng, firewall, route, load balancer, security group | Gói tin có đến máy chủ không, cổng có mở theo chính sách? |
| `no pg_hba.conf entry for host ...` | `pg_hba.conf` | Loại kết nối, database, user, IP và TLS có dòng khớp không? |
| `password authentication failed for user ...` | HBA method, role và thông tin xác thực | Dòng đầu khớp là gì, password/verifier có đúng không? |
| `Peer authentication failed for user ...` | `peer` và `pg_ident.conf` | OS username có khớp PostgreSQL role hoặc mapping không? |
| `role "..." does not exist` | Role trong database cluster | Tài khoản đã được tạo chưa? |
| `role "..." is not permitted to log in` | Thuộc tính role | Role đã có `LOGIN` chưa? |
| `permission denied for database ...` | SQL privilege | Đã có quyền `CONNECT` phù hợp chưa? |
| `permission denied for schema/table ...` | SQL privilege | Quyền `USAGE`, `SELECT`/DML, RLS ra sao? |
| TLS handshake/certificate error | TLS/cert/client settings | CA, hostname, certificate và `sslmode` có đúng không? |
| Sửa tham số nhưng `SHOW` chưa đổi | Reload/restart/ưu tiên config | Context của tham số, `pending_restart` và `source` là gì? |
| PostgreSQL không khởi động sau sửa file | Cú pháp/giá trị config, đường dẫn tệp/certificate | Log startup báo lỗi gì, có bản backup để phục hồi không? |

### 17.1. Cách phân tích “no pg_hba.conf entry”

Giả sử log:

```text
FATAL: no pg_hba.conf entry for host "10.20.1.15",
user "app_login", database "appdb", no encryption
```

Cụm “no encryption” cho biết yêu cầu kết nối trong tình huống này **không dùng TLS**. Nếu HBA chỉ có:

```conf
hostssl  appdb  app_login  10.20.1.15/32  scram-sha-256
```

thì một kết nối không TLS **không khớp** dòng `hostssl`. Cách xử lý có thể là cấu hình client sử dụng TLS đúng cách, không phải nới HBA thành `host` hoặc `trust` ngay.

Tương tự, nếu client thực sự đến từ IP proxy/NAT khác với IP bạn dự tính, HBA phải được thiết kế theo địa chỉ nguồn mà server nhìn thấy.

### 17.2. Cách phân tích “peer authentication failed”

Một người dùng chạy:

```bash
psql -U app_login -d appdb
```

trên Linux dưới OS user `developer`, trong khi HBA dùng:

```conf
local  all  all  peer
```

Phương thức `peer` thường mong danh tính OS user khớp với PostgreSQL role nếu không có mapping phù hợp. Vì `developer` khác `app_login`, kết nối có thể thất bại.

Các lựa chọn đúng ngữ cảnh:

1. Đăng nhập bằng PostgreSQL role cùng tên OS user nếu được tạo/cấp quyền.
2. Cấu hình `pg_ident.conf` và dòng HBA `peer map=...` **hẹp** nếu muốn mapping chính thức.
3. Dùng kết nối TCP với SCRAM/TLS và secret được quản lý nếu ứng dụng không cần xác thực qua OS user.
4. Kiểm tra client thực sự dùng Unix socket hay TCP; `-h 127.0.0.1` thay đổi loại HBA được xét.

Không nên thay toàn bộ dòng `local all all peer` thành `trust` như một “sửa nhanh” trên máy dùng chung.

---

## 18. Gợi ý bảo mật khi chỉnh ba tệp

### 18.1. Không mở mạng rộng hơn nhu cầu

Một cấu hình rủi ro khi đi cùng quy tắc xác thực quá rộng:

```conf
# postgresql.conf
listen_addresses = '*'
```

và:

```conf
# pg_hba.conf: KHÔNG KHUYẾN NGHỊ cho production
host  all  all  0.0.0.0/0  trust
```

Nếu cổng được mở đến các nguồn không đáng tin cậy, các client khớp quy tắc `trust` có thể đăng nhập mà không cần mật khẩu. Thay bằng:

- Địa chỉ server lắng nghe có chủ đích.
- Giới hạn dải IP client thực sự được phép.
- `hostssl` cho kết nối cần TLS.
- Phương thức xác thực đáng tin cậy như SCRAM hoặc chứng chỉ.
- Firewall/security group/private network.
- Vai trò SQL với quyền tối thiểu.

### 18.2. Bảo vệ file cấu hình ở hệ điều hành

Các tệp cấu hình thuộc hoạt động của server và có thể chứa đường dẫn, chính sách mạng hoặc tham số nhạy cảm. Quyền đọc/ghi chúng phải phù hợp với OS account vận hành PostgreSQL và quy trình quản trị.

Không chỉnh tệp qua thư mục chia sẻ công khai, không mở quyền ghi cho mọi người, không lưu private key TLS hoặc password trực tiếp vào tài liệu mẫu.

### 18.3. Tách tài khoản đăng nhập và quản trị

Role ứng dụng nên chỉ có các quyền cần cho nghiệp vụ. Tài khoản quản trị thay `postgresql.conf`/HBA hoặc cấp `GRANT` cần được bảo vệ riêng.

Sau khi đăng nhập thành công, HBA không thay thế ranh giới quyền giữa hai role. Một session ứng dụng không được quyền sửa bảng hoặc đọc dữ liệu nhạy cảm chỉ vì địa chỉ IP của nó được phép kết nối.

### 18.4. Không nhầm bảo mật đường truyền với xác thực role

`hostssl` yêu cầu kết nối TLS để dòng HBA đó khớp, nhưng không tự bảo đảm client đang kiểm tra đúng server. Phía client nên xác minh CA và hostname khi cần, ví dụ `sslmode=verify-full`, đồng thời quản lý chứng chỉ và vòng đời gia hạn.

Ngược lại, `scram-sha-256` xác thực password mạnh hơn những phương án cũ nhưng không thay thế việc mã hóa đường truyền khi chính sách bảo mật yêu cầu.

---

## 19. Bài thực hành: đọc mà không sửa cấu hình production

Nếu có một PostgreSQL instance thử nghiệm và quyền quan sát phù hợp, có thể làm phần này chỉ với câu lệnh `SELECT` và `SHOW`.

### Bước 1 — Tìm ba tệp

```sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
```

Ghi lại các đường dẫn và trả lời: chúng có nhất thiết nằm cùng `data_directory` không?

### Bước 2 — Xem cấu hình kết nối và context

```sql
SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'listen_addresses',
    'port',
    'max_connections',
    'work_mem',
    'shared_buffers'
)
ORDER BY name;
```

Tìm tham số nào có context `postmaster`, tham số nào có thể thay đổi trong session.

### Bước 3 — Xem HBA theo cách server parse

```sql
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

Chỉ ra dòng khớp với một kết nối TCP `localhost` trong hệ thống lab (cần biết database, role và TLS).

### Bước 4 — Xem mapping nếu có

```sql
SELECT
    line_number,
    map_name,
    sys_name,
    pg_username,
    error
FROM pg_ident_file_mappings
ORDER BY line_number;
```

Nếu bảng không có mapping, giải thích vì sao không đồng nghĩa tất cả kết nối `peer` đều lỗi: `peer` có thể xác thực khi OS username trùng database role mà không cần mapping riêng.

### Bước 5 — Kiểm tra nguồn và ưu tiên

```sql
SELECT
    name,
    setting,
    source,
    sourcefile,
    sourceline
FROM pg_settings
WHERE name IN ('work_mem', 'log_min_duration_statement');
```

Nếu người quản trị đặt cấu hình trong nhiều tệp, hãy nêu cách đối chiếu `pg_file_settings` và giá trị hiệu lực.

### Bước 6 — Quan sát kết nối của chính mình

```sql
SELECT
    current_user,
    session_user,
    current_database(),
    inet_client_addr(),
    inet_server_addr(),
    inet_server_port();
```

Nếu một trường địa chỉ TCP là `NULL`, cân nhắc session đang dùng Unix socket. Không suy luận một kết nối có dùng TLS hay không chỉ từ việc có địa chỉ IP; cần xem cấu hình/quan sát TLS thích hợp.

---

## 20. Bài tập tình huống

### Bài 1 — Hai tệp và một lỗi mạng

Server có:

```conf
# postgresql.conf
listen_addresses = 'localhost'
```

và:

```conf
# pg_hba.conf
host  appdb  app_login  10.20.1.15/32  scram-sha-256
```

Ứng dụng trên `10.20.1.15` cố kết nối tới IP nội bộ của server nhưng nhận `connection refused`. Tại sao chỉ thêm dòng HBA chưa đủ? Còn những cấu hình mạng nào phải kiểm tra?

### Bài 2 — Quy tắc đầu tiên

Cho HBA:

```conf
host  appdb  app_login  10.20.1.0/24    reject
host  appdb  app_login  10.20.1.15/32   scram-sha-256
```

Kết nối từ `10.20.1.15` có được thử SCRAM không? Viết lại thứ tự để địa chỉ đó được phép xác thực bằng SCRAM, còn những địa chỉ khác trong dải bị từ chối.

### Bài 3 — Local socket khác TCP

Giải thích vì sao hai lệnh có thể nhận kết quả khác nhau:

```bash
psql -U app_login -d appdb
psql -h 127.0.0.1 -U app_login -d appdb
```

Hãy liệt kê dòng `local` và dòng `host` tương ứng trong HBA.

### Bài 4 — Viết mapping an toàn

Một service trên Linux chạy dưới OS user `batchsvc`, nhưng PostgreSQL role cần dùng là `batch_login`. Cần kết nối qua Unix socket vào database `appdb`.

Hãy viết một dòng `pg_ident.conf` và một dòng `pg_hba.conf` dùng `peer map=...` để thực hiện ánh xạ tường minh. Giải thích vì sao các dòng cụ thể phải đứng trước một quy tắc `local all all ...` rộng hơn.

### Bài 5 — Reload hay restart?

Phân loại những thay đổi sau:

1. Thêm dòng `hostssl` vào `pg_hba.conf`.
2. Thêm mapping vào `pg_ident.conf`.
3. Đổi `listen_addresses`.
4. Đổi `shared_buffers`.
5. Dùng `SET work_mem = '16MB'` trong session được phép.

Nêu khi nào reload đủ, khi nào restart, và vì sao phải thử **kết nối mới** sau khi sửa HBA.

### Bài 6 — Login được nhưng không SELECT được

Một ứng dụng đăng nhập thành công nhưng nhận `permission denied for relation orders`. Vì sao không nên tiếp tục sửa HBA? Kể tên các quyền có thể cần kiểm tra ở database, schema và table.

### Bài 7 — HBA và TLS

Chỉ có quy tắc:

```conf
hostssl  appdb  app_login  10.20.1.15/32  scram-sha-256
```

Kết nối từ đúng IP nhưng không dùng TLS có khớp không? Nếu client sử dụng TLS nhưng certificate server không được client tin cậy, phải xem lớp nào? Tại sao không nên vội chuyển thành `host all all ... trust`?

### Bài 8 — Đọc những gì được áp dụng

Một người sửa `work_mem` trong tệp chính, reload thành công nhưng `SHOW work_mem` vẫn trả giá trị cũ. Hãy nêu ba khả năng: dòng đã bị override bởi file include/auto conf, session có override riêng, hoặc giá trị hiện tại chưa được nạp do lỗi. Viết các câu SQL cần dùng để xác minh `source`, `sourcefile`, `pg_file_settings` và `pending_restart`.

---

## 21. Bảng ghi nhớ nhanh

| Bạn muốn làm gì? | Kiểm tra ở đâu? | Ghi chú |
| --- | --- | --- |
| Server lắng nghe IP/cổng khác | `postgresql.conf`: `listen_addresses`, `port` | Thường cần restart |
| Tăng bộ nhớ `shared_buffers` | `postgresql.conf` hoặc nguồn cấu hình có hiệu lực | Xem `context`, thường cần restart |
| Thay ngưỡng slow query logging | Tham số logging PostgreSQL | Xem context và reload phù hợp |
| Cho app từ IP cụ thể xác thực | `pg_hba.conf` | Dòng cụ thể, method mạnh, kiểm tra first-match |
| Buộc một nhóm kết nối dùng TLS | `hostssl` + cấu hình TLS server/client | Không thay thế xác minh chứng chỉ |
| OS user khác tên PostgreSQL role | `pg_ident.conf` + `pg_hba.conf map=...` | Áp dụng cho phương thức hỗ trợ mapping |
| Không biết file cấu hình nằm đâu | `SHOW config_file/hba_file/ident_file` | Đọc từ instance đang kết nối |
| Không rõ giá trị nào có hiệu lực | `pg_settings` | Xem `setting`, `source`, `context` |
| Kiểm tra dòng file cấu hình lỗi | `pg_file_settings` | Xem `applied` và `error` |
| Kiểm tra HBA có parse được | `pg_hba_file_rules` | Hợp lệ cú pháp chưa chứng minh đúng chính sách |
| Kiểm tra ident mapping | `pg_ident_file_mappings` | Xem tên map và username |
| Yêu cầu PostgreSQL đọc lại config | `SELECT pg_reload_conf();` | Xác minh lại log và giá trị hiệu lực |
| App kết nối rồi bị từ chối SELECT | `GRANT`, `REVOKE`, schema/table/RLS | Không phải lỗi HBA |
| App nhận connection refused | Service, listen address, firewall, route | HBA không thay thế việc server lắng nghe |

## Kết luận

Ba tệp cấu hình PostgreSQL có những trách nhiệm rõ ràng:

- **`postgresql.conf`** quyết định các tham số vận hành của PostgreSQL server, bao gồm địa chỉ lắng nghe, cổng, bộ nhớ và logging. Thay đổi có thể cần reload hoặc restart tùy `pg_settings.context`.
- **`pg_hba.conf`** quyết định quy tắc xác thực cho từng loại kết nối. PostgreSQL xét theo **thứ tự và lấy dòng khớp đầu tiên**; việc xác thực thất bại ở dòng đó không khiến server thử dòng phía sau.
- **`pg_ident.conf`** hỗ trợ ánh xạ danh tính bên ngoài sang PostgreSQL role khi dùng phương thức như `peer` hoặc một phương thức hỗ trợ user mapping. Nó không tạo role, không lưu mật khẩu và không tự cấp quyền dữ liệu.

Một kết nối thành công cần phối hợp **server đang lắng nghe → mạng tới được server → HBA chọn đúng phương thức → danh tính xác thực hợp lệ → role có quyền SQL phù hợp**. Khi một bước thất bại, hãy sửa đúng lớp thay vì mở rộng quyền hoặc tắt xác thực một cách tùy tiện. Đọc giá trị hiệu lực, ghi nhận thay đổi, reload/restart đúng cách và kiểm tra kết nối mới là những thói quen quan trọng để vận hành PostgreSQL an toàn.
