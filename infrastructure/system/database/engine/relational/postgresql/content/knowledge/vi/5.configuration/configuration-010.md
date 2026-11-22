# Kiểm tra lỗi cấu hình và thay đổi an toàn có phương án hoàn tác trong PostgreSQL

## 1. Vì sao thay đổi cấu hình cần một quy trình riêng?

Một PostgreSQL Server có thể đang phục vụ nhiều hệ thống cùng lúc: API giao dịch, công việc xử lý nền, báo cáo, kết nối quản trị và replication. Thay đổi một tham số như `work_mem` có thể ảnh hưởng mức sử dụng bộ nhớ của nhiều truy vấn; thay `max_connections` có thể thay đổi ngân sách tài nguyên sau khi khởi động lại; sửa `pg_hba.conf` có thể khiến ứng dụng hoặc người quản trị **không đăng nhập được**.

Không ít sự cố phát sinh từ những thao tác tưởng như nhỏ:

- Sửa đúng một file nhưng **file đó không phải file cấu hình đang được server dùng**.
- Có giá trị mới trong `postgresql.conf` nhưng bị `postgresql.auto.conf` hoặc một nguồn khác ghi đè.
- Gọi `pg_reload_conf()`, thấy trả `true` rồi kết luận mọi thay đổi đã được áp dụng.
- Thay tham số **cần restart** nhưng chỉ reload.
- Thay quyền kết nối trong `pg_hba.conf` và mất luôn đường đăng nhập quản trị.
- Cấu hình đúng cú pháp nhưng gây **tải cao, hết bộ nhớ, query timeout hoặc chậm ứng dụng**.
- Có backup file nhưng không biết **cách hoàn tác**, ai quyết định rollback và cách xác nhận hệ thống đã trở về trạng thái an toàn.

Bài học này trình bày một quy trình xuyên suốt:

1. **Xác định cấu hình hiệu lực và nguồn gốc của nó.**
2. **Tìm lỗi cú pháp, lỗi giá trị và lỗi phạm vi áp dụng.**
3. **Đánh giá tác động và chuẩn bị trước khi thay đổi.**
4. **Triển khai theo cách nhỏ nhất có thể, có xác minh.**
5. **Theo dõi dấu hiệu bất thường, hoàn tác nếu vượt ngưỡng đã định.**
6. **Ghi lại kết quả, giữ khả năng khôi phục cho thay đổi sau.**

Ví dụ hướng đến PostgreSQL hiện đại và môi trường Linux thông dụng. Đường dẫn, dịch vụ, quyền và cách điều phối restart khác nhau giữa bản cài trực tiếp, container, Kubernetes và các dịch vụ PostgreSQL được quản lý. **Không dùng nguyên xi lệnh quản lý tiến trình** nếu không phù hợp hệ thống thật.

> **Nguyên tắc quan trọng:** ví dụ thay đổi cấu hình chỉ chạy trên **lab hoặc staging được phép**. Trên production, cần runbook/phê duyệt, cửa sổ bảo trì khi cần, quyền dự phòng và kế hoạch rollback trước khi nhấn Reload hoặc Restart.

## 2. Phân biệt “giá trị trong file” và “giá trị hiệu lực”

PostgreSQL có nhiều tầng cấu hình. Cùng một tên tham số có thể xuất hiện ở hơn một nơi:

~~~text
Khởi động PostgreSQL
  ├── Tham số dòng lệnh cho server
  ├── postgresql.conf
  │     ├── include '...'
  │     ├── include_if_exists '...'
  │     └── include_dir '...'
  └── postgresql.auto.conf (thường do ALTER SYSTEM ghi)
             |
             v
    Giá trị cấu hình áp dụng ở mức server
             |
             +--- ALTER DATABASE ... SET
             +--- ALTER ROLE ... SET
             +--- ALTER ROLE ... IN DATABASE ... SET
             +--- startup options / cấu hình kết nối
             +--- SET / SET LOCAL trong session (nếu tham số cho phép)
             |
             v
    Giá trị hiệu lực của session đang quan sát
~~~

Sơ đồ nhằm phân loại **nguồn**, không phải bảng thứ tự ưu tiên tuyệt đối cho tất cả tham số. Thứ tự thực tế phụ thuộc **ngữ cảnh của tham số**, mức override và các quy tắc PostgreSQL.

### 2.1. Các nguồn cấu hình thường gặp

| Nguồn | Phạm vi | Khi nào liên quan? |
|---|---|---|
| `postgresql.conf` | Cấu hình server | Thiết lập cơ sở của cluster PostgreSQL |
| `include` / `include_dir` | Các tệp cấu hình được nạp thêm | Tổ chức cấu hình theo nhóm/môi trường |
| `postgresql.auto.conf` | Override mức server, do `ALTER SYSTEM` quản lý | Khi cấu hình đã được đặt qua SQL `ALTER SYSTEM` |
| Server command line | Tùy tham số, có thể ưu tiên cao | Khi service/container chạy postgres với tùy chọn `-c` |
| `ALTER DATABASE ... SET` | Giá trị mặc định cho kết nối mới tới database | Khi mỗi database cần cấu hình session riêng |
| `ALTER ROLE ... SET` | Giá trị mặc định cho kết nối mới của role | Khi ứng dụng/user có nhu cầu riêng |
| `ALTER ROLE ... IN DATABASE ... SET` | Giá trị cho tổ hợp role + database | Khi phải giới hạn chính xác phạm vi |
| Startup options | Session mới | Client/driver truyền option khi đăng nhập |
| `SET` / `SET LOCAL` | Session hoặc transaction, với GUC cho phép | Khi cần thay đổi tạm thời trong phạm vi hẹp |

Các thay đổi ở cấp role/database thường áp dụng khi **bắt đầu session mới**; chúng không tự động sửa mọi kết nối đang mở từ trước. Ngược lại, một số tham số được nạp lại bằng SIGHUP ở các tiến trình backend hiện hữu.

### 2.2. Không phải tham số nào cũng cho phép SET

PostgreSQL phân loại tham số theo `context`. Ví dụ `max_connections` không thể tăng trong một session bằng `SET max_connections = 200`: nó cần restart server. Một tham số như `statement_timeout` có thể được điều chỉnh trong session khi người dùng có quyền thích hợp.

Vì thế phải tìm hiểu **tham số cho phép thay đổi ở cấp nào**, thay vì đoán từ tên hoặc chỉ nhìn file.

### 2.3. Tình huống override dễ gây nhầm lẫn

Giả sử file `postgresql.conf` ghi:

~~~conf
work_mem = '8MB'
~~~

nhưng trước đó có người đã chạy:

~~~sql
ALTER SYSTEM SET work_mem = '16MB';
~~~

Sau reload, trong những bối cảnh không có override khác, giá trị mặc định server thường lấy từ `postgresql.auto.conf` và có thể là **16MB**, không phải 8MB.

Nếu session ứng dụng lại thực hiện:

~~~sql
SET work_mem = '32MB';
~~~

thì `SHOW work_mem` trong session ấy có thể thấy 32MB. Đây là lý do khi điều tra cần ghi nhận **giá trị hiệu lực, nguồn cấu hình và phạm vi của session**, không chỉ grep một file.

## 3. Kiểm tra nhanh server và các đường dẫn cấu hình

### 3.1. Xác minh kết nối đúng máy

Trước khi thao tác:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    inet_server_addr() AS server_ip,
    inet_server_port() AS server_port,
    version() AS postgres_version;
~~~

Một số kết nối qua Unix-domain socket có thể khiến `inet_server_addr()` hoặc port trả `NULL`. Điều đó không tự là lỗi; cần đối chiếu kiểu kết nối và endpoint thực tế.

Nếu ứng dụng sử dụng proxy, DNS, connection pooler hoặc endpoint failover, hãy xác nhận **server đích thực sự** bằng thông tin vận hành, không chỉ dựa trên tên database giống nhau giữa staging và production.

### 3.2. Tìm file cấu hình mà server đang dùng

Với quyền phù hợp:

~~~sql
SHOW config_file;
SHOW hba_file;
SHOW ident_file;
SHOW data_directory;
~~~

Ý nghĩa:

- `config_file`: file cấu hình chính.
- `hba_file`: file điều khiển xác thực client.
- `ident_file`: file ánh xạ định danh dùng với các cơ chế xác thực liên quan.
- `data_directory`: thư mục dữ liệu PostgreSQL.

Các giá trị có thể khác mặc định; một container hoặc dịch vụ managed có thể tổ chức file ngoài data directory. Một số tham số và đường dẫn bị giới hạn theo quyền. Nếu gặp lỗi quyền, cần nhờ người phụ trách cung cấp thông tin, **không đổi role thành superuser chỉ để xem đường dẫn**.

### 3.3. Thời điểm tải cấu hình gần nhất

~~~sql
SELECT
    pg_postmaster_start_time() AS server_started_at,
    pg_conf_load_time() AS configuration_last_loaded_at;
~~~

`pg_postmaster_start_time()` giúp nhận biết server đã khởi động lại hay chưa. `pg_conf_load_time()` phản ánh lần tải lại cấu hình theo quy tắc của PostgreSQL; kết quả có thể liên quan thời điểm backend trong session xử lý reload.

