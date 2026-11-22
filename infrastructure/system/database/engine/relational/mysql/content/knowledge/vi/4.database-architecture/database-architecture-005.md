# Bộ nhớ dùng chung, bộ nhớ theo kết nối và vùng làm việc

MySQL cần bộ nhớ để giữ trang dữ liệu thường được truy cập, quản lý metadata, tiếp nhận kết nối, thực thi câu SQL, sắp xếp kết quả và xử lý bảng tạm. Các phần bộ nhớ này có phạm vi sống và cách chia sẻ khác nhau. Một số vùng được nhiều kết nối dùng chung trong suốt thời gian máy chủ hoạt động; một số vùng gắn với từng kết nối; một số vùng chỉ được cấp phát khi một câu truy vấn cần thực hiện công việc cụ thể.

Phân biệt ba nhóm này là nền tảng để đọc cấu hình MySQL, dự tính số kết nối an toàn và điều tra tình trạng dùng RAM tăng cao. Nếu coi mọi biến cấu hình bộ nhớ là một khoản cấp phát cố định cho từng kết nối, ta dễ ước tính sai. Ngược lại, nếu chỉ nhìn vào bộ nhớ dùng chung như InnoDB buffer pool, ta có thể bỏ qua lượng RAM tăng thêm khi nhiều truy vấn nặng chạy đồng thời.

Bài viết tập trung vào MySQL 8.x với InnoDB là storage engine chính. Một số bộ nhớ và biến cấu hình chỉ liên quan đến engine khác hoặc có cách xử lý thay đổi theo phiên bản.

## 1. Ba nhóm bộ nhớ trong MySQL

Có thể chia bộ nhớ theo phạm vi sử dụng thành ba nhóm:

| Nhóm | Phạm vi | Thời gian sử dụng | Ví dụ |
|---|---|---|---|
| Bộ nhớ dùng chung (global/shared memory) | Nhiều kết nối hoặc toàn bộ server cùng sử dụng | Thường tồn tại trong phần lớn vòng đời tiến trình mysqld | InnoDB buffer pool, redo log buffer, metadata cache |
| Bộ nhớ theo kết nối (connection/session memory) | Gắn với một phiên client hoặc thread xử lý phiên đó | Từ khi kết nối được tạo đến khi kết nối kết thúc, tùy cấu trúc | Thread stack, network buffer, session context |
| Vùng làm việc (execution/work area) | Một thao tác hoặc một truy vấn đang chạy | Được cấp phát khi cần và có thể giải phóng sau thao tác | Sort buffer, join buffer, read buffer, internal temporary table |

Sơ đồ khái niệm:

~~~text
Tiến trình MySQL Server (mysqld)
|
+-- Bộ nhớ dùng chung
|   +-- InnoDB buffer pool
|   +-- InnoDB redo log buffer
|   +-- Cache metadata / table definition / table open
|   +-- Performance Schema và cấu trúc quản lý server
|
+-- Các kết nối client
    |
    +-- Kết nối A
    |   +-- Thread / session context
    |   +-- Network buffer
    |   +-- Vùng làm việc khi truy vấn cần
    |
    +-- Kết nối B
    |   +-- Thread / session context
    |   +-- Network buffer
    |   +-- Vùng làm việc khi truy vấn cần
    |
    +-- Kết nối C ...
~~~

Đây là cách phân loại để tư duy và lập kế hoạch. Trong mã nguồn, một số cấu trúc có thể thuộc thread, session, engine hoặc allocator; không phải mọi khoản cấp phát đều nằm gọn trong đúng một hộp.

## 2. Bộ nhớ dùng chung

Bộ nhớ dùng chung được MySQL hoặc storage engine cấp phát để phục vụ nhiều kết nối. Một kết nối không cần tạo bản sao riêng của toàn bộ vùng nhớ này. Ví dụ, hàng nghìn phiên InnoDB có thể cùng truy cập các trang đang nằm trong một buffer pool.

### 2.1. InnoDB buffer pool

InnoDB buffer pool là vùng nhớ lớn thường quan trọng nhất trong cấu hình MySQL dùng InnoDB. Nó lưu các trang dữ liệu và chỉ mục đã được đọc từ tablespace hoặc vừa được cập nhật. Khi một truy vấn cần trang đang có trong buffer pool, InnoDB có thể đọc trang từ RAM thay vì yêu cầu đọc thiết bị lưu trữ.

