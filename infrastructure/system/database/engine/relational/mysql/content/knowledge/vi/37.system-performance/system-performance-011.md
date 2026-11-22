# Thread pool, cơ chế điều phối và điều kiện edition

Thread pool là cơ chế phía máy chủ dùng một nhóm worker threads để xử lý câu lệnh từ nhiều kết nối client. Thay vì gắn cố định một thread thực thi với mỗi connection, MySQL Enterprise Thread Pool tách kết nối khỏi thread thực thi, đưa câu lệnh vào các nhóm điều phối và giới hạn mức đồng thời phù hợp với tài nguyên máy chủ. Cơ chế này có thể giảm chi phí chuyển ngữ cảnh và tranh chấp khi hệ thống có rất nhiều truy vấn đồng thời.

Điều kiện edition là điểm cần xác định trước khi thiết kế: plugin MySQL Enterprise Thread Pool là thành phần thương mại của MySQL Enterprise Edition. MySQL Community Server sử dụng mô hình xử lý mặc định one-thread-per-connection và không có plugin Enterprise này để bật chỉ bằng cách thay đổi một system variable. Bài học này tập trung vào plugin chính thức của MySQL, cơ chế điều phối và cách quan sát, tinh chỉnh nó.

## 1. Thread pool giải quyết vấn đề nào?

Trong mô hình mặc định, MySQL Server thường tạo một thread xử lý cho mỗi client connection. Với số lượng kết nối và truy vấn đồng thời lớn, mô hình này có thể làm tăng:

- Số thread và vùng stack cần quản lý.
- Chi phí context switch giữa các thread.
- Áp lực lên scheduler của hệ điều hành.
- Mức cạnh tranh CPU cache và bộ nhớ.
- Số transaction chạy đồng thời, từ đó tăng tranh chấp tài nguyên nội bộ của InnoDB.

Thread pool kiểm soát số worker có thể thực thi câu lệnh cùng lúc. Nhiều connection vẫn có thể tồn tại, nhưng chỉ một số worker được điều phối để chạy statement tại một thời điểm. Khi một câu lệnh chờ I/O hoặc khóa, thread pool có thể cho phép worker khác trong cùng group tiếp tục xử lý công việc đang xếp hàng.

Mục tiêu là điều tiết concurrency và cải thiện throughput dưới tải cao. Thread pool không làm cho một câu SQL vốn chậm trở nên nhanh hơn, không thay thế index, không loại bỏ lock contention và không tăng tốc thiết bị lưu trữ.

## 2. Điều kiện edition và phạm vi hỗ trợ

MySQL Enterprise Thread Pool được cung cấp như server plugin trong MySQL Enterprise Edition. Đây là điều kiện sản phẩm, không phải tùy chọn có thể bật trên mọi bản cài MySQL.

| Môi trường | Thread handling |
|---|---|
| MySQL Community Server | Mô hình mặc định one-thread-per-connection |
| MySQL Enterprise Edition có plugin thread_pool | Có thể dùng mô hình thread pool phía server |
| MySQL Enterprise Edition nhưng plugin chưa được nạp | Vẫn dùng thread handling hiện tại; plugin chưa hoạt động |
| Sản phẩm tương thích MySQL của nhà cung cấp khác | Phải kiểm tra tài liệu riêng; không mặc định plugin hoặc biến cấu hình giống MySQL Enterprise |

Không kết luận edition chỉ từ số phiên bản trả về bởi VERSION(). Hãy kiểm tra gói cài đặt, quyền sử dụng sản phẩm và khả năng có thư viện plugin trong plugin directory.

Có thể kiểm tra plugin đang hoạt động:

~~~sql
SELECT
    PLUGIN_NAME,
    PLUGIN_STATUS,
    PLUGIN_TYPE,
    PLUGIN_LIBRARY
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME = 'thread_pool';
~~~

Nếu không có dòng nào, plugin chưa được đăng ký hoặc không có trong server. Nếu có dòng nhưng PLUGIN_STATUS không phải ACTIVE, hãy kiểm tra error log và trạng thái nạp plugin.

Kiểm tra thread handling:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_handling';
SHOW GLOBAL VARIABLES LIKE 'thread_pool%';
~~~

Khi plugin được nạp thành công, thread_handling thường hiển thị loaded-dynamically. Các biến thread_pool chỉ xuất hiện khi plugin hỗ trợ đã được nạp.

## 3. Thread pool khác client connection pool

Hai cơ chế cùng có chữ pool nhưng giải quyết hai vấn đề khác nhau:

| Cơ chế | Vị trí | Quản lý | Mục tiêu |
|---|---|---|---|
| Client connection pool | Trong ứng dụng hoặc connector | Tái sử dụng các kết nối đã mở | Giảm chi phí mở/đóng kết nối và giới hạn số connection từ ứng dụng |
| MySQL Thread Pool | Bên trong MySQL Server | Điều phối worker threads thực thi statement | Giới hạn concurrency phía server và giảm overhead khi có nhiều kết nối |