**Thời điểm mới không chứng minh mọi dòng cấu hình mới đều hợp lệ hoặc đã hiệu lực.** Phải đối chiếu trạng thái tham số, lỗi parse và log.

## 4. Khám phá pg_settings: nguồn sự thật của session hiện tại

`pg_settings` là system view quan trọng nhất khi kiểm tra các tham số vận hành.

### 4.1. Truy vấn trạng thái tham số

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    vartype,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem',
    'shared_buffers',
    'max_connections',
    'statement_timeout',
    'log_min_duration_statement',
    'listen_addresses'
)
ORDER BY name;
~~~

Các trường cần hiểu:

| Trường | Ý nghĩa |
|---|---|
| `name` | Tên tham số |
| `setting` | Giá trị hiệu lực dạng nội bộ/text của tham số |
| `unit` | Đơn vị lưu trong metadata, ví dụ `kB` hoặc `8kB` |
| `context` | Bối cảnh cần thiết để thay đổi có hiệu lực |
| `vartype` | Kiểu tham số: bool, integer, real, string, enum |
| `source` | Nguồn đã xác định giá trị hiệu lực, như default, configuration file, database/user, client, session |
| `sourcefile` / `sourceline` | File/dòng có liên quan nếu nguồn là file và có quyền hiển thị |
| `pending_restart` | Có thay đổi dạng cần restart đang chờ áp dụng hay không |

`sourcefile` và `sourceline` có thể trả `NULL` vì giá trị không đến từ file **hoặc** vì role không được xem đường dẫn theo quyền hiện tại. Không kết luận “không có cấu hình file” chỉ từ một ô `NULL`.

### 4.2. Phân biệt setting và unit

Ví dụ một số GUC lưu `setting` là `8192` nhưng `unit` lại là `8kB` hay `kB` tùy tham số. Nếu muốn giá trị dễ đọc, dùng:

~~~sql
SHOW work_mem;
SHOW shared_buffers;
SHOW statement_timeout;
~~~

Không tự coi `pg_settings.setting = 8192` luôn là 8192 **byte**. Hãy xem `unit` và định nghĩa chính xác của tham số.

### 4.3. Xem mô tả và giới hạn

~~~sql
SELECT
    name,
    short_desc,
    context,
    vartype,
    min_val,
    max_val,
    enumvals,
    boot_val,
    reset_val
FROM pg_settings
WHERE name IN (
    'work_mem',
    'max_connections',
    'wal_level'
)
ORDER BY name;
~~~

- `short_desc` cho biết mục đích cơ bản.
- `min_val` / `max_val` giới hạn giá trị với các kiểu phù hợp.
- `enumvals` có thể chứa các giá trị enum cho phép.
- `boot_val` là mặc định được biên dịch.
- `reset_val` là giá trị dùng khi `RESET` session, không phải bản sao file trước khi bạn sửa.

**Không dùng `reset_val` như bằng chứng chắc chắn về “giá trị production trước thay đổi”**. Muốn rollback đúng cần lưu baseline ở thời điểm trước thao tác, gồm cả nguồn và file.

### 4.4. So sánh cùng tham số ở hai session

Session DBA và session ứng dụng có thể có `SHOW statement_timeout` khác nhau do `ALTER ROLE`, `ALTER DATABASE`, startup options hoặc `SET`. Vì vậy không chỉ dùng SQL trên một session superuser rồi kết luận chính xác mọi ứng dụng đang chạy với cùng giá trị.

Một kiểm tra đáng tin cậy phải thực hiện **trong đúng database, role và loại kết nối** mà ứng dụng sử dụng, hoặc có bằng chứng từ cấu hình và trạng thái các session ứng dụng.

## 5. Phân loại tham số theo cách áp dụng

### 5.1. Context trong pg_settings

| `context` thường gặp | Cách hiểu vận hành |
|---|---|
| `internal` | Giá trị nội bộ, không đổi bằng cấu hình người dùng |
| `postmaster` | Cần **restart server** để thay đổi hiệu lực |
| `sighup` | Có thể nạp lại cấu hình bằng SIGHUP/reload |
| `backend` | Cấu hình có thể ảnh hưởng tới backend khi **session mới bắt đầu** |
| `superuser-backend` | Tương tự phạm vi backend nhưng có giới hạn quyền |
| `superuser` | Có thể do role có đặc quyền phù hợp điều chỉnh trong session; file thay đổi thường cần reload |
| `user` | Có thể được thay đổi ở session bởi người dùng trong phạm vi cho phép |

Tên context không đồng nhất với **quyền chỉnh mọi file**. Một tham số có `context=user` vẫn có thể bị hạn chế theo thiết lập, môi trường managed service hoặc chính sách tổ chức.

### 5.2. Những ví dụ điển hình

| Tham số | Vai trò | Ghi chú áp dụng |
|---|---|---|
| `max_connections` | Số kết nối tối đa theo cấu hình server | Thường là `postmaster`: cần restart |
| `shared_buffers` | Bộ nhớ đệm chia sẻ của PostgreSQL | `postmaster`: cần restart |
| `listen_addresses` | Địa chỉ mạng server lắng nghe | `postmaster`: cần restart |
| `wal_level` | Mức thông tin WAL | Thường cần restart và có tác động replication |
| `log_min_duration_statement` | Ngưỡng ghi log câu SQL chậm | Có thể reload ở cấp phù hợp |
| `work_mem` | Ngân sách bộ nhớ cho các thao tác sort/hash theo quy tắc thực thi | Có thể cấu hình session phù hợp |
| `statement_timeout` | Thời gian giới hạn thực thi statement | Có thể cấu hình session phù hợp |
| `lock_timeout` | Thời gian tối đa đợi lấy lock | Có thể cấu hình session phù hợp |

Nên **xem `pg_settings.context` trên đúng phiên bản server** thay vì thuộc lòng một danh sách cố định; các tham số, đặc quyền và semantics có thể thay đổi giữa các phiên bản.

### 5.3. Reload không phải restart

- **Reload:** yêu cầu PostgreSQL đọc lại các file cấu hình có thể áp dụng trong khi server tiếp tục chạy. Các setting đòi `postmaster` vẫn chờ restart.
- **Restart:** dừng rồi khởi động lại tiến trình PostgreSQL; làm gián đoạn kết nối, có thể kích hoạt failover/khôi phục theo topology và cần phối hợp ứng dụng.
- **Session mới:** một số thay đổi mặc định của role/database hoặc backend context chỉ xuất hiện khi kết nối mới được tạo.
- **SET/SET LOCAL:** áp dụng cho một session hoặc transaction, không phải bằng chứng cấu hình toàn hệ thống đã đổi.

Đừng dùng restart như bước mặc định cho mọi lỗi cấu hình: nhiều thay đổi có thể được áp dụng an toàn hơn bằng reload, còn restart có thể gây gián đoạn dịch vụ lớn.

## 6. Phát hiện lỗi trong file: pg_file_settings

PostgreSQL có view `pg_file_settings` cho phép xem kết quả phân tích các entry từ file cấu hình trong phạm vi quyền.

~~~sql
SELECT
    sourcefile,
    sourceline,
    seqno,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
ORDER BY seqno;
~~~

Đây là cách quan sát hữu ích khi:

- Có nhiều file `include` với thứ tự áp dụng khác nhau.
- Một tham số xuất hiện lặp lại.
- Một dòng có cú pháp/giá trị không được chấp nhận.
- Cần biết thông tin dòng nào được áp dụng hay bị ghi đè.

### 6.1. Tìm lỗi rõ ràng

~~~sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    error
FROM pg_file_settings
WHERE error IS NOT NULL
ORDER BY sourcefile, sourceline;
~~~

Nếu có lỗi, cần giải thích thông báo, sửa đúng file và **kiểm tra lại**. Lỗi có thể liên quan cú pháp, tham số không tồn tại, giá trị không hợp lệ, thiếu điều kiện áp dụng hoặc ngữ cảnh.

**Không nhìn một view lỗi rỗng rồi khẳng định PostgreSQL sẽ khởi động lại thành công**: còn các vấn đề ngoài cú pháp như tài nguyên, filesystem, certificate, quyền file, extension và topology.

### 6.2. applied=false không luôn là lỗi

`pg_file_settings.applied = false` có thể xuất hiện vì:

- Entry trước đó bị **override** bởi một entry có ưu tiên/đứng sau.
- Một thay đổi không thể áp dụng ở thời điểm hiện tại (ví dụ cần restart).
- Có lỗi cụ thể ở entry hoặc tập file.

Do đó, nên đọc **`error`**, chuỗi các entry cùng `name`, `pg_settings.source` và `pending_restart` trước khi đánh giá.

~~~sql
SELECT
    sourcefile,
    sourceline,
    seqno,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE name = 'work_mem'
ORDER BY seqno;
~~~

Đây là ví dụ giúp phân biệt một cấu hình trong file chính đã bị ghi đè bởi một cấu hình file khác.

### 6.3. Quyền truy cập

Không phải role ứng dụng nào cũng được phép xem mọi thông tin file cấu hình qua các system views. Nếu kết quả bị từ chối hoặc có trường ẩn, dùng quyền **đọc cấu hình có kiểm soát**, không tự grant superuser. Cấu hình có thể chứa đường dẫn nội bộ và thông tin liên quan bảo mật.

