# Phân tích nguyên nhân gốc và cập nhật biện pháp phòng ngừa

Khi một sự cố PostgreSQL được xử lý xong, việc khôi phục dịch vụ mới chỉ giải quyết phần trước mắt. Nếu nhóm vận hành chỉ restart service, tăng giới hạn kết nối hoặc chạy lại một truy vấn mà không hiểu điều gì đã gây ra lỗi, cùng một kiểu sự cố có thể xuất hiện trở lại dưới tải lớn hơn hoặc ở một thời điểm khó kiểm soát hơn.

**Phân tích nguyên nhân gốc (Root Cause Analysis - RCA)** là quá trình dựng lại diễn biến sự cố bằng bằng chứng, xác định các điều kiện trực tiếp và điều kiện hệ thống khiến sự cố xảy ra, rồi chuyển kết luận thành hành động khắc phục và phòng ngừa. Mục tiêu là giảm khả năng tái diễn và giảm phạm vi ảnh hưởng nếu sự cố tương tự vẫn xảy ra.

Trong hệ thống dùng PostgreSQL, RCA cần kết hợp dữ liệu từ database, ứng dụng, connection pool, hệ điều hành, mạng, hạ tầng và quy trình triển khai. Một lỗi timeout ở ứng dụng có thể bắt nguồn từ truy vấn chậm, lock kéo dài, thiếu connection, I/O bão hòa, replication lag hoặc thay đổi cấu hình. Bản thân thông báo lỗi thường chỉ mô tả nơi vấn đề được phát hiện, không nhất thiết chỉ ra nguyên nhân đầu tiên.

## 1. RCA bắt đầu từ mục tiêu và phạm vi sự cố

Trước khi tìm nguyên nhân, cần xác định sự cố nào đang được phân tích và tác động của nó. Một incident có thể bao gồm nhiều triệu chứng liên quan, nhưng không nên gộp các sự kiện không có quan hệ nhân quả chỉ vì chúng xảy ra gần nhau.

Thông tin ban đầu nên có:

- **Thời gian:** thời điểm bắt đầu, thời điểm phát hiện, thời điểm ảnh hưởng đạt đỉnh và thời điểm dịch vụ phục hồi.
- **Phạm vi:** database, cluster, service, endpoint, tenant hoặc khu vực bị ảnh hưởng.
- **Tác động:** request lỗi, thời gian phản hồi, dữ liệu không nhất quán, công việc bị trì hoãn hoặc giao dịch bị thất bại.
- **Mức độ:** mức độ ảnh hưởng theo tiêu chí nội bộ như số người dùng, tỷ lệ lỗi, thời lượng và mức độ nghiêm trọng của dữ liệu.
- **Phát hiện:** cảnh báo, ticket, log hoặc phản ánh đầu tiên.
- **Biện pháp khôi phục:** thao tác đã thực hiện và thời điểm thực hiện.

Nên phân biệt ba mốc thời gian:

1. **Thời điểm sự cố bắt đầu:** khi hệ thống bắt đầu lệch khỏi trạng thái bình thường.
2. **Thời điểm phát hiện:** khi người hoặc hệ thống giám sát nhận ra vấn đề.
3. **Thời điểm khôi phục:** khi dịch vụ trở lại mức chấp nhận được.

Khoảng cách giữa thời điểm bắt đầu và phát hiện cho biết khả năng quan sát có thể cần cải thiện. Khoảng cách giữa phát hiện và khôi phục phản ánh năng lực chẩn đoán, quy trình ứng phó và hiệu quả của biện pháp giảm thiểu.

Không nên mặc định thời điểm cảnh báo đầu tiên chính là thời điểm nguyên nhân xuất hiện. Ví dụ, một transaction có thể giữ lock từ 10:00, nhưng chỉ đến 10:15 khi lưu lượng tăng thì hàng đợi mới vượt ngưỡng cảnh báo.

## 2. Thu thập bằng chứng trước khi kết luận

RCA đáng tin cậy dựa trên bằng chứng có thể đối chiếu. Hãy lưu lại dữ liệu gần thời điểm sự cố trước khi restart, xóa log, reset thống kê hoặc thay đổi cấu hình làm mất dấu vết.

### 2.1. Nguồn dữ liệu cần thu thập

| Nguồn | Dữ liệu hữu ích | Câu hỏi cần trả lời |
|---|---|---|
| PostgreSQL logs | Lỗi, duration, SQLSTATE, PID, user, database, application_name | Server ghi nhận điều gì và theo thứ tự nào? |
| pg_stat_activity | Backend, trạng thái, query, transaction age, wait event | Kết nối đang làm gì hoặc đang chờ gì? |
| pg_stat_statements | Số lần gọi, thời gian tổng, thời gian trung bình, hàng trả về | Query nào tiêu tốn tài nguyên bất thường? |
| Lock diagnostics | Blocker, blocked PID, loại lock, thời gian chờ | Transaction nào tạo điểm nghẽn? |
| Application logs | Request ID, trace ID, exception, endpoint, retry | Người dùng và service nhìn thấy lỗi gì? |
| Pool metrics | Active, idle, pending, acquisition time, timeout | Kết nối bị giữ ở ứng dụng hay server đã hết slot? |
| OS / infrastructure | CPU, RAM, disk latency, IOPS, network, filesystem | Tài nguyên nào đã bão hòa? |
| Replication metrics | Replay lag, slot retention, WAL volume | Replica có tụt lại hoặc giữ WAL không? |
| Deployment records | Commit, migration, config change, scale event | Có thay đổi nào trùng với thời điểm sự cố? |

