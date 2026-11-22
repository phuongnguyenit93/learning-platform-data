# Giao dịch đọc kéo dài và ảnh hưởng đến dọn dẹp dữ liệu cũ

Trong cơ sở dữ liệu hỗ trợ kiểm soát đồng thời nhiều phiên bản (MVCC), một giao dịch đọc thường nhìn thấy ảnh chụp dữ liệu nhất quán tại một thời điểm. Khi giao dịch ghi thay đổi một hàng, hệ quản trị có thể giữ lại phiên bản cũ để các giao dịch đọc đang hoạt động tiếp tục nhìn thấy dữ liệu đúng theo snapshot của chúng. Những phiên bản cũ chỉ được thu hồi khi hệ quản trị xác định không còn giao dịch nào cần chúng.

Một giao dịch đọc kéo dài có thể giữ snapshot quá lâu và trì hoãn việc dọn dẹp phiên bản không còn cần thiết. Hậu quả không chỉ là truy vấn đọc chậm: dữ liệu cũ tích tụ, undo hoặc version store tăng, dung lượng lưu trữ phình to, I/O và CPU cho bảo trì tăng, thậm chí gây áp lực lên toàn hệ thống. Hiểu cơ chế này giúp phân biệt tranh chấp khóa với việc giữ phiên bản dữ liệu, xác định đúng giao dịch gây cản trở và chọn cách xử lý phù hợp.

Bài học thuộc chương **Giao dịch và tranh chấp** của module DATABASE_PERFORMANCE. Module DATABASE_PERFORMANCE rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, khi điều tra giao dịch đọc kéo dài, cần kết hợp tuổi giao dịch, snapshot, thống kê version/undo, hoạt động vacuum hoặc purge, tài nguyên và số liệu trước/sau xử lý.

## 1. MVCC và lý do hệ quản trị phải giữ phiên bản cũ

MVCC cho phép nhiều giao dịch đồng thời đọc và ghi dữ liệu mà không phải buộc mọi thao tác đọc chờ mọi thao tác ghi. Thay vì chỉ ghi đè một giá trị rồi khiến tất cả phiên đọc nhìn thấy ngay giá trị mới, hệ quản trị duy trì thông tin phiên bản và quy tắc xác định phiên bản nào hiển thị với từng snapshot.

Ví dụ, tài khoản A có số dư 100. Một giao dịch T1 bắt đầu đọc và lấy snapshot. Sau đó giao dịch T2 cập nhật số dư thành 150 rồi commit. T1 vẫn có thể cần nhìn thấy số dư 100 để kết quả của nó nhất quán với snapshot ban đầu. Vì vậy, hệ quản trị phải giữ đủ thông tin về phiên bản cũ cho đến khi T1 không còn cần nó.

Quy trình khái quát:

1. Giao dịch đọc bắt đầu và có snapshot hoặc read view theo mức cô lập.
2. Giao dịch ghi cập nhật hàng và commit phiên bản mới.
3. Hệ quản trị giữ phiên bản cũ trong heap, undo log hoặc version store tùy kiến trúc.
4. Tiến trình dọn dẹp xác định các phiên bản không còn có thể được snapshot đang hoạt động nhìn thấy.
5. Những phiên bản an toàn được thu hồi hoặc đánh dấu có thể tái sử dụng.

Một giao dịch đọc kéo dài có thể làm chậm bước 4. Hệ quản trị không thể chỉ dựa vào việc phiên bản mới đã commit để xóa phiên bản cũ; nó phải bảo đảm không giao dịch nào còn cần phiên bản đó.

### Snapshot không giống nhau ở mọi mức cô lập

Thời điểm snapshot được xác định phụ thuộc hệ quản trị và isolation level:

- **Read Committed:** thường tạo snapshot theo từng câu lệnh trong nhiều hệ MVCC. Một giao dịch kéo dài nhưng mỗi câu lệnh có snapshot mới có thể ít giữ phiên bản cũ hơn so với snapshot cố định toàn giao dịch; tuy nhiên, một câu SELECT đơn lẻ chạy rất lâu vẫn có thể giữ snapshot trong suốt thời gian thực thi.
- **Repeatable Read hoặc Snapshot Isolation:** thường giữ snapshot ổn định trong phạm vi giao dịch hoặc theo quy tắc tương đương. Giao dịch mở lâu có thể giữ mốc phiên bản cũ lâu hơn.
- **Serializable:** có thể dùng snapshot, khóa hoặc cơ chế kiểm tra xung đột tùy sản phẩm. Không thể suy ra tác động chỉ từ tên isolation level; cần hiểu cách triển khai cụ thể.
- **Lock-based isolation:** một số thao tác đọc có thể giữ shared lock trong thời gian dài và trực tiếp chặn thao tác ghi. Đây là dạng tranh chấp khóa khác với việc giữ phiên bản MVCC.

