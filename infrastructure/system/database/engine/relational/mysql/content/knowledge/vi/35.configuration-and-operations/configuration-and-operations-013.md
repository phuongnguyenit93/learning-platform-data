# Kiểm tra sức khỏe và xây dựng sổ tay vận hành có thể thực hiện lại

Một máy chủ MySQL trả lời được kết nối chưa chắc đã sẵn sàng phục vụ nghiệp vụ. Kết nối có thể thành công trong khi connection pool gần cạn, truy vấn bị khóa, replica chậm, dung lượng đĩa sắp hết hoặc bản sao lưu gần nhất chưa từng được kiểm tra phục hồi. Kiểm tra sức khỏe có ý nghĩa khi nó đánh giá được nhiều lớp của hệ thống và chỉ ra hành động tiếp theo.

Một sổ tay vận hành (runbook) tốt biến kinh nghiệm xử lý sự cố thành quy trình mà người khác có thể lặp lại: biết khi nào bắt đầu, cần quyền gì, chạy lệnh nào, kết quả bình thường trông ra sao, khi nào dừng, cách xác minh sau xử lý và khi nào phải chuyển cấp. Runbook cần dựa trên số liệu của chính hệ thống, có phiên bản và được diễn tập định kỳ.

Bài học thuộc chương **Cấu hình và vận hành** của module **DATABASE_MYSQL**. Trong phạm vi làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời, kỹ năng kiểm tra sức khỏe và viết runbook giúp vận hành cơ sở dữ liệu nhất quán, phát hiện bất thường sớm và giảm rủi ro khi thay đổi cấu hình.

## 1. Sức khỏe MySQL gồm nhiều lớp

Không có một câu lệnh duy nhất xác nhận toàn bộ hệ thống khỏe mạnh. Hãy tách kiểm tra thành các lớp để tránh bỏ sót:

| Lớp | Câu hỏi cần trả lời | Ví dụ tín hiệu |
|---|---|---|
| Tiến trình và kết nối | mysqld có hoạt động và nhận kết nối không? | mysqladmin ping, SELECT 1, Uptime |
| Vai trò và khả năng phục vụ | Đây là primary hay replica? Có được phép ghi không? | read_only, super_read_only, trạng thái replication |
| Tài nguyên kết nối | Có nguy cơ cạn connection không? | Threads_connected, Threads_running, Max_used_connections |
| Truy vấn và tải | Truy vấn có tăng độ trễ hoặc đọc quá nhiều dữ liệu không? | digest statistics, slow log, rows examined |
| Transaction và khóa | Có transaction kéo dài hoặc lock wait không? | innodb_trx, data_lock_waits, deadlocks |
| InnoDB và lưu trữ | Buffer pool, redo, bảng và index có dấu hiệu bất thường không? | InnoDB status, buffer pool counters, table statistics |
| Hạ tầng | CPU, RAM, filesystem và network còn đủ không? | OS metrics, disk free, I/O latency |
| Replication và tính sẵn sàng | Replica có theo kịp? Failover có thể thực hiện không? | Replica status, GTID, group replication status |
| Backup và phục hồi | Có bản backup hợp lệ và đã thử restore không? | backup age, restore test, binlog coverage |
| Bảo mật và cấu hình | Quyền, TLS, audit và cấu hình có đúng chuẩn không? | users/grants, variables, error log |

Kết quả kiểm tra nên phân thành ít nhất ba trạng thái:

- **OK**: tín hiệu nằm trong ngưỡng đã thống nhất và không có điều kiện bất thường.
- **WARN**: có xu hướng xấu hoặc một giới hạn đang đến gần; cần theo dõi hay điều tra.
- **CRITICAL**: đã ảnh hưởng dịch vụ hoặc có nguy cơ mất dữ liệu, không thể ghi/đọc theo yêu cầu, hoặc sắp cạn tài nguyên thiết yếu.

Không dùng một ngưỡng chung cho mọi hệ thống. Ví dụ 70% max_connections có thể bình thường với workload ổn định, nhưng nguy hiểm nếu số kết nối tăng nhanh và pool đang retry liên tục. Ngưỡng phải gắn với baseline, tốc độ tăng, SLO và khả năng dự phòng.

## 2. Xác nhận máy chủ đang hoạt động và đúng vai trò

Có thể kiểm tra tiến trình bằng mysqladmin:

~~~bash
mysqladmin --host=db01.example.internal --user=healthcheck --password ping
~~~

mysqladmin ping kiểm tra mysqld có phản hồi hay không. Kết quả ping thành công không chứng minh người dùng nghiệp vụ có quyền truy cập, truy vấn có thể hoàn thành hoặc replica đã theo kịp. Đặc biệt, mysqladmin ping có thể trả exit code thành công ngay cả khi máy chủ đang chạy nhưng từ chối xác thực; vì vậy hãy xem cả thông báo, sau đó kiểm tra bằng một kết nối SQL đã xác thực.

Kiểm tra qua một kết nối SQL đã xác thực:

~~~sql
SELECT
    NOW(6) AS checked_at,
    VERSION() AS mysql_version,
    @@version_comment AS distribution,
    @@hostname AS server_host,
    @@port AS server_port,
    @@server_id AS server_id,
    @@server_uuid AS server_uuid,
    @@global.read_only AS read_only,
    @@global.super_read_only AS super_read_only;
~~~