Lưu cả đơn vị đo, khoảng thời gian, múi giờ và nguồn phát sinh. Một biểu đồ ghi thời gian UTC và log ứng dụng ghi giờ địa phương có thể khiến nhóm dựng sai thứ tự nếu không chuẩn hóa.

### 2.2. Bảo toàn log và thống kê

Không nên reset pg_stat_statements hoặc xóa log ngay khi bắt đầu điều tra. Nếu cần reset để đo một khoảng mới, hãy lưu snapshot trước, ghi rõ thời điểm reset và lý do.

Với log, giữ các trường như timestamp, process ID, session ID, transaction ID, user, database, application_name và SQLSTATE nếu cấu hình PostgreSQL có ghi. Nếu bật log_duration hoặc log_min_duration_statement, cần kiểm soát nội dung nhạy cảm vì câu SQL hoặc parameter có thể chứa dữ liệu riêng tư.

Không nhất thiết thu thập toàn bộ dữ liệu thô vào báo cáo hậu sự cố. Lưu bản gốc ở nơi có kiểm soát truy cập, còn báo cáo chỉ trích dẫn những dòng hoặc khoảng thời gian cần thiết.

### 2.3. Gắn kết sự kiện giữa các tầng

Dùng một định danh request hoặc trace xuyên suốt gateway, ứng dụng và các dịch vụ liên quan. Ở PostgreSQL, đặt application_name khác nhau theo service hoặc worker để phân biệt kết nối trong pg_stat_activity và log.

Nếu có thể, ghi nhận PID backend cùng request ID ở lớp ứng dụng khi connection được mượn. Không phải mọi driver hoặc pool đều cung cấp cách gắn request ID trực tiếp vào server session; có thể truyền application_name ở cấp kết nối và giữ trace ID trong log ứng dụng.

Cần cẩn thận khi sử dụng SET session-level trên connection pool. Connection có thể được tái sử dụng cho request khác. Nếu đặt trạng thái session theo request, phải reset đúng cách hoặc dùng thiết lập theo transaction phù hợp.

## 3. Dựng timeline và xác định điểm thay đổi

Timeline là danh sách sự kiện theo thời gian, kết hợp dữ liệu từ các nguồn khác nhau. Nó giúp phân biệt nguyên nhân, điều kiện kích hoạt và triệu chứng xuất hiện sau đó.

Ví dụ một sự cố pool cạn:

| Thời gian | Sự kiện quan sát được |
|---|---|
| 09:58 | Triển khai phiên bản API mới |
| 10:02 | P95 của một truy vấn tăng từ 80 ms lên 2,4 s |
| 10:04 | Active connections tăng đến giới hạn pool |
| 10:05 | Pending acquisition tăng |
| 10:07 | Request timeout và retry bắt đầu tăng |
| 10:10 | PostgreSQL CPU cao, nhiều backend chờ lock |
| 10:14 | Tạm dừng worker batch và giảm retry |
| 10:18 | Query latency và pending connection giảm |
| 10:25 | Lưu lượng được khôi phục dần |

Timeline này chưa chứng minh deployment là nguyên nhân gốc. Nó chỉ cho thấy thay đổi được triển khai trước khi query latency tăng. Cần xem kế hoạch truy vấn, dữ liệu, migration, cấu hình và log để xác định mối liên hệ.

### 3.1. Tìm điểm bắt đầu của bất thường

So sánh các chỉ số với baseline trước sự cố:

- Query count và query latency theo fingerprint.
- Số active backend, trạng thái và wait event.
- Số lock wait và thời gian transaction.
- CPU, disk read/write latency và I/O queue.
- WAL generation, checkpoint và replication lag.
- Số kết nối pool, số request chờ và tỷ lệ retry.
- Lưu lượng, số replica, lịch batch và thay đổi cấu hình.

Một metric tăng sau khi lỗi đã xuất hiện có thể là hệ quả. Ví dụ, CPU tăng vì retry storm có thể xảy ra sau khi truy vấn ban đầu bị chặn bởi lock. Nếu coi CPU là nguyên nhân duy nhất, biện pháp tăng CPU sẽ không xử lý blocker.

### 3.2. Phân biệt tương quan và quan hệ nhân quả

Hai sự kiện xảy ra cùng lúc không có nghĩa sự kiện này gây ra sự kiện kia. Hãy đặt câu hỏi:

- Sự kiện nào xuất hiện trước?
- Khi nguyên nhân giả định xảy ra, cơ chế nào có thể tạo ra triệu chứng?
- Có log hoặc metric nào chứng minh cơ chế đó?
- Nếu bỏ điều kiện này, sự cố có khả năng vẫn xảy ra không?
- Có một nguyên nhân khác giải thích dữ liệu tốt hơn không?

Ví dụ, một lần tăng số replica trùng với pool exhaustion. Phân tích cấu hình có thể cho thấy tổng maximum pool đã vượt ngân sách PostgreSQL. Đây là cơ chế có thể giải thích sự cố. Tuy nhiên, nếu tất cả connection chỉ tăng sau khi một transaction bị treo, việc scale out có thể là yếu tố khuếch đại chứ không phải nguyên nhân khởi đầu.