## 7. Lỗi đường dẫn và thứ tự include

### 7.1. Các directive cấu hình

Trong `postgresql.conf` có thể gặp:

~~~conf
include = 'common.conf'
include_if_exists = 'site-override.conf'
include_dir = 'conf.d'
~~~

Điều quan trọng:

- `include` yêu cầu file được chỉ định tồn tại/hợp lệ theo quy tắc parser.
- `include_if_exists` cho phép bỏ qua khi file không tồn tại.
- `include_dir` tải các file cấu hình đủ điều kiện trong thư mục theo thứ tự tên được PostgreSQL định nghĩa; thứ tự này có thể khiến giá trị xuất hiện sau override giá trị trước.
- Đường dẫn tương đối có quy tắc giải quyết theo vị trí file cấu hình liên quan; không đoán từ working directory của terminal.
- Tệp `postgresql.auto.conf` là nguồn khác và thường có ưu tiên hơn các mục trong `postgresql.conf` theo cơ chế cấu hình server.

Ví dụ:

~~~text
postgresql.conf
   work_mem = '8MB'
   include_dir = 'conf.d'

conf.d/10-base.conf
   work_mem = '12MB'

conf.d/90-app.conf
   work_mem = '16MB'

postgresql.auto.conf
   work_mem = '24MB'
~~~

Giá trị mặc định server sau khi nạp có thể lấy từ override ở nguồn sau/cao hơn, **nhưng session cụ thể vẫn có thể đặt giá trị khác**. Tìm nguyên nhân với `pg_file_settings` và `pg_settings`, không chỉ grep dòng đầu tiên.

### 7.2. Không sửa nhầm file được công cụ quản lý tạo

Ở dịch vụ managed hoặc môi trường triển khai bằng automation, file có thể được tạo lại bởi Helm chart, operator, Ansible, Terraform hoặc control plane. Một chỉnh sửa thủ công đôi khi bị ghi đè ở lần triển khai sau.

Phải xác định **source of truth** của cấu hình: repository, ConfigMap, tham số dịch vụ quản lý, API cloud, hay file trực tiếp trên host. Kế hoạch rollback cũng phải thực hiện **qua cùng kênh quản lý** nếu không muốn hệ thống drift.

## 8. pg_hba.conf: kiểm tra xác thực và tránh tự khóa mình

`pg_hba.conf` xác định các quy tắc cho phép và phương thức xác thực kết nối PostgreSQL. Tên viết tắt HBA là **Host-Based Authentication**, nhưng file này cũng có quy tắc cho kết nối local.

Một dòng minh họa:

~~~conf
# TYPE     DATABASE  USER           ADDRESS           METHOD
hostssl    shopdb    report_reader  192.0.2.0/24      scram-sha-256
~~~

Ở đây:

- `hostssl` chỉ khớp kết nối TCP có SSL/TLS nếu server cấu hình hỗ trợ SSL.
- `shopdb` giới hạn database.
- `report_reader` giới hạn role.
- `192.0.2.0/24` là dải IP ví dụ dành cho tài liệu, không phải IP thực của môi trường.
- `scram-sha-256` là phương pháp xác thực mật khẩu theo SCRAM.

`pg_hba.conf` **không tự kích hoạt server lắng nghe mạng**: `listen_addresses`, firewall, DNS, proxy và TLS server còn phải được cấu hình phù hợp.

### 8.1. Quy tắc được xét theo thứ tự

PostgreSQL dùng **quy tắc khớp đầu tiên** theo thứ tự trong `pg_hba.conf` cho một kết nối phù hợp. Không có cơ chế “nếu mật khẩu sai ở dòng này thì thử một dòng khác lỏng hơn” như một fallback thông thường.

Ví dụ:

~~~conf
# Dòng chặt cho nguồn cụ thể
hostssl shopdb report_reader 192.0.2.10/32 scram-sha-256

# Dòng tổng quát cho cả dải
hostssl shopdb report_reader 192.0.2.0/24 scram-sha-256
~~~

Dòng đầu khớp trước nếu kết nối đến từ `192.0.2.10`. Nếu đặt dòng `reject` hoặc chính sách chặn trước các dòng cần thiết, bạn có thể khóa đường truy cập dự kiến.

**Không tự thêm dòng mở toàn mạng** như `0.0.0.0/0` với phương thức xác thực yếu để giải quyết lỗi kết nối. Điều đó làm tăng bề mặt tấn công và thường không đúng nguyên nhân.

### 8.2. Kiểm tra file HBA bằng pg_hba_file_rules

Với quyền phù hợp:

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

Các dòng có `error IS NOT NULL` cho biết vấn đề parser hoặc cú pháp được PostgreSQL nhận diện:

~~~sql
SELECT line_number, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL
ORDER BY line_number;
~~~

**Giới hạn của kiểm tra này:**

- View phản ánh các quy tắc từ **nội dung file hiện tại**, không nhất thiết một ảnh chụp không đổi của các quy tắc đang phục vụ mọi kết nối.
- Không có `error` **không đảm bảo** người dùng đăng nhập được. Vẫn cần đúng host, database, role, password/certificate, SSL và thứ tự matching.
- Quy tắc còn có tác động với các **kết nối mới**; một kết nối đã mở không tự được “xác thực lại” chỉ vì file HBA vừa đổi.
- Trên một số nền tảng/hình thức triển khai có khác biệt về thời điểm áp dụng file; hãy theo quy trình reload của môi trường.

### 8.3. Kế hoạch thay HBA an toàn

Trước khi đổi:

1. Xác nhận **đường vào quản trị dự phòng** độc lập với quy tắc sắp thay (ví dụ kết nối local/tunnel/bastion đã kiểm chứng).
2. Sao lưu chính xác file `pg_hba.conf` hiện tại, ghi checksum/version.
3. Mô tả những kết nối phải tiếp tục hoạt động: ứng dụng, job, replica, monitoring, DBA.
4. Giữ **kết nối quản trị đang mở** trong lúc kiểm tra; đừng coi nó là đảm bảo duy nhất cho khả năng khôi phục.
5. Sửa đúng một nhóm quy tắc với phạm vi rõ ràng.
6. Kiểm tra `pg_hba_file_rules`, reload theo runbook và **thử đăng nhập bằng kết nối mới** từ các nguồn thật.
7. Nếu thất bại, **phục hồi file HBA cũ**, reload, thử lại và kiểm tra log.

Khi kết nối từ một máy chủ ứng dụng qua proxy, IP mà PostgreSQL thấy có thể là địa chỉ của proxy/NAT, không phải IP máy người dùng. Phải xác minh thực tế thay vì suy đoán CIDR từ mạng nội bộ.

## 9. pg_ident.conf và các lỗi ánh xạ danh tính

`pg_ident.conf` phục vụ ánh xạ giữa danh tính hệ điều hành hoặc danh tính xác thực ngoài và role PostgreSQL trong một số phương thức xác thực như `ident`/`peer` khi có cấu hình `map` phù hợp.

Nếu HBA dùng mapping mà file ident thiếu/sai, đăng nhập có thể thất bại dù tên role tồn tại.

Kiểm tra khi có view/phiên bản hỗ trợ:

~~~sql
SELECT *
FROM pg_ident_file_mappings
WHERE error IS NOT NULL;
~~~

Hoặc xem các rule mapping hiện tại:

~~~sql
SELECT
    line_number,
    map_name,
    sys_name,
    pg_username,
    error
FROM pg_ident_file_mappings
ORDER BY line_number;
~~~

Khi lỗi, cần đối chiếu:

- HBA rule đang dùng mapping name nào.
- Hệ thống xác thực cung cấp danh tính nào.
- Mapping có cho phép trở thành role PostgreSQL dự kiến không.
- Cú pháp file có hợp lệ không.

Không nên thay toàn bộ xác thực sang `trust` chỉ để vượt lỗi mapping. `trust` có thể cho phép kết nối không cần xác minh mật khẩu theo quy tắc khớp, nguy hiểm nếu phạm vi mạng không được kiểm soát.

## 10. Tìm lỗi cấu hình trong log

System views giúp kiểm tra metadata; log giúp biết PostgreSQL **đã làm gì khi parse/reload/startup**.

### 10.1. Những nhóm thông báo thường gặp

Ví dụ thông điệp có thể liên quan đến:

- `unrecognized configuration parameter`: tham số không tồn tại/không được hỗ trợ ở phiên bản đó.
- `invalid value for parameter`: giá trị không thể chuyển đổi, nằm ngoài giới hạn hoặc enum sai.
- `parameter ... cannot be changed without restarting the server`: cần restart.
- `could not open configuration file`: đường dẫn/quyền/file thiếu.
- `could not load ... certificate/key`: lỗi tài nguyên TLS khi có cấu hình liên quan.
- `no pg_hba.conf entry for host ...`: không có quy tắc xác thực phù hợp cho kết nối.
- `password authentication failed for user ...`: xác thực thất bại, phải phân biệt với thiếu HBA rule.
- `FATAL: ...` khi startup: cấu hình hoặc điều kiện môi trường ngăn server chạy.

Văn bản cụ thể khác theo phiên bản và tình huống; phải đọc **log đầy đủ, timestamp, process ID, host và mức độ lỗi**.

### 10.2. Log nằm ở đâu?

