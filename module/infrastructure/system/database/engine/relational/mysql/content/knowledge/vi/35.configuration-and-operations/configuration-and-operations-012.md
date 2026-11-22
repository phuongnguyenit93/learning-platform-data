# Xác định cấu hình hiệu lực thay vì chỉ đọc một file cấu hình

Khi MySQL chạy với giá trị cấu hình không như mong đợi, mở một file `my.cnf` hoặc `my.ini` thường chưa đủ để tìm ra nguyên nhân. Một instance có thể đọc nhiều option file, nhận thêm tham số từ command line hoặc dịch vụ hệ điều hành, nạp thiết lập đã lưu trong `mysqld-auto.cnf`, rồi tiếp tục bị thay đổi khi chạy bằng `SET GLOBAL`. Mỗi kết nối còn có thể có giá trị `SESSION` riêng.

Vì vậy, cần phân biệt **giá trị được khai báo** với **giá trị đang có hiệu lực**. Giá trị hiệu lực là giá trị mà đúng instance MySQL đang dùng tại thời điểm kiểm tra, trong đúng phạm vi `GLOBAL` hoặc `SESSION`. Muốn giải thích vì sao có giá trị đó, hãy truy nguồn cấu hình thay vì chỉ đọc một file.

## 1. Những nơi có thể cung cấp cấu hình cho MySQL

Một biến hệ thống của MySQL có thể nhận giá trị từ nhiều nguồn:

| Nguồn | Vai trò |
|---|---|
| Giá trị mặc định được biên dịch | Giá trị nền nếu không có nguồn cấu hình khác ghi đè |
| Option file (`my.cnf`, `my.ini` và file được include) | Cấu hình lúc khởi động, thường trong các nhóm như `[mysqld]` hoặc `[server]` |
| Tham số command line của `mysqld` | Giá trị truyền trực tiếp khi tiến trình server khởi động |
| File `mysqld-auto.cnf` | Các thiết lập được lưu bằng `SET PERSIST` hoặc `SET PERSIST_ONLY` |
| `SET GLOBAL` | Thay đổi giá trị global động trong lúc server đang chạy |
| `SET SESSION` hoặc khởi tạo session từ ứng dụng | Giá trị riêng của kết nối hiện tại |

Các nguồn này có phạm vi và thời điểm áp dụng khác nhau. Một dòng cấu hình trong file chỉ là một đầu vào; nó không chứng minh rằng instance đang dùng giá trị đó.

## 2. Xác nhận đúng instance MySQL đang kiểm tra

Trước khi đọc cấu hình, xác định đúng server, port, socket hoặc named pipe và data directory. Một máy có thể chạy nhiều instance MySQL với file cấu hình và cổng khác nhau.

Chạy các truy vấn trên chính kết nối đến instance cần điều tra:

```sql
SELECT VERSION() AS mysql_version,
       @@version_comment AS version_comment,
       @@hostname AS server_host,
       @@port AS server_port,
       @@datadir AS data_directory,
       @@basedir AS base_directory,
       @@server_uuid AS server_uuid;
```

Ghi nhận các thông tin này cùng thời điểm kiểm tra. Nếu ứng dụng kết nối qua proxy, load balancer hoặc connection pool, hãy xác định backend thực sự đang phục vụ kết nối; truy vấn lặp lại có thể đến những instance khác nhau.

### Xác minh tiến trình dịch vụ trên hệ điều hành

Trên Windows, có thể xem đường dẫn executable và command line của tiến trình `mysqld`:

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'mysqld.exe'" |
    Select-Object ProcessId, ExecutablePath, CommandLine
```

Nếu cần biết dịch vụ nào khởi chạy tiến trình, xem cấu hình dịch vụ bằng tên dịch vụ thực tế:

```powershell
Get-CimInstance Win32_Service -Filter "Name = 'MySQL80'" |
    Select-Object Name, State, StartName, PathName