## 4. Phương pháp phân tích nguyên nhân

Không có một kỹ thuật duy nhất phù hợp cho mọi incident. Có thể kết hợp 5 Whys, sơ đồ nguyên nhân - kết quả, phân tích chuỗi sự kiện và kiểm chứng giả thuyết.

### 4.1. Phương pháp 5 Whys

5 Whys đặt câu hỏi “Vì sao?” liên tiếp để đi từ triệu chứng đến điều kiện hệ thống có thể thay đổi. Số lần hỏi không bắt buộc là năm; dừng khi đã có nguyên nhân có bằng chứng và có thể chuyển thành hành động.

Ví dụ:

1. **Vì sao API trả về timeout?** Vì request không lấy được connection từ pool trước deadline.
2. **Vì sao pool không có connection rảnh?** Vì phần lớn connection đang nằm trong transaction chờ lock.
3. **Vì sao transaction chờ lock kéo dài?** Vì một luồng cập nhật đơn hàng giữ transaction trong lúc gọi dịch vụ bên ngoài.
4. **Vì sao transaction bao trùm lời gọi bên ngoài?** Vì ranh giới transaction được đặt ở tầng xử lý request thay vì quanh thao tác database.
5. **Vì sao thiết kế này được đưa vào production?** Vì kiểm thử tích hợp không mô phỏng độ trễ dịch vụ bên ngoài và chưa có cảnh báo transaction age.

Hành động tương ứng có thể gồm thu hẹp transaction scope, thêm kiểm thử mô phỏng dịch vụ chậm, giám sát transaction age và bổ sung hướng dẫn review về việc không giữ transaction khi chờ I/O bên ngoài.

Không nên dùng 5 Whys để tìm một cá nhân để quy trách nhiệm. Câu trả lời như “vì lập trình viên bất cẩn” không giải thích cơ chế kỹ thuật hoặc điều kiện tổ chức khiến lỗi lọt qua kiểm soát.

### 4.2. Sơ đồ nguyên nhân - kết quả

Có thể nhóm giả thuyết theo các nhánh:

- **Ứng dụng:** connection leak, transaction scope rộng, retry không giới hạn, pool sizing sai.
- **SQL và schema:** query plan thay đổi, thiếu index, thống kê cũ, migration tạo lock.
- **PostgreSQL:** max_connections, autovacuum, checkpoint, WAL, lock contention.
- **Hạ tầng:** CPU, RAM, disk latency, network, DNS, storage quota.
- **Dữ liệu và tải:** tăng kích thước bảng, skew, burst traffic, batch chạy trùng.
- **Quy trình:** deploy thiếu canary, không có rollback, cảnh báo không đủ, runbook lỗi thời.

Sơ đồ giúp nhóm không bỏ qua một nhóm nguyên nhân, nhưng mỗi nhánh vẫn cần bằng chứng. Không ghi tất cả khả năng vào báo cáo như thể chúng đều đã xảy ra.

### 4.3. Kiểm chứng giả thuyết

Mỗi giả thuyết nên có một phép kiểm chứng và kết quả mong đợi.

| Giả thuyết | Bằng chứng cần tìm | Điều gì sẽ làm giả thuyết yếu đi? |
|---|---|---|
| Query chậm gây cạn pool | Query latency tăng trước pool wait; pg_stat_statements chỉ ra query | Pool đã đầy trước khi query latency tăng |
| Lock gây nghẽn | pg_blocking_pids, wait_event_type = Lock, transaction age cao | Không có blocker và backend không chờ lock |
| Connection leak | Active connection tăng dần, không giảm sau khi tải hạ; leak stack trace | Connection đều được trả và pool phục hồi đúng theo tải |
| Pool tổng vượt ngân sách | Số replica × pool max vượt giới hạn kết nối | Tổng kết nối thực tế vẫn dưới ngân sách |
| Disk bão hòa | I/O latency và queue tăng trước query latency | Storage vẫn ổn định trong toàn bộ thời gian |
| Replication slot giữ WAL | Slot inactive hoặc restart_lsn cũ, pg_wal tăng | Slot không giữ WAL và dung lượng WAL ổn định |

Có thể dùng phép thử có kiểm soát trên môi trường staging để tái hiện cơ chế. Không cần tái tạo toàn bộ production incident nếu một test nhỏ đã chứng minh được nguyên nhân.

## 5. Các nhóm nguyên nhân thường gặp trong PostgreSQL

### 5.1. Query plan thay đổi hoặc truy vấn thiếu index

Một truy vấn vốn nhanh có thể chậm sau khi dữ liệu tăng, thống kê thay đổi hoặc planner chọn kế hoạch khác. Tác động thường thấy là thời gian query tăng, số hàng đọc lớn và pool connection bị giữ lâu hơn.

Điều tra bằng pg_stat_statements để tìm query fingerprint có thời gian tổng hoặc trung bình tăng. Lấy EXPLAIN để xem scan, join, estimated rows và actual rows trong môi trường có thể chạy ANALYZE an toàn.

Ví dụ:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Nếu cần đo kế hoạch thực tế, có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT *
FROM orders
WHERE customer_id = 1001;
~~~