Kết quả giúp xác nhận phiên đang nói chuyện với máy chủ nào và máy chủ có cho phép ghi hay không. Với MySQL 8.0, read_only và super_read_only là các biến quan trọng khi phân biệt primary và replica. Nếu vận hành phiên bản cũ hơn, kiểm tra biến có sẵn và tài liệu đúng phiên bản.

Đừng suy ra vai trò chỉ từ hostname hoặc tên DNS. Một endpoint có thể được chuyển sang node khác sau failover. Runbook cần xác minh server_uuid, server_id, read_only/super_read_only và trạng thái replication trước khi chạy thao tác ghi hoặc thay đổi cấu hình.

Kiểm tra thời gian hoạt động:

~~~sql
SHOW GLOBAL STATUS LIKE 'Uptime';
~~~

Uptime là số giây kể từ khi server khởi động. Uptime thấp có thể phản ánh restart có kế hoạch, crash, failover hoặc triển khai mới. Cần đối chiếu lịch thay đổi, error log và thời điểm bắt đầu sự cố. Uptime cao không tự động chứng minh server ổn định; một máy chủ có thể hoạt động lâu nhưng đang tích lũy transaction hoặc tài nguyên bị rò rỉ.

## 3. Kiểm tra kết nối và khả năng nhận truy vấn

Một kiểm tra readiness tối thiểu nên thực thi truy vấn thực sự:

~~~sql
SELECT 1 AS database_ready, NOW(6) AS checked_at;
~~~

Nếu ứng dụng cần xác nhận truy cập schema nghiệp vụ, có thể đọc một bảng health-check chuyên dụng hoặc một bảng cấu hình nhỏ bằng tài khoản ứng dụng. Không dùng một truy vấn nặng chỉ để kiểm tra readiness.

Phân biệt:

- **Liveness**: tiến trình MySQL còn hoạt động và có thể phản hồi.
- **Readiness**: node này có thể phục vụ loại traffic dự kiến, có kết nối, quyền và trạng thái phù hợp.
- **Business health**: các thao tác nghiệp vụ quan trọng có thể hoàn thành trong thời gian cho phép.

Ví dụ, replica có thể liveness và readiness cho truy vấn đọc, nhưng không sẵn sàng cho ghi vì read_only đang bật. Một primary vẫn có thể trả SELECT 1 trong khi connection pool gần cạn hoặc truy vấn ghi đang chờ khóa.

Nếu dùng load balancer hoặc proxy, kiểm tra cả đường kết nối qua proxy và đường trực tiếp đến node khi runbook cho phép. Hai đường có thể có DNS, TLS, routing và giới hạn connection khác nhau.

## 4. Chụp trạng thái kết nối và mức sử dụng connection

Các biến trạng thái sau thường hữu ích:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects',
    'Aborted_clients',
    'Uptime'
);
~~~

Ý nghĩa:

- **Threads_connected**: số connection hiện đang mở.
- **Threads_running**: số thread đang hoạt động, không ở trạng thái ngủ; đây không phải số truy vấn CPU-bound chính xác.
- **Max_used_connections**: mức connection đồng thời cao nhất kể từ khi server khởi động hoặc trạng thái được reset.
- **Connections**: tổng số lần thử kết nối đến server kể từ khi khởi động.
- **Aborted_connects**: số lần kết nối thất bại.
- **Aborted_clients**: số connection bị đóng không đúng cách sau khi đã kết nối.
- **Uptime**: thời gian từ lần khởi động gần nhất.

Đọc các biến này cùng max_connections:

~~~sql
SELECT
    @@global.max_connections AS max_connections,
    @@global.max_user_connections AS max_user_connections;
~~~

Tỷ lệ sử dụng tức thời có thể tính gần đúng bằng Threads_connected / max_connections. Mức cao kéo dài hoặc tăng nhanh là tín hiệu cần điều tra. Max_used_connections cho biết đỉnh lịch sử, nhưng sau restart số liệu lịch sử bắt đầu lại nên phải lưu snapshot ở hệ thống giám sát bên ngoài.

Xem connection đang mở:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Hoặc dùng Performance Schema:

~~~sql
SELECT
    PROCESSLIST_ID AS connection_id,
    PROCESSLIST_USER AS user_name,
    PROCESSLIST_HOST AS client_host,
    PROCESSLIST_DB AS current_schema,
    PROCESSLIST_COMMAND AS command_name,
    PROCESSLIST_TIME AS command_seconds,
    PROCESSLIST_STATE AS process_state,
    PROCESSLIST_INFO AS current_sql
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
  AND PROCESSLIST_ID IS NOT NULL
ORDER BY PROCESSLIST_TIME DESC;
~~~

PROCESSLIST_INFO có thể chứa literal nhạy cảm, dữ liệu cá nhân hoặc token được ứng dụng đưa thẳng vào SQL. Khi ghi snapshot vào ticket hoặc log, hãy che thông tin nhạy cảm và chỉ lưu phần cần thiết. Tài khoản giám sát cần quyền phù hợp để xem connection của người dùng khác.

Một connection ở trạng thái Sleep không nhất thiết vô hại. Nó có thể giữ transaction mở và khóa InnoDB. Nếu thấy connection ngủ lâu, đối chiếu với information_schema.innodb_trx thay vì chỉ nhìn PROCESSLIST_COMMAND.

## 5. Theo dõi counter theo khoảng thời gian

Nhiều biến trong SHOW GLOBAL STATUS là counter tích lũy kể từ khi server khởi động hoặc lần reset tương ứng. Giá trị tuyệt đối không cho biết tốc độ hiện tại. Hãy lấy hai snapshot cách nhau một khoảng thời gian đã biết rồi tính delta.

