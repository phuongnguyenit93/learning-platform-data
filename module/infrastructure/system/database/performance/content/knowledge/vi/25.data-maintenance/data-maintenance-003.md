# VACUUM, autovacuum và ảnh hưởng của giao dịch kéo dài trong PostgreSQL

PostgreSQL dùng MVCC (Multi-Version Concurrency Control) để cho phép nhiều giao dịch đọc và ghi dữ liệu đồng thời. Khi một hàng được UPDATE hoặc DELETE, PostgreSQL thường giữ lại phiên bản hàng cũ một thời gian để các giao dịch có snapshot phù hợp vẫn nhìn thấy dữ liệu đúng. Những phiên bản không còn cần thiết được gọi là dead tuples. Nếu không được dọn dẹp, chúng làm bảng và chỉ mục phình to, tăng I/O, giảm hiệu quả cache và khiến truy vấn phải đọc nhiều trang hơn.

VACUUM là cơ chế thu hồi không gian có thể tái sử dụng và hỗ trợ quản lý vòng đời transaction ID. Autovacuum tự động kích hoạt VACUUM và ANALYZE theo ngưỡng cấu hình. Giao dịch kéo dài, snapshot cũ, replication slot hoặc standby feedback có thể ngăn VACUUM loại bỏ một số phiên bản hàng, khiến dead tuples tích tụ dù autovacuum vẫn chạy.

Trong chương **Bảo trì dữ liệu** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn cách hiểu VACUUM và autovacuum, nhận diện ảnh hưởng của giao dịch kéo dài và xử lý tình trạng vacuum không theo kịp. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng sau điều chỉnh. Vì vậy, bảo trì dữ liệu cần được đánh giá bằng số liệu dead tuples, tuổi transaction ID, temp và I/O, kế hoạch truy vấn cùng tải đồng thời.

## 1. MVCC tạo ra phiên bản hàng như thế nào?

PostgreSQL không ghi đè ngay mọi hàng khi UPDATE. Một hàng có thông tin transaction ID tạo và kết thúc phiên bản. Khi một transaction cập nhật hàng, PostgreSQL thường tạo phiên bản mới; phiên bản cũ vẫn tồn tại vật lý cho đến khi không còn snapshot nào có thể cần đọc nó.

Ví dụ, một hàng có quantity = 10 được cập nhật thành quantity = 8:

1. Transaction A đọc phiên bản cũ theo snapshot của nó.
2. Transaction B cập nhật hàng và tạo phiên bản mới có quantity = 8.
3. Transaction B commit.
4. Transaction A vẫn có thể cần nhìn thấy phiên bản quantity = 10 nếu snapshot của A bắt đầu trước thay đổi.
5. Khi mọi snapshot có thể nhìn thấy phiên bản cũ đã kết thúc, phiên bản cũ trở thành ứng viên để VACUUM thu hồi.

DELETE cũng đánh dấu phiên bản hàng là đã xóa về mặt logic. Hàng không nhất thiết biến mất ngay khỏi file dữ liệu; nó chỉ có thể được loại bỏ vật lý khi không còn transaction nào cần nhìn thấy.

Cơ chế này giúp reader và writer ít chặn nhau hơn, nhưng tạo ra công việc bảo trì. Bảng có tần suất UPDATE/DELETE cao thường sinh nhiều phiên bản cũ. Nếu VACUUM không thu hồi kịp, số trang phải đọc tăng lên dù số hàng logic đang hoạt động không đổi.

## 2. Dead tuples, bloat và không gian có thể tái sử dụng

Dead tuple là phiên bản hàng không còn cần cho bất kỳ snapshot hợp lệ nào. Bloat là phần không gian dư thừa do các phiên bản cũ, phân bố dữ liệu, cập nhật chỉ mục và các yếu tố lưu trữ khác làm bảng hoặc index lớn hơn mức cần thiết.

Cần phân biệt:

- **Dead tuples:** phiên bản hàng cũ có thể được VACUUM xử lý khi hết giới hạn snapshot.
- **Free space:** chỗ trống bên trong các trang mà PostgreSQL có thể tái sử dụng cho các lần INSERT/UPDATE sau.
- **Bloat:** phần dung lượng dư thừa làm tăng footprint và số trang cần đọc.
- **File size:** kích thước file trên filesystem, không đồng nghĩa với số byte đang chứa hàng sống.

VACUUM thông thường đánh dấu không gian đã thu hồi để PostgreSQL tái sử dụng. Nó thường không làm file bảng nhỏ lại trên filesystem. Trong một số điều kiện, VACUUM có thể truncate các trang trống ở cuối quan hệ, nhưng không nên dựa vào điều đó để thu nhỏ toàn bộ file.

