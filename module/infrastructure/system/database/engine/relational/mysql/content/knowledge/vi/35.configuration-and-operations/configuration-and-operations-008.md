# Thread/table cache, open_files_limit và giới hạn hệ điều hành

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Khi vận hành MySQL, các giới hạn về thread, table cache và file descriptor ảnh hưởng trực tiếp đến khả năng nhận kết nối, mở bảng và duy trì tải đồng thời. Một cấu hình có thể chạy tốt ở môi trường thử nghiệm nhưng gặp lỗi khi số kết nối, số bảng, số partition hoặc số file tăng lên.

Bài này tập trung vào ba nhóm tài nguyên có liên quan nhưng không thay thế lẫn nhau:

- **Thread cache** giữ lại thread đã phục vụ kết nối để tái sử dụng, giảm chi phí tạo thread khi kết nối đến rồi ngắt liên tục.
- **Table cache** giữ các table instance và table definition để giảm thao tác mở bảng, đọc metadata và tranh chấp khi nhiều session truy cập.
- **open_files_limit** và giới hạn hệ điều hành quyết định số file descriptor mà tiến trình mysqld có thể sử dụng.

Mục tiêu vận hành là đo đúng dấu hiệu nghẽn, hiểu giới hạn hiệu lực của server và hệ điều hành, thay đổi có kiểm soát, sau đó xác nhận bằng status, log và tải đại diện. Không nên tăng mọi biến lên mức lớn nhất: cache quá lớn có thể tiêu thụ RAM và file descriptor, làm tăng áp lực lên hệ thống.

## 1. Bức tranh tài nguyên của mysqld

MySQL server xử lý kết nối, câu lệnh SQL, table metadata, data file, redo/undo, binary log, temporary file, socket và nhiều loại file khác. Những tài nguyên này có giới hạn khác nhau:

| Tài nguyên | Vai trò | Cấu hình hoặc giới hạn liên quan |
|---|---|---|
| Thread phục vụ kết nối | Thực thi công việc của session | thread_cache_size, max_connections, thread_handling |
| Table instance cache | Giữ bảng đang mở để tái sử dụng | table_open_cache, table_open_cache_instances |
| Table definition cache | Giữ định nghĩa bảng trong bộ nhớ | table_definition_cache |
| File descriptor | Mở table file, log, socket và file nội bộ | open_files_limit, giới hạn tiến trình của OS |
| Kết nối đồng thời | Số client được server chấp nhận | max_connections, giới hạn tài nguyên |
| Bộ nhớ | Thread, table metadata, buffer, session và cache | RAM, cấu hình MySQL, workload |

Không có một biến duy nhất điều khiển tất cả. Ví dụ:

- Tăng thread_cache_size không làm tăng max_connections.
- Tăng table_open_cache không tự nâng giới hạn file descriptor của hệ điều hành.
- Tăng open_files_limit không tự tăng table_open_cache.
- table_definition_cache không phải là table_open_cache.
- Thread cache không giới hạn số thread đang chạy đồng thời.

Khi điều tra, hãy xác định chính xác lớp tài nguyên nào đang thiếu trước khi sửa cấu hình.

## 2. Thread cache hoạt động như thế nào?

Trong mô hình mặc định one-thread-per-connection, một kết nối client được phục vụ bởi một thread phía server. Khi client ngắt kết nối, thread có thể được đưa vào thread cache để tái sử dụng cho kết nối mới. Nếu cache không còn chỗ hoặc bị tắt, thread được giải phóng; kết nối mới sau đó có thể khiến server tạo thread mới.

Thread cache giúp giảm chi phí tạo và hủy thread khi ứng dụng có connection churn cao. Nó không giữ kết nối client sống và không phải connection pool.

### 2.1. Phân biệt thread cache và connection pool

| Cơ chế | Nằm ở đâu | Giải quyết vấn đề gì? |
|---|---|---|
| Connection pool | Ứng dụng hoặc proxy | Tái sử dụng kết nối client, giới hạn số kết nối mở tới server |
| Thread cache | MySQL server | Tái sử dụng thread server sau khi session đóng |
| max_connections | MySQL server | Giới hạn số client connection đồng thời |
| Thread pool plugin | Cơ chế lập lịch thread chuyên biệt nếu được cài và hỗ trợ | Điều phối nhiều session lên một nhóm thread worker |

Nếu ứng dụng đã dùng pool với số kết nối ổn định, số lần tạo thread mới có thể thấp. Trong trường hợp đó, tăng thread_cache_size có thể không đem lại lợi ích rõ rệt. Nếu ứng dụng liên tục mở rồi đóng kết nối, thread cache có thể hữu ích hơn.

### 2.2. thread_cache_size

thread_cache_size là số thread tối đa MySQL giữ lại để phục vụ kết nối mới. Giá trị 0 tắt cache. Biến này có phạm vi GLOBAL và có thể thay đổi khi server đang chạy.

Kiểm tra cấu hình:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_cache_size';
SHOW GLOBAL VARIABLES LIKE 'max_connections';
~~~

Kiểm tra hoạt động:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Connections',
    'Threads_created',
    'Threads_cached',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections'
);
~~~

Ý nghĩa các chỉ số:

- **Threads_cached:** số thread hiện đang nằm trong cache và sẵn sàng tái sử dụng.
- **Threads_created:** tổng số thread MySQL đã tạo để phục vụ kết nối kể từ khi server khởi động.
- **Threads_connected:** số kết nối hiện đang mở.
- **Threads_running:** số thread không ở trạng thái ngủ, đang thực hiện công việc hoặc chờ xử lý.
- **Connections:** số lần client cố gắng kết nối đến server kể từ khi server khởi động.
- **Max_used_connections:** số kết nối đồng thời cao nhất kể từ khi server khởi động.

Threads_created là bộ đếm tích lũy, không phải số thread đang chạy. Threads_cached là số hiện tại, không phải tổng số thread từng được cache.

### 2.3. Đánh giá nhu cầu cache thread