Connection pool không biết đầy đủ khả năng thực thi của backend. Thread pool không thay thế việc tái sử dụng kết nối ở client. Hai cơ chế độc lập và có thể dùng đồng thời.

Ví dụ, một dịch vụ có thể giữ 100 kết nối trong connection pool. Server vẫn nhận các connection đó, nhưng thread pool có thể chỉ cho một số statement chạy đồng thời trong các thread group. Các statement còn lại chờ đến lượt.

## 4. Kiến trúc: connection, thread group và worker

Thread pool chia các connection thành nhiều thread group. Mỗi group quản lý một tập kết nối và có cơ chế nhận statement, xếp hàng và phân công worker.

Các thành phần chính:

- Connection: phiên client đã kết nối đến MySQL.
- Thread group: nhóm điều phối một tập connection.
- Listener thread: nhận statement mới từ các connection được gán vào group.
- Query worker thread: thực thi statement được chọn từ queue hoặc được chạy trực tiếp.
- Background stall checker: theo dõi group để phát hiện statement bị stall và bảo đảm group không bị nghẽn lâu.
- Priority queues: hàng đợi ưu tiên cao và ưu tiên thấp.

Khi connection được tạo, thread pool phân công nó vào thread group theo round-robin. Kết nối và thread thực thi không còn quan hệ một-một cố định. Một worker có thể xử lý statement từ các connection khác nhau theo lịch điều phối.

## 5. Cách phân công connection vào thread group

Giả sử thread_pool_size được đặt là 4. Thread pool có bốn group với ID 0 đến 3. Khi các connection mới đến, chúng được phân phối luân phiên:

~~~mermaid
flowchart TD
    C[Client connections] --> D[Thread pool dispatcher]
    D --> G0[Group 0]
    D --> G1[Group 1]
    D --> G2[Group 2]
    D --> G3[Group 3]
    G0 --> W0[Listener and query workers]
    G1 --> W1[Listener and query workers]
    G2 --> W2[Listener and query workers]
    G3 --> W3[Listener and query workers]
~~~

Round-robin giúp phân phối connection ban đầu giữa các group. Nó không có nghĩa mọi group luôn có lượng công việc bằng nhau: truy vấn của các connection được gán vào một group có thể có thời lượng và mức tranh chấp rất khác nhóm khác.

thread_pool_size là số thread group, không phải số connection tối đa và cũng không phải số worker cố định. Một group có thể tạo thêm worker khi cần xử lý statement bị stall hoặc bị chặn.

## 6. Listener thread và đường đi của một statement

Mỗi group có listener thread để nhận command từ các connection đã được gán vào group. Khi statement đến, group có hai lựa chọn:

1. Nếu group có thể thực thi ngay, listener có thể bắt đầu xử lý statement.
2. Nếu group đang bận hoặc statement cần chờ, nó được đưa vào queue thích hợp.

Nếu statement hoàn tất nhanh, thread đang thực thi có thể quay lại vai trò listener. Nếu statement kéo dài vượt ngưỡng stall, thread pool có thể tạo hoặc đánh thức worker khác để group tiếp tục nhận statement mới.

Cách dùng listener để thực thi trực tiếp khi group rảnh giúp tránh tạo worker mới không cần thiết trong workload nhẹ. Khi workload tăng, group có thể mở rộng số worker trong giới hạn và quy tắc điều phối.

## 7. Mặc định giới hạn một statement ngắn đang chạy trong mỗi group

Thread pool cố gắng chỉ có tối đa một statement ngắn thực thi tại một thời điểm trong mỗi group. Cách làm này kiểm soát số statement đồng thời và giảm context switch. Tuy nhiên, một statement dài hoặc bị block không nên giữ group đứng yên vô thời hạn.

Nếu statement chạy lâu hơn stall limit, thread pool đánh dấu nó là stalled. Group sau đó có thể cho statement khác bắt đầu, dù statement trước vẫn tiếp tục chạy.

Nếu một thread bị block do row lock, table lock, disk I/O hoặc một hoạt động chờ khác mà server nhận diện được, thread pool có thể xem nó là blocked và cho worker khác chạy. Với một số loại block không được báo qua callback của thread pool, stall checker sẽ phát hiện bằng timeout.

Stalled không có nghĩa statement đã bị hủy, timeout hay rollback. Statement cũ vẫn có thể tiếp tục và dùng tài nguyên; thread pool chỉ không để nó ngăn mọi statement khác trong group bắt đầu.

## 8. Hai hàng đợi ưu tiên

Thread pool có high-priority queue và low-priority queue. Khi worker chọn công việc, nó kiểm tra hàng đợi ưu tiên cao trước, sau đó mới đến hàng đợi ưu tiên thấp.

Quy tắc cơ bản:

- Statement đầu tiên của một transaction được đưa vào low-priority queue.
- Các statement tiếp theo của transaction đang diễn ra có thể được đưa vào high-priority queue.
- Statement của nontransactional engine hoặc statement autocommit được xem như transaction riêng và thường đi vào low-priority queue.
- Có thể đặt thread_pool_high_priority_connection để đưa tất cả statement được xếp hàng từ một session vào high-priority queue.

Ưu tiên các statement tiếp theo trong transaction đang mở giúp transaction có cơ hội hoàn tất, tránh để các transaction mới liên tục chen ngang làm tăng tranh chấp. Tuy vậy, nếu một session được ưu tiên quá cao, các session khác có thể phải chờ lâu hơn.

## 9. Chuyển statement từ low priority lên high priority

Nếu statement chờ trong low-priority queue quá lâu, thread pool có thể chuyển nó lên high-priority queue. Biến thread_pool_prio_kickup_timer điều khiển khoảng thời gian trước khi chuyển.

Trong MySQL 8.4, giá trị mặc định thường là 1000 millisecond. Mỗi group giới hạn tốc độ chuyển tối đa một statement mỗi 10 millisecond, tức khoảng 100 statement mỗi giây.

Cơ chế này giúp tránh starvation cho statement ở low-priority queue. Nếu kickup xảy ra quá thường xuyên, có thể có quá nhiều transaction bắt đầu trước khi các transaction trước hoàn tất; với InnoDB điều đó có thể làm giảm hiệu năng do contention.

Kiểm tra cấu hình:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_pool_prio_kickup_timer';
~~~

Không giảm timer chỉ để làm một truy vấn riêng lẻ được ưu tiên. Hãy xem số liệu PRIO_KICKUPS theo thời gian và tác động đến throughput, latency của các workload khác.

## 10. Stall detection và thread_pool_stall_limit

thread_pool_stall_limit xác định thời gian một statement được phép chạy trước khi được xem là stalled. Đơn vị của biến là khoảng 10 millisecond, không phải millisecond trực tiếp.

Trong MySQL 8.4:

| Giá trị | Thời gian tương ứng |
|---:|---:|
| 4 | 40 ms |
| 6 (mặc định) | 60 ms |
| 10 | 100 ms |
| 100 | 1 giây |
| 600 (tối đa) | 6 giây |

Giá trị thấp giúp group mở worker tiếp theo sớm hơn, giảm nguy cơ một statement chờ lâu làm chặn các statement khác. Đổi lại, nhiều statement có thể bị đánh dấu stalled và phát sinh thêm thread/context switch.

Giá trị cao giảm việc mở worker mới khi workload có truy vấn dài, nhưng có thể làm các truy vấn ngắn chờ lâu hơn nếu group đang chạy statement dài.

Biến này có thể thay đổi động:

~~~sql
SET GLOBAL thread_pool_stall_limit = 10;
SELECT @@GLOBAL.thread_pool_stall_limit;
~~~

Ví dụ đặt 10 tương ứng khoảng 100 ms. Đây chỉ là giá trị minh họa; hãy chọn theo phân bố latency của statement trong workload thật và benchmark trước khi áp dụng.

## 11. Background stall checker

Thread pool có background thread định kỳ kiểm tra trạng thái thread group. Nếu một group bị chiếm bởi statement kéo dài hoặc bị block mà không báo trạng thái phù hợp, stall checker có thể đánh dấu thread stalled và đánh thức hoặc tạo worker để tiếp nhận statement khác.

Điều này giúp tránh tình trạng toàn bộ connection được gán vào một group phải chờ một statement chạy hàng giờ hoặc một binary log dump thread chạy rất lâu.

Stall checker không giải quyết nguyên nhân gốc của statement dài. Nếu workload có truy vấn quét bảng lớn, lock wait hoặc I/O chậm, cần tối ưu query, index, transaction và storage riêng.

## 12. Các biến cấu hình quan trọng

Các biến thread pool chỉ có khi plugin được nạp. Phạm vi và giá trị mặc định có thể thay đổi theo phiên bản; bảng sau mô tả các biến thường dùng trong MySQL 8.4.

| Biến | Ý nghĩa | Ghi chú vận hành |
|---|---|---|
| thread_pool_size | Số thread group | GLOBAL, không dynamic; cần cấu hình lúc khởi động |
| thread_pool_stall_limit | Ngưỡng đánh dấu statement stalled | GLOBAL, dynamic; đơn vị 10 ms |
| thread_pool_prio_kickup_timer | Thời gian trước khi low-priority statement được nâng ưu tiên | GLOBAL, dynamic; đơn vị millisecond |
| thread_pool_query_threads_per_group | Số query worker tối đa mỗi group theo cấu hình | GLOBAL, dynamic |
| thread_pool_high_priority_connection | Đưa statement của session vào high-priority queue | GLOBAL/SESSION, dynamic |
| thread_pool_max_active_query_threads | Giới hạn worker query active trong một group | GLOBAL, dynamic; 0 dùng thuật toán mặc định |
| thread_pool_max_transactions_limit | Giới hạn transaction do thread pool quản lý | GLOBAL; giá trị 0 thường biểu thị không đặt giới hạn này |
| thread_pool_transaction_delay | Độ trễ trước khi bắt đầu transaction mới | GLOBAL, dynamic |
| thread_pool_algorithm | Thuật toán điều phối concurrency | GLOBAL; lựa chọn phụ thuộc workload |
| thread_pool_max_unused_threads | Giới hạn số thread ngủ không sử dụng | GLOBAL, dynamic |