Nếu cần trả lại phần lớn dung lượng cho hệ điều hành, có thể phải dùng thao tác rewrite như VACUUM FULL hoặc công cụ tái cấu trúc phù hợp. Những thao tác này có chi phí I/O, cần dung lượng tạm và có thể khóa truy cập lâu hơn.

## 3. VACUUM làm những việc gì?

VACUUM thông thường thực hiện nhiều công việc liên quan:

- Tìm và loại bỏ phiên bản hàng không còn cần thiết theo snapshot horizon.
- Đánh dấu không gian trống trong heap để tái sử dụng.
- Làm sạch các entry chỉ mục trỏ đến phiên bản hàng đã chết khi điều kiện cho phép.
- Cập nhật visibility map để hỗ trợ index-only scan.
- Freeze các transaction ID đủ cũ theo chính sách để tránh wraparound.
- Cập nhật thông tin bảo trì liên quan.

VACUUM không thay thế ANALYZE. ANALYZE thu thập thống kê phân bố dữ liệu để optimizer ước lượng cardinality và chọn kế hoạch truy vấn. VACUUM và ANALYZE có mục đích khác nhau, dù có thể chạy cùng nhau bằng tùy chọn ANALYZE.

Ví dụ:

~~~sql
VACUUM (VERBOSE, ANALYZE) public.orders;
~~~

Lệnh này thực hiện VACUUM và thu thập thống kê cho bảng. VACUUM là lệnh bảo trì cần chạy ngoài transaction block thông thường; không đặt nó trong một transaction do ứng dụng mở rồi mong nó thực thi như một câu DML bình thường.

## 4. VACUUM thông thường và VACUUM FULL

| Đặc điểm | VACUUM thông thường | VACUUM FULL |
|---|---|---|
| Mục tiêu | Thu hồi dead tuples và cho phép tái sử dụng không gian | Viết lại bảng để thu gọn file |
| Dung lượng filesystem | Thường giữ nguyên, trừ khả năng truncate phần cuối | Có thể giảm đáng kể sau khi rewrite |
| Khóa | Cho phép hoạt động đọc/ghi thông thường tiếp tục với mức khóa tương thích | Cần ACCESS EXCLUSIVE lock trên bảng |
| Dung lượng tạm | Thường thấp hơn, tùy thao tác | Cần không gian bổ sung cho bản rewrite |
| Tác động vận hành | Có thể chạy định kỳ và đồng thời với workload | Có thể chặn truy cập và tạo I/O lớn |

Không dùng VACUUM FULL như thao tác định kỳ để thay thế autovacuum. Nó có thể làm gián đoạn workload, cần đủ dung lượng đĩa cho bản viết lại và giữ khóa mạnh trong thời gian thực hiện.

Nếu bloat lớn đến mức cần rewrite, hãy chọn cửa sổ bảo trì hoặc công cụ online phù hợp, ước lượng dung lượng, kiểm tra replica lag và có kế hoạch rollback/vận hành. Các công cụ tái cấu trúc bên ngoài có yêu cầu riêng về quyền, phiên bản và khóa; phải thử trước trên môi trường tương tự.

## 5. Autovacuum hoạt động như thế nào?

Autovacuum là cơ chế nền gồm launcher và các worker. Launcher kiểm tra các database theo chu kỳ, xác định bảng cần VACUUM hoặc ANALYZE và khởi chạy worker trong giới hạn cấu hình.

Autovacuum có thể tự động:

- VACUUM bảng có đủ dead tuples hoặc đủ số hàng mới theo ngưỡng.
- ANALYZE bảng khi số thay đổi dữ liệu vượt ngưỡng thống kê.
- Freeze transaction ID cũ để bảo vệ hệ thống khỏi transaction ID wraparound.
- Xử lý các bảng riêng lẻ dựa trên thống kê và cấu hình toàn cục hoặc per-table.

Autovacuum không chạy liên tục trên mọi bảng. Nó dùng ngưỡng để tránh quét các bảng không cần thiết quá thường xuyên. Một bảng ít thay đổi có thể lâu mới được vacuum; một bảng có lượng UPDATE/DELETE lớn cần vacuum thường xuyên hơn.

Việc autovacuum chạy không bảo đảm nó có thể dọn sạch mọi dead tuple. Nếu snapshot cũ còn tồn tại, VACUUM phải giữ lại những phiên bản vẫn có thể được nhìn thấy. Nếu worker không đủ, thời gian vacuum quá dài hoặc bảng liên tục phát sinh dữ liệu nhanh hơn tốc độ dọn dẹp, lượng dead tuples vẫn có thể tăng.

