# Khởi động, dừng, khởi động lại và kiểm tra bằng pg_ctl

Trong PostgreSQL, tiện ích **`pg_ctl`** dùng để quản lý vòng đời của một **database cluster**: khởi động máy chủ, dừng có kiểm soát, khởi động lại, nạp lại cấu hình và xem trạng thái. Những thao tác này khác với truy vấn SQL thông thường: `pg_ctl` chạy trên hệ điều hành của máy chủ, cần quyền truy cập thư mục dữ liệu và có thể ảnh hưởng đến mọi database nằm trong cùng PostgreSQL instance.

Bài học hướng dẫn thao tác `start`, `stop`, `restart` và `status`, phân biệt chế độ dừng `smart`, `fast`, `immediate`, sử dụng các tùy chọn `-D`, `-l`, `-w`, `-t`, kiểm tra tiếp bằng `pg_isready` và `psql`, cũng như xử lý lỗi khởi động thường gặp.

> **An toàn:** Chỉ thực hành dừng và khởi động lại trên PostgreSQL cluster thử nghiệm mà bạn được phép quản lý. Trong production, cần xác nhận đúng máy, đúng thư mục dữ liệu, lịch bảo trì và hệ thống quản lý dịch vụ. Không dùng `pg_ctl` để tranh quyền điều khiển với systemd, Kubernetes hay trình quản lý high availability.

## 1. Cấu trúc cần hiểu trước khi chạy pg_ctl

Một PostgreSQL **cluster** là tập hợp database do cùng một PostgreSQL server quản lý, dùng chung một **data directory**. Một cluster có thể chứa `postgres`, `appdb`, `reportdb` và nhiều database khác. Lệnh `pg_ctl stop` dừng **cả server**, không chỉ một database được chọn.

| Thành phần | Vai trò |
|---|---|
| `postgres` | Chương trình server xử lý kết nối, truy vấn và các tiến trình nền. |
| `pg_ctl` | Tiện ích điều khiển tiến trình server, dựa vào thư mục dữ liệu được chỉ định. |
| `PGDATA` | Biến môi trường trỏ tới thư mục dữ liệu của cluster. |
| `-D directory` | Cách chỉ định data directory trực tiếp cho lệnh `pg_ctl`. |
| `postmaster.pid` | File trạng thái/khóa của server trong data directory khi PostgreSQL đang chạy; không được xóa tùy tiện. |
| `postgresql.conf` và cấu hình liên quan | Điều khiển cổng, bộ nhớ, logging và các tham số server. |
| `pg_wal/` | Nơi chứa các WAL segment liên quan tới tính bền vững và khôi phục giao dịch. |

Sơ đồ khái niệm:

```text
Máy thử nghiệm
├── PostgreSQL binaries
│   ├── postgres
│   ├── pg_ctl
│   ├── pg_isready
│   └── psql
│
└── /srv/postgresql/labdata    <-- PGDATA
    ├── PG_VERSION
    ├── base/
    ├── global/
    ├── pg_wal/
    ├── postgresql.conf (có thể nằm nơi khác tùy cách cài)
    └── postmaster.pid (khi server đang chạy)
```

**`PGDATA` không phải tên database SQL.** Khi dùng `pg_ctl -D /srv/postgresql/labdata status`, bạn đang kiểm tra server gắn với thư mục dữ liệu đó, chứ không phải truy vấn một database tên `labdata`.

### Cluster phải được khởi tạo trước

`pg_ctl start` khởi động **cluster đã có**. Nó không tạo dữ liệu lần đầu; việc tạo cluster mới thuộc công cụ `initdb` và quy trình cài đặt riêng. **Không chạy lại `initdb` trên thư mục dữ liệu hiện hữu để sửa lỗi không start được.** Làm như vậy có thể dẫn tới khởi tạo nhầm một cluster rỗng hoặc làm gián đoạn quy trình phục hồi dữ liệu.

## 2. Chuẩn bị quyền, phiên bản và đường dẫn

Trên Linux/macOS, kiểm tra công cụ:

```bash
command -v pg_ctl
pg_ctl --version
pg_config --bindir
```

