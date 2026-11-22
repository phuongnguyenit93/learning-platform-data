# Hoàn thiện dashboard, cảnh báo và runbook cho môi trường thực hành PostgreSQL

Một môi trường thực hành PostgreSQL chỉ thật sự hữu ích khi người học có thể quan sát hệ thống, nhận biết dấu hiệu bất thường và xử lý sự cố theo một quy trình có thể lặp lại. Dashboard cho biết điều gì đang diễn ra; cảnh báo thông báo khi một chỉ số cần được chú ý; runbook hướng dẫn cách xác minh nguyên nhân và khôi phục dịch vụ.

Ba thành phần này phải dùng chung định nghĩa chỉ số và cùng phản ánh một mô hình vận hành. Ví dụ, nếu dashboard hiển thị số kết nối đang hoạt động nhưng cảnh báo lại tính cả session idle, người vận hành có thể nhận thông báo quá sớm. Nếu cảnh báo báo filesystem gần đầy nhưng runbook không chỉ ra volume nào chứa WAL, người học sẽ khó tìm đúng nơi xử lý.

Bài thực hành này xây dựng quy trình quan sát và ứng phó cho một PostgreSQL instance chạy trong môi trường lab. Có thể áp dụng với PostgreSQL cài trực tiếp, Docker Compose hoặc máy ảo; tên metric và cách triển khai exporter cần được xác minh theo phiên bản công cụ đang dùng.

## 1. Mục tiêu và phạm vi của môi trường thực hành

Một lab hoàn chỉnh nên giúp người học trả lời được các câu hỏi:

- PostgreSQL có đang hoạt động và nhận kết nối không?
- Tải đọc/ghi, số giao dịch và số kết nối thay đổi như thế nào?
- Truy vấn nào đang chạy lâu, chờ khóa hoặc tiêu thụ nhiều tài nguyên?
- RAM, CPU, I/O và dung lượng filesystem còn đủ không?
- WAL, checkpoint, backup và replication có đang vận hành bình thường không?
- Khi có sự cố, cần kiểm tra bằng chứng nào, thực hiện thao tác nào và xác nhận phục hồi ra sao?

Phạm vi cơ bản gồm một PostgreSQL primary, một ứng dụng tạo tải, một bộ thu thập metrics, một dashboard và một nơi lưu trữ cảnh báo. Nếu lab có standby, hãy bổ sung chỉ số replication và runbook failover riêng. Không đưa thao tác failover vào runbook chung nếu lab không có cơ chế quản lý vai trò primary/standby.

Có thể đặt mục tiêu theo ba mức:

| Mức | Kết quả cần đạt |
|---|---|
| Cơ bản | Có health check, kết nối, CPU, RAM, dung lượng và cảnh báo database ngừng hoạt động |
| Trung cấp | Có transaction rate, latency, wait event, deadlock, WAL, backup và runbook theo tình huống |
| Nâng cao | Có replication lag, dự báo dung lượng, kiểm thử cảnh báo, kiểm soát nhiễu và diễn tập khôi phục |

Không cần triển khai tất cả công cụ trong một lần. Hãy bắt đầu bằng các chỉ số có hành động xử lý rõ ràng, sau đó mở rộng khi người học hiểu cách dữ liệu được thu thập và diễn giải.

## 2. Kiến trúc quan sát tham khảo

Một kiến trúc phổ biến dùng PostgreSQL Exporter, Prometheus và Grafana:

~~~mermaid
flowchart LR
    APP["Ứng dụng / pgbench"] --> PG["PostgreSQL"]
    PG --> EXP["postgres_exporter"]
    EXP --> PROM["Prometheus"]
    NODE["node_exporter"] --> PROM
    PROM --> GRAF["Grafana Dashboard"]
    PROM --> RULE["Alert Rules"]
    RULE --> AM["Alertmanager / Grafana Alerting"]
    AM --> DEST["Kênh thông báo lab"]
    GRAF --> OP["Người học / người vận hành"]
    OP --> RUN["Runbook"]
    RUN --> PG
~~~

Vai trò của từng thành phần:

- PostgreSQL lưu dữ liệu và cung cấp các view thống kê như pg_stat_activity, pg_stat_database, pg_stat_replication và pg_stat_wal.
- postgres_exporter đọc các thống kê được phép truy cập và chuyển thành metrics để Prometheus thu thập.
- node_exporter cung cấp số liệu hệ điều hành như CPU, RAM, filesystem và I/O trên Linux.
- Prometheus lưu chuỗi thời gian và đánh giá rule định kỳ.
- Grafana hiển thị dashboard và có thể quản lý alert rule, contact point và notification policy.
- Alertmanager hoặc cơ chế cảnh báo của Grafana nhóm, định tuyến và gửi thông báo.
- Runbook ghi rõ cách xác minh, xử lý, rollback và xác nhận phục hồi.

Có thể thay exporter bằng bộ giám sát của nhà cung cấp cloud hoặc hệ thống metrics hiện có. Điều quan trọng là phải biết chỉ số đến từ đâu, được lấy mẫu bao lâu một lần, có reset hay không và có độ trễ bao nhiêu.

### 2.1. Chọn khoảng thời gian thu thập

Với lab, khoảng scrape 15–30 giây thường đủ để quan sát các thay đổi thông thường. Khoảng ngắn hơn làm tăng số mẫu, tải truy vấn metrics và dung lượng lưu trữ; khoảng dài hơn có thể bỏ lỡ sự cố ngắn. Chọn khoảng phù hợp với mục tiêu học và tài nguyên máy.

Nên ghi rõ:

- Scrape interval của Prometheus.
- Thời gian lưu metrics (retention).
- Thời gian lưu log PostgreSQL.
- Khoảng lấy mẫu của dashboard SQL nếu dùng truy vấn trực tiếp.
- Múi giờ hiển thị và cách quy đổi thời gian.

Không nên đặt scrape interval quá ngắn rồi giả định hệ thống có độ chính xác tương ứng. Một số thống kê PostgreSQL là bộ đếm tích lũy; để tính tốc độ cần lấy chênh lệch giữa các lần thu thập.

## 3. Chuẩn bị quyền giám sát PostgreSQL

Tài khoản exporter hoặc dashboard chỉ cần quyền đọc thống kê. Không dùng tài khoản superuser của ứng dụng để thu thập metrics.

Có thể tạo role giám sát riêng:

~~~sql
CREATE ROLE monitoring LOGIN;
GRANT pg_monitor TO monitoring;
~~~

Role hệ thống pg_monitor cung cấp quyền đọc nhiều view và hàm giám sát. Phạm vi quyền cụ thể phụ thuộc phiên bản PostgreSQL; hãy xem tài liệu phiên bản đang triển khai và chỉ cấp thêm quyền khi có lý do.

Nếu exporter cần xác thực password, đặt password bằng công cụ quản trị an toàn và lưu trong secret store hoặc file được bảo vệ. Không đưa password vào Git, dashboard JSON, URL, ví dụ bài học hoặc log.

Các nguyên tắc:

- Chỉ cho phép tài khoản giám sát kết nối từ máy exporter hoặc subnet monitoring.
- Dùng TLS khi kết nối đi qua mạng không tin cậy.
- Giới hạn quyền đọc dữ liệu nghiệp vụ; dashboard không nên cần SELECT trên mọi bảng ứng dụng nếu chỉ đọc thống kê hệ thống.
- Dùng secret riêng cho từng môi trường.
- Xoay vòng thông tin xác thực theo quy trình và xác minh exporter sau khi thay đổi.
- Không cấp quyền ghi, CREATE hoặc SUPERUSER cho tài khoản giám sát.

Kiểm tra quyền và phiên đăng nhập:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper
FROM pg_roles
WHERE rolname = 'monitoring';
~~~

Nếu exporter không đọc được một view, kiểm tra log exporter và quyền trên view đó. Không giải quyết bằng cách cấp SUPERUSER ngay lập tức.

## 4. Chọn các chỉ số cần theo dõi

Một dashboard tốt tập trung vào các chỉ số dẫn đến quyết định vận hành. Không nên đưa mọi metric có sẵn lên cùng một màn hình.

### 4.1. Nhóm health và availability

| Chỉ số | Ý nghĩa | Câu hỏi vận hành |
|---|---|---|
| Exporter scrape success | Prometheus có thu thập được exporter không | Mất metrics hay database thực sự ngừng hoạt động? |
| PostgreSQL up/readiness | Instance có nhận kết nối không | Có cần kiểm tra service và log khởi động? |
| Connection success | Client thử đăng nhập có thành công không | Lỗi nằm ở DNS, mạng, TLS hay xác thực? |
| Restart/start time | Thời điểm instance khởi động gần nhất | Có restart ngoài kế hoạch không? |
| Last successful backup | Lần backup thành công gần nhất | Có thể phục hồi trong RPO yêu cầu không? |

Không đồng nhất exporter không scrape được với PostgreSQL đã down. Exporter có thể bị dừng, mất mạng, hết quyền hoặc lỗi secret trong khi database vẫn phục vụ ứng dụng. Nên theo dõi cả trạng thái endpoint database và trạng thái collector.

### 4.2. Nhóm workload và kết nối

- Số backend theo state: active, idle, idle in transaction và các trạng thái khác.
- Transaction commit và rollback mỗi giây.
- Số query đang chạy và thời gian chạy lâu.
- Tỷ lệ block hit/read và lượng dữ liệu tạm.
- Số deadlock.
- Số kết nối so với max_connections.
- Wait event theo loại và tên sự kiện.

Số connection tổng không đồng nghĩa số truy vấn đang chạy. Một pool có thể giữ nhiều session idle để tái sử dụng; cần hiển thị active, idle và idle in transaction riêng.

### 4.3. Nhóm tài nguyên máy chủ và storage

- CPU utilization và CPU steal trên máy ảo.
- RAM khả dụng, swap và dấu hiệu OOM.
- Filesystem available bytes và phần trăm đã dùng.
- IOPS đọc/ghi, throughput, latency và queue depth.
- Network throughput và lỗi kết nối.
- Dung lượng thư mục dữ liệu, WAL, log và nơi lưu backup.

Filesystem gần đầy thường là rủi ro cấp bách hơn một tỷ lệ CPU cao ngắn hạn. Đặc biệt cần giám sát riêng filesystem chứa PGDATA và WAL nếu chúng nằm trên các volume khác nhau.

### 4.4. Nhóm PostgreSQL maintenance và reliability

- WAL bytes phát sinh theo thời gian.
- Số lần archive thành công/thất bại và thời điểm archive gần nhất.
- Checkpoint và thời gian ghi checkpoint.
- Replication state, write/flush/replay lag nếu có standby.
- Autovacuum và vacuum tiến triển.
- Backup duration, backup age và kết quả kiểm tra restore.
- Query statistics từ pg_stat_statements.

Các chỉ số này giúp phát hiện vấn đề trước khi người dùng gặp lỗi, nhưng phải gắn với hành động cụ thể. Ví dụ, replication lag cần được diễn giải theo vai trò standby và yêu cầu RPO; một standby dùng cho báo cáo có thể chấp nhận độ trễ khác standby phục vụ failover.

## 5. Thu thập số liệu trực tiếp từ PostgreSQL

Có thể dùng SQL để kiểm tra trước khi đưa dữ liệu lên dashboard. Các truy vấn dưới đây chạy trên schema thống kê chuẩn của PostgreSQL; quyền truy cập có thể khác theo role và phiên bản.

### 5.1. Số session theo trạng thái và wait event

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    COUNT(*) AS session_count
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event
ORDER BY session_count DESC;
~~~

Truy vấn này cho thấy số session theo database, user, ứng dụng, trạng thái và loại chờ. Nếu nhiều session ở idle in transaction, hãy kiểm tra ứng dụng có mở transaction rồi giữ quá lâu hay không. Không kết luận chỉ dựa trên số lượng; cần xem tuổi transaction và tác động đến vacuum, khóa và tài nguyên.

### 5.2. Truy vấn đang chạy lâu

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    LEFT(query, 300) AS query_preview
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start IS NOT NULL
  AND pid <> pg_backend_pid()
ORDER BY query_start;
~~~

query_start là thời điểm bắt đầu truy vấn hiện tại. Một truy vấn chạy lâu có thể là báo cáo hợp lệ; hãy đối chiếu với thời gian chạy thông thường, wait event, kế hoạch và tác động đến người dùng. Cẩn thận với nội dung query có thể chứa dữ liệu nhạy cảm.

### 5.3. Transaction và block statistics

~~~sql
SELECT
    datname,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    tup_returned,
    tup_fetched,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY datname;
~~~