Phụ thuộc cấu hình và cách triển khai:

- PostgreSQL logging collector.
- journald/systemd hoặc log của process manager.
- Container stdout/stderr và log aggregator.
- Dịch vụ managed database có giao diện/API đọc log riêng.

Không mặc định `/var/log/postgresql/postgresql.log` luôn tồn tại. Trước khi tìm log, xem cách instance được triển khai và các thông số logging liên quan như `logging_collector`, `log_destination`, `log_directory` khi có quyền.

### 10.3. Tránh làm lộ bí mật khi cung cấp log

Log có thể chứa SQL, tên user, địa chỉ IP, tên database hoặc dữ liệu từ error message. Khi gửi báo cáo sự cố, chỉ chia sẻ phần cần thiết và loại bỏ password, token hoặc dữ liệu cá nhân theo quy trình bảo mật.

## 11. Quy trình chuẩn bị thay đổi an toàn

Một thay đổi cấu hình có chất lượng nên có một **change record** tối thiểu:

| Thành phần | Ví dụ nội dung |
|---|---|
| Mục tiêu | Giảm thời gian chạy báo cáo hoặc tăng quan sát query chậm |
| Phạm vi | Instance nào, primary hay replica, database/role nào |
| Giá trị hiện tại | Giá trị hiệu lực, nguồn, file/dòng, `pending_restart` |
| Giá trị đề xuất | `log_min_duration_statement = '750ms'` |
| Lý do | Ghi log query trên 750 ms để đo trong thời gian giới hạn |
| Tác động | Tăng lưu lượng log, khả năng log chứa SQL nhạy cảm |
| Kiểu áp dụng | Reload / session mới / restart |
| Phép kiểm chứng | `SHOW`, `pg_settings`, log, test query, metric |
| Điều kiện rollback | Log tăng đột biến, CPU/I/O hoặc độ trễ vượt ngưỡng |
| Cách rollback | Khôi phục đúng nguồn cũ, reload/restart, xác nhận |
| Người chịu trách nhiệm | Người triển khai và người phê duyệt |
| Thời hạn quan sát | Khoảng thời gian được thỏa thuận trong change plan |

Nếu chưa biết **giá trị cũ và nguồn hiệu lực**, bạn chưa đủ cơ sở nói rằng “có thể hoàn tác”.

### 11.1. Lưu baseline của các tham số liên quan

~~~sql
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
    'log_min_duration_statement',
    'statement_timeout',
    'work_mem',
    'max_connections'
)
ORDER BY name;
~~~

Lưu kết quả theo cách phù hợp và ghi thời điểm thực hiện. Nếu không được xem `sourcefile`, ghi rõ giới hạn quyền và lấy bằng chứng cấu hình qua hệ thống quản lý chính thức.

### 11.2. Lưu bản sao các file thay đổi

Nếu tự quản lý host:

- Sao lưu file gốc, quyền file/owner và checksum trước chỉnh sửa.
- Không sao chép tùy tiện file chứa bí mật đến thư mục công khai.
- Dùng version control hoặc công cụ quản lý cấu hình có review.
- Tránh hai người cùng sửa một file bằng những kênh khác nhau.
- Với `postgresql.auto.conf`, ưu tiên quản lý qua `ALTER SYSTEM` khi server đang chạy; không chỉnh tay trái quy trình.

Trong dịch vụ managed, lưu **bản export của parameter group hoặc cấu hình tương đương**, vì không phải người dùng nào cũng có quyền đọc file OS.

### 11.3. Thử trước ở môi trường tương tự

Nếu có staging:

1. Dùng PostgreSQL version và extension tương thích.
2. Dựng dữ liệu/workload đại diện nếu cần benchmark.
3. Thử đúng phương thức thay đổi: SQL, file, operator hoặc API.
4. Thực hiện cả **rollback thử**.
5. Ghi thời gian reload/restart và ảnh hưởng tới kết nối/replication.
6. Đối chiếu metric với baseline, không chỉ nhìn tham số đã đổi.

Một cấu hình hợp lệ về cú pháp có thể thất bại **về hiệu năng** khi workload tăng; vì vậy preflight phải bao gồm cả kế hoạch đo tác động.

## 12. Thay đổi thử trong transaction: SET LOCAL

Khi chỉ muốn kiểm tra tác động của `work_mem` tới **một truy vấn phân tích**, phương án rủi ro thấp hơn đổi toàn server là `SET LOCAL`.

~~~sql
BEGIN;

SET LOCAL work_mem = '16MB';

SHOW work_mem;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM lab_orders
GROUP BY customer_id
ORDER BY order_count DESC;

ROLLBACK;
~~~

Ví dụ giả định bảng `lab_orders` đã tồn tại trong database lab. Có thể thay truy vấn bằng một câu `SELECT` hợp lệ khác của bạn; không chạy `EXPLAIN ANALYZE` trên query rất nặng ở production nếu chưa có sự cho phép.

`SET LOCAL` có phạm vi transaction. Sau `COMMIT` hoặc `ROLLBACK`, thiết lập local không tiếp tục là override của session đó.

### 12.1. SET khác SET LOCAL

~~~sql
-- Thay trong session hiện tại, nếu tham số và quyền cho phép.
SET statement_timeout = '5s';

SHOW statement_timeout;

-- Khôi phục giá trị session theo nguồn mặc định/session reset.
RESET statement_timeout;
~~~

`SET` thường có hiệu lực tới khi được reset hoặc session kết thúc (có các quy tắc transaction khi SET nằm trong transaction). `SET LOCAL` có hiệu lực trong transaction đang mở. Không dùng `RESET` như phương pháp rollback một thay đổi đã ghi vào `postgresql.conf` hoặc `postgresql.auto.conf` ở cấp server.

### 12.2. Vì sao thay đổi session an toàn hơn?

- Phạm vi ảnh hưởng nhỏ.
- Không cần restart.
- Có thể kết thúc transaction để dừng override.
- Giúp đo giả thuyết trước khi biến thành chính sách server.

Tuy nhiên, nếu truy vấn thử tiêu thụ nhiều tài nguyên, **SET LOCAL không làm query nặng trở nên vô hại**. Cần chọn câu SQL và môi trường phù hợp.

## 13. Thay đổi mặc định theo database hoặc role

Khi một ứng dụng cần timeout riêng, không nhất thiết phải đổi mặc định cho mọi user trong instance.

### 13.1. Ở cấp database

~~~sql
-- Chỉ chạy trên database lab, khi có quyền.
ALTER DATABASE shopdb
SET statement_timeout = '5s';
~~~

Các session **mở mới** vào `shopdb` có thể nhận mặc định này, trừ khi bị override bởi cấu hình có ưu tiên phù hợp. Những connection đang mở từ trước trong pool không nhất thiết đổi ngay.

Rollback:

~~~sql
ALTER DATABASE shopdb
RESET statement_timeout;
~~~

`RESET` ở đây **xóa override cấp database**. Nó không nhất thiết đưa kết nối đang mở về giá trị cũ, cũng không đặt một con số “mặc định PostgreSQL” nếu còn override ở tầng khác.

### 13.2. Ở cấp role

~~~sql
ALTER ROLE report_reader
SET statement_timeout = '30s';
~~~

Rollback:

~~~sql
ALTER ROLE report_reader
RESET statement_timeout;
~~~

### 13.3. Chỉ cho một tổ hợp role và database

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
SET work_mem = '32MB';
~~~

Rollback:

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
RESET work_mem;
~~~

Cần có quyền đối với role/database tương ứng. Đây là những câu **minh họa**, không nên chạy khi `shopdb` hoặc `report_reader` là đối tượng production không thuộc trách nhiệm của bạn.

### 13.4. Connection pool và tác động lên session mới

Nhiều ứng dụng dùng HikariCP, PgBouncer hoặc pool khác. Thay `ALTER ROLE` / `ALTER DATABASE` không đảm bảo các connection vật lý **đã tồn tại** sẽ tự cập nhật thiết lập mặc định. Cần có kế hoạch:

- Tạo kết nối **mới** để xác minh.
- Nếu cần, luân chuyển/recycle connection pool theo cơ chế ứng dụng.
- Tránh kill toàn bộ connection đồng thời khi tải cao.
- Với transaction pooling, hiểu cách pooler xử lý session state và reset query.
- Kiểm tra bằng **đúng role/database** mà ứng dụng sử dụng.

Không lấy `SHOW statement_timeout` của session DBA làm bằng chứng ứng dụng đã nhận chính sách mới.

## 14. Thay đổi cấu hình server bằng ALTER SYSTEM

`ALTER SYSTEM` là SQL dành cho việc đặt cấu hình **mức server**. PostgreSQL ghi các thiết lập này vào `postgresql.auto.conf`.

### 14.1. Ví dụ trên lab: bật log query chậm

Giả sử muốn đo những câu chạy trên 750 ms:

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '750ms';

SELECT pg_reload_conf();
~~~

`ALTER SYSTEM` yêu cầu quyền phù hợp, **không chạy trong transaction block**, và tác động phạm vi instance. `SELECT pg_reload_conf()` yêu cầu server nhận yêu cầu reload; kết quả `true` chủ yếu thể hiện yêu cầu SIGHUP được gửi, **không tự chứng minh mọi cấu hình đã được nạp thành công**.

