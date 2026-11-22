# SET GLOBAL, SET PERSIST, SET PERSIST_ONLY và cấu hình sau khởi động

MySQL có nhiều cách thay đổi system variable: chỉnh cấu hình khởi động, dùng lệnh SET GLOBAL, lưu giá trị bằng SET PERSIST hoặc chuẩn bị giá trị cho lần khởi động tiếp theo bằng SET PERSIST_ONLY. Chọn sai cách có thể khiến cấu hình chỉ có hiệu lực tạm thời, ghi đè cấu hình được quản lý bằng file hoặc làm máy chủ không khởi động như dự kiến.

Bài học này giải thích phạm vi và khả năng thay đổi của system variable, sự khác nhau giữa ba lệnh SET, cách MySQL nạp cấu hình sau restart, nơi lưu giá trị persistent, quyền cần có, cách kiểm tra nguồn cấu hình và quy trình rollback. Ví dụ tập trung vào cấu hình vận hành như max_connections, innodb_buffer_pool_size và biến chỉ được thiết lập khi khởi động.

## 1. System variable và các lớp cấu hình

System variable điều khiển hành vi của MySQL Server. Ví dụ:

- max_connections: giới hạn số kết nối đồng thời.
- innodb_buffer_pool_size: dung lượng buffer pool của InnoDB.
- slow_query_log: bật hoặc tắt slow query log.
- long_query_time: ngưỡng thời gian để ghi nhận truy vấn chậm.
- innodb_flush_method: lựa chọn phương thức flush file của InnoDB trên các hệ điều hành hỗ trợ.

Giá trị hiệu lực của một biến có thể đến từ nhiều nơi:

1. Giá trị mặc định được biên dịch trong MySQL.
2. Option file như my.cnf hoặc my.ini.
3. File persistent do MySQL quản lý.
4. Tham số dòng lệnh khi khởi động mysqld.
5. Lệnh SET trong lúc server đang chạy.

Các nguồn này có thời điểm áp dụng và mức ưu tiên khác nhau. Cần phân biệt giá trị hiện tại trong bộ nhớ với giá trị sẽ được nạp khi server khởi động lại.

### 1.1. Cấu hình runtime và cấu hình startup

**Runtime configuration** là giá trị đang có hiệu lực trong tiến trình MySQL hiện tại. Nó có thể được thay đổi bằng SET GLOBAL hoặc SET PERSIST nếu biến cho phép thay đổi động.

**Startup configuration** là giá trị MySQL đọc khi khởi động. Nó có thể đến từ option file, persisted configuration hoặc command line. Một số biến chỉ được thiết lập tại thời điểm này.

Ví dụ:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';

SET GLOBAL max_connections = 300;
~~~

Lệnh SET GLOBAL thay đổi giá trị runtime. Sau khi server restart, giá trị 300 không tự tồn tại nếu không có nguồn cấu hình startup lưu nó.

### 1.2. Ba câu hỏi cần trả lời trước khi thay đổi

Trước khi chỉnh một biến, xác định:

1. Biến có phạm vi GLOBAL, SESSION hay cả hai?
2. Biến có dynamic hay chỉ được đọc khi khởi động?
3. Giá trị cần có hiệu lực ngay, sau restart, hay cả hai?

Ba câu hỏi này quyết định nên dùng SET GLOBAL, SET PERSIST hay SET PERSIST_ONLY.

## 2. Phạm vi GLOBAL và SESSION

System variable có thể có phạm vi GLOBAL, SESSION hoặc cả hai.

| Phạm vi | Ý nghĩa |
|---|---|
| GLOBAL | Một giá trị chung ở cấp server |
| SESSION | Giá trị riêng của một kết nối |
| BOTH | Có cả giá trị global và session |

Đọc giá trị:

~~~sql
SELECT
    @@GLOBAL.max_connections AS global_max_connections;

SHOW GLOBAL VARIABLES LIKE 'max_connections';
~~~

Đọc giá trị session:

~~~sql
SELECT @@SESSION.sql_mode;

SHOW SESSION VARIABLES LIKE 'sql_mode';
~~~

Nếu một biến có cả hai phạm vi, giá trị session thường được khởi tạo từ giá trị global khi kết nối mới được tạo. Thay đổi giá trị global không tự ghi đè giá trị session của các kết nối đã tồn tại.

Ví dụ:

~~~sql
SET GLOBAL sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

Kết nối mới nhận giá trị mặc định session từ global mới. Một kết nối cũ có thể vẫn giữ session sql_mode trước đó cho đến khi session tự thay đổi hoặc kết thúc.

### 2.1. Không dùng SET GLOBAL để thay đổi session

Nếu chỉ muốn đổi hành vi trong kết nối hiện tại, dùng:

~~~sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

Hoặc:

~~~sql
SET @@SESSION.sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

SET GLOBAL tác động ở cấp server và cần quyền quản trị phù hợp. Không dùng nó để sửa một truy vấn thử nghiệm chỉ cần thay đổi trong session.

### 2.2. SET PERSIST không phải lệnh dành cho SESSION

SET PERSIST và SET PERSIST_ONLY lưu giá trị ở phạm vi global để MySQL sử dụng khi khởi động. Chúng không dùng để lưu cấu hình riêng cho một connection.

Nếu biến có cả GLOBAL và SESSION, hãy chọn rõ SET SESSION khi muốn thay đổi riêng kết nối; dùng SET PERSIST khi muốn thay đổi global runtime và lưu giá trị cho lần khởi động sau.

## 3. Dynamic variable và read-only variable

Khả năng thay đổi một system variable được quyết định bởi thuộc tính của biến, không phải chỉ bởi việc người dùng có quyền quản trị.

### 3.1. Dynamic variable

Dynamic variable có thể thay đổi khi server đang chạy. Ví dụ max_connections và long_query_time có thể thay đổi runtime.

~~~sql
SET GLOBAL max_connections = 300;
SET GLOBAL long_query_time = 2;
~~~

Thay đổi có hiệu lực ngay theo phạm vi và quy tắc của từng biến. Tuy nhiên, thay đổi runtime bằng SET GLOBAL không tự được ghi vào cấu hình persistent.

### 3.2. Read-only hoặc startup-only variable

Một số biến chỉ có thể được xác định khi server khởi động. Chúng không thể được đổi bằng SET GLOBAL trong lúc server đang chạy.