```

`PathName` có thể cho biết server đang dùng `--defaults-file` hoặc tham số khởi động riêng. `MySQL80` chỉ là ví dụ; thay bằng tên dịch vụ trên máy đang kiểm tra.

Trên Linux dùng systemd, kiểm tra unit đang chạy và nội dung cấu hình dịch vụ:

```bash
systemctl status mysqld
systemctl cat mysqld
ps -ef | grep '[m]ysqld'
```

Tên unit có thể là `mysql`, `mysqld` hoặc tên riêng do gói cài đặt và quản trị viên thiết lập. Đừng giả định mọi hệ điều hành đều dùng cùng một tên dịch vụ hoặc cùng đường dẫn option file.

## 3. Hiểu cách MySQL đọc option file

MySQL có thể đọc nhiều option file theo thứ tự phụ thuộc nền tảng, cách cài đặt và tham số khởi động. Các file có thể chứa nhiều nhóm cấu hình; server đọc những nhóm dành cho server, thường gồm `[mysqld]` và `[server]`. Chỉ đọc một file trong số đó có thể bỏ sót giá trị được đặt ở file khác hoặc trong nhóm khác.

Các chỉ thị trong option file cũng có thể đưa thêm file vào quá trình đọc:

```ini
[mysqld]
port = 3306
max_connections = 300

!include C:/mysql/conf/instance-extra.ini
!includedir C:/mysql/conf/conf.d
```

`!include` nạp một file cụ thể; `!includedir` nạp các option file trong thư mục được chỉ định. Khi điều tra, phải lần theo cả các file include và xác định file nào được instance thực sự đọc.

Một số tham số làm thay đổi cách tìm option file:

- `--defaults-file=...`: yêu cầu dùng file option được chỉ định thay cho chuỗi file mặc định.
- `--defaults-extra-file=...`: thêm một file option vào quá trình đọc.
- `--no-defaults`: không đọc option file thông thường.

Các tham số điều khiển việc đọc defaults có quy tắc vị trí riêng trên command line; đặc biệt `--defaults-file` cần xuất hiện ở vị trí mà MySQL yêu cầu, thường là ngay sau tên chương trình. Hãy lấy command line thực tế của tiến trình làm căn cứ, không chỉ suy luận từ vị trí file phổ biến.

Có thể yêu cầu chương trình hiển thị tùy chọn đọc từ option file:

```bash
mysqld --print-defaults
```

Hoặc dùng tiện ích `my_print_defaults` để đọc các nhóm liên quan:

```bash
my_print_defaults mysqld server
```

Nếu server được khởi chạy với `--defaults-file` hoặc `--defaults-extra-file`, hãy dùng cùng tùy chọn đó khi kiểm tra. Kết quả của các lệnh này cho biết option được đọc từ file; chúng không bao gồm đầy đủ giá trị runtime do `SET GLOBAL`, thiết lập session hay mọi giá trị đã persist.

`mysqld --verbose --help` có thể giúp xem danh sách tùy chọn và giá trị mặc định mà chương trình nhận biết. Đây không phải ảnh chụp giá trị runtime của một server đang chạy. Muốn biết giá trị hiện tại, truy vấn chính instance bằng SQL.

## 4. Xem giá trị global và session đang có hiệu lực

`SHOW GLOBAL VARIABLES` hiển thị giá trị global. `SHOW SESSION VARIABLES` hiển thị giá trị của kết nối hiện tại đối với các biến có phạm vi session:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';

SHOW SESSION VARIABLES LIKE 'time_zone';
SHOW SESSION VARIABLES LIKE 'sql_mode';
```

Có thể truy cập trực tiếp bằng system variable:

```sql
SELECT @@GLOBAL.max_connections AS global_max_connections,
       @@GLOBAL.innodb_buffer_pool_size AS global_buffer_pool_size,
       @@SESSION.time_zone AS session_time_zone,
       @@SESSION.sql_mode AS session_sql_mode;
```

Phạm vi cần được chỉ rõ:

- `@@GLOBAL.var_name` đọc giá trị global.
- `@@SESSION.var_name` đọc giá trị của session hiện tại nếu biến hỗ trợ session scope.
- `@@var_name` đọc giá trị session nếu biến có phạm vi session; nếu không, nó đọc giá trị global.
- `SHOW VARIABLES` mặc định hiển thị phạm vi session; dùng `SHOW GLOBAL VARIABLES` khi cần giá trị global.

Ví dụ, `max_connections` là biến global; `time_zone` có thể khác nhau giữa các kết nối. Một truy vấn `SHOW VARIABLES LIKE 'time_zone'` chạy từ tài khoản quản trị có thể trả về giá trị session của chính kết nối quản trị, không nhất thiết là giá trị mà connection pool của ứng dụng đang dùng.