Buffer pool chứa các trang theo đơn vị page, không phải một bản sao nguyên vẹn của mọi bảng. Các trang được nạp và thay thế theo mẫu truy cập. Trang đã sửa nhưng chưa được ghi xuống tablespace là dirty page; InnoDB ghi các trang này xuống lưu trữ theo cơ chế nền và checkpoint.

Biến cấu hình chính:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
~~~

Ví dụ cấu hình trong file tùy chọn:

~~~ini
[mysqld]
innodb_buffer_pool_size=8G
~~~

Giá trị 8G chỉ là ví dụ minh họa, không phải khuyến nghị cho mọi máy. Kích thước phù hợp phụ thuộc RAM thực có, kích thước tập dữ liệu hoạt động, tải truy vấn, số kết nối, vùng nhớ cho hệ điều hành và các thành phần khác của MySQL. Máy chủ chuyên dụng cho database thường dành phần lớn RAM cho buffer pool, nhưng vẫn phải để đủ bộ nhớ cho phần còn lại và tránh swap.

### 2.2. InnoDB redo log buffer

Redo log buffer là vùng nhớ dùng chung để giữ các bản ghi redo trước khi chúng được ghi vào redo log files. Khi transaction thay đổi dữ liệu, InnoDB tạo thông tin redo cần thiết cho phục hồi. Redo log buffer giúp gom thông tin trong bộ nhớ trước khi ghi log theo cơ chế của InnoDB.

Biến cấu hình:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_log_buffer_size';
~~~

Redo log buffer không phải buffer pool. Buffer pool giữ các trang dữ liệu và chỉ mục; redo log buffer giữ thông tin nhật ký cần thiết để phục hồi thay đổi. Tăng redo log buffer có thể hữu ích khi transaction lớn tạo nhiều redo trước khi log được ghi, nhưng tăng quá mức không tự động làm mọi transaction nhanh hơn.

### 2.3. Cache metadata và cấu trúc quản lý bảng

MySQL và InnoDB giữ nhiều thông tin cấu trúc trong bộ nhớ để tránh đọc và phân tích lại metadata liên tục. Các ví dụ gồm:

- Table definition cache lưu định nghĩa bảng đã được nạp.
- Table open cache giữ các đối tượng bảng đang mở để tái sử dụng.
- InnoDB data dictionary và các cấu trúc nội bộ giữ thông tin về schema, bảng, cột, index và tablespace.

Một số biến liên quan:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'table_open_cache';
SHOW GLOBAL VARIABLES LIKE 'table_definition_cache';
~~~

Các biến này đặt giới hạn hoặc quy mô cache; không nên hiểu rằng MySQL lập tức dành toàn bộ số byte tương ứng với giá trị cấu hình. Cache thực tế tăng theo số đối tượng được sử dụng và cách server quản lý chúng.

### 2.4. Bộ đệm chỉ mục của storage engine khác

Nếu máy chủ còn sử dụng MyISAM, biến key_buffer_size điều khiển vùng nhớ cache các block chỉ mục MyISAM. Đây không phải bộ nhớ cache chỉ mục của InnoDB. InnoDB lưu trang dữ liệu và chỉ mục trong buffer pool.

Vì vậy, không nên tăng key_buffer_size để cải thiện truy vấn trên bảng InnoDB. Trước khi điều chỉnh, hãy xác định storage engine của bảng đang gây tải.

### 2.5. Performance Schema và bộ nhớ nội bộ

Performance Schema dùng bộ nhớ để thu thập thông tin về hoạt động, sự kiện, statement, wait và memory instrument. Nó giúp quan sát máy chủ nhưng cũng có chi phí bộ nhớ riêng. Cấu hình instrument và consumer càng rộng thì dữ liệu quan sát có thể càng nhiều.

Không phải toàn bộ bộ nhớ của mysqld đều được Performance Schema ghi nhận. Kết quả memory instrumentation chỉ phản ánh các khoản cấp phát đã được instrument và đang được theo dõi. Khi đối chiếu với RSS của tiến trình hoặc số RAM hệ điều hành báo cáo, có thể còn chênh lệch do allocator, thư viện, plugin, cấu trúc chưa instrument và memory mapping.

## 3. Bộ nhớ theo kết nối