EXPLAIN ANALYZE thực thi câu lệnh. Với truy vấn SELECT thường có thể dùng để đo, nhưng cần xem xét tác động tài nguyên; với INSERT, UPDATE hoặc DELETE, việc chạy thử có thể thay đổi dữ liệu và cần transaction/rollback hoặc môi trường thử nghiệm. Không chạy một truy vấn nặng chỉ để thu thập kế hoạch trong lúc production đang quá tải.

Biện pháp phòng ngừa có thể gồm index phù hợp, thống kê được cập nhật, regression test cho query trọng yếu, theo dõi latency theo query fingerprint và kiểm tra kế hoạch khi thay đổi schema.

### 5.2. Lock contention và transaction kéo dài

Một transaction cập nhật hàng hoặc bảng có thể chặn transaction khác. Nếu blocker giữ transaction lâu, số backend chờ có thể tăng nhanh.

Dùng pg_stat_activity và pg_blocking_pids để tìm blocker, xác định application_name, transaction age và câu lệnh liên quan. Kiểm tra thứ tự cập nhật nhiều bảng, transaction scope và việc ứng dụng có chờ mạng bên ngoài khi đang giữ transaction hay không.

Biện pháp phòng ngừa:

- Giữ transaction ngắn và chỉ bao quanh công việc cần tính nguyên tử.
- Cập nhật nhiều tài nguyên theo thứ tự nhất quán để giảm deadlock.
- Đặt lock_timeout phù hợp cho workload cần phản hồi nhanh.
- Theo dõi transaction age và lock wait.
- Có kiểm thử đồng thời cho luồng ghi quan trọng.

### 5.3. Autovacuum chậm và table bloat

PostgreSQL dùng MVCC. UPDATE và DELETE tạo phiên bản hàng mới hoặc đánh dấu phiên bản cũ không còn nhìn thấy với transaction mới. VACUUM giúp thu hồi không gian có thể tái sử dụng và duy trì visibility information. Nếu autovacuum không theo kịp, bảng và index có thể phình to, truy vấn phải đọc nhiều page hơn và hiệu năng suy giảm.

Kiểm tra số liệu vacuum/analyze:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

Số liệu thống kê là ước lượng và phụ thuộc thời điểm cập nhật. Cần kết hợp kích thước relation, tốc độ thay đổi dữ liệu, log autovacuum và transaction cũ. Transaction hoặc replication slot giữ horizon có thể ngăn PostgreSQL loại bỏ phiên bản hàng cũ.

Biện pháp phòng ngừa gồm theo dõi dead tuples, vacuum activity, long-running transaction, điều chỉnh autovacuum theo đặc điểm bảng và phân vùng workload có tốc độ cập nhật cao.

### 5.4. WAL tăng nhanh và replication lag

WAL ghi lại thay đổi dữ liệu để hỗ trợ phục hồi và replication. Một đợt ghi lớn, checkpoint không phù hợp, replica chậm hoặc replication slot giữ WAL có thể làm dung lượng WAL tăng. Nếu filesystem chứa WAL đầy, database có thể không tiếp tục ghi được.

Kiểm tra replication sender và receiver:

~~~sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Kiểm tra replication slot và lượng WAL được giữ:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots;
~~~

Tên cột có thể khác theo loại slot và phiên bản PostgreSQL; hãy kiểm tra schema catalog của phiên bản đang dùng. Với logical slot, confirmed_flush_lsn có ý nghĩa đối với tiến độ consumer. Không xóa slot chỉ vì nó inactive mà chưa xác định consumer và khả năng cần dữ liệu WAL đó.

Biện pháp phòng ngừa gồm cảnh báo slot inactive kéo dài, theo dõi WAL directory, replication lag, tốc độ WAL generation và có quy trình xử lý consumer chậm.

### 5.5. Hết connection và pool exhaustion

Pool cạn có thể do leak, query chậm, lock, transaction dài hoặc tổng pool trên mọi replica vượt ngân sách. Phân biệt số connection active ở pool với backend đang tồn tại trong pg_stat_activity.

Biện pháp phòng ngừa gồm tính ngân sách kết nối toàn hệ thống, đặt giới hạn concurrency, đo acquisition latency, sử dụng try-with-resources hoặc transaction manager đúng cách, và thiết kế retry có backoff cùng jitter.

### 5.6. Disk, memory và CPU bão hòa

Database có thể chậm vì tài nguyên hệ điều hành. CPU cao có thể do query đắt, parallel workers hoặc workload tăng. Disk latency cao có thể làm query chờ I/O. Memory pressure có thể khiến cache hit giảm hoặc hệ điều hành phải reclaim/swap.

Không nên kết luận chỉ từ một phần trăm CPU hoặc RAM. Hãy đối chiếu với thời điểm query latency tăng, I/O wait, disk queue, swap activity, checkpoint và workload. Biện pháp phòng ngừa có thể là tối ưu query, điều chỉnh concurrency, nâng dung lượng hoặc IOPS, phân vùng dữ liệu và đặt cảnh báo theo latency thay vì chỉ theo utilization.

### 5.7. Thay đổi cấu hình, migration hoặc triển khai