Không phải mọi giao dịch đọc lâu đều chặn ghi hoặc giữ phiên bản theo cùng cách. Cần xác định engine, isolation level, snapshot lifetime và loại truy vấn đang chạy.

## 2. Vì sao giao dịch đọc lâu trì hoãn dọn dẹp?

Tiến trình dọn dẹp cần biết phiên bản cũ nhất nào còn có thể được tham chiếu. Một snapshot lâu đời có thể cần đọc phiên bản đã bị thay thế bởi nhiều lần cập nhật sau đó. Nếu xóa phiên bản đó quá sớm, giao dịch đọc sẽ thấy dữ liệu sai hoặc không thể tái dựng ảnh chụp nhất quán.

Hình dung một hàng được cập nhật liên tục:

~~~text
Thời gian ---------------------------------------------------->

T1:  BEGIN, lấy snapshot S0 ------------------------------- COMMIT
T2:       UPDATE v1 -> v2, COMMIT
T3:             UPDATE v2 -> v3, COMMIT
T4:                   UPDATE v3 -> v4, COMMIT

Phiên bản:
        v1       v2       v3       v4
        |--------|--------|--------|
T1 vẫn có thể cần v1 theo snapshot S0.
Tiến trình dọn dẹp phải giữ đủ lịch sử để T1 đọc đúng.
~~~

Trong thời gian T1 còn giữ snapshot, các phiên bản cũ liên quan có thể chưa đủ điều kiện thu hồi. Khi nhiều hàng bị cập nhật hoặc xóa, số phiên bản tồn đọng có thể tăng nhanh. Giao dịch càng lâu, hệ thống càng có thể phải duy trì lịch sử lớn hơn.

### Giao dịch đọc không cần ghi vẫn có thể là nguyên nhân

Một giao dịch chỉ chạy SELECT có thể giữ snapshot mà không thay đổi dữ liệu. Nếu truy vấn tạo báo cáo lớn, xuất dữ liệu, chạy cursor lâu hoặc ứng dụng mở transaction rồi chờ người dùng, snapshot có thể tồn tại hàng phút hoặc hàng giờ.

Các trường hợp thường gặp:

- Báo cáo quét bảng lớn và giữ transaction cho đến khi truyền hết kết quả.
- Export dữ liệu theo cursor, ứng dụng đọc từng phần chậm.
- Giao dịch bắt đầu trước khi gọi một dịch vụ bên ngoài rồi mới tiếp tục đọc.
- Ứng dụng mở transaction ở đầu request nhưng quên commit/rollback khi xử lý lỗi.
- Connection pool trả kết nối về pool trong trạng thái transaction còn mở.
- Một job ETL hoặc đồng bộ đọc snapshot nhất quán trong thời gian dài.
- Câu SELECT chờ khóa, chờ I/O hoặc bị treo do ứng dụng không tiêu thụ kết quả.

Trạng thái **idle in transaction** hoặc tên tương đương đặc biệt đáng chú ý: câu lệnh có thể đã kết thúc nhưng transaction vẫn mở, do đó snapshot hoặc lock vẫn được giữ.

## 3. Hậu quả đối với hiệu năng và vận hành

Khi dọn dẹp phiên bản cũ bị trì hoãn, nhiều loại chi phí có thể xuất hiện cùng lúc.

### Tích tụ phiên bản chết hoặc lịch sử undo

Các hàng cũ không còn là phiên bản hiện hành nhưng chưa thể thu hồi vẫn chiếm dung lượng. Với workload cập nhật/xóa nhiều, số phiên bản tồn đọng có thể tăng liên tục.

### Bảng và chỉ mục phình to

Phiên bản cũ hoặc mục chỉ mục liên quan có thể làm tăng số trang cần lưu trữ và quét. Tỷ lệ dữ liệu hữu ích trên mỗi trang giảm, cache chứa được ít dữ liệu hữu ích hơn và truy vấn có thể phải đọc nhiều trang hơn.

### Tăng CPU và I/O cho dọn dẹp

Khi snapshot cũ kết thúc, tiến trình vacuum hoặc purge có thể phải xử lý một lượng lịch sử lớn. Hoạt động bảo trì cạnh tranh CPU, I/O và bộ nhớ với truy vấn ứng dụng. Việc dọn dẹp theo sau một thời gian trì hoãn dài có thể tạo ra tải tăng đột biến.

### Tăng version store hoặc undo tablespace

Một số engine lưu phiên bản trong vùng dữ liệu riêng. Nếu phiên bản không được thu hồi, vùng này tăng kích thước và có thể gây áp lực dung lượng. Với SQL Server, version store có thể nằm trong tempdb hoặc Persistent Version Store tùy cấu hình và kiến trúc. Với Oracle và InnoDB, undo phục vụ consistent read và các mục đích khác có thể phải được giữ lâu hơn.

### Tăng độ trễ và giảm thông lượng