Khi client kết nối, MySQL tạo ngữ cảnh phiên để theo dõi tài khoản, quyền, database mặc định, biến session, trạng thái transaction, prepared statement và các thông tin cần thiết để xử lý yêu cầu. Trong mô hình one-thread-per-connection phổ biến, một thread phục vụ một kết nối trong thời gian phiên tồn tại.

### 3.1. Thread stack và ngữ cảnh phiên

Mỗi thread cần stack và cấu trúc quản lý riêng. Biến thread_stack điều khiển kích thước stack của thread xử lý kết nối. Ngoài stack, MySQL còn có đối tượng nội bộ lưu trạng thái session, thông tin xác thực, transaction, statement đang thực thi và tài nguyên liên quan.

Thread cache là cơ chế tái sử dụng thread sau khi kết nối kết thúc. Nó giúp giảm chi phí tạo thread mới khi có kết nối tiếp theo; đây không phải vùng nhớ dùng chung cho toàn bộ nội dung truy vấn và cũng không đồng nghĩa mọi thread đã được giải phóng hoàn toàn khỏi bộ nhớ.

Nếu triển khai thread pool, quan hệ giữa số kết nối và số worker thread có thể khác mô hình một thread cho mỗi kết nối. Vì vậy, không nên lấy số kết nối nhân với thread_stack rồi xem đó là toàn bộ bộ nhớ connection.

### 3.2. Network buffer

MySQL cần buffer để nhận và gửi dữ liệu qua kết nối. Biến net_buffer_length xác định kích thước ban đầu của communication buffer; buffer có thể tăng khi câu lệnh hoặc gói dữ liệu cần nhiều chỗ hơn, nhưng không vượt quá giới hạn max_allowed_packet tương ứng.

max_allowed_packet là giới hạn kích thước packet hoặc dữ liệu mà client/server chấp nhận trong một số thao tác. Nó không có nghĩa mỗi kết nối lập tức cấp phát một vùng RAM bằng đúng giá trị này.

Kiểm tra cấu hình:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'net_buffer_length';
SHOW GLOBAL VARIABLES LIKE 'max_allowed_packet';
~~~

Nếu ứng dụng gửi BLOB, JSON hoặc batch dữ liệu lớn, cần kiểm tra giới hạn packet ở cả client và server. Tăng max_allowed_packet chỉ giải quyết giới hạn kích thước; nó không thay thế việc kiểm soát payload và bộ nhớ tiêu thụ khi xử lý dữ liệu lớn.

### 3.3. Biến session và trạng thái transaction

MySQL có biến ở phạm vi GLOBAL, SESSION hoặc cả hai. Biến SESSION áp dụng cho kết nối hiện tại. Biến GLOBAL thường xác định giá trị mặc định cho các kết nối mới đối với biến có phạm vi session; thay đổi giá trị global không nhất thiết thay đổi ngay giá trị session của các kết nối đã tồn tại.

Có thể xem rõ hai phạm vi:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'sort_buffer_size';
SHOW SESSION VARIABLES LIKE 'sort_buffer_size';
~~~

Khi cần điều chỉnh thử cho một kết nối kiểm thử:

~~~sql
SET SESSION sort_buffer_size = 524288;
~~~

Không nên tăng biến session trên toàn bộ hệ thống chỉ để cải thiện một truy vấn đơn lẻ. Mỗi phiên có thể có giá trị riêng, và các giá trị lớn có thể làm tổng mức tiêu thụ RAM tăng mạnh khi nhiều truy vấn đồng thời cần cấp phát vùng làm việc tương ứng.

## 4. Vùng làm việc khi thực thi truy vấn

Vùng làm việc là bộ nhớ MySQL cấp phát để hoàn thành một thao tác cụ thể. Chúng thường chỉ xuất hiện khi truy vấn cần sort, join, scan hoặc tạo bảng tạm. Đây là nhóm bộ nhớ dễ làm RAM tăng đột biến khi nhiều truy vấn nặng chạy đồng thời.

### 4.1. Sort buffer

sort_buffer_size là kích thước vùng nhớ dùng cho thao tác sắp xếp của một thread. Khi truy vấn cần ORDER BY hoặc một thao tác khác yêu cầu sort và không thể đáp ứng trực tiếp bằng index, MySQL có thể cấp phát sort buffer.

Ví dụ:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE status = 'PENDING'
ORDER BY created_at DESC;
~~~