Một migration có thể giữ lock lâu, tạo index lớn, tăng WAL hoặc chặn truy vấn. Thay đổi connection pool, timeout, search_path, role hoặc extension cũng có thể làm ứng dụng lỗi dù database vẫn hoạt động.

Đối chiếu deployment timestamp, migration history, config diff và log PostgreSQL. Cần biết thay đổi nào thực sự đã được áp dụng, không chỉ thay đổi nào được merge.

Biện pháp phòng ngừa gồm migration có kế hoạch lock, canary cho thay đổi ứng dụng, kiểm tra tương thích schema giữa phiên bản cũ và mới, và rollback plan đã được thử.

## 6. Phân biệt nguyên nhân gốc, yếu tố góp phần và triệu chứng

Một báo cáo RCA nên phân loại kết luận rõ ràng:

- **Nguyên nhân trực tiếp:** cơ chế ngay lập tức làm dịch vụ thất bại, ví dụ tất cả connection của pool bị giữ trong các transaction chờ lock.
- **Nguyên nhân gốc:** điều kiện hệ thống khiến cơ chế đó xuất hiện, ví dụ transaction bao trùm một lời gọi HTTP và không có giới hạn thời gian.
- **Yếu tố góp phần:** làm sự cố nghiêm trọng hơn, ví dụ retry không giới hạn hoặc scale out nhân số pool.
- **Triệu chứng:** biểu hiện người dùng hoặc hệ thống quan sát được, ví dụ HTTP 503, pool timeout và CPU tăng.
- **Lỗ hổng phát hiện:** lý do sự cố không được nhận biết sớm, ví dụ thiếu metric transaction age hoặc cảnh báo chỉ dựa trên CPU.

Một incident có thể có nhiều nguyên nhân gốc và nhiều yếu tố góp phần. Không cần ép mọi sự cố vào một nguyên nhân duy nhất nếu bằng chứng cho thấy nhiều cơ chế độc lập cùng tác động.

Ví dụ cách viết kết luận tốt:

“Sau triển khai phiên bản API mới, một luồng cập nhật đơn hàng giữ transaction trong lúc chờ dịch vụ thanh toán. Khi dịch vụ thanh toán tăng latency, transaction giữ row lock lâu hơn, làm các request cập nhật khác chờ. Connection pool của API đạt giới hạn, request timeout kích hoạt retry và làm số request chờ tăng thêm. Cảnh báo hiện tại chỉ theo dõi CPU và số lỗi HTTP nên nhóm phát hiện muộn hơn thời điểm lock bắt đầu.”

Kết luận này mô tả cơ chế, điều kiện kích hoạt và cách sự cố khuếch đại. Nó có thể dẫn trực tiếp đến các hành động cụ thể.

## 7. Chuyển RCA thành hành động khắc phục và phòng ngừa

RCA chỉ tạo giá trị khi kết quả thay đổi cách hệ thống vận hành. Mỗi phát hiện cần được chuyển thành một hành động có chủ sở hữu, thời hạn và cách xác minh.

### 7.1. Phân loại hành động

| Loại hành động | Mục đích | Ví dụ |
|---|---|---|
| Khắc phục (corrective) | Loại bỏ nguyên nhân đã gây sự cố | Thu hẹp transaction scope, sửa query, thêm index |
| Phòng ngừa (preventive) | Ngăn điều kiện tương tự tái xuất hiện | Thêm kiểm thử đồng thời, giới hạn retry, review migration |
| Phát hiện sớm (detective) | Nhận ra dấu hiệu trước khi tác động lớn | Cảnh báo lock wait, pool pending, transaction age |
| Giảm tác động (mitigating) | Hạn chế phạm vi khi lỗi vẫn xảy ra | Backpressure, bulkhead, load shedding, failover plan |
| Phục hồi (recovery) | Rút ngắn thời gian đưa hệ thống về trạng thái tốt | Runbook, backup/restore drill, rollback procedure |

Một biện pháp như “tăng max_connections” có thể giảm triệu chứng trong một số tình huống nhưng không nhất thiết loại bỏ nguyên nhân. Nếu query hoặc transaction vẫn chậm, hệ thống có thể chỉ trì hoãn thời điểm pool cạn và làm PostgreSQL chịu tải đồng thời cao hơn.

### 7.2. Viết action item có thể kiểm chứng

Một action item tốt nên có:

- **Hành động cụ thể:** thay đổi code, cấu hình, dashboard, cảnh báo hoặc quy trình nào.
- **Chủ sở hữu:** một nhóm hoặc vai trò chịu trách nhiệm.
- **Thời hạn:** thời điểm dự kiến hoàn thành.
- **Ưu tiên:** dựa trên mức độ giảm rủi ro và công sức.
- **Tiêu chí hoàn thành:** bằng chứng cho thấy thay đổi hoạt động.
- **Liên kết:** incident, pull request, ticket hoặc runbook liên quan.

Ví dụ:

| Phát hiện | Hành động | Tiêu chí xác minh |
|---|---|---|
| Transaction giữ trong lúc gọi dịch vụ thanh toán | Chuyển lời gọi HTTP ra ngoài transaction; chỉ mở transaction quanh thao tác ghi cần thiết | Integration test mô phỏng HTTP chậm vẫn không giữ row lock trong thời gian gọi |
| Retry làm pool tiếp tục đầy | Đặt tối đa hai lần retry với exponential backoff và jitter; dùng deadline chung | Load test xác nhận retry không vượt ngân sách và queue có giới hạn |
| Không thấy lock wait sớm | Tạo dashboard và cảnh báo theo wait event, blocker age | Alert test kích hoạt khi lock wait vượt ngưỡng đã định |
| Tổng pool vượt ngân sách sau scale out | Tính pool budget theo replica và đưa vào cấu hình triển khai | Kiểm tra scale tối đa vẫn nằm trong connection budget |
| Không có kiểm tra migration nâng cấp | Thêm CI test từ schema phiên bản trước có dữ liệu | Pipeline chứng minh migration upgrade hoàn tất trên dữ liệu mẫu |

Tránh action item mơ hồ như “tối ưu database”, “theo dõi kỹ hơn” hoặc “cải thiện quy trình”. Chúng không chỉ ra ai làm gì và khi nào có thể coi là hoàn tất.

### 7.3. Ưu tiên theo rủi ro

Không phải mọi hành động đều cần hoàn thành ngay. Có thể xếp ưu tiên dựa trên:

- Mức độ nghiêm trọng nếu sự cố tái diễn.
- Khả năng tái diễn và tần suất workload liên quan.
- Phạm vi dịch vụ hoặc dữ liệu bị ảnh hưởng.
- Thời gian phát hiện và phục hồi hiện tại.
- Chi phí triển khai và rủi ro của chính thay đổi.

Hành động giảm thiểu rủi ro lớn, chi phí thấp thường được thực hiện trước. Các thay đổi schema hoặc kiến trúc có phạm vi rộng cần thiết kế, thử nghiệm và rollout có kiểm soát.

## 8. Cập nhật giám sát và cảnh báo

Giám sát sau incident nên phản ánh cơ chế đã gây ra sự cố. Nếu nguyên nhân là transaction giữ lock lâu, chỉ tăng ngưỡng cảnh báo CPU không giúp phát hiện sớm.

### 8.1. Chọn chỉ số gắn với hành vi

Các metric PostgreSQL có thể đưa vào dashboard:

- Số connection theo database, user, application_name và state.
- Số active query, idle in transaction và transaction age.
- Lock wait count và thời gian chờ.
- Query latency theo fingerprint.
- Dead tuples, vacuum/analyze age và table growth.
- WAL generation, dung lượng pg_wal và replication lag.
- Checkpoint activity và I/O latency.
- Tỷ lệ lỗi, deadlock và query bị cancel.

Ở tầng ứng dụng, theo dõi active/idle/pending connection, acquisition latency, connection usage duration, timeout, retry, queue depth và request latency. Dùng percentile như P95/P99 để thấy tail latency thay vì chỉ xem trung bình.

### 8.2. Đặt ngưỡng dựa trên baseline và SLO

Ngưỡng cảnh báo nên dựa trên tải bình thường, headroom và mục tiêu dịch vụ. Ví dụ, cảnh báo khi pending connection liên tục lớn hơn 0 trong một khoảng thời gian, hoặc P95 acquisition latency vượt ngân sách request. Với lock, có thể cảnh báo blocker giữ transaction quá lâu hoặc số session bị block tăng bất thường.

Không nên cảnh báo trên một giá trị đơn lẻ mà không có thời lượng hoặc bối cảnh. Một spike ngắn có thể là hoạt động bình thường. Ngược lại, một chỉ số chưa vượt ngưỡng tuyệt đối nhưng tăng nhanh và kéo dài có thể báo trước sự cố.

### 8.3. Cảnh báo cần dẫn đến hành động

Mỗi alert nên có:

- Điều kiện kích hoạt và mức độ ưu tiên.
- Dashboard hoặc query hỗ trợ điều tra.
- Runbook nêu bước kiểm tra đầu tiên.
- Hướng xử lý an toàn và điều kiện cần escalation.
- Người hoặc nhóm nhận cảnh báo.

Một alert không có hướng xử lý thường tạo tiếng ồn. Sau mỗi incident, kiểm tra alert có phát hiện đúng tín hiệu không, có đến đúng người không và có đủ sớm để hành động không.

## 9. Cập nhật kiểm thử và quy trình thay đổi

Biện pháp phòng ngừa bền vững thường cần được đưa vào CI, code review hoặc quy trình triển khai để lỗi khó quay trở lại.

### 9.1. Thêm kiểm thử hồi quy

Nếu nguyên nhân liên quan query, thêm integration test cho kết quả và trường hợp dữ liệu biên. Nếu liên quan lock, thêm kiểm thử hai transaction đồng thời. Nếu liên quan pool leak, kiểm thử đường exception và xác minh connection được trả về. Nếu liên quan migration, kiểm tra cả database mới và database nâng cấp.

Một regression test nên tái hiện cơ chế gây lỗi ở quy mô nhỏ. Không nhất thiết phải mô phỏng toàn bộ tải production trong mỗi pull request.

### 9.2. Thêm kiểm tra migration

Đối với migration có thể giữ lock hoặc tạo WAL lớn, kiểm tra kích thước bảng, thời gian dự kiến và tác động của câu lệnh. Dùng migration tương thích với phiên bản ứng dụng cũ và mới khi triển khai rolling update.