Ví dụ, innodb_flush_method là biến cấu hình khởi động trên các nền tảng và phiên bản có hỗ trợ. Muốn chuẩn bị giá trị mới cho lần restart, có thể dùng SET PERSIST_ONLY nếu biến đó được phép persist và môi trường hỗ trợ giá trị được chọn.

~~~sql
SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT';
~~~

Đây là ví dụ minh họa cú pháp, không phải khuyến nghị áp dụng O_DIRECT cho mọi máy chủ. Phương thức flush hợp lệ phụ thuộc hệ điều hành, filesystem, phiên bản MySQL và cách triển khai lưu trữ. Hãy kiểm tra tài liệu của nền tảng trước khi chọn giá trị.

### 3.3. Kiểm tra thuộc tính và nguồn của biến

MySQL cung cấp metadata trong Performance Schema:

~~~sql
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
    'innodb_flush_method'
);
~~~

VARIABLE_SOURCE cho biết nguồn cấu hình mà MySQL ghi nhận, chẳng hạn giá trị mặc định, option file, command line, persisted configuration hoặc thay đổi động. VARIABLE_PATH có thể cho biết đường dẫn option file liên quan. Metadata có thể khác nhau tùy phiên bản và nguồn thực tế.

Không suy luận một biến là dynamic chỉ từ tên hoặc từ việc SHOW VARIABLES đọc được nó. Hãy tra cứu thuộc tính của đúng biến trong Reference Manual và kiểm tra metadata trên server.

## 4. SET GLOBAL: thay đổi runtime

SET GLOBAL gán giá trị mới cho một system variable ở phạm vi global nếu biến cho phép thay đổi động.

Cú pháp:

~~~sql
SET GLOBAL variable_name = value;
~~~

Hoặc:

~~~sql
SET @@GLOBAL.variable_name = value;
~~~

Ví dụ:

~~~sql
SET GLOBAL max_connections = 400;

SELECT @@GLOBAL.max_connections;
~~~

Giá trị mới có hiệu lực trong server đang chạy. Với biến có cả GLOBAL và SESSION, các kết nối mới nhận giá trị global mới làm giá trị session khởi tạo; các kết nối hiện tại không tự động bị ghi đè.

### 4.1. SET GLOBAL không lưu qua restart

SET GLOBAL chỉ thay đổi runtime. Nếu không có cấu hình startup khác lưu giá trị, sau khi restart MySQL sẽ nạp giá trị từ option file, persisted configuration, command line hoặc default.

Đây là lựa chọn phù hợp khi:

- Thử nghiệm thay đổi trong môi trường staging.
- Điều chỉnh tạm thời để xử lý sự cố.
- Muốn đo tác động trước khi quyết định lưu lâu dài.
- Giá trị chỉ cần tồn tại trong vòng đời hiện tại của server.

Nếu thay đổi đã được xác nhận và cần giữ qua restart, hãy cập nhật nguồn cấu hình lâu dài hoặc dùng SET PERSIST theo chính sách vận hành.

### 4.2. SET GLOBAL chỉ áp dụng cho biến dynamic

Nếu biến là read-only hoặc chỉ được thiết lập lúc khởi động, SET GLOBAL sẽ thất bại. Quyền quản trị không làm một biến startup-only trở thành dynamic.

Không dùng SET GLOBAL để thử ép thay đổi một biến không hỗ trợ runtime. Hãy kiểm tra tài liệu biến và dùng SET PERSIST_ONLY hoặc option file nếu phù hợp.

### 4.3. Ví dụ điều chỉnh tạm thời

~~~sql
-- Ghi nhận giá trị hiện tại.
SELECT @@GLOBAL.long_query_time AS old_value;

-- Hạ ngưỡng trong thời gian điều tra.
SET GLOBAL long_query_time = 1;

-- Xác nhận giá trị mới.
SELECT @@GLOBAL.long_query_time AS current_value;
~~~

Khi kết thúc điều tra, có thể trả về giá trị đã ghi nhận bằng SET GLOBAL. Đừng mặc định giá trị cũ là giá trị mặc định của MySQL; nó có thể đến từ option file hoặc một cấu hình persistent.

## 5. SET PERSIST: thay đổi runtime và lưu cho lần khởi động sau

SET PERSIST thực hiện hai việc đối với biến global có thể thay đổi động:

1. Gán giá trị mới vào runtime như SET GLOBAL.
2. Ghi giá trị vào persistent configuration để MySQL nạp lại ở lần khởi động tiếp theo.

Cú pháp:

~~~sql
SET PERSIST variable_name = value;
~~~

Ví dụ:

~~~sql
SET PERSIST max_connections = 400;
~~~

Sau lệnh này, giá trị global đang chạy được đổi và giá trị cũng được lưu vào file persistent do MySQL quản lý.

### 5.1. Khi nào dùng SET PERSIST?

Dùng khi:

- Biến hỗ trợ thay đổi runtime.
- Giá trị mới đã được kiểm thử và cần tồn tại qua restart.
- Chính sách vận hành cho phép MySQL quản lý persistent setting.
- Đã ghi nhận giá trị hiện tại và có phương án rollback.

SET PERSIST thuận tiện cho thay đổi có kiểm soát từ SQL. Tuy nhiên, nếu tổ chức quản lý cấu hình tập trung bằng Ansible, Puppet, Chef, image hoặc hệ thống deployment, hãy cân nhắc cập nhật nguồn cấu hình chuẩn thay vì tạo thêm một nguồn cấu hình riêng trong mysqld-auto.cnf.

### 5.2. SET PERSIST không thay thế kiểm tra tải

Ví dụ tăng max_connections không có nghĩa máy chủ tự có thêm RAM cho mỗi kết nối. Mỗi kết nối có thể sử dụng bộ nhớ theo workload và các buffer được cấp phát theo nhu cầu.

Trước khi tăng giới hạn, hãy kiểm tra:

- Số kết nối thực tế và số kết nối đồng thời cao điểm.
- Connection pool ở tầng ứng dụng.
- Bộ nhớ nền và bộ nhớ theo connection.
- Giới hạn file descriptor và tài nguyên hệ điều hành.
- Khả năng chịu tải của CPU, storage và workload.

Persistent setting làm thay đổi tồn tại lâu dài; nó không chứng minh giá trị mới là an toàn.

### 5.3. SET PERSIST chỉ dành cho GLOBAL