Xác minh:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name = 'log_min_duration_statement';

SHOW log_min_duration_statement;

SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE name = 'log_min_duration_statement'
ORDER BY seqno;
~~~

Có thể có override trong session DBA làm `SHOW` không phản ánh default mà các session mới sẽ nhận. Kiểm tra thêm một kết nối mới không có `SET` cá nhân khi cần.

### 14.2. Hai cách hoàn tác khác nhau

**Trường hợp A — trước đó không có override qua ALTER SYSTEM:** có thể xóa override mới để quay lại nguồn bên dưới:

~~~sql
ALTER SYSTEM RESET log_min_duration_statement;
SELECT pg_reload_conf();
~~~

**Trường hợp B — trước đó đã có ALTER SYSTEM với giá trị cũ:** nếu thay từ `'1000ms'` sang `'750ms'`, cách khôi phục chính xác có thể là đặt lại **giá trị cũ**:

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '1000ms';
SELECT pg_reload_conf();
~~~

Dùng `RESET` trong trường hợp B sẽ xóa override hoàn toàn, khiến cấu hình lấy từ nguồn thấp hơn, **có thể khác 1000 ms**. Đó là lý do không thể rollback an toàn nếu chưa ghi nhận trạng thái ban đầu.

### 14.3. Tránh xung đột với quản lý cấu hình

Nếu automation đang tạo `postgresql.conf` mà DBA dùng `ALTER SYSTEM` để override, những lần deploy sau có thể thấy một giá trị trong file chính nhưng runtime lấy giá trị khác từ `postgresql.auto.conf`. Nên thống nhất **một kênh quản trị cấu hình**, hoặc ghi rõ quy tắc override và có kế hoạch giải quyết drift.

Không xóa toàn bộ `postgresql.auto.conf` chỉ vì một tham số gây lỗi: file có thể chứa những override khác có chủ đích.

## 15. Thay đổi cần restart: lập kế hoạch khác hẳn reload

Một số tham số như `max_connections`, `shared_buffers` hoặc `listen_addresses` cần restart.

Ví dụ **chỉ dùng để minh họa yêu cầu restart**, không tự chạy trên production:

~~~sql
-- Ví dụ staging có kế hoạch restart:
ALTER SYSTEM SET max_connections = '250';

-- Reload không làm max_connections=250 có hiệu lực ngay.
SELECT pg_reload_conf();

SELECT
    name,
    setting,
    pending_restart
FROM pg_settings
WHERE name = 'max_connections';
~~~

Nếu giá trị mới hợp lệ nhưng cần restart, có thể thấy `pending_restart = true` trong bối cảnh phù hợp. `SHOW max_connections` thường vẫn thể hiện giá trị mà postmaster đang chạy sử dụng.

### 15.1. Tại sao restart nguy hiểm hơn?

- Ngắt các session ứng dụng đang kết nối.
- Dừng query/transaction chưa hoàn thành; ứng dụng phải xử lý lỗi kết nối đúng.
- Có thể gây backlog request khi pool cùng tạo connection mới.
- Có thể liên quan failover và replication lag trong môi trường HA.
- Có nguy cơ server **không khởi động lại được** nếu cấu hình lỗi hoặc tài nguyên thiếu.
- Thay `max_connections` hoặc `shared_buffers` có tác động ngân sách RAM và tài nguyên hệ điều hành.

Vì vậy restart cần:

1. Xác nhận đúng instance và topology.
2. Kiểm tra dung lượng/tài nguyên, thông số OS, replica và số connection dự kiến.
3. Lập maintenance window hoặc quy trình rolling/failover phù hợp.
4. Sao lưu cấu hình và xác nhận đường vào recovery.
5. Thử restart ở staging với phiên bản/cấu hình tương đương.
6. Có người giám sát log, health check và trạng thái kết nối.
7. Định nghĩa **deadline hoặc điều kiện dừng** cho phép rollback.
8. Xác nhận lại ứng dụng và replication sau khi hoàn tất.

### 15.2. Không gợi ý một lệnh restart áp dụng chung

Trong các môi trường khác nhau, restart có thể qua:

- `systemctl` và service unit do package quản lý.
- `pg_ctl` theo data directory và user hệ điều hành chính xác.
- Kubernetes operator hoặc StatefulSet theo chính sách HA.
- API của dịch vụ PostgreSQL được quản lý.
- Công cụ orchestration cho cụm primary/standby.

Một thao tác như `systemctl restart postgresql` **không luôn chỉ đúng cluster mục tiêu**; trên một số máy có nhiều version/instance, tên unit khác hoặc lệnh có thể tác động nhiều thành phần. Chỉ chạy câu lệnh cụ thể theo runbook của môi trường.

### 15.3. Rollback tham số cần restart

Nếu thay `max_connections` từ 150 lên 250 và restart xong phát sinh sự cố:

1. Xác định rõ giá trị và **nguồn ban đầu** (ví dụ auto.conf đã có 150).
2. Phục hồi giá trị 150 qua đúng kênh quản lý.
3. Lập kế hoạch **restart lần nữa** để hiệu lực.
4. Xác minh `pg_settings`, số kết nối thực tế, health check và metric sau restart.

Chỉ reload lại **không đủ** để hoàn tác một thay đổi `postmaster` đã được áp dụng bằng restart.

## 16. Kiểm tra trước reload và xác minh sau reload

Một mẫu checklist có thể dùng cho thay đổi tham số `sighup` hoặc file `pg_hba.conf`:

### 16.1. Trước khi áp dụng

- [ ] Đúng server, instance, environment và quyền được ủy quyền.
- [ ] Đã lưu giá trị hiệu lực, nguồn và backup file/record trước thay đổi.
- [ ] Đã phân loại context bằng `pg_settings.context`.
- [ ] Đã xem `pg_file_settings` cho các lỗi hiện có.
- [ ] Nếu sửa HBA/ident, đã đọc `pg_hba_file_rules` / `pg_ident_file_mappings`.
- [ ] Có kết nối quản trị dự phòng và bản sao file đáng tin.
- [ ] Đã xác định dấu hiệu thành công và ngưỡng rollback.
- [ ] Đã thông báo nhóm ứng dụng nếu hành vi timeout/log/role thay đổi.

### 16.2. Thao tác reload

Với quyền thích hợp:

~~~sql
SELECT pg_reload_conf();
~~~

Hoặc dùng phương thức reload từ service manager/operator theo runbook. Thao tác gửi yêu cầu reload không đồng nghĩa mọi backend ngay lập tức có cùng kết quả nếu còn các mức override/session context.

### 16.3. Sau khi áp dụng

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'log_min_duration_statement',
    'statement_timeout',
    'max_connections'
);

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

SELECT pg_conf_load_time();
~~~

Sau đó:

- Xem log có lỗi parse/reload không.
- Nếu thay HBA, tạo **kết nối mới** từ các đường ứng dụng/DBA và xác minh thành công.
- Nếu thay role/database defaults, kiểm tra bằng **session mới** đúng user/database.
- Nếu thay tham số dùng cho query, thử một câu đại diện trên staging và quan sát latency/log.
- Nếu `pending_restart` bật, không tuyên bố thay đổi đã áp dụng toàn bộ.
- Kiểm tra các số đo hệ thống so với baseline.

## 17. Theo dõi tác động: cấu hình đúng nhưng workload có thể sai

### 17.1. Các chỉ số hữu ích

| Nhóm | Metric/quan sát | Vì sao liên quan? |
|---|---|---|
| Kết nối | Số session, kết nối lỗi, pool acquisition timeout | Thay auth, giới hạn kết nối, timeout |
| Hiệu năng | Query latency p50/p95/p99, throughput | Thay bộ nhớ, planner hoặc giới hạn |
| CPU/I/O | CPU usage, IOPS, đọc/ghi đĩa, temp files | Sort/hash, query scan, logging |
| Bộ nhớ | RAM, swap, OOM killer, container memory | `work_mem` và tổng đồng thời |
| Lock | Lock wait, deadlock, transaction dài | Thay timeout hoặc load |
| WAL/replication | WAL volume, replica lag, state standby | Thay wal_level, logging/HA liên quan |
| Ứng dụng | HTTP error rate, retry, connection reset | Thay đổi ảnh hưởng client |
| Log | FATAL/ERROR, khối lượng log | Tăng logging hoặc lỗi cấu hình |
| Bảo mật | Authentication failures, unexpected grants | HBA/role/SSL |

Không nên xem một metric đơn lẻ là bằng chứng đầy đủ. Ví dụ tăng `work_mem` có thể giảm temporary I/O cho một truy vấn nhưng làm tổng memory vượt ngân sách khi nhiều truy vấn chạy đồng thời.

### 17.2. Pg_stat_activity để xem trạng thái session

~~~sql
SELECT
    pid,
    usename,
    datname,
    state,
    wait_event_type,
    wait_event,
    query_start,
    xact_start
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST
LIMIT 30;
~~~

Quyền xem chi tiết session của người khác có thể bị hạn chế. Đặc biệt lưu ý những session `idle in transaction` quá lâu khi thay timeout hoặc cấu hình pool.

### 17.3. Kiểm tra số kết nối

~~~sql
SELECT
    state,
    COUNT(*) AS sessions