`pg_config --bindir` giúp tìm thư mục chứa binaries khi `pg_ctl` chưa có trong `PATH`. Ví dụ bản cài từ package có thể đặt binary ở thư mục theo phiên bản như `/usr/lib/postgresql/16/bin/`. Đường dẫn thực tế phụ thuộc cách cài đặt.

PostgreSQL server thường chạy dưới **tài khoản hệ điều hành** `postgres` hoặc tài khoản chuyên dụng khác sở hữu thư mục dữ liệu. **Không chạy server PostgreSQL trực tiếp bằng root.** Role SQL tên `postgres` và người dùng hệ điều hành `postgres` là hai loại danh tính khác nhau.

Trong lab, giả định cluster đã khởi tạo tại:

```bash
export PGDATA=/srv/postgresql/labdata
export PGLOG=/srv/postgresql/logs/lab-postgres.log
```

Đây là đường dẫn **minh họa**, không phải đường dẫn bắt buộc trên mọi máy. Thư mục cha của file log phải tồn tại và người chạy PostgreSQL phải có quyền ghi. Bài học tiếp tục dùng các biến này để dễ đọc lệnh.

### Cần biết hệ thống nào quản lý PostgreSQL

Nếu PostgreSQL cài qua service manager, lệnh vận hành đúng có thể là:

```bash
# Ví dụ kiểm tra service trên một hệ thống Linux dùng systemd.
systemctl status postgresql
```

Tên unit có thể là `postgresql@16-main`, `postgresql-16` hoặc tên khác. Debian/Ubuntu còn có `pg_ctlcluster` cho cluster được quản lý bởi package. Container/Kubernetes và nền tảng HA có cơ chế riêng.

**Không tự khởi động bằng `pg_ctl` trên data directory đang do một service manager quản lý.** Supervisor có thể tự bật lại tiến trình vừa bị dừng, hoặc thấy trạng thái không nhất quán. Phần lệnh trực tiếp tiếp theo dành cho **cluster thủ công trong lab**.

## 3. Cú pháp và các tùy chọn quan trọng

Các thao tác cơ bản:

```bash
pg_ctl -D "$PGDATA" status
pg_ctl -D "$PGDATA" -l "$PGLOG" -w -t 120 start
pg_ctl -D "$PGDATA" -m fast -w -t 120 stop
pg_ctl -D "$PGDATA" -m fast -w -t 120 restart
pg_ctl -D "$PGDATA" reload
```

| Tùy chọn | Tác dụng |
|---|---|
| `-D directory` | Xác định data directory. Nếu không truyền, `pg_ctl` có thể dùng `PGDATA` từ môi trường. |
| `-l filename` | Chuyển output/log của server khởi động vào file chỉ định theo cách `pg_ctl` quản lý. |
| `-w` | Yêu cầu công cụ chờ hoàn tất khi start/stop/restart. |
| `-W` | Không chờ hoàn tất; caller phải có cơ chế xác nhận riêng. |
| `-t seconds` | Giới hạn thời gian chờ, ví dụ 120 giây. |
| `-m smart/fast/immediate` | Chọn cách dừng cho `stop`/`restart`. |
| `-o options` | Truyền tùy chọn khởi động cho tiến trình `postgres`. |
| `-s` | Giảm bớt output của tiện ích. |

Trên PostgreSQL hiện đại, `pg_ctl` thường chờ thao tác hoàn tất theo mặc định, nhưng dùng `-w` tường minh giúp runbook rõ ràng. Một lần `-t` hết thời gian chờ **không đủ để kết luận** server đã dừng hoặc chắc chắn khởi động thất bại; cần kiểm tra trạng thái thực tế và log.

### Vì sao nên viết -D tường minh?

Giả sử máy có hai cluster:

```text
/srv/postgresql/main   -> cổng 5432
/srv/postgresql/lab    -> cổng 55432
```

Nếu `PGDATA` còn sót từ một shell khác, `pg_ctl status` không có `-D` có thể nhắm tới cluster không mong muốn. Trong script vận hành, dùng `-D "/đường/dẫn/đúng"` và xác nhận data directory trước thao tác dừng hoặc restart.

## 4. Kiểm tra bằng pg_ctl status

Lệnh không thay đổi dữ liệu:

```bash
pg_ctl -D "$PGDATA" status
```

Khi server chạy, output có thể có dạng:

```text
pg_ctl: server is running (PID: 12345)
/path/to/postgres "-D" "/srv/postgresql/labdata" ...
```

Khi server không chạy:

```text
pg_ctl: no server running
```

PID và thông điệp ở đây chỉ là ví dụ. Công cụ có **exit status** để chương trình gọi biết kết quả, không chỉ có chuỗi hiển thị.

### status kiểm tra đến mức nào?

`pg_ctl status` giúp xác định trạng thái tiến trình cho **đúng PGDATA**. Nhưng “server is running” không bảo đảm:

1. Server đã sẵn sàng nhận connection mới.
2. Tài khoản ứng dụng có thể đăng nhập.
3. Database mục tiêu tồn tại và schema đầy đủ.
4. Một truy vấn nghiệp vụ có thể chạy thành công.
5. Bạn đang dùng đúng host/port nếu có nhiều PostgreSQL instance.

Để xác nhận khả năng sử dụng thực tế, kết hợp **`pg_ctl status` → `pg_isready` → `psql`** ở các bước sau.

### Không tự xóa postmaster.pid khi thấy trạng thái bất thường

File `postmaster.pid` giúp server quản lý tình trạng cluster và tránh hai tiến trình cùng sử dụng data directory. Nếu start báo có server đang chạy dù bạn không thấy cổng mở, hãy kiểm tra PID, log, các service manager và tiến trình thực tế.

**Không xóa `postmaster.pid` để “ép PostgreSQL khởi động” khi chưa xác minh chắc chắn cluster không còn tiến trình sử dụng dữ liệu.** Xóa sai file trạng thái rồi start một server thứ hai trên cùng dữ liệu có thể gây hư hỏng nghiêm trọng.

## 5. Khởi động bằng pg_ctl start

Sau khi xác nhận server đang dừng và thư mục dữ liệu hợp lệ:

```bash
pg_ctl -D "$PGDATA" -l "$PGLOG" -w -t 120 start
```

Giải thích:

- `-D "$PGDATA"`: chọn cluster cần khởi động.
- `-l "$PGLOG"`: lưu output/log startup vào vị trí có quyền ghi.
- `-w`: chờ server đạt điều kiện khởi động thành công.
- `-t 120`: đặt giới hạn chờ là 120 giây cho công cụ.

Sơ đồ:

```text
pg_ctl start
      |
      v
Xác định data directory và cấu hình
      |
      v
Chạy tiến trình postgres
      |
      v
Mở file dữ liệu, listener và tiến trình nền
      |
      v
Thực hiện recovery/WAL replay nếu cần
      |
      v
Server sẵn sàng cho kết nối
      |
      v
pg_ctl -w xác nhận hoặc báo lỗi/chờ quá hạn
```

Nếu server đã chạy với cùng PGDATA, **không gọi start lần nữa**. PostgreSQL không được vận hành với hai tiến trình server dùng chung thư mục dữ liệu.

### Lưu ý về file log

`-l` giúp chuyển output của server tới file chỉ định khi start. Nhưng một bản cài PostgreSQL có thể gửi log qua **logging collector, systemd journal hoặc container logs**, nên file này không nhất thiết chứa toàn bộ log về sau.

Nếu start thất bại:

```bash
pg_ctl -D "$PGDATA" status
tail -n 100 "$PGLOG"
```

Đồng thời kiểm tra nơi PostgreSQL thực tế cấu hình xuất log. Không gửi log chứa thông tin cá nhân hoặc SQL nhạy cảm vào nơi công khai.

### Khi lệnh khởi động quá thời gian chờ

Nếu `-t 120` hết thời gian, server có thể vẫn đang **replay WAL sau một shutdown không sạch**. Hãy kiểm tra `status`, `pg_isready`, log và tài nguyên thay vì tự động chạy lại start hoặc xóa file trạng thái.

Timeout của `pg_ctl` là giới hạn chờ của **lệnh điều khiển**, không phải bằng chứng rằng tiến trình PostgreSQL đã kết thúc.

## 6. Kiểm tra sẵn sàng bằng pg_isready