Truy vấn đọc có thể phải đi qua nhiều phiên bản hơn; thao tác ghi tạo thêm lịch sử; tiến trình bảo trì tiêu tốn tài nguyên; bộ nhớ đệm bị ảnh hưởng. Các yếu tố này có thể làm tăng p95/p99, giảm throughput và khiến độ trễ biến động.

### Rủi ro vận hành đặc thù

Một số hệ quản trị có nguy cơ transaction ID wraparound nếu vacuum không thể tiến đủ xa; một số hệ có thể báo lỗi snapshot quá cũ khi undo cần thiết đã bị ghi đè hoặc không còn khả dụng. Cơ chế và ngưỡng cụ thể phụ thuộc nền tảng, nhưng đều cho thấy việc giữ lịch sử và dọn dẹp là vấn đề vận hành quan trọng.

## 4. Phân biệt giữ phiên bản với tranh chấp khóa

Hai hiện tượng có thể cùng xảy ra nhưng không đồng nhất:

| Hiện tượng | Cơ chế | Dấu hiệu thường gặp |
| --- | --- | --- |
| Tranh chấp khóa | Giao dịch giữ lock khiến giao dịch khác phải chờ | Blocking chain, lock wait, deadlock |
| Giữ snapshot lâu | Giao dịch còn cần phiên bản cũ nên dọn dẹp không thể thu hồi | Oldest transaction/snapshot age cao, dead tuples hoặc undo/version store tăng |
| Truy vấn đọc lâu do I/O/CPU | Truy vấn chưa hoàn tất nên snapshot có thể còn hiệu lực | Query duration cao, CPU, I/O, temp spill |
| Transaction idle nhưng chưa kết thúc | Ứng dụng giữ transaction sau khi câu lệnh hoàn tất | Idle-in-transaction, open transaction age cao |

Trong MVCC, một truy vấn đọc thường không chặn cập nhật chỉ vì nó đang đọc. Tuy nhiên, nó có thể gián tiếp làm tăng chi phí ghi và trì hoãn thu hồi phiên bản. Ở isolation level hoặc thao tác cần khóa, truy vấn đọc cũng có thể giữ lock và chặn writer. Hãy kiểm tra cả lock waits lẫn version retention thay vì giả định chỉ có một nguyên nhân.

## 5. PostgreSQL: snapshot cũ và VACUUM

PostgreSQL dùng MVCC với các thông tin transaction ID trên tuple. UPDATE thường tạo phiên bản tuple mới; phiên bản cũ trở thành dead tuple khi không còn cần cho snapshot nào. VACUUM xác định và thu hồi không gian có thể tái sử dụng, đồng thời duy trì visibility map và các thông tin phục vụ vận hành.

Một transaction có snapshot cũ có thể giữ xmin horizon ở quá khứ. VACUUM không thể loại bỏ các tuple mà snapshot đó vẫn có thể nhìn thấy. Vì vậy, dead tuples có thể tích tụ dù autovacuum vẫn chạy.

### Quan sát transaction đang mở

Truy vấn sau giúp xem các backend có transaction lâu:

~~~sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    query_start,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Chú ý các session idle in transaction, tuổi xact_age, câu lệnh hiện tại hoặc gần nhất và trạng thái chờ. query_start và xact_start có ý nghĩa khác nhau: câu lệnh hiện tại có thể mới bắt đầu nhưng transaction đã mở từ lâu.

### Kiểm tra bảng có dead tuples

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
~~~

Các số liệu thống kê là ước lượng và có thể trễ; không dùng một giá trị n_dead_tup đơn lẻ để kết luận bảng chắc chắn bị bloat. Cần xem xu hướng, kích thước quan hệ, tốc độ ghi và lịch sử vacuum.

### Kiểm tra vacuum đang chạy

~~~sql
SELECT
    pid,
    relid::regclass AS table_name,
    phase,
    heap_blks_scanned,
    heap_blks_total,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum;
~~~

Nếu phiên vacuum chạy lâu, hãy xem phase, lượng trang đã quét và mức tiến triển. Không kết luận vacuum bị treo chỉ vì một lần đọc số liệu không thay đổi; cần quan sát theo thời gian và xem wait event, I/O, khóa cùng các snapshot đang hoạt động.

### Kiểm tra các nguồn giữ horizon khác

Transaction lâu không phải nguồn duy nhất giữ xmin. Replication slot, prepared transaction hoặc một số cơ chế snapshot/replication khác cũng có thể ngăn tiến trình vacuum tiến qua mốc an toàn. Vì vậy, nếu đã xử lý transaction lâu mà dead tuples vẫn không được thu hồi, cần điều tra các horizon khác bằng các view phù hợp với phiên bản PostgreSQL.

### Biện pháp xử lý