Ví dụ lấy snapshot:

~~~sql
SELECT
    NOW(6) AS captured_at,
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Connections',
    'Questions',
    'Slow_queries',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_read_requests',
    'Innodb_row_lock_time',
    'Bytes_received',
    'Bytes_sent'
)
ORDER BY VARIABLE_NAME;
~~~

Giả sử hai snapshot cách nhau 60 giây. Với counter tăng đơn điệu, tốc độ trung bình trong khoảng là:

\[
\text{Rate} = \frac{\text{Counter}_{t2} - \text{Counter}_{t1}}{t2 - t1}
\]

Ví dụ Connections tăng 120 trong 60 giây thì tốc độ mở kết nối trung bình là 2 kết nối/giây. Nếu Uptime giảm hoặc server_uuid thay đổi giữa hai snapshot, có thể server đã restart hoặc endpoint đã trỏ sang node khác; không lấy delta qua hai node như thể đó là cùng một counter.

Một số tỷ lệ cần theo dõi:

- **Tốc độ kết nối mới**: delta Connections / số giây.
- **Tỷ lệ temporary table trên đĩa**: delta Created_tmp_disk_tables / delta Created_tmp_tables, nếu mẫu số lớn hơn 0.
- **Buffer pool read miss tương đối**: delta Innodb_buffer_pool_reads / delta Innodb_buffer_pool_read_requests, nếu mẫu số lớn hơn 0.
- **Tốc độ truy vấn**: delta Questions / số giây; lưu ý Questions không đại diện chính xác cho số request nghiệp vụ.
- **Tốc độ mạng**: delta Bytes_received và Bytes_sent / số giây.

Các tỷ lệ chỉ là chỉ báo. Temporary table trên đĩa có thể hợp lý với một số truy vấn; buffer pool miss tăng không đồng nghĩa chắc chắn phải tăng buffer pool. Hãy liên kết với latency, workload, RAM, I/O và kế hoạch truy vấn.

## 6. Kiểm tra transaction kéo dài và lock wait

Transaction mở lâu có thể giữ row lock, undo history và làm tăng áp lực purge. Bắt đầu bằng danh sách transaction InnoDB:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_wait_started,
    trx_mysql_thread_id AS connection_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Đối chiếu connection ID với process list để tìm user, host, command và SQL hiện tại. Nếu trx_query là NULL nhưng transaction vẫn tồn tại, session có thể đang chờ ứng dụng gửi câu lệnh tiếp theo hoặc đang Sleep giữa các câu lệnh của transaction.

Với MySQL 8.0, có thể xem lock wait bằng Performance Schema:

~~~sql
SELECT
    REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    REQUESTING_THREAD_ID AS waiting_thread,
    BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    BLOCKING_THREAD_ID AS blocking_thread,
    REQUESTING_ENGINE_LOCK_ID AS requested_lock_id,
    BLOCKING_ENGINE_LOCK_ID AS blocking_lock_id
FROM performance_schema.data_lock_waits;
~~~

Nếu sys schema được cài đặt và các view tương ứng khả dụng, sys.innodb_lock_waits có thể cung cấp góc nhìn dễ đọc hơn về waiter, blocker và thời gian chờ. Cấu trúc cột cụ thể tùy phiên bản; kiểm tra DESCRIBE hoặc tài liệu đúng bản cài trước khi đưa truy vấn vào runbook.

Không tự động KILL mọi transaction có tuổi lớn hơn một con số cố định. Xác định chủ sở hữu, thao tác nghiệp vụ, số dòng đã sửa, tác động rollback và mức độ ảnh hưởng trước khi dừng connection. Rollback một transaction lớn có thể kéo dài và tiếp tục tiêu thụ I/O.

## 7. Kiểm tra truy vấn và thống kê hiệu năng

Performance Schema lưu thống kê câu lệnh theo digest khi instrumentation và consumers phù hợp được bật. Có thể xem các truy vấn có tổng thời gian thực thi cao:

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR AS execution_count,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED AS rows_examined,
    SUM_ROWS_SENT AS rows_sent,
    SUM_NO_INDEX_USED AS executions_without_index,
    SUM_CREATED_TMP_DISK_TABLES AS disk_tmp_tables
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Các timer trong Performance Schema được lưu theo picosecond; phép chia 1.000.000.000.000 chuyển sang giây. Thống kê digest được tổng hợp cho nhiều lần thực thi, vì vậy tổng thời gian cao có thể đến từ truy vấn chạy thường xuyên chứ không chỉ truy vấn có latency mỗi lần cao.

Đọc đồng thời:

- COUNT_STAR để biết tần suất.
- AVG_TIMER_WAIT để xem thời gian trung bình.
- SUM_TIMER_WAIT để thấy tổng tác động.
- SUM_ROWS_EXAMINED so với SUM_ROWS_SENT để nhận diện truy vấn đọc nhiều nhưng trả ít dòng.
- SUM_NO_INDEX_USED và SUM_CREATED_TMP_DISK_TABLES như tín hiệu cần điều tra thêm.

Các cột và mức hỗ trợ có thể khác giữa phiên bản. Nếu truy vấn không có dữ liệu, kiểm tra Performance Schema có bật không, statement instrumentation/consumer có được bật không và tài khoản có quyền đọc không. Không bật instrumentation rộng trong production mà chưa đánh giá chi phí.