Đọc giá trị thực tế trước khi thay đổi:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'thread_pool%';
~~~

Không sao chép nguyên bộ cấu hình giữa hai server khác số core, storage engine, workload hoặc phiên bản MySQL. Các biến có quan hệ với nhau; thay đổi một biến có thể làm thay đổi concurrency và queue latency của toàn hệ thống.

## 13. thread_pool_size: số thread group

thread_pool_size là tham số quan trọng nhất của thread pool vì nó quyết định số group và ảnh hưởng số statement có thể bắt đầu thực thi đồng thời.

Trong MySQL 8.4, giá trị mặc định là 16, phạm vi thường từ 1 đến 512. Biến này không dynamic; thay đổi cần restart server. Trong tài liệu MySQL 9.7, giá trị mặc định được mô tả theo MIN(VCPU/2, 16), do đó không nên áp dụng một con số mặc định cho mọi nhánh phiên bản.

Một số hướng dẫn tuning trong MySQL 8.4:

- Với workload chủ yếu InnoDB, có thể bắt đầu thử nghiệm gần số physical CPU cores, tối đa 512.
- Với workload chủ yếu MyISAM, giá trị thấp hơn, thường thử trong khoảng 4 đến 8.
- Đo throughput, p95/p99 latency, CPU và queue behavior thay vì chỉ nhìn số connection.

Các con số trên là điểm bắt đầu để benchmark, không phải công thức bảo đảm tối ưu. Số logical CPU, giới hạn container, NUMA, tốc độ storage và tỷ lệ truy vấn ngắn/dài đều có thể làm kết quả khác nhau.

## 14. thread_pool_query_threads_per_group

Biến này điều khiển số query worker được phép hoạt động trong mỗi group. Giá trị mặc định thường là 1. Tăng giá trị có thể giúp khi một group có nhiều statement dài hoặc transaction chờ lâu khiến response time của truy vấn ngắn tăng.

Tăng worker trên mỗi group cũng làm tăng mức concurrency và chi phí polling/điều phối. Nếu thread_pool_size đã lớn, tăng thêm query threads per group có thể tạo quá nhiều statement đồng thời và làm tăng contention.

Tài liệu MySQL 8.4 gợi ý có thể bắt đầu benchmark với giá trị 2 cho biến này, sau đó đo theo workload. Không áp dụng con số đó mà không kiểm tra CPU, lock wait và latency.

## 15. Điều tiết số transaction

Một số workload InnoDB giảm throughput khi quá nhiều transaction bắt đầu đồng thời. Thread pool có thể điều tiết transaction bằng các biến như:

- thread_pool_max_transactions_limit: giới hạn số transaction mà thread pool cho phép.
- thread_pool_transaction_delay: trì hoãn thời điểm bắt đầu transaction mới.
- thread_pool_longrun_trx_limit: tham số hỗ trợ xử lý transaction kéo dài khi giới hạn transaction đang được dùng.

thread_pool_max_transactions_limit bằng 0 là cấu hình mặc định không áp dụng giới hạn transaction này. Khi đặt một giới hạn dương, thread có thể được gắn với transaction cho đến khi transaction commit hoặc rollback. Vì vậy, nếu transaction không kết thúc, các kết nối mới có thể phải chờ.

Giới hạn transaction là công cụ kiểm soát concurrency, không phải cách sửa transaction bị mở quá lâu. Trước khi bật, cần đo thời lượng transaction, số connection, số transaction active và cách ứng dụng commit/rollback.

Nếu giới hạn khiến mọi kết nối bị chặn, MySQL Enterprise Thread Pool hỗ trợ privileged connection dành cho tài khoản có TP_CONNECTION_ADMIN. Kết nối đặc quyền được đưa vào Admin thread group và có thể được dùng để điều chỉnh giới hạn hoặc xử lý transaction bị kẹt. Quyền này cần được cấp có chủ đích, không cấp cho tài khoản ứng dụng thông thường.

## 16. Queue priority theo transaction và autocommit

Điều phối ưu tiên có liên hệ với ranh giới transaction:

1. Statement đầu tiên trong transaction đi vào low-priority queue.
2. Khi transaction đã bắt đầu, statement tiếp theo của transaction đó có thể được đưa vào high-priority queue.
3. Với autocommit, mỗi statement là một transaction riêng nên thường được xếp ở low priority.
4. Statement của nontransactional engine cũng được xem như statement riêng.

Đây là lý do hai truy vấn giống nhau có thể được xếp khác nhau tùy session đang ở trong transaction hay không. Khi thiết kế ứng dụng, hãy giữ transaction ngắn và commit/rollback rõ ràng để tránh giữ tài nguyên trong lúc chờ client.