Lấy hai mẫu status cách nhau một khoảng thời gian có tải đại diện. So sánh mức tăng của Threads_created với mức tăng Connections:

~~~text
delta_threads_created = Threads_created_moi - Threads_created_cu
delta_connections    = Connections_moi - Connections_cu

ty_le_tao_thread = delta_threads_created / delta_connections
~~~

Tỷ lệ cao trong giai đoạn có nhiều kết nối mới có thể cho thấy server thường xuyên phải tạo thread. Tỷ lệ thấp cho thấy thread được tái sử dụng hoặc kết nối được giữ ổn định. Đây là tín hiệu chẩn đoán, không phải ngưỡng pass/fail phổ quát.

Không đánh giá thread cache chỉ từ một snapshot. Cần xem:

- Tốc độ mở/đóng kết nối của ứng dụng.
- Số kết nối đang mở và số kết nối tối đa đã đạt.
- CPU và độ trễ khi tạo kết nối.
- Thời gian sống trung bình của session.
- Hành vi của connection pool hoặc proxy.

### 2.4. Chọn thread_cache_size

Chọn giá trị dựa trên connection churn và khả năng tài nguyên. Có thể bắt đầu với giá trị nhỏ đến vừa, quan sát trong giờ cao điểm, sau đó tăng từng bước nếu Threads_created vẫn tăng nhanh so với Connections và việc tạo thread thực sự là chi phí đáng kể.

Ví dụ thay đổi runtime:

~~~sql
SET GLOBAL thread_cache_size = 64;
~~~

Giá trị 64 chỉ minh họa cú pháp, không phải khuyến nghị áp dụng cho mọi server. Nếu muốn giữ sau restart, hãy lưu vào cấu hình được quản lý hoặc dùng SET PERSIST trên phiên bản hỗ trợ và sau khi kiểm tra chính sách cấu hình của môi trường.

Không đặt thread_cache_size bằng max_connections một cách máy móc. Cache chỉ giữ thread đã rảnh; kích thước lớn hơn nhu cầu không tự làm truy vấn nhanh hơn.

## 3. Table cache và table definition cache

MySQL phải mở bảng và nạp định nghĩa bảng khi xử lý truy vấn. Để tránh lặp lại công việc này, server duy trì các cache:

- **table_open_cache:** số table instance tối đa có thể được giữ mở trong table cache.
- **table_definition_cache:** số table definition tối đa được cache.
- **table_open_cache_instances:** chia table cache thành nhiều instance để giảm tranh chấp nội bộ khi nhiều thread đồng thời truy cập cache.

Table instance và table definition là hai loại đối tượng khác nhau. Một bảng có thể có nhiều instance được mở đồng thời tùy hoạt động của session và server. Một definition mô tả cấu trúc bảng, không phải file dữ liệu đang mở.

### 3.1. table_open_cache

table_open_cache giới hạn số table instance được cache. Khi truy vấn truy cập nhiều bảng và cache không đủ, MySQL có thể phải đóng một số instance rồi mở lại khi cần. Việc mở/đóng lặp lại làm tăng I/O metadata, syscall và chi phí xử lý.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'table_open_cache';
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_tables',
    'Opened_tables',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows'
);
~~~

Các status variable:

- **Open_tables:** số table instance hiện đang mở.
- **Opened_tables:** tổng số lần bảng được mở kể từ khi server khởi động.
- **Table_open_cache_hits:** số lần tìm thấy table instance trong cache.
- **Table_open_cache_misses:** số lần không tìm thấy instance trong cache và phải thực hiện thao tác mở.
- **Table_open_cache_overflows:** số lần cache đạt giới hạn và server cần xử lý tình huống vượt cache.

Tên và mức độ sẵn có của một số status variable có thể phụ thuộc phiên bản. Nếu một biến không tồn tại, kiểm tra danh sách status của đúng bản MySQL đang chạy.

### 3.2. Đọc các chỉ số table cache

Open_tables gần bằng table_open_cache trong thời gian dài có thể là dấu hiệu cache đang chịu áp lực, nhưng chưa đủ để kết luận thiếu cache. Một số bảng có thể đang được nhiều thread sử dụng và chưa thể đóng ngay.

Opened_tables tăng nhanh trong khoảng thời gian ngắn có thể cho thấy server phải mở bảng lặp lại. Hãy so sánh delta theo thời gian, không nhìn tổng từ lúc khởi động mà không xét uptime.

Table_open_cache_misses và Table_open_cache_overflows tăng đều dưới tải có thể củng cố giả thuyết cache thiếu. Kiểm tra thêm:

- Số bảng và partition thực tế được workload truy cập.
- Số session đồng thời mở nhiều bảng.
- DDL, FLUSH TABLES hoặc hoạt động triển khai có làm cache bị invalidation hay không.
- open_files_limit và giới hạn file descriptor có đủ cho mức table cache mong muốn không.

### 3.3. table_definition_cache

table_definition_cache giữ metadata định nghĩa bảng để giảm chi phí đọc và phân tích cấu trúc bảng. Nó không giữ table file đang mở và không thay thế table_open_cache.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'table_definition_cache';
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_table_definitions',
    'Opened_table_definitions'
);
~~~

Open_table_definitions biểu thị số table definition đang được cache; Opened_table_definitions là bộ đếm số definition đã được mở kể từ khi server khởi động.

Nếu hệ thống có nhiều bảng hoặc partition, table_definition_cache có thể cần đủ lớn để tránh nạp lại metadata thường xuyên. Tuy nhiên, tăng quá cao cũng tiêu thụ bộ nhớ. Một số phiên bản có cơ chế tự điều chỉnh hoặc giá trị mặc định phụ thuộc cấu hình; hãy kiểm tra giá trị hiệu lực thay vì giả định một con số mặc định.

### 3.4. table_open_cache_instances

table_open_cache_instances chia cache thành nhiều phần để giảm contention trên cấu trúc cache khi nhiều thread mở bảng cùng lúc. Nó hữu ích ở workload có nhiều kết nối đồng thời và nhiều thao tác mở bảng.