## 6. Ngưỡng kích hoạt VACUUM và ANALYZE

Với UPDATE/DELETE, ngưỡng VACUUM thường được tính theo công thức khái quát:

~~~text
vacuum_threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * reltuples
~~~

Trong đó:

- autovacuum_vacuum_threshold là ngưỡng tuyệt đối.
- autovacuum_vacuum_scale_factor là tỷ lệ theo kích thước ước lượng của bảng.
- reltuples là số hàng ước lượng trong thống kê quan hệ.

Ngưỡng ANALYZE thường có dạng:

~~~text
analyze_threshold =
    autovacuum_analyze_threshold
    + autovacuum_analyze_scale_factor * reltuples
~~~

Các phiên bản PostgreSQL có thêm ngưỡng VACUUM dựa trên INSERT để bảo trì bảng chỉ có nhiều dữ liệu mới mà ít UPDATE/DELETE. Tên và hành vi tham số cần kiểm tra theo phiên bản đang chạy.

Ví dụ minh họa: một bảng 100 triệu hàng với vacuum scale factor 0,2 có thể cần khoảng 20 triệu dead tuples cộng ngưỡng tuyệt đối trước khi đạt điều kiện thông thường. Với bảng lớn, tỷ lệ mặc định có thể khiến autovacuum bắt đầu quá muộn so với mục tiêu vận hành.

Có thể đặt storage parameters riêng cho bảng có workload đặc biệt:

~~~sql
ALTER TABLE public.orders SET (
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_vacuum_threshold = 5000,
    autovacuum_analyze_scale_factor = 0.01,
    autovacuum_analyze_threshold = 2000
);
~~~

Các giá trị trên chỉ là ví dụ để minh họa cách đặt ngưỡng thấp hơn. Không sao chép trực tiếp vào production. Hãy dựa trên tốc độ thay đổi, kích thước bảng, thời gian vacuum, dung lượng I/O và mức đồng thời.

## 7. Các tham số autovacuum quan trọng

Một số tham số thường cần hiểu:

| Tham số | Vai trò |
|---|---|
| autovacuum | Bật/tắt cơ chế autovacuum thông thường |
| autovacuum_naptime | Khoảng nghỉ giữa các lần launcher kiểm tra database |
| autovacuum_max_workers | Số worker autovacuum tối đa hoạt động đồng thời |
| autovacuum_vacuum_threshold | Ngưỡng dead tuples tuyệt đối |
| autovacuum_vacuum_scale_factor | Tỷ lệ dead tuples theo kích thước bảng |
| autovacuum_analyze_threshold | Ngưỡng thay đổi dữ liệu tuyệt đối cho ANALYZE |
| autovacuum_analyze_scale_factor | Tỷ lệ thay đổi dữ liệu theo kích thước bảng |
| autovacuum_vacuum_cost_limit | Ngân sách cost cho hoạt động vacuum |
| autovacuum_vacuum_cost_delay | Thời gian trì hoãn dựa trên cost để giảm áp lực I/O |
| autovacuum_work_mem | Bộ nhớ làm việc cho vacuum worker, nếu được cấu hình riêng |

Các tham số có thể chịu ảnh hưởng bởi cấu hình toàn cục, tham số per-table và phiên bản PostgreSQL. Một bảng có thể ghi đè một số ngưỡng bằng storage parameters. Không phải mọi tham số đều được đặt ở cấp bảng.

Tăng autovacuum_max_workers có thể giúp xử lý nhiều bảng đồng thời, nhưng cũng làm tăng cạnh tranh CPU, I/O và bộ nhớ. Giảm cost delay có thể làm vacuum nhanh hơn nhưng tăng áp lực storage. Tăng cost limit có thể cho worker làm nhiều việc hơn trước khi nghỉ. Mọi điều chỉnh cần được đo dưới workload thực tế.

## 8. Vì sao autovacuum không theo kịp?

Autovacuum có thể bị tụt lại vì nhiều nguyên nhân:

- Bảng phát sinh dead tuples nhanh hơn tốc độ vacuum.
- Bảng quá lớn, mỗi lần vacuum mất nhiều thời gian.
- Nhiều bảng cùng cần vacuum nhưng số worker bị giới hạn.
- Cost delay và cost limit làm worker bị điều tiết mạnh.
- I/O storage chậm hoặc cạnh tranh với truy vấn khác.
- Long-running transaction giữ snapshot cũ, ngăn dọn một số phiên bản.
- Replication slot hoặc standby feedback giữ xmin horizon.
- DDL hoặc lock conflict làm worker phải chờ hoặc không xử lý được bảng.
- Thống kê và ngưỡng chưa phù hợp với tốc độ thay đổi của bảng.
- Index lớn làm công việc index cleanup tốn thời gian.