FROM pg_stat_activity
GROUP BY state
ORDER BY sessions DESC;
~~~

Câu này đếm các phiên trong thống kê hiện tại với các quyền hiển thị tương ứng; **không đồng nghĩa** số HTTP request đang chạy hoặc số thread chờ connection pool. Phải ghép thêm metric ứng dụng/pool.

### 17.4. Không biến log chậm thành log dữ liệu nhạy cảm

Giảm `log_min_duration_statement` có thể tạo nhiều log SQL, đôi khi chứa literal nhạy cảm. Cần thống nhất thời hạn bật, quyền truy cập log và chính sách bảo mật. **Rollback do quá tải log** có thể cần diễn ra nhanh hơn quy trình tối ưu truy vấn lâu dài.

## 18. Tình huống A: tham số cấu hình “không đổi” sau reload

**Triệu chứng:** DBA sửa `postgresql.conf`:

~~~conf
work_mem = '16MB'
~~~

rồi gọi `pg_reload_conf()`, nhưng một session mới vẫn thấy `32MB`.

### 18.1. Các giả thuyết

1. Có override trong `postgresql.auto.conf`.
2. Có file `include_dir` ghi giá trị khác.
3. Role/database/session đặt giá trị riêng.
4. DBA sửa **không đúng file đang được sử dụng**.
5. Dòng cấu hình lỗi và chưa được áp dụng.
6. Query được thử trên **server hoặc session khác**.
7. Có server command line/startup options ghi đè.

### 18.2. Quy trình kiểm tra

~~~sql
SHOW config_file;

SELECT
    name, setting, unit, context,
    source, sourcefile, sourceline, pending_restart
FROM pg_settings
WHERE name = 'work_mem';

SELECT
    seqno, sourcefile, sourceline,
    setting, applied, error
FROM pg_file_settings
WHERE name = 'work_mem'
ORDER BY seqno;
~~~

Sau đó kết nối bằng role/database dự kiến để đối chiếu, xem log reload và file thực tế.

### 18.3. Hoàn tác đúng cách

Nếu lỗi bắt đầu từ override do `ALTER SYSTEM` mới, hoàn tác **override đó**; nếu lỗi do thay đổi file quản lý bởi GitOps, revert đúng commit rồi để automation áp dụng. Không sửa cùng một tham số ở nhiều tầng nhằm “ép” số mong muốn vì sẽ làm khó kiểm soát thay đổi tiếp theo.

## 19. Tình huống B: sửa pg_hba.conf làm ứng dụng mất kết nối

**Triệu chứng:** sau khi thay HBA, các connection cũ vẫn chạy, nhưng connection mới báo:

~~~text
FATAL: no pg_hba.conf entry for host ...
~~~

### 19.1. Giải thích

HBA xét các kết nối **mới**. Connection đang mở không chứng minh quy tắc mới hoạt động. Lỗi có thể do:

- Địa chỉ IP nguồn khác dự kiến (NAT/proxy).
- Sai database hoặc role trong rule.
- Không có rule cho TLS/non-TLS đúng kiểu.
- Dòng `reject` hoặc matching rule khác đứng trước.
- File sửa chưa được nạp hoặc có lỗi parse.

### 19.2. Phục hồi từng bước

1. Giữ đường truy cập DBA hiện hữu, kiểm tra khả năng vào console/out-of-band.
2. Xem log kết nối và `pg_hba_file_rules`.
3. So sánh file mới với bản backup, tìm những dòng đã thay.
4. Nếu vượt ngưỡng lỗi, **phục hồi file HBA trước thay đổi** và reload theo phương thức phù hợp.
5. Thử **kết nối mới** từ app, job, monitoring, DBA.
6. Khi ổn, phân tích nguyên nhân và chỉnh rule ở staging trước khi triển khai lại.

Không đề xuất `trust` hoặc mở CIDR toàn mạng làm cách sửa mặc định. Việc cấp phép phải bảo vệ cả khả năng truy cập **và** chính sách bảo mật.

## 20. Tình huống C: restart thất bại vì tham số không hợp lệ

**Triệu chứng:** sau khi sửa `shared_buffers` hoặc `max_connections`, PostgreSQL không khởi động lại được.

### 20.1. Việc cần làm

1. Giữ log startup nguyên vẹn và xác định **lỗi đầu tiên**.
2. Kiểm tra service/cluster thật sự được restart có phải mục tiêu không.
3. Đối chiếu file/parameter group mới với **baseline**.
4. Nếu do tài nguyên (RAM, shared memory, file descriptors, disk), không chỉ sửa cú pháp.
5. Phục hồi **cấu hình cuối cùng đã được xác nhận chạy tốt** qua phương thức phù hợp, khi PostgreSQL đang dừng nếu cần.
6. Khởi động lại theo runbook, xác minh health check và ứng dụng.
7. Kiểm tra các thành phần HA/replica liên quan, không chỉ một lần kết nối psql.

### 20.2. Khi SQL không còn dùng được

Nếu server không khởi động, bạn **không thể dựa vào `ALTER SYSTEM RESET` qua SQL**, vì không có PostgreSQL backend đang nhận lệnh. Việc khôi phục phải qua cơ chế quản lý file/configuration của host, container/operator hoặc control plane của managed service.

`postgresql.auto.conf` có thể liên quan nếu thay đổi do `ALTER SYSTEM` trước restart; đừng xóa file này bừa bãi. Cần sao lưu và phục hồi đúng phần cấu hình theo runbook, giữ quyền file/owner và tránh phá các override khác.

### 20.3. Vì sao không được “restart thử nhiều lần”?

Việc restart lặp vô kế hoạch có thể:

- Làm tăng thời gian gián đoạn.
- Gây failover lặp hoặc xung đột với orchestration.
- Làm ứng dụng mở lại connection theo đợt lớn.
- Làm mờ log hoặc trạng thái hệ thống trong quá trình điều tra.

Tốt hơn là dừng, xác định nguyên nhân đầu tiên và dùng **bản cấu hình đã biết tốt**.

## 21. Tình huống D: thay work_mem gây tăng RAM và temp I/O

`work_mem` thường được hiểu sai là “tổng bộ nhớ của một connection”. Trên thực tế, đây là ngân sách liên quan đến các thao tác executor như sort/hash theo các quy tắc riêng; **một query có thể sử dụng nhiều node**, nhiều query có thể chạy đồng thời, và hash operations còn có các hệ số/liên quan riêng.

Giả sử có 50 query đồng thời, mỗi query có nhiều thao tác sort/hash. Tăng `work_mem` từ 4MB lên 128MB toàn server có thể làm rủi ro dùng RAM tăng mạnh, dù một báo cáo riêng lẻ nhanh hơn.

### 21.1. Cách thử an toàn hơn

1. Chọn một query chậm có bằng chứng sort/hash spill.
2. Dùng `SET LOCAL work_mem` trên session lab/staging.
3. So sánh `EXPLAIN (ANALYZE, BUFFERS)` và temporary I/O.
4. Thử nhiều mức tải đồng thời.
5. Nếu hữu ích cho một nhóm report, cân nhắc **role/database override** thay vì tăng toàn cluster.
6. Có ngưỡng rollback về RAM/swap/OOM, không chỉ latency query.

Ví dụ trong lab:

~~~sql
BEGIN;
SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, COUNT(*)
FROM lab_orders
GROUP BY customer_id
ORDER BY COUNT(*) DESC;

ROLLBACK;
~~~

`lab_orders` là bảng minh họa do người học tạo trong môi trường lab. `EXPLAIN ANALYZE` **thực thi SELECT**; nếu dữ liệu thật rất lớn, nó vẫn có thể tạo tải đáng kể.

## 22. Tình huống E: đổi timeout khiến ứng dụng lỗi hàng loạt

Giả sử đặt `statement_timeout = '2s'` cho mọi session. Sau thay đổi, một số báo cáo mất 3–5 giây bắt đầu lỗi, dù trước đó thành công.

### 22.1. Đặt đúng tầng

Các timeout khác nhau:

| Timeout | Tác dụng điển hình |
|---|---|
| `statement_timeout` | Giới hạn thời gian thực thi một statement theo cơ chế server |
| `lock_timeout` | Giới hạn thời gian **chờ lấy lock** |
| `idle_in_transaction_session_timeout` | Giới hạn thời gian session bị idle trong transaction |
| `idle_session_timeout` | Giới hạn thời gian session idle ngoài transaction theo chính sách |
| Timeout của connection pool | Người gọi chờ mượn connection từ pool bao lâu |
| HTTP/request timeout | Client/gateway chờ request phản hồi bao lâu |

Không phải lỗi request hết 2 giây nào cũng là PostgreSQL statement timeout. Có thể là pool acquisition, HTTP deadline, lock wait hoặc mạng.

### 22.2. Phương án thay đổi có kiểm soát

Thay vì đặt timeout ngắn cho toàn instance:

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
SET statement_timeout = '30s';
~~~

Khi đó chỉ các **session mới** thuộc role/database tương ứng mới nhận giá trị mặc định này theo precedence. Điều này phù hợp hơn nếu báo cáo được tách role với ứng dụng OLTP.

Hoàn tác:

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
RESET statement_timeout;
~~~

Sau đó cần tạo session mới phù hợp để thấy giá trị reset, không kết luận sau một lệnh `SHOW` trong connection đang mở trước đó.