Với index lớn, xem xét CREATE INDEX CONCURRENTLY khi phù hợp và đảm bảo công cụ migration xử lý đúng việc câu lệnh này không chạy trong transaction block. Kiểm thử upgrade trên dữ liệu đại diện để phát hiện các thay đổi có thể thất bại khi bảng không còn trống.

### 9.3. Thêm kiểm thử tải và khả năng phục hồi

Các bài kiểm thử có thể mô phỏng:

- Query chậm hoặc dịch vụ phụ thuộc chậm.
- Một transaction giữ lock trong khoảng thời gian có kiểm soát.
- Pool đạt maximum và request phải chờ.
- PostgreSQL tạm thời từ chối kết nối.
- Replica chậm hoặc consumer logical replication ngừng hoạt động.
- Retry, queue và worker tăng dưới tải.

Mục tiêu là xác minh giới hạn, timeout, backpressure, cảnh báo và quy trình phục hồi. Chạy các bài kiểm thử gây tải trong môi trường được cấp riêng, với mức tải và thời gian dừng rõ ràng.

## 10. Cập nhật runbook và quy trình ứng phó

Runbook cần phản ánh những gì nhóm đã học được từ incident. Không chỉ ghi lệnh, mà cần mô tả điều kiện sử dụng, quyền cần có, rủi ro và cách xác minh sau thao tác.

Ví dụ một runbook xử lý lock wait có thể gồm:

1. Xác nhận số backend đang chờ lock và phạm vi ứng dụng bị ảnh hưởng.
2. Dùng pg_blocking_pids để tìm blocker.
3. Xác định owner, application_name, transaction age và câu lệnh.
4. Kiểm tra blocker có phải tác vụ hợp lệ, migration hay transaction bị bỏ quên.
5. Chọn cancel query hoặc terminate session theo mức tác động.
6. Theo dõi số session chờ, query latency và pool pending sau can thiệp.
7. Ghi lại PID, thời gian, người thực hiện và kết quả.

Với sự cố WAL tăng, runbook cần chỉ ra cách kiểm tra replication slot, replica lag và dung lượng filesystem; không xóa slot chỉ để giải phóng dung lượng khi chưa xác định tác động đến consumer.

Với pool exhaustion, runbook cần phân biệt pool đầy với PostgreSQL đạt max_connections, hướng dẫn kiểm tra active/pending, transaction age, retry rate và ngân sách kết nối theo replica. Các thao tác nguy hiểm như terminate backend hoặc xóa replication slot cần điều kiện xác minh rõ ràng.

Sau khi cập nhật, diễn tập runbook để chắc chắn lệnh còn đúng với phiên bản PostgreSQL hiện tại và người trực có quyền cần thiết. Runbook không được kiểm chứng dễ trở thành một nguồn rủi ro mới.

## 11. Mẫu báo cáo hậu sự cố

Báo cáo nên ngắn gọn đủ để người đọc hiểu tác động, nguyên nhân, quyết định và hành động. Có thể dùng cấu trúc sau:

~~~text
# Incident review: [Tên sự cố]

## Tóm tắt
- Dịch vụ / database bị ảnh hưởng:
- Thời gian bắt đầu:
- Thời gian phát hiện:
- Thời gian phục hồi:
- Mức độ ảnh hưởng:

## Tác động
- Request hoặc giao dịch bị ảnh hưởng:
- Dữ liệu có bị mất hoặc sai lệch không:
- Người dùng / hệ thống phụ thuộc bị ảnh hưởng:

## Timeline
- [Thời gian] Sự kiện và bằng chứng
- [Thời gian] Sự kiện và bằng chứng

## Nguyên nhân
- Nguyên nhân trực tiếp:
- Nguyên nhân gốc:
- Yếu tố góp phần:
- Lỗ hổng phát hiện:

## Khôi phục
- Biện pháp giảm thiểu đã thực hiện:
- Kết quả quan sát sau thao tác:
- Rủi ro hoặc giới hạn còn lại:

## Hành động
- [Ưu tiên] Hành động / Owner / Due date / Tiêu chí hoàn thành
- [Ưu tiên] Hành động / Owner / Due date / Tiêu chí hoàn thành

## Bằng chứng
- Log, dashboard, query, trace, deployment hoặc ticket:
~~~

Không đưa credential, dữ liệu cá nhân hoặc câu SQL chứa giá trị nhạy cảm vào báo cáo phổ biến rộng. Có thể tham chiếu đến nơi lưu bằng chứng có kiểm soát quyền truy cập.

## 12. Đo hiệu quả của biện pháp phòng ngừa

Một action item được đánh dấu hoàn thành chưa có nghĩa rủi ro đã giảm. Cần xác minh thay đổi hoạt động trong điều kiện gần với tình huống gây sự cố.

Có thể đo theo các nhóm:

| Mục tiêu | Chỉ số hoặc bằng chứng |
|---|---|
| Giảm khả năng tái diễn | Số incident cùng nguyên nhân trong khoảng thời gian theo dõi |
| Phát hiện sớm hơn | MTTD, thời gian từ tín hiệu đầu tiên đến cảnh báo |
| Khôi phục nhanh hơn | MTTR, thời gian từ phát hiện đến phục hồi |
| Giảm tác động | Số request lỗi, thời lượng downtime, số giao dịch bị ảnh hưởng |
| Tăng độ tin cậy | Tỷ lệ regression test, migration test và recovery drill thành công |
| Cải thiện vận hành | Tỷ lệ action item hoàn thành đúng hạn và runbook được diễn tập |