Nếu index không đáp ứng được điều kiện và thứ tự cần thiết, kế hoạch thực thi có thể cần sort. Có thể quan sát kế hoạch bằng EXPLAIN; trong MySQL 8.0.18 trở lên, EXPLAIN ANALYZE giúp xem số liệu thực thi thực tế của câu SELECT.

Kiểm tra giá trị:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'sort_buffer_size';
SHOW SESSION VARIABLES LIKE 'sort_buffer_size';
~~~

Không nên tăng sort_buffer_size ngay khi thấy truy vấn có filesort. Trước tiên hãy kiểm tra index, số hàng phải sắp xếp, cột sort và hình dạng truy vấn. Một sort buffer lớn có thể giúp một số phép sort, nhưng nếu nhiều kết nối cùng sort thì lượng RAM cấp phát có thể tăng nhanh.

### 4.2. Join buffer

join_buffer_size được dùng trong một số phép join khi MySQL không thể dùng index thích hợp để tìm hàng ở bảng được nối. Join buffer có thể được cấp phát cho từng phép join cần nó; một truy vấn có nhiều join không dùng index có thể cần nhiều vùng buffer.

Ví dụ:

~~~sql
SELECT o.order_id, c.full_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PENDING';
~~~

Trong ví dụ này, khóa chính của customers và index trên orders.customer_id có thể hỗ trợ truy cập. Nếu điều kiện JOIN hoặc bộ lọc không có index phù hợp, optimizer có thể chọn phương án join tốn nhiều công việc và dùng join buffer.

Kiểm tra cấu hình:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'join_buffer_size';
SHOW SESSION VARIABLES LIKE 'join_buffer_size';
~~~

Giải pháp ưu tiên là thiết kế index phù hợp với điều kiện JOIN và lọc, đồng thời kiểm tra thứ tự truy cập trong kế hoạch thực thi. Tăng join_buffer_size chỉ nên được cân nhắc sau khi đã hiểu kiểu join, lượng dữ liệu và số truy vấn đồng thời.

### 4.3. Read buffer và read-rnd buffer

Hai biến thường gặp:

- read_buffer_size hỗ trợ đọc tuần tự trong một số thao tác quét bảng hoặc quét index.
- read_rnd_buffer_size hỗ trợ đọc hàng theo thứ tự sau khi sắp xếp trong một số kế hoạch thực thi.

Chúng là vùng làm việc liên quan đến thao tác đọc, không phải cache dùng chung cho mọi kết nối. Tăng chúng có thể làm tăng bộ nhớ khi nhiều phiên cùng thực hiện thao tác tương ứng.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'read_buffer_size';
SHOW GLOBAL VARIABLES LIKE 'read_rnd_buffer_size';
~~~

Nếu truy vấn quét lượng dữ liệu lớn, hãy xem xét điều kiện lọc, index, partition và số hàng cần trả về trước khi điều chỉnh buffer. Đọc nhiều hàng không cần thiết vẫn tốn I/O và CPU ngay cả khi tăng vùng đệm.

### 4.4. Bảng tạm nội bộ

MySQL có thể tạo internal temporary table khi truy vấn cần lưu kết quả trung gian, chẳng hạn một số trường hợp GROUP BY, DISTINCT, UNION hoặc xử lý kết quả phức tạp. Bảng tạm có thể được giữ trong bộ nhớ hoặc chuyển sang lưu trữ trên đĩa khi vượt giới hạn hoặc không phù hợp với engine tạm trong bộ nhớ.

Các biến thường liên quan gồm:

| Biến | Ý nghĩa |
|---|---|
| tmp_table_size | Giới hạn kích thước của internal in-memory temporary table trong các phiên bản có áp dụng biến này cho TempTable |
| max_heap_table_size | Giới hạn kích thước bảng MEMORY; với một số bảng tạm MEMORY, giới hạn hiệu lực là giá trị nhỏ hơn giữa biến này và tmp_table_size |
| temptable_max_ram | Ngưỡng RAM tổng thể mà TempTable engine có thể dùng trước khi chuyển sang cơ chế khác |
| temptable_max_mmap | Giới hạn vùng memory-mapped file mà TempTable có thể sử dụng trước khi chuyển sang InnoDB |