## 23. Cấu hình trong cluster có replication hoặc HA

Trên một PostgreSQL đơn lẻ, rollback đã cần cẩn thận. Trong cluster HA, mức độ phức tạp tăng vì có **primary, standby, failover, synchronous/asynchronous replication** và nhiều lớp orchestration.

### 23.1. Các câu hỏi trước khi đổi

- Tham số này có phải được cấu hình **nhất quán giữa primary và standby** không?
- Thay đổi có ảnh hưởng WAL, replication slot, timeline hoặc khả năng standby bắt kịp không?
- Restart standby trước có phù hợp với rolling change của hệ thống không?
- Nếu primary failover ngay sau khi thay, standby có nhận cùng cấu hình không?
- Client có dùng endpoint cố định hay discovery có thể đổi primary?
- Ai điều phối restart/failover? Có operator tự ghi lại config không?

Một số cấu hình replication như `wal_level`, `max_wal_senders`, `max_replication_slots` có liên quan trực tiếp đến kiến trúc; không thay theo ví dụ tối ưu query thông thường.

### 23.2. Không áp dụng cấu hình từng node một cách thủ công thiếu kiểm soát

Nếu primary nhận một file khác standby nhưng automation chưa đồng bộ, failover có thể làm lộ sự khác biệt. Cần xác định **source of truth**, chính sách roll-out và test failover đúng quyền. Đừng tự gọi `pg_ctl restart` trên một node do operator quản lý nếu operator có cơ chế riêng.

### 23.3. Xem trạng thái trước/sau

Các câu SQL hữu ích tùy vai trò máy:

~~~sql
SELECT pg_is_in_recovery() AS is_standby;

SELECT
    application_name,
    state,
    sync_state,
    replay_lag
FROM pg_stat_replication;
~~~

`pg_stat_replication` trên primary thể hiện những kết nối replication đang được báo cáo, với quyền hiển thị phù hợp. Trên standby, view này có thể không có hàng tương ứng primary-to-standby; cần các view/hàm phía standby thích hợp. `replay_lag` có thể là `NULL` trong một số trạng thái, không được diễn giải đơn giản rằng `NULL = 0 ms`.

Rollback thành công trong HA phải xác minh **đúng cấu hình ở các node liên quan** và health của replication, không chỉ kết quả `SHOW` trên một session.

## 24. Bảng quyết định reload, reconnect hay restart

| Thay đổi | Cơ chế thường cần | Cách xác minh | Hoàn tác |
|---|---|---|---|
| `SET LOCAL work_mem` | Trong transaction | `SHOW` cùng transaction, đo query | `ROLLBACK` hoặc kết thúc transaction |
| `SET statement_timeout` | Trong session | `SHOW` đúng session | `RESET` hoặc kết thúc session |
| `ALTER ROLE ... SET` | Session mới | Kết nối lại bằng đúng role | `ALTER ROLE ... RESET` rồi session mới |
| `ALTER DATABASE ... SET` | Session mới | Kết nối lại đúng database | `ALTER DATABASE ... RESET` rồi session mới |
| Sửa `postgresql.conf` với GUC `sighup` | Reload | `pg_settings`, `pg_file_settings`, log | Restore file cũ rồi reload |
| `ALTER SYSTEM SET` với GUC reloadable | Reload | `pg_settings` sourcefile/pending_restart, log | Khôi phục override cũ hoặc `RESET` rồi reload |
| Đổi `pg_hba.conf` | Reload theo môi trường; kiểm tra kết nối mới | `pg_hba_file_rules` và login mới | Restore HBA cũ, reload, login lại |
| GUC `postmaster` như `max_connections` | Restart | `pending_restart`, SHOW sau restart, health check | Restore giá trị/source cũ và restart nữa |
| Đổi tham số quản lý qua cloud/operator | Theo quy trình của control plane | Provider config + SQL + health | Revert qua chính control plane |

Bảng mô tả nguyên tắc. **Nguồn cấu hình, context và cách quản lý của instance** vẫn quyết định thao tác cụ thể. Không có một phím “rollback” dùng chung cho mọi cấp thay đổi.

## 25. Sơ đồ xử lý một thay đổi cấu hình

~~~mermaid
flowchart TD
    A["Có yêu cầu thay đổi cấu hình"] --> B["Xác minh đúng instance, role và scope"]
    B --> C["Ghi baseline giá trị + source + log/metrics"]
    C --> D["Đọc context và kiểm tra lỗi file"]
    D --> E{"Đã xác định cách áp dụng?"}
    E -- "Chưa" --> F["Tìm hiểu parameter, yêu cầu quyền, staging"]
    F --> D
    E -- "Có" --> G["Lưu cấu hình cũ và chuẩn bị rollback"]
    G --> H["Thử trên staging / canary khi khả thi"]
    H --> I["Áp dụng thay đổi trong phạm vi nhỏ nhất"]
    I --> J["Reload / reconnect / restart theo context"]
    J --> K["Xác minh giá trị + log + kết nối + workload"]
    K --> L{"Đạt điều kiện thành công?"}
    L -- "Có" --> M["Tiếp tục theo dõi và ghi change record"]
    L -- "Không" --> N["Rollback đúng nguồn và cơ chế"]
    N --> O["Xác minh lại hoạt động và baseline"]
~~~

**Rollback phải có phép xác minh riêng.** Một câu `ALTER SYSTEM RESET` chạy không lỗi không chứng minh service đã trở về trạng thái cũ; còn có source khác, session cũ, pending restart và tác động ứng dụng đã phát sinh.

## 26. Mẫu runbook chi tiết cho một thay đổi có thể reload

Giả sử staging đã có quyền thử cấu hình **ghi log query chậm**, và người phụ trách muốn giảm ngưỡng logging từ một giá trị đang có xuống 750ms.

### 26.1. Thu thập baseline

~~~sql
SELECT
    current_database(),
    current_user,
    pg_postmaster_start_time(),
    pg_conf_load_time();

SELECT
    name, setting, unit, context,
    source, sourcefile, sourceline, pending_restart
FROM pg_settings
WHERE name = 'log_min_duration_statement';

SELECT
    seqno, sourcefile, sourceline,
    setting, applied, error
FROM pg_file_settings
WHERE name = 'log_min_duration_statement'
ORDER BY seqno;
~~~

Ghi kết quả ra change record; đặc biệt xem có **override cũ trong auto.conf** không. Sao lưu configuration record nguồn theo phương pháp hạ tầng.

### 26.2. Đặt tiêu chí thay đổi

Ví dụ điều kiện chấp nhận:

- Cấu hình 750ms được nhận, không có parser error.
- Log bắt đầu phản ánh các truy vấn vượt ngưỡng khi có lưu lượng phù hợp.
- Không tăng lỗi hệ thống hoặc tăng log volume ngoài ngân sách.
- Latency và CPU/I/O không xấu đi vượt ngưỡng được nhóm vận hành xác định.
- Có đường quản trị vẫn đăng nhập được.

Những ngưỡng cụ thể phải do người chịu trách nhiệm workload đặt; bài không giả định **750ms** là giá trị tối ưu cho mọi hệ thống.

### 26.3. Áp dụng trong lab

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '750ms';

SELECT pg_reload_conf();
~~~

Sau đó:

~~~sql
SELECT
    name, setting, unit, source, pending_restart
FROM pg_settings
WHERE name = 'log_min_duration_statement';

SELECT sourcefile, sourceline, applied, error
FROM pg_file_settings
WHERE name = 'log_min_duration_statement'
ORDER BY seqno;
~~~

Ghi thời điểm reload, kiểm tra log và một session mới nếu cần. Không đưa một câu SQL bí mật hoặc có dữ liệu cá nhân vào log chỉ để thử một ngưỡng.

### 26.4. Rollback có điều kiện

Nếu **baseline không có override trong auto.conf**:

~~~sql
ALTER SYSTEM RESET log_min_duration_statement;
SELECT pg_reload_conf();
~~~

Nếu **baseline có override** (ví dụ `'1500ms'`):

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '1500ms';
SELECT pg_reload_conf();
~~~

Các lệnh trong hai nhánh là **lựa chọn theo baseline**, không chạy cả hai như một chuỗi. Sau rollback phải xác minh `SHOW`, `source`, log và tác động thực tế; session-level override có thể làm quan sát khác.

## 27. Bài tập thực hành

Các bài dưới đây chỉ nhằm luyện kỹ năng suy luận và kiểm tra. Những lệnh thay đổi cấu hình cần thực hiện trên **PostgreSQL lab** được cấp quyền hoặc mô tả bằng văn bản; không làm trên production chưa được phê duyệt.

### Bài 1 — Phân biệt nguồn cấu hình

File `postgresql.conf` có `work_mem = '8MB'`, nhưng `postgresql.auto.conf` có `work_mem = '16MB'`. Một session mới của role `report_reader` lại thấy `32MB`.

Hãy nêu ít nhất ba nơi cần kiểm tra và một câu SQL tìm `source` hiệu lực.

### Bài 2 — Reload hay restart?

Cho danh sách tham số:

~~~text
max_connections
shared_buffers
log_min_duration_statement
statement_timeout
listen_addresses
~~~