Khi `pg_ctl` đã start, kiểm tra endpoint:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Ví dụ:

```text
127.0.0.1:5432 - accepting connections
```

Các exit code phổ biến:

| Exit code | Ý nghĩa | Hướng xử lý |
|---:|---|---|
| `0` | Server đang chấp nhận kết nối. | Thử đăng nhập với `psql`. |
| `1` | Server phản hồi nhưng đang từ chối kết nối. | Kiểm tra startup/recovery/log. |
| `2` | Không có phản hồi. | Kiểm tra host, port, listener, firewall, server. |
| `3` | Tham số không hợp lệ hoặc lỗi cách dùng công cụ. | Sửa lệnh kiểm tra. |

**`pg_isready` không xác minh đầy đủ quyền truy cập của ứng dụng.** Nó kiểm tra server có sẵn sàng nhận connection, kể cả trong những tình huống role/database bạn định dùng không hợp lệ.

Vì vậy, bước xác minh tiếp theo là **đăng nhập thật và chạy SQL**:

```bash
psql \
  -h 127.0.0.1 \
  -p 5432 \
  -U app_user \
  -d appdb \
  -v ON_ERROR_STOP=1 \
  -c "SELECT current_database(), current_user, pg_postmaster_start_time();"
```

`app_user` và `appdb` là tên minh họa. Hãy dùng tài khoản/database thử nghiệm có thật. Không đưa mật khẩu vào command line hay log; dùng prompt hoặc cơ chế secret phù hợp.

Hàm `pg_postmaster_start_time()` trả thời điểm server bắt đầu chạy, giúp kiểm tra sau một lần restart. Với hệ thống có nhiều cluster, dùng đúng host/port và tài khoản của cluster cần kiểm tra.

## 7. Dừng PostgreSQL: smart, fast và immediate

`pg_ctl stop` có ba **shutdown mode**. Lựa chọn mode ảnh hưởng đến client và transaction.

### 7.1. smart — chờ client tự kết thúc

```bash
pg_ctl -D "$PGDATA" -m smart -w -t 120 stop
```

Server ngừng tiếp nhận kết nối mới theo tiến trình shutdown và **chờ những client hiện có tự ngắt**. Những session còn mở lâu, kể cả connection pool hoặc session idle, có thể khiến lệnh dừng không hoàn tất trong thời gian mong đợi.

Phù hợp khi đã có kế hoạch **drain traffic** và muốn các client hoàn thành công việc bình thường. Nếu quá thời gian, xác định session còn kết nối trước khi quyết định chuyển sang mode khác.

### 7.2. fast — hủy công việc đang chạy và dừng sạch

```bash
pg_ctl -D "$PGDATA" -m fast -w -t 120 stop
```

Server không chờ các client tự thoát; các connection được kết thúc và transaction chưa hoàn tất bị **rollback**. PostgreSQL thực hiện **shutdown sạch**.

Đối với các phiên bản PostgreSQL hiện đại, `fast` là chế độ mặc định của `pg_ctl stop` nếu không truyền `-m`. Viết tường minh giúp người vận hành nhận biết rằng request đang chạy có thể bị ngắt.

### 7.3. immediate — chỉ dành cho tình huống khẩn cấp

```bash
# Chỉ là minh họa. Không chạy khi chưa có lý do và phê duyệt.
pg_ctl -D "$PGDATA" -m immediate stop
```

Server dừng **ngay lập tức**, không theo quy trình shutdown sạch thông thường. Lần start tiếp theo cần **crash recovery** dựa trên WAL. Đây không phải cách dừng chuẩn để tiết kiệm vài giây trong bảo trì.

WAL bảo vệ tính nhất quán và độ bền theo cấu hình PostgreSQL, nhưng dừng `immediate` có thể khiến startup lần sau mất nhiều thời gian khôi phục; nó không thay thế backup và không phải cách xử lý an toàn cho mọi sự cố.

### Bảng so sánh

| Mode | Connection hiện có | Transaction đang hoạt động | Lần khởi động sau |
|---|---|---|---|
| `smart` | Chờ client tự rời. | Có cơ hội hoàn tất qua kết nối trước khi dừng. | Sau shutdown sạch. |
| `fast` | Ngắt client; không chờ họ tự ngắt. | Hủy công việc và rollback phần chưa hoàn tất. | Sau shutdown sạch. |
| `immediate` | Kết thúc tiến trình tức thì. | Không đi theo đường hoàn tác/shutdown sạch thông thường. | Cần crash recovery bằng WAL. |