Để chẩn đoán một truy vấn cụ thể, lấy SQL đại diện và dùng EXPLAIN hoặc EXPLAIN ANALYZE trong điều kiện an toàn. Không chạy EXPLAIN ANALYZE một SELECT lớn trên production chỉ vì muốn có số liệu; lệnh này thực sự thực thi truy vấn.

## 8. Kiểm tra InnoDB, buffer pool và bảng

Lấy báo cáo InnoDB:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Trong mysql client có thể thêm \G để hiển thị theo chiều dọc:

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Các phần thường đáng xem gồm TRANSACTIONS, LATEST DETECTED DEADLOCK, FILE I/O, INSERT BUFFER AND ADAPTIVE HASH INDEX, BUFFER POOL AND MEMORY và ROW OPERATIONS. Đây là snapshot chẩn đoán, không phải log đầy đủ mọi sự kiện đã xảy ra. Phần LATEST DETECTED DEADLOCK chỉ giữ thông tin deadlock gần nhất được ghi nhận trong output đó.

Xem cấu hình buffer pool:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
~~~

Theo dõi các counter như Innodb_buffer_pool_reads và Innodb_buffer_pool_read_requests theo delta, không chỉ nhìn tỷ lệ tích lũy từ lúc khởi động. Cần xem thêm RAM thực tế, workload, kích thước working set và I/O latency trước khi quyết định tăng buffer pool.

Ước lượng dung lượng bảng và index từ Information Schema:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE,
    UPDATE_TIME
FROM information_schema.tables
WHERE TABLE_SCHEMA NOT IN (
    'mysql',
    'information_schema',
    'performance_schema',
    'sys'
)
ORDER BY DATA_LENGTH + INDEX_LENGTH DESC
LIMIT 30;
~~~

Với InnoDB, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH và DATA_FREE có thể là số liệu ước lượng. UPDATE_TIME không phải lúc nào cũng phản ánh chính xác thời điểm dữ liệu InnoDB được thay đổi. Dùng chúng để tìm bảng cần khảo sát, không thay thế công cụ đo dung lượng filesystem hoặc thống kê lưu trữ chuyên dụng.

MySQL SQL không cung cấp đầy đủ thông tin filesystem như dung lượng còn trống của volume chứa datadir, binary log, relay log, redo hoặc backup. Runbook cần có bước kiểm tra ở hệ điều hành hoặc nền tảng cloud cho disk free, inode, I/O latency, CPU, memory và network.

## 9. Kiểm tra error log và sự kiện máy chủ

Error log là nguồn quan trọng để tìm crash, restart, lỗi khởi tạo, lỗi InnoDB, lỗi replication, vấn đề TLS và cảnh báo cấu hình.

Xem cấu hình liên quan:

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'log_error',
    'log_error_verbosity',
    'log_timestamps',
    'log_error_services'
);
~~~

Không phải mọi phiên bản đều có cùng tập biến hoặc cùng cơ chế log service. Kiểm tra biến thực tế bằng SHOW VARIABLES và đọc error log tại vị trí hoặc sink mà cấu hình hiện tại sử dụng. Trên dịch vụ managed, log có thể được chuyển sang hệ thống log của nhà cung cấp thay vì file cục bộ.

Khi điều tra, ghi lại:

- Thời điểm bắt đầu và kết thúc sự cố, kèm múi giờ.
- Server UUID, hostname và phiên bản.
- Dòng lỗi đầu tiên liên quan và các lỗi xuất hiện ngay trước/sau.
- Sự kiện restart, failover, thay đổi cấu hình hoặc deploy gần thời điểm đó.
- Các cảnh báo lặp lại và tần suất xuất hiện.

Không chỉ tìm từ khóa ERROR. Một cảnh báo lặp lại về disk space, certificate sắp hết hạn, replication hoặc thread creation có thể là tín hiệu sớm trước khi dịch vụ thất bại.

Error log và process list có thể chứa tên user, hostname, đường dẫn nội bộ hoặc câu SQL. Chỉ chia sẻ phần cần thiết, che thông tin xác thực và tuân theo chính sách lưu trữ log.

## 10. Kiểm tra replication và trạng thái phục vụ

Nếu máy chủ là replica, kiểm tra trạng thái replication bằng cú pháp phù hợp phiên bản. Trên MySQL 8.0.22 trở lên, dùng:

~~~sql
SHOW REPLICA STATUS\G
~~~

Các bản MySQL cũ hơn có thể dùng tên lệnh SHOW SLAVE STATUS. Không trộn tên biến trạng thái cũ/mới trong một runbook mà không ghi rõ phiên bản hỗ trợ.

Một số trường cần xem trong output gồm:

- Replica_IO_Running và Replica_SQL_Running: trạng thái các luồng nhận và áp dụng relay log.
- Seconds_Behind_Source: ước lượng độ trễ trong một số điều kiện; NULL hoặc 0 không chứng minh replica luôn đồng bộ hoàn toàn.
- Last_IO_Error và Last_SQL_Error: lỗi gần nhất ở luồng I/O hoặc SQL.
- Retrieved_Gtid_Set và Executed_Gtid_Set: phạm vi GTID đã nhận và đã thực thi khi GTID được bật.
- Source_Host, Source_Port và Channel_Name: nguồn replication và channel đang kiểm tra.

Không dùng riêng Seconds_Behind_Source làm tiêu chí duy nhất để quyết định failover. Hãy xem trạng thái luồng, GTID, lỗi, khả năng đọc dữ liệu mới nhất và quy trình failover của topology.