SET PERSIST không lưu một giá trị SESSION riêng cho connection. Khi cần thay đổi session, dùng SET SESSION. Khi cần thay đổi global và giữ qua restart, dùng SET PERSIST.

### 5.4. Giá trị DEFAULT

Có thể dùng DEFAULT để đặt biến về giá trị mặc định của MySQL trong phạm vi lệnh tương ứng:

~~~sql
SET GLOBAL max_connections = DEFAULT;
~~~

Đối với thay đổi persistent, hãy phân biệt việc lưu giá trị DEFAULT với việc xóa override persistent. Nếu mục tiêu là bỏ hẳn một mục khỏi persisted configuration để server quay lại lấy giá trị từ nguồn thấp hơn, dùng RESET PERSIST.

## 6. SET PERSIST_ONLY: lưu giá trị, chưa đổi runtime

SET PERSIST_ONLY ghi giá trị vào persistent configuration nhưng không thay đổi giá trị đang chạy. Khi MySQL khởi động lại và nạp persisted setting, giá trị mới mới có hiệu lực.

Cú pháp:

~~~sql
SET PERSIST_ONLY variable_name = value;
~~~

Ví dụ:

~~~sql
SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT';
~~~

Đây là ví dụ minh họa một biến chỉ cấu hình lúc khởi động. Giá trị O_DIRECT chỉ là lựa chọn ví dụ trên nền tảng hỗ trợ; cần xác minh filesystem, thiết bị lưu trữ, phiên bản MySQL và yêu cầu durability trước khi áp dụng.

### 6.1. Phân biệt với SET PERSIST

| Lệnh | Đổi runtime ngay | Ghi persistent setting | Có hiệu lực sau restart |
|---|---:|---:|---:|
| SET GLOBAL | Có, nếu dynamic | Không | Không tự giữ |
| SET PERSIST | Có, nếu dynamic | Có | Có |
| SET PERSIST_ONLY | Không | Có | Có |

SET PERSIST_ONLY cũng có thể được dùng với một biến dynamic khi muốn chuẩn bị cấu hình cho lần restart mà chưa thay đổi hành vi hiện tại.

### 6.2. Vì sao cần SET PERSIST_ONLY?

Một số biến không thể thay đổi khi server đang chạy nhưng vẫn có thể được ghi vào persisted configuration. SET PERSIST_ONLY cho phép quản trị viên chuẩn bị giá trị cho lần khởi động tiếp theo mà không phải sửa trực tiếp option file.

Đây là cách phù hợp cho biến read-only có thể persist. Không phải mọi system variable đều được phép lưu; MySQL có danh sách và quy tắc riêng cho các biến không thể persist.

### 6.3. Kiểm tra trước khi restart

Sau SET PERSIST_ONLY, giá trị runtime vẫn là giá trị cũ:

~~~sql
SELECT @@GLOBAL.innodb_flush_method;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'innodb_flush_method';
~~~

Truy vấn thứ nhất đọc giá trị hiện tại. Truy vấn thứ hai xem giá trị đã lưu để khởi động sau. Hai kết quả có thể khác nhau trước khi restart.

## 7. Quyền cần có để thay đổi system variable

Thay đổi cấu hình global là thao tác quản trị. Không nên cấp quyền này cho tài khoản ứng dụng thông thường.

Trong MySQL 8.0, các dynamic privilege quan trọng gồm:

| Quyền | Mục đích |
|---|---|
| SYSTEM_VARIABLES_ADMIN | Cho phép SET GLOBAL và các thao tác SET PERSIST/SET PERSIST_ONLY trên biến không read-only theo quy tắc MySQL |
| PERSIST_RO_VARIABLES_ADMIN | Cho phép lưu biến read-only bằng SET PERSIST_ONLY |
| SUPER | Quyền quản trị cũ; đã deprecated và nhiều thao tác được tách thành dynamic privilege chuyên biệt |

Các dynamic privilege chuyên biệt được giới thiệu trong MySQL 8.0.14. SUPER vẫn xuất hiện trong một số hướng dẫn tương thích cũ nhưng đã bị deprecated; nên cấp quyền tối thiểu theo đúng thao tác cần thực hiện.

### 7.1. Cấp quyền SYSTEM_VARIABLES_ADMIN

Ví dụ cấp cho tài khoản vận hành:

~~~sql
GRANT SYSTEM_VARIABLES_ADMIN ON *.* TO 'ops_config'@'localhost';
~~~

Quyền này cho phép thực hiện các thao tác quản lý biến global trong phạm vi được MySQL hỗ trợ. Nó không có nghĩa tài khoản có thể thay đổi mọi biến read-only bằng SET GLOBAL.

### 7.2. Cấp quyền PERSIST_RO_VARIABLES_ADMIN

Nếu tài khoản cần lưu biến read-only cho lần khởi động sau:

~~~sql
GRANT PERSIST_RO_VARIABLES_ADMIN ON *.* TO 'ops_config'@'localhost';
~~~

Quyền này phục vụ trường hợp persist biến read-only bằng SET PERSIST_ONLY. SYSTEM_VARIABLES_ADMIN vẫn là quyền cần thiết cho các thao tác SET GLOBAL và persist biến không read-only; SUPER là quyền tương thích cũ có thể đáp ứng một số yêu cầu quản trị. Chỉ cấp quyền tối thiểu mà người vận hành thực sự cần.

### 7.3. Kiểm tra quyền của tài khoản

~~~sql
SHOW GRANTS FOR 'ops_config'@'localhost';
~~~

Nếu câu lệnh SET bị từ chối, kiểm tra quyền hiện có, phạm vi biến và thuộc tính dynamic/read-only. Không giải quyết mọi lỗi quyền bằng cách cấp SUPER cho tài khoản.

### 7.4. Tách tài khoản ứng dụng và tài khoản vận hành

Tài khoản ứng dụng thường chỉ cần quyền trên schema và đối tượng dữ liệu mà ứng dụng sử dụng. Tài khoản vận hành cấu hình cần được quản lý riêng, có audit, xác thực mạnh và quy trình phê duyệt theo chính sách tổ chức.

Không đặt SYSTEM_VARIABLES_ADMIN hoặc PERSIST_RO_VARIABLES_ADMIN vào tài khoản kết nối của ứng dụng chỉ để tránh lỗi SET trong một script triển khai.

## 8. Persisted configuration và mysqld-auto.cnf