Biến này là cấu hình khởi động trên các phiên bản MySQL phổ biến; kiểm tra tài liệu đúng phiên bản trước khi thay đổi. Tăng số instance không làm tổng table_open_cache tăng tương ứng. Nó thay đổi cách cache được phân chia và đồng bộ.

Không tăng số instance chỉ vì Open_tables lớn. Hãy tìm dấu hiệu contention, tải đồng thời và hiệu quả thực tế sau khi thay đổi.

### 3.5. Ví dụ workload nhiều bảng

Một ứng dụng kế toán có thể truy vấn đồng thời:

- invoices, invoice_items, customers, tax_rates;
- payments, payment_methods, refunds;
- accounts, journal_entries, cost_centers;
- nhiều bảng lịch sử theo tenant hoặc theo tháng.

Mỗi truy vấn có thể mở nhiều bảng. Khi nhiều session chạy cùng lúc, nhu cầu table instance tăng. Nếu bảng bị chia partition, số đối tượng cần mở và quản lý cũng có thể tăng theo thiết kế.

Đừng ước lượng table_open_cache chỉ bằng số bảng trong schema. Hãy xem số bảng được truy cập đồng thời, số session, số partition, truy vấn động và pattern của workload.

## 4. File descriptor và open_files_limit

Hệ điều hành cấp file descriptor cho tiến trình để truy cập file, socket, pipe và các đối tượng I/O khác. Trong Linux, mỗi tiến trình có giới hạn số file descriptor có thể mở. MySQL cần file descriptor cho nhiều mục đích:

- File dữ liệu và index của các bảng.
- File log, binary log, relay log và redo/undo tùy cấu hình.
- File tạm và file nội bộ.
- Socket kết nối client.
- Các file khác do storage engine và server quản lý.

open_files_limit là giới hạn file descriptor mà MySQL server có thể sử dụng theo cấu hình và giới hạn hệ điều hành cấp cho tiến trình. Đây không phải số bảng tối đa và cũng không phải số file dữ liệu tối đa theo cách đếm đơn giản một bảng bằng một file.

### 4.1. Kiểm tra giới hạn MySQL

~~~sql
SHOW GLOBAL VARIABLES LIKE 'open_files_limit';
SHOW GLOBAL VARIABLES LIKE 'table_open_cache';
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_files',
    'Opened_files'
);
~~~

- **Open_files:** số file descriptor MySQL đang mở tại thời điểm lấy mẫu.
- **Opened_files:** tổng số file MySQL đã mở kể từ khi server khởi động.
- **open_files_limit:** giới hạn hiệu lực MySQL có thể sử dụng theo cấu hình/OS.

Open_files là số hiện tại; Opened_files là bộ đếm tích lũy. Opened_files tăng không tự động có nghĩa server sắp hết file descriptor. Cần so Open_files với open_files_limit và theo dõi tốc độ thay đổi.

### 4.2. MySQL không thể vượt giới hạn của hệ điều hành

MySQL có thể yêu cầu một mức open_files_limit khi khởi động. Giá trị hiệu lực phụ thuộc giới hạn mà tiến trình mysqld thực sự được cấp. Nếu service manager, container runtime hoặc OS đặt giới hạn thấp hơn, MySQL không thể tự nâng vượt quyền được cấp.

Một dòng cấu hình open_files_limit lớn trong my.cnf không chứng minh tiến trình đã nhận được mức đó. Luôn xác minh giá trị runtime và log khởi động.

### 4.3. Vì sao table cache và file descriptor liên quan?

Mở nhiều table instance thường cần thêm file descriptor. Vì vậy, tăng table_open_cache có thể làm tăng nhu cầu file descriptor. MySQL cũng cần descriptor cho kết nối và các file khác, nên không thể dành toàn bộ open_files_limit cho table cache.

Nếu open_files_limit thấp, table_open_cache có thể không đạt quy mô mong muốn hoặc server có thể phát cảnh báo, lỗi khi mở file. Nếu table_open_cache được tăng mà giới hạn OS không tăng, thay đổi có thể không đem lại kết quả như kỳ vọng.

### 4.4. Không suy ra số file descriptor chỉ từ số bảng

Một bảng InnoDB có thể liên quan đến file tablespace, shared tablespace, redo, undo hoặc cấu trúc lưu trữ khác tùy cấu hình. Một bảng partition có thể tạo thêm nhu cầu metadata và file. Một kết nối client thường sử dụng socket descriptor. Binary log và relay log cũng dùng file descriptor.

Vì vậy, mô hình tính toán phải dựa trên workload và cách triển khai cụ thể. Không dùng công thức kiểu “mỗi bảng bằng một descriptor” để sizing production.

## 5. Giới hạn file descriptor ở Linux và systemd

Trên Linux, giới hạn của tiến trình thường được biểu diễn bởi RLIMIT_NOFILE. Giá trị shell ulimit của người đăng nhập không nhất thiết là giá trị service MySQL nhận được.

### 5.1. Kiểm tra giới hạn shell

~~~bash
ulimit -n
ulimit -Hn
~~~

Lệnh đầu hiển thị soft limit; lệnh thứ hai hiển thị hard limit của shell hiện tại. Nếu MySQL được khởi động bởi systemd, cron, container runtime hoặc supervisor, shell của người vận hành có thể không phản ánh giới hạn của tiến trình mysqld.

### 5.2. Kiểm tra systemd service

Tên service có thể là mysqld hoặc mysql tùy bản phân phối. Xác định đúng tên service trước khi chạy lệnh:

~~~bash
sudo systemctl show mysqld --property=LimitNOFILE
~~~

Có thể kiểm tra giới hạn của tiến trình đang chạy:

~~~bash
pidof mysqld
cat /proc/<PID>/limits
~~~

Trong kết quả, tìm dòng Max open files. Đây là giới hạn thực tế của process, có giá trị chẩn đoán trực tiếp hơn ulimit của terminal.