- Kết thúc transaction đọc ngay khi hoàn tất công việc.
- Tránh giữ transaction mở trong lúc chờ người dùng hoặc dịch vụ bên ngoài.
- Chia export/batch thành các phần có ranh giới nhất quán được xác định rõ.
- Tối ưu câu truy vấn và chỉ mục để giảm thời gian giữ snapshot.
- Theo dõi autovacuum, ngưỡng kích hoạt và tốc độ tạo dead tuples.
- Xác định replication slot hoặc prepared transaction giữ xmin nếu vacuum vẫn bị chặn.

Tăng tần suất hoặc tài nguyên autovacuum không thể thu hồi các tuple mà snapshot cũ vẫn cần. Trước tiên phải giải quyết nguyên nhân giữ horizon.

## 6. MySQL InnoDB: read view, undo log và purge

InnoDB dùng MVCC và undo log để tái dựng phiên bản cũ cho consistent read. Khi transaction tạo read view còn hoạt động, purge thread phải giữ lại những undo record mà read view đó có thể cần. Một transaction đọc kéo dài có thể làm History List Length tăng và trì hoãn purge.

### Quan sát transaction đang mở

Có thể xem các transaction InnoDB qua INFORMATION_SCHEMA.INNODB_TRX:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_mysql_thread_id,
    trx_isolation_level,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Không phải mọi transaction đều có trx_query khác NULL; một transaction có thể đang idle sau khi câu lệnh cuối kết thúc. Hãy kết hợp tuổi transaction, trạng thái connection và thông tin process list để xác định ứng dụng sở hữu session.

### Quan sát lịch sử purge

SHOW ENGINE INNODB STATUS cung cấp thông tin InnoDB, trong đó phần TRANSACTIONS có thể hiển thị History list length và trạng thái purge. Cần đọc xu hướng qua nhiều thời điểm:

- History list length tăng liên tục: purge có thể đang tụt lại hoặc bị một read view cũ giữ.
- History list length giảm sau khi transaction lâu kết thúc: purge đang xử lý được lịch sử tồn đọng.
- History list length cao nhưng ổn định: cần xem tốc độ tạo undo, dung lượng, độ trễ và hoạt động purge trước khi kết luận có sự cố.

Tên chỉ số và cách diễn giải chi tiết có thể thay đổi theo phiên bản.

### Biện pháp xử lý

- Commit hoặc rollback transaction đọc khi hoàn tất.
- Tránh mở transaction trước khi ứng dụng bắt đầu xử lý kết quả hoặc chờ I/O bên ngoài.
- Dùng phân trang theo khóa hoặc batch có snapshot ngắn nếu nghiệp vụ cho phép.
- Theo dõi History List Length, dung lượng undo tablespace và tốc độ purge.
- Điều tra transaction lâu, kết nối idle và luồng ứng dụng giữ connection.

Điều chỉnh tốc độ purge hoặc giới hạn lag có thể ảnh hưởng đến writer và tải hệ thống. Không thay đổi tham số chỉ để ép purge chạy nhanh khi read view cũ vẫn còn cần undo record.

## 7. SQL Server: row versioning và version store

SQL Server có thể dùng row versioning cho READ COMMITTED SNAPSHOT (RCSI) hoặc SNAPSHOT isolation. Các phiên bản hàng được lưu trong version store để truy vấn đọc có thể nhìn thấy phiên bản phù hợp với thời điểm snapshot.

Với RCSI, snapshot thường được áp dụng theo câu lệnh; với SNAPSHOT isolation, transaction có thể giữ một góc nhìn nhất quán trong suốt transaction. Một transaction snapshot lâu có thể làm chậm quá trình dọn dẹp các phiên bản mà nó còn cần.

Vị trí version store phụ thuộc cấu hình và kiến trúc. Trong các cấu hình truyền thống, version store dùng tempdb; với Accelerated Database Recovery (ADR), Persistent Version Store (PVS) được dùng trong user database. Khi điều tra, phải xác định đúng nơi lưu phiên bản.

### Quan sát snapshot transaction đang hoạt động

Ví dụ truy vấn DMV:

~~~sql
SELECT
    transaction_id,
    transaction_sequence_num,
    first_snapshot_sequence_num,
    elapsed_time_seconds,
    max_version_chain_traversed,
    average_version_chain_traversed
FROM sys.dm_tran_active_snapshot_database_transactions
ORDER BY elapsed_time_seconds DESC;
~~~

DMV này tập trung vào các transaction snapshot đang hoạt động. Quyền xem DMV phụ thuộc phiên bản và quyền hệ thống. Hãy kết hợp với session, request và transaction DMV để tìm ứng dụng sở hữu giao dịch.

### Kiểm tra dung lượng version store

Với version store trong tempdb, có thể xem mức sử dụng theo database:

~~~sql
SELECT
    database_id,
    reserved_page_count,
    reserved_space_kb
FROM sys.dm_tran_version_store_space_usage
ORDER BY reserved_space_kb DESC;
~~~