**Nguyên tắc:** Với bảo trì thông thường cần giới hạn thời gian, `fast` thường hợp lý hơn `immediate`. Nếu cần chờ các kết nối hoàn thành một cách tự nhiên, `smart` phù hợp nhưng có thể đợi rất lâu.

## 8. Khởi động lại bằng pg_ctl restart

`restart` kết hợp dừng và khởi động lại cluster:

```bash
pg_ctl -D "$PGDATA" -m fast -w -t 120 restart
```

Tác động:

1. Những kết nối tới server đang mở bị mất trong quá trình shutdown.
2. Transaction chưa hoàn tất tại thời điểm dừng `fast` không tiếp tục sau restart.
3. PostgreSQL đọc lại các cấu hình startup phù hợp; các tham số cần restart có thể nhận giá trị mới.
4. Ứng dụng cần kết nối lại, tái tạo physical connections trong pool và xử lý request lỗi theo chính sách.

**`pg_ctl restart` không phải thao tác không gián đoạn.** Muốn duy trì availability trong hệ thống production cần thiết kế replica, failover hoặc cách điều phối tải phù hợp; gọi `restart` trên một node độc lập sẽ tạo một khoảng ngừng phục vụ.

### Kiểm tra server thực sự đã restart

Trước và sau khi restart trong lab:

```sql
SELECT pg_postmaster_start_time() AS server_started_at;
```

Thời điểm thay đổi là một tín hiệu PostgreSQL server đã được khởi chạy lại. Sau đó kiểm tra tiếp tham số dự định thay đổi và khả năng ứng dụng kết nối.

### Ví dụ tham số cần restart

Một số thiết lập như `shared_buffers`, `max_connections` có ngữ cảnh `postmaster` và cần restart sau thay đổi cấu hình:

```conf
# Chỉ là ví dụ trong postgresql.conf của cluster lab.
shared_buffers = '256MB'
max_connections = 150
```

Sau khi sửa đúng file cấu hình, thực hiện restart bằng **công cụ quản lý vòng đời chính thức** của môi trường và kiểm tra:

```sql
SHOW shared_buffers;
SHOW max_connections;
```

Không nên khẳng định cấu hình đã áp dụng chỉ vì lệnh restart kết thúc mà chưa kiểm tra giá trị runtime.

## 9. Khi nào chỉ cần pg_ctl reload?

`reload` yêu cầu PostgreSQL nạp lại các file cấu hình:

```bash
pg_ctl -D "$PGDATA" reload
```

Lệnh này **không dừng toàn bộ server** và thông thường không ngắt mọi client. Tuy nhiên, chỉ những tham số cho phép nạp lại theo ngữ cảnh tương ứng mới có hiệu lực khi reload.

Có thể gọi reload bằng SQL khi tài khoản có quyền:

```sql
SELECT pg_reload_conf();
```

Hàm trả true khi việc gửi tín hiệu reload thành công; **không đồng nghĩa tất cả thay đổi đều hợp lệ và đã áp dụng**. Cần kiểm tra log, `pg_settings` và khi có quyền, `pg_file_settings`.

### Xem tham số có đòi hỏi restart không

```sql
SELECT
    name,
    setting,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'max_connections',
    'log_min_duration_statement',
    'work_mem'
)
ORDER BY name;
```

`context` cho biết loại ngữ cảnh của tham số, còn `pending_restart` phản ánh có thay đổi được ghi nhận mà cần restart mới áp dụng. Tham số có thể đổi trong session hoặc bởi superuser có hành vi khác với tham số khởi động.

| Thao tác | Có làm gián đoạn kết nối hiện tại? | Có áp dụng tham số yêu cầu restart? |
|---|---|---|
| `pg_ctl reload` | Thông thường không. | Không. |
| `SELECT pg_reload_conf()` | Thông thường không. | Không. |
| `pg_ctl restart` | Có. | Có thể, khi cấu hình hợp lệ và server lên thành công. |