### Vì sao GLOBAL và SESSION có thể khác nhau?

`SET GLOBAL` thay đổi giá trị global động. Với biến có cả hai phạm vi, giá trị global mới thường trở thành giá trị mặc định cho các session được tạo sau đó; session đã tồn tại giữ giá trị session hiện tại cho đến khi được thay đổi hoặc kết nối kết thúc.

`SET SESSION` chỉ thay đổi kết nối hiện tại:

```sql
SET SESSION time_zone = '+00:00';
SELECT @@GLOBAL.time_zone, @@SESSION.time_zone;
```

Vì vậy, khi ứng dụng dùng connection pool, hãy kiểm tra cả cấu hình khởi tạo connection và các lệnh `SET SESSION` được chạy khi mượn kết nối. Giá trị trong session có thể còn sót lại giữa hai lượt sử dụng nếu pool không đặt lại trạng thái.

## 5. Truy nguồn biến bằng Performance Schema

Đọc giá trị hiện tại cho biết MySQL đang dùng gì; metadata của Performance Schema giúp tìm hiểu giá trị global đến từ đâu.

Trong MySQL 8.0, `performance_schema.variables_info` cung cấp nguồn cấu hình và thông tin lần thay đổi gần nhất cho các global system variable:

```sql
SELECT VARIABLE_NAME,
       VARIABLE_SOURCE,
       VARIABLE_PATH,
       SET_TIME,
       SET_USER,
       SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME IN (
    'max_connections',
    'innodb_buffer_pool_size',
    'slow_query_log',
    'time_zone'
)
ORDER BY VARIABLE_NAME;
```

Các cột đáng chú ý:

- `VARIABLE_SOURCE`: nguồn mà MySQL ghi nhận cho giá trị global, chẳng hạn giá trị biên dịch, option file, command line, persisted setting hoặc thay đổi động.
- `VARIABLE_PATH`: đường dẫn option file khi nguồn là file và metadata có sẵn.
- `SET_TIME`: thời điểm biến được thay đổi động, nếu có.
- `SET_USER` và `SET_HOST`: tài khoản và host liên quan đến lần thay đổi động gần nhất, nếu có.

Giá trị nguồn cụ thể phụ thuộc phiên bản và cách thiết lập. Hãy đọc dữ liệu trả về thay vì tự giả định tên nguồn. Nếu `VARIABLE_SOURCE` cho thấy biến đến từ option file, `VARIABLE_PATH` giúp xác định file cần kiểm tra. Nếu biến được thay đổi động, thời gian và tài khoản giúp thu hẹp phạm vi điều tra.

`performance_schema.persisted_variables` liệt kê các biến được lưu bền vững:

```sql
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
ORDER BY VARIABLE_NAME;
```

Hai bảng này bổ sung cho `SHOW VARIABLES`: một bảng giúp truy nguồn giá trị global, bảng kia cho biết các thiết lập persisted. Chúng không thay thế việc kiểm tra session variable trên chính kết nối ứng dụng.

## 6. Hiểu `SET GLOBAL`, `SET PERSIST` và `SET PERSIST_ONLY`

Ba lệnh này có tác động khác nhau:

| Lệnh | Tác động runtime | Lưu qua lần khởi động lại |
|---|---|---|
| `SET GLOBAL` | Thay đổi giá trị global động nếu biến cho phép | Không |
| `SET PERSIST` | Thay đổi giá trị global động | Có, ghi vào `mysqld-auto.cnf` |
| `SET PERSIST_ONLY` | Không đổi giá trị đang chạy | Có, áp dụng khi server khởi động lại |

Ví dụ:

```sql
-- Chỉ đổi runtime
SET GLOBAL max_connections = 400;

-- Đổi runtime và lưu để lần khởi động sau tiếp tục dùng
SET PERSIST max_connections = 400;

-- Chỉ lưu cho lần khởi động sau, không đổi runtime hiện tại
SET PERSIST_ONLY max_connections = 500;
```

Các ví dụ minh họa cú pháp; chọn giá trị phù hợp với RAM, số kết nối, workload và giới hạn của biến trên server thực tế. Không phải biến nào cũng có thể thay đổi động hoặc persist. Biến chỉ đọc hoặc chỉ có hiệu lực lúc khởi động có thể cần `SET PERSIST_ONLY` nếu biến đó hỗ trợ persist.