## 17. thread_pool_high_priority_connection

Biến thread_pool_high_priority_connection cho phép điều chỉnh queue của một session. Khi bật, tất cả statement được xếp hàng từ session đó đi vào high-priority queue.

Ví dụ:

~~~sql
SET SESSION thread_pool_high_priority_connection = 1;
SELECT @@SESSION.thread_pool_high_priority_connection;
~~~

Giá trị mặc định là 0. Khi bật, statement của session có thể được xử lý trước các statement ở low-priority queue. Điều này có thể hữu ích cho một kết nối quản trị hoặc workload cần độ trễ thấp, nhưng sử dụng rộng rãi có thể làm các session bình thường bị đói tài nguyên.

Không bật biến này cho mọi connection trong connection pool. Nếu ứng dụng đặt giá trị ở session, cần reset session state khi connection được tái sử dụng.

## 18. Điều kiện edition khi triển khai plugin

Vì thread pool là plugin thương mại của MySQL Enterprise Edition, quy trình triển khai phải bắt đầu bằng xác nhận edition và file plugin có sẵn.

Các bước tổng quát:

1. Xác nhận server là MySQL Enterprise Edition và quyền sử dụng hợp lệ.
2. Kiểm tra plugin directory bằng biến plugin_dir.
3. Xác nhận thư viện thread_pool có trong thư mục plugin.
4. Cấu hình plugin-load-add lúc khởi động.
5. Restart theo maintenance plan.
6. Kiểm tra plugin status và các monitoring tables.
7. Chỉ sau khi xác nhận plugin ACTIVE mới tinh chỉnh các biến thread_pool.

Đọc thư mục plugin:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'plugin_dir';
~~~

Tên thư viện cơ bản là thread_pool. Phần mở rộng phụ thuộc hệ điều hành: thường là .so trên Unix/Linux và .dll trên Windows.

## 19. Nạp plugin khi khởi động

Ví dụ cấu hình trên Linux:

~~~ini
[mysqld]
plugin-load-add=thread_pool.so
~~~

Ví dụ trên Windows:

~~~ini
[mysqld]
plugin-load-add=thread_pool.dll
~~~

Đặt file plugin trong thư mục được plugin_dir chỉ định hoặc cấu hình plugin_dir lúc khởi động cho đúng vị trí. Không chép thư viện từ một bản MySQL hoặc hệ điều hành khác nếu chưa xác nhận tương thích ABI và phiên bản.

Sau khi restart, kiểm tra:

~~~sql
SHOW PLUGINS;

SELECT PLUGIN_NAME, PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME = 'thread_pool';

SHOW GLOBAL VARIABLES LIKE 'thread_handling';
~~~

Plugin cần có trạng thái ACTIVE. Nếu không nạp được, đọc error log để tìm nguyên nhân như không tìm thấy thư viện, sai quyền truy cập, không tương thích binary hoặc plugin không được hỗ trợ bởi edition đang dùng.

## 20. Theo dõi bằng Performance Schema

Trong MySQL 8.4, các bảng giám sát thread pool nằm trong Performance Schema và được nạp cùng plugin:

| Bảng | Mục đích |
|---|---|
| performance_schema.tp_connections | Thông tin về các connection thuộc thread pool |
| performance_schema.tp_thread_group_state | Snapshot trạng thái từng thread group |
| performance_schema.tp_thread_group_stats | Bộ đếm hoạt động theo thread group |
| performance_schema.tp_thread_state | Trạng thái và hoạt động của từng thread pool worker |

Các bảng này chỉ tồn tại khi plugin thread pool được nạp và bật. Dữ liệu là snapshot hoặc bộ đếm hoạt động; chúng không thay thế hệ thống time-series monitoring. Các phiên bản cũ có thể dùng bảng INFORMATION_SCHEMA cho thread pool; kiểm tra đúng tài liệu phiên bản trước khi viết công cụ giám sát.

Liệt kê bảng có sẵn:

~~~sql
SHOW TABLES FROM performance_schema LIKE 'tp%';
~~~

## 21. Đọc thống kê theo thread group

tp_thread_group_stats cung cấp một dòng cho mỗi thread group. Các cột hữu ích:

- TP_GROUP_ID: ID của group.
- CONNECTIONS_STARTED và CONNECTIONS_CLOSED: số connection bắt đầu/kết thúc.
- QUERIES_EXECUTED: số statement bắt đầu thực thi; bộ đếm tăng khi statement bắt đầu, không phải khi hoàn tất.
- QUERIES_QUEUED: số statement phải xếp hàng; không tính statement được thực thi ngay.
- THREADS_STARTED: số thread đã được tạo.
- PRIO_KICKUPS: số statement được chuyển từ low queue lên high queue.
- STALLED_QUERIES_EXECUTED: số statement bị đánh dấu stalled.
- ROW_LOCK_WAITS, DISK_IO_WAITS, META_DATA_LOCK_WAITS: các bộ đếm wait theo loại.