Không restart chỉ vì vừa sửa một file: trước hết xác định tham số nào có thể reload và tham số nào thực sự đòi hỏi restart.

## 10. Đọc log và giải thích các lỗi start thường gặp

Khi start thất bại, đọc thông báo và log trước khi sửa bất cứ file dữ liệu nào.

| Triệu chứng | Nguyên nhân khả dĩ | Cách tiếp cận |
|---|---|---|
| “permission denied” với data directory. | Sai tài khoản OS, owner hoặc quyền. | Kiểm tra account/permissions; không chạy server bằng root hoặc mở toàn quyền thư mục dữ liệu. |
| Không tìm thấy `PG_VERSION`. | Sai `-D`, đường dẫn rỗng hoặc chưa `initdb`. | Xác nhận cluster gốc; không initdb đè dữ liệu. |
| Cổng đã bị chiếm. | Instance khác đang listen trên cổng. | Xác định port/process; không dừng server khác mà chưa được phép. |
| Báo server đã chạy. | Cluster hiện đang hoạt động hoặc file trạng thái cần điều tra. | Kiểm tra `status`, PID, supervisor; không xóa `postmaster.pid` tùy tiện. |
| Data directory không đúng phiên bản server. | Dùng binary PostgreSQL major khác. | Kiểm tra `pg_ctl --version` và `PG_VERSION`; cần kế hoạch nâng cấp đúng. |
| Server đang recovery và chưa chấp nhận kết nối. | Replay WAL, khởi động sau shutdown không sạch. | Theo dõi log/trạng thái; không start trùng khi timeout. |
| “unrecognized configuration parameter” hoặc giá trị sai. | Sửa cấu hình không phù hợp. | Khôi phục/sửa thiết lập; kiểm tra log và nguồn config thực tế. |
| Không tìm thấy log trong file `-l`. | Logging collector hoặc service manager đưa log nơi khác. | Xem nguồn log thực tế (journal/container/log directory). |

### Kiểm tra cổng cho cluster thử nghiệm

Nếu cluster lab cần cổng `55432` và server chưa chạy:

```bash
pg_ctl -D "$PGDATA" \
  -l "$PGLOG" \
  -o "-p 55432" \
  -w -t 120 start

pg_isready -h 127.0.0.1 -p 55432
```

`-o` truyền tham số khởi động cho `postgres`. Với cấu hình cần ổn định qua nhiều restart, nên quản lý cổng trong nguồn cấu hình chính thức thay vì phụ thuộc vào một tham số dòng lệnh được nhập thủ công.

### Xác minh đường dẫn dữ liệu khi đã kết nối

Người dùng PostgreSQL có quyền phù hợp có thể chạy:

```sql
SHOW data_directory;
SELECT version(), pg_postmaster_start_time();
```

Đường dẫn data directory có thể bị hạn chế vì chứa thông tin nội bộ; tài khoản ứng dụng không nhất thiết có quyền đọc. Đây là thao tác hỗ trợ người vận hành xác nhận **cluster đích**, không phải một quyền cần cấp đại trà.

## 11. Thứ tự xác minh sau khi khởi động lại

Khi một lệnh `restart` báo thành công, vẫn cần kiểm tra nhiều tầng:

```text
pg_ctl status
    |
    v
Đúng PostgreSQL process/cluster đang chạy?
    |
    v
pg_isready -h ... -p ...
    |
    v
Endpoint có chấp nhận kết nối?
    |
    v
psql -U ... -d ... -c "SELECT 1"
    |
    v
Tài khoản ứng dụng có đăng nhập/chạy SQL?
    |
    v
Kiểm tra schema, giao dịch thử trong lab, API
    |
    v
Dịch vụ hoạt động theo tiêu chí nghiệp vụ?
```

Một server có PID chưa có nghĩa database mục tiêu đúng, role đã có quyền, extension tải được hoặc ứng dụng phục vụ bình thường.

### PostgreSQL và connection pool Java

Trong Spring Boot, HikariCP hoặc các pool tương tự tái sử dụng **physical connections**. Khi PostgreSQL server restart, những kết nối mở trước đó không thể tiếp tục được dùng như khi chưa gián đoạn. Pool cần tạo connection mới; một số request đúng lúc restart có thể gặp `SQLException`.