### 5.3. Đặt LimitNOFILE bằng systemd drop-in

Nếu đã xác nhận giới hạn service thấp hơn nhu cầu, có thể tạo override cho đúng service:

~~~bash
sudo systemctl edit mysqld
~~~

Nội dung drop-in minh họa:

~~~ini
[Service]
LimitNOFILE=65535
~~~

Sau khi lưu:

~~~bash
sudo systemctl daemon-reload
sudo systemctl show mysqld --property=LimitNOFILE
~~~

Giá trị 65535 chỉ là ví dụ minh họa. Chọn giới hạn theo dung lượng RAM, số kết nối, table cache, file log, storage engine và giới hạn của máy. Việc áp dụng thay đổi giới hạn cho tiến trình thường cần restart service trong cửa sổ bảo trì.

### 5.4. Kiểm tra sau restart

Sau khi service được khởi động lại:

1. Kiểm tra trạng thái service.
2. Kiểm tra Max open files trong /proc/<PID>/limits.
3. Kiểm tra open_files_limit trong MySQL.
4. Đọc error log để xác nhận server đã nhận giới hạn yêu cầu hoặc có cảnh báo.
5. Kiểm tra Open_files dưới tải thực tế.

Không giả định systemctl daemon-reload tự thay đổi giới hạn của tiến trình mysqld đang chạy. Drop-in mới có hiệu lực khi service được khởi động lại.

## 6. Container và môi trường điều phối

Nếu MySQL chạy trong container, giới hạn descriptor phải được cấp từ runtime hoặc cấu hình container. Giá trị ulimit của host không tự động chứng minh container đã nhận cùng giới hạn.

Ví dụ Docker:

~~~bash
docker run --ulimit nofile=65535:65535 ...
~~~

Ví dụ Docker Compose:

~~~yaml
services:
  mysql:
    image: mysql:8.4
    ulimits:
      nofile:
        soft: 65535
        hard: 65535
~~~

Đây là cấu hình minh họa. Trong môi trường hiện có, hãy dùng đúng image, service name, secret, volume và chính sách triển khai của hệ thống. Không thay toàn bộ cấu hình container production chỉ để sửa một giới hạn.

Với Kubernetes, không giả định có một trường ulimit chuẩn trong Pod spec áp dụng đồng nhất trên mọi runtime. Cần kiểm tra cấu hình node, container runtime, security policy và nền tảng quản lý cluster. Xác minh giới hạn từ bên trong container và từ tiến trình mysqld.

## 7. MySQL trên Windows

Trên Windows, giới hạn tiến trình và cách chạy dịch vụ khác Linux. MySQL thường đọc cấu hình từ file my.ini và được quản lý bởi Windows Service Control Manager. Không áp dụng lệnh ulimit hoặc systemd vào Windows.

Các bước chẩn đoán:

1. Xác định đúng Windows service đang chạy mysqld.
2. Kiểm tra file my.ini thực sự được service sử dụng.
3. Kiểm tra cấu hình open_files_limit và các biến cache trong nhóm [mysqld].
4. Đọc error log sau khi khởi động.
5. Kiểm tra giá trị hiệu lực bằng SHOW GLOBAL VARIABLES và SHOW GLOBAL STATUS.
6. Nếu cần đổi startup option, chỉnh cấu hình đúng instance rồi restart service trong cửa sổ bảo trì.

Không dùng một giá trị open_files_limit trong my.ini làm bằng chứng rằng Windows đã cấp chính xác số handle đó. Giá trị hiệu lực và log của server mới là cơ sở xác nhận.

## 8. Mối quan hệ giữa max_connections, table_open_cache và open_files_limit

Ba biến này có quan hệ về tài nguyên:

- max_connections quyết định số kết nối client tối đa được chấp nhận.
- table_open_cache quyết định quy mô table instance cache.
- open_files_limit giới hạn số file descriptor server có thể sử dụng.

Khi max_connections tăng, server có thể cần thêm tài nguyên cho session, socket, thread, table handle và hoạt động phụ trợ. Khi table_open_cache tăng, server có thể cần thêm descriptor để giữ nhiều table instance. Vì vậy, cấu hình phải được xem xét cùng nhau.

MySQL có thể tính hoặc điều chỉnh yêu cầu open_files_limit khi khởi động dựa trên các biến cấu hình khác và khả năng OS. Chi tiết tính toán thay đổi theo phiên bản và nền tảng; không dựa vào một công thức cố định áp dụng cho mọi release.

### 8.1. Ví dụ về cấu hình mất cân đối

Giả sử cấu hình yêu cầu:

~~~ini
[mysqld]
max_connections=800
table_open_cache=12000
open_files_limit=4096
~~~

Nếu tiến trình chỉ được OS cấp vài nghìn descriptor, mức table cache yêu cầu có thể không khả thi. Server có thể giảm giới hạn hiệu lực hoặc ghi cảnh báo. Số kết nối lớn cũng tiêu thụ thêm tài nguyên khác, không chỉ file descriptor.

Hãy xem giá trị thực tế sau khi khởi động:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'table_open_cache',
    'table_definition_cache',
    'table_open_cache_instances',
    'open_files_limit',
    'thread_cache_size'
);
~~~

Nếu giá trị hiệu lực khác giá trị cấu hình, điều tra startup log và giới hạn service/OS trước khi tiếp tục tăng cache.

### 8.2. max_connections không phải mục tiêu tối ưu hóa

Đặt max_connections quá cao có thể làm tăng bộ nhớ dự phòng, thread/session overhead và nhu cầu file descriptor. Một connection pool có giới hạn phù hợp thường dễ kiểm soát hơn hàng trăm hoặc hàng nghìn client mở kết nối không giới hạn.

Đo Max_used_connections, Threads_connected, Threads_running, tỷ lệ timeout và hàng đợi ứng dụng. Tăng max_connections chỉ khi có nhu cầu đồng thời thực tế và server còn đủ CPU, RAM, descriptor cùng năng lực xử lý.