MTTD là Mean Time to Detect, thời gian trung bình để phát hiện sự cố; MTTR thường được dùng cho Mean Time to Restore hoặc Repair tùy quy ước của tổ chức. Cần định nghĩa cách tính thống nhất để so sánh giữa các incident.

Không nên dùng số incident giảm trong một khoảng thời gian ngắn làm bằng chứng duy nhất. Workload có thể chưa gặp lại điều kiện kích hoạt. Hãy kết hợp test hồi quy, load test, diễn tập và metric vận hành.

## 13. Những sai lầm thường gặp trong RCA

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Dừng ở thông báo lỗi cuối cùng | Chỉ xử lý triệu chứng | Dựng timeline và tìm sự kiện đầu tiên |
| Kết luận từ tương quan | Chọn sai biện pháp | Kiểm chứng cơ chế bằng log, metric và test |
| Quy lỗi cho cá nhân | Không phát hiện lỗ hổng hệ thống | Tập trung vào điều kiện, thiết kế và kiểm soát |
| Chỉ ghi một nguyên nhân | Bỏ qua yếu tố khuếch đại | Phân biệt nguyên nhân gốc và yếu tố góp phần |
| Action item mơ hồ | Không thể xác minh tiến độ | Ghi owner, deadline và tiêu chí hoàn thành |
| Chỉ thêm cảnh báo | Phát hiện nhưng không ngăn tái diễn | Kết hợp sửa code, cấu hình, kiểm thử và runbook |
| Không kiểm tra sau thay đổi | Không biết biện pháp có hiệu quả | Chạy test và theo dõi metric sau triển khai |
| Xóa log hoặc reset thống kê quá sớm | Mất bằng chứng | Snapshot và bảo toàn dữ liệu điều tra trước |

RCA nên có văn hóa không đổ lỗi. Điều này không có nghĩa bỏ qua trách nhiệm thực hiện hoặc quyết định kỹ thuật. Nó có nghĩa phân tích cách hệ thống, quy trình và điều kiện làm việc cho phép sự cố xảy ra, thay vì kết thúc bằng việc tìm một cá nhân để quy lỗi.

## 14. Quy trình RCA có thể áp dụng sau mỗi incident PostgreSQL

Một quy trình thực tế có thể đi theo thứ tự:

1. **Ổn định dịch vụ:** giảm tải, khôi phục dữ liệu hoặc kết nối và bảo đảm người dùng có thể tiếp tục công việc.
2. **Bảo toàn bằng chứng:** lưu log, metric, query statistics, cấu hình và deployment history.
3. **Xác định tác động:** ghi phạm vi, thời lượng, request và dữ liệu bị ảnh hưởng.
4. **Dựng timeline:** chuẩn hóa múi giờ và ghép sự kiện từ ứng dụng, PostgreSQL và hạ tầng.
5. **Đặt giả thuyết:** liệt kê các cơ chế có thể giải thích dữ liệu.
6. **Kiểm chứng:** tìm bằng chứng ủng hộ và phản bác từng giả thuyết.
7. **Viết nguyên nhân:** tách nguyên nhân trực tiếp, nguyên nhân gốc, yếu tố góp phần và lỗ hổng phát hiện.
8. **Tạo hành động:** gán owner, deadline, mức ưu tiên và tiêu chí hoàn thành.
9. **Cập nhật hệ thống:** sửa code, query, schema, cấu hình, monitoring, CI hoặc runbook.
10. **Xác minh hiệu quả:** chạy regression test, load test hoặc recovery drill và theo dõi metric.

Không cần đợi đến khi báo cáo hoàn chỉnh mới tạo hành động giảm rủi ro khẩn cấp. Những biện pháp giảm thiểu an toàn có thể được thực hiện ngay trong incident response; báo cáo sau đó ghi rõ lý do, bằng chứng và tác động của chúng.

## 15. Duy trì vòng lặp cải tiến

Phân tích nguyên nhân gốc là một phần của vòng đời vận hành PostgreSQL. Mỗi incident cung cấp thông tin về cách hệ thống phản ứng dưới tải, cách ứng dụng sử dụng connection, cách migration tác động đến dữ liệu và nơi giám sát chưa đủ nhạy.

Để bài học không mất đi, hãy liên kết báo cáo incident với ticket, pull request, dashboard, test và runbook đã được cập nhật. Theo dõi action item đến khi có bằng chứng hoàn thành, rồi kiểm tra lại sau một khoảng thời gian đủ để đánh giá hiệu quả. Khi thay đổi kiến trúc hoặc nâng cấp PostgreSQL, xem lại các biện pháp phòng ngừa liên quan để bảo đảm chúng vẫn phù hợp.

Một quy trình RCA hiệu quả không cố gắng dự đoán mọi lỗi có thể xảy ra. Nó giúp nhóm hiểu cơ chế của sự cố đã xảy ra, giảm điều kiện khiến sự cố tái diễn, phát hiện dấu hiệu sớm hơn và phục hồi có kiểm soát hơn khi một thành phần vẫn gặp lỗi.