Khi chạy SET PERSIST hoặc SET PERSIST_ONLY, MySQL ghi giá trị vào file persistent configuration có tên mysqld-auto.cnf trong data directory.

Đây là file JSON do MySQL tự quản lý. File chứa các giá trị đã persist cùng metadata liên quan. Nó được đọc khi server khởi động nếu persisted configuration được bật.

### 8.1. Không sửa mysqld-auto.cnf bằng tay

Không chỉnh sửa, định dạng lại, xóa một phần hoặc tạo file này bằng trình soạn thảo văn bản. Dùng SET PERSIST, SET PERSIST_ONLY và RESET PERSIST để quản lý nội dung.

Sửa file trực tiếp có thể làm mất metadata, tạo JSON không hợp lệ hoặc gây khác biệt giữa cấu hình runtime và cấu hình startup. Nếu cần backup, thực hiện theo quy trình backup data directory và quản lý cấu hình của hệ thống.

### 8.2. Xem các giá trị đã persist

Performance Schema cung cấp bảng persisted_variables:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
ORDER BY VARIABLE_NAME;
~~~

Lọc một biến cụ thể:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Bảng này phản ánh các giá trị persistent đã lưu. Nó không thay thế SHOW GLOBAL VARIABLES khi cần biết giá trị runtime hiện tại.

### 8.3. So sánh giá trị runtime và persistent

~~~sql
SELECT @@GLOBAL.max_connections AS runtime_value;

SELECT VARIABLE_VALUE AS persisted_value
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Hai giá trị có thể khác nhau nếu dùng SET PERSIST_ONLY, nếu runtime đã được thay đổi sau đó bằng SET GLOBAL, hoặc nếu persisted configuration chưa được nạp trong tiến trình hiện tại.

### 8.4. Kiểm tra nguồn cấu hình

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

Kết quả giúp điều tra giá trị hiện tại được lấy từ đâu và thay đổi động gần nhất do ai thực hiện khi metadata có sẵn. Đây là công cụ hữu ích để phát hiện cấu hình bị ghi đè giữa option file và persisted setting.

## 9. Cấu hình nào thắng sau khi MySQL khởi động?

MySQL nạp cấu hình từ nhiều nguồn theo thứ tự. Đối với các nguồn thường gặp, persisted setting được nạp sau option file và trước command-line option. Vì vậy:

- Giá trị trong mysqld-auto.cnf có thể ghi đè giá trị cùng biến trong my.cnf.
- Giá trị truyền trực tiếp trên command line có ưu tiên cao hơn persisted setting.
- Nếu không có override, server dùng giá trị được nạp từ option file hoặc giá trị mặc định.

Có thể hình dung thứ tự ưu tiên thường gặp từ thấp đến cao:

~~~text
Giá trị mặc định
    ↓
Option file (my.cnf / my.ini)
    ↓
Persisted configuration (mysqld-auto.cnf)
    ↓
Command-line option của mysqld
~~~

Thứ tự cụ thể còn phụ thuộc cách khởi động và những nguồn cấu hình được cung cấp. Hãy kiểm tra cách service hoặc container khởi chạy mysqld trước khi kết luận nguồn nào đang thắng.

### 9.1. Ví dụ cấu hình bị ghi đè

Giả sử option file có:

~~~ini
[mysqld]
max_connections = 200
~~~

Sau đó quản trị viên chạy:

~~~sql
SET PERSIST max_connections = 400;
~~~

Runtime chuyển thành 400 và persisted configuration lưu 400. Sau restart, persisted setting được nạp sau option file nên giá trị 400 tiếp tục có hiệu lực.

Nếu sau đó đội vận hành đổi my.cnf thành 250 nhưng không xóa persisted setting, giá trị 400 vẫn có thể thắng. Đây là một dạng configuration drift: file cấu hình được quản lý nói 250 nhưng server vẫn chạy 400.

### 9.2. Khi nào nên dùng option file?

Ưu tiên option file hoặc công cụ quản lý cấu hình tập trung khi:

- Muốn cấu hình được version control và review.
- Cần áp dụng nhất quán trên nhiều máy chủ.
- Cần tái tạo môi trường từ image hoặc automation.
- Quy trình triển khai yêu cầu mọi thay đổi startup phải qua change management.

SET PERSIST phù hợp cho thao tác quản trị có kiểm soát trên một server, nhưng phải ghi nhận thay đổi vào nguồn cấu hình chuẩn của tổ chức nếu chính sách yêu cầu.

### 9.3. Kiểm tra các option file được đọc

Có thể dùng chương trình client hoặc server option inspection để xem các file cấu hình và nhóm option được đọc. Ví dụ trên hệ thống có MySQL client:

~~~bash
mysql --help
~~~

Phần đầu output của client cho biết thứ tự các option file mà client đọc. Đường dẫn và cách service khởi chạy server có thể khác với client; kiểm tra cấu hình service hoặc tham số mysqld riêng khi điều tra server.

## 10. RESET PERSIST: xóa override đã lưu

RESET PERSIST xóa một giá trị khỏi persistent configuration. Nó không tương đương với SET GLOBAL và cũng không tự khôi phục giá trị runtime hiện tại.

Cú pháp xóa một biến:

~~~sql
RESET PERSIST max_connections;
~~~

Nếu muốn bỏ qua trường hợp biến chưa có trong persistent configuration:

~~~sql
RESET PERSIST IF EXISTS max_connections;
~~~

Có thể xóa toàn bộ persistent settings:

~~~sql
RESET PERSIST;
~~~

> RESET PERSIST không xóa biến khỏi option file hoặc command line. Nó chỉ xóa override do MySQL lưu trong persisted configuration.

### 10.1. Runtime không tự quay về giá trị cũ

Giả sử đã chạy:

~~~sql
SET PERSIST max_connections = 400;
~~~

Sau đó chạy:

~~~sql
RESET PERSIST max_connections;
~~~

Giá trị runtime hiện tại vẫn có thể là 400. Lệnh RESET PERSIST chỉ loại bỏ giá trị persistent. Muốn thay đổi runtime ngay, cần chạy SET GLOBAL với giá trị mong muốn:

~~~sql
SET GLOBAL max_connections = 200;
~~~

Nếu option file cũng đặt 200, sau lần restart tiếp theo giá trị 200 sẽ được nạp từ option file. Nếu không có nguồn cấu hình nào đặt giá trị, server sẽ dùng nguồn cấu hình còn lại theo thứ tự ưu tiên.