Truy vấn:

~~~sql
SELECT
    TP_GROUP_ID,
    CONNECTIONS_STARTED,
    CONNECTIONS_CLOSED,
    QUERIES_EXECUTED,
    QUERIES_QUEUED,
    THREADS_STARTED,
    PRIO_KICKUPS,
    STALLED_QUERIES_EXECUTED,
    ROW_LOCK_WAITS,
    DISK_IO_WAITS,
    META_DATA_LOCK_WAITS
FROM performance_schema.tp_thread_group_stats
ORDER BY TP_GROUP_ID;
~~~

QUERIES_QUEUED tăng nhanh có thể cho thấy group thường xuyên phải xếp hàng. STALLED_QUERIES_EXECUTED tăng nhanh có thể cho thấy nhiều statement vượt stall limit. ROW_LOCK_WAITS hoặc DISK_IO_WAITS tăng cho thấy cần điều tra lock hoặc I/O chứ không chỉ tăng số worker.

## 22. Đọc trạng thái worker

tp_thread_state có một dòng cho mỗi thread được thread pool tạo ra. Các cột đáng chú ý:

- TP_GROUP_ID và TP_THREAD_NUMBER xác định group và thread.
- TP_THREAD_TYPE cho biết loại thread như query worker, listener worker hoặc timer worker.
- STATE mô tả thread đang polling, xử lý trực tiếp, xử lý queued, ngủ ở vai trò consumer hoặc reserve.
- WAIT_TYPE cho biết loại wait nếu thread đang bị block.
- MARKED_STALLED cho biết stall checker đã đánh dấu thread stalled hay chưa.
- EXEC_COUNT và ACCUMULATED_EXEC_TIME cho biết số statement và thời gian thực thi tích lũy.

Ví dụ:

~~~sql
SELECT
    TP_GROUP_ID,
    TP_THREAD_NUMBER,
    TP_THREAD_TYPE,
    STATE,
    WAIT_TYPE,
    MARKED_STALLED,
    EXEC_COUNT,
    ACCUMULATED_EXEC_TIME
FROM performance_schema.tp_thread_state
ORDER BY TP_GROUP_ID, TP_THREAD_NUMBER;
~~~

WAIT_TYPE có thể cho biết thread đang chờ row lock, metadata lock, disk I/O, group commit hoặc fsync. Kết hợp các giá trị này với process list, transaction và lock metadata để tìm nguyên nhân gốc.

## 23. So sánh số liệu qua các khoảng thời gian

Các bộ đếm trong tp_thread_group_stats là số tích lũy. Một snapshot đơn lẻ cho biết tổng kể từ khi plugin hoặc server khởi động, không trực tiếp cho biết tốc độ tăng trong phút gần nhất.

Quy trình đo:

1. Lấy snapshot tại thời điểm T1.
2. Chờ một khoảng thời gian đủ đại diện, ví dụ 60 giây trong giờ tải ổn định.
3. Lấy snapshot T2.
4. Tính delta T2 - T1 cho QUERIES_EXECUTED, QUERIES_QUEUED, STALLED_QUERIES_EXECUTED và wait counters.
5. So sánh các delta với TPS, p95/p99 latency, CPU, I/O và số connection.

Ví dụ tỷ lệ statement bị stalled trong một khoảng:

~~~sql
SELECT
    SUM(STALLED_QUERIES_EXECUTED) /
    NULLIF(SUM(QUERIES_EXECUTED), 0) AS stalled_ratio
FROM performance_schema.tp_thread_group_stats;
~~~

Đây là tỷ lệ trên bộ đếm hiện tại kể từ khi khởi động/reset thống kê. Khi so sánh một khoảng thời gian, hãy tính trên delta của hai snapshot để tránh trộn lịch sử dài với tải hiện tại.

Không dùng TRUNCATE để xóa các bảng thread pool monitoring; các bảng này có hạn chế thao tác và phục vụ plugin.

## 24. Đọc status variables cùng thread pool metrics

Thread pool không nên được đánh giá chỉ bằng một bảng riêng. Hãy đối chiếu với status variables:

~~~sql
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_created';
SHOW GLOBAL STATUS LIKE 'Threads_cached';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
~~~

Ý nghĩa:

- Threads_running: số thread đang thực thi statement tại thời điểm đọc.
- Threads_connected: số connection đang mở.
- Threads_created: số thread đã được tạo để xử lý connection theo thống kê của server.
- Threads_cached: số thread trong cache nếu thread cache được dùng.
- Max_used_connections: số connection đồng thời cao nhất kể từ khi server khởi động hoặc reset status.

Với thread pool, quan hệ giữa connection và query worker không còn một-một. Vì vậy không lấy Threads_connected làm đại diện trực tiếp cho số worker đang thực thi.

## 25. Tuning theo workload

Một quy trình tuning thực tế:

1. Xác nhận edition, plugin status và phiên bản.
2. Đo baseline khi chưa thay đổi tham số: throughput, p95/p99 latency, CPU, I/O, Threads_running, queue và wait counters.
3. Phân loại workload: nhiều truy vấn ngắn, hỗn hợp ngắn/dài, nhiều transaction ghi, hoặc chủ yếu đọc.
4. Chọn thread_pool_size theo số physical cores và storage engine làm điểm bắt đầu.
5. Benchmark thread_pool_query_threads_per_group để cân bằng số group với số worker mỗi group.
6. Điều chỉnh thread_pool_stall_limit theo phân bố thời lượng statement.
7. Theo dõi PRIO_KICKUPS và cân nhắc thread_pool_prio_kickup_timer nếu queue aging quá thường xuyên.
8. Chỉ bật transaction limit/delay khi đã xác định vấn đề do concurrency transaction.
9. Đo lại bằng cùng bộ truy vấn và mức tải.
10. Ghi lại cấu hình cũ, cấu hình mới, kết quả và kế hoạch rollback.

Không thay nhiều biến cùng lúc. Nếu throughput tăng nhưng p99 latency hoặc lock wait xấu đi, cần đánh giá trade-off thay vì chỉ nhìn TPS.

## 26. Khi nào thread pool có thể hữu ích?

Thread pool thường đáng thử nghiệm khi:

- Có rất nhiều client connection đồng thời.
- Threads_running thường xuyên cao và context switching đáng kể.
- Workload có nhiều statement ngắn, chi phí điều phối thread trở thành một phần đáng kể.
- Máy chủ có nhiều CPU core nhưng hiệu năng giảm khi concurrency tăng quá mức.
- InnoDB bị contention do quá nhiều transaction hoạt động cùng lúc.

Thread pool có thể không mang lại lợi ích rõ rệt khi:

- Số connection và concurrency vốn thấp.
- Workload chủ yếu bị giới hạn bởi disk I/O hoặc storage latency.
- Truy vấn dài, quét dữ liệu lớn hoặc thiếu index là nguyên nhân chính.
- Lock contention trong ứng dụng đã chi phối response time.
- Server không có edition/plugin tương ứng.

Thread pool là công cụ điều phối concurrency. Nó không phải một giải pháp tổng quát cho mọi dạng chậm của MySQL.

## 27. Thread pool và connection limit

thread_pool_size không giới hạn số connection client. Số connection vẫn chịu ảnh hưởng của max_connections và các giới hạn khác.

Một server có thể có nhiều connection Sleep trong khi chỉ một số statement đang thực thi. Ngược lại, nếu queue tích tụ, connection client có thể vẫn được mở nhưng statement phải chờ worker.

Do đó, khi điều tra hiện tượng connection timeout hoặc ứng dụng thấy latency tăng, hãy kiểm tra cả:

- Threads_connected và Max_used_connections.
- Threads_running.
- QUERIES_QUEUED theo thread group.
- STALLED_QUERIES_EXECUTED.
- CPU utilization và run queue của hệ điều hành.
- Lock waits, disk I/O waits và thời gian statement.

Nếu chỉ tăng max_connections, server có thể nhận thêm connection nhưng không tăng năng lực xử lý statement. Trong một số tình huống, điều đó còn làm queue dài hơn và bộ nhớ tiêu thụ cao hơn.

## 28. Thread pool không thay thế tối ưu truy vấn

Nếu một truy vấn đọc hàng triệu dòng do thiếu index, thread pool không làm lượng công việc đó biến mất. Nếu transaction giữ khóa lâu, các transaction khác vẫn có thể phải chờ. Nếu buffer pool không đủ hoặc storage chậm, worker vẫn phải đợi I/O.

Khi queue tăng, hãy kiểm tra:

- EXPLAIN hoặc EXPLAIN ANALYZE cho truy vấn tốn thời gian.
- Rows examined và rows sent.
- Slow query log và statement digest.
- Transaction age và lock wait.
- InnoDB buffer pool hit behavior và disk I/O.

Chỉ tăng concurrency sau khi đã hiểu workload. Nhiều worker hơn có thể làm CPU, memory bandwidth và storage contention tăng mạnh.

## 29. Lỗi thường gặp khi triển khai và vận hành

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy biến thread_pool | Plugin chưa được nạp hoặc edition không có plugin | Kiểm tra edition, plugin directory, SHOW PLUGINS |
| Plugin không ACTIVE | Thư viện thiếu, sai suffix hoặc không tương thích | Đọc error log và kiểm tra plugin_dir |
| Thay thread_pool_size bằng SET GLOBAL thất bại | Biến không dynamic | Cấu hình lúc startup và restart theo kế hoạch |
| Queue tăng dù Threads_connected chưa cao | Một số group có thể đang bận hoặc lệch tải | Xem tp_thread_group_stats theo từng group |
| Stalled query tăng | Statement vượt stall limit hoặc bị block lâu | Kiểm tra truy vấn, wait type và stall_limit |
| PRIO_KICKUPS tăng nhanh | Low-priority queue thường xuyên phải nâng ưu tiên | Xem transaction duration, queue pressure và timer |
| Tăng query threads làm latency xấu đi | Concurrency tăng gây contention | Quay lại cấu hình trước và benchmark từng bước |
| Connection pool lớn nhưng throughput không tăng | Số connection không đồng nghĩa số worker thực thi | Đọc queue, active workers và resource saturation |
| Dùng biến MariaDB cho MySQL | Plugin và tên biến khác nhau giữa sản phẩm | Dùng đúng manual và edition của server |
| Community Server không nạp được thread_pool | Plugin Enterprise không có trong bản cài | Dùng thread-per-connection, connection pool và tuning khác; hoặc đánh giá Enterprise Edition |