Với ADR/PVS, dùng các DMV và báo cáo dung lượng phù hợp phiên bản SQL Server đang triển khai. Không giả định chỉ tempdb mới chứa version store trong mọi cấu hình.

### Biện pháp xử lý

- Xác định transaction snapshot lâu nhất và session/ứng dụng tương ứng.
- Rút ngắn thời gian transaction và tránh giữ snapshot qua các bước xử lý bên ngoài.
- Theo dõi version store ở đúng vị trí, dung lượng tempdb/PVS và tốc độ tăng.
- Kiểm tra các truy vấn đọc dài, cursor và ứng dụng tiêu thụ kết quả chậm.
- Đánh giá isolation level theo yêu cầu nhất quán, không tự hạ mức cô lập chỉ để giảm version store.

Nếu version store đã tăng lớn, kết thúc transaction gây giữ phiên bản có thể cho phép cleanup tiến lên, nhưng dung lượng file có thể không tự động thu nhỏ ngay. Cần phân biệt dung lượng đã cấp phát, dung lượng đang sử dụng và khả năng tái sử dụng.

## 8. Oracle: consistent read và undo retention

Oracle dùng undo để tái dựng phiên bản nhất quán khi truy vấn cần đọc dữ liệu trước một thay đổi đã commit. Một truy vấn hoặc transaction đọc lâu có thể cần các undo record cũ trong thời gian dài.

Nếu undo cần thiết không còn khả dụng do bị ghi đè hoặc không được giữ đủ lâu, truy vấn có thể gặp lỗi ORA-01555: snapshot too old. Lỗi này không đồng nghĩa đơn giản với việc undo tablespace đầy; cần xem thời gian truy vấn, tốc độ ghi, dung lượng undo, retention và mức độ tái sử dụng undo.

### Quan sát hoạt động undo

V$UNDOSTAT cung cấp số liệu theo khoảng thời gian về undo generation, số lần hết không gian, tuned undo retention và các lỗi snapshot quá cũ. Ví dụ:

~~~sql
SELECT
    begin_time,
    end_time,
    undoblks,
    txncount,
    maxquerylen,
    tuned_undoretention,
    ssolderrcnt,
    nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC;
~~~

Các cột có thể khác theo phiên bản hoặc quyền truy cập. MAXQUERYLEN, TUNED_UNDORETENTION và SSOLDERRCNT giúp đối chiếu thời gian truy vấn với khả năng giữ undo. Cần xem nhiều khoảng liên tiếp để nhận biết xu hướng.

### Biện pháp xử lý

- Rút ngắn truy vấn và transaction đọc khi có thể.
- Đảm bảo undo tablespace và retention được cấu hình phù hợp với workload thực tế.
- Theo dõi tốc độ tạo undo, thời gian truy vấn dài nhất và lỗi snapshot too old.
- Cân nhắc chia batch hoặc thiết kế báo cáo để giảm thời gian cần giữ consistent read.

Không tăng retention một cách mù quáng. Cấu hình cần phù hợp với dung lượng, tốc độ phát sinh undo và yêu cầu nhất quán; dung lượng không đủ vẫn có thể gây áp lực hoặc lỗi vận hành.

## 9. Những dấu hiệu cần theo dõi

Không có một chỉ số duy nhất chứng minh giao dịch đọc lâu đang chặn dọn dẹp. Hãy kết hợp nhiều tín hiệu và xem xu hướng.

| Nhóm tín hiệu | Chỉ số hoặc dấu hiệu | Câu hỏi cần trả lời |
| --- | --- | --- |
| Transaction | Tuổi transaction, tuổi snapshot, idle-in-transaction | Transaction nào mở lâu nhất? |
| MVCC cleanup | Oldest xmin, dead tuples, History List Length, version store | Lịch sử cũ có tăng và bị giữ không? |
| Bảo trì | Vacuum/purge progress, thời điểm vacuum gần nhất | Tiến trình dọn dẹp có chạy và tiến triển không? |
| Lưu trữ | Table/index bloat, undo tablespace, tempdb/PVS usage | Dung lượng tăng ở đâu và tốc độ thế nào? |
| Truy vấn | Duration, rows read, cursor fetch, wait events | Câu lệnh nào giữ snapshot lâu? |
| Tài nguyên | CPU, IOPS, read/write latency, memory, temp I/O | Cleanup và workload đang cạnh tranh tài nguyên nào? |
| Chất lượng dịch vụ | p95/p99, throughput, timeout, lỗi ứng dụng | Người dùng bị ảnh hưởng ra sao? |

Đặt ngưỡng cảnh báo dựa trên baseline và đặc điểm hệ thống. Một History List Length hoặc số dead tuples có thể bình thường ở hệ thống ghi nhiều; xu hướng tăng kéo dài, dung lượng tăng nhanh và latency suy giảm mới là tín hiệu mạnh hơn.

## 10. Quy trình điều tra giao dịch đọc kéo dài

Khi bảng hoặc version store tăng bất thường, hãy điều tra theo thứ tự:

1. **Xác định triệu chứng:** bảng phình to, undo/version store tăng, vacuum/purge không tiến, I/O tăng hay truy vấn đọc chậm?
2. **Tìm transaction lâu nhất:** xem tuổi transaction, thời điểm bắt đầu, isolation level, trạng thái session và câu lệnh gần nhất.
3. **Phân biệt active với idle:** truy vấn đang chạy, đang chờ hay ứng dụng đã ngừng làm việc nhưng chưa commit/rollback?
4. **Xác định snapshot lifetime:** transaction hay statement đang giữ snapshot? Mức cô lập và engine có ý nghĩa gì?
5. **Tìm tiến trình dọn dẹp:** vacuum, purge hoặc version cleanup đang ở trạng thái nào, có tiến triển không?
6. **Kiểm tra các nguồn giữ lịch sử khác:** replication slot, prepared transaction, snapshot khác hoặc cấu hình retention.
7. **Đo tốc độ phát sinh lịch sử:** số update/delete, undo generation, version store growth và dead tuple generation.
8. **Xác định chủ sở hữu:** ánh xạ session về service, request, job, batch hoặc người vận hành.
9. **Chọn biện pháp ít rủi ro:** kết thúc transaction đúng quy trình, sửa vòng đời transaction, chia batch hoặc tối ưu truy vấn.
10. **Theo dõi sau xử lý:** xác nhận transaction đã kết thúc, cleanup tiến triển, lịch sử giảm hoặc ổn định và tài nguyên phục hồi.

Không chỉ nhìn vào tuổi câu SQL. Một câu lệnh có thể đã kết thúc nhưng transaction vẫn mở; ngược lại, một câu SELECT chạy lâu có thể là nguyên nhân giữ snapshot dù trạng thái session là active.

## 11. Biện pháp thiết kế ứng dụng để tránh snapshot bị giữ lâu

### Giữ transaction quanh đúng phần công việc cần nhất quán

Mở transaction sát thời điểm cần đọc/ghi và commit hoặc rollback ngay khi hoàn thành. Tránh đặt các thao tác không liên quan vào trong transaction:

~~~text
Không nên:
BEGIN
  Đọc dữ liệu
  Gọi API bên ngoài
  Chờ người dùng xác nhận
  Tạo file hoặc upload
  Ghi kết quả
COMMIT

Nên cân nhắc:
  Đọc snapshot/dữ liệu cần thiết
  Đóng transaction
  Xử lý hoặc truyền dữ liệu bên ngoài transaction
  Mở transaction ngắn để ghi kết quả nếu cần
~~~

Việc tách transaction cần bảo đảm yêu cầu nhất quán nghiệp vụ. Nếu dữ liệu phải phản ánh cùng một thời điểm trên nhiều bước, hãy thiết kế rõ snapshot, watermark hoặc phiên bản dữ liệu thay vì vô tình giữ một transaction không giới hạn.

### Dùng batch có ranh giới rõ ràng

Với export hoặc xử lý hàng triệu bản ghi, có thể chia công việc thành các batch nhỏ. Mỗi batch đọc và xử lý một phạm vi, sau đó đóng transaction trước khi tiếp tục. Điều này giảm thời gian giữ snapshot và giới hạn lượng dữ liệu tạm.

Tuy nhiên, các batch có snapshot khác nhau có thể nhìn thấy dữ liệu thay đổi giữa các lần chạy. Nếu cần một kết quả nhất quán trên toàn bộ export, cần xác định chiến lược:

- Dùng snapshot/backup/reporting copy có vòng đời được quản lý.
- Ghi nhận watermark hoặc mốc dữ liệu và lọc mọi batch theo cùng mốc nghiệp vụ.
- Tạo tập dữ liệu trung gian ổn định trong một quy trình kiểm soát được.
- Chấp nhận eventual consistency nếu nghiệp vụ cho phép.

Không thể vừa đóng mọi transaction ngay lập tức vừa mặc định các batch độc lập sẽ nhìn thấy đúng một snapshot giống nhau.

### Dùng keyset pagination khi phù hợp

Phân trang bằng OFFSET sâu có thể đọc và bỏ qua nhiều hàng. Keyset pagination dùng khóa cuối trang trước để tiếp tục từ vị trí gần đó:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at < ?
   OR (created_at = ? AND order_id < ?)
ORDER BY created_at DESC, order_id DESC
LIMIT 500;
~~~

Điều kiện trên giả định thứ tự giảm dần và order_id là tie-breaker duy nhất. Cần chỉ mục tương thích với thứ tự này. Keyset pagination có thể giảm lượng đọc và thời gian mỗi batch, nhưng nếu mỗi trang dùng transaction/snapshot mới thì dữ liệu mới hoặc thay đổi có thể ảnh hưởng kết quả giữa các trang. Hãy chọn watermark hoặc quy tắc nhất quán phù hợp với nghiệp vụ.