### 10.2. Xóa toàn bộ persistent settings cần thận trọng

RESET PERSIST không có tên biến sẽ xóa toàn bộ persistent setting. Điều này có thể làm nhiều cấu hình vận hành biến mất sau lần restart tiếp theo.

Trước khi dùng, hãy liệt kê persisted_variables và xác định từng override. Trong vận hành thường ngày, ưu tiên xóa đúng biến cần thay đổi thay vì xóa toàn bộ.

### 10.3. Xác minh sau RESET PERSIST

~~~sql
RESET PERSIST IF EXISTS max_connections;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';

SELECT @@GLOBAL.max_connections;
~~~

Truy vấn persisted_variables không còn hàng tương ứng nếu override đã được xóa. Giá trị @@GLOBAL.max_connections phản ánh runtime và có thể vẫn giữ giá trị vừa được SET trước đó.

## 11. Khởi động lại và nạp persistent setting

SET PERSIST_ONLY không đổi runtime. Để giá trị đã lưu có hiệu lực, cần khởi động lại MySQL theo quy trình vận hành của môi trường.

### 11.1. Vai trò của persisted_globals_load

MySQL có biến startup persisted_globals_load để điều khiển việc nạp các giá trị từ mysqld-auto.cnf. Mặc định, persisted configuration được nạp khi khởi động.

Nếu cần khởi động server mà bỏ qua các persisted setting, có thể dùng startup option:

~~~bash
mysqld --persisted-globals-load=OFF
~~~

Đây là công cụ phục hồi khi một persisted setting gây vấn đề lúc startup hoặc khi cần chẩn đoán cấu hình. Cách truyền option thực tế phải phù hợp với service manager, container entrypoint hoặc hệ thống quản lý MySQL. Không khởi chạy thêm một tiến trình mysqld thứ hai trên cùng data directory.

### 11.2. Tắt nạp persisted setting không xóa file

Khi persisted_globals_load bị tắt, MySQL bỏ qua các giá trị trong mysqld-auto.cnf khi nạp cấu hình startup. File vẫn tồn tại; các giá trị đã lưu không tự bị xóa.

Sau khi server khởi động bằng chế độ bỏ qua persistent settings:

1. Kết nối bằng tài khoản quản trị phù hợp.
2. Kiểm tra performance_schema.persisted_variables.
3. Xác định biến gây lỗi hoặc cấu hình không phù hợp.
4. Dùng RESET PERSIST để xóa đúng override hoặc cập nhật giá trị hợp lệ.
5. Khởi động lại theo cấu hình bình thường và xác minh.

Không giữ persisted_globals_load=OFF như giải pháp lâu dài nếu hệ thống dựa vào persistent configuration cho các giá trị startup.

### 11.3. Quy trình kiểm tra sau restart

Sau khi server khởi động:

~~~sql
SELECT @@GLOBAL.max_connections;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';

SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

Ba truy vấn lần lượt kiểm tra giá trị runtime, giá trị đã persist và nguồn cấu hình được MySQL ghi nhận. Nếu giá trị runtime khác giá trị persistent, kiểm tra command line, option file, khả năng persist và trạng thái nạp persisted configuration.

## 12. SET GLOBAL, SET PERSIST và SET PERSIST_ONLY trong quy trình vận hành

Hãy chọn lệnh theo mục tiêu thay đổi:

| Mục tiêu | Lệnh phù hợp | Cần restart? |
|---|---|---|
| Thử thay đổi runtime cho biến dynamic | SET GLOBAL | Không |
| Thay đổi runtime và giữ qua restart | SET PERSIST | Không để có hiệu lực runtime; restart để xác minh startup |
| Chuẩn bị giá trị cho lần khởi động sau | SET PERSIST_ONLY | Có |
| Xóa một persisted override | RESET PERSIST variable | Không để xóa file; restart để xác minh nguồn fallback |
| Chỉ đổi một kết nối | SET SESSION | Không |
| Quản lý cấu hình chuẩn cho nhiều máy chủ | Option file/configuration management | Theo yêu cầu của biến |

### 12.1. Ví dụ điều chỉnh biến dynamic và lưu lâu dài

Giả sử sau khi kiểm thử, nhóm vận hành quyết định tăng max_connections từ 200 lên 300:

~~~sql
-- Kiểm tra hiện trạng.
SELECT @@GLOBAL.max_connections AS before_value;

-- Thay đổi runtime và lưu cho lần khởi động sau.
SET PERSIST max_connections = 300;

-- Xác nhận runtime.
SELECT @@GLOBAL.max_connections AS runtime_value;

-- Xác nhận persisted setting.
SELECT VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Sau khi restart theo change window, kiểm tra lại runtime và nguồn cấu hình. Đồng thời theo dõi số kết nối, memory usage, connection errors và độ trễ ứng dụng.

### 12.2. Ví dụ chuẩn bị biến startup-only

Giả sử nhóm vận hành đã kiểm tra nền tảng và quyết định thay đổi innodb_flush_method ở lần restart kế tiếp:

~~~sql
-- Giá trị hiện tại vẫn được sử dụng trong tiến trình đang chạy.
SELECT @@GLOBAL.innodb_flush_method AS runtime_value;

-- Chỉ ghi giá trị mới vào persistent configuration.
SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT';

-- So sánh runtime với giá trị đã lưu.
SELECT @@GLOBAL.innodb_flush_method AS current_runtime;

SELECT VARIABLE_VALUE AS next_startup_value
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'innodb_flush_method';
~~~

Sau khi kiểm tra tương thích hệ điều hành và lên lịch restart, server sẽ nạp giá trị persistent. Nếu giá trị không được hỗ trợ trên nền tảng, cần sửa hoặc xóa override trước khi khởi động lại bình thường.

### 12.3. Ví dụ rollback một thay đổi persistent

Giả sử giá trị ban đầu là 200, sau đó đã SET PERSIST thành 300. Nếu quyết định quay lại 200 và tiếp tục giữ cấu hình qua restart:

~~~sql
SET PERSIST max_connections = 200;
~~~

Nếu muốn xóa override persistent và để option file/default quyết định giá trị startup:

~~~sql
RESET PERSIST IF EXISTS max_connections;
SET GLOBAL max_connections = 200;
~~~