Đừng kết luận autovacuum hỏng chỉ vì n_dead_tup tăng. Cần xác định worker có chạy không, đang ở giai đoạn nào, có bị chặn bởi snapshot không, tốc độ phát sinh dead tuple bao nhiêu và dung lượng temp/data I/O ra sao.

## 9. Giao dịch kéo dài ảnh hưởng đến VACUUM

PostgreSQL phải giữ các phiên bản hàng mà một snapshot còn có thể nhìn thấy. Một transaction hoặc snapshot tồn tại lâu có thể đẩy lùi giới hạn dọn dẹp (cleanup horizon). VACUUM có thể quét bảng nhưng không được phép loại bỏ các tuple còn cần cho snapshot đó.

Các nguồn thường gặp:

- Transaction mở lâu ở mức isolation giữ snapshot.
- Truy vấn đọc lớn hoặc cursor giữ snapshot trong thời gian dài.
- Session ở trạng thái idle in transaction.
- Prepared transaction chưa được COMMIT hoặc ROLLBACK.
- Logical replication slot giữ xmin hoặc catalog_xmin.
- Standby bật hot_standby_feedback và gửi xmin cũ về primary.
- Một số tiến trình nội bộ giữ snapshot hoặc transaction horizon.

Một transaction chạy lâu không phải lúc nào cũng giữ cùng một snapshot theo mọi isolation level. Ví dụ, READ COMMITTED lấy snapshot mới cho từng statement; REPEATABLE READ và SERIALIZABLE giữ snapshot nhất quán lâu hơn. Vì vậy, hãy xem backend_xmin, trạng thái transaction và loại workload thay vì chỉ dựa trên thời lượng xact_start.

### 9.1. Idle in transaction

Idle in transaction là session đã bắt đầu transaction nhưng hiện không chạy câu lệnh. Ứng dụng có thể mở transaction, thực hiện SELECT, rồi chờ người dùng, gọi HTTP hoặc xử lý nghiệp vụ trước khi commit/rollback.

Nếu transaction giữ snapshot cũ, nó có thể ngăn VACUUM thu hồi dead tuples. Ngay cả khi không giữ snapshot lâu trong một số trường hợp, transaction mở lâu vẫn giữ tài nguyên, có thể giữ lock và tạo rủi ro vận hành.

Ứng dụng nên:

- Giữ transaction ngắn và chỉ bao quanh thao tác database cần tính nguyên tử.
- Không gọi HTTP hoặc chờ người dùng trong khi transaction đang mở.
- Đóng ResultSet/Statement và hoàn tất transaction đúng cách.
- Không giữ cursor hoặc snapshot lâu hơn nhu cầu.
- Dùng timeout phù hợp cho session idle in transaction.
- Kiểm tra framework/ORM có tự mở transaction bao quanh cả luồng xử lý hay không.

## 10. Xem transaction và snapshot đang giữ horizon

pg_stat_activity cung cấp trạng thái session, thời điểm bắt đầu transaction và một số thông tin về snapshot.

Ví dụ:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Các cột cần chú ý:

- xact_start: thời điểm transaction hiện tại bắt đầu.
- state: active, idle, idle in transaction hoặc trạng thái khác.
- backend_xmin: xmin mà backend đang giữ, nếu có.
- wait_event_type/wait_event: loại chờ và sự kiện chờ.
- application_name: giúp xác định dịch vụ hoặc job tạo session.

Transaction age lớn là tín hiệu điều tra, không tự chứng minh transaction đang chặn VACUUM. Hãy so sánh backend_xmin, isolation level, query, cursor và snapshot. Nếu backend_xmin rất cũ so với workload hiện tại, cần tìm nguyên nhân giữ horizon.

## 11. Prepared transaction cũng có thể giữ phiên bản cũ

Two-phase commit cho phép transaction đi qua trạng thái PREPARED trước khi được COMMIT hoặc ROLLBACK. Một prepared transaction bị bỏ quên có thể giữ tài nguyên và transaction ID lâu dài.

Kiểm tra:

~~~sql
SELECT
    gid,
    prepared,
    owner,
    database,
    transaction
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Nếu có prepared transaction tồn tại lâu, xác định transaction coordinator và trạng thái nghiệp vụ trước khi quyết định COMMIT PREPARED hoặc ROLLBACK PREPARED. Không tự động rollback chỉ vì thời gian dài; transaction có thể là một phần của quy trình phân tán cần khôi phục chính xác.

## 12. Replication slot và hot standby feedback

