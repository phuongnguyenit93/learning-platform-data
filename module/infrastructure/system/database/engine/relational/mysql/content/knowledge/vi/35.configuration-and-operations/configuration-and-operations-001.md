# Option file, tham số dòng lệnh và thứ tự ưu tiên cấu hình

MySQL nhận cấu hình từ nhiều nguồn: giá trị mặc định được biên dịch vào chương trình, option file, tham số dòng lệnh và các thiết lập system variable được lưu bền vững. Khi server không khởi động hoặc một tham số có giá trị khác mong đợi, cần xác định chính xác chương trình đã đọc file nào, đọc group nào và nguồn nào thắng khi cùng một option xuất hiện nhiều lần.

Option file thường là `my.cnf` trên Unix/Linux hoặc `my.ini` trên Windows. File chứa các group như `[mysqld]`, `[client]`, `[mysql]`; mỗi chương trình chỉ đọc những group phù hợp với nó. Tham số dòng lệnh có thể ghi đè giá trị trong file. Trên MySQL 8.0, persisted system variables được lưu trong `mysqld-auto.cnf` và có quy tắc ưu tiên riêng.

Hiểu đúng thứ tự cấu hình giúp tránh sửa nhầm file, tránh để giá trị cũ âm thầm thắng giá trị mới và giúp triển khai thay đổi an toàn. Bài học tập trung vào cách MySQL tìm option file, cú pháp/group, tham số điều khiển quá trình đọc file, thứ tự ưu tiên, persisted variables và quy trình kiểm tra cấu hình.

## 1. Những nguồn cấu hình của MySQL

Một chương trình MySQL có thể nhận option từ các nguồn sau:

1. **Giá trị mặc định:** giá trị được chương trình sử dụng khi không có nguồn cấu hình nào đặt option đó.
2. **Option file:** file cấu hình chứa các group và option, ví dụ `my.cnf` hoặc `my.ini`.
3. **Tham số dòng lệnh:** option truyền khi khởi động `mysqld`, `mysql` hoặc công cụ client khác.
4. **Persisted system variables:** các global system variable được lưu bằng `SET PERSIST`/`SET PERSIST_ONLY` trên MySQL 8.0.
5. **Thiết lập runtime:** giá trị system variable được thay đổi bằng `SET GLOBAL` hoặc `SET SESSION` trong lúc server/client đang chạy.

Không phải mọi option đều là system variable. Một số option chỉ điều khiển cách chương trình đọc option file hoặc hành vi client; chúng không thể được thay bằng `SET GLOBAL`. Ngược lại, không phải mọi system variable đều có thể thay đổi runtime hoặc được ghi bền vững.

## 2. Option file là gì?

Option file là file văn bản chứa các cấu hình theo nhóm. Server và client đọc file lúc khởi động để lấy các option phù hợp với chương trình.

Ví dụ cấu hình server:

```ini
[mysqld]
max_connections=250
innodb_buffer_pool_size=2G
slow_query_log=ON
long_query_time=1
```

Ví dụ cấu hình client:

```ini
[client]
host=db.internal.example
port=3306
default-character-set=utf8mb4

[mysql]
prompt=\\u@\\h [\\d]> 
```

Trong option file, tên option thường viết không có tiền tố `--`. Ví dụ dòng `max_connections=250` tương đương option dòng lệnh `--max-connections=250`.

## 3. MySQL tìm option file ở đâu?

Các đường dẫn mặc định phụ thuộc hệ điều hành, cách đóng gói, thư mục cài đặt và chương trình cụ thể. Trên Unix/Linux, MySQL thường xét các vị trí cấu hình hệ thống như `/etc/my.cnf`, `/etc/mysql/my.cnf`, thư mục cấu hình do build quy định, file trong thư mục home hoặc file liên quan đến `MYSQL_HOME` đối với server. Trên Windows, các vị trí thường liên quan đến thư mục Windows, ổ đĩa gốc, thư mục cài đặt MySQL hoặc thư mục dữ liệu.

Không nên đoán file nào đang có hiệu lực dựa trên tên hoặc vị trí. Hãy hỏi chính chương trình MySQL:

```bash
mysqld --verbose --help
```

Phần đầu output cho biết các option file và option group mà server dự kiến đọc. Với client:

```bash
mysql --help
```