Thay đổi runtime và thay đổi persistent là hai trạng thái riêng. Xác nhận cả hai sau rollback.

## 13. Phiên bản MySQL và khả năng tương thích

SET PERSIST và SET PERSIST_ONLY được giới thiệu trong MySQL 8.0.11. Các dynamic privilege chuyên biệt như SYSTEM_VARIABLES_ADMIN và PERSIST_RO_VARIABLES_ADMIN có từ MySQL 8.0.14.

| Khả năng | Phiên bản |
|---|---|
| SET PERSIST và SET PERSIST_ONLY | MySQL 8.0.11 trở lên |
| RESET PERSIST | MySQL 8.0.11 trở lên |
| SYSTEM_VARIABLES_ADMIN và PERSIST_RO_VARIABLES_ADMIN | MySQL 8.0.14 trở lên |
| performance_schema.persisted_variables | MySQL 8.0.11 trở lên |
| performance_schema.variables_info | MySQL 8.0.16 trở lên |

Nếu ứng dụng hoặc automation còn hỗ trợ MySQL 5.7, không thể dùng SET PERSIST/SET PERSIST_ONLY trên phiên bản đó. Hãy dùng option file hoặc công cụ quản lý cấu hình cho startup value và SET GLOBAL cho thay đổi runtime được hỗ trợ.

### 13.1. Kiểm tra phiên bản trước khi chạy

~~~sql
SELECT VERSION() AS mysql_version;
~~~

Không chỉ kiểm tra phiên bản major. Hãy xác định đúng minor release và đọc tài liệu của phiên bản server thực tế, vì system variable có thể được thêm, đổi tên, deprecated hoặc thay đổi thuộc tính dynamic qua các bản phát hành.

### 13.2. Không phải mọi biến đều persist được

MySQL giới hạn các biến có thể ghi vào persisted configuration. Một số biến phụ thuộc tiến trình, đường dẫn, môi trường hoặc trạng thái khởi tạo của data directory không thể persist theo cách thông thường.

Nếu SET PERSIST hoặc SET PERSIST_ONLY từ chối biến, đọc thông báo lỗi và tài liệu của biến đó. Không tìm cách vượt qua bằng cách sửa mysqld-auto.cnf thủ công.

## 14. Persistent setting không tự nhân bản sang server khác

Persistent configuration là trạng thái cục bộ của từng MySQL Server instance. SET PERSIST và SET PERSIST_ONLY không phải cơ chế phân phối cấu hình cho toàn bộ replication topology.

Nếu có primary và replicas:

- Thay đổi runtime trên primary không tự bảo đảm các replicas có cùng system variable.
- Giá trị ghi trong mysqld-auto.cnf của một node không tự xuất hiện trên node khác.
- Cần áp dụng cấu hình riêng trên từng instance theo vai trò và yêu cầu tải.
- Có thể dùng configuration management để triển khai cùng một thay đổi có kiểm soát.

Ví dụ, tăng max_connections trên primary không có nghĩa replica cũng tự tăng. Replica có thể có workload đọc khác, giới hạn tài nguyên khác hoặc cần giá trị riêng.

### 14.1. Lập inventory cấu hình theo node

Một bảng vận hành đơn giản có thể ghi:

| Node | Vai trò | Biến | Runtime | Persisted | Nguồn chuẩn |
|---|---|---|---:|---:|---|
| db-primary-1 | Primary | max_connections | 300 | 300 | Config management |
| db-replica-1 | Replica | max_connections | 250 | 250 | Config management |
| db-replica-2 | Replica | max_connections | 250 | 250 | Config management |

Các giá trị trên chỉ là ví dụ minh họa. Điều quan trọng là ghi nhận runtime và persisted riêng biệt, đồng thời biết nguồn cấu hình chuẩn của từng node.

### 14.2. Thay đổi đồng bộ theo topology

Trước khi triển khai:

1. Xác định biến có cần cùng giá trị trên tất cả node hay không.
2. Xác định node nào cần thay đổi trước.
3. Kiểm tra giới hạn tài nguyên riêng của từng node.
4. Áp dụng qua công cụ quản lý cấu hình hoặc thao tác được phê duyệt trên từng node.
5. Xác minh runtime, persisted value và nguồn cấu hình sau triển khai.

Không giả định một câu lệnh SET PERSIST chạy trên primary sẽ được binary log phát tới replicas.

## 15. Lỗi thường gặp và cách khắc phục

### 15.1. SET GLOBAL báo biến không dynamic

**Nguyên nhân:** biến chỉ được thiết lập khi khởi động hoặc là read-only.

**Cách xử lý:** xác minh biến có thể persist không. Nếu được phép, dùng SET PERSIST_ONLY để chuẩn bị giá trị startup; nếu không, cập nhật option file hoặc phương thức khởi động được hỗ trợ.

### 15.2. SET PERSIST báo không có quyền

**Nguyên nhân:** tài khoản thiếu SYSTEM_VARIABLES_ADMIN hoặc quyền phù hợp.

**Cách xử lý:** kiểm tra SHOW GRANTS và cấp dynamic privilege tối thiểu qua quy trình quản trị. Không cấp SUPER theo phản xạ.

### 15.3. SET PERSIST_ONLY với biến read-only bị từ chối

**Nguyên nhân:** thiếu PERSIST_RO_VARIABLES_ADMIN hoặc biến không nằm trong nhóm được phép persist.

**Cách xử lý:** kiểm tra quyền và tài liệu của biến. Không phải mọi biến read-only đều có thể lưu persistent.

### 15.4. Giá trị sau restart khác giá trị đã SET PERSIST

**Nguyên nhân có thể gồm:**

- Command-line option ghi đè persisted setting.
- Persisted configuration không được nạp.
- Giá trị đã bị RESET PERSIST hoặc thay đổi sau đó.
- Service khởi động một instance khác hoặc dùng data directory khác.
- Biến không được persist theo quy tắc của MySQL.

**Cách xử lý:** kiểm tra @@GLOBAL.variable, performance_schema.persisted_variables, performance_schema.variables_info, tham số service và data directory.

### 15.5. Sửa my.cnf nhưng server vẫn giữ giá trị cũ

**Nguyên nhân:** persisted setting trong mysqld-auto.cnf được nạp sau option file và ghi đè giá trị trong my.cnf.