Với Group Replication hoặc InnoDB Cluster, dùng các view/trạng thái tương ứng của group và MySQL Shell theo phiên bản triển khai. Runbook cần chỉ rõ loại topology; không áp dụng câu lệnh replica đơn giản cho một cụm có cơ chế điều phối khác.

Trước thao tác ghi, xác minh node là primary theo cơ chế quản lý topology và read_only/super_read_only ở trạng thái mong đợi. Trước thao tác đọc có yêu cầu dữ liệu mới nhất, xác định mức replication lag mà nghiệp vụ cho phép.

## 11. Kiểm tra backup và khả năng phục hồi

Một backup thành công về mặt kỹ thuật chưa chứng minh hệ thống có thể phục hồi đúng thời điểm cần thiết. Health check phải xác nhận cả quy trình tạo backup lẫn khả năng restore.

Các câu hỏi cần trả lời:

- Bản backup gần nhất hoàn thành lúc nào và thuộc server/schema nào?
- Backup có mã định danh, checksum hoặc manifest để xác minh tính toàn vẹn không?
- Backup có bao gồm dữ liệu cần thiết, metadata, user/grant và cấu hình cần phục hồi không?
- Nếu cần point-in-time recovery, binary log có liên tục và được lưu đủ lâu không?
- Bản backup có được mã hóa và quyền truy cập có được giới hạn không?
- Lần restore test gần nhất là khi nào, mất bao lâu và có đạt RTO/RPO không?

Định kỳ restore vào môi trường cô lập, xác minh schema, số lượng dữ liệu quan trọng, quyền truy cập và ứng dụng có thể kết nối. Không thử restore đè lên production để kiểm tra backup.

Runbook backup cần phân biệt snapshot vật lý, logical dump, backup managed service và backup kết hợp binary log. Mỗi phương pháp có yêu cầu nhất quán, thời gian khóa, dung lượng, phiên bản tương thích và bước phục hồi khác nhau.

Không coi việc bật binary log là backup hoàn chỉnh. Binary log hỗ trợ replication và point-in-time recovery, nhưng vẫn cần base backup hợp lệ, retention phù hợp, lưu trữ an toàn và diễn tập khôi phục.

## 12. Xây dựng baseline và ngưỡng cảnh báo

Baseline là mô tả hành vi bình thường của hệ thống trong các chu kỳ workload đại diện. Hãy thu thập dữ liệu ở giờ cao điểm, giờ thấp điểm, ngày thường, ngày cuối tuần và các đợt batch nếu chúng có ảnh hưởng.

Một baseline thực dụng nên gồm:

| Nhóm | Số liệu nên lưu |
|---|---|
| Kết nối | Threads_connected, Threads_running, Max_used_connections, tốc độ Connections |
| Truy vấn | p50/p95/p99 latency từ ứng dụng, digest count, rows examined |
| InnoDB | buffer pool reads, row lock time, deadlocks, transaction age |
| Storage | data/index size, disk free, I/O latency, binary log growth |
| Replication | trạng thái luồng, GTID gap, lag và thời gian áp dụng |
| Backup | thời điểm backup, thời lượng, kích thước, kết quả restore test |
| Hạ tầng | CPU, RAM, swap, network, filesystem và inode |

Chọn ngưỡng dựa trên tác động:

- Ngưỡng cảnh báo sớm khi tốc độ tăng cho thấy sẽ chạm giới hạn trong thời gian ngắn.
- Ngưỡng nghiêm trọng khi SLO bị vi phạm, connection gần cạn hoặc replica vượt mức lag nghiệp vụ cho phép.
- Ngưỡng dung lượng dựa trên tốc độ tăng và thời gian cần để mở rộng volume, không chỉ phần trăm còn trống hiện tại.
- Ngưỡng transaction/lock wait dựa trên loại workload và thời gian nghiệp vụ có thể chờ.

Với counter tích lũy, alert nên dựa trên rate hoặc delta. Với gauge như Threads_connected, đo giá trị hiện tại và xu hướng. Với latency, dùng percentile thay vì chỉ average vì một nhóm truy vấn rất chậm có thể bị trung bình che khuất.

Mỗi cảnh báo phải có owner, mức độ, liên kết runbook, điều kiện đóng cảnh báo và cách tránh báo động lặp. Alert không có hành động tiếp theo chỉ tạo nhiễu.

## 13. Cấu trúc một runbook có thể thực hiện lại

Mỗi runbook nên có cùng một cấu trúc để người trực ca không phải đoán bước tiếp theo:

1. **Tên và mã runbook**: định danh ổn định để liên kết từ alert và ticket.
2. **Mục đích**: sự cố hoặc thay đổi mà runbook xử lý.
3. **Phạm vi**: môi trường, cluster, phiên bản MySQL, topology và dịch vụ liên quan.
4. **Điều kiện kích hoạt**: alert, triệu chứng, ngưỡng hoặc yêu cầu thay đổi.
5. **Mức độ ảnh hưởng**: cách xác định severity, user impact và data risk.
6. **Vai trò và quyền cần có**: người thực hiện, người phê duyệt, tài khoản giám sát hoặc quản trị.
7. **Điều kiện trước khi chạy**: xác nhận node, backup, thời gian, quyền và cửa sổ thay đổi.
8. **Các bước thực hiện**: câu lệnh chính xác, thứ tự, tham số và cách lưu output.
9. **Kết quả mong đợi**: điều kiện pass/fail sau mỗi bước.
10. **Nhánh quyết định**: nếu kết quả A thì làm gì; nếu B thì dừng hoặc chuyển cấp.
11. **Xác minh sau xử lý**: kiểm tra dịch vụ, dữ liệu, replication và metric.
12. **Rollback hoặc phục hồi**: điều kiện, lệnh và giới hạn của rollback.
13. **Escalation**: người/nhóm cần liên hệ, dữ liệu cần bàn giao và thời hạn.
14. **Bằng chứng và lịch sử**: timestamp, server UUID, lệnh đã chạy, kết quả, thay đổi và người thực hiện.
15. **Chủ sở hữu và ngày rà soát**: người duy trì, phiên bản, ngày kiểm thử gần nhất.