Với thao tác đọc có thể thử lại theo chính sách, nhưng với thao tác ghi cần cẩn thận: **lỗi mạng khi đang nhận kết quả không luôn chứng minh transaction chưa commit**. Nếu nghiệp vụ có thể tạo tác động kép, phải có idempotency hoặc cách xác minh giao dịch trước khi retry.

## 12. Phân biệt pg_ctl với công cụ quản lý khác

| Công cụ | Phạm vi | Dùng khi |
|---|---|---|
| `pg_ctl` | Tiến trình PostgreSQL và data directory. | Cluster thủ công hoặc bước runbook đã phê duyệt. |
| `systemctl` | Vòng đời service trong systemd. | PostgreSQL do Linux service manager quản lý. |
| `pg_ctlcluster` | Cluster PostgreSQL do Debian/Ubuntu package quản lý, nếu có. | Máy dùng công cụ đóng gói đó. |
| `pg_isready` | Kiểm tra endpoint PostgreSQL. | Xác định server đang chấp nhận connection. |
| `psql` | Kết nối và thực thi SQL. | Xác thực role/database, kiểm tra truy vấn thật. |

Trong container/Kubernetes, trình điều phối có thể tự restart workload khi thấy tiến trình kết thúc. Với giải pháp HA, một cluster manager có thể quản lý leader, replica và failover. **Không kết hợp các nguồn điều khiển khác nhau một cách tùy tiện.**

Trên Windows, `pg_ctl.exe` cũng có các thao tác cơ bản tương đương. Ví dụ (đường dẫn minh họa):

```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\PostgreSQL\labdata" status
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\PostgreSQL\labdata" -l "C:\PostgreSQL\logs\startup.log" -w -t 120 start
& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\PostgreSQL\labdata" -m fast -w -t 120 stop
```

Nếu cluster đã được đăng ký và quản lý dưới dạng Windows Service, dùng công cụ dịch vụ tương ứng theo quy trình quản trị thay vì tự chạy thêm một tiến trình từ cùng data directory.

## 13. Runbook tối thiểu cho một cluster thử nghiệm

### Trước khi thao tác

1. Xác nhận máy, phiên bản PostgreSQL, `PGDATA`, port và người dùng OS.
2. Kiểm tra ai đang quản lý vòng đời server: thủ công hay supervisor.
3. Kiểm tra `pg_ctl status`, `pg_isready`, nơi ghi log.
4. Với thao tác stop/restart, đảm bảo có quyền và thông báo việc gián đoạn.
5. Xác định chính sách cho các transaction đang thực thi và kết nối Java.

### Khởi động

```bash
pg_ctl -D "$PGDATA" status
# Chỉ khi đã xác nhận cluster dừng:
pg_ctl -D "$PGDATA" -l "$PGLOG" -w -t 120 start
pg_ctl -D "$PGDATA" status
pg_isready -h 127.0.0.1 -p 5432
```

Tiếp theo phải đăng nhập với `psql` và chạy smoke test tương ứng.

### Dừng

```bash
# Cần chuẩn bị cho việc ngắt kết nối/rollback giao dịch chưa xong.
pg_ctl -D "$PGDATA" -m fast -w -t 120 stop
pg_ctl -D "$PGDATA" status
```

Sau khi stop, việc `status` báo không có server chạy là kết quả mong đợi. Nếu lệnh stop hết thời gian chờ, cần kiểm tra tiến trình và log trước khi thực hiện thêm thao tác.

### Khởi động lại

```bash
# Chỉ dùng nếu server đang chạy và có kế hoạch gián đoạn.
pg_ctl -D "$PGDATA" -m fast -w -t 120 restart
pg_ctl -D "$PGDATA" status
pg_isready -h 127.0.0.1 -p 5432
```

Nếu server đã dừng, dùng `start`; không dựa vào `restart` như cách chữa mọi trạng thái cluster. Sau đó truy vấn thời điểm server start và các cấu hình đã thay đổi.

### Ghi nhận bằng chứng vận hành