Output của client cũng hiển thị vị trí option file và các group được đọc. Cú pháp/path cụ thể có thể khác theo phiên bản và bản phân phối; output từ binary đang triển khai là căn cứ thực tế.

## 4. Xác định đúng chương trình và group

Một option file có thể chứa cấu hình cho nhiều chương trình. Mỗi chương trình chỉ đọc những group mà nó hỗ trợ.

| Group | Chương trình thường đọc |
| --- | --- |
| `[client]` | Nhiều chương trình client MySQL |
| `[mysql]` | MySQL command-line client `mysql` |
| `[mysqld]` | MySQL server |
| `[server]` | Các chương trình server phù hợp |
| `[mysqldump]` | Công cụ `mysqldump` |
| `[mysqladmin]` | Công cụ `mysqladmin` |

Ví dụ, `max_connections` thuộc cấu hình server nên đặt trong `[mysqld]` hoặc group server phù hợp. Đặt nó trong `[mysql]` không khiến server nhận giá trị đó. Tương tự, `default-character-set` của client không phải cấu hình server.

Một số phiên bản hỗ trợ group có hậu tố phiên bản như `[mysqld-8.0]` hoặc `[mysqld-8.4]`. Chỉ sử dụng group version-specific khi binary mục tiêu thực sự đọc group đó; kiểm tra danh sách group qua `mysqld --verbose --help`.

## 5. Cú pháp cơ bản của option file

Một option file thường gồm comment, group header và các option:

```ini
# Server configuration
[mysqld]
port=3306
max_connections=250
skip-name-resolve

; Client defaults
[client]
port=3306
default-character-set=utf8mb4
```

Các quy tắc thường dùng:

- Dòng bắt đầu bằng `#` hoặc `;` là comment.
- Group bắt đầu bằng `[group_name]`.
- Option nằm sau group header thuộc group đó cho đến group header tiếp theo.
- Trong option file, thường không đặt `--` trước tên option.
- Option dạng boolean có thể viết `name`, `name=ON`, `name=TRUE` hoặc `name=1` tùy option.
- Option phủ định có thể dùng dạng `skip-name-resolve` hoặc `disable-...` nếu option hỗ trợ.
- Giá trị có khoảng trắng cần được quote theo cú pháp option file.

Tên option có thể dùng dấu gạch ngang hoặc dấu gạch dưới theo quy tắc tương thích của MySQL, nhưng nên thống nhất một kiểu trong repository cấu hình để review dễ hơn.

## 6. Boolean option và giá trị có kiểu

Ví dụ boolean:

```ini
[mysqld]
event-scheduler=ON
local-infile=OFF
```

Một số option có dạng phủ định:

```ini
[mysqld]
skip-name-resolve
```

Không áp dụng `skip-` một cách máy móc cho mọi tên option. Hãy kiểm tra option cụ thể trong tài liệu phiên bản MySQL đang chạy.

Ví dụ option có số và đơn vị:

```ini
[mysqld]
max_connections=250
innodb_buffer_pool_size=2G
tmp_table_size=64M
```

Giá trị cần nằm trong miền hợp lệ của biến. MySQL có thể từ chối giá trị không hợp lệ, cảnh báo hoặc điều chỉnh theo quy tắc của từng biến. Không giả định mọi biến đều chấp nhận cùng một hậu tố đơn vị.

## 7. Include file cấu hình khác

Option file có thể nạp file khác bằng directive `!include` hoặc nạp thư mục bằng `!includedir` trên các nền tảng/phiên bản hỗ trợ.

Ví dụ:

```ini
!include /etc/mysql/conf.d/server-base.cnf
!includedir /etc/mysql/conf.d
```

Đây là directive của option-file parser, không phải system variable. Chúng hữu ích để tách cấu hình theo thành phần, ví dụ `server.cnf`, `innodb.cnf`, `logging.cnf`.

Khi dùng `!includedir`, không nên dựa vào thứ tự tên file nếu ứng dụng yêu cầu một option phải thắng option khác. Quy tắc chọn file trong thư mục có thể phụ thuộc nền tảng và cách triển khai. Hãy kiểm tra output `--print-defaults` và giá trị runtime thực tế.

## 8. Thứ tự đọc nhiều option file