### Không để connection pool giữ transaction

Ứng dụng cần:

- Commit/rollback trong khối xử lý bảo đảm chạy cả khi có exception.
- Không trả connection về pool khi transaction chưa kết thúc.
- Đóng cursor/result set đúng lúc.
- Không giữ transaction trong khi chờ mạng hoặc tác vụ bất đồng bộ.
- Có log transaction start/end và request/job ID để truy vết.
- Có kiểm tra thời gian transaction trong middleware hoặc data access layer.

Các timeout như idle-in-transaction timeout hoặc transaction timeout có thể bảo vệ hệ thống, nhưng phải cấu hình theo SLA và cách ứng dụng xử lý lỗi. Timeout quá ngắn có thể hủy báo cáo hợp lệ; quá dài không giải quyết được transaction bị bỏ quên.

## 12. Cách xử lý transaction lâu đang tồn tại

Khi tìm thấy transaction giữ snapshot lâu, không nên lập tức kill mọi session có tuổi cao. Trước tiên xác định:

- Session thuộc ứng dụng, job hay thao tác quản trị nào?
- Nó có đang chạy công việc hợp lệ hoặc tạo báo cáo quan trọng không?
- Có đang giữ lock ngoài snapshot không?
- Nếu hủy, ứng dụng có retry và có thể tạo thêm tải không?
- Rollback có thể mất bao lâu hoặc cần giải phóng tài nguyên gì?
- Có quy trình phối hợp với chủ sở hữu dịch vụ không?

Nếu transaction bị bỏ quên hoặc không còn cần thiết, hãy yêu cầu ứng dụng commit/rollback đúng cách hoặc kết thúc session theo quy trình vận hành. Hủy một transaction ghi có thể cần rollback; hủy một transaction đọc có thể giải phóng snapshot nhanh hơn nhưng vẫn có thể cần thời gian để session đóng và cleanup tiến triển.

Sau khi transaction kết thúc, không giả định dung lượng file lập tức giảm. Tiến trình vacuum/purge/version cleanup cần thời gian để xử lý lịch sử; không gian có thể được tái sử dụng nội bộ mà file vật lý vẫn giữ kích thước đã cấp phát.

## 13. Những biện pháp không giải quyết được nguyên nhân gốc

- **Chỉ tăng autovacuum hoặc purge workers:** không thể xóa phiên bản mà snapshot cũ vẫn cần.
- **Chỉ tăng dung lượng undo/version store:** có thể trì hoãn sự cố nhưng không sửa transaction bị giữ quá lâu.
- **Chỉ thêm chỉ mục:** có thể rút ngắn truy vấn, nhưng không giải phóng snapshot đang mở do ứng dụng chưa commit.
- **Chỉ kill truy vấn hiện tại:** transaction có thể vẫn tồn tại nếu connection hoặc transaction scope không được đóng đúng cách.
- **Chỉ chạy VACUUM thủ công:** vacuum vẫn phải tuân thủ visibility horizon và không thể thu hồi tuple còn cần thiết.
- **Hạ isolation level không đánh giá:** có thể làm thay đổi tính nhất quán mà nghiệp vụ dựa vào, đồng thời không bảo đảm mọi loại version retention biến mất.
- **Chỉ nhìn dung lượng file:** file không giảm kích thước không có nghĩa cleanup thất bại; cần xem không gian đã được tái sử dụng hay chưa.

Điều chỉnh tài nguyên bảo trì, dung lượng hoặc isolation level có thể là một phần của giải pháp, nhưng phải đi sau việc xác định transaction giữ snapshot và yêu cầu nhất quán.

## 14. Ví dụ điều tra: báo cáo đọc lâu khiến lịch sử phiên bản tăng

Một hệ thống bán hàng có job xuất báo cáo toàn bộ đơn hàng. Job mở transaction, chạy SELECT lớn rồi gửi từng batch kết quả đến dịch vụ lưu trữ. Trong khi job chạy, ứng dụng tiếp tục cập nhật trạng thái đơn hàng và thông tin khách hàng.

Triệu chứng:

- Độ trễ truy vấn ghi tăng dần.
- PostgreSQL có nhiều dead tuples và autovacuum không thu hồi được như dự kiến; hoặc MySQL có History List Length tăng; hoặc SQL Server version store tăng.
- Một transaction đọc có tuổi lớn hơn nhiều so với thời gian truy vấn thông thường.
- Sau khi job hoàn tất, tiến trình dọn dẹp bắt đầu giảm lịch sử tồn đọng.

Quy trình xác minh:

1. Ghi lại thời điểm bắt đầu job và transaction.
2. Tìm session đọc lâu, kiểm tra trạng thái active/idle và tuổi transaction.
3. Đối chiếu thời điểm đó với xu hướng dead tuples, History List Length hoặc version store.
4. Kiểm tra tiến trình cleanup có bị giữ ở cùng một horizon hay không.
5. Xác định job có giữ cursor/transaction trong lúc upload dữ liệu hay không.
6. Thử một phiên bản job đọc theo batch, đóng transaction trước khi upload từng batch.
7. So sánh tính nhất quán của báo cáo, thời gian giữ snapshot, lượng lịch sử tồn đọng và tài nguyên.

Một thiết kế thay thế có thể đọc dữ liệu theo watermark cố định và batch theo khóa tăng dần, đồng thời ghi lại watermark để có thể tiếp tục. Nếu yêu cầu báo cáo là snapshot chính xác tại một thời điểm, cần dùng một cơ chế snapshot/reporting phù hợp thay vì âm thầm đổi sang nhiều snapshot độc lập.

Kết quả cần chứng minh bằng dữ liệu: transaction age giảm, cleanup tiến triển, tốc độ tăng version store hoặc undo giảm, latency ghi phục hồi và báo cáo vẫn đúng quy tắc nghiệp vụ. Chỉ việc job chạy xong hoặc dung lượng file không tăng thêm chưa đủ chứng minh vấn đề đã được xử lý.

## 15. Checklist theo dõi và phòng ngừa

### Trước khi phát hành ứng dụng

- Xác định transaction boundary cho báo cáo, export, cursor và job nền.
- Bảo đảm mọi đường đi thành công, lỗi và timeout đều commit hoặc rollback.
- Đóng result set/cursor khi không còn dùng.
- Kiểm tra isolation level và snapshot lifetime cần thiết.
- Đánh giá kích thước batch, watermark và cách phân trang.
- Thử workload đồng thời có cập nhật dữ liệu trong lúc đọc.

### Trong vận hành

- Theo dõi tuổi transaction và snapshot lâu nhất.
- Cảnh báo session idle-in-transaction.
- Theo dõi dead tuples, vacuum progress, History List Length, version store hoặc undo retention tùy engine.
- Theo dõi dung lượng bảng, chỉ mục, tempdb, PVS hoặc undo tablespace.
- Gắn session với service, request ID, job ID và chủ sở hữu.
- Theo dõi p95/p99, I/O, CPU, memory, temp I/O và lock waits.
- Lưu baseline để phân biệt dao động bình thường với xu hướng tích tụ.

### Sau khi xử lý

- Xác nhận transaction đã kết thúc.
- Xác nhận vacuum/purge/version cleanup tiến triển.
- Xác nhận lịch sử cũ giảm hoặc ổn định ở mức phù hợp.
- Kiểm tra dung lượng đã tái sử dụng và file allocation riêng biệt.
- Đo lại truy vấn đọc, ghi và toàn workload.
- Xác nhận không làm sai tính nhất quán hoặc bỏ sót dữ liệu trong batch/report.

## 16. Nguyên tắc cần ghi nhớ

- MVCC giữ các phiên bản cũ để snapshot đang hoạt động có thể đọc dữ liệu nhất quán.
- Giao dịch đọc kéo dài, kể cả giao dịch chỉ SELECT hoặc idle trong transaction, có thể trì hoãn thu hồi phiên bản.
- Hậu quả có thể gồm dead tuples, undo/history tăng, version store phình to, cache kém hiệu quả, I/O và độ trễ tăng.
- Tranh chấp khóa và giữ snapshot là hai cơ chế khác nhau; cần kiểm tra lock waits cùng version retention.
- PostgreSQL cần xét xmin horizon và VACUUM; InnoDB cần xét read view, undo và purge; SQL Server cần xét row versioning và đúng vùng version store; Oracle cần xét consistent read và undo retention.
- Transaction age, snapshot age, dead tuples, History List Length, version store, undo statistics và cleanup progress phải được xem theo xu hướng.
- Rút ngắn transaction, đóng cursor, tránh chờ bên ngoài transaction và chia batch có watermark là các biện pháp ứng dụng thường hữu ích.
- Chia batch có thể tạo các snapshot khác nhau; phải thiết kế tính nhất quán phù hợp nghiệp vụ.
- Tăng worker cleanup hoặc dung lượng không thể giải quyết một snapshot cũ vẫn còn hiệu lực.
- Sau khi xử lý, xác nhận cả cleanup, tài nguyên, độ trễ và tính đúng đắn của dữ liệu.

Giao dịch đọc kéo dài có thể gây tác động lớn dù không ghi dữ liệu và không trực tiếp chặn writer. Khi hiểu snapshot đang giữ phiên bản nào, quan sát đúng tiến trình dọn dẹp của hệ quản trị và rút ngắn vòng đời transaction trong ứng dụng, nhóm vận hành có thể ngăn lịch sử dữ liệu tích tụ và duy trì hiệu năng ổn định. Mọi điều chỉnh cần được kiểm chứng bằng tuổi transaction, chỉ số version/undo, cleanup progress và kết quả nghiệp vụ trước/sau.