Chi tiết chính xác phụ thuộc phiên bản. Từ MySQL 8.0, TempTable là engine mặc định cho nhiều internal temporary table; từ MySQL 8.0.28, tmp_table_size áp dụng giới hạn cho từng internal in-memory temporary table dùng TempTable. Các bảng vượt giới hạn có thể được chuyển sang InnoDB. Với bảng MEMORY, giới hạn liên quan đến tmp_table_size và max_heap_table_size vẫn cần được xét.

Các bảng tạm trên đĩa không đồng nghĩa MySQL gặp lỗi. Chúng có thể là hành vi bình thường khi truy vấn xử lý tập dữ liệu lớn. Tuy nhiên, tỷ lệ bảng tạm trên đĩa tăng bất thường có thể cho thấy truy vấn, cấu trúc dữ liệu hoặc giới hạn bộ nhớ cần được xem xét.

Kiểm tra cấu hình và thống kê:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
SHOW GLOBAL VARIABLES LIKE 'max_heap_table_size';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_ram';
SHOW GLOBAL VARIABLES LIKE 'temptable_max_mmap';

SHOW GLOBAL STATUS LIKE 'Created_tmp_tables';
SHOW GLOBAL STATUS LIKE 'Created_tmp_disk_tables';
~~~

Hai bộ đếm Created_tmp_tables và Created_tmp_disk_tables là số liệu tích lũy kể từ khi server khởi động hoặc từ lần reset status thích hợp. Để đánh giá xu hướng, hãy ghi nhận chênh lệch trong một khoảng thời gian và so sánh với lượng truy vấn, thay vì chỉ nhìn một con số tuyệt đối.

## 5. Một truy vấn sử dụng những vùng nhớ nào?

Xét một truy vấn có lọc, JOIN và sắp xếp:

~~~sql
SELECT c.customer_id, c.full_name, o.order_id, o.created_at
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PENDING'
ORDER BY o.created_at DESC
LIMIT 100;
~~~

Đường đi khái niệm:

1. Kết nối đã có session context và network buffer.
2. MySQL phân tích SQL, kiểm tra quyền và xây dựng kế hoạch thực thi.
3. InnoDB đọc các trang cần thiết từ buffer pool; nếu trang chưa có trong RAM, engine nạp trang từ tablespace.
4. Nếu phép JOIN cần phương án không có index phù hợp, executor có thể dùng join buffer.
5. Nếu thứ tự kết quả không thể lấy trực tiếp từ index, executor có thể cần sort buffer.
6. Nếu truy vấn cần lưu kết quả trung gian, MySQL có thể tạo internal temporary table.
7. Kết quả được gửi về client qua network buffer.

Không phải truy vấn nào cũng dùng tất cả vùng nhớ trên. Optimizer có thể chọn kế hoạch khác; một index phù hợp có thể tránh sort hoặc giảm lượng hàng phải join. Các vùng làm việc cũng có thể được cấp phát theo nhu cầu, không nhất thiết cùng tồn tại với kích thước tối đa trong suốt phiên.

## 6. Vì sao số kết nối ảnh hưởng đến RAM?

Mỗi kết nối tạo ra chi phí bộ nhớ nền. Khi truy vấn bắt đầu, nó có thể cần thêm work area. Vì thế, hai máy chủ có cùng số kết nối có thể tiêu thụ RAM rất khác nhau:

- Máy A có nhiều kết nối nhàn rỗi, ít truy vấn hoạt động.
- Máy B có cùng số kết nối nhưng nhiều truy vấn đồng thời sắp xếp, join và tạo bảng tạm.

Máy B có thể dùng nhiều RAM hơn đáng kể vì work area tăng theo hoạt động truy vấn. Không thể lấy một con số cố định như sort_buffer_size rồi nhân với max_connections để dự báo chính xác; mỗi buffer có điều kiện cấp phát, thời điểm cấp phát và số lần sử dụng khác nhau.

Một mô hình ước tính tư duy:

~~~text
RAM cho MySQL tại một thời điểm
  ≈ bộ nhớ dùng chung
  + tổng bộ nhớ nền của các kết nối đang tồn tại
  + tổng vùng làm việc của các truy vấn đang hoạt động
  + bộ nhớ plugin, allocator và cấu trúc nội bộ khác
~~~

Đây là mô hình định hướng, không phải công thức đo chính xác. Một số vùng được chia sẻ, một số được tái sử dụng, một số không được Performance Schema instrument; hệ điều hành cũng cần RAM cho page cache, filesystem, agent giám sát và dịch vụ khác.