MySQL có thể đọc nhiều option file theo thứ tự được xác định bởi chương trình và nền tảng. Khi cùng một option xuất hiện trong nhiều file, giá trị đọc sau thường ghi đè giá trị đọc trước.

Ví dụ minh họa:

```ini
# File cấu hình nền được đọc trước
[mysqld]
max_connections=200
```

```ini
# File cấu hình bổ sung được đọc sau
[mysqld]
max_connections=300
```

Nếu cả hai file đều được server đọc theo thứ tự trên, giá trị cuối cùng từ option file là `300`. Nhưng không được kết luận chỉ từ nội dung file; phải xác nhận file nào thực sự được đọc và thứ tự của chúng.

Khi một option xuất hiện nhiều lần trong cùng nguồn, lần xuất hiện sau thường có hiệu lực theo cách parser xử lý option đó. Một số option có thể có hành vi tích lũy/đặc biệt; không áp dụng quy tắc “last wins” cho mọi danh sách option mà không kiểm tra tài liệu.

## 9. Tham số dòng lệnh ghi đè option file

Option truyền trực tiếp khi khởi động chương trình thường có ưu tiên cao hơn option đọc từ file.

Ví dụ server được khởi động bằng:

```bash
mysqld --defaults-file=/etc/mysql/my.cnf --max-connections=400
```

Nếu file chứa `max_connections=250`, tham số `--max-connections=400` trên command line sẽ ghi đè giá trị trong file cho lần khởi động đó.

Điều này thường gặp khi service manager, container entrypoint, orchestration platform hoặc script khởi động truyền thêm tham số. Sửa `my.cnf` mà không kiểm tra command line có thể không làm giá trị runtime thay đổi như mong muốn.

## 10. Các option điều khiển quá trình đọc option file

Một số option đặc biệt quyết định MySQL đọc file nào. Chúng thường cần đặt ở đầu danh sách tham số, trước các option thông thường:

| Option | Tác dụng |
| --- | --- |
| `--no-defaults` | Không đọc option file mặc định |
| `--defaults-file=path` | Chỉ đọc option file được chỉ định thay cho tập file mặc định |
| `--defaults-extra-file=path` | Đọc thêm file được chỉ định cùng các file mặc định theo quy tắc chương trình |
| `--defaults-group-suffix=suffix` | Đọc thêm các group có hậu tố được chỉ định |
| `--print-defaults` | In các option chương trình lấy từ option file rồi thoát |

Ví dụ chạy client với file cấu hình riêng:

```bash
mysql --defaults-file=/opt/app/mysql-client.cnf -u app_reader -p
```

Ví dụ bỏ qua cấu hình mặc định để thử nghiệm:

```bash
mysql --no-defaults -h 127.0.0.1 -P 3306 -u test_user -p
```

Đặt các option `--defaults-...` trước các option khác để tránh chương trình không áp dụng chúng như mong đợi. Chúng là chỉ thị cho option parser, không phải cấu hình có thể thay đổi bằng `SET GLOBAL`.

## 11. Phân biệt defaults-file và defaults-extra-file

`--defaults-file` yêu cầu chương trình đọc file được chỉ định thay cho các option file mặc định. Đây là cách cô lập cấu hình cho một instance hoặc một lệnh cụ thể.

`--defaults-extra-file` bổ sung một file vào quá trình đọc option file mặc định. Nó phù hợp khi muốn giữ cấu hình hệ thống chung và thêm một số option riêng cho một lần chạy hoặc một ứng dụng.

Ví dụ:

```bash
# Chỉ dùng file được chỉ định
mysqld --defaults-file=/etc/mysql/instance-a.cnf

# Đọc cấu hình mặc định và thêm file riêng
mysql --defaults-extra-file=/opt/app/client-extra.cnf -u app_reader -p
```

Không dùng hai option này như thể chúng đồng nghĩa. Khi điều tra cấu hình bị ghi đè, hãy xác nhận command line của process thực tế và danh sách file mà chương trình đọc.

## 12. Group suffix cho nhiều cấu hình trong cùng file

`--defaults-group-suffix` cho phép chương trình đọc thêm group có hậu tố. Ví dụ:

```ini
[client]
host=localhost
port=3306

[client_reporting]
host=report-db.internal.example
port=3307
```

Chạy:

```bash
mysql --defaults-group-suffix=_reporting -u report_user -p
```