Replication slot giữ thông tin cần thiết để replica hoặc consumer tiếp tục nhận WAL. Một số slot có thể giữ xmin hoặc catalog_xmin, làm PostgreSQL phải giữ phiên bản hàng hoặc tuple trong system catalog lâu hơn.

Kiểm tra slot:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Nếu slot inactive lâu ngày hoặc consumer bị dừng, WAL có thể tích tụ. Với slot có xmin/catalog_xmin, dead tuples hoặc catalog tuples cũng có thể không được dọn. Cần xác định consumer, tình trạng replication và mục tiêu phục hồi trước khi xử lý.

hot_standby_feedback cho phép standby gửi thông tin xmin về primary để tránh query conflict trên replica. Đổi lại, primary có thể phải giữ các phiên bản cũ lâu hơn và tăng bloat. Tắt tính năng này có thể giảm bloat nhưng làm truy vấn trên standby bị hủy do conflict. Đây là trade-off giữa ổn định truy vấn replica và khả năng vacuum trên primary.

Không xóa replication slot hoặc thay đổi hot_standby_feedback một cách máy móc. Trước hết xác định slot còn cần hay không, consumer có thể bắt kịp không, nguy cơ mất khả năng tiếp tục replication và dung lượng WAL có thể phát sinh.

## 13. VACUUM FREEZE và transaction ID wraparound

PostgreSQL dùng transaction ID có không gian hữu hạn. Để tránh việc transaction ID cũ bị hiểu nhầm sau khi vòng số quay lại, hệ thống cần freeze các tuple đủ cũ. Tuple đã freeze không còn phụ thuộc vào transaction ID cũ theo cách thông thường để xác định khả năng hiển thị.

VACUUM thực hiện freezing theo ngưỡng. Autovacuum cũng có nhiệm vụ chống wraparound và có thể chạy vacuum khẩn cấp khi tuổi transaction ID tiến gần giới hạn bảo vệ.

Các khái niệm cần theo dõi:

- relfrozenxid của từng bảng.
- datfrozenxid của database.
- age(relfrozenxid), thể hiện tuổi tương đối của mốc freeze.
- autovacuum_freeze_max_age, ngưỡng tuổi XID kích hoạt vacuum chống wraparound.
- vacuum_freeze_min_age và vacuum_freeze_table_age, điều khiển chính sách freeze.
- Các tham số failsafe hoặc ngưỡng liên quan tùy phiên bản.

Wraparound là rủi ro nghiêm trọng hơn bloat thông thường. Nếu không freeze kịp, PostgreSQL có thể buộc phải chặn ghi để bảo vệ dữ liệu. Không tắt autovacuum để tránh tải mà không có kế hoạch vacuum/freeze thay thế.

### 13.1. Kiểm tra tuổi XID của bảng