### 6.1. max_connections không phải số vùng nhớ đã cấp phát

max_connections giới hạn số kết nối client đồng thời được phép. Nó không có nghĩa MySQL cấp phát sẵn toàn bộ bộ nhớ có thể dùng cho từng kết nối ngay khi khởi động.

Tuy vậy, tăng max_connections làm tăng mức tải kết nối mà server có thể nhận. Khi nhiều kết nối đồng thời thực thi truy vấn nặng, nhu cầu RAM có thể tăng vượt dự tính. Nếu không đủ RAM, hệ điều hành có thể swap, tiến trình mysqld có thể bị OOM killer kết thúc hoặc máy chủ trở nên chậm nghiêm trọng.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
~~~

Max_used_connections cho biết đỉnh số kết nối đã dùng kể từ khi server khởi động hoặc từ lần reset status. Hãy dùng số liệu thực tế cùng tải truy vấn để đặt giới hạn, thay vì tăng max_connections chỉ để che lỗi connection pool hoặc kết nối không được đóng đúng cách.

### 6.2. Connection pool giúp kiểm soát tải

Connection pool tái sử dụng một số lượng kết nối hữu hạn. Nó giúp tránh tạo và hủy kết nối liên tục, đồng thời giới hạn số truy vấn có thể đồng thời đi vào database từ một ứng dụng.

Pool không loại bỏ chi phí bộ nhớ theo kết nối. Một pool quá lớn vẫn giữ nhiều session, và nhiều pool từ nhiều instance ứng dụng có thể cộng lại thành lượng kết nối rất lớn. Cần đặt kích thước pool theo tổng số instance, năng lực máy chủ, thời gian truy vấn và nhu cầu concurrency.

Khi ứng dụng không cần giữ transaction, hãy commit hoặc rollback sớm rồi trả kết nối về pool. Transaction kéo dài giữ trạng thái và có thể giữ khóa, read view hoặc tài nguyên liên quan lâu hơn cần thiết.

## 7. Quan sát bộ nhớ bằng Performance Schema

MySQL 8.x cung cấp memory instrumentation qua Performance Schema. Có thể dùng các bảng tổng hợp để xem khoản cấp phát hiện tại và mức cao nhất đã quan sát cho từng event.

### 7.1. Xem các khoản cấp phát toàn server

~~~sql
SELECT
    event_name,
    current_number_of_bytes_used,
    high_number_of_bytes_used
FROM performance_schema.memory_summary_global_by_event_name
ORDER BY current_number_of_bytes_used DESC
LIMIT 20;
~~~

Kết quả giúp tìm các nhóm memory event đang dùng nhiều bộ nhớ nhất trong phạm vi đã instrument. Tên event có thể thay đổi theo phiên bản, và một số event có thể không được bật để thu thập.

### 7.2. Xem bộ nhớ theo thread

~~~sql
SELECT
    t.processlist_id,
    t.processlist_user,
    SUM(m.current_number_of_bytes_used) AS current_bytes
FROM performance_schema.memory_summary_by_thread_by_event_name AS m
JOIN performance_schema.threads AS t
  ON t.thread_id = m.thread_id
WHERE t.type = 'FOREGROUND'
GROUP BY t.thread_id, t.processlist_id, t.processlist_user
ORDER BY current_bytes DESC
LIMIT 20;
~~~

Truy vấn này tổng hợp các khoản cấp phát được instrument theo thread foreground. processlist_id có thể đối chiếu với connection id của client. Một thread nền của InnoDB hoặc thread quản trị có thể không xuất hiện trong danh sách foreground.

### 7.3. Dùng sys schema để xem tổng quan

Nếu sys schema được cài đặt và các memory instrument tương ứng hoạt động, các view như sau có thể giúp đọc kết quả dễ hơn:

~~~sql
SELECT * FROM sys.memory_global_total;

SELECT *
FROM sys.memory_by_thread_by_current_bytes
LIMIT 20;
~~~

Các view sys là lớp trình bày trên dữ liệu Performance Schema. Quyền truy cập, phiên bản và trạng thái instrument có thể ảnh hưởng đến kết quả.

### 7.4. Khi số liệu không đầy đủ