Một runbook chỉ có câu lệnh mà không có kết quả mong đợi sẽ buộc người thực hiện tự diễn giải. Một runbook không có điều kiện dừng có thể khiến người mới tiếp tục thao tác khi đã đi vào trạng thái nguy hiểm.

## 14. Ví dụ runbook: connection tăng cao

**Mục tiêu:** xác định nguyên nhân connection tăng, bảo vệ khả năng phục vụ và giảm áp lực một cách có kiểm soát.

**Điều kiện kích hoạt:** Threads_connected tăng gần max_connections, ứng dụng báo lỗi too many connections hoặc độ trễ tăng đồng thời với connection churn.

**Bước 1 — Xác minh node và ghi thời điểm**

~~~sql
SELECT
    NOW(6) AS checked_at,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    @@global.read_only AS read_only,
    @@global.super_read_only AS super_read_only;

SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects'
);

SHOW GLOBAL VARIABLES LIKE 'max_connections';
~~~

Ghi lại output và so sánh với snapshot trước. Nếu endpoint đã chuyển node hoặc Uptime vừa reset, xác minh topology trước khi so sánh counter.

**Bước 2 — Tìm nhóm connection chiếm nhiều**

~~~sql
SELECT
    PROCESSLIST_USER AS user_name,
    PROCESSLIST_HOST AS client_host,
    PROCESSLIST_DB AS current_schema,
    PROCESSLIST_COMMAND AS command_name,
    COUNT(*) AS connection_count
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
  AND PROCESSLIST_ID IS NOT NULL
GROUP BY
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND
ORDER BY connection_count DESC;
~~~

Nếu một user/host chiếm phần lớn connection, đối chiếu với connection pool, số instance ứng dụng, giới hạn pool và retry policy. Kiểm tra xem nhiều connection có đang Sleep nhưng vẫn giữ transaction mở không.

**Bước 3 — Kiểm tra transaction mở**

~~~sql
SELECT
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Nếu có transaction mở lâu, xác định chủ sở hữu và tác động trước khi yêu cầu ứng dụng commit/rollback hoặc dừng connection. Không KILL hàng loạt chỉ để làm giảm Threads_connected.

**Bước 4 — Chọn hành động**

- Nếu ứng dụng tạo connection quá nhanh: kiểm tra pool max size, connection leak, retry storm và timeout; điều chỉnh ở ứng dụng theo quy trình triển khai.
- Nếu connection Sleep tích tụ: xác định pool/worker sở hữu và transaction mở; yêu cầu đóng transaction đúng logic.
- Nếu có truy vấn đang chạy lâu: kiểm tra plan, lock wait, I/O và tải; xử lý nguyên nhân truy vấn.
- Nếu thực sự cần tăng max_connections: xác minh RAM cho mỗi connection, workload, giới hạn OS và proxy; thay đổi theo quy trình cấu hình đã phê duyệt.
- Nếu node đã mất khả năng phục vụ: chuyển cấp theo runbook failover/incident, không tự thay đổi vai trò node trong runbook connection.

**Bước 5 — Xác minh**

Lặp lại snapshot sau hành động. Xác nhận Threads_connected giảm hoặc ổn định, lỗi kết nối ngừng tăng, p95/p99 latency phục hồi và ứng dụng xử lý được request. Ghi lại thời gian phục hồi và nguyên nhân gốc nếu đã xác định.

## 15. Thay đổi cấu hình an toàn và có thể kiểm chứng

Trước khi thay đổi biến, xác định giá trị hiện tại, phạm vi GLOBAL/SESSION, khả năng dynamic, nguồn cấu hình và phiên bản hỗ trợ.

Xem giá trị:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'max_connections';
SHOW GLOBAL VARIABLES LIKE 'innodb_buffer_pool_size';
~~~

Với MySQL 8.0, có thể xem nguồn thiết lập trong Performance Schema:

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
    'innodb_buffer_pool_size'
);
~~~

Các cột trong variables_info giúp xác định nguồn cấu hình và thời điểm một biến được đặt. Nếu bảng không có dữ liệu hoặc phiên bản khác, dùng SHOW VARIABLES và kiểm tra file cấu hình theo quy trình quản trị máy chủ.

Các cách thay đổi khác nhau:

~~~sql
-- Chỉ thay đổi runtime, không ghi cấu hình tồn tại sau restart.
SET GLOBAL max_connections = 500;
~~~

~~~sql
-- Thay đổi runtime và lưu cấu hình cho lần khởi động sau.
SET PERSIST max_connections = 500;
~~~

~~~sql
-- Lưu giá trị cho lần khởi động sau, không áp dụng runtime ngay.
SET PERSIST_ONLY max_connections = 500;
~~~

~~~sql
-- Xóa override đã lưu cho biến này.
RESET PERSIST IF EXISTS max_connections;
~~~