Client đọc group thông thường mà nó hỗ trợ và thêm group có hậu tố tương ứng, ví dụ `[client_reporting]` và `[mysql_reporting]` nếu phù hợp. Tính năng này hữu ích khi cùng một binary cần kết nối nhiều môi trường/instance mà không phải tạo nhiều file riêng.

Không đặt bí mật vào group suffix dùng chung hoặc chia sẻ file rộng hơn phạm vi cần thiết. Cũng cần kiểm tra chính xác group mà chương trình đọc trước khi kỳ vọng một option có hiệu lực.

## 13. In các option đã đọc bằng --print-defaults

`--print-defaults` hiển thị các option chương trình lấy từ option file:

```bash
mysqld --print-defaults
mysql --print-defaults
```

Lệnh này hữu ích để phát hiện file/group có được đọc và option nào đang xuất hiện trong kết quả parser. Nó không chứng minh server đang chạy đã áp dụng thành công mọi giá trị, cũng không phản ánh thay đổi runtime được thực hiện sau khi server khởi động.

Output có thể chứa thông tin nhạy cảm nếu option file lưu credential hoặc token. Không dán output nguyên văn vào ticket, chat hoặc log công khai; che bí mật trước khi chia sẻ.

## 14. Thứ tự ưu tiên tổng thể trên MySQL 8.0

Với system variable, cần xét cả option file, command line và persisted settings. Một cách nhớ thực tế cho cấu hình khởi động MySQL 8.0 là:

1. Giá trị mặc định của chương trình là nền thấp nhất.
2. Option file cung cấp giá trị cấu hình.
3. Persisted system variable settings trong `mysqld-auto.cnf` được nạp sau option file và có thể ghi đè giá trị từ file.
4. Tham số dòng lệnh có ưu tiên cao hơn persisted settings.
5. Sau khi server chạy, các thay đổi runtime hợp lệ có thể thay giá trị hiện hành theo scope và quyền của người thực hiện.

Thứ tự thực tế còn phụ thuộc loại option, phiên bản và cách service khởi động. Đặc biệt, `--no-defaults`, `--defaults-file` và `--defaults-extra-file` thay đổi chính quá trình đọc file. Hãy kiểm tra `VARIABLE_SOURCE` và giá trị runtime thay vì chỉ suy ra từ file.

## 15. System variable khác startup option như thế nào?

Startup option là tham số chương trình nhận khi khởi động. Nhiều startup option tương ứng với system variable, ví dụ `--max-connections` điều khiển system variable `max_connections`.

Một số option chỉ điều khiển chương trình hoặc option parser và không có system variable tương ứng. Vì vậy, không thể tìm mọi option bằng `SHOW VARIABLES`.

System variable có thể có:

- **Global scope:** áp dụng ở cấp server; có thể ảnh hưởng session mới.
- **Session scope:** áp dụng cho connection/session hiện tại.
- **Dynamic:** có thể thay đổi khi server đang chạy.
- **Static:** cần thay đổi cấu hình khởi động và restart server.

Kiểm tra phạm vi và khả năng thay đổi theo tài liệu của từng biến. `SET GLOBAL` không có nghĩa mọi connection hiện tại lập tức nhận giá trị session mới; session variable có thể giữ giá trị riêng.

## 16. Thay đổi runtime bằng SET GLOBAL

Ví dụ thay đổi số connection tối đa trong lúc server chạy:

```sql
SET GLOBAL max_connections = 300;

SHOW GLOBAL VARIABLES LIKE 'max_connections';
```

`SET GLOBAL` chỉ thay giá trị trong bộ nhớ của server. Khi restart, giá trị có thể trở về nguồn cấu hình lúc khởi động nếu không lưu bền vững.