### 8.3. Phân biệt open_files_limit và innodb_open_files

open_files_limit là giới hạn file descriptor ở cấp server/process. innodb_open_files là cấu hình riêng của InnoDB liên quan số file dữ liệu InnoDB có thể giữ mở trong một số cấu hình tablespace.

Hai biến có liên quan về tài nguyên nhưng không đồng nghĩa. Tăng innodb_open_files không vượt qua giới hạn descriptor của tiến trình; tăng open_files_limit cũng không tự chọn giá trị innodb_open_files phù hợp.

## 9. Thu thập baseline bằng SQL

Trước khi thay đổi, lưu lại cấu hình và status hiện tại. Nên lấy ít nhất hai snapshot cách nhau một khoảng thời gian có tải đại diện.

### 9.1. Snapshot cấu hình

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'thread_cache_size',
    'table_open_cache',
    'table_open_cache_instances',
    'table_definition_cache',
    'open_files_limit',
    'innodb_open_files'
);
~~~

Ghi lại giá trị, thời điểm, uptime, phiên bản MySQL và nguồn cấu hình nếu môi trường có nhiều file option hoặc SET PERSIST.

### 9.2. Snapshot thread và connection

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Connections',
    'Threads_created',
    'Threads_cached',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Aborted_connects'
);
~~~

Đọc các bộ đếm cùng thời điểm. Nếu cần phân tích theo khoảng thời gian, lưu snapshot vào hệ thống monitoring hoặc ghi lại kết quả bên ngoài database.

### 9.3. Snapshot table cache và file

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Open_tables',
    'Opened_tables',
    'Open_table_definitions',
    'Opened_table_definitions',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows',
    'Open_files',
    'Opened_files'
);
~~~

Nếu phiên bản không cung cấp một status variable trong danh sách, bỏ biến đó và dùng các chỉ số còn lại. Không kết luận cache thiếu chỉ từ một biến đơn lẻ.

### 9.4. Kiểm tra file qua Performance Schema

Nếu Performance Schema đang bật và các instrument liên quan được thu thập, có thể xem số file instance theo loại:

~~~sql
SELECT
    EVENT_NAME,
    COUNT(*) AS file_instances,
    SUM(OPEN_COUNT) AS open_count
FROM performance_schema.file_instances
GROUP BY EVENT_NAME
ORDER BY open_count DESC;
~~~

Xem các file có hoạt động I/O tích lũy lớn:

~~~sql
SELECT
    EVENT_NAME,
    FILE_NAME,
    COUNT_STAR,
    SUM_TIMER_WAIT
FROM performance_schema.file_summary_by_instance
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Các bảng Performance Schema phụ thuộc instrument và consumer đã bật. Nếu kết quả trống, kiểm tra cấu hình thu thập trước khi kết luận server không mở file.

### 9.5. Kiểm tra giới hạn từ OS

Trên Linux, dùng thông tin của chính tiến trình mysqld:

~~~bash
pidof mysqld
cat /proc/<PID>/limits
ls /proc/<PID>/fd | wc -l
~~~

Lệnh đầu tìm PID, lệnh thứ hai cho thấy soft/hard limit, lệnh thứ ba đếm descriptor đang mở trong thư mục fd của tiến trình. Thực hiện với quyền đủ đọc thông tin process.

Có thể xem tình trạng file handle toàn hệ thống:

~~~bash
cat /proc/sys/fs/file-nr
cat /proc/sys/fs/file-max
~~~

Đây là số liệu cấp host, không thay thế giới hạn riêng của mysqld. Một host có thể còn nhiều file handle nhưng tiến trình MySQL vẫn chạm RLIMIT_NOFILE của riêng nó.

## 10. Quy trình sizing và tuning

Điều chỉnh cache là một quá trình đo, thay đổi và xác nhận. Thực hiện từng nhóm biến để biết thay đổi nào tạo ra tác động.

### 10.1. Xác định tải thực tế

Thu thập:

- Số kết nối đồng thời trung bình và peak.
- Số lần mở kết nối mới mỗi giây.
- Số bảng và partition được truy cập trong cùng khoảng thời gian.
- Số session có truy vấn mở nhiều bảng.
- Số file descriptor thực tế trong tiến trình.
- Dung lượng RAM còn trống và mức dùng bộ nhớ của mysqld.
- Các lỗi mở file, timeout, connection refusal và cảnh báo khi khởi động.

Không dùng tổng số bảng trong schema hoặc max_connections cấu hình làm đại diện duy nhất cho tải.

### 10.2. Tuning thread cache

1. Lấy snapshot Connections và Threads_created.
2. Chờ một khoảng thời gian có tải đại diện.
3. Lấy snapshot lần hai và tính delta.
4. Đối chiếu với connection pool, tốc độ kết nối và CPU.
5. Nếu thread mới được tạo thường xuyên và chi phí này đáng kể, tăng thread_cache_size từng bước.
6. Lặp lại phép đo sau thay đổi.

Nếu connection pool giữ kết nối lâu, thread cache có thể không phải nút thắt. Tăng cache trong tình huống này có thể chỉ giữ thêm thread rảnh mà không cải thiện latency.

### 10.3. Tuning table_open_cache

1. Lấy Open_tables, Opened_tables, Table_open_cache_misses và Table_open_cache_overflows.
2. Đo delta theo thời gian có workload đại diện.
3. Kiểm tra open_files_limit và số descriptor thực tế.
4. Nếu cache thường xuyên bị thiếu và file descriptor còn đủ, tăng table_open_cache theo từng bước.
5. Theo dõi RAM, Open_files, miss/overflow và latency.
6. Nếu giá trị hiệu lực không tăng như yêu cầu, xem startup log và OS limit.

Không tăng table_open_cache vượt khả năng file descriptor và bộ nhớ của server. Cache lớn hơn cũng không đảm bảo truy vấn nhanh hơn nếu bottleneck nằm ở I/O dữ liệu, lock hoặc execution plan.

### 10.4. Tuning table_definition_cache