Chỉ dùng cú pháp phù hợp phiên bản và quyền được cấp. SET PERSIST và SET PERSIST_ONLY cần quyền quản trị biến hệ thống phù hợp. Một số biến chỉ có hiệu lực lúc khởi động; một số biến có thể thay đổi runtime. Không giả định mọi biến đều dynamic.

SET GLOBAL không tự ghi giá trị vào file cấu hình thông thường; thay đổi có thể mất sau restart. SET PERSIST ghi override vào kho cấu hình persisted của MySQL, thường được lưu trong mysqld-auto.cnf. Không sửa trực tiếp file mysqld-auto.cnf bằng trình soạn thảo. RESET PERSIST xóa giá trị persisted; việc xóa override không nhất thiết đưa giá trị runtime hiện tại về giá trị mặc định ngay lập tức.

Trước khi áp dụng:

1. Ghi lại giá trị hiện tại và nguồn cấu hình.
2. Xác định lý do thay đổi và tác động tới RAM, CPU, connection, I/O hoặc replication.
3. Kiểm tra dynamic/startup-only và phiên bản.
4. Thử trên staging hoặc replica phù hợp.
5. Chuẩn bị cách rollback và người phê duyệt.
6. Thay đổi một biến hoặc một nhóm có quan hệ rõ ràng tại một thời điểm.
7. Xác minh runtime, persisted value và metric sau thay đổi.
8. Ghi lại kết quả vào change record.

Không tăng max_connections để xử lý connection leak mà chưa tìm nguyên nhân. Mỗi connection có thể sử dụng bộ nhớ cho thread, buffer và trạng thái session; nâng giới hạn có thể làm máy chủ cạn RAM nhanh hơn khi tải tăng.

## 16. Phân biệt kiểm tra định kỳ và xử lý sự cố

Health check định kỳ nên ngắn, có thể tự động hóa và ưu tiên lệnh đọc ít tác động. Runbook sự cố có thể sâu hơn và chỉ chạy khi có trigger cụ thể.

| Hoạt động | Tần suất gợi ý | Ví dụ |
|---|---|---|
| Liveness/readiness | Liên tục hoặc mỗi phút | mysqladmin ping, SELECT 1, role check |
| Connection và resource | Mỗi 1–5 phút | Threads_connected, Threads_running, disk free |
| Query/lock/transaction | Liên tục hoặc mỗi vài phút | digest, lock waits, transaction age |
| Replication | Liên tục hoặc theo topology | thread status, GTID, lag |
| Backup job | Sau mỗi lần chạy | exit status, checksum, manifest |
| Restore test | Theo lịch phục hồi | restore vào môi trường cô lập |
| Configuration drift | Khi deploy và định kỳ | variables, source, persisted settings |
| Runbook exercise | Theo lịch hoặc sau thay đổi lớn | diễn tập incident, failover, restore |

Các khoảng thời gian chỉ là điểm bắt đầu. Hãy điều chỉnh theo tải, chi phí thu thập metric, khả năng phát hiện và thời gian phản ứng cần thiết.

Health check tự động không nên tự ý KILL connection, restart MySQL, đổi read_only, promote replica hoặc sửa cấu hình. Những hành động đó cần runbook có điều kiện rõ, kiểm tra vai trò và cơ chế phê duyệt tương ứng.

## 17. Ghi bằng chứng và bảo trì runbook

Mỗi lần thực hiện runbook nên lưu:

- Mã runbook và phiên bản.
- Người thực hiện, người phê duyệt và ticket/incident liên quan.
- Thời điểm bắt đầu/kết thúc theo UTC hoặc múi giờ đã quy định.
- Hostname, server_uuid, server_id, phiên bản và vai trò node.
- Lệnh đã chạy cùng output đã che dữ liệu nhạy cảm.
- Giá trị trước/sau khi thay đổi.
- Điều kiện pass/fail và các nhánh đã chọn.
- Hành động rollback, escalation hoặc follow-up.
- Kết quả cuối cùng và thời gian phục hồi dịch vụ.

Runbook cần được kiểm tra sau các thay đổi MySQL version, topology, proxy, monitoring, schema, quy trình backup và quyền quản trị. Một lệnh đúng ở MySQL 8.0 có thể đã đổi tên hoặc thay đổi hành vi ở phiên bản khác; ghi rõ phiên bản được kiểm thử.

Nên diễn tập runbook trong môi trường không production trước khi dùng cho sự cố thật. Đo thời gian từng bước, xác nhận quyền cần thiết, kiểm tra output, phát hiện lệnh không còn hợp lệ và cập nhật nhánh quyết định. Sau incident, bổ sung điều kiện đã bị bỏ sót và ghi rõ lệnh nào không nên chạy trong hoàn cảnh cụ thể.

## 18. Những lỗi vận hành thường gặp

**Chỉ kiểm tra mysqladmin ping.** Ping chứng minh tiến trình phản hồi, không chứng minh truy vấn nghiệp vụ, quyền, replication hay connection pool đều khỏe.

**Dùng một giá trị counter tích lũy làm cảnh báo.** Connections hoặc Slow_queries tăng theo thời gian là bình thường. Dùng delta/rate và đối chiếu uptime.

**Dùng Threads_connected thay cho Threads_running.** Một lượng lớn connection Sleep có thể là pool bình thường hoặc connection leak; một lượng nhỏ Threads_running nhưng truy vấn chậm do I/O cũng có thể ảnh hưởng nghiêm trọng.