Ví dụ:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    age(c.relfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint AS freeze_max_age
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY age(c.relfrozenxid) DESC
LIMIT 30;
~~~

Kết quả giúp xác định bảng có tuổi XID cao. Hãy xem cả tuổi XID và tiến độ vacuum, không chỉ một bảng lớn nhất. Bảng ít thay đổi cũng có thể cần vacuum freeze dù n_dead_tup thấp.

## 14. Theo dõi dead tuples và lịch sử vacuum

pg_stat_user_tables cung cấp các ước lượng và thời điểm vacuum/analyze:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 30;
~~~

Lưu ý:

- n_live_tup và n_dead_tup là ước lượng thống kê, không phải phép đếm chính xác từng tuple tại thời điểm truy vấn.
- last_autovacuum cho biết lần autovacuum gần nhất được ghi nhận.
- autovacuum_count giúp xem bảng có được xử lý hay không.
- Một lần vacuum gần đây không bảo đảm bloat đã được xử lý hoàn toàn.
- Cần so sánh xu hướng qua thời gian, không chỉ ảnh chụp một lần.

Để theo dõi bảng quan trọng, có thể ghi nhận các chỉ số theo chu kỳ và đối chiếu với tốc độ INSERT/UPDATE/DELETE. Nếu n_dead_tup tăng liên tục trong khi autovacuum_count không đổi, hãy kiểm tra ngưỡng, worker và lý do worker không xử lý.

## 15. Theo dõi tiến trình VACUUM đang chạy

PostgreSQL cung cấp pg_stat_progress_vacuum để quan sát một số giai đoạn vacuum đang hoạt động.

~~~sql
SELECT
    p.pid,
    p.relid::regclass AS relation_name,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    a.query_start,
    now() - a.query_start AS elapsed
FROM pg_stat_progress_vacuum AS p
JOIN pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY a.query_start;
~~~

Các trường cho biết tiến trình đang ở pha nào, đã quét bao nhiêu block và đã vacuum bao nhiêu block. Tên pha và trường có thể khác theo phiên bản; hãy đối chiếu tài liệu đang dùng.

Nếu vacuum kéo dài, kiểm tra kích thước bảng, index, tốc độ I/O, worker cạnh tranh và snapshot horizon. Đừng kết luận tiến trình bị treo chỉ vì một pha kéo dài; một số giai đoạn có thể cần nhiều I/O hoặc xử lý index.

## 16. Bảng lớn và cấu hình autovacuum riêng

Bảng lớn có thể cần scale factor thấp hơn mặc định để vacuum bắt đầu trước khi dead tuples tích tụ quá nhiều. Ví dụ, bảng orders nhận lượng UPDATE lớn mỗi ngày có thể cần ngưỡng riêng.

~~~sql
ALTER TABLE public.orders SET (
    autovacuum_vacuum_scale_factor = 0.01,
    autovacuum_vacuum_threshold = 10000,
    autovacuum_analyze_scale_factor = 0.005,
    autovacuum_analyze_threshold = 5000
);
~~~

Đây chỉ là giá trị minh họa. Trước khi áp dụng, hãy ước lượng số dead tuples phát sinh mỗi giờ/ngày, thời gian vacuum cần, tốc độ đọc/ghi và dung lượng I/O có thể dành cho bảo trì.

Có thể điều chỉnh fillfactor để dành chỗ cho UPDATE tại cùng page và tăng cơ hội HOT update trong workload phù hợp. Nhưng fillfactor thấp làm tăng dung lượng bảng ban đầu và không giải quyết được snapshot cũ. Hãy xem đây là một quyết định thiết kế riêng, cần benchmark.

Với bảng partitioned, theo dõi từng partition vì tốc độ thay đổi và kích thước có thể khác nhau. Autovacuum xử lý các partition có storage riêng; thống kê trên partitioned parent cần được kiểm tra và có thể cần ANALYZE thủ công sau khi dữ liệu các partition thay đổi đáng kể, tùy phiên bản và cấu trúc.

## 17. Khi nào cần chạy VACUUM thủ công?

Autovacuum nên là cơ chế bảo trì thường xuyên. VACUUM thủ công có thể phù hợp khi:

- Sau một đợt DELETE/UPDATE lớn cần thu hồi dead tuples sớm.
- Autovacuum bị tụt lại và cần xử lý một bảng quan trọng.
- Cần chạy VACUUM ANALYZE sau bulk load hoặc thay đổi dữ liệu lớn.
- Cần kiểm soát thời điểm bảo trì trong cửa sổ vận hành.
- Cần freeze chủ động theo kế hoạch chống wraparound.

Ví dụ:

~~~sql
VACUUM (VERBOSE, ANALYZE) public.orders;
~~~

VACUUM thủ công cũng chịu giới hạn snapshot horizon. Nếu transaction cũ vẫn giữ tuple, chạy lặp lại VACUUM không thể dọn phần dữ liệu đó. Hãy tìm blocker trước khi lặp lệnh hoặc tăng tài nguyên.

VACUUM không thể chạy trong transaction block thông thường. Khi chạy từ migration framework hoặc client, bảo đảm công cụ không tự bọc lệnh trong transaction.

## 18. Cách xử lý giao dịch kéo dài an toàn

Khi phát hiện transaction giữ xmin cũ:

1. Xác định PID, application_name, user, database, query và xact_start.
2. Xem state và backend_xmin để biết session còn giữ snapshot hay không.
3. Xác định dịch vụ hoặc job sở hữu session.
4. Kiểm tra transaction có giữ lock hoặc đang chờ tài nguyên không.
5. Trao đổi với chủ sở hữu ứng dụng về khả năng hoàn tất, rollback hoặc dừng job.
6. Nếu cần hủy, đánh giá tác động dữ liệu và quy trình retry trước.
7. Sau khi transaction kết thúc, quan sát vacuum có tiến triển và dead tuples giảm không.

pg_cancel_backend(pid) yêu cầu hủy câu lệnh đang chạy nhưng không nhất thiết kết thúc transaction. Session có thể trở thành idle in transaction và tiếp tục giữ tài nguyên. pg_terminate_backend(pid) kết thúc session và làm transaction chưa commit bị rollback, nhưng có thể ảnh hưởng request hoặc job đang thực hiện.

Không tự động terminate mọi session lâu năm. Một transaction có thể là batch hợp lệ, một giao dịch phân tán hoặc một thao tác quản trị quan trọng. Phải xác định chủ sở hữu và tác động trước khi can thiệp.

## 19. Cấu hình timeout để ngăn idle transaction kéo dài

PostgreSQL có tham số idle_in_transaction_session_timeout để chấm dứt session ở trạng thái idle in transaction quá thời gian cấu hình. Đây là hàng rào hữu ích cho ứng dụng thường quên commit/rollback.

Ví dụ cấu hình ở cấp role hoặc database có thể phù hợp hơn đặt toàn server, tùy mức độ tương thích của ứng dụng:

~~~sql
ALTER ROLE app_user
SET idle_in_transaction_session_timeout = '2min';
~~~

Giá trị minh họa cần được điều chỉnh theo workload. Một số quy trình hợp lệ có thể cần transaction chờ lâu; timeout quá thấp sẽ làm chúng bị ngắt và phát sinh retry.

statement_timeout giới hạn thời gian chạy statement, nhưng không thay thế idle_in_transaction_session_timeout. lock_timeout giới hạn thời gian chờ khóa. Ba timeout giải quyết các tình huống khác nhau.

Sau khi đặt timeout, kiểm tra log, lỗi ứng dụng và tỷ lệ rollback. Ứng dụng phải xử lý SQLSTATE tương ứng, đóng transaction và trả connection về pool ở trạng thái sạch.

## 20. Các nguyên nhân giữ horizon ngoài transaction ứng dụng

Nếu không tìm thấy session lâu năm rõ ràng trong pg_stat_activity, hãy kiểm tra thêm:

- Replication slot inactive hoặc consumer bị dừng.
- Logical replication giữ xmin/catalog_xmin.
- Standby bật hot_standby_feedback và replica bị lag.
- Prepared transaction chưa được quyết định.
- Backup hoặc công cụ quản trị giữ snapshot lâu.
- Extension hoặc tác vụ nội bộ có hành vi giữ snapshot.

Replication slot:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots;
~~~

Prepared transaction:

~~~sql
SELECT gid, prepared, owner, database, transaction
FROM pg_prepared_xacts;
~~~

Nếu một slot không còn được dùng, việc xóa slot có thể giải phóng WAL retention và horizon, nhưng có thể làm consumer không thể tiếp tục từ vị trí cũ. Xác nhận consumer đã dừng vĩnh viễn hoặc có kế hoạch tạo lại trước khi drop.

Nếu standby feedback đang giữ xmin, cân nhắc thời gian query replica, lag và nhu cầu tránh query cancellation. Thay đổi cấu hình cần đánh giá tác động lên cả primary lẫn standby.

## 21. Bảng hệ thống và công cụ quan sát quan trọng

| Nguồn | Mục đích |
|---|---|
| pg_stat_activity | Transaction, snapshot, trạng thái session, wait event |
| pg_stat_user_tables | Ước lượng live/dead tuples và lịch sử vacuum/analyze |
| pg_stat_progress_vacuum | Tiến độ VACUUM đang chạy |
| pg_class.relfrozenxid | Mốc freeze của quan hệ |
| pg_database.datfrozenxid | Mốc freeze của database |
| pg_replication_slots | Slot, xmin, catalog_xmin và restart_lsn |
| pg_prepared_xacts | Transaction đã PREPARE chưa được kết thúc |
| pg_stat_database | Thống kê hoạt động ở cấp database |
| Log autovacuum | Thời gian, số trang, dead tuples và chi tiết vacuum nếu bật log phù hợp |

Các view thống kê có thể reset hoặc thay đổi hành vi giữa phiên bản. Cần ghi lại thời điểm reset, cấu hình logging và phiên bản PostgreSQL để so sánh đúng.

## 22. Quy trình điều tra khi bảng phình to

Một quy trình thực tế:

1. **Xác định bảng bị ảnh hưởng:** xem kích thước, tốc độ tăng và query fingerprint chậm.
2. **Xem thống kê dead tuples:** kiểm tra n_dead_tup, last_autovacuum và autovacuum_count.
3. **Xác định VACUUM có chạy không:** xem pg_stat_progress_vacuum, log và worker.
4. **Tìm snapshot cũ:** kiểm tra xact_start, backend_xmin, idle in transaction và prepared transaction.
5. **Kiểm tra replication horizon:** xem xmin/catalog_xmin trong replication slots và standby feedback.
6. **Kiểm tra XID age:** xem age(relfrozenxid), age(datfrozenxid) và ngưỡng chống wraparound.
7. **Đánh giá tốc độ phát sinh:** so sánh UPDATE/DELETE với tốc độ vacuum xử lý.
8. **Đánh giá I/O và worker:** xem cost delay, worker saturation, storage latency và index cleanup.
9. **Đưa ra thay đổi nhỏ:** xử lý transaction giữ horizon, điều chỉnh per-table threshold hoặc worker/cost khi có số liệu.
10. **Chạy vacuum/analyze khi phù hợp:** không lặp lệnh nếu snapshot cũ vẫn chặn.
11. **Đo lại:** dead tuples, tuổi XID, table/index size, I/O và p95/p99.
12. **Theo dõi chu kỳ tiếp theo:** xác nhận autovacuum giữ được tốc độ ổn định sau khi dữ liệu tiếp tục thay đổi.

## 23. Các sai lầm thường gặp

- **Cho rằng VACUUM luôn thu nhỏ file trên filesystem.** VACUUM thông thường chủ yếu cho phép tái sử dụng không gian bên trong quan hệ.
- **Dùng VACUUM FULL như tác vụ định kỳ.** Nó rewrite bảng và cần khóa mạnh, dung lượng bổ sung.
- **Tăng worker mà không xem I/O.** Nhiều worker có thể làm storage quá tải.
- **Giảm scale factor cho mọi bảng.** Bảng nhỏ, bảng lớn và tốc độ cập nhật khác nhau cần ngưỡng khác nhau.
- **Chỉ nhìn n_dead_tup.** Đây là ước lượng và không phản ánh đầy đủ bloat hoặc horizon.
- **Lặp VACUUM khi snapshot cũ vẫn tồn tại.** VACUUM không thể loại tuple còn cần cho snapshot.
- **Nhầm READ COMMITTED với REPEATABLE READ.** Thời gian transaction và thời gian giữ snapshot không luôn giống nhau.
- **Bỏ qua replication slot.** Slot inactive có thể giữ WAL và xmin lâu dài.
- **Terminate session mà không xác định chủ sở hữu.** Có thể rollback công việc hợp lệ và gây lỗi ứng dụng.
- **Tắt autovacuum để giảm I/O.** Có thể khiến bloat và rủi ro wraparound tăng nhanh.
- **Bỏ qua freeze khi dead tuples thấp.** VACUUM freeze còn phục vụ an toàn transaction ID.
- **Chỉ đo sau một lần vacuum.** Cần theo dõi nhiều chu kỳ và tốc độ phát sinh dữ liệu.

## 24. Checklist vận hành VACUUM và autovacuum

- [ ] Đã hiểu bảng có tần suất INSERT/UPDATE/DELETE như thế nào.
- [ ] Đã phân biệt dead tuples, free space, bloat và file size.
- [ ] Đã kiểm tra last_autovacuum, autovacuum_count và n_dead_tup.
- [ ] Đã xác nhận worker có chạy và có bị quá tải không.
- [ ] Đã kiểm tra ngưỡng vacuum/analyze toàn cục và per-table.
- [ ] Đã đo vacuum duration, I/O, cost delay và index cleanup.
- [ ] Đã kiểm tra transaction age cùng backend_xmin.
- [ ] Đã rà soát idle in transaction và prepared transactions.
- [ ] Đã kiểm tra replication slot xmin/catalog_xmin và standby feedback.
- [ ] Đã theo dõi age(relfrozenxid) và datfrozenxid để phòng wraparound.
- [ ] Đã đánh giá tác động trước khi cancel/terminate session.
- [ ] Đã chọn timeout phù hợp với ứng dụng.
- [ ] Đã chạy VACUUM/ANALYZE đúng thời điểm và ngoài transaction block.
- [ ] Đã kiểm tra bảng partitioned và thống kê của parent/child.
- [ ] Đã đo lại dead tuples, table/index size, I/O và p95/p99 qua nhiều chu kỳ.

## 25. Nguyên tắc cần ghi nhớ

VACUUM duy trì khả năng tái sử dụng không gian và freeze transaction ID; autovacuum tự động thực hiện công việc theo ngưỡng và giới hạn tài nguyên. Dead tuples tích tụ có thể làm tăng số trang đọc và bloat, nhưng VACUUM chỉ được loại bỏ những phiên bản hàng mà không còn snapshot hợp lệ nào cần nhìn thấy.

Giao dịch kéo dài, idle in transaction, prepared transaction, replication slot và hot standby feedback có thể giữ cleanup horizon cũ. Khi vacuum không theo kịp, hãy kiểm tra backend_xmin, tuổi transaction, slot, tiến độ worker và tốc độ phát sinh dữ liệu trước khi tăng tài nguyên hoặc chạy VACUUM FULL. Điều chỉnh ngưỡng per-table, worker và cost dựa trên đo đạc; theo dõi cả bloat, XID age, I/O và p95/p99. Mục tiêu là duy trì bảo trì đều đặn, tránh wraparound và giữ hiệu năng ổn định trong suốt vòng đời dữ liệu.