Các thiết lập persisted được ghi trong file `mysqld-auto.cnf` tại data directory. MySQL đọc file này khi khởi động và áp dụng các giá trị persisted sau khi xử lý option file và command line; do đó chúng có thể ghi đè giá trị được khai báo ở những nguồn đó. Không chỉnh sửa trực tiếp `mysqld-auto.cnf`; dùng SQL để thay đổi hoặc xóa persisted setting.

Có thể kiểm tra trạng thái cho phép nạp persisted setting:

```sql
SHOW GLOBAL VARIABLES LIKE 'persisted_globals_load';
```

Nếu `persisted_globals_load` bị tắt, server không nạp các persisted setting khi khởi động. Hãy kiểm tra biến này khi giá trị trong `mysqld-auto.cnf` không xuất hiện như mong đợi.

### Xóa persisted setting

Xóa một biến khỏi danh sách persisted:

```sql
RESET PERSIST max_connections;
```

Lệnh này xóa thiết lập được lưu cho lần khởi động sau; nó không tự động đổi giá trị runtime đang có hiệu lực. Nếu cần thay đổi runtime, thực hiện riêng bằng `SET GLOBAL` với giá trị phù hợp.

Để xóa toàn bộ persisted setting, MySQL có `RESET PERSIST` không kèm tên biến. Đây là thao tác phạm vi rộng; cần xem danh sách persisted trước khi dùng và chỉ thực hiện khi đã xác định rõ các thiết lập cần loại bỏ.

Các thao tác thay đổi biến hệ thống cần quyền quản trị phù hợp, thường là `SYSTEM_VARIABLES_ADMIN`; một số thao tác với biến chỉ đọc còn yêu cầu quyền `PERSIST_RO_VARIABLES_ADMIN`. Quyền cụ thể phụ thuộc loại biến và lệnh. Không cấp quyền quản trị rộng cho ứng dụng chỉ để ứng dụng tự thay đổi cấu hình server.

## 7. Thứ tự ưu tiên và cách giải thích xung đột

Khi nhiều nguồn đặt cùng một biến, cần xét cả thứ tự đọc và thời điểm áp dụng. Một mô hình điều tra hữu ích:

1. Giá trị mặc định của MySQL là nền ban đầu.
2. Option file được đọc theo quy tắc và thứ tự của instance; giá trị xuất hiện ở nguồn được xử lý sau có thể ghi đè giá trị trước.
3. Tham số command line có thể ghi đè giá trị đến từ option file.
4. Khi khởi động, persisted setting trong `mysqld-auto.cnf` được áp dụng sau option file và command line, nên có thể ghi đè chúng.
5. Sau khi server chạy, `SET GLOBAL` có thể thay đổi giá trị global động.
6. `SET SESSION` và thiết lập từ ứng dụng có thể làm giá trị của một kết nối khác với global.

Thứ tự chi tiết của option file phụ thuộc nền tảng và tham số khởi động, vì vậy phải kiểm tra command line và metadata `VARIABLE_SOURCE`/`VARIABLE_PATH` của biến cụ thể. Mô hình trên giúp xác định nơi cần kiểm tra; không dùng nó thay cho bằng chứng runtime.

Ví dụ: file `my.ini` đặt `max_connections = 300`, service khởi chạy với `--max-connections=350`, nhưng `mysqld-auto.cnf` có persisted value `400`. Sau khởi động, giá trị global có thể là `400`. Nếu quản trị viên tiếp tục chạy `SET GLOBAL max_connections = 450`, giá trị runtime sẽ là `450` cho đến khi server khởi động lại hoặc bị thay đổi lần nữa. Muốn biết vì sao, hãy kiểm tra giá trị runtime, `variables_info` và `persisted_variables` cùng nhau.

## 8. Quy trình tìm nguyên nhân khi cấu hình không đúng mong đợi

Giả sử nhóm vận hành thay `innodb_buffer_pool_size` trong `my.ini` nhưng sau restart, giá trị global không đổi. Có thể xử lý theo trình tự:

1. **Xác nhận instance:** truy vấn `@@hostname`, `@@port`, `@@datadir`, `@@server_uuid` để chắc đang xem đúng server.
2. **Kiểm tra tiến trình:** xác định executable và command line của dịch vụ, tìm `--defaults-file`, `--defaults-extra-file` hoặc `--no-defaults`.
3. **Xác định option file thực sự:** dùng `mysqld --print-defaults` hoặc `my_print_defaults` với cùng tham số defaults; lần theo `!include` và `!includedir`.
4. **Đọc runtime:** chạy `SHOW GLOBAL VARIABLES` hoặc `SELECT @@GLOBAL...` trên đúng instance.
5. **Truy nguồn:** xem `performance_schema.variables_info` để biết biến đến từ file, command line, persisted setting hay thay đổi động.
6. **Kiểm tra persisted:** xem `performance_schema.persisted_variables` và `persisted_globals_load`.
7. **Kiểm tra session:** nếu ứng dụng vẫn thấy giá trị khác, chạy truy vấn trên chính connection của ứng dụng và kiểm tra lệnh khởi tạo session/connection pool.
8. **Điều chỉnh một nguồn:** sửa đúng nguồn đã xác định, khởi động lại nếu biến chỉ có hiệu lực lúc startup, rồi xác minh lại bằng SQL.

Không nên sửa đồng thời nhiều file hoặc xóa `mysqld-auto.cnf` để thử vận may. Làm vậy có thể che mất nguồn gây xung đột và làm mất các thiết lập persisted khác.

## 9. Ví dụ so sánh GLOBAL và SESSION trên hai kết nối

Giả sử quản trị viên chạy:

```sql
SET GLOBAL time_zone = '+00:00';
```

Một connection mới thường nhận giá trị session mặc định từ global mới. Nhưng connection ứng dụng đã mở trước đó có thể vẫn giữ `time_zone` cũ. Kiểm tra từ từng kết nối:

```sql
SELECT CONNECTION_ID() AS connection_id,
       @@GLOBAL.time_zone AS global_time_zone,
       @@SESSION.time_zone AS session_time_zone;
```

Nếu hai connection trả về `session_time_zone` khác nhau, hãy kiểm tra lệnh `SET SESSION`, cấu hình driver, câu lệnh khởi tạo connection và việc tái sử dụng connection trong pool. Không thể kết luận server đã bỏ qua `SET GLOBAL` chỉ vì một kết nối cũ vẫn có session value cũ.

## 10. Checklist xác định cấu hình hiệu lực

| Câu hỏi | Bằng chứng cần thu thập |
|---|---|
| Đang kiểm tra đúng server không? | `VERSION()`, `@@hostname`, `@@port`, `@@datadir`, `@@server_uuid` |
| Server được khởi chạy với tham số nào? | Command line của process hoặc cấu hình service/unit |
| Option file nào được đọc? | `--defaults-file`, `--defaults-extra-file`, `mysqld --print-defaults`, include directives |
| Runtime global đang là bao nhiêu? | `SHOW GLOBAL VARIABLES`, `@@GLOBAL.variable` |
| Giá trị đến từ đâu? | `performance_schema.variables_info` |
| Có thiết lập persisted không? | `performance_schema.persisted_variables`, `persisted_globals_load` |
| Ứng dụng có session override không? | `@@SESSION.variable` trên chính connection ứng dụng và cấu hình pool |
| Sau thay đổi đã đúng chưa? | Đọc lại runtime, source metadata và xác minh sau restart nếu cần |

## 11. Tự kiểm tra

1. Vì sao đọc một file `my.ini` chưa đủ để kết luận giá trị MySQL đang có hiệu lực?
2. `--defaults-file` khác `--defaults-extra-file` ở mục đích nào?
3. `mysqld --print-defaults` cho biết điều gì và không cho biết điều gì?
4. Vì sao `@@GLOBAL.time_zone` và `@@SESSION.time_zone` có thể khác nhau?
5. `SET GLOBAL`, `SET PERSIST` và `SET PERSIST_ONLY` khác nhau thế nào về runtime và restart?
6. `performance_schema.variables_info` giúp tìm nguồn cấu hình ra sao?
7. Nếu giá trị trong `mysqld-auto.cnf` ghi đè file option, cần kiểm tra bảng nào để xác nhận?
8. Khi ứng dụng nhìn thấy session value cũ sau `SET GLOBAL`, cần điều tra những nơi nào?