**Giết mọi connection Sleep lâu.** Session Sleep có thể giữ transaction và khóa. Xác định transaction, chủ sở hữu và tác động rollback trước khi dừng.

**Coi Seconds_Behind_Source = 0 là bằng chứng replica đồng bộ tuyệt đối.** Cần xem trạng thái I/O/SQL, GTID, lỗi và topology. Giá trị này không thay thế quy trình failover.

**Chỉ xác minh backup bằng exit code.** Cần checksum/manifest và restore test. Backup chưa từng phục hồi là một giả định chưa được kiểm chứng.

**Thay đổi cấu hình nhưng không ghi lại nguồn.** Sau restart, giá trị có thể quay về file cấu hình hoặc override khác. Kiểm tra variables_info, persisted setting và cấu hình khởi động.

**Đặt ngưỡng cảnh báo giống nhau cho mọi môi trường.** Baseline và SLO của mỗi workload khác nhau. Ngưỡng cần dựa trên dữ liệu và tốc độ tiến tới giới hạn.

**Runbook không có điều kiện dừng.** Người trực có thể tiếp tục thao tác khi node sai vai trò, backup chưa có hoặc tác động đã vượt phạm vi. Mỗi runbook phải nêu rõ khi nào dừng và chuyển cấp.

**Lưu nguyên output chứa dữ liệu nhạy cảm.** SQL text, host, username và literal có thể tiết lộ thông tin. Che dữ liệu trước khi đưa vào ticket hoặc kho log có phạm vi truy cập rộng.

## 19. Bài thực hành: tạo health snapshot và runbook

Dùng một MySQL instance thử nghiệm hoặc môi trường được phép quan sát. Không chạy thay đổi cấu hình trên production chỉ để hoàn thành bài học.

**Phần A — Thu thập health snapshot**

Chạy và lưu kết quả các nhóm sau:

~~~sql
SELECT
    NOW(6) AS captured_at,
    VERSION() AS mysql_version,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    @@global.read_only AS read_only,
    @@global.super_read_only AS super_read_only;

SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Connections',
    'Aborted_connects',
    'Slow_queries'
);

SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
    'max_connections',
    'innodb_buffer_pool_size',
    'performance_schema',
    'log_error'
);
~~~

Ghi lại thời điểm, server UUID, phiên bản và vai trò. Chạy snapshot lần hai sau một khoảng thời gian đã biết; tính delta cho counter và giải thích biến nào là gauge, biến nào là counter.

**Phần B — Kiểm tra transaction và truy vấn**

~~~sql
SELECT
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_state,
    trx_rows_locked,
    trx_rows_modified
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Nếu Performance Schema statement summary khả dụng, lấy top digest theo tổng thời gian và so sánh với số lần thực thi. Xác định truy vấn nào có tổng tác động cao và truy vấn nào có thời gian trung bình cao.

**Phần C — Viết runbook một trang**

Chọn một triệu chứng như connection tăng, transaction mở lâu, replica lag hoặc disk sắp đầy. Viết các mục: trigger, phạm vi, điều kiện trước khi chạy, lệnh đọc, output mong đợi, nhánh quyết định, hành động được phép, điều kiện dừng, xác minh, rollback/escalation và bằng chứng cần lưu.

**Phần D — Diễn tập**

Một người đóng vai người trực ca, một người đọc runbook và kiểm tra từng bước. Không cung cấp lời giải miệng ngoài tài liệu. Ghi lại chỗ thiếu quyền, thiếu lệnh, kết quả không rõ hoặc nhánh quyết định không đủ. Sửa runbook và diễn tập lại đến khi người khác có thể thực hiện an toàn.

## 20. Checklist trước khi kết luận MySQL khỏe mạnh

- Đã xác nhận đúng server UUID, phiên bản và vai trò node chưa?
- Liveness và readiness có được kiểm tra riêng không?
- read_only/super_read_only có đúng với vai trò dự kiến không?
- Connection count, running threads và tốc độ mở kết nối có ổn định không?
- Có transaction kéo dài, lock wait hoặc deadlock bất thường không?
- Query latency, rows examined và digest workload có thay đổi không?
- Buffer pool, InnoDB và table statistics có tín hiệu cần điều tra không?
- CPU, RAM, disk free, inode, I/O latency và network đã được kiểm tra ở tầng hạ tầng chưa?
- Error log có crash, restart, lỗi TLS, InnoDB hoặc replication không?
- Replica có đúng trạng thái, GTID và lag trong giới hạn nghiệp vụ không?
- Backup mới nhất có hợp lệ và restore test gần đây có thành công không?
- Cấu hình runtime và persisted có khớp với change record không?
- Cảnh báo có owner, ngưỡng dựa trên baseline và runbook liên kết không?
- Runbook có điều kiện dừng, xác minh sau xử lý, rollback và escalation không?
- Bằng chứng có timestamp, server identity và đã che dữ liệu nhạy cảm không?

Một health check đáng tin cậy phải chỉ ra hệ thống đang ở trạng thái nào, tín hiệu nào dẫn đến kết luận đó và ai cần hành động tiếp theo. Một runbook tốt phải giúp người khác lặp lại quy trình trong điều kiện áp lực mà vẫn biết giới hạn an toàn. Khi kết hợp baseline, metric theo thời gian, kiểm tra backup/replication và runbook được diễn tập, hoạt động MySQL trở nên có thể quan sát, giải thích và cải thiện liên tục.