Nếu kết quả trống hoặc thấp hơn nhiều so với RSS của mysqld:

1. Kiểm tra Performance Schema có bật hay không.
2. Kiểm tra các memory instrument cần thiết có được bật trong performance_schema.setup_instruments không.
3. Xác định khoản cấp phát nào không được instrument.
4. So sánh với số liệu từ hệ điều hành, container hoặc hệ thống giám sát.
5. Quan sát xu hướng theo thời gian thay vì kết luận từ một ảnh chụp đơn lẻ.

Không nên bật toàn bộ instrument trên môi trường tải cao mà không đánh giá chi phí quan sát. Hãy bật đúng nhóm cần điều tra và tắt hoặc thu hẹp sau khi hoàn tất nếu chính sách vận hành yêu cầu.

## 8. Cách đọc và điều chỉnh biến bộ nhớ

Khi điều chỉnh cấu hình, cần biết biến thuộc phạm vi nào và thay đổi ảnh hưởng đến đối tượng nào:

| Biến | Phạm vi sử dụng chính | Hướng xem xét |
|---|---|---|
| innodb_buffer_pool_size | Global, InnoDB | Phù hợp với working set và RAM máy chủ |
| innodb_log_buffer_size | Global, InnoDB | Transaction tạo lượng redo lớn |
| thread_stack | Thread xử lý kết nối | Nhu cầu stack và cấu hình thread |
| net_buffer_length | Buffer giao tiếp của kết nối | Kích thước thông điệp trao đổi thường gặp |
| max_allowed_packet | Giới hạn packet/dữ liệu | Payload lớn, BLOB hoặc batch |
| sort_buffer_size | Vùng làm việc cho sort | Sort thực tế và concurrency |
| join_buffer_size | Vùng làm việc cho một số join | Join không có index thích hợp |
| read_buffer_size | Vùng đọc tuần tự | Quét dữ liệu tuần tự |
| read_rnd_buffer_size | Vùng đọc theo thứ tự sau sort | Đọc hàng sau thao tác sắp xếp |
| tmp_table_size | Internal temporary table / MEMORY tùy phiên bản | Kích thước bảng tạm trong bộ nhớ |
| temptable_max_ram | Global, TempTable engine | Tổng RAM TempTable có thể dùng |
| temptable_max_mmap | Global, TempTable engine | Giới hạn vùng memory-mapped temporary data |

### 8.1. Kiểm tra trước khi thay đổi

Ghi lại giá trị hiện tại và xác định phạm vi:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL VARIABLES LIKE 'sort_buffer_size';
SHOW SESSION VARIABLES LIKE 'sort_buffer_size';
SHOW GLOBAL VARIABLES LIKE 'join_buffer_size';
SHOW GLOBAL VARIABLES LIKE 'tmp_table_size';
~~~

Một số biến có thể thay đổi động, một số cần restart hoặc chỉ có hiệu lực với kết nối mới. Hãy kiểm tra tài liệu đúng phiên bản trước khi thực hiện. Khi thay đổi biến GLOBAL có biến thể SESSION, những session đang tồn tại có thể vẫn giữ giá trị riêng.

### 8.2. Điều chỉnh theo bằng chứng

Một quy trình an toàn:

1. Xác định triệu chứng: thiếu RAM, swap, OOM, sort chậm, join chậm hay bảng tạm trên đĩa tăng.
2. Thu thập số liệu từ Performance Schema, status variables, slow query log và hệ điều hành.
3. Tìm truy vấn hoặc loại workload tạo ra khoản cấp phát lớn.
4. Kiểm tra kế hoạch thực thi, index, điều kiện lọc và lượng dữ liệu trung gian.
5. Thử thay đổi nhỏ trong môi trường kiểm thử hoặc trên một session có kiểm soát.
6. Đo lại thời gian truy vấn, throughput, độ trễ, RAM, swap và số bảng tạm trên đĩa.
7. Chỉ triển khai rộng khi kết quả đo chứng minh có lợi và mức sử dụng RAM cực đại vẫn nằm trong giới hạn an toàn.

Ví dụ, nếu một truy vấn ORDER BY tạo sort lớn, hãy kiểm tra index có thể đáp ứng điều kiện lọc và thứ tự sắp xếp hay không. Nếu JOIN cần join buffer lớn, kiểm tra index trên các cột JOIN. Nếu bảng tạm chuyển sang đĩa, hãy kiểm tra số hàng trung gian và cách viết GROUP BY hoặc DISTINCT trước khi tăng giới hạn bộ nhớ.