## 30. Quy trình quyết định có bật thread pool hay không

1. Xác định MySQL edition và phiên bản chính xác.
2. Kiểm tra số physical cores, RAM, storage và loại workload.
3. Thu thập baseline Threads_running, connection count, TPS, latency và CPU.
4. Xác nhận vấn đề có phải do concurrency/context switching hay do query, lock hoặc I/O.
5. Nếu edition hỗ trợ, thử plugin trên môi trường staging với workload đại diện.
6. Chọn thread_pool_size và các biến điều phối làm cấu hình ban đầu.
7. Quan sát queue, stalled queries, priority kickups và wait counters.
8. So sánh throughput lẫn p95/p99 latency trước/sau.
9. Kiểm tra ảnh hưởng đến các session ưu tiên thấp và transaction dài.
10. Triển khai production theo maintenance plan, lưu cấu hình và kế hoạch rollback.

Nếu server không có Enterprise Thread Pool, không cố bật bằng cách thêm tên biến vào file cấu hình. Hãy chọn giải pháp phù hợp edition: giới hạn connection ở ứng dụng, dùng connection pool, kiểm soát concurrency ở tầng dịch vụ, tối ưu query và theo dõi thread metrics hiện có.

## 31. Bài tập thực hành

1. Giải thích khác nhau giữa client connection pool và MySQL server thread pool.
2. Kiểm tra edition, plugin status, plugin_dir và thread_handling trên một server MySQL.
3. Giải thích vì sao MySQL Community Server không thể bật MySQL Enterprise Thread Pool chỉ bằng SET GLOBAL.
4. Vẽ luồng từ connection đến thread group, listener, queue và query worker.
5. Với thread_pool_size = 4, mô tả cách connection mới được phân phối round-robin.
6. Giải thích vì sao thread pool cố gắng giới hạn một statement ngắn đang chạy trong mỗi group.
7. Mô tả điều gì xảy ra khi statement vượt thread_pool_stall_limit.
8. Phân biệt high-priority queue và low-priority queue; giải thích vai trò của transaction.
9. Thay đổi thread_pool_high_priority_connection trong session test và mô tả rủi ro nếu bật cho mọi connection.
10. Tính thời gian thực tế khi thread_pool_stall_limit = 10 và khi = 600.
11. Dùng tp_thread_group_stats để xem QUERIES_QUEUED, STALLED_QUERIES_EXECUTED và PRIO_KICKUPS.
12. Dùng tp_thread_state để xác định worker đang chạy, ngủ hoặc chờ row lock.
13. Lấy hai snapshot cách nhau 60 giây và tính delta của queue/stall counters.
14. Thiết kế benchmark so sánh thread_pool_size và thread_pool_query_threads_per_group trên workload ngắn/dài hỗn hợp.
15. Viết runbook rollback nếu thread pool làm p99 latency tăng hoặc queue tích tụ.

Bạn hoàn thành bài khi giải thích được điều kiện edition của MySQL Enterprise Thread Pool, mô tả được cách connection được phân vào thread group và statement được chọn từ hai priority queues, hiểu cơ chế stall detection, đồng thời biết đọc Performance Schema để đánh giá hiệu quả điều phối. Hãy quyết định bật và tinh chỉnh thread pool dựa trên workload cùng số liệu đo, không dựa riêng vào số connection.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual, MySQL Enterprise Thread Pool: https://dev.mysql.com/doc/refman/8.4/en/thread-pool.html
- MySQL 8.4 Reference Manual, Thread Pool Installation: https://dev.mysql.com/doc/refman/8.4/en/thread-pool-installation.html
- MySQL 8.4 Reference Manual, Thread Pool Operation: https://dev.mysql.com/doc/refman/8.4/en/thread-pool-operation.html
- MySQL 8.4 Reference Manual, Thread Pool Tuning: https://dev.mysql.com/doc/refman/8.4/en/thread-pool-tuning.html
- MySQL 8.4 Reference Manual, Performance Schema Thread Pool Tables: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-thread-pool-tables.html
- MySQL 8.4 Reference Manual, MySQL Enterprise Thread Pool FAQ: https://dev.mysql.com/doc/refman/8.4/en/faqs-thread-pool.html