Nếu workload có rất nhiều bảng hoặc partition, theo dõi Open_table_definitions và Opened_table_definitions. Cân nhắc tăng cache khi metadata liên tục phải nạp lại và bộ nhớ còn đủ.

Đừng dùng Opened_table_definitions tích lũy mà không tính delta. DDL, restart và workload có thể làm thay đổi cách đọc số liệu.

### 10.5. Tuning table_open_cache_instances

Chỉ cân nhắc thay đổi khi workload có mức đồng thời cao và có dấu hiệu tranh chấp ở table cache. Đây là biến cần cấu hình khi khởi động trên nhiều bản MySQL; kiểm tra dynamic scope của phiên bản đang chạy.

Tăng số instance không phải cách chữa table cache quá nhỏ. Hãy phân biệt contention với thiếu dung lượng cache.

### 10.6. Tuning open_files_limit

Nếu Open_files tiến gần open_files_limit hoặc startup log cho biết MySQL không nhận đủ descriptor:

1. Kiểm tra giới hạn thực tế của tiến trình.
2. Kiểm tra systemd, container runtime hoặc service manager.
3. Chọn mức mới dựa trên kết nối, table cache, log và file nội bộ.
4. Nâng giới hạn OS/service trước hoặc cùng đợt thay đổi MySQL.
5. Cấu hình open_files_limit ở startup nếu cần.
6. Restart có kế hoạch và kiểm tra giá trị hiệu lực.

Không thể sửa giới hạn tiến trình đã khởi chạy chỉ bằng SET GLOBAL open_files_limit. Đây là cấu hình khởi động và cần xử lý ở đúng lớp OS/service.

## 11. Áp dụng cấu hình MySQL

### 11.1. Nhận diện biến runtime và startup

Các biến có thể thay đổi runtime trong những phiên bản MySQL phổ biến:

- thread_cache_size;
- table_open_cache;
- table_definition_cache;
- max_connections.

Các biến như open_files_limit và table_open_cache_instances thường cần cấu hình khi khởi động. Phạm vi thay đổi có thể khác theo phiên bản; kiểm tra tài liệu và metadata biến của bản đang chạy trước khi lập kế hoạch.

### 11.2. Thay đổi runtime để thử nghiệm

Ví dụ:

~~~sql
SET GLOBAL thread_cache_size = 64;
SET GLOBAL table_open_cache = 4000;
SET GLOBAL table_definition_cache = 2000;
~~~

Các con số chỉ minh họa cú pháp. Trước khi chạy, xác định giá trị phù hợp với workload, phiên bản, RAM và open_files_limit. Thay đổi GLOBAL thường ảnh hưởng các session mới hoặc hành vi toàn server theo phạm vi của biến; session hiện tại có thể vẫn giữ một số trạng thái đã mở.

### 11.3. Lưu cấu hình sau restart

Có thể lưu option vào file cấu hình MySQL:

~~~ini
[mysqld]
thread_cache_size=64
table_open_cache=4000
table_definition_cache=2000
table_open_cache_instances=16
open_files_limit=65535
~~~

Đây là ví dụ minh họa, không phải cấu hình production dùng chung. Các giá trị cần được tính theo máy chủ cụ thể. Trên Linux file thường là my.cnf; trên Windows thường là my.ini. Đảm bảo chỉnh đúng file mà service thực sự đọc.

Trên phiên bản hỗ trợ, SET PERSIST có thể lưu một số biến dynamic để dùng sau restart:

~~~sql
SET PERSIST thread_cache_size = 64;
~~~

Không dùng SET PERSIST cho biến chỉ được đặt khi khởi động hoặc biến read-only. Kiểm tra nguồn cấu hình và chính sách quản lý config để tránh hai nguồn cấu hình xung đột.

### 11.4. Thứ tự thay đổi an toàn

Với một lần nâng table cache đáng kể, quy trình nên là:

1. Ước lượng nhu cầu file descriptor và bộ nhớ.
2. Kiểm tra giới hạn OS/service.
3. Nâng giới hạn OS/service nếu cần.
4. Cấu hình open_files_limit ở startup.
5. Cấu hình table_open_cache và các cache liên quan.
6. Restart trong cửa sổ bảo trì nếu có biến startup-only.
7. Xác nhận giá trị hiệu lực và startup log.
8. Chạy workload đại diện, theo dõi status và tài nguyên.

Không đổi nhiều biến không liên quan trong cùng một lần nếu chưa có baseline. Khi có hồi quy, cần biết thay đổi nào gây ra nó.

## 12. Đọc startup log và nhận diện giới hạn bị áp thấp

Khi khởi động, MySQL có thể ghi thông báo về số file mở tối đa được yêu cầu và số file mở tối đa thực tế được cấp. Nếu giá trị thực tế thấp hơn yêu cầu, hãy tìm nguyên nhân ở OS hoặc service manager.

Các dấu hiệu cần điều tra:

- MySQL không tăng được số open files theo yêu cầu.
- Giá trị open_files_limit runtime thấp hơn cấu hình.
- table_open_cache hiệu lực thấp hơn mức mong muốn.
- Server phát cảnh báo hoặc lỗi khi mở file.
- Kết nối mới bị từ chối hoặc truy vấn không thể mở bảng.
- Open_files tiến gần giới hạn trong giờ cao điểm.

Không chỉ tìm một thông báo theo chuỗi cố định vì câu chữ log có thể khác theo phiên bản. Đọc toàn bộ startup log quanh thời điểm mysqld khởi động và đối chiếu với biến runtime.

## 13. Chẩn đoán theo triệu chứng