Các trường bộ đếm thường tăng dần kể từ lần reset thống kê. Không vẽ trực tiếp xact_commit như một tốc độ. Hãy tính rate từ chênh lệch hai lần lấy mẫu hoặc dùng Prometheus counter và hàm rate. Nếu stats_reset thay đổi, cần bắt đầu một khoảng đo mới.

Tỷ lệ hit tham khảo:

~~~sql
SELECT
    datname,
    ROUND(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_percent
FROM pg_stat_database
WHERE datname IS NOT NULL;
~~~

Đây là tỷ lệ block được tìm thấy trong shared_buffers so với tổng block được yêu cầu đọc và hit. Nó không phải tỷ lệ cache của toàn bộ hệ điều hành và không chứng minh rằng mọi lần blks_read đều truy cập thiết bị vật lý. Cần xem thêm storage metrics và latency truy vấn.

### 5.4. Dung lượng database và bảng

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;
~~~

Các bảng lớn trong schema người dùng:

~~~sql
SELECT
    schemaname,
    relname,
    pg_size_pretty(pg_total_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS total_size,
    pg_size_pretty(pg_relation_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS table_size,
    pg_size_pretty(pg_indexes_size(
        format('%I.%I', schemaname, relname)::regclass
    )) AS indexes_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, relname)::regclass
) DESC
LIMIT 20;
~~~

pg_database_size và pg_total_relation_size cho biết dung lượng đối tượng PostgreSQL. Chúng không thay thế số liệu filesystem: volume còn chứa WAL, log, file tạm, metadata filesystem và có thể cả dữ liệu khác.

### 5.5. Theo dõi WAL và archiver

~~~sql
SELECT
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_generated,
    wal_buffers_full,
    wal_write,
    wal_sync,
    wal_write_time,
    wal_sync_time
FROM pg_stat_wal;
~~~

pg_stat_wal có trên các phiên bản PostgreSQL hỗ trợ view này. Các bộ đếm là số liệu tích lũy; cần lấy chênh lệch để tính tốc độ phát sinh WAL. Các cột thời gian phụ thuộc cấu hình track_wal_io_timing ở phiên bản tương ứng.

Trạng thái archiver:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

failed_count tăng là dấu hiệu cần điều tra. Một lần archive thất bại không nhất thiết làm database ngừng hoạt động ngay, nhưng lỗi kéo dài có thể khiến WAL tích tụ và tiêu thụ hết dung lượng.

### 5.6. Theo dõi replication nếu lab có standby

Trên primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    write_lag,
    flush_lag,
    replay_lag,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes
FROM pg_stat_replication;
~~~

View này hiển thị các standby đang kết nối trực tiếp đến primary. Nếu không có dòng, có thể lab không có standby, standby chưa kết nối hoặc đang gặp sự cố. Không áp dụng cảnh báo replication cho lab single-node.

write_lag, flush_lag và replay_lag là thời gian trễ quan sát được trong một số điều kiện; khi primary ít hoặc không phát sinh ghi, giá trị có thể NULL. replay_lag_bytes so sánh vị trí WAL hiện tại với replay_lsn và hữu ích để xem lượng WAL chưa replay, nhưng cần diễn giải theo tốc độ ghi và trạng thái kết nối.

### 5.7. Theo dõi thống kê câu SQL

Nếu pg_stat_statements đã được cài và bật:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    LEFT(query, 250) AS query_preview
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

View này giúp tìm các mẫu truy vấn tiêu thụ tổng thời gian lớn, thời gian trung bình cao hoặc ghi nhiều dữ liệu tạm. Các cột và kiểu dữ liệu có thể khác theo phiên bản; kiểm tra schema view trước khi đưa truy vấn vào dashboard.

Không hiển thị query text đầy đủ cho mọi người xem nếu câu SQL có thể chứa literal nhạy cảm. Dashboard vận hành thường chỉ cần queryid, tổng thời gian, số lần gọi và phần preview đã được kiểm soát.

## 6. Xây dựng dashboard trong Grafana

Nên tạo một dashboard tổng quan và một số dashboard chi tiết theo chủ đề. Người học mở dashboard tổng quan trước, sau đó chuyển đến trang phù hợp khi cần tìm nguyên nhân.

### 6.1. Dashboard tổng quan PostgreSQL

Các hàng panel đề xuất:

| Hàng | Panel | Cách hiển thị |
|---|---|---|
| Trạng thái | PostgreSQL up, exporter up, thời điểm khởi động | Stat / status |
| Workload | Transactions/s, active sessions, connections | Time series |
| Query | Query chạy lâu, wait event, deadlocks | Table / time series |
| Tài nguyên | CPU, RAM, swap, I/O latency | Time series |
| Dung lượng | Filesystem used %, database size, WAL size | Gauge / time series |
| Reliability | Backup age, archive failures, replication lag | Stat / time series |
| Cảnh báo | Alert đang firing và lịch sử gần đây | Alert list |

Trên mỗi panel nên có:

- Tên chỉ số rõ nghĩa, đơn vị và nguồn dữ liệu.
- Khoảng thời gian mặc định phù hợp, ví dụ 1 giờ hoặc 6 giờ.
- Trục thời gian cùng múi giờ đã thống nhất.
- Legend có instance, database hoặc application khi cần phân biệt.
- Ngưỡng tham chiếu có giải thích, không chỉ dùng màu.
- Link hoặc ghi chú dẫn đến runbook liên quan.

Tránh đặt quá nhiều panel nhỏ trên một màn hình. Một panel chỉ hữu ích khi người học biết nó đo gì và cần làm gì khi giá trị thay đổi.

### 6.2. Dashboard workload và truy vấn

Có thể chia thành:

- Transaction rate: commit/s và rollback/s.
- Connections: active, idle, idle in transaction và tổng backend.
- Query duration: truy vấn active lâu nhất và top query từ pg_stat_statements.
- Wait events: số backend chờ theo wait_event_type.
- Temporary files: temp_files và temp_bytes theo tốc độ tăng.
- Deadlocks: số phát sinh theo thời gian.
- Cache behavior: blks_hit và blks_read theo rate, kèm ghi chú giới hạn diễn giải.

### 6.3. Dashboard capacity và storage

Hiển thị:

- Filesystem sử dụng theo mountpoint.
- Dung lượng còn trống theo GB.
- Tốc độ tăng database theo ngày/tuần.
- WAL phát sinh theo phút hoặc giờ.
- WAL archive failure.
- Dung lượng backup và thời gian lưu nếu có.
- IOPS, throughput, latency và queue depth của volume.

Dung lượng database và filesystem là hai chỉ số khác nhau. Ví dụ database có thể tăng chậm nhưng filesystem vẫn đầy do WAL được giữ lại bởi replication slot, log, file tạm hoặc backup cục bộ.

### 6.4. Dashboard replication và backup

Nếu lab có standby, hiển thị:

- Standby đang kết nối hay không.
- sync_state và application_name.
- Replay lag bytes và thời gian replay.
- WAL sender/receiver state nếu thu thập được.
- Thời điểm backup thành công gần nhất.
- Thời lượng backup và kích thước bản backup.
- Kết quả kiểm tra restore gần nhất.

Backup thành công không đồng nghĩa restore thành công. Nên có một bài thực hành phục hồi vào database hoặc instance riêng để xác minh bản backup có thể dùng được.

## 7. Kết nối Prometheus và exporter

Nếu dùng postgres_exporter, hãy cố định phiên bản exporter trong môi trường lab và đọc tài liệu đúng phiên bản. Bộ metric mặc định, tên metric và custom query có thể thay đổi theo release hoặc cấu hình.

Ví dụ cấu hình scrape cơ bản:

~~~yaml
scrape_configs:
  - job_name: postgres
    scrape_interval: 15s
    static_configs:
      - targets:
          - postgres-exporter:9187

  - job_name: node
    scrape_interval: 15s
    static_configs:
      - targets:
          - node-exporter:9100
~~~

Đoạn trên chỉ là phần cấu hình Prometheus. Các service exporter cần được tạo trong Docker Compose hoặc môi trường tương ứng, có network route tới PostgreSQL và credentials an toàn.

Sau khi khởi động:

1. Mở trang Prometheus Targets.
2. Xác nhận target postgres và node ở trạng thái UP.
3. Truy vấn một metric cơ bản để xác nhận dữ liệu có được ingest.
4. Mở endpoint /metrics của exporter trong mạng quản trị và tìm metric PostgreSQL.
5. Đối chiếu tên metric với phiên bản exporter đang chạy.
6. Kiểm tra log exporter nếu target UP nhưng metric database bị thiếu.

Một target UP chỉ chứng minh Prometheus scrape endpoint thành công. Nó chưa chắc chứng minh exporter đăng nhập được PostgreSQL hoặc custom query hoạt động. Hãy kiểm tra cả metric health của database và log exporter.

### 7.1. Ví dụ PromQL

Một số metric node_exporter phổ biến:

CPU busy percentage (xấp xỉ, loại bỏ idle và iowait theo mục tiêu dashboard):

~~~promql
100 * (1 - avg by (instance) (
  rate(node_cpu_seconds_total{mode="idle"}[5m])
))
~~~

Filesystem used percentage:

~~~promql
100 * (
  1 -
  node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"}
  /
  node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"}
)
~~~

Lọc thêm mountpoint để chỉ theo dõi volume chứa dữ liệu PostgreSQL. Không áp dụng ngưỡng cho mọi filesystem như tmpfs, overlay hoặc volume tạm nếu chúng không thuộc phạm vi vận hành.

Với postgres_exporter, tên metric tùy phiên bản và mapping. Ví dụ các bản exporter thường cung cấp metric trạng thái PostgreSQL như pg_up và metric từ pg_stat_database. Trước khi dùng truy vấn PromQL trong dashboard hoặc alert rule, hãy mở /metrics và xác minh metric thực tế có tồn tại, đúng label và đúng loại counter/gauge.

Ví dụ nếu metric pg_up có trong phiên bản exporter đang chạy:

~~~promql
pg_up == 0
~~~

Nếu exporter dùng tên metric khác, hãy thay bằng metric trạng thái tương ứng. Đừng copy truy vấn từ dashboard của phiên bản exporter khác mà không xác minh.

### 7.2. Phân biệt counter, gauge và histogram

- Counter chỉ tăng cho đến khi process hoặc thống kê reset. Dùng rate hoặc increase để tính tốc độ/thay đổi.
- Gauge có thể tăng hoặc giảm, ví dụ số kết nối hiện tại hay dung lượng trống.
- Histogram lưu phân phối theo bucket, thường dùng để tính phân vị latency bằng histogram_quantile nếu exporter cung cấp đúng bucket.

Ví dụ, dùng rate trên counter transaction để tính commit mỗi giây; không dùng rate trên số connection hiện tại. Dùng trực tiếp gauge filesystem available để biểu diễn dung lượng trống.

Khi counter reset, Prometheus rate xử lý một số trường hợp reset trong khoảng đo. Tuy vậy, cần kiểm tra restart exporter, reset stats PostgreSQL và nhãn instance để tránh ghép dữ liệu của hai nguồn khác nhau.

## 8. Thiết kế cảnh báo có thể hành động

Một alert rule tốt cần trả lời bốn câu hỏi:

1. Điều kiện nào được xem là bất thường?
2. Bất thường phải kéo dài bao lâu mới phát cảnh báo?
3. Người nhận cần kiểm tra gì?
4. Mức độ nào cần hành động ngay?

Không đặt cảnh báo chỉ vì một metric vượt ngưỡng trong một lần scrape. Dùng khoảng duy trì (for duration), ngưỡng theo tải thực tế và điều kiện loại trừ để tránh cảnh báo chập chờn.

### 8.1. Phân loại severity

| Mức | Ý nghĩa | Ví dụ |
|---|---|---|
| Info | Thông tin để học hoặc theo dõi | Backup hoàn tất, checkpoint bất thường nhưng đã phục hồi |
| Warning | Cần điều tra trong thời gian gần | Filesystem vượt ngưỡng, connections tăng nhanh |
| Critical | Ảnh hưởng dịch vụ hoặc nguy cơ mất khả năng vận hành | PostgreSQL down, volume gần đầy, backup vượt RPO |
| Resolved | Điều kiện đã hết | Target trở lại UP, dung lượng xuống dưới ngưỡng hồi phục |

Môi trường lab có thể gửi cảnh báo lên một contact point thử nghiệm hoặc hiển thị trong Grafana. Không gửi thông báo đến nhóm production khi đang thực hành.

### 8.2. Cảnh báo database không phản hồi

Điều kiện ví dụ: metric trạng thái database báo down liên tục 1 phút.

~~~yaml
groups:
  - name: postgres-availability
    rules:
      - alert: PostgreSQLUnavailable
        expr: pg_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL không phản hồi"
          description: "Exporter không xác nhận được trạng thái PostgreSQL cho {{ $labels.instance }}."
          runbook: "runbooks/postgresql-unavailable.md"
~~~

Chỉ dùng rule này khi metric pg_up đã được xác minh trong exporter. Nếu target scrape biến mất, pg_up có thể không có sample thay vì bằng 0; cần thêm rule cho target absent/down và phân biệt exporter down với database down.

### 8.3. Cảnh báo filesystem gần đầy

Ví dụ cảnh báo khi filesystem đã dùng trên 85% trong 10 phút:

~~~yaml
- alert: PostgreSQLFilesystemUsageHigh
  expr: |
    100 * (
      1 -
      node_filesystem_avail_bytes{mountpoint="/var/lib/postgresql"}
      /
      node_filesystem_size_bytes{mountpoint="/var/lib/postgresql"}
    ) > 85
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Filesystem PostgreSQL gần đầy"
    description: "Mountpoint {{ $labels.mountpoint }} trên {{ $labels.instance }} đã dùng hơn 85%."
    runbook: "runbooks/postgresql-disk-capacity.md"
~~~

Mountpoint trong ví dụ phải thay bằng đường dẫn thực tế của lab. Nếu WAL, log hoặc backup nằm trên volume riêng, tạo rule riêng cho từng volume. Dùng available bytes thay vì free bytes khi filesystem dành trước một phần dung lượng cho root hoặc metadata.

Nên có ngưỡng critical cao hơn, chẳng hạn 95%, nhưng phải đặt theo thời gian cần để mở rộng volume và tốc độ tăng dữ liệu. Với volume nhỏ, 95% có thể đã quá muộn; với volume lớn và tốc độ tăng thấp, có thể chọn cách khác.

### 8.4. Cảnh báo số kết nối cao

Nếu exporter cung cấp metric số backend và max_connections, có thể tạo rule theo tỷ lệ:

~~~promql
100 *
pg_stat_activity_count
/
pg_settings_max_connections
> 80
~~~

Tên metric ở ví dụ có thể khác giữa các phiên bản hoặc custom query. Hãy xác minh metric, label instance và cách exporter tính backend. Nếu không có metric phù hợp, dùng custom query hoặc dashboard SQL.

Không chỉ nhìn tổng số kết nối. Khi tỷ lệ cao, hãy xem active, idle, idle in transaction, reserved connection và số pool instance. Cảnh báo cần hướng người học đến việc kiểm tra pool, connection leak và giới hạn backend.

### 8.5. Cảnh báo backup quá hạn

Backup age cần dựa trên mốc thời gian backup thành công gần nhất từ hệ thống backup, không suy ra từ việc PostgreSQL đang hoạt động. Ví dụ nếu lab yêu cầu có backup ít nhất mỗi ngày, cảnh báo khi thời gian từ lần backup thành công gần nhất vượt 26 giờ.

Metric có thể là timestamp epoch do job backup tự xuất:

~~~promql
time() - postgresql_backup_last_success_timestamp_seconds > 26 * 3600
~~~

Đây là metric mẫu cần được tạo bởi job backup hoặc custom exporter. Hãy kiểm tra job có cập nhật timestamp chỉ sau khi backup hoàn tất và xác minh thành công. Không cập nhật timestamp khi job chỉ mới bắt đầu.

### 8.6. Cảnh báo replication lag

Chỉ bật khi lab có standby. Đặt ngưỡng theo RPO, workload và mục đích standby. Có thể dùng lag bytes hoặc thời gian replay, nhưng không coi NULL trong lúc primary không phát sinh ghi là sự cố.

Cảnh báo nên đi kèm runbook kiểm tra:

- Standby có đang kết nối không.
- WAL sender/receiver state.
- Replication slot có giữ WAL không.
- Mạng giữa primary và standby.
- Tốc độ phát sinh WAL có tăng bất thường không.
- Standby có đang replay hoặc bị query dài làm trì hoãn replay không.

### 8.7. Cảnh báo không có dữ liệu

Một target biến mất có thể làm biểu thức alert không trả về dòng nào. Tùy hệ thống alerting, no data có thể được xử lý là OK, NoData hoặc Error. Cấu hình rõ hành vi khi thiếu dữ liệu và tạo cảnh báo riêng cho exporter hoặc Prometheus scrape failure.

Không để trạng thái “không có sample” bị hiểu thành database khỏe mạnh. Đồng thời, tránh tạo nhiều cảnh báo giống nhau khi một host down làm tất cả exporter metrics biến mất.

## 9. Nhóm cảnh báo và giảm nhiễu

Khi có nhiều alert cùng phát sinh, hãy nhóm theo instance, cluster hoặc môi trường để người nhận thấy một sự cố chính thay vì hàng chục thông báo lặp.

Các nguyên tắc:

- Đặt tên alert theo thành phần và tình trạng.
- Gắn labels như severity, environment, service và instance.
- Dùng annotations có mô tả, giá trị hiện tại và link runbook.
- Dùng for duration phù hợp với đặc tính metric.
- Có ngưỡng hồi phục hoặc hysteresis để tránh bật/tắt liên tục.
- Nhóm các alert liên quan đến cùng một sự cố.
- Không gửi cảnh báo cho lab vào contact point production.
- Ghi nhận thời điểm firing, acknowledged, resolved và hành động xử lý.

Một alert nên có một người hoặc vai trò chịu trách nhiệm. Với bài thực hành, người học là người trực ca; hãy ghi rõ ai thực hiện, ai xác nhận và ai được phép thao tác phá hủy dữ liệu.

## 10. Thiết kế runbook

Runbook là tài liệu hành động theo từng tình huống. Nó cần đủ cụ thể để người khác làm theo, nhưng không khuyến khích chạy lệnh thay đổi trạng thái trước khi xác minh.

Mỗi runbook nên có:

| Trường | Nội dung |
|---|---|
| Tên sự cố | Tên ngắn, trùng với alert |
| Mục tiêu | Dịch vụ hoặc chỉ số cần khôi phục |
| Phạm vi | Instance, database, môi trường, phiên bản |
| Mức độ | Warning/Critical và tác động |
| Điều kiện kích hoạt | Alert expression và thời gian duy trì |
| Kiểm tra ban đầu | Metrics, log, SQL và thời điểm |
| Nguyên nhân thường gặp | Những giả thuyết có thể kiểm chứng |
| Các bước xử lý | Thứ tự thao tác và điều kiện tiếp tục |
| Rollback | Cách quay lại cấu hình trước |
| Xác nhận phục hồi | Chỉ số và phép thử sau xử lý |
| Escalation | Khi nào cần quản trị viên hoặc nhóm khác |
| Nhật ký | Thời điểm, người xử lý, thay đổi và kết quả |

Runbook cần ghi rõ lệnh nào chỉ đọc, lệnh nào thay đổi trạng thái, lệnh nào có thể gây downtime hoặc mất dữ liệu. Không đặt password trong ví dụ. Dùng placeholder cho hostname, database và đường dẫn; hướng dẫn người học lấy giá trị từ cấu hình lab đã cấp.

## 11. Runbook mẫu: PostgreSQL không phản hồi

**Alert:** PostgreSQLUnavailable

**Mục tiêu:** Xác định database down, exporter down hay lỗi mạng giữa collector và database; khôi phục khả năng kết nối có kiểm chứng.

### Kiểm tra ban đầu

1. Ghi lại thời điểm alert và instance.
2. Mở dashboard tổng quan, kiểm tra exporter target và PostgreSQL status.
3. Kiểm tra log exporter, Prometheus và PostgreSQL.
4. Xác định lỗi chỉ xảy ra từ exporter hay ứng dụng cũng không kết nối được.

Trên máy chạy PostgreSQL:

~~~bash
systemctl status postgresql
~~~

Tên service có thể khác theo distro và cách cài đặt. Với Docker:

~~~bash
docker compose ps
docker compose logs --tail=100 postgres
~~~

Kiểm tra readiness:

~~~bash
pg_isready -h 127.0.0.1 -p 5432
~~~

Kiểm tra listener:

~~~bash
ss -lntp | grep 5432
~~~

### Phân nhánh xử lý

- Nếu service dừng: đọc log khởi động và log hệ điều hành trước khi start. Xác minh nguyên nhân như disk full, config sai, permission hoặc crash.
- Nếu service chạy nhưng không listen: kiểm tra port và listen_addresses, sau đó đối chiếu trạng thái reload/restart.
- Nếu local kết nối được nhưng remote không được: kiểm tra route, firewall, security group và pg_hba.conf.
- Nếu exporter down nhưng ứng dụng vẫn hoạt động: kiểm tra exporter service, DNS, network, secret và quyền monitoring.
- Nếu service restart liên tục: không lặp lệnh restart; thu thập log và kiểm tra tài nguyên, file cấu hình, dung lượng và lỗi hệ điều hành.

### Xác nhận phục hồi

- pg_isready báo server đang nhận kết nối.
- Ứng dụng kết nối thành công từ đúng môi trường.
- Exporter target trở lại UP và metrics mới xuất hiện.
- Dashboard không còn khoảng trống dữ liệu bất thường.
- Không còn lỗi lặp trong log.
- Ghi lại nguyên nhân và thao tác đã thực hiện.

## 12. Runbook mẫu: Filesystem chứa PostgreSQL gần đầy

**Alert:** PostgreSQLFilesystemUsageHigh

**Mục tiêu:** Xác định volume nào đầy, nguyên nhân tăng dung lượng và giải phóng hoặc mở rộng dung lượng an toàn.

### Kiểm tra ban đầu

~~~bash
df -h
df -i
du -xhd1 /var/lib/postgresql
~~~

Các lệnh trên dành cho Linux; đường dẫn phải đổi theo PGDATA thực tế. df -i kiểm tra inode, vì filesystem có thể hết inode dù còn dung lượng byte.

Từ PostgreSQL:

~~~sql
SHOW data_directory;
SHOW log_directory;
SHOW archive_mode;
~~~

Kiểm tra database và bảng lớn bằng pg_database_size và pg_total_relation_size. Kiểm tra WAL archiver:

~~~sql
SELECT
    archived_count,
    failed_count,
    last_failed_time,
    last_failed_wal
FROM pg_stat_archiver;
~~~

Nếu có replication slot:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots;
~~~

### Phân nhánh xử lý

- Nếu log tăng nhanh: xác định loại log, nguyên nhân lặp và chính sách rotation. Không xóa log đang được PostgreSQL ghi mà chưa hiểu cơ chế quản lý file.
- Nếu WAL tăng nhanh: kiểm tra archive failure, replication lag và slot giữ WAL. Sửa consumer hoặc archive theo quy trình.
- Nếu backup nằm trên cùng volume: kiểm tra retention và chuyển backup sang nơi lưu phù hợp sau khi xác minh bản backup và chính sách.
- Nếu dữ liệu nghiệp vụ tăng thật: mở rộng volume hoặc thực hiện chính sách lưu trữ/partition/retention đã được phê duyệt.
- Nếu bảng hoặc index tăng bất thường: kiểm tra workload, bloat, migration và các lần tạo index.

**Không xóa thủ công file trong pg_wal hoặc thư mục dữ liệu để lấy lại dung lượng.** Làm vậy có thể khiến PostgreSQL không thể phục hồi hoặc khởi động. Không chạy VACUUM FULL tùy tiện khi volume gần đầy vì thao tác này cần thêm dung lượng và có thể khóa bảng lâu.

### Xác nhận phục hồi

- Filesystem có khoảng trống đủ theo kế hoạch.
- WAL archive và replication hoạt động trở lại nếu có.
- PostgreSQL vẫn nhận kết nối và truy vấn cơ bản thành công.
- Alert chuyển Resolved sau khoảng duy trì hồi phục.
- Đã ghi nguyên nhân tăng dung lượng và hành động phòng ngừa.

## 13. Runbook mẫu: Connections tăng cao hoặc cạn connection

**Alert:** PostgreSQLConnectionsHigh

**Mục tiêu:** Phân biệt tải thật, connection pool cấu hình sai, session idle in transaction và connection leak.

### Kiểm tra

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    COUNT(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Xem session theo ứng dụng:

~~~sql
SELECT
    application_name,
    usename,
    client_addr,
    state,
    COUNT(*) AS sessions,
    MAX(now() - xact_start) AS oldest_transaction
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY application_name, usename, client_addr, state
ORDER BY sessions DESC;
~~~

Xem giới hạn:

~~~sql
SELECT
    current_setting('max_connections')::integer AS max_connections,
    COUNT(*) FILTER (
        WHERE backend_type = 'client backend'
    ) AS client_backends
FROM pg_stat_activity;
~~~

### Xử lý

- Xác định ứng dụng hoặc pool tạo nhiều kết nối nhất.
- Kiểm tra số instance ứng dụng nhân với max pool size; tổng có thể vượt giới hạn PostgreSQL.
- Kiểm tra idle in transaction và transaction lâu.
- Kiểm tra retry storm khi database chậm hoặc mất kết nối.
- Giảm pool size hoặc giới hạn concurrency nếu cấu hình ứng dụng là nguyên nhân.
- Chỉ terminate session khi đã xác định owner, tác động và được phép.

Không terminate hàng loạt session chỉ để làm alert biến mất. Không tăng max_connections mà chưa đánh giá RAM và chi phí mỗi backend.

### Xác nhận phục hồi

- Số connection trở về vùng vận hành bình thường.
- Ứng dụng mở kết nối mới và xử lý request thành công.
- Không còn transaction treo bất thường.
- Pool không tiếp tục tăng không kiểm soát.
- Không phát sinh lỗi connection refused hoặc too many connections mới.

## 14. Runbook mẫu: Query chậm, lock và deadlock

**Alert:** PostgreSQLLongRunningQuery hoặc PostgreSQLDeadlocks

### Kiểm tra query và wait event

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    LEFT(query, 300) AS query_preview
FROM pg_stat_activity
WHERE pid <> pg_backend_pid()
  AND (
      state = 'active'
      OR state = 'idle in transaction'
  )
ORDER BY query_start NULLS LAST;
~~~

Kiểm tra blocking session bằng hàm pg_blocking_pids:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    now() - blocked.query_start AS blocked_duration,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocker.state AS blocker_state,
    LEFT(blocker.query, 200) AS blocker_query
FROM pg_stat_activity AS blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS blocking_pid(pid)
    ON true
JOIN pg_stat_activity AS blocker
    ON blocker.pid = blocking_pid.pid
ORDER BY blocked.query_start;
~~~

### Xử lý

- Xác định query đang chạy hay đang chờ lock.
- Nếu chờ lock, tìm blocker và owner của transaction.
- Kiểm tra ứng dụng có giữ transaction mở quá lâu không.
- Xem EXPLAIN (ANALYZE, BUFFERS) trong môi trường phù hợp để tìm scan, sort hoặc join tốn kém.
- Với deadlock, đọc log để xác định các transaction và thứ tự khóa.
- Chỉ cancel hoặc terminate backend khi đã đánh giá tác động và có quyền.

pg_cancel_backend gửi yêu cầu hủy truy vấn hiện tại; pg_terminate_backend kết thúc session. Hai thao tác có tác động khác nhau và có thể làm ứng dụng rollback transaction. Không tự động dùng terminate như bước đầu tiên.

### Xác nhận phục hồi

- Wait event và số session bị block giảm.
- Query latency trở lại vùng bình thường.
- Deadlock không tiếp tục tăng bất thường.
- Ứng dụng hoàn thành transaction và không xuất hiện lỗi dữ liệu.

## 15. Runbook mẫu: Backup hoặc WAL archiving thất bại

**Alert:** PostgreSQLBackupOverdue hoặc PostgreSQLArchiveFailures

### Kiểm tra

- Xem kết quả job backup và exit code.
- Xác định backup gần nhất thực sự hoàn tất.
- Kiểm tra dung lượng nơi lưu, quyền truy cập, network và credentials.
- Đọc pg_stat_archiver và log PostgreSQL.
- Kiểm tra WAL đang tích tụ và các replication slot.
- Kiểm tra lịch retention và thời gian chạy backup.

### Xử lý

- Sửa lỗi credential, quyền, network hoặc dung lượng theo nguyên nhân.
- Chạy lại backup theo quy trình; không ghi đè bản backup tốt gần nhất nếu chưa có kế hoạch.
- Nếu archive lỗi, khôi phục đích archive và kiểm tra tiến trình archive tiếp tục.
- Không xóa WAL đang cần cho archive hoặc replication.
- Sau backup, thực hiện kiểm tra checksum hoặc restore test theo khả năng công cụ.

### Xác nhận phục hồi

- Job backup mới kết thúc thành công.
- Timestamp last success được cập nhật sau khi hoàn tất.
- File backup hoặc artifact tồn tại và có thể đọc.
- Restore test thành công trong môi trường riêng theo lịch.
- WAL archive tiếp tục tiến triển và dung lượng ổn định.

## 16. Tổ chức thư mục runbook trong repository hoặc lab

Có thể sắp xếp tài liệu theo cấu trúc:

~~~text
observability/
├── prometheus/
│   ├── prometheus.yml
│   └── alerts/
│       ├── postgres-availability.yml
│       ├── postgres-capacity.yml
│       └── postgres-workload.yml
├── grafana/
│   ├── dashboards/
│   │   ├── postgres-overview.json
│   │   ├── postgres-workload.json
│   │   └── postgres-capacity.json
│   └── provisioning/
├── exporter/
│   └── README.md
└── runbooks/
    ├── README.md
    ├── postgresql-unavailable.md
    ├── postgresql-disk-capacity.md
    ├── postgresql-connections.md
    ├── postgresql-locks-and-slow-queries.md
    └── postgresql-backup-and-wal.md
~~~

Đây là cấu trúc gợi ý. Điều chỉnh theo repository thực tế và cách triển khai của lab. Mỗi dashboard JSON, alert rule và runbook nên có phiên bản, người sở hữu và cách kiểm thử.

Không commit secret vào thư mục observability. Có thể commit file cấu hình mẫu với placeholder, còn password, private key, webhook URL và token được đưa vào secret store hoặc file cấu hình cục bộ không theo dõi bởi Git.

## 17. Kiểm thử dashboard và cảnh báo trong lab

Một cảnh báo chưa từng được kích hoạt chưa chắc đã hoạt động đúng. Cần tạo tình huống thử có kiểm soát và kiểm tra cả đường đi từ metric đến thông báo.

### 17.1. Kiểm tra dashboard

1. Mở PostgreSQL và xác nhận target exporter UP.
2. Chạy một workload đọc/ghi nhẹ.
3. Quan sát transaction rate và connection count.
4. Chạy truy vấn có thời gian đủ dài trong lab, quan sát active query.
5. Tạo dữ liệu mẫu để tăng dung lượng bảng.
6. Xác nhận dashboard cập nhật trong khoảng thời gian scrape.
7. Tắt exporter trong thời gian ngắn và kiểm tra dashboard thể hiện trạng thái thiếu metrics.

Không tạo tải nặng hoặc cố tình làm đầy ổ đĩa trên máy dùng chung. Mọi thử nghiệm tạo sự cố cần có giới hạn, thời gian kết thúc và cách khôi phục.

### 17.2. Kiểm thử alert rule

Với từng alert:

- Kiểm tra expression trả về đúng series khi điều kiện bình thường.
- Tạo tình huống vượt ngưỡng trong lab.
- Xác nhận alert chuyển Pending rồi Firing theo thời gian for.
- Xác nhận label, annotation và link runbook đúng.
- Xác nhận thông báo đến đúng contact point lab.
- Khôi phục tình trạng và xác nhận alert chuyển Resolved.
- Kiểm tra trường hợp metric biến mất để xác nhận no-data behavior.

Đối với alert disk, không cần làm đầy volume thật. Có thể dùng một metric thử nghiệm hoặc rule tạm với ngưỡng thấp hơn để kiểm tra đường thông báo. Sau kiểm thử, xóa rule thử nghiệm và xác nhận cấu hình production/lab chính trở về trạng thái mong muốn.

### 17.3. Kiểm thử runbook

Chọn một người chưa viết runbook thực hiện theo tài liệu. Ghi lại:

- Bước nào thiếu thông tin?
- Lệnh nào không chạy trong môi trường hiện tại?
- Có bước nào cần quyền mà người trực không có?
- Điều kiện nào cho phép chuyển sang bước tiếp theo?
- Kết quả nào xác nhận đã phục hồi?
- Khi nào phải dừng và escalates?

Cập nhật runbook sau mỗi lần diễn tập. Một runbook chỉ được xem là hữu ích khi người khác có thể dùng nó để xử lý cùng tình huống mà không cần đoán.

## 18. Bảo mật và giới hạn dữ liệu quan sát

Dashboard và exporter có thể làm lộ thông tin về hạ tầng, người dùng, database và câu SQL. Cần bảo vệ:

- Tài khoản monitoring và secret của exporter.
- Endpoint /metrics, Prometheus và Grafana.
- Dashboard có query text, username, client IP hoặc tên database.
- Webhook, token và contact point.
- Log có thể chứa literal, dữ liệu cá nhân hoặc nội dung ứng dụng.

Đặt authentication cho Grafana, giới hạn quyền truy cập dashboard và chỉ mở exporter trong mạng quản trị. Không expose PostgreSQL exporter hoặc Prometheus ra Internet công cộng. Nếu cần chia sẻ dashboard cho người học, dùng tài khoản chỉ đọc và dataset đã làm sạch.

Metrics cũng có chi phí. Label có độ biến thiên cao như query text, request id hoặc user id có thể làm tăng cardinality rất lớn. Tránh đưa nội dung SQL đầy đủ thành label Prometheus; dùng queryid hoặc một bảng top query có kiểm soát trong dashboard.

## 19. Checklist hoàn thiện lab

- [ ] PostgreSQL có health check và log truy cập được.
- [ ] Role monitoring có quyền tối thiểu và secret được bảo vệ.
- [ ] Exporter và node metrics thu thập thành công.
- [ ] Prometheus targets hiển thị đúng trạng thái.
- [ ] Dashboard tổng quan có health, workload, capacity và reliability.
- [ ] Các bộ đếm được hiển thị bằng rate hoặc increase khi phù hợp.
- [ ] Dashboard phân biệt active, idle và idle in transaction.
- [ ] Filesystem chứa data, WAL và backup được xác định rõ.
- [ ] Alert database down, disk usage và các điều kiện quan trọng đã được kiểm thử.
- [ ] No-data và exporter-down được xử lý riêng.
- [ ] Mỗi alert có severity, mô tả và liên kết runbook.
- [ ] Contact point lab được kiểm thử và không gửi nhầm đến production.
- [ ] Runbook có bước xác minh, xử lý, rollback và xác nhận phục hồi.
- [ ] Backup đã có restore test theo lịch.
- [ ] Dashboard, alert rule và runbook được lưu phiên bản.
- [ ] Không có password, private key hoặc token trong Git và dashboard export.

## 20. Mẫu ghi nhận sự cố sau khi diễn tập

Sau mỗi lần thử, ghi nhận theo mẫu:

~~~text
Incident ID:
Thời điểm bắt đầu:
Thời điểm phát hiện:
Thời điểm phục hồi:
Môi trường / instance:
Alert:
Severity:
Triệu chứng người dùng:
Metrics và log liên quan:
Nguyên nhân gốc:
Các giả thuyết đã loại trừ:
Thao tác đã thực hiện:
Rollback (nếu có):
Kết quả xác nhận phục hồi:
Ảnh hưởng dữ liệu:
Thời gian gián đoạn:
Runbook cần cập nhật:
Hành động phòng ngừa:
Người thực hiện / người xác nhận:
~~~

Phân biệt thời điểm phát hiện và thời điểm bắt đầu sự cố để tính thời gian phát hiện (MTTD). Phân biệt thời điểm phát hiện và thời điểm phục hồi để tính thời gian khôi phục (MTTR) theo định nghĩa của nhóm. Không kết luận nguyên nhân gốc chỉ từ một alert; cần có bằng chứng từ log, metrics hoặc thử nghiệm tái hiện.

## Kết luận

Dashboard cho người vận hành thấy trạng thái và xu hướng; cảnh báo giúp nhận biết điều kiện cần chú ý; runbook chuyển tín hiệu đó thành hành động có kiểm soát. Một lab tốt phải kiểm tra được toàn bộ chuỗi này: PostgreSQL phát sinh số liệu, exporter thu thập, Prometheus lưu và đánh giá rule, Grafana hiển thị, thông báo đến đúng người và runbook giúp xác nhận phục hồi.

Hãy bắt đầu với các chỉ số cơ bản, ghi rõ nguồn và ngữ nghĩa của từng metric, thiết kế cảnh báo có hành động cụ thể rồi diễn tập từng tình huống. Khi dashboard, alert và runbook được kiểm thử cùng nhau, môi trường thực hành sẽ dạy được cả cách theo dõi lẫn cách vận hành PostgreSQL khi có sự cố.