Một biến session có thể được đặt riêng cho connection:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
SELECT @@SESSION.sql_mode;
```

Không nhầm `SET SESSION` với thay đổi cấu hình toàn server. Thay đổi global thường cần quyền quản trị phù hợp; MySQL 8.0 dùng dynamic privilege như `SYSTEM_VARIABLES_ADMIN` cho nhiều thao tác quản lý system variable.

## 17. SET PERSIST và SET PERSIST_ONLY

MySQL 8.0 hỗ trợ lưu một số global system variable để tồn tại qua lần restart:

```sql
SET PERSIST max_connections = 300;
```

`SET PERSIST` thay giá trị global runtime và ghi giá trị vào kho persisted settings để server nạp lại khi khởi động sau.

`SET PERSIST_ONLY` lưu giá trị cho lần khởi động sau mà không thay đổi giá trị runtime hiện tại. Nó hữu ích với biến không thể thay đổi động hoặc khi muốn chuẩn bị thay đổi có hiệu lực sau restart:

```sql
SET PERSIST_ONLY some_startup_variable = value;
```

Ví dụ thứ hai chỉ là khuôn cú pháp; thay `some_startup_variable` và `value` bằng biến thực tế, kiểu dữ liệu hợp lệ và xác nhận biến hỗ trợ persistence trong phiên bản đang chạy.

Không phải mọi system variable đều có thể persist. Biến phải có scope/đặc tính phù hợp và không thuộc nhóm bị cấm lưu bền vững. Kiểm tra lỗi trả về và tài liệu của biến trước khi đưa vào quy trình vận hành.

## 18. mysqld-auto.cnf và quản lý persisted settings

Các giá trị được lưu bằng `SET PERSIST`/`SET PERSIST_ONLY` được ghi vào file `mysqld-auto.cnf` trong data directory. Server đọc file này khi khởi động nếu `persisted_globals_load` cho phép.

Kiểm tra các giá trị persisted:

```sql
SELECT *
FROM performance_schema.persisted_variables;
```

Xóa một giá trị persisted:

```sql
RESET PERSIST max_connections;
```

Xóa toàn bộ persisted settings:

```sql
RESET PERSIST;
```

Không sửa `mysqld-auto.cnf` bằng editor hoặc script thông thường khi server đang quản lý file. Dùng `SET PERSIST`, `SET PERSIST_ONLY` và `RESET PERSIST` để giữ metadata nhất quán. Nếu cần vô hiệu hóa việc nạp persisted settings, kiểm tra biến `persisted_globals_load` và quy trình khởi động của phiên bản đang dùng.

## 19. Xác định nguồn giá trị bằng Performance Schema

Trên MySQL 8.0, `performance_schema.variables_info` giúp điều tra nguồn của global system variable:

```sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME IN (
    'max_connections',
    'innodb_buffer_pool_size',
    'slow_query_log'
);
```

Các cột source/path giúp nhận biết giá trị đến từ option file, command line, persisted setting hoặc thao tác runtime tùy phiên bản và trường hợp. Bảng có thể chứa `NULL` cho một số thông tin nếu không áp dụng.

Để xem giá trị hiện tại:

```sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SELECT @@GLOBAL.max_connections;
```

Kết hợp giá trị runtime với nguồn cấu hình là cách nhanh để tìm ra vì sao file có `250` nhưng server đang trả `400`.

## 20. Validate cấu hình trước khi restart

Không nên thay đổi cấu hình production rồi restart ngay mà chưa kiểm tra cú pháp và option name.

Trên MySQL 8.0.16 trở lên, có thể dùng:

```bash
mysqld --validate-config
```

Lệnh này yêu cầu server kiểm tra cấu hình và thoát; nó không thay thế việc khởi động thử trong môi trường staging. Có thể kết hợp chỉ định file cấu hình:

```bash
mysqld --defaults-file=/etc/mysql/my.cnf --validate-config
```

Trên Windows, chỉ định đường dẫn `my.ini` bằng dấu nháy nếu path có khoảng trắng:

```powershell
mysqld.exe --defaults-file="C:\ProgramData\MySQL\MySQL Server 8.4\my.ini" --validate-config
```

Nếu server chạy như Windows service, kiểm tra cả cấu hình service và tham số khởi động mà service truyền cho `mysqld.exe`; chúng có thể cung cấp option ghi đè file.

Với phiên bản không hỗ trợ `--validate-config`, dùng `mysqld --verbose --help` để kiểm tra option/group được nhận và kiểm thử thay đổi trong môi trường tương ứng trước khi triển khai.

## 21. Ví dụ một cấu hình server và client có phân nhóm

Một file minh họa:

```ini
[mysqld]
port=3306
max_connections=250
innodb_buffer_pool_size=2G
slow_query_log=ON
long_query_time=1
character-set-server=utf8mb4
collation-server=utf8mb4_0900_ai_ci

[client]
port=3306
default-character-set=utf8mb4