Hãy phân loại những thay đổi thường cần restart; những thay đổi có thể reload hoặc chỉ áp dụng ở session; và viết câu SQL kiểm tra `context` thực tế.

### Bài 3 — Phát hiện file lỗi

Một DBA sửa file include rồi `pg_reload_conf()` trả `true`, nhưng cấu hình không đổi. Hãy dùng `pg_file_settings` và `pg_settings` để phân biệt lỗi parse, entry bị override và pending restart.

### Bài 4 — Rollback ALTER SYSTEM đúng source

Ban đầu `postgresql.auto.conf` đã có `log_min_duration_statement = '2000ms'`. Sau thử nghiệm đổi thành `500ms`, muốn khôi phục đúng baseline. `ALTER SYSTEM RESET` có phải luôn đáp án đúng không? Vì sao?

### Bài 5 — Lỗi HBA sau reload

Ứng dụng dùng kết nối cũ vẫn hoạt động, nhưng worker mới không đăng nhập được. Hãy trình bày các bước kiểm tra ``pg_hba.conf``, nguồn IP, role, TLS, thứ tự rule và phép thử kết nối mới; mô tả rollback.

### Bài 6 — Thay role defaults

Bạn muốn đặt `statement_timeout = '10s'` cho `report_reader` trên `shopdb`, không ảnh hưởng role khác. Viết SQL đặt và reset. Kết nối đang mở trước thay đổi có chắc nhận giá trị mới không?

### Bài 7 — Work_mem và RAM

Một báo cáo cần sort nhiều dữ liệu; người quản trị đề xuất tăng `work_mem` toàn server từ 4MB lên 256MB. Nêu ba rủi ro và một kế hoạch thử phạm vi hẹp hơn.

### Bài 8 — Restart lỗi

Sau khi thay `max_connections`, PostgreSQL không khởi động được và không thể chạy `psql`. Bạn sẽ rollback như thế nào mà không dựa vào `ALTER SYSTEM` qua SQL?

### Bài 9 — Đọc pg_settings

Giải thích ý nghĩa của:

~~~text
name = max_connections
setting = 100
context = postmaster
pending_restart = true
~~~

Có thể kết luận server hiện đang cho phép 250 kết nối vì trong file đã đổi sang 250 không?

### Bài 10 — Viết change record

Soạn một bản ghi thay đổi tối thiểu cho việc điều chỉnh `log_min_duration_statement`, gồm mục tiêu, baseline, scope, cách áp dụng, cách xác minh, ngưỡng rollback và người chịu trách nhiệm.

### Bài 11 — Kiểm tra thay HBA

Viết SQL đọc các dòng HBA có lỗi. Vì sao truy vấn trả không có lỗi nhưng ứng dụng vẫn có thể không đăng nhập?

### Bài 12 — Đo tác động thật

Một tham số `statement_timeout` mới hiển thị đúng khi DBA chạy `SHOW`. Nhưng API vẫn timeout ở 3 giây. Liệt kê những tầng timeout và bằng chứng cần kiểm tra để phân biệt PostgreSQL, connection pool và HTTP gateway.

## 28. Gợi ý lời giải

### Bài 1

Kiểm tra file chính/includes, `postgresql.auto.conf`, role/database defaults, startup options và session `SET`. SQL:

~~~sql
SELECT
    name, setting, unit, source,
    sourcefile, sourceline, context
FROM pg_settings
WHERE name = 'work_mem';
~~~

Cần chạy trong **session/role thật** của báo cáo để biết nguồn hiệu lực.

### Bài 2

`max_connections`, `shared_buffers`, `listen_addresses` thường là tham số cần restart. `log_min_duration_statement` có thể áp dụng bằng reload hoặc session theo quyền/context. `statement_timeout` có thể cấu hình ở session và có các nguồn mặc định khác.

~~~sql
SELECT name, context, setting, unit, pending_restart
FROM pg_settings
WHERE name IN (
  'max_connections',
  'shared_buffers',
  'log_min_duration_statement',
  'statement_timeout',
  'listen_addresses'
)
ORDER BY name;
~~~

Luôn dùng kết quả thực tế của server, không chỉ bảng ghi nhớ.

### Bài 3

~~~sql
SELECT sourcefile, sourceline, name, setting, applied, error
FROM pg_file_settings
WHERE error IS NOT NULL OR name = 'work_mem'
ORDER BY seqno;

SELECT name, setting, source, pending_restart
FROM pg_settings
WHERE name = 'work_mem';
~~~

Đọc `error` để phát hiện lỗi; `applied=false` có thể do override; `pending_restart` cho biết thay đổi cần restart. Kiểm tra log để xác định reload có vấn đề khác.

### Bài 4

Không luôn đúng. `RESET` xóa override qua ALTER SYSTEM, có thể làm runtime rơi về một giá trị khác từ file chính. Nếu baseline đã có auto.conf override `2000ms`, có thể cần:

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '2000ms';
SELECT pg_reload_conf();
~~~

Sau đó xác minh giá trị và nguồn hiệu lực.

### Bài 5

Kiểm tra `SHOW hba_file`, nội dung file backup/current, `pg_hba_file_rules`, log, địa chỉ thực tế qua NAT/proxy, database/user và TLS. Giữ đường vào dự phòng, phục hồi file cũ, reload và thử **kết nối mới** từ ứng dụng và DBA. Không mở `trust` hay CIDR toàn mạng để sửa nhanh.

### Bài 6

~~~sql
ALTER ROLE report_reader IN DATABASE shopdb
SET statement_timeout = '10s';

-- Rollback:
ALTER ROLE report_reader IN DATABASE shopdb
RESET statement_timeout;
~~~

Defaults cấp role/database thường áp dụng cho **session mới**. Pool phải tái tạo connection phù hợp và kiểm tra bằng đúng role/database.

### Bài 7

Rủi ro: nhiều sort/hash nodes đồng thời làm RAM tăng, có thể swap/OOM; tăng áp lực lên cache/OS; query khác hoặc instance bị ảnh hưởng dù chỉ một report cần thêm memory. Trước tiên thử `SET LOCAL work_mem` với một SELECT ở staging, đo `EXPLAIN ANALYZE`, temp I/O và tải đồng thời; cân nhắc role override nếu chỉ reporting cần.

### Bài 8

SQL không khả dụng khi server không khởi động. Phục hồi giá trị/file/parameter group **qua kênh vận hành thực tế** (host, operator, cloud provider), dựa trên bản cấu hình biết tốt; tránh xóa `postgresql.auto.conf` mù quáng. Xem log nguyên nhân, khởi động lại theo runbook rồi xác minh health và ứng dụng.

### Bài 9

`context=postmaster` cần restart. `pending_restart=true` cho biết có thay đổi cần restart chưa được áp dụng. `setting=100` phản ánh giá trị hiệu lực mà session/instance đang sử dụng theo view; không thể kết luận `250` đã có hiệu lực chỉ vì file chứa giá trị mới.

### Bài 10

Change record cần có: người yêu cầu, lý do, instance/role, baseline và source, giá trị mới, phép đo trước/sau, loại reload, thời điểm, dự kiến log volume, điều kiện rollback, cách khôi phục override hoặc file chính, người chịu trách nhiệm và xác nhận sau thay đổi.

### Bài 11

~~~sql
SELECT line_number, type, database, user_name, address, auth_method, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL
ORDER BY line_number;
~~~

Không có parser error không chứng minh một rule match kết nối mới; còn IP nguồn, thứ tự, database, user, TLS, mật khẩu/chứng chỉ, listener, firewall và việc reload.

### Bài 12

Kiểm tra `statement_timeout`, `lock_timeout`, driver socket/read timeout, timeout mượn connection pool, HTTP gateway và deadline request. Thu log SQLSTATE/error chính xác, thời gian acquire/execute ở pool, thời gian server thực thi, HTTP status và tracing từng bước.

## 29. Kết luận

Cấu hình PostgreSQL có nhiều tầng và phạm vi. **Thấy một giá trị trong file chưa đủ để khẳng định giá trị đang được áp dụng**, và **reload thành công ở mức gửi tín hiệu chưa đủ chứng minh cấu hình hợp lệ**. Các công cụ trọng tâm để điều tra gồm `pg_settings` (giá trị và nguồn hiệu lực), `pg_file_settings` (các entry trong file và lỗi), `pg_hba_file_rules`/`pg_ident_file_mappings` (quy tắc xác thực) cùng log và các phép kiểm tra kết nối thật.

Mỗi tham số phải được phân loại theo `context`: dùng `SET LOCAL` cho thử nghiệm ngắn, `ALTER ROLE`/`ALTER DATABASE` cho phạm vi session mới, reload cho những thay đổi có thể nạp lại và **restart có kiểm soát** cho tham số `postmaster`. Thay đổi càng rộng càng cần thử trước, giám sát và điều kiện dừng rõ ràng.

Một phương án hoàn tác đúng nghĩa phải biết **giá trị trước đó, nguồn đã ghi giá trị ấy, cách đưa nguồn về trạng thái cũ và cách xác minh kết quả trên đúng session/instance**. Khi chuẩn bị cả rollback trước khi thay, PostgreSQL có thể được điều chỉnh một cách có hệ thống, có bằng chứng, giảm rủi ro mất kết nối, gián đoạn hoặc làm chậm workload sản xuất.