Một báo cáo ngắn nên có: tên cluster, đường dẫn dữ liệu, phiên bản, công cụ điều khiển, người thực thi, mốc bắt đầu/kết thúc, shutdown mode, kết quả lệnh, log lỗi nếu có, xác nhận `pg_isready` và kết quả smoke test ứng dụng. Trong production, thêm thông tin phê duyệt, ảnh hưởng khách hàng và kế hoạch hoàn tác.

## 14. Bài tập thực hành

### Bài 1 — Viết đúng lệnh và xác định cluster

Máy có hai cluster: `/srv/postgresql/a` dùng port `5432` và `/srv/postgresql/b` dùng port `55432`. Viết hai lệnh `pg_ctl status` riêng biệt và hai lệnh `pg_isready` cho đúng cổng. Giải thích vì sao `pg_isready -p 5432` không xác nhận trạng thái cluster B.

### Bài 2 — Chọn chế độ stop

Chọn một trong `smart`, `fast`, `immediate` cho từng tình huống:

1. Muốn chờ các session tự đóng sau khi đã drain traffic.
2. Phải dừng trong cửa sổ bảo trì và chấp nhận rollback transaction chưa hoàn tất.
3. Sự cố khẩn cấp đã được phê duyệt dừng ngay.

Nêu khác biệt về connection và recovery ở lần start sau.

### Bài 3 — Phân tích kết quả status

`pg_ctl status` báo server đang chạy nhưng `pg_isready` báo `rejecting connections`. Hãy nêu ít nhất hai lý do có thể xảy ra và trình tự kiểm tra. Tại sao không nên chạy một lệnh start thứ hai ngay hoặc xóa `postmaster.pid`?

### Bài 4 — Khởi động có timeout

Viết câu lệnh start cho `/srv/postgresql/labdata`, ghi log `/srv/postgresql/logs/startup.log` và chờ tối đa 90 giây. Nếu quá 90 giây nhưng log cho thấy đang replay WAL, hãy mô tả bước tiếp theo an toàn.

### Bài 5 — Reload hay restart

Bạn sửa hai tham số `max_connections` và `log_min_duration_statement`. Hãy tìm cách xem `pg_settings.context` và `pending_restart`, giải thích tham số nào yêu cầu restart và cách xác minh thay đổi thực sự áp dụng.

### Bài 6 — Kiểm tra ứng dụng sau restart

Ứng dụng Java có HikariCP đang kết nối PostgreSQL. Hãy lập chuỗi kiểm tra từ `status` đến `pg_isready`, `psql` và API, đồng thời mô tả cách xử lý connection cũ bị mất và nguy cơ retry ghi dữ liệu không có idempotency.

### Bài 7 — Khi PostgreSQL có service manager

Một admin chạy `pg_ctl stop` trên PostgreSQL do systemd quản lý, nhưng server tự bật lại. Hãy giải thích cơ chế có thể gây hiện tượng đó và nêu vì sao không nên điều khiển cùng cluster bằng cả `pg_ctl` thủ công và supervisor.

## Kết luận

**`pg_ctl` giúp kiểm soát vòng đời PostgreSQL theo đúng data directory**. `start` mở server, `stop` dừng theo chế độ lựa chọn, `restart` dừng rồi khởi động lại, còn `status` phản ánh tình trạng tiến trình gắn với cluster. `-D`/`PGDATA` giúp chọn chính xác mục tiêu; `-l` lưu log khởi động; `-w`/`-t` kiểm soát việc chờ; và `-m` quyết định tác động lên client khi dừng.

Hãy nhớ **`smart` chờ client, `fast` ngắt và rollback công việc chưa hoàn tất để dừng sạch, `immediate` cần crash recovery ở lần start sau**. Nếu chỉ đổi cấu hình không đòi restart, `reload` có thể tránh gián đoạn không cần thiết.

Trạng thái “server đang chạy” mới chỉ là bước đầu: luôn kiểm tra tiếp **`pg_isready`, đăng nhập `psql` và các thao tác nghiệp vụ** trước khi xác nhận dịch vụ đã sẵn sàng. Trên hạ tầng có systemd, Kubernetes hoặc bộ quản lý HA, tuân thủ **công cụ điều khiển chính thức** và quy trình vận hành của hệ thống.