| Triệu chứng | Lớp cần kiểm tra trước | Bằng chứng nên thu thập |
|---|---|---|
| Nhiều thread mới khi kết nối liên tục | Thread cache / connection churn | Delta Threads_created, Connections, thời gian sống session |
| Too many connections | max_connections và pool | Threads_connected, Max_used_connections, hàng đợi ứng dụng |
| Table cache miss/overflow tăng nhanh | table_open_cache | Open_tables, delta Opened_tables, cache misses/overflows |
| Nạp metadata bảng lặp lại | table_definition_cache | Open_table_definitions, delta Opened_table_definitions |
| Too many open files | open_files_limit và OS | Open_files, open_files_limit, process limits, startup log |
| table cache không đạt giá trị yêu cầu | OS descriptor limit hoặc cấu hình | Biến runtime, log khởi động, service/container limit |
| RAM tăng sau khi mở cache lớn | Cache sizing và concurrency | RSS mysqld, số table instance, số session |

### 13.1. Too many open files

Thông báo này thường liên quan đến giới hạn descriptor ở cấp tiến trình hoặc hệ thống. Kiểm tra theo thứ tự:

1. Open_files và open_files_limit trong MySQL.
2. Max open files trong /proc/<PID>/limits nếu dùng Linux.
3. LimitNOFILE của systemd hoặc ulimit cấu hình cho container.
4. Startup log để biết server đã yêu cầu và nhận được bao nhiêu.
5. Số kết nối, table cache, file log và workload thực tế.

Không chỉ giảm table_open_cache ngay lập tức nếu giới hạn OS đang thấp do cấu hình service. Cần xác định mức tải có hợp lý không trước khi chọn giảm cache hay nâng limit.

### 13.2. Too many connections

Đây là giới hạn kết nối, không phải thread cache. Kiểm tra Max_used_connections, Threads_connected, max_connections, pool size và việc ứng dụng có đóng connection đúng cách không.

Tăng max_connections có thể che giấu connection leak và làm server chịu thêm áp lực. Hãy sửa pool, timeout và vòng đời connection trước khi tăng giới hạn nếu nguyên nhân là ứng dụng giữ kết nối không cần thiết.

### 13.3. Mở bảng chậm hoặc cache churn

Nếu Opened_tables tăng nhanh và cache miss/overflow tăng, kiểm tra số bảng/partition truy cập, số session và hoạt động DDL. Sau đó đánh giá table_open_cache cùng open_files_limit.

Nếu cache đủ nhưng truy vấn vẫn chậm, chuyển sang phân tích execution plan, I/O, lock và metadata contention. Không quy mọi truy vấn chậm cho table cache.

## 14. Sai lầm cấu hình thường gặp

1. **Tăng mọi cache lên mức cao:** có thể tiêu thụ RAM và descriptor, không đảm bảo tăng throughput.
2. **Nhầm thread cache với connection pool:** thread cache không giữ client connection sống.
3. **Nhầm thread_cache_size với max_connections:** một biến tái sử dụng thread rảnh, biến kia giới hạn kết nối đồng thời.
4. **Nhầm table_open_cache với table_definition_cache:** một biến quản lý table instance, biến kia quản lý metadata định nghĩa.
5. **Chỉ sửa open_files_limit trong my.cnf:** tiến trình có thể vẫn bị systemd hoặc container giới hạn thấp hơn.
6. **Chỉ kiểm tra ulimit của terminal:** mysqld có thể được service manager khởi chạy với limit khác.
7. **Tăng table_open_cache mà quên descriptor:** server có thể không đạt cache size mong muốn.
8. **Đọc bộ đếm tích lũy như số hiện tại:** Opened_tables và Threads_created cần được phân tích bằng delta.
9. **Tăng max_connections để chữa connection leak:** có thể làm áp lực RAM, CPU và descriptor nghiêm trọng hơn.
10. **Không kiểm tra startup log:** giá trị runtime có thể khác giá trị trong file cấu hình.
11. **Chạy FLUSH TABLES để thử cache:** thao tác này có thể đóng/invalidate table cache và làm sai phép đo workload bình thường.
12. **Không có kế hoạch restart:** biến startup-only hoặc giới hạn OS cần khởi động lại để có hiệu lực.

## 15. Bài thực hành: đo thread, table cache và file descriptor

Thực hiện trong môi trường lab hoặc staging. Không thay đổi giới hạn OS hay restart database production chỉ để làm bài tập.

### 15.1. Ghi nhận phiên bản và cấu hình

~~~sql
SELECT VERSION() AS mysql_version;

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'thread_cache_size',
    'table_open_cache',
    'table_open_cache_instances',
    'table_definition_cache',
    'open_files_limit'
);
~~~

Lưu kết quả làm baseline.

### 15.2. Ghi nhận status ban đầu

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Connections',
    'Threads_created',
    'Threads_cached',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Open_tables',
    'Opened_tables',
    'Table_open_cache_hits',
    'Table_open_cache_misses',
    'Table_open_cache_overflows',
    'Open_files',
    'Opened_files'
);
~~~

### 15.3. Tạo workload bảng lab

~~~sql
CREATE DATABASE IF NOT EXISTS cache_lab;
USE cache_lab;