## 9. Những sai lầm thường gặp

**“Mọi biến buffer đều được cấp phát đầy đủ cho mọi kết nối ngay khi kết nối mở.”** Không đúng. Nhiều vùng làm việc chỉ được cấp phát khi truy vấn cần; cách cấp phát và tái sử dụng phụ thuộc từng thành phần.

**“Tổng RAM bằng buffer pool cộng max_connections nhân tổng các biến buffer.”** Đây chỉ là cách ước tính quá thô. Các biến có phạm vi và điều kiện cấp phát khác nhau; một số buffer được dùng theo từng phép sort hoặc join, một số vùng dùng chung, một số giới hạn không phải lượng RAM được cấp phát.

**“Tăng sort_buffer_size và join_buffer_size luôn làm truy vấn nhanh hơn.”** Không đúng. Nếu vấn đề nằm ở index, số hàng trung gian hoặc kế hoạch thực thi, tăng buffer có thể chỉ làm tăng RAM mà không giảm công việc cần thiết.

**“max_allowed_packet là RAM được dành sẵn cho mỗi kết nối.”** Không đúng. Đây là giới hạn kích thước packet hoặc dữ liệu; buffer giao tiếp có thể tăng khi cần.

**“Buffer pool là bộ nhớ theo kết nối.”** Không đúng. InnoDB buffer pool là vùng nhớ dùng chung cho các kết nối InnoDB.

**“Performance Schema hiển thị toàn bộ RAM của tiến trình.”** Không đúng. Nó hiển thị các khoản cấp phát được instrument; cần đối chiếu thêm với hệ điều hành và công cụ giám sát.

**“Tăng max_connections giải quyết mọi lỗi kết nối.”** Không đúng. Nếu ứng dụng không trả kết nối về pool hoặc transaction kéo dài, tăng giới hạn có thể làm áp lực bộ nhớ và lock nghiêm trọng hơn.

## 10. Quy trình đánh giá bộ nhớ cho một hệ thống MySQL

Khi triển khai hoặc vận hành một database quan hệ, hãy đánh giá theo trình tự:

1. Xác định RAM khả dụng, giới hạn container và các tiến trình cùng chia sẻ máy.
2. Đo mức dùng bộ nhớ thực tế của mysqld và trạng thái swap/OOM ở hệ điều hành.
3. Xem các vùng global, đặc biệt là InnoDB buffer pool, redo log buffer và cache metadata.
4. Xem số kết nối hiện tại, đỉnh kết nối, thread model và cấu hình connection pool.
5. Xác định truy vấn hoạt động có sort, join, scan hoặc internal temporary table lớn.
6. Dùng Performance Schema và sys schema để phân tích các khoản cấp phát đã instrument.
7. Điều chỉnh index và truy vấn trước khi tăng các work area buffer trên diện rộng.
8. Đặt giới hạn kết nối và kích thước pool theo concurrency thực tế, chừa RAM cho hệ điều hành và phần bộ nhớ chưa instrument.
9. Theo dõi sau thay đổi trong điều kiện tải đại diện và có cả thời điểm cao điểm.

Điều cần tối ưu là tổng thể hệ thống: truy vấn hoàn thành trong thời gian phù hợp, server không swap, RAM có dư địa cho tải tăng và các kết nối không tạo ra lượng work area vượt khả năng máy chủ.

## Kết luận

MySQL sử dụng bộ nhớ ở nhiều phạm vi. Bộ nhớ dùng chung như InnoDB buffer pool và redo log buffer phục vụ nhiều kết nối; bộ nhớ theo kết nối giữ thread, network buffer và trạng thái session; vùng làm việc như sort buffer, join buffer, read buffer và bảng tạm được cấp phát theo nhu cầu thực thi.

Số kết nối và mức độ phức tạp của truy vấn cùng quyết định áp lực RAM. Vì thế, cần phân biệt giới hạn cấu hình với lượng bộ nhớ thực sự được cấp phát, theo dõi cả global lẫn thread, kiểm tra truy vấn và index trước khi tăng buffer. Một cấu hình tốt cân bằng được working set, concurrency, vùng làm việc, giới hạn RAM và nhu cầu của hệ điều hành.