**Cách xử lý:** kiểm tra persisted_variables. Nếu muốn option file trở thành nguồn quyết định, dùng RESET PERSIST cho đúng biến rồi restart hoặc cập nhật persisted value theo chính sách.

### 15.6. RESET PERSIST nhưng runtime không đổi

**Nguyên nhân:** RESET PERSIST chỉ xóa cấu hình đã lưu, không thay đổi biến đang chạy.

**Cách xử lý:** nếu cần đổi runtime ngay, dùng SET GLOBAL với giá trị mong muốn. Sau đó kiểm tra nguồn cấu hình startup để xác nhận giá trị sau restart.

### 15.7. SET PERSIST_ONLY thành công nhưng hành vi hiện tại không đổi

**Nguyên nhân:** lệnh chỉ ghi giá trị cho lần khởi động tiếp theo.

**Cách xử lý:** kiểm tra persisted_variables để xác nhận giá trị đã lưu, lên lịch restart và xác minh sau khi server hoạt động trở lại.

### 15.8. Server không khởi động sau khi persist giá trị

**Nguyên nhân:** giá trị không hợp lệ, không được nền tảng hỗ trợ hoặc gây lỗi trong quá trình khởi tạo.

**Cách xử lý phục hồi:**

1. Dùng quy trình khởi động có kiểm soát của hệ thống.
2. Nếu cần, khởi động với persisted_globals_load=OFF để bỏ qua persisted settings.
3. Kết nối và kiểm tra các giá trị đã lưu.
4. RESET PERSIST đúng biến gây lỗi hoặc đặt giá trị hợp lệ.
5. Khởi động lại ở chế độ bình thường và xác minh.

Không xóa hoặc chỉnh mysqld-auto.cnf bằng tay như bước xử lý đầu tiên.

## 16. Quy trình thay đổi cấu hình an toàn

Một thay đổi system variable nên có trạng thái trước, thay đổi, xác minh và rollback rõ ràng.

### 16.1. Trước khi thay đổi

1. Xác định đúng MySQL instance và phiên bản.
2. Đọc tài liệu của biến: scope, dynamic/read-only, type, range và default.
3. Ghi lại giá trị runtime hiện tại.
4. Kiểm tra option file, persisted value và command-line override.
5. Đánh giá tác động tới CPU, RAM, disk, connection và workload.
6. Xác định nguồn cấu hình chuẩn và quyền người thực hiện.
7. Thử trên staging hoặc một node đại diện nếu có thể.

### 16.2. Khi thay đổi

Chọn một phương thức theo mục tiêu:

- Thử runtime: SET GLOBAL.
- Đổi runtime và lưu qua restart: SET PERSIST.
- Chuẩn bị giá trị startup-only: SET PERSIST_ONLY.
- Quản lý đồng bộ bằng cấu hình chuẩn: cập nhật option file/configuration management theo change process.

Ghi nhận câu lệnh, người thực hiện, thời gian, giá trị trước/sau và lý do thay đổi.

### 16.3. Sau khi thay đổi

~~~sql
SELECT
    @@GLOBAL.max_connections AS runtime_value;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';

SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH,
    SET_TIME,
    SET_USER,
    SET_HOST
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

Sau đó theo dõi:

- Error log của MySQL.
- Số kết nối và số lần từ chối kết nối.
- Memory usage và swap.
- CPU, I/O latency và throughput.
- Query latency, lock wait và connection pool.
- Hành vi của ứng dụng sau khi cấu hình có hiệu lực.

### 16.4. Rollback

Rollback cần khôi phục cả runtime lẫn nguồn startup:

- Nếu chỉ dùng SET GLOBAL, đặt lại runtime value đã ghi nhận.
- Nếu dùng SET PERSIST, persist lại giá trị cũ hoặc RESET PERSIST rồi đặt runtime theo nguồn chuẩn.
- Nếu dùng SET PERSIST_ONLY, RESET PERSIST giá trị mới trước khi restart hoặc persist giá trị cũ.
- Nếu dùng option file, khôi phục file cấu hình chuẩn và restart theo quy trình.

Đừng chỉ nhìn giá trị hiện tại rồi kết luận rollback hoàn tất. Phải xác minh cả giá trị runtime, persisted value và nguồn cấu hình sau restart.

## 17. Thực hành: quản lý max_connections qua các trạng thái

Bài thực hành minh họa sự khác nhau giữa runtime và persistent setting. Thực hiện trên môi trường thử nghiệm với tài khoản có quyền phù hợp; không thay đổi giới hạn kết nối của production chỉ để làm bài tập.

### 17.1. Ghi nhận hiện trạng

~~~sql
SELECT
    VERSION() AS mysql_version,
    @@GLOBAL.max_connections AS runtime_value;

SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';

SELECT
    VARIABLE_NAME,
    VARIABLE_SOURCE,
    VARIABLE_PATH
FROM performance_schema.variables_info
WHERE VARIABLE_NAME = 'max_connections';
~~~

Ghi lại runtime value, persisted value nếu có và nguồn cấu hình. Nếu không có persisted row, biến có thể đang lấy giá trị từ option file, command line hoặc default.

### 17.2. Thử SET GLOBAL trong môi trường lab

~~~sql
SET GLOBAL max_connections = 250;

SELECT @@GLOBAL.max_connections;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Quan sát runtime thay đổi nhưng persisted value không tự được tạo hoặc cập nhật bởi SET GLOBAL.

### 17.3. Thử SET PERSIST

~~~sql
SET PERSIST max_connections = 280;

SELECT @@GLOBAL.max_connections;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Quan sát runtime và persisted value cùng được cập nhật. Ghi lại thay đổi để có thể rollback sau bài tập.

### 17.4. Thử RESET PERSIST

~~~sql
RESET PERSIST IF EXISTS max_connections;

SELECT @@GLOBAL.max_connections;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'max_connections';
~~~

Xác nhận persisted row đã bị xóa trong khi runtime có thể vẫn là giá trị đã SET. Dùng SET GLOBAL để đưa runtime về giá trị phù hợp với môi trường lab.

### 17.5. Thực hành SET PERSIST_ONLY

Chỉ thực hiện phần này nếu có quyền phù hợp, môi trường tương thích và một biến startup-only đã được chọn theo tài liệu chính thức. Không chọn giá trị tùy ý cho biến ảnh hưởng đến data directory hoặc khả năng khởi động.

~~~sql
SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT';

SELECT @@GLOBAL.innodb_flush_method;

SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.persisted_variables
WHERE VARIABLE_NAME = 'innodb_flush_method';
~~~

Xác nhận giá trị runtime chưa đổi nhưng persisted value đã được ghi. Sau đó xóa override nếu không định restart lab với cấu hình này:

~~~sql
RESET PERSIST IF EXISTS innodb_flush_method;
~~~

## 18. Bài tập và câu hỏi tự kiểm tra

### 18.1. Chọn lệnh phù hợp

Với từng yêu cầu, chọn SET GLOBAL, SET PERSIST, SET PERSIST_ONLY, SET SESSION hay option file:

1. Thay đổi long_query_time trong session hiện tại để điều tra một truy vấn.
2. Tăng max_connections ngay lập tức và giữ giá trị sau restart.
3. Chuẩn bị một biến read-only cho lần khởi động tiếp theo.
4. Thử một giá trị dynamic trong 15 phút rồi hoàn nguyên.
5. Triển khai cùng cấu hình trên 20 máy chủ bằng hệ thống quản lý cấu hình.

### 18.2. Phân tích giá trị sau restart

Option file đặt max_connections = 200. Một quản trị viên chạy SET PERSIST max_connections = 400. Sau đó option file được đổi thành 250 nhưng không xóa persisted setting.

- Giá trị nào có thể có hiệu lực sau restart?
- Vì sao thay đổi option file không thắng?
- Cần làm gì để option file trở thành nguồn quyết định?

### 18.3. Phân biệt runtime và persistent

Sau khi chạy SET PERSIST_ONLY innodb_flush_method = 'O_DIRECT':

- Giá trị runtime có thay đổi ngay không?
- Bảng nào cho biết giá trị đã lưu?
- Khi nào giá trị mới được nạp?
- Cần kiểm tra gì trước khi restart?

### 18.4. Thiết kế rollback

Một thay đổi SET PERSIST làm ứng dụng tăng số kết nối lỗi. Viết quy trình rollback gồm:

- Giá trị runtime cần khôi phục.
- Cách xử lý persisted setting.
- Cách xác minh option file/command line.
- Các metric cần theo dõi sau rollback.

### 18.5. Quyền tối thiểu

Giải thích vì sao tài khoản chỉ cần SET GLOBAL cho một biến dynamic không nên mặc nhiên được cấp PERSIST_RO_VARIABLES_ADMIN hoặc SUPER.

### 18.6. Câu hỏi tự kiểm tra

1. SET GLOBAL khác SET PERSIST ở điểm nào?
2. SET PERSIST_ONLY thay đổi trạng thái nào?
3. Vì sao SET GLOBAL không đảm bảo giá trị tồn tại qua restart?
4. Một biến có GLOBAL và SESSION scope sẽ ảnh hưởng các kết nối hiện tại thế nào khi global value thay đổi?
5. SET PERSIST có thể dùng để lưu session variable không?
6. mysqld-auto.cnf được lưu ở đâu và ai quản lý nội dung?
7. Vì sao không nên sửa mysqld-auto.cnf bằng tay?
8. RESET PERSIST có khôi phục runtime value không?
9. persisted setting có ưu tiên cao hơn option file không?
10. Command-line option có thể ghi đè persisted setting không?
11. persisted_globals_load=OFF có xóa mysqld-auto.cnf không?
12. Vì sao thay đổi SET PERSIST trên primary không tự cấu hình các replica?
13. Khi nào dùng option file thay cho SET PERSIST?
14. Cần xác minh những gì sau khi restart?

## 19. Checklist trước khi thay đổi system variable

- [ ] Đã xác định đúng MySQL instance và phiên bản.
- [ ] Đã đọc tài liệu của biến và xác định GLOBAL/SESSION scope.
- [ ] Đã xác định biến dynamic hay read-only/startup-only.
- [ ] Đã kiểm tra kiểu dữ liệu, miền giá trị và giá trị mặc định.
- [ ] Đã ghi lại runtime value trước khi thay đổi.
- [ ] Đã kiểm tra option file, persisted_variables và command-line option.
- [ ] Đã xác định nguồn cấu hình chuẩn của tổ chức.
- [ ] Đã đánh giá tác động tới RAM, CPU, I/O, kết nối và workload.
- [ ] Đã thử trên staging hoặc node đại diện khi có thể.
- [ ] Dùng SET GLOBAL chỉ cho thay đổi runtime.
- [ ] Dùng SET PERSIST khi cần runtime và persistent value.
- [ ] Dùng SET PERSIST_ONLY cho thay đổi startup được phép persist.
- [ ] Đã xác nhận quyền SYSTEM_VARIABLES_ADMIN hoặc PERSIST_RO_VARIABLES_ADMIN phù hợp.
- [ ] Không cấp SUPER rộng hơn nhu cầu.
- [ ] Không sửa mysqld-auto.cnf bằng tay.
- [ ] Đã kiểm tra persisted_globals_load và thứ tự ưu tiên cấu hình.
- [ ] Đã xác định cách áp dụng trên từng node trong replication topology.
- [ ] Đã ghi nhận câu lệnh, người thực hiện, thời gian và lý do thay đổi.
- [ ] Đã chuẩn bị rollback cho cả runtime và persistent state.
- [ ] Đã xác minh giá trị runtime, persisted value và VARIABLE_SOURCE sau thay đổi.
- [ ] Đã kiểm tra error log và metric sau restart.

## Kết luận

SET GLOBAL thay đổi runtime của biến global dynamic nhưng không tự lưu qua restart. SET PERSIST vừa thay đổi runtime vừa ghi giá trị vào persisted configuration. SET PERSIST_ONLY chỉ ghi giá trị cho lần khởi động sau, phù hợp với biến startup-only hoặc khi muốn trì hoãn hiệu lực. RESET PERSIST xóa override đã lưu nhưng không tự đổi giá trị runtime.

MySQL lưu persistent setting trong mysqld-auto.cnf và nạp chúng sau option file, trước command-line option. Vì vậy, quản trị viên phải theo dõi cả giá trị runtime lẫn nguồn startup, cấp dynamic privilege tối thiểu, áp dụng cấu hình riêng cho từng server và có phương án phục hồi khi một giá trị làm server khởi động lỗi. Chọn đúng lệnh chỉ là bước đầu; thay đổi chỉ hoàn tất khi đã đo tác động và xác minh trạng thái sau restart.