CREATE TABLE lab_a (
    id BIGINT NOT NULL PRIMARY KEY,
    value_text VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE lab_b (
    id BIGINT NOT NULL PRIMARY KEY,
    value_text VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

INSERT INTO lab_a (id, value_text)
VALUES (1, 'alpha'), (2, 'beta');

INSERT INTO lab_b (id, value_text)
VALUES (1, 'one'), (2, 'two');

SELECT a.id, a.value_text, b.value_text
FROM lab_a AS a
JOIN lab_b AS b
  ON b.id = a.id;
~~~

Truy vấn lặp lại nhiều lần để tạo hoạt động mở và tra cứu bảng. Có thể mở nhiều session lab để quan sát ảnh hưởng đồng thời; không tạo hàng nghìn kết nối tùy tiện trên máy dùng chung.

### 15.4. So sánh status theo thời gian

Chụp lại các status ở mục 15.2 sau một khoảng tải. Tính delta:

- Threads_created và Connections để đánh giá thread creation.
- Opened_tables, Table_open_cache_misses và Table_open_cache_overflows để đánh giá cache churn.
- Open_files để đánh giá số descriptor đang mở.

Không so sánh tổng bộ đếm giữa hai server khác uptime mà không chuẩn hóa thời gian và workload.

### 15.5. Thử thay đổi thread cache trong lab

Nếu có quyền và môi trường cho phép, ghi giá trị cũ rồi thay đổi:

~~~sql
SET GLOBAL thread_cache_size = 32;
~~~

Tạo một số kết nối ngắn có kiểm soát, ngắt kết nối và quan sát Threads_cached, Threads_created. So sánh với baseline. Khôi phục giá trị ban đầu sau bài tập.

### 15.6. Kiểm tra file descriptor trên Linux

Trên host lab, tìm PID mysqld và kiểm tra:

~~~bash
pidof mysqld
cat /proc/<PID>/limits
ls /proc/<PID>/fd | wc -l
~~~

Đối chiếu Max open files với open_files_limit trong MySQL. Nếu hai mức không khớp, ghi lại service manager hoặc container runtime đang quản lý tiến trình.

### 15.7. Dọn bảng lab

~~~sql
DROP DATABASE cache_lab;
~~~

Chỉ xóa database cache_lab do chính bài tập vừa tạo.

## 16. Runbook khi cần nâng giới hạn

Khi có bằng chứng server sắp hết file descriptor hoặc table cache bị thiếu, thực hiện theo trình tự:

1. **Xác nhận triệu chứng:** lấy status, log và số liệu OS cùng thời điểm.
2. **Xác định process:** xác nhận đúng PID, service name, container và instance MySQL.
3. **Xác định giới hạn hiện tại:** kiểm tra open_files_limit, process limit và giới hạn runtime.
4. **Ước lượng nhu cầu:** tính đến max_connections, table cache, log, socket, partition và file nội bộ.
5. **Kiểm tra RAM:** bảo đảm table cache và số session mới không làm bộ nhớ vượt khả năng máy.
6. **Lập kế hoạch thay đổi:** ghi giá trị cũ/mới, cách rollback và cửa sổ restart nếu cần.
7. **Áp dụng ở đúng lớp:** OS/service/container trước hoặc cùng lúc với startup option của MySQL.
8. **Khởi động lại có kiểm soát:** kiểm tra trạng thái service và error log.
9. **Xác nhận hiệu lực:** đọc lại biến MySQL và process limit.
10. **Theo dõi sau thay đổi:** đo connection churn, cache miss/overflow, Open_files, RAM và latency.
11. **Rollback nếu có hồi quy:** khôi phục cấu hình cũ theo kế hoạch và xác nhận server ổn định.

## 17. Checklist vận hành

### Trước khi thay đổi

- [ ] Đã ghi phiên bản MySQL và uptime.
- [ ] Đã lấy snapshot biến GLOBAL và status.
- [ ] Đã đo delta của bộ đếm tích lũy.
- [ ] Đã xác định đúng tiến trình và service/container.
- [ ] Đã kiểm tra giới hạn file descriptor thực tế của process.
- [ ] Đã ước lượng nhu cầu RAM và descriptor.
- [ ] Đã biết biến nào dynamic, biến nào cần restart ở phiên bản đang chạy.
- [ ] Đã chuẩn bị kế hoạch rollback và cửa sổ bảo trì.

### Sau khi thay đổi

- [ ] Service khởi động thành công.
- [ ] Error log không còn cảnh báo giới hạn ngoài dự kiến.
- [ ] Giá trị open_files_limit và cache runtime đạt mức mong muốn.
- [ ] Process limit từ OS khớp kế hoạch.
- [ ] Open_files còn khoảng dự phòng dưới tải peak.
- [ ] Table cache miss/overflow không tăng bất thường.
- [ ] Threads_created không tăng bất thường so với Connections.
- [ ] RAM, CPU và latency vẫn trong mục tiêu.
- [ ] Cấu hình được lưu ở nguồn quản lý chuẩn, không chỉ thay đổi tạm thời.

## 18. Nguyên tắc cần ghi nhớ

- thread_cache_size tái sử dụng thread server sau khi session đóng; nó không phải connection pool và không giới hạn kết nối đồng thời.
- max_connections, thread_cache_size và thread pool giải quyết các vấn đề khác nhau.
- table_open_cache giữ table instance; table_definition_cache giữ định nghĩa bảng.
- table_open_cache_instances giảm tranh chấp giữa các cache instance, không tự tăng tổng dung lượng table cache.
- open_files_limit là giới hạn descriptor phía MySQL, nhưng giá trị hiệu lực bị chi phối bởi quyền và giới hạn OS/service/container.
- Open_files là số file hiện tại; Opened_files là bộ đếm tích lũy.
- Threads_cached là số thread đang nằm trong cache; Threads_created là tổng số thread đã tạo.
- Opened_tables và Opened_table_definitions cần được đọc bằng delta theo thời gian.
- Tăng table_open_cache làm tăng nhu cầu descriptor; phải xem cùng open_files_limit và max_connections.
- ulimit của shell không chứng minh systemd service hoặc container nhận cùng giới hạn.
- Trên Linux, kiểm tra process limits; trên Windows, kiểm tra đúng Windows service và file my.ini.
- Không dùng một công thức file descriptor cố định cho mọi phiên bản, engine và workload.
- Chỉ tăng cache khi status và workload cho thấy lợi ích; cache quá lớn có thể tiêu thụ RAM và handle.
- Biến startup-only cần cấu hình đúng nguồn và restart có kế hoạch.
- Luôn xác minh giá trị runtime, process limit, startup log và hành vi dưới tải sau thay đổi.

Thread cache, table cache và file descriptor là các phần khác nhau của cùng một bài toán tài nguyên. Thiết kế vận hành tốt bắt đầu từ số liệu: đo connection churn, table cache miss, file descriptor thực tế và giới hạn tiến trình; sau đó điều chỉnh từng lớp theo tải, bộ nhớ và nền tảng triển khai. Khi giá trị hiệu lực được xác minh sau restart và workload vẫn ổn định, cấu hình mới mới được xem là hoàn tất.