[mysql]
prompt=\\u@\\h [\\d]> 
```

Server đọc nhóm cấu hình server; command-line client `mysql` đọc nhóm client và nhóm riêng của nó. Nếu đưa `max_connections` vào `[client]`, client không truyền nó thành cấu hình server. Nếu đưa `default-character-set` vào `[mysqld]`, không có nghĩa mọi client sẽ tự dùng charset đó.

## 22. Ví dụ truy tìm giá trị bị ghi đè

Giả sử `my.cnf` có:

```ini
[mysqld]
max_connections=250
```

Nhưng runtime trả về `400`:

```sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
```

Điều tra theo thứ tự:

1. Kiểm tra process command line xem có `--max-connections=400` không.
2. Chạy `mysqld --verbose --help` để xác định file và group được đọc.
3. Dùng `mysqld --print-defaults` để xem các option parser lấy từ file.
4. Trên MySQL 8.0, kiểm tra `performance_schema.variables_info` để xem nguồn giá trị.
5. Kiểm tra `performance_schema.persisted_variables` xem có persisted value `400` không.
6. Kiểm tra có thao tác `SET GLOBAL` sau startup hoặc automation nào thay đổi giá trị không.

Không sửa file đầu tiên tìm thấy rồi restart nhiều lần. Xác định nguồn thắng trước, sau đó thay đổi đúng nguồn và loại bỏ cấu hình trùng lặp không còn cần thiết.

## 23. Bảo mật và quản lý option file

Option file có thể chứa username, password, TLS path hoặc thông tin kết nối. Một số công cụ client có thể đọc credential từ option file; do đó:

- Chỉ cấp quyền đọc file cho tài khoản hệ điều hành cần thiết.
- Không commit password/token vào repository cấu hình dùng chung.
- Dùng secret manager hoặc cơ chế credential phù hợp cho môi trường production.
- Không chia sẻ nguyên output `--print-defaults` nếu có thông tin nhạy cảm.
- Không đặt mật khẩu trong command line vì có thể lộ qua process listing, shell history hoặc hệ thống giám sát.
- Tách cấu hình client và server bằng group rõ ràng.
- Quản lý thay đổi qua version control, review và quy trình rollout.

Option file không phải cơ chế mã hóa bí mật. Nếu file chứa credential, bảo vệ file bằng quyền filesystem và quy trình quản lý secret.

## 24. Quy trình triển khai thay đổi cấu hình

Một quy trình vận hành an toàn:

1. Xác định mục tiêu, biến/option và phiên bản MySQL đang chạy.
2. Xác định nguồn hiện tại: option file, command line, persisted setting hay runtime.
3. Xác nhận biến có dynamic hay cần restart; kiểm tra scope và miền giá trị.
4. Chỉnh đúng file/group hoặc dùng `SET PERSIST` nếu đó là cơ chế được chọn.
5. Review diff, quyền file và các giá trị nhạy cảm.
6. Validate bằng `mysqld --validate-config` nếu phiên bản hỗ trợ.
7. Thử ở staging hoặc instance canary có dữ liệu/workload tương tự.
8. Triển khai thay đổi; nếu cần restart, dùng quy trình restart có kiểm soát và xác nhận replication/cluster health.
9. Đọc lại `SHOW GLOBAL VARIABLES` và `variables_info` để xác nhận giá trị cùng nguồn.
10. Theo dõi error log, connection, latency, memory và metric liên quan.
11. Lưu lại cấu hình hiệu lực, lý do thay đổi và phương án rollback.

Không thay nhiều tham số không liên quan trong cùng một lần rollout nếu chưa có cách quy trách nhiệm khi sự cố xảy ra.

## 25. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| Chỉ có một file my.cnf | MySQL có thể đọc nhiều file theo thứ tự | Dùng `--verbose --help` để liệt kê |
| Mọi chương trình đọc mọi group | Mỗi chương trình đọc group phù hợp | Xác định group theo binary |
| Đặt option ở đâu trong file cũng có tác dụng | Option chỉ thuộc group hiện tại | Đặt vào `[mysqld]`, `[client]` hoặc group đúng |
| Sửa option file luôn thắng | Command line và persisted setting có thể ghi đè | Kiểm tra nguồn runtime |
| `--defaults-file` giống `--defaults-extra-file` | Một cái thay tập file mặc định; cái kia bổ sung file | Chọn đúng mục tiêu |
| `--no-defaults` tắt mọi nguồn cấu hình | Nó bỏ qua option file mặc định, nhưng command line/runtime vẫn tồn tại | Phân biệt các nguồn |
| `SET GLOBAL` tồn tại sau restart | Thông thường chỉ thay runtime | Dùng option file hoặc `SET PERSIST` nếu phù hợp |
| Mọi biến đều dynamic | Một số biến cần restart | Kiểm tra metadata/tài liệu biến |
| `--print-defaults` cho biết runtime chắc chắn | Nó chỉ in option từ file | Kiểm tra `SHOW GLOBAL VARIABLES` và `variables_info` |
| `mysqld-auto.cnf` nên sửa trực tiếp | Đây là file server quản lý | Dùng `SET PERSIST`/`RESET PERSIST` |
| `mysqld --validate-config` có ở mọi phiên bản | Tùy phiên bản; có từ MySQL 8.0.16 | Kiểm tra phiên bản trước |
| Tên option không phân biệt client/server | Group quyết định chương trình nhận option | Phân nhóm và xác minh bằng help output |

## 26. Bài tập thực hành

1. Chạy `mysqld --verbose --help` và ghi lại các option file/group server đọc trên máy lab.
2. Chạy `mysql --help` và so sánh danh sách file/group với server.
3. Tạo option file lab có `[mysqld]`, `[client]` và `[mysql]`; giải thích chương trình nào đọc từng group.
4. Đặt cùng một option trong hai file được đọc nối tiếp; kiểm tra giá trị nào có hiệu lực.
5. Khởi động một client với `--defaults-file` và so sánh với `--defaults-extra-file`.
6. Dùng `--no-defaults` để chạy client độc lập với option file; xác nhận tham số dòng lệnh vẫn có tác dụng.
7. Dùng `--defaults-group-suffix` để chọn một group riêng cho môi trường báo cáo.
8. Chạy `--print-defaults`; xác định giới hạn của output và che mọi credential trước khi lưu lại.
9. Thay đổi một dynamic global variable bằng `SET GLOBAL`; restart lab và quan sát giá trị có trở về hay không.
10. Dùng `SET PERSIST` cho một biến được hỗ trợ; kiểm tra `performance_schema.persisted_variables`.
11. Dùng `RESET PERSIST` để xóa giá trị đã lưu; xác nhận nguồn giá trị sau restart.
12. Truy vấn `performance_schema.variables_info` để tìm nguồn của `max_connections`.
13. Trên MySQL 8.0.16+, chạy `mysqld --validate-config`; thử một option sai trong file lab và ghi nhận lỗi.
14. Viết quy trình rollout/rollback cho một thay đổi `innodb_buffer_pool_size` hoặc `max_connections` ở môi trường staging.

## 27. Ghi nhớ

MySQL đọc option từ nhiều nguồn. Option file chứa group như `[mysqld]`, `[server]`, `[client]`, `[mysql]`; mỗi binary chỉ đọc group phù hợp. Đường dẫn và thứ tự file phụ thuộc nền tảng/phiên bản, vì vậy dùng `mysqld --verbose --help` hoặc `mysql --help` để xác nhận. Trong option file, option thường không có tiền tố `--`; có thể dùng `!include`/`!includedir` để tách cấu hình khi được hỗ trợ.

Các option `--no-defaults`, `--defaults-file`, `--defaults-extra-file` và `--defaults-group-suffix` điều khiển cách đọc file, nên đặt ở đầu command line. File đọc sau thường ghi đè file đọc trước; command-line option ghi đè option file. Trên MySQL 8.0, persisted system variables trong `mysqld-auto.cnf` được nạp sau option file; command line có ưu tiên cao hơn persisted settings. `SET GLOBAL` thay runtime; `SET PERSIST` thay runtime và lưu cho lần restart; `SET PERSIST_ONLY` chỉ lưu cho lần restart sau. Dùng `--print-defaults`, `SHOW GLOBAL VARIABLES`, `performance_schema.variables_info`, `performance_schema.persisted_variables` và `mysqld --validate-config` (MySQL 8.0.16+) để điều tra. Luôn xác định nguồn thắng, kiểm tra phiên bản, bảo vệ credential, thử staging và có phương án rollback trước khi triển khai.
